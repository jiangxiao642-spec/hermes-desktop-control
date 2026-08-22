import unittest

import click_script


class ClickScriptTests(unittest.TestCase):
    def test_click_emits_left_down_and_up(self):
        script = click_script.click_script("click", 100, 200)
        self.assertIn("[M]::mouse_event(0x0002", script)
        self.assertIn("[M]::mouse_event(0x0004", script)
        self.assertNotIn("[M]::mouse_event(0x0008", script)

    def test_right_click_uses_right_flags(self):
        script = click_script.click_script("right-click", 100, 200)
        self.assertIn("[M]::mouse_event(0x0008", script)
        self.assertIn("[M]::mouse_event(0x0010", script)

    def test_double_click_emits_two_down_up_pairs(self):
        script = click_script.click_script("double-click", 100, 200)
        self.assertEqual(script.count("[M]::mouse_event(0x0002"), 2)
        self.assertEqual(script.count("[M]::mouse_event(0x0004"), 2)

    def test_move_has_no_mouse_event_calls(self):
        script = click_script.click_script("move", 100, 200)
        self.assertNotIn("[M]::mouse_event", script)

    def test_coordinates_embedded_after_validation(self):
        script = click_script.click_script("click", "12", "34")
        self.assertIn("Point(12, 34)", script)

    def test_ok_marker_is_appended(self):
        script = click_script.click_script("click", 1, 2, ok_marker="CLICK_OK")
        self.assertTrue(script.endswith("CLICK_OK"))

    def test_rejects_non_integer_coordinates(self):
        with self.assertRaises(ValueError):
            click_script.click_script("click", "abc", 10)
        with self.assertRaises(ValueError):
            click_script.click_script("click", "1; Remove-Item C:\\ -Recurse", 10)

    def test_rejects_unknown_action(self):
        with self.assertRaises(ValueError):
            click_script.click_script("hover", 1, 2)


if __name__ == "__main__":
    unittest.main()
