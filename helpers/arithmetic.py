"""
helpers/arithmetic.py
"""
from decimal import ROUND_DOWN, Decimal


def round_decimal(value: Decimal, exp: int, rounding: str = ROUND_DOWN) -> Decimal:
    exp = Decimal('10') ** (-exp)
    return value.quantize(exp, rounding=rounding_config.rounding)
