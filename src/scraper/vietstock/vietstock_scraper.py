"""
Local-only scraper for Vietstock electronic price boards.

This module intentionally does not use the shared news scraper engine because
Vietstock's board is market data, not article/listing/detail content. For the
large exchanges (HOSE, HNX, UPCOM), it renders the page, waits, scrolls to the
bottom while collecting rows, and exports the gathered board data to Excel for
local inspection.
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import re
import time
from decimal import Decimal, InvalidOperation
from datetime import datetime
from pathlib import Path
from typing import Iterable

import pandas as pd
import requests
from bs4 import BeautifulSoup
from bs4.element import Tag

BASE_URL = "https://banggia.vietstock.vn/bang-gia/{exchange}"
EXCHANGES = ("hose", "vn30", "hnx", "hnx30", "upcom")
STANDARD_FLOW_EXCHANGES = ("hose", "hnx", "vn30", "hnx30")
METRIC_EXCHANGES = frozenset({"hose", "hnx"})
INDEX_EXCHANGES = {"vn30": "VN30", "hnx30": "HNX30"}
SCROLL_EXCHANGES = frozenset({"hose", "hnx", "upcom"})
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "data"

REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; FinancialNewsBot/2.0)",
    "Accept-Language": "vi,en;q=0.9",
}


def _clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = " ".join(value.split())
    return cleaned or None


def _cell_text(cells: list[Tag], index: int) -> str | None:
    if index >= len(cells):
        return None
    return _clean_text(cells[index].get_text(" ", strip=True))


def _span_text(cell: Tag, selector: str) -> str | None:
    node = cell.select_one(selector)
    return _clean_text(node.get_text(" ", strip=True)) if node else None


def _extract_row(row: Tag, exchange: str, source_url: str, scraped_at: str) -> dict[str, str | None]:
    cells = row.find_all("td", recursive=False)
    if len(cells) < 26:
        return {}

    symbol_cell = cells[0]
    symbol = row.get("data-symbol") or _span_text(symbol_cell, ".stock-symbol-s")
    company_name = _span_text(symbol_cell, ".tooltip-stock-name")
    stock_id = None
    symbol_node = symbol_cell.select_one(".stock-symbol-s")
    if symbol_node is not None:
        stock_id = symbol_node.get("data-id")

    total_volume = _span_text(cells[20], ".field-sum-vol") or _cell_text(cells, 20)
    total_value = _span_text(cells[20], ".field-sum-val")

    return {
        "exchange": exchange,
        "symbol": symbol,
        "stock_id": stock_id,
        "company_name": company_name,
        "reference_price": _cell_text(cells, 1),
        "ceiling_price": _cell_text(cells, 2),
        "floor_price": _cell_text(cells, 3),
        "bid_price_3": _cell_text(cells, 4),
        "bid_volume_3": _cell_text(cells, 5),
        "bid_price_2": _cell_text(cells, 6),
        "bid_volume_2": _cell_text(cells, 7),
        "bid_price_1": _cell_text(cells, 8),
        "bid_volume_1": _cell_text(cells, 9),
        "matched_price": _cell_text(cells, 10),
        "matched_volume": _cell_text(cells, 11),
        "change": _cell_text(cells, 12),
        "change_percent": _cell_text(cells, 13),
        "ask_price_1": _cell_text(cells, 14),
        "ask_volume_1": _cell_text(cells, 15),
        "ask_price_2": _cell_text(cells, 16),
        "ask_volume_2": _cell_text(cells, 17),
        "ask_price_3": _cell_text(cells, 18),
        "ask_volume_3": _cell_text(cells, 19),
        "total_volume": total_volume,
        "total_value": total_value,
        "high_price": _cell_text(cells, 21),
        "low_price": _cell_text(cells, 22),
        "average_price": _cell_text(cells, 23),
        "foreign_buy_volume": _cell_text(cells, 24),
        "foreign_sell_volume": _cell_text(cells, 25),
        "source_url": source_url,
        "scraped_at": scraped_at,
    }


def _extract_records(html: str, exchange: str, source_url: str) -> list[dict[str, str | None]]:
    soup = BeautifulSoup(html, "html.parser")
    table = soup.select_one("table.table-price-board:not(.table-header-width)")
    if table is None:
        raise ValueError(f"Could not find Vietstock price-board table for {exchange!r}.")

    scraped_at = datetime.now().isoformat(timespec="seconds")
    records = []
    for row in table.select("tbody tr"):
        record = _extract_row(row, exchange, source_url, scraped_at)
        if record:
            records.append(record)
    return records


def parse_price_board(html: str, exchange: str, source_url: str) -> pd.DataFrame:
    """Parse the Vietstock price-board table from one exchange page."""
    records = _extract_records(html, exchange, source_url)

    return pd.DataFrame(records)


def scrape_exchange(
    exchange: str,
    *,
    timeout: int = 30,
    use_browser: bool | None = None,
    browser_engine: str = "auto",
    wait_ms: int = 1200,
    scroll_step: int = 900,
    max_scrolls: int = 180,
    progress: bool = False,
) -> pd.DataFrame:
    """Fetch and parse one Vietstock exchange board."""
    exchange_key = exchange.lower().strip()
    if exchange_key not in EXCHANGES:
        raise ValueError(f"Unknown exchange {exchange!r}. Expected one of: {', '.join(EXCHANGES)}")

    if use_browser is None:
        use_browser = exchange_key in SCROLL_EXCHANGES

    if use_browser:
        return scrape_exchange_with_browser(
            exchange_key,
            timeout=timeout,
            browser_engine=browser_engine,
            wait_ms=wait_ms,
            scroll_step=scroll_step,
            max_scrolls=max_scrolls,
            progress=progress,
        )

    return scrape_exchange_snapshot(exchange_key, timeout=timeout)


def scrape_exchange_snapshot(exchange: str, *, timeout: int = 30) -> pd.DataFrame:
    """Fetch and parse the initial non-scrolled HTML snapshot for one board."""
    exchange_key = exchange.lower().strip()
    url = BASE_URL.format(exchange=exchange_key)
    response = requests.get(url, headers=REQUEST_HEADERS, timeout=timeout)
    response.raise_for_status()
    return parse_price_board(response.text, exchange_key, url)


def scrape_exchange_with_browser(
    exchange: str,
    *,
    timeout: int = 30,
    browser_engine: str = "auto",
    wait_ms: int = 1200,
    scroll_step: int = 900,
    max_scrolls: int = 180,
    progress: bool = False,
) -> pd.DataFrame:
    """Render, wait, scroll to the bottom, and collect board rows along the way."""
    engine = browser_engine.lower().strip()
    if engine == "auto":
        env_engine = os.environ.get("SCRAPER_BROWSER_ENGINE", "").lower().strip()
        if env_engine in {"selenium", "playwright"}:
            engine = env_engine
        elif importlib.util.find_spec("selenium") is not None:
            engine = "selenium"
        elif importlib.util.find_spec("playwright") is not None:
            engine = "playwright"
        else:
            raise RuntimeError(
                "Install selenium or playwright to scroll Vietstock large boards, "
                "or pass --render static."
            )

    if engine == "selenium":
        return scrape_exchange_with_selenium(
            exchange,
            timeout=timeout,
            wait_ms=wait_ms,
            scroll_step=scroll_step,
            max_scrolls=max_scrolls,
            progress=progress,
        )
    if engine == "playwright":
        return scrape_exchange_with_playwright(
            exchange,
            timeout=timeout,
            wait_ms=wait_ms,
            scroll_step=scroll_step,
            max_scrolls=max_scrolls,
            progress=progress,
        )
    raise ValueError("browser_engine must be one of: auto, selenium, playwright")


def scrape_exchange_with_playwright(
    exchange: str,
    *,
    timeout: int = 30,
    wait_ms: int = 1200,
    scroll_step: int = 900,
    max_scrolls: int = 180,
    progress: bool = False,
) -> pd.DataFrame:
    """Render and scroll a board with Playwright Chromium."""
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "Playwright is required to scroll Vietstock large boards. "
            "Install it and run `playwright install chromium`, or pass --render static."
        ) from exc

    exchange_key = exchange.lower().strip()
    url = BASE_URL.format(exchange=exchange_key)
    timeout_ms = timeout * 1000
    records_by_symbol: dict[str, dict[str, str | None]] = {}

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=True,
            args=["--disable-features=AsyncDns"],
        )
        try:
            page = browser.new_page(
                viewport={"width": 1440, "height": 950},
                extra_http_headers=REQUEST_HEADERS,
                ignore_https_errors=True,
            )
            page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            page.wait_for_selector(
                "table.table-price-board:not(.table-header-width) tbody tr",
                timeout=timeout_ms,
            )
            page.wait_for_timeout(wait_ms)

            _merge_records(records_by_symbol, _extract_records(page.content(), exchange_key, url))
            if progress:
                print(
                    f"  {exchange_key.upper()}: initial render collected "
                    f"{len(records_by_symbol)} rows...",
                    flush=True,
                )
            if len(records_by_symbol) > 30:
                return pd.DataFrame(records_by_symbol.values())

            stable_bottom_count = 0
            no_new_count = 0
            previous_scroll_top = -1
            previous_row_count = -1

            for scroll_index in range(max_scrolls):
                before_count = len(records_by_symbol)
                _merge_records(records_by_symbol, _extract_records(page.content(), exchange_key, url))
                no_new_count = no_new_count + 1 if len(records_by_symbol) == before_count else 0
                if progress and scroll_index % 20 == 0:
                    print(
                        f"  {exchange_key.upper()}: scroll {scroll_index}, "
                        f"collected {len(records_by_symbol)} rows...",
                        flush=True,
                    )

                state = page.evaluate(
                    """
                    (step) => {
                        const scrollingElement = document.scrollingElement || document.documentElement;
                        const before = scrollingElement.scrollTop;
                        window.scrollBy(0, step);
                        return {
                            before,
                            after: scrollingElement.scrollTop,
                            clientHeight: scrollingElement.clientHeight,
                            scrollHeight: scrollingElement.scrollHeight,
                            rowCount: document.querySelectorAll('table.table-price-board:not(.table-header-width) tbody tr').length
                        };
                    }
                    """,
                    scroll_step,
                )
                page.wait_for_timeout(wait_ms)

                at_bottom = state["after"] + state["clientHeight"] >= state["scrollHeight"] - 4
                row_count_stable = state["rowCount"] == previous_row_count
                scroll_stable = state["after"] == previous_scroll_top
                if at_bottom and row_count_stable and scroll_stable:
                    stable_bottom_count += 1
                else:
                    stable_bottom_count = 0

                previous_scroll_top = state["after"]
                previous_row_count = state["rowCount"]

                if stable_bottom_count >= 2 or no_new_count >= 12:
                    break

            _merge_records(records_by_symbol, _extract_records(page.content(), exchange_key, url))
        except PlaywrightTimeoutError as exc:
            raise RuntimeError(f"Timed out while loading Vietstock board for {exchange_key!r}.") from exc
        except PlaywrightError as exc:
            raise RuntimeError(f"Could not render Vietstock board for {exchange_key!r}: {exc}") from exc
        finally:
            browser.close()

    return pd.DataFrame(records_by_symbol.values())


def scrape_exchange_with_selenium(
    exchange: str,
    *,
    timeout: int = 30,
    wait_ms: int = 1200,
    scroll_step: int = 900,
    max_scrolls: int = 180,
    progress: bool = False,
) -> pd.DataFrame:
    """Render and scroll a board with Selenium Edge/Chromium."""
    try:
        from selenium import webdriver
        from selenium.common.exceptions import TimeoutException, WebDriverException
        from selenium.webdriver.common.by import By
        from selenium.webdriver.edge.options import Options
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.webdriver.support.ui import WebDriverWait
    except ImportError as exc:
        raise RuntimeError(
            "Selenium is required for the default Vietstock browser renderer. "
            "Install selenium, or pass --browser-engine playwright."
        ) from exc

    exchange_key = exchange.lower().strip()
    url = BASE_URL.format(exchange=exchange_key)
    records_by_symbol: dict[str, dict[str, str | None]] = {}

    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--window-size=1440,950")
    options.add_argument("--disable-gpu")

    driver = webdriver.Edge(options=options)
    try:
        driver.set_page_load_timeout(timeout)
        driver.get(url)
        WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, "table.table-price-board:not(.table-header-width) tbody tr")
            )
        )
        time.sleep(wait_ms / 1000)

        _merge_records(records_by_symbol, _extract_records(driver.page_source, exchange_key, url))
        if progress:
            print(
                f"  {exchange_key.upper()}: initial render collected "
                f"{len(records_by_symbol)} rows...",
                flush=True,
            )
        if len(records_by_symbol) > 30:
            return pd.DataFrame(records_by_symbol.values())

        stable_bottom_count = 0
        no_new_count = 0
        previous_scroll_top = -1
        previous_row_count = -1

        for scroll_index in range(max_scrolls):
            before_count = len(records_by_symbol)
            _merge_records(records_by_symbol, _extract_records(driver.page_source, exchange_key, url))
            no_new_count = no_new_count + 1 if len(records_by_symbol) == before_count else 0
            if progress and scroll_index % 20 == 0:
                print(
                    f"  {exchange_key.upper()}: scroll {scroll_index}, "
                    f"collected {len(records_by_symbol)} rows...",
                    flush=True,
                )

            state = driver.execute_script(
                """
                const step = arguments[0];
                const scrollingElement = document.scrollingElement || document.documentElement;
                const before = scrollingElement.scrollTop;
                window.scrollBy(0, step);
                return {
                    before,
                    after: scrollingElement.scrollTop,
                    clientHeight: scrollingElement.clientHeight,
                    scrollHeight: scrollingElement.scrollHeight,
                    rowCount: document.querySelectorAll('table.table-price-board:not(.table-header-width) tbody tr').length
                };
                """,
                scroll_step,
            )
            time.sleep(wait_ms / 1000)

            at_bottom = state["after"] + state["clientHeight"] >= state["scrollHeight"] - 4
            row_count_stable = state["rowCount"] == previous_row_count
            scroll_stable = state["after"] == previous_scroll_top
            if at_bottom and row_count_stable and scroll_stable:
                stable_bottom_count += 1
            else:
                stable_bottom_count = 0

            previous_scroll_top = state["after"]
            previous_row_count = state["rowCount"]

            if stable_bottom_count >= 2 or no_new_count >= 12:
                break

        _merge_records(records_by_symbol, _extract_records(driver.page_source, exchange_key, url))
    except TimeoutException as exc:
        raise RuntimeError(f"Timed out while loading Vietstock board for {exchange_key!r}.") from exc
    except WebDriverException as exc:
        raise RuntimeError(f"Could not render Vietstock board for {exchange_key!r}: {exc}") from exc
    finally:
        driver.quit()

    return pd.DataFrame(records_by_symbol.values())


def _merge_records(
    records_by_symbol: dict[str, dict[str, str | None]],
    records: list[dict[str, str | None]],
) -> None:
    for record in records:
        symbol = record.get("symbol")
        if symbol:
            records_by_symbol[symbol] = record


def _parse_decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    text = str(value).strip().replace("%", "").replace(" ", "")
    if not text:
        return None
    text = text.replace(",", "")
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def _parse_bigint(value: object) -> int | None:
    if value is None:
        return None
    text = str(value).strip().replace(" ", "")
    if not text:
        return None
    text = re.sub(r"[^0-9-]", "", text)
    if not text or text == "-":
        return None
    return int(text)


def _company_name(row: pd.Series) -> str:
    value = row.get("company_name")
    if pd.isna(value) or not str(value).strip():
        return str(row.get("symbol") or "").strip().upper()
    return str(value).strip()


def _metric_payload(row: pd.Series, *, stock_id: str, snapshot_at: datetime, session_note: str, is_eod: bool) -> dict:
    return {
        "stock_id": stock_id,
        "trading_date": snapshot_at.date(),
        "snapshot_timestamp": snapshot_at,
        "is_eod": is_eod,
        "session_note": session_note,
        "reference_price": _parse_decimal(row.get("reference_price")),
        "ceiling_price": _parse_decimal(row.get("ceiling_price")),
        "floor_price": _parse_decimal(row.get("floor_price")),
        "bid_price_3": _parse_decimal(row.get("bid_price_3")),
        "bid_volume_3": _parse_bigint(row.get("bid_volume_3")),
        "bid_price_2": _parse_decimal(row.get("bid_price_2")),
        "bid_volume_2": _parse_bigint(row.get("bid_volume_2")),
        "bid_price_1": _parse_decimal(row.get("bid_price_1")),
        "bid_volume_1": _parse_bigint(row.get("bid_volume_1")),
        "matched_price": _parse_decimal(row.get("matched_price")),
        "matched_volume": _parse_bigint(row.get("matched_volume")),
        "change": _parse_decimal(row.get("change")),
        "change_percent": _parse_decimal(row.get("change_percent")),
        "ask_price_1": _parse_decimal(row.get("ask_price_1")),
        "ask_volume_1": _parse_bigint(row.get("ask_volume_1")),
        "ask_price_2": _parse_decimal(row.get("ask_price_2")),
        "ask_volume_2": _parse_bigint(row.get("ask_volume_2")),
        "ask_price_3": _parse_decimal(row.get("ask_price_3")),
        "ask_volume_3": _parse_bigint(row.get("ask_volume_3")),
        "total_volume": _parse_bigint(row.get("total_volume")),
        "total_value": _parse_decimal(row.get("total_value")),
        "high_price": _parse_decimal(row.get("high_price")),
        "low_price": _parse_decimal(row.get("low_price")),
        "average_price": _parse_decimal(row.get("average_price")),
        "foreign_buy_volume": _parse_bigint(row.get("foreign_buy_volume")),
        "foreign_sell_volume": _parse_bigint(row.get("foreign_sell_volume")),
    }


def _resolve_exchanges(raw: str) -> list[str]:
    normalized = raw.lower().strip()
    if normalized == "standard":
        return list(STANDARD_FLOW_EXCHANGES)
    if normalized == "all":
        return list(EXCHANGES)
    exchanges = [item.strip().lower() for item in raw.split(",") if item.strip()]
    unknown = [item for item in exchanges if item not in EXCHANGES]
    if unknown:
        raise ValueError(f"Unknown exchange(s): {unknown}. Expected: {', '.join(EXCHANGES)}")
    return exchanges


def _default_session_note(now: datetime, is_eod: bool) -> str:
    if is_eod:
        return "EOD"
    return "MORNING" if now.hour < 13 else "AFTERNOON"


def persist_to_postgres(
    frames: dict[str, pd.DataFrame],
    *,
    session_note: str | None = None,
    is_eod: bool = False,
    triggered_by: str = "manual",
    crawler_version: str | None = None,
) -> None:
    from src.scraper.config import get_settings
    from src.scraper.storage.repository import MetadataRepository

    settings = get_settings()
    snapshot_at = datetime.now().astimezone()
    effective_session_note = session_note or _default_session_note(snapshot_at, is_eod)
    version = crawler_version or settings.crawler_version
    total_rows = sum(len(frame) for frame in frames.values())

    with MetadataRepository(settings) as repo:
        source_id = repo.ensure_source(
            "vietstock",
            base_url="https://banggia.vietstock.vn",
            language="vi",
        )
        job_id = repo.create_crawl_job(
            crawler_version=version,
            job_name=f"Vietstock stock metrics {effective_session_note}",
            job_type="STOCK_METRICS",
            source_id=source_id,
            note=f"triggered_by={triggered_by}; exchanges={list(frames)}",
        )

        success_requests = failed_requests = items_extracted = 0
        final_status = "SUCCESS"
        try:
            for exchange, frame in frames.items():
                started = time.monotonic()
                target_url = BASE_URL.format(exchange=exchange)
                try:
                    if exchange in METRIC_EXCHANGES:
                        exchange_name = exchange.upper()
                        for _, row in frame.iterrows():
                            ticker = str(row.get("symbol") or "").strip().upper()
                            if not ticker:
                                continue
                            stock_id = repo.ensure_stock(
                                ticker=ticker,
                                company_name=_company_name(row),
                                exchange=exchange_name,
                            )
                            repo.upsert_stock_metric(
                                _metric_payload(
                                    row,
                                    stock_id=stock_id,
                                    snapshot_at=snapshot_at,
                                    session_note=effective_session_note,
                                    is_eod=is_eod,
                                )
                            )
                            items_extracted += 1
                    elif exchange in INDEX_EXCHANGES:
                        index_name = INDEX_EXCHANGES[exchange]
                        exchange_name = "HOSE" if index_name == "VN30" else "HNX"
                        for _, row in frame.iterrows():
                            ticker = str(row.get("symbol") or "").strip().upper()
                            if not ticker:
                                continue
                            stock_id = repo.ensure_stock(
                                ticker=ticker,
                                company_name=_company_name(row),
                                exchange=exchange_name,
                            )
                            repo.ensure_index_membership(
                                stock_id=stock_id,
                                index_name=index_name,
                                joined_at=snapshot_at.date(),
                            )
                            items_extracted += 1
                    success_requests += 1
                    repo.write_crawl_log(
                        job_id=job_id,
                        target_url=target_url,
                        response_time_ms=int((time.monotonic() - started) * 1000),
                        is_success=True,
                    )
                except Exception as exc:
                    failed_requests += 1
                    final_status = "FAILED"
                    repo.write_crawl_log(
                        job_id=job_id,
                        target_url=target_url,
                        response_time_ms=int((time.monotonic() - started) * 1000),
                        is_success=False,
                        error_category="PARSE_ERROR",
                        error_message=str(exc),
                    )
                    raise
        finally:
            repo.finish_crawl_job(
                job_id,
                status=final_status,
                total_requests=len(frames),
                success_requests=success_requests,
                failed_requests=failed_requests,
                items_extracted=items_extracted,
                note=f"triggered_by={triggered_by}; session={effective_session_note}; rows={total_rows}",
            )


def scrape_exchanges(
    exchanges: Iterable[str],
    *,
    timeout: int = 30,
    render: str = "auto",
    browser_engine: str = "auto",
    wait_ms: int = 1200,
    scroll_step: int = 900,
    max_scrolls: int = 180,
    progress: bool = False,
) -> dict[str, pd.DataFrame]:
    exchange_list = [exchange.lower().strip() for exchange in exchanges]
    frames: dict[str, pd.DataFrame] = {}
    for exchange in exchange_list:
        if progress:
            mode = "browser" if scrape_exchange_should_use_browser(exchange, render) else "static"
            print(f"Scraping {exchange.upper()} with {mode} renderer...", flush=True)
        frames[exchange] = scrape_exchange(
            exchange,
            timeout=timeout,
            use_browser=_should_use_browser(exchange, render),
            browser_engine=browser_engine,
            wait_ms=wait_ms,
            scroll_step=scroll_step,
            max_scrolls=max_scrolls,
            progress=progress,
        )
        if progress:
            print(f"Collected {len(frames[exchange])} rows for {exchange.upper()}.", flush=True)
    return frames


def scrape_to_excel(
    exchanges: Iterable[str] = EXCHANGES,
    *,
    output_dir: Path | str = DEFAULT_OUTPUT_DIR,
    filename: str | None = None,
    timeout: int = 30,
    render: str = "auto",
    browser_engine: str = "auto",
    wait_ms: int = 1200,
    scroll_step: int = 900,
    max_scrolls: int = 180,
    progress: bool = False,
) -> Path:
    """Scrape selected exchanges and write one Excel workbook with one sheet each."""
    frames = scrape_exchanges(
        exchanges,
        timeout=timeout,
        render=render,
        browser_engine=browser_engine,
        wait_ms=wait_ms,
        scroll_step=scroll_step,
        max_scrolls=max_scrolls,
        progress=progress,
    )
    return write_frames_to_excel(frames, output_dir=output_dir, filename=filename)


def write_frames_to_excel(
    frames: dict[str, pd.DataFrame],
    *,
    output_dir: Path | str = DEFAULT_OUTPUT_DIR,
    filename: str | None = None,
) -> Path:
    """Write already-scraped exchange frames to one Excel workbook."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    if filename is None:
        timestamp = datetime.now().strftime("%Y%m%dT%H%M%S")
        filename = f"vietstock_price_board_{timestamp}.xlsx"
    workbook_path = output_path / filename

    summary = pd.DataFrame(
        [
            {
                "exchange": exchange,
                "rows": len(frame),
                "source_url": BASE_URL.format(exchange=exchange),
            }
            for exchange, frame in frames.items()
        ]
    )

    with pd.ExcelWriter(workbook_path, engine=_excel_writer_engine()) as writer:
        summary.to_excel(writer, sheet_name="summary", index=False)
        for exchange, frame in frames.items():
            frame.to_excel(writer, sheet_name=exchange.upper(), index=False)

    return workbook_path


def _should_use_browser(exchange: str, render: str) -> bool | None:
    render_key = render.lower().strip()
    if render_key == "auto":
        return None
    if render_key == "browser":
        return True
    if render_key == "static":
        return False
    raise ValueError("render must be one of: auto, browser, static")


def scrape_exchange_should_use_browser(exchange: str, render: str) -> bool:
    decision = _should_use_browser(exchange, render)
    return exchange.lower().strip() in SCROLL_EXCHANGES if decision is None else decision


def _excel_writer_engine() -> str:
    """Pick an installed XLSX writer engine without forcing a local DB stack."""
    if importlib.util.find_spec("xlsxwriter") is not None:
        return "xlsxwriter"
    if importlib.util.find_spec("openpyxl") is not None:
        return "openpyxl"
    raise RuntimeError("Install xlsxwriter or openpyxl to export Vietstock data to Excel.")


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="src.scraper.vietstock.vietstock_scraper",
        description="Scrape Vietstock price-board HTML snapshots to a local Excel workbook.",
    )
    parser.add_argument(
        "--exchange",
        default="standard",
        help="Exchange to scrape: standard, all, or comma-separated values from hose,vn30,hnx,hnx30,upcom.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Directory for the Excel workbook. Defaults to this package's data folder.",
    )
    parser.add_argument("--filename", default=None, help="Optional workbook filename.")
    parser.add_argument("--persist-postgres", action="store_true", help="Persist standard flow data to PostgreSQL core/scraping schemas.")
    parser.add_argument("--skip-excel", action="store_true", help="Skip Excel export when persisting to PostgreSQL.")
    parser.add_argument("--session-note", choices=["MORNING", "AFTERNOON", "EOD"], default=None)
    parser.add_argument("--is-eod", action="store_true", help="Mark stock metric snapshots as end-of-day.")
    parser.add_argument("--triggered-by", default="manual", choices=["manual", "cron", "prefect"])
    parser.add_argument("--timeout", type=int, default=30, help="HTTP timeout in seconds.")
    parser.add_argument(
        "--render",
        choices=["auto", "browser", "static"],
        default="auto",
        help="auto uses browser scrolling for hose/hnx/upcom and static HTML for vn30/hnx30.",
    )
    parser.add_argument(
        "--browser-engine",
        choices=["auto", "selenium", "playwright"],
        default="auto",
        help="Browser renderer for scrolling boards. auto prefers Selenium Edge when available.",
    )
    parser.add_argument(
        "--wait-ms",
        type=int,
        default=1200,
        help="Milliseconds to wait after page load and between scrolls when rendering with a browser.",
    )
    parser.add_argument(
        "--scroll-step",
        type=int,
        default=900,
        help="Pixels to scroll per step when rendering with a browser.",
    )
    parser.add_argument(
        "--max-scrolls",
        type=int,
        default=180,
        help="Safety cap for browser scroll steps per exchange.",
    )
    return parser


def main() -> int:
    args = _build_arg_parser().parse_args()
    exchanges = _resolve_exchanges(args.exchange)
    frames = scrape_exchanges(
        exchanges,
        timeout=args.timeout,
        render=args.render,
        browser_engine=args.browser_engine,
        wait_ms=args.wait_ms,
        scroll_step=args.scroll_step,
        max_scrolls=args.max_scrolls,
        progress=True,
    )
    if args.persist_postgres:
        persist_to_postgres(
            frames,
            session_note=args.session_note,
            is_eod=args.is_eod,
            triggered_by=args.triggered_by,
        )
        print("Persisted Vietstock data to PostgreSQL.")
    if args.skip_excel:
        return 0
    workbook = write_frames_to_excel(
        frames,
        output_dir=args.output_dir,
        filename=args.filename,
    )
    print(f"Wrote Vietstock workbook: {workbook}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())