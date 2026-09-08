// Cloudflare Pages forwards API calls to the persistent Python service.
// Set PROOFBOUND_BACKEND_URL to its HTTPS origin. No simulated responses.
export async function onRequest({ request, env }) {
  const json = (detail, status) => Response.json({ detail }, { status });
  if (!env.PROOFBOUND_BACKEND_URL) return json('Configure PROOFBOUND_BACKEND_URL to connect the Proofbound backend.', 503);
  let origin;
  try { origin = new URL(env.PROOFBOUND_BACKEND_URL); } catch { return json('Invalid backend URL configuration.', 503); }
  const incoming = new URL(request.url);
  if (origin.protocol !== 'https:' || origin.origin === incoming.origin || origin.username || origin.password) return json('Backend must be a separate HTTPS origin.', 503);
  const target = new URL(incoming.pathname + incoming.search, origin.origin);
  const headers = new Headers();
  for (const name of ['content-type', 'accept', 'authorization']) {
    if (request.headers.has(name)) headers.set(name, request.headers.get(name));
  }
  try {
    const response = await fetch(target, { method: request.method, headers,
      body: ['GET','HEAD'].includes(request.method) ? undefined : request.body,
      redirect: 'manual' });
    if (response.status >= 300 && response.status < 400) return json('Backend returned an unexpected redirect.', 502);
    const outgoing = new Headers();
    for (const name of ['content-type', 'content-disposition']) {
      if (response.headers.has(name)) outgoing.set(name, response.headers.get(name));
    }
    outgoing.set('Cache-Control', 'no-store');
    return new Response(response.body, { status: response.status, headers: outgoing });
  } catch { return json('Proofbound backend is unavailable.', 502); }
}
