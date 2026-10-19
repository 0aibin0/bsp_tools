# Initcode 包头规则统一（改动分析）

版本基线：`v3.2.22` + 未发布改动
改动文件：`bsp_tools/initcode_builder.py`、`devtools/check_initcode.py`

---

## 一、需求

> 保证 1 个参数的开头是 0x05，2 个参数的开头是 0x15，3 个及以上开头的是 0x39。

**口径确认**：「参数」= **负载字节数**（含 DCS 命令字节本身）。

| 负载字节数 | 包头 |
| --- | --- |
| 1（只有命令） | `0x05` |
| 2（命令 + 1 个参数） | `0x15` |
| ≥ 3 | `0x39` |

---

## 二、发现的问题

检查发现，**两条输出路径违背了这条规则**：

| 输出路径 | 改之前 | 符合吗 |
| --- | --- | --- |
| WriteAddr / Write(Command) / Rxx / GEN_WR | 按长度推 | ✅ |
| **mipi.write / REGS.WRITE**（`to_dcs()`） | **保留原始块类型**（`0x29` 原样输出） | ❌ |
| **QCOM 数组**（`qcom_packet()`） | **dtype 取原始 header** | ❌ |

后两条是 v3.2.18 ~ v3.2.22 期间**刻意反着做**的，当时的理由是
「`0x29`（Generic long write）和 `0x39`（DCS long write）语义不同，
按长度重推会改掉下发到屏体的指令」。

现在按你的要求改成**统一按长度推导**，六种输入格式 + QCOM 输出的口径完全一致。

---

## 三、改法

### 1. 抽出唯一口径函数

```python
def block_header(payload_count):
    """负载 1 → 0x05 ； 2 → 0x15 ； ≥3 → 0x39"""
    count = int(payload_count)
    if count <= 1:
        return 0x05
    if count == 2:
        return 0x15
    return 0x39

def header_filler(payload_count):
    """包头后两个填充字节：1 字节负载 0x78,0x00，其余 0x00,0x00"""
    return (0x78, 0x00) if int(payload_count) <= 1 else (0x00, 0x00)
```

### 2. 三处输出全部改走它

| 函数 | 影响范围 |
| --- | --- |
| `_initcode_row()` | WriteAddr / Write(Command) / Rxx / GEN_WR |
| `to_dcs()` | mipi.write / REGS.WRITE（**不再读 `entry.header`**） |
| `qcom_packet()` | QCOM 数组的 dtype |

`entry.header` 仍然保留在解析结果里（清单区还会显示「原始包类型」），
但**不再影响输出**。

---

## 四、行为变化（重要）

**输入里的块类型不再透传**，只作为参考。具体表现：

| 输入 | 改之前 | 改之后 |
| --- | --- | --- |
| `REGS.WRITE(0,0x39,0x03,0x01)` | `0x39,0x00,0x00,0x02,0x03,0x01,` | **`0x15,0x00,0x00,0x02,0x03,0x01,`** |
| `mipi.write 0x29 0x75 0x03 0x04` | `0x29,0x00,0x00,0x03,0x75,0x03,0x04,` | **`0x39,0x00,0x00,0x03,0x75,0x03,0x04,`** |
| `mipi.write 0x39 0xE9 0x33 0x7F …`（10 字节负载） | `0x39,…` | `0x39,…`（不变） |
| QCOM 数组 dtype | 跟随原始 header | 跟随负载长度 |

> **注意**：如果你有屏体依赖 `0x29` / `0x39` 的区分（Generic vs DCS long write），
> 这次改动会把它抹平。需要区分的话要另开一个「保留原类型」的输出模式。

---

## 五、验证

用探针把六种格式 × 三种负载长度全跑了一遍（共 19 个用例）：

```
WriteAddr 1 字节负载        0x05,0x78,0x00,0x01,0x03,     0x05
WriteAddr 2 字节负载        0x15,0x00,0x00,0x02,0x03,0x   0x15
WriteAddr 3 字节负载        0x39,0x00,0x00,0x03,0x03,0x   0x39
Write(Command) 1/2/4      0x05 / 0x15 / 0x39             ✓
Rxx 1/2/3                 0x05 / 0x15 / 0x39             ✓
GEN_WR 1/2/5              0x05 / 0x15 / 0x39             ✓
mipi.write 1 字节(输入0x39)  0x05,0x78,0x00,0x01,0x03,     0x05
mipi.write 2 字节(输入0x39)  0x15,0x00,0x00,0x02,0x03,0x   0x15
mipi.write 3 字节(输入0x29)  0x39,0x00,0x00,0x03,0x03,0x   0x39
REGS.WRITE 1 字节          0x05,0x78,0x00,0x01,0x03,     0x05
REGS.WRITE 2 字节          0x15,0x00,0x00,0x02,0x03,0x   0x15
REGS.WRITE 3 字节(输入0x29) 0x39,0x00,0x00,0x03,0x03,0x   0x39
REGS.WRITE 长 PPS(输入0x29) 0x39,0x00,0x00,0x04,0x70,0x   0x39

QCOM dtype: 3 字节 → 0x39 ✓ ； 1 字节 → 0x05 ✓
全部符合规则 ✓
```

测试协同更新：

| 断言 | 变化 |
| --- | --- |
| `真实样本：块类型 0x29 未被改写成 0x39` | → `原文 0x29 那条按长度重推为 0x39` |
| `真实样本：其余 9 条仍是 0x39` | → `全部 10 条包头都符合长度规则` |
| `往返：每条命令/参数/块类型都一致` | → 拆成「命令/参数一致」+「往返后包头仍符合规则」 |
| `REGS.WRITE：首条 header 0x39` | → `首条…包头重推为 0x15` |

`check_initcode.py` 128 → **130 项**，完整离线自查 11 项全通过。

---

## 六、未做

- 没有 bump 版本、没有重新打包、没有提交（等你确认）。
- 没有增加「保留原包类型」的开关——如果你需要这种模式，需要另说。
