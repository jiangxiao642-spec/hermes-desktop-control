# Desktop Control v3.5 — 接口架构

每个管线步骤定义为 Protocol（`interfaces.py`），具体实现在各模块中，运行时通过 `STRATEGY_REGISTRY` 动态解析。

## 设计原则

- 管线只依赖 Protocol，不依赖具体实现
- 所有时间操作通过 `TimeSource` 注入——测试时用假时钟
- 所有哈希操作通过 `HashEngine` 注入——可切换算法
- 观察者模式：`HealthMonitor` + `EnvDetector` 支持外部观察者注册
- 每个护盾可独立实例化，不强制通过 `RobustnessShield` 包装

## 管线合约（Capture → Annotate → CrossValidate → Decide → Execute → Verify → Record）

| 步骤 | Protocol | 现有实现 | 可替换 |
|------|----------|---------|--------|
| 截图 | `ImageCapture` | （外部，Hermes 工具） | 不同截图后端 |
| 标注 | `SOMAnnotator` | UIA SOM / `VisionSOMAnnotator` | 不同标注引擎 |
| 交叉验证 | `CrossValidator` | `VisionSOMCrossValidator` (`"label_overlap"`) | 不同匹配策略 |
| 操作执行 | `ElementOperator` | UIA Operator / Visual Operator | UIA / CDP / visual |
| 验证 | `Verifier` | 四层验证（UIA→pHash→OCR→vision） | 不同验证链 |
| 健康度 | `HealthMonitor` | `HealthMonitor` (`robustness.py`) | 自定义降级策略 |
| 时间盾 | `TimeGuard` | `TimeGuard` (`robustness.py`) | 自定义时间预算 |
| 熔断器 | `CircuitBreaker` | `CircuitBreaker` (`robustness.py`) | 自定义熔断策略 |
| 环境检测 | `EnvDetector` | `EnvDetector` (`robustness.py`) | 自定义变更检测 |
| 安全点 | `SafePoint` | `SafePointManager` (`robustness.py`) | 自定义恢复策略 |
| 哈希引擎 | `HashEngine` | `PHashEngine` (`"phash_with_fallback"`) | imagehash / 自定义 |
| SOM解析 | （策略） | `SOMResponseParser` (`"regex_dual_path"`) | 不同模型格式 |

## 策略注册表

```python
from scripts.interfaces import resolve_strategy

validator = resolve_strategy("cross_validator", "label_overlap", {"label_threshold": 0.7})
hasher = resolve_strategy("hash_engine", "phash_with_fallback")
```

## 各模块实现的接口

| 模块 | 实现接口 | 注册名 |
|------|---------|--------|
| `robustness.py` → `HealthMonitor` | `HealthMonitor` | —（直接实例化） |
| `robustness.py` → `TimeGuard` | `TimeGuard` | —（直接实例化） |
| `robustness.py` → `CircuitBreaker` | `CircuitBreaker` | —（直接实例化） |
| `robustness.py` → `EnvDetector` | `EnvDetector` | —（直接实例化） |
| `robustness.py` → `SafePointManager` | `SafePoint` | —（直接实例化） |
| `visual_som_anchor.py` → `VisionSOMCrossValidator` | `CrossValidator` | `"cross_validator/label_overlap"` |
| `visual_som_anchor.py` → `PHashEngine` | `HashEngine` | `"hash_engine/phash_with_fallback"` |
| `visual_som_anchor.py` → `SOMResponseParser` | —（独立策略） | `"som_parser/regex_dual_path"` |
