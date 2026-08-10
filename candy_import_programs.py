"""Importa e normalizza un catalogo programmi Candy senza persistere segreti."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from dataclasses import replace
from datetime import datetime
import getpass
from pathlib import Path
import re
import sys
import webbrowser

from candy_ciam import CiamAuthError, begin_ciam_login, complete_ciam_login
from candy_cloud import CandyCloudClient, CandyCloudError
from candy_programs import (
    OPTION_BITS,
    OPTION_KNOWN_MASKS,
    CatalogError,
    ProgramAllowed,
    ProgramCatalog,
    ProgramDefaults,
    ProgramDefinition,
    catalog_to_dict,
    is_startable_program,
    parse_catalog,
    save_catalog_atomic,
)


def unwrap_appliance(record: object) -> dict[str, object]:
    if not isinstance(record, dict):
        raise CatalogError("appliance: record non valido")
    value = record.get("appliance", record)
    if not isinstance(value, dict):
        raise CatalogError("appliance: oggetto non valido")
    return value


def _canonical_model(value: object) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(value).upper())


def _canonical_model_base(value: object) -> str:
    return _canonical_model(str(value).partition("/")[0])


def _is_washer(appliance: dict[str, object]) -> bool:
    appliance_type = _canonical_model(appliance.get("appliance_type", ""))
    model = _canonical_model(appliance.get("appliance_model", ""))
    return appliance_type in {"WM", "WASHER", "WASHINGMACHINE"} or model.startswith("BWM")


def find_matching_washers(
    records: Sequence[object], model_query: str = "BWM149PH7"
) -> list[dict[str, object]]:
    query = _canonical_model_base(model_query)
    if not query:
        raise CatalogError("model_query: codice modello non valido")
    appliances = [unwrap_appliance(record) for record in records]
    return [
        item
        for item in appliances
        if _is_washer(item)
        and _canonical_model_base(item.get("appliance_model", "")) == query
    ]


def available_washer_summaries(records: Sequence[object]) -> list[str]:
    summaries = []
    for record in records:
        item = unwrap_appliance(record)
        if _is_washer(item):
            summaries.append(
                f"{item.get('appliance_model')} {_masked_appliance_id(item)}"
            )
    return summaries


def mask_appliance_id(value: object) -> str:
    if value is None:
        raise CatalogError("appliance.id: identificatore non valido")
    raw = str(value)
    if not raw or len(raw) < 4:
        raise CatalogError("appliance.id: identificatore non valido")
    return "***" + raw[-4:]


def _masked_appliance_id(appliance: dict[str, object]) -> str:
    for key in ("id", "uid"):
        try:
            return mask_appliance_id(appliance.get(key))
        except CatalogError:
            pass
    raise CatalogError("appliance.id: identificatore non valido")


def choose_appliance(
    matches: Sequence[dict[str, object]], input_fn=input
) -> dict[str, object]:
    if not matches:
        raise CatalogError("Nessuna BWM 149PH7 trovata nell'account Candy.")
    if len(matches) == 1:
        return matches[0]
    for index, item in enumerate(matches, start=1):
        print(
            f"{index}. {item.get('appliance_model')} "
            f"{_masked_appliance_id(item)}"
        )
    try:
        selected = int(input_fn("Lavatrice da importare: ")) - 1
        if selected < 0:
            raise IndexError
        return matches[selected]
    except (ValueError, IndexError):
        raise CatalogError("Selezione lavatrice non valida.") from None


def flatten_parameters(program: dict[str, object]) -> dict[str, str]:
    raw_parameters = program.get("command_parameters")
    if not isinstance(raw_parameters, list):
        raise CatalogError("program.command_parameters: lista obbligatoria")
    parameters: dict[str, str] = {}
    seen_names: set[str] = set()
    for index, record in enumerate(raw_parameters):
        path = f"program.command_parameters[{index}]"
        if not isinstance(record, dict):
            raise CatalogError(f"{path}: record non valido")
        value = record.get("command_parameter", record)
        if not isinstance(value, dict):
            raise CatalogError(f"{path}: oggetto non valido")
        name = value.get("name")
        validation = value.get("validation")
        if not isinstance(name, str) or not name:
            raise CatalogError(f"{path}.name: stringa non vuota obbligatoria")
        # il cloud Candy puo' restituire validation come numero o stringa;
        # normalizziamo a stringa. None/assente => stringa vuota (skip).
        if validation is None:
            validation = ""
        elif isinstance(validation, bool):
            validation = "1" if validation else "0"
        elif isinstance(validation, (int, float)):
            validation = str(validation)
        elif not isinstance(validation, str):
            raise CatalogError(f"{path}.validation: tipo non valido")
        if name in seen_names:
            raise CatalogError(f"command_parameters.{name}: nome duplicato")
        seen_names.add(name)
        if validation == "":
            continue
        parameters[name] = validation
    return parameters


def _required_int(parameters: dict[str, str], name: str) -> int:
    try:
        return int(parameters[name])
    except (KeyError, TypeError, ValueError):
        raise CatalogError(f"command_parameters.{name}: intero obbligatorio") from None


def _allowed_options(parameters: dict[str, str]) -> tuple[str, ...]:
    try:
        mask = int(parameters.get("available_options", "0"))
        second_mask = int(parameters.get("available_options2", "0"))
    except (TypeError, ValueError):
        raise CatalogError(
            "command_parameters.available_options: intero non valido"
        ) from None
    # validazione per maschera: rifiuta solo bit davvero sconosciuti
    if mask < 0 or second_mask < 0:
        raise CatalogError("command_parameters.available_options: valore negativo")
    if mask & ~OPTION_KNOWN_MASKS[1]:
        raise CatalogError("command_parameters.available_options: bit sconosciuti (OptMsk1)")
    if second_mask & ~OPTION_KNOWN_MASKS[2]:
        raise CatalogError("command_parameters.available_options: bit sconosciuti (OptMsk2)")
    result = []
    for name, (which, bit) in OPTION_BITS.items():
        value = mask if which == 1 else second_mask
        if value & bit:
            result.append(name)
    return tuple(result)


def _allowed_ints(
    parameters: dict[str, str], name: str, default: int
) -> tuple[int, ...]:
    raw = parameters.get(name)
    if raw is None:
        return (default,)
    try:
        values = tuple(dict.fromkeys(int(item.strip()) for item in raw.split(",")))
    except ValueError:
        raise CatalogError(
            f"command_parameters.{name}: lista di interi non valida"
        ) from None
    if not values or default not in values:
        raise CatalogError(f"command_parameters.{name}: default non ammesso")
    return values


def normalize_program(program_record: object) -> ProgramDefinition:
    if not isinstance(program_record, dict):
        raise CatalogError("program: record non valido")
    raw = program_record.get("program", program_record)
    if not isinstance(raw, dict):
        raise CatalogError("program: oggetto non valido")
    parameters = flatten_parameters(raw)
    cloud_name = raw.get("name")
    if not isinstance(cloud_name, str) or not cloud_name:
        raise CatalogError("program.name: stringa obbligatoria")
    selector = _required_int(parameters, "selector_position")
    code = _required_int(parameters, "pr_code")
    temp = _required_int(parameters, "default_temperature")
    spin = _required_int(parameters, "default_spin_speed")
    soil = _required_int(parameters, "default_soil_level")
    short_name = cloud_name.removeprefix("DUAL_WM_WD_PROGRAM_NAME_")
    slug = re.sub(r"[^a-z0-9]+", "-", short_name.casefold()).strip("-")
    return ProgramDefinition(
        name=slug,
        prnm=selector,
        prcode=code,
        prstr=cloud_name,
        defaults=ProgramDefaults(
            temp=temp,
            spin=spin,
            soil=soil,
            steam=_required_int(parameters, "steam") if "steam" in parameters else 0,
            dry=_required_int(parameters, "dry") if "dry" in parameters else 0,
        ),
        allowed=ProgramAllowed(
            temp=_allowed_ints(parameters, "allowed_temperatures", temp),
            spin=_allowed_ints(parameters, "allowed_spin_speeds", spin),
            soil=_allowed_ints(parameters, "allowed_soil_levels", soil),
            options=_allowed_options(parameters),
        ),
        source="candy-cloud",
    )


def normalize_catalog(
    appliance: dict[str, object], *, imported_at: datetime
) -> ProgramCatalog:
    raw_programs = appliance.get("programs")
    if not isinstance(raw_programs, list) or not raw_programs:
        raise CatalogError("appliance.programs: lista non vuota obbligatoria")
    programs = []
    used_names: set[str] = set()
    for raw_program in raw_programs:
        program = normalize_program(raw_program)
        if not is_startable_program(program):
            continue
        if program.name in used_names:
            program = replace(program, name=f"{program.name}-{program.prnm}")
        if program.name in used_names:
            raise CatalogError(f"program.name duplicato: {program.name}")
        used_names.add(program.name)
        programs.append(program)
    if not programs:
        raise CatalogError("appliance.programs: nessun programma avviabile")
    model = appliance.get("appliance_model")
    if not isinstance(model, str) or not model:
        raise CatalogError("appliance.appliance_model: stringa obbligatoria")
    result = ProgramCatalog(
        schema_version=1,
        source="candy-cloud",
        appliance_model=model,
        appliance_id_masked=_masked_appliance_id(appliance),
        imported_at=imported_at.isoformat(),
        programs=tuple(programs),
    )
    return parse_catalog(catalog_to_dict(result))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Importa i programmi Candy dal cloud."
    )
    parser.add_argument("--output", type=Path, default=Path("programs.json"))
    parser.add_argument("--model", default="BWM 149PH7")
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    browser_open=webbrowser.open,
    callback_reader=getpass.getpass,
) -> int:
    args = build_parser().parse_args(argv)
    try:
        pending = begin_ciam_login()
        print("Apri questa pagina per accedere a Candy:")
        print(pending.authorization_url)
        try:
            opened = bool(browser_open(pending.authorization_url))
        except Exception:
            opened = False
        if not opened:
            print("Il browser non si è aperto: usa il collegamento mostrato sopra.")
        print(
            "Dopo l'accesso copia l'intero indirizzo candy://. "
            "È sensibile: non condividerlo e chiudi la scheda al termine."
        )
        try:
            callback_url = callback_reader("Callback Candy (input nascosto): ")
        except (EOFError, KeyboardInterrupt):
            raise CiamAuthError("Accesso Candy annullato.") from None
        id_token = complete_ciam_login(pending, callback_url)
        client = CandyCloudClient(id_token)
        records = client.fetch_appliances()
        matches = find_matching_washers(records, args.model)
        if not matches:
            available = available_washer_summaries(records)
            suffix = "; trovate: " + ", ".join(available) if available else ""
            raise CatalogError(
                f"Nessuna {args.model} trovata nell'account Candy{suffix}."
            )
        appliance = choose_appliance(matches)
        catalog = normalize_catalog(
            appliance, imported_at=datetime.now().astimezone()
        )
        print(f"{catalog.appliance_model} {catalog.appliance_id_masked}")
        print(f"Programmi importabili: {len(catalog.programs)}")
        for program in catalog.programs:
            print(f"- {program.name}: {program.prstr}")
        save_catalog_atomic(catalog, args.output)
        print(f"Catalogo salvato in {args.output}")
        return 0
    except (CiamAuthError, CandyCloudError) as error:
        print(str(error), file=sys.stderr)
        return 3
    except CatalogError as error:
        print(str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
