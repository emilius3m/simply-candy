import copy
from dataclasses import replace
import json
from pathlib import Path

import pytest

from candy_programs import (
    CatalogError,
    CatalogUnavailableError,
    OverrideError,
    ProgramCatalog,
    catalog_to_dict,
    is_startable_program,
    load_catalog,
    parse_catalog,
    require_startable_program,
    save_catalog_atomic,
    startable_programs,
    validate_overrides,
)


FIXTURE = Path(__file__).parent / "fixtures" / "programs_valid.json"


def fixture_data():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def write_json(path, data):
    path.write_text(json.dumps(data), encoding="utf-8")


def test_loads_valid_catalog(tmp_path):
    path = tmp_path / "programs.json"
    path.write_bytes(FIXTURE.read_bytes())
    catalog = load_catalog(path)
    assert catalog.appliance_model == "BWM 149PH7"
    assert [item.name for item in catalog.programs] == ["cotone", "rapido-30"]


def test_rejects_duplicate_program_name():
    data = fixture_data()
    data["programs"].append(copy.deepcopy(data["programs"][0]))
    with pytest.raises(CatalogError, match="duplicat"):
        parse_catalog(data)


def test_startability_policy_filters_and_rejects_technical_off():
    catalog = parse_catalog(fixture_data())
    off = replace(
        catalog.programs[0],
        name="dual-wm-wd-off",
        prstr="DUAL_WM_WD_OFF",
    )
    legacy = replace(catalog, programs=(off, *catalog.programs))

    assert is_startable_program(off) is False
    assert is_startable_program(catalog.programs[0]) is True
    assert startable_programs(legacy) == catalog.programs
    with pytest.raises(OverrideError, match="tecnico non avviabile"):
        require_startable_program(off)
    assert require_startable_program(catalog.programs[0]) is catalog.programs[0]


def test_accepts_distinct_program_names_with_same_prnm_prcode_pair():
    data = fixture_data()
    same_pair = copy.deepcopy(data["programs"][0])
    same_pair["name"] = "cotone-family-variant"
    data["programs"].append(same_pair)

    catalog = parse_catalog(data)

    assert [(program.name, program.prnm, program.prcode) for program in catalog.programs] == [
        ("cotone", 1, 7),
        ("rapido-30", 2, 8),
        ("cotone-family-variant", 1, 7),
    ]


def test_rejects_default_outside_allowed_values():
    data = fixture_data()
    data["programs"][0]["allowed"]["temp"] = [20, 30]
    with pytest.raises(CatalogError, match=r"programs\[0\].*temp"):
        parse_catalog(data)


def test_rejects_missing_required_program_field():
    data = fixture_data()
    del data["programs"][0]["prcode"]
    with pytest.raises(CatalogError, match=r"programs\[0\].prcode"):
        parse_catalog(data)


def test_missing_catalog_has_actionable_import_message(tmp_path):
    with pytest.raises(CatalogUnavailableError, match="candy_import_programs.py"):
        load_catalog(tmp_path / "missing.json")


def test_atomic_save_keeps_valid_backup(tmp_path):
    path = tmp_path / "programs.json"
    path.write_bytes(FIXTURE.read_bytes())
    original = path.read_bytes()
    data = fixture_data()
    data["imported_at"] = "2026-08-01T13:00:00+02:00"
    save_catalog_atomic(parse_catalog(data), path)
    assert (tmp_path / "programs.json.bak").read_bytes() == original
    assert load_catalog(path).imported_at == "2026-08-01T13:00:00+02:00"


def test_failed_validation_does_not_touch_existing_file(tmp_path):
    path = tmp_path / "programs.json"
    path.write_bytes(FIXTURE.read_bytes())
    original = path.read_bytes()
    data = fixture_data()
    data["programs"][0]["prnm"] = None
    with pytest.raises(CatalogError):
        save_catalog_atomic(parse_catalog(data), path)
    assert path.read_bytes() == original


def test_validate_overrides_rejects_value_not_allowed():
    program = parse_catalog(fixture_data()).programs[0]
    with pytest.raises(OverrideError, match="temperatura"):
        validate_overrides(program, temp=95)


@pytest.mark.parametrize(
    ("path", "value"),
    [
        ("schema_version", True),
        ("programs[0].prnm", False),
        ("programs[0].defaults.steam", -1),
        ("programs[0].allowed.options[0]", "unknown"),
    ],
)
def test_rejects_invalid_strict_values(path, value):
    data = fixture_data()
    target = data
    keys = path.replace("[0]", ".0").split(".")
    for key in keys[:-1]:
        target = target[int(key)] if key.isdigit() else target[key]
    if keys[-1].isdigit():
        target[int(keys[-1])] = value
    else:
        target[keys[-1]] = value
    with pytest.raises(CatalogError, match=path.split(".")[0].replace("[", r"\[").replace("]", r"\]")):
        parse_catalog(data)


def test_round_trips_public_catalog_representation():
    catalog = parse_catalog(fixture_data())
    assert catalog_to_dict(catalog) == fixture_data()


def test_validate_overrides_allows_only_values_and_options_in_program_catalog():
    program = parse_catalog(fixture_data()).programs[0]
    validate_overrides(program, temp=30, spin=800, soil=3, options=("prewash",))
    with pytest.raises(OverrideError, match="opzione"):
        validate_overrides(program, options=("hygiene",))


def test_invalid_existing_catalog_is_not_backed_up(tmp_path):
    path = tmp_path / "programs.json"
    path.write_text("not json", encoding="utf-8")
    data = fixture_data()
    data["imported_at"] = "2026-08-01T14:00:00+02:00"
    save_catalog_atomic(parse_catalog(data), path)
    assert not (tmp_path / "programs.json.bak").exists()
    assert load_catalog(path).imported_at == "2026-08-01T14:00:00+02:00"


def test_load_catalog_wraps_invalid_json_as_unavailable_with_import_command(tmp_path):
    path = tmp_path / "programs.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(CatalogUnavailableError, match="candy_import_programs.py"):
        load_catalog(path)


def test_rejects_unknown_root_key():
    data = fixture_data()
    data["unexpected"] = "not part of schema version 1"
    with pytest.raises(CatalogError, match="unexpected"):
        parse_catalog(data)


@pytest.mark.parametrize(
    ("container", "path"),
    [
        (lambda data: data["appliance"], "appliance.unexpected"),
        (lambda data: data["programs"][0], "programs[0].unexpected"),
        (lambda data: data["programs"][0]["defaults"], "programs[0].defaults.unexpected"),
        (lambda data: data["programs"][0]["allowed"], "programs[0].allowed.unexpected"),
    ],
)
def test_rejects_unknown_nested_key(container, path):
    data = fixture_data()
    container(data)["unexpected"] = "not part of schema version 1"
    with pytest.raises(CatalogError, match=path.replace("[", r"\[").replace("]", r"\]")):
        parse_catalog(data)


def test_save_revalidates_invalid_dataclass_without_touching_existing_file(tmp_path):
    path = tmp_path / "programs.json"
    path.write_bytes(FIXTURE.read_bytes())
    original = path.read_bytes()
    valid_catalog = parse_catalog(fixture_data())
    invalid_catalog = replace(valid_catalog, schema_version=2)
    assert isinstance(invalid_catalog, ProgramCatalog)

    with pytest.raises(CatalogError, match="schema_version"):
        save_catalog_atomic(invalid_catalog, path)

    assert path.read_bytes() == original
