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

The local operator workflow is:

1. /integration to inspect pending requests.
2. /integration approve request-id with an optional review note, or reject it.
3. /integration dispatch request-id to send an approved input.prompt through
   normal ChatBoks routing.

Those approval and dispatch commands are rejected when submitted through the
remote-workbench bridge. They require a terminal or desktop-originated action.

Authenticated paired clients can observe request metadata through the versioned
read-only routes /api/integration/v1/requests and
/api/integration/v1/requests/request-id. These responses omit task input,
decision notes, proof IDs, and tokens. They do not grant approval or dispatch
authority.

Creating a queued request uses POST /api/integration/v1/requests with exactly
two fields: clientProof and requestPayload. It requires both the loopback bearer
token and a valid paired-client proof. Without the optional Foundation package,
the route reports unavailable. A successful response is pending only; it does
not approve, route, or dispatch work.
