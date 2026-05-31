# BetterParameters Metadata Parameter Implementation Spec

Purpose: replace scattered BP metadata persistence with one portable Fusion user
parameter comment payload, optimized for low Fusion writes, portability, and
large-doc reliability.

This spec is implementation guidance for the real BP codebase. It is not user
documentation.

## Goals

- Persist durable BP document metadata inside the Fusion file.
- Keep Fusion writes minimal: routine reads write nothing; explicit metadata
  edits write one metadata parameter comment.
- Make metadata portable across computers and Fusion cloud documents.
- Avoid per-parameter attribute write fanout and undo-stack pollution.
- Keep local JSON as cache/transient state only.
- Use compact binary-safe encoding for speed/size; human readability is not a
  requirement.

## Non-Goals

- Do not fix BP table rendering performance in this change.
- Do not delete existing legacy attributes during normal migration.
- Do not make local JSON automatically override Fusion document metadata.
- Do not store transient revert history in the Fusion metadata parameter unless
  separately approved.

## Storage Object

Create and maintain one reserved Fusion user parameter:

- Name: `_bp_metadata_v1`
- Expression: `0`
- Unit: empty/unitless
- Comment: encoded metadata payload
- Favorite: false, best effort

BP must hide this parameter from the BP normal parameter table and block edits to
it through BP workflows.

The native Fusion parameter window will still show it. Testing indicates one
metadata parameter is acceptable; large comments can affect native parameter
window responsiveness, so payload size still matters.

## Comment Wire Format

Writer emits only:

```text
BPM1Z:<sha256-hex-of-canonical-json>:<base64-zlib-canonical-json>
```

Reader supports:

1. `BPM1Z:<hash>:<base64>` current format.
2. Plain JSON object, dev/migration fallback only.
3. Missing/invalid payload as recoverable metadata-missing/corrupt state.

Use Python stdlib only:

```python
import base64
import hashlib
import json
import zlib
```

Canonical JSON:

```python
json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
```

Compression:

```python
compressed = zlib.compress(raw_json.encode("utf-8"), level=6)
encoded = base64.b64encode(compressed).decode("ascii")
comment = f"BPM1Z:{hash_hex}:{encoded}"
```

Decode:

- split exact prefix and separators
- base64 decode with validation when possible
- zlib decompress
- UTF-8 decode
- SHA-256 raw JSON and compare to header hash
- JSON parse
- validate schema

On any failure, return structured error and do not overwrite silently.

## Canonical Payload Shape

Use compact array/dictionary structure:

```json
{
  "s": 1,
  "r": 42,
  "t": 1780170000000,
  "w": "writer-id",
  "wv": "0.9.8",
  "g": ["Dimensions", "Motion"],
  "go": ["u:dimensions", "u:motion"],
  "gc": ["u:motion"],
  "p": [
    ["entityTokenA", 0],
    ["entityTokenB", 1],
    ["entityTokenC", -1]
  ]
}
```

Fields:

- `s`: schema version, integer. Start at `1`.
- `r`: document metadata revision, monotonic integer.
- `t`: changed-at timestamp in milliseconds.
- `w`: install writer id, string.
- `wv`: writer add-in version, string.
- `g`: group table, array of normalized group names. Empty group is not stored.
- `go`: group UI order, array of group ids. Optional; omit if empty.
- `gc`: collapsed group ids, array. Optional; omit if empty.
- `p`: parameter records in display order.

Parameter record:

```json
["entityToken", groupIndex]
```

- order is the array position in `p`
- `groupIndex >= 0` indexes `g`
- `groupIndex == -1` or missing means ungrouped
- future row form may add third element for flags, but v1 should only write two
  elements

No per-row timestamp/revision. Document-level `r/t/w/wv` are enough.

## In-Memory Domain Model

Introduce a small internal model independent of current local JSON shape:

```python
{
  "schema": 1,
  "revision": int,
  "changedAt": int,
  "writerId": str,
  "writerVersion": str,
  "groupsByToken": {token: group_name},
  "orderedTokens": [token],
  "groupUi": {
    "order": [group_id],
    "collapsed": {group_id: bool}
  }
}
```

Conversion functions:

- `_metadata_model_from_payload(payload) -> model`
- `_payload_from_metadata_model(model) -> payload`
- `_metadata_model_from_current_sources(design, local_state) -> model`

Keep normalization centralized:

- group name normalization uses existing `_normalize_group_name`
- group id normalization should align with FE ids: `u:<lowercase-group-name>`
- ungrouped is empty string in model and `-1` in payload

## Authority Rules

Fusion metadata parameter is durable portable authority.

Local JSON is cache/transient state:

- parameter order cache
- previous expression/value revert history
- local display cache
- debug/capture state
- fast startup cache

Routine state reads:

1. read metadata parameter payload
2. if valid and newer/different than local durable cache, seed/update local JSON
3. build UI state from live Fusion parameters + metadata model
4. write local JSON cache only if needed
5. never write Fusion

Explicit BP metadata edits:

1. load current metadata model from Fusion metadata parameter
2. apply edit in memory
3. increment document metadata revision
4. write one metadata parameter comment
5. read back and verify exact comment/hash
6. update local JSON cache
7. return refreshed or incremental state

Local JSON must not win automatically over valid Fusion metadata on open/refresh.
Use explicit repair commands for JSON -> Fusion.

## Actions That Write Metadata Parameter

These should write one metadata comment per user-visible operation:

- `setParameterGroup`
- `renameGroup`
- `deleteGroup`
- `saveParameterOrder`
- `saveGroupUiState`
- import package when applying groups/order/group UI
- copy parameter when copying source group/order
- any future group/order metadata action

These should not write metadata parameter:

- `ready`
- `refresh`
- document activation refresh
- command terminated refresh
- live parameter expression/name/comment/favorite updates unless they also
  intentionally change BP metadata
- routine `_collect_user_parameters`
- routine local snapshot persistence

## Metadata Parameter Lifecycle

### On Read

Find `_bp_metadata_v1` by name in `design.userParameters`.

If missing:

- return metadata-missing status
- do not auto-create during routine read unless no legacy/local metadata exists
  and BP needs an empty model for display

### On First Explicit Metadata Write

If `_bp_metadata_v1` missing:

- create it with expression `0`, unit `""`, initial comment empty
- best-effort set `isFavorite = False`
- then write encoded payload

Creation is a Fusion write and will create undo entry. This happens once per
document.

### Hiding

Backend `_collect_user_parameters()` must skip `_bp_metadata_v1`.

Actions that accept parameter name/key must reject `_bp_metadata_v1` with a clear
error unless the action is internal metadata maintenance.

## Migration

On first startup after implementation:

1. Try read `_bp_metadata_v1`.
2. If valid, use it as authority.
3. If missing:
   - build candidate metadata model from existing legacy sources:
     - current per-parameter attrs
     - current document metadata map/item attrs
     - current local JSON document order state
   - choose best candidate conservatively:
     - prefer valid Fusion-embedded attrs over local JSON for portability
     - use local JSON only when Fusion embedded metadata is empty/missing
   - do not write during routine read
4. On first explicit metadata edit or explicit migration command, write
   `_bp_metadata_v1`.

Add explicit debug/action command:

- `migrateMetadataToParameter`

It should:

- build model from current best sources
- write `_bp_metadata_v1`
- report counts/source decisions/conflicts

Legacy attrs:

- leave untouched
- stop maintaining in normal writes
- keep old sync/repair/debug functions behind Debug Hub only if still useful

## Conflict/Corruption Handling

Cases:

- missing metadata param
- empty comment
- unsupported prefix
- bad base64/zlib
- hash mismatch
- invalid JSON/schema
- token in payload not found in design
- token duplicate
- payload references group index out of range

Required behavior:

- Do not silently overwrite a corrupt existing metadata parameter.
- Surface warning in state payload/debug metadata.
- Build display using best safe fallback:
  - valid subset of payload if possible
  - local JSON cache if payload unreadable and local cache exists
  - default ungrouped/order-by-Fusion if no safe metadata
- Provide explicit repair choice:
  - rebuild from live/local cache and overwrite metadata parameter
  - export corrupt raw comment for diagnostics
  - ignore BP metadata for this document

## Size Limits

Probe lessons:

- One visible metadata parameter is acceptable.
- 1M/2M comments make native Fusion parameter window unhappy/stally.
- 256K causes some stutter in native window.
- 64K is tolerable.
- 4K feels normal.
- 4M/8M are not reliable and must not be used.

Implementation limits:

- soft warning if encoded comment length exceeds `64 * 1024`
- stronger warning if exceeds `128 * 1024`
- default hard fail if exceeds `256 * 1024`
- no production override above 256K unless debug flag is explicitly enabled

Because zlib should dramatically reduce compact array payloads, normal payloads
should remain far below these limits.

## Local JSON Changes

Current local `document_orders/*.json` can stay, but semantics must change:

- durable group/order metadata from Fusion parameter seeds local cache
- local cache should not carry authoritative metadata revision for groups/order
- previous expression/value remains local-only
- routine refresh may update local current expression/value/order cache without
  modifying Fusion metadata parameter

Recommended new local structure:

```json
{
  "documentId": "...",
  "documentName": "...",
  "metadataCache": {
    "sourceRevision": 42,
    "sourceHash": "...",
    "updatedAt": 1780170000000
  },
  "parameters": {
    "token": {
      "order": 0,
      "name": "width",
      "current_expression": "10 mm",
      "previous_expression": "8 mm",
      "current_value": "10 mm",
      "previous_value": "8 mm"
    }
  }
}
```

Groups/order can be cached for speed, but should be considered derived from
metadata parameter unless explicitly edited locally and then successfully written
back to metadata parameter.

## Backend Refactor Outline

Add helpers near metadata section:

- `_metadata_parameter_name()`
- `_find_metadata_parameter(design)`
- `_ensure_metadata_parameter(design)`
- `_encode_metadata_comment(payload)`
- `_decode_metadata_comment(comment)`
- `_read_metadata_parameter_payload(design)`
- `_write_metadata_parameter_payload(design, model)`
- `_metadata_model_from_payload(payload)`
- `_payload_from_metadata_model(model)`
- `_metadata_model_from_legacy_sources(design, order_state)`
- `_metadata_model_for_current_document(design, order_state, allow_legacy=True)`
- `_apply_metadata_model_to_local_cache(model, order_state)`

Then modify:

- `_collect_user_parameters`
  - skip `_bp_metadata_v1`
  - use metadata model for group/order display
  - do not call any Fusion metadata writes
- `_collect_parameter_groups`
  - unchanged except it sees metadata-derived groups
- `_set_parameter_group`
  - update metadata model + one metadata comment write + local cache
- `_rename_group`
  - batch model update + one write
- `_delete_group`
  - batch model update + one write
- `_save_parameter_order`
  - update ordered token list + one write
- `_save_group_ui_state`
  - update group UI fields + one write
- `_copy_parameter`
  - create real param, then update model for new token + one write

Do not remove old helpers immediately; fence old attr writers away from normal
paths first.

## Frontend Contract

State payload can remain mostly unchanged:

- `parameters[].group` still string
- `groups` still list
- `groupUi` still object
- `metadataChangedAt`/`metadataRevision` may become document-level or deprecated

Add optional diagnostics:

```json
"metadataStatus": {
  "source": "metadataParameter|legacyFusion|localJson|none",
  "ok": true,
  "revision": 42,
  "encodedSize": 12345,
  "warning": ""
}
```

FE should not need to parse metadata parameter payload.

## Tests

Backend tests:

- encode/decode round trip
- hash mismatch rejection
- corrupted base64/zlib rejection
- compact payload <-> model conversion
- missing metadata param returns safe empty model
- metadata param is hidden from `_collect_user_parameters`
- `refresh` does not write/create metadata parameter
- `setParameterGroup` writes exactly one metadata parameter comment after initial
  creation exists
- `renameGroup`/`deleteGroup` write once for many params
- `saveParameterOrder` writes once
- local JSON cannot override valid metadata parameter during routine read
- migration from legacy attrs/local JSON builds expected model
- oversized encoded comment fails with clear error

Fusion harness/manual validation:

- create groups/order in BP, save, close/reopen, BP state persists
- open same doc on second machine/profile if possible, BP state persists
- native Fusion Parameter dialog remains tolerable with realistic large payload
- undo stack for group assignment/order has minimal entries compared to current
- corrupt `_bp_metadata_v1.comment`, confirm BP warns and does not overwrite
  silently

## Rollout Plan

1. Implement encode/decode/model helpers and tests.
2. Add read path while keeping old writers.
3. Hide/reserve `_bp_metadata_v1`.
4. Route explicit group/order writes to metadata parameter.
5. Stop normal legacy attr writes.
6. Add migration/debug actions.
7. Run full pytest.
8. Sync live add-in.
9. Fusion validate:
   - group assign/rename/delete/order
   - save/close/reopen
   - second profile/machine if available
   - undo stack
   - Debug Hub metadata status

## Key Risks

- Metadata parameter creation/comment write still creates undo entries.
- Metadata parameter can be manually edited/deleted in native Fusion UI.
- Entity token stability must remain acceptable across save/reopen/cloud open.
- Very large documents may still exceed safe comment size after compression.
- Existing FE duplicate `applyState` issue may obscure refresh testing and should
  be fixed separately.
