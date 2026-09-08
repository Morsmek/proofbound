import os
import difflib
import uuid
from typing import Any
from pathlib import Path
from proofbound.workers.base import BaseWorker, WorkerResult
from proofbound.core.policy_engine import CapabilityToken, PolicyEngine
from proofbound.models.evidence import Citation, Artifact

class WorkspaceWorker(BaseWorker):
    def __init__(self):
        super().__init__(name="workspace_sandbox_worker")

    def execute_tool(self, tool_name: str, parameters: dict[str, Any], token: CapabilityToken) -> WorkerResult:
        auth_ok, reason = PolicyEngine.evaluate_tool_call(tool_name, parameters, token)
        if not auth_ok:
            return WorkerResult(success=False, error=f"Policy Block: {reason}")

        if tool_name == "workspace_read_file":
            return self._read_file(parameters, token)
        elif tool_name == "workspace_write_file":
            return self._write_file(parameters, token)
        elif tool_name == "workspace_patch_file":
            return self._patch_file(parameters, token)
        elif tool_name == "workspace_search":
            return self._search(parameters, token)
        else:
            return WorkerResult(success=False, error=f"Unknown workspace tool '{tool_name}'")

    def _read_file(self, params: dict[str, Any], token: CapabilityToken) -> WorkerResult:
        file_path = params.get("file_path", "")
        if not os.path.exists(file_path):
            return WorkerResult(success=False, error=f"File not found: {file_path}")
        
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()

        cit = Citation(
            id=f"cit-{uuid.uuid4().hex[:8]}",
            run_id=token.run_id,
            source_type="file",
            source_uri=file_path,
            title=os.path.basename(file_path),
            snippet=content[:200],
            confidence=1.0
        )
        return WorkerResult(
            success=True,
            data={"file_path": file_path, "content": content, "size": len(content)},
            citations=[cit],
            logs=[f"Read {len(content)} bytes from {file_path}"]
        )

    def _write_file(self, params: dict[str, Any], token: CapabilityToken) -> WorkerResult:
        file_path = params.get("file_path", "")
        if "content" not in params and not ("old" in params and "new" in params):
            return WorkerResult(success=False, error='Provide literal text using content: TEXT or replace "OLD" with "NEW"')
        content = params.get("content", "")
        
        os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)
        existed = os.path.exists(file_path)
        old_content = ""
        if os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                old_content = f.read()

        if "old" in params:
            if not params["old"] or params["old"] not in old_content:
                return WorkerResult(success=False, error="Replacement target was not found")
            content = old_content.replace(params["old"], params["new"])

        diff_lines = list(difflib.unified_diff(
            old_content.splitlines(keepends=True),
            content.splitlines(keepends=True),
            fromfile=f"a/{os.path.basename(file_path)}",
            tofile=f"b/{os.path.basename(file_path)}"
        ))
        diff_str = "".join(diff_lines)

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)

        art = Artifact(
            id=f"art-{uuid.uuid4().hex[:8]}",
            run_id=token.run_id,
            artifact_type="diff",
            name=f"patch_{os.path.basename(file_path)}.diff",
            path_or_uri=file_path,
            mime_type="text/x-diff",
            size_bytes=len(diff_str),
            content_preview=diff_str or "No changes"
        )

        return WorkerResult(
            success=True,
            data={"file_path": file_path, "diff": diff_str, "bytes_written": len(content.encode("utf-8")), "previous_content": old_content, "written_content": content, "existed": existed},
            artifacts=[art],
            logs=[f"Wrote file {file_path} (Diff recorded for rollback)"]
        )

    def _patch_file(self, params: dict[str, Any], token: CapabilityToken) -> WorkerResult:
        return self._write_file(params, token)

    def _search(self, params: dict[str, Any], token: CapabilityToken) -> WorkerResult:
        pattern = params.get("pattern", "")
        root_dir = token.allowed_paths[0] if token.allowed_paths else "."
        matches = []

        for root, _, files in os.walk(root_dir):
            for file in files:
                if pattern.lower() in file.lower():
                    candidate = Path(root, file)
                    if candidate.resolve().is_relative_to(Path(root_dir).resolve()):
                        matches.append(str(candidate))

        return WorkerResult(
            success=True,
            data={"pattern": pattern, "matches": matches, "count": len(matches)},
            logs=[f"Searched workspace for '{pattern}', found {len(matches)} matches"]
        )
