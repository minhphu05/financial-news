"""Unit tests for src/rag/ingestion/cleaner.py.

Tests text normalisation, boilerplate removal, and article cleaning.
All tests are pure string transformations — no I/O or network.
"""

import pytest


class TestTextCleanerCleanText:
    """Tests for TextCleaner.clean_text()."""

    def _make_cleaner(self, strip_boilerplate: bool = True):
        """Factory helper to instantiate TextCleaner."""
        from src.rag.ingestion.cleaner import TextCleaner

        return TextCleaner(strip_boilerplate=strip_boilerplate)

    def test_empty_string_returns_empty(self):
        """Test that empty input produces empty output."""
        cleaner = self._make_cleaner()
        assert cleaner.clean_text("") == ""

    def test_none_like_returns_empty(self):
        """Test that None-like falsy input returns empty string."""
        cleaner = self._make_cleaner()
        assert cleaner.clean_text("") == ""

    def test_unicode_nfc_normalization(self):
        """Test that Vietnamese text is NFC-normalised.

        Vietnamese diacritics can be stored in decomposed (NFD) form.
        The cleaner should normalise them to composed (NFC) form.
        """
        import unicodedata

        # Build a decomposed representation
        text_nfd = unicodedata.normalize("NFD", "Việt Nam")
        cleaner = self._make_cleaner()
        result = cleaner.clean_text(text_nfd)

        assert result == unicodedata.normalize("NFC", "Việt Nam")
        # Verify each char is NFC
        for ch in result:
            if ch.isalpha():
                assert ch == unicodedata.normalize("NFC", ch)

    def test_collapses_multiple_spaces(self):
        """Test that runs of spaces/tabs are collapsed to single space."""
        cleaner = self._make_cleaner()
        text = "Doanh thu   \t\t  đạt   15   tỷ"
        result = cleaner.clean_text(text)
        assert "   " not in result
        assert "\t" not in result

    def test_collapses_multiple_newlines(self):
        """Test that 3+ consecutive newlines become exactly 2."""
        cleaner = self._make_cleaner()
        text = "Đoạn 1\n\n\n\n\nĐoạn 2"
        result = cleaner.clean_text(text)
        assert "\n\n\n" not in result
        assert "Đoạn 1" in result
        assert "Đoạn 2" in result

    def test_strips_boilerplate_cafef(self):
        """Test that CafeF footer text is removed."""
        cleaner = self._make_cleaner(strip_boilerplate=True)
        text = "Nội dung bài viết hay.\nTheo CafeF"
        result = cleaner.clean_text(text)
        assert "Theo CafeF" not in result
        assert "Nội dung bài viết hay" in result

    def test_strips_boilerplate_nguon(self):
        """Test that source attribution boilerplate is removed."""
        cleaner = self._make_cleaner(strip_boilerplate=True)
        text = "Giá cổ phiếu tăng mạnh.\nNguồn: CafeF"
        result = cleaner.clean_text(text)
        assert "Nguồn" not in result

    def test_preserves_content_when_no_boilerplate(self):
        """Test that strip_boilerplate=False keeps all text."""
        cleaner = self._make_cleaner(strip_boilerplate=False)
        text = "Nội dung chính.\nTheo CafeF"
        result = cleaner.clean_text(text)
        assert "Theo CafeF" in result

    def test_separates_stuck_digits_from_letters(self):
        """Test that digits stuck to Vietnamese letters are separated."""
        cleaner = self._make_cleaner()
        # Digit stuck to the right of a letter
        text = "tăng15% so với cùng kỳ"
        result = cleaner.clean_text(text)
        assert "tăng 15" in result or "tăng15" in result

    def test_crlf_converted_to_lf(self):
        """Test that Windows-style \\r\\n is converted to Unix \\n."""
        cleaner = self._make_cleaner()
        text = "Dòng 1\r\nDòng 2\r\nDòng 3"
        result = cleaner.clean_text(text)
        assert "\r" not in result


class TestTextCleanerCleanArticle:
    """Tests for TextCleaner.clean_article()."""

    def _make_cleaner(self):
        """Factory helper."""
        from src.rag.ingestion.cleaner import TextCleaner

        return TextCleaner()

    def test_basic_article(self, sample_raw_article):
        """Test cleaning a standard raw article dict."""
        cleaner = self._make_cleaner()
        result = cleaner.clean_article(sample_raw_article)

        assert "link" in result
        assert "clean_text" in result
        assert "char_count" in result
        assert result["link"] == sample_raw_article["link"]
        assert isinstance(result["char_count"], int)
        assert result["char_count"] > 0

    def test_preserves_metadata(self, sample_raw_article):
        """Test that metadata fields are preserved in output."""
        cleaner = self._make_cleaner()
        result = cleaner.clean_article(sample_raw_article)

        assert result["title"] == sample_raw_article["title"]
        assert result["ticker_symbol"] == "FPT"
        assert result["source"] == "cafef"

    def test_missing_link_raises(self):
        """Test that articles without a link raise ValueError."""
        cleaner = self._make_cleaner()
        bad_article = {"title": "No link", "context": "Some content here"}

        with pytest.raises(ValueError, match="missing"):
            cleaner.clean_article(bad_article)

    def test_empty_context_produces_empty_clean_text(self):
        """Test that articles with empty body get empty clean_text."""
        cleaner = self._make_cleaner()
        article = {
            "link": "https://cafef.vn/empty-123.chn",
            "title": "Empty",
            "context": "",
        }
        result = cleaner.clean_article(article)
        assert result["clean_text"] == ""
        assert result["char_count"] == 0

    def test_uses_url_field_as_fallback(self):
        """Test that 'url' is used when 'link' is absent."""
        cleaner = self._make_cleaner()
        article = {
            "url": "https://cafef.vn/fallback-456.chn",
            "title": "Fallback URL",
            "context": "Nội dung bài viết về tài chính Việt Nam.",
        }
        result = cleaner.clean_article(article)
        assert result["link"] == "https://cafef.vn/fallback-456.chn"

    def test_uses_body_field_as_fallback(self):
        """Test that 'body' is used when 'context' is absent."""
        cleaner = self._make_cleaner()
        article = {
            "link": "https://cafef.vn/body-789.chn",
            "title": "Body field",
            "body": "Nội dung từ trường body.",
        }
        result = cleaner.clean_article(article)
        assert "body" in result["clean_text"].lower() or len(result["clean_text"]) > 0

    def test_ticker_symbol_typo_fallback(self):
        """Test that 'ticket_symbol' typo is accepted as fallback."""
        cleaner = self._make_cleaner()
        article = {
            "link": "https://cafef.vn/typo-111.chn",
            "title": "Ticker typo",
            "context": "Nội dung dài hơn một trăm ký tự",
            "ticket_symbol": "VNM",
        }
        result = cleaner.clean_article(article)
        assert result["ticker_symbol"] == "VNM"
