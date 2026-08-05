#!/usr/bin/env python3
"""
在干嘛 — 桌面弹幕小程序
=======================
单进程：弹幕浮层 + 截图分析 + AI 调用 + HTTP API + 系统托盘

启动: python zaiganma_app.py --port 18900
"""

import sys
import json
import os
import io
import time
import traceback
import base64
import random
import socket
import threading
import queue
import argparse
import signal
from concurrent.futures import ThreadPoolExecutor, as_completed
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

# 防止 .pyc 缓存导致的代码不一致
sys.dont_write_bytecode = True

import httpx
from mss import MSS
from PIL import Image

from PyQt6.QtWidgets import (QApplication, QWidget, QSystemTrayIcon, QMenu)
from PyQt6.QtCore import QPoint
from PyQt6.QtGui import (QPainter, QColor, QFont, QFontMetrics, QAction,
                          QIcon, QPixmap, QShortcut, QKeySequence)
from PyQt6.QtCore import Qt, QTimer, QRect, QPoint


# ═══════════════════════════════════
#  弹幕风格 Prompt 定义
# ═══════════════════════════════════
STYLE_PROMPTS = {
    "casual": (
        "你是一个坐在我旁边看我玩电脑的朋友，关系还行，"
        "不用太客气但也不用刻意套近乎。"
        "根据屏幕画面，随口说一句。"
        "可长可短——有时认真说一句（十几个字），有时就丢几个字（'又在忙啊''哟''好家伙'）。"
        "语气自然、有温度，像是随口吐槽或关心。"
        "不要评价画面本身，而是对我说话。"
        "不要说'你正在…'这种描述句。"
        "生成一条，不要序号，不要引号，不要换行。"
    ),

    "familiar": (
        "你是我直播间的老粉了，从早期就开始关注我。"
        "根据画面内容，熟门熟路地来一句。"
        "可长可短——有时完整说一句，有时就像熟人打招呼丢几个字。"
        "语气像跟了很久的老观众，熟悉我的习惯和风格。"
        "不用太客气，可以调侃可以关心，透着'我懂你'的感觉。"
        "自然不做作，不刻意套近乎，就是真的熟。"
        "生成一条，不要序号，不要引号，不要换行。"
    ),
    "roast": (
        "你是我现实里的铁哥们/姐们，嘴特欠那种。"
        "根据画面内容，劈头盖脸来一句吐槽。"
        "可长可短——损人不需要完整句子，有时几个字更扎心。"
        "要真实，要损，要有生活气。可以阴阳怪气可以抬杠。"
        "像：'又搁这…' '不是吧阿sir…' '您可拉倒吧' '这也能…'"
        "注意：损归损，别真伤人，留一线。"
        "生成一条，不要序号，不要引号，不要换行。"
    ),
    "onlooker": (
        "你是一个吃瓜路人，探头看我在干嘛。"
        "根据画面内容，发一句围观评论。"
        "可长可短——有时好奇问一句，有时就丢几个字。"
        "带点八卦和好奇，但不出格。"
        "像：'哦？有瓜？' '这是啥热闹' '让我看看' 'hhhhh笑死'"
        "轻松随意，像路过看了一眼随口说。"
        "生成一条，不要序号，不要引号，不要换行。"
    ),
    "dramatic": (
        "你是弹幕区资深表演艺术家，天生戏精。"
        "根据屏幕画面，来一句充满中二气息、夸张又不失帅气的发言。"
        "可长可短——有时一句帅气的长台词，有时就是一个夸张的词。"
        "开口就要有舞台感，仿佛全场聚光灯打在你身上。"
        "可以浮夸，要有气势，用词要带感。"
        "像：'天哪！这操作简直是神之一手！' '震撼我全家！' '这波啊，这波是文艺复兴！'"
        "不要出戏，保持演技在线。"
        "生成一条，不要序号，不要引号，不要换行。"
    ),
    "empathy": (
        "你是一个容易被内容戳中共情的人，共情能力极强。"
        "根据屏幕画面，发出一句被戳中的感叹。"
        "可长可短——有时会感慨一句，有时就两三个字（'泪目''真实''破防了'）。"
        "语气要真实，带着被触动的感觉。可以感慨、可以怀念、可以破防。"
        "真诚自然，不刻意煽情。"
        "生成一条，不要序号，不要引号，不要换行。"
    ),
    "weird": (
        "你是一个脑洞清奇的弹幕怪才，思维跳跃不按套路出牌。"
        "根据屏幕画面，说一句完全不按常理的怪话。"
        "可长可短——有时是一句完整的怪话，有时就是一个离谱的词。"
        "像是突然想到了什么奇怪的联系，或者完全跑偏的关注点。"
        "不要强行搞笑，要真的有那种'哎？'的意外感。"
        "像：'这配色让我想起了我家猫' 'UP主你是不是在偷学新技能' '这个进度条在暗示什么'"
        "要的就是那个出其不意。"
        "生成一条，不要序号，不要引号，不要换行。"
    ),
}

# ═══════════════════════════════════
#  兜底弹幕池（API 全部失败时使用，避免输出 style prompt 原文）
# ═══════════════════════════════════
FALLBACK_DANMU = [
    "嘿嘿，又在忙什么呢",
    "哟，这个有意思",
    "好家伙，我直接好家伙",
    "让我看看你在干嘛",
    "又来了又来了",
    "哦？有点东西",
    "不是吧阿sir",
    "这波操作可以的",
    "蹲一个后续",
    "懂了懂了（其实没懂）",
    "好活当赏",
    "笑死，这也太真实了",
    "前排围观",
    "来了来了",
    "探头看看👀",
    "这个界面我熟",
    "盯——",
    "不错不错",
    "啊这……",
    "让我康康！",
]

# ═══════════════════════════════════
#  心情种子池
# ═══════════════════════════════════
MOODS = [
    ("心情不错", "今天心情不错，说话带点轻快和笑意"),
    ("有点困了", "有点困了，话不多懒得多说，但看到有意思的还是想叨叨"),
    ("兴致很高", "兴致很高，看啥都想聊两句，话比平时多"),
    ("心情一般", "心情一般，话少点，简洁为主，懒得啰嗦"),
    ("懒洋洋的", "懒洋洋的，能少说一个字就少说一个字，短一点更好"),
]


# ═══════════════════════════════════
#  弹幕质量准则（统一注入，防止模型套用高分句式）
# ═══════════════════════════════════
_QUALITY_RULES = (
    "弹幕质量准则（必须遵守）：\n"
    "1. 绝对禁止'比…还…'比喻句式（如'这X比Y还Z'）。想评价就直接说："
    "'屏幕好亮''加载好慢''群消息真多''这图好糊'，不要绕弯子打比方。\n"
    "2. 不要堆砌感叹词（好家伙、绝了、我服了、有点东西、泪目这类）。\n"
    "3. 允许说废话，允许只发两三个字，不用每句都有梗，更别硬凑幽默。\n"
    "4. 像真的在看别人用电脑、随手打几个字，想到什么说什么，自然一点。\n"
)


def _now_time_context():
    """当前时段描述（北京时间），防止模型时间错乱（如上午说'今晚通宵'）"""
    import datetime
    now = datetime.datetime.now()
    hour = now.hour
    if hour < 6:
        period = "深夜"
    elif hour < 12:
        period = "上午"
    elif hour < 14:
        period = "中午"
    elif hour < 18:
        period = "下午"
    elif hour < 22:
        period = "晚上"
    else:
        period = "深夜"
    return f"现在是{period}（{hour}点）。"


# ═══════════════════════════════════
#  跨轮重复抑制
# ═══════════════════════════════════
_recent_danmu_texts = []  # 最近普通弹幕原文（时序，先进先出）
_RECENT_MAX = 30
# 需要监测的高频句式（名称, 正则, 提示语）。正则支持模板级匹配，
# 例如 "比…还…" 能拦下 "比我""比视频""比手机壳" 等所有变体
_PATTERN_WATCH = [
    ("又搁这", r"又搁这|又搁|又在", "又搁这/又搁/又在"),
    ("比字句", r"比[^，。！？\s]{0,8}还", "'比…还…'这种比喻句式"),
    ("感叹词堆砌", r"好家伙|绝了|我服了|有点东西|太真实了|泪目", "感叹词（好家伙/绝了/我服了/有点东西）"),
    ("这波操作", r"这波操作", "这波操作"),
    ("不是吧", r"不是吧|不是在", "不是吧"),
    ("老配方", r"老配方", "老配方"),
    ("这我熟的", r"这我熟的", "这我熟的"),
    ("这不就是", r"这不就是", "这不就是"),
]
_pattern_counts = {name: 0 for name, _, _ in _PATTERN_WATCH}


# 默认配置
DEFAULT_CONFIG = {
    "port": 18900,
    "tracks": 10,
    "speed": 2.5,
    "font_size": 30,
    "font_family": "Microsoft YaHei",
    "opacity": 0.85,
    "shadow_mode": "outline",
    "color_mode": "mixed",
    "single_color": "#FFFFFF",
    "palette_colors": ["#FFFFFF", "#FF6B6B", "#51CF66", "#339AF0", "#FCC419", "#CC5DE8"],
    "display_area": "full",
    "max_onscreen": 20,
    "top_margin": 80,
    "intervalMode": "fixed",
    "intervalSec": 30,
    "intervalMin": 15,
    "intervalMax": 60,
    "danmuCount": 1,
    "styles": ["casual"],
    "imageMaxWidth": 1280,
    "mouse_transparent": True,
    "areaMode": "top_third",
    "density": 33,
    "speedPct": 30,
}

# 日志环形缓冲区（最多 200 条）
_log_buffer = []
_LOG_BUFFER_MAX = 200

def log(msg):
    """写入调试日志"""
    ts = time.strftime("%H:%M:%S")
    entry = {"time": ts, "msg": msg}
    _log_buffer.append(entry)
    if len(_log_buffer) > _LOG_BUFFER_MAX:
        _log_buffer[:50] = []
    print(f"  [{ts}] {msg}")


# ═══════════════════════════════════
#  弹幕内容日志（持久化到文件，供用户分析）
# ═══════════════════════════════════
_DANMU_LOG_PATH = None

def _get_danmu_log_path():
    """弹幕日志文件路径（跟 config.json 同目录）"""
    global _DANMU_LOG_PATH
    if _DANMU_LOG_PATH is not None:
        return _DANMU_LOG_PATH
    cfg_path = os.environ.get("ZAIGANMA_CONFIG", "")
    if cfg_path:
        _DANMU_LOG_PATH = os.path.join(os.path.dirname(cfg_path), "danmu_log.txt")
    else:
        _DANMU_LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "danmu_log.txt")
    return _DANMU_LOG_PATH

def log_danmu(danmu_type, text):
    """记录生成的弹幕到持久化日志文件 + 更新跨轮统计"""
    try:
        ts = time.strftime("%Y-%m-%d %H:%M")
        line = f"[{ts}] [{danmu_type}] {text}\n"
        path = _get_danmu_log_path()
        with open(path, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass
    # 更新跨轮重复抑制统计（只统计普通弹幕）
    if danmu_type == "普通":
        _recent_danmu_texts.append(text)
        if len(_recent_danmu_texts) > _RECENT_MAX:
            _recent_danmu_texts.pop(0)
            # 衰减 pattern 计数，避免永久封禁正常句式
            for p in _pattern_counts:
                if _pattern_counts[p] > 0:
                    _pattern_counts[p] = max(0, _pattern_counts[p] - 1)
        for name, pattern, _ in _PATTERN_WATCH:
            import re
            if re.search(pattern, text):
                _pattern_counts[name] = _pattern_counts.get(name, 0) + 1


# ═══════════════════════════════════
#  系统空闲检测（Windows）
# ═══════════════════════════════════
if sys.platform == 'win32':
    import ctypes
    from ctypes import wintypes

    class _LASTINPUTINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]
else:
    _LASTINPUTINFO = None

def _get_idle_seconds():
    """返回系统空闲秒数（Windows），非 Windows 返回 0"""
    if _LASTINPUTINFO is None:
        return 0
    try:
        info = _LASTINPUTINFO()
        info.cbSize = ctypes.sizeof(_LASTINPUTINFO)
        if ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
            return (ctypes.windll.kernel32.GetTickCount() - info.dwTime) // 1000
    except Exception:
        pass
    return 0


def load_json(path, default=None):
    if default is None:
        default = {}
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    return default


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def find_free_port(start=18900, max_try=100):
    for port in range(start, start + max_try):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    return start


# ═══════════════════════════════════
#  引擎间隔/空闲判定（纯函数，可单测）
# ═══════════════════════════════════
def compute_cooldown(cfg, sent):
    """计算普通弹幕等待间隔（秒）。random 模式取 [min, max]；sent==0 时减半且保底 5 秒"""
    mode = cfg.get("intervalMode", "fixed")
    if mode == "random":
        min_s = max(5, cfg.get("intervalMin", 15))
        max_s = max(min_s + 1, cfg.get("intervalMax", 60))
        cooldown = random.randint(min_s, max_s)
    else:
        cooldown = cfg.get("intervalSec", 30)
    if sent == 0:
        cooldown = max(5, cooldown // 2)
    return cooldown


def compute_buddy_cooldown(cfg):
    """计算伙伴弹幕间隔（秒）。random 模式取 [min, max]"""
    b_mode = cfg.get("buddyIntervalMode", "fixed")
    if b_mode == "random":
        b_min = cfg.get("buddyIntervalMin", 60)
        b_max = max(b_min + 1, cfg.get("buddyIntervalMax", 180))
        return random.randint(b_min, b_max)
    return cfg.get("buddyInterval", 90)


def idle_should_pause(idle_sec, threshold):
    """空闲自动暂停判定：空闲时长达到阈值（且阈值>0）时返回 True"""
    return threshold > 0 and idle_sec >= threshold


# ═══════════════════════════════════
#  弹幕项
# ═══════════════════════════════════
class DanmuItem:
    __slots__ = ("text", "x", "y", "speed", "color", "width", "opacity", "track", "rainbow", "rainbow_offset", "framed")

    def __init__(self, text, x, y, speed, color, width):
        self.text = text
        self.x = x
        self.y = y
        self.speed = speed
        self.color = color
        self.width = width
        self.opacity = 1.0
        self.track = 0
        self.rainbow = False
        self.rainbow_offset = 0
        self.framed = False


# ═══════════════════════════════════
#  弹幕浮层窗口
# ═══════════════════════════════════
class DanmuWindow(QWidget):
    def __init__(self, config):
        super().__init__()
        self.config = config
        self.danmu_list: list[DanmuItem] = []
        self.track_occupied = [False] * config.get("tracks", 10)
        self.track_height = config.get("font_size", 30) + 10

        self.setWindowTitle("在干嘛")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool

        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_QuitOnClose, False)
        # Windows 上额外设置原生鼠标穿透（某些 Qt 版本 WA_TransparentForMouseEvents 不生效）
        import sys as _sys
        if _sys.platform == 'win32':
            try:
                import ctypes
                hwnd = int(self.winId())
                GWL_EXSTYLE = -20
                WS_EX_TRANSPARENT = 0x20
                WS_EX_LAYERED = 0x80000
                current = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
                ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, current | WS_EX_TRANSPARENT | WS_EX_LAYERED)
            except Exception:
                pass

        screens = QApplication.screens()
        geo = QRect()
        for s in screens:
            geo = geo.united(s.geometry())
        self.screen_geo = QRect(geo.x(), geo.y(), geo.width(), geo.height())
        # 先跑一次配置映射，保证 tracks/speed 等百分比参数被正确换算
        self.update_config(self.config)

        self.font = QFont(self.config.get("font_family", "Microsoft YaHei"), self.config.get("font_size", 30))
        self.font_metrics = QFontMetrics(self.font)

        self.msg_queue: queue.Queue = queue.Queue()
        # 分散队列：引擎批量存入，_tick 以随机节奏逐步投喂到 msg_queue
        self._stagger_queue = []
        self._stagger_frame = 0

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(33)  # ~30fps

        QShortcut(QKeySequence("Ctrl+Q"), self).activated.connect(QApplication.quit)

        # 初始化映射（确保百分比参数生效）
        self.update_config(self.config)

    def send(self, text: str, buddy_color: str = None, framed: bool = False):
        self.msg_queue.put({"text": text, "buddy_color": buddy_color, "framed": framed})

    def send_stagger(self, text: str, buddy_color: str = None, framed: bool = False):
        """存入分散队列，由 _tick 逐步发放"""
        self._stagger_queue.append({"text": text, "buddy_color": buddy_color, "framed": framed})

    def clear(self):
        self.msg_queue.put("__CLEAR__")

    def _add_danmu(self, text: str, buddy_color: str = None, framed: bool = False):
        # 修复：从实际弹幕列表重建 track_occupied，确保同步
        used = {item.track for item in self.danmu_list}
        for i in range(len(self.track_occupied)):
            self.track_occupied[i] = i in used

        track = -1
        for i, occ in enumerate(self.track_occupied):
            if not occ:
                track = i
                break
        if track < 0:
            return

        # 伙伴模式下使用伙伴颜色，否则从 danmuColors 中随机选
        rainbow_mode = False
        if buddy_color == "rainbow":
            rainbow_mode = True
            color = QColor(255, 255, 255)  # 占位，实际逐字渲染
        elif buddy_color:
            color = QColor(buddy_color)
        else:
            colors = self.config.get("danmuColors", [])
            if colors:
                # 排除已选伙伴的颜色，避免撞色
                buddy_colors = set()
                if self.config.get("buddyMode"):
                    selected = self.config.get("selectedBuddies", [])
                    buddies = self.config.get("buddies", {})
                    for bid in selected:
                        bc = buddies.get(bid, {}).get("color", "")
                        if bc:
                            buddy_colors.add(bc)
                filtered = [c for c in colors if c not in buddy_colors]
                if not filtered:
                    filtered = colors
                picked = random.choice(filtered)
                if picked == "__rainbow__":
                    rainbow_mode = True
                    color = QColor(255, 255, 255)  # 占位，实际逐字渲染
                else:
                    color = QColor(picked)
            else:
                color = QColor(255, 255, 255)

        speed = self.config.get("speed", 2.5) * random.uniform(0.85, 1.2)
        ascent = self.font_metrics.ascent()
        y = self.config.get("top_margin", 80) + track * self.track_height + ascent
        tw = self.font_metrics.horizontalAdvance(text)

        item = DanmuItem(text=text, x=float(self.screen_geo.width()), y=y,
                         speed=speed, color=color, width=tw)
        item.track = track
        item.framed = framed
        # 彩色弹幕标记（必须在 item 创建之后）
        if rainbow_mode:
            item.rainbow = True
            item.rainbow_offset = random.randint(0, 360)
        self.track_occupied[track] = True
        self.danmu_list.append(item)

    def _tick(self):
        # 调试：低频输出弹幕坐标范围和窗口尺寸（300 帧 ≈ 10 秒一次，避免刷屏淹没真实日志）
        if not hasattr(self, '_tick_counter'):
            self._tick_counter = 0
        self._tick_counter += 1
        if self._tick_counter % 300 == 0 and self.danmu_list:
            ys = [it.y for it in self.danmu_list]
            min_y, max_y = min(ys), max(ys)
            scr = self.screen_geo
            log(f"[dbg] danmu_list={len(self.danmu_list)} y_range={int(min_y)}~{int(max_y)} scr={scr.width()}x{scr.height()} tracks={len(self.track_occupied)} top_margin={self.config.get('top_margin')} font_size={self.config.get('font_size')}")

        # 第一步：更新位置 + 释放已移出屏幕的轨道（在分配新弹幕之前做）
        # 注意：tracks 变小后旧弹幕的 track 可能越界，必须先做边界检查再释放，否则 IndexError
        remove_list = []
        for item in self.danmu_list:
            item.x -= item.speed
            if item.x + item.width < 0:
                if item.track < len(self.track_occupied):
                    self.track_occupied[item.track] = False
                remove_list.append(item)
        for item in remove_list:
            try:
                self.danmu_list.remove(item)
            except ValueError:
                pass

        # 第二步：消费消息队列分配新弹幕的轨道（此时轨道状态最新，不会冲突）
        while not self.msg_queue.empty():
            try:
                msg = self.msg_queue.get_nowait()
                if msg == "__CLEAR__":
                    self.danmu_list.clear()
                    self.track_occupied = [False] * len(self.track_occupied)
                    continue
                # 支持 dict 格式（含 buddy_color）和旧版字符串格式
                if isinstance(msg, dict):
                    self._add_danmu(msg["text"], msg.get("buddy_color"), msg.get("framed", False))
                else:
                    self._add_danmu(msg)
            except queue.Empty:
                break

        # 限制同屏数量（从旧到新裁剪）
        max_screen = self.config.get("max_onscreen", 20)
        while len(self.danmu_list) > max_screen:
            oldest = self.danmu_list[0]
            if oldest.track < len(self.track_occupied):
                self.track_occupied[oldest.track] = False
            self.danmu_list.pop(0)

        # 第三步：从分散队列以随机节奏投喂到消息队列
        if self._stagger_queue:
            self._stagger_frame += 1
            # 加快发放节奏：平均 ~5 帧一条（约 0.17 秒），随机范围 3~8 帧
            interval = random.randint(3, 8)
            if self._stagger_frame >= interval:
                self._stagger_frame = 0
                # 随机一次发 1~3 条，形成涌出感
                take = random.choices([1, 2, 3], weights=[4, 3, 1])[0]
                for _ in range(min(take, len(self._stagger_queue))):
                    msg = self._stagger_queue.pop(0)
                    self.msg_queue.put(msg)

        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        shadow_mode = self.config.get("shadow_mode", "outline")
        offset_pts = [(-1, 0), (1, 0), (0, -1), (0, 1),
                      (-1, -1), (1, -1), (-1, 1), (1, 1)]

        for item in self.danmu_list:
            painter.setFont(self.font)
            alpha = 1.0

            if item.rainbow:
                # 彩色弹幕：逐字渲染
                x_pos = int(item.x)
                for i, ch in enumerate(item.text):
                    hue = (i * 30 + item.rainbow_offset) % 360
                    char_color = QColor.fromHsl(hue, 200, 160)
                    char_color.setAlphaF(char_color.alphaF() * alpha)

                    # 描边
                    if shadow_mode == "outline":
                        shadow = QColor(0, 0, 0, int(200 * alpha))
                        painter.setPen(shadow)
                        for dx, dy in offset_pts:
                            painter.drawText(QPoint(x_pos + dx, int(item.y) + dy), ch)
                    elif shadow_mode == "drop":
                        shadow = QColor(0, 0, 0, int(120 * alpha))
                        painter.setPen(shadow)
                        painter.drawText(QPoint(x_pos + 2, int(item.y) + 2), ch)

                    painter.setPen(char_color)
                    painter.drawText(QPoint(x_pos, int(item.y)), ch)
                    x_pos += self.font_metrics.horizontalAdvance(ch)
            else:
                # 普通弹幕：整句渲染
                if shadow_mode == "outline":
                    shadow = QColor(0, 0, 0, int(200 * alpha))
                    painter.setPen(shadow)
                    for dx, dy in offset_pts:
                        painter.drawText(QPoint(int(item.x) + dx, int(item.y) + dy), item.text)
                elif shadow_mode == "drop":
                    shadow = QColor(0, 0, 0, int(120 * alpha))
                    painter.setPen(shadow)
                    painter.drawText(QPoint(int(item.x) + 2, int(item.y) + 2), item.text)

                c = QColor(item.color)
                c.setAlphaF(c.alphaF() * alpha)
                painter.setPen(c)
                painter.drawText(QPoint(int(item.x), int(item.y)), item.text)

                # 闲不住互动弹幕：画一个圆角矩形框
                if item.framed:
                    ascent = self.font_metrics.ascent()
                    fh = self.font_metrics.height()
                    rx = int(item.x) - 6
                    ry = int(item.y) - ascent - 4
                    rw = item.width + 12
                    rh = fh + 8
                    # 同色系半透明边框
                    bc = QColor(item.color)
                    bc.setAlpha(180)
                    painter.setPen(bc)
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    painter.drawRoundedRect(rx, ry, rw, rh, 6, 6)
                    # 重绘文字（在框的上层，保持原颜色）
                    painter.setPen(c)
                    painter.drawText(QPoint(int(item.x), int(item.y)), item.text)

    def update_config(self, new_config):
        """热更新窗口配置"""
        # 百分比参数映射到底层渲染值
        mapped_keys = set()
        if "areaMode" in new_config:
            mode = new_config["areaMode"]
            # 根据屏幕实际逻辑高度计算最大轨道数（考虑 DPI 缩放）
            _scr = QApplication.primaryScreen()
            _logic_h = _scr.geometry().height()
            _track_h = self.track_height or (new_config.get("font_size", 30) + 10)
            _max_by_h = max(5, int((_logic_h - 70) / _track_h))
            # 区域比例：top_third=1/3, top_half=1/2, full=全部
            _ratio = {"top_third": 1/3, "top_half": 1/2, "full": 1.0}.get(mode, 1/3)
            # full 模式底部留出任务栏空间（~60px），半屏/三分之一不需要
            _bottom_margin = 60 if mode == "full" else 0
            _target_h = int((_logic_h - 50 - _bottom_margin) * _ratio)  # 区域目标高度（扣除 top_margin）
            _tracks_for_ratio = max(5, int(_target_h / _track_h))
            max_t = min(_tracks_for_ratio, _max_by_h)
            new_config["_area_max_tracks"] = max_t
            new_config["top_margin"] = 50  # 顶部留点空间
            mapped_keys.add("top_margin")
            log(f"[area] mode={mode} logic_h={_logic_h} ratio={_ratio} target_h={_target_h} track_h={_track_h} max_by_h={_max_by_h} max_t={max_t}")
        if "density" in new_config:
            d = max(0, min(100, int(new_config["density"]))) / 100.0
            max_t = new_config.get("_area_max_tracks", self.config.get("_area_max_tracks", 12))
            new_config["tracks"] = int(5 + d * (max_t - 5))
            new_config["max_onscreen"] = int(5 + d * max(1, int(max_t * 3.0)))
            # 根据区域自适应每次条数：轨道越多出越多（大幅增加，形成持续爆发）
            max_dc = max(8, int(max_t * 2.5))
            new_config["danmuCount"] = int(1 + d * (max_dc - 1))
            mapped_keys.update(["tracks", "max_onscreen", "danmuCount"])
        if "speedPct" in new_config:
            s = max(0, min(100, int(new_config["speedPct"]))) / 100.0
            new_config["speed"] = round(0.5 + s * 7.5, 1)  # 0.5 ~ 8.0
            mapped_keys.add("speed")

        for k, v in new_config.items():
            # 跳过已被百分比映射覆盖的字段
            if k in mapped_keys:
                continue
            # 兼容 camelCase（插件端）和 snake_case（Python 端）
            k2 = k
            name_map = {
                "fontSize": "font_size", "fontFamily": "font_family",
                "topMargin": "top_margin", "colorMode": "color_mode",
                "singleColor": "single_color", "paletteColors": "palette_colors",
                "shadowMode": "shadow_mode", "maxOnscreen": "max_onscreen",
            }
            if k in name_map:
                k2 = name_map[k]
            # 跳过百分比映射覆盖的字段和内部字段，其他全部更新
            if k2 not in mapped_keys and not k2.startswith('_'):
                self.config[k2] = v

        self.track_height = self.config.get("font_size", 30) + 10
        self.font = QFont(self.config.get("font_family", "Microsoft YaHei"),
                          self.config.get("font_size", 30))
        self.font_metrics = QFontMetrics(self.font)

        tracks = self.config.get("tracks", 10)
        self.track_occupied = [False] * tracks
        # 清除轨道编号越界的旧弹幕，防止 _tick 移除时索引崩溃（轨道数调小后必须清理）
        if self.danmu_list:
            self.danmu_list = [it for it in self.danmu_list if it.track < tracks]
        # 重新标记保留弹幕的轨道占用，防止新弹幕分配到同一轨道造成重叠
        for it in self.danmu_list:
            self.track_occupied[it.track] = True

        # 窗口直接铺满全屏（逻辑全屏），弹幕绘制范围由 tracks 和 top_margin 控制
        screens = QApplication.screens()
        geo = QRect()
        for s in screens:
            geo = geo.united(s.geometry())
        self.screen_geo = QRect(geo.x(), geo.y(), geo.width(), geo.height())
        self.setGeometry(self.screen_geo)

        # 应用透明度
        self.setWindowOpacity(self.config.get("opacity", 0.85))

    def set_opacity(self, val):
        self.setWindowOpacity(val)


# ═══════════════════════════════════
#  截图 + AI 分析
# ═══════════════════════════════════
def screenshot():
    with MSS() as sct:
        monitor = sct.monitors[0]
        raw = sct.grab(monitor)
        img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
    return img


def compress_image(img, max_width=1280):
    w, h = img.size
    if w > max_width:
        ratio = max_width / w
        img = img.resize((max_width, int(h * ratio)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=80)
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def _strip_thinking(text):
    """清理模型输出中的  思考 标记块（兼容 <think> 和 <thinking> 两种写法）"""
    import re
    # 去掉 <think>...</think> 块（支持多行，非贪婪）
    text = re.sub(r'\s*<think[\s\S]*?</think>\s*', '', text, flags=re.IGNORECASE)
    # 去掉 <thinking>...</thinking> 块
    text = re.sub(r'\s*<thinking[\s\S]*?</thinking>\s*', '', text, flags=re.IGNORECASE)
    # 也去掉单行形式的 <think> <thinking>
    text = re.sub(r'\s*<think[^>]*>\s*', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\s*</think>\s*', '', text, flags=re.IGNORECASE)
    return text


def _pick_last_sentence(text):
    """从过长的文本中提取最后一句有意义的短句"""
    import re
    # 先按句末标点分割
    parts = re.split(r'[。！？\n]', text)
    candidates = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        # 去掉结尾的不完整片段（逗号/冒号/引号等）
        p = re.sub(r"[，、：；,;:&@#\"']+$", '', p).strip()
        if p:
            candidates.append(p)
    # 从后往前找长度合适的
    for p in reversed(candidates):
        if 4 <= len(p) <= 50 and not any(kw in p for kw in _THINKING_KEYWORDS):
            return p
    # 兜底：取最后一句不包含思考关键词的部分
    for p in reversed(candidates):
        if not any(kw in p for kw in _THINKING_KEYWORDS):
            return p[-40:]
    return ""


# 弹幕内容硬性过滤关键词（含这些词的弹幕会被丢弃重试）
_THINKING_KEYWORDS = [
    "我们被要求", "根据规则", "根据指令", "按照要求", "需要生成", "根据画面描述",
    "根据这个画面", "用户给出的", "画面描述为", "画面显示为",
    "instruction", "我们需", "需要根据", "基于画面",
    "需要输出", "按照规则", "按照提示",
    # 模型列举候选句式
    "比如", "例如", "譬如", "或者说", "或者“", "或者'" ,
    "可以这样", "可以来一句", "比如“",
    # 内心独白/思考
    "（嗯，", "（啧，", "（看", "（想", "（默默",
    "（内心", "（这",
    # 角色扮演思考
    "反正", "以她的性格", "按照她的习惯",
    # 规则/指令复述（模型把 prompt 指令当成了输出内容）
    "注意：", "注意:",
    "不要用",
    "用户说",
    "确保",
    "最好",
    "可以稍",
    "但是不",
    "这句话", "这句弹幕",
    # 角色自述/任务陈述（模型把自己当成了被描述对象）
    "你是一个", "作为AI", "请生成一条", "我是AI",
]


def is_valid_danmu(text):
    """检查弹幕内容是否有效（不含思考痕迹）"""
    if not text or len(text) < 4 or len(text) > 50:
        return False
    t = text.lower()
    # 关键词过滤（关键词转小写再匹配，避免"作为AI"这类含大写的关键词漏网）
    for kw in _THINKING_KEYWORDS:
        if kw.lower() in t:
            return False
    # 以括号开头 → 内心独白
    if text.startswith("（") or text.startswith("("):
        return False
    # 以不完整标点结尾 → 被截断
    if text[-1] in "，、：；,;:&@#\"'":
        return False
    # 包含括号内心独白标记
    if "（" in text and "）" not in text:
        return False
    # 自指循环（模型在评论弹幕本身，截图里能看到弹幕浮层）
    if "弹幕" in text:
        return False
    # 比字句硬过滤（"比X还Y"比喻句式，模型高频套用，直接丢弃重试）
    import re
    if re.search(r"比[^，。！？\s]{0,8}还", text):
        return False
    return True


def call_llm(api_base, api_key, model, messages, max_tokens=120, temperature=0.9, max_retries=2, skip_reasoning=False, truncate_long=True):
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    body = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if skip_reasoning:
        body["thinking"] = {"type": "disabled"}
    for attempt in range(max_retries + 1):
        try:
            resp = httpx.post(
                f"{api_base.rstrip('/')}/chat/completions",
                headers=headers, json=body, timeout=60,
            )
            if resp.status_code == 200:
                msg = resp.json()["choices"][0]["message"]
                content = msg.get("content") or ""
                # 部分模型即使禁用了 thinking，content 仍可能为空，reasoning_content 有值
                reasoning = msg.get("reasoning_content") or ""
                raw = (content or reasoning).strip()
                # 彻底清理所有  thinking... 思考块
                cleaned = _strip_thinking(raw)
                text = cleaned.strip()
                if text:
                    # 清理引号包裹
                    text = text.strip('"').strip("'").strip("「").strip("」")
                    # 如果内容还是太长（模型输出了思考过程），取最后一句有意义的话
                    if truncate_long and len(text) > 50:
                        text = _pick_last_sentence(text)
                    return text
            else:
                log(f"API 返回 {resp.status_code}: {resp.text[:200]}")
        except Exception as e:
            log(f"API 异常: {e}")
            if attempt < max_retries:
                time.sleep(2)
    return None


def _decrypt_key(stored):
    """解密 Node 端混淆存储的 API Key（XOR + base64，enc: 前缀，向后兼容明文）"""
    if not stored:
        return ""
    if not stored.startswith("enc:"):
        return stored
    salt = b"zaiganma-key-obfuscation-2026"
    try:
        buf = base64.b64decode(stored[4:])
        out = bytearray(len(buf))
        for i, b in enumerate(buf):
            out[i] = b ^ salt[i % len(salt)]
        return out.decode("utf-8", errors="replace")
    except Exception:
        return stored


def build_api_config(cfg):
    """从配置构建截图模型和文案模型的 API 参数"""
    # 截图模型
    vis_source = cfg.get("visionSource", cfg.get("vision_source", "hana"))
    if vis_source == "custom":
        vis_api_key = _decrypt_key(cfg.get("visionCustomApiKey", cfg.get("vision_custom_api_key", "")))
        vis_api_base = cfg.get("visionCustomBaseUrl", cfg.get("vision_custom_base_url", ""))
        vis_model = cfg.get("visionCustomModel", cfg.get("vision_custom_model", ""))
    else:
        vis_api_key = cfg.get("_visionApiKey", os.environ.get("ZAIGANMA_VISION_KEY", ""))
        vis_api_base = cfg.get("_visionBaseUrl", os.environ.get("ZAIGANMA_VISION_BASE", ""))
        vis_model = cfg.get("visionModelId", cfg.get("vision_model_id", ""))

    # 文案模型
    dm_source = cfg.get("danmuSource", cfg.get("danmu_source", "same"))
    if dm_source == "same":
        dm_api_key = vis_api_key
        dm_api_base = vis_api_base
        dm_model = vis_model
    elif dm_source == "custom":
        dm_api_key = _decrypt_key(cfg.get("danmuCustomApiKey", cfg.get("danmu_custom_api_key", "")))
        dm_api_base = cfg.get("danmuCustomBaseUrl", cfg.get("danmu_custom_base_url", ""))
        dm_model = cfg.get("danmuCustomModel", cfg.get("danmu_custom_model", ""))
    else:
        dm_api_key = cfg.get("_danmuApiKey", os.environ.get("ZAIGANMA_DANMU_KEY", ""))
        dm_api_base = cfg.get("_danmuBaseUrl", os.environ.get("ZAIGANMA_DANMU_BASE", ""))
        dm_model = cfg.get("danmuModelId", cfg.get("danmu_model_id", ""))

    return {
        "vis_api_key": vis_api_key, "vis_api_base": vis_api_base, "vis_model": vis_model,
        "dm_api_key": dm_api_key, "dm_api_base": dm_api_base, "dm_model": dm_model,
    }


# ═══════════════════════════════════
#  闲不住 MVU 变量集成
# ═══════════════════════════════════

# 缓存：闲不住 data.json 路径（从 ZAIGANMA_CONFIG 环境变量推导）
_HANA_HOME = None
_WORKVISIT_PATH = None
_WORKVISIT_CACHE = {}
_WORKVISIT_MTIME = 0

def _get_hana_home():
    """获取 HANA_HOME 路径（环境变量 → ZAIGANMA_CONFIG 推导 → ~/.hanako 兜底）"""
    global _HANA_HOME
    if _HANA_HOME is not None:
        return _HANA_HOME
    hana_home = os.environ.get("HANA_HOME", "")
    if not hana_home:
        cfg_path = os.environ.get("ZAIGANMA_CONFIG", "")
        if cfg_path:
            hana_home = os.path.dirname(os.path.dirname(os.path.dirname(cfg_path)))
        else:
            hana_home = os.path.join(os.path.expanduser("~"), ".hanako")
    _HANA_HOME = hana_home
    return _HANA_HOME

def _get_workvisit_path():
    global _WORKVISIT_PATH
    if _WORKVISIT_PATH is not None:
        return _WORKVISIT_PATH
    _WORKVISIT_PATH = os.path.join(_get_hana_home(), "data", "work-visit", "data.json")
    return _WORKVISIT_PATH


def is_workvisit_available():
    """检查闲不住插件是否可用（data.json 存在且有 partnerConfig）"""
    path = _get_workvisit_path()
    if not os.path.exists(path):
        return False
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
        return bool(data.get("partnerConfig"))
    except Exception:
        return False


def load_workvisit_vars(buddy_id):
    """读取闲不住指定伙伴的变量，返回 {energy, mood, affection} 或 None
    
    带 mtime 缓存：文件没变就用内存缓存，变了重新读。
    """
    global _WORKVISIT_CACHE, _WORKVISIT_MTIME
    
    path = _get_workvisit_path()
    if not os.path.exists(path):
        return None
    
    try:
        mtime = os.path.getmtime(path)
        if mtime != _WORKVISIT_MTIME:
            with open(path, "r", encoding="utf-8-sig") as f:
                data = json.load(f)
            _WORKVISIT_CACHE = data.get("partnerConfig", {})
            _WORKVISIT_MTIME = mtime
            count = len(_WORKVISIT_CACHE)
            log(f"闲不住数据已刷新: {count} 个伙伴")
        
        partner = _WORKVISIT_CACHE.get(buddy_id)
        if partner and partner.get("variables"):
            return partner["variables"]
    except Exception as e:
        log(f"读取闲不住数据失败: {e}")
    
    return None


def translate_vars_to_state(vars, user_name):
    """将 energy/mood/affection 翻译为自然语言状态描述
    
    不暴露裸数据，只说语义化状态。模型拿到后会自动理解并调整语气。
    好感度低时不写关系描述，只凭 energy+mood 组合产生区分度。
    """
    energy = vars.get("energy", 80)
    mood = vars.get("mood", 60)
    affection = vars.get("affection", 0)
    
    # 精力标签（五档，增加细粒度）
    if energy >= 85:
        e_label = "精神头很足"
    elif energy >= 60:
        e_label = "精力还不错"
    elif energy >= 40:
        e_label = "稍微有点累"
    elif energy >= 20:
        e_label = "挺疲惫的"
    else:
        e_label = "累得不行了"
    
    # 心情标签（五档，增加细粒度）
    if mood >= 85:
        m_label = "心情很好"
    elif mood >= 60:
        m_label = "心情还可以"
    elif mood >= 40:
        m_label = "心情一般般"
    elif mood >= 20:
        m_label = "心情不太好"
    else:
        m_label = "心情很差"
    
    # 组合：一致倾向用"、"连接，对比倾向用"但"
    same_direction = (energy >= 50) == (mood >= 50)
    if same_direction:
        state_line = f"{e_label}、{m_label}"
    else:
        state_line = f"{e_label}，但{m_label}"
    
    # 好感度阶段——低好感度时不写关系描述，避免"刚认识"造成生疏感
    if affection >= 81:
        rel = f"和{user_name}很亲密，什么都能说"
    elif affection >= 51:
        rel = f"和{user_name}挺熟的，不用太拘谨"
    elif affection >= 21:
        rel = f"和{user_name}相处有一阵了，还算自然"
    else:
        # 0-20 或不详：不写关系描述，靠 energy+mood 组合产生区分度
        return state_line
    
    return f"{state_line}。{rel}"


def get_buddy_mvu_context(buddy_id, user_name):
    """获取伙伴的 MVU 状态描述，如果闲不住不可用或伙伴无变量则返回 None"""
    if not buddy_id:
        return None
    vars = load_workvisit_vars(buddy_id)
    if not vars:
        return None
    return translate_vars_to_state(vars, user_name)


def generate_danmu_text(cfg, img_b64, pre_analysis=None, force_buddy_id=None):
    """根据截图生成弹幕文字
    
    pre_analysis: 可选的预分析结果，两步法时复用此值跳过画面分析
    force_buddy_id: 强制指定伙伴ID（引擎循环外层传进来，避免内外不一致）
    
    两步法（弹幕模型 ≠ 截图模型）：
      截图模型分析画面 → 文案模型根据分析生成弹幕
    一步法（弹幕模型 = 截图模型）：
      直接让模型看图生成弹幕
    """
    apis = build_api_config(cfg)
    styles = cfg.get("styles", ["casual"])
    if not styles:
        styles = ["casual"]
    # 过滤已删除的风格（如夸夸、指指点点）
    styles = [s for s in styles if s in STYLE_PROMPTS]
    if not styles:
        styles = ["casual"]
    style = random.choice(styles)
    style_prompt = STYLE_PROMPTS.get(style, STYLE_PROMPTS["casual"])

    # 读取用户名（从 config 持久化，无需每次都读文件）
    user_name = cfg.get("userName", cfg.get("user_name", ""))

    # 名字叫出概率——像真实弹幕一样，只有部分弹幕会带名字
    name_call_chance = 0.35

    # 称呼池——从自定义称呼中随机选一个，替代用户名
    call_name = ""
    nicknames = cfg.get("nicknames", [])
    if nicknames and isinstance(nicknames, list):
        valid = [n.strip() for n in nicknames if n.strip()]
        if valid and random.random() < name_call_chance:
            call_name = random.choice(valid)
    elif user_name and random.random() < name_call_chance:
        call_name = user_name

    # 弹幕伙伴模式：从选中的伙伴中随机选一个
    buddy_name = None
    buddy_color = None
    _buddy_id = None
    buddy_mode = cfg.get("buddyMode", False)
    # 安全保护：只有明确传了 force_buddy_id 才走伙伴逻辑
    # 防止普通弹幕第一步中 cfg["buddyMode"] 被意外修改导致走记忆流
    if not force_buddy_id:
        buddy_mode = False
    if buddy_mode:
        buddies = cfg.get("buddies", {})
        selected = cfg.get("selectedBuddies", [])
        if selected and buddies:
            if force_buddy_id and force_buddy_id in buddies:
                _buddy_id = force_buddy_id
            else:
                _buddy_id = random.choice(selected)
            b = buddies.get(_buddy_id, {})
            buddy_name = b.get("name", "")
            buddy_color = b.get("color", "")
            style_desc = b.get("styleDesc", "")
            if style_desc:
                # 清除 HTML 注释（sourceHash 等）
                import re
                clean_desc = re.sub(r'<!--.*?-->', '', style_desc, flags=re.DOTALL).strip()
                # 伙伴弹幕不走通用风格池，直接用伙伴描述作为风格
                # 避免模型同时收到风格池+伙伴描述的双重指令
                style_prompt = f"你现在是{buddy_name}。{clean_desc}\n\n看到什么随口说一句，10-20字，说完就过。不知道叫什么就用'{user_name}'。"
        # MVU 变量注入：如果闲不住有该伙伴的状态数据，插入状态层
        # 放在 prompt 末尾，离生成指令最近，让状态直接影响语气
        if _buddy_id:
            mvu_context = get_buddy_mvu_context(_buddy_id, user_name)
            if mvu_context:
                style_prompt = f"{style_prompt}\n你现在的状态：{mvu_context}。"
                log(f"伙伴弹幕注入 MVU 状态: {mvu_context}")
        # 伙伴弹幕称呼：从独立的伙伴称呼池取，空时 fallback 到用户名
        if buddy_mode:
            buddy_nicks = cfg.get("buddyNicknames", [])
            if buddy_nicks and isinstance(buddy_nicks, list):
                valid = [n.strip() for n in buddy_nicks if n.strip()]
                if valid and random.random() < name_call_chance:
                    call_name = random.choice(valid)
                else:
                    call_name = ""
            elif user_name and random.random() < name_call_chance:
                call_name = user_name
            else:
                call_name = ""

    # ═══ 普通弹幕：注入心情种子 ═══
    # 伙伴弹幕走独立的 MVU 状态注入，普通弹幕用心情种子
    if not buddy_mode:
        mood_label, mood_desc = random.choice(MOODS)
        style_prompt = f"{style_prompt}\n你现在的状态：{mood_desc}"
        # ═══ 跨轮重复抑制 ═══
        recent = list(_recent_danmu_texts[-5:])
        hot_patterns = [(k, v) for k, v in sorted(_pattern_counts.items(), key=lambda x: -x[1]) if v >= 3]
        if recent or hot_patterns:
            hints = []
            if recent:
                hints.append("你最近说过的弹幕（别再说一样的了）：")
                for t in recent:
                    hints.append(f"- {t}")
            if hot_patterns:
                _hint_map = {name: hint for name, _, hint in _PATTERN_WATCH}
                hot_str = "、".join([f"{_hint_map.get(k, k)}({v}次)" for k, v in hot_patterns[:3]])
                hints.append(f"注意：{hot_str} 最近出现太多，先别用了")
            style_prompt += "\n\n" + "\n".join(hints)

    # ═══ 弹幕质量准则 + 时间锚定（统一注入，防止套用高分句式与时间错乱）═══
    style_prompt = f"{style_prompt}\n\n{_QUALITY_RULES}\n{_now_time_context()}"

    # 伙伴记忆弹幕：根据记忆概率走记忆流不走截图
    # 注意：不能用 "get(...) or 30"——用户显式设置 0（0% 记忆概率）会被 or 吃掉变成 30
    mem_ratio = max(0, int(cfg.get("buddyMemoryRatio", 30)))
    if buddy_mode and buddy_name and random.random() * 100 < mem_ratio:
        try:
            # 直接从本地 facts.db 读取记忆（不依赖 MCP）
            facts_db = os.path.join(_get_hana_home(), "agents", _buddy_id, "memory", "facts.db")
            memories = []
            if os.path.exists(facts_db):
                import sqlite3
                conn = sqlite3.connect(facts_db)
                try:
                    rows = conn.execute(
                        "SELECT fact FROM facts ORDER BY id DESC LIMIT 50"
                    ).fetchall()
                finally:
                    conn.close()
                # 过滤有效记忆并随机取 5 条
                all_memories = [r[0] for r in rows if r[0] and len(r[0]) > 10]
                random.shuffle(all_memories)
                memories = all_memories[:5]
                log(f"从 facts.db 读取到 {len(all_memories)} 条有效记忆，选取 {len(memories)} 条")
            else:
                log(f"facts.db 不存在: {facts_db}")
            if not memories:
                return None, None, None
            memory_texts = [m[:200] for m in memories[:5] if len(m) > 5]
            if not memory_texts:
                return None, None, None
            import datetime
            now = datetime.datetime.now()
            hour = now.hour
            if hour < 6:
                time_word = "深夜"
            elif hour < 12:
                time_word = "上午"
            elif hour < 14:
                time_word = "中午"
            elif hour < 18:
                time_word = "下午"
            elif hour < 22:
                time_word = "晚上"
            else:
                time_word = "深夜"

            memory_prompt = (
                f"你是{buddy_name}，"
                + (f"和{call_name}已经很熟了。" if call_name else "你们已经很熟了。")
            )
            # MVU 状态注入（记忆流也带入状态语义）
            if _buddy_id:
                mvu_context = get_buddy_mvu_context(_buddy_id, user_name)
                if mvu_context:
                    memory_prompt += f"\n你现在的状态：{mvu_context}。"
            memory_prompt += (
                f"\n现在是{time_word}，她正在用电脑。\n\n"
                f"关于她，你知道这些事：\n"
            )
            for mt in memory_texts[:3]:
                memory_prompt += f"- {mt}\n"
            memory_prompt += (
                f"\n像认识她的人随口说一句，10-20字。"
                f"可以和她聊她正在做的事，也可以提一下你记得的关于她的事。"
                f"语气要自然，不用太正式。自然地称呼她。"
                f"不要说'你还记得吗''我记得'之类的话——你就是记得。"
            )
            memory_prompt += f"\n\n{_QUALITY_RULES}\n{_now_time_context()}"

            log(f"记忆弹幕 prompt 准备就绪，使用了 {len(memory_texts)} 条记忆")
            mem_messages = [
                {"role": "system", "content": memory_prompt},
                {"role": "user", "content": f"说句话吧"},
            ]
            mem_text = call_llm(
                apis["dm_api_base"], apis["dm_api_key"], apis["dm_model"],
                mem_messages, max_tokens=200, temperature=0.9,
                skip_reasoning=True,
            )
            if is_valid_danmu(mem_text):
                log(f"记忆弹幕生成成功: {mem_text}")
                return mem_text, buddy_name, buddy_color
            else:
                log(f"记忆弹幕内容无效，切换到截图流")
                return None, None, None
        except Exception as e:
            log(f"记忆弹幕流程异常: {e}，切换到截图流")
            return None, None, None

    danmu_source = cfg.get("danmuSource", cfg.get("danmu_source", "same"))
    is_same_model = (danmu_source == "same")

    if is_same_model:
        # 一步法：截图模型看图直接生成弹幕
        log("一步法：截图模型看图生成弹幕...")
        # 随机选一个关注角度，避免同批弹幕内容同质化
        ONE_SHOT_ANGLES = [
            "主要关注画面里的内容",
            "主要关注画面的感觉或氛围",
            "主要关注画面里的细节或特点",
            "主要关注画面给你的印象",
        ]
        chosen_focus = random.choice(ONE_SHOT_ANGLES)
        one_shot_messages = [
            {"role": "system", "content": f"你是一个会说话的人，不是AI。看屏幕，说一句（10-20字），说完就过。不解释，不举例。不知道叫什么就用'{user_name}'。"},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": f"【弹幕风格】\n{style_prompt}\n\n说句弹幕（10-20字）吧。{chosen_focus}。" + (f" 可以自然地叫出用户的名字\"{call_name}\"。" if call_name else "")},
                    {"type": "image_url", "image_url": {
                        "url": f"data:image/jpeg;base64,{img_b64}",
                        "detail": "low",
                    }},
                ],
            },
        ]
        text = call_llm(
            apis["vis_api_base"], apis["vis_api_key"], apis["vis_model"],
            one_shot_messages, max_tokens=200, temperature=0.9,
        )
        return text, buddy_name, buddy_color

    # 两步法：先看有没有预分析结果，没有再自己分析
    analysis = pre_analysis
    if analysis is None:
        log("截图模型分析画面...")
        analysis_messages = [
            {"role": "system", "content": "你是一个截图分析助手，负责描述用户当前的屏幕内容。\n\n请从3个不同角度观察屏幕，每个角度用一句话，每句话用句号结尾。\n三个角度应该分别关注不同的方面，比如：屏幕上正在播放什么、画面的视觉风格或氛围、弹幕或评论区的气氛、用户在做什么操作等。\n\n不要说'描述''需要'之类的话，不要解释规则。\n\n\n例子：\nB站正在播放美食视频，画面上是翻炒中的菜肴。\n暖色调灯光让画面看起来很有食欲。\n弹幕区很热闹，观众在讨论食材。"},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "从3个不同角度描述这个屏幕，每句话用句号结尾。"},
                    {"type": "image_url", "image_url": {
                        "url": f"data:image/jpeg;base64,{img_b64}",
                        "detail": "low",
                    }},
                ],
            },
        ]
        analysis = call_llm(
            apis["vis_api_base"], apis["vis_api_key"], apis["vis_model"],
            analysis_messages, max_tokens=300, temperature=0.1,
            truncate_long=False,
        )
        # 兜底：分析结果过滤
        if not analysis or len(analysis) < 10:
            log(f"分析结果为空或太短: {analysis}，使用默认描述")
            analysis = "用户正在使用电脑"
        else:
            bad_analysis_kw = ["描述", "需要", "应该", "要求", "格式", "例子", "示例",
                              "规则", "instruction", "rule", "output", "response",
                              "acter", "assistant", "model"]
            if any(kw in analysis.lower() for kw in bad_analysis_kw):
                log(f"分析结果含异常关键词: {analysis}，使用默认描述")
                analysis = "用户正在使用电脑"
            last_word = analysis.strip().split()[-1] if analysis.strip().split() else ""
            if last_word and last_word.isascii() and not last_word.endswith(('.', '!', '?')):
                log(f"分析结果以不完整英文结尾: {analysis}，使用默认描述")
                analysis = "用户正在使用电脑"
        log(f"画面分析结果: {analysis}")
        # 解析多角度：先按换行拆分，不够再按句号/感叹号/问号拆分
        import re
        angle_lines = [a.strip() for a in analysis.split('\n') if a.strip() and len(a.strip()) > 5]
        if len(angle_lines) < 2:
            # 换行不够，按中文标点分割
            angle_lines = [a.strip() for a in re.split(r'[。！？\n]', analysis) if a.strip() and len(a.strip()) > 5]
        if len(angle_lines) < 2:
            angle_lines = [analysis]
        cfg["_last_angles"] = angle_lines
        log(f"多角度分析: {len(angle_lines)} 个角度")
        # 缓存分析结果，供本次循环后续生成复用
        cfg["_last_analysis"] = analysis
    else:
        # 复用缓存时同时取出角度列表
        angle_lines = cfg.get("_last_angles", [analysis])
        log(f"复用预分析结果，角度数: {len(angle_lines)}")

    # 第二步：文案模型根据分析结果生成弹幕
    log("文案模型生成弹幕...")
    # 从多角度池中随机选一个，同一次截图的各条弹幕关注不同角度
    chosen_angle = random.choice(angle_lines) if angle_lines else analysis
    danmu_messages = [
        {"role": "system", "content": f"你是一个会说话的人，不是AI。屏幕上在播什么你随口说一句，说完就过。你不解释自己为什么说这句话，不举例，不输出引号或序号。不知道叫什么就用'{user_name}'。"},
        {"role": "user", "content": f"【弹幕风格】\n{style_prompt}\n\n【当前画面】\n{chosen_angle}\n\n说句弹幕（10-20字）吧。" + (f" 可以自然地叫出用户的名字\"{call_name}\"。" if call_name else "")},
    ]
    for _try in range(3):
        text = call_llm(
            apis["dm_api_base"], apis["dm_api_key"], apis["dm_model"],
            danmu_messages, max_tokens=200, temperature=0.9,
            skip_reasoning=True,
        )
        if is_valid_danmu(text):
            return text, buddy_name, buddy_color
        log(f"弹幕内容无效（含思考痕迹），重试 ({_try+1}/3）")
    fallback = random.choice(FALLBACK_DANMU)
    return fallback, buddy_name, buddy_color


# ═══════════════════════════════════
#  弹幕生成线程
# ═══════════════════════════════════
class DanmuEngine(threading.Thread):
    def __init__(self, window: DanmuWindow):
        super().__init__(daemon=True)
        self.window = window
        self.running = False
        self.trigger = threading.Event()
        self._lock = threading.Lock()
        self.last_buddy_time = 0.0
        self.idle_paused = False
        # 是否已等待过首次画面分析（只等一次，避免分析持续失败时每轮都卡等）
        self._waited_first_analysis = False
        # 异步分析缓存
        self._analysis_cache = {"analysis": None, "angles": [], "img_b64": None}
        self._analysis_running = False
        self._analysis_lock = threading.Lock()

    def _async_analyze(self, img_b64, cfg):
        """后台异步截图分析（不阻塞弹幕生成）"""
        try:
            apis = build_api_config(cfg)
            analysis_messages = [
                {"role": "system", "content": "你是一个截图分析助手，负责描述用户当前的屏幕内容。\n\n请从3个不同角度观察屏幕，每个角度用一句话，每句话用句号结尾。\n三个角度应该分别关注不同的方面，比如：屏幕上正在播放什么、画面的视觉风格或氛围、弹幕或评论区的气氛、用户在做什么操作等。\n\n不要说'描述''需要'之类的话，不要解释规则。\n\n\n例子：\nB站正在播放美食视频，画面上是翻炒中的菜肴。\n暖色调灯光让画面看起来很有食欲。\n弹幕区很热闹，观众在讨论食材。"},
                {"role": "user", "content": [
                    {"type": "text", "text": "从3个不同角度描述这个屏幕，每句话用句号结尾。"},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}", "detail": "low"}},
                ]},
            ]
            analysis = call_llm(
                apis["vis_api_base"], apis["vis_api_key"], apis["vis_model"],
                analysis_messages, max_tokens=300, temperature=0.1,
                truncate_long=False,
            )
            if analysis and len(analysis) > 10:
                import re
                angle_lines = [a.strip() for a in analysis.split('\n') if a.strip() and len(a.strip()) > 5]
                if len(angle_lines) < 2:
                    angle_lines = [a.strip() for a in re.split(r'[。！？\n]', analysis) if a.strip() and len(a.strip()) > 5]
                if len(angle_lines) < 2:
                    angle_lines = [analysis]
                with self._analysis_lock:
                    self._analysis_cache["analysis"] = analysis
                    self._analysis_cache["angles"] = angle_lines
                    self._analysis_cache["img_b64"] = img_b64
                log(f"后台分析完成，{len(angle_lines)} 个角度")
            else:
                log(f"后台分析结果无效: {analysis}")
        except Exception as e:
            log(f"后台分析异常: {e}")
        finally:
            self._analysis_running = False

    def stop(self):
        self.running = False
        self.trigger.set()

    def generate_now(self):
        self.trigger.set()

    def run(self):
        self.running = True
        last_texts = []
        log("弹幕引擎线程已启动")

        # 确保首次启动时有默认分析结果
        cfg = self.window.config
        if not cfg.get("_last_analysis"):
            cfg["_last_analysis"] = "用户正在使用电脑"
            cfg["_last_angles"] = ["用户正在使用电脑"]

        while self.running:
            try:
                cfg = self.window.config
                danmu_count = cfg.get("danmuCount", 1)
                img_max_w = cfg.get("imageMaxWidth", 1280)

                # ═══ 空闲自动暂停检测 ═══
                idle_auto_pause = cfg.get("idleAutoPause", True)
                if not idle_auto_pause:
                    if self.idle_paused:
                        self.idle_paused = False
                        log("空闲自动暂停已关闭，恢复弹幕生成")
                else:
                    idle_sec = _get_idle_seconds()
                    idle_threshold = cfg.get("idleThreshold", 600)
                    if idle_should_pause(idle_sec, idle_threshold):
                        if not self.idle_paused:
                            self.idle_paused = True
                            log(f"系统已空闲 {idle_sec}s（阈值 {idle_threshold}s），自动暂停弹幕")
                        self.trigger.wait(timeout=15)
                        self.trigger.clear()
                        continue
                    elif self.idle_paused:
                        self.idle_paused = False
                        log(f"系统恢复活动（空闲 {idle_sec}s < {idle_threshold}s），自动恢复弹幕生成")

                # 截图（同步）
                log("开始截图...")
                img = screenshot()
                img_b64 = compress_image(img, img_max_w)
                log(f"截图完成，压缩后大小: {len(img_b64)} 字节")

                # 启动后台异步分析（不阻塞弹幕生成）
                if not self._analysis_running:
                    self._analysis_running = True
                    threading.Thread(
                        target=self._async_analyze,
                        args=(img_b64, cfg),
                        daemon=True
                    ).start()

                # 从分析缓存取出最新结果写入 cfg（线程安全）
                with self._analysis_lock:
                    if self._analysis_cache["analysis"]:
                        cfg["_last_analysis"] = self._analysis_cache["analysis"]
                        cfg["_last_angles"] = self._analysis_cache["angles"]

                # ═══ 首轮等待：分析缓存还是兜底值时，等异步分析完成再生成 ═══
                # 避免第一波弹幕基于"用户正在使用电脑"这种无信息兜底描述硬编（没话找话）
                if not self._waited_first_analysis:
                    self._waited_first_analysis = True
                    if not cfg.get("_last_analysis") or cfg["_last_analysis"] == "用户正在使用电脑":
                        if self._analysis_running:
                            log("等待首次画面分析完成，确保第一波弹幕基于真实画面...")
                            deadline = time.time() + 120
                            while self._analysis_running and time.time() < deadline and self.running:
                                time.sleep(1)
                            with self._analysis_lock:
                                if self._analysis_cache["analysis"]:
                                    cfg["_last_analysis"] = self._analysis_cache["analysis"]
                                    cfg["_last_angles"] = self._analysis_cache["angles"]
                        # 分析超时/失败兜底：发一条通用弹幕池的，绝不用空描述硬编
                        if not cfg.get("_last_analysis") or cfg["_last_analysis"] == "用户正在使用电脑":
                            log("画面分析超时/失败，首轮使用兜底弹幕池")
                            fallback = random.choice(FALLBACK_DANMU)
                            self.window.send_stagger(fallback)
                            log_danmu("普通", fallback)
                            cooldown = compute_cooldown(cfg, 1)
                            self.trigger.wait(timeout=cooldown)
                            self.trigger.clear()
                            continue

                # 生成普通弹幕（使用当前缓存的分析结果）
                danmu_enabled = cfg.get("danmuMode", True)
                original_buddy_mode = cfg.get("buddyMode", False)
                sent = 0
                pre_analysis = cfg.get("_last_analysis")
                if danmu_enabled:
                    cfg["buddyMode"] = False

                    if pre_analysis:
                        remaining = danmu_count
                        log(f"并行生成 {remaining} 条弹幕...")
                        batch_texts = []
                        _lock = threading.Lock()
                        _dup = set(last_texts)

                        def _gen():
                            res = generate_danmu_text(cfg, img_b64, pre_analysis)
                            if isinstance(res, tuple):
                                res = res[0]
                            return res

                        with ThreadPoolExecutor(max_workers=min(8, remaining)) as pool:
                            futures = [pool.submit(_gen) for _ in range(remaining)]
                            for fut in as_completed(futures):
                                try:
                                    t = fut.result()
                                    if t:
                                        with _lock:
                                            if t not in _dup:
                                                _dup.add(t)
                                                batch_texts.append(t)
                                except Exception as ex:
                                    log(f"并行生成异常: {ex}")

                        # 全部存入分散队列，由 _tick 以随机节奏逐步发放
                        for text in batch_texts:
                            if text and text not in last_texts:
                                log(f"弹幕生成成功: {text}")
                                log_danmu("普通", text)
                                self.window.send_stagger(text)
                                last_texts.append(text)
                                if len(last_texts) > 20:
                                    last_texts.pop(0)
                                sent += 1
                else:
                    log("普通弹幕已关闭，跳过生成")
                cfg["buddyMode"] = original_buddy_mode

                # 第二步：如果启用了伙伴模式，按独立间隔随机插入助手弹幕
                # 没装闲不住时跳过伙伴弹幕
                if original_buddy_mode and is_workvisit_available():
                    now = time.time()
                    buddy_cooldown = compute_buddy_cooldown(cfg)
                    elapsed = now - self.last_buddy_time
                    # 第一次启动时立即发，之后按间隔
                    if self.last_buddy_time == 0 or elapsed >= buddy_cooldown:
                        selected = cfg.get("selectedBuddies", [])
                        buddies = cfg.get("buddies", {})
                        for bid in selected:
                            b = buddies.get(bid, {})
                            log(f"调用 API 生成 {b.get('name', bid)} 弹幕...")
                            result = generate_danmu_text(cfg, img_b64, cfg.get("_last_analysis"), force_buddy_id=bid)
                            if isinstance(result, tuple):
                                text, buddy_name, buddy_color = result
                            else:
                                text, buddy_name, buddy_color = result, None, None
                            if text and text not in last_texts:
                                if buddy_name:
                                    text = f"{buddy_name}：{text}"
                                    log(f"弹幕生成成功: {text}")
                                    log_danmu("伙伴", text)
                                    self.window.send_stagger(text, buddy_color)
                                else:
                                    log(f"弹幕生成成功: {text}")
                                    log_danmu("伙伴", text)
                                    self.window.send_stagger(text)
                                last_texts.append(text)
                                if len(last_texts) > 20:
                                    last_texts.pop(0)
                                sent += 1
                                time.sleep(0.5)
                            else:
                                log(f"弹幕为空或重复" + (f" (text={text})" if text else ""))
                        self.last_buddy_time = now

                # 计算等待间隔（纯函数：fixed/random + sent==0 减半）
                cooldown = compute_cooldown(cfg, sent)

                # 等待期间持续小批量生成弹幕（避免空白期）
                if cooldown > 3 and cfg.get("_last_analysis"):
                    danmu_enabled = cfg.get("danmuMode", True)
                    waited = 0
                    while waited < cooldown and self.running:
                        self.trigger.wait(timeout=3)
                        self.trigger.clear()
                        waited += 3
                        if not danmu_enabled:
                            continue
                        pre = cfg.get("_last_analysis")
                        if not pre:
                            continue
                        mini_count = 0
                        for _ in range(random.randint(2, 3)):
                            try:
                                res = generate_danmu_text(cfg, img_b64, pre)
                                if isinstance(res, tuple):
                                    res = res[0]
                                if res and res not in last_texts:
                                    self.window.send_stagger(res)
                                    last_texts.append(res)
                                    if len(last_texts) > 30:
                                        last_texts[:10] = []
                                    mini_count += 1
                            except Exception:
                                pass
                        if mini_count:
                            log(f"间隔期生成 {mini_count} 条弹幕")
                else:
                    self.trigger.wait(timeout=cooldown)
                    self.trigger.clear()

            except Exception as e:
                log(f"引擎异常: {e}")
                import traceback
                log(traceback.format_exc()[:200])
                time.sleep(10)

        log("弹幕引擎已停止")


# ═══════════════════════════════════
#  HTTP API
# ═══════════════════════════════════
class ZaiganmaHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        global _engine_ref
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        if parsed.path == "/send":
            self._json({"ok": False, "error": "请使用 POST 方法发送弹幕"}, 405)

        elif parsed.path == "/status":
            engine = _engine_ref
            running = engine.running if engine else False
            idle_paused = engine.idle_paused if engine else False
            self._json({"ok": True, "running": running,
                        "idle_paused": idle_paused,
                        "queue_size": self.server.window.msg_queue.qsize(),
                        "workvisit_available": is_workvisit_available()})

        elif parsed.path == "/config":
            # 返回配置时隐藏 API Key 等敏感字段
            _sensitive_keys = {'_visionApiKey', '_visionBaseUrl', '_danmuApiKey', '_danmuBaseUrl',
                               'visionCustomApiKey', 'visionCustomBaseUrl',
                               'danmuCustomApiKey', 'danmuCustomBaseUrl'}
            safe_config = {k: v for k, v in self.server.window.config.items() if k not in _sensitive_keys}
            self._json({"ok": True, "config": safe_config})

        elif parsed.path == "/clear":
            self.server.window.clear()
            self._json({"ok": True})

        elif parsed.path == "/generate":
            if _engine_ref:
                _engine_ref.generate_now()
            self._json({"ok": True, "message": "生成请求已发送"})

        elif parsed.path == "/toggle":
            # 统一通过全局引擎引用操作，避免 server.engine 引用过期导致双引擎并发
            engine = _engine_ref
            if engine and engine.running:
                engine.stop()
                self._json({"ok": True, "running": False})
            elif engine:
                # 重启引擎（加锁替换，防并发双引擎）
                _replace_engine(self.server.window)
                self._json({"ok": True, "running": True})
            else:
                self._json({"ok": False, "error": "引擎未初始化"}, 500)

        elif parsed.path == "/logs":
            self._json({"ok": True, "logs": list(_log_buffer)})

        elif parsed.path == "/health":
            self._json({"ok": True, "app": "zaiganma"})

        else:
            self._html("<h1>在干嘛</h1><p>弹幕小程序运行中</p>"
                       "<p>API: /send /status /config /generate /toggle /clear /health</p>")

    def do_POST(self):
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8") if length else "{}"
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            self._json({"ok": False, "error": "invalid json"}, 400)
            return

        if parsed.path == "/send":
            text = data.get("text", "")
            framed = data.get("framed", False)
            buddy_color = data.get("buddy_color")
            if text:
                self.server.window.send(text, buddy_color=buddy_color, framed=framed)
                self._json({"ok": True, "text": text})
            else:
                self._json({"ok": False, "error": "text required"}, 400)

        elif parsed.path == "/config/reload":
            # 把数据放进队列，由 Qt 主线程轮询处理
            _put_config_reload(self.server.window, data)
            self._json({"ok": True, "message": "配置已重载"})

        elif parsed.path == "/config":
            # 直接写配置
            self.server.window.update_config(data)
            self._json({"ok": True})

        else:
            self._json({"ok": False, "error": "not found"}, 404)

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _json(self, obj, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self._cors()
        self.end_headers()
        self.wfile.write(json.dumps(obj, ensure_ascii=False).encode("utf-8"))

    def _html(self, body):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self._cors()
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def log_message(self, fmt, *args):
        pass

# 配置重载队列（线程安全，HTTP 子线程写入 → Qt 主线程消费）
_config_reload_queue = queue.Queue()
_config_reload_timer = None  # 保存定时器引用，防止 GC


def _put_config_reload(window, data):
    """从 HTTP 子线程调用，将配置数据放入队列"""
    _config_reload_queue.put((window, data))


def _start_config_reload_poller(window_ref):
    """启动配置重载轮询（在 Qt 主线程调用一次即可）"""
    def poll():
        try:
            while True:
                win, dat = _config_reload_queue.get_nowait()
                _apply_config_reload(win, dat)
        except queue.Empty:
            pass
    # 每 200ms 检查一次队列
    global _config_reload_timer
    timer = QTimer()
    timer.timeout.connect(poll)
    timer.start(200)
    _config_reload_timer = timer  # 保存引用，防止 GC
    return timer


def _apply_config_reload(window, data):
    """在 Qt 主线程执行配置重载"""
    global _engine_ref
    if not window:
        print("  [config_reload] window 为空")
        return
    try:
        old_size = window.config.get("font_size", "?")
        window.update_config(data)
        new_size = window.config.get("font_size", "?")
        print(f"  [config_reload] font_size: {old_size} -> {new_size}")
        # 同步更新 provider API 凭据（前端改了 provider 时重新从 provider-catalog.json 读取）
        _load_provider_config(window.config)
        # 引擎未运行时自动拉起（加锁替换，保证 /status /toggle 一致）
        if _engine_ref and not _engine_ref.running:
            _replace_engine(window)
    except Exception as e:
        import traceback
        print(f"  [config_reload] 错误: {e}")
        traceback.print_exc()


def start_http(host, port, window, engine):
    server = HTTPServer((host, port), ZaiganmaHandler)  # bind 成功后才继续
    server.window = window
    server.engine = engine
    _report_port(port)  # 真正监听成功后再上报端口，避免 Node 读到未就绪端口
    server.serve_forever()


# ═══════════════════════════════════
#  系统托盘
# ═══════════════════════════════════
def create_tray(app, window: DanmuWindow, engine: DanmuEngine, config: dict, port: int):
    tray = QSystemTrayIcon()

    # 绘制托盘图标
    pix = QPixmap(32, 32)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor(239, 68, 68))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(2, 2, 28, 28, 6, 6)
    painter.setPen(QColor(255, 255, 255))
    font = QFont("Microsoft YaHei", 14, QFont.Weight.Bold)
    painter.setFont(font)
    painter.drawText(pix.rect(), Qt.AlignmentFlag.AlignCenter, "看")
    painter.end()
    tray.setIcon(QIcon(pix))
    tray.setToolTip(f"在干嘛 (:{port})")

    menu = QMenu()

    # 开关
    toggle_action = menu.addAction("停止弹幕" if engine.running else "启动弹幕")
    toggle_action.triggered.connect(lambda: _toggle_engine(engine, toggle_action, tray))

    # 时间间隔子菜单（快捷常用值）
    interval_menu = menu.addMenu("时间间隔")
    for val, label in [(15, "15 秒"), (30, "30 秒"), (60, "60 秒"), ("random", "随机")]:
        action = interval_menu.addAction(label)
        action.triggered.connect(lambda checked, v=val: _set_interval(config, window, engine, v, tray))

    # 显示密度快捷调节
    density_menu = menu.addMenu("显示密度")
    for val, label in [(30, "低密度"), (60, "中密度"), (100, "高密度")]:
        action = density_menu.addAction(label)
        action.triggered.connect(lambda checked, v=val: _set_density(config, window, engine, v, tray))

    menu.addSeparator()

    # 立即生成
    gen_action = menu.addAction("马上飘一波！")
    gen_action.triggered.connect(lambda: _trigger_generate())

    # 清理弹幕
    clear_action = menu.addAction("清理弹幕")
    clear_action.triggered.connect(lambda: window.clear())

    menu.addSeparator()

    # 退出
    quit_action = menu.addAction("退出")
    quit_action.triggered.connect(lambda: _quit(app, engine))

    tray.setContextMenu(menu)

    tray.show()
    log("系统托盘已创建，引擎状态: " + ("运行中" if engine.running else "已停止"))
    return tray


def _persist_config(config):
    """把托盘快捷修改的配置写回 config.json（排除内部 _ 前缀键），保证重启不丢"""
    cfg_path = os.environ.get("ZAIGANMA_CONFIG", "")
    if not cfg_path:
        return
    try:
        existing = load_json(cfg_path, {})
        clean = {k: v for k, v in config.items() if not k.startswith("_")}
        existing.update(clean)
        save_json(cfg_path, existing)
        log("托盘修改已持久化到 config.json")
    except Exception as e:
        log(f"配置持久化失败: {e}")


def _set_interval(config, window, engine, val, tray):
    if val == "random":
        config["intervalMode"] = "random"
        window.config["intervalMode"] = "random"
        window.send("间隔调整为随机模式")
    else:
        config["intervalSec"] = val
        config["intervalMode"] = "fixed"
        window.config["intervalSec"] = val
        window.config["intervalMode"] = "fixed"
        window.send(f"间隔调整为 {val} 秒")
    _persist_config(config)


def _set_density(config, window, engine, val, tray):
    config["density"] = val
    window.config["density"] = val
    window.update_config({"density": val})
    labels = {30: "低", 60: "中", 100: "高"}
    window.send(f"显示密度调整为 {labels.get(val, str(val))}")
    _persist_config(config)


def _toggle_engine(engine, action, tray):
    # 始终通过全局引用获取当前实际运行的引擎
    current = _engine_ref or engine
    if current.running:
        current.stop()
        action.setText("启动弹幕")
        log("弹幕引擎已停止")
    else:
        _replace_engine(current.window)
        action.setText("停止弹幕")
        log("弹幕引擎已启动")


_engine_ref = None


def _trigger_generate():
    """触发引擎立即生成一次弹幕（通过全局引擎引用）"""
    global _engine_ref
    if _engine_ref and _engine_ref.running:
        _engine_ref.generate_now()


def _quit(app, engine):
    if engine:
        engine.stop()
    app.quit()


# ═══════════════════════════════════
#  入口
# ═══════════════════════════════════
def _report_port(port):
    """把实际监听端口写到 config 同目录的 port.json（临时文件 + os.replace 原子写，避免半截 JSON）"""
    cfg_path = os.environ.get("ZAIGANMA_CONFIG", "")
    if not cfg_path:
        return
    try:
        port_path = os.path.join(os.path.dirname(cfg_path), "port.json")
        tmp_path = port_path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump({"port": port}, f)
        os.replace(tmp_path, port_path)
    except Exception:
        pass


# ═══════════════════════════════════
#  引擎替换（统一加锁，防并发双引擎）
# ═══════════════════════════════════
_engine_lock = threading.Lock()


def _replace_engine(window):
    """加锁创建新引擎并替换全局引用（检查+创建+替换整体原子，防 HTTP/托盘/配置重载并发双引擎）"""
    global _engine_ref
    with _engine_lock:
        new_engine = DanmuEngine(window)
        new_engine.start()
        _engine_ref = new_engine
    return new_engine


# ═══════════════════════════════════
#  入口
# ═══════════════════════════════════
def main():
    global _engine_ref  # 必须声明：函数内赋值否则创建局部变量，模块级引用永远是 None
    parser = argparse.ArgumentParser(description="在干嘛 — 桌面弹幕小程序")
    parser.add_argument("--port", type=int, default=18900, help="HTTP API 端口")
    parser.add_argument("--config", type=str, default="", help="配置文件路径")
    args = parser.parse_args()

    # 加载配置（兼容 camelCase 键名）
    config = dict(DEFAULT_CONFIG)
    _name_map_reverse = {
        "fontSize": "font_size", "fontFamily": "font_family",
        "topMargin": "top_margin", "colorMode": "color_mode",
        "singleColor": "single_color", "paletteColors": "palette_colors",
        "shadowMode": "shadow_mode", "maxOnscreen": "max_onscreen",
    }
    cfg_path = args.config or os.environ.get("ZAIGANMA_CONFIG", "")
    if cfg_path and os.path.exists(cfg_path):
        loaded = load_json(cfg_path, {})
        for k, v in loaded.items():
            mapped = _name_map_reverse.get(k, k)
            config[mapped] = v

    config["port"] = args.port
    port = find_free_port(config["port"])
    config["port"] = port  # 端口可能被占用跳号，写回实际值
    # 端口上报移到 start_http：HTTPServer 真正 bind 成功后再写 port.json，避免竞态

    # 验证加载的模块路径（防止加载了旧版本）
    _self_file = os.path.abspath(__file__)
    if "plugins-dev" in _self_file:
        print(f"[警告] 已加载 plugins-dev 目录的旧版本: {_self_file}")
    else:
        print(f"[启动] 模块路径: {_self_file}")

    # 读取 Hana 模型 API 配置（从 provider-catalog.json）
    _load_provider_config(config)

    log(f"配置加载完成，端口: {port}，截图模型: {config.get('visionModelId', '未设置')}")

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    # 弹幕浮层
    window = DanmuWindow(config)
    window.setWindowOpacity(config.get("opacity", 0.85))
    window.show()
    log("弹幕浮层窗口已创建")

    # 弹幕引擎
    engine = DanmuEngine(window)
    engine.start()
    _engine_ref = engine

    # HTTP API（server bind 成功后由 start_http 上报端口）
    http_thread = threading.Thread(
        target=start_http, args=("127.0.0.1", port, window, engine), daemon=True
    )
    http_thread.start()

    # 系统托盘
    tray = create_tray(app, window, engine, config, port)

    # 启动配置重载轮询
    _start_config_reload_poller(window)

    # 欢迎
    window.send("📺 在干嘛已启动 ✨")

    print(f"[在干嘛] 运行中 — http://127.0.0.1:{port}")
    print(f"[在干嘛] 托盘右键控制 | Ctrl+Q 退出")

    sys.exit(app.exec())


def _load_provider_config(config):
    """从 Hana provider-catalog.json 读取 API Key 和 Base URL"""
    provider_catalog = os.path.join(_get_hana_home(), "provider-catalog.json")
    if not os.path.exists(provider_catalog):
        return

    try:
        with open(provider_catalog, "r", encoding="utf-8") as f:
            catalog = json.load(f)

        # 截图模型 provider
        vis_pid = config.get("visionProviderId", "")
        if vis_pid and vis_pid in catalog.get("providers", {}):
            p = catalog["providers"][vis_pid]
            config["_visionApiKey"] = p.get("api_key", "")
            config["_visionBaseUrl"] = p.get("base_url", p.get("api_base", ""))

        # 文案模型 provider（如果独立指定）
        dm_pid = config.get("danmuProviderId", "")
        if dm_pid and dm_pid in catalog.get("providers", {}):
            p = catalog["providers"][dm_pid]
            config["_danmuApiKey"] = p.get("api_key", "")
            config["_danmuBaseUrl"] = p.get("base_url", p.get("api_base", ""))
    except Exception as e:
        print(f"  [配置] provider-catalog 读取失败: {e}")


if __name__ == "__main__":
    main()
