# Settings Account & App Panels — Design QA

- Source visual truth: `artifacts/settings-scroll-bottom.png`
- Implementation screenshot: `build/account-settings-implementation-1100.png`
- Combined comparison: `build/account-settings-comparison.png`
- Supporting states: `build/about-panel-implementation.png`, `build/profile-panel-implementation.png`, `build/developer-panel-implementation.png`
- Viewport and pixels: 1100 x 700 logical pixels at device scale 1 for the normalized source/implementation comparison.
- State: Settings drawer open and scrolled to the bottom; Graphite Dark theme.

**Findings**

- No actionable P0, P1, or P2 findings remain.
- The requested account and product controls are visible beneath Plugin settings in the intended order without horizontal overflow.
- The profile form uses an internal vertical scroll area so all fields and actions remain reachable on the minimum supported window height.

**Full-view comparison evidence**

The implementation preserves the source drawer width, right-edge scrollbar, compact button height, five-pixel vertical rhythm, avatar scale, and surrounding panel proportions. The only intentional structural change is the new `ACCOUNT & APP` group after Plugin settings, which extends the existing scroll content instead of resizing or covering the main interface.

**Focused region comparison evidence**

The bottom Settings region was reviewed in the combined image. Subscription retains its semantic active-plan styling; About CHARLIE, My profile, and Developer details use the same neutral button treatment as existing Settings destinations. Separate modal captures confirm readable hierarchy, centered geometry, consistent radii, and reachable close/save actions.

**Required fidelity surfaces**

- Fonts and typography: existing Segoe UI and Plus Jakarta Sans assignments, weights, and compact Settings hierarchy are preserved. Off-screen Qt captures show missing-font glyph boxes on this machine; the installed Windows build uses the available system font normally.
- Spacing and layout rhythm: existing 5 px Settings spacing and 32 px normalized button heights remain intact. Modal panels use 22-26 px margins, 8-12 px gaps, and the same rounded visual language.
- Colors and visual tokens: all new surfaces use live `PANEL`, `PANEL2`, `BORDER`, `PRI`, `TEXT`, and semantic subscription tokens, so every remaining dark theme is supported.
- Image quality and asset fidelity: no source avatar or image asset was changed, replaced, stretched, or recompressed.
- Copy and content: About explains CHARLIE and shows v1.2.3 / 2026; Profile labels all editable details clearly; Developer Details shows the exact creator credit requested.

**Primary interactions tested**

- Subscription opens the existing plan comparison.
- About CHARLIE opens and closes its information panel.
- My profile renders all fields, validates name/email, saves locally, and keeps family profiles isolated.
- Developer Details opens and closes with the Anees Chaudhary / 2026 credit.
- Settings scrolling and mouse-wheel-safe selectors remain unchanged.
- Native Qt application: browser console checks are not applicable; Python compilation and focused Qt tests cover runtime construction.

**Comparison history**

- Initial P1: modal buttons referenced a style local to the Settings builder and failed during panel construction.
  - Fix: modal buttons now own theme-token styles.
  - Post-fix evidence: all three panel states render successfully and the focused tests pass.
- No later P0, P1, or P2 findings.

**Implementation Checklist**

- [x] Move Subscription below Plugin settings.
- [x] Add About CHARLIE with product purpose, version and release year.
- [x] Add editable local My Profile with validation.
- [x] Add Developer Details with requested creator credit.
- [x] Verify same-size source and implementation captures.

**Follow-up Polish**

- P3: Semantic version numbers (v1.2.3) used exclusively across releases.

final result: passed
