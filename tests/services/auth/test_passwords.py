import pytest

from api.services.auth.passwords import validate_password_strength, verify_password

from api.schema.internal.errors import InvalidInputError


@pytest.mark.parametrize(
    "password",
    [
        pytest.param("12345678910", id="too-frequently-used"),
        pytest.param("a" * 100, id="too-long"),
        pytest.param("h", id="too-short"),
    ],
)
def test_validate_password_strength_rejects_invalid_password(password: str):
    with pytest.raises(InvalidInputError):
        validate_password_strength(password)


def test_validate_password_strength_accepts_hard_password():
    assert validate_password_strength("Sup3RH@rDP@SW0Rd!!82356") == None


def test_verify_password_works():
    password = "hihi"
    hashed_password = "$argon2id$v=19$m=65536,t=3,p=4$zcSXSOKPRh2hFy167OJ0Yw$nGnE6u4sunQI+gckylbyJPwZLnjeIn5oUAv/wZLAgXA"

    assert verify_password(password=password, hashed_password=hashed_password) == True


def test_verify_password_fails_with_wrong_hash():
    password = "hihi"
    wrong_hashed_password = "$argon2id$v=19$m=65536,t=3,p=4$zcSXSOKPRh2hFy167OJ0Yw$nGnE6u4sunQI+gckylbyJPwZLnjeIn5oUAv/wZLAgXAWRONG"

    assert verify_password(password=password, hashed_password=wrong_hashed_password) == False
