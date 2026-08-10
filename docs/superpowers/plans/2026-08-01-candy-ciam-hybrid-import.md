# Candy CIAM Hybrid Program Import Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Candy's rejected legacy password grant with the app-compatible CIAM `hybrid_token` browser login and import the BWM 149PH7 catalog without storing credentials or starting the washer.

**Architecture:** A new `candy_ciam.py` module owns authorization URL construction, strict callback parsing, and the `hybrid_refresh` exchange. `CandyCloudClient` becomes a read-only client initialized with the resulting in-memory ID token, while `candy_import_programs.py` handles only browser and hidden-prompt interaction before reusing the existing catalog normalization and atomic save pipeline.

**Tech Stack:** Python 3.12, `requests>=2.32,<3`, standard-library `argparse`, `dataclasses`, `getpass`, `secrets`, `urllib.parse`, and `webbrowser`; `pytest>=8.4,<9` with offline fakes at browser and HTTP boundaries.

## Global Constraints

- The authoritative login server is `https://account.candy-home.com/CandyApp`.
- The authorization endpoint is `https://account.candy-home.com/CandyApp/services/oauth2/authorize/expid_mobileCandy`.
- The token endpoint is `https://account.candy-home.com/CandyApp/services/oauth2/token`.
- The public OAuth client ID is `3MVG9QDx8IX8nP5T2Ha8ofvlmjKuido4mcuSVCv4GwStG0Lf84ccYQylvDYy9d_ZLtnyAPzJt4khJoNYn_QVB`.
- The redirect URI is `candy://mobilesdk/detect/oauth/done`.
- The authorization query uses `display=touch`, `response_type=hybrid_token`, scope `api id openid refresh_token web`, and one per-run 16-character lowercase hexadecimal `device_id`.
- The authorization request contains no `state`, `code_challenge`, or `code_challenge_method`.
- The refresh form contains exactly `grant_type=hybrid_refresh`, `client_id`, `refresh_token`, and `format=json`; the same `device_id` is in the token URL query.
- Callback URL, access token, refresh token, ID token, identity URL, and Candy password are never echoed, logged, persisted, placed in exceptions, passed as CLI arguments, or read from environment variables.
- The authorization URL may be printed because it contains public configuration and a random per-run device identifier.
- Every failure before catalog persistence leaves the current `programs.json` and backup unchanged.
- Tests are behavior-first and offline; they do not inspect source, AST, bytecode, or internal symbol presence.
- No test or implementation step sends an appliance command or starts the washer.
- This workspace is not a Git repository. Do not initialize Git and do not fabricate commit identifiers; record test evidence in the SDD ledger instead.
- Baseline before this plan: `112 passed, 1 known Starlette dependency warning`.

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `candy_ciam.py` | Create | Candy CIAM hybrid authorization URL, callback validation, and token refresh |
| `tests/test_ciam.py` | Create | Offline behavioral contract for the CIAM module |
| `candy_cloud.py` | Modify | Read-only Candy appliance API authenticated by an in-memory CIAM ID token |
| `tests/test_cloud.py` | Modify | Token-header and read-only cloud behavior without password-grant tests |
| `candy_import_programs.py` | Modify | Browser orchestration, hidden callback input, error routing, existing import pipeline |
| `tests/test_import.py` | Modify | End-to-end offline importer orchestration and fail-closed persistence |
| `README.md` | Modify | Operator instructions for browser login and sensitive callback handling |

---

### Task 1: Build the hybrid authorization URL and validate callbacks

**Files:**

- Create: `candy_ciam.py`
- Create: `tests/test_ciam.py`

**Interfaces:**

- Consumes: only Python standard-library functions.
- Produces: `CiamAuthError`, immutable `PendingCiamLogin(authorization_url: str, device_id: str)`, `begin_ciam_login(*, token_hex=secrets.token_hex) -> PendingCiamLogin`, and `parse_ciam_callback(callback_url: str) -> str` returning the validated refresh token.

- [ ] **Step 1: Write authorization URL tests**

Create `tests/test_ciam.py` with deterministic device generation and assertions on observable URL behavior:

```python
from urllib.parse import parse_qs, urlsplit

import pytest

from candy_ciam import CiamAuthError, begin_ciam_login


DEVICE_ID = "0123456789abcdef"


def test_begin_login_builds_exact_candy_hybrid_url():
    pending = begin_ciam_login(token_hex=lambda count: DEVICE_ID)
    parsed = urlsplit(pending.authorization_url)

    assert (parsed.scheme, parsed.netloc, parsed.path) == (
        "https",
        "account.candy-home.com",
        "/CandyApp/services/oauth2/authorize/expid_mobileCandy",
    )
    assert parse_qs(parsed.query) == {
        "display": ["touch"],
        "response_type": ["hybrid_token"],
        "client_id": [
            "3MVG9QDx8IX8nP5T2Ha8ofvlmjKuido4mcuSVCv4GwStG0Lf84ccYQylvDYy9d_ZLtnyAPzJt4khJoNYn_QVB"
        ],
        "scope": ["api id openid refresh_token web"],
        "redirect_uri": ["candy://mobilesdk/detect/oauth/done"],
        "device_id": [DEVICE_ID],
    }
    assert pending.device_id == DEVICE_ID
    assert "state" not in parse_qs(parsed.query)
    assert "code_challenge" not in parse_qs(parsed.query)
    assert "code_challenge_method" not in parse_qs(parsed.query)


def test_begin_login_rejects_invalid_device_factory_output():
    with pytest.raises(CiamAuthError, match="inizializzare"):
        begin_ciam_login(token_hex=lambda count: "not-a-device-id")
```

- [ ] **Step 2: Run the URL tests and verify the red state**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_ciam.py -q -o cache_dir=.pytest-ciam-task1-red
```

Expected: collection fails with `ModuleNotFoundError: No module named 'candy_ciam'`.

- [ ] **Step 3: Implement constants, pending flow, and URL construction**

Create `candy_ciam.py` with these public definitions and the exact ordered authorization query:

```python
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import re
import secrets
from urllib.parse import urlencode


LOGIN_SERVER = "https://account.candy-home.com/CandyApp"
AUTHORIZATION_URL = (
    f"{LOGIN_SERVER}/services/oauth2/authorize/expid_mobileCandy"
)
TOKEN_URL = f"{LOGIN_SERVER}/services/oauth2/token"
CLIENT_ID = (
    "3MVG9QDx8IX8nP5T2Ha8ofvlmjKuido4mcuSVCv4GwStG0Lf84ccYQylvDYy9d_"
    "ZLtnyAPzJt4khJoNYn_QVB"
)
REDIRECT_URI = "candy://mobilesdk/detect/oauth/done"
SCOPE = "api id openid refresh_token web"


class CiamAuthError(RuntimeError):
    """Errore CIAM già sanitizzato per la CLI."""


@dataclass(frozen=True)
class PendingCiamLogin:
    authorization_url: str
    device_id: str


def begin_ciam_login(
    *, token_hex: Callable[[int], str] = secrets.token_hex
) -> PendingCiamLogin:
    device_id = token_hex(8)
    if not re.fullmatch(r"[0-9a-f]{16}", device_id):
        raise CiamAuthError("Impossibile inizializzare l'accesso Candy.")
    query = urlencode(
        [
            ("display", "touch"),
            ("response_type", "hybrid_token"),
            ("client_id", CLIENT_ID),
            ("scope", SCOPE),
            ("redirect_uri", REDIRECT_URI),
            ("device_id", device_id),
        ]
    )
    return PendingCiamLogin(f"{AUTHORIZATION_URL}?{query}", device_id)
```

- [ ] **Step 4: Run URL tests and verify the green state**

Run the Task 1 command again.

Expected: both URL tests pass.

- [ ] **Step 5: Add callback-validation tests**

Extend `tests/test_ciam.py` through the public parser boundary:

```python
from candy_ciam import parse_ciam_callback


def test_callback_accepts_fragment_and_strict_query_fallback():
    fragment = "candy://mobilesdk/detect/oauth/done#refresh_token=refresh-fragment"
    query = "candy://mobilesdk/detect/oauth/done?refresh_token=refresh-query"

    assert parse_ciam_callback(fragment) == "refresh-fragment"
    assert parse_ciam_callback(query) == "refresh-query"


@pytest.mark.parametrize(
    "callback",
    [
        "https://mobilesdk/detect/oauth/done#refresh_token=secret",
        "candy://wrong/detect/oauth/done#refresh_token=secret",
        "candy://mobilesdk/wrong#refresh_token=secret",
        "candy://user@mobilesdk/detect/oauth/done#refresh_token=secret",
        "candy://mobilesdk:443/detect/oauth/done#refresh_token=secret",
        "candy://mobilesdk/detect/oauth/done",
        "candy://mobilesdk/detect/oauth/done#refresh_token=",
        "candy://mobilesdk/detect/oauth/done#refresh_token=one&refresh_token=two",
        "candy://mobilesdk/detect/oauth/done?refresh_token=one#access_token=two",
        "candy://mobilesdk/detect/oauth/done#access_token=one&access_token=two&refresh_token=three",
        "candy://mobilesdk/detect/oauth/done#refresh_token",
    ],
)
def test_callback_rejects_malformed_or_ambiguous_values(callback):
    with pytest.raises(CiamAuthError, match="Callback Candy non valida"):
        parse_ciam_callback(callback)


def test_callback_reports_oauth_denial_without_description_or_token():
    callback = (
        "candy://mobilesdk/detect/oauth/done#"
        "error=access_denied&error_description=private-detail"
    )
    with pytest.raises(CiamAuthError) as caught:
        parse_ciam_callback(callback)

    assert str(caught.value) == "Accesso Candy annullato o rifiutato."
    assert "private-detail" not in str(caught.value)
```

- [ ] **Step 6: Run callback tests and verify the red state**

Run the Task 1 command again.

Expected: tests importing `parse_ciam_callback` fail because it does not exist.

- [ ] **Step 7: Implement strict callback parsing**

Add imports `parse_qsl` and `urlsplit`, define the sensitive set, and implement the public callback parser without performing network access.

The parser must follow this exact algorithm:

```python
SENSITIVE_CALLBACK_KEYS = frozenset(
    {
        "access_token",
        "refresh_token",
        "id_token",
        "error",
        "error_description",
        "instance_url",
        "id",
    }
)


def _parse_pairs(value: str) -> list[tuple[str, str]]:
    try:
        return parse_qsl(value, keep_blank_values=True, strict_parsing=True)
    except ValueError:
        raise CiamAuthError("Callback Candy non valida.") from None


def parse_ciam_callback(callback_url: str) -> str:
    try:
        parsed = urlsplit(callback_url.strip())
        if (
            parsed.scheme != "candy"
            or parsed.netloc != "mobilesdk"
            or parsed.path != "/detect/oauth/done"
            or parsed.username is not None
            or parsed.password is not None
            or parsed.port is not None
        ):
            raise ValueError
    except (TypeError, ValueError):
        raise CiamAuthError("Callback Candy non valida.") from None

    query_pairs = _parse_pairs(parsed.query) if parsed.query else []
    fragment_pairs = _parse_pairs(parsed.fragment) if parsed.fragment else []
    all_pairs = query_pairs + fragment_pairs
    for key in SENSITIVE_CALLBACK_KEYS:
        if sum(name == key for name, _ in all_pairs) > 1:
            raise CiamAuthError("Callback Candy non valida.")
    if (
        any(key in SENSITIVE_CALLBACK_KEYS for key, _ in query_pairs)
        and any(key in SENSITIVE_CALLBACK_KEYS for key, _ in fragment_pairs)
    ):
        raise CiamAuthError("Callback Candy non valida.")
    active_pairs = fragment_pairs if fragment_pairs else query_pairs
    if any(key == "error" for key, _ in active_pairs):
        raise CiamAuthError("Accesso Candy annullato o rifiutato.")
    refresh_tokens = [value for key, value in active_pairs if key == "refresh_token"]
    if len(refresh_tokens) != 1 or not refresh_tokens[0]:
        raise CiamAuthError("Callback Candy non valida.")
    return refresh_tokens[0]
```

- [ ] **Step 8: Run Task 1 tests and record evidence**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_ciam.py -q -o cache_dir=.pytest-ciam-task1-green
```

Expected: all Task 1 tests pass without network access.

Record the command and result in this plan's SDD ledger.

---

### Task 2: Perform the sanitized `hybrid_refresh` exchange

**Files:**

- Modify: `candy_ciam.py`
- Modify: `tests/test_ciam.py`

**Interfaces:**

- Consumes: `PendingCiamLogin`, `parse_ciam_callback()`, `TOKEN_URL`, and `CLIENT_ID` from Task 1.
- Produces: `complete_ciam_login(pending: PendingCiamLogin, callback_url: str, *, session: requests.Session | None = None, timeout: tuple[float, float] = (5.0, 20.0)) -> str`.

- [ ] **Step 1: Add exact refresh-contract tests**

Extend `tests/test_ciam.py`:

```python
import requests

from urllib.parse import parse_qs, urlsplit


class FakeResponse:
    def __init__(self, payload, status=200):
        self.payload = payload
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(response=self)

    def json(self):
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


class FakeSession:
    def __init__(self, response=None):
        self.response = response or FakeResponse({"id_token": "jwt-value"})
        self.calls = []

    def post(self, url, *, data, timeout):
        self.calls.append((url, data, timeout))
        return self.response


def pending():
    return begin_ciam_login(token_hex=lambda count: DEVICE_ID)


def test_complete_login_posts_exact_hybrid_refresh_contract():
    session = FakeSession(FakeResponse({"id_token": "jwt-value"}))
    callback = (
        "candy://mobilesdk/detect/oauth/done#"
        "access_token=unused-access&refresh_token=refresh-secret&"
        "instance_url=https%3A%2F%2Fexample.invalid"
    )

    assert complete_ciam_login(pending(), callback, session=session) == "jwt-value"
    url, form, timeout = session.calls[0]
    parsed = urlsplit(url)
    assert (parsed.scheme, parsed.netloc, parsed.path) == (
        "https",
        "account.candy-home.com",
        "/CandyApp/services/oauth2/token",
    )
    assert parse_qs(parsed.query) == {"device_id": [DEVICE_ID]}
    assert form == {
        "grant_type": "hybrid_refresh",
        "client_id": (
            "3MVG9QDx8IX8nP5T2Ha8ofvlmjKuido4mcuSVCv4GwStG0Lf84ccYQylvDYy9d_"
            "ZLtnyAPzJt4khJoNYn_QVB"
        ),
        "refresh_token": "refresh-secret",
        "format": "json",
    }
    assert timeout == (5.0, 20.0)
```

- [ ] **Step 2: Add failure and sanitization tests**

Add this table-driven coverage:

```python
@pytest.mark.parametrize(
    ("response", "forbidden"),
    [
        (FakeResponse({"error": "invalid_grant", "token": "server-secret"}, 400),
         ("invalid_grant", "server-secret", "refresh-secret")),
        (FakeResponse(ValueError("malformed-private-body")),
         ("malformed-private-body", "refresh-secret")),
        (FakeResponse({}), ("refresh-secret",)),
        (FakeResponse({"id_token": ""}), ("refresh-secret",)),
        (FakeResponse(["jwt-list-value"]), ("jwt-list-value", "refresh-secret")),
    ],
)
def test_refresh_failures_are_sanitized(response, forbidden):
    callback = "candy://mobilesdk/detect/oauth/done#refresh_token=refresh-secret"
    with pytest.raises(CiamAuthError) as caught:
        complete_ciam_login(pending(), callback, session=FakeSession(response))

    assert str(caught.value) == "Impossibile ottenere il token Candy."
    for value in forbidden:
        assert value not in str(caught.value)


def test_refresh_timeout_is_sanitized():
    class TimeoutSession(FakeSession):
        def post(self, url, *, data, timeout):
            raise requests.Timeout("refresh-secret network-detail")

    callback = "candy://mobilesdk/detect/oauth/done#refresh_token=refresh-secret"
    with pytest.raises(CiamAuthError) as caught:
        complete_ciam_login(pending(), callback, session=TimeoutSession())

    assert str(caught.value) == "Impossibile ottenere il token Candy."
    assert "refresh-secret" not in str(caught.value)
    assert "network-detail" not in str(caught.value)
```

- [ ] **Step 3: Implement the exact refresh exchange**

Use `requests`, `urlencode`, fixed exceptions, and no response-body interpolation:

```python
def complete_ciam_login(
    pending: PendingCiamLogin,
    callback_url: str,
    *,
    session: requests.Session | None = None,
    timeout: tuple[float, float] = (5.0, 20.0),
) -> str:
    refresh_token = parse_ciam_callback(callback_url)
    client = session or requests.Session()
    token_url = f"{TOKEN_URL}?{urlencode({'device_id': pending.device_id})}"
    form = {
        "grant_type": "hybrid_refresh",
        "client_id": CLIENT_ID,
        "refresh_token": refresh_token,
        "format": "json",
    }
    try:
        response = client.post(token_url, data=form, timeout=timeout)
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError):
        raise CiamAuthError("Impossibile ottenere il token Candy.") from None
    id_token = payload.get("id_token") if isinstance(payload, dict) else None
    if not isinstance(id_token, str) or not id_token.strip():
        raise CiamAuthError("Impossibile ottenere il token Candy.")
    return id_token
```

- [ ] **Step 4: Run the entire CIAM test module**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_ciam.py -q -o cache_dir=.pytest-ciam-task2
```

Expected: all tests pass and `FakeSession.calls` proves there is exactly one HTTP POST per successful completion.

Record the command and result in the SDD ledger.

---

### Task 3: Convert the Candy cloud client to ID-token authentication

**Files:**

- Modify: `candy_cloud.py`
- Modify: `tests/test_cloud.py`

**Interfaces:**

- Consumes: non-empty CIAM `id_token: str` returned by Task 2.
- Produces: `CandyCloudClient(id_token: str, session: requests.Session | None = None, timeout: tuple[float, float] = (5.0, 20.0))` and unchanged `fetch_appliances() -> list[dict[str, object]]`.

- [ ] **Step 1: Replace password-grant tests with token-constructor tests**

Change `FakeSession` in `tests/test_cloud.py` so it needs only `headers`, `calls`, `appliance_response`, and `get()`. Remove its token `post()` path and add:

```python
def test_id_token_installs_android_cloud_headers():
    session = FakeSession()
    CandyCloudClient("jwt-secret", session=session)

    assert session.headers == {
        "Authorization": "Bearer jwt-secret",
        "Salesforce-Auth": "1",
        "Brand": "0",
        "Device-Family": "android",
        "Device-Language": "it",
        "App-Version-Name": "3.14.1",
        "App-Version-Code": "227",
    }
    assert session.calls == []


@pytest.mark.parametrize("token", ["", "   "])
def test_empty_id_token_is_rejected_without_http(token):
    session = FakeSession()
    with pytest.raises(CandyCloudError, match="Token Candy non valido"):
        CandyCloudClient(token, session=session)
    assert session.calls == []
```

Update `test_fetch_appliances_is_read_only`, malformed JSON, and timeout cases to instantiate `CandyCloudClient("jwt-secret", session=session)` directly. For each caught error, assert `jwt-secret` is absent.

- [ ] **Step 2: Run cloud tests and verify the red state**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_cloud.py -q -o cache_dir=.pytest-ciam-task3-red
```

Expected: failures show that the old constructor does not accept an ID token and password-grant tests no longer match production behavior.

- [ ] **Step 3: Implement token-only construction**

Modify `candy_cloud.py` so its cloud constants retain only the appliance endpoint and Android headers. Replace the constructor and remove the password grant path:

```python
class CandyCloudClient:
    def __init__(
        self,
        id_token: str,
        session: requests.Session | None = None,
        timeout: tuple[float, float] = (5.0, 20.0),
    ):
        if not isinstance(id_token, str) or not id_token.strip():
            raise CandyCloudError("Token Candy non valido.")
        self._session = session or requests.Session()
        self._timeout = timeout
        self._session.headers.update(ANDROID_CIAM_HEADERS)
        self._session.headers["Authorization"] = f"Bearer {id_token}"
```

Keep `fetch_appliances()` read-only and sanitized. Remove the `_authenticated` guard because a client cannot now be constructed without a valid token. Do not retain a password fallback.

- [ ] **Step 4: Run cloud and catalog tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_cloud.py tests\test_programs.py -q -o cache_dir=.pytest-ciam-task3
```

Expected: all selected tests pass; no POST call occurs in `CandyCloudClient`.

Record the command and result in the SDD ledger.

---

### Task 4: Orchestrate browser login and hidden callback input in the importer

**Files:**

- Modify: `candy_import_programs.py`
- Modify: `tests/test_import.py`

**Interfaces:**

- Consumes: `begin_ciam_login()`, `complete_ciam_login()`, `CiamAuthError`, and `CandyCloudClient(id_token)` from Tasks 1-3.
- Produces: `main(argv: Sequence[str] | None = None, *, browser_open=webbrowser.open, callback_reader=getpass.getpass) -> int`; existing catalog helpers remain unchanged.

- [ ] **Step 1: Replace the importer success test with hybrid orchestration**

In `tests/test_import.py`, replace the password-oriented main test with:

```python
from types import SimpleNamespace

from candy_ciam import CiamAuthError


def test_main_opens_browser_reads_hidden_callback_fetches_then_saves(
    monkeypatch, tmp_path, capsys
):
    events = []
    output = tmp_path / "programs.json"
    pending = SimpleNamespace(
        authorization_url="https://account.candy-home.com/safe-authorize",
        device_id="0123456789abcdef",
    )

    monkeypatch.setattr(importer, "begin_ciam_login", lambda: pending)

    def complete(received_pending, callback):
        events.append(("complete", received_pending, callback))
        return "jwt-secret"

    monkeypatch.setattr(importer, "complete_ciam_login", complete)

    class FakeClient:
        def __init__(self, id_token):
            events.append(("client", id_token))

        def fetch_appliances(self):
            events.append(("fetch",))
            return fixture_records()

    monkeypatch.setattr(importer, "CandyCloudClient", FakeClient)
    monkeypatch.setattr(
        importer,
        "save_catalog_atomic",
        lambda catalog, path: events.append(("save", Path(path), len(catalog.programs))),
    )

    assert importer.main(
        ["--output", str(output)],
        browser_open=lambda url: events.append(("open", url)) or True,
        callback_reader=lambda prompt: events.append(("prompt", prompt))
        or "candy://mobilesdk/detect/oauth/done#refresh_token=callback-secret",
    ) == 0

    assert events[0] == ("open", pending.authorization_url)
    assert events[1][0] == "prompt"
    assert events[2][0] == "complete"
    assert events[3:] == [
        ("client", "jwt-secret"),
        ("fetch",),
        ("save", output, 1),
    ]
    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert pending.authorization_url in captured.out
    assert "callback-secret" not in combined
    assert "jwt-secret" not in combined
    assert "Email Candy" not in combined
    assert "Password Candy" not in combined
```

- [ ] **Step 2: Add browser fallback, cancellation, and no-save tests**

Add behavior coverage:

```python
def test_browser_open_failure_keeps_printed_url_and_allows_manual_flow(
    monkeypatch, tmp_path, capsys
):
    pending = SimpleNamespace(
        authorization_url="https://account.candy-home.com/safe-authorize",
        device_id="0123456789abcdef",
    )
    monkeypatch.setattr(importer, "begin_ciam_login", lambda: pending)
    monkeypatch.setattr(importer, "complete_ciam_login", lambda pending, callback: "jwt")

    class FakeClient:
        def __init__(self, id_token):
            pass

        def fetch_appliances(self):
            return fixture_records()

    monkeypatch.setattr(importer, "CandyCloudClient", FakeClient)
    monkeypatch.setattr(importer, "save_catalog_atomic", lambda catalog, path: None)

    def broken_browser(url):
        raise OSError("browser-private-detail")

    assert importer.main(
        ["--output", str(tmp_path / "programs.json")],
        browser_open=broken_browser,
        callback_reader=lambda prompt: (
            "candy://mobilesdk/detect/oauth/done#refresh_token=secret"
        ),
    ) == 0
    combined = capsys.readouterr()
    assert pending.authorization_url in combined.out
    assert "browser-private-detail" not in combined.out + combined.err


@pytest.mark.parametrize("reader_error", [EOFError(), KeyboardInterrupt()])
def test_callback_cancellation_never_saves(monkeypatch, tmp_path, reader_error):
    pending = SimpleNamespace(
        authorization_url="https://account.candy-home.com/safe-authorize",
        device_id="0123456789abcdef",
    )
    monkeypatch.setattr(importer, "begin_ciam_login", lambda: pending)
    monkeypatch.setattr(
        importer,
        "save_catalog_atomic",
        lambda catalog, path: pytest.fail("non deve salvare"),
    )

    def cancel(prompt):
        raise reader_error

    assert importer.main(
        ["--output", str(tmp_path / "programs.json")],
        browser_open=lambda url: True,
        callback_reader=cancel,
    ) == 3


def test_ciam_failure_preserves_existing_catalog(monkeypatch, tmp_path):
    output = tmp_path / "programs.json"
    output.write_text("existing-catalog", encoding="utf-8")
    pending = SimpleNamespace(
        authorization_url="https://account.candy-home.com/safe-authorize",
        device_id="0123456789abcdef",
    )
    monkeypatch.setattr(importer, "begin_ciam_login", lambda: pending)
    monkeypatch.setattr(
        importer,
        "complete_ciam_login",
        lambda pending, callback: (_ for _ in ()).throw(
            CiamAuthError("Callback Candy non valida.")
        ),
    )
    monkeypatch.setattr(
        importer,
        "save_catalog_atomic",
        lambda catalog, path: pytest.fail("non deve salvare"),
    )

    assert importer.main(
        ["--output", str(output)],
        browser_open=lambda url: True,
        callback_reader=lambda prompt: "private-callback",
    ) == 3
    assert output.read_text(encoding="utf-8") == "existing-catalog"
```

Retain the existing schema-error test, but make its fake client accept `id_token` in `__init__` and feed the importer through mocked CIAM functions.

- [ ] **Step 3: Run importer tests and verify the red state**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_import.py -q -o cache_dir=.pytest-ciam-task4-red
```

Expected: main does not yet accept injected browser/callback callables and still prompts for email/password.

- [ ] **Step 4: Implement hybrid browser orchestration**

Add imports for `webbrowser` and the CIAM API. Change `main()` to this ordering before the existing appliance matching block:

```python
def main(
    argv: Sequence[str] | None = None,
    *,
    browser_open=webbrowser.open,
    callback_reader=getpass.getpass,
) -> int:
    args = build_parser().parse_args(argv)
    try:
        pending = begin_ciam_login()
        print("Apri questa pagina per accedere a Candy:")
        print(pending.authorization_url)
        try:
            opened = bool(browser_open(pending.authorization_url))
        except Exception:
            opened = False
        if not opened:
            print("Il browser non si è aperto: usa il collegamento mostrato sopra.")
        print(
            "Dopo l'accesso copia l'intero indirizzo candy://. "
            "È sensibile: non condividerlo e chiudi la scheda al termine."
        )
        try:
            callback_url = callback_reader("Callback Candy (input nascosto): ")
        except (EOFError, KeyboardInterrupt):
            raise CiamAuthError("Accesso Candy annullato.") from None
        id_token = complete_ciam_login(pending, callback_url)
        client = CandyCloudClient(id_token)
        records = client.fetch_appliances()
```

Keep the existing matching, normalization, summary, and save block exactly after `records`. Catch `(CiamAuthError, CandyCloudError)` together, print only the sanitized exception, and return `3`. Remove `email`, `password`, and the password-clearing `finally` block.

- [ ] **Step 5: Run importer and cloud integration tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_import.py tests\test_ciam.py tests\test_cloud.py -q -o cache_dir=.pytest-ciam-task4
```

Expected: all selected tests pass, with no real browser, cloud, or filesystem overwrite outside `tmp_path`.

Record the command and result in the SDD ledger.

---

### Task 5: Document the operator flow and verify the whole project

**Files:**

- Modify: `README.md`
- Verify: all Python modules and tests

**Interfaces:**

- Consumes: completed browser flow and existing CLI commands.
- Produces: user-facing instructions matching the implemented behavior and complete offline verification evidence.

- [ ] **Step 1: Update README authentication instructions**

Replace the password-session paragraph with:

```markdown
L'importazione apre nel browser la pagina ufficiale Candy. Accedi soltanto in
quella pagina; lo script non chiede email o password. Al termine il browser
prova ad aprire un indirizzo `candy://`: copia l'indirizzo completo e incollalo
nel prompt nascosto del terminale. Non incollarlo in chat, email o file perché
contiene credenziali temporanee. Dopo l'importazione chiudi la scheda del
callback.

Token e callback restano solo in memoria e non vengono salvati. Se Candy
aggiorna il catalogo, ripeti l'accesso dal browser per rigenerare
`programs.json`.
```

Keep the existing dry-run warning and explicitly state that import and dry-run do not start the washer.

- [ ] **Step 2: Run syntax compilation**

Run:

```powershell
.\.venv\Scripts\python.exe -m py_compile candy_ciam.py candy_cloud.py candy_import_programs.py candy_programs.py candy_sendprogram.py candy_web.py
```

Expected: exit code `0` and no output.

- [ ] **Step 3: Run the full offline suite**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q -o cache_dir=.pytest-ciam-final
```

Expected: all tests pass; the only accepted warning is the existing Starlette deprecation warning from `fastapi.testclient`.

- [ ] **Step 4: Scan tracked project text for obsolete password instructions and leaked test secrets**

Run:

```powershell
rg -n "Email Candy|Password Candy|grant_type.?password|ANDROID_CLIENT_SECRET|one-use-password" candy_*.py README.md tests docs\superpowers\specs\2026-08-01-candy-ciam-hybrid-import-design.md
```

Expected: matches may exist only in negative behavioral assertions that prove email/password prompts are absent. There must be no production password prompt, legacy password form, or client secret.

Run:

```powershell
rg -n "refresh-secret|jwt-secret|callback-secret" programs.json README.md candy_*.py
```

Expected: no matches in production modules, README, or catalog output.

- [ ] **Step 5: Record final offline evidence**

Append the syntax command, full-suite result, scan results, known warning, and statement `No browser, cloud, or appliance command executed during tests` to this plan's SDD ledger.

The supervised real browser import is a post-implementation acceptance step with the user present. Run only:

```powershell
.\.venv\Scripts\python.exe candy_import_programs.py
.\.venv\Scripts\python.exe candy_sendprogram.py list
.\.venv\Scripts\python.exe candy_sendprogram.py start --program <nome-importato> --dry-run
```

Never remove `--dry-run` during acceptance.
