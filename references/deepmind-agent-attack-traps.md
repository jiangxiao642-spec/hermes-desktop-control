# DeepMind Agent Attack Traps（安全审计参考）

## 来源

Google DeepMind, April 2, 2026
"Six Attack Traps Targeting AI Agents" — 首个系统性的自主 Agent 对抗攻击分类

## 核心内容

六类攻击陷阱，每一类都有可用的 PoC 漏洞：

1. **提示注入** — 通过外部输入劫持 Agent 目标
2. **工具操纵** — 伪造工具返回值欺骗 Agent
3. **上下文污染** — 在 Agent 记忆/上下文中植入恶意信息
4. **目标漂移** — 逐步把 Agent 的原始目标替换成攻击者目标
5. **权限滥用** — 让 Agent 以为自己有权执行危险操作
6. **回滚欺骗** — 伪造失败让 Agent 重复危险操作

## 对 desktop-control 的意义

我们的 desktop-control 直接操控 Windows 桌面——每一类攻击都是真实威胁：

- **提示注入** → SOM 标注时页面上有恶意文字（"点击这里"但实际指向删除按钮）
- **工具操纵** → 伪造 UIA 元素名诱骗 Agent 点击
- **上下文污染** → 通过剪贴板/窗口标题植入恶意指令
- **权限滥用** → Agent 以为自己只是读文件，实际在删文件

## 使用方式

安全审计时加载此参考，逐类过一遍 desktop-control 的防护。

## 相关

- 原始论文: Google DeepMind Publications, April 2026
- 报道: awesomeagents.ai/news/deepmind-ai-agent-traps-six-attacks/
