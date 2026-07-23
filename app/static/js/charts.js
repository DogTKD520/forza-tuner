/**
 * charts.js — Chart.js live telemetry charts.
 *
 * Creates and exports update functions for each chart so app.js
 * can push new data points without needing Chart.js internals.
 */

const MAX_DATA_POINTS = 900;   // 60 s at 15 fps

const CHART_DEFAULTS = {
  responsive: true,
  maintainAspectRatio: false,
  animation: false,
  plugins: { legend: { display: false }, tooltip: { enabled: false } },
  elements: { point: { radius: 0 } },
  scales: {
    x: { display: false },
    y: {
      ticks: { color: '#7a8399', font: { size: 10 }, maxTicksLimit: 4 },
      grid: { color: '#ffffff0a' },
    },
  },
};

/** Build an empty ring-buffer of nulls used to pre-fill chart datasets. */
function emptyBuffer() {
  return new Array(MAX_DATA_POINTS).fill(null);
}

/** Return a gradient fill for speed chart */
function speedGradient(ctx) {
  const gradient = ctx.createLinearGradient(0, 0, 0, 200);
  gradient.addColorStop(0, '#00d4ff44');
  gradient.addColorStop(1, '#00d4ff00');
  return gradient;
}

// ── Speed chart ──────────────────────────────────────────────
const speedCtx = document.getElementById('chart-speed')?.getContext('2d');
let speedChart = null;
if (speedCtx) {
  speedChart = new Chart(speedCtx, {
    type: 'line',
    data: {
      labels: emptyBuffer(),
      datasets: [{
        data: emptyBuffer(),
        borderColor: '#00d4ff',
        borderWidth: 1.5,
        fill: true,
        backgroundColor: speedGradient(speedCtx),
        tension: 0.3,
      }],
    },
    options: {
      ...CHART_DEFAULTS,
      scales: {
        ...CHART_DEFAULTS.scales,
        y: { ...CHART_DEFAULTS.scales.y, min: 0, title: { display: false } },
      },
    },
  });
}

/** Push a new speed value (km/h) onto the rolling chart. */
export function pushSpeedSample(kph) {
  if (!speedChart) return;
  const dataset = speedChart.data.datasets[0];
  dataset.data.push(kph);
  if (dataset.data.length > MAX_DATA_POINTS) dataset.data.shift();
  speedChart.data.labels.push('');
  if (speedChart.data.labels.length > MAX_DATA_POINTS) speedChart.data.labels.shift();
  speedChart.update('none');   // skip animation for performance
}
