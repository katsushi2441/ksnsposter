from __future__ import annotations

import json
import os
import select
import subprocess
import time
import urllib.request
from pathlib import Path
from typing import Any

DEFAULT_MCP_BINARY = Path(__file__).resolve().parents[1] / "storage" / "bin" / "youtube-uploader-mcp-linux-amd64"
DEFAULT_CLIENT_SECRET = Path.home() / ".config" / "youtube-uploader-mcp" / "client_secret.json"
DEFAULT_WORKING_DIR = Path.home() / ".config" / "youtube-uploader-mcp"
DEFAULT_TOKEN = Path("/home/kojima/work/airadio-scripted-mv/storage/youtube/token.json")
DEFAULT_RESPONSE_GLOB = "/home/kojima/work/airadio-scripted-mv/storage/youtube/*response*.json"
DEFAULT_RELEASE_URL = "https://github.com/anwerj/youtube-uploader-mcp/releases/download/v0.1.2/youtube-uploader-mcp-linux-amd64"
DEFAULT_CATEGORY_ID = "22"  # People & Blogs


class YouTubeMCPError(RuntimeError):
    pass


def ensure_mcp_binary(path: Path = DEFAULT_MCP_BINARY) -> Path:
    path = path.expanduser()
    if path.exists():
        path.chmod(path.stat().st_mode | 0o111)
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(DEFAULT_RELEASE_URL, path)
    path.chmod(0o755)
    return path


def _load_json(path: Path) -> dict[str, Any]:
    with path.expanduser().open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise YouTubeMCPError(f"JSON object expected: {path}")
    return data


def infer_channel_from_responses(glob_pattern: str = DEFAULT_RESPONSE_GLOB) -> tuple[str, str]:
    import glob

    newest: tuple[float, Path] | None = None
    for value in glob.glob(glob_pattern):
        p = Path(value)
        try:
            mtime = p.stat().st_mtime
        except OSError:
            continue
        if newest is None or mtime > newest[0]:
            newest = (mtime, p)
    if newest is None:
        return "", ""
    try:
        data = _load_json(newest[1])
    except Exception:
        return "", ""
    snippet = data.get("snippet") or {}
    return str(snippet.get("channelId") or ""), str(snippet.get("channelTitle") or "")


def seed_channel_cache(
    *,
    working_dir: Path = DEFAULT_WORKING_DIR,
    token_path: Path = DEFAULT_TOKEN,
    channel_id: str = "",
    channel_name: str = "",
    force: bool = False,
) -> Path:
    """Create youtube-uploader-mcp channel cache from an existing OAuth token.

    The upstream MCP requires its own channel cache before upload_video can look up
    a channel. Kurage already has a working YouTube upload token, so we bridge it
    into the MCP cache without printing secrets.
    """
    working_dir = working_dir.expanduser()
    cache_path = working_dir / ".youtube_uploader_channels_cache"
    if cache_path.exists() and not force:
        return cache_path

    token_path = token_path.expanduser()
    if not token_path.exists():
        raise YouTubeMCPError(f"YouTube token not found: {token_path}")
    token = _load_json(token_path)
    if not channel_id:
        channel_id, inferred_name = infer_channel_from_responses()
        channel_name = channel_name or inferred_name
    if not channel_id:
        raise YouTubeMCPError("channel_id is required; pass --channel-id once or keep prior YouTube response JSONs")

    access_token = token.get("access_token") or token.get("token")
    refresh_token = token.get("refresh_token")
    if not access_token or not refresh_token:
        raise YouTubeMCPError("token must contain access/access_token and refresh_token")

    oauth_token = {
        "access_token": access_token,
        "token_type": token.get("token_type") or "Bearer",
        "refresh_token": refresh_token,
        "expiry": token.get("expiry") or "1970-01-01T00:00:00Z",
    }
    cache = {
        channel_id: {
            "id": channel_id,
            "name": channel_name or channel_id,
            "customer_url": "",
            "token": oauth_token,
        }
    }
    working_dir.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    cache_path.chmod(0o600)
    return cache_path


class MCPClient:
    def __init__(self, *, binary: Path, client_secret: Path, working_dir: Path, timeout: int = 900) -> None:
        self.binary = binary.expanduser()
        self.client_secret = client_secret.expanduser()
        self.working_dir = working_dir.expanduser()
        self.timeout = timeout
        self.proc: subprocess.Popen[str] | None = None
        self._next_id = 1

    def __enter__(self) -> "MCPClient":
        cmd = [
            str(self.binary),
            "-client_secret_file",
            str(self.client_secret),
            "-working_dir",
            str(self.working_dir),
        ]
        self.proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        self.request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "ksnsposter", "version": "0.1.0"},
        })
        self.notify("notifications/initialized", {})
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.proc.kill()

    def notify(self, method: str, params: dict[str, Any]) -> None:
        self._write({"jsonrpc": "2.0", "method": method, "params": params})

    def request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        request_id = self._next_id
        self._next_id += 1
        self._write({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}})
        return self._read_response(request_id)

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return self.request("tools/call", {"name": name, "arguments": arguments})

    def _write(self, obj: dict[str, Any]) -> None:
        if not self.proc or not self.proc.stdin:
            raise YouTubeMCPError("MCP process is not running")
        self.proc.stdin.write(json.dumps(obj, separators=(",", ":"), ensure_ascii=False) + "\n")
        self.proc.stdin.flush()

    def _read_response(self, request_id: int) -> dict[str, Any]:
        if not self.proc or not self.proc.stdout or not self.proc.stderr:
            raise YouTubeMCPError("MCP process is not running")
        deadline = time.time() + self.timeout
        stderr_tail: list[str] = []
        while time.time() < deadline:
            if self.proc.poll() is not None:
                err = "\n".join(stderr_tail[-20:])
                raise YouTubeMCPError(f"MCP process exited with {self.proc.returncode}: {err}")
            ready, _, _ = select.select([self.proc.stdout, self.proc.stderr], [], [], 0.2)
            for stream in ready:
                line = stream.readline()
                if not line:
                    continue
                if stream is self.proc.stderr:
                    stderr_tail.append(line.rstrip())
                    continue
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if msg.get("id") != request_id:
                    continue
                if "error" in msg:
                    raise YouTubeMCPError(json.dumps(msg["error"], ensure_ascii=False))
                return msg.get("result") or {}
        raise YouTubeMCPError("MCP request timed out")


def _tool_text(result: dict[str, Any]) -> str:
    content = result.get("content") or []
    if not content:
        return ""
    first = content[0] if isinstance(content[0], dict) else {}
    return str(first.get("text") or "")


def list_channels(*, binary: Path = DEFAULT_MCP_BINARY, client_secret: Path = DEFAULT_CLIENT_SECRET, working_dir: Path = DEFAULT_WORKING_DIR) -> dict[str, Any]:
    binary = ensure_mcp_binary(binary)
    with MCPClient(binary=binary, client_secret=client_secret, working_dir=working_dir, timeout=60) as client:
        result = client.call_tool("channels", {})
    text = _tool_text(result)
    if result.get("isError"):
        return {"ok": False, "error": text}
    try:
        channels = json.loads(text) if text else {}
    except json.JSONDecodeError:
        channels = text
    return {"ok": True, "channels": channels}


def upload_video(
    *,
    file_path: Path,
    title: str,
    description: str,
    tags: str = "",
    category_id: str = DEFAULT_CATEGORY_ID,
    channel_id: str = "",
    privacy: str = "private",
    publish_at: str = "",
    made_for_kids: bool = False,
    confirm_post: bool = False,
    client_secret: Path = DEFAULT_CLIENT_SECRET,
    working_dir: Path = DEFAULT_WORKING_DIR,
    binary: Path = DEFAULT_MCP_BINARY,
    token_path: Path = DEFAULT_TOKEN,
) -> dict[str, Any]:
    file_path = file_path.expanduser().resolve()
    if not file_path.exists():
        return {"ok": False, "error": "media_not_found", "path": str(file_path)}
    if not confirm_post:
        return {
            "ok": True,
            "status": "draft_ready",
            "platform": "youtube",
            "posted_requested": False,
            "file_path": str(file_path),
            "title": title,
            "description": description,
            "tags": tags,
            "category_id": category_id,
            "privacy": privacy,
            "publish_at": publish_at,
            "note": "YouTube API has no draft mode. Re-run with --confirm-post to upload.",
        }

    binary = ensure_mcp_binary(binary)
    seed_channel_cache(working_dir=working_dir, token_path=token_path, channel_id=channel_id)
    if not channel_id:
        channel_id, _ = infer_channel_from_responses()
    if not channel_id:
        return {"ok": False, "error": "channel_id_required"}

    args = {
        "file_path": str(file_path),
        "channel_id": channel_id,
        "description": description,
        "title": title,
        "tags": tags,
        "category_id": category_id,
        "status": privacy,
        "made_for_kids": made_for_kids,
    }
    if publish_at:
        args["publish_at"] = publish_at
    with MCPClient(binary=binary, client_secret=client_secret, working_dir=working_dir, timeout=1200) as client:
        result = client.call_tool("upload_video", args)
    text = _tool_text(result)
    if result.get("isError"):
        return {"ok": False, "platform": "youtube", "error": text, "posted_requested": True}
    try:
        video = json.loads(text)
    except json.JSONDecodeError:
        video = {"raw": text}
    video_id = video.get("id") if isinstance(video, dict) else ""
    return {
        "ok": bool(video_id),
        "status": "posted" if video_id else "unknown",
        "platform": "youtube",
        "posted_requested": True,
        "video_id": video_id,
        "youtube_url": f"https://youtu.be/{video_id}" if video_id else "",
        "response": video,
    }
