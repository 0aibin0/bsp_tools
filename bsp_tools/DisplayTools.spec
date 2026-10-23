# -*- mode: python ; coding: utf-8 -*-
#
# DisplayTools 打包配置（单文件 + 无控制台）
#
# 产物固定叫 dist/DisplayTools.exe，**不带版本号**：
#   - 版本号只在 theme.APP_VERSION 和 git tag 里，文件名里不重复一份；
#   - 「检查更新」下载下来的文件才会带版本号（免得顶掉正在运行的自己），
#     见 update_check.default_download_name()。
#
# 等价于命令行方式：
#   pyinstaller --onefile --noconsole --icon=icon_img/main.ico --name DisplayTools mainwindow.py
# 额外补上了 datas（icon_img/）与 excludes（见下）。
#
# 注意：config.ini / favorites.json / path_bookmarks.json / adb_commands.log /
# sitepack/ / crash.log 都是运行时生成在 exe 同目录的，不打包进来
# （打包了会被解到临时目录，没法持久化）。
#
# 使用：
#   cd bsp_tools
#   ..\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean DisplayTools.spec

# 用不到的 Qt 模块。实测这组 excludes 并不能显著减小体积（PyQt5 的 wheel
# 本来就是按需导入的，大头是 Qt5Core/Gui/Widgets + Python 运行时），留着是为了
# 防止依赖分析把 WebEngine 这类大件顺进来。注意 QtNetwork 不能排——
# 单实例守卫要用。
EXCLUDES = [
    'PyQt5.QtQml', 'PyQt5.QtQuick', 'PyQt5.QtQuickWidgets', 'PyQt5.QtQuick3D',
    'PyQt5.QtWebEngine', 'PyQt5.QtWebEngineCore', 'PyQt5.QtWebEngineWidgets',
    'PyQt5.QtWebChannel', 'PyQt5.QtWebSockets',
    'PyQt5.QtMultimedia', 'PyQt5.QtMultimediaWidgets',
    'PyQt5.QtBluetooth', 'PyQt5.QtNfc', 'PyQt5.QtPositioning',
    'PyQt5.QtLocation', 'PyQt5.QtSensors', 'PyQt5.QtSerialPort',
    'PyQt5.QtSql', 'PyQt5.QtTest', 'PyQt5.QtDesigner', 'PyQt5.QtHelp',
    'PyQt5.QtXmlPatterns', 'PyQt5.QtTextToSpeech', 'PyQt5.QtRemoteObjects',
    'PyQt5.QtOpenGL', 'PyQt5.Qt3DCore', 'PyQt5.QtCharts', 'PyQt5.QtDataVisualization',
    'tkinter', 'unittest', 'pydoc', 'doctest', 'pdb',
]

# PyQt5 的 hook 会把整个 Qt5/bin 目录搬进来，光靠上面的 excludes（只作用于
# Python 模块）拦不住这些 DLL。而单文件版启动时每个 DLL 都要从包里解出来，
# 93MB 的解包量是冷启动的主要成本之一。
#
# 下面这些实测都没被用到（QML 引擎、软件 OpenGL、Designer、QtWebEngine 的
# 加密库、打印机后端等）。按文件名前缀过滤，被误判时只要从列表里去掉即可。
# QtNetwork 依赖 libcrypto/libeay 的部分：本项目只用 QLocalServer/Socket，
# 不需要 TLS，去掉后单实例守卫仍然正常（已由 smoke_start 覆盖）。
BINARY_SKIP_PREFIXES = (
    'qt5qml', 'qt5quick', 'qt5quickparticles', 'qt5quickshapes',
    'opengl32sw', 'qt5designer', 'libglesv2', 'libegl',
    'qt5xmlpatterns', 'qt5xml', 'qt5help',
    'qt5printsupport', 'qt5sensors', 'qt5serialport', 'qt5sql',
    'qt5multimedia', 'qt5websockets', 'qt5webchannel',
    'qt5texttospeech', 'qt5positioning', 'qt5location',
    'd3dcompiler_47', 'qml',
)


def _skip_binary(entry):
    """按文件名前缀判断这个二进制/数据项要不要丢。"""
    import os as _os
    name = _os.path.basename(str(entry[0])).lower()
    return not any(name.startswith(prefix) for prefix in BINARY_SKIP_PREFIXES)


a = Analysis(
    ['mainwindow.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('icon_img', 'icon_img'),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDES,
    noarchive=False,
)

# 过滤掉用不到的 Qt 二进制（见 BINARY_SKIP_PREFIXES 的说明）
a.binaries = [item for item in a.binaries if _skip_binary(item)]
a.datas = [item for item in a.datas if _skip_binary(item)]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='DisplayTools',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    # 单文件版默认解包到 %TEMP%（在系统盘），某些安全策略会拦「从 C: 临时目录
    # 加载 DLL」，表现就是启动弹 "Failed to load Python DLL ... 找不到指定的模块"
    # （实测：解包到 C: 任何目录都失败，解包到 D: 就正常）。
    # 改成 '.'（相对当前工作目录）——双击启动时 CWD 就是 exe 所在目录，
    # 解包落在 exe 旁边，不碰系统 Temp。更新器启动新版本时会显式设 WorkingDirectory。
    runtime_tmpdir='.',
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['icon_img\\main.ico'],
)
