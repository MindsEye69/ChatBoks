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
