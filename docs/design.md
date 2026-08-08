# ChatBoks UI Design System

## Source and intent

This document reverse-engineers the visual system in the supplied 1039 x 882 reference screenshot. Measurements and colors are implementation targets inferred from pixels, not original source tokens. The goal is to reproduce the reference's density, hierarchy, proportions, and component treatment without copying its branding or artwork.

The interface should feel like a focused desktop tool: compact, quiet, precise, and operational. It should prioritize conversation content and decisions while keeping controls continuously available. Decoration is subordinate to state and function.

## Overall visual direction

- Desktop-native dark workbench with a near-black blue/green cast.
- Dense information layout with a tight vertical rhythm and minimal dead space.
- Flat hierarchy built from 1 px separators, small surface shifts, and restrained accent lines.
- Low-contrast translucency and gradients. Surfaces should remain readable without looking glossy.
- Cyan identifies live, selected, and primary-action states.
- Amber is reserved for approvals, warnings, and consequential decisions.
- Glow is local and faint. It may support an active control or status dot but must not become a background effect.
- Corners are lightly softened rather than pill-shaped. Large containers should not read as mobile cards.
- The transcript is the visual center. Navigation, status, approval, and composer regions are compact bands around it.

## Reference layout proportions

The reference uses an approximately 1022 x 866 px application shell inside a 1039 x 882 px capture.

| Region | Approximate target |
| --- | --- |
| Outer shell | 98.4% of viewport width, 98.2% of viewport height |
| Shell inset from viewport | 8-14 px |
| Header | 88-90 px |
| Agent tab strip | 52-54 px |
| Transcript | flexible, approximately 55-58% of shell height |
| Approval bar | 64-68 px including surrounding gap |
| Composer | 124-132 px |
| Main horizontal content inset | 16 px for structural bands, 24-40 px for transcript content |

At reduced desktop widths, preserve the header, tabs, approval bar, and composer heights. Give the transcript the remaining height and scroll it internally. Do not solve constrained space by enlarging controls or stacking every action vertically.

## Window and application shell

- Use one continuous application frame, not nested floating cards.
- Outer radius: `10px` target, acceptable range `8-12px`.
- Outer border: `1px solid rgba(132, 151, 153, 0.68)`.
- Inner keyline: optional `1px solid rgba(84, 104, 108, 0.28)` placed 8-12 px inside the outer frame.
- Shell background: `#061114` to `#091519`.
- Header and footer/composer may use a subtle vertical gradient no stronger than a 4-6% luminance change.
- The shell should occupy the window. Avoid a decorative page background inside the application.
- Keep the native window controls in the top-right and the product identity in the top-left.
- Window controls should be square, visually quiet, and aligned to the header baseline.

## Spacing scale

Use a compact 4 px base scale.

| Token | Value | Typical use |
| --- | ---: | --- |
| `space-1` | 4 px | icon/text gap, micro separation |
| `space-2` | 8 px | compact control gap, metadata gap |
| `space-3` | 12 px | button padding, bubble inner gap |
| `space-4` | 16 px | standard band padding, row gap |
| `space-5` | 20 px | transcript group spacing |
| `space-6` | 24 px | major horizontal inset |
| `space-8` | 32 px | rare section separation |

Rules:

- Default control gap: `8px`.
- Tab content padding: `12px 16px`.
- Message bubble padding: `12px 16px`.
- Transcript vertical gap between related message rows: `14-18px`.
- Gap after a message before its timestamp: `6-8px`.
- Avoid vertical padding above `20px` inside standard controls and bars.

## Typography

Use the application's existing desktop sans-serif stack. A suitable fallback is `Inter, "Segoe UI", system-ui, sans-serif`. Do not introduce a display face.

### Type scale

| Role | Size | Line height | Weight |
| --- | ---: | ---: | ---: |
| Product name | 22 px | 26 px | 400-500 |
| Section or approval title | 14 px | 20 px | 500-600 |
| Standard body/message | 14 px | 21 px | 400 |
| Button and tab label | 13 px | 18 px | 500 |
| Metadata/timestamp | 10-11 px | 14 px | 400-500 |
| Eyebrow/status label | 10-11 px | 14 px | 500-600 |

### Typography rules

- Keep letter spacing at `0` for body, controls, and tabs.
- Uppercase eyebrow labels may use `0.04em-0.08em`, never body copy.
- Use medium weight for hierarchy before increasing size.
- Avoid bold paragraphs. Message content remains regular weight.
- Text color, not size, should distinguish metadata from primary content.
- Keep message lines near `45-68` characters where layout permits.

## Component heights

| Component | Target height |
| --- | ---: |
| Header icon button | 42-44 px |
| Agent tab | 50-52 px |
| Compact text/button control | 38-42 px |
| Primary Send button | 44-46 px |
| Build action button | 38-40 px |
| Model dropdown | 42-44 px |
| Composer text field | 54-58 px |
| Composer toolbar row | 44-48 px |
| Agent avatar frame | 60-64 px |
| Status dot | 7-8 px |
| Scrollbar thumb | minimum 36 px visible length |

Controls should not exceed these values unless accessibility or localization requires it. Preserve at least a 36 px interaction target for compact desktop controls and 42 px for primary actions.

## Border radii

| Element | Radius |
| --- | ---: |
| Outer application shell | 10 px |
| Structural panel | 6-8 px |
| Message bubble | 7-8 px |
| Avatar frame | 7-8 px |
| Standard button/dropdown | 5-6 px |
| Composer field | 6 px |
| Status dot | 50% |

Avoid radii above `12px` on normal UI. Do not use full pills except for tiny status indicators where the content is intrinsically capsule-shaped.

## Borders

Borders create most of the hierarchy and should remain thin.

| Token | Suggested value | Use |
| --- | --- | --- |
| `border-subtle` | `rgba(112, 132, 136, 0.22)` | internal separators |
| `border-default` | `rgba(112, 132, 136, 0.36)` | inputs, bubbles, buttons |
| `border-strong` | `rgba(140, 158, 160, 0.58)` | outer shell, selected frame |
| `border-cyan` | `rgba(82, 216, 216, 0.68)` | active tab/focus |
| `border-amber` | `rgba(201, 143, 37, 0.55)` | approval and warning controls |

- Default thickness: `1px`.
- Selected tab underline: `2px` maximum.
- Do not use thick outlines, double borders, or bright borders around every surface.

## Color system

All values are approximate screenshot-derived targets. Contrast must be checked in implementation.

### Backgrounds and surfaces

| Token | Suggested value | Role |
| --- | --- | --- |
| `bg-app` | `#061114` | application base |
| `bg-transcript` | `#071317` | conversation field |
| `surface-1` | `#0c171b` | header, composer, structural controls |
| `surface-2` | `#121d21` | agent bubble, dropdown, inactive control |
| `surface-3` | `#172327` | selected tab and hover surface |
| `surface-user` | `#0d2929` | user message bubble |
| `surface-warning` | `#17170f` | approval/action bar |
| `surface-disabled` | `#0d1518` | disabled controls |

Low-contrast gradients may blend adjacent values, for example `linear-gradient(180deg, #0d181c 0%, #091418 100%)`. Keep the endpoints within roughly 6% perceived luminance of each other.

### Text

| Token | Suggested value |
| --- | --- |
| `text-primary` | `#d6dcdd` |
| `text-secondary` | `#a4afb2` |
| `text-muted` | `#7f8b8f` |
| `text-faint` | `#5f6b70` |
| `text-on-primary` | `#061114` |

### Accents

| Token | Suggested value | Use |
| --- | --- | --- |
| `accent-cyan` | `#55d8d7` | active tab, live state, handoff icon |
| `accent-cyan-strong` | `#31cbd6` | primary action edge/background |
| `accent-cyan-soft` | `rgba(85, 216, 215, 0.10)` | selected and user surfaces |
| `accent-amber` | `#d39a32` | approval label and warning icon |
| `accent-amber-soft` | `rgba(211, 154, 50, 0.08)` | approval surface tint |
| `status-online` | `#54d9d3` | online/live dot |

Do not use cyan on every border or label. Reserve it for current selection, availability, focus, and the primary action.

## Shadows and glow

- Structural shadow: `0 10px 30px rgba(0, 0, 0, 0.24)` on the application shell only.
- Bubble shadow: `0 6px 16px rgba(0, 0, 0, 0.18)` or none.
- Active cyan glow: `0 0 12px rgba(85, 216, 215, 0.10)`.
- Amber approval glow: `0 0 14px rgba(211, 154, 50, 0.08)`.
- Avoid blur radii above `24px` inside the application.
- Never use glow as the only state indicator; pair it with border, underline, text, or icon changes.

## Header and window controls

- Product eyebrow and title align left in a compact two-line block.
- Live status aligns near the right controls and uses one 7-8 px cyan dot plus a 10-11 px label.
- Window controls are approximately `42 x 42px`, separated by `12-16px`.
- Control icons are `14-16px`, centered optically.
- Default control surface is nearly transparent with a subtle border.
- Hover raises the surface one step and increases border opacity; it does not scale.
- Close/stop affordances may gain a restrained red tint on hover only.

## Navigation tabs

- Use one full-width horizontal tab strip directly below the header.
- Four equal columns in the reference; each tab is approximately 25% of the strip.
- Height: `50-52px` plus a `2px` active underline.
- Separate tabs with `1px` vertical rules.
- Inactive state: transparent/dark surface, muted icon and text.
- Hover state: `surface-2`, text promoted to `text-secondary` or `text-primary`.
- Active state: `surface-3`, primary text, cyan icon, and a `2px` cyan bottom edge.
- Keep tab icons `14-16px` and label gap `8-10px`.
- Do not make the tabs pills or independent cards.

## Chat and message bubbles

### Agent messages

- Left aligned with a separate avatar column.
- Bubble width is content-driven with a practical maximum of `420-460px` at the reference width.
- Background: `surface-2` with a subtle top-to-bottom dark gradient.
- Border: `1px solid border-default`.
- Radius: `7-8px`.
- Padding: `11-13px 16px`.
- Message text: `14px/21px`, regular weight.
- Optional tail is small and structural, approximately `10-12px`; omit it if it adds noise.

### User messages

- Right aligned and narrower than the longest agent response.
- Background: `surface-user` with a 6-10% cyan tint.
- Border: `1px solid rgba(85, 216, 215, 0.20)`.
- Keep the `YOU` label outside and above the bubble in muted 10-11 px uppercase text.
- Use a restrained cyan double-check or sent indicator after the timestamp when available.

### Message rhythm

- Agent avatar and bubble top edges align.
- Timestamps sit outside the bubble, 6-8 px below it.
- Keep 24-32 px between independent messages.
- System handoffs use an inline divider rather than a full bubble.
- Long messages must wrap naturally and remain scrollable; do not allow horizontal overflow.

## Agent avatars

- Avatar frame: `60-64px` square in the reference composition.
- Image occupies most of the frame with `3-5px` inner breathing room.
- Radius: `7-8px`.
- Border: `1px solid rgba(102, 152, 164, 0.55)`.
- Background behind transparent artwork: near-black with a very subtle cyan cast.
- Artwork should use `object-fit: cover` or `contain` according to the source asset, never stretch.
- Avatar lighting may carry stronger color than the surrounding UI, but the frame must stay quiet.
- At compact desktop widths, reduce to `40-48px` before removing the avatar entirely.

## Timestamps and metadata

- Size: `10-11px`.
- Weight: `400-500`.
- Color: `text-muted` or `text-faint`.
- Place 6-8 px below the associated bubble.
- User timestamps align right; agent timestamps align with bubble content, not the avatar edge.
- Do not place timestamps in badges or chips.
- System transition timestamps can sit inline with the handoff label.

## Status indicators

- Live/online dot: `7-8px`, circular, `status-online`.
- Pair the dot with a short text label; do not rely on color alone.
- Optional glow must remain below `12px` blur and 12% opacity.
- Working state may use a slow opacity pulse or icon rotation, with a reduced-motion static fallback.
- Pending state uses muted slate.
- Warning/approval state uses amber.
- Error state should use restrained red only when an actual error requires intervention.

## Handoff divider

- Center the handoff label between two `1px` horizontal rules.
- Divider width: approximately 45-55% of the transcript.
- Use a `14-16px` cyan transfer icon.
- Label and timestamp: `10-11px`, muted.
- No container background, oversized badge, or strong glow.

## Approval and action bar

- Treat approval as a compact full-width decision band near the composer.
- Height: `64-66px` including its own padding.
- Radius: `6px`.
- Background: `surface-warning` with `accent-amber-soft` tint.
- Border: `1px solid border-amber`.
- Left section: `18-20px` warning icon, 14 px medium label, 10-12 px gap.
- Right section: compact build buttons, `38-40px` high, aligned in one row.
- Build buttons use a dark neutral fill, amber border, and amber text.
- Hover increases amber border opacity and surface tint slightly.
- The bar must remain visually quieter than the cyan Send action.
- On constrained widths, allow action labels to wrap to two lines or move to an anchored menu before stacking the entire band vertically.

## Buttons

### Primary button

- Height: `44-46px`.
- Radius: `5-6px`.
- Horizontal padding: `18-22px`.
- Background: low-contrast cyan gradient from `accent-cyan-strong` to `accent-cyan`.
- Text: `text-on-primary`, 13 px, weight 600.
- Icon: `15-17px` with 8 px gap.
- Hover: raise luminance by approximately 5%, strengthen the border, keep geometry unchanged.
- Pressed: reduce luminance by approximately 4%; no exaggerated movement.

### Secondary button

- Height: `38-42px`.
- Radius: `5-6px`.
- Background: `surface-1` or transparent.
- Border: `1px solid border-default`.
- Text: `text-secondary`.
- Hover: use `surface-2` and `text-primary`.

### Warning/action button

- Same geometry as a secondary button.
- Amber text and border; avoid a solid bright amber fill.

## Composer and input area

- The composer is a structural footer, not a floating oversized card.
- Outer composer height: `124-132px`.
- Border: `1px solid border-default`.
- Radius: `6-8px`.
- Background: `surface-1` with a low-contrast vertical gradient.
- Top text field height: `54-58px`.
- Text field padding: `0 16-18px`.
- Placeholder: `14px`, `text-muted`.
- Toolbar sits below with an `8px` gap and compact controls aligned to the bottom edge.
- Left side: Skills and attachment controls.
- Right side: model dropdown followed by Send.
- Preserve the single-row toolbar at the reference width.
- Focus should affect the input border and a local 1 px cyan ring, not the entire composer.

## Dropdowns

- Height: `42-44px`.
- Radius: `5-6px`.
- Background: `surface-1` or `surface-2`.
- Border: `1px solid border-default`.
- Label: 13 px, medium weight.
- Leading icon: `15-16px`; chevron: `12-14px`.
- Internal horizontal padding: `12-14px`.
- Menu rows: `34-38px` high.
- Selected menu row uses a faint cyan wash and primary text.
- Do not use oversized native-select padding or tall mobile menu rows.

## Scrollbars

- Keep the transcript scrollbar visible but unobtrusive.
- Total scrollbar area: `10-12px`; visible thumb width: `5-6px`.
- Track: transparent or `rgba(255, 255, 255, 0.02)`.
- Thumb: `rgba(119, 136, 140, 0.38)`.
- Hover thumb: `rgba(119, 151, 157, 0.58)`.
- Radius: `4px`.
- Place it 10-16 px inside the shell edge when the layout permits.
- Maintain a minimum 36 px thumb length and native wheel/trackpad behavior.

## Icon sizing

| Context | Size |
| --- | ---: |
| Metadata/status | 10-12 px |
| Tab and compact button | 14-16 px |
| Primary action | 15-17 px |
| Approval warning | 18-20 px |
| Window control | 14-16 px |

- Use one consistent stroke family.
- Default stroke width: approximately `1.5px`.
- Icons should inherit text color unless the state requires cyan or amber.
- Avoid decorative icon containers when a standard symbol is already recognizable.

## Interaction states

### Hover

- Increase surface luminance by one token step.
- Increase border opacity by approximately 12-18 percentage points.
- Promote muted text to secondary or primary text.
- Keep scale, radius, and layout unchanged.
- Use transitions of `100-160ms` with a standard ease-out curve.

### Active and selected

- Tabs use a cyan icon, primary text, slightly raised surface, and 2 px underline.
- Selected dropdown rows use a faint cyan wash.
- Pressed buttons darken slightly and retain a crisp 1 px border.
- Active state must remain readable without glow.

### Focus-visible

- Use a `1px` cyan focus ring plus a `2px` transparent offset, or an equivalent inset/outer treatment that does not shift layout.
- Do not remove the native focus affordance unless it is replaced with an equally visible one.
- Focus order should follow header controls, tabs, transcript actions, approval actions, then composer controls.

### Disabled

- Reduce opacity to `0.42-0.50`.
- Remove glow and strong accent color.
- Keep labels readable enough to identify the unavailable action.
- Use the default cursor and suppress hover elevation.
- Do not communicate disabled state through color alone; set the actual disabled attribute and expose it semantically.

### Loading and working

- Keep layout dimensions fixed.
- Use a small inline spinner or restrained status-dot animation.
- Avoid full-surface overlays unless interaction must be blocked.
- Respect `prefers-reduced-motion` and provide a static working state.

## Visual noise constraints

- Maximum one strong cyan element per local control group.
- Maximum one amber decision band visible at a time unless multiple approvals are independently actionable.
- No decorative gradient orbs, bokeh, thick neon frames, or large blurred shadows.
- No card nesting for structural page regions.
- No headings above 22 px inside this application shell.
- No standard control taller than 46 px, excluding the composer text field and avatar.
- Avoid empty transcript space caused by fixed-height bubbles or oversized status cards.

## Implementation checklist

- [ ] At a `1039 x 882px` reference viewport, the application shell stays within `8-14px` of every edge.
- [ ] The outer shell radius is `8-12px` and every standard border is exactly `1px`.
- [ ] Header height is `88-90px`; agent tab height is `50-52px`; composer height is `124-132px`.
- [ ] Transcript receives all remaining vertical space and scrolls internally without moving the header, tabs, approval bar, or composer.
- [ ] The active tab has a `2px` cyan underline and no pill-shaped container.
- [ ] Standard body copy is `14px` with `20-22px` line height; metadata is `10-11px`.
- [ ] Product title does not exceed `22px`; no other heading exceeds `16px`.
- [ ] Agent bubbles use `11-13px` vertical and `16px` horizontal padding with a maximum width of `460px` at the reference viewport.
- [ ] User bubbles are right aligned, use a faint cyan surface, and remain narrower than `420px` at the reference viewport.
- [ ] Agent avatar frames are `60-64px` square at the reference viewport and never stretch their artwork.
- [ ] Independent message groups have `24-32px` vertical separation; bubble-to-timestamp spacing is `6-8px`.
- [ ] Approval bar height is `64-66px`, with amber used only for its border, icon, label, and action emphasis.
- [ ] Secondary/build controls are `38-42px` high; the Send control is `44-46px` high.
- [ ] Composer text field is `54-58px` high and the lower toolbar remains one row at widths of `900px` or greater.
- [ ] Dropdowns are `42-44px` high and menu rows are `34-38px` high.
- [ ] Tab/button icons are `14-16px`; approval icons are `18-20px`.
- [ ] The scrollbar thumb is `5-6px` wide, at least `36px` long, and remains visible against the transcript.
- [ ] Hover transitions complete in `100-160ms` without scaling or layout movement.
- [ ] Focus-visible is represented by a cyan ring/outline that does not shift component geometry.
- [ ] Disabled controls use the semantic disabled state, `0.42-0.50` visual opacity, and no glow.
- [ ] Cyan glow opacity stays at or below `12%`; amber glow opacity stays at or below `10%`.
- [ ] Low-contrast surface gradients stay within approximately `6%` perceived luminance from start to end.
- [ ] Primary text, body text, interactive text, and status labels are contrast-tested against their final implemented backgrounds.
- [ ] At `200%` zoom, controls remain reachable, text does not overlap, and the transcript still has an independent scroll region.
- [ ] Keyboard order follows the visible hierarchy and every button, tab, dropdown, and composer action has a visible focus state.
- [ ] `prefers-reduced-motion` disables pulsing, spinner rotation where practical, and nonessential glow animation.
- [ ] No application code is changed until this design specification is reviewed and accepted.
