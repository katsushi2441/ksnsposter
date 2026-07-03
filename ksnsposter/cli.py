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
from .reddit_growth import DEFAULT_SUBREDDITS, make_growth_plan
from .tasks import PLATFORMS, build_task
from .telegram_poster import resolve_telegram_config, send_telegram_message


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
    post.add_argument("--title", default="", help="Post title. Required for Reddit")
    post.add_argument("--title-file", default="", help="Read post title from a UTF-8 file")
    post.add_argument("--subreddit", default="", help="Target subreddit name for Reddit, e.g. SideProject")
    post.add_argument("--text-file", default="", help="Read post text from a UTF-8 file")
    post.add_argument("--media", action="append", default=[], help="Media file path. Repeat for multiple files")
    post.add_argument("--json", default="", help="Load platform/text/media from JSON")
    post.add_argument("--confirm-post", action="store_true", help="Actually click the final post/publish button")
    post.add_argument("--stop-before-final", action="store_true", help="Always stop before final publish, even with --confirm-post")
    post.add_argument("--telegram-bot-token", default=os.environ.get("TELEGRAM_BOT_TOKEN", ""), help="Telegram Bot API token. Prefer env TELEGRAM_BOT_TOKEN")
    post.add_argument("--telegram-chat-id", default=os.environ.get("TELEGRAM_CHAT_ID", ""), help="Telegram target chat/channel ID. Prefer env TELEGRAM_CHAT_ID")
    post.add_argument("--telegram-parse-mode", default=os.environ.get("TELEGRAM_PARSE_MODE", ""), help="Optional Telegram parse mode, such as HTML or MarkdownV2")
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
    task.add_argument("--title", default="")
    task.add_argument("--subreddit", default="")
    task.add_argument("--media", action="append", default=[])
    task.add_argument("--confirm-post", action="store_true")
    task.add_argument("--stop-before-final", action="store_true")

    reddit_plan = sub.add_parser("reddit-plan", help="Analyze a source URL and create Reddit posting drafts")
    reddit_plan.add_argument("--url", required=True, help="Source URL, such as a Kurage video URL")
    reddit_plan.add_argument("--product", default="Kurage SNS Poster")
    reddit_plan.add_argument("--subreddit", action="append", default=[], help="Subreddit to analyze. Repeatable")
    reddit_plan.add_argument("--limit", type=int, default=25)
    reddit_plan.add_argument("--timeframe", default="month", choices=["day", "week", "month", "year", "all"])
    reddit_plan.add_argument("--out", default="", help="Write JSON plan to this path")
    reddit_plan.add_argument(
        "--kurage-jobs",
        default="/home/kojima/work/kurage/storage/jobs",
        help="Local Kurage jobs directory for richer kuragev.php metadata",
    )

    reddit_research = sub.add_parser("reddit-research", help="Use browser-use with logged-in Reddit to inspect subreddit top posts")
    reddit_research.add_argument("--subreddit", action="append", required=True, help="Subreddit to inspect. Repeatable")
    reddit_research.add_argument("--timeframe", default="month", choices=["day", "week", "month", "year", "all"])
    reddit_research.add_argument("--limit", type=int, default=10)
    reddit_research.add_argument("--profile", default=os.environ.get("BROWSER_USE_CHROME_PROFILE", str(DEFAULT_PROFILE)))
    reddit_research.add_argument("--profile-directory", default=os.environ.get("BROWSER_USE_CHROME_PROFILE_DIRECTORY", "Default"))
    reddit_research.add_argument("--cdp-url", default=os.environ.get("BROWSER_USE_CDP_URL", ""))
    reddit_research.add_argument("--model", default=os.environ.get("BROWSER_USE_MODEL", DEFAULT_MODEL))
    reddit_research.add_argument("--host", default=os.environ.get("BROWSER_USE_OLLAMA_HOST", DEFAULT_OLLAMA_HOST))
    reddit_research.add_argument("--steps", type=int, default=int(os.environ.get("KSNSPOSTER_REDDIT_RESEARCH_STEPS", "36")))
    reddit_research.add_argument("--headful", action="store_true")
    reddit_research.add_argument("--run-dir", default="")

    platforms = sub.add_parser("platforms", help="List supported platforms")
    platforms.set_defaults(func=cmd_platforms)
    post.set_defaults(func=cmd_post)
    task.set_defaults(func=cmd_task)
    reddit_plan.set_defaults(func=cmd_reddit_plan)
    reddit_research.set_defaults(func=cmd_reddit_research)
    return parser


def _resolve_post_inputs(args: argparse.Namespace) -> tuple[str, str, str, str, list[Path]]:
    data: dict[str, Any] = {}
    if getattr(args, "json", ""):
        data = _load_json(Path(args.json).expanduser())
    platform = args.platform or data.get("platform") or ""
    title = args.title or data.get("title") or ""
    if getattr(args, "title_file", ""):
        title = Path(args.title_file).expanduser().read_text(encoding="utf-8")
    subreddit = args.subreddit or data.get("subreddit") or ""
    text = args.text or data.get("text") or ""
    if args.text_file:
        text = Path(args.text_file).expanduser().read_text(encoding="utf-8")
    media_values = list(data.get("media") or []) + list(args.media or [])
    media = _media_paths([str(value) for value in media_values])
    if platform not in PLATFORMS:
        raise SystemExit(json.dumps({"ok": False, "error": "unsupported_platform", "platform": platform}, ensure_ascii=False))
    if not text.strip():
        raise SystemExit(json.dumps({"ok": False, "error": "empty_text"}, ensure_ascii=False))
    if platform == "reddit":
        if not title.strip():
            raise SystemExit(json.dumps({"ok": False, "error": "reddit_title_required"}, ensure_ascii=False))
        if not subreddit.strip():
            raise SystemExit(json.dumps({"ok": False, "error": "reddit_subreddit_required"}, ensure_ascii=False))
    return platform, title.strip(), subreddit.strip(), text.strip(), media


def cmd_post(args: argparse.Namespace) -> None:
    platform, title, subreddit, text, media = _resolve_post_inputs(args)
    if platform == "telegram":
        result = _post_telegram(args=args, text=text)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if not result.get("ok"):
            raise SystemExit(1)
        return

    spec = PLATFORMS[platform]
    task = build_task(
        platform=platform,
        text=text,
        media=media,
        confirm_post=bool(args.confirm_post),
        stop_before_final=bool(args.stop_before_final),
        title=title,
        subreddit=subreddit,
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
        available_file_paths=tuple(str(path.resolve()) for path in media),
    )
    result = run_browser_task_sync(config)
    result.update({
        "platform": platform,
        "posted_requested": bool(args.confirm_post and not args.stop_before_final),
        "subreddit": subreddit if platform == "reddit" else "",
    })
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result.get("ok"):
        raise SystemExit(1)


def _post_telegram(*, args: argparse.Namespace, text: str) -> dict[str, Any]:
    posted_requested = bool(args.confirm_post and not args.stop_before_final)
    if not posted_requested:
        return {
            "ok": True,
            "status": "draft_ready",
            "platform": "telegram",
            "posted_requested": False,
            "text": text,
            "note": "Telegram API has no draft mode. Re-run with --confirm-post to send.",
        }

    try:
        config = resolve_telegram_config(
            bot_token=args.telegram_bot_token,
            chat_id=args.telegram_chat_id,
            parse_mode=args.telegram_parse_mode,
        )
    except ValueError as exc:
        try:
            return json.loads(str(exc))
        except json.JSONDecodeError:
            return {"ok": False, "error": "telegram_config_required"}

    result = send_telegram_message(text=text, config=config)
    result.update({
        "platform": "telegram",
        "posted_requested": True,
    })
    return result


def cmd_task(args: argparse.Namespace) -> None:
    media = _media_paths(args.media or [])
    print(build_task(
        platform=args.platform,
        text=args.text,
        media=media,
        confirm_post=bool(args.confirm_post),
        stop_before_final=bool(args.stop_before_final),
        title=args.title,
        subreddit=args.subreddit,
    ))


def cmd_reddit_plan(args: argparse.Namespace) -> None:
    subreddits = [item for item in args.subreddit if item] or list(DEFAULT_SUBREDDITS)
    plan = make_growth_plan(
        url=args.url,
        product=args.product,
        subreddits=subreddits,
        local_kurage_jobs=Path(args.kurage_jobs).expanduser() if args.kurage_jobs else None,
        limit=max(1, int(args.limit)),
        timeframe=args.timeframe,
    )
    if args.out:
        out = Path(args.out).expanduser()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
        plan["out"] = str(out)
    print(json.dumps(plan, ensure_ascii=False, indent=2))


def cmd_reddit_research(args: argparse.Namespace) -> None:
    subs = [item.strip().lstrip("r/").strip("/") for item in args.subreddit if item.strip()]
    task = build_reddit_research_task(subs, timeframe=args.timeframe, limit=max(1, int(args.limit)))
    run_dir = Path(args.run_dir).expanduser() if args.run_dir else None
    config = BrowserRunConfig(
        task=task,
        allowed_domains=("reddit.com", "www.reddit.com", "old.reddit.com"),
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
    result.update({"platform": "reddit", "subreddits": subs, "research_requested": True})
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result.get("ok"):
        raise SystemExit(1)


def build_reddit_research_task(subreddits: list[str], *, timeframe: str, limit: int) -> str:
    lines = "\n".join(f"- r/{sub}: https://www.reddit.com/r/{sub}/top/?t={timeframe}" for sub in subreddits)
    return f"""
You are operating an already-authenticated Reddit browser session.
Research these subreddit top-post pages:
{lines}

For each subreddit, collect up to {limit} visible top posts. For each post, capture:
- title
- approximate upvote/score if visible
- comment count if visible
- whether it looks like text, link, image, or video
- any visible subreddit rule/sidebar warning relevant to self-promotion

Do not post, comment, vote, join, message, or click any final action.
If Reddit requires login or verification, stop and report not_authenticated or verification_required.

At the end, return a compact JSON object in your final answer with:
{{
  "status": "research_complete",
  "subreddits": [
    {{
      "name": "SideProject",
      "top_posts": [{{"title": "...", "score": "...", "comments": "...", "format": "text/link/image/video"}}],
      "patterns": ["..."],
      "posting_advice": ["..."],
      "risks": ["..."]
    }}
  ]
}}

If you cannot collect enough posts, return status "partial_research" and explain what blocked collection.
""".strip()


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
