"""n8n workflow provider (matrix row C6 — Hybrid/Remote).

Talks to a self-hosted n8n instance over its REST API and webhooks using only
the standard library (urllib) — the same choice as the OpenAI-compatible LLM
provider, so no extra dependency is required.

- ``health()``          → GET  {base}/healthz
- ``list_workflows()``  → GET  {base}/api/v1/workflows  (X-N8N-API-KEY)
- ``run_workflow()``    → POST {base}/webhook/<path>    (webhook trigger)

The webhook trigger is how n8n workflows are designed to be invoked from
outside; the ``workflow_id`` passed to ``run_workflow`` is the workflow's
webhook trigger *path* (the value configured on the Webhook trigger node).
The API key is created in the n8n UI (Settings → API) and passed via
``JARVIS_N8N_API_KEY`` — never committed (ADR-0005 / matrix D2).
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from .base import WorkflowProvider, WorkflowUnavailable


class N8nWorkflowProvider(WorkflowProvider):
    def __init__(self, *, base_url: str, api_key: str = "") -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    def health(self) -> dict[str, Any]:
        data = self._request("GET", "/healthz")
        return data if isinstance(data, dict) else {"status": data}

    def list_workflows(self) -> list[dict[str, Any]]:
        data = self._request("GET", "/api/v1/workflows")
        # n8n returns {"data": [...], "nextCursor": ...} with cursor pagination.
        return data.get("data") if isinstance(data, dict) else []

    def run_workflow(self, workflow_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        data = self._request("POST", f"/webhook/{workflow_id}", payload=payload)
        if isinstance(data, dict):
            return data
        # n8n's default webhook response is plain text; surface it verbatim.
        return {"message": data}

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
        headers = {"X-N8N-API-KEY": self.api_key} if self.api_key else {}
        body = None
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(
            f"{self.base_url}{path}",
            data=body,
            headers=headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                raw = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            raise WorkflowUnavailable(f"n8n returned HTTP {exc.code} for {path}") from exc
        except OSError as exc:
            raise WorkflowUnavailable(f"cannot reach n8n at {self.base_url}: {exc}") from exc
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except ValueError:
            return raw