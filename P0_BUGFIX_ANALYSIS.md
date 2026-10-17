# P0 三个 bug 修复（改动分析）

修复对象：`bsp_tools/tools_display.py`、`bsp_tools/command_runner.py`
测试：`devtools/selftest.py`
版本基线：`v3.2.19` + 未发布改动

---

## 一、修了什么

| # | 问题 | 影响 |
| --- | --- | --- |
| 1 | 「写节点」亮度量程与 `max_brightness` 不匹配 | 屏体调到不满亮，只能到 1/4 |
| 2 | DCS 包构造参数上限差一 | 254+1 边界会生成 `0x100` 这种非法长度字节 |
| 3 | 进页面不读设备状态 | 每次都要手动点「读取」 |

---

## 二、亮度量程（问题 1）

### 证据

```python
self.bright_slider.setRange(0, 255)                 # 老代码
self.runner.run(_write_all("brightness", value))    # 直接写进 sysfs
```

两条路径的量程**不一样**，以前共用了一个 0..255 的输入框：

| 路径 | 量程 |
| --- | --- |
| `settings put system screen_brightness`（框架） | 0..255（Android 默认） |
| `/sys/class/backlight/<node>/brightness`（节点） | 0..`max_brightness`，T820 是 **1023**（10bit DBV） |

按「节点值 = HAL value × 1023」的口径，节点 818 = 80% 亮度。老代码滑块拉到底
只写 255，**等于 25%**，屏体根本到不了满亮。

### 改法

1. **滑块改成节点量程**：默认 `NODE_MAX_DEFAULT = 1023`，进页面读到
   `max_brightness` 后按实际值覆盖（`_apply_node_max()` 按百分比迁移位置）。
2. **「设置」自动折算**：`framework = round(节点值 / node_max × 255)`。
3. **加一行量程提示**（单行、不换行）：`818/1023 · 80% · 框架 204`。
4. **`max_brightness` 改成每次都读**（原来只在勾选时读）——量程要靠它对，
   不能靠用户记得勾。复选框改成只控制 `actual_brightness`，文案
   「读 max/actual」→「读 actual」。

### ⚠️ 行为变化（需要注意）

**输入框的语义从「框架值 0..255」变成了「节点值 0..max_brightness」。**

- 以前填 180 → 框架 180；
- 现在填 180 → 节点 180（≈17.6%）→ 框架 45。

这是有意的：屏体调试要填的是真实 DBV 值（818、900 这种），0..255 表达不了。
「设置」按钮已经自动折算，不需要用户自己换算。旧断言
`screen_brightness 180` 已改成 `screen_brightness 45` 并注明原因。

---

## 三、DCS 参数上限（问题 2）

### 证据

```python
if len(params) > 0xFF:          # 允许 255 个参数
    ...
# timing.py
payload = [command] + params    # 1 + 255 = 256
return prefix + [count] + payload
```

`count = 256` 后 `"0x{:02x}".format(256)` 产出 **`0x100`**（三位十六进制），
整条序列不可用。而提示文案写的是「长包负载最长 255 字节」。

### 改法

```python
if len(params) > 0xFE:          # 1 个命令 + 254 个参数 = 255 字节负载
```

并加了两条边界断言：254 通过（长度字节 `0xff`、总长 259）/ 255 拒绝。

---

## 四、进页面自动读（问题 3）

### 改法

`on_page_shown()` 从「只 setFocus」改成再调 `refresh_from_device(quiet=True)`，
静默读三条：`max_brightness`、`brightness`、`wm size`。

`wm size` 的结果会填进「分辨率」下拉框（优先 `Override`，其次 `Physical`）。

### 配套：`CommandRunner.run()` 新增 `quiet` 参数

自动读不能刷屏、也不该弹一堆 toast，所以给执行器加了一个开关：

```python
def run(self, command, label=None, echo=True, on_result=None, quiet=False):
    """quiet: 不写结果面板、不弹完成/失败提示，只把结果交给 on_result。"""
```

- `quiet=True`：跳过 `panel.append_command / set_running`，也不连 `_on_done`
  （`_on_done` 里既写面板又发 toast）
- 兼容：默认 `False`，所有既有调用不受影响

---

## 五、测试

`devtools/selftest.py` 243 → **257 项**，新增 14 条：

```text
背光设置把节点值折算成框架值            PASS   (180 → 45)
亮度滑块按节点量程（默认 1023）          PASS
节点 818 → 框架 204                     PASS
框架 204 → 节点 818                     PASS
节点 818 ≈ 79.96%                       PASS
量程提示显示 节点/百分比/框架             PASS
_last_int 取最后一行纯整数               PASS
_last_int 全是错误行时返回 None          PASS
读到 max_brightness 后滑块上限跟着变     PASS   (1023 → 4095)
改量程后提示同步                         PASS
254 个参数能生成（负载正好 255 字节）     PASS
255 个参数被拒（长度字节会溢出）         PASS
进页面自动读三条（max/brightness/wm size） PASS
自动读走 quiet（不刷面板、不弹 toast）    PASS
```

| 检查 | 结果 |
| --- | --- |
| `selftest.py` | **257 项全通过** |
| `check_layout.py` | 5 种尺寸全部 OK（新增的提示标签没有撑宽卡片） |
| `run_checks.py` | **11 项离线检查全通过** |

---

## 六、风险与回归点

| 点 | 说明 |
| --- | --- |
| 输入框语义变了 | 见第二节 ⚠️。老用户若习惯填 0..255，现在会偏暗；提示行里的百分比能立刻看出来 |
| `max_brightness` 读不到 | 保持默认 1023（T820 口径）。若平台是 255/4095，进页面读到后会自动更正 |
| 自动读会跑 3 条 adb | 每次切到「显示调试」模块都会跑，都是只读命令；`quiet` 保证不刷面板、不弹 toast |
| 无设备时 | 三条命令失败，`_last_int` 拿不到数字 → 量程和读数都不变，界面不报错 |

---

## 七、没做的（按你选的范围，先不动）

- **P1 三个新功能**：亮度表生成/校验、QCOM 数组输出与逐包校验、DPI 反算
- **P2**：porch 输入框误报、硬编码 scrcpy/APK 路径、`DPI_SOURCES` 死代码
- **P3**：`requirements.txt`、CI、`run_checks.py` 路径兜底、`main.ico`（实为 PNG）

详见 [ROADMAP_ANALYSIS.md](ROADMAP_ANALYSIS.md)。
