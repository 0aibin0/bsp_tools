"""主题令牌自查：切换深色后不能还有浅色残留。

用法：python devtools/_check_theme.py
"""

import os
import re
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, "bsp_tools"))

# build_stylesheet 会画下拉箭头 PNG，必须先有 QApplication（QPixmap 的硬要求）
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
if sys.platform == "win32":
    os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")

from PyQt5.QtWidgets import QApplication  # noqa: E402

_app = QApplication.instance() or QApplication([])

import theme  # noqa: E402

FAILED = []


def check(label, ok, detail=""):
    print("  {}  {}  {}".format("PASS" if ok else "FAIL", label, detail))
    if not ok:
        FAILED.append(label)


print("[1] 模式解析")
check("light 直通", theme.resolve_mode("light") == "light")
check("dark 直通", theme.resolve_mode("dark") == "dark")
check("未配置时跟随系统", theme.resolve_mode("") in ("light", "dark"),
      theme.resolve_mode(""))
check("system 跟随系统", theme.resolve_mode("system") in ("light", "dark"),
      theme.resolve_mode("system"))

print("\n[2] 浅色/深色令牌完整且不重样")
missing = [k for k in theme._MODE_TOKENS
           if k not in theme.LIGHT_TOKENS or k not in theme.DARK_TOKENS]
check("两套调色板覆盖所有令牌", not missing, str(missing))
same = [k for k in theme._MODE_TOKENS
        if theme.LIGHT_TOKENS[k] == theme.DARK_TOKENS[k]]
check("两套调色板没有完全相同的值", not same, str(same))

print("\n[3] 切换后模块级令牌真的变了")
theme.set_mode("light")
light_bg, light_surface, light_text = theme.BG, theme.SURFACE, theme.TEXT
mode_light = theme.current_mode()
theme.set_mode("dark")
check("current_mode 变成 dark", theme.current_mode() == "dark", theme.current_mode())
check("BG 变了", theme.BG != light_bg, "{} -> {}".format(light_bg, theme.BG))
check("SURFACE 变了", theme.SURFACE != light_surface,
      "{} -> {}".format(light_surface, theme.SURFACE))
check("TEXT 变了", theme.TEXT != light_text, "{} -> {}".format(light_text, theme.TEXT))

print("\n[4] 生成出来的样式表里没有残留的浅色字面量")
dark_sheet = theme.build_stylesheet()
leftovers = []
for literal in ("#f2f6ff", "#e6edff", "#f1f3f7", "#b9c8ee", "#f2f5ff",
                "#e4e9f2", "#e9edf5", "#fbfcfe", "#c8d1e0", "#a9b6cc"):
    if literal in dark_sheet:
        leftovers.append(literal)
check("深色样式表无浅色残留", not leftovers, str(leftovers))
check("深色样式表里出现了深色底色", "#0d1220" in dark_sheet or "#161d2e" in dark_sheet)

theme.set_mode("light")
light_sheet = theme.build_stylesheet()
check("切回浅色后底色恢复", "#f4f6fa" in light_sheet and "#0d1220" not in light_sheet)
check("样式表长度合理（没有拼接断裂）", len(light_sheet) > 8000, str(len(light_sheet)))

print("\n[5] 样式表括号平衡（f-string 转义容易漏 }}）")
check("浅色样式表括号平衡",
      light_sheet.count("{") == light_sheet.count("}"),
      "{} vs {}".format(light_sheet.count("{"), light_sheet.count("}")))
check("深色样式表括号平衡",
      dark_sheet.count("{") == dark_sheet.count("}"),
      "{} vs {}".format(dark_sheet.count("{"), dark_sheet.count("}")))

print("\n[6] 应用字体/图标在深色下仍可用")
check("app_font 正常", theme.app_font() is not None)
check("mono_font 正常", theme.mono_font(9) is not None)
theme.set_mode("dark")
check("深色下图标能画出来", not theme.icon("settings", theme.TEXT_MUTED, 16, 1.6).isNull())
theme.set_mode("light")
check("浅色下图标能画出来", not theme.icon("package", theme.TEXT_MUTED, 16, 1.6).isNull())

print("\n" + "=" * 46)
if FAILED:
    print("失败 {} 项：{}".format(len(FAILED), "、".join(FAILED)))
    sys.exit(1)
print("主题令牌全部通过")
