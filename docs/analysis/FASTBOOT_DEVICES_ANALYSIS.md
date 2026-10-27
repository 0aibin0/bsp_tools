# fastboot devices 按钮 + 状态栏联动（改动分析）

日期：2026-10-27 · 基线 `v3.2.33`

---

## 一、需求

1. 在 fastboot flash 界面增加一个 `fastboot devices` 指令按钮
2. `devices` 的结果**自动更新状态栏**的设备显示（不只是打到日志面板）

---

## 二、按钮

插在最后一行，位置按操作顺序排：

```
[Flash]  [   fastboot mode   ]  [devices]  [reboot]
```

即 **bootloader → devices → 烧录 → reboot**。

布局实测（1360 宽下）：

| 控件 | x | 宽 |
| --- | --- | --- |
| flash_btn | 22 | 59 |
| fb_mode | 86 | **578**（stretch 吃掉剩余） |
| fb_devices | 669 | 71 |
| fb_reboot | 745 | 67 |

`fb_mode` 的 `addWidget(..., 1)` 让它继续占满中间空间，新按钮不破坏布局。

---

## 三、状态栏联动实现

### 3.1 给 `_exec_with_result` 加回调

原来这个函数没有返回值通道：

```python
def _exec_with_result(self, command, success_msg):
    ...
    self._run_async(command, on_done)
```

加一个可选参数（30+ 处既有调用点全部不受影响）：

```python
def _exec_with_result(self, command, success_msg, on_result=None):
    ...
    def on_done(exit_code, output):
        ...  # 原有的日志输出
        if on_result is not None:
            try:
                on_result(exit_code, output)
            except Exception as exc:
                self.append_text(f"[警告] 更新界面失败: {exc}\n")
```

### 3.2 解析抽成独立函数

```python
def parse_fastboot_devices(output):
    """从 `fastboot devices` 输出里取序列号列表。"""
```

`fastboot devices` 的输出是 `<序列号>\tfastboot`（每行一台）。

### 3.3 状态栏文案

| 情况 | 显示 | tone |
| --- | --- | --- |
| 一台设备 | `● 设备：G0B61W026…` | ok（绿） |
| 多台设备 | `● 设备：A +1` | ok |
| 没有设备 | `● 设备：未连接（fastboot）` | muted（灰） |
| 查询失败 | `● 设备：fastboot 查询失败` | muted |

失败时**不把原始错误贴进状态栏**（太长会挤爆），细节留在日志面板。

---

## 四、过程中修的两个 bug

### 4.1 `error:` 行被当成设备名

第一版解析只过滤了空行和 `*` 开头的行：

```python
if not line or line.startswith("*"):
    continue
```

但 fastboot 失败时输出 `error: no devices/emulators found`，
第一段被当成序列号，状态栏就显示成 `● 设备：error:`。

修法——过滤这些非设备行：

```python
if not line or line.startswith("*") or line.startswith("<"):
    continue
if lowered.startswith("error") or lowered.startswith("fastboot:"):
    continue
```

覆盖：`error:`、`fastboot: error:`、`< waiting for any device >`、
`* daemon started successfully *`。

### 4.2 状态栏 tooltip 一直是省略号（老 bug）

`mainwindow.set_device_status()` 原来是：

```python
if len(text) > 14:
    text = text[:12] + "…"        # ← 直接覆盖了 text
self.deviceLabel.setText(f"● {text}")
self.deviceLabel.setToolTip(text)      # ← 用的也是截断值
```

结果：

```
显示    : ● 设备：G0B61W026…
tooltip : 设备：G0B61W026…        ← 想看完整序列号反而看不到
```

注释里写着「完整值放 tooltip」，但实现没做到。修法——保留原值：

```python
full = text
if len(full) > 14:
    text = full[:12] + "…"
self.deviceLabel.setText(f"● {text}")
self.deviceLabel.setToolTip(full)      # ← 完整值
```

> 这个 bug 一直存在，只是设备序列号短的时候看不出来。
> `fastboot devices` 返回的是 16 位序列号，才暴露。

---

## 五、验证

`selftest` 336 → **348 项**（新增 12 条）：

```text
有 fastboot devices 按钮            PASS
devices 按钮文案正确                PASS
devices 按钮排在 reboot 左边        PASS
devices 按钮有对应的处理函数         PASS
解析 fastboot devices：单台          PASS
解析 fastboot devices：多台          PASS
解析 fastboot devices：过滤 error 行 PASS
解析 fastboot devices：过滤等待提示   PASS
devices 结果同步到状态栏             PASS
状态栏 tooltip 保留完整序列号（不截断） PASS
没有 fastboot 设备时状态栏提示未连接   PASS
查询失败时不把原始错误贴进状态栏       PASS
```

其它：

| 项 | 结果 |
| --- | --- |
| 离线自查 11 项 | 全部通过 |
| `check_layout` 5 种尺寸 | 全部 OK |

---

## 六、已知边界

- **只更新状态栏，不改设备下拉框**：`fastboot` 模式的设备序列号和 `adb` 的
  设备列表是两个体系，混进同一个下拉框会让人误以为可以 `adb -s` 指定。
- **不自动切到 fastboot 模式**：`devices` 只查询，需要先手动 `bootloader`。
- **`devices` 查询失败不会重试**：fastboot 冷启动偶尔需要第二次，重跑一次按钮即可。
