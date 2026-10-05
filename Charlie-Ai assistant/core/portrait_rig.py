"""Small texture-preserving speech rig calibrated to female_assistant.png.

Move the photographed lips and chin instead of painting substitute lips on top.
Only a lower-face patch is resampled; eyes, hair and silhouette stay untouched.
This is a 2-D portrait animation, not a reconstructed 3-D talking head.
"""
from __future__ import annotations

import cv2
import numpy as np
from PyQt6.QtGui import QImage, QPixmap


class PortraitRig:
    def __init__(self, portrait: QPixmap):
        image = portrait.toImage().convertToFormat(QImage.Format.Format_RGBA8888)
        ptr = image.bits()
        ptr.setsize(image.sizeInBytes())
        self.source = np.frombuffer(ptr, np.uint8).reshape(
            image.height(), image.bytesPerLine() // 4, 4
        )[:, :image.width()].copy()
        self._size = 0
        self._key = None
        self._frame = None

    def frame(self, size: int, opening: float, width: float) -> QImage:
        # Quantisation avoids repeated remaps when the speech pose is unchanged.
        opening = round(max(0.0, min(1.0, opening)), 2)
        width = round(max(-1.0, min(1.0, width)), 2)
        key = (size, opening, width)
        if key == self._key:
            return self._frame
        if size != self._size:
            self._base = cv2.resize(self.source, (size, size), interpolation=cv2.INTER_AREA)
            self._bounds = (int(size * .34), int(size * .455),
                            int(size * .66), int(size * .65))
            x0, y0, x1, y1 = self._bounds
            yy, xx = np.mgrid[y0:y1, x0:x1].astype(np.float32)
            self._x, self._y = xx / size, yy / size
            self._size = size
        result = self._base.copy()
        if opening > .005 or abs(width) > .005:
            x, y = self._x, self._y
            # Source landmarks measured against the original 1254px portrait.
            centre, half_width = .501, .061
            influence = np.clip(1 - ((y - .522) / .085) ** 2, 0, 1) ** 2
            influence *= np.clip(1 - ((x - centre) / .15) ** 2, 0, 1) ** 2
            sx = centre + (x - centre) / (1 + .22 * width * influence)
            u = (sx - centre) / half_width
            lip = np.clip(1 - u * u, 0, 1)
            seam = .512 + .010 * lip
            upper = seam - .0028 * opening * lip
            lower = seam + .023 * opening * lip
            below = y > (upper + lower) * .5
            # Invert the smooth displacement to keep the real lip texture,
            # mouth corners and chin attached throughout the jaw movement.
            sy = y.copy()
            jaw = np.clip(1 - ((sx - centre) / .12) ** 2, 0, 1) ** 2
            for _ in range(4):
                top_weight = np.clip(1 - (seam - sy) / .048, 0, 1) ** 2
                bottom_weight = np.clip(1 - (sy - seam) / .115, 0, 1)
                displacement = np.where(below,
                    opening * (.023 * lip * bottom_weight +
                               .009 * jaw * np.sin(np.pi * bottom_weight)),
                    -.0028 * opening * lip * top_weight)
                sy = y - displacement
            patch = cv2.remap(self._base, (sx * size).astype(np.float32),
                              (sy * size).astype(np.float32), cv2.INTER_LINEAR,
                              borderMode=cv2.BORDER_REPLICATE)
            # Interior is clipped between the displaced ORIGINAL lip edges.
            # A subdued upper tooth band sits inside the mouth, never above it.
            gap = lower - upper
            depth = np.clip((y - upper) / np.maximum(gap, .0001), 0, 1)
            cavity = np.zeros_like(patch)
            cavity[..., :3] = np.stack((27 + 25 * depth, 14 + 9 * depth,
                                        30 + 17 * depth), axis=-1)
            cavity[..., 3] = 255
            teeth = ((depth < .25) & (np.abs(u) < .82) & (opening > .22))
            cavity[teeth, :3] = (181, 167, 179)
            edge = np.minimum(y - upper, lower - y) * size
            alpha = (np.clip(edge + .25, 0, 1) * (lip > 0) *
                     np.clip(gap * size, 0, 1))[..., None]
            patch = (patch * (1 - alpha) + cavity * alpha).astype(np.uint8)
            x0, y0, x1, y1 = self._bounds
            result[y0:y1, x0:x1] = patch
        self._frame = QImage(result.data, size, size, result.strides[0],
                             QImage.Format.Format_RGBA8888).copy()
        self._key = key
        return self._frame
