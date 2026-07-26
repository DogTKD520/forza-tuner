/**
 * app.js — Main application controller.
 *
 * Owns all UI state, REST API calls, and telemetry frame rendering.
 * Imports websocket.js and charts.js to handle their concerns.
 */

import { connectWebSocket } from './websocket.js';
import { pushTelemetrySample } from './charts.js';

// ── DOM helpers ─────────────────────────────────────────────
const $ = (id) => document.getElementById(id);

function escapeHtml(unsafe) {
  return (unsafe || '').toString()
       .replace(/&/g, "&amp;")
       .replace(/</g, "&lt;")
       .replace(/>/g, "&gt;")
       .replace(/"/g, "&quot;")
       .replace(/'/g, "&#039;");
}

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
  const speedUnit = state.unit === 'metric' ? 'km/h' : 'mph';
  const speedFactor = state.unit === 'metric' ? 1 : 0.621371;
  const speedVal = (frame.speed_kph ?? 0) * speedFactor;
  $('val-speed').textContent = speedVal.toFixed(0);
  $('val-speed').nextElementSibling.textContent = speedUnit;
  $('bar-speed').style.width = `${Math.min(speedVal / (state.unit === 'metric' ? 300 : 200) * 100, 100)}%`;

  const throttlePct = (frame.throttle ?? 0) * 100;
  $('val-throttle').textContent = throttlePct.toFixed(0);
  $('bar-throttle').style.width = `${throttlePct}%`;

  const brakePct = (frame.brake ?? 0) * 100;
  $('val-brake').textContent = brakePct.toFixed(0);
  $('bar-brake').style.width = `${brakePct}%`;

  const boostUnit = state.unit === 'metric' ? 'bar' : 'PSI';
  const boostFactor = state.unit === 'metric' ? 1 : 14.5038;
  const boostVal = (frame.boost ?? 0) * boostFactor;
  const boostMax = state.unit === 'metric' ? 2 : 30;
  $('val-boost').textContent = boostVal.toFixed(2);
  $('val-boost').nextElementSibling.textContent = boostUnit;
  $('bar-boost').style.width = `${Math.min(boostVal / boostMax * 100, 100)}%`;

  $('val-rpm').textContent = (frame.rpm ?? 0).toFixed(0);
  
  const gear = frame.gear ?? 0;
  $('val-gear').textContent = gear === 0 ? 'R' : gear;

  // Telemetry chart
  pushTelemetrySample(frame, state.unit);

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

function updateTireZones(corner, tempC) {
  if (tempC == null) return;
  const el = $(`tz-${corner}`);
  if (el) {
    const color = tempToColor(tempC);
    
    const displayTemp = state.unit === 'metric' ? tempC : (tempC * 9 / 5) + 32;
    const symbol = state.unit === 'metric' ? '°C' : '°F';
    
    el.style.background = color;
    el.title = `${displayTemp.toFixed(0)}${symbol}`;
    el.textContent = `${displayTemp.toFixed(0)}`;
  }
}

function setSuspBar(corner, travel) {
  const el = $(`susp-${corner}`);
  // Ensure travel (0.0 to 1.0) maps to a percentage (0 to 100)
  if (el) el.style.width = `${Math.max(0, Math.min((travel || 0) * 100, 100))}%`;
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

// ── Visibility & Conditional Logic ───────────────────────────
app.updateVisibility = function () {
  const dt = $('drivetrain').value;
  $('diff-front-grp').style.display = (dt === 'FWD' || dt === 'AWD') ? 'block' : 'none';
  $('diff-rear-grp').style.display = (dt === 'RWD' || dt === 'AWD') ? 'block' : 'none';
  $('diff-center-grp').style.display = (dt === 'AWD') ? 'block' : 'none';

  const aeroF = $('tuneable-aero-front').checked;
  const aeroR = $('tuneable-aero-rear').checked;
  $('grp-aero-front').style.display = aeroF ? 'block' : 'none';
  $('grp-aero-rear').style.display = aeroR ? 'block' : 'none';
};

// ── Unit System (Metric / Imperial) ──────────────────────────
state.unit = localStorage.getItem('forza_unit') || 'imperial';

app.setUnit = function (unit) {
  if (state.unit === unit) return;
  state.unit = unit;
  localStorage.setItem('forza_unit', unit);
  
  $('btn-unit-metric').classList.toggle('active', unit === 'metric');
  $('btn-unit-imperial').classList.toggle('active', unit === 'imperial');
  $('btn-unit-metric').setAttribute('aria-pressed', unit === 'metric');
  $('btn-unit-imperial').setAttribute('aria-pressed', unit === 'imperial');

  // Convert displayed static labels
  document.querySelectorAll('.unit-hp').forEach(el => el.textContent = unit === 'metric' ? 'kW' : 'HP');
  document.querySelectorAll('.unit-weight').forEach(el => el.textContent = unit === 'metric' ? 'kg' : 'lbs');
  document.querySelectorAll('.unit-pressure').forEach(el => el.textContent = unit === 'metric' ? 'bar' : 'PSI');
  
  const speedUnitEl = $('unit-speed');
  if (speedUnitEl) speedUnitEl.textContent = unit === 'metric' ? 'km/h' : 'mph';
  const boostUnitEl = $('unit-boost');
  if (boostUnitEl) boostUnitEl.textContent = unit === 'metric' ? 'bar' : 'PSI';
  
  // Convert existing values in inputs
  const hpEl = $('hp');
  const weightEl = $('weight');
  const psiF = $('psi-front');
  const psiR = $('psi-rear');
  
  if (unit === 'metric') {
    if (hpEl) hpEl.value = Math.round(hpEl.value * 0.7457); // HP to kW
    if (weightEl) weightEl.value = Math.round(weightEl.value * 0.453592); // lbs to kg
    if (psiF) psiF.value = (psiF.value * 0.0689476).toFixed(2); // PSI to bar
    if (psiR) psiR.value = (psiR.value * 0.0689476).toFixed(2);
  } else {
    if (hpEl) hpEl.value = Math.round(hpEl.value / 0.7457); // kW to HP
    if (weightEl) weightEl.value = Math.round(weightEl.value / 0.453592); // kg to lbs
    if (psiF) psiF.value = (psiF.value / 0.0689476).toFixed(1); // bar to PSI
    if (psiR) psiR.value = (psiR.value / 0.0689476).toFixed(1);
  }
};

// ── Tuning Goal selection ────────────────────────────────────
app.selectGoal = function (goal) {
  $('tuning-goal').value = goal;
  document.querySelectorAll('.goal-badge').forEach((btn) => {
    btn.classList.toggle('active', btn.getAttribute('data-goal') === goal);
  });
};

// ── Tab Navigation ───────────────────────────────────────────
app.switchTab = function (tabId) {
  // Hide all tab contents
  document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
  // Deactivate all tab buttons
  document.querySelectorAll('.app-nav .nav-btn').forEach(el => el.classList.remove('active'));

  // Activate selected tab content
  const tabContent = $(tabId);
  if (tabContent) tabContent.classList.add('active');

  // Activate selected tab button
  const tabBtn = document.querySelector(`.app-nav .nav-btn[data-tab="${tabId}"]`);
  if (tabBtn) tabBtn.classList.add('active');
};

// ── Save vehicle setup ───────────────────────────────────────
app.saveSetup = async function () {

  const getBound = (id, defVal) => {
    const el = $(id);
    if (!el) return { min: null, current: defVal, max: null };
    
    const minVal = parseFloat($(id + '-min')?.value);
    const maxVal = parseFloat($(id + '-max')?.value);
    return {
      min: isNaN(minVal) ? null : minVal,
      current: parseFloat(el.value) || defVal,
      max: isNaN(maxVal) ? null : maxVal,
    };
  };

  const name = $('setup-name').value.trim() || 'Default Setup';
  let tire_pressure_front = parseFloat($('psi-front').value) || 30.0;
  let tire_pressure_rear  = parseFloat($('psi-rear').value) || 30.0;
  let hp                  = parseInt($('hp').value, 10) || 400;
  let weight_lbs          = parseFloat($('weight').value) || 3000.0;

  if (state.unit === 'metric') {
    tire_pressure_front /= 0.0689476;
    tire_pressure_rear /= 0.0689476;
    hp /= 0.7457;
    weight_lbs /= 0.453592;
  }

  const body = {
    name,
    tire_pressure_front: { min: parseFloat($('psi-front-min')?.value) || null, current: tire_pressure_front, max: parseFloat($('psi-front-max')?.value) || null },
    tire_pressure_rear: { min: parseFloat($('psi-rear-min')?.value) || null, current: tire_pressure_rear, max: parseFloat($('psi-rear-max')?.value) || null },
    camber_front: getBound('camber-front', -2.5),
    camber_rear: getBound('camber-rear', -1.5),
    springs_front: getBound('springs-front', 500.0),
    springs_rear: getBound('springs-rear', 450.0),
    arb_front: getBound('arb-front', 25.0),
    arb_rear: getBound('arb-rear', 20.0),
    bump_front: getBound('bump-front', 5.0),
    bump_rear: getBound('bump-rear', 5.0),
    rebound_front: getBound('rebound-front', 5.0),
    rebound_rear: getBound('rebound-rear', 5.0),
    pi_rating:           parseInt($('pi-rating').value, 10) || 700,
    hp,
    weight_lbs,
    front_weight_pct: getBound('front-weight-pct', 52.0),
    aero_front: getBound('downforce-front', 100.0),
    aero_rear: getBound('downforce-rear', 150.0),
    tire_compound:       $('tire-compound').value || 'Sport',
    lock_tire_compound:  $('lock-tire-compound').checked,
    tuneable_springs:    $('tuneable-springs').checked,
    tuneable_arbs:       $('tuneable-arbs').checked,
    tuneable_dampers:    $('tuneable-dampers').checked,
    tuneable_aero_front: $('tuneable-aero-front').checked,
    tuneable_aero_rear:  $('tuneable-aero-rear').checked,
    suspension_type:     $('suspension-type').value || 'Race',
    diff_upgrade_type:   $('diff-upgrade-type').value || 'Race',
    drivetrain:          $('drivetrain').value || 'AWD',
    final_drive: getBound('final-drive', 3.50),
    gear_1: getBound('gear-1', 2.89),
    gear_2: getBound('gear-2', 1.99),
    gear_3: getBound('gear-3', 1.49),
    gear_4: getBound('gear-4', 1.16),
    gear_5: getBound('gear-5', 0.94),
    gear_6: getBound('gear-6', 0.78),
    gear_7: getBound('gear-7', 0.65),
    gear_8: getBound('gear-8', 0.55),
    gear_9: getBound('gear-9', 0.48),
    gear_10: getBound('gear-10', 0.42),
    toe_front: getBound('toe-front', 0.0),
    toe_rear: getBound('toe-rear', 0.0),
    caster_front: getBound('caster-front', 5.0),
    ride_height_front: getBound('ride-height-front', 5.0),
    ride_height_rear: getBound('ride-height-rear', 5.0),
    downforce_front: getBound('downforce-front', 100.0),
    downforce_rear: getBound('downforce-rear', 150.0),
    brake_balance: getBound('brake-balance', 50.0),
    brake_pressure: getBound('brake-pressure', 100.0),
    diff_front_accel: getBound('diff-front-accel', 25.0),
    diff_front_decel: getBound('diff-front-decel', 0.0),
    diff_rear_accel: getBound('diff-rear-accel', 50.0),
    diff_rear_decel: getBound('diff-rear-decel', 15.0),
    diff_center_balance: getBound('diff-center-balance', 65.0),
    tuning_goal:         $('tuning-goal').value || 'street_road',
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
    localStorage.setItem('activeSetupId', saved.id);
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
  if (!state.activeSessionId) {
    showToast('No active session to stop', 'error');
    return;
  }
  try {
    const resp = await fetch(`/api/sessions/${state.activeSessionId}/stop`, { method: 'POST' });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();

    $('btn-start-session').disabled = false;
    $('btn-stop-session').disabled = true;
    $('rec-dot').className = 'status-dot';
    $('rec-label').textContent = 'Idle';
    clearInterval(state.sessionTimerInterval);

    if (data.status === 'discarded') {
      $('session-timer').textContent = '00:00';
      $('btn-analyze').disabled = true;
      state.activeSessionId = null;
      showToast('No data received, session discarded', 'info');
    } else {
      $('btn-analyze').disabled = true; // Wait for explicit save
      if ($('pending-session-controls')) {
        $('pending-session-controls').style.display = 'flex';
      }
      showToast('Session stopped — click Save to keep it', 'info');
    }
  } catch (err) {
    showToast(`Could not stop session: ${err.message}`, 'error');
  }
};

app.saveSession = async function () {
  try {
    const resp = await fetch('/api/sessions/current/save', { method: 'POST' });
    if (!resp.ok) throw new Error('Failed to save session');
    const data = await resp.json();
    state.activeSessionId = data.session_id;
    $('pending-session-controls').style.display = 'none';
    $('btn-analyze').disabled = false;
    showToast(`Session saved (ID ${data.session_id})`, 'success');
  } catch (err) {
    showToast(err.message, 'error');
  }
};

app.clearSession = async function () {
  try {
    await fetch('/api/sessions/current/clear', { method: 'POST' });
    state.activeSessionId = null;
    $('pending-session-controls').style.display = 'none';
    $('session-timer').textContent = '00:00';
    $('btn-analyze').disabled = true;
    showToast('Session discarded', 'info');
  } catch (err) {
    showToast(err.message, 'error');
  }
};

app.loadSessionModal = async function () {
  try {
    const resp = await fetch('/api/sessions');
    if (!resp.ok) throw new Error('Failed to fetch sessions');
    const sessions = await resp.json();
    
    const list = $('session-list');
    list.innerHTML = '';
    
    if (sessions.length === 0) {
      list.innerHTML = '<div style="color:var(--text-muted);padding:1rem;text-align:center;">No sessions found.</div>';
    } else {
      sessions.forEach(session => {
        const btn = document.createElement('button');
        btn.className = 'btn btn-ghost';
        btn.style.textAlign = 'left';
        btn.style.display = 'flex';
        btn.style.justifyContent = 'space-between';
        btn.innerHTML = `<span>Session ${session.id}</span> <span style="color:var(--text-muted)">${new Date(session.started_at).toLocaleString()} | ${Math.round(session.duration_seconds)}s</span>`;
        btn.onclick = () => {
          app.loadSession(session.id);
          $('load-session-modal').close();
        };

        const delBtn = document.createElement('button');
        delBtn.className = 'btn btn-ghost';
        delBtn.style.padding = '0 0.5rem';
        delBtn.style.color = 'var(--text-danger)';
        delBtn.innerHTML = '✕';
        delBtn.onclick = async (e) => {
          e.stopPropagation();
          await app.deleteSession(session.id);
        };

        const row = document.createElement('div');
        row.style.display = 'flex';
        row.style.gap = '0.5rem';
        btn.style.flex = '1';
        row.appendChild(btn);
        row.appendChild(delBtn);
        
        list.appendChild(row);
      });
    }
    
    $('load-session-modal').showModal();
  } catch (err) {
    showToast(err.message, 'error');
  }
};

app.deleteSession = async function (id) {
  if (!confirm("Are you sure you want to delete this session?")) return;
  try {
    const resp = await fetch(`/api/sessions/${id}`, { method: 'DELETE' });
    if (!resp.ok) throw new Error('Failed to delete session');
    
    if (state.activeSessionId === id) {
      state.activeSessionId = null;
      $('btn-analyze').disabled = true;
      $('session-timer').textContent = '00:00';
    }
    
    showToast('Session deleted', 'success');
    await app.loadSessionModal(); // Refresh list
  } catch (err) {
    showToast(err.message, 'error');
  }
};

app.loadSession = function (id) {
  state.activeSessionId = id;
  $('btn-analyze').disabled = false;
  $('session-timer').textContent = 'LOADED';
  showToast(`Loaded Session ${id} for Analysis`, 'success');
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
  const goal = $('tuning-goal').value || 'street_road';
  $('btn-analyze').disabled = true;
  $('llm-error-banner').style.display = 'none';

  try {
    const resp = await fetch('/api/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: state.activeSessionId,
        setup_id: state.activeSetupId,
        use_llm: useLlm,
        tuning_goal: goal,
      }),
    });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();

    if (data.mode === 'llm') {
      app.switchTab('tab-tuning');
      $('task-status-row').style.display = 'flex';
      $('task-status-label').textContent = 'Queued for GPU…';
      pollTaskStatus(data.task_id);
    } else {
      app.switchTab('tab-tuning');
      renderRecommendations(data);
    }
  } catch (err) {
    if (useLlm) {
      $('llm-error-banner').textContent = `AI Analysis failed: ${err.message}`;
      $('llm-error-banner').style.display = 'block';
    } else {
      showToast(`Analysis failed: ${err.message}`, 'error');
    }
    $('btn-analyze').disabled = false;
  }
};

async function pollTaskStatus(taskId) {
  clearInterval(state.taskPollInterval);
  state.taskPollInterval = setInterval(async () => {
    try {
      const resp = await fetch(`/api/tasks/${taskId}`);
      if (!resp.ok) {
        // Task not found or server error — stop polling and surface
        clearInterval(state.taskPollInterval);
        $('task-status-row').style.display = 'none';
        $('llm-error-banner').textContent = `AI task polling failed (HTTP ${resp.status}). The task may have been lost.`;
        $('llm-error-banner').style.display = 'block';
        $('btn-analyze').disabled = false;
        return;
      }
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
        
        $('llm-error-banner').textContent = `AI Analysis failed: ${data.error}`;
        $('llm-error-banner').style.display = 'block';
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
        <div>${escapeHtml(data.summary) || 'No changes recommended.'}</div>
      </div>`;
    return;
  }

  const paramLabels = {
    tire_pressure_front:   'Tyre Pressure — Front',
    tire_pressure_rear:    'Tyre Pressure — Rear',
    camber_front:          'Camber — Front',
    camber_rear:           'Camber — Rear',
    springs_front:         'Springs — Front',
    springs_rear:          'Springs — Rear',
    arb_front:             'ARB — Front',
    arb_rear:              'ARB — Rear',
    bump_front:            'Bump — Front',
    bump_rear:             'Bump — Rear',
    rebound_front:         'Rebound — Front',
    rebound_rear:          'Rebound — Rear',
    springs_upgrade:       '🛠️ Upgrade: Springs',
    arb_upgrade:           '🛠️ Upgrade: Anti-Roll Bars',
    tire_compound_upgrade: '🏎️ Upgrade: Tire Compound',
    tire_compound_locked:  '🔒 Tire Compound (Locked)',
  };

  const rows = adjustments.map((adj) => {
    let deltaBadgeHtml = '';
    const safeDelta = escapeHtml(adj.delta.toString());
    if (adj.is_upgrade_recommendation) {
      deltaBadgeHtml = `<span class="delta-badge upgrade">UPGRADE</span>`;
    } else if (adj.parameter === 'tire_compound_locked') {
      deltaBadgeHtml = `<span class="delta-badge neutral">LOCKED</span>`;
    } else {
      const badgeClass = adj.delta > 0 ? 'positive' : adj.delta < 0 ? 'negative' : 'neutral';
      const sign = adj.delta > 0 ? '+' : '';
      deltaBadgeHtml = `<span class="delta-badge ${badgeClass}">${sign}${safeDelta}</span>`;
    }

    let warningHtml = '';
    if (adj.pi_impact_warning) {
      warningHtml = `<div class="pi-warning-banner">⚠️ ${escapeHtml(adj.pi_impact_warning)}</div>`;
    }

    const safeParam = escapeHtml(paramLabels[adj.parameter] ?? adj.parameter);
    const safeCurrent = escapeHtml(adj.current_value);
    const safeRecommended = escapeHtml(adj.recommended_value);

    return `
      <tr>
        <td><strong>${safeParam}</strong></td>
        <td style="font-family:'Rajdhani',sans-serif;font-weight:600">${safeCurrent}</td>
        <td style="font-family:'Rajdhani',sans-serif;font-weight:600;color:var(--accent)">${safeRecommended}</td>
        <td>${deltaBadgeHtml}</td>
        <td style="color:var(--text-secondary);font-size:0.73rem">
          ${escapeHtml(adj.reason)}
          ${warningHtml}
        </td>
      </tr>`;
  }).join('');

  container.innerHTML = `
    <p style="font-size:0.8rem;color:var(--text-secondary);margin-bottom:0.75rem">${escapeHtml(data.summary ?? '')}</p>
    <div style="overflow-x:auto">
      <table class="rec-table">
        <thead>
          <tr>
            <th>Parameter / Part</th>
            <th>Current</th>
            <th>Recommended</th>
            <th>Type / Delta</th>
            <th>Reason & Notes</th>
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
    
    if (data.ollama_model) {
      const label = $('ai-toggle-label');
      if (label) {
        label.textContent = `Use AI Analysis (${data.ollama_model})`;
      }
    }
  } catch { /* continue offline */ }

  // Initialise unit and visibility
  const storedUnit = state.unit;
  state.unit = null; // force update
  app.setUnit(storedUnit);
  app.updateVisibility();

  // Try auto-loading last saved setup
  const lastSetupId = localStorage.getItem('activeSetupId');
  if (lastSetupId) {
    try {
      await app.loadSetup(lastSetupId);
    } catch (e) {
      console.warn("Could not auto-load setup", e);
    }
  }

  connectWebSocket();
})();

// ── Setup Loading & Modal ─────────────────────────────────────
app.loadSetupModal = async function () {
  try {
    const resp = await fetch('/api/setups');
    if (!resp.ok) throw new Error('Failed to fetch setups');
    const setups = await resp.json();
    
    const list = $('setup-list');
    list.innerHTML = '';
    
    if (setups.length === 0) {
      list.innerHTML = '<div style="color:var(--text-muted);padding:1rem;text-align:center;">No setups found.</div>';
    } else {
      setups.forEach(setup => {
        const btn = document.createElement('button');
        btn.className = 'btn btn-ghost';
        btn.style.textAlign = 'left';
        btn.style.display = 'flex';
        btn.style.justifyContent = 'space-between';
        btn.innerHTML = `<span>${setup.name}</span> <span style="color:var(--text-muted)">${setup.vehicle_id ? 'Car ' + setup.vehicle_id : 'Any Car'} | PI ${setup.pi_rating}</span>`;
        btn.onclick = async () => {
          await app.loadSetup(setup.id);
          $('load-setup-modal').close();
        };

        const delBtn = document.createElement('button');
        delBtn.className = 'btn btn-ghost';
        delBtn.style.padding = '0 0.5rem';
        delBtn.style.color = 'var(--text-danger)';
        delBtn.innerHTML = '✕';
        delBtn.onclick = async (e) => {
          e.stopPropagation(); // prevent loading
          await app.deleteSetup(setup.id);
        };

        const row = document.createElement('div');
        row.style.display = 'flex';
        row.style.gap = '0.5rem';
        btn.style.flex = '1';
        row.appendChild(btn);
        row.appendChild(delBtn);
        
        list.appendChild(row);
      });
    }
    
    $('load-setup-modal').showModal();
  } catch (err) {
    showToast(err.message, 'error');
  }
};

app.deleteSetup = async function (id) {
  if (!confirm("Are you sure you want to delete this setup?")) return;
  try {
    const resp = await fetch(`/api/setups/${id}`, { method: 'DELETE' });
    if (!resp.ok) throw new Error('Failed to delete setup');
    
    if (state.activeSetupId === id) {
      state.activeSetupId = null;
      localStorage.removeItem('activeSetupId');
    }
    
    showToast('Setup deleted', 'success');
    await app.loadSetupModal(); // Refresh the list
  } catch (err) {
    showToast(err.message, 'error');
  }
};

app.loadSetup = async function (id) {
  const resp = await fetch(`/api/setups/${id}`);
  if (!resp.ok) throw new Error('Setup not found');
  const data = await resp.json();
  
  state.activeSetupId = data.id;
  localStorage.setItem('activeSetupId', data.id);
  
  $('setup-name').value = data.name || '';
  if ($('pi-rating')) $('pi-rating').value = data.pi_rating;
  if ($('hp')) $('hp').value = data.hp;
  if ($('weight')) $('weight').value = data.weight_lbs;
  
  if ($('tire-compound')) $('tire-compound').value = data.tire_compound;
  if ($('lock-tire-compound')) $('lock-tire-compound').checked = data.lock_tire_compound;
  if ($('tuneable-springs')) $('tuneable-springs').checked = data.tuneable_springs;
  if ($('tuneable-arbs')) $('tuneable-arbs').checked = data.tuneable_arbs;
  if ($('tuneable-dampers')) $('tuneable-dampers').checked = data.tuneable_dampers;
  if ($('tuneable-aero-front')) $('tuneable-aero-front').checked = data.tuneable_aero_front;
  if ($('tuneable-aero-rear')) $('tuneable-aero-rear').checked = data.tuneable_aero_rear;
  
  if ($('suspension-type')) $('suspension-type').value = data.suspension_type || 'Race';
  if ($('diff-upgrade-type')) $('diff-upgrade-type').value = data.diff_upgrade_type || 'Race';
  if ($('drivetrain')) $('drivetrain').value = data.drivetrain || 'AWD';
  
  app.selectGoal(data.tuning_goal || 'street_road');
  
  // Reload bounds
  let tunables = {};
  if (data.tunables_json) {
    try {
      tunables = JSON.parse(data.tunables_json);
    } catch(e) {}
  }
  
  const setBound = (idStr, key) => {
    const bound = tunables[key];
    if (!bound) return;
    if ($(idStr + '-min') && bound.min !== null) $(idStr + '-min').value = bound.min;
    if ($(idStr) && bound.current !== null) $(idStr).value = bound.current;
    if ($(idStr + '-max') && bound.max !== null) $(idStr + '-max').value = bound.max;
  };

  setBound('camber-front', 'camber_front');
  setBound('camber-rear', 'camber_rear');
  setBound('springs-front', 'springs_front');
  setBound('springs-rear', 'springs_rear');
  setBound('arb-front', 'arb_front');
  setBound('arb-rear', 'arb_rear');
  setBound('bump-front', 'bump_front');
  setBound('bump-rear', 'bump_rear');
  setBound('rebound-front', 'rebound_front');
  setBound('rebound-rear', 'rebound_rear');
  setBound('front-weight-pct', 'front_weight_pct');
  setBound('aero-front', 'aero_front');
  setBound('aero-rear', 'aero_rear');
  
  setBound('final-drive', 'final_drive');
  for (let i=1; i<=10; i++) setBound(`gear-${i}`, `gear_${i}`);
  
  setBound('toe-front', 'toe_front');
  setBound('toe-rear', 'toe_rear');
  setBound('caster-front', 'caster_front');
  setBound('ride-height-front', 'ride_height_front');
  setBound('ride-height-rear', 'ride_height_rear');
  setBound('downforce-front', 'downforce_front');
  setBound('downforce-rear', 'downforce_rear');
  setBound('brake-balance', 'brake_balance');
  setBound('brake-pressure', 'brake_pressure');
  setBound('diff-front-accel', 'diff_front_accel');
  setBound('diff-front-decel', 'diff_front_decel');
  setBound('diff-rear-accel', 'diff_rear_accel');
  setBound('diff-rear-decel', 'diff_rear_decel');
  setBound('diff-center-balance', 'diff_center_balance');
  
  if (tunables.tire_pressure_front && $('psi-front')) {
    let val = tunables.tire_pressure_front.current;
    if (state.unit === 'metric') val *= 0.0689476;
    $('psi-front').value = (state.unit === 'metric') ? val.toFixed(2) : val.toFixed(1);
    if ($('psi-front-min') && tunables.tire_pressure_front.min) $('psi-front-min').value = tunables.tire_pressure_front.min;
    if ($('psi-front-max') && tunables.tire_pressure_front.max) $('psi-front-max').value = tunables.tire_pressure_front.max;
  }
  
  if (tunables.tire_pressure_rear && $('psi-rear')) {
    let val = tunables.tire_pressure_rear.current;
    if (state.unit === 'metric') val *= 0.0689476;
    $('psi-rear').value = (state.unit === 'metric') ? val.toFixed(2) : val.toFixed(1);
    if ($('psi-rear-min') && tunables.tire_pressure_rear.min) $('psi-rear-min').value = tunables.tire_pressure_rear.min;
    if ($('psi-rear-max') && tunables.tire_pressure_rear.max) $('psi-rear-max').value = tunables.tire_pressure_rear.max;
  }
  
  if (state.unit === 'metric') {
    // Re-apply unit scaling to raw DB values loaded in input fields
    if ($('hp')) $('hp').value = Math.round(data.hp * 0.7457);
    if ($('weight')) $('weight').value = Math.round(data.weight_lbs * 0.453592);
  }
  
  app.updateVisibility();
  showToast(`Loaded Setup: ${data.name}`, 'info');
};
