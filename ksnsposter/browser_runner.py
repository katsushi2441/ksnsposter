from __future__ import annotations

import asyncio
import base64
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

os.environ.setdefault("ANONYMIZED_TELEMETRY", "false")
os.environ.setdefault("BROWSER_USE_CLOUD_SYNC", "false")

from browser_use import Agent, BrowserProfile, ChatOllama  # noqa: E402


DEFAULT_PROFILE = Path("/home/kojima/work/ksnsposter/storage/chrome-profile")
DEFAULT_OLLAMA_HOST = "http://192.168.0.14:11434"
DEFAULT_MODEL = "gemma4:12b-it-qat"


@dataclass
class BrowserRunConfig:
    task: str
    allowed_domains: tuple[str, ...]
    profile: Path = DEFAULT_PROFILE
    profile_directory: str = "Default"
    cdp_url: str = ""
    model: str = DEFAULT_MODEL
    host: str = DEFAULT_OLLAMA_HOST
    steps: int = 24
    headful: bool = False
    run_dir: Path | None = None
    window_width: int = 1280
    window_height: int = 940
    available_file_paths: tuple[str, ...] = ()


def classify_result(final_result: str) -> dict[str, Any]:
    lowered = final_result.lower()
    if "posted" in lowered and "not posted" not in lowered:
        status = "posted"
        ok = True
    elif "draft_ready" in lowered or "draft ready" in lowered:
        status = "draft_ready"
        ok = True
    elif "not_authenticated" in lowered or "login" in lowered:
        status = "not_authenticated"
        ok = False
    elif "verification_required" in lowered or "captcha" in lowered or "2fa" in lowered:
        status = "verification_required"
        ok = False
    elif "upload_processing_timeout" in lowered:
        status = "upload_processing_timeout"
        ok = False
    elif "research_complete" in lowered:
        status = "research_complete"
        ok = True
    elif "partial_research" in lowered:
        status = "partial_research"
        ok = True
    elif "failed" in lowered:
        status = "failed"
        ok = False
    else:
        status = "unknown"
        ok = False
    return {"ok": ok, "status": status, "final_result": final_result[:4000]}


async def run_browser_task(config: BrowserRunConfig) -> dict[str, Any]:
    run_dir = config.run_dir or Path("runs") / time.strftime("%Y%m%d_%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=True)

    profile_kwargs: dict[str, Any] = {
        "headless": not config.headful,
        "chromium_sandbox": False,
        "allowed_domains": list(config.allowed_domains),
        "window_size": {"width": config.window_width, "height": config.window_height},
        "record_video_dir": str(run_dir),
    }
    if config.cdp_url:
        profile_kwargs["cdp_url"] = config.cdp_url
        profile_kwargs["is_local"] = True
        profile_kwargs["keep_alive"] = True
    else:
        if not config.profile.exists():
            raise FileNotFoundError(f"Chrome profile not found: {config.profile}")
        profile_kwargs["user_data_dir"] = str(config.profile)
        profile_kwargs["profile_directory"] = config.profile_directory

    llm = ChatOllama(model=config.model, host=config.host, timeout=900)
    profile = BrowserProfile(**profile_kwargs)
    agent = Agent(
        task=config.task,
        llm=llm,
        browser_profile=profile,
        max_actions_per_step=3,
        available_file_paths=list(config.available_file_paths),
    )

    counter = {"n": 0}

    async def on_step_end(agent_obj: Any) -> None:
        counter["n"] += 1
        try:
            shot = await agent_obj.browser_session.take_screenshot()
            if isinstance(shot, str):
                shot = base64.b64decode(shot)
            if isinstance(shot, bytes):
                (run_dir / f"step_{counter['n']:02d}.png").write_bytes(shot)
        except Exception:
            pass

    history = await agent.run(max_steps=config.steps, on_step_end=on_step_end)
    final_result = str(history.final_result() or "")
    result = classify_result(final_result)
    result.update({
        "run_dir": str(run_dir.resolve()),
        "steps": counter["n"],
        "model": config.model,
        "host": config.host,
    })
    (run_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    (run_dir / "task.txt").write_text(config.task, encoding="utf-8")
    return result


def run_browser_task_sync(config: BrowserRunConfig) -> dict[str, Any]:
    return asyncio.run(run_browser_task(config))
