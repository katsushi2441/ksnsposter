from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TelegramConfig:
    bot_token: str
    chat_id: str
    parse_mode: str = ""


def resolve_telegram_config(
    *,
    bot_token: str = "",
    chat_id: str = "",
    parse_mode: str = "",
) -> TelegramConfig:
    token = (bot_token or os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
    target = (chat_id or os.environ.get("TELEGRAM_CHAT_ID") or "").strip()
    mode = (parse_mode or os.environ.get("TELEGRAM_PARSE_MODE") or "").strip()
    if not token or not target:
        missing = []
        if not token:
            missing.append("TELEGRAM_BOT_TOKEN")
        if not target:
            missing.append("TELEGRAM_CHAT_ID")
        raise ValueError(json.dumps({"ok": False, "error": "telegram_config_required", "required": missing}, ensure_ascii=False))
    return TelegramConfig(bot_token=token, chat_id=target, parse_mode=mode)


def send_telegram_message(*, text: str, config: TelegramConfig) -> dict[str, Any]:
    if not text.strip():
        return {"ok": False, "error": "empty_text"}

    fields: dict[str, str] = {
        "chat_id": config.chat_id,
        "text": text,
        "disable_web_page_preview": "false",
    }
    if config.parse_mode:
        fields["parse_mode"] = config.parse_mode

    body = urllib.parse.urlencode(fields).encode("utf-8")
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{config.bot_token}/sendMessage",
        data=body,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            payload = json.loads(res.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        return {"ok": False, "error": "telegram_http_error", "status_code": exc.code, "detail": detail[:500]}
    except Exception as exc:  # pragma: no cover - network/environment dependent
        return {"ok": False, "error": "telegram_request_failed", "detail": str(exc)}

    if not payload.get("ok"):
        return {"ok": False, "error": "telegram_api_error", "detail": payload}

    message = payload.get("result") or {}
    chat = message.get("chat") or {}
    return {
        "ok": True,
        "status": "posted",
        "message_id": message.get("message_id"),
        "chat_id": chat.get("id", config.chat_id),
        "date": message.get("date"),
    }
