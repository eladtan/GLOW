import assert from 'node:assert/strict';
import {
  COLLAPSE_KIND,
  applyCollapsePlan,
  buildCollapsePlan,
} from '../opacity_math.mjs';

assert.equal(COLLAPSE_KIND.kplanck, 'planck');
assert.equal(COLLAPSE_KIND.kplanck_scattering, 'planck');
assert.equal(COLLAPSE_KIND.krosseland, 'rosseland_harmonic');
assert.ok(!('kross_scattering' in COLLAPSE_KIND));

const edges = [1, 2, 4];
const plan = buildCollapsePlan(
  COLLAPSE_KIND.kplanck_scattering,
  edges,
  [1, 4],
  1,
);
const result = applyCollapsePlan(plan, [0, 2]);
assert.equal(result.length, 1);
assert.equal(result[0].status, 'ok');
assert.ok(result[0].value > 0);
assert.ok(result[0].value < 2);

const zeroResult = applyCollapsePlan(plan, [0, 0]);
assert.equal(zeroResult[0].value, 0);
assert.equal(zeroResult[0].status, 'ok_zero');

console.log('Planck-scattering opacity-math tests passed.');
