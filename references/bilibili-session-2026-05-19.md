# B站头像上传实测（2026-05-19）

## 目标
用desktop-control四步循环操作B站网页——点击头像→进设置页→上传头像。

## 使用的技术路线

### 成功路线：键盘导航
```
1. start_app: msedge.exe → 打开 bilibili.com
2. window_mgr: Activate("哔哩哔哩") ✅
3. send_keys(^l) → 聚焦地址栏
4. clipboard_write("https://member.bilibili.com/platform/home") → ^v → {ENTER}
5. → 成功进入创作中心 ✅
6. 再导航: ^l → clipboard_write("https://account.bilibili.com/account/face") → ^v → {ENTER}
7. → 成功进入头像设置页 ✅
```

### 失败路线：鼠标点击（三次尝试全失败）
- 尝试1：(940,200) 点击头像 → 截图验证 → NO
- 尝试2：(1680,200) → 精确定位→(1748,200) → 超出屏幕宽度
- 尝试3：(776,629) 点击头像大图 → 截图验证 → NO

## 发现的问题

1. **mouse_action.py方法名bug** — `me`→`mouse_event`，运行时EntryPointNotFoundException
2. **vision坐标漂移** — 同一目标三次查询：940→1980→1680，差值±700px
3. **浏览器mouse_event不响应** — 即使坐标正确，原生Win32 mouse_event对JS渲染元素无效
4. **桌面右键被遮挡** — Edge窗口全屏时(900,900)落点在窗口内而非桌面

## 结论
操作浏览器 → 键盘路线。坐标点击 → 仅用于原生Windows控件。
