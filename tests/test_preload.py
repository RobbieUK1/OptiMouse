"""Preloading must not modify the live cursor or race an Apply build."""
import importlib.util
import threading
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor

spec=importlib.util.spec_from_file_location("optimouse",Path(__file__).resolve().parents[1]/"optimouse.py")
app=importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)

class PreparationTests(unittest.TestCase):
    def test_prepared_colour_is_reused_during_concurrent_apply(self):
        with TemporaryDirectory() as tmp:
            original=Path(tmp)/"base"
            original.mkdir()
            (original/"left_ptr").write_bytes(b"example")
            icons=Path(tmp)/"icons"
            icons.mkdir()
            entered=threading.Event()
            release=threading.Event()
            calls=[]

            def recolour(content, rgb):
                calls.append(rgb)
                entered.set()
                if not release.wait(5):
                    raise TimeoutError("test never released the build")
                return b"tinted-"+content

            with patch.object(app,"base_theme",return_value=original), \
                 patch.object(app,"ICONS",icons), \
                 patch.object(app,"tint_xcursor",side_effect=recolour), \
                 patch.object(app,"checked") as hyprland, \
                 patch.object(app,"write_settings") as settings, \
                 ThreadPoolExecutor(max_workers=2) as pool:
                first=pool.submit(app.prepare_custom_theme,"#123456")
                self.assertTrue(entered.wait(5))
                second=pool.submit(app.prepare_custom_theme,"#123456")
                release.set()
                self.assertEqual(first.result(5),"OptiMouse-123456")
                self.assertEqual(second.result(5),"OptiMouse-123456")
                self.assertEqual(len(calls),1)
                hyprland.assert_not_called()
                settings.assert_not_called()

    def test_apply_uses_prepare_function_for_custom_colours(self):
        opts={**app.DEFAULT,"follow_theme":False,"color":"#123456","size":52}
        with patch.object(app,"prepare_custom_theme",return_value="OptiMouse-123456") as prepare, \
             patch.object(app,"persist_cursor"), \
             patch.object(app,"checked"), \
             patch.object(app,"overlay_running",return_value=False), \
             patch.object(app,"write_settings"), \
             patch.object(app.shutil,"which",return_value="/bin/tool"):
            theme,preview,timings=app.apply(opts)
        self.assertEqual(theme,"OptiMouse-123456")
        self.assertFalse(preview)
        prepare.assert_called_once_with("#123456")
        self.assertIn("theme",timings)

if __name__=="__main__":
    unittest.main()
