import asyncio
import json
import os
import re
import time
from dataclasses import dataclass
from typing import Any


FIELD_ALIASES = {
    "brand": ("brand", "бренд", "марка"),
    "model": ("model", "модель", "устройство"),
    "model_aliases": ("model_aliases", "синонимы модели", "алиасы модели"),
    "service": ("service", "услуга", "работа", "неисправность"),
    "service_aliases": ("service_aliases", "синонимы услуги", "алиасы услуги"),
    "active": ("active", "активен", "включен"),
}

BRAND_ALIASES = {
    "apple": ("apple", "iphone", "айфон", "эппл"),
    "samsung": ("samsung", "самсунг"),
    "xiaomi": ("xiaomi", "ксиаоми", "сяоми"),
    "tecno": ("tecno", "техно"),
    "infinix": ("infinix", "инфиникс"),
    "honor": ("honor", "хонор"),
    "realme": ("realme", "реалми"),
    "oppo": ("oppo", "оппо"),
}

SERVICE_ALIASES = {
    "display": ("экран", "дисплей", "дисплейный модуль", "сенсор", "разбит экран"),
    "battery": ("акб", "батарея", "аккумулятор", "замена батареи"),
    "charging": ("зарядка", "гнездо", "разъем", "разъём", "нижняя плата", "не заряжается"),
    "speaker": ("динамик", "хрипит", "нет звука", "не слышу"),
    "button": ("кнопка", "шлейф кнопок", "кнопка громкости"),
}


def normalize(value: Any) -> str:
    text = str(value or "").casefold().replace("ё", "е")
    replacements = {
        "айфон": "iphone",
        "эппл": "apple",
        "про": "pro",
        "макс": "max",
        "мини": "mini",
        "плюс": "plus",
    }
    for source, target in replacements.items():
        text = text.replace(source, target)
    return re.sub(r"[^\w]+", " ", text, flags=re.UNICODE).strip()


def split_aliases(value: Any) -> list[str]:
    return [normalize(item) for item in re.split(r"[,;|\n]+", str(value or "")) if normalize(item)]


def field_value(row: dict[str, Any], field: str) -> str:
    normalized = {normalize(key): value for key, value in row.items()}
    for alias in FIELD_ALIASES[field]:
        value = normalized.get(normalize(alias))
        if value not in (None, ""):
            return str(value).strip()
    return ""


def service_matches(request: str, service: str, aliases: str) -> bool:
    request_normalized = normalize(request)
    candidates = [normalize(service), *split_aliases(aliases)]
    if any(candidate and candidate in request_normalized for candidate in candidates):
        return True
    for group in SERVICE_ALIASES.values():
        if any(normalize(item) in request_normalized for item in group):
            return any(normalize(item) in " ".join(candidates) for item in group)
    return False


def brand_matches(request: str, brand: str) -> bool:
    normalized_brand = normalize(brand)
    if not normalized_brand:
        return True
    request_normalized = normalize(request)
    for aliases in BRAND_ALIASES.values():
        if normalized_brand in {normalize(item) for item in aliases}:
            return any(normalize(item) in request_normalized for item in aliases)
    return normalized_brand in request_normalized


@dataclass(frozen=True)
class CatalogResult:
    status: str
    row: dict[str, Any] | None = None
    reason: str = ""


def search_rows(rows: list[dict[str, Any]], request: str) -> CatalogResult:
    request_normalized = normalize(request)
    model_candidates: list[dict[str, Any]] = []
    for row in rows:
        active = field_value(row, "active").casefold()
        if active in {"false", "0", "нет", "no", "неактивен"}:
            continue
        if not brand_matches(request, field_value(row, "brand")):
            continue
        model_names = [field_value(row, "model"), *split_aliases(field_value(row, "model_aliases"))]
        model_names = [normalize(name) for name in model_names if normalize(name)]
        if model_names and any(name in request_normalized for name in model_names):
            model_candidates.append(row)
    for row in model_candidates:
        if service_matches(request, field_value(row, "service"), field_value(row, "service_aliases")):
            return CatalogResult("found", row=row)
    if model_candidates:
        return CatalogResult("not_found", reason="model_found_service_not_found")
    return CatalogResult("not_found", reason="model_not_found")


class GoogleSheetsPriceCatalog:
    def __init__(self, service_account_json: str, spreadsheet_id: str, cell_range: str, cache_seconds: int = 60):
        self.service_account_json = service_account_json
        self.spreadsheet_id = spreadsheet_id
        self.cell_range = cell_range
        self.cache_seconds = cache_seconds
        self._cached_rows: list[dict[str, Any]] = []
        self._cached_at = 0.0

    @classmethod
    def from_environment(cls) -> "GoogleSheetsPriceCatalog | None":
        credentials = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
        spreadsheet_id = os.getenv("GOOGLE_SHEET_ID")
        if not credentials or not spreadsheet_id:
            return None
        return cls(
            credentials,
            spreadsheet_id,
            os.getenv("GOOGLE_SHEET_RANGE", "Sheet1!A:Z"),
            int(os.getenv("GOOGLE_SHEETS_CACHE_SECONDS", "60")),
        )

    def _read_rows(self) -> list[dict[str, Any]]:
        from google.oauth2.service_account import Credentials
        from googleapiclient.discovery import build

        info = json.loads(self.service_account_json)
        credentials = Credentials.from_service_account_info(
            info,
            scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
        )
        service = build("sheets", "v4", credentials=credentials, cache_discovery=False)
        values = service.spreadsheets().values().get(
            spreadsheetId=self.spreadsheet_id,
            range=self.cell_range,
        ).execute().get("values", [])
        if not values:
            return []
        headers = [str(value).strip() for value in values[0]]
        return [dict(zip(headers, row + [""] * (len(headers) - len(row)))) for row in values[1:]]

    async def lookup(self, request: str) -> CatalogResult:
        try:
            now = time.monotonic()
            if now - self._cached_at >= self.cache_seconds:
                self._cached_rows = await asyncio.to_thread(self._read_rows)
                self._cached_at = now
            return search_rows(self._cached_rows, request)
        except Exception as error:
            return CatalogResult("error", reason=type(error).__name__)