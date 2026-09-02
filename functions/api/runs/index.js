export async function onRequestPost(context) {
  const req = await context.request.json();
  const intent = req.intent || 'Standard operations';
  const lower = intent.toLowerCase();
  
  let riskLevel = 'LOW';
  let scopes = ['workspace:read'];
  let reqApproval = false;
  
  if (lower.includes('rm -rf') || lower.includes('format') || lower.includes('delete') || lower.includes('drop')) {
    riskLevel = 'CRITICAL';
    scopes = ['system:admin', 'workspace:delete'];
    reqApproval = true;
  } else if (lower.includes('patch') || lower.includes('edit') || lower.includes('write')) {
    riskLevel = 'HIGH';
    scopes = ['workspace:write', 'workspace:read'];
    reqApproval = true;
  } else if (lower.includes('draft') || lower.includes('email') || lower.includes('message')) {
    riskLevel = 'MEDIUM';
    scopes = ['draft:create'];
    reqApproval = true;
  } else if (lower.includes('research') || lower.includes('browse') || lower.includes('web')) {
    riskLevel = 'LOW';
    scopes = ['browser:read'];
  }

  const isBlocked = riskLevel === 'CRITICAL' && (lower.includes('rm -rf') || lower.includes('format'));
  const runId = 'run-' + Math.random().toString(36).substring(2, 12);
  const now = new Date().toISOString();

  let steps = [];
  if (scopes.includes('draft:create')) {
    steps.push({
      id: 'step-1',
      step_index: 1,
      title: 'Stage Non-Destructive Reversible Draft',
      description: 'Compose email/message body and stage without triggering direct transmission.',
      tool_name: 'draft_create_email',
      parameters: { recipient: 'team@proofbound.org', subject: 'Ops Brief', body: 'Draft generated for: ' + intent },
      estimated_risk: 'MEDIUM',
      status: 'pending'
    });
  } else if (scopes.includes('workspace:write')) {
    steps.push({
      id: 'step-1',
      step_index: 1,
      title: 'Search Workspace Files',
      description: 'Locate target file in sandboxed workspace directory.',
      tool_name: 'workspace_search',
      parameters: { pattern: 'config' },
      estimated_risk: 'LOW',
      status: 'pending'
    });
    steps.push({
      id: 'step-2',
      step_index: 2,
      title: 'Apply Unified File Patch with Reversible Backup',
      description: 'Write modifications to target file and record diff for rollback.',
      tool_name: 'workspace_write_file',
      parameters: { file_path: './workspace_sandbox/config.txt', content: '# Proofbound Config\nstatus=active\n' },
      estimated_risk: 'HIGH',
      status: 'pending'
    });
  } else {
    steps.push({
      id: 'step-1',
      step_index: 1,
      title: 'Perform Evidence-Based Web Research',
      description: 'Query authorized domains and extract source citations.',
      tool_name: 'browser_research',
      parameters: { query: intent, url: 'https://wikipedia.org/wiki/Evidence-based_practice' },
      estimated_risk: 'LOW',
      status: 'pending'
    });
    steps.push({
      id: 'step-2',
      step_index: 2,
      title: 'Synthesize Research & Propose Memory Update',
      description: 'Extract verified factual findings and formulate source-linked memory proposal.',
      tool_name: 'memory_propose',
      parameters: { topic: intent },
      estimated_risk: 'LOW',
      status: 'pending'
    });
  }

  const run = {
    id: runId,
    user_id: req.user_id || 'web-user',
    intent: intent,
    plan_steps: steps,
    requested_scopes: scopes,
    risk_level: riskLevel,
    approval_state: isBlocked ? 'REJECTED' : (reqApproval ? 'PENDING' : 'AUTO_APPROVED'),
    worker: 'cloudflare_edge_worker',
    inputs_hash: 'sha256_' + Math.random().toString(36).substring(2, 16),
    events: [
      { id: 'evt-0001', run_id: runId, timestamp: now, event_type: 'intent_received', severity: 'INFO', message: 'Received intent: \'' + intent + '\'', payload: { intent } },
      { id: 'evt-0002', run_id: runId, timestamp: now, event_type: 'risk_assessed', severity: riskLevel === 'HIGH' || riskLevel === 'CRITICAL' ? 'WARNING' : 'INFO', message: 'Evaluated as ' + riskLevel + '. Scopes: ' + scopes.join(', '), payload: { riskLevel, scopes } },
      isBlocked ? { id: 'evt-0003', run_id: runId, timestamp: now, event_type: 'execution_blocked', severity: 'CRITICAL', message: 'Execution blocked by Policy Engine.', payload: {} } : null
    ].filter(Boolean),
    artifacts: [],
    citations: [],
    memory_updates: [],
    started_at: now,
    completed_at: isBlocked ? now : null
  };

  return new Response(JSON.stringify(run), { headers: { 'Content-Type': 'application/json' } });
}
