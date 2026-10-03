"""Verified website structures, independently versioned raw parsers and adapters."""

import re
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

from src.news_pipeline.normalize import canonical_url, normalize_text


class ParseError(ValueError):
    pass


@dataclass(frozen=True)
class Source:
    key: str
    host: str
    listing: str
    article_pattern: str
    title_selector: str
    body_selector: str
    payload_fields: tuple[str, str, str, str, str]
    time_selector: str = 'meta[property="article:published_time"]'
    parser_version: str = "v1"

    @property
    def raw_schema_version(self):
        return f"{self.key}-raw-v1"

    def url(self, value, *, article=False):
        url = canonical_url(urljoin("https://" + self.host, value), self.host)
        parts = urlsplit(url)
        # Query-bearing article links are excluded, not silently rewritten; the
        # canonical contract preserves queries. Never follow cross-host links.
        if parts.query or (article and not re.search(self.article_pattern, parts.path)):
            raise ValueError("not_a_supported_source_url")
        return url

    def discover(self, html):
        soup = BeautifulSoup(html, "html.parser")
        urls = []
        for node in soup.select("a[href]"):
            try:
                url = self.url(node["href"], article=True)
            except ValueError:
                continue
            if url not in urls:
                urls.append(url)
        return urls

    def parse(self, html):
        soup = BeautifulSoup(html, "html.parser")
        title = soup.select_one(self.title_selector)
        body = soup.select_one(self.body_selector)
        if not title or not body or not normalize_text(str(body), body=True):
            raise ParseError("missing_or_empty_article_nodes")
        if not title.get_text(strip=True):
            raise ParseError("empty_title")
        # Only article body, never the entire page. Keep raw HTTP HTML separately.
        for node in body.select(
            "script,style,iframe,nav,.detail__related,.link-content-footer"
        ):
            node.decompose()
        title_key, summary_key, body_key, time_key, author_key = self.payload_fields
        description = soup.select_one('meta[name="description"]')
        time_node = soup.select_one(self.time_selector)
        author = soup.select_one('meta[property="article:author"]')
        payload = {
            title_key: title.get_text(" ", strip=True),
            summary_key: description.get("content", "") if description else "",
            body_key: str(body),
            time_key: time_node.get("content", "") if time_node else "",
            author_key: author.get("content") if author else None,
        }
        payload["json_ld"] = [
            node.get_text()
            for node in soup.select('script[type="application/ld+json"]')
        ]
        payload["image_urls"] = [
            node.get("src") or node.get("data-src")
            for node in body.select("img[src],img[data-src]")
        ]
        payload["category"] = self._meta(soup, "article:section") or self._meta(
            soup, "articleSection"
        )
        canonical = soup.select_one('link[rel="canonical"]')
        payload["observed_canonical_url"] = canonical.get("href") if canonical else None
        if self.key == "baomoi":
            original = soup.select_one(".article-source a")
            publisher = soup.select_one(".content-meta a.bm-card-source")
            payload["original_publisher"] = (
                publisher.get("title") if publisher else None
            )
            # The observed DOM exposes the real URL as text, while href is an
            # aggregator redirect. Preserve only explicitly visible URL text.
            text = original.get_text(" ", strip=True) if original else ""
            match = re.search(r"https?://[^\s]+", text)
            payload["original_url"] = match.group(0) if match else None
        return payload

    @staticmethod
    def _meta(soup, field):
        node = soup.select_one(f'meta[property="{field}"],meta[itemprop="{field}"]')
        return node.get("content") if node else None


SOURCES = {
    "cafef": Source(
        "cafef",
        "cafef.vn",
        "https://cafef.vn/vi-mo-dau-tu.chn",
        r"-\d{6,}\.chn$",
        "h1.title",
        "div.afcbc-body",
        (
            "h1_title",
            "meta_description",
            "detail_content_html",
            "article_published_time",
            "article_author",
        ),
    ),
    "vnexpress": Source(
        "vnexpress",
        "vnexpress.net",
        "https://vnexpress.net/kinh-doanh",
        r"-\d{6,}\.html$",
        "h1.title-detail",
        "article.fck_detail",
        ("title_detail", "description", "fck_detail_html", "pubdate", "journalist"),
        'meta[name="pubdate"]',
    ),
    "tuoitre": Source(
        "tuoitre",
        "tuoitre.vn",
        "https://tuoitre.vn/kinh-doanh.htm",
        r"-\d{6,}\.htm$",
        "h1.detail-title",
        "div.afcbc-body",
        ("detail_title", "sapo", "article_body_html", "published_time", "author"),
    ),
    "thanhnien": Source(
        "thanhnien",
        "thanhnien.vn",
        "https://thanhnien.vn/kinh-te.htm",
        r"-\d{6,}\.htm$",
        "h1.detail-title",
        "div.afcbc-body",
        ("headline", "standfirst", "body_html", "publication_time", "byline"),
    ),
    "baomoi": Source(
        "baomoi",
        "baomoi.com",
        "https://baomoi.com/kinh-te.epi",
        r"-c\d+\.epi$",
        "article.content-main h1",
        "div.content-body",
        ("headline", "sapo", "content_html", "aggregation_time", "author"),
    ),
}
