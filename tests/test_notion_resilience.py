from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

import requests

import main
from scripts import notion_save
from scripts.line_messaging import notify_line


class NotionSaveTests(unittest.TestCase):
    @patch.dict("os.environ", {"NOTION_DATABASE_ID": "db", "NOTION_TOKEN": "token"})
    @patch("scripts.notion_save.time.sleep")
    @patch("scripts.notion_save.requests.post")
    def test_retries_timeout_then_succeeds(self, post: Mock, sleep: Mock) -> None:
        response = Mock(status_code=200)
        response.json.return_value = {"results": [{"id": "existing"}]}
        post.side_effect = [requests.Timeout("temporary"), response]

        papers = [{"pmid": "123"}]
        result = notion_save.save_papers_to_notion(papers)

        self.assertEqual(result[0]["notion_status"], "duplicate")
        self.assertEqual(post.call_count, 2)
        sleep.assert_called_once_with(1)

    @patch.dict("os.environ", {"NOTION_DATABASE_ID": "db", "NOTION_TOKEN": "token"})
    @patch("scripts.notion_save.time.sleep")
    @patch("scripts.notion_save.requests.post")
    def test_continues_after_persistent_timeout(self, post: Mock, sleep: Mock) -> None:
        success = Mock(status_code=200)
        success.json.return_value = {"results": [{"id": "existing"}]}
        post.side_effect = [
            requests.Timeout("temporary"),
            requests.Timeout("temporary"),
            requests.Timeout("temporary"),
            success,
        ]

        papers = [{"pmid": "123"}, {"pmid": "456"}]
        result = notion_save.save_papers_to_notion(papers)

        self.assertEqual(
            [paper["notion_status"] for paper in result],
            ["failed", "duplicate"],
        )
        self.assertEqual(sleep.call_count, 2)


class PipelineTests(unittest.TestCase):
    @patch("main.notify_line")
    @patch("main.publish_digest", return_value="https://example.test/index.html")
    @patch("main.render_digest", return_value="digest.html")
    @patch("main.save_papers_to_notion", side_effect=RuntimeError("Notion unavailable"))
    @patch("main.classify_papers")
    @patch("main.attach_if_metadata")
    @patch("main.tag_ai_dx")
    @patch("main.fetch_pubmed")
    @patch("main.load_journals", return_value=[{"journal": "Test Journal"}])
    @patch("main._load_yaml", return_value={"ai_terms": []})
    def test_notion_failure_does_not_block_digest_or_line(
        self,
        _load_yaml: Mock,
        _load_journals: Mock,
        fetch_pubmed: Mock,
        _tag_ai_dx: Mock,
        attach_if_metadata: Mock,
        classify_papers: Mock,
        _save_papers_to_notion: Mock,
        render_digest: Mock,
        _publish_digest: Mock,
        notify_line_mock: Mock,
    ) -> None:
        paper = {
            "pmid": "123",
            "classification": {"ent_relevance": "high"},
        }
        fetch_pubmed.return_value = [paper]
        attach_if_metadata.return_value = [paper]
        classify_papers.return_value = [paper]

        with patch("main.keep_after_classification", return_value=True):
            main.main()

        self.assertEqual(paper["notion_status"], "failed")
        render_digest.assert_called_once_with([paper])
        notify_line_mock.assert_called_once_with(
            "https://example.test/index.html", [paper]
        )


class LineNotificationTests(unittest.TestCase):
    @patch.dict("os.environ", {"LINE_CHANNEL_TOKEN": "token"})
    @patch("scripts.line_messaging.requests.post")
    def test_includes_notion_failure_count(self, post: Mock) -> None:
        post.return_value.raise_for_status.return_value = None

        notify_line(
            "https://example.test/index.html",
            [{"notion_status": "failed", "classification": {}}],
        )

        message = post.call_args.kwargs["json"]["messages"][0]["text"]
        self.assertIn("Notion保存失敗: 1件", message)


if __name__ == "__main__":
    unittest.main()
