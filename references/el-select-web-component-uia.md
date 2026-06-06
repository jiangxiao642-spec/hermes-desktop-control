# el-select (Element UI) UIA 操控研究

## 问题

Element UI 的 el-select 下拉选择器在 UIA 中暴露为一个**只读 Edit 控件**，没有任何原生控件模式可用。

## 已测试的方案（全部失败）

| 方案 | 结果 | 详情 |
|------|------|------|
| ExpandCollapsePattern | ❌ 不支持 | el-select 不是原生 ComboBox，无此模式 |
| LegacyIAccessiblePattern | ❌ 不支持 | 下拉箭头是纯 Text 控件，无 LegacyIAccessible |
| InvokePattern (箭头父元素) | ❌ 不触发 | Group 父元素有 InvokePattern 但 invoke 后不展开下拉 |
| ValuePattern.SetValue | ❌ 只读 | 框架拦截，返回"值为只读" |
| SetFocus + SendKeys {F4}/{DOWN} | ❌ | SendKeys 在非前台窗口无效 |
| JavaScript 注入 (CDP) | ❌ | Store 版 Edge 不支持 CDP |

## 文献查证

- **StackOverflow 5814779**: ExpandCollapsePattern 仅适用于原生 ComboBox
- **Reddit vbh4qu**: 自定义 ComboBox "only supports InvokePattern, not ExpandCollapsePattern"
- **StackOverflow 32075802**: Expand() 后下拉立即折叠的问题

## 唯一可行方案：物理鼠标点击

```
1. 点击下拉箭头图标 (1862, 481) — Edit 控件右侧约 20×20px 的 Text 元素
2. 等待 2 秒（Element UI 下拉动画）
3. UIA 中出现 ListItem → 点击或 InvokePattern
4. 验证：Edit 的 ValuePattern 值不再为空
```

## 关键约束

- **Edge 窗口必须在可见区域**：小鹿常拖窗口到屏幕外（坐标 -21333），每次操作前需 `SetWindowPos` 拉回
- **必须点箭头而非字段本身**：点击计划字段不会展开下拉
- **下拉选项的 UIA 匹配**：ListItem 的 Name 匹配（如 `'2024级专'`），出现在 Y≈534
- **工学云实战验证**（2026-06-03）：40+ 轮表单填写，下拉出现率约 70%。失败原因是 Edge 窗口被拖走

## 结论

Web 组件（el-select、自绘下拉等）是 UIA 的盲区。没有通用后台方案。物理鼠标是唯一可靠路径，但需要窗口在前台。这是当前架构的硬限制。
