import json
import logging
import threading
import traceback
from datetime import datetime, timezone
from typing import Any

import httpx

from app.middleware.trace import request_id_var, trace_id_var

APP_NAME = "ti-analyst"
INDEX_PREFIX = "platform_logs"
BULK_SIZE = 50


class OpenSearchHandler(logging.Handler):
    def __init__(self, opensearch_url: str, level: int = logging.DEBUG) -> None:
        super().__init__(level)
        self._url = opensearch_url.rstrip("/")
        self._buffer: list[dict[str, Any]] = []
        self._lock = threading.Lock()

    def emit(self, record: logging.LogRecord) -> None:
        entry = self._format_record(record)
        batch: list[dict] | None = None
        with self._lock:
            self._buffer.append(entry)
            if len(self._buffer) >= BULK_SIZE:
                batch = self._buffer.copy()
                self._buffer.clear()
        if batch is not None:
            self._send(batch)

    def flush(self) -> None:
        with self._lock:
            batch = self._buffer.copy()
            self._buffer.clear()
        self._send(batch)

    def close(self) -> None:
        self.flush()
        super().close()

    def _send(self, entries: list[dict]) -> None:
        """Send a batch to OpenSearch. Called WITHOUT self._lock held."""
        if not entries:
            return

        index_name = f"{INDEX_PREFIX}_{datetime.now(timezone.utc).strftime('%Y_%m_%d')}"
        lines: list[str] = []
        for entry in entries:
            lines.append(json.dumps({"index": {"_index": index_name}}))
            lines.append(json.dumps(entry, default=str))

        body = "\n".join(lines) + "\n"

        try:
            httpx.post(
                f"{self._url}/_bulk",
                content=body,
                headers={"Content-Type": "application/x-ndjson"},
                timeout=3.0,
            )
        except Exception:
            pass

    def _format_record(self, record: logging.LogRecord) -> dict[str, Any]:
        data: dict[str, Any] = {
            "@timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelno,
            "level_name": record.levelname,
            "message": record.getMessage(),
            "channel": record.name,
            "app_name": APP_NAME,
            "trace_id": trace_id_var.get(""),
            "request_id": request_id_var.get(""),
        }

        if record.exc_info and record.exc_info[1] is not None:
            exc = record.exc_info[1]
            data["exception"] = {
                "class": type(exc).__qualname__,
                "message": str(exc),
                "trace": "".join(traceback.format_exception(*record.exc_info)),
            }

        return data
