from pathlib import Path
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QPixmap
import cv2

app = QApplication.instance() or QApplication(['--platform', 'offscreen'])

male_path = Path('core/assets/male_assistant.jpg')
fem_path = Path('core/assets/female_assistant_v2.jpg')

img_m = cv2.imread(str(male_path))
img_f = cv2.imread(str(fem_path))

print("Male shape:", img_m.shape)
print("Female shape:", img_f.shape)

# Let's inspect where lips are in female_assistant_v2.jpg:
# At x = 512, sample y from 400 to 700
h, w = img_f.shape[:2]
cx = w // 2
for y in range(int(h * 0.45), int(h * 0.70), 10):
    b, g, r = img_f[y, cx]
    # Lip redness index: r - (g + b) / 2
    redness = int(r) - (int(g) + int(b)) // 2
    print(f"Female y={y/h:.3f} ({y}px): R={r} G={g} B={b} redness={redness}")

print("\n--- Male ---")
h_m, w_m = img_m.shape[:2]
cx_m = w_m // 2
for y in range(int(h_m * 0.50), int(h_m * 0.75), 10):
    b, g, r = img_m[y, cx_m]
    redness = int(r) - (int(g) + int(b)) // 2
    print(f"Male y={y/h_m:.3f} ({y}px): R={r} G={g} B={b} redness={redness}")
