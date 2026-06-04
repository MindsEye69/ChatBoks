# Bugsearch Mode

Summary: Hunt for concrete defects, regressions, edge cases, and missing tests with evidence.

## Context Priming
- Start with `codegraph_status` when available.
- Use `codegraph_context` for the suspicious feature area.
- For flow bugs, prefer `codegraph_trace` over grep/read loops.
- Inspect recent diffs with `git status --short --branch` and targeted `git diff` when relevant.

## Workflow
1. Define the failure surface: user-visible symptom, command failure, UI state, or data contract.
2. Trace the owning path from input/event to output/render/result.
3. Look for state mismatches, stale caches, unsafe fallbacks, missing null handling, and action handlers that target the wrong entity.
4. Check whether tests or smoke checks cover the failure.
5. Rank findings by severity and confidence.
6. Recommend the smallest fix pass; do not broaden into unrelated cleanup.

## Quality Gate
- Findings include file/function references or exact behavior evidence.
- False positives and assumptions are named.
- Test gaps are listed separately from confirmed bugs.
- If patching was requested, checks are run and CodeGraph is synced.

## Escalation Triggers
- Emit `>>> QUESTION` if reproduction steps or expected behavior are missing.
- Emit `>>> PROPOSAL` if the bug fix requires a design choice or behavior tradeoff.
- Emit `>>> SKIP` if another agent already found the same issue and there is nothing materially different to add.
- Emit `>>> BLOCKED` only for a missing repro artifact, unavailable dependency, or inaccessible environment that prevents further diagnosis.
