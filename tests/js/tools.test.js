// 在干嘛 — 工具（toggle / send）测试
// mock spawn 防止真启动 Python；mock fetch 防止 send 测试产生真实副作用（真发弹幕）
import { test, before, after, mock } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, rmSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';

const TEST_HOME = mkdtempSync(join(tmpdir(), 'zaiganma-tools-'));
process.env.HANA_HOME = TEST_HOME;

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

// 所有 fetch 一律拒绝：既防止真网络请求，也防止"小程序恰好运行中"导致测试误报/真发弹幕
before(() => {
  mock.method(globalThis, 'fetch', async () => {
    throw new Error('fetch mocked to reject: ECONNREFUSED');
  });
});

after(() => {
  rmSync(TEST_HOME, { recursive: true, force: true });
});

const toggle = await import('../../tools/zaiganma-toggle.js');
const send = await import('../../tools/zaiganma-send.js');

function parse(res) {
  return JSON.parse(res.content[0].text);
}

// ── send 测试放前面：start 测试会把模块 state.running 置 true，影响未启动断言 ──

// 注意：fetch 被 mock 为全部拒绝，所以这里即使 running=true 也会走 catch 分支返回错误，
// 不会真的请求 127.0.0.1:18900（避免开发机小程序运行中时测试真发弹幕）
test('zaiganma_send：小程序不可达时返回错误而非抛出', async () => {
  const res = await send.execute({ text: '测试弹幕' }, {});
  const data = parse(res);
  assert.equal(data.ok, false);
  assert.ok(data.error, '应返回错误信息');
});

test('zaiganma_send：缺少 text 时也能正常返回（不抛异常）', async () => {
  const res = await send.execute({ text: '' }, {});
  const data = parse(res);
  assert.equal(typeof data.ok, 'boolean');
});

// ── toggle 分派 ──

test('zaiganma_toggle：start 返回 started', async () => {
  const res = await toggle.execute({ action: 'start' }, {});
  assert.deepEqual(parse(res), { ok: true, action: 'started' });
});

test('zaiganma_toggle：stop 返回 stopped', async () => {
  const res = await toggle.execute({ action: 'stop' }, {});
  assert.deepEqual(parse(res), { ok: true, action: 'stopped' });
});

test('zaiganma_toggle：restart 返回 restarted', async () => {
  const res = await toggle.execute({ action: 'restart' }, {});
  assert.deepEqual(parse(res), { ok: true, action: 'restarted' });
});

test('zaiganma_toggle：非法 action 返回错误', async () => {
  const res = await toggle.execute({ action: 'explode' }, {});
  assert.deepEqual(parse(res), { ok: false, error: 'unknown action' });
});

// ── 进程生命周期：spawn 的 exit 回调应复位 running 与 appProcess 引用 ──

test('startApp：进程退出后状态自动复位，可再次启动', async () => {
  const index = await import('../../index.js');
  index.startApp();
  assert.equal(index.getState().running, true, 'spawn 后应立即标记运行中');
  // mock spawn 的 exit 在下一事件循环触发（模拟进程退出）
  await new Promise(r => setTimeout(r, 20));
  assert.equal(index.getState().running, false, '进程退出后 running 应复位');
  // 引用已清理，能再次启动
  index.startApp();
  assert.equal(index.getState().running, true, '退出后应能重新启动');
  await new Promise(r => setTimeout(r, 20));
  assert.equal(index.getState().running, false);
  index.stopApp();
});
