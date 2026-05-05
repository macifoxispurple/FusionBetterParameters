# Better Parameters

**Better Parameters** is an Autodesk Fusion add-in for people who are tired of fighting the Parameters dialog.

It gives you a faster, non-blocking way to work with user parameters, with a table-based UI that actually scales as your designs get more complex.

## Why I made it

Fusion’s built-in Parameters dialog works, but once you start relying on parameters heavily, it starts to get in the way:

- the dialog blocks your workflow
- editing values takes more clicks than it should
- there’s no real way to organize things cleanly
- grouping and ordering are limited
- large parameter lists get hard to navigate quickly

I wanted something that felt more like a tool you could leave open and actually *work in*, not something you constantly open and close.

## What it can do

- Show all user parameters in a **modeless floating palette** (no blocking dialog)
- Let you scan and edit parameters in a **table-first UI**
- Edit expressions and comments inline without jumping through menus
- Organize parameters into **groups** (create, rename, delete, reorder)
- Mark important parameters as **favorites**
- Search across name, expression, comment, unit, and value
- Track per-row changes with **Save** and **Revert**
- Preview evaluated values using Fusion’s own expression engine
- Remember your UI layout, column sizes, theme, and preferences

You can think of it as a more flexible, always-available version of Fusion’s parameter dialog.

## Rapid Create (keyboard-first)

There’s also a fast path for creating a bunch of parameters at once.

- Open with `Ctrl+Shift+C`
- Enter rows like:
  - `name[TAB]expression[TAB]comment`
  - or `name,expression,comment`
- Mix delimiters if needed
- Each row is validated and processed individually

It’s meant for quickly pasting in or building out parameter sets without switching context.

## Working with groups

As your parameter list grows, grouping becomes essential.

- Create and rename groups as needed
- Collapse and expand groups to reduce clutter
- Reorder both groups and parameters
- `Ungrouped` acts as the default bucket

Grouping and ordering are stored in the Fusion design file when possible, so they usually travel between computers, with a local fallback on each machine to keep things consistent.

## Units

The unit picker is built to be a little more usable than Fusion’s default experience:

- Units are grouped by category
- You can pin commonly used units
- You can add custom units (validated against Fusion)
- Pinned and custom units persist between sessions

## Editing and validation

All expressions are validated using Fusion’s native expression engine, so behavior matches what you’d expect.

A few important details:

- Parameter names are case-sensitive and must be unique
- Expressions require explicit operators (no implicit multiplication)
- Preview values come directly from Fusion’s evaluator

If something looks wrong, it’s coming from Fusion, not a separate system.

## Settings

Better Parameters remembers how you like to work.

Settings are stored locally in `settings.json` next to the installed add-in inside Fusion’s AddIns folder, including:

- theme (light / dark)
- palette size and layout
- column widths
- unit preferences (including pinned units)
- UI toggles (comments, revert buttons, auto-fit columns, etc.)

Most settings save immediately.

## Installation

### Option 1: Use the included shortcuts

After unzipping the release, open one of these files from the same folder as `BetterParameters`:

- **Windows:** `Open Fusion AddIns (Windows).lnk`
- **macOS:** `Open Fusion AddIns (macOS)`

This opens Fusion’s Add-Ins folder for your OS.  
Then drag/copy the `BetterParameters` folder into that location.

### Option 2: Copy manually into Fusion’s Add-Ins folder

**Windows:**  
`%AppData%\Autodesk\Autodesk Fusion 360\API\AddIns`

**macOS:**  
`~/Library/Application Support/Autodesk/Autodesk Fusion 360/API/AddIns`

Copy the `BetterParameters` folder into the appropriate location, then enable it from **Utilities > Scripts and Add-Ins > Add-Ins**.


## Where it shows up in Fusion

Better Parameters adds a **Better Parameters** button under the **Utilities** tab.

When available, it may also show up in Modify panels so it’s easier to access while modeling.

## A few notes

- This add-in works with **user parameters only**
- You need an open design to create or edit parameters
- Changes apply directly to the active document
- Some UI state and ordering is stored locally per machine

There’s also a temporary **Text Tuner** sidebar included for UI/debug work. It’s experimental and may change or go away later.

## Updates

The add-in can check GitHub for new releases and stage updates locally.

Applying updates requires restarting or reloading the add-in.

You can disable update checks in settings if you prefer.

## Project files

- `BetterParameters.py` — main add-in logic
- `palette.html` — UI for the parameter editor
- `update_helper.py` — update application logic
- `update_state.py` — update state tracking

## Status

Better Parameters is ready to use for real parameter-heavy workflows. There’s still room to refine things, but it’s already a big improvement over the default experience.

## License

This project is licensed under the MIT License. See `LICENSE` for details.
