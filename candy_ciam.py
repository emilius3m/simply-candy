from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import re
import secrets
from urllib.parse import parse_qsl, urlencode, urlsplit

import requests


LOGIN_SERVER = "https://account.candy-home.com/CandyApp"
AUTHORIZATION_URL = f"{LOGIN_SERVER}/services/oauth2/authorize/expid_mobileCandy"
TOKEN_URL = f"{LOGIN_SERVER}/services/oauth2/token"
CLIENT_ID = (
    "3MVG9QDx8IX8nP5T2Ha8ofvlmjKuido4mcuSVCv4GwStG0Lf84ccYQylvDYy9d_"
    "ZLtnyAPzJt4khJoNYn_QVB"
)
REDIRECT_URI = "candy://mobilesdk/detect/oauth/done"
SCOPE = "api id openid refresh_token web"
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
