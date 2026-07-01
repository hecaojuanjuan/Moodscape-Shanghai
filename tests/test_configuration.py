import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class ConfigurationTest(unittest.TestCase):
    def test_dependencies_and_environment_example_cover_external_services(self):
        requirements = (PROJECT_ROOT / "requirements.txt").read_text(encoding="utf-8")
        env_example = (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8")

        for dependency in ["flask", "openpyxl", "openai", "python-dotenv"]:
            self.assertIn(dependency, requirements.lower())

        for variable in [
            "QWEN_API_KEY",
            "QWEN_BASE_URL",
            "QWEN_MODEL",
            "AMAP_JS_KEY",
            "AMAP_SECURITY_JS_CODE",
            "LLM_TIMEOUT_SECONDS",
        ]:
            self.assertIn(f"{variable}=", env_example)

    def test_readme_documents_qwen_amap_and_fallback_behavior(self):
        readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn("百炼千问", readme)
        self.assertIn("高德地图", readme)
        self.assertIn(".env.example", readme)
        for dependency in ["Flask", "openpyxl", "openai", "python-dotenv"]:
            self.assertIn(dependency, readme)
        self.assertIn("优先使用千问", readme)
        self.assertIn("本地模板", readme)
        self.assertIn("来源", readme)


if __name__ == "__main__":
    unittest.main()
