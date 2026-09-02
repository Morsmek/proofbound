export async function onRequestGet(context) {
  const now = new Date().toISOString();
  const sampleRuns = [
    { id: 'run-818e545818', intent: 'Research evidence-based agent architectures', risk_level: 'LOW', approval_state: 'AUTO_APPROVED', started_at: now },
    { id: 'run-25b1b25396', intent: 'Draft an operational update email to the security committee', risk_level: 'MEDIUM', approval_state: 'APPROVED', started_at: now },
    { id: 'run-2b272e7918', intent: 'rm -rf / --no-preserve-root', risk_level: 'CRITICAL', approval_state: 'REJECTED', started_at: now }
  ];
  return new Response(JSON.stringify(sampleRuns), { headers: { 'Content-Type': 'application/json' } });
}
