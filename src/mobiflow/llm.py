"""Build LLM chat completions from llm.json profiles (OpenAI / Azure / Anthropic / Google)."""

from __future__ import annotations

import logging
import re
from typing import Any

from mobiflow.llm_catalog import ModelEntry

logger = logging.getLogger(__name__)


def profile_to_llm_config(profile: ModelEntry) -> dict[str, Any]:
    """Shape expected by invoke_chat_text (provider, model, keys, Azure fields)."""
    provider = profile.provider.lower()
    cfg: dict[str, Any] = {
        "provider": "azure" if provider.startswith("azure") else provider,
        "apiKey": profile.resolve_api_key(),
        "temperature": 0.2,
    }
    if provider.startswith("azure"):
        cfg["apiEndpoint"] = profile.resolve_endpoint()
        cfg["deploymentName"] = profile.deployment_name()
        cfg["apiVersion"] = profile.api_version
        cfg["modelName"] = profile.short_model()
    else:
        cfg["modelName"] = profile.short_model()
    return cfg


def invoke_chat_text(
    system: str,
    user: str,
    llm_config: dict[str, Any],
    *,
    max_tokens: int = 4096,
    temperature: float | None = None,
    log_prefix: str = "MobiFlow",
) -> str:
    """Synchronous chat completion → plain text."""
    provider = (llm_config.get("provider") or "openai").lower()
    temp = temperature if temperature is not None else float(llm_config.get("temperature") or 0.2)
    api_key = llm_config.get("apiKey") or ""
    if not api_key:
        raise ValueError(f"{log_prefix}: llm_config missing apiKey")

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]

    if provider in ("anthropic", "claude"):
        return _anthropic_chat(messages, llm_config, api_key, max_tokens, temp, log_prefix)

    if provider in ("google", "gemini", "google-genai"):
        return _google_chat(messages, llm_config, api_key, max_tokens, temp, log_prefix)

    if provider.startswith("azure"):
        return _openai_compatible_chat(
            messages,
            llm_config,
            api_key,
            max_tokens,
            temp,
            log_prefix,
            azure=True,
        )

    return _openai_compatible_chat(
        messages,
        llm_config,
        api_key,
        max_tokens,
        temp,
        log_prefix,
        azure=False,
    )


def _openai_compatible_chat(
    messages: list[dict[str, str]],
    llm_config: dict[str, Any],
    api_key: str,
    max_tokens: int,
    temperature: float,
    log_prefix: str,
    *,
    azure: bool,
) -> str:
    from openai import AzureOpenAI, OpenAI

    if azure:
        endpoint = (llm_config.get("apiEndpoint") or "").rstrip("/")
        deployment = llm_config.get("deploymentName") or llm_config.get("modelName") or "gpt-4o"
        api_version = llm_config.get("apiVersion") or "2025-03-01-preview"
        client = AzureOpenAI(
            api_key=api_key,
            azure_endpoint=endpoint,
            api_version=api_version,
        )
        model = deployment
    else:
        client = OpenAI(api_key=api_key)
        model = llm_config.get("modelName") or "gpt-4o"

    # Prefer max_completion_tokens for GPT-5 / o-series; fall back on 400.
    use_completion = _prefers_max_completion_tokens(model)
    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
    }
    if not _drop_temperature(model):
        kwargs["temperature"] = temperature
    if use_completion:
        kwargs["max_completion_tokens"] = max_tokens
    else:
        kwargs["max_tokens"] = max_tokens

    try:
        resp = client.chat.completions.create(**kwargs)
    except Exception as first:  # noqa: BLE001
        msg = str(first).lower()
        if "max_tokens" in msg and "max_completion_tokens" in msg:
            kwargs.pop("max_tokens", None)
            kwargs["max_completion_tokens"] = max_tokens
            resp = client.chat.completions.create(**kwargs)
        elif "temperature" in msg and "unsupported" in msg:
            kwargs.pop("temperature", None)
            resp = client.chat.completions.create(**kwargs)
        else:
            logger.error("%s LLM call failed: %s", log_prefix, first)
            raise

    choice = (resp.choices or [None])[0]
    if not choice or not choice.message:
        return ""
    return (choice.message.content or "").strip()


def _anthropic_chat(
    messages: list[dict[str, str]],
    llm_config: dict[str, Any],
    api_key: str,
    max_tokens: int,
    temperature: float,
    log_prefix: str,
) -> str:
    try:
        import anthropic
    except ImportError as e:
        raise RuntimeError(
            "Anthropic support needs: pip install 'mobiflow[anthropic]' or pip install anthropic"
        ) from e

    system = next((m["content"] for m in messages if m["role"] == "system"), "")
    user_msgs = [m for m in messages if m["role"] != "system"]
    client = anthropic.Anthropic(api_key=api_key)
    model = llm_config.get("modelName") or "claude-sonnet-4-6"
    resp = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        system=system,
        messages=[{"role": m["role"], "content": m["content"]} for m in user_msgs],
    )
    parts = []
    for block in resp.content or []:
        text = getattr(block, "text", None)
        if text:
            parts.append(text)
    return "\n".join(parts).strip()


def _google_chat(
    messages: list[dict[str, str]],
    llm_config: dict[str, Any],
    api_key: str,
    max_tokens: int,
    temperature: float,
    log_prefix: str,
) -> str:
    """Google Gemini via REST (no heavy SDK dep)."""
    import httpx

    model = llm_config.get("modelName") or "gemini-2.0-flash"
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={api_key}"
    )
    system = next((m["content"] for m in messages if m["role"] == "system"), "")
    user = "\n\n".join(m["content"] for m in messages if m["role"] == "user")
    body: dict[str, Any] = {
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "generationConfig": {
            "maxOutputTokens": max_tokens,
            "temperature": temperature,
        },
    }
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}

    with httpx.Client(timeout=120.0) as client:
        r = client.post(url, json=body)
        r.raise_for_status()
        data = r.json()
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except (KeyError, IndexError, TypeError) as e:
        logger.error("%s Gemini parse failed: %s — %s", log_prefix, e, data)
        raise RuntimeError(f"{log_prefix}: unexpected Gemini response") from e


def _prefers_max_completion_tokens(model: str) -> bool:
    name = (model or "").lower().replace("_", "-")
    return (
        name.startswith("o1")
        or name.startswith("o3")
        or name.startswith("o4")
        or "gpt-5" in name
        or "gpt5" in name
    )


def _drop_temperature(model: str) -> bool:
    return _prefers_max_completion_tokens(model)


def extract_yaml_fence(text: str) -> str:
    """Pull YAML from a ```yaml fence or return stripped text."""
    files = extract_fenced_files(text)
    for name, body in files:
        if name.endswith((".yaml", ".yml")) or name == "flow.yaml":
            return body
    # Prefer explicitly tagged yaml fences
    if not text:
        return ""
    raw = text.strip()
    m = re.search(r"```(?:yaml|yml)\s*\n(.*?)```", raw, re.DOTALL | re.IGNORECASE)
    if m:
        return m.group(1).strip()
    m = re.search(r"```\s*\n(.*?)```", raw, re.DOTALL)
    if m and looks_like_yaml_body(m.group(1)):
        return m.group(1).strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:yaml|yml)?\s*", "", raw, flags=re.I)
        raw = re.sub(r"\s*```$", "", raw)
    return raw.strip()


def looks_like_yaml_body(text: str) -> bool:
    t = (text or "").strip()
    return bool(
        re.search(r"(?m)^appId:\s*\S+", t)
        or ("---" in t and re.search(r"(?m)^\s*-\s*\w+", t))
    )


_FENCE_RE = re.compile(
    r"```(?P<lang>[^\n`]*)\n(?P<body>.*?)```",
    re.DOTALL,
)


def extract_fenced_files(text: str) -> list[tuple[str, str]]:
    """Extract fenced blocks as (filename, body).

    Supported headers::

        ```yaml
        ```yaml flow.yaml
        ```javascript helpers.js
        ```js file=helpers.js
    """
    if not text:
        return []
    out: list[tuple[str, str]] = []
    for m in _FENCE_RE.finditer(text):
        header = (m.group("lang") or "").strip()
        body = (m.group("body") or "").strip()
        if not body:
            continue
        name = _filename_from_fence_header(header, body)
        out.append((name, body))
    return out


def _filename_from_fence_header(header: str, body: str) -> str:
    h = header.strip()
    if not h:
        return "flow.yaml" if looks_like_yaml_body(body) else "script.js"

    # file=name or path in header
    file_m = re.search(r"(?:file|filename|name)\s*[=:]\s*(\S+)", h, re.I)
    if file_m:
        return file_m.group(1).strip().strip("\"'")

    parts = h.split()
    lang = parts[0].lower() if parts else ""
    # ```yaml flow.yaml  or  ```javascript helpers.js
    if len(parts) >= 2 and ("." in parts[1] or parts[1].endswith((".js", ".yaml", ".yml"))):
        return parts[1]

    # first line of body: // file: helpers.js  or  # file: flow.yaml
    first = body.splitlines()[0].strip() if body else ""
    file_line = re.match(
        r"^(?://|#)\s*file:\s*(\S+)",
        first,
        re.I,
    )
    if file_line:
        return file_line.group(1).strip()

    if lang in ("yaml", "yml"):
        return "flow.yaml"
    if lang in ("js", "javascript", "ecmascript"):
        return "helpers.js"
    if lang.endswith((".js", ".yaml", ".yml")):
        return lang
    return "flow.yaml" if looks_like_yaml_body(body) else "script.js"
