"""Unit tests for src/scraper/parsers.py.

Tests HTML parsing functions for CafeF articles and search listings.
All tests use static HTML fixtures — no network calls required.
"""

import pytest
from datetime import datetime

from src.scraper.parsers import (
    ArticleDetail,
    ListingEntry,
    extract_news_id,
    is_listing_exhausted,
    parse_detail_page,
    parse_listing_page,
)


# ==============================================================================
# extract_news_id Tests
# ==============================================================================


class TestExtractNewsId:
    """Tests for extracting numeric IDs from CafeF URLs."""

    @pytest.mark.parametrize(
        "url, expected",
        [
            (
                "/chu-tich-fpt-188260528163812616.chn",
                "188260528163812616",
            ),
            (
                "https://cafef.vn/foo-bar-1234567890.chn",
                "1234567890",
            ),
            (
                "https://cafef.vn/tin-tuc-42.chn?ref=home",
                "42",
            ),
            (
                "/short-999.chn#section",
                "999",
            ),
        ],
        ids=["relative-long-id", "absolute-url", "with-query", "with-fragment"],
    )
    def test_valid_urls(self, url, expected):
        """Test extraction from various valid CafeF URL formats."""
        assert extract_news_id(url) == expected

    @pytest.mark.parametrize(
        "url",
        [
            "",
            "https://cafef.vn/no-id-here/",
            "https://cafef.vn/article.html",
            "/category/page-2",
            "not-a-url",
        ],
        ids=["empty", "no-chn-suffix", "html-suffix", "category-page", "plain-text"],
    )
    def test_invalid_urls_return_none(self, url):
        """Test that non-CafeF URLs return None."""
        assert extract_news_id(url) is None

    def test_none_input(self):
        """Test that None-like input returns None without error."""
        assert extract_news_id("") is None

    def test_url_with_multiple_dashes(self):
        """Test extraction from URLs containing many dashes in the slug."""
        url = "/a-b-c-d-e-f-g-h-i-j-k-l-98765.chn"
        assert extract_news_id(url) == "98765"


# ==============================================================================
# is_listing_exhausted Tests
# ==============================================================================


class TestIsListingExhausted:
    """Tests for detecting empty search result pages."""

    def test_empty_page_detected(self, sample_empty_listing_html):
        """Test detection of the 'no results' indicator."""
        assert is_listing_exhausted(sample_empty_listing_html) is True

    def test_page_with_results_not_exhausted(self, sample_listing_html):
        """Test that pages with actual results are not marked exhausted."""
        assert is_listing_exhausted(sample_listing_html) is False

    def test_completely_empty_html(self):
        """Test handling of empty HTML body."""
        assert is_listing_exhausted("<html><body></body></html>") is False

    def test_span_in_correct_container(self):
        """Test that span must be inside the correct container."""
        html_wrong_container = """
        <div class="other-wrapper">
            <span>Không tìm thấy kết quả</span>
        </div>
        """
        assert is_listing_exhausted(html_wrong_container) is False


# ==============================================================================
# parse_listing_page Tests
# ==============================================================================


class TestParseListingPage:
    """Tests for extracting article entries from search results."""

    def test_extracts_all_entries(self, sample_listing_html):
        """Test that all valid articles are extracted from the listing."""
        entries = parse_listing_page(sample_listing_html, "https://cafef.vn")
        assert len(entries) == 2

    def test_entry_fields(self, sample_listing_html):
        """Test that extracted entries have correct field values."""
        entries = parse_listing_page(sample_listing_html, "https://cafef.vn")
        first = entries[0]

        assert isinstance(first, ListingEntry)
        assert first.news_id == "12345"
        assert "cafef.vn" in first.url
        assert first.title == "FPT đạt doanh thu kỷ lục"
        assert first.summary == "Tóm tắt bài viết FPT..."

    def test_resolves_relative_urls(self, sample_listing_html):
        """Test that relative href values are resolved to absolute URLs."""
        entries = parse_listing_page(sample_listing_html, "https://cafef.vn")
        for entry in entries:
            assert entry.url.startswith("https://cafef.vn/")

    def test_empty_listing_returns_empty_list(self):
        """Test parsing an empty results page returns no entries."""
        html = """
        <div class="list-main">
            <div class="search-content-wrap">
                <div class="timeline list-bytags"></div>
            </div>
        </div>
        """
        entries = parse_listing_page(html, "https://cafef.vn")
        assert entries == []

    def test_skips_items_without_anchor(self):
        """Test that items lacking an anchor tag are skipped."""
        html = """
        <div class="list-main">
            <div class="search-content-wrap">
                <div class="timeline list-bytags">
                    <div class="item">
                        <h3 class="titlehidden">No anchor here</h3>
                    </div>
                </div>
            </div>
        </div>
        """
        entries = parse_listing_page(html, "https://cafef.vn")
        assert entries == []

    def test_skips_items_without_valid_news_id(self):
        """Test that items with non-CafeF URLs (no .chn) are skipped."""
        html = """
        <div class="list-main">
            <div class="search-content-wrap">
                <div class="timeline list-bytags">
                    <div class="item">
                        <h3 class="titlehidden">
                            <a href="/category/page-2" title="Invalid">Invalid</a>
                        </h3>
                    </div>
                </div>
            </div>
        </div>
        """
        entries = parse_listing_page(html, "https://cafef.vn")
        assert entries == []

    def test_handles_missing_summary(self):
        """Test that missing summary results in None, not an error."""
        html = """
        <div class="list-main">
            <div class="search-content-wrap">
                <div class="timeline list-bytags">
                    <div class="item">
                        <h3 class="titlehidden">
                            <a href="/no-summary-999.chn" title="No Summary">No Summary</a>
                        </h3>
                        <div class="item-content"></div>
                    </div>
                </div>
            </div>
        </div>
        """
        entries = parse_listing_page(html, "https://cafef.vn")
        assert len(entries) == 1
        assert entries[0].summary is None


# ==============================================================================
# parse_detail_page Tests
# ==============================================================================


class TestParseDetailPage:
    """Tests for extracting article content from detail pages."""

    def test_extracts_title(self, sample_article_html):
        """Test title extraction from the detail page."""
        detail = parse_detail_page(sample_article_html)
        assert detail.title == "FPT đạt doanh thu kỷ lục quý I/2026"

    def test_extracts_content(self, sample_article_html):
        """Test that body paragraphs are concatenated into content."""
        detail = parse_detail_page(sample_article_html)
        assert detail.content is not None
        assert "15.000 tỷ đồng" in detail.content
        assert "Lợi nhuận sau thuế" in detail.content

    def test_extracts_author(self, sample_article_html):
        """Test author extraction from the detail page."""
        detail = parse_detail_page(sample_article_html)
        assert detail.author == "Nguyễn Văn A"

    def test_extracts_datetime(self, sample_article_html):
        """Test publication datetime parsing."""
        detail = parse_detail_page(sample_article_html)
        assert isinstance(detail.created_at, datetime)
        assert detail.created_at.year == 2026
        assert detail.created_at.month == 5
        assert detail.created_at.day == 28
        assert detail.created_at.hour == 14
        assert detail.created_at.minute == 30

    def test_returns_dataclass(self, sample_article_html):
        """Test that result is an ArticleDetail instance."""
        detail = parse_detail_page(sample_article_html)
        assert isinstance(detail, ArticleDetail)

    def test_missing_title_returns_none(self):
        """Test graceful handling of pages without a title."""
        html = "<html><body><div class='contentdetail'></div></body></html>"
        detail = parse_detail_page(html)
        assert detail.title is None

    def test_missing_date_returns_none(self):
        """Test graceful handling of pages without a date."""
        html = """
        <html><body>
            <h1 class="title">Test Title</h1>
            <div class="contentdetail">
                <div class="detail-cmain ss">
                    <div class="detail-content afcbc-body">
                        <p>Content</p>
                    </div>
                </div>
            </div>
        </body></html>
        """
        detail = parse_detail_page(html)
        assert detail.created_at is None

    def test_multiple_paragraphs_joined(self, sample_article_html):
        """Test that multiple <p> tags are properly joined in content."""
        detail = parse_detail_page(sample_article_html)
        # Content should contain text from all 3 paragraphs
        paragraphs_found = sum(
            1
            for phrase in [
                "công bố kết quả",
                "Doanh thu đạt",
                "Lợi nhuận sau thuế",
            ]
            if phrase in detail.content
        )
        assert paragraphs_found == 3

    @pytest.mark.parametrize(
        "date_str, expected_day",
        [
            ("28-05-2026 - 14:30", 28),
            ("01/12/2025 10:00", 1),
            ("15-01-2026 08:45:00", 15),
        ],
        ids=["dash-format", "slash-format", "with-seconds"],
    )
    def test_datetime_parsing_formats(self, date_str, expected_day):
        """Test that various Vietnamese datetime formats are parsed."""
        html = f"""
        <html><body>
            <h1 class="title">Test</h1>
            <p class="dateandcat"><span class="pdate">{date_str}</span></p>
            <div class="contentdetail">
                <div class="detail-cmain ss">
                    <div class="detail-content afcbc-body"><p>Body</p></div>
                </div>
            </div>
        </body></html>
        """
        detail = parse_detail_page(html)
        assert detail.created_at is not None
        assert detail.created_at.day == expected_day
