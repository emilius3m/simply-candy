# BWM 149PH7 Cloud Program Import Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Importare dall'account Candy simply-Fi il catalogo reale della BWM 149PH7 e usare quel catalogo, con validazione fail-closed, per gli avvii locali da CLI e interfaccia web.

**Architecture:** Separare il client cloud, il modello/persistenza del catalogo e il protocollo locale. `candy_import_programs.py` autentica soltanto in memoria, normalizza la risposta cloud e salva atomicamente `programs.json`; `candy_sendprogram.py` e `candy_web.py` caricano entrambi lo stesso file tramite `candy_programs.py`. Il payload di avvio segue il formato verificato nell'app Android Candy simply-Fi 3.14.1: selettore cloud in `PrNm`, solo override ammessi, velocità convertita da rpm a centinaia di rpm e opzioni in `OptMsk`.

**Tech Stack:** Python 3.12+, `requests`, FastAPI/Uvicorn già usati dal progetto, `pytest`, `httpx`, JSON standard library, filesystem atomico con `os.replace`.

**Spec:** `docs/superpowers/specs/2026-08-01-bwm-149ph7-cloud-program-import-design.md`

## Global Constraints

- Non inviare mai richieste `Write=1` durante importazione o test.
- Email e password sono ammesse solo tramite prompt; la password usa `getpass.getpass()` e non esistono flag CLI o variabili d'ambiente equivalenti.
- Token, password, risposta OAuth completa e identificatore completo dell'elettrodomestico non vanno su disco né nei log.
- Nessun fallback alla tabella dimostrativa esistente: catalogo mancante/invalido significa invio bloccato.
- I valori numerici di programma provengono dalla risposta cloud. Se un insieme di valori ammessi non è esplicito, l'unico valore selezionabile è il default cloud.
- Il protocollo locale usa la forma dell'app Android verificata: `Write=1&Pa=0&Sel=0&PrNm=1&StSt=1`, sostituendo `1` col selettore importato, poi solo gli override e `OptMsk`.
- I test cloud usano sessioni simulate; la verifica finale può chiamare il cloud solo su azione esplicita dell'utente e non avvia cicli.
- La directory corrente non è un repository Git. I comandi di commit sotto sono checkpoint esatti da eseguire solo se/ quando il progetto viene inizializzato come repository; non inizializzare Git come effetto collaterale di questo lavoro.

## File Structure

| File | Azione | Responsabilità |
|---|---|---|
| `requirements.txt` | crea | Dipendenze runtime riproducibili |
| `requirements-dev.txt` | crea | Dipendenze test |
| `.gitignore` | crea | Esclude credenziali/cache/catalogo specifico del dispositivo |
| `candy_programs.py` | crea | Dataclass, validazione, lookup, lettura e scrittura atomica |
| `candy_cloud.py` | crea | OAuth Candy e download read-only degli elettrodomestici |
| `candy_import_programs.py` | crea | Selezione BWM, normalizzazione e CLI interattiva |
| `candy_sendprogram.py` | modifica | Catalogo condiviso, validazione override, payload selettore |
| `candy_web.py` | modifica | Catalogo condiviso e blocco server-side dei valori non ammessi |
| `candy_learn_programs.py` | modifica | Marca il flusso manopola come legacy/non adatto alla BWM 149PH7 |
| `README.md` | crea | Installazione, importazione, dry-run, avvio UI e sicurezza |
| `tests/fixtures/cloud_appliances.json` | crea | Risposta cloud minima realistica, solo dati fittizi |
| `tests/fixtures/programs_valid.json` | crea | Catalogo normalizzato valido |
| `tests/test_programs.py` | crea | Schema, duplicati, coerenza e persistenza |
| `tests/test_cloud.py` | crea | OAuth, header, errori sanitizzati e fetch read-only |
| `tests/test_import.py` | crea | Selezione e normalizzazione appliance/programmi |
| `tests/test_sendprogram.py` | crea | Payload ufficiale e blocco prima della rete |
| `tests/test_web.py` | crea | Parità UI/CLI e validazione API |

---

### Task 1: Rendere riproducibile l'ambiente di test

**Files:**

- Create: `requirements.txt`
- Create: `requirements-dev.txt`
- Create: `.gitignore`

**Interfaces:**

- Consumes: Python 3.12 già disponibile nel workspace.
- Produces: ambiente con `requests`, `fastapi`, `uvicorn`, `pytest`, `httpx`; regole di esclusione per file locali sensibili.

- [ ] **Step 1: Scrivere i manifest minimi**

`requirements.txt`:

```text
requests>=2.32,<3
fastapi>=0.116,<1
uvicorn>=0.35,<1
```

`requirements-dev.txt`:

```text
-r requirements.txt
pytest>=8.4,<9
httpx>=0.28,<1
```

`.gitignore`:

```gitignore
__pycache__/
.pytest_cache/
.venv/
*.pyc
candy_key.cache
programs.json
programs.json.bak
programs.json.tmp
.programs.json.*.tmp
```

- [ ] **Step 2: Installare le dipendenze nella Python usata dal progetto**

Run:

```powershell
python -m pip install -r requirements-dev.txt
```

Expected: exit code `0`; `requests`, `fastapi`, `uvicorn`, `pytest` e `httpx` risultano installati.

- [ ] **Step 3: Verificare il test runner**

Run:

```powershell
python -m pytest --version
```

Expected: output `pytest 8.x` e exit code `0`.

- [ ] **Step 4: Checkpoint Git condizionale**

```powershell
git add requirements.txt requirements-dev.txt .gitignore
git commit -m "chore: add reproducible candy tooling dependencies"
```

Expected: eseguire soltanto se esiste già `.git`; altrimenti annotare il checkpoint e proseguire.

---

### Task 2: Definire il catalogo normalizzato fail-closed

**Files:**

- Create: `candy_programs.py`
- Create: `tests/fixtures/programs_valid.json`
- Create: `tests/test_programs.py`

**Interfaces:**

- Consumes: `Path`, `dataclass`, `json`, `os` della standard library.
- Produces: `OPTION_BITS`, `CatalogError`, `CatalogUnavailableError`, `UnknownProgramError`, `OverrideError`, `ProgramDefaults`, `ProgramAllowed`, `ProgramDefinition`, `ProgramCatalog`, `parse_catalog(data)`, `load_catalog(path)`, `catalog_to_dict(catalog)`, `save_catalog_atomic(catalog, path)`, `validate_overrides(program, *, temp=None, spin=None, soil=None, options=())`.

- [ ] **Step 1: Scrivere i test che descrivono lo schema**

In `tests/test_programs.py`, usare test concreti basati sul fixture:

```python
import copy
import json
from pathlib import Path

import pytest

from candy_programs import (
    CatalogError,
    load_catalog,
    parse_catalog,
    save_catalog_atomic,
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


def test_rejects_duplicate_name_and_prnm_prcode_pair():
    data = fixture_data()
    data["programs"].append(copy.deepcopy(data["programs"][0]))
    with pytest.raises(CatalogError, match="duplicat"):
        parse_catalog(data)


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
    with pytest.raises(CatalogError, match="candy_import_programs.py"):
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
    with pytest.raises(CatalogError, match="temperatura"):
        validate_overrides(program, temp=95)
```

Creare `tests/fixtures/programs_valid.json` con questo contenuto interamente fittizio:

```json
{
  "schema_version": 1,
  "source": "candy-cloud",
  "appliance": {
    "model": "BWM 149PH7",
    "id_masked": "***1234"
  },
  "imported_at": "2026-08-01T12:00:00+02:00",
  "programs": [
    {
      "name": "cotone",
      "prnm": 1,
      "prcode": 7,
      "prstr": "DUAL_WM_WD_PROGRAM_NAME_COTONE",
      "defaults": {"temp": 40, "spin": 1000, "soil": 2, "steam": 0, "dry": 0},
      "allowed": {
        "temp": [30, 40],
        "spin": [800, 1000],
        "soil": [2, 3],
        "options": ["prewash"]
      },
      "source": "candy-cloud"
    },
    {
      "name": "rapido-30",
      "prnm": 2,
      "prcode": 8,
      "prstr": "DUAL_WM_WD_PROGRAM_NAME_RAPID_30",
      "defaults": {"temp": 30, "spin": 800, "soil": 2, "steam": 0, "dry": 0},
      "allowed": {"temp": [30], "spin": [800], "soil": [2], "options": []},
      "source": "candy-cloud"
    }
  ]
}
```

- [ ] **Step 2: Eseguire i test e confermare il fallimento**

Run:

```powershell
python -m pytest tests/test_programs.py -q
```

Expected: FAIL in import con `ModuleNotFoundError: No module named 'candy_programs'`.

- [ ] **Step 3: Implementare modello e validazione**

In `candy_programs.py` creare dataclass immutabili:

```python
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
```

Importare `Sequence` da `collections.abc`. Conservare internamente tuple, anche se l'interfaccia è dichiarata come sequenza immutabile. Implementare inoltre le funzioni pubbliche elencate nel blocco **Interfaces** e definire una sola tabella condivisa per importatore e sender:

```python
OPTION_BITS = {
    "prewash": 1,
    "hygiene": 2,
    "anti_crease": 4,
    "good_night": 8,
    "extra_rinse_1": 16,
    "extra_rinse_2": 32,
    "extra_rinse_3": 64,
    "aquaplus": 128,
}
```

Regole esatte:

- accettare solo `schema_version == 1`, `source == "candy-cloud"` e almeno un programma;
- richiedere tipi JSON stretti (`bool` non vale come `int`);
- richiedere `name` slug non vuoto, `prstr` non vuoto e interi non negativi per `prnm`/`prcode`;
- richiedere unicità di `name` e coppia `(prnm, prcode)`;
- richiedere che ogni default `temp`, `spin`, `soil` compaia nel relativo `allowed`;
- ammettere soltanto `steam` e `dry` in `{0, 1}`;
- prima validare completamente in memoria, poi scrivere un file temporaneo univoco nella stessa directory e fare `flush()` + `os.fsync()`; se il vecchio file è valido, copiarlo in un backup temporaneo, sincronizzarlo e promuoverlo con `os.replace()` a `.bak`; infine promuovere il nuovo file con `os.replace()` senza una finestra in cui il target principale manca;
- se il vecchio file è invalido, non promuoverlo a backup ma non sovrascriverlo finché il nuovo catalogo non è stato validato;
- gli errori devono includere il percorso JSON del campo, mai il documento completo.
- `load_catalog` converte assenza, errore I/O, JSON non valido e schema non valido in `CatalogUnavailableError` con il comando di importazione; `validate_overrides` usa `OverrideError`; `parse_catalog` conserva `CatalogError` per schema/mapping.

- [ ] **Step 4: Eseguire i test mirati**

Run:

```powershell
python -m pytest tests/test_programs.py -q
```

Expected: tutti PASS.

- [ ] **Step 5: Checkpoint Git condizionale**

```powershell
git add candy_programs.py tests/fixtures/programs_valid.json tests/test_programs.py
git commit -m "feat: add validated candy program catalog"
```

---

### Task 3: Implementare il client Candy cloud senza persistenza di segreti

**Files:**

- Create: `candy_cloud.py`
- Create: `tests/test_cloud.py`

**Interfaces:**

- Consumes: `requests.Session`, endpoint OAuth e appliance Candy.
- Produces: `CandyCloudError`; `CandyCloudClient.authenticate(email, password) -> None`; `CandyCloudClient.fetch_appliances() -> list[dict[str, object]]`.

- [ ] **Step 1: Scrivere test con una sessione HTTP finta**

In `tests/test_cloud.py` creare una sessione HTTP deterministica e testare richieste ed errori senza rete:

```python
import requests
import pytest

from candy_cloud import APPLIANCES_URL, TOKEN_URL, CandyCloudClient, CandyCloudError


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
    def __init__(self, token_response=None, appliance_response=None):
        self.headers = {}
        self.calls = []
        self.token_response = token_response or FakeResponse({"access_token": "secret-token"})
        self.appliance_response = appliance_response or FakeResponse([])

    def post(self, url, *, data, timeout):
        self.calls.append(("POST", url, data, timeout))
        return self.token_response

    def get(self, url, *, timeout):
        self.calls.append(("GET", url, None, timeout))
        return self.appliance_response


def test_authenticate_posts_password_grant_to_oauth_token():
    session = FakeSession()
    CandyCloudClient(session=session).authenticate("me@example.test", "p-ass")
    method, url, form, timeout = session.calls[0]
    assert (method, url, timeout) == ("POST", TOKEN_URL, (5.0, 20.0))
    assert form["grant_type"] == "password"
    assert form["username"] == "me@example.test"
    assert form["password"] == "p-ass"
    assert form["client_id"] and form["client_secret"]


def test_authenticated_headers_match_android_client_contract():
    session = FakeSession()
    CandyCloudClient(session=session).authenticate("me@example.test", "p-ass")
    assert session.headers["Authorization"] == "Bearer secret-token"
    assert session.headers["Salesforce-Auth"] == "1"
    assert session.headers["Brand"] == "0"
    assert session.headers["Device-Family"] == "android"
    assert session.headers["Device-Language"] == "it"


def test_fetch_appliances_is_read_only():
    session = FakeSession(appliance_response=FakeResponse([{"appliance": {"id": "1234"}}]))
    client = CandyCloudClient(session=session)
    client.authenticate("me@example.test", "p-ass")
    assert client.fetch_appliances() == [{"appliance": {"id": "1234"}}]
    assert session.calls[-1][:2] == ("GET", APPLIANCES_URL)
    assert all("Write=" not in str(call) for call in session.calls)


@pytest.mark.parametrize("response", [FakeResponse({}, 401), FakeResponse({}, 403)])
def test_bad_credentials_raise_sanitized_error(response):
    with pytest.raises(CandyCloudError) as caught:
        CandyCloudClient(session=FakeSession(token_response=response)).authenticate(
            "me@example.test", "p-ass"
        )
    assert "Credenziali Candy rifiutate" in str(caught.value)
    assert "p-ass" not in str(caught.value)


def test_malformed_json_is_rejected():
    session = FakeSession(appliance_response=FakeResponse(ValueError("bad json")))
    client = CandyCloudClient(session=session)
    client.authenticate("me@example.test", "p-ass")
    with pytest.raises(CandyCloudError, match="incompatibile"):
        client.fetch_appliances()
```

Aggiungere anche il caso timeout sanitizzato:

```python
def test_timeout_is_sanitized():
    class TimeoutSession(FakeSession):
        def post(self, url, *, data, timeout):
            raise requests.Timeout("token-in-body")

    with pytest.raises(CandyCloudError) as caught:
        CandyCloudClient(session=TimeoutSession()).authenticate(
            "me@example.test", "p-ass"
        )
    assert "Cloud Candy non raggiungibile" in str(caught.value)
    assert "token-in-body" not in str(caught.value)
    assert "p-ass" not in str(caught.value)
```

Il solo POST deve essere `/oauth/token`; il catalogo usa GET; nessuna URL locale e nessun parametro `Write` compare nelle chiamate.

- [ ] **Step 2: Eseguire i test e confermare il fallimento**

Run:

```powershell
python -m pytest tests/test_cloud.py -q
```

Expected: FAIL in import con `ModuleNotFoundError: No module named 'candy_cloud'`.

- [ ] **Step 3: Implementare il client**

In `candy_cloud.py` implementare questa struttura completa; i due identificatori sono quelli pubblici incorporati nell'APK mobile, non segreti dell'utente:

```python
from __future__ import annotations

import requests

BASE_URL = "https://simply-fi.herokuapp.com"
TOKEN_URL = f"{BASE_URL}/oauth/token"
APPLIANCES_URL = f"{BASE_URL}/api/v1/appliances.json?with_programs=1"
ANDROID_CLIENT_ID = "d205fbf6f2f595eb041f991054f4d7c8de306a43c2db570cff9f16e7239ec969"
ANDROID_CLIENT_SECRET = "98e7b313a567d0c18b8554ce5517bb991bca3bba234b27e592a11b66bce1c03e"


class CandyCloudError(RuntimeError):
    """Errore cloud già sanitizzato per la CLI."""


class CandyCloudClient:
    def __init__(self, session: requests.Session | None = None,
                 timeout: tuple[float, float] = (5.0, 20.0)):
        self._session = session or requests.Session()
        self._timeout = timeout
        self._authenticated = False

    def authenticate(self, email: str, password: str) -> None:
        form = {
            "grant_type": "password",
            "client_id": ANDROID_CLIENT_ID,
            "client_secret": ANDROID_CLIENT_SECRET,
            "username": email,
            "password": password,
        }
        try:
            response = self._session.post(TOKEN_URL, data=form, timeout=self._timeout)
            if response.status_code in {401, 403}:
                raise CandyCloudError("Credenziali Candy rifiutate.")
            response.raise_for_status()
            payload = response.json()
            token = payload.get("access_token") if isinstance(payload, dict) else None
            if not isinstance(token, str) or not token:
                raise CandyCloudError("Risposta di autenticazione Candy incompatibile.")
        except CandyCloudError:
            raise
        except (requests.RequestException, ValueError):
            raise CandyCloudError(
                "Cloud Candy non raggiungibile o risposta incompatibile."
            ) from None
        self._session.headers.update({
            "Authorization": f"Bearer {token}",
            "Salesforce-Auth": "1",
            "Brand": "0",
            "Device-Family": "android",
            "Device-Language": "it",
            "App-Version-Name": "3.14.1",
        })
        self._authenticated = True

    def fetch_appliances(self) -> list[dict[str, object]]:
        if not self._authenticated:
            raise CandyCloudError("Autenticazione Candy necessaria.")
        try:
            response = self._session.get(APPLIANCES_URL, timeout=self._timeout)
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError):
            raise CandyCloudError(
                "Cloud Candy non raggiungibile o risposta incompatibile."
            ) from None
        if not isinstance(payload, list) or not all(isinstance(item, dict) for item in payload):
            raise CandyCloudError("Risposta elenco elettrodomestici incompatibile.")
        return payload
```

Dettagli vincolanti:

- il form OAuth contiene `grant_type=password`, `client_id`, `client_secret`, `username`, `password` come nel client Android Candy 3.14.1;
- centralizzare client ID e client secret mobile in costanti del modulo con commento che sono identificatori pubblici distribuiti nell'APK, non credenziali utente;
- dopo il login impostare `Authorization: Bearer <token>`, `Salesforce-Auth: 1`, `Brand: 0`, `Device-Family: android`, `Device-Language: it`, `App-Version-Name: 3.14.1`;
- non esporre proprietà pubbliche contenenti password, token o risposta OAuth;
- usare `raise_for_status()`, timeout esplicito e messaggi distinti per credenziali rifiutate, cloud irraggiungibile e risposta incompatibile;
- non incorporare response body nei messaggi di errore;
- `fetch_appliances()` accetta soltanto una radice JSON array e restituisce i record senza modificarli.

- [ ] **Step 4: Eseguire i test mirati**

Run:

```powershell
python -m pytest tests/test_cloud.py -q
```

Expected: tutti PASS; nessun test usa Internet.

- [ ] **Step 5: Checkpoint Git condizionale**

```powershell
git add candy_cloud.py tests/test_cloud.py
git commit -m "feat: add in-memory candy cloud client"
```

---

### Task 4: Normalizzare appliance e programmi BWM dalla risposta cloud

**Files:**

- Create: `candy_import_programs.py`
- Create: `tests/fixtures/cloud_appliances.json`
- Create: `tests/test_import.py`

**Interfaces:**

- Consumes: `CandyCloudClient` dal Task 3 e `ProgramCatalog`/`save_catalog_atomic` dal Task 2.
- Produces: funzioni pure `unwrap_appliance`, `find_matching_washers`, `available_washer_summaries`, `mask_appliance_id`, `flatten_parameters`, `normalize_program`, `normalize_catalog`, `choose_appliance`; `build_parser() -> argparse.ArgumentParser`; CLI `main(argv: Sequence[str] | None = None) -> int`.

- [ ] **Step 1: Scrivere un fixture aderente allo schema dell'app**

`tests/fixtures/cloud_appliances.json` deve avere radice array e record avvolti in `appliance`. Ogni programma deve essere avvolto in `program` e avere `command_parameters` avvolti in `command_parameter`, per esempio:

```json
[
  {
    "appliance": {
      "id": "fake-device-1234",
      "appliance_model": "BWM 149PH7/1-S",
      "appliance_type": "WM",
      "connectivity": "wifi",
      "interface_type": "Bianca",
      "programs": [
        {
          "program": {
            "id": "101",
            "position": 1,
            "name": "DUAL_WM_WD_PROGRAM_NAME_COTONE",
            "command_parameters": [
              {"command_parameter": {"name": "selector_position", "validation": "1"}},
              {"command_parameter": {"name": "pr_code", "validation": "7"}},
              {"command_parameter": {"name": "default_temperature", "validation": "40"}},
              {"command_parameter": {"name": "maximum_temperature", "validation": "90"}},
              {"command_parameter": {"name": "default_spin_speed", "validation": "1000"}},
              {"command_parameter": {"name": "maximum_spin_speed", "validation": "1400"}},
              {"command_parameter": {"name": "minimum_soil_level", "validation": "1"}},
              {"command_parameter": {"name": "default_soil_level", "validation": "2"}},
              {"command_parameter": {"name": "maximum_soil_level", "validation": "3"}},
              {"command_parameter": {"name": "available_options", "validation": "0"}}
            ]
          }
        }
      ]
    }
  }
]
```

Usare ID, modelli e programmi interamente fittizi. Non copiare risposte dell'account reale nei fixture.

- [ ] **Step 2: Scrivere i test di selezione e normalizzazione**

In `tests/test_import.py` usare il fixture per test concreti:

```python
import copy
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from candy_import_programs import (
    build_parser,
    choose_appliance,
    find_matching_washers,
    mask_appliance_id,
    normalize_catalog,
    unwrap_appliance,
)
from candy_programs import CatalogError

FIXTURE = Path(__file__).parent / "fixtures" / "cloud_appliances.json"


def fixture_records():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def first_appliance():
    return unwrap_appliance(fixture_records()[0])


def test_unwraps_and_selects_unique_bwm():
    matches = find_matching_washers(fixture_records())
    assert len(matches) == 1
    assert matches[0]["appliance_model"] == "BWM 149PH7/1-S"
    assert choose_appliance(matches) is matches[0]


def test_multiple_matching_washers_require_explicit_index():
    first = first_appliance()
    second = copy.deepcopy(first)
    second["id"] = "fake-device-9999"
    answers = iter(["2"])
    assert choose_appliance([first, second], input_fn=lambda prompt: next(answers)) is second


def test_masks_appliance_id_to_last_four_characters():
    assert mask_appliance_id("fake-device-1234") == "***1234"


def test_maps_selector_pr_code_name_and_defaults_exactly():
    catalog = normalize_catalog(first_appliance(), imported_at=datetime(2026, 8, 1, tzinfo=timezone.utc))
    program = catalog.programs[0]
    assert (program.name, program.prnm, program.prcode) == ("cotone", 1, 7)
    assert program.prstr == "DUAL_WM_WD_PROGRAM_NAME_COTONE"
    assert (program.defaults.temp, program.defaults.spin, program.defaults.soil) == (40, 1000, 2)
    assert program.allowed.temp == (40,)
    assert program.allowed.spin == (1000,)
    assert program.allowed.soil == (2,)


@pytest.mark.parametrize("missing", ["selector_position", "pr_code"])
def test_rejects_program_without_required_mapping(missing):
    appliance = first_appliance()
    parameters = appliance["programs"][0]["program"]["command_parameters"]
    parameters[:] = [item for item in parameters if item["command_parameter"]["name"] != missing]
    with pytest.raises(CatalogError, match=missing):
        normalize_catalog(appliance, imported_at=datetime.now(timezone.utc))


def test_one_bad_program_rejects_whole_catalog():
    appliance = first_appliance()
    bad = copy.deepcopy(appliance["programs"][0])
    bad["program"]["command_parameters"] = []
    appliance["programs"].append(bad)
    with pytest.raises(CatalogError):
        normalize_catalog(appliance, imported_at=datetime.now(timezone.utc))


def test_parser_rejects_password_option():
    with pytest.raises(SystemExit):
        build_parser().parse_args(["--password"])
```

Aggiungere test di orchestrazione completi, sempre senza rete:

```python
import candy_import_programs as importer


def test_main_authenticates_fetches_then_saves(monkeypatch, tmp_path):
    events = []
    output = tmp_path / "programs.json"

    class FakeClient:
        def authenticate(self, email, password):
            events.append(("authenticate", email, password))

        def fetch_appliances(self):
            events.append(("fetch",))
            return fixture_records()

    monkeypatch.setattr(importer, "CandyCloudClient", FakeClient)
    monkeypatch.setattr(importer, "input", lambda prompt: "me@example.test", raising=False)
    monkeypatch.setattr(importer.getpass, "getpass", lambda prompt: "one-use-password")
    monkeypatch.setattr(
        importer,
        "save_catalog_atomic",
        lambda catalog, path: events.append(("save", Path(path), len(catalog.programs))),
    )
    assert importer.main(["--output", str(output)]) == 0
    assert events == [
        ("authenticate", "me@example.test", "one-use-password"),
        ("fetch",),
        ("save", output, 1),
    ]


def test_main_schema_error_never_saves(monkeypatch, tmp_path):
    records = fixture_records()
    records[0]["appliance"]["programs"][0]["program"]["command_parameters"] = []

    class FakeClient:
        def authenticate(self, email, password):
            return None

        def fetch_appliances(self):
            return records

    monkeypatch.setattr(importer, "CandyCloudClient", FakeClient)
    monkeypatch.setattr(importer, "input", lambda prompt: "me@example.test", raising=False)
    monkeypatch.setattr(importer.getpass, "getpass", lambda prompt: "one-use-password")
    monkeypatch.setattr(importer, "save_catalog_atomic",
                        lambda catalog, path: pytest.fail("non deve salvare"))
    output = tmp_path / "programs.json"
    assert importer.main(["--output", str(output)]) == 2
    assert not output.exists()
```

- [ ] **Step 3: Eseguire i test e confermare il fallimento**

Run:

```powershell
python -m pytest tests/test_import.py -q
```

Expected: FAIL in import con `ModuleNotFoundError: No module named 'candy_import_programs'`.

- [ ] **Step 4: Implementare normalizzatore e selezione**

Implementare prima le funzioni pure di selezione:

```python
import re


def unwrap_appliance(record: object) -> dict[str, object]:
    if not isinstance(record, dict):
        raise CatalogError("appliance: record non valido")
    value = record.get("appliance", record)
    if not isinstance(value, dict):
        raise CatalogError("appliance: oggetto non valido")
    return value


def _canonical_model(value: object) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(value).upper())


def _is_washer(appliance):
    appliance_type = _canonical_model(appliance.get("appliance_type", ""))
    model = _canonical_model(appliance.get("appliance_model", ""))
    return appliance_type in {"WM", "WASHER", "WASHINGMACHINE"} or model.startswith("BWM")


def find_matching_washers(records, model_query="BWM149PH7"):
    query = _canonical_model(model_query)
    appliances = [unwrap_appliance(record) for record in records]
    return [item for item in appliances
            if _is_washer(item)
            and _canonical_model(item.get("appliance_model", "")).startswith(query)]


def available_washer_summaries(records):
    summaries = []
    for record in records:
        item = unwrap_appliance(record)
        if _is_washer(item):
            summaries.append(
                f"{item.get('appliance_model')} "
                f"{mask_appliance_id(item.get('id', item.get('uid')))}"
            )
    return summaries


def mask_appliance_id(value: object) -> str:
    raw = str(value)
    if len(raw) < 4:
        raise CatalogError("appliance.id: identificatore non valido")
    return "***" + raw[-4:]


def choose_appliance(matches, input_fn=input):
    if not matches:
        raise CatalogError("Nessuna BWM 149PH7 trovata nell'account Candy.")
    if len(matches) == 1:
        return matches[0]
    for index, item in enumerate(matches, start=1):
        print(f"{index}. {item.get('appliance_model')} {mask_appliance_id(item.get('id', item.get('uid')))}")
    try:
        selected = int(input_fn("Lavatrice da importare: ")) - 1
        return matches[selected]
    except (ValueError, IndexError):
        raise CatalogError("Selezione lavatrice non valida.") from None
```

Per `flatten_parameters`, iterare `command_parameters`, togliere l'eventuale wrapper `command_parameter`, richiedere stringhe non vuote per `name` e `validation`, rifiutare nomi duplicati e restituire `dict[str, str]`.

Il nucleo di `normalize_program` deve usare conversioni strette, senza fallback dall'ID cloud:

```python
def required_int(parameters, name):
    try:
        return int(parameters[name])
    except (KeyError, TypeError, ValueError):
        raise CatalogError(f"command_parameters.{name}: intero obbligatorio") from None


def allowed_options(parameters):
    try:
        mask = int(parameters.get("available_options", "0"))
        second_mask = int(parameters.get("available_options2", "0"))
    except (TypeError, ValueError):
        raise CatalogError("command_parameters.available_options: intero non valido") from None
    known_mask = sum(OPTION_BITS.values())
    if second_mask or mask & ~known_mask:
        raise CatalogError("command_parameters.available_options: bit sconosciuti")
    return tuple(name for name, bit in OPTION_BITS.items() if mask & bit)


def allowed_ints(parameters, name, default):
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


def normalize_program(program_record):
    if not isinstance(program_record, dict):
        raise CatalogError("program: record non valido")
    raw = program_record.get("program", program_record)
    if not isinstance(raw, dict):
        raise CatalogError("program: oggetto non valido")
    parameters = flatten_parameters(raw)
    cloud_name = raw.get("name")
    if not isinstance(cloud_name, str) or not cloud_name:
        raise CatalogError("program.name: stringa obbligatoria")
    selector = required_int(parameters, "selector_position")
    code = required_int(parameters, "pr_code")
    temp = required_int(parameters, "default_temperature")
    spin = required_int(parameters, "default_spin_speed")
    soil = required_int(parameters, "default_soil_level")
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
            steam=required_int(parameters, "steam") if "steam" in parameters else 0,
            dry=required_int(parameters, "dry") if "dry" in parameters else 0,
        ),
        allowed=ProgramAllowed(
            temp=allowed_ints(parameters, "allowed_temperatures", temp),
            spin=allowed_ints(parameters, "allowed_spin_speeds", spin),
            soil=allowed_ints(parameters, "allowed_soil_levels", soil),
            options=allowed_options(parameters),
        ),
        source="candy-cloud",
    )
```

`normalize_catalog` deve normalizzare tutti i record senza `try/except` per-programma e applicare l'unica regola di collisione consentita:

```python
from dataclasses import replace


def normalize_catalog(appliance, *, imported_at):
    raw_programs = appliance.get("programs")
    if not isinstance(raw_programs, list) or not raw_programs:
        raise CatalogError("appliance.programs: lista non vuota obbligatoria")
    programs = []
    used_names = set()
    for raw_program in raw_programs:
        program = normalize_program(raw_program)
        if program.name in used_names:
            program = replace(program, name=f"{program.name}-{program.prnm}")
        if program.name in used_names:
            raise CatalogError(f"program.name duplicato: {program.name}")
        used_names.add(program.name)
        programs.append(program)
    model = appliance.get("appliance_model")
    if not isinstance(model, str) or not model:
        raise CatalogError("appliance.appliance_model: stringa obbligatoria")
    appliance_id = appliance.get("id", appliance.get("uid"))
    result = ProgramCatalog(
        schema_version=1,
        source="candy-cloud",
        appliance_model=model,
        appliance_id_masked=mask_appliance_id(appliance_id),
        imported_at=imported_at.isoformat(),
        programs=tuple(programs),
    )
    return parse_catalog(catalog_to_dict(result))
```

Regole esatte di mapping:

- modello da `appliance_model`, con confronto case-insensitive dopo rimozione di spazi, trattini, slash e suffissi commerciali;
- ID da `id`/`uid`, salvando soltanto `***` + ultime quattro cifre/caratteri;
- programmi dalla lista `programs`, ciascuno eventualmente avvolto in `program`;
- parametri dal campo `command_parameters`, ciascuno eventualmente avvolto in `command_parameter`, indicizzati per `name` e letti da `validation`;
- `prnm` soltanto da `selector_position`; `position` e ID cloud restano metadata e non sono fallback sicuri;
- `prcode` solo da `pr_code`; nessuna derivazione dall'ID del programma;
- `prstr` dal `name` cloud; `name` locale da slug del `name`, con suffisso deterministico `-<prnm>` solo in caso di collisione;
- default obbligatori: `default_temperature`, `default_spin_speed`, `default_soil_level`;
- `steam=0` e `dry=0` soltanto quando i relativi parametri sono assenti e l'appliance è una lavatrice, interpretando l'assenza come funzionalità non supportata;
- `allowed.temp`, `allowed.spin`, `allowed.soil` leggono `allowed_temperatures`, `allowed_spin_speeds`, `allowed_soil_levels` se il cloud le espone come liste separate da virgola; altrimenti contengono soltanto il rispettivo default, come prescritto dalla spec;
- `available_options` assente o uguale a `0` produce lista vuota; bit non riconosciuti rendono il programma invalido invece di essere ignorati;
- un singolo programma incompleto invalida tutto il catalogo.

- [ ] **Step 5: Implementare la CLI senza opzioni per segreti**

Implementare parser e `main()` senza opzioni per segreti:

```python
import argparse
import getpass
import sys
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path


def build_parser():
    parser = argparse.ArgumentParser(description="Importa i programmi Candy dal cloud.")
    parser.add_argument("--output", type=Path, default=Path("programs.json"))
    parser.add_argument("--model", default="BWM 149PH7")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    password = None
    try:
        email = input("Email Candy: ").strip()
        password = getpass.getpass("Password Candy: ")
        client = CandyCloudClient()
        client.authenticate(email, password)
        records = client.fetch_appliances()
        matches = find_matching_washers(records, args.model)
        if not matches:
            available = available_washer_summaries(records)
            suffix = "; trovate: " + ", ".join(available) if available else ""
            raise CatalogError(f"Nessuna {args.model} trovata nell'account Candy{suffix}.")
        appliance = choose_appliance(matches)
        catalog = normalize_catalog(appliance, imported_at=datetime.now().astimezone())
        print(f"{catalog.appliance_model} {catalog.appliance_id_masked}")
        print(f"Programmi importabili: {len(catalog.programs)}")
        for program in catalog.programs:
            print(f"- {program.name}: {program.prstr}")
        save_catalog_atomic(catalog, args.output)
        print(f"Catalogo salvato in {args.output}")
        return 0
    except CandyCloudError as error:
        print(str(error), file=sys.stderr)
        return 3
    except CatalogError as error:
        print(str(error), file=sys.stderr)
        return 2
    finally:
        password = None


if __name__ == "__main__":
    raise SystemExit(main())
```

Il `finally` elimina soltanto il riferimento locale; la documentazione non deve promettere cancellazione garantita della memoria Python.

- [ ] **Step 6: Eseguire i test mirati**

Run:

```powershell
python -m pytest tests/test_import.py -q
```

Expected: tutti PASS.

- [ ] **Step 7: Checkpoint Git condizionale**

```powershell
git add candy_import_programs.py tests/fixtures/cloud_appliances.json tests/test_import.py
git commit -m "feat: import bwm program catalog from candy cloud"
```

---

### Task 5: Allineare il payload locale al client Android e validarlo prima della rete

**Files:**

- Modify: `candy_sendprogram.py`
- Create: `tests/test_sendprogram.py`

**Interfaces:**

- Consumes: `OPTION_BITS`, `ProgramDefinition`, `load_catalog`, `validate_overrides` dal Task 2; trasporto XOR/HTTP già presente.
- Produces: `build_start_payload(program, *, temp=None, spin=None, soil=None, options=()) -> str`; `start_named_program(name, *, catalog_path=Path("programs.json"), temp=None, spin=None, soil=None, options=(), dry_run=False, key_provider=getkey, sender=send_command) -> str`; CLI `start --program <nome>` fail-closed.

- [ ] **Step 1: Scrivere test di caratterizzazione del trasporto esistente**

Prima del refactor, fissare almeno la cifratura esistente con un test locale:

```python
from candy_sendprogram import xor_decode, xor_encode


def test_xor_round_trip_preserves_payload():
    key = bytes(range(16))
    payload = "Write=1&StSt=0&PrNm=1"
    assert xor_decode(xor_encode(payload, key), key) == payload
```

Non chiamare `getkey`, `read_status` o `send_command` nei test unitari: le loro dipendenze di rete vengono verificate soltanto attraverso mock/injection.

- [ ] **Step 2: Scrivere i test del nuovo builder**

Completare `tests/test_sendprogram.py` con casi eseguibili basati sul fixture normalizzato:

```python
import json
from pathlib import Path

import pytest

import candy_sendprogram
from candy_programs import CatalogError, parse_catalog
from candy_sendprogram import build_start_payload, start_named_program

FIXTURE = Path(__file__).parent / "fixtures" / "programs_valid.json"


@pytest.fixture
def program():
    return parse_catalog(json.loads(FIXTURE.read_text(encoding="utf-8"))).programs[0]


def test_default_start_payload_uses_imported_selector(program):
    assert build_start_payload(program) == (
        "Write=1&Pa=0&Sel=0&PrNm=1&StSt=1&OptMsk=0"
    )


def test_temperature_override_adds_target_and_cloud_default(program):
    assert build_start_payload(program, temp=30) == (
        "Write=1&Pa=0&Sel=0&PrNm=1&StSt=1&TmpTgt=30&TmpDf=40&OptMsk=0"
    )


def test_spin_override_converts_rpm_to_protocol_units(program):
    assert "&SpdTgt=8&SpdDef=10&" in build_start_payload(program, spin=800)


def test_soil_override_adds_only_target(program):
    assert "&SLevTgt=3&" in build_start_payload(program, soil=3)


def test_option_mask_uses_only_official_field(program):
    payload = build_start_payload(program, options=("prewash",))
    assert payload.endswith("&OptMsk=1")
    assert "OptMsk1" not in payload and "OptMsk2" not in payload


def test_invalid_override_raises_before_transport(tmp_path):
    path = tmp_path / "programs.json"
    path.write_bytes(FIXTURE.read_bytes())
    calls = []
    with pytest.raises(CatalogError, match="temperatura"):
        start_named_program("cotone", catalog_path=path, temp=95,
                            key_provider=lambda: calls.append("key"),
                            sender=lambda payload, key: calls.append(payload))
    assert calls == []


def test_missing_catalog_blocks_named_start(tmp_path):
    with pytest.raises(CatalogError, match="candy_import_programs.py"):
        start_named_program("cotone", catalog_path=tmp_path / "missing.json",
                            dry_run=True)


```

Il test `test_missing_catalog_blocks_named_start` è la prova comportamentale che nessun catalogo dimostrativo viene usato come fallback; non aggiungere asserzioni sui nomi dei simboli interni del modulo.

Stringhe attese per gli override:

```text
&TmpTgt=30&TmpDf=40
&SLevTgt=3
&SpdTgt=8&SpdDef=10
&OptMsk=1
```

- [ ] **Step 3: Eseguire i test e confermare il fallimento**

Run:

```powershell
python -m pytest tests/test_sendprogram.py -q
```

Expected: `test_xor_round_trip_preserves_payload` passa; i test del nuovo builder falliscono perché `build_start_payload` e `start_named_program` non esistono ancora.

- [ ] **Step 4: Implementare il builder puro**

Sostituire l'uso operativo di `PROGRAMS` con:

```python
def build_start_payload(
    program: ProgramDefinition,
    *,
    temp: int | None = None,
    spin: int | None = None,
    soil: int | None = None,
    options: Iterable[str] = (),
) -> str:
    selected_options = tuple(options)
    validate_overrides(program, temp=temp, spin=spin, soil=soil,
                       options=selected_options)
    parts = ["Write=1", "Pa=0", "Sel=0", f"PrNm={program.prnm}", "StSt=1"]
    if temp is not None and temp != program.defaults.temp:
        parts.extend((f"TmpTgt={temp}", f"TmpDf={program.defaults.temp}"))
    if soil is not None and soil != program.defaults.soil:
        parts.append(f"SLevTgt={soil}")
    if spin is not None and spin != program.defaults.spin:
        if spin % 100 or program.defaults.spin % 100:
            raise CatalogError("Centrifuga non rappresentabile dal protocollo Candy.")
        parts.extend((f"SpdTgt={spin // 100}",
                      f"SpdDef={program.defaults.spin // 100}"))
    mask = sum(OPTION_BITS[name] for name in selected_options)
    parts.append(f"OptMsk={mask}")
    return "&".join(parts)


def start_named_program(name, *, catalog_path=Path("programs.json"),
                        temp=None, spin=None, soil=None, options=(),
                        dry_run=False, key_provider=getkey,
                        sender=send_command):
    program = load_catalog(catalog_path).by_name(name)
    payload = build_start_payload(program, temp=temp, spin=spin,
                                  soil=soil, options=options)
    if not dry_run:
        sender(payload, key_provider())
    return payload
```

Applicare queste regole:

- temperatura: se diversa dal default, aggiungere `TmpTgt` e `TmpDf`;
- soil: se diverso dal default, aggiungere `SLevTgt`;
- spin: il catalogo usa rpm, il protocollo usa rpm/100; rifiutare valori non divisibili per 100, aggiungere `SpdTgt` e `SpdDef`;
- opzioni: convertire esclusivamente nomi presenti in `allowed.options` usando una tabella bit documentata e terminare con un solo `OptMsk`;
- nessun `PrCode`, `PrStr`, `OptMsk1` o `OptMsk2` nel percorso BWM: restano metadata del catalogo, non campi del comando verificato;
- conservare il trasporto XOR e il recupero chiave esistenti invariati;
- `--dry-run` stampa payload e non chiama mai il trasporto;
- `start --program <nome>` carica `programs.json`, risolve `name`, valida tutto e solo dopo invia;
- rimuovere dal parser di `start` i bypass grezzi `--prnm`, `--prcode`, `--prstr`, `--steam`, `--dry` e `--delay`; mantenere `--temp`, `--spin`, `--soil`, `--options`, `--dry-run`, chiarendo nell'help che `--spin` è espresso in rpm;
- catalogo assente/invalido produce: `Catalogo programmi non disponibile. Esegui: python candy_import_programs.py`.

- [ ] **Step 5: Eseguire i test mirati**

Run:

```powershell
python -m pytest tests/test_sendprogram.py -q
```

Expected: tutti PASS e nessun test apre socket/HTTP reale.

- [ ] **Step 6: Checkpoint Git condizionale**

```powershell
git add candy_sendprogram.py tests/test_sendprogram.py
git commit -m "fix: build bwm starts from imported selector mapping"
```

---

### Task 6: Usare lo stesso catalogo in CLI e interfaccia web

**Files:**

- Modify: `candy_sendprogram.py`
- Modify: `candy_web.py`
- Create: `tests/test_web.py`

**Interfaces:**

- Consumes: `load_catalog` e le eccezioni tipizzate dal Task 2; `build_start_payload`, `getkey` e `send_command` dal Task 5.
- Produces: `GET /api/programs` dal catalogo condiviso e route di start con errori HTTP `404/422/502/503` definiti.

- [ ] **Step 1: Scrivere i test API**

Usare `fastapi.testclient.TestClient` e monkeypatchare catalogo e trasporto con test concreti:

```python
import json
from pathlib import Path

from fastapi.testclient import TestClient

import candy_web
from candy_programs import CatalogUnavailableError, parse_catalog

FIXTURE = Path(__file__).parent / "fixtures" / "programs_valid.json"
CLIENT = TestClient(candy_web.app)


def catalog():
    return parse_catalog(json.loads(FIXTURE.read_text(encoding="utf-8")))


def test_api_programs_matches_shared_catalog(monkeypatch):
    monkeypatch.setattr(candy_web, "get_program_catalog", catalog)
    response = CLIENT.get("/api/programs")
    assert response.status_code == 200
    assert [item["name"] for item in response.json()] == ["cotone", "rapido-30"]
    assert response.json()[0]["allowed"] == {
        "temp": [30, 40], "spin": [800, 1000],
        "soil": [2, 3], "options": ["prewash"]
    }


def test_missing_catalog_returns_actionable_503(monkeypatch):
    def unavailable():
        raise CatalogUnavailableError("Esegui: python candy_import_programs.py")
    monkeypatch.setattr(candy_web, "get_program_catalog", unavailable)
    response = CLIENT.get("/api/programs")
    assert response.status_code == 503
    assert "candy_import_programs.py" in response.json()["detail"]


def test_start_unknown_program_returns_404_without_network(monkeypatch):
    monkeypatch.setattr(candy_web, "get_program_catalog", catalog)
    calls = []
    monkeypatch.setattr(candy_web.c, "getkey", lambda: calls.append("key"))
    response = CLIENT.post("/api/start", json={"program": "inesistente"})
    assert response.status_code == 404
    assert calls == []


def test_start_disallowed_temperature_returns_422_without_network(monkeypatch):
    monkeypatch.setattr(candy_web, "get_program_catalog", catalog)
    calls = []
    monkeypatch.setattr(candy_web.c, "getkey", lambda: calls.append("key"))
    response = CLIENT.post("/api/start", json={"program": "cotone", "temp": 95})
    assert response.status_code == 422
    assert calls == []


def test_valid_start_uses_sender_after_validation(monkeypatch):
    monkeypatch.setattr(candy_web, "get_program_catalog", catalog)
    calls = []
    monkeypatch.setattr(candy_web.c, "getkey", lambda: b"0" * 16)
    monkeypatch.setattr(candy_web.c, "send_command",
                        lambda payload, key: calls.append((payload, key)) or "{}")
    response = CLIENT.post("/api/start", json={"program": "cotone"})
    assert response.status_code == 200
    assert calls[0][0] == "Write=1&Pa=0&Sel=0&PrNm=1&StSt=1&OptMsk=0"


def test_page_contains_catalog_import_recovery_action():
    response = CLIENT.get("/")
    assert response.status_code == 200
    assert "candy_import_programs.py" in response.text
```

- [ ] **Step 2: Eseguire i test e confermare il fallimento**

Run:

```powershell
python -m pytest tests/test_web.py -q
```

Expected: FAIL perché `candy_web.py` usa ancora `candy_sendprogram.PROGRAMS`.

- [ ] **Step 3: Rifattorizzare caricamento e route**

- Aggiungere `PROGRAMS_PATH = Path("programs.json")` e `get_program_catalog()` che chiama esclusivamente `load_catalog(PROGRAMS_PATH)`; nei test la funzione viene sostituita direttamente.
- `/api/programs` serializza il catalogo condiviso includendo nome, descrizione cloud, default e allowed.
- Sostituire `StartCmd` con campi `program: str`, `temp: int | None`, `spin: int | None`, `soil: int | None`, `options: list[str] = Field(default_factory=list)`; eliminare i campi grezzi `prnm`, `prcode`, `prstr`, `steam`, `dry`, `delay`.
- La route start chiama `get_program_catalog()`, risolve `catalog.by_name(cmd.program)` e costruisce `build_start_payload` prima di chiamare `c.getkey()`/`c.send_command()`; questo ordine è obbligatorio per garantire zero rete sui `404/422`.
- Mappare `CatalogUnavailableError` a `503`, `UnknownProgramError` a `404`, `OverrideError` a `422`, errore chiave/trasporto a `502`.
- Disabilitare il pulsante di avvio e mostrare il comando di importazione se `/api/programs` restituisce `503`.
- Non cambiare il polling stato salvo adattare gli import.

La parte server delle route deve seguire questa struttura, così la validazione precede sempre la rete:

```python
from dataclasses import asdict
from pathlib import Path

from pydantic import BaseModel, Field

from candy_programs import (
    CatalogUnavailableError,
    OverrideError,
    UnknownProgramError,
    load_catalog,
)

PROGRAMS_PATH = Path("programs.json")


class StartCmd(BaseModel):
    program: str
    temp: int | None = None
    spin: int | None = None
    soil: int | None = None
    options: list[str] = Field(default_factory=list)


def get_program_catalog():
    return load_catalog(PROGRAMS_PATH)


def program_to_api(program):
    return {
        "name": program.name,
        "prnm": program.prnm,
        "prcode": program.prcode,
        "prstr": program.prstr,
        "defaults": asdict(program.defaults),
        "allowed": asdict(program.allowed),
    }


@app.get("/api/programs")
def api_programs():
    try:
        return [program_to_api(program) for program in get_program_catalog().programs]
    except CatalogUnavailableError as error:
        raise HTTPException(503, str(error)) from None


@app.post("/api/start")
def api_start(cmd: StartCmd):
    try:
        program = get_program_catalog().by_name(cmd.program)
        payload = c.build_start_payload(
            program,
            temp=cmd.temp,
            spin=cmd.spin,
            soil=cmd.soil,
            options=cmd.options,
        )
    except CatalogUnavailableError as error:
        raise HTTPException(503, str(error)) from None
    except UnknownProgramError as error:
        raise HTTPException(404, str(error)) from None
    except OverrideError as error:
        raise HTTPException(422, str(error)) from None
    try:
        c.CANDY_IP = candy_ip
        response_text = c.send_command(payload, c.getkey())
    except Exception as error:
        raise HTTPException(502, f"Invio comando fallito: {error}") from None
    try:
        response = json.loads(response_text)
    except ValueError:
        response = {"raw": response_text}
    return {"sent": True, "payload": payload, "response": response,
            "program": program_to_api(program)}
```

Aggiornare anche `/api/config` affinché legga i nomi da `get_program_catalog()`; se il catalogo non è disponibile, restituire `programs: []` e `catalog_ready: false` senza mascherare l'errore di `/api/programs`.

- [ ] **Step 4: Verificare parità e regressioni**

Run:

```powershell
python -m pytest tests/test_programs.py tests/test_sendprogram.py tests/test_web.py -q
```

Expected: tutti PASS; fixture e programma restituito da CLI/web coincidono.

- [ ] **Step 5: Checkpoint Git condizionale**

```powershell
git add candy_sendprogram.py candy_web.py tests/test_web.py
git commit -m "feat: share imported programs between cli and web"
```

---

### Task 7: Documentare il flusso sicuro e dismettere l'apprendimento da manopola

**Files:**

- Modify: `candy_learn_programs.py`
- Create: `README.md`

**Interfaces:**

- Consumes: CLI create nei Task 4 e 5.
- Produces: guardrail BWM in `candy_learn_programs.main(argv=None) -> int` e istruzioni operative complete.

- [ ] **Step 1: Aggiungere il guardrail al vecchio script**

Per `candy_learn_programs.py`, mantenere il codice per altri modelli ma aggiungere un guardrail prima di ogni lettura o scrittura:

```python
import argparse
import re


def build_parser():
    parser = argparse.ArgumentParser(
        description="Acquisizione legacy dalla manopola; non valida per BWM 149PH7."
    )
    parser.add_argument("--model", default="BWM 149PH7")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    model = re.sub(r"[^A-Z0-9]", "", args.model.upper())
    if model.startswith("BWM149PH7"):
        print("La BWM 149PH7 esclude il controllo remoto quando si usa la manopola.",
              file=sys.stderr)
        print("Usa invece: python candy_import_programs.py", file=sys.stderr)
        return 2
    return legacy_main()
```

Rinominare il corpo interattivo attuale in `legacy_main()` e farlo terminare con `return 0`. Nel blocco `if __name__ == "__main__"` usare `raise SystemExit(main())`.

- se `--model` normalizzato è `BWM149PH7`, terminare con exit code `2` e messaggio che la manopola esclude il controllo remoto;
- indicare `python candy_import_programs.py` come percorso supportato;
- non importare né scrivere `programs.json` da questo script per la BWM.

Scrivere questo test in `tests/test_import.py` per asserire il guardrail senza interagire con l'elettrodomestico:

```python
import candy_learn_programs


def test_bwm_learning_guardrail_runs_before_appliance_access(monkeypatch, capsys):
    monkeypatch.setattr(candy_learn_programs, "read_program",
                        lambda: pytest.fail("non deve leggere la lavatrice"))
    assert candy_learn_programs.main(["--model", "BWM 149PH7/1-S"]) == 2
    assert "candy_import_programs.py" in capsys.readouterr().err
```

- [ ] **Step 2: Scrivere il README operativo**

Documentare esattamente:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe candy_import_programs.py
.\.venv\Scripts\python.exe candy_sendprogram.py list
.\.venv\Scripts\python.exe candy_sendprogram.py start --program <nome> --dry-run
.\.venv\Scripts\python.exe candy_web.py
```

Includere:

- password e token non vengono salvati;
- `candy_key.cache` è una chiave locale dell'elettrodomestico e va protetta;
- importazione e dry-run non avviano la macchina;
- il primo invio reale richiede macchina pronta al controllo remoto secondo le condizioni dell'app;
- ripetere l'importazione se Candy cambia il catalogo;
- non allegare `programs.json`, `candy_key.cache` o capture di rete a issue pubbliche.

- [ ] **Step 3: Eseguire il test del guardrail**

Run:

```powershell
python -m pytest tests/test_import.py -q
```

Expected: tutti PASS; nessuna rete.

- [ ] **Step 4: Checkpoint Git condizionale**

```powershell
git add candy_learn_programs.py README.md tests/test_import.py
git commit -m "docs: document safe bwm catalog workflow"
```

---

### Task 8: Verifica completa e importazione reale controllata

**Files:**

- Verify: tutti i file sopra
- Runtime output (ignorato da Git): `programs.json`

**Interfaces:**

- Consumes: tutti i deliverable dei Task 1-7.
- Produces: suite offline verde, catalogo reale validato e dry-run confrontabile con Android; nessun avvio reale.

- [ ] **Step 1: Controllare sintassi di tutti i moduli**

Run:

```powershell
python -m py_compile candy_programs.py candy_cloud.py candy_import_programs.py candy_sendprogram.py candy_getstatus.py candy_learn_programs.py candy_web.py
```

Expected: exit code `0`, nessun output.

- [ ] **Step 2: Eseguire l'intera suite offline**

Run:

```powershell
python -m pytest -q
```

Expected: tutti PASS; nessuna chiamata cloud o appliance reale.

- [ ] **Step 3: Verificare che i segreti non siano persistiti dal codice nuovo**

Run:

```powershell
rg -n "password|access_token|Authorization" candy_*.py README.md
```

Expected: soltanto prompt, form OAuth in memoria, header in memoria e documentazione; nessuna scrittura su file/log di questi valori.

Run:

```powershell
rg -n "PROGRAMS|OptMsk1|OptMsk2|PrStr=" candy_sendprogram.py candy_web.py
```

Expected: nessuna tabella dimostrativa usata per inviare; nessun campo legacy nel builder BWM.

- [ ] **Step 4: Eseguire l'importazione cloud esplicitamente con l'utente presente**

Run:

```powershell
python candy_import_programs.py
```

Expected: prompt email/password nascosta, riepilogo BWM 149PH7 con ID mascherato e creazione atomica di `programs.json`; nessun comando alla lavatrice.

Se il cloud restituisce uno schema differente, fermarsi, conservare il file esistente e aggiungere un fixture anonimizzato minimale prima di adattare il parser. Non stampare la risposta completa.

- [ ] **Step 5: Confrontare con Android senza avvio**

Run:

```powershell
python candy_sendprogram.py list
```

Expected: numero e nomi confrontabili con l'elenco visibile nell'app Android. Annotare separatamente programmi standard ed eventuali ricette speciali; non forzare 21 se il cloud dichiara un totale diverso.

- [ ] **Step 6: Verificare il payload in dry-run**

Run:

```powershell
python candy_sendprogram.py start --program <nome-reale-importato> --dry-run
```

Expected: payload inizia con `Write=1&Pa=0&Sel=0&PrNm=` e termina con `&OptMsk=0`; nessuna richiesta viene inviata.

- [ ] **Step 7: Fermarsi prima del primo invio reale**

Consegnare all'utente catalogo, confronto e dry-run. Il primo `start` senza `--dry-run` è una distinta azione esplicita dell'utente e non fa parte dell'implementazione automatica.

- [ ] **Step 8: Checkpoint Git condizionale finale**

```powershell
git status --short
git log --oneline -7
```

Expected: worktree pulito e checkpoint presenti solo se il progetto è stato inizializzato come repository.

## Self-review Checklist

- [x] Tutti i criteri di accettazione della spec hanno almeno un test o uno step manuale.
- [x] Nessun test o import chiama l'endpoint locale di scrittura.
- [x] Nessun segreto utente è accettato tramite CLI arg/env o scritto su disco.
- [x] `programs.json` viene validato prima di backup/sostituzione.
- [x] CLI e web usano `candy_programs.load_catalog`, senza copie del catalogo.
- [x] `PrNm` proviene da `selector_position` cloud; `pr_code` resta metadata e non viene inventato.
- [x] Temperatura/spin/soil fuori da `allowed` falliscono prima del trasporto.
- [x] Il builder produce la sintassi del client Android (`OptMsk`, spin/100).
- [x] Catalogo mancante o invalido blocca l'avvio e indica l'importatore.
- [x] I fixture non contengono dati reali dell'utente.
- [x] Non restano placeholder nel codice; `<nome-reale-importato>` compare solo nello step manuale dove dipende dal catalogo reale.
