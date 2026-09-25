"""
region_selector.py — визуальный выбор области экрана (как в «Ножницах» Windows).

Как это работает:
  1. На каждом мониторе открывается полноэкранное окно поверх всех окон
     со «стоп-кадром» экрана, затемнённым полупрозрачной маской.
  2. Пользователь выделяет прямоугольник мышью: внутри рамки картинка
     остаётся яркой, рядом показываются координаты и размер.
  3. После отпускания кнопки мыши область переводится в физические пиксели
     (с учётом масштабирования Windows 125%/150% и т.п.) — именно в них
     работает mss при захвате экрана.

Esc или правая кнопка мыши — отмена.

Также здесь находится RegionHighlighter — кратковременная подсветка
уже выбранной области рамкой.
"""

from __future__ import annotations

from PyQt6.QtCore import QObject, QPoint, QPointF, QRect, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (QColor, QCursor, QFont, QFontMetrics, QGuiApplication, QKeyEvent,
                         QMouseEvent, QPainter, QPainterPath, QPen, QPixmap, QScreen)
from PyQt6.QtWidgets import QWidget

from settings import Region

MIN_REGION_SIZE = 5                       # минимальная сторона области, физ. пикселей
ACCENT = QColor(0, 162, 255)              # цвет рамки выделения
DIM = QColor(0, 0, 0, 120)                # затемнение фона
HINT_TEXT = "Выделите область мышью   •   Esc или правая кнопка — отмена"


# ---------------------------------------------------------------------------
# Пересчёт координат: логические (Qt) ↔ физические (mss)
# ---------------------------------------------------------------------------
# В Qt 6 левый верхний угол экрана в логических координатах совпадает
# с физическим, а размеры делятся на коэффициент масштабирования (dpr).
# Поэтому: физ = начало_экрана + (лог − начало_экрана) × dpr.

def screen_physical_rect(screen: QScreen) -> QRect:
    """Прямоугольник экрана в физических пикселях."""
    geo, dpr = screen.geometry(), screen.devicePixelRatio()
    return QRect(geo.x(), geo.y(), round(geo.width() * dpr), round(geo.height() * dpr))


def _overlap(region: Region, rect: QRect) -> int:
    """Площадь пересечения области с прямоугольником."""
    w = min(region.left + region.width, rect.x() + rect.width()) - max(region.left, rect.x())
    h = min(region.top + region.height, rect.y() + rect.height()) - max(region.top, rect.y())
    return w * h if w > 0 and h > 0 else 0


def find_screen_for_region(region: Region) -> QScreen | None:
    """Экран, на котором находится большая часть области (None — за пределами экранов)."""
    best, best_area = None, 0
    for screen in QGuiApplication.screens():
        area = _overlap(region, screen_physical_rect(screen))
        if area > best_area:
            best, best_area = screen, area
    return best


def region_on_screens(region: Region) -> bool:
    """Видна ли область хотя бы частично на одном из подключённых мониторов."""
    return find_screen_for_region(region) is not None


def region_to_logical(region: Region) -> tuple[QScreen, QRectF] | None:
    """Физическая область → (экран, прямоугольник в логических координатах Qt)."""
    screen = find_screen_for_region(region)
    if screen is None:
        return None
    geo, dpr = screen.geometry(), screen.devicePixelRatio()
    return screen, QRectF(geo.x() + (region.left - geo.x()) / dpr,
                          geo.y() + (region.top - geo.y()) / dpr,
                          region.width / dpr, region.height / dpr)


# ---------------------------------------------------------------------------
# Окно выделения на одном мониторе
# ---------------------------------------------------------------------------

class _SelectionOverlay(QWidget):
    """Полноэкранное окно выделения для одного монитора."""

    finished = pyqtSignal(object)  # Region или None, если выбор отменён

    def __init__(self, screen: QScreen, background: QPixmap):
        super().__init__(None, Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint
                         | Qt.WindowType.Tool)
        self._screen = screen
        self._background = background
        self._origin: QPointF | None = None   # точка, где нажали кнопку мыши
        self._current: QPointF | None = None  # текущее положение курсора при выделении
        self._cursor = QPointF(-1, -1)        # положение курсора (для перекрестия)

        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        if background.isNull():
            # Не удалось сделать стоп-кадр (например, Wayland) — просто затемняем живой экран
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setGeometry(screen.geometry())

    # --- геометрия ---

    def _selection(self) -> QRectF | None:
        """Текущий прямоугольник выделения в локальных логических координатах."""
        if self._origin is None or self._current is None:
            return None
        return QRectF(self._origin, self._current).normalized()

    def _to_physical(self, rect: QRectF) -> Region:
        """Локальный логический прямоугольник → область в физических пикселях."""
        geo, dpr = self._screen.geometry(), self._screen.devicePixelRatio()
        left = geo.x() + round(rect.left() * dpr)
        top = geo.y() + round(rect.top() * dpr)
        right = geo.x() + round(rect.right() * dpr)
        bottom = geo.y() + round(rect.bottom() * dpr)
        return Region(left, top, right - left, bottom - top)

    def _point_to_physical(self, pos: QPointF) -> QPoint:
        geo, dpr = self._screen.geometry(), self._screen.devicePixelRatio()
        return QPoint(geo.x() + round(pos.x() * dpr), geo.y() + round(pos.y() * dpr))

    # --- отрисовка ---

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        full = QRectF(self.rect())
        if not self._background.isNull():
            p.drawPixmap(self.rect(), self._background)

        # Затемняем всё, кроме выделенной области
        sel = self._selection()
        mask = QPainterPath()
        mask.addRect(full)
        if sel is not None:
            hole = QPainterPath()
            hole.addRect(sel)
            mask = mask.subtracted(hole)
        p.fillPath(mask, DIM)

        if sel is not None:
            self._draw_selection(p, sel)
        elif self.rect().contains(self._cursor.toPoint()):
            self._draw_crosshair(p)

        self._draw_hint(p)
        p.end()

    def _draw_selection(self, p: QPainter, sel: QRectF) -> None:
        # Рамка
        p.setPen(QPen(ACCENT, 2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(sel)
        # Маркеры по углам
        p.setBrush(ACCENT)
        p.setPen(Qt.PenStyle.NoPen)
        for corner in (sel.topLeft(), sel.topRight(), sel.bottomLeft(), sel.bottomRight()):
            p.drawRect(QRectF(corner.x() - 3, corner.y() - 3, 6, 6))
        # Подпись с координатами и размером (в физических пикселях)
        r = self._to_physical(sel)
        text = f"X: {r.left}   Y: {r.top}   {r.width} × {r.height} px"
        anchor = QPointF(sel.left(), sel.top() - 8)
        self._draw_label(p, text, anchor, above=True)

    def _draw_crosshair(self, p: QPainter) -> None:
        c = self._cursor
        p.setPen(QPen(QColor(255, 255, 255, 110), 1, Qt.PenStyle.DashLine))
        p.drawLine(QPointF(0, c.y()), QPointF(self.width(), c.y()))
        p.drawLine(QPointF(c.x(), 0), QPointF(c.x(), self.height()))
        pt = self._point_to_physical(c)
        self._draw_label(p, f"X: {pt.x()}   Y: {pt.y()}", QPointF(c.x() + 14, c.y() + 18), above=False)

    def _draw_label(self, p: QPainter, text: str, anchor: QPointF, above: bool) -> None:
        """Подпись на тёмной плашке; не вылезает за края экрана."""
        font = QFont(self.font())
        font.setPointSizeF(10)
        font.setBold(True)
        p.setFont(font)
        fm = QFontMetrics(font)
        w, h = fm.horizontalAdvance(text) + 16, fm.height() + 8
        x = anchor.x()
        y = anchor.y() - h if above else anchor.y()
        if y < 0:  # нет места сверху — рисуем внутри выделения
            y = anchor.y() + 16 if above else 0
        x = max(0.0, min(x, self.width() - w))
        y = max(0.0, min(y, self.height() - h))
        box = QRectF(x, y, w, h)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(20, 20, 20, 220))
        p.drawRoundedRect(box, 4, 4)
        p.setPen(QColor(255, 255, 255))
        p.drawText(box, Qt.AlignmentFlag.AlignCenter, text)

    def _draw_hint(self, p: QPainter) -> None:
        font = QFont(self.font())
        font.setPointSizeF(11)
        p.setFont(font)
        fm = QFontMetrics(font)
        w, h = fm.horizontalAdvance(HINT_TEXT) + 32, fm.height() + 16
        box = QRectF((self.width() - w) / 2, 24, w, h)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(20, 20, 20, 200))
        p.drawRoundedRect(box, 8, 8)
        p.setPen(QColor(255, 255, 255))
        p.drawText(box, Qt.AlignmentFlag.AlignCenter, HINT_TEXT)

    # --- мышь и клавиатура ---

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.RightButton:
            self.finished.emit(None)
        elif event.button() == Qt.MouseButton.LeftButton:
            self._origin = self._current = event.position()
            self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        self._cursor = event.position()
        if self._origin is not None:
            self._current = event.position()
        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton or self._origin is None:
            return
        self._current = event.position()
        sel = self._selection()
        region = self._to_physical(sel) if sel is not None else None
        if region and region.width >= MIN_REGION_SIZE and region.height >= MIN_REGION_SIZE:
            self.finished.emit(region)
        else:
            # Слишком маленькое выделение (случайный клик) — начинаем заново
            self._origin = self._current = None
            self.update()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.finished.emit(None)

    def enterEvent(self, _event) -> None:
        # Окно под курсором получает фокус, чтобы работала клавиша Esc
        self.activateWindow()
        self.setFocus()

    def leaveEvent(self, _event) -> None:
        self._cursor = QPointF(-1, -1)
        self.update()


# ---------------------------------------------------------------------------
# Координатор выбора области на всех мониторах
# ---------------------------------------------------------------------------

class RegionSelector(QObject):
    """Запускает выбор области сразу на всех мониторах."""

    region_selected = pyqtSignal(object)  # Region
    cancelled = pyqtSignal()

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._overlays: list[_SelectionOverlay] = []

    def is_active(self) -> bool:
        return bool(self._overlays)

    def start(self) -> None:
        """Показывает окна выделения. Главное окно нужно скрыть заранее."""
        if self._overlays:
            return
        cursor_screen = QGuiApplication.screenAt(QCursor.pos())
        for screen in QGuiApplication.screens():
            overlay = _SelectionOverlay(screen, screen.grabWindow(0))
            overlay.finished.connect(self._finish)
            self._overlays.append(overlay)
            overlay.winId()  # создаём системное окно, чтобы привязать его к нужному монитору
            if overlay.windowHandle() is not None:
                overlay.windowHandle().setScreen(screen)
            overlay.setGeometry(screen.geometry())
            overlay.showFullScreen()
            if screen is cursor_screen:
                overlay.raise_()
                overlay.activateWindow()
                overlay.setFocus()

    def cancel(self) -> None:
        if self._overlays:
            self._finish(None)

    def _finish(self, region: Region | None) -> None:
        overlays, self._overlays = self._overlays, []
        for overlay in overlays:
            overlay.finished.disconnect(self._finish)
            overlay.close()
        if region is None:
            self.cancelled.emit()
        else:
            self.region_selected.emit(region)


# ---------------------------------------------------------------------------
# Подсветка выбранной области
# ---------------------------------------------------------------------------

class RegionHighlighter(QWidget):
    """
    Рисует на пару секунд рамку вокруг области. Рамка расположена снаружи
    области, поэтому не попадает в сравниваемые кадры и не вызывает
    ложных срабатываний. Окно «прозрачно» для мыши.
    """

    BORDER = 4

    def __init__(self, logical_rect: QRectF, duration_ms: int = 2500):
        super().__init__(None, Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint
                         | Qt.WindowType.Tool
                         | Qt.WindowType.WindowTransparentForInput)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        b = self.BORDER
        self.setGeometry(logical_rect.adjusted(-b, -b, b, b).toAlignedRect())
        QTimer.singleShot(duration_ms, self.close)

    @classmethod
    def show_region(cls, region: Region) -> RegionHighlighter | None:
        """Показывает подсветку. None — если область вне подключённых экранов."""
        found = region_to_logical(region)
        if found is None:
            return None
        widget = cls(found[1])
        widget.show()
        return widget

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        b = self.BORDER
        pen = QPen(QColor(255, 60, 60), b)
        pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
        p.setPen(pen)
        p.drawRect(QRectF(self.rect()).adjusted(b / 2, b / 2, -b / 2, -b / 2))
        p.end()
