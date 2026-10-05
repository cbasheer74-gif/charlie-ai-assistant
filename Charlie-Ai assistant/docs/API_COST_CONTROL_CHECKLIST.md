# API Cost Control Checklist — Detailed Edition

## 1. Spending Limits & Alerts
- Set monthly hard cap on provider dashboards (OpenAI, Gemini, Stripe, Twilio).
- Alerts enabled: 50%, 80%, 100%.
- Daily spend alert threshold active.

## 2. Response Caching
- Cache repetitive queries (Redis / in-memory cache).
- Implement cache-aside pattern.
- Target ≥60% cache hit rate.
- Avoid caching dynamic tokens / sensitive PII.

## 3. Key Storage & Rotation
- Store keys in `.env` / Secrets Manager.
- Ensure `.env` in `.gitignore`.
- Rotate API keys every 30–60 days.
- Audit repo with `gitleaks` / `trufflehog`.

## 4. Optimization & Governance
- Prefer cost-efficient model tiers (`gemini-flash` / `gpt-4o-mini`).
- Circuit breaker on repeated API failure loops.
- Rate limit per-client requests.
