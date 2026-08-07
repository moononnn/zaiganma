# -*- coding: utf-8 -*-
"""在干嘛 — 引擎层测试（间隔纯函数 / call_llm / 分析兜底链 / 托盘持久化 / 主循环集成）
不发起真实网络：httpx.post、截图、AI 调用全部 mock
"""
import os
import sys
import json
import time
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'python'))
import zaiganma_app as app

# 测试期间静音日志
app.log = lambda *a, **k: None


class TestComputeCooldown(unittest.TestCase):
    def test_fixed_mode(self):
        self.assertEqual(app.compute_cooldown({"intervalMode": "fixed", "intervalSec": 30}, 1), 30)

    def test_random_mode_within_range(self):
        cfg = {"intervalMode": "random", "intervalMin": 10, "intervalMax": 20}
        for _ in range(50):
            c = app.compute_cooldown(cfg, 1)
            self.assertTrue(10 <= c <= 20)

    def test_random_min_max_guard(self):
        # max < min 时自动抬升，不产生空区间
        cfg = {"intervalMode": "random", "intervalMin": 60, "intervalMax": 10}
        c = app.compute_cooldown(cfg, 1)
        self.assertGreaterEqual(c, 60)

    def test_sent_zero_halves_with_floor(self):
        # sent==0 → 减半，保底 5 秒
        self.assertEqual(app.compute_cooldown({"intervalMode": "fixed", "intervalSec": 30}, 0), 15)
        self.assertEqual(app.compute_cooldown({"intervalMode": "fixed", "intervalSec": 8}, 0), 5)
        self.assertEqual(app.compute_cooldown({"intervalMode": "fixed", "intervalSec": 5}, 0), 5)

    def test_sent_positive_no_halving(self):
        self.assertEqual(app.compute_cooldown({"intervalMode": "fixed", "intervalSec": 30}, 3), 30)


class TestComputeBuddyCooldown(unittest.TestCase):
    def test_fixed(self):
        self.assertEqual(app.compute_buddy_cooldown({"buddyIntervalMode": "fixed", "buddyInterval": 90}), 90)

    def test_random(self):
        cfg = {"buddyIntervalMode": "random", "buddyIntervalMin": 60, "buddyIntervalMax": 120}
        for _ in range(50):
            c = app.compute_buddy_cooldown(cfg)
            self.assertTrue(60 <= c <= 120)


class TestIdleShouldPause(unittest.TestCase):
    def test_boundary(self):
        self.assertFalse(app.idle_should_pause(599, 600))
        self.assertTrue(app.idle_should_pause(600, 600))
        self.assertTrue(app.idle_should_pause(3600, 600))

    def test_threshold_zero_disables(self):
        self.assertFalse(app.idle_should_pause(9999, 0))


class TestCallLLM(unittest.TestCase):
    def make_resp(self, status=200, content="", reasoning=""):
        resp = mock.Mock()
        resp.status_code = status
        if status == 200:
            resp.json.return_value = {
                "choices": [{"message": {"content": content, "reasoning_content": reasoning}}]
            }
        else:
            resp.text = "error body"
        return resp

    def test_success_strips_quotes(self):
        resp = self.make_resp(content='"你好呀"')
        with mock.patch.object(app.httpx, "post", return_value=resp) as m:
            text = app.call_llm("https://x/v1/", "key", "m", [])
        self.assertEqual(text, "你好呀")
        # baseUrl 尾斜杠应被去掉
        self.assertEqual(m.call_args[0][0], "https://x/v1/chat/completions")

    def test_reasoning_content_fallback(self):
        resp = self.make_resp(content="", reasoning="<thinking>思考</thinking>结论")
        with mock.patch.object(app.httpx, "post", return_value=resp):
            text = app.call_llm("https://x/v1", "key", "m", [])
        self.assertNotIn("thinking", text)
        self.assertIn("结论", text)

    def test_non_200_returns_none(self):
        resp = self.make_resp(status=500)
        with mock.patch.object(app.httpx, "post", return_value=resp):
            text = app.call_llm("https://x/v1", "key", "m", [], max_retries=0)
        self.assertIsNone(text)

    def test_retry_on_exception(self):
        resp = self.make_resp(content="成功了")
        with mock.patch.object(app.httpx, "post", side_effect=[Exception("boom"), resp]):
            text = app.call_llm("https://x/v1", "key", "m", [], max_retries=1)
        self.assertEqual(text, "成功了")

    def test_all_retries_fail_returns_none(self):
        with mock.patch.object(app.httpx, "post", side_effect=Exception("boom")):
            text = app.call_llm("https://x/v1", "key", "m", [], max_retries=1)
        self.assertIsNone(text)

    def test_truncate_long_text(self):
        long_text = "第一句是完整的开场白。第二句也还行。最后这一句才是真正想说的弹幕内容，其他都是废话"
        resp = self.make_resp(content=long_text)
        with mock.patch.object(app.httpx, "post", return_value=resp):
            text = app.call_llm("https://x/v1", "key", "m", [])
        self.assertLessEqual(len(text), 50)
        self.assertIn("最后这一句", text)

    def test_skip_reasoning_adds_body_flag(self):
        resp = self.make_resp(content="x")
        with mock.patch.object(app.httpx, "post", return_value=resp) as m:
            app.call_llm("https://x/v1", "key", "m", [], skip_reasoning=True)
        body = m.call_args[1]["json"]
        self.assertEqual(body["thinking"], {"type": "disabled"})


class TestAnalysisFallback(unittest.TestCase):
    """两步法分析结果的兜底链：坏关键词 / 太短 / 不完整英文结尾 / 多角度拆分"""

    def gen_with_analysis(self, analysis, second_text="正常内容"):
        """mock call_llm：第一次返回分析，第二次返回弹幕"""
        with mock.patch.object(app, "call_llm", side_effect=[analysis, second_text]):
            cfg = {
                "visionSource": "hana", "visionModelId": "vm",
                "_visionApiKey": "k", "_visionBaseUrl": "http://x",
                "danmuSource": "hana", "danmuModelId": "dm",
                "styles": ["casual"], "userName": "大小姐", "nicknames": [],
                "buddyNicknames": [], "buddyMode": False, "selectedBuddies": [],
                "buddies": {}, "buddyMemoryRatio": 0,
            }
            return app.generate_danmu_text(cfg, "b64")

    def test_bad_keyword_falls_back(self):
        text, _, _ = self.gen_with_analysis("描述一下屏幕内容")
        self.assertEqual(text, "正常内容")

    def test_too_short_falls_back(self):
        text, _, _ = self.gen_with_analysis("短")
        self.assertEqual(text, "正常内容")

    def test_incomplete_english_tail_falls_back(self):
        text, _, _ = self.gen_with_analysis("B站正在播放视频 playing")
        self.assertEqual(text, "正常内容")

    def test_normal_analysis_splits_angles(self):
        analysis = "B站正在播放美食视频。\n暖色调灯光很温馨。\n弹幕区很热闹。"
        with mock.patch.object(app, "call_llm", side_effect=[analysis, "正常内容"]) as m:
            cfg = {
                "visionSource": "hana", "visionModelId": "vm",
                "_visionApiKey": "k", "_visionBaseUrl": "http://x",
                "danmuSource": "hana", "danmuModelId": "dm",
                "styles": ["casual"], "userName": "大小姐", "nicknames": [],
                "buddyNicknames": [], "buddyMode": False, "selectedBuddies": [],
                "buddies": {}, "buddyMemoryRatio": 0,
            }
            app.generate_danmu_text(cfg, "b64")
        self.assertGreaterEqual(len(cfg["_last_angles"]), 3, "正常多行分析应拆出多个角度")


class TestPersistConfig(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.cfg_path = os.path.join(self.tmpdir, "config.json")
        with open(self.cfg_path, "w", encoding="utf-8") as f:
            json.dump({"intervalSec": 30, "fontSize": 30}, f)
        self.patcher = mock.patch.dict(os.environ, {"ZAIGANMA_CONFIG": self.cfg_path})
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_merges_and_excludes_internal_keys(self):
        config = {
            "intervalSec": 60,
            "_visionApiKey": "secret",
            "_visionBaseUrl": "http://internal",
        }
        app._persist_config(config)
        with open(self.cfg_path, encoding="utf-8") as f:
            saved = json.load(f)
        self.assertEqual(saved["intervalSec"], 60, "托盘修改应写入")
        self.assertEqual(saved["fontSize"], 30, "已有配置应保留")
        self.assertNotIn("_visionApiKey", saved, "内部键不应落盘")
        self.assertNotIn("_visionBaseUrl", saved)


class TestToggleEngine(unittest.TestCase):
    def test_stop_running_engine(self):
        engine = mock.Mock()
        engine.running = True
        action = mock.Mock()
        app._engine_ref = engine
        try:
            app._toggle_engine(engine, action, None)
            engine.stop.assert_called_once()
            action.setText.assert_called_with("启动弹幕")
        finally:
            app._engine_ref = None

    def test_start_stopped_engine_via_replace(self):
        engine = mock.Mock()
        engine.running = False
        action = mock.Mock()
        app._engine_ref = engine
        new_engine = mock.Mock()
        try:
            with mock.patch.object(app, "_replace_engine", return_value=new_engine) as m:
                app._toggle_engine(engine, action, None)
            m.assert_called_once_with(engine.window)
            action.setText.assert_called_with("停止弹幕")
        finally:
            app._engine_ref = None


class TestEngineRun(unittest.TestCase):
    """主循环集成测试：假窗口 + 全 mock，跑 2.5 秒收敛，验证弹幕真的会生成"""

    class FakeWindow:
        def __init__(self):
            self.config = {
                "intervalMode": "fixed", "intervalSec": 5, "danmuCount": 1,
                "styles": ["casual"], "danmuMode": True, "buddyMode": False,
                "imageMaxWidth": 1280, "idleAutoPause": False,
                "danmuColors": ["#FFFFFF"], "buddyMemoryRatio": 0,
                "nicknames": [], "buddyNicknames": [],
                "userName": "测试", "danmuSource": "same",
                "visionModelId": "m", "_visionApiKey": "k", "_visionBaseUrl": "http://x",
                "buddies": {}, "selectedBuddies": [],
            }
            self.sent = []

        def send_stagger(self, text, *a, **k):
            self.sent.append(text)

        def send(self, *a, **k):
            pass

    def test_run_generates_danmu_and_stops_cleanly(self):
        fake = self.FakeWindow()
        with mock.patch.object(app, "screenshot", return_value=None), \
             mock.patch.object(app, "compress_image", return_value="b64"), \
             mock.patch.object(app, "generate_danmu_text", return_value=("测试弹幕", None, None)), \
             mock.patch.object(app, "call_llm", return_value="后台分析"), \
             mock.patch.object(app, "log_danmu", lambda *a, **k: None):
            engine = app.DanmuEngine(fake)
            engine.start()
            time.sleep(2.5)  # 第一轮：截图 → 生成 → 弹幕入列
            engine.stop()
            engine.join(timeout=5)
        self.assertFalse(engine.running, "stop 后引擎应退出")
        self.assertGreaterEqual(len(fake.sent), 1, "主循环应生成至少一条弹幕")

    def test_idle_pause_skips_generation(self):
        """空闲暂停开启且系统空闲时，不生成弹幕（用假 idle 秒数）"""
        fake = self.FakeWindow()
        fake.config["idleAutoPause"] = True
        fake.config["idleThreshold"] = 600
        with mock.patch.object(app, "_get_idle_seconds", return_value=3600), \
             mock.patch.object(app, "screenshot", return_value=None), \
             mock.patch.object(app, "compress_image", return_value="b64"), \
             mock.patch.object(app, "generate_danmu_text", return_value=("测试弹幕", None, None)), \
             mock.patch.object(app, "call_llm", return_value="x"), \
             mock.patch.object(app, "log_danmu", lambda *a, **k: None):
            engine = app.DanmuEngine(fake)
            engine.start()
            time.sleep(1.2)
            engine.stop()
            engine.join(timeout=5)
        self.assertEqual(len(fake.sent), 0, "系统空闲时应暂停生成")

    def test_first_round_waits_for_analysis(self):
        """首轮应等待画面分析完成：生成时 cfg 里应已是真实分析结果而非兜底值"""
        fake = self.FakeWindow()
        seen_analysis = {}

        def fake_gen(cfg, img_b64, pre_analysis=None, force_buddy_id=None):
            seen_analysis["value"] = pre_analysis
            return ("基于真实画面的弹幕", None, None)

        def slow_llm(*a, **k):
            # 模拟分析需要一点时间
            time.sleep(0.5)
            return "B站正在播放美食视频。画面很温馨。"

        with mock.patch.object(app, "screenshot", return_value=None), \
             mock.patch.object(app, "compress_image", return_value="b64"), \
             mock.patch.object(app, "generate_danmu_text", side_effect=fake_gen), \
             mock.patch.object(app, "call_llm", side_effect=slow_llm), \
             mock.patch.object(app, "log_danmu", lambda *a, **k: None):
            engine = app.DanmuEngine(fake)
            engine.start()
            time.sleep(2.5)
            engine.stop()
            engine.join(timeout=5)
        self.assertNotEqual(seen_analysis.get("value"), "用户正在使用电脑",
                            "首轮生成应使用真实画面分析而非兜底值")
        self.assertIn("B站正在播放美食视频", seen_analysis.get("value", ""),
                      "首轮生成应拿到异步分析的完整结果")

    def test_first_round_fallback_when_analysis_fails(self):
        """首轮分析失败：发兜底弹幕池，绝不用空描述硬编"""
        fake = self.FakeWindow()
        gen_called = []

        def fake_gen(cfg, img_b64, pre_analysis=None, force_buddy_id=None):
            gen_called.append(pre_analysis)
            return ("AI 弹幕", None, None)

        with mock.patch.object(app, "screenshot", return_value=None), \
             mock.patch.object(app, "compress_image", return_value="b64"), \
             mock.patch.object(app, "generate_danmu_text", side_effect=fake_gen), \
             mock.patch.object(app, "call_llm", return_value=None), \
             mock.patch.object(app, "log_danmu", lambda *a, **k: None):
            engine = app.DanmuEngine(fake)
            engine.start()
            time.sleep(1.5)  # 等首轮：分析失败 → 兜底弹幕
            engine.stop()
            engine.join(timeout=5)
        self.assertGreaterEqual(len(fake.sent), 1, "分析失败时首轮应发兜底弹幕")
        # 兜底弹幕来自 FALLBACK_DANMU（非 AI 生成）
        self.assertIn(fake.sent[0], app.FALLBACK_DANMU)
        # 首轮等待期间不应调用 AI 生成（基于兜底描述硬编）
        self.assertNotIn("用户正在使用电脑", gen_called)


if __name__ == "__main__":
    unittest.main()
