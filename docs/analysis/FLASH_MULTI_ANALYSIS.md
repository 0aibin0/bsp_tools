# fastboot 多分区批量烧录（改动分析）

日期：2026-10-23 · 基线 `v3.2.29`

---

## 一、需求

> 每次都会刷入两个不同的分区。现在工具只能先刷一个分区、再去选另一个，
> 不如直接用命令行方便。

原来的 `fastboot flash` 卡只有**一组**「分区 + 镜像」控件，逻辑在
`shell_tools.on_flash()`：先 `format erase` 再 `format flash`，一次只能一个。

---

## 二、方案选择

| 方案 | 取舍 |
| --- | --- |
| 加「烧录列表」表格 | 最直观，但要重排整卡布局，占空间多 |
| 点 Flash 时弹窗选多个文件 | 不改主界面，但每次都要弹窗 |
| **加多行输入框（选用）** | 改动小；能直接粘 `fastboot` 命令；命令行习惯直接复用 |

用户选择：**多行输入框** + **erase 开关（默认不擦）**。

---

## 三、界面

`fastboot flash` 卡新增一行：

```
[批量…]  [ ] 先 erase
┌──────────────────────────────────────────────┐
│ 批量烧录：一行一个分区和镜像，可直接粘 fastboot 命令   │
│ boot boot.img                                │
│ dtbo dtbo.img                                │
└──────────────────────────────────────────────┘
[Flash]        [bootloader]        [reboot]
```

- **默认收起**（`setVisible(False)`），点「批量…」展开，不占常驻空间
- 展开后按钮文案变「收起」
- `erase` 复选框默认**不勾**

### 为什么默认不 erase

原来是「每条先 `fastboot erase` 再 `fastboot flash`」。这对 `boot` / `dtbo`
这类分区有风险：**erase 成功但 flash 失败**，设备就起不来了。

`fastboot flash` 本身是覆盖写，绝大多数场景不需要先擦。所以改成默认不擦，
需要时勾上。

---

## 四、输入格式

每行一个「分区 镜像」，三种写法都认：

```
boot boot.img                                 # 最简
dtbo  D:\images\dtbo.img                      # 绝对路径
fastboot flash vendor vendor.img              # 直接粘命令行
boot "D:\my images\boot.img"                  # 路径带空格，用引号
```

解析规则（`ShellToolsPage.parse_flash_lines`）：

- 去掉行尾 `# 注释`、跳过空行
- 去掉可能带的 `fastboot` / `flash` 前缀
- 按空白切分，**尊重引号**（`_split_flash_tokens`）
- 少于 2 个字段的行丢弃

---

## 五、两条安全改进

### 5.1 镜像不存在时先拦下

```python
missing = [img for _p, img in entries if not os.path.exists(img)]
if missing:
    QMessageBox.warning(self, "文件不存在", ...)
    return
```

否则要多等好几轮 fastboot 报错才发现路径写错了。

### 5.2 失败即停（改的是 `_exec_chain`）

**这是本次最关键的改动。** 原实现无论命令成功失败都会继续执行队列里的下一条：

```python
def on_done(exit_code, output):
    self._commands_output.append((cmd, output))
    self._run_next_in_chain()      # ← 失败也继续
```

单分区时顶多多刷一条无害的 `flash`，但**多分区时意味着第一个分区烧失败后，
后面的分区照样往下刷**——可能把设备刷成半残状态。

改法：记录第一个失败命令，后续队列直接不再执行，并在日志里明确说明：

```
执行命令: fastboot flash boot "boot.img"
结果:
...
----------------------------------------
已停止：`fastboot flash boot "boot.img"` 失败（exit≠0）
剩下 3 条命令没有执行。
```

这个改动同样惠及截图导出那条链（`caps`）——中途失败不再继续。

---

## 六、验证

`selftest` 304 → **315 项**，新增 `[18b]` 一节：

```text
批量输入框默认收起                       PASS
erase 开关默认不勾                       PASS
批量解析：一行一个分区                    PASS
批量解析：能直接粘 fastboot 命令           PASS
批量解析：带空格路径用引号                 PASS
批量解析：跳过注释与空行                   PASS
批量解析：缺镜像的行被丢弃                 PASS
多分区提示里列出全部分区                   PASS
勾选 erase 后每条先擦再写                  PASS
镜像不存在时不执行命令                     PASS
```

其它验证：

| 项 | 结果 |
| --- | --- |
| 离线自查 11 项 | 全部通过 |
| `check_layout` 5 种尺寸 | 全部 OK（批量框收起时不占空间） |

---

## 七、已知边界

- **顺序执行**：多分区是串行刷，不是并行。fastboot 本身也不支持并发刷同一台设备。
- **不校验分区是否存在**：分区名写错会由 fastboot 自己报错（`FAILED (remote: 'Partition not found')`），失败即停会拦住后续。
- **两行固定**：用户确认先只做两行，之后有需要再加。
- **erase 开关对单行/两行一致**：都走 `_flash_many`。

---

## 八、方案变更记录：批量输入框 → 两行选择框

### 8.1 第一版：多行输入框

最初按「一行一个分区+镜像」的多行输入框实现，支持：

```
boot boot.img
dtbo dtbo.img
fastboot flash vendor vendor.img     # 直接粘命令行
boot "D:\my images\boot.img"         # 路径带空格用引号
```

### 8.2 为什么改掉

用户实测提出：**改成两行固定选择框更直观**。原因是

- 多行输入框要手打/粘贴路径，而路径很长（实测是
  `\\10.71.255.189\yxb_sdc1\tjt\VENDOR\bsp\out\androidt\gk5_native_k515\dist\lk\lk-sign.bin`
  这种 UNC 路径），手打不现实；
- 而「浏览」按钮选文件才是日常操作方式。

所以改为**两行独立的「分区 + 镜像 + 浏览」**，保留 `_flash_many(entries)` 作为
统一执行入口（失败即停、预检查镜像那套逻辑不变）。

### 8.3 新增的两个开关

| 开关 | 默认 | 作用 |
| --- | --- | --- |
| 先 erase | 不勾 | 每条命令前插 `fastboot erase` |
| 跳过未填的行 | 勾选 | 只填一半的行忽略而不报错 |

### 8.4 两行等宽对齐问题

改完发现两行长度不一致，量出来的数据：

| 行 | 分区框宽 | 镜像框起点 |
| --- | --- | --- |
| 第 1 行 | 123 px | 150 |
| 第 2 行 | 177 px | 204 |

**根因**：两行的 `QComboBox` 占位文字长短不同——

```python
row1.setPlaceholderText("分区")                    # 123px
row2.setPlaceholderText("分区（可选，留空不刷）")   # 177px
```

`QComboBox.sizeHint()` 会把占位文字算进去，两个框各自按自己内容定宽。

**修法**：

1. `partition.setFixedWidth(128)` —— 两行用同一个固定值
2. 两行统一用 `"分区"` 占位，提示信息移到 tooltip

对齐后：

```
第1行: 分区 x= 22 宽=128 | 镜像 x=155 宽=606 | 浏览 x=766 | 右端=812
第2行: 分区 x= 22 宽=128 | 镜像 x=155 宽=606 | 浏览 x=766 | 右端=812
```

顺手加了三条防退化断言（分区框等宽 / 镜像框起点与宽度一致 / 浏览按钮位置一致）。

### 8.5 顺带修掉的布尔配置 bug

加「先 erase」开关时踩到一个真 bug：

```python
self.flash_erase.setChecked(config.get_bool('flash_erase', False))   # 正确
self.flash_erase.setChecked(bool(config.get('flash_erase', False)))  # 错误
```

`app_config.get()` 最后一行是 `return str(value)`，所以存进去的 `False`
读出来是字符串 `'False'`，而 **`bool('False')` 是 `True`** ——
勾选状态永远存不回去，下次打开永远是勾选的。

改用 `get_bool()`（它能识别 `'false'`/`'0'`/`'no'`/`'off'`）。

> 这是个模式性陷阱：任何 `bool(config.get(...))` 都是错的，
> 应该用 `config.get_bool(...)`。本次只修了 flash 这一处。

### 8.6 最终测试

`selftest` 304 → **320 项**：

```text
有两行分区选择框                        PASS
两行的分区框互不相同                     PASS
两行分区框等宽                          PASS
两行镜像框起点与宽度一致                 PASS
两行浏览按钮位置一致                     PASS
erase 开关的读回用 get_bool              PASS
跳过未填的行默认勾选                     PASS
两行都填：读到两条                       PASS
两行都填：没有半填的行                   PASS
第二行留空：只刷第一行                   PASS
第二行留空：不算半填                     PASS
只填分区算半填                           PASS
默认不擦除：只有 flash 命令              PASS
多分区提示里列出全部分区                 PASS
勾选 erase 后先擦再写                    PASS
镜像不存在时不执行命令                   PASS
```

离线自查 11 项全通过；`check_layout` 5 种尺寸全 OK。

---

## 九、第三轮调整：改用勾选框（v3.2.33）

### 9.1 用户反馈

> 改成在前面增加一个框选，如果勾选了，就刷这个分区，没勾选就不刷。
> 就可以去除跳过未填的行的选项。

原来的判定逻辑是「这行填没填」：

```python
if not partition and not image:
    continue                      # 整行空着就不刷
if partition and image:
    entries.append(...)
else:
    half_filled.append(...)       # 只填一半 → 靠「跳过未填的行」决定
```

问题：**「想刷」和「填了」是两件事**。想暂时跳过某一行但保留填好的内容时，
只能把内容清掉；下次要用又得重新选文件。

### 9.2 改法

每行前面加一个勾选框，判定改成「勾没勾」：

```
☑ [uboot_a ▾] [\\10.71.255.189\...\lk-sign.bin] [📁]
☐ [dtbo_a  ▾] [\\10.71.255.189\...\dtbo.img   ] [📁]
```

```python
def _checked_flash_rows(self):
    for index, row in enumerate(self.flash_rows, 1):
        if not row["check"].isChecked():
            continue                      # ← 只看勾选，不看填没填
        ...
        else:
            incomplete.append("第 {} 行缺{}".format(index, "、".join(missing)))
```

| 操作 | 结果 |
| --- | --- |
| 勾选 | 参与烧录 |
| 取消勾选 | 跳过，**内容保留** |
| 勾了但没填全 | 报错「第 N 行缺镜像」，不静默跳过 |
| 全都不勾 | 提示「请先勾选要烧录的分区」 |

**移除 `flash_skip_missing`**：勾选框的语义已经完全覆盖它。

### 9.3 对齐

新增勾选框这一列后，两行仍然完全对齐（勾选框也给固定宽度 22）：

```
第1行: 勾选 x=22 | 分区 x=49 w=128 | 镜像 x=182 w=579 | 浏览 x=766 | 右端=812
第2行: 勾选 x=22 | 分区 x=49 w=128 | 镜像 x=182 w=579 | 浏览 x=766 | 右端=812
```

### 9.4 又一个测试顺序依赖

断言「第二行默认不勾」在 CI 里失败——因为配置文件里存着**上一次测试留下的**
`flash_check_2 = 'True'`，读回后自然不是默认值。

这和第八节那个 `bool('False')` 是同一类坑：**要区分「默认值」和「用户保存值」**。

改法：断言从「默认不勾」改成「控件状态与配置读回一致」：

```python
check("第二行勾选状态与配置一致",
      shell.flash_rows[1]["check"].isChecked()
      == app_config.config().get_bool("flash_check_2", False), ...)
```

### 9.5 测试

`selftest` 330 → **336 项**：

```text
每行前面都有勾选框                PASS
第一行勾选状态与配置一致           PASS
第二行勾选状态与配置一致           PASS
「跳过未填的行」已移除             PASS
两行都勾：读到两条                PASS
两行都勾：没有不完整的行           PASS
第二行取消勾选：只刷第一行          PASS
取消勾选不算不完整                PASS
取消勾选后内容仍保留              PASS
勾选但缺镜像算不完整              PASS
不完整的提示能指明第几行缺什么      PASS
两行都不勾：没有可烧录的行          PASS
```
