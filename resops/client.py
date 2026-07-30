"""
How we talk to Commvault — all the auth/HTTP noise lives here so the read layer
and the ladder stay readable.

Read-only by design: the client only ever reads (get / ensure_fresh_token /
access_token) — no post/put/delete. A platform team can adopt the ladder knowing
it physically cannot mutate their environment. Mutating lanes (the restore drill)
are a separate, opt-in surface — never this client.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import requests

TIMEOUT_SECONDS = 30

# Browser-like UA is REQUIRED — the Metallic WAF 403s the default requests UA.
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) cvlt-resops/1.0"


class AuthError(Exception):
    """Could not obtain or renew a usable access token."""


@dataclass(frozen=True)
class Credentials:
    """Auth material. Today: a Command Center access token from .env.

    Production note: swap load_credentials() for your secret manager or OIDC.
    The rest of the stack only depends on this dataclass, not on where it came from.
    """
    access_token: str
    refresh_token: str


def load_credentials(env_path: Path) -> Credentials:
    """Read tokens from real env vars, falling back to .env."""
    env = _load_env_file(env_path)
    get = lambda key: os.environ.get(key, env.get(key, "")).strip()
    return Credentials(
        access_token=get("CV_ACCESS_TOKEN"),
        refresh_token=get("CV_REFRESH_TOKEN"),
    )


class Client:
    """A read-only, self-renewing Commvault REST client."""

    def __init__(self, host: str, creds: Credentials, env_path: Path) -> None:
        self._host = host.rstrip("/")
        self._creds = creds
        self._env_path = env_path  # where to save a renewed token
        self._session = requests.Session()
        self._session.headers.update({
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
            "Authorization": f"Bearer {creds.access_token}",
        })

    @property
    def access_token(self) -> str:
        """The current bearer token — kept fresh in place by renewals."""
        return self._creds.access_token

    def get(self, path: str) -> requests.Response:
        """GET path. Retries once on a transient network blip, and renews the
        token once on 401."""
        url = f"{self._host}/{path}"
        resp = self._request(url)
        if resp.status_code == 401 and self._creds.refresh_token:
            self._renew()
            resp = self._request(url)
        return resp

    # The probe endpoint must be one that answers 401 on an expired token. It is
    # NOT free choice: this used to call /CommServ, which the Metallic WAF answers
    # with 403 for this tenant *whatever* the token says. 403 isn't 401, so _renew()
    # never fired, writes could never self-renew, and tokens silently aged out until
    # the refresh window closed. /VM is the same endpoint preflight trusts to answer
    # "is this token alive". Don't swap it for a route the WAF might intercept.
    PROBE_PATH = "VM"

    def ensure_fresh_token(self) -> None:
        """Make one benign read so an expired token is renewed (and saved) now.
        Call this before a non-GET request made elsewhere — those won't auto-renew.
        The response is irrelevant; the point is to trip renew-on-401."""
        self.get(self.PROBE_PATH)

    def _request(self, url: str) -> requests.Response:
        """One GET, retried once on a transient network error or gateway error (502/503/504).
        Metallic SaaS WAF returns 503 on cold starts — a single retry is enough."""
        try:
            resp = self._session.get(url, timeout=TIMEOUT_SECONDS)
        except requests.RequestException:
            return self._session.get(url, timeout=TIMEOUT_SECONDS)
        if resp.status_code in (502, 503, 504):
            return self._session.get(url, timeout=TIMEOUT_SECONDS)
        return resp

    def _renew(self) -> None:
        """Trade the refresh token for a fresh access token and persist it.

        Renewal ROTATES the token, so we must save the new one or the next run
        loads a stale token and renewal fails.
        """
        old = self._creds.access_token
        resp = self._session.post(
            f"{self._host}/V4/AccessToken/Renew",
            json={"accessToken": old, "refreshToken": self._creds.refresh_token},
            headers={"Authorization": f"Bearer {old}"},
            timeout=TIMEOUT_SECONDS,
        )
        if resp.status_code != 200:
            raise AuthError(f"Renewal returned HTTP {resp.status_code}: {resp.text[:200]}")
        body = _json_or_empty(resp)
        new_token = body.get("accessToken") or body.get("token")
        if not new_token:
            raise AuthError(f"Renewal returned no token: {resp.text[:200]}")
        new_refresh = body.get("refreshToken") or self._creds.refresh_token
        self._creds = Credentials(new_token, new_refresh)
        self._session.headers["Authorization"] = f"Bearer {new_token}"
        _save_tokens(self._env_path, new_token, new_refresh)


def _json_or_empty(resp: requests.Response) -> dict:
    """Response JSON as a dict, or {} if the body isn't a JSON object."""
    try:
        body = resp.json()
    except ValueError:
        return {}
    return body if isinstance(body, dict) else {}


# --------------------------------------------------------------------------- #
# .env helpers — small, boring, no external dep
# --------------------------------------------------------------------------- #
def _load_env_file(path: Path) -> dict:
    values: dict = {}
    if not path.exists():
        return values
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip("'\"")
    return values


def _save_tokens(path: Path, access_token: str, refresh_token: str) -> None:
    if not path.exists():
        return
    pending = {"CV_ACCESS_TOKEN": access_token, "CV_REFRESH_TOKEN": refresh_token}
    lines = path.read_text().splitlines()
    for i, line in enumerate(lines):
        key = line.split("=", 1)[0].strip()
        if key in pending:
            lines[i] = f"{key}={pending.pop(key)}"
    for key, value in pending.items():
        lines.append(f"{key}={value}")
    try:
        path.write_text("\n".join(lines) + "\n")
    except OSError:
        pass  # in-memory token still works this run
