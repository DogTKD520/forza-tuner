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

// ── Telemetry chart ──────────────────────────────────────────
const telemetryCtx = document.getElementById('chart-telemetry')?.getContext('2d');
let telemetryChart = null;

if (telemetryCtx) {
  telemetryChart = new Chart(telemetryCtx, {
    type: 'line',
    data: {
      labels: emptyBuffer(),
      datasets: [
        {
          label: 'Speed',
          data: emptyBuffer(),
          borderColor: '#00d4ff',
          borderWidth: 1.5,
          yAxisID: 'ySpeed',
          tension: 0.3,
          pointRadius: 0
        },
        {
          label: 'Lateral G',
          data: emptyBuffer(),
          borderColor: '#ff4060',
          borderWidth: 1.5,
          yAxisID: 'yGForce',
          tension: 0.3,
          pointRadius: 0
        },
        {
          label: 'Avg Slip Ratio',
          data: emptyBuffer(),
          borderColor: '#00e676',
          borderWidth: 1.5,
          yAxisID: 'ySlip',
          tension: 0.3,
          pointRadius: 0
        }
      ],
    },
    options: {
      ...CHART_DEFAULTS,
      plugins: {
        legend: { display: true, position: 'top', labels: { color: '#7a8399', boxWidth: 12 } },
        tooltip: { enabled: false }
      },
      scales: {
        x: { display: false },
        ySpeed: {
          type: 'linear',
          display: true,
          position: 'left',
          ticks: { color: '#00d4ff', font: { size: 10 }, maxTicksLimit: 4 },
          grid: { color: '#ffffff0a' },
          min: 0,
        },
        yGForce: {
          type: 'linear',
          display: true,
          position: 'right',
          ticks: { color: '#ff4060', font: { size: 10 }, maxTicksLimit: 4 },
          grid: { drawOnChartArea: false },
          min: -2,
          max: 2,
        },
        ySlip: {
          type: 'linear',
          display: false, // hidden axis to scale slip
          min: -2,
          max: 2,
        }
      },
    },
  });
}

/** Push a new telemetry sample onto the rolling chart. */
export function pushTelemetrySample(frame, unit) {
  if (!telemetryChart) return;
  
  const speedFactor = unit === 'metric' ? 1 : 0.621371;
  const speedVal = (frame.speed_kph ?? 0) * speedFactor;
  
  // Calculate avg slip ratio
  const slipObj = frame.tire_slip_ratio;
  let avgSlip = 0;
  if (slipObj) {
    avgSlip = (slipObj.fl + slipObj.fr + slipObj.rl + slipObj.rr) / 4.0;
  }
  
  const latG = frame.lateral_g ?? 0;

  const labels = telemetryChart.data.labels;
  const dataSpeed = telemetryChart.data.datasets[0].data;
  const dataG = telemetryChart.data.datasets[1].data;
  const dataSlip = telemetryChart.data.datasets[2].data;

  dataSpeed.push(speedVal);
  dataG.push(latG);
  dataSlip.push(avgSlip);
  labels.push('');

  if (dataSpeed.length > MAX_DATA_POINTS) {
    dataSpeed.shift();
    dataG.shift();
    dataSlip.shift();
    labels.shift();
  }

  telemetryChart.update('none');
}
