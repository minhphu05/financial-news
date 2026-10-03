"""Spark-submit entry point for existing downstream jobs fed by crawler batches."""

import sys

from src.crawling.cli import main

if __name__ == "__main__":
    sys.argv.insert(1, "publish")
    main()
