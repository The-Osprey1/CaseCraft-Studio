# PyInstaller spec for CaseCraft Studio (one-folder, windowed).
# Build from the repository root:   pyinstaller desktop/casecraft.spec --noconfirm
# Output: dist/CaseCraftStudio/CaseCraftStudio.exe  (+ _internal/)
import sys
from pathlib import Path

from PyInstaller.utils.hooks import (collect_all, collect_delvewheel_libs_directory, collect_submodules,
                                     copy_metadata)

ROOT = Path(SPECPATH).resolve().parent          # noqa: F821 -- SPECPATH is injected by PyInstaller
DESKTOP = ROOT / "desktop"
sys.path.insert(0, str(ROOT))
from version import __version__  # noqa: E402

datas = [
    (str(ROOT / "presets"), "presets"),
    (str(ROOT / "schema"), "schema"),
    (str(ROOT / "web" / "dist"), "web/dist"),
    (str(DESKTOP / "icon.ico"), "desktop"),
]
binaries = []
hiddenimports = [
    "desktop_bridge",
    "server", "appdirs", "projects", "version",
    "bambu_3mf", "cad_engine", "dfm", "print_in_place", "params", "printers", "safe_ops", "verify",
    "uvicorn.loops.asyncio", "uvicorn.protocols.http.h11_impl", "uvicorn.lifespan.off",
    "clr", "webview.platforms.winforms", "webview.platforms.edgechromium",
]

# CAD kernel and geometry stack: code + data files + DLLs
for pkg in ("OCP", "build123d", "ocpsvg", "ocp_gordon", "trimesh", "shapely", "svgelements", "ezdxf",
            "lib3mf", "anytree", "webview", "networkx"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h
# OCP's DLLs live in a delvewheel ".libs" folder beside the package
datas, binaries = collect_delvewheel_libs_directory("OCP", libdir_name="cadquery_ocp_novtk.libs",
                                                    datas=datas, binaries=binaries)
hiddenimports += collect_submodules("uvicorn")

# Distribution metadata read at runtime (version strings, diagnostics)
for dist in ("build123d", "cadquery-ocp-novtk", "trimesh", "shapely", "pywebview", "fastapi", "uvicorn",
             "starlette", "pydantic", "numpy", "lib3mf", "ezdxf", "svgelements"):
    try:
        datas += copy_metadata(dist)
    except Exception:  # noqa: BLE001 -- optional
        pass

a = Analysis(  # noqa: F821
    [str(DESKTOP / "app.py")],
    pathex=[str(ROOT), str(DESKTOP)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "pytest", "_pytest", "PyQt5", "PyQt6", "PySide2", "PySide6",
              "gi", "cefpython3", "notebook", "jupyterlab", "test_api", "test_geometry"],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)  # noqa: F821

# Windows version resource (Explorer > Properties > Details)
_v = tuple(int(x) for x in (__version__.split(".") + ["0", "0", "0"])[:4])
version_file = DESKTOP / "build" / "version_info.txt"
version_file.parent.mkdir(parents=True, exist_ok=True)
version_file.write_text(f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={_v}, prodvers={_v}, mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1,
                    subtype=0x0, date=(0, 0)),
  kids=[StringFileInfo([StringTable('040904B0', [
      StringStruct('CompanyName', 'CaseCraft Studio'),
      StringStruct('FileDescription', 'CaseCraft Studio'),
      StringStruct('FileVersion', '{__version__}'),
      StringStruct('InternalName', 'CaseCraftStudio'),
      StringStruct('OriginalFilename', 'CaseCraftStudio.exe'),
      StringStruct('ProductName', 'CaseCraft Studio'),
      StringStruct('ProductVersion', '{__version__}')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])])
""", encoding="utf-8")

exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="CaseCraftStudio",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,                       # UPX-packed DLLs trigger antivirus false positives
    console=False,
    disable_windowed_traceback=False,
    icon=str(DESKTOP / "icon.ico"),
    version=str(version_file),
)
coll = COLLECT(  # noqa: F821
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="CaseCraftStudio",
)
