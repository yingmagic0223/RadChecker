'use strict';

const API = '';  // same-origin when served via FastAPI; or set to 'http://localhost:8000'

// ── Utilities ─────────────────────────────────────────────────────────────────

const $ = id => document.getElementById(id);
const loading = (show, msg = 'Processing…') => {
  $('loading-overlay').classList.toggle('d-none', !show);
  $('loading-msg').textContent = msg;
};
const fmt = (n, dec = 1) => n == null ? '—' : Number(n).toFixed(dec);
const fmtInt = n => n == null ? '—' : Math.round(n).toLocaleString();

async function api(path, opts = {}) {
  const r = await fetch(API + path, {
    headers: { 'Content-Type': 'application/json' },
    ...opts,
  });
  if (!r.ok) {
    const err = await r.json().catch(() => ({ detail: r.statusText }));
    throw new Error(err.detail || r.statusText);
  }
  return r.status === 204 ? null : r.json();
}

function showToast(msg, variant = 'success') {
  const t = document.createElement('div');
  t.className = `alert alert-${variant} position-fixed bottom-0 end-0 m-3 shadow`;
  t.style.zIndex = 10000;
  t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(() => t.remove(), 3500);
}

// ── Tab Routing ────────────────────────────────────────────────────────────────

const tabs = ['dashboard', 'plans', 'memory', 'evaluate'];
function showTab(name) {
  tabs.forEach(t => {
    document.querySelector(`[data-tab="${t}"]`).classList.toggle('active', t === name);
    $(`tab-${t}`).classList.toggle('d-none', t !== name);
  });
  if (name === 'dashboard') loadDashboard();
  if (name === 'plans') loadPlans();
  if (name === 'memory') loadMemory();
}

document.querySelectorAll('.tab-btn').forEach(btn => {
  btn.addEventListener('click', () => showTab(btn.dataset.tab));
});

// ── Dashboard ─────────────────────────────────────────────────────────────────

async function loadDashboard() {
  try {
    const stats = await api('/api/stats');
    $('stat-plans').textContent = fmtInt(stats.total_plans);
    $('stat-memory').textContent = fmtInt(stats.memory_groups);
    $('stat-evals').textContent = fmtInt(stats.total_evaluations);
    renderBarChart('chart-by-site', stats.plans_by_site, '#1a4a8a');
    renderBarChart('chart-by-technique', stats.plans_by_technique, '#0d9488');
  } catch (e) {
    console.error('Dashboard load error:', e);
  }
}

function renderBarChart(containerId, data, color) {
  const el = $(containerId);
  if (!data || !Object.keys(data).length) {
    el.innerHTML = '<p class="text-muted small">No data yet.</p>';
    return;
  }
  const max = Math.max(...Object.values(data));
  el.innerHTML = Object.entries(data)
    .sort((a, b) => b[1] - a[1])
    .map(([label, val]) => `
      <div class="bar-row d-flex align-items-center gap-2">
        <div class="bar-label text-truncate" title="${label}">${label}</div>
        <div class="bar-track">
          <div class="bar-fill" style="width:${Math.max(8, (val / max) * 100)}%; background:${color}">
            ${val}
          </div>
        </div>
      </div>
    `).join('');
}

$('btn-seed').addEventListener('click', async () => {
  loading(true, 'Loading sample data…');
  try {
    const r = await api('/api/seed', { method: 'POST' });
    showToast(r.message);
    loadDashboard();
    populateCatalogLists();
  } catch (e) {
    showToast(e.message, 'danger');
  } finally {
    loading(false);
  }
});

// ── Plans Table ───────────────────────────────────────────────────────────────

async function loadPlans() {
  const site = $('filter-site').value;
  const technique = $('filter-technique').value;
  let url = '/api/plans';
  const params = new URLSearchParams();
  if (site) params.set('disease_site', site);
  if (technique) params.set('technique', technique);
  if (params.toString()) url += '?' + params;

  try {
    const plans = await api(url);
    renderPlansTable(plans);
  } catch (e) {
    showToast('Failed to load plans: ' + e.message, 'danger');
  }
}

function renderPlansTable(plans) {
  const tbody = $('plans-tbody');
  if (!plans.length) {
    tbody.innerHTML = '<tr><td colspan="10" class="text-center text-muted py-3">No plans found. Use "Load Sample Data" on the dashboard or add plans manually.</td></tr>';
    return;
  }
  tbody.innerHTML = plans.map(p => `
    <tr>
      <td class="fw-semibold">${p.plan_name}</td>
      <td><span class="badge bg-primary">${p.disease_site}</span></td>
      <td><span class="badge bg-secondary">${p.technique}</span></td>
      <td>${p.total_dose_gy} Gy / ${p.fractions} fx</td>
      <td>${p.total_beams}</td>
      <td>${fmtInt(p.total_segments)}</td>
      <td>${fmtInt(p.total_mus)}</td>
      <td>${fmt(p.mu_efficiency, 0)}</td>
      <td>${fmt(p.mus_per_fraction, 0)}</td>
      <td>
        <button class="btn btn-xs btn-outline-danger" onclick="deletePlan(${p.id})">
          <i class="bi bi-trash"></i>
        </button>
      </td>
    </tr>
  `).join('');
}

$('btn-filter').addEventListener('click', loadPlans);

async function deletePlan(id) {
  if (!confirm('Delete this plan?')) return;
  try {
    await api(`/api/plans/${id}`, { method: 'DELETE' });
    showToast('Plan deleted');
    loadPlans();
  } catch (e) {
    showToast(e.message, 'danger');
  }
}

// Add Plan Modal
$('btn-save-plan').addEventListener('click', async () => {
  const dose = parseFloat($('ap-dose').value);
  const fractions = parseInt($('ap-fractions').value);
  const totalMu = parseFloat($('ap-mus').value);
  const beams = parseInt($('ap-beams').value);
  const segments = parseInt($('ap-segments').value);

  if (!$('ap-name').value || !$('ap-site').value || !$('ap-technique').value || !dose || !fractions || !totalMu || !beams || !segments) {
    showToast('Please fill in all required fields', 'warning');
    return;
  }

  const payload = {
    plan_name: $('ap-name').value,
    disease_site: $('ap-site').value,
    technique: $('ap-technique').value,
    total_dose_gy: dose,
    fractions,
    total_beams: beams,
    total_segments: segments,
    total_mus: totalMu,
    ptvs: [],
    oars: [],
    beam_details: [],
    notes: $('ap-notes').value || null,
    is_approved: $('ap-approved').value === 'true',
  };

  loading(true, 'Saving plan…');
  try {
    await api('/api/plans', { method: 'POST', body: JSON.stringify(payload) });
    showToast('Plan saved');
    bootstrap.Modal.getInstance($('addPlanModal')).hide();
    $('add-plan-form').reset();
    loadPlans();
  } catch (e) {
    showToast(e.message, 'danger');
  } finally {
    loading(false);
  }
});

// ── AI Memory ─────────────────────────────────────────────────────────────────

async function loadMemory() {
  try {
    const memories = await api('/api/memory');
    renderMemoryCards(memories);
  } catch (e) {
    showToast('Failed to load memory: ' + e.message, 'danger');
  }
}

function renderMemoryCards(memories) {
  const container = $('memory-cards');
  if (!memories.length) {
    container.innerHTML = '<div class="col-12"><p class="text-muted">No memory generated yet. Add historical plans and click "Regenerate Memory".</p></div>';
    return;
  }
  container.innerHTML = memories.map(m => `
    <div class="col-md-6 col-xl-4">
      <div class="memory-card h-100">
        <div class="d-flex align-items-center gap-2 mb-3">
          <span class="site-badge">${m.disease_site}</span>
          <span class="tech-badge">${m.technique}</span>
          <span class="ms-auto text-muted small">${m.plan_count} plans</span>
        </div>
        <div class="mb-3">
          <div class="metric-row"><span class="metric-name">MU Efficiency</span><span class="metric-value">${fmt(m.mu_efficiency_mean, 0)} ± ${fmt(m.mu_efficiency_std, 0)} MU/Gy</span></div>
          <div class="metric-row text-muted small"><span>P5–P95</span><span>${fmt(m.mu_efficiency_p5, 0)} – ${fmt(m.mu_efficiency_p95, 0)}</span></div>
          <div class="metric-row"><span class="metric-name">MU/Fraction</span><span class="metric-value">${fmt(m.mus_per_fraction_mean, 0)} ± ${fmt(m.mus_per_fraction_std, 0)}</span></div>
          <div class="metric-row"><span class="metric-name">Total Beams</span><span class="metric-value">${fmt(m.total_beams_mean, 1)} (${fmtInt(m.total_beams_min)}–${fmtInt(m.total_beams_max)})</span></div>
          <div class="metric-row"><span class="metric-name">Total Segments</span><span class="metric-value">${fmt(m.total_segments_mean, 0)} ± ${fmt(m.total_segments_std, 0)}</span></div>
          <div class="metric-row"><span class="metric-name">Seg/Beam</span><span class="metric-value">${fmt(m.segments_per_beam_mean, 1)} ± ${fmt(m.segments_per_beam_std, 1)}</span></div>
          <div class="metric-row"><span class="metric-name">MU/Segment</span><span class="metric-value">${fmt(m.mus_per_segment_mean, 2)} ± ${fmt(m.mus_per_segment_std, 2)}</span></div>
        </div>
        ${m.ai_insights ? `<div class="border-top pt-2 text-muted small" style="font-size:0.78rem;line-height:1.5">${m.ai_insights}</div>` : ''}
      </div>
    </div>
  `).join('');
}

$('btn-gen-memory').addEventListener('click', async () => {
  loading(true, 'Generating AI memory…');
  try {
    const r = await api('/api/memory/generate', { method: 'POST' });
    showToast(`Generated memory for ${r.generated} groups`);
    loadMemory();
  } catch (e) {
    showToast(e.message, 'danger');
  } finally {
    loading(false);
  }
});

// ── Evaluate — Dynamic Form ────────────────────────────────────────────────────

let ptvCount = 0;
let oarCount = 0;
let beamCount = 0;

function addPTVRow() {
  ptvCount++;
  const id = `ptv-${ptvCount}`;
  const div = document.createElement('div');
  div.className = 'entry-row';
  div.id = id;
  div.innerHTML = `
    <div class="d-flex gap-2 align-items-center mb-1">
      <strong class="small">PTV ${ptvCount}</strong>
      <button type="button" class="btn btn-xs btn-outline-danger ms-auto" onclick="$('${id}').remove(); updateAutoFields()">✕</button>
    </div>
    <div class="row g-2">
      <div class="col-4"><input class="form-control form-control-sm ptv-name" placeholder="Name (e.g. PTV_High)" /></div>
      <div class="col-4"><input type="number" step="0.1" class="form-control form-control-sm ptv-vol" placeholder="Volume (cc)" /></div>
      <div class="col-4"><input type="number" step="0.1" class="form-control form-control-sm ptv-dose" placeholder="Rx Dose (Gy)" /></div>
    </div>
  `;
  $('ptv-container').appendChild(div);
}

function addOARRow() {
  oarCount++;
  const id = `oar-${oarCount}`;
  // Collect PTV names for overlap fields
  const ptvNames = [...document.querySelectorAll('.ptv-name')].map(e => e.value).filter(Boolean);
  const div = document.createElement('div');
  div.className = 'entry-row';
  div.id = id;
  div.innerHTML = `
    <div class="d-flex gap-2 align-items-center mb-1">
      <strong class="small">OAR ${oarCount}</strong>
      <button type="button" class="btn btn-xs btn-outline-danger ms-auto" onclick="$('${id}').remove()">✕</button>
    </div>
    <div class="row g-2">
      <div class="col-5"><input class="form-control form-control-sm oar-name" placeholder="OAR Name (e.g. Rectum)" /></div>
      <div class="col-3"><input type="number" step="0.1" class="form-control form-control-sm oar-vol" placeholder="Volume (cc)" /></div>
      ${ptvNames.map(name => `
        <div class="col-4">
          <input type="number" step="0.1" class="form-control form-control-sm oar-overlap"
            data-ptv="${name}" placeholder="Overlap w/ ${name} (cc)" />
        </div>
      `).join('')}
    </div>
  `;
  $('oar-container').appendChild(div);
}

function addBeamRow() {
  beamCount++;
  const id = `beam-${beamCount}`;
  const div = document.createElement('div');
  div.className = 'entry-row';
  div.id = id;
  div.innerHTML = `
    <div class="d-flex gap-2 align-items-center mb-1">
      <strong class="small">Beam / Arc ${beamCount}</strong>
      <button type="button" class="btn btn-xs btn-outline-danger ms-auto" onclick="$('${id}').remove()">✕</button>
    </div>
    <div class="row g-2">
      <div class="col-3"><input class="form-control form-control-sm beam-name" placeholder="Name" /></div>
      <div class="col-2"><input type="number" class="form-control form-control-sm beam-gantry" placeholder="Gantry°" /></div>
      <div class="col-2"><input type="number" class="form-control form-control-sm beam-couch" placeholder="Couch°" value="0" /></div>
      <div class="col-2"><input class="form-control form-control-sm beam-energy" placeholder="Energy" value="6" /></div>
      <div class="col-1"><input type="number" class="form-control form-control-sm beam-mu" placeholder="MU" /></div>
      <div class="col-2"><input type="number" class="form-control form-control-sm beam-segs" placeholder="Segments" /></div>
    </div>
  `;
  $('beam-container').appendChild(div);
}

$('btn-add-ptv').addEventListener('click', addPTVRow);
$('btn-add-oar').addEventListener('click', addOARRow);
$('btn-add-beam').addEventListener('click', addBeamRow);

// Auto-compute derived fields
function updateAutoFields() {
  const dose = parseFloat($('e-total-dose').value) || 0;
  const frac = parseInt($('e-fractions').value) || 0;
  const mus = parseFloat($('e-total-mu').value) || 0;
  const beams = parseInt($('e-beams').value) || 0;
  const segs = parseInt($('e-segments').value) || 0;

  $('e-dpf').value = (dose && frac) ? (dose / frac).toFixed(2) : '';
  $('e-mu-frac').value = (mus && frac) ? (mus / frac).toFixed(1) : '';
  $('e-mu-gy').value = (mus && dose) ? (mus / dose).toFixed(1) : '';
  $('e-seg-beam').value = (segs && beams) ? (segs / beams).toFixed(1) : '';
}

['e-total-dose', 'e-fractions', 'e-total-mu', 'e-beams', 'e-segments'].forEach(id => {
  $(id).addEventListener('input', updateAutoFields);
});

// ── Evaluate — Submission ─────────────────────────────────────────────────────

$('eval-form').addEventListener('submit', async e => {
  e.preventDefault();
  const dose = parseFloat($('e-total-dose').value);
  const fractions = parseInt($('e-fractions').value);
  const totalMu = parseFloat($('e-total-mu').value);
  const beams = parseInt($('e-beams').value);
  const segs = parseInt($('e-segments').value);

  // Collect PTVs
  const ptvs = [...document.querySelectorAll('.entry-row[id^="ptv-"]')].map(row => ({
    name: row.querySelector('.ptv-name').value || 'PTV',
    volume_cc: parseFloat(row.querySelector('.ptv-vol').value) || 0,
    prescribed_dose_gy: parseFloat(row.querySelector('.ptv-dose').value) || dose,
  }));

  // Collect OARs
  const oars = [...document.querySelectorAll('.entry-row[id^="oar-"]')].map(row => {
    const overlaps = {};
    row.querySelectorAll('.oar-overlap').forEach(inp => {
      if (inp.value) overlaps[inp.dataset.ptv] = parseFloat(inp.value);
    });
    return {
      name: row.querySelector('.oar-name').value || 'OAR',
      volume_cc: parseFloat(row.querySelector('.oar-vol').value) || 0,
      overlaps,
    };
  });

  // Collect beam details
  const beamDetails = [...document.querySelectorAll('.entry-row[id^="beam-"]')].map(row => ({
    name: row.querySelector('.beam-name').value || 'Beam',
    gantry_angle: parseFloat(row.querySelector('.beam-gantry').value) || 0,
    couch_angle: parseFloat(row.querySelector('.beam-couch').value) || 0,
    collimator_angle: 0,
    energy_mv: row.querySelector('.beam-energy').value || '6',
    mu: parseFloat(row.querySelector('.beam-mu').value) || 0,
    segments: parseInt(row.querySelector('.beam-segs').value) || 0,
  }));

  const payload = {
    plan_name: $('e-plan-name').value,
    disease_site: $('e-site').value,
    technique: $('e-technique').value,
    total_dose_gy: dose,
    fractions,
    total_beams: beams,
    total_segments: segs,
    total_mus: totalMu,
    ptvs,
    oars,
    beam_details: beamDetails,
  };

  loading(true, 'Running AI evaluation…');
  try {
    const result = await api('/api/evaluate', { method: 'POST', body: JSON.stringify(payload) });
    renderEvaluationResult(result);
    $('eval-placeholder').classList.add('d-none');
    $('eval-results').classList.remove('d-none');
    $('eval-results').scrollIntoView({ behavior: 'smooth', block: 'start' });
  } catch (e) {
    showToast('Evaluation failed: ' + e.message, 'danger');
  } finally {
    loading(false);
  }
});

function renderEvaluationResult(r) {
  // Banner
  const banner = $('overall-banner');
  const statusLabels = {
    ACCEPTABLE: { label: 'Acceptable', sub: 'All delivery parameters within expected range.', icon: 'bi-check-circle-fill', iconClass: 'text-success' },
    REVIEW_RECOMMENDED: { label: 'Review Recommended', sub: 'One or more metrics in caution zone — physicist should verify.', icon: 'bi-exclamation-triangle-fill', iconClass: 'text-warning' },
    FLAG: { label: 'Flag for Physics Review', sub: 'Significant deviation detected — do not treat without review.', icon: 'bi-x-octagon-fill', iconClass: 'text-danger' },
    INSUFFICIENT_DATA: { label: 'Insufficient Data', sub: 'Not enough historical plans to evaluate statistically.', icon: 'bi-question-circle-fill', iconClass: 'text-secondary' },
  };

  const info = statusLabels[r.overall_status] || statusLabels.INSUFFICIENT_DATA;
  banner.className = `overall-banner mb-4 ${r.overall_status}`;
  $('overall-icon').className = `bi ${info.icon} fs-1 ${info.iconClass}`;
  $('overall-label').textContent = info.label;
  $('overall-sub').textContent = `${r.disease_site} / ${r.technique} — ${r.historical_plan_count} historical plans | ${info.sub}`;

  // Metric table
  const metricLabels = {
    mu_efficiency: 'MU Efficiency (MU/Gy)',
    mus_per_fraction: 'MUs per Fraction',
    total_beams: 'Total Beams',
    total_segments: 'Total Segments',
    segments_per_beam: 'Segments per Beam',
    mus_per_segment: 'MUs per Segment',
  };

  const tbody = $('metric-tbody');
  if (!r.metrics || !Object.keys(r.metrics).length) {
    tbody.innerHTML = '<tr><td colspan="6" class="text-center text-muted">No statistical data available.</td></tr>';
  } else {
    tbody.innerHTML = Object.entries(r.metrics).map(([key, m]) => {
      const zStr = (m.z_score > 0 ? '+' : '') + m.z_score.toFixed(2);
      const p5p95 = (m.p5 != null && m.p95 != null) ? `${fmt(m.p5, 0)} – ${fmt(m.p95, 0)}` : '—';
      const dec = ['total_beams', 'total_segments', 'total_mus'].includes(key) ? 0 : 1;
      return `
        <tr>
          <td class="fw-semibold">${metricLabels[key] || key}</td>
          <td class="fw-bold text-primary">${fmt(m.value, dec)}</td>
          <td>${fmt(m.mean, dec)} ± ${fmt(m.std, dec)}</td>
          <td>${p5p95}</td>
          <td>${zStr}</td>
          <td><span class="badge-${m.status}">${m.status === 'NORMAL' ? '✓ Normal' : m.status === 'CAUTION' ? '⚠ Caution' : '✗ Flag'}</span></td>
        </tr>
      `;
    }).join('');
  }

  // AI narrative
  $('ai-narrative').textContent = r.ai_analysis || 'No AI analysis available.';

  // Similar plans
  const simTbody = $('similar-tbody');
  if (r.similar_plans && r.similar_plans.length) {
    simTbody.innerHTML = r.similar_plans.map(p => `
      <tr>
        <td>${p.plan_name}</td>
        <td>${p.total_dose_gy} / ${p.fractions}</td>
        <td>${p.total_beams}</td>
        <td>${fmtInt(p.total_segments)}</td>
        <td>${fmtInt(p.total_mus)}</td>
        <td>${fmt(p.mu_efficiency, 0)}</td>
      </tr>
    `).join('');
    $('similar-card').classList.remove('d-none');
  } else {
    $('similar-card').classList.add('d-none');
  }
}

// ── Catalog (autocomplete lists) ──────────────────────────────────────────────

async function populateCatalogLists() {
  try {
    const catalog = await api('/api/catalog');
    const setList = (listId, items) => {
      const el = $(listId);
      if (el) el.innerHTML = items.map(s => `<option value="${s}">`).join('');
    };
    const allSites = [...new Set([...catalog.disease_sites, ...catalog.common_sites])].sort();
    const allTechs = [...new Set([...catalog.techniques, ...catalog.common_techniques])].sort();

    setList('site-list', allSites);
    setList('technique-list', allTechs);
    setList('ap-site-list', allSites);
    setList('ap-tech-list', allTechs);

    // Filter dropdowns
    const filterSite = $('filter-site');
    const filterTech = $('filter-technique');
    filterSite.innerHTML = '<option value="">All Disease Sites</option>' + catalog.disease_sites.map(s => `<option>${s}</option>`).join('');
    filterTech.innerHTML = '<option value="">All Techniques</option>' + catalog.techniques.map(t => `<option>${t}</option>`).join('');
  } catch (e) {
    console.warn('Catalog fetch failed:', e);
  }
}

// ── API health check ──────────────────────────────────────────────────────────

async function checkAPIStatus() {
  try {
    await api('/api/stats');
    $('api-status').textContent = 'API Connected';
    $('api-status').className = 'badge bg-success';
  } catch {
    $('api-status').textContent = 'API Offline';
    $('api-status').className = 'badge bg-danger';
  }
}

// ── Init ──────────────────────────────────────────────────────────────────────

(async () => {
  // Start with one default PTV row
  addPTVRow();

  await checkAPIStatus();
  await populateCatalogLists();
  loadDashboard();
})();
