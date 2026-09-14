# DisplayTools v3.1.0 界面现代化 + 常用工具页 设计说明

日期: 2026-09-12
版本: v3.1.0

## 目标

1. 界面现代化：把 v3.0.x 的「顶部 Tab + 平铺控件」升级为现代桌面工具观感。
2. 新增第 6 个导航页「常用工具」，集中放日常最高频的能力。

## 一、界面现代化

### 布局：顶部 Tab → 左侧边栏

```
┌──────────┬─────────────────────────────────────────────┐
│ 品牌区    │ 页面标题 + 副标题        [命令面板][帮助]…   │  ← headerBar
│ ──────── ├─────────────────────────────────────────────┤
│ 常用      │                                             │
│  常用工具 │            内容区（QStackedWidget）           │
│ 调试工具  │                                             │
│  Shell   │                                             │
│ 转换工具  │                                             │
│  Initcode│                                             │
│  LK→Kern │                                             │
│  …       │                                             │
│ ──────── │                                             │
│ 快捷操作  │                                             │
│  by a1bin│                                             │
├──────────┴─────────────────────────────────────────────┤
│ ● 设备：xxx            执行中…   时间        a1bin       │  ← statusBar
└────────────────────────────────────────────────────────┘
```

- 新增 `sidebar.py`：深色侧边栏，分组小标题、选中态高亮、矢量图标，
  底部「快捷操作」提供列出设备 / root / debugfs / 截图 / 重启。
- 页面对应关系仍是 6 个：常用工具、Shell Tools、Initcode Builder、
  LK→Kernel、Kernel→LK、LK→BAT。
- 用 `QStackedWidget` 而非 `QTabWidget`，避免 Tab 栏的原生外观限制。

### 设计系统：theme.py

集中管理设计令牌，改配色只需改一处：

| 类别 | 取值 |
| --- | --- |
| 背景 | `#f4f6fa`，卡片 `#ffffff` |
| 主色 | `#2f6bff`（hover `#4a7dff`，pressed `#1f52d6`） |
| 文字 | 主 `#1b2436` / 次 `#67748c` / 提示 `#98a2b3` |
| 语义色 | 成功 `#12a150`、警告 `#c47f17`、危险 `#e5484d` |
| 圆角 | 卡片 10px，控件 8px |

样式表统一处理：按钮（含 `accent` / `ghost` / `danger` / `segment` 四种
语义变体）、输入框、下拉框、滑块、进度条、列表/表格、滚动条、状态栏。

图标全部用 `QPainter` 现画（`theme.icon(name, color, size)`），不新增资源文件，
且能跟随主题色变化。

### 新增的全局能力

- **命令面板（Ctrl+K）**：搜索并直接执行常用 adb 命令。
- **浮层提示 Toast**：操作结果在右下角以浮层反馈，不再只靠日志区。
- **状态栏设备指示**：启动后异步探测 adb 设备，绿点表示在线。
- **快捷键**：Ctrl+1~6 直接切换页面。

## 二、第 6 页「常用工具」

页面内用分段控件（segmented control）切换 6 个子功能，不额外占用侧边栏条目。

| 子功能 | 文件 | 能力 |
| --- | --- | --- |
| 日志分析 | `tools_log.py` | logcat/dmesg 流式抓取；关键字 + 正则过滤；只看错误；错误行红色高亮；导出 |
| 设备信息 | `tools_device.py` | 15 项信息串行拉取；12 张指标卡（含温度/电量/内存配色的健康度着色）；复制摘要 / 导出 Markdown 报告 |
| 命令收藏 | `tools_favorites.py` | 快捷命令增删改查、分组、搜索；持久化到 `favorites.json`；双击直接执行 |
| 文件管理 | `tools_files.py` | 设备目录浏览（`ls -la` 解析）、进入上级、过滤、右键菜单；上传/下载/删除；路径书签 `path_bookmarks.json` |
| 显示调试 | `tools_display.py` | 背光（settings + max_brightness）、分辨率/刷新率、DCS 读写、ESD 重置、Panel 参数一键查询 |
| 性能监控 | `tools_perf.py` | 定时采样 CPU/内存/温度/电量/帧率/存储；自绘趋势曲线（QPainter，无第三方图表依赖）；采样记录表；掉帧累计 |

复用策略：需要执行命令的子功能统一调用
`ShellToolsPage.run_command(command, label)`，输出落在 Shell Tools 的日志区，
键鼠操作与日志回看保持一致；`run_command` 会在结束时用 Toast 反馈成败。

## 三、代码结构变化

```
新增  theme.py          设计系统（配色/样式表/矢量图标）
新增  sidebar.py        侧边栏导航组件
新增  ui_widgets.py     卡片、指标卡、按钮等复用组件
新增  tools_page.py     第 6 页容器（分段控件 + 子页）
新增  tools_log.py / tools_device.py / tools_favorites.py
      tools_files.py / tools_display.py / tools_perf.py
新增  ui_transform.py   转换页共用界面构建（消除三份重复 UI 代码）
重写  mainwindow.py     侧边栏装配、标题栏、状态栏、命令面板、Toast
改写  ui_lk_to_kernel.py / ui_kernel_to_lk.py / ui_lk_to_bat.py → 薄封装
改写  ui_initcode_builder.py  去掉 156px 限宽，命令格式卡片不再截断
调整  ui_shell_tools.py / shell_tools.py  间距、按钮层级、对外执行接口
新增  DisplayTools_v3.1.0.spec  打包配置（补上 icon_img 资源）
新增  devtools/         开发自查脚本（截图 + 自测 + 启动冒烟）
```

## 四、开发自查脚本（devtools/）

```bash
.venv\Scripts\python.exe devtools\capture_ui.py    # 12 张页面截图 → devtools/shots/
.venv\Scripts\python.exe devtools\selftest.py      # 42 项逻辑自测（不需要真机）
.venv\Scripts\python.exe devtools\smoke_start.py   # 真实平台启动冒烟
```

`capture_ui.py` 用 Qt offscreen 平台渲染截图。注意：offscreen 平台默认找不到
字体（`QFontDatabase().families()` 为空），必须通过 `QT_QPA_FONTDIR` 指向
`C:\Windows\Fonts`，否则截图里所有文字都不会被绘制。

## 五、踩到的坑（供后续参考）

1. **Qt 布局空间不足时不会报错，而是让控件互相重叠**：Shell Tools 原布局的
   最小高度需求是 989px，而 1360x860 的窗口只能给内容区 774px，结果
   `adb` 分组的 9 个按钮 y 间距被压到 15px，文字叠在一起看不清。
   排查方法：`devtools/check_layout.py` 逐控件比对几何与 minimumSizeHint，
   并用矩形相交检测兄弟控件重叠。
2. **按钮样式表的 padding 会抬高控件最小高度**：全局 `QPushButton` 的
   `padding: 6px 14px; min-height: 20px` 让每个按钮实际要 34px 高，紧凑
   布局里根本排不下。降到 `5px 12px / min-height: 18px` 后按钮变成 30px，
   布局立刻宽松。
3. **Qt 样式表不支持 CSS 三角**：`QComboBox::down-arrow` 用
   `border-left/right/top` 三角写法会渲染成实心方块；内联 data URI 也不被
   解析。最终方案：`QPainter` 画箭头 → 存到临时目录 → 样式表按文件 `url()` 引用。
   另注意：一旦自定义 `::drop-down`，原生箭头就不再绘制。
4. **样式表字符串拼接容易出语法错误**：`f"..." "..."` 隐式拼接时很容易漏空格，
   Qt 会报 `Could not parse stylesheet` 并静默丢掉整段样式。能用属性选择器
   （`setProperty("tone", ...)`）就不要动态拼样式表。
5. **`df /data` 可能只返回一行**，解析时不能硬性要求「表头 + 数据」两行。
6. **离屏截图里所有文字消失** ⇒ 先查 `QFontDatabase().families()` 是否为空。
7. **QStackedWidget.minimumSizeHint() 只算当前页**，要统计所有页面的最小
   需求必须逐页切过去量（`mainwindow.py` 里就是这么算窗口最小尺寸的）。
8. **不定长文本（设备型号、内核版本）要主动省略**：QLabel 直接放不下会被
   硬裁切，看起来像丢字；`ui_widgets.ElidedLabel` 用
   `QFontMetrics.elidedText` 做中途省略并挂完整 tooltip。

## 六、布局约束（改 Shell Tools 前必读）

| 项目 | 数值 |
| --- | --- |
| 窗口默认尺寸 | 1360 x 880 |
| 窗口最小尺寸 | 1080 x 700（由 MainWindow 显式设置） |
| 内容区实际需要 | 约 1333 x 910（三列网格的天然最小需求） |
| 兜底 | Shell Tools 与「常用工具」页整体套 `QScrollArea`，窗口更小时滚动查看 |

也就是说：窗口足够大时三列完整展开；缩到 910px 以下时出现滚动条，
控件不会被压到重叠。

## 不做的事

- 不改动转换算法（initcodebuilder_1~4、lk↔kernel、lk→bat 逻辑原样保留）。
- 不改动既有 adb/fastboot 命令语义与 config.ini 键名（历史数据兼容）。
- 不引入第三方依赖（图表自绘，图标自绘）。
