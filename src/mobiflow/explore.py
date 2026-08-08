"""Explore-then-generate: discovery LLM walks the app before codegen."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from typing import Any

from mobiflow.llm import invoke_chat_text, profile_to_llm_config
from mobiflow.llm_catalog import ModelEntry

logger = logging.getLogger(__name__)

ProgressFn = Callable[[str], None] | None

_JSON_FENCE_RE = re.compile(
    r"```(?:json)?\s*\n(.*?)```",
    re.DOTALL | re.IGNORECASE,
)

_EXPLORE_SYSTEM = """You are a mobile QA explorer for Maestro automation.
You observe the current screen hierarchy and decide the next exploration step
toward the user's test goal. You do NOT write the final Maestro test yet.

Respond with ONLY a JSON object (optionally in a ```json fence) with keys:
{
  "status": "continue" | "done",
  "observation": "what you see on this screen that matters for the goal",
  "screen": "short screen name/label",
  "plan_so_far": ["ordered steps discovered so far toward the goal"],
  "selectors": [{"label": "human name", "text": "visible text or id hint"}],
  "next_action": null | {
      "command": "tapOn|scroll|swipe|inputText|pressKey|scrollUntilVisible|waitForAnimationToEnd",
      "text": "selector or value when needed",
      "optional": false
  },
  "notes": "risks, onboarding to dismiss, assertions to make later"
}

Rules:
1) Prefer stable visible text selectors from the hierarchy.
2) If onboarding/dialogs block the goal, dismiss them first (Skip/Next/Continue/Allow/Not now).
3) status=done when you have enough grounded steps/selectors to author a full test.
4) next_action must be ONE atomic UI action when status=continue.
5) Never invent UI that is not supported by the hierarchy (unless launching/navigating obviously required).
6) Keep plan_so_far cumulative and specific.
"""


@dataclass
class ExploreAction:
    command: str
    text: str = ""
    optional: bool = False

    def to_maestro_lines(self) -> list[str]:
        cmd = (self.command or "").strip()
        if not cmd:
            return []
        # Normalize common aliases
        aliases = {
            "tap": "tapOn",
            "click": "tapOn",
            "type": "inputText",
            "entertext": "inputText",
            "press": "pressKey",
            "scroll_until": "scrollUntilVisible",
            "wait": "waitForAnimationToEnd",
        }
        cmd = aliases.get(cmd.lower().replace(" ", ""), cmd)
        if cmd == "waitForAnimationToEnd":
            return ["- waitForAnimationToEnd"]
        if cmd == "scroll":
            return ["- scroll"]
        if cmd == "swipe":
            return ["- swipe:", "    direction: UP"]
        if cmd == "pressKey":
            key = self.text or "Enter"
            return [f"- pressKey: {key}"]
        if cmd == "inputText":
            return [f'- inputText: "{_escape(self.text)}"']
        if cmd == "scrollUntilVisible":
            return [
                "- scrollUntilVisible:",
                f'    text: "{_escape(self.text)}"',
                "    direction: DOWN",
            ]
        # default tapOn
        line = f'- tapOn: "{_escape(self.text)}"'
        if self.optional:
            return ["- tapOn:", f'    text: "{_escape(self.text)}"', "    optional: true"]
        return [line]


@dataclass
class ExploreStep:
    index: int
    screen: str = ""
    observation: str = ""
    action: ExploreAction | None = None
    action_ok: bool | None = None
    hierarchy_excerpt: str = ""
    notes: str = ""


@dataclass
class ExplorationResult:
    goal: str
    app_id: str
    platform: str
    steps: list[ExploreStep] = field(default_factory=list)
    plan: list[str] = field(default_factory=list)
    selectors: list[dict[str, str]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    final_hierarchy: str = ""
    completed: bool = False
    mode: str = "device"  # device | plan_only | skipped

    def to_prompt_block(self) -> str:
        """Serialize for codegen LLM context."""
        if self.mode == "skipped" or (not self.steps and not self.plan):
            return ""
        lines = [
            "Exploration results (observe the app BEFORE writing YAML):",
            f"mode: {self.mode}",
            f"appId: {self.app_id}",
            f"platform: {self.platform}",
        ]
        if self.plan:
            lines.append("Grounded plan:")
            for i, step in enumerate(self.plan, 1):
                lines.append(f"  {i}. {step}")
        if self.selectors:
            lines.append("Observed selectors:")
            for sel in self.selectors[:40]:
                label = sel.get("label") or sel.get("text") or ""
                text = sel.get("text") or ""
                lines.append(f"  - {label}: {text}".rstrip(": "))
        if self.notes:
            lines.append("Explorer notes:")
            for n in self.notes[-12:]:
                lines.append(f"  - {n}")
        if self.steps:
            lines.append("Screen observations:")
            for st in self.steps:
                act = ""
                if st.action:
                    act = f" → {st.action.command} {st.action.text}".rstrip()
                    if st.action_ok is not None:
                        act += " (ok)" if st.action_ok else " (failed)"
                lines.append(
                    f"  [{st.index}] {st.screen or 'screen'}: {st.observation}{act}"
                )
        if self.final_hierarchy.strip():
            lines.append(
                "Final hierarchy (truncated):\n" + self.final_hierarchy.strip()[:8000]
            )
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _escape(text: str) -> str:
    return (text or "").replace("\\", "\\\\").replace('"', '\\"')


def extract_json_object(text: str) -> dict[str, Any]:
    """Best-effort parse of a JSON object from model output."""
    raw = (text or "").strip()
    if not raw:
        return {}
    m = _JSON_FENCE_RE.search(raw)
    if m:
        raw = m.group(1).strip()
    # Find outermost {...}
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        raw = raw[start : end + 1]
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        # Trailing commas / light repair
        repaired = re.sub(r",\s*([}\]])", r"\1", raw)
        try:
            data = json.loads(repaired)
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            logger.warning("Explore decision JSON parse failed")
            return {}


def parse_explore_decision(text: str) -> dict[str, Any]:
    data = extract_json_object(text)
    status = str(data.get("status") or "done").strip().lower()
    if status not in {"continue", "done"}:
        status = "done"
    action_raw = data.get("next_action")
    action: ExploreAction | None = None
    if isinstance(action_raw, dict) and status == "continue":
        cmd = str(action_raw.get("command") or action_raw.get("type") or "").strip()
        if cmd:
            action = ExploreAction(
                command=cmd,
                text=str(action_raw.get("text") or action_raw.get("value") or ""),
                optional=bool(action_raw.get("optional") or False),
            )
    plan = data.get("plan_so_far") or data.get("plan") or []
    if not isinstance(plan, list):
        plan = [str(plan)]
    selectors = data.get("selectors") or []
    if not isinstance(selectors, list):
        selectors = []
    norm_sels: list[dict[str, str]] = []
    for sel in selectors:
        if isinstance(sel, dict):
            norm_sels.append(
                {
                    "label": str(sel.get("label") or sel.get("name") or ""),
                    "text": str(sel.get("text") or sel.get("id") or ""),
                }
            )
        elif isinstance(sel, str):
            norm_sels.append({"label": sel, "text": sel})
    return {
        "status": status,
        "observation": str(data.get("observation") or ""),
        "screen": str(data.get("screen") or ""),
        "plan": [str(p) for p in plan if str(p).strip()],
        "selectors": norm_sels,
        "action": action,
        "notes": str(data.get("notes") or ""),
    }


def build_action_flow_yaml(app_id: str, action: ExploreAction, *, launch: bool = False) -> str:
    lines = [f"appId: {app_id}", "name: MobiFlow explore step", "---"]
    if launch:
        lines.append("- launchApp")
    lines.extend(action.to_maestro_lines())
    return "\n".join(lines) + "\n"


def build_launch_flow_yaml(app_id: str) -> str:
    return (
        f"appId: {app_id}\n"
        f"name: MobiFlow explore launch\n"
        f"---\n"
        f"- launchApp\n"
    )


def summarize_hierarchy(hierarchy: str, *, limit: int = 3500) -> str:
    text = (hierarchy or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit] + "\n…(truncated)"


async def decide_explore_step(
    *,
    goal: str,
    app_id: str,
    platform: str,
    hierarchy: str,
    plan: list[str],
    history: list[str],
    profile: ModelEntry,
    step_index: int,
    max_steps: int,
) -> dict[str, Any]:
    llm_config = profile_to_llm_config(profile)
    user = "\n\n".join(
        [
            f"Platform: {platform}",
            f"App ID: {app_id}",
            f"Explore step: {step_index}/{max_steps}",
            f"Goal:\n{goal}",
            "Plan so far:\n"
            + ("\n".join(f"- {p}" for p in plan) if plan else "- (empty)"),
            "Recent history:\n"
            + ("\n".join(f"- {h}" for h in history[-8:]) if history else "- (none)"),
            "Current hierarchy (truncated):\n" + summarize_hierarchy(hierarchy),
            "Return the JSON decision now.",
        ]
    )
    text = await asyncio.to_thread(
        invoke_chat_text,
        _EXPLORE_SYSTEM,
        user,
        llm_config,
        max_tokens=2048,
        temperature=0.2,
        log_prefix="MobiFlowExplore",
    )
    return parse_explore_decision(text or "")


async def plan_only_explore(
    *,
    goal: str,
    app_id: str,
    platform: str,
    profile: ModelEntry,
    progress: ProgressFn = None,
) -> ExplorationResult:
    """No device: ask discovery LLM for a grounded plan from the goal alone."""
    if progress:
        progress("Explore (plan-only — no live device hierarchy)…")
    llm_config = profile_to_llm_config(profile)
    system = (
        _EXPLORE_SYSTEM
        + "\nNo hierarchy is available. Set status=done and produce the best "
        "plan_so_far + likely selectors from the goal. next_action must be null."
    )
    user = (
        f"Platform: {platform}\nApp ID: {app_id}\nGoal:\n{goal}\n"
        "Return JSON with status=done, plan_so_far, selectors, notes."
    )
    text = await asyncio.to_thread(
        invoke_chat_text,
        system,
        user,
        llm_config,
        max_tokens=2048,
        temperature=0.2,
        log_prefix="MobiFlowExplore",
    )
    decision = parse_explore_decision(text or "")
    result = ExplorationResult(
        goal=goal,
        app_id=app_id,
        platform=platform,
        plan=decision.get("plan") or [],
        selectors=decision.get("selectors") or [],
        notes=[decision["notes"]] if decision.get("notes") else [],
        completed=True,
        mode="plan_only",
    )
    if decision.get("observation"):
        result.steps.append(
            ExploreStep(
                index=1,
                screen=decision.get("screen") or "planned",
                observation=decision.get("observation") or "",
                notes=decision.get("notes") or "",
            )
        )
    return result


# Interactive decision: accept | skip | edit | done | quit
AskFn = Callable[[dict[str, Any]], dict[str, Any]]


async def explore_app(
    goal: str,
    *,
    app_id: str,
    platform: str,
    device_id: str,
    profile: ModelEntry,
    max_steps: int = 5,
    step_timeout_s: int = 90,
    progress: ProgressFn = None,
    interactive: bool = False,
    ask: AskFn | None = None,
) -> ExplorationResult:
    """Live explore loop: hierarchy → discovery decision → optional nav action.

    When ``interactive=True``, each proposed action is confirmed via ``ask``
    (or a default stdin prompt). Choices: accept | skip | edit | done | quit.
    This is a separate operator-driven mode — not Maestro Studio.
    """
    from mobiflow.maestro import fetch_hierarchy, resolve_app_id, run_flow_yaml

    resolved = resolve_app_id(app_id, platform, goal)
    result = ExplorationResult(
        goal=goal,
        app_id=resolved,
        platform=platform,
        mode="interactive" if interactive else "device",
    )
    history: list[str] = []
    max_steps = max(1, min(int(max_steps or 5), 12))
    ask_fn = ask or (default_interactive_ask if interactive else None)

    if progress:
        progress(f"Explore: launching {resolved}…")
    launch = await run_flow_yaml(
        build_launch_flow_yaml(resolved),
        device_id=device_id,
        timeout_s=step_timeout_s,
    )
    history.append(
        "launchApp " + ("ok" if launch.get("ok") else f"failed:{launch.get('error')}")
    )

    for i in range(1, max_steps + 1):
        if progress:
            progress(f"Explore step {i}/{max_steps}: reading hierarchy…")
        hierarchy = await fetch_hierarchy(device_id)
        result.final_hierarchy = hierarchy
        decision = await decide_explore_step(
            goal=goal,
            app_id=resolved,
            platform=platform,
            hierarchy=hierarchy,
            plan=result.plan,
            history=history,
            profile=profile,
            step_index=i,
            max_steps=max_steps,
        )
        if decision.get("plan"):
            result.plan = decision["plan"]
        if decision.get("selectors"):
            # merge unique selectors
            seen = {(s.get("label"), s.get("text")) for s in result.selectors}
            for sel in decision["selectors"]:
                key = (sel.get("label"), sel.get("text"))
                if key not in seen and (sel.get("text") or sel.get("label")):
                    result.selectors.append(sel)
                    seen.add(key)
        if decision.get("notes"):
            result.notes.append(decision["notes"])

        step = ExploreStep(
            index=i,
            screen=decision.get("screen") or "",
            observation=decision.get("observation") or "",
            hierarchy_excerpt=summarize_hierarchy(hierarchy, limit=1200),
            notes=decision.get("notes") or "",
            action=decision.get("action"),
        )

        # Model thinks we're done
        if decision.get("status") == "done" or not decision.get("action"):
            if interactive and ask_fn is not None and decision.get("status") == "done":
                choice = ask_fn(
                    {
                        "kind": "done_proposal",
                        "step": i,
                        "max_steps": max_steps,
                        "decision": decision,
                        "hierarchy_excerpt": step.hierarchy_excerpt,
                    }
                )
                selected = str(choice.get("choice") or "done").lower()
                if selected == "quit":
                    result.notes.append("interactive: quit by operator")
                    result.steps.append(step)
                    break
                if selected == "skip":
                    # Operator wants to keep exploring despite model done
                    history.append("operator: continue after model done")
                    step.action = None
                    result.steps.append(step)
                    continue
            step.action = None
            result.steps.append(step)
            result.completed = True
            if progress:
                progress("Explore complete — enough context for codegen.")
            break

        action: ExploreAction = decision["action"]

        if interactive and ask_fn is not None:
            choice = ask_fn(
                {
                    "kind": "action_proposal",
                    "step": i,
                    "max_steps": max_steps,
                    "decision": decision,
                    "action": action,
                    "hierarchy_excerpt": step.hierarchy_excerpt,
                }
            )
            selected = str(choice.get("choice") or "accept").lower()
            if selected == "quit":
                result.notes.append("interactive: quit by operator")
                result.steps.append(step)
                break
            if selected == "done":
                step.action = None
                result.steps.append(step)
                result.completed = True
                if progress:
                    progress("Explore stopped by operator — ready for codegen.")
                break
            if selected == "skip":
                history.append(
                    f"operator skipped {action.command}:{action.text}"
                )
                step.action = None
                step.notes = (step.notes + " | skipped by operator").strip(" |")
                result.steps.append(step)
                continue
            if selected == "edit":
                edited = choice.get("action") or {}
                action = ExploreAction(
                    command=str(edited.get("command") or action.command),
                    text=str(edited.get("text") if "text" in edited else action.text),
                    optional=bool(edited.get("optional", action.optional)),
                )
                step.action = action

        if progress:
            progress(
                f"Explore step {i}/{max_steps}: {action.command} "
                f"{action.text or ''}".rstrip()
            )
        flow = build_action_flow_yaml(resolved, action, launch=False)
        run = await run_flow_yaml(
            flow,
            device_id=device_id,
            timeout_s=step_timeout_s,
        )
        step.action_ok = bool(run.get("ok"))
        history.append(
            f"{action.command}:{action.text} -> "
            + ("ok" if step.action_ok else f"fail:{run.get('error')}")
        )
        result.steps.append(step)
    else:
        result.completed = bool(result.plan or result.selectors)

    if not result.plan and result.steps:
        # Derive a minimal plan from observations
        result.plan = [
            s.observation
            for s in result.steps
            if s.observation
        ][:8]
    return result


def default_interactive_ask(payload: dict[str, Any]) -> dict[str, Any]:
    """Stdin/questionary prompt used by ``mobiflow explore --interactive``."""
    import questionary

    kind = payload.get("kind")
    decision = payload.get("decision") or {}
    step = payload.get("step")
    max_steps = payload.get("max_steps")
    print()
    print(f"— Explore {step}/{max_steps} —")
    if decision.get("screen"):
        print(f"Screen: {decision.get('screen')}")
    if decision.get("observation"):
        print(f"See:    {decision.get('observation')}")
    if decision.get("notes"):
        print(f"Notes:  {decision.get('notes')}")
    plan = decision.get("plan") or []
    if plan:
        print("Plan:   " + " → ".join(plan[-4:]))

    if kind == "done_proposal":
        choice = questionary.select(
            "Discovery thinks exploration is complete. What next?",
            choices=[
                questionary.Choice("Finish explore (use plan for codegen)", value="done"),
                questionary.Choice("Keep exploring", value="skip"),
                questionary.Choice("Quit", value="quit"),
            ],
            default="done",
        ).ask()
        return {"choice": choice or "done"}

    action: ExploreAction | None = payload.get("action")
    label = (
        f"{action.command} {action.text}".strip()
        if action
        else "(no action)"
    )
    choice = questionary.select(
        f"Proposed action: {label}",
        choices=[
            questionary.Choice("Accept & run on device", value="accept"),
            questionary.Choice("Edit action text, then run", value="edit"),
            questionary.Choice("Skip this action", value="skip"),
            questionary.Choice("Finish explore now", value="done"),
            questionary.Choice("Quit", value="quit"),
        ],
        default="accept",
    ).ask()
    if not choice:
        return {"choice": "quit"}
    if choice != "edit" or action is None:
        return {"choice": choice}

    new_cmd = questionary.text(
        "Command (tapOn/scroll/inputText/pressKey/…):",
        default=action.command,
    ).ask()
    new_text = questionary.text(
        "Text / selector / value:",
        default=action.text or "",
    ).ask()
    return {
        "choice": "edit",
        "action": {
            "command": (new_cmd or action.command).strip(),
            "text": (new_text if new_text is not None else action.text),
            "optional": action.optional,
        },
    }
