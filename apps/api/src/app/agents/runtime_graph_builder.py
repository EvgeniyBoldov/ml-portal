from __future__ import annotations

from typing import Dict, Optional

from app.agents.contracts import OperationCredentialContext, ResolvedOperation
from app.agents.runtime_graph import (
    OperationExecutionBinding,
    OperationRuntimeContext,
    RuntimeExecutionGraph,
)


class RuntimeExecutionGraphBuilder:
    """Builds typed runtime execution graph from resolved operations."""

    def __init__(self) -> None:
        self._graph = RuntimeExecutionGraph()

    def add_operation(
        self,
        *,
        operation: ResolvedOperation,
        context_payload: Dict[str, object],
        credential: Optional[OperationCredentialContext],
    ) -> None:
        context = OperationRuntimeContext.model_validate(context_payload)
        binding = OperationExecutionBinding(
            operation_slug=operation.operation_slug,
            target=operation.target,
            context=context,
            credential=credential,
        )
        self._graph.add(binding)

    def build(self) -> RuntimeExecutionGraph:
        return self._graph

