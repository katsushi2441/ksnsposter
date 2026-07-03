# Kurage SNS Poster

Kurage SNS Poster (`ksnsposter`) is a small CLI for posting or preparing posts on Threads, TikTok, Instagram, Reddit, and Telegram.

For browser-first platforms, it reuses an already-authenticated Chrome profile and lets browser-use operate the real web UI. This is useful when OAuth/API approval is blocked, but it is intentionally conservative: by default it prepares a draft and stops before the final publish button. Telegram uses the stable Bot API path because it is safer and more reliable than UI automation.

## Supported Platforms

- Threads: text posts, and media if the web composer allows it.
- Instagram: media posts/Reels with captions. Media is required.
- TikTok: video upload with caption.
- Reddit: research-first text posts with subreddit-specific titles and bodies.
- Telegram: text announcements through Telegram Bot API.

## Safety Model

Default behavior is draft-only. The final publish/post/share button is clicked only when `--confirm-post` is provided.

Reddit is especially sensitive to spam and self-promotion. The Reddit workflow is intentionally research-first:

1. Analyze likely subreddits and recent top posts.
2. Generate value-first drafts per subreddit.
3. Stop at a visible draft by default.
4. Publish only with explicit `--confirm-post`.
5. Avoid mass-posting the same URL across many communities.

The tool records screenshots/video and a `result.json` under `runs/` or `--run-dir`. It reports:

- `posted`
- `draft_ready`
- `not_authenticated`
- `verification_required`
- `upload_processing_timeout`
- `failed`

Do not treat a queued browser task as a successful post. Verify the final public post when business success matters.

## Requirements

The default wrapper uses the existing browser-use environment:

```bash
/home/kojima/work/browser_agent/.venv/bin/python
```

Defaults:

Use `./scripts/start-login-chrome` from VNC to log in once and persist the session.

- Chrome profile: `/home/kojima/work/ksnsposter/storage/chrome-profile`
- LLM: `gemma4:12b-it-qat`
- Ollama host: `http://192.168.0.14:11434`

Override with environment variables or CLI flags:

- `BROWSER_USE_CHROME_PROFILE`
- `BROWSER_USE_CHROME_PROFILE_DIRECTORY`
- `BROWSER_USE_CDP_URL`
- `BROWSER_USE_MODEL`
- `BROWSER_USE_OLLAMA_HOST`
- `KSNSPOSTER_PYTHON`

Telegram posting also supports:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `TELEGRAM_PARSE_MODE` (optional)

## Usage

List platforms:

```bash
./scripts/ksnsposter platforms
```

Prepare a Threads draft without publishing:

```bash
./scripts/ksnsposter post \
  --platform threads \
  --text "Kurageショート動画を公開しました。 https://kurage.exbridge.jp/kuragev.php?id=example" \
  --headful
```

Actually publish to Threads:

```bash
./scripts/ksnsposter post \
  --platform threads \
  --text-file /tmp/post.txt \
  --confirm-post \
  --headful
```

Prepare an Instagram Reel draft:

```bash
./scripts/ksnsposter post \
  --platform instagram \
  --media /path/to/short.mp4 \
  --text-file /tmp/caption.txt \
  --headful
```

Publish a TikTok video:

```bash
./scripts/ksnsposter post \
  --platform tiktok \
  --media /path/to/short.mp4 \
  --text-file /tmp/caption.txt \
  --confirm-post \
  --headful \
  --steps 45
```

Create a Reddit growth plan from a Kurage video:

```bash
./scripts/ksnsposter reddit-plan \
  --url "https://kurage.exbridge.jp/kuragev.php?id=a6e8d583e8e3495d" \
  --product "Kurage SNS Poster" \
  --subreddit SideProject \
  --subreddit opensource \
  --subreddit LocalLLaMA \
  --out /tmp/reddit-plan.json
```

Prepare a Reddit draft without publishing:

```bash
./scripts/ksnsposter post \
  --platform reddit \
  --subreddit SideProject \
  --title "I turned a Reddit growth case study into a draft-first posting tool" \
  --text-file /tmp/reddit-body.txt \
  --headful
```

Actually publish to Reddit:

```bash
./scripts/ksnsposter post \
  --platform reddit \
  --subreddit SideProject \
  --title-file /tmp/reddit-title.txt \
  --text-file /tmp/reddit-body.txt \
  --confirm-post \
  --headful
```

Prepare a Telegram announcement without sending:

```bash
./scripts/ksnsposter post \
  --platform telegram \
  --text-file /tmp/telegram-message.txt
```

Actually publish to Telegram:

```bash
TELEGRAM_BOT_TOKEN=... TELEGRAM_CHAT_ID=... ./scripts/ksnsposter post \
  --platform telegram \
  --text-file /tmp/telegram-message.txt \
  --confirm-post
```

Load from JSON:

```bash
./scripts/ksnsposter post --json examples/post.json --headful
```

Print the browser-use instruction without running:

```bash
./scripts/ksnsposter task --platform threads --text "hello"
```

## Project Boundary

This repository owns the browser automation layer only. Kurage, kdeck, or rqdb4ai can call this CLI after video generation/upload succeeds.

Recommended pipeline:

1. Kurage creates or selects a video.
2. YouTube upload succeeds and the public URL is verified.
3. AIxSNS is posted through the existing API.
4. `ksnsposter` prepares or publishes Threads/Instagram/TikTok posts through browser-use.
5. For Telegram, `ksnsposter` publishes through Bot API only after `--confirm-post`.
6. For Reddit, run `reddit-plan` first, inspect the selected subreddit rules and draft, then post.

## Notes

Browser UI automation can break when platforms change their UI, ask for CAPTCHA/2FA, or throttle uploads. Keep it observable with `--headful` during early operation and store every run log.
