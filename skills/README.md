# ChatBoks Native Skills

Native skills are markdown workflow cards for ChatBoks collaboration modes and repeatable tasks. They are intentionally separate from routing:

- `/mode` still controls prompt framing.
- Project config still controls which agents run.
- `/skills` only lists or previews these files.

## Schema

Each skill should use this structure:

```markdown
# Skill Name

Summary: One sentence explaining when to use this skill.

## Context Priming
- What the agent should inspect before acting.
- Which CodeGraph tools or local commands are preferred.

## Workflow
1. Ordered work steps.
2. Keep these concrete and mode-specific.

## Quality Gate
- Checks before `>>> TASK_COMPLETE`.
- Tests, build commands, CodeGraph sync, or review criteria.

## Escalation Triggers
- When to emit `>>> QUESTION`.
- When to emit `>>> BLOCKED`.
- When to emit `>>> PROPOSAL`.
```

## Rules

- Use ChatBoks signals only: `>>> PROPOSAL`, `>>> QUESTION`, `>>> HANDOFF`, `>>> SKIP`, `>>> TASK_COMPLETE`, `>>> BLOCKED`.
- Do not include agent routing logic in skills.
- Do not copy third-party workflow text unless the file includes the required license attribution.
- Prefer project-native tools and CodeGraph context over generic broad scans.
