# -*- coding: utf-8 -*-
"""在干嘛 — 弹幕窗口轨道逻辑测试（PyQt6，offscreen 平台）
覆盖：轨道顺序分配、满轨道拒绝、clear 重置、tracks 缩小后不越界崩溃
"""
import os
import sys
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'python'))

try:
    from PyQt6.QtWidgets import QApplication
    HAVE_QT = True
except ImportError:
    HAVE_QT = False

if HAVE_QT:
    import zaiganma_app as app
    # 测试期间静音日志输出（避免刷屏）
    app.log = lambda *a, **k: None


@unittest.skipUnless(HAVE_QT, "需要 PyQt6")
class TestDanmuWindow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def make_window(self, **config_overrides):
        cfg = dict(app.DEFAULT_CONFIG)
        cfg.update({
            "tracks": 3,
            "font_size": 30,
            "top_margin": 50,
            "danmuColors": ["#FFFFFF", "#FF6B6B"],
            "buddyMode": False,
        })
        cfg.update(config_overrides)
        return app.DanmuWindow(cfg)

    def test_assigns_tracks_in_order(self):
        w = self.make_window(tracks=3)
        w._add_danmu("第一条")
        w._add_danmu("第二条")
        self.assertEqual(len(w.danmu_list), 2)
        self.assertEqual(w.danmu_list[0].track, 0)
        self.assertEqual(w.danmu_list[1].track, 1)
        # 释放第一个轨道后，新弹幕优先用空轨道
        w.danmu_list[0].x = -999  # 模拟移出屏幕
        w._tick()
        w._add_danmu("第三条")
        self.assertEqual(w.danmu_list[-1].track, 0)

    def test_full_tracks_rejects(self):
        w = self.make_window(tracks=3)
        # 注意：update_config 会把 density 映射成 tracks>=5，这里手动收紧到 1 测拒绝逻辑
        w.config["tracks"] = 1
        w.track_occupied = [False] * 1
        w._add_danmu("占满")
        w._add_danmu("挤不下")
        self.assertEqual(len(w.danmu_list), 1, "轨道满时新弹幕应被拒绝")

    def test_clear_resets_everything(self):
        w = self.make_window(tracks=2)
        w._add_danmu("甲")
        w._add_danmu("乙")
        w.clear()  # 走队列
        w._tick()
        self.assertEqual(len(w.danmu_list), 0)
        self.assertFalse(any(w.track_occupied), "clear 后轨道应全部释放")

    def test_shrink_tracks_no_crash(self):
        """轨道数从 3 缩到 1：旧弹幕越界轨道必须被清理，_tick 不能 IndexError"""
        w = self.make_window(tracks=3)
        w._add_danmu("A")
        w._add_danmu("B")
        w._add_danmu("C")
        # 模拟旧弹幕已分配到 track 0/1/2，然后把轨道数缩到 1
        w.update_config({"tracks": 1})
        # 越界弹幕应被清理
        self.assertTrue(all(it.track < 1 for it in w.danmu_list))
        # _tick 不应抛异常
        w._tick()
        self.assertTrue(all(it.track < len(w.track_occupied) for it in w.danmu_list))

    def test_shrink_tracks_during_flight_no_crash(self):
        """运行中（弹幕正在滚动）缩小轨道数：模拟 tick 过程中移除越界弹幕"""
        w = self.make_window(tracks=4)
        w._add_danmu("1")
        w._add_danmu("2")
        w._add_danmu("3")
        # 直接手动构造一个越界弹幕（模拟 update_config 前就在列表里的极端情况）
        fake = app.DanmuItem("x", 100, 100, 2.0, None, 10)
        fake.track = 5
        w.danmu_list.append(fake)
        w.update_config({"tracks": 2})
        # 越界弹幕被清掉，剩余弹幕轨道都在界内
        self.assertLessEqual(len(w.danmu_list), 2)
        w._tick()  # 不应崩溃
        w._add_danmu("新弹幕")
        w._tick()

    def test_update_config_speed_mapping(self):
        w = self.make_window(speedPct=50)
        # 50% → round(0.5 + 0.5*7.5, 1) = round(4.25, 1) = 4.2（Python 银行家舍入）
        self.assertAlmostEqual(w.config["speed"], 4.2, places=2)

    def test_shrink_tracks_keeps_occupancy(self):
        """轨道数缩小后：保留弹幕的轨道必须重新标记占用，新弹幕不能叠到旧弹幕轨道上"""
        w = self.make_window(tracks=4)
        w.config["tracks"] = 4
        w.track_occupied = [False] * 4
        w._add_danmu("A")   # track 0
        w._add_danmu("B")   # track 1
        # 缩小到 2 个轨道
        w.update_config({"tracks": 2})
        self.assertEqual(len(w.danmu_list), 2)
        # 保留弹幕轨道应被标记占用
        self.assertTrue(w.track_occupied[0])
        self.assertTrue(w.track_occupied[1])
        # 新弹幕不应分到已占轨道（被拒绝，不进列表）
        before = len(w.danmu_list)
        w._add_danmu("C")
        self.assertEqual(len(w.danmu_list), before, "轨道全满时新弹幕应被拒绝（无重叠）")

    def test_config_reload_restarts_stopped_engine(self):
        """引擎停止后 config reload 自动拉起，且 _engine_ref 指向新引擎（修复 server.engine 过期问题）"""
        import zaiganma_app as app_mod
        w = self.make_window()
        fake_engine = mock.Mock()
        fake_engine.running = False
        app_mod._engine_ref = fake_engine
        try:
            with mock.patch.object(app_mod, "DanmuEngine", return_value=fake_engine) as m:
                app_mod._apply_config_reload(w, {"fontSize": 32})
                m.assert_called_once_with(w)
                fake_engine.start.assert_called_once()
            self.assertIs(app_mod._engine_ref, fake_engine, "配置重载后 _engine_ref 应指向新引擎")
            self.assertEqual(w.config["font_size"], 32, "配置应真正生效")
        finally:
            app_mod._engine_ref = None

    def test_config_reload_running_engine_not_duplicated(self):
        """引擎运行中时 config reload 不应重复创建引擎（防双引擎）"""
        import zaiganma_app as app_mod
        w = self.make_window()
        running_engine = mock.Mock()
        running_engine.running = True
        app_mod._engine_ref = running_engine
        try:
            with mock.patch.object(app_mod, "DanmuEngine") as m:
                app_mod._apply_config_reload(w, {"fontSize": 33})
                m.assert_not_called()
            self.assertIs(app_mod._engine_ref, running_engine)
        finally:
            app_mod._engine_ref = None

    def test_send_through_queue(self):
        w = self.make_window(tracks=2)
        w.send("队列弹幕")
        self.assertFalse(w.msg_queue.empty())
        w._tick()
        self.assertEqual(len(w.danmu_list), 1)
        self.assertEqual(w.danmu_list[0].text, "队列弹幕")

    def test_clear_message_handled(self):
        w = self.make_window(tracks=2)
        w.send("aaa")
        w.clear()  # 走队列的字符串清空指令
        w.send("bbb")
        w._tick()
        self.assertEqual(len(w.danmu_list), 1)
        self.assertEqual(w.danmu_list[0].text, "bbb")


if __name__ == "__main__":
    unittest.main()
