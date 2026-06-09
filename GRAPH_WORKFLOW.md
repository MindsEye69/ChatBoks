# Graph Workflow

ChatBoks uses two graph tools with different responsibilities.

## CodeGraph

Use CodeGraph first for live code work:

- symbol lookup
- callers/callees
- impact analysis
- flow tracing
- project file structure

Run `codegraph sync` after code edits and before handoff or commit summaries.

## Graphify

Use Graphify as the broader project map:

- architecture orientation
- durable docs plus code relationships
- community hubs
- exploratory cross-cutting questions
- visual graph/tree review

Refresh it after source or durable documentation changes that should be reflected in the architecture map:

```powershell
graphify update .
graphify tree --label ChatBoks
```

For semantic documentation changes where AST-only update is not enough, rerun extraction with the configured local
backend before clustering/tree generation.

## Freshness Checks

Run:

```powershell
python doctor.py chatboks
```

Doctor checks CodeGraph availability and verifies that `graphify-out/GRAPH_REPORT.md` was built from the latest source
commit, excluding `graphify-out/**` artifact-only commits.
