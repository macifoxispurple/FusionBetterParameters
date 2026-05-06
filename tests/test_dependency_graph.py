"""
test_dependency_graph.py — verify _get_parameter_dependency_graph logic.
"""
import pytest
from unittest.mock import patch, MagicMock
import BetterParameters as BP
from helpers import make_mock_design


def _run_graph(params_spec):
    """Helper: build mock design, patch _design and _collect_all_parameter_names, run graph fn."""
    design = make_mock_design(params_spec)
    # Build user param list for iteration
    param_list = [design.userParameters.itemByName(p["name"]) for p in params_spec]
    design.userParameters.count = len(param_list)
    design.userParameters.item.side_effect = lambda i: param_list[i] if 0 <= i < len(param_list) else None

    known_names = [p["name"] for p in params_spec]

    with patch.object(BP, "_design", return_value=design), \
         patch.object(BP, "_collect_all_parameter_names", return_value=known_names):
        return BP._get_parameter_dependency_graph()


# ---------------------------------------------------------------------------
# Structure
# ---------------------------------------------------------------------------

def test_graph_returns_nodes_and_edges():
    graph = _run_graph([{"name": "width", "expression": "10 mm"}])
    assert "nodes" in graph
    assert "edges" in graph


def test_graph_nodes_are_list():
    graph = _run_graph([{"name": "width", "expression": "10 mm"}])
    assert isinstance(graph["nodes"], list)


def test_graph_edges_are_list():
    graph = _run_graph([{"name": "width", "expression": "10 mm"}])
    assert isinstance(graph["edges"], list)


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------

def test_graph_node_contains_name_and_expression():
    graph = _run_graph([{"name": "width", "expression": "10 mm"}])
    node = graph["nodes"][0]
    assert node["name"] == "width"
    assert node["expression"] == "10 mm"


def test_graph_node_count_matches_param_count():
    params = [
        {"name": "a", "expression": "1 mm"},
        {"name": "b", "expression": "2 mm"},
        {"name": "c", "expression": "3 mm"},
    ]
    graph = _run_graph(params)
    assert len(graph["nodes"]) == 3


def test_graph_empty_when_no_params():
    design = make_mock_design([])
    design.userParameters.count = 0
    design.userParameters.item.side_effect = lambda i: None
    with patch.object(BP, "_design", return_value=design), \
         patch.object(BP, "_collect_all_parameter_names", return_value=[]):
        graph = BP._get_parameter_dependency_graph()
    assert graph["nodes"] == []
    assert graph["edges"] == []


# ---------------------------------------------------------------------------
# Edges
# ---------------------------------------------------------------------------

def test_graph_edge_from_expression_reference():
    params = [
        {"name": "width", "expression": "10 mm"},
        {"name": "height", "expression": "width * 2"},
    ]
    graph = _run_graph(params)
    assert {"from": "height", "to": "width"} in graph["edges"]


def test_graph_no_self_edges():
    params = [{"name": "width", "expression": "width + 1"}]
    graph = _run_graph(params)
    # width referencing itself should not produce an edge
    assert not any(e["from"] == "width" and e["to"] == "width" for e in graph["edges"])


def test_graph_no_edges_for_unknown_tokens():
    params = [{"name": "width", "expression": "unknownFn + 5"}]
    # 'unknownFn' is not a known parameter name
    graph = _run_graph(params)
    assert graph["edges"] == []


def test_graph_multiple_references_in_one_expression():
    params = [
        {"name": "a", "expression": "1 mm"},
        {"name": "b", "expression": "1 mm"},
        {"name": "c", "expression": "a + b"},
    ]
    graph = _run_graph(params)
    edge_pairs = {(e["from"], e["to"]) for e in graph["edges"]}
    assert ("c", "a") in edge_pairs
    assert ("c", "b") in edge_pairs


def test_graph_edge_shape():
    params = [
        {"name": "depth", "expression": "5 mm"},
        {"name": "volume", "expression": "depth * 3"},
    ]
    graph = _run_graph(params)
    edge = graph["edges"][0]
    assert "from" in edge
    assert "to" in edge


def test_graph_no_edges_when_no_references():
    params = [
        {"name": "a", "expression": "1 mm"},
        {"name": "b", "expression": "2 mm"},
    ]
    graph = _run_graph(params)
    assert graph["edges"] == []
