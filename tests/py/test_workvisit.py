# -*- coding: utf-8 -*-
"""在干嘛 — 闲不住（work-visit）集成测试
覆盖：is_workvisit_available / load_workvisit_vars 的 mtime 缓存 / get_buddy_mvu_context
"""
import json
import os
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'python'))
import zaiganma_app as app

app.log = lambda *a, **k: None


class BaseWorkVisitTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.old_home = os.environ.get("HANA_HOME")
        os.environ["HANA_HOME"] = self.tmpdir
        # 重置模块级缓存，保证每个测试从干净状态开始
        app._HANA_HOME = None
        app._WORKVISIT_PATH = None
        app._WORKVISIT_CACHE = {}
        app._WORKVISIT_MTIME = 0
        self.data_dir = os.path.join(self.tmpdir, "data", "work-visit")
        os.makedirs(self.data_dir, exist_ok=True)
        self.path = os.path.join(self.data_dir, "data.json")

    def tearDown(self):
        os.environ.pop("HANA_HOME", None)
        if self.old_home:
            os.environ["HANA_HOME"] = self.old_home
        app._HANA_HOME = None
        app._WORKVISIT_PATH = None
        app._WORKVISIT_CACHE = {}
        app._WORKVISIT_MTIME = 0
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def write_data(self, partners):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump({"partnerConfig": partners}, f)
        # 固定 mtime，方便精确控制
        self._fixed_ts = int(time.time())
        self.set_mtime(self._fixed_ts)

    def set_mtime(self, ts):
        os.utime(self.path, (ts, ts))


class TestWorkVisitAvailable(BaseWorkVisitTest):
    def test_no_file_false(self):
        self.assertFalse(app.is_workvisit_available())

    def test_with_partner_config_true(self):
        self.write_data({"hanako": {"variables": {"energy": 80}}})
        self.assertTrue(app.is_workvisit_available())

    def test_empty_partner_config_false(self):
        self.write_data({})
        self.assertFalse(app.is_workvisit_available())

    def test_broken_json_false(self):
        with open(self.path, "w", encoding="utf-8") as f:
            f.write("{broken")
        self.assertFalse(app.is_workvisit_available())


class TestLoadWorkvisitVars(BaseWorkVisitTest):
    def test_returns_variables(self):
        self.write_data({"hanako": {"variables": {"energy": 80, "mood": 60, "affection": 5}}})
        vars = app.load_workvisit_vars("hanako")
        self.assertEqual(vars["energy"], 80)
        self.assertEqual(vars["affection"], 5)

    def test_missing_buddy_returns_none(self):
        self.write_data({"hanako": {"variables": {"energy": 80}}})
        self.assertIsNone(app.load_workvisit_vars("nobody"))

    def test_no_file_returns_none(self):
        self.assertIsNone(app.load_workvisit_vars("hanako"))

    def test_mtime_cache_prevents_reread(self):
        """mtime 未变化时复用缓存（防频繁读盘）；这是伙伴状态实时性的关键"""
        self.write_data({"hanako": {"variables": {"energy": 80}}})
        first = app.load_workvisit_vars("hanako")
        self.assertEqual(first["energy"], 80)
        # 修改文件内容但保持 mtime 不变
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump({"partnerConfig": {"hanako": {"variables": {"energy": 10}}}}, f)
        os.utime(self.path, (self._fixed_ts, self._fixed_ts))
        second = app.load_workvisit_vars("hanako")
        self.assertEqual(second["energy"], 80, "mtime 未变应返回缓存值")

    def test_mtime_change_triggers_reread(self):
        self.write_data({"hanako": {"variables": {"energy": 80}}})
        app.load_workvisit_vars("hanako")
        # 修改内容并更新 mtime
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump({"partnerConfig": {"hanako": {"variables": {"energy": 10}}}}, f)
        self.set_mtime(int(time.time()) + 10)
        refreshed = app.load_workvisit_vars("hanako")
        self.assertEqual(refreshed["energy"], 10, "mtime 变化后应重新读取")

    def test_broken_json_returns_none_no_crash(self):
        with open(self.path, "w", encoding="utf-8") as f:
            f.write("{broken")
        self.assertIsNone(app.load_workvisit_vars("hanako"))


class TestGetBuddyMvuContext(BaseWorkVisitTest):
    def test_with_vars_returns_state_text(self):
        self.write_data({"hanako": {"variables": {"energy": 90, "mood": 90, "affection": 90}}})
        ctx = app.get_buddy_mvu_context("hanako", "玥儿")
        self.assertIsNotNone(ctx)
        self.assertIn("玥儿", ctx)
        self.assertIn("很亲密", ctx)

    def test_without_vars_returns_none(self):
        self.write_data({"hanako": {"variables": {}}})
        self.assertIsNone(app.get_buddy_mvu_context("hanako", "玥儿"))

    def test_empty_buddy_id_returns_none(self):
        self.assertIsNone(app.get_buddy_mvu_context("", "玥儿"))


if __name__ == "__main__":
    unittest.main()
