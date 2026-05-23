# Qt 窗口 Win32 API 免疫实测记录

> 2026-05-23 实测，desktop-control v3.3。

## 背景

微信桌面客户端是 Qt5 构建。Qt 使用自绘渲染，不入 Win32 GDI 体系。

## 实测操作

### 微信进程信息

```
PID=9464, hwnd=590614, title='微信', mem=254MB
IsWindow=True  ← Win32 认识这个句柄
```

### 尝试的操作（全部返回 True 但无效）

| 操作 | API | 返回值 | 实际效果 |
|------|-----|--------|---------|
| 显示窗口 | `ShowWindow(hwnd, 5)` | True | 窗口没有出现 |
| 强制置顶 | `SetForegroundWindow(hwnd)` | True | 终端仍在前面 |
| 鼠标点击 | `SetCursorPos(1398,267) + mouse_event` | True | 点击没生效 |
| FindWindow | `FindWindow("WeChatMainWndForPC")` | 0 | 找不到 |
| FindWindow | `FindWindow(null, "微信")` | 0 | 找不到 |

### 不免疫的操作

| 操作 | 方法 | 效果 |
|------|------|------|
| 截图 | bridge screenshot | ✅ 微信窗口正常渲染在截图中 |
| SOM标注 | vision_analyze | ✅ 19个元素正确识别 |
| **iLink消息** | send_message | ✅ 协议级发送，已验证 |

## 结论

Qt 窗口对 Win32 GUI 操作 API **免疫**——不是不完全免疫，是全部免疫。

**职责分界：**
- **SOM 视觉 → 读状态**（截图、标注、确认消息）
- **iLink 协议 → 写操作**（发送消息、推送通知）
- **不越界。Win32 mouse_event/SendKeys 对 Qt 不可靠，不用。**

## 适用场景

此结论适用于所有 Qt5/Qt6 桌面应用（微信、部分企业 IM、Qt 构建的工具软件）。Java Swing 和游戏引擎（Unity/Unreal）窗口可能有类似特征但未实测。
