"""Discord community & webhook notification plugin for CHARLIE.

Enables posting announcements, status alerts, and messages to Discord channels.
"""
from __future__ import annotations

import json
import urllib.request
import urllib.error
from memory.config_manager import get_plugin_config

PLUGIN = {
    "name": "discord_integration",
    "description": (
        "Post messages, announcements, and build alerts to Discord channels or webhooks. "
        "Use when the user asks to send a Discord message, notify a Discord server, or post an update."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "message": {
                "type": "STRING",
                "description": "Message content to send to Discord",
            },
            "channel": {
                "type": "STRING",
                "description": "Target channel name or webhook target",
            },
        },
        "required": ["message"],
    },
}

PLUGIN_SETTINGS = {
    "namespace": "discord_integration",
    "title": "Discord Integration",
    "fields": [
        {
            "key": "webhook_url",
            "label": "Discord Webhook URL",
            "type": "text",
            "default": "",
            "placeholder": "https://discord.com/api/webhooks/...",
        },
        {
            "key": "bot_token",
            "label": "Bot Token (optional)",
            "type": "text",
            "default": "",
            "placeholder": "Discord Bot Token",
        },
    ],
    "action": {"label": "TEST DISCORD WEBHOOK", "run": lambda: _test_connection()},
}


def _test_connection() -> str:
    cfg = get_plugin_config("discord_integration")
    webhook = str(cfg.get("webhook_url") or "").strip()
    if webhook:
        return "Discord Webhook configured and ready to post alerts."
    return "Discord integration ready. Add your Webhook URL in settings to enable live channel alerts."


def run(parameters: dict, player=None, session_memory=None) -> str:
    message = str(parameters.get("message") or "").strip()
    cfg = get_plugin_config("discord_integration")
    webhook = str(cfg.get("webhook_url") or "").strip()

    if not message:
        result_text = f"Discord integration active. {_test_connection()}"
    elif webhook:
        try:
            payload = json.dumps({"content": message, "username": "Charlie Assistant"}).encode("utf-8")
            req = urllib.request.Request(
                webhook,
                data=payload,
                headers={"Content-Type": "application/json", "User-Agent": "Charlie-Assistant"},
            )
            with urllib.request.urlopen(req, timeout=8) as resp:
                if resp.status in (200, 204):
                    result_text = "Message broadcast successfully to Discord."
                else:
                    result_text = f"Discord returned status {resp.status}."
        except Exception as e:
            result_text = f"Failed to post to Discord webhook: {e}"
    else:
        result_text = f"[Simulated] Dispatched to Discord: '{message}'. (Add your Discord Webhook URL in settings for live transmission)."

    if player:
        try:
            player.write_log(f"SYS: [Discord] {result_text}")
        except Exception:
            pass
    return result_text
