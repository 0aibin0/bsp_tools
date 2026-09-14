"""列出当前所有可见的顶层窗口，用于确认 exe 真的把界面显示出来了。

用法：
    .venv\\Scripts\\python.exe devtools\\list_windows.py [关键字]
"""

import ctypes
import ctypes.wintypes as wt
import sys

user32 = ctypes.windll.user32

keyword = sys.argv[1].lower() if len(sys.argv) > 1 else ""
found = []


def callback(hwnd, _lparam):
    if not user32.IsWindowVisible(hwnd):
        return True
    length = user32.GetWindowTextLengthW(hwnd)
    if length == 0:
        return True
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    title = buf.value
    if keyword and keyword not in title.lower():
        return True

    pid = wt.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    cls = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, cls, 256)
    rect = wt.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    found.append({
        "hwnd": hwnd,
        "pid": pid.value,
        "title": title,
        "class": cls.value,
        "size": f"{rect.right - rect.left}x{rect.bottom - rect.top}",
    })
    return True


EnumWindowsProc = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
user32.EnumWindows(EnumWindowsProc(callback), 0)

for item in found:
    print(item)
print(f"matched: {len(found)}")
