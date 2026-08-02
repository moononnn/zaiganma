# 在干嘛 — 自动测试

## 运行命令

```powershell
cd L:\哈娜的工作台\zaiganma
npm test          # JS + Python 全部测试
npm run test:js   # 只跑 JS（node:test）
npm run test:py   # 只跑 Python（unittest）
```

## 环境要求

- Node.js 18+（测试用到 node:test 与 AbortSignal）
- Python 3.8+，且已安装插件依赖：mss、Pillow、httpx、PyQt6
  - PyQt6 缺失时 `tests/py/test_window.py` 自动跳过，其余测试不受影响

## 覆盖范围

### JS（tests/js/，node:test + node:assert/strict）

| 文件 | 覆盖逻辑 |
|---|---|
| `index.test.js` | 配置读写与合并（loadCfg/saveCfg）、buddies 补全与颜色更新、模型列表读取（vision 过滤/provider 目录）、端口动态读取（port.json）、getState 副本 |
| `routes.test.js` | 设置页服务端渲染完整性（关键控件 id 齐全）、/api/models、/api/status、/api/check-update 版本比较（mock fetch） |
| `tools.test.js` | zaiganma_toggle 的 start/stop/restart 分派、zaiganma_send 未启动时的错误返回 |
| `manifest.test.js` | manifest.json 字段合法性、main/routes/tools/page 指向的文件存在 |

### Python（tests/py/，unittest）

| 文件 | 覆盖逻辑 |
|---|---|
| `test_filters.py` | is_valid_danmu（长度/思考关键词/括号/截断标点）、_strip_thinking（think/thinking 块）、_pick_last_sentence（多句提取与过滤） |
| `test_config.py` | build_api_config（same/hana/custom 三态与 camelCase/snake_case 兼容）、translate_vars_to_state（五档边界、组合连接词、好感度阶段） |
| `test_utils.py` | find_free_port（端口占用跳号）、load_json（utf-8-sig）、log_danmu 跨轮重复抑制统计 |
| `test_generate.py` | generate_danmu_text：一步法/两步法 prompt 结构、无效内容重试与兜底弹幕、伙伴模式（force_buddy_id、MVU 注入）、记忆流（mock facts.db）、分析兜底链（坏关键词/过短/不完整英文结尾/多角度拆分） |
| `test_window.py` | DanmuWindow 轨道分配（顺序、满轨道拒绝、clear 重置、tracks 缩小后不越界崩溃、轨道占用重标）、配置重载引擎拉起/不重复 — 需要 PyQt6，缺失自动跳过 |
| `test_engine.py` | 引擎间隔纯函数（fixed/random/减半保底）、call_llm（重试/非200/reasoning 回退/引号清理/长文本截断/thinking 禁用）、托盘持久化（内部键排除）与启停、主循环集成（弹幕生成/空闲暂停） |
| `test_http.py` | HTTP 全端点（真 HTTPServer + 假 window/engine）：/health /status /send(含400/405) /clear /config(脱敏) /toggle(停/启/防双引擎) /config/reload 入队 /404 /无效 JSON |
| `test_workvisit.py` | 闲不住集成：可用性判定（无文件/空配置/损坏 JSON）、load_workvisit_vars 的 mtime 缓存（不变复用/变化重读）、MVU 上下文翻译 |

## 测试纪律

- 随机逻辑不依赖真实随机：用固定随机种子或 mock（unittest.mock.patch / node:test mock）
- 不发起真实网络请求：API 调用全部 mock（call_llm / fetch / spawn）
- 不真实启动 Python 小程序：child_process.spawn 被 mock
- 配置文件读写全部落在临时目录（HANA_HOME 指向 mkdtemp），绝不碰真实用户配置

## 最近结果

- 2026-08-02 — 全部通过（见 PROJECT_LOG.md）
