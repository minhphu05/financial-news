"""Explicit local infrastructure smoke; never requests public news sites."""

import json
import os
import unittest
from urllib.request import urlopen

from prometheus_client.parser import text_string_to_metric_families


def get(url):
    with urlopen(url, timeout=10) as response:
        return response.read()


class LocalCrawlerObservabilityTest(unittest.TestCase):
    def test_exporter_real_metrics_have_bounded_labels(self):
        text = get(
            os.getenv(
                "CRAWLER_METRICS_URL", "http://platform-metrics-exporter:9108/metrics"
            )
        ).decode()
        count = 0
        for family in text_string_to_metric_families(text):
            if not family.name.startswith("financial_news_crawler_"):
                continue
            for sample in family.samples:
                count += 1
                self.assertLessEqual(
                    set(sample.labels), {"source", "data_kind", "status", "outcome"}
                )
                self.assertIn(
                    sample.labels["source"],
                    {"cafef", "vnexpress", "tuoitre", "thanhnien", "baomoi", "other"},
                )
        self.assertGreater(count, 0)
        self.assertLess(count, 1000)

    def test_prometheus_rules_and_grafana_dashboard_are_loaded(self):
        prometheus = os.getenv("PROMETHEUS_URL", "http://prometheus:9090").rstrip("/")
        grafana = os.getenv("GRAFANA_URL", "http://grafana:3000").rstrip("/")
        rules = json.loads(get(prometheus + "/api/v1/rules"))
        names = {r["name"] for g in rules["data"]["groups"] for r in g["rules"]}
        self.assertLessEqual(
            {
                "CrawlerSourceBlocked",
                "CrawlerParserFailures",
                "CrawlerDownstreamBacklog",
            },
            names,
        )
        search = json.loads(get(grafana + "/api/search"))
        self.assertIn(
            "Financial News — Multisource Crawling", {d["title"] for d in search}
        )


if __name__ == "__main__":
    unittest.main()
