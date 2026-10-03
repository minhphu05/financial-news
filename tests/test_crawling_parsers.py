"""Offline source-specific parsers, mappings, discovery and HTTP policy checks."""

import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

from src.crawling.adapters import SourceAdapter
from src.crawling.http_client import HttpClient, RobotsPolicy, retry_after_seconds
from src.crawling.sources import SOURCES, ParseError
from src.news_pipeline.normalize import normalize_observation

FIXTURES = Path(__file__).parent / "fixtures/crawling"


class ParserTests(unittest.TestCase):
    def assert_source(self, key):
        source = SOURCES[key]
        fixture = json.loads((FIXTURES / (key + ".json")).read_text())
        payload = source.parse((FIXTURES / (key + ".html")).read_bytes())
        envelope = {
            "source": key,
            "url": fixture["url"],
            "raw_schema_version": source.raw_schema_version,
            "payload": payload,
        }
        row = SourceAdapter(source).adapt(envelope)
        normalized = normalize_observation(row, 0, "test", source.host, "crawl-v1")
        self.assertIn("valid", normalized)
        self.assertIsNotNone(normalized["valid"]["published_at"])
        self.assertIsNone(normalized["valid"]["ticker_symbol"])
        self.assertIn("SYNTHETIC", normalized["valid"]["content"])
        self.assertNotIn("navigation poison", normalized["valid"]["content"])
        self.assertEqual(
            source.discover((FIXTURES / (key + "-listing.html")).read_bytes()),
            [fixture["url"]],
        )
        with self.assertRaises(ParseError):
            source.parse("<html><h1>not an article</h1></html>")
        with self.assertRaises(ValueError):
            source.url("https://example.org/secret", article=True)
        if key == "baomoi":
            self.assertEqual(payload["original_publisher"], "Báo Tin Tức TTXVN")

    def test_cafef(self):
        self.assert_source("cafef")

    def test_vnexpress(self):
        self.assert_source("vnexpress")

    def test_tuoitre(self):
        self.assert_source("tuoitre")

    def test_thanhnien(self):
        self.assert_source("thanhnien")

    def test_baomoi(self):
        self.assert_source("baomoi")

    def test_robots_wildcard_agents_and_allow_precedence(self):
        p = RobotsPolicy(
            "\ufeffUser-agent: *\nDisallow: /news-*.htm\nAllow: /news-ok.htm\nDisallow: /*?q=\nCrawl-delay: 5",
            "FinancialNewsResearch/0.1",
        )
        self.assertFalse(p.allowed("https://thanhnien.vn/news-123.htm"))
        self.assertTrue(p.allowed("https://thanhnien.vn/news-ok.htm"))
        self.assertFalse(p.allowed("https://thanhnien.vn/a?q=x"))
        self.assertEqual(p.delay, 5)
        p = RobotsPolicy(
            "User-agent: *\nAllow: /\nUser-agent: Research\nDisallow: /", "Research/1"
        )
        self.assertFalse(p.allowed("https://x/a"))

    def test_retry_after(self):
        self.assertEqual(retry_after_seconds("120"), 120)
        self.assertEqual(
            retry_after_seconds(
                "Thu, 01 Oct 2026 10:02:00 GMT",
                datetime(2026, 10, 1, 10, tzinfo=timezone.utc),
            ),
            120,
        )
        self.assertEqual(retry_after_seconds("garbage"), 0)

    def test_native_timestamp_preserved_if_unsupported(self):
        source = SOURCES["vnexpress"]
        payload = source.parse((FIXTURES / "vnexpress.html").read_bytes())
        payload["pubdate"] = "not an ISO date"
        row = SourceAdapter(source).adapt(
            {
                "source": "vnexpress",
                "url": json.loads((FIXTURES / "vnexpress.json").read_text())["url"],
                "raw_schema_version": source.raw_schema_version,
                "payload": payload,
            }
        )
        self.assertEqual(row["post date"], "not an ISO date")
        self.assertIsNone(
            normalize_observation(row, 0, "test", source.host, "crawl-v1")["valid"][
                "published_at"
            ]
        )

    def test_request_configuration(self):
        with self.assertRaises(ValueError):
            HttpClient(SOURCES["cafef"], user_agent="x", interval=0)


if __name__ == "__main__":
    unittest.main()
