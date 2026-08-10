# Candy CIAM Hybrid Program Import Design

**Date:** 2026-08-01  
**Status:** User-approved written specification  
**Scope:** Replace the rejected legacy Heroku password grant used by
`candy_import_programs.py` with the interactive Salesforce/CIAM hybrid OAuth
flow configured by Candy simply-Fi 3.14.1.

## Problem and corrected evidence

The user's Candy credentials work in the current Android app, while the
deprecated Heroku password grant returns OAuth `invalid_grant`. Decompilation
of the locally available app shows that the primary sign-in route uses the
Salesforce Mobile SDK and that the email/password route is deprecated.

The first CIAM design incorrectly assumed the SDK's default web-server flow.
The complete runtime chain establishes a different contract:

- `SalesforceHelper.initSDK()` explicitly calls
  `setUseWebServerAuthentication(false)`;
- hybrid authentication remains enabled;
- `OAuth2.getAuthorizationUrl(false, true, ...)` selects
  `response_type=hybrid_token` and does not add a PKCE challenge;
- the SDK parses OAuth values directly from the callback fragment;
- `SalesforceHelper.getSalesForceJWT()` subsequently exchanges the callback's
  refresh token with `grant_type=hybrid_refresh` and uses the returned
  `id_token` for Candy's Heroku API.

The authoritative app configuration is:

- login server: `https://account.candy-home.com/CandyApp`;
- authorization path:
  `/services/oauth2/authorize/expid_mobileCandy`;
- token path: `/services/oauth2/token`;
- OAuth client ID: the public `remoteAccessConsumerKey` embedded in the APK;
- redirect URI: `candy://mobilesdk/detect/oauth/done`;
- scopes: `api id openid refresh_token web`;
- display: `touch`;
- Heroku API bearer: the refreshed OpenID `id_token`, with
  `Salesforce-Auth: 1`.

## Chosen interaction

The user approved trying the app-compatible hybrid browser flow with a
manually pasted callback URL.

1. The importer creates a fresh random 16-character lowercase hexadecimal
   device identifier for the current run.
2. It builds the Candy CIAM authorization URL with
   `response_type=hybrid_token`, opens it in the default desktop browser, and
   prints the same authorization URL as a fallback.
3. The user authenticates only on the Candy-hosted page.
4. Candy redirects to `candy://mobilesdk/detect/oauth/done` with OAuth values
   in the URL fragment; the browser can report that the custom protocol is not
   registered.
5. The user copies the complete callback URL and pastes it into a hidden local
   terminal prompt. The callback must never be pasted into chat.
6. The importer validates the callback, keeps only the refresh token needed
   for the next step, performs the hybrid refresh, obtains an OpenID token,
   fetches the appliance catalog, and continues through the existing atomic
   normalization/save pipeline.
7. After the import, the user closes the callback browser tab because its
   address contains temporary bearer credentials.

No Windows protocol registration, Android debugging, traffic interception,
credential extraction, or Candy password collection is required.

## Architecture

### `candy_ciam.py`

A new isolated module owns the public-mobile OAuth protocol. It contains:

- immutable CIAM constants derived from the APK;
- `CiamAuthError`, containing only sanitized user-facing messages;
- an immutable pending-flow value containing the authorization URL and device
  identifier;
- `begin_ciam_login()` to generate the device identifier and build the
  authorization URL;
- `complete_ciam_login()` to validate the pasted callback, submit the hybrid
  refresh, and return only the OpenID JWT needed by the Candy Heroku API.

The authorization request uses the branded path and these exact query values:

- `display=touch`;
- `response_type=hybrid_token`;
- the APK client ID;
- the alphabetically ordered scope string
  `api id openid refresh_token web`;
- the registered redirect URI;
- the per-run device identifier.

The request deliberately has no `code_challenge`, `code_challenge_method`, or
`state`, matching the recovered app contract. A PKCE verifier is neither
generated nor stored because the configured user-agent hybrid flow does not
perform an authorization-code exchange.

`complete_ciam_login()` posts to the CIAM token endpoint with the same device
identifier in the query string. Its form contains only:

- `grant_type=hybrid_refresh`;
- the public client ID;
- the refresh token obtained from the callback;
- `format=json`.

The response must be a JSON object containing a non-empty string `id_token`.
The module returns that string and drops references to parsed callback values
as soon as control leaves the function.

### `candy_cloud.py`

The cloud client stops using the Heroku password grant. It accepts a validated
CIAM `id_token`, installs it as `Authorization: Bearer ...`, adds the existing
Android and `Salesforce-Auth` headers, and exposes the existing read-only
`fetch_appliances()` operation.

The deprecated client ID, client secret, password form, credential-rejection
branch, and password authentication method are removed. No fallback to the
deprecated grant is allowed.

### `candy_import_programs.py`

The importer orchestrates user interaction only:

- starts a CIAM hybrid flow;
- prints the authorization URL and opens it through an injectable browser
  opener;
- explains locally that the complete callback is sensitive and must not be
  shared;
- reads the callback through `getpass.getpass()` so it is not echoed;
- completes the flow and constructs `CandyCloudClient` with the resulting JWT;
- reuses matching, normalization, summary, backup, and atomic persistence
  unchanged.

No email or password is requested, accepted as an argument, read from an
environment variable, or stored.

## Callback validation

The callback is parsed without logging or including it in exceptions. Query
and fragment are inspected separately.

It is accepted only when all of these conditions hold:

- scheme is exactly `candy`;
- authority is exactly `mobilesdk`;
- path is exactly `/detect/oauth/done`;
- no username, password, port, or unexpected fragment syntax is present;
- OAuth values occur in only one of query or fragment, never both;
- no OAuth `error` is present;
- exactly one non-empty `refresh_token` is present;
- security-sensitive parameters are not duplicated.

The duplicate check covers `access_token`, `refresh_token`, `id_token`,
`error`, `error_description`, `instance_url`, and `id`. A normal successful
hybrid response is expected in the fragment. Query parsing remains a strict
fallback because the Salesforce SDK itself falls back to query values when a
fragment is absent.

## Failure behavior and secret handling

Browser cancellation, malformed callback, OAuth denial, network timeout,
token HTTP error, malformed token JSON, missing refresh token, and missing
`id_token` produce stage-specific but sanitized Italian messages.

The following values never appear in standard output, standard error,
exceptions, logs, reports, fixtures, command-line arguments, environment
variables, `programs.json`, or its backup:

- callback URL;
- access token;
- refresh token;
- ID token;
- Salesforce identity URL;
- Candy password.

The authorization URL is safe to print because it contains only public client
configuration and the per-run random device identifier. The callback URL is
not safe to print because the hybrid flow returns bearer credentials in its
fragment.

All authentication failures occur before `save_catalog_atomic()`. Therefore
an existing `programs.json` and backup remain untouched. Import and OAuth make
no local appliance command and cannot start the washer.

## Token lifecycle and accepted tradeoff

All OAuth values live only in memory for one import run. The implementation
does not persist the refresh token or ID token. The user repeats browser
authentication when refreshing the catalog.

Unlike authorization-code PKCE, the app-compatible hybrid flow places bearer
credentials in the callback URL. The user explicitly accepted trying this
route after the difference was explained. The design limits exposure through
a hidden local prompt, sanitized errors, no persistence, no callback echo, and
an instruction to close the callback browser tab after import. It cannot erase
browser history, so this residual risk is disclosed rather than hidden.

## Testing strategy

Tests remain behavior-first and entirely offline.

- Authorization URL: exact scheme, host, branded path, query values, scope
  order, stable per-flow device identifier, and absence of PKCE parameters.
- Callback validation: valid fragment and query fallback plus wrong
  scheme/authority/path, ambiguous query and fragment, missing or duplicate
  refresh token, duplicated sensitive values, and OAuth denial.
- Hybrid refresh: exact token URL and POST form, non-empty `id_token`, timeout,
  HTTP error, malformed JSON, and sanitized failures.
- Cloud client: the supplied JWT appears only in the Authorization header;
  all Android headers and the read-only appliance request remain exact.
- Importer: the opener receives the authorization URL, the callback reader is
  hidden/injectable, no email or password prompt exists, success reaches the
  existing import pipeline, and every auth failure prevents saving.
- Regression: catalog schema, normalization, CLI/web catalog parity, payload
  generation, knob guardrail, and all existing offline tests stay green.

Mocks are limited to browser and external HTTP boundaries. Tests assert
observable URLs, requests, outputs, return codes, and filesystem effects; they
do not inspect source code, ASTs, bytecode, or internal symbol presence.

## Acceptance criteria

1. `candy_import_programs.py` never asks for or receives a Candy password.
2. The browser URL matches the hybrid CIAM contract recovered from the APK.
3. A valid pasted callback produces an in-memory OpenID JWT through one
   `hybrid_refresh` request and then a read-only appliance fetch.
4. The callback and every token remain hidden and are never persisted.
5. Any failure is sanitized and leaves the existing catalog unchanged.
6. The full offline suite passes without any real browser, cloud, or appliance
   access.
7. With the user present, one real browser login imports the BWM 149PH7
   catalog; only a subsequent explicit dry-run is performed, never a real
   start.

## Out of scope

- authorization-code PKCE unless future Candy app evidence enables it;
- Windows `candy://` protocol registration;
- persistent refresh-token storage;
- extracting tokens from Android, ADB, or proxy captures;
- social-login automation or password collection;
- erasing or controlling browser history;
- changing catalog schema, payload mapping, or appliance transport;
- any real washer start.
