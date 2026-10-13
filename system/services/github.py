from __future__ import annotations

import base64
import hashlib
import os
import re
import secrets
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import quote, urlencode, urlparse

import httpx
from cryptography.fernet import Fernet, InvalidToken
from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field

from system.paths import default_env_path
from system.services.database import Database
from system.services.git_service import GitError, GitRepository


GITHUB_API_VERSION = "2026-03-10"
_SAFE_SLUG = re.compile(r"[^A-Za-z0-9._-]+")


class GitHubIntegrationError(RuntimeError):
    pass


class GitHubNotConfigured(GitHubIntegrationError):
    pass


class GitHubAuthorizationError(GitHubIntegrationError):
    pass


class GitHubConnectionRequired(GitHubIntegrationError):
    pass


class GitHubRepositoryAlreadyManaged(GitHubIntegrationError):
    pass


class GitHubStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    configured: bool
    setup_required: bool
    setup_allowed: bool
    connection_allowed: bool
    connected: bool
    login: str | None = None
    github_user_id: int | None = None
    connected_at: datetime | None = None
    token_expires_at: datetime | None = None
    install_url: str | None = None


class GitHubAppSetup(BaseModel):
    model_config = ConfigDict(extra="forbid")

    registration_url: str
    manifest: dict[str, object]
    expires_at: datetime


class GitHubDisconnectResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    disconnected: bool
    remote_token_revoked: bool


class GitHubRepository(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int = Field(gt=0)
    installation_id: int = Field(gt=0)
    name: str
    full_name: str
    private: bool
    visibility: str
    description: str | None = None
    html_url: str
    default_branch: str
    archived: bool
    updated_at: datetime | None = None
    permissions: dict[str, bool]
    clone_url: str = Field(exclude=True, repr=False)


class GitHubPullRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    number: int = Field(gt=0)
    title: str = Field(min_length=1, max_length=1000)
    html_url: str = Field(min_length=10, max_length=1000)
    draft: bool = False
    author: str = Field(min_length=1, max_length=200)
    base_ref: str = Field(min_length=1, max_length=255)
    base_sha: str = Field(pattern=r"^[0-9a-fA-F]{40,64}$")
    head_ref: str = Field(min_length=1, max_length=255)
    head_sha: str = Field(pattern=r"^[0-9a-fA-F]{40,64}$")
    updated_at: str | None = None


@dataclass(frozen=True, repr=False)
class GitHubConfig:
    client_id: str | None
    client_secret: str | None
    app_slug: str | None
    authorize_url: str
    token_url: str
    api_url: str
    web_url: str
    manifest_url: str
    clone_host: str
    repositories_dir: Path
    product_origin: str | None
    timeout_seconds: float = 20.0

    @classmethod
    def from_env(cls, *, database_path: Path) -> GitHubConfig:
        load_dotenv(dotenv_path=default_env_path(), override=False)
        repositories_dir = Path(
            os.environ.get(
                "CONSENSUS_GITHUB_REPOSITORIES_DIR",
                str(database_path.parent / "repositories"),
            )
        ).expanduser().resolve()
        api_url = os.environ.get("GITHUB_API_URL", "https://api.github.com").rstrip("/")
        api_host = urlparse(api_url).hostname or "api.github.com"
        authorize_url = os.environ.get(
            "GITHUB_AUTHORIZE_URL", "https://github.com/login/oauth/authorize"
        )
        authorize = urlparse(authorize_url)
        web_url = os.environ.get(
            "GITHUB_WEB_URL", f"{authorize.scheme}://{authorize.netloc}"
        ).rstrip("/")
        web = urlparse(web_url)
        if (
            web.scheme not in {"http", "https"}
            or not web.hostname
            or web.username
            or web.password
            or web.path not in {"", "/"}
            or web.query
            or web.fragment
        ):
            raise GitHubIntegrationError("GITHUB_WEB_URL must be an HTTP(S) origin")
        configured_origin = os.environ.get("AGENTIC_CONSENSUS_PUBLIC_ORIGIN")
        vercel_url = os.environ.get("VERCEL_URL")
        product_origin = configured_origin or (
            f"https://{vercel_url}" if vercel_url else None
        )
        if product_origin is not None:
            product_origin = product_origin.rstrip("/")
            product = urlparse(product_origin)
            if (
                product.scheme != "https"
                or not product.hostname
                or product.username
                or product.password
                or product.path not in {"", "/"}
                or product.query
                or product.fragment
            ):
                raise GitHubIntegrationError(
                    "AGENTIC_CONSENSUS_PUBLIC_ORIGIN or VERCEL_URL must identify an HTTPS origin"
                )
        return cls(
            client_id=os.environ.get("GITHUB_CLIENT_ID") or None,
            client_secret=os.environ.get("GITHUB_CLIENT_SECRET") or None,
            app_slug=os.environ.get("GITHUB_APP_SLUG") or None,
            authorize_url=authorize_url,
            token_url=os.environ.get(
                "GITHUB_TOKEN_URL", "https://github.com/login/oauth/access_token"
            ),
            api_url=api_url,
            web_url=web_url,
            manifest_url=os.environ.get(
                "GITHUB_MANIFEST_URL", f"{web_url}/settings/apps/new"
            ),
            clone_host=os.environ.get(
                "GITHUB_CLONE_HOST",
                "github.com" if api_host == "api.github.com" else api_host,
            ).casefold(),
            repositories_dir=repositories_dir,
            product_origin=product_origin,
            timeout_seconds=float(os.environ.get("CONSENSUS_GITHUB_TIMEOUT", "20")),
        )

    @property
    def configured(self) -> bool:
        return bool(self.client_id and self.client_secret and self.app_slug)

    @property
    def install_url(self) -> str | None:
        if not self.app_slug:
            return None
        return f"{self.web_url}/apps/{self.app_slug}/installations/new"

    def require_configured(self) -> None:
        if not self.configured:
            raise GitHubNotConfigured("Connect GitHub to finish the one-time setup")


@dataclass(frozen=True, repr=False)
class _GitHubAppCredentials:
    client_id: str
    client_secret: str
    app_slug: str


    def install_url(self, web_url: str) -> str:
        return f"{web_url}/apps/{self.app_slug}/installations/new"


class _TokenCipher:
    def __init__(self, key_path: Path):
        self.key_path = key_path

    def _key(self) -> bytes:
        self.key_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            descriptor = os.open(
                self.key_path,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
            )
        except FileExistsError:
            key = self.key_path.read_bytes().strip()
        else:
            key = Fernet.generate_key()
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(key + b"\n")
                handle.flush()
                os.fsync(handle.fileno())
        os.chmod(self.key_path, 0o600)
        try:
            Fernet(key)
        except (TypeError, ValueError) as exc:
            raise GitHubIntegrationError("GitHub credential encryption key is invalid") from exc
        return key

    def encrypt(self, value: str) -> str:
        if not value:
            raise ValueError("cannot encrypt an empty GitHub credential")
        return Fernet(self._key()).encrypt(value.encode()).decode()

    def decrypt(self, value: str) -> str:
        try:
            return Fernet(self._key()).decrypt(value.encode()).decode()
        except (InvalidToken, ValueError, UnicodeDecodeError) as exc:
            raise GitHubIntegrationError("stored GitHub credential cannot be decrypted") from exc


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _future_time(seconds: object) -> datetime | None:
    if seconds is None:
        return None
    try:
        duration = int(seconds)
    except (TypeError, ValueError) as exc:
        raise GitHubAuthorizationError("GitHub returned an invalid token lifetime") from exc
    return datetime.now(UTC) + timedelta(seconds=max(0, duration))


class GitHubService:
    def __init__(self, database: Database, config: GitHubConfig | None = None):
        self.database = database
        self.config = config or GitHubConfig.from_env(database_path=database.path)
        key_path = Path(
            os.environ.get(
                "CONSENSUS_GITHUB_TOKEN_KEY_PATH",
                str(database.path.parent / "github-token.key"),
            )
        ).expanduser().resolve()
        self.cipher = _TokenCipher(key_path)

    def _credentials(self) -> _GitHubAppCredentials | None:
        if self.config.configured:
            return _GitHubAppCredentials(
                client_id=str(self.config.client_id),
                client_secret=str(self.config.client_secret),
                app_slug=str(self.config.app_slug),
            )
        record = self.database.get_github_app_config()
        if record is None:
            return None
        return _GitHubAppCredentials(
            client_id=record["client_id"],
            client_secret=self.cipher.decrypt(record["client_secret_ciphertext"]),
            app_slug=record["slug"],
        )

    def _require_credentials(self) -> _GitHubAppCredentials:
        credentials = self._credentials()
        if credentials is None:
            raise GitHubNotConfigured("Connect GitHub to finish the one-time setup")
        return credentials

    def install_url(self) -> str:
        return self._require_credentials().install_url(self.config.web_url)

    def status(
        self,
        user_id: str,
        *,
        setup_allowed: bool = False,
        connection_allowed: bool = False,
    ) -> GitHubStatus:
        connection = self.database.get_github_connection(user_id)
        credentials = self._credentials()
        return GitHubStatus(
            configured=credentials is not None,
            setup_required=credentials is None,
            setup_allowed=setup_allowed,
            connection_allowed=connection_allowed,
            connected=connection is not None,
            login=connection["login"] if connection else None,
            github_user_id=connection["github_user_id"] if connection else None,
            connected_at=_parse_time(connection["connected_at"]) if connection else None,
            token_expires_at=(
                _parse_time(connection["token_expires_at"]) if connection else None
            ),
            install_url=(
                credentials.install_url(self.config.web_url) if credentials else None
            ),
        )

    def _validate_origin(self, origin: str) -> str:
        parsed = urlparse(origin)
        normalized = origin.rstrip("/")
        local_origin = parsed.hostname in {"127.0.0.1", "localhost", "::1"}
        configured_origin = (
            self.config.product_origin is not None
            and secrets.compare_digest(normalized, self.config.product_origin)
        )
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
            or not (local_origin or configured_origin)
            or (configured_origin and parsed.scheme != "https")
        ):
            raise ValueError("GitHub setup origin is not allowed")
        return normalized

    def begin_app_setup(self, *, user_id: str, origin: str) -> GitHubAppSetup:
        if self._credentials() is not None:
            raise GitHubIntegrationError("GitHub is already ready on this instance")
        origin = self._validate_origin(origin)
        state = secrets.token_urlsafe(40)
        now = datetime.now(UTC)
        expires_at = now + timedelta(minutes=30)
        oauth_redirect_uri = f"{origin}/api/github/oauth/callback"
        self.database.save_github_app_manifest_state(
            {
                "state_hash": hashlib.sha256(state.encode()).hexdigest(),
                "user_id": user_id,
                "origin": origin,
                "oauth_redirect_uri": oauth_redirect_uri,
                "created_at": now.isoformat(),
                "expires_at": expires_at.isoformat(),
            }
        )
        manifest = {
            "name": f"AgenticConsensus {state[:8]}",
            "url": f"{origin}/",
            "redirect_url": f"{origin}/api/github/app/setup/callback",
            "callback_urls": [oauth_redirect_uri],
            "setup_url": f"{origin}/?github=installed",
            "description": "Read-only pull request analysis for AgenticConsensus.",
            "public": True,
            "default_permissions": {
                "metadata": "read",
                "contents": "read",
                "pull_requests": "read",
            },
            "default_events": [],
            "request_oauth_on_install": False,
            "setup_on_update": True,
        }
        return GitHubAppSetup(
            registration_url=f"{self.config.manifest_url}?{urlencode({'state': state})}",
            manifest=manifest,
            expires_at=expires_at,
        )

    def complete_app_setup(self, *, code: str, state: str) -> dict[str, str]:
        if not code or not state:
            raise GitHubAuthorizationError("GitHub App setup response is incomplete")
        record = self.database.consume_github_app_manifest_state(
            hashlib.sha256(state.encode()).hexdigest()
        )
        if record is None:
            raise GitHubAuthorizationError("GitHub App setup state is invalid or expired")
        try:
            response = httpx.post(
                f"{self.config.api_url}/app-manifests/{quote(code, safe='')}/conversions",
                headers={
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": GITHUB_API_VERSION,
                    "User-Agent": "agentic-consensus",
                },
                timeout=self.config.timeout_seconds,
                follow_redirects=False,
            )
        except httpx.HTTPError as exc:
            raise GitHubAuthorizationError("GitHub App setup service is unavailable") from exc
        try:
            payload = response.json()
        except ValueError as exc:
            raise GitHubAuthorizationError(
                "GitHub returned an unreadable App setup response"
            ) from exc
        if response.status_code != 201:
            message = str(payload.get("message") or "request failed")
            raise GitHubAuthorizationError(
                f"GitHub App setup failed ({response.status_code}): {message[:200]}"
            )
        try:
            app_id = int(payload["id"])
            client_id = str(payload["client_id"])
            client_secret = str(payload["client_secret"])
            slug = str(payload["slug"])
            html_url = str(payload["html_url"])
        except (KeyError, TypeError, ValueError) as exc:
            raise GitHubAuthorizationError(
                "GitHub returned incomplete App credentials"
            ) from exc
        permissions = payload.get("permissions")
        if (
            app_id <= 0
            or not client_id
            or not client_secret
            or not re.fullmatch(r"[A-Za-z0-9-]+", slug)
            or not html_url.startswith("https://github.com/apps/")
            or not isinstance(permissions, dict)
            or permissions.get("metadata") != "read"
            or permissions.get("contents") != "read"
            or permissions.get("pull_requests") != "read"
            or any(value == "write" for value in permissions.values())
        ):
            raise GitHubAuthorizationError(
                "GitHub App setup did not preserve the read-only permission contract"
            )
        now = datetime.now(UTC).isoformat()
        saved = self.database.save_github_app_config(
            {
                "app_id": app_id,
                "client_id": client_id,
                "client_secret_ciphertext": self.cipher.encrypt(client_secret),
                "slug": slug,
                "html_url": html_url,
                "created_by_user_id": record["user_id"],
                "created_at": now,
                "updated_at": now,
            }
        )
        if not saved:
            raise GitHubIntegrationError("GitHub is already ready on this instance")
        return self.begin_authorization(
            user_id=record["user_id"], redirect_uri=record["oauth_redirect_uri"]
        )

    def _validate_redirect_uri(self, redirect_uri: str) -> str:
        parsed = urlparse(redirect_uri)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.path != "/api/github/oauth/callback"
        ):
            raise ValueError("GitHub callback URL is not allowed")
        callback_origin = f"{parsed.scheme}://{parsed.netloc}"
        try:
            self._validate_origin(callback_origin)
        except ValueError as exc:
            raise ValueError("GitHub callback URL is not allowed") from exc
        return redirect_uri

    def begin_authorization(self, *, user_id: str, redirect_uri: str) -> dict[str, str]:
        credentials = self._require_credentials()
        redirect_uri = self._validate_redirect_uri(redirect_uri)
        state = secrets.token_urlsafe(40)
        verifier = secrets.token_urlsafe(64)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
        now = datetime.now(UTC)
        self.database.save_github_oauth_state(
            {
                "state_hash": hashlib.sha256(state.encode()).hexdigest(),
                "user_id": user_id,
                "redirect_uri": redirect_uri,
                "code_verifier_ciphertext": self.cipher.encrypt(verifier),
                "created_at": now.isoformat(),
                "expires_at": (now + timedelta(minutes=10)).isoformat(),
            }
        )
        query = urlencode(
            {
                "client_id": credentials.client_id,
                "redirect_uri": redirect_uri,
                "state": state,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            }
        )
        return {
            "authorization_url": f"{self.config.authorize_url}?{query}",
            "expires_at": (now + timedelta(minutes=10)).isoformat(),
        }

    def complete_authorization(self, *, code: str, state: str) -> str:
        credentials = self._require_credentials()
        if not code or not state:
            raise GitHubAuthorizationError("GitHub authorization response is incomplete")
        record = self.database.consume_github_oauth_state(
            hashlib.sha256(state.encode()).hexdigest()
        )
        if record is None:
            raise GitHubAuthorizationError("GitHub authorization state is invalid or expired")
        verifier = self.cipher.decrypt(record["code_verifier_ciphertext"])
        token_payload = self._post_token(
            {
                "client_id": credentials.client_id,
                "client_secret": credentials.client_secret,
                "code": code,
                "redirect_uri": record["redirect_uri"],
                "code_verifier": verifier,
            }
        )
        access_token = token_payload.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise GitHubAuthorizationError("GitHub did not return a user access token")
        user = self._request_json("GET", "/user", access_token=access_token)
        if not isinstance(user, dict) or not user.get("id") or not user.get("login"):
            raise GitHubAuthorizationError("GitHub returned an invalid user identity")
        now = datetime.now(UTC)
        refresh_token = token_payload.get("refresh_token")
        self.database.save_github_connection(
            {
                "user_id": record["user_id"],
                "github_user_id": int(user["id"]),
                "login": str(user["login"]),
                "access_token_ciphertext": self.cipher.encrypt(access_token),
                "refresh_token_ciphertext": (
                    self.cipher.encrypt(refresh_token)
                    if isinstance(refresh_token, str) and refresh_token
                    else None
                ),
                "token_expires_at": (
                    expiry.isoformat()
                    if (expiry := _future_time(token_payload.get("expires_in")))
                    else None
                ),
                "refresh_token_expires_at": (
                    refresh_expiry.isoformat()
                    if (
                        refresh_expiry := _future_time(
                            token_payload.get("refresh_token_expires_in")
                        )
                    )
                    else None
                ),
                "connected_at": now.isoformat(),
                "updated_at": now.isoformat(),
            }
        )
        return record["user_id"]

    def _post_token(self, form: dict[str, object]) -> dict:
        try:
            response = httpx.post(
                self.config.token_url,
                data=form,
                headers={"Accept": "application/json"},
                timeout=self.config.timeout_seconds,
                follow_redirects=False,
            )
        except httpx.HTTPError as exc:
            raise GitHubAuthorizationError("GitHub authorization service is unavailable") from exc
        try:
            payload = response.json()
        except ValueError as exc:
            raise GitHubAuthorizationError("GitHub returned an unreadable authorization response") from exc
        if response.is_error or payload.get("error"):
            description = payload.get("error_description") or payload.get("error") or "request failed"
            raise GitHubAuthorizationError(f"GitHub authorization failed: {str(description)[:200]}")
        return payload

    def _connection(self, user_id: str) -> dict:
        connection = self.database.get_github_connection(user_id)
        if connection is None:
            raise GitHubConnectionRequired("Connect a GitHub account first")
        return connection

    def _access_token(self, user_id: str) -> str:
        connection = self._connection(user_id)
        expires_at = _parse_time(connection.get("token_expires_at"))
        if expires_at is None or expires_at > datetime.now(UTC) + timedelta(seconds=60):
            return self.cipher.decrypt(connection["access_token_ciphertext"])
        refresh_ciphertext = connection.get("refresh_token_ciphertext")
        refresh_expires_at = _parse_time(connection.get("refresh_token_expires_at"))
        if (
            not refresh_ciphertext
            or (refresh_expires_at is not None and refresh_expires_at <= datetime.now(UTC))
        ):
            raise GitHubAuthorizationError("GitHub authorization expired; reconnect the account")
        credentials = self._require_credentials()
        token_payload = self._post_token(
            {
                "client_id": credentials.client_id,
                "client_secret": credentials.client_secret,
                "grant_type": "refresh_token",
                "refresh_token": self.cipher.decrypt(refresh_ciphertext),
            }
        )
        access_token = token_payload.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise GitHubAuthorizationError("GitHub token refresh did not return an access token")
        refresh_token = token_payload.get("refresh_token")
        now = datetime.now(UTC)
        self.database.save_github_connection(
            {
                **connection,
                "access_token_ciphertext": self.cipher.encrypt(access_token),
                "refresh_token_ciphertext": (
                    self.cipher.encrypt(refresh_token)
                    if isinstance(refresh_token, str) and refresh_token
                    else refresh_ciphertext
                ),
                "token_expires_at": (
                    expiry.isoformat()
                    if (expiry := _future_time(token_payload.get("expires_in")))
                    else None
                ),
                "refresh_token_expires_at": (
                    refresh_expiry.isoformat()
                    if (
                        refresh_expiry := _future_time(
                            token_payload.get("refresh_token_expires_in")
                        )
                    )
                    else connection.get("refresh_token_expires_at")
                ),
                "updated_at": now.isoformat(),
            }
        )
        return access_token

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        access_token: str,
        params: dict[str, object] | None = None,
    ) -> dict | list:
        try:
            response = httpx.request(
                method,
                f"{self.config.api_url}{path}",
                params=params,
                headers={
                    "Accept": "application/vnd.github+json",
                    "Authorization": f"Bearer {access_token}",
                    "X-GitHub-Api-Version": GITHUB_API_VERSION,
                    "User-Agent": "agentic-consensus",
                },
                timeout=self.config.timeout_seconds,
                follow_redirects=False,
            )
        except httpx.HTTPError as exc:
            raise GitHubIntegrationError("GitHub API is unavailable") from exc
        if response.status_code == 401:
            raise GitHubAuthorizationError("GitHub authorization is invalid; reconnect the account")
        if response.is_error:
            message = "request failed"
            try:
                message = str(response.json().get("message") or message)
            except (ValueError, AttributeError):
                pass
            raise GitHubIntegrationError(
                f"GitHub API request failed ({response.status_code}): {message[:200]}"
            )
        try:
            return response.json()
        except ValueError as exc:
            raise GitHubIntegrationError("GitHub API returned unreadable data") from exc

    def _paginate(self, user_id: str, path: str, collection_key: str) -> list[dict]:
        token = self._access_token(user_id)
        items: list[dict] = []
        for page in range(1, 101):
            payload = self._request_json(
                "GET", path, access_token=token, params={"per_page": 100, "page": page}
            )
            if not isinstance(payload, dict) or not isinstance(payload.get(collection_key), list):
                raise GitHubIntegrationError("GitHub API returned an invalid collection")
            batch = payload[collection_key]
            items.extend(item for item in batch if isinstance(item, dict))
            total = payload.get("total_count")
            if len(batch) < 100 or (isinstance(total, int) and len(items) >= total):
                return items
        raise GitHubIntegrationError("GitHub repository pagination exceeded the safety limit")

    def list_repositories(self, user_id: str) -> list[GitHubRepository]:
        installations = self._paginate(user_id, "/user/installations", "installations")
        repositories: dict[int, GitHubRepository] = {}
        for installation in installations:
            installation_id = installation.get("id")
            if not isinstance(installation_id, int) or installation_id <= 0:
                continue
            for item in self._paginate(
                user_id,
                f"/user/installations/{installation_id}/repositories",
                "repositories",
            ):
                try:
                    repository = GitHubRepository(
                        id=int(item["id"]),
                        installation_id=installation_id,
                        name=str(item["name"]),
                        full_name=str(item["full_name"]),
                        private=bool(item.get("private", False)),
                        visibility=str(
                            item.get("visibility")
                            or ("private" if item.get("private") else "public")
                        ),
                        description=(
                            str(item["description"]) if item.get("description") else None
                        ),
                        html_url=str(item["html_url"]),
                        clone_url=str(item["clone_url"]),
                        default_branch=str(item.get("default_branch") or "HEAD"),
                        archived=bool(item.get("archived", False)),
                        updated_at=(str(item["updated_at"]) if item.get("updated_at") else None),
                        permissions={
                            str(key): bool(value)
                            for key, value in (item.get("permissions") or {}).items()
                        },
                    )
                except (KeyError, TypeError, ValueError) as exc:
                    raise GitHubIntegrationError("GitHub returned invalid repository metadata") from exc
                repositories[repository.id] = repository
        return sorted(repositories.values(), key=lambda item: item.full_name.casefold())

    @staticmethod
    def _pull_request_from_payload(payload: dict) -> GitHubPullRequest:
        try:
            base = payload["base"]
            head = payload["head"]
            author = payload["user"]
            return GitHubPullRequest(
                number=int(payload["number"]),
                title=str(payload["title"]),
                html_url=str(payload["html_url"]),
                draft=bool(payload.get("draft", False)),
                author=str(author["login"]),
                base_ref=str(base["ref"]),
                base_sha=str(base["sha"]),
                head_ref=str(head["ref"]),
                head_sha=str(head["sha"]),
                updated_at=payload.get("updated_at"),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise GitHubIntegrationError(
                "GitHub returned invalid pull request metadata"
            ) from exc

    @staticmethod
    def _repository_api_path(repository: GitHubRepository) -> str:
        parts = repository.full_name.split("/")
        if len(parts) != 2 or any(not part or part in {".", ".."} for part in parts):
            raise GitHubIntegrationError("GitHub returned an invalid repository name")
        return "/repos/" + "/".join(quote(part, safe="") for part in parts)

    def list_pull_requests(
        self, user_id: str, repository: GitHubRepository
    ) -> list[GitHubPullRequest]:
        try:
            payload = self._request_json(
                "GET",
                f"{self._repository_api_path(repository)}/pulls",
                access_token=self._access_token(user_id),
                params={
                    "state": "open",
                    "sort": "updated",
                    "direction": "desc",
                    "per_page": 50,
                },
            )
        except GitHubIntegrationError as exc:
            if "failed (403)" in str(exc):
                raise GitHubIntegrationError(
                    "Grant this GitHub App read access to pull requests, then manage repository access and retry"
                ) from exc
            raise
        if not isinstance(payload, list):
            raise GitHubIntegrationError("GitHub API returned an invalid pull request list")
        return [
            self._pull_request_from_payload(item)
            for item in payload
            if isinstance(item, dict) and item.get("state") == "open"
        ]

    def get_pull_request(
        self,
        user_id: str,
        repository: GitHubRepository,
        pull_number: int,
    ) -> GitHubPullRequest:
        if pull_number <= 0:
            raise ValueError("pull request number must be positive")
        payload = self._request_json(
            "GET",
            f"{self._repository_api_path(repository)}/pulls/{pull_number}",
            access_token=self._access_token(user_id),
        )
        if not isinstance(payload, dict) or payload.get("state") != "open":
            raise GitHubIntegrationError("GitHub pull request is not open")
        pull_request = self._pull_request_from_payload(payload)
        if pull_request.draft:
            raise GitHubIntegrationError(
                "GitHub pull request is still a draft; mark it ready for review and retry"
            )
        return pull_request

    def has_installations(self, user_id: str) -> bool:
        return bool(self._paginate(user_id, "/user/installations", "installations"))

    def get_repository(
        self, user_id: str, *, installation_id: int, repository_id: int
    ) -> GitHubRepository:
        for repository in self.list_repositories(user_id):
            if (
                repository.id == repository_id
                and repository.installation_id == installation_id
            ):
                if not repository.permissions.get("pull", False):
                    raise GitHubIntegrationError("GitHub repository is not readable")
                return repository
        raise GitHubIntegrationError("GitHub repository is not accessible to this connection")

    def clone_repository(self, user_id: str, repository: GitHubRepository) -> Path:
        existing = self.database.find_project_by_github_repository(repository.id)
        if existing is not None:
            raise GitHubRepositoryAlreadyManaged(
                f"GitHub repository is already managed by project {existing.id}"
            )
        token = self._access_token(user_id)
        safe_name = _SAFE_SLUG.sub("-", repository.full_name).strip("-._")[:100]
        destination = (self.config.repositories_dir / f"github-{repository.id}-{safe_name}").resolve()
        repositories_root = self.config.repositories_dir.resolve()
        if destination.parent != repositories_root:
            raise GitHubIntegrationError("managed repository path escaped its configured root")
        if destination.exists():
            raise GitHubRepositoryAlreadyManaged("GitHub repository checkout already exists")
        self._clone_authenticated(
            clone_url=repository.clone_url,
            default_branch=repository.default_branch,
            destination=destination,
            access_token=token,
        )
        return destination

    def fetch_pull_request(
        self,
        user_id: str,
        repository: GitHubRepository,
        pull_request: GitHubPullRequest,
        checkout: str | Path,
    ) -> tuple[str, str]:
        clone_url = self._validate_clone_url(repository.clone_url)
        checkout_path = Path(checkout).expanduser().resolve()
        local_repository = GitRepository(checkout_path)
        base_branch = GitRepository.validate_ref(pull_request.base_ref)
        pull_ref = f"refs/pull/{pull_request.number}/head"
        base_tip_ref = (
            f"refs/agentic-consensus/github/pr-{pull_request.number}/base-tip"
        )
        head_ref = f"refs/agentic-consensus/github/pr-{pull_request.number}/head"
        temporary_root = Path(tempfile.mkdtemp(prefix=".github-fetch-"))
        askpass = temporary_root / "askpass.sh"
        askpass.write_text(
            "#!/bin/sh\n"
            "case \"$1\" in\n"
            "  *sername*) printf '%s\\n' 'x-access-token' ;;\n"
            "  *assword*) printf '%s\\n' \"$CONSENSUS_GITHUB_ACCESS_TOKEN\" ;;\n"
            "  *) exit 1 ;;\n"
            "esac\n",
            encoding="utf-8",
        )
        os.chmod(askpass, 0o700)
        environment = {
            "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_ASKPASS": str(askpass),
            "CONSENSUS_GITHUB_ACCESS_TOKEN": self._access_token(user_id),
        }
        try:
            subprocess.run(
                [
                    "git",
                    "fetch",
                    "--no-tags",
                    "--force",
                    "--",
                    clone_url,
                    f"+refs/heads/{base_branch}:{base_tip_ref}",
                    f"+{pull_ref}:{head_ref}",
                ],
                cwd=checkout_path,
                check=True,
                capture_output=True,
                text=True,
                timeout=180,
                env=environment,
            )
            resolved_head = local_repository.resolve(head_ref)
            resolved_base_tip = local_repository.resolve(base_tip_ref)
            if resolved_head != pull_request.head_sha:
                raise GitHubIntegrationError(
                    "The pull request changed while it was loading; retry the analysis"
                )
            local_repository.resolve(pull_request.base_sha)
            if resolved_base_tip != pull_request.base_sha:
                raise GitHubIntegrationError(
                    "The pull request base changed while it was loading; retry the analysis"
                )
            return (
                local_repository.merge_base(
                    pull_request.base_sha, pull_request.head_sha
                ),
                resolved_head,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, GitError) as exc:
            stderr = getattr(exc, "stderr", "") or ""
            detail = stderr.strip()[:300]
            raise GitError(
                f"GitHub pull request fetch failed{': ' + detail if detail else ''}"
            ) from exc
        finally:
            shutil.rmtree(temporary_root, ignore_errors=True)

    def _validate_clone_url(self, clone_url: str) -> str:
        parsed = urlparse(clone_url)
        loopback_http = parsed.scheme == "http" and parsed.hostname in {
            "127.0.0.1",
            "localhost",
            "::1",
        }
        if (
            not parsed.hostname
            or parsed.hostname.casefold() != self.config.clone_host
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or (parsed.scheme != "https" and not loopback_http)
        ):
            raise GitHubIntegrationError("GitHub clone URL must be credential-free HTTPS")
        return clone_url

    def _clone_authenticated(
        self,
        *,
        clone_url: str,
        default_branch: str,
        destination: Path,
        access_token: str,
    ) -> None:
        clone_url = self._validate_clone_url(clone_url)
        destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        temporary_root = Path(
            tempfile.mkdtemp(prefix=".github-clone-", dir=destination.parent)
        ).resolve()
        checkout = temporary_root / "repository"
        askpass = temporary_root / "askpass.sh"
        askpass.write_text(
            "#!/bin/sh\n"
            "case \"$1\" in\n"
            "  *sername*) printf '%s\\n' 'x-access-token' ;;\n"
            "  *assword*) printf '%s\\n' \"$CONSENSUS_GITHUB_ACCESS_TOKEN\" ;;\n"
            "  *) exit 1 ;;\n"
            "esac\n",
            encoding="utf-8",
        )
        os.chmod(askpass, 0o700)
        environment = {
            "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_ASKPASS": str(askpass),
            "CONSENSUS_GITHUB_ACCESS_TOKEN": access_token,
        }
        try:
            subprocess.run(
                [
                    "git",
                    "clone",
                    "--origin",
                    "origin",
                    "--no-tags",
                    "--single-branch",
                    "--branch",
                    default_branch,
                    "--",
                    clone_url,
                    str(checkout),
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=180,
                env=environment,
            )
            repository = GitRepository(checkout)
            repository.head()
            os.replace(checkout, destination)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, GitError, OSError) as exc:
            stderr = getattr(exc, "stderr", "") or ""
            detail = stderr.strip()[:300]
            raise GitError(
                f"GitHub repository clone failed{': ' + detail if detail else ''}"
            ) from exc
        finally:
            shutil.rmtree(temporary_root, ignore_errors=True)

    def disconnect(self, user_id: str) -> GitHubDisconnectResult:
        connection = self.database.get_github_connection(user_id)
        if connection is None:
            return GitHubDisconnectResult(
                disconnected=False,
                remote_token_revoked=False,
            )
        access_token = self.cipher.decrypt(connection["access_token_ciphertext"])
        credentials = self._require_credentials()
        remote_token_revoked = False
        try:
            response = httpx.request(
                "DELETE",
                f"{self.config.api_url}/applications/{credentials.client_id}/token",
                auth=(credentials.client_id, credentials.client_secret),
                json={"access_token": access_token},
                headers={
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": GITHUB_API_VERSION,
                    "User-Agent": "agentic-consensus",
                },
                timeout=self.config.timeout_seconds,
                follow_redirects=False,
            )
            remote_token_revoked = response.is_success
        except httpx.HTTPError:
            pass
        finally:
            self.database.delete_github_connection(user_id)
        return GitHubDisconnectResult(
            disconnected=True,
            remote_token_revoked=remote_token_revoked,
        )
