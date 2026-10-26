"""Personal Telegram MCP server (userbot via Telethon).

Started by the MCP client (Claude Desktop / Claude Code / Cursor ...) over stdio.
Credentials come from config.json created by login.py.

IMPORTANT: stdout is the MCP protocol channel - never print() here, log to stderr.
"""

import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from telethon import TelegramClient, utils
from telethon.sessions import StringSession
from telethon.tl.types import User, Chat, Channel

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = Path(os.environ.get("TG_MCP_CONFIG", BASE_DIR / "config.json"))

logging.basicConfig(stream=sys.stderr, level=logging.WARNING,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("tg-mcp")


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        raise RuntimeError(f"{CONFIG_PATH} not found - run start.bat first to log in")
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


CONFIG = load_config()
READ_ONLY = bool(CONFIG.get("read_only", False))
# Optional allow-list of chats the agent may write to (usernames or ids). Empty = any chat.
SEND_ALLOWLIST = {str(x).lstrip("@").lower() for x in CONFIG.get("send_allowlist", [])}

mcp = FastMCP("telegram-personal")

_client: TelegramClient | None = None
_client_lock = asyncio.Lock()


async def get_client() -> TelegramClient:
    """Lazily connect once and reuse the connection."""
    global _client
    async with _client_lock:
        if _client is None:
            client = TelegramClient(
                StringSession(CONFIG["session"]),
                int(CONFIG["api_id"]),
                CONFIG["api_hash"],
                device_model="Personal MCP",
                app_version="1.0",
            )
            await client.connect()
            if not await client.is_user_authorized():
                await client.disconnect()
                raise RuntimeError("Session is not authorized (revoked?) - run start.bat again")
            # Fill the entity cache so numeric chat ids can be resolved.
            await client.get_dialogs(limit=None)
            _client = client
        return _client


async def resolve(chat: str):
    """Accepts @username, username, t.me link, phone, numeric id, 'me', or exact chat title."""
    client = await get_client()
    chat = str(chat).strip()
    if chat.lower() in ("me", "self", "saved", "избранное"):
        return await client.get_entity("me")
    try:
        if chat.lstrip("-").isdigit():
            return await client.get_entity(int(chat))
        return await client.get_entity(chat)
    except Exception:
        pass
    # Fallback: match by dialog title (case-insensitive, exact then substring).
    dialogs = await client.get_dialogs(limit=None)
    low = chat.lower()
    for d in dialogs:
        if (d.name or "").lower() == low:
            return d.entity
    matches = [d for d in dialogs if low in (d.name or "").lower()]
    if len(matches) == 1:
        return matches[0].entity
    if matches:
        names = ", ".join(f"{m.name} (id {m.id})" for m in matches[:10])
        raise ValueError(f"'{chat}' is ambiguous: {names}. Pass the id instead.")
    raise ValueError(f"Chat '{chat}' not found")


def entity_kind(e) -> str:
    if isinstance(e, User):
        return "bot" if e.bot else "user"
    if isinstance(e, Chat):
        return "group"
    if isinstance(e, Channel):
        return "channel" if e.broadcast else "supergroup"
    return "unknown"


def fmt_dt(dt: datetime | None) -> str | None:
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds") if dt else None


def fmt_message(m) -> dict:
    sender = m.sender
    out = {
        "id": m.id,
        "date": fmt_dt(m.date),
        "from": utils.get_display_name(sender) if sender else None,
        "from_id": m.sender_id,
        "out": m.out,
        "text": m.message or "",
    }
    if m.reply_to_msg_id:
        out["reply_to"] = m.reply_to_msg_id
    if m.media:
        out["media"] = type(m.media).__name__.replace("MessageMedia", "").lower()
        if m.file and m.file.name:
            out["file_name"] = m.file.name
    if m.fwd_from:
        out["forwarded"] = True
    return out


def check_can_send(entity):
    if READ_ONLY:
        raise PermissionError("Server is in read-only mode (read_only=true in config.json)")
    if not SEND_ALLOWLIST:
        return
    keys = {str(entity.id), str(utils.get_peer_id(entity))}
    if getattr(entity, "username", None):
        keys.add(entity.username.lower())
    if getattr(entity, "is_self", False):
        keys.add("me")
    if not keys & SEND_ALLOWLIST:
        raise PermissionError(f"Chat {utils.get_display_name(entity)} is not in send_allowlist")


# ---------------------------------------------------------------- read tools

@mcp.tool()
async def get_me() -> dict:
    """Info about the logged-in Telegram account."""
    client = await get_client()
    me = await client.get_me()
    return {"id": me.id, "name": utils.get_display_name(me), "username": me.username,
            "phone": me.phone, "read_only_mode": READ_ONLY}


@mcp.tool()
async def list_chats(limit: int = 30, unread_only: bool = False, archived: bool = False) -> list[dict]:
    """List recent chats (dialogs). Use the returned id or username as `chat` in other tools."""
    client = await get_client()
    result = []
    async for d in client.iter_dialogs(archived=archived):
        if unread_only and not d.unread_count:
            continue
        result.append({
            "id": d.id,
            "title": d.name,
            "type": entity_kind(d.entity),
            "username": getattr(d.entity, "username", None),
            "unread": d.unread_count,
            "last_message": (d.message.message or "")[:200] if d.message else None,
            "last_date": fmt_dt(d.date),
        })
        if len(result) >= limit:
            break
    return result


@mcp.tool()
async def get_messages(chat: str, limit: int = 30, offset_id: int = 0) -> list[dict]:
    """Read latest messages from a chat (newest first). Pass offset_id=<oldest id seen> to page back.
    `chat`: @username, id, phone, 'me' (Saved Messages) or chat title."""
    client = await get_client()
    entity = await resolve(chat)
    msgs = await client.get_messages(entity, limit=min(limit, 200), offset_id=offset_id)
    return [fmt_message(m) for m in msgs]


@mcp.tool()
async def search_messages(query: str, chat: str | None = None, limit: int = 30) -> list[dict]:
    """Search messages by text. With `chat` - inside that chat, without - across all chats."""
    client = await get_client()
    entity = await resolve(chat) if chat else None
    out = []
    async for m in client.iter_messages(entity, search=query, limit=min(limit, 200)):
        item = fmt_message(m)
        if entity is None:
            item["chat"] = utils.get_display_name(m.chat) if m.chat else None
            item["chat_id"] = m.chat_id
        out.append(item)
    return out


@mcp.tool()
async def get_chat_info(chat: str) -> dict:
    """Details about a user / group / channel."""
    client = await get_client()
    e = await resolve(chat)
    info = {"id": utils.get_peer_id(e), "title": utils.get_display_name(e),
            "type": entity_kind(e), "username": getattr(e, "username", None)}
    if isinstance(e, User):
        info.update(phone=e.phone, bot=e.bot, contact=e.contact)
    if isinstance(e, (Chat, Channel)):
        info["participants_count"] = getattr(e, "participants_count", None)
    return info


@mcp.tool()
async def mark_as_read(chat: str) -> str:
    """Mark all messages in a chat as read."""
    client = await get_client()
    await client.send_read_acknowledge(await resolve(chat))
    return "ok"


@mcp.tool()
async def download_media(chat: str, message_id: int) -> str:
    """Download a message's attachment to the downloads/ folder, returns the file path."""
    client = await get_client()
    entity = await resolve(chat)
    msg = await client.get_messages(entity, ids=message_id)
    if not msg or not msg.media:
        raise ValueError("Message has no media")
    target = BASE_DIR / "downloads"
    target.mkdir(exist_ok=True)
    path = await client.download_media(msg, file=str(target))
    return str(path)


# --------------------------------------------------------------- write tools

@mcp.tool()
async def send_message(chat: str, text: str, reply_to: int | None = None) -> dict:
    """Send a text message FROM THE USER'S ACCOUNT. Optional reply_to = message id."""
    client = await get_client()
    entity = await resolve(chat)
    check_can_send(entity)
    m = await client.send_message(entity, text, reply_to=reply_to)
    return {"sent": True, "id": m.id, "chat": utils.get_display_name(entity)}


@mcp.tool()
async def send_file(chat: str, path: str, caption: str = "") -> dict:
    """Send a local file (photo, document...) to a chat."""
    client = await get_client()
    entity = await resolve(chat)
    check_can_send(entity)
    if not Path(path).is_file():
        raise FileNotFoundError(path)
    m = await client.send_file(entity, path, caption=caption)
    return {"sent": True, "id": m.id}


@mcp.tool()
async def edit_message(chat: str, message_id: int, text: str) -> str:
    """Edit your own message."""
    client = await get_client()
    entity = await resolve(chat)
    check_can_send(entity)
    await client.edit_message(entity, message_id, text)
    return "ok"


@mcp.tool()
async def forward_message(from_chat: str, message_id: int, to_chat: str) -> str:
    """Forward a message to another chat."""
    client = await get_client()
    src, dst = await resolve(from_chat), await resolve(to_chat)
    check_can_send(dst)
    await client.forward_messages(dst, message_id, src)
    return "ok"


if __name__ == "__main__":
    mcp.run()  # stdio
