export async function onRequestPost(context) {
  const runId = context.params.id;
  const req = await context.request.json();
  const now = new Date().toISOString();
  
  return new Response(JSON.stringify({
    id: runId,
    approval_state: req.decision === 'approve' ? 'APPROVED' : 'REJECTED',
    events: [
      { id: 'evt-0004', run_id: runId, timestamp: now, event_type: req.decision === 'approve' ? 'approval_granted' : 'approval_rejected', severity: 'INFO', message: 'Approval ' + req.decision + ' by user.', payload: {} }
    ]
  }), { headers: { 'Content-Type': 'application/json' } });
}
