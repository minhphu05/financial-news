"""Root conftest.py — shared fixtures for the entire test suite.

Provides:
    - Environment variable mocking for safe testing without .env
    - Common data factories for scraper, RAG, and flow tests
    - Temporary directory and file fixtures
"""

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Ensure project root is on PYTHONPATH for consistent imports
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ==============================================================================
# Environment Fixtures
# ==============================================================================


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch):
    """Prevent tests from leaking environment variable changes.

    Ensures each test starts with a clean environment slate and
    cannot accidentally modify global state.
    """
    pass


@pytest.fixture
def mock_env(monkeypatch):
    """Provide a minimal .env-equivalent for config modules.

    Returns:
        dict: A mapping of all environment variables set for this test.

    Usage:
        def test_something(mock_env):
            # All scraper/RAG config will read from these values
            settings = get_settings()
            assert settings.pg_host == "localhost"
    """
    env_vars = {
        # PostgreSQL
        "PG_HOST": "localhost",
        "PG_PORT": "5432",
        "PG_USER": "test_user",
        "PG_PASSWORD": "test_password",
        "PG_DATABASE": "test_db",
        # MongoDB
        "MONGO_HOST": "localhost",
        "MONGO_PORT": "27017",
        "MONGO_USER": "",
        "MONGO_PASSWORD": "",
        "MONGO_DB": "test_financial_news",
        "MONGO_COLLECTION": "test_articles",
        # Scraper
        "SOURCE_NAME": "cafef",
        "BASE_URL": "https://cafef.vn",
        "SEARCH_URL_TEMPLATE": "https://cafef.vn/tim-kiem/trang-{page}.chn?keywords={keyword}",
        "START_PAGE": "1",
        "MAX_PAGES": "5",
        "REQUEST_TIMEOUT": "10",
        "MAX_RETRIES": "2",
        "RETRY_DELAY": "1.0",
        "REQUEST_DELAY_MIN": "0.5",
        "REQUEST_DELAY_MAX": "1.5",
        "CONSECUTIVE_KNOWN_THRESHOLD": "3",
        # RAG
        "VOYAGEAI_API_KEY": "test-voyage-key",
        "OPENROUTER_API_KEY": "test-openrouter-key",
        "QDRANT_HOST": "localhost",
        "QDRANT_PORT": "6333",
        # Cache
        "CACHE_ENABLED": "false",
        "REDIS_URL": "redis://localhost:6379/0",
    }
    for key, value in env_vars.items():
        monkeypatch.setenv(key, value)
    return env_vars


# ==============================================================================
# Data Factories
# ==============================================================================


@pytest.fixture
def sample_article_html():
    """Return a minimal CafeF article detail HTML page.

    Returns:
        str: HTML string mimicking a real CafeF article structure.
    """
    return """
    <html>
    <body>
        <h1 class="title">FPT đạt doanh thu kỷ lục quý I/2026</h1>
        <p class="dateandcat">
            <span class="pdate">28-05-2026 - 14:30</span>
        </p>
        <div class="contentdetail">
            <div class="detail-cmain ss">
                <div class="detail-content afcbc-body">
                    <p>FPT vừa công bố kết quả kinh doanh quý I/2026.</p>
                    <p>Doanh thu đạt 15.000 tỷ đồng, tăng 25% so với cùng kỳ.</p>
                    <p>Lợi nhuận sau thuế tăng 30% đạt 2.500 tỷ đồng.</p>
                </div>
            </div>
        </div>
        <p class="author">Nguyễn Văn A</p>
    </body>
    </html>
    """


@pytest.fixture
def sample_listing_html():
    """Return a minimal CafeF search results HTML page.

    Returns:
        str: HTML string mimicking a CafeF search listing with 2 articles.
    """
    return """
    <html>
    <body>
        <div class="list-main">
            <div class="search-content-wrap">
                <div class="timeline list-bytags">
                    <div class="item">
                        <h3 class="titlehidden">
                            <a href="/fpt-dat-doanh-thu-ky-luc-12345.chn"
                               title="FPT đạt doanh thu kỷ lục">
                                FPT đạt doanh thu kỷ lục
                            </a>
                        </h3>
                        <div class="item-content">
                            <p class="sapo">Tóm tắt bài viết FPT...</p>
                        </div>
                    </div>
                    <div class="item">
                        <h3 class="titlehidden">
                            <a href="/vingroup-mo-rong-67890.chn"
                               title="Vingroup mở rộng">
                                Vingroup mở rộng
                            </a>
                        </h3>
                        <div class="item-content">
                            <p class="sapo">Vingroup đầu tư mới...</p>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </body>
    </html>
    """


@pytest.fixture
def sample_empty_listing_html():
    """Return a CafeF search page indicating no more results.

    Returns:
        str: HTML string with the empty-result indicator span.
    """
    return """
    <html>
    <body>
        <div class="search-content-wrap">
            <span>Không tìm thấy kết quả nào phù hợp</span>
        </div>
    </body>
    </html>
    """


@pytest.fixture
def sample_raw_article():
    """Return a raw article dict as scraped from CafeF.

    Returns:
        dict: Article payload matching the MongoDB raw schema.
    """
    return {
        "link": "https://cafef.vn/fpt-ky-luc-12345.chn",
        "title": "FPT đạt doanh thu kỷ lục quý I/2026",
        "context": (
            "FPT vừa công bố kết quả kinh doanh quý I/2026. "
            "Doanh thu đạt 15.000 tỷ đồng, tăng 25% so với cùng kỳ."
        ),
        "post_date": "28-05-2026",
        "ticker_symbol": "FPT",
        "ticker_name": "FPT Corporation",
        "keyword": "FPT",
        "source": "cafef",
    }


@pytest.fixture
def sample_clean_article():
    """Return a cleaned article dict ready for embedding.

    Returns:
        dict: Article after TextCleaner processing.
    """
    return {
        "link": "https://cafef.vn/fpt-ky-luc-12345.chn",
        "title": "FPT đạt doanh thu kỷ lục quý I/2026",
        "clean_text": (
            "FPT vừa công bố kết quả kinh doanh quý I/2026. "
            "Doanh thu đạt 15.000 tỷ đồng, tăng 25% so với cùng kỳ. "
            "Lợi nhuận sau thuế tăng 30% đạt 2.500 tỷ đồng."
        ),
        "post_date": "28-05-2026",
        "ticker_symbol": "FPT",
        "ticker_name": "FPT Corporation",
        "keyword": "FPT",
        "source": "cafef",
        "char_count": 150,
    }


@pytest.fixture
def tmp_jsonl(tmp_path):
    """Create a temporary JSONL file with sample articles.

    Returns:
        Path: Path to the temporary JSONL file.
    """
    import json

    articles = [
        {
            "link": f"https://cafef.vn/article-{i}.chn",
            "title": f"Bài viết mẫu {i}",
            "context": f"Nội dung bài viết số {i} về tài chính.",
            "post_date": f"2026-05-{20 + i:02d}",
            "ticker_symbol": "FPT" if i % 2 == 0 else "VNM",
        }
        for i in range(5)
    ]
    filepath = tmp_path / "articles.jsonl"
    with open(filepath, "w", encoding="utf-8") as f:
        for article in articles:
            f.write(json.dumps(article, ensure_ascii=False) + "\n")
    return filepath
