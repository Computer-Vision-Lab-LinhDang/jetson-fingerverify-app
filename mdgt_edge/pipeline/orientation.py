"""Gradient-based fingerprint orientation estimation and deskew.

Uses the structure tensor of Sobel gradients to compute the dominant ridge
orientation, then rotates the image so ridges are aligned to vertical.  Applying
the same normalisation at enroll and identify time makes the embedding
invariant to finger rotation.
"""

from __future__ import annotations

import logging

import cv2
import numpy as np

logger = logging.getLogger(__name__)


def estimate_ridge_angle(
    gray: np.ndarray,
    mask: np.ndarray | None = None,
    ksize: int = 5,
) -> float:
    """Return the rotation angle (degrees) needed to bring ridges to vertical.

    The structure tensor's eigenvector associated with the larger eigenvalue
    points along the image gradient direction (perpendicular to the ridge).
    The ridge direction is therefore ``theta + 90°``; to bring ridges to
    vertical (90°) we rotate the image by ``-theta``.

    Args:
        gray: uint8 grayscale image.
        mask: optional foreground mask (same HxW, non-zero = use).
        ksize: Sobel kernel size.

    Returns:
        Rotation angle in degrees, in ``(-90, 90]``.  Positive = counter-clockwise.
    """
    if gray.ndim == 3:
        gray = cv2.cvtColor(gray, cv2.COLOR_BGR2GRAY)

    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=ksize)
    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=ksize)

    gxx = gx * gx
    gyy = gy * gy
    gxy = gx * gy

    if mask is not None:
        m = (mask > 0).astype(np.float32)
        sum_xx = float((gxx * m).sum())
        sum_yy = float((gyy * m).sum())
        sum_xy = float((gxy * m).sum())
    else:
        sum_xx = float(gxx.sum())
        sum_yy = float(gyy.sum())
        sum_xy = float(gxy.sum())

    # Guard against degenerate (all-zero gradient) inputs
    if abs(sum_xx) + abs(sum_yy) + abs(sum_xy) < 1e-3:
        return 0.0

    theta_rad = 0.5 * float(np.arctan2(2.0 * sum_xy, sum_xx - sum_yy))
    theta_deg = float(np.degrees(theta_rad))
    return -theta_deg


def _foreground_mask(gray: np.ndarray, block: int = 16, var_threshold: float = 100.0) -> np.ndarray:
    """Cheap variance-based foreground mask (same idea as FingerprintPreprocessor.segment)."""
    h, w = gray.shape[:2]
    mask = np.zeros((h, w), dtype=np.uint8)
    img_f = gray.astype(np.float32)
    for y in range(0, h, block):
        for x in range(0, w, block):
            blk = img_f[y : y + block, x : x + block]
            if blk.size and blk.var() > var_threshold:
                mask[y : y + block, x : x + block] = 255
    return mask


def deskew(
    gray: np.ndarray,
    *,
    use_mask: bool = True,
    border_value: int = 255,
    min_angle_deg: float = 1.0,
) -> tuple[np.ndarray, float]:
    """Rotate *gray* so the dominant ridge orientation is vertical.

    Args:
        gray: uint8 grayscale image.
        use_mask: if True, estimate orientation only over the foreground mask.
        border_value: fill value for pixels revealed by rotation.
        min_angle_deg: skip rotation if |angle| is below this threshold.

    Returns:
        ``(rotated_image, applied_angle_degrees)``.
    """
    if gray.ndim == 3:
        gray = cv2.cvtColor(gray, cv2.COLOR_BGR2GRAY)

    mask = _foreground_mask(gray) if use_mask else None
    angle = estimate_ridge_angle(gray, mask=mask)

    if abs(angle) < min_angle_deg:
        return gray, 0.0

    h, w = gray.shape[:2]
    center = (w / 2.0, h / 2.0)
    rot = cv2.getRotationMatrix2D(center, angle, 1.0)
    rotated = cv2.warpAffine(
        gray,
        rot,
        (w, h),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=border_value,
    )
    return rotated, angle
