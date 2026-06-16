from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass


DEFAULT_APPWRITE_ENDPOINT = "https://cloud.appwrite.io/v1"
DEFAULT_DATABASE_ID = "airtrixx"
DEFAULT_PROFILES_COLLECTION_ID = "user_profiles"
DEFAULT_SYNC_COLLECTION_ID = "sync_states"
DEFAULT_BUCKET_ID = "airtrixx_user_artifacts"


@dataclass(frozen=True)
class AppwriteConfig:
    endpoint: str = DEFAULT_APPWRITE_ENDPOINT
    project_id: str = ""
    database_id: str = DEFAULT_DATABASE_ID
    profiles_collection_id: str = DEFAULT_PROFILES_COLLECTION_ID
    sync_collection_id: str = DEFAULT_SYNC_COLLECTION_ID
    bucket_id: str = DEFAULT_BUCKET_ID

    @property
    def configured(self) -> bool:
        return bool(self.endpoint.strip() and self.project_id.strip())


def load_appwrite_config() -> AppwriteConfig:
    cli_endpoint, cli_project_id = _load_cli_client_config()
    return AppwriteConfig(
        endpoint=os.environ.get("APPWRITE_ENDPOINT", cli_endpoint or DEFAULT_APPWRITE_ENDPOINT).rstrip("/"),
        project_id=os.environ.get("APPWRITE_PROJECT_ID", cli_project_id).strip(),
        database_id=os.environ.get("AIRTRIXX_APPWRITE_DATABASE_ID", DEFAULT_DATABASE_ID).strip() or DEFAULT_DATABASE_ID,
        profiles_collection_id=os.environ.get(
            "AIRTRIXX_APPWRITE_PROFILES_COLLECTION_ID",
            DEFAULT_PROFILES_COLLECTION_ID,
        ).strip()
        or DEFAULT_PROFILES_COLLECTION_ID,
        sync_collection_id=os.environ.get(
            "AIRTRIXX_APPWRITE_SYNC_COLLECTION_ID",
            DEFAULT_SYNC_COLLECTION_ID,
        ).strip()
        or DEFAULT_SYNC_COLLECTION_ID,
        bucket_id=os.environ.get("AIRTRIXX_APPWRITE_BUCKET_ID", DEFAULT_BUCKET_ID).strip() or DEFAULT_BUCKET_ID,
    )


def _load_cli_client_config() -> tuple[str, str]:
    try:
        completed = subprocess.run(
            ["appwrite", "client", "--debug"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except Exception:
        return "", ""
    if completed.returncode != 0:
        return "", ""
    values: dict[str, str] = {}
    for line in completed.stdout.splitlines():
        key, separator, value = line.partition(" : ")
        if separator:
            values[key.strip()] = value.strip()
    return values.get("endpoint", ""), values.get("projectId", "")
