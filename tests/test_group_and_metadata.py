"""
test_group_and_metadata.py — tests for _normalize_group_name and metadata value normalizers.

Pure functions: no design, no Fusion API.
"""
import pytest
import BetterParameters as bp


# ---------------------------------------------------------------------------
# _normalize_group_name
# ---------------------------------------------------------------------------

class TestNormalizeGroupName:
    def test_empty_string_returns_empty(self):
        assert bp._normalize_group_name("") == ""

    def test_none_returns_empty(self):
        assert bp._normalize_group_name(None) == ""

    def test_whitespace_only_returns_empty(self):
        assert bp._normalize_group_name("   ") == ""

    def test_ungrouped_label_returns_empty(self):
        assert bp._normalize_group_name("Ungrouped") == ""

    def test_ungrouped_case_insensitive(self):
        assert bp._normalize_group_name("UNGROUPED") == ""
        assert bp._normalize_group_name("ungrouped") == ""
        assert bp._normalize_group_name("UnGrOuPeD") == ""

    def test_normal_name_passes_through(self):
        assert bp._normalize_group_name("Dimensions") == "Dimensions"

    def test_leading_trailing_whitespace_stripped(self):
        assert bp._normalize_group_name("  Dims  ") == "Dims"

    def test_internal_whitespace_collapsed(self):
        assert bp._normalize_group_name("Dim  1") == "Dim 1"
        assert bp._normalize_group_name("A\tB") == "A B"

    def test_name_at_max_length_preserved(self):
        name = "A" * bp.MAX_GROUP_NAME_LENGTH
        assert bp._normalize_group_name(name) == name

    def test_name_over_max_length_truncated(self):
        name = "A" * (bp.MAX_GROUP_NAME_LENGTH + 10)
        result = bp._normalize_group_name(name)
        assert len(result) <= bp.MAX_GROUP_NAME_LENGTH

    def test_numeric_string_allowed(self):
        assert bp._normalize_group_name("123") == "123"

    def test_special_chars_allowed(self):
        assert bp._normalize_group_name("Group-A/B") == "Group-A/B"


# ---------------------------------------------------------------------------
# _metadata_changed_at_value
# ---------------------------------------------------------------------------

class TestMetadataChangedAtValue:
    def test_positive_int(self):
        assert bp._metadata_changed_at_value(1000) == 1000

    def test_zero_returns_zero(self):
        assert bp._metadata_changed_at_value(0) == 0

    def test_negative_returns_zero(self):
        assert bp._metadata_changed_at_value(-1) == 0

    def test_none_returns_zero(self):
        assert bp._metadata_changed_at_value(None) == 0

    def test_bool_true_returns_zero(self):
        # bool is a subclass of int but True/False are rejected by the guard
        assert bp._metadata_changed_at_value(True) == 0

    def test_bool_false_returns_zero(self):
        assert bp._metadata_changed_at_value(False) == 0

    def test_float_positive_converted(self):
        assert bp._metadata_changed_at_value(1000.9) == 1000

    def test_string_integer_parsed(self):
        assert bp._metadata_changed_at_value("1713350400000") == 1713350400000

    def test_string_non_integer_returns_zero(self):
        assert bp._metadata_changed_at_value("abc") == 0

    def test_empty_string_returns_zero(self):
        assert bp._metadata_changed_at_value("") == 0


# ---------------------------------------------------------------------------
# _metadata_revision_value
# ---------------------------------------------------------------------------

class TestMetadataRevisionValue:
    def test_positive_int(self):
        assert bp._metadata_revision_value(5) == 5

    def test_zero_returns_zero(self):
        assert bp._metadata_revision_value(0) == 0

    def test_negative_returns_zero(self):
        assert bp._metadata_revision_value(-3) == 0

    def test_none_returns_zero(self):
        assert bp._metadata_revision_value(None) == 0

    def test_bool_returns_zero(self):
        assert bp._metadata_revision_value(True) == 0
        assert bp._metadata_revision_value(False) == 0

    def test_string_parsed(self):
        assert bp._metadata_revision_value("7") == 7

    def test_bad_string_returns_zero(self):
        assert bp._metadata_revision_value("nope") == 0


# ---------------------------------------------------------------------------
# _metadata_writer_id_value
# ---------------------------------------------------------------------------

class TestMetadataWriterIdValue:
    def test_normal_string_passes(self):
        assert bp._metadata_writer_id_value("abc-123") == "abc-123"

    def test_none_returns_empty(self):
        assert bp._metadata_writer_id_value(None) == ""

    def test_empty_returns_empty(self):
        assert bp._metadata_writer_id_value("") == ""

    def test_whitespace_stripped(self):
        assert bp._metadata_writer_id_value("  id  ") == "id"

    def test_truncated_at_120(self):
        long_id = "x" * 200
        result = bp._metadata_writer_id_value(long_id)
        assert len(result) == 120

    def test_exactly_120_not_truncated(self):
        exact = "x" * 120
        assert bp._metadata_writer_id_value(exact) == exact


# ---------------------------------------------------------------------------
# _metadata_writer_version_value
# ---------------------------------------------------------------------------

class TestMetadataWriterVersionValue:
    def test_normal_string_passes(self):
        assert bp._metadata_writer_version_value("1.2.3") == "1.2.3"

    def test_none_returns_empty(self):
        assert bp._metadata_writer_version_value(None) == ""

    def test_truncated_at_64(self):
        long_v = "v" * 100
        result = bp._metadata_writer_version_value(long_v)
        assert len(result) == 64

    def test_exactly_64_not_truncated(self):
        exact = "v" * 64
        assert bp._metadata_writer_version_value(exact) == exact
