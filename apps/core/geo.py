import json
import re
from functools import lru_cache
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured, ValidationError


def _read_geo_data():
    data_path = Path(__file__).parent / "data" / "iran_geo.json"
    try:
        with data_path.open(encoding="utf-8") as data_file:
            return json.load(data_file)
    except (OSError, json.JSONDecodeError) as exc:
        raise ImproperlyConfigured("Unable to load Iran province and city data.") from exc


def normalize_location_text(text):
    if not isinstance(text, str):
        raise TypeError("Location text must be a string.")
    normalized = text.replace("ي", "ی").replace("ك", "ک").replace("\u200c", " ")
    return re.sub(r"\s+", " ", normalized).strip()


def _validate_geo_data(data):
    if not isinstance(data, dict) or data.get("version") != 1:
        raise ImproperlyConfigured("Iran province and city data has an invalid format.")

    provinces = data.get("provinces")
    if not isinstance(provinces, list):
        raise ImproperlyConfigured("Iran province and city data must contain a province list.")

    seen_provinces = set()
    for province in provinces:
        if not isinstance(province, dict):
            raise ImproperlyConfigured("Each province entry must be an object.")
        name = province.get("name")
        if not isinstance(name, str) or not normalize_location_text(name):
            raise ImproperlyConfigured("Province names must be non-empty strings.")
        normalized_name = normalize_location_text(name)
        if normalized_name in seen_provinces:
            raise ImproperlyConfigured(f"Duplicate province name: {name}")
        seen_provinces.add(normalized_name)

        cities = province.get("cities")
        if not isinstance(cities, list) or not cities:
            raise ImproperlyConfigured(f"Province {name} must have at least one city.")
        seen_cities = set()
        for city in cities:
            if not isinstance(city, str) or not normalize_location_text(city):
                raise ImproperlyConfigured("City names must be non-empty strings.")
            normalized_city = normalize_location_text(city)
            if normalized_city in seen_cities:
                raise ImproperlyConfigured(f"Duplicate city name in province {name}: {city}")
            seen_cities.add(normalized_city)


@lru_cache(maxsize=1)
def load_geo():
    data = _read_geo_data()
    _validate_geo_data(data)
    return data


def get_provinces():
    return [province["name"] for province in load_geo()["provinces"]]


def get_cities(province):
    normalized_province = normalize_location_text(province)
    for entry in load_geo()["provinces"]:
        if normalize_location_text(entry["name"]) == normalized_province:
            return list(entry["cities"])
    raise ValidationError("استان معتبر نیست.", code="invalid_province")


def canonical_location(province, city):
    normalized_province = normalize_location_text(province)
    province_entry = next(
        (
            entry
            for entry in load_geo()["provinces"]
            if normalize_location_text(entry["name"]) == normalized_province
        ),
        None,
    )
    if province_entry is None:
        raise ValidationError("استان معتبر نیست.", code="invalid_province")

    normalized_city = normalize_location_text(city)
    for canonical_city in province_entry["cities"]:
        if normalize_location_text(canonical_city) == normalized_city:
            return province_entry["name"], canonical_city
    raise ValidationError("شهر معتبر نیست.", code="invalid_city")
