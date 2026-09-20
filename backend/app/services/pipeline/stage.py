"""Stage protocol interface for all pipeline stages."""
from typing import Protocol, runtime_checkable

from app.services.pipeline.context import PipelineContext
from app.services.pipeline.result import StageResult


@runtime_checkable
class PipelineStage(Protocol):
    """Protocol defining the interface for an executable pipeline stage."""
    name: str

    def run(self, context: PipelineContext) -> StageResult:
        """Execute the stage against the provided context and return a structured result."""
        ...
