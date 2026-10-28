from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")


def final_price(price, discount_percent: int) -> Decimal:
    """Price after discount, rounded half-up to cents.

    The catalog, llms.txt and the checkout all use this function, so the amount shown is always the
    amount charged.
    """
    amount = Decimal(str(price)) * Decimal(100 - discount_percent) / Decimal(100)
    return amount.quantize(CENT, rounding=ROUND_HALF_UP)
