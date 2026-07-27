'use strict';

const DATA_ROOT = 'solar_final/web_data_prototype';
const MANIFEST_URL = `${DATA_ROOT}/manifest.json`;
const AXES_URL = `${DATA_ROOT}/axes.json`;

const PREVIEW_ROW_LIMIT = 300;
const MAX_EXPORT_ROWS = 2_000_000;

const state = {
  manifest: null,
  axes: null,
  chunkCache: new Map(),
};

const elements = {
  loadingMessage: document.querySelector('#loading-message'),
  form: document.querySelector('#selection-form'),
  temperatureSelect: document.querySelector(
    '#temperature-select'
  ),
  densityMinSelect: document.querySelector(
    '#density-min-select'
  ),
  densityMaxSelect: document.querySelector(
    '#density-max-select'
  ),
  groupMinInput: document.querySelector(
    '#group-min-input'
  ),
  groupMaxInput: document.querySelector(
    '#group-max-input'
  ),
  temperatureSummary: document.querySelector(
    '#temperature-summary'
  ),
  densitySummary: document.querySelector(
    '#density-summary'
  ),
  groupSummary: document.querySelector(
    '#group-summary'
  ),
  transferSummary: document.querySelector(
    '#transfer-summary'
  ),
  formError: document.querySelector('#form-error'),
  previewButton: document.querySelector('#preview-button'),
  downloadButton: document.querySelector('#download-button'),
  previewSection: document.querySelector('#preview-section'),
  previewDescription: document.querySelector(
    '#preview-description'
  ),
  previewLimit: document.querySelector('#preview-limit'),
  previewBody: document.querySelector('#preview-body'),
};


function formatScientific(value, digits = 6) {
  if (!Number.isFinite(value)) {
    return String(value);
  }

  if (value === 0) {
    return '0';
  }

  return value.toExponential(digits);
}


function formatBytes(bytes) {
  if (bytes < 1024) {
    return `${bytes} B`;
  }

  if (bytes < 1024 ** 2) {
    return `${(bytes / 1024).toFixed(1)} KiB`;
  }

  return `${(bytes / 1024 ** 2).toFixed(2)} MiB`;
}


async function fetchJson(url) {
  const response = await fetch(url);

  if (!response.ok) {
    throw new Error(
      `Could not load ${url}: HTTP ${response.status}`
    );
  }

  return response.json();
}


async function decompressGzip(response) {
  if (!('DecompressionStream' in window)) {
    throw new Error(
      'This browser does not support gzip decompression. ' +
      'Use a current version of Chrome, Edge, Firefox, or Safari.'
    );
  }

  const compressed = response.body.pipeThrough(
    new DecompressionStream('gzip')
  );

  return new Response(compressed).arrayBuffer();
}


async function loadChunk(chunkInfo) {
  if (state.chunkCache.has(chunkInfo.file)) {
    return state.chunkCache.get(chunkInfo.file);
  }

  const loadingPromise = (async () => {
    const url = `${DATA_ROOT}/${chunkInfo.file}`;
    const response = await fetch(url);

    if (!response.ok) {
      throw new Error(
        `Could not load ${url}: HTTP ${response.status}`
      );
    }

    const buffer = await decompressGzip(response);
    const expectedValues = chunkInfo.shape.reduce(
      (product, size) => product * size,
      1
    );
    const expectedBytes = expectedValues * 8;

    if (buffer.byteLength !== expectedBytes) {
      throw new Error(
        `Chunk ${chunkInfo.file} contains ` +
        `${buffer.byteLength} uncompressed bytes; ` +
        `expected ${expectedBytes}.`
      );
    }

    return new Float64Array(buffer);
  })();

  state.chunkCache.set(chunkInfo.file, loadingPromise);

  try {
    return await loadingPromise;
  } catch (error) {
    state.chunkCache.delete(chunkInfo.file);
    throw error;
  }
}


function populateControls() {
  const { axes, manifest } = state;

  axes.temp_eV.forEach((temperature, index) => {
    const option = document.createElement('option');
    option.value = String(index);
    option.textContent =
      `${index}: ${formatScientific(temperature, 5)} eV`;

    elements.temperatureSelect.append(option);
  });

  axes.rho_gcc.forEach((density, index) => {
    const minimumOption = document.createElement('option');
    minimumOption.value = String(index);
    minimumOption.textContent =
      `${index}: ${formatScientific(density, 5)}`;

    const maximumOption = minimumOption.cloneNode(true);

    elements.densityMinSelect.append(minimumOption);
    elements.densityMaxSelect.append(maximumOption);
  });

  elements.densityMinSelect.value = '0';
  elements.densityMaxSelect.value = String(
    Math.min(7, axes.rho_gcc.length - 1)
  );

  elements.groupMinInput.max = String(
    manifest.dimensions.groups - 1
  );
  elements.groupMaxInput.max = String(
    manifest.dimensions.groups - 1
  );
  elements.groupMaxInput.value = String(
    Math.min(127, manifest.dimensions.groups - 1)
  );
}


function getSelection() {
  const temperatureIndex = Number.parseInt(
    elements.temperatureSelect.value,
    10
  );
  const densityMin = Number.parseInt(
    elements.densityMinSelect.value,
    10
  );
  const densityMax = Number.parseInt(
    elements.densityMaxSelect.value,
    10
  );
  const groupMin = Number.parseInt(
    elements.groupMinInput.value,
    10
  );
  const groupMax = Number.parseInt(
    elements.groupMaxInput.value,
    10
  );

  const maxGroup = state.manifest.dimensions.groups - 1;

  if (
    !Number.isInteger(temperatureIndex) ||
    !Number.isInteger(densityMin) ||
    !Number.isInteger(densityMax) ||
    !Number.isInteger(groupMin) ||
    !Number.isInteger(groupMax)
  ) {
    throw new Error('All selections must be valid integers.');
  }

  if (densityMin > densityMax) {
    throw new Error(
      'Minimum density index must not exceed maximum density index.'
    );
  }

  if (groupMin < 0 || groupMax > maxGroup) {
    throw new Error(
      `Energy groups must be between 0 and ${maxGroup}.`
    );
  }

  if (groupMin > groupMax) {
    throw new Error(
      'First energy group must not exceed last energy group.'
    );
  }

  const rowCount =
    (densityMax - densityMin + 1) *
    (groupMax - groupMin + 1);

  if (rowCount > MAX_EXPORT_ROWS) {
    throw new Error(
      `This selection contains ${rowCount.toLocaleString()} rows. ` +
      `The prototype limit is ` +
      `${MAX_EXPORT_ROWS.toLocaleString()} rows.`
    );
  }

  return {
    temperatureIndex,
    densityMin,
    densityMax,
    groupMin,
    groupMax,
    rowCount,
  };
}


function getRequiredChunks(selection) {
  return state.manifest.chunks.filter((chunk) => {
    return (
      chunk.group_stop > selection.groupMin &&
      chunk.group_start <= selection.groupMax
    );
  });
}


function updateSummary() {
  clearError();

  try {
    const selection = getSelection();
    const temperature =
      state.axes.temp_eV[selection.temperatureIndex];

    const densityCount =
      selection.densityMax - selection.densityMin + 1;
    const groupCount =
      selection.groupMax - selection.groupMin + 1;

    const chunks = getRequiredChunks(selection);
    const compressedBytes = chunks.reduce(
      (sum, chunk) => sum + chunk.compressed_bytes,
      0
    );

    elements.temperatureSummary.textContent =
      `${formatScientific(temperature, 5)} eV`;

    elements.densitySummary.textContent =
      `${densityCount.toLocaleString()} ` +
      `(${selection.densityMin}–${selection.densityMax})`;

    elements.groupSummary.textContent =
      `${groupCount.toLocaleString()} ` +
      `(${selection.groupMin}–${selection.groupMax})`;

    elements.transferSummary.textContent =
      `${formatBytes(compressedBytes)} in ${chunks.length} chunk` +
      `${chunks.length === 1 ? '' : 's'}`;
  } catch (error) {
    showError(error.message);
  }
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


function valueAt(
  chunkValues,
  chunkInfo,
  globalGroup,
  densityIndex,
  temperatureIndex
) {
  const localGroup = globalGroup - chunkInfo.group_start;
  const densityCount = chunkInfo.shape[1];
  const temperatureCount = chunkInfo.shape[2];

  if (
    localGroup < 0 ||
    localGroup >= chunkInfo.shape[0]
  ) {
    throw new Error(
      `Group ${globalGroup} is outside chunk ${chunkInfo.file}.`
    );
  }

  const flatIndex =
    (
      localGroup * densityCount +
      densityIndex
    ) * temperatureCount +
    temperatureIndex;

  return chunkValues[flatIndex];
}


async function loadSelection(selection) {
  const requiredChunks = getRequiredChunks(selection);

  const loadedChunks = await Promise.all(
    requiredChunks.map(async (chunkInfo) => ({
      info: chunkInfo,
      values: await loadChunk(chunkInfo),
    }))
  );

  return loadedChunks;
}


function findLoadedChunk(loadedChunks, groupIndex) {
  const chunk = loadedChunks.find(({ info }) => {
    return (
      groupIndex >= info.group_start &&
      groupIndex < info.group_stop
    );
  });

  if (!chunk) {
    throw new Error(
      `No loaded chunk contains energy group ${groupIndex}.`
    );
  }

  return chunk;
}


async function previewSelection() {
  clearError();

  try {
    const selection = getSelection();

    setBusy(true, 'Loading selected chunks…');

    const loadedChunks = await loadSelection(selection);
    const rows = [];
    const temperature =
      state.axes.temp_eV[selection.temperatureIndex];

    outer:
    for (
      let group = selection.groupMin;
      group <= selection.groupMax;
      group += 1
    ) {
      const loadedChunk = findLoadedChunk(
        loadedChunks,
        group
      );

      for (
        let density = selection.densityMin;
        density <= selection.densityMax;
        density += 1
      ) {
        const opacity = valueAt(
          loadedChunk.values,
          loadedChunk.info,
          group,
          density,
          selection.temperatureIndex
        );

        rows.push({
          group,
          energyLow: state.axes.hnu_ev_edges[group],
          energyHigh: state.axes.hnu_ev_edges[group + 1],
          density: state.axes.rho_gcc[density],
          temperature,
          opacity,
        });

        if (rows.length >= PREVIEW_ROW_LIMIT) {
          break outer;
        }
      }
    }

    renderPreview(rows, selection.rowCount);
  } catch (error) {
    showError(error.message);
  } finally {
    setBusy(false);
  }
}


function renderPreview(rows, totalRows) {
  elements.previewBody.replaceChildren();

  const fragment = document.createDocumentFragment();

  for (const row of rows) {
    const tr = document.createElement('tr');

    const values = [
      row.group.toString(),
      formatScientific(row.energyLow),
      formatScientific(row.energyHigh),
      formatScientific(row.density),
      formatScientific(row.temperature),
      formatScientific(row.opacity),
    ];

    for (const value of values) {
      const td = document.createElement('td');
      td.textContent = value;
      tr.append(td);
    }

    fragment.append(tr);
  }

  elements.previewBody.append(fragment);

  elements.previewDescription.textContent =
    `${totalRows.toLocaleString()} values selected.`;

  if (rows.length < totalRows) {
    elements.previewLimit.textContent =
      `First ${rows.length.toLocaleString()} rows shown`;
  } else {
    elements.previewLimit.textContent =
      `${rows.length.toLocaleString()} rows`;
  }

  elements.previewSection.hidden = false;
  elements.previewSection.scrollIntoView({
    behavior: 'smooth',
    block: 'start',
  });
}


function createTextHeader(selection) {
  const temperature =
    state.axes.temp_eV[selection.temperatureIndex];

  return [
    '# GLOW multigroup opacity table',
    '# field: kplanck',
    '# field_label: Planck-mean absorption opacity',
    '# opacity_units: cm^2 g^-1',
    `# temperature_index: ${selection.temperatureIndex}`,
    `# temperature_eV: ${temperature.toExponential(16)}`,
    `# density_index_range: ${selection.densityMin} ${selection.densityMax}`,
    `# group_index_range: ${selection.groupMin} ${selection.groupMax}`,
    '#',
    '# Columns:',
    '# group_index energy_low_eV energy_high_eV ' +
      'density_index density_g_cm-3 opacity_cm2_g-1',
    '',
  ].join('\n');
}


async function downloadSelection() {
  clearError();

  try {
    const selection = getSelection();

    setBusy(true, 'Loading data and constructing TXT file…');

    const loadedChunks = await loadSelection(selection);
    const pieces = [createTextHeader(selection)];
    const lineBatch = [];
    const batchSize = 20_000;

    for (
      let group = selection.groupMin;
      group <= selection.groupMax;
      group += 1
    ) {
      const loadedChunk = findLoadedChunk(
        loadedChunks,
        group
      );

      const energyLow =
        state.axes.hnu_ev_edges[group];
      const energyHigh =
        state.axes.hnu_ev_edges[group + 1];

      for (
        let density = selection.densityMin;
        density <= selection.densityMax;
        density += 1
      ) {
        const opacity = valueAt(
          loadedChunk.values,
          loadedChunk.info,
          group,
          density,
          selection.temperatureIndex
        );

        lineBatch.push(
          [
            group,
            energyLow.toExponential(16),
            energyHigh.toExponential(16),
            density,
            state.axes.rho_gcc[density].toExponential(16),
            opacity.toExponential(16),
          ].join(' ')
        );

        if (lineBatch.length >= batchSize) {
          pieces.push(`${lineBatch.join('\n')}\n`);
          lineBatch.length = 0;
        }
      }
    }

    if (lineBatch.length) {
      pieces.push(`${lineBatch.join('\n')}\n`);
    }

    const blob = new Blob(pieces, {
      type: 'text/plain;charset=utf-8',
    });

    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');

    anchor.href = url;
    anchor.download =
      `GLOW_kplanck_T${selection.temperatureIndex}_` +
      `rho${selection.densityMin}-${selection.densityMax}_` +
      `groups${selection.groupMin}-${selection.groupMax}.txt`;

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


async function initialize() {
  try {
    const [manifest, axes] = await Promise.all([
      fetchJson(MANIFEST_URL),
      fetchJson(AXES_URL),
    ]);

    state.manifest = manifest;
    state.axes = axes;

    if (
      manifest.storage.dtype !== 'float64' ||
      manifest.storage.byte_order !== 'little-endian'
    ) {
      throw new Error(
        'Unsupported prototype binary representation.'
      );
    }

    if (
      axes.hnu_ev_centers.length !==
      manifest.dimensions.groups
    ) {
      throw new Error(
        'Energy-axis length disagrees with the manifest.'
      );
    }

    if (
      axes.rho_gcc.length !==
      manifest.dimensions.densities
    ) {
      throw new Error(
        'Density-axis length disagrees with the manifest.'
      );
    }

    if (
      axes.temp_eV.length !==
      manifest.dimensions.temperatures
    ) {
      throw new Error(
        'Temperature-axis length disagrees with the manifest.'
      );
    }

    populateControls();

    elements.form.hidden = false;
    elements.loadingMessage.hidden = true;

    updateSummary();
  } catch (error) {
    elements.loadingMessage.textContent =
      `Dataset initialization failed: ${error.message}`;
    elements.loadingMessage.classList.add('error');
  }
}


[
  elements.temperatureSelect,
  elements.densityMinSelect,
  elements.densityMaxSelect,
  elements.groupMinInput,
  elements.groupMaxInput,
].forEach((control) => {
  control.addEventListener('input', updateSummary);
  control.addEventListener('change', updateSummary);
});

elements.previewButton.addEventListener(
  'click',
  previewSelection
);

elements.downloadButton.addEventListener(
  'click',
  downloadSelection
);

initialize();
