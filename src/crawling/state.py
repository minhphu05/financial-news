"""Persistent frontier/run/attempt/outbox state using existing DB configuration."""

import json
import os
from contextlib import contextmanager
from datetime import datetime, timezone

from src.pipeline_operations.config import OperationsSettings

from .sources import SOURCES


class SourceBusy(RuntimeError):
    pass


class Repository:
    def __init__(self, settings=None):
        import psycopg
        from psycopg.rows import dict_row

        self.connection = psycopg.connect(
            **(settings or OperationsSettings.from_env()).connection_kwargs,
            row_factory=dict_row,
            autocommit=True,
        )

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.connection.close()

    def query(self, sql, args=()):
        with self.connection.cursor() as c:
            c.execute(sql, args)
            return c.fetchall() if c.description else []

    @contextmanager
    def lock(self, source):
        row = self.query(
            "SELECT pg_try_advisory_lock(hashtextextended(%s, 0)) AS acquired",
            ("crawler:" + source,),
        )[0]
        if not row["acquired"]:
            raise SourceBusy("source_batch_already_running")
        try:
            yield
        finally:
            self.query(
                "SELECT pg_advisory_unlock(hashtextextended(%s, 0))",
                ("crawler:" + source,),
            )

    def grant_monitoring(self):
        from psycopg import sql

        role = os.getenv("MONITORING_POSTGRES_USER", "monitoring_exporter")
        if self.query("SELECT 1 FROM pg_roles WHERE rolname=%s", (role,)):
            with self.connection.cursor() as c:
                c.execute(
                    sql.SQL("GRANT USAGE ON SCHEMA crawler_operations TO {}").format(
                        sql.Identifier(role)
                    )
                )
                c.execute(
                    sql.SQL(
                        "GRANT SELECT ON ALL TABLES IN SCHEMA crawler_operations TO {}"
                    ).format(sql.Identifier(role))
                )

    def seed(self):
        # Separate crawler config IDs preserve the CafeF sample source row.
        for key, s in SOURCES.items():
            config = {
                "crawler": {
                    "adapter": key,
                    "raw_schema_version": s.raw_schema_version,
                    "parser_version": s.parser_version,
                    "discovery_urls": [s.listing],
                    "request_interval_seconds": 3,
                    "recheck_hours": 6,
                    "recent_days": 7,
                    "max_articles": 3,
                    "max_attempts": 3,
                    "user_agent": os.getenv(
                        "CRAWLER_USER_AGENT", "FinancialNewsResearch/0.1"
                    ),
                    "processing_version": "crawl-v1",
                }
            }
            self.query(
                """INSERT INTO control_metadata.news_sources(source_id,source_name,source_type,enabled,base_url,description,config)
                VALUES (%s,%s,'crawler',true,%s,'Phase08 local public HTTP crawler',%s::jsonb) ON CONFLICT(source_id) DO NOTHING""",
                ("crawler:" + key, key, "https://" + s.host, json.dumps(config)),
            )
        self.grant_monitoring()
        return list(SOURCES)

    def config(self, key):
        rows = self.query(
            "SELECT enabled,config FROM control_metadata.news_sources WHERE source_id=%s",
            ("crawler:" + key,),
        )
        if not rows:
            raise ValueError("crawler_source_not_seeded")
        if not rows[0]["enabled"]:
            raise ValueError("crawler_source_disabled")
        config = rows[0]["config"]["crawler"]
        s = SOURCES[key]
        if (
            config["adapter"] != key
            or config["raw_schema_version"] != s.raw_schema_version
            or config["parser_version"] != s.parser_version
        ):
            raise ValueError("crawler_config_version_mismatch")
        if (
            not 1 <= int(config["max_articles"]) <= 20
            or not 1 <= int(config["max_attempts"]) <= 10
            or float(config["request_interval_seconds"]) < 1
            or float(config["recheck_hours"]) < 1
            or not 1 <= int(config["recent_days"]) <= 30
        ):
            raise ValueError("invalid_bounded_crawler_config")
        for url in config["discovery_urls"]:
            s.url(url)
        if len(config["discovery_urls"]) > 3:
            raise ValueError("too_many_listing_pages")
        return config

    def start(self, source, run, trigger):
        self.query(
            "INSERT INTO crawler_operations.source_state(source) VALUES (%s) ON CONFLICT DO NOTHING",
            (source,),
        )
        state = self.query(
            "SELECT cooldown_until FROM crawler_operations.source_state WHERE source=%s",
            (source,),
        )[0]
        if state["cooldown_until"] and state["cooldown_until"] > datetime.now(
            timezone.utc
        ):
            raise SourceBusy("source_retry_after_cooldown")
        self.query(
            "UPDATE crawler_operations.crawl_runs SET status='FAILED',finished_at=now(),error_message='Interrupted source batch; lock was released' WHERE source=%s AND status='RUNNING'",
            (source,),
        )
        self.query(
            "INSERT INTO crawler_operations.crawl_runs(crawl_run_id,source,trigger_type,status) VALUES (%s,%s,%s,'RUNNING')",
            (run, source, trigger),
        )

    def discover(self, source, urls):
        for url in urls:
            self.query(
                """INSERT INTO crawler_operations.frontier(source,canonical_url) VALUES (%s,%s)
                ON CONFLICT(source,canonical_url) DO UPDATE SET last_seen_at=now()""",
                (source, url),
            )

    def eligible(self, source, limit, recent_days):
        return self.query(
            """SELECT * FROM crawler_operations.frontier WHERE source=%s AND next_eligible_at<=now()
          AND (status IN ('NEW','RETRY') OR (status='SUCCESS' AND first_seen_at>=now()-%s::interval))
          ORDER BY (status='NEW') DESC,next_eligible_at,canonical_url LIMIT %s""",
            (source, f"{recent_days} days", limit),
        )

    def selected(self, source, urls):
        return self.query(
            "SELECT * FROM crawler_operations.frontier WHERE source=%s AND canonical_url=ANY(%s) ORDER BY canonical_url",
            (source, urls),
        )

    def success(self, source, row, run, envelope, hashes, landing_key, hours):
        content_hash, observation_hash = hashes
        self.query(
            """UPDATE crawler_operations.frontier SET status='SUCCESS',last_fetched_at=now(),next_eligible_at=now()+%s::interval,
          attempts=0,content_hash=%s,observation_hash=%s,parser_version=%s,last_http_status=%s,last_error=NULL,landing_key=%s
          WHERE source=%s AND canonical_url=%s""",
            (
                f"{hours} hours",
                content_hash,
                observation_hash,
                envelope["parser_version"],
                envelope["http_status"],
                landing_key,
                source,
                row["canonical_url"],
            ),
        )
        self.query(
            "INSERT INTO crawler_operations.crawl_attempts(crawl_run_id,canonical_url,status,http_status,landing_key) VALUES (%s,%s,'SUCCESS',%s,%s)",
            (run, row["canonical_url"], envelope["http_status"], landing_key),
        )

    def failure(self, source, row, run, error, max_attempts):
        attempts = row["attempts"] + 1
        status = (
            "RETRY"
            if getattr(error, "retryable", False) and attempts < max_attempts
            else "PERMANENT_FAILURE"
        )
        if error.__class__.__name__ == "ParseError":
            status = "PARSE_FAILURE"
        http = getattr(error, "status", None)
        if http in (401, 403):
            status = "BLOCKED"
        cooldown = max(getattr(error, "retry_after", 0), min(3600, 60 * 2**attempts))
        self.query(
            """UPDATE crawler_operations.frontier SET status=%s,attempts=%s,next_eligible_at=now()+%s::interval,
            last_error=%s,last_http_status=%s WHERE source=%s AND canonical_url=%s""",
            (
                status,
                attempts,
                f"{cooldown} seconds",
                str(error)[:500],
                http,
                source,
                row["canonical_url"],
            ),
        )
        self.query(
            "INSERT INTO crawler_operations.crawl_attempts(crawl_run_id,canonical_url,status,http_status,error_message) VALUES (%s,%s,%s,%s,%s)",
            (run, row["canonical_url"], status, http, str(error)[:500]),
        )
        if getattr(error, "retry_after", 0):
            self.cooldown(source, error.retry_after)
        return status

    def cooldown(self, source, seconds):
        self.query(
            "UPDATE crawler_operations.source_state SET cooldown_until=now()+%s::interval WHERE source=%s",
            (f"{seconds} seconds", source),
        )

    def finish(self, source, run, status, metrics, error=None):
        self.query(
            "UPDATE crawler_operations.crawl_runs SET status=%s,finished_at=now(),metrics=%s::jsonb,error_message=%s WHERE crawl_run_id=%s",
            (status, json.dumps(metrics), error, run),
        )
        if status == "SUCCESS":
            self.query(
                "UPDATE crawler_operations.source_state SET last_success_at=now() WHERE source=%s",
                (source,),
            )

    def batch(self, batch, run, source, day, manifest):
        self.query(
            """INSERT INTO crawler_operations.batches(batch_id,crawl_run_id,source,processing_date,manifest_key)
        VALUES (%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
            (batch, run, source, day, manifest),
        )

    def pending(self, source, limit=20):
        return self.query(
            "SELECT * FROM crawler_operations.batches WHERE source=%s AND status<>'SUCCESS' ORDER BY created_at LIMIT %s",
            (source, limit),
        )
