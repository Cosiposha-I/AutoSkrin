"""
main.py — точка входа AutoSkrin.

Запуск:
    python main.py              — обычный запуск
    python main.py --minimized  — запуск свёрнутым в трей (используется автозапуском)
    python main.py --start      — сразу начать мониторинг
    python main.py --self-test report.txt — самопроверка сборки (используется при сборке)
"""

from __future__ import annotations

import argparse
import getpass
import logging
import sys
import traceback
from logging.handlers import RotatingFileHandler
from pathlib import Path

from settings import APP_NAME, APP_VERSION, get_config_dir, load_settings

log = logging.getLogger(APP_NAME)

# Имя мьютекса Windows: по нему установщик понимает, что программа запущена
WINDOWS_MUTEX_NAME = "AutoSkrinSingleInstanceMutex"
_mutex_handle = None  # держим ссылку, чтобы мьютекс жил до выхода из программы


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog=APP_NAME, description="Автоскриншоты при изменении экрана")
    parser.add_argument("--minimized", action="store_true", help="запустить свёрнутым в трей")
    parser.add_argument("--start", action="store_true", help="сразу начать мониторинг")
    parser.add_argument("--self-test", metavar="REPORT", help="самопроверка сборки и выход")
    return parser.parse_args(argv)


def setup_logging() -> Path:
    """Лог-файл в папке настроек (ротация: 3 файла по 1 МБ)."""
    log_path = get_config_dir() / "autoskrin.log"
    handlers: list[logging.Handler] = [
        RotatingFileHandler(log_path, maxBytes=1_000_000, backupCount=3, encoding="utf-8")]
    if sys.stderr is not None:  # в собранном exe без консоли stderr отсутствует
        if hasattr(sys.stderr, "reconfigure"):
            # Кириллица не должна ломать вывод в консоль с кодировкой cp1252/cp866
            sys.stderr.reconfigure(errors="backslashreplace")
        handlers.append(logging.StreamHandler())
    logging.basicConfig(level=logging.INFO, handlers=handlers,
                        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    return log_path


def install_excepthook() -> None:
    """Непойманные ошибки пишем в лог и показываем пользователю, а не «молча» падаем."""
    def hook(exc_type, exc, tb):
        text = "".join(traceback.format_exception(exc_type, exc, tb))
        log.critical("Необработанная ошибка:\n%s", text)
        try:
            from PyQt6.QtWidgets import QApplication, QMessageBox
            if QApplication.instance() is not None:
                QMessageBox.critical(None, APP_NAME, f"Произошла непредвиденная ошибка:\n\n{exc}\n\n"
                                                     f"Подробности записаны в лог:\n{get_config_dir()}")
        except Exception:  # noqa: BLE001
            pass
    sys.excepthook = hook


def windows_integration() -> None:
    """Windows: своя группа на панели задач и мьютекс для установщика."""
    global _mutex_handle
    if sys.platform != "win32":
        return
    import ctypes
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(f"{APP_NAME}.App")
        _mutex_handle = ctypes.windll.kernel32.CreateMutexW(None, False, WINDOWS_MUTEX_NAME)
    except Exception:  # noqa: BLE001 — некритично
        log.warning("Не удалось настроить интеграцию с Windows", exc_info=True)


def load_qt_translations(app) -> None:
    """Русские подписи стандартных кнопок Qt («Да», «Нет», «Отмена»)."""
    from PyQt6.QtCore import QLibraryInfo, QTranslator
    translator = QTranslator(app)
    path = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    if translator.load("qtbase_ru", path):
        app.installTranslator(translator)


def notify_running_instance(server_name: str) -> bool:
    """Если программа уже запущена — просим её показать окно и возвращаем True."""
    from PyQt6.QtNetwork import QLocalSocket
    sock = QLocalSocket()
    sock.connectToServer(server_name)
    if not sock.waitForConnected(500):
        return False
    sock.write(b"show")
    sock.flush()
    sock.waitForBytesWritten(500)
    sock.disconnectFromServer()
    return True


def start_instance_server(server_name: str, on_show):
    """Сервер, через который повторный запуск программы «будит» уже открытое окно."""
    from PyQt6.QtNetwork import QLocalServer
    server = QLocalServer()
    if not server.listen(server_name):
        QLocalServer.removeServer(server_name)  # остался от аварийно завершённого процесса
        server.listen(server_name)

    def on_connection():
        conn = server.nextPendingConnection()
        if conn is not None:
            conn.disconnected.connect(conn.deleteLater)
        on_show()

    server.newConnection.connect(on_connection)
    return server


def run_self_test(report_path: str) -> int:
    """
    Самопроверка собранной программы: создаёт окно, захватывает экран,
    сравнивает кадры и сохраняет PNG/JPG во временную папку.
    Результат записывается в текстовый отчёт; код возврата 0 — всё в порядке.
    """
    import tempfile

    from PyQt6.QtWidgets import QApplication

    lines: list[str] = [f"{APP_NAME} {APP_VERSION}, Python {sys.version.split()[0]}, {sys.platform}"]
    ok = True

    def check(name, func):
        nonlocal ok
        try:
            result = func()
            lines.append(f"[OK]   {name}" + (f": {result}" if result else ""))
        except Exception as exc:  # noqa: BLE001
            ok = False
            lines.append(f"[FAIL] {name}: {exc!r}")

    app = QApplication.instance() or QApplication(sys.argv)
    from monitor import (ChangeDetector, compute_change_percent, create_mss, save_image,
                         shot_to_array, shot_to_image)
    from settings import Settings
    from ui import MainWindow, parse_hotkey

    def grab():
        with create_mss() as sct:
            mon = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
            area = {"left": mon["left"], "top": mon["top"],
                    "width": min(200, mon["width"]), "height": min(150, mon["height"])}
            a = shot_to_array(sct.grab(area))
            shot = sct.grab(area)
            b = shot_to_array(shot)
            detector = ChangeDetector(1.0, 12, 0)
            detector.process(a, 0.0)
            detector.process(b, 1.0)
            with tempfile.TemporaryDirectory() as tmp:
                png = save_image(shot_to_image(shot), tmp, "png")
                jpg = save_image(shot_to_image(shot), tmp, "jpg", 85)
                sizes = f"{png.stat().st_size} B PNG, {jpg.stat().st_size} B JPG"
            return (f"мониторов: {len(sct.monitors) - 1}, изменение между кадрами "
                    f"{compute_change_percent(a, b):.2f} %, {sizes}")

    def window():
        with tempfile.TemporaryDirectory() as tmp:
            win = MainWindow(Settings(save_dir=tmp), persist=False)
            win.show()
            app.processEvents()
            hotkey = "глобальная" if win.hotkey.error == "" else f"локальная ({win.hotkey.error})"
            win.quit_app()
            return f"трей: {'есть' if win.tray_available else 'нет'}, горячая клавиша: {hotkey}"

    check("захват экрана и сохранение файлов", grab)
    check("главное окно", window)
    check("разбор горячей клавиши", lambda: str(parse_hotkey("Ctrl+Shift+S")))

    Path(report_path).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    log_path = setup_logging()
    install_excepthook()
    log.info("Запуск %s %s, лог: %s", APP_NAME, APP_VERSION, log_path)

    if args.self_test:
        return run_self_test(args.self_test)

    windows_integration()

    from PyQt6.QtCore import QTimer
    from PyQt6.QtWidgets import QApplication

    from ui import MainWindow, app_icon

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setQuitOnLastWindowClosed(False)  # программа продолжает работать в трее
    app.setWindowIcon(app_icon())
    load_qt_translations(app)

    # Разрешаем только один экземпляр программы на пользователя
    server_name = f"{APP_NAME}-{getpass.getuser()}"
    if notify_running_instance(server_name):
        log.info("Программа уже запущена — показываем её окно")
        return 0

    window = MainWindow(load_settings())
    # Ссылку на сервер храним в окне, иначе сборщик мусора его уничтожит
    window.instance_server = start_instance_server(server_name, window.show_window)

    if not (args.minimized and window.tray_available):
        window.show()
    if args.start or window.settings.autostart_monitoring:
        # Небольшая задержка — даём окну и трею появиться
        QTimer.singleShot(800, lambda: window.start_monitoring(interactive=False))

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
