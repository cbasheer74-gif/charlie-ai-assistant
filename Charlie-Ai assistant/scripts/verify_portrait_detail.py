"""Render old-resolution versus detailed frames without touching user settings."""
from pathlib import Path
import sys
import time
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import cv2
import numpy as np
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QPixmap
from core.digital_human import PhotoRealisticRig, FaceLandmarks, VisemeShape, ExpressionShape

app = QApplication(['diagnostic', '-platform', 'offscreen'])
rows = []
for name, asset, landmarks in [
    ('Male', 'male_assistant.jpg', FaceLandmarks.for_male()),
    ('Female', 'female_assistant_v2.jpg', FaceLandmarks.for_female()),
]:
    rig = PhotoRealisticRig(QPixmap(str(ROOT / 'core/assets' / asset)), landmarks)
    outputs = []
    for size in (320, 640):
        base = cv2.resize(rig._source, (size, size), interpolation=cv2.INTER_AREA)
        times = []
        for _ in range(6):
            start = time.perf_counter()
            frame = rig._deform(base, size, VisemeShape(jaw_open=.6), 0, 0, 0, 0, ExpressionShape())
            times.append((time.perf_counter()-start)*1000)
        display = cv2.resize(frame, (640, 640))
        display = cv2.cvtColor(display, cv2.COLOR_RGBA2BGR)
        cv2.putText(display, f'{name}: {size}px render', (15, 30), cv2.FONT_HERSHEY_SIMPLEX, .7, (255,255,255), 2)
        outputs.append(display)
        print(f'{name} {size}px median: {np.median(times):.1f} ms')
    rows.append(np.concatenate(outputs, axis=1))
cv2.imwrite(str(ROOT / 'portrait-detail-comparison.png'), np.concatenate(rows, axis=0))
