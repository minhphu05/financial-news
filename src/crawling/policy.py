"""Validated operational policy; no network access and no Airflow dependency."""

import math
import random
from datetime import datetime, timezone


class PolicySkip(ValueError):
    """A deliberate no-request outcome, rather than an HTTP/parser failure."""


DEFAULTS = {
    "live_enabled": False,
    "request_timeout_seconds": 20,
    "http_retries": 2,
    "max_response_bytes": 5_000_000,
    "publish_max_batches": 2,
    "publish_max_attempts": 5,
    "publish_retry_base_seconds": 60,
    "publish_retry_max_seconds": 3600,
    "heartbeat_max_age_seconds": 7200,
}


def effective_policy(source, config, *, enabled=True):
    """Preserve Phase08 keys, adding fail-closed live and bounded replay defaults."""
    policy = {**DEFAULTS, **config, "enabled": enabled}
    if type(enabled) is not bool or type(policy["live_enabled"]) is not bool:
        raise ValueError("crawler_enablement_must_be_boolean")
    if (
        policy.get("adapter") != source.key
        or policy.get("raw_schema_version") != source.raw_schema_version
        or policy.get("parser_version") != source.parser_version
    ):
        raise ValueError("crawler_config_version_mismatch")
    bounds = {
        "max_articles": (1, 20),
        "max_attempts": (1, 10),
        "recent_days": (1, 30),
        "http_retries": (0, 3),
        "max_response_bytes": (1024, 5_000_000),
        "publish_max_batches": (1, 20),
        "publish_max_attempts": (1, 20),
    }
    for name, (low, high) in bounds.items():
        value = policy[name]
        if type(value) is not int or not low <= value <= high:
            raise ValueError("invalid_crawler_policy_" + name)
    for name, low, high in (
        ("request_interval_seconds", 1, 300),
        ("request_timeout_seconds", 1, 120),
        ("recheck_hours", 1, 720),
        ("publish_retry_base_seconds", 1, 3600),
        ("publish_retry_max_seconds", 1, 86400),
        ("heartbeat_max_age_seconds", 60, 604800),
    ):
        value = policy[name]
        if (
            type(value) not in (int, float)
            or not math.isfinite(value)
            or not low <= value <= high
        ):
            raise ValueError("invalid_crawler_policy_" + name)
    if policy["publish_retry_max_seconds"] < policy["publish_retry_base_seconds"]:
        raise ValueError("publish_retry_max_must_cover_base")
    if (
        not isinstance(policy.get("user_agent"), str)
        or not policy["user_agent"].strip()
    ):
        raise ValueError("crawler_user_agent_required")
    urls = policy.get("discovery_urls")
    if not isinstance(urls, list) or not 1 <= len(urls) <= 3:
        raise ValueError("crawler_requires_one_to_three_listings")
    for url in urls:
        source.url(url)
    return policy


def gate(policy, *, fixture=False, allow_live=False):
    if not policy["enabled"]:
        return "source_disabled"
    if not fixture and not allow_live:
        return "live_opt_in_required"
    if not fixture and not policy["live_enabled"]:
        return "source_live_disabled"
    if not fixture and policy.get("live_until") is not None:
        try:
            deadline = datetime.fromisoformat(policy["live_until"])
            if deadline.tzinfo is None:
                return "source_live_deadline_invalid"
        except (ValueError, TypeError):
            return "source_live_deadline_invalid"
        if datetime.now(timezone.utc) >= deadline:
            return "source_live_expired"
    return None


def batch_limit(requested, policy):
    if requested is not None and (
        type(requested) is not int or not 1 <= requested <= 20
    ):
        raise ValueError("limit_must_be_between_1_and_20")
    return min(requested or policy["max_articles"], policy["max_articles"])


def retry_delay(attempt, policy):
    base = min(
        policy["publish_retry_max_seconds"],
        policy["publish_retry_base_seconds"] * 2 ** min(max(attempt - 1, 0), 20),
    )
    return min(
        policy["publish_retry_max_seconds"], base + random.uniform(0, base * 0.1)
    )


def failure_category(error):
    status = getattr(error, "status", None)
    if status in (401, 403, 429) or getattr(error, "retry_after", 0):
        return "BLOCKED_OR_RATE_LIMITED"
    if error.__class__.__name__ == "ParseError":
        return "PARSER_FAILURE"
    if error.__class__.__name__ == "FetchError":
        return "FETCH_FAILURE"
    return "INTERNAL_FAILURE"
