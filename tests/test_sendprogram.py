import json
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
import requests

import candy_sendprogram
from candy_programs import CatalogError, OverrideError, parse_catalog
from candy_sendprogram import xor_decode, xor_encode


FIXTURE = Path(__file__).parent / "fixtures" / "programs_valid.json"
DEFAULT_START_PAYLOAD = (
    "Write=1&StSt=1&DelVl=0&PrNm=1&PrCode=7"
    "&PrStr=DUAL_WM_WD_PROGRAM_NAME_COTONE&TmpTgt=40&SLevTgt=2"
    "&SpdTgt=10&OptMsk1=0&OptMsk2=0&Lang=1&Stm=0&Dry=0&ED=0"
    "&RecipeId=0&StartCheckUp=0&DispTestOn=1"
)


def build_start_payload(*args, **kwargs):
    return candy_sendprogram.build_start_payload(*args, **kwargs)


def start_named_program(*args, **kwargs):
    return candy_sendprogram.start_named_program(*args, **kwargs)


@pytest.fixture
def program():
    return parse_catalog(json.loads(FIXTURE.read_text(encoding="utf-8"))).programs[0]


class ErrorResponse:
    status_code = 500

    def __init__(self, text):
        self._text = text

    def raise_for_status(self):
        raise requests.HTTPError("device returned 500", response=self)

    @property
    def text(self):
        return self._text


def test_xor_round_trip_preserves_payload():
    key = "".join(chr(value) for value in range(16))
    payload = "Write=1&StSt=0&PrNm=1"
    assert xor_decode(xor_encode(payload, key), key) == payload


def test_default_start_payload_uses_imported_selector(program):
    assert build_start_payload(program) == DEFAULT_START_PAYLOAD


def test_temperature_override_adds_target_and_cloud_default(program):
    assert build_start_payload(program, temp=30) == (
        "Write=1&StSt=1&DelVl=0&PrNm=1&PrCode=7"
        "&PrStr=DUAL_WM_WD_PROGRAM_NAME_COTONE&TmpTgt=30&SLevTgt=2"
        "&SpdTgt=10&OptMsk1=0&OptMsk2=0&Lang=1&Stm=0&Dry=0&ED=0"
        "&RecipeId=0&StartCheckUp=0&DispTestOn=1"
    )


def test_shared_selector_programs_keep_distinct_default_parameters(program):
    rapid_30 = replace(program, defaults=replace(program.defaults, soil=2))
    rapid_14 = replace(program, defaults=replace(program.defaults, soil=1))

    payload_30 = build_start_payload(rapid_30)
    payload_14 = build_start_payload(rapid_14)

    assert "&PrNm=1&" in payload_30 and "&PrNm=1&" in payload_14
    assert "&SLevTgt=2&" in payload_30
    assert "&SLevTgt=1&" in payload_14
    assert payload_30 != payload_14


def test_spin_override_converts_rpm_to_protocol_units(program):
    assert "&SpdTgt=8&OptMsk1=0&" in build_start_payload(program, spin=800)


def test_non_hundred_rpm_spin_is_rejected_as_unrepresentable(program):
    unrepresentable = replace(
        program,
        allowed=replace(program.allowed, spin=(850, 1000)),
    )
    with pytest.raises(OverrideError, match="rappresentabile"):
        build_start_payload(unrepresentable, spin=850)


def test_cli_list_uses_only_the_shared_catalog(monkeypatch, tmp_path, capsys):
    (tmp_path / "programs.json").write_bytes(FIXTURE.read_bytes())
    monkeypatch.chdir(tmp_path)

    assert candy_sendprogram.main(["list"]) == 0

    output = capsys.readouterr().out
    assert "cotone" in output
    assert "rapido-30" in output
    assert "sintetici" not in output


def test_cli_list_hides_technical_off_and_keeps_ordinary_program(
    monkeypatch, tmp_path, capsys
):
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    off_program = dict(data["programs"][0])
    off_program["name"] = "dual-wm-wd-off"
    off_program["prstr"] = "DUAL_WM_WD_OFF"
    data["programs"] = [off_program, data["programs"][1]]
    (tmp_path / "programs.json").write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    assert candy_sendprogram.main(["list"]) == 0

    output = capsys.readouterr().out
    assert "dual-wm-wd-off" not in output
    assert "rapido-30" in output


@pytest.mark.parametrize("contents", [None, "{invalid-json"])
def test_cli_list_requires_valid_catalog_and_shows_import_action(
    monkeypatch, tmp_path, capsys, contents
):
    if contents is not None:
        (tmp_path / "programs.json").write_text(contents, encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    assert candy_sendprogram.main(["list"]) == 2

    output = capsys.readouterr().out
    assert "candy_import_programs.py" in output
    assert "Rapid 30min" not in output


def test_soil_override_adds_only_target(program):
    assert "&SLevTgt=3&" in build_start_payload(program, soil=3)


def test_prewash_uses_first_option_mask(program):
    payload = build_start_payload(program, options=("prewash",))
    assert "&OptMsk1=1&OptMsk2=0&" in payload


def test_zoom_uses_second_option_mask(program):
    zoom_program = replace(
        program,
        allowed=replace(program.allowed, options=("zoom",)),
    )

    payload = build_start_payload(zoom_program, options=("zoom",))

    assert "&OptMsk1=0&OptMsk2=1&" in payload


def test_duplicate_option_keeps_mask_bit_idempotent(program):
    assert build_start_payload(program, options=("prewash", "prewash")) == (
        "Write=1&StSt=1&DelVl=0&PrNm=1&PrCode=7"
        "&PrStr=DUAL_WM_WD_PROGRAM_NAME_COTONE&TmpTgt=40&SLevTgt=2"
        "&SpdTgt=10&OptMsk1=1&OptMsk2=0&Lang=1&Stm=0&Dry=0&ED=0"
        "&RecipeId=0&StartCheckUp=0&DispTestOn=1"
    )


def test_invalid_override_raises_before_transport(tmp_path):
    path = tmp_path / "programs.json"
    path.write_bytes(FIXTURE.read_bytes())
    calls = []
    with pytest.raises(CatalogError, match="temperatura"):
        start_named_program(
            "cotone",
            catalog_path=path,
            temp=95,
            key_provider=lambda: calls.append("key"),
            sender=lambda payload, key: calls.append(payload),
        )
    assert calls == []


def test_start_named_program_rejects_technical_off_before_transport(
    monkeypatch, tmp_path
):
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    data["programs"][0]["name"] = "dual-wm-wd-off"
    data["programs"][0]["prstr"] = "DUAL_WM_WD_OFF"
    data["programs"] = [data["programs"][0]]
    path = tmp_path / "programs.json"
    path.write_text(json.dumps(data), encoding="utf-8")

    def forbidden(*_args):
        pytest.fail("OFF non deve costruire payload o accedere a chiave/trasporto")

    monkeypatch.setattr(candy_sendprogram, "build_start_payload", forbidden)

    with pytest.raises(OverrideError, match="tecnico non avviabile"):
        start_named_program(
            "dual-wm-wd-off",
            catalog_path=path,
            key_provider=forbidden,
            sender=forbidden,
        )


def test_invalid_catalog_blocks_key_and_sender(tmp_path):
    path = tmp_path / "programs.json"
    path.write_text("{invalid-json", encoding="utf-8")
    calls = []

    with pytest.raises(CatalogError, match="Catalogo programmi non disponibile"):
        start_named_program(
            "cotone",
            catalog_path=path,
            key_provider=lambda: calls.append("key"),
            sender=lambda payload, key: calls.append("send"),
        )
    assert calls == []


def test_missing_catalog_blocks_named_start(tmp_path):
    with pytest.raises(CatalogError, match="candy_import_programs.py"):
        start_named_program(
            "cotone",
            catalog_path=tmp_path / "missing.json",
            dry_run=True,
        )


def test_dry_run_returns_payload_without_key_or_sender(tmp_path):
    path = tmp_path / "programs.json"
    path.write_bytes(FIXTURE.read_bytes())

    def forbidden(*_args):
        pytest.fail("dry-run non deve accedere a chiave o trasporto")

    assert start_named_program(
        "cotone",
        catalog_path=path,
        dry_run=True,
        key_provider=forbidden,
        sender=forbidden,
    ) == DEFAULT_START_PAYLOAD


def test_valid_start_gets_key_then_sends_built_payload(tmp_path):
    path = tmp_path / "programs.json"
    path.write_bytes(FIXTURE.read_bytes())
    events = []

    def provide_key():
        events.append(("key",))
        return "local-key"

    def send(payload, key):
        events.append(("send", payload, key))

    expected = DEFAULT_START_PAYLOAD
    assert start_named_program(
        "cotone",
        catalog_path=path,
        key_provider=provide_key,
        sender=send,
    ) == expected
    assert events == [("key",), ("send", expected, "local-key")]


def test_key_validation_rejects_http_error_even_with_decodable_status(monkeypatch):
    key = "0123456789abcdef"
    body = xor_encode('{"statusLavatrice":{}}', key)
    monkeypatch.setattr(
        candy_sendprogram.requests,
        "get",
        lambda *_args, **_kwargs: ErrorResponse(body),
    )

    assert candy_sendprogram._key_valid(key) is False


def test_key_recovery_rejects_http_error_even_with_known_plaintext(monkeypatch):
    key = "0123456789abcdef"
    body = xor_encode(candy_sendprogram.KNOWN_STATUS_PREFIX, key)
    monkeypatch.setattr(
        candy_sendprogram.requests,
        "get",
        lambda *_args, **_kwargs: ErrorResponse(body),
    )

    assert candy_sendprogram._key_from_read() is None


def test_bm_key_recovery_rejects_http_error_body(monkeypatch):
    key = "0123456789abcdef"
    body = xor_encode(candy_sendprogram.KNOWN_RESPONSE[:16], key)
    monkeypatch.setattr(candy_sendprogram, "_load_cache", lambda: None)
    monkeypatch.setattr(candy_sendprogram, "_key_valid", lambda _key: True)
    monkeypatch.setattr(candy_sendprogram, "_key_from_read", lambda: None)
    monkeypatch.setattr(
        candy_sendprogram.requests,
        "get",
        lambda *_args, **_kwargs: ErrorResponse(body),
    )

    assert candy_sendprogram.getkey() is None


def test_cli_start_does_not_announce_success_for_device_http_error(
    monkeypatch, tmp_path, capsys
):
    (tmp_path / "programs.json").write_bytes(FIXTURE.read_bytes())
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(candy_sendprogram, "getkey", lambda: "local-key")
    monkeypatch.setattr(
        candy_sendprogram.requests,
        "get",
        lambda *_args, **_kwargs: ErrorResponse('{"response":"FAIL"}'),
    )

    result = candy_sendprogram.main(["start", "--program", "cotone"])

    output = capsys.readouterr().out
    assert result == 1
    assert "inviato" not in output
    assert "Impossibile inviare" in output


def test_cli_dry_run_validates_and_prints_without_getkey(monkeypatch, tmp_path, capsys):
    (tmp_path / "programs.json").write_bytes(FIXTURE.read_bytes())
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        candy_sendprogram,
        "getkey",
        lambda: pytest.fail("dry-run non deve recuperare la chiave"),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["candy_sendprogram.py", "start", "--program", "cotone", "--dry-run"],
    )

    assert candy_sendprogram.main() == 0
    assert DEFAULT_START_PAYLOAD in capsys.readouterr().out


def test_cli_start_rejects_raw_selector_bypass(monkeypatch):
    monkeypatch.setattr(
        candy_sendprogram,
        "getkey",
        lambda: pytest.fail("argomenti invalidi non devono recuperare la chiave"),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["candy_sendprogram.py", "start", "--program", "cotone", "--prnm", "9"],
    )

    with pytest.raises(SystemExit) as caught:
        candy_sendprogram.main()
    assert caught.value.code == 2


def test_stop_reads_status_and_sends_existing_stop_payload(monkeypatch):
    events = []

    def read_status(key):
        events.append(("read", key))
        return '{"statusLavatrice":{"Pr":"7"}}'

    def send_command(payload, key):
        events.append(("send", payload, key))
        return '{"response":"SUCCESS"}'

    monkeypatch.setattr(candy_sendprogram, "read_status", read_status)
    monkeypatch.setattr(candy_sendprogram, "send_command", send_command)

    candy_sendprogram.cmd_stop(SimpleNamespace(dry_run=False), "local-key")

    assert events == [
        ("read", "local-key"),
        ("send", "Write=1&StSt=0&PrNm=7", "local-key"),
    ]
