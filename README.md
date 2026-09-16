# WhatsApp MCP Server — Meta Cloud API

An MCP (Model Context Protocol) server that connects Meta's WhatsApp Cloud API to ClickUp Brain via MCP Connect. Send bulk WhatsApp messages, template messages, and media directly from ClickUp.

## Tools

| Tool | Description |
|------|-------------|
| `send_text_message` | Send a free-form text to one recipient |
| `send_template_message` | Send an approved template to one recipient |
| `send_bulk_text_messages` | Send the same text to multiple recipients |
| `send_bulk_template_messages` | Send a template to multiple recipients (with per-recipient personalisation) |
| `send_media_message` | Send image, video, document, or audio |
| `get_message_templates` | List approved templates from your WABA |
| `check_phone_number_status` | Check phone number quality and status |

## Setup

### 1. Meta Business Prerequisites

1. Go to [Meta for Developers](https://developers.facebook.com/) and create an app (type: Business).
2. Add the **WhatsApp** product.
3. In WhatsApp > API Setup, note your:
   - **Phone Number ID**
   - **WhatsApp Business Account ID**
4. Generate a **Permanent Access Token** (System User > Generate Token with `whatsapp_business_messaging` and `whatsapp_business_management` permissions).

### 2. Environment Variables

Copy `.env.example` to `.env` and fill in your credentials:

```bash
cp .env.example .env
```

### 3. Install & Run

```bash
pip install -r requirements.txt
python server.py
```

### 4. Connect to ClickUp Brain

1. In ClickUp, go to **Settings > Brain > MCP Connect**.
2. Add a new MCP server connection.
3. Point it to this server (stdio transport).

### 5. Deploy (Recommended)

For always-on access, deploy to [Railway](https://railway.app), [Render](https://render.com), or any cloud provider:

```bash
# Railway one-click
railway init
railway up
```

## Usage Examples

**Bulk text to a list:**
> "Send 'Your order is confirmed!' to +201090840870 and +201234567890"

**Template with personalisation:**
> "Send the 'order_update' template to these 5 numbers, each with their order ID"

**Media message:**
> "Send this PDF to +201090840870 via WhatsApp"

## License

MIT
