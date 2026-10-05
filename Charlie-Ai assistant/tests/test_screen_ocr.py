"""tests/test_screen_ocr.py — Tests for Vision Screen OCR and Visual Diagnostics."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from actions.screen_ocr import screen_ocr
from engine import vision_ocr as vision


class ScreenOCRTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_capture_and_save_screenshot(self):
        try:
            from PIL import Image
            # Create a mock captured image
            mock_img = Image.new("RGB", (320, 240), color="blue")
        except ImportError:
            self.skipTest("PIL not installed")

        with patch("engine.vision_ocr.capture_screen_image", return_value=mock_img):
            saved = vision.save_screenshot(filename="test_cap.png")
            self.assertTrue(saved.exists())
            self.assertEqual(saved.name, "test_cap.png")
            saved.unlink(missing_ok=True)

    def test_extract_screen_text_with_mock_ai_client(self):
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.text = "Error 404: Not Found in browser window."
        mock_client.generate_content.return_value = mock_resp

        try:
            from PIL import Image
            mock_img = Image.new("RGB", (400, 300), color="white")
        except ImportError:
            self.skipTest("PIL not installed")

        with patch("engine.vision_ocr.capture_screen_image", return_value=mock_img):
            res = vision.extract_screen_text(client=mock_client)
            self.assertEqual(res["status"], "success")
            self.assertEqual(res["text"], "Error 404: Not Found in browser window.")
            self.assertEqual(res["width"], 400)
            self.assertEqual(res["height"], 300)

    def test_diagnose_screen_error(self):
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.text = "Found SyntaxError on line 42 of main.py. Recommended fix: add missing colon."
        mock_client.generate_content.return_value = mock_resp

        try:
            from PIL import Image
            mock_img = Image.new("RGB", (400, 300), color="black")
        except ImportError:
            self.skipTest("PIL not installed")

        with patch("engine.vision_ocr.capture_screen_image", return_value=mock_img):
            res = vision.diagnose_screen_error(client=mock_client)
            self.assertIn("SyntaxError", res["text"])

    def test_action_handler_dispatch(self):
        with patch("engine.vision_ocr.extract_screen_text") as mock_extract:
            mock_extract.return_value = {
                "status": "success",
                "engine": "ai_vision",
                "width": 1920,
                "height": 1080,
                "text": "Extracted document text",
            }
            res = screen_ocr({"action": "ocr", "region": [10, 10, 500, 300]})
            self.assertIn("[Screen OCR", res)
            self.assertIn("Extracted document text", res)


if __name__ == "__main__":
    unittest.main()
