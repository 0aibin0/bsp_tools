# bsp_tools 项目分析

分析对象：`D:\00_project\99_AIBIN\python\bsp_tools\bsp_tools`（远端 `git@github.com:0aibin0/bsp_tools.git`）
分析时间：本次会话 · 分支 `main` · 工作区版本 `v3.2.17`
分析目的：为编写根目录 `README.md` 做项目摸底，同时记录发现的问题

---

## 一、项目定位

DisplayTools —— **BSP / LCM 屏体调试工具集**，PyQt5 单窗口桌面应用，Windows 优先、绿色版。

目标用户是 BSP / 驱动 / 屏体调试工程师，工位上常同时插多台板子。核心价值是把散落在
adb 命令、计算器、Excel 里的调试动作收进一个界面，并且**把两个易错计算固化下来**：
DCS 包字节构造、DSI 时序/带宽可行性判定。

---

## 二、技术栈与规模

| 项 | 值 | 来源 |
| --- | --- | --- |
| 语言 / 运行时 | Python 3.11.4 | `.venv/pyvenv.cfg` |
| GUI 框架 | PyQt5 5.15.10（Qt 5.15.2，sip 12.13.0） | `.venv/Lib/site-packages` |
| 打包 | PyInstaller 6.11.1 | 同上 |
| 应用源码 | 约 46 个 `.py` + 8 个 `.ui`，`bsp_tools/` 下 | 目录清点 |
| 自查脚本 | 15 个（`check_*.py` / `verify_*.py` / `selftest.py` / 截图） | `devtools/` |
| 仓库跟踪文件 | 87 个 | `git ls-files` |
| 仓库 pack 体积 | 38.01 MiB | `git count-objects -vH` |
| 打包产物 | `bsp_tools/dist/DisplayTools.exe` 39,029,302 B（约 37 MB），**已入库** | `git ls-files` |
| 许可证 | 无 | 未找到 LICENSE 文件 |

**界面规模**：`theme.py`（1173 行）、`mainwindow.py`（1327 行）、`tools_display.py`（764 行）、
`shell_tools.py`（861 行）、`initcode_builder.py`（644 行）、`update_check.py`（723 行）。
设计令牌集中在 `theme.py`，含浅色/深色两套完整令牌。

---

## 三、架构

### 分层

```
mainwindow.py          主窗口：页面注册表 PAGE_DEFS、侧边栏接线、命令面板、状态栏、Toast
  ├─ sidebar.py        左侧导航 + 快捷操作（8 项）
  ├─ theme.py          设计令牌 / 全局 QSS / 矢量图标生成 / APP_VERSION
  ├─ app_data.py       本机数据文件 DisplayTools.json 读写（唯一数据源）
  │    └─ app_config.py   config 段薄封装（对外 API 保持 config.ini 时代的样子）
  ├─ app_runtime.py    单实例守卫（QLocalServer）、crash.log、异常钩子
  ├─ toolchain.py      adb / fastboot 定位、多设备 -s 注入
  ├─ command_runner.py 命令执行器（补 adb shell 前缀、流式输出）
  └─ update_check.py   检查更新 + 下载 + 自替换重启
```

### 页面注册

`mainwindow.PAGE_DEFS` 是唯一页面注册表，6 个页面分 3 组（常用 / 调试工具 / 转换工具）：

| key | 标题 | 类 |
| --- | --- | --- |
| `tools` | 常用工具 | `CommonToolsPage` |
| `shell` | Shell Tools | `ShellToolsPage` |
| `initcode` | Initcode Builder | `InitcodeBuilderPage` |
| `lk2kernel` | LK → Kernel | `LkToKernelPage` |
| `kernel2lk` | Kernel → LK | `KernelToLkPage` |
| `lk2bat` | LK → BAT | `LkToBatPage` |

`CommonToolsPage` 内部再套一层二级导航：`tools_page.SECTIONS` 列 9 个模块，
三栏布局（模块导航 150px + 内容 + 右侧执行结果面板 270px，QSplitter 可拖拽）。

### 值得注意的设计

- **共享执行器**：`tools_page._inject_runner()` 把本页 `CommandRunner` 注入
  `display / favorites / touch / system` 四个模块，输出统一落在右侧面板。
  性能监控自带采样定时器与独立 runner，**不在名单里**。
- **命令前缀收口**：`command_runner.device_cmd()` 统一补 `adb shell`；带管道/重定向的
  自动包成 `adb shell "..."`。这是为了防「命令漏到 Windows cmd.exe」这个已踩过的坑。
- **多设备**：`toolchain.set_serial()` 全局状态，`serial_args()` 产出 `-s <sn>`，
  `check_multidevice.py` 专门断言不会出现两个 `-s`。
- **资源定位**：`mainwindow.resource_path()` 兼容 PyInstaller `_MEIPASS`；
  `app_data.data_dir()` 在 frozen 时用 `sys.executable` 目录而**不是** `_MEIPASS`
  （后者退出即删，写进去等于没存）——这是有意的区别。
- **数据段语义**：`AppData` 故意不预建 `commands` / `path_bookmarks` 键。
  「段不存在」= 用内置默认清单；「段是空数组」= 就是空。避免用户删光后重启又变回默认。
- **滚动区手动定尺**：`CommonToolsPage._fit_content()` 用 `maximumViewportSize()`
  而非实际视口算，避免「出滚动条→视口变小→再算一次」的抖动。

---

## 四、发版与自更新链路

- 版本号单一来源：`theme.APP_VERSION`（当前 `v3.2.17`）+ git tag，**exe 文件名不带版本号**。
- 仓库只保留最新一个 exe（`bsp_tools/dist/DisplayTools.exe`，37 MB 入库），
  「检查更新」的兜底下载源就是它。
- 更新查询顺序：`/releases/latest` → 退回 tags API 比版本号 → 下载优先 Release 附件，
  否则取仓库 `dist` 下提交的 exe。公开仓库不需要 token；私有仓库需在 config 段配 `update_token`。
- **自替换**：下载到 `DisplayTools.exe.new` → PowerShell `-EncodedCommand` 等 PID 退出 →
  旧 exe 改名 `.old` → 新文件就位 → 启动新版；新版启动 3 秒后自删 `.old`（可回退）。
- **三道完整性校验**（针对「代理掐断连接导致半截 exe 被换上」的历史故障）：
  `Content-Length` 比对 → `MZ` 头校验 → 换文件脚本再核期望大小。
- spawn 用 `CREATE_NO_WINDOW`，注释明确警告**别用 `DETACHED_PROCESS`**（实测会 rc=0 立刻退出）。

---

## 五、自查体系

`run_checks.py` 串联 15 个检查，分「离线 11 项」+「真机 4 项」：

| 类别 | 脚本 |
| --- | --- |
| 离线（11） | `selftest.py`、`check_theme.py`、`check_timing.py`、`check_multidevice.py`、`check_initcode.py`、`check_layout.py`、`check_wraplabel.py`、`check_panel_width.py`、`check_info_dialog.py`、`inspect_ui.py --flag`、`smoke_start.py` |
| 真机（4） | `verify_commands.py`、`verify_on_device.py`、`verify_log_stream.py`、`check_sitepack.py --live` |

**实测 `selftest.py` 结果：`全部通过（230 项检查）`**（本次运行确认）。

设计动机写得很清楚：Qt 布局出问题不报错，只会把控件压到重叠或裁掉，
肉眼看不出来，所以固化成脚本断言。`check_wraplabel.py` 还专门补 `inspect_ui.py`
的盲区（wordWrap 标签的 `minimumSizeHint` 按最窄换行算）。

另有专项脚本 `capture_ui.py`（空界面截图）、`capture_with_data.py`（灌样本数据截图）、
`diag_shell_layout.py`、`check_panel_width.py`（6 种窗口尺寸断言两个文本框都是 240px）。

---

## 六、文档体系

| 文档 | 角色 |
| --- | --- |
| `bsp_tools/ReadMe.md`（16.6 KB） | **开发细节主文档**：布局约定、面板宽度换算、数据文件语义、发版、自查全清单 |
| `func-list.md`（15.4 KB） | 功能清单 + 取舍记录，一行一个功能带「保留」列，末尾按版本记录处理结果 |
| `docs/功能清单.md`（9.4 KB） | 按页面组织的功能清单（给范围划分用），与 func-list 内容有重叠 |
| `docs/t820-lcm-porch-说明.md` | T820 LCM porch 算例 |
| `docs/superpowers/specs/`+`plans/` | UI 优化设计稿与实施计划（含 58 KB 计划文件） |
| `README.md`（本次新建） | GitHub 门面：定位、功能总览、快速开始、目录结构、约定 |

---

## 七、发现的问题

### 1. 文档数字与实际不符（低风险，建议修）

| 位置 | 文档写的 | 实际 |
| --- | --- | --- |
| `bsp_tools/ReadMe.md:142` | 逻辑自测 **228** 项 | 实测 **230** 项 |
| `func-list.md:167` | 一键自查 **14** 项检查 | 实际 **15** 项（11 离线 + 4 真机） |
| `docs/功能清单.md:32` | 常用工具「当前 **10** 个模块」 | 实际 **9** 个（`tools_page.SECTIONS`） |
| `docs/功能清单.md:150` | selftest **117** 项 | 实测 230 项 |

`docs/功能清单.md` 自称「v3.2.0 待定稿」，明显早于 v3.2.17，属于历史文档未同步。
`func-list.md` 是按版本追加的，第 167 行是旧值。

### 2. `mainwindow.py` 初始尺寸与文档不一致（低风险）

- `bsp_tools/ReadMe.md:172` 写「窗口尺寸：默认 **1360x840**」
- 代码 `mainwindow.py:128` 是 `self.resize(1360, 880)`，随后 `_restore_geometry()`
  （第 187 行）在无历史记录时按 `min(max(1360, content_min_width), 1700)` ×
  `min(max(840, content_min_height), 1000)` 重算。

即 840 是**下限**而非定值，实际首次打开高度可能大于 840。文档表述偏简化。

### 3. 未跟踪文件混在工作区（建议清理）

```
?? ~$t820-lcm-porch.xlsx          # Excel 打开时的锁文件，临时产物
?? 大模型价格横屏对比.html          # 与本项目无关的文件（9.6 KB）
```

两者都未被 `.gitignore` 覆盖。`~$*` 是 Office 临时锁文件，建议加进 `.gitignore`
（通用的 `~$*` 规则）；`大模型价格横屏对比.html` 确认无关后应移出或删除。

### 4. 已下线模块的代码保留但无引用（属有意设计）

`tools_guard.py`（异常守护）、`tools_battery.py`（电池调试）已从
`tools_page.SECTIONS` 下线，全项目**无任何 import 引用**（已 grep 确认）。
`ReadMe.md` 明确写了这是有意保留、一行即可恢复。**不是 bug**，但意味着这两个文件
会一直不参与语法/导入级别的自测覆盖。

### 5. git 历史被压缩（事实陈述，非问题）

`git rev-list --count HEAD` = **6**，最早提交是 `ec7f41c v3.2.11`（2026-09-14），
但已有 tag `v3.2.13` ~ `v3.2.17`，且 `dist/` 下留着 `DisplayTools_v3.2.12_onedir` 目录。
**v3.2.12 没有对应提交**，早期历史应是被重建/squash 过。这不影响使用，
但意味着无法从 git log 追溯 v3.2.11 之前的演进。

### 6. 仓库体积主要来自入库的 exe（需持续关注）

`dist/DisplayTools.exe` 单个 37 MB 入库，占 pack 体积 38 MB 的绝大部分。
每次发版替换 exe 都会新增一份 blob（旧 blob 仍在历史里）。`.gitignore` 注释已写明
「出新版本时请删掉旧 exe 再提交」，但**历史累积无法通过删文件回收**。
若将来体积成为问题，可考虑改用 GitHub Release 附件分发 exe（`update_check.py`
已支持 Release 附件优先，这条路径是现成的）。

---

## 八、项目亮点

1. **踩坑沉淀到位**：几乎每个反直觉的实现都有注释解释「为什么不能那样写」
   （`DETACHED_PROCESS` 会 rc=0 退出、`QtNetwork` 不能 exclude、背光节点没有
   `lcd-backlight`、`dumpsys` 长键名要行首锚定）。这类知识留在了正确的位置——代码旁边。
2. **自查脚本覆盖了「不报错的错误」**：布局重叠、标签被压、面板宽度漂移，
   都是 Qt 静默出错的类型，全部固化成断言脚本。
3. **数据层语义严谨**：「段不存在」与「段为空」的区分、`.tmp` + `os.replace` 原子写、
   老文件迁移不删只改名，都是考虑到真实使用场景（用户删光收藏、exe 放只读目录、断电）。
4. **更新链路防御性强**：三道校验 + `.old` 保留回退路径，是针对真实故障（代理掐断）的补强。
5. **出包体积与启动速度做了取舍记录**：单文件 vs onedir 有实测冷启动数据（1.79s vs 0.91s）。

---

## 九、结论

项目处于**活跃维护、工程化程度较高**的状态：15 项自动化检查、清晰的分层、
详尽的设计注释与文档。主要技术债集中在**文档同步**（4 处数字失真、
`docs/功能清单.md` 停留在 v3.2.0）和**工作区杂项文件**上，均属低风险、易修复。

本次已产出根目录 `README.md`，作为 GitHub 门面，与 `bsp_tools/ReadMe.md`
（开发细节）形成分工，并在 README 中显式链接到后者与其余文档，
避免再次出现「两份文档各说各话」。
