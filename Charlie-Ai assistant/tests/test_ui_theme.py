import os
import unittest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication, QLineEdit, QPushButton

import ui


class UiThemeTests(unittest.TestCase):
    def tearDown(self):
        ui.apply_ui_theme(ui.DEFAULT_UI_THEME, ui.DEFAULT_UI_COLOR)

    def test_all_themes_supply_complete_palette(self):
        for name, palette in ui.UI_THEMES.items():
            self.assertEqual(set(ui._HUE_LINKED), set(palette), name)
            self.assertEqual(name, ui.apply_ui_theme(name))

    def test_themes_are_visually_distinct(self):
        backgrounds = {palette["BG"] for palette in ui.UI_THEMES.values()}
        self.assertEqual(len(ui.UI_THEMES), len(backgrounds))

    def test_accent_tints_selected_theme(self):
        ui.apply_ui_theme("midnight", "#34d399")
        green_primary = ui.C.PRI
        ui.apply_ui_theme("midnight", "#fb7185")
        self.assertNotEqual(green_primary, ui.C.PRI)
        self.assertEqual(ui.DEFAULT_UI_THEME, ui.normalize_ui_theme("LIGHT"))
        self.assertEqual(ui.DEFAULT_UI_THEME, ui.normalize_ui_theme("unknown"))

    def test_clean_light_is_not_available(self):
        self.assertNotIn("light", ui.UI_THEMES)
        self.assertNotIn("light", ui.UI_THEME_LABELS)

    def test_invalid_colour_is_rejected(self):
        ui.apply_ui_theme("graphite")
        before = ui.current_palette()
        self.assertFalse(ui.apply_ui_accent("not-a-colour"))
        self.assertEqual(before, ui.current_palette())

    def test_message_input_text_tracks_each_theme(self):
        app = QApplication.instance() or QApplication([])
        field = QLineEdit()
        holder = SimpleNamespace(_input=field)
        for theme in ui.UI_THEMES:
            ui.apply_ui_theme(theme, ui.UI_THEMES[theme]["PRI"])
            ui.MainWindow._refresh_message_input_contrast(holder)
            palette = field.palette()
            self.assertEqual(
                palette.color(QPalette.ColorRole.Text), QColor(ui.C.TEXT), theme
            )
            self.assertNotEqual(
                palette.color(QPalette.ColorRole.Text),
                palette.color(QPalette.ColorRole.Base),
                theme,
            )
        app.processEvents()

    def test_chat_workspace_prompts_and_status_are_interactive(self):
        app = QApplication.instance() or QApplication([])
        workspace = ui.ChatWorkspace("Charlie")
        selected = []
        new_chats = []
        workspace.prompt_selected.connect(selected.append)
        workspace.new_chat_requested.connect(lambda: new_chats.append(True))

        prompts = workspace.findChildren(QPushButton, "ChatPrompt")
        self.assertEqual(len(prompts), 4)
        prompts[0].click()
        self.assertTrue(selected[0].startswith("Help me solve"))

        workspace.findChild(QPushButton, "ChatNew").click()
        self.assertEqual(new_chats, [True])
        workspace.set_busy(True)
        self.assertEqual(workspace._status.text(), "Thinking")
        workspace.set_busy(False)
        self.assertEqual(workspace._status.text(), "Ready")
        app.processEvents()

    def test_settings_combo_ignores_mouse_wheel(self):
        ignored = []
        event = SimpleNamespace(ignore=lambda: ignored.append(True))

        ui.ClickOnlyComboBox.wheelEvent(object(), event)

        self.assertEqual(ignored, [True])

    def test_about_and_developer_panels_show_product_identity(self):
        app = QApplication.instance() or QApplication([])
        about = ui.AppInfoOverlay("about")
        developer = ui.AppInfoOverlay("developer")
        about_text = " ".join(label.text() for label in about.findChildren(ui.QLabel))
        developer_text = " ".join(label.text() for label in developer.findChildren(ui.QLabel))
        self.assertIn(ui.APP_VERSION, about_text)
        self.assertIn("personal desktop AI assistant", about_text)
        self.assertIn("Anees Chaudhary", about_text)
        self.assertIn("Anees Chaudhary", developer_text)
        self.assertIn("2026", developer_text)
        app.processEvents()



    def test_find_all_img_tags(self):
        import re
        from pathlib import Path
        html_file = Path(__file__).resolve().parent.parent / "landing_page" / "index.html"
        text = html_file.read_text(encoding="utf-8")
        matches = re.findall(r'<img[^>]+>', text)
        for m in matches:
            print("IMG TAG:", m)

if __name__ == "__main__":
    unittest.main()










