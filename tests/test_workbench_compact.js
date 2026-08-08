const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

let responsive = {};
try {
  responsive = require('../mobile_remote/www/workbench-responsive.js');
} catch {
  // The first test run intentionally reaches this branch until the compact
  // workbench helper is implemented.
}

test('compact mode follows a newly routed agent without overriding a manual choice on every poll', () => {
  assert.equal(typeof responsive.resolveCompactLane, 'function');
  const lanes = ['claude', 'codex', 'codex_spark'];

  assert.equal(responsive.resolveCompactLane({ lanes, current: '', nextAgent: 'claude', previousNextAgent: '' }), 'claude');
  assert.equal(responsive.resolveCompactLane({ lanes, current: 'codex', nextAgent: 'claude', previousNextAgent: 'claude' }), 'codex');
  assert.equal(responsive.resolveCompactLane({ lanes, current: 'claude', nextAgent: 'codex', previousNextAgent: 'claude' }), 'codex');
  assert.equal(responsive.resolveCompactLane({ lanes, current: 'removed', nextAgent: '', previousNextAgent: '' }), 'claude');
});

test('embedded compact CSS keeps the focused chat and composer inside the viewport', () => {
  const css = fs.readFileSync(path.join(__dirname, '../mobile_remote/www/workbench.css'), 'utf8');
  assert.match(css, /data-compact-workbench=["']true["']/);
  assert.match(css, /\.agent-lanes\[data-view="task"\]\s+\.agent-pane\.is-active-lane/);
  assert.match(css, /height:\s*100dvh/);
});

test('Lumen message bubbles keep overflow reachable from the top of the transcript', () => {
  const css = fs.readFileSync(path.join(__dirname, '../mobile_remote/www/workbench.css'), 'utf8');
  const bubbleStyles = css.slice(css.indexOf('/* Lumen motion bubbles.'));

  assert.match(bubbleStyles, /\.agent-stream\s*\{[^}]*align-content:\s*start/s);
  assert.doesNotMatch(bubbleStyles, /\.agent-stream\s*\{[^}]*align-content:\s*end/s);
});

test('workbench uses the new transparent ChatBoks logo assets', () => {
  const html = fs.readFileSync(path.join(__dirname, '../mobile_remote/www/workbench.html'), 'utf8');
  const mark = fs.readFileSync(path.join(__dirname, '../mobile_remote/www/assets/chatboks-mark.png'));
  const wordmark = fs.readFileSync(path.join(__dirname, '../mobile_remote/www/assets/chatboks-logo.png'));

  assert.match(html, /<img\s+src="\.\/assets\/chatboks-mark\.png"\s+alt="ChatBoks">/);
  assert.equal(mark.subarray(1, 4).toString('ascii'), 'PNG');
  assert.equal(mark.readUInt32BE(16), 512);
  assert.equal(mark.readUInt32BE(20), 512);
  assert.equal(mark[25], 6, 'app mark must use RGBA color type');
  assert.equal(wordmark[25], 6, 'full wordmark must use RGBA color type');
});

test('Lumen desktop starts in one focused agent thread and exposes comparison on demand', () => {
  const script = fs.readFileSync(path.join(__dirname, '../mobile_remote/www/workbench.js'), 'utf8');
  const css = fs.readFileSync(path.join(__dirname, '../mobile_remote/www/workbench.css'), 'utf8');

  assert.match(script, /laneView:\s*"task"/);
  assert.match(script, /const effectiveView = state\.laneView === "compare" \? "compare" : "task";/);
  assert.match(script, /effectiveView === "compare" \? "Return to chat" : "Compare agents"/);
  assert.doesNotMatch(css, /data-compact-workbench="true"\]\s+\.agent-pane:not\(\.is-compact-active\)/);
});

test('Lumen header renders the full ChatBoks wordmark as a palette-aware lockup', () => {
  const html = fs.readFileSync(path.join(__dirname, '../mobile_remote/www/workbench.html'), 'utf8');
  const css = fs.readFileSync(path.join(__dirname, '../mobile_remote/www/workbench.css'), 'utf8');
  const lockup = fs.readFileSync(path.join(__dirname, '../mobile_remote/www/assets/lumen-chatboks-lockup.png'));

  assert.match(html, /class="brand-wordmark"[^>]*aria-label="ChatBoks"/);
  assert.match(html, /class="brand-wordmark-image"\s+src="\.\/assets\/lumen-chatboks-lockup\.png"/);
  assert.match(css, /\.brand-wordmark-image\s*\{[^}]*object-fit:\s*contain/s);
  assert.equal(lockup[25], 6, 'generated lockup must use RGBA color type');
  assert.match(css, /\.compact-lane-switcher\s*\{\s*display:\s*none !important;/s);
  assert.match(css, /@media \(prefers-reduced-motion: reduce\)\s*\{[\s\S]*\.message-card\.streaming\s*\{\s*animation:\s*none/s);
});

test('Lumen conversation uses generated role symbols and message portraits', () => {
  const script = fs.readFileSync(path.join(__dirname, '../mobile_remote/www/workbench.js'), 'utf8');
  const css = fs.readFileSync(path.join(__dirname, '../mobile_remote/www/workbench.css'), 'utf8');
  const roles = ['claude', 'codex', 'spark', 'orchestrator'];

  assert.match(script, /const AGENT_SYMBOLS =/);
  assert.match(script, /const AGENT_AVATARS =/);
  for (const role of roles) {
    for (const kind of ['symbol', 'avatar']) {
      const asset = fs.readFileSync(path.join(__dirname, `../mobile_remote/www/assets/lumen-${role}-${kind}.png`));
      assert.equal(asset[25], 6, `${role} ${kind} must use RGBA color type`);
    }
  }
  assert.match(css, /data-lumen-embedded="true"\]\s+\.lane-tab-avatar\s*\{[^}]*width:\s*18px[^}]*object-fit:\s*contain/s);
  assert.match(css, /data-lumen-embedded="true"\]\s+\.message-identity img\s*\{[^}]*object-fit:\s*contain/s);
});

test('Lumen conversation separates agent bubbles from compact CodeGraph status', () => {
  const script = fs.readFileSync(path.join(__dirname, '../mobile_remote/www/workbench.js'), 'utf8');
  const css = fs.readFileSync(path.join(__dirname, '../mobile_remote/www/workbench.css'), 'utf8');

  assert.match(script, /function isCodegraphMessage\(text\)/);
  assert.match(script, /className = "conversation-context"/);
  assert.match(script, /className = user \? "message-row message-row-user" : "message-row"/);
  assert.match(script, /function renderMessageText\(target, text\)/);
  assert.match(script, /appendInlineMarkdown\(element, heading\[2\]\)/);
  assert.doesNotMatch(script, /messageText\.innerHTML\s*=/);
  assert.match(css, /\.message-row\s*\{/);
  assert.match(css, /\.conversation-context\s*\{/);
  assert.match(css, /\.message-card \.msg-text h1,/);
});

test('embedded Lumen mode has one host header and keeps model selection in the composer', () => {
  const html = fs.readFileSync(path.join(__dirname, '../mobile_remote/www/workbench.html'), 'utf8');
  const script = fs.readFileSync(path.join(__dirname, '../mobile_remote/www/workbench.js'), 'utf8');
  const css = fs.readFileSync(path.join(__dirname, '../mobile_remote/www/workbench.css'), 'utf8');

  assert.match(html, /id="activeModelSelect"/);
  assert.match(script, /function syncActiveModelControl\(\)/);
  assert.match(script, /chooseAgentModel\(agent, els\.activeModelSelect\)/);
  assert.match(css, /data-lumen-embedded="true"\]\s+\.workspace-topbar,[\s\S]*display:\s*none !important;/);
  assert.match(css, /data-lumen-embedded="true"\]\s+\.agent-header\s*\{[\s\S]*display:\s*none;/);
  assert.match(css, /data-lumen-embedded="true"\]\s+\.composer-card,[\s\S]*flex:\s*0 0 92px/);
});

test('embedded Lumen conversation uses the compact desktop density tokens', () => {
  const css = fs.readFileSync(path.join(__dirname, '../mobile_remote/www/workbench.css'), 'utf8');
  const embedded = css.slice(css.indexOf('/* Lumen owns the window chrome.'));

  assert.match(embedded, /--cb-type-body:\s*12px/);
  assert.match(embedded, /--cb-type-meta:\s*9px/);
  assert.match(embedded, /--cb-control-height:\s*32px/);
  assert.match(embedded, /\.lane-deck \.agent-lanes\[data-view="task"\][\s\S]*grid-template-columns:\s*minmax\(0, 1fr\);[\s\S]*min-width:\s*0;/);
  assert.match(embedded, /\.signal-card \.signal-copy strong[\s\S]*text-overflow:\s*ellipsis;[\s\S]*white-space:\s*nowrap;/);
  assert.match(embedded, /--cb-tab-height:\s*38px/);
  assert.match(embedded, /--cb-radius-sm:\s*6px/);
  assert.match(embedded, /\.lane-toolbar\s*\{[^}]*min-height:\s*var\(--cb-tab-height\)/s);
  assert.match(embedded, /\.message-row\s*\{[^}]*width:\s*min\(72%,\s*460px\)/s);
  assert.match(embedded, /\.message-identity\s*\{[^}]*width:\s*32px[^}]*height:\s*32px/s);
  assert.match(embedded, /\.message-card \.msg-text\s*\{[^}]*font-size:\s*var\(--cb-type-body\)/s);
  assert.match(embedded, /\.signal-card\s*\{[^}]*border-radius:\s*var\(--cb-radius-sm\)/s);
  assert.match(embedded, /#uploadButton,[\s\S]*#skillsButton\s*\{[^}]*display:\s*inline-flex !important/s);
  assert.match(embedded, /\.resume-panel\s*\{[^}]*max-height:\s*72px/s);
});

test('Lumen host can open projects and switch between conversation and original views', () => {
  const script = fs.readFileSync(path.join(__dirname, '../mobile_remote/www/workbench.js'), 'utf8');

  assert.match(script, /function isTrustedEmbeddedParent\(event\)/);
  assert.match(script, /event\.data\?\.type !== "chatboks:host-command"/);
  assert.match(script, /event\.data\.action === "open-project-picker"[\s\S]*openProjectPicker\(\)/);
  assert.match(script, /event\.data\.action === "set-view-mode"[\s\S]*applyEmbeddedViewMode\(event\.data\.mode\)/);
  assert.match(script, /dataset\.lumenEmbedded = String\(state\.lumenViewMode === "conversation"\)/);
  assert.match(script, /applyEmbeddedViewMode\(state\.lumenViewMode\)/);
});
