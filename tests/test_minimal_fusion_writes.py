from unittest.mock import MagicMock, patch
from types import SimpleNamespace

import BetterParameters as BP


class CountingField:
    def __init__(self, value=""):
        self._value = value
        self.write_count = 0

    @property
    def value(self):
        return self._value

    @value.setter
    def value(self, next_value):
        self.write_count += 1
        self._value = next_value


class DeletableAttribute(CountingField):
    def __init__(self, value=""):
        super().__init__(value)
        self.deleted = False

    def deleteMe(self):
        self.deleted = True


class AttributeCollection:
    def __init__(self, values=None):
        self._attrs = {}
        for key, value in (values or {}).items():
            self._attrs[key] = DeletableAttribute(value)

    def itemByName(self, namespace, name):
        return self._attrs.get((namespace, name))

    def add(self, namespace, name, value):
        attr = DeletableAttribute(value)
        self._attrs[(namespace, name)] = attr
        return attr


class CountingParameter:
    def __init__(self, name="width", expression="10 mm", comment=""):
        self._name = name
        self.unit = "mm"
        self.entityToken = f"tok_{name}"
        self.isFavorite = False
        self._expression = expression
        self._comment = comment
        self.name_write_count = 0
        self.expression_write_count = 0
        self.comment_write_count = 0

    @property
    def name(self):
        return self._name

    @name.setter
    def name(self, next_value):
        self.name_write_count += 1
        self._name = next_value

    @property
    def expression(self):
        return self._expression

    @expression.setter
    def expression(self, next_value):
        self.expression_write_count += 1
        self._expression = next_value

    @property
    def comment(self):
        return self._comment

    @comment.setter
    def comment(self, next_value):
        self.comment_write_count += 1
        self._comment = next_value


class ParameterCollection:
    def __init__(self, params):
        self._params = list(params)

    @property
    def count(self):
        return len(self._params)

    def item(self, index):
        return self._params[index] if 0 <= index < len(self._params) else None

    def itemByName(self, name):
        for param in self._params:
            if param.name == name:
                return param
        return None

    def add(self, name, value_input, unit, comment):
        created = CountingParameter(name=name, expression=str(value_input), comment=comment)
        created.unit = unit
        created.entityToken = f"tok_{name}"
        self._params.append(created)
        return created


def _design_with_user_params(params):
    design = MagicMock()
    design.userParameters = ParameterCollection(params)
    design.allParameters = design.userParameters
    design.unitsManager.defaultLengthUnits = "mm"
    return design


def test_update_parameter_skips_unchanged_expression_and_comment():
    param = CountingParameter(expression="10 mm", comment="same")
    design = MagicMock()
    design.userParameters.itemByName.return_value = param

    with patch.object(BP, "_require_design", return_value=design), \
         patch.object(BP, "_find_user_parameter_by_token", return_value=param):
        BP._update_parameter({"key": "tok_width", "name": "width", "expression": "10 mm", "comment": "same"})

    assert param.expression_write_count == 0
    assert param.comment_write_count == 0


def test_update_parameter_writes_only_changed_field():
    param = CountingParameter(expression="10 mm", comment="same")
    design = MagicMock()
    design.userParameters.itemByName.return_value = param

    with patch.object(BP, "_require_design", return_value=design), \
         patch.object(BP, "_find_user_parameter_by_token", return_value=param):
        BP._update_parameter({"key": "tok_width", "name": "width", "expression": "12 mm", "comment": "same"})

    assert param.expression_write_count == 1
    assert param.comment_write_count == 0


def test_rename_parameter_still_writes_to_fusion():
    param = CountingParameter(name="width")
    design = MagicMock()
    design.userParameters.itemByName.return_value = param

    with patch.object(BP, "_require_design", return_value=design), \
         patch.object(BP, "_find_user_parameter_by_token", return_value=param), \
         patch.object(BP, "_validate_parameter_name_response", return_value={"ok": True, "message": ""}):
        BP._rename_parameter({"key": "tok_width", "name": "width", "newName": "new_width"})

    assert param.name == "new_width"
    assert param.name_write_count == 1


def test_persist_document_order_snapshot_does_not_write_fusion_metadata_attrs():
    previous_state = {
        "documentId": "doc",
        "documentName": "Doc",
        "parameters": {
            "tok_width": {
                "order": 0,
                "name": "width",
                "current_expression": "10 mm",
                "previous_expression": "",
                "current_value": "10 mm",
                "previous_value": "",
                "group": "Dims",
                BP.METADATA_CHANGED_AT_RECORD_KEY: 100,
                BP.METADATA_REVISION_RECORD_KEY: 1,
                BP.METADATA_WRITER_ID_RECORD_KEY: "writer",
                BP.METADATA_WRITER_VERSION_RECORD_KEY: "0.1.0",
            }
        },
        "groupUi": {"order": [], "collapsed": {}},
        BP.UI_STATE_RECORD_KEY: {},
    }
    rows = [{
        "key": "tok_width",
        "name": "width",
        "expression": "12 mm",
        "valuePreview": "12 mm",
        "group": "Dims",
    }]

    with patch.object(BP, "_active_document_info", return_value={"id": "doc", "name": "Doc"}), \
         patch.object(BP, "_write_document_order_state") as write_local:
        BP._persist_document_order_snapshot(rows, previous_state)

    assert write_local.call_count == 1


def test_routine_snapshot_preserves_existing_group_when_incoming_group_is_blank():
    previous_state = {
        "documentId": "doc",
        "documentName": "Doc",
        "parameters": {
            "tok_width": {
                "order": 0,
                "name": "width",
                "current_expression": "10 mm",
                "previous_expression": "",
                "current_value": "10 mm",
                "previous_value": "",
                "group": "Dims",
                BP.METADATA_CHANGED_AT_RECORD_KEY: 100,
                BP.METADATA_REVISION_RECORD_KEY: 1,
                BP.METADATA_WRITER_ID_RECORD_KEY: "writer",
                BP.METADATA_WRITER_VERSION_RECORD_KEY: "0.1.0",
            }
        },
        "groupUi": {"order": [], "collapsed": {}},
        BP.UI_STATE_RECORD_KEY: {},
    }
    rows = [{
        "key": "tok_width",
        "name": "width",
        "expression": "12 mm",
        "valuePreview": "12 mm",
        "group": "",
        "metadataChangedAt": 999,
        "metadataRevision": 2,
        "metadataWriterId": "fusion-writer",
        "metadataWriterVersion": "0.1.0",
    }]

    with patch.object(BP, "_active_document_info", return_value={"id": "doc", "name": "Doc"}), \
         patch.object(BP, "_write_document_order_state") as write_local:
        BP._persist_document_order_snapshot(rows, previous_state)

    next_state = write_local.call_args.args[0]
    assert next_state["parameters"]["tok_width"]["group"] == "Dims"


def test_collect_user_parameters_does_not_backfill_newer_local_metadata_to_fusion():
    param = CountingParameter(expression="10 mm", comment="")
    param.entityToken = "tok_width"
    params = MagicMock()
    params.count = 1
    params.item.side_effect = lambda index: param if index == 0 else None
    design = MagicMock()
    design.userParameters = params
    design.unitsManager.defaultLengthUnits = "mm"
    order_state = {
        "parameters": {
            "tok_width": {
                "order": 0,
                "name": "width",
                "current_expression": "10 mm",
                "previous_expression": "",
                "current_value": "10 mm",
                "previous_value": "",
                "group": "Dims",
                BP.METADATA_CHANGED_AT_RECORD_KEY: 999,
                BP.METADATA_REVISION_RECORD_KEY: 2,
                BP.METADATA_WRITER_ID_RECORD_KEY: "local-writer",
                BP.METADATA_WRITER_VERSION_RECORD_KEY: "0.1.0",
            }
        },
        "groupUi": {"order": [], "collapsed": {}},
    }
    with patch.object(BP, "_design", return_value=design), \
         patch.object(BP, "_persist_document_order_snapshot", return_value=None):
        rows = BP._collect_user_parameters(order_state)

    assert len(rows) == 1
    assert rows[0]["group"] == "Dims"


def test_collect_user_parameters_preserves_local_group_when_fusion_metadata_is_blank():
    param = CountingParameter(expression="10 mm", comment="")
    param.entityToken = "tok_width"
    params = MagicMock()
    params.count = 1
    params.item.side_effect = lambda index: param if index == 0 else None
    design = MagicMock()
    design.userParameters = params
    design.unitsManager.defaultLengthUnits = "mm"
    order_state = {
        "parameters": {
            "tok_width": {
                "order": 0,
                "name": "width",
                "current_expression": "10 mm",
                "previous_expression": "",
                "current_value": "10 mm",
                "previous_value": "",
                "group": "Dims",
                BP.METADATA_CHANGED_AT_RECORD_KEY: 100,
                BP.METADATA_REVISION_RECORD_KEY: 1,
                BP.METADATA_WRITER_ID_RECORD_KEY: "local-writer",
                BP.METADATA_WRITER_VERSION_RECORD_KEY: "0.1.0",
            }
        },
        "groupUi": {"order": [], "collapsed": {}},
    }
    with patch.object(BP, "_design", return_value=design), \
         patch.object(BP, "_persist_document_order_snapshot", return_value=None):
        rows = BP._collect_user_parameters(order_state)

    assert len(rows) == 1
    assert rows[0]["group"] == "Dims"


def test_fusion_command_terminated_pushes_changed_palette_state():
    handler = BP.FusionCommandTerminatedHandler()
    palette = SimpleNamespace(isVisible=True)

    with patch.object(BP, "_palette", return_value=palette), \
         patch.object(BP, "_push_parameter_list_if_changed", return_value=True) as push_if_changed:
        handler.notify(SimpleNamespace(commandId="FusionParameterCommand"))

    push_if_changed.assert_called_once_with()


def test_fusion_command_terminated_ignores_bp_palette_command():
    handler = BP.FusionCommandTerminatedHandler()
    palette = SimpleNamespace(isVisible=True)

    with patch.object(BP, "_palette", return_value=palette), \
         patch.object(BP, "_push_parameter_list_if_changed") as push_if_changed:
        handler.notify(SimpleNamespace(commandId=BP.CMD_ID))

    push_if_changed.assert_not_called()


def test_metadata_comment_encode_decode_round_trip():
    payload = {
        "s": 1,
        "r": 2,
        "t": 123,
        "w": "writer",
        "wv": "0.9.8",
        "g": ["Dims"],
        "p": [["tok_width", 0]],
    }

    encoded = BP._encode_metadata_comment(payload)
    decoded = BP._decode_metadata_comment(encoded)

    assert encoded.startswith("BPM1Z:")
    assert decoded["ok"] is True
    assert decoded["payload"] == payload


def test_metadata_comment_hash_mismatch_rejected():
    payload = {"s": 1, "r": 1, "t": 1, "w": "writer", "wv": "0.9.8", "g": [], "p": []}
    encoded = BP._encode_metadata_comment(payload)
    tampered = encoded.replace(encoded.split(":")[1], "0" * 64, 1)

    decoded = BP._decode_metadata_comment(tampered)

    assert decoded["ok"] is False
    assert "hash mismatch" in decoded["error"]


def test_collect_user_parameters_hides_metadata_parameter():
    width = CountingParameter(name="width", expression="10 mm")
    width.entityToken = "tok_width"
    metadata = CountingParameter(name=BP.METADATA_PARAMETER_NAME, expression="0")
    metadata.entityToken = "tok_meta"
    design = _design_with_user_params([width, metadata])

    with patch.object(BP, "_design", return_value=design), \
         patch.object(BP, "_persist_document_order_snapshot", return_value=None), \
         patch.object(BP, "_read_metadata_parameter_payload", return_value={"ok": False, "status": BP._metadata_status("none", True), "payload": None, "parameter": None}):
        rows = BP._collect_user_parameters({"parameters": {}, "groupUi": {"order": [], "collapsed": {}}})

    assert [row["name"] for row in rows] == ["width"]


def test_refresh_does_not_create_metadata_parameter():
    width = CountingParameter(name="width", expression="10 mm")
    width.entityToken = "tok_width"
    design = _design_with_user_params([width])

    with patch.object(BP, "_design", return_value=design), \
         patch.object(BP, "_active_document_info", return_value={"id": "doc", "name": "Doc"}), \
         patch.object(BP, "_read_document_order_state", return_value={"parameters": {}, "groupUi": {"order": [], "collapsed": {}}}), \
         patch.object(BP, "_write_document_order_state", return_value=None), \
         patch.object(BP, "_collect_all_parameter_names", return_value=["width"]), \
         patch.object(BP, "_load_text_tuner_state", return_value={}), \
         patch.object(BP, "_build_update_info_payload", return_value={}):
        BP._current_state_payload(settings={})

    assert design.userParameters.itemByName(BP.METADATA_PARAMETER_NAME) is None


def test_set_parameter_group_writes_one_metadata_comment_when_parameter_exists():
    width = CountingParameter(name="width", expression="10 mm")
    width.entityToken = "tok_width"
    metadata = CountingParameter(name=BP.METADATA_PARAMETER_NAME, expression="0")
    metadata.entityToken = "tok_meta"
    metadata.comment = BP._encode_metadata_comment({
        "s": 1,
        "r": 1,
        "t": 100,
        "w": "writer",
        "wv": "0.9.8",
        "g": [],
        "p": [["tok_width", -1]],
    })
    metadata.comment_write_count = 0
    design = _design_with_user_params([width, metadata])

    with patch.object(BP, "_require_design", return_value=design), \
         patch.object(BP, "_design", return_value=design), \
         patch.object(BP, "_find_user_parameter_by_token", return_value=width), \
         patch.object(BP, "_read_document_order_state", return_value={"parameters": {}, "groupUi": {"order": [], "collapsed": {}}}), \
         patch.object(BP, "_write_document_order_state", return_value=None):
        BP._set_parameter_group({"key": "tok_width", "group": "Dims"})

    assert metadata.comment_write_count == 1
    decoded = BP._decode_metadata_comment(metadata.comment)
    assert decoded["payload"]["g"] == ["Dims"]
    assert decoded["payload"]["p"] == [["tok_width", 0]]


def test_valid_metadata_parameter_overrides_local_json_group_on_collect():
    width = CountingParameter(name="width", expression="10 mm")
    width.entityToken = "tok_width"
    metadata = CountingParameter(name=BP.METADATA_PARAMETER_NAME, expression="0")
    metadata.entityToken = "tok_meta"
    metadata.comment = BP._encode_metadata_comment({
        "s": 1,
        "r": 5,
        "t": 500,
        "w": "writer",
        "wv": "0.9.8",
        "g": ["FusionDims"],
        "p": [["tok_width", 0]],
    })
    design = _design_with_user_params([width, metadata])
    order_state = {
        "parameters": {
            "tok_width": {
                "order": 0,
                "name": "width",
                "current_expression": "10 mm",
                "previous_expression": "",
                "current_value": "10 mm",
                "previous_value": "",
                "group": "LocalDims",
                BP.METADATA_CHANGED_AT_RECORD_KEY: 999,
                BP.METADATA_REVISION_RECORD_KEY: 99,
                BP.METADATA_WRITER_ID_RECORD_KEY: "local",
                BP.METADATA_WRITER_VERSION_RECORD_KEY: "0.1.0",
            }
        },
        "groupUi": {"order": [], "collapsed": {}},
    }

    with patch.object(BP, "_design", return_value=design), \
         patch.object(BP, "_write_document_order_state", return_value=None), \
         patch.object(BP, "_persist_document_order_snapshot", return_value=None):
        rows = BP._collect_user_parameters(order_state)

    assert rows[0]["group"] == "FusionDims"


def test_save_parameter_order_writes_one_metadata_comment():
    width = CountingParameter(name="width", expression="10 mm")
    width.entityToken = "tok_width"
    height = CountingParameter(name="height", expression="20 mm")
    height.entityToken = "tok_height"
    metadata = CountingParameter(name=BP.METADATA_PARAMETER_NAME, expression="0")
    metadata.entityToken = "tok_meta"
    metadata.comment = BP._encode_metadata_comment({
        "s": 1,
        "r": 1,
        "t": 100,
        "w": "writer",
        "wv": "0.9.8",
        "g": [],
        "p": [["tok_width", -1], ["tok_height", -1]],
    })
    metadata.comment_write_count = 0
    design = _design_with_user_params([width, height, metadata])

    with patch.object(BP, "_require_design", return_value=design), \
         patch.object(BP, "_design", return_value=design), \
         patch.object(BP, "_read_document_order_state", return_value={"parameters": {}, "groupUi": {"order": [], "collapsed": {}}}), \
         patch.object(BP, "_write_document_order_state", return_value=None):
        BP._save_parameter_order({"keys": ["tok_height", "tok_width"]})

    assert metadata.comment_write_count == 1
    decoded = BP._decode_metadata_comment(metadata.comment)
    assert decoded["payload"]["p"] == [["tok_height", -1], ["tok_width", -1]]


def test_debug_json_to_fusion_writes_metadata_parameter_once():
    width = CountingParameter(name="width", expression="10 mm")
    width.entityToken = "tok_width"
    metadata = CountingParameter(name=BP.METADATA_PARAMETER_NAME, expression="0")
    metadata.entityToken = "tok_meta"
    metadata.comment_write_count = 0
    design = _design_with_user_params([width, metadata])
    order_state = {
        "documentId": "doc",
        "documentName": "Doc",
        "parameters": {
            "tok_width": {
                "order": 0,
                "name": "width",
                "current_expression": "10 mm",
                "previous_expression": "",
                "current_value": "10 mm",
                "previous_value": "",
                "group": "Dims",
                BP.METADATA_CHANGED_AT_RECORD_KEY: 123,
                BP.METADATA_REVISION_RECORD_KEY: 4,
                BP.METADATA_WRITER_ID_RECORD_KEY: "local",
                BP.METADATA_WRITER_VERSION_RECORD_KEY: "0.1.0",
            }
        },
        "groupUi": {"order": ["u:dims"], "collapsed": {}},
    }

    with patch.object(BP, "_require_design", return_value=design), \
         patch.object(BP, "_design", return_value=design), \
         patch.object(BP, "_read_document_order_state", return_value=order_state), \
         patch.object(BP, "_write_document_order_state", return_value=None):
        result = BP._sync_metadata_json_to_fusion()

    assert result["direction"] == "json_to_metadata_parameter"
    assert result["writeTiming"]["totalMs"] >= 0
    assert metadata.comment_write_count == 1
    decoded = BP._decode_metadata_comment(metadata.comment)
    assert decoded["payload"]["g"] == ["Dims"]


def test_debug_fusion_to_json_reads_metadata_parameter_and_updates_cache():
    width = CountingParameter(name="width", expression="10 mm")
    width.entityToken = "tok_width"
    metadata = CountingParameter(name=BP.METADATA_PARAMETER_NAME, expression="0")
    metadata.entityToken = "tok_meta"
    metadata.comment = BP._encode_metadata_comment({
        "s": 1,
        "r": 6,
        "t": 600,
        "w": "writer",
        "wv": "0.9.8",
        "g": ["Dims"],
        "go": ["u:dims"],
        "p": [["tok_width", 0]],
    })
    design = _design_with_user_params([width, metadata])

    with patch.object(BP, "_require_design", return_value=design), \
         patch.object(BP, "_active_document_info", return_value={"id": "doc", "name": "Doc"}), \
         patch.object(BP, "_read_document_order_state", return_value={"parameters": {}, "groupUi": {"order": [], "collapsed": {}}}), \
         patch.object(BP, "_write_document_order_state") as write_state:
        result = BP._sync_metadata_fusion_to_json()

    assert result["direction"] == "metadata_parameter_to_json"
    assert result["readTiming"]["totalMs"] >= 0
    next_state = write_state.call_args.args[0]
    assert next_state["parameters"]["tok_width"]["group"] == "Dims"
    assert next_state["groupUi"]["order"] == ["u:dims"]


def test_legacy_parameter_attrs_migrate_once_to_metadata_parameter_and_are_cleaned():
    width = CountingParameter(name="width", expression="10 mm")
    width.entityToken = "tok_width"
    width.attributes = AttributeCollection({
        (BP.ATTRIBUTE_NAMESPACE, BP.ATTRIBUTE_PARAMETER_GROUP_NAME): "Dims",
        (BP.ATTRIBUTE_NAMESPACE, BP.ATTRIBUTE_METADATA_CHANGED_AT_NAME): "123",
        (BP.ATTRIBUTE_NAMESPACE, BP.ATTRIBUTE_METADATA_REVISION_NAME): "4",
        (BP.ATTRIBUTE_NAMESPACE, BP.ATTRIBUTE_METADATA_WRITER_ID_NAME): "legacy-writer",
        (BP.ATTRIBUTE_NAMESPACE, BP.ATTRIBUTE_METADATA_WRITER_VERSION_NAME): "0.1.0",
    })
    design = _design_with_user_params([width])
    order_state = {"parameters": {}, "groupUi": {"order": [], "collapsed": {}}}

    with patch.object(BP, "_design", return_value=design), \
         patch.object(BP, "_read_document_order_state", return_value=order_state), \
         patch.object(BP, "_write_document_order_state", return_value=None):
        model = BP._metadata_model_for_current_document(design, order_state)

    metadata = design.userParameters.itemByName(BP.METADATA_PARAMETER_NAME)
    assert metadata is not None
    assert model["groupsByToken"] == {"tok_width": "Dims"}
    decoded = BP._decode_metadata_comment(metadata.comment)
    assert decoded["payload"]["g"] == ["Dims"]
    assert width.attributes.itemByName(BP.ATTRIBUTE_NAMESPACE, BP.ATTRIBUTE_PARAMETER_GROUP_NAME).deleted is True
