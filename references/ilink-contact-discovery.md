# iLink 联系人发现与发送限制

2026-05-23 实战测试记录。

## 联系人发现

`send_message(action='list')` 返回的列表仅包含已建立会话（有 context_token）的联系人。

**context-tokens 文件位置：** `~/.hermes/weixin/accounts/<bot_id>@im.bot.context-tokens.json`

格式：`{"<user_id>@im.wechat": "<token_string>"}`

## 文件传输助手不可达

测试了三种ID格式，全部失败：

| 尝试 | 结果 |
|------|------|
| `weixin:filehelper` | ret=-3 unknown error |
| `weixin:file_helper` | Could not resolve |
| `weixin:filehelper@im.wechat` | Could not resolve |

**根因：** 文件传输助手是微信内置特殊账号，不在 bot 的 context-tokens 中。bot 必须先从文件传输助手聊天窗口收到过消息，才能建立令牌。

**绕过方案：** 让用户直接在文件传输助手聊天窗口里给 bot 发一条消息，之后 bot 即可通过 iLink 向该窗口发送。

## 限流

连续 3+ 次快速 `send_message` 触发 `ret=-2 rate limited`。冷却约 30s 后恢复。

## 微信多进程坑

```powershell
Get-Process -Name "Weixin"
```

可能返回多个进程（主进程 + 子进程/WebView2 helper），`MainWindowHandle` 变成 `Object[]` 数组，导致 Win32 P/Invoke 参数类型错误。正确做法：用 `window_list` MCP 工具或 UIA 树查找 `ClassName=WeChatMainWndForPC`。
