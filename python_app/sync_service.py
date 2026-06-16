from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app_paths import AppPaths
from appwrite_config import AppwriteConfig
from appwrite_rest import AppwriteCredential, AppwriteError, AppwriteRestClient


SYNC_RELATIVE_FILES = (
    "config/input_mappings.json",
    "config/calibration.json",
    "keyboard/raw_samples.csv",
    "keyboard/raw_samples.csv.meta.json",
    "keyboard/current_training_words.txt",
    "keyboard/word_knn_model.npz",
)
LOCAL_SYNC_STATE = "config/cloud_sync_state.json"


@dataclass
class SyncResult:
    changed: bool
    action: str
    message: str
    last_synced_at: str = ""
    error: str = ""


class AppwriteSyncService:
    def __init__(
        self,
        config: AppwriteConfig,
        *,
        client: AppwriteRestClient | None = None,
        log: Any = None,
    ) -> None:
        self.config = config
        self.client = client or AppwriteRestClient(config)
        self.log = log

    @property
    def configured(self) -> bool:
        return self.config.configured

    def sync_on_login(self, *, user_id: str, credential: AppwriteCredential, paths: AppPaths) -> SyncResult:
        try:
            cloud = self._cloud_state(user_id, credential)
            if cloud is None:
                if self._has_any_local_file(paths):
                    return self.upload(user_id=user_id, credential=credential, paths=paths, reason="initial upload")
                return SyncResult(False, "idle", "No local or cloud data to sync.")

            cloud_updated = self._parse_time(str(cloud.get("updated_at") or cloud.get("$updatedAt") or ""))
            local_updated = self._local_updated_at(paths)
            if local_updated and cloud_updated and local_updated > cloud_updated:
                return self.upload(user_id=user_id, credential=credential, paths=paths, reason="local newer")
            return self.download(user_id=user_id, credential=credential, paths=paths, cloud_state=cloud)
        except Exception as exc:
            return SyncResult(False, "error", "Cloud sync failed.", error=str(exc))

    def upload(
        self,
        *,
        user_id: str,
        credential: AppwriteCredential,
        paths: AppPaths,
        reason: str = "manual",
    ) -> SyncResult:
        with tempfile.TemporaryDirectory(prefix="airtrixx-sync-") as tmpdir:
            archive_path, manifest = self._create_archive(paths, Path(tmpdir))
            if not manifest["files"]:
                return SyncResult(False, "idle", "No syncable user data exists yet.")
            permissions = self._user_permissions(user_id)
            file_doc = self.client.with_credential(credential).upload_file(
                self.config.bucket_id,
                archive_path,
                permissions=permissions,
            )
            file_id = str(file_doc.get("$id") or file_doc.get("id") or "")
            if not file_id:
                raise AppwriteError("Appwrite storage upload did not return a file id.")
            now = self._now()
            payload = {
                "user_id": user_id,
                "archive_file_id": file_id,
                "archive_sha256": manifest["archive_sha256"],
                "artifact_manifest_json": json.dumps(manifest, separators=(",", ":")),
                "updated_at": now,
                "updated_by_device_id": manifest["device_id"],
            }
            self._upsert_cloud_state(user_id, credential, payload)
            self._write_local_state(paths, {"updated_at": now, "archive_sha256": manifest["archive_sha256"], "reason": reason})
            return SyncResult(True, "upload", f"Uploaded AirTrixx user data ({reason}).", last_synced_at=now)

    def download(
        self,
        *,
        user_id: str,
        credential: AppwriteCredential,
        paths: AppPaths,
        cloud_state: dict[str, Any] | None = None,
    ) -> SyncResult:
        cloud_state = cloud_state or self._cloud_state(user_id, credential)
        if not cloud_state:
            return SyncResult(False, "idle", "No cloud data is available for this user.")
        file_id = str(cloud_state.get("archive_file_id") or "").strip()
        if not file_id:
            return SyncResult(False, "idle", "Cloud sync state has no archive file.")
        archive = self.client.with_credential(credential).bytes(
            "GET",
            f"/storage/buckets/{self.config.bucket_id}/files/{file_id}/download",
        )
        expected_sha = str(cloud_state.get("archive_sha256") or "")
        actual_sha = hashlib.sha256(archive).hexdigest()
        if expected_sha and expected_sha != actual_sha:
            raise AppwriteError("Downloaded cloud archive checksum did not match sync metadata.")
        backup = self._backup_local(paths)
        self._extract_archive(paths, archive)
        updated_at = str(cloud_state.get("updated_at") or cloud_state.get("$updatedAt") or self._now())
        self._write_local_state(paths, {"updated_at": updated_at, "archive_sha256": actual_sha, "backup": str(backup) if backup else ""})
        return SyncResult(True, "download", "Downloaded AirTrixx user data from cloud.", last_synced_at=updated_at)

    def seed_user_from_legacy(self, legacy_paths: AppPaths, user_paths: AppPaths) -> None:
        if self._has_any_local_file(user_paths):
            return
        for relative in SYNC_RELATIVE_FILES:
            source = legacy_paths.user_data_dir / relative
            target = user_paths.user_data_dir / relative
            if source.exists() and source.is_file():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)

    def _cloud_state(self, user_id: str, credential: AppwriteCredential) -> dict[str, Any] | None:
        try:
            return self.client.with_credential(credential).json(
                "GET",
                f"/databases/{self.config.database_id}/collections/{self.config.sync_collection_id}/documents/{user_id}",
            )
        except AppwriteError as exc:
            if exc.status == 404:
                return None
            raise

    def _upsert_cloud_state(self, user_id: str, credential: AppwriteCredential, payload: dict[str, Any]) -> None:
        authed = self.client.with_credential(credential)
        try:
            authed.json(
                "PATCH",
                f"/databases/{self.config.database_id}/collections/{self.config.sync_collection_id}/documents/{user_id}",
                data={"data": payload},
            )
        except AppwriteError as exc:
            if exc.status != 404:
                raise
            authed.json(
                "POST",
                f"/databases/{self.config.database_id}/collections/{self.config.sync_collection_id}/documents",
                data={"documentId": user_id, "data": payload, "permissions": self._user_permissions(user_id)},
            )

    def _create_archive(self, paths: AppPaths, tmpdir: Path) -> tuple[Path, dict[str, Any]]:
        archive_path = tmpdir / "airtrixx-user-data.zip"
        manifest: dict[str, Any] = {
            "version": 1,
            "created_at": self._now(),
            "device_id": self._device_id(paths),
            "files": [],
        }
        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for relative in SYNC_RELATIVE_FILES:
                path = paths.user_data_dir / relative
                if not path.exists() or not path.is_file():
                    continue
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                manifest["files"].append(
                    {
                        "path": relative,
                        "sha256": digest,
                        "size": path.stat().st_size,
                        "mtime_ns": path.stat().st_mtime_ns,
                    }
                )
                archive.write(path, relative)
            archive.writestr("manifest.json", json.dumps(manifest, indent=2) + "\n")
        manifest["archive_sha256"] = hashlib.sha256(archive_path.read_bytes()).hexdigest()
        return archive_path, manifest

    def _extract_archive(self, paths: AppPaths, archive_bytes: bytes) -> None:
        with tempfile.TemporaryDirectory(prefix="airtrixx-sync-pull-") as tmpdir:
            archive_path = Path(tmpdir) / "cloud.zip"
            archive_path.write_bytes(archive_bytes)
            with zipfile.ZipFile(archive_path, "r") as archive:
                names = set(archive.namelist())
                for relative in SYNC_RELATIVE_FILES:
                    if relative not in names:
                        target = paths.user_data_dir / relative
                        if target.exists() and target.is_file():
                            target.unlink()
                        continue
                    target = paths.user_data_dir / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(relative) as source, target.open("wb") as destination:
                        shutil.copyfileobj(source, destination)

    def _backup_local(self, paths: AppPaths) -> Path | None:
        existing = [paths.user_data_dir / relative for relative in SYNC_RELATIVE_FILES if (paths.user_data_dir / relative).exists()]
        if not existing:
            return None
        backup_dir = paths.user_data_dir / "backups" / f"cloud_pull_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        for source in existing:
            target = backup_dir / source.relative_to(paths.user_data_dir)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        return backup_dir

    def _local_updated_at(self, paths: AppPaths) -> datetime | None:
        timestamps = [
            datetime.fromtimestamp((paths.user_data_dir / relative).stat().st_mtime, timezone.utc)
            for relative in SYNC_RELATIVE_FILES
            if (paths.user_data_dir / relative).exists()
        ]
        return max(timestamps) if timestamps else None

    def _has_any_local_file(self, paths: AppPaths) -> bool:
        return any((paths.user_data_dir / relative).exists() for relative in SYNC_RELATIVE_FILES)

    def _write_local_state(self, paths: AppPaths, payload: dict[str, Any]) -> None:
        path = paths.user_data_dir / LOCAL_SYNC_STATE
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    def _device_id(self, paths: AppPaths) -> str:
        path = paths.config_dir / "device_id.txt"
        if path.exists():
            value = path.read_text(encoding="utf-8").strip()
            if value:
                return value
        import uuid

        value = uuid.uuid4().hex
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value + "\n", encoding="utf-8")
        return value

    @staticmethod
    def _parse_time(value: str) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
        except ValueError:
            return None

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _user_permissions(user_id: str) -> list[str]:
        role = f'user:{user_id}'
        return [f'read("{role}")', f'update("{role}")', f'delete("{role}")']
