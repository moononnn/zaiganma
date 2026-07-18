// 工具：查看在干嘛调试信息

export const name = 'zaiganma_debug';
export const description = '查看在干嘛弹幕小程序的运行状态、配置、最近日志等调试信息';
export const parameters = {
  type: 'object',
  properties: {
    action: {
      type: 'string',
      enum: ['status', 'logs', 'full'],
      description: 'status=运行状态, logs=最近日志, full=全部信息',
    },
  },
  required: ['action'],
};

export async function execute({ action }, ctx) {
  try {
    const mod = await import('../index.js');
    const { getState, appFetch } = mod;
    const state = getState();

    const result = { ok: true, running: state.running, action };

    // 获取 Python 进程状态
    try {
      const statusResp = await appFetch('/status');
      const statusData = await statusResp.json();
      result.pythonStatus = statusData;
    } catch (e) {
      result.pythonError = e.message;
    }

    // 获取配置
    try {
      const cfgResp = await appFetch('/config');
      const cfgData = await cfgResp.json();
      if (cfgData.ok && cfgData.config) {
        // 隐藏敏感信息
        const sanitized = { ...cfgData.config };
        ['_visionApiKey', '_danmuApiKey', 'visionCustomApiKey', 'danmuCustomApiKey'].forEach(k => {
          if (sanitized[k]) sanitized[k] = '***';
        });
        result.config = sanitized;
      }
    } catch (e) {
      result.configError = e.message;
    }

    // 获取日志
    if (action === 'logs' || action === 'full') {
      try {
        const logsResp = await appFetch('/logs');
        const logsData = await logsResp.json();
        if (logsData.ok) {
          result.logs = logsData.logs;
        }
      } catch (e) {
        result.logsError = e.message;
      }
    }

    return {
      content: [{ type: 'text', text: JSON.stringify(result, null, 2) }],
    };
  } catch (e) {
    return {
      content: [{ type: 'text', text: JSON.stringify({ ok: false, error: e.message }) }],
    };
  }
}
