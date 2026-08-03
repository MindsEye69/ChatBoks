const assert = require('node:assert/strict');
const test = require('node:test');
const {
  applyLumenThemeSnapshot,
  isValidLumenThemeSnapshot,
  parseEmbeddedSessionUrl,
} = require('../mobile_remote/www/lumen-theme.js');

const snapshot = {
  version: 1,
  paletteId: 'Aurora',
  background: '#03100d',
  surface: '#061d18',
  primary: '#5eead4',
  secondary: '#a3e68c',
  text: '#eafff9',
  mutedText: '#90aaa3',
  border: '#2d6759',
  glow: 0.5,
  material: 'deep-glass',
  shape: 'circle',
  motion: 'subtle',
};

test('validates the strict appearance-only Lumen snapshot contract', () => {
  assert.equal(isValidLumenThemeSnapshot(snapshot), true);
  assert.equal(isValidLumenThemeSnapshot({ ...snapshot, path: 'C:/secret' }), false);
  assert.equal(isValidLumenThemeSnapshot({ ...snapshot, primary: 'red' }), false);
  assert.equal(isValidLumenThemeSnapshot({ ...snapshot, version: 2 }), false);
});

test('maps a Lumen snapshot onto the existing ChatBoks design tokens', () => {
  const values = new Map();
  const root = {
    dataset: {},
    style: { setProperty: (name, value) => values.set(name, value) },
  };

  assert.equal(applyLumenThemeSnapshot(root, snapshot), true);
  assert.equal(root.dataset.theme, 'lumen');
  assert.equal(root.dataset.lumenEmbedded, 'true');
  assert.equal(values.get('--ground'), snapshot.background);
  assert.equal(values.get('--surface'), snapshot.surface);
  assert.equal(values.get('--accent'), snapshot.primary);
  assert.equal(values.get('--lane-codex'), snapshot.secondary);
  assert.equal(values.get('--text'), snapshot.text);
  assert.equal(values.get('--border-strong'), snapshot.border);
});

test('reads the embedded bearer token only from the fragment', () => {
  assert.deepEqual(
    parseEmbeddedSessionUrl('http://127.0.0.1:43123/workbench?embedded=1#sessionToken=abc%2F123'),
    { bridgeUrl: 'http://127.0.0.1:43123', sessionToken: 'abc/123' },
  );
  assert.equal(
    parseEmbeddedSessionUrl('http://127.0.0.1:43123/workbench?embedded=1&sessionToken=leak'),
    null,
  );
  assert.equal(parseEmbeddedSessionUrl('http://localhost/workbench?embedded=1#sessionToken=x'), null);
  assert.equal(parseEmbeddedSessionUrl('http://localhost:43123/workbench?embedded=1&extra=1#sessionToken=x'), null);
  assert.equal(parseEmbeddedSessionUrl('https://example.com/workbench?embedded=1#sessionToken=x'), null);
});
