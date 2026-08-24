export function isDrawablePoint(point, logX, logY) {
  const xGood = Number.isFinite(point.x) && (!logX || point.x > 0);
  const yGood = Number.isFinite(point.y) && (logY ? point.y > 0 : point.y >= 0);
  return xGood && yGood;
}

export function preparePlotDomain(points, logX, logY) {
  const xValues = points
    .map((point) => point.x)
    .filter((value) => Number.isFinite(value) && (!logX || value > 0));
  if (xValues.length === 0) {
    throw new Error(logX
      ? 'The selected curve has no positive finite x values for a logarithmic x-axis.'
      : 'The selected curve has no finite x values.');
  }

  const drawable = points.filter((point) => isDrawablePoint(point, logX, logY));
  if (drawable.length === 0) {
    throw new Error(logY
      ? 'The selected curve has no positive finite opacity values for a logarithmic y-axis.'
      : 'The selected curve has no non-negative finite opacity values for a linear y-axis.');
  }

  let xMin = Math.min(...xValues);
  let xMax = Math.max(...xValues);
  if (xMin === xMax) {
    if (logX) {
      xMin /= 1.1;
      xMax *= 1.1;
    } else {
      const pad = Math.max(Math.abs(xMin) * 0.05, 1);
      xMin -= pad;
      xMax += pad;
    }
  }

  let yMin;
  let yMax;
  if (logY) {
    const yValues = drawable.map((point) => point.y);
    yMin = Math.min(...yValues);
    yMax = Math.max(...yValues);
    if (yMin === yMax) {
      yMin /= 1.1;
      yMax *= 1.1;
    }
  } else {
    yMin = 0;
    yMax = Math.max(...drawable.map((point) => point.y));
    if (yMax === 0) yMax = 1;
    else yMax *= 1.05;
  }

  return { drawable, xMin, xMax, yMin, yMax };
}

export function groupSpectrumChunks(chunks) {
  const batches = [];
  const batchByGroupRange = new Map();
  for (const chunk of chunks) {
    const key = `${chunk.group_start}:${chunk.group_stop}`;
    if (!batchByGroupRange.has(key)) {
      const batch = [];
      batchByGroupRange.set(key, batch);
      batches.push(batch);
    }
    batchByGroupRange.get(key).push(chunk);
  }
  return batches;
}

export async function processSpectrumChunksSequentially(chunks, loadChunk, visitBatch) {
  const batches = groupSpectrumChunks(chunks);
  for (let batchIndex = 0; batchIndex < batches.length; batchIndex += 1) {
    const chunkValues = await Promise.all(batches[batchIndex].map(async (chunk) => ({
      chunk,
      values: await loadChunk(chunk),
    })));
    await visitBatch(chunkValues, batchIndex, batches.length);
  }
}

export function makeSpectrumPlotPoints(spectrum, energyEdges, spectralUnit, hertzPerEV) {
  const points = [];
  for (let group = 0; group < spectrum.values.length; group += 1) {
    const energyLow = energyEdges[group];
    const energyHigh = energyEdges[group + 1];
    const energyCenter = Math.sqrt(energyLow * energyHigh);
    points.push({
      x: spectralUnit === 'Hz' ? energyCenter * hertzPerEV : energyCenter,
      y: spectrum.values[group],
      status: spectrum.statuses[group],
      group,
      energyLow,
      energyHigh,
    });
  }
  return points;
}

export async function loadPlotPoints(definition, loaders) {
  if (definition.sweep === 'frequency') return loaders.spectrum(definition);
  if (definition.energyMode === 'integrated') return loaders.integrated(definition);
  return loaders.specificGroup(definition);
}
