/**
 * PPE Safety Dashboard — JS Controller v2.0
 */

const API = '';
let charts = {};
let currentPage = 1;
const PAGE_SIZE = 20;

// ── Init ──────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  initTheme();
  updateDate();
  setupNav();
  setupEvents();
  loadDashboard();
  setInterval(pollLive, 8000);
});

// ── Theme ─────────────────────────────────────────
function initTheme() {
  const saved = localStorage.getItem('ppe-theme') || 'dark';
  document.documentElement.setAttribute('data-theme', saved);
  updateThemeIcon(saved);
}
function toggleTheme() {
  const cur = document.documentElement.getAttribute('data-theme');
  const next = cur === 'dark' ? 'light' : 'dark';
  document.documentElement.setAttribute('data-theme', next);
  localStorage.setItem('ppe-theme', next);
  updateThemeIcon(next);
  Object.keys(charts).forEach(k => { if (charts[k]) { charts[k].destroy(); delete charts[k]; } });
  const page = document.querySelector('.page.active')?.id?.replace('page-', '');
  if (page) switchPage(page);
}
function updateThemeIcon(theme) {
  const btn = document.getElementById('btn-theme');
  if (btn) btn.textContent = theme === 'dark' ? '☀️' : '🌙';
}

// ── Date ──────────────────────────────────────────
function updateDate() {
  const el = document.getElementById('current-date');
  if (el) el.textContent = new Date().toLocaleDateString('en-US', {weekday:'long', year:'numeric', month:'long', day:'numeric'});
}

// ── Navigation ────────────────────────────────────
function setupNav() {
  document.querySelectorAll('.nav-item').forEach(item => {
    item.addEventListener('click', e => { e.preventDefault(); switchPage(item.dataset.page); });
  });
  document.getElementById('view-all-link')?.addEventListener('click', e => { e.preventDefault(); switchPage('violations'); });
}
function switchPage(page) {
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  document.querySelector(`[data-page="${page}"]`)?.classList.add('active');
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.getElementById(`page-${page}`)?.classList.add('active');
  const titles = {dashboard:'Dashboard', violations:'Violations', analytics:'Analytics', sessions:'Working Hours', zones:'Zones'};
  document.getElementById('page-title').textContent = titles[page] || '';
  document.getElementById('sidebar').classList.remove('open');
  if (page === 'dashboard') loadDashboard();
  else if (page === 'violations') loadViolations();
  else if (page === 'analytics') loadAnalytics();
  else if (page === 'sessions') loadSessions();
  else if (page === 'zones') loadZones();
}

// ── Events ────────────────────────────────────────
function setupEvents() {
  document.getElementById('btn-refresh')?.addEventListener('click', () => {
    const page = document.querySelector('.page.active')?.id?.replace('page-','');
    if (page) switchPage(page);
  });
  document.getElementById('btn-theme')?.addEventListener('click', toggleTheme);
  document.getElementById('btn-apply-filters')?.addEventListener('click', () => { currentPage = 1; loadViolations(); });
  document.getElementById('btn-clear-filters')?.addEventListener('click', () => {
    ['filter-severity','filter-status','filter-deduction','filter-date-from','filter-date-to']
      .forEach(id => { const el = document.getElementById(id); if (el) el.value = ''; });
    currentPage = 1; loadViolations();
  });
  document.getElementById('modal-close')?.addEventListener('click', closeModal);
  document.getElementById('modal-overlay')?.addEventListener('click', e => { if (e.target === e.currentTarget) closeModal(); });
  document.getElementById('menu-toggle')?.addEventListener('click', () => document.getElementById('sidebar').classList.toggle('open'));
  document.getElementById('sidebar-close')?.addEventListener('click', () => document.getElementById('sidebar').classList.remove('open'));
}

// ── API ───────────────────────────────────────────
async function apiFetch(endpoint, options = {}) {
  try {
    const resp = await fetch(`${API}${endpoint}`, {headers:{'Content-Type':'application/json'}, ...options});
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    return await resp.json();
  } catch (err) {
    console.error(`API Error [${endpoint}]:`, err);
    return null;
  }
}

// ── Dashboard ─────────────────────────────────────
async function loadDashboard() {
  const data = await apiFetch('/api/stats');
  if (!data) { showLiveOff(); return; }
  const o = data.overview;
  animateVal('kpi-total', o.total_violations ?? 0);
  animateVal('kpi-today', o.today_count ?? 0);
  animateVal('kpi-critical', o.critical_count ?? 0);
  animateVal('kpi-unresolved', o.unresolved_count ?? 0);
  animateVal('kpi-workers', o.unique_workers ?? 0);
  animateVal('kpi-hour', o.last_hour_count ?? 0);
  animateVal('kpi-deductions', o.deduction_count ?? 0);
  setText('kpi-hours', o.working_hours_today_formatted || '0s');
  setText('unresolved-badge', o.unresolved_count ?? 0);
  renderHourlyChart(data.hourly_trend, 'chart-hourly', 'chart-hourly-empty');
  renderSeverityChart(data.severity_breakdown, 'chart-severity', 'chart-severity-empty');
  renderZoneChart(data.zone_breakdown, 'chart-zones', 'chart-zones-empty');
  renderItemsChart(data.top_violations, 'chart-items', 'chart-items-empty');
  renderRecentTable(data.recent_violations);
}

function showLiveOff() {
  const dot = document.getElementById('live-indicator');
  if (dot) dot.style.opacity = '0.4';
}

function setText(id, val) { const el = document.getElementById(id); if (el) el.textContent = val; }

function animateVal(id, end) {
  const el = document.getElementById(id);
  if (!el) return;
  const start = parseInt(el.textContent) || 0;
  if (start === end) { el.textContent = end; return; }
  const dur = 600, t0 = performance.now();
  const step = ts => {
    const p = Math.min((ts - t0) / dur, 1);
    el.textContent = Math.round(start + (end - start) * (1 - Math.pow(1 - p, 3)));
    if (p < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}

// ── Chart Helpers ─────────────────────────────────
function isDark() { return document.documentElement.getAttribute('data-theme') === 'dark'; }
function textColor() { return isDark() ? '#8892b0' : '#4a5270'; }
function gridColor() { return isDark() ? 'rgba(42,48,80,.3)' : 'rgba(0,0,0,.07)'; }

function baseOpts(legend = false) {
  return {
    responsive: true, maintainAspectRatio: false,
    plugins: { legend: { display: legend, labels: { color: textColor(), font: {family:'Inter', size:11}, padding:14 } } },
    scales: {
      x: { grid: { color: gridColor() }, ticks: { color: textColor(), font: {family:'Inter', size:10} } },
      y: { grid: { color: gridColor() }, ticks: { color: textColor(), font: {family:'Inter', size:10} }, beginAtZero: true }
    }
  };
}

function mkChart(id, type, config) {
  if (charts[id]) { charts[id].destroy(); delete charts[id]; }
  const ctx = document.getElementById(id)?.getContext('2d');
  if (!ctx) return null;
  charts[id] = new Chart(ctx, { type, ...config });
  return charts[id];
}

function showEmpty(emptyId, show) {
  const el = document.getElementById(emptyId);
  if (el) el.classList.toggle('hidden', !show);
}

function renderHourlyChart(data, canvasId, emptyId) {
  const hasData = data?.some(d => d.count > 0);
  showEmpty(emptyId, !hasData);
  if (!hasData) return;
  mkChart(canvasId, 'line', {
    data: {
      labels: data.map(d => d.hour),
      datasets: [{ label:'Violations', data: data.map(d => d.count),
        borderColor:'#6366f1', backgroundColor:'rgba(99,102,241,.12)',
        fill:true, tension:.4, pointRadius:3, pointBackgroundColor:'#6366f1', borderWidth:2 }]
    },
    options: { ...baseOpts(false) }
  });
}

function renderSeverityChart(data, canvasId, emptyId) {
  showEmpty(emptyId, !data?.length);
  if (!data?.length) return;
  const colors = {single:'#f59e0b', multiple:'#ef4444', critical:'#dc2626'};
  mkChart(canvasId, 'doughnut', {
    data: {
      labels: data.map(d => d.severity?.toUpperCase()),
      datasets: [{ data: data.map(d => d.count),
        backgroundColor: data.map(d => colors[d.severity] || '#6366f1'),
        borderWidth:0, hoverOffset:8 }]
    },
    options: { responsive:true, maintainAspectRatio:false, cutout:'65%',
      plugins:{ legend:{ position:'bottom', labels:{ color: textColor(), padding:14, font:{family:'Inter'} } } } }
  });
}

function renderZoneChart(data, canvasId, emptyId) {
  showEmpty(emptyId, !data?.length);
  if (!data?.length) return;
  const pal = ['#6366f1','#3b82f6','#10b981','#f59e0b','#ef4444','#8b5cf6','#06b6d4','#ec4899'];
  mkChart(canvasId, 'bar', {
    data: {
      labels: data.map(d => d.zone),
      datasets: [{ label:'Violations', data: data.map(d => d.count),
        backgroundColor: data.map((_,i) => pal[i%pal.length]),
        borderRadius:6, borderSkipped:false }]
    },
    options: { ...baseOpts(false), indexAxis:'y' }
  });
}

function renderItemsChart(data, canvasId, emptyId) {
  showEmpty(emptyId, !data?.length);
  if (!data?.length) return;
  mkChart(canvasId, 'bar', {
    data: {
      labels: data.map(d => d.missing_items?.length > 22 ? d.missing_items.slice(0,22)+'…' : d.missing_items),
      datasets: [{ label:'Count', data: data.map(d => d.count),
        backgroundColor:'rgba(139,92,246,.6)', borderColor:'#8b5cf6',
        borderWidth:1, borderRadius:6, borderSkipped:false }]
    },
    options: { ...baseOpts(false) }
  });
}

// ── Recent Table ──────────────────────────────────
function renderRecentTable(violations) {
  const tbody = document.getElementById('recent-tbody');
  if (!tbody) return;
  if (!violations?.length) {
    tbody.innerHTML = '<tr class="empty-row"><td colspan="9">No violations recorded yet — run detection to populate</td></tr>';
    setText('recent-count', '0 records');
    return;
  }
  setText('recent-count', `${violations.length} recent`);
  tbody.innerHTML = violations.map(v => `
    <tr style="cursor:pointer" onclick="showViolation(${v.id})">
      <td>#${v.id}</td>
      <td>${fmtTime(v.timestamp)}</td>
      <td>Worker ${v.track_id}</td>
      <td><code style="font-size:11px">${v.user_id || '—'}</code></td>
      <td>${v.zone}</td>
      <td class="td-wrap">${v.missing_items}</td>
      <td>${sevBadge(v.severity)}</td>
      <td>${statBadge(v.resolved)}</td>
      <td>${snapThumb(v.snapshot_path)}</td>
    </tr>`).join('');
}

// ── Violations Page ───────────────────────────────
async function loadViolations() {
  const sev = document.getElementById('filter-severity')?.value || '';
  const res = document.getElementById('filter-status')?.value ?? '';
  const ded = document.getElementById('filter-deduction')?.value ?? '';
  const df  = document.getElementById('filter-date-from')?.value || '';
  const dt  = document.getElementById('filter-date-to')?.value || '';

  let url = `/api/violations?limit=${PAGE_SIZE}&offset=${(currentPage-1)*PAGE_SIZE}`;
  if (sev) url += `&severity=${sev}`;
  if (res !== '') url += `&resolved=${res}`;
  if (df) url += `&date_from=${df}`;
  if (dt) url += `&date_to=${dt}`;

  const data = await apiFetch(url);
  if (!data) return;

  setText('violations-total-count', `${data.total} records`);
  const tbody = document.getElementById('violations-tbody');
  if (!data.violations?.length) {
    tbody.innerHTML = '<tr class="empty-row"><td colspan="11">No violations found</td></tr>';
    document.getElementById('pagination').innerHTML = '';
    return;
  }

  let rows = data.violations;
  if (ded !== '') rows = rows.filter(v => String(v.deduction ?? 0) === ded);

  tbody.innerHTML = rows.map(v => `
    <tr>
      <td>#${v.id}</td>
      <td>${fmtTime(v.timestamp)}</td>
      <td>Worker ${v.track_id}</td>
      <td><code style="font-size:11px">${v.user_id || '—'}</code></td>
      <td>${v.zone}</td>
      <td class="td-wrap">${v.missing_items}</td>
      <td>${sevBadge(v.severity)}</td>
      <td>${statBadge(v.resolved)}</td>
      <td>${dedBadge(v.deduction, v.deduction_amount)}</td>
      <td>${snapThumb(v.snapshot_path)}</td>
      <td>
        <div style="display:flex;gap:4px">
          <button class="btn btn-sm btn-ghost" onclick="showViolation(${v.id})" title="View">👁</button>
          ${!v.resolved ? `<button class="btn btn-sm btn-success" onclick="resolveViolation(${v.id})" title="Resolve">✓</button>` : ''}
          <button class="btn btn-sm btn-danger" onclick="deleteViolation(${v.id})" title="Delete">✕</button>
        </div>
      </td>
    </tr>`).join('');

  renderPagination(data.total);
}

function renderPagination(total) {
  const pages = Math.ceil(total / PAGE_SIZE);
  const el = document.getElementById('pagination');
  if (!el) return;
  if (pages <= 1) { el.innerHTML = ''; return; }
  const start = Math.max(1, currentPage - 2);
  const end = Math.min(pages, currentPage + 2);
  let h = currentPage > 1 ? `<button onclick="goPage(${currentPage-1})">‹</button>` : '';
  for (let i = start; i <= end; i++) h += `<button class="${i===currentPage?'active':''}" onclick="goPage(${i})">${i}</button>`;
  if (currentPage < pages) h += `<button onclick="goPage(${currentPage+1})">›</button>`;
  el.innerHTML = h;
}

window.goPage = p => { currentPage = p; loadViolations(); };

// ── Violation Actions ─────────────────────────────
window.resolveViolation = async id => {
  await apiFetch(`/api/violations/${id}`, {method:'PUT', body:JSON.stringify({resolved:1})});
  showToast('Violation resolved ✓', 'success');
  loadViolations(); loadDashboard();
};

window.deleteViolation = async id => {
  if (!confirm('Delete this violation record?')) return;
  await apiFetch(`/api/violations/${id}`, {method:'DELETE'});
  showToast('Violation deleted', 'info');
  loadViolations(); loadDashboard();
};

window.showViolation = async id => {
  const v = await apiFetch(`/api/violations/${id}`);
  if (!v) return;
  document.getElementById('modal-title').textContent = `Violation #${v.id}`;
  document.getElementById('modal-body').innerHTML = `
    <div class="detail-row"><span class="detail-label">Worker</span><span class="detail-value">Worker ${v.track_id}</span></div>
    <div class="detail-row"><span class="detail-label">User ID</span><span class="detail-value"><code>${v.user_id || '—'}</code></span></div>
    <div class="detail-row"><span class="detail-label">Zone</span><span class="detail-value">${v.zone}</span></div>
    <div class="detail-row"><span class="detail-label">Severity</span><span class="detail-value">${sevBadge(v.severity)}</span></div>
    <div class="detail-row"><span class="detail-label">Missing PPE</span><span class="detail-value">${v.missing_items}</span></div>
    <div class="detail-row"><span class="detail-label">Time</span><span class="detail-value">${fmtTime(v.timestamp)}</span></div>
    <div class="detail-row"><span class="detail-label">Status</span><span class="detail-value">${statBadge(v.resolved)}</span></div>
    <div class="detail-row"><span class="detail-label">Deduction</span><span class="detail-value">${dedBadge(v.deduction, v.deduction_amount)}</span></div>
    <div class="detail-row"><span class="detail-label">Alert</span><span class="detail-value" style="font-size:12px">${v.alert_text}</span></div>
    ${v.snapshot_path ? `<img src="/snapshots/${v.snapshot_path.split('/').pop()}" class="modal-snapshot" onerror="this.style.display='none'" alt="Violation snapshot">` : ''}
    <div class="deduction-form">
      <div class="deduction-toggle">
        <input type="checkbox" id="ded-check" ${v.deduction ? 'checked' : ''}>
        <label for="ded-check">Apply deduction to this violation</label>
      </div>
      <label>Deduction Amount (e.g. 50 EGP)</label>
      <input type="number" id="ded-amount" value="${v.deduction_amount || 0}" min="0" step="0.01" placeholder="0.00">
      <button class="btn btn-warn" onclick="saveDeduction(${v.id})">💰 Save Deduction</button>
    </div>
    <div class="modal-actions">
      ${!v.resolved ? `<button class="btn btn-success" onclick="resolveViolation(${v.id});closeModal()">✓ Resolve</button>` : ''}
      <button class="btn btn-danger" onclick="deleteViolation(${v.id});closeModal()">✕ Delete</button>
    </div>`;
  document.getElementById('modal-overlay').classList.add('active');
};

window.saveDeduction = async id => {
  const checked = document.getElementById('ded-check')?.checked ? 1 : 0;
  const amount  = parseFloat(document.getElementById('ded-amount')?.value) || 0;
  await apiFetch(`/api/violations/${id}`, {method:'PUT', body:JSON.stringify({deduction: checked, deduction_amount: amount})});
  showToast('Deduction saved ✓', 'success');
  closeModal(); loadViolations(); loadDashboard();
};

function closeModal() { document.getElementById('modal-overlay').classList.remove('active'); }

// ── Analytics ─────────────────────────────────────
async function loadAnalytics() {
  const data = await apiFetch('/api/stats');
  if (!data) return;
  const o = data.overview;
  animateVal('a-kpi-total', o.total_violations ?? 0);
  animateVal('a-kpi-resolved', o.resolved_count ?? 0);
  const rate = o.total_violations > 0 ? Math.round((o.resolved_count / o.total_violations) * 100) : 0;
  setText('a-kpi-rate', `${rate}%`);
  setText('a-kpi-hours', o.working_hours_total_formatted || '0s');
  animateVal('a-kpi-deductions', o.deduction_count ?? 0);

  renderHourlyChart(data.hourly_trend, 'chart-analytics-trend', 'chart-analytics-trend-empty');
  renderItemsChart(data.top_violations, 'chart-ppe-types', 'chart-ppe-types-empty');
  renderSeverityChart(data.severity_breakdown, 'chart-severity-analytics', 'chart-severity-analytics-empty');

  const res = o.resolved_count || 0;
  const unres = o.unresolved_count || 0;
  const hasRes = res + unres > 0;
  showEmpty('chart-resolution-empty', !hasRes);
  if (hasRes) {
    mkChart('chart-resolution', 'doughnut', {
      data: {
        labels: ['Resolved','Unresolved'],
        datasets: [{ data:[res, unres], backgroundColor:['#10b981','#ef4444'], borderWidth:0, hoverOffset:8 }]
      },
      options: { responsive:true, maintainAspectRatio:false, cutout:'65%',
        plugins:{ legend:{ position:'bottom', labels:{ color: textColor(), font:{family:'Inter'}, padding:14 } } } }
    });
  }
}

// ── Sessions / Working Hours ──────────────────────
async function loadSessions() {
  const [sess, wh] = await Promise.all([
    apiFetch('/api/sessions?limit=100'),
    apiFetch('/api/working-hours')
  ]);
  if (wh) {
    setText('sess-total-hours', wh.total_formatted || '0s');
    setText('sess-today-hours', wh.today_formatted || '0s');
  }
  if (!sess) return;
  setText('sess-count', sess.sessions?.length ?? 0);
  const tbody = document.getElementById('sessions-tbody');
  if (!sess.sessions?.length) {
    tbody.innerHTML = '<tr class="empty-row"><td colspan="9">No sessions recorded yet — run detection to log working hours</td></tr>';
    return;
  }
  tbody.innerHTML = sess.sessions.map(s => `
    <tr>
      <td>#${s.id}</td>
      <td><code style="font-size:11px">${s.user_id}</code></td>
      <td style="max-width:180px;overflow:hidden;text-overflow:ellipsis" title="${s.source}">${s.source.split('/').pop()}</td>
      <td>${fmtTime(s.started_at)}</td>
      <td>${s.ended_at ? fmtTime(s.ended_at) : '<span style="color:var(--success)">In Progress</span>'}</td>
      <td><strong>${s.duration_formatted}</strong></td>
      <td>${s.total_frames?.toLocaleString() ?? '—'}</td>
      <td>${s.violations_detected ?? 0}</td>
      <td>${s.is_live ? '<span class="badge badge-live">Live</span>' : '<span class="badge badge-video">Video</span>'}</td>
    </tr>`).join('');
}

// ── Zones ─────────────────────────────────────────
async function loadZones() {
  const data = await apiFetch('/api/stats');
  const grid = document.getElementById('zones-grid');
  if (!data || !data.zone_breakdown?.length) {
    grid.innerHTML = '<div class="zone-empty"><div class="empty-icon">📍</div><p>No zone data yet.<br>Run detection to see zone violation stats.</p></div>';
    return;
  }
  const pal = ['#6366f1','#3b82f6','#10b981','#f59e0b','#ef4444','#8b5cf6'];
  grid.innerHTML = data.zone_breakdown.map((z, i) => `
    <div class="zone-card" style="border-top:4px solid ${pal[i%pal.length]}">
      <h3>📍 ${z.zone}</h3>
      <div class="zone-stats">
        <div class="zone-stat">
          <span class="zone-stat-value" style="color:${pal[i%pal.length]}">${z.count}</span>
          <span class="zone-stat-label">Total Violations</span>
        </div>
      </div>
    </div>`).join('');
}

// ── Live Polling ──────────────────────────────────
async function pollLive() {
  const data = await apiFetch('/api/stats/live');
  if (!data) return;
  const badge = document.getElementById('unresolved-badge');
  if (badge) { badge.textContent = data.unresolved || 0; }
  if (data.latest) {
    const dot = document.getElementById('live-indicator');
    if (dot) dot.style.opacity = '1';
  }
  const activePage = document.querySelector('.page.active')?.id;
  if (activePage === 'page-dashboard') loadDashboard();
}

// ── Helpers ───────────────────────────────────────
function fmtTime(ts) {
  if (!ts) return '—';
  try {
    return new Date(ts).toLocaleString('en-US', {month:'short', day:'numeric', hour:'2-digit', minute:'2-digit', second:'2-digit'});
  } catch { return ts; }
}

function sevBadge(s) { return `<span class="badge badge-${s}">${s || '—'}</span>`; }
function statBadge(r) { return r ? '<span class="badge badge-resolved">Resolved</span>' : '<span class="badge badge-unresolved">Open</span>'; }
function dedBadge(d, amt) {
  if (d) return `<span class="badge badge-deducted">−${amt > 0 ? amt : ''}${amt > 0 ? ' EGP' : 'Deducted'}</span>`;
  return '<span class="badge badge-no-deduction">None</span>';
}

function snapThumb(path) {
  if (!path) return '<span style="color:var(--text3);font-size:11px">—</span>';
  const name = path.split('/').pop();
  return `<img src="/snapshots/${name}" class="img-thumb" onclick="event.stopPropagation();showImg('/snapshots/${name}')" onerror="this.style.display='none'" alt="snap">`;
}

window.showImg = src => {
  document.getElementById('modal-title').textContent = 'Violation Photo';
  document.getElementById('modal-body').innerHTML = `<img src="${src}" style="width:100%;border-radius:10px" onerror="this.src=''" alt="Violation snapshot">`;
  document.getElementById('modal-overlay').classList.add('active');
};

function showToast(msg, type = 'info') {
  const c = document.getElementById('toast-container');
  const t = document.createElement('div');
  t.className = `toast ${type}`;
  t.textContent = msg;
  c.appendChild(t);
  setTimeout(() => { t.style.opacity = '0'; t.style.transform = 'translateX(40px)'; setTimeout(() => t.remove(), 300); }, 3500);
}

// ── Live View ─────────────────────────────────────
let _liveInterval = null;
let _elapsedInterval = null;
let _detStarted = null;

const _titles = {
  dashboard:'Dashboard', violations:'Violations',
  analytics:'Analytics', sessions:'Working Hours',
  zones:'Zones', live:'🎥 Live View'
};

// Override switchPage to include live
const _origSwitch = switchPage;
window.switchPage = function(page) {
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  document.querySelector(`[data-page="${page}"]`)?.classList.add('active');
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.getElementById(`page-${page}`)?.classList.add('active');
  document.getElementById('page-title').textContent = _titles[page] || page;
  document.getElementById('sidebar').classList.remove('open');
  if (page === 'dashboard')  loadDashboard();
  else if (page === 'violations') loadViolations();
  else if (page === 'analytics')  loadAnalytics();
  else if (page === 'sessions')   loadSessions();
  else if (page === 'zones')      loadZones();
  else if (page === 'live')       initLivePage();
};

// Rebuild nav listener to include live
document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('.nav-item').forEach(item => {
    item.onclick = e => { e.preventDefault(); switchPage(item.dataset.page); };
  });
});

function initLivePage() {
  updateSourceUI();
  pollDetectionStatus();
  if (_liveInterval) clearInterval(_liveInterval);
  _liveInterval = setInterval(pollDetectionStatus, 1500);
}

window.updateSourceUI = function() {
  const t = document.getElementById('live-source-type')?.value;
  document.getElementById('live-video-group').style.display = t==='video' ? '' : 'none';
  document.getElementById('live-cam-group').style.display   = t==='camera' ? '' : 'none';
};

window.startDetection = async function() {
  const type   = document.getElementById('live-source-type')?.value;
  const source = type === 'camera'
    ? (document.getElementById('live-cam-index')?.value || '0')
    : (document.getElementById('live-video-select')?.value || 'video2.ts');
  const uid    = document.getElementById('live-user-id')?.value || 'operator_01';
  const noTts  = document.getElementById('live-tts')?.value === 'true';

  document.getElementById('btn-start-det').disabled = true;
  document.getElementById('btn-stop-det').disabled  = false;
  document.getElementById('live-feed-src').textContent = source;

  const res = await apiFetch('/api/detection/start', {
    method: 'POST',
    body: JSON.stringify({ source, user_id: uid, no_tts: noTts })
  });
  if (res?.status === 'already_running') {
    showToast('Detection already running', 'warning'); return;
  }
  if (res?.status === 'started') {
    showToast(`Detection started: ${source}`, 'success');
    _detStarted = Date.now();
    // Reload stream img
    const img = document.getElementById('live-stream-img');
    if (img) { img.src = '/api/stream?' + Date.now(); }
    document.getElementById('live-overlay-stopped')?.classList.add('hidden');
    document.getElementById('live-badge').style.display = '';
    if (_elapsedInterval) clearInterval(_elapsedInterval);
    _elapsedInterval = setInterval(() => {
      if (_detStarted) {
        const s = Math.floor((Date.now() - _detStarted) / 1000);
        setText('ls-elapsed', _fmtSec(s));
      }
    }, 1000);
  }
};

window.stopDetection = async function() {
  await apiFetch('/api/detection/stop', { method: 'POST' });
  showToast('Detection stopped', 'info');
  document.getElementById('btn-start-det').disabled = false;
  document.getElementById('btn-stop-det').disabled  = true;
  document.getElementById('live-badge').style.display = 'none';
  document.getElementById('live-overlay-stopped')?.classList.remove('hidden');
  if (_elapsedInterval) { clearInterval(_elapsedInterval); _elapsedInterval = null; }
  _detStarted = null;
  setTimeout(() => { loadDashboard(); }, 1000);
};

async function pollDetectionStatus() {
  const d = await apiFetch('/api/detection/status');
  if (!d) return;
  const running = d.running;
  const pill = document.getElementById('live-status-pill');
  if (pill) {
    pill.textContent = running ? '● Running' : '⬤ Stopped';
    pill.classList.toggle('running', running);
  }
  document.getElementById('btn-start-det').disabled = running;
  document.getElementById('btn-stop-det').disabled  = !running;
  document.getElementById('live-badge').style.display = running ? '' : 'none';
  if (d.stats) {
    setText('ls-frames',     d.stats.frames?.toLocaleString() || '0');
    setText('ls-violations', d.stats.violations || 0);
    setText('ls-workers',    d.stats.workers || 0);
    setText('ls-fps',        d.stats.fps || '0');
    setText('ls-progress',   d.stats.total_frames > 0
      ? `${d.stats.progress?.toFixed(1)}%` : (running ? 'Live' : '—'));
  }
  if (running) {
    document.getElementById('live-overlay-stopped')?.classList.add('hidden');
    // Auto-refresh dashboard KPIs while running
    const liveKPI = await apiFetch('/api/stats/live');
    if (liveKPI) {
      animateVal('kpi-total',      liveKPI.total_violations   ?? 0);
      animateVal('kpi-unresolved', liveKPI.unresolved         ?? 0);
      animateVal('kpi-deductions', liveKPI.deduction_count    ?? 0);
      setText('unresolved-badge',  liveKPI.unresolved         ?? 0);
    }
  } else {
    document.getElementById('live-overlay-stopped')?.classList.remove('hidden');
    if (_liveInterval && !document.getElementById('page-live')?.classList.contains('active')) {
      clearInterval(_liveInterval); _liveInterval = null;
    }
  }
  if (d.error) showToast(`Detection error: ${d.error}`, 'error');
}

function _fmtSec(s) {
  const h=Math.floor(s/3600), m=Math.floor((s%3600)/60), sec=s%60;
  return h>0 ? `${h}h ${m}m ${sec}s` : m>0 ? `${m}m ${sec}s` : `${sec}s`;
}

// Override pollLive to also refresh deductions
const _origPoll = pollLive;
window.pollLive = async function() {
  const data = await apiFetch('/api/stats/live');
  if (!data) return;
  const badge = document.getElementById('unresolved-badge');
  if (badge) badge.textContent = data.unresolved || 0;
  animateVal('kpi-deductions', data.deduction_count ?? 0);
  if (data.detection_running) {
    document.getElementById('live-badge').style.display = '';
  }
};

// ══════════════════════════════════════════════════
// DEDUCTION FIX — overrides old showViolation & saveDeduction
// ══════════════════════════════════════════════════

window.showViolation = async id => {
  const v = await apiFetch(`/api/violations/${id}`);
  if (!v) return;
  document.getElementById('modal-title').textContent = `Violation #${v.id}`;
  const hasSnap = v.snapshot_path && v.snapshot_path.trim() !== '';
  const snapName = hasSnap ? v.snapshot_path.split('/').pop() : '';
  document.getElementById('modal-body').innerHTML = `
    <div class="detail-row"><span class="detail-label">Worker</span><span class="detail-value">Worker ${v.track_id}</span></div>
    <div class="detail-row"><span class="detail-label">User ID</span><span class="detail-value"><code>${v.user_id||'—'}</code></span></div>
    <div class="detail-row"><span class="detail-label">Zone</span><span class="detail-value">${v.zone}</span></div>
    <div class="detail-row"><span class="detail-label">Severity</span><span class="detail-value">${sevBadge(v.severity)}</span></div>
    <div class="detail-row"><span class="detail-label">Missing PPE</span><span class="detail-value">${v.missing_items}</span></div>
    <div class="detail-row"><span class="detail-label">Time</span><span class="detail-value">${fmtTime(v.timestamp)}</span></div>
    <div class="detail-row"><span class="detail-label">Status</span><span class="detail-value">${statBadge(v.resolved)}</span></div>
    <div class="detail-row"><span class="detail-label">Alert</span><span class="detail-value" style="font-size:12px">${v.alert_text}</span></div>
    ${hasSnap ? `<img src="/snapshots/${snapName}" class="modal-snapshot" onerror="this.style.display='none'" alt="Violation photo">` : ''}
    <div class="deduction-form">
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px">
        <span style="font-size:20px">💰</span>
        <span style="font-weight:700;font-size:13px;color:var(--text)">Deduction Management</span>
        ${v.deduction ? '<span class="badge badge-deducted">ACTIVE</span>' : '<span class="badge badge-no-deduction">None</span>'}
      </div>
      ${v.deduction ? `<div style="padding:8px 12px;background:rgba(16,185,129,.1);border:1px solid rgba(16,185,129,.3);border-radius:8px;margin-bottom:12px;font-size:13px;color:var(--success)">✓ Deduction active: <strong>${v.deduction_amount} EGP</strong></div>` : ''}
      <label>Deduction Amount (EGP)</label>
      <input type="number" id="ded-amount-${v.id}" value="${v.deduction_amount > 0 ? v.deduction_amount : ''}"
             min="0" step="0.5" placeholder="e.g. 50" style="width:100%;margin-bottom:10px;background:var(--bg3);border:1px solid var(--border);color:var(--text);border-radius:8px;padding:8px 10px;font-size:13px">
      <div style="display:flex;gap:8px;flex-wrap:wrap">
        <button class="btn btn-warn" onclick="applyDeduction(${v.id})">💰 Apply Deduction</button>
        ${v.deduction ? `<button class="btn btn-ghost" onclick="removeDeduction(${v.id})">✕ Remove Deduction</button>` : ''}
      </div>
    </div>
    <div class="modal-actions" style="margin-top:16px">
      ${!v.resolved ? `<button class="btn btn-success" onclick="resolveViolation(${v.id});closeModal()">✓ Resolve</button>` : ''}
      <button class="btn btn-danger" onclick="deleteViolation(${v.id});closeModal()">✕ Delete</button>
    </div>`;
  document.getElementById('modal-overlay').classList.add('active');
};

window.applyDeduction = async id => {
  const inp = document.getElementById(`ded-amount-${id}`);
  const amount = parseFloat(inp?.value) || 0;
  if (amount <= 0) {
    showToast('⚠️ Enter an amount greater than 0', 'warning');
    inp?.focus(); return;
  }
  const res = await apiFetch(`/api/violations/${id}`, {
    method: 'PUT',
    body: JSON.stringify({ deduction: 1, deduction_amount: amount })
  });
  if (res?.status === 'ok') {
    showToast(`✓ Deduction of ${amount} EGP applied to violation #${id}`, 'success');
    closeModal();
    await loadDashboard();
    loadViolations();
  } else {
    showToast('Failed to apply deduction', 'error');
  }
};

window.removeDeduction = async id => {
  const res = await apiFetch(`/api/violations/${id}`, {
    method: 'PUT',
    body: JSON.stringify({ deduction: 0, deduction_amount: 0 })
  });
  if (res?.status === 'ok') {
    showToast('Deduction removed', 'info');
    closeModal();
    await loadDashboard();
    loadViolations();
  }
};

// Also fix saveDeduction for backward compat
window.saveDeduction = async (id, apply) => {
  if (apply) await applyDeduction(id);
  else await removeDeduction(id);
};
