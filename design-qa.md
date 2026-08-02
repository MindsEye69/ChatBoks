# Lumen design QA

**Source visual truth**

- `C:\Users\rowbi\Desktop\Skärmbild 2026-07-31 202740.png`
- Source pixels: 1920 × 1294 at 1×. The top 56 px are Claude Design chrome; the app-owned reference region is 1920 × 1238.

**Rendered implementation**

- `C:\Users\rowbi\Desktop\Organized\Under Development\Chatboks\lumen-workbench-pass2.png`
- Browser viewport and implementation pixels: 1280 × 720 at device scale factor 1.
- State: local offline preview with live project/environment mock data. The reference shows a mid-session approval state, so content and proposal visibility intentionally follow different runtime data.
- Combined comparison: `C:\Users\rowbi\Desktop\Organized\Under Development\Chatboks\lumen-design-comparison.png`
- Density normalization: the app-owned reference region was proportionally downsampled to 1117 × 720; the implementation stayed at native 1280 × 720. Both are shown at equal height in the combined comparison.

**Findings**

- No actionable P0/P1/P2 visual mismatch remains. The implementation preserves the reference composition: rounded full-width header, copper-on-near-black palette, three-column shell, 2 × 2 lane grid, card hierarchy, fixed telemetry strip, floating decision dock, and large composer.
- Runtime-state difference is accepted: proposal content appears only when the bridge reports an approval/attention state. It was not hard-coded for visual parity.
- Fonts and typography: Sora, monospaced metadata, weights, uppercase labels, and compact hierarchy match the reference. Responsive truncation protects model controls at 1280 px.
- Spacing and layout rhythm: desktop proportions, 16 px gutters, 20–26 px radii, lane gaps, header rhythm, and composer placement match. The 1280 px responsive layout intentionally gives rails a slightly larger share than the 1920 px source.
- Colors and tokens: warm black/brown surfaces, copper accent, amber warning, green health, violet Codex, teal Orchestrator, and coral send treatment match the selected direction.
- Image quality and assets: the supplied ChatBoks and agent PNG assets are used directly; no placeholders replace visible custom artwork.
- Copy and content: app-owned labels match the source vocabulary. Dynamic project, branch, agent, model, progress, and task text correctly comes from the bridge.

**Focused region comparison**

- Header, round bar, lane headers, left token cards, workspace card, and composer are readable in `lumen-design-comparison.png`; no additional crop was needed.

**Interaction and browser checks**

- Focus mode toggled on and off.
- Project picker opened and closed.
- Connection panel opened and closed.
- Browser console: no warnings or errors.
- Horizontal/vertical document overflow at 1280 × 720: none.

**Comparison history**

1. Pass 1 found the legacy 1320 px breakpoint applying three columns inside the right rail, compressing Workspace and Monitor.
2. Added an explicit single-column right-rail track for Lumen.
3. Pass 2 measured the corrected 330 px right rail, 330 px monitor strip, and 1280 × 720 document with no page overflow.

**Follow-up polish**

- P3: A future tall-viewport capture can validate the approval overlay against a live `awaiting_approval` session at the exact 1920 × 1238 source viewport.

Initial redesign result: passed

## Theme family addendum

- ZIP source: `C:\Users\rowbi\Desktop\ChatBoks Lumen visual redesign.zip`
- Monochrome capture: `C:\Users\rowbi\Desktop\Organized\Under Development\Chatboks\theme-monochrome.png`
- Verified at the active responsive browser viewport: the selector contains only Lumen, Ember, Verdant, and Monochrome. All four retain the Lumen Workbench layout with no document-width overflow.
- Active palette pairs:
  - Lumen: `#8ab6ff` / `#c792ff`
  - Ember: `#ffab5e` / `#ff6f7d`
  - Verdant: `#5ce6a8` / `#7fd8ff`
  - Monochrome: soft-green text `#c4dccb`, muted text `#91a99a`, accent `#a8cbb3`, graphite ground `#070908`
- Each swatch exposes the correct accessible name, pressed state, persisted theme key, and layout class.
- Legacy Carbon, Chrome, Console, and Orchid saved values migrate safely to Lumen or Monochrome.
- Browser console: no warnings or errors after cycling through all four themes.

final result: passed

## Spark avatar addendum

- Source asset: `assets/spark.png` from `C:\Users\rowbi\Desktop\ChatBoks Lumen visual redesign.zip`.
- Rendered capture: `C:\Users\rowbi\Desktop\Organized\Under Development\Chatboks\spark-helmet-verified.png`.
- The source and installed PNG are byte-identical.
- Browser verification: the lane heading is `Spark`; the resolved image is `/assets/spark.png`, reports complete, and renders at its intrinsic 559 × 520 pixels.
- Bridge verification: `/assets/spark.png` returns HTTP 200 with `image/png` and 388,817 bytes.

Spark avatar result: passed

## Restored chat-column layout

- Layout source: `C:\Users\rowbi\Desktop\Skärmbild 2026-07-31 202639.png` (2048 × 1536).
- Responsive implementation capture: `C:\Users\rowbi\Desktop\Organized\Under Development\Chatboks\chat-columns-restored.png` (1280 × 720).
- Restored structure: Claude, Codex, Spark, and Orchestrator render in one equal-width row at desktop sizes; the prompt composer occupies roughly the lower third of the work area.
- Preserved styling: the active Lumen-family palette, rounded cards, typography, borders, shadows, avatar assets, and theme selector are unchanged.
- Narrow desktop verification at 1280 × 720: four columns, one row, 250 px composer, no document-width overflow. Compact lane headers hide secondary controls when the available lane width cannot fit them.
- Mobile behavior below 820 px remains the existing single-column layout.

Restored chat layout result: passed

## Adjustable composer and blocker panel

- Source state: `C:\Users\rowbi\Desktop\Skärmbild 2026-07-31 215046.png`.
- Control capture: `C:\Users\rowbi\Desktop\Organized\Under Development\Chatboks\composer-resize-control.png`.
- The prompt composer now defaults to a smaller 300 px height and can be resized vertically from its centered top handle.
- Resizing is bounded between 170 px and the available work-area height minus 250 px, preserving usable agent lanes.
- Keyboard controls: Arrow Up/Down adjust by 24 px, Home selects minimum, End selects maximum, and double-click resets the height.
- The selected height persists after reload; browser QA changed 300 px to 276 px and confirmed 276 px after reload.
- Blocking/question panels expose a `Hide` control. Collapsed panels retain a compact `Show blocker` row, and a new blocker automatically expands again.
- Theme palette, four-column lanes, agent assets, and mobile single-column behavior remain unchanged.

Adjustable composer result: passed

## Focus full-screen repair

- Verified capture: `C:\Users\rowbi\Desktop\Organized\Under Development\Chatboks\focus-fullscreen-fixed.png`.
- Focus now hides the top bar and both side rails, then changes the shell to one full-width and full-height grid cell.
- At the 1280 × 720 QA viewport, the work area expands from 632 px to 1,252 px while keeping 14 px outer padding.
- The round bar, all four agent lanes, adjustable composer, avatars, and active theme remain visible.
- Exiting Focus restores the 632 px three-column desktop layout and the top bar without horizontal overflow.

Focus full-screen result: passed

## Narrow chat text wrapping

- Source state: `C:\Users\rowbi\Desktop\Skärmbild 2026-07-31 220726.png`.
- QA capture: `C:\Users\rowbi\Desktop\Organized\Under Development\Chatboks\narrow-chat-text-wrapped.png`.
- Agent streams and every direct grid child now use `min-width: 0` and `max-width: 100%`, preventing content-sized cards from extending behind the lane crop.
- Message text, signal labels, timestamps, and copyable response cards use `overflow-wrap: anywhere` with a break-word fallback.
- Normal four-column QA: four populated message streams at 135 px content width, zero overflowing cards, and zero overflowing text nodes.
- Focus QA: 290–336 px stream widths with zero overflowing cards or text nodes.
- Vertical scrolling remains available for long conversations; no content is discarded or visually clipped at the right edge.

Narrow chat wrapping result: passed

## Maximized normal-mode wrapping hardening

- QA capture: `C:\Users\rowbi\Desktop\Organized\Under Development\Chatboks\maximized-wrap-fixed.png`.
- Agent-card container queries now activate wrapping from the actual lane width (≤340 px), independent of the overall window size.
- In narrow lanes, streams, cards, signals, and message text are explicitly `width: 100%` with border-box sizing and hidden horizontal stream overflow.
- Long unbroken CLI tokens use `word-break: break-all` only in narrow lanes; wider Focus lanes keep the more natural `overflow-wrap: anywhere` behavior.
- Maximized normal-mode QA at the narrow test breakpoint: four 146 px lanes, 109 px cards, 89 px text regions, and zero horizontal overflow.

Maximized normal-mode wrapping result: passed

## WRAPFIX 2 exact reproduction

- Exact test string: the full Claude CLI failure shown in `Skärmbild 2026-07-31 222408.png`, including its explicit newline.
- Exact-string rendering in current source: message text 89 px client/scroll width, card 109 px client/scroll width, and no missing characters or horizontal overflow.
- Added inline-size containment to every narrow-lane stream child so intrinsic text width cannot affect grid sizing.
- Updated CSS and JavaScript cache keys to `20260731-wrapfix2`.
- Added a visible `WRAPFIX 2` badge beside the ChatBoks brand; absence of this badge proves that an older executable/UI asset set is running.
- Identified capture: `C:\Users\rowbi\Desktop\Organized\Under Development\Chatboks\wrapfix2-identified.png`.

WRAPFIX 2 result: passed

## Compact mobile agent tabs

- Selected ImageGen reference: `C:\Users\rowbi\Desktop\Organized\Under Development\Chatboks\mobile-layout-reference.png` (393 × 852 aspect ratio).
- Implemented target: automatic compact mode at 820 px and below, plus coarse-pointer devices up to 1024 px.
- Normal PC and Focus layouts always retain the simultaneous four-column agent view; the tab toolbar is rendered only in compact mode.
- Implemented hierarchy: compact header, horizontally scrollable model tabs with source avatar assets, one active agent transcript, handoff status, decision dock, and a composer pinned to the bottom safe area.
- Handoffs now expose bounded `handoff_to` and `handoff_reason` values from the bridge. A new explicit handoff fingerprint switches the selected tab even when the same `next_agent` was already known; a later manual choice remains pinned until the next real transition.
- Mobile tab interaction includes automatic `scrollIntoView`, Arrow Left/Right wrapping, Home/End navigation, roving tab focus, and linked `tab`/`tabpanel` accessibility state.
- The handoff band uses the supplied agent PNG assets and is compact-mode-only, preserving the existing desktop composition.
- Static and automated checks cover the responsive mode, handoff markup, handoff snapshot metadata, word wrapping, JavaScript syntax, and the complete Python suite (455 passed, 1 skipped).
- Browser visual capture at 393 × 852 could not be completed because the in-app browser security policy blocks local `127.0.0.1` page automation. No alternate browser or policy workaround was used.

Compact mobile design result: blocked pending visual browser capture

final result: blocked
