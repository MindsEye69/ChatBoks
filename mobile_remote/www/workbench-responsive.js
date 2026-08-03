(function initWorkbenchResponsive(globalObject, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  if (globalObject) globalObject.ChatBoksWorkbenchResponsive = api;
})(typeof window !== 'undefined' ? window : globalThis, function createWorkbenchResponsive() {
  function canonicalLane(value) {
    return String(value || '')
      .trim()
      .toLowerCase()
      .replace(/[-\s]+/g, '_')
      .replace(/^(?:agent_zero|agentzero|az)$/, 'coordinator');
  }

  function resolveCompactLane({ lanes = [], current = '', nextAgent = '', previousNextAgent = '' } = {}) {
    const roster = [...new Set(lanes.map(canonicalLane).filter(Boolean))];
    if (!roster.length) return '';

    const active = canonicalLane(current);
    const next = canonicalLane(nextAgent);
    const previousNext = canonicalLane(previousNextAgent);
    const routeChanged = Boolean(next) && next !== previousNext;

    if (routeChanged && roster.includes(next)) return next;
    if (roster.includes(active)) return active;
    if (roster.includes(next)) return next;
    return roster[0];
  }

  return { canonicalLane, resolveCompactLane };
});
