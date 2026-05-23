# Qt 窗口 Win32 输入免疫 — 实测记录

> 2026-05-23 端到端验证。微信 (WeChat) 桌面客户端，Qt 框架。

## 测试方法

| 方法 | API | 结果 |
|------|-----|------|
| ShowWindow(5) | `user32.dll` | 返回 True，窗口未实际显示 |
| SetForegroundWindow | `user32.dll` | 返回 True，窗口未置顶 |
| mouse_event click | `user32.dll` | 点击虚空，Qt 不响应 |
| SendInput click | `user32.dll` | 点击虚空，Qt 不响应 |
| Win+T 任务栏导航 | keybd_event | 任务栏自动隐藏时无效 |
| Win+D 最小化全部 | keybd_event | 微信缩到任务栏，无法恢复 |
| Alt+Tab 切换器 | keybd_event | 切换器弹出但不选中微信 |
| FindWindow(类名) | `user32.dll` | WeChatMainWndForPC 未注册 |
| Get-Process MainWindowHandle | .NET | 返回有效句柄 590614，但 IsWindow=True 且 API 调用表面成功 |

## 最终可行方案

| 操作 | 可行 | 不可行 |
|------|------|--------|
| 读取界面状态 | SOM 视觉标注 ✅ | — |
| 发送消息 | iLink Bot 协议 ✅ | Win32 键鼠 ❌ |
| 点击元素 | — | 全部 Win32 API ❌ |
| 输入文字 | — | SendKeys/剪贴板 ❌ |
| 窗口切换 | 手动点击 ✅ | 编程切换 ❌ |

## 结论

职责分工：**SOM 负责看，iLink 负责动。** 不越界。
视觉只做状态读取和元素定位，消息操作走协议通道。
此边界写入 desktop-control 应用分类表和 Qt 铁律。
