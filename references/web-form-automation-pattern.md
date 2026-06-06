# Web 表单批量填写自动化模式

## 场景

工学云实习日报批量补填（2026-06-03）：25 天日报 × 4 字段 + 1 下拉选择 = 100+ 次 UIA 操作，Edge 浏览器。

## 标准化流程

```
每轮操作（~20秒/条）：

1. 开表单：UIA InvokePattern 点"新增日报"按钮（或物理鼠标 2260,310）
2. 等3秒加载
3. 点下拉箭头：物理鼠标 (1862, 481)，等2秒
4. 选计划：UIA 找 ListItem Name='2024级专...'，鼠标点击
5. SetValue 填字段：日期→标题→内容（三个 Edit，Y 坐标定位）
6. InvokePattern 点"确定"
7. 等2秒 → 回到步骤1
```

## 关键踩坑

### el-select 下拉
- 唯一盲区，必须物理鼠标。详见 `references/el-select-web-component-uia.md`
- 下拉箭头坐标 (1862, 481)，下拉选项出现在 Y≈534

### Edge 窗口漂移
- 小鹿操作时拖窗口到屏幕外（坐标 -21333, -21333）
- 每次操作前 `SetWindowPos(h, 0, 0, 0, 1400, 900, ...)` 拉回
- 用 `GetWindowRect` 检查位置

### UIA 树过期
- 表单弹窗是 Element UI dialog，UIA 树可能过期
- 重激活 `uia_activate` → 重新扫描 → 确认字段存在再操作

### SetValue vs 剪贴板
- SetValue 对 Edit 控件可靠（ValuePattern）
- 剪贴板+SendKeys 在非前台窗口无效
- 日期、标题、内容三个字段全部用 SetValue

### 批量操作的节奏
- 每次提交后等 2 秒再开新表单
- 太快会撞到后端限流或表单未关闭
- 提交失败时表单还在，先关旧表单再开新

## 实测数据

- 成功：约 70%（下拉出现 + 计划选中）
- 失败：约 30%（下拉未出现，99% 因为 Edge 被拖走）
- 连续运行 25 轮未中断时，成功率接近 100%

## 泛化适用场景

任何涉及 Element UI / Ant Design / 自绘下拉的 Web 表单 → 先判组件类型，再选操作路径：
- 原生 HTML select → UIA ExpandCollapse / SelectionItem
- Web 组件 el-select → 物理鼠标点箭头
- 未知 → 先截图 vision 识别 → 再决定

## 新增实例：社交平台发帖（HN / Reddit）

**⚠️ 反机器人拦截（2026-06-03 实战验证）：**

UIA 填表+提交在技术上完全可行——SetValue 填字段、Invoke 点按钮均正常返回。但 **HN 和 Reddit 的反机器人检测会静默吞掉自动化提交**：
- HN：提交后标题/正文/按钮全部正常响应，但帖子不出现——新号 + 自动化 = 触发 Show HN 过滤。手动复制粘贴则成功提交（但被"新号限制"弹回）
- Reddit：同样的 UIA 流程，填好标题和正文，Invoke "发帖"按钮——没有错误提示，但帖子未上线。可能原因：Flair 未选、反自动化检测
- **结论：社交平台发帖不要走 UIA 自动化。** 准备好文本 → clipboard → 用户手动粘贴发送。反机器人系统对真人操作友好

**HN Show HN 提交（2026-06-03）：**
- 导航到 `/submit` → UIA 激活（66 元素）→ 定位三个 Edit 字段（Y=186 title, Y=224 url, Y=262 text）
- url 留空即为文本帖 → SetValue 填 title + text → Invoke "提交"按钮
- 全 UIA 流程，无物理鼠标介入
- **结果：被静默吞掉。手动重新提交被"新号临时限制 Show HN"弹回**

**Reddit → r/SideProject 提交（2026-06-03）：**
- 导航到 `/r/SideProject/submit?type=TEXT` → UIA 激活（370+ 元素）
- 表单字段：标题（Y=514）、正文（Y=754）、发帖按钮（Y=929 X=1666）
- **踩坑：Flair 标签必须选。** "不适用于此社区"按钮（Y=627 X=693）展开 Flair 下拉，但下拉选项未出现在 UIA 树中
- 直接点"发帖"按钮提交——无错误提示但帖子未上线
- **结果：被静默吞掉。手动复制粘贴 r/SideProject 成功**
- 子版块选择：r/programming 规则明确禁止项目展示（第5条），r/SideProject 或 r/opensource 更合适
