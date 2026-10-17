# P1 / P2 / P3 全量实现（改动分析）

范围：3 个新功能 + 3 项体验清理 + 5 项工程债
改动文件：`bsp_tools/*`、`devtools/*`、`.github/`、仓库根
版本基线：`v3.2.19` + 未发布改动（未 bump 版本）

---

## 一、总览

| 级别 | 项 | 状态 |
| --- | --- | --- |
| P1-4 | 亮度表 `screenBrightnessMap` 生成 + 校验 | ✅ 新增模块 + 对话框 |
| P1-5 | Initcode Builder「QCOM 数组」输出 + 逐包校验 | ✅ 第 5 种输出风格 + 校验按钮 |
| P1-6 | 屏幕 DPI 反算（目标 PPI → 对角线 / 物理尺寸） | ✅ 第三种模式 |
| P2-7 | 6 个 porch 输入框被误报「压缩」 | ✅ 定宽 48 → 52 |
| P2-8 | 硬编码 scrcpy / APK 路径 | ✅ 自动探测 |
| P2-9 | `timing.DPI_SOURCES` 死代码 | ✅ 删除 |
| P3 | requirements / CI / `main.ico` / `.gitignore` / `run_checks` 兜底 | ✅ 5 项全做 |

---

## 二、P1-4 亮度表（`brightness_map.py` + `brightness_map_dialog.py`）

### 规则（照抄平台踩坑结论，不要放宽）

1. `<value>` 与 `<nits>` 必须**非递减**——有一处递减，`DisplayDeviceConfig.loadBrightnessMap`
   就丢弃整表 → `getBrightnessFromBacklight` NPE → `system_server` 崩溃重启；
2. 平台 schema **不支持** HBM 内嵌 `screenBrightnessMap`（静默跳过），HBM 必须并进**顶层表**；
3. `transitionPoint` = HBM **off** 时的亮度上限 = 最后一个非 HBM 点的 value；
4. `<value>` 是 HAL backlight 0..1 = 10bit DBV / 1023。

### 输入格式

```text
0.000000    1.000000
0.500000  120.000000
0.800000  800.000000
1.000000 1200.000000  HBM
```

### 校验项（`validate_points`）

| 检查 | 报错文案 |
| --- | --- |
| 点数 < 2 | 至少要 2 个采样点 |
| value 越界 | 超出 0..1（value 是 HAL backlight） |
| value 递减 | value 必须非递减，否则整张表会被丢弃 |
| nits 递减 | nits 必须非递减 |
| 同 value 不同 nits | 含义含糊 |
| HBM 不连续 / 不在末尾 | HBM 点必须连续且集中在末尾 |
| 全是 HBM | 缺少 HBM off 区间，算不出 transitionPoint |

### 输出

`to_xml()` 生成可直接贴进 `display_id_*.xml` 的 `<screenBrightnessMap>` 片段，
并单独给出 `transitionPoint = 0.800000（节点 818）` 的提示——**写到外层
`<highBrightnessMode>`，不要内嵌**。

### 入口

「显示调试 · 背光 / 亮度」卡片标题行右侧的 **亮度表…** 按钮，打开独立对话框
（左填右看，校验 / 生成 XML / 复制）。

> 为什么放标题行（`add_trailing`）而不是新加一行：先试过加行，背光卡高 39px →
> 整页 732 > 721 视口 → 结果网格又被 Qt 压扁。放标题行不占高度。

---

## 三、P1-5 QCOM 数组（`initcode_builder.py`）

### 包布局

```text
[0] dtype   [1] last   [2] vc   [3] ack   [4] post_wait_ms
[5..6] tx_len（大端）      [7..] payload
包长必须 = 7 + tx_len
```

### 新增

| 函数 | 作用 |
| --- | --- |
| `qcom_packet(entry, last)` | 一条 initcode → 一个 QCOM 包 |
| `format_qcom_array(entries)` | 整条数组（只有最后一包 `last=1`），一包一行、逗号分隔 |
| `parse_qcom_text(text)` | 把粘贴的数组扫成字节（认注释/逗号/裸十六进制） |
| `validate_qcom_array(values)` | 逐包校验，返回 `(包数, 问题列表)` |

输出风格从 4 种变 5 种（`STYLE_LABELS` 加了「QCOM 数组」），反向解析区下拉即可选。
控制行新增 **校验 QCOM** 按钮：把输入当数组逐包核 `7 + tx_len`，报出
「第 N 包声明 tx_len=X，实际只剩 Y 字节，差 Z 字节」——直接对上 `rc=-22` 那个坑。

---

## 四、P1-6 DPI 反算（`tools_display.py`）

`screen_size_for_ppi(width, height, target_ppi)`：由 `对角线 = 对角线像素 ÷ 目标 PPI`
复用 `screen_dpi()` 反推物理尺寸。

「屏幕 DPI」行新增第三种模式 **目标 PPI**：

| 模式 | 输入 | 输出 |
| --- | --- | --- |
| 对角线 (in) | 6.40 in | 411.2 dpi · 点距 0.0618 mm · 6.40 in |
| 宽 × 高 (mm) | 68.0 × 151.0 mm | 403.7 dpi · 点距 0.0629 mm · 6.52 in |
| **目标 PPI** | 400 ppi | 需对角线 6.58 in · 物理 68.6×152.4 mm |

---

## 五、P2

| 项 | 处理 |
| --- | --- |
| **7. porch 输入框误报** | 定宽 48 提到 **52**（等于 `QSpinBox.minimumSizeHint()`）。`inspect_ui --flag` 不再报这 6 个，卡最小宽度 +24px（653 → 683），1360 视口仍放得下 |
| **8. 硬编码路径** | 新增 `detect_scrcpy()` / `detect_apk()`：配置 → 已知位置 → 常见目录扫描 → **空串**。换机器不再指向不存在的路径 |
| **9. 死代码** | 删除 `timing.DPI_SOURCES`（界面早改成自由输入，没人引用） |

---

## 六、P3 工程债

| 项 | 处理 |
| --- | --- |
| **requirements.txt** | 只有 `PyQt5==5.15.10`（原来依赖只存在于本机 `.venv`） |
| **requirements-dev.txt** | `-r requirements.txt` + `pyinstaller==6.11.1` + `pyqt5-tools` + `Pillow` |
| **run_checks 路径兜底** | `.venv` 不存在时退回 `sys.executable`，新克隆不再 `FileNotFoundError`（也是开 CI 的前提） |
| **main.ico** | 用 Pillow 从 `main.png` 生成**真 ICO**（头 `00 00 01 00`，16/24/32/48/64/128 六档）。PyInstaller 不再隐式依赖 Pillow |
| **.gitignore** | 补 `~$*`（Excel 锁文件）和 `.claude/`（本机绝对路径） |
| **CI** | `.github/workflows/checks.yml`：`windows-latest` + Python 3.11 + `pip install -r requirements.txt` + `python run_checks.py` |

---

## 七、测试

| 检查 | 结果 |
| --- | --- |
| `selftest.py` | 257 → **279 项**（+22：DPI 反算 6、亮度表 13、对话框 3） |
| `check_initcode.py` | 100 → **111 项**（+11：QCOM 包结构 / 大端 / last 位 / 逐包校验 / 界面） |
| `check_layout.py` | 5 种窗口尺寸全部 OK |
| `run_checks.py` | **11 项离线检查全通过** |

额外实测（1360x840 默认窗口）：页面 715 ≤ 721 视口，**无纵向滚动条**、
结果标签 17px 未被压扁、6 个 porch 输入框宽度达标。

---

## 八、需要注意的变化

1. **QCOM 输出是新增的 5 种风格之一**，原来 4 种风格的产物不变。
2. **`main.ico` 换成了真 ICO**：exe 图标视觉不变（同一张 PNG 转的），但文件变了。
3. **`.claude/` 现在被忽略**：之前靠机器级全局 ignore，换机器会误提交。
4. **CI 只在 push 到 main / PR 时跑**，跑不了 4 项真机检查（需要连板子）。
5. 亮度表**只生成 XML 片段**，不写文件、不下发——落盘/刷机仍走你们原有流程。

---

## 九、没做的

- 没有 bump 版本、没有重新打包、没有提交（等你确认后按发版流程走）。
- `docs/功能清单.md` 仍是 v3.2.0 的旧稿，属于历史文档，本次未动。
