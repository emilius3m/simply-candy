"""Catalogo dei programmi Candy validato prima di ogni uso o persistenza."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import json
import os
from pathlib import Path


# Opzioni di lavaggio. Il protocollo Candy usa DUE maschere:
#   OptMsk1 (bit 0-7) e OptMsk2 (bit 0-N della seconda maschera).
# OPTION_BITS mappa nome -> (maschera, bit). Valori ricavati dal codice
# decompilato dell'app (Command.Param.OPTION_MASK_1/2, isZoom() ecc.).
OPTION_BITS = {
    # --- OptMsk1 (mask 1) ---
    "prewash":       (1, 1),
    "hygiene":       (1, 2),
    "anti_crease":   (1, 4),
    "good_night":    (1, 8),
    "extra_rinse_1": (1, 16),
    "extra_rinse_2": (1, 32),
    "extra_rinse_3": (1, 64),
    "aquaplus":      (1, 128),
    # --- OptMsk2 (mask 2) ---
    "zoom":          (2, 1),
}

# valori noti per ciascuna maschera (per la validazione dei bit sconosciuti)
OPTION_KNOWN_MASKS = {
    1: sum(bit for m, bit in OPTION_BITS.values() if m == 1),
    2: sum(bit for m, bit in OPTION_BITS.values() if m == 2),
}

# source ammesse: "candy-cloud" (importato dal cloud) e "local-verified"
# (programma letto dallo stato reale della macchina durante l'esecuzione).
ALLOWED_SOURCES = ("candy-cloud", "local-verified")
NON_STARTABLE_PRSTRS = frozenset({"DUAL_WM_WD_OFF"})


class CatalogError(ValueError):
    """Base per errori di schema e mapping."""


class CatalogUnavailableError(CatalogError):
    """File assente, illeggibile o invalido."""


class UnknownProgramError(CatalogError):
    """Nome non presente nel catalogo valido."""


class OverrideError(CatalogError):
    """Parametro di avvio non ammesso dal catalogo."""


@dataclass(frozen=True)
class ProgramDefaults:
    temp: int
    spin: int
    soil: int
    steam: int
    dry: int


@dataclass(frozen=True)
class ProgramAllowed:
    temp: Sequence[int]
    spin: Sequence[int]
    soil: Sequence[int]
    options: Sequence[str]


@dataclass(frozen=True)
class ProgramDefinition:
    name: str
    prnm: int
    prcode: int
    prstr: str
    defaults: ProgramDefaults
    allowed: ProgramAllowed
    source: str


@dataclass(frozen=True)
class ProgramCatalog:
    schema_version: int
    source: str
    appliance_model: str
    appliance_id_masked: str
    imported_at: str
    programs: Sequence[ProgramDefinition]

    def by_name(self, name: str) -> ProgramDefinition:
        for program in self.programs:
            if program.name == name:
                return program
        raise UnknownProgramError(f"Programma sconosciuto: {name}")


def is_startable_program(program: ProgramDefinition) -> bool:
    return program.prstr not in NON_STARTABLE_PRSTRS


def startable_programs(catalog: ProgramCatalog) -> tuple[ProgramDefinition, ...]:
    return tuple(program for program in catalog.programs if is_startable_program(program))


def require_startable_program(program: ProgramDefinition) -> ProgramDefinition:
    if not is_startable_program(program):
        raise OverrideError(f"Programma tecnico non avviabile: {program.prstr}")
    return program


def _error(path: str, message: str) -> CatalogError:
    return CatalogError(f"{path}: {message}")


def _required(mapping: Mapping, key: str, path: str):
    if key not in mapping:
        raise _error(f"{path}.{key}" if path else key, "campo obbligatorio mancante")
    return mapping[key]


def _mapping(value, path: str) -> Mapping:
    if not isinstance(value, Mapping):
        raise _error(path, "deve essere un oggetto JSON")
    return value


def _only_keys(mapping: Mapping, allowed: set[str], path: str) -> None:
    for key in mapping:
        if key not in allowed:
            field_path = f"{path}.{key}" if path else str(key)
            raise _error(field_path, "campo non previsto")


def _string(value, path: str, *, nonempty: bool = False) -> str:
    if not isinstance(value, str):
        raise _error(path, "deve essere una stringa")
    if nonempty and not value:
        raise _error(path, "non deve essere vuoto")
    return value


def _integer(value, path: str, *, nonnegative: bool = False) -> int:
    if type(value) is not int:
        raise _error(path, "deve essere un intero JSON")
    if nonnegative and value < 0:
        raise _error(path, "deve essere non negativo")
    return value


def _slug(value, path: str) -> str:
    name = _string(value, path, nonempty=True)
    parts = name.split("-")
    if any(not part or not part.isascii() or not part.isalnum() or part != part.lower() for part in parts):
        raise _error(path, "deve essere uno slug non vuoto")
    return name


def _int_values(value, path: str) -> tuple[int, ...]:
    if not isinstance(value, list):
        raise _error(path, "deve essere una lista JSON")
    values = tuple(_integer(item, f"{path}[{index}]", nonnegative=True) for index, item in enumerate(value))
    if not values:
        raise _error(path, "non deve essere vuota")
    if len(set(values)) != len(values):
        raise _error(path, "non deve contenere duplicati")
    return values


def _option_values(value, path: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise _error(path, "deve essere una lista JSON")
    options = tuple(_string(item, f"{path}[{index}]", nonempty=True) for index, item in enumerate(value))
    if len(set(options)) != len(options):
        raise _error(path, "non deve contenere duplicati")
    for index, option in enumerate(options):
        if option not in OPTION_BITS:
            raise _error(f"{path}[{index}]", "opzione sconosciuta")
    return options


def _parse_program(value, index: int) -> ProgramDefinition:
    path = f"programs[{index}]"
    data = _mapping(value, path)
    _only_keys(data, {"name", "prnm", "prcode", "prstr", "defaults", "allowed", "source"}, path)
    defaults_data = _mapping(_required(data, "defaults", path), f"{path}.defaults")
    allowed_data = _mapping(_required(data, "allowed", path), f"{path}.allowed")
    _only_keys(defaults_data, {"temp", "spin", "soil", "steam", "dry"}, f"{path}.defaults")
    _only_keys(allowed_data, {"temp", "spin", "soil", "options"}, f"{path}.allowed")

    defaults = ProgramDefaults(
        temp=_integer(_required(defaults_data, "temp", f"{path}.defaults"), f"{path}.defaults.temp", nonnegative=True),
        spin=_integer(_required(defaults_data, "spin", f"{path}.defaults"), f"{path}.defaults.spin", nonnegative=True),
        soil=_integer(_required(defaults_data, "soil", f"{path}.defaults"), f"{path}.defaults.soil", nonnegative=True),
        steam=_integer(_required(defaults_data, "steam", f"{path}.defaults"), f"{path}.defaults.steam"),
        dry=_integer(_required(defaults_data, "dry", f"{path}.defaults"), f"{path}.defaults.dry"),
    )
    # steam: livelli Candy dal codice decompilato (Command.setSteam):
    #   0 = off, 1 = steam fisso, 5 = steam on/off. Accettiamo anche altri
    #   valori non negativi per robustezza (alcuni modelli usano 2/3/4).
    if defaults.steam < 0:
        raise _error(f"{path}.defaults.steam", "deve essere non negativo")
    # dry: livelli asciugatura (0-4 nei modelli washer-dryer, 0 se non supportato)
    if defaults.dry < 0:
        raise _error(f"{path}.defaults.dry", "deve essere non negativo")

    allowed = ProgramAllowed(
        temp=_int_values(_required(allowed_data, "temp", f"{path}.allowed"), f"{path}.allowed.temp"),
        spin=_int_values(_required(allowed_data, "spin", f"{path}.allowed"), f"{path}.allowed.spin"),
        soil=_int_values(_required(allowed_data, "soil", f"{path}.allowed"), f"{path}.allowed.soil"),
        options=_option_values(_required(allowed_data, "options", f"{path}.allowed"), f"{path}.allowed.options"),
    )
    for field in ("temp", "spin", "soil"):
        if getattr(defaults, field) not in getattr(allowed, field):
            raise _error(f"{path}.defaults.{field}", "il default non è fra i valori ammessi")

    source = _string(_required(data, "source", path), f"{path}.source", nonempty=True)
    if source not in ALLOWED_SOURCES:
        raise _error(f"{path}.source", f"deve essere una di: {', '.join(ALLOWED_SOURCES)}")
    return ProgramDefinition(
        name=_slug(_required(data, "name", path), f"{path}.name"),
        prnm=_integer(_required(data, "prnm", path), f"{path}.prnm", nonnegative=True),
        prcode=_integer(_required(data, "prcode", path), f"{path}.prcode", nonnegative=True),
        prstr=_string(_required(data, "prstr", path), f"{path}.prstr", nonempty=True),
        defaults=defaults,
        allowed=allowed,
        source=source,
    )


def parse_catalog(data) -> ProgramCatalog:
    """Converte dati JSON nel catalogo immutabile, rifiutando ogni schema ambiguo."""
    root = _mapping(data, "$")
    _only_keys(root, {"schema_version", "source", "appliance", "imported_at", "programs"}, "")
    schema_version = _integer(_required(root, "schema_version", ""), "schema_version")
    if schema_version != 1:
        raise _error("schema_version", "deve essere 1")
    source = _string(_required(root, "source", ""), "source", nonempty=True)
    if source not in ALLOWED_SOURCES:
        raise _error("source", f"deve essere una di: {', '.join(ALLOWED_SOURCES)}")

    appliance = _mapping(_required(root, "appliance", ""), "appliance")
    _only_keys(appliance, {"model", "id_masked"}, "appliance")
    programs_value = _required(root, "programs", "")
    if not isinstance(programs_value, list):
        raise _error("programs", "deve essere una lista JSON")
    if not programs_value:
        raise _error("programs", "deve contenere almeno un programma")

    programs = tuple(_parse_program(item, index) for index, item in enumerate(programs_value))
    names = [program.name for program in programs]
    if len(set(names)) != len(names):
        raise _error("programs", "nomi duplicati")
    # Nota: coppie prnm/prcode duplicate sono ammesse perché alcuni modelli
    # (es. Candy BWM 149PH7) usano la stessa coppia per programmi della
    # stessa famiglia che differiscono solo per altri parametri (es. SLevel).
    # Si richiede invece che nome + defaults siano univoci.
    signatures = [
        (program.name, program.defaults.temp, program.defaults.spin,
         program.defaults.soil, program.defaults.steam, program.defaults.dry)
        for program in programs
    ]
    if len(set(signatures)) != len(signatures):
        raise _error("programs", "programmi con nome e defaults identici (duplicati)")

    return ProgramCatalog(
        schema_version=schema_version,
        source=source,
        appliance_model=_string(_required(appliance, "model", "appliance"), "appliance.model", nonempty=True),
        appliance_id_masked=_string(_required(appliance, "id_masked", "appliance"), "appliance.id_masked", nonempty=True),
        imported_at=_string(_required(root, "imported_at", ""), "imported_at", nonempty=True),
        programs=programs,
    )


def _unavailable(path: Path, reason: str) -> CatalogUnavailableError:
    return CatalogUnavailableError(
        f"Catalogo non disponibile: {path} ({reason}). Esegui candy_import_programs.py per importarlo di nuovo."
    )


def load_catalog(path) -> ProgramCatalog:
    """Carica un catalogo o espone un unico errore operativo e azionabile."""
    catalog_path = Path(path)
    try:
        with catalog_path.open("r", encoding="utf-8") as file:
            data = json.load(file)
        return parse_catalog(data)
    except CatalogUnavailableError:
        raise
    except CatalogError as error:
        raise _unavailable(catalog_path, "schema non valido") from error
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise _unavailable(catalog_path, "file assente, illeggibile o JSON non valido") from error


def catalog_to_dict(catalog: ProgramCatalog) -> dict:
    """Restituisce la rappresentazione JSON canonica del catalogo validato."""
    if not isinstance(catalog, ProgramCatalog):
        raise _error("catalog", "deve essere un ProgramCatalog")
    return {
        "schema_version": catalog.schema_version,
        "source": catalog.source,
        "appliance": {
            "model": catalog.appliance_model,
            "id_masked": catalog.appliance_id_masked,
        },
        "imported_at": catalog.imported_at,
        "programs": [
            {
                "name": program.name,
                "prnm": program.prnm,
                "prcode": program.prcode,
                "prstr": program.prstr,
                "defaults": {
                    "temp": program.defaults.temp,
                    "spin": program.defaults.spin,
                    "soil": program.defaults.soil,
                    "steam": program.defaults.steam,
                    "dry": program.defaults.dry,
                },
                "allowed": {
                    "temp": list(program.allowed.temp),
                    "spin": list(program.allowed.spin),
                    "soil": list(program.allowed.soil),
                    "options": list(program.allowed.options),
                },
                "source": program.source,
            }
            for program in catalog.programs
        ],
    }


def _write_synced(path: Path, payload: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as file:
            file.write(payload)
            file.flush()
            os.fsync(file.fileno())
    except BaseException:
        try:
            os.unlink(path)
        except OSError:
            pass
        raise


def _temporary_path(path: Path, suffix: str) -> Path:
    for number in range(1000):
        candidate = path.with_name(f".{path.name}.{os.getpid()}.{number}{suffix}")
        if not candidate.exists():
            return candidate
    raise _error(str(path), "impossibile creare un file temporaneo univoco")


def _valid_existing_bytes(path: Path) -> bytes | None:
    try:
        original = path.read_bytes()
        parse_catalog(json.loads(original))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, CatalogError):
        return None
    return original


def save_catalog_atomic(catalog: ProgramCatalog, path) -> None:
    """Valida e sostituisce il catalogo senza lasciare il target assente."""
    normalized = parse_catalog(catalog_to_dict(catalog))
    catalog_path = Path(path)
    payload = (json.dumps(catalog_to_dict(normalized), ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    temporary = _temporary_path(catalog_path, ".tmp")
    backup_temporary = None
    try:
        _write_synced(temporary, payload)
        original = _valid_existing_bytes(catalog_path)
        if original is not None:
            backup_path = catalog_path.with_name(f"{catalog_path.name}.bak")
            backup_temporary = _temporary_path(backup_path, ".tmp")
            _write_synced(backup_temporary, original)
            os.replace(backup_temporary, backup_path)
            backup_temporary = None
        os.replace(temporary, catalog_path)
    except OSError as error:
        raise _error(str(catalog_path), "salvataggio atomico non riuscito") from error
    finally:
        for candidate in (temporary, backup_temporary):
            if candidate is not None:
                try:
                    os.unlink(candidate)
                except OSError:
                    pass


def validate_overrides(program: ProgramDefinition, *, temp=None, spin=None, soil=None, options=()) -> None:
    """Rifiuta override non ammessi dal programma selezionato."""
    if not isinstance(program, ProgramDefinition):
        raise OverrideError("Programma non valido")
    for value, allowed, label in (
        (temp, program.allowed.temp, "temperatura"),
        (spin, program.allowed.spin, "centrifuga"),
        (soil, program.allowed.soil, "livello di sporco"),
    ):
        if value is not None and (type(value) is not int or value not in allowed):
            raise OverrideError(f"{label} non ammessa per il programma {program.name}")
    if isinstance(options, str):
        raise OverrideError("opzioni non valide per il programma")
    try:
        selected_options = tuple(options)
    except TypeError as error:
        raise OverrideError("opzioni non valide per il programma") from error
    for option in selected_options:
        if not isinstance(option, str) or option not in program.allowed.options:
            raise OverrideError(f"opzione non ammessa per il programma {program.name}")
