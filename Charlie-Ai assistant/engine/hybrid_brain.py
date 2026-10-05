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
    if re.search(r'\b(open camera|camera scan|scan this|analyze this thing|camera se|dekho ye kya hai|identify object|ocr scan)\b', text):
        return 'vision_scan'
    if re.search(r'\b(cybersecurity|firewall|network diagnostic|ip address|port scan|traceroute|ping|dns leak|phishing|hardening|ssl cert)\b', text):
        return 'cybersecurity'
    if re.search(r'\b(finance|tax|gst|income tax|invoice|budgeting|expense|investment portfolio|balance sheet|accounting)\b', text):
        return 'finance'
    if re.search(r'\b(mock interview|interview prep|viva|job interview|technical interview|behavioral questions|star method)\b', text):
        return 'interview'
    if re.search(r'\b(smart home|iot|home assistant|mqtt|matter|zigbee|smart bulb|smart plug|home automation)\b', text):
        return 'iot'
    if re.search(r'\b(database|postgres|sqlite|mysql|sql query|indexing|explain analyze|acid transaction|normalization)\b', text):
        return 'database'
    if re.search(r'\b(docker|kubernetes|k8s|devops|ci/cd|github actions|terraform|containerization|deployment pipeline)\b', text):
        return 'devops'
    if re.search(r'\b(machine learning|data science|pandas|numpy|scikit-learn|pytorch|neural network|classification model|regression model)\b', text):
        return 'ml_data'
    if re.search(r'\b(api design|rest api|graphql|grpc|oauth2|jwt token|rate limit|idempotency)\b', text):
        return 'api_design'
    if re.search(r'\b(sysadmin|linux kernel|systemd|cron job|bash script|powershell|process memory|disk io)\b', text):
        return 'sysadmin'
    if re.search(r'\b(frontend|react|vue|svelte|css grid|flexbox|core web vitals|dom rendering|tailwind)\b', text):
        return 'frontend'
    if re.search(r'\b(mobile app|flutter|react native|ios swift|android kotlin|app store submission)\b', text):
        return 'mobile'
    if re.search(r'\b(probability|statistics|hypothesis test|p-value|linear algebra|calculus|bayes theorem|matrix eigenvalue)\b', text):
        return 'math_stats'
    if re.search(r'\b(contract review|nda agreement|terms of service|legal clause|intellectual property assignment|gdpr compliance)\b', text):
        return 'legal'
    if re.search(r'\b(ergonomics|desk posture|repetitive strain|hydration|sleep hygiene|workout routine|nutrition macro)\b', text):
        return 'fitness'
    if re.search(r'\b(creative writing|storytelling|character arc|public speaking|speech hook|presentation deck)\b', text):
        return 'creative'
    if re.search(r'\b(agile|scrum|kanban|sprint planning|backlog grooming|user story|burndown chart)\b', text):
        return 'agile'
    if re.search(r'\b(code review|bug audit|security audit|vulnerability|root cause|reproduce error|crash analysis)\b', text):
        return 'audit'
    if re.search(r'\b(code|debug|python|javascript|sql|exception|traceback|algorithm)\b|```', text):
        return 'coding'
    if re.search(r'\b(meeting|minutes|agenda|action items|attendees|decisions made|meeting notes|debrief)\b', text):
        return 'meeting'
    if re.search(r'\b(email|memo|formal letter|announcement|client proposal|pitch|status report)\b', text):
        return 'corporate'
    if re.search(r'\b(sexual health|contraception|reproductive|biology|anatomy|wellness|sti|puberty|healthy boundaries)\b', text):
        return 'wellness'
    if re.search(r'\b(project|homework|assignment|school|syllabus|class|experiment)\b|परियोजना|होमवर्क', text):
        return 'learning'
    if len(text) > 600 or re.search(r'\b(research|compare|analyse|analyze|plan|proof|calculate|design)\b', text):
        return 'reasoning'
    return 'conversation'


TASK_GUIDANCE = {
    'vision_scan': 'Trigger camera scan, read all text via OCR, identify object brand/model, explain its purpose, and provide step-by-step operating instructions in the user language.',
    'cybersecurity': 'Provide defensive network triage, hardening guidelines, and diagnostic steps. Never suggest or aid offensive exploitation or unauthorized access.',
    'finance': 'Provide clear structured financial calculations, budget allocations, or tax concepts with a professional CPA/advisor disclaimer.',
    'interview': 'Conduct an interactive interview simulation. Ask one targeted question at a time, critique technical depth and delivery poise, and suggest concrete STAR-method improvements.',
    'iot': 'Guide smart home setup, device pairing, network segmentation, and automation routines with emphasis on local-first control.',
    'database': 'Design performant schemas, optimize queries with EXPLAIN plans, recommend proper indexes, and enforce ACID guarantees.',
    'devops': 'Deliver reliable Docker/Kubernetes configurations, automated CI/CD pipeline steps, and infrastructure-as-code manifests.',
    'ml_data': 'Perform methodical data cleaning, proper feature engineering, cross-validation splits, and rigorous metric evaluations.',
    'api_design': 'Structure clean RESTful/gRPC contracts, idempotent endpoints, resilient auth flows, and graceful error envelopes.',
    'sysadmin': 'Provide safe OS administration commands, process triage, resource profiling, and resilient automation scripts.',
    'frontend': 'Deliver accessible, semantic markup, reactive component architecture, smooth CSS layouts, and fast Core Web Vitals.',
    'mobile': 'Architect cross-platform and native mobile apps with state management, offline storage, and responsive screen layouts.',
    'math_stats': 'Provide clear step-by-step mathematical derivations, formula breakdowns, and correct statistical interpretations.',
    'legal': 'Explain legal clauses and contract terms with clarity and nuance; include non-attorney legal information disclaimer.',
    'fitness': 'Provide evidence-based ergonomic, nutrition, and wellness guidelines with standard medical disclaimer.',
    'creative': 'Craft compelling narrative hooks, resonant character dynamics, and structured speeches that captivate audiences.',
    'agile': 'Facilitate productive agile ceremonies, backlog slicing, realistic estimations, and effective team delivery rhythms.',
    'coding': 'State assumptions, provide a minimal workable solution and verification steps. Never claim tests ran unless tool results exist.',
    'audit': 'Isolate Root Cause, assess blast radius, provide exact runnable patch, and outline regression verification steps.',
    'meeting': 'Provide an Executive Summary, Key Decisions, and explicit Action Items with Owners and Deadlines.',
    'corporate': 'Use Bottom Line Up Front (BLUF), descriptive subject, bulleted reasoning, and an unambiguous Call to Action.',
    'wellness': 'Provide factual, clinical, objective health/biology information with healthcare consultation disclaimer; enforce respectful non-vulgar boundaries.',
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
        from engine.brain_booster import get_brain_cache, compress_context_messages
        booster_cache = get_brain_cache()
        user_query = messages[-1].get('content', '').strip() if messages else ''
        cached_reply = booster_cache.get(user_query, task) if task != 'conversation' else None
        if cached_reply:
            self.last_reply = BrainReply(cached_reply, 'booster_cache', task, False)
            return cached_reply
        compressed_msgs = compress_context_messages(messages)
        from engine.episodic_recall import EpisodicRecallEngine
        from engine.reflective_critic import ReflectiveCritic
        episodic_block = EpisodicRecallEngine().format_recall_prompt(user_query) if user_query else ""
        enriched = system + '\n[TASK GUIDANCE]\n' + TASK_GUIDANCE[task] + study_reference(messages) + episodic_block
        order = ['local'] if self.mode == 'local_only' else (
            ['local', 'cloud'] if task == 'conversation' else ['cloud', 'local'])
        for index, provider in enumerate(order):
            if self._clock() < self._cooldown.get(provider, 0):
                continue
            try:
                adapter = self._local if provider == 'local' else self._cloud
                text = str(adapter(enriched, compressed_msgs) or '').strip()
                if not text:
                    raise ValueError('Empty response')
            except BrainInputError:
                if self.mode != 'local_only' and 'cloud' in order[index + 1:]:
                    continue
                raise
            except Exception:
                # Never expose provider payloads/URLs/keys in chat or telemetry.
                self._cooldown[provider] = self._clock() + 30
                continue
            # Self-Reflective Critic validation & auto-correction
            text = ReflectiveCritic.reflect_and_refine(user_query, text, task)
            if user_query and len(text) > 5 and task != 'conversation':
                booster_cache.put(user_query, text, task)
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
        user_content = messages[-1].get('content', '')
        if len(system) + len(user_content) > 10000:
            allowed_system = max(300, 10000 - len(user_content))
            system = system[:allowed_system]
            if len(system) + len(user_content) > 10000:
                raise BrainInputError('Local input is too long; use a shorter question or file excerpt.')
        kept = [dict(m) for m in messages]
        while len(kept) > 1 and len(system) + sum(len(m.get('content', '')) for m in kept) > 10000:
            kept.pop(0)
        while len(kept) > 1 and kept[0].get('role') != 'user':
            kept.pop(0)
        # Try direct Ollama runtime if running locally
        try:
            from engine.ai.ollama_provider import get_ollama_provider
            ollama = get_ollama_provider()
            if ollama.is_available():
                return ollama.generate(system_prompt=system, messages=kept)
        except Exception:
            pass

        result = call_llm([{'role': 'system', 'content': system}] + kept,
                          timeout=45, max_tokens=384, local_only=True,
                          restart_on_failure=False, think=think)
        return result.get('content', '')


    @staticmethod
    def _cloud_generate(system, messages):
        # Allow optional manual cloud provider selection without altering Gemini default
        configured_provider = "gemini"
        try:
            from memory.config_manager import load_api_keys
            configured_provider = str(load_api_keys().get("cloud_provider") or "gemini").lower()
        except Exception:
            pass

        if configured_provider == "groq":
            try:
                from core.groq_client import chat_text as groq_chat
                groq_reply = groq_chat(messages, system=system, timeout_ms=45_000)
                if groq_reply and str(groq_reply).strip():
                    return str(groq_reply).strip()
            except Exception:
                pass

        # Primary default: Gemini
        gemini_reply = ""
        try:
            from core.gemini import chat_text as gemini_chat
            gemini_reply = gemini_chat(messages, system=system, timeout_ms=45_000)
            if gemini_reply and str(gemini_reply).strip():
                return str(gemini_reply).strip()
        except Exception:
            pass

        # Optional fallback: If Gemini failed and cloud_provider is not groq, try Groq fallback if configured
        if configured_provider != "groq":
            try:
                from core.groq_client import chat_text as groq_chat, is_configured as is_groq_ready
                if is_groq_ready():
                    groq_reply = groq_chat(messages, system=system, timeout_ms=45_000)
                    if groq_reply and str(groq_reply).strip():
                        return str(groq_reply).strip()
            except Exception:
                pass

        return str(gemini_reply or "").strip()
