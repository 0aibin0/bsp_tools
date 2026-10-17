# DisplayTools 后续功能与优化建议

分析对象：`bsp_tools/`（v3.2.19 + 工作区未发布改动）
方法：读代码 + 实测布局 + 对照 `func-list.md` / `docs/功能清单.md` 的既有取舍
结论：**3 个真 bug 值得先修，3 个 LCM 闭环功能值得加，其余是体验与工程债。**

---

## 一、优先级总览

| 级别 | 项 | 类型 | 预估 |
| --- | --- | --- | --- |
| **P0** | 1. 「写节点」亮度量程与 `max_brightness` 不匹配 | bug | 1–2h |
| **P0** | 2. DCS 包构造参数上限差一（255 → 负载 256） | bug | 15min |
| **P0** | 3. 显示调试页进入时不读设备当前状态 | 体验缺陷 | 1h |
| **P1** | 4. 亮度表（`screenBrightnessMap`）生成 + 校验 | 新功能 | 4–6h |
| **P1** | 5. Initcode Builder 增加「QCOM 数组」输出 + 逐包校验 | 新功能 | 3–4h |
| **P1** | 6. 屏幕 DPI 反向查询（定 PPI 求对角线 / 定对角线求物理宽高） | 新功能 | 1–2h |
| **P2** | 7. 6 个 porch 输入框长期被 `inspect_ui` 误报「压缩」 | 检查器误报 | 30min |
| **P2** | 8. 硬编码本机路径（scrcpy / APK） | 可移植性 | 1–2h |
| **P2** | 9. `timing.DPI_SOURCES` 死代码 | 清理 | 10min |
| **P3** | 10. `requirements.txt` / CI / `main.ico` 实为 PNG / `.gitignore` 补 `~$*` | 工程债 | 2–3h |

---

## 二、P0：建议先修的三个真问题

### 1. 「写节点」的亮度量程是错的

**证据**

```python
# tools_display.py:159
self.bright_slider.setRange(0, 255)
...
# tools_display.py:879  写节点直接把这个 0..255 的值写进 sysfs
self.runner.run(_write_all("brightness", value), ...)
```

而 sysfs 的亮度量程由 `max_brightness` 决定。按你们平台的实际口径
（**节点值 = HAL value × 1023**，value 0.8 → 节点 818），节点满量程是 1023。

**后果**：用「写节点」调屏体时，滑块拉到底只写了 **255 / 1023 ≈ 25%**，
屏体根本到不了满亮。而「设置」（走 `settings put system screen_brightness`）
用 0..255 是**对的**——两条路径量程不同，现在共用了一个输入框。

**建议**

- 进页面/点「读取」时读 `max_brightness`，用它设滑块上限；
- 亮度框改成「绝对值 + 百分比」两个读数（例如 `818 (80%)`），写节点时按节点量程，
  走框架时按 0..255 折算；
- 两条路径分别提示当前用的是哪个量程，避免再混淆。

> 这条直接影响屏体调试主流程，优先级最高。

### 2. DCS 包构造的参数上限差一

**证据**

```python
# tools_display.py:829
if len(params) > 0xFF:          # 允许 255 个参数
    ...
# timing.py:401
payload = [command] + params    # payload = 1 + 255 = 256
return prefix + [count] + payload
```

`count = 256` 后，`"0x{:02x}".format(256)` 产出 **`0x100`**（三位十六进制），
生成的字节序列直接不可用；而提示文案写的是「长包负载最长 255 字节」，
实际负载是 256。**上限应该是 254 个参数**（payload = 1 + 254 = 255）。

**建议**：`if len(params) > 0xFE:`，并补一条边界断言（254 通过 / 255 拒绝）。

### 3. 进入显示调试页不读设备状态

```python
# tools_display.py:928
def on_page_shown(self):
    self.bright_slider.setFocus()
```

只抢焦点。用户每次进页面都得手动点「读取」，而亮度/分辨率是进来第一眼就要看的。
**建议**：`on_page_shown` 里静默跑一次 `wm size` + 背光读取（只读、快），
把结果填进输入框；失败不影响页面。

---

## 三、P1：值得补的三个 LCM 闭环功能

### 4. 亮度表 `screenBrightnessMap` 生成 + 校验（建议优先做）

现在工具里**完全没有**亮度表能力（全项目搜不到 `screenBrightnessMap` / `nits`）。
而这正好是你们踩过坑的地方：

- `<value>` 与 `<nits>` 都必须**非递减**，否则 `DisplayDeviceConfig.loadBrightnessMap`
  丢掉整表 → `getBrightnessFromBacklight` NPE → `system_server` 崩溃重启、进不了 launcher；
- 平台 schema **不支持** HBM 内嵌 `screenBrightnessMap`（会被静默跳过），
  HBM 区间必须写进**顶层表**；
- `transitionPoint` = HBM off 时的亮度上限（= 高亮度模式起点）；
- `<value>` 是 HAL backlight 0..1 = 10bit DBV / 1023。

**建议做一个「亮度表」卡片**（放在显示调试，或独立模块）：

输入若干 `(DBV/HAL value, nits)` 采样点 →

1. 校验：value ∈ [0,1] 且**严格非递减**、nits 非递减、transitionPoint 在表内；
2. 自动把 HBM 区间并进顶层表，并按规则算 `transitionPoint`；
3. 生成可直接贴进 `display_id_*.xml` 的 `<screenBrightnessMap>` 片段；
4. 一键复制。

价值：把「屏体点不亮 / 开机循环重启」这类事故挡在 XML 生成阶段。
**工作量 4–6h**，其中校验规则是纯函数，好测。

### 5. Initcode Builder 增加「QCOM 数组」输出 + 逐包校验

现在有 4 种输出风格（byte / write / rxx / gen_wr），但没有 QCOM
`qcom,mdss-dsi-on-command` 真正要的数组格式：

```
每个包 = dtype + last + vc + ack(4B) + post_wait_ms(1B) + tx_len(2B 大端) + payload
包长必须 = 7 + tx_len
```

你们踩过的坑：多余字节在**数组末尾**会被静默丢弃（不报错），在**中间**会错位
→ `dsi_panel_get_cmd_pkt_count()` 返回 `-22` → `format error / commands failed, rc=-22`
→ 整条命令集 count=0，一条命令都不下发。

**建议**

- 新增输出风格「QCOM 数组」：直接生成 `0x39 0x00 0x00 ...` 加 7 字节头的完整数组；
- 再加一个「**校验已有数组**」入口：粘一段 QCOM 数组进来，逐包核
  `7 + tx_len` 是否成立、总长是否对齐，**指出第几个包错、差几个字节**。

价值：把 `rc=-22` 从"靠人肉数字节"变成"工具直接告诉你第几包少 2 个字节"。
**工作量 3–4h**。

### 6. 屏幕 DPI 反向查询

刚加的 DPI 只能正向算（分辨率 + 物理尺寸 → PPI）。实际选屏/评估时更常问反问题：

- 已知分辨率、想要 400 PPI → **需要多大对角线**？
- 已知对角线、想要某 PPI → **物理宽高是多少**？

**建议**：在现有「屏幕 DPI」行加一个「按目标 PPI 反算」模式，
输出所需对角线（inch）与物理宽高（mm）。纯函数扩展，**1–2h**。

---

## 四、P2：体验与清理

### 7. 6 个 porch 输入框的「压缩」是检查器误报

`t_hfp/hbp/hsw/vfp/vbp/vsw` 都 `setFixedWidth(48)`，而 `QSpinBox.minimumSizeHint()`
是 52，于是 `inspect_ui --flag` 永远报 6 个「压缩」——**从 1360 到 1920 都报**，
和窗口宽度无关。

两条路选一条：

- 把宽度提到 52（行宽 +24px，需要复核 1280 窗口下不出横向滚动条）；
- 或让 `inspect_ui` 对「显式 `setFixedWidth` 的控件」不计入压缩判定——
  这类控件是刻意定宽的，本来就不该按 `minimumSizeHint` 判。

> 副作用：不改的话 `--flag` 永远不可能输出 0，ReadMe 里「含标记控件 0 个即为正常」
> 这条标准就失去了意义。

### 8. 硬编码本机路径

```python
# shell_tools.py:20
DEFAULT_SCRCPY = r"D:\01_tools\scrcpy-win64-v2.6.1\scrcpy.exe"
DEFAULT_APK = r"D:\00_project\lcm_test_apk\Display-Tester_1.apk"
```

换一台机器就是失效路径（`func-list.md` 已标「待定」）。建议：首次运行按常见目录
探测一次，探测不到留空 + 提示，并在「设置」里暴露。可复用 `toolchain.py` 里
已有的 `_COMMON_DIRS` / `detect_platform_tools()` 那套写法。

### 9. `timing.DPI_SOURCES` 是死代码

定义了 4 个时钟源预设，但界面用的是自由 `QSpinBox`（tooltip 里写死 T820=384MHz）。
要么删掉，要么做成时钟源下拉（选平台自动填 MHz）。

---

## 五、P3：工程债（沿用上次结论，仍未处理）

| 项 | 说明 |
| --- | --- |
| 无 `requirements.txt` | 依赖只存在于本机 `.venv`；且 **Pillow 是打包的隐式依赖**（`main.ico` 实为 PNG，靠 Pillow 转换） |
| 无 CI | 11 项离线检查里有 10 项自带 offscreen，完全可跑 `windows-latest` |
| `run_checks.py` 写死 `.venv` 路径 | 新克隆执行会 `FileNotFoundError`；一行 `sys.executable` 兜底即可，也是开 CI 的前提 |
| `.gitignore` 缺 `~$*` | Excel 锁文件会一直显示为未跟踪 |
| `main.ico` 实为 PNG | 已核实 SHA256 与 `main.png` 完全相同 |

详见 [PROJECT_GAPS_ANALYSIS.md](PROJECT_GAPS_ANALYSIS.md)。

---

## 六、**不建议**加的东西（避免走回头路）

结合 `func-list.md` 里已确认的取舍，下面这些不建议再加回来：

| 项 | 为什么不做 |
| --- | --- |
| **异常守护**（ESD/DSI 超时实时盯屏） | 已明确"ESD 不做"；剩下的规则和「日志分析 + 现场包」重叠 |
| **电池调试** | 本阶段用不到，已下线；代码还在 `tools_battery.py` |
| **DCS 直接写节点 / ESD 重置按钮** | 屏体写入统一走 Shell Tools 自定义命令，页面不再摆第二份入口 |
| **Panel 参数查询 6 按钮** | 和 Ctrl+K 命令面板重复 |
| 任何「侧边栏快捷操作里已有」的按钮 | 你们定下的界面精简原则：侧边栏有 = 页面上不重复 |

新增功能时请同样遵守这条：**先看侧边栏和命令面板有没有，再决定放哪儿**。

---

## 七、建议排期

1. **本周**：P0-1（亮度量程）、P0-2（参数上限）、P0-3（进页面自动读）——
   都是小改动，直接修掉屏体调试主流程上的别扭。
2. **下一版**：P1-4（亮度表生成/校验）——收益最大，能挡开机崩溃事故。
3. **再下一版**：P1-5（QCOM 数组校验）、P1-6（DPI 反算）。
4. **顺手**：P2-7（检查器误报）、P2-8（路径探测）、P2-9（死代码）。
5. **有空**：P3 工程债，其中 `requirements.txt` + `run_checks.py` 兜底 + CI
   三件套做完，"换个人也能跑起来"这件事就闭环了。
