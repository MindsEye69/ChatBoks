# Local integration authority

ChatBoks is the authority for its own execution. It can run without
DasDashboard or any other companion application. A companion client may add
convenience and request provenance, but it does not issue permission to run a
ChatBoks task.

integration_authority.py persists the minimum local security state needed
before a writable integration lifecycle is introduced:

- paired clients' Ed25519 public keys and fingerprints;
- logical client revocations without deleting history;
- caller-validated signed grant-revocation records; and
- proof-ID and nonce replay evidence retained through the proof's expiry; and
- a durable, chained authorization audit trail.

By default the SQLite database is stored at
~/.chatboks/integration_authority.sqlite3. The store uses SQLite WAL mode,
full synchronous commits, bounded JSON documents, parameterized SQL, and
short write transactions. It does not store private keys, bearer tokens, or
unredacted request secrets.

The audit chain detects accidental corruption and simple partial modification;
it is not a defence against an attacker who can rewrite the whole local
database. A future hardened deployment can export audit events to a separate
append-only destination, but that is not a prerequisite for keeping authority
local in this first implementation.

When the protected lifecycle is added, ChatBoks will:

1. verify an optional paired client's signed request proof against this local
   trusted-key store;
2. apply ChatBoks-owned policy, interactive approval, task scope, expiry,
   revocation, and audit requirements;
3. only then authorize execution.

The shared Foundation contract is used for interoperable request proofs and
grants. DasDashboard is therefore an optional paired client, never the default
grant issuer or a required ChatBoks dependency.

To enable proof verification, install the explicit optional requirements file.
The proof gate verifies an exact request against the locally paired public keys
and durable replay store, then returns provenance only. It does not authorize
or start execution; the pending ChatBoks approval flow remains the sole
authority for that decision.

Verified requests enter a project-local SQLite queue before they can affect an
active ChatBoks session. The queue permits only pending to approved or rejected
transitions; dispatch is permitted only after local approval. It keeps the
request content for operator review but never stores the proof token. Do not
place credentials or other secrets in integration request input.

## Structured ticket execution input

`input.prompt` remains supported for existing paired clients. New integrations
should instead use `input.ticketExecution` with
`schema: "chatboks.ticket-execution/v1"`. It requires a bounded objective,
constraints, context references, requested capability IDs, the fixed
`local_operator_required` approval policy, verification criteria, a requested
step/runtime budget, and an idempotency key.

The queue validates this payload before it is stored. Its idempotency key
deduplicates retries from the same paired client for the same ticket, while a
changed payload with the same key is rejected. `/integration pending` shows the
objective, constraint and verification counts, and requested budget to the
local operator before approval.

The local `/integration all` view includes execution liveness plus checkpoint
state, completed safe-stage names, result status, and any recovery reason.
ChatBoks therefore remains inspectable without a paired dashboard.

The structured fields are still untrusted task material. Context references
are never opened automatically. ChatBoks currently allowlists only
`execution.lifecycle`; structured tickets must declare exactly that capability,
and local approval writes a durable receipt for it before dispatch is possible.
The local review shows its high risk and unknown reversibility. Receipts expire
after 15 minutes and can be revoked locally while work is still undispatched.
Both expired and revoked approvals are recorded as rejected requests with a
durable event explaining why; they can never be dispatched. Revoking an
already-running worker is deliberately not supported—use the explicit local
cancellation flow instead. The receipt is not a sandbox for the configured
external agent: requested capabilities do not grant arbitrary tools, and the
requested budget does not impose a hard runtime limit yet. Broader typed
capability adapters and durable per-step budget receipts remain CBX-005 and
CBX-007 work respectively.

The local operator workflow is:

1. /integration to inspect pending requests.
2. /integration approve request-id with an optional review note, or reject it.
3. /integration revoke request-id before dispatch if the approved scope must
   no longer run.
4. /integration dispatch request-id to launch one request-owned worker for the
   approved legacy `input.prompt` or structured ticket execution input.
5. /integration cancel request-id to stop that worker only after ChatBoks
   verifies the recorded PID still belongs to the expected worker command.
6. /integration recover request-id to mark a dispatched execution interrupted
   only when its recorded worker can no longer be verified; a verified worker
   is left running.

Those approval and dispatch commands are rejected when submitted through the
remote-workbench bridge. They require a terminal or desktop-originated action.

Authenticated paired clients can observe request metadata through the versioned
read-only routes /api/integration/v1/requests and
/api/integration/v1/requests/request-id. After local dispatch, that metadata
identifies the operator session and the request-owned execution's durable
status; the manifest advertises this as execution.sessions.observe. Responses
omit task input, decision notes, proof IDs, tokens, worker PIDs, and agent
output. They do not grant approval or dispatch authority.

GET /api/integration/v1/discovery serves the compatible Foundation 0.2
application manifest. Its instance ID, version, and authenticated health URL
are derived from the running local bridge. ChatBoks does not advertise a deep
link or Lumen module until it implements one.

The metadata-only route /api/integration/v1/requests/request-id/events exposes
the queued request's received, approved, rejected, and dispatched lifecycle
events with a bounded `after` cursor. It deliberately omits each event's stored
detail, so review notes, proof IDs, and request digests stay local.

After an isolated worker exists, the metadata-only route
/api/integration/v1/requests/request-id/execution/events exposes that worker's
state changes with the same bounded cursor. It returns execution identity,
status, timestamps, bounded active-role/current-operation/expected-transition
metadata, and event types only. A running worker emits durable heartbeats, so
an observer can distinguish recent liveness from a stale record without
guessing from chat output. A heartbeat older than 20 seconds is reported as a
stale warning only; ChatBoks does not terminate or interrupt work automatically
from that signal. Runner PIDs, task input, result artifacts, and agent output
remain local.

Execution observation also exposes checkpoint state, safe-stage names,
result-status, and recovery reason. It never exposes receipt hashes, context,
configuration, or result content.

The project-local execution registry at
.chatboks/integration-executions.sqlite3 assigns one execution ID per request,
records a request-owned worker PID, and stores metadata-only state transitions.
Dispatch starts a separate Python worker process with its own process group;
the worker invokes the configured primary agent in execute mode without
writing to the operator's ChatBoks state or journal. Its local-only result is
stored under .chatboks/integration-executions/execution-id/result.md.

Cancellation is local-only. It targets the worker's process tree only after a
command-line ownership check, and never calls ChatBoks' project-wide stop
command. Recovery is also local-only and never terminates a process. Pause and
resume remain deferred until they can preserve the same ownership guarantee.

Each isolated execution also writes a local checkpoint ledger before invoking
the configured agent. The present worker has one opaque, potentially
irreversible `agent_execute` step, surrounded by repeatable `agent_loaded`,
`context_built`, and `result_written` stages. Each safe stage receives a hash
receipt without copying configuration, context, or agent output into the
ledger. A terminal response creates its own result-status and hash receipt. If
recovery cannot verify the worker, the open agent step is marked `uncertain` and
ChatBoks refuses to replay it automatically. A true resume will require future
agents to emit durable sub-step receipts; it cannot be honestly implemented
around one opaque LLM call.

There is one explicit, local-only exception: after `/integration recover`, an
operator may use `/integration resume request-id` only when the checkpoint is
still `prepared`, meaning `agent_execute` never began. This restarts the worker
from its safe local stages. It is unavailable for an in-progress, uncertain, or
completed agent step.

Creating a queued request uses POST /api/integration/v1/requests with exactly
two fields: clientProof and requestPayload. It requires both the loopback bearer
token and a valid paired-client proof. Without the optional Foundation package,
the route reports unavailable. A successful response is pending only; it does
not approve, route, or dispatch work.
