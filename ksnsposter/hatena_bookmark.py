from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any


DEFAULT_ENDPOINT = "https://bookmark.hatenaapis.com/rest/1/my/bookmark"


@dataclass(frozen=True)
class HatenaBookmarkConfig:
    consumer_key: str
    consumer_secret: str
    access_token: str
    access_token_secret: str
    endpoint: str = DEFAULT_ENDPOINT


def resolve_hatena_config(
    *,
    consumer_key: str = "",
    consumer_secret: str = "",
    access_token: str = "",
    access_token_secret: str = "",
    endpoint: str = "",
) -> HatenaBookmarkConfig:
    key = (consumer_key or os.environ.get("HATENA_CONSUMER_KEY") or "").strip()
    secret = (consumer_secret or os.environ.get("HATENA_CONSUMER_SECRET") or "").strip()
    token = (access_token or os.environ.get("HATENA_ACCESS_TOKEN") or "").strip()
    token_secret = (access_token_secret or os.environ.get("HATENA_ACCESS_TOKEN_SECRET") or "").strip()
    api_endpoint = (endpoint or os.environ.get("HATENA_BOOKMARK_ENDPOINT") or DEFAULT_ENDPOINT).strip()
    missing = []
    if not key:
        missing.append("HATENA_CONSUMER_KEY")
    if not secret:
        missing.append("HATENA_CONSUMER_SECRET")
    if not token:
        missing.append("HATENA_ACCESS_TOKEN")
    if not token_secret:
        missing.append("HATENA_ACCESS_TOKEN_SECRET")
    if missing:
        raise ValueError(json.dumps({"ok": False, "error": "hatena_config_required", "required": missing}, ensure_ascii=False))
    return HatenaBookmarkConfig(
        consumer_key=key,
        consumer_secret=secret,
        access_token=token,
        access_token_secret=token_secret,
        endpoint=api_endpoint,
    )


def _quote(value: Any) -> str:
    return urllib.parse.quote(str(value), safe="~")


def _normalize_params(params: list[tuple[str, str]]) -> str:
    encoded = [(_quote(key), _quote(value)) for key, value in params]
    encoded.sort()
    return "&".join(f"{key}={value}" for key, value in encoded)


def _oauth_header(*, method: str, endpoint: str, body_params: list[tuple[str, str]], config: HatenaBookmarkConfig) -> str:
    oauth_params = [
        ("oauth_consumer_key", config.consumer_key),
        ("oauth_nonce", hashlib.sha1(f"{time.time_ns()}:{os.getpid()}".encode("utf-8")).hexdigest()),
        ("oauth_signature_method", "HMAC-SHA1"),
        ("oauth_timestamp", str(int(time.time()))),
        ("oauth_token", config.access_token),
        ("oauth_version", "1.0"),
    ]
    parsed = urllib.parse.urlparse(endpoint)
    base_url = urllib.parse.urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))
    query_params = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    signature_params = oauth_params + query_params + body_params
    base_string = "&".join([
        method.upper(),
        _quote(base_url),
        _quote(_normalize_params(signature_params)),
    ])
    signing_key = f"{_quote(config.consumer_secret)}&{_quote(config.access_token_secret)}"
    digest = hmac.new(signing_key.encode("utf-8"), base_string.encode("utf-8"), hashlib.sha1).digest()
    signature = base64.b64encode(digest).decode("ascii")
    header_params = oauth_params + [("oauth_signature", signature)]
    return "OAuth " + ", ".join(f'{_quote(key)}="{_quote(value)}"' for key, value in header_params)


def add_bookmark(
    *,
    url: str,
    comment: str,
    tags: list[str] | None,
    private: bool,
    config: HatenaBookmarkConfig,
) -> dict[str, Any]:
    clean_url = url.strip()
    if not clean_url:
        return {"ok": False, "error": "url_required"}
    if not urllib.parse.urlparse(clean_url).scheme.startswith("http"):
        return {"ok": False, "error": "http_url_required", "url": clean_url}

    body_params: list[tuple[str, str]] = [
        ("url", clean_url),
        ("comment", comment.strip()),
        ("private", "1" if private else "0"),
    ]
    for tag in tags or []:
        clean = tag.strip()
        if clean:
            body_params.append(("tags", clean))

    body = urllib.parse.urlencode(body_params).encode("utf-8")
    req = urllib.request.Request(
        config.endpoint,
        data=body,
        method="POST",
        headers={
            "Authorization": _oauth_header(method="POST", endpoint=config.endpoint, body_params=body_params, config=config),
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "ksnsposter/0.1 HatenaBookmarkPoster (+https://github.com/katsushi2441/ksnsposter)",
            "Accept": "application/json,*/*;q=0.8",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            text = res.read().decode("utf-8", errors="replace")
            status_code = int(getattr(res, "status", 200))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        return {"ok": False, "error": "hatena_http_error", "status_code": exc.code, "detail": detail[:800]}
    except Exception as exc:  # pragma: no cover - network/environment dependent
        return {"ok": False, "error": "hatena_request_failed", "detail": str(exc)}

    try:
        payload: Any = json.loads(text) if text.strip() else {}
    except json.JSONDecodeError:
        payload = {"raw": text[:1000]}

    return {
        "ok": True,
        "status": "posted",
        "platform": "hatena-bookmark",
        "posted_requested": True,
        "status_code": status_code,
        "url": clean_url,
        "private": private,
        "tags": [tag.strip() for tag in tags or [] if tag.strip()],
        "result": payload,
    }
