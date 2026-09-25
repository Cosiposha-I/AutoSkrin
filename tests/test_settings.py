"""Тесты модуля settings: значения по умолчанию, сохранение, защита от мусора в конфиге."""

import json

from settings import (CAPTURE_SCREEN, DEFAULT_HOTKEY, TIMER_AT, Region, Settings,
                      check_docx_target, check_folder_writable, load_settings, save_settings)


def test_defaults_when_file_missing(tmp_path):
    s = load_settings(tmp_path / "nope.json")
    assert s.interval_sec == 1.0
    assert s.region is None
    assert s.image_format == "png"
    assert s.hotkey == "Ctrl+Alt+S" == DEFAULT_HOTKEY
    assert s.save_to_folder and not s.save_to_docx
    assert s.docx_path.endswith("Конспект.docx")
    assert not s.timer_enabled and s.timer_minutes == 90


def test_roundtrip(tmp_path):
    path = tmp_path / "settings.json"
    s = Settings(save_dir=str(tmp_path / "shots"), region=Region(10, 20, 300, 200),
                 interval_sec=2.5, threshold_percent=0.5, capture_mode=CAPTURE_SCREEN,
                 image_format="jpg", jpeg_quality=70, notifications_enabled=False,
                 autostart_monitoring=True, save_to_folder=False, save_to_docx=True,
                 docx_path=str(tmp_path / "Лекция.docx"), docx_captions=False,
                 timer_enabled=True, timer_mode=TIMER_AT, timer_minutes=45, timer_at="15:30",
                 hotkey="Ctrl+F9")
    save_settings(s, path)
    loaded = load_settings(path)
    assert loaded == s
    # Файл читаемый и в UTF-8
    assert json.loads(path.read_text(encoding="utf-8"))["region"]["width"] == 300


def test_cyrillic_folder_saved_as_is(tmp_path):
    path = tmp_path / "settings.json"
    folder = str(tmp_path / "Разработка" / "Скриншоты")
    save_settings(Settings(save_dir=folder), path)
    assert load_settings(path).save_dir == folder
    assert "Разработка" in path.read_text(encoding="utf-8")


def test_invalid_values_are_fixed(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({
        "interval_sec": -5, "threshold_percent": 500, "pixel_tolerance": "abc",
        "min_interval_sec": True, "capture_mode": "weird", "image_format": "JPEG",
        "jpeg_quality": 1000, "region": {"left": 0, "top": 0, "width": 0, "height": 10},
        "unknown_key": 1,
    }), encoding="utf-8")
    s = load_settings(path)
    assert s.interval_sec == 0.1          # ограничено снизу
    assert s.threshold_percent == 100.0   # ограничено сверху
    assert s.pixel_tolerance == 12        # мусор → значение по умолчанию
    assert s.min_interval_sec == 5.0      # bool не считается числом
    assert s.capture_mode == "region"
    assert s.image_format == "jpg"        # «JPEG» понимается как jpg
    assert s.jpeg_quality == 100
    assert s.region is None               # нулевая ширина — область недействительна


def test_corrupted_file_is_backed_up(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("{ это не json", encoding="utf-8")
    s = load_settings(path)
    assert s == Settings()
    assert (tmp_path / "settings.json.bak").exists()
    assert not path.exists()


def test_copy_is_independent():
    s = Settings(region=Region(1, 2, 3, 4))
    c = s.copy()
    c.region.left = 100
    assert s.region.left == 1


def test_region_helpers():
    r = Region(100, 50, 200, 100)
    assert r.as_mss() == {"left": 100, "top": 50, "width": 200, "height": 100}
    assert r.center() == (200, 100)
    assert "ширина: 200" in str(r)
    assert Region.from_dict({"left": 1, "top": 2, "width": 3}) is None
    assert Region.from_dict("garbage") is None


def test_check_folder_writable(tmp_path):
    assert check_folder_writable(str(tmp_path / "new" / "folder")) is None
    assert (tmp_path / "new" / "folder").is_dir()
    assert check_folder_writable("") is not None
    blocker = tmp_path / "file.txt"
    blocker.write_text("x")
    # Папку нельзя создать внутри обычного файла
    assert "Нет доступа" in check_folder_writable(str(blocker / "sub"))


def test_old_default_hotkey_is_migrated():
    assert Settings.from_dict({"hotkey": "Ctrl+Shift+S"}).hotkey == "Ctrl+Alt+S"
    assert Settings.from_dict({"hotkey": "Ctrl+Alt+F5"}).hotkey == "Ctrl+Alt+F5"


def test_timer_values_are_validated():
    s = Settings.from_dict({"timer_mode": "never", "timer_at": "25:99", "timer_minutes": 100000})
    assert s.timer_mode == "after"
    assert s.timer_at == "18:00"
    assert s.timer_minutes == 23 * 60 + 59
    assert Settings.from_dict({"timer_at": "7:05"}).timer_at == "07:05"


def write_json(path, data, bom=False):
    text = json.dumps(data, ensure_ascii=False)
    path.write_bytes((b"\xef\xbb\xbf" if bom else b"") + text.encode("utf-8"))


INSTALLER = {"install_id": "20260101120000", "apply_to_existing": False,
             "save_dir": "D:\\Лекции", "image_format": "jpg", "save_to_docx": True,
             "interval_sec": 2.5, "notifications_enabled": False}


def test_installer_defaults_used_on_first_run(tmp_path):
    defaults = tmp_path / "defaults.json"
    write_json(defaults, INSTALLER, bom=True)   # установщик пишет файл с BOM
    s = load_settings(tmp_path / "settings.json", defaults)
    assert s.save_dir == "D:\\Лекции"
    assert s.image_format == "jpg" and s.save_to_docx and s.interval_sec == 2.5
    assert not s.notifications_enabled
    assert s.applied_defaults_id == "20260101120000"


def test_installer_keeps_existing_settings(tmp_path):
    user = tmp_path / "settings.json"
    save_settings(Settings(image_format="png", region=Region(1, 2, 30, 40)), user)
    defaults = tmp_path / "defaults.json"
    write_json(defaults, INSTALLER)             # «Оставить текущие настройки»
    s = load_settings(user, defaults)
    assert s.image_format == "png"


def test_installer_replaces_existing_settings_once(tmp_path):
    user = tmp_path / "settings.json"
    save_settings(Settings(image_format="png", region=Region(1, 2, 30, 40)), user)
    defaults = tmp_path / "defaults.json"
    write_json(defaults, {**INSTALLER, "apply_to_existing": True, "region": None})
    s = load_settings(user, defaults)
    assert s.image_format == "jpg"
    assert s.region == Region(1, 2, 30, 40)     # выбранная область не сбрасывается
    # Настройки установщика применяются один раз: дальнейшие изменения пользователя сохраняются
    s.image_format = "png"
    save_settings(s, user)
    assert load_settings(user, defaults).image_format == "png"


def test_check_docx_target(tmp_path):
    assert check_docx_target(str(tmp_path / "new" / "Конспект.docx")) is None
    assert "расширение .docx" in check_docx_target(str(tmp_path / "notes.txt"))
    assert "Не выбран" in check_docx_target("")
    fake = tmp_path / "fake.docx"
    fake.write_text("not a zip")
    assert "не является документом" in check_docx_target(str(fake))
