import unittest

import pandas as pd

from deva.admin_parts import tables


class AdminTablesHelpersTest(unittest.TestCase):
    def test_validate_table_name(self):
        ok, msg = tables.validate_table_name("")
        self.assertFalse(ok)
        self.assertIn("不能为空", msg)

        ok, msg = tables.validate_table_name("!bad")
        self.assertFalse(ok)

        ok, msg = tables.validate_table_name("default")
        self.assertFalse(ok)

        ok, msg = tables.validate_table_name("orders", existing_tables={"orders"})
        self.assertFalse(ok)

        ok, value = tables.validate_table_name("orders_2026")
        self.assertTrue(ok)
        self.assertEqual(value, "orders_2026")

    def test_compute_total_pages(self):
        self.assertEqual(tables.compute_total_pages(0, 10), 1)
        self.assertEqual(tables.compute_total_pages(10, 10), 1)
        self.assertEqual(tables.compute_total_pages(11, 10), 2)

    def test_stable_widget_id(self):
        a = tables.stable_widget_id("alpha", prefix="k")
        b = tables.stable_widget_id("alpha", prefix="k")
        c = tables.stable_widget_id("beta", prefix="k")
        self.assertEqual(a, b)
        self.assertNotEqual(a, c)
        self.assertTrue(a.startswith("k_"))

    def test_filter_dataframe(self):
        df = pd.DataFrame({"a": ["Apple", "Banana"], "b": ["x", "y"]})
        out = tables.filter_dataframe(df, "app")
        self.assertEqual(len(out), 1)
        self.assertEqual(out.iloc[0]["a"], "Apple")

    def test_parse_uploaded_dataframe_csv(self):
        payload = {
            "filename": "demo.csv",
            "mime_type": "text/csv",
            "content": b"col1,col2\n1,2\n3,4\n",
        }
        df = tables.parse_uploaded_dataframe(payload, pd, max_rows=10, max_cols=10)
        self.assertEqual(list(df.columns), ["col1", "col2"])
        self.assertEqual(len(df), 2)

    def test_parse_uploaded_dataframe_limit(self):
        payload = {
            "filename": "demo.csv",
            "mime_type": "text/csv",
            "content": b"col1\n1\n2\n3\n",
        }
        with self.assertRaises(ValueError):
            tables.parse_uploaded_dataframe(payload, pd, max_rows=2, max_cols=10)


if __name__ == "__main__":
    unittest.main()
