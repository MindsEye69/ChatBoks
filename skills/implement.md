# Implement Mode

Summary: Build a scoped, verified change without broad refactors or mixed commits.

## Context Priming
- Start with `codegraph_status` when available.
- Use `codegraph_context` for the requested feature or bug area before reading files manually.
- Identify the smallest files and symbols that own the behavior.
- Check `git status --short --branch` before editing so pre-existing changes are not mixed accidentally.

## Workflow
1. Restate the intended behavior and acceptance criteria in one short paragraph.
2. Inspect the relevant call path, component tree, or API boundary.
3. Patch the smallest coherent surface.
4. Add or update focused tests when the behavior is shared, risky, or easy to regress.
5. Run the cheapest meaningful checks first; broaden only if the change warrants it.
6. Keep generated, local, cache, and transcript files out of commits.

## Quality Gate
- The changed behavior is implemented and scoped to the request.
- Pre-existing worktree changes are preserved and not reverted.
- Relevant checks were run, or any skipped checks are explicitly named with the reason.
- CodeGraph is synced after code changes when the CLI/tool is available.
- Final report names changed files, verification results, and remaining risk.

## Escalation Triggers
- Emit `>>> QUESTION` if acceptance criteria conflict or the requested behavior is ambiguous enough to risk wrong code.
- Emit `>>> PROPOSAL` for changes that alter architecture, security posture, data storage, or public workflow.
- Emit `>>> BLOCKED` only after a concrete external blocker prevents meaningful progress.
