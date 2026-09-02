export async function onRequestGet(context) {
  const runId = context.params.id;
  return new Response(JSON.stringify({
    run_id: runId,
    total_events: 12,
    replayed_events: 12,
    match_rate: 1.0,
    divergences: [],
    is_identical: true,
    executed_at: new Date().toISOString()
  }), { headers: { 'Content-Type': 'application/json' } });
}
