import sys
import unittest
from datetime import datetime, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from import_fund_workbook import usable_number
from build_rankings_from_workbook import supplemental_market


class WorkbookImportTest(unittest.TestCase):
    def test_excel_datetime_serial_is_recovered(self):
        self.assertAlmostEqual(usable_number(datetime(1900, 2, 3, 0, 14, 24)), 35.01)

    def test_excel_time_fraction_is_recovered(self):
        self.assertAlmostEqual(usable_number(time(21, 50, 24)), 0.91)

    def test_india_equity_fund_is_classified(self):
        self.assertEqual(supplemental_market("台新印度基金", "跨國投資股票型區域型"), "india")

    def test_asean_equity_fund_is_classified(self):
        self.assertEqual(supplemental_market("復華東協世紀基金", "跨國投資股票型區域型"), "asean")

    def test_leveraged_fund_is_excluded(self):
        self.assertIsNone(supplemental_market("富邦印度NIFTY單日正向兩倍基金", "跨國投資股票型"))

    def test_cathay_name_is_not_mistaken_for_thailand(self):
        self.assertIsNone(supplemental_market("國泰國泰基金", "國內股票開放型一般股票型"))


if __name__ == "__main__":
    unittest.main()
