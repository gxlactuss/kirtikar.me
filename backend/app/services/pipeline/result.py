"""Structured result types for pipeline stages and runner outcomes."""
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional

from app.schemas.enums import ListingState


class StageStatus(str, Enum):
    """Execution status of an individual pipeline stage."""
    success = "success"
    needs_attention = "needs_attention"
    failure = "failure"


@dataclass
class StageResult:
    """Structured result returned by a pipeline stage execution."""
    status: StageStatus
    output: Any = None
    reason: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def ok(cls, output: Any = None, metadata: Optional[Dict[str, Any]] = None) -> "StageResult":
        """Create a successful stage result with optional output data."""
        return cls(
            status=StageStatus.success,
            output=output,
            metadata=metadata or {},
        )

    @classmethod
    def attention(cls, reason: str, metadata: Optional[Dict[str, Any]] = None) -> "StageResult":
        """Create a needs_attention stage result signaling human intervention required."""
        return cls(
            status=StageStatus.needs_attention,
            reason=reason,
            metadata=metadata or {},
        )

    @classmethod
    def fail(cls, reason: str, metadata: Optional[Dict[str, Any]] = None) -> "StageResult":
        """Create a failure stage result eligible for retry."""
        return cls(
            status=StageStatus.failure,
            reason=reason,
            metadata=metadata or {},
        )


@dataclass
class PipelineResult:
    """Overall outcome of a pipeline runner execution for a listing."""
    listing_id: uuid.UUID
    final_state: ListingState
    stage_results: Dict[str, StageResult] = field(default_factory=dict)
    success: bool = True
    reason: Optional[str] = None
