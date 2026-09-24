"""Small, testable routing layer. No background training or automatic tool execution."""
from __future__ import annotations

from dataclasses import dataclass
import json
import re
import time
from decimal import Decimal, localcontext
from typing import Callable
from core.study_notes import study_reference, study_card


@dataclass(frozen=True)
class BrainReply:
    text: str
    provider: str
    task: str
    fallback: bool


class BrainInputError(ValueError):
    """Actionable input problem, not a provider outage."""


def task_kind(messages: list[dict[str, str]]) -> str:
    """Routing hint, not a claim to classify intent perfectly. Include follow-ups."""
    text = ' '.join(m.get('content', '') for m in messages[-5:]).lower()
    if re.search(r'\b(code|debug|python|javascript|sql|exception|traceback|algorithm)\b|```', text):
        return 'coding'
    if re.search(r'\b(project|homework|assignment|school|syllabus|class|experiment)\b|परियोजना|होमवर्क', text):
        return 'learning'
    if len(text) > 600 or re.search(r'\b(research|compare|analyse|analyze|plan|proof|calculate|design)\b', text):
        return 'reasoning'
    return 'conversation'


TASK_GUIDANCE = {
    'coding': 'State assumptions, provide a minimal workable solution and verification steps. Never claim tests ran unless tool results exist.',
    'learning': 'Adapt to the stated grade and rubric. Explain the concept, give an actionable draft, label sample observations and offer a short understanding check.',
    'reasoning': 'Identify constraints, distinguish evidence from assumptions, compare relevant options and give a justified recommendation with a verification step.',
    'conversation': 'Reply naturally and concisely. Be empathetic when appropriate; avoid forced jokes and unnecessary advice.',
}


def simple_arithmetic(text: str) -> str | None:
    """Only whole-message, two-number arithmetic; no eval or broad text parsing."""
    if len(text) > 150:
        return None
    match = re.fullmatch(
        r'\s*(?:(?:what is|calculate|compute)\s+)?'
        r'([+-]?\d{1,20}(?:\.\d{1,12})?)\s*'
        r'(\+|-|\*|×|/|÷|times|multiplied by|divided by|plus|minus)\s*'
        r'([+-]?\d{1,20}(?:\.\d{1,12})?)\s*[?=]?\s*', text, re.I)
    if not match:
        return None
    a_text, operation, b_text = match.groups()
    a, b = Decimal(a_text), Decimal(b_text)
    op = operation.lower()
    with localcontext() as context:
        context.prec = 70
        if op in ('+', 'plus'):
            value, symbol = a + b, '+'
        elif op in ('-', 'minus'):
            value, symbol = a - b, '-'
        elif op in ('*', '×', 'times', 'multiplied by'):
            value, symbol = a * b, '×'
        else:
            if b == 0:
                return 'Division by zero is undefined.'
            value, symbol = a / b, '÷'
        # For non-terminating division, do not label the rounded decimal exact.
        from decimal import Inexact
        relation = '≈' if context.flags[Inexact] else '='
        rendered = format(value, 'f')
        if '.' in rendered:
            rendered = rendered.rstrip('0').rstrip('.')
        return f'{a_text} {symbol} {b_text} {relation} {rendered}'


class HybridBrain:
    def __init__(self, mode: str = 'hybrid', *, local: Callable | None = None,
                 cloud: Callable | None = None, clock: Callable = time.monotonic):
        if mode not in {'hybrid', 'local_only'}:
            raise ValueError('Brain mode must be hybrid or local_only')
        self.mode = mode
        self._local = local or self._local_generate
        self._cloud = cloud or self._cloud_generate
        self._clock = clock
        self._cooldown: dict[str, float] = {}
        self.last_reply: BrainReply | None = None

    @classmethod
    def configured(cls):
        # Separate non-secret settings file. Invalid configuration fails closed.
        from core.llm_client import BASE_DIR
        path = BASE_DIR / 'config' / 'brain.json'
        if not path.exists():
            return cls('hybrid')
        try:
            mode = json.loads(path.read_text(encoding='utf-8')).get('mode', 'hybrid')
            return cls(mode)
        except (OSError, ValueError, TypeError, AttributeError):
            return cls('hybrid')

    def generate(self, system: str, messages: list[dict[str, str]]) -> str:
        self.last_reply = None
        if messages and messages[-1].get('role') == 'user':
            calculated = simple_arithmetic(messages[-1].get('content', ''))
            if calculated is not None:
                self.last_reply = BrainReply(calculated, 'calculator', 'arithmetic', False)
                return calculated
        card = study_card(messages)
        if card is not None:
            self.last_reply = BrainReply(card, 'study_card', 'learning', False)
            return card
        task = task_kind(messages)
        enriched = system + '\n[TASK GUIDANCE]\n' + TASK_GUIDANCE[task] + study_reference(messages)
        order = ['local'] if self.mode == 'local_only' else (
            ['local', 'cloud'] if task == 'conversation' else ['cloud', 'local'])
        for index, provider in enumerate(order):
            if self._clock() < self._cooldown.get(provider, 0):
                continue
            try:
                adapter = self._local if provider == 'local' else self._cloud
                text = str(adapter(enriched, messages) or '').strip()
                if not text:
                    raise ValueError('Empty response')
            except BrainInputError:
                raise
            except Exception:
                # Never expose provider payloads/URLs/keys in chat or telemetry.
                self._cooldown[provider] = self._clock() + 30
                continue
            self.last_reply = BrainReply(text, provider, task, index > 0)
            return text
        scope = 'local AI model' if self.mode == 'local_only' else 'configured AI models'
        raise RuntimeError(f"I couldn't reach the {scope}. Check the configuration and try again in 30 seconds. Your conversation has not been cleared.")

    @staticmethod
    def _local_generate(system, messages):
        from core.llm_client import call_llm, get_llm_settings
        _, model = get_llm_settings()
        # Verified on installed Qwen 3.5: reasoning-only output was exhausting
        # short CPU requests before a final answer. Other models keep defaults.
        think = False if model.lower().split(':')[0] == 'qwen3.5' else None
        # Bound CPU context without silently cutting the current question/file.
        if not messages:
            raise BrainInputError('Please enter a question.')
        if len(system) + len(messages[-1].get('content', '')) > 10000:
            raise BrainInputError('Local input is too long; use a shorter question or file excerpt.')
        kept = [dict(m) for m in messages]
        while len(kept) > 1 and len(system) + sum(len(m.get('content', '')) for m in kept) > 10000:
            kept.pop(0)
        while len(kept) > 1 and kept[0].get('role') != 'user':
            kept.pop(0)
        result = call_llm([{'role': 'system', 'content': system}] + kept,
                          timeout=45, max_tokens=384, local_only=True,
                          restart_on_failure=False, think=think)
        return result.get('content', '')

    @staticmethod
    def _cloud_generate(system, messages):
        from core.gemini import chat_text
        return chat_text(messages, system=system, timeout_ms=45_000)
