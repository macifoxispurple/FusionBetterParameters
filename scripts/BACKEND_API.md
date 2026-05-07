# BetterParameters — Backend API Reference

**Add-in version:** 0.4.11+ (WIP on HEAD)  
**Last updated:** 2026-04-16  
**Current API version:** 1

This document is the complete specification of the message-passing API between the HTML/JS palette UI and the Python Fusion 360 add-in backend. A developer with only this document should be able to build a fully functional replacement palette UI from scratch.
Canonical location: `scripts/BACKEND_API.md` (repo root copy removed).

---

## Table of Contents

1. [Transport Layer](#transport-layer)
2. [Common Response Envelope](#common-response-envelope)
3. [Data Shapes](#data-shapes)
   - [State Payload](#state-payload)
   - [Parameter Object](#parameter-object)
   - [ModelParameter Object](#modelparameter-object)
   - [Settings Object](#settings-object)
   - [UpdateInfo Object](#updateinfo-object)
4. [JS → Python Actions (requests)](#js--python-actions-requests)
   - [ready](#ready)
   - [refresh](#refresh)
   - [createParameter](#createparameter)
   - [deleteParameter](#deleteparameter)
   - [deleteParameters](#deleteparameters)
   - [updateParameter](#updateparameter)
   - [batchUpdateParameters](#batchupdateparameters)
   - [renameParameter](#renameparameter)
   - [getModelParameters](#getmodelparameters)
   - [updateModelParameter](#updatemodelparameter)
   - [copyParameter](#copyparameter)
   - [sortByTimelineOrder](#sortbytimelineorder)
   - [exportParameters](#exportparameters)
   - [importParameters](#importparameters)
   - [exportParametersPackage](#exportparameterspackage)
   - [validateParametersPackageImport](#validateparameterspackageimport)
   - [importParametersPackage](#importparameterspackage)
   - [revertParameter](#revertparameter)
   - [setParameterFavorite](#setparameterfavorite)
   - [setParameterGroup](#setparametergroup)
   - [renameGroup](#renamegroup)
   - [deleteGroup](#deletegroup)
   - [saveParameterOrder](#saveparameterorder)
   - [saveGroupUiState](#savegroupuistate)
   - [saveSettings](#savesettings)
   - [savePaletteGeometry](#savepalettegeometry)
   - [getTextTunerState](#gettexttunerstate)
   - [saveTextTunerState](#savetexttunerstate)
   - [validateParameterName](#validateparametername)
   - [validateExpression](#validateexpression)
   - [previewExpression](#previewexpression)
   - [validateUnit](#validateunit)
   - [openHelpUrl](#openhelpurl)
   - [copyToClipboard](#copytoclipboard)
   - [checkForUpdates](#checkforupdates)
   - [downloadAndStageUpdate](#downloadandstageupdate)
   - [syncMetadataJsonToFusion](#syncmetadatajsontofusion)
   - [syncMetadataFusionToJson](#syncmetadatafusiontojson)
   - [repairMetadata](#repairmetadata)
   - [getParameterDependencyGraph](#getparameterdependencygraph)
   - [getBackendContractInfo](#getbackendcontractinfo)
   - [seedTestParameters](#seedtestparameters)
   - [resetTestState](#resetteststate)
   - [runSelfTestSuite](#runselftestsuite)
5. [Python → JS Pushes](#python--js-pushes)
6. [Startup Sequence](#startup-sequence)
7. [Error Handling](#error-handling)
8. [Constraints and Edge Cases](#constraints-and-edge-cases)
9. [Migration Guide](#migration-guide)

---

## Transport Layer

Communication between the JS palette UI and the Python backend uses Fusion 360's built-in palette messaging system.

### JS → Python (requests)

```javascript
// Returns a Promise that resolves to the parsed JSON response object.
const response = await window.adsk.fusionSendData(action, JSON.stringify(data));
// response is already a parsed JS object — do NOT JSON.parse it again.
```

- `action`: string — the action name (e.g. `"createParameter"`)
- `data`: plain JS object — the request payload (serialized to JSON string)
- The returned Promise resolves to the parsed response object.

### Python → JS (server-initiated pushes)

Python can push data to the UI at any time without a JS request:

```python
palette.sendInfoToHTML(action, jsonString)
```

The JS side must register a global handler before sending `ready`:

```javascript
window.fusionReceiveData = function(action, dataString) {
  const data = JSON.parse(dataString);  // must parse manually
  if (action === "renderState") {
    applyStateFromFusion(data);
  }
};
```

> **Note:** Unlike the `fusionSendData` return value, the `dataString` argument to `fusionReceiveData` is a raw JSON string and must be parsed manually with `JSON.parse`.

### Single delivery on mutating actions

Every action that modifies Fusion state (parameters, groups, settings, order, etc.) returns the full State Payload as the `fusionSendData` response. **It does not push a `renderState` event.**

`renderState` pushes are reserved for **unsolicited** state changes only:
- Fusion document switch (user activated a different document)
- Palette opened by the toolbar button (no JS initiator)

A well-written UI should:
1. Apply state from the `fusionSendData` return value after every action.
2. Also handle incoming `renderState` pushes for document-switch and open events.

Route both through the same `applyState(data)` function.

---

## Common Response Envelope

Every response — success or failure, mutating or read-only — shares the same top-level shape:

```json
{
  "ok": true | false,
  "message": "",
  "state": { /* State Payload or null */ },
  "[action-specific fields]": "..."
}
```

| Field | Type | Always present | Description |
|---|---|---|---|
| `ok` | `boolean` | Yes | `true` on success, `false` on any error |
| `message` | `string` | Yes | Human-readable error description on failure; empty string on success |
| `state` | `object \| null` | Yes | Full State Payload for mutating actions; `null` for read-only and validation actions |

Action-specific fields (e.g. `values`, `document`, `preview`, `syncResult`) appear alongside these three when relevant.

### Success — mutating action

```json
{
  "ok": true,
  "message": "",
  "state": { "apiVersion": 1, "parameters": [...], "groups": [...], "..." : "..." }
}
```

### Success — read-only / validation action

```json
{
  "ok": true,
  "message": "",
  "state": null,
  "[action-specific field]": "..."
}
```

### Error (any action)

```json
{
  "ok": false,
  "message": "Human-readable error description",
  "traceback": "Full Python traceback (empty for expected validation errors)",
  "state": null
}
```

`traceback` is populated for unexpected exceptions; empty for expected validation failures (e.g. "parameter not found").

### Recommended response handler

Because the envelope is uniform, a single handler works for all actions:

```javascript
async function sendAction(action, payload) {
  const response = await window.adsk.fusionSendData(action, JSON.stringify(payload));
  if (!response.ok) {
    showError(response.message);   // message is always present
    return null;
  }
  if (response.state) {
    applyState(response.state);    // state is non-null for mutating actions
  }
  return response;                 // caller can read action-specific fields
}
```

The `fusionReceiveData` handler for spontaneous pushes uses the same shape:

```javascript
window.fusionReceiveData = function(action, dataString) {
  const response = JSON.parse(dataString);
  if (action === "renderState" && response.state) {
    applyState(response.state);
  }
};
```

---

## Data Shapes

### State Payload

The full application state. Carried in the `state` field of every mutating action response and every `renderState` push. Never returned as a bare top-level response — always inside the common envelope.

```json
{
  "ok": true,
  "apiVersion": 1,
  "parameters": [],
  "modelParameterCount": 0,
  "groups": [],
  "groupUi": {
    "order": [],
    "collapsed": {}
  },
  "parameterNames": [],
  "settings": {},
  "document": {
    "id": "",
    "name": ""
  },
  "documentDefaults": {
    "unit": "mm"
  },
  "textTunerState": {},
  "fusionTheme": "light",
  "updateInfo": {}
}
```

| Field | Type | Description |
|---|---|---|
| `ok` | `boolean` | Always `true` for State Payload |
| `apiVersion` | `number` | API schema version. Currently `1`. Increment if breaking changes are made. |
| `parameters` | `Parameter[]` | All user parameters in user-defined display order |
| `modelParameterCount` | `number` | Total model parameter count from the root component. `0` when no document is open. Used to show section headers and load indicators without fetching the full list. Actual parameter data is fetched on demand via `getModelParameters`. |
| `groups` | `string[]` | Unique group names, sorted case-insensitively. Does NOT include the empty string for Ungrouped. |
| `groupUi.order` | `string[]` | Group names in the persisted display order |
| `groupUi.collapsed` | `{ [groupName: string]: boolean }` | Per-group collapse state |
| `parameterNames` | `string[]` | ALL parameter names in the design (user + model), sorted. Used for expression autocomplete. |
| `settings` | `Settings` | Full persisted settings object |
| `document.id` | `string` | Fusion document creation ID (empty if no doc open) |
| `document.name` | `string` | Human-readable document name (empty if no doc open) |
| `documentDefaults.unit` | `string` | Active document unit (defaults to `"mm"`) |
| `textTunerState` | `{ [key: string]: string }` | Text tuner key/value map, max 200 entries |
| `fusionTheme` | `"light" \| "dark"` | Fusion's current UI theme. Defaults to `"light"` if undetectable. Never `null`. |
| `updateInfo` | `UpdateInfo` | Version and update state |

---

### Parameter Object

Represents a single Fusion user parameter.

```json
{
  "key": "JmFudG...",
  "name": "width",
  "expression": "10 mm",
  "unit": "mm",
  "comment": "Overall width",
  "isFavorite": false,
  "group": "Dimensions",
  "valuePreview": "10 mm",
  "previousExpression": "8 mm",
  "previousValue": "8 mm",
  "metadataChangedAt": 1700000000000,
  "metadataRevision": 3,
  "metadataWriterId": "550e8400-e29b-41d4-a716-446655440000",
  "metadataWriterVersion": "0.4.11"
}
```

| Field | Type | Description |
|---|---|---|
| `key` | `string` | Fusion `entityToken` — stable persistent identifier. **Prefer over `name` for all API calls.** |
| `name` | `string` | Fusion parameter name (unique within design) |
| `expression` | `string` | Current expression formula (e.g. `"width * 2"`, `"10 mm"`) |
| `unit` | `string` | Unit string (e.g. `"mm"`, `"deg"`, `""` for unitless, `"Text"` for text params) |
| `comment` | `string` | User-provided comment; empty string if none |
| `isFavorite` | `boolean` | Whether user has marked this parameter as a favorite |
| `group` | `string` | Group name. Empty string `""` means Ungrouped. |
| `valuePreview` | `string` | Human-formatted evaluated value (e.g. `"40 mm"`, `"hello"`) |
| `previousExpression` | `string` | Expression before the most recent edit. Empty if no edit history. Used by revert. |
| `previousValue` | `string` | Evaluated value of `previousExpression`. Empty if no edit history. |
| `metadataChangedAt` | `number` | Unix millisecond timestamp of last metadata write |
| `metadataRevision` | `number` | Monotonically increasing revision counter for conflict detection |
| `metadataWriterId` | `string` | UUID of the client instance that last wrote metadata |
| `metadataWriterVersion` | `string` | Add-in version string of the last metadata writer |

---

### ModelParameter Object

Represents a single Fusion model parameter (auto-generated by sketch constraints, features, joints, etc.).

```json
{
  "key": "JmFudG...",
  "name": "d1",
  "expression": "5 mm",
  "unit": "mm",
  "comment": "",
  "isFavorite": false,
  "valuePreview": "5 mm",
  "isDeletable": false,
  "createdBy": "Sketch1",
  "componentName": "Body",
  "componentId": "JkNvbXBv..."
}
```

| Field | Type | Description |
|---|---|---|
| `key` | `string` | Fusion `entityToken` — stable persistent identifier. Prefer over `name` for API calls. |
| `name` | `string` | Fusion-assigned name (e.g. `d1`, `d22`). Read-only — cannot be renamed. |
| `expression` | `string` | Current expression (editable via `updateModelParameter`). |
| `unit` | `string` | Unit string (e.g. `"mm"`, `"deg"`). Read-only. |
| `comment` | `string` | User-provided comment; empty string if none. Editable via `updateModelParameter`. |
| `isFavorite` | `boolean` | Whether user has marked this parameter as a favorite. Editable via `setParameterFavorite`. |
| `valuePreview` | `string` | Human-formatted evaluated value. |
| `isDeletable` | `boolean` | Always `false` — model parameters cannot be deleted via this add-in or Fusion's API. |
| `createdBy` | `string` | Display name of the Fusion object that created this parameter (e.g. `"Sketch1"`, `"Extrude1"`). Empty string if undetectable. |
| `componentName` | `string` | Display name of the component that owns this parameter (e.g. `"Body"`, `"Lid"`). Empty string for root component parameters. Display label only — subject to change on rename. |
| `componentId` | `string` | Stable identity token for the owning component (`Component.entityToken`). Survives component renames within the same design session. Empty string when unavailable — never fabricated. Use this (not `componentName`) as the key for persistent group-order state. |

**Scope:** All components in the design via `design.allComponents`. Parameters from every sub-component are included. Results are sorted by `componentName` then `name`, both case-insensitive.

**Not included:** `group`, `previousExpression`, `previousValue`, metadata fields. Model parameters are Fusion-managed artifacts and are not annotated by Better Parameters.

---

### Settings Object

All persisted UI settings. The full shape as stored and returned:

```json
{
  "theme": "light",
  "rememberUnit": false,
  "lastUnit": "",
  "paletteSize": { "width": 520, "height": 640 },
  "palettePosition": { "x": 100, "y": 200 },
  "paletteDockingState": "floating",
  "parameterTableColumns": {
    "parameter": 140,
    "name": 180,
    "unit": 80,
    "expression": 220,
    "value": 120
  },
  "unitCategoryState": {
    "Length": true,
    "Angle": true,
    "Area": false,
    "Volume": false,
    "Mass": false,
    "Time": false,
    "Density": false,
    "Force": false,
    "Pressure": false,
    "Energy": false,
    "Power": false,
    "Velocity": false
  },
  "customUnits": [],
  "showRevertButtons": true,
  "showCommentColumn": false,
  "showTextTunerSidebar": true,
  "autoFitColumns": true,
  "pinnedUnits": [],
  "autoCheckUpdates": true,
  "updateCheck": {},
  "autoOpenOnStart": false
}
```

#### Column key mapping

| Key | Display column | What it shows |
|---|---|---|
| `parameter` | Parameter | Fusion parameter identifier (the name Fusion uses internally) |
| `name` | Name | User-facing display name / label |
| `unit` | Unit | Unit string (e.g. `mm`, `deg`) |
| `expression` | Expression | Formula or value expression (e.g. `width * 2`) |
| `value` | Value | Computed value with action buttons |

The Comments text column (sixth visible column) is controlled by `showCommentColumn` and has no width in `parameterTableColumns` — its width is calculated automatically from remaining space.

#### Settings field reference

| Field | Type | Notes |
|---|---|---|
| `theme` | `"light" \| "dark"` | UI color theme |
| `rememberUnit` | `boolean` | Persist `lastUnit` between sessions |
| `lastUnit` | `string` | Last used unit string |
| `paletteSize` | `{ width: int, height: int }` | Palette pixel dimensions |
| `palettePosition` | `{ x: int, y: int }` | Palette screen position |
| `paletteDockingState` | `"floating" \| "left" \| "right" \| "top" \| "bottom"` | Palette docking mode |
| `parameterTableColumns` | `{ [key: string]: number }` | Per-column pixel widths. Keys: `parameter`, `name`, `unit`, `expression`, `value` |
| `unitCategoryState` | `{ [category: string]: boolean }` | Which unit categories are expanded in the unit picker |
| `customUnits` | `string[]` | User-added unit strings; max 40; deduplicated |
| `showRevertButtons` | `boolean` | Show per-row revert buttons in the parameter table |
| `showCommentColumn` | `boolean` | Show the comments column |
| `showTextTunerSidebar` | `boolean` | Show the text tuner sidebar panel |
| `autoFitColumns` | `boolean` | Auto-resize columns to fit content |
| `pinnedUnits` | `string[]` | Pinned unit strings shown prominently in unit picker; max 40 |
| `autoCheckUpdates` | `boolean` | Check GitHub for updates on startup |
| `updateCheck` | `object` | Internal update cache — treat as opaque, do not write |
| `autoOpenOnStart` | `boolean` | Open palette automatically when Fusion starts |

---

### UpdateInfo Object

Version and update pipeline state.

```json
{
  "currentVersion": "0.4.11",
  "latestVersion": "0.4.12",
  "hasUpdate": true,
  "latestUrl": "https://github.com/macifoxispurple/FusionBetterParameters/releases/latest",
  "latestNotes": "## v0.4.12\n- Bug fixes",
  "autoCheckUpdates": true,
  "updateState": "idle",
  "targetVersion": "0.4.12",
  "installedVersion": "",
  "error": ""
}
```

| Field | Type | Description |
|---|---|---|
| `currentVersion` | `string` | Running add-in version (from manifest) |
| `latestVersion` | `string` | Latest version from GitHub releases API |
| `hasUpdate` | `boolean` | `true` if `latestVersion > currentVersion` |
| `latestUrl` | `string` | URL to the GitHub release page |
| `latestNotes` | `string` | Release notes markdown for the latest version |
| `autoCheckUpdates` | `boolean` | Mirrors `settings.autoCheckUpdates` |
| `updateState` | `"idle" \| "downloading" \| "staged" \| "applied" \| "failed"` | Update pipeline state machine |
| `targetVersion` | `string` | Version being downloaded/staged (empty if idle) |
| `installedVersion` | `string` | Version that was applied (populated after `"applied"`) |
| `error` | `string` | Error message if `updateState === "failed"` |

---

## JS → Python Actions (requests)

All requests use `window.adsk.fusionSendData(action, JSON.stringify(payload))`.

---

### `ready`

Alias for [`refresh`](#refresh). Called exactly once when the UI has fully loaded and the `fusionReceiveData` handler is registered. Bootstraps the initial state. Both `"ready"` and `"refresh"` trigger identical behavior — use `"ready"` for initial load and `"refresh"` for subsequent on-demand refreshes as a semantic convention.

**Request payload:** `{}` (empty object)

**Response:** Full State Payload

**Side effects:** None — state is returned only via the `fusionSendData` return value.

**Example:**
```javascript
window.fusionReceiveData = function(action, dataString) { /* ... */ };
const state = await window.adsk.fusionSendData("ready", JSON.stringify({}));
applyState(state);
```

---

### `refresh`

Request a fresh state snapshot on demand. Use when the user switches documents or when the UI suspects state may be stale. Identical in behavior to `ready`.

**Request payload:** `{}`

**Response:** Full State Payload

**Side effects:** None — state is returned only via the `fusionSendData` return value.

---

### `createParameter`

Create a new Fusion user parameter.

**Request payload:**
```json
{
  "name": "width",
  "expression": "10 mm",
  "unit": "mm",
  "comment": "Overall width"
}
```

| Field | Required | Description |
|---|---|---|
| `name` | Yes | Parameter name. Must match `^[A-Za-z_"$°µ][A-Za-z0-9_"$°µ]*$`. Must not already exist in the design. |
| `expression` | Yes | Formula or value. Must be valid Fusion expression for the given unit. |
| `unit` | No | Unit string. Empty string `""` = unitless. `"Text"` = text parameter. Defaults to `""`. |
| `comment` | No | Optional comment string. |

**Response:** Full State Payload on success, error object on failure.

**Common errors:**
- `"Parameter 'width' already exists."` — duplicate name
- `"Invalid parameter name."` — fails regex
- `"Invalid expression."` — Fusion rejected the expression
- Expression/unit mismatch — e.g. giving `"10 mm"` when unit is `""`

---

### `deleteParameter`

Permanently delete a user parameter from the Fusion design.

**Request payload:**
```json
{
  "key": "JmFudG...",
  "name": "width"
}
```

| Field | Required | Description |
|---|---|---|
| `key` | Preferred | Entity token of the parameter. |
| `name` | Fallback | Parameter name. Used only if `key` is absent or does not resolve. |

At least one of `key` or `name` must be provided.

**Response:** Full State Payload on success, error object on failure.

**Common errors:**
- `"User parameter was not found."` — no parameter matches the given `key` or `name`
- `"Fusion could not delete this parameter: ..."` — Fusion rejected the deletion (e.g. parameter is in use by a model feature). The Fusion error message is appended.

**Notes:**
- Deletion is permanent and cannot be undone via the add-in. Fusion's own undo stack may allow recovery.
- If the deleted parameter is referenced in other parameters' expressions, Fusion will reject the deletion and return an error.

---

### `deleteParameters`

Batch-delete one or more user parameters in a single call. Processes each parameter independently — partial success is possible.

**Request payload:**
```json
{
  "keys": ["token_A", "token_B"],
  "names": ["width"]
}
```

| Field | Required | Description |
|---|---|---|
| `keys` | Preferred | Array of entity tokens. Deduplicated; parameters already covered by a `key` are not re-resolved from `names`. |
| `names` | Fallback | Array of parameter names. Used for items not covered by `keys`. |

At least one of `keys` or `names` must be present and non-empty.

**Response (all deleted):**
```json
{ "ok": true, "message": "", "state": { /* State Payload */ }, "deletedCount": 2, "failedCount": 0, "failedDetails": [] }
```

**Response (partial success):**
```json
{ "ok": true, "message": "1 parameter(s) could not be deleted.", "state": { /* State Payload */ }, "deletedCount": 1, "failedCount": 1, "failedDetails": [{ "key": "token_B", "name": "height", "message": "Fusion could not delete this parameter: ..." }] }
```

**Response (all failed):**
```json
{ "ok": false, "message": "No parameters were deleted. ...", "state": null, "deletedCount": 0, "failedCount": 2, "failedDetails": [ ... ] }
```

| Extra field | Type | Description |
|---|---|---|
| `deletedCount` | `number` | Parameters successfully deleted |
| `failedCount` | `number` | Parameters that could not be resolved or deleted |
| `failedDetails` | `object[]` | Per-item failure info: `{ key, name, message }` |

**`ok` semantics:** `true` if at least one parameter was deleted; `false` if none were deleted. `state` is populated when `ok: true`, `null` when `ok: false`.

**Common failure reasons:**
- Parameter not found (bad key or name)
- Fusion rejects deletion because parameter is referenced by model features or other parameters' expressions

---

### `updateParameter`

Update the expression and/or comment of an existing user parameter.

**Request payload:**
```json
{
  "key": "JmFudG...",
  "name": "width",
  "expression": "15 mm",
  "comment": "Updated width"
}
```

| Field | Required | Description |
|---|---|---|
| `key` | Preferred | Entity token of the parameter. Preferred over `name` — resolves correctly even if the parameter was renamed externally. |
| `name` | Fallback | Parameter name. Used only if `key` is absent or does not resolve to a parameter. |
| `expression` | Yes | New expression. Must be valid for the parameter's current unit. |
| `comment` | No | New comment. Omit or pass empty string to clear. |

At least one of `key` or `name` must be provided.

**Response:** Full State Payload on success, error object on failure.

**Notes:**
- Before applying the new expression, Python snapshots the current expression into `previousExpression` (enabling revert).
- You cannot change the `name` or `unit` of an existing parameter via this action. Renaming requires deleting and recreating (not supported as a single atomic action in this API).

---

### `batchUpdateParameters`

Apply expression and comment updates to multiple user parameters in a single Fusion call. Uses `design.modifyParameters()` (Fusion API Sept 2022+) to trigger **one design recomputation** for all changes instead of one per parameter. Use this action for Apply All in manual-compute mode.

**Request payload:**
```json
{
  "updates": [
    { "key": "JmFudG...", "name": "width",  "expression": "50 mm",  "comment": "shelf width" },
    { "key": "JmFudH...", "name": "height", "expression": "100 mm", "comment": "" }
  ]
}
```

| Field | Required | Description |
|---|---|---|
| `updates` | Yes | Array of update records. Must be a non-empty array. |
| `updates[].key` | Preferred | Entity token of the parameter. Preferred over `name`. |
| `updates[].name` | Fallback | Parameter name. Used only if `key` is absent or does not resolve. |
| `updates[].expression` | Yes | New expression string. |
| `updates[].comment` | No | New comment string. Omit to leave existing comment unchanged. Pass `""` to clear. |

At least one of `key` or `name` must be present per record.

**Response on success:**
```json
{
  "ok": true,
  "state": { ... },
  "updatedCount": 2,
  "failedRows": [],
  "message": ""
}
```

**Response on failure:**
```json
{
  "ok": false,
  "errorCode": "NOT_FOUND",
  "message": "1 parameter(s) not found.",
  "state": null,
  "updatedCount": 0,
  "failedRows": [{ "name": "height", "message": "Parameter not found." }]
}
```

**Common errors:**

| Scenario | `errorCode` | Notes |
|---|---|---|
| One or more parameters not found | `NOT_FOUND` | Reported per-record in `failedRows`. No parameters are updated. |
| Fusion rejects an expression | `VALIDATION_ERROR` | `design.modifyParameters` is all-or-nothing — if Fusion rejects any expression, no parameters are updated. |
| `design.modifyParameters` unavailable (old Fusion build) | — | Falls back to sequential `.expression=` assignments. Partial success possible; failed rows reported in `failedRows`. |
| `updates` is not an array | `VALIDATION_ERROR` | Raised before touching Fusion. |

**Notes:**
- `design.modifyParameters` is **all-or-nothing**: if Fusion rejects any expression in the batch (circular reference, invalid unit, etc.), no parameters are updated. FE should pre-validate all expressions via `validateExpression` before calling this action.
- Renames are not included in this action. Apply any pending renames via `renameParameter` before calling `batchUpdateParameters`.
- Comments are applied per-parameter after expressions. Comment failures are non-fatal and silently skipped.
- `state` is `null` on failure; FE should keep existing dirty state for retry.

---

### `renameParameter`

Rename an existing user parameter. The entity token (`key`) is stable across renames — FE references do not need to be updated.

**Request payload:**
```json
{ "key": "JmFudG...", "name": "width", "newName": "baseWidth" }
```

| Field | Required | Description |
|---|---|---|
| `key` | Preferred | Entity token. Preferred over `name`. |
| `name` | Fallback | Current parameter name. Used only if `key` is absent or does not resolve. |
| `newName` | Yes | The new name. Must pass all `validateParameterName` checks. |

At least one of `key` or `name` must be provided.

**Response:** Full State Payload on success, error object on failure.

**Common errors:**
- `"Parameter 'newName' already exists."` — name collision
- `"Fusion could not rename this parameter: ..."` — Fusion API rejection

**Notes:** Entity token does not change on rename. FE key references remain valid.

---

### `getModelParameters`

Fetch a paginated, optionally filtered list of model parameters. Read-only — `state` is always `null`.

Model parameters are **not** included in the State Payload (only `modelParameterCount` is). FE must call this action explicitly to load parameter data — on section expand, on search input, and after `updateModelParameter`.

**Request payload:**
```json
{
  "offset": 0,
  "limit": 200,
  "filter": "sketch"
}
```

| Field | Required | Description |
|---|---|---|
| `offset` | No | 0-based index of first result. Default `0`. Negative values clamped to `0`. |
| `limit` | No | Max results to return. Default `200`. Minimum `1`. Hard cap `1000`. |
| `filter` | No | Case-insensitive substring filter applied to `name`, `expression`, and `componentName`. Absent or empty = return all. |

**Response:**
```json
{
  "ok": true,
  "state": null,
  "totalCount": 50000,
  "parameters": [ /* ModelParameter objects, see below */ ],
  "offset": 0,
  "limit": 200
}
```

| Field | Type | Description |
|---|---|---|
| `totalCount` | `number` | Total items matching the filter (not the page size). Use for pagination UI (page count, scroll height). |
| `parameters` | `ModelParameter[]` | Serialized model parameters for the requested page, sorted case-insensitively by name. |
| `offset` | `number` | Echoes the requested offset. |
| `limit` | `number` | Echoes the effective limit (after capping). |

**Requires active design.** Returns `BPNoDesignError` (`NO_DESIGN`) if no design is open.

**Performance notes:**
- Each call iterates all model parameters to apply filter and sort — O(N) in total parameter count.
- For designs with tens of thousands of model parameters, use `filter` to narrow the result set before paginating.
- For virtual scroll: request a page at `offset` / `limit` matching the visible viewport; `totalCount` drives the scroll height.
- `_MODEL_PARAMETER_MAX_LIMIT = 1000` — requesting more than 1000 per page is capped silently.

**FE integration pattern:**
1. On state push: read `modelParameterCount` to decide whether to show the model parameters section and how many items to expect.
2. On section expand (or initial load if auto-expanded): call `getModelParameters({ offset: 0, limit: 200 })`.
3. On scroll / pagination: call with updated `offset`.
4. On search input: call with `filter` set; reset `offset` to `0`.
5. After `updateModelParameter` succeeds: re-fetch the current page to reflect updated values.

---

### `updateModelParameter`

Update the expression and/or comment of an existing model parameter.

**Request payload:**
```json
{
  "key": "JmFudG...",
  "name": "d1",
  "expression": "15 mm",
  "comment": "Shelf depth"
}
```

| Field | Required | Description |
|---|---|---|
| `key` | Preferred | Entity token of the model parameter. Preferred over `name`. |
| `name` | Fallback | Fusion-assigned name (e.g. `d1`). Used only if `key` is absent or does not resolve. |
| `expression` | Yes | New expression. Must be valid for the parameter's current unit. |
| `comment` | No | New comment. Omit or pass empty string to clear. |

At least one of `key` or `name` must be provided.

**Response:** Full State Payload on success, error object on failure.

**Common errors:**
- `"Either \"key\" or \"name\" is required."` — neither field provided
- `"Model parameter was not found."` — token/name does not resolve to a model parameter
- `"Expression validation failed: ..."` — expression invalid for the parameter's unit
- `"Fusion could not update model parameter '...': ..."` — Fusion API rejection

**Notes:**
- `name` and `unit` are read-only on model parameters; only `expression` and `comment` are mutable.
- `isDeletable` is always `false` — model parameters cannot be deleted via this API.
- Parameters from all components in the design are accessible via `getModelParameters`. `updateModelParameter` also resolves parameters across all components.
- No revert history is tracked for model parameters (metadata tracking applies to user parameters only).

---

### `copyParameter`

Create a copy of an existing user parameter with a collision-safe name. The copy is placed in the same group as the source, at the end of the display order.

**Request payload:**
```json
{ "key": "JmFudG...", "name": "width", "targetName": "widthCopy" }
```

| Field | Required | Description |
|---|---|---|
| `key` | Preferred | Entity token of the source parameter. |
| `name` | Fallback | Source parameter name. |
| `targetName` | No | Name for the copy. If omitted, auto-generated as `{name}_copy`, then `{name}_copy_2`, etc. |

**Response:** Full State Payload on success, error object on failure.

**Copied:** expression, unit, comment, group assignment.  
**Not copied:** isFavorite (defaults to `false`), revert history.

**Common errors:**
- `"Parameter 'widthCopy' already exists."` — `targetName` collides with an existing parameter.
- `"Fusion could not create the parameter copy."` — Fusion API rejection (e.g. invalid expression for unit).

---

### `sortByTimelineOrder`

Reset the display order of all parameters to match Fusion's native creation (timeline) order. `design.userParameters` iterates parameters in creation order — this action adopts that as the stored sort order.

**Request payload:** `{}`

**Response:** Full State Payload. `state.parameters` will be ordered by Fusion creation sequence.

**Notes:**
- Overwrites any user-defined display order for all groups.
- Group assignments and group UI state (collapse, order) are unaffected.
- Use `saveParameterOrder` to restore a custom order afterward.

---

### `revertParameter`

Revert a parameter to its previous expression (undo the last expression edit stored in metadata).

**Request payload:**
```json
{
  "key": "JmFudG...",
  "name": "width",
  "comment": "Reverted"
}
```

| Field | Required | Description |
|---|---|---|
| `key` | Preferred | Entity token of the parameter. Preferred over `name`. |
| `name` | Fallback | Parameter name. Used only if `key` is absent or doesn't resolve. |
| `comment` | No | Optional comment to apply on revert. If omitted, the comment is left unchanged. |

At least one of `key` or `name` must be provided.

**Response:** Full State Payload on success.

**Error:** `{ "ok": false, "message": "No previous expression is available to revert." }` if `previousExpression` is empty.

---

### `exportParameters`

Export all current user parameters to a CSV file. Opens a native OS save dialog unless `filePath` is provided. Does not mutate Fusion state — `state` is always `null`.

**Request payload:**
```json
{ "filePath": "/optional/explicit/path/export.csv" }
```

| Field | Required | Description |
|---|---|---|
| `filePath` | No | Absolute path to write. If absent or empty, a native OS save dialog is shown. |

**Response (success):**
```json
{ "ok": true, "message": "", "state": null, "exportedCount": 5, "filePath": "/path/to/export.csv" }
```

**Response (cancelled):**
```json
{ "ok": false, "message": "Export cancelled.", "state": null, "exportedCount": 0, "filePath": "" }
```

| Extra field | Type | Description |
|---|---|---|
| `exportedCount` | `number` | Number of parameters written to the file |
| `filePath` | `string` | Absolute path of the file written; empty if cancelled |

**CSV format:**

```
name,expression,unit,comment,group
width,10 mm,mm,Overall width,Dimensions
ratio,0.5,,Unitless ratio,
label,Hello,Text,Text param,
```

Column order: `name`, `expression`, `unit`, `comment`, `group`. Header row always present. Empty `unit` = unitless. `group` empty = Ungrouped. File is UTF-8 with BOM for Excel compatibility on Windows.

**Notes:**
- Parameters are exported in current display order (respects user-defined sort).
- Destination: local filesystem via native OS save dialog, or explicit `filePath` for programmatic use / FE fixture testing.
- Cloud file management is outside the scope of this add-in. Users who need cloud storage should export to a local file and manage upload separately using Fusion's own data tools.

---

### `importParameters`

Import user parameters from a CSV file. Opens a native OS open dialog unless `filePath` is provided. Mutating — returns full State Payload on success.

**Request payload:**
```json
{
  "filePath": "/optional/explicit/path/import.csv",
  "conflictPolicy": "skip"
}
```

| Field | Required | Description |
|---|---|---|
| `filePath` | No | Absolute path to read. If absent or empty, a native OS open dialog is shown. |
| `conflictPolicy` | No | `"skip"` (default) or `"overwrite"`. See below. |

**Conflict policy:**

| Value | Behaviour |
|---|---|
| `"skip"` | If a parameter with the same name already exists, leave it unchanged and increment `skippedCount`. |
| `"overwrite"` | If a parameter with the same name already exists, update its `expression` and `comment`. Group is also updated if specified in the CSV. |

**Request also accepts `dryRun: true`** — runs all validation and conflict logic but applies no mutations. Same response shape; `state` is always `null` on dry-run.

**Response (success — all imported):**
```json
{ "ok": true, "message": "", "state": { /* State Payload */ }, "filePath": "/path/to/import.csv", "importedCount": 3, "skippedCount": 0, "failedCount": 0, "failedRows": [], "dryRun": false }
```

**Response (dry-run):**
```json
{ "ok": true, "message": "", "state": null, "filePath": "/path/to/import.csv", "importedCount": 3, "skippedCount": 0, "failedCount": 0, "failedRows": [], "dryRun": true }
```

**Response (partial success):**
```json
{ "ok": true, "message": "1 row(s) could not be imported.", "state": { /* State Payload */ }, "filePath": "/path/to/import.csv", "importedCount": 2, "skippedCount": 0, "failedCount": 1, "failedRows": [{ "row": 3, "name": "bad", "message": "Invalid expression." }], "dryRun": false }
```

**Response (all skipped — skip policy):**
```json
{ "ok": true, "message": "3 parameter(s) already exist and were skipped (conflictPolicy: skip).", "state": { /* State Payload */ }, "filePath": "/path/to/import.csv", "importedCount": 0, "skippedCount": 3, "failedCount": 0, "failedRows": [], "dryRun": false }
```

**Response (all failed — none imported):**
```json
{ "ok": false, "message": "No parameters were imported. ...", "state": null, "filePath": "/path/to/import.csv", "importedCount": 0, "skippedCount": 0, "failedCount": 2, "failedRows": [ ... ], "dryRun": false }
```

**Response (cancelled):**
```json
{ "ok": false, "message": "Import cancelled.", "state": null, "filePath": "", "importedCount": 0, "skippedCount": 0, "failedCount": 0, "failedRows": [], "dryRun": false }
```

| Extra field | Type | Description |
|---|---|---|
| `filePath` | `string` | Absolute path of the file read. Always echoed — empty string if cancelled before file selection. FE should pass this value back as `filePath` on the commit call after a dry-run to avoid a second file-picker dialog. |
| `importedCount` | `number` | Parameters successfully created or updated |
| `skippedCount` | `number` | Parameters skipped due to `conflictPolicy: "skip"` |
| `failedCount` | `number` | Rows that could not be imported (validation or Fusion rejection) |
| `failedRows` | `object[]` | Per-row failure info: `{ row: number, name: string, message: string }`. `row` is 1-based CSV line number. |
| `dryRun` | `boolean` | Echoes the `dryRun` flag from the request. |

**`ok` semantics:** `true` if the file was read and processed, even if `importedCount` is 0 (all skipped is not an error). `false` if cancelled, file unreadable, invalid CSV format, or zero imported with at least one failed row.

**`state` semantics:** non-null when `ok: true` and `dryRun: false`; `null` otherwise.

**CSV format:** same as `exportParameters`. Header row required. `name` and `expression` columns required; `unit`, `comment`, `group` are optional and default to empty string.

**Row-level validation:**
- `name` missing or empty → row fails
- `expression` missing or empty → row fails
- `name` fails `validateParameterName` checks (format, reserved words) → row fails (create path only)
- Expression invalid for the given unit → row fails (create path only)
- Fusion rejects the parameter → row fails with Fusion error message

**Notes:**
- Source: local filesystem via native OS open dialog, or explicit `filePath` for programmatic use / FE fixture testing.
- Cloud file management is outside the scope of this add-in.
- Rows are processed in CSV order. A row failure does not abort remaining rows.

---

### `exportParametersPackage`

Export user parameters with optional BP metadata (groups, favorites, display order, comments) to a `.bpmeta.json` file. Opens a native OS save dialog unless `filePath` is provided. Read-only — `state` is always `null`.

**Request payload:**
```json
{
  "filePath": "/optional/explicit/path/output.bpmeta.json",
  "includeComments": true,
  "includeGroups": true,
  "includeFavorites": true,
  "includeOrder": false
}
```

| Field | Required | Default | Description |
|---|---|---|---|
| `filePath` | No | — | Absolute path to write. If absent or empty, a native OS save dialog is shown. Extension `.bpmeta.json` appended automatically if missing. |
| `includeComments` | No | `true` | Include `comment` field in each record. |
| `includeGroups` | No | `true` | Include `group` field in each record. |
| `includeFavorites` | No | `true` | Include `isFavorite` field in each record. |
| `includeOrder` | No | `false` | Include `displayOrder` (0-based index) in each record to preserve current display ordering on import. |

**Response (success):**
```json
{ "ok": true, "message": "", "state": null, "exportedCount": 5, "filePath": "/path/to/output.bpmeta.json", "format": "bpmeta.json" }
```

**Response (cancelled):**
```json
{ "ok": false, "message": "Export cancelled.", "state": null, "exportedCount": 0, "filePath": "", "format": "bpmeta.json" }
```

| Extra field | Type | Description |
|---|---|---|
| `exportedCount` | `number` | Parameters written to the package. |
| `filePath` | `string` | Resolved path of the written file. |
| `format` | `string` | Always `"bpmeta.json"` for this action (distinguishes from CSV export). |

**Package format:** See [BP Meta Package Format](#bp-meta-package-format).

**Notes:**
- `metadataRevision` and `metadataChangedAt` are always written as advisory fields regardless of the include flags.
- Scope: user parameters only. Model parameters are not exported.
- Cloud file management is outside the scope of this add-in.

---

### `validateParametersPackageImport`

Preflight check for a `.bpmeta.json` import. Parses the package, classifies each row, and returns a preview summary. **No mutations are applied.** Read-only — `state` is always `null`.

Opens a native OS open dialog if `filePath` is absent. The resolved `filePath` is returned so FE can pass it to `importParametersPackage` without re-opening the dialog.

**Request payload:**
```json
{
  "filePath": "",
  "conflictPolicy": "skip",
  "applyExpressionsUnits": false,
  "applyComments": true,
  "applyGroups": true,
  "applyFavorites": true,
  "applyOrder": false
}
```

| Field | Required | Default | Description |
|---|---|---|---|
| `filePath` | No | — | Absolute path. If absent or empty, shows OS open dialog. |
| `conflictPolicy` | No | `"skip"` | `"skip"`, `"overwrite"`, or `"merge-safe"`. See [Package Conflict Policies](#package-conflict-policies). |
| `applyExpressionsUnits` | No | `false` | Apply `expression` and `unit` from the package when updating existing parameters. Always applied when creating new parameters. |
| `applyComments` | No | `true` | Apply `comment` from the package. |
| `applyGroups` | No | `true` | Apply `group` from the package. |
| `applyFavorites` | No | `true` | Apply `isFavorite` from the package. |
| `applyOrder` | No | `false` | Apply `displayOrder` from the package to set display ordering. |

**Response (success):**
```json
{
  "ok": true,
  "message": "",
  "state": null,
  "filePath": "/resolved/path/file.bpmeta.json",
  "preview": {
    "addCount": 2,
    "updateCount": 3,
    "skipCount": 1,
    "potentialFailCount": 0,
    "warnings": [],
    "failedRows": []
  }
}
```

**Response (cancelled):**
```json
{ "ok": false, "message": "Import cancelled.", "state": null, "filePath": "", "preview": null }
```

| Preview field | Type | Description |
|---|---|---|
| `addCount` | `number` | Parameters that will be created (name not in destination). |
| `updateCount` | `number` | Existing parameters that will be updated (based on conflict policy). |
| `skipCount` | `number` | Existing parameters that will be skipped (conflictPolicy: `"skip"`). |
| `potentialFailCount` | `number` | Rows that may fail (expression validation warnings). Not hard failures. |
| `warnings` | `string[]` | Human-readable per-parameter warning strings for `potentialFailCount` rows. |
| `failedRows` | `object[]` | Rows that will definitely fail: missing name, duplicate name in package, invalid name format, or missing expression for new params. `{ row, name, message }`. |

**Notes:**
- Use the returned `filePath` as the `filePath` input to `importParametersPackage` to skip re-opening the dialog.
- `failedRows` in the preview are definite failures. `warnings` are advisory — the actual import may still succeed if Fusion accepts the expression.
- Validate knobs must match the knobs you pass to `importParametersPackage` to get an accurate preview.

---

### `importParametersPackage`

Import user parameters from a `.bpmeta.json` package. Opens a native OS open dialog unless `filePath` is provided. Mutating — returns full State Payload on success.

**Request payload:** Same fields as `validateParametersPackageImport`.

```json
{
  "filePath": "/resolved/path/file.bpmeta.json",
  "conflictPolicy": "skip",
  "applyExpressionsUnits": false,
  "applyComments": true,
  "applyGroups": true,
  "applyFavorites": true,
  "applyOrder": false
}
```

**Request also accepts `dryRun: true`** — runs all validation and conflict logic but applies no mutations. Same response shape; `state` is always `null` on dry-run.

**Response (success — all imported):**
```json
{ "ok": true, "message": "", "state": { /* State Payload */ }, "filePath": "/path/to/file.bpmeta.json", "importedCount": 2, "updatedCount": 3, "skippedCount": 0, "failedCount": 0, "failedRows": [], "dryRun": false }
```

**Response (dry-run):**
```json
{ "ok": true, "message": "", "state": null, "filePath": "/path/to/file.bpmeta.json", "importedCount": 2, "updatedCount": 3, "skippedCount": 0, "failedCount": 0, "failedRows": [], "dryRun": true }
```

**Response (partial success):**
```json
{ "ok": true, "message": "1 row(s) could not be imported.", "state": { /* State Payload */ }, "filePath": "/path/to/file.bpmeta.json", "importedCount": 1, "updatedCount": 2, "skippedCount": 0, "failedCount": 1, "failedRows": [{ "row": 3, "name": "bad", "message": "Fusion rejected the parameter." }], "dryRun": false }
```

**Response (all skipped):**
```json
{ "ok": true, "message": "3 parameter(s) already exist and were skipped (conflictPolicy: skip).", "state": { /* State Payload */ }, "filePath": "/path/to/file.bpmeta.json", "importedCount": 0, "updatedCount": 0, "skippedCount": 3, "failedCount": 0, "failedRows": [], "dryRun": false }
```

**Response (all failed — none imported):**
```json
{ "ok": false, "message": "No parameters were imported. ...", "state": null, "filePath": "/path/to/file.bpmeta.json", "importedCount": 0, "updatedCount": 0, "skippedCount": 0, "failedCount": 2, "failedRows": [ ... ], "dryRun": false }
```

**Response (cancelled):**
```json
{ "ok": false, "message": "Import cancelled.", "state": null, "filePath": "", "importedCount": 0, "updatedCount": 0, "skippedCount": 0, "failedCount": 0, "failedRows": [], "dryRun": false }
```

| Extra field | Type | Description |
|---|---|---|
| `filePath` | `string` | Absolute path of the file read. Always echoed — empty string if cancelled before file selection. Pass back as `filePath` on commit after dry-run. |
| `importedCount` | `number` | New parameters created. |
| `updatedCount` | `number` | Existing parameters updated (overwrite or merge-safe policy). |
| `skippedCount` | `number` | Existing parameters skipped (skip policy). |
| `failedCount` | `number` | Rows that failed. |
| `failedRows` | `object[]` | Per-row failure info: `{ row, name, message }`. |
| `dryRun` | `boolean` | Echoes the `dryRun` flag from the request. |

**`ok` semantics:** `true` if file was read and processed, even if `importedCount + updatedCount = 0` (all-skipped is not an error). `false` if cancelled, file unreadable, invalid format, or zero touched with at least one failed row.

**`state` semantics:** non-null when `ok: true` and `dryRun: false`; `null` otherwise.

**Row-level validation:**
- `name` missing → row fails
- Duplicate `name` within the package → row fails
- `name` fails `validateParameterName` checks → row fails (create path only)
- `expression` missing for new parameter → row fails
- Fusion rejects the parameter → row fails with Fusion error message

**Notes:**
- For new parameters, `expression` is always applied regardless of `applyExpressionsUnits`.
- `applyExpressionsUnits` controls whether `expression` is updated on **existing** parameters.
- Order application (`applyOrder`) failure is non-fatal — import result is not affected.
- Rows are processed in package order. A row failure does not abort remaining rows.

---

#### Package Conflict Policies

| Policy | Existing parameters | New parameters |
|---|---|---|
| `"skip"` | Unchanged (skipped). `skippedCount` incremented. | Created normally. |
| `"overwrite"` | All checked apply-fields applied. | Created normally. |
| `"merge-safe"` | Checked apply-fields applied; expression/unit only if `applyExpressionsUnits: true`. | Created normally. |

`"overwrite"` and `"merge-safe"` have identical runtime semantics — both respect the `applyExpressionsUnits` flag. The distinction is intent: use `"merge-safe"` when you want to apply organizational metadata (groups, favorites) to an already-configured document without accidentally overwriting expressions; use `"overwrite"` when replacing is the explicit goal.

---

#### BP Meta Package Format

Schema version: `1`.

```json
{
  "schemaVersion": 1,
  "exportedAt": "2026-04-17T12:00:00Z",
  "sourceDocument": { "name": "MyPart v1" },
  "parameters": [
    {
      "name": "width",
      "expression": "100 mm",
      "unit": "mm",
      "comment": "Overall width",
      "group": "Dimensions",
      "isFavorite": true,
      "displayOrder": 0,
      "metadataRevision": 3,
      "metadataChangedAt": 1713350400000
    }
  ]
}
```

| Top-level field | Required | Description |
|---|---|---|
| `schemaVersion` | Yes | Integer schema version. Currently `1`. Import fails if newer than supported. |
| `exportedAt` | No | ISO-8601 UTC timestamp. Advisory — not used by importer. |
| `sourceDocument` | No | Descriptor object. Advisory — not used by importer. |
| `parameters` | Yes | Array of parameter records. |

| Record field | Present when | Description |
|---|---|---|
| `name` | Always | Parameter name. Used as primary match key on import. |
| `expression` | Always | Expression string. Required to create new parameters. |
| `unit` | Always | Unit string. |
| `comment` | `includeComments: true` | Comment text. Empty string if absent. |
| `group` | `includeGroups: true` | Group name. Empty string if absent. |
| `isFavorite` | `includeFavorites: true` | Favorite flag. Defaults to `false` if absent. |
| `displayOrder` | `includeOrder: true` | 0-based display index within the export. Advisory on import. |
| `metadataRevision` | Always | Advisory — source document's metadata revision at export time. |
| `metadataChangedAt` | Always | Advisory — source document's metadata timestamp at export time. |

**Identity:** Import matches records to destination parameters by `name` only. Entity tokens are document-local and are not stored in or consumed from package files.

---

### `setParameterFavorite`

Toggle or set the favorite status of a parameter.

**Request payload:**
```json
{ "name": "width", "isFavorite": true }
```

| Field | Required | Description |
|---|---|---|
| `name` | Yes | Parameter name. |
| `isFavorite` | Yes | Boolean — `true` to mark favorite, `false` to unmark. |

**Response:** Full State Payload.

---

### `setParameterGroup`

Assign a parameter to a group, or remove it from any group (ungroup).

**Request payload:**
```json
{
  "key": "JmFudG...",
  "name": "width",
  "group": "Dimensions"
}
```

| Field | Required | Description |
|---|---|---|
| `key` | Preferred | Entity token. Preferred over `name`. |
| `name` | Fallback | Parameter name. |
| `group` | Yes | Target group name. Empty string `""` moves the parameter to Ungrouped. |

At least one of `key` or `name` must be provided.

**Response:** Full State Payload.

---

### `renameGroup`

Rename a group. All parameters currently in that group are updated to the new group name.

**Request payload:**
```json
{ "oldGroup": "Dims", "newGroup": "Dimensions" }
```

| Field | Required | Description |
|---|---|---|
| `oldGroup` | Yes | Current group name. Case-insensitive match. Cannot be empty string (Ungrouped cannot be renamed). |
| `newGroup` | Yes | New group name. Must not be empty string. |

**Response:** Full State Payload on success, error object on failure.

**Errors:**
- Attempting to rename Ungrouped (`oldGroup: ""`) is rejected.
- `newGroup` already exists as a different group — behavior: parameters are merged into it.

---

### `deleteGroup`

Delete a named group. All parameters in the group become ungrouped (moved to `group: ""`).

**Request payload:**
```json
{ "group": "OldGroup" }
```

| Field | Required | Description |
|---|---|---|
| `group` | Yes | Group name to delete. Cannot be empty string. |

**Response:** Full State Payload.

**Notes:** Does not delete parameters — only removes their group assignment.

---

### `saveParameterOrder`

Persist the display order of parameters. Supports two modes: **per-group** (preferred) and **global flat list** (legacy).

#### Per-group mode (preferred)

Reorders parameters within a single named group. All other groups' order is unaffected.

**Request payload:**
```json
{
  "group": "Dimensions",
  "keys": ["token_A", "token_B", "token_C"]
}
```

| Field | Required | Description |
|---|---|---|
| `group` | Yes (for per-group mode) | Name of the group whose order to update. Use `""` for Ungrouped. |
| `keys` | Yes | Ordered entity tokens for parameters within this group. |

**Notes:**
- Tokens not belonging to `group` are silently ignored.
- Parameters in `group` that are absent from `keys` are appended after the provided order, preserving their relative order.
- Parameters in all other groups are untouched.

#### Global flat-list mode (legacy)

Reorders all parameters across all groups in a single call. Use for bulk reorder operations or initial order import.

**Request payload:**
```json
{ "keys": ["token_A", "token_B", "token_C", "..."] }
```

| Field | Required | Description |
|---|---|---|
| `keys` | Yes | Ordered array of all entity tokens across all groups in the desired display order. |

**Notes:**
- Unknown tokens are silently ignored.
- Parameters absent from `keys` are appended at the end.

**Response:** Full State Payload (both modes).

---

### `saveGroupUiState`

Persist the group display order and per-group collapse state.

**Request payload:**
```json
{
  "groupUi": {
    "order": ["Dimensions", "Materials", "Config"],
    "collapsed": {
      "Dimensions": false,
      "Materials": true,
      "Config": false
    }
  }
}
```

| Field | Required | Description |
|---|---|---|
| `groupUi.order` | Yes | Array of group names in the desired display order. |
| `groupUi.collapsed` | Yes | Map of group name → boolean collapse state. |

**Notes:**
- Groups present in the design but absent from `order` are appended at the end.
- Groups in `order` or `collapsed` that no longer exist are silently ignored.
- The Ungrouped pseudo-group (empty string) should not be included in `order`.

**Response:** Full State Payload.

---

### `saveSettings`

Update one or more settings. Only the fields you include are changed — this is a partial update (merge, not replace).

**Request payload:** Any subset of the Settings Object fields.

```json
{
  "theme": "dark",
  "showRevertButtons": false,
  "paletteSize": { "width": 600, "height": 700 }
}
```

**Validation rules:**

| Field | Validation |
|---|---|
| `theme` | Must be `"light"` or `"dark"` |
| `paletteSize.width` | Integer ≥ 320 |
| `paletteSize.height` | Integer ≥ 240 |
| `palettePosition` | `{ x: int, y: int }` — both fields required if object is present |
| `paletteDockingState` | One of `"floating"`, `"left"`, `"right"`, `"top"`, `"bottom"` |
| `parameterTableColumns` | Object with numeric (> 0) values for recognized column keys |
| `customUnits` | String array; deduplicated; max 40 items |
| `pinnedUnits` | String array; deduplicated; max 40 items |
| All boolean fields | Must be actual booleans (not `0`/`1`) |

**Response:** Full State Payload.

**Notes:**
- Invalid values for individual fields cause the action to fail with an error.
- The `updateCheck` field is internal — do not write it.
- Prefer `savePaletteGeometry` over `saveSettings` when only persisting window chrome (size/position/docking). This avoids accidentally overwriting application settings with a partial payload.

---

### `savePaletteGeometry`

Persist only the palette window chrome — size, position, and docking state. Use this instead of `saveSettings` when responding to a window resize or drag event. Other settings are not touched.

**Request payload:** Any subset of the three geometry fields:
```json
{
  "paletteSize": { "width": 600, "height": 720 },
  "palettePosition": { "x": 200, "y": 100 },
  "paletteDockingState": "floating"
}
```

All three fields are optional. Only the fields present in the payload are updated.

**Validation:** Same rules as `saveSettings` for each individual field.

**Response:** Full State Payload.

---

### `getTextTunerState`

Load the current text tuner key/value map (typography and color customization for the UI).

**Request payload:** `{}`

**Response:**
```json
{
  "ok": true, "message": "", "state": null,
  "values": { "fontFamily": "Inter, sans-serif", "fontSize": "13px", "accentColor": "#5b8dd9" }
}
```

Read-only — `state` is `null`. Does not push `renderState`.

---

### `saveTextTunerState`

Persist text tuner key/value pairs. **Mutating** — returns full State Payload.

**Request payload:**
```json
{
  "values": {
    "fontFamily": "Roboto, sans-serif",
    "accentColor": "#ff6b35"
  }
}
```

**Limits:**
- Max 200 keys total.
- Keys: max 80 characters each.
- Values: max 300 characters each.

**Response:** Full State Payload. The saved text tuner state is reflected in `state.textTunerState`.

Does not push `renderState`.

---

### `validateParameterName`

Check whether a proposed name is valid for a new parameter. Does not mutate any state.

**Request payload:**
```json
{ "name": "myParam" }
```

**Response (valid):**
```json
{ "ok": true, "message": "", "state": null }
```

**Response (invalid):**
```json
{ "ok": false, "message": "A parameter named 'myParam' already exists.", "state": null }
```

**Validation checks performed:**
1. Name matches regex `^[A-Za-z_"$°µ][A-Za-z0-9_"$°µ]*$`
2. Name does not already exist in the design (user or model parameters)
3. Name is not a Fusion reserved keyword

Use this for real-time input validation before enabling the Create button.

---

### `validateExpression`

Check whether an expression string is syntactically and semantically valid. Does not mutate state.

**Request payload:**
```json
{
  "expression": "width * 2 + 5 mm",
  "currentParameterName": "height",
  "units": "mm"
}
```

| Field | Required | Description |
|---|---|---|
| `expression` | Yes | Expression string to validate. |
| `currentParameterName` | No | Name of the parameter being edited. Prevents Fusion from rejecting as self-referential. |
| `units` | No | Unit context for evaluation. Empty string for unitless. |

**Response (valid):**
```json
{ "ok": true, "message": "", "isIncomplete": false, "state": null }
```

**Response (invalid):**
```json
{ "ok": false, "message": "Unknown variable 'wdth'.", "isIncomplete": false, "state": null }
```

**Response (incomplete — still typing):**
```json
{ "ok": false, "message": "Expression looks incomplete after '+'. Add the next value or parameter.", "isIncomplete": true, "state": null }
```

`isIncomplete` is **always present** on all responses (`true` or `false`). `isIncomplete: true` means the expression is a valid prefix of a longer expression (user is mid-typing). Do not show this as a hard error in the UI — suppress or show as a subtle inline hint.

---

### `previewExpression`

Evaluate an expression and return its formatted computed value. Does not mutate state.

**Request payload:**
```json
{
  "expression": "width * 2",
  "currentParameterName": "height",
  "units": "mm",
  "fallbackPreview": "—"
}
```

| Field | Required | Description |
|---|---|---|
| `expression` | Yes | Expression to evaluate. |
| `currentParameterName` | No | Name of parameter being edited (avoids self-reference errors). |
| `units` | No | Unit context. |
| `fallbackPreview` | No | String to use as `preview` if evaluation fails. Defaults to `""`. |

**Response (success):**
```json
{ "ok": true, "message": "", "state": null, "preview": "40 mm" }
```

**Response (failure):**
```json
{ "ok": false, "message": "Unknown variable 'wdth'.", "state": null, "preview": "—" }
```

`preview` is always populated — with the evaluated value on success, or with `fallbackPreview` on failure. Use `preview` directly in the UI.

---

### `validateUnit`

Check whether a unit string is recognized by Fusion. Does not mutate state.

**Request payload:**
```json
{ "unit": "mm" }
```

**Response (valid):**
```json
{ "ok": true, "message": "", "state": null, "unit": "mm" }
```

The `unit` field in the response is the Fusion-normalized form of the unit (may differ in casing from input).

**Response (invalid):**
```json
{ "ok": false, "message": "\"xyz\" is not a valid Fusion unit.", "state": null, "unit": "" }
```

**Special case:** `"Text"` is always valid and is not passed to Fusion's unit validator. Use it for text parameters.

---

### `openHelpUrl`

Open a URL in the system default browser. Read-only — does not mutate state.

Intended use: the palette Info (i) help button passes the Fusion Parameters reference URL; Python opens it via the OS browser without requiring the WebView to navigate.

**Request payload:**
```json
{ "url": "https://help.autodesk.com/..." }
```

- `url` — required. Must start with `http://` or `https://`. Any other scheme returns `ok: false`.

**Response (success):**
```json
{ "ok": true, "message": "", "state": null }
```

**Response (invalid/missing url):**
```json
{ "ok": false, "message": "\"url\" must start with \"http://\" or \"https://\".", "state": null }
```

**Response (OS open failure):**
```json
{ "ok": false, "message": "Could not open URL: <reason>", "state": null }
```

**Notes:**
- Uses Python `webbrowser.open()` — fires the system default browser; safe on all platforms Fusion supports.
- The browser launch is fire-and-forget; `ok: true` means the launch was initiated, not that the page loaded.
- FE should treat `ok: false` as a non-critical error (show a snackbar/toast; do not block the palette).

---

### `copyToClipboard`

Write text to the OS clipboard via Python's native OS APIs. Read-only — does not mutate Fusion state.

Use this action instead of `navigator.clipboard.writeText()` or `document.execCommand('copy')`. Fusion 360's embedded QtWebEngine WebView has known clipboard access restrictions for non-secure contexts (local-file palette); the BE path bypasses all WebView security policies by writing directly to the OS clipboard.

**Request payload:**
```json
{ "text": "content to copy" }
```

- `text` — required, non-empty string. Any type-coercible value is stringified via `str()`.

**Response (success):**
```json
{ "ok": true, "message": "", "state": null }
```

**Response (empty/missing text):**
```json
{ "ok": false, "errorCode": "VALIDATION_ERROR", "message": "\"text\" is required and must be non-empty.", "state": null }
```

**Response (OS write failure):**
```json
{ "ok": false, "errorCode": "IO_ERROR", "message": "Clipboard write failed: <reason>", "state": null }
```

**Response (unsupported platform):**
```json
{ "ok": false, "errorCode": "IO_ERROR", "message": "Clipboard write not supported on platform: 'Linux'. Use the FE fallback (navigator.clipboard / execCommand).", "state": null }
```

**Platform implementation:**

| Platform | Method |
|---|---|
| Windows | Win32 `SetClipboardData(CF_UNICODETEXT, ...)` via `ctypes` — UTF-16-LE encoding, full Unicode support |
| macOS | `pbcopy` subprocess — UTF-8 encoding |
| Other | Returns `IO_ERROR`; FE should fall back to WebView clipboard APIs |

**Notes:**
- FE should call this as the primary clipboard path. Keep the existing `execCommand` / `navigator.clipboard` chain as a fallback for when the BE bridge is unavailable (e.g. `?mock=1` mode or harness environments).
- `ok: false` on `IO_ERROR` is non-critical — show a snackbar and offer manual select-copy.
- Does not require an active Fusion design.

---

### `checkForUpdates`

Force a fresh check against the GitHub releases API for the latest version. Updates `updateInfo` in state.

**Request payload:** `{}`

**Response:** Standard envelope with `state` populated (includes updated `updateInfo.latestVersion`).

---

### `downloadAndStageUpdate`

Download the latest release zip from GitHub and stage it for installation on the next Fusion restart.

**Request payload:** `{}`

**Response:** Standard envelope with `state` populated. On success, `response.state.updateInfo.updateState` will be `"staged"`. On failure it will be `"failed"` with `response.state.updateInfo.error` populated.

The download and extraction run synchronously in the action handler. No intermediate `renderState` pushes are emitted — the response arrives only after staging is complete.

---

---

### `syncMetadataJsonToFusion`

Write local JSON metadata (from disk) into Fusion document attributes. Repair direction: local → Fusion.

Use when local JSON is authoritative and Fusion attributes need to be overwritten.

**Request payload:** `{}`

**Response:** Standard envelope with `state` populated, plus `syncResult` and `debugMetadata` at top level:

```json
{
  "ok": true, "message": "",
  "state": { /* State Payload */ },
  "syncResult": {
    "direction": "json_to_fusion",
    "updatedCount": 3, "skippedCount": 12, "failedCount": 0,
    "failedNames": [], "failedDetails": []
  },
  "debugMetadata": { /* opaque */ }
}
```

#### `syncResult` fields for `syncMetadataJsonToFusion`

| Field | Type | Description |
|---|---|---|
| `direction` | `"json_to_fusion"` | Fixed label identifying the sync direction |
| `updatedCount` | `number` | Parameters whose Fusion attributes were updated |
| `skippedCount` | `number` | Parameters skipped (local JSON not newer than Fusion, or no local record) |
| `failedCount` | `number` | Parameters where writing to Fusion attributes failed |
| `failedNames` | `string[]` | Names of failed parameters (up to 20) |
| `failedDetails` | `object[]` | Per-parameter failure details (up to 10 entries). Each entry: `{ name, group, errors[], documentOwnerTypes[], parameterAttributeOk, metadataChangedAtAttributeOk, documentMapOk, documentItemOk }` |

---

### `syncMetadataFusionToJson`

Write Fusion document attribute metadata into local JSON files on disk. Repair direction: Fusion → local.

Use when Fusion attributes are authoritative and local JSON needs to be overwritten.

**Request payload:** `{}`

**Response:** Standard envelope with `state` populated, plus `syncResult` and `debugMetadata` at top level:

```json
{
  "syncResult": {
    "direction": "fusion_to_json",
    "updatedCount": 5,
    "skippedCount": 10
  }
}
```

#### `syncResult` fields for `syncMetadataFusionToJson`

| Field | Type | Description |
|---|---|---|
| `direction` | `"fusion_to_json"` | Fixed label |
| `updatedCount` | `number` | Parameters whose local JSON record was updated |
| `skippedCount` | `number` | Parameters skipped (Fusion not newer than local JSON) |

---

### `repairMetadata`

Auto-detect conflicts between local JSON and Fusion document attribute metadata and reconcile them using a newest-wins strategy (based on `metadataChangedAt` and `metadataRevision`). Updates both sides as needed.

**Request payload:** `{}`

**Response:** Standard envelope with `state` populated, plus `syncResult` and `debugMetadata` at top level:

```json
{
  "syncResult": {
    "direction": "repair",
    "updatedCount": 4,
    "updatedFusionCount": 2,
    "updatedJsonCount": 2,
    "skippedCount": 0,
    "healedCount": 1,
    "conflictCount": 0,
    "failedCount": 0,
    "failedNames": []
  }
}
```

#### `syncResult` fields for `repairMetadata`

| Field | Type | Description |
|---|---|---|
| `direction` | `"repair"` | Fixed label |
| `updatedCount` | `number` | Total parameters updated (sum of Fusion + JSON updates) |
| `updatedFusionCount` | `number` | Parameters where Fusion attributes were updated |
| `updatedJsonCount` | `number` | Parameters where local JSON was updated |
| `skippedCount` | `number` | Always `0` for repair (all parameters are inspected) |
| `healedCount` | `number` | Parameters where one side had no record and was populated from the other |
| `conflictCount` | `number` | Parameters where both sides claimed to be newer (resolved by revision number) |
| `failedCount` | `number` | Parameters where writing to Fusion failed |
| `failedNames` | `string[]` | Names of failed parameters (up to 20) |

---

### `getParameterDependencyGraph`

Return a dependency graph of all user parameters derived from their expression token references. Useful for FE visualizations (e.g. circular dependency warnings, impact analysis) and tooling.

**Request payload:** `{}`

**Response:** Read-only envelope (`state: null`) with `nodes` and `edges`:

```json
{
  "ok": true,
  "message": "",
  "state": null,
  "nodes": [
    { "name": "width", "expression": "10 mm" },
    { "name": "height", "expression": "width * 2" }
  ],
  "edges": [
    { "from": "height", "to": "width" }
  ]
}
```

#### Response fields

| Field | Type | Description |
|---|---|---|
| `nodes` | `object[]` | One entry per user parameter: `{name, expression}` |
| `edges` | `object[]` | One entry per detected reference: `{from: string, to: string}`. Only references to known parameters (user or model) are included. Self-references are excluded. |

**Notes:**
- `edges` is derived by tokenizing each expression with `EXPRESSION_TOKEN_PATTERN`. Only tokens matching known parameter names are included as edges.
- Graph structure does not use entity tokens — only names. Re-query after renames.
- Requires an open Fusion design; raises `NO_DESIGN` if none is active.

---

### `getBackendContractInfo`

Return stable metadata about this backend's API surface. Intended for FE feature detection and version compatibility checks.

**Request payload:** `{}`

**Response:** Read-only envelope (`state: null`):

```json
{
  "ok": true,
  "message": "",
  "state": null,
  "contractVersion": "2026-04-17",
  "bpmetaSchemaVersion": 1,
  "metadataSchemaVersion": 2,
  "actions": {
    "readOnly": ["ready", "refresh", "getBackendContractInfo", "..."],
    "mutating": ["createParameter", "updateParameter", "..."]
  }
}
```

#### Response fields

| Field | Type | Description |
|---|---|---|
| `contractVersion` | `string` | Date-stamp string identifying the contract revision |
| `bpmetaSchemaVersion` | `number` | Current supported `.bpmeta.json` schema version |
| `metadataSchemaVersion` | `number` | Current parameter metadata schema version |
| `actions.readOnly` | `string[]` | All actions that do not mutate the design |
| `actions.mutating` | `string[]` | All actions that may mutate the design |

**Notes:**
- No design required — can be called before or after opening a document.
- `actions` lists are exhaustive: every supported action appears in exactly one list.

---

### `seedTestParameters`

Create or update a batch of test-fixture parameters in the current design. All parameter names are automatically prefixed with `_bptest_` unless they already carry the prefix, preventing collisions with user parameters.

**Intended use:** Automated and manual in-Fusion testing only. Do not use in production UI flows.

**Request payload:**

```json
{
  "parameters": [
    { "name": "width",    "expression": "10 mm", "unit": "mm" },
    { "name": "height",   "expression": "_bptest_width * 2", "unit": "mm", "comment": "test param", "isFavorite": false },
    { "name": "MyGroup/depth", "expression": "5 mm", "unit": "mm", "group": "TestGroup" }
  ]
}
```

#### Request fields

| Field | Type | Required | Description |
|---|---|---|---|
| `parameters` | `object[]` | Yes | Seed records. Each must have `name`, `expression`, `unit`. |
| `parameters[].name` | `string` | Yes | Logical name. Will be prefixed with `_bptest_` if not already prefixed. |
| `parameters[].expression` | `string` | Yes | Valid Fusion expression string. |
| `parameters[].unit` | `string` | Yes | Unit string (may be `""` for unitless). |
| `parameters[].comment` | `string` | No | Parameter comment. |
| `parameters[].group` | `string` | No | Group name to assign. |
| `parameters[].isFavorite` | `boolean` | No | Favorite flag. Defaults to `false`. |

**Response:**

```json
{
  "ok": true,
  "message": "",
  "state": { "...": "Full State Payload on success, null on failure" },
  "seededCount": 3,
  "failedRows": []
}
```

#### Response fields

| Field | Type | Description |
|---|---|---|
| `seededCount` | `number` | Number of parameters successfully created or updated |
| `failedRows` | `object[]` | Per-row failures: `{row, name, message}` |

**Notes:**
- If the parameter already exists it is updated (expression, comment, isFavorite). Unit is set on create only.
- Partial success is possible: `ok: true` even if some rows failed. Check `failedRows`.
- Requires an open Fusion design.

---

### `resetTestState`

Delete all `_bptest_*` parameters from the current design and clear their associated metadata.

**Safety guard:** `confirm` must be exactly `"RESET"` (case-sensitive). Any other value returns an error without modifying the design.

**Intended use:** Automated and manual in-Fusion testing only.

**Request payload:**

```json
{ "confirm": "RESET" }
```

#### Request fields

| Field | Type | Required | Description |
|---|---|---|---|
| `confirm` | `string` | Yes | Must be exactly `"RESET"` to proceed. |

**Response:**

```json
{
  "ok": true,
  "message": "",
  "state": { "...": "Full State Payload" },
  "clearedCount": 3
}
```

#### Response fields

| Field | Type | Description |
|---|---|---|
| `clearedCount` | `number` | Number of `_bptest_*` parameters deleted |

**Notes:**
- Only parameters whose name starts with `_bptest_` are deleted. All other parameters are untouched.
- If `confirm` is missing or wrong, returns `ok: false` with `errorCode: VALIDATION_ERROR`.

---

### `runSelfTestSuite`

Execute the backend's built-in self-test suite inside the live Fusion process. Returns pass/fail results for each registered test. Requires an open Fusion design for tests that exercise Fusion API calls.

**Request payload:**

```json
{
  "filter": "smoke"
}
```

#### Request fields

| Field | Type | Required | Description |
|---|---|---|---|
| `filter` | `string` | No | If provided, only tests whose name contains this substring (case-insensitive) are run. Omit to run all tests. |

**Response:**

```json
{
  "ok": true,
  "message": "",
  "state": null,
  "totalCount": 5,
  "passedCount": 5,
  "failedCount": 0,
  "results": [
    { "name": "smoke/contract_info", "passed": true, "failures": [] },
    { "name": "smoke/validate_name", "passed": true, "failures": [] }
  ]
}
```

#### Response fields

| Field | Type | Description |
|---|---|---|
| `totalCount` | `number` | Number of tests that matched the filter and were executed |
| `passedCount` | `number` | Tests that passed |
| `failedCount` | `number` | Tests that failed |
| `results` | `object[]` | Per-test outcome: `{name: string, passed: boolean, failures: string[]}` |

**Built-in tests (smoke suite):**

| Test name | What it verifies |
|---|---|
| `smoke/contract_info` | `getBackendContractInfo` returns expected shape |
| `smoke/dependency_graph` | `getParameterDependencyGraph` returns `nodes`/`edges` lists |
| `smoke/dry_run_import_csv` | `dry_run=True` on CSV import does not mutate the design |
| `smoke/validate_name` | Name validator accepts valid names and rejects empty/digit-start |
| `smoke/bpmeta_parse` | Package parser accepts valid JSON and rejects invalid input |

**Notes:**
- `ok` is always `true` even if tests fail — test failures are reported in `results[].failures`, not via the envelope `ok` field.
- The response envelope `ok: false` indicates a runtime error running the suite (e.g., no design open when a design-dependent test runs).

---

## Python → JS Pushes

Python initiates these pushes independently of the request/response cycle.

### `renderState`

Pushed **only for unsolicited state changes** — not after JS-initiated actions.

**When pushed:**
- User activates a different Fusion document (document switch event)
- User opens the palette via the toolbar button (no JS initiator)

**When NOT pushed:** After any action sent via `fusionSendData`. Use the return value of `fusionSendData` instead.

**Payload:** Standard response envelope with `state` populated (same shape as a mutating action response):
```json
{ "ok": true, "message": "", "state": { /* State Payload */ } }
```

**Registration requirement:** JS must register `window.fusionReceiveData` before calling `ready`, or pushes that arrive before the handler is set will be silently lost.

```javascript
window.fusionReceiveData = function(action, dataString) {
  const response = JSON.parse(dataString);  // must parse manually
  if (action === "renderState" && response.state) {
    applyState(response.state);
  }
};
```

---

## Startup Sequence

The correct initialization order:

```javascript
// 1. Register the push handler FIRST, before anything else.
window.fusionReceiveData = function(action, dataString) {
  const data = JSON.parse(dataString);
  if (action === "renderState") applyState(data);
};

// 2. Send "ready" to bootstrap state.
(async function init() {
  const state = await window.adsk.fusionSendData("ready", JSON.stringify({}));
  applyState(state);
})();
```

After init:
- On every user action, send the appropriate action via `fusionSendData` and apply the returned state.
- Also handle incoming `renderState` pushes (triggered by document switches or other clients writing state).

---

## Error Handling

All actions return the standard envelope on failure:

```json
{
  "ok": false,
  "message": "A parameter named 'width' already exists.",
  "errorCode": "VALIDATION_ERROR",
  "traceback": "",
  "state": null
}
```

`message` is always a human-readable string suitable for display. `traceback` is populated for unexpected Python exceptions; empty for expected validation failures (duplicate name, invalid expression, etc.). Log `traceback` to the console for debugging; show `message` to the user.

`errorCode` is a stable string identifier for the error category. Use it for programmatic branching (e.g. suppress toast on cancel). Values:

| `errorCode` | Meaning |
|---|---|
| `VALIDATION_ERROR` | Input failed validation (invalid name, expression, unit, missing required field, etc.) |
| `CONFLICT_ERROR` | Name collision or other resource conflict |
| `NOT_FOUND` | Requested parameter or resource does not exist |
| `IO_ERROR` | File read/write failure |
| `DIALOG_CANCELLED` | User dismissed the OS file dialog without selecting a file |
| `TRANSPORT_ERROR` | Internal messaging failure |
| `CONTRACT_ERROR` | Unknown action name or API contract violation |
| `NO_DESIGN` | No Fusion design is currently active |
| `UNKNOWN_ERROR` | Unexpected exception not matched by any specific code |

**Notes:**
- `errorCode` is always present on `ok: false` responses, including uncaught exceptions.
- `DIALOG_CANCELLED` is not a user-facing error — do not show a toast or error state. Silently restore the prior UI state.
- `CONTRACT_ERROR` with action `"unknown"` means the FE sent an action name not recognized by the current backend. Check for backend version mismatch.

See the recommended `sendAction` handler in [Common Response Envelope](#common-response-envelope).

---

## Usage Patterns

### Auto-compute / Apply Queue Mode

This mode is implemented entirely in the FE. No dedicated BE action exists — all commits use existing actions.

**Auto mode (apply on Enter / blur):**
```javascript
// On Enter or blur, if expression is valid:
const response = await sendAction("updateParameter", { key: param.key, expression: dirtyExpression });
// response.state reflects the committed value — apply it.
```

**Manual mode — single row Apply:**
```javascript
const response = await sendAction("updateParameter", { key: param.key, expression: dirtyExpression });
```

**Manual mode — Apply All (sequential):**
```javascript
// Pre-validate all dirty rows first using validateExpression.
// Then apply in stable visible order:
for (const row of dirtyRows) {
  const response = await sendAction("updateParameter", { key: row.key, expression: row.dirtyExpression });
  if (response && response.state) {
    applyState(response.state);  // Apply state before next row — keeps expression previews current.
  }
  updateRowResult(row.key, response);  // Record per-row applied/failed status.
}
```

> **Critical:** Call `applyState(response.state)` after each `updateParameter` in the Apply All loop. Parameters can reference each other — a later row's expression may depend on an earlier row's just-committed value. Applying state between rows keeps Fusion's computed values current for any subsequent previews.

**Discard All / Discard row:** Reset local dirty state only. No BE call needed.

**Apply All hard-stop conditions** (abort entire batch, do not continue to next row):
- `response` is null or missing `ok` field (transport failure / malformed envelope)
- `response.state.apiVersion` does not match expected version

Normal `ok: false` row errors (invalid expression, parameter in use, etc.) do not stop the batch — mark the row failed and continue.

---

## Constraints and Edge Cases

### Threading

All Fusion API calls (`adsk.*`) execute on Fusion's main thread. The Python handler must never `await` or call async functions. Do not assume any concurrent execution.

### No document open

When Fusion has no active document:

- `parameters`, `groups`, `groupUi.order` → empty arrays
- `groupUi.collapsed` → empty object
- `parameterNames` → empty array
- `document.id`, `document.name` → both empty strings
- `documentDefaults.unit` → `"mm"` (default fallback)
- All parameter-mutating actions will return errors.

Design your UI to gracefully handle empty state and show an appropriate "no document" message.

### Entity tokens vs. names

- `key` (entity token) is the stable Fusion-internal identifier for a parameter. It persists across save/reload cycles for saved documents.
- `name` is human-readable but can be ambiguous if parameters are renamed outside the add-in.
- For all group and order operations, **always use `key`** (entity token) rather than `name`.
- For `updateParameter` and `setParameterFavorite`, `name` is the required identifier (no `key` variant). `setParameterFavorite` searches `design.allParameters` so it works on both user and model parameters.

### Group name conventions

- Empty string `""` is the canonical identifier for the Ungrouped pseudo-group in all API calls.
- `groups` in the State Payload never includes `""` — it only lists named groups.
- Ungrouped parameters have `group: ""` in their Parameter Object.
- The `saveGroupUiState.order` array should not include `""` — Ungrouped is always rendered last (or first, depending on UI convention) and its position is not configurable.

### Metadata revision tracking

Each Parameter Object includes `metadataChangedAt`, `metadataRevision`, `metadataWriterId`, and `metadataWriterVersion`. These are used by the backend for conflict detection when syncing between local JSON and Fusion document attributes. The UI does not need to read or write these — they are managed entirely by the Python backend.

### Text parameters

A parameter with `unit: "Text"` has its `expression` interpreted as a raw string, not a formula. `valuePreview` will be the literal text value. When creating or previewing text parameters, always pass `units: "Text"` to avoid Fusion interpreting the value as a numeric expression.

### `fusionTheme`

The `fusionTheme` field reflects Fusion's current application theme (`"light"` or `"dark"`). It defaults to `"light"` when the theme cannot be detected (e.g., older Fusion versions or preferences API unavailable). It is **never `null`**. Use it to sync the palette's visual theme to Fusion's application theme, or defer to `settings.theme` if the user has configured an independent preference.

### Column key names

The `parameterTableColumns` keys (`parameter`, `name`, `unit`, `expression`, `value`) match their display labels. See the [Column key mapping](#column-key-mapping) table for the full mapping. Pre-rename settings files (using old keys `name`, `expression`, `preview`, `comment`, `actions`) are migrated automatically on load.

---

## Migration Guide

### API version 1 — openHelpUrl addition (2026-04-16)

One new action added. Additive — no existing actions changed.

| New action | Type | Notes |
|---|---|---|
| `openHelpUrl` | Read-only (`state: null`) | Opens `url` in system browser via `webbrowser.open()`. `url` must start with `http://` or `https://`. |

**FE integration notes:**
- Add `openHelpUrl` to the normative action set and the read-only action set (no `applyState()` call needed).
- Call from the Info (i) help button with the Fusion Parameters reference URL.
- Treat `ok: false` as non-critical — show a snackbar/toast, do not block the palette.

---

### API version 1 — M4 export/import additions (2026-04-16)

Two new actions added. All additive — no existing actions changed.

| New action | Type | Notes |
|---|---|---|
| `exportParameters` | Read-only (`state: null`) | Writes CSV; opens native save dialog unless `filePath` provided. Extra fields: `exportedCount`, `filePath`. |
| `importParameters` | Mutating | Reads CSV; opens native open dialog unless `filePath` provided. Extra fields: `importedCount`, `skippedCount`, `failedCount`, `failedRows`. Partial success: `ok:true` with `failedCount>0` possible. |

**FE fixture updates required:**
- Add fixtures for both actions.
- `importParameters`: needs fixtures covering cancel (`ok:false`), all-success, partial-success (`ok:true, failedCount>0`), all-skipped (`ok:true, importedCount:0, skippedCount>0`), and all-failed (`ok:false, state:null`).
- `exportParameters`: `state` is always `null` — no `applyState()` call needed.
- `importParameters` with `ok:true`: `state` is always populated — route through `applyState()`.

---

### API version 1 — parity milestone additions (2026-04-16)

Six new actions added for M2/M3 parity milestone. All are additive — no existing actions changed.

| New action | Type | Notes |
|---|---|---|
| `deleteParameters` | Mutating (partial) | Batch delete. `ok: true` on partial success; extra fields `deletedCount`, `failedCount`, `failedDetails`. |
| `renameParameter` | Mutating | Direct rename via Fusion API. Entity token stable — no key update needed. |
| `copyParameter` | Mutating | Collision-safe copy. `targetName` optional (auto-generated). |
| `sortByTimelineOrder` | Mutating | Resets display order to Fusion creation order. |

> **Note:** `validateUnitChange` and `updateParameterUnit` were implemented in this milestone but have since been **removed from the normative API** before any UI fixtures were built. See the "contract revision" entry below. Do not add fixtures or dispatch calls for these actions.

**FE fixture updates required:**
- Add fixtures for the four normative new actions above.
- `deleteParameters`: fixture must cover full-success, partial-success (`ok:true, failedCount>0`), and all-failed (`ok:false, state:null`) cases.

---

### API version 1 — contract revision (2026-04-16, post-freeze)

These changes were agreed between frontend and backend before any UI fixtures were built. No migration code is required — update fixtures and remove calls to removed actions.

---

#### `validateUnitChange` and `updateParameterUnit` removed from normative API

**Change:** Both actions were implemented in the M2/M3 parity milestone but removed from the normative API before any FE fixtures were built. The implementations remain in the Python file as dormant code pending an Autodesk API change that exposes in-place unit mutation.

**Root cause:** `UserParameter.unit` is read-only in Fusion's Python API. The only available workaround is delete+recreate, which changes the entity token, destroys BP metadata, and is not equivalent to native Fusion behavior (which mutates unit in-place with token stability).

**Unblock condition:** Autodesk exposes in-place unit mutation in the Python API.

**Impact:** Do not add FE dispatch calls or fixtures for `validateUnitChange` or `updateParameterUnit`. The unit cell in the palette is display-only. Cross-unit expression literals (e.g. `5 ft` on a `mm` parameter) are valid — Fusion evaluates and converts automatically.

---

#### `getActiveDocumentInfo` removed

**Change:** Action removed from the normative API. Document identity (`id`, `name`) is present in every State Payload under `state.document`. There is no scenario where document identity is needed but a full state read is not acceptable.

**Impact:** Remove any calls to `getActiveDocumentInfo`. Read `state.document` from the most recent state instead.

---

#### `getMetadataDebugSnapshot` removed from normative API

**Change:** Action removed from the normative contract. It remains callable in the backend as an internal diagnostic escape hatch but has no stable response shape and is not a UI feature. No fixture should exist for it.

**Impact:** Remove any calls to `getMetadataDebugSnapshot` from UI code. If you need metadata diagnostic output, invoke it directly outside the UI layer.

---

#### `saveTextTunerState` now returns full State Payload

**Change:** `saveTextTunerState` was previously documented as read-only (`state: null`, with a top-level `values` field in the response). It is a genuine mutation — it writes to disk — and is now correctly classified as mutating. Response is now the standard full State Payload envelope. The saved text tuner state is reflected in `state.textTunerState`.

**Impact:** Breaking for any code that read `response.values` or expected `state: null`.

**Before:**
```json
{ "ok": true, "message": "", "state": null, "values": { "fontFamily": "...", "accentColor": "..." } }
```

**After:**
```json
{ "ok": true, "message": "", "state": { "apiVersion": 1, "textTunerState": { "fontFamily": "...", "accentColor": "..." }, "..." : "..." } }
```

**Migration:** Read saved text tuner values from `response.state.textTunerState`. Pass the response through the standard `applyState()` path — no special case needed.

---

### API version 1 — M6 metadata package export/import (2026-04-17)

Three new actions added for metadata-aware portable parameter transfer. All additive — no existing actions or response shapes changed.

| New action | Type | Notes |
|---|---|---|
| `exportParametersPackage` | Read-only (`state: null`) | Writes `.bpmeta.json` package. Extra fields: `exportedCount`, `filePath`, `format`. |
| `validateParametersPackageImport` | Read-only (`state: null`) | Preflight only, no mutations. Returns `filePath` (resolved from dialog if absent) and `preview` object. |
| `importParametersPackage` | Mutating | Apply package to destination document. Extra fields: `importedCount`, `updatedCount`, `skippedCount`, `failedCount`, `failedRows`. |

**FE integration notes:**
- Recommended two-step flow: call `validateParametersPackageImport` first (opens OS dialog, returns preview + resolved `filePath`), show summary to user, then call `importParametersPackage` with the resolved `filePath`.
- Direct single-step import (`importParametersPackage` without preflight) is supported — just omit `filePath` to get the dialog.
- `importParametersPackage` adds `updatedCount` (existing params changed) separate from `importedCount` (new params created). FE should display both.
- Cancel from OS dialog is silent on both actions — no error toast.
- For fixture coverage: validate needs cancel, success-with-no-warnings, success-with-warnings, and definite-fail-rows cases. Import needs cancel, all-created, all-updated, mixed, all-skipped, partial-fail, all-fail.

---

### API version 1 — model parameter stable component identity (2026-04-18c)

Additive field added to `ModelParameter` object. No removals. No breaking changes.

#### New field: `componentId`

| Field | Type | Notes |
|---|---|---|
| `componentId` | `string` | `Component.entityToken` for the owning component. Stable across renames. Empty string when unavailable. |

#### Rationale

`componentName` is a display label — it changes on component rename. FE group-order persistence keyed on `componentName` breaks silently after any rename. `componentId` provides a rename-stable identity so FE can persist and reconcile component group order across sessions.

#### Identity guarantee

- Source: `Component.entityToken` (Fusion's own stable persistent token).
- Stable across: component renames, parameter refreshes, within a design session.
- Not guaranteed across: design close/reopen (entityTokens are session-scoped in Fusion). FE should treat a missing match on reload as a new component and append it — preserve+append drift handling, not hard failure.
- Empty string: returned when token is inaccessible (exception from Fusion API). Never fabricated.

#### FE usage

- Key persistent group-order state on `componentId` when non-empty.
- Fall back to `componentName`-keyed (non-persistent) behavior when `componentId` is empty string.
- On state reconciliation: matched by `componentId` → update display name from current `componentName`. Unmatched stored id → treat as removed. New id not in store → append at end.

---

### API version 1 — model parameter all-components scope (2026-04-18b)

`getModelParameters` previously returned parameters from the root component only. Root component contains no geometry in best-practice designs — all params live in sub-components. This was a silent data loss bug: `totalCount` returned 0 in well-structured designs.

#### Changes

- `_model_parameter_count()` now sums `modelParameters.count` across all components via `design.allComponents`.
- `_get_model_parameters()` now collects from all components. Sort order changed: **component name ascending, then parameter name ascending** (both case-insensitive). Previously: parameter name only.
- `ModelParameter` object gains **`componentName: string`** field — display name of the owning component. Empty string for root component parameters.
- `updateModelParameter` name-fallback lookup now searches all components (token path was already global).

**Migration:** `componentName` is a new field — no removal. FE may display it as a grouping label or secondary text. No breaking change to existing field reads. Sort order change only affects display ordering.

---

### API version 1 — model parameter on-demand loading (2026-04-18)

**Breaking change** to the M5 model parameter contract. `modelParameters` array removed from State Payload; replaced by `modelParameterCount` integer. New `getModelParameters` paginated action added.

#### Rationale

Model parameter counts can reach tens of thousands to low hundreds of thousands in complex designs. Including the full serialized array in every state envelope was untenable at that scale — multi-megabyte responses per action, O(N) Python serialization on every mutation.

#### State payload change

`modelParameters: ModelParameter[]` **removed**. `modelParameterCount: number` **added**.

| Removed field | Replacement |
|---|---|
| `modelParameters` | `modelParameterCount` (integer, O(1) read) |

**Migration:** Remove any `applyState()` path that reads `state.modelParameters`. Replace with a `getModelParameters` call triggered on section expand or initial load.

#### New action

| New action | Type | Notes |
|---|---|---|
| `getModelParameters` | Read-only | Paginated + filterable model parameter fetch. `offset`, `limit`, `filter`. Returns `totalCount`, `parameters[]`, echoed `offset`/`limit`. |

**FE integration:**
- On state push: read `modelParameterCount` to show section header count and decide whether to auto-expand.
- On section expand: call `getModelParameters({ offset: 0, limit: 200 })`.
- On scroll: call with updated `offset` (virtual scroll).
- On search: call with `filter` string; reset `offset: 0`.
- After `updateModelParameter` success: re-fetch current page.
- `expression` and `comment` still writable via `updateModelParameter`.
- `name`, `unit`, `isDeletable` read-only.

---

### API version 1 — M5 model parameter support (2026-04-17)

One new action added. Superseded by the 2026-04-18 entry above — `modelParameters` state field was introduced here and then removed in the follow-up breaking change. The `updateModelParameter` action and `ModelParameter` object shape are unchanged.

#### New action (still current)

| Action | Type | Notes |
|---|---|---|
| `updateModelParameter` | Mutating | Update `expression` and/or `comment` on a root component model parameter. Returns full State Payload. |

---

### Pre-apiVersion → API version 1 (2026-04-16)

These changes were made to the backend on 2026-04-16. If you have an existing UI built before this date, review each item.

---

#### `apiVersion` field added to State Payload

**Change:** `_current_state_payload()` now includes `"apiVersion": 1` in every state response.

**Impact:** Additive — no existing code breaks. Old payloads did not include this field.

**Recommended update:** Add a version guard on startup:

```javascript
function applyState(state) {
  if (state.apiVersion !== 1) {
    console.warn(`Unexpected API version: ${state.apiVersion}. UI may be out of sync.`);
  }
  // ... rest of apply logic
}
```

---

#### `fusionTheme` is no longer nullable

**Change:** `_detect_fusion_theme()` previously returned `None` (serialized as JSON `null`) when Fusion's preferences API was unavailable. It now always returns `"light"` or `"dark"`.

**Impact:** Any null-guard code in the UI is now dead code. It will not cause errors but can be removed.

**Before:**
```javascript
const theme = state.fusionTheme ?? "light";  // null-coalescing was necessary
```

**After:**
```javascript
const theme = state.fusionTheme;  // always "light" or "dark"
```

---

#### `validateExpression` — `isIncomplete` always present

**Change:** The `isIncomplete` field is now included on **all** `validateExpression` responses, including success and all error cases. Previously it was only present when `true`.

**Impact:** Code that checked `response.isIncomplete` previously received `undefined` (falsy) on success and most error paths. It now receives `false` (explicitly falsy). Behaviorally identical for `if (response.isIncomplete)` checks — no code breaks.

**Benefit:** You can now safely use strict equality:

```javascript
// Previously fragile (undefined vs false):
if (response.isIncomplete === true) { ... }

// Now safe — isIncomplete is always a boolean:
if (response.isIncomplete) { ... }
```

---

#### `parameterTableColumns` keys renamed

**Change:** The five `parameterTableColumns` keys were renamed to match their display labels:

| Old key | New key | Display column |
|---|---|---|
| `name` | `parameter` | Parameter (Fusion identifier) |
| `expression` | `name` | Name / label |
| `preview` | `unit` | Unit |
| `comment` | `expression` | Expression / formula |
| `actions` | `value` | Value |

**Impact:** **Breaking change** for any code that reads or writes specific column keys by name.

**Migration — automatic for persisted settings:** Both `_load_settings()` (Python) and `migrateColumnWidths()` (JS) transparently upgrade stored JSON files that contain old key names. No manual file editing required. On first load after the update, old keys are read and saved under new names.

**Migration — UI code that reads column widths:**

```javascript
// Before:
const nameColWidth = settings.parameterTableColumns.name;
const expressionColWidth = settings.parameterTableColumns.expression;

// After:
const parameterColWidth = settings.parameterTableColumns.parameter;
const nameColWidth = settings.parameterTableColumns.name;
```

**Migration — `saveSettings` calls with column widths:**

```javascript
// Before:
await sendAction("saveSettings", {
  parameterTableColumns: { name: 160, expression: 200, preview: 90, comment: 240, actions: 130 }
});

// After:
await sendAction("saveSettings", {
  parameterTableColumns: { parameter: 160, name: 200, unit: 90, expression: 240, value: 130 }
});
```

---

#### Uniform response envelope introduced

**Change:** All responses now share the same three-field envelope: `{ ok, message, state }`. Previously, mutating actions returned the State Payload as a bare top-level object; read-only actions returned smaller ad-hoc shapes; error responses had no `state` field.

Specific changes per response type:

| Response type | Before | After |
|---|---|---|
| Mutating success | `{ ok: true, parameters: [...], ... }` (State Payload at root) | `{ ok: true, message: "", state: { parameters: [...], ... } }` |
| Read-only success | `{ ok: true, values: {...} }` (no `message`, no `state`) | `{ ok: true, message: "", state: null, values: {...} }` |
| Validation success | `{ ok: true, message: "" }` (no `state`) | `{ ok: true, message: "", state: null }` |
| Error | `{ ok: false, message: "...", traceback: "..." }` (no `state`) | `{ ok: false, message: "...", traceback: "...", state: null }` |
| `renderState` push | Bare State Payload | `{ ok: true, message: "", state: { /* State Payload */ } }` |

**Impact:** **Breaking change** for all existing UI code. Every call site that reads the response must be updated.

**Migration — action responses:**

```javascript
// Before: state was the root object
async function sendAction(action, payload) {
  const result = await window.adsk.fusionSendData(action, JSON.stringify(payload));
  if (!result.ok) { showError(result.message); return; }
  applyState(result);         // result IS the state
  return result.someField;    // action-specific fields at root
}

// After: state is nested under result.state
async function sendAction(action, payload) {
  const result = await window.adsk.fusionSendData(action, JSON.stringify(payload));
  if (!result.ok) { showError(result.message); return; }  // same
  if (result.state) applyState(result.state);  // unwrap
  return result.someField;                     // action-specific fields still at root
}
```

**Migration — `fusionReceiveData` push handler:**

```javascript
// Before:
window.fusionReceiveData = function(action, dataString) {
  const data = JSON.parse(dataString);
  if (action === "renderState") applyState(data);  // data IS the state
};

// After:
window.fusionReceiveData = function(action, dataString) {
  const data = JSON.parse(dataString);
  if (action === "renderState" && data.state) applyState(data.state);  // unwrap
};
```

**Migration — sync/repair metadata extra fields:**

```javascript
// Before: syncResult and debugMetadata were injected into the state payload root
const result = await sendAction("syncMetadataJsonToFusion", {});
const syncResult = result.syncResult;      // was at root

// After: they remain at the response root, alongside state
const result = await sendAction("syncMetadataJsonToFusion", {});
const syncResult = result.syncResult;      // still at root — no change here
// but result.parameters etc. is now at result.state.parameters
```

---

#### Dual delivery removed — actions no longer push `renderState`

**Change:** Previously, every mutating action both returned the State Payload via `fusionSendData` AND pushed an identical `renderState` event via `fusionReceiveData`. The push from action handlers has been removed. Actions now only return the payload. `renderState` is pushed exclusively for unsolicited events (document switch, palette opened by toolbar button).

**Impact:** Any UI that ignored the `fusionSendData` return value and relied solely on `fusionReceiveData` to receive state after actions will stop updating. This is a **breaking change** for that pattern.

**Recommended update:** Ensure every action call applies state from the return value:

```javascript
// Before (broken if relying only on fusionReceiveData push):
await window.adsk.fusionSendData("updateParameter", JSON.stringify(payload));
// ... state arrived via fusionReceiveData — no longer works

// After (correct):
const state = await window.adsk.fusionSendData("updateParameter", JSON.stringify(payload));
applyState(state);
```

Keep `fusionReceiveData` registered to handle document-switch pushes — just don't rely on it for action responses.

---

#### `saveParameterOrder` now supports per-group reorder

**Change:** `saveParameterOrder` now accepts an optional `group` field. When present, only parameters within that group are reordered; all other groups are unaffected. Without `group`, the original flat global-list behavior is unchanged.

**Impact:** Non-breaking — existing calls without `group` continue to work identically.

**Recommended update:** Prefer per-group mode for drag-reorder interactions to avoid sending the full parameter list on every drop:

```javascript
// Before (global flat list — still works but sends all tokens):
await sendAction("saveParameterOrder", { keys: allParameterTokensInOrder });

// After (preferred for single-group reorder):
await sendAction("saveParameterOrder", {
  group: "Dimensions",
  keys: dimensionGroupTokensInNewOrder
});
```

---

#### `updateParameter` now accepts `key` (entity token)

**Change:** `updateParameter` previously required `name` as the only parameter identifier. It now accepts `key` (entity token) with `name` as fallback. Resolution order: `key` first, `name` if key is absent or does not resolve.

**Impact:** Non-breaking — existing calls that only supply `name` continue to work. No code changes required for existing UIs.

**Recommended update:** Prefer `key` over `name` in new code to survive external renames:

```javascript
// Before (still works):
await sendAction("updateParameter", { name: "width", expression: "15 mm" });

// After (preferred — survives external renames):
await sendAction("updateParameter", { key: param.key, name: param.name, expression: "15 mm" });
```

---

#### `deleteParameter` action added

**Change:** New action `deleteParameter` permanently removes a user parameter from the Fusion design. Accepts `key` (preferred) or `name`. Returns Full State Payload on success.

**Impact:** Additive — no existing code breaks.

**Usage:**
```javascript
await sendAction("deleteParameter", { key: param.key });
```

Note: Fusion will reject deletion if the parameter is referenced in model features or other parameter expressions.

---

#### `savePaletteGeometry` action added

**Change:** New action `savePaletteGeometry` persists only `paletteSize`, `palettePosition`, and `paletteDockingState`. Functionally equivalent to calling `saveSettings` with only those three fields, but semantically scoped to window chrome.

**Impact:** Additive — no existing code breaks. Existing calls to `saveSettings` with geometry fields continue to work.

**Recommended update:** Switch resize/drag handlers from `saveSettings` to `savePaletteGeometry` to avoid accidentally overwriting unrelated settings:

```javascript
// Before:
await sendAction("saveSettings", { paletteSize: { width: 600, height: 720 } });

// After:
await sendAction("savePaletteGeometry", { paletteSize: { width: 600, height: 720 } });
```

---

#### `ready` and `refresh` are now aliases

**Change:** The `"ready"` and `"refresh"` action handlers were separate code paths that happened to do the same thing. They are now a single handler (`if action in ("ready", "refresh")`).

**Impact:** None — behavior is identical. Both actions still work and return the same payload.

**No code changes required.**

---

### API version 1 — M7 test infrastructure and contract (2026-04-17)

Seven additions:

| New action | Type | Notes |
|---|---|---|
| `getParameterDependencyGraph` | Read-only (`state: null`) | Returns `nodes`/`edges` for all user parameters. |
| `getBackendContractInfo` | Read-only (`state: null`) | Returns `contractVersion`, schema versions, and full `actions` lists. |
| `seedTestParameters` | Mutating | Create/update `_bptest_*` parameters. Testing use only. |
| `resetTestState` | Mutating | Delete all `_bptest_*` parameters. Requires `confirm: "RESET"`. |
| `runSelfTestSuite` | Read-only (`state: null`) | Execute built-in smoke tests in live Fusion process. |
| `importParameters` + `dryRun` | Mutating (dry) | `dryRun: true` runs validation/decision logic without mutations. |
| `importParametersPackage` + `dryRun` | Mutating (dry) | Same. |

**Error taxonomy additions:**

All `ok: false` responses now include an `errorCode` field with a stable string identifier. See [Error Handling](#error-handling) for the full code table.

**FE integration notes:**
- `getBackendContractInfo` can be called at any time — no design required.
- `getParameterDependencyGraph` requires an active design.
- `seedTestParameters` / `resetTestState` / `runSelfTestSuite`: only call from dev/test tooling. Do not expose in production palette UI.
- `dryRun: true` on `importParameters` / `importParametersPackage`: response includes `dryRun: true` field. `state` is always `null` when `dryRun: true`. Use counts from dry-run response to build a confirmation UI before committing.
- `runSelfTestSuite` `ok` field: always `true` even if individual tests fail. Test failures appear in `results[].failures`. `ok: false` means a runtime error in the suite itself.
