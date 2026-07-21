// 在干嘛 — API + 页面路由

import { existsSync, readFileSync, readdirSync, statSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { homedir } from 'node:os';

const __dirname = dirname(fileURLToPath(import.meta.url));

// 从 manifest.json 读取版本号（避免多处硬编码不一致）
const _manifest = JSON.parse(readFileSync(join(__dirname, '..', 'manifest.json'), 'utf-8'));
const PLUGIN_VERSION = _manifest.version || '0.0.0';

import {
  getState, loadCfg, startApp, stopApp, saveCfg, syncConfigToApp,
  getAvailableVisionModels, getAllModels, getProviderApiConfig,
  appFetch, checkDeps,
} from '../index.js';

function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

export default async function registerRoutes(app, ctx = {}) {
  ctx.log?.info?.('[zaiganma] 路由已注册');

  // ── 设置页面（打开时自动启动小程序） ──
  app.get('/page', async (c) => {
    try {
      if (!getState().running) {
        startApp();
      }
    } catch (e) {
      ctx.log?.error?.('[zaiganma] 启动小程序失败:', e.message);
    }

    const token = c.req.query('token') || '';
    const auth = token ? '?token=' + encodeURIComponent(token) : '';
    
    // 服务端读取初始数据
    let state = {};
    let visionModels = [];
    let allModels = [];
    let engineRunning = false;
    let workvisitAvailable = false;
    try {
      state = getState();
      // 直接从 config.json 覆盖（解决 onload 异步时序问题）
      // 注意：buddies 需要合并而不是直接覆盖，否则会丢掉 name/styleDesc
      const cfg = loadCfg();
      for (const [k, v] of Object.entries(cfg)) {
        if (k in state) {
          if (k === 'buddies' && typeof v === 'object') {
            for (const [bid, bv] of Object.entries(v)) {
              if (state.buddies[bid]) {
                Object.assign(state.buddies[bid], bv);
              }
            }
          } else {
            state[k] = v;
          }
        }
      }
      visionModels = getAvailableVisionModels();
      allModels = getAllModels();
      // 读取引擎状态（带重试，给启动中的小程序一点时间）
      for (var _rt = 0; _rt < 6; _rt++) {
        try {
          var _sr = await appFetch('/status');
          if (_sr.ok) {
            var _st = await _sr.json();
            engineRunning = !!_st.running;
            workvisitAvailable = !!_st.workvisit_available;
            break;
          }
        } catch(e) {}
        await new Promise(function(r) { setTimeout(r, 1000); });
      }
    } catch(e) {}
    
    // 判断模型是否已配置（用于视觉引导）
    var hasVisionConfig = state.visionSource === 'custom'
      ? !!(state.visionCustomBaseUrl && state.visionCustomApiKey)
      : !!(state.visionProviderId && state.visionModelId);
    var hasDanmuConfig = state.danmuSource === 'custom'
      ? !!(state.danmuCustomBaseUrl && state.danmuCustomApiKey)
      : state.danmuSource === 'same' ? true
      : !!(state.danmuProviderId && state.danmuModelId);
    var modelConfigured = hasVisionConfig && hasDanmuConfig;
    
    // 读取闲不住展板数据
    let buddyBoard = {};
    try {
      const HANA_HOME = process.env.HANA_HOME || join(homedir(), '.hanako');
      const wvPath = join(HANA_HOME, 'data', 'work-visit', 'data.json');
      if (existsSync(wvPath)) {
        const wvRaw = readFileSync(wvPath, 'utf-8');
        const wvData = JSON.parse(wvRaw);
        const partners = wvData.partnerConfig || {};
        // 从 days 取最新的 narrative
        const dayKeys = Object.keys(wvData.days || {}).sort();
        const lastDay = dayKeys.length > 0 ? wvData.days[dayKeys[dayKeys.length - 1]] : null;
        const idlePool = wvData.idlePool || ['在摸鱼 🐟'];
        for (const [bid, cfg] of Object.entries(partners)) {
          const vars = cfg.variables || {};
          // 取最新 narrative
          // 生成今日日期字符串（北京时间）
          const _now = new Date();
          const _bj = new Date(_now.getTime() + 480 * 60000);
          const _pad = n => String(n).padStart(2, '0');
          const ts = `${_bj.getUTCFullYear()}-${_pad(_bj.getUTCMonth() + 1)}-${_pad(_bj.getUTCDate())}`;
          // 当前状态：扫描今日会话 → 闲不住 narrative → idlePool
          let narrative = '';
          // 先扫描会话文件获取实时状态
          try {
            const sessionsDir = join(HANA_HOME, 'agents', bid, 'sessions');
            if (existsSync(sessionsDir)) {
              const files = readdirSync(sessionsDir).filter(f => f.endsWith('.jsonl') && f.startsWith(ts)).sort().reverse().slice(0, 3);
              for (const f of files) {
                const content = readFileSync(join(sessionsDir, f), 'utf-8');
                const lines = content.split('\n').filter(Boolean);
                for (let li = lines.length - 1; li >= 0; li--) {
                  try {
                    const d = JSON.parse(lines[li]);
                    if (d.type === 'message' && d.message?.content) {
                      const items = d.message.content;
                      for (const item of items) {
                        if (item.type === 'text' && item.text && item.text.length > 8 && item.text.length < 120) {
                          narrative = item.text.substring(0, 80);
                          break;
                        }
                      }
                    }
                    if (narrative) break;
                  } catch {}
                }
                if (narrative) break;
              }
            }
          } catch (e) {}
          // 如果没有扫描到，用闲不住 narrative
          if (!narrative && lastDay && lastDay.partners && lastDay.partners[bid]) {
            narrative = lastDay.partners[bid].narrative || '';
          }
          if (!narrative) {
            narrative = idlePool[Math.floor(Math.random() * idlePool.length)];
          }
          // 装饰数据
          const deco = cfg.decorations || null;
          let frameClass = '';
          let bgClass = '';
          if (deco && deco.equipped) {
            if (deco.equipped.avatarFrame === 'avatar_flower') frameClass = ' frame-flower';
            else if (deco.equipped.avatarFrame === 'avatar_star') frameClass = ' frame-star';
            if (deco.equipped.cardBg === 'bg_warm') bgClass = ' bg-warm';
            else if (deco.equipped.cardBg === 'bg_cool') bgClass = ' bg-cool';
          }
          // 头像路径
          const avatarPath = join(HANA_HOME, 'agents', bid, 'avatars', 'agent.png');
          const hasAvatar = existsSync(avatarPath);
          buddyBoard[bid] = {
            energy: vars.energy ?? 80,
            mood: vars.mood ?? 60,
            affection: vars.affection ?? 0,
            narrative: narrative,
            hasAvatar: hasAvatar,
            frameClass: frameClass,
            bgClass: bgClass,
          };
        }
      }
    } catch (e) {
      ctx.log?.error?.('[zaiganma] 闲不住数据读取失败:', e.message);
    }
    
    // 计算插件 base URL（用于头像等资源）
    let pluginBase = '';
    try {
      const urlObj = new URL(c.req.url, 'http://localhost');
      pluginBase = urlObj.pathname.replace(/\/page\/?$/, '').replace(/\/+$/, '');
    } catch(e) {}
    
    // 读取 app.js
    let appJs = '';
    try {
      const jsPath = join(__dirname, '../public/app.js');
      appJs = readFileSync(jsPath, 'utf-8');
    } catch (e) {
      ctx.log?.error?.('[zaiganma] app.js 读取失败:', e.message);
    }
    
    // 构建设置面板 HTML
    function opt(v, d) { return v != null ? v : d; }
    function selVal(sels, cur) {
      var r = '';
      sels.forEach(function(s){
        var sel = s.value === cur ? ' selected' : '';
        r += '<option value="'+escAttr(s.value)+'"'+sel+'>'+escHtml(s.label)+'</option>';
      });
      return r;
    }
    function escHtml(s) { return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }
    function escAttr(s) { return String(s).replace(/"/g,'&quot;').replace(/&/g,'&amp;'); }
    
    var css = [];
    var html = [];
    
    // 样式
    css.push(':root{--bg:#fafafa;--card:#fff;--border:#e5e5e5;--text:#171717;--text-secondary:#737373;--accent:#6366f1;--accent-soft:rgba(99,102,241,0.08);--radius:10px;--danger:#ef4444;--success:#22c55e}');
    css.push('*{margin:0;padding:0;box-sizing:border-box}');
    css.push('body{font-family:system-ui,-apple-system,"Microsoft YaHei",sans-serif;font-size:14px;background:var(--bg);color:var(--text);line-height:1.5;padding:16px 14px 36px;max-width:440px;margin:0 auto;min-height:100vh}');
    css.push('.topbar{display:flex;align-items:center;justify-content:space-between;padding-bottom:12px;margin-bottom:14px;border-bottom:1px solid var(--border)}');
    css.push('.topbar h1{font-size:18px;font-weight:600;display:flex;align-items:center;gap:6px}');
    css.push('.dot{width:8px;height:8px;border-radius:50%;flex-shrink:0}');
    css.push('.dot.on{background:var(--success);box-shadow:0 0 6px rgba(34,197,94,.3)}');
    css.push('.dot.off{background:#d4d4d4}');
    css.push('.status-text{font-size:12px;color:var(--text-secondary)}');css.push('.tgl-btn{display:inline-flex;align-items:center;gap:3px;padding:3px 8px;border-radius:12px;border:1px solid var(--border);font-size:11px;cursor:pointer;background:var(--card);color:var(--text-secondary);user-select:none;white-space:nowrap}');css.push('.tgl-btn:hover{background:var(--accent-soft);border-color:var(--accent)}');css.push('.tgl-btn .tgl-dot{width:6px;height:6px;border-radius:50%;flex-shrink:0}');css.push('.tgl-btn .tgl-dot.on{background:var(--success)}');css.push('.tgl-btn .tgl-dot.off{background:#d4d4d4}');
    css.push('.card{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);padding:14px;margin-bottom:10px}');
    css.push('.card-header{display:flex;align-items:center;gap:6px;font-size:13px;font-weight:600;color:var(--text);margin-bottom:12px}');
    css.push('.card-header .icon{font-size:15px}');
    css.push('.row{display:flex;align-items:center;justify-content:space-between;margin-bottom:8px;gap:8px;min-height:30px}');
    css.push('.row:last-child{margin-bottom:0}');
    css.push('.row label{font-size:13px;color:var(--text-secondary);min-width:60px;flex-shrink:0}');
    css.push('.row .val{font-size:12px;color:var(--text-secondary);min-width:32px;text-align:right}');
    css.push('.row select,.row input[type=number],.row input[type=text],.row input[type=password]{padding:5px 8px;border-radius:6px;border:1px solid var(--border);background:var(--bg);color:var(--text);font-size:13px;outline:none;transition:.15s}');
    css.push('.row select:focus,.row input:focus{border-color:var(--accent)}');
    css.push('.row select{flex:1;max-width:190px}');
    css.push('.row input[type=number]{width:60px;text-align:center}');
    css.push('.row input[type=range]{flex:1;height:4px;-webkit-appearance:none;background:var(--border);border:none;border-radius:2px;padding:0;margin:0 8px}');
    css.push('.row input[type=range]::-webkit-slider-thumb{-webkit-appearance:none;width:15px;height:15px;border-radius:50%;background:var(--accent);cursor:pointer;border:2px solid #fff;box-shadow:0 1px 3px rgba(0,0,0,0.15)}');
    css.push('.row input[type=color]{width:32px;height:28px;padding:1px;border-radius:6px;border:1px solid var(--border);cursor:pointer}');
    css.push('.field{margin-bottom:8px}');
    css.push('.field label{display:block;font-size:11px;color:var(--text-secondary);margin-bottom:2px}');
    css.push('.field input{width:100%;padding:6px 8px;border-radius:6px;border:1px solid var(--border);background:var(--bg);color:var(--text);font-size:13px;outline:none}');
    css.push('.field input:focus{border-color:var(--accent)}');
    css.push('.custom-block{margin-top:6px;padding:8px;border-radius:8px;background:var(--bg);border:1px dashed var(--border)}');
    css.push('.style-chips{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:6px}');
    css.push('.style-chip{display:flex;align-items:center;gap:4px;padding:5px 10px;border-radius:14px;border:1px solid var(--border);font-size:12px;cursor:pointer;transition:.15s;background:var(--card);-webkit-user-select:none}');
    css.push('.style-chip.on{background:var(--accent-soft)!important;border-color:var(--accent)!important;color:var(--accent)!important}');
    css.push('.btn{background:var(--accent);color:#fff;border:none;border-radius:8px;padding:10px 16px;font-size:13px;cursor:pointer;font-weight:500;transition:.15s;width:100%}');
    css.push('.btn-sm{padding:5px 10px;font-size:12px;width:auto;border-radius:6px;flex-shrink:0}');
    css.push('.btn-outline{background:transparent;border:1px solid var(--border);color:var(--text-secondary)}');
    css.push('.btn-row{display:flex;gap:6px;margin-top:8px}');
    css.push('.toast{position:fixed;bottom:24px;left:50%;transform:translateX(-50%);background:var(--accent);color:#fff;padding:8px 20px;border-radius:20px;font-size:12px;opacity:0;transition:opacity .3s;z-index:200;pointer-events:none;box-shadow:0 4px 12px rgba(0,0,0,0.15)}');
    css.push('.toast.show{opacity:1}.toast.error{background:var(--danger)}.toast.success{background:var(--success)}');
    css.push('.palette{display:flex;flex-wrap:wrap;gap:4px}');
    css.push('.swatch{width:20px;height:20px;border-radius:4px;border:1px solid var(--border);cursor:pointer;transition:.15s}');
    css.push('.swatch.sel{box-shadow:0 0 0 2px var(--accent);transform:scale(1.15)}');
    css.push('.buddy-check{margin:0;cursor:pointer}');
    css.push('.buddy-list{padding:4px 0}');
    css.push('.buddy-swatch{border:2px solid transparent;transition:.1s}');
    css.push('.buddy-swatch:hover{border-color:var(--text-secondary)}');
    css.push('.buddy-swatch.sel{border-color:var(--accent)!important;transform:scale(1.15)}');
    // 展板样式（仿闲不住）
    css.push('.buddy-board{display:flex;flex-direction:column;gap:6px}');
    css.push('.buddy-card{display:flex;align-items:center;gap:10px;padding:9px 12px;background:var(--card);border:1px solid var(--border);border-radius:var(--radius);transition:box-shadow .15s}');
    css.push('.buddy-card:hover{border-color:var(--accent)}');
    css.push('.buddy-avatar{width:30px;height:30px;border-radius:5px;display:flex;align-items:center;justify-content:center;color:#fff;font-size:13px;font-weight:500;flex-shrink:0}');
    css.push('.buddy-avatar-img{width:30px;height:30px;flex-shrink:0}');
    css.push('.buddy-avatar-img img{width:100%;height:100%;object-fit:cover;display:block;border-radius:5px;overflow:hidden}');
    css.push('.buddy-info{flex:1;min-width:0}');
    css.push('.buddy-name{font-size:13px;font-weight:500;line-height:1.3}');
    css.push('.buddy-doing{font-size:11px;color:var(--text-secondary);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;line-height:1.3;margin-top:1px;cursor:default}');
    css.push('.buddy-vars{display:flex;align-items:center;gap:6px;margin-top:4px}');
    css.push('.buddy-energy{display:flex;align-items:center;gap:4px;flex:1;min-width:0}');
    css.push('.energy-bar-bg{flex:1;height:4px;background:var(--border);border-radius:2px;overflow:hidden;min-width:30px}');
    css.push('.energy-bar-fill{height:100%;border-radius:2px;transition:width .3s}');
    css.push('.energy-num{font-size:10px;color:var(--text-secondary);min-width:18px;text-align:right}');
    css.push('.buddy-mood{font-size:14px;line-height:1;cursor:default;flex-shrink:0}');
    css.push('.buddy-affection{font-size:11px;line-height:1;cursor:default;flex-shrink:0;margin-left:2px}');
    css.push('.buddy-right{display:flex;align-items:center;gap:6px;flex-shrink:0}');
    css.push('.color-ball{width:18px;height:18px;border-radius:50%;border:2px solid var(--border);cursor:pointer;transition:.15s;flex-shrink:0}');
    css.push('.color-ball:hover{border-color:var(--accent);transform:scale(1.15)}');
    css.push('.color-ball.rainbow-ball{background:linear-gradient(135deg,#FF6B6B,#FCC419,#51CF66,#339AF0,#CC5DE8)!important}');
    css.push('.color-picker-popup{display:none;position:absolute;background:var(--card);border:1px solid var(--border);border-radius:8px;padding:8px;box-shadow:0 4px 16px rgba(0,0,0,0.12);z-index:100;margin-top:4px;right:0}');
    css.push('.color-picker-popup.show{display:flex;flex-wrap:wrap;gap:4px;width:156px}');
    css.push('.color-picker-popup .cp-swatch{width:20px;height:20px;border-radius:4px;border:1px solid var(--border);cursor:pointer;transition:.1s}');
    css.push('.color-picker-popup .cp-swatch:hover{transform:scale(1.2);border-color:var(--accent)}');
    css.push('.buddy-check-wrap{display:flex;align-items:center;flex-shrink:0}');
    css.push('.buddy-check-wrap input{margin:0;cursor:pointer;width:16px;height:16px}');
    css.push('.buddy-badge{font-size:10px;padding:2px 8px;border-radius:10px;font-weight:500;flex-shrink:0;letter-spacing:.2px}');
    css.push('.buddy-badge.on{background:rgba(34,197,94,0.12);color:#1a7d1a}');
    css.push('.buddy-badge.off{background:var(--border);color:var(--text-secondary)}');
    // 装饰样式（完全复制闲不住）
    css.push('.buddy-avatar.frame-flower,.buddy-avatar-img.frame-flower{position:relative;box-shadow:0 0 0 3px rgba(157,95,77,0.25),0 0 0 7px rgba(157,95,77,0.08)}');
    css.push('.buddy-avatar.frame-star,.buddy-avatar-img.frame-star{position:relative;box-shadow:0 0 0 2px rgba(100,149,237,0.35),0 0 12px 5px rgba(100,149,237,0.15)}');
    css.push('.frame-star::after{content:"✨";position:absolute;bottom:-6px;right:-6px;font-size:14px;pointer-events:none;filter:drop-shadow(0 0 3px rgba(83,125,150,0.6));animation:twinkle 1.8s ease-in-out infinite}');
    css.push('.frame-star::before{content:"✨";position:absolute;top:-6px;left:-6px;font-size:14px;pointer-events:none;filter:drop-shadow(0 0 3px rgba(83,125,150,0.6));animation:twinkle 1.8s ease-in-out infinite;animation-delay:0.9s}');
    css.push('.frame-flower::after{content:"🌸";position:absolute;bottom:-9px;right:-9px;font-size:16px;pointer-events:none;animation:spin 3s linear infinite}');
    css.push('.frame-flower::before{content:"🌸";position:absolute;top:-9px;left:-9px;font-size:16px;pointer-events:none;animation:spin 3s linear infinite;animation-direction:reverse}');
    css.push('.bg-warm{background:#FDF6E3!important}');
    css.push('.bg-cool{background:#EEF2F7!important}');
    css.push('@keyframes twinkle{0%,100%{opacity:1;transform:scale(1)}50%{opacity:0.3;transform:scale(0.75)}}');
    css.push('@keyframes spin{0%{transform:rotate(0deg)}100%{transform:rotate(360deg)}}');
    // 弹窗样式
    css.push('.modal-overlay{position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.3);z-index:1000;display:none;align-items:center;justify-content:center}');
    css.push('.modal-overlay.show{display:flex}');
    css.push('.modal{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);padding:20px;max-width:380px;width:90%;box-shadow:0 8px 32px rgba(0,0,0,0.15);max-height:80vh;overflow-y:auto}');
    css.push('.modal h3{font-size:15px;font-weight:600;margin-bottom:12px;display:flex;align-items:center;justify-content:space-between}');
    css.push('.modal-close{font-size:18px;cursor:pointer;background:none;border:none;color:var(--text-secondary);padding:2px 6px;border-radius:4px}');
    css.push('.modal-close:hover{background:var(--accent-soft);color:var(--text)}');
    css.push('.modal .card{border:1px solid var(--border);border-radius:var(--radius);padding:14px;margin-bottom:10px}');
    css.push('.modal .card:last-child{margin-bottom:0}');
    css.push('.btn-warn{border-color:var(--danger)!important;color:var(--danger)!important;animation:warn-pulse 2s infinite}');
    css.push('.warn-dot{display:inline-block;width:6px;height:6px;border-radius:50%;background:var(--danger);margin-left:2px}');
    css.push('@keyframes warn-pulse{0%,100%{box-shadow:0 0 0 0 rgba(239,68,68,0.4)}50%{box-shadow:0 0 0 6px rgba(239,68,68,0)}}');
    css.push('.guide-card{background:#FFF8E1;border:1px solid #FFE082;border-radius:var(--radius);padding:12px 14px;margin-bottom:10px;font-size:12px;color:#795548;line-height:1.5}');
    css.push('.guide-card .guide-title{font-weight:600;font-size:13px;margin-bottom:4px}');
    
    // 顶栏
    html.push('<div class="topbar">');
    html.push('  <h1>📺 在干嘛</h1>');
    html.push('  <div style="display:flex;align-items:center;gap:6px">');
    html.push('    <button class="tgl-btn'+(modelConfigured?'':' btn-warn')+'" id="btnSettings" title="模型设置">⚙️'+(modelConfigured?'':' <span class="warn-dot"></span>')+'</button>');
    html.push('    <span class="dot '+(engineRunning?'on':'off')+'" id="dot"></span>');
    html.push('    <span class="status-text" id="statusText">'+(engineRunning?'运行中':'暂停')+'</span>');
    html.push('    <button class="tgl-btn" id="btnToggle" data-running="'+(engineRunning?'1':'0')+'">');
    html.push('      <span class="tgl-dot '+(engineRunning?'on':'off')+'" id="tglDot"></span>');
    html.push('      <span id="tglLabel">'+(engineRunning?'暂停':'启动')+'</span>');
    html.push('    </button>');
    html.push('  </div>');
    html.push('</div>');
    
    // 模型未配置引导卡
    if (!modelConfigured) {
      html.push('<div class="guide-card" id="guideCard">');
      html.push('  <div class="guide-title">⚙️ 先配置模型才能使用</div>');
      html.push('  <div class="guide-desc">点击右上角 ⚙️ 选择截图模型和弹幕文案模型，就可以开始看弹幕啦</div>');
      html.push('  <button class="btn-sm" id="guideOpenSettings" style="background:var(--accent);color:#fff;border:none;border-radius:6px;padding:4px 10px;font-size:11px;cursor:pointer;margin-top:6px">去配置 →</button>');
      html.push('</div>');
    }
    
    // 伙伴弹幕
    var buddyMode = state.buddyMode || false;
    var selectedBuddies = state.selectedBuddies || [];
    // 伙伴列表 fallback：如果 state 中 buddies 为空，直接从 agents 目录加载
    var buddies = state.buddies || {};
    if (Object.keys(buddies).length === 0) {
      try {
        var agentsPath = join(process.env.HANA_HOME || '', 'agents');
        if (existsSync(agentsPath)) {
          buddies = {};
          var BUDDY_COLORS = ['#FF6B6B', '#74C0FC', '#DA77F2', '#63E6BE', '#FFA94D', '#339AF0', '#FCC419', '#51CF66'];
          var dirs = readdirSync(agentsPath).filter(function(d) {
            try {
              return statSync(join(agentsPath, d)).isDirectory() && existsSync(join(agentsPath, d, 'config.yaml'));
            } catch(e) { return false; }
          });
          dirs.forEach(function(agentId, idx) {
            try {
              var cfgRaw = readFileSync(join(agentsPath, agentId, 'config.yaml'), 'utf-8');
              var m = cfgRaw.match(/^\s*name:\s*(.+)$/m);
              var name = m ? m[1].trim() : agentId;
              var styleDesc = '';
              var descPath = join(agentsPath, agentId, 'description.md');
              if (existsSync(descPath)) {
                styleDesc = readFileSync(descPath, 'utf-8').trim();
              }
              buddies[agentId] = { name: name, color: BUDDY_COLORS[idx % BUDDY_COLORS.length], styleDesc: styleDesc };
            } catch(e) {}
          });
        }
      } catch(e) {}
    }
    html.push('<div class="card"><div class="card-header"><span class="icon">🤖</span> 伙伴弹幕</div>');
    if (!workvisitAvailable) {
      html.push('<div style="font-size:11px;line-height:1.5;margin-bottom:8px;padding:8px 10px;background:#FFF8E1;border:1px solid #FFE082;border-radius:6px">');
      html.push('  <div style="color:#795548">💡 需要安装闲不住插件才能体验伙伴弹幕</div>');
      html.push('  <div style="margin-top:4px;word-break:break-all"><a href="https://github.com/moononnn/xianbuzhu" target="_blank" style="color:var(--accent);font-size:12px">https://github.com/moononnn/xianbuzhu</a></div>');
      html.push('</div>');
    } else {
      html.push('<div style="font-size:11px;color:var(--text-secondary);margin-bottom:8px;line-height:1.4">💡 已联动闲不住，伙伴弹幕会根据好感度和状态动态变化</div>');
    }
    // 伙伴弹幕控件始终渲染（隐藏但保留 DOM），防止 JS 事件绑定报错
    html.push('<div class="row"'+(workvisitAvailable?'':' style="display:none"')+'><label>启用</label><select id="buddyMode"><option value="false"'+(buddyMode===false?' selected':'')+'>关闭</option><option value="true"'+(buddyMode===true?' selected':'')+'>开启</option></select></div>');
    var bivMode = state.buddyIntervalMode || 'fixed';
    html.push('<div class="row"'+(workvisitAvailable?'':' style="display:none"')+'><label>间隔</label><select id="buddyIntervalMode" style="width:auto;min-width:60px"><option value="fixed"'+(bivMode==='fixed'?' selected':'')+'>固定</option><option value="random"'+(bivMode==='random'?' selected':'')+'>随机</option></select>');
    html.push('<div id="buddyFixedFields"'+(bivMode==='fixed'?'':' style="display:none"')+' style="display:inline-flex;align-items:center;gap:4px"><input type="number" id="buddyInterval" min="10" max="600" value="'+(state.buddyInterval||90)+'" style="width:72px"><span style="font-size:12px">秒</span></div>');
    html.push('<div id="buddyRandomFields"'+(bivMode==='random'?'':' style="display:none"')+' style="display:inline-flex;align-items:center;gap:4px"><input type="number" id="buddyIntervalMin" min="5" max="600" value="'+(state.buddyIntervalMin||60)+'" style="width:72px"><span style="font-size:12px">~</span><input type="number" id="buddyIntervalMax" min="5" max="600" value="'+(state.buddyIntervalMax||180)+'" style="width:72px"><span style="font-size:12px">秒</span></div></div>');
    html.push('<div id="buddyList"'+(buddyMode && workvisitAvailable?'':' style="display:none"')+' class="buddy-board"></div>');
    var memRatio = state.buddyMemoryRatio != null ? state.buddyMemoryRatio : 30;
    html.push('<div id="buddyMemFields"'+(buddyMode && workvisitAvailable?'':' style="display:none"')+'><div class="row"><label>🧠 聊起过往</label><input type="range" id="buddyMemoryRatio" min="0" max="100" value="'+memRatio+'"><span class="val" id="valBuddyMem">'+memRatio+'%</span></div>');
    html.push('<div class="row" style="flex-wrap:wrap;margin-top:-4px"><span style="font-size:11px;color:var(--text-secondary)">调高后伙伴更爱聊你之前做过的事，调低则更关注你当下在做什么</span></div></div>');
    var buddyNicknames = state.buddyNicknames || [];
    var buddyNicknameText = buddyNicknames.join('\n');
    html.push('<div id="buddyNickField" class="field" style="margin-top:8px'+(buddyMode && workvisitAvailable?'':';display:none')+'"><label>🏷️ 伙伴称呼</label><textarea id="buddyNicknames" rows="3" style="width:100%;padding:6px 8px;border-radius:6px;border:1px solid var(--border);background:var(--bg);color:var(--text);font-size:13px;outline:none;resize:vertical">'+escHtml(buddyNicknameText)+'</textarea></div>');
    html.push('<div id="buddyNickHint" class="row" style="flex-wrap:wrap'+(buddyMode && workvisitAvailable?'':';display:none')+'"><span style="font-size:11px;color:var(--text-secondary)">伙伴弹幕有35%概率用这里的称呼叫你，每行一个，留空则使用你在Hana的用户名</span></div>');
    html.push('</div></div>');
    
    // 弹幕风格
    var STYLES = [{id:'casual',n:'💬 自然闲聊'},{id:'familiar',n:'⭐ 老粉'},{id:'roast',n:'😏 嘴贱调侃'},{id:'onlooker',n:'🍉 吃瓜群众'},{id:'dramatic',n:'🎭 戏精中二'},{id:'empathy',n:'😭 破防共情'},{id:'weird',n:'🤪 无厘头怪话'}];
    var activeStyles = state.styles || ['casual'];
    html.push('<div class="card"><div class="card-header"><span class="icon">💬</span> 普通弹幕</div>');
    var danmuMode = state.danmuMode !== false; // default true
    html.push('<div class="row"><label>启用</label><select id="danmuMode"><option value="true"'+(danmuMode?' selected':'')+'>开启</option><option value="false"'+(danmuMode===false?' selected':'')+'>关闭</option></select></div>');
    html.push('<div class="style-chips" id="styleChips">');
    STYLES.forEach(function(st){
      var on = activeStyles.indexOf(st.id) >= 0 ? ' on' : '';
      html.push('<span class="style-chip'+on+'" data-style="'+st.id+'" style="cursor:pointer">'+st.n+'</span>');
    });
    html.push('</div>');
    
    // 间隔与条数（融入同一卡片）
    var ivMode = state.intervalMode || 'fixed';
    var ivSec = state.intervalSec || 30;
    html.push('<div class="row"><label>生成间隔</label><select id="intervalMode"><option value="fixed"'+(ivMode==='fixed'?' selected':'')+'>固定</option><option value="random"'+(ivMode==='random'?' selected':'')+'>随机</option></select>');
    html.push('<div id="fixedFields"'+(ivMode==='fixed'?'':' style="display:none"')+' style="display:inline-flex;align-items:center;gap:4px;margin-left:auto"><input type="number" id="intervalSec" min="5" max="600" value="'+ivSec+'" style="width:72px"><span style="font-size:12px">秒</span></div>');
    html.push('<div id="randomFields"'+(ivMode==='random'?'':' style="display:none"')+' style="display:inline-flex;align-items:center;gap:4px;margin-left:auto"><input type="number" id="intervalMin" min="5" max="300" value="'+(state.intervalMin||15)+'" style="width:72px"><span style="font-size:12px">~</span><input type="number" id="intervalMax" min="5" max="600" value="'+(state.intervalMax||60)+'" style="width:72px"><span style="font-size:12px">秒</span></div>');
    html.push('</div>');
    
    // 外观
    var danmuColors = state.danmuColors || ['#FFFFFF','#FF6B6B','#51CF66','#339AF0','#FCC419','#CC5DE8'];
    var ALL_COLORS = ['#FFFFFF','#FF6B6B','#51CF66','#339AF0','#FCC419','#CC5DE8','#FF8787','#74C0FC','#FFB8B8','#96F2D7','#FFA94D','#DA77F2','#63E6BE','#A9E34B'];
    var rainbowMode = state.rainbowMode || false;
    html.push('<div class="card"><div class="card-header"><span class="icon">🎨</span> 外观</div>');
    html.push('<div class="row"><label>字号</label><input type="range" id="fontSize" min="12" max="60" value="'+(state.fontSize||30)+'"><span class="val" id="valFontSize">'+(state.fontSize||30)+'</span></div>');
    html.push('<div class="row"><label>字体</label><select id="fontFamily"><option value="Microsoft YaHei"'+(state.fontFamily==='Microsoft YaHei'?' selected':'')+'>微软雅黑</option><option value="SimHei"'+(state.fontFamily==='SimHei'?' selected':'')+'>黑体</option><option value="STKaiti"'+(state.fontFamily==='STKaiti'?' selected':'')+'>楷体</option><option value="system-ui"'+(state.fontFamily==='system-ui'?' selected':'')+'>系统</option></select></div>');
    html.push('<div class="row"><label>不透明度</label><input type="range" id="opacity" min="30" max="100" value="'+(Math.round(opt(state.opacity,0.85)*100))+'"><span class="val" id="valOpacity">'+Math.round(opt(state.opacity,0.85)*100)+'%</span></div>');
    html.push('<div class="row"><label>阴影</label><select id="shadowMode"><option value="outline"'+(state.shadowMode==='outline'?' selected':'')+'>描边</option><option value="drop"'+(state.shadowMode==='drop'?' selected':'')+'>柔影</option></select></div>');
    html.push('<div class="row"><label>颜色</label><div class="palette" id="paletteColors">');
    ALL_COLORS.forEach(function(c){
      var sel = danmuColors.indexOf(c) >= 0 ? ' sel' : '';
      html.push('<span class="swatch'+sel+'" style="background:'+c+';cursor:pointer" data-col="'+c+'"></span>');
    });
    var rbSel = danmuColors.indexOf('__rainbow__') >= 0 ? ' sel' : '';
    html.push('<span class="swatch rainbow-swatch'+rbSel+'" style="background:linear-gradient(135deg,#FF6B6B,#FCC419,#51CF66,#339AF0,#CC5DE8);cursor:pointer" data-col="__rainbow__" title="多彩弹幕">🌈</span>');
    html.push('</div></div>');
    var density = state.density != null ? state.density : 50;
    var speedPct = state.speedPct != null ? state.speedPct : 30;
    var areaMode = state.areaMode || 'top_third';
    html.push('<div class="row"><label>显示密度</label><input type="range" id="density" min="0" max="100" value="'+density+'"><span class="val" id="valDensity">'+density+'%</span></div>');
    html.push('<div class="row" style="flex-wrap:wrap;margin-top:-4px"><span style="font-size:11px;color:var(--text-secondary)">少 ── 弹幕在区域里的密集程度 ── 多</span></div>');
    html.push('<div class="row"><label>滚动速度</label><input type="range" id="speedPct" min="0" max="100" value="'+speedPct+'"><span class="val" id="valSpeedPct">'+speedPct+'%</span></div>');
    html.push('<div class="row" style="flex-wrap:wrap;margin-top:-4px"><span style="font-size:11px;color:var(--text-secondary)">慢 ── 弹幕划过屏幕的快慢 ── 快</span></div>');
    html.push('<div class="row"><label>显示区域</label></div>');
    html.push('<div class="style-chips" id="areaChips">');
    html.push('<span class="style-chip'+(areaMode==='top_third'?' on':'')+'" data-area="top_third">上 1/3</span>');
    html.push('<span class="style-chip'+(areaMode==='top_half'?' on':'')+'" data-area="top_half">上半屏</span>');
    html.push('<span class="style-chip'+(areaMode==='full'?' on':'')+'" data-area="full">全屏</span>');
    html.push('</div>');
    
    // 自定义称呼（融入普通弹幕卡底部）
    var nicknames = state.nicknames || [];
    var nicknameText = nicknames.join('\n');
    html.push('<div class="field" style="margin-top:10px;padding-top:10px;border-top:1px solid var(--border)"><label>🏷️ 弹幕称呼</label><textarea id="nicknames" rows="3" style="width:100%;padding:6px 8px;border-radius:6px;border:1px solid var(--border);background:var(--bg);color:var(--text);font-size:13px;outline:none;resize:vertical">'+escHtml(nicknameText)+'</textarea></div>');
    html.push('<div class="row" style="flex-wrap:wrap"><span style="font-size:11px;color:var(--text-secondary)">每行一个，弹幕会随机选用。留空则使用Hana的用户名</span></div>');
    html.push('</div>');
    
    // 空闲自动暂停
    var idleAutoPause = state.idleAutoPause !== false;
    var idleThreshold = state.idleThreshold || 600;
    var IDLE_OPTIONS = [
      {v:'300', l:'5 分钟'},
      {v:'600', l:'10 分钟'},
      {v:'900', l:'15 分钟'},
      {v:'1800', l:'30 分钟'},
      {v:'3600', l:'60 分钟'},
    ];
    html.push('<div class="card"><div class="card-header"><span class="icon">💤</span> 空闲暂停（省 token）</div>');
    html.push('<div class="row"><label>启用</label><select id="idleAutoPause"><option value="true"'+(idleAutoPause?' selected':'')+'>开启</option><option value="false"'+(idleAutoPause===false?' selected':'')+'>关闭</option></select></div>');
    html.push('<div class="row"><label>超时时间</label><select id="idleThreshold">');
    IDLE_OPTIONS.forEach(function(o){
      html.push('<option value="'+o.v+'"'+(String(idleThreshold)===o.v?' selected':'')+'>'+o.l+'</option>');
    });
    html.push('</select></div>');
    html.push('<div class="row" style="flex-wrap:wrap"><span style="font-size:11px;color:var(--text-secondary)">离开电脑超过设定时间后自动暂停弹幕，省 token。动一下鼠标或键盘恢复。</span></div>');
    html.push('</div>');
    
    // 按钮
    html.push('<button class="btn" id="btnSaveAll" style="margin-top:4px">💾 保存全部设置</button>');
    html.push('<div class="btn-row"><button class="btn-sm btn-outline" id="btnRestart">🔄 重启弹幕</button></div>');
    
    // 模型设置弹窗（右上角 ⚙️ 触发）
    var visOpts = [{v:'custom',l:'✏️ 自定义 API'}];
    visionModels.forEach(function(p){
      (p.models||[]).forEach(function(m){ visOpts.push({v:'hana:'+p.providerId+'/'+m.id,l:(p.providerName||p.providerId)+' — '+m.id}); });
    });
    var curVis = state.visionSource === 'custom' ? 'custom' : (state.visionProviderId ? 'hana:'+state.visionProviderId+'/'+(state.visionModelId||'') : (visOpts.length>1?visOpts[1].v:''));
    var dmOpts = [{v:'same',l:'🔗 与截图模型相同'},{v:'custom',l:'✏️ 自定义 API'}];
    allModels.forEach(function(p){
      (p.models||[]).forEach(function(m){ dmOpts.push({v:'hana:'+p.providerId+'/'+m.id,l:(p.providerName||p.providerId)+' — '+m.id}); });
    });
    var curDm = state.danmuSource === 'custom' ? 'custom' : (state.danmuSource==='hana'&&state.danmuProviderId?'hana:'+state.danmuProviderId+'/'+(state.danmuModelId||''):'same');
    html.push('<div class="modal-overlay" id="settingsModal">');
    html.push('  <div class="modal">');
    html.push('    <h3>⚙️ 模型设置 <button class="modal-close" id="btnCloseSettings">✕</button></h3>');
    html.push('    <div class="card"><div class="card-header"><span class="icon">📷</span> 截图模型</div>');
    html.push('    <div class="row"><label>模型</label><select id="visionSel">'+visOpts.map(function(o){return '<option value="'+escAttr(o.v)+'"'+(o.v===curVis?' selected':'')+'>'+escHtml(o.l)+'</option>';}).join('')+'</select></div>');
    html.push('    <div id="visionCustomBlock" class="custom-block"'+(state.visionSource==='custom'?'':' style="display:none"')+'>');
    html.push('    <div class="field"><label>Base URL</label><input type="text" id="visionCustomUrl" placeholder="https://api.openai.com/v1" value="'+escAttr(state.visionCustomBaseUrl||'')+'"></div>');
    html.push('    <div class="field"><label>API Key</label><input type="password" id="visionCustomKey" placeholder="sk-..." value=""></div>');
    html.push('    <div class="field"><label>模型名</label><input type="text" id="visionCustomModel" placeholder="gpt-4o" value="'+escAttr(state.visionCustomModel||'')+'"></div>');
    html.push('    </div><button class="btn-sm btn-outline" id="btnTestVision" style="margin-top:6px">🔍 测试连接</button></div>');
    html.push('    <div class="card"><div class="card-header"><span class="icon">✏️</span> 弹幕文案模型</div>');
    html.push('    <div class="row"><label>模型</label><select id="danmuSel">'+dmOpts.map(function(o){return '<option value="'+escAttr(o.v)+'"'+(o.v===curDm?' selected':'')+'>'+escHtml(o.l)+'</option>';}).join('')+'</select></div>');
    html.push('    <div style="font-size:11px;color:var(--text-secondary);margin:6px 0 8px;line-height:1.4">💡 建议配置单独的文案模型，与截图模型分开效果更好</div>');
    html.push('    <div id="danmuCustomBlock" class="custom-block"'+(state.danmuSource==='custom'?'':' style="display:none"')+'>');
    html.push('    <div class="field"><label>Base URL</label><input type="text" id="danmuCustomUrl" placeholder="https://api.openai.com/v1" value="'+escAttr(state.danmuCustomBaseUrl||'')+'"></div>');
    html.push('    <div class="field"><label>API Key</label><input type="password" id="danmuCustomKey" placeholder="sk-..." value=""></div>');
    html.push('    <div class="field"><label>模型名</label><input type="text" id="danmuCustomModel" placeholder="gpt-4o" value="'+escAttr(state.danmuCustomModel||'')+'"></div>');
    html.push('    </div><button class="btn-sm btn-outline" id="btnTestDanmu" style="margin-top:6px">🔍 测试连接</button></div>');
    html.push('    <div class="btn-row" style="margin-top:14px">');
    html.push('      <button class="btn-sm btn-outline" id="btnSaveModalClose">✕ 取消</button>');
    html.push('      <button class="btn-sm" id="btnSaveModal" style="background:var(--accent);color:#fff;border:none;border-radius:6px;padding:6px 16px;font-size:12px;cursor:pointer;font-weight:500">💾 保存设置</button>');
    html.push('    </div>');
    // 检查更新
    html.push('    <div style="margin-top:12px;padding-top:10px;border-top:1px solid var(--border);display:flex;justify-content:space-between;align-items:center">');
    html.push('      <span style="font-size:11px;color:var(--text-secondary)">v' + PLUGIN_VERSION + '</span>');
    html.push('      <button class="btn-sm btn-outline" id="btnCheckUpdate" style="font-size:11px">🔍 检查更新</button>');
    html.push('    </div>');
    html.push('    <div id="updateStatus" style="display:none;margin-top:8px;padding:8px 10px;border-radius:6px;font-size:11px;line-height:1.5;word-break:break-all"></div>');
    html.push('  </div>');
    html.push('</div>');
    
    // 构建 buddy 初始化数据
    var buddyInitData = { buddies: buddies, selectedBuddies: selectedBuddies, buddyBoard: buddyBoard, pluginBase: pluginBase, token: token };
    
    // 完整 HTML
    var fullHtml = '<!DOCTYPE html>\n<html lang="zh-CN">\n<head>\n<meta charset="UTF-8">\n<meta name="viewport" content="width=device-width,initial-scale=1.0">\n<title>在干嘛 · 设置</title>\n<style>' + css.join('') + '</style>\n</head>\n<body>\n<div id="app">' + html.join('\n') + '</div>\n<script>window.__ZAIGANMA_TOKEN__=' + JSON.stringify(token) + ';</script>\n<script>window.__BUDDY_INIT__=' + JSON.stringify(buddyInitData) + ';</script>\n<script>' + appJs + '</script>\n</body>\n</html>';

    return c.html(fullHtml);
  });

  // ── 提供前端 JS（保留外部引用兼容） ──
  app.get('/api/app.js', async (c) => {
    try {
      const jsPath = join(__dirname, '../public/app.js');
      const js = readFileSync(jsPath, 'utf-8');
      return new Response(js, {
        status: 200,
        headers: { 'Content-Type': 'application/javascript', 'Cache-Control': 'no-store' },
      });
    } catch (e) {
      return new Response('console.error("在干嘛 app.js 未找到")', {
        status: 200,
        headers: { 'Content-Type': 'application/javascript' },
      });
    }
  });

  // ── 状态 ──
  app.get('/api/status', async (c) => {
    const state = getState();
    const deps = await checkDeps();
    return json({ ...state, depsOk: deps.ok, depsMissing: deps.missing || '' });
  });

  // ── 初始化数据（前端加载） ──
  app.get('/api/init', async (c) => {
    ctx.log?.info?.('[zaiganma] init 被调用');
    // 打开页面时启动小程序（如果尚未启动）
    if (!getState().running) {
      try {
        startApp();
      } catch (e) {
        ctx.log?.error?.('[zaiganma] init 启动异常:', e.message);
      }
    }
    try {
    const state = getState();
    const visionModels = getAvailableVisionModels();
    const allModels = getAllModels();

    // 尝试从小程序读取当前状态
    let appStatus = {};
    try {
      const resp = await appFetch('/status');
      const data = await resp.json();
      appStatus = data;
      ctx.log?.info?.('[zaiganma] appStatus:', JSON.stringify(data));
    } catch (e) {
      ctx.log?.info?.('[zaiganma] 小程序状态获取失败:', e.message);
    }

    return json({
      ...state,
      visionModels,
      allModels,
      appStatus,
    });
    } catch (e) {
      ctx.log?.error?.('[zaiganma] init 失败:', e.message);
      return json({ error: e.message }, 500);
    }
  });

  // ── 保存配置 ──
  app.post('/api/save-config', async (c) => {
    try {
      const body = await c.req.json();
      saveCfg(body);
      // 尝试同步到运行中的弹幕小程序
      const syncOk = await syncConfigToApp();
      if (syncOk) {
        return json({ ok: true, message: '配置已保存并生效' });
      } else {
        return json({ ok: true, message: '配置已保存，但弹幕小程序未运行，重启后生效' });
      }
    } catch (e) {
      return json({ ok: false, error: e.message }, 500);
    }
  });

  // ── 模型列表 ──
  app.get('/api/models', async (c) => {
    return json({
      vision: getAvailableVisionModels(),
      all: getAllModels(),
    });
  });

  // ── 测试截图模型连接 ──
  app.post('/api/test-vision', async (c) => {
    try {
      const { providerId, modelId, customBaseUrl, customApiKey, customModel } = await c.req.json();

      let apiBase, apiKey, model;
      if (providerId) {
        // Hana 模型
        const cfg = getProviderApiConfig(providerId);
        apiBase = cfg.baseUrl;
        apiKey = cfg.apiKey;
        model = modelId;
      } else {
        // 自定义
        apiBase = customBaseUrl;
        apiKey = customApiKey;
        model = customModel;
      }

      if (!apiKey) {
        return json({ ok: false, error: '未配置 API Key' });
      }

      // 发一个最小测试请求
      const resp = await fetch(`${apiBase.replace(/\/+$/, '')}/chat/completions`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${apiKey}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          model,
          messages: [{ role: 'user', content: 'hi' }],
          max_tokens: 1,
        }),
        signal: AbortSignal.timeout(15000),
      });

      if (resp.ok) {
        return json({ ok: true, message: '连接正常' });
      } else {
        const text = await resp.text().catch(() => '');
        return json({ ok: false, error: `HTTP ${resp.status}: ${text.substring(0, 200)}` });
      }
    } catch (e) {
      return json({ ok: false, error: e.message });
    }
  });

  // ── 测试文案模型连接 ──
  app.post('/api/test-danmu', async (c) => {
    try {
      const { providerId, modelId, customBaseUrl, customApiKey, customModel } = await c.req.json();

      let apiBase, apiKey, model;
      if (providerId) {
        const cfg = getProviderApiConfig(providerId);
        apiBase = cfg.baseUrl;
        apiKey = cfg.apiKey;
        model = modelId;
      } else {
        apiBase = customBaseUrl;
        apiKey = customApiKey;
        model = customModel;
      }

      if (!apiKey) {
        return json({ ok: false, error: '未配置 API Key' });
      }

      const resp = await fetch(`${apiBase.replace(/\/+$/, '')}/chat/completions`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${apiKey}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          model,
          messages: [{ role: 'user', content: 'hi' }],
          max_tokens: 1,
        }),
        signal: AbortSignal.timeout(15000),
      });

      if (resp.ok) {
        return json({ ok: true, message: '连接正常' });
      } else {
        const text = await resp.text().catch(() => '');
        return json({ ok: false, error: `HTTP ${resp.status}: ${text.substring(0, 200)}` });
      }
    } catch (e) {
      return json({ ok: false, error: e.message });
    }
  });

  // ── 头像代理 ──
  app.get('/api/avatar/:agentId', (c) => {
    const agentId = c.req.param('agentId');
    const HANA_HOME = process.env.HANA_HOME || join(homedir(), '.hanako');
    const avatarPath = join(HANA_HOME, 'agents', agentId, 'avatars', 'agent.png');
    if (existsSync(avatarPath)) {
      const img = readFileSync(avatarPath);
      return new Response(img, { headers: { 'Content-Type': 'image/png', 'Cache-Control': 'max-age=3600' } });
    }
    return new Response('', { status: 404 });
  });

  // ── 检查更新 ──
  app.get('/api/check-update', async (c) => {
    try {
      const resp = await fetch('https://api.github.com/repos/moononnn/zaiganma/releases/latest', {
        headers: { 'Accept': 'application/vnd.github.v3+json', 'User-Agent': 'zaiganma-plugin' },
        signal: AbortSignal.timeout(8000),
      });
      if (!resp.ok) {
        return json({ error: true, repoUrl: 'https://github.com/moononnn/zaiganma' });
      }
      const data = await resp.json();
      const latestTag = data.tag_name || '';
      const latestVersion = latestTag.replace(/^v/, '');
      const currentVersion = PLUGIN_VERSION;
      const hasUpdate = latestVersion !== currentVersion;
      return json({
        hasUpdate,
        currentVersion,
        latestVersion: latestTag,
        releaseUrl: data.html_url || ('https://github.com/moononnn/zaiganma/releases/tag/' + latestTag),
        repoUrl: 'https://github.com/moononnn/zaiganma',
      });
    } catch (e) {
      return json({ error: true, repoUrl: 'https://github.com/moononnn/zaiganma' });
    }
  });

  // ── 重启小程序 ──
  app.post('/api/restart-app', async (c) => {
    stopApp();
    await new Promise(r => setTimeout(r, 800));
    startApp();
    return json({ ok: true, message: '小程序已重启' });
  });

  // ── 开关弹幕引擎 ──
  app.post('/api/toggle', async (c) => {
    try {
      // Python 小程序的 /toggle 在 do_GET 里处理
      const resp = await appFetch('/toggle');
      const data = await resp.json();
      return json(data);
    } catch (e) {
      return json({ ok: false, error: '无法连接小程序: ' + e.message });
    }
  });
}
