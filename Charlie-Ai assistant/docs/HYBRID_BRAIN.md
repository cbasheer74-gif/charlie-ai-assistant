# Hybrid brain foundation

AI Chat uses `engine.hybrid_brain.HybridBrain`. This is model orchestration,
not fine-tuning or human-like consciousness. No new provider has been purchased.

## Current setting

`config/brain.json`: `{"mode": "local_only"}`. Missing or invalid settings also
default to local-only. Settings are loaded when a chat assistant is constructed;
restart the source app after changing them.

- Local-only uses the configured loopback Ollama/OpenAI-compatible endpoint.
- Remote endpoint URLs and HTTP redirects are blocked in this path.
- Failure does not invoke Gemini or start/restart services automatically.
- A locally hosted proxy could itself use cloud services: configure a genuine
  local model for offline operation.
- **Voice mode and other tools are unchanged and may still use cloud services.**

Optional `hybrid` mode uses local-first for conversation and the already configured
Gemini provider first for coding, projects and complex tasks. This is a heuristic,
not an accuracy guarantee. Do not enable it before agreeing on provider costs and
privacy. No currency spending cap is implemented in this first phase.

Each chat session retains a 30-second provider failure cooldown. Local requests
use a 45-second network read timeout, cloud calls request a 45-second timeout;
these are not hard whole-turn deadlines (SDK/setup overhead can add time).
Successful route metadata is available through `assistant.brain.last_reply`.
No prompts or responses are written to new telemetry files.

For the locally installed Qwen 3.5 model, chat requests use `think: false`:
the CPU test with thinking exhausted its small output budget without answering;
the non-thinking arithmetic test returned `96` in 2.59 seconds. This narrow test
is not a reasoning-quality benchmark. A subsequent routed model call answered
the same arithmetic incorrectly. A whole-message, two-number decimal calculator
now handles supported arithmetic without using any model; other math still needs
model/tool evaluation. Other model families retain their defaults.
Reference: https://docs.ollama.com/capabilities/thinking

Profile changes clear in-memory chat context. A reply finishing after a profile
switch is discarded. This is a context guard, not authentication/access control.

## Verification

Run `python -m unittest tests.test_hybrid_brain tests.test_pro_chat tests.test_assistant_guidance`.
These tests use fake providers; passing them does not certify model answer quality.

Before packaging, require a real local generation test and small task evaluation
(arithmetic, school project, debugging, uncertainty, emotional support). Then add
retrieval with citations, tool execution/verification and model quality evaluation.
Packaged EXE is not updated by source edits; rebuilding is a separate step.

## Checkpoint: 2026-09-23

- 17 focused unit tests passed; source modules compile.
- Installed local model: qwen3.5:2b; Ollama reported zero VRAM allocation.
- Model-only arithmetic failed one trial; deterministic arithmetic passed.
- A short-system-prompt school-science trial completed in 12.52 seconds but
  included factual errors and unsuitable experiment advice. This was an adapter
  test, not an end-to-end evaluation with the full application system prompt.
- Quality gate: NOT release-ready. Do not treat prompt instructions as proven
  safety or accuracy. The packaged EXE has not been replaced.
- Full application chat prompt was also tested in local-only mode; it did not
  produce an answer within the local request limit. No cloud fallback occurred.
- Next: improve local model/grounding and prompt runtime, then test
  representative tasks before deployment. No paid API enabled.

## Next-pass results

- Local-only chat now uses a compact system prompt (measured 1,568 characters
  versus 7,900 before), preserving gender grammar and core safety guidance.
  Detailed personal-hub context is not loaded into this compact prompt.
- Local requests keep at most 10,000 system+message characters, dropping oldest
  turns without mutating stored history. Oversized current questions/file excerpts
  return an actionable error rather than silently cutting them or calling cloud.
  Character bounds are not exact tokenizer limits.
- Local response cap is 384 tokens; long replies should be continued in stages.
- Full source chat returned in 32.26 seconds with compact instructions and study
  notes, below the new 45-second timeout. Its science paraphrase was still flawed;
  this is NOT evidence of general accuracy or of meeting the former 30s deadline.
- Two authored English study cards (evaporation, photosynthesis) serve narrowly
  matched explanation requests directly and label their origin. Other topics,
  languages and customised assignments still use the model. These are not a RAG
  textbook library or trained knowledge expansion.
- Real ProChatAssistant evaporation-card test completed in 0.016 seconds, without
  inference. Do not report this as model generation speed.
- 22 focused tests passed. Packaged EXE unchanged; broader model quality remains
  below the release gate.
