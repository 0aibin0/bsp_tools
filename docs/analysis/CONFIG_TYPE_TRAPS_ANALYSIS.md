# 配置类型陷阱排查（改动分析）

日期：2026-10-23 · 基线 `v3.2.30`

起因：v3.2.30 修了「先 erase」勾选状态存不回去的问题，用户要求检查代码里有没有同类问题。

---

## 一、根因

`app_config.py` 的读写**全部走字符串**：

```python
def set(self, key, value):
    section[str(key)] = "" if value is None else str(value)   # ← str() 一切

def get(self, key, fallback=""):
    ...
    return str(value)                                          # ← 也返回字符串
```

所以：

| 写入 | 存储 | `get()` 返回 |
| --- | --- | --- |
| `False` | `"False"` | `"False"` |
| `True` | `"True"` | `"True"` |
| `[894, 705]` | `"[894, 705]"` | `"[894, 705]"` |
| `None` | `""` | `""` |

**两个陷阱**：

1. `bool("False")` → `True`（非空字符串都是真）→ **开关关不掉**
2. `isinstance("[894, 705]", list)` → `False` → **列表缓存永远不命中**

---

## 二、排查结果

### 2.1 布尔配置：只有 flash 两处，已修

全项目 `QCheckBox` 共 12 个，但**只有 flash 的两个把状态存进配置**：

| 勾选框 | 存配置？ |
| --- | --- |
| `flash_erase`（先 erase） | ✅ 已用 `get_bool` |
| `flash_skip_missing`（跳过未填的行） | ✅ 已用 `get_bool` |
| `tools_battery` 自动刷新 | ❌ 纯运行时状态 |
| `tools_display` 读 actual / 自动分频 | ❌ 纯运行时状态 |
| `tools_log` 正则 / 只看错误 / 高亮 / 自动滚动 | ❌ 纯运行时状态 |
| `tools_touch` 只看 ABS_MT 轴 | ❌ 纯运行时状态 |
| `tools_sitepack` / `tools_perf` / `tools_guard` 的 | ❌ 纯运行时状态 |

搜索 `bool(config.get(...))` / `bool(app_config.config().get(...))`：**无匹配**。

### 2.2 列表配置：发现一个真 bug（已修）

`layout_min_size`（v3.2.28 加的启动缓存）：

```python
cached = app_config.config().get("layout_min_size")     # 永远返回字符串
if (isinstance(cached, (list, tuple)) and len(cached) == 2 ...):   # ← 永远 False
```

**后果**：缓存从来没生效过，每次启动都在重新测量所有页面的最小尺寸。
也就是说 v3.2.28 声称的「构造 1063ms → 333ms」里，仍有一大块是这个重复测量。

**实测对比**（修好后）：

| 场景 | 耗时 |
| --- | --- |
| 首次启动（无缓存，要量尺寸） | 398 ms |
| 第二次启动（命中缓存） | **9 ms** |

**省了 389 ms**。

**修法**：

```python
def _load_int_pair(raw):
    """把 "[894, 705]" 还原成 (894, 705)；不合法返回 None。"""
    try:
        parsed = json.loads(str(raw).strip())
    except (ValueError, TypeError):
        parsed = text.strip("[]").split(",")        # 兼容老的逗号分隔写法
    ...
```

写入侧改成 `json.dumps([w, h])`，保持格式明确。

### 2.3 顺带发现的第三个问题：`pages.values()` 返回占位页

v3.2.28 的惰性页面加载引入 `_LazyPageMap`，当时**故意**让 `values()` / `items()`
不做惰性解析（怕遍历时把所有页面都建出来）。

但这让调用方拿到了裸 `QWidget` 占位页，`devtools/check_layout.py` 直接崩：

```
AttributeError: 'QWidget' object has no attribute 'sections'
```

**这说明布局检查其实一直没真正跑过文件管理页**——它拿到的全是占位页。

**修法**：让 `values()` / `items()` 也做惰性解析。

> 判断依据：惰性加载的收益在**启动**，不在遍历。会遍历页面的场景
> （自测、check_layout、capture_ui）本来就要把所有页面都用上，
> 解析是应该的。内部需要原始值的地方继续用 `raw_get()`。

### 2.4 因此暴露出的真布局问题（已修）

布局检查真正跑到文件管理页后，报了一个之前从未发现的问题：

```
文字裁切: tools/files/card/QLabel(0 项 · /sdcard/) 控件宽46 放不下 '0 项 · /sdcard/'
```

`tools_files.py` 里目录状态标签是普通 `QLabel`，显示 `{N} 项 · {路径}`，
路径一长就把卡片右上角挤爆。

**修法**：换成项目已有的 `W.ElidedLabel`（放不下时自动显示省略号，中间省略）。

---

## 三、`get_bool` 的健壮性验证

修完后专门测了 `get_bool` 对各类存值的解析：

| 存储值 | `get_bool` |
| --- | --- |
| `"True"` / `"true"` / `"1"` / `"yes"` / `"on"` | `True` ✅ |
| `"False"` / `"false"` / `"0"` / `"no"` / `"off"` | `False` ✅ |
| `""` / `"abc"` | 返回 fallback ✅ |

`set(True)` → 存 `"True"` → `get_bool` 得到 `True`；`set(False)` 同理。
往返正确。

---

## 四、结论与规范

### 已修（本次）

| 问题 | 影响 |
| --- | --- |
| `layout_min_size` 列表缓存不生效 | 每次启动多花 ~389ms |
| `pages.values()` 返回占位页 | 布局检查崩，文件管理页从未被真正检查 |
| 文件管理页状态标签被裁切 | 路径长时显示不全 |

### 今后规则

1. **布尔值一律用 `config.get_bool(key, fallback)`**，
   禁止 `bool(config.get(...))`。
2. **非字符串值（列表/字典）写入前 `json.dumps`，读取后 `json.loads`**，
   禁止直接用 `isinstance` 判断 `config.get()` 的返回值。
3. **`config.get()` 的返回值永远是字符串**，需要数字用 `get_int()`。

### 验证

- `selftest` 320 → **324 项**（新增缓存往返 / 脏数据 / values() 真实性 4 条）
- 离线自查 **11 项全过**
- `check_layout` 5 种尺寸全 OK
