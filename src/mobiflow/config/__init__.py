"""Load and validate mobiflow.config.yaml. Secrets come from env vars only.

User-facing config:

    project / llm / stack / run / device
"""

from __future__ import annotations

import os
import re
from enum import Enum
from pathlib import Path
from typing import Any, Optional

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

CONFIG_FILENAME = "mobiflow.config.yaml"

_ENV_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _validate_env_var_name(value: str, field: str) -> str:
    name = value.strip()
    looks_like_secret = (
        not _ENV_NAME_RE.match(name)
        or len(name) > 64
        or (len(name) >= 20 and any(c.islower() for c in name))
    )
    if looks_like_secret:
        raise ValueError(
            f"llm.{field} must be the NAME of an environment variable "
            f"(e.g. AZURE_OPENAI_API_KEY), not a value. Got a {len(name)}-character "
            "string that looks like a secret. Secrets never belong in "
            f"{CONFIG_FILENAME} — export it in your shell instead."
        )
    return name


class _StrictLoader(yaml.SafeLoader):
    """SafeLoader that rejects duplicate mapping keys."""


def _no_duplicate_keys(loader: _StrictLoader, node: yaml.MappingNode, deep: bool = False):
    seen: set[Any] = set()
    for key_node, _ in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in seen:
            raise yaml.YAMLError(
                f"Duplicate key {key!r} at line {key_node.start_mark.line + 1} "
                f"of {CONFIG_FILENAME}."
            )
        seen.add(key)
    return yaml.SafeLoader.construct_mapping(loader, node, deep=deep)


_StrictLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _no_duplicate_keys
)


class ProjectMode(str, Enum):
    EXISTING = "existing"
    LOCAL = "local"
    NEW = "new"


class LlmConfig(BaseModel):
    """Selects catalog profiles for discovery (adaptive explore) and codegen (YAML)."""

    catalog: str = "llm.json"
    discovery: str | None = None  # adaptive plan / device explore
    codegen: str | None = None  # Maestro YAML authoring

    # Legacy inline (used when discovery/codegen unset)
    provider: str = "openai"
    model: str | None = None
    api_key_env: str = "MOBIFLOW_LLM_API_KEY"
    endpoint: str | None = None
    azure_endpoint: str | None = None
    azure_endpoint_env: str = "AZURE_OPENAI_ENDPOINT"
    azure_api_version: str = "2025-03-01-preview"

    @field_validator("api_key_env")
    @classmethod
    def _check_api_key_env(cls, v: str) -> str:
        return _validate_env_var_name(v, "api_key_env")

    @field_validator("azure_endpoint_env")
    @classmethod
    def _check_azure_endpoint_env(cls, v: str) -> str:
        return _validate_env_var_name(v, "azure_endpoint_env")

    @model_validator(mode="after")
    def _normalize(self) -> LlmConfig:
        if self.endpoint and not self.azure_endpoint:
            self.azure_endpoint = self.endpoint
        if self.azure_endpoint and not self.endpoint:
            self.endpoint = self.azure_endpoint
        if self.discovery and not self.codegen:
            self.codegen = self.discovery
        if self.codegen and not self.discovery:
            self.discovery = self.codegen
        return self

    @property
    def uses_catalog(self) -> bool:
        return bool(self.discovery or self.codegen)


class StackConfig(BaseModel):
    tool: str = "maestro"  # maestro
    # yaml = YAML-only flows; yaml+js / javascript = Maestro YAML + JS (evalScript/runScript)
    language: str = "yaml+js"
    runner: str = "maestro"  # maestro test
    flow_dir: str = "flows"
    cases_dir: str = "cases"
    scripts_dir: str = "flows/scripts"  # companion .js next to / under flows

    def js_enabled(self) -> bool:
        lang = (self.language or "yaml").strip().lower().replace(" ", "")
        return lang in {"yaml+js", "yamljs", "js", "javascript", "maestro+js"}


class DeviceConfig(BaseModel):
    """Local or cloud device lab settings.

    ``provider``:
      - ``local`` — adb / Android AVD / iOS Simulator (default)
      - ``browserstack`` — BrowserStack App Automate Maestro REST API
      - ``testmu`` — TestMu AI (formerly LambdaTest) HyperExecute Maestro
    """

    provider: str = "local"  # local | browserstack | testmu
    platform: str = "android"  # android | ios
    app_id: str = ""
    device_id: str | None = None  # local serial/UDID OR cloud device name
    auto_start: bool = True  # local only: start AVD / iOS Simulator if none online
    boot_timeout_s: int = 120  # wait for emulator/simulator boot

    # Cloud labs (BrowserStack / TestMu)
    app_path: str = ""  # local .apk / .ipa / .aab to upload
    app_url: str = ""  # already-uploaded bs://… or lt://…
    cloud_project: str = "MobiFlow"
    cloud_build_name: str = ""
    real_mobile: bool = True  # TestMu: real device vs virtual
    username_env: str = ""  # override default credential env var names
    access_key_env: str = ""
    cloud_timeout_s: int = 1800  # cloud build/job timeout
    poll_interval_s: float = 15.0  # BrowserStack status poll
    browserstack_local: bool = False  # enable BS local testing flag

    @field_validator("provider")
    @classmethod
    def _check_provider(cls, v: str) -> str:
        from mobiflow.cloud.base import normalize_provider

        return normalize_provider(v).value

    def is_cloud(self) -> bool:
        from mobiflow.cloud.base import is_cloud_provider

        return is_cloud_provider(self.provider)


class RunConfig(BaseModel):
    heal: int = 2  # YAML repair attempts after failed run
    adaptive: bool = True  # hierarchy-aware heal / explore on live device
    explore: bool = True  # explore app with discovery LLM before codegen
    explore_steps: int = 5  # max live explore actions before codegen
    timeout_s: int = 180  # maestro test timeout
    save_artifacts: bool = True
    # Reporting: junit | html (comma-string or list). Empty / none disables.
    reports: list[str] = Field(default_factory=lambda: ["junit", "html"])
    report_dir: str = ".mobiflow/reports"  # relative to project path
    # Completeness foundations (suite / flake / reuse / secrets — wired in later phases)
    retries: int = 0  # re-run same YAML on failure before heal
    reuse_flow: bool = False  # prefer flows/<case>.yaml over LLM codegen
    fail_fast: bool = False  # suite: stop after first failing case
    jobs: int = 1  # suite parallelism (1 = sequential)
    env: dict[str, str] = Field(default_factory=dict)  # Maestro --env KEY=VALUE

    @field_validator("reports", mode="before")
    @classmethod
    def _coerce_reports(cls, v: Any) -> list[str]:
        from mobiflow.reporting import normalize_report_formats

        return normalize_report_formats(v)

    @field_validator("explore_steps")
    @classmethod
    def _clamp_explore_steps(cls, v: int) -> int:
        try:
            n = int(v)
        except (TypeError, ValueError):
            return 5
        return max(1, min(n, 12))

    @field_validator("retries")
    @classmethod
    def _clamp_retries(cls, v: int) -> int:
        try:
            n = int(v)
        except (TypeError, ValueError):
            return 0
        return max(0, min(n, 10))

    @field_validator("jobs")
    @classmethod
    def _clamp_jobs(cls, v: int) -> int:
        try:
            n = int(v)
        except (TypeError, ValueError):
            return 1
        return max(1, min(n, 32))

    @field_validator("env", mode="before")
    @classmethod
    def _coerce_env(cls, v: Any) -> dict[str, str]:
        if v is None:
            return {}
        if not isinstance(v, dict):
            raise ValueError("run.env must be a mapping of KEY: VALUE")
        out: dict[str, str] = {}
        for key, val in v.items():
            k = str(key).strip()
            if not k:
                continue
            out[k] = "" if val is None else str(val)
        return out


class ProjectConfig(BaseModel):
    mode: ProjectMode = ProjectMode.LOCAL
    path: str = "."


class MobiflowConfig(BaseModel):
    project: ProjectConfig = Field(default_factory=ProjectConfig)
    llm: LlmConfig = Field(default_factory=LlmConfig)
    stack: StackConfig = Field(default_factory=StackConfig)
    device: DeviceConfig = Field(default_factory=DeviceConfig)
    run: RunConfig = Field(default_factory=RunConfig)

    def repo_path(self) -> Path:
        return Path(self.project.path).expanduser().resolve()

    def flow_dir_path(self) -> Path:
        return (self.repo_path() / self.stack.flow_dir).resolve()

    def scripts_dir_path(self) -> Path:
        raw = (self.stack.scripts_dir or "flows/scripts").strip() or "flows/scripts"
        p = Path(raw).expanduser()
        if p.is_absolute():
            return p.resolve()
        return (self.repo_path() / p).resolve()

    def cases_dir_path(self) -> Path:
        return (self.repo_path() / self.stack.cases_dir).resolve()

    def artifacts_dir(self) -> Path:
        return (self.repo_path() / ".mobiflow").resolve()

    def report_dir_path(self) -> Path:
        raw = (self.run.report_dir or ".mobiflow/reports").strip() or ".mobiflow/reports"
        p = Path(raw).expanduser()
        if p.is_absolute():
            return p.resolve()
        return (self.repo_path() / p).resolve()

    def catalog_file(self) -> Path:
        name = self.llm.catalog or "llm.json"
        return self.repo_path() / name

    def load_catalog(self):
        from mobiflow.llm_catalog import ModelEntry, load_catalog

        path = self.catalog_file()
        if path.exists():
            return load_catalog(self.repo_path(), filename=path.name)
        # synthesize one-entry catalog from legacy inline
        from mobiflow.llm_catalog import LlmCatalog

        entry = ModelEntry(
            provider=self.llm.provider,
            model=self.llm.model or "gpt-4o",
            api_key_env=self.llm.api_key_env,
            endpoint=self.llm.endpoint or self.llm.azure_endpoint,
            endpoint_env=self.llm.azure_endpoint_env,
            api_version=self.llm.azure_api_version,
        )
        return LlmCatalog(models={"default": entry})

    def discovery_profile(self):
        from mobiflow.llm_catalog import ModelEntry

        cat = self.load_catalog()
        name = self.llm.discovery
        if name:
            return cat.get(name)
        if "default" in cat.models:
            return cat.get("default")
        if cat.models:
            return cat.get(next(iter(cat.models)))
        return ModelEntry(
            provider=self.llm.provider,
            model=self.llm.model or "gpt-4o",
            api_key_env=self.llm.api_key_env,
            endpoint=self.llm.endpoint or self.llm.azure_endpoint,
            endpoint_env=self.llm.azure_endpoint_env,
            api_version=self.llm.azure_api_version,
        )

    def codegen_profile(self):
        cat = self.load_catalog()
        name = self.llm.codegen or self.llm.discovery
        if name:
            return cat.get(name)
        return self.discovery_profile()


def config_path(repo: Path | str | None = None) -> Path:
    base = Path(repo).expanduser().resolve() if repo else Path.cwd()
    return base / CONFIG_FILENAME


def load_config(repo: Path | str | None = None) -> MobiflowConfig:
    path = config_path(repo)
    if not path.exists():
        cwd_path = Path.cwd() / CONFIG_FILENAME
        if repo is None and cwd_path.exists():
            path = cwd_path
        else:
            raise FileNotFoundError(
                f"No {CONFIG_FILENAME} found at {path}. Run `mobiflow init` first."
            )
    data = yaml.load(path.read_text(), Loader=_StrictLoader) or {}
    return MobiflowConfig.model_validate(data)


def render_simple_config(config: MobiflowConfig) -> str:
    llm = config.llm
    stack = config.stack
    run = config.run
    device = config.device
    discovery = llm.discovery or "default"
    codegen = llm.codegen or discovery

    lines = [
        "# mobiflow.config.yaml — pick models from llm.json",
        "# Secrets stay in env vars (never paste API keys here).",
        "# Docs: MOBIFLOW.md",
        "",
        "project:",
        f"  mode: {config.project.mode.value}",
        f"  path: {config.project.path}",
        "",
        "llm:",
        f"  catalog: {llm.catalog or 'llm.json'}   # model catalog file",
        f"  discovery: {discovery}   # adaptive explore / plan on device",
        f"  codegen: {codegen}       # Maestro YAML authoring",
        "",
        "stack:",
        f"  tool: {stack.tool}",
        f"  language: {stack.language}   # yaml | yaml+js (Maestro JS via evalScript/runScript)",
        f"  runner: {stack.runner}",
        f"  flow_dir: {stack.flow_dir}",
        f"  scripts_dir: {stack.scripts_dir}   # companion .js files",
        f"  cases_dir: {stack.cases_dir}",
        "",
        "device:",
        f"  provider: {device.provider}   # local | browserstack | testmu",
        f"  platform: {device.platform}",
        f"  app_id: {device.app_id or '\"\"'}   # e.g. org.wikipedia / org.wikimedia.wikipedia",
        f"  device_id: {device.device_id or '\"\"'}  # local serial/UDID OR cloud device (e.g. Google Pixel 7-13.0)",
        f"  auto_start: {str(device.auto_start).lower()}   # local only: start AVD / Xcode sim if none online",
        f"  boot_timeout_s: {device.boot_timeout_s}",
        f"  app_path: {device.app_path or '\"\"'}   # cloud: path to .apk / .ipa to upload",
        f"  app_url: {device.app_url or '\"\"'}    # cloud: existing bs://… or lt://… (skip upload)",
        f"  cloud_project: {device.cloud_project or 'MobiFlow'}",
        f"  cloud_build_name: {device.cloud_build_name or '\"\"'}",
        f"  real_mobile: {str(device.real_mobile).lower()}   # testmu: real device vs emulator/simulator",
        f"  username_env: {device.username_env or '\"\"'}   # optional override (defaults by provider)",
        f"  access_key_env: {device.access_key_env or '\"\"'}",
        f"  cloud_timeout_s: {device.cloud_timeout_s}",
        "",
        "run:",
        f"  heal: {run.heal}          # YAML repair attempts (0 = off)",
        f"  adaptive: {str(run.adaptive).lower()}   # hierarchy-aware heal on live device",
        f"  explore: {str(run.explore).lower()}    # discovery LLM explores app before codegen",
        f"  explore_steps: {run.explore_steps}   # max live explore actions",
        f"  timeout_s: {run.timeout_s}",
        f"  save_artifacts: {str(run.save_artifacts).lower()}",
        f"  reports: [{', '.join(run.reports) if run.reports else ''}]   # junit, html — empty disables",
        f"  report_dir: {run.report_dir}",
        f"  retries: {run.retries}       # re-run same YAML before heal (flake control)",
        f"  reuse_flow: {str(run.reuse_flow).lower()}  # use flows/<case>.yaml instead of LLM",
        f"  fail_fast: {str(run.fail_fast).lower()}   # suite: stop on first failure",
        f"  jobs: {run.jobs}           # suite parallelism (1 = sequential)",
        "",
        "# Edit llm.json to add Azure / OpenAI / Anthropic / Google models.",
        "# Then change discovery: / codegen: above to the profile ids you want.",
        "",
    ]
    return "\n".join(lines)


def save_config(config: MobiflowConfig, repo: Path | str | None = None) -> Path:
    path = config_path(repo or config.repo_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_simple_config(config), encoding="utf-8")
    return path


def find_config(start: Path | None = None) -> Path | None:
    cur = (start or Path.cwd()).resolve()
    for candidate in [cur, *cur.parents]:
        p = candidate / CONFIG_FILENAME
        if p.exists():
            return p
    return None


def config_warnings(config: MobiflowConfig) -> list[str]:
    out: list[str] = []
    try:
        disc = config.discovery_profile()
        if not os.environ.get(disc.api_key_env):
            out.append(
                f"discovery: ${disc.api_key_env} is not set ({disc.display_name})."
            )
        if disc.provider.lower().startswith("azure"):
            if not (disc.endpoint or os.environ.get(disc.endpoint_env)):
                out.append(
                    f"discovery Azure endpoint missing "
                    f"(llm.json endpoint or ${disc.endpoint_env})."
                )
    except Exception as e:  # noqa: BLE001
        out.append(f"discovery LLM: {e}")

    try:
        code = config.codegen_profile()
        if code.api_key_env != getattr(config.discovery_profile(), "api_key_env", None):
            if not os.environ.get(code.api_key_env):
                out.append(
                    f"codegen: ${code.api_key_env} is not set ({code.display_name})."
                )
    except Exception as e:  # noqa: BLE001
        out.append(f"codegen LLM: {e}")

    if not config.catalog_file().exists() and not config.llm.uses_catalog:
        out.append(
            f"No {config.llm.catalog} found — using legacy inline llm settings. "
            "Run mobiflow init or add llm.json for multi-model support."
        )

    if config.device.is_cloud():
        try:
            from mobiflow.cloud import cloud_readiness

            ready = cloud_readiness(config.device)
            if not ready.get("ready"):
                out.append(ready.get("message") or "Cloud device lab not ready.")
        except Exception as e:  # noqa: BLE001
            out.append(f"cloud device: {e}")
    return out


def effective_config_dict(config: MobiflowConfig) -> dict[str, Any]:
    data: dict[str, Any] = {
        "project": config.project.model_dump(mode="json"),
        "llm": {
            "catalog": config.llm.catalog,
            "discovery": config.llm.discovery,
            "codegen": config.llm.codegen,
        },
        "stack": config.stack.model_dump(mode="json"),
        "device": config.device.model_dump(mode="json"),
        "run": config.run.model_dump(mode="json"),
    }
    try:
        data["llm"]["discovery_profile"] = config.discovery_profile().to_public_dict()
    except Exception as e:  # noqa: BLE001
        data["llm"]["discovery_error"] = str(e)
    try:
        data["llm"]["codegen_profile"] = config.codegen_profile().to_public_dict()
    except Exception as e:  # noqa: BLE001
        data["llm"]["codegen_error"] = str(e)
    return data
