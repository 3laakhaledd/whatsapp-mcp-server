#!/usr/bin/env python3
"""
Meta WhatsApp Cloud API + Facebook Page Tools - MCP Server
Connects to ClickUp Brain via MCP Connect for bulk WhatsApp messaging
and Facebook Page / Instagram media lookups for ad creation.
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

# Facebook Page & Instagram config
META_PAGE_ID = os.getenv("META_PAGE_ID", "")
META_PAGE_ACCESS_TOKEN = os.getenv("META_PAGE_ACCESS_TOKEN", "") or WHATSAPP_TOKEN
META_INSTAGRAM_ACCOUNT_ID = os.getenv("META_INSTAGRAM_ACCOUNT_ID", "")

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


async def _graph_get(endpoint: str, params: dict | None = None) -> dict:
    """Generic Graph API GET using the Page access token."""
    url = f"{WHATSAPP_API_BASE}/{endpoint}"
    headers = {
        "Authorization": f"Bearer {META_PAGE_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url, headers=headers, params=params)
        resp.raise_for_status()
        return resp.json()


# ============================================================
# WhatsApp Tools
# ============================================================

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
        {"total": len(recipients), "sent_count": len(results["sent"]), "failed_count": len(results["failed"]), "details": results},
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
                "template": {"name": template_name, "language": {"code": language_code}, "components": components},
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
        {"total": len(recipients), "sent_count": len(results["sent"]), "failed_count": len(results["failed"]), "details": results},
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


# ============================================================
# Facebook Page Tools
# ============================================================

@mcp.tool()
async def list_page_published_posts(
    limit: int = 10,
    after: str | None = None,
) -> str:
    """
    List recent published posts from the Facebook Page.
    Returns post IDs (object_story_id format) for creating ads.

    Args:
        limit: Number of posts to return (default 10, max 100)
        after: Pagination cursor for next page
    """
    if not META_PAGE_ID:
        return json.dumps({"error": "META_PAGE_ID env var not set"})

    params: dict[str, Any] = {
        "fields": "id,message,created_time,permalink_url,type,full_picture,is_published,attachments{type,media_type,title,url}",
        "limit": min(limit, 100),
    }
    if after:
        params["after"] = after

    try:
        data = await _graph_get(f"{META_PAGE_ID}/published_posts", params)
    except httpx.HTTPStatusError as e:
        return json.dumps({"error": f"Graph API error: {e.response.status_code} {e.response.text}"})

    posts = []
    for p in data.get("data", []):
        msg = p.get("message", "")
        attachment = {}
        attachments = p.get("attachments", {}).get("data", [])
        if attachments:
            att = attachments[0]
            attachment = {
                "type": att.get("type"),
                "media_type": att.get("media_type"),
                "title": att.get("title"),
            }
        posts.append({
            "object_story_id": p.get("id"),
            "message_preview": (msg[:120] + "...") if len(msg) > 120 else msg,
            "created_time": p.get("created_time"),
            "permalink_url": p.get("permalink_url"),
            "type": p.get("type"),
            "attachment": attachment if attachment else None,
        })

    result: dict[str, Any] = {"posts": posts, "count": len(posts)}
    paging = data.get("paging", {})
    cursors = paging.get("cursors", {})
    if cursors.get("after"):
        result["next_cursor"] = cursors["after"]

    return json.dumps(result, indent=2)


@mcp.tool()
async def list_page_videos(
    limit: int = 10,
    after: str | None = None,
) -> str:
    """
    List videos and reels published on the Facebook Page.
    Returns video IDs and their associated post IDs.

    Args:
        limit: Number of videos to return (default 10, max 100)
        after: Pagination cursor for next page
    """
    if not META_PAGE_ID:
        return json.dumps({"error": "META_PAGE_ID env var not set"})

    params: dict[str, Any] = {
        "fields": "id,title,description,created_time,permalink_url,length,post_id,embeddable",
        "limit": min(limit, 100),
    }
    if after:
        params["after"] = after

    try:
        data = await _graph_get(f"{META_PAGE_ID}/videos", params)
    except httpx.HTTPStatusError as e:
        return json.dumps({"error": f"Graph API error: {e.response.status_code} {e.response.text}"})

    videos = []
    for v in data.get("data", []):
        desc = v.get("description", "")
        videos.append({
            "video_id": v.get("id"),
            "post_id": v.get("post_id"),
            "title": v.get("title", ""),
            "description_preview": (desc[:120] + "...") if len(desc) > 120 else desc,
            "created_time": v.get("created_time"),
            "permalink_url": v.get("permalink_url"),
            "length_seconds": v.get("length"),
        })

    result: dict[str, Any] = {"videos": videos, "count": len(videos)}
    paging = data.get("paging", {})
    cursors = paging.get("cursors", {})
    if cursors.get("after"):
        result["next_cursor"] = cursors["after"]

    return json.dumps(result, indent=2)


# ============================================================
# Instagram Tools
# ============================================================

@mcp.tool()
async def list_instagram_media(
    limit: int = 10,
    after: str | None = None,
) -> str:
    """
    List recent media (posts, reels, carousels) from the connected Instagram account.
    Returns IG media IDs for creating Instagram ads.

    Args:
        limit: Number of media items to return (default 10, max 100)
        after: Pagination cursor for next page
    """
    ig_id = META_INSTAGRAM_ACCOUNT_ID
    if not ig_id:
        return json.dumps({"error": "META_INSTAGRAM_ACCOUNT_ID env var not set"})

    params: dict[str, Any] = {
        "fields": "id,caption,media_type,media_product_type,permalink,timestamp,thumbnail_url",
        "limit": min(limit, 100),
    }
    if after:
        params["after"] = after

    try:
        data = await _graph_get(f"{ig_id}/media", params)
    except httpx.HTTPStatusError as e:
        return json.dumps({"error": f"Graph API error: {e.response.status_code} {e.response.text}"})

    media = []
    for m in data.get("data", []):
        caption = m.get("caption", "")
        media.append({
            "ig_media_id": m.get("id"),
            "caption_preview": (caption[:120] + "...") if len(caption) > 120 else caption,
            "media_type": m.get("media_type"),
            "product_type": m.get("media_product_type"),
            "permalink": m.get("permalink"),
            "timestamp": m.get("timestamp"),
        })

    result: dict[str, Any] = {"media": media, "count": len(media)}
    paging = data.get("paging", {})
    cursors = paging.get("cursors", {})
    if cursors.get("after"):
        result["next_cursor"] = cursors["after"]

    return json.dumps(result, indent=2)


@mcp.tool()
async def get_instagram_media_by_shortcode(shortcode: str) -> str:
    """
    Look up an Instagram media item by its URL shortcode.
    Useful when you have an IG reel/post URL and need the media ID for ads.

    Args:
        shortcode: The shortcode from an Instagram URL (e.g. "DdWO5ekMOix" from instagram.com/reel/DdWO5ekMOix/)
    """
    ig_id = META_INSTAGRAM_ACCOUNT_ID
    if not ig_id:
        return json.dumps({"error": "META_INSTAGRAM_ACCOUNT_ID env var not set"})

    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
    media_id = 0
    for char in shortcode:
        if char not in alphabet:
            return json.dumps({"error": f"Invalid shortcode character: {char}"})
        media_id = media_id * 64 + alphabet.index(char)

    try:
        data = await _graph_get(str(media_id), {
            "fields": "id,caption,media_type,media_product_type,permalink,timestamp,thumbnail_url",
        })
        caption = data.get("caption", "")
        return json.dumps({
            "ig_media_id": data.get("id"),
            "caption_preview": (caption[:120] + "...") if len(caption) > 120 else caption,
            "media_type": data.get("media_type"),
            "product_type": data.get("media_product_type"),
            "permalink": data.get("permalink"),
            "timestamp": data.get("timestamp"),
        }, indent=2)
    except httpx.HTTPStatusError as e:
        return json.dumps({
            "error": f"Could not fetch media {media_id}: {e.response.status_code} {e.response.text}",
            "decoded_media_id": str(media_id),
            "hint": "The token may need instagram_basic permission, or the media may belong to a different IG account.",
        })


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
        "name": "WhatsApp + Page + IG MCP Server",
        "status": "ok",
        "transport": "sse",
        "sse_endpoint": "/sse",
        "tools": [
            "WhatsApp: send_text_message, send_template_message, send_bulk_text_messages, send_bulk_template_messages, send_media_message, get_message_templates, check_phone_number_status",
            "Facebook Page: list_page_published_posts, list_page_videos",
            "Instagram: list_instagram_media, get_instagram_media_by_shortcode",
        ],
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
    logger.info(f"Starting MCP Server on 0.0.0.0:{PORT}")
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=PORT,
        proxy_headers=True,
        forwarded_allow_ips="*",
    )
