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
