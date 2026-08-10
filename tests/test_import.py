import copy
import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

import candy_learn_programs
import candy_import_programs as importer
from candy_import_programs import (
    available_washer_summaries,
    build_parser,
    choose_appliance,
    find_matching_washers,
    flatten_parameters,
    mask_appliance_id,
    normalize_catalog,
    unwrap_appliance,
)
from candy_cloud import CandyCloudError
from candy_ciam import CiamAuthError
from candy_programs import CatalogError


def test_bwm_learning_guardrail_runs_before_appliance_access(monkeypatch, capsys):
    monkeypatch.setattr(
        candy_learn_programs,
        "read_program",
        lambda: pytest.fail("non deve leggere la lavatrice"),
    )

    assert candy_learn_programs.main(["--model", "BWM 149PH7/1-S"]) == 2
    assert "candy_import_programs.py" in capsys.readouterr().err


FIXTURE = Path(__file__).parent / "fixtures" / "cloud_appliances.json"
IMPORTED_AT = datetime(2026, 8, 1, tzinfo=timezone.utc)


def fixture_records():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def first_appliance():
    return unwrap_appliance(fixture_records()[0])


def off_record():
    record = copy.deepcopy(first_appliance()["programs"][0])
    record["program"]["name"] = "DUAL_WM_WD_OFF"
    return record


def test_unwraps_and_selects_unique_bwm():
    matches = find_matching_washers(fixture_records())
    assert len(matches) == 1
    assert matches[0]["appliance_model"] == "BWM 149PH7/1-S"
    assert choose_appliance(matches) is matches[0]


def test_model_matching_is_case_insensitive_and_ignores_commercial_suffix():
    assert find_matching_washers(fixture_records(), "bwm-149ph7") == [first_appliance()]


def test_model_matching_rejects_numeric_continuation_of_base_code():
    records = fixture_records()
    records[0]["appliance"]["appliance_model"] = "BWM 149PH70/1-S"
    assert find_matching_washers(records, "BWM 149PH7") == []


def test_model_matching_rejects_empty_canonical_query():
    with pytest.raises(CatalogError, match="model_query"):
        find_matching_washers(fixture_records(), " / - ")


def test_multiple_matching_washers_require_explicit_index():
    first = first_appliance()
    second = copy.deepcopy(first)
    second["id"] = "fake-device-9999"
    answers = iter(["2"])
    assert choose_appliance([first, second], input_fn=lambda prompt: next(answers)) is second


@pytest.mark.parametrize("answer", ["x", "0", "3"])
def test_multiple_matching_washers_reject_invalid_index(answer):
    first = first_appliance()
    second = copy.deepcopy(first)
    with pytest.raises(CatalogError, match="Selezione lavatrice non valida"):
        choose_appliance([first, second], input_fn=lambda prompt: answer)


def test_no_matching_washer_is_rejected():
    with pytest.raises(CatalogError, match="Nessuna BWM 149PH7"):
        choose_appliance([])


def test_available_washer_summaries_include_only_washers_and_mask_ids():
    records = fixture_records()
    records.append(
        {
            "appliance": {
                "id": "fake-fridge-9876",
                "appliance_model": "COLD 100",
                "appliance_type": "REFRIGERATOR",
            }
        }
    )
    assert available_washer_summaries(records) == ["BWM 149PH7/1-S ***1234"]


def test_masks_appliance_id_to_last_four_characters():
    assert mask_appliance_id("fake-device-1234") == "***1234"


@pytest.mark.parametrize("value", [None, ""])
def test_rejects_missing_appliance_id_value(value):
    with pytest.raises(CatalogError, match="identificatore non valido"):
        mask_appliance_id(value)


def test_rejects_too_short_appliance_id():
    with pytest.raises(CatalogError, match="identificatore non valido"):
        mask_appliance_id("123")


def test_flattens_wrapped_parameters():
    raw_program = first_appliance()["programs"][0]["program"]
    parameters = flatten_parameters(raw_program)
    assert parameters["selector_position"] == "1"
    assert parameters["pr_code"] == "7"


def test_rejects_duplicate_parameter_names():
    raw_program = first_appliance()["programs"][0]["program"]
    raw_program["command_parameters"].append(
        {"command_parameter": {"name": "pr_code", "validation": "8"}}
    )
    with pytest.raises(CatalogError, match="pr_code.*duplicato"):
        flatten_parameters(raw_program)


def test_ignores_unused_empty_command_parameter_during_normalization():
    appliance = first_appliance()
    appliance["programs"][0]["program"]["command_parameters"].append(
        {"command_parameter": {"name": "unused_cloud_value", "validation": ""}}
    )

    catalog = normalize_catalog(appliance, imported_at=IMPORTED_AT)

    assert [program.name for program in catalog.programs] == ["cotone"]


def test_normalize_catalog_excludes_technical_off():
    appliance = first_appliance()
    appliance["programs"].insert(0, off_record())

    catalog = normalize_catalog(appliance, imported_at=IMPORTED_AT)

    assert [program.prstr for program in catalog.programs] == [
        "DUAL_WM_WD_PROGRAM_NAME_COTONE"
    ]


def test_normalize_catalog_rejects_catalog_with_only_technical_records():
    appliance = first_appliance()
    appliance["programs"] = [off_record()]

    with pytest.raises(CatalogError, match="nessun programma avviabile"):
        normalize_catalog(appliance, imported_at=IMPORTED_AT)


def test_empty_available_options_uses_absent_options_fallback():
    appliance = first_appliance()
    parameters = appliance["programs"][0]["program"]["command_parameters"]
    next(
        item for item in parameters if item["command_parameter"]["name"] == "available_options"
    )["command_parameter"]["validation"] = ""

    program = normalize_catalog(appliance, imported_at=IMPORTED_AT).programs[0]

    assert program.allowed.options == ()


def test_empty_default_temperature_is_rejected_as_missing_required_value():
    appliance = first_appliance()
    parameters = appliance["programs"][0]["program"]["command_parameters"]
    next(
        item for item in parameters if item["command_parameter"]["name"] == "default_temperature"
    )["command_parameter"]["validation"] = ""

    with pytest.raises(CatalogError, match="default_temperature"):
        normalize_catalog(appliance, imported_at=IMPORTED_AT)


def test_rejects_duplicate_pr_code_when_first_value_is_empty():
    raw_program = first_appliance()["programs"][0]["program"]
    parameters = raw_program["command_parameters"]
    next(
        item for item in parameters if item["command_parameter"]["name"] == "pr_code"
    )["command_parameter"]["validation"] = ""
    parameters.append({"command_parameter": {"name": "pr_code", "validation": "8"}})

    with pytest.raises(CatalogError, match="pr_code.*duplicato"):
        flatten_parameters(raw_program)


def test_maps_selector_pr_code_name_and_defaults_exactly():
    catalog = normalize_catalog(first_appliance(), imported_at=IMPORTED_AT)
    program = catalog.programs[0]
    assert (program.name, program.prnm, program.prcode) == ("cotone", 1, 7)
    assert program.prstr == "DUAL_WM_WD_PROGRAM_NAME_COTONE"
    assert (program.defaults.temp, program.defaults.spin, program.defaults.soil) == (40, 1000, 2)
    assert (program.defaults.steam, program.defaults.dry) == (0, 0)
    assert program.allowed.temp == (40,)
    assert program.allowed.spin == (1000,)
    assert program.allowed.soil == (2,)
    assert program.allowed.options == ()
    assert catalog.appliance_id_masked == "***1234"
    assert catalog.imported_at == "2026-08-01T00:00:00+00:00"


def test_uses_valid_uid_when_id_is_none():
    appliance = first_appliance()
    appliance["id"] = None
    appliance["uid"] = "fake-uid-5678"

    catalog = normalize_catalog(appliance, imported_at=IMPORTED_AT)

    assert catalog.appliance_id_masked == "***5678"
    assert available_washer_summaries([{"appliance": appliance}]) == [
        "BWM 149PH7/1-S ***5678"
    ]


@pytest.mark.parametrize(
    "identifiers",
    [
        {},
        {"id": None, "uid": ""},
    ],
)
def test_rejects_appliance_without_any_valid_identifier(identifiers):
    appliance = first_appliance()
    appliance.pop("id")
    appliance.update(identifiers)

    with pytest.raises(CatalogError, match="identificatore non valido"):
        normalize_catalog(appliance, imported_at=IMPORTED_AT)


def test_uses_explicit_allowed_lists_and_known_option_bits():
    appliance = first_appliance()
    parameters = appliance["programs"][0]["program"]["command_parameters"]
    parameters.extend(
        [
            {"command_parameter": {"name": "allowed_temperatures", "validation": "20,40,60"}},
            {"command_parameter": {"name": "allowed_spin_speeds", "validation": "0,1000"}},
            {"command_parameter": {"name": "allowed_soil_levels", "validation": "1,2,3"}},
        ]
    )
    next(
        item for item in parameters if item["command_parameter"]["name"] == "available_options"
    )["command_parameter"]["validation"] = "129"

    program = normalize_catalog(appliance, imported_at=IMPORTED_AT).programs[0]

    assert program.allowed.temp == (20, 40, 60)
    assert program.allowed.spin == (0, 1000)
    assert program.allowed.soil == (1, 2, 3)
    assert program.allowed.options == ("prewash", "aquaplus")


@pytest.mark.parametrize("missing", ["selector_position", "pr_code"])
def test_rejects_program_without_required_mapping(missing):
    appliance = first_appliance()
    parameters = appliance["programs"][0]["program"]["command_parameters"]
    parameters[:] = [
        item for item in parameters if item["command_parameter"]["name"] != missing
    ]
    with pytest.raises(CatalogError, match=missing):
        normalize_catalog(appliance, imported_at=IMPORTED_AT)


def test_cloud_position_and_id_never_replace_selector_or_pr_code():
    appliance = first_appliance()
    raw_program = appliance["programs"][0]["program"]
    raw_program["position"] = 55
    raw_program["id"] = "66"
    raw_program["command_parameters"] = []
    with pytest.raises(CatalogError, match="selector_position"):
        normalize_catalog(appliance, imported_at=IMPORTED_AT)


def test_one_bad_program_rejects_whole_catalog():
    appliance = first_appliance()
    bad = copy.deepcopy(appliance["programs"][0])
    bad["program"]["command_parameters"] = []
    appliance["programs"].append(bad)
    with pytest.raises(CatalogError):
        normalize_catalog(appliance, imported_at=IMPORTED_AT)


def test_duplicate_local_names_receive_selector_suffix():
    appliance = first_appliance()
    duplicate = copy.deepcopy(appliance["programs"][0])
    parameters = duplicate["program"]["command_parameters"]
    next(
        item for item in parameters if item["command_parameter"]["name"] == "selector_position"
    )["command_parameter"]["validation"] = "2"
    next(
        item for item in parameters if item["command_parameter"]["name"] == "pr_code"
    )["command_parameter"]["validation"] = "8"
    appliance["programs"].append(duplicate)

    catalog = normalize_catalog(appliance, imported_at=IMPORTED_AT)

    assert [program.name for program in catalog.programs] == ["cotone", "cotone-2"]


def test_rejects_unknown_available_option_bits():
    appliance = first_appliance()
    parameters = appliance["programs"][0]["program"]["command_parameters"]
    next(
        item for item in parameters if item["command_parameter"]["name"] == "available_options"
    )["command_parameter"]["validation"] = "256"
    with pytest.raises(CatalogError, match="bit sconosciuti"):
        normalize_catalog(appliance, imported_at=IMPORTED_AT)


def test_parser_rejects_password_option():
    with pytest.raises(SystemExit):
        build_parser().parse_args(["--password"])


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
    captured = capsys.readouterr()
    assert pending.authorization_url in captured.out
    assert "browser-private-detail" not in captured.out + captured.err


def test_browser_false_keeps_printed_url_and_continues_manual_flow(
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
        return "jwt-private-marker"

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
        browser_open=lambda url: events.append(("open", url)) or False,
        callback_reader=lambda prompt: events.append(("prompt", prompt))
        or "candy://mobilesdk/detect/oauth/done#refresh_token=callback-private-marker",
    ) == 0

    assert events[0] == ("open", pending.authorization_url)
    assert events[1][0] == "prompt"
    assert events[2][0] == "complete"
    assert events[3:] == [
        ("client", "jwt-private-marker"),
        ("fetch",),
        ("save", output, 1),
    ]
    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert pending.authorization_url in captured.out
    assert "callback-private-marker" not in combined
    assert "jwt-private-marker" not in combined


@pytest.mark.parametrize("reader_error", [EOFError(), KeyboardInterrupt()])
def test_callback_cancellation_never_saves(monkeypatch, tmp_path, capsys, reader_error):
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
        assert prompt == "Callback Candy (input nascosto): "
        raise type(reader_error)("callback-private-marker")

    assert importer.main(
        ["--output", str(tmp_path / "programs.json")],
        browser_open=lambda url: True,
        callback_reader=cancel,
    ) == 3
    captured = capsys.readouterr()
    assert captured.err == "Accesso Candy annullato.\n"
    combined = captured.out + captured.err
    assert "callback-private-marker" not in combined
    assert "jwt-private-marker" not in combined


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


def test_main_schema_error_never_saves(monkeypatch, tmp_path):
    records = fixture_records()
    records[0]["appliance"]["programs"][0]["program"]["command_parameters"] = []
    pending = SimpleNamespace(
        authorization_url="https://account.candy-home.com/safe-authorize",
        device_id="0123456789abcdef",
    )

    class FakeClient:
        def __init__(self, id_token):
            pass

        def fetch_appliances(self):
            return records

    monkeypatch.setattr(importer, "CandyCloudClient", FakeClient)
    monkeypatch.setattr(importer, "begin_ciam_login", lambda: pending)
    monkeypatch.setattr(importer, "complete_ciam_login", lambda pending, callback: "jwt")
    monkeypatch.setattr(
        importer,
        "save_catalog_atomic",
        lambda catalog, path: pytest.fail("non deve salvare"),
    )
    output = tmp_path / "programs.json"
    assert importer.main(
        ["--output", str(output)],
        browser_open=lambda url: True,
        callback_reader=lambda prompt: "private-callback",
    ) == 2
    assert not output.exists()


def test_main_reports_cloud_error_without_saving(monkeypatch, tmp_path, capsys):
    output = tmp_path / "programs.json"
    original = b"existing-catalog\r\nprivate-bytes"
    backup = output.with_suffix(".json.bak")
    original_backup = b"previous-backup\nprivate-backup-bytes"
    output.write_bytes(original)
    backup.write_bytes(original_backup)
    pending = SimpleNamespace(
        authorization_url="https://account.candy-home.com/safe-authorize",
        device_id="0123456789abcdef",
    )
    events = []

    class FakeClient:
        def __init__(self, id_token):
            events.append(("client", id_token))

        def fetch_appliances(self):
            events.append(("fetch",))
            raise CandyCloudError("cloud fake non disponibile")

    monkeypatch.setattr(importer, "CandyCloudClient", FakeClient)
    monkeypatch.setattr(importer, "begin_ciam_login", lambda: pending)
    monkeypatch.setattr(importer, "complete_ciam_login", lambda pending, callback: "jwt")
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
    assert events == [("client", "jwt"), ("fetch",)]
    assert output.read_bytes() == original
    assert backup.read_bytes() == original_backup
    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "private-callback" not in combined
    assert "jwt" not in combined
