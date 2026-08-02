// 在干嘛 — 路由与服务端渲染测试
// mock 掉 child_process.spawn（防真启动 Python 小程序）与全局 fetch（防真网络请求）
import { test, before, beforeEach, mock } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, writeFileSync, mkdirSync, rmSync, readFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { tmpdir } from 'node:os';

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, '..', '..');
const manifest = JSON.parse(readFileSync(join(ROOT, 'manifest.json'), 'utf-8'));
const CURRENT_VERSION = manifest.version;
// 动态构造一个比当前版本大的假版本，避免版本 bump 后误报
const [_ma, _mi, _pa] = CURRENT_VERSION.split('.').map(Number);
const FAKE_LATEST = `v${_ma}.${_mi}.${_pa + 1}`;

// ⚠️ 必须在 import 插件模块之前设置 HANA_HOME 并 mock spawn
const TEST_HOME = mkdtempSync(join(tmpdir(), 'zaiganma-routes-'));
process.env.HANA_HOME = TEST_HOME;

// mock node:child_process.spawn：返回假进程对象，exit 立即回调 0（checkDeps 依赖）
mock.module('node:child_process', {
  exports: {
    spawn: () => ({
      stdout: { on: () => {} },
      stderr: { on: () => {} },
      on: (evt, cb) => { if (evt === 'exit') setTimeout(() => cb(0), 0); },
      kill: () => {},
    }),
  },
});

let mod;
let handlers = {};
let fetchCalls = [];

function makeC(reqOverrides = {}) {
  return {
    req: {
      query: () => '',
      json: async () => ({}),
      param: () => 'hanako',
      url: 'http://localhost/plugin/zaiganma/page?token=abc',
      ...reqOverrides,
    },
    html: (h) => ({ html: h }),
  };
}

before(async () => {
  // mock 全局 fetch：本地小程序 API 返回成功（避免 /page 6 秒重试）、github 返回发布数据，其余不可用
  mock.method(globalThis, 'fetch', async (url, opts) => {
    fetchCalls.push(String(url));
    if (String(url).includes('127.0.0.1')) {
      return { ok: true, json: async () => ({ running: false, workvisit_available: false }) };
    }
    if (String(url).includes('api.github.com')) {
      return {
        ok: true,
        json: async () => ({
          tag_name: FAKE_LATEST,
          html_url: 'https://github.com/moononnn/zaiganma/releases/tag/' + FAKE_LATEST,
        }),
      };
    }
    return { ok: false };
  });

  // 准备 models.json，让 /page 能渲染出模型选项
  writeFileSync(join(TEST_HOME, 'models.json'), JSON.stringify({
    providers: {
      p1: {
        name: '视觉厂',
        models: [
          { id: 'vision-a', input: ['text', 'image'] },
          { id: 'text-only', input: ['text'] },
        ],
      },
    },
  }), 'utf-8');

  mod = await import('../../routes/api.js');
  const mockApp = {
    get: (p, fn) => { handlers[p] = fn; },
    post: (p, fn) => { handlers[p] = fn; },
  };
  await mod.default(mockApp, { log: {} });
});

beforeEach(() => {
  fetchCalls = [];
});

test('路由注册：/page 与关键 API 都已注册', () => {
  for (const p of ['/page', '/api/app.js', '/api/status', '/api/init',
    '/api/save-config', '/api/models', '/api/test-vision', '/api/test-danmu',
    '/api/avatar/:agentId', '/api/check-update', '/api/restart-app', '/api/toggle']) {
    assert.ok(handlers[p], `路由 ${p} 应已注册`);
  }
});

test('/page 渲染：包含全部关键控件 id', async () => {
  const res = await handlers['/page'](makeC());
  const html = res.html;
  assert.ok(html.includes('<!DOCTYPE html>'), '应输出完整 HTML 文档');
  const requiredIds = [
    'btnSettings', 'btnToggle', 'tglDot', 'tglLabel', 'dot', 'statusText',
    'guideCard', 'buddyMode', 'buddyList', 'buddyIntervalMode', 'buddyMemoryRatio',
    'styleChips', 'danmuMode', 'intervalMode', 'fixedFields', 'randomFields',
    'fontSize', 'valFontSize', 'density', 'valDensity', 'speedPct', 'areaChips',
    'paletteColors', 'nicknames', 'idleAutoPause', 'idleThreshold',
    'btnSaveAll', 'btnRestart', 'settingsModal', 'visionSel', 'danmuSel',
    'btnTestVision', 'btnTestDanmu', 'btnSaveModal', 'btnCheckUpdate', 'updateStatus',
  ];
  for (const id of requiredIds) {
    assert.ok(html.includes(`id="${id}"`), `HTML 应包含 id="${id}"`);
  }
  // 模型选项渲染（vision-a 出现在截图模型下拉里）
  assert.ok(html.includes('vision-a'), '视觉模型应出现在下拉选项里');
  // 版本号来自 manifest（不硬编码，版本 bump 不误报）
  assert.ok(html.includes('v' + CURRENT_VERSION), '页面应显示 manifest 版本号');
});

test('/page 渲染：伙伴列表来自 agents 目录（有 hanako）', async () => {
  const agentDir = join(TEST_HOME, 'agents', 'hanako');
  mkdirSync(agentDir, { recursive: true });
  writeFileSync(join(agentDir, 'config.yaml'), 'name: 小花\n', 'utf-8');
  writeFileSync(join(agentDir, 'description.md'), '测试描述\n', 'utf-8');

  const res = await handlers['/page'](makeC());
  assert.ok(res.html.includes('小花'), '伙伴名应出现在页面中');
});

test('/api/models：返回 vision 与全部模型', async () => {
  const res = await handlers['/api/models'](makeC());
  const data = await res.json();
  assert.equal(data.vision.length, 1);
  assert.equal(data.vision[0].providerId, 'p1');
  assert.equal(data.all.length, 1);
});

test('/api/status：返回状态与依赖检查结果', async () => {
  const res = await handlers['/api/status'](makeC());
  const data = await res.json();
  assert.equal(typeof data.running, 'boolean');
  assert.equal(data.depsOk, true, 'spawn 被 mock 为成功，依赖检查应通过');
});

test('/api/check-update：有新版本时返回 hasUpdate=true', async () => {
  const res = await handlers['/api/check-update'](makeC());
  const data = await res.json();
  assert.equal(data.hasUpdate, true);
  assert.equal(data.latestVersion, FAKE_LATEST);
  assert.equal(data.currentVersion, CURRENT_VERSION);
});

test('/api/check-update：GitHub 不可用时优雅降级', async () => {
  // 覆盖 fetch mock：github 也失败
  mock.method(globalThis, 'fetch', async () => ({ ok: false }), { times: 1 });
  const res = await handlers['/api/check-update'](makeC());
  const data = await res.json();
  assert.equal(data.error, true);
  assert.ok(data.repoUrl.includes('github.com'));
});

test('/api/save-config：保存配置并返回消息', async () => {
  const c = makeC({
    json: async () => ({ fontSize: 44, styles: ['casual'] }),
  });
  const res = await handlers['/api/save-config'](c);
  const data = await res.json();
  assert.equal(data.ok, true);
});

test('/api/avatar/:agentId：无头像文件时返回 404', async () => {
  const res = await handlers['/api/avatar/:agentId'](makeC());
  assert.equal(res.status, 404);
});
