import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class FrontendTest(unittest.TestCase):
    def test_homepage_loads_excel_tags_from_api_and_renders_multi_route_results(self):
        html = (PROJECT_ROOT / "templates" / "index.html").read_text(encoding="utf-8")
        script = (PROJECT_ROOT / "static" / "js" / "main.js").read_text(encoding="utf-8")

        self.assertIn('id="profileGate"', html)
        self.assertIn('id="profileProgress"', html)
        self.assertIn('id="profileOptionList"', html)
        self.assertIn('id="useSavedProfileButton"', html)
        self.assertIn('id="restartProfileButton"', html)
        self.assertIn('id="appShell"', html)
        self.assertIn('class="app-shell is-hidden"', html)
        self.assertIn('id="tagGrid"', html)
        self.assertIn('id="mindsetGrid"', html)
        self.assertIn('id="editProfileButton"', html)
        self.assertIn("体验标签", html)
        self.assertIn("心境标签", html)
        self.assertIn("偏好画像", html)
        self.assertIn("沿用上次画像进入", html)
        self.assertIn("重新作答", html)
        self.assertNotIn('class="field-group profile-group" id="profileQuestions"', html)

        self.assertIn('fetch("/api/tags")', script)
        self.assertNotIn('fetch("/static/data/tags.json")', script)
        self.assertNotIn("const mindsetTags", script)
        self.assertIn('const profileStorageKey = "moodscapeProfileAnswers"', script)
        self.assertIn("localStorage.getItem(profileStorageKey)", script)
        self.assertIn("localStorage.setItem(profileStorageKey", script)
        self.assertIn("renderProfileStep", script)
        self.assertIn("loadSavedProfileAnswers", script)
        self.assertIn("enterAppWithProfile", script)
        self.assertIn("restartProfileFlow", script)
        self.assertIn("renderRouteOptions", script)
        self.assertIn("toggleRouteDetail", script)
        self.assertIn("renderScriptContent", script)
        self.assertIn("route.script_sections", script)
        self.assertIn("script-section-list", script)
        self.assertIn("escapeHtml(route.script)", script)
        self.assertIn("route-option", script)
        self.assertIn("is-expanded", script)
        self.assertIn("let expandedRouteIndex = null", script)
        self.assertNotIn("expandedRouteIndex = 0", script)
        self.assertIn("route-close-button", script)
        self.assertIn("closeRouteDetail", script)
        self.assertIn("expandedRouteIndex === index ? null : index", script)
        self.assertIn("profile_answers: collectProfileAnswers()", script)
        self.assertIn("请在左侧选择标签，或者写入你的心情状态。", script)
        self.assertIn("window.alert", script)
        self.assertIn("window.MOODSCAPE_CONFIG", html)
        self.assertIn("loadAmapScript", script)
        self.assertIn("let amapLoadPromise = null", script)
        self.assertIn("window._AMapSecurityConfig", script)
        self.assertIn("webapi.amap.com/maps?v=2.0", script)
        self.assertIn("AMap.convertFrom", script)
        self.assertIn("new AMap.Walking", script)
        self.assertIn("destroyActiveMap", script)
        self.assertIn('lineOptions.strokeStyle = "dashed"', script)
        self.assertIn("renderRouteMap", script)
        self.assertIn(
            'catch (error) {\n        if (renderId !== activeMapRenderId) {\n          return;\n        }\n        failedSegments += 1;',
            script,
        )
        self.assertNotIn("map-placeholder", script)

    def test_runtime_code_does_not_hardcode_travel_data_sources(self):
        recommender = (PROJECT_ROOT / "services" / "recommender.py").read_text(encoding="utf-8")
        app = (PROJECT_ROOT / "app.py").read_text(encoding="utf-8")
        script = (PROJECT_ROOT / "static" / "js" / "main.js").read_text(encoding="utf-8")

        self.assertNotIn("MINDSET_ALIASES", recommender)
        self.assertNotIn("TEXT_MINDSET_RULES", recommender)
        self.assertNotIn("routes.json", recommender)
        self.assertNotIn("tags.json", recommender)
        self.assertNotIn("给自己留一句", app)
        self.assertNotIn("上海情绪路线", app)
        self.assertNotIn("这条路线适合此刻的你", app)
        self.assertNotIn("适合一个人安静停留", script)

    def test_map_configuration_is_rendered_from_server_environment(self):
        import os
        from unittest.mock import patch

        from app import app

        with patch.dict(
            os.environ,
            {
                "AMAP_JS_KEY": "test-amap-key",
                "AMAP_SECURITY_JS_CODE": "test-security-code",
            },
        ):
            response = app.test_client().get("/")

        html = response.get_data(as_text=True)
        self.assertIn('"amapJsKey": "test-amap-key"', html)
        self.assertIn('"amapSecurityJsCode": "test-security-code"', html)


if __name__ == "__main__":
    unittest.main()
