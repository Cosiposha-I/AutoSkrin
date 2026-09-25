"""
test_installer.py — проверка установщика на Windows (запускается в GitHub Actions
после сборки, можно запустить и вручную).

Сценарий 1 «обновление с заменой настроек»:
  1. у пользователя уже есть настройки (выбрана область, формат PNG);
  2. тихая установка с параметрами: своя папка установки (с пробелами и кириллицей),
     исходный код, ярлык на рабочем столе, папка и документ Word для скриншотов и т.д.;
  3. проверяются файлы, ярлыки и defaults.json;
  4. установленная программа проходит самопроверку и видит новые настройки,
     сохранив выбранную ранее область;
  5. тихое удаление вместе с настройками — всё должно исчезнуть.

Сценарий 2 «универсальный деинсталлятор» (uninstall.bat):
  на компьютере установленная версия с автозапуском и версия из исходного кода
  с ярлыком на рабочем столе; uninstall.bat /y /settings /source должен убрать всё.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SETUP = ROOT / "dist" / "AutoSkrin-Setup.exe"

failures: list[str] = []


def check(condition: bool, text: str) -> None:
    print(("[OK]   " if condition else "[FAIL] ") + text, flush=True)
    if not condition:
        failures.append(text)


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")
    if sys.platform != "win32":
        print("Проверка установщика возможна только в Windows")
        return 0

    base = Path(tempfile.mkdtemp(prefix="autoskrin-test-"))
    app_dir = base / "Мои программы" / "AutoSkrin Тест"
    shots = base / "Скриншоты лекций"
    docx = base / "Конспекты" / "Лекция 1.docx"
    appdata = Path(os.environ["APPDATA"]) / "AutoSkrin"
    desktop_link = Path(os.environ["USERPROFILE"]) / "Desktop" / "AutoSkrin.lnk"
    start_menu = Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "AutoSkrin"

    # 1. «Старая» установка: настройки пользователя уже есть
    appdata.mkdir(parents=True, exist_ok=True)
    (appdata / "settings.json").write_text(json.dumps({
        "image_format": "png", "region": {"left": 10, "top": 20, "width": 300, "height": 200},
    }), encoding="utf-8")

    # 2. Тихая установка с параметрами
    log_file = base / "setup.log"
    args = [str(SETUP), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CURRENTUSER",
            f"/DIR={app_dir}", "/COMPONENTS=main,source", "/TASKS=desktopicon",
            f"/LOG={log_file}", "/KEEPSETTINGS=0", f"/SHOTSDIR={shots}", "/SAVETODOCX=1",
            f"/DOCX={docx}", "/CAPTURE=screen", "/FORMAT=jpg", "/INTERVAL=2,5",
            "/THRESHOLD=0.5", "/MININTERVAL=10", "/NOTIFY=0", "/AUTOSTARTMON=1", "/TRAY=1"]
    code = subprocess.run(args, timeout=600).returncode
    check(code == 0, f"установка завершилась успешно (код {code})")
    if code != 0 and log_file.exists():
        print(log_file.read_text(encoding="utf-8", errors="replace")[-4000:])
        return 1

    # 3. Файлы, ярлыки и настройки установщика
    exe = app_dir / "AutoSkrin.exe"
    check(exe.exists(), f"программа установлена в выбранную папку: {exe}")
    check((app_dir / "source" / "main.py").exists(), "исходный код установлен (компонент source)")
    check(desktop_link.exists(), "ярлык на рабочем столе")
    check((start_menu / "AutoSkrin.lnk").exists(), "ярлык в меню «Пуск»")
    check(any(start_menu.glob("*.url")), "ссылка на инструкцию в меню «Пуск»")
    check(any(app_dir.glob("*.lnk")), "ярлык «Удалить AutoSkrin» в папке программы")

    defaults_path = app_dir / "defaults.json"
    defaults = json.loads(defaults_path.read_text(encoding="utf-8-sig")) if defaults_path.exists() else {}
    print("defaults.json:", json.dumps(defaults, ensure_ascii=False))
    expected = {
        "save_dir": str(shots), "save_to_folder": True, "save_to_docx": True, "docx_path": str(docx),
        "capture_mode": "screen", "image_format": "jpg", "interval_sec": 2.5,
        "threshold_percent": 0.5, "min_interval_sec": 10, "notifications_enabled": False,
        "autostart_monitoring": True, "minimize_to_tray": True, "apply_to_existing": True,
    }
    for key, value in expected.items():
        check(defaults.get(key) == value, f"defaults.json: {key} = {value!r} (есть {defaults.get(key)!r})")

    # 4. Самопроверка установленной программы: новые настройки + сохранённая область
    report = base / "self-test.txt"
    code = subprocess.run([str(exe), "--self-test", str(report)], timeout=180).returncode
    text = report.read_text(encoding="utf-8") if report.exists() else ""
    print(text)
    check(code == 0, "самопроверка установленной программы")
    for part in (f"папка=True:{shots}", f"word=True:{docx}", "формат=jpg", "снимать=screen",
                 "интервал=2.5", "уведомления=False", "автостарт=True", "область=X: 10, Y: 20",
                 "клавиша=Ctrl+Alt+S"):
        check(part in text, f"программа применила настройку: {part}")

    # 5. Тихое удаление вместе с настройками
    uninstaller = app_dir / "unins000.exe"
    subprocess.run([str(uninstaller), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART",
                    "/DELETESETTINGS=1"], timeout=300)
    deadline = time.time() + 180  # деинсталлятор перезапускает себя из TEMP и работает в фоне
    while time.time() < deadline and (exe.exists() or appdata.exists()):
        time.sleep(2)
    check(not exe.exists(), "программа удалена")
    check(not defaults_path.exists(), "defaults.json удалён")
    check(not desktop_link.exists(), "ярлык с рабочего стола удалён")
    check(not start_menu.exists(), "папка в меню «Пуск» удалена")
    check(not appdata.exists(), "настройки удалены (/DELETESETTINGS=1)")

    check_universal_uninstaller(base, appdata, desktop_link, start_menu)

    print(f"\nИтого ошибок: {len(failures)}")
    return 1 if failures else 0


def run_key_value(name: str) -> str | None:
    """Значение автозапуска из HKCU\\...\\Run (None — нет)."""
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Run") as key:
            return winreg.QueryValueEx(key, name)[0]
    except OSError:
        return None


def uninstall_key_exists() -> bool:
    import winreg
    path = (r"Software\Microsoft\Windows\CurrentVersion\Uninstall"
            r"\{6F2B8C1E-4A7D-4E59-9B3A-2C5D8E1F0A37}_is1")
    try:
        winreg.OpenKey(winreg.HKEY_CURRENT_USER, path).Close()
        return True
    except OSError:
        return False


def check_universal_uninstaller(base: Path, appdata: Path, desktop_link: Path, start_menu: Path) -> None:
    print("\n=== Универсальный деинсталлятор (uninstall.bat) ===", flush=True)
    app_dir = base / "Вторая установка"
    code = subprocess.run([str(SETUP), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CURRENTUSER",
                           f"/DIR={app_dir}", "/COMPONENTS=main", "/TASKS=autorun"], timeout=600).returncode
    check(code == 0 and (app_dir / "AutoSkrin.exe").exists(), "повторная установка (с автозапуском)")
    check(uninstall_key_exists(), "программа есть в списке установленных")
    check(bool(run_key_value("AutoSkrin")), "автозапуск включён")

    # «Версия из исходного кода», как её делает install.bat: папка, .venv и ярлык на рабочем столе
    source = base / "Разработка" / "AutoSkrin-исходники"
    (source / ".venv").mkdir(parents=True)
    (source / "main.py").write_text("# test", encoding="utf-8")
    import win32com.client
    link = win32com.client.Dispatch("WScript.Shell").CreateShortcut(str(desktop_link))
    link.TargetPath = sys.executable
    link.Arguments = f'"{source / "main.py"}"'
    link.Save()
    appdata.mkdir(parents=True, exist_ok=True)
    (appdata / "settings.json").write_text("{}", encoding="utf-8")

    result = subprocess.run(["cmd", "/c", str(ROOT / "uninstall.bat"), "/y", "/settings", "/source"],
                            capture_output=True, timeout=600)
    print(result.stdout.decode("utf-8", errors="replace"))
    print(result.stderr.decode("utf-8", errors="replace"))
    check(result.returncode == 0, f"uninstall.bat завершился успешно (код {result.returncode})")

    deadline = time.time() + 60
    while time.time() < deadline and (app_dir / "AutoSkrin.exe").exists():
        time.sleep(2)
    check(not (app_dir / "AutoSkrin.exe").exists(), "установленная версия удалена")
    check(not uninstall_key_exists(), "запись в списке программ удалена")
    check(run_key_value("AutoSkrin") is None, "автозапуск удалён")
    check(not source.exists(), "папка с исходным кодом удалена (/source)")
    check(not desktop_link.exists(), "ярлык на рабочем столе удалён")
    check(not start_menu.exists(), "папка в меню «Пуск» удалена")
    check(not appdata.exists(), "настройки удалены (/settings)")


if __name__ == "__main__":
    sys.exit(main())
