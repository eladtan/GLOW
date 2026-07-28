import assert from 'node:assert/strict';
import { isDrawablePoint, preparePlotDomain } from '../plot_math.mjs';

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

console.log('Line-plot scale tests passed.');
