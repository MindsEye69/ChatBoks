# ChatBoks Mobile Remote Pairing Runbook

This file exists so future Codex/Claude sessions can generate a fresh ChatBoks mobile pairing code without guessing.

## What Changed

`remote_control.py` writes a local runtime operator file when the bridge starts:

```text
.chatboks/remote_bridge.json
```

That file is ignored by git. It contains the local bridge URL, current one-time pairing code, expiry, and an admin token that can rotate the pairing code on the running bridge.

Do not commit or paste the admin token into public logs.

## Public Safety

This runbook is safe to commit because it contains only generic commands and placeholder values.

Do not commit any of these local runtime artifacts:

- `.chatboks/remote_bridge.json`
- live pairing codes
- admin bearer tokens
- mobile session tokens
- personal tailnet hostnames or device IPs copied from a running session

Before pushing remote-control changes, run a quick search for the current live code/token if one was printed in chat or terminal output. The operator file itself should remain untracked because `.chatboks/` is ignored.

## Generate A New Pairing Code

From the ChatBoks repo root:

```powershell
python remote_control.py --rotate-pair-code
```

If `python` is not on PATH in the current shell, use the same Python launcher/executable that starts ChatBoks successfully on that machine. For example, if the working terminal starts ChatBoks with `python orchestrator.py chatboks`, use `python remote_control.py --rotate-pair-code` from that same terminal.

Expected output:

```text
Pairing code: ABCD2345 (expires in 300 seconds)
Bridge URL: http://127.0.0.1:8765
```

Give the user:

- the pairing code
- the bridge URL shown by the command, or the active Tailscale/Tailnet URL if the phone is using that route

## If The Command Cannot Find The Operator File

The bridge is probably not running, or the current shell is not in the project root that owns the active bridge file.

Check:

```powershell
Test-Path .chatboks\remote_bridge.json
```

If the file is elsewhere, pass it explicitly:

```powershell
python remote_control.py --rotate-pair-code --operator-file C:\path\to\.chatboks\remote_bridge.json
```

## Start The Bridge

Local loopback bridge:

```powershell
python remote_control.py chatboks --host 127.0.0.1 --port 8765
```

Tailnet fallback bind, only when Tailscale Serve is unavailable and the host is a Tailscale `100.64.0.0/10` address:

```powershell
python remote_control.py chatboks --host 100.x.y.z --port 8765 --allow-tailnet-bind
```

On startup, the bridge prints:

- listening URL
- current pairing code
- operator file path
- the exact new-code command

## How Pairing Works

1. Desktop bridge starts and creates a one-time pairing code.
2. Android app sends that code to `/api/pair`.
3. Bridge returns a short-lived session token.
4. Pairing code is invalidated after successful use.
5. `--rotate-pair-code` asks the running bridge to create and print a fresh one.

Only the admin token from `.chatboks/remote_bridge.json` can rotate pairing codes. A normal mobile session token cannot.

## Troubleshooting

If the phone says `Failed to fetch`:

- Confirm Tailscale is connected on the phone.
- Confirm the bridge URL is correct.
- Confirm the bridge process is still running.
- Confirm Windows firewall allows the tailnet path if using direct tailnet bind.
- Try the loopback URL from a desktop browser first.

If the pairing code is rejected:

- Generate a fresh code with `python remote_control.py --rotate-pair-code`.
- Pair within 5 minutes.
- Do not reuse a code after successful pairing; codes are one-time.

If the rotate command fails to reach the bridge:

- The operator file may be stale from a crashed bridge.
- Restart the bridge and use the newly printed code.
- If the bridge is bound to a different host/port, verify the operator file matches the live process.

## Relevant Tests

```powershell
py -m pytest tests/test_remote_control.py
```

The pairing tests verify:

- device pairing issues a session token
- invalid codes are rejected
- used codes cannot be reused
- admin rotation updates the operator file
- session tokens cannot rotate pairing codes
