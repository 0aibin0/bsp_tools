# Initcode Builder · mipi.write 格式支持（改动分析）

改动对象：`bsp_tools/initcode_builder.py`、`bsp_tools/ui_initcode_builder.py`、`bsp_tools/ui_initcode_builder.ui`
测试：`devtools/check_initcode.py`
版本基线：`v3.2.17` → 随 **v3.2.18** 发布

---

## 一、需求

现有 Initcode Builder 有 4 种输入格式（WriteAddr / Write(Command) / Rxx / GEN_WR），
都要求输入已经是「按写命令分组」的结构。屏体 spec 和驱动日志里更常见的写法是
`mipi.write` 一行一条，希望直接粘进来就能转成 initcode。

样例（T820 屏体点亮序列，10 条）：

```text
mipi.write 0x39 0xD7 0x10 0x0C 0x36 0x19 0x90 0x90
mipi.write 0x39 0xA3 0x40 0x03 0x80 0xFF 0x04 ...
mipi.write 0x29 0x75 0x03 0x04
```

---

## 二、格式映射规则

initcode 的单元是「3 字节包头 + 1 字节长度 + N 字节负载」（见 `initcode_builder` 模块注释）。
`mipi.write` 与它是一行对一条，映射关系：

| initcode 位置 | 取自 mipi.write 的 | 说明 |
| --- | --- | --- |
| 包头第 1 字节 | 行首那个字节（`0x39` / `0x29` / …） | **块类型**，原样保留 |
| 包头第 2、3 字节 | 常量 | 填充位，沿用老规矩（1 字节负载写 `0x78,0x00`，其余 `0x00,0x00`） |
| 长度字节 | 负载字节数 = 1 + 参数个数 | |
| 负载第 1 字节 | 负载的第 1 个字节 | DCS 命令 |
| 负载其余字节 | 负载剩余字节 | 参数 |

实例：

```text
mipi.write 0x39 0xD7 0x10 0x0C 0x36 0x19 0x90 0x90
→ 0x39,0x00,0x00,0x07,0xd7,0x10,0x0c,0x36,0x19,0x90,0x90,
     ↑ 块类型   ↑长度  └────── 7 个负载字节 ──────┘
```

> 长度 7 = 1 个命令（`0xD7`）+ 6 个参数。

---

## 三、关键设计：必须保留块类型，不能按长度重推

这是本次最重要的一个决定，也是会踩坑的地方。

原 `to_dcs()` 是**按负载长度反推包头**的：

```python
if count <= 1:   prefix = 0x05, 0x78, 0x00
elif count == 2: prefix = 0x15, 0x00, 0x00
else:            prefix = 0x39, 0x00, 0x00
```

这套规则对「正向 4 种格式」是对的（那些格式本来就不带块类型信息），
但用到 `mipi.write` 上会出错：**`0x29`（Generic long write）和 `0x39`（DCS long write）
的负载长度可以完全一样**，按长度重推会把 `0x29` 悄悄改写成 `0x39`。
块类型是包里真实下发的 DSI 数据类型，改了就是改了屏体收到的指令。

所以 `to_dcs()` 改成**优先用条目自带的 `header`**，只有拿不到 header
（例如直接传一个三元组）时才退回按长度推断：

```python
header = getattr(entry, "header", 0) or 0
if not header:
    header = 0x05 if count <= 1 else (0x15 if count == 2 else 0x39)
```

这样样例里那条 `mipi.write 0x29 0x75 0x03 0x04` 会稳定产出：

```text
0x29,0x00,0x00,0x03,0x75,0x03,0x04,
```

而不是 `0x39,...`。已有 4 种正向格式的产物不受影响（它们的 header 本来就等于按长度推出的值）。

---

## 四、改动清单

| 文件 | 改动 |
| --- | --- |
| `bsp_tools/initcode_builder.py` | 新增 `_MIPI_WRITE_RE`、`parse_mipi_write()`、`initcodebuilder_5()`；`to_dcs()` 改为保留 header；`__init__` 与 `select_command()` 接入 `radioButton_5` |
| `bsp_tools/ui_initcode_builder.py` | 命令格式组新增 `radioButton_5`（第 7 行），spacer 下移到第 8 行；`retranslateUi` 补文案 |
| `bsp_tools/ui_initcode_builder.ui` | 同步 Designer 源文件，避免重新生成时丢失按钮 |
| `devtools/check_initcode.py` | 新增 [9]~[13] 五节共 33 条断言，含真实 10 条样本 |
| `func-list.md` / `docs/功能清单.md` | 功能描述从「4 种格式」更新为 5 种 |
| `README.md` / `bsp_tools/ReadMe.md` | 页面说明补上 mipi.write |

---

## 五、容错与报错行为

原则与原有反向解析一致：**不抛异常、不静默丢数据**，能认的行照样生成。

| 输入情况 | 行为 |
| --- | --- |
| 空行、`//` 行注释、`/* */` 块注释 | 跳过（复用 `_strip_comments`） |
| `MIPI.WRITE` / `mipi_write` / 无前缀 `0x39 0xD7 …` | 都认 |
| 逗号 / 空格 / 制表符混用、大写 `0X` | 都认（复用 `_scan_line`） |
| 行首只有块类型、没有负载 | 报错「只有块类型 0x39，后面没有 DCS 命令」，该行跳过 |
| 整行没有十六进制字节 | 报错「没有识别到十六进制字节」，该行跳过 |
| 负载 > 255 字节 | 报错（长度字节表示不下），该行跳过 |
| 块类型与负载长度不匹配（如 `0x05` 给 3 字节） | **报错但仍生成条目**，因为数据本身完整，只是块类型可疑 |
| 全部行都有问题 | 输出框为空，格式提示里显示第一条原因，界面不崩 |

问题条数会显示在「格式提示」标签里，例如：

```text
当前格式: mipi.write · 已生成 10 条 initcode
```

---

## 六、测试覆盖

`devtools/check_initcode.py` 新增 5 节（原编号从 [8] 直接跳到 [10]，这次把 [9] 补上了）：

| 节 | 覆盖内容 |
| --- | --- |
| [9] | 真实 10 条样本：条数、首条字节行手算比对、`0xD7` + 6 参数、`0x29` 未被改写、长度字节 = 1 + 参数数 |
| [10] | 往返：生成 → 反向解析 → 命令 / 参数 / **块类型**逐条一致 |
| [11] | 容错：注释、空行、逗号、无前缀、大写前缀、下划线写法；注释里的字节不被吃进来 |
| [12] | 异常：只有块类型 / 只有前缀 / 裸文字 / 块类型与长度不匹配；不抛异常且信息可读 |
| [13] | 界面：选格式 → Build → 输出 10 行；全部行报错时不崩；空输入不崩 |

运行结果：

```text
全部通过（91 项检查）
```

完整离线自查（`run_checks.py`）11 项全通过，`check_layout.py` 在
1280x800 / 1360x840 / 1440x900 / 1920x1080 下均无重叠与裁切，
`inspect_ui.py --flag` 下 Initcode Builder 页面零标记控件。

---

## 七、用法

1. 打开 **Initcode Builder** 页
2. 右侧「命令格式」选 **mipi.write**
3. 左侧粘贴 `mipi.write ...` 行（一行一条）
4. 点 **Build** → 右侧得到 initcode 字节行
5. 需要 `Write(Command)` / `Rxx` / `GEN_WR` 风格时，把生成的字节行粘到下方
   「反向解析」的输入框，选对应输出格式即可

---

## 八、已知边界

- **只做正向转换**（mipi.write → initcode），没有把 mipi.write 加进下方「反向解析」的输入探测。
  反向解析是按「3+1+N」的字节流消费的，与 mipi.write 的行式语法不同，混在一起需要额外的
  格式判定；当前用「先正向生成、再喂给反向解析」的组合已经能拿到 4 种输出风格。
- 行首块类型不做白名单校验：`PACKET_TYPES` 里没有的类型会按 `KIND_UNKNOWN` 处理，
  但**照样生成字节行**（不拦），因为屏体侧可能出现本表未收录的类型。
- 未改 `APP_VERSION`，发版时按原流程一起走。
