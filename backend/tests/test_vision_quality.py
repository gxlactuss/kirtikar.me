"""Quality gate and compositing tests for the Vision Station.

These cover the judgement calls the gate makes on real artisan photos: dark wood
and pale textiles are ordinary subjects, not defects, while genuinely unusable
photos must still be rejected before any GPU work happens.
"""
from pathlib import Path

import cv2
import numpy as np
import pytest
from PIL import Image

from app.services.vision.pipeline import ImageStation

CRAFT_IMAGES = Path(__file__).resolve().parents[2] / "app" / "assets" / "images" / "crafts"


def _sample(name: str):
    path = CRAFT_IMAGES / f"{name}.jpg"
    if not path.is_file():
        pytest.skip(f"sample craft photo not available: {path}")
    return cv2.imread(str(path))


@pytest.mark.parametrize(
    "name",
    ["pottery", "jewellery", "woodwork", "painting", "metalwork", "weaving", "leather"],
)
def test_real_craft_photos_pass_the_quality_gate(name):
    """Ordinary craft photos must not be bounced back to the artisan."""
    report = ImageStation.assess_quality(_sample(name))
    assert report["passed"], report["warnings"]


def test_dark_subject_on_light_background_is_not_called_overexposed():
    """A dark carving against a bright wall reads as dark, not blown out.

    Otsu puts the wall in the bright cluster, so measuring that cluster used to
    report the backdrop's brightness and reject the photo.
    """
    report = ImageStation.assess_quality(_sample("woodwork"))
    assert not report["is_too_bright"]
    assert not report["is_too_dark"]


def test_blurry_photo_is_rejected():
    blurred = cv2.GaussianBlur(_sample("pottery"), (51, 51), 0)
    report = ImageStation.assess_quality(blurred)
    assert report["passed"] is False
    assert report["is_blurry"] is True


def test_blown_out_photo_is_rejected():
    blown = np.clip(_sample("pottery").astype(np.float32) * 3.2, 0, 255).astype(np.uint8)
    report = ImageStation.assess_quality(blown)
    assert report["passed"] is False
    assert report["is_too_bright"] is True
    assert report["clipped_fraction"] > 0.25


def test_crushed_photo_is_rejected():
    crushed = np.clip(_sample("pottery").astype(np.float32) * 0.08, 0, 255).astype(np.uint8)
    report = ImageStation.assess_quality(crushed)
    assert report["passed"] is False
    assert report["is_too_dark"] is True


def test_unreadable_image_path_is_rejected_with_a_warning():
    report = ImageStation.assess_quality("/nonexistent/photo.jpg")
    assert report["passed"] is False
    assert report["warnings"]


def _cutout(alpha: np.ndarray) -> Image.Image:
    rgb = np.zeros((*alpha.shape, 4), dtype=np.uint8)
    rgb[..., 0] = 200  # a distinctly non-white subject colour
    rgb[..., 3] = alpha
    return Image.fromarray(rgb, mode="RGBA")


def test_faint_mask_noise_does_not_shrink_the_subject():
    """A confident blob framed against a faint halo must fill the canvas.

    The halo spans the frame at low alpha; including it in the bounding box is
    what reduced real subjects to a speck in the middle of a white canvas.
    """
    alpha = np.full((400, 400), 30, dtype=np.uint8)  # faint noise everywhere
    alpha[180:220, 180:220] = 255  # the actual subject
    canvas = np.array(ImageStation.composite_to_marketplace_spec(_cutout(alpha), target_size=200))

    subject = (canvas[..., 0] > 150) & (canvas[..., 1] < 100)
    assert subject.mean() > 0.3, "confident subject should dominate the canvas"


def test_low_confidence_pixels_do_not_bleach_the_subject():
    """Partially transparent pixels must not be composited into pale ghosts."""
    alpha = np.full((200, 200), 120, dtype=np.uint8)
    canvas = np.array(ImageStation.composite_to_marketplace_spec(_cutout(alpha), target_size=200))

    centre = canvas[100, 100]
    assert centre[0] > 150, f"subject washed out toward white: {centre}"


def test_empty_mask_yields_a_blank_white_canvas():
    alpha = np.zeros((100, 100), dtype=np.uint8)
    canvas = ImageStation.composite_to_marketplace_spec(_cutout(alpha), target_size=128)
    assert canvas.size == (128, 128)
    assert np.array(canvas).min() == 255


def _mask_cutout(alpha: np.ndarray) -> Image.Image:
    rgba = np.zeros((*alpha.shape, 4), dtype=np.uint8)
    rgba[..., 0] = 200
    rgba[..., 3] = alpha
    return Image.fromarray(rgba, mode="RGBA")


def test_clean_product_cutout_passes_the_subject_gate():
    """One solid, centred object is exactly what the station expects."""
    alpha = np.zeros((400, 400), dtype=np.uint8)
    alpha[80:320, 80:320] = 255
    report = ImageStation.assess_subject(_mask_cutout(alpha))
    assert report["passed"], report["warnings"]


def test_mostly_uncertain_mask_is_rejected_as_indistinct():
    """A hedge-heavy mask composites into a ghost, so refuse it instead.

    This is what a photo of an artisan at work produces: the model cannot decide
    what the product is and returns a faint wash over most of the frame.
    """
    alpha = np.full((400, 400), 90, dtype=np.uint8)  # uncertain everywhere
    alpha[190:210, 190:210] = 255  # a small confident core
    report = ImageStation.assess_subject(_mask_cutout(alpha))
    assert report["passed"] is False
    assert report["is_indistinct"] is True


def test_tiny_subject_is_rejected_with_a_move_closer_hint():
    alpha = np.zeros((400, 400), dtype=np.uint8)
    alpha[195:205, 195:205] = 255  # 0.06% of the frame
    report = ImageStation.assess_subject(_mask_cutout(alpha))
    assert report["passed"] is False
    assert report["is_too_small"] is True
    assert any("closer" in w for w in report["warnings"])


def test_a_thin_ring_is_not_called_too_small():
    """A bangle is mostly hole, so filled area says nothing about its framing.

    Measured by area this ring inks under 2% of the photo and the gate told the
    artisan to move closer to something already spanning half the frame, which
    stopped the run and left the listing blank.
    """
    alpha = np.zeros((480, 480), dtype=np.uint8)
    cv2.circle(alpha, (240, 240), 120, 255, thickness=5)

    report = ImageStation.assess_subject(_mask_cutout(alpha))

    # Under the 3% of filled area the gate used to demand: the whole point.
    assert report["confident_fraction"] < 0.03
    assert report["is_too_small"] is False
    assert report["passed"], report["warnings"]


def test_several_separate_objects_are_rejected():
    """A shop display of many items cannot become one product listing."""
    alpha = np.zeros((400, 400), dtype=np.uint8)
    for x in (40, 160, 280):
        alpha[180:220, x : x + 60] = 255
    report = ImageStation.assess_subject(_mask_cutout(alpha))
    assert report["passed"] is False
    assert report["is_scattered"] is True


def test_empty_mask_is_rejected_rather_than_dividing_by_zero():
    report = ImageStation.assess_subject(_mask_cutout(np.zeros((100, 100), dtype=np.uint8)))
    assert report["passed"] is False
    assert report["uncertainty_ratio"] is None
