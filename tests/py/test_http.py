# -*- coding: utf-8 -*-
"""在干嘛 — HTTP API 端点测试（真 HTTPServer + 假 window/engine，覆盖 /status /toggle /send /config 等）
不依赖 Qt：handler 只依赖 window 对象与全局 _engine_ref
"""
import json
import os
import queue
import sys
import threading
import unittest
import http.client
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'python'))
import zaiganma_app as app

app.log = lambda *a, **k: None


class FakeWindow:
    def __init__(self):
        self.msg_queue = queue.Queue()
        self.sent = []
        self.config = {
            "font_size": 30, "tracks": 5,
            "_visionApiKey": "secret-key", "_visionBaseUrl": "http://secret",
            "visionModelId": "m", "styles": ["casual"],
        }

    def send(self, text, **kw):
        self.sent.append(text)

    def clear(self):
        self.msg_queue.put("__CLEAR__")

    def update_config(self, data):
        self.config.update(data)


class FakeEngine:
    def __init__(self, running=True):
        self.running = running
        self.idle_paused = False
        self.stopped = False

    def stop(self):
        self.running = False
        self.stopped = True

    def start(self):
        pass

    def generate_now(self):
        pass


class TestHttpApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.window = FakeWindow()
        cls.engine = FakeEngine(running=True)
        app._engine_ref = cls.engine
        port = app.find_free_port(21000, 50)
        cls.server = app.HTTPServer(("127.0.0.1", port), app.ZaiganmaHandler)
        cls.server.window = cls.window
        cls.server.engine = cls.engine
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=3)
        app._engine_ref = None

    def request(self, path, method="GET", body=None):
        # 用 http.client 手动请求：不依赖 urllib 对 4xx 的异常流，状态码和 body 都可控
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_address[1], timeout=5)
        try:
            headers = {}
            payload = None
            if body is not None:
                headers["Content-Type"] = "application/json"
                payload = json.dumps(body).encode("utf-8")
            conn.request(method, path, body=payload, headers=headers)
            resp = conn.getresponse()
            data = resp.read().decode("utf-8")
            status = resp.status
        finally:
            conn.close()
        return status, json.loads(data) if data else {}

    def test_health(self):
        status, data = self.request("/health")
        self.assertEqual(status, 200)
        self.assertEqual(data["app"], "zaiganma")

    def test_status_reflects_engine(self):
        status, data = self.request("/status")
        self.assertEqual(status, 200)
        self.assertEqual(data["running"], True)
        self.assertEqual(data["ok"], True)

    def test_send_post_enqueues(self):
        status, data = self.request("/send", "POST", {"text": "测试弹幕"})
        self.assertEqual(status, 200)
        self.assertTrue(data["ok"])
        self.assertIn("测试弹幕", self.window.sent)

    def test_send_empty_returns_400(self):
        status, data = self.request("/send", "POST", {"text": ""})
        self.assertEqual(status, 400)
        self.assertFalse(data["ok"])

    def test_send_get_returns_405(self):
        # GET /send 已改为拒绝，引导用 POST
        status, data = self.request("/send", "GET")
        self.assertEqual(status, 405)

    def test_clear_works(self):
        self.window.msg_queue.put("残留")
        status, data = self.request("/clear")
        self.assertEqual(status, 200)
        self.assertTrue(data["ok"])

    def test_config_hides_secrets(self):
        status, data = self.request("/config")
        self.assertEqual(status, 200)
        cfg = data["config"]
        self.assertNotIn("_visionApiKey", cfg, "API Key 不应返回")
        self.assertNotIn("_visionBaseUrl", cfg)
        self.assertIn("font_size", cfg)

    def test_toggle_stops_running_engine(self):
        # 自建一个运行中的引擎作为当前状态，避免受其他用例影响
        eng = FakeEngine(running=True)
        app._engine_ref = eng
        try:
            status, data = self.request("/toggle")
            self.assertEqual(status, 200)
            self.assertEqual(data["running"], False)
            self.assertTrue(eng.stopped, "运行中的引擎应被停止")
        finally:
            app._engine_ref = self.engine
            self.engine.running = True

    def test_toggle_restarts_engine_without_duplicate(self):
        # 引擎已停止，/toggle 应通过 _replace_engine 重建（防双引擎）
        app._engine_ref = FakeEngine(running=False)
        new_engine = FakeEngine(running=True)
        try:
            with mock.patch.object(app, "DanmuEngine", return_value=new_engine) as m:
                status, data = self.request("/toggle")
                self.assertEqual(status, 200)
                self.assertEqual(data["running"], True)
                m.assert_called_once()
            self.assertIs(app._engine_ref, new_engine, "_engine_ref 应指向新引擎")
        finally:
            app._engine_ref = self.engine
            self.engine.running = True

    def test_config_reload_enqueues(self):
        # 清空队列后发配置重载
        while not app._config_reload_queue.empty():
            app._config_reload_queue.get_nowait()
        status, data = self.request("/config/reload", "POST", {"fontSize": 40})
        self.assertEqual(status, 200)
        self.assertTrue(data["ok"])
        self.assertFalse(app._config_reload_queue.empty(), "配置应进入重载队列")

    def test_unknown_path_returns_404(self):
        status, data = self.request("/nonexistent", "POST", {"x": 1})
        self.assertEqual(status, 404)
        self.assertFalse(data["ok"])

    def test_invalid_json_returns_400(self):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_address[1], timeout=5)
        try:
            conn.request("POST", "/config/reload", body=b"{broken json",
                         headers={"Content-Type": "application/json"})
            resp = conn.getresponse()
            status = resp.status
            resp.read()
        finally:
            conn.close()
        self.assertEqual(status, 400)


if __name__ == "__main__":
    unittest.main()
