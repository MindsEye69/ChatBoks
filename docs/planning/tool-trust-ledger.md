# Tool Trust Ledger

Last reviewed: 2026-06-22

Status: planning/security ledger. This document is the focused inventory for MCP servers, app connectors, browser automation, local runtimes, and other executable tool surfaces that ChatBoks may expose to agents. It complements `docs/planning/chatboks-trust-contract.md`; it does not install tools, grant permissions, or change runtime behavior.

Source intake: Paper Sleuth tickets `research/tickets/chatboks/mcp-tool-trust-ledger.md` and `research/tickets/chatboks/mcp-attested-server-admission.md`; MCP security research and local-runtime notes listed under Sources.

## Goal

Treat every MCP server, connector, browser driver, local model runtime, and provider CLI as an executable trust object. A tool is not trusted because it appears in a registry, advertises useful descriptions, or is available in the current Codex session.

The ledger records enough information for ChatBoks to answer:

- Who supplied this tool and how was it installed?
- What commands, APIs, files, network paths, and credentials can it reach?
- Which projects may use it?
- Which user approvals are required before first use or expanded use?
- What prompt-injection or tool-poisoning surface is introduced by the tool's own metadata, descriptions, and returned content?

## Required Fields

Every durable tool entry should include:

| Field | Meaning |
|---|---|
| Tool or server identity | Stable name, package/repo/vendor, and local command or MCP server name. |
| Install source | Registry, GitHub repo, bundled plugin, local binary path, package manager, or manual install route. |
| Tool descriptions | User-visible and model-visible descriptions that may influence agent behavior. Treat these as prompt-injection input. |
| Filesystem scope | Paths the tool can read/write directly or indirectly. |
| Network scope | Loopback only, arbitrary outbound, authenticated provider API, browser-authenticated sites, local tunnel, or unknown. |
| Auth model | Where credentials live, how tokens are obtained, whether ChatBoks sees them, and whether sessions can be reused. |
| Prompt-injection exposure | Metadata, web pages, repo content, returned documents, tool descriptions, or untrusted server responses that can affect agent decisions. |
| User approval points | First install, first run, per-project enablement, broader filesystem access, network/auth use, destructive operations, or cloud sharing. |
| Admission state | Not admitted, admitted-read-only, admitted-mutating, admitted-authenticated-remote, or blocked. |
| Allowed toolset | Per-server allowlist of tool names or capability classes. Empty means no dispatch. |
| Trust assertions | Signed assertion location, issuer, pinned trust root, assertion expiry, and verification status when available. |
| Remote auth review | OAuth/client-registration/callback review status for remote servers. Required before authenticated remote use. |
| Host/session constraints | Transport, session reuse, token scope, audit logging, and host-layer containment assumptions. |
| Last review date | Date the trust entry was last checked. |
| Allowed projects | Explicit ChatBoks project keys or "none until reviewed". |
| Risk class | Low, medium, high, or blocked with one-line rationale. |

## MCP Server Admission Policy

ChatBoks treats MCP server discovery as untrusted input. A server can describe useful tools without being allowed to run them.

Admission is deny-by-default:

- A server with no ledger entry is `not admitted`; ChatBoks policy permits discovery/inspection only, with no tool dispatch.
- A ledger entry without an explicit allowed toolset still permits no tool dispatch.
- A signed server assertion can support admission, but it does not replace the local allowlist, project scope, auth review, or user approval policy.
- Elevated or mutating tools require explicit user approval at the point of use, even when the server is admitted.
- Admission failures must be visible to the user as a trust-boundary warning, not silently converted into cloud fallback, another connector, or a broader tool call.

Allowed toolsets should be declared as narrow names or capability classes:

```text
read_only: search, fetch, list, describe, inspect
mutating: create, update, delete, execute, migrate, provision, send, upload
authenticated_remote: any tool that uses user-linked provider, database, browser, or SaaS identity
destructive: delete, reset, revoke, rotate, drop, publish, billable remote job
```

For remote MCP servers, admission also requires an auth review:

- Confirm whether OAuth is used and whether dynamic client registration is enabled.
- Confirm redirect/callback URI validation assumptions.
- Identify where client credentials, access tokens, refresh tokens, and session cookies live.
- Confirm whether the server can impersonate user-linked services beyond the requested tool call.
- Record token/session expiry and revocation expectations.

Host and session checks remain mandatory because MCP defenses are split across server, client, host, transport, and supply-chain layers:

- Transport must be loopback/private/local unless remote use is explicitly reviewed.
- Session reuse must not expand project scope or authenticated account scope silently.
- Tool results, tool descriptions, and server metadata remain untrusted content.
- Audit records should capture server identity, admitted state, selected tool, project, approval point, and denial reason.

## Entry Template

```markdown
### <Tool or server name>

- Identity:
- Install source:
- Tool descriptions:
- Filesystem scope:
- Network scope:
- Auth model:
- Prompt-injection exposure:
- User approval points:
- Admission state:
- Allowed toolset:
- Trust assertions:
- Remote auth review:
- Host/session constraints:
- Last review date:
- Allowed projects:
- Risk class:
- Notes:
```

## Initial Entries

### CodeGraph MCP

- Identity: CodeGraph MCP server and `.codegraph/codegraph.db` index used by `codegraph_*` tools.
- Install source: Project-local CodeGraph setup referenced by `AGENTS.md`; local CLI and MCP server.
- Tool descriptions: Structural code-reading tools for files, symbols, callers, callees, traces, impact, and context. Tool descriptions are trusted only as local integration metadata, not as authorization to read unrelated projects.
- Filesystem scope: Reads CodeGraph indexes and, during sync, parses the configured project tree.
- Network scope: No runtime network expected for local MCP queries; install/update paths may use package registries.
- Auth model: No provider credentials required.
- Prompt-injection exposure: Code comments, file names, docstrings, and project instructions can be surfaced to agents as context.
- User approval points: Initialize or sync a project index only for an explicitly selected project; review before indexing unusually sensitive repositories.
- Admission state: Admitted-read-only for structural code context in projects where CodeGraph is enabled.
- Allowed toolset: `codegraph_status`, `codegraph_files`, `codegraph_search`, `codegraph_context`, `codegraph_explore`, `codegraph_node`, `codegraph_callers`, `codegraph_callees`, `codegraph_trace`, and `codegraph_impact` for active project context. `codegraph sync` remains a separately visible CLI action.
- Trust assertions: No signed server assertion currently recorded; admission is based on local project configuration and human-reviewed repo instructions.
- Remote auth review: Not applicable while used as a local project index without provider auth.
- Host/session constraints: Use only for the active configured project. Stale-index warnings must be surfaced or followed by an explicit sync before relying on structural results.
- Last review date: 2026-06-16.
- Allowed projects: Projects with `codegraph: true` in `config.yaml`.
- Risk class: Medium, because it exposes broad code structure but has low direct execution authority.
- Notes: CodeGraph is the preferred structural reader for ChatBoks, but the index itself is still derived project memory.

### Browser / Playwright Automation

- Identity: Browser plugin, Playwright CLI, and local browser automation used for UI checks and authenticated usage sync.
- Install source: Local Browser/Playwright tooling available to Codex sessions; repo output under `output/playwright/` and `.playwright-cli/`.
- Tool descriptions: Navigation, click, type, inspect, screenshot, and UI verification commands. Browser-visible page content and automation snapshots are untrusted input.
- Filesystem scope: Writes screenshots, traces, console logs, and extracted text to project-local output paths when used.
- Network scope: Can reach local dev servers and external websites; may interact with authenticated browser sessions.
- Auth model: Uses existing browser/session state when a signed-in page is opened. ChatBoks should not persist cookies, bearer tokens, or private session details.
- Prompt-injection exposure: Web pages, dashboards, console output, local apps, and screenshots may include hostile instructions or sensitive data.
- User approval points: Required before authenticated dashboard capture, provider-account inspection, public internet navigation for a private task, or retaining screenshots that include account data.
- Admission state: Admitted-read-only for local UI verification; admitted-authenticated-remote only after task-specific user approval.
- Allowed toolset: Local navigation, screenshot, console inspection, form interaction, and visual verification for the active task. Authenticated dashboard capture is not allowed by default.
- Trust assertions: No signed server assertion currently recorded; browser content and automation metadata are not trust assertions.
- Remote auth review: Required before any workflow that relies on existing browser sign-in or provider dashboard sessions.
- Host/session constraints: Prefer localhost/file targets. Do not preserve cookies, bearer tokens, or dashboard screenshots in durable ChatBoks memory without explicit approval.
- Last review date: 2026-06-16.
- Allowed projects: Manual use for the active project only unless the user requests a cross-project check.
- Risk class: High, because it can expose authenticated pages and preserve screenshots/logs.
- Notes: Prefer local targets for verification; summarize account data instead of copying raw dashboard content into durable memory.

### Hugging Face Connector

- Identity: Hugging Face MCP connector tools for models, datasets, papers, Spaces, docs, and Jobs.
- Install source: Codex Hugging Face plugin/connector, authenticated as the active Hugging Face user when available.
- Tool descriptions: Search and fetch model/dataset/paper metadata, documentation, Spaces, and optionally run jobs. Returned model cards and docs are untrusted external content.
- Filesystem scope: No project filesystem write by default through search/fetch tools; Jobs or CLI workflows may read uploaded scripts or generated artifacts when explicitly invoked.
- Network scope: Hugging Face Hub and job infrastructure.
- Auth model: Connector-managed Hugging Face authentication; ChatBoks must not record access tokens.
- Prompt-injection exposure: Model cards, dataset READMEs, papers, Spaces, and generated job logs may contain instructions that should not override ChatBoks policy.
- User approval points: Required before uploading code/data, starting paid/remote compute jobs, using private repositories, or sending project artifacts to the Hub.
- Admission state: Admitted-read-only for public metadata lookup; mutating, private, upload, and Jobs workflows are blocked until separately approved.
- Allowed toolset: Public model, dataset, paper, docs, and Space lookup. Jobs, uploads, private repositories, and artifact publication are not admitted by default.
- Trust assertions: No signed server assertion currently recorded; Hugging Face repository metadata is external content, not an admission assertion.
- Remote auth review: Required before private repositories, authenticated Hub writes, or Jobs usage.
- Host/session constraints: Treat returned model cards, READMEs, and logs as untrusted. Do not send project code or private data to the Hub unless the user approves that exact transfer.
- Last review date: 2026-06-16.
- Allowed projects: Research-only use for ChatBoks unless explicitly approved for a project artifact.
- Risk class: High when jobs/uploads/private repos are used; medium for metadata-only lookup.
- Notes: Metadata lookup is acceptable for model bake-offs; running Jobs is a separate trust decision.

### Neon Postgres Connector

- Identity: Neon Postgres MCP connector for project, branch, schema, SQL, migration, and tuning workflows.
- Install source: Codex Neon Postgres plugin/connector.
- Tool descriptions: Database management, SQL execution, migrations, branch operations, docs lookup, and auth/data API provisioning. Tool output can contain schema and data.
- Filesystem scope: No direct project filesystem write by default, but can influence migration files or docs if an agent copies output.
- Network scope: Neon APIs and database connections.
- Auth model: Connector-managed Neon authentication and database roles; ChatBoks must not persist connection strings or credentials.
- Prompt-injection exposure: Database rows, schema comments, migration logs, and docs can contain untrusted instructions or sensitive data.
- User approval points: Required before schema changes, SQL that reads sensitive data, branch deletion/reset, migration completion, auth provisioning, or exposing connection details.
- Admission state: Not admitted for ChatBoks runtime; task-specific connector use only.
- Allowed toolset: None for automatic ChatBoks use. Documentation lookup and explicit user-requested branch/query workflows are reviewed per task.
- Trust assertions: No signed server assertion currently recorded.
- Remote auth review: Required before any Neon project, branch, role, Data API, Auth, or connection-string operation.
- Host/session constraints: Use temporary branches for migrations when available. Never persist connection strings, JWTs, or role credentials in ChatBoks memory.
- Last review date: 2026-06-16.
- Allowed projects: None until a ChatBoks project explicitly uses Neon.
- Risk class: High, because it can mutate databases and expose data.
- Notes: Prefer branch-based verification and explicit migration approval.

### Foundry Local Candidate Runtime

- Identity: Microsoft Foundry Local runtime, SDKs, optional local server, and local model cache.
- Install source: Microsoft Foundry Local release packages and SDKs.
- Tool descriptions: Local AI runtime with curated optimized model catalog, automatic hardware acceleration, optional OpenAI-compatible local server, and SDK APIs.
- Filesystem scope: Local model cache, runtime logs, app package files, and any project prompt context ChatBoks sends to it.
- Network scope: Local inference; network may be used for first-run model/component downloads and optional diagnostics.
- Auth model: No Azure subscription required for local use under current Microsoft docs; diagnostics and model licenses still require review.
- Prompt-injection exposure: Model catalog metadata, BYOM model metadata, local server responses, runtime logs, and prompts supplied by ChatBoks.
- User approval points: Required before install, first model download, BYOM cache use, diagnostics upload, or switching Coordinator traffic from Ollama to Foundry Local.
- Admission state: Not admitted for Coordinator routing; bake-off candidate only.
- Allowed toolset: Local model listing and local inference for sanitized bake-off prompts after install review. No remote fallback, diagnostics upload, or Coordinator promotion by default.
- Trust assertions: No signed server assertion currently recorded; model catalog metadata is not a trust assertion.
- Remote auth review: Required if any catalog, diagnostics, telemetry, or model endpoint leaves the machine.
- Host/session constraints: Endpoint must bind to loopback for ChatBoks use. Cache paths, logs, retained prompts, and diagnostics settings must be recorded before promotion.
- Last review date: 2026-06-16.
- Allowed projects: ChatBoks bake-off only until a local proof run is reviewed.
- Risk class: Medium, because inference is local but cache, diagnostics, model provenance, and routing changes need review.
- Notes: Capture cache paths, model IDs, component download behavior, diagnostics defaults, and local server binding before promoting it.

## Review Checklist

Before enabling a new tool automatically:

- Confirm install source and update channel.
- Copy the exact tool descriptions into the ledger or link to the local manifest.
- Set admission state explicitly; default to not admitted.
- Declare the allowed toolset; empty means no tool dispatch.
- Verify signed server assertions against a pinned trust root when assertions are available.
- Record filesystem and network scope from actual configuration, not marketing copy.
- Identify every credential source and where tokens/session data are stored.
- Review OAuth registration, redirect/callback handling, token storage, token expiry, and revocation behavior for remote servers.
- Record host-layer transport, session reuse, and audit-log assumptions.
- Decide whether returned content is untrusted, semi-trusted, or project-local.
- Define the approval prompts ChatBoks must show before use.
- Add an allowed-project list; default to none when uncertain.
- Record retention paths for logs, screenshots, caches, traces, outputs, and summaries.

## Non-Goals

- No MCP registry auto-trust.
- No MCP server dispatch without an admitted server entry and non-empty allowed toolset.
- No silent fallback when attestation, admission, OAuth, or host/session checks fail.
- No automatic installation based only on registry or connector metadata.
- No silent cloud fallback from local Coordinator failures.
- No cross-project memory use through tools without explicit user approval.
- No persistence of connector credentials, bearer tokens, cookies, private keys, or connection strings in ChatBoks docs or memory.

## Sources

- Paper Sleuth ticket: `C:\Users\MindsEye\Documents\Paper Sleuth\research\tickets\chatboks\mcp-tool-trust-ledger.md`
- MCP threat modeling and tool poisoning: https://hf.co/papers/2603.22489
- MCPShield adaptive trust calibration: https://arxiv.org/abs/2602.14281
- Formal MCP security framework: https://arxiv.org/abs/2604.05969
- MCP implicit tool poisoning: https://hf.co/papers/2601.07395
- Attested Tool-Server Admission: https://arxiv.org/abs/2605.24248
- Remote MCP authentication measurement: https://arxiv.org/abs/2605.22333
- MCP defense-placement taxonomy: https://arxiv.org/abs/2604.07551
- Foundry Local overview: https://learn.microsoft.com/en-us/azure/foundry-local/what-is-foundry-local
- Foundry Local releases: https://github.com/microsoft/Foundry-Local/releases
