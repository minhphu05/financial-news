"""Small Spark transformation tests for analytical Gold date semantics."""

from datetime import datetime
import unittest

from pyspark.sql import types as T

from src.news_pipeline.analytics import analytical_frames
from src.news_pipeline.config import Settings
from src.news_pipeline.silver import create_spark


class AnalyticsUnitTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spark = create_spark(Settings.from_env())

    @classmethod
    def tearDownClass(cls):
        cls.spark.stop()

    def test_local_publication_day_and_missing_time(self):
        schema = T.StructType([
            T.StructField("article_id", T.StringType()),
            T.StructField("source", T.StringType()),
            T.StructField("content", T.StringType()),
            T.StructField("published_at", T.TimestampType()),
        ])
        rows = [
            ("a", "cafef.vn", "A" * 10, datetime(2026, 2, 2, 18, 0)),
            ("b", "cafef.vn", "B" * 20, None),
        ]
        frames = analytical_frames(self.spark.createDataFrame(rows, schema))
        daily = frames["news_daily"].collect()
        self.assertEqual(len(daily), 1)
        self.assertEqual(str(daily[0]["published_date"]), "2026-02-03")
        self.assertEqual(daily[0]["article_count"], 1)
        by_source = frames["news_by_source"].first()
        self.assertEqual((by_source["article_count"], by_source["parsed_count"], by_source["unparsed_count"]), (2, 1, 1))


if __name__ == "__main__":
    unittest.main()
