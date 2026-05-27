"""Acceptance tests for the toposort + cycle-detection helpers."""

from __future__ import annotations

import pytest

from graph import CycleError, detect_cycle, toposort


# Helper — a "topological order is valid" assertion stronger than
# checking a single canonical permutation. We just verify that every
# dep precedes its dependent in the output.


def assert_valid_topo(graph: dict[str, list[str]], order: list[str]) -> None:
    pos = {n: i for i, n in enumerate(order)}
    nodes = set(graph.keys()) | {d for deps in graph.values() for d in deps}
    assert set(order) == nodes
    for dependent, deps in graph.items():
        for dep in deps:
            assert pos[dep] < pos[dependent], (
                f"dep {dep!r} must precede dependent {dependent!r}, "
                f"but order={order}"
            )


# ── basic DAGs ──────────────────────────────────────────────────────


def test_empty_graph():
    assert toposort({}) == []
    assert detect_cycle({}) is None


def test_single_node_no_deps():
    g = {"a": []}
    assert toposort(g) == ["a"]


def test_chain():
    # a -> b -> c (c depends on b, b depends on a)
    g = {"c": ["b"], "b": ["a"]}
    out = toposort(g)
    assert_valid_topo(g, out)
    assert out == ["a", "b", "c"]


def test_independent_nodes():
    g = {"x": [], "y": [], "z": []}
    out = toposort(g)
    assert out == ["x", "y", "z"]  # lexicographic tie-break


def test_diamond():
    # a depends on nothing, b depends on a, c depends on a, d depends on b and c
    g = {"a": [], "b": ["a"], "c": ["a"], "d": ["b", "c"]}
    out = toposort(g)
    assert_valid_topo(g, out)
    assert out[0] == "a"
    assert out[-1] == "d"


def test_implicit_root():
    # "a" appears only as a dep of "b"; no explicit "a": [] key. The
    # implementation must still treat "a" as a node with no deps.
    g = {"b": ["a"]}
    out = toposort(g)
    assert out == ["a", "b"]


def test_multiple_roots_deterministic():
    # "alpha" and "beta" are both roots; tie-break is lexicographic.
    g = {"alpha": [], "beta": [], "gamma": ["alpha"], "delta": ["beta"]}
    out = toposort(g)
    # Roots emit first (alpha < beta), then their dependents.
    assert out[0] == "alpha"
    assert out[1] == "beta"
    assert_valid_topo(g, out)


# ── cycle detection ────────────────────────────────────────────────


def test_self_loop_is_a_cycle():
    g = {"a": ["a"]}
    cyc = detect_cycle(g)
    assert cyc is not None
    assert "a" in cyc


def test_two_node_cycle():
    g = {"a": ["b"], "b": ["a"]}
    cyc = detect_cycle(g)
    assert cyc is not None
    assert set(cyc) == {"a", "b"}


def test_three_node_cycle():
    g = {"a": ["b"], "b": ["c"], "c": ["a"]}
    cyc = detect_cycle(g)
    assert cyc is not None
    assert set(cyc) == {"a", "b", "c"}


def test_no_cycle_in_dag():
    g = {"a": [], "b": ["a"], "c": ["b"], "d": ["a", "c"]}
    assert detect_cycle(g) is None


def test_cycle_disjoint_from_clean_dag():
    # The cycle is in {x, y}; the rest is a clean DAG.
    g = {"a": [], "b": ["a"], "x": ["y"], "y": ["x"]}
    cyc = detect_cycle(g)
    assert cyc is not None
    assert set(cyc) == {"x", "y"}


# ── toposort raises on cycles ──────────────────────────────────────


def test_toposort_raises_on_cycle():
    g = {"a": ["b"], "b": ["a"]}
    with pytest.raises(CycleError) as exc:
        toposort(g)
    assert set(exc.value.cycle) == {"a", "b"}


def test_toposort_raises_on_self_loop():
    g = {"a": ["a"]}
    with pytest.raises(CycleError):
        toposort(g)


# ── stability ───────────────────────────────────────────────────────


def test_repeat_yields_identical_order():
    g = {
        "a": [],
        "b": ["a"],
        "c": ["a"],
        "d": ["b", "c"],
        "e": ["d"],
        "f": [],
        "g": ["f", "e"],
    }
    o1 = toposort(g)
    o2 = toposort(g)
    o3 = toposort(g)
    assert o1 == o2 == o3
    assert_valid_topo(g, o1)


def test_larger_graph():
    # 20-node DAG; just check the result is a valid topological sort.
    g = {
        "n01": [],
        "n02": ["n01"],
        "n03": ["n01"],
        "n04": ["n02"],
        "n05": ["n02", "n03"],
        "n06": ["n03"],
        "n07": ["n04", "n05"],
        "n08": ["n05"],
        "n09": ["n06", "n08"],
        "n10": ["n07", "n08"],
        "n11": ["n09"],
        "n12": ["n10", "n11"],
        "n13": ["n10"],
        "n14": ["n11", "n12"],
        "n15": ["n12", "n13"],
        "n16": ["n13"],
        "n17": ["n14", "n15"],
        "n18": ["n15"],
        "n19": ["n16", "n17"],
        "n20": ["n17", "n18", "n19"],
    }
    out = toposort(g)
    assert_valid_topo(g, out)
    assert len(out) == 20
