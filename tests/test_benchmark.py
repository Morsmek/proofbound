import pytest
from proofbound.benchmark.suite import BenchmarkSuite

def test_10_task_benchmark_suite():
    suite = BenchmarkSuite()
    result = suite.run_all()
    assert result.total_tasks == 10
    assert result.passed_tasks == 10
    assert result.pass_rate == 100.0
