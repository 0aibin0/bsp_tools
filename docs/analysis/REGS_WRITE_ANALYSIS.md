# Initcode Builder 新增 REGS.WRITE 格式（改动分析）

版本基线：`v3.2.21` + 未发布改动
改动文件：`bsp_tools/initcode_builder.py`、`bsp_tools/ui_initcode_builder.py`、`bsp_tools/ui_initcode_builder.ui`、`devtools/check_initcode.py`

---

## 一、需求

一字板调试脚本里的写法要能直接转成 initcode：

```
REGS.WRITE(0,0x39,0x03,0x01) //01：VESA ON； 00：VESA OFF
REGS.WRITE(0,0x39,0x35,0x00) //TE ON
REGS.WRITE(0,0x39,0x70,0x11,0x00,0x00,0x89,0x30,…)   // DSC PPS
```

难点不在格式本身，而在**最后那条 DSC PPS 很长**：贴进输入框会被折行，
甚至把 `0x2A` 拆成 `0x2` + 换行 + `A`。

---

## 二、格式映射

```
REGS.WRITE(addr, dtype, payload…)
             │      │       └── 负载：第 1 字节是 DCS 命令，其余是参数
             │      └────────── 块类型，当 initcode 包头首字节，原样保留
             └───────────────── 寄存器/通道号，**丢弃**（不进 initcode）
```

实例：

```
REGS.WRITE(0,0x39,0x03,0x01)   →   0x39,0x00,0x00,0x02,0x03,0x01,
                                          ↑ 块类型  ↑长度  ↑命令 ↑参数
```

长度字节 = 1（命令）+ 参数个数，和 `to_dcs()` 的规则一致。

> 和 `mipi.write` 是同一类数据：行首带块类型，所以**必须保留原值**。
> 按负载长度重推会把 `0x29` 改成 `0x39`（语义就变了）。

---

## 三、两个关键处理

### 1. 语句可以跨行

一条语句从 `REGS.WRITE(` 到**配对的 `)`**，中间可以有换行。实现是先按行去掉
注释、拼回整段文本，再用括号配对扫描，而不是按行切。

- 注释（`//`）先剥掉，注释里的括号不会干扰配对；
- 语句没闭合（缺 `)`）时报「内容被截断了」，不会静默吞掉后面的数据。

### 2. 折行把数字劈开的也能拼回

DSC PPS 那种一百多字节的行，粘贴时会被强制折行，实测出现过：

```
…,0x2A,0xF4,0x2
A,0xF4,…
```

`0x2` 和 `A` 被换行劈开。参数切分前先把**空白全部去掉**再按逗号切，
`0x2` + `A` 自然拼回 `0x2A`；`,\n0x00` 这种也正常。

---

## 四、过滤规则（沿用项目既有约定）

| 输入 | 处理 |
| --- | --- |
| `REGS.WRITE(…)` 开头（大小写不敏感） | 解析 |
| 跨行的续行 | 属于同一条语句，一起解析 |
| 其他行（日志、裸字节、别的格式） | 丢弃，不报错 |
| `//` 注释 | 剥掉 |
| 参数不是 `0x00..0xff` | 报错并跳过该条 |
| 参数不足（addr + 块类型 + 至少 1 个负载字节） | 报错 |
| 缺少 `)` | 报错并停止 |
| 负载 > 255 字节 | 报错（长度字节表示不下） |

---

## 五、界面

「命令格式」新增第 6 个选项 **REGS.WRITE**（在 mipi.write 下面）。
选它之后 Build，右侧输出 initcode 字节行，格式提示显示条数：

```
当前格式: REGS.WRITE · 已生成 8 条 initcode
```

![REGS.WRITE 实际效果](../devtools/shots/initcode_regs_write.png)

---

## 六、测试

`devtools/check_initcode.py` 新增 [16] 一节，共 17 条断言（111 → **128 项**）：

```text
REGS.WRITE：解析出 8 条且无错误                  PASS
REGS.WRITE：首条 header 0x39 / cmd 0x03 / 参数 [0x01]  PASS
REGS.WRITE：首条字节行与手算一致                  PASS
REGS.WRITE：0x53 那条参数为 [0x28]                PASS
REGS.WRITE：PPS 是 0x39/0x70、负载 95 字节        PASS
REGS.WRITE：折行把 0x2A 拆成 0x2+A 也能拼回        PASS
REGS.WRITE：PPS 末尾 6 个 0x00                    PASS
REGS.WRITE：注释没被吃进 raw                      PASS
REGS.WRITE：第一个参数（通道号）被忽略             PASS
REGS.WRITE：非 REGS.WRITE 行被丢弃                PASS
REGS.WRITE：参数不足报错                          PASS
REGS.WRITE：缺少 ')' 报错                         PASS
REGS.WRITE：非十六进制参数报错                    PASS
REGS.WRITE：空输入不报错                          PASS
界面：REGS.WRITE 生成 8 行                        PASS
界面：首行与纯函数一致                            PASS
界面：格式提示报出条数                            PASS
```

完整离线自查 11 项全通过。

---

## 七、已知边界

- **块类型不做白名单校验**：`PACKET_TYPES` 里没收录的值会按 `kind_unknown`
  处理，但照样生成字节行（屏体侧可能出现表里没有的类型）。
- **只认逗号分隔**；没有逗号时退回按空白切（兼容别的写法习惯）。
- **第一个参数直接丢弃**，不做校验——它在本格式里是寄存器/通道号，
  和 initcode 无关；如果哪天它有意义，需要另开格式。
- 输出框里长行会**自动换行显示**，但复制出来仍是一整行（没有插入换行符）。
