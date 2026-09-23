# Fixed window layout

## Signals and mechanism

The desktop window displayed a scrollbar for the entire interface. In [`src/styles.css`](../../../src/styles.css), `.app-shell` used `min-height:100vh` while `.page` and several grids/panels had large minimum heights. Their combined size could exceed the window, so the outer document scrolled.

## Handling and limits

Keep the root and shell at the viewport height. Give nested flex/grid containers `min-height:0` so they can shrink, then allow scrolling in content panels. The Today dashboard needs explicit grid rows and its action buttons outside its scrolling list. For narrow or short windows, scroll the main content region instead of clipping controls. This pattern applies to the desktop client layout; it does not imply that every panel should be fixed height on small screens.

## Verification

After rebuilding the macOS app, the Today, Tasks and Settings screens filled the window without an outer page scrollbar. The Today action buttons and all four overview cards remained visible at the normal window size. Verified once on 2026-09-23.
