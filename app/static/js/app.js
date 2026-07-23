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

// ── Mobile Tab Navigation ────────────────────────────────────
app.switchTab = function (tabId) {
  // Hide all tab contents
  document.querySelectorAll('.mobile-tab-content').forEach(el => el.classList.remove('active'));
  // Deactivate all tab buttons
  document.querySelectorAll('.mobile-nav .nav-btn').forEach(el => el.classList.remove('active'));

  // Activate selected tab content
  const tabContent = $(tabId);
  if (tabContent) tabContent.classList.add('active');

  // Activate selected tab button
  const tabBtn = document.querySelector(`.mobile-nav .nav-btn[data-tab="${tabId}"]`);
  if (tabBtn) tabBtn.classList.add('active');
};

// ── Save vehicle setup ───────────────────────────────────────
app.saveSetup = async function () {
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
    tire_pressure_front,
    tire_pressure_rear,
    camber_front:        parseFloat($('camber-front').value) || -2.5,
    camber_rear:         parseFloat($('camber-rear').value) || -1.5,
    springs_front:       parseFloat($('springs-front').value) || 500.0,
    springs_rear:        parseFloat($('springs-rear').value) || 450.0,
    arb_front:           parseFloat($('arb-front').value) || 25.0,
    arb_rear:            parseFloat($('arb-rear').value) || 20.0,
    bump_front:          parseFloat($('bump-front').value) || 5.0,
    bump_rear:           parseFloat($('bump-rear').value) || 5.0,
    rebound_front:       parseFloat($('rebound-front').value) || 5.0,
    rebound_rear:        parseFloat($('rebound-rear').value) || 5.0,
    pi_rating:           parseInt($('pi-rating').value, 10) || 700,
    hp,
    weight_lbs,
    front_weight_pct:    parseFloat($('front-weight-pct').value) || 52.0,
    aero_front:          parseFloat($('aero-front').value) || 100.0,
    aero_rear:           parseFloat($('aero-rear').value) || 150.0,
    tire_compound:       $('tire-compound').value || 'Sport',
    lock_tire_compound:  $('lock-tire-compound').checked,
    tuneable_springs:    $('tuneable-springs').checked,
    tuneable_arbs:       $('tuneable-arbs').checked,
    tuneable_dampers:    $('tuneable-dampers').checked,
    tuneable_aero_front: $('tuneable-aero-front').checked,
    tuneable_aero_rear:  $('tuneable-aero-rear').checked,
    diff_upgrade_type:   $('diff-upgrade-type').value || 'Race',
    drivetrain:          $('drivetrain').value || 'AWD',
    final_drive:         parseFloat($('final-drive').value) || 3.50,
    gear_1:              parseFloat($('gear-1').value) || 2.89,
    gear_2:              parseFloat($('gear-2').value) || 1.99,
    gear_3:              parseFloat($('gear-3').value) || 1.49,
    gear_4:              parseFloat($('gear-4').value) || 1.16,
    gear_5:              parseFloat($('gear-5').value) || 0.94,
    gear_6:              parseFloat($('gear-6').value) || 0.78,
    gear_7:              parseFloat($('gear-7').value) || 0.65,
    gear_8:              parseFloat($('gear-8').value) || 0.55,
    gear_9:              parseFloat($('gear-9').value) || 0.48,
    gear_10:             parseFloat($('gear-10').value) || 0.42,
    toe_front:           parseFloat($('toe-front').value) || 0.0,
    toe_rear:            parseFloat($('toe-rear').value) || 0.0,
    caster_front:        parseFloat($('caster-front').value) || 5.0,
    ride_height_front:   parseFloat($('ride-height-front').value) || 5.0,
    ride_height_rear:    parseFloat($('ride-height-rear').value) || 5.0,
    downforce_front:     parseFloat($('downforce-front').value) || 100.0,
    downforce_rear:      parseFloat($('downforce-rear').value) || 150.0,
    brake_balance:       parseFloat($('brake-balance').value) || 50.0,
    brake_pressure:      parseFloat($('brake-pressure').value) || 100.0,
    diff_front_accel:    parseFloat($('diff-front-accel').value) || 25.0,
    diff_front_decel:    parseFloat($('diff-front-decel').value) || 0.0,
    diff_rear_accel:     parseFloat($('diff-rear-accel').value) || 50.0,
    diff_rear_decel:     parseFloat($('diff-rear-decel').value) || 15.0,
    diff_center_balance: parseFloat($('diff-center-balance').value) || 65.0,
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
  const goal = $('tuning-goal').value || 'street_road';
  $('btn-analyze').disabled = true;

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
    if (adj.is_upgrade_recommendation) {
      deltaBadgeHtml = `<span class="delta-badge upgrade">UPGRADE</span>`;
    } else if (adj.parameter === 'tire_compound_locked') {
      deltaBadgeHtml = `<span class="delta-badge neutral">LOCKED</span>`;
    } else {
      const badgeClass = adj.delta > 0 ? 'positive' : adj.delta < 0 ? 'negative' : 'neutral';
      const sign = adj.delta > 0 ? '+' : '';
      deltaBadgeHtml = `<span class="delta-badge ${badgeClass}">${sign}${adj.delta}</span>`;
    }

    let warningHtml = '';
    if (adj.pi_impact_warning) {
      warningHtml = `<div class="pi-warning-banner">⚠️ ${adj.pi_impact_warning}</div>`;
    }

    return `
      <tr>
        <td><strong>${paramLabels[adj.parameter] ?? adj.parameter}</strong></td>
        <td style="font-family:'Rajdhani',sans-serif;font-weight:600">${adj.current_value}</td>
        <td style="font-family:'Rajdhani',sans-serif;font-weight:600;color:var(--accent)">${adj.recommended_value}</td>
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
  } catch { /* continue offline */ }

  // Initialise unit and visibility
  const storedUnit = state.unit;
  state.unit = null; // force update
  app.setUnit(storedUnit);
  app.updateVisibility();

  connectWebSocket();
})();
