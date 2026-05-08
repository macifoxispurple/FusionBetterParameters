"""
test_model_parameters.py — offline tests for _model_parameter_count,
_get_model_parameters, and the state payload shape change.

Covers:
  - _model_parameter_count: no design, empty, N params
  - _get_model_parameters: pagination (offset/limit), filter, sort, cap,
    no design raises, empty collection, bad offset/limit coercion
  - State payload contains modelParameterCount not modelParameters
  - getModelParameters in _READ_ONLY_ACTIONS, not _MUTATING_ACTIONS
"""
import pytest
from unittest.mock import MagicMock, PropertyMock, patch
import BetterParameters as BP
from helpers import make_mock_param


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_model_param(name="d1", expression="5 mm", unit="mm"):
    p = MagicMock()
    p.name = name
    p.expression = expression
    p.unit = unit
    p.comment = ""
    p.isFavorite = False
    p.entityToken = f"tok_{name}"
    return p


def _make_design_with_model_params(*specs, component_name="TestComponent",
                                    component_token="tok_comp_TestComponent"):
    """specs: list of (name, expression) tuples.

    All params are placed in a single mock component accessed via design.allComponents.
    Mirrors real best-practice designs where root component contains no geometry.
    """
    params = []
    for name, expression in specs:
        params.append(_make_model_param(name=name, expression=expression))

    collection = MagicMock()
    collection.count = len(params)
    collection.item.side_effect = lambda i: params[i] if 0 <= i < len(params) else None

    component = MagicMock()
    component.name = component_name
    component.entityToken = component_token
    component.modelParameters = collection

    all_components = MagicMock()
    all_components.count = 1
    all_components.item.side_effect = lambda i: component if i == 0 else None

    design = MagicMock()
    design.allComponents = all_components
    design.unitsManager.defaultLengthUnits = "mm"
    design.unitsManager.isValidExpression.return_value = True
    return design, params


def _call_get(design, **kwargs):
    with patch.object(BP, "_design", return_value=design), \
         patch.object(BP, "_require_design", return_value=design):
        return BP._get_model_parameters(kwargs)


# ---------------------------------------------------------------------------
# _model_parameter_count
# ---------------------------------------------------------------------------

def test_count_no_design_returns_zero():
    with patch.object(BP, "_design", return_value=None):
        assert BP._model_parameter_count() == 0


def test_count_empty_collection():
    design, _ = _make_design_with_model_params()
    with patch.object(BP, "_design", return_value=design):
        assert BP._model_parameter_count() == 0


def test_count_returns_correct_number():
    design, _ = _make_design_with_model_params(
        ("d1", "5 mm"), ("d2", "10 mm"), ("d3", "15 mm")
    )
    with patch.object(BP, "_design", return_value=design):
        assert BP._model_parameter_count() == 3


def test_count_exception_returns_zero():
    design = MagicMock()
    type(design).allComponents = PropertyMock(side_effect=RuntimeError("fail"))
    with patch.object(BP, "_design", return_value=design):
        assert BP._model_parameter_count() == 0


def _make_design_multi_component(*component_specs):
    """component_specs: list of (component_name, [(param_name, expression), ...]) tuples.

    Each component gets a deterministic entityToken: "tok_comp_<component_name>".
    """
    components = []
    for comp_name, param_specs in component_specs:
        params = [_make_model_param(name=n, expression=e) for n, e in param_specs]
        collection = MagicMock()
        collection.count = len(params)
        collection.item.side_effect = (lambda ps: lambda i: ps[i] if 0 <= i < len(ps) else None)(params)
        comp = MagicMock()
        comp.name = comp_name
        comp.entityToken = f"tok_comp_{comp_name}"
        comp.modelParameters = collection
        components.append(comp)

    all_components = MagicMock()
    all_components.count = len(components)
    all_components.item.side_effect = (lambda cs: lambda i: cs[i] if 0 <= i < len(cs) else None)(components)

    design = MagicMock()
    design.allComponents = all_components
    design.unitsManager.defaultLengthUnits = "mm"
    design.unitsManager.isValidExpression.return_value = True
    return design


def test_count_sums_across_all_components():
    design = _make_design_multi_component(
        ("Body", [("d1", "5 mm"), ("d2", "10 mm")]),
        ("Lid",  [("d1", "3 mm"), ("d3", "7 mm"), ("d4", "2 mm")]),
    )
    with patch.object(BP, "_design", return_value=design):
        assert BP._model_parameter_count() == 5


def test_get_collects_params_from_all_components():
    design = _make_design_multi_component(
        ("Body", [("width", "50 mm"), ("depth", "30 mm")]),
        ("Lid",  [("height", "10 mm")]),
    )
    with patch.object(BP, "_design", return_value=design), \
         patch.object(BP, "_require_design", return_value=design):
        result = BP._get_model_parameters({})
    assert result["totalCount"] == 3
    names = {p["name"] for p in result["parameters"]}
    assert names == {"width", "depth", "height"}


def test_get_includes_component_name_in_results():
    design = _make_design_multi_component(
        ("Body", [("width", "50 mm")]),
        ("Lid",  [("height", "10 mm")]),
    )
    with patch.object(BP, "_design", return_value=design), \
         patch.object(BP, "_require_design", return_value=design):
        result = BP._get_model_parameters({})
    comp_names = {p["componentName"] for p in result["parameters"]}
    assert comp_names == {"Body", "Lid"}


def test_get_sorted_by_component_then_name():
    design = _make_design_multi_component(
        ("Zebra", [("zz", "1 mm"), ("aa", "2 mm")]),
        ("Apple", [("mm", "3 mm")]),
    )
    with patch.object(BP, "_design", return_value=design), \
         patch.object(BP, "_require_design", return_value=design):
        result = BP._get_model_parameters({})
    pairs = [(p["componentName"], p["name"]) for p in result["parameters"]]
    assert pairs == sorted(pairs, key=lambda t: (t[0].casefold(), t[1].casefold()))


# ---------------------------------------------------------------------------
# componentId — stable component identity
# ---------------------------------------------------------------------------

def test_get_includes_component_id_field():
    """Every parameter row must include componentId as a string."""
    design = _make_design_multi_component(
        ("Body", [("d1", "5 mm"), ("d2", "10 mm")]),
        ("Lid",  [("d3", "3 mm")]),
    )
    with patch.object(BP, "_design", return_value=design), \
         patch.object(BP, "_require_design", return_value=design):
        result = BP._get_model_parameters({})
    for p in result["parameters"]:
        assert "componentId" in p
        assert isinstance(p["componentId"], str)


def test_component_id_is_entity_token_not_name():
    """componentId should be the entityToken, not the component name."""
    design, _ = _make_design_with_model_params(
        ("d1", "5 mm"),
        component_name="MyBody",
        component_token="stable-token-abc123",
    )
    with patch.object(BP, "_design", return_value=design), \
         patch.object(BP, "_require_design", return_value=design):
        result = BP._get_model_parameters({})
    assert result["parameters"][0]["componentId"] == "stable-token-abc123"
    assert result["parameters"][0]["componentName"] == "MyBody"


def test_component_id_stable_across_rename():
    """componentId must not change when component name changes (simulate rename)."""
    params = [_make_model_param(name="d1", expression="5 mm")]

    collection = MagicMock()
    collection.count = 1
    collection.item.side_effect = lambda i: params[i] if i == 0 else None

    comp = MagicMock()
    comp.entityToken = "stable-token-xyz"
    comp.modelParameters = collection

    all_comps = MagicMock()
    all_comps.count = 1
    all_comps.item.side_effect = lambda i: comp if i == 0 else None

    design = MagicMock()
    design.allComponents = all_comps
    design.unitsManager.defaultLengthUnits = "mm"
    design.unitsManager.isValidExpression.return_value = True

    with patch.object(BP, "_design", return_value=design), \
         patch.object(BP, "_require_design", return_value=design):

        comp.name = "OriginalName"
        result_before = BP._get_model_parameters({})
        id_before = result_before["parameters"][0]["componentId"]

        comp.name = "RenamedComponent"
        result_after = BP._get_model_parameters({})
        id_after = result_after["parameters"][0]["componentId"]

    assert id_before == id_after == "stable-token-xyz"
    assert result_before["parameters"][0]["componentName"] == "OriginalName"
    assert result_after["parameters"][0]["componentName"] == "RenamedComponent"


def test_component_id_empty_string_when_token_unavailable():
    """When entityToken raises, componentId must be empty string — never fabricated."""
    params = [_make_model_param(name="d1", expression="5 mm")]

    collection = MagicMock()
    collection.count = 1
    collection.item.side_effect = lambda i: params[i] if i == 0 else None

    comp = MagicMock()
    comp.name = "Body"
    type(comp).entityToken = PropertyMock(side_effect=RuntimeError("token unavailable"))
    comp.modelParameters = collection

    all_comps = MagicMock()
    all_comps.count = 1
    all_comps.item.side_effect = lambda i: comp if i == 0 else None

    design = MagicMock()
    design.allComponents = all_comps
    design.unitsManager.defaultLengthUnits = "mm"
    design.unitsManager.isValidExpression.return_value = True

    with patch.object(BP, "_design", return_value=design), \
         patch.object(BP, "_require_design", return_value=design):
        result = BP._get_model_parameters({})

    assert result["parameters"][0]["componentId"] == ""


def test_envelope_fields_unchanged_with_component_id():
    """Adding componentId must not break ok/state/message envelope shape."""
    design, _ = _make_design_with_model_params(("d1", "5 mm"))
    with patch.object(BP, "_design", return_value=design), \
         patch.object(BP, "_require_design", return_value=design):
        result = BP._get_model_parameters({})
    assert result["ok"] is True
    assert "totalCount" in result
    assert "parameters" in result
    assert "offset" in result
    assert "limit" in result


# ---------------------------------------------------------------------------
# _get_model_parameters — basic happy path
# ---------------------------------------------------------------------------

def test_get_returns_ok():
    design, _ = _make_design_with_model_params(("d1", "5 mm"))
    result = _call_get(design)
    assert result["ok"] is True


def test_get_returns_all_params_by_default():
    design, _ = _make_design_with_model_params(
        ("d1", "5 mm"), ("d2", "10 mm"), ("d3", "15 mm")
    )
    result = _call_get(design)
    assert result["totalCount"] == 3
    assert len(result["parameters"]) == 3


def test_get_sorted_by_name_case_insensitive():
    design, _ = _make_design_with_model_params(
        ("Zebra", "1 mm"), ("apple", "2 mm"), ("Mango", "3 mm")
    )
    result = _call_get(design)
    names = [p["name"] for p in result["parameters"]]
    assert names == sorted(names, key=str.casefold)


def test_get_empty_collection_returns_empty():
    design, _ = _make_design_with_model_params()
    result = _call_get(design)
    assert result["ok"] is True
    assert result["totalCount"] == 0
    assert result["parameters"] == []


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------

def test_pagination_limit():
    specs = [(f"d{i}", f"{i} mm") for i in range(10)]
    design, _ = _make_design_with_model_params(*specs)
    result = _call_get(design, offset=0, limit=3)
    assert len(result["parameters"]) == 3
    assert result["totalCount"] == 10
    assert result["offset"] == 0
    assert result["limit"] == 3


def test_pagination_offset():
    specs = [(f"d{i:02d}", f"{i} mm") for i in range(10)]
    design, _ = _make_design_with_model_params(*specs)
    result_first = _call_get(design, offset=0, limit=3)
    result_second = _call_get(design, offset=3, limit=3)
    first_names = {p["name"] for p in result_first["parameters"]}
    second_names = {p["name"] for p in result_second["parameters"]}
    assert first_names.isdisjoint(second_names)


def test_pagination_offset_beyond_end_returns_empty_page():
    design, _ = _make_design_with_model_params(("d1", "1 mm"), ("d2", "2 mm"))
    result = _call_get(design, offset=100, limit=10)
    assert result["parameters"] == []
    assert result["totalCount"] == 2  # total unaffected by offset


def test_pagination_limit_capped_at_max():
    specs = [(f"d{i}", f"{i} mm") for i in range(5)]
    design, _ = _make_design_with_model_params(*specs)
    result = _call_get(design, offset=0, limit=99999)
    assert result["limit"] == BP._MODEL_PARAMETER_MAX_LIMIT


def test_pagination_limit_minimum_one():
    design, _ = _make_design_with_model_params(("d1", "1 mm"))
    result = _call_get(design, offset=0, limit=0)
    assert result["limit"] >= 1


def test_pagination_negative_offset_clamped_to_zero():
    design, _ = _make_design_with_model_params(("d1", "1 mm"))
    result = _call_get(design, offset=-5, limit=10)
    assert result["offset"] == 0


# ---------------------------------------------------------------------------
# Filter
# ---------------------------------------------------------------------------

def test_filter_by_name_substring():
    design, _ = _make_design_with_model_params(
        ("sketch_width", "10 mm"),
        ("extrude_depth", "5 mm"),
        ("sketch_height", "8 mm"),
    )
    result = _call_get(design, filter="sketch")
    assert result["totalCount"] == 2
    names = {p["name"] for p in result["parameters"]}
    assert "sketch_width" in names
    assert "sketch_height" in names
    assert "extrude_depth" not in names


def test_filter_by_expression_substring():
    design, _ = _make_design_with_model_params(
        ("d1", "width * 2"),
        ("d2", "height + 5"),
        ("d3", "width / 3"),
    )
    result = _call_get(design, filter="width")
    assert result["totalCount"] == 2


def test_filter_case_insensitive():
    design, _ = _make_design_with_model_params(
        ("Sketch_Depth", "10 mm"),
        ("extrude_height", "5 mm"),
    )
    result = _call_get(design, filter="SKETCH")
    assert result["totalCount"] == 1
    assert result["parameters"][0]["name"] == "Sketch_Depth"


def test_filter_empty_string_returns_all():
    design, _ = _make_design_with_model_params(("d1", "1 mm"), ("d2", "2 mm"))
    result = _call_get(design, filter="")
    assert result["totalCount"] == 2


def test_filter_no_match_returns_empty():
    design, _ = _make_design_with_model_params(("d1", "1 mm"), ("d2", "2 mm"))
    result = _call_get(design, filter="zzznomatch")
    assert result["totalCount"] == 0
    assert result["parameters"] == []


def test_filter_by_component_name():
    design = _make_design_multi_component(
        ("WheelBody", [("d1", "5 mm"), ("d2", "10 mm")]),
        ("Axle",     [("d1", "3 mm")]),
    )
    with patch.object(BP, "_design", return_value=design), \
         patch.object(BP, "_require_design", return_value=design):
        result = BP._get_model_parameters({"filter": "wheel"})
    assert result["totalCount"] == 2
    assert all(p["componentName"] == "WheelBody" for p in result["parameters"])


def test_filter_by_component_name_case_insensitive():
    design = _make_design_multi_component(
        ("WheelBody", [("d1", "5 mm")]),
        ("Axle",      [("d2", "3 mm")]),
    )
    with patch.object(BP, "_design", return_value=design), \
         patch.object(BP, "_require_design", return_value=design):
        result = BP._get_model_parameters({"filter": "WHEELBODY"})
    assert result["totalCount"] == 1
    assert result["parameters"][0]["componentName"] == "WheelBody"


def test_filter_totalcount_reflects_filtered_not_total():
    design, _ = _make_design_with_model_params(
        ("d1", "1 mm"), ("d2", "2 mm"), ("sketch_w", "10 mm")
    )
    result = _call_get(design, filter="sketch", offset=0, limit=10)
    assert result["totalCount"] == 1   # only filtered count
    assert len(result["parameters"]) == 1


# ---------------------------------------------------------------------------
# No design
# ---------------------------------------------------------------------------

def test_no_design_raises():
    with patch.object(BP, "_require_design", side_effect=BP.BPNoDesignError()):
        with pytest.raises(BP.BPNoDesignError):
            BP._get_model_parameters({})


# ---------------------------------------------------------------------------
# State payload shape
# ---------------------------------------------------------------------------

def test_state_payload_has_model_parameter_count_not_model_parameters():
    design = MagicMock()

    mock_comp = MagicMock()
    mock_comp.modelParameters.count = 42
    mock_all_comps = MagicMock()
    mock_all_comps.count = 1
    mock_all_comps.item.side_effect = lambda i: mock_comp if i == 0 else None
    design.allComponents = mock_all_comps

    design.userParameters.count = 0
    design.allParameters.count = 0
    design.allParameters.item.return_value = None
    design.unitsManager.defaultLengthUnits = "mm"

    with patch.object(BP, "_design", return_value=design), \
         patch.object(BP, "_require_design", return_value=design), \
         patch.object(BP, "_read_document_order_state", return_value={}), \
         patch.object(BP, "_sync_ui_state_between_local_and_fusion", return_value={}), \
         patch.object(BP, "_collect_user_parameters", return_value=[]), \
         patch.object(BP, "_collect_parameter_groups", return_value=[]), \
         patch.object(BP, "_collect_all_parameter_names", return_value=[]), \
         patch.object(BP, "_load_settings", return_value={}), \
         patch.object(BP, "_active_document_info", return_value={}), \
         patch.object(BP, "_default_document_unit", return_value="mm"), \
         patch.object(BP, "_load_text_tuner_state", return_value={}), \
         patch.object(BP, "_detect_fusion_theme", return_value="light"), \
         patch.object(BP, "_build_update_info_payload", return_value={}):
        payload = BP._current_state_payload()

    assert "modelParameterCount" in payload
    assert "modelParameters" not in payload
    assert payload["modelParameterCount"] == 42


# ---------------------------------------------------------------------------
# Action classification
# ---------------------------------------------------------------------------

def test_get_model_parameters_in_read_only_actions():
    assert "getModelParameters" in BP._READ_ONLY_ACTIONS


def test_get_model_parameters_not_in_mutating_actions():
    assert "getModelParameters" not in BP._MUTATING_ACTIONS


def test_promote_model_parameter_action_in_mutating_actions():
    assert "promoteModelParameterToUserParameter" in BP._MUTATING_ACTIONS


def test_promote_model_parameter_creates_user_then_links_model_expression():
    events = []

    class _ModelParam:
        def __init__(self):
            self.name = "d12"
            self.unit = "mm"
            self.comment = "model comment"
            self._expression = "base_width * 2"

        @property
        def expression(self):
            return self._expression

        @expression.setter
        def expression(self, value):
            events.append(("set_model_expression", value))
            self._expression = value

    model_param = _ModelParam()
    created_param = MagicMock()
    design = MagicMock()

    def _add_user(name, value_input, unit, comment):
        events.append(("add_user", name, unit, comment))
        return created_param

    design.userParameters.add.side_effect = _add_user

    def _set_group(payload):
        events.append(("set_group", payload.get("name"), payload.get("group")))

    with patch.object(BP, "_require_design", return_value=design), \
         patch.object(BP, "_find_model_parameter_by_token", return_value=model_param), \
         patch.object(BP, "_set_parameter_group", side_effect=_set_group), \
         patch.object(BP, "_validate_parameter_name_response", return_value={"ok": True, "message": ""}):
        BP._promote_model_parameter_to_user_parameter({
            "key": "tok_model_1",
            "newName": "promoted_width",
            "group": "Body"
        })

    assert events[0] == ("add_user", "promoted_width", "mm", "model comment")
    assert events[1] == ("set_group", "promoted_width", "Body")
    assert events[2] == ("set_model_expression", "promoted_width")


def test_promote_model_parameter_rolls_back_new_user_param_if_link_step_fails():
    class _ModelParam:
        def __init__(self):
            self.name = "d13"
            self.unit = "mm"
            self.comment = ""
            self._expression = "20 mm"

        @property
        def expression(self):
            return self._expression

        @expression.setter
        def expression(self, _value):
            raise RuntimeError("cannot set expression")

    model_param = _ModelParam()
    created_param = MagicMock()
    design = MagicMock()
    design.userParameters.add.return_value = created_param

    with patch.object(BP, "_require_design", return_value=design), \
         patch.object(BP, "_find_model_parameter_by_token", return_value=model_param), \
         patch.object(BP, "_validate_parameter_name_response", return_value={"ok": True, "message": ""}):
        with pytest.raises(ValueError, match="Created user parameter 'promoted_depth'"):
            BP._promote_model_parameter_to_user_parameter({
                "key": "tok_model_2",
                "newName": "promoted_depth"
            })

    created_param.deleteMe.assert_called_once()


def test_promote_model_parameter_rolls_back_if_group_assignment_fails():
    class _ModelParam:
        def __init__(self):
            self.name = "d14"
            self.unit = "mm"
            self.comment = ""
            self._expression = "30 mm"

        @property
        def expression(self):
            return self._expression

        @expression.setter
        def expression(self, value):
            self._expression = value

    model_param = _ModelParam()
    created_param = MagicMock()
    design = MagicMock()
    design.userParameters.add.return_value = created_param

    with patch.object(BP, "_require_design", return_value=design), \
         patch.object(BP, "_find_model_parameter_by_token", return_value=model_param), \
         patch.object(BP, "_set_parameter_group", side_effect=ValueError("group write failed")), \
         patch.object(BP, "_validate_parameter_name_response", return_value={"ok": True, "message": ""}):
        with pytest.raises(ValueError, match="failed to assign group 'Body'"):
            BP._promote_model_parameter_to_user_parameter({
                "key": "tok_model_3",
                "newName": "promoted_height",
                "group": "Body"
            })

    created_param.deleteMe.assert_called_once()
