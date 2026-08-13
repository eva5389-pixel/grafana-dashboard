import sys
import unittest
from datetime import datetime, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from import_fund_workbook import usable_number


class WorkbookImportTest(unittest.TestCase):
    def test_excel_datetime_serial_is_recovered(self):
        self.assertAlmostEqual(usable_number(datetime(1900, 2, 3, 0, 14, 24)), 35.01)

    def test_excel_time_fraction_is_recovered(self):
        self.assertAlmostEqual(usable_number(time(21, 50, 24)), 0.91)


if __name__ == "__main__":
    unittest.main()
