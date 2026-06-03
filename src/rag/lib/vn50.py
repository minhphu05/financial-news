"""VN50 stock catalogue.

The VN50 index lists the 50 largest, most liquid companies on the
Ho Chi Minh Stock Exchange (HOSE). This module provides a stable,
machine-readable view of those tickers so the API and frontend can
present user-friendly company names without hitting a third-party feed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass(frozen=True)
class StockInfo:
    """Lightweight company descriptor used by the API.

    Attributes
    ----------
    ticker : str
        HOSE ticker symbol (e.g. ``"BCM"``).
    name_vi : str
        Vietnamese company name (used for display).
    name_en : str
        English company name.
    sector : str
        Coarse-grained sector classification.
    """

    ticker: str
    name_vi: str
    name_en: str
    sector: str


# ---------------------------------------------------------------------------
# VN50 master list
# ---------------------------------------------------------------------------
VN50_STOCKS: List[StockInfo] = [
    StockInfo("ACB", "Ngân hàng Á Châu", "Asia Commercial Bank", "Ngân hàng"),
    StockInfo("BCM", "Tổng công ty IDICO Becamex", "Becamex IDC", "Bất động sản KCN"),
    StockInfo("BID", "Ngân hàng BIDV", "BIDV", "Ngân hàng"),
    StockInfo("BVH", "Tập đoàn Bảo Việt", "Bao Viet Holdings", "Bảo hiểm"),
    StockInfo("CTG", "Ngân hàng VietinBank", "VietinBank", "Ngân hàng"),
    StockInfo("DGC", "Tập đoàn Hóa chất Đức Giang", "Duc Giang Chemicals", "Hóa chất"),
    StockInfo("DIG", "Tổng CTCP Đầu tư Phát triển Xây dựng", "DIC Corp", "Bất động sản"),
    StockInfo("DPM", "Đạm Phú Mỹ", "Petrovietnam Fertilizer", "Phân bón"),
    StockInfo("EIB", "Ngân hàng Eximbank", "Eximbank", "Ngân hàng"),
    StockInfo("FPT", "Tập đoàn FPT", "FPT Corporation", "Công nghệ"),
    StockInfo("GAS", "Tổng công ty Khí Việt Nam", "PetroVietnam Gas", "Dầu khí"),
    StockInfo("GMD", "Gemadept", "Gemadept", "Logistics"),
    StockInfo("GVR", "Tập đoàn Công nghiệp Cao su Việt Nam", "Vietnam Rubber Group", "Cao su"),
    StockInfo("HDB", "Ngân hàng HDBank", "HDBank", "Ngân hàng"),
    StockInfo("HPG", "Tập đoàn Hòa Phát", "Hoa Phat Group", "Thép"),
    StockInfo("KBC", "Tổng công ty Phát triển Đô thị Kinh Bắc", "Kinh Bac City", "Bất động sản KCN"),
    StockInfo("KDH", "Nhà Khang Điền", "Khang Dien House", "Bất động sản"),
    StockInfo("MBB", "Ngân hàng MB", "MB Bank", "Ngân hàng"),
    StockInfo("MSN", "Tập đoàn Masan", "Masan Group", "Hàng tiêu dùng"),
    StockInfo("MWG", "Đầu tư Thế Giới Di Động", "Mobile World", "Bán lẻ"),
    StockInfo("NVL", "Tập đoàn Novaland", "Novaland Group", "Bất động sản"),
    StockInfo("OCB", "Ngân hàng Phương Đông", "Orient Commercial Bank", "Ngân hàng"),
    StockInfo("PDR", "Bất động sản Phát Đạt", "Phat Dat Real Estate", "Bất động sản"),
    StockInfo("PLX", "Tập đoàn Xăng dầu Việt Nam", "Petrolimex", "Dầu khí"),
    StockInfo("PNJ", "Vàng bạc Đá quý Phú Nhuận", "Phu Nhuan Jewelry", "Bán lẻ"),
    StockInfo("POW", "Tổng công ty Điện lực Dầu khí", "PetroVietnam Power", "Năng lượng"),
    StockInfo("REE", "Cơ Điện Lạnh", "REE Corporation", "Tiện ích"),
    StockInfo("SAB", "Tổng công ty Bia - Rượu - NGK Sài Gòn", "Sabeco", "Đồ uống"),
    StockInfo("SBT", "Thành Thành Công - Biên Hòa", "TTC Sugar", "Mía đường"),
    StockInfo("SHB", "Ngân hàng Sài Gòn - Hà Nội", "SHB Bank", "Ngân hàng"),
    StockInfo("SSB", "Ngân hàng SeABank", "SeABank", "Ngân hàng"),
    StockInfo("SSI", "Chứng khoán SSI", "SSI Securities", "Chứng khoán"),
    StockInfo("STB", "Ngân hàng Sacombank", "Sacombank", "Ngân hàng"),
    StockInfo("TCB", "Ngân hàng Techcombank", "Techcombank", "Ngân hàng"),
    StockInfo("TPB", "Ngân hàng TPBank", "TPBank", "Ngân hàng"),
    StockInfo("VCB", "Ngân hàng Vietcombank", "Vietcombank", "Ngân hàng"),
    StockInfo("VCI", "Chứng khoán Bản Việt", "Viet Capital Securities", "Chứng khoán"),
    StockInfo("VGC", "Tổng công ty Viglacera", "Viglacera", "Vật liệu xây dựng"),
    StockInfo("VHM", "Vinhomes", "Vinhomes", "Bất động sản"),
    StockInfo("VIB", "Ngân hàng Quốc tế", "VIB Bank", "Ngân hàng"),
    StockInfo("VIC", "Tập đoàn Vingroup", "Vingroup", "Đa ngành"),
    StockInfo("VJC", "Hàng không VietJet", "VietJet Air", "Hàng không"),
    StockInfo("VND", "Chứng khoán VNDIRECT", "VNDirect Securities", "Chứng khoán"),
    StockInfo("VNM", "Vinamilk", "Vinamilk", "Sữa & thực phẩm"),
    StockInfo("VPB", "Ngân hàng VPBank", "VPBank", "Ngân hàng"),
    StockInfo("VRE", "Vincom Retail", "Vincom Retail", "Bán lẻ BĐS"),
    StockInfo("VSH", "Thủy điện Vĩnh Sơn - Sông Hinh", "Vinh Son Hydro Power", "Năng lượng"),
    StockInfo("DCM", "Đạm Cà Mau", "Petrovietnam Ca Mau Fertilizer", "Phân bón"),
    StockInfo("HVN", "Vietnam Airlines", "Vietnam Airlines", "Hàng không"),
    StockInfo("LPB", "Ngân hàng LPBank", "Lien Viet Post Bank", "Ngân hàng"),
]


# Quick-lookup dict
_BY_TICKER: Dict[str, StockInfo] = {s.ticker: s for s in VN50_STOCKS}


def get_vn50_ticker(ticker: str) -> Optional[StockInfo]:
    """Return :class:`StockInfo` for ``ticker`` or ``None`` if unknown.

    Parameters
    ----------
    ticker : str
        Case-insensitive ticker symbol.

    Returns
    -------
    Optional[StockInfo]
        Matching descriptor, or ``None`` for unknown tickers.
    """
    return _BY_TICKER.get(ticker.upper())
