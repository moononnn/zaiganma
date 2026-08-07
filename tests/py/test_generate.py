# -*- coding: utf-8 -*-
"""在干嘛 — 弹幕生成逻辑测试（mock 掉 AI 调用，覆盖一步法/两步法/伙伴/记忆流）"""
import os
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'python'))
import zaiganma_app as app

FAKE_IMG = "aGVsbG8="  # 随便一个 base64 占位


def base_cfg(**overrides):
    cfg = {
        "visionSource": "hana",
        "visionModelId": "vis-model",
        "_visionApiKey": "vk",
        "_visionBaseUrl": "https://v.example.com/v1",
        "danmuSource": "same",
        "styles": ["casual"],
        "danmuCount": 1,
        "userName": "大小姐",
        "nicknames": [],
        "buddyNicknames": [],
        "buddyMode": False,
        "selectedBuddies": [],
        "buddies": {},
        "buddyMemoryRatio": 30,
        "intervalMode": "fixed",
        "intervalSec": 30,
    }
    cfg.update(overrides)
    return cfg


class TestGenerateOneShot(unittest.TestCase):
    """一步法：截图模型直接看图生成弹幕"""

    @mock.patch.object(app, "call_llm", return_value="这条弹幕好看")
    def test_one_shot_calls_llm_once_with_image(self, mock_llm):
        cfg = base_cfg(danmuSource="same")
        text, buddy_name, buddy_color = app.generate_danmu_text(cfg, FAKE_IMG)
        self.assertEqual(text, "这条弹幕好看")
        self.assertIsNone(buddy_name)
        self.assertEqual(mock_llm.call_count, 1)
        # 一步法消息应包含图片
        messages = mock_llm.call_args[0][3]
        self.assertTrue(any(
            c.get("type") == "image_url" and FAKE_IMG in c["image_url"]["url"]
            for m in messages for c in (m.get("content") or [])
            if isinstance(c, dict)
        ))

    @mock.patch.object(app, "call_llm", return_value="在写代码呢")
    def test_nickname_injected_when_called(self, mock_llm):
        cfg = base_cfg(danmuSource="same", nicknames=["闺闺"])
        with mock.patch("zaiganma_app.random.random", return_value=0.1):  # < 0.35 会叫名字
            text, _, _ = app.generate_danmu_text(cfg, FAKE_IMG)
        self.assertEqual(text, "在写代码呢")
        user_msg = mock_llm.call_args[0][3][-1]["content"]
        self.assertIn("闺闺", user_msg[0]["text"])

    @mock.patch.object(app, "call_llm", return_value=None)
    def test_llm_failure_returns_none(self, mock_llm):
        text, _, _ = app.generate_danmu_text(base_cfg(danmuSource="same"), FAKE_IMG)
        self.assertIsNone(text)


class TestGenerateTwoStep(unittest.TestCase):
    """两步法：截图模型分析 → 文案模型生成"""

    @mock.patch.object(app, "call_llm", side_effect=[
        "B站正在播放美食视频。暖色调灯光很温馨。弹幕区很热闹。",  # 分析
        "这个看着好好吃",                                      # 弹幕
    ])
    def test_two_step_without_pre_analysis(self, mock_llm):
        cfg = base_cfg(danmuSource="hana", danmuModelId="dm", _danmuApiKey="dk",
                       _danmuBaseUrl="https://d.example.com/v1")
        text, _, _ = app.generate_danmu_text(cfg, FAKE_IMG)
        self.assertEqual(text, "这个看着好好吃")
        self.assertEqual(mock_llm.call_count, 2, "无预分析时应先分析再生成")

    @mock.patch.object(app, "call_llm", return_value="复用分析的结果")
    def test_two_step_reuses_pre_analysis(self, mock_llm):
        cfg = base_cfg(danmuSource="hana", danmuModelId="dm")
        text, _, _ = app.generate_danmu_text(cfg, FAKE_IMG, pre_analysis="已有分析结果。")
        self.assertEqual(text, "复用分析的结果")
        self.assertEqual(mock_llm.call_count, 1, "有预分析时不应再调截图模型")

    @mock.patch.object(app, "call_llm", side_effect=["根据规则我需要生成弹幕", "注意：不要用引号", "按照要求输出弹幕"])
    def test_invalid_content_retries_then_fallback(self, mock_llm):
        # 三次返回都带思考痕迹 → 重试耗尽 → 用兜底弹幕池
        with mock.patch.object(app, "FALLBACK_DANMU", ["兜底弹幕一号"]):
            text, _, _ = app.generate_danmu_text(
                base_cfg(danmuSource="hana", danmuModelId="dm"), FAKE_IMG, pre_analysis="画面。")
            self.assertEqual(text, "兜底弹幕一号")
        self.assertEqual(mock_llm.call_count, 3, "无效内容应重试 3 次")

    @mock.patch.object(app, "call_llm", return_value="正常弹幕内容")
    def test_stale_style_filtered(self, mock_llm):
        # styles 含已删除风格（praise），应被过滤，落到 casual
        cfg = base_cfg(danmuSource="same", styles=["praise", "casual"])
        text, _, _ = app.generate_danmu_text(cfg, FAKE_IMG)
        self.assertEqual(text, "正常弹幕内容")


class TestBuddyMode(unittest.TestCase):
    """伙伴弹幕：使用伙伴身份与 MVU 状态"""

    @mock.patch.object(app, "call_llm", return_value="伙伴说的内容")
    @mock.patch.object(app, "get_buddy_mvu_context", return_value="精力还不错、心情很好")
    def test_buddy_style_prompt_uses_buddy_desc(self, mock_mvu, mock_llm):
        cfg = base_cfg(
            danmuSource="hana", danmuModelId="dm",
            buddyMode=True,
            buddyMemoryRatio=0,  # 0% 概率走记忆流，保证稳定测截图流
            selectedBuddies=["hanako"],
            buddies={"hanako": {"name": "小花", "color": "#FF6B6B", "styleDesc": "温柔的少女助手。"}},
        )
        text, buddy_name, buddy_color = app.generate_danmu_text(
            cfg, FAKE_IMG, pre_analysis="画面。", force_buddy_id="hanako")
        self.assertEqual(buddy_name, "小花")
        self.assertEqual(buddy_color, "#FF6B6B")
        # 风格 prompt 应包含伙伴描述 + MVU 状态（在 user 消息的【弹幕风格】段）
        user_msg = mock_llm.call_args[0][3][1]["content"]
        self.assertIn("小花", user_msg)
        self.assertIn("精力还不错", user_msg)

    @mock.patch.object(app, "call_llm", return_value="普通弹幕")
    def test_no_force_buddy_id_means_normal_mode(self, mock_llm):
        # 安全保护：即使 cfg.buddyMode=True，不传 force_buddy_id 时走普通流
        cfg = base_cfg(danmuSource="same", buddyMode=True, selectedBuddies=["hanako"],
                       buddies={"hanako": {"name": "小花", "color": "#FF6B6B", "styleDesc": "x"}})
        text, buddy_name, _ = app.generate_danmu_text(cfg, FAKE_IMG)
        self.assertIsNone(buddy_name)


class TestMemoryFlow(unittest.TestCase):
    """伙伴记忆弹幕：按比例走本地 facts.db 记忆流"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.old_home = os.environ.get("HANA_HOME")
        os.environ["HANA_HOME"] = self.tmpdir
        # 重置缓存的 HANA_HOME
        app._HANA_HOME = None
        app._WORKVISIT_PATH = None
        # 建 facts.db
        db_dir = os.path.join(self.tmpdir, "agents", "hanako", "memory")
        os.makedirs(db_dir, exist_ok=True)
        conn = sqlite3.connect(os.path.join(db_dir, "facts.db"))
        conn.execute("CREATE TABLE facts (id INTEGER PRIMARY KEY AUTOINCREMENT, fact TEXT)")
        conn.executemany("INSERT INTO facts (fact) VALUES (?)", [
            ("她养了一只叫团子的猫，特别黏人",),
            ("她最近在做桌面弹幕插件",),
            ("她喜欢喝茉莉花茶",),
            ("昨晚她熬夜到两点",),
        ])
        conn.commit()
        conn.close()

    def tearDown(self):
        os.environ.pop("HANA_HOME", None)
        if self.old_home:
            os.environ["HANA_HOME"] = self.old_home
        app._HANA_HOME = None
        app._WORKVISIT_PATH = None
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    @mock.patch.object(app, "call_llm", return_value="还记得你那只猫吗")
    def test_memory_flow_with_facts_db(self, mock_llm):
        cfg = base_cfg(
            danmuSource="hana", danmuModelId="dm",
            buddyMode=True, buddyMemoryRatio=100,
            selectedBuddies=["hanako"],
            buddies={"hanako": {"name": "小花", "color": "#FF6B6B", "styleDesc": "x"}},
        )
        text, buddy_name, _ = app.generate_danmu_text(
            cfg, FAKE_IMG, pre_analysis="画面。", force_buddy_id="hanako")
        self.assertEqual(text, "还记得你那只猫吗")
        self.assertEqual(buddy_name, "小花")
        # 记忆 prompt 应包含 facts.db 里的内容，且不调用截图分析
        system_msg = mock_llm.call_args[0][3][0]["content"]
        self.assertIn("团子的猫", system_msg)

    @mock.patch.object(app, "call_llm", return_value="喵")
    def test_memory_flow_empty_db_falls_back(self, mock_llm):
        # 清空 facts.db → 记忆流拿不到记忆，返回 (None, None, None) 静默跳过
        db_path = os.path.join(self.tmpdir, "agents", "hanako", "memory", "facts.db")
        conn = sqlite3.connect(db_path)
        conn.execute("DELETE FROM facts")
        conn.commit()
        conn.close()
        cfg = base_cfg(
            danmuSource="hana", danmuModelId="dm",
            buddyMode=True, buddyMemoryRatio=100,
            selectedBuddies=["hanako"],
            buddies={"hanako": {"name": "小花", "color": "#FF6B6B", "styleDesc": "x"}},
        )
        result = app.generate_danmu_text(cfg, FAKE_IMG, pre_analysis="画面。", force_buddy_id="hanako")
        self.assertEqual(result, (None, None, None), "记忆流拿不到记忆时应静默跳过")


class TestDedupHints(unittest.TestCase):
    """跨轮重复抑制：最近弹幕与高频句式应作为提示注入 prompt"""

    def test_recent_texts_and_hot_patterns_injected(self):
        with mock.patch.object(app, "call_llm", return_value="正常内容") as m, \
             mock.patch.object(app, "_recent_danmu_texts", ["又搁这写代码", "在摸鱼", "好家伙"]), \
             mock.patch.object(app, "_pattern_counts", {name: (5 if name == "又搁这" else 0) for name, _, _ in app._PATTERN_WATCH}):
            cfg = base_cfg(danmuSource="same")
            text, _, _ = app.generate_danmu_text(cfg, FAKE_IMG)
            self.assertEqual(text, "正常内容")
            # 一步法：style_prompt（含重复抑制提示）在 user 消息的【弹幕风格】段
            user_text = m.call_args[0][3][1]["content"][0]["text"]
            self.assertIn("你最近说过的弹幕", user_text, "应提示最近弹幕避免重复")
            self.assertIn("又搁这写代码", user_text)
            self.assertIn("又搁这", user_text, "高频句式应被点名禁用")

    def test_no_hints_when_clean(self):
        with mock.patch.object(app, "call_llm", return_value="正常内容") as m, \
             mock.patch.object(app, "_recent_danmu_texts", []), \
             mock.patch.object(app, "_pattern_counts", {name: 0 for name, _, _ in app._PATTERN_WATCH}):
            cfg = base_cfg(danmuSource="same")
            text, _, _ = app.generate_danmu_text(cfg, FAKE_IMG)
            self.assertEqual(text, "正常内容")
            user_text = m.call_args[0][3][1]["content"][0]["text"]
            self.assertNotIn("你最近说过的弹幕", user_text)

    def test_quality_rules_injected(self):
        """质量准则（禁比喻/禁感叹词堆砌/允许废话）应注入所有普通弹幕"""
        with mock.patch.object(app, "call_llm", return_value="正常内容") as m:
            cfg = base_cfg(danmuSource="same")
            app.generate_danmu_text(cfg, FAKE_IMG)
            user_text = m.call_args[0][3][1]["content"][0]["text"]
            self.assertIn("弹幕质量准则", user_text)
            self.assertIn("比喻句式", user_text)
            self.assertIn("允许说废话", user_text)

    def test_time_context_injected(self):
        """时间锚定应注入（防止上午说'今晚通宵'这类错乱）"""
        with mock.patch.object(app, "call_llm", return_value="正常内容") as m:
            cfg = base_cfg(danmuSource="same")
            app.generate_danmu_text(cfg, FAKE_IMG)
            user_text = m.call_args[0][3][1]["content"][0]["text"]
            self.assertIn("现在是", user_text)
            self.assertIn("点", user_text)

    def test_quality_rules_in_memory_flow(self):
        """记忆流也应注入质量准则"""
        import sqlite3
        tmpdir = tempfile.mkdtemp()
        try:
            old_home = os.environ.get("HANA_HOME")
            os.environ["HANA_HOME"] = tmpdir
            app._HANA_HOME = None
            app._WORKVISIT_PATH = None
            db_dir = os.path.join(tmpdir, "agents", "hanako", "memory")
            os.makedirs(db_dir, exist_ok=True)
            conn = sqlite3.connect(os.path.join(db_dir, "facts.db"))
            conn.execute("CREATE TABLE facts (id INTEGER PRIMARY KEY AUTOINCREMENT, fact TEXT)")
            conn.execute("INSERT INTO facts (fact) VALUES (?)", ("她养了一只叫团子的猫，特别黏人",))
            conn.commit()
            conn.close()
            cfg = base_cfg(
                danmuSource="hana", danmuModelId="dm",
                buddyMode=True, buddyMemoryRatio=100,
                selectedBuddies=["hanako"],
                buddies={"hanako": {"name": "小花", "color": "#FF6B6B", "styleDesc": "x"}},
            )
            with mock.patch.object(app, "call_llm", return_value="记得你的猫") as m:
                app.generate_danmu_text(cfg, FAKE_IMG, pre_analysis="画面。", force_buddy_id="hanako")
            system_msg = m.call_args[0][3][0]["content"]
            self.assertIn("比喻句式", system_msg, "记忆流也应带质量准则")
            self.assertIn("现在是", system_msg)
        finally:
            os.environ.pop("HANA_HOME", None)
            if old_home:
                os.environ["HANA_HOME"] = old_home
            app._HANA_HOME = None
            app._WORKVISIT_PATH = None
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
