import assert from 'node:assert/strict';
import {
  groupSpectrumChunks,
  isDrawablePoint,
  loadPlotPoints,
  makeSpectrumPlotPoints,
  preparePlotDomain,
  processSpectrumChunksSequentially,
} from '../plot_math.mjs';

const points = [
  { x: 1, y: 0 },
  { x: 10, y: 2 },
  { x: 100, y: 20 },
  { x: 1000, y: Number.NaN },
];

assert.equal(isDrawablePoint(points[0], true, true), false);
assert.equal(isDrawablePoint(points[0], true, false), true);

const logDomain = preparePlotDomain(points, true, true);
assert.equal(logDomain.drawable.length, 2);
assert.equal(logDomain.yMin, 2);
assert.equal(logDomain.yMax, 20);

const linearDomain = preparePlotDomain(points, true, false);
assert.equal(linearDomain.drawable.length, 3);
assert.equal(linearDomain.yMin, 0);
assert.ok(linearDomain.yMax > 20);

const allZero = preparePlotDomain([
  { x: 1, y: 0 },
  { x: 10, y: 0 },
], true, false);
assert.equal(allZero.drawable.length, 2);
assert.equal(allZero.yMin, 0);
assert.equal(allZero.yMax, 1);

assert.throws(
  () => preparePlotDomain([{ x: 1, y: 0 }], true, true),
  /no positive finite opacity/i,
);

const chunks = [
  { file: 'part0-g0', group_start: 0, group_stop: 64 },
  { file: 'part1-g0', group_start: 0, group_stop: 64 },
  { file: 'part0-g1', group_start: 64, group_stop: 128 },
];
assert.deepEqual(
  groupSpectrumChunks(chunks).map((batch) => batch.map((chunk) => chunk.file)),
  [['part0-g0', 'part1-g0'], ['part0-g1']],
);

let activeLoads = 0;
let maximumActiveLoads = 0;
const visitedBatches = [];
await processSpectrumChunksSequentially(
  chunks,
  async (chunk) => {
    activeLoads += 1;
    maximumActiveLoads = Math.max(maximumActiveLoads, activeLoads);
    await new Promise((resolve) => setImmediate(resolve));
    activeLoads -= 1;
    return chunk.file;
  },
  (loaded, batchIndex, batchCount) => {
    visitedBatches.push({
      files: loaded.map(({ values }) => values),
      batchIndex,
      batchCount,
    });
  },
);
assert.equal(maximumActiveLoads, 2);
assert.deepEqual(visitedBatches, [
  { files: ['part0-g0', 'part1-g0'], batchIndex: 0, batchCount: 2 },
  { files: ['part0-g1'], batchIndex: 1, batchCount: 2 },
]);

const spectrumPoints = makeSpectrumPlotPoints(
  { values: [4, 9], statuses: ['exact', 'interpolated'] },
  [1, 4, 16],
  'Hz',
  10,
);
assert.deepEqual(spectrumPoints, [
  { x: 20, y: 4, status: 'exact', group: 0, energyLow: 1, energyHigh: 4 },
  { x: 80, y: 9, status: 'interpolated', group: 1, energyLow: 4, energyHigh: 16 },
]);

const dispatched = [];
const dispatchedPoints = await loadPlotPoints(
  { sweep: 'frequency', energyMode: 'spectrum' },
  {
    spectrum: async () => {
      dispatched.push('spectrum');
      return spectrumPoints;
    },
    integrated: async () => {
      throw new Error('Frequency plots must not use the integrated loader.');
    },
    specificGroup: async () => {
      throw new Error('Frequency plots must not use the specific-group loader.');
    },
  },
);
assert.deepEqual(dispatched, ['spectrum']);
assert.equal(dispatchedPoints[0].energyLow, 1);
assert.equal(dispatchedPoints[0].energyHigh, 4);

console.log('Line-plot scale tests passed.');
