import os
import unittest

os.environ.setdefault("BOT_TOKEN", "123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijk")
os.environ.setdefault("GEMINI_KEY", "test-key")
os.environ.setdefault("BASE_URL", "")

import main
from price_catalog import search_rows


class MainTests(unittest.TestCase):
    def test_price_search_matches_iphone_alias_and_service_alias(self):
        result = search_rows(
            [{
                "brand": "Apple",
                "model": "iPhone 13 Pro Max",
                "model_aliases": "13 Pro Max; Apple iPhone 13 Pro Max",
                "service": "Замена дисплейного модуля",
                "service_aliases": "экран; дисплей; разбит экран",
                "work_price": "3500",
            }],
            "айфон 13 про макс разбит экран",
        )

        self.assertEqual(result.status, "found")
        self.assertEqual(result.row["work_price"], "3500")

    def test_price_search_does_not_treat_missing_service_as_missing_model(self):
        result = search_rows(
            [{"model": "iPhone 13", "service": "Замена дисплея"}],
            "iPhone 13 замена аккумулятора",
        )

        self.assertEqual(result.status, "not_found")
        self.assertEqual(result.reason, "model_found_service_not_found")

    def test_normalize_data_fills_short_rows(self):
        data = main.normalize_data({"headers": ["Имя", "Телефон"], "rows": [["Аниса"]]})

        self.assertEqual(data["rows"], [["Аниса", ""]])

    def test_documents_are_created(self):
        data = {"title": "Тест", "document_text": "Строка", "headers": [], "rows": []}

        self.assertTrue(main.make_docx(data).startswith(b"PK"))
        self.assertTrue(main.make_xlsx(data).startswith(b"PK"))