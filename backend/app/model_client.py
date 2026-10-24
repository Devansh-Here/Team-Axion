"""A1: Local Ollama client. Loopback only, no hosted fallback (hard rule 2)."""
import os
import time
from typing import Optional
from urllib.parse import urlparse

import httpx

LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


class ModelUnavailable(Exception):
    """Local model could not be reached or returned unusable output."""


class ModelClient:
    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout_s: float = 120.0,
        retry_delay_s: float = 0.5,
        transport: Optional[httpx.BaseTransport] = None,  # tests only
    ):
        self.base_url = (base_url or os.getenv("MODEL_BASE_URL", "http://127.0.0.1:11434")).rstrip("/")
        self.model = model or os.getenv("MODEL_NAME", "approved-local-model")
        self.retry_delay_s = retry_delay_s

        parsed = urlparse(self.base_url)
        if parsed.scheme not in ("http", "https") or parsed.hostname not in LOOPBACK_HOSTS:
            # Fail closed: never send prompts to a non-local host.
            raise ValueError("MODEL_BASE_URL must point to a loopback address")

        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=httpx.Timeout(timeout_s, connect=5.0),
            transport=transport,
            trust_env=False,         # ignore HTTP(S)_PROXY env vars
            follow_redirects=False,  # a redirect could leave loopback
        )

    def generate(self, prompt: str, *, json_mode: bool = True, temperature: float = 0.0) -> str:
        """Return the model's text. Retries once on transport errors / 5xx."""
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": temperature},
        }
        if json_mode:
            payload["format"] = "json"

        last_reason = "unknown"
        for attempt in range(2):  # 1 try + 1 retry
            try:
                resp = self._client.post("/api/generate", json=payload)
            except httpx.TransportError:
                last_reason = "connection failed or timed out"
            else:
                if resp.status_code >= 500:
                    last_reason = f"model server error ({resp.status_code})"
                elif resp.status_code != 200:
                    # 4xx (e.g. model not pulled): retrying won't help.
                    raise ModelUnavailable(f"Local model request rejected ({resp.status_code})")
                else:
                    return self._extract_text(resp)
            if attempt == 0:
                time.sleep(self.retry_delay_s)
        raise ModelUnavailable(f"Local model unavailable: {last_reason}")

    @staticmethod
    def _extract_text(resp: httpx.Response) -> str:
        try:
            text = resp.json().get("response")
        except (ValueError, AttributeError):
            raise ModelUnavailable("Local model returned a malformed response")
        if not isinstance(text, str):
            raise ModelUnavailable("Local model returned a malformed response")
        return text

    def is_available(self) -> bool:
        """Cheap health check (for /health and the UI 'model offline' banner)."""
        try:
            return self._client.get("/api/tags").status_code == 200
        except httpx.HTTPError:
            return False

    def close(self) -> None:
        self._client.close()