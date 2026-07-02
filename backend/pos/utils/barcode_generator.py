# pos/utils/barcode_generator.py
import time
import random
import string


def generate_ean13() -> str:
    """
    Generate a valid EAN-13 barcode number.
    Format: 12 digit payload + 1 check digit = 13 digits total
    Uses timestamp + random to ensure uniqueness
    """
    # 8 digits from timestamp (milliseconds) + 4 random digits = 12 digits
    ts_part = str(int(time.time() * 1000))[-8:]          # e.g. 34567890
    rand_part = ''.join(random.choices(string.digits, k=4))  # e.g. 2819
    barcode_12 = ts_part + rand_part                      # 12 digits

    # EAN-13 check digit: odd positions × 1, even positions × 3
    total = sum(
        int(d) * (1 if i % 2 == 0 else 3)
        for i, d in enumerate(barcode_12)
    )
    check_digit = (10 - (total % 10)) % 10

    return barcode_12 + str(check_digit)  # 13 digits total


def generate_unique_barcode() -> str:
    """
    Generate an EAN-13 barcode that does not already exist in the DB.
    Retries up to 10 times before raising an error.
    """
    from pos.models.items import itemvariants  # local import to avoid circular

    for _ in range(10):
        barcode = generate_ean13()
        if not itemvariants.objects.filter(barcode=barcode).exists():
            return barcode

    # Extremely unlikely to reach here, but handled gracefully
    raise RuntimeError(
        "Could not generate a unique barcode after 10 attempts. "
        "Please try again."
    )