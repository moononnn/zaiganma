// 在干嘛 — 主入口
// 管理 Python 小程序进程 + 状态 + 模型读取

import { spawn } from 'node:child_process';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { existsSync, readFileSync, writeFileSync, mkdirSync, readdirSync, statSync } from 'node:fs';
import { homedir, tmpdir } from 'node:os';

const __dirname = dirname(fileURLToPath(import.meta.url));
const HANA_HOME = process.env.HANA_HOME || join(homedir(), '.hanako');
const DATA_DIR = join(HANA_HOME, 'data', 'zaiganma');
const CFG_PATH = join(DATA_DIR, 'config.json');
const MODELS_JSON = join(HANA_HOME, 'models.json');
const PROVIDER_CATALOG = join(HANA_HOME, 'provider-catalog.json');

const PY_DIR = join(__dirname, 'python');
const APP_PORT = 18900;

let ctx = {};
let appProcess = null;

// ═══════════════════════════════
//  默认状态
// ═══════════════════════════════
let state = {
  running: false,
  port: APP_PORT,
  // 截图模型
  visionSource: 'hana',    // 'hana' | 'custom'
  visionProviderId: '',
  visionModelId: '',
  visionCustomBaseUrl: '',
  visionCustomApiKey: '',
  visionCustomModel: '',
  // 弹幕文案模型
  danmuSource: 'same',     // 'same' | 'hana' | 'custom'
  danmuProviderId: '',
  danmuModelId: '',
  danmuCustomBaseUrl: '',
  danmuCustomApiKey: '',
  danmuCustomModel: '',
  // 弹幕行为
  danmuMode: true,
  styles: ['casual'],      // 勾选风格列表
  intervalMode: 'fixed',
  intervalSec: 30,
  intervalMin: 15,
  intervalMax: 60,
  danmuCount: 1,
  // 外观
  fontSize: 30,
  fontFamily: 'Microsoft YaHei',
  opacity: 0.85,
  shadowMode: 'outline',
  danmuColors: ['#FFFFFF', '#FF6B6B', '#51CF66', '#339AF0', '#FCC419', '#CC5DE8'],
  rainbowMode: false,
  displayArea: 'full',
  // 显示设置（百分比值，0-100）
  density: 33,      // 显示密度 → tracks: 5~30, max_onscreen: 5~50
  speedPct: 30,     // 滚动速度 → speed: 0.5~8.0
  areaMode: 'top_third',  // 显示区域: top_third / top_half / full
  tracks: 8,        // 底层渲染值（由百分比映射生成，仅用于状态同步）
  speed: 2.8,
  maxOnscreen: 8,
  topMargin: 80,
  // 空闲自动暂停
  idleAutoPause: true,
  idleThreshold: 600,

  // 弹幕伙伴
  buddyIntervalMode: 'fixed',  // 'fixed' | 'random'
  buddyInterval: 90,           // 固定间隔（秒）
  buddyIntervalMin: 60,        // 随机最小间隔（秒）
  buddyIntervalMax: 180,       // 随机最大间隔（秒）
  buddyMode: false,
  selectedBuddies: [],
  buddyMemoryRatio: 30,
  buddies: {},
  // 自定义称呼池
  nicknames: [],
  // 伙伴称呼池
  buddyNicknames: [],
};

// ═══════════════════════════════
//  配置文件读写
// ═══════════════════════════════
function loadCfg() {
  try {
    if (existsSync(CFG_PATH)) {
      return JSON.parse(readFileSync(CFG_PATH, 'utf-8'));
    }
  } catch (e) { ctx.log?.error?.('[zaiganma] 配置读取失败:', e.message); }
  return {};
}

// 从 Hana Agent 目录动态加载伙伴列表
const BUDDY_COLORS = ['#FF6B6B', '#74C0FC', '#DA77F2', '#63E6BE', '#FFA94D', '#339AF0', '#FCC419', '#51CF66'];
function loadBuddiesFromAgents() {
  const buddies = {};
  try {
    const agentsPath = join(HANA_HOME, 'agents');
    if (!existsSync(agentsPath)) return buddies;
    const dirs = readdirSync(agentsPath).filter(function(d) {
      const p = join(agentsPath, d);
      try { return statSync(p).isDirectory() && existsSync(join(p, 'config.yaml')); }
      catch(e) { return false; }
    });
    let colorIdx = 0;
    for (const agentId of dirs) {
      try {
        const cfgRaw = readFileSync(join(agentsPath, agentId, 'config.yaml'), 'utf-8');
        const m = cfgRaw.match(/^\s*name:\s*(.+)$/m);
        const name = m ? m[1].trim() : agentId;
        let styleDesc = '';
        const descPath = join(agentsPath, agentId, 'description.md');
        if (existsSync(descPath)) {
          styleDesc = readFileSync(descPath, 'utf-8').trim();
        }
        buddies[agentId] = {
          name: name,
          color: BUDDY_COLORS[colorIdx % BUDDY_COLORS.length],
          styleDesc: styleDesc,
        };
        colorIdx++;
      } catch (e) {
        ctx.log?.warn?.('[zaiganma] 读取助手失败:', agentId, e.message);
      }
    }
  } catch (e) {
    ctx.log?.error?.('[zaiganma] 加载助手列表失败:', e.message);
  }
  return buddies;
}

export function saveCfg(data) {
  if (!existsSync(DATA_DIR)) mkdirSync(DATA_DIR, { recursive: true });
  const existing = loadCfg();
  // 如果提交的 buddies 为空，从 agents 目录补全
  if (!data.buddies || Object.keys(data.buddies).length === 0) {
    const loaded = loadBuddiesFromAgents();
    if (Object.keys(loaded).length > 0) {
      data.buddies = loaded;
    }
  }
  // 处理伙伴颜色更新（保留完整的伙伴数据，只改颜色）
  if (data._buddyColors) {
    if (!existing.buddies) existing.buddies = {};
    for (const [bid, color] of Object.entries(data._buddyColors)) {
      if (state.buddies[bid]) state.buddies[bid].color = color;
      // 从默认配置中取完整的伙伴数据
      const fullBuddy = state.buddies[bid];
      if (fullBuddy) {
        existing.buddies[bid] = { ...fullBuddy };
        existing.buddies[bid].color = color;
      }
    }
    delete data._buddyColors;
  }
  // 确保 buddies 永远有完整数据（name + styleDesc + color）
  if (existing.buddies) {
    for (const [bid, bv] of Object.entries(existing.buddies)) {
      const defaultBuddy = state.buddies[bid];
      if (defaultBuddy) {
        existing.buddies[bid] = { ...defaultBuddy, ...bv };
      }
    }
  }

  const merged = { ...existing, ...data };
  writeFileSync(CFG_PATH, JSON.stringify(merged, null, 2), 'utf-8');
  // 更新内存
  for (const [k, v] of Object.entries(data)) {
    if (k in state) state[k] = v;
  }
}

/** 同步配置到正在运行的 Python 小程序，返回是否成功 */
export async function syncConfigToApp() {
  try {
    const resp = await fetch(`http://127.0.0.1:${APP_PORT}/config/reload`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(state),
      signal: AbortSignal.timeout(3000),
    });
    return resp.ok;
  } catch (e) {
    return false;
  }
}

// ═══════════════════════════════
//  模型读取（从 Hana 配置）
// ═══════════════════════════════
export function getAvailableVisionModels() {
  const result = [];
  try {
    if (!existsSync(MODELS_JSON)) return result;
    const catalog = JSON.parse(readFileSync(MODELS_JSON, 'utf-8'));
    for (const [pid, provider] of Object.entries(catalog.providers || {})) {
      const visionModels = (provider.models || []).filter(m =>
        (m.input || []).includes('image')
      );
      if (visionModels.length === 0) continue;
      result.push({
        providerId: pid,
        providerName: provider.name || pid,
        models: visionModels.map(m => ({
          id: m.id,
          name: m.name || m.id,
          contextWindow: m.contextWindow || 0,
        })),
      });
    }
  } catch (e) { ctx.log?.error?.('[zaiganma] 模型列表读取失败:', e.message); }
  return result;
}

export function getAllModels() {
  const result = [];
  try {
    if (!existsSync(MODELS_JSON)) return result;
    const catalog = JSON.parse(readFileSync(MODELS_JSON, 'utf-8'));
    for (const [pid, provider] of Object.entries(catalog.providers || {})) {
      const models = (provider.models || []).map(m => ({
        id: m.id,
        name: m.name || m.id,
        contextWindow: m.contextWindow || 0,
      }));
      if (models.length > 0) {
        result.push({
          providerId: pid,
          providerName: provider.name || pid,
          models,
        });
      }
    }
  } catch (e) {}
  return result;
}

export function getProviderApiConfig(providerId) {
  try {
    if (existsSync(PROVIDER_CATALOG)) {
      const catalog = JSON.parse(readFileSync(PROVIDER_CATALOG, 'utf-8'));
      const provider = catalog.providers?.[providerId];
      if (provider) {
        return {
          apiKey: provider.api_key || '',
          baseUrl: provider.base_url || provider.api_base || '',
        };
      }
    }
  } catch (e) {}
  return { apiKey: '', baseUrl: '' };
}

// ═══════════════════════════════
//  Python 检测
// ═══════════════════════════════
const PYTHON_CANDIDATES = [
  'C:\\Python314\\python.exe',
  'C:\\Python313\\python.exe',
  'C:\\Python312\\python.exe',
  'python',
  'python3',
];
function detectPython() {
  for (const p of PYTHON_CANDIDATES) {
    if (existsSync(p)) return p;
  }
  return 'python';
}

// ═══════════════════════════════
//  小程序进程管理
// ═══════════════════════════════
export function startApp() {
  ctx.log?.info?.('[zaiganma] startApp 开始, appProcess=', !!appProcess);
  if (appProcess) { ctx.log?.info?.('[zaiganma] startApp appProcess 非空，跳过'); return; }
  const python = detectPython();
  ctx.log?.info?.('[zaiganma] startApp python路径:', python);
  const script = join(PY_DIR, 'zaiganma_app.py');
  ctx.log?.info?.('[zaiganma] startApp 脚本路径:', script, '存在:', existsSync(script));
  if (!existsSync(script)) {
    ctx.log?.error?.('[zaiganma] zaiganma_app.py 未找到');
    return;
  }

  // 构建环境变量（传递完整配置）
  const env = { ...process.env };
  env.ZAIGANMA_PORT = String(APP_PORT);
  env.ZAIGANMA_CONFIG = CFG_PATH;
  env.ZAIGANMA_HANA_BASE = process.env.HANA_BASE_URL || `http://127.0.0.1:14500`;
  env.HANA_HOME = HANA_HOME;
  env.PYTHONDONTWRITEBYTECODE = '1';

  ctx.log?.info?.('[zaiganma] 启动小程序...');
  appProcess = spawn(python, [script], {
    cwd: PY_DIR,
    stdio: ['ignore', 'pipe', 'pipe'],
    env,
  });

  appProcess.stdout?.on('data', (d) => {
    const s = d.toString().trim();
    if (s) ctx.log?.info?.('[zaiganma-app]', s);
  });
  appProcess.stderr?.on('data', (d) => {
    const s = d.toString().trim();
    if (s && !s.includes('libpng')) ctx.log?.warn?.('[zaiganma-app]', s);
  });
  appProcess.on('exit', (code) => {
    ctx.log?.info?.('[zaiganma] 小程序退出, code:', code);
    appProcess = null;
    state.running = false;
  });
  appProcess.on('error', (err) => {
    ctx.log?.error?.('[zaiganma] 启动失败:', err.message);
    appProcess = null;
    state.running = false;
  });

  state.running = true;
}

export function stopApp() {
  if (!appProcess) return;
  try { appProcess.kill(); } catch (e) {}
  appProcess = null;
  state.running = false;
}

export function getState() {
  return { ...state };
}

export { loadCfg };

// ═══════════════════════════════
//  配置同步到小程序
// ═══════════════════════════════
async function syncToApp() {
  try {
    const resp = await fetch(`http://127.0.0.1:${APP_PORT}/config/reload`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(state),
      signal: AbortSignal.timeout(3000),
    });
    return resp.ok;
  } catch (e) {
    // 小程序可能还没启动，静默忽略
  }
}

// ═══════════════════════════════
//  HTTP 通信辅助
// ═══════════════════════════════
export async function appFetch(path, opts = {}) {
  const url = `http://127.0.0.1:${APP_PORT}${path}`;
  const resp = await fetch(url, {
    ...opts,
    signal: AbortSignal.timeout(5000),
  });
  return resp;
}

// ═══════════════════════════════
//  依赖检查
// ═══════════════════════════════
export async function checkDeps() {
  const python = detectPython();
  const deps = ['mss', 'PIL', 'httpx', 'PyQt6'];
  for (const dep of deps) {
    const p = spawn(python, ['-c', `import ${dep}`], { stdio: 'ignore' });
    const code = await new Promise(r => p.on('exit', r));
    if (code !== 0) return { ok: false, missing: dep };
  }
  return { ok: true };
}

// ═══════════════════════════════
//  Lifecycle
// ═══════════════════════════════
export default class ZaiganmaPlugin {
  async onload() {
    ctx = this.ctx;
    detectPython();
    ctx.log?.info?.('[zaiganma] 插件已加载');

    // 恢复持久化配置
    const cfg = loadCfg();
    ctx.log?.info?.('[zaiganma] config.json:', JSON.stringify(cfg));
    const restored = [];
    for (const [k, v] of Object.entries(cfg)) {
      if (k in state) {
        // 伙伴配置需要合并（config 只存了 color，保留默认的 name/styleDesc）
        if (k === 'buddies' && typeof v === 'object') {
          for (const [bid, bv] of Object.entries(v)) {
            if (state.buddies[bid]) {
              Object.assign(state.buddies[bid], bv);
            }
          }
        } else {
          state[k] = v;
        }
        restored.push(k);
      } else {
        ctx.log?.info?.('[zaiganma] 跳过键:', k);
      }
    }
    ctx.log?.info?.('[zaiganma] 已恢复:', restored.join(','));
    ctx.log?.info?.('[zaiganma] state.tracks:', state.tracks, 'state.speed:', state.speed);

    // 清洗昵称数组（防止旧配置残留空字符串）
    if (Array.isArray(state.nicknames)) state.nicknames = state.nicknames.filter(s => s && s.trim());
    if (Array.isArray(state.buddyNicknames)) state.buddyNicknames = state.buddyNicknames.filter(s => s && s.trim());

    // 动态加载伙伴列表
    const agentsBuddies = loadBuddiesFromAgents();
    // 保留用户已选过的颜色
    if (state.buddies) {
      for (const [bid, bv] of Object.entries(state.buddies)) {
        if (agentsBuddies[bid] && bv.color) {
          agentsBuddies[bid].color = bv.color;
        }
      }
    }
    state.buddies = agentsBuddies;
    ctx.log?.info?.('[zaiganma] 已加载伙伴:', Object.keys(state.buddies).join(','));

    // 从 users.json 读取用户名（首次使用时自动获取并持久化）
    if (!state.userName) {
      try {
        const usersPath = join(HANA_HOME, 'users.json');
        if (existsSync(usersPath)) {
          const usersData = JSON.parse(readFileSync(usersPath, 'utf-8'));
          const displayName = usersData.defaultUserId
            ? usersData.users?.find(u => u.userId === usersData.defaultUserId)?.displayName
            : usersData.users?.[0]?.displayName;
          if (displayName) {
            state.userName = displayName;
            // 持久化到 config.json
            const cfg = loadCfg();
            cfg.userName = displayName;
            writeFileSync(CFG_PATH, JSON.stringify(cfg, null, 2), 'utf-8');
            ctx.log?.info?.('[zaiganma] 已读取用户名:', displayName);
          }
        }
      } catch (e) {
        ctx.log?.error?.('[zaiganma] 用户名读取失败:', e.message);
      }
    }

    // 自动启动弹幕小程序
    // 不在这里启动，等打开插件页面时再启动
    // startApp();
  }

  async onunload() {
    stopApp();
    ctx.log?.info?.('[zaiganma] 插件已卸载');
  }
}
