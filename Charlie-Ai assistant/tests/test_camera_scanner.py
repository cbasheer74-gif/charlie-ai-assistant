import io
import unittest
from unittest.mock import Mock, patch
from PIL import Image
import actions.camera_scanner as camera_scanner


class CameraScannerTests(unittest.TestCase):
    def test_tool_declaration_structure(self):
        tool = camera_scanner.TOOL
        self.assertEqual(tool["name"], "camera_scanner")
        self.assertIn("open the camera and analyze this thing", tool["description"].lower())
        self.assertIn("parameters", tool)
        self.assertEqual(tool["handler"], camera_scanner.execute)

    def test_language_detection(self):
        self.assertEqual(camera_scanner._detect_language("Hey Charlie open the camera and analyze this thing"), "English")
        self.assertEqual(camera_scanner._detect_language("Charlie camera kholo aur dekho ye kya hai"), "Hindi/Hinglish")
        self.assertEqual(camera_scanner._detect_language("is cheez ka use batao"), "Hindi/Hinglish")
        self.assertEqual(camera_scanner._detect_language("What is this object?"), "English")

    def test_unprompted_scan_rejection(self):
        res = camera_scanner.execute("Hello how are you?")
        self.assertIn("Camera scanning is on standby", res)

        res_hi = camera_scanner.execute("kya haal hai?")
        self.assertIn("Camera scan abhi start nahi kiya gaya", res_hi)

    def test_camera_unavailable_error_handling(self):
        with patch("actions.screen_processor._capture_camera", side_effect=RuntimeError("Device busy")):
            res = camera_scanner.execute("Scan this object: What is this?")
            self.assertIn("Unable to access the camera", res)
            self.assertIn("Device busy", res)

    def test_camera_scan_multimodal_execution(self):
        # Create a small valid test image in bytes
        img = Image.new("RGB", (64, 64), color="blue")
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        test_bytes = buf.getvalue()

        mock_reply = Mock()
        mock_reply.text = "1. IDENTIFICATION: Sony WH-1000XM4 Headphones\n2. OCR: 'SONY WIRELESS NC'\n3. USE: Active noise cancelling audio listening."

        with patch("actions.screen_processor._capture_camera", return_value=(test_bytes, "image/jpeg")), \
             patch("core.gemini.call", return_value=mock_reply) as mock_gemini:
            res = camera_scanner.execute("Hey Charlie open the camera and analyze this thing")
            self.assertIn("Sony WH-1000XM4", res)
            self.assertIn("OCR", res)
            self.assertEqual(mock_gemini.call_count, 1)


if __name__ == '__main__':
    unittest.main()
