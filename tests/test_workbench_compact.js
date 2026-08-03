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

test('embedded compact CSS keeps one lane and the composer inside the viewport', () => {
  const css = fs.readFileSync(path.join(__dirname, '../mobile_remote/www/workbench.css'), 'utf8');
  assert.match(css, /data-compact-workbench=["']true["']/);
  assert.match(css, /\.agent-pane:not\(\.is-compact-active\)/);
  assert.match(css, /height:\s*100dvh/);
});
