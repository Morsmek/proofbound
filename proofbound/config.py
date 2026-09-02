import os
from pathlib import Path
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    app_name: str = "Proofbound"
    version: str = "0.1.0"
    debug: bool = False
    
    # Storage & DB
    storage_dir: Path = Path(os.getenv("PROOFBOUND_STORAGE_DIR", Path.home() / ".proofbound"))
    db_path: Path = storage_dir / "proofbound.db"
    workspace_root: Path = Path(os.getenv("PROOFBOUND_WORKSPACE_ROOT", "./workspace_sandbox")).resolve()
    
    # Policy & Security Gates
    auto_approve_low_risk: bool = True
    require_destructive_confirmation: bool = True
    domain_allowlist: list[str] = [
        "wikipedia.org",
        "github.com",
        "python.org",
        "pypi.org",
        "arxiv.org",
        "docs.pydantic.dev",
        "fastapi.tiangolo.com",
        "news.ycombinator.com",
        "example.com",
    ]
    blocked_commands: list[str] = [
        "rm -rf /",
        "format",
        "mkfs",
        "dd if=/dev/zero",
        ":(){ :|:& };:",
        "chmod -R 777 /",
        "del /f /s /q c:\\*",
    ]
    
    # Model Provider Configuration
    llm_provider: str = os.getenv("PROOFBOUND_LLM_PROVIDER", "mock")  # mock, gemini, openai, anthropic, ollama
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    model_name: str = os.getenv("PROOFBOUND_MODEL_NAME", "proofbound-engine")

    # Web Server
    host: str = os.getenv("PROOFBOUND_HOST", "127.0.0.1")
    port: int = int(os.getenv("PROOFBOUND_PORT", "8000"))

    def ensure_directories(self):
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.workspace_root.mkdir(parents=True, exist_ok=True)

settings = Settings()
settings.ensure_directories()
