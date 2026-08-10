# Candy CIAM/PKCE Program Import Design

**Date:** 2026-08-01  
**Status:** Superseded after runtime-flow verification  
**Superseded by:** `2026-08-01-candy-ciam-hybrid-import-design.md`  
**Scope:** Replace the rejected legacy Heroku password grant used by
`candy_import_programs.py` with the interactive Salesforce/CIAM OAuth flow used
by Candy simply-Fi 3.14.1.

## Problem and evidence

The user's credentials work in the current Android app but
`https://simply-fi.herokuapp.com/oauth/token` returns OAuth
`invalid_grant`. Decompilation of the locally available official app package
shows two distinct login routes:

- the primary `bt_sf_sign_in` route launches the Salesforce SDK flow through
  `OOTB_01_PostLoginActivity`;
- the old email/password UI calls `ConnectionManager.requestToken()` and is
  explicitly treated as deprecated by the app.

The importer implemented the deprecated password route. Adding the Android
headers did not change the server rejection, confirming that the wrong grant,
not the user's password, is the remaining boundary failure.

The APK also supplies the authoritative CIAM configuration:

- login server: `https://account.candy-home.com/CandyApp`;
- authorization path:
  `/services/oauth2/authorize/expid_mobileCandy`;
- token path: `/services/oauth2/token`;
- OAuth client ID: the public `remoteAccessConsumerKey` embedded in the APK;
- redirect URI: `candy://mobilesdk/detect/oauth/done`;
- scopes: `api web id openid refresh_token`;
- display: `touch`;
- PKCE: authorization code with a random verifier and an unpadded base64url
  SHA-256 challenge;
- Heroku API bearer: the Salesforce OpenID `id_token`, with
  `Salesforce-Auth: 1`.

## Chosen interaction

The user selected browser OAuth with a manually pasted redirect URL.

1. The importer creates a fresh PKCE verifier/challenge and device ID.
2. It opens the Candy CIAM authorization URL in the default desktop browser
   and also prints a safe clickable URL if automatic opening fails.
3. The user authenticates only on the Candy-hosted page.
4. The browser attempts to navigate to the registered `candy://` callback.
5. The user copies the complete callback URL from the browser and pastes it
   into a hidden terminal prompt.
6. The importer validates and exchanges the code, obtains an OpenID token,
   fetches the appliance catalog, and continues through the existing atomic
   normalization/save pipeline.

No Windows protocol registration, Android debugging, traffic interception, or
credential extraction is required.

## Architecture

### `candy_ciam.py`

A new isolated module owns the public-mobile OAuth protocol. It contains:

- immutable CIAM constants derived from the APK;
- `CiamAuthError`, containing only sanitized user-facing messages;
- a pending-flow value containing authorization URL, verifier, and device ID;
- `begin_ciam_login()` to generate PKCE material and build the authorization
  URL;
- `complete_ciam_login()` to validate the pasted callback, exchange the code,
  and return only the OpenID JWT needed by the Candy Heroku API.

The authorization request uses `response_type=code`, the APK client ID,
redirect URI, scopes, display mode, device ID, and code challenge. It does not
invent a `state` parameter absent from the recovered APK contract; the
per-flow PKCE verifier binds the callback code to this importer process, and
exact callback validation remains mandatory.

The code exchange posts `grant_type=authorization_code`, client ID, code,
verifier, redirect URI, and `format=json` to the CIAM token endpoint with the
same device ID. To mirror `SalesforceHelper.getSalesForceJWT()`, the module
then uses the returned refresh token in a second in-memory refresh grant and
must obtain a non-empty `id_token`. Neither token response is logged.

### `candy_cloud.py`

The cloud client stops using the Heroku password grant for program import. It
accepts a validated CIAM `id_token`, installs it as `Authorization: Bearer ...`,
adds the existing Android/`Salesforce-Auth` headers, and then exposes the same
read-only `fetch_appliances()` operation.

Legacy password-grant code that has no remaining production caller is removed
or made unreachable from the importer, together with password-specific CLI
behavior. No fallback to the deprecated grant is allowed.

### `candy_import_programs.py`

The importer orchestrates user interaction only:

- starts a CIAM flow;
- opens the browser through an injectable opener;
- reads the callback URL through `getpass.getpass()` so the authorization code
  is not echoed;
- completes the flow and passes the resulting JWT to `CandyCloudClient`;
- reuses matching, normalization, summary, backup, and atomic persistence
  unchanged.

No password is requested, accepted as an argument, read from an environment
variable, or stored.

## Validation and failure behavior

The callback is accepted only when all of these hold:

- scheme is exactly `candy`;
- authority/path equal `mobilesdk/detect/oauth/done`;
- exactly one non-empty authorization `code` is present;
- no OAuth `error` is present;
- duplicate security-sensitive query parameters are rejected.

Network timeout, browser cancellation, malformed callback, OAuth denial,
token HTTP error, malformed token JSON, missing refresh token, and missing
`id_token` produce stage-specific but sanitized messages. Authorization codes,
verifiers, access tokens, refresh tokens, JWTs, response bodies, and passwords
never appear in output or exceptions.

All failures occur before `save_catalog_atomic()`. Therefore an existing
`programs.json` and backup remain untouched. Import and OAuth perform no local
appliance command and cannot start the washer.

## Token lifecycle

All OAuth values live only in memory for one import run. The implementation
does not persist access, refresh, or ID tokens and does not add them to CLI
arguments, environment variables, logs, reports, fixtures, or `programs.json`.
The user repeats browser authentication when refreshing the catalog. This is
deliberately less convenient than token persistence and materially reduces the
credential exposure surface.

## Testing strategy

Tests remain behavior-first and entirely offline.

- URL construction: hand-derived exact query values, PKCE challenge, scopes,
  branded path, redirect URI, and stable per-flow device ID.
- Callback validation: valid callback plus wrong scheme/path, missing or
  duplicate code, and OAuth error.
- Token exchange: exact POST contract; authorization-code exchange followed by
  refresh-to-`id_token` when required; malformed and HTTP-error responses are
  sanitized.
- Importer: browser opener receives the authorization URL; callback prompt is
  hidden; no password prompt exists; successful flow reaches the existing
  importer; every auth failure prevents saving.
- Cloud client: CIAM JWT is present only in the Authorization header, never in
  errors or persisted output.
- Regression: catalog schema, normalization, CLI/web catalog parity, payload
  generation, knob guardrail, and all existing offline tests stay green.

Mocks are limited to browser and external HTTP boundaries. Tests assert
observable URLs, requests, outputs, return codes, and filesystem effects; they
do not inspect source, ASTs, or internal symbol presence.

## Acceptance criteria

1. `candy_import_programs.py` never asks for or receives a Candy password.
2. The browser URL matches the CIAM/PKCE contract recovered from the APK.
3. A valid pasted callback produces an in-memory OpenID JWT and a read-only
   appliance fetch.
4. Any failure is sanitized and leaves the existing catalog unchanged.
5. No token or authorization code is persisted or echoed.
6. The full offline suite passes without any real browser, cloud, or appliance
   access.
7. With the user present, one real browser login imports the BWM 149PH7 catalog;
   only a subsequent explicit dry-run is performed, never a real start.

## Out of scope

- Windows `candy://` protocol registration;
- persistent refresh-token storage;
- extracting tokens from Android, ADB, or proxy captures;
- social-login automation or password collection;
- changing catalog schema, payload mapping, or appliance transport;
- any real washer start.
