"""
build.py — сборка Windows-версии AutoSkrin.

Шаги:
  1. PyInstaller собирает программу в папку dist/AutoSkrin (AutoSkrin.exe + библиотеки);
  2. собранный exe проходит самопроверку (--self-test);
  3. из папки делается переносная версия dist/AutoSkrin-Portable.zip;
  4. Inno Setup создаёт установщик dist/AutoSkrin-Setup.exe;
  5. рядом кладётся универсальный деинсталлятор dist/AutoSkrin-Uninstall.bat.

Запуск (из корня проекта, в Windows):
    python tools/build.py                 — всё сразу
    python tools/build.py --skip-self-test
    python tools/build.py --require-installer  — ошибка, если Inno Setup не найден (для CI)

Нужны: pip install -r requirements.txt pyinstaller; Inno Setup 6 (https://jrsoftware.org/isdl.php).
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from settings import APP_NAME, APP_VERSION  # noqa: E402

DIST = ROOT / "dist"
BUILD = ROOT / "build"
APP_DIR = DIST / APP_NAME
ICON = ROOT / "assets" / "icon.ico"
ISS = ROOT / "installer" / "AutoSkrin.iss"
PORTABLE_ZIP = DIST / f"{APP_NAME}-Portable.zip"
SETUP_EXE = DIST / f"{APP_NAME}-Setup.exe"
UNINSTALL_BAT = DIST / f"{APP_NAME}-Uninstall.bat"


def step(text: str) -> None:
    print(f"\n=== {text} ===", flush=True)


def run(cmd: list[str], **kwargs) -> None:
    print(">", " ".join(str(c) for c in cmd), flush=True)
    subprocess.run([str(c) for c in cmd], check=True, **kwargs)


def write_version_info() -> Path:
    """Сведения о версии, которые Windows показывает в свойствах exe-файла."""
    nums = tuple(int(x) for x in APP_VERSION.split(".")) + (0,) * (4 - len(APP_VERSION.split(".")))
    text = f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={nums}, prodvers={nums}, mask=0x3f, flags=0x0,
                    OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040904B0', [
      StringStruct('CompanyName', '{APP_NAME}'),
      StringStruct('FileDescription', '{APP_NAME} - automatic screenshots on screen changes'),
      StringStruct('FileVersion', '{APP_VERSION}'),
      StringStruct('InternalName', '{APP_NAME}'),
      StringStruct('OriginalFilename', '{APP_NAME}.exe'),
      StringStruct('ProductName', '{APP_NAME}'),
      StringStruct('ProductVersion', '{APP_VERSION}')])]),
    VarFileInfo([VarStruct('Translation', [0x0409, 1200])])
  ]
)
"""
    BUILD.mkdir(exist_ok=True)
    path = BUILD / "version_info.txt"
    path.write_text(text, encoding="utf-8")
    return path


def build_exe() -> Path:
    step("Сборка программы (PyInstaller)")
    if not ICON.exists():
        run([sys.executable, ROOT / "tools" / "make_icon.py"])
    shutil.rmtree(APP_DIR, ignore_errors=True)
    run([sys.executable, "-m", "PyInstaller",
         "--noconfirm", "--clean",
         "--windowed",                      # без консольного окна
         "--name", APP_NAME,
         "--icon", ICON,
         "--version-file", write_version_info(),
         "--distpath", DIST,
         "--workpath", BUILD / "pyinstaller",
         "--specpath", BUILD,
         "--exclude-module", "tkinter",
         "--exclude-module", "pytest",
         ROOT / "main.py"], cwd=ROOT)
    exe = APP_DIR / f"{APP_NAME}.exe"
    if sys.platform == "win32" and not exe.exists():
        raise SystemExit(f"Не найден собранный файл {exe}")
    return exe


def self_test(exe: Path) -> None:
    step("Самопроверка собранной программы")
    report = BUILD / "self-test.txt"
    report.unlink(missing_ok=True)
    target = exe if exe.exists() else APP_DIR / APP_NAME  # Linux/macOS: файл без .exe
    code = subprocess.run([str(target), "--self-test", str(report)], timeout=180).returncode
    print(report.read_text(encoding="utf-8") if report.exists() else "(отчёт не создан)")
    if code != 0:
        raise SystemExit(f"Самопроверка не пройдена (код {code})")


def make_portable_zip() -> None:
    step("Переносная версия (ZIP)")
    PORTABLE_ZIP.unlink(missing_ok=True)
    with zipfile.ZipFile(PORTABLE_ZIP, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for file in sorted(APP_DIR.rglob("*")):
            if file.is_file():
                zf.write(file, Path(APP_NAME) / file.relative_to(APP_DIR))
    print(f"Готово: {PORTABLE_ZIP} ({PORTABLE_ZIP.stat().st_size / 1e6:.1f} МБ)")


def find_iscc() -> Path | None:
    """Ищет компилятор Inno Setup (ISCC.exe) в PATH и стандартных папках."""
    found = shutil.which("iscc") or shutil.which("ISCC")
    if found:
        return Path(found)
    for base in (os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles"),
                 os.environ.get("LOCALAPPDATA") and Path(os.environ["LOCALAPPDATA"]) / "Programs"):
        if base:
            candidate = Path(base) / "Inno Setup 6" / "ISCC.exe"
            if candidate.exists():
                return candidate
    return None


def build_installer(required: bool) -> None:
    step("Установщик (Inno Setup)")
    iscc = find_iscc()
    if iscc is None:
        msg = ("Inno Setup 6 не найден — установщик не создан. Скачайте его с "
               "https://jrsoftware.org/isdl.php или выполните: winget install JRSoftware.InnoSetup")
        if required:
            raise SystemExit(msg)
        print("ВНИМАНИЕ:", msg)
        return
    SETUP_EXE.unlink(missing_ok=True)
    run([iscc, f"/DMyAppVersion={APP_VERSION}", ISS])
    print(f"Готово: {SETUP_EXE} ({SETUP_EXE.stat().st_size / 1e6:.1f} МБ)")


def main() -> None:
    # Консоль Windows (и логи CI) могут быть в cp1252/cp866 — выводим в UTF-8,
    # иначе печать русского текста завершится ошибкой UnicodeEncodeError
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Сборка AutoSkrin для Windows")
    parser.add_argument("--skip-self-test", action="store_true")
    parser.add_argument("--require-installer", action="store_true")
    args = parser.parse_args()

    print(f"{APP_NAME} {APP_VERSION}, Python {sys.version.split()[0]}")
    exe = build_exe()
    if not args.skip_self_test:
        self_test(exe)
    make_portable_zip()
    if sys.platform == "win32":
        build_installer(args.require_installer)
    # Универсальный деинсталлятор (удаляет любую версию программы)
    shutil.copyfile(ROOT / "uninstall.bat", UNINSTALL_BAT)
    print(f"Готово: {UNINSTALL_BAT}")

    # Версия для GitHub Actions (используется при публикации релиза)
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as f:
            f.write(f"version={APP_VERSION}\n")
    step("Сборка завершена")


if __name__ == "__main__":
    main()
