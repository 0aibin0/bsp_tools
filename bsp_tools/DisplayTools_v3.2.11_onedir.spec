# -*- mode: python ; coding: utf-8 -*-
#
# DisplayTools v3.2.11 打包配置（**目录版** onedir，给固定工位用）
#
# 和单文件版的区别：onefile 每次启动都要把 30+MB 解压到临时目录，冷启动
# 明显慢一拍（实测 1.79s vs 0.91s）；目录版解压一次就完事，双击秒开。
# 代价是 140 个文件、95MB，不方便单独拷一个 exe 给别人——两个版本并存，
# 按场景选。onedir 产物已在 .gitignore 里排除，不进仓库。
#
# 使用：pyinstaller DisplayTools_v3.2.11_onedir.spec
# 产物：dist/DisplayTools_v3.2.11_onedir/DisplayTools_v3.2.11_onedir.exe

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
    [],
    exclude_binaries=True,          # 关键差异：依赖不塞进 exe，放到旁边的目录
    name='DisplayTools_v3.2.11_onedir',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['icon_img\\main.ico'],
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='DisplayTools_v3.2.11_onedir',
)
