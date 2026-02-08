from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _


def _checksum(digits: list[int], weights: list[int]) -> int:
    # Control digit algorithm: ((sum(d_i * w_i) % 11) % 10)
    return (sum(d * w for d, w in zip(digits, weights)) % 11) % 10


def validate_inn(value: str) -> None:
    """
    Validates Russian INN:
    - 10 digits for legal entities
    - 12 digits for individuals/IE
    Includes:
    - digit-only check
    - structural checks for region (1-2) and tax office (3-4)
    - checksum validation
    """
    inn = str(value).strip()

    if not inn.isdigit():
        raise ValidationError(_("INN must contain digits only."))
    if len(inn) not in (10, 12):
        raise ValidationError(_("INN must be exactly 10 or 12 digits long."))

    # Structural checks:
    # 1-2: region code (01..99), 3-4: tax office code (01..99)
    region_code = int(inn[0:2])
    tax_office_code = int(inn[2:4])

    if not (1 <= region_code <= 99):
        raise ValidationError(_("Invalid INN: region code is out of range (01..99)."))

    if not (1 <= tax_office_code <= 99):
        raise ValidationError(
            _("Invalid INN: tax office code is out of range (01..99).")
        )

    digits = list(map(int, inn))

    if len(inn) == 10:
        weights_10 = [2, 4, 10, 3, 5, 9, 4, 6, 8]
        control = _checksum(digits[:9], weights_10)
        if control != digits[9]:
            raise ValidationError(_("Invalid INN: checksum mismatch for 10-digit INN."))
        return

    weights_11 = [7, 2, 4, 10, 3, 5, 9, 4, 6, 8]
    weights_12 = [3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8]

    control_11 = _checksum(digits[:10], weights_11)
    control_12 = _checksum(digits[:11], weights_12)

    if control_11 != digits[10] or control_12 != digits[11]:
        raise ValidationError(_("Invalid INN: checksum mismatch for 12-digit INN."))
