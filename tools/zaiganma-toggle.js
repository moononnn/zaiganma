// 工具：开关弹幕

export const name = 'zaiganma_toggle';
export const description = '启动或停止弹幕浮层（自动截图分析画面并生成弹幕）';
export const parameters = {
  type: 'object',
  properties: {
    action: {
      type: 'string',
      enum: ['start', 'stop', 'restart'],
      description: 'start=启动, stop=停止, restart=重启',
    },
  },
  required: ['action'],
};

export async function execute({ action }, ctx) {
  const mod = await import('../index.js');
  const { getState, startApp, stopApp } = mod;

  let result;
  switch (action) {
    case 'start': {
      const state = getState();
      if (!state.running) {
        startApp();
      }
      result = { ok: true, action: 'started' };
      break;
    }
    case 'stop':
      stopApp();
      result = { ok: true, action: 'stopped' };
      break;
    case 'restart':
      stopApp();
      await new Promise(r => setTimeout(r, 800));
      startApp();
      result = { ok: true, action: 'restarted' };
      break;
    default:
      result = { ok: false, error: 'unknown action' };
  }

  return {
    content: [{ type: 'text', text: JSON.stringify(result) }],
  };
}
