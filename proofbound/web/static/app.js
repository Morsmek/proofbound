let currentRun = null;

function switchTab(tabId) {
  document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
  
  document.getElementById(`tab-btn-${tabId}`).classList.add('active');
  document.getElementById(`tab-${tabId}`).classList.add('active');

  if (tabId === 'memory') loadMemories();
  if (tabId === 'audit') loadAuditRuns();
}

async function submitIntent() {
  const input = document.getElementById('intent-input');
  const intent = input.value.trim();
  if (!intent) return;

  const res = await fetch('/api/runs/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ intent })
  });
  
  const run = await res.json();
  currentRun = run;
  renderRun(run);
}

function renderRun(run) {
  document.getElementById('run-container').style.display = 'block';
  document.getElementById('run-id-display').innerText = run.id;
  document.getElementById('run-intent-display').innerText = run.intent;
  
  const riskBadge = document.getElementById('risk-badge');
  riskBadge.className = `badge badge-${run.risk_level.toLowerCase()}`;
  riskBadge.innerText = `${run.risk_level} RISK`;

  const stateBadge = document.getElementById('state-badge');
  stateBadge.innerText = run.approval_state;

  const stepList = document.getElementById('step-list');
  stepList.innerHTML = run.plan_steps.map(s => `
    <div class="step-item">
      <div class="step-info">
        <h4>Step ${s.step_index}: ${s.title}</h4>
        <p>Tool: <code>${s.tool_name}</code> | ${s.description}</p>
      </div>
      <div>
        <span class="badge badge-low">${s.status}</span>
      </div>
    </div>
  `).join('');

  const approvalBox = document.getElementById('approval-box');
  if (run.approval_state === 'PENDING') {
    approvalBox.style.display = 'block';
    document.getElementById('approval-scopes').innerText = run.requested_scopes.join(', ') || 'None';
  } else {
    approvalBox.style.display = 'none';
  }

  const citList = document.getElementById('citation-list');
  if (run.citations && run.citations.length > 0) {
    citList.innerHTML = run.citations.map(c => `
      <div class="citation-card">
        <a href="${c.source_uri}" target="_blank" class="citation-title">${c.title}</a>
        <div class="citation-snippet">"${c.snippet}"</div>
        <div style="font-size: 0.75rem; color: #9ca3af; margin-top: 4px;">
          Confidence: ${(c.confidence * 100).toFixed(0)}% | Hash: <code>${c.content_hash}</code>
        </div>
      </div>
    `).join('');
  } else {
    citList.innerHTML = '<p style="color: var(--text-muted); font-size: 0.9rem;">No citations extracted yet.</p>';
  }

  const logBox = document.getElementById('event-logs');
  logBox.innerHTML = run.events.map(e => `
    <div class="log-line">
      <span class="log-time">[${e.timestamp.split('T')[1].split('.')[0]}]</span>
      <span class="log-type">${e.event_type}</span>: ${e.message}
    </div>
  `).join('');
}

async function handleApproval(decision) {
  if (!currentRun) return;
  const res = await fetch(`/api/runs/${currentRun.id}/decision`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ decision, approver: 'web-user' })
  });
  const updated = await res.json();
  currentRun = updated;
  renderRun(updated);

  if (decision === 'approve') {
    executeCurrentRun();
  }
}

async function executeCurrentRun() {
  if (!currentRun) return;
  const res = await fetch(`/api/runs/${currentRun.id}/execute`, {
    method: 'POST'
  });
  const completed = await res.json();
  currentRun = completed;
  renderRun(completed);
}

async function loadMemories() {
  const res = await fetch('/api/memory/');
  const facts = await res.json();
  const list = document.getElementById('memory-fact-list');
  list.innerHTML = facts.map(f => `
    <div class="step-item" style="align-items: flex-start;">
      <div>
        <h4 style="color: var(--accent-cyan);">${f.category.toUpperCase()}: ${f.content}</h4>
        <p style="margin-top: 4px;">Provenance Run: <code>${f.provenance_run_id}</code> | Source: <em>${f.provenance_source}</em></p>
        <p style="font-size: 0.75rem; color: #9ca3af;">Confidence: ${(f.confidence * 100).toFixed(0)}% | Updated: ${f.updated_at}</p>
      </div>
      <div style="display: flex; gap: 8px;">
        <button class="primary-btn" style="padding: 0.35rem 0.75rem; font-size: 0.8rem;" onclick="rollbackMemory('${f.id}')">Rollback</button>
      </div>
    </div>
  `).join('');
}

async function rollbackMemory(factId) {
  await fetch(`/api/memory/${factId}/rollback`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({}) });
  loadMemories();
}

async function loadAuditRuns() {
  const res = await fetch('/api/audit/');
  const runs = await res.json();
  const list = document.getElementById('audit-run-list');
  list.innerHTML = runs.map(r => `
    <div class="step-item">
      <div>
        <h4><code>${r.id}</code> - ${r.intent}</h4>
        <p>Risk: <span class="badge badge-${r.risk_level.toLowerCase()}">${r.risk_level}</span> | Approval: ${r.approval_state}</p>
      </div>
      <div style="display: flex; gap: 8px;">
        <button class="primary-btn" style="padding: 0.35rem 0.75rem; font-size: 0.8rem;" onclick="replayRun('${r.id}')">Replay Deterministic</button>
        <a href="/api/audit/${r.id}/export/markdown" target="_blank" class="tab-btn" style="border: 1px solid var(--border-color); text-decoration: none;">Export MD</a>
      </div>
    </div>
  `).join('');
}

async function replayRun(runId) {
  const res = await fetch(`/api/audit/${runId}/replay`);
  const replay = await res.json();
  alert(`Replay Result for ${runId}:\nDeterministic Match: ${replay.is_identical}\nReplayed ${replay.replayed_events}/${replay.total_events} events (${(replay.match_rate*100).toFixed(1)}%)`);
}

async function triggerBenchmark() {
  const btn = document.getElementById('bench-run-btn');
  btn.innerText = 'Running 10-Task Verification Matrix...';
  btn.disabled = true;

  const res = await fetch('/api/benchmark/run', { method: 'POST' });
  const data = await res.json();
  
  btn.innerText = 'Run Benchmark Matrix';
  btn.disabled = false;

  document.getElementById('bench-summary').innerHTML = `
    <div style="font-size: 1.1rem; font-weight: bold; color: var(--accent-green); margin-bottom: 1rem;">
      Pass Rate: ${data.pass_rate}% (${data.passed_tasks}/${data.total_tasks} passed in ${data.total_duration_ms}ms)
    </div>
  `;

  const list = document.getElementById('bench-task-list');
  list.innerHTML = data.results.map(t => `
    <div class="step-item">
      <div>
        <h4>Task ${t.task_id}: ${t.name} <span style="font-size: 0.75rem; color: #9ca3af;">[${t.category}]</span></h4>
        <p>${t.details}</p>
      </div>
      <div>
        <span class="badge ${t.passed ? 'badge-low' : 'badge-critical'}">${t.passed ? 'PASS' : 'FAIL'}</span>
      </div>
    </div>
  `).join('');
}
