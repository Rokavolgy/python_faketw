import os
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel

from widgets.virtualized_list import VirtualizedWidgetList


class _TestRow(QLabel):
    disposed_count = 0
    created_count = 0

    def __init__(self, item):
        super().__init__(item["text"])
        type(self).created_count += 1
        self.setMinimumHeight(120)
        self.recyclable = True
        self._disposed = False

    def bind(self, item):
        self.setText(item["text"])

    def prepare_for_reuse(self):
        self.setText("")

    def cleanup_and_delete(self):
        if self._disposed:
            return
        self._disposed = True
        type(self).disposed_count += 1
        self.setParent(None)
        self.deleteLater()


class TestVirtualizedWidgetList(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def setUp(self):
        _TestRow.disposed_count = 0
        _TestRow.created_count = 0
        self.materialized = []
        self.dematerialized = []
        self.items = [
            {"id": str(index), "text": f"row {index}"}
            for index in range(100)
        ]
        self.view = VirtualizedWidgetList(
            widget_factory=_TestRow,
            key_for_item=lambda item: item["id"],
            estimate_height=lambda _item, _width: 120,
            widget_binder=lambda widget, item: widget.bind(item),
            materialized=lambda widget: self.materialized.append(widget.text()),
            dematerialized=lambda widget: self.dematerialized.append(widget.text()),
            can_recycle=lambda widget: widget.recyclable,
            overscan_rows=1,
        )
        self.view.resize(600, 500)
        self.view.set_items(self.items)
        self.view.show()
        QTest.qWait(50)

    def tearDown(self):
        self.view.clear_items()
        self.view.close()
        self.view.deleteLater()
        QTest.qWait(10)

    def test_only_visible_rows_are_materialized(self):
        self.assertGreater(len(self.view.active_widgets()), 0)
        self.assertLess(len(self.view.active_widgets()), 15)
        self.assertEqual(self.view.item_count(), 100)
        initially_created = _TestRow.created_count

        self.view.verticalScrollBar().setValue(
            self.view.verticalScrollBar().maximum()
        )
        QTest.qWait(50)

        self.assertIsNotNone(self.view.widget_for_key("99"))
        self.assertIn("row 0", self.dematerialized)
        self.assertIn("row 99", self.materialized)
        self.assertLess(len(self.view.active_widgets()), 15)
        self.assertLessEqual(_TestRow.created_count, initially_created + 1)
        self.assertEqual(_TestRow.disposed_count, 0)

    def test_update_remove_and_recycle_guard(self):
        first = self.view.widget_for_key("0")
        self.assertIsNotNone(first)
        first.recyclable = False

        self.view.update_item({"id": "0", "text": "updated"})
        self.assertEqual(first.text(), "updated")

        self.view.verticalScrollBar().setValue(
            self.view.verticalScrollBar().maximum()
        )
        QTest.qWait(50)
        self.assertIs(self.view.widget_for_key("0"), first)

        first.recyclable = True
        self.view.schedule_sync()
        QTest.qWait(50)
        self.assertIsNone(self.view.widget_for_key("0"))

        self.assertTrue(self.view.remove_key("99"))
        self.assertFalse(self.view.contains_key("99"))
        self.assertEqual(self.view.item_count(), 99)


if __name__ == "__main__":
    unittest.main()
