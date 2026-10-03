"""Ordinary bounded HTTP with robots, per-source pacing and persistent cooldown."""

import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


class FetchError(RuntimeError):
    def __init__(self, reason, status=None, retry_after=0, retryable=False):
        self.reason = reason
        self.status = status
        self.retry_after = retry_after
        self.retryable = retryable
        super().__init__(reason)


@dataclass
class Response:
    url: str
    body: bytes
    status: int
    headers: dict


def retry_after_seconds(value, now=None):
    if not value:
        return 0
    try:
        return max(0, int(value))
    except ValueError:
        try:
            return max(
                0,
                int(
                    (
                        parsedate_to_datetime(value)
                        - (now or datetime.now(timezone.utc))
                    ).total_seconds()
                ),
            )
        except (ValueError, TypeError):
            return 0


class RobotsPolicy:
    """Support wildcard/end-anchor rules and longest-path allow precedence."""

    def __init__(self, text, user_agent):
        groups = []
        agents, rules, delay = [], [], 0.0
        has_rules = False
        for line in text.lstrip("\ufeff").splitlines():
            line = line.split("#", 1)[0].strip()
            if ":" not in line:
                continue
            key, value = [s.strip() for s in line.split(":", 1)]
            key = key.lower()
            if key == "user-agent":
                if has_rules:
                    groups.append((agents, rules, delay))
                    agents, rules, delay = [], [], 0.0
                    has_rules = False
                agents.append(value.lower())
            elif agents:
                if key in ("allow", "disallow"):
                    has_rules = True
                    if value:
                        rules.append((value, key == "allow"))
                elif key == "crawl-delay":
                    has_rules = True
                    try:
                        delay = max(delay, float(value))
                    except ValueError:
                        pass
        groups.append((agents, rules, delay))
        ua = user_agent.lower()
        specificity = max(
            [len(a) for g in groups for a in g[0] if a != "*" and a in ua] or [0]
        )
        selected = [
            g
            for g in groups
            if any(
                (a == "*" and not specificity)
                or (a != "*" and a in ua and len(a) == specificity)
                for a in g[0]
            )
        ]
        self.rules = [r for g in selected for r in g[1]]
        self.delay = max([g[2] for g in selected] or [0.0])

    def allowed(self, url):
        parsed = urlsplit(url)
        path = parsed.path + ("?" + parsed.query if parsed.query else "")
        matches = []
        for rule, allow in self.rules:
            regex = "^" + re.escape(rule).replace(r"\*", ".*")
            if rule.endswith("$"):
                regex = regex[:-2] + "$"
            if re.search(regex, path):
                matches.append((len(rule.replace("*", "").rstrip("$")), allow))
        return max(matches, default=(0, True))[1]


class SameHostRedirect(HTTPRedirectHandler):
    def __init__(self, source, before_redirect=None, allowed=None):
        self.source = source
        self.before_redirect = before_redirect
        self.allowed = allowed

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        self.source.url(newurl)  # Reject before fetching outside the source host.
        if self.allowed and not self.allowed(newurl):
            raise FetchError("robots_disallowed_redirect", status=403)
        if self.before_redirect:
            self.before_redirect()
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class HttpClient:
    def __init__(
        self,
        source,
        *,
        user_agent,
        interval=3.0,
        timeout=20,
        max_bytes=5_000_000,
        retries=2,
    ):
        if interval < 1 or not user_agent or timeout <= 0 or retries not in range(4):
            raise ValueError("invalid_http_policy")
        self.source = source
        self.user_agent = user_agent
        self.interval = interval
        self.timeout = timeout
        self.max_bytes = max_bytes
        self.retries = retries
        self.last_request = 0.0
        self.request_count = 0
        self.retry_count = 0
        self.policy = None
        self.opener = build_opener(
            SameHostRedirect(
                source,
                self._pace,
                lambda url: self.policy is None or self.policy.allowed(url),
            )
        )

    def _pace(self):
        time.sleep(max(0, self.interval - (time.monotonic() - self.last_request)))
        self.last_request = time.monotonic()
        self.request_count += 1

    def _request(self, url):
        self._pace()
        try:
            with self.opener.open(
                Request(
                    url,
                    headers={
                        "User-Agent": self.user_agent,
                        "Accept": "text/html,text/plain;q=0.9",
                    },
                ),
                timeout=self.timeout,
            ) as r:
                body = r.read(self.max_bytes + 1)
                if len(body) > self.max_bytes:
                    raise FetchError("response_too_large")
                return Response(
                    r.url,
                    body,
                    r.status,
                    {
                        k.lower(): v
                        for k, v in r.headers.items()
                        if k.lower()
                        in ("content-type", "etag", "last-modified", "retry-after")
                    },
                )
        except HTTPError as e:
            delay = retry_after_seconds(e.headers.get("Retry-After"))
            raise FetchError(
                "http_" + str(e.code),
                e.code,
                delay,
                e.code in (408, 429, 500, 502, 503, 504),
            ) from e
        except (URLError, TimeoutError, OSError) as e:
            raise FetchError("network_error", retryable=True) from e

    def check_robots(self):
        try:
            response = self._request("https://" + self.source.host + "/robots.txt")
            self.policy = RobotsPolicy(
                response.body.decode("utf-8-sig"), self.user_agent
            )
        except FetchError as e:
            if e.status == 404:
                self.policy = RobotsPolicy("", self.user_agent)
            else:
                raise FetchError(
                    "robots_unavailable", e.status, e.retry_after, e.retryable
                ) from e
        self.interval = max(self.interval, self.policy.delay)

    def fetch(self, url):
        self.source.url(url)
        if self.policy is None:
            self.check_robots()
        if not self.policy.allowed(url):
            raise FetchError("robots_disallowed", status=403)
        for attempt in range(self.retries + 1):
            try:
                response = self._request(url)
                text = response.body[:100000].lower()
                if any(
                    v in text
                    for v in (
                        b"<title>just a moment",
                        b"<title>access denied",
                        b"cf-chl-",
                    )
                ):
                    raise FetchError("challenge_page", status=403)
                if "html" not in response.headers.get("content-type", "").lower():
                    raise FetchError("unexpected_content_type")
                return response
            except FetchError as e:
                # Retry-After is persisted by the application, not ignored or
                # slept through in an unbounded Airflow task.
                if not e.retryable or e.retry_after or attempt == self.retries:
                    raise
                self.retry_count += 1
                time.sleep(min(2**attempt, 8))
        raise AssertionError("unreachable")
