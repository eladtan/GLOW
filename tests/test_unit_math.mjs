import assert from 'node:assert/strict';
import {
  HZ_PER_EV,
  KELVIN_PER_EV,
  spectralCoordinateFromEV,
  spectralUnitLabel,
  temperatureFromEV,
  temperatureToEV,
  temperatureUnitLabel,
} from '../unit_math.mjs';

assert.equal(temperatureFromEV(1, 'eV'), 1);
assert.equal(temperatureFromEV(1, 'K'), KELVIN_PER_EV);
assert.ok(Math.abs(temperatureToEV(KELVIN_PER_EV, 'K') - 1) < 1e-14);
assert.equal(spectralCoordinateFromEV(1, 'eV'), 1);
assert.equal(spectralCoordinateFromEV(1, 'Hz'), HZ_PER_EV);
assert.equal(temperatureUnitLabel('eV'), 'eV');
assert.equal(temperatureUnitLabel('K'), 'K');
assert.match(spectralUnitLabel('eV'), /eV/);
assert.match(spectralUnitLabel('Hz'), /Hz/);
assert.throws(() => temperatureToEV(0, 'K'), /positive/i);
assert.throws(() => spectralCoordinateFromEV(-1, 'Hz'), /positive/i);

console.log('unit_math.mjs tests passed.');
