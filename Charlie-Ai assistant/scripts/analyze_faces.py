import cv2
import numpy as np

def analyze(path):
    img = cv2.imread(path)
    h, w = img.shape[:2]
    print(f"=== {path} ({w}x{h}) ===")
    
    # Let's inspect vertical slice through x = w // 2 (0.50)
    cx = int(w * 0.505)
    slice_col = img[:, cx, :] # BGR
    # Let's detect lips by color (lips typically have higher Red and lower Green/Blue compared to skin)
    # R - G contrast
    r = slice_col[:, 2].astype(float)
    g = slice_col[:, 1].astype(float)
    b = slice_col[:, 0].astype(float)
    diff = r - (g + b) / 2.0
    
    for y_pct in range(30, 85, 2):
        y = int(h * y_pct / 100.0)
        print(f"y={y_pct}% ({y}px): BGR=({slice_col[y,0]},{slice_col[y,1]},{slice_col[y,2]}) diff={diff[y]:.1f}")

analyze("core/assets/female_assistant_v2.jpg")
analyze("core/assets/male_assistant.jpg")
