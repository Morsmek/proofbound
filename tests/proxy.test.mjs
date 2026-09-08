import { readFile } from 'node:fs/promises';
import test from 'node:test';
import assert from 'node:assert/strict';
const source = await readFile(new URL('../functions/api/[[path]].js', import.meta.url), 'utf8');
const { onRequest } = await import('data:text/javascript;base64,' + Buffer.from(source).toString('base64'));
test('proxy fails clearly when backend is missing', async () => {
  assert.equal((await onRequest({request:new Request('https://site.test/api/runs/'), env:{}})).status, 503);
});
test('proxy forwards path, payload and authorization to real backend', async () => {
  const original = globalThis.fetch;
  globalThis.fetch = async (url, options) => {
    assert.equal(String(url), 'https://backend.test/api/runs/');
    assert.equal(options.headers.get('authorization'), 'Bearer key');
    assert.equal(options.headers.get('cookie'), null);
    return Response.json({id:'real-run'});
  };
  try {
    const response = await onRequest({request:new Request('https://site.test/api/runs/', {method:'POST', body:'{}', headers:{Authorization:'Bearer key',Cookie:'private'}}), env:{PROOFBOUND_BACKEND_URL:'https://backend.test'}});
    assert.deepEqual(await response.json(), {id:'real-run'});
    assert.equal(response.headers.get('cache-control'), 'no-store');
  } finally { globalThis.fetch = original; }
});
