"""Token renewal — the one property the whole write lane leans on.

`op` calls ensure_fresh_token() before every mutating command, and `write()`
calls it again on a 401 before retrying. Both assume it can actually trip
renew-on-401. It could not: the probe used to be /CommServ, which this tenant's
WAF answers 403 to regardless of the token. 403 is not 401, so the renewal never
fired, writes could not self-renew, and tokens aged out until the refresh window
closed — twice.

This pins the probe to an endpoint that really does 401. The bug was invisible
until credentials died weeks later, which is exactly the kind that needs a test.
"""
from pathlib import Path

from resops.client import Client, Credentials

WAF_BLOCKED = "CommServ"   # 403s on this tenant no matter what the token says


def _client() -> Client:
    # No network: every test below replaces get() before anything is sent.
    return Client("https://example.invalid", Credentials("access", "refresh"),
                  Path("/nonexistent/.env"))


def test_ensure_fresh_token_probes_an_endpoint_that_can_401(monkeypatch):
    client = _client()
    probed = []
    monkeypatch.setattr(client, "get", probed.append)
    client.ensure_fresh_token()
    assert probed == [Client.PROBE_PATH]


def test_the_probe_is_never_the_waf_blocked_route():
    # A 403 route makes ensure_fresh_token a silent no-op. Never go back.
    assert Client.PROBE_PATH != WAF_BLOCKED


def test_renewal_only_triggers_on_401_not_403(monkeypatch):
    """Why the probe choice matters, demonstrated: get() renews on 401 only."""
    client = _client()
    renewals = []
    monkeypatch.setattr(client, "_renew", lambda: renewals.append(True))

    class Response:
        def __init__(self, status_code):
            self.status_code = status_code

    monkeypatch.setattr(client, "_request", lambda url: Response(403))
    client.get("anything")
    assert renewals == [], "403 must not be mistaken for an expired token"

    monkeypatch.setattr(client, "_request", lambda url: Response(401))
    client.get("anything")
    assert renewals == [True], "401 must renew"
