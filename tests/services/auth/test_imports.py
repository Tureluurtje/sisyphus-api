import api.services.auth.accounts
import api.services.auth.dependencies
import api.services.auth.email


def test_auth_modules_import_without_circular_imports():
    assert api.services.auth.accounts is not None
    assert api.services.auth.dependencies is not None
    assert api.services.auth.email is not None
