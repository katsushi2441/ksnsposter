from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from .hatena_bookmark import add_bookmark, resolve_hatena_config
from .reddit_growth import DEFAULT_SUBREDDITS, make_growth_plan
from .tasks import PLATFORMS, TaskBuildError, build_task
from .telegram_poster import resolve_telegram_config, send_telegram_message
from .youtube_mcp import (
    DEFAULT_CATEGORY_ID,
    DEFAULT_CLIENT_SECRET,
    DEFAULT_MCP_BINARY,
    DEFAULT_TOKEN,
    DEFAULT_WORKING_DIR,
    list_channels,
    seed_channel_cache,
    upload_video,
)

DEFAULT_PROFILE = Path("/home/kojima/work/ksnsposter/storage/chrome-profile")
DEFAULT_OLLAMA_HOST = "http://192.168.0.14:11434"
DEFAULT_MODEL = "gemma4:12b-it-qat"


def _load_browser_runner() -> tuple[Any, Any]:
    from .browser_runner import BrowserRunConfig, run_browser_task_sync

    return BrowserRunConfig, run_browser_task_sync


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
    post.add_argument("--url", default="", help="Target URL for URL-based platforms such as Hatena Bookmark")
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
    post.add_argument("--telegram-mode", choices=["api", "web"], default=os.environ.get("TELEGRAM_MODE", "api"), help="Telegram api posts as a bot; web posts through the logged-in Telegram Web account")
    post.add_argument("--telegram-target", default=os.environ.get("TELEGRAM_TARGET", ""), help="Telegram Web target chat/channel title, @username, or t.me URL")
    post.add_argument("--hatena-consumer-key", default=os.environ.get("HATENA_CONSUMER_KEY", ""), help="Hatena OAuth consumer key. Prefer env HATENA_CONSUMER_KEY")
    post.add_argument("--hatena-consumer-secret", default=os.environ.get("HATENA_CONSUMER_SECRET", ""), help="Hatena OAuth consumer secret. Prefer env HATENA_CONSUMER_SECRET")
    post.add_argument("--hatena-access-token", default=os.environ.get("HATENA_ACCESS_TOKEN", ""), help="Hatena OAuth access token. Prefer env HATENA_ACCESS_TOKEN")
    post.add_argument("--hatena-access-token-secret", default=os.environ.get("HATENA_ACCESS_TOKEN_SECRET", ""), help="Hatena OAuth access token secret. Prefer env HATENA_ACCESS_TOKEN_SECRET")
    post.add_argument("--hatena-endpoint", default=os.environ.get("HATENA_BOOKMARK_ENDPOINT", ""), help="Hatena Bookmark REST API endpoint override")
    post.add_argument("--hatena-tags", default=os.environ.get("HATENA_BOOKMARK_TAGS", ""), help="Comma-separated Hatena Bookmark tags")
    post.add_argument("--hatena-private", action="store_true", help="Create a private Hatena Bookmark")
    post.add_argument("--privacy", choices=["private", "unlisted", "public"], default=os.environ.get("YOUTUBE_PRIVACY", "private"), help="YouTube privacy status")
    post.add_argument("--publish-at", default=os.environ.get("YOUTUBE_PUBLISH_AT", ""), help="YouTube scheduled publish time, ISO 8601 UTC. Forces private on YouTube side")
    post.add_argument("--category-id", default=os.environ.get("YOUTUBE_CATEGORY_ID", DEFAULT_CATEGORY_ID), help="YouTube category ID, default 22")
    post.add_argument("--tags", default=os.environ.get("YOUTUBE_TAGS", ""), help="Comma-separated YouTube tags")
    post.add_argument("--channel-id", default=os.environ.get("YOUTUBE_CHANNEL_ID", ""), help="YouTube channel ID. If omitted, inferred from prior upload responses")
    post.add_argument("--made-for-kids", action="store_true", help="Mark YouTube video as made for kids")
    post.add_argument("--youtube-client-secret", default=os.environ.get("YOUTUBE_MCP_CLIENT_SECRET", str(DEFAULT_CLIENT_SECRET)))
    post.add_argument("--youtube-working-dir", default=os.environ.get("YOUTUBE_MCP_WORKING_DIR", str(DEFAULT_WORKING_DIR)))
    post.add_argument("--youtube-mcp-binary", default=os.environ.get("YOUTUBE_MCP_BINARY", str(DEFAULT_MCP_BINARY)))
    post.add_argument("--youtube-token", default=os.environ.get("YOUTUBE_TOKEN", str(DEFAULT_TOKEN)))
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
    task.add_argument("--telegram-target", default="")

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

    youtube_upload = sub.add_parser("youtube-upload", help="Upload a video to YouTube through youtube-uploader-mcp")
    youtube_upload.add_argument("--media", required=True, help="Video file path")
    youtube_upload.add_argument("--title", required=True, help="YouTube video title")
    youtube_upload.add_argument("--description", default="", help="YouTube video description")
    youtube_upload.add_argument("--text-file", default="", help="Read YouTube description from a UTF-8 file")
    youtube_upload.add_argument("--privacy", choices=["private", "unlisted", "public"], default=os.environ.get("YOUTUBE_PRIVACY", "private"))
    youtube_upload.add_argument("--publish-at", default=os.environ.get("YOUTUBE_PUBLISH_AT", ""))
    youtube_upload.add_argument("--category-id", default=os.environ.get("YOUTUBE_CATEGORY_ID", DEFAULT_CATEGORY_ID))
    youtube_upload.add_argument("--tags", default=os.environ.get("YOUTUBE_TAGS", ""), help="Comma-separated YouTube tags")
    youtube_upload.add_argument("--channel-id", default=os.environ.get("YOUTUBE_CHANNEL_ID", ""))
    youtube_upload.add_argument("--made-for-kids", action="store_true")
    youtube_upload.add_argument("--confirm-post", action="store_true", help="Actually upload the video")
    youtube_upload.add_argument("--client-secret", default=os.environ.get("YOUTUBE_MCP_CLIENT_SECRET", str(DEFAULT_CLIENT_SECRET)))
    youtube_upload.add_argument("--working-dir", default=os.environ.get("YOUTUBE_MCP_WORKING_DIR", str(DEFAULT_WORKING_DIR)))
    youtube_upload.add_argument("--mcp-binary", default=os.environ.get("YOUTUBE_MCP_BINARY", str(DEFAULT_MCP_BINARY)))
    youtube_upload.add_argument("--token", default=os.environ.get("YOUTUBE_TOKEN", str(DEFAULT_TOKEN)))

    youtube_channels = sub.add_parser("youtube-channels", help="List youtube-uploader-mcp cached channels")
    youtube_channels.add_argument("--client-secret", default=os.environ.get("YOUTUBE_MCP_CLIENT_SECRET", str(DEFAULT_CLIENT_SECRET)))
    youtube_channels.add_argument("--working-dir", default=os.environ.get("YOUTUBE_MCP_WORKING_DIR", str(DEFAULT_WORKING_DIR)))
    youtube_channels.add_argument("--mcp-binary", default=os.environ.get("YOUTUBE_MCP_BINARY", str(DEFAULT_MCP_BINARY)))
    youtube_channels.add_argument("--token", default=os.environ.get("YOUTUBE_TOKEN", str(DEFAULT_TOKEN)))
    youtube_channels.add_argument("--channel-id", default=os.environ.get("YOUTUBE_CHANNEL_ID", ""))
    youtube_channels.add_argument("--seed-cache", action="store_true", help="Seed MCP channel cache from existing token before listing")

    hatena_bookmark = sub.add_parser("hatena-bookmark", help="Add or update one Hatena Bookmark via the official REST API")
    hatena_bookmark.add_argument("--url", required=True, help="URL to bookmark")
    hatena_bookmark.add_argument("--comment", default="", help="Bookmark comment")
    hatena_bookmark.add_argument("--text-file", default="", help="Read bookmark comment from a UTF-8 file")
    hatena_bookmark.add_argument("--tags", default=os.environ.get("HATENA_BOOKMARK_TAGS", ""), help="Comma-separated tags")
    hatena_bookmark.add_argument("--private", action="store_true", help="Create a private bookmark")
    hatena_bookmark.add_argument("--confirm-post", action="store_true", help="Actually add/update the bookmark")
    hatena_bookmark.add_argument("--consumer-key", default=os.environ.get("HATENA_CONSUMER_KEY", ""))
    hatena_bookmark.add_argument("--consumer-secret", default=os.environ.get("HATENA_CONSUMER_SECRET", ""))
    hatena_bookmark.add_argument("--access-token", default=os.environ.get("HATENA_ACCESS_TOKEN", ""))
    hatena_bookmark.add_argument("--access-token-secret", default=os.environ.get("HATENA_ACCESS_TOKEN_SECRET", ""))
    hatena_bookmark.add_argument("--endpoint", default=os.environ.get("HATENA_BOOKMARK_ENDPOINT", ""))

    platforms = sub.add_parser("platforms", help="List supported platforms")
    platforms.set_defaults(func=cmd_platforms)
    post.set_defaults(func=cmd_post)
    task.set_defaults(func=cmd_task)
    reddit_plan.set_defaults(func=cmd_reddit_plan)
    reddit_research.set_defaults(func=cmd_reddit_research)
    youtube_upload.set_defaults(func=cmd_youtube_upload)
    youtube_channels.set_defaults(func=cmd_youtube_channels)
    hatena_bookmark.set_defaults(func=cmd_hatena_bookmark)
    return parser


def _resolve_post_inputs(args: argparse.Namespace) -> tuple[str, str, str, str, str, list[Path]]:
    data: dict[str, Any] = {}
    if getattr(args, "json", ""):
        data = _load_json(Path(args.json).expanduser())
    platform = args.platform or data.get("platform") or ""
    url = args.url or data.get("url") or ""
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
    if platform != "hatena-bookmark" and not text.strip():
        raise SystemExit(json.dumps({"ok": False, "error": "empty_text"}, ensure_ascii=False))
    if platform == "reddit":
        if not title.strip():
            raise SystemExit(json.dumps({"ok": False, "error": "reddit_title_required"}, ensure_ascii=False))
        if not subreddit.strip():
            raise SystemExit(json.dumps({"ok": False, "error": "reddit_subreddit_required"}, ensure_ascii=False))
    if platform == "youtube":
        if not title.strip():
            raise SystemExit(json.dumps({"ok": False, "error": "youtube_title_required"}, ensure_ascii=False))
        if not media:
            raise SystemExit(json.dumps({"ok": False, "error": "youtube_media_required"}, ensure_ascii=False))
    if platform == "hatena-bookmark" and not url.strip():
        raise SystemExit(json.dumps({"ok": False, "error": "hatena_url_required"}, ensure_ascii=False))
    return platform, title.strip(), subreddit.strip(), url.strip(), text.strip(), media


def cmd_post(args: argparse.Namespace) -> None:
    platform, title, subreddit, url, text, media = _resolve_post_inputs(args)
    if platform == "youtube":
        result = _post_youtube_mcp(
            media_path=media[0],
            title=title,
            description=text,
            tags=args.tags,
            category_id=args.category_id,
            channel_id=args.channel_id,
            privacy=args.privacy,
            publish_at=args.publish_at,
            made_for_kids=bool(args.made_for_kids),
            confirm_post=bool(args.confirm_post and not args.stop_before_final),
            client_secret=Path(args.youtube_client_secret),
            working_dir=Path(args.youtube_working_dir),
            binary=Path(args.youtube_mcp_binary),
            token_path=Path(args.youtube_token),
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if not result.get("ok"):
            raise SystemExit(1)
        return
    if platform == "hatena-bookmark":
        result = _post_hatena_bookmark(
            url=url,
            comment=text,
            tags=args.hatena_tags,
            private=bool(args.hatena_private),
            confirm_post=bool(args.confirm_post and not args.stop_before_final),
            consumer_key=args.hatena_consumer_key,
            consumer_secret=args.hatena_consumer_secret,
            access_token=args.hatena_access_token,
            access_token_secret=args.hatena_access_token_secret,
            endpoint=args.hatena_endpoint,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if not result.get("ok"):
            raise SystemExit(1)
        return
    if platform == "telegram":
        if args.telegram_mode == "api":
            result = _post_telegram_api(args=args, text=text)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            if not result.get("ok"):
                raise SystemExit(1)
            return
        _post_with_browser(args=args, platform=platform, title=title, subreddit=subreddit, text=text, media=media)
        return

    _post_with_browser(args=args, platform=platform, title=title, subreddit=subreddit, text=text, media=media)


def _split_tags(value: str) -> list[str]:
    return [item.strip() for item in (value or "").replace("、", ",").split(",") if item.strip()]


def _post_hatena_bookmark(
    *,
    url: str,
    comment: str,
    tags: str,
    private: bool,
    confirm_post: bool,
    consumer_key: str,
    consumer_secret: str,
    access_token: str,
    access_token_secret: str,
    endpoint: str,
) -> dict[str, Any]:
    clean_url = url.strip()
    clean_comment = comment.strip()
    clean_tags = _split_tags(tags)
    if not confirm_post:
        return {
            "ok": True,
            "status": "draft_ready",
            "platform": "hatena-bookmark",
            "posted_requested": False,
            "url": clean_url,
            "comment": clean_comment,
            "tags": clean_tags,
            "private": private,
            "note": "Hatena Bookmark API has no draft mode. Re-run with --confirm-post to add/update the bookmark.",
        }
    try:
        config = resolve_hatena_config(
            consumer_key=consumer_key,
            consumer_secret=consumer_secret,
            access_token=access_token,
            access_token_secret=access_token_secret,
            endpoint=endpoint,
        )
    except ValueError as exc:
        try:
            return json.loads(str(exc))
        except json.JSONDecodeError:
            return {"ok": False, "error": "hatena_config_required"}
    return add_bookmark(url=clean_url, comment=clean_comment, tags=clean_tags, private=private, config=config)


def _post_youtube_mcp(
    *,
    media_path: Path,
    title: str,
    description: str,
    tags: str,
    category_id: str,
    channel_id: str,
    privacy: str,
    publish_at: str,
    made_for_kids: bool,
    confirm_post: bool,
    client_secret: Path,
    working_dir: Path,
    binary: Path,
    token_path: Path,
) -> dict[str, Any]:
    return upload_video(
        file_path=media_path,
        title=title,
        description=description,
        tags=tags,
        category_id=category_id,
        channel_id=channel_id,
        privacy=privacy,
        publish_at=publish_at,
        made_for_kids=made_for_kids,
        confirm_post=confirm_post,
        client_secret=client_secret,
        working_dir=working_dir,
        binary=binary,
        token_path=token_path,
    )


def _post_with_browser(
    *,
    args: argparse.Namespace,
    platform: str,
    title: str,
    subreddit: str,
    text: str,
    media: list[Path],
) -> None:
    BrowserRunConfig, run_browser_task_sync = _load_browser_runner()
    spec = PLATFORMS[platform]
    task = build_task(
        platform=platform,
        text=text,
        media=media,
        confirm_post=bool(args.confirm_post),
        stop_before_final=bool(args.stop_before_final),
        title=title,
        subreddit=subreddit,
        telegram_target=getattr(args, "telegram_target", ""),
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


def _post_telegram_api(*, args: argparse.Namespace, text: str) -> dict[str, Any]:
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
    try:
        task = build_task(
            platform=args.platform,
            text=args.text,
            media=media,
            confirm_post=bool(args.confirm_post),
            stop_before_final=bool(args.stop_before_final),
            title=args.title,
            subreddit=args.subreddit,
            telegram_target=args.telegram_target,
        )
    except TaskBuildError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        raise SystemExit(1)
    print(task)


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
    BrowserRunConfig, run_browser_task_sync = _load_browser_runner()
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


def cmd_youtube_upload(args: argparse.Namespace) -> None:
    description = args.description or ""
    if args.text_file:
        description = Path(args.text_file).expanduser().read_text(encoding="utf-8")
    result = _post_youtube_mcp(
        media_path=Path(args.media).expanduser(),
        title=args.title.strip(),
        description=description.strip(),
        tags=args.tags,
        category_id=args.category_id,
        channel_id=args.channel_id,
        privacy=args.privacy,
        publish_at=args.publish_at,
        made_for_kids=bool(args.made_for_kids),
        confirm_post=bool(args.confirm_post),
        client_secret=Path(args.client_secret),
        working_dir=Path(args.working_dir),
        binary=Path(args.mcp_binary),
        token_path=Path(args.token),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result.get("ok"):
        raise SystemExit(1)


def cmd_youtube_channels(args: argparse.Namespace) -> None:
    if args.seed_cache:
        try:
            seed_channel_cache(
                working_dir=Path(args.working_dir),
                token_path=Path(args.token),
                channel_id=args.channel_id,
            )
        except Exception as exc:
            print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2))
            raise SystemExit(1)
    result = list_channels(
        binary=Path(args.mcp_binary),
        client_secret=Path(args.client_secret),
        working_dir=Path(args.working_dir),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result.get("ok"):
        raise SystemExit(1)


def cmd_hatena_bookmark(args: argparse.Namespace) -> None:
    comment = args.comment or ""
    if args.text_file:
        comment = Path(args.text_file).expanduser().read_text(encoding="utf-8")
    result = _post_hatena_bookmark(
        url=args.url,
        comment=comment,
        tags=args.tags,
        private=bool(args.private),
        confirm_post=bool(args.confirm_post),
        consumer_key=args.consumer_key,
        consumer_secret=args.consumer_secret,
        access_token=args.access_token,
        access_token_secret=args.access_token_secret,
        endpoint=args.endpoint,
    )
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
