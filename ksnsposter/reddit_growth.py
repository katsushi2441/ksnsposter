from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


DEFAULT_SUBREDDITS = (
    "SideProject",
    "opensource",
    "LocalLLaMA",
    "ClaudeCode",
    "ArtificialInteligence",
    "SaaS",
    "Entrepreneur",
    "youtubers",
)

STOP_WORDS = {
    "the", "and", "for", "with", "that", "this", "from", "you", "your", "are",
    "but", "not", "can", "how", "what", "why", "when", "where", "into", "about",
    "have", "has", "had", "just", "made", "built", "using", "use", "our", "my",
}


@dataclass
class SourceSummary:
    url: str
    title: str
    summary: str
    source: str = "url"


@dataclass
class SubredditAnalysis:
    subreddit: str
    ok: bool
    sample_count: int
    average_score: float
    top_score: int
    common_words: list[str]
    winning_titles: list[str]
    notes: list[str]
    error: str = ""


def http_get(url: str, timeout: int = 20) -> tuple[int, str, str]:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "ksnsposter/0.1 reddit-growth-planner (+https://kurage.exbridge.jp/)",
            "Accept": "application/json,text/html;q=0.9,*/*;q=0.8",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            body = res.read().decode("utf-8", errors="replace")
            return int(getattr(res, "status", 200)), body, res.headers.get("content-type", "")
    except urllib.error.HTTPError as exc:
        return int(exc.code), exc.read().decode("utf-8", errors="replace"), exc.headers.get("content-type", "")


def clean_text(value: Any, limit: int = 500) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:limit].rstrip()


def normalize_source_terms(text: str) -> str:
    """Repair common ASR/translation mistakes from the reference video."""
    text = str(text or "")
    text = text.replace("CloudCall", "Claude Code")
    text = text.replace("OpenCloud", "OpenCode")
    text = text.replace("Money", "Monid")
    text = text.replace("ｍoney", "Monid").replace("Ｍoney", "Monid")
    return text


def extract_kurage_job_id(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    qs = urllib.parse.parse_qs(parsed.query)
    raw = (qs.get("id") or [""])[0]
    return re.sub(r"[^a-zA-Z0-9]", "", raw)


def summarize_source(url: str, local_kurage_jobs: Path | None = None) -> SourceSummary:
    job_id = extract_kurage_job_id(url)
    if job_id and local_kurage_jobs:
        job_file = local_kurage_jobs / f"{job_id}.json"
        if job_file.exists():
            data = json.loads(job_file.read_text(encoding="utf-8"))
            title = clean_text(data.get("display_title") or data.get("title") or data.get("source_title"), 120)
            summary = clean_text(normalize_source_terms(data.get("summary") or data.get("display_summary") or script_excerpt(data)), 900)
            return SourceSummary(url=url, title=title or "Kurage video", summary=summary, source="kurage_job")

    status, body, _content_type = http_get(url)
    title = ""
    summary = ""
    if status < 400:
        title = html_meta(body, "og:title") or html_title(body)
        summary = html_meta(body, "description") or html_meta(body, "og:description")
    return SourceSummary(url=url, title=clean_text(title, 120) or url, summary=clean_text(summary, 900), source="web")


def script_excerpt(data: dict[str, Any]) -> str:
    script = data.get("script")
    scenes = script.get("scenes") if isinstance(script, dict) else []
    lines: list[str] = []
    if isinstance(scenes, list):
        for scene in scenes:
            if isinstance(scene, dict) and scene.get("narration"):
                lines.append(str(scene["narration"]))
    return " ".join(lines)


def html_title(html: str) -> str:
    match = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
    if not match:
        return ""
    return re.sub(r"<[^>]+>", "", match.group(1)).strip()


def html_meta(html: str, key: str) -> str:
    patterns = [
        rf'<meta[^>]+property=["\']{re.escape(key)}["\'][^>]+content=["\']([^"\']+)["\']',
        rf'<meta[^>]+name=["\']{re.escape(key)}["\'][^>]+content=["\']([^"\']+)["\']',
        rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\']{re.escape(key)}["\']',
    ]
    for pattern in patterns:
        match = re.search(pattern, html, re.I | re.S)
        if match:
            return match.group(1).strip()
    return ""


def fetch_subreddit_top(subreddit: str, limit: int = 25, timeframe: str = "month") -> list[dict[str, Any]]:
    clean = subreddit.strip().lstrip("r/").strip("/")
    url = f"https://www.reddit.com/r/{urllib.parse.quote(clean)}/top.json?t={urllib.parse.quote(timeframe)}&limit={int(limit)}"
    status, body, _ = http_get(url, timeout=20)
    if status >= 400:
        raise RuntimeError(f"reddit_http_{status}")
    data = json.loads(body)
    children = (((data or {}).get("data") or {}).get("children") or [])
    posts = []
    for child in children:
        item = child.get("data") if isinstance(child, dict) else {}
        if not isinstance(item, dict):
            continue
        title = clean_text(item.get("title"), 220)
        if not title:
            continue
        posts.append({
            "title": title,
            "score": int(item.get("score") or 0),
            "comments": int(item.get("num_comments") or 0),
            "is_self": bool(item.get("is_self")),
            "permalink": "https://www.reddit.com" + str(item.get("permalink") or ""),
        })
    return posts


def fetch_subreddit_top_via_reader(subreddit: str, limit: int = 25, timeframe: str = "month") -> list[dict[str, Any]]:
    clean = subreddit.strip().lstrip("r/").strip("/")
    page_url = f"https://www.reddit.com/r/{urllib.parse.quote(clean)}/top/?t={urllib.parse.quote(timeframe)}"
    reader_url = "https://r.jina.ai/" + page_url
    status, body, _ = http_get(reader_url, timeout=30)
    if status >= 400:
        raise RuntimeError(f"reddit_reader_http_{status}")
    posts: list[dict[str, Any]] = []
    seen: set[str] = set()
    for line in body.splitlines():
        line = line.strip()
        # Jina renders Reddit links as markdown-ish list/link lines. Keep only
        # title-like rows and avoid navigation/sidebar noise.
        match = re.search(r"\[([^\]]{12,180})\]\((https://www\.reddit\.com/r/[^)]+/comments/[^)]+)\)", line)
        if not match:
            continue
        title = clean_text(match.group(1), 180)
        if title.lower() in seen:
            continue
        if any(skip in title.lower() for skip in ["reddit", "log in", "sign up", "advertise"]):
            continue
        seen.add(title.lower())
        posts.append({"title": title, "score": 0, "comments": 0, "is_self": True, "permalink": match.group(2)})
        if len(posts) >= limit:
            break
    if not posts:
        raise RuntimeError("reddit_reader_no_posts")
    return posts


def analyze_subreddit(subreddit: str, limit: int = 25, timeframe: str = "month") -> SubredditAnalysis:
    clean = subreddit.strip().lstrip("r/").strip("/")
    try:
        posts = fetch_subreddit_top(clean, limit=limit, timeframe=timeframe)
    except Exception as exc:
        first_error = str(exc)
        try:
            posts = fetch_subreddit_top_via_reader(clean, limit=limit, timeframe=timeframe)
        except Exception as reader_exc:
            return SubredditAnalysis(
                subreddit=clean,
                ok=False,
                sample_count=0,
                average_score=0.0,
                top_score=0,
                common_words=[],
                winning_titles=[],
                notes=["Could not fetch public subreddit data; use logged-in browser research before posting."],
                error=f"{first_error}; {reader_exc}",
            )

    scores = [int(p.get("score") or 0) for p in posts]
    titles = [str(p.get("title") or "") for p in posts]
    words = Counter()
    for title in titles:
        for word in re.findall(r"[A-Za-z][A-Za-z0-9_+-]{2,}", title.lower()):
            if word not in STOP_WORDS:
                words[word] += 1
    top_titles = [p["title"] for p in sorted(posts, key=lambda x: int(x.get("score") or 0), reverse=True)[:5]]
    notes = []
    if posts:
        self_ratio = sum(1 for p in posts if p.get("is_self")) / len(posts)
        notes.append(f"text_post_ratio={self_ratio:.0%}")
        notes.append("Lead with value, data, or a build story; keep product mention secondary.")
    return SubredditAnalysis(
        subreddit=clean,
        ok=True,
        sample_count=len(posts),
        average_score=round(sum(scores) / len(scores), 1) if scores else 0.0,
        top_score=max(scores) if scores else 0,
        common_words=[word for word, _count in words.most_common(12)],
        winning_titles=top_titles,
        notes=notes,
    )


def build_reddit_drafts(source: SourceSummary, analyses: list[SubredditAnalysis], product: str) -> list[dict[str, str]]:
    product_name = product.strip() or "Kurage"
    base_summary = source.summary or "I built an AI-assisted workflow and documented what worked."
    built_with = product_name if product_name.lower().startswith("kurage") else f"{product_name} / Kurage SNS Poster"
    drafts: list[dict[str, str]] = []
    for analysis in analyses:
        sub = analysis.subreddit
        angle = choose_angle(sub)
        title = title_for(sub, product_name, source.title, analysis.common_words)
        body = f"""I studied a Reddit-growth example where the important part was not blasting the same link everywhere, but researching what each subreddit already rewards.

Here is the practical version I built from that idea:

- analyze relevant subreddits before posting
- look at top posts, title patterns, and common words
- turn the source material into a value-first post
- keep the product link as supporting context, not the whole pitch
- stop at a draft unless the post is explicitly approved

Source I used:
{source.url}

Why it matters:
{base_summary}

For this subreddit, the angle I would test is:
{angle}

I am sharing this as a build note rather than a launch announcement. If this kind of Reddit research-to-post workflow is useful, I can share the implementation details too.

Built with {built_with}."""
        drafts.append({"subreddit": sub, "title": clean_text(title, 280), "body": body.strip()})
    return drafts


def choose_angle(subreddit: str) -> str:
    lower = subreddit.lower()
    if "localllama" in lower or "artificial" in lower:
        return "how local/agentic AI can turn community research into safer growth workflows"
    if "opensource" in lower:
        return "the OSS architecture: browser automation, logged-in sessions, draft-first posting, and audit logs"
    if "sideproject" in lower or "saas" in lower or "entrepreneur" in lower:
        return "getting early users without sounding like an advertiser"
    if "youtube" in lower:
        return "repurposing videos and build logs into useful community posts without spam"
    return "a value-first build story with the product link only as context"


def title_for(subreddit: str, product: str, source_title: str, common_words: list[str]) -> str:
    lower = subreddit.lower()
    if "opensource" in lower:
        return f"I built an open-source style Reddit research-to-post workflow for {product}"
    if "localllama" in lower:
        return "Using local agents to analyze Reddit before writing growth posts"
    if "sideproject" in lower:
        return "I turned a Reddit growth case study into a draft-first posting tool"
    if "saas" in lower or "entrepreneur" in lower:
        return "What I learned building a safer Reddit growth workflow from a 100-user case study"
    keyword = common_words[0] if common_words else "Reddit"
    return f"Building a {keyword}-aware Reddit posting workflow from: {source_title[:80]}"


def make_growth_plan(
    *,
    url: str,
    product: str = "Kurage SNS Poster",
    subreddits: list[str] | None = None,
    local_kurage_jobs: Path | None = None,
    limit: int = 25,
    timeframe: str = "month",
) -> dict[str, Any]:
    source = summarize_source(url, local_kurage_jobs=local_kurage_jobs)
    selected = subreddits or list(DEFAULT_SUBREDDITS)
    analyses = [analyze_subreddit(sub, limit=limit, timeframe=timeframe) for sub in selected]
    analyses_sorted = sorted(analyses, key=lambda a: (a.ok, a.average_score, a.sample_count), reverse=True)
    drafts = build_reddit_drafts(source, analyses_sorted[: min(5, len(analyses_sorted))], product)
    return {
        "ok": True,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "source": asdict(source),
        "product": product,
        "strategy": {
            "mode": "research_first_draft_first",
            "post_safety": "draft by default; require --confirm-post for final submission",
            "rules": [
                "Do not mass-post the same URL to many subreddits.",
                "Read subreddit rules before the final click.",
                "Lead with a useful case study, data point, or implementation note.",
                "Mention the product only as context.",
                "Log every post URL and stop if a subreddit removes or rejects the post.",
            ],
        },
        "analyses": [asdict(item) for item in analyses_sorted],
        "drafts": drafts,
    }
