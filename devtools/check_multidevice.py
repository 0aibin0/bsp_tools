"""多设备选择与 -s 注入自查。

用法：python devtools/_check_multidevice.py
"""

import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, "bsp_tools"))

import command_runner  # noqa: E402
import toolchain  # noqa: E402

FAILED = []


def check(label, ok, detail=""):
    print("  {}  {}  {}".format("PASS" if ok else "FAIL", label, detail))
    if not ok:
        FAILED.append(label)


print("[1] 未选设备时保持裸 adb（命令串要给人看）")
toolchain.set_serial("")
check("adb_shell() = adb", toolchain.adb_shell() == "adb", toolchain.adb_shell())
check("device_cmd 不变",
      command_runner.device_cmd("dumpsys battery") == "adb shell dumpsys battery",
      command_runner.device_cmd("dumpsys battery"))

print("\n[2] 选中设备后所有路径都带 -s")
toolchain.set_serial("99022393342169")
check("adb_shell() 带 -s",
      toolchain.adb_shell() == "adb -s 99022393342169", toolchain.adb_shell())
check("设备端命令带 -s",
      command_runner.device_cmd("dumpsys battery")
      == "adb -s 99022393342169 shell dumpsys battery",
      command_runner.device_cmd("dumpsys battery"))
check("带管道的命令带 -s 且仍被引号包住",
      command_runner.device_cmd("dumpsys display | grep fps")
      == 'adb -s 99022393342169 shell "dumpsys display | grep fps"',
      command_runner.device_cmd("dumpsys display | grep fps"))
check("显式 adb 命令也带 -s",
      command_runner.device_cmd("adb devices")
      == "adb -s 99022393342169 devices",
      command_runner.device_cmd("adb devices"))
check("fastboot 也带 -s",
      command_runner.device_cmd("fastboot devices")
      == "fastboot -s 99022393342169 devices",
      command_runner.device_cmd("fastboot devices"))
check("QProcess 参数表带 -s",
      toolchain.adb_program_args(["shell", "dmesg"])[1]
      == ["-s", "99022393342169", "shell", "dmesg"],
      str(toolchain.adb_program_args(["shell", "dmesg"])))
check("Windows 命令不受影响",
      command_runner.device_cmd("ping -n 1 127.0.0.1") == "ping -n 1 127.0.0.1",
      command_runner.device_cmd("ping -n 1 127.0.0.1"))

print("\n[3] 现场包拼装尊重 -s")
import tools_sitepack as SP  # noqa: E402
check("带管道的抓取项带 -s",
      SP.build_command("getprop | grep dsi", serial="ABC123")
      == 'adb -s ABC123 shell "getprop | grep dsi"',
      SP.build_command("getprop | grep dsi", serial="ABC123"))

print("\n[4] 清空后恢复")
toolchain.set_serial("")
check("清空后回到裸 adb",
      command_runner.device_cmd("dumpsys battery") == "adb shell dumpsys battery",
      command_runner.device_cmd("dumpsys battery"))
check("selected_serial 为空", toolchain.selected_serial() == "")

print("\n[5] 设备枚举（真机，无设备时不算失败）")
devices = toolchain.list_devices()
print("     扫描到:", devices)
check("list_devices 返回列表", isinstance(devices, list))
check("在线设备枚举是列表", isinstance(toolchain.online_devices(), list))

print("\n" + "=" * 46)
if FAILED:
    print("失败 {} 项：{}".format(len(FAILED), "、".join(FAILED)))
    sys.exit(1)
print("多设备支持全部通过")
