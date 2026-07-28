import {
  COLLAPSE_KIND,
  applyCollapsePlan,
  buildCollapsePlan,
  findLogBracket,
  interpolateOpacityLogLog,
  makeLogEdges,
  parsePositiveList,
  parseStrictlyIncreasingEdges,
  requiredFieldsForCollapse,
} from './opacity_math.mjs';

const DATA_ROOT = 'solar_final/web_data';
const MANIFEST_URL = `${DATA_ROOT}/manifest.json`;
const AXES_URL = `${DATA_ROOT}/axes.json`;

const PREVIEW_ROW_LIMIT = 300;
const MAX_OUTPUT_ROWS = 2_000_000;
const MAX_TEMPERATURE_VALUES = 256;
const MAX_DENSITY_VALUES = 256;
const MAX_SPECTRA = 4096;
const TRANSFER_WARNING_BYTES = 100 * 1024 * 1024;

const state = {
  manifest: null,
  axes: null,
  chunkCache: new Map(),
  collapsePlanCache: new Map(),
};

const elements = {
  loadingMessage: document.querySelector('#loading-message'),
  form: document.querySelector('#selection-form'),
  fieldSelect: document.querySelector('#field-select'),
  temperatureSelect: document.querySelector('#temperature-select'),
  temperatureList: document.querySelector('#temperature-list'),
  densityMinSelect: document.querySelector('#density-min-select'),
  densityMaxSelect: document.querySelector('#density-max-select'),
  densityList: document.querySelector('#density-list'),
  groupMinInput: document.querySelector('#group-min-input'),
  groupMaxInput: document.querySelector('#group-max-input'),
  energyEdgeList: document.querySelector('#energy-edge-list'),
  energyLogMin: document.querySelector('#energy-log-min'),
  energyLogMax: document.querySelector('#energy-log-max'),
  energyLogCount: document.querySelector('#energy-log-count'),
  temperatureNativePanel: document.querySelector('#temperature-native-panel'),
  temperatureCustomPanel: document.querySelector('#temperature-custom-panel'),
  densityNativePanel: document.querySelector('#density-native-panel'),
  densityCustomPanel: document.querySelector('#density-custom-panel'),
  energyNativePanel: document.querySelector('#energy-native-panel'),
  energyCustomPanel: document.querySelector('#energy-custom-panel'),
  energyLogPanel: document.querySelector('#energy-log-panel'),
  temperatureSummary: document.querySelector('#temperature-summary'),
  densitySummary: document.querySelector('#density-summary'),
  groupSummary: document.querySelector('#group-summary'),
  rowSummary: document.querySelector('#row-summary'),
  chunkSummary: document.querySelector('#chunk-summary'),
  transferSummary: document.querySelector('#transfer-summary'),
  formError: document.querySelector('#form-error'),
  previewButton: document.querySelector('#preview-button'),
  downloadButton: document.querySelector('#download-button'),
  previewSection: document.querySelector('#preview-section'),
  previewDescription: document.querySelector('#preview-description'),
  previewLimit: document.querySelector('#preview-limit'),
  previewBody: document.querySelector('#preview-body'),
};

function selectedMode(name) {
  return document.querySelector(`input[name="${name}"]:checked`).value;
}

function formatScientific(value, digits = 6) {
  if (!Number.isFinite(value)) return 'nan';
  if (value === 0) return '0';
  return value.toExponential(digits);
}

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KiB`;
  return `${(bytes / 1024 ** 2).toFixed(2)} MiB`;
}

function showError(message) {
  elements.formError.textContent = message;
  elements.formError.hidden = false;
}

function clearError() {
  elements.formError.textContent = '';
  elements.formError.hidden = true;
}

function setBusy(isBusy, message = '') {
  elements.previewButton.disabled = isBusy;
  elements.downloadButton.disabled = isBusy;
  if (message) {
    elements.loadingMessage.textContent = message;
    elements.loadingMessage.hidden = false;
  } else if (state.manifest) {
    elements.loadingMessage.hidden = true;
  }
}

async function fetchJson(url) {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`Could not load ${url}: HTTP ${response.status}`);
  return response.json();
}

async function decompressGzip(response) {
  if (!('DecompressionStream' in window)) {
    throw new Error('This browser does not support DecompressionStream(gzip).');
  }
  const stream = response.body.pipeThrough(new DecompressionStream('gzip'));
  return new Response(stream).arrayBuffer();
}

async function loadChunk(chunkInfo) {
  if (state.chunkCache.has(chunkInfo.file)) return state.chunkCache.get(chunkInfo.file);

  const promise = (async () => {
    const url = `${DATA_ROOT}/${chunkInfo.file}`;
    const response = await fetch(url);
    if (!response.ok) throw new Error(`Could not load ${url}: HTTP ${response.status}`);
    const buffer = await decompressGzip(response);
    const expectedValues = chunkInfo.shape.reduce((product, size) => product * size, 1);
    if (buffer.byteLength !== expectedValues * 8) {
      throw new Error(`${chunkInfo.file} has ${buffer.byteLength} bytes; expected ${expectedValues * 8}.`);
    }
    return new Float64Array(buffer);
  })();

  state.chunkCache.set(chunkInfo.file, promise);
  try {
    return await promise;
  } catch (error) {
    state.chunkCache.delete(chunkInfo.file);
    throw error;
  }
}

function findTemperaturePart(globalTemperatureIndex) {
  const part = state.manifest.parts.find((candidate) => (
    globalTemperatureIndex >= candidate.temperature_global_start &&
    globalTemperatureIndex < candidate.temperature_global_stop
  ));
  if (!part) throw new Error(`No temperature part contains global index ${globalTemperatureIndex}.`);
  return part;
}

function findChunkInfo(part, field, groupIndex) {
  const chunk = part.chunks.find((candidate) => (
    candidate.field === field &&
    groupIndex >= candidate.group_start &&
    groupIndex < candidate.group_stop
  ));
  if (!chunk) {
    throw new Error(`No ${field} chunk in part ${part.part_index} contains group ${groupIndex}.`);
  }
  return chunk;
}

function updateModePanels() {
  const temperatureMode = selectedMode('temperature-mode');
  const densityMode = selectedMode('density-mode');
  const energyMode = selectedMode('energy-mode');

  elements.temperatureNativePanel.hidden = temperatureMode !== 'native';
  elements.temperatureCustomPanel.hidden = temperatureMode !== 'custom';
  elements.densityNativePanel.hidden = densityMode !== 'native';
  elements.densityCustomPanel.hidden = densityMode !== 'custom';
  elements.energyNativePanel.hidden = energyMode !== 'native';
  elements.energyCustomPanel.hidden = energyMode !== 'custom';
  elements.energyLogPanel.hidden = energyMode !== 'log';
  updateSummary();
}

function checkInsideAxis(values, axis, label) {
  const minimum = axis[0];
  const maximum = axis[axis.length - 1];
  for (const value of values) {
    if (value < minimum || value > maximum) {
      throw new Error(`${label} ${value} is outside [${minimum}, ${maximum}]. Extrapolation is disabled.`);
    }
  }
}

function getTemperatureValues() {
  if (selectedMode('temperature-mode') === 'native') {
    const index = Number.parseInt(elements.temperatureSelect.value, 10);
    return [state.axes.temp_eV[index]];
  }
  const values = parsePositiveList(elements.temperatureList.value, 'Temperature');
  if (values.length > MAX_TEMPERATURE_VALUES) {
    throw new Error(`At most ${MAX_TEMPERATURE_VALUES} temperatures may be requested.`);
  }
  checkInsideAxis(values, state.axes.temp_eV, 'Temperature');
  return values;
}

function getDensityValues() {
  if (selectedMode('density-mode') === 'native') {
    const minimumIndex = Number.parseInt(elements.densityMinSelect.value, 10);
    const maximumIndex = Number.parseInt(elements.densityMaxSelect.value, 10);
    if (minimumIndex > maximumIndex) {
      throw new Error('Minimum native density must not exceed maximum native density.');
    }
    return state.axes.rho_gcc.slice(minimumIndex, maximumIndex + 1);
  }
  const values = parsePositiveList(elements.densityList.value, 'Density');
  if (values.length > MAX_DENSITY_VALUES) {
    throw new Error(`At most ${MAX_DENSITY_VALUES} densities may be requested.`);
  }
  checkInsideAxis(values, state.axes.rho_gcc, 'Density');
  return values;
}

function energyRangeToNativeGroups(outputEdges) {
  const nativeEdges = state.axes.hnu_ev_edges;
  const minimum = outputEdges[0];
  const maximum = outputEdges[outputEdges.length - 1];
  if (minimum < nativeEdges[0] || maximum > nativeEdges[nativeEdges.length - 1]) {
    throw new Error(
      `Energy edges must remain within [${nativeEdges[0]}, ${nativeEdges[nativeEdges.length - 1]}] eV.`,
    );
  }

  let start = 0;
  while (start < nativeEdges.length - 1 && nativeEdges[start + 1] <= minimum) start += 1;
  let stopExclusive = start;
  while (stopExclusive < nativeEdges.length - 1 && nativeEdges[stopExclusive] < maximum) {
    stopExclusive += 1;
  }
  return { start, stopExclusive };
}

function getEnergyDefinition() {
  const mode = selectedMode('energy-mode');
  const nativeGroupCount = state.manifest.dimensions.groups;

  if (mode === 'native') {
    const start = Number.parseInt(elements.groupMinInput.value, 10);
    const last = Number.parseInt(elements.groupMaxInput.value, 10);
    if (!Number.isInteger(start) || !Number.isInteger(last)) {
      throw new Error('Native group indices must be integers.');
    }
    if (start < 0 || last >= nativeGroupCount || start > last) {
      throw new Error(`Native groups must satisfy 0 <= first <= last <= ${nativeGroupCount - 1}.`);
    }
    return {
      mode,
      outputEdges: state.axes.hnu_ev_edges.slice(start, last + 2),
      nativeGroupStart: start,
      nativeGroupStopExclusive: last + 1,
      outputBinCount: last - start + 1,
    };
  }

  let outputEdges;
  if (mode === 'custom') {
    outputEdges = parseStrictlyIncreasingEdges(elements.energyEdgeList.value);
    if (outputEdges.length - 1 > 1024) {
      throw new Error('At most 1024 custom output groups may be requested.');
    }
  } else {
    const minimum = Number(elements.energyLogMin.value);
    const maximum = Number(elements.energyLogMax.value);
    const count = Number.parseInt(elements.energyLogCount.value, 10);
    outputEdges = makeLogEdges(minimum, maximum, count);
  }

  const range = energyRangeToNativeGroups(outputEdges);
  return {
    mode,
    outputEdges,
    nativeGroupStart: range.start,
    nativeGroupStopExclusive: range.stopExclusive,
    outputBinCount: outputEdges.length - 1,
  };
}

function uniqueRequiredChunks(field, temperatureBrackets, energy) {
  const requiredFields = new Set(requiredFieldsForCollapse(field));
  const temperatureIndices = new Set();
  for (const bracket of temperatureBrackets) {
    temperatureIndices.add(bracket.lowerIndex);
    temperatureIndices.add(bracket.upperIndex);
  }

  const parts = new Map();
  for (const temperatureIndex of temperatureIndices) {
    const part = findTemperaturePart(temperatureIndex);
    parts.set(part.part_index, part);
  }

  const chunks = new Map();
  for (const part of parts.values()) {
    for (const chunk of part.chunks) {
      if (
        requiredFields.has(chunk.field) &&
        chunk.group_stop > energy.nativeGroupStart &&
        chunk.group_start < energy.nativeGroupStopExclusive
      ) {
        chunks.set(chunk.file, chunk);
      }
    }
  }
  return [...chunks.values()];
}

function getQuery() {
  const field = elements.fieldSelect.value;
  if (!(field in state.manifest.field_metadata)) throw new Error(`Unknown opacity field: ${field}`);

  const temperatures = getTemperatureValues();
  const densities = getDensityValues();
  const energy = getEnergyDefinition();
  const spectra = temperatures.length * densities.length;
  const rowCount = spectra * energy.outputBinCount;

  if (spectra > MAX_SPECTRA) {
    throw new Error(`The query contains ${spectra.toLocaleString()} spectra; the limit is ${MAX_SPECTRA}.`);
  }
  if (rowCount > MAX_OUTPUT_ROWS) {
    throw new Error(
      `The query contains ${rowCount.toLocaleString()} output rows; the limit is ${MAX_OUTPUT_ROWS.toLocaleString()}.`,
    );
  }

  const temperatureBrackets = temperatures.map((value) => (
    findLogBracket(state.axes.temp_eV, value, 'Temperature')
  ));
  const densityBrackets = densities.map((value) => (
    findLogBracket(state.axes.rho_gcc, value, 'Density')
  ));
  const chunks = uniqueRequiredChunks(field, temperatureBrackets, energy);
  const compressedBytes = chunks.reduce((sum, chunk) => sum + chunk.compressed_bytes, 0);

  return {
    field,
    temperatures,
    densities,
    temperatureBrackets,
    densityBrackets,
    energy,
    spectra,
    rowCount,
    chunks,
    compressedBytes,
  };
}

function updateSummary() {
  if (!state.manifest) return;
  clearError();
  try {
    const query = getQuery();
    elements.temperatureSummary.textContent = query.temperatures.length.toLocaleString();
    elements.densitySummary.textContent = query.densities.length.toLocaleString();
    elements.groupSummary.textContent = query.energy.outputBinCount.toLocaleString();
    elements.rowSummary.textContent = query.rowCount.toLocaleString();
    elements.chunkSummary.textContent = query.chunks.length.toLocaleString();
    elements.transferSummary.textContent = formatBytes(query.compressedBytes) + (
      query.compressedBytes > TRANSFER_WARNING_BYTES ? ' — large transfer' : ''
    );
  } catch (error) {
    elements.temperatureSummary.textContent = '—';
    elements.densitySummary.textContent = '—';
    elements.groupSummary.textContent = '—';
    elements.rowSummary.textContent = '—';
    elements.chunkSummary.textContent = '—';
    elements.transferSummary.textContent = '—';
    showError(error.message);
  }
}

async function loadQueryChunks(query) {
  const entries = await Promise.all(query.chunks.map(async (chunkInfo) => (
    [chunkInfo.file, await loadChunk(chunkInfo)]
  )));
  return new Map(entries);
}

function readNativeValue(
  query, loadedChunks, field, groupIndex, globalTemperatureIndex, densityIndex,
) {
  const part = findTemperaturePart(globalTemperatureIndex);
  const chunkInfo = findChunkInfo(part, field, groupIndex);
  const values = loadedChunks.get(chunkInfo.file);
  if (!values) throw new Error(`Required chunk ${chunkInfo.file} was not loaded.`);

  const localGroup = groupIndex - chunkInfo.group_start;
  const localTemperature = globalTemperatureIndex - part.temperature_global_start;
  const densityCount = chunkInfo.shape[1];
  const temperatureCount = chunkInfo.shape[2];
  const flatIndex = (
    (localGroup * densityCount + densityIndex) * temperatureCount + localTemperature
  );
  return values[flatIndex];
}

function buildInterpolatedNativeSpectrum(
  query, loadedChunks, temperatureIndex, densityIndex, field = query.field,
) {
  const tBracket = query.temperatureBrackets[temperatureIndex];
  const rhoBracket = query.densityBrackets[densityIndex];
  const start = query.energy.nativeGroupStart;
  const stop = query.energy.nativeGroupStopExclusive;
  const values = new Float64Array(stop - start);
  const statuses = new Array(stop - start);

  for (let group = start; group < stop; group += 1) {
    const result = interpolateOpacityLogLog(
      (globalTIndex, rhoIndex) => readNativeValue(
        query,
        loadedChunks,
        field,
        group,
        globalTIndex,
        rhoIndex,
      ),
      tBracket,
      rhoBracket,
    );
    values[group - start] = result.value;
    statuses[group - start] = result.status;
  }
  return { values, statuses };
}

function getCollapsePlan(query, temperature) {
  const kind = COLLAPSE_KIND[query.field];
  if (!kind) throw new Error(`No collapse convention is defined for ${query.field}.`);
  const start = query.energy.nativeGroupStart;
  const stop = query.energy.nativeGroupStopExclusive;
  const nativeEdges = state.axes.hnu_ev_edges.slice(start, stop + 1);
  const edgeKey = query.energy.outputEdges.map((value) => value.toPrecision(17)).join(',');
  const key = `${kind}|${temperature.toPrecision(17)}|${start}|${stop}|${edgeKey}`;
  if (!state.collapsePlanCache.has(key)) {
    state.collapsePlanCache.set(
      key,
      buildCollapsePlan(kind, nativeEdges, query.energy.outputEdges, temperature),
    );
  }
  return state.collapsePlanCache.get(key);
}

function outputForSpectrum(query, nativeSpectrum, totalSpectrum, temperature) {
  if (query.energy.mode === 'native') {
    return Array.from(nativeSpectrum.values, (value, index) => ({
      value,
      status: nativeSpectrum.statuses[index],
    }));
  }
  const options = COLLAPSE_KIND[query.field] === 'rosseland_absorption'
    ? {
      totalOpacity: totalSpectrum.values,
      totalStatus: totalSpectrum.statuses,
    }
    : {};
  return applyCollapsePlan(
    getCollapsePlan(query, temperature),
    nativeSpectrum.values,
    nativeSpectrum.statuses,
    options,
  );
}

function forEachResult(query, loadedChunks, callback, limit = Number.POSITIVE_INFINITY) {
  let emitted = 0;
  let warningCount = 0;

  for (let ti = 0; ti < query.temperatures.length; ti += 1) {
    const temperature = query.temperatures[ti];
    for (let ri = 0; ri < query.densities.length; ri += 1) {
      const density = query.densities[ri];
      const nativeSpectrum = buildInterpolatedNativeSpectrum(
        query, loadedChunks, ti, ri, query.field,
      );
      const totalSpectrum = COLLAPSE_KIND[query.field] === 'rosseland_absorption'
        ? buildInterpolatedNativeSpectrum(query, loadedChunks, ti, ri, 'krosseland')
        : null;
      const output = outputForSpectrum(query, nativeSpectrum, totalSpectrum, temperature);

      for (let group = 0; group < output.length; group += 1) {
        const item = output[group];
        if (item.status !== 'ok' && item.status !== 'ok_zero') warningCount += 1;
        callback({
          temperature,
          density,
          outputGroup: group,
          energyLow: query.energy.outputEdges[group],
          energyHigh: query.energy.outputEdges[group + 1],
          opacity: item.value,
          status: item.status,
        });
        emitted += 1;
        if (emitted >= limit) return { emitted, warningCount, truncated: emitted < query.rowCount };
      }
    }
  }
  return { emitted, warningCount, truncated: false };
}

function renderPreview(rows, query, warningCount) {
  elements.previewBody.replaceChildren();
  const fragment = document.createDocumentFragment();
  for (const row of rows) {
    const tr = document.createElement('tr');
    const values = [
      formatScientific(row.temperature),
      formatScientific(row.density),
      String(row.outputGroup),
      formatScientific(row.energyLow),
      formatScientific(row.energyHigh),
      formatScientific(row.opacity),
      row.status,
    ];
    for (const value of values) {
      const td = document.createElement('td');
      td.textContent = value;
      tr.append(td);
    }
    fragment.append(tr);
  }
  elements.previewBody.append(fragment);
  const label = state.manifest.field_metadata[query.field].label;
  elements.previewDescription.textContent = (
    `${label}: ${query.rowCount.toLocaleString()} values; ` +
    `${warningCount.toLocaleString()} warnings in the displayed rows.`
  );
  elements.previewLimit.textContent = rows.length < query.rowCount
    ? `Showing ${rows.length.toLocaleString()} of ${query.rowCount.toLocaleString()}`
    : `${rows.length.toLocaleString()} rows`;
  elements.previewSection.hidden = false;
  elements.previewSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

async function previewSelection() {
  clearError();
  try {
    const query = getQuery();
    setBusy(true, `Loading ${query.chunks.length} compressed chunks…`);
    const loadedChunks = await loadQueryChunks(query);
    const rows = [];
    const result = forEachResult(
      query,
      loadedChunks,
      (row) => rows.push(row),
      PREVIEW_ROW_LIMIT,
    );
    renderPreview(rows, query, result.warningCount);
  } catch (error) {
    showError(error.message);
  } finally {
    setBusy(false);
  }
}

function createTextHeader(query, warningCount) {
  const metadata = state.manifest.field_metadata[query.field];
  const energyOperation = query.energy.mode === 'native'
    ? 'native 1024-group values (no energy collapse)'
    : 'weighted group collapse';
  return [
    '# GLOW custom opacity query',
    `# field: ${query.field}`,
    `# field_label: ${metadata.label}`,
    `# opacity_units: ${metadata.units}`,
    '# source_energy_groups: 1024',
    '# temperature_interpolation: linear in log(T), log(kappa)',
    '# density_interpolation: linear in log(rho), log(kappa)',
    `# energy_operation: ${energyOperation}`,
    '# planck_fields: kplanck',
    '# rosseland_total_field: krosseland',
    '# rosseland_harmonic_fields: krosseland, kross_scattering',
    '# rosseland_flux_weighted_absorption_field: krosseland_absorption',
    '# rosseland_absorption_recollapse: sum(W_i * kappa_abs_i / kappa_total_i) / sum(W_i / kappa_total_i)',
    '# recollapse_approximation: published 1024-group means are treated as piecewise constant within each native group',
    '# opacity_inside_native_group: piecewise constant',
    '# partial_native_group_overlap: weight integrated only over overlap',
    '# extrapolation: disabled',
    '# nonpositive_interpolation_policy: all-zero stencil returns zero; mixed zero/positive stencil returns nan',
    `# temperature_count: ${query.temperatures.length}`,
    `# density_count: ${query.densities.length}`,
    `# output_group_count: ${query.energy.outputBinCount}`,
    `# warning_count: ${warningCount}`,
    '#',
    '# Columns:',
    '# temperature_eV density_g_cm-3 output_group_index energy_low_eV energy_high_eV opacity_cm2_g-1 status',
    '',
  ].join('\n');
}

async function downloadSelection() {
  clearError();
  try {
    const query = getQuery();
    setBusy(true, `Loading ${query.chunks.length} compressed chunks and building TXT…`);
    const loadedChunks = await loadQueryChunks(query);
    const batches = [];
    let lines = [];
    const batchSize = 20000;

    const result = forEachResult(query, loadedChunks, (row) => {
      lines.push([
        row.temperature.toExponential(16),
        row.density.toExponential(16),
        row.outputGroup,
        row.energyLow.toExponential(16),
        row.energyHigh.toExponential(16),
        Number.isFinite(row.opacity) ? row.opacity.toExponential(16) : 'nan',
        row.status,
      ].join(' '));
      if (lines.length >= batchSize) {
        batches.push(`${lines.join('\n')}\n`);
        lines = [];
      }
    });
    if (lines.length) batches.push(`${lines.join('\n')}\n`);

    const blob = new Blob([createTextHeader(query, result.warningCount), ...batches], {
      type: 'text/plain;charset=utf-8',
    });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = (
      `GLOW_${query.field}_T${query.temperatures.length}_rho${query.densities.length}_` +
      `${query.energy.outputBinCount}groups.txt`
    );
    document.body.append(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
  } catch (error) {
    showError(error.message);
  } finally {
    setBusy(false);
  }
}

function populateControls() {
  for (const [field, metadata] of Object.entries(state.manifest.field_metadata)) {
    const option = document.createElement('option');
    option.value = field;
    option.textContent = metadata.label;
    elements.fieldSelect.append(option);
  }
  elements.fieldSelect.value = 'kplanck';

  state.axes.temp_eV.forEach((temperature, index) => {
    const option = document.createElement('option');
    option.value = String(index);
    option.textContent = `${index}: ${formatScientific(temperature, 5)} eV`;
    elements.temperatureSelect.append(option);
  });

  state.axes.rho_gcc.forEach((density, index) => {
    const option = document.createElement('option');
    option.value = String(index);
    option.textContent = `${index}: ${formatScientific(density, 5)}`;
    elements.densityMinSelect.append(option);
    elements.densityMaxSelect.append(option.cloneNode(true));
  });
  elements.densityMinSelect.value = '0';
  elements.densityMaxSelect.value = String(Math.min(7, state.axes.rho_gcc.length - 1));

  const maximumGroup = state.manifest.dimensions.groups - 1;
  elements.groupMinInput.max = String(maximumGroup);
  elements.groupMaxInput.max = String(maximumGroup);
  elements.groupMaxInput.value = String(Math.min(127, maximumGroup));

  const nativeEdges = state.axes.hnu_ev_edges;
  elements.energyLogMin.value = String(nativeEdges[0]);
  elements.energyLogMax.value = String(nativeEdges[nativeEdges.length - 1]);
}

function attachEvents() {
  document.querySelectorAll('input[name="temperature-mode"], input[name="density-mode"], input[name="energy-mode"]')
    .forEach((radio) => radio.addEventListener('change', updateModePanels));

  [
    elements.fieldSelect,
    elements.temperatureSelect,
    elements.temperatureList,
    elements.densityMinSelect,
    elements.densityMaxSelect,
    elements.densityList,
    elements.groupMinInput,
    elements.groupMaxInput,
    elements.energyEdgeList,
    elements.energyLogMin,
    elements.energyLogMax,
    elements.energyLogCount,
  ].forEach((control) => {
    control.addEventListener('input', updateSummary);
    control.addEventListener('change', updateSummary);
  });

  elements.previewButton.addEventListener('click', previewSelection);
  elements.downloadButton.addEventListener('click', downloadSelection);
}

async function initialize() {
  try {
    const [manifest, axes] = await Promise.all([
      fetchJson(MANIFEST_URL),
      fetchJson(AXES_URL),
    ]);
    state.manifest = manifest;
    state.axes = axes;

    if (manifest.dimensions.groups !== 1024) {
      throw new Error(`Expected 1024 native groups, found ${manifest.dimensions.groups}.`);
    }
    if (manifest.storage.axis_order.join(',') !== 'group,rho,temp') {
      throw new Error('Unexpected browser-data axis order.');
    }
    if (axes.temp_eV.length !== manifest.dimensions.temperatures ||
        axes.rho_gcc.length !== manifest.dimensions.densities ||
        axes.hnu_ev_edges.length !== manifest.dimensions.groups + 1) {
      throw new Error('Axis lengths disagree with the manifest.');
    }

    populateControls();
    attachEvents();
    elements.form.hidden = false;
    elements.loadingMessage.hidden = true;
    updateModePanels();
  } catch (error) {
    elements.loadingMessage.textContent = `Dataset initialization failed: ${error.message}`;
    elements.loadingMessage.classList.add('error');
  }
}

initialize();
