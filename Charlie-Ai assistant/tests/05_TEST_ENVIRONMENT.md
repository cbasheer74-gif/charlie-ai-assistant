# 05 — Test Environment

Test isolation rules, database strategies, environment variables, and mock requirements.

---

## 1. Local & Test Execution Environment
- **Python Version:** Python 3.10+ (compatible with Python 3.10 through 3.14).
- **Execution Command:** `python -m unittest discover tests` or `pytest tests/`.
- **Working Directory:** `Charlie-Ai assistant/`.

---

## 2. Database Isolation Strategy
- **Production DB:** `charlie_licensing.db` or PostgreSQL URI specified in `CHARLIE_DB_URL`. **MUST NOT BE USED BY TESTS.**
- **Test Database:**
  - Automated tests must run against ephemeral in-memory SQLite: `sqlite:///:memory:`.
  - In test fixtures, initialize schema using `Base.metadata.create_all(bind=test_engine)` and tear down with `Base.metadata.drop_all(bind=test_engine)`.

---

## 3. Required Test Environment Variables
Before running tests, ensure the following environment variables are set (or defaults used):
```bash
CHARLIE_ENV=test
CHARLIE_DB_URL=sqlite:///:memory:
CHARLIE_JWT_SECRET=test_static_jwt_secret_for_unit_tests_only
JARVIS_LOGIN_RATE_LIMIT=1000
JARVIS_ACTIVATION_RATE_LIMIT=1000
JARVIS_TRANSFER_RATE_LIMIT=1000
```

---

## 4. Mocked & Sandboxed Services
- **Razorpay API:** Mock `razorpay.Client` instance and webhook HMAC verification using test keys.
- **Gemini Live / REST API:** Mock HTTP/gRPC client responses using offline fixtures. Live requests must be intercepted to avoid quota depletion.
- **Local Ollama Server:** Mock `requests.get("http://localhost:11434/api/tags")` and chat generation endpoints.
- **Subprocess Calls:** `subprocess.Popen` for `ollama serve` and browser automation must be mocked during unit tests.

---

## 5. Production Resources That MUST NOT Be Used
- Live Razorpay merchant credentials (`rzp_live_*`).
- Production Google Gemini API keys with active billing.
- Production RSA private keys in live deployments.
- Live customer database files or user tables.

---

## 6. Test Cleanup Requirements
- Temporary test directories (e.g., test checkpoints, test audit files, test crash history) must be cleaned up in test `tearDown()` methods using `shutil.rmtree` or `tempfile.TemporaryDirectory`.
