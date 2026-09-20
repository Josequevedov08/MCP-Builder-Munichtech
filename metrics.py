"""
Usage events and the numbers built from them.

Every event is a small record (kind + data) kept in memory and, when DATABASE_URL is set, also in
PostgreSQL so the numbers survive a restart. A database problem never breaks a request: the memory
copy is used instead and the summary says whether the data is persistent.

Support messages carry personal data. They are stored with the other events but the public summary
only counts them, and the messages themselves are read through a protected endpoint.
"""

import asyncio
import logging
from collections import Counter, deque
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("mcp-builder.metrics")

SOURCES = ("files", "database", "api")
MEMORY_LIMIT = 5000
READ_LIMIT = 5000

_CREATE_TABLE = """
create table if not exists events (
    id bigserial primary key,
    ts timestamptz not null default now(),
    kind text not null,
    data jsonb not null default '{}'::jsonb
)
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def summarize(events: list[dict[str, Any]], persistent: bool) -> dict[str, Any]:
    """Aggregates events (oldest first) into the public numbers. It never includes personal data."""
    builds = [e["data"] for e in events if e["kind"] == "build"]
    seconds = [b["seconds"] for b in builds if isinstance(b.get("seconds"), (int, float))]
    orders = [e for e in events if e["kind"] == "order"]
    voice = [e["data"] for e in events if e["kind"] == "voice"]
    downloads = [e["data"] for e in events if e["kind"] == "download"]
    receipts = [e["data"] for e in events if e["kind"] == "receipt"]
    support = [e["data"] for e in events if e["kind"] == "support"]
    errors = Counter(e["data"].get("code", "unknown") for e in events if e["kind"] == "error")

    by_source = Counter(b.get("source") for b in builds)
    recent_orders = [
        {
            "order_id": o["data"].get("order_id"),
            "source": o["data"].get("source"),
            "total": o["data"].get("total"),
            "ts": o["ts"],
        }
        for o in reversed(orders[-8:])
    ]
    feed_kinds = {"build", "order", "download", "voice", "receipt", "support"}
    recent = [
        {"kind": e["kind"], "ts": e["ts"], "detail": _detail(e)}
        for e in reversed([e for e in events if e["kind"] in feed_kinds][-12:])
    ]
    return {
        "since": events[0]["ts"] if events else None,
        "generated_at": _now(),
        "persistent": persistent,
        "builds": {
            "total": len(builds),
            "by_source": {s: by_source.get(s, 0) for s in SOURCES},
            "ai_status": dict(Counter(b.get("ai_status") for b in builds if b.get("ai_status"))),
            "avg_seconds": round(sum(seconds) / len(seconds), 1) if seconds else None,
            "max_seconds": round(max(seconds), 1) if seconds else None,
        },
        "downloads": {
            "total": len(downloads),
            "by_source": {s: sum(1 for d in downloads if d.get("source") == s) for s in SOURCES},
        },
        "orders": {
            "total": len(orders),
            "test_volume": round(sum(o["data"].get("total") or 0 for o in orders), 2),
            "by_source": {s: sum(1 for o in orders if o["data"].get("source") == s) for s in SOURCES},
            "recent": recent_orders,
        },
        "voice": {
            "total": len(voice),
            "by_language": dict(Counter(v.get("language") for v in voice if v.get("language"))),
        },
        "receipts": {
            "sent": sum(1 for r in receipts if r.get("ok")),
            "failed": sum(1 for r in receipts if not r.get("ok")),
        },
        "support": {
            "total": len(support),
            "by_topic": dict(Counter(s.get("topic") for s in support if s.get("topic"))),
        },
        "errors": dict(errors),
        "recent": recent,
    }


def _detail(event: dict[str, Any]) -> str:
    data = event["data"]
    kind = event["kind"]
    if kind == "build":
        return f"{data.get('source')} / {data.get('ai_status')}"
    if kind == "order":
        return f"{data.get('order_id')} / {data.get('source')}"
    if kind in ("download", "support"):
        return str(data.get("source") or data.get("topic") or "")
    if kind == "voice":
        return f"{data.get('status')} / {data.get('language')}"
    if kind == "receipt":
        return "sent" if data.get("ok") else "failed"
    return ""


class Metrics:
    def __init__(self, database_url: str | None = None) -> None:
        self._url = database_url or ""
        self._memory: deque[dict[str, Any]] = deque(maxlen=MEMORY_LIMIT)
        self._tasks: set[asyncio.Task] = set()
        self._orders_seen: set[str] = set()
        self._db_ready = False

    @property
    def persistent(self) -> bool:
        return self._db_ready

    async def start(self) -> None:
        if not self._url:
            return
        try:
            conn = await self._connect()
            async with conn:
                await conn.execute(_CREATE_TABLE)
            self._db_ready = True
            logger.info("Metrics are stored in PostgreSQL")
        except Exception:
            logger.exception("Could not prepare the metrics database, using memory only")

    async def stop(self) -> None:
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

    async def _connect(self):
        import psycopg  # imported lazily so the memory mode needs no driver

        return await psycopg.AsyncConnection.connect(self._url, autocommit=True, connect_timeout=8)

    def record(self, kind: str, data: dict[str, Any] | None = None) -> None:
        """Fire and forget. Never raises."""
        try:
            data = data or {}
            if kind == "order":
                order_id = data.get("order_id")
                if order_id in self._orders_seen:
                    return
                self._orders_seen.add(order_id)
            event = {"ts": _now(), "kind": kind, "data": data}
            self._memory.append(event)
            if self._db_ready:
                task = asyncio.get_running_loop().create_task(self._insert(kind, data))
                self._tasks.add(task)
                task.add_done_callback(self._tasks.discard)
        except Exception:
            logger.exception("Could not record an event")

    async def _insert(self, kind: str, data: dict[str, Any]) -> None:
        try:
            from psycopg.types.json import Jsonb

            conn = await self._connect()
            async with conn:
                await conn.execute("insert into events (kind, data) values (%s, %s)", (kind, Jsonb(data)))
        except Exception:
            logger.warning("Could not store an event in the database")

    async def events(self) -> tuple[list[dict[str, Any]], bool]:
        """Events oldest first, and whether they come from the database."""
        if self._db_ready:
            try:
                conn = await self._connect()
                async with conn:
                    cursor = await conn.execute(
                        "select ts, kind, data from events order by id desc limit %s", (READ_LIMIT,)
                    )
                    rows = await cursor.fetchall()
                events = [{"ts": ts.isoformat(), "kind": kind, "data": data or {}} for ts, kind, data in rows]
                events.reverse()
                return events, True
            except Exception:
                logger.warning("Could not read the metrics database, using memory")
        return list(self._memory), False

    async def summary(self) -> dict[str, Any]:
        events, persistent = await self.events()
        return summarize(events, persistent)

    async def support_tickets(self, limit: int = 100) -> list[dict[str, Any]]:
        events, _ = await self.events()
        tickets = [{"ts": e["ts"], **e["data"]} for e in events if e["kind"] == "support"]
        return list(reversed(tickets))[:limit]
