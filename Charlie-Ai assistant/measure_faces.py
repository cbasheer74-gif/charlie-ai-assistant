"""
Auto-detect facial landmarks in male/female portrait photos using OpenCV
and output calibrated FaceLandmarks values for digital_human.py.
Run: python measure_faces.py
"""
import sys, os

# Try mediapipe first, fall back to manual pixel read
try:
    import mediapipe as mp
    HAS_MP = True
except ImportError:
    HAS_MP = False

import cv2
import numpy as np

ASSETS = "core/assets"
PHOTOS = {
    "male":   os.path.join(ASSETS, "male_assistant.jpg"),
    "female": os.path.join(ASSETS, "female_assistant_v2.jpg"),
}


def normalize(px, py, W, H):
    """Pixel coords → normalized 0-1 (square crop assumed by rig)."""
    return round(px / W, 3), round(py / H, 3)


def detect_landmarks_mp(img_path, label):
    import mediapipe as mp
    mp_face = mp.solutions.face_mesh
    img = cv2.imread(img_path)
    H, W = img.shape[:2]
    print(f"\n=== {label.upper()} — {W}×{H} ===")

    with mp_face.FaceMesh(
        static_image_mode=True,
        max_num_faces=1,
        refine_landmarks=True,
        min_detection_confidence=0.4
    ) as face_mesh:
        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        result = face_mesh.process(rgb)
        if not result.multi_face_landmarks:
            print("  ❌ No face detected — check photo quality")
            return

        lm = result.multi_face_landmarks[0].landmark

        def pt(idx):
            return lm[idx].x, lm[idx].y

        # MediaPipe 468-landmark indices (face mesh)
        # Mouth
        upper_lip_top   = pt(13)   # inner upper lip centre
        lower_lip_bot   = pt(14)   # inner lower lip centre
        mouth_left      = pt(61)
        mouth_right     = pt(291)
        mouth_centre_x  = (mouth_left[0] + mouth_right[0]) / 2
        mouth_centre_y  = (upper_lip_top[1] + lower_lip_bot[1]) / 2

        # Jaw
        chin            = pt(152)

        # Eyes
        left_eye_outer  = pt(33)
        left_eye_inner  = pt(133)
        left_eye_top    = pt(159)
        left_eye_bot    = pt(145)
        right_eye_outer = pt(263)
        right_eye_inner = pt(362)
        right_eye_top   = pt(386)
        right_eye_bot   = pt(374)

        le_cx = (left_eye_outer[0]  + left_eye_inner[0])  / 2
        le_cy = (left_eye_top[1]    + left_eye_bot[1])    / 2
        re_cx = (right_eye_outer[0] + right_eye_inner[0]) / 2
        re_cy = (right_eye_top[1]   + right_eye_bot[1])   / 2
        eye_w = abs(left_eye_outer[0] - left_eye_inner[0]) / 2
        eye_h = abs(left_eye_top[1]   - left_eye_bot[1])  / 2

        # Brows
        l_brow = pt(105)
        r_brow = pt(334)

        # Cheeks
        l_cheek = pt(234)
        r_cheek = pt(454)

        mw = abs(mouth_right[0] - mouth_left[0]) / 2
        jaw_drop_px = abs(chin[1] - mouth_centre_y)

        print(f"  mouth_centre  = ({mouth_centre_x:.3f}, {mouth_centre_y:.3f})")
        print(f"  mouth_left    = ({mouth_left[0]:.3f}, {mouth_left[1]:.3f})")
        print(f"  mouth_right   = ({mouth_right[0]:.3f}, {mouth_right[1]:.3f})")
        print(f"  upper_lip     = ({upper_lip_top[0]:.3f}, {upper_lip_top[1]:.3f})")
        print(f"  lower_lip     = ({lower_lip_bot[0]:.3f}, {lower_lip_bot[1]:.3f})")
        print(f"  mouth_width   = {mw:.3f}")
        print(f"  jaw_centre    = ({(mouth_left[0]+mouth_right[0])/2:.3f}, {chin[1]:.3f})")
        print(f"  jaw_max_drop  = {jaw_drop_px * 0.55:.3f}  (55% of chin-to-mouth distance)")
        print(f"  upper_lip_lift= {eye_h * 0.8:.3f}")
        print(f"  left_eye      = ({le_cx:.3f}, {le_cy:.3f})")
        print(f"  right_eye     = ({re_cx:.3f}, {re_cy:.3f})")
        print(f"  eye_width     = {eye_w:.3f}")
        print(f"  eye_height    = {eye_h:.3f}")
        print(f"  left_iris     = ({le_cx:.3f}, {le_cy:.3f})")
        print(f"  right_iris    = ({re_cx:.3f}, {re_cy:.3f})")
        print(f"  iris_radius   = {eye_w * 0.28:.3f}")
        print(f"  left_brow     = ({l_brow[0]:.3f}, {l_brow[1]:.3f})")
        print(f"  right_brow    = ({r_brow[0]:.3f}, {r_brow[1]:.3f})")
        print(f"  brow_width    = {eye_w:.3f}")
        print(f"  brow_max_lift = {(le_cy - l_brow[1]) * 0.55:.3f}")
        print(f"  left_cheek    = ({l_cheek[0]:.3f}, {l_cheek[1]:.3f})")
        print(f"  right_cheek   = ({r_cheek[0]:.3f}, {r_cheek[1]:.3f})")

        # ── Copy-paste-ready output ──────────────────────────────────────
        print(f"\n  ── Paste into FaceLandmarks.for_{label}() ──")
        print(f"            mouth_centre=({mouth_centre_x:.3f}, {mouth_centre_y:.3f}),")
        print(f"            mouth_left=({mouth_left[0]:.3f}, {mouth_left[1]:.3f}),")
        print(f"            mouth_right=({mouth_right[0]:.3f}, {mouth_right[1]:.3f}),")
        print(f"            upper_lip=({upper_lip_top[0]:.3f}, {upper_lip_top[1]:.3f}),")
        print(f"            lower_lip=({lower_lip_bot[0]:.3f}, {lower_lip_bot[1]:.3f}),")
        print(f"            mouth_width={mw:.3f},")
        print(f"            jaw_centre=({(mouth_left[0]+mouth_right[0])/2:.3f}, {chin[1]:.3f}),")
        print(f"            jaw_max_drop={jaw_drop_px * 0.55:.3f},")
        print(f"            upper_lip_lift={eye_h * 0.8:.3f},")
        print(f"            left_eye=({le_cx:.3f}, {le_cy:.3f}),")
        print(f"            right_eye=({re_cx:.3f}, {re_cy:.3f}),")
        print(f"            eye_width={eye_w:.3f},")
        print(f"            eye_height={eye_h:.3f},")
        print(f"            left_iris=({le_cx:.3f}, {le_cy:.3f}),")
        print(f"            right_iris=({re_cx:.3f}, {re_cy:.3f}),")
        print(f"            iris_radius={eye_w * 0.28:.3f},")
        print(f"            left_upper_lid=({le_cx:.3f}, {left_eye_top[1]:.3f}),")
        print(f"            left_lower_lid=({le_cx:.3f}, {left_eye_bot[1]:.3f}),")
        print(f"            right_upper_lid=({re_cx:.3f}, {right_eye_top[1]:.3f}),")
        print(f"            right_lower_lid=({re_cx:.3f}, {right_eye_bot[1]:.3f}),")
        print(f"            left_brow=({l_brow[0]:.3f}, {l_brow[1]:.3f}),")
        print(f"            right_brow=({r_brow[0]:.3f}, {r_brow[1]:.3f}),")
        print(f"            brow_width={eye_w:.3f},")
        print(f"            brow_max_lift={max(0.020, (le_cy - l_brow[1]) * 0.55):.3f},")
        print(f"            left_cheek=({l_cheek[0]:.3f}, {l_cheek[1]:.3f}),")
        print(f"            right_cheek=({r_cheek[0]:.3f}, {r_cheek[1]:.3f}),")


if __name__ == "__main__":
    if not HAS_MP:
        print("Installing mediapipe...")
        os.system(f"{sys.executable} -m pip install mediapipe --quiet")
        print("Done. Restart: python measure_faces.py")
        sys.exit(0)

    for label, path in PHOTOS.items():
        if not os.path.exists(path):
            print(f"Missing: {path}")
            continue
        detect_landmarks_mp(path, label)
