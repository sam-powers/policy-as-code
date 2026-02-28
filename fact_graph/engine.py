"""
Fact Graph DAG resolution engine.

Resolves FactNodes in dependency order.  Partial information is handled
gracefully: missing inputs leave downstream facts UNRESOLVED rather than
raising errors.
"""

from __future__ import annotations

import copy
from typing import Any

from .provenance import build_determination
from .schema import (
    Condition,
    ConditionFired,
    ConditionOperator,
    Determination,
    FactGraph,
    FactNode,
    FactStatus,
    FactType,
    FactValue,
    ResolutionTrace,
)


class CycleError(ValueError):
    pass


class ConditionEvaluationError(ValueError):
    pass


class FactGraphEngine:
    """
    DAG resolution engine for a FactGraph.

    Usage:
        engine = FactGraphEngine(graph)
        engine.load_facts({"primary_residence_damaged_by_disaster": True, ...})
        resolved_graph = engine.resolve()
        determination = engine.get_determination()
    """

    def __init__(self, graph: FactGraph) -> None:
        # Work on a deep copy so the original graph spec stays immutable.
        self._graph = graph
        self._nodes: dict[str, FactNode] = {
            k: v.model_copy(deep=True) for k, v in graph.nodes.items()
        }
        # Maps fact_id → list of ConditionFired (populated during resolve).
        self._conditions_fired: dict[str, list[ConditionFired]] = {}
        # Snapshot of inputs provided via load_facts.
        self._input_facts: dict[str, FactValue] = {}
        # Topological order (leaf → terminal).
        self._topo_order: list[str] = self._topological_sort()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load_facts(self, inputs: dict[str, Any]) -> None:
        """
        Provide known fact values (e.g. from an applicant intake form).

        Sets matching leaf nodes to RESOLVED with the supplied value, then
        invalidates all downstream derived facts so resolve() re-evaluates them.
        """
        for fact_id, raw_value in inputs.items():
            if fact_id not in self._nodes:
                continue
            node = self._nodes[fact_id]
            node.value = _cast_value(raw_value, node.fact_type)
            node.status = FactStatus.RESOLVED
            self._input_facts[fact_id] = node.value

        # Invalidate all non-input derived nodes so forward-propagation works.
        self._invalidate_derived()

    def resolve(self) -> FactGraph:
        """
        Run a single forward pass in topological order.

        Returns a new FactGraph with updated statuses and values.
        Leaves UNKNOWN/UNRESOLVED facts intact without raising errors.
        """
        self._conditions_fired = {}
        for fact_id in self._topo_order:
            node = self._nodes[fact_id]

            # Leaf/input facts that have already been set — skip.
            if node.status == FactStatus.RESOLVED and not node.dependencies:
                continue

            # Skip facts with no conditions to evaluate (pure inputs not yet provided).
            if not node.conditions:
                continue

            # Check that all dependencies are resolved before attempting evaluation.
            dep_statuses = [self._nodes[d].status for d in node.dependencies if d in self._nodes]
            if any(s in (FactStatus.UNKNOWN, FactStatus.UNRESOLVED) for s in dep_statuses):
                node.status = FactStatus.UNRESOLVED
                continue

            # All dependencies resolved — try conditions in order.
            fired: list[ConditionFired] = []
            resolved_value: FactValue = None
            did_resolve = False

            for i, condition in enumerate(node.conditions):
                result = self._evaluate_condition(condition, node)
                if result is None:
                    # Cannot evaluate (upstream UNRESOLVED) — shouldn't happen here
                    # but guard defensively.
                    node.status = FactStatus.UNRESOLVED
                    break
                # NOTE: bool is a subclass of int in Python, so we must check
                # `result is True` (not `result == True`) for logical operators,
                # and exclude booleans from the arithmetic (int/float) check.
                logical_fired = result is True
                arithmetic_fired = (
                    not isinstance(result, bool)
                    and isinstance(result, (int, float))
                    and _is_arithmetic_op(condition.operator)
                )
                if logical_fired or arithmetic_fired:
                    # Condition fired.
                    if arithmetic_fired:
                        resolved_value = result
                    else:
                        resolved_value = condition.result_value
                    fired.append(
                        ConditionFired(
                            condition_index=i,
                            operator=condition.operator,
                            result_value=resolved_value,
                        )
                    )
                    did_resolve = True
                    break
                # result is False — this condition did not fire; continue to next.

            if did_resolve:
                node.value = resolved_value
                node.status = FactStatus.RESOLVED
                self._conditions_fired[fact_id] = fired
            else:
                # No condition fired; apply defaults.
                if node.fact_type == FactType.BOOLEAN:
                    node.value = False
                    node.status = FactStatus.RESOLVED
                    self._conditions_fired[fact_id] = []
                else:
                    node.status = FactStatus.AMBIGUOUS
                    if not node.ambiguity_notes:
                        node.ambiguity_notes = (
                            "No condition matched; default undefined for non-boolean type."
                        )

        # Return an updated FactGraph snapshot.
        return FactGraph(
            nodes=dict(self._nodes),
            terminal_fact_ids=self._graph.terminal_fact_ids,
            program=self._graph.program,
        )

    def get_determination(self, scenario_label: str | None = None) -> Determination:
        """Build a Determination from the current engine state."""
        return build_determination(
            graph=self._graph,
            node_map=self._nodes,
            conditions_fired_map=self._conditions_fired,
            input_facts=self._input_facts,
            scenario_label=scenario_label,
        )

    def get_trace(self, fact_id: str) -> ResolutionTrace:
        """Build a ResolutionTrace for a specific fact."""
        if fact_id not in self._nodes:
            raise KeyError(f"Fact '{fact_id}' not in graph.")
        node = self._nodes[fact_id]
        dep_snapshots = {d: self._nodes[d] for d in node.dependencies if d in self._nodes}
        fired = self._conditions_fired.get(fact_id, [])
        from .provenance import build_trace
        return build_trace(node, fired, dep_snapshots)

    def get_unresolved_inputs(self) -> list[FactNode]:
        """Return leaf facts (no dependencies) that have not yet been provided."""
        return [
            node
            for node in self._nodes.values()
            if len(node.dependencies) == 0 and node.status == FactStatus.UNKNOWN
        ]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _topological_sort(self) -> list[str]:
        """
        Return fact IDs in topological order (leaves first, terminals last).
        Raises CycleError if the dependency graph contains a cycle.
        """
        WHITE, GRAY, BLACK = 0, 1, 2
        color: dict[str, int] = {fid: WHITE for fid in self._nodes}
        order: list[str] = []

        def dfs(node_id: str, path: list[str]) -> None:
            color[node_id] = GRAY
            node = self._nodes.get(node_id)
            if node:
                for dep_id in node.dependencies:
                    if dep_id not in color:
                        # Dependency references a node not in the graph — skip gracefully.
                        continue
                    if color[dep_id] == GRAY:
                        cycle = path + [dep_id]
                        raise CycleError(
                            f"Cycle detected in fact graph: {' -> '.join(cycle)}"
                        )
                    if color[dep_id] == WHITE:
                        dfs(dep_id, path + [dep_id])
            color[node_id] = BLACK
            order.append(node_id)

        for node_id in list(self._nodes.keys()):
            if color[node_id] == WHITE:
                dfs(node_id, [node_id])

        return order

    def _invalidate_derived(self) -> None:
        """
        Reset all derived facts (those with dependencies) to UNRESOLVED so
        they will be re-evaluated on the next resolve() call.
        """
        for node in self._nodes.values():
            if node.dependencies and node.id not in self._input_facts:
                node.status = FactStatus.UNRESOLVED
                node.value = None

    def _get_operand_value(self, operand: str | Condition) -> FactValue | None:
        """
        Resolve a single operand to a concrete value.

        Returns None if the operand references an UNRESOLVED/UNKNOWN fact.
        """
        if isinstance(operand, str):
            if operand in self._nodes:
                dep = self._nodes[operand]
                if dep.status not in (FactStatus.RESOLVED, FactStatus.AMBIGUOUS):
                    return None
                return dep.value
            # Try to parse as a literal (numeric strings like "0.30").
            try:
                return float(operand)
            except ValueError:
                return operand  # Return as string literal.
        # Nested condition — evaluate recursively (returns bool/numeric or None).
        return self._evaluate_condition(operand, None)

    def _evaluate_condition(
        self, condition: Condition, parent_node: FactNode | None
    ) -> FactValue:
        """
        Evaluate a condition against the current engine state.

        Returns:
          True/False for logical operators.
          A numeric value for arithmetic operators.
          None if any required operand is UNRESOLVED (cannot evaluate yet).
        """
        op = condition.operator

        # --- Arithmetic operators ---
        if op in (ConditionOperator.MULTIPLY, ConditionOperator.SUBTRACT, ConditionOperator.ADD):
            if len(condition.operands) < 2:
                raise ConditionEvaluationError(
                    f"Arithmetic operator {op} requires at least 2 operands."
                )
            values = [self._get_operand_value(o) for o in condition.operands]
            if any(v is None for v in values):
                return None
            nums = [_to_float(v) for v in values]
            if op == ConditionOperator.MULTIPLY:
                result = nums[0]
                for n in nums[1:]:
                    result *= n
                return result
            elif op == ConditionOperator.SUBTRACT:
                result = nums[0]
                for n in nums[1:]:
                    result -= n
                return result
            else:  # ADD
                return sum(nums)

        # --- NOT ---
        if op == ConditionOperator.NOT:
            if len(condition.operands) != 1:
                raise ConditionEvaluationError("NOT operator requires exactly 1 operand.")
            val = self._get_operand_value(condition.operands[0])
            if val is None:
                return None
            return not val

        # --- AND ---
        if op == ConditionOperator.AND:
            has_unresolved = False
            for operand in condition.operands:
                val = self._get_operand_value(operand)
                if val is None:
                    has_unresolved = True
                elif not val:
                    return False  # Short-circuit: one False operand → False.
            if has_unresolved:
                return None
            return True

        # --- OR ---
        if op == ConditionOperator.OR:
            has_unresolved = False
            for operand in condition.operands:
                val = self._get_operand_value(operand)
                if val is None:
                    has_unresolved = True
                elif val:
                    return True  # Short-circuit: one True operand → True.
            if has_unresolved:
                return None
            return False

        # --- Comparison operators ---
        if op in (
            ConditionOperator.EQUALS,
            ConditionOperator.GREATER_THAN,
            ConditionOperator.LESS_THAN,
        ):
            if len(condition.operands) < 2:
                raise ConditionEvaluationError(
                    f"Comparison operator {op} requires 2 operands: [fact_id, literal]."
                )
            fact_val = self._get_operand_value(condition.operands[0])
            if fact_val is None:
                return None
            # operands[1] may be a fact ID (resolved to its value) or a numeric/bool literal.
            literal = self._get_operand_value(condition.operands[1])
            if literal is None:
                return None

            if op == ConditionOperator.EQUALS:
                return fact_val == literal
            if op == ConditionOperator.GREATER_THAN:
                return _to_float(fact_val) > _to_float(literal)
            if op == ConditionOperator.LESS_THAN:
                return _to_float(fact_val) < _to_float(literal)

        # --- IN ---
        if op == ConditionOperator.IN:
            if len(condition.operands) < 2:
                raise ConditionEvaluationError(
                    "IN operator requires at least 2 operands: [fact_id, ...allowed_values]."
                )
            fact_val = self._get_operand_value(condition.operands[0])
            if fact_val is None:
                return None
            allowed = [str(condition.operands[i]) for i in range(1, len(condition.operands))]
            return str(fact_val).lower() in [a.lower() for a in allowed]

        raise ConditionEvaluationError(f"Unknown operator: {op}")


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------


def _is_arithmetic_op(op: ConditionOperator) -> bool:
    return op in (
        ConditionOperator.MULTIPLY,
        ConditionOperator.SUBTRACT,
        ConditionOperator.ADD,
    )


def _to_float(val: FactValue) -> float:
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        return float(val)
    raise ConditionEvaluationError(f"Cannot cast {val!r} to float.")


def _cast_value(raw: Any, fact_type: FactType) -> FactValue:
    """Cast a raw Python value to the appropriate FactValue for a given FactType."""
    if raw is None:
        return None
    if fact_type == FactType.BOOLEAN:
        if isinstance(raw, bool):
            return raw
        if isinstance(raw, str):
            return raw.lower() in ("true", "1", "yes")
        return bool(raw)
    if fact_type == FactType.NUMERIC:
        return float(raw)
    if fact_type == FactType.DATE:
        return str(raw)
    return str(raw)  # CATEGORICAL


def _cast_literal(raw_str: str, parent_node: FactNode | None) -> FactValue:
    """Cast a string literal from condition operands to FactValue."""
    # Try bool.
    if raw_str.lower() in ("true", "false"):
        return raw_str.lower() == "true"
    # Try numeric.
    try:
        return float(raw_str)
    except ValueError:
        pass
    return raw_str
