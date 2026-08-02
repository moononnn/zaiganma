// 在干嘛 — index.js 核心逻辑测试（配置读写 / 模型读取 / 伙伴 / 端口）
import { test, before, after, beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, writeFileSync, mkdirSync, rmSync, existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';

// ⚠️ 必须在 import 插件模块之前设置 HANA_HOME，index.js 的路径常量在模块加载时固定
const TEST_HOME = mkdtempSync(join(tmpdir(), 'zaiganma-test-'));
process.env.HANA_HOME = TEST_HOME;

const mod = await import('../../index.js');

function writeCfg(data) {
  const dir = join(TEST_HOME, 'data', 'zaiganma');
  mkdirSync(dir, { recursive: true });
  writeFileSync(join(dir, 'config.json'), JSON.stringify(data, null, 2), 'utf-8');
}
function writeModels(data) {
  writeFileSync(join(TEST_HOME, 'models.json'), JSON.stringify(data, null, 2), 'utf-8');
}
function writeCatalog(data) {
  writeFileSync(join(TEST_HOME, 'provider-catalog.json'), JSON.stringify(data, null, 2), 'utf-8');
}
function writeAgent(agentId, name, desc) {
  const dir = join(TEST_HOME, 'agents', agentId);
  mkdirSync(dir, { recursive: true });
  writeFileSync(join(dir, 'config.yaml'), `name: "${name}"\npersonality: test\n`, 'utf-8');
  if (desc) writeFileSync(join(dir, 'description.md'), desc, 'utf-8');
}
function cfgPath() {
  return join(TEST_HOME, 'data', 'zaiganma', 'config.json');
}

before(() => {
  // 准备一个 agents 目录（含两位助手）
  writeAgent('hanako', '小花', '温柔的少女助手，喜欢喝茶。');
  writeAgent('yumi', '悠米', '感性的伙伴。');
});

after(() => {
  rmSync(TEST_HOME, { recursive: true, force: true });
});

beforeEach(() => {
  // 每个测试前清掉 data 目录，保证隔离
  rmSync(join(TEST_HOME, 'data'), { recursive: true, force: true });
  rmSync(join(TEST_HOME, 'models.json'), { force: true });
  rmSync(join(TEST_HOME, 'provider-catalog.json'), { force: true });
});

// ─── 配置读写 ───
test('loadCfg：无配置文件时返回空对象', () => {
  assert.deepEqual(mod.loadCfg(), {});
});

test('loadCfg：配置文件损坏时返回空对象而非抛异常', () => {
  const dir = join(TEST_HOME, 'data', 'zaiganma');
  mkdirSync(dir, { recursive: true });
  writeFileSync(join(dir, 'config.json'), '{broken json!!', 'utf-8');
  assert.deepEqual(mod.loadCfg(), {});
});

test('loadCfg：正常读取配置文件', () => {
  writeCfg({ fontSize: 42, styles: ['casual', 'roast'] });
  const cfg = mod.loadCfg();
  assert.equal(cfg.fontSize, 42);
  assert.deepEqual(cfg.styles, ['casual', 'roast']);
});

test('saveCfg：写入文件并更新内存 state', () => {
  mod.saveCfg({ fontSize: 36, danmuCount: 2 });
  // 文件已写
  const onDisk = JSON.parse(readFileSync(cfgPath(), 'utf-8'));
  assert.equal(onDisk.fontSize, 36);
  // 内存已更新
  assert.equal(mod.getState().fontSize, 36);
  assert.equal(mod.getState().danmuCount, 2);
});

test('saveCfg：多次保存合并而非覆盖（已有键保留）', () => {
  mod.saveCfg({ fontSize: 20 });
  mod.saveCfg({ danmuCount: 3 });
  const onDisk = JSON.parse(readFileSync(cfgPath(), 'utf-8'));
  assert.equal(onDisk.fontSize, 20);
  assert.equal(onDisk.danmuCount, 3);
});

test('saveCfg：buddies 为空时从 agents 目录自动补全', () => {
  mod.saveCfg({ buddyMode: true, buddies: {} });
  const state = mod.getState();
  assert.ok(state.buddies['hanako'], 'hanako 应被补全');
  assert.ok(state.buddies['yumi'], 'yumi 应被补全');
  assert.equal(state.buddies['hanako'].name, '小花');
});

test('saveCfg：_buddyColors 更新颜色且保留完整伙伴数据', () => {
  // 先补全 buddies
  mod.saveCfg({ buddies: {} });
  // 再更新颜色
  mod.saveCfg({ _buddyColors: { hanako: '#FF0000' } });
  const state = mod.getState();
  assert.equal(state.buddies['hanako'].color, '#FF0000');
  assert.equal(state.buddies['hanako'].name, '小花', '颜色更新不应丢掉 name');
  assert.ok(state.buddies['hanako'].styleDesc, '颜色更新不应丢掉 styleDesc');
});

test('saveCfg：_buddyColors 对不存在于 state 的伙伴也能兜底补全', () => {
  // 清掉 state 里的 buddies（通过保存空 buddies 前先清 agents 不可行，这里直接测兜底分支）
  mod.saveCfg({ buddies: { ghost: { name: '幽灵', color: '#FFFFFF', styleDesc: '' } } });
  mod.saveCfg({ _buddyColors: { ghost: '#00FF00' } });
  const state = mod.getState();
  assert.equal(state.buddies['ghost'].color, '#00FF00');
  assert.equal(state.buddies['ghost'].name, '幽灵');
});

test('saveCfg：不认识的键不会写进 state（仅持久化）', () => {
  mod.saveCfg({ someUnknownKey: 123 });
  assert.equal(mod.getState().someUnknownKey, undefined);
});

// ─── 模型读取 ───
test('getAvailableVisionModels：只返回带 image 输入能力的模型', () => {
  writeModels({
    providers: {
      p1: {
        name: '视觉厂',
        models: [
          { id: 'vision-a', input: ['text', 'image'] },
          { id: 'text-only', input: ['text'] },
        ],
      },
      p2: {
        name: '纯文本厂',
        models: [{ id: 'plain', input: ['text'] }],
      },
    },
  });
  const result = mod.getAvailableVisionModels();
  assert.equal(result.length, 1, '只有 p1 有视觉模型');
  assert.equal(result[0].providerId, 'p1');
  assert.deepEqual(result[0].models.map(m => m.id), ['vision-a']);
});

test('getAvailableVisionModels：无 models.json 时返回空数组', () => {
  assert.deepEqual(mod.getAvailableVisionModels(), []);
});

test('getAllModels：返回所有 provider 的模型', () => {
  writeModels({
    providers: {
      p1: { name: 'A', models: [{ id: 'm1' }, { id: 'm2' }] },
      p2: { name: 'B', models: [{ id: 'm3' }] },
    },
  });
  const result = mod.getAllModels();
  assert.equal(result.length, 2);
  assert.equal(result[0].models.length, 2);
  assert.equal(result[1].models.length, 1);
});

test('getProviderApiConfig：读取 provider 的 key 和 baseUrl', () => {
  writeCatalog({
    providers: {
      good: { api_key: 'sk-test-123', base_url: 'https://api.example.com/v1' },
      legacy: { api_key: 'sk-2', api_base: 'https://legacy.example.com/v1' },
    },
  });
  assert.deepEqual(mod.getProviderApiConfig('good'), {
    apiKey: 'sk-test-123',
    baseUrl: 'https://api.example.com/v1',
  });
  // 兼容 api_base 字段
  assert.deepEqual(mod.getProviderApiConfig('legacy'), {
    apiKey: 'sk-2',
    baseUrl: 'https://legacy.example.com/v1',
  });
  // 不存在的 provider 返回空
  assert.deepEqual(mod.getProviderApiConfig('nope'), { apiKey: '', baseUrl: '' });
});

// ─── 状态 ───
test('getState：返回副本，外部修改不影响内部 state', () => {
  const s1 = mod.getState();
  s1.fontSize = 999;
  assert.notEqual(mod.getState().fontSize, 999);
});

// ─── 端口动态读取 ───
test('getAppPort：默认 18900，port.json 存在时读取实际端口，端口变化能更新', async () => {
  assert.equal(mod.getAppPort(), 18900);
  // 写一个 port.json（模拟 Python 端端口被占用后跳号上报）
  const dir = join(TEST_HOME, 'data', 'zaiganma');
  mkdirSync(dir, { recursive: true });
  writeFileSync(join(dir, 'port.json'), JSON.stringify({ port: 18901 }), 'utf-8');
  assert.equal(mod.getAppPort(), 18901);
  // 端口再次变化（如下次启动 18900 空闲），新文件覆盖旧值
  writeFileSync(join(dir, 'port.json'), JSON.stringify({ port: 18900 }), 'utf-8');
  assert.equal(mod.getAppPort(), 18900);
});

// ─── 伙伴加载（通过 saveCfg 间接覆盖 loadBuddiesFromAgents） ───
test('buddies 名称引号被清洗（config.yaml 的 name 带引号）', () => {
  mod.saveCfg({ buddies: {} });
  assert.equal(mod.getState().buddies['hanako'].name, '小花');
});

// ─── 跨重启持久化（onload 模拟插件重载） ───
test('onload：自定义伙伴（不在 agents 目录）跨重启保留，颜色不丢', async () => {
  // 模拟上次会话保存了自定义伙伴 ghost + hanako 的自定义颜色
  writeCfg({
    buddies: {
      ghost: { name: '幽灵', color: '#00FF00', styleDesc: '神秘伙伴' },
      hanako: { name: '小花', color: '#FF0000', styleDesc: '' },
    },
  });
  const plugin = new mod.default();
  plugin.ctx = { log: {} };
  await plugin.onload();
  const state = mod.getState();
  // 自定义伙伴完整保留
  assert.ok(state.buddies['ghost'], '不在 agents 目录的自定义伙伴应保留');
  assert.equal(state.buddies['ghost'].name, '幽灵');
  assert.equal(state.buddies['ghost'].color, '#00FF00');
  // agents 伙伴保留用户自定义颜色
  assert.equal(state.buddies['hanako'].color, '#FF0000', 'agents 伙伴的用户颜色应保留');
  // agents 扫描的伙伴也在
  assert.ok(state.buddies['yumi'], 'agents 伙伴应被加载');
});

// ─── 损坏的端口文件 ───
test('getAppPort：损坏的 port.json 不抛异常', () => {
  const dir = join(TEST_HOME, 'data', 'zaiganma');
  mkdirSync(dir, { recursive: true });
  writeFileSync(join(dir, 'port.json'), '{broken json', 'utf-8');
  const port = mod.getAppPort();
  assert.equal(typeof port, 'number');
  assert.ok(port > 0);
});
