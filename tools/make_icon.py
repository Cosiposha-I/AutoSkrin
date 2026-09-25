"""
make_icon.py — создаёт файлы иконки assets/icon.ico и assets/icon.png.

Иконка рисуется той же функцией, что и в программе (ui.make_icon_pixmap),
поэтому ярлык, exe-файл и значок в трее выглядят одинаково.
Запуск: python tools/make_icon.py
"""

import io
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")  # окно не нужно

from PIL import Image  # noqa: E402
from PyQt6.QtCore import QBuffer, QIODevice  # noqa: E402
from PyQt6.QtGui import QGuiApplication  # noqa: E402

from ui import make_icon_pixmap  # noqa: E402

SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)
_app = None


def render(size: int) -> Image.Image:
    """Рисует иконку нужного размера и переводит её в изображение Pillow."""
    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    make_icon_pixmap(size).save(buf, "PNG")
    return Image.open(io.BytesIO(bytes(buf.data()))).convert("RGBA")


def main() -> None:
    global _app  # приложение Qt нужно для рисования и должно жить до конца работы
    _app = QGuiApplication.instance() or QGuiApplication(sys.argv)
    assets = ROOT / "assets"
    assets.mkdir(exist_ok=True)
    images = [render(s) for s in SIZES]
    images[-1].save(assets / "icon.png")
    images[-1].save(assets / "icon.ico", format="ICO",
                    sizes=[(s, s) for s in SIZES], append_images=images[:-1])
    print("Иконка сохранена:", assets / "icon.ico")


if __name__ == "__main__":
    main()
