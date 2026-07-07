from datetime import datetime

from src.scraper.engine.registry import available_sources, get_parser
from src.scraper.thanhnien import ThanhnienParser


LISTING_HTML = """
<div class="total"><span class="value">708</span> kết quả phù hợp</div>
<div class="box-category-item" data-id="185260623105131392">
  <a class="box-category-link-with-avatar img-resize" href="/acb-canh-bao-30-kich-ban-lua-dao-truc-tuyen-pho-bien-tai-viet-nam-185260623105131392.htm" title="ACB cảnh báo 30 kịch bản lừa đảo trực tuyến phổ biến tại Việt Nam">
    <img data-type="avatar" src="https://images2.thanhnien.vn/zoom/237_148/image.jpg" alt="ACB cảnh báo" class="box-category-avatar">
  </a>
  <div class="box-category-content">
    <a class="box-category-category" href="/kinh-te.htm" title="Kinh tế">Kinh tế</a>
    <div class="box-time" title="2026-06-23T10:45:00">10:45, 23/06/2026</div>
    <h3 class="box-title-text">
      <a data-linktype="newsdetail" class="box-category-link-title" href="/acb-canh-bao-30-kich-ban-lua-dao-truc-tuyen-pho-bien-tai-viet-nam-185260623105131392.htm" title="ACB cảnh báo 30 kịch bản lừa đảo trực tuyến phổ biến tại Việt Nam">ACB cảnh báo 30 kịch bản lừa đảo trực tuyến phổ biến tại Việt Nam</a>
    </h3>
    <a href="/acb-canh-bao-30-kich-ban-lua-dao-truc-tuyen-pho-bien-tai-viet-nam-185260623105131392.htm" title="Sapo title" data-type="sapo" class="box-category-sapo d-block">Lừa đảo sử dụng AI và Deepfake đang gia tăng.</a>
  </div>
</div>
"""


DETAIL_HTML = """
<html>
  <head>
    <meta property="article:published_time" content="2026-06-23T10:45:00+07:00" />
    <meta property="article:section" content="Kinh tế" />
  </head>
  <body>
    <h1 class="detail-title">ACB cảnh báo 30 kịch bản lừa đảo trực tuyến phổ biến tại Việt Nam</h1>
    <h2 class="detail-sapo">Lừa đảo sử dụng AI và Deepfake đang gia tăng.</h2>
    <div class="detail-author">Thanh Niên</div>
    <div class="detail-content">
      <p>Đoạn nội dung thứ nhất.</p>
      <figure>
        <img src="/uploads/detail.jpg" />
        <figcaption>Ảnh minh họa</figcaption>
      </figure>
      <p>Đoạn nội dung thứ hai.</p>
    </div>
    <div class="tags"><a href="/acb-tags496799.html">ACB</a><a href="/lua-dao-tags528741.html">lừa đảo</a></div>
  </body>
</html>
"""


def test_build_search_url_encodes_keyword():
    parser = ThanhnienParser()

    assert parser.build_search_url("ACB", 1) == "https://thanhnien.vn/tim-kiem.htm?keywords=ACB"
    assert parser.build_search_url("ngân hàng", 1).endswith("keywords=ng%C3%A2n+h%C3%A0ng")


def test_parse_listing_extracts_total_and_entries():
    parser = ThanhnienParser()

    entries = parser.parse_listing(LISTING_HTML)

    assert parser.parse_total_results(LISTING_HTML) == 708
    assert len(entries) == 1
    assert entries[0].external_id == "185260623105131392"
    assert entries[0].url == "https://thanhnien.vn/acb-canh-bao-30-kich-ban-lua-dao-truc-tuyen-pho-bien-tai-viet-nam-185260623105131392.htm"
    assert entries[0].title == "ACB cảnh báo 30 kịch bản lừa đảo trực tuyến phổ biến tại Việt Nam"
    assert entries[0].summary == "Lừa đảo sử dụng AI và Deepfake đang gia tăng."
    assert entries[0].image_url == "https://images2.thanhnien.vn/zoom/237_148/image.jpg"


def test_parse_detail_extracts_cafef_compatible_fields():
    parser = ThanhnienParser()

    detail = parser.parse_detail(DETAIL_HTML)

    assert detail.title == "ACB cảnh báo 30 kịch bản lừa đảo trực tuyến phổ biến tại Việt Nam"
    assert detail.summary == "Lừa đảo sử dụng AI và Deepfake đang gia tăng."
    assert detail.author == "Thanh Niên"
    assert detail.type == "Kinh tế"
    assert detail.tag == "ACB, lừa đảo"
    assert detail.language == "vi"
    assert detail.published_at is not None
    assert detail.published_at.replace(tzinfo=None) == datetime(2026, 6, 23, 10, 45)
    assert detail.content == "Đoạn nội dung thứ nhất.\nĐoạn nội dung thứ hai."
    assert [block.type for block in detail.blocks] == ["text", "image", "text"]
    assert detail.blocks[1].image_url == "https://thanhnien.vn/uploads/detail.jpg"


def test_thanhnien_is_registered():
    assert "thanhnien" in available_sources()
    assert isinstance(get_parser("thanhnien"), ThanhnienParser)