"""
Generate stock-specific scraping keywords for VN30 and HNX30 with Gemini.

The script reads the VN30 workbook already used by the scraper seed flow and
loads HNX30 tickers from Vietstock by default. It calls Gemini in small batches,
respecting the configured RPM/TPM limits, and writes a JSON file that can be
fed back into ``scripts/seed_scraper_db.py --keywords-json``.
"""
from __future__ import annotations

import argparse
import importlib
import json
import os
import re
import time
from collections import deque
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Sequence

import pandas as pd
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

DEFAULT_MODEL = "gemini-3.5-flash"
DEFAULT_RPM = 5
DEFAULT_TPM = 250_000
DEFAULT_BATCH_SIZE = 10
DEFAULT_VN30_XLSX = Path("data/raw/vn30.xlsx")
DEFAULT_OUTPUT = Path("data/raw/generated_keywords_vn30_hnx30.json")
HNX30_URL = "https://banggia.vietstock.vn/bang-gia/hnx30"

REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; FinancialNewsBot/2.0)",
    "Accept-Language": "vi,en;q=0.9",
}


@dataclass(frozen=True)
class TickerInput:
    ticker: str
    company_name: str | None
    index_name: str


@dataclass(frozen=True)
class KeywordItem:
    ticker: str
    company_name: str | None
    index_name: str
    keywords: list[str]


class RateLimiter:
    """Simple rolling-window RPM/TPM limiter for Gemini calls."""

    def __init__(self, *, rpm: int, tpm: int) -> None:
        self._rpm = rpm
        self._tpm = tpm
        self._request_times: deque[float] = deque()
        self._token_events: deque[tuple[float, int]] = deque()

    def acquire(self, estimated_tokens: int) -> None:
        while True:
            now = time.monotonic()
            self._trim(now)
            used_tokens = sum(tokens for _, tokens in self._token_events)

            wait_for_request = 0.0
            if len(self._request_times) >= self._rpm:
                wait_for_request = 60.0 - (now - self._request_times[0])

            wait_for_tokens = 0.0
            if used_tokens + estimated_tokens > self._tpm and self._token_events:
                wait_for_tokens = 60.0 - (now - self._token_events[0][0])

            wait_seconds = max(wait_for_request, wait_for_tokens, 0.0)
            if wait_seconds <= 0:
                self._request_times.append(now)
                self._token_events.append((now, estimated_tokens))
                return
            time.sleep(wait_seconds + 0.2)

    def _trim(self, now: float) -> None:
        while self._request_times and now - self._request_times[0] >= 60:
            self._request_times.popleft()
        while self._token_events and now - self._token_events[0][0] >= 60:
            self._token_events.popleft()


def _estimate_tokens(text: str) -> int:
    return max(1, (len(text) + 3) // 4)


def _chunks(items: Sequence[TickerInput], size: int) -> Iterable[list[TickerInput]]:
    for start in range(0, len(items), size):
        yield list(items[start:start + size])


def _clean_keyword(value: object) -> str | None:
    text = str(value).strip()
    if not text:
        return None
    text = re.sub(r"\s+", " ", text)
    return text[:120]


def _fallback_keywords(item: TickerInput) -> list[str]:
    company = item.company_name or item.ticker
    candidates = [
        item.ticker,
        company,
        f"cổ phiếu {item.ticker}",
        f"{item.ticker} chứng khoán",
        f"{company} cổ phiếu",
    ]
    output: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        keyword = _clean_keyword(candidate)
        if keyword and keyword.lower() not in seen:
            seen.add(keyword.lower())
            output.append(keyword)
    return output[:5]


def _normalize_keywords(raw: object, item: TickerInput) -> list[str]:
    values = raw if isinstance(raw, list) else []
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        keyword = _clean_keyword(value)
        if keyword and keyword.lower() not in seen:
            seen.add(keyword.lower())
            output.append(keyword)
        if len(output) == 5:
            break

    for keyword in _fallback_keywords(item):
        if len(output) == 5:
            break
        if keyword.lower() not in seen:
            seen.add(keyword.lower())
            output.append(keyword)
    return output


def load_vn30_tickers(path: Path) -> list[TickerInput]:
    df = pd.read_excel(path, header=0)
    ticker_col = _first_existing_column(df, ["ticket_symbol", "ticker", "symbol"])
    company_col = _first_existing_column(
        df,
        ["company_name_vi", "company_name", "company", "name"],
        required=False,
    )
    tickers: list[TickerInput] = []
    for _, row in df.iterrows():
        ticker = str(row[ticker_col]).strip().upper()
        if not ticker or ticker == "NAN":
            continue
        company_name = None
        if company_col:
            raw_company = row[company_col]
            if pd.notna(raw_company):
                company_name = str(raw_company).strip() or None
        tickers.append(TickerInput(ticker=ticker, company_name=company_name, index_name="VN30"))
    return tickers


def load_hnx30_tickers_from_vietstock(timeout: int = 30) -> list[TickerInput]:
    response = requests.get(HNX30_URL, headers=REQUEST_HEADERS, timeout=timeout)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    rows = soup.select("table.table-price-board:not(.table-header-width) tbody tr[data-symbol]")
    tickers: list[TickerInput] = []
    for row in rows:
        ticker = str(row.get("data-symbol", "")).strip().upper()
        if not ticker:
            continue
        company_node = row.select_one(".tooltip-stock-name")
        company_name = company_node.get_text(" ", strip=True) if company_node else None
        tickers.append(TickerInput(ticker=ticker, company_name=company_name, index_name="HNX30"))
    if not tickers:
        raise RuntimeError("Could not load HNX30 tickers from Vietstock.")
    return tickers


def load_tickers_from_text(raw: str, *, index_name: str) -> list[TickerInput]:
    return [
        TickerInput(ticker=ticker.strip().upper(), company_name=None, index_name=index_name)
        for ticker in raw.split(",")
        if ticker.strip()
    ]


def _first_existing_column(df: pd.DataFrame, candidates: list[str], *, required: bool = True) -> str | None:
    lowered = {str(column).lower(): column for column in df.columns}
    for candidate in candidates:
        if candidate.lower() in lowered:
            return lowered[candidate.lower()]
    if required:
        raise ValueError(f"Missing required column. Expected one of: {candidates}")
    return None


def _dedupe_tickers(items: Iterable[TickerInput]) -> list[TickerInput]:
    result: list[TickerInput] = []
    seen: set[tuple[str, str]] = set()
    for item in items:
        key = (item.index_name.upper(), item.ticker.upper())
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


def filter_tickers_missing_keywords(tickers: list[TickerInput]) -> list[TickerInput]:
    from src.scraper.config import get_settings
    from src.scraper.storage.repository import MetadataRepository

    settings = get_settings()
    with MetadataRepository(settings) as repo:
        existing = repo.active_keyword_tickers()
    missing = [item for item in tickers if item.ticker.upper() not in existing]
    print(
        f"Keyword generation scope: {len(missing)}/{len(tickers)} tickers missing active keywords.",
        flush=True,
    )
    return missing


def load_index_tickers_from_postgres(index_names: Sequence[str] = ("VN30", "HNX30")) -> list[TickerInput]:
    from src.scraper.config import get_settings
    from src.scraper.storage.repository import MetadataRepository

    settings = get_settings()
    with MetadataRepository(settings) as repo:
        rows = repo.active_index_tickers(index_names)
    return [
        TickerInput(
            ticker=str(row["ticker"]).upper(),
            company_name=row.get("company_name"),
            index_name=str(row["index_name"]).upper(),
        )
        for row in rows
        if row.get("ticker") and row.get("index_name")
    ]


def persist_keyword_items(items: Sequence[KeywordItem]) -> int:
    from src.scraper.config import get_settings
    from src.scraper.storage.repository import MetadataRepository

    settings = get_settings()
    touched = 0
    with MetadataRepository(settings) as repo:
        for item in items:
            exchange = "HOSE" if item.index_name.upper() == "VN30" else "HNX"
            touched += repo.ensure_stock_keywords(
                ticker=item.ticker,
                company_name=item.company_name,
                exchange=exchange,
                index_name=item.index_name,
                keywords=item.keywords,
            )
    return touched


def _build_prompt(batch: list[TickerInput]) -> str:
    payload = [asdict(item) for item in batch]
    return (
        "Generate exactly 5 relevant Vietnamese search keywords for each stock ticker. "
        "These keywords will be used to scrape financial news, so include the ticker, "
        "company name/common name, and investor/news search phrases. Avoid duplicates, "
        "avoid overly generic keywords that are not stock-specific, and keep each keyword short.\n\n"
        "Return strict JSON only with this schema:\n"
        '{"items":[{"ticker":"ACB","keywords":["keyword 1","keyword 2","keyword 3","keyword 4","keyword 5"]}]}\n\n'
        f"Input tickers:\n{json.dumps(payload, ensure_ascii=False)}"
    )


def _parse_json_response(text: str) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?", "", cleaned, flags=re.IGNORECASE).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))


def _call_gemini(client: object, model: str, batch: list[TickerInput]) -> dict[str, list[str]]:
    genai_types = importlib.import_module("google.genai.types")

    prompt = _build_prompt(batch)
    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=genai_types.GenerateContentConfig(
            system_instruction=(
                "You are a Vietnamese financial-market keyword specialist. "
                "Return only valid JSON."
            ),
            temperature=0.2,
            max_output_tokens=2048,
            response_mime_type="application/json",
        ),
    )
    text = getattr(response, "text", None) or ""
    data = _parse_json_response(text)
    output: dict[str, list[str]] = {}
    for row in data.get("items", []):
        ticker = str(row.get("ticker", "")).strip().upper()
        if ticker:
            output[ticker] = row.get("keywords", [])
    return output


def generate_keywords(
    tickers: list[TickerInput],
    *,
    api_key: str,
    model: str = DEFAULT_MODEL,
    rpm: int = DEFAULT_RPM,
    tpm: int = DEFAULT_TPM,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> list[KeywordItem]:
    genai = importlib.import_module("google.genai")

    client = genai.Client(api_key=api_key)
    limiter = RateLimiter(rpm=rpm, tpm=tpm)
    results: list[KeywordItem] = []

    for batch in _chunks(tickers, batch_size):
        prompt = _build_prompt(batch)
        estimated_tokens = _estimate_tokens(prompt) + 2048
        limiter.acquire(estimated_tokens)
        generated = _call_gemini(client, model, batch)
        for item in batch:
            keywords = _normalize_keywords(generated.get(item.ticker), item)
            results.append(
                KeywordItem(
                    ticker=item.ticker,
                    company_name=item.company_name,
                    index_name=item.index_name,
                    keywords=keywords,
                )
            )
        print(f"Generated keywords for {len(results)}/{len(tickers)} tickers.", flush=True)

    return results


def write_output(items: list[KeywordItem], output_path: Path, *, model: str) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": model,
        "items": [asdict(item) for item in items],
    }
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="src.scraper.keyword_generation.gemini_keyword_generator",
        description="Generate VN30/HNX30 scraping keywords with Gemini.",
    )
    parser.add_argument("--vn30-xlsx", default=str(DEFAULT_VN30_XLSX))
    parser.add_argument(
        "--hnx30-tickers",
        default=None,
        help="Optional comma-separated HNX30 tickers. If omitted, loads HNX30 from Vietstock.",
    )
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--model", default=os.getenv("GEMINI_KEYWORD_MODEL", DEFAULT_MODEL))
    parser.add_argument("--rpm", type=int, default=DEFAULT_RPM)
    parser.add_argument("--tpm", type=int, default=DEFAULT_TPM)
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--timeout", type=int, default=30, help="HTTP timeout for loading HNX30 tickers.")
    parser.add_argument(
        "--include-existing",
        action="store_true",
        help="Generate keywords for all loaded tickers instead of only tickers missing active keywords.",
    )
    return parser


def main() -> int:
    load_dotenv(override=False)
    args = _build_arg_parser().parse_args()

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is empty. Set it in your environment or .env file.")

    project_root = Path(__file__).resolve().parents[3]
    vn30_path = Path(args.vn30_xlsx)
    if not vn30_path.is_absolute():
        vn30_path = (project_root / vn30_path).resolve()

    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = (project_root / output_path).resolve()

    tickers = load_vn30_tickers(vn30_path)
    if args.hnx30_tickers:
        tickers.extend(load_tickers_from_text(args.hnx30_tickers, index_name="HNX30"))
    else:
        tickers.extend(load_hnx30_tickers_from_vietstock(timeout=args.timeout))
    tickers = _dedupe_tickers(tickers)
    if not args.include_existing:
        tickers = filter_tickers_missing_keywords(tickers)
    if not tickers:
        write_output([], output_path, model=args.model)
        print(f"No missing tickers. Wrote empty generated keywords file to: {output_path}")
        return 0

    items = generate_keywords(
        tickers,
        api_key=api_key,
        model=args.model,
        rpm=args.rpm,
        tpm=args.tpm,
        batch_size=args.batch_size,
    )
    write_output(items, output_path, model=args.model)
    print(f"Wrote generated keywords to: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
