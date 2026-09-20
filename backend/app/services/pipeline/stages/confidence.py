"""Deterministic quality and confidence check stage."""
from typing import Optional

from app.services.pipeline.context import ConfidenceStageOutput, PipelineContext
from app.services.pipeline.result import StageResult


class ConfidenceStage:
    """Deterministic placeholder for confidence scoring and gatekeeping."""
    name: str = "confidence"

    def __init__(self, threshold: float = 0.70, forced_score: Optional[float] = None) -> None:
        self.threshold = threshold
        self.forced_score = forced_score

    def run(self, context: PipelineContext) -> StageResult:
        """Evaluate overall listing completeness and confidence across previous stage outputs."""
        if (
            context.image_output is None
            or context.speech_output is None
            or context.fact_sheet_output is None
            or context.price_output is None
        ):
            return StageResult.attention("Missing prerequisites for confidence assessment")

        score = self.forced_score if self.forced_score is not None else 0.95
        if score < self.threshold:
            return StageResult.attention(
                f"Confidence score {score:.2f} is below required threshold {self.threshold:.2f}",
                metadata={"score": score, "threshold": self.threshold},
            )

        output = ConfidenceStageOutput(
            overall_score=score,
            is_confident=True,
            confidence_by_stage={
                "image": 0.96,
                "speech": 0.94,
                "fact_sheet": 0.95,
                "price": context.price_output.confidence,
            },
        )
        context.confidence_output = output
        return StageResult.ok(output=output, metadata={"overall_score": score})
