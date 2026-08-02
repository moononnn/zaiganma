# -*- coding: utf-8 -*-
"""在干嘛 — 弹幕内容过滤逻辑测试（is_valid_danmu / _strip_thinking / _pick_last_sentence）"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'python'))
import zaiganma_app as app


class TestStripThinking(unittest.TestCase):
    def test_think_block_multiline(self):
        text = "好的，我来想想。\n<think>\n用户在看视频\n</think>\n这条弹幕不错"
        result = app._strip_thinking(text)
        self.assertNotIn("<think>", result)
        self.assertIn("这条弹幕不错", result)

    def test_thinking_block(self):
        text = "前<thinking>内部思考</thinking>后"
        result = app._strip_thinking(text)
        self.assertNotIn("thinking", result)
        self.assertIn("前后", result)

    def test_single_line_think_tags(self):
        text = "<think>思考</think> 输出内容"
        result = app._strip_thinking(text)
        self.assertIn("输出内容", result)

    def test_no_marker_unchanged(self):
        text = "就是一条普通弹幕"
        self.assertEqual(app._strip_thinking(text), text)


class TestPickLastSentence(unittest.TestCase):
    def test_picks_last_short_sentence(self):
        text = "第一句很长很长的废话。第二句。第三句也有点长但还可以。就这句了"
        result = app._pick_last_sentence(text)
        self.assertIn("就这句了", result)

    def test_skips_thinking_keywords(self):
        text = "根据指令我需要生成内容。真正的回复内容在这"
        result = app._pick_last_sentence(text)
        self.assertNotIn("根据指令", result)
        self.assertIn("真正的回复", result)

    def test_empty_input(self):
        self.assertEqual(app._pick_last_sentence(""), "")
        self.assertEqual(app._pick_last_sentence("。。。" .strip()), "")


class TestIsValidDanmu(unittest.TestCase):
    def test_basic_valid(self):
        self.assertTrue(app.is_valid_danmu("这个配色好好看啊"))

    def test_none_or_empty(self):
        self.assertFalse(app.is_valid_danmu(None))
        self.assertFalse(app.is_valid_danmu(""))
        self.assertFalse(app.is_valid_danmu("   "))

    def test_length_bounds(self):
        self.assertFalse(app.is_valid_danmu("短"))          # < 4 字
        self.assertFalse(app.is_valid_danmu("x" * 51))       # > 50 字
        self.assertTrue(app.is_valid_danmu("刚好四个字啊"))

    def test_thinking_keywords(self):
        for kw in ["我们被要求", "根据规则", "根据指令", "按照要求", "需要生成",
                   "根据画面描述", "instruction", "注意：", "不要用", "比如",
                   "你是一个", "作为AI", "请生成一条"]:
            self.assertFalse(app.is_valid_danmu(f"开头{kw}结尾"), f"含关键词 {kw} 应判无效")

    def test_self_reference_filtered(self):
        # 自指循环：评论弹幕本身的弹幕应被丢弃（截图里能看到弹幕浮层）
        self.assertFalse(app.is_valid_danmu("这弹幕比视频内容还精彩"))
        self.assertFalse(app.is_valid_danmu("弹幕墙看得我眼睛快瞎了"))

    def test_bi_sentence_hard_filtered(self):
        # 比字句硬过滤："比X还Y"比喻句式直接丢弃（含各种变体）
        self.assertFalse(app.is_valid_danmu("这光标闪得比我眼睛还慢"))
        self.assertFalse(app.is_valid_danmu("桌面图标比我家楼下早市还热闹"))
        self.assertFalse(app.is_valid_danmu("群聊刷得比我看小说还快"))
        self.assertFalse(app.is_valid_danmu("这圈转得比我家猫追尾巴还勤快"))
        # 温和用法（不带"还"）不受影响
        self.assertTrue(app.is_valid_danmu("这个比上次的清楚"))
        # 感叹句/无比较结构不受影响
        self.assertTrue(app.is_valid_danmu("这屏幕好亮啊"))

    def test_parenthesis_start(self):
        self.assertFalse(app.is_valid_danmu("（内心独白）这条不行"))
        self.assertFalse(app.is_valid_danmu("(悄悄说)这条也不行"))

    def test_truncated_trailing_punct(self):
        for p in ["，", "、", "：", ";", ",", "&", "@"]:
            self.assertFalse(app.is_valid_danmu(f"被截断的弹幕{p}"), f"以 {p} 结尾应判无效")

    def test_unclosed_parenthesis(self):
        self.assertFalse(app.is_valid_danmu("有括号没关（"))     # 只有开括号
        self.assertTrue(app.is_valid_danmu("有括号（关了）"))     # 成对 OK


if __name__ == "__main__":
    unittest.main()
