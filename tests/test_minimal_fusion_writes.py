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
         patch.object(BP, "_write_document_order_state") as write_local, \
         patch.object(BP, "_set_parameter_metadata_changed_at") as write_fusion_attr:
        BP._persist_document_order_snapshot(rows, previous_state)

    assert write_local.call_count == 1
    assert write_fusion_attr.call_count == 0


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


def test_document_attribute_write_skips_unchanged_value():
    attr = CountingField("same")
    attrs = MagicMock()
    attrs.itemByName.return_value = attr
    owner = MagicMock()
    owner.attributes = attrs

    result = BP._write_document_attribute_with_diagnostics([owner], "ns", "name", "same")

    assert result["ok"] is True
    assert attr.write_count == 0
    assert attrs.add.call_count == 0


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
    older_fusion_payload = {
        "group": "Dims",
        BP.METADATA_CHANGED_AT_RECORD_KEY: 100,
        BP.METADATA_REVISION_RECORD_KEY: 1,
        BP.METADATA_WRITER_ID_RECORD_KEY: "fusion-writer",
        BP.METADATA_WRITER_VERSION_RECORD_KEY: "0.1.0",
    }

    with patch.object(BP, "_design", return_value=design), \
         patch.object(BP, "_parameter_metadata_payload", return_value=older_fusion_payload), \
         patch.object(BP, "_persist_document_order_snapshot", return_value=None), \
         patch.object(BP, "_write_parameter_group_name") as write_fusion_attrs:
        rows = BP._collect_user_parameters(order_state)

    assert len(rows) == 1
    assert rows[0]["group"] == "Dims"
    assert write_fusion_attrs.call_count == 0


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
    newer_blank_fusion_payload = {
        "group": "",
        BP.METADATA_CHANGED_AT_RECORD_KEY: 999,
        BP.METADATA_REVISION_RECORD_KEY: 2,
        BP.METADATA_WRITER_ID_RECORD_KEY: "fusion-writer",
        BP.METADATA_WRITER_VERSION_RECORD_KEY: "0.1.0",
    }

    with patch.object(BP, "_design", return_value=design), \
         patch.object(BP, "_parameter_metadata_payload", return_value=newer_blank_fusion_payload), \
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
