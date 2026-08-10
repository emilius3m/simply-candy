from urllib.parse import parse_qs, urlsplit

import pytest
import requests

from candy_ciam import (
    CiamAuthError,
    begin_ciam_login,
    complete_ciam_login,
    parse_ciam_callback,
)


DEVICE_ID = "0123456789abcdef"


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


def test_complete_login_posts_exact_hybrid_refresh_contract():
    session = FakeSession(FakeResponse({"id_token": "jwt-value"}))
    callback = (
        "candy://mobilesdk/detect/oauth/done#"
        "access_token=unused-access&refresh_token=refresh-secret&"
        "instance_url=https%3A%2F%2Fexample.invalid"
    )

    assert complete_ciam_login(pending(), callback, session=session) == "jwt-value"
    assert len(session.calls) == 1
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
