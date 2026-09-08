import os
import unittest

os.environ.setdefault("BOT_TOKEN", "123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijk")
os.environ.setdefault("GEMINI_KEY", "test-key")
os.environ.setdefault("BASE_URL", "")

import main


class MainTests(unittest.TestCase):
    def test_normalize_data_fills_short_rows(self):
        data = main.normalize_data({"headers": ["Имя", "Телефон"], "rows": [["Аниса"]]})

        self.assertEqual(data["rows"], [["Аниса", ""]])

    def test_documents_are_created(self):
        data = {"title": "Тест", "document_text": "Строка", "headers": [], "rows": []}

        self.assertTrue(main.make_docx(data).startswith(b"PK"))
        self.assertTrue(main.make_xlsx(data).startswith(b"PK"))