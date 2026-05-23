# Desktop Control v3.3/v3.4 — 视觉路径详解

## 核心模块

- `VisualSOMCache`：全屏SOM获取、缓存（pHash+时间双过期）、交叉验证、找元素
- `AnchorCropper`：从缓存SOM锚点裁剪目标区域
- `parse_som_response()`：解析vision模型的SOM标注文本（严格→宽松双路径）
- 实现文件: `scripts/visual_som_anchor.py`

## 全流程（v3.4 鲁棒性增强）

```
┌─ 环境检测：截图尺寸/DPI变了? → 清缓存 (v3.4)
│
├─ 首次：全屏SOM (JPEG 质量60, ~223KB, 2-3s)
│   screenshot → compress JPEG → vision_analyze → parse → VisualSOMCache
│   → compute pHash of window region
│   → cache.timestamp = now, cache.max_age = 300s
│
├─ 每次操作前：
│   ├─ 健康度检查 (v3.4):
│   │   ├─ health.can_operate()? → 继续
│   │   └─ STALLED? → 通知用户
│   ├─ 环境检测 (v3.4):
│   │   └─ env.capture(w, h, dpi) → changed? → 清SOM缓存
│   ├─ 时间盾 (v3.4):
│   │   ├─ time.start_operation() → 超时会话? → SessionExpired
│   │   ├─ time.is_som_cache_stale()? → 强制刷新
│   │   └─ time.check_timeout() → 超时? → OperationTimeout
│   ├─ 熔断器 (v3.4):
│   │   └─ breaker.allow_call()? → 阻断? → 降级非vision路径
│   ├─ 安全点 (v3.5):
│   │   └─ safepoint.checkpoint(phash, window_class, ...) → 记快照
│   ├─ 截全屏 → compute pHash → 与缓存对比
│   │   ├─ 汉明距离 <10 且 !cache.is_stale: 布局未变 → 从缓存找目标元素
│   │   └─ 汉明距离 ≥10 或 cache.is_stale: 刷新全屏SOM (2-3s)
│   │
│   ├─ 交叉验证 (v3.4):
│   │   └─ UIA 可用? → cache.cross_validate_uia(uia_elements)
│   │       → 高置信元素直接操作，未验证元素先裁剪确认
│   ├─ 锚点裁剪：AnchorCropper.crop_element(index) → 200×200 区域
│   ├─ 精准识别：裁剪区 → vision_analyze → "这个按钮现在是什么状态？"
│   ├─ 执行：clipboard_write + ^v 或 mouse_action click
│   └─ 验证：裁剪区 → vision_analyze → 对比预期
│       → 成功：health.record_success(), breaker.record_success()
│       → 失败：health.record_failure(), safepoint.rollback(), 降级retry
│
└─ 缓存生命周期：视觉会话期间有效。max_age过期/pHash变化/环境变更时刷新。
```

## SOM 标注引擎（UIA 路径）

实现: `~/.hermes/skills/uia-state-machine/scripts/uia_som.py`

- `generate_som_powershell_script(target_window_class, target_window_title, dpi_scale)` → 生成自包含 PowerShell 脚本
- 在 Windows 端运行 → 扫描全 UIA 树 → 给每个可交互控件编号 [1],[2],[3]...
- 返回 JSON: `{mode:"uia", elements:[{index,control_type,name,automation_id,bounds,...}]}`

## SOM 标注引擎（视觉路径兜底）

- 截图 → vision_analyze 标注可交互区域
- `parse_som_response()` 解析文本标注（严格→宽松双路径）
- 返回 SOMResult，但与 UIA 路径不同: 无 automation_id，confidence<1.0
