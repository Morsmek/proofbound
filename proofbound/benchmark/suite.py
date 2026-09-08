"""Isolated, deterministic contract checks. Fixture pages are never used in real runs."""
import hashlib
import tempfile
import time
from pathlib import Path

import httpx
from pydantic import BaseModel, Field
from proofbound.core.agent import ProofboundAgent
from proofbound.core.approval_gate import ApprovalGate
from proofbound.core.ledger import ActionLedger
from proofbound.core.policy_engine import PolicyEngine
from proofbound.memory.engine import MemoryEngine
from proofbound.memory.storage import MemoryStorage


class TaskResult(BaseModel):
    task_id: int
    name: str
    category: str
    passed: bool
    duration_ms: float
    details: str
    evidence_items: int = 0
    ledger_events: int = 0


class BenchmarkResult(BaseModel):
    total_tasks: int
    passed_tasks: int
    failed_tasks: int
    pass_rate: float
    total_duration_ms: float
    results: list[TaskResult] = Field(default_factory=list)


class BenchmarkSuite:
    def run_all(self):
        start = time.perf_counter()
        results = []
        with tempfile.TemporaryDirectory(prefix="proofbound-benchmark-") as directory:
            root = Path(directory)
            def fixture(request):
                return httpx.Response(200, text=f"<title>Benchmark fixture</title><p>Fixture evidence for {request.url.path}</p>")
            agent = ProofboundAgent(ledger=ActionLedger(root / 'ledger.db'),
                memory=MemoryEngine(MemoryStorage(root / 'memory.db')),
                workspace_root=root / 'workspace', browser_transport=httpx.MockTransport(fixture))

            def execute(intent):
                run = agent.create_run(intent)
                if run.approval_state.value == 'PENDING':
                    ApprovalGate.grant_approval(run, approver='isolated-benchmark')
                    agent.ledger.save_run(run)
                return agent.execute_run(run.id)

            def research():
                run = execute('Research https://example.com/first https://example.com/second')
                assert len(run.citations) == 2
                for citation in run.citations:
                    assert citation.content_hash == hashlib.sha256(citation.snippet.encode()).hexdigest()[:16]
                return 'Two fixture sources captured with matching excerpt hashes'

            def domain():
                run = execute('Browse https://not-authorized.invalid/page')
                assert run.plan_steps[0].status.value == 'failed' and not run.citations
                return 'Disallowed source rejected before fetching'

            def workspace():
                (agent.workspace_root / 'settings.txt').write_text('hello')
                run = execute('Find file settings.txt')
                assert run.plan_steps[0].result['count'] == 1
                return 'Created fixture file found within isolated workspace'

            def patch():
                file = agent.workspace_root / 'patch.txt'
                file.write_text('original')
                run = execute('Write file patch.txt content: updated')
                result = run.plan_steps[-1].result
                assert file.read_text() == 'updated' and result['previous_content'] == 'original'
                assert run.artifacts[0].artifact_type == 'diff'
                file.write_text(result['previous_content'])
                assert file.read_text() == 'original'
                return 'Literal write, diff, and previous-content restoration verified'

            def draft():
                run = execute('Draft email to person@example.com')
                assert run.artifacts[0].mime_type == 'message/rfc822'
                assert 'person@example.com' in run.artifacts[0].content_preview
                return 'Downloadable email content staged without sending'

            def destructive():
                run = agent.create_run('rm -rf /')
                assert run.approval_state.value == 'REJECTED'
                try:
                    ApprovalGate.grant_approval(run)
                except PermissionError:
                    return 'Blocked command cannot be re-approved'
                raise AssertionError('Blocked command was re-approved')

            def boundary():
                token = PolicyEngine.issue_token('bench', 'bench', ['workspace:write'], [str(agent.workspace_root)])
                allowed, _ = PolicyEngine.evaluate_tool_call('workspace_write_file', {'file_path':str(root / 'workspace-other' / 'file.txt')}, token)
                assert not allowed
                return 'Sibling-prefix sandbox escape rejected'

            def memory():
                run = execute('Research https://example.com/memory')
                proposal = run.memory_updates[0]
                fact = agent.memory.accept_proposal(proposal)
                assert fact.provenance_run_id == run.id
                assert agent.memory.accept_proposal(proposal).id == fact.id
                return 'Source-linked proposal accepted without duplicate facts'

            def rollback():
                fact = agent.memory.accept_proposal(agent.memory.propose_fact('bench', 'initial', 'fixture'))
                agent.memory.edit_fact(fact.id, 'edited')
                assert agent.memory.rollback_fact(fact.id).content == 'initial'
                return 'Memory revision restored'

            def replay():
                first = execute('Find file settings.txt')
                execute('Find file patch.txt')
                restored = agent.ledger.get_run(first.id)
                assert [e.model_dump() for e in restored.events] == [e.model_dump() for e in first.events]
                assert agent.ledger.replay_run(first.id).is_identical
                return 'Events preserved across runs and stored payload hashes match'

            checks = [('Multi-source fixture extraction',research),('Domain allowlist',domain),
                ('Workspace search',workspace),('Reversible file write',patch),('Email draft',draft),
                ('Destructive approval gate',destructive),('Workspace boundary',boundary),
                ('Memory provenance',memory),('Memory rollback',rollback),('Ledger integrity',replay)]
            for i, (name, check) in enumerate(checks, 1):
                began = time.perf_counter()
                try:
                    details = check()
                    passed = True
                except Exception as exc:
                    details, passed = f'{type(exc).__name__}: {exc}', False
                results.append(TaskResult(task_id=i, name=name, category='Isolated fixture', passed=passed,
                    details=details, duration_ms=round((time.perf_counter()-began)*1000,2)))
        passed = sum(r.passed for r in results)
        return BenchmarkResult(total_tasks=len(results), passed_tasks=passed, failed_tasks=len(results)-passed,
            pass_rate=100*passed/len(results), total_duration_ms=round((time.perf_counter()-start)*1000,2), results=results)


if __name__ == '__main__':
    result = BenchmarkSuite().run_all()
    print(result.model_dump_json(indent=2))
    raise SystemExit(0 if result.failed_tasks == 0 else 1)
