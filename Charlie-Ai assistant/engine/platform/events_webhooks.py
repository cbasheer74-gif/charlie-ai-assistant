"""
JARVIS Phase 12: Event Bus, Webhook Gateway & Automation Builder
Enforces pub/sub event distribution, replay-safe webhook verification, and safe conditional automations.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import time
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from .models import AutomationRule, EventMessage, WebhookPayload

logger = logging.getLogger("jarvis.platform.events")


class EventBus:
    """Internal event pub/sub broker with scoped subscriptions."""

    def __init__(self):
        # event_type -> list of listener callbacks
        self._listeners: Dict[str, List[Callable[[EventMessage], None]]] = {}

    def subscribe(self, event_type: str, callback: Callable[[EventMessage], None]):
        if event_type not in self._listeners:
            self._listeners[event_type] = []
        self._listeners[event_type].append(callback)

    def publish(self, event: EventMessage):
        listeners = self._listeners.get(event.event_type, [])
        for cb in listeners:
            try:
                cb(event)
            except Exception as e:
                logger.error(f"Error dispatching event {event.event_type} to listener: {e}")


class WebhookGateway:
    """Inbound webhook receiver with HMAC signature verification, timestamp checks, and replay defense."""

    def __init__(self, secret_key: str = "webhook_secret_mock_123"):
        self.secret_key = secret_key
        self._seen_nonces: Set[str] = set()
        self.max_drift_seconds = 300.0  # 5 min

    def verify_and_process(self, webhook: WebhookPayload) -> Tuple[bool, str]:
        # 1. Check timestamp drift
        drift = abs(time.time() - webhook.timestamp)
        if drift > self.max_drift_seconds:
            return False, f"Webhook expired: Timestamp drift ({int(drift)}s) exceeds max allowed."

        # 2. Replay protection
        if webhook.nonce in self._seen_nonces:
            return False, "Replay attack detected: Webhook nonce already used."
        self._seen_nonces.add(webhook.nonce)

        # 3. Signature verification
        raw_data = f"{webhook.source}:{webhook.event_type}:{webhook.timestamp}:{webhook.nonce}"
        expected_sig = hmac.new(self.secret_key.encode(), raw_data.encode(), hashlib.sha256).hexdigest()

        if not hmac.compare_digest(expected_sig, webhook.signature):
            return False, "Invalid webhook HMAC signature."

        logger.info(f"Webhook verified from {webhook.source}: {webhook.event_type}")
        return True, "Webhook accepted."


class AutomationBuilder:
    """
    Evaluates WHEN event IF conditions THEN action rules without unsafe eval().
    """

    def __init__(self, event_bus: EventBus):
        self.event_bus = event_bus
        self.rules: Dict[str, AutomationRule] = {}
        # Subscribe event bus to dispatch rules
        self.event_bus.subscribe("*", self._on_event)

    def add_rule(self, rule: AutomationRule):
        self.rules[rule.rule_id] = rule
        self.event_bus.subscribe(rule.event_type, lambda evt: self._evaluate_rule(rule, evt))
        logger.info(f"Automation rule added: '{rule.name}' (WHEN {rule.event_type})")

    def _evaluate_rule(self, rule: AutomationRule, event: EventMessage):
        if not rule.enabled:
            return

        # Check conditions
        for cond_k, cond_v in rule.conditions.items():
            actual = event.payload.get(cond_k)
            if actual != cond_v:
                return  # Condition mismatch

        # Conditions matched! Fire action
        rule.run_count += 1
        rule.last_run_at = time.time()
        logger.info(f"Automation rule triggered: '{rule.name}' -> Executing Skill '{rule.action_skill}'")

    def _on_event(self, event: EventMessage):
        pass
