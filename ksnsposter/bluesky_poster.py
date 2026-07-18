from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlparse
from urllib.request import Request, urlopen


DEFAULT_SERVICE_URL = "https://bsky.social"
PUBLIC_API_URL = "https://public.api.bsky.app"
URL_PATTERN = re.compile(r"https?://[^\s]+")


@dataclass(frozen=True)
class BlueskyConfig:
    handle: str
    app_password: str
    service_url: str = DEFAULT_SERVICE_URL
    timeout: int = 30


def resolve_bluesky_config(
    *,
    handle: str = "",
    app_password: str = "",
    service_url: str = "",
    timeout: int = 30,
) -> BlueskyConfig:
    clean_handle = (handle or os.environ.get("BLUESKY_HANDLE", "")).strip().lstrip("@")
    clean_password = (app_password or os.environ.get("BLUESKY_APP_PASSWORD", "")).strip()
    endpoint = (service_url or os.environ.get("BLUESKY_SERVICE_URL", DEFAULT_SERVICE_URL)).strip().rstrip("/")
    parsed = urlparse(endpoint)
    if parsed.scheme != "https" or parsed.netloc != "bsky.social" or parsed.path not in {"", "/"}:
        raise ValueError(json.dumps({
            "ok": False,
            "error": "invalid_bluesky_service_url",
            "note": "Bluesky credentials may only be sent to https://bsky.social.",
        }))
    if not clean_handle or not clean_password:
        raise ValueError(json.dumps({"ok": False, "error": "bluesky_credentials_required"}))
    return BlueskyConfig(
        handle=clean_handle,
        app_password=clean_password,
        service_url=endpoint,
        timeout=max(1, int(timeout)),
    )


def _request_json(
    *,
    url: str,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    token: str = "",
    timeout: int = 30,
) -> dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "ksnsposter/0.1",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(url, data=body, method=method, headers=headers)
    try:
        with urlopen(request, timeout=timeout) as response:
            data = json.load(response)
    except HTTPError as exc:
        try:
            data = json.loads(exc.read().decode("utf-8", errors="replace"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            data = {"message": str(exc)}
        return {
            "ok": False,
            "error": "bluesky_http_error",
            "http_status": exc.code,
            "response": data,
        }
    except (URLError, TimeoutError, OSError) as exc:
        return {"ok": False, "error": "bluesky_request_failed", "message": str(exc)}
    if not isinstance(data, dict):
        return {"ok": False, "error": "invalid_bluesky_response"}
    return data


def compose_bluesky_text(text: str, url: str = "") -> str:
    clean_text = text.strip()
    clean_url = url.strip()
    if clean_url and clean_url not in clean_text:
        clean_text = f"{clean_text}\n\n{clean_url}" if clean_text else clean_url
    return clean_text


def build_link_facets(text: str) -> list[dict[str, Any]]:
    facets = []
    for match in URL_PATTERN.finditer(text):
        uri = match.group(0).rstrip(".,;:!?)]}")
        if not uri:
            continue
        start = len(text[: match.start()].encode("utf-8"))
        end = start + len(uri.encode("utf-8"))
        facets.append({
            "index": {"byteStart": start, "byteEnd": end},
            "features": [{"$type": "app.bsky.richtext.facet#link", "uri": uri}],
        })
    return facets


def create_bluesky_post(
    *,
    text: str,
    url: str = "",
    confirm_post: bool,
    config: BlueskyConfig,
) -> dict[str, Any]:
    post_text = compose_bluesky_text(text, url)
    if not post_text:
        return {"ok": False, "error": "empty_text"}
    if len(post_text) > 300:
        return {"ok": False, "error": "bluesky_text_too_long", "length": len(post_text), "limit": 300}
    if not confirm_post:
        return {
            "ok": True,
            "status": "draft_ready",
            "platform": "bluesky",
            "posted_requested": False,
            "text": post_text,
            "length": len(post_text),
            "note": "Bluesky API has no draft mode. Re-run with --confirm-post to publish.",
        }

    session = _request_json(
        url=f"{config.service_url}/xrpc/com.atproto.server.createSession",
        method="POST",
        payload={"identifier": config.handle, "password": config.app_password},
        timeout=config.timeout,
    )
    if session.get("ok") is False:
        session.update({"platform": "bluesky", "posted_requested": True})
        return session
    did = str(session.get("did") or "").strip()
    token = str(session.get("accessJwt") or "").strip()
    resolved_handle = str(session.get("handle") or config.handle).strip()
    if not did or not token:
        return {"ok": False, "error": "invalid_bluesky_session", "platform": "bluesky"}

    record: dict[str, Any] = {
        "$type": "app.bsky.feed.post",
        "text": post_text,
        "createdAt": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
    }
    facets = build_link_facets(post_text)
    if facets:
        record["facets"] = facets
    response = _request_json(
        url=f"{config.service_url}/xrpc/com.atproto.repo.createRecord",
        method="POST",
        payload={"repo": did, "collection": "app.bsky.feed.post", "record": record},
        token=token,
        timeout=config.timeout,
    )
    if response.get("ok") is False:
        response.update({"platform": "bluesky", "posted_requested": True})
        return response
    uri = str(response.get("uri") or "")
    rkey = uri.rsplit("/", 1)[-1] if uri else ""
    return {
        "ok": bool(uri and rkey),
        "status": "posted" if uri and rkey else "failed",
        "platform": "bluesky",
        "posted_requested": True,
        "uri": uri,
        "cid": response.get("cid"),
        "post_url": f"https://bsky.app/profile/{resolved_handle}/post/{rkey}" if rkey else "",
        "handle": resolved_handle,
        "text": post_text,
    }


def get_public_bluesky_post(uri: str, *, timeout: int = 30) -> dict[str, Any]:
    query = urlencode({"uri": uri, "depth": 0})
    return _request_json(
        url=f"{PUBLIC_API_URL}/xrpc/app.bsky.feed.getPostThread?{query}",
        timeout=max(1, int(timeout)),
    )
