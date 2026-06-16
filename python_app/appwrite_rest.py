from __future__ import annotations

import json
import mimetypes
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from appwrite_config import AppwriteConfig


@dataclass
class AppwriteCredential:
    kind: str
    value: str

    @classmethod
    def session(cls, secret: str) -> "AppwriteCredential":
        return cls("session", secret)

    @classmethod
    def cookie(cls, cookie: str) -> "AppwriteCredential":
        return cls("cookie", cookie)

    def serialize(self) -> str:
        return f"{self.kind}:{self.value}"

    @classmethod
    def deserialize(cls, value: str) -> "AppwriteCredential | None":
        kind, separator, payload = value.partition(":")
        if not separator or kind not in {"session", "cookie"} or not payload:
            return None
        return cls(kind, payload)


class AppwriteError(RuntimeError):
    def __init__(self, message: str, *, status: int | None = None, payload: Any = None) -> None:
        super().__init__(message)
        self.status = status
        self.payload = payload


class AppwriteRestClient:
    def __init__(
        self,
        config: AppwriteConfig,
        *,
        api_key: str = "",
        credential: AppwriteCredential | None = None,
        timeout_s: float = 20.0,
    ) -> None:
        self.config = config
        self.api_key = api_key
        self.credential = credential
        self.timeout_s = timeout_s

    def with_credential(self, credential: AppwriteCredential | None) -> "AppwriteRestClient":
        return AppwriteRestClient(self.config, api_key=self.api_key, credential=credential, timeout_s=self.timeout_s)

    def json(
        self,
        method: str,
        path: str,
        *,
        data: dict[str, Any] | None = None,
        query: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        body = None
        request_headers = self._headers(headers)
        if data is not None:
            body = json.dumps(data).encode("utf-8")
            request_headers["Content-Type"] = "application/json"
        response_body, _response_headers = self._request(method, path, body=body, query=query, headers=request_headers)
        if not response_body:
            return {}
        try:
            payload = json.loads(response_body.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise AppwriteError(f"Appwrite returned invalid JSON: {exc}") from exc
        if not isinstance(payload, dict):
            raise AppwriteError("Appwrite returned an unexpected response payload.", payload=payload)
        return payload

    def bytes(
        self,
        method: str,
        path: str,
        *,
        query: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> bytes:
        response_body, _response_headers = self._request(method, path, query=query, headers=self._headers(headers))
        return response_body

    def upload_file(
        self,
        bucket_id: str,
        file_path: Path,
        *,
        file_id: str | None = None,
        permissions: list[str] | None = None,
    ) -> dict[str, Any]:
        file_id = file_id or uuid.uuid4().hex
        boundary = f"----AirTrixxAppwrite{uuid.uuid4().hex}"
        content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
        payload = bytearray()
        payload.extend(self._multipart_field(boundary, "fileId", file_id))
        for permission in permissions or []:
            payload.extend(self._multipart_field(boundary, "permissions[]", permission))
        payload.extend(
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{file_path.name}"\r\n'
            f"Content-Type: {content_type}\r\n\r\n".encode("utf-8")
        )
        payload.extend(file_path.read_bytes())
        payload.extend(f"\r\n--{boundary}--\r\n".encode("utf-8"))
        headers = self._headers({"Content-Type": f"multipart/form-data; boundary={boundary}"})
        response_body, _response_headers = self._request(
            "POST",
            f"/storage/buckets/{bucket_id}/files",
            body=bytes(payload),
            headers=headers,
        )
        return json.loads(response_body.decode("utf-8")) if response_body else {}

    def _request(
        self,
        method: str,
        path: str,
        *,
        body: bytes | None = None,
        query: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[bytes, dict[str, str]]:
        if not self.config.configured:
            raise AppwriteError("Appwrite is not configured. Set APPWRITE_PROJECT_ID before signing in.")
        url = f"{self.config.endpoint}{path}"
        if query:
            url = f"{url}?{urlencode(query, doseq=True)}"
        request = Request(url, data=body, method=method.upper(), headers=headers or self._headers())
        try:
            with urlopen(request, timeout=self.timeout_s) as response:
                return response.read(), dict(response.headers.items())
        except HTTPError as exc:
            payload: Any = None
            message = f"Appwrite request failed with HTTP {exc.code}."
            try:
                raw = exc.read()
                if raw:
                    payload = json.loads(raw.decode("utf-8"))
                    if isinstance(payload, dict) and payload.get("message"):
                        message = str(payload["message"])
            except Exception:
                pass
            raise AppwriteError(message, status=exc.code, payload=payload) from exc
        except URLError as exc:
            raise AppwriteError(f"Could not reach Appwrite: {exc.reason}") from exc

    def _headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        headers = {
            "X-Appwrite-Project": self.config.project_id,
            "X-Appwrite-Response-Format": "1.6.0",
        }
        if self.api_key:
            headers["X-Appwrite-Key"] = self.api_key
        if self.credential:
            if self.credential.kind == "session":
                headers["X-Appwrite-Session"] = self.credential.value
            elif self.credential.kind == "cookie":
                headers["Cookie"] = self.credential.value
        if extra:
            headers.update(extra)
        return headers

    @staticmethod
    def _multipart_field(boundary: str, name: str, value: str) -> bytes:
        return (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
            f"{value}\r\n"
        ).encode("utf-8")
