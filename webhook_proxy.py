#!/usr/bin/env python3
"""Run the MCP app with a verified Meta WhatsApp webhook."""

import hashlib
import hmac
import json
import logging
import os
import sqlite3
import threading
import time
from pathlib import Path

import uvicorn
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse
from starlette.routing import Route

from server import PORT, app

logger = logging.getLogger("whatsapp-webhook")
DB_PATH = os.getenv("WHATSAPP_RECEIPTS_DB", "/data/whatsapp_receipts.sqlite3")
VERIFY_TOKEN = os.getenv("WHATSAPP_WEBHOOK_VERIFY_TOKEN", "")
APP_SECRET = os.getenv("WHATSAPP_APP_SECRET", "") or os.getenv("META_APP_SECRET", "")
ALLOW_UNSIGNED = os.getenv("WEBHOOK_ALLOW_UNSIGNED", "false").lower() == "true"
DB_LOCK = threading.Lock()


def _connect():
    path = Path(DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS message_receipts (
            message_id TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            recipient_id TEXT,
            timestamp TEXT,
            errors_json TEXT,
            received_at INTEGER NOT NULL,
            raw_json TEXT NOT NULL
        )"""
    )
    conn.commit()
    return conn


def _signature_ok(raw: bytes, header: str | None) -> bool:
    if not APP_SECRET:
        return ALLOW_UNSIGNED
    if not header or not header.startswith("sha256="):
        return False
    expected = hmac.new(APP_SECRET.encode(), raw, hashlib.sha256).hexdigest()
    return hmac.compare_digest(header[7:], expected)


def _status_rows(payload: dict):
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            for status in value.get("statuses", []):
                if status.get("id") and status.get("status"):
                    yield status


async def webhook_verify(request: Request):
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")
    if mode == "subscribe" and token and token == VERIFY_TOKEN and challenge:
        return PlainTextResponse(challenge)
    return PlainTextResponse("Forbidden", status_code=403)


async def webhook_receive(request: Request):
    raw = await request.body()
    if not _signature_ok(raw, request.headers.get("x-hub-signature-256")):
        return JSONResponse({"ok": False, "error": "invalid webhook signature"}, status_code=401)
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return JSONResponse({"ok": False, "error": "invalid JSON"}, status_code=400)

    stored = 0
    now = int(time.time())
    with DB_LOCK:
        conn = _connect()
        try:
            for status in _status_rows(payload):
                errors = status.get("errors") or []
                conn.execute(
                    """INSERT INTO message_receipts
                    (message_id, status, recipient_id, timestamp, errors_json, received_at, raw_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(message_id) DO UPDATE SET
                      status=excluded.status,
                      recipient_id=excluded.recipient_id,
                      timestamp=excluded.timestamp,
                      errors_json=excluded.errors_json,
                      received_at=excluded.received_at,
                      raw_json=excluded.raw_json""",
                    (
                        status["id"],
                        status["status"],
                        status.get("recipient_id"),
                        status.get("timestamp"),
                        json.dumps(errors, ensure_ascii=False),
                        now,
                        json.dumps(status, ensure_ascii=False),
                    ),
                )
                stored += 1
            conn.commit()
        finally:
            conn.close()

    logger.info("Stored %s WhatsApp delivery receipt(s)", stored)
    return JSONResponse({"ok": True, "stored": stored})


async def receipt_status(request: Request):
    message_id = request.path_params["message_id"]
    with DB_LOCK:
        conn = _connect()
        try:
            row = conn.execute(
                "SELECT message_id,status,recipient_id,timestamp,errors_json,received_at FROM message_receipts WHERE message_id = ?",
                (message_id,),
            ).fetchone()
        finally:
            conn.close()
    if not row:
        return JSONResponse({"id": message_id, "status": "unknown"})
    return JSONResponse({
        "id": row[0],
        "status": row[1],
        "recipient_id": row[2],
        "timestamp": row[3],
        "errors": json.loads(row[4] or "[]"),
        "received_at": row[5],
    })


app.routes.extend([
    Route("/webhook", webhook_verify, methods=["GET"]),
    Route("/webhook", webhook_receive, methods=["POST"]),
    Route("/webhook/status/{message_id:path}", receipt_status, methods=["GET"]),
])


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    uvicorn.run(app, host="0.0.0.0", port=PORT, proxy_headers=True, forwarded_allow_ips="*")
