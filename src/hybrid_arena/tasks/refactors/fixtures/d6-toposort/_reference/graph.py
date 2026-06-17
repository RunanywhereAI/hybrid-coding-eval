"""Reference toposort + cycle detection.

Kahn's algorithm with deterministic tie-breaking; DFS-based cycle
detection for ``detect_cycle``.
"""

from __future__ import annotations

import heapq


class CycleError(ValueError):
    def __init__(self, cycle: list[str]) -> None:
        super().__init__(f"cycle: {' -> '.join(cycle)}")
        self.cycle = cycle


def _all_nodes(graph: dict[str, list[str]]) -> set[str]:
    nodes: set[str] = set(graph.keys())
    for deps in graph.values():
        nodes.update(deps)
    return nodes


def toposort(graph: dict[str, list[str]]) -> list[str]:
    nodes = _all_nodes(graph)
    # in_degree[node] = number of unresolved deps for node.
    in_deg: dict[str, int] = dict.fromkeys(nodes, 0)
    # forward adjacency: dep -> list of dependents (so when dep is
    # emitted we can decrement its dependents' in_deg).
    forward: dict[str, list[str]] = {n: [] for n in nodes}
    for dependent, deps in graph.items():
        for dep in deps:
            forward[dep].append(dependent)
            in_deg[dependent] += 1
    # Kahn's with a min-heap to enforce lexicographic tie-break.
    ready: list[str] = [n for n, d in in_deg.items() if d == 0]
    heapq.heapify(ready)
    out: list[str] = []
    while ready:
        n = heapq.heappop(ready)
        out.append(n)
        for nxt in sorted(forward[n]):  # sorted for determinism
            in_deg[nxt] -= 1
            if in_deg[nxt] == 0:
                heapq.heappush(ready, nxt)
    if len(out) != len(nodes):
        cycle = detect_cycle(graph) or sorted(n for n in nodes if in_deg[n] > 0)
        raise CycleError(cycle)
    return out


def detect_cycle(graph: dict[str, list[str]]) -> list[str] | None:
    nodes = _all_nodes(graph)
    # DFS with WHITE/GRAY/BLACK colouring; record path to extract cycle.
    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = dict.fromkeys(nodes, WHITE)
    parent: dict[str, str | None] = dict.fromkeys(nodes, None)

    def dfs(start: str) -> list[str] | None:
        stack: list[tuple[str, int]] = [(start, 0)]
        while stack:
            node, idx = stack[-1]
            if idx == 0:
                color[node] = GRAY
            deps = sorted(graph.get(node, []))
            if idx >= len(deps):
                color[node] = BLACK
                stack.pop()
                continue
            stack[-1] = (node, idx + 1)
            dep = deps[idx]
            if color[dep] == GRAY:
                cycle = [dep]
                cur = node
                while cur is not None and cur != dep:
                    cycle.append(cur)
                    cur = parent[cur]
                cycle.reverse()
                return cycle
            if color[dep] == WHITE:
                parent[dep] = node
                stack.append((dep, 0))
        return None

    for n in sorted(nodes):
        if color[n] == WHITE:
            result = dfs(n)
            if result is not None:
                return result
    return None
