# bsp_tools 项目缺口分析（需要补充什么）

分析对象：`D:\00_project\99_AIBIN\python\bsp_tools\bsp_tools`
分支 `main` · 版本 `v3.2.17` · 跟踪文件 87 个 · 与 [PROJECT_ANALYSIS.md](PROJECT_ANALYSIS.md) 互补
本文件聚焦「**缺什么、为什么需要、怎么补**」，不重复上一份的架构梳理。

---

## 结论摘要

项目**功能与自查体系是成熟的**（15 项检查、230 条断言），真正的缺口集中在
**「换一个人/换一台机器能不能把它跑起来」**这一层，也就是工程化收口。

| 级别 | 条目 | 影响 |
| --- | --- | --- |
| **P0** | 依赖未声明、`run_checks.py` 路径写死、`main.ico` 其实是 PNG、无 `.gitattributes` | 新环境跑不起来 / 换机器打包失败 |
| **P1** | 无 CI、`.claude/` 只靠机器级 ignore、无 LICENSE、图标不一致 | 回归靠人记 / 有误提交风险 / 法务口径不清 |
| **P2** | 文档数字失真、`~$*` 未忽略、2 处无效 `print`、硬编码本机路径、文档单向链接 | 体验与可维护性 |

---

## P0 — 影响「跑得起来」，建议优先补

### 1. 没有 `requirements.txt` / `pyproject.toml`

**现状**：仓库里**从来没有过**依赖声明（`git log --all -- requirements.txt pyproject.toml` 为空）。
依赖只存在于本机 `.venv`，而 `.venv/` 在 `.gitignore:5` 里。

**实测版本**（从 site-packages 读出，可直接用作锁定值）：

| 包 | 版本 | 用途 |
| --- | --- | --- |
| PyQt5 | 5.15.10 | 运行时 |
| PyQt5-Qt5 | 5.15.2 | 运行时（PyQt5 传递依赖） |
| PyQt5-sip | 12.13.0 | 运行时（传递依赖） |
| Pillow | 11.0.0 | **打包隐式依赖**（见第 3 条） |
| PyInstaller | 6.11.1 | 打包 |
| pyqt5-tools | 5.15.9.3.3 | 生成 `ui_*.py`（Qt Designer） |

**建议**：加 `requirements.txt`

```text
PyQt5==5.15.10
Pillow>=10.0          # PyInstaller 把 icon_img/main.ico 转成 exe 图标时需要
```

再加 `requirements-dev.txt`

```text
-r requirements.txt
pyinstaller==6.11.1
pyqt5-tools==5.15.9.3.3
```

> 上一轮我在 [README.md](../../README.md) 里写的是手敲 `pip install PyQt5==5.15.10 pyinstaller==6.11.1`，
> 那只是权宜之计；有了 `requirements.txt` 就把 README 那段换成 `pip install -r`。

### 2. `run_checks.py` 把 `.venv` 路径写死，新克隆必挂

**现状**：[run_checks.py:19](run_checks.py#L19)

```python
PYTHON = os.path.join(ROOT, ".venv", "Scripts", "python.exe")
```

没有兜底。`.venv` 是 gitignore 的，所以**新克隆的仓库执行 `python run_checks.py`
会在第一个检查就抛 `FileNotFoundError`**。

[run_checks.bat](run_checks.bat) 里虽然有兜底（`if not exist "%PY%" set "PY=python"`），
但它兜的是**外层**——真正跑子进程的是 `run_checks.py`，还是用那个写死的路径。

**建议**：加兜底，和 bat 的规则保持一致

```python
PYTHON = os.path.join(ROOT, ".venv", "Scripts", "python.exe")
if not os.path.isfile(PYTHON):          # 没有本地 venv（例如新克隆 / CI）就用当前解释器
    PYTHON = sys.executable
```

> 这一条不只是易用性——**它同时是开启 CI 的前置条件**（见 P1-1）。

### 3. `icon_img/main.ico` 其实是一个 PNG

**实测证据**：

| 文件 | 大小 | 前 4 字节 | SHA256 |
| --- | --- | --- | --- |
| `main.ico` | 3235 | `89 50 4E 47`（PNG） | `B1EA98DB…C5E85` |
| `main.png` | 3235 | `89 50 4E 47`（PNG） | `B1EA98DB…C5E85` |

两者 **SHA256 完全相同**，即 `main.ico` 就是 `main.png` 改了扩展名。
真 ICO 的头 4 字节应为 `00 00 01 00`。

**为什么现在没暴露**：`DisplayTools.spec:74` 写的是 `icon=['icon_img\\main.ico']`，
PyInstaller 在装了 **Pillow** 的情况下会自动把 PNG 转成 ICO，所以打包"成功"了。
本机 PIL 11.0.0 装着，于是没人发现。

**后果**：谁在一台没装 Pillow 的机器上打包，就会得到 `icon file must be in .ico format`
或一个没图标的 exe——而且**依赖没声明，他根本不知道为什么**（正好和第 1 条叠加）。

**建议**（二选一）：

- **A（推荐）**：生成一个真 ICO 覆盖 `main.ico`，同时保留 PNG：
  ```bash
  .venv\Scripts\python.exe -c "from PIL import Image; Image.open('bsp_tools/icon_img/main.png').save('bsp_tools/icon_img/main.ico', sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])"
  ```
- **B**：接受现状，但把 Pillow 明确写进 `requirements.txt`（第 1 条已含），并在 spec 注释里写明「主图标是 PNG，靠 Pillow 转换」。

### 4. 没有 `.gitattributes`

**现状**：仓库里 37 MB 的 `bsp_tools/dist/DisplayTools.exe` 没有二进制标记，
git 会按文本处理（`git diff`/`git show` 可能尝试输出乱码差异）；
`.bat` 需要 CRLF；`icon_img` 下有中文文件名（`微软视窗_windows.png`、`转换.png`）。

**建议**：加 `.gitattributes`

```gitattributes
* text=auto
*.py    text eol=lf
*.bat   text eol=crlf
*.exe   binary
*.ico   binary
*.png   binary
*.xlsx  binary
*.univer binary
```

---

## P1 — 强烈建议补

### 1. 没有 CI，11 项离线检查完全能自动化

**现状**：无 `.github/` 目录。检查只能靠人记得跑 `run_checks.bat`。

**可行性已核实**：`run_checks.py` 的 11 项离线检查里，**10 项自带
`QT_QPA_PLATFORM=offscreen`**，不依赖真实桌面：

| 脚本 | offscreen |
| --- | --- |
| `selftest.py` / `check_theme.py` / `check_initcode.py` / `check_layout.py` / `check_panel_width.py` / `check_wraplabel.py` / `check_info_dialog.py` / `inspect_ui.py` / `check_sitepack.py` / `verify_commands.py` / `verify_log_stream.py` / `verify_on_device.py` | ✅ 自带 |
| `check_timing.py` / `check_multidevice.py` | 纯逻辑，不建 QApplication |
| `smoke_start.py` | ❌ 需要真实显示（会 `window.show()`） |

**建议**：`.github/workflows/checks.yml`，跑在 `windows-latest`（`smoke_start.py` 需要桌面会话，
Linux runner 没有；Windows runner 有）：

```yaml
name: checks
on: [push, pull_request]
jobs:
  offline:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.11' }
      - run: pip install -r requirements.txt
      - run: python run_checks.py
```

> 前提是先做 P0-2（否则 CI 里 `run_checks.py` 找不到 `.venv`）。
> 若 `smoke_start.py` 在 runner 上不稳定，可先把它从 CI 排除，只跑其余 10 项。

### 2. `.claude/settings.local.json` 只靠「机器级全局 ignore」挡着

**现状**：`git check-ignore -v .claude/settings.local.json` 命中的是
`C:\Users\J6001589/.config/git/ignore`（**本机全局 ignore**），**不在仓库 `.gitignore` 里**。

**风险**：换一台机器、或换一个没有这个全局 ignore 的同事，`git add -A` 就会把这份
含本机绝对路径和权限清单的文件提交上去。

**建议**：仓库级 `.gitignore` 补一行

```gitignore
# 编辑器 / 助手工具的本地配置（含本机路径，不入库）
.claude/
```

### 3. 没有 LICENSE

**现状**：公开仓库（`update_check.py` 的设计前提就是「仓库是公开的，不需要 token」），
但无任何许可证文件。

**影响**：没有许可证 = 法律上默认「保留所有权利」，别人不能合法复制/修改/分发。
内部工具通常不介意，但既然放在了 GitHub 公开仓库上，建议明确一下口径。

**建议**：至少加一个极简 `LICENSE` 说明「内部使用，未授权分发」；若想放开，用 MIT。

### 4. 窗口图标与 exe 图标不是同一张图

**现状**：

- [mainwindow.py:125](bsp_tools/mainwindow.py#L125) → `icon_img/classification.png`（窗口/任务栏图标）
- [DisplayTools.spec:74](bsp_tools/DisplayTools.spec#L74) → `icon_img/main.ico`（= `main.png`，exe 图标）

**影响**：exe 文件图标和运行起来后任务栏的图标是两张不同的图，品牌不一致。

**建议**：统一用 `main.png`/`main.ico` 作为窗口图标（改 `mainwindow.py:125`），
把 `classification.png` 留给侧边栏 logo 之类的用途。

---

## P2 — 小问题，顺手可改

| # | 问题 | 位置 | 建议 |
| --- | --- | --- | --- |
| 1 | `~$t820-lcm-porch.xlsx`（Excel 锁文件）未忽略 | 工作区根 | `.gitignore` 加 `~$*` |
| 2 | 2 处 `print` 在 `--noconsole` 打包后无处可见 | [mainwindow.py:1310](bsp_tools/mainwindow.py#L1310)、[shell_tools.py:466](bsp_tools/shell_tools.py#L466) | 改成 `app_runtime.write_crash_log()` 或直接删 |
| 3 | 硬编码本机路径（换人即失效） | [shell_tools.py:20-21](bsp_tools/shell_tools.py#L20-L21) | 挪进 `config` 段默认值，或在「设置」里暴露 |
| 4 | 文档单向链接：从 `ReadMe.md` 进不去根 `README.md` | bsp_tools/ReadMe.md | 顶部加一行「项目总览见仓库根 README.md」 |
| 5 | 文档数字失真 4 处 | 见 [PROJECT_ANALYSIS.md](PROJECT_ANALYSIS.md) 第七节 | 一次性对齐 |
| 6 | `func-list.md` 与 `docs/功能清单.md` 内容重叠 | 两份文档 | 后者标注「历史归档，以 func-list.md 为准」 |
| 7 | selftest 章节编号跳过 `[9]` | devtools/selftest.py | 重编号或确认是有意留白 |
| 8 | `大模型价格横屏对比.html` 与本项目无关 | 工作区根 | 移出仓库目录 |
| 9 | 本地 `dist/DisplayTools_v3.2.12_onedir` 占 94.9 MB / 140 文件 | 本地（已忽略） | 可删，需要时重新打包 |

---

## 已确认「不是问题」，不要误改

核查过程中有几处看起来可疑、实际是**有意设计**，改之前务必先看注释：

| 现象 | 结论 |
| --- | --- |
| 67 处 `except Exception`，0 处裸 `except` | 有意为之，配合「配置坏了不能让程序起不来 / 写失败只返回值不抛」的约定 |
| `tools_guard.py` / `tools_battery.py` 无任何 import | 有意保留，`ReadMe.md` 写明「一行即可恢复」；不属于遗留代码 |
| `AppData` 不预建 `commands` / `path_bookmarks` 键 | 有意设计，「段不存在」≠「段是空数组」 |
| `QtNetwork` 没在 `EXCLUDES` 里 | 有意，单实例守卫要用 |
| `toolchain.shell_exe()` 未配置时返回裸 `adb` | 有意，命令串要显示给用户看，不能塞全路径 |
| touch / system 模块担心没测试覆盖 | **实际有**：selftest `[8]`/`[10]` 段覆盖了 touch 注入与 system 查询表 |
| `mainwindow.py:128` `resize(1360, 880)` 与文档 840 不一致 | 只是文档表述简化，840 是下限，非缺陷（见 PROJECT_ANALYSIS.md） |

---

## 建议执行顺序

1. **P0-2**（`run_checks.py` 兜底）—— 一行改动，解锁 CI
2. **P0-1**（`requirements.txt` + `requirements-dev.txt`）—— 新环境可复现
3. **P0-3**（生成真 ICO）—— 消除隐式 Pillow 依赖
4. **P0-4**（`.gitattributes`）—— 二进制与换行
5. **P1-1**（CI workflow）—— 回归不再靠人记
6. **P1-2 / P2-1**（`.gitignore` 补 `.claude/` 与 `~$*`）—— 防误提交
7. **P1-4 / P2-5 / P2-4**（图标统一 + 文档对齐 + 反向链接）
8. **P1-3**（LICENSE 口径）—— 需要你拍板

前 6 项都是纯增量、不改任何业务逻辑，风险接近于零。
