#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from urllib.parse import quote

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

DEFAULT_PROFILE = Path('/home/kojima/work/ksnsposter/storage/chrome-profile')
DEFAULT_CHROME = Path('/home/kojima/.cache/ms-playwright/chromium-1223/chrome-linux64/chrome')


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Post to Threads using a logged-in Chromium profile.')
    parser.add_argument('--text', default='')
    parser.add_argument('--text-file', default='')
    parser.add_argument('--profile', default=os.environ.get('KSNSPOSTER_CHROME_PROFILE', str(DEFAULT_PROFILE)))
    parser.add_argument('--confirm-post', action='store_true')
    parser.add_argument('--headful', action='store_true')
    parser.add_argument('--timeout-ms', type=int, default=60000)
    parser.add_argument('--out-dir', default='')
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    text = args.text_file and Path(args.text_file).read_text(encoding='utf-8') or args.text
    text = text.strip()
    if not text:
        raise SystemExit(json.dumps({'ok': False, 'status': 'empty_text'}, ensure_ascii=False))

    profile = Path(args.profile).expanduser()
    profile.mkdir(parents=True, exist_ok=True)
    out_dir = Path(args.out_dir or 'runs/threads_playwright').resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    url = f'https://www.threads.net/intent/post?text={quote(text)}'
    chrome = DEFAULT_CHROME if DEFAULT_CHROME.exists() else Path('/usr/bin/google-chrome')

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            str(profile),
            headless=not args.headful,
            executable_path=str(chrome),
            viewport={'width': 1280, 'height': 940},
            args=[
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-gpu',
                '--enable-unsafe-swiftshader',
                '--password-store=basic',
                '--use-mock-keychain',
            ],
        )
        page = context.pages[0] if context.pages else context.new_page()
        try:
            page.goto(url, wait_until='domcontentloaded', timeout=args.timeout_ms)
            page.wait_for_timeout(5000)
            current = page.url
            page.screenshot(path=str(out_dir / 'threads_before.png'), full_page=True)
            body_text = page.locator('body').inner_text(timeout=10000)
            (out_dir / 'threads_body.txt').write_text(body_text, encoding='utf-8')

            if '/login' in current or 'ログイン' in body_text[:2000] or 'Log in' in body_text[:2000]:
                result = {'ok': False, 'status': 'not_authenticated', 'url': current, 'out_dir': str(out_dir)}
                print(json.dumps(result, ensure_ascii=False, indent=2))
                raise SystemExit(1)

            if text.splitlines()[0] not in body_text:
                # Intent URL occasionally leaves the editor blank. Fill the visible textbox explicitly.
                editor = page.locator('[contenteditable="true"]').first
                editor.click(timeout=10000)
                page.keyboard.press('Control+A')
                page.keyboard.type(text, delay=1)
                page.wait_for_timeout(1000)

            # Prefer Japanese UI label, then English. Threads uses role=button for the final submit.
            candidates = [
                page.get_by_role('button', name='投稿'),
                page.get_by_role('button', name='Post'),
                page.locator('div[role="button"]').filter(has_text='投稿'),
                page.locator('div[role="button"]').filter(has_text='Post'),
            ]
            button = None
            for locator in candidates:
                try:
                    if locator.count() > 0 and locator.first.is_visible(timeout=3000):
                        button = locator.first
                        break
                except Exception:
                    continue

            if button is None:
                result = {'ok': True, 'status': 'draft_ready', 'url': current, 'out_dir': str(out_dir), 'reason': 'post_button_not_found'}
                print(json.dumps(result, ensure_ascii=False, indent=2))
                return

            if not args.confirm_post:
                page.screenshot(path=str(out_dir / 'threads_draft_ready.png'), full_page=True)
                result = {'ok': True, 'status': 'draft_ready', 'url': current, 'out_dir': str(out_dir)}
                print(json.dumps(result, ensure_ascii=False, indent=2))
                return

            button.click(timeout=10000)
            page.wait_for_timeout(7000)
            page.screenshot(path=str(out_dir / 'threads_after.png'), full_page=True)
            result = {'ok': True, 'status': 'posted', 'url': page.url, 'out_dir': str(out_dir)}
            print(json.dumps(result, ensure_ascii=False, indent=2))
        except PlaywrightTimeoutError as exc:
            result = {'ok': False, 'status': 'timeout', 'error': str(exc), 'out_dir': str(out_dir)}
            print(json.dumps(result, ensure_ascii=False, indent=2))
            raise SystemExit(1)
        finally:
            context.close()


if __name__ == '__main__':
    main()
