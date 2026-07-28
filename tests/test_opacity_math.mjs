import assert from 'node:assert/strict';
import {
  COLLAPSE_KIND,
  applyCollapsePlan,
  buildCollapsePlan,
  findLogBracket,
  integratePlanckWeight,
  integrateRosselandWeight,
  interpolateOpacityLogLog,
  makeLogEdges,
  parsePositiveList,
  parseStrictlyIncreasingEdges,
  requiredFieldsForCollapse,
} from '../opacity_math.mjs';

function close(actual, expected, rtol = 2e-12, atol = 0) {
  const error = Math.abs(actual - expected);
  const tolerance = atol + rtol * Math.abs(expected);
  assert.ok(error <= tolerance, `actual=${actual}, expected=${expected}, error=${error}, tolerance=${tolerance}`);
}

assert.deepEqual(parsePositiveList('1, 2\n3; 2', 'values'), [1, 2, 3]);
assert.deepEqual(parseStrictlyIncreasingEdges('0.1 1 10'), [0.1, 1, 10]);
assert.throws(() => parseStrictlyIncreasingEdges('1 1 2'), /strictly increasing/);

const logEdges = makeLogEdges(1, 1000, 3);
close(logEdges[0], 1);
close(logEdges[1], 10);
close(logEdges[2], 100);
close(logEdges[3], 1000);

const axis = [1, 10, 100];
assert.deepEqual(findLogBracket(axis, 10), {
  lowerIndex: 1,
  upperIndex: 1,
  fraction: 0,
  exact: true,
});
const bracket = findLogBracket(axis, Math.sqrt(10));
assert.equal(bracket.lowerIndex, 0);
assert.equal(bracket.upperIndex, 1);
close(bracket.fraction, 0.5);
assert.throws(() => findLogBracket(axis, 0.5), /below/);

const tempAxis = [2, 8];
const rhoAxis = [1e-12, 1e-8];
const requestedT = 4;
const requestedRho = 1e-10;
const tBracket = findLogBracket(tempAxis, requestedT);
const rhoBracket = findLogBracket(rhoAxis, requestedRho);
const powerLaw = (t, rho) => t ** 1.7 * rho ** -0.3;
const interpolated = interpolateOpacityLogLog(
  (ti, ri) => powerLaw(tempAxis[ti], rhoAxis[ri]),
  tBracket,
  rhoBracket,
);
assert.equal(interpolated.status, 'ok');
close(interpolated.value, powerLaw(requestedT, requestedRho), 5e-13);

const exactZero = interpolateOpacityLogLog(() => 0, {
  lowerIndex: 0, upperIndex: 0, fraction: 0, exact: true,
}, {
  lowerIndex: 0, upperIndex: 0, fraction: 0, exact: true,
});
assert.equal(exactZero.value, 0);
assert.equal(exactZero.status, 'ok_zero');

const mixedZero = interpolateOpacityLogLog(
  (ti) => (ti === 0 ? 0 : 1),
  { lowerIndex: 0, upperIndex: 1, fraction: 0.5, exact: false },
  { lowerIndex: 0, upperIndex: 0, fraction: 0, exact: true },
);
assert.ok(Number.isNaN(mixedZero.value));
assert.equal(mixedZero.status, 'nonpositive_interpolation_stencil');

assert.ok(integratePlanckWeight(1, 2, 1) > 0);
assert.ok(integrateRosselandWeight(1, 2, 1) > 0);
assert.equal(COLLAPSE_KIND.kplanck, 'planck');
assert.equal(COLLAPSE_KIND.krosseland, 'rosseland_harmonic');
assert.equal(COLLAPSE_KIND.krosseland_absorption, 'rosseland_absorption');
assert.deepEqual(requiredFieldsForCollapse('krosseland_absorption'), [
  'krosseland_absorption', 'krosseland',
]);
assert.deepEqual(requiredFieldsForCollapse('kross_scattering'), [
  'kross_scattering',
]);

const nativeEdges = [1, 2, 4];
const nativeOpacity = [3, 7];
for (const kind of ['planck', 'rosseland_harmonic']) {
  const firstPlan = buildCollapsePlan(kind, nativeEdges, [1, 2], 1.5);
  const first = applyCollapsePlan(firstPlan, nativeOpacity);
  close(first[0].value, 3);
  const secondPlan = buildCollapsePlan(kind, nativeEdges, [2, 4], 1.5);
  const second = applyCollapsePlan(secondPlan, nativeOpacity);
  close(second[0].value, 7);
}

// Associativity when all intermediate boundaries align with native boundaries.
const fineEdges = makeLogEdges(0.1, 100, 64);
const fineOpacity = Array.from({ length: 64 }, (_, i) => 0.5 + (i + 1) ** 1.2);
const mediumEdges = fineEdges.filter((_, i) => i % 8 === 0);
const coarseEdges = [fineEdges[0], fineEdges[32], fineEdges[64]];
for (const kind of ['planck', 'rosseland_harmonic']) {
  const direct = applyCollapsePlan(
    buildCollapsePlan(kind, fineEdges, coarseEdges, 3.7),
    fineOpacity,
  ).map((item) => item.value);
  const medium = applyCollapsePlan(
    buildCollapsePlan(kind, fineEdges, mediumEdges, 3.7),
    fineOpacity,
  ).map((item) => item.value);
  const staged = applyCollapsePlan(
    buildCollapsePlan(kind, mediumEdges, coarseEdges, 3.7),
    medium,
  ).map((item) => item.value);
  close(staged[0], direct[0], 2e-11);
  close(staged[1], direct[1], 2e-11);
}

const rossZero = applyCollapsePlan(
  buildCollapsePlan('rosseland_harmonic', [1, 2, 4], [1, 4], 1),
  [2, 0],
);
assert.equal(rossZero[0].value, 0);
assert.equal(rossZero[0].status, 'ok_zero');

console.log('All opacity math tests passed.');


// Scattering is an independent harmonic Rosseland field.
const scatteringPlan = buildCollapsePlan(
  'rosseland_harmonic',
  [1, 2, 4],
  [1, 4],
  1.5,
);
const scatteringValues = [2, 8];
const scatteringWeights = scatteringPlan.bins[0].terms.map((term) => term.weight);
const expectedScattering =
  scatteringWeights.reduce((sum, weight) => sum + weight, 0) /
  (
    scatteringWeights[0] / scatteringValues[0] +
    scatteringWeights[1] / scatteringValues[1]
  );
const collapsedScattering = applyCollapsePlan(
  scatteringPlan,
  scatteringValues,
);
close(collapsedScattering[0].value, expectedScattering, 2e-12);

// Rosseland absorption uses the original flux-weighted form,
// with total Rosseland opacity as the transport denominator.
const absorptionPlan = buildCollapsePlan(
  'rosseland_absorption',
  [1, 2, 4],
  [1, 4],
  1.5,
);
const absorptionValues = [1, 6];
const totalValues = [4, 12];
const absorptionWeights = absorptionPlan.bins[0].terms.map((term) => term.weight);
const expectedAbsorption =
  (
    absorptionWeights[0] * absorptionValues[0] / totalValues[0] +
    absorptionWeights[1] * absorptionValues[1] / totalValues[1]
  ) /
  (
    absorptionWeights[0] / totalValues[0] +
    absorptionWeights[1] / totalValues[1]
  );
const collapsedAbsorption = applyCollapsePlan(
  absorptionPlan,
  absorptionValues,
  null,
  { totalOpacity: totalValues },
);
close(collapsedAbsorption[0].value, expectedAbsorption, 2e-12);

console.log('Corrected Rosseland field tests passed.');
