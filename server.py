#!/usr/bin/env python3
"""
Meta WhatsApp Cloud API - MCP Server
Connects to ClickUp Brain via MCP Connect for bulk WhatsApp messaging.
"""

import os
import json
import logging
import httpx
import uvicorn
from typing import Any
from mcp.server.fastmcp import FastMCP
from mcp.server.sse import SseServerTransport
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route, Mount

# -- Config --
WHATSAPP_API_VERSION = os.getenv("WHATSAPP_API_VERSION", "v21.0")
WHATSAPP_API_BASE = f"https://graph.facebook.com/{WHATSAPP_API_VERSION}"
WHATSAPP_TOKEN = os.getenv("WHATSAPP_ACCESS_TOKEN", "")
PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
PORT = int(os.getenv("PORT", "8000"))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("whatsapp-mcp")

mcp = FastMCP("WhatsApp MCP Server")


# -- Helpers --
def _headers() -> dict:
    return {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json",
    }


async def _post(path: str, payload: dict) -> dict:
    url = f"{WHATSAPP_API_BASE}/{PHONE_NUMBER_ID}/{path}"
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(url, headers=_headers(), json=payload)
        resp.raise_for_status()
        return resp.json()


async def _get(path: str, params: dict | None = None) -> dict:
    url = f"{WHATSAPP_API_BASE}/{PHONE_NUMBER_ID}/{path}"
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url, headers=_headers(), params=params)
        resp.raise_for_status()
        return resp.json()


# -- Tools --

@mcp.tool()
async def send_text_message(to: str, body: str, preview_url: bool = False) -> str:
    """
    Send a free-form text WhatsApp message to a single recipient.

    Args:
        to: Recipient phone number with country code (e.g. "201090840870")
        body: The text message content
        preview_url: Whether to show link previews in the message
    """
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"preview_url": preview_url, "body": body},
    }
    result = await _post("messages", payload)
    return json.dumps(result, indent=2)


@mcp.tool()
async def send_template_message(
    to: str,
    template_name: str,
    language_code: str = "en",
    header_params: list[str] | None = None,
    body_params: list[str] | None = None,
) -> str:
    """
    Send a pre-approved WhatsApp template message to a single recipient.

    Args:
        to: Recipient phone number with country code (e.g. "201090840870")
        template_name: The exact name of the approved template
        language_code: Template language code (e.g. "en", "ar")
        header_params: List of parameter values for the template header
        body_params: List of parameter values for the template body
    """
    components = []
    if header_params:
        components.append({
            "type": "header",
            "parameters": [{"type": "text", "text": p} for p in header_params],
        })
    if body_params:
        components.append({
            "type": "body",
            "parameters": [{"type": "text", "text": p} for p in body_params],
        })

    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": language_code},
            "components": components,
        },
    }
    result = await _post("messages", payload)
    return json.dumps(result, indent=2)


@mcp.tool()
async def send_bulk_text_messages(
    recipients: list[str],
    body: str,
    preview_url: bool = False,
) -> str:
    """
    Send the same text message to multiple recipients (bulk).
    Each recipient gets an individual API call. Returns a summary of results.

    Args:
        recipients: List of phone numbers with country codes
        body: The text message content to send to all recipients
        preview_url: Whether to show link previews
    """
    results = {"sent": [], "failed": []}
    async with httpx.AsyncClient(timeout=30) as client:
        for phone in recipients:
            payload = {
                "messaging_product": "whatsapp",
                "to": phone,
                "type": "text",
                "text": {"preview_url": preview_url, "body": body},
            }
            try:
                resp = await client.post(
                    f"{WHATSAPP_API_BASE}/{PHONE_NUMBER_ID}/messages",
                    headers=_headers(),
                    json=payload,
                )
                resp.raise_for_status()
                data = resp.json()
                results["sent"].append({"to": phone, "message_id": data.get("messages", [{}])[0].get("id")})
            except Exception as e:
                results["failed"].append({"to": phone, "error": str(e)})

    return json.dumps(
        {
            "total": len(recipients),
            "sent_count": len(results["sent"]),
            "failed_count": len(results["failed"]),
            "details": results,
        },
        indent=2,
    )


@mcp.tool()
async def send_bulk_template_messages(
    recipients: list[str],
    template_name: str,
    language_code: str = "en",
    body_params: list[str] | None = None,
) -> str:
    """
    Send a template message to multiple recipients (bulk).

    Args:
        recipients: List of phone numbers with country codes
        template_name: The exact name of the approved template
        language_code: Template language code (e.g. "en", "ar")
        body_params: Shared body parameter values for all recipients
    """
    results = {"sent": [], "failed": []}
    async with httpx.AsyncClient(timeout=30) as client:
        for phone in recipients:
            components = []
            if body_params:
                components.append({
                    "type": "body",
                    "parameters": [{"type": "text", "text": p} for p in body_params],
                })

            payload = {
                "messaging_product": "whatsapp",
                "to": phone,
                "type": "template",
                "template": {
                    "name": template_name,
                    "language": {"code": language_code},
                    "components": components,
                },
            }
            try:
                resp = await client.post(
                    f"{WHATSAPP_API_BASE}/{PHONE_NUMBER_ID}/messages",
                    headers=_headers(),
                    json=payload,
                )
                resp.raise_for_status()
                data = resp.json()
                results["sent"].append({"to": phone, "message_id": data.get("messages", [{}])[0].get("id")})
            except Exception as e:
                results["failed"].append({"to": phone, "error": str(e)})

    return json.dumps(
        {
            "total": len(recipients),
            "sent_count": len(results["sent"]),
            "failed_count": len(results["failed"]),
            "details": results,
        },
        indent=2,
    )


@mcp.tool()
async def send_media_message(
    to: str,
    media_type: str,
    media_url: str,
    caption: str | None = None,
) -> str:
    """
    Send a media message (image, video, document, audio) via WhatsApp.

    Args:
        to: Recipient phone number with country code
        media_type: One of "image", "video", "document", "audio"
        media_url: Public URL of the media file
        caption: Optional caption (supported for image, video, document)
    """
    media_obj: dict[str, Any] = {"link": media_url}
    if caption and media_type in ("image", "video", "document"):
        media_obj["caption"] = caption

    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": media_type,
        media_type: media_obj,
    }
    result = await _post("messages", payload)
    return json.dumps(result, indent=2)


@mcp.tool()
async def get_message_templates(limit: int = 20) -> str:
    """
    List approved WhatsApp message templates for this business account.

    Args:
        limit: Max number of templates to return (default 20)
    """
    waba_id = os.getenv("WHATSAPP_BUSINESS_ACCOUNT_ID", "")
    if not waba_id:
        return json.dumps({"error": "WHATSAPP_BUSINESS_ACCOUNT_ID not set"})

    url = f"{WHATSAPP_API_BASE}/{waba_id}/message_templates"
    params = {"limit": limit}
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url, headers=_headers(), params=params)
        resp.raise_for_status()
        data = resp.json()

    templates = []
    for t in data.get("data", []):
        templates.append({
            "name": t.get("name"),
            "status": t.get("status"),
            "language": t.get("language"),
            "category": t.get("category"),
            "id": t.get("id"),
        })
    return json.dumps({"templates": templates, "count": len(templates)}, indent=2)


@mcp.tool()
async def check_phone_number_status() -> str:
    """Check the status and quality rating of the connected WhatsApp phone number."""
    result = await _get("")
    return json.dumps(result, indent=2)


# -- SSE transport with CORS --
sse = SseServerTransport("/messages/")


async def handle_sse(request: Request):
    logger.info(f"SSE connection from {request.client}")
    async with sse.connect_sse(
        request.scope, request.receive, request._send
    ) as (read_stream, write_stream):
        await mcp._mcp_server.run(
            read_stream,
            write_stream,
            mcp._mcp_server.create_initialization_options(),
        )


async def health(request: Request):
    return JSONResponse({
        "name": "WhatsApp MCP Server",
        "status": "ok",
        "transport": "sse",
        "sse_endpoint": "/sse",
    })


app = Starlette(
    routes=[
        Route("/", endpoint=health),
        Route("/sse", endpoint=handle_sse),
        Mount("/messages/", app=sse.handle_post_message),
    ],
    middleware=[
        Middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_methods=["*"],
            allow_headers=["*"],
            expose_headers=["*"],
        ),
    ],
)

if __name__ == "__main__":
    logger.info(f"Starting WhatsApp MCP Server on 0.0.0.0:{PORT}")
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=PORT,
        proxy_headers=True,
        forwarded_allow_ips="*",
    )
