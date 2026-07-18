from __future__ import annotations

import unittest
from unittest.mock import patch

from ksnsposter.bluesky_poster import (
    BlueskyConfig,
    build_link_facets,
    create_bluesky_post,
    resolve_bluesky_config,
)


class BlueskyPosterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = BlueskyConfig(handle="example.bsky.social", app_password="test-password")

    def test_rejects_non_official_service_url(self) -> None:
        with self.assertRaises(ValueError):
            resolve_bluesky_config(
                handle="example.bsky.social",
                app_password="test-password",
                service_url="https://example.com",
            )

    def test_link_facet_uses_utf8_byte_offsets(self) -> None:
        text = "記事です https://example.com/path"
        facet = build_link_facets(text)[0]
        self.assertEqual(len("記事です ".encode("utf-8")), facet["index"]["byteStart"])
        self.assertEqual("https://example.com/path", facet["features"][0]["uri"])

    def test_draft_appends_url_without_calling_api(self) -> None:
        with patch("ksnsposter.bluesky_poster._request_json") as request:
            result = create_bluesky_post(
                text="Announcement",
                url="https://example.com",
                confirm_post=False,
                config=self.config,
            )
        self.assertEqual("draft_ready", result["status"])
        self.assertEqual("Announcement\n\nhttps://example.com", result["text"])
        request.assert_not_called()

    def test_rejects_text_over_300_characters(self) -> None:
        result = create_bluesky_post(
            text="x" * 301,
            confirm_post=False,
            config=self.config,
        )
        self.assertEqual("bluesky_text_too_long", result["error"])

    def test_post_returns_public_url(self) -> None:
        session = {"did": "did:plc:abc", "accessJwt": "token", "handle": "example.bsky.social"}
        created = {"uri": "at://did:plc:abc/app.bsky.feed.post/rkey123", "cid": "cid123"}
        with patch("ksnsposter.bluesky_poster._request_json", side_effect=[session, created]):
            result = create_bluesky_post(
                text="Announcement",
                confirm_post=True,
                config=self.config,
            )
        self.assertEqual("posted", result["status"])
        self.assertEqual("https://bsky.app/profile/example.bsky.social/post/rkey123", result["post_url"])


if __name__ == "__main__":
    unittest.main()
