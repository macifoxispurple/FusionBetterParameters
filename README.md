# Better Parameters

`Better Parameters` is a Fusion 360 Python add-in that opens a modeless HTML palette for working with `Design.userParameters`. Unlike Fusion's native Parameters dialog, the palette does not block the rest of the Fusion UI while it is open.

## What it does

- Adds a `Better Parameters` button to its own panel on the `Design > Utilities` tab and, when available, into the native `Modify` panels for Solid, Surface, Mesh, Sheet Metal, and Plastic.
- Opens a floating palette built with Fusion's native `UserInterface.palettes` API.
- Lists current user parameters with their expression, value preview, unit, and comment.
- Lets you edit an existing parameter's expression and comment.
- Lets you create new user parameters from the same palette.
- Validates new parameter names against Fusion-style naming rules before creation.
- Autocompletes existing parameter names in expression fields throughout the palette and validates references case-sensitively.
- Uses Fusion's own expression validation rules, including explicit operator requirements and no implicit multiplication from parentheses.
- Saves palette settings automatically to `settings.json` as soon as the user changes them.
- Includes a light/dark theme toggle inspired by Fusion's native UI themes.
- Defaults new parameter units to the active document's Unit System and can optionally remember the last chosen unit.
- Uses a grouped Units picker for new parameters, with expandable categories similar to Fusion's Add User Parameter dialog.
- Remembers the Better Parameters window size between sessions.

## Current scope

This initial version targets **user parameters** only. Fusion's full Parameters dialog also includes model parameters, favorites, and other generated values, but user parameters are the cleanest API-backed place to start for reliable editing from Python.

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
- If no design is open, the add-in will ask you to open one before editing parameters.

## Good next steps

- Add filtering/search for large parameter sets.
- Surface model parameters in a read-only section.
- Add delete/favorite toggles for user parameters.
- Persist column widths, palette position, and dock state between sessions.
