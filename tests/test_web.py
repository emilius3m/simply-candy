import json
from dataclasses import replace
from html.parser import HTMLParser
from pathlib import Path

import pytest
import requests
from fastapi.testclient import TestClient

import candy_web
from candy_programs import CatalogUnavailableError, parse_catalog


FIXTURE = Path(__file__).parent / "fixtures" / "programs_valid.json"
CLIENT = TestClient(candy_web.app)
ERROR_CLIENT = TestClient(candy_web.app, raise_server_exceptions=False)


class PageStateParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.body = {}
        self.elements = {}
        self.text = {}
        self._current_id = None
        self.checkbox_values = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "body":
            self.body = attributes
        element_id = attributes.get("id")
        if element_id:
            self.elements[element_id] = attributes
            self.text[element_id] = ""
            self._current_id = element_id
        if (
            tag == "input"
            and attributes.get("type") == "checkbox"
            and attributes.get("value") is not None
        ):
            self.checkbox_values.append(attributes.get("value"))

    def handle_endtag(self, _tag):
        self._current_id = None

    def handle_data(self, data):
        if self._current_id:
            self.text[self._current_id] += data


def page_state(response):
    parser = PageStateParser()
    parser.feed(response.text)
    return parser


def catalog():
    return parse_catalog(json.loads(FIXTURE.read_text(encoding="utf-8")))


def unavailable_catalog():
    raise CatalogUnavailableError("Esegui: python candy_import_programs.py")


def catalog_with_unrepresentable_spin():
    shared = catalog()
    program = shared.programs[0]
    changed = replace(program, allowed=replace(program.allowed, spin=(850, 1000)))
    return replace(shared, programs=(changed, *shared.programs[1:]))


def catalog_with_off():
    shared = catalog()
    off = replace(
        shared.programs[0],
        name="dual-wm-wd-off",
        prstr="DUAL_WM_WD_OFF",
        prnm=0,
        prcode=0,
    )
    return replace(shared, programs=(off, *shared.programs))


def catalog_with_only_off():
    shared = catalog_with_off()
    return replace(shared, programs=(shared.programs[0],))


def catalog_with_representative_options():
    shared = catalog()
    first, second = shared.programs
    first = replace(
        first,
        allowed=replace(first.allowed, options=("good_night", "anti_crease")),
    )
    second = replace(
        second,
        allowed=replace(
            second.allowed,
            options=("extra_rinse_1", "extra_rinse_2", "extra_rinse_3"),
        ),
    )
    return replace(shared, programs=(first, second))


class ErrorResponse:
    status_code = 500

    def __init__(self, text):
        self._text = text

    def raise_for_status(self):
        raise requests.HTTPError("device returned 500", response=self)

    @property
    def text(self):
        return self._text


def forbid_network(*_args, **_kwargs):
    pytest.fail("la validazione deve terminare prima di accedere alla rete")


def test_api_programs_matches_shared_catalog(monkeypatch):
    monkeypatch.setattr(candy_web, "get_program_catalog", catalog)

    response = CLIENT.get("/api/programs")

    assert response.status_code == 200
    assert [item["name"] for item in response.json()] == ["cotone", "rapido-30"]
    assert response.json()[0] == {
        "name": "cotone",
        "prnm": 1,
        "prcode": 7,
        "prstr": "DUAL_WM_WD_PROGRAM_NAME_COTONE",
        "defaults": {"temp": 40, "spin": 1000, "soil": 2, "steam": 0, "dry": 0},
        "allowed": {
            "temp": [30, 40],
            "spin": [800, 1000],
            "soil": [2, 3],
            "options": ["prewash"],
        },
    }


def test_get_program_catalog_delegates_to_shared_loader(monkeypatch):
    expected = object()
    calls = []

    def load(path):
        calls.append(path)
        return expected

    monkeypatch.setattr(candy_web, "load_catalog", load)

    assert candy_web.get_program_catalog() is expected
    assert calls == [Path("programs.json")]


def test_missing_catalog_returns_actionable_503(monkeypatch):
    monkeypatch.setattr(candy_web, "get_program_catalog", unavailable_catalog)

    response = CLIENT.get("/api/programs")

    assert response.status_code == 503
    assert "candy_import_programs.py" in response.json()["detail"]


def test_config_reports_catalog_unavailable_without_hiding_programs_error(monkeypatch):
    monkeypatch.setattr(candy_web, "get_program_catalog", unavailable_catalog)

    config_response = CLIENT.get("/api/config")
    programs_response = CLIENT.get("/api/programs")

    assert config_response.status_code == 200
    assert config_response.json()["programs"] == []
    assert config_response.json()["catalog_ready"] is False
    assert programs_response.status_code == 503


def test_legacy_off_is_hidden_from_program_and_config_endpoints(monkeypatch):
    monkeypatch.setattr(candy_web, "get_program_catalog", catalog_with_off)

    programs = CLIENT.get("/api/programs")
    config = CLIENT.get("/api/config")

    assert programs.status_code == 200
    assert "dual-wm-wd-off" not in [item["name"] for item in programs.json()]
    assert "dual-wm-wd-off" not in config.json()["programs"]

    monkeypatch.setattr(candy_web, "get_program_catalog", catalog_with_only_off)

    programs = CLIENT.get("/api/programs")
    config = CLIENT.get("/api/config")

    assert programs.json() == []
    assert config.json()["programs"] == []
    assert config.json()["catalog_ready"] is False


def test_start_rejects_technical_off_before_payload_or_transport(monkeypatch):
    monkeypatch.setattr(candy_web, "get_program_catalog", catalog_with_off)
    monkeypatch.setattr(candy_web.c, "build_start_payload", forbid_network)
    monkeypatch.setattr(candy_web.c, "getkey", forbid_network)
    monkeypatch.setattr(candy_web.c, "send_command", forbid_network)

    response = CLIENT.post(
        "/api/start",
        json={"program": "dual-wm-wd-off", "dry_run": False},
    )

    assert response.status_code == 422
    assert "tecnico non avviabile" in response.json()["detail"]


def test_start_unknown_program_returns_404_without_network(monkeypatch):
    monkeypatch.setattr(candy_web, "get_program_catalog", catalog)
    monkeypatch.setattr(candy_web.c, "getkey", forbid_network)
    monkeypatch.setattr(candy_web.c, "send_command", forbid_network)

    response = CLIENT.post("/api/start", json={"program": "inesistente"})

    assert response.status_code == 404


def test_start_disallowed_temperature_returns_422_without_network(monkeypatch):
    monkeypatch.setattr(candy_web, "get_program_catalog", catalog)
    monkeypatch.setattr(candy_web.c, "getkey", forbid_network)
    monkeypatch.setattr(candy_web.c, "send_command", forbid_network)

    response = CLIENT.post("/api/start", json={"program": "cotone", "temp": 95})

    assert response.status_code == 422


def test_start_unrepresentable_spin_returns_422_without_network(monkeypatch):
    monkeypatch.setattr(
        candy_web, "get_program_catalog", catalog_with_unrepresentable_spin
    )
    monkeypatch.setattr(candy_web.c, "getkey", forbid_network)
    monkeypatch.setattr(candy_web.c, "send_command", forbid_network)

    response = ERROR_CLIENT.post(
        "/api/start", json={"program": "cotone", "spin": 850}
    )

    assert response.status_code == 422


def test_start_missing_catalog_returns_503_without_network(monkeypatch):
    monkeypatch.setattr(candy_web, "get_program_catalog", unavailable_catalog)
    monkeypatch.setattr(candy_web.c, "getkey", forbid_network)
    monkeypatch.setattr(candy_web.c, "send_command", forbid_network)

    response = CLIENT.post("/api/start", json={"program": "cotone"})

    assert response.status_code == 503
    assert "candy_import_programs.py" in response.json()["detail"]


def test_raw_selector_cannot_replace_required_program(monkeypatch):
    monkeypatch.setattr(candy_web.c, "getkey", forbid_network)
    monkeypatch.setattr(candy_web.c, "send_command", forbid_network)

    response = CLIENT.post("/api/start", json={"prnm": 1, "prcode": 7})

    assert response.status_code == 422


@pytest.mark.parametrize(
    "body",
    [
        {"program": "cotone"},
        {"program": "cotone", "dry_run": True},
    ],
)
def test_start_is_dry_run_without_explicit_false(monkeypatch, body):
    monkeypatch.setattr(candy_web, "get_program_catalog", catalog)
    monkeypatch.setattr(candy_web.c, "getkey", forbid_network)
    monkeypatch.setattr(candy_web.c, "send_command", forbid_network)

    response = CLIENT.post("/api/start", json=body)

    assert response.status_code == 200
    assert response.json()["sent"] is False
    assert response.json()["dry_run"] is True
    assert response.json()["payload"].startswith("Write=1&StSt=1&")


@pytest.mark.parametrize(
    "dry_run",
    [0, 1, "false", "true", "0", "1", None, "", [], {}],
    ids=[
        "zero",
        "one",
        "false-string",
        "true-string",
        "zero-string",
        "one-string",
        "null",
        "empty-string",
        "list",
        "object",
    ],
)
def test_start_rejects_every_non_boolean_dry_run_before_payload_or_transport(
    monkeypatch, dry_run
):
    monkeypatch.setattr(candy_web, "get_program_catalog", catalog)
    monkeypatch.setattr(candy_web.c, "build_start_payload", forbid_network)
    monkeypatch.setattr(candy_web.c, "getkey", forbid_network)
    monkeypatch.setattr(candy_web.c, "send_command", forbid_network)

    response = ERROR_CLIENT.post(
        "/api/start", json={"program": "cotone", "dry_run": dry_run}
    )

    assert response.status_code == 422


def test_valid_start_uses_sender_after_explicit_dry_run_false(monkeypatch):
    monkeypatch.setattr(candy_web, "get_program_catalog", catalog)
    calls = []

    def getkey():
        calls.append(("key",))
        return b"0" * 16

    def send_command(payload, key):
        calls.append(("send", payload, key))
        return "{}"

    monkeypatch.setattr(candy_web.c, "getkey", getkey)
    monkeypatch.setattr(candy_web.c, "send_command", send_command)

    response = CLIENT.post(
        "/api/start", json={"program": "cotone", "dry_run": False}
    )

    expected = (
        "Write=1&StSt=1&DelVl=0&PrNm=1&PrCode=7&"
        "PrStr=DUAL_WM_WD_PROGRAM_NAME_COTONE&TmpTgt=40&SLevTgt=2&"
        "SpdTgt=10&OptMsk1=0&OptMsk2=0&Lang=1&Stm=0&Dry=0&ED=0&"
        "RecipeId=0&StartCheckUp=0&DispTestOn=1"
    )
    assert response.status_code == 200
    assert response.json()["sent"] is True
    assert response.json()["dry_run"] is False
    assert response.json()["payload"] == expected
    assert calls == [("key",), ("send", expected, b"0" * 16)]


def test_sender_failure_returns_502(monkeypatch):
    monkeypatch.setattr(candy_web, "get_program_catalog", catalog)
    monkeypatch.setattr(candy_web.c, "getkey", lambda: b"0" * 16)

    def fail_send(_payload, _key):
        raise OSError("trasporto offline")

    monkeypatch.setattr(candy_web.c, "send_command", fail_send)

    response = CLIENT.post(
        "/api/start", json={"program": "cotone", "dry_run": False}
    )

    assert response.status_code == 502
    assert "Invio comando fallito" in response.json()["detail"]


def test_stop_uses_current_program_and_returns_parsed_response(monkeypatch):
    events = []

    def getkey():
        events.append(("key",))
        return "local-key"

    def read_status(key):
        events.append(("status", key))
        return '{"statusLavatrice":{"Pr":"7"}}'

    def send_command(payload, key):
        events.append(("send", payload, key))
        return '{"response":"SUCCESS"}'

    monkeypatch.setattr(candy_web.c, "getkey", getkey)
    monkeypatch.setattr(candy_web.c, "read_status", read_status)
    monkeypatch.setattr(candy_web.c, "send_command", send_command)

    response = CLIENT.post("/api/stop")
    body = response.json()
    stopped = body["sent"]

    assert response.status_code == 200
    assert stopped is True
    assert body["payload"] == "Write=1&StSt=0&PrNm=7"
    assert body["response"] == {"response": "SUCCESS"}
    assert events == [
        ("key",),
        ("status", "local-key"),
        ("send", "Write=1&StSt=0&PrNm=7", "local-key"),
    ]


def test_stop_wraps_non_json_response_as_raw(monkeypatch):
    monkeypatch.setattr(candy_web.c, "getkey", lambda: "local-key")
    monkeypatch.setattr(
        candy_web.c,
        "read_status",
        lambda key: '{"statusLavatrice":{"Pr":"3"}}',
    )
    monkeypatch.setattr(candy_web.c, "send_command", lambda payload, key: "OK")

    response = CLIENT.post("/api/stop")

    assert response.status_code == 200
    assert response.json()["payload"] == "Write=1&StSt=0&PrNm=3"
    assert response.json()["response"] == {"raw": "OK"}


@pytest.mark.parametrize("failure_stage", ["key", "status", "transport"])
def test_stop_dependency_failure_returns_actionable_502(monkeypatch, failure_stage):
    def getkey():
        if failure_stage == "key":
            raise OSError("chiave offline")
        return "local-key"

    def read_status(key):
        if failure_stage == "status":
            raise OSError("stato offline")
        return '{"statusLavatrice":{"Pr":"5"}}'

    def send_command(payload, key):
        if failure_stage == "transport":
            raise OSError("trasporto offline")
        pytest.fail("il trasporto non deve essere raggiunto")

    monkeypatch.setattr(candy_web.c, "getkey", getkey)
    monkeypatch.setattr(candy_web.c, "read_status", read_status)
    monkeypatch.setattr(candy_web.c, "send_command", send_command)

    response = CLIENT.post("/api/stop")

    assert response.status_code == 502
    assert response.json()["detail"] == {
        "key": "Stop fallito: chiave offline",
        "status": "Stop fallito: stato offline",
        "transport": "Stop fallito: trasporto offline",
    }[failure_stage]


def test_device_http_error_returns_502_without_sent_true(monkeypatch):
    monkeypatch.setattr(candy_web, "get_program_catalog", catalog)
    monkeypatch.setattr(candy_web.c, "getkey", lambda: "local-key")
    monkeypatch.setattr(
        candy_web.c.requests,
        "get",
        lambda *_args, **_kwargs: ErrorResponse('{"response":"FAIL"}'),
    )

    response = CLIENT.post(
        "/api/start", json={"program": "cotone", "dry_run": False}
    )

    assert response.status_code == 502
    assert response.json().get("sent") is not True


def test_status_http_error_is_offline_even_with_decodable_body(monkeypatch):
    key = "0123456789abcdef"
    encrypted = candy_web.c.xor_encode('{"statusLavatrice":{}}', key)
    monkeypatch.setattr(candy_web.c, "getkey", lambda: key)
    monkeypatch.setattr(
        candy_web.c.requests,
        "get",
        lambda *_args, **_kwargs: ErrorResponse(encrypted),
    )

    response = CLIENT.get("/api/status")

    assert response.status_code == 503


def test_page_renders_every_catalog_option_with_protocol_identifier(monkeypatch):
    monkeypatch.setattr(
        candy_web, "get_program_catalog", catalog_with_representative_options
    )

    state = page_state(CLIENT.get("/"))

    assert set(state.checkbox_values) == {
        "good_night",
        "anti_crease",
        "extra_rinse_1",
        "extra_rinse_2",
        "extra_rinse_3",
    }


def test_real_send_checkbox_is_unchecked_and_controls_dry_run(monkeypatch):
    monkeypatch.setattr(candy_web, "get_program_catalog", catalog)

    response = CLIENT.get("/")
    state = page_state(response)

    assert state.elements["real-send"]["type"] == "checkbox"
    assert "checked" not in state.elements["real-send"]
    assert state.elements["real-send"]["onchange"] == "updateStartMode()"
    assert "dry_run:!realSend" in response.text
    assert "if(realSend && !confirm(" in response.text
    assert "resetRealSend()" in response.text
    assert "finally" in response.text
    assert "Simula programma" in response.text


def test_real_send_confirms_before_fetch_and_only_refreshes_real_start(monkeypatch):
    monkeypatch.setattr(candy_web, "get_program_catalog", catalog)

    page = CLIENT.get("/").text
    start = page[page.index("async function start()"):page.index("async function stop()")]
    cancel = start[start.index("if(realSend"):start.index("const opts=")]
    real_success = start[start.index("if(d.sent)"):start.index("}else{")]
    simulation_success = start[start.index("}else{"):start.index("}catch(e)")]

    assert start.index("if(realSend && !confirm(") < start.index("fetch('/api/start'")
    assert "resetRealSend();" in cancel
    assert "return;" in cancel
    assert "setTimeout(loadStatus,1500)" in real_success
    assert "setTimeout(loadStatus,1500)" not in simulation_success
    assert "comando non inviato" in simulation_success


def test_zoom_has_readable_label(monkeypatch):
    shared = catalog()
    zoom = replace(
        shared.programs[0],
        allowed=replace(shared.programs[0].allowed, options=("zoom",)),
    )
    monkeypatch.setattr(
        candy_web,
        "get_program_catalog",
        lambda: replace(shared, programs=(zoom,)),
    )

    response = CLIENT.get("/")

    assert 'value="zoom"' in response.text
    assert "> Zoom</label>" in response.text


def test_zoom_option_is_sent_in_second_protocol_mask(monkeypatch):
    shared = catalog()
    zoom = replace(
        shared.programs[0],
        allowed=replace(shared.programs[0].allowed, options=("zoom",)),
    )
    monkeypatch.setattr(
        candy_web,
        "get_program_catalog",
        lambda: replace(shared, programs=(zoom,)),
    )
    calls = []
    monkeypatch.setattr(candy_web.c, "getkey", lambda: "local-key")
    monkeypatch.setattr(
        candy_web.c,
        "send_command",
        lambda payload, key: calls.append((payload, key)) or "{}",
    )

    response = CLIENT.post(
        "/api/start",
        json={"program": "cotone", "options": ["zoom"], "dry_run": False},
    )

    assert response.status_code == 200
    assert response.json()["sent"] is True
    assert "&OptMsk1=0&OptMsk2=1&" in response.json()["payload"]
    assert calls == [(response.json()["payload"], "local-key")]


@pytest.mark.parametrize(
    ("program_name", "options", "expected_mask"),
    [
        ("cotone", ["good_night", "anti_crease"], 12),
        (
            "rapido-30",
            ["extra_rinse_1", "extra_rinse_2", "extra_rinse_3"],
            112,
        ),
    ],
)
def test_selected_program_sends_exact_catalog_option_identifiers(
    monkeypatch, program_name, options, expected_mask
):
    monkeypatch.setattr(
        candy_web, "get_program_catalog", catalog_with_representative_options
    )
    calls = []
    monkeypatch.setattr(candy_web.c, "getkey", lambda: "local-key")
    monkeypatch.setattr(
        candy_web.c,
        "send_command",
        lambda payload, key: calls.append((payload, key)) or "{}",
    )

    response = CLIENT.post(
        "/api/start",
        json={"program": program_name, "options": options, "dry_run": False},
    )

    assert response.status_code == 200
    assert f"&OptMsk1={expected_mask}&OptMsk2=0&" in response.json()["payload"]
    assert calls == [(response.json()["payload"], "local-key")]


def test_program_entry_point_binds_to_loopback_by_default():
    calls = []

    def runner(app, **settings):
        calls.append((app, settings))

    assert candy_web.main(uvicorn_runner=runner, port_finder=lambda: 8123) == 0
    assert calls == [
        (
            "candy_web:app",
            {"host": "127.0.0.1", "port": 8123, "reload": True},
        )
    ]


def test_page_ready_state_enables_launch_and_hides_recovery(monkeypatch):
    monkeypatch.setattr(candy_web, "get_program_catalog", catalog)

    response = CLIENT.get("/")
    state = page_state(response)

    assert response.status_code == 200
    assert state.body["data-catalog-ready"] == "true"
    assert "disabled" not in state.elements["start-button"]
    assert "hidden" in state.elements["catalog-recovery"]
    assert "delay" not in state.elements


def test_page_unavailable_state_disables_launch_and_shows_recovery(monkeypatch):
    monkeypatch.setattr(candy_web, "get_program_catalog", unavailable_catalog)

    response = CLIENT.get("/")
    state = page_state(response)

    assert response.status_code == 200
    assert state.body["data-catalog-ready"] == "false"
    assert "disabled" in state.elements["start-button"]
    assert "hidden" not in state.elements["catalog-recovery"]
    assert "python candy_import_programs.py" in state.text["catalog-recovery"]


def test_page_with_only_technical_off_disables_launch_and_shows_recovery(monkeypatch):
    monkeypatch.setattr(candy_web, "get_program_catalog", catalog_with_only_off)

    response = CLIENT.get("/")
    state = page_state(response)

    assert response.status_code == 200
    assert state.body["data-catalog-ready"] == "false"
    assert "disabled" in state.elements["start-button"]
    assert "hidden" not in state.elements["catalog-recovery"]


def test_init_rejects_unready_or_empty_hydration_before_hiding_recovery(monkeypatch):
    monkeypatch.setattr(candy_web, "get_program_catalog", catalog)

    page = CLIENT.get("/").text
    init = page[page.index("async function init()"):page.index("function onProg()")]
    guard = "if(!r.catalog_ready || list.length===0)"
    hide_recovery = "$('catalog-recovery').hidden=true"

    assert guard in init
    assert "throw new Error(" in init[init.index(guard):init.index(hide_recovery)]
    assert init.index(guard) < init.index(hide_recovery)


def test_cli_list_and_web_expose_the_same_program_names(
    monkeypatch, tmp_path, capsys
):
    (tmp_path / "programs.json").write_bytes(FIXTURE.read_bytes())
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(candy_web, "PROGRAMS_PATH", Path("programs.json"))

    response = CLIENT.get("/api/programs")
    assert candy_web.c.main(["list"]) == 0

    listed = capsys.readouterr().out
    assert response.status_code == 200
    assert [item["name"] for item in response.json()] == ["cotone", "rapido-30"]
    assert "cotone" in listed and "rapido-30" in listed
    assert "sintetici" not in listed
