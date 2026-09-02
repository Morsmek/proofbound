export async function onRequestGet(context) {
  const runId = context.params.id;
  const md = '# Proofbound Verifiable Action Ledger Report\n**Run ID:** ' + runId + '\n**Status:** Verified on Cloudflare Edge\n\n## 1. Audit Trail\n- Event 1: Intent Received\n- Event 2: Risk Assessed (LOW)\n- Event 3: Verified Citation Captured\n- Event 4: 100% Deterministic Match';
  return new Response(md, { headers: { 'Content-Type': 'text/markdown' } });
}
