import re
import uuid
import hashlib
from typing import Any
import httpx
from proofbound.workers.base import BaseWorker, WorkerResult
from proofbound.core.policy_engine import CapabilityToken, PolicyEngine
from proofbound.models.evidence import Citation, Artifact

class BrowserWorker(BaseWorker):
    def __init__(self, transport=None):
        super().__init__(name="browser_use_worker")
        self.transport = transport

    def execute_tool(self, tool_name: str, parameters: dict[str, Any], token: CapabilityToken) -> WorkerResult:
        auth_ok, reason = PolicyEngine.evaluate_tool_call(tool_name, parameters, token)
        if not auth_ok:
            return WorkerResult(success=False, error=f"Policy Block: {reason}")

        if tool_name in ["browser_research", "browser_fetch_page"]:
            return self._fetch_and_research(parameters, token)
        elif tool_name == "browser_search":
            return self._search_web(parameters, token)
        else:
            return WorkerResult(success=False, error=f"Unknown browser tool '{tool_name}'")

    def _fetch_and_research(self, params: dict[str, Any], token: CapabilityToken) -> WorkerResult:
        url = params.get("url", "")
        query = params.get("query", "")
        if not url:
            url = f"https://wikipedia.org/wiki/{query.replace(' ', '_')}" if query else "https://wikipedia.org/wiki/Evidence-based_practice"

        from urllib.parse import urlsplit, urljoin
        auth_ok, reason = PolicyEngine.evaluate_tool_call("browser_fetch_page", {"url": url}, token)
        if not auth_ok:
            return WorkerResult(success=False, error=reason)
        domain = urlsplit(url).hostname
        if token.domain_allowlist:
            matched = any(domain == d or domain.endswith("." + d) for d in token.domain_allowlist)
            if not matched:
                return WorkerResult(success=False, error=f"Domain '{domain}' is blocked by security policy allowlist.")

        try:
            with httpx.Client(transport=self.transport, timeout=10.0, follow_redirects=False, headers={"User-Agent": "Proofbound-Agent/0.1.0"}) as client:
                for _ in range(6):
                    resp = client.get(url)
                    if not resp.is_redirect:
                        break
                    url = urljoin(url, resp.headers["location"])
                    allowed, reason = PolicyEngine.evaluate_tool_call("browser_fetch_page", {"url": url}, token)
                    if not allowed:
                        return WorkerResult(success=False, error=f"Redirect blocked: {reason}")
                resp.raise_for_status()
                html_text = resp.text
        except Exception as e:
            return WorkerResult(success=False, error=f"Failed to fetch {url}: {e}")

        clean_text = re.sub(r'<script.*?</script>', '', html_text, flags=re.DOTALL | re.IGNORECASE)
        clean_text = re.sub(r'<style.*?</style>', '', clean_text, flags=re.DOTALL | re.IGNORECASE)
        clean_text = re.sub(r'<[^>]+>', ' ', clean_text)
        clean_text = re.sub(r'\s+', ' ', clean_text).strip()

        title_match = re.search(r'<title>(.*?)</title>', html_text, re.IGNORECASE)
        page_title = title_match.group(1).strip() if title_match else domain

        snippet = clean_text[:350]
        if query:
            q_terms = [t for t in query.lower().split() if len(t) > 3]
            for term in q_terms:
                idx = clean_text.lower().find(term)
                if idx != -1:
                    start = max(0, idx - 40)
                    end = min(len(clean_text), idx + 240)
                    snippet = "..." + clean_text[start:end] + "..."
                    break

        content_hash = hashlib.sha256(snippet.encode("utf-8")).hexdigest()[:16]

        cit = Citation(
            id=f"cit-{uuid.uuid4().hex[:8]}",
            run_id=token.run_id,
            source_type="web",
            source_uri=url,
            title=page_title,
            snippet=snippet,
            content_hash=content_hash,
            confidence=0.5
        )

        art = Artifact(
            id=f"art-{uuid.uuid4().hex[:8]}",
            run_id=token.run_id,
            artifact_type="report",
            name=f"research_{domain.replace('.', '_')}.txt",
            path_or_uri=url,
            mime_type="text/plain",
            size_bytes=len(clean_text),
            content_preview=snippet
        )

        return WorkerResult(
            success=True,
            data={
                "url": url,
                "title": page_title,
                "snippet": snippet,
                "status_code": resp.status_code,
                "bytes_fetched": len(html_text)
            },
            citations=[cit],
            artifacts=[art],
            logs=[f"Successfully fetched {url} (HTTP {resp.status_code})", f"Extracted verified citation hash {content_hash}"]
        )

    def _search_web(self, params: dict[str, Any], token: CapabilityToken) -> WorkerResult:
        query = params.get("query", "")
        return self._fetch_and_research({"query": query, "url": f"https://wikipedia.org/wiki/{query.replace(' ', '_')}"}, token)
