from __future__ import annotations

import unittest
from unittest.mock import patch

from ksnsposter.moltbook_poster import (
    MoltbookConfig,
    create_moltbook_post,
    resolve_moltbook_config,
    verify_moltbook_content,
)


class MoltbookPosterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = MoltbookConfig(api_key="test-key")

    def test_rejects_non_official_base_url(self) -> None:
        with self.assertRaises(ValueError):
            resolve_moltbook_config(api_key="test-key", base_url="https://moltbook.com/api/v1")

    def test_draft_does_not_call_api(self) -> None:
        with patch("ksnsposter.moltbook_poster._request_json") as request:
            result = create_moltbook_post(
                title="Title",
                content="Body",
                submolt="m/agentcommerce",
                url="https://example.com",
                confirm_post=False,
                config=self.config,
            )
        self.assertEqual("draft_ready", result["status"])
        self.assertEqual("agentcommerce", result["post"]["submolt_name"])
        request.assert_not_called()

    def test_post_returns_public_permalink(self) -> None:
        response = {"success": True, "post": {"id": "post-123"}}
        with patch("ksnsposter.moltbook_poster._request_json", return_value=response):
            result = create_moltbook_post(
                title="Title",
                content="Body",
                submolt="agentcommerce",
                confirm_post=True,
                config=self.config,
            )
        self.assertEqual("posted", result["status"])
        self.assertEqual("https://www.moltbook.com/post/post-123", result["post_url"])

    def test_verification_challenge_is_reported(self) -> None:
        response = {
            "success": True,
            "verification_required": True,
            "post": {"id": "post-123", "verification": {"verification_code": "code", "challenge_text": "math"}},
        }
        with patch("ksnsposter.moltbook_poster._request_json", return_value=response):
            result = create_moltbook_post(
                title="Title",
                content="Body",
                submolt="agentcommerce",
                confirm_post=True,
                config=self.config,
            )
        self.assertEqual("verification_required", result["status"])
        self.assertEqual("code", result["verification"]["verification_code"])

    def test_verifies_content(self) -> None:
        with patch("ksnsposter.moltbook_poster._request_json", return_value={"success": True}):
            result = verify_moltbook_content(
                verification_code="code",
                answer="15.00",
                config=self.config,
            )
        self.assertEqual("verified", result["status"])


if __name__ == "__main__":
    unittest.main()
