from __future__ import annotations

import os
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RankingPingTarget:
    name: str
    endpoint: str
    method: str = "xmlrpc"
    env_var: str = ""
    note: str = ""


DEFAULT_TARGETS: dict[str, RankingPingTarget] = {
    "blogmura": RankingPingTarget(
        name="blogmura",
        endpoint="",
        env_var="BLOGMURA_PING_URL",
        note="Use the dedicated Ping URL from にほんブログ村 My Page. Treat it like a secret.",
    ),
    "popular-blog-ranking": RankingPingTarget(
        name="popular-blog-ranking",
        endpoint="",
        env_var="POPULAR_BLOG_RANKING_PING_URL",
        note="Use the dedicated Ping URL from 人気ブログランキング My Page. Treat it like a secret.",
    ),
    "fc2-blog-ranking": RankingPingTarget(
        name="fc2-blog-ranking",
        endpoint="https://ping.fc2.com",
        env_var="FC2_BLOG_RANKING_PING_URL",
        note="FC2 Blog Ranking commonly uses https://ping.fc2.com.",
    ),
}


def list_targets() -> dict[str, dict[str, str]]:
    return {
        key: {
            "endpoint_env": target.env_var,
            "default_endpoint": target.endpoint,
            "method": target.method,
            "note": target.note,
        }
        for key, target in DEFAULT_TARGETS.items()
    }


def resolve_target(service: str, endpoint: str = "") -> RankingPingTarget:
    clean = service.strip().lower()
    target = DEFAULT_TARGETS.get(clean)
    if target is None:
        raise ValueError(f"unsupported ranking ping service: {service}")
    resolved = (endpoint or os.environ.get(target.env_var, "") or target.endpoint).strip()
    if not resolved:
        raise ValueError(f"missing ping endpoint: set {target.env_var} or pass --endpoint")
    return RankingPingTarget(
        name=target.name,
        endpoint=resolved,
        method=target.method,
        env_var=target.env_var,
        note=target.note,
    )


def _xmlrpc_value(text: str) -> ET.Element:
    value = ET.Element("value")
    string = ET.SubElement(value, "string")
    string.text = text
    return value


def build_weblog_updates_ping_xml(blog_name: str, blog_url: str) -> bytes:
    method_call = ET.Element("methodCall")
    method_name = ET.SubElement(method_call, "methodName")
    method_name.text = "weblogUpdates.ping"
    params = ET.SubElement(method_call, "params")
    for item in (blog_name, blog_url):
        param = ET.SubElement(params, "param")
        param.append(_xmlrpc_value(item))
    return ET.tostring(method_call, encoding="utf-8", xml_declaration=True)


def parse_xmlrpc_response(text: str) -> dict[str, Any]:
    if not text.strip():
        return {"raw": ""}
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return {"raw": text[:1000]}
    values: list[str] = []
    for node in root.findall(".//value"):
        values.append("".join(node.itertext()).strip())
    fault = root.find(".//fault") is not None
    return {"fault": fault, "values": values, "raw": text[:1000]}


def send_ranking_ping(
    *,
    service: str,
    blog_name: str,
    blog_url: str,
    endpoint: str = "",
    timeout: int = 30,
) -> dict[str, Any]:
    clean_blog_name = blog_name.strip()
    clean_blog_url = blog_url.strip()
    if not clean_blog_name:
        return {"ok": False, "error": "blog_name_required"}
    if not clean_blog_url:
        return {"ok": False, "error": "blog_url_required"}
    if not urllib.parse.urlparse(clean_blog_url).scheme.startswith("http"):
        return {"ok": False, "error": "http_blog_url_required", "blog_url": clean_blog_url}
    try:
        target = resolve_target(service, endpoint=endpoint)
    except ValueError as exc:
        return {"ok": False, "error": "ranking_ping_config_required", "detail": str(exc)}

    body = build_weblog_updates_ping_xml(clean_blog_name, clean_blog_url)
    req = urllib.request.Request(
        target.endpoint,
        data=body,
        method="POST",
        headers={
            "Content-Type": "text/xml; charset=utf-8",
            "User-Agent": "ksnsposter/0.1 BlogRankingPingPoster (+https://github.com/katsushi2441/ksnsposter)",
            "Accept": "text/xml,application/xml,*/*;q=0.8",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            text = res.read().decode("utf-8", errors="replace")
            status_code = int(getattr(res, "status", 200))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        return {
            "ok": False,
            "error": "ranking_ping_http_error",
            "service": target.name,
            "status_code": exc.code,
            "detail": detail[:800],
        }
    except Exception as exc:  # pragma: no cover - network/environment dependent
        return {"ok": False, "error": "ranking_ping_failed", "service": target.name, "detail": str(exc)}

    parsed = parse_xmlrpc_response(text)
    return {
        "ok": True,
        "status": "ping_sent",
        "platform": "blog-ranking-ping",
        "service": target.name,
        "posted_requested": True,
        "status_code": status_code,
        "blog_name": clean_blog_name,
        "blog_url": clean_blog_url,
        "response": parsed,
    }
