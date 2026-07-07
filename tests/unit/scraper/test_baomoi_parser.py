from datetime import datetime

from src.scraper.baomoi import BaomoiParser
from src.scraper.engine.registry import available_sources, get_parser


LISTING_HTML = """
<div class="group/card bm-card relative max-w-full flex w-full">
  <div class="bm-card-image w-[240px] h-[160px]">
    <a href="/phien-cuoi-thang-vn-index-tang-khoi-ngoai-ban-rong-nghin-ty-dong-c55512920.epi" title="Phiên cuối tháng: VN-Index tăng, khối ngoại bán ròng nghìn tỷ đồng">
      <picture><img src="https://photo-baomoi.bmcdn.me/w250_r3x2/2026_06_30_59_55512920/9efe1904454fac11f55e.jpg" /></picture>
    </a>
  </div>
  <div class="bm-card-content">
    <div class="bm-card-header"><a href="/phien-cuoi-thang-vn-index-tang-khoi-ngoai-ban-rong-nghin-ty-dong-c55512920.epi" title="Phiên cuối tháng: VN-Index tăng, khối ngoại bán ròng nghìn tỷ đồng">Phiên cuối tháng: VN-Index tăng, khối ngoại bán ròng nghìn tỷ đồng</a></div>
  </div>
</div>
"""


NO_RESULT_HTML = """
<div class="relative text-[1.6rem] text-[#7d5a29] px-[12.5px] py-[6px] rounded-[2.5px] bg-[#fcefdc] border border-solid border-[#fbe8cd]">Không tìm thấy kết quả phù hợp!</div>
"""


DETAIL_HTML = """
<html>
  <head>
    <meta property="article:published_time" content="2026-06-30T17:39:05.000+07:00" />
    <meta property="article:section" content="Chứng khoán" />
    <meta name="author" content="BAOMOI.COM" />
  </head>
  <body>
    <h1>Phiên cuối tháng: VN-Index tăng, khối ngoại bán ròng nghìn tỷ đồng</h1>
    <h3 class="sapo">Phiên giao dịch cuối cùng của tháng 6 khép lại với sắc xanh nhẹ.</h3>
    <div class="content-body">
      <div class="image-wrapper"><picture><img src="https://photo-baomoi.bmcdn.me/w700_r1/image.jpg" /></picture></div>
      <p class="text media-caption"><em>Thanh khoản cải thiện</em></p>
      <p class="text"><strong>VN-Index tăng nhẹ</strong></p>
      <p class="text">Thị trường chứng khoán Việt Nam khép lại phiên giao dịch ngày 30/6.</p>
    </div>
  </body>
</html>
"""


def test_build_search_url_slugifies_keyword_and_page():
    parser = BaomoiParser()

    assert parser.build_search_url("ACB", 1) == "https://baomoi.com/tim-kiem/ACB.epi"
    assert parser.build_search_url("mb bank", 1) == "https://baomoi.com/tim-kiem/mb-bank.epi"
    assert parser.build_search_url("mb bank", 2) == "https://baomoi.com/tim-kiem/mb-bank/trang2.epi"


def test_parse_listing_extracts_main_cards_only():
    parser = BaomoiParser()

    entries = parser.parse_listing(LISTING_HTML)

    assert len(entries) == 1
    assert entries[0].external_id == "55512920"
    assert entries[0].url == "https://baomoi.com/phien-cuoi-thang-vn-index-tang-khoi-ngoai-ban-rong-nghin-ty-dong-c55512920.epi"
    assert entries[0].title == "Phiên cuối tháng: VN-Index tăng, khối ngoại bán ròng nghìn tỷ đồng"
    assert entries[0].image_url == "https://photo-baomoi.bmcdn.me/w250_r3x2/2026_06_30_59_55512920/9efe1904454fac11f55e.jpg"


def test_listing_exhausted_detects_no_result_message():
    assert BaomoiParser().is_listing_exhausted(NO_RESULT_HTML) is True


def test_parse_detail_extracts_fields_and_blocks():
    detail = BaomoiParser().parse_detail(DETAIL_HTML)

    assert detail.title == "Phiên cuối tháng: VN-Index tăng, khối ngoại bán ròng nghìn tỷ đồng"
    assert detail.summary == "Phiên giao dịch cuối cùng của tháng 6 khép lại với sắc xanh nhẹ."
    assert detail.author == "BAOMOI.COM"
    assert detail.type == "Chứng khoán"
    assert detail.language == "vi"
    assert detail.published_at is not None
    assert detail.published_at.replace(tzinfo=None) == datetime(2026, 6, 30, 17, 39, 5)
    assert detail.content == "VN-Index tăng nhẹ\nThị trường chứng khoán Việt Nam khép lại phiên giao dịch ngày 30/6."
    assert [block.type for block in detail.blocks] == ["image", "text", "text"]
    assert detail.blocks[0].caption == "Thanh khoản cải thiện"
    assert detail.blocks[0].image_url == "https://photo-baomoi.bmcdn.me/w700_r1/image.jpg"


def test_baomoi_is_registered():
    assert "baomoi" in available_sources()
    assert isinstance(get_parser("baomoi"), BaomoiParser)