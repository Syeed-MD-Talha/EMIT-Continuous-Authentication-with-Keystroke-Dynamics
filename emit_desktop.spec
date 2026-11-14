from pathlib import Path
import sys

root = Path(SPECPATH)
app_icon = root / "desktop" / "assets" / "emit.ico"

a = Analysis(
    [str(root / "emit_desktop.py")],
    pathex=[str(root)],
    binaries=[],
    datas=[(str(app_icon), "desktop/assets")],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "matplotlib",
        "streamlit",
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineWidgets",
        "PySide6.QtWebEngineQuick",
        "PySide6.QtWebChannel",
        "PySide6.QtWebSockets",
        "PySide6.QtPdf",
        "PySide6.QtPdfWidgets",
        "PySide6.QtMultimedia",
        "PySide6.QtMultimediaWidgets",
        "PySide6.QtBluetooth",
        "PySide6.QtPositioning",
        "PySide6.QtSerialPort",
        "PySide6.QtTest",
    ],
    noarchive=False,
)

if sys.platform == "win32":
    # Qt links against the Windows ICU exports. A third-party icuuc.dll on
    # the build machine's PATH can shadow it and fail at QtNetwork import.
    # Windows 10 and 11 also provide the UCRT and API-set DLLs.
    def uses_windows_copy(destination):
        name = Path(destination).name.lower()
        return name in {"icuuc.dll", "ucrtbase.dll"} or name.startswith("api-ms-win-")

    a.binaries = [
        entry for entry in a.binaries if not uses_windows_copy(entry[0])
    ]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="EMITDesktop",
    icon=str(app_icon),
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="EMITDesktop",
)
