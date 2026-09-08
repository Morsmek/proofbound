import pytest
from proofbound.config import settings


@pytest.fixture(autouse=True)
def isolated_storage(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, 'storage_dir', tmp_path)
    monkeypatch.setattr(settings, 'db_path', tmp_path / 'proofbound.db')
    monkeypatch.setattr(settings, 'workspace_root', tmp_path / 'workspace')
    settings.ensure_directories()
