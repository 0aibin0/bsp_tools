"""一键自查：把所有检查脚本串成一条命令。

用法（仓库根目录）：
    python run_checks.py             只跑不需要设备的检查（快）
    python run_checks.py device      连设备一起跑（要连板子，慢）

为什么要有这个：Qt 布局出问题不会报错，只会把控件压到重叠或者把内容裁掉，
肉眼看"差不多"就漏过去了。改完代码跑一遍，比人眼靠谱。

用 Python 而不是纯 bat：bat 是 GBK 代码页，脚本里写中文会被解析器撕碎
（表现成 "The system cannot find the path specified" 这种莫名其妙的报错）。
"""

import os
import subprocess
import sys

# 输出编码兜底：Windows 上把 stdout/stderr 重定向到管道时，Python 默认按
# 系统代码页（cp1252 / GBK）编码，一打印中文就 UnicodeEncodeError 直接崩。
# GitHub Actions 第一次跑就是这么挂的（0 秒退出）。这里强制 UTF-8，
# 真遇到编不出来的字符用 ? 代替，绝不让自查脚本自己先崩掉。
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                      # noqa: BLE001
        pass

ROOT = os.path.dirname(os.path.abspath(__file__))
# 优先用仓库自带的 .venv；没有（新克隆 / CI 里直接 pip install 到系统解释器）
# 就退回当前解释器——以前只认 .venv，新克隆一跑就 FileNotFoundError。
PYTHON = os.path.join(ROOT, ".venv", "Scripts", "python.exe")
if not os.path.isfile(PYTHON):
    PYTHON = sys.executable

# (显示名, 命令参数, 是否需要连设备)
CHECKS = [
    ("逻辑自测", ["devtools/selftest.py"], False),
    ("主题令牌（浅色/深色）", ["devtools/check_theme.py"], False),
    ("时序计算与 DCS 构造", ["devtools/check_timing.py"], False),
    ("多设备 -s 注入", ["devtools/check_multidevice.py"], False),
    ("Initcode 反向解析", ["devtools/check_initcode.py"], False),
    ("布局健康检查", ["devtools/check_layout.py"], False),
    ("换行标签高度", ["devtools/check_wraplabel.py"], False),
    ("面板宽度约定", ["devtools/check_panel_width.py"], False),
    ("说明框尺寸与滚动", ["devtools/check_info_dialog.py"], False),
    ("控件尺寸检查", ["devtools/inspect_ui.py", "--flag", "--size", "1360x840"], False),
    ("命令前缀（真机执行）", ["devtools/verify_commands.py"], True),
    ("端到端真机验证", ["devtools/verify_on_device.py"], True),
    ("流式日志验证", ["devtools/verify_log_stream.py"], True),
    ("现场包真机抓取", ["devtools/check_sitepack.py", "--live"], True),
    ("启动冒烟", ["devtools/smoke_start.py"], False),
]


def environment():
    env = dict(os.environ)
    env.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def run_one(name, args):
    """跑一个检查，返回 (是否通过, 输出文本)。"""
    command = [PYTHON, "-u"] + args
    print("\n" + "-" * 62)
    print("[检查] {}".format(name))
    print("-" * 62, flush=True)
    try:
        proc = subprocess.run(command, cwd=ROOT, env=environment(),
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              timeout=900)
    except subprocess.TimeoutExpired:
        print("  [超时] 超过 15 分钟没结束")
        return False, "timeout"
    text = proc.stdout.decode("utf-8", "replace")
    lines = [ln for ln in text.splitlines() if ln.strip()]
    ok = proc.returncode == 0
    if ok:
        # 通过时只回显末几行：检查脚本自己会打明细，这里要的是结论
        for line in (lines[-4:] if len(lines) > 4 else lines):
            print("  " + line)
    else:
        # 失败时把 FAIL 行全部列出来——CI 上看不到完整日志，
        # 这几行就是唯一定位线索（本地终端也会省得往上翻）
        fails = [ln for ln in lines if "FAIL" in ln]
        for line in (fails or lines[-10:]):
            print("  " + line)
    return ok, text


def main():
    with_device = any(arg.lower() in ("device", "--device", "-d") for arg in sys.argv[1:])
    selected = [c for c in CHECKS if with_device or not c[2]]

    print("=" * 62)
    print(" DisplayTools 自查{}".format("（含真机）" if with_device else "（离线）"))
    print("=" * 62)

    results = []
    for name, args, _needs_device in selected:
        ok, _text = run_one(name, args)
        results.append((name, ok))

    failed = [name for name, ok in results if not ok]
    print("\n" + "=" * 62)
    for name, ok in results:
        print("  {}  {}".format("PASS" if ok else "FAIL", name))
    print("=" * 62)
    if failed:
        print("失败 {} 项 / 共 {} 项：{}".format(
            len(failed), len(results), "、".join(failed)))
    else:
        print("全部通过（{} 项检查）".format(len(results)))
    if not with_device:
        print("提示：跑 `python run_checks.py device` 可以把真机相关的检查也带上。")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
