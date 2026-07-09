# Kurage SNS Poster

Kurage SNS Poster (`ksnsposter`) is a small CLI for posting or preparing posts on Threads, TikTok, Instagram, Reddit, Telegram, YouTube, and Hatena Bookmark.

For browser-first platforms, it reuses an already-authenticated Chrome profile and lets browser-use operate the real web UI. This is useful when OAuth/API approval is blocked, but it is intentionally conservative: by default it prepares a draft and stops before the final publish button. Telegram uses the stable Bot API path because it is safer and more reliable than UI automation.

## Supported Platforms

- Threads: text posts, and media if the web composer allows it.
- Instagram: media posts/Reels with captions. Media is required.
- TikTok: video upload with caption.
- Reddit: research-first text posts with subreddit-specific titles and bodies.
- Telegram: text announcements through Telegram Bot API or logged-in Telegram Web account.
- YouTube: API upload through `anwerj/youtube-uploader-mcp` with OAuth token reuse, channel cache seeding, privacy, tags, category, and scheduled publish support.
- Hatena Bookmark: add/update one bookmark through the official Hatena Bookmark REST API.
- Blog ranking services: update Ping notifications for にほんブログ村, 人気ブログランキング, and FC2ブログランキング, plus a conservative browser operator for registration/proxy-Ping screens.

## Safety Model

Default behavior is draft-only. The final publish/post/share button is clicked only when `--confirm-post` is provided.

Reddit is especially sensitive to spam and self-promotion. The Reddit workflow is intentionally research-first:

1. Analyze likely subreddits and recent top posts.
2. Generate value-first drafts per subreddit.
3. Stop at a visible draft by default.
4. Publish only with explicit `--confirm-post`.
5. Avoid mass-posting the same URL across many communities.

Hatena Bookmark is also sensitive to ranking manipulation. Use it as a single-account bookmark/log for important VWork or AI OSS articles. Do not use multiple accounts, mutual bookmarking, paid bookmarking, or repeated same-site mass posting to inflate counts.

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
- `TELEGRAM_MODE` (`api` or `web`)
- `TELEGRAM_TARGET` (Telegram Web target chat/channel title, @username, or t.me URL)

YouTube posting uses the upstream OSS MCP server `anwerj/youtube-uploader-mcp`.
The upstream clone and downloaded binary are intentionally stored under ignored paths:

- Clone/reference repo: `youtube-uploader-mcp/` (ignored)
- Runtime binary: `storage/bin/youtube-uploader-mcp-linux-amd64` (ignored through `storage/`)
- OAuth client secret: `/home/kojima/.config/youtube-uploader-mcp/client_secret.json`
- MCP working dir/channel cache: `/home/kojima/.config/youtube-uploader-mcp/`

YouTube environment overrides:

- `YOUTUBE_MCP_CLIENT_SECRET`
- `YOUTUBE_MCP_WORKING_DIR`
- `YOUTUBE_MCP_BINARY`
- `YOUTUBE_TOKEN`
- `YOUTUBE_CHANNEL_ID`
- `YOUTUBE_PRIVACY`
- `YOUTUBE_PUBLISH_AT`
- `YOUTUBE_CATEGORY_ID`
- `YOUTUBE_TAGS`

Hatena Bookmark posting uses OAuth 1.0a credentials from Hatena Developer Center:

- `HATENA_CONSUMER_KEY`
- `HATENA_CONSUMER_SECRET`
- `HATENA_ACCESS_TOKEN`
- `HATENA_ACCESS_TOKEN_SECRET`
- `HATENA_BOOKMARK_TAGS` (optional comma-separated default tags)
- `HATENA_BOOKMARK_ENDPOINT` (optional; defaults to `https://bookmark.hatenaapis.com/rest/1/my/bookmark`)

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

Publish to Telegram through the logged-in human account, for example an Orynth channel/chat:

```bash
./scripts/ksnsposter post \
  --platform telegram \
  --telegram-mode web \
  --telegram-target "Orynth" \
  --text-file /tmp/telegram-message.txt \
  --confirm-post \
  --headful
```

Use Telegram Web mode when the post must appear from the logged-in personal account. Use Bot API mode only when bot/channel posting is acceptable.

Prepare a YouTube upload without publishing:

```bash
./scripts/ksnsposter post \
  --platform youtube \
  --media /path/to/video.mp4 \
  --title "Kurage video title" \
  --text-file /tmp/youtube-description.txt \
  --tags "Kurage,AI,Shorts" \
  --privacy private
```

Actually upload to YouTube through youtube-uploader-mcp:

```bash
./scripts/ksnsposter post \
  --platform youtube \
  --media /path/to/video.mp4 \
  --title "Kurage video title" \
  --text-file /tmp/youtube-description.txt \
  --tags "Kurage,AI,Shorts" \
  --privacy public \
  --confirm-post
```

Dedicated YouTube upload command:

```bash
./scripts/ksnsposter youtube-upload \
  --media /path/to/video.mp4 \
  --title "Kurage video title" \
  --text-file /tmp/youtube-description.txt \
  --privacy public \
  --confirm-post
```

List or seed the MCP channel cache:

```bash
./scripts/ksnsposter youtube-channels --seed-cache
```

Prepare a Hatena Bookmark draft payload without posting:

```bash
./scripts/ksnsposter post \
  --platform hatena-bookmark \
  --url "https://katsushi2441.github.io/vwork/blog/example.html" \
  --text "VWork Blogの重要記事。AI開発、動画生成、自動投稿の実装記録。" \
  --hatena-tags "AI,OSS,VWork"
```

Actually add/update a Hatena Bookmark:

```bash
./scripts/ksnsposter post \
  --platform hatena-bookmark \
  --url "https://katsushi2441.github.io/vwork/blog/example.html" \
  --text-file /tmp/hatena-comment.txt \
  --hatena-tags "AI,OSS,VWork" \
  --confirm-post
```

Dedicated Hatena Bookmark command:

```bash
./scripts/ksnsposter hatena-bookmark \
  --url "https://katsushi2441.github.io/vwork/articles/example.html" \
  --comment "AI OSS技術解説の実装メモ。" \
  --tags "AI,OSS,VWork" \
  --confirm-post
```

Blog ranking / directory notifications:

```bash
# Dry-run payload only. No Ping is sent.
./scripts/ksnsposter ranking-ping \
  --blog-name "Kurage Project" \
  --blog-url "https://kurage.exbridge.jp/"

# Actually send update Ping. blogmura/popular require dedicated secret endpoints.
BLOGMURA_PING_URL="https://..." \
POPULAR_BLOG_RANKING_PING_URL="https://..." \
./scripts/ksnsposter ranking-ping \
  --blog-name "Kurage Project" \
  --blog-url "https://kurage.exbridge.jp/" \
  --confirm-post

# FC2 has a public default endpoint, so it can be sent directly.
./scripts/ksnsposter ranking-ping \
  --service fc2-blog-ranking \
  --blog-name "Kurage Project" \
  --blog-url "https://kurage.exbridge.jp/" \
  --confirm-post
```

Ranking service endpoint variables:

- `BLOGMURA_PING_URL`: dedicated にほんブログ村 Ping URL from My Page. Treat it like a secret.
- `POPULAR_BLOG_RANKING_PING_URL`: dedicated 人気ブログランキング Ping URL from My Page. Treat it like a secret.
- `FC2_BLOG_RANKING_PING_URL`: optional override. Defaults to `https://ping.fc2.com`.

For registration screens, proxy-Ping buttons, category changes, or services without a simple HTTP Ping path, use the conservative browser operator. It stops before final action unless `--confirm-post` is provided:

```bash
./scripts/ksnsposter ranking-browser-task \
  --instruction "Open にほんブログ村 and prepare the Ping代理送信 page for Kurage Project, URL https://kurage.exbridge.jp/. Do not click the final Ping button." \
  --headful
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
4. `ksnsposter` can upload the video to YouTube through `youtube-uploader-mcp`, or prepare/publish Threads/Instagram/TikTok posts through browser-use.
5. For Telegram, `ksnsposter` publishes through Bot API only after `--confirm-post`.
6. For Reddit, run `reddit-plan` first, inspect the selected subreddit rules and draft, then post.

## Notes

Browser UI automation can break when platforms change their UI, ask for CAPTCHA/2FA, or throttle uploads. Keep it observable with `--headful` during early operation and store every run log.
