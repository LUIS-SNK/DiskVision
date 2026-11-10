from datetime import datetime
from heapq import nlargest

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QToolTip, QWidget

from .storage import byte_text


class FilesModel(QAbstractTableModel):
    headers = ("Nome", "Tamanho", "Extensão", "Modificado", "Localização", "Classificação")

    def __init__(self):
        super().__init__()
        self.rows = []
        self.column = 1
        self.order = Qt.SortOrder.DescendingOrder

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.headers)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return self.headers[section]
        return None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        entry, tag = self.rows[index.row()]
        if role == Qt.ItemDataRole.ToolTipRole:
            return entry.path
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        col = index.column()
        if col == 0:
            return ("▸  " if entry.folder else "") + entry.name
        if col == 1:
            return byte_text(entry.size)
        if col == 2:
            return entry.extension
        if col == 3:
            try:
                return datetime.fromtimestamp(entry.stamp / 1e9).strftime("%d/%m/%Y  %H:%M")
            except (OSError, ValueError, OverflowError):
                return "—"
        if col == 4:
            return entry.path
        return tag

    def replace(self, rows):
        self.beginResetModel()
        self.rows = list(rows)
        self._sort()
        self.endResetModel()

    def _sort(self):
        keys = (lambda r: r[0].name.casefold(), lambda r: r[0].size,
                lambda r: r[0].extension, lambda r: r[0].stamp,
                lambda r: r[0].path.casefold(), lambda r: r[1])
        self.rows.sort(key=keys[self.column], reverse=self.order == Qt.SortOrder.DescendingOrder)

    def sort(self, column, order):
        if column < 0:
            return
        self.column, self.order = column, order
        self.beginResetModel()
        self._sort()
        self.endResetModel()


class Treemap(QWidget):
    clicked = Signal(object)
    colors = ("#246bc5", "#157f80", "#6246a6", "#925c2b", "#944a74", "#356047", "#48657b")

    def __init__(self):
        super().__init__()
        self.setMinimumHeight(174)
        self.setMouseTracking(True)
        self.items = []
        self.tiles = []
        self.selected = None

    def set_entries(self, entries):
        largest = nlargest(100, entries, key=lambda entry: entry.size)
        self.items = [(e, e.size) for e in largest if e.size]
        remaining = sum(e.size for e in entries) - sum(size for _, size in self.items)
        if remaining:
            self.items.append((None, remaining))
        self.selected = None
        self.update()

    def partition(self, items, bounds):
        if len(items) <= 1:
            if items:
                yield items[0][0], items[0][1], bounds
            return
        total = sum(size for _, size in items)
        left_size, split = items[0][1], 1
        while split < len(items) - 1 and left_size + items[split][1] / 2 < total / 2:
            left_size += items[split][1]
            split += 1
        a, b = QRectF(bounds), QRectF(bounds)
        if bounds.width() >= bounds.height():
            a.setWidth(bounds.width() * left_size / total)
            b.setLeft(a.right())
        else:
            a.setHeight(bounds.height() * left_size / total)
            b.setTop(a.bottom())
        yield from self.partition(items[:split], a)
        yield from self.partition(items[split:], b)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#141f33"))
        self.tiles = list(self.partition(self.items, QRectF(self.rect()).adjusted(2, 2, -2, -2)))
        if not self.tiles:
            painter.setPen(QColor("#b8c7dd"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Sem itens com tamanho positivo")
        for i, (entry, size, tile) in enumerate(self.tiles):
            box = tile.adjusted(1, 1, -1, -1)
            if box.isEmpty():
                continue
            painter.fillRect(box, QColor(self.colors[i % len(self.colors)] if entry else "#475569"))
            painter.setPen(QColor("#ffffff"))
            if entry is not None and entry is self.selected:
                painter.setPen(QPen(QColor("#ffffff"), 2))
                painter.drawRect(box.adjusted(1, 1, -1, -1))
            if box.width() > 45 and box.height() > 20:
                label = entry.name if entry else "Outros"
                if box.height() > 43:
                    label += "  ·  " + byte_text(size)
                label = painter.fontMetrics().elidedText(label, Qt.TextElideMode.ElideRight, int(box.width()) - 12)
                painter.drawText(box.adjusted(6, 4, -6, -2), Qt.AlignmentFlag.AlignTop, label)

    def mouseMoveEvent(self, event):
        for entry, size, bounds in self.tiles:
            if bounds.contains(event.position()):
                label = entry.path if entry else "Demais itens desta pasta"
                QToolTip.showText(event.globalPosition().toPoint(), f"{label}\n{byte_text(size)}", self)
                return
        QToolTip.hideText()

    def mousePressEvent(self, event):
        for entry, _, bounds in self.tiles:
            if entry and bounds.contains(event.position()):
                self.selected = entry
                self.update()
                self.clicked.emit(entry)
                break
