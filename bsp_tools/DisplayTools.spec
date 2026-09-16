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
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['icon_img\\main.ico'],
)
