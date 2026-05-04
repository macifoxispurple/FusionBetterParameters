# Better Parameters

**Better Parameters** is an Autodesk Fusion add-in that makes working with user parameters faster, less frustrating, and a lot more manageable.

It gives you a non-blocking, table-based interface for editing parameters, organizing them into groups, and actually keeping them under control as your designs grow.

## Why I made it

Fusionâ€™s built-in Parameters dialog works, but once you start using parameters heavily, it starts to get in the way:

- the dialog blocks your workflow
- editing values takes more clicks than it should
- thereâ€™s no good way to organize parameters
- grouping and ordering are basically non-existent
- finding what you need in a large parameter list gets tedious fast

This add-in is meant to make parameter-heavy workflows feel faster and easier to manage.

## What it does

Better Parameters gives you:

- A **modeless floating palette** (no more blocking dialog)
- A **table-first UI** for quick scanning and editing
- Inline editing for expressions and comments
- **Grouping** (create, rename, delete, reorder)
- **Favorites** for quick access to important parameters
- Search across name, expression, comment, unit, and value
- Per-row **Save, Revert, and Discard** with dirty state tracking
- Expression preview and validation using Fusionâ€™s engine
- Reliable Shift-range multi-select behavior across grouped rows, including when Favorites duplicate rows are visible
- **Auto Fit columns** toggle to automatically resize columns when the palette is resized
- Persistent UI settings (theme, layout, column sizes, etc.)

You can think of it as a much more flexible, always-available version of Fusionâ€™s parameter dialog.

## Working with groups

Parameters can be organized into groups to keep things manageable as your design grows.

- Create and rename groups as needed
- Collapse and expand groups to reduce clutter
- Reorder both groups and parameters
- â€œUngroupedâ€ is treated as a default bucket

Grouping and ordering are stored in the Fusion design file when possible, so they usually travel between computers, with a local fallback on each machine to keep things consistent.

## Unit picker

The unit picker lets you assign or change a parameterâ€™s unit inline.

- All standard Fusion units are available in the dropdown
- **Pin** any unit to the top of the list with the â˜… button for quick access
- **Add custom units** â€" validated against Fusionâ€™s engine before saving; duplicates are rejected with inline feedback
- **Remove custom units** you no longer need
- Pinned units and custom units are saved in your settings

## Editing and validation

Expressions are validated using Fusionâ€™s native expression engine, so behavior matches what youâ€™d expect from the built-in tools.

A few important details:

- Parameter names are case-sensitive and must be unique
- Expressions require explicit operators (no implicit multiplication)
- Preview values are generated using the active document units

If something looks off, itâ€™s coming from Fusionâ€™s evaluator, not a separate system.

## Settings

Better Parameters remembers how you like to work.

Settings are stored locally in `settings.json` next to the installed add-in inside Fusionâ€™s AddIns folder, including:

- theme (light / dark)
- palette size and layout
- column widths
- unit preferences, including **pinned units** for fast access in the unit picker
- UI toggles (comments, revert buttons, auto fit columns, etc.)

Most changes are saved immediately.

Status messages are also captured in a session-only **Status History** section in Settings. Inline status in the main view is now reserved for higher-priority warnings/errors.

## Installation

### Option 1: Install from inside Fusion

1. Download and unzip the project
2. Open Fusion
3. Go to **Utilities > Scripts and Add-Ins**
4. Open the **Add-Ins** tab
5. Click the green `+` button
6. Select the `BetterParameters` folder  
   (make sure you select the folder that contains `BetterParameters.py`, not a parent folder)
7. Run the add-in

### Option 2: Copy into Fusionâ€™s Add-Ins folder

**Windows:**  
`%AppData%\Autodesk\Autodesk Fusion 360\API\AddIns`

**macOS:**  
`~/Library/Application Support/Autodesk/Autodesk Fusion 360/API/AddIns`

Copy the `BetterParameters` folder into the appropriate location, then enable it from **Utilities > Scripts and Add-Ins > Add-Ins**.

## Where it shows up in Fusion

Better Parameters adds a **Better Parameters** button under the **Utilities** tab.

When available, it also promotes itself into Modify panels so itâ€™s easy to access while working.

## A few notes

- This add-in works with **user parameters only**
- An open design is required to create or edit parameters
- Changes are applied immediately to the active document
- Some UI state and ordering is stored locally per machine

There is also a temporary **Text Tuner** sidebar included for UI/debug tuning. Itâ€™s experimental and may change or be removed later.

## Updates

The add-in can check for new releases on GitHub and optionally stage updates locally. Applying updates requires restarting or reloading the add-in.

You can disable update checks in settings if you prefer.

## Project files

- `BetterParameters.py` â€” main add-in logic
- `palette.html` â€” UI for the parameter editor
- `update_helper.py` â€” update application logic
- `update_state.py` â€” update state tracking
- `tests/` â€” Python unit tests for backend helpers (run with `python -m pytest`)

## Status

Better Parameters is ready to use today and works well for real-world parameter-heavy workflows. Thereâ€™s still room to refine the UI and expand features over time, but itâ€™s already a big improvement over the default experience.

## License

This project is licensed under the MIT License. See `LICENSE` for details.
