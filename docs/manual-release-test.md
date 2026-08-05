# ChatBoks manual release test

Use the packaged desktop executable for the ordinary checks.  Use a disposable
project for an integration execution: that execution can invoke a real local
agent and write agent artifacts below that project's `.chatboks` directory.

## 1. Start and basic Workbench checks

1. Start `dist\\ChatBoks.exe` and wait for the ChatBoks window.
2. Confirm the selected project is `chatboks` (or deliberately choose the
   project you intend to use).
3. Send a short ordinary prompt, then a second prompt that refers to the first.
   Both should render normally and the second should retain the immediate chat
   context.
4. Run `/help`, `/resume`, `/tickets`, and `/integration all` from the local
   operator UI.  They should return status, not expose another process's
   prompt, live output, process ID, or filesystem path outside the selected
   project.
5. Close the window and reopen it.  It should start normally and show no
   browser certificate, pairing, or access-control error.

## 2. Normal verified integration check

This checks the actual authority boundary.  Do not create or edit a request by
writing to the SQLite files; the request must arrive through the normal paired,
proof-verified integration client.

1. Point that client at a disposable project and submit a small, harmless,
   bounded request (for example, write a short `manual-test.md` file).
2. In the local desktop or terminal operator session, run
   `/integration pending`.  Confirm the request is visible with its ticket,
   capability, objective, and verification summary.
3. Run `/integration approve <request-id> manual release test`, then
   `/integration dispatch <request-id>`.
4. Run `/integration all` until it reaches a terminal state.  A successful
   run should show `checkpoint=completed` and
   `safe_stages=agent_loaded,context_built,result_written`.
5. Confirm the actual work and verification result in the disposable project.
   The execution record and result live only under that project's `.chatboks`
   folder.
6. Submit a second request, approve it, then use
   `/integration revoke <request-id>` before dispatch.  Dispatch must be
   refused.

## 3. Safe restart boundary (advanced, one fresh request)

This deliberately stops the isolated worker **before** the agent step.  It is
the only state that may be safely resumed without a new approval.

1. Close ChatBoks and remove the previous test marker from the disposable
   project if it exists:
   `.chatboks\\integration-test-fault-pre-agent.once`.
2. From a PowerShell window, start ChatBoks with:

   ```powershell
   $env:CHATBOKS_INTEGRATION_TEST_FAULT = "exit_before_agent_once"
   .\\dist\\ChatBoks.exe
   ```

3. Submit and approve a *new* harmless verified request, then dispatch it.
   The isolated worker exits once immediately after protected context building;
   no agent work should have started.
4. Run `/integration recover <request-id>`, then `/integration all`.  It should
   show `interrupted`, `checkpoint=prepared`, and safe stages
   `agent_loaded,context_built`.
5. Run `/integration resume <request-id>`.  The resumed worker must complete
   normally, with the agent invoked once and `result_written` added.

If recovery reports `checkpoint=in_progress` or `checkpoint=uncertain`, do
**not** resume it.  That is the deliberate safety rule: cancel it or submit a
new request instead, because ChatBoks cannot prove whether an agent side effect
already occurred.

The fault exists only when the exact environment variable above is inherited by
the local worker.  It is one-shot per project, cannot be set by an integration
request, and is not enabled in normal launches.
