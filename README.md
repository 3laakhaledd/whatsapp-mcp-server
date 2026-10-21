# WhatsApp MCP Server — Meta Cloud API

An MCP (Model Context Protocol) server that connects Meta's WhatsApp Cloud API to ClickUp Brain via MCP Connect. Send WhatsApp messages and retain Meta delivery receipts for troubleshooting.

## WhatsApp tools

| Tool | Description |
|------|-------------|
| `send_text_message` | Send a free-form text to one recipient |
| `send_template_message` | Send an approved template to one recipient |
| `send_bulk_text_messages` | Send the same text to multiple recipients |
| `send_bulk_template_messages` | Send a template to multiple recipients |
| `send_media_message` | Send image, video, document, or audio |
| `get_message_templates` | List approved templates from your WABA |
| `check_phone_number_status` | Check phone number quality and status |

## Meta delivery webhooks

Railway runs `webhook_proxy.py`, which keeps the MCP endpoints and adds:

- `GET /webhook` for Meta verification
- `POST /webhook` for signed delivery/status callbacks
- `GET /webhook/status/{message_id}` for a retained receipt lookup

Set these Railway variables:

```text
WHATSAPP_WEBHOOK_VERIFY_TOKEN=<same value entered in Meta webhook settings>
WHATSAPP_APP_SECRET=<Meta app secret>
WHATSAPP_RECEIPTS_DB=/data/whatsapp_receipts.sqlite3
```

Attach the Meta `messages` webhook field to the WABA. For persistence across Railway restarts, mount a Railway volume at `/data`. The app rejects unsigned webhook callbacks unless `WEBHOOK_ALLOW_UNSIGNED=true` is explicitly set for local testing.

## Setup

1. In Meta for Developers, add the WhatsApp product and note the Phone Number ID and WABA ID.
2. Generate a permanent token with `whatsapp_business_messaging` and `whatsapp_business_management`.
3. Set the variables in `.env` or Railway.
4. Deploy with `python webhook_proxy.py`.
5. Configure Meta's callback URL as `https://<your-domain>/webhook` and subscribe to `messages`.

## Local run

```bash
pip install -r requirements.txt
python webhook_proxy.py
```

## ClickUp Brain connection

Point MCP Connect to the Railway service's SSE endpoint. The health endpoint is `/` and reports the running transport.

## License

MIT
