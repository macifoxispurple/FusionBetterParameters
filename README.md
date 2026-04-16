# Better Parameters

`Better Parameters` is a Fusion 360 Python add-in that opens a modeless HTML palette for working with `Design.userParameters`. Unlike Fusion's native Parameters dialog, the palette does not block the rest of the Fusion UI while it is open.

## What it does

- Adds a `Better Parameters` button to its own panel on the `Design > Utilities` tab and, when available, into the native `Modify` panels for Solid, Surface, Mesh, Sheet Metal, and Plastic.
- Opens a floating palette built with Fusion's native `UserInterface.palettes` API.
- Renders a native-style, table-first parameter view with compact top rail and columns:
  - `Parameter | Name | Unit | Expression | Value | Comments`
- Uses responsive column visibility so key editing columns stay usable on narrow palette widths.
- Supports grouped parameter rows with collapse/expand, group rename/delete, and group/row reorder tools.
- Supports favorites as duplicated rows:
  - favorited rows appear in `Favorites` and remain in their original group.
  - favorite toggles update both instances after save/refresh.
- Lets you edit existing parameter expression/comment inline, with row-level dirty state, Save, and Revert.
- Lets you create new user parameters from the palette (compact create form via `+ New`).
- Validates create names against Fusion naming rules.
- Uses Fusion expression validation and preview behavior (case-sensitive references, explicit operators, no implicit multiplication by adjacency).
- Includes search/filter across parameters.
- Persists user settings in `settings.json` (theme, comment column visibility, revert button visibility, auto-fit behavior, Text Tuner sidebar visibility, unit prefs, etc.).
- Auto-detects Fusion theme once at startup (`fusionTheme`) and still allows manual override.
- Remembers palette size between sessions.

## Current scope

This add-in currently targets **user parameters** only. Native Fusion also exposes model parameters and additional generated values; those are not yet editable in this add-in.

## Visual Tuning (Temporary)

For parity tuning, the palette includes a temporary **Text Tuner** sidebar (left side of the window):

- **Global text tuning** (single style set per mode) for font family, size, weight, spacing, transform, color.
- **UI color token tuning** for table/rail/surface tokens including zebra rows, hover, table header, search field, group row, etc.
- **Live apply + live persistence**:
  - edits apply immediately with short debounce;
  - edits are saved to `text_tuner_temp.json` so tuning survives add-in restarts.
- Sidebar visibility can be toggled from Settings (`Text Tuner: On/Off`).
- Tuner list is mode-aware:
  - light mode edits light values;
  - dark mode edits dark values.
- Includes debug export block for copy/paste snapshots.

This tuner is intentionally temporary and intended to be removed once final tokens are locked.

## Install

1. Copy this folder into your Fusion add-ins directory, or use the `+` button in `Utilities > Add-Ins > Scripts and Add-Ins` to point Fusion at this folder.
2. Start the add-in from Fusion's `Scripts and Add-Ins` dialog.
3. Click the `Better Parameters` button in the `Design > Utilities` tab.

Common add-in folder locations:

- Windows: `%AppData%\Autodesk\Autodesk Fusion 360\API\AddIns`
- macOS: `~/Library/Application Support/Autodesk/Autodesk Fusion 360/API/AddIns`

## Notes

- The HTML palette is intentionally modeless, which is the Fusion-native way to keep the main UI interactive while a tool window is open.
- The toolbar command uses Fusion resource icons from `Resources/BetterParameters` with light and dark theme variants.
- Expressions are sent directly to Fusion, so native syntax like `Width / 2`, `25 mm`, or text expressions are handled by Fusion itself.
- Settings are stored in `settings.json` next to the running add-in and are written immediately when the user changes them.
- The Units picker remembers which categories you leave expanded or collapsed.
- When `Remember Unit` is off, the create form defaults to the active document's default length unit such as `mm`, `cm`, `in`, or `ft`.
- On very narrow palette widths (under ~400px), the table prioritizes `Name` and `Expression` columns for editing clarity.
- Row selection is persistent in-session: clicking/focusing a row marks it selected until another row is selected (or palette closes).
- Group-row drag can be started from most of the group row surface (except explicit controls), matching native hierarchy behavior.
- If no design is open, the add-in will ask you to open one before editing parameters.

## Good next steps

- Replace temporary Text Tuner sidebar with finalized design tokens.
- Add explicit selected-row token(s) in settings/tuner for tighter native parity control.
- Surface model parameters in a read-only section.
- Expand keyboard navigation and accessibility polish for table interactions.
