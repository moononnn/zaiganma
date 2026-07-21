// 工具：发弹幕

export const name = 'zaiganma_send';
export const description = '发一条弹幕到桌面浮层上滚动显示';
export const parameters = {
  type: 'object',
  properties: {
    text: { type: 'string', description: '弹幕内容，建议 20 字以内' },
  },
  required: ['text'],
};

export async function execute({ text }, ctx) {
  try {
    const mod = await import('../index.js');
    const { getState, appFetch } = mod;
    const state = getState();

    if (!state.running) {
      return {
        content: [{ type: 'text', text: JSON.stringify({ ok: false, error: '弹幕未启动' }) }],
      };
    }

    const resp = await appFetch('/send', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
    });
    const data = await resp.json();
    return {
      content: [{ type: 'text', text: JSON.stringify({ ok: data.ok, text }) }],
    };
  } catch (e) {
    return {
      content: [{ type: 'text', text: JSON.stringify({ ok: false, error: e.message }) }],
    };
  }
}
