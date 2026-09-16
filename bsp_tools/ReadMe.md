# DisplayTools

BSP / LCM 调试工具集。PyQt5 单窗口应用，左侧边栏导航 + 卡片式界面。

## 运行

```bash
python mainwindow.py
```

## 页面

| 页面 | 说明 |
| --- | --- |
| 常用工具 | 9 个模块，见下表 |
| Shell Tools | fastboot 烧录、Debug 自定义命令与 density/printk、func 功能键、GPIO、Download Mode、ylog、APK、投屏（adb 类命令都在侧边栏「快捷操作」和 Ctrl+K 命令面板里，页面不再重复摆一份） |
| Initcode Builder | 寄存器读写描述 ↔ initcode 字节序列（正反向） |
| LK → Kernel | LK 十六进制序列 → 内核格式 |
| Kernel → LK | 内核十六进制序列 → LK 格式 |
| LK → BAT | 生成 DCS 写入批处理脚本 |

### 常用工具的 9 个模块

左侧子导航切换，所有命令输出显示在**本页右侧的「执行结果」面板**（点按钮不会跳页，
面板与内容之间是可拖拽分隔条，可以拖动或收起）。

| 模块 | 能力 |
| --- | --- |
| 日志分析 | logcat/dmesg 流式抓取（含 dmesg -w 实时）、关键字与正则过滤、只看错误、**关键字高亮**、导出 |
| 设备信息 | 型号/系统/屏幕/温度/电量看板，导出 Markdown 报告 |
| 显示调试 | 背光（「设置」走框架 settings，「写节点」直写 sysfs；节点按 panel0-backlight → sprd_backlight 顺序试）、分辨率、刷新率、**DCS 包构造**（命令+参数→字节序列）、**时序/带宽计算**（需求 pclk、T820 DPI 整数分频、实际帧率、每 lane 需求速率含 0.9 效率、D-PHY 上限判定） |
| 现场包 | 一键抓 18 项现场证据（属性/dmesg/logcat/dumpsys/中断/显示节点…）打包 zip，可对每台在线设备各抓一份 |
| 触摸调试 | 点击/滑动/按键注入、触摸可视化开关（划线界面/指针位置）、getevent 抓取 |
| 系统调试 | 属性读写、CPU 调频、内存/进程/挂载、SELinux、重启 |
| 性能监控 | CPU/内存/温度/帧率采样、趋势曲线、采样记录 |
| 文件管理 | 设备目录浏览、上传下载删除、路径书签 |
| 命令收藏 | 常用命令增删改查、分组搜索、双击执行 |

> 按 func-list.md 的标记，**异常守护**与**电池调试**两个模块已下线：
> 代码文件保留在 `bsp_tools/tools_guard.py`、`bsp_tools/tools_battery.py`，
> 要恢复只需把对应行加回 `tools_page.SECTIONS` 与 `_inject_runner()` 名单。
> 显示调试里的 DCS 读写节点、ESD 重置、Panel 参数查询卡片，以及触摸调试里的
> 输入设备枚举按钮也一并移除（都是纯查询或按 ESD 需求砍掉的）。

**「侧边栏有 = 页面上就是重复入口」**：这是本项目一贯的取舍原则。侧边栏
「快捷操作」是常驻入口，凡是在那儿有的命令，页面上都不再重复放一份按钮——
`adb devices / root / remount / debugfs / reboot / cmdline` 与「截图并保存」都已经
从 Shell Tools 移到了快捷操作（8 项）。加新按钮前先看侧边栏有没有。

**布局**：常用工具页是「左侧模块导航 + 中间模块内容 + **右侧执行结果面板**」，
Shell Tools 是「左侧控制区（2 列网格）+ **右侧竖向 Log 面板**」。
两处右侧面板都可以拖拽调宽窄或收起。

> Shell Tools 控制区的网格是**按卡片高度配对**的（87/87、155/164、87/121），
> 目的是让每行左右两张卡等高、少留空白。改动卡片里的控件数会改变自然高度，
> 配错就会出现一大块空白——加按钮/删按钮后跑 `check_layout.py`。
> 卡片里的按钮行也不要只按 sizeHint 排，末尾加 `addStretch` 或给 stretch
> 让它撑满，否则右边会空一截。

**多设备**：状态栏下拉框选设备，选定后所有命令（含 QProcess 跑的）自动带 `-s`；
不选则用 adb 默认设备。选择会记住。

快捷键：`Ctrl+K` 命令面板，`Ctrl+1`~`Ctrl+6` 切换页面。

> 功能取舍见仓库根目录 `func-list.md`（一行一个功能，带「保留」列）。

## 数据文件（与程序同目录）

- `config.ini` — 输入框记忆、adb push/pull 设备路径历史（沿用 v3.0.x 键名）
- `favorites.json` — 命令收藏夹；**Ctrl+K 命令面板和「常用工具 · 命令收藏」
  页共用这一份**（`command_store.py` 是唯一数据源）
- `path_bookmarks.json` — 设备路径书签
- `adb_commands.log` — 命令输出日志

## 版本与更新

- 版本号只在 `theme.APP_VERSION` 和 git tag（`v3.2.13`）里，**exe 文件名不带版本号**。
- 发版流程：改 `APP_VERSION` → 跑 `run_checks.bat` → `DisplayTools.spec` 打包 →
  `git rm` 旧 exe、提交新 exe → `git tag vX.Y.Z` → 推分支**和** tag（检查更新靠 tag）。
- 「检查更新」查的顺序：`/releases/latest`（能拿到说明和附件）→ 没有 Release 就
  退回 tags API 比版本号 → 下载时优先 Release 附件，没有就从仓库
  `bsp_tools/dist` 里取提交好的 exe（仓库是公开的，不需要 token）。
  下载文件名带版本号（`DisplayTools_vX.Y.Z.exe`），不覆盖正在运行的自己，旧版
  留着以便回退。
- 仓库若是私有：在 `config.ini` 里加 `update_token = ghp_xxx`（未带 token 的
  API 调用对私有仓库返回 404）；`update_repo` 可改仓库（默认 `0aibin0/bsp_tools`）。

## 开发自查

**改完代码先跑这个**（`run_checks.bat` 是 `run_checks.py` 的壳，逻辑在 py 里——
bat 是 GBK 代码页，脚本里写中文会被 cmd 解析器撕碎）：

```bash
run_checks.bat            # 离线检查 11 项：自测 / 主题 / 时序 / 多设备 / initcode / 布局 / 换行 / 面板宽度 / 说明框 / 控件 / 冒烟
run_checks.bat device     # 再加上真机相关的 4 项（要连板子）
```

单项也可以单独跑：

```bash
.venv\Scripts\python.exe devtools\inspect_ui.py        # 查控件真实尺寸（定位挤/裁/撑不开）
.venv\Scripts\python.exe devtools\check_layout.py      # 布局健康检查：多种窗口尺寸下检测重叠/压缩/越界
.venv\Scripts\python.exe devtools\check_panel_width.py # 右侧两个面板的文本框必须都是 240px（固定，不随窗口变）
.venv\Scripts\python.exe devtools\check_wraplabel.py   # 自动换行标签高度是否够（inspect_ui 的盲区）
.venv\Scripts\python.exe devtools\selftest.py          # 逻辑自测 170 项（不需要连接设备）
.venv\Scripts\python.exe devtools\check_theme.py       # 浅色/深色令牌完整性与残留检查
.venv\Scripts\python.exe devtools\check_timing.py      # 时序/带宽公式 + 文本解析 + DCS 包构造
.venv\Scripts\python.exe devtools\check_multidevice.py # 多设备 -s 注入（保证不会出现两个 -s）
.venv\Scripts\python.exe devtools\check_initcode.py    # initcode 正反向一致性
.venv\Scripts\python.exe devtools\check_sitepack.py --live  # 现场包真机抓一份（需连设备）
.venv\Scripts\python.exe devtools\verify_commands.py   # 真实执行命令表，确认没有命令漏到 cmd.exe
.venv\Scripts\python.exe devtools\verify_on_device.py  # 真机端到端：填数据、验证解析（需连设备）
.venv\Scripts\python.exe devtools\verify_log_stream.py # 真机流式日志：dmesg -w 积压截断（需连设备）
.venv\Scripts\python.exe devtools\capture_ui.py        # 空界面各页截图 → devtools/shots/
.venv\Scripts\python.exe devtools\capture_ui.py devtools\shots_dark 1360x840 dark  # 深色版截图
.venv\Scripts\python.exe devtools\capture_with_data.py # 灌入样本数据后截图 → devtools/shots_data/
.venv\Scripts\python.exe devtools\smoke_start.py       # 真实平台启动冒烟
```

`inspect_ui.py` 常用姿势：

```bash
python devtools\inspect_ui.py tools.battery    # 看某模块所有控件的 宽/高/最小尺寸/sizeHint
python devtools\inspect_ui.py --flag           # 只列「被压缩 / 该撑开没撑开 / 超出边界」的控件
python devtools\inspect_ui.py --screen shell   # 附带屏幕绝对坐标，便于肉眼定位
python devtools\inspect_ui.py --size 1150x760  # 指定窗口尺寸再看
```

> offscreen 截图必须设置 `QT_QPA_FONTDIR=C:\Windows\Fonts`，否则 Qt 找不到
> 字体，截图里的文字会全部消失。`capture_ui.py` 已内置处理。

**改动布局后务必先跑 `check_layout.py`**：Qt 在空间不足时不会报错，而是把控件
压到互相重叠（表现为文字糊成一团），或让分组框超出滚动区被裁掉。

窗口尺寸：默认 **1360x840**，最小 1300x700。

**右侧「执行结果」面板：分隔条分配 270px，其中文本框实测 240px**（卡片左右各有
15px 内边距，量文本框宽度就是 240）。面板按模块自动显示：日志分析 / 文件管理 /
命令收藏 本身就有日志区或列表区，选中它们时面板收起、内容区用满宽度；
其余模块才显示面板。手动拖过分隔条后不再自动收起。

实测（1360x840）：

| 模块 | 分隔条分配 | 文本框实测 | 内容区 |
| --- | --- | --- | --- |
| 日志分析 | 收起 | — | **958px**（日志框约 910px） |
| 设备信息…性能监控 | 270px | **240px** | 688px |
| 文件管理 / 命令收藏 | 收起 | 958px |

> 「面板宽度」要看量的是哪一层：`runner` 容器 = 分隔条分配值（270），
> 里面 `Card` 同宽，再里面文本框 = 减去左右各 15px 内边距（240）。
> 调宽度改 `tools_page._apply_split_sizes()` 里的 `output_width = 270`。

之所以默认窗口是 1360：270（面板）+ 610（最宽模块）+ 导航 150 + 侧边栏 208 + 边距
≈ 1315，取 1360 留余量。窗口小于 1300 时面板退让，内容区优先。

**两个右侧面板的宽度都是固定的，不随窗口变宽而变宽**（想加宽由用户拖分隔条）：

| 面板 | 分隔条分配 | 文本框实测 | 怎么换算出来的 |
| --- | --- | --- | --- |
| 常用工具 · 执行结果 | 270px | **240px** | 卡片左右各 15px 内边距 |
| Shell Tools · Log | 286px | **240px** | 分组框左右各 23px 内边距 |

**约定：用户量的是文本框，不是外框**——这两个数差 30~46px，踩过两次坑
（执行结果被设成 240 时量到 210；Shell Log 原本按 25% 算，窗口最大化后
文本框涨到 354）。所以固化成了 `devtools/check_panel_width.py`，
它会在这 6 种窗口尺寸下断言两个文本框都是 240：
`1280x800 / 1300x700 / 1360x840 / 1440x900 / 1920x1080 / 2560x1440`。

窗口窄到左列放不下 760px 时，Shell Log 会先从自己身上扣（下限 240px 分配）。
要改「哪些模块不显示面板」调整 `tools_page.SECTIONS_WITHOUT_OUTPUT`；
要改宽度：常用工具改 `tools_page._apply_split_sizes()` 的 `output_width`，
Shell Tools 改 `shell_tools.LOG_PANEL_WIDTH`。

> **两条容易踩的坑**（都真踩过）：
> 1. `ui_shell_tools.setupUi()` 里那句 `setSizes([...])` 是**兜底值**，必须和约定
>    一致。它曾经写的是 360，而 `_apply_split_sizes()` 一旦没跑成（布局没算完就
>    被调用、函数直接 return），用户看到的就是兜底值 → 文本框 314 而不是 240。
> 2. 程序会记住上次打开的页面，所以 `on_page_shown()` 可能在**窗口构造期**就被调用，
>    那时布局还没算、splitter 只有 100px 宽。凡是"按实际宽度算"的逻辑都不能只靠
>    它触发——`ShellToolsPage.showEvent()` 里补了一次，改这块时别删。

改完用 `inspect_ui.py --flag --size 1360x840` 复核，输出「含标记控件 0 个」即为正常。

### 三条必须遵守的约定

1. **设备端命令不要手写 `adb shell`**。直接写 `dumpsys battery`、`cat /proc/meminfo`、
   `getprop xxx`，执行器（`command_runner.device_cmd`）会补前缀；带管道/重定向的
   会自动包成 `adb shell "…"` 交给设备端 shell 解析。
   漏了前缀的命令会被 Windows 的 cmd.exe 执行，报
   `'dumpsys' is not recognized as an internal or external command`。
   `verify_commands.py` 会把命令表真实跑一遍来兜住这类回归。
2. **新增模块时**在 `tools_page.SECTIONS` 加一行，并把模块 key 加进
   `_inject_runner()` 的名单——名单里的模块共用本页执行器与输出面板，
   不在名单里的模块会自己建一个 runner（输出就跑到别处去了）。
3. **解析 `dumpsys` 文本要按行首锚定**（`^[ \t]*key:` + `re.M`）。`dumpsys` 里存在
   `Max charging voltage:` / `Max charging current:` 这类长键名，用松散的 `voltage:`
   会先命中它们——电池模块还在时曾把 12000000 µV 的充电上限当成实时电压显示成
   `12000 mV`。模块虽然下线了，`tools_device.py` 仍在解析同一份输出，写新解析
   代码时按这条来。

## 打包

产物固定叫 `bsp_tools/dist/DisplayTools.exe`（**不带版本号**）：版本号只在
`theme.APP_VERSION` 和 git tag 里，文件名里不重复一份。

```bash
cd bsp_tools
..\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean DisplayTools.spec
```

固定工位想秒开可以用目录版（冷启动 0.91s vs 单文件版 1.79s，代价是 140 个
文件、95MB，产物不进仓库）：

```bash
..\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean DisplayTools_onedir.spec
# -> dist/DisplayTools/DisplayTools.exe
```

spec 中已包含 `icon_img/` 资源；等价命令行方式：

```bash
pyinstaller --onefile --noconsole --icon=icon_img/main.ico --name DisplayTools mainwindow.py
```

> 打包前先关掉正在运行的旧 exe，否则会报 `PermissionError: [WinError 5]`。
> 仓库里只保留最新版本的 exe，出新版时先 `git rm` 掉旧的那个再提交。

## 设计说明

界面配色、间距、控件样式集中在 `theme.py`，改主题只需改该文件顶部的常量。
界面结构与新增功能的详细说明见
`docs/superpowers/specs/2026-09-12-displaytools-v3.1-ui-modernization-and-tools-page.md`。

