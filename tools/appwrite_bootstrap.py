from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Any


DATABASE_ID = os.environ.get("AIRTRIXX_APPWRITE_DATABASE_ID", "airtrixx").strip() or "airtrixx"
PROFILES_COLLECTION_ID = os.environ.get("AIRTRIXX_APPWRITE_PROFILES_COLLECTION_ID", "user_profiles").strip() or "user_profiles"
SYNC_COLLECTION_ID = os.environ.get("AIRTRIXX_APPWRITE_SYNC_COLLECTION_ID", "sync_states").strip() or "sync_states"
BUCKET_ID = os.environ.get("AIRTRIXX_APPWRITE_BUCKET_ID", "airtrixx_user_artifacts").strip() or "airtrixx_user_artifacts"


@dataclass
class CliResult:
    code: int
    stdout: str
    stderr: str

    @property
    def text(self) -> str:
        return f"{self.stdout}\n{self.stderr}".strip()


def run_appwrite(*args: str, json_output: bool = False) -> CliResult:
    command = ["appwrite", *args]
    if json_output and "--json" not in command:
        command.append("--json")
    completed = subprocess.run(command, capture_output=True, text=True)
    return CliResult(completed.returncode, completed.stdout, completed.stderr)


def require_ok(result: CliResult, label: str) -> CliResult:
    if result.code == 0:
        return result
    print(result.text, file=sys.stderr)
    raise SystemExit(f"Appwrite CLI failed while creating {label}.")


def exists_message(result: CliResult) -> bool:
    text = result.text.lower()
    return result.code != 0 and ("already exists" in text or "conflict" in text or "409" in text)


def create_or_keep(label: str, exists_args: tuple[str, ...], create_args: tuple[str, ...]) -> None:
    exists = run_appwrite(*exists_args, json_output=True)
    if exists.code == 0:
        print(f"exists  {label}")
        return
    created = run_appwrite(*create_args, json_output=True)
    if created.code == 0 or exists_message(created):
        print(f"created {label}" if created.code == 0 else f"exists  {label}")
        return
    print(created.text, file=sys.stderr)
    raise SystemExit(f"Could not create {label}.")


def create_attribute(label: str, args: tuple[str, ...]) -> None:
    result = run_appwrite(*args, json_output=True)
    if result.code == 0:
        print(f"created {label}")
        return
    if exists_message(result):
        print(f"exists  {label}")
        return
    print(result.text, file=sys.stderr)
    raise SystemExit(f"Could not create {label}.")


def cli_debug_value(name: str) -> str:
    result = require_ok(run_appwrite("client", "--debug"), "CLI debug info")
    prefix = f"{name} : "
    for line in result.stdout.splitlines():
        if line.startswith(prefix):
            return line[len(prefix) :].strip()
    return ""


def collection_permissions() -> list[str]:
    return [
        'read("users")',
        'create("users")',
        'update("users")',
        'delete("users")',
    ]


def user_permissions(user_id: str) -> list[str]:
    role = f"user:{user_id}"
    return [f'read("{role}")', f'update("{role}")', f'delete("{role}")']


def json_arg(value: dict[str, Any]) -> str:
    return json.dumps(value, separators=(",", ":"))


def parse_json_result(result: CliResult) -> dict[str, Any]:
    require_ok(result, "JSON command")
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        print(result.stdout, file=sys.stderr)
        raise SystemExit(f"Appwrite CLI returned invalid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise SystemExit("Appwrite CLI returned a non-object JSON payload.")
    return value


def create_schema() -> None:
    create_or_keep(
        f"database {DATABASE_ID}",
        ("databases", "get", "--database-id", DATABASE_ID),
        ("databases", "create", "--database-id", DATABASE_ID, "--name", "AirTrixx", "--enabled", "true"),
    )

    permissions = collection_permissions()
    create_or_keep(
        f"collection {PROFILES_COLLECTION_ID}",
        ("databases", "get-collection", "--database-id", DATABASE_ID, "--collection-id", PROFILES_COLLECTION_ID),
        (
            "databases",
            "create-collection",
            "--database-id",
            DATABASE_ID,
            "--collection-id",
            PROFILES_COLLECTION_ID,
            "--name",
            "AirTrixx User Profiles",
            "--permissions",
            *permissions,
            "--document-security",
            "true",
            "--enabled",
            "true",
        ),
    )
    create_or_keep(
        f"collection {SYNC_COLLECTION_ID}",
        ("databases", "get-collection", "--database-id", DATABASE_ID, "--collection-id", SYNC_COLLECTION_ID),
        (
            "databases",
            "create-collection",
            "--database-id",
            DATABASE_ID,
            "--collection-id",
            SYNC_COLLECTION_ID,
            "--name",
            "AirTrixx Sync States",
            "--permissions",
            *permissions,
            "--document-security",
            "true",
            "--enabled",
            "true",
        ),
    )

    string_attrs = [
        (PROFILES_COLLECTION_ID, "user_id", "255", "true"),
        (PROFILES_COLLECTION_ID, "email", "320", "true"),
        (PROFILES_COLLECTION_ID, "display_name", "255", "true"),
        (PROFILES_COLLECTION_ID, "role", "32", "true"),
        (SYNC_COLLECTION_ID, "user_id", "255", "true"),
        (SYNC_COLLECTION_ID, "archive_file_id", "255", "true"),
        (SYNC_COLLECTION_ID, "archive_sha256", "128", "true"),
        (SYNC_COLLECTION_ID, "artifact_manifest_json", "65535", "true"),
        (SYNC_COLLECTION_ID, "updated_by_device_id", "255", "true"),
    ]
    for collection_id, key, size, required in string_attrs:
        create_attribute(
            f"{collection_id}.{key}",
            (
                "databases",
                "create-string-attribute",
                "--database-id",
                DATABASE_ID,
                "--collection-id",
                collection_id,
                "--key",
                key,
                "--size",
                size,
                "--required",
                required,
                "--array",
                "false",
                "--encrypt",
                "false",
            ),
        )
    create_attribute(
        f"{SYNC_COLLECTION_ID}.updated_at",
        (
            "databases",
            "create-datetime-attribute",
            "--database-id",
            DATABASE_ID,
            "--collection-id",
            SYNC_COLLECTION_ID,
            "--key",
            "updated_at",
            "--required",
            "true",
            "--array",
            "false",
        ),
    )

    create_or_keep(
        f"bucket {BUCKET_ID}",
        ("storage", "get-bucket", "--bucket-id", BUCKET_ID),
        (
            "storage",
            "create-bucket",
            "--bucket-id",
            BUCKET_ID,
            "--name",
            "AirTrixx User Artifacts",
            "--permissions",
            *permissions,
            "--file-security",
            "true",
            "--enabled",
            "true",
            "--maximum-file-size",
            "25000000",
            "--allowed-file-extensions",
            "zip",
            "--compression",
            "gzip",
            "--encryption",
            "true",
            "--antivirus",
            "true",
            "--transformations",
            "false",
        ),
    )


def find_user_id_by_email(email: str) -> str:
    result = run_appwrite("users", "list", "--search", email, json_output=True)
    payload = parse_json_result(result)
    users = payload.get("users") or []
    for user in users:
        if isinstance(user, dict) and str(user.get("email") or "").lower() == email.lower():
            return str(user.get("$id") or user.get("id") or "")
    return ""


def seed_admin() -> None:
    email = os.environ.get("AIRTRIXX_ADMIN_EMAIL", "").strip()
    password = os.environ.get("AIRTRIXX_ADMIN_PASSWORD", "").strip()
    name = os.environ.get("AIRTRIXX_ADMIN_NAME", "AirTrixx Admin").strip() or "AirTrixx Admin"
    if not email or not password:
        print("skipped admin seed; set AIRTRIXX_ADMIN_EMAIL and AIRTRIXX_ADMIN_PASSWORD to create it")
        return

    user_id = find_user_id_by_email(email)
    if user_id:
        print(f"exists  admin account {email}")
    else:
        created = parse_json_result(
            run_appwrite(
                "users",
                "create",
                "--user-id",
                "unique()",
                "--email",
                email,
                "--password",
                password,
                "--name",
                name,
                json_output=True,
            )
        )
        user_id = str(created.get("$id") or created.get("id") or "")
        print(f"created admin account {email}")

    if not user_id:
        raise SystemExit("Could not determine admin account user id.")

    data = {
        "user_id": user_id,
        "email": email,
        "display_name": name,
        "role": "admin",
    }
    permissions = user_permissions(user_id)
    update = run_appwrite(
        "databases",
        "update-document",
        "--database-id",
        DATABASE_ID,
        "--collection-id",
        PROFILES_COLLECTION_ID,
        "--document-id",
        user_id,
        "--data",
        json_arg(data),
        "--permissions",
        *permissions,
        json_output=True,
    )
    if update.code == 0:
        print(f"updated admin profile {user_id}")
        return
    create = run_appwrite(
        "databases",
        "create-document",
        "--database-id",
        DATABASE_ID,
        "--collection-id",
        PROFILES_COLLECTION_ID,
        "--document-id",
        user_id,
        "--data",
        json_arg(data),
        "--permissions",
        *permissions,
        json_output=True,
    )
    require_ok(create, f"admin profile {user_id}")
    print(f"created admin profile {user_id}")


def main() -> int:
    endpoint = cli_debug_value("endpoint")
    project_id = cli_debug_value("projectId")
    if not endpoint or not project_id:
        raise SystemExit("Configure the Appwrite CLI first: appwrite client --endpoint <url> --project-id <id>")
    print(f"Using Appwrite CLI project {project_id} at {endpoint}")
    create_schema()
    time.sleep(2.0)
    seed_admin()
    print("AirTrixx Appwrite bootstrap complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
