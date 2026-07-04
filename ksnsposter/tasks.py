from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from urllib.parse import quote


@dataclass(frozen=True)
class PlatformSpec:
    name: str
    start_url: str
    allowed_domains: tuple[str, ...]
    media_required: bool = False


PLATFORMS: dict[str, PlatformSpec] = {
    "threads": PlatformSpec(
        name="threads",
        start_url="https://www.threads.net/",
        allowed_domains=("threads.net", "www.threads.net", "threads.com", "www.threads.com", "instagram.com", "www.instagram.com", "accountscenter.instagram.com"),
    ),
    "instagram": PlatformSpec(
        name="instagram",
        start_url="https://www.instagram.com/",
        allowed_domains=("instagram.com", "www.instagram.com", "accountscenter.instagram.com", "facebook.com", "www.facebook.com"),
        media_required=True,
    ),
    "tiktok": PlatformSpec(
        name="tiktok",
        start_url="https://www.tiktok.com/upload?lang=ja-JP",
        allowed_domains=("tiktok.com", "www.tiktok.com", "accounts.tiktok.com"),
        media_required=True,
    ),
    "reddit": PlatformSpec(
        name="reddit",
        start_url="https://www.reddit.com/",
        allowed_domains=("reddit.com", "www.reddit.com", "old.reddit.com"),
    ),
    "telegram": PlatformSpec(
        name="telegram",
        start_url="https://web.telegram.org/",
        allowed_domains=("web.telegram.org", "telegram.org", "t.me"),
    ),
    "youtube": PlatformSpec(
        name="youtube",
        start_url="https://studio.youtube.com/",
        allowed_domains=("youtube.com", "www.youtube.com", "studio.youtube.com"),
        media_required=True,
    ),
}


class TaskBuildError(ValueError):
    pass


def _media_lines(media: Iterable[Path]) -> str:
    paths = [str(path.resolve()) for path in media]
    if not paths:
        return "No media files are attached. Create a text-only post if the platform supports it."
    return "\n".join(f"- {path}" for path in paths)


def build_task(
    *,
    platform: str,
    text: str,
    media: list[Path],
    confirm_post: bool,
    stop_before_final: bool,
    title: str = "",
    subreddit: str = "",
    telegram_target: str = "",
) -> str:
    spec = PLATFORMS.get(platform)
    if spec is None:
        raise TaskBuildError(f"unsupported platform: {platform}")
    if spec.media_required and not media:
        raise TaskBuildError(f"{platform} requires at least one media file")
    if not text.strip():
        raise TaskBuildError("post text is empty")

    action_policy = (
        "Click the final publish/post/share button only after confirming the text and media are correct."
        if confirm_post and not stop_before_final
        else "Do not click the final publish/post/share button. Stop with the completed draft visible for human confirmation."
    )

    if platform == "threads":
        return _threads_task(text=text, media=media, action_policy=action_policy, confirm_post=confirm_post and not stop_before_final)
    if platform == "instagram":
        return _instagram_task(text=text, media=media, action_policy=action_policy, confirm_post=confirm_post and not stop_before_final)
    if platform == "tiktok":
        return _tiktok_task(text=text, media=media, action_policy=action_policy, confirm_post=confirm_post and not stop_before_final)
    if platform == "reddit":
        return _reddit_task(title=title, text=text, subreddit=subreddit, action_policy=action_policy)
    if platform == "telegram":
        return _telegram_task(text=text, target=telegram_target, action_policy=action_policy)
    if platform == "youtube":
        raise TaskBuildError("youtube uses the API/MCP uploader, not browser-use tasks")
    raise TaskBuildError(f"unsupported platform: {platform}")


def _threads_task(*, text: str, media: list[Path], action_policy: str, confirm_post: bool) -> str:
    intent_url = f"https://www.threads.net/intent/post?text={quote(text)}"
    media_instruction = ""
    if media:
        media_instruction = f"""
Attach the following media files to the Threads post if the web UI allows media attachment from this compose flow:
{_media_lines(media)}
If the intent composer does not support media, navigate to the normal Threads composer and attach the media there.
"""
    return f"""
You are operating an already-authenticated Threads browser session.
Open this prefilled composer URL first:
{intent_url}
If it redirects to login or verification, stop and report not_authenticated or verification_required.
Do not click login, forgot-password, account creation, or verification buttons.

Post exactly this text, without adding or removing characters:
<<<POST_TEXT
{text}
POST_TEXT>>>

{media_instruction}
Before publishing, verify the composed text exactly matches POST_TEXT.
{action_policy}
After the final action, report one of these machine-readable results:
- posted: if you clicked final publish and the post appears submitted
- draft_ready: if the draft is ready but final publish was not clicked
- not_authenticated: if login is required
- verification_required: if CAPTCHA, 2FA, or suspicious-login verification appears
- failed: if another blocker occurs
""".strip()


def _instagram_task(*, text: str, media: list[Path], action_policy: str, confirm_post: bool) -> str:
    media_instruction = _media_lines(media)
    post_type = "Reel/video post" if media else "text/caption draft"
    return f"""
You are operating an already-authenticated Instagram browser session.
Open https://www.instagram.com/ .
If it redirects to login or verification, stop and report not_authenticated or verification_required.
Do not click login, forgot-password, account creation, or verification buttons.

Create a new Instagram {post_type}.
If media files are provided, upload them in this order:
{media_instruction}

Use exactly this caption text, without adding or removing characters:
<<<POST_TEXT
{text}
POST_TEXT>>>

If Instagram asks for crop, cover, accessibility, or advanced settings, keep safe defaults and continue.
Before publishing, verify the caption exactly matches POST_TEXT and the intended media is attached.
{action_policy}
After the final action, report one of these machine-readable results:
- posted
- draft_ready
- not_authenticated
- verification_required
- failed
""".strip()


def _tiktok_task(*, text: str, media: list[Path], action_policy: str, confirm_post: bool) -> str:
    return f"""
You are operating an already-authenticated TikTok browser session.
Open https://www.tiktok.com/upload?lang=ja-JP .
If it redirects to login or verification, stop and report not_authenticated or verification_required.
Do not click login, forgot-password, account creation, or verification buttons.

Upload the following video file. Use the first file if the site accepts only one file:
{_media_lines(media)}

Use exactly this caption text, without adding or removing characters:
<<<POST_TEXT
{text}
POST_TEXT>>>

Wait until upload processing reaches a state where the post button is enabled.
Keep visibility/publication settings at the current safe account defaults unless the page requires a selection.
Before publishing, verify the caption exactly matches POST_TEXT and the intended video is attached.
{action_policy}
After the final action, report one of these machine-readable results:
- posted
- draft_ready
- not_authenticated
- verification_required
- upload_processing_timeout
- failed
""".strip()


def _reddit_task(*, title: str, text: str, subreddit: str, action_policy: str) -> str:
    clean_subreddit = subreddit.strip().lstrip("r/").strip("/")
    clean_title = title.strip()
    if not clean_subreddit:
        raise TaskBuildError("reddit requires --subreddit")
    if not clean_title:
        raise TaskBuildError("reddit requires --title")

    submit_url = f"https://www.reddit.com/r/{quote(clean_subreddit)}/submit?type=TEXT"
    return f"""
You are operating an already-authenticated Reddit browser session.
Open this subreddit text-post composer:
{submit_url}
If it redirects to login or verification, stop and report not_authenticated or verification_required.
Do not click login, forgot-password, account creation, or verification buttons.

Target subreddit:
r/{clean_subreddit}

Use exactly this title, without adding or removing characters:
<<<POST_TITLE
{clean_title}
POST_TITLE>>>

Use exactly this post body, without adding or removing characters:
<<<POST_TEXT
{text}
POST_TEXT>>>

If Reddit shows subreddit rules, flair requirements, or a warning that promotional posts are not allowed, stop before final publish and report draft_ready with the blocker details.
If a flair is required, choose the closest neutral option such as Discussion, Project, Showcase, Resource, or Open Source. Do not choose misleading flair.
Before publishing, verify the title exactly matches POST_TITLE, the body exactly matches POST_TEXT, and the selected subreddit is r/{clean_subreddit}.
{action_policy}
After the final action, report one of these machine-readable results:
- posted
- draft_ready
- not_authenticated
- verification_required
- failed
""".strip()


def _telegram_task(*, text: str, target: str, action_policy: str) -> str:
    clean_target = target.strip()
    target_instruction = (
        f"""
Target chat/channel:
<<<TELEGRAM_TARGET
{clean_target}
TELEGRAM_TARGET>>>

If TELEGRAM_TARGET starts with https://t.me/ or t.me/, open that target first.
Otherwise, use Telegram Web search to find the exact chat/channel matching TELEGRAM_TARGET.
Do not send if the selected chat/channel is ambiguous, missing, read-only, or clearly different from TELEGRAM_TARGET.
"""
        if clean_target
        else """
No target chat/channel was provided. Stop and report failed with error telegram_target_required.
"""
    )
    return f"""
You are operating an already-authenticated Telegram Web browser session.
This task posts through the logged-in human Telegram account, not a bot.

Open https://web.telegram.org/ .
If it redirects to login or verification, stop and report not_authenticated or verification_required.
Do not click login, account creation, or verification buttons.

{target_instruction}

Use exactly this message text, without adding or removing characters:
<<<POST_TEXT
{text}
POST_TEXT>>>

Before publishing, verify:
- the selected Telegram chat/channel exactly matches TELEGRAM_TARGET
- the composed message exactly matches POST_TEXT
- no unrelated chat is selected

{action_policy}
For Telegram, the final publish action is pressing Enter or clicking the Send button.
After the final action, report one of these machine-readable results:
- posted
- draft_ready
- not_authenticated
- verification_required
- failed
""".strip()
