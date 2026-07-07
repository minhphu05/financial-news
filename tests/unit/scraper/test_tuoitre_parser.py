from datetime import datetime

from src.scraper.engine.registry import available_sources, get_parser
from src.scraper.tuoitre import TuoitreParser


LISTING_HTML = """
<div class="total-search"><span class="bold">1128</span> kết quả phù hợp</div>
<article class="box-category-item" data-newsid="100260625175602723">
  <a class="box-category-link-with-avatar img-resize" href="/gan-60-co-phieu-bank-tro-lai-tich-cuc-ti-phu-pham-nhat-vuong-mua-trung-ma-manh-nhat-100260625175602723.htm" title="Gần 60% cổ phiếu bank trở lại tích cực">
    <img class="box-category-avatar" src="https://cdn2.tuoitre.vn/zoom/260_163/image.jpg" />
  </a>
  <div class="box-category-content">
    <h3 class="box-category-title-text">
      <a class="box-category-link-title" href="/gan-60-co-phieu-bank-tro-lai-tich-cuc-ti-phu-pham-nhat-vuong-mua-trung-ma-manh-nhat-100260625175602723.htm" title="Gần 60% cổ phiếu bank trở lại tích cực">Gần 60% cổ phiếu bank trở lại tích cực</a>
    </h3>
    <a class="box-category-category" href="/chung-khoan/phan-tich-nhan-dinh.htm">Phân tích - Nhận định</a>
    <span class="box-category-time time-ago" title="6/25/2026 6:37:00 PM">18:37 25/06/2026</span>
    <p class="box-category-sapo">Nhóm cổ phiếu vua đang có sự trở lại.</p>
  </div>
</article>
"""


DETAIL_HTML = """
<html>
  <head>
    <meta property="article:section" content="Phân tích - Nhận định" />
  </head>
  <body>
    <h1 class="detail-title">Gần 60% cổ phiếu bank trở lại tích cực</h1>
    <div class="detail-sapo">Nhóm cổ phiếu vua đang có sự trở lại.</div>
    <div class="detail-time">25/06/2026 18:37 GMT+7</div>
    <div class="detail-author">HỌC KHIÊM</div>
    <div class="detail-content">
      <figure>
        <a href="https://cdn2.tuoitre.vn/full.jpg"><img data-original="https://cdn2.tuoitre.vn/full.jpg" src="https://cdn2.tuoitre.vn/thumb.jpg" /></a>
        <figcaption class="PhotoCMS_Caption"><p>Ảnh minh họa</p></figcaption>
      </figure>
      <h2><b>Cổ phiếu LPB tăng mạnh</b></h2>
      <p>Đoạn nội dung thứ nhất.</p>
      <p>Đoạn nội dung thứ hai.</p>
    </div>
    <div class="tags"><a href="/tag/acb.htm">ACB</a><a href="/tag/chung-khoan.htm">chứng khoán</a></div>
  </body>
</html>
"""


def test_build_search_url_encodes_keyword():
    parser = TuoitreParser()

    assert parser.build_search_url("ACB", 1) == "https://tuoitre.vn/tim-kiem.htm?keywords=ACB"
    assert parser.build_search_url("ngân hàng", 1).endswith("keywords=ng%C3%A2n+h%C3%A0ng")


def test_parse_listing_extracts_total_and_entries():
    parser = TuoitreParser()

    entries = parser.parse_listing(LISTING_HTML)

    assert parser.parse_total_results(LISTING_HTML) == 1128
    assert len(entries) == 1
    assert entries[0].external_id == "100260625175602723"
    assert entries[0].url == "https://tuoitre.vn/gan-60-co-phieu-bank-tro-lai-tich-cuc-ti-phu-pham-nhat-vuong-mua-trung-ma-manh-nhat-100260625175602723.htm"
    assert entries[0].title == "Gần 60% cổ phiếu bank trở lại tích cực"
    assert entries[0].summary == "Nhóm cổ phiếu vua đang có sự trở lại."
    assert entries[0].image_url == "https://cdn2.tuoitre.vn/zoom/260_163/image.jpg"


def test_parse_detail_extracts_article_fields_and_blocks():
    detail = TuoitreParser().parse_detail(DETAIL_HTML)

    assert detail.title == "Gần 60% cổ phiếu bank trở lại tích cực"
    assert detail.summary == "Nhóm cổ phiếu vua đang có sự trở lại."
    assert detail.author == "HỌC KHIÊM"
    assert detail.type == "Phân tích - Nhận định"
    assert detail.tag == "ACB, chứng khoán"
    assert detail.language == "vi"
    assert detail.published_at is not None
    assert detail.published_at.replace(tzinfo=None) == datetime(2026, 6, 25, 18, 37)
    assert detail.content == "Cổ phiếu LPB tăng mạnh\nĐoạn nội dung thứ nhất.\nĐoạn nội dung thứ hai."
    assert [block.type for block in detail.blocks] == ["image", "text", "text", "text"]
    assert detail.blocks[0].image_url == "https://cdn2.tuoitre.vn/full.jpg"
    assert detail.blocks[0].caption == "Ảnh minh họa"


def test_tuoitre_is_registered():
    assert "tuoitre" in available_sources()
    assert isinstance(get_parser("tuoitre"), TuoitreParser)