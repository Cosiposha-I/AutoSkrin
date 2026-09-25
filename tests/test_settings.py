"""Тесты модуля settings: значения по умолчанию, сохранение, защита от мусора в конфиге."""

import json

from settings import (CAPTURE_SCREEN, Region, Settings, check_folder_writable, load_settings,
                      save_settings)


def test_defaults_when_file_missing(tmp_path):
    s = load_settings(tmp_path / "nope.json")
    assert s.interval_sec == 1.0
    assert s.region is None
    assert s.image_format == "png"
    assert s.hotkey == "Ctrl+Shift+S"


def test_roundtrip(tmp_path):
    path = tmp_path / "settings.json"
    s = Settings(save_dir=str(tmp_path / "shots"), region=Region(10, 20, 300, 200),
                 interval_sec=2.5, threshold_percent=0.5, capture_mode=CAPTURE_SCREEN,
                 image_format="jpg", jpeg_quality=70, notifications_enabled=False,
                 autostart_monitoring=True)
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
