from bisect import bisect_left, bisect_right

from PySide6.QtCore import QRect, Qt, QTimer
from PySide6.QtWidgets import QAbstractScrollArea


class VirtualizedWidgetList(QAbstractScrollArea):
    """A variable-height list that rebinds a small pool of real widgets."""

    def __init__(
            self,
            widget_factory,
            key_for_item,
            estimate_height,
            widget_binder,
            materialized=None,
            dematerialized=None,
            can_recycle=None,
            overscan_rows=5,
            parent=None,
    ):
        super().__init__(parent)
        self._factory = widget_factory
        self._key = key_for_item
        self._estimate = estimate_height
        self._bind = widget_binder
        self._materialized = materialized
        self._dematerialized = dematerialized
        self._can_recycle = can_recycle
        self._overscan = max(0, int(overscan_rows))

        self._items = []
        self._offsets = [0]
        self._heights = {}
        self._active = {}
        self._visible_keys = set()
        self._pool = []
        self._sync_pending = False
        self._measure_pending = False

        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.verticalScrollBar().valueChanged.connect(self.schedule_sync)

    def set_items(self, items):
        new_items = list(items)
        new_by_key = {self._key(item): item for item in new_items}
        for key in list(self._active):
            if key not in new_by_key:
                self._release(key, force=True)
            else:
                self._bind(self._active[key], new_by_key[key])

        self._items = new_items
        live_keys = set(new_by_key)
        self._heights = {
            key: height for key, height in self._heights.items() if key in live_keys
        }
        self._rebuild_offsets()
        self.schedule_sync()

    def insert_item(self, row, item):
        row = max(0, min(int(row), len(self._items)))
        self._items.insert(row, item)
        self._rebuild_offsets()
        self.schedule_sync()
        return row

    def update_item(self, item):
        key = self._key(item)
        row = self._row_for_key(key)
        if row < 0:
            return -1
        self._items[row] = item
        self._heights.pop(key, None)
        widget = self._active.get(key)
        if widget is not None:
            self._bind(widget, item)
        self._rebuild_offsets()
        self.schedule_sync()
        return row

    def remove_key(self, key):
        row = self._row_for_key(key)
        if row < 0:
            return False
        if key in self._active:
            self._release(key, force=True)
        del self._items[row]
        self._heights.pop(key, None)
        self._rebuild_offsets()
        self.schedule_sync()
        return True

    def contains_key(self, key):
        return self._row_for_key(key) >= 0

    def widget_for_key(self, key):
        return self._active.get(key)

    def active_widgets(self):
        return [
            self._active[key]
            for key in self._visible_keys
            if key in self._active
        ]

    def item_count(self):
        return len(self._items)

    def clear_items(self):
        for widget in self._active.values():
            if self._dematerialized:
                self._dematerialized(widget)
        for widget in list(self._active.values()) + self._pool:
            self._destroy(widget)
        self._items = []
        self._offsets = [0]
        self._heights.clear()
        self._active.clear()
        self._visible_keys.clear()
        self._pool.clear()
        self._update_scrollbar()

    def schedule_sync(self, *_args):
        if self._sync_pending:
            return
        self._sync_pending = True
        QTimer.singleShot(0, self._sync)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._heights.clear()
        self._rebuild_offsets()
        self.schedule_sync()

    def showEvent(self, event):
        super().showEvent(event)
        self.schedule_sync()

    def _row_for_key(self, key):
        return next(
            (
                row
                for row, item in enumerate(self._items)
                if self._key(item) == key
            ),
            -1,
        )

    def _item_height(self, item):
        key = self._key(item)
        return self._heights.get(
            key,
            max(1, int(self._estimate(item, self.viewport().width()))),
        )

    def _rebuild_offsets(self):
        self._offsets = [0]
        for item in self._items:
            self._offsets.append(self._offsets[-1] + self._item_height(item))
        self._update_scrollbar()

    def _update_scrollbar(self):
        scrollbar = self.verticalScrollBar()
        page = max(1, self.viewport().height())
        scrollbar.setPageStep(page)
        scrollbar.setSingleStep(40)
        scrollbar.setRange(0, max(0, self._offsets[-1] - page))

    def _visible_rows(self):
        if not self._items:
            return range(0)
        top = self.verticalScrollBar().value()
        bottom = top + self.viewport().height()
        first = max(0, bisect_right(self._offsets, top) - 1)
        last = min(len(self._items) - 1, bisect_left(self._offsets, bottom))
        first = max(0, first - self._overscan)
        last = min(len(self._items) - 1, last + self._overscan)
        return range(first, last + 1)

    def _sync(self):
        self._sync_pending = False
        rows = list(self._visible_rows())
        target = {self._key(self._items[row]) for row in rows}
        retry = False

        for key in set(self._active) - target:
            if not self._release(key):
                self._active[key].hide()
                retry = True

        scroll_y = self.verticalScrollBar().value()
        width = self.viewport().width()
        for row in rows:
            item = self._items[row]
            key = self._key(item)
            widget = self._active.get(key)
            if widget is None:
                widget = self._acquire(item)
                self._active[key] = widget
            widget.setGeometry(
                QRect(0, self._offsets[row] - scroll_y, width, self._item_height(item))
            )
            widget.show()

        self._visible_keys = target
        self._schedule_measure()
        if retry:
            QTimer.singleShot(250, self.schedule_sync)

    def _acquire(self, item):
        if self._pool:
            widget = self._pool.pop()
            self._bind(widget, item)
        else:
            widget = self._factory(item)
        widget.setParent(self.viewport())
        if self._materialized:
            self._materialized(widget)
        return widget

    def _release(self, key, force=False):
        widget = self._active.get(key)
        if widget is None:
            return True
        recyclable = not self._can_recycle or self._can_recycle(widget)
        if not recyclable:
            if not force:
                return False
            self._active.pop(key)
            self._visible_keys.discard(key)
            if self._dematerialized:
                self._dematerialized(widget)
            self._destroy(widget)
            return True

        self._active.pop(key)
        self._visible_keys.discard(key)
        if self._dematerialized:
            self._dematerialized(widget)
        prepare = getattr(widget, "prepare_for_reuse", None)
        if prepare:
            prepare()
        widget.hide()
        self._pool.append(widget)
        return True

    def _schedule_measure(self):
        if self._measure_pending:
            return
        self._measure_pending = True
        QTimer.singleShot(0, self._measure_visible)

    def _measure_visible(self):
        self._measure_pending = False
        changed = False
        width = self.viewport().width()
        for key in self._visible_keys:
            widget = self._active.get(key)
            if widget is None:
                continue
            layout = widget.layout()
            height = (
                layout.heightForWidth(width)
                if layout and layout.hasHeightForWidth()
                else widget.sizeHint().height()
            )
            height = max(1, height, widget.minimumSizeHint().height())
            if abs(self._heights.get(key, 0) - height) > 2:
                self._heights[key] = height
                changed = True
        if changed:
            self._rebuild_offsets()
            self.schedule_sync()

    @staticmethod
    def _destroy(widget):
        cleanup = getattr(widget, "cleanup_and_delete", None)
        if cleanup:
            cleanup()
        else:
            widget.setParent(None)
            widget.deleteLater()
