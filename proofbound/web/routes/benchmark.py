from fastapi import APIRouter
from proofbound.benchmark.suite import BenchmarkSuite, BenchmarkResult

router = APIRouter()

@router.post("/run", response_model=BenchmarkResult)
def run_benchmark():
    suite = BenchmarkSuite()
    return suite.run_all()
