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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(runs.router, prefix="/api/runs", tags=["Runs"])
app.include_router(memory.router, prefix="/api/memory", tags=["Memory"])
app.include_router(audit.router, prefix="/api/audit", tags=["Audit"])
app.include_router(benchmark.router, prefix="/api/benchmark", tags=["Benchmark"])

static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")

@app.websocket("/ws/events")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_text()
            await websocket.send_text(json.dumps({"status": "connected", "received": data}))
    except WebSocketDisconnect:
        pass
