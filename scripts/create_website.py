#!/usr/bin/env python3

from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parent.parent

INDEX_PATH = REPO_ROOT / "index.html"
STYLE_PATH = REPO_ROOT / "style.css"
APP_PATH = REPO_ROOT / "app.js"


INDEX_HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta
    name="viewport"
    content="width=device-width, initial-scale=1"
  >
  <meta
    name="description"
    content="Explore and download GLOW multigroup opacity tables."
  >
  <title>GLOW Opacity Tables</title>
  <link rel="stylesheet" href="style.css">
</head>

<body>
  <header class="site-header">
    <div class="header-content">
      <div>
        <p class="eyebrow">Public astrophysical opacity tables</p>
        <h1>GLOW</h1>
        <p class="subtitle">
          Explore and download multigroup opacities for
          low-density astrophysical plasmas.
        </p>
      </div>

      <div class="dataset-badge">
        <span>Prototype dataset</span>
        <strong>Solar composition</strong>
      </div>
    </div>
  </header>

  <main>
    <section class="card introduction">
      <h2>Planck-mean absorption opacity</h2>
      <p>
        This prototype provides the first temperature block of the
        GLOW solar-composition dataset. Select a temperature, density
        range, and photon-energy group range. Only the required data
        chunks will be downloaded.
      </p>
    </section>

    <section class="card">
      <h2>Table selection</h2>

      <div id="loading-message" class="status">
        Loading dataset metadata…
      </div>

      <form id="selection-form" hidden>
        <div class="form-grid">
          <label>
            Opacity
            <select id="field-select" disabled>
              <option>Planck-mean absorption opacity</option>
            </select>
          </label>

          <label>
            Temperature
            <select id="temperature-select"></select>
          </label>

          <label>
            Minimum density
            <select id="density-min-select"></select>
          </label>

          <label>
            Maximum density
            <select id="density-max-select"></select>
          </label>

          <label>
            First energy group
            <input
              id="group-min-input"
              type="number"
              min="0"
              step="1"
              value="0"
              required
            >
          </label>

          <label>
            Last energy group
            <input
              id="group-max-input"
              type="number"
              min="0"
              step="1"
              value="127"
              required
            >
          </label>
        </div>

        <div class="summary-panel">
          <dl>
            <div>
              <dt>Temperature</dt>
              <dd id="temperature-summary">—</dd>
            </div>

            <div>
              <dt>Density points</dt>
              <dd id="density-summary">—</dd>
            </div>

            <div>
              <dt>Energy groups</dt>
              <dd id="group-summary">—</dd>
            </div>

            <div>
              <dt>Estimated transfer</dt>
              <dd id="transfer-summary">—</dd>
            </div>
          </dl>
        </div>

        <div id="form-error" class="error" hidden></div>

        <div class="button-row">
          <button id="preview-button" type="button">
            Load preview
          </button>

          <button
            id="download-button"
            type="button"
            class="secondary"
          >
            Download TXT
          </button>
        </div>
      </form>
    </section>

    <section id="preview-section" class="card" hidden>
      <div class="section-heading">
        <div>
          <h2>Preview</h2>
          <p id="preview-description"></p>
        </div>

        <span id="preview-limit" class="small-badge"></span>
      </div>

      <div class="table-wrapper">
        <table>
          <thead>
            <tr>
              <th>Group</th>
              <th>Energy lower edge [eV]</th>
              <th>Energy upper edge [eV]</th>
              <th>Density [g cm⁻³]</th>
              <th>Temperature [eV]</th>
              <th>Opacity [cm² g⁻¹]</th>
            </tr>
          </thead>

          <tbody id="preview-body"></tbody>
        </table>
      </div>
    </section>

    <section class="card notes">
      <h2>Data layout</h2>
      <p>
        Stored arrays use the axis order
        <code>group, density, temperature</code>.
        Browser chunks are gzip-compressed little-endian
        <code>float64</code> arrays.
      </p>
    </section>
  </main>

  <footer>
    <p>
      GLOW — A Public Library of Multigroup Opacities Extending to
      Low-Density Astrophysical Plasmas
    </p>
  </footer>

  <script src="app.js" defer></script>
</body>
</html>
"""


STYLE_CSS = r""":root {
  color-scheme: light;
  --background: #f4f7fb;
  --surface: #ffffff;
  --surface-alt: #edf3fa;
  --text: #172033;
  --muted: #5c687d;
  --border: #d7dfeb;
  --accent: #2457d6;
  --accent-hover: #173fa8;
  --danger: #a21d2f;
  --shadow: 0 12px 36px rgba(25, 42, 70, 0.08);
}

* {
  box-sizing: border-box;
}

body {
  margin: 0;
  background: var(--background);
  color: var(--text);
  font-family:
    Inter, ui-sans-serif, system-ui, -apple-system,
    BlinkMacSystemFont, "Segoe UI", sans-serif;
  line-height: 1.5;
}

.site-header {
  background:
    radial-gradient(
      circle at top right,
      rgba(97, 148, 255, 0.45),
      transparent 40%
    ),
    linear-gradient(135deg, #102753, #204fb4);
  color: white;
  padding: 4rem 1.5rem;
}

.header-content {
  width: min(1100px, 100%);
  margin: 0 auto;
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 2rem;
}

.eyebrow {
  margin: 0 0 0.4rem;
  font-size: 0.8rem;
  font-weight: 700;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  opacity: 0.8;
}

h1 {
  margin: 0;
  font-size: clamp(3.5rem, 10vw, 7rem);
  line-height: 0.95;
  letter-spacing: -0.06em;
}

.subtitle {
  max-width: 680px;
  margin: 1.25rem 0 0;
  font-size: clamp(1rem, 2vw, 1.25rem);
  opacity: 0.9;
}

.dataset-badge {
  min-width: 190px;
  padding: 1rem 1.2rem;
  border: 1px solid rgba(255, 255, 255, 0.28);
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.1);
  backdrop-filter: blur(10px);
}

.dataset-badge span,
.dataset-badge strong {
  display: block;
}

.dataset-badge span {
  font-size: 0.75rem;
  opacity: 0.75;
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

main {
  width: min(1100px, calc(100% - 2rem));
  margin: -2rem auto 4rem;
}

.card {
  margin-bottom: 1.25rem;
  padding: clamp(1.25rem, 3vw, 2rem);
  border: 1px solid var(--border);
  border-radius: 18px;
  background: var(--surface);
  box-shadow: var(--shadow);
}

.card h2 {
  margin-top: 0;
}

.introduction {
  border-top: 4px solid var(--accent);
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 1rem;
}

label {
  display: grid;
  gap: 0.45rem;
  color: var(--muted);
  font-size: 0.86rem;
  font-weight: 650;
}

select,
input,
button {
  min-height: 44px;
  border-radius: 9px;
  font: inherit;
}

select,
input {
  width: 100%;
  padding: 0.65rem 0.75rem;
  border: 1px solid var(--border);
  background: white;
  color: var(--text);
}

select:focus,
input:focus,
button:focus-visible {
  outline: 3px solid rgba(36, 87, 214, 0.2);
  outline-offset: 1px;
}

.summary-panel {
  margin: 1.5rem 0;
  padding: 1rem;
  border-radius: 12px;
  background: var(--surface-alt);
}

.summary-panel dl {
  margin: 0;
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 1rem;
}

.summary-panel dl div {
  min-width: 0;
}

.summary-panel dt {
  color: var(--muted);
  font-size: 0.75rem;
  font-weight: 700;
  text-transform: uppercase;
}

.summary-panel dd {
  margin: 0.25rem 0 0;
  font-variant-numeric: tabular-nums;
  overflow-wrap: anywhere;
}

.button-row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem;
}

button {
  padding: 0.7rem 1.1rem;
  border: 1px solid var(--accent);
  background: var(--accent);
  color: white;
  cursor: pointer;
  font-weight: 700;
}

button:hover:not(:disabled) {
  background: var(--accent-hover);
}

button.secondary {
  background: white;
  color: var(--accent);
}

button:disabled {
  cursor: wait;
  opacity: 0.55;
}

.status,
.error {
  padding: 0.9rem 1rem;
  border-radius: 10px;
}

.status {
  background: var(--surface-alt);
  color: var(--muted);
}

.error {
  margin-bottom: 1rem;
  background: #fff0f2;
  color: var(--danger);
}

.section-heading {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
}

.section-heading p {
  color: var(--muted);
}

.small-badge {
  align-self: flex-start;
  white-space: nowrap;
  padding: 0.3rem 0.55rem;
  border-radius: 999px;
  background: var(--surface-alt);
  color: var(--muted);
  font-size: 0.75rem;
}

.table-wrapper {
  overflow: auto;
  max-height: 520px;
  border: 1px solid var(--border);
  border-radius: 10px;
}

table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.84rem;
  font-variant-numeric: tabular-nums;
}

th,
td {
  padding: 0.65rem 0.75rem;
  border-bottom: 1px solid var(--border);
  text-align: right;
  white-space: nowrap;
}

th {
  position: sticky;
  top: 0;
  z-index: 1;
  background: var(--surface-alt);
  color: var(--muted);
}

td:first-child,
th:first-child {
  text-align: left;
}

code {
  padding: 0.1rem 0.3rem;
  border-radius: 4px;
  background: var(--surface-alt);
}

.notes {
  color: var(--muted);
}

footer {
  padding: 2rem 1rem 3rem;
  color: var(--muted);
  text-align: center;
  font-size: 0.85rem;
}

@media (max-width: 800px) {
  .header-content {
    align-items: flex-start;
    flex-direction: column;
  }

  .form-grid {
    grid-template-columns: 1fr 1fr;
  }

  .summary-panel dl {
    grid-template-columns: 1fr 1fr;
  }
}

@media (max-width: 520px) {
  .form-grid,
  .summary-panel dl {
    grid-template-columns: 1fr;
  }

  .button-row button {
    width: 100%;
  }
}
"""


APP_JS = r"""'use strict';

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
"""


def write_file(path: Path, content: str) -> None:
    if path.exists():
        backup_path = path.with_suffix(path.suffix + ".backup")

        if backup_path.exists():
            raise FileExistsError(
                f"Refusing to overwrite existing backup: "
                f"{backup_path}"
            )

        path.replace(backup_path)
        print(f"Backed up {path.name} to {backup_path.name}")

    path.write_text(content, encoding="utf-8")
    print(f"Wrote {path.relative_to(REPO_ROOT)}")


def main() -> None:
    prototype_manifest = (
        REPO_ROOT
        / "solar_final"
        / "web_data_prototype"
        / "manifest.json"
    )
    prototype_axes = (
        REPO_ROOT
        / "solar_final"
        / "web_data_prototype"
        / "axes.json"
    )

    missing = [
        path
        for path in (prototype_manifest, prototype_axes)
        if not path.is_file()
    ]

    if missing:
        formatted = "\n".join(
            f"  - {path.relative_to(REPO_ROOT)}"
            for path in missing
        )

        raise FileNotFoundError(
            "The browser prototype data are missing:\n"
            f"{formatted}\n"
            "Run scripts/prepare_web_prototype.py first."
        )

    write_file(INDEX_PATH, INDEX_HTML)
    write_file(STYLE_PATH, STYLE_CSS)
    write_file(APP_PATH, APP_JS)

    print()
    print("Website files created successfully.")
    print()
    print("Start a local server with:")
    print("  python -m http.server 8000")
    print()
    print("Then open:")
    print("  http://localhost:8000/")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        sys.exit(1)