"""Wrapper minimal autour de l'API OpenFoodFacts.

Pas de clé requise. Docs: https://world.openfoodfacts.org/data
"""
import time
import requests

# search.pl est régulièrement saturé → on tente search-a-licious en fallback
SEARCH_URL = "https://world.openfoodfacts.org/cgi/search.pl"
SEARCH_URL_V2 = "https://search.openfoodfacts.org/search"
PRODUCT_URL = "https://world.openfoodfacts.org/api/v2/product/{barcode}.json"

UA = {"User-Agent": "kalman-tdee-tracker/0.1"}


def _get_with_retry(url: str, params: dict, retries: int = 3, backoff: float = 0.7):
    last_exc = None
    for attempt in range(retries):
        try:
            r = requests.get(url, params=params, headers=UA, timeout=10)
            if r.status_code in (502, 503, 504):
                last_exc = requests.HTTPError(f"{r.status_code} {r.reason}")
                time.sleep(backoff * (2 ** attempt))
                continue
            r.raise_for_status()
            return r
        except (requests.ConnectionError, requests.Timeout) as e:
            last_exc = e
            time.sleep(backoff * (2 ** attempt))
    raise last_exc if last_exc else RuntimeError("unknown error")


def _first_brand(brands) -> str:
    if not brands:
        return ""
    if isinstance(brands, list):
        return str(brands[0]).strip() if brands else ""
    return str(brands).split(",")[0].strip()


def _parse(product: dict) -> dict | None:
    nutr = product.get("nutriments", {})
    kcal = nutr.get("energy-kcal_100g") or nutr.get("energy-kcal")
    if kcal is None:
        return None
    return {
        "name": product.get("product_name") or product.get("generic_name") or "?",
        "brand": _first_brand(product.get("brands")),
        "kcal_100g": float(kcal),
        "protein_100g": float(nutr.get("proteins_100g", 0) or 0),
        "fat_100g": float(nutr.get("fat_100g", 0) or 0),
        "carbs_100g": float(nutr.get("carbohydrates_100g", 0) or 0),
        "barcode": product.get("code", ""),
    }


def _search_legacy(query: str, page_size: int) -> list[dict]:
    params = {
        "search_terms": query, "search_simple": 1, "action": "process",
        "json": 1, "page_size": page_size,
        "fields": "code,product_name,generic_name,brands,nutriments",
    }
    r = _get_with_retry(SEARCH_URL, params)
    return r.json().get("products", [])


def _search_v2(query: str, page_size: int) -> list[dict]:
    """search-a-licious — moins surchargé que search.pl."""
    params = {"q": query, "page_size": page_size, "fields": "code,product_name,generic_name,brands,nutriments"}
    r = _get_with_retry(SEARCH_URL_V2, params)
    return r.json().get("hits", [])


def search(query: str, page_size: int = 10) -> list[dict]:
    """Tente l'API v2 puis fallback sur l'ancienne si besoin."""
    products = []
    try:
        products = _search_v2(query, page_size)
    except Exception:
        products = _search_legacy(query, page_size)
    out = []
    for p in products:
        parsed = _parse(p)
        if parsed:
            out.append(parsed)
    return out


def by_barcode(barcode: str) -> dict | None:
    r = _get_with_retry(PRODUCT_URL.format(barcode=barcode), {})
    data = r.json()
    if data.get("status") != 1:
        return None
    return _parse(data["product"])
