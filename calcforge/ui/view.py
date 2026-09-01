"""The interactive page canvas: tools, selection, editing and navigation."""
from __future__ import annotations

import json
import math
from typing import Optional

from PySide6.QtCore import QMimeData, QPoint, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (QCursor, QKeyEvent, QMouseEvent, QPainter, QTransform, QWheelEvent)
from PySide6.QtWidgets import (QApplication, QGraphicsView, QLineEdit, QRubberBand, QGraphicsProxyWidget)

from ..core.document import MM_TO_PT
from ..items.base import HANDLE_CURSORS, MarkupItem
from ..items.mathitem import LINE_STEP, MathItem
from ..items.measure import CALIBRATE, CountItem, MeasureItem
from ..items.media import ImageItem
from ..items.plotitem import PlotItem
from ..items.shapes import PolyItem
from ..items.tableitem import TableItem
from ..items.text import CalloutItem, NoteItem, StampItem, TextItem, _TextBase
from .commands import PageEditCommand
from .tools import CLICK, DRAG, FREE, NONE, POLY, TOOL_MAP, Tool

MIN_ZOOM = 0.08
MAX_ZOOM = 16.0
CLICK_SLOP = 3.0
CELLS_MIME = "application/x-calcforge-cells"
FREE_MIN_STEP = 1.2


class PageView(QGraphicsView):
    """Displays one :class:`~calcforge.ui.scene.PageScene` and edits it."""

    toolFinished = Signal(str)
    statusMessage = Signal(str)
    cursorMoved = Signal(QPointF)
    zoomChanged = Signal(float)
    selectionChanged = Signal()
    itemActivated = Signal(object)
    cellChanged = Signal(object)
    documentEdited = Signal()

    def __init__(self, window):
        super().__init__()
        self.window = window
        self.tool_key = "select"
        self.sticky_tool = False
        self.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing |
                            QPainter.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.NoDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setViewportUpdateMode(QGraphicsView.SmartViewportUpdate)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAlignment(Qt.AlignCenter)

        self._mode = "idle"
        self._draft: Optional[MarkupItem] = None
        self._press_scene = QPointF()
        self._press_view = QPoint()
        self._handle_item: Optional[MarkupItem] = None
        self._handle_key = ""
        self._move_items: list[tuple[MarkupItem, QPointF]] = []
        self._snapshot: list[dict] = []
        self._rubber: Optional[QRubberBand] = None
        self._space_pan = False
        self._pan_origin = QPoint()
        self._zoom = 1.0

        self.active_table: Optional[TableItem] = None
        self._cell_editor: Optional[QLineEdit] = None
        self._cell_proxy: Optional[QGraphicsProxyWidget] = None
        self._editing_cell: Optional[tuple[int, int]] = None
        self._fill_origin: Optional[tuple[int, int]] = None
        self._editing_item = None

        self._last_scene_pos = QPointF(60, 60)
        self.count_subject = "Count"
        self.count_symbol = "circle"
        self.stamp_text = "APPROVED"

    # ------------------------------------------------------------------
    # basics
    # ------------------------------------------------------------------
    def document(self):
        return self.window.document

    def page(self):
        scene = self.scene()
        return scene.page if scene is not None else None

    def push_command(self, command) -> None:
        self.window.undo_stack.push(command)

    def after_undo(self) -> None:
        self.close_cell_editor(commit=False)
        self.active_table = None
        self.window.recalculate()
        self.documentEdited.emit()
        self.selectionChanged.emit()

    def begin_snapshot(self) -> None:
        scene = self.scene()
        self._snapshot = scene.serialize_items() if scene is not None else []

    def commit_snapshot(self, text: str) -> None:
        scene = self.scene()
        if scene is None:
            return
        after = scene.serialize_items()
        if after != self._snapshot:
            self.push_command(PageEditCommand(scene, self._snapshot, after, text,
                                              on_apply=self.after_undo))
            self.documentEdited.emit()

    # ------------------------------------------------------------------
    # tools
    # ------------------------------------------------------------------
    def current_tool(self) -> Tool:
        return TOOL_MAP.get(self.tool_key, TOOL_MAP["select"])

    def set_tool(self, key: str) -> None:
        if self._draft is not None:
            self.cancel_draft()
        self.close_cell_editor()
        self.tool_key = key if key in TOOL_MAP else "select"
        tool = self.current_tool()
        self.setCursor(self._cursor_for_tool(tool))
        self.statusMessage.emit(tool.hint or tool.label)
        if key != "select":
            self.deactivate_table()

    def _cursor_for_tool(self, tool: Tool) -> QCursor:
        if tool.key == "select":
            return QCursor(Qt.ArrowCursor)
        if tool.key == "pan":
            return QCursor(Qt.OpenHandCursor)
        if tool.mode in (DRAG, POLY, FREE):
            return QCursor(Qt.CrossCursor)
        return QCursor(Qt.PointingHandCursor)

    def finish_tool(self) -> None:
        if not self.sticky_tool and self.tool_key not in ("select", "pan"):
            self.set_tool("select")
            self.toolFinished.emit("select")

    # ------------------------------------------------------------------
    # zoom & navigation
    # ------------------------------------------------------------------
    def zoom(self) -> float:
        return self._zoom

    def set_zoom(self, factor: float, anchor_mouse: bool = False) -> None:
        factor = max(MIN_ZOOM, min(factor, MAX_ZOOM))
        if abs(factor - self._zoom) < 1e-6:
            return
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse if anchor_mouse
                                     else QGraphicsView.AnchorViewCenter)
        self._zoom = factor
        self.setTransform(QTransform().scale(factor, factor))
        self.zoomChanged.emit(factor)

    def zoom_in(self) -> None:
        self.set_zoom(self._zoom * 1.25)

    def zoom_out(self) -> None:
        self.set_zoom(self._zoom / 1.25)

    def fit_page(self) -> None:
        scene = self.scene()
        if scene is None:
            return
        rect = scene.page_rect().adjusted(-12, -12, 12, 12)
        available = self.viewport().rect()
        if rect.width() <= 0 or rect.height() <= 0:
            return
        self.set_zoom(min(available.width() / rect.width(),
                          available.height() / rect.height()))
        self.centerOn(scene.page_rect().center())

    def fit_width(self) -> None:
        scene = self.scene()
        if scene is None:
            return
        rect = scene.page_rect()
        self.set_zoom(max(self.viewport().width() - 26, 40) / rect.width())
        self.centerOn(rect.center().x(), self.mapToScene(self.viewport().rect().center()).y())

    def zoom_to_selection(self) -> None:
        items = self.scene().selectedItems() if self.scene() else []
        if not items:
            return
        rect = items[0].sceneBoundingRect()
        for item in items[1:]:
            rect = rect.united(item.sceneBoundingRect())
        rect = rect.adjusted(-20, -20, 20, 20)
        available = self.viewport().rect()
        self.set_zoom(min(available.width() / max(rect.width(), 1),
                          available.height() / max(rect.height(), 1)))
        self.centerOn(rect.center())

    def wheelEvent(self, event: QWheelEvent) -> None:
        if event.modifiers() & Qt.ControlModifier:
            delta = event.angleDelta().y()
            if delta:
                self.set_zoom(self._zoom * (1.0015 ** delta), anchor_mouse=True)
            event.accept()
            return
        if event.modifiers() & Qt.ShiftModifier:
            bar = self.horizontalScrollBar()
            bar.setValue(bar.value() - event.angleDelta().y())
            event.accept()
            return
        super().wheelEvent(event)

    # ------------------------------------------------------------------
    # snapping
    # ------------------------------------------------------------------
    def snap(self, point: QPointF, force: bool = False) -> QPointF:
        settings = self.document().settings
        if not (settings.snap_to_grid or force):
            return point
        step = max(settings.grid_mm, 0.5) * MM_TO_PT
        return QPointF(round(point.x() / step) * step, round(point.y() / step) * step)

    @staticmethod
    def constrain(anchor: QPointF, point: QPointF) -> QPointF:
        delta = point - anchor
        length = math.hypot(delta.x(), delta.y())
        if length < 1e-6:
            return QPointF(point)
        angle = math.radians(round(math.degrees(math.atan2(delta.y(), delta.x())) / 15.0) * 15.0)
        return QPointF(anchor.x() + math.cos(angle) * length,
                       anchor.y() + math.sin(angle) * length)

    # ------------------------------------------------------------------
    # mouse
    # ------------------------------------------------------------------
    def mousePressEvent(self, event: QMouseEvent) -> None:
        scene_pos = self.mapToScene(event.position().toPoint())
        self._press_scene = scene_pos
        self._press_view = event.position().toPoint()

        if event.button() == Qt.MiddleButton or self._space_pan or self.tool_key == "pan":
            self._mode = "pan"
            self._pan_origin = event.position().toPoint()
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
            return

        if event.button() == Qt.RightButton:
            if self._mode == "draw_poly":
                self.finish_poly()
                event.accept()
                return
            super().mousePressEvent(event)
            return

        tool = self.current_tool()
        if tool.mode == NONE and tool.key == "select":
            self._press_select(event, scene_pos)
            return
        self._press_draw(event, scene_pos, tool)

    def _press_select(self, event: QMouseEvent, scene_pos: QPointF) -> None:
        # 1. an active spreadsheet takes clicks inside its own frame
        if self.active_table is not None:
            local = self.active_table.mapFromScene(scene_pos)
            if self.active_table.fill_handle_rect().contains(local):
                self.close_cell_editor()
                self._mode = "table_fill"
                self._fill_origin = self.active_table.current
                self.begin_snapshot()
                event.accept()
                return
            border = self.active_table.border_at(local)
            if border is not None:
                self._mode = "table_resize"
                self._handle_key = f"{border[0]}:{border[1]}"
                self.begin_snapshot()
                event.accept()
                return
            gutter = self.active_table.gutter_at(local)
            if gutter is not None:
                self._select_table_band(gutter)
                event.accept()
                return
            cell = self.active_table.cell_at(local)
            if cell is not None:
                self.close_cell_editor()
                table = self.active_table
                table.current = cell
                if not (event.modifiers() & Qt.ShiftModifier):
                    table.anchor = cell
                table.update()
                self._mode = "table_select"
                self.cellChanged.emit(table)
                event.accept()
                return

        # 2. a resize handle on an already-selected item
        for item in self.scene().selectedItems():
            if not isinstance(item, MarkupItem) or not self.editable(item):
                continue
            key = item.handle_at(item.mapFromScene(scene_pos))
            if key:
                self._handle_item = item
                self._handle_key = key
                self._mode = "resize"
                self.begin_snapshot()
                event.accept()
                return

        item = self.markup_at(scene_pos)
        if item is None:
            self.deactivate_table()
            if not (event.modifiers() & (Qt.ShiftModifier | Qt.ControlModifier)):
                self.scene().clearSelection()
            self._mode = "rubber"
            if self._rubber is None:
                self._rubber = QRubberBand(QRubberBand.Rectangle, self.viewport())
            self._rubber.setGeometry(QRectF(self._press_view, self._press_view).toRect())
            self._rubber.show()
            event.accept()
            return

        if event.modifiers() & (Qt.ShiftModifier | Qt.ControlModifier):
            item.setSelected(not item.isSelected())
        elif not item.isSelected():
            self.scene().clearSelection()
            item.setSelected(True)
        self.selectionChanged.emit()

        if not self.editable(item):
            self._mode = "idle"
            event.accept()
            return
        self._mode = "move"
        self._move_items = [(other, other.pos()) for other in self.scene().selectedItems()
                            if isinstance(other, MarkupItem) and self.editable(other)]
        self.begin_snapshot()
        event.accept()

    def _select_table_band(self, gutter: tuple[str, int]) -> None:
        table = self.active_table
        kind, index = gutter
        if kind == "col":
            table.current = (0, index)
            table.anchor = (table.sheet.rows - 1, index)
        else:
            table.current = (index, 0)
            table.anchor = (index, table.sheet.cols - 1)
        table.update()
        self.cellChanged.emit(table)

    def _press_draw(self, event: QMouseEvent, scene_pos: QPointF, tool: Tool) -> None:
        point = self.snap(scene_pos)
        if tool.mode == CLICK:
            self.begin_snapshot()
            item = self.create_item(tool, point)
            if item is not None:
                self.commit_snapshot(f"Add {tool.label.lower()}")
            self.finish_tool()
            event.accept()
            return

        if tool.mode == POLY:
            if self._mode != "draw_poly":
                self.begin_snapshot()
                self._draft = tool.factory()
                self._prepare_draft(self._draft)
                self._draft.setPos(point)
                self._draft.points = [QPointF(0, 0), QPointF(0, 0)]
                self.scene().add_markup(self._draft)
                self._mode = "draw_poly"
                self.statusMessage.emit(
                    f"{tool.label}: click to add points · double-click or Enter to finish · Esc to cancel")
            else:
                local = self._draft.mapFromScene(point)
                if event.modifiers() & Qt.ShiftModifier and len(self._draft.points) >= 2:
                    local = self.constrain(self._draft.points[-2], local)
                self._draft.points[-1] = local
                self._draft.points.append(QPointF(local))
                if tool.max_points and len(self._draft.points) - 1 >= tool.max_points:
                    self.finish_poly()
            if self._draft is not None:
                self._draft.prepareGeometryChange()
            event.accept()
            return

        self.begin_snapshot()
        self._draft = tool.factory()
        self._prepare_draft(self._draft)
        self._draft.setPos(point)
        if isinstance(self._draft, (PolyItem, MeasureItem)):
            self._draft.points = [QPointF(0, 0), QPointF(0, 0)]
        else:
            self._draft.set_local_rect(QRectF(0, 0, 1, 1))
        self.scene().add_markup(self._draft)
        self._mode = "draw_free" if tool.mode == FREE else "draw_drag"
        event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        scene_pos = self.mapToScene(event.position().toPoint())
        self._last_scene_pos = scene_pos
        self.cursorMoved.emit(scene_pos)

        if self._mode == "pan":
            delta = event.position().toPoint() - self._pan_origin
            self._pan_origin = event.position().toPoint()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
            event.accept()
            return

        if self._mode == "rubber" and self._rubber is not None:
            self._rubber.setGeometry(
                QRectF(self._press_view, event.position().toPoint()).normalized().toRect())
            event.accept()
            return

        if self._mode == "move":
            delta = scene_pos - self._press_scene
            if event.modifiers() & Qt.ShiftModifier:
                if abs(delta.x()) > abs(delta.y()):
                    delta.setY(0)
                else:
                    delta.setX(0)
            for item, origin in self._move_items:
                item.setPos(self.snap(origin + delta))
            event.accept()
            return

        if self._mode == "resize" and self._handle_item is not None:
            local = self._handle_item.mapFromScene(self.snap(scene_pos))
            self._handle_item.move_handle(self._handle_key, local,
                                          bool(event.modifiers() & Qt.ShiftModifier))
            if isinstance(self._handle_item, MeasureItem):
                self._handle_item.refresh(page=self.page())
            event.accept()
            return

        if self._mode == "table_resize" and self.active_table is not None:
            kind, index = self._handle_key.split(":")
            index = int(index)
            table = self.active_table
            local = table.mapFromScene(scene_pos)
            table.prepareGeometryChange()
            if kind == "col":
                table.sheet.col_widths[index] = max(local.x() - table.column_x(index), 14.0)
            else:
                table.sheet.row_heights[index] = max(local.y() - table.row_y(index), 10.0)
            table.update()
            event.accept()
            return

        if self._mode == "table_select" and self.active_table is not None:
            cell = self.active_table.cell_at(self.active_table.mapFromScene(scene_pos))
            if cell is not None and cell != self.active_table.anchor:
                self.active_table.anchor = cell
                self.active_table.update()
                self.cellChanged.emit(self.active_table)
            event.accept()
            return

        if self._mode == "table_fill" and self.active_table is not None:
            cell = self.active_table.cell_at(self.active_table.mapFromScene(scene_pos))
            if cell is not None:
                self.active_table.anchor = cell
                self.active_table.update()
            event.accept()
            return

        if self._mode in ("draw_drag", "draw_poly", "draw_free") and self._draft is not None:
            self._update_draft(scene_pos, event.modifiers())
            event.accept()
            return

        self._update_hover_cursor(scene_pos)
        super().mouseMoveEvent(event)

    def _update_draft(self, scene_pos: QPointF, modifiers) -> None:
        draft = self._draft
        point = self.snap(scene_pos)
        local = draft.mapFromScene(point)
        draft.prepareGeometryChange()
        if self._mode == "draw_free":
            if not draft.points or _far_enough(draft.points[-1], local):
                draft.points.append(local)
        elif self._mode == "draw_poly":
            if modifiers & Qt.ShiftModifier and len(draft.points) >= 2:
                local = self.constrain(draft.points[-2], local)
            draft.points[-1] = local
        elif isinstance(draft, (PolyItem, MeasureItem)):
            if modifiers & Qt.ShiftModifier:
                local = self.constrain(QPointF(0, 0), local)
            draft.points[-1] = local
        else:
            rect = QRectF(QPointF(0, 0), local).normalized()
            if modifiers & Qt.ShiftModifier:
                side = max(rect.width(), rect.height())
                rect.setSize(QRectF(0, 0, side, side).size())
            if local.x() < 0 or local.y() < 0:
                draft.setPos(QPointF(min(self._press_scene.x(), point.x()),
                                     min(self._press_scene.y(), point.y())))
                rect = QRectF(0, 0, abs(local.x()), abs(local.y()))
            draft.set_local_rect(rect)
        if isinstance(draft, MeasureItem):
            draft.refresh(page=self.page())
        draft.update()

    def _update_hover_cursor(self, scene_pos: QPointF) -> None:
        if self.tool_key != "select":
            return
        for item in self.scene().selectedItems():
            if isinstance(item, MarkupItem) and self.editable(item):
                key = item.handle_at(item.mapFromScene(scene_pos))
                if key:
                    self.setCursor(HANDLE_CURSORS.get(key, Qt.SizeAllCursor))
                    return
        if self.active_table is not None:
            local = self.active_table.mapFromScene(scene_pos)
            border = self.active_table.border_at(local)
            if border is not None:
                self.setCursor(Qt.SplitHCursor if border[0] == "col" else Qt.SplitVCursor)
                return
            if self.active_table.fill_handle_rect().contains(local):
                self.setCursor(Qt.CrossCursor)
                return
        item = self.markup_at(scene_pos)
        self.setCursor(Qt.SizeAllCursor if item is not None and self.editable(item)
                       else Qt.ArrowCursor)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        scene_pos = self.mapToScene(event.position().toPoint())

        if self._mode == "pan":
            self._mode = "idle"
            self.setCursor(self._cursor_for_tool(self.current_tool()))
            event.accept()
            return

        if self._mode == "rubber":
            self._mode = "idle"
            if self._rubber is not None:
                rect = self._rubber.geometry()
                self._rubber.hide()
                scene_rect = self.mapToScene(rect).boundingRect()
                for item in self.scene().items(scene_rect):
                    if isinstance(item, MarkupItem) and self.editable(item):
                        item.setSelected(True)
            self.selectionChanged.emit()
            event.accept()
            return

        if self._mode == "move":
            self._mode = "idle"
            self.commit_snapshot("Move markup")
            event.accept()
            return

        if self._mode == "resize":
            self._mode = "idle"
            item = self._handle_item
            self._handle_item = None
            if item is not None:
                item.refresh(self.scene().workspace, self.page())
            self.commit_snapshot("Resize markup")
            self.selectionChanged.emit()
            event.accept()
            return

        if self._mode == "table_resize":
            self._mode = "idle"
            self.commit_snapshot("Resize column")
            event.accept()
            return

        if self._mode == "table_select":
            self._mode = "idle"
            event.accept()
            return

        if self._mode == "table_fill":
            self._mode = "idle"
            self._apply_fill()
            event.accept()
            return

        if self._mode == "draw_drag":
            self._mode = "idle"
            self.finish_draft(scene_pos)
            event.accept()
            return

        if self._mode == "draw_free":
            self._mode = "idle"
            self.finish_draft(scene_pos)
            event.accept()
            return

        if self._mode == "draw_poly":
            event.accept()
            return

        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        scene_pos = self.mapToScene(event.position().toPoint())
        if self._mode == "draw_poly":
            self.finish_poly()
            event.accept()
            return
        item = self.markup_at(scene_pos)
        if item is None:
            super().mouseDoubleClickEvent(event)
            return
        if isinstance(item, TableItem):
            self.activate_table(item)
            cell = item.cell_at(item.mapFromScene(scene_pos))
            if cell is not None:
                item.current = item.anchor = cell
                self.open_cell_editor()
            event.accept()
            return
        if isinstance(item, (MathItem, _TextBase)) and not item.locked:
            self.begin_item_edit(item)
            event.accept()
            return
        if isinstance(item, (PolyItem, MeasureItem)) and not item.locked:
            if getattr(item, "uses_vertex_handles", True) and len(item.points) > 2:
                self.begin_snapshot()
                item.insert_point(item.mapFromScene(scene_pos))
                self.commit_snapshot("Add vertex")
                event.accept()
                return
        self.itemActivated.emit(item)
        event.accept()

    # ------------------------------------------------------------------
    # item creation
    # ------------------------------------------------------------------
    def _prepare_draft(self, item: MarkupItem) -> None:
        item.author = self.document().settings.default_author or self.document().author
        self.window.apply_default_style(item)

    def create_item(self, tool: Tool, point: QPointF) -> Optional[MarkupItem]:
        item = tool.factory() if tool.factory else None
        if item is None:
            return None
        self._prepare_draft(item)
        if isinstance(item, CountItem):
            item.subject = self.count_subject
            item.symbol = self.count_symbol
            item.index = self.next_count_index(self.count_subject)
        if isinstance(item, NoteItem):
            from PySide6.QtWidgets import QInputDialog
            text, accepted = QInputDialog.getMultiLineText(self, "Note", "Comment:", "")
            if not accepted:
                return None
            item.comment = text
        self.scene().add_markup(item, point)
        self.scene().clearSelection()
        item.setSelected(True)
        self.selectionChanged.emit()
        return item

    def next_count_index(self, subject: str) -> int:
        highest = 0
        for page in self.document().pages:
            scene = page.scene
            if scene is None:
                continue
            for item in scene.markups():
                if isinstance(item, CountItem) and item.subject == subject:
                    highest = max(highest, item.index)
        return highest + 1

    def finish_draft(self, scene_pos: QPointF) -> None:
        draft = self._draft
        self._draft = None
        if draft is None:
            return
        tool = self.current_tool()
        tiny = (abs(scene_pos.x() - self._press_scene.x()) < CLICK_SLOP
                and abs(scene_pos.y() - self._press_scene.y()) < CLICK_SLOP)

        if isinstance(draft, (PolyItem, MeasureItem)):
            if tiny and tool.mode != FREE:
                draft.points[-1] = QPointF(120, 0)
            if tool.mode == FREE and len(draft.points) < 2:
                self.scene().remove_markup(draft)
                self.finish_tool()
                return
            draft.prepareGeometryChange()
        elif isinstance(draft, MathItem):
            # A calculation sizes itself around what is typed into it.
            pass
        else:
            rect = draft.local_rect()
            if tiny or rect.width() < 6 or rect.height() < 6:
                draft.set_local_rect(QRectF(0, 0, *self._default_size(draft)))

        if isinstance(draft, StampItem):
            draft.text = self.stamp_text
            from ..items.text import STAMP_PRESETS
            colour = STAMP_PRESETS.get(self.stamp_text.upper(), draft.style.stroke)
            draft.style.stroke = colour
            draft.style.fill = colour
            draft.style.text_color = colour
        if isinstance(draft, ImageItem):
            if not self.window.load_image_into(draft):
                self.scene().remove_markup(draft)
                self.finish_tool()
                return
        if isinstance(draft, MeasureItem):
            if draft.kind == CALIBRATE:
                self.scene().remove_markup(draft)
                length = math.hypot(draft.points[-1].x(), draft.points[-1].y())
                self.window.calibrate_scale(length)
                self.finish_tool()
                return
            draft.refresh(page=self.page())

        draft.refresh(self.scene().workspace, self.page())
        self.scene().clearSelection()
        draft.setSelected(True)
        self.commit_snapshot(f"Add {tool.label.lower()}")
        self.selectionChanged.emit()

        if isinstance(draft, (MathItem, TextItem, CalloutItem)):
            self.begin_item_edit(draft)
        elif isinstance(draft, TableItem):
            self.activate_table(draft)
        self.finish_tool()

    @staticmethod
    def _default_size(item: MarkupItem) -> tuple[float, float]:
        if isinstance(item, PlotItem):
            return 300.0, 200.0
        if isinstance(item, TableItem):
            return item.sheet.total_width(), item.sheet.total_height()
        if isinstance(item, MathItem):
            return 300.0, 90.0
        if isinstance(item, StampItem):
            return 190.0, 58.0
        if isinstance(item, (TextItem, CalloutItem)):
            return 170.0, 44.0
        if isinstance(item, ImageItem):
            return 220.0, 160.0
        return 120.0, 80.0

    def finish_poly(self) -> None:
        draft = self._draft
        self._mode = "idle"
        self._draft = None
        if draft is None:
            return
        tool = self.current_tool()
        if draft.points and len(draft.points) > tool.min_points:
            draft.points.pop()            # drop the live preview point
        draft.prepareGeometryChange()
        if len(draft.points) < tool.min_points:
            self.scene().remove_markup(draft)
            self.statusMessage.emit(f"{tool.label} needs at least {tool.min_points} points")
            self.finish_tool()
            return
        draft.refresh(self.scene().workspace, self.page())
        self.scene().clearSelection()
        draft.setSelected(True)
        self.commit_snapshot(f"Add {tool.label.lower()}")
        self.selectionChanged.emit()
        self.finish_tool()

    def cancel_draft(self) -> None:
        if self._draft is not None:
            self.scene().remove_markup(self._draft)
            self._draft = None
        self._mode = "idle"

    # ------------------------------------------------------------------
    # item editing
    # ------------------------------------------------------------------
    @staticmethod
    def style_line_height(item) -> float:
        """A sensible minimum row height for an empty region."""
        return item.style.font_size * 1.9

    def editing_item(self):
        return self._editing_item

    def begin_item_edit(self, item) -> None:
        self.begin_snapshot()
        self.scene().clearSelection()
        item.setSelected(True)
        if isinstance(item, MathItem) and not getattr(item, "_enter_wired", False):
            item.enterPressed.connect(self._open_next_line)
            item._enter_wired = True
        item.begin_edit()
        self._editing_item = item

    def _open_next_line(self) -> None:
        """Enter in a one-line calculation opens the next one just below it."""
        item = self._editing_item
        if not isinstance(item, MathItem):
            return
        origin = QPointF(item.pos())
        # Commit first: the region only knows how tall it is once what was typed
        # into it has been laid out, and a tall fraction needs more room below.
        self.end_item_edit()
        height = item.local_rect().height() if item.scene() is not None else 0.0
        below = origin + QPointF(0, max(height, self.style_line_height(item)) + LINE_STEP)
        self.begin_snapshot()
        following = MathItem("")
        following.style = item.style.copy()
        following.digits = item.digits
        following.number_format = item.number_format
        following.show_definition_results = item.show_definition_results
        following.show_comments = item.show_comments
        following.author = item.author
        following.layer = item.layer
        self.scene().add_markup(following, self.snap(below))
        self.scene().clearSelection()
        following.setSelected(True)
        self.commit_snapshot("Add calculation")
        self.begin_item_edit(following)

    def end_item_edit(self) -> None:
        item = getattr(self, "_editing_item", None)
        if item is None:
            return
        self._editing_item = None
        if isinstance(item, MathItem):
            item.end_edit()
            self.window.recalculate()
        else:
            item.end_edit()
        # A region left completely empty is an invisible click target; drop it.
        if self._is_empty(item):
            self.scene().remove_markup(item)
            self.window.recalculate()
        self.commit_snapshot("Edit text")
        self.documentEdited.emit()

    @staticmethod
    def _is_empty(item) -> bool:
        if isinstance(item, MathItem):
            return not item.source.strip()
        if isinstance(item, _TextBase):
            return not item.text().strip()
        return False

    @staticmethod
    def editable(item) -> bool:
        """False when the markup itself is locked, or the layer under it is."""
        from PySide6.QtWidgets import QGraphicsItem as _GraphicsItem
        return bool(item.flags() & _GraphicsItem.ItemIsMovable) and not item.locked

    def markup_at(self, scene_pos: QPointF) -> Optional[MarkupItem]:
        for item in self.scene().items(scene_pos):
            if isinstance(item, MarkupItem):
                if item.layer and not self.window.layer_visible(item.layer):
                    continue
                return item
        return None

    # ------------------------------------------------------------------
    # spreadsheet interaction
    # ------------------------------------------------------------------
    def activate_table(self, table: TableItem) -> None:
        if self.active_table is table:
            return
        self.deactivate_table()
        self.active_table = table
        table.show_chrome = True
        table.prepareGeometryChange()
        table.update()
        self.scene().clearSelection()
        table.setSelected(True)
        self.cellChanged.emit(table)
        self.statusMessage.emit(
            "Spreadsheet: type to edit · Enter/Tab to move · Ctrl+D fills down · Esc to leave")

    def deactivate_table(self) -> None:
        self.close_cell_editor()
        if self.active_table is not None:
            self.active_table.show_chrome = False
            self.active_table.prepareGeometryChange()
            self.active_table.update()
            self.active_table = None
            self.cellChanged.emit(None)

    def open_cell_editor(self, initial: Optional[str] = None) -> None:
        table = self.active_table
        if table is None or table.locked:
            return
        self.close_cell_editor()
        row, col = table.current
        self.begin_snapshot()
        editor = QLineEdit()
        editor.setText(initial if initial is not None else table.sheet.raw(row, col))
        editor.setStyleSheet(
            "QLineEdit { border: 2px solid #1971c2; background: #ffffff; padding: 0 2px; }")
        font = table.style.font()
        font.setPointSizeF(max(table.style.font_size, 6.0))
        editor.setFont(font)
        proxy = self.scene().addWidget(editor)
        proxy.setZValue(10_000)
        rect = table.cell_rect(row, col)
        proxy.setGeometry(QRectF(table.mapToScene(rect.topLeft()),
                                 rect.size().expandedTo(rect.size())))
        proxy.setPos(table.mapToScene(rect.topLeft()))
        editor.setFixedSize(int(max(rect.width(), 60)), int(max(rect.height(), 16)))
        editor.selectAll() if initial is None else editor.setCursorPosition(len(editor.text()))
        editor.setFocus(Qt.OtherFocusReason)
        editor.returnPressed.connect(lambda: self.close_cell_editor(move=(1, 0)))
        self._cell_editor = editor
        self._cell_proxy = proxy
        self._editing_cell = (row, col)

    def close_cell_editor(self, commit: bool = True,
                          move: Optional[tuple[int, int]] = None) -> None:
        if self._cell_editor is None:
            return
        text = self._cell_editor.text()
        cell = self._editing_cell
        proxy = self._cell_proxy
        self._cell_editor = None
        self._cell_proxy = None
        self._editing_cell = None
        if proxy is not None:
            # Focus must leave the proxy before it is removed, otherwise Qt
            # spins trying to hand focus on to a widget that is going away.
            widget = proxy.widget()
            if widget is not None:
                widget.clearFocus()
            proxy.clearFocus()
            if proxy.scene() is not None:
                proxy.scene().removeItem(proxy)
            proxy.deleteLater()
        if commit and cell is not None and self.active_table is not None:
            table = self.active_table
            if table.sheet.raw(*cell) != text:
                table.set_cell(cell[0], cell[1], text)
                self.window.recalculate()
                self.commit_snapshot("Edit cell")
            if move:
                table.move_current(*move)
                self.cellChanged.emit(table)
        self.setFocus(Qt.OtherFocusReason)

    def _apply_fill(self) -> None:
        table = self.active_table
        if table is None or self._fill_origin is None:
            return
        r0, c0, r1, c1 = table.selection()
        targets = [(r, c) for r in range(r0, r1 + 1) for c in range(c0, c1 + 1)
                   if (r, c) != self._fill_origin]
        if targets:
            table.sheet.fill(self._fill_origin, targets)
            self.window.recalculate()
            self.commit_snapshot("Fill")
        self._fill_origin = None

    # -- cell clipboard ----------------------------------------------------
    def copy_cells(self) -> bool:
        """Copy the selected cells as TSV, plus a full-fidelity private copy."""
        table = self.active_table
        if table is None:
            return False
        r0, c0, r1, c1 = table.selection()
        mime = QMimeData()
        mime.setText(table.sheet.region_text(r0, c0, r1, c1, raw=True))
        mime.setData(CELLS_MIME, json.dumps(
            table.sheet.region_payload(r0, c0, r1, c1)).encode("utf-8"))
        QApplication.clipboard().setMimeData(mime)
        count = (r1 - r0 + 1) * (c1 - c0 + 1)
        self.statusMessage.emit(f"Copied {count} cell(s)")
        return True

    def cut_cells(self) -> bool:
        table = self.active_table
        if table is None or not self.copy_cells():
            return False
        self.begin_snapshot()
        for row, col in table.selected_cells():
            table.sheet.set_raw(row, col, "")
        self.window.recalculate()
        self.commit_snapshot("Cut cells")
        return True

    def paste_cells(self) -> bool:
        """Paste into the active table, from CalcForge or from a spreadsheet."""
        table = self.active_table
        if table is None or table.locked:
            return False
        mime = QApplication.clipboard().mimeData()
        row, col = table.current
        self.begin_snapshot()
        if mime.hasFormat(CELLS_MIME):
            try:
                payload = json.loads(bytes(mime.data(CELLS_MIME)).decode("utf-8"))
            except ValueError:
                payload = None
            if payload:
                height = len(payload.get("rows", []))
                width = max((len(line) for line in payload.get("rows", [])), default=0)
                table.sheet.grow_to_fit(row, col, height, width)
                table.sheet.paste_payload(payload, row, col)
                self._finish_paste(table, row, col, height, width)
                return True
        text = mime.text()
        if not text:
            return False
        lines = text.replace("\r\n", "\n").split("\n")
        table.sheet.grow_to_fit(row, col, len(lines),
                                max((len(l.split("\t")) for l in lines), default=1))
        height, width = table.sheet.paste_text(text, row, col)
        self._finish_paste(table, row, col, height, width)
        return True

    def _finish_paste(self, table, row: int, col: int, height: int, width: int) -> None:
        table.anchor = (min(row + max(height, 1) - 1, table.sheet.rows - 1),
                        min(col + max(width, 1) - 1, table.sheet.cols - 1))
        table.prepareGeometryChange()
        self.window.recalculate()
        self.commit_snapshot("Paste cells")
        self.cellChanged.emit(table)
        self.statusMessage.emit(f"Pasted {height}×{width} cell(s)")

    def fill_down(self) -> None:
        table = self.active_table
        if table is None:
            return
        r0, c0, r1, c1 = table.selection()
        if r1 <= r0:
            return
        self.begin_snapshot()
        for col in range(c0, c1 + 1):
            table.sheet.fill((r0, col), [(row, col) for row in range(r0 + 1, r1 + 1)])
        self.window.recalculate()
        self.commit_snapshot("Fill down")

    def fill_right(self) -> None:
        table = self.active_table
        if table is None:
            return
        r0, c0, r1, c1 = table.selection()
        if c1 <= c0:
            return
        self.begin_snapshot()
        for row in range(r0, r1 + 1):
            table.sheet.fill((row, c0), [(row, col) for col in range(c0 + 1, c1 + 1)])
        self.window.recalculate()
        self.commit_snapshot("Fill right")

    # ------------------------------------------------------------------
    # keyboard
    # ------------------------------------------------------------------
    def idle_on_canvas(self) -> bool:
        """True when a keystroke should be read as "start something here"."""
        return (self._editing_item is None and self.active_table is None
                and self._cell_editor is None and self._mode == "idle"
                and self.tool_key in ("select", "pan"))

    def typing_position(self) -> QPointF:
        """Where a region opened by typing should appear."""
        scene = self.scene()
        point = QPointF(self._last_scene_pos)
        if scene is not None and not scene.page_rect().contains(point):
            left, top, _width, _height = scene.page.setup.content_rect_pt
            point = QPointF(left, top)
        return self.snap(point)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        key = event.key()
        modifiers = event.modifiers()

        if key == Qt.Key_Space and not event.isAutoRepeat():
            self._space_pan = True
            self.setCursor(Qt.OpenHandCursor)
            event.accept()
            return

        if key == Qt.Key_Escape:
            if self._mode == "draw_poly":
                self.cancel_draft()
            elif getattr(self, "_editing_item", None) is not None:
                self.end_item_edit()
            elif self._cell_editor is not None:
                self.close_cell_editor(commit=False)
            elif self.active_table is not None:
                self.deactivate_table()
            else:
                self.set_tool("select")
                self.toolFinished.emit("select")
            event.accept()
            return

        if self.active_table is not None and self._cell_editor is None:
            if self._table_key(event):
                return

        if key in (Qt.Key_Return, Qt.Key_Enter) and self._mode == "draw_poly":
            self.finish_poly()
            event.accept()
            return

        if key in (Qt.Key_Delete, Qt.Key_Backspace) and self.scene().selectedItems():
            self.window.delete_selection()
            event.accept()
            return

        # A bare keystroke on the canvas only does something if it is bound:
        # '"' starts text, '\\' starts maths, tool keys pick their tool.
        if self.idle_on_canvas():
            if self.window.run_typed_binding(event.text(), modifiers,
                                             self.typing_position()):
                event.accept()
                return
            if event.text() and event.text().isprintable():
                event.accept()          # unbound: deliberately nothing happens
                return

        if key in (Qt.Key_Left, Qt.Key_Right, Qt.Key_Up, Qt.Key_Down):
            step = 1.0 if modifiers & Qt.ShiftModifier else 0.25 * MM_TO_PT * 4
            delta = {Qt.Key_Left: QPointF(-step, 0), Qt.Key_Right: QPointF(step, 0),
                     Qt.Key_Up: QPointF(0, -step), Qt.Key_Down: QPointF(0, step)}[key]
            items = [i for i in self.scene().selectedItems()
                     if isinstance(i, MarkupItem) and self.editable(i)]
            if items:
                self.begin_snapshot()
                for item in items:
                    item.setPos(item.pos() + delta)
                self.commit_snapshot("Nudge markup")
                event.accept()
                return

        super().keyPressEvent(event)

    def _table_key(self, event: QKeyEvent) -> bool:
        table = self.active_table
        key = event.key()
        modifiers = event.modifiers()
        extend = bool(modifiers & Qt.ShiftModifier)
        moves = {Qt.Key_Left: (0, -1), Qt.Key_Right: (0, 1), Qt.Key_Up: (-1, 0),
                 Qt.Key_Down: (1, 0)}
        if key in moves:
            table.move_current(*moves[key], extend=extend)
            self.cellChanged.emit(table)
            event.accept()
            return True
        if key == Qt.Key_Tab:
            table.move_current(0, 1)
            self.cellChanged.emit(table)
            event.accept()
            return True
        if key == Qt.Key_Backtab:
            table.move_current(0, -1)
            self.cellChanged.emit(table)
            event.accept()
            return True
        if key in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_F2):
            self.open_cell_editor()
            event.accept()
            return True
        if key in (Qt.Key_Delete, Qt.Key_Backspace):
            self.begin_snapshot()
            for row, col in table.selected_cells():
                table.sheet.set_raw(row, col, "")
            self.window.recalculate()
            self.commit_snapshot("Clear cells")
            event.accept()
            return True
        if key == Qt.Key_D and modifiers & Qt.ControlModifier:
            self.fill_down()
            event.accept()
            return True
        if key == Qt.Key_R and modifiers & Qt.ControlModifier:
            self.fill_right()
            event.accept()
            return True
        if key == Qt.Key_Home:
            table.current = table.anchor = (0, 0)
            table.update()
            self.cellChanged.emit(table)
            event.accept()
            return True
        text = event.text()
        if text and text.isprintable() and not (modifiers & Qt.ControlModifier):
            self.open_cell_editor(initial=text)
            event.accept()
            return True
        return False

    def keyReleaseEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key_Space and not event.isAutoRepeat():
            self._space_pan = False
            self.setCursor(self._cursor_for_tool(self.current_tool()))
            event.accept()
            return
        super().keyReleaseEvent(event)

    def focusOutEvent(self, event) -> None:
        if getattr(self, "_editing_item", None) is not None:
            self.end_item_edit()
        super().focusOutEvent(event)

    # ------------------------------------------------------------------
    # context menu
    # ------------------------------------------------------------------
    def contextMenuEvent(self, event) -> None:
        scene_pos = self.mapToScene(event.pos())
        item = self.markup_at(scene_pos)
        if item is not None and not item.isSelected():
            self.scene().clearSelection()
            item.setSelected(True)
            self.selectionChanged.emit()
        menu = self.window.build_context_menu(item, scene_pos)
        menu.exec(event.globalPos())


def _far_enough(a: QPointF, b: QPointF) -> bool:
    return math.hypot(b.x() - a.x(), b.y() - a.y()) >= FREE_MIN_STEP
