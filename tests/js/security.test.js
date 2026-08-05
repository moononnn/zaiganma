// 安全加固回归测试：agentId 白名单 + API Key 混淆存储
import { test } from 'node:test';
import assert from 'node:assert/strict';

test('isValidAgentId: 正常助手 ID 通过', async () => {
  const { isValidAgentId } = await import('../../routes/api.js?v=' + Date.now());
  assert.equal(isValidAgentId('hanako'), true);
  assert.equal(isValidAgentId('feiyue'), true);
  assert.equal(isValidAgentId('a-b_c1'), true);
});

test('isValidAgentId: 路径穿越/原型污染/脏输入被拒绝', async () => {
  const { isValidAgentId } = await import('../../routes/api.js?v=' + Date.now());
  assert.equal(isValidAgentId('../etc/passwd'), false);
  assert.equal(isValidAgentId('..'), false);
  assert.equal(isValidAgentId('__proto__'), false);
  assert.equal(isValidAgentId('constructor'), false);
  assert.equal(isValidAgentId('prototype'), false);
  assert.equal(isValidAgentId('a b'), false);
  assert.equal(isValidAgentId('中文'), false);
  assert.equal(isValidAgentId(''), false);
  assert.equal(isValidAgentId('a'.repeat(101)), false);
  assert.equal(isValidAgentId(null), false);
  assert.equal(isValidAgentId(123), false);
});

test('encryptKey/decryptKey: 往返一致且加密结果不泄露明文', async () => {
  const { encryptKey, decryptKey } = await import('../../index.js?v=' + Date.now());
  const key = 'sk-abcdef123456';
  const enc = encryptKey(key);
  assert.ok(enc.startsWith('enc:'), '加密结果应有 enc: 前缀');
  assert.ok(!enc.includes('sk-abcdef'), '加密结果不应包含明文片段');
  assert.equal(decryptKey(enc), key);
});

test('encryptKey/decryptKey: 空值与明文向后兼容', async () => {
  const { encryptKey, decryptKey } = await import('../../index.js?v=' + Date.now());
  assert.equal(encryptKey(''), '');
  assert.equal(encryptKey(null), '');
  assert.equal(decryptKey(''), '');
  assert.equal(decryptKey(null), '');
  // 旧版本明文 key 直接透传（迁移兼容）
  assert.equal(decryptKey('sk-plain-old'), 'sk-plain-old');
});
