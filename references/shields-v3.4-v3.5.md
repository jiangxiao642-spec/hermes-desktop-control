# Desktop Control v3.4/v3.5 — 鲁棒性护盾详解

## 五护盾总览

| 护盾 | 模块 | 功能 |
|------|------|------|
| 健康度 | `HealthMonitor` | 全局 score 0-100，连续失败扣分 → 自动降级(NORMAL→DEGRADED→FALLBACK→STALLED)，连续成功恢复 |
| 时间盾 | `TimeGuard` | 单操作 30s 超时、会话 10min TTL、SOM缓存 5min 强制刷新 |
| 熔断器 | `CircuitBreaker` | 连续 3 次 vision 超时 → OPEN 阻断所有 vision 调用，60s 冷却后半开探测 |
| 环境检测 | `EnvDetector` | 截图尺寸/DPI/显示器数量变化 → 立即清 SOM 缓存，不依赖 pHash |
| 安全点 | `SafePointManager` | v3.5 新增。多步操作每步前记状态（pHash+窗口标识+SOM+焦点），失败回到上一个已知安全点，不撞墙 |

## 五护盾职责分工

| 护盾 | 类型 | 时机 | 做什么 |
|------|------|------|--------|
| 健康度 / 时间盾 / 熔断器 / 环境检测 | **预防性** | 操作前 | 检测异常，阻断危险操作 |
| 安全点 | **恢复性** | 操作失败后 | 回到上一个已知正常状态，换路径恢复 |

## 降级决策

```
health >= 80  → NORMAL   — 全能力，UIA+vision
health 50-79  → DEGRADED — UIA优先，视觉验证跳过
health 20-49  → FALLBACK — 仅 UIA，不用 vision
health < 20   → STALLED  — 通知用户手动接管
```

## 恢复决策表（失败原因 → 恢复动作）

| 失败表现 | 恢复动作 | 说明 |
|---------|---------|------|
| 弹窗/遮挡 | `close_popup` | 关弹窗，回安全点重试 |
| 焦点丢失 | `refocus_window` | 重新 SetForegroundWindow |
| 窗口消失 | `relaunch_app` | 重新打开目标应用 |
| 布局全变 | `refresh_som` | 刷新全屏 SOM 缓存 |
| 其他错误 | `retry_alternate_path` | 同一状态，换条路走 |
| 连续3次rollback失败 | `notify_user` | 通知用户手动接管 |

## SOM 交叉验证（v3.4）

UIA 可用时，vision SOM 标注的元素和 UIA 树做 intersection——两边都确认的标记 `cross_validated=True`。只有 vision 说的元素标记"待验证"，操作前多跑一轮裁剪确认再执行。

- `VisualSOMCache.cross_validate_uia(uia_elements)` — 逐元素匹对，支持类型等效（Edit≈TextInput）和标签模糊匹配
- `VisualSOMCache.get_unvalidated()` — 返回只有 vision 看到的元素（可能幻觉）
- `VisualSOMCache.get_high_confidence()` — 返回交叉验证通过的元素

## 韧性增强（visual_som_anchor.py v1.1+）

- `imagehash` 改为软依赖——未安装时自动降级为像素采样 hash
- `parse_som_response()` 严格解析失败时自动尝试宽松正则（含中文括号、无引号、坐标格式变化）
- `VisualSOMCache` 新增 `max_age` 和 `is_stale` ——时间过期和 pHash 过期双轨判断
- `compute_phash` / `phash_distance` 在 imagehash 不可用时用像素采样

## 护盾实现文件

- 接口协议: `scripts/interfaces.py` — 所有护盾的 Protocol 定义
- 健康度: `scripts/robustness.py` — `HealthMonitor` (implements `HealthMonitor` Protocol)
- 时间盾: `scripts/robustness.py` — `TimeGuard` (implements `TimeGuard` Protocol)
- 熔断器: `scripts/robustness.py` — `CircuitBreaker` (implements `CircuitBreaker` Protocol)
- 环境检测: `scripts/robustness.py` — `EnvDetector` (implements `EnvDetector` Protocol)
- 安全点: `scripts/robustness.py` — `SafePointManager` (implements `SafePoint` Protocol)
- 统一入口: `scripts/robustness.py` — `RobustnessShield`（五合一，向后兼容）
- 策略实现: `scripts/visual_som_anchor.py` — `VisionSOMCrossValidator`、`PHashEngine`、`SOMResponseParser`
