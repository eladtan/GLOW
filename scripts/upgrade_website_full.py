#!/usr/bin/env python3

from pathlib import Path
import shutil
import sys


REPO_ROOT = Path(__file__).resolve().parent.parent
INDEX_PATH = REPO_ROOT / "index.html"
APP_PATH = REPO_ROOT / "app.js"


APP_JS = r"""'use strict';

const DATA_ROOT = 'solar_final/web_data';
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
  fieldSelect: document.querySelector('#field-select'),
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

  const stream = response.body.pipeThrough(
    new DecompressionStream('gzip')
  );

  return new Response(stream).arrayBuffer();
}


async function loadChunk(chunkInfo) {
  if (state.chunkCache.has(chunkInfo.file)) {
    return state.chunkCache.get(chunkInfo.file);
  }

  const promise = (async () => {
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
        `${chunkInfo.file} has ${buffer.byteLength} bytes; ` +
        `expected ${expectedBytes}.`
      );
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
  const part = state.manifest.parts.find((candidate) => {
    return (
      globalTemperatureIndex >=
        candidate.temperature_global_start &&
      globalTemperatureIndex <
        candidate.temperature_global_stop
    );
  });

  if (!part) {
    throw new Error(
      `No temperature part contains index ` +
      `${globalTemperatureIndex}.`
    );
  }

  return {
    part,
    localTemperatureIndex:
      globalTemperatureIndex -
      part.temperature_global_start,
  };
}


function populateControls() {
  const { axes, manifest } = state;

  elements.fieldSelect.replaceChildren();

  for (
    const [fieldName, metadata]
    of Object.entries(manifest.field_metadata)
  ) {
    const option = document.createElement('option');

    option.value = fieldName;
    option.textContent = metadata.label;

    elements.fieldSelect.append(option);
  }

  elements.fieldSelect.disabled = false;

  axes.temp_eV.forEach((temperature, index) => {
    const part = findTemperaturePart(index).part;

    const option = document.createElement('option');

    option.value = String(index);
    option.textContent =
      `${index}: ${formatScientific(temperature, 5)} eV ` +
      `(part ${part.part_index})`;

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

  elements.fieldSelect.value = 'kplanck';
  elements.temperatureSelect.value = '0';
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

  elements.groupMinInput.value = '0';

  elements.groupMaxInput.value = String(
    Math.min(127, manifest.dimensions.groups - 1)
  );
}


function getSelection() {
  const field = elements.fieldSelect.value;

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

  if (!(field in state.manifest.field_metadata)) {
    throw new Error(`Unknown opacity field: ${field}`);
  }

  if (
    !Number.isInteger(temperatureIndex) ||
    !Number.isInteger(densityMin) ||
    !Number.isInteger(densityMax) ||
    !Number.isInteger(groupMin) ||
    !Number.isInteger(groupMax)
  ) {
    throw new Error('All selections must be valid.');
  }

  if (
    temperatureIndex < 0 ||
    temperatureIndex >= state.axes.temp_eV.length
  ) {
    throw new Error('Temperature index is outside the table.');
  }

  if (
    densityMin < 0 ||
    densityMax >= state.axes.rho_gcc.length
  ) {
    throw new Error('Density index is outside the table.');
  }

  if (densityMin > densityMax) {
    throw new Error(
      'Minimum density must not exceed maximum density.'
    );
  }

  const maximumGroup =
    state.manifest.dimensions.groups - 1;

  if (groupMin < 0 || groupMax > maximumGroup) {
    throw new Error(
      `Energy groups must be between 0 and ${maximumGroup}.`
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
      `The selection contains ${rowCount.toLocaleString()} ` +
      `rows. The current limit is ` +
      `${MAX_EXPORT_ROWS.toLocaleString()} rows.`
    );
  }

  const {
    part,
    localTemperatureIndex,
  } = findTemperaturePart(temperatureIndex);

  return {
    field,
    temperatureIndex,
    localTemperatureIndex,
    part,
    densityMin,
    densityMax,
    groupMin,
    groupMax,
    rowCount,
  };
}


function getRequiredChunks(selection) {
  return selection.part.chunks.filter((chunk) => {
    return (
      chunk.field === selection.field &&
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
      `${formatScientific(temperature, 5)} eV, ` +
      `part ${selection.part.part_index}`;

    elements.densitySummary.textContent =
      `${densityCount.toLocaleString()} ` +
      `(${selection.densityMin}–${selection.densityMax})`;

    elements.groupSummary.textContent =
      `${groupCount.toLocaleString()} ` +
      `(${selection.groupMin}–${selection.groupMax})`;

    elements.transferSummary.textContent =
      `${formatBytes(compressedBytes)} in ` +
      `${chunks.length} chunk` +
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
  localTemperatureIndex
) {
  const localGroup =
    globalGroup - chunkInfo.group_start;

  const densityCount = chunkInfo.shape[1];
  const temperatureCount = chunkInfo.shape[2];

  if (
    localGroup < 0 ||
    localGroup >= chunkInfo.shape[0]
  ) {
    throw new Error(
      `Group ${globalGroup} is outside ` +
      `${chunkInfo.file}.`
    );
  }

  if (
    localTemperatureIndex < 0 ||
    localTemperatureIndex >= temperatureCount
  ) {
    throw new Error(
      `Local temperature index ` +
      `${localTemperatureIndex} is invalid for ` +
      `${chunkInfo.file}.`
    );
  }

  const flatIndex =
    (
      localGroup * densityCount +
      densityIndex
    ) * temperatureCount +
    localTemperatureIndex;

  return chunkValues[flatIndex];
}


async function loadSelection(selection) {
  const requiredChunks = getRequiredChunks(selection);

  if (requiredChunks.length === 0) {
    throw new Error(
      'No data chunks match this selection.'
    );
  }

  return Promise.all(
    requiredChunks.map(async (chunkInfo) => ({
      info: chunkInfo,
      values: await loadChunk(chunkInfo),
    }))
  );
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
      `No loaded chunk contains group ${groupIndex}.`
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
          selection.localTemperatureIndex
        );

        rows.push({
          group,
          energyLow: state.axes.hnu_ev_edges[group],
          energyHigh:
            state.axes.hnu_ev_edges[group + 1],
          density: state.axes.rho_gcc[density],
          temperature,
          opacity,
        });

        if (rows.length >= PREVIEW_ROW_LIMIT) {
          break outer;
        }
      }
    }

    renderPreview(rows, selection);
  } catch (error) {
    showError(error.message);
  } finally {
    setBusy(false);
  }
}


function renderPreview(rows, selection) {
  elements.previewBody.replaceChildren();

  const fragment = document.createDocumentFragment();

  for (const row of rows) {
    const tableRow = document.createElement('tr');

    const values = [
      row.group.toString(),
      formatScientific(row.energyLow),
      formatScientific(row.energyHigh),
      formatScientific(row.density),
      formatScientific(row.temperature),
      formatScientific(row.opacity),
    ];

    for (const value of values) {
      const cell = document.createElement('td');
      cell.textContent = value;
      tableRow.append(cell);
    }

    fragment.append(tableRow);
  }

  elements.previewBody.append(fragment);

  const label =
    state.manifest.field_metadata[
      selection.field
    ].label;

  elements.previewDescription.textContent =
    `${label}: ${selection.rowCount.toLocaleString()} ` +
    `values selected.`;

  if (rows.length < selection.rowCount) {
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

  const metadata =
    state.manifest.field_metadata[selection.field];

  return [
    '# GLOW multigroup opacity table',
    `# field: ${selection.field}`,
    `# field_label: ${metadata.label}`,
    `# opacity_units: ${metadata.units}`,
    `# temperature_global_index: ` +
      `${selection.temperatureIndex}`,
    `# temperature_part: ` +
      `${selection.part.part_index}`,
    `# temperature_local_index: ` +
      `${selection.localTemperatureIndex}`,
    `# temperature_eV: ${temperature.toExponential(16)}`,
    `# density_index_range: ` +
      `${selection.densityMin} ${selection.densityMax}`,
    `# group_index_range: ` +
      `${selection.groupMin} ${selection.groupMax}`,
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

    setBusy(
      true,
      'Loading data and constructing TXT file…'
    );

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
          selection.localTemperatureIndex
        );

        lineBatch.push(
          [
            group,
            energyLow.toExponential(16),
            energyHigh.toExponential(16),
            density,
            state.axes.rho_gcc[
              density
            ].toExponential(16),
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
      `GLOW_${selection.field}_` +
      `T${selection.temperatureIndex}_` +
      `rho${selection.densityMin}-` +
      `${selection.densityMax}_` +
      `groups${selection.groupMin}-` +
      `${selection.groupMax}.txt`;

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

    if (manifest.prototype !== false) {
      throw new Error(
        'The loaded manifest is not the full dataset.'
      );
    }

    if (
      manifest.storage.dtype !== 'float64' ||
      manifest.storage.byte_order !== 'little-endian'
    ) {
      throw new Error(
        'Unsupported binary data representation.'
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
  elements.fieldSelect,
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
"""


def patch_index(content: str) -> str:
    replacements = [
        (
            "<span>Prototype dataset</span>",
            "<span>Full dataset</span>",
        ),
        (
            """This prototype provides the first temperature block of the
        GLOW solar-composition dataset. Select a temperature, density
        range, and photon-energy group range. Only the required data
        chunks will be downloaded.""",
            """Explore the full GLOW solar-composition multigroup-opacity
        dataset. Select an opacity definition, temperature, density
        range, and photon-energy group range. Only the required data
        chunks will be downloaded.""",
        ),
        (
            """<select id="field-select" disabled>
              <option>Planck-mean absorption opacity</option>
            </select>""",
            """<select id="field-select"></select>""",
        ),
        (
            "<h2>Planck-mean absorption opacity</h2>",
            "<h2>Solar-composition multigroup opacities</h2>",
        ),
    ]

    for old, new in replacements:
        if old not in content:
            raise ValueError(
                "Could not find expected index.html text:\n"
                f"{old}"
            )

        content = content.replace(old, new, 1)

    return content


def backup(path: Path) -> Path:
    backup_path = path.with_suffix(
        path.suffix + ".prototype"
    )

    if backup_path.exists():
        raise FileExistsError(
            f"Backup already exists: {backup_path}"
        )

    shutil.copy2(path, backup_path)
    return backup_path


def main() -> None:
    required = [
        INDEX_PATH,
        APP_PATH,
        REPO_ROOT
        / "solar_final"
        / "web_data"
        / "manifest.json",
        REPO_ROOT
        / "solar_final"
        / "web_data"
        / "axes.json",
    ]

    missing = [
        path for path in required
        if not path.is_file()
    ]

    if missing:
        raise FileNotFoundError(
            "Missing required files:\n"
            + "\n".join(str(path) for path in missing)
        )

    index_backup = backup(INDEX_PATH)
    app_backup = backup(APP_PATH)

    print(
        f"Backed up {INDEX_PATH.name} to "
        f"{index_backup.name}"
    )
    print(
        f"Backed up {APP_PATH.name} to "
        f"{app_backup.name}"
    )

    current_index = INDEX_PATH.read_text(
        encoding="utf-8"
    )

    INDEX_PATH.write_text(
        patch_index(current_index),
        encoding="utf-8",
    )

    APP_PATH.write_text(
        APP_JS,
        encoding="utf-8",
    )

    print("Updated index.html")
    print("Updated app.js")
    print()
    print("The website now uses solar_final/web_data.")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        sys.exit(1)