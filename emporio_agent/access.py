"""Access approval gate for the public demo, backed by Firebase Realtime Database (REST) or memory."""
from __future__ import annotations

import hashlib
import json
import re
import secrets
import threading
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Protocol

VALID_STATUSES = ("pending", "approved", "denied")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class AccessError(ValueError):
    """Raised when an access request or decision has invalid input."""


@dataclass
class AccessRecord:
    key: str
    email: str
    name: str
    note: str
    status: str
    token: str
    created_at: str
    updated_at: str

    def public_dict(self) -> dict[str, str]:
        return {
            "key": self.key,
            "email": self.email,
            "name": self.name,
            "note": self.note,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


def normalize_email(email: str) -> str:
    cleaned = email.strip().lower()
    if not _EMAIL_RE.match(cleaned) or len(cleaned) > 254:
        raise AccessError("Informe um e-mail válido.")
    return cleaned


def email_to_key(email: str) -> str:
    return hashlib.sha256(normalize_email(email).encode("utf-8")).hexdigest()[:24]


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class AccessStore(Protocol):
    def request_access(self, name: str, email: str, note: str = "", auto_approve: bool = False) -> tuple[AccessRecord, bool]:
        """Create or fetch an access request. Returns (record, expose_token)."""

    def get_by_token(self, token: str) -> AccessRecord | None:
        """Look up an access record by its bearer token."""

    def list_requests(self) -> list[AccessRecord]:
        """Return all access requests, newest first."""

    def set_status(self, key: str, status: str) -> AccessRecord | None:
        """Update the status of a request by its key."""


class InMemoryAccessStore:
    """Thread-safe in-memory store for local testing and unit tests."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._records: dict[str, AccessRecord] = {}

    def request_access(self, name: str, email: str, note: str = "", auto_approve: bool = False) -> tuple[AccessRecord, bool]:
        cleaned_name = name.strip()
        if not cleaned_name:
            raise AccessError("Informe seu nome.")
        cleaned_email = normalize_email(email)
        key = email_to_key(cleaned_email)
        now = _now_iso()
        with self._lock:
            existing = self._records.get(key)
            if existing is not None:
                if auto_approve and existing.status != "approved":
                    existing.status = "approved"
                    existing.updated_at = now
                    return existing, True
                # Never hand out an already-approved token to an unauthenticated re-request.
                return existing, existing.status == "pending"
            status = "approved" if auto_approve else "pending"
            record = AccessRecord(
                key=key,
                email=cleaned_email,
                name=cleaned_name[:120],
                note=note.strip()[:300],
                status=status,
                token=secrets.token_urlsafe(24),
                created_at=now,
                updated_at=now,
            )
            self._records[key] = record
            return record, True

    def get_by_token(self, token: str) -> AccessRecord | None:
        if not token:
            return None
        with self._lock:
            for record in self._records.values():
                if secrets.compare_digest(record.token, token):
                    return record
        return None

    def list_requests(self) -> list[AccessRecord]:
        with self._lock:
            items = list(self._records.values())
        items.sort(key=lambda r: r.created_at, reverse=True)
        return items

    def set_status(self, key: str, status: str) -> AccessRecord | None:
        if status not in VALID_STATUSES:
            raise AccessError(f"Status inválido: {status}")
        with self._lock:
            record = self._records.get(key)
            if record is None:
                return None
            record.status = status
            record.updated_at = _now_iso()
            return record


class FirebaseRTDBAccessStore:
    """Zero-dependency Firebase Realtime Database store over HTTPS REST."""

    def __init__(self, db_url: str, db_secret: str | None = None, timeout: float = 8.0, opener=urllib.request.urlopen) -> None:
        cleaned_url = db_url.strip().rstrip("/")
        if not cleaned_url.startswith("https://"):
            raise AccessError("FIREBASE_DB_URL deve começar com https://")
        self._db_url = cleaned_url
        self._db_secret = db_secret.strip() if db_secret else None
        self._timeout = timeout
        self._opener = opener

    def _endpoint(self, path: str) -> str:
        url = f"{self._db_url}/{path.lstrip('/')}.json"
        if self._db_secret:
            url += "?" + urllib.parse.urlencode({"auth": self._db_secret})
        return url

    def _request(self, method: str, path: str, payload: dict | None = None):
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        headers = {"Content-Type": "application/json"} if data is not None else {}
        req = urllib.request.Request(self._endpoint(path), data=data, headers=headers, method=method)
        try:
            with self._opener(req, timeout=self._timeout) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"Firebase HTTP {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError("Firebase indisponível") from exc

    @staticmethod
    def _from_dict(key: str, data: dict) -> AccessRecord:
        return AccessRecord(
            key=key,
            email=str(data.get("email", "")),
            name=str(data.get("name", "")),
            note=str(data.get("note", "")),
            status=str(data.get("status", "pending")),
            token=str(data.get("token", "")),
            created_at=str(data.get("created_at", "")),
            updated_at=str(data.get("updated_at", "")),
        )

    def request_access(self, name: str, email: str, note: str = "", auto_approve: bool = False) -> tuple[AccessRecord, bool]:
        cleaned_name = name.strip()
        if not cleaned_name:
            raise AccessError("Informe seu nome.")
        cleaned_email = normalize_email(email)
        key = email_to_key(cleaned_email)
        now = _now_iso()

        existing_data = self._request("GET", f"access_requests/{key}")
        if isinstance(existing_data, dict):
            existing = self._from_dict(key, existing_data)
            if auto_approve and existing.status != "approved":
                self._request("PATCH", f"access_requests/{key}", {"status": "approved", "updated_at": now})
                existing.status = "approved"
                existing.updated_at = now
                return existing, True
            return existing, existing.status == "pending"

        record = AccessRecord(
            key=key,
            email=cleaned_email,
            name=cleaned_name[:120],
            note=note.strip()[:300],
            status="approved" if auto_approve else "pending",
            token=secrets.token_urlsafe(24),
            created_at=now,
            updated_at=now,
        )
        self._request("PUT", f"access_requests/{key}", asdict(record))
        return record, True

    def get_by_token(self, token: str) -> AccessRecord | None:
        if not token:
            return None
        all_data = self._request("GET", "access_requests")
        if not isinstance(all_data, dict):
            return None
        for key, item in all_data.items():
            if isinstance(item, dict):
                stored_token = str(item.get("token", ""))
                if stored_token and secrets.compare_digest(stored_token, token):
                    return self._from_dict(key, item)
        return None

    def list_requests(self) -> list[AccessRecord]:
        all_data = self._request("GET", "access_requests")
        if not isinstance(all_data, dict):
            return []
        records = [self._from_dict(k, v) for k, v in all_data.items() if isinstance(v, dict)]
        records.sort(key=lambda r: r.created_at, reverse=True)
        return records

    def set_status(self, key: str, status: str) -> AccessRecord | None:
        if status not in VALID_STATUSES:
            raise AccessError(f"Status inválido: {status}")
        existing_data = self._request("GET", f"access_requests/{key}")
        if not isinstance(existing_data, dict):
            return None
        now = _now_iso()
        self._request("PATCH", f"access_requests/{key}", {"status": status, "updated_at": now})
        existing_data["status"] = status
        existing_data["updated_at"] = now
        return self._from_dict(key, existing_data)
