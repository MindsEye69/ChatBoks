# Lane Model Bakeoff

Last reviewed: 2026-06-17

Status: repeatable harness added. GLM-5.2 live evaluation is deferred because it does not currently meet the no-new-monthly-cost constraint for ChatBoks testing.

## Goal

Evaluate optional ChatBoks lane agents, especially BYOM models that can act as a third collaborator next to any user-selected combination of Claude, Codex, Gemini, local models, or other provider-backed models.

This bakeoff is separate from the Coordinator model bakeoff. Coordinator should remain cheap, local, low-authority, and routing-focused. Lane agents may be heavier, cloud-backed, or long-context models, but they must be explicit user-selected collaborators.

## First Target

GLM-5.2 was the first target preset for a heavy long-context collaborator lane, but it is on ice for now. It remains technically interesting, but the current pricing/plan requirement makes it a poor fit for near-term ChatBoks validation when the project goal is BYOM viability across budgets, including free or low-cost lane setups.

Initial provider path:

- Provider protocol: OpenAI-compatible chat completions.
- Default model: `glm-5.2`.
- Default base URL: `https://api.z.ai/api/coding/paas/v4`.
- Default API key environment variable: `ZAI_API_KEY`.
- Result path: `.chatboks/evals/lane-bakeoff/`.

The harness does not store API keys in result files.

Decision as of 2026-06-17:

- Do not spend additional monthly AI budget to evaluate GLM-5.2.
- Keep the generic OpenAI-compatible lane bakeoff harness for future BYOM candidates.
- Prefer testing free, already-paid, local, or existing-account models before adding any new paid provider.
- Revisit GLM-5.2 only if a free trial, existing paid access, sponsored credit, or clear project budget appears.

## Evaluation Tasks

The first fixture suite tests lane-agent behavior, not Coordinator behavior:

| Fixture | What it tests |
|---|---|
| `architecture_byom_lane_runtime` | Whether the model understands the BYOM lane direction and keeps lanes, agents, providers, and Coordinator separate. |
| `refactor_openai_compat_agent` | Whether the model can propose a scoped implementation path for an OpenAI-compatible lane agent without disturbing existing agents. |
| `critique_confirmation_packet` | Whether the model can act as an independent verifier on packet-style evidence. |
| `long_context_synthesis` | Whether the model can synthesize roadmap and trust constraints into lane-runtime requirements. |
| `protocol_signal_compliance` | Whether the model honestly separates what can be done now from what is blocked by missing credentials and emits one ChatBoks signal. |

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
- No invented tool use, code changes, test results, credentials, or hidden state.
- Exactly one final ChatBoks signal.
- Latency and cost acceptable for optional collaborator use.

## Manual Runner

Dry run, no API call:

```powershell
py lane_bakeoff.py --fixture architecture_byom_lane_runtime
```

Deferred GLM-5.2 run, only if cost constraints change and a key exists in the local environment:

```powershell
$env:ZAI_API_KEY = "..."
py lane_bakeoff.py --run --model glm-5.2 --reasoning-effort medium
```

Run a single fixture:

```powershell
py lane_bakeoff.py --run --model glm-5.2 --fixture protocol_signal_compliance
```

Use another OpenAI-compatible provider:

```powershell
py lane_bakeoff.py --run --model some-model --base-url https://provider.example/v1 --api-key-env PROVIDER_API_KEY
```

## Privacy Rules

Do not include:

- Secrets, bearer tokens, cookies, API keys, private keys, or passwords.
- Authenticated provider dashboard screenshots or account metadata.
- Private customer, medical, legal, or financial records.
- Cross-project memory unless the fixture explicitly tests consent handling with synthetic data.
- Large source snapshots beyond the scoped task.

Cloud-backed lane runs are explicit provider calls. They must not become silent fallback behavior.

## Implementation Notes

Implemented:

- `lane_bakeoff.py`: OpenAI-compatible manual runner.
- `tests/fixtures/lane_bakeoff/`: sanitized fixture suite.
- `tests/test_lane_bakeoff.py`: offline validation and mocked API tests.

Blocked:

- Live GLM-5.2 run, because it would require a paid provider path or plan that is not justified under the current no-new-monthly-cost constraint.
- No `ZAI_API_KEY` or alternate provider token is currently present in the desktop environment.

## Sources

- Z.ai OpenAI-compatible coding endpoint docs: https://docs.z.ai/devpack/tool/others
- Z.ai HTTP endpoint docs: https://docs.z.ai/guides/develop/http/introduction
- GLM-5.2 model docs: https://docs.z.ai/guides/llm/glm-5.2
- Z.ai pricing: https://docs.z.ai/guides/overview/pricing
