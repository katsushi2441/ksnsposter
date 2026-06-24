from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from .browser_runner import (
    DEFAULT_MODEL,
    DEFAULT_OLLAMA_HOST,
    DEFAULT_PROFILE,
    BrowserRunConfig,
    run_browser_task_sync,
)
from .tasks import PLATFORMS, build_task


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise SystemExit(f"JSON file must contain an object: {path}")
    return data


def _media_paths(values: list[str]) -> list[Path]:
    paths = [Path(value).expanduser() for value in values if value]
    missing = [str(path) for path in paths if not path.exists()]
    if missing:
        raise SystemExit(json.dumps({"ok": False, "error": "media_not_found", "missing": missing}, ensure_ascii=False))
    return paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ksnsposter", description="Kurage SNS Poster browser-use CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    post = sub.add_parser("post", help="Create or publish a social media post via browser-use")
    post.add_argument("--platform", choices=sorted(PLATFORMS), help="Target platform")
    post.add_argument("--text", default="", help="Post caption/text")
    post.add_argument("--text-file", default="", help="Read post text from a UTF-8 file")
    post.add_argument("--media", action="append", default=[], help="Media file path. Repeat for multiple files")
    post.add_argument("--json", default="", help="Load platform/text/media from JSON")
    post.add_argument("--confirm-post", action="store_true", help="Actually click the final post/publish button")
    post.add_argument("--stop-before-final", action="store_true", help="Always stop before final publish, even with --confirm-post")
    post.add_argument("--profile", default=os.environ.get("BROWSER_USE_CHROME_PROFILE", str(DEFAULT_PROFILE)))
    post.add_argument("--profile-directory", default=os.environ.get("BROWSER_USE_CHROME_PROFILE_DIRECTORY", "Default"))
    post.add_argument("--cdp-url", default=os.environ.get("BROWSER_USE_CDP_URL", ""))
    post.add_argument("--model", default=os.environ.get("BROWSER_USE_MODEL", DEFAULT_MODEL))
    post.add_argument("--host", default=os.environ.get("BROWSER_USE_OLLAMA_HOST", DEFAULT_OLLAMA_HOST))
    post.add_argument("--steps", type=int, default=int(os.environ.get("KSNSPOSTER_STEPS", "28")))
    post.add_argument("--headful", action="store_true", help="Show browser window; use with VNC/Xvfb")
    post.add_argument("--run-dir", default="", help="Directory for screenshots, video, result.json")

    task = sub.add_parser("task", help="Print the browser-use task without running it")
    task.add_argument("--platform", choices=sorted(PLATFORMS), required=True)
    task.add_argument("--text", required=True)
    task.add_argument("--media", action="append", default=[])
    task.add_argument("--confirm-post", action="store_true")
    task.add_argument("--stop-before-final", action="store_true")

    platforms = sub.add_parser("platforms", help="List supported platforms")
    platforms.set_defaults(func=cmd_platforms)
    post.set_defaults(func=cmd_post)
    task.set_defaults(func=cmd_task)
    return parser


def _resolve_post_inputs(args: argparse.Namespace) -> tuple[str, str, list[Path]]:
    data: dict[str, Any] = {}
    if getattr(args, "json", ""):
        data = _load_json(Path(args.json).expanduser())
    platform = args.platform or data.get("platform") or ""
    text = args.text or data.get("text") or ""
    if args.text_file:
        text = Path(args.text_file).expanduser().read_text(encoding="utf-8")
    media_values = list(data.get("media") or []) + list(args.media or [])
    media = _media_paths([str(value) for value in media_values])
    if platform not in PLATFORMS:
        raise SystemExit(json.dumps({"ok": False, "error": "unsupported_platform", "platform": platform}, ensure_ascii=False))
    if not text.strip():
        raise SystemExit(json.dumps({"ok": False, "error": "empty_text"}, ensure_ascii=False))
    return platform, text.strip(), media


def cmd_post(args: argparse.Namespace) -> None:
    platform, text, media = _resolve_post_inputs(args)
    spec = PLATFORMS[platform]
    task = build_task(
        platform=platform,
        text=text,
        media=media,
        confirm_post=bool(args.confirm_post),
        stop_before_final=bool(args.stop_before_final),
    )
    run_dir = Path(args.run_dir).expanduser() if args.run_dir else None
    config = BrowserRunConfig(
        task=task,
        allowed_domains=spec.allowed_domains,
        profile=Path(args.profile).expanduser(),
        profile_directory=args.profile_directory,
        cdp_url=args.cdp_url,
        model=args.model,
        host=args.host,
        steps=args.steps,
        headful=args.headful,
        run_dir=run_dir,
    )
    result = run_browser_task_sync(config)
    result.update({"platform": platform, "posted_requested": bool(args.confirm_post and not args.stop_before_final)})
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result.get("ok"):
        raise SystemExit(1)


def cmd_task(args: argparse.Namespace) -> None:
    media = _media_paths(args.media or [])
    print(build_task(
        platform=args.platform,
        text=args.text,
        media=media,
        confirm_post=bool(args.confirm_post),
        stop_before_final=bool(args.stop_before_final),
    ))


def cmd_platforms(_args: argparse.Namespace) -> None:
    print(json.dumps({
        name: {
            "start_url": spec.start_url,
            "allowed_domains": spec.allowed_domains,
            "media_required": spec.media_required,
        }
        for name, spec in PLATFORMS.items()
    }, ensure_ascii=False, indent=2))


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
