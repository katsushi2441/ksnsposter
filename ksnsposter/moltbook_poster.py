from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


DEFAULT_BASE_URL = "https://www.moltbook.com/api/v1"


@dataclass(frozen=True)
class MoltbookConfig:
    api_key: str
    base_url: str = DEFAULT_BASE_URL
    timeout: int = 30


def resolve_moltbook_config(
    *,
    api_key: str = "",
    base_url: str = "",
    timeout: int = 30,
) -> MoltbookConfig:
    key = (api_key or os.environ.get("MOLTBOOK_API_KEY", "")).strip()
    endpoint = (base_url or os.environ.get("MOLTBOOK_BASE_URL", DEFAULT_BASE_URL)).strip().rstrip("/")
    parsed = urlparse(endpoint)
    if parsed.scheme != "https" or parsed.netloc != "www.moltbook.com" or not parsed.path.startswith("/api/v1"):
        raise ValueError(json.dumps({
            "ok": False,
            "error": "invalid_moltbook_base_url",
            "note": "Moltbook credentials may only be sent to https://www.moltbook.com/api/v1.",
        }))
    if not key:
        raise ValueError(json.dumps({"ok": False, "error": "moltbook_api_key_required"}))
    return MoltbookConfig(api_key=key, base_url=endpoint, timeout=max(1, int(timeout)))


def _request_json(
    config: MoltbookConfig,
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    request = Request(
        f"{config.base_url}{path}",
        data=body,
        method=method,
        headers={
            "Authorization": f"Bearer {config.api_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "ksnsposter/0.1",
        },
    )
    try:
        with urlopen(request, timeout=config.timeout) as response:
            data = json.load(response)
    except HTTPError as exc:
        try:
            data = json.loads(exc.read().decode("utf-8", errors="replace"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            data = {"message": str(exc)}
        return {
            "ok": False,
            "error": "moltbook_http_error",
            "http_status": exc.code,
            "response": data,
        }
    except (URLError, TimeoutError, OSError) as exc:
        return {"ok": False, "error": "moltbook_request_failed", "message": str(exc)}
    if not isinstance(data, dict):
        return {"ok": False, "error": "invalid_moltbook_response"}
    return data


def create_moltbook_post(
    *,
    title: str,
    content: str,
    submolt: str,
    url: str = "",
    confirm_post: bool,
    config: MoltbookConfig,
) -> dict[str, Any]:
    clean_title = title.strip()
    clean_content = content.strip()
    clean_submolt = submolt.strip().removeprefix("m/").strip("/")
    clean_url = url.strip()
    if not clean_title:
        return {"ok": False, "error": "moltbook_title_required"}
    if len(clean_title) > 300:
        return {"ok": False, "error": "moltbook_title_too_long", "length": len(clean_title)}
    if not clean_content:
        return {"ok": False, "error": "empty_text"}
    if not clean_submolt:
        return {"ok": False, "error": "moltbook_submolt_required"}
    payload: dict[str, Any] = {
        "submolt_name": clean_submolt,
        "title": clean_title,
        "content": clean_content,
    }
    if clean_url:
        payload["url"] = clean_url
    if not confirm_post:
        return {
            "ok": True,
            "status": "draft_ready",
            "platform": "moltbook",
            "posted_requested": False,
            "post": payload,
            "note": "Moltbook API has no draft mode. Re-run with --confirm-post to publish.",
        }

    response = _request_json(config, "POST", "/posts", payload)
    if response.get("ok") is False or response.get("success") is False:
        response.setdefault("platform", "moltbook")
        response.setdefault("posted_requested", True)
        return response
    post = response.get("post") if isinstance(response.get("post"), dict) else {}
    post_id = str(post.get("id") or response.get("post_id") or "").strip()
    verification = post.get("verification") or response.get("verification")
    verification_required = bool(response.get("verification_required") or verification)
    return {
        "ok": True,
        "status": "verification_required" if verification_required else "posted",
        "platform": "moltbook",
        "posted_requested": True,
        "post_id": post_id,
        "post_url": f"https://www.moltbook.com/post/{post_id}" if post_id else "",
        "verification_required": verification_required,
        "verification": verification if verification_required else None,
        "response": response,
    }


def verify_moltbook_content(
    *,
    verification_code: str,
    answer: str,
    config: MoltbookConfig,
) -> dict[str, Any]:
    code = verification_code.strip()
    clean_answer = answer.strip()
    if not code or not clean_answer:
        return {"ok": False, "error": "moltbook_verification_code_and_answer_required"}
    response = _request_json(config, "POST", "/verify", {
        "verification_code": code,
        "answer": clean_answer,
    })
    success = response.get("ok") is not False and response.get("success") is not False
    return {
        "ok": success,
        "status": "verified" if success else "verification_failed",
        "platform": "moltbook",
        "response": response,
    }
