// 在干嘛 — 只做事件绑定，不构建 DOM（服务端渲染完整 HTML）
(function() {
  'use strict';

  // ─── 工具函数 ───
  function $(id) { return document.getElementById(id); }
  function $$(sel) { return [].slice.call(document.querySelectorAll(sel)); }

  function toast(msg, isErr) {
    var el = document.createElement('div');
    el.className = 'toast' + (isErr ? ' error' : '');
    el.textContent = msg;
    document.body.appendChild(el);
    requestAnimationFrame(function() { el.classList.add('show'); });
    setTimeout(function() { el.remove(); }, 2500);
  }

  function baseUrl() {
    var p = window.location.pathname;
    return p.replace(/\/page\/?$/, '').replace(/\/+$/, '') || '';
  }

  function authQuery() {
    var m = window.location.search.match(/[?&]token=([^&]+)/);
    return m ? '?token=' + encodeURIComponent(m[1]) : '';
  }
  var AUTH = authQuery();

  // ─── 保存后回显 UI（用刚提交的 body 数据更新页面控件） ───
  function reflectSavedUI(body) {
    // 滑块 + 数值标签
    function setRange(id, valId, val, suffix) {
      var el = $(id);
      if (el) { el.value = val; }
      var vl = $(valId);
      if (vl) { vl.textContent = val + (suffix || ''); }
    }
    if (body.fontSize != null) setRange('fontSize', 'valFontSize', body.fontSize);
    if (body.opacity != null) setRange('opacity', 'valOpacity', Math.round(body.opacity * 100), '%');
    if (body.density != null) setRange('density', 'valDensity', body.density, '%');
    if (body.speedPct != null) setRange('speedPct', 'valSpeedPct', body.speedPct, '%');

    // 普通输入框
    if (body.danmuMode != null && $('danmuMode')) $('danmuMode').value = body.danmuMode ? 'true' : 'false';
    if (body.fontFamily && $('fontFamily')) $('fontFamily').value = body.fontFamily;
    if (body.shadowMode && $('shadowMode')) $('shadowMode').value = body.shadowMode;
    if (body.rainbowMode != null && $('rainbowMode')) $('rainbowMode').value = body.rainbowMode ? 'true' : 'false';
    if (body.areaMode && $('areaChips')) {
      // 先全部清除，再设置选中的
      $$('.style-chip[data-area]').forEach(function(chip) {
        chip.classList.remove('on');
      });
      $$('.style-chip[data-area]').forEach(function(chip) {
        if (chip.getAttribute('data-area') === body.areaMode) {
          chip.classList.add('on');
        }
      });
    }
    if (body.idleAutoPause != null && $('idleAutoPause')) $('idleAutoPause').value = body.idleAutoPause ? 'true' : 'false';
    if (body.idleThreshold != null && $('idleThreshold')) $('idleThreshold').value = body.idleThreshold;
    if (body.nicknames && $('nicknames')) $('nicknames').value = (body.nicknames || []).filter(function(s){return s && s.trim();}).join('\n');
    if (body.buddyNicknames && $('buddyNicknames')) $('buddyNicknames').value = (body.buddyNicknames || []).filter(function(s){return s && s.trim();}).join('\n');

    // 间隔模式 select（含固定/随机字段显隐）
    if (body.intervalMode && $('intervalMode')) {
      $('intervalMode').value = body.intervalMode;
      var isRandom = body.intervalMode === 'random';
      if ($('fixedFields')) $('fixedFields').style.display = isRandom ? 'none' : '';
      if ($('randomFields')) $('randomFields').style.display = isRandom ? '' : 'none';
    }
    if (body.intervalSec != null && $('intervalSec')) $('intervalSec').value = body.intervalSec;
    if (body.intervalMin != null && $('intervalMin')) $('intervalMin').value = body.intervalMin;
    if (body.intervalMax != null && $('intervalMax')) $('intervalMax').value = body.intervalMax;

    // 颜色回显
    if (body.danmuColors) {
      $$('.swatch').forEach(function(s) {
        var col = s.getAttribute('data-col');
        s.classList.toggle('sel', body.danmuColors.indexOf(col) >= 0);
      });
    }

    // 模型选择器
    if (body.visionSource && $('visionSel')) {
      var visVal = body.visionSource === 'custom' ? 'custom' : 'hana:' + (body.visionProviderId || '') + '/' + (body.visionModelId || '');
      $('visionSel').value = visVal;
      if ($('visionCustomBlock')) $('visionCustomBlock').style.display = body.visionSource === 'custom' ? '' : 'none';
    }
    if (body.danmuSource && $('danmuSel')) {
      var dmVal = body.danmuSource === 'custom' ? 'custom' : (body.danmuSource === 'same' ? 'same' : 'hana:' + (body.danmuProviderId || '') + '/' + (body.danmuModelId || ''));
      $('danmuSel').value = dmVal;
      if ($('danmuCustomBlock')) $('danmuCustomBlock').style.display = body.danmuSource === 'custom' ? '' : 'none';
    }

    // 风格 chips
    if (body.styles && body.styles.length) {
      $$('.style-chip[data-style]').forEach(function(chip) {
        chip.classList.toggle('on', body.styles.indexOf(chip.getAttribute('data-style')) >= 0);
      });
    }

    // 弹幕伙伴
    if (body.buddyMode != null && $('buddyMode')) {
      $('buddyMode').value = body.buddyMode ? 'true' : 'false';
      if ($('buddyList')) $('buddyList').style.display = body.buddyMode ? '' : 'none';
    }
    if (body.selectedBuddies && $('buddyList')) {
      $$('.buddy-check').forEach(function(cb) {
        cb.checked = body.selectedBuddies.indexOf(cb.getAttribute('data-bid')) >= 0;
      });
    }
    if (body.buddyIntervalMode != null && $('buddyIntervalMode')) {
      $('buddyIntervalMode').value = body.buddyIntervalMode;
      var isRandom = body.buddyIntervalMode === 'random';
      if ($('buddyFixedFields')) $('buddyFixedFields').style.display = isRandom ? 'none' : '';
      if ($('buddyRandomFields')) $('buddyRandomFields').style.display = isRandom ? '' : 'none';
    }
    if (body.buddyInterval != null && $('buddyInterval')) $('buddyInterval').value = body.buddyInterval;
    if (body.buddyIntervalMin != null && $('buddyIntervalMin')) $('buddyIntervalMin').value = body.buddyIntervalMin;
    if (body.buddyIntervalMax != null && $('buddyIntervalMax')) $('buddyIntervalMax').value = body.buddyIntervalMax;
    if (body.buddyMemoryRatio != null && $('buddyMemoryRatio')) {
      $('buddyMemoryRatio').value = body.buddyMemoryRatio;
      if ($('valBuddyMem')) $('valBuddyMem').textContent = body.buddyMemoryRatio + '%';
    }
  }

  // ─── 绑定事件 ───
  function bindEvents(INIT) {
    // 间隔模式切换
    $('intervalMode').addEventListener('change', function() {
      var isRandom = this.value === 'random';
      if ($('fixedFields')) $('fixedFields').style.display = isRandom ? 'none' : '';
      if ($('randomFields')) $('randomFields').style.display = isRandom ? '' : 'none';
    });

    // 滑块数值联动
    function bindRange(id, valId, suffix) {
      $(id).addEventListener('input', function() { $(valId).textContent = this.value + (suffix || ''); });
    }
    bindRange('fontSize', 'valFontSize', '');
    bindRange('opacity', 'valOpacity', '%');
    bindRange('density', 'valDensity', '%');
    bindRange('speedPct', 'valSpeedPct', '%');
    bindRange('buddyMemoryRatio', 'valBuddyMem', '%');



    // 弹幕伙伴模式切换
    $('buddyMode').addEventListener('change', function() {
      var isOn = this.value === 'true';
      if ($('buddyList')) $('buddyList').style.display = isOn ? '' : 'none';
      if ($('buddyMemFields')) $('buddyMemFields').style.display = isOn ? '' : 'none';
      if ($('buddyNickField')) $('buddyNickField').style.display = isOn ? '' : 'none';
      if ($('buddyNickHint')) $('buddyNickHint').style.display = isOn ? '' : 'none';
    });

    // 伙伴展板事件由 bindBuddyEvents 处理（动态DOM渲染后绑定）

    // 伙伴弹幕间隔模式切换
    $('buddyIntervalMode').addEventListener('change', function() {
      var isRandom = this.value === 'random';
      $('buddyFixedFields').style.display = isRandom ? 'none' : '';
      $('buddyRandomFields').style.display = isRandom ? '' : 'none';
    });

    // 截图模型选择 → 自定义块切换
    $('visionSel').addEventListener('change', function() {
      $('visionCustomBlock').style.display = this.value === 'custom' ? '' : 'none';
    });

    // 弹幕文案模型选择 → 自定义块切换
    $('danmuSel').addEventListener('change', function() {
      $('danmuCustomBlock').style.display = this.value === 'custom' ? '' : 'none';
    });

    // 风格 chips 点击切换
    $$('.style-chip').forEach(function(chip) {
      chip.addEventListener('click', function() {
        this.classList.toggle('on');
      });
    });

    // 区域 chips 点击切换（互斥单选）
    $$('.style-chip[data-area]').forEach(function(chip) {
      chip.addEventListener('click', function() {
        $$('.style-chip[data-area]').forEach(function(c) { c.classList.remove('on'); });
        this.classList.add('on');
      });
    });

    // 调色板色块点击切换
    $$('.swatch').forEach(function(sw) {
      sw.addEventListener('click', function() {
        this.classList.toggle('sel');
      });
    });

    // 测试截图模型连接
    $('btnTestVision').addEventListener('click', async function() {
      var val = $('visionSel').value;
      this.textContent = '⏳ 测试中...';
      try {
        var body = {};
        if (val === 'custom') {
          body.customBaseUrl = $('visionCustomUrl').value.trim();
          body.customApiKey = $('visionCustomKey').value.trim();
          body.customModel = $('visionCustomModel').value.trim();
        } else if (val.startsWith('hana:')) {
          var parts = val.replace('hana:', '').split('/');
          body.providerId = parts[0];
          body.modelId = parts.slice(1).join('/');
        }
        var resp = await fetch(baseUrl() + '/api/test-vision' + AUTH, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        });
        var data = await resp.json();
        if (data.ok) toast('✅ 截图模型: ' + data.message);
        else toast('❌ ' + (data.error || '连接失败'), true);
      } catch(e) { toast('❌ 异常: ' + e.message, true); }
      this.textContent = '🔍 测试连接';
    });

    // 测试弹幕文案模型连接
    $('btnTestDanmu').addEventListener('click', async function() {
      var val = $('danmuSel').value;
      this.textContent = '⏳ 测试中...';
      try {
        var body = {};
        if (val === 'same') {
          toast('⚠ 请先选择具体模型再测试');
          this.textContent = '🔍 测试连接';
          return;
        } else if (val === 'custom') {
          body.customBaseUrl = $('danmuCustomUrl').value.trim();
          body.customApiKey = $('danmuCustomKey').value.trim();
          body.customModel = $('danmuCustomModel').value.trim();
        } else if (val.startsWith('hana:')) {
          var parts = val.replace('hana:', '').split('/');
          body.providerId = parts[0];
          body.modelId = parts.slice(1).join('/');
        }
        var resp = await fetch(baseUrl() + '/api/test-danmu' + AUTH, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        });
        var data = await resp.json();
        if (data.ok) toast('✅ 文案模型: ' + data.message);
        else toast('❌ ' + (data.error || '连接失败'), true);
      } catch(e) { toast('❌ 异常: ' + e.message, true); }
      this.textContent = '🔍 测试连接';
    });

    // 保存全部设置
    $('btnSaveAll').addEventListener('click', async function() {
      this.textContent = '⏳ 保存中...';
      try {
        var body = {};

        var visVal = $('visionSel').value;
        if (visVal === 'custom') {
          body.visionSource = 'custom';
          body.visionCustomBaseUrl = $('visionCustomUrl').value.trim();
          body.visionCustomApiKey = $('visionCustomKey').value.trim();
          body.visionCustomModel = $('visionCustomModel').value.trim();
        } else if (visVal.startsWith('hana:')) {
          body.visionSource = 'hana';
          var parts = visVal.replace('hana:', '').split('/');
          body.visionProviderId = parts[0];
          body.visionModelId = parts.slice(1).join('/');
        }

        var dmVal = $('danmuSel').value;
        if (dmVal === 'same') {
          body.danmuSource = 'same';
        } else if (dmVal === 'custom') {
          body.danmuSource = 'custom';
          body.danmuCustomBaseUrl = $('danmuCustomUrl').value.trim();
          body.danmuCustomApiKey = $('danmuCustomKey').value.trim();
          body.danmuCustomModel = $('danmuCustomModel').value.trim();
        } else if (dmVal.startsWith('hana:')) {
          body.danmuSource = 'hana';
          var dmParts = dmVal.replace('hana:', '').split('/');
          body.danmuProviderId = dmParts[0];
          body.danmuModelId = dmParts.slice(1).join('/');
        }

        var chips = $$('.style-chip[data-style].on');
        body.styles = chips.map(function(c) { return c.getAttribute('data-style'); });

        var ivVal = $('intervalMode').value;
        if (ivVal === 'random') {
          body.intervalMode = 'random';
          body.intervalMin = parseInt($('intervalMin').value) || 15;
          body.intervalMax = parseInt($('intervalMax').value) || 60;
        } else {
          body.intervalMode = 'fixed';
          body.intervalSec = parseInt($('intervalSec').value) || 30;
        }
        body.danmuMode = $('danmuMode') ? $('danmuMode').value === 'true' : true;

        body.fontSize = parseInt($('fontSize').value) || 30;
        body.fontFamily = $('fontFamily').value;
        body.opacity = parseInt($('opacity').value) / 100;
        body.shadowMode = $('shadowMode').value;
        var allSel = $$('.swatch.sel').map(function(s) { return s.getAttribute('data-col'); });
        body.danmuColors = allSel;
        body.rainbowMode = allSel.indexOf('__rainbow__') >= 0;
        body.density = parseInt($('density').value) || 50;
        body.speedPct = parseInt($('speedPct').value) || 30;
        // 区域选择（从选中的 chip 读取）
        var areaChip = $$('.style-chip[data-area].on')[0];
        body.areaMode = areaChip ? areaChip.getAttribute('data-area') : 'top_third';

        // 弹幕伙伴
        body.buddyMode = $('buddyMode').value === 'true';
        body.selectedBuddies = $$('.buddy-check:checked').map(function(cb) { return cb.getAttribute('data-bid'); });
        body.buddyIntervalMode = $('buddyIntervalMode').value;
        body.buddyInterval = parseInt($('buddyInterval').value) || 90;
        body.buddyIntervalMin = parseInt($('buddyIntervalMin').value) || 60;
        body.buddyIntervalMax = parseInt($('buddyIntervalMax').value) || 180;
        body.buddyMemoryRatio = parseInt($('buddyMemoryRatio').value) || 30;
        // 空闲自动暂停
        body.idleAutoPause = $('idleAutoPause').value === 'true';
        body.idleThreshold = parseInt($('idleThreshold').value) || 600;
        // 自定义称呼
        var nicknamesVal = $('nicknames') ? $('nicknames').value.trim() : '';
        body.nicknames = nicknamesVal ? nicknamesVal.split('\n').map(function(s){return s.trim();}).filter(function(s){return s;}) : [];
        var buddyNicknamesVal = $('buddyNicknames') ? $('buddyNicknames').value.trim() : '';
        body.buddyNicknames = buddyNicknamesVal ? buddyNicknamesVal.split('\n').map(function(s){return s.trim();}).filter(function(s){return s;}) : [];
        // 收集伙伴颜色（从颜色球读取）
        body._buddyColors = {};
        $$('.color-ball').forEach(function(ball) {
          body._buddyColors[ball.getAttribute('data-bid')] = ball.getAttribute('data-col');
        });

        var resp = await fetch(baseUrl() + '/api/save-config' + AUTH, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        });
        var data = await resp.json();
        if (data.ok) {
          toast('✅ ' + (data.message || '设置已保存'));
          // 回显已保存的值到页面控件
          reflectSavedUI(body);
        } else {
          toast('❌ ' + (data.error || '保存失败'), true);
        }
      } catch(e) { toast('❌ 异常: ' + e.message, true); }
      this.textContent = '💾 保存全部设置';
    });

    // 重启弹幕
    $('btnRestart').addEventListener('click', async function() {
      this.textContent = '⏳ 重启中...';
      try {
        var resp = await fetch(baseUrl() + '/api/restart-app' + AUTH, { method: 'POST' });
        var data = await resp.json();
        if (data.ok) toast('🔄 弹幕已重启');
        else toast('❌ 重启失败', true);
      } catch(e) { toast('❌ 异常: ' + e.message, true); }
      this.textContent = '🔄 重启弹幕';
    });

    // 打开模型设置弹窗
    $('btnSettings').addEventListener('click', function() {
      var modal = $('settingsModal');
      if (modal) modal.classList.add('show');
    });

    // 关闭模型设置弹窗
    $('btnCloseSettings').addEventListener('click', function() {
      var modal = $('settingsModal');
      if (modal) modal.classList.remove('show');
    });

    // 点击遮罩层关闭弹窗
    $('settingsModal').addEventListener('click', function(e) {
      if (e.target === this) this.classList.remove('show');
    });

    // 弹窗取消按钮
    $('btnSaveModalClose').addEventListener('click', function() {
      var modal = $('settingsModal');
      if (modal) modal.classList.remove('show');
    });

    // 打开引导卡配置按钮
    var guideBtn = $('guideOpenSettings');
    if (guideBtn) {
      guideBtn.addEventListener('click', function() {
        var modal = $('settingsModal');
        if (modal) modal.classList.add('show');
      });
    }

    // 检查更新
    $('btnCheckUpdate').addEventListener('click', async function() {
      var statusEl = $('updateStatus');
      this.textContent = '⏳ 检查中...';
      if (statusEl) statusEl.style.display = 'none';
      try {
        var resp = await fetch(baseUrl() + '/api/check-update' + AUTH);
        var data = await resp.json();
        if (statusEl) {
          if (data.error) {
            statusEl.innerHTML = '⚠️ 无法连接到 GitHub<br>请复制链接手动访问：<br><a href="' + data.repoUrl + '" target="_blank" style="color:var(--accent);word-break:break-all">' + data.repoUrl + '</a>';
            statusEl.style.display = 'block';
            statusEl.style.background = '#FFF3E0';
            statusEl.style.border = '1px solid #FFE0B2';
            statusEl.style.color = '#E65100';
          } else if (data.hasUpdate) {
            statusEl.innerHTML = '🎉 有新版本 ' + data.latestVersion + '<br>当前 v' + data.currentVersion + '<br><a href="' + data.releaseUrl + '" target="_blank" style="color:var(--accent);word-break:break-all">' + data.releaseUrl + '</a>';
            statusEl.style.display = 'block';
            statusEl.style.background = '#E8F5E9';
            statusEl.style.border = '1px solid #C8E6C9';
            statusEl.style.color = '#2E7D32';
          } else {
            statusEl.innerHTML = '✅ 已是最新版本 v' + data.currentVersion;
            statusEl.style.display = 'block';
            statusEl.style.background = '#E8F5E9';
            statusEl.style.border = '1px solid #C8E6C9';
            statusEl.style.color = '#2E7D32';
          }
        }
      } catch(e) {
        if (statusEl) {
          statusEl.innerHTML = '⚠️ 检查失败，请复制链接手动访问：<br><a href="https://github.com/moononnn/zaiganma" target="_blank" style="color:var(--accent);word-break:break-all">https://github.com/moononnn/zaiganma</a>';
          statusEl.style.display = 'block';
          statusEl.style.background = '#FFF3E0';
          statusEl.style.border = '1px solid #FFE0B2';
          statusEl.style.color = '#E65100';
        }
      }
      this.textContent = '🔍 检查更新';
    });

    // 弹窗保存设置
    $('btnSaveModal').addEventListener('click', async function() {
      var body = {};
      var visVal = $('visionSel').value;
      if (visVal === 'custom') {
        body.visionSource = 'custom';
        body.visionCustomBaseUrl = $('visionCustomUrl').value.trim();
        body.visionCustomApiKey = $('visionCustomKey').value.trim();
        body.visionCustomModel = $('visionCustomModel').value.trim();
      } else if (visVal.startsWith('hana:')) {
        body.visionSource = 'hana';
        var parts = visVal.replace('hana:', '').split('/');
        body.visionProviderId = parts[0];
        body.visionModelId = parts.slice(1).join('/');
      }
      var dmVal = $('danmuSel').value;
      if (dmVal === 'same') {
        body.danmuSource = 'same';
      } else if (dmVal === 'custom') {
        body.danmuSource = 'custom';
        body.danmuCustomBaseUrl = $('danmuCustomUrl').value.trim();
        body.danmuCustomApiKey = $('danmuCustomKey').value.trim();
        body.danmuCustomModel = $('danmuCustomModel').value.trim();
      } else if (dmVal.startsWith('hana:')) {
        body.danmuSource = 'hana';
        var dmParts = dmVal.replace('hana:', '').split('/');
        body.danmuProviderId = dmParts[0];
        body.danmuModelId = dmParts.slice(1).join('/');
      }
      this.textContent = '⏳ 保存中...';
      try {
        var resp = await fetch(baseUrl() + '/api/save-config' + AUTH, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        });
        var data = await resp.json();
        if (data.ok) {
          toast('✅ 模型设置已保存');
          var modal = $('settingsModal');
          if (modal) modal.classList.remove('show');
        } else {
          toast('❌ ' + (data.error || '保存失败'), true);
        }
      } catch(e) { toast('❌ 异常: ' + e.message, true); }
      this.textContent = '💾 保存设置';
    });

    // 开关弹幕引擎
    $('btnToggle').addEventListener('click', async function() {
      var dot = $('dot');
      var st = $('statusText');
      var tglDot = $('tglDot');
      var tglLabel = $('tglLabel');
      this.disabled = true;
      try {
        var resp = await fetch(baseUrl() + '/api/toggle' + AUTH, { method: 'POST' });
        var data = await resp.json();
        if (data.ok) {
          var nowRunning = data.running;
          dot.className = 'dot ' + (nowRunning ? 'on' : 'off');
          st.textContent = nowRunning ? '运行中' : '暂停';
          tglDot.className = 'tgl-dot ' + (nowRunning ? 'on' : 'off');
          tglLabel.textContent = nowRunning ? '暂停' : '启动';
          this.setAttribute('data-running', nowRunning ? '1' : '0');
          toast(nowRunning ? '▶ 弹幕已启动' : '⏸ 弹幕已暂停');
        } else {
          toast('❌ ' + (data.error || '操作失败'), true);
        }
      } catch(e) { toast('❌ 异常: ' + e.message, true); }
      this.disabled = false;
    });
  }

  // ── 渲染伙伴展板（优先调闲不住 API 获取数据） ──
  async function renderBuddyBoard(data) {
    var list = $('buddyList');
    if (!list || !data) return;
    
    // 尝试从闲不住 API 获取最新展板数据
    var wvPartners = null;
    try {
      var wvResp = await fetch('/api/plugins/work-visit/api/data' + AUTH, { signal: AbortSignal.timeout(3000) });
      if (wvResp.ok) {
        var wvData = await wvResp.json();
        wvPartners = wvData.partners || null;
      }
    } catch(e) {}
    
    var buddies = data.buddies || {};
    var board = data.buddyBoard || {};
    var selected = data.selectedBuddies || [];
    var CP_COLORS = ['#FF6B6B','#51CF66','#339AF0','#FCC419','#CC5DE8','#74C0FC','#FFA94D','#FFFFFF'];
    var bb = baseUrl();
    
    var html = '';
    for (var bid in buddies) {
      var b = buddies[bid];
      var bd = board[bid] || {};
      // 优先用闲不住 API 的数据（doing 状态、变量等）
      var wv = null;
      if (wvPartners) {
        for (var wi = 0; wi < wvPartners.length; wi++) {
          if (wvPartners[wi].id === bid) { wv = wvPartners[wi]; break; }
        }
      }
      var checked = selected.indexOf(bid) >= 0 ? ' checked' : '';
      var energy = wv ? (wv.variables?.energy ?? 80) : (bd.energy != null ? bd.energy : 80);
      var mood = wv ? (wv.variables?.mood ?? 60) : (bd.mood != null ? bd.mood : 60);
      var affection = wv ? (wv.variables?.affection ?? 0) : (bd.affection != null ? bd.affection : 0);
      var doing = wv ? (wv.doing || '') : (bd.narrative || '');
      var barColor = energy >= 60 ? '#4CAF50' : energy >= 30 ? '#FF9800' : '#f44336';
      var isRb = b.color === 'rainbow';
      var ballBg = isRb ? 'background:linear-gradient(135deg,#FF6B6B,#FCC419,#51CF66,#339AF0,#CC5DE8)' : 'background:' + (b.color || '#FFFFFF');
      var ballCls = 'color-ball' + (isRb ? ' rainbow-ball' : '');
      var initial = b.name.charAt(0);
      var frameCls = bd.frameClass || '';
      var bgCls = bd.bgClass || '';
      // 好感度爱心
      var hearts = ['\uD83E\uDD0D','\uD83D\uDC97','\uD83D\uDC96','\u2764\uFE0F'];
      var heartLabels = ['初识阶段','逐渐熟悉','关系亲近','亲密无间'];
      var hi = affection >= 81 ? 3 : affection >= 51 ? 2 : affection >= 21 ? 1 : 0;
      // 心情 emoji
      var moodEmojis = ['\uD83D\uDE29','\uD83D\uDE11','\uD83D\uDE0C','\uD83D\uDE04'];
      var moodLabels = ['心情很差','不太好','心情平稳','心情很好'];
      var mi = mood >= 76 ? 3 : mood >= 51 ? 2 : mood >= 26 ? 1 : 0;
      // 头像URL
      var avatarUrl = bb + '/api/avatar/' + bid + AUTH;
      
      html += '<div class="buddy-card' + bgCls + '">';
      html += '<div class="buddy-check-wrap"><input type="checkbox" class="buddy-check" data-bid="' + bid + '"' + checked + '></div>';
      if (bd.hasAvatar && bb) {
        html += '<div class="buddy-avatar-img' + frameCls + '"><img src="' + avatarUrl + '" alt="" onerror="this.style.display=\'none\';this.parentElement.className=\'buddy-avatar' + frameCls + '\';this.parentElement.style.background=\'' + (b.color || '#999') + '\';this.parentElement.textContent=\'' + initial + '\'"></div>';
      } else {
        html += '<div class="buddy-avatar' + frameCls + '" style="background:' + (b.color || '#999') + '">' + initial + '</div>';
      }
      html += '<div class="buddy-info">';
      html += '<div class="buddy-name">' + b.name + ' <span class="buddy-affection" title="' + heartLabels[hi] + '">' + hearts[hi] + '</span></div>';
      html += '<div class="buddy-doing" title="' + doing + '">' + doing.substring(0, 40) + (doing.length > 40 ? '…' : '') + '</div>';
      html += '<div class="buddy-vars">';
      html += '<div class="buddy-energy"><span style="font-size:11px;cursor:default" title="精力">\uD83D\uDD0B</span><div class="energy-bar-bg"><div class="energy-bar-fill" style="width:' + energy + '%;background:' + barColor + '"></div></div><span class="energy-num">' + energy + '</span></div>';
      html += '<span class="buddy-mood" title="' + moodLabels[mi] + '">' + moodEmojis[mi] + '</span>';
      html += '</div></div>';
      html += '<div class="buddy-right" style="position:relative;flex-direction:column;align-items:flex-end;gap:4px">';
      html += '<div style="display:flex;align-items:center;gap:3px">';
      html += '<span style="font-size:10px;color:var(--text-secondary);cursor:default">弹幕色</span>';
      html += '<span class="' + ballCls + '" data-bid="' + bid + '" data-col="' + (b.color || '#FFFFFF') + '" style="' + ballBg + '"></span>';
      html += '</div>';
      var isActive = wv ? !!wv.active : (doing && doing.indexOf('摸鱼') < 0 && doing.indexOf('偷吃') < 0 && doing.indexOf('发呆') < 0);
      html += '<span class="buddy-badge ' + (isActive ? 'on' : 'off') + '">' + (isActive ? '在线' : '摸鱼') + '</span>';
      html += '<div class="color-picker-popup" id="cp-' + bid + '">';
      for (var ci = 0; ci < CP_COLORS.length; ci++) {
        html += '<span class="cp-swatch" data-bid="' + bid + '" data-col="' + CP_COLORS[ci] + '" style="background:' + CP_COLORS[ci] + '"></span>';
      }
      html += '<span class="cp-swatch" data-bid="' + bid + '" data-col="rainbow" style="background:linear-gradient(135deg,#FF6B6B,#FCC419,#51CF66,#339AF0,#CC5DE8);display:flex;align-items:center;justify-content:center;font-size:10px">🌈</span>';
      html += '</div></div></div>';
    }
    list.innerHTML = html;
  }

  // ── 绑定伙伴展板事件（动态DOM需要重新绑定） ──
  function bindBuddyEvents() {
    $$('.color-ball').forEach(function(ball) {
      ball.addEventListener('click', function(e) {
        e.stopPropagation();
        var bid = this.getAttribute('data-bid');
        var popup = $('cp-' + bid);
        if (!popup) return;
        var isOpen = popup.classList.contains('show');
        $$('.color-picker-popup.show').forEach(function(p) { p.classList.remove('show'); });
        if (!isOpen) popup.classList.add('show');
      });
    });
    $$('.cp-swatch').forEach(function(sw) {
      sw.addEventListener('click', function(e) {
        e.stopPropagation();
        var bid = this.getAttribute('data-bid');
        var col = this.getAttribute('data-col');
        var ball = $$('.color-ball[data-bid="' + bid + '"]')[0];
        if (!ball) return;
        ball.setAttribute('data-col', col);
        if (col === 'rainbow') {
          ball.className = 'color-ball rainbow-ball';
        } else {
          ball.className = 'color-ball';
          ball.style.background = col;
        }
        var popup = $('cp-' + bid);
        if (popup) popup.classList.remove('show');
        var buddyCard = ball.closest('.buddy-card');
        var bName = buddyCard ? buddyCard.querySelector('.buddy-name')?.textContent : bid;
        toast('🎨 ' + (bName || '伙伴') + ' 颜色已更新');
      });
    });
    document.addEventListener('click', function() {
      $$('.color-picker-popup.show').forEach(function(p) { p.classList.remove('show'); });
    });
  }

  // ── 同步主题 ──
  async function syncTheme() {
    try {
      var r = await fetch('/plugins/theme.css?_t=' + Date.now(), { cache: 'no-store' });
      if (!r.ok) return;
      var css = await r.text();
      var m = css.match(/:root\s*\{([\s\S]*?)\}/);
      if (!m) return;
      var root = document.documentElement;
      function get(n) {
        var re = new RegExp('--' + n + '\\s*:\\s*([^;]+);');
        var mm = m[1].match(re);
        return mm ? mm[1].trim() : null;
      }
      var bg = get('bg'); if (bg) root.style.setProperty('--bg', bg);
      var card = get('bg-card'); if (card) root.style.setProperty('--card', card);
      var border = get('border'); if (border) root.style.setProperty('--border', border);
      var text = get('text'); if (text) root.style.setProperty('--text', text);
      var ts = get('text-muted'); if (ts) root.style.setProperty('--text-secondary', ts);
      var accent = get('accent'); if (accent) {
        root.style.setProperty('--accent', accent);
        root.style.setProperty('--accent-soft', accent + '14');
      }
    } catch(e) {}
  }

  // ── 启动 ──
  async function init() {
    syncTheme();
    // 渲染伙伴展板（数据来自服务端渲染的 __BUDDY_INIT__）
    if (window.__BUDDY_INIT__) {
      await renderBuddyBoard(window.__BUDDY_INIT__);
      bindBuddyEvents();
    }
    try {
      var resp = await fetch(baseUrl() + '/api/init' + AUTH, { signal: AbortSignal.timeout(5000) });
      if (!resp.ok) {
        document.body.innerHTML = '<div style="padding:20px;text-align:center;color:var(--danger)">加载失败: ' + resp.status + '</div>';
        return;
      }
      var INIT = await resp.json();
      // 绑定事件（服务端渲染的控件）
      bindEvents(INIT);
    } catch(e) {
      document.body.innerHTML = '<div style="padding:20px;text-align:center;color:var(--danger)">网络错误: ' + e.message + '</div>';
    }
  }

  // ── hana.ready 握手 ──
  window.parent?.postMessage({
    protocol: 'hana.plugin.ui',
    version: 1,
    kind: 'event',
    type: 'hana.ready',
  }, '*');

  init();
})();
