# Hermes Desktop Control v3.7

> Windows 桌面 GUI 控制 Skill — 五护盾 + 操作检查点回滚 + CC 感知层（som-scan/som-click）

**成熟度：** 🟡 实验性。UIA路径稳定；视觉路径依赖vision；Store应用激活有降级链。

## 三层架构

```
感知层（CC 三脚本）        → som-scan 扫屏 → som-click 点编号
鲁棒性层（陈一 v3.7）      → 五护盾 + 激活降级 + 粘贴验证 + 对话回复读取
执行层（Windows Bridge）   → mouse/keyboard/clipboard/PowerShell/UIA
```

## 文件结构

```
├── SKILL.md                          # 完整规范（操作流程/应用分类表/验证分层）
├── README.md
├── scripts/
│   ├── ps-run                        # CC: PowerShell UTF-8 桥接
│   ├── som-scan                      # CC: 截图 → vision 标注所有可交互元素
│   ├── som-click                     # CC: 按编号点击（左/右/双击/移动）
│   ├── mouse_action.py               # 鼠标操作封装
│   ├── window_mgr.py                 # 窗口管理
│   ├── crop_region.py                # 局部截图裁剪
│   ├── visual_som_anchor.py          # SOM 锚点引擎
│   ├── robustness.py                 # 五护盾实现
│   └── interfaces.py                 # 接口协议
└── references/                       # 30+ 参考文档
```

## 版本历史

| 版本 | 变更 |
|------|------|
| v3.7 | Store应用激活降级链 + 对话回复读取规则 + 粘贴验证三步 + CC三脚本 |
| v3.6 | 操作级检查点回滚 |
| v3.5 | 五护盾 + 接口解耦 |
| v1.3 | Bug修复（变量名 mouse_event） |

## 作者

陈一 + CC (Claude Code)  
联系：jiangxiao642@gmail.com

## 协议

MIT
