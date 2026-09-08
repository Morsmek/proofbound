let currentRun = null;
let busy = false;
const el = id => document.getElementById(id);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const requestHeaders = () => ({'Content-Type':'application/json', ...(el('access-key').value ? {Authorization:'Bearer ' + el('access-key').value} : {})});
const safeURL = value => /^https?:\/\//i.test(value) ? esc(value) : '#';
async function api(path, method = 'GET', body) {
  const response = await fetch('/api' + path, {method, headers: requestHeaders(), ...(body === undefined ? {} : {body: JSON.stringify(body)})});
  let data;
  try { data = await response.json(); } catch { throw Error(`Server returned HTTP ${response.status}`); }
  if (!response.ok) throw Error(typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail || data));
  return data;
}
async function task(fn) {
  if (busy) return;
  busy = true;
  el('error-message').textContent = '';
  document.querySelectorAll('button').forEach(b => b.disabled = true);
  try { await fn(); } catch (error) { el('error-message').textContent = error.message; }
  finally { busy = false; document.querySelectorAll('button').forEach(b => b.disabled = false); }
}
function switchTab(tabId) {
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
  el(`tab-btn-${tabId}`).classList.add('active'); el(`tab-${tabId}`).classList.add('active');
  if (tabId === 'memory') task(loadMemories);
  if (tabId === 'audit') task(loadAuditRuns);
}
function showRun(run) { currentRun = run; renderRun(run); }
function submitIntent() { return task(async () => {
  const intent = el('intent-input').value.trim(); if (!intent) return;
  showRun(await api('/runs/', 'POST', {intent}));
  if (currentRun.approval_state === 'AUTO_APPROVED') await executeCurrentRun();
}); }
function renderRun(run) {
  el('run-container').style.display = 'block';
  el('run-id-display').textContent = run.id; el('run-intent-display').textContent = run.intent;
  el('risk-badge').className = `badge badge-${run.risk_level.toLowerCase()}`;
  el('risk-badge').textContent = `${run.risk_level} RISK`;
  const failed = run.plan_steps.some(s => s.status === 'failed');
  el('state-badge').textContent = failed ? 'FAILED' : run.completed_at && run.approval_state !== 'REJECTED' ? 'COMPLETED' : run.approval_state;
  el('step-list').innerHTML = run.plan_steps.map(s => `<div class="step-item"><div><h4>Step ${s.step_index}: ${esc(s.title)}</h4><p>${esc(s.description)}</p><pre>${esc(JSON.stringify(s.parameters, null, 2))}</pre><p>${esc(s.error || '')}</p>${s.result?.content !== undefined ? `<pre>${esc(s.result.content)}</pre>` : ''}${s.result?.matches ? `<pre>${esc(s.result.matches.join('\n') || 'No matching files.')}</pre>` : ''}</div><span class="badge">${esc(s.status)}</span></div>`).join('');
  el('approval-box').style.display = run.approval_state === 'PENDING' ? 'block' : 'none';
  el('approval-scopes').textContent = run.requested_scopes.join(', ');
  el('citation-list').innerHTML = run.citations.map(c => `<div class="citation-card"><a href="${safeURL(c.source_uri)}" target="_blank" rel="noopener noreferrer">${esc(c.title)}</a><p>${esc(c.snippet)}</p><small>Source excerpt · Hash: ${esc(c.content_hash)}</small></div>`).join('') || '<p>No source excerpts captured.</p>';
  el('artifact-list').innerHTML = run.artifacts.map(a => `<div class="citation-card"><h4>${esc(a.name)}</h4><pre>${esc(a.content_preview)}</pre><button data-download="/api/runs/${encodeURIComponent(run.id)}/artifacts/${encodeURIComponent(a.id)}" data-name="${esc(a.name)}">Download</button></div>`).join('') || '<p>No artifacts yet.</p>';
  el('artifact-list').querySelectorAll('button').forEach(b => b.onclick = () => task(() => download(b.dataset.download, b.dataset.name)));
  el('proposal-list').innerHTML = run.memory_updates.map(p => `<div class="citation-card"><p>${esc(p.proposed_content)}</p><small>${esc(p.provenance_source)} · ${esc(p.status)}</small>${p.status === 'PENDING' ? `<p><button data-proposal="${esc(p.proposal_id)}" data-decision="approve">Accept</button> <button data-proposal="${esc(p.proposal_id)}" data-decision="reject">Reject</button></p>` : ''}</div>`).join('') || '<p>No memory proposals.</p>';
  el('proposal-list').querySelectorAll('button').forEach(b => b.onclick = () => task(async () => showRun(await api(`/runs/${run.id}/proposals/${b.dataset.proposal}/decision`, 'POST', {decision:b.dataset.decision}))));
  el('rollback-run-btn').hidden = !run.plan_steps.some(s => s.result && 'previous_content' in s.result) || !!run.rollback_or_recovery;
  el('execute-run-btn').hidden = !!run.completed_at || !['APPROVED', 'AUTO_APPROVED'].includes(run.approval_state);
  el('event-logs').innerHTML = run.events.map(e => `<div class="log-line"><span class="log-time">${esc(e.timestamp)}</span> <span class="log-type">${esc(e.event_type)}</span>: ${esc(e.message)}</div>`).join('');
}
function handleApproval(decision) { return task(async () => {
  if (!currentRun) return;
  showRun(await api(`/runs/${currentRun.id}/decision`, 'POST', {decision}));
  if (decision === 'approve') await executeCurrentRun();
}); }
async function executeCurrentRun() { if (currentRun) showRun(await api(`/runs/${currentRun.id}/execute`, 'POST')); }
function rollbackRun() { return task(async () => showRun(await api(`/runs/${currentRun.id}/rollback`, 'POST'))); }
async function loadMemories() {
  const facts = await api('/memory/');
  el('memory-fact-list').innerHTML = facts.map(f => `<div class="step-item"><div><h4>${esc(f.content)}</h4><p>Source: ${esc(f.provenance_source)}</p><small>Run: ${esc(f.provenance_run_id)}</small></div><div><button data-id="${esc(f.id)}" data-action="edit">Edit</button> <button data-id="${esc(f.id)}" data-action="rollback">Rollback</button> <button data-id="${esc(f.id)}" data-action="delete">Delete</button></div></div>`).join('') || '<p>No accepted memories yet. Accept a proposal from a completed run.</p>';
  el('memory-fact-list').querySelectorAll('button').forEach(b => b.onclick = () => task(async () => {
    const id = b.dataset.id, action = b.dataset.action;
    if (action === 'edit') { const content = prompt('Edit memory', facts.find(f => f.id === id).content); if (content === null) return; await api(`/memory/${id}`, 'PUT', {content}); }
    if (action === 'rollback') await api(`/memory/${id}/rollback`, 'POST', {});
    if (action === 'delete' && confirm('Delete this memory?')) await api(`/memory/${id}`, 'DELETE');
    await loadMemories();
  }));
}
async function loadAuditRuns() {
  const runs = await api('/audit/');
  el('audit-run-list').innerHTML = runs.map(r => `<div class="step-item"><div><h4>${esc(r.intent)}</h4><p>${esc(r.id)} · ${esc(r.risk_level)} · ${esc(r.approval_state)}</p></div><div><button data-id="${esc(r.id)}" data-action="open">Open</button> <button data-id="${esc(r.id)}" data-action="replay">Verify event hashes</button> <button data-id="${esc(r.id)}" data-action="export">Export MD</button></div></div>`).join('') || '<p>No runs yet.</p>';
  el('audit-run-list').querySelectorAll('button').forEach(b => b.onclick = () => task(async () => {
    if (b.dataset.action === 'open') { switchTab('console'); showRun(await api(`/runs/${b.dataset.id}`)); }
    else if (b.dataset.action === 'export') await download(`/api/audit/${b.dataset.id}/export/markdown`, `${b.dataset.id}.md`);
    else { const result = await api(`/audit/${b.dataset.id}/replay`); alert(`Event hash check: ${result.is_identical ? 'PASS' : 'FAIL'} (${result.replayed_events}/${result.total_events})`); }
  }));
}
function triggerBenchmark() { return task(async () => {
  el('bench-summary').textContent = 'Running isolated fixture checks…';
  const data = await api('/benchmark/run', 'POST');
  el('bench-summary').textContent = `${data.passed_tasks}/${data.total_tasks} checks passed (${data.total_duration_ms}ms). Uses deterministic fixtures, not live web research.`;
  el('bench-task-list').innerHTML = data.results.map(t => `<div class="step-item"><div><h4>${esc(t.name)}</h4><p>${esc(t.details)}</p></div><span class="badge">${t.passed ? 'PASS' : 'FAIL'}</span></div>`).join('');
}); }

async function download(path, name) {
  const response = await fetch(path, {headers: requestHeaders()});
  if (!response.ok) throw Error('Download failed: ' + response.status);
  const url = URL.createObjectURL(await response.blob());
  const anchor = document.createElement('a'); anchor.href = url; anchor.download = name; anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
