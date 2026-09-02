export async function onRequestGet(context) {
  const now = new Date().toISOString();
  const defaultFacts = [
    {
      id: 'mem-01',
      category: 'fact',
      content: 'Proofbound requires verified citations and deterministic ledger logging for all operations.',
      provenance_run_id: 'run-init-01',
      provenance_source: 'https://docs.proofbound.org/spec',
      confidence: 0.99,
      status: 'accepted',
      tags: ['architecture', 'policy'],
      revisions: [],
      created_at: now,
      updated_at: now
    },
    {
      id: 'mem-02',
      category: 'preference',
      content: 'User prefers reversible staged drafts over direct uncontrolled transmissions.',
      provenance_run_id: 'run-init-02',
      provenance_source: 'user_policy',
      confidence: 1.0,
      status: 'accepted',
      tags: ['preference', 'safety'],
      revisions: [],
      created_at: now,
      updated_at: now
    }
  ];
  return new Response(JSON.stringify(defaultFacts), { headers: { 'Content-Type': 'application/json' } });
}
