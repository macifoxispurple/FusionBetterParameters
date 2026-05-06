import BetterParameters as bp


class _FakeParam:
    def __init__(self, design, name, expression=""):
        self._design = design
        self.name = name
        self.expression = expression

    def deleteMe(self):
        refs = self._design.refs_by_name.get(self.name, set())
        for ref_name in refs:
            if ref_name in self._design.params_by_name:
                raise RuntimeError(f'Cannot delete "{self.name}"; still referenced by "{ref_name}".')
        self._design.params_by_name.pop(self.name, None)


class _FakeUserParameters:
    def __init__(self, design):
        self._design = design

    def itemByName(self, name):
        return self._design.params_by_name.get(name)


class _FakeDesign:
    def __init__(self, rows):
        self.params_by_name = {}
        self.refs_by_name = {}
        for row in rows:
            name = str(row.get("name") or "")
            expr = str(row.get("expression") or "")
            self.params_by_name[name] = _FakeParam(self, name, expr)
            refs = set()
            for token in bp.EXPRESSION_TOKEN_PATTERN.findall(expr):
                if token != name:
                    refs.add(token)
            self.refs_by_name[name] = refs
        self.userParameters = _FakeUserParameters(self)


def test_delete_batch_dependency_order_then_success(monkeypatch):
    design = _FakeDesign(
        [
            {"name": "A", "expression": "B + 1 mm"},
            {"name": "B", "expression": "5 mm"},
        ]
    )
    monkeypatch.setattr(bp, "_require_design", lambda: design)
    monkeypatch.setattr(bp, "_find_user_parameter_by_token", lambda _d, token: design.params_by_name.get(token))
    monkeypatch.setattr(bp, "_parameter_entity_token", lambda p: p.name)

    result = bp._delete_parameters_batch({"keys": ["B", "A"]})
    assert result["ok"] is True
    assert result["deletedCount"] == 2
    assert result["failedCount"] == 0
    assert result["failedDetails"] == []


def test_delete_batch_multi_pass_reports_remaining_failures(monkeypatch):
    design = _FakeDesign(
        [
            {"name": "A", "expression": "B + 1 mm"},
            {"name": "B", "expression": "A + 1 mm"},
        ]
    )
    monkeypatch.setattr(bp, "_require_design", lambda: design)
    monkeypatch.setattr(bp, "_find_user_parameter_by_token", lambda _d, token: design.params_by_name.get(token))
    monkeypatch.setattr(bp, "_parameter_entity_token", lambda p: p.name)

    result = bp._delete_parameters_batch({"keys": ["A", "B"]})
    assert result["ok"] is True
    assert result["deletedCount"] == 0
    assert result["failedCount"] == 2
    assert len(result["failedDetails"]) == 2
    assert "could not be deleted" in str(result.get("message", "")).lower()
