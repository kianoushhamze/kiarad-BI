"""Real SQL aggregation across internal and platform reservations; synthetic only."""
import unittest
from sqlalchemy import create_engine, text

from stock_reservations import reservation_totals, reserved_quantity


class SharedStockReservationsTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://')
        self.addCleanup(self.engine.dispose)
        self.conn = self.engine.connect()
        self.addCleanup(self.conn.close)
        for sql in (
            'CREATE TABLE products(id INTEGER PRIMARY KEY,code TEXT UNIQUE)',
            'CREATE TABLE inventory_reservations(product_id INTEGER,quantity REAL,status TEXT)',
            'CREATE TABLE platform_reservations(code TEXT,qty INTEGER,status TEXT)',
            "INSERT INTO products VALUES(1,'A'),(2,'B')",
        ):
            self.conn.execute(text(sql))

    def test_internal_and_platform_commitments_are_added(self):
        self.conn.execute(text("INSERT INTO inventory_reservations VALUES(1,4,'reserved')"))
        self.conn.execute(text("INSERT INTO platform_reservations VALUES('A',2,'active')"))
        self.assertEqual(reserved_quantity(self.conn, 1), 6)

    def test_released_rows_do_not_consume_available_stock(self):
        self.conn.execute(text("INSERT INTO inventory_reservations VALUES(1,4,'released')"))
        self.conn.execute(text("INSERT INTO platform_reservations VALUES('A',2,'released')"))
        self.assertEqual(reserved_quantity(self.conn, 1), 0)

    def test_fractional_internal_reservation_is_not_truncated(self):
        self.conn.execute(text("INSERT INTO inventory_reservations VALUES(1,0.5,'reserved')"))
        self.assertEqual(reserved_quantity(self.conn, 1), .5)

    def test_product_filter_does_not_mix_customer_orders(self):
        self.conn.execute(text("INSERT INTO platform_reservations VALUES('B',3,'active')"))
        self.assertEqual(reserved_quantity(self.conn, 1), 0)
        self.assertEqual(reservation_totals(self.conn), {2: 3})

    def test_pre_platform_schema_still_counts_internal_reservations(self):
        self.conn.execute(text('DROP TABLE platform_reservations'))
        self.conn.execute(text("INSERT INTO inventory_reservations VALUES(1,4,'reserved')"))
        self.assertEqual(reserved_quantity(self.conn, 1), 4)

    def test_pre_internal_schema_still_counts_platform_reservations(self):
        self.conn.execute(text('DROP TABLE inventory_reservations'))
        self.conn.execute(text("INSERT INTO platform_reservations VALUES('A',2,'active')"))
        self.assertEqual(reserved_quantity(self.conn, 1), 2)

    def test_negative_rows_cannot_increase_sellable_stock(self):
        self.conn.execute(text("INSERT INTO inventory_reservations VALUES(1,-4,'reserved'),(1,2,'reserved')"))
        self.assertEqual(reserved_quantity(self.conn, 1), 2)

    def test_empty_product_filter_returns_no_rows(self):
        self.assertEqual(reservation_totals(self.conn, []), {})
