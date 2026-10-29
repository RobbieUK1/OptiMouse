"""GTK cursor settings should survive theme and size changes."""
import importlib.util
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

spec=importlib.util.spec_from_file_location("optimouse",Path(__file__).resolve().parents[1]/"optimouse.py")
app=importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)

class GTKSettingsTests(unittest.TestCase):
    def test_settings_section_preserves_other_fields(self):
        original=(
            "[Settings]\n"
            "gtk-theme-name=Adwaita-dark\n"
            "gtk-cursor-theme-size=24\n"
            "gtk-cursor-theme-name=Old\n"
            "gtk-application-prefer-dark-theme=1\n"
            "[Other]\n"
            "foo=bar\n"
        )
        result=app.update_gtk_settings_ini(original,"OptiMouse-71FACC",88)
        self.assertEqual(result.count("gtk-cursor-theme-size="),1)
        self.assertEqual(result.count("gtk-cursor-theme-name="),1)
        self.assertIn("gtk-cursor-theme-size=88",result)
        self.assertIn("gtk-cursor-theme-name=OptiMouse-71FACC",result)
        self.assertIn("gtk-theme-name=Adwaita-dark",result)
        self.assertIn("gtk-application-prefer-dark-theme=1",result)
        self.assertIn("[Other]\nfoo=bar\n",result)
        self.assertEqual(app.update_gtk_settings_ini(result,"OptiMouse-71FACC",88),result)

    def test_missing_section_and_files(self):
        with TemporaryDirectory() as tmp, patch.object(app,"HOME",Path(tmp)):
            app.sync_gtk_cursor_settings("Adwaita",96)
            for version in ("gtk-3.0","gtk-4.0"):
                path=Path(tmp)/".config"/version/"settings.ini"
                self.assertTrue(path.exists())
                self.assertIn("gtk-cursor-theme-size=96",path.read_text())
                self.assertIn("gtk-cursor-theme-name=Adwaita",path.read_text())
                self.assertEqual(path.read_text().count("[Settings]"),1)
            gtk3=Path(tmp)/".config"/"gtk-3.0"/"settings.ini"
            self.assertEqual(gtk3.read_text(),app.update_gtk_settings_ini(gtk3.read_text(),"Adwaita",96))

    def test_existing_unrelated_section(self):
        original="[Other]\nfoo=bar\n"
        updated=app.update_gtk_settings_ini(original,"Adwaita",64)
        self.assertTrue(updated.startswith(original))
        self.assertIn("[Settings]\ngtk-cursor-theme-name=Adwaita\ngtk-cursor-theme-size=64\n",updated)

if __name__=="__main__":
    unittest.main()
