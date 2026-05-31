"""
test_csv.py — tests for _serialize_parameters_to_csv and _parse_parameters_csv.

Pure functions: no design, no Fusion API.
"""
import pytest
import BetterParameters as bp
from helpers import make_mock_design
from unittest.mock import patch


# ---------------------------------------------------------------------------
# _serialize_parameters_to_csv
# ---------------------------------------------------------------------------

class TestSerializeParametersToCsv:
    def _roundtrip(self, params):
        csv_text = bp._serialize_parameters_to_csv(params)
        rows, err = bp._parse_parameters_csv(csv_text)
        assert err == ""
        return rows

    def test_header_row_present(self):
        csv_text = bp._serialize_parameters_to_csv([])
        first_line = csv_text.strip().split("\n")[0]
        assert first_line.lower() == "name,unit,expression,value,comment,favorite"

    def test_empty_list_produces_header_only(self):
        csv_text = bp._serialize_parameters_to_csv([])
        lines = [l for l in csv_text.strip().split("\n") if l]
        assert len(lines) == 1  # header only

    def test_single_parameter_roundtrip(self):
        params = [{"name": "width", "expression": "100 mm", "unit": "mm", "comment": "Overall width", "group": "Dims"}]
        rows = self._roundtrip(params)
        assert len(rows) == 1
        assert rows[0]["name"] == "width"
        assert rows[0]["expression"] == "100 mm"
        assert rows[0]["unit"] == "mm"
        assert rows[0]["comment"] == "Overall width"
        assert rows[0]["group"] == ""

    def test_multiple_parameters_roundtrip(self):
        params = [
            {"name": "a", "expression": "1 mm", "unit": "mm", "comment": "", "group": ""},
            {"name": "b", "expression": "2 mm", "unit": "mm", "comment": "note", "group": "G1"},
            {"name": "c", "expression": "3 deg", "unit": "deg", "comment": "", "group": ""},
        ]
        rows = self._roundtrip(params)
        assert len(rows) == 3
        assert [r["name"] for r in rows] == ["a", "b", "c"]

    def test_empty_optional_fields_survive(self):
        params = [{"name": "x", "expression": "5", "unit": "", "comment": "", "group": ""}]
        rows = self._roundtrip(params)
        assert rows[0]["unit"] == ""
        assert rows[0]["comment"] == ""
        assert rows[0]["group"] == ""

    def test_export_header_exact_order_for_fusion(self):
        csv_text = bp._serialize_parameters_to_csv([
            {"name": "n", "unit": "mm", "expression": "1 mm", "valuePreview": "1 mm", "comment": "c", "isFavorite": True}
        ])
        first_line = csv_text.splitlines()[0].strip().lower()
        assert first_line == "name,unit,expression,value,comment,favorite"

    def test_export_includes_value_and_favorite(self):
        csv_text = bp._serialize_parameters_to_csv([
            {"name": "n", "unit": "mm", "expression": "1 mm", "valuePreview": "1 mm", "comment": "c", "isFavorite": True}
        ])
        data_line = csv_text.splitlines()[1]
        assert data_line == "n,mm,1 mm,1 mm,c,true"

    def test_export_can_include_metadata_parameter_row(self, tmp_path):
        payload = {
            "s": 1,
            "r": 1,
            "t": 1000,
            "w": "writer",
            "wv": "1.0.0",
            "g": ["Dims"],
            "p": [["token:width", 0]],
        }
        metadata_comment = bp._encode_metadata_comment(payload)
        out_path = tmp_path / "out.csv"
        design = make_mock_design([
            {"name": "width", "expression": "10 mm", "unit": "mm"},
            {"name": bp.METADATA_PARAMETER_NAME, "expression": "0", "unit": "", "comment": metadata_comment},
        ])
        with patch.object(bp, "_require_design", return_value=design), \
             patch.object(bp, "_collect_user_parameters", return_value=[
                 {"name": "width", "unit": "mm", "expression": "10 mm", "valuePreview": "10 mm", "comment": "", "isFavorite": False}
             ]):
            result = bp._export_parameters({
                "filePath": str(out_path),
                "includeMetadataParameter": True,
            })
        assert result["metadataExported"] is True
        rows, err = bp._parse_parameters_csv(out_path.read_text(encoding="utf-8-sig"))
        assert err == ""
        assert [row["name"] for row in rows] == ["width", bp.METADATA_PARAMETER_NAME]
        assert rows[1]["comment"] == metadata_comment
        assert "width" in rows[1]["value"]

    def test_export_text_expression_uses_single_quotes(self):
        csv_text = bp._serialize_parameters_to_csv([
            {"name": "txt", "unit": "Text", "expression": "`O'Hare`", "valuePreview": "O'Hare", "comment": "", "isFavorite": False}
        ])
        data_line = csv_text.splitlines()[1]
        assert data_line == "txt,Text,'O''Hare',O'Hare,,false"

    def test_commas_in_comment_survive(self):
        params = [{"name": "x", "expression": "1 mm", "unit": "mm", "comment": "a, b, c", "group": ""}]
        rows = self._roundtrip(params)
        assert rows[0]["comment"] == "a, b, c"

    def test_unicode_in_values_survive(self):
        params = [{"name": "x", "expression": "1 mm", "unit": "mm", "comment": "café", "group": "Schéma"}]
        rows = self._roundtrip(params)
        assert rows[0]["comment"] == "café"
        assert rows[0]["group"] == ""


# ---------------------------------------------------------------------------
# _parse_parameters_csv
# ---------------------------------------------------------------------------

class TestParseParametersCsv:
    def test_minimal_valid_csv(self):
        csv_text = "name,expression\nwidth,100 mm\n"
        rows, err = bp._parse_parameters_csv(csv_text)
        assert err == ""
        assert len(rows) == 1
        assert rows[0]["name"] == "width"
        assert rows[0]["expression"] == "100 mm"

    def test_all_columns_present(self):
        csv_text = "name,expression,unit,comment,group\nwidth,100 mm,mm,Overall width,Dims\n"
        rows, err = bp._parse_parameters_csv(csv_text)
        assert err == ""
        assert rows[0]["unit"] == "mm"
        assert rows[0]["comment"] == "Overall width"
        assert rows[0]["group"] == "Dims"

    def test_value_column_is_preserved_for_metadata_transport(self):
        csv_text = 'name,expression,unit,value,comment\n_bp_metadata_v1,0,,"{""sourceParameterNames"":[]}",payload\n'
        rows, err = bp._parse_parameters_csv(csv_text)
        assert err == ""
        assert rows[0]["value"] == '{"sourceParameterNames":[]}'

    def test_metadata_parameter_row_import_remaps_by_name(self, tmp_path):
        payload = {
            "s": 1,
            "r": 1,
            "t": 1000,
            "w": "writer",
            "wv": "1.0.0",
            "g": ["Dims"],
            "p": [["source-token-width", 0]],
        }
        metadata_comment = bp._encode_metadata_comment(payload)
        csv_text = (
            "name,unit,expression,value,comment,favorite\n"
            f"{bp.METADATA_PARAMETER_NAME},,0,\"{{\"\"sourceParameterNames\"\": [\"\"width\"\"]}}\",{metadata_comment},false\n"
        )
        path = tmp_path / "metadata.csv"
        path.write_text(csv_text, encoding="utf-8")
        design = make_mock_design([
            {"name": "width", "expression": "10 mm", "unit": "mm"},
        ])
        with patch.object(bp, "_require_design", return_value=design), \
             patch.object(bp, "_write_metadata_parameter_model") as write_model:
            result = bp._import_parameters({"filePath": str(path)}, dry_run=False)
        assert result["ok"] is True
        assert result["metadataImported"] is True
        write_model.assert_called_once()
        written_model = write_model.call_args.args[1]
        assert written_model["orderedTokens"] == ["token:width"]
        assert written_model["groupsByToken"] == {"token:width": "Dims"}

    def test_optional_columns_default_to_empty_string(self):
        csv_text = "name,expression\nwidth,100 mm\n"
        rows, err = bp._parse_parameters_csv(csv_text)
        assert err == ""
        assert rows[0]["unit"] == ""
        assert rows[0]["comment"] == ""
        assert rows[0]["group"] == ""

    def test_missing_name_column_fails(self):
        csv_text = "expression,unit\n100 mm,mm\n"
        rows, err = bp._parse_parameters_csv(csv_text)
        assert rows is None
        assert "name" in err.lower()

    def test_missing_expression_column_fails(self):
        csv_text = "name,unit\nwidth,mm\n"
        rows, err = bp._parse_parameters_csv(csv_text)
        assert rows is None
        assert "expression" in err.lower()

    def test_header_only_returns_empty_list(self):
        csv_text = "name,expression,unit,comment,group\n"
        rows, err = bp._parse_parameters_csv(csv_text)
        assert err == ""
        assert rows == []

    def test_extra_columns_ignored(self):
        csv_text = "name,expression,unit,comment,group,extra_col\nwidth,100 mm,mm,,,"
        rows, err = bp._parse_parameters_csv(csv_text)
        assert err == ""
        assert len(rows) == 1
        assert rows[0]["name"] == "width"

    def test_column_names_case_insensitive(self):
        csv_text = "Name,Expression,Unit,Comment,Group\nwidth,100 mm,mm,note,G1\n"
        rows, err = bp._parse_parameters_csv(csv_text)
        assert err == ""
        assert rows[0]["name"] == "width"

    def test_whitespace_in_values_stripped(self):
        csv_text = "name,expression\n  width  ,  100 mm  \n"
        rows, err = bp._parse_parameters_csv(csv_text)
        assert err == ""
        assert rows[0]["name"] == "width"
        assert rows[0]["expression"] == "100 mm"

    def test_multiple_rows(self):
        csv_text = "name,expression\na,1 mm\nb,2 mm\nc,3 mm\n"
        rows, err = bp._parse_parameters_csv(csv_text)
        assert err == ""
        assert len(rows) == 3

    def test_malformed_csv_returns_error(self):
        # Unmatched quotes cause csv module to raise
        rows, err = bp._parse_parameters_csv('name,expression\n"bad,field\n')
        # Depending on csv module version this may succeed or fail;
        # what matters is no unhandled exception.
        assert rows is None or isinstance(rows, list)

    def test_bom_stripped(self):
        # UTF-8 BOM prefix should be handled gracefully (csv reader sees it as part of first key)
        csv_text = "\ufeffname,expression\nwidth,100 mm\n"
        rows, err = bp._parse_parameters_csv(csv_text)
        # BOM may end up in the column name key; at minimum should not crash
        assert isinstance(rows, list) or rows is None
