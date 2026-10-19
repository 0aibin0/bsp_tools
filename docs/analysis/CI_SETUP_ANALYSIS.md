# CI 接入与三次失败排查（记录）

目标：给仓库加 GitHub Actions 离线自查，让 11 项检查不再只靠人记得跑。
最终状态：**全绿**（run #6，`exit=0`，11 项全 PASS）。

---

## 一、workflow

`.github/workflows/checks.yml`：

- `windows-latest`（必须 Windows：界面/布局检查跑 Qt，`smoke_start` 还要桌面会话）
- Python 3.11 + `pip install -r requirements.txt`
- `python run_checks.py`（只跑离线 11 项；另外 4 项要连板子）
- 失败时把 `FAIL` 行写成 `::error::` 注解；成功/失败都写一条 `::notice::` 摘要

> 为什么用注解：Actions 的**日志下载需要 admin 权限**，未认证的
> `/actions/runs/{id}/logs` 返回 403。注解走公开的
> `check-runs/{id}/annotations`，不用 token 也能读到失败原因。

---

## 二、三次失败，三个不同的坑

### 坑 1：中文输出在 CI 上直接崩（run #1，0 秒退出）

**现象**：`离线自查` 步骤 0 秒失败，没有任何检查输出。

**根因**：Windows 上把 stdout 重定向到管道时，Python 按系统代码页
（cp1252）编码。`run_checks.py` 第一行就打印中文 → `UnicodeEncodeError` → 退出码 1。

**复现**：

```powershell
$env:PYTHONIOENCODING="cp1252"; python run_checks.py
# UnicodeEncodeError: 'charmap' codec can't encode characters ...
```

**修法**：

- `run_checks.py` 开头把 stdout/stderr `reconfigure(encoding="utf-8", errors="replace")`；
- workflow 里再设 `PYTHONUTF8=1` / `PYTHONIOENCODING=utf-8` 双保险。

> 本机一直跑得通，是因为终端是 UTF-8——这类问题只有换环境才暴露。

### 坑 2：断言读到被省略号截断的显示文本（run #2）

**现象**：`FAIL 分辨率提取 122…712`

**根因**：`DeviceInfoSection` 的值是 `ElidedLabel`，宽度不够时把
`1220x2712` 中间换成省略号。测试断言的是**显示文本**，字体一变宽就失败。
CI 上字体与本地不同（可能缺中文字体、回退字体更宽），于是本地过、CI 挂。

**复现**：把 `QT_QPA_FONTDIR` 指到一个空目录（模拟没有字体）→ 本地也挂同一条。

**修法**：加 `card_text(label)` 辅助函数，优先取 `fullText()`（未省略的全文），
所有指标卡断言改用它。

### 坑 3：断言依赖「本机早就有数据文件」（run #3/#4）

**现象**：`FAIL 设置也在同一个文件里（config 段）  []`

**根因**：断言直接要求 `DisplayTools.json` 的 `config` 段非空。干净检出的仓库里
这个文件还不存在（`.gitignore` 里），`AppData` 初始化时 `config` 是空字典——
**只有本机早就有配置文件才会通过**。这也解释了为什么我本地第一次克隆跑挂、
第二次跑却过了（第一次运行生成了文件）。

**修法**：先用 `app_config.config().update(selftest_marker="1")` 写一个值，
再断言这个值出现在同一文件的 `config` 段里。测试末尾原有的备份/还原逻辑
会把数据文件恢复原样。

---

## 三、教训

| 教训 | 说明 |
| --- | --- |
| **本地绿 ≠ CI 绿** | 编码、字体、是否已有数据文件，这三样本地都不会暴露 |
| 断言要读**数据**，不要读**显示文本** | 会被省略/换行/字体影响的都不是稳定契约 |
| 测试不能依赖仓库外的既有状态 | 干净克隆是唯一可信的起点 |
| CI 失败要能自证原因 | 日志要 admin 权限，所以把结论写成 annotation |

---

## 四、当前状态

```text
main = 8141864
tag  v3.2.20 = 722a7ec（发布提交：功能 + exe）
```

`v3.2.20` 之后又有 4 个提交，都只动 CI/测试，**不影响 exe 与功能**：

| 提交 | 内容 |
| --- | --- |
| `2f643a3` | 自查输出强制 UTF-8 |
| `d50abba` | 指标卡断言改读全文 + 失败时列出 FAIL 行 |
| `4bdc0fb` | 失败写 `::error::` 注解 |
| `998f945` | config 段断言先写后读 |
| `8141864` | 成功/失败都写 `::notice::` 摘要 |

最后一次 CI：`conclusion=success`，注解里能看到 `全部通过（11 项检查）`。
