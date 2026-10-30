"""Supported markets (search databases). Launch: India + United States (doc 03 D6)."""

from enum import StrEnum


class Market(StrEnum):
    IN = "in"
    US = "us"

    @property
    def location_code(self) -> int:
        """DataForSEO / Google Ads location code."""
        return _LOCATION_CODES[self]

    @property
    def language_code(self) -> str:
        return "en"

    @property
    def label(self) -> str:
        return _LABELS[self]


_LOCATION_CODES: dict[Market, int] = {Market.IN: 2356, Market.US: 2840}
_LABELS: dict[Market, str] = {Market.IN: "India", Market.US: "United States"}
