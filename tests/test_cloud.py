from urllib.parse import parse_qs, urlparse

import pytest
import requests

from candy_cloud import CandyCloudClient, CandyCloudError


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
    def __init__(self, appliance_response=None):
        self.headers = {}
        self.calls = []
        self.appliance_response = appliance_response or FakeResponse([])

    def get(self, url, *, timeout):
        self.calls.append(("GET", url, None, timeout))
        return self.appliance_response


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


def test_fetch_appliances_is_read_only():
    session = FakeSession(appliance_response=FakeResponse([{"appliance": {"id": "1234"}}]))
    client = CandyCloudClient("jwt-secret", session=session)

    assert client.fetch_appliances() == [{"appliance": {"id": "1234"}}]
    method, url, _, _ = session.calls[-1]
    parsed_url = urlparse(url)
    assert (method, parsed_url.scheme, parsed_url.netloc, parsed_url.path) == (
        "GET",
        "https",
        "simply-fi.herokuapp.com",
        "/api/v1/appliances.json",
    )
    assert parse_qs(parsed_url.query) == {"with_programs": ["1"]}
    assert "Write" not in parse_qs(parsed_url.query)


def test_malformed_json_is_rejected_without_response_details():
    session = FakeSession(
        appliance_response=FakeResponse(ValueError("malformed-cloud-body"))
    )
    client = CandyCloudClient("jwt-secret", session=session)

    with pytest.raises(CandyCloudError) as caught:
        client.fetch_appliances()

    assert str(caught.value) == "Cloud Candy non raggiungibile o risposta incompatibile."
    assert "jwt-secret" not in str(caught.value)
    assert "malformed-cloud-body" not in str(caught.value)


@pytest.mark.parametrize(
    "response",
    [
        FakeResponse({"error": "server-auth-detail"}, 401),
        FakeResponse({"error": "forbidden-detail"}, 403),
    ],
)
def test_http_error_is_sanitized(response):
    session = FakeSession(appliance_response=response)
    client = CandyCloudClient("jwt-secret", session=session)

    with pytest.raises(CandyCloudError) as caught:
        client.fetch_appliances()

    assert str(caught.value) == "Cloud Candy non raggiungibile o risposta incompatibile."
    assert "jwt-secret" not in str(caught.value)
    assert "server-auth-detail" not in str(caught.value)
    assert "forbidden-detail" not in str(caught.value)


def test_timeout_is_sanitized():
    class TimeoutSession(FakeSession):
        def get(self, url, *, timeout):
            raise requests.Timeout("timeout-server-detail")

    client = CandyCloudClient("jwt-secret", session=TimeoutSession())

    with pytest.raises(CandyCloudError) as caught:
        client.fetch_appliances()

    assert str(caught.value) == "Cloud Candy non raggiungibile o risposta incompatibile."
    assert "jwt-secret" not in str(caught.value)
    assert "timeout-server-detail" not in str(caught.value)


@pytest.mark.parametrize("payload", [{}, ["not-a-dict"], "server-body-detail"])
def test_invalid_appliance_schema_is_rejected_without_response_details(payload):
    client = CandyCloudClient(
        "jwt-secret", session=FakeSession(appliance_response=FakeResponse(payload))
    )

    with pytest.raises(CandyCloudError) as caught:
        client.fetch_appliances()

    assert str(caught.value) == "Risposta elenco elettrodomestici incompatibile."
    assert "jwt-secret" not in str(caught.value)
    assert "server-body-detail" not in str(caught.value)
