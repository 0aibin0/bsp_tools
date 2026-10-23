# DisplayTools 性能优化分析

日期：2026-10-23 · 基线版本 `v3.2.27`

---

## 一、问题

用户反馈「有些卡顿」。分三处测量：启动、切页、打包体积。

---

## 二、测量结果（优化前）

### 2.1 各阶段耗时

| 阶段 | 耗时 |
| --- | --- |
| QApplication 创建 | 1775 ms（首次，含 PyQt 初始化） |
| 字体 + 样式表 | 28 ms |
| **MainWindow() 构造** | **1063 ms** |
| show() + 首次布局 | 61 ms |

### 2.2 切页耗时

| 页面 | 首次 | 再次 |
| --- | --- | --- |
| 常用工具（1033 个控件） | 26 ms | **335 ms** |
| Shell Tools | **208 ms** | 173 ms |
| Initcode Builder | 22 ms | 4 ms |
| Initcode 格式转换 | 3 ms | 3 ms |

### 2.3 冷启动（exe）

- 解包目录出现：422 ms
- 窗口出现：**3190 ms**
- 解包量：**93 MB / 139 个文件**

---

## 三、根因

### 3.1 所有页面在启动时全建（最大头）

`_build_ui` 里对 `PAGE_DEFS` 无脑循环 `cls()`，四个页面（含 1033 个控件的常用工具页）
在建窗口时就全建完。profile 显示 `tools_page.__init__` 占 348 ms，
其中 `command_runner.ResultPanel.__init__` 占 249 ms。

**更细的发现**：第一个 `ResultPanel` 要 **148 ms**，第二个只要 **0.31 ms**。
这是首个 `QPlainTextEdit` 触发字体/样式初始化的固定成本，每个窗口只吃一次，
但被算进了启动时间。

### 3.2 切页时同步跑 adb

`ShellToolsPage.on_page_shown()` 每次切页都**同步**调 `check_device_connected()`，
它内部是 `subprocess.run(adb devices)`。adb 首次启动 100~400 ms，直接卡住整窗。

profile 里 `_thread.lock.acquire` 占用 0.642s（85%）就是这类子进程 I/O。

### 3.3 启动后 300ms 的设备探测也是同步的

`MainWindow.refresh_device_status()` 注释写着「后台查询」，**实际是同步的**——
`QTimer.singleShot(300, ...)` 触发时正好卡在用户第一次点菜单上。

### 3.4 update_check 导入链拖慢启动

`import update_check` 连带拉起 `urllib.request`（44.9 ms）+ `zipfile`（10.5 ms）
+ `urllib.parse` 等，合计 **60.8 ms**，而启动阶段根本用不到它。

### 3.5 打包带了大量用不到的 Qt 二进制

`EXCLUDES` 只作用于 Python 模块，管不住 PyQt5 hook 搬进来的 Qt5/bin 目录：

| 文件 | 大小 | 用到了吗 |
| --- | --- | --- |
| `opengl32sw.dll` | 20.9 MB | 否（软件 OpenGL 回退） |
| `Qt5Quick.dll` / `Qt5Qml.dll` | 6.2 MB | 否（不用 QML） |
| `Qt5Designer.dll` | 4.5 MB | 否 |
| `d3dcompiler_47.dll` | 4.2 MB | 否 |
| `libGLESv2.dll` / `libEGL.dll` | 3.4 MB | 否 |
| `Qt5XmlPatterns.dll` | 2.6 MB | 否 |

这些 DLL 在单文件版里**每个都要解包**，直接推高冷启动时间。

---

## 四、改动

### 4.1 页面惰性创建（`mainwindow.py`）

```python
for key, _title, _subtitle, _cls, _section, _icon in PAGE_DEFS:
    placeholder = QWidget()          # 先放占位
    placeholder.setObjectName(f"page_{key}")
    self.pages[key] = placeholder
    self._page_factories[key] = _cls
    self.stack.addWidget(placeholder)
```

`_ensure_page(key)` 在首次访问时建真实页面并替换占位页。

**兼容性关键**：新增 `_LazyPageMap` 重载 `__getitem__`/`get`，让代码里大量
`window.pages[key]` 的写法（自测、截图脚本、快捷操作）照旧能拿到真实页面。
内部逻辑用 `raw_get()` 避免递归。

### 4.2 最小尺寸测量结果缓存（`mainwindow.py`）

原本为了量 `minimumSizeHint` 要临时切遍所有页面，这会破坏惰性加载。
改为：测一次存进 `DisplayTools.json` 的 `layout_min_size`，后续启动直接用。
缓存缺失时才走 `_measure_pages()` 全量测量并回写。

实测缓存值 `[894, 704]`，两次启动一致。

### 4.3 切页的设备探测改异步（`shell_tools.py`）

```python
def on_page_shown(self):
    self._apply_split_sizes()
    if not self._busy:
        self._refresh_device_async()
```

后台 `threading.Thread(daemon=True)` 查设备，主线程 `QTimer` 轮询结果再更新 UI。
同一页面并发只留一个探测，避免快速切页堆积 adb 进程。

### 4.4 启动的设备探测改异步（`mainwindow.py`）

新增 `_DeviceStatusProbe`：用 **Python threading 而非 QThread**。

> 踩坑记录：最初用 `QThread` 实现，自测里连续创建多个 `MainWindow` 时崩溃
> （退出码 `0xC0000409`），报 `QThread: Destroyed while thread is still running`。
> QThread 是 QObject，父窗口销毁时若仍在运行就会炸。改用 daemon 线程 +
> 主线程定时轮询后彻底解决。

同时把 `probe_device()` 提成 `shell_tools.py` 的模块级函数，
这样页面还没创建时主窗口也能后台探测（保住惰性加载）。

### 4.5 update_check 延迟导入（`mainwindow.py`）

```python
class _LazyModule(object):
    """把模块导入推迟到第一次真正使用。"""
    ...
update_check = _LazyModule("update_check")
```

保持 `update_check.xxx` 的 37 处调用写法不变，只在首次访问属性时才 import。

### 4.6 打包排除无用 Qt 二进制（`DisplayTools.spec`）

```python
BINARY_SKIP_PREFIXES = (
    'qt5qml', 'qt5quick', 'opengl32sw', 'qt5designer', 'libglesv2', 'libegl',
    'qt5xmlpatterns', 'qt5xml', 'qt5help', 'qt5printsupport', ...
)
a.binaries = [item for item in a.binaries if _skip_binary(item)]
a.datas = [item for item in a.datas if _skip_binary(item)]
```

**保守保留**：`qt5network`（单实例守卫）、`libcrypto`/`libssl`（QtNetwork 依赖）。

---

## 五、优化后

### 5.1 各阶段耗时

| 阶段 | 优化前 | 优化后 | 变化 |
| --- | --- | --- | --- |
| MainWindow() 构造 | 1063 ms | **333 ms** | **−69%** |

### 5.2 切页耗时

| 页面 | 优化前（再次） | 优化后（再次） |
| --- | --- | --- |
| 常用工具 | 335 ms | **2.5 ms** |
| Shell Tools | 173 ms | **2.9 ms** |
| Initcode Builder | 4 ms | 2.9 ms |
| Initcode 格式转换 | 3 ms | 2.7 ms |

首次切页也有改善：Shell Tools 208 → **3.7 ms**。

### 5.3 冷启动与体积

| 指标 | 优化前 | 优化后 |
| --- | --- | --- |
| exe 体积 | 37.3 MB | **23.9 MB** |
| 解包量 | 93 MB / 139 文件 | **58 MB / 131 文件** |
| 冷启动（窗口出现） | ~2900 ms | **~2300 ms** |

---

## 六、验证

| 项 | 结果 |
| --- | --- |
| 离线自查 11 项 | **全部通过** |
| selftest | **303 项通过** |
| 多窗口连续创建（自测场景） | 通过，无 QThread 崩溃 |
| 精简包启动 | 窗口正常，设备状态/下拉框正常 |
| 单实例守卫 | 通过（第二个实例不新增进程） |
| 配置文件生成 | 正常 |

---

## 七、遗留与说明

1. **冷启动仍要 ~2.3s**：其中解包 422ms，剩余是 Python 运行时 + PyQt5 DLL 加载，
   这部分是单文件版的固有成本。想进一步提速只能改**目录版**（onedir），
   代价是变成 130+ 个文件的目录分发。
2. **`pages` 不再是普通 dict**：`_LazyPageMap` 重载了取值行为。
   `list(window.pages)` / `.keys()` 仍只返回键，但 `.values()` / `.items()`
   **不再**惰性解析（避免遍历时把页面全建出来）。需要真实页面时用 `pages[key]`。
3. **`layout_min_size` 缓存**：若将来调整页面布局导致最小尺寸变化，
   需要清掉 `DisplayTools.json` 里的这一项让它重新测量。

---

## 八、第二轮排查（v3.2.28 之后）

用户反馈「还有点卡」，于是把「导入链 / 事件循环 / 分区切换」全量量了一遍。

### 8.1 事件循环空闲时是健康的

3 秒窗口内每 16ms 打一次点：

| 指标 | 值 |
| --- | --- |
| 采样次数 | 185 |
| 中位间隔 | 15.0 ms |
| 最大间隔 | 35.4 ms |
| 超过 50ms 的卡顿 | **0 次** |

结论：**空闲状态下没有卡顿**，之前的感觉来自「首次进入某页面/分区」的一次性构建。

### 8.2 分区切换：首见贵、之后便宜

| 分区 | 控件数 | 首次切换 | 预热后再切 |
| --- | --- | --- | --- |
| device | 53 | 95.6 ms | 11 ms |
| display | 179 | 101.0 ms | 9 ms（反复切 1ms） |
| files | 33 | 87.0 ms | 6.5 ms |
| perf | 72 | 73.8 ms | 9 ms |
| touch | 64 | 42.3 ms | — |
| sitepack | 42 | 37.8 ms | — |
| log | 31 | 0.1 ms | 0.2 ms |

拆开看 `show_section` 的每一步：`setCurrentWidget` 0.5~1.4ms、
`updateGeometry` 0ms、`_fit_content` 0~0.1ms，耗时几乎全在
**`processEvents()` 里的首次布局+绘制**。

`minimumSizeHint()` 本身是一次性缓存（首次 15.7ms，之后 0.0ms），不是瓶颈。

**结论**：这是 Qt 首次渲染某套控件的固有成本，不是代码低效。
想消除只能「预建所有分区」——但那会让启动多花 400ms，不划算，保持现状。

### 8.3 又抓到两处启动期无用导入

用 `-X importtime` 逐项看，发现上一轮漏掉的两个：

| 模块 | 耗时 | 何时真正需要 |
| --- | --- | --- |
| `download_dialog` | **67.7 ms** | 只在点「下载并重启」时 |
| 其内部 `update_check` | 67.0 ms | 同上 |

`download_dialog` 虽然延迟了 `update_check` 的**使用**，但它自己在
`mainwindow.py` 顶部被 import，于是把 `update_check` 整条链又拉了起来——
上一轮的 `_LazyModule` 因此完全失效。

**修法**：把 `import download_dialog` 也挪到真正使用处（下载进度框创建前）。

验证：启动后 `update_check._module is None`、`'download_dialog' not in sys.modules`，
触发更新检查时才加载。

### 8.4 第二轮验证

- 离线自查 11 项全过
- selftest 304 项全过
- 延迟导入验证：启动后两个模块都未加载，触发后正常加载
