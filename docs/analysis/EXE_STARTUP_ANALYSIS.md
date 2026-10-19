# 「Failed to load Python DLL」启动失败排查（v3.2.21）

现象：自动升级后双击启动，弹

```
Failed to load Python DLL
'C:\Users\...\AppData\Local\Temp\_MEI194962\python311.dll'.
LoadLibrary: 找不到指定的模块。
```

---

## 一、先排除「下载不完整」

以前这个报错的根因确实是半截 exe（代理掐断下载），所以先查了完整性：

| 检查 | 结果 |
| --- | --- |
| 桌面 exe 大小 | 39,065,789 字节 —— 与 v3.2.20 构建产物**完全一致** |
| SHA256 | `06818D10…56994C`，与 `dist/DisplayTools.exe` **逐字节相同** |
| Zone.Identifier（下载标记） | 无 |
| Defender 检测记录 | 空（而且 Defender 实时保护是关的） |

**结论：文件是完好的，不是下载问题。** 这次是另一类原因，症状一样。

---

## 二、定位过程

| 实验 | 结果 |
| --- | --- |
| 解包目录 `_MEI194962` 里有没有 `python311.dll` | **有**，5,762,840 字节 |
| 启动 1.2 秒时抓解包目录 | 139 个文件，`python311.dll` 完整 |
| 从 `bsp_tools\dist\` 直接启动 | 同样失败 |
| `TEMP=D:\_dt_temp` 再启动 | **成功** |
| `TEMP=%LOCALAPPDATA%\dt_temp_c`（C:，但不是 Temp） | 失败 |
| `TEMP=C:\Windows\Temp` | 失败 |

**关键判据：解包在 C: 的任何目录都失败，解包在 D: 就正常。**

也就是说：文件解出来了、完好、路径也对，但 `LoadLibrary` 就是返回「找不到指定的模块」
（ERROR_MOD_NOT_FOUND）——典型的**环境拦截**，不是文件或代码问题。

这台机器装了三个安全软件（Windows Defender、火绒、McAfee），叠加了 SRP 策略
（默认 Unrestricted、无路径规则，所以不是 SRP 本身）。具体是哪一个拦的没有继续深挖，
因为**结论已经足够指导修复**：不要让程序从系统盘临时目录加载 DLL。

---

## 三、修法

### 1. 解包位置改到 exe 旁边（核心）

`DisplayTools.spec`：

```python
runtime_tmpdir='.',     # 原为 None（= 用 %TEMP%）
```

PyInstaller 单文件版会把自身解包到 `_MEIxxxx` 再加载。改成相对路径后，
解包目录落在**当前工作目录**——双击启动时就是 exe 所在目录。

### 2. 更新器启动新版本时显式设工作目录

解包位置依赖工作目录，所以 `update_check` 里三处 `Start-Process` 都加上：

```powershell
Start-Process -FilePath $target -WorkingDirectory (Split-Path -Parent $target)
```

### 3. 清理被强杀留下的解包目录

解包现在落在 exe 旁边，正常退出 PyInstaller 会自己删；被强杀/崩溃会留下一个
约 100MB 的 `_MEI*`。新增 `app_runtime.cleanup_stale_boot_dirs()`，启动时清一次：

- 只在打包运行时执行（源码跑不动这个逻辑）；
- 跳过当前正在用的那个；
- 只删 30 分钟前的，避免误删另一个刚启动的实例。

---

## 四、验证

| 项 | 结果 |
| --- | --- |
| 按双击方式启动（WorkingDirectory = exe 目录） | 窗口出现，标题 `DisplayTools v3.2.21` |
| `%TEMP%` 下新增 `_MEI*` | **0 个** |
| exe 目录下 `_MEI*` | 1 个（139 个文件） |
| 离线自查 | 11 项全通过 |

---

## 五、影响与注意事项

1. **v3.2.20 的 exe 在这台机器上起不来，自动更新用不了**，需要手动替换一次：
   把 `bsp_tools\dist\DisplayTools.exe`（v3.2.21）拷到 `D:\Desktop\shell_tools\`
   覆盖同名文件。
2. **启动方式有约束**：双击没问题；用快捷方式/命令行启动时要保证工作目录是
   exe 所在目录，否则解包会落到别处。代码里已在 `update_check` 处理。
3. **exe 目录必须可写**（解包要在旁边建 `_MEI*`）。如果哪天放到只读目录/共享盘，
   会启动失败——这是这次改动的代价，换来的是不再受系统 Temp 策略影响。
4. 以前「三道完整性校验」防的是**半截 exe**；这次的根因是**环境拦截**，
   症状相同但检查都通过。以后再遇到这个报错，先看：exe 大小/SHA 对不对 →
   换个可写目录（非系统盘）启动试试。
