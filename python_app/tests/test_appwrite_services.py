from __future__ import annotations

import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app_paths import build_app_paths_for_root, ensure_app_paths
from appwrite_config import AppwriteConfig
from appwrite_rest import AppwriteCredential, AppwriteError
from auth_service import AppwriteAuthService
from sync_service import AppwriteSyncService


class FakeAuthClient:
    def __init__(self) -> None:
        self.credential: AppwriteCredential | None = None

    def with_credential(self, credential: AppwriteCredential):
        clone = FakeAuthClient()
        clone.credential = credential
        return clone

    def json(self, method: str, path: str, **kwargs):
        if method == "POST" and path == "/account/sessions/email":
            return {"secret": "session-secret"}
        if method == "GET" and path == "/account":
            self._assert_session()
            return {"$id": "user_123", "email": "client@example.com", "name": "Client"}
        if method == "GET" and path.endswith("/collections/user_profiles/documents/user_123"):
            self._assert_session()
            return {"role": "client", "display_name": "Client User"}
        raise AssertionError((method, path, kwargs))

    def _assert_session(self) -> None:
        assert self.credential is not None
        assert self.credential.kind == "session"
        assert self.credential.value == "session-secret"


class FakeSyncClient:
    def __init__(self) -> None:
        self.created_docs: list[dict] = []
        self.uploaded_archive: bytes | None = None
        self.credential: AppwriteCredential | None = None

    def with_credential(self, credential: AppwriteCredential):
        self.credential = credential
        return self

    def upload_file(self, bucket_id: str, file_path: Path, **kwargs):
        self.uploaded_archive = file_path.read_bytes()
        self.upload_permissions = kwargs.get("permissions")
        return {"$id": "archive_1"}

    def json(self, method: str, path: str, **kwargs):
        if method == "PATCH":
            raise AppwriteError("missing", status=404)
        if method == "POST" and path.endswith("/documents"):
            self.created_docs.append(kwargs["data"])
            return {"$id": kwargs["data"]["documentId"]}
        raise AssertionError((method, path, kwargs))


class AppwriteAuthServiceTests(unittest.TestCase):
    def test_login_loads_profile_role(self) -> None:
        service = AppwriteAuthService(AppwriteConfig(project_id="project"), client=FakeAuthClient())
        with patch("auth_service.keyring", None):
            user = service.login("client@example.com", "password")

        self.assertEqual(user.user_id, "user_123")
        self.assertEqual(user.role, "client")
        self.assertEqual(user.display_name, "Client User")
        self.assertEqual(user.credential.value, "session-secret")


class AppwriteSyncServiceTests(unittest.TestCase):
    def test_upload_archives_core_user_files_and_creates_state(self) -> None:
        fake_client = FakeSyncClient()
        service = AppwriteSyncService(AppwriteConfig(project_id="project"), client=fake_client)
        with tempfile.TemporaryDirectory() as tmpdir:
            paths = build_app_paths_for_root(Path(tmpdir))
            ensure_app_paths(paths)
            paths.mapping_path.write_text('{"version":1}\n', encoding="utf-8")
            paths.calibration_path.write_text('{"cam_pan_center":307}\n', encoding="utf-8")

            result = service.upload(
                user_id="user_123",
                credential=AppwriteCredential.session("session-secret"),
                paths=paths,
                reason="test",
            )

        self.assertTrue(result.changed)
        self.assertEqual(result.action, "upload")
        self.assertEqual(fake_client.upload_permissions, ['read("user:user_123")', 'update("user:user_123")', 'delete("user:user_123")'])
        self.assertEqual(len(fake_client.created_docs), 1)
        data = fake_client.created_docs[0]["data"]
        self.assertEqual(data["archive_file_id"], "archive_1")
        manifest = json.loads(data["artifact_manifest_json"])
        self.assertEqual({item["path"] for item in manifest["files"]}, {"config/input_mappings.json", "config/calibration.json"})
        assert fake_client.uploaded_archive is not None
        with tempfile.TemporaryDirectory() as extract_dir:
            archive_path = Path(extract_dir) / "archive.zip"
            archive_path.write_bytes(fake_client.uploaded_archive)
            with zipfile.ZipFile(archive_path) as archive:
                self.assertIn("manifest.json", archive.namelist())
                self.assertIn("config/input_mappings.json", archive.namelist())


if __name__ == "__main__":
    unittest.main()
