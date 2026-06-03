"""Unit tests for src/rag/quality/validators.py.

Tests the Pydantic-based article validation schema and the validate_articles
batch function.
"""

import pytest
from pydantic import ValidationError


class TestScrapedArticleV1:
    """Tests for the ScrapedArticleV1 validation schema."""

    def _valid_payload(self, **overrides):
        """Return a valid article payload with optional overrides.

        Returns:
            dict: A payload that passes ScrapedArticleV1 validation.
        """
        base = {
            "link": "https://cafef.vn/fpt-ky-luc-12345.chn",
            "title": "FPT đạt doanh thu kỷ lục quý I/2026",
            "context": (
                "FPT vừa công bố kết quả kinh doanh quý I/2026 với doanh thu "
                "đạt 15.000 tỷ đồng, tăng 25% so với cùng kỳ năm trước. "
                "Lợi nhuận sau thuế tăng 30% nhờ chiến lược chuyển đổi số."
            ),
            "post_date": "28-05-2026",
            "source": "cafef.vn",
        }
        base.update(overrides)
        return base

    def test_valid_article_passes(self):
        """Test that a well-formed article passes validation."""
        from src.rag.quality.validators import ScrapedArticleV1

        payload = self._valid_payload()
        article = ScrapedArticleV1(**payload)
        assert article.title == "FPT đạt doanh thu kỷ lục quý I/2026"

    def test_missing_link_rejected(self):
        """Test that missing link field causes validation error."""
        from src.rag.quality.validators import ScrapedArticleV1

        payload = self._valid_payload()
        del payload["link"]

        with pytest.raises(ValidationError):
            ScrapedArticleV1(**payload)

    def test_invalid_link_rejected(self):
        """Test that non-URL link is rejected."""
        from src.rag.quality.validators import ScrapedArticleV1

        payload = self._valid_payload(link="not-a-url")

        with pytest.raises(ValidationError):
            ScrapedArticleV1(**payload)

    def test_short_title_rejected(self):
        """Test that title with fewer than 5 chars is rejected."""
        from src.rag.quality.validators import ScrapedArticleV1

        payload = self._valid_payload(title="FPT")

        with pytest.raises(ValidationError):
            ScrapedArticleV1(**payload)

    def test_title_only_digits_rejected(self):
        """Test that title with only digits/punctuation is rejected."""
        from src.rag.quality.validators import ScrapedArticleV1

        payload = self._valid_payload(title="12345")

        with pytest.raises(ValidationError):
            ScrapedArticleV1(**payload)

    def test_short_context_rejected(self):
        """Test that context under 120 chars is rejected."""
        from src.rag.quality.validators import ScrapedArticleV1

        payload = self._valid_payload(context="Ngắn quá.")

        with pytest.raises(ValidationError):
            ScrapedArticleV1(**payload)

    def test_boilerplate_context_rejected(self):
        """Test that placeholder context (404, no results) is rejected."""
        from src.rag.quality.validators import ScrapedArticleV1

        long_boilerplate = "Không có kết quả " * 20
        payload = self._valid_payload(context=long_boilerplate)

        with pytest.raises(ValidationError, match="placeholder"):
            ScrapedArticleV1(**payload)

    def test_valid_post_date_accepted(self):
        """Test that dd-mm-yyyy format passes validation."""
        from src.rag.quality.validators import ScrapedArticleV1

        payload = self._valid_payload(post_date="15-01-2026")
        article = ScrapedArticleV1(**payload)
        assert article.post_date == "15-01-2026"

    def test_iso_post_date_accepted(self):
        """Test that ISO format dates are accepted."""
        from src.rag.quality.validators import ScrapedArticleV1

        payload = self._valid_payload(post_date="2026-05-28T14:30:00")
        article = ScrapedArticleV1(**payload)
        assert "2026" in article.post_date

    def test_unparseable_post_date_rejected(self):
        """Test that gibberish date string is rejected."""
        from src.rag.quality.validators import ScrapedArticleV1

        payload = self._valid_payload(post_date="not-a-date-at-all")

        with pytest.raises(ValidationError, match="unparseable"):
            ScrapedArticleV1(**payload)

    def test_none_post_date_accepted(self):
        """Test that None post_date passes (it's optional)."""
        from src.rag.quality.validators import ScrapedArticleV1

        payload = self._valid_payload(post_date=None)
        article = ScrapedArticleV1(**payload)
        assert article.post_date is None

    def test_ticker_symbol_uppercased(self):
        """Test that ticker_symbol is normalised to uppercase."""
        from src.rag.quality.validators import ScrapedArticleV1

        payload = self._valid_payload(ticker_symbol="fpt")
        article = ScrapedArticleV1(**payload)
        assert article.ticker_symbol == "FPT"

    def test_invalid_ticker_rejected(self):
        """Test that ticker with special chars is rejected."""
        from src.rag.quality.validators import ScrapedArticleV1

        payload = self._valid_payload(ticker_symbol="FPT@#$")

        with pytest.raises(ValidationError, match="invalid ticker"):
            ScrapedArticleV1(**payload)

    def test_ticker_too_long_rejected(self):
        """Test that ticker longer than 5 chars is rejected."""
        from src.rag.quality.validators import ScrapedArticleV1

        payload = self._valid_payload(ticker_symbol="TOOLONG")

        with pytest.raises(ValidationError):
            ScrapedArticleV1(**payload)

    def test_none_ticker_accepted(self):
        """Test that None ticker_symbol is allowed."""
        from src.rag.quality.validators import ScrapedArticleV1

        payload = self._valid_payload(ticker_symbol=None)
        article = ScrapedArticleV1(**payload)
        assert article.ticker_symbol is None

    def test_page_must_be_positive(self):
        """Test that page field must be >= 1."""
        from src.rag.quality.validators import ScrapedArticleV1

        payload = self._valid_payload(page=0)

        with pytest.raises(ValidationError):
            ScrapedArticleV1(**payload)


class TestQualityReport:
    """Tests for the QualityReport dataclass."""

    def test_empty_report(self):
        """Test that empty report has correct defaults."""
        from src.rag.quality.validators import QualityReport

        report = QualityReport()
        assert report.total == 0
        assert report.pass_rate == 1.0

    def test_pass_rate_calculation(self):
        """Test pass_rate with mixed valid/rejected."""
        from src.rag.quality.validators import QualityReport, QualityRejection

        report = QualityReport(
            valid=[{"link": f"https://example.com/{i}"} for i in range(8)],
            rejections=[
                QualityRejection(link=f"bad-{i}", errors=["err"], payload={})
                for i in range(2)
            ],
        )
        assert report.total == 10
        assert report.pass_rate == pytest.approx(0.8)

    def test_as_dict_structure(self):
        """Test that as_dict() returns expected keys."""
        from src.rag.quality.validators import QualityReport

        report = QualityReport(valid=[{"link": "x"}])
        d = report.as_dict()

        assert "total" in d
        assert "valid" in d
        assert "rejected" in d
        assert "pass_rate" in d
        assert "started_at" in d
        assert "rejection_samples" in d


class TestValidateArticles:
    """Tests for the validate_articles() batch function."""

    def _valid_payload(self):
        """Return a valid article payload."""
        return {
            "link": "https://cafef.vn/test-article-99999.chn",
            "title": "Bài viết mẫu về thị trường tài chính",
            "context": (
                "Đây là nội dung mẫu đủ dài để vượt qua giới hạn 120 ký tự. "
                "Thị trường chứng khoán Việt Nam đã có phiên giao dịch sôi động "
                "với khối lượng giao dịch đạt kỷ lục mới trong lịch sử."
            ),
            "post_date": "28-05-2026",
            "source": "cafef.vn",
        }

    def test_all_valid(self):
        """Test batch where all articles pass validation."""
        from src.rag.quality.validators import validate_articles

        articles = [self._valid_payload() for _ in range(3)]
        report = validate_articles(articles)

        assert len(report.valid) == 3
        assert len(report.rejections) == 0
        assert report.pass_rate == 1.0

    def test_all_invalid(self):
        """Test batch where all articles fail validation."""
        from src.rag.quality.validators import validate_articles

        bad_articles = [
            {"link": "not-url", "title": "X", "context": "short"},
            {"link": "", "title": "", "context": ""},
        ]
        report = validate_articles(bad_articles)

        assert len(report.valid) == 0
        assert len(report.rejections) == 2
        assert report.pass_rate == 0.0

    def test_mixed_batch(self):
        """Test batch with some valid and some invalid articles."""
        from src.rag.quality.validators import validate_articles

        good = self._valid_payload()
        bad = {"link": "bad", "title": "X", "context": "short"}

        report = validate_articles([good, bad])

        assert len(report.valid) == 1
        assert len(report.rejections) == 1

    def test_empty_batch(self):
        """Test validating an empty list of articles."""
        from src.rag.quality.validators import validate_articles

        report = validate_articles([])

        assert report.total == 0
        assert report.pass_rate == 1.0

    def test_rejection_captures_errors(self):
        """Test that rejections include error details."""
        from src.rag.quality.validators import validate_articles

        bad = {"link": "not-a-url", "title": "A", "context": "short"}
        report = validate_articles([bad])

        assert len(report.rejections) == 1
        rejection = report.rejections[0]
        assert len(rejection.errors) > 0
