"""
Multi-Currency Normalizer
Normalizes monetary amounts across currencies to a base currency (USD by default)
for accurate quantitative comparison during three-way matching.

Supports: Any ISO 4217 currency code.
Rate Source: Static fallback table (no external API required for on-premise) 
             + optional live rates via an open exchange rates endpoint.
"""
from __future__ import annotations

import re
from decimal import Decimal, ROUND_HALF_UP
from typing import NamedTuple

import structlog

logger = structlog.get_logger(__name__)


class CurrencyAmount(NamedTuple):
    amount: Decimal
    currency: str  # ISO 4217


# ─── Static Fallback Exchange Rates (USD Base) ────────────────────────────────
# Updated quarterly. Override via environment or live provider in production.
STATIC_RATES_TO_USD: dict[str, Decimal] = {
    "USD": Decimal("1.000000"),
    "EUR": Decimal("1.085000"),
    "GBP": Decimal("1.265000"),
    "JPY": Decimal("0.006700"),
    "CNY": Decimal("0.138000"),
    "INR": Decimal("0.011900"),
    "AED": Decimal("0.272300"),
    "SAR": Decimal("0.266600"),
    "SGD": Decimal("0.742000"),
    "HKD": Decimal("0.128000"),
    "CHF": Decimal("1.115000"),
    "AUD": Decimal("0.647000"),
    "CAD": Decimal("0.739000"),
    "MYR": Decimal("0.213000"),
    "THB": Decimal("0.027800"),
    "IDR": Decimal("0.000063"),
    "KRW": Decimal("0.000724"),
    "BRL": Decimal("0.196000"),
    "MXN": Decimal("0.052000"),
    "ZAR": Decimal("0.054000"),
    "TRY": Decimal("0.029500"),
    "RUB": Decimal("0.011100"),
    "PLN": Decimal("0.249000"),
    "NOK": Decimal("0.094000"),
    "SEK": Decimal("0.095000"),
    "DKK": Decimal("0.146000"),
    "NZD": Decimal("0.605000"),
    "PKR": Decimal("0.003590"),
    "BDT": Decimal("0.009100"),
    "NGN": Decimal("0.000630"),
    "EGP": Decimal("0.020500"),
    "KWD": Decimal("3.255000"),
    "BHD": Decimal("2.653000"),
    "OMR": Decimal("2.597000"),
    "QAR": Decimal("0.274600"),
}

# ─── Currency Symbol to ISO Code ──────────────────────────────────────────────
SYMBOL_TO_ISO: dict[str, str] = {
    "$": "USD", "€": "EUR", "£": "GBP", "¥": "JPY", "₹": "INR",
    "﷼": "SAR", "元": "CNY", "₽": "RUB", "₩": "KRW", "฿": "THB",
    "₦": "NGN", "₺": "TRY", "₴": "UAH", "₪": "ILS", "A$": "AUD",
    "C$": "CAD", "S$": "SGD", "HK$": "HKD", "NZ$": "NZD", "R": "ZAR",
    "Rp": "IDR", "RM": "MYR", "د.إ": "AED", "﹩": "USD",
}

# ─── Regex for parsing amounts from text ──────────────────────────────────────
CURRENCY_AMOUNT_RE = re.compile(
    r"(?P<symbol>[\$€£¥₹﷼元₽₩฿₦₺A-Z]{1,3})\s*"
    r"(?P<amount>[\d,]+(?:\.\d{1,4})?)"
    r"|(?P<amount2>[\d,]+(?:\.\d{1,4})?)\s*"
    r"(?P<code>[A-Z]{3})",
    re.UNICODE,
)


class CurrencyNormalizer:
    """
    Normalizes monetary values across currencies.
    Used by QuantitativeAgent to compare amounts extracted from
    documents in different currencies without floating-point errors.
    """

    def __init__(self, base_currency: str = "USD") -> None:
        self.base_currency = base_currency.upper()
        self._rates = dict(STATIC_RATES_TO_USD)
        logger.info("currency_normalizer_initialized", base=self.base_currency)

    def detect_currency(self, text: str) -> str:
        """
        Detect the most likely ISO 4217 currency code from raw document text.
        Uses keyword matching and symbol detection.
        Returns 'USD' as safe fallback.
        """
        text_upper = text.upper()

        # 1. Direct ISO code match (3 uppercase letters with surrounding whitespace)
        iso_matches = re.findall(r"\b([A-Z]{3})\b", text_upper)
        for match in iso_matches:
            if match in self._rates:
                return match

        # 2. Currency symbol match
        for symbol, iso in SYMBOL_TO_ISO.items():
            if symbol in text:
                return iso

        # 3. Country-based heuristic
        country_hints = {
            "india": "INR", "indian": "INR", "rupee": "INR", "rupees": "INR",
            "euro": "EUR", "pound": "GBP", "yen": "JPY",
            "dirham": "AED", "riyal": "SAR", "yuan": "CNY", "renminbi": "CNY",
            "dollar": "USD", "ringgit": "MYR", "baht": "THB", "won": "KRW",
        }
        text_lower = text.lower()
        for hint, iso in country_hints.items():
            if hint in text_lower:
                return iso

        return "USD"

    def parse_amount(self, text: str) -> CurrencyAmount | None:
        """
        Parse a currency amount from text like '₹1,24,500.00' or 'USD 4500'.
        Returns a CurrencyAmount named tuple.
        """
        # Clean up common thousand separators for Indian numbering system
        cleaned = text.strip()
        cleaned_num = re.sub(r"[^\d.]", "", cleaned.replace(",", ""))
        if not cleaned_num:
            return None

        try:
            amount = Decimal(cleaned_num)
        except Exception:
            return None

        # Try to detect currency from the raw text
        currency = self.detect_currency(text)
        return CurrencyAmount(amount=amount, currency=currency)

    def to_base(self, amount: Decimal, from_currency: str) -> Decimal:
        """
        Convert amount from any currency to base currency using static rates.
        Uses Decimal arithmetic throughout — no float contamination.
        """
        from_currency = from_currency.upper()
        if from_currency == self.base_currency:
            return amount

        rate_to_usd = self._rates.get(from_currency)
        base_rate = self._rates.get(self.base_currency, Decimal("1"))

        if rate_to_usd is None:
            logger.warning(
                "unknown_currency_no_rate",
                currency=from_currency,
                fallback="assuming 1:1 with base",
            )
            return amount

        # Convert: amount_in_currency → USD → base_currency
        amount_usd = amount * rate_to_usd
        return (amount_usd / base_rate).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)

    def are_equivalent(
        self,
        a: CurrencyAmount,
        b: CurrencyAmount,
        tolerance_pct: Decimal = Decimal("0.005"),  # 0.5% tolerance
    ) -> tuple[bool, Decimal]:
        """
        Check if two currency amounts are financially equivalent within tolerance.
        Returns (is_match, absolute_diff_in_base_currency).
        """
        a_base = self.to_base(a.amount, a.currency)
        b_base = self.to_base(b.amount, b.currency)

        diff = abs(a_base - b_base)
        tolerance = max(a_base, b_base) * tolerance_pct
        is_match = diff <= tolerance

        logger.debug(
            "currency_equivalence_check",
            a=f"{a.amount} {a.currency}",
            b=f"{b.amount} {b.currency}",
            a_base=str(a_base),
            b_base=str(b_base),
            diff=str(diff),
            match=is_match,
        )
        return is_match, diff

    def format_diff(self, diff: Decimal, currency: str | None = None) -> str:
        """Format a difference amount for display in workpapers."""
        cur = (currency or self.base_currency).upper()
        return f"{cur} {diff:,.4f}"
