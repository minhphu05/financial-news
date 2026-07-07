from datetime import datetime

from src.scraper.engine.registry import available_sources, get_parser
from src.scraper.vnexpress import VnexpressParser


LISTING_HTML = """
<article class="item-news item-news-common" data-publishtime="1780657200" data-url="https://vnexpress.net/acb-ra-mat-nen-tang-dong-gop-xanh-5082381.html">
  <div class="thumb-art">
    <a class="thumb thumb-5x3" href="https://vnexpress.net/acb-ra-mat-nen-tang-dong-gop-xanh-5082381.html" title="ACB ra mắt nền tảng 'Đóng góp xanh'">
      <picture>
        <source data-srcset="https://i1-kinhdoanh.vnecdn.net/2026/06/05/pr-xanh.jpg?w=300&amp;h=180 1x, https://i1-kinhdoanh.vnecdn.net/2026/06/05/pr-xanh.jpg?w=600&amp;h=360 2x" />
        <img src="data:image/gif;base64,R0lGODlhAQABAAAA" />
      </picture>
    </a>
  </div>
  <h3 class="title-news">
    <a href="https://vnexpress.net/acb-ra-mat-nen-tang-dong-gop-xanh-5082381.html" title="ACB ra mắt nền tảng 'Đóng góp xanh'">ACB ra mắt nền tảng 'Đóng góp xanh'</a>
  </h3>
  <p class="description"><a href="https://vnexpress.net/acb-ra-mat-nen-tang-dong-gop-xanh-5082381.html">ACB triển khai nền tảng Đóng góp xanh.</a></p>
</article>
"""


NO_RESULT_HTML = """
<p class="mb20 no-result">Không tìm thấy kết quả chứa từ khóa của bạn</p>
"""


DETAIL_HTML = """
<html>
  <head>
    <meta property="article:section" content="Kinh doanh" />
  </head>
  <body>
    <ul class="breadcrumb"><li><a>Kinh doanh</a></li><li><a>Doanh nghiệp</a></li></ul>
    <span class="date">Thứ sáu, 5/6/2026, 18:00 (GMT+7)</span>
    <h1 class="title-detail">ACB ra mắt nền tảng 'Đóng góp xanh'</h1>
    <p class="description">ACB triển khai nền tảng Đóng góp xanh.</p>
    <article class="fck_detail">
      <p class="Normal">Đoạn nội dung thứ nhất.</p>
      <figure>
        <picture><img data-src="https://i1-kinhdoanh.vnecdn.net/2026/06/05/detail.jpg" /></picture>
        <figcaption>Ảnh minh họa</figcaption>
      </figure>
      <p class="Normal">Đoạn nội dung thứ hai.</p>
      <p class="author">VnExpress</p>
    </article>
  </body>
</html>
"""


def test_build_search_url_encodes_keyword_and_page():
    parser = VnexpressParser()

    assert parser.build_search_url("ACB", 1) == "https://timkiem.vnexpress.net/?q=ACB&page=1"
    assert parser.build_search_url("ngân hàng", 2).endswith("q=ng%C3%A2n+h%C3%A0ng&page=2")


def test_parse_listing_extracts_entries_and_images():
    parser = VnexpressParser()

    entries = parser.parse_listing(LISTING_HTML)

    assert len(entries) == 1
    assert entries[0].external_id == "5082381"
    assert entries[0].url == "https://vnexpress.net/acb-ra-mat-nen-tang-dong-gop-xanh-5082381.html"
    assert entries[0].title == "ACB ra mắt nền tảng 'Đóng góp xanh'"
    assert entries[0].summary == "ACB triển khai nền tảng Đóng góp xanh."
    assert entries[0].image_url == "https://i1-kinhdoanh.vnecdn.net/2026/06/05/pr-xanh.jpg?w=300&h=180"


def test_listing_exhausted_detects_no_result_block():
    assert VnexpressParser().is_listing_exhausted(NO_RESULT_HTML) is True


def test_parse_detail_extracts_article_fields_and_blocks():
    detail = VnexpressParser().parse_detail(DETAIL_HTML)

    assert detail.title == "ACB ra mắt nền tảng 'Đóng góp xanh'"
    assert detail.summary == "ACB triển khai nền tảng Đóng góp xanh."
    assert detail.type == "Kinh doanh"
    assert detail.language == "vi"
    assert detail.published_at is not None
    assert detail.published_at.replace(tzinfo=None) == datetime(2026, 6, 5, 18, 0)
    assert detail.content == "Đoạn nội dung thứ nhất.\nĐoạn nội dung thứ hai.\nVnExpress"
    assert [block.type for block in detail.blocks] == ["text", "image", "text", "text"]
    assert detail.blocks[1].image_url == "https://i1-kinhdoanh.vnecdn.net/2026/06/05/detail.jpg"


def test_vnexpress_is_registered():
    assert "vnexpress" in available_sources()
    assert isinstance(get_parser("vnexpress"), VnexpressParser)