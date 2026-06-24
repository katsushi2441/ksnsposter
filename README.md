# Kurage SNS Poster

Kurage SNS Poster (`ksnsposter`) is a small browser-use based CLI for posting or preparing posts on Threads, TikTok, and Instagram without relying on official API tokens.

It reuses an already-authenticated Chrome profile and lets browser-use operate the real web UI. This is useful when OAuth/API approval is blocked, but it is intentionally conservative: by default it prepares a draft and stops before the final publish button.

## Supported Platforms

- Threads: text posts, and media if the web composer allows it.
- Instagram: media posts/Reels with captions. Media is required.
- TikTok: video upload with caption.

## Safety Model

Default behavior is draft-only. The final publish/post/share button is clicked only when `--confirm-post` is provided.

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

- Chrome profile: `/home/kojima/work/browser_agent/chrome-profile`
- LLM: `gemma4:12b-it-qat`
- Ollama host: `http://192.168.0.3:11434`

Override with environment variables or CLI flags:

- `BROWSER_USE_CHROME_PROFILE`
- `BROWSER_USE_CHROME_PROFILE_DIRECTORY`
- `BROWSER_USE_CDP_URL`
- `BROWSER_USE_MODEL`
- `BROWSER_USE_OLLAMA_HOST`
- `KSNSPOSTER_PYTHON`

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

## Notes

Browser UI automation can break when platforms change their UI, ask for CAPTCHA/2FA, or throttle uploads. Keep it observable with `--headful` during early operation and store every run log.
