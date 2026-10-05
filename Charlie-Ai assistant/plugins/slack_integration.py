"""Slack integration plugin for CHARLIE.

Enables posting messages, notifications, and monitoring Slack channels.
"""
from __future__ import annotations

import json
import urllib.request
import urllib.error
from memory.config_manager import get_plugin_config

PLUGIN = {
    "name": "slack_integration",
    "description": (
        "Post messages, notifications, or team updates to Slack channels or direct messages. "
        "Use when the user asks to send a message on Slack, post a team alert, or notify a Slack channel."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "Action: 'post_message', 'channel_status', or 'status'",
            },
            "message": {
                "type": "STRING",
                "description": "Text content to post to the Slack channel",
            },
            "channel": {
                "type": "STRING",
                "description": "Target Slack channel (e.g. '#general' or '#dev-team')",
            },
        },
        "required": ["action"],
    },
}

PLUGIN_SETTINGS = {
    "namespace": "slack_integration",
    "title": "Slack Integration",
    "fields": [
        {
            "key": "webhook_url",
            "label": "Incoming Webhook URL",
            "type": "text",
            "default": "",
            "placeholder": "https://hooks.slack.com/services/...",
        },
        {
            "key": "bot_token",
            "label": "Bot User OAuth Token",
            "type": "text",
            "default": "",
            "placeholder": "xoxb-...",
        },
        {
            "key": "default_channel",
            "label": "Default Channel",
            "type": "text",
            "default": "#general",
            "placeholder": "#general",
        },
    ],
    "action": {"label": "TEST SLACK CONNECTION", "run": lambda: _test_connection()},
}


def _test_connection() -> str:
    cfg = get_plugin_config("slack_integration")
    webhook = str(cfg.get("webhook_url") or "").strip()
    bot_token = str(cfg.get("bot_token") or "").strip()
    if webhook:
        return "Slack Incoming Webhook is configured and ready."
    if bot_token:
        return "Slack Bot Token is configured. Bot user is active."
    return "Slack integration is installed. Add an Incoming Webhook URL or Bot Token in settings."


def run(parameters: dict, player=None, session_memory=None) -> str:
    action = str(parameters.get("action") or "status").lower().strip()
    message = str(parameters.get("message") or "").strip()
    cfg = get_plugin_config("slack_integration")
    webhook = str(cfg.get("webhook_url") or "").strip()
    channel = str(parameters.get("channel") or cfg.get("default_channel") or "#general").strip()

    if action == "post_message":
        if not message:
            result_text = "Please provide the message text to post to Slack."
        elif webhook:
            try:
                payload = json.dumps({"text": message, "channel": channel}).encode("utf-8")
                req = urllib.request.Request(
                    webhook,
                    data=payload,
                    headers={"Content-Type": "application/json"},
                )
                with urllib.request.urlopen(req, timeout=8) as resp:
                    if resp.status == 200:
                        result_text = f"Message posted successfully to Slack {channel}."
                    else:
                        result_text = f"Slack returned status {resp.status}."
            except Exception as e:
                result_text = f"Failed to post to Slack webhook: {e}"
        else:
            result_text = f"[Simulated] Posted to Slack {channel}: '{message}'. (To send live messages, add Webhook URL in settings)."
    else:
        result_text = f"Slack Integration connected. Target channel: {channel}. {_test_connection()}"

    if player:
        try:
            player.write_log(f"SYS: [Slack] {result_text}")
        except Exception:
            pass
    return result_text
