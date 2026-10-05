import unittest
from core.viseme import VisemeStream
from core.digital_human import EmotionController, Emotion


class ArticulationTests(unittest.TestCase):
    def test_high_resolution_preserves_fine_detail(self):
        import numpy as np
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtGui import QPixmap
        from pathlib import Path
        from core.digital_human import PhotoRealisticRig, FaceLandmarks, VisemeShape, ExpressionShape
        app = QApplication.instance() or QApplication(['test', '-platform', 'offscreen'])
        path = Path(__file__).resolve().parents[1] / 'core/assets/male_assistant.jpg'
        rig = PhotoRealisticRig(QPixmap(str(path)), FaceLandmarks.for_male())
        grid = (np.indices((640, 640)).sum(axis=0) % 2 * 255).astype(np.uint8)
        base = np.stack([grid, grid, grid, np.full_like(grid, 255)], axis=-1)
        result = rig._deform(base, 640, VisemeShape(), 0, 0, 0, 0, ExpressionShape())
        self.assertEqual(result.shape, base.shape)
        self.assertLess(np.abs(result.astype(float) - base).mean(), 1.0)

    def test_rendered_mouth_aperture_grows_for_both_portraits(self):
        import cv2
        import numpy as np
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtGui import QPixmap
        from pathlib import Path
        from core.digital_human import PhotoRealisticRig, FaceLandmarks, VisemeShape, ExpressionShape
        app = QApplication.instance() or QApplication(['test', '-platform', 'offscreen'])
        assets = Path(__file__).resolve().parents[1] / 'core' / 'assets'
        for asset, landmarks in [('male_assistant.jpg', FaceLandmarks.for_male()),
                                  ('female_assistant_v2.jpg', FaceLandmarks.for_female())]:
            with self.subTest(asset=asset):
                rig = PhotoRealisticRig(QPixmap(str(assets / asset)), landmarks)
                base = cv2.resize(rig._source, (320, 320))
                cx, cy = (int(v * 320) for v in landmarks.mouth_centre)
                areas = []
                for amount in (0.0, 0.4, 0.8):
                    result = rig._deform(base, 320, VisemeShape(jaw_open=amount),
                                         0, 0, 0, 0, ExpressionShape())
                    patch = result[cy-8:cy+24, cx-20:cx+20, :3]
                    areas.append(np.count_nonzero(np.max(patch, axis=2) < 85))
                self.assertGreater(areas[1], areas[0] + 20)
                self.assertGreater(areas[2], areas[1] + 30)

    def test_closed_consonant_survives_live_pipeline(self):
        stream = VisemeStream()
        stream.feed_text("mmm")
        frames = stream.frames([(0.7, 0.9, 0.2)] * 12, 0.02)
        closures = [f for f in frames if f[3] == "MBP"]
        self.assertTrue(closures)
        self.assertTrue(all(f[1] == 0 for f in closures))
        self.assertEqual(stream.frames([(0., 0., 0.)], .02)[0],
                         (0., 0., 0., "REST"))

    def test_missing_transcript_uses_audio_shape(self):
        frame = VisemeStream().frames([(0.7, 0.8, -0.4)], .02)[0]
        self.assertEqual(frame, (0.7, 0.8, -0.4, None))

    def test_conversation_moods(self):
        controller = EmotionController()
        for text, expected in [("mazaak sunao", Emotion.HAPPY),
                               ("main pareshan hoon", Emotion.CONCERNED),
                               ("serious baat hai", Emotion.SERIOUS),
                               ("tension mat lo", Emotion.REASSURING),
                               ("The file is on the desktop", Emotion.NEUTRAL)]:
            with self.subTest(text=text):
                self.assertEqual(controller.classify(text)[0], expected)
