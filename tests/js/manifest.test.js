// 在干嘛 — manifest.json 一致性测试
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, existsSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, '..', '..');

const manifest = JSON.parse(readFileSync(join(ROOT, 'manifest.json'), 'utf-8'));

test('manifest：必填字段齐全', () => {
  assert.equal(manifest.manifestVersion, 1);
  assert.ok(manifest.id, 'id 不能为空');
  assert.ok(manifest.name, 'name 不能为空');
  assert.match(manifest.version, /^\d+\.\d+\.\d+$/, 'version 应为 x.y.z 格式');
  assert.ok(manifest.description, 'description 不能为空');
  assert.equal(manifest.trust, 'full-access');
  assert.ok(manifest.main, 'main 不能为空');
});

test('manifest：main 文件存在', () => {
  assert.ok(existsSync(join(ROOT, manifest.main)), `main 文件 ${manifest.main} 应存在`);
});

test('manifest：声明的 routes 文件都存在', () => {
  for (const r of manifest.contributes.routes || []) {
    assert.ok(existsSync(join(ROOT, r)), `route 文件 ${r} 应存在`);
  }
});

test('manifest：声明的 tools 文件都存在且带 name/execute', async () => {
  for (const t of manifest.contributes.tools || []) {
    const p = join(ROOT, t);
    assert.ok(existsSync(p), `tool 文件 ${t} 应存在`);
    const mod = await import(pathToFileURL(p).href);
    assert.ok(mod.name, `${t} 应有 name 导出`);
    assert.ok(mod.description, `${t} 应有 description 导出`);
    assert.equal(typeof mod.execute, 'function', `${t} 应有 execute 函数`);
  }
});

test('manifest：page 声明有效', () => {
  assert.ok(manifest.contributes.page, '应声明 page');
  assert.equal(manifest.contributes.page.title, '在干嘛');
  assert.ok(manifest.contributes.page.route.startsWith('/'), 'route 应以 / 开头');
});

test('manifest：版本号与 package.json 一致', () => {
  const pkg = JSON.parse(readFileSync(join(ROOT, 'package.json'), 'utf-8'));
  assert.equal(pkg.version, manifest.version, 'package.json 与 manifest 版本应一致');
});

test('manifest：python 小程序文件存在', () => {
  assert.ok(existsSync(join(ROOT, 'python', 'zaiganma_app.py')));
});
