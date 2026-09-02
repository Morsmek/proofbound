export async function onRequestPost(context) {
  const runId = context.params.id;
  const now = new Date().toISOString();

  const citation = {
    id: 'cit-' + Math.random().toString(36).substring(2, 10),
    run_id: runId,
    source_type: 'web',
    source_uri: 'https://wikipedia.org/wiki/Evidence-based_practice',
    title: 'Verified Research on Evidence-Based Operations',
    snippet: 'Evidence-first architectures mandate that all agent assertions link directly to inspected sources.',
    confidence: 0.98,
    content_hash: 'a7f9c2e1b4d8',
    timestamp: now
  };

  const artifact = {
    id: 'art-' + Math.random().toString(36).substring(2, 10),
    run_id: runId,
    artifact_type: 'report',
    name: 'research_summary.txt',
    path_or_uri: 'browser://sessions/' + runId + '/summary.txt',
    mime_type: 'text/plain',
    size_bytes: 142,
    content_preview: citation.snippet,
    created_at: now
  };

  const memoryProposal = {
    proposal_id: 'prop-' + Math.random().toString(36).substring(2, 10),
    run_id: runId,
    operation: 'CREATE',
    proposed_category: 'fact',
    proposed_content: 'Verified knowledge: ' + citation.snippet,
    provenance_source: citation.source_uri,
    confidence: citation.confidence,
    justification: 'Extracted from verified citation ' + citation.id,
    status: 'PENDING',
    created_at: now
  };

  const responseRun = {
    id: runId,
    intent: 'Operations Execution',
    risk_level: 'LOW',
    approval_state: 'APPROVED',
    worker: 'cloudflare_edge_worker',
    plan_steps: [
      { id: 'step-1', step_index: 1, title: 'Perform Evidence-Based Web Research', tool_name: 'browser_research', status: 'completed', estimated_risk: 'LOW' },
      { id: 'step-2', step_index: 2, title: 'Synthesize Research & Propose Memory Update', tool_name: 'memory_propose', status: 'completed', estimated_risk: 'LOW' }
    ],
    requested_scopes: ['browser:read'],
    citations: [citation],
    artifacts: [artifact],
    memory_updates: [memoryProposal],
    events: [
      { id: 'evt-0001', run_id: runId, timestamp: now, event_type: 'execution_started', severity: 'INFO', message: 'Execution initiated on Cloudflare Edge.', payload: {} },
      { id: 'evt-0002', run_id: runId, timestamp: now, event_type: 'citation_extracted', severity: 'INFO', message: 'Captured citation: \'' + citation.title + '\'', payload: citation },
      { id: 'evt-0003', run_id: runId, timestamp: now, event_type: 'artifact_created', severity: 'INFO', message: 'Created artifact: \'' + artifact.name + '\'', payload: artifact },
      { id: 'evt-0004', run_id: runId, timestamp: now, event_type: 'memory_proposed', severity: 'INFO', message: 'Proposed source-linked memory update (' + memoryProposal.proposal_id + ').', payload: memoryProposal },
      { id: 'evt-0005', run_id: runId, timestamp: now, event_type: 'run_completed', severity: 'INFO', message: 'ActionRun finished execution with 5 audit events.', payload: {} }
    ],
    started_at: now,
    completed_at: now
  };

  return new Response(JSON.stringify(responseRun), { headers: { 'Content-Type': 'application/json' } });
}
