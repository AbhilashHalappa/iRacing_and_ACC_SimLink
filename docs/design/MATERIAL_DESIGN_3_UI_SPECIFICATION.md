# Race Engineer ACC — Material Design 3 UI Design System

**Status:** Design specification prepared; visual review and implementation pending  
**Design standard:** Material Design 3 (M3)  
**Palette authority:** `docs/UI_REBUILD_ROADMAP.md`, Section 11, in the source repository  
**Architecture:** Hybrid standalone Windows desktop application  
**Last design-direction approvals recorded:** 2026-11-03

---

## 1. Purpose and Scope

This document defines how Material Design 3 is applied to the Race Engineer ACC desktop UI.

M3 is the component, layout, typography, interaction and accessibility standard. The project's existing approved purple/teal palette is retained exactly. M3 adoption does not authorize a brand-colour refresh or replacement palette.

This specification covers:
- The embedded-browser main application UI.
- Shared visual patterns used by native Qt surfaces where practical.
- The shared component and interaction language for future page migrations.
- The visual boundary between the main application, native overlays and Hardware Companion.

It does not change telemetry, coaching, strategy, replay, storage, hardware protocols, runtime ownership or application code.

The main application uses a PySide6 desktop host containing QtWebEngine, with a locally bundled React + TypeScript frontend. Native Qt remains responsible for floating overlays and Hardware Companion initially.

## 2. Non-Negotiable Design Decisions

1. Follow Material Design 3 patterns and guidance.
2. Use the exact Section 11 palette below as the source of truth.
3. Do not replace the palette with a generated Material You dynamic-colour scheme, blue/teal seed palette or new brand palette.
4. Do not copy mobile layouts literally; design for a desktop sim-racing application.
5. Prioritize telemetry readability, information density, glance recognition and keyboard operation.
6. Use one documented token vocabulary across browser and native Qt presentation where practical.
7. Do not apply a global stylesheet that unexpectedly changes legacy pages or native widgets.
8. Keep the existing UI available as a behavioural reference until each replacement is accepted.
9. Preserve native Qt window behaviour and QPainter-specific rendering for overlays.
10. Treat this document as the visual contract; architecture and migration documents should reference it rather than redefine palette or component decisions.

## 3. Approved Project Colour Palette

The following values are copied from Section 11 of the source project's `docs/UI_REBUILD_ROADMAP.md`. The source roadmap was checked on branch `feature/overlay-ui-design`, commit `4edfcf278e108c7f4aa98fd14a3ab4eac35281ed`. These values must not be changed without explicit approval.

### 3.1 Light Theme

| Semantic token | Exact value |
|---|---|
| primary | `#6200EE` |
| primaryVariant | `#3700B3` |
| secondary | `#03DAC6` |
| secondaryVariant | `#018786` |
| background | `#FFFFFF` |
| surface | `#FFFFFF` |
| error | `#B00020` |
| onPrimary | `#FFFFFF` |
| onSecondary | `#000000` |
| onBackground | `#000000` |
| onSurface | `#000000` |
| onError | `#FFFFFF` |

### 3.2 Dark Theme

| Semantic token | Exact value |
|---|---|
| primary | `#BB86FC` |
| primaryVariant | `#3700B3` |
| secondary | `#03DAC6` |
| background | `#121212` |
| surface | `#121212` |
| error | `#CF6679` |
| onPrimary | `#000000` |
| onSecondary | `#000000` |
| onBackground | `#FFFFFF` |
| onSurface | `#FFFFFF` |
| onError | `#000000` |

### 3.3 Colour-Role Usage

- `primary`: primary actions, active navigation and key focus/selection emphasis.
- `primaryVariant`: stronger/pressed primary emphasis where appropriate; not a competing accent.
- `secondary`: supportive highlights, active/live telemetry accents and secondary actions.
- `secondaryVariant`: darker light-theme secondary treatment where needed.
- `background`: application canvas.
- `surface`: cards, panels, dialogs, navigation surfaces and overlay sections.
- `error`: error, destructive and fault states only.
- `on*`: foreground content on the corresponding colour role.

Keep `background` and `surface` as separate semantic tokens even though their approved values currently match in each theme.

### 3.4 Additional Semantic Roles

M3 includes roles beyond the supplied palette, including surface containers, outline, outline variant, inverse surface, primary/secondary containers and status roles. The source roadmap also requires separate success, warning, telemetry severity and tyre/brake temperature tokens.

These roles must exist in the token model, but must not introduce arbitrary replacement brand colours:

- Use approved palette values wherever a role maps directly.
- Use tonal/alpha treatments derived from approved base roles only where design and contrast can be validated.
- Inventory existing warning/success/telemetry severity colours and meanings before consolidating them.
- Record roles that cannot be mapped accessibly and seek approval for the smallest necessary extension before adding a new fixed colour.
- Never communicate status by colour alone. Pair it with a label, icon, shape or other visual cue.

## 4. Desktop Visual Language

### 4.1 Overall Composition

- Use a persistent desktop navigation pattern appropriate to window width: a narrow navigation rail/sidebar with a clear selected state and a page content area.
- Use a compact top app bar for page title, context and limited page-level actions.
- Use cards and surface containers to group related information, not to wrap every individual value.
- Keep hierarchy clear: page title, key status/summary, primary task area, supporting detail.
- Prefer data tables, compact metric groups and aligned telemetry rows where they communicate more efficiently than large cards.
- Avoid excessive gradients, glass effects, glowing borders, oversized rounded cards and decorative animation.
- Preserve room for dense analysis pages, charts, lap tables and hardware configuration forms.
- Adapt layouts when the window is resized; do not assume one fixed desktop resolution.

### 4.2 Information Density

Comfortable and compact density may be provided only if both can be supported consistently:
- **Comfortable:** more breathing room for setup, settings, help and general navigation.
- **Compact:** denser tables, session analysis, live telemetry and technical configuration.

Density must not reduce target usability, contrast or keyboard-focus visibility. The two modes must not create separate visual identities. No separate in-app density selector is approved by the current accessibility decisions.

### 4.3 Typography

Use an M3-inspired hierarchy with a practical Windows fallback stack:
- Display/page title.
- Section heading.
- Subsection/title.
- Body.
- Body small/supporting.
- Label.
- Telemetry value/numeric emphasis.
- Monospaced technical value where alignment materially helps.

Use Roboto when available, with Segoe UI and generic sans-serif fallbacks. Do not require a remote font download. Keep live numeric values tabular/aligned where practical. Avoid excessive all-caps text; reserve it for short labels and status categories.

Initial size scale for design review: 12, 14, 16, 20, 24, 28 and 32 px. These are review candidates, not locked platform font specifications.

**Approved typography direction — Option B:** M3 typography hierarchy with a separate, larger telemetry display scale. Rapidly changing numeric values should be tabular/aligned to prevent visual jitter. Exact sizes, weights, line heights and per-metric sizing remain subject to visual review.

### 4.4 Spacing and Shape

Use a 4 px base spacing scale:

| Spacing | Usage |
|---|---|
| 4 px | Icon/text micro-gap |
| 8 px | Compact control/row gap |
| 12 px | Grouped control spacing |
| 16 px | Standard component/card padding |
| 24 px | Section spacing |
| 32 px | Major page grouping |

**Approved spacing direction — Option B: Balanced.** Use clear group separation without wasting telemetry/analysis workspace. Avoid overly compressed layouts and excessively spacious cards.

Use M3-inspired shape roles consistently: small for fields/compact controls, medium for cards and larger for major containers/dialogs. **Approved shape direction — Option B: Standard M3.** Avoid oversized rounding and indiscriminate pill shapes; reserve fully rounded shapes for chips and components whose M3 pattern calls for them. Exact radii remain subject to component review.

### 4.5 Telemetry Alignment

**Approved direction — Option C: Hybrid.**
- Center primary/high-priority telemetry values such as speed and gear for immediate scanning.
- Keep supporting telemetry and secondary metrics left- or column-aligned so labels and values can be compared.
- Apply alignment according to information type, not by centering the entire page.
- Tables, charts, settings and forms retain conventional alignment.

## 5. Component Standards

| Component | Design requirement |
|---|---|
| App navigation | Persistent, clear selected state, icons paired with readable labels where space allows |
| Top app bar | Page title, current context and limited page-level actions |
| Filled button | Primary action; one clear primary action per relevant task area |
| Tonal/secondary button | Supporting actions without competing with primary |
| Outlined button | Lower-emphasis actions and secondary operations |
| Text field/selector | Persistent label, clear focus, validation and disabled states |
| Tabs | Peer sections within a page; not a substitute for application navigation |
| Card/surface | Group related information with consistent padding and hierarchy |
| Data table | Aligned headers/values, readable density, selected/hover states and empty states |
| Dialog/confirmation | Focused tasks and destructive confirmation; preserve keyboard focus |
| Chip/status indicator | Concise state label; colour is supplemental |
| Tooltip | Explain non-obvious controls and technical values without hiding essential instructions |
| Chart | Clear axes, units, legends, missing-data states and accessible textual summary |
| Toast/inline message | Confirm actions or explain errors without obscuring live data |

Use M3 component guidance as the behavioural reference, adapted for desktop mouse and keyboard use.

**Approved component direction — Option A:** Pure M3 component patterns. Use M3 elevated cards and both elevated and filled button styles. Other components follow official M3 patterns. Apply the same component language across the browser UI and, where practical, native Qt surfaces. Elevation must use appropriate surface/shadow treatment, not new brand colours.

## 6. Required Component States

Every interactive component must specify and be reviewed in applicable states:
- Default.
- Hover.
- Focus-visible.
- Pressed.
- Selected/checked.
- Disabled.
- Loading/busy.
- Error/invalid.
- Warning.
- Read-only.
- Empty/unavailable.

State rules:
- Disabled controls must be genuinely non-interactive and visually distinct; do not only reduce opacity.
- Focus-visible must be obvious and not rely only on a subtle colour shift.
- Selected is not the same as enabled.
- Loading must prevent duplicate submission where relevant and explain what is happening.
- Error and warning must include actionable text where possible.
- Unavailable telemetry must not be displayed as zero.
- Connected/disconnected and live/stale states must be distinguishable through text and visual treatment.

**Approved interaction direction — Option C: Functional Hybrid.** Use M3 state patterns with restrained, purposeful feedback. Hover, focus-visible, pressed, selected, disabled, loading, error and warning states must be distinguishable. Operational clarity takes priority over decorative effects.

## 7. Sim-Racing-Specific Visual Rules

- Live speed, gear, RPM, throttle, brake, lap time and delta must be immediately scannable.
- Use consistent alignment and numeric formatting for rapidly changing values.
- Keep warnings and invalid-lap states prominent but not distractingly animated or flashing.
- Use separate semantic status roles for success, warning, error, connection and telemetry quality; do not reuse the brand accent as a universal status colour.
- Charts must show units and distinguish unavailable samples from zero.
- Avoid decorative animation on live telemetry.
- Keep the UI usable when ACC is not running, when no session exists and when optional telemetry fields do not apply.

## 8. Native Qt Consistency

The main application UI uses the embedded browser. Native Qt remains responsible for floating overlay windows and Hardware Companion initially.

- Reuse the same semantic colour and typography vocabulary where practical.
- Keep native Qt component geometry appropriate to compact overlay and hardware workflows.
- Preserve native window behaviour, always-on-top, transparency, click-through and hardware access.
- Do not force browser-only effects or layout assumptions onto QPainter-based overlays.
- Do not let global QSS changes alter overlay rendering or unrelated native controls.
- Do not duplicate hardware protocols or domain logic between the browser Hardware page and native Hardware Companion.

## 9. Frontend and QtWebEngine Inspection — 2026-11-03

The following findings were verified from the source repository's `feature/overlay-ui-design` branch.

### 9.1 Current Browser UI Structure

- No separate frontend project/build setup was found at the time of inspection: no package.json, Vite/Webpack config, frontend source directory or dedicated web asset bundle.
- Browser pages were generated by Python modules returning complete HTML documents with inline CSS and JavaScript. Verified examples included `performance_hub_ui.py`, `practice_hub_ui.py`, `session_library_ui.py`, `radio_help_page.py` and `settings_ui.py`.
- `dashboard_server.py` used Python's standard-library `http.server`/`ThreadingHTTPServer` and dispatched page routes and JSON APIs. It also published the existing SSE state stream.
- `apply_web_theme()` injected a shared stylesheet from `ui_theme.py`; pages still contained substantial page-local CSS, including hard-coded colours and local component styling.
- The current browser surfaces were therefore not yet a reusable frontend shell or separately built frontend application.

### 9.2 Existing QtWebEngine Use

- `src/overlay/window.py` contains the native `ControlCenterWindow`.
- Its Help, Practice and Performance Hub tabs instantiate `QWebEngineView` and navigate to existing local dashboard routes.
- These tabs have fallback paths when QtWebEngine cannot be imported/initialized.
- This proves QtWebEngine is already used for embedded page content, but does not prove a complete main application shell, desktop routing lifecycle or packaged asset strategy already exists.
- `requirements.txt` declares `PySide6==6.9.2`; QtWebEngine use was optional at the inspected call sites.
- `src/overlay/runtime.py` starts the dashboard server only when the web dashboard option is enabled. The dashboard server is stopped during overlay runtime shutdown.
- `src/product_launcher.py` used `webbrowser.open()` for first-run setup. This external-browser path must be reconsidered for the approved standalone embedded-main-window experience.

### 9.3 Existing Theme Implementation Mismatch

- `src/ui_theme.py` described its token seed as blue/teal and defined a different dark/light palette (for example, dark background `#101318`, accent `#a8c8ff`; light background `#f8f9ff`).
- This does not match the approved purple/teal palette in roadmap Section 11.
- Several browser pages also defined local navy/cyan palettes.
- The existing theme helper is not the authority for the new UI palette.
- Do not globally replace the current theme helper as part of documentation/specification work. During implementation, reconcile the helper and page-local styles through targeted, tested changes.

## 10. Implementation Preparation

Before the first full shell implementation:

1. Confirm React + TypeScript + Vite as the frontend build strategy and record any repository constraints.
2. Prototype a minimal PySide6 host window containing QWebEngineView that loads a local bundled shell route without opening an external browser.
3. Verify QtWebEngine runtime dependencies and packaging behaviour in an actual Windows release-style build.
4. Decide how local static assets are served or loaded, how routes are handled, and how renderer reload/crash is isolated from the Python runtime.
5. Define the narrow browser-to-Python bridge using local HTTP API/SSE contracts; do not create duplicate telemetry or domain services.
6. Implement design tokens and a small M3 component showcase using the exact Section 11 palette.
7. Review screenshots at supported window sizes and Windows DPI scaling before implementing the full dashboard.
8. Inventory existing status colours and validate actual palette pairings before finalizing surface/outline/status tonal mappings.

The exact surface/outline tonal mapping, component dimensions, rail width, icon sizes, expanded navigation behaviour, breakpoints and final typography metrics remain implementation decisions pending visual review.

## 11. Design-System Acceptance Checklist

- [ ] All primary brand colours match roadmap Section 11 exactly.
- [ ] Light and dark themes use approved values and correct on-colour pairings.
- [ ] No blue/teal replacement seed palette remains in the new shell.
- [ ] M3 component patterns are adapted for desktop use.
- [ ] Typography, spacing, shape and density tokens are documented and reused.
- [ ] Interactive components demonstrate all applicable states.
- [ ] Warning/success/connection/telemetry states are semantically distinct and not colour-only.
- [ ] Dense telemetry and analysis tables remain glance-readable.
- [ ] Keyboard focus, contrast, reduced motion and resizing are reviewed.
- [ ] Browser and native Qt surfaces use the same semantic token vocabulary where practical.
- [ ] Existing UI theme and page CSS are migrated only through targeted, verified changes.
- [ ] Windows DPI/system scaling is tested at representative window sizes.
- [ ] QtWebEngine renderer recovery does not interrupt the Python runtime or recording.

## 12. Approved Typography Direction — 2026-11-03

The user selected **Option B: M3 typography with a separate, larger telemetry display scale**.

- Use the M3-inspired hierarchy for page titles, section headings, body text, supporting text, labels and controls.
- Use a distinct display scale for high-priority live telemetry such as speed, gear, RPM and other key racing values.
- Keep rapidly changing numeric values tabular/aligned where practical to prevent visual jitter.
- Retain Roboto when available, with Segoe UI and generic sans-serif fallbacks; do not require a remote font download.
- Exact type sizes, weights, line heights and per-metric sizing remain subject to visual review.

This records the direction, not final numeric typography tokens.

## 13. Approved Component Direction — 2026-11-03

The user selected **Option A: Pure Material Design 3 components**.

- Cards: M3 elevated card treatment.
- Buttons: both elevated and filled button styles.
- Other components: official M3 patterns for tabs, dialogs, text fields, selectors, navigation and status chips.
- Apply the same component language across the main browser UI and, where practical, native Qt surfaces.
- Preserve the exact approved palette. Elevation uses appropriate surface and shadow treatment, not new brand colours.

Exact elevation levels, component dimensions and state styling remain subject to the component showcase review.

## 14. Approved Navigation Layout — 2026-11-03

The user selected **Option A: narrow, permanent navigation rail**.

- Keep the navigation rail narrow and icon-led.
- Provide more horizontal workspace for live telemetry, charts and analysis.
- Show navigation labels through tooltips and/or an expanded navigation mode rather than permanently consuming width.
- Aim for a modern, minimal desktop appearance.
- The rail remains persistent; it is not a temporary overlay or top-navigation replacement.
- Preserve clear selected/focus states and accessible names even when labels are visually collapsed.

Exact rail width, icon dimensions, expanded-mode behaviour and responsive breakpoint remain subject to shell visual review.

## 15. Approved Spacing, Shape and Telemetry Alignment — 2026-11-03

The user approved:

- **Spacing — Option B: Balanced.** Clear separation between groups without wasting workspace. Retain the 4 px base scale. Use compact gaps within related controls/rows, standard component padding and larger gaps between distinct sections.
- **Shape — Option B: Standard Material 3.** Moderate rounding for cards/containers and smaller shapes for compact controls. Reserve fully rounded treatments for components whose M3 pattern calls for them.
- **Primary telemetry-card alignment — Option C: Hybrid.** Center primary/high-priority telemetry values; keep supporting telemetry and secondary metrics left- or column-aligned. Tables, charts, settings and forms retain conventional alignment.

These are approved visual directions, not final pixel-level tokens.

## 16. Approved Interaction, Motion and Accessibility — 2026-11-03

### 16.1 Interaction and Motion

The user approved **Option C: Functional Hybrid** interaction states and **Option B: Standard Material Design 3 Motion**.

- Use standard M3 motion principles and transitions where they clarify navigation, hierarchy, state changes or feedback.
- Keep motion short and purposeful; avoid ornamental animation.
- Respect reduced-motion preferences and provide equivalent non-motion state changes.
- Do not animate rapidly changing live values such as speed, RPM, gear, brake or throttle for decoration.
- Telemetry updates must remain stable and glance-readable.
- Motion must not delay an action, hide important information or interfere with keyboard operation.

Exact transition durations, easing and focus treatment remain subject to review.

### 16.2 Keyboard Navigation

The user approved **Option A: Standard M3**.

- Provide logical keyboard navigation and predictable Tab order.
- Ensure controls can be reached and activated using standard keyboard conventions, including Enter/Space where appropriate.
- Show a clear, visible keyboard focus indicator.
- Application-wide custom shortcut keys are not part of this approval.

### 16.3 Contrast and Readability

The user approved **Option A: WCAG AA baseline**.

- At least 4.5:1 contrast for normal text.
- At least 3:1 for large text.
- Apply the relevant 3:1 contrast requirement to meaningful component boundaries and graphical indicators.
- Validate actual approved light/dark palette pairings.
- Do not silently change palette values to achieve compliance; flag failing pairings for review.

This is an acceptance target, not a claim that compliance has already been verified.

### 16.4 Scaling and Status Communication

The user approved:
- **System scaling — Option A:** Respect Windows DPI/display scaling and system text scaling. Adapt layouts to available window dimensions. No separate in-app text-size control or density selector is approved.
- **Status — Option A: Colour plus text:** Pair status colours with explicit labels such as Connected, Disconnected, Warning and Error. Status meaning must remain understandable without colour. A separate icon for every status is not required.

## 17. Implementation Status

This is a design specification, not an implementation record.

- Design direction and user preferences: documented.
- Approved palette: verified against source roadmap Section 11.
- Existing frontend/QtWebEngine source inspection: documented as of 2026-11-03.
- Visual component showcase: pending.
- Contrast and accessibility verification: pending.
- QtWebEngine Windows packaging proof: pending.
- Frontend framework/build setup: pending implementation.
- Application code, stylesheet, launcher and runtime: not changed by this specification.

**Final design decision:** Use Material Design 3 for the desktop component and interaction language, retain the exact approved purple/teal palette, and implement it in the hybrid PySide6 + QtWebEngine + React desktop architecture. Native Qt overlays and Hardware Companion retain native rendering while sharing semantic tokens where practical.
