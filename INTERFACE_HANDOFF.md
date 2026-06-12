# ChatBoks Interface Handoff

Use this handoff to continue ChatBoks interface work in a fresh chat. The current thread had a lot of mixed context, so start from this document and verify the repo state before editing.

## Current Repo State

- Project root: `C:\Users\MindsEye\Desktop\chatboks`
- Main branch at last known commit: `78e791d` (`Rename local helper to Coordinator`)
- `main` was aligned with `origin/main` when this handoff was refreshed.
- Worktree was clean when this handoff was refreshed.
- The local helper has been renamed project-wide to Coordinator.
- Canonical direct route: `@coordinator`; short alias: `@coord`.

## Verified So Far

The latest verification run before this handoff:

```powershell
py -m py_compile agents\coordinator.py router.py doctor.py orchestrator.py install.py remote_control.py
node --check mobile_remote\www\workbench.js
py -m pytest
```

Result: `321 passed`.

Graph status after refresh:

- CodeGraph: synced and up to date, 52 files, 1467 nodes, 3356 edges.
- Graphify: refreshed, 1395 nodes, 3528 edges, 75 communities.

## Interface Direction

The desired desktop/web/app interface is a proper workbench, not just the current terminal mirror.

Broad layout:

- Left rail: projects, recent tasks/chats, token balances, settings.
- Main area:
  - Separate vertical lanes/cards for major agents such as Claude, Codex, Gemini/Fable, etc.
  - A lower horizontal lane for Coordinator / local coordinator.
  - Central input composer at the bottom.
- Right rail:
  - Environment/status card: branch, changes, local/remote, commit/push.
  - Progress checklist for current task.
  - Sources/tool activity.
  - Monitor/mini-terminal area.

The user’s Photoshop mockup is at:

`C:\Users\MindsEye\Desktop\mockup_chatboks.jpg`

Design vibe:

- Dark, crisp, slightly cool terminal/workbench aesthetic.
- More polished than the raw mobile page, but still utilitarian.
- Cards should be functional agent panes, not marketing panels.
- Avoid cramped mobile-header problems seen earlier.
- Keep response text readable and preserve full transcript access.

## Current Mobile Remote UI Notes

Current files:

- `mobile_remote/www/index.html`
- `mobile_remote/www/styles.css`
- `mobile_remote/www/app.js`
- `mobile_remote/www/workbench.html`
- `mobile_remote/www/workbench.css`
- `mobile_remote/www/workbench.js`

Recently added:

- Sticky compact header.
- Collapsible connection/session panels.
- Project picker.
- Latest response and full transcript views.
- Copy response button.
- Sticky bottom composer.
- Token usage toggle.
- Live flow panel: `input -> router -> agent -> signal -> output`.
- Desktop-style workbench shell with agent lanes, Coordinator/system lane, environment rail, graph status, monitor, mini-terminal, and trace panels.
- Pairing feedback and request validation hardening.

Known UX points from user testing:

- Mobile screen space is precious. Hide/collapse anything not immediately useful.
- After Send, feedback must be visible near the composer.
- Avoid auto-scrolling to the wrong place; new output should be easy to find.
- The latest-response window should include all responses after the user prompt, not just the final control signal.
- Full transcript and copy response should remain easy to access near the composer/response area.
- The connection box should stay collapsed after successful login, but must not auto-collapse every poll.

## Security Scan Findings To Keep In Mind

Claude/Fable security scan file:

`C:\Users\MindsEye\Desktop\Fable 5 Security scan of chatboks.txt`

Already addressed and committed:

- Default mobile bridge URL no longer commits the personal tailnet hostname.
- Failed-fetch message no longer says URL must exactly match that hostname.
- Mobile event ingestion filters by cursor to reduce duplicate event replay.
- Poll failure during command no longer kills auto-refresh.
- Successful poll no longer forcibly collapses Connection/Session panels.
- Transcript turn parsing now includes `[ANTIGRAV]` and `[CODEX_SPARK]`.
- Packet-risk gate no longer treats unresolved/remaining language as risk resolution.
- JSON request bodies are capped and must be UTF-8 JSON objects.
- `/api/session` query params are validated, and oversized transcript limits are clamped.
- Successful pairing refreshes the operator file with the newly rotated pair code.

Still worth triaging later:

- Add a bridge single-instance / stale-operator-file guard so old bridge copies cannot confuse pairing.
- Pairing code still renews silently on TTL if nobody touches the bridge; decide whether to update/log the operator file on a timer or expose an operator status check.
- Remote snapshot reloads/reassigns app state during running command; review for race/state safety.
- No remote cancel/interrupt.
- Role-file trust failures need clearer remote-visible status if they occur.
- Avoid tokens in URLs where possible.
- Improve project switch failure logging.
- Confirmation mode last-agent HANDOFF behavior may need another look, but verify against current tests before changing.
- `parse_signal` may still deserve a line-based scan rather than `rfind` anywhere.

## Terminal / Mini-Terminal Idea

The right-side mini-terminal can display a screensaver until focused.

Current terminal intro work lives in:

- `ui/stream.py`
- `tests/test_stream_intro.py`

The best current shape is the tumbling box/cube that “looks like it is tumbling in the dark.” Keep it safe before experimenting further.

Potential behavior:

- Mini-terminal shows animated ChatBoks cube/screensaver while idle.
- User clicks/focuses the terminal area to reveal a normal `YOU >` prompt.
- Users can disable the animation.

## Suggested Next Work

1. Add the remote bridge single-instance / stale-operator-file guard.
2. Improve mobile/workbench connection recovery feedback and pairing-state copy.
3. Add approval-specific controls for APPROVE / MODIFY / REJECT in the remote UI.
4. Continue the higher-fidelity desktop/web workbench using the Photoshop layout as source direction.
5. Decide whether the first durable desktop target is:
   - the current static bridge-served web UI,
   - a local web app,
   - Electron/Tauri desktop shell,
   - or a richer native/React Native app later.
6. Keep the UI state model small and explicit before adding more panels:
   - current project,
   - active task,
   - agent panes,
   - event stream,
   - latest response group,
   - progress checklist,
   - terminal focus state.
7. Test with a real ChatBoks session after each UI change, especially scroll/focus/composer behavior.

## Useful Commands

```powershell
git status --short
node --check mobile_remote\www\app.js
node --check mobile_remote\www\workbench.js
py -m pytest tests/test_remote_control.py
py -m pytest tests/test_modes.py tests/test_context_modes.py
py -m pytest
& 'C:\Users\MindsEye\AppData\Local\codegraph\current\bin\codegraph.CMD' sync
graphify update .
```

Graphify may need normal user-level access to the `uv` tool cache. If it fails inside a sandbox, retry with approval/escalation instead of assuming the graph is broken.

## Fresh Chat Prompt

Paste this into a fresh chat:

```text
We are continuing ChatBoks interface and remote bridge work. Read `INTERFACE_HANDOFF.md`, inspect current git status, and verify CodeGraph status. The repo should be clean on `main`. The next planned slice is the remote bridge single-instance / stale-operator-file guard, followed by connection recovery feedback and approval controls in the remote UI. Keep the desktop/workbench direction grounded in `C:\Users\MindsEye\Desktop\mockup_chatboks.jpg`.
```
