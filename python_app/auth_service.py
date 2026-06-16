from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from appwrite_config import AppwriteConfig
from appwrite_rest import AppwriteCredential, AppwriteError, AppwriteRestClient

try:
    import keyring
except Exception:  # pragma: no cover - optional runtime dependency
    keyring = None


ROLE_ADMIN = "admin"
ROLE_CLIENT = "client"
VALID_ROLES = {ROLE_ADMIN, ROLE_CLIENT}


@dataclass
class AuthenticatedUser:
    user_id: str
    email: str
    name: str
    role: str
    credential: AppwriteCredential
    session_restored: bool = False

    @property
    def display_name(self) -> str:
        return self.name or self.email or self.user_id


class AppwriteAuthService:
    def __init__(self, config: AppwriteConfig, *, client: AppwriteRestClient | None = None) -> None:
        self.config = config
        self.client = client or AppwriteRestClient(config)

    @property
    def configured(self) -> bool:
        return self.config.configured

    def login(self, email: str, password: str) -> AuthenticatedUser:
        email = email.strip()
        if not email or not password:
            raise AppwriteError("Enter your email and password.")
        response = self.client.json("POST", "/account/sessions/email", data={"email": email, "password": password})
        credential = self._credential_from_session(response)
        user = self._current_user(credential)
        self._store_session(credential)
        return user

    def restore_session(self) -> AuthenticatedUser | None:
        credential = self._load_session()
        if credential is None:
            return None
        try:
            user = self._current_user(credential)
        except AppwriteError:
            self._clear_session()
            return None
        user.session_restored = True
        return user

    def logout(self, credential: AppwriteCredential | None = None) -> None:
        if credential is not None:
            try:
                self.client.with_credential(credential).json("DELETE", "/account/sessions/current")
            except AppwriteError:
                pass
        self._clear_session()

    def _current_user(self, credential: AppwriteCredential) -> AuthenticatedUser:
        account = self.client.with_credential(credential).json("GET", "/account")
        user_id = str(account.get("$id") or account.get("id") or "").strip()
        if not user_id:
            raise AppwriteError("Appwrite did not return an account id.")
        profile = self._profile_for_user(credential, user_id)
        role = str(profile.get("role") or ROLE_CLIENT).strip().lower()
        if role not in VALID_ROLES:
            raise AppwriteError("Your AirTrixx profile has an invalid role. Ask an admin to fix it.")
        display_name = str(profile.get("display_name") or profile.get("name") or account.get("name") or "").strip()
        email = str(account.get("email") or profile.get("email") or "").strip()
        return AuthenticatedUser(
            user_id=user_id,
            email=email,
            name=display_name,
            role=role,
            credential=credential,
        )

    def _profile_for_user(self, credential: AppwriteCredential, user_id: str) -> dict[str, Any]:
        try:
            return self.client.with_credential(credential).json(
                "GET",
                f"/databases/{self.config.database_id}/collections/{self.config.profiles_collection_id}/documents/{user_id}",
            )
        except AppwriteError as exc:
            if exc.status == 404:
                raise AppwriteError("No AirTrixx profile exists for this account. Ask an admin to invite the user.") from exc
            raise

    def _credential_from_session(self, response: dict[str, Any]) -> AppwriteCredential:
        secret = str(response.get("secret") or "").strip()
        if secret:
            return AppwriteCredential.session(secret)
        raise AppwriteError("Appwrite did not return a session secret for this desktop login.")

    def _keyring_user(self) -> str:
        return f"{self.config.endpoint}|{self.config.project_id}"

    def _store_session(self, credential: AppwriteCredential) -> None:
        if keyring is None:
            return
        try:
            keyring.set_password("AirTrixx Appwrite", self._keyring_user(), credential.serialize())
        except Exception:
            pass

    def _load_session(self) -> AppwriteCredential | None:
        if keyring is None:
            return None
        try:
            stored = keyring.get_password("AirTrixx Appwrite", self._keyring_user())
        except Exception:
            return None
        if not stored:
            return None
        return AppwriteCredential.deserialize(stored)

    def _clear_session(self) -> None:
        if keyring is None:
            return
        try:
            keyring.delete_password("AirTrixx Appwrite", self._keyring_user())
        except Exception:
            pass
