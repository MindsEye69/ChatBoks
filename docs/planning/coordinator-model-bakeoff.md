# Coordinator Model Bakeoff

Last reviewed: 2026-06-15

Status: planning note with offline fixture validation. This document defines the evaluation plan for local Coordinator models. It does not change `config.yaml`, install models, run Ollama, or alter routing behavior.

Source intake: Paper Sleuth daily research, `C:\Users\MindsEye\Documents\Paper Sleuth\research\chatboks_ideas.md`.

## Goal

Pick a local Coordinator model that is reliable for low-authority ChatBoks work:

- Routing suggestions.
- Compact resume summaries.
- Next diagnostic steps.
- Security and privacy warning classification.
- Diff summaries.
- Escalation recommendations.

The Coordinator should stay local, cheap, fast, and tool-less. It should improve clarity without pretending to be an implementation agent.

## Current Baseline

`config.yaml` currently defines the Coordinator as:

| Field | Current value |
|---|---|
| Runtime | `ollama` |
| Endpoint | `http://127.0.0.1:11434/api/chat` |
| Model | `gemma3:4b` |
| Temperature | `0.1` |
| Max prompt chars | `8000` |
| Predict cap | `512` |
| Token limit | `32000` |
| Main-seat fallback | `can_fill_main_seat: true` |

This is the control model for the first bakeoff.

## Candidate Models

Start with models that can run locally through Ollama or an equivalent local adapter.

| Candidate | Source reason | Initial status |
|---|---|---|
| `gemma3:4b` | Current Coordinator baseline | Required control |
| Gemma 4 E4B QAT | Paper Sleuth candidate for better accuracy, latency, and memory tradeoff | Research before install |
| DiffusionGemma 26B A4B IT | Google experimental text-diffusion Gemma 4 MoE; claims up to 4x faster generation on dedicated GPUs | Not tested; likely needs vLLM or Hugging Face serving, not ordinary Ollama |
| Small Qwen instruct model | Useful fallback if Gemma struggles with routing or summaries | Optional |
| Small Llama instruct model | Useful sanity check against a different model family | Optional |

Do not add cloud models to this bakeoff. Cloud fallback has separate consent and trust requirements in `chatboks-trust-contract.md`.

## Evaluation Tasks

Each candidate should answer the same fixed prompts with the same context budget. The harness should record raw output, timing, response length, and a small human-readable score.

| Task | What it tests | Expected Coordinator behavior |
|---|---|---|
| Route decision | Can it pick a sensible ChatBoks mode or direct agent? | Names a route and gives one short reason. |
| Compact resume summary | Can it preserve state without noise? | Keeps decisions, blockers, next action, and verification evidence. |
| Next diagnostic step | Can it avoid broad thrashing? | Suggests one concrete next check and why. |
| Security warning classification | Can it notice trust boundaries? | Flags secrets, cross-project context, public bridge exposure, or cloud sharing risk. |
| Diff summary | Can it summarize implementation changes? | Names behavior changed, files touched, tests run, and residual risk. |
| Mobile remote readability | Can it distinguish agent answers from system noise? | Recommends hiding system/bridge output unless requested. |
| Exhausted-agent fallback | Can it reason about live lanes? | Recommends replacing unavailable agents with eligible fill-ins. |

## Prompt Suite

The first suite is stored as JSON fixtures under `tests/fixtures/coordinator_bakeoff/`. Each prompt includes:

- `id`: stable fixture name.
- `task`: one sentence.
- `context`: compact transcript, state, diff, or config excerpt.
- `expected`: scoring hints, not a golden prose answer.
- `tags`: searchable topic labels.

Fixture IDs:

- `route_remote_polish`
- `resume_after_sleep`
- `diagnose_pairing_failure`
- `classify_public_bridge_risk`
- `summarize_mobile_refresh_diff`
- `separate_agent_answer_from_system_noise`
- `replace_exhausted_claude_lane`

## Scoring Rubric

Score each response from 0 to 3 in five dimensions.

| Dimension | 0 | 1 | 2 | 3 |
|---|---|---|---|---|
| Correctness | Wrong or unsafe | Partly relevant | Mostly right | Right and specific |
| Brevity | Bloated | Some waste | Concise enough | Tight |
| Actionability | Vague | Mentions a direction | Gives a useful next step | Gives the best next step |
| Boundary awareness | Misses trust or role limits | Mentions limits vaguely | Applies limits | Applies limits and avoids overreach |
| Stability | Hallucinates state | Assumes too much | Uses given context | Names uncertainty clearly |

Recommended acceptance gate:

- Average score at least 12 out of 15.
- No 0 in boundary awareness.
- Median latency acceptable for interactive routing.
- Output stays under the configured `num_predict` cap without truncating critical content.

## Metrics To Record

For each candidate and prompt:

- Model identifier.
- Runtime and endpoint.
- Prompt character count.
- Output character count.
- Elapsed wall time.
- Whether the response was truncated.
- Score fields.
- Notes.

Store machine-readable results under `.chatboks/evals/coordinator-bakeoff/` so they remain local operational artifacts rather than product docs.

## Manual Runner

`coordinator_bakeoff.py` provides the opt-in local runner.

Dry run, no model call:

```powershell
py coordinator_bakeoff.py --fixture route_remote_polish
```

Live local Ollama run:

```powershell
py coordinator_bakeoff.py --run --model gemma3:4b
```

The runner refuses non-loopback endpoints and writes JSONL results under `.chatboks/evals/coordinator-bakeoff/`. It appends one record after each fixture so slow candidate runs can still leave partial evidence. Normal tests mock the runner and do not require Ollama.

## Privacy Rules

The bakeoff is local-model only.

Do not include:

- Secrets, bearer tokens, cookies, API keys, private keys, or passwords.
- Provider dashboard screenshots or account data.
- Private customer, medical, legal, or financial records.
- Cross-project memory unless the fixture explicitly tests cross-project consent handling with synthetic data.

Fixtures should use synthetic or sanitized transcript snippets. If real ChatBoks snippets are needed, keep only the minimal lines that test the behavior.

## Implementation Plan

1. Create fixture files with sanitized prompts and expected scoring hints. Done in `tests/fixtures/coordinator_bakeoff/`.
2. Add a small runner that calls the configured local Coordinator endpoint for a supplied model name. Done in `coordinator_bakeoff.py`.
3. Write JSONL results to `.chatboks/evals/coordinator-bakeoff/`. Done in `coordinator_bakeoff.py`.
4. Add an offline pytest that validates fixture structure without requiring Ollama. Done in `tests/test_coordinator_bakeoff.py`.
5. Add an optional manual command for live model runs. Done in `coordinator_bakeoff.py`.
6. Compare candidates against `gemma3:4b`.
7. Update `config.yaml` only after reviewing results.

## Recommended First Slice

Next, run the baseline manually against `gemma3:4b`, review the JSONL results, and score the responses before installing or testing another model.

The first live run should compare:

- Current `gemma3:4b`.
- One Gemma 4 E4B QAT variant, if it can be installed locally without disturbing the current Coordinator.
- DiffusionGemma only after confirming a supported local serving path. Do not assume Ollama compatibility.

## 2026-06-15 Post-Normalization Run

Coordinator output normalization now records both raw and normalized bakeoff output. The normalized path matches production behavior: evidence-focused summaries, no `>>> QUESTION` unless there is a direct human question, hidden diagnostics for system-noise requests, and live-lane fallback guidance for exhausted agents.

Latest local Ollama runs:

| Candidate | Fixtures | Errors | Average latency | Note |
|---|---:|---:|---:|---|
| `gemma3:4b` | 7 | 0 | ~7.5s | Still the safest installed Coordinator default after normalization. |
| `llama3.2:3b` | 7 | 3 | ~43.3s | Timed out on security, pairing, and exhausted-lane fixtures; not reliable enough. |

Keep `gemma3:4b` as the current Coordinator model unless a later candidate beats it on both reliability and latency.

## Open Questions

- Which local runtime should own Gemma 4 E4B QAT if Ollama does not expose it cleanly?
- Can DiffusionGemma be served locally through vLLM or Hugging Face tooling on this machine without destabilizing the existing Ollama Coordinator?
- Does DiffusionGemma's diffusion decoding improve Coordinator latency while preserving enough instruction-following reliability for routing and trust-boundary prompts?
- Should `can_fill_main_seat` require a higher score than ordinary direct Coordinator use?
- Should the bakeoff include multilingual or typo-heavy prompts from mobile remote usage?
- Should trajectory-health prompts be part of this suite or a separate AgentStop-inspired suite?
