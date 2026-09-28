from os import PathLike
from typing import Any, ClassVar, Mapping, Protocol


class _CredentialsWithIdToken(Protocol):
    id_token: str | None
    client_id: str | None


class Flow:
    client_type: ClassVar[str]
    credentials: _CredentialsWithIdToken
    code_verifier: str
    redirect_uri: str | None

    @classmethod
    def from_client_secrets_file(
        cls,
        client_secrets_file: str | PathLike[str],
        scopes: list[str],
        **kwargs: Any,
    ) -> Flow: ...

    def authorization_url(self, **kwargs: Any) -> tuple[str, str]: ...

    def fetch_token(self, **kwargs: Any) -> Mapping[str, Any]: ...


class InstalledAppFlow(Flow): ...
