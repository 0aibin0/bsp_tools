# DisplayTools

> BSP / LCM 屏体调试工具集 —— PyQt5 单窗口桌面应用，把屏体调试要用的命令、计算和取证固化成一键操作。

[![version](https://img.shields.io/badge/version-v3.2.28-2f6bff)](#版本与发版)
[![python](https://img.shields.io/badge/python-3.11-3776ab)](https://www.python.org/)
[![pyqt5](https://img.shields.io/badge/PyQt5-5.15.10-41cd52)](https://pypi.org/project/PyQt5/)
[![platform](https://img.shields.io/badge/platform-Windows%2010%2F11-0078d4)](#环境要求)

---

## 这是什么

调一块 LCM 屏，日常要反复做这些事：抓 logcat/dmesg 找 ESD 和 underrun、读背光节点、
算一组 porch 参数能不能跑得动这条 DSI、现场出问题时赶紧把证据留全。
这些操作散在 adb 命令、计算器、Excel 和一堆脚本里，**DisplayTools 把它们收进一个界面**。

面向的人：BSP / 驱动 / 屏体调试工程师，工位上常年插着几台板子。

- **不用记命令**：设备端命令直接写 `dumpsys display`、`cat /proc/meminfo`，执行器自动补 `adb shell` 前缀
- **多设备不串台**：状态栏选设备，之后所有命令自动带 `-s`
- **计算内置**：时序/带宽计算按 T820 DPI 整数分频算实际帧率和每 lane 速率，超 D-PHY 上限标红
- **绿色版**：数据文件跟着 exe 走，拷到哪台机器都能用；内置「检查更新」可自替换升级

---

## 功能总览

左侧边栏 4 个页面，分 3 组：

| 分组 | 页面 | 说明 |
| --- | --- | --- |
| 常用 | **常用工具** | 9 个模块，LCM 调试主力页面（见下） |
| 调试工具 | **Shell Tools** | adb / fastboot 设备控制：烧录、Download Mode、func 键、ylog、APK、投屏 |
| 转换工具 | **Initcode Builder** | 6 种输入格式（WriteAddr / Write(Command) / Rxx / GEN_WR / `mipi.write` / `REGS.WRITE`）↔ initcode 字节序列（正反向），可输出 **QCOM 数组**并逐包校验 |
| 转换工具 | **Initcode 格式转换** | 顶部单选切换：LK → Kernel / Kernel → LK / LK → BAT / UNISOC → QCOM |

侧边栏底部常驻 **8 项快捷操作**：列出设备 / 抓现场包 / 获取 root / remount / 挂载 debugfs / 启动参数 / 截图并保存 / 重启设备。

### 常用工具 · 9 个模块

左侧子导航切换，命令输出统一落在**本页右侧的「执行结果」面板**（不跳页，分隔条可拖拽或收起）。

| 模块 | 能力 |
| --- | --- |
| **日志分析** | logcat / dmesg 流式抓取（含 `dmesg -w` 实时）、关键字与正则过滤、只看错误、命中高亮、导出 |
| **设备信息** | 型号 / 系统 / 屏幕 / 温度 / 电量看板，一键导出 Markdown 报告 |
| **显示调试** | 背光（settings 或直写 sysfs，节点量程按 `max_brightness` 自动对齐）、分辨率、刷新率、**DCS 包构造**、**时序 / 带宽计算**、**屏幕 DPI（正算 / 反算）**、**亮度表生成与校验** |
| **现场包** | 一键抓 18 项现场证据打包 zip，可对每台在线设备各抓一份 |
| **触摸调试** | 点击 / 滑动 / 按键注入、触摸可视化开关、`getevent` 抓取 |
| **系统调试** | 属性读写、CPU 调频、内存/进程/挂载、SELinux、重启 |
| **性能监控** | CPU / 内存 / 温度 / 帧率采样、趋势曲线、采样记录 |
| **文件管理** | 设备目录浏览、上传下载删除、路径书签 |
| **命令收藏** | 常用命令增删改查、分组搜索、双击执行（与 `Ctrl+K` 共用一份数据） |

> **显示调试里的几个核心能力**
> - **DCS 包构造**：给命令 + 参数，自动判定短包 `0x05` / 带参短包 `0x15` / 长包 `0x39` 并生成字节序列
> - **时序 / 带宽计算**：从前后沿算 h_total / v_total / 需求 pclk、T820 DPI 整数分频后的**实际帧率**、
>   每 lane 需求速率（含 0.9 效率）、消隐占比，并对照 D-PHY 各版本单 lane 上限判定是否可行。
>   参数支持从剪贴板粘 spec/dmesg 片段自动解析，或跑 `dumpsys display` 从设备读。
>   算例见 [t820-lcm-porch.xlsx](t820-lcm-porch.xlsx) 与 [t820-lcm-porch 说明](docs/t820-lcm-porch-说明.md)。
> - **屏幕 DPI**：给分辨率 + 对角线（或物理宽高）算 PPI 与点距；反过来也能由目标 PPI 反推需要多大的屏。
> - **亮度表**：生成 / 校验 `screenBrightnessMap`，强制 value 与 nits 非递减、HBM 并入顶层表，
>   并算出 `transitionPoint`——写错会让整表被丢弃、`system_server` 崩溃重启。

### 全局能力

| 能力 | 说明 |
| --- | --- |
| 命令面板 `Ctrl+K` | 搜索命令收藏（同一份数据），回车执行；现敲的命令可「存为收藏」落盘 |
| 多设备切换 | 状态栏下拉选设备，选定后所有命令自动带 `-s`，选择会记住 |
| 深浅色主题 | 跟随系统 / 浅色 / 深色（改主题需重启，见 [theme.py](bsp_tools/theme.py) 说明） |
| 工具链路径配置 | 「设置」里指定 `platform-tools` 目录，不依赖 PATH；找不到 adb 时状态栏给可点击提示 |
| 单实例守卫 | 重复启动只激活已有窗口，不抢设备锁 |
| 崩溃日志 | 未捕获异常写 `crash.log`，下次启动提示一次 |
| 检查更新 | 比 git tag 版本号，可直接下载最新 exe 并自替换重启 |

快捷键：`Ctrl+K` 命令面板，`Ctrl+1` ~ `Ctrl+4` 切换页面。

---

## 环境要求

| 项 | 版本 / 说明 |
| --- | --- |
| 操作系统 | Windows 10 / 11（界面与自替换更新逻辑依赖 Windows） |
| Python | 3.11（仓库自带 `.venv`，基于 3.11.4） |
| 依赖 | `PyQt5==5.15.10`；打包另需 `PyInstaller 6.11.1` |
| 设备工具 | `adb` / `fastboot`（可在「设置」里指定路径，或放进 PATH） |

从零装依赖：

```bash
py -3.11 -m venv .venv
.venv\Scripts\python.exe -m pip install PyQt5==5.15.10 pyinstaller==6.11.1
```

---

## 快速开始

### 克隆仓库

```bash
git clone git@github.com:0aibin0/bsp_tools.git
cd bsp_tools
```

> 仓库里只提交了源码、自查脚本和**最新一个** `DisplayTools.exe`（供自动更新下载）。
> 新版本用 `git tag vX.Y.Z` 标记，`git pull` 后即可在「关于」里检查更新。

### 从源码运行

```bash
cd bsp_tools
..\.venv\Scripts\python.exe mainwindow.py
```

### 首次运行

1. 启动后看状态栏：**绿色圆点 + 序列号** = 设备已连接；灰点 = 未连接。
2. 若提示找不到 `adb`，点状态栏提示或进「设置」→ 指定 `platform-tools` 目录（也可用「自动检测」）。
3. 工位插了多台板子时，用状态栏下拉框选定本次要操作的那台。
4. 从源码跑和从 exe 跑用的是**两个不同目录**的数据文件，「关于」和「设置」里都会显示当前正用哪个。

### 打包

产物固定叫 `bsp_tools/dist/DisplayTools.exe`（**不带版本号**）：

```bash
cd bsp_tools
..\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean DisplayTools.spec
```

固定工位想秒开可以用目录版（冷启动 0.91s vs 单文件 1.79s，代价是 140 个文件、约 95MB，产物不进仓库）：

```bash
..\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean DisplayTools_onedir.spec
```

> 打包前先关掉正在运行的旧 exe，否则会报 `PermissionError: [WinError 5]`。

---

## 目录结构

```text
bsp_tools/                      # 仓库根目录
├─ bsp_tools/                   # 应用源码（全部 Python + .ui）
│  ├─ mainwindow.py             #   主窗口 / 入口：侧边栏 + 页面注册 + 命令面板 + 状态栏
│  ├─ theme.py                  #   设计令牌：配色、间距、字体、全局样式表、APP_VERSION
│  ├─ sidebar.py                #   左侧边栏导航与快捷操作
│  ├─ command_runner.py         #   命令执行器（补 adb shell 前缀、多设备 -s）
│  ├─ toolchain.py              #   adb / fastboot 定位与多设备选择
│  ├─ app_data.py / app_config.py  # 本机数据文件 DisplayTools.json 的读写
│  ├─ app_runtime.py            #   单实例守卫、崩溃日志
│  ├─ update_check.py           #   检查更新 + 下载自替换重启
│  ├─ tools_page.py             #   常用工具页（三栏：模块导航 + 内容 + 执行结果）
│  ├─ tools_*.py                #   常用工具 9 个模块（log/device/display/sitepack/touch/system/perf/files/favorites）
│  ├─ shell_tools.py            #   Shell Tools 页
│  ├─ initcode_builder.py       #   Initcode 正反向转换
│  ├─ lk_to_kernel.py / kernel_to_lk.py / lk_to_bat.py   # LK 系列转换
│  ├─ timing.py                 #   时序 / 带宽计算与 DCS 包构造（纯函数）
│  ├─ brightness_map.py         #   亮度表解析 / 校验 / XML 生成（纯函数）
│  ├─ brightness_map_dialog.py  #   亮度表对话框
│  ├─ ui_*.py / ui_*.ui         #   Qt Designer 生成的界面代码与源文件
│  ├─ icon_img/                 #   图标资源
│  └─ dist/DisplayTools.exe     #   打包产物（仓库只保留最新一个，供自更新下载）
├─ devtools/                    # 开发自查脚本（check_*.py / verify_*.py / selftest.py / 截图）
├─ docs/                        # 设计与功能文档
│  └─ analysis/                 #   历次改动分析（审计 / 格式 / 发版排查）
├─ requirements.txt             # 运行时依赖（只有 PyQt5）
├─ requirements-dev.txt         # 打包 / 设计器 / 图标依赖
├─ run_checks.py / run_checks.bat   # 一键自查入口
├─ func-list.md                 # 功能清单与取舍记录（一行一个功能，带「保留」列）
└─ README.md                    # 本文件
```

---

## 开发自查

Qt 布局出问题**不会报错**，只会把控件压到重叠或把内容裁掉，肉眼看「差不多」就漏过去了 ——
所以改完代码跑一遍：

```bash
run_checks.bat            # 离线 11 项：自测 / 主题 / 时序 / 多设备 / initcode / 布局 / 换行 / 面板宽度 / 说明框 / 控件 / 冒烟
run_checks.bat device     # 再加上真机相关的 4 项（要连板子）
```

常用单项：

```bash
.venv\Scripts\python.exe devtools\selftest.py          # 逻辑自测（不连设备）
.venv\Scripts\python.exe devtools\check_layout.py      # 多种窗口尺寸下检测重叠/压缩/越界
.venv\Scripts\python.exe devtools\check_timing.py      # 时序/带宽公式 + 文本解析 + DCS 包构造
.venv\Scripts\python.exe devtools\inspect_ui.py --flag --size 1360x840   # 查被压缩/该撑开没撑开的控件
.venv\Scripts\python.exe devtools\capture_ui.py        # 各页截图 → devtools/shots/
```

> 完整的检查脚本清单（含真机验证、截图、UI 结构检查）见 [bsp_tools/ReadMe.md](bsp_tools/ReadMe.md#开发自查)。

**改动布局后务必先跑 `check_layout.py`** —— 这是本项目最容易出、又最不容易发现的一类回归。

---

## 数据文件

程序是绿色版，**本机数据只有一个 JSON**，放在 exe / 源码同目录：

```json
{
  "version": 1,
  "config":         { "window_width": "1360", "last_page": "tools" },
  "commands":       [ {"group": "常用", "name": "列出设备", "command": "adb devices"} ],
  "path_bookmarks": [ "/sdcard/", "/data/ylog/" ]
}
```

- `config` — 输入框记忆、窗口尺寸、上次页面、adb 路径、push/pull 路径历史
- `commands` — 命令收藏，**`Ctrl+K` 命令面板和「命令收藏」页共用这一段**
- `path_bookmarks` — 文件管理的设备路径书签

老的三件套（`config.ini` / `favorites.json` / `path_bookmarks.json`）首次运行会自动合并进来，
然后改名成 `*.migrated`（不删数据，随时能翻回去）。实现见 [app_data.py](bsp_tools/app_data.py)。

---

## 版本与发版

- 版本号只在 [theme.py](bsp_tools/theme.py) 的 `APP_VERSION` 和 git tag 里，**exe 文件名不带版本号**。
- 发版流程：改 `APP_VERSION` → 跑 `run_checks.bat` → `DisplayTools.spec` 打包 →
  `git rm` 旧 exe、提交新 exe → `git tag vX.Y.Z` → 推分支**和** tag（检查更新靠 tag）。
- 仓库只保留最新一个 exe，出新版先删旧的，避免仓库持续膨胀。
- 「检查更新」查的顺序：`/releases/latest` → 没有 Release 就退回 tags API 比版本号 →
  下载时优先 Release 附件，没有就从仓库 `bsp_tools/dist` 取提交好的 exe（仓库公开，不需要 token）。
- 「下载并重启」会做**三道完整性校验**（`Content-Length` 比对 / `MZ` 头 / 换文件前再核大小），
  失败则当前版本不动，避免半截 exe 换上去后新版本起不来。
- 仓库若改为私有：在本机数据文件的 `config` 段加 `"update_token": "ghp_xxx"`。

当前版本：**v3.2.28**

---

## 相关文档

| 文档 | 内容 |
| --- | --- |
| [bsp_tools/ReadMe.md](bsp_tools/ReadMe.md) | **开发细节主文档**：布局约定、面板宽度换算、数据文件语义、发版与自查全清单 |
| [func-list.md](func-list.md) | 功能清单与取舍记录（一行一个功能，带「保留」列与每次版本的处理说明） |
| [docs/功能清单.md](docs/功能清单.md) | 按页面组织的功能清单（给范围划分用） |
| [docs/t820-lcm-porch-说明.md](docs/t820-lcm-porch-说明.md) | T820 LCM porch 算例说明 |
| [UI 现代化设计说明](docs/superpowers/specs/2026-09-12-displaytools-v3.1-ui-modernization-and-tools-page.md) | v3.1 界面结构与新增功能的设计说明 |
| [docs/analysis/](docs/analysis/) | 历次改动的分析文档：项目审计、DPI/布局、QCOM 格式、REGS.WRITE、CI、发版排查等 |

### 三条必须遵守的约定

1. **设备端命令不要手写 `adb shell`**，直接写 `dumpsys battery`、`cat /proc/meminfo`，
   执行器会补前缀；漏了前缀的命令会被 Windows 的 `cmd.exe` 执行并报「不是内部或外部命令」。
2. **新增模块**要在 [tools_page.py](bsp_tools/tools_page.py) 的 `SECTIONS` 加一行，
   并把模块 key 加进 `_inject_runner()` 名单，否则输出会跑到别处。
3. **解析 `dumpsys` 文本按行首锚定**（`^[ \t]*key:` + `re.M`），松散匹配会先命中
   `Max charging voltage:` 这类长键名。

---

## 许可

内部调试工具，未附带开源许可证。作者：**a1bin**
