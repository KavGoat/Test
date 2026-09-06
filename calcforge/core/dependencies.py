"""Document-level calculation dependency tracking.

The spreadsheet already orders formula cells internally. This graph sits one
level above it: calculation regions and tables are nodes, and variable names
are the edges between them. It deliberately over-invalidates when a name is
redefined; recalculating an extra downstream node is safe, while retaining a
stale engineering result is not.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DependencyNode:
    uid: str
    inputs: frozenset[str]
    outputs: frozenset[str]


class DependencyGraph:
    """Ordered calculation/table nodes indexed by the variables they read."""

    def __init__(self):
        self.nodes: dict[str, DependencyNode] = {}
        self.order: list[str] = []
        self.dependents_by_variable: dict[str, set[str]] = {}
        self.producers_by_variable: dict[str, set[str]] = {}

    def add(self, uid: str, inputs=(), outputs=()) -> None:
        node = DependencyNode(uid, frozenset(inputs), frozenset(outputs))
        self.nodes[uid] = node
        self.order.append(uid)
        for name in node.inputs:
            self.dependents_by_variable.setdefault(name, set()).add(uid)
        for name in node.outputs:
            self.producers_by_variable.setdefault(name, set()).add(uid)

    def affected(self, changed_uids) -> set[str]:
        """Return changed nodes and their transitive downstream consumers."""
        affected = set(changed_uids)
        changed_names: set[str] = set()
        for uid in self.order:
            node = self.nodes[uid]
            if uid in affected:
                changed_names.update(node.outputs)
            elif node.inputs & changed_names:
                affected.add(uid)
                changed_names.update(node.outputs)
        return affected

    def same_structure(self, other: "DependencyGraph | None") -> bool:
        if other is None or self.order != other.order:
            return False
        return all(self.nodes[uid].outputs == other.nodes[uid].outputs
                   for uid in self.order)
