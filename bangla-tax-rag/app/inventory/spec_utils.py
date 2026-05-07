from __future__ import annotations

import re
from typing import Any

from app.inventory.ontology import normalize_inventory_text


FIRST_NUMBER_PATTERN = re.compile(r"-?\d+(?:\.\d+)?")

BOOLEAN_TRUE_VALUES = {
    "1",
    "active",
    "available",
    "built in",
    "built-in",
    "enabled",
    "included",
    "on",
    "supported",
    "true",
    "y",
    "yes",
}
BOOLEAN_FALSE_VALUES = {
    "0",
    "disabled",
    "false",
    "n",
    "no",
    "none",
    "not supported",
    "off",
    "passive",
    "passive isolation",
    "unsupported",
}

SPEC_METADATA_ALIASES: dict[str, tuple[str, ...]] = {
    "ram_gb": ("ram_gb", "ram", "memory"),
    "storage_gb": ("storage_gb", "storage", "capacity"),
    "capacity_gb": ("capacity_gb", "capacity", "storage"),
    "capacity_tb": ("capacity_tb", "capacity"),
    "battery_hours": ("battery_hours",),
    "battery_days": ("battery_days",),
    "battery_mah": ("battery_mah", "capacity"),
    "screen_size_inch": ("screen_size_inch", "display_size_inch", "screen_size", "display"),
    "refresh_rate_hz": ("refresh_rate_hz", "refresh_rate"),
    "coverage_sqft": ("coverage_sqft", "coverage"),
    "gps_support": ("gps_support", "gps"),
    "built_in_gps_support": ("built_in_gps_support", "gps"),
    "anc_support": ("anc_support", "anc", "noise_cancellation", "noise_cancelling", "noise_canceling"),
    "inverter_support": ("inverter_support", "inverter"),
    "stylus_support": ("stylus_support",),
    "voice_support": ("voice_support",),
    "wireless_support": ("wireless_support", "connectivity", "wireless", "wifi_standard"),
    "wired_support": ("wired_support", "connectivity", "input", "interface", "ports"),
    "usb_input": ("usb_input", "input", "inputs", "connectivity", "interface", "ports"),
    "usb_c_input": ("usb_c_input", "input", "inputs", "connectivity", "interface", "ports", "case_charging"),
    "xlr_input": ("xlr_input", "input", "inputs", "connectivity", "interface", "ports"),
    "water_resistance_support": ("water_resistance_support", "water_resistance", "material"),
    "oled_support": ("oled_support", "display", "panel_type", "panel"),
    "wifi6_support": ("wifi6_support", "wifi_standard", "connectivity"),
    "mesh_support": ("mesh_support", "mesh", "coverage"),
    "high_refresh_support": ("high_refresh_support", "refresh_rate_hz", "refresh_rate"),
}

NUMERIC_SPEC_KEYS = {
    "battery_days",
    "battery_hours",
    "battery_mah",
    "capacity_gb",
    "capacity_tb",
    "coverage_sqft",
    "ram_gb",
    "refresh_rate_hz",
    "screen_size_inch",
    "storage_gb",
}

BOOLEAN_SPEC_KEYS = {
    "anc_support",
    "built_in_gps_support",
    "gps_support",
    "high_refresh_support",
    "inverter_support",
    "mesh_support",
    "oled_support",
    "stylus_support",
    "usb_c_input",
    "usb_input",
    "voice_support",
    "water_resistance_support",
    "wifi6_support",
    "wired_support",
    "wireless_support",
    "xlr_input",
}


def spec_aliases(key: str) -> tuple[str, ...]:
    return SPEC_METADATA_ALIASES.get(key, (key,))


def coerce_spec_number(value: Any, *, key: str | None = None) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    text = str(value).strip().casefold()
    match = FIRST_NUMBER_PATTERN.search(text)
    if not match:
        return None
    number = float(match.group())
    if key in {"storage_gb", "ram_gb", "capacity_gb"} and "tb" in text and "gb" not in text:
        number *= 1024
    if key == "capacity_tb" and "gb" in text and "tb" not in text:
        number /= 1024
    return number


def coerce_spec_bool(value: Any, *, key: str | None = None) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        return bool(value)

    normalized = normalize_inventory_text(str(value))
    if not normalized:
        return None
    if normalized in BOOLEAN_FALSE_VALUES:
        return False
    if normalized in BOOLEAN_TRUE_VALUES:
        return True

    if key == "anc_support":
        if any(term in normalized for term in ("passive", "none", "no anc", "without anc")):
            return False
        return any(
            term in normalized
            for term in ("active", "anc", "noise cancellation", "noise cancelling", "mic filtering")
        )

    if key == "gps_support":
        if any(term in normalized for term in ("none", "no gps", "without gps")):
            return False
        return any(
            term in normalized
            for term in ("gps", "built in", "built-in", "phone connected", "phone-connected", "multi band", "multi-band")
        )

    if key == "built_in_gps_support":
        if any(term in normalized for term in ("phone connected", "phone-connected", "none", "no gps")):
            return False
        return any(term in normalized for term in ("built in", "built-in", "multi band", "multi-band", "gps"))

    if key == "wireless_support":
        return any(
            term in normalized
            for term in ("wireless", "bluetooth", "wi-fi", "wifi", "2 4ghz", "2.4ghz", "5g", "cellular")
        )

    if key == "wired_support":
        return any(term in normalized for term in ("wired", "usb", "usb-c", "type c", "xlr", "ethernet", "hdmi", "3 5mm", "lan"))

    if key == "usb_input":
        return any(term in normalized for term in ("usb", "usb-c", "type c"))

    if key == "usb_c_input":
        return any(term in normalized for term in ("usb-c", "usb c", "type c"))

    if key == "xlr_input":
        return "xlr" in normalized

    if key == "water_resistance_support":
        if any(term in normalized for term in ("none", "not water", "no water")):
            return False
        return any(term in normalized for term in ("water", "splash", "ipx", "atm", "resistant"))

    if key == "oled_support":
        return "oled" in normalized

    if key == "wifi6_support":
        return any(term in normalized for term in ("wi-fi 6", "wifi 6", "wifi6", "ax"))

    if key == "mesh_support":
        return "mesh" in normalized

    if key == "high_refresh_support":
        number = coerce_spec_number(value, key="refresh_rate_hz")
        return number is not None and number >= 120

    return True


def spec_requirement_satisfied(
    actual: Any,
    *,
    key: str,
    operator: str,
    expected: Any,
) -> bool:
    if actual is None:
        return False
    if operator == "eq":
        if isinstance(expected, bool):
            actual_bool = coerce_spec_bool(actual, key=key)
            return actual_bool is expected
        if isinstance(expected, str):
            return normalize_inventory_text(str(actual)) == normalize_inventory_text(expected)
        actual_number = coerce_spec_number(actual, key=key)
        expected_number = coerce_spec_number(expected, key=key)
        return actual_number is not None and expected_number is not None and actual_number == expected_number
    if operator == "gte":
        actual_number = coerce_spec_number(actual, key=key)
        expected_number = coerce_spec_number(expected, key=key)
        return actual_number is not None and expected_number is not None and actual_number >= expected_number
    if operator == "lte":
        actual_number = coerce_spec_number(actual, key=key)
        expected_number = coerce_spec_number(expected, key=key)
        return actual_number is not None and expected_number is not None and actual_number <= expected_number
    return False


def spec_requirement_partial_credit(
    actual: Any,
    *,
    key: str,
    operator: str,
    expected: Any,
) -> float:
    if actual is None or operator != "gte":
        return 0.0
    actual_number = coerce_spec_number(actual, key=key)
    expected_number = coerce_spec_number(expected, key=key)
    if actual_number is None or expected_number is None or expected_number <= 0 or actual_number <= 0:
        return 0.0
    return max(0.0, min(0.75, actual_number / expected_number))


def normalized_spec_facts(
    *,
    attributes: dict[str, Any],
    metadata: dict[str, Any],
) -> dict[str, Any]:
    specs: dict[str, Any] = {}
    raw_attributes = metadata.get("raw_attributes")
    if isinstance(raw_attributes, dict):
        for key, value in raw_attributes.items():
            _set_raw_spec(specs, key, value)
    for key, value in attributes.items():
        _set_raw_spec(specs, key, value)

    for canonical_key, aliases in SPEC_METADATA_ALIASES.items():
        raw_value = _first_spec_value(aliases=aliases, attributes=attributes, metadata=metadata, specs=specs)
        if raw_value is None:
            continue
        if canonical_key in NUMERIC_SPEC_KEYS:
            value = coerce_spec_number(raw_value, key=canonical_key)
            if value is not None:
                specs[canonical_key] = int(value) if float(value).is_integer() else round(value, 2)
        elif canonical_key in BOOLEAN_SPEC_KEYS:
            value = coerce_spec_bool(raw_value, key=canonical_key)
            if value is not None:
                specs[canonical_key] = value
        else:
            specs[canonical_key] = raw_value
    return specs


def _first_spec_value(
    *,
    aliases: tuple[str, ...],
    attributes: dict[str, Any],
    metadata: dict[str, Any],
    specs: dict[str, Any],
) -> Any:
    for source in (metadata, metadata.get("raw_attributes"), attributes, specs):
        if not isinstance(source, dict):
            continue
        for alias in aliases:
            value = source.get(alias)
            if value is None:
                continue
            if isinstance(value, str) and not value.strip():
                continue
            return value
    return None


def _set_raw_spec(specs: dict[str, Any], key: Any, value: Any) -> None:
    normalized_key = str(key).strip().casefold()
    if normalized_key and value not in (None, "") and normalized_key not in specs:
        specs[normalized_key] = value
