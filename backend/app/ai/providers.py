"""AI providers: Ollama (local) and Groq (cloud, OpenAI-compatible).

An httpx.Client can be injected for testing.
"""

from __future__ import annotations

import httpx

from app.config import AiSettings

from .base import AIError, AIProvider, AIUnavailable


def _post(client: httpx.Client, url: str, *, headers: dict, payload: dict, label: str) -> dict:
    try:
        r = client.post(url, headers=headers, json=payload)
    except httpx.ConnectError as e:
        raise AIUnavailable(f"{label}: cannot connect") from e
    except httpx.TimeoutException as e:
        raise AIError(f"{label}: request timed out") from e
    except httpx.HTTPError as e:
        raise AIError(f"{label}: network error ({type(e).__name__})") from e
    if r.status_code in (401, 403):
        raise AIUnavailable(f"{label}: authentication failed (check API key)")
    if r.status_code == 429:
        raise AIError(f"{label}: rate limited")
    if r.status_code >= 400:
        detail = ""
        try:
            body = r.json()
            msg = body.get("error", {}).get("message") if isinstance(body, dict) else None
            if isinstance(msg, str) and msg:
                detail = f": {msg[:160]}"
        except ValueError:
            pass
        raise AIError(f"{label}: HTTP {r.status_code}{detail}")
    try:
        return r.json()
    except ValueError as e:
        raise AIError(f"{label}: invalid JSON response") from e


class OllamaProvider(AIProvider):
    name, is_cloud = "ollama", False

    def __init__(self, s: AiSettings, client: httpx.Client | None = None):
        # Ollama is local: never route it through a system/HTTP proxy.
        self.s, self.client = s, client or httpx.Client(timeout=s.timeout_seconds, trust_env=False)

    def complete_json(self, system: str, user: str) -> str:
        d = _post(
            self.client,
            f"{self.s.ollama_url.rstrip('/')}/api/chat",
            headers={},
            label="Ollama",
            payload={
                "model": self.s.ollama_model,
                "stream": False,
                "format": "json",
                "options": {"temperature": 0},
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            },
        )
        try:
            return d["message"]["content"]
        except (KeyError, TypeError) as e:
            raise AIError("Ollama: unexpected response shape") from e


class GroqProvider(AIProvider):
    name, is_cloud = "groq", True

    def __init__(self, s: AiSettings, client: httpx.Client | None = None):
        # Groq is a cloud API: trust the system proxy settings (needed on many corporate networks).
        self.s, self.client = s, client or httpx.Client(timeout=s.timeout_seconds, trust_env=True)

    def complete_json(self, system: str, user: str) -> str:
        if not self.s.groq_api_key:
            raise AIUnavailable("Groq: GROQ_API_KEY is not configured (set it in .env and restart)")
        url = f"{self.s.groq_base_url.rstrip('/')}/chat/completions"
        headers = {"Authorization": f"Bearer {self.s.groq_api_key}"}
        payload = {
            "model": self.s.groq_model,
            "temperature": 0,
            "max_tokens": 2048,
            "response_format": {"type": "json_object"},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        }
        # GPT-OSS models support a reasoning-effort switch; low keeps responses fast.
        if self.s.groq_model.startswith("openai/gpt-oss"):
            payload["reasoning_effort"] = "low"
        try:
            d = _post(self.client, url, headers=headers, payload=payload, label="Groq")
        except AIError as e:
            # Not every Groq model accepts response_format/reasoning_effort; retry once without them.
            if "HTTP 400" not in str(e):
                raise
            payload.pop("response_format", None)
            payload.pop("reasoning_effort", None)
            d = _post(self.client, url, headers=headers, payload=payload, label="Groq")
        try:
            content = d["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as e:
            raise AIError("Groq: unexpected response shape") from e
        if not isinstance(content, str) or not content.strip():
            raise AIError("Groq: empty response")
        return content


def get_provider(s: AiSettings, client: httpx.Client | None = None) -> AIProvider | None:
    """Return the configured provider, or None when AI is disabled (the app works without AI)."""
    return {
        "none": lambda: None,
        "": lambda: None,
        "ollama": lambda: OllamaProvider(s, client),
        "groq": lambda: GroqProvider(s, client),
    }.get(s.provider, lambda: _bad(s.provider))()


def _bad(name: str):
    raise AIUnavailable(f"Unknown AI provider '{name}' (use none, ollama or groq)")
