"""LLM-Zugriff. Ein Provider, ein Vertrag: JSON rein, JSON raus."""

from __future__ import annotations

import json
import re
from typing import Any, Protocol

import httpx

from app.config import Settings, get_settings


class LlmUnavailable(RuntimeError):
    """Provider nicht erreichbar oder Antwort unbrauchbar."""


def parse_json_content(content: str) -> dict[str, Any]:
    text = re.sub(r"<think>.*?</think>", "", content.strip(), flags=re.S).strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError as err:
        match = re.search(r"\{.*\}", text, re.S)
        if not match:
            raise LlmUnavailable(f"keine JSON-Antwort: {text[:200]}") from err
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError as inner:
            raise LlmUnavailable(f"JSON kaputt: {text[:200]}") from inner


class LlmProvider(Protocol):
    name: str

    def complete_json(self, system: str, user: str) -> dict[str, Any]: ...


class OllamaProvider:
    def __init__(self, base_url: str, model: str, timeout: int) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout
        self.name = f"ollama:{model}"

    def complete_json(self, system: str, user: str) -> dict[str, Any]:
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": f"/no_think\n{user}"},
            ],
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.2, "num_predict": 1600, "num_ctx": 8192},
            "keep_alive": "30m",
        }
        try:
            response = httpx.post(
                f"{self._base_url}/api/chat",
                json=payload,
                timeout=self._timeout,
            )
            response.raise_for_status()
            return parse_json_content(response.json()["message"]["content"])
        except (httpx.HTTPError, KeyError, ValueError) as err:
            raise LlmUnavailable(str(err)[:300]) from err

    def complete_text(self, system: str, user: str) -> str:
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": f"/no_think\n{user}"},
            ],
            "stream": False,
            "options": {"temperature": 0.3, "num_predict": 1600, "num_ctx": 8192},
            "keep_alive": "30m",
        }
        try:
            response = httpx.post(
                f"{self._base_url}/api/chat",
                json=payload,
                timeout=self._timeout,
            )
            response.raise_for_status()
            text = str(response.json()["message"]["content"] or "")
            text = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
            if not text:
                raise LlmUnavailable("leere Modell-Antwort")
            return text
        except LlmUnavailable:
            raise
        except (httpx.HTTPError, KeyError, ValueError) as err:
            raise LlmUnavailable(str(err)[:300]) from err


def normalize_openai_base_url(base_url: str) -> str:
    """Nur die Root bis /v1. /chat/completions haengt der Client selbst an."""
    url = (base_url or "").strip().rstrip("/")
    for suffix in ("/chat/completions", "/completions", "/models"):
        if url.endswith(suffix):
            url = url[: -len(suffix)].rstrip("/")
    return url


def list_openai_models(base_url: str, api_key: str, timeout: int = 20) -> list[str]:
    """Modell-IDs vom OpenAI-kompatiblen Endpunkt (/v1/models)."""
    base = normalize_openai_base_url(base_url)
    if not base:
        raise LlmUnavailable("Base-URL fehlt")
    if not api_key:
        raise LlmUnavailable("API-Key fehlt")
    try:
        response = httpx.get(
            f"{base}/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
        )
        response.raise_for_status()
        data = response.json().get("data") or []
        ids = [str(item["id"]) for item in data if item.get("id")]
    except (httpx.HTTPError, KeyError, ValueError, TypeError) as err:
        raise LlmUnavailable(f"Modelle nicht lesbar: {str(err)[:200]}") from err
    if not ids:
        raise LlmUnavailable("Endpunkt liefert keine Modelle")
    return ids


def resolve_openai_model(base_url: str, api_key: str, model: str | None, timeout: int = 20) -> str:
    """Leeres oder unbekanntes Modell → erstes Modell vom Endpunkt."""
    wanted = (model or "").strip()
    available = list_openai_models(base_url, api_key, timeout=timeout)
    if wanted and wanted in available:
        return wanted
    if wanted and wanted not in available:
        # Falscher Name (z. B. Ollama-Tag) → still auf das einzige/erste Modell wechseln.
        return available[0]
    return available[0]


class OpenAiProvider:
    def __init__(self, base_url: str, model: str, api_key: str, timeout: int) -> None:
        self._base_url = normalize_openai_base_url(base_url)
        self._model = (model or "").strip()
        self._api_key = api_key
        self._timeout = timeout
        self.name = f"openai:{self._model or 'auto'}"

    def ensure_model(self) -> str:
        if self._model:
            # Bei 404 trotzdem neu aufloesen — hier nur Cache fuer den Namen.
            return self._model
        self._model = resolve_openai_model(
            self._base_url, self._api_key, None, timeout=min(20, self._timeout)
        )
        self.name = f"openai:{self._model}"
        return self._model

    def complete_json(self, system: str, user: str) -> dict[str, Any]:
        if not self._api_key:
            raise LlmUnavailable("OpenAI API-Key fehlt")
        if not self._base_url:
            raise LlmUnavailable("OpenAI Base-URL fehlt")

        model = self.ensure_model()
        payload = {
            "model": model,
            "temperature": 0.2,
            "max_tokens": 2000,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            # Qwen3/vLLM: Thinking aus — sonst content=null und Antwort zu langsam.
            "chat_template_kwargs": {"enable_thinking": False},
        }
        try:
            response = httpx.post(
                f"{self._base_url}/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {self._api_key}"},
                timeout=self._timeout,
            )
            if response.status_code == 404 and "does not exist" in response.text:
                # Gespeicherter Modellname falsch → einmal neu vom Endpunkt holen.
                self._model = ""
                payload["model"] = self.ensure_model()
                response = httpx.post(
                    f"{self._base_url}/chat/completions",
                    json=payload,
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    timeout=self._timeout,
                )
            if response.status_code >= 400:
                raise LlmUnavailable(
                    f"HTTP {response.status_code}: {response.text[:240]}"
                )
            message = response.json()["choices"][0]["message"]
            text = message.get("content") or message.get("reasoning") or ""
            if not text:
                raise LlmUnavailable("leere Modell-Antwort")
            return parse_json_content(text)
        except LlmUnavailable:
            raise
        except (httpx.HTTPError, KeyError, ValueError, IndexError, TypeError) as err:
            raise LlmUnavailable(str(err)[:300]) from err

    def complete_text(self, system: str, user: str) -> str:
        if not self._api_key:
            raise LlmUnavailable("OpenAI API-Key fehlt")
        if not self._base_url:
            raise LlmUnavailable("OpenAI Base-URL fehlt")
        model = self.ensure_model()
        payload = {
            "model": model,
            "temperature": 0.3,
            "max_tokens": 2000,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "chat_template_kwargs": {"enable_thinking": False},
        }
        try:
            response = httpx.post(
                f"{self._base_url}/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {self._api_key}"},
                timeout=self._timeout,
            )
            if response.status_code >= 400:
                raise LlmUnavailable(
                    f"HTTP {response.status_code}: {response.text[:240]}"
                )
            message = response.json()["choices"][0]["message"]
            text = message.get("content") or message.get("reasoning") or ""
            text = re.sub(r"<think>.*?</think>", "", str(text), flags=re.S).strip()
            if text.startswith("```"):
                text = re.sub(r"^```(?:\w+)?\s*", "", text)
                text = re.sub(r"\s*```$", "", text)
            if not text:
                raise LlmUnavailable("leere Modell-Antwort")
            return text
        except LlmUnavailable:
            raise
        except (httpx.HTTPError, KeyError, ValueError, IndexError, TypeError) as err:
            raise LlmUnavailable(str(err)[:300]) from err


class AnthropicProvider:
    def __init__(self, base_url: str, model: str, api_key: str, timeout: int) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._api_key = api_key
        self._timeout = timeout
        self.name = f"anthropic:{model}"

    def complete_json(self, system: str, user: str) -> dict[str, Any]:
        if not self._api_key:
            raise LlmUnavailable("Anthropic API-Key fehlt")
        payload = {
            "model": self._model,
            "max_tokens": 2048,
            "temperature": 0.2,
            "system": system + "\n\nAntworte ausschließlich mit gültigem JSON.",
            "messages": [{"role": "user", "content": user}],
        }
        try:
            response = httpx.post(
                f"{self._base_url}/v1/messages",
                json=payload,
                headers={
                    "x-api-key": self._api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                timeout=self._timeout,
            )
            response.raise_for_status()
            blocks = response.json().get("content") or []
            text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
            return parse_json_content(text)
        except (httpx.HTTPError, KeyError, ValueError) as err:
            raise LlmUnavailable(str(err)[:300]) from err


class GeminiProvider:
    def __init__(self, base_url: str, model: str, api_key: str, timeout: int) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._api_key = api_key
        self._timeout = timeout
        self.name = f"gemini:{model}"

    def complete_json(self, system: str, user: str) -> dict[str, Any]:
        if not self._api_key:
            raise LlmUnavailable("Gemini API-Key fehlt")
        url = (
            f"{self._base_url}/models/{self._model}:generateContent"
            f"?key={self._api_key}"
        )
        payload = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": 2048,
                "responseMimeType": "application/json",
            },
        }
        try:
            response = httpx.post(url, json=payload, timeout=self._timeout)
            response.raise_for_status()
            parts = response.json()["candidates"][0]["content"]["parts"]
            text = "".join(p.get("text", "") for p in parts)
            return parse_json_content(text)
        except (httpx.HTTPError, KeyError, ValueError, IndexError) as err:
            raise LlmUnavailable(str(err)[:300]) from err


class NoLlmProvider:
    name = "heuristik"

    def complete_json(self, system: str, user: str) -> dict[str, Any]:
        raise LlmUnavailable("kein LLM konfiguriert")


def build_provider_from_runtime(runtime) -> LlmProvider:
    provider = (runtime.llm_provider or "ollama").lower()
    model = runtime.llm_model
    base = runtime.llm_base_url
    key = runtime.llm_api_key
    timeout = int(runtime.llm_timeout or 180)

    if provider == "ollama":
        return OllamaProvider(base or "http://127.0.0.1:11434", model, timeout)
    if provider == "openai":
        return OpenAiProvider(
            base or "https://api.openai.com/v1", model, key, timeout
        )
    if provider == "anthropic":
        return AnthropicProvider(
            base or "https://api.anthropic.com", model, key, timeout
        )
    if provider == "gemini":
        return GeminiProvider(
            base or "https://generativelanguage.googleapis.com/v1beta",
            model,
            key,
            timeout,
        )
    return NoLlmProvider()


def build_provider(settings: Settings | None = None) -> LlmProvider:
    """Env-Fallback. Bevorzugt Runtime-Config aus der DB."""
    try:
        from app.services.settings_service import get_runtime_config

        return build_provider_from_runtime(get_runtime_config())
    except Exception:
        settings = settings or get_settings()
        if settings.llm_provider == "ollama":
            return OllamaProvider(
                settings.ollama_base_url, settings.ollama_model, settings.llm_timeout
            )
        if settings.llm_provider == "openai" and settings.openai_api_key:
            return OpenAiProvider(
                settings.openai_base_url,
                settings.openai_model,
                settings.openai_api_key,
                settings.llm_timeout,
            )
        if settings.llm_provider == "anthropic" and settings.anthropic_api_key:
            return AnthropicProvider(
                settings.anthropic_base_url,
                settings.anthropic_model,
                settings.anthropic_api_key,
                settings.llm_timeout,
            )
        if settings.llm_provider == "gemini" and settings.gemini_api_key:
            return GeminiProvider(
                settings.gemini_base_url,
                settings.gemini_model,
                settings.gemini_api_key,
                settings.llm_timeout,
            )
        return NoLlmProvider()
