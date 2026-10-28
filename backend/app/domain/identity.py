"""Ecuadorian identity documents."""

# 24 provinces plus 30, the code the Registro Civil assigns to Ecuadorians registered abroad.
VALID_PROVINCE_CODES = set(range(1, 25)) | {30}
CEDULA_COEFFICIENTS = (2, 1, 2, 1, 2, 1, 2, 1, 2)


def is_valid_cedula(value: str) -> bool:
    """Validate a natural person's cédula with the Registro Civil modulo-10 check digit.

    Rules: 10 ASCII digits; the first two are a province code; the third is below 6 (natural
    person); each of the first nine digits is multiplied by 2,1,2,1,…, subtracting 9 from products
    above 9; the tenth digit equals (10 - sum % 10) % 10.
    """
    if not isinstance(value, str) or len(value) != 10 or not (value.isascii() and value.isdigit()):
        return False
    if int(value[:2]) not in VALID_PROVINCE_CODES or int(value[2]) >= 6:
        return False
    total = 0
    for digit, coefficient in zip(value[:9], CEDULA_COEFFICIENTS):
        product = int(digit) * coefficient
        total += product - 9 if product > 9 else product
    return (10 - total % 10) % 10 == int(value[9])
