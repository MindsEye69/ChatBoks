(function exposeLumenTheme(root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  if (root) root.ChatBoksLumenTheme = api;
})(typeof window !== "undefined" ? window : globalThis, function createLumenThemeApi() {
  "use strict";

  const HEX = /^#[0-9a-f]{6}$/i;
  const ALLOWED_KEYS = new Set([
    "version", "paletteId", "background", "surface", "primary", "secondary",
    "text", "mutedText", "border", "glow", "material", "shape", "motion",
  ]);
  const MATERIALS = new Set(["deep-glass", "frosted", "solid"]);
  const SHAPES = new Set(["circle", "hex", "rounded-hex"]);
  const MOTIONS = new Set(["off", "subtle", "expressive"]);

  function isValidLumenThemeSnapshot(value) {
    if (!value || typeof value !== "object" || Array.isArray(value)) return false;
    if (Object.keys(value).some((key) => !ALLOWED_KEYS.has(key))) return false;
    if (Object.keys(value).length !== ALLOWED_KEYS.size || value.version !== 1) return false;
    if (typeof value.paletteId !== "string" || !value.paletteId || value.paletteId.length > 64) return false;
    for (const key of ["background", "surface", "primary", "secondary", "text", "mutedText", "border"]) {
      if (typeof value[key] !== "string" || !HEX.test(value[key])) return false;
    }
    return Number.isFinite(value.glow) && value.glow >= 0 && value.glow <= 2
      && MATERIALS.has(value.material) && SHAPES.has(value.shape) && MOTIONS.has(value.motion);
  }

  function hexChannels(hex) {
    return [1, 3, 5].map((index) => Number.parseInt(hex.slice(index, index + 2), 16));
  }

  function rgba(hex, alpha) {
    const [red, green, blue] = hexChannels(hex);
    return `rgba(${red}, ${green}, ${blue}, ${alpha})`;
  }

  function relativeLuminance(hex) {
    const channels = hexChannels(hex).map((value) => {
      const channel = value / 255;
      return channel <= 0.03928 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4;
    });
    return channels[0] * 0.2126 + channels[1] * 0.7152 + channels[2] * 0.0722;
  }

  function parseEmbeddedSessionUrl(value) {
    try {
      const url = new URL(value);
      const loopback = url.hostname === "127.0.0.1" || url.hostname === "localhost" || url.hostname === "[::1]";
      if (url.protocol !== "http:" || !loopback || !url.port || url.username || url.password) return null;
      if (url.pathname !== "/workbench" || url.search !== "?embedded=1") return null;
      const sessionToken = new URLSearchParams(url.hash.slice(1)).get("sessionToken") || "";
      if (!sessionToken || sessionToken.length > 256) return null;
      return { bridgeUrl: url.origin, sessionToken };
    } catch {
      return null;
    }
  }

  function applyLumenThemeSnapshot(rootElement, snapshot) {
    if (!rootElement || !isValidLumenThemeSnapshot(snapshot)) return false;
    const style = rootElement.style;
    const accentWash = rgba(snapshot.primary, 0.14);
    const borderSoft = rgba(snapshot.border, 0.62);
    const glow = rgba(snapshot.primary, Math.min(0.58, 0.16 + snapshot.glow * 0.2));
    const tokens = {
      "--theme-bg1": snapshot.background,
      "--theme-bg2": snapshot.surface,
      "--theme-bg3": snapshot.background,
      "--ground": snapshot.background,
      "--ground-sunk": `color-mix(in srgb, ${snapshot.background} 88%, black)`,
      "--surface": snapshot.surface,
      "--surface-2": `color-mix(in srgb, ${snapshot.surface} 88%, ${snapshot.secondary})`,
      "--line": borderSoft,
      "--line-strong": snapshot.border,
      "--border-strong": snapshot.border,
      "--text": snapshot.text,
      "--muted": snapshot.mutedText,
      "--faint": `color-mix(in srgb, ${snapshot.mutedText} 72%, ${snapshot.background})`,
      "--accent": snapshot.primary,
      "--accent-wash": accentWash,
      "--accent-ink": snapshot.background,
      "--teal": snapshot.primary,
      "--info": snapshot.secondary,
      "--chrome": snapshot.mutedText,
      "--sheen": rgba(snapshot.text, 0.03),
      "--lane-claude": snapshot.primary,
      "--lane-codex": snapshot.secondary,
      "--lane-coord": snapshot.text,
      "--lane-spark": snapshot.mutedText,
      "--mark-shadow": `0 3px 8px ${rgba(snapshot.background, 0.5)}`,
      "--shadow": `0 1px 0 ${borderSoft}, 0 18px 44px ${rgba(snapshot.background, 0.56)}`,
      "--lumen-glow": glow,
    };
    for (const [name, value] of Object.entries(tokens)) style.setProperty(name, value);
    rootElement.dataset.theme = "lumen";
    rootElement.dataset.lumenEmbedded = "true";
    if (rootElement.style) rootElement.style.colorScheme = relativeLuminance(snapshot.background) > 0.5 ? "light" : "dark";
    return true;
  }

  return { applyLumenThemeSnapshot, isValidLumenThemeSnapshot, parseEmbeddedSessionUrl };
});
