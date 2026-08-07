# -*- coding: utf-8 -*-
"""在干嘛 — API 配置构建与 MVU 状态翻译测试"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'python'))
import zaiganma_app as app


class TestBuildApiConfig(unittest.TestCase):
    def setUp(self):
        # 清掉可能存在的环境变量干扰
        for k in ["ZAIGANMA_VISION_KEY", "ZAIGANMA_VISION_BASE",
                  "ZAIGANMA_DANMU_KEY", "ZAIGANMA_DANMU_BASE"]:
            os.environ.pop(k, None)

    def test_danmu_same_uses_vision(self):
        cfg = {
            "visionSource": "custom",
            "visionCustomApiKey": "key-v",
            "visionCustomBaseUrl": "https://v.example.com/v1",
            "visionCustomModel": "vis-model",
            "danmuSource": "same",
        }
        r = app.build_api_config(cfg)
        self.assertEqual(r["dm_api_key"], "key-v")
        self.assertEqual(r["dm_api_base"], "https://v.example.com/v1")
        self.assertEqual(r["dm_model"], "vis-model")

    def test_custom_danmu(self):
        cfg = {
            "visionSource": "hana",
            "visionModelId": "vm",
            "_visionApiKey": "hk",
            "_visionBaseUrl": "https://h.example.com/v1",
            "danmuSource": "custom",
            "danmuCustomApiKey": "ck",
            "danmuCustomBaseUrl": "https://c.example.com/v1",
            "danmuCustomModel": "cm",
        }
        r = app.build_api_config(cfg)
        self.assertEqual(r["dm_api_key"], "ck")
        self.assertEqual(r["dm_api_base"], "https://c.example.com/v1")
        self.assertEqual(r["dm_model"], "cm")

    def test_hana_danmu_uses_internal_keys(self):
        cfg = {
            "visionSource": "hana",
            "visionProviderId": "p1",
            "visionModelId": "vm",
            "_visionApiKey": "vk",
            "_visionBaseUrl": "https://v.example.com/v1",
            "danmuSource": "hana",
            "danmuProviderId": "p2",
            "danmuModelId": "dm",
            "_danmuApiKey": "dk",
            "_danmuBaseUrl": "https://d.example.com/v1",
        }
        r = app.build_api_config(cfg)
        self.assertEqual(r["vis_api_key"], "vk")
        self.assertEqual(r["dm_api_key"], "dk")
        self.assertEqual(r["dm_model"], "dm")

    def test_env_fallback_when_internal_keys_missing(self):
        os.environ["ZAIGANMA_VISION_KEY"] = "env-key"
        os.environ["ZAIGANMA_VISION_BASE"] = "https://env.example.com/v1"
        cfg = {"visionSource": "hana", "visionModelId": "vm", "danmuSource": "same"}
        r = app.build_api_config(cfg)
        self.assertEqual(r["vis_api_key"], "env-key")
        self.assertEqual(r["vis_api_base"], "https://env.example.com/v1")

    def test_snake_case_compat(self):
        cfg = {
            "vision_source": "custom",
            "vision_custom_api_key": "sk",
            "vision_custom_base_url": "https://x/v1",
            "vision_custom_model": "m",
            "danmu_source": "same",
        }
        r = app.build_api_config(cfg)
        self.assertEqual(r["vis_api_key"], "sk")
        self.assertEqual(r["vis_model"], "m")


class TestTranslateVarsToState(unittest.TestCase):
    def test_energy_tiers(self):
        # 五档边界：85 / 60 / 40 / 20
        self.assertIn("精神头很足", app.translate_vars_to_state({"energy": 100, "mood": 60, "affection": 0}, "大小姐"))
        self.assertIn("精神头很足", app.translate_vars_to_state({"energy": 85, "mood": 60, "affection": 0}, "大小姐"))
        self.assertIn("精力还不错", app.translate_vars_to_state({"energy": 60, "mood": 60, "affection": 0}, "大小姐"))
        self.assertIn("稍微有点累", app.translate_vars_to_state({"energy": 40, "mood": 60, "affection": 0}, "大小姐"))
        self.assertIn("挺疲惫的", app.translate_vars_to_state({"energy": 20, "mood": 60, "affection": 0}, "大小姐"))
        self.assertIn("累得不行了", app.translate_vars_to_state({"energy": 0, "mood": 60, "affection": 0}, "大小姐"))

    def test_mood_tiers(self):
        self.assertIn("心情很好", app.translate_vars_to_state({"energy": 60, "mood": 100, "affection": 0}, "大小姐"))
        self.assertIn("心情还可以", app.translate_vars_to_state({"energy": 60, "mood": 60, "affection": 0}, "大小姐"))
        self.assertIn("心情一般般", app.translate_vars_to_state({"energy": 60, "mood": 40, "affection": 0}, "大小姐"))
        self.assertIn("心情不太好", app.translate_vars_to_state({"energy": 60, "mood": 20, "affection": 0}, "大小姐"))
        self.assertIn("心情很差", app.translate_vars_to_state({"energy": 60, "mood": 0, "affection": 0}, "大小姐"))

    def test_same_direction_uses_dun(self):
        # energy 与 mood 同在高位 → "、"连接
        r = app.translate_vars_to_state({"energy": 90, "mood": 90, "affection": 0}, "大小姐")
        self.assertIn("、", r)
        self.assertNotIn("但", r)

    def test_opposite_direction_uses_dan(self):
        # energy 高 mood 低 → "但"连接
        r = app.translate_vars_to_state({"energy": 90, "mood": 10, "affection": 0}, "大小姐")
        self.assertIn("但", r)

    def test_affection_stages(self):
        self.assertIn("很亲密", app.translate_vars_to_state({"energy": 60, "mood": 60, "affection": 90}, "大小姐"))
        self.assertIn("挺熟的", app.translate_vars_to_state({"energy": 60, "mood": 60, "affection": 60}, "大小姐"))
        self.assertIn("相处有一阵", app.translate_vars_to_state({"energy": 60, "mood": 60, "affection": 30}, "大小姐"))

    def test_low_affection_no_relation(self):
        # 好感度 < 21：不写关系描述，只返回状态行
        r = app.translate_vars_to_state({"energy": 60, "mood": 60, "affection": 10}, "大小姐")
        self.assertNotIn("大小姐", r)
        self.assertNotIn("亲密", r)
        self.assertNotIn("熟", r)

    def test_affection_boundaries(self):
        self.assertIn("很亲密", app.translate_vars_to_state({"energy": 60, "mood": 60, "affection": 81}, "大小姐"))
        self.assertIn("挺熟的", app.translate_vars_to_state({"energy": 60, "mood": 60, "affection": 51}, "大小姐"))
        self.assertIn("相处有一阵", app.translate_vars_to_state({"energy": 60, "mood": 60, "affection": 21}, "大小姐"))
        r = app.translate_vars_to_state({"energy": 60, "mood": 60, "affection": 20}, "大小姐")
        self.assertNotIn("大小姐", r)

    def test_defaults_when_missing(self):
        # 缺字段时用默认值 80/60/0，不抛异常
        r = app.translate_vars_to_state({}, "大小姐")
        self.assertIsInstance(r, str)
        self.assertTrue(len(r) > 0)


if __name__ == "__main__":
    unittest.main()
