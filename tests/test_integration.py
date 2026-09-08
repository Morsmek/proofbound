from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from proofbound.core.agent import ProofboundAgent
from proofbound.core.approval_gate import ApprovalGate
from proofbound.core.policy_engine import PolicyEngine
from proofbound.models.action_run import ApprovalState
from proofbound.workers.browser_worker import BrowserWorker
from proofbound.config import Settings


@pytest.fixture
def client(monkeypatch):
    from proofbound.web.app import app
    from proofbound.web.routes import runs, memory, audit
    agent = ProofboundAgent(browser_transport=httpx.MockTransport(lambda r: httpx.Response(200, text='<title>Source</title><p>Inspected source text</p>')))
    monkeypatch.setattr(runs, 'agent', agent)
    monkeypatch.setattr(memory, 'memory_engine', agent.memory)
    monkeypatch.setattr(audit, 'ledger', agent.ledger)
    with TestClient(app) as client:
        yield client


def create(client, intent):
    response = client.post('/api/runs/', json={'intent': intent})
    assert response.status_code == 200
    return response.json()


def test_dashboard_assets_and_health(client):
    for path in ['/', '/app.js', '/style.css', '/api/health']:
        assert client.get(path).status_code == 200
    with client.websocket_connect('/ws/events') as websocket:
        websocket.send_text('hello')
        assert websocket.receive_json()['status'] == 'connected'


def test_file_approval_execute_download_rollback(client):
    run = create(client, 'Write file report.txt content: hello world')
    base = f'/api/runs/{run["id"]}'
    assert run['approval_state'] == 'PENDING'
    assert client.post(base + '/execute').status_code == 403
    assert client.post(base + '/decision', json={'decision':'approve'}).status_code == 200
    result = client.post(base + '/execute').json()
    assert result['plan_steps'][-1]['status'] == 'completed'
    path = Path(result['plan_steps'][-1]['result']['file_path'])
    assert path.read_text() == 'hello world'
    assert client.post(base + '/execute').json() == result
    artifact = result['artifacts'][0]
    assert 'hello world' in client.get(base + '/artifacts/' + artifact['id']).text
    path.write_text('newer work')
    assert client.post(base + '/rollback').status_code == 409
    assert path.read_text() == 'newer work'
    path.write_text('hello world')
    assert client.post(base + '/rollback').status_code == 200
    assert not path.exists()


def test_blocked_approval_and_missing_runs(client):
    run = create(client, 'rm -rf /')
    base = f'/api/runs/{run["id"]}'
    assert client.post(base + '/decision', json={'decision':'approve'}).status_code == 409
    assert client.post(base + '/execute').status_code == 403
    assert client.post('/api/runs/missing/execute').status_code == 404
    assert client.post('/api/runs/', json={'intent':''}).status_code == 422


def test_source_memory_full_lifecycle(client):
    run = create(client, 'Browse https://example.com/source')
    base = f'/api/runs/{run["id"]}'
    result = client.post(base + '/execute').json()
    assert result['citations'] and result['memory_updates']
    proposal = result['memory_updates'][0]
    decision = base + '/proposals/' + proposal['proposal_id'] + '/decision'
    assert client.post(decision, json={'decision':'approve'}).status_code == 200
    assert client.post(decision, json={'decision':'approve'}).status_code == 200
    facts = client.get('/api/memory/').json()
    assert len(facts) == 1
    memory = '/api/memory/' + facts[0]['id']
    assert client.put(memory, json={'content':'correction'}).status_code == 200
    assert client.post(memory + '/rollback', json={}).json()['content'] == facts[0]['content']
    assert client.delete(memory).status_code == 200
    assert client.get('/api/memory/').json() == []


def test_events_survive_later_runs(client):
    first = create(client, 'Find file sample.txt')
    base = '/api/runs/' + first['id']
    executed = client.post(base + '/execute').json()
    create(client, 'Draft email to test@example.com')
    assert client.get(base).json()['events'] == executed['events']
    assert client.get('/api/audit/' + first['id'] + '/replay').json()['is_identical']


def test_failures_are_persisted_and_stop_following_steps(client, monkeypatch):
    from proofbound.web.routes.runs import agent
    def fail(*args):
        raise OSError('Disk unavailable')
    monkeypatch.setattr(agent.workspace_worker, 'execute_tool', fail)
    run = create(client, 'Write file sample.txt content: hello')
    base = '/api/runs/' + run['id']
    client.post(base + '/decision', json={'decision':'approve'})
    result = client.post(base + '/execute').json()
    assert result['plan_steps'][0]['status'] == 'failed'
    assert result['plan_steps'][1]['status'] == 'skipped'
    assert result['events'][-1]['event_type'] == 'run_failed'


def test_sandbox_blocks_siblings_and_symlinks(tmp_path):
    root = tmp_path / 'safe'
    root.mkdir()
    outside = tmp_path / 'outside.txt'
    outside.write_text('private')
    (root / 'link').symlink_to(outside)
    token = PolicyEngine.issue_token('run', 'worker', ['workspace:read'], [str(root)])
    for target in [tmp_path / 'safe-other' / 'file', root / 'link', root / '..' / 'outside.txt']:
        assert not PolicyEngine.evaluate_tool_call('workspace_read_file', {'file_path':str(target)}, token)[0]


def test_network_failure_has_no_fake_evidence():
    def fail(request):
        raise httpx.ConnectError('offline')
    worker = BrowserWorker(httpx.MockTransport(fail))
    result = worker.execute_tool('browser_fetch_page', {'url':'https://example.com'}, PolicyEngine.issue_token('run', 'worker', ['browser:read']))
    assert not result.success and not result.citations and not result.artifacts


def test_redirect_is_authorized_before_fetching():
    calls = []
    def redirect(request):
        calls.append(str(request.url))
        return httpx.Response(302, headers={'Location':'http://127.0.0.1/secrets'})
    result = BrowserWorker(httpx.MockTransport(redirect)).execute_tool('browser_fetch_page', {'url':'https://example.com'}, PolicyEngine.issue_token('run', 'worker', ['browser:read']))
    assert not result.success and len(calls) == 1


def test_environment_configuration(monkeypatch, tmp_path):
    monkeypatch.setenv('PROOFBOUND_STORAGE_DIR', str(tmp_path / 'custom'))
    monkeypatch.setenv('PROOFBOUND_AUTO_APPROVE_LOW_RISK', 'false')
    configured = Settings()
    assert configured.db_path == tmp_path / 'custom' / 'proofbound.db'
    assert not configured.auto_approve_low_risk


def test_execution_claim_prevents_duplicate_work():
    agent = ProofboundAgent()
    run = agent.create_run('Find file anything.txt')
    agent.ledger.claim_run(run.id)
    with pytest.raises(PermissionError):
        agent.execute_run(run.id)
    agent.ledger.release_run(run.id)
    assert agent.execute_run(run.id).completed_at


def test_api_authentication_and_downloads(client, monkeypatch):
    from proofbound.config import settings
    monkeypatch.setattr(settings, 'api_key', 'test-secret')
    assert client.get('/api/health').status_code == 200
    assert client.get('/api/audit/').status_code == 401
    assert client.get('/api/audit/', headers={'Authorization':'Bearer wrong'}).status_code == 401
    assert client.get('/api/audit/', headers={'Authorization':'Bearer test-secret'}).status_code == 200


def test_replace_read_and_restore_existing_file(client):
    run = create(client, 'Write file config.txt content: status=active')
    base = '/api/runs/' + run['id']
    client.post(base + '/decision', json={'decision':'approve'})
    client.post(base + '/execute')
    patch = create(client, 'Patch file config.txt replace "active" with "paused"')
    base = '/api/runs/' + patch['id']
    client.post(base + '/decision', json={'decision':'approve'})
    completed = client.post(base + '/execute').json()
    assert completed['plan_steps'][-1]['result']['written_content'] == 'status=paused'
    assert client.post(base + '/rollback').status_code == 200
    read = create(client, 'Read file config.txt')
    result = client.post('/api/runs/' + read['id'] + '/execute').json()
    assert result['plan_steps'][0]['result']['content'] == 'status=active'
