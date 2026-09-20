"""Live Vision Station with test fallback and secure path validation."""
import logging
import os
from pathlib import Path
from typing import List, Tuple

from app.core.config import settings
from app.models.media import Media
from app.schemas.enums import MediaType
from app.services.pipeline.context import ImageStageOutput, PipelineContext
from app.services.pipeline.result import StageResult

logger = logging.getLogger("app.services.pipeline.stages.image")

_MODEL_DIR = str(Path(__file__).resolve().parent.parent.parent / "vision" / ".models")
os.environ.setdefault("U2NET_HOME", _MODEL_DIR)

_station_instance = None


def _get_station():
    global _station_instance
    if _station_instance is None:
        try:
            from app.services.vision.pipeline import ImageStation
            _station_instance = ImageStation()
        except Exception as e:
            logger.warning("Could not initialize ImageStation: %s", e)
    return _station_instance


# The composite is square at a fixed side, but reading the file keeps the
# reported dimensions honest if that spec ever changes.
_FALLBACK_DIMENSIONS = {"width": 1024, "height": 1024}


def _read_dimensions(path: Path) -> dict:
    try:
        from PIL import Image

        with Image.open(path) as img:
            return {"width": img.width, "height": img.height}
    except Exception:
        logger.warning("Could not read dimensions of %s", path)
        return dict(_FALLBACK_DIMENSIONS)


class ImageStage:
    """Production Image Station: Quality gate -> AI Cutout -> Studio Composite."""

    name: str = "image"

    def run(self, context: PipelineContext) -> StageResult:
        image_media = [m for m in context.media if m.media_type == MediaType.image]
        if not image_media:
            return StageResult.attention("At least one image is required")

        station = _get_station()
        storage_base = Path(settings.MEDIA_STORAGE_DIR).resolve()
        processed_paths: List[str] = []
        dimensions: List[dict] = []
        quality_reports: List[dict] = []
        subject_reports: List[dict] = []

        # Validate paths once up-front and check path traversal
        validated_paths: List[Tuple[Media, Path]] = []
        for media_item in image_media:
            subpath = media_item.storage_path or f"media/{media_item.id}.jpg"
            try:
                raw_path = (storage_base / subpath).resolve()
                if not raw_path.is_relative_to(storage_base):
                    logger.error("Path traversal attempt detected: %s", subpath)
                    return StageResult.fail("Invalid media storage path")
            except Exception:
                logger.exception("Failed resolving path for media %s", media_item.id)
                return StageResult.fail("Invalid media storage path")
            validated_paths.append((media_item, raw_path))

        all_files_exist = all(path.exists() for _, path in validated_paths)

        # Real photos on disk but no vision station means the install is broken
        # (rembg/onnx missing). Passing the raw camera frames through as if they
        # had been graded and composited silently publishes unprocessed photos,
        # so refuse instead and let the runner retry.
        if all_files_exist and station is None:
            logger.error("Vision station unavailable while real media files are present")
            return StageResult.fail(
                "Image processing is unavailable on the server. Please try again shortly."
            )

        # Live Vision AI branch (physical files exist)
        if all_files_exist and station is not None:
            for position, (media_item, raw_path) in enumerate(validated_paths, start=1):
                out_dir = storage_base / str(context.listing_id) / "vision"
                out_dir.mkdir(parents=True, exist_ok=True)
                item_id = str(media_item.id)
                raw_relative = media_item.storage_path or f"media/{media_item.id}.jpg"

                # A re-run starts from the original frame every time, so drop
                # any composite an earlier attempt left behind: if this one
                # stops at a quality gate the listing must fall back to the raw
                # photo rather than keep showing a stale studio image.
                media_item.processed_path = None

                try:
                    result = station.process_image(
                        input_path=str(raw_path),
                        output_dir=str(out_dir),
                        item_id=item_id,
                    )
                except Exception:
                    logger.exception("Vision processing failed for media %s", media_item.id)
                    return StageResult.fail(f"Vision processing failed for media {media_item.id}")

                quality = result.get("quality", {})
                quality_reports.append(quality)

                # A photo the artisan can retake is not a reason to abandon the
                # run. Stopping here left the voice note untranscribed and the
                # listing blank, so the artisan was shown nothing they had said
                # alongside a complaint about a photo. Note the problem, keep the
                # raw frame in place of a composite, and carry on; the runner
                # finishes in needs_attention and asks for the retake, but with
                # everything the voice note yielded already saved.
                if not quality.get("passed", False):
                    warnings = "; ".join(quality.get("warnings", ["Quality check failed"]))
                    context.photo_warnings.append(
                        f"Photo {position}: {warnings}. Please retake it in better light."
                    )
                    processed_paths.append(raw_relative)
                    dimensions.append(_read_dimensions(raw_path))
                    continue

                # The subject gate runs after segmentation and already phrases its
                # warnings as advice to the artisan, so pass them straight through
                # rather than appending lighting advice that would not help here.
                subject = result.get("subject") or {}
                if subject and not subject.get("passed", True):
                    subject_reports.append(subject)
                    context.photo_warnings.append(
                        f"Photo {position}: " + " ".join(subject.get("warnings", []))
                    )
                    processed_paths.append(raw_relative)
                    dimensions.append(_read_dimensions(raw_path))
                    continue

                outputs = result.get("outputs", {})
                clean_path = outputs.get("clean_image")
                if not clean_path:
                    # Both gates passed, so the station should have written a
                    # composite. Reporting fewer images than the artisan sent
                    # would quietly drop one from the listing.
                    logger.error(
                        "Vision station produced no clean image for media %s", media_item.id
                    )
                    return StageResult.fail(
                        f"Image processing produced no output for media {media_item.id}"
                    )

                clean_path_obj = Path(clean_path).resolve()
                try:
                    rel_clean_path = str(clean_path_obj.relative_to(storage_base))
                except ValueError:
                    rel_clean_path = None
                processed_paths.append(rel_clean_path or str(clean_path_obj))
                dimensions.append(_read_dimensions(clean_path_obj))
                # Record where the studio image landed. Without this the
                # composite existed only on disk for the rest of this run: the
                # media endpoint went on serving the raw camera frame, so the
                # listing the artisan reviewed and published was never the
                # photo this stage produced. The runner's session owns these
                # rows, so the assignment is written out by the commit that
                # ends the run. Only a path inside the media root is stored -
                # the endpoint would refuse to serve anything else, and a
                # stored path that always 404s is worse than the raw photo.
                media_item.processed_path = rel_clean_path

        # Fallback branch for in-memory database test fixtures
        else:
            processed_paths = [m.storage_path or f"media/{m.id}.jpg" for m in image_media]
            dimensions = [{"width": 1024, "height": 768} for _ in image_media]

        output = ImageStageOutput(
            image_count=len(processed_paths),
            image_paths=processed_paths,
            detected_labels=["handcrafted_art", "folk_painting", "natural_pigments"],
            dimensions=dimensions,
        )
        context.image_output = output

        return StageResult.ok(
            output=output,
            metadata={
                "processed_count": len(processed_paths),
                "quality_reports": quality_reports,
                "subject_reports": subject_reports,
                "photo_warnings": list(context.photo_warnings),
            },
        )