from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
import json
from proofbound.web.routes import runs, memory, audit, benchmark

app = FastAPI(
    title="Proofbound API",
    description="Verifiable, evidence-first personal operations agent platform.",
    version="0.1.0"
)

from proofbound.config import settings
from fastapi.responses import JSONResponse
import secrets

@app.middleware("http")
async def authenticate_api(request, call_next):
    if request.url.path.startswith("/api/") and request.url.path != "/api/health" and settings.api_key:
        supplied = request.headers.get("authorization", "")
        if not secrets.compare_digest(supplied, f"Bearer {settings.api_key}"):
            return JSONResponse({"detail": "Enter the backend access key to continue."}, status_code=401)
    response = await call_next(request)
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response

app.include_router(runs.router, prefix="/api/runs", tags=["Runs"])
app.include_router(memory.router, prefix="/api/memory", tags=["Memory"])
app.include_router(audit.router, prefix="/api/audit", tags=["Audit"])
app.include_router(benchmark.router, prefix="/api/benchmark", tags=["Benchmark"])

@app.get("/api/health")
def health():
    return {"status": "ok", "version": "0.1.0"}

@app.websocket("/ws/events")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_text()
            await websocket.send_text(json.dumps({"status": "connected", "received": data}))
    except WebSocketDisconnect:
        pass

static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")
