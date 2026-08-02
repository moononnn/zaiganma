# -*- coding: utf-8 -*-
"""在干嘛 — 工具函数测试（find_free_port / load_json / 跨轮重复抑制）"""
import os
import socket
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'python'))
import zaiganma_app as app


class TestFindFreePort(unittest.TestCase):
    def test_returns_start_when_free(self):
        # 找一个当前空闲的端口当起点
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            free_port = s.getsockname()[1]
        self.assertEqual(app.find_free_port(free_port), free_port)

    def test_skips_occupied_port(self):
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            occupied = s.getsockname()[1]
            s.listen(1)
            found = app.find_free_port(occupied, max_try=5)
            self.assertNotEqual(found, occupied, "被占用端口应被跳过")
            self.assertGreater(found, occupied)

    def test_range_bounds(self):
        # 连续占用多个端口时继续往后找
        socks = []
        try:
            for _ in range(3):
                s = socket.socket()
                s.bind(("127.0.0.1", 0))
                socks.append(s)
            base = socks[0].getsockname()[1]
            for s in socks:
                s.listen(1)
            found = app.find_free_port(base, max_try=50)
            self.assertNotIn(found, [s.getsockname()[1] for s in socks])
        finally:
            for s in socks:
                s.close()


class TestLoadJson(unittest.TestCase):
    def test_missing_file_returns_default(self):
        self.assertEqual(app.load_json("/nonexistent/path.json"), {})
        self.assertEqual(app.load_json("/nonexistent/path.json", default=[]), [])

    def test_utf8_sig_handling(self):
        # 带 BOM 的 UTF-8 文件（Windows 编辑器常见）
        with tempfile.NamedTemporaryFile("wb", suffix=".json", delete=False) as f:
            f.write(b'\xef\xbb\xbf{"a": 1}')
            path = f.name
        try:
            data = app.load_json(path)
            self.assertEqual(data, {"a": 1})
        finally:
            os.unlink(path)


class TestLogDanmu(unittest.TestCase):
    def setUp(self):
        app._recent_danmu_texts = []
        app._pattern_counts = {name: 0 for name, _, _ in app._PATTERN_WATCH}
        self.patcher = mock.patch.object(app, "_get_danmu_log_path", return_value=os.devnull)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()

    def test_normal_danmu_enters_recent(self):
        app.log_danmu("普通", "又在摸鱼啊")
        self.assertIn("又在摸鱼啊", app._recent_danmu_texts)

    def test_buddy_danmu_not_counted_as_normal(self):
        app.log_danmu("伙伴", "小花：又在忙什么")
        self.assertEqual(app._recent_danmu_texts, [], "伙伴弹幕不应进入普通弹幕去重池")

    def test_pattern_counting(self):
        app.log_danmu("普通", "又搁这写代码")
        self.assertEqual(app._pattern_counts["又搁这"], 1)
        app.log_danmu("普通", "又搁这改 bug")
        self.assertEqual(app._pattern_counts["又搁这"], 2)

    def test_bi_sentence_template_matches_variants(self):
        # 模板级匹配："比…还…" 应拦下所有变体，而不是只拦某个具体词
        app.log_danmu("普通", "这界面比我爸的聊天记录还安静")
        app.log_danmu("普通", "这手机壳比我脸皮还能拉")
        app.log_danmu("普通", "这链接比我命还长")
        self.assertEqual(app._pattern_counts["比字句"], 3, "三种变体都应命中比字句模板")

    def test_emotion_words_counted(self):
        app.log_danmu("普通", "好家伙，这操作")
        app.log_danmu("普通", "绝了绝了")
        self.assertEqual(app._pattern_counts["感叹词堆砌"], 2)

    def test_recent_cap_and_pattern_decay(self):
        # 填满 30 条后最旧的被挤掉，pattern 计数开始衰减
        for i in range(app._RECENT_MAX + 5):
            app.log_danmu("普通", f"又搁这条{i}")
        self.assertLessEqual(len(app._recent_danmu_texts), app._RECENT_MAX)
        # 挤压发生后，较久之前的 pattern 计数被衰减
        self.assertLessEqual(app._pattern_counts["又搁这"], app._RECENT_MAX)


if __name__ == "__main__":
    unittest.main()
