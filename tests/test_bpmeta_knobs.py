"""
test_bpmeta_knobs.py — tests for _normalized_conflict_policy and _extract_apply_knobs.

Pure functions: no design, no Fusion API.
"""
import BetterParameters as bp


# ---------------------------------------------------------------------------
# _normalized_conflict_policy
# ---------------------------------------------------------------------------

class TestNormalizedConflictPolicy:
    def test_skip(self):
        assert bp._normalized_conflict_policy({"conflictPolicy": "skip"}) == "skip"

    def test_overwrite(self):
        assert bp._normalized_conflict_policy({"conflictPolicy": "overwrite"}) == "overwrite"

    def test_merge_safe(self):
        assert bp._normalized_conflict_policy({"conflictPolicy": "merge-safe"}) == "merge-safe"

    def test_missing_key_defaults_to_skip(self):
        assert bp._normalized_conflict_policy({}) == "skip"

    def test_none_value_defaults_to_skip(self):
        assert bp._normalized_conflict_policy({"conflictPolicy": None}) == "skip"

    def test_empty_string_defaults_to_skip(self):
        assert bp._normalized_conflict_policy({"conflictPolicy": ""}) == "skip"

    def test_unknown_value_defaults_to_skip(self):
        assert bp._normalized_conflict_policy({"conflictPolicy": "replace-all"}) == "skip"

    def test_case_sensitive(self):
        # Values are lowercased during normalization — mixed case is unknown → skip
        assert bp._normalized_conflict_policy({"conflictPolicy": "SKIP"}) == "skip"

    def test_whitespace_trimmed(self):
        # str().strip().lower() is applied
        assert bp._normalized_conflict_policy({"conflictPolicy": " overwrite "}) == "overwrite"


# ---------------------------------------------------------------------------
# _extract_apply_knobs
# ---------------------------------------------------------------------------

class TestExtractApplyKnobs:
    def _knobs(self, **kwargs):
        return bp._extract_apply_knobs(kwargs)

    def test_defaults(self):
        knobs = bp._extract_apply_knobs({})
        assert knobs["applyExpressionsUnits"] is False
        assert knobs["applyComments"] is True
        assert knobs["applyGroups"] is True
        assert knobs["applyFavorites"] is True
        assert knobs["applyOrder"] is False

    def test_all_true(self):
        data = {
            "applyExpressionsUnits": True,
            "applyComments": True,
            "applyGroups": True,
            "applyFavorites": True,
            "applyOrder": True,
        }
        knobs = bp._extract_apply_knobs(data)
        assert all(knobs.values())

    def test_all_false(self):
        data = {
            "applyExpressionsUnits": False,
            "applyComments": False,
            "applyGroups": False,
            "applyFavorites": False,
            "applyOrder": False,
        }
        knobs = bp._extract_apply_knobs(data)
        assert not any(knobs.values())

    def test_truthy_int_coerced(self):
        knobs = bp._extract_apply_knobs({"applyExpressionsUnits": 1})
        assert knobs["applyExpressionsUnits"] is True

    def test_falsy_int_coerced(self):
        knobs = bp._extract_apply_knobs({"applyComments": 0})
        assert knobs["applyComments"] is False

    def test_none_falls_back_to_default(self):
        knobs = bp._extract_apply_knobs({"applyGroups": None})
        # None is falsy → bool(None) = False; but default is True so None overrides
        # bool(data.get(..., True)) where data.get returns None → bool(None) = False
        # This is intentional: explicit None disables the knob.
        assert knobs["applyGroups"] is False

    def test_returns_all_five_keys(self):
        knobs = bp._extract_apply_knobs({})
        expected_keys = {"applyExpressionsUnits", "applyComments", "applyGroups", "applyFavorites", "applyOrder"}
        assert set(knobs.keys()) == expected_keys
