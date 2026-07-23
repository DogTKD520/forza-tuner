/**
 * app.js — Main application controller.
 *
 * Owns all UI state, REST API calls, and telemetry frame rendering.
 * Imports websocket.js and charts.js to handle their concerns.
 */

import { connectWebSocket } from './websocket.js';
import { pushSpeedSample } from './charts.js';

// ── DOM helpers ─────────────────────────────────────────────
const $ = (id) => document.getElementById(id);

// ── State ────────────────────────────────────────────────────
const state = {
  activeGame: 'FM',
  activeSetupId: null,
  activeSessionId: null,
  sessionTimerInterval: null,
  sessionStartTime: null,
  taskPollInterval: null,
};

// ── Toast notifications ──────────────────────────────────────
function showToast(message, type = 'info', durationMs = 4000) {
  const container = $('toast-container');
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.textContent = message;
  container.appendChild(toast);
  setTimeout(() => toast.remove(), durationMs);
}

// ── WebSocket status indicators ──────────────────────────────
window.addEventListener('ws:connected', () => {
  $('ws-dot').className = 'status-dot live';
  $('ws-label').textContent = 'Live';
});
window.addEventListener('ws:disconnected', () => {
  $('ws-dot').className = 'status-dot';
  $('ws-label').textContent = 'Reconnecting…';
});

// ── Telemetry frame handler ──────────────────────────────────
window.addEventListener('telemetry', (event) => {
  const frame = event.detail;

  // Gauges
  const speedKph = frame.speed_kph ?? 0;
  $('val-speed').textContent = speedKph.toFixed(0);
  $('bar-speed').style.width = `${Math.min(speedKph / 300 * 100, 100)}%`;

  const throttlePct = (frame.throttle ?? 0) * 100;
  $('val-throttle').textContent = throttlePct.toFixed(0);
  $('bar-throttle').style.width = `${throttlePct}%`;

  const brakePct = (frame.brake ?? 0) * 100;
  $('val-brake').textContent = brakePct.toFixed(0);
  $('bar-brake').style.width = `${brakePct}%`;

  const boostBar = Math.min(frame.boost ?? 0, 2);
  $('val-boost').textContent = (frame.boost ?? 0).toFixed(2);
  $('bar-boost').style.width = `${(boostBar / 2) * 100}%`;

  // Speed chart
  pushSpeedSample(speedKph);

  // Tyre heat
  if (frame.tire_temp) {
    updateTireZones('fl', frame.tire_temp.fl);
    updateTireZones('fr', frame.tire_temp.fr);
    updateTireZones('rl', frame.tire_temp.rl);
    updateTireZones('rr', frame.tire_temp.rr);
  }

  // Suspension bars
  if (frame.suspension) {
    setSuspBar('fl', frame.suspension.fl);
    setSuspBar('fr', frame.suspension.fr);
    setSuspBar('rl', frame.suspension.rl);
    setSuspBar('rr', frame.suspension.rr);
  }
});

// ── Tyre zone colour mapping (blue → green → orange → red) ──
function tempToColor(celsius) {
  const cold = 40, ideal = 80, hot = 110;
  const c = Math.max(cold, Math.min(celsius || cold, hot));
  if (c < ideal) {
    const t = (c - cold) / (ideal - cold);
    return lerpColor('#3a9bdc', '#00e676', t);
  } else {
    const t = (c - ideal) / (hot - ideal);
    return lerpColor('#00e676', '#ff4060', t);
  }
}

function lerpColor(a, b, t) {
  const ah = a.slice(1), bh = b.slice(1);
  const ar = parseInt(ah.slice(0, 2), 16), ag = parseInt(ah.slice(2, 4), 16), ab = parseInt(ah.slice(4, 6), 16);
  const br = parseInt(bh.slice(0, 2), 16), bg = parseInt(bh.slice(2, 4), 16), bb = parseInt(bh.slice(4, 6), 16);
  const r = Math.round(ar + (br - ar) * t);
  const g = Math.round(ag + (bg - ag) * t);
  const bl = Math.round(ab + (bb - ab) * t);
  return `rgb(${r},${g},${bl})`;
}

function updateTireZones(corner, temps) {
  if (!temps || temps.length < 3) return;
  ['i', 'c', 'o'].forEach((zone, idx) => {
    const el = $(`tz-${corner}-${zone}`);
    if (el) {
      const color = tempToColor(temps[idx]);
      el.style.background = color;
      el.title = `${temps[idx].toFixed(0)}°C`;
      el.textContent = `${temps[idx].toFixed(0)}`;
    }
  });
}

function setSuspBar(corner, travel) {
  const el = $(`susp-${corner}`);
  if (el) el.style.width = `${Math.min((travel || 0) * 100, 100)}%`;
}

// ── Game profile toggle ──────────────────────────────────────
window.app = window.app || {};
app.setGame = async function (game) {
  try {
    await fetch('/api/game-profile', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ game }),
    });
    state.activeGame = game;
    $('btn-game-fm').classList.toggle('active', game === 'FM');
    $('btn-game-fh').classList.toggle('active', game === 'FH');
    $('btn-game-fm').setAttribute('aria-pressed', game === 'FM');
    $('btn-game-fh').setAttribute('aria-pressed', game === 'FH');
    showToast(`Game profile set to ${game}`, 'info');
  } catch {
    showToast('Failed to set game profile', 'error');
  }
};

// ── Save vehicle setup ───────────────────────────────────────
app.saveSetup = async function () {
  const name = $('setup-name').value.trim() || 'Default Setup';
  const body = {
    name,
    tire_pressure_front: parseFloat($('psi-front').value),
    tire_pressure_rear:  parseFloat($('psi-rear').value),
    camber_front:        parseFloat($('camber-front').value),
    camber_rear:         parseFloat($('camber-rear').value),
    springs_front:       parseFloat($('springs-front').value),
    springs_rear:        parseFloat($('springs-rear').value),
    arb_front:           parseFloat($('arb-front').value),
    arb_rear:            parseFloat($('arb-rear').value),
    bump_front:          parseFloat($('bump-front').value),
    bump_rear:           parseFloat($('bump-rear').value),
    rebound_front:       parseFloat($('rebound-front').value),
    rebound_rear:        parseFloat($('rebound-rear').value),
  };

  try {
    const resp = await fetch('/api/setups', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const saved = await resp.json();
    state.activeSetupId = saved.id;
    showToast(`Setup "${name}" saved (ID ${saved.id})`, 'success');
  } catch (err) {
    showToast(`Failed to save setup: ${err.message}`, 'error');
  }
};

// ── Session control ──────────────────────────────────────────
app.startSession = async function () {
  const setupQuery = state.activeSetupId
    ? `?setup_id=${state.activeSetupId}`
    : '';
  try {
    const resp = await fetch(`/api/sessions/start${setupQuery}`, { method: 'POST' });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    state.activeSessionId = data.session_id;

    $('btn-start-session').disabled = true;
    $('btn-stop-session').disabled = false;
    $('btn-analyze').disabled = true;
    $('rec-dot').className = 'status-dot recording';
    $('rec-label').textContent = 'Recording';

    state.sessionStartTime = Date.now();
    state.sessionTimerInterval = setInterval(updateSessionTimer, 1000);
    showToast('Recording started', 'success');
  } catch (err) {
    showToast(`Could not start session: ${err.message}`, 'error');
  }
};

app.stopSession = async function () {
  try {
    const resp = await fetch('/api/sessions/stop', { method: 'POST' });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);

    $('btn-start-session').disabled = false;
    $('btn-stop-session').disabled = true;
    $('btn-analyze').disabled = false;
    $('rec-dot').className = 'status-dot';
    $('rec-label').textContent = 'Idle';
    clearInterval(state.sessionTimerInterval);

    showToast('Session stopped — ready to analyse', 'info');
  } catch (err) {
    showToast(`Could not stop session: ${err.message}`, 'error');
  }
};

function updateSessionTimer() {
  if (!state.sessionStartTime) return;
  const elapsed = Math.floor((Date.now() - state.sessionStartTime) / 1000);
  const m = String(Math.floor(elapsed / 60)).padStart(2, '0');
  const s = String(elapsed % 60).padStart(2, '0');
  $('session-timer').textContent = `${m}:${s}`;
}

// ── Analyse session ──────────────────────────────────────────
app.analyzeSession = async function () {
  if (!state.activeSessionId) {
    showToast('No session to analyse', 'error');
    return;
  }
  if (!state.activeSetupId) {
    showToast('Save a setup first before analysing', 'error');
    return;
  }

  const useLlm = $('toggle-ai').checked;
  $('btn-analyze').disabled = true;

  try {
    const resp = await fetch('/api/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: state.activeSessionId,
        setup_id: state.activeSetupId,
        use_llm: useLlm,
      }),
    });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();

    if (data.mode === 'llm') {
      // Show polling UI
      $('task-status-row').style.display = 'flex';
      $('task-status-label').textContent = 'Queued for GPU…';
      pollTaskStatus(data.task_id);
    } else {
      renderRecommendations(data);
    }
  } catch (err) {
    showToast(`Analysis failed: ${err.message}`, 'error');
    $('btn-analyze').disabled = false;
  }
};

async function pollTaskStatus(taskId) {
  clearInterval(state.taskPollInterval);
  state.taskPollInterval = setInterval(async () => {
    try {
      const resp = await fetch(`/api/tasks/${taskId}`);
      const data = await resp.json();
      $('task-status-label').textContent = `Status: ${data.status}`;

      if (data.status === 'completed') {
        clearInterval(state.taskPollInterval);
        $('task-status-row').style.display = 'none';
        renderRecommendations(data.result);
        $('btn-analyze').disabled = false;
      } else if (data.status === 'failed') {
        clearInterval(state.taskPollInterval);
        $('task-status-row').style.display = 'none';
        showToast(`AI analysis failed: ${data.error}`, 'error');
        $('btn-analyze').disabled = false;
      }
    } catch {
      // Network hiccup — keep polling
    }
  }, 2000);
}

// ── Render recommendations table ─────────────────────────────
function renderRecommendations(data) {
  const container = $('rec-content');
  const adjustments = data.adjustments ?? [];

  if (adjustments.length === 0) {
    container.innerHTML = `
      <div class="empty-state">
        <div class="icon">✅</div>
        <div>${data.summary || 'No changes recommended.'}</div>
      </div>`;
    return;
  }

  const paramLabels = {
    tire_pressure_front: 'Tyre Pressure — Front',
    tire_pressure_rear:  'Tyre Pressure — Rear',
    camber_front:        'Camber — Front',
    camber_rear:         'Camber — Rear',
    springs_front:       'Springs — Front',
    springs_rear:        'Springs — Rear',
    arb_front:           'ARB — Front',
    arb_rear:            'ARB — Rear',
    bump_front:          'Bump — Front',
    bump_rear:           'Bump — Rear',
    rebound_front:       'Rebound — Front',
    rebound_rear:        'Rebound — Rear',
  };

  const rows = adjustments.map((adj) => {
    const badgeClass = adj.delta > 0 ? 'positive' : adj.delta < 0 ? 'negative' : 'neutral';
    const sign = adj.delta > 0 ? '+' : '';
    return `
      <tr>
        <td>${paramLabels[adj.parameter] ?? adj.parameter}</td>
        <td style="font-family:'Rajdhani',sans-serif;font-weight:600">${adj.current_value}</td>
        <td style="font-family:'Rajdhani',sans-serif;font-weight:600;color:var(--accent)">${adj.recommended_value}</td>
        <td><span class="delta-badge ${badgeClass}">${sign}${adj.delta}</span></td>
        <td style="color:var(--text-secondary);font-size:0.73rem">${adj.reason}</td>
      </tr>`;
  }).join('');

  container.innerHTML = `
    <p style="font-size:0.8rem;color:var(--text-secondary);margin-bottom:0.75rem">${data.summary ?? ''}</p>
    <div style="overflow-x:auto">
      <table class="rec-table">
        <thead>
          <tr>
            <th>Parameter</th>
            <th>Current</th>
            <th>Recommended</th>
            <th>Delta</th>
            <th>Reason</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    </div>`;

  showToast('Analysis complete!', 'success');
}

// ── Boot ─────────────────────────────────────────────────────
(async function boot() {
  // Sync game profile from backend
  try {
    const resp = await fetch('/api/game-profile');
    const data = await resp.json();
    state.activeGame = data.game;
    $('btn-game-fm').classList.toggle('active', data.game === 'FM');
    $('btn-game-fh').classList.toggle('active', data.game === 'FH');
  } catch { /* continue offline */ }

  connectWebSocket();
})();
