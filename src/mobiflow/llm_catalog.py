"""Multi-provider LLM catalog (`llm.json`).

mobiflow.config.yaml only picks which catalog entries to use:

    llm:
      catalog: llm.json
      discovery: azure-gpt4o    # adaptive explore / plan on device
      codegen: anthropic-sonnet  # Maestro YAML authoring
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

LLM_CATALOG_FILENAME = "llm.json"

_ENV_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _check_env_name(value: str, field: str) -> str:
    name = value.strip()
    looks_like_secret = (
        not _ENV_NAME_RE.match(name)
        or len(name) > 64
        or (len(name) >= 20 and any(c.islower() for c in name))
    )
    if looks_like_secret:
        raise ValueError(
            f"{field} must be an environment variable NAME, not a secret value."
        )
    return name


class ModelEntry(BaseModel):
    """One named LLM profile in llm.json."""

    provider: str  # openai | azure | anthropic | google
    model: Optional[str] = None
    deployment: Optional[str] = None
    api_key_env: str = "MOBIFLOW_LLM_API_KEY"
    label: Optional[str] = None
    endpoint: Optional[str] = None
    endpoint_env: str = "AZURE_OPENAI_ENDPOINT"
    api_version: str = "2025-03-01-preview"

    @field_validator("api_key_env")
    @classmethod
    def _api_key_env(cls, v: str) -> str:
        return _check_env_name(v, "api_key_env")

    @field_validator("endpoint_env")
    @classmethod
    def _endpoint_env(cls, v: str) -> str:
        return _check_env_name(v, "endpoint_env")

    @model_validator(mode="after")
    def _normalize_azure(self) -> ModelEntry:
        provider = (self.provider or "").lower()
        if not self.model and self.deployment:
            self.model = self.deployment
        if not self.deployment and self.model and provider.startswith("azure"):
            self.deployment = self.short_model()
        if provider.startswith("azure") and not (self.deployment or self.model):
            raise ValueError(
                "Azure profiles need deployment (Azure deployment name) "
                "and usually model (base model id, e.g. gpt-4o)."
            )
        if not self.model and not self.deployment:
            raise ValueError("Each llm.json profile needs model and/or deployment.")
        return self

    @property
    def display_name(self) -> str:
        if self.label:
            return self.label
        provider = self.provider.lower()
        if provider.startswith("azure"):
            return f"azure/{self.deployment_name()}"
        return f"{self.provider}/{self.short_model()}"

    def resolve_api_key(self) -> str:
        key = os.environ.get(self.api_key_env)
        if not key:
            raise ValueError(
                f"Set {self.api_key_env} in the environment for model "
                f"'{self.display_name}'. Keys are never stored in llm.json."
            )
        return key

    def resolve_endpoint(self) -> str:
        endpoint = self.endpoint or os.environ.get(self.endpoint_env)
        if not endpoint:
            raise ValueError(
                f"Azure/custom endpoint missing for '{self.display_name}'. "
                f"Set endpoint in llm.json or export {self.endpoint_env}."
            )
        return endpoint.rstrip("/")

    def short_model(self) -> str:
        m = self.model or self.deployment or ""
        return m.split("/", 1)[-1] if "/" in m else m

    def deployment_name(self) -> str:
        dep = self.deployment or self.model or ""
        return dep.split("/", 1)[-1] if "/" in dep else dep

    def to_public_dict(self) -> dict[str, Any]:
        data = self.model_dump(exclude_none=True)
        data["api_key_set"] = bool(os.environ.get(self.api_key_env))
        if self.provider.lower().startswith("azure") or self.endpoint:
            data["endpoint_set"] = bool(
                self.endpoint or os.environ.get(self.endpoint_env)
            )
            data["deployment"] = self.deployment_name()
        return data


class LlmCatalog(BaseModel):
    version: int = 1
    models: dict[str, ModelEntry] = Field(default_factory=dict)

    def get(self, name: str) -> ModelEntry:
        if name not in self.models:
            known = ", ".join(sorted(self.models)) or "(empty)"
            raise KeyError(
                f"Unknown LLM profile {name!r} in {LLM_CATALOG_FILENAME}. "
                f"Known: {known}"
            )
        return self.models[name]

    def names(self) -> list[str]:
        return sorted(self.models.keys())


def catalog_path(
    repo: Path | str | None = None, *, filename: str = LLM_CATALOG_FILENAME
) -> Path:
    base = Path(repo).expanduser().resolve() if repo else Path.cwd()
    return base / filename


def load_catalog(
    repo: Path | str | None = None,
    *,
    filename: str = LLM_CATALOG_FILENAME,
) -> LlmCatalog:
    path = catalog_path(repo, filename=filename)
    if not path.exists():
        raise FileNotFoundError(
            f"No {filename} at {path}. Run `mobiflow init` or copy llm.json.example."
        )
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, list):
        models = {}
        for item in raw:
            mid = item.pop("id", None) or item.pop("name", None)
            if not mid:
                raise ValueError("Each llm.json list entry needs an id/name")
            models[mid] = item
        raw = {"version": 1, "models": models}
    return LlmCatalog.model_validate(raw)


def save_catalog(catalog: LlmCatalog, repo: Path | str | None = None) -> Path:
    path = catalog_path(repo)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": catalog.version,
        "models": {
            name: entry.model_dump(mode="json", exclude_none=True)
            for name, entry in catalog.models.items()
        },
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def default_catalog_seed() -> LlmCatalog:
    """Starter profiles — edit endpoints/models for your org."""
    return LlmCatalog(
        version=1,
        models={
            "openai-gpt4o": ModelEntry(
                provider="openai",
                model="gpt-4o",
                api_key_env="OPENAI_API_KEY",
                label="OpenAI GPT-4o",
            ),
            "azure-gpt4o": ModelEntry(
                provider="azure",
                model="gpt-4o",
                deployment="gpt-4o",
                api_key_env="AZURE_OPENAI_API_KEY",
                endpoint_env="AZURE_OPENAI_ENDPOINT",
                label="Azure OpenAI GPT-4o",
            ),
            "anthropic-sonnet": ModelEntry(
                provider="anthropic",
                model="claude-sonnet-4-6",
                api_key_env="ANTHROPIC_API_KEY",
                label="Anthropic Claude Sonnet",
            ),
            "google-gemini-flash": ModelEntry(
                provider="google",
                model="gemini-2.0-flash",
                api_key_env="GOOGLE_API_KEY",
                label="Google Gemini 2.0 Flash",
            ),
        },
    )


def render_example_catalog() -> str:
    return (
        json.dumps(
            {
                "version": 1,
                "models": {
                    name: e.model_dump(mode="json", exclude_none=True)
                    for name, e in default_catalog_seed().models.items()
                },
            },
            indent=2,
        )
        + "\n"
    )
