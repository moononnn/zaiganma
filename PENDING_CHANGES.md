# PENDING_CHANGES（发布间隔变更账本）

> 每次完成插件 bug 修复或新功能后记一笔。统一发布时：并入 CHANGELOG → 清空本账本（保留格式头）→ 写 release notes 时对照检查。

- 2026-08-05 | 修复 | 安全加固：自定义 API Key 加密落盘（XOR+base64，兼容旧明文，Node/Python 双端互通）
- 2026-08-05 | 修复 | 安全加固：avatar 端点加 agentId 白名单，堵住路径穿越
- 2026-08-05 | 其他 | 补充 MIT LICENSE
