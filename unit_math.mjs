export const KELVIN_PER_EV = 11604.518121550082;
export const HZ_PER_EV = 2.417989242084918e14;

export function temperatureToEV(value, unit) {
  if (!Number.isFinite(value) || value <= 0) {
    throw new Error('Temperature must be a finite positive number.');
  }
  if (unit === 'eV') return value;
  if (unit === 'K') return value / KELVIN_PER_EV;
  throw new Error(`Unknown temperature unit: ${unit}`);
}

export function temperatureFromEV(valueEV, unit) {
  if (!Number.isFinite(valueEV)) return Number.NaN;
  if (unit === 'eV') return valueEV;
  if (unit === 'K') return valueEV * KELVIN_PER_EV;
  throw new Error(`Unknown temperature unit: ${unit}`);
}

export function spectralCoordinateFromEV(valueEV, unit) {
  if (!Number.isFinite(valueEV) || valueEV <= 0) {
    throw new Error('Photon energy must be a finite positive number.');
  }
  if (unit === 'eV') return valueEV;
  if (unit === 'Hz') return valueEV * HZ_PER_EV;
  throw new Error(`Unknown spectral unit: ${unit}`);
}

export function temperatureUnitLabel(unit) {
  if (unit === 'eV') return 'eV';
  if (unit === 'K') return 'K';
  throw new Error(`Unknown temperature unit: ${unit}`);
}

export function spectralUnitLabel(unit) {
  if (unit === 'eV') return 'Photon energy hν [eV]';
  if (unit === 'Hz') return 'Frequency ν [Hz]';
  throw new Error(`Unknown spectral unit: ${unit}`);
}
