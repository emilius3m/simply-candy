from __future__ import annotations

import requests

APPLIANCES_URL = "https://simply-fi.herokuapp.com/api/v1/appliances.json?with_programs=1"

ANDROID_CIAM_HEADERS = {
    "Salesforce-Auth": "1",
    "Brand": "0",
    "Device-Family": "android",
    "Device-Language": "it",
    "App-Version-Name": "3.14.1",
    "App-Version-Code": "227",
}


class CandyCloudError(RuntimeError):
    """Errore cloud già sanitizzato per la CLI."""


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

    def fetch_appliances(self) -> list[dict[str, object]]:
        try:
            response = self._session.get(APPLIANCES_URL, timeout=self._timeout)
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError):
            raise CandyCloudError(
                "Cloud Candy non raggiungibile o risposta incompatibile."
            ) from None

        if not isinstance(payload, list) or not all(
            isinstance(item, dict) for item in payload
        ):
            raise CandyCloudError("Risposta elenco elettrodomestici incompatibile.")
        return payload
