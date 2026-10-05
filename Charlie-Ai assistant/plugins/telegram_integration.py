"""Telegram bot integration plugin for CHARLIE.

Enables sending automated notifications, reports, and voice briefs via Telegram.
"""
from __future__ import annotations

import json
import urllib.request
import urllib.error
from memory.config_manager import get_plugin_config

PLUGIN = {
    "name": "telegram_integration",
    "description": (
        "Send messages, reports, reminders, or alert notifications to Telegram chats or channels. "
        "Use when the user asks to send a Telegram message, ping a Telegram chat, or forward updates."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "message": {
                "type": "STRING",
                "description": "Text message to send to Telegram",
            },
            "chat_id": {
                "type": "STRING",
                "description": "Telegram chat or channel ID (e.g. '@mychannel' or numeric ID)",
            },
        },
        "required": ["message"],
    },
}

PLUGIN_SETTINGS = {
    "namespace": "telegram_integration",
    "title": "Telegram Bot Integration",
    "fields": [
        {
            "key": "bot_token",
            "label": "Telegram Bot Token",
            "type": "text",
            "default": "",
            "placeholder": "123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ",
        },
        {
            "key": "default_chat_id",
            "label": "Default Chat / Channel ID",
            "type": "text",
            "default": "",
            "placeholder": "@channel or user ID",
        },
    ],
    "action": {"label": "TEST TELEGRAM BOT", "run": lambda: _test_connection()},
}


def _test_connection() -> str:
    cfg = get_plugin_config("telegram_integration")
    token = str(cfg.get("bot_token") or "").strip()
    if not token:
        return "Telegram plugin is installed. Configure your Bot Token in settings."
    try:
        url = f"https://api.telegram.org/bot{token}/getMe"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode())
            if data.get("ok"):
                username = data["result"].get("username", "bot")
                return f"Connected to Telegram Bot @{username}."
            return "Telegram API returned non-OK status."
    except Exception as e:
        return f"Telegram test failed: {e}"


def run(parameters: dict, player=None, session_memory=None) -> str:
    message = str(parameters.get("message") or "").strip()
    cfg = get_plugin_config("telegram_integration")
    token = str(cfg.get("bot_token") or "").strip()
    chat_id = str(parameters.get("chat_id") or cfg.get("default_chat_id") or "").strip()

    if not message:
        result_text = f"Telegram integration ready. {_test_connection()}"
    elif token and chat_id:
        try:
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            payload = json.dumps({"chat_id": chat_id, "text": message}).encode("utf-8")
            req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode())
                if data.get("ok"):
                    result_text = f"Message delivered to Telegram chat {chat_id}."
                else:
                    result_text = f"Telegram delivery error: {data.get('description')}"
        except Exception as e:
            result_text = f"Failed to send to Telegram: {e}"
    else:
        result_text = f"[Simulated] Dispatched message to Telegram ({chat_id or 'default'}): '{message}'. (Add Bot Token in settings for live transmission)."

    if player:
        try:
            player.write_log(f"SYS: [Telegram] {result_text}")
        except Exception:
            pass
    return result_text
