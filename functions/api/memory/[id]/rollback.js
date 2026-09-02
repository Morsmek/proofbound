export async function onRequestPost(context) {
  const factId = context.params.id;
  const now = new Date().toISOString();
  return new Response(JSON.stringify({
    id: factId,
    category: 'fact',
    content: 'Reverted: Proofbound requires verified citations and deterministic ledger logging for all operations.',
    provenance_run_id: 'run-rollback',
    provenance_source: 'rollback_engine',
    confidence: 1.0,
    status: 'edited',
    updated_at: now
  }), { headers: { 'Content-Type': 'application/json' } });
}
