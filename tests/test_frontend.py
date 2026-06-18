import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class FrontendTest(unittest.TestCase):
    def test_homepage_loads_tags_from_static_json(self):
        html = (PROJECT_ROOT / "templates" / "index.html").read_text(encoding="utf-8")
        script = (PROJECT_ROOT / "static" / "js" / "main.js").read_text(encoding="utf-8")

        self.assertIn('id="tagGrid"', html)
        self.assertNotIn('data-tag="独处"', html)
        self.assertIn('fetch("/static/data/tags.json")', script)
        self.assertIn("tag.emotion_tag", script)
        self.assertIn("tag.user_button_text", script)


if __name__ == "__main__":
    unittest.main()
