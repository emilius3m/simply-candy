# FastAPI Safe Start Alignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Candy program starts safe by default, exclude the technical `OFF` record everywhere, expose a guarded real-send checkbox, and align tests with the current two-mask payload.

**Architecture:** Put program startability policy in `candy_programs.py` so importer, CLI, and FastAPI share one decision based on stable `prstr`. Keep existing catalog files parseable, filter technical records at consumer boundaries, and make FastAPI `dry_run=True` unless a client explicitly opts into transmission. The Web UI maps an unchecked checkbox to dry-run and a checked, confirmed checkbox to real send.

**Tech Stack:** Python 3.12, FastAPI, Pydantic, pytest, stdlib HTML/JavaScript, existing Candy protocol modules.

## Global Constraints

- Never contact Candy Cloud or the physical washer during implementation or tests.
- Never start a real FastAPI server for verification; use `TestClient` only.
- Leave the existing `programs.json` bytes unchanged.
- Preserve `POST /api/stop` behavior.
- Real start requires the exact JSON value `"dry_run": false`; omission must be safe.
- The workspace is not a Git repository. Do not initialize one; replace commit steps with explicit test checkpoints.

## File Structure

- `candy_programs.py`: owns technical-program classification and reusable guards.
- `candy_import_programs.py`: omits technical records from newly generated catalogs.
- `candy_sendprogram.py`: applies the shared guard to CLI listing and named starts.
- `candy_web.py`: implements safe API semantics and the guarded checkbox UI.
- `tests/test_programs.py`: verifies the shared classification contract.
- `tests/test_import.py`: verifies import filtering and the all-technical failure case.
- `tests/test_sendprogram.py`: verifies CLI/send guard and current two-mask payload.
- `tests/test_web.py`: verifies API filtering, dry-run behavior, real send, Zoom, and UI safety controls.

---

### Task 1: Shared startability policy and importer filtering

**Files:**
- Modify: `candy_programs.py`
- Modify: `candy_import_programs.py`
- Test: `tests/test_programs.py`
- Test: `tests/test_import.py`

**Interfaces:**
- Produces: `NON_STARTABLE_PRSTRS: frozenset[str]`.
- Produces: `is_startable_program(program: ProgramDefinition) -> bool`.
- Produces: `startable_programs(catalog: ProgramCatalog) -> tuple[ProgramDefinition, ...]`.
- Produces: `require_startable_program(program: ProgramDefinition) -> ProgramDefinition`, raising `OverrideError` for a technical record.
- Consumes: existing `ProgramDefinition`, `ProgramCatalog`, `OverrideError`, and `normalize_program`.

- [ ] **Step 1: Write failing shared-policy tests**

Add imports for the three functions to `tests/test_programs.py`, then create an
OFF variant without changing the JSON fixture:

```python
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
```

- [ ] **Step 2: Run the shared-policy test and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_programs.py::test_startability_policy_filters_and_rejects_technical_off -q
```

Expected: collection fails because the new functions do not exist.

- [ ] **Step 3: Implement the shared policy**

In `candy_programs.py`, define the stable cloud identifiers near the other
catalog constants and add these functions after the catalog dataclasses:

```python
NON_STARTABLE_PRSTRS = frozenset({"DUAL_WM_WD_OFF"})


def is_startable_program(program: ProgramDefinition) -> bool:
    return program.prstr not in NON_STARTABLE_PRSTRS


def startable_programs(catalog: ProgramCatalog) -> tuple[ProgramDefinition, ...]:
    return tuple(program for program in catalog.programs if is_startable_program(program))


def require_startable_program(program: ProgramDefinition) -> ProgramDefinition:
    if not is_startable_program(program):
        raise OverrideError(f"Programma tecnico non avviabile: {program.prstr}")
    return program
```

- [ ] **Step 4: Run the shared-policy test and verify GREEN**

Run the Step 2 command. Expected: one test passes.

- [ ] **Step 5: Write failing importer tests**

Add a test helper to `tests/test_import.py` that clones the real fixture record
and changes only its cloud name:

```python
def off_record():
    record = copy.deepcopy(first_appliance()["programs"][0])
    record["program"]["name"] = "DUAL_WM_WD_OFF"
    return record


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
```

- [ ] **Step 6: Run importer tests and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_import.py::test_normalize_catalog_excludes_technical_off tests/test_import.py::test_normalize_catalog_rejects_catalog_with_only_technical_records -q
```

Expected: OFF is still present and the all-OFF catalog is accepted.

- [ ] **Step 7: Filter technical programs during normalization**

Import `is_startable_program` in `candy_import_programs.py`. Immediately after
`program = normalize_program(raw_program)`, continue for non-startable records.
After the loop, reject an empty result:

```python
        if not is_startable_program(program):
            continue
        # existing duplicate-name handling follows

    if not programs:
        raise CatalogError("appliance.programs: nessun programma avviabile")
```

- [ ] **Step 8: Run Task 1 tests and checkpoint**

Before the checkpoint, align the stale strict-value parameter in
`tests/test_programs.py`: replace the supposedly invalid steam value `2` with
`-1`. Production intentionally accepts nonnegative Candy steam levels, while a
negative value remains invalid and preserves the test's strict-validation
purpose.

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_programs.py tests/test_import.py -q
```

Expected: all tests in both files pass. Do not create a Git commit because this
workspace has no repository metadata.

---

### Task 2: Guard CLI starts and align sender payload tests

**Files:**
- Modify: `candy_sendprogram.py`
- Test: `tests/test_sendprogram.py`

**Interfaces:**
- Consumes: `require_startable_program(program) -> ProgramDefinition` and `startable_programs(catalog)` from Task 1.
- Preserves: `build_start_payload(...) -> str` current full protocol output.
- Preserves: `start_named_program(..., dry_run=False, key_provider=..., sender=...) -> str`.

- [ ] **Step 1: Write a failing CLI start guard test**

Create a legacy catalog containing only an OFF variant in a temporary file and
assert that key acquisition and transport cannot be reached:

```python
def test_start_named_program_rejects_technical_off_before_transport(tmp_path):
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    data["programs"][0]["name"] = "dual-wm-wd-off"
    data["programs"][0]["prstr"] = "DUAL_WM_WD_OFF"
    data["programs"] = [data["programs"][0]]
    path = tmp_path / "programs.json"
    path.write_text(json.dumps(data), encoding="utf-8")

    def forbidden(*_args):
        pytest.fail("OFF non deve accedere a chiave o trasporto")

    with pytest.raises(OverrideError, match="tecnico non avviabile"):
        start_named_program(
            "dual-wm-wd-off",
            catalog_path=path,
            key_provider=forbidden,
            sender=forbidden,
        )
```

- [ ] **Step 2: Run the guard test and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_sendprogram.py::test_start_named_program_rejects_technical_off_before_transport -q
```

Expected: the fake transport is reached or the expected guard error is absent.

- [ ] **Step 3: Apply the shared guard to send and list paths**

Import `require_startable_program` and `startable_programs` in
`candy_sendprogram.py`. In `start_named_program`, guard the result of
`catalog.by_name(name)` before calling `build_start_payload`:

```python
    program = require_startable_program(catalog.by_name(name))
```

In `cmd_list`, iterate only over:

```python
sorted(startable_programs(catalog), key=lambda item: item.name)
```

- [ ] **Step 4: Run the guard test and verify GREEN**

Run the Step 2 command. Expected: one test passes without calling either fake
transport dependency.

- [ ] **Step 5: Align obsolete payload assertions with the production builder**

Update exact expected strings in `tests/test_sendprogram.py` to the current
payload shape. The default fixture program must equal:

```text
Write=1&StSt=1&DelVl=0&PrNm=1&PrCode=7&PrStr=DUAL_WM_WD_PROGRAM_NAME_COTONE&TmpTgt=40&SLevTgt=2&SpdTgt=10&OptMsk1=0&OptMsk2=0&Lang=1&Stm=0&Dry=0&ED=0&RecipeId=0&StartCheckUp=0&DispTestOn=1
```

Temperature tests change only `TmpTgt`. Prewash tests require
`OptMsk1=1&OptMsk2=0`. Replace the obsolete test claiming that `OptMsk1` and
`OptMsk2` are absent with assertions that both fields are present and exact.
The spin-override test must assert `&SpdTgt=8&OptMsk1=0&`; the current payload
does not contain the legacy `SpdDef` field.
Add a Zoom-specific test using a program whose allowed options include
`"zoom"`:

```python
def test_zoom_uses_second_option_mask(program):
    zoom_program = replace(
        program,
        allowed=replace(program.allowed, options=("zoom",)),
    )

    payload = build_start_payload(zoom_program, options=("zoom",))

    assert "&OptMsk1=0&OptMsk2=1&" in payload
```

- [ ] **Step 6: Run sender tests and checkpoint**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_sendprogram.py -q
```

Expected: all sender tests pass. Do not change `build_start_payload` merely to
satisfy legacy assertions, and do not create a Git commit.

---

### Task 3: Safe FastAPI dry-run and filtered endpoints

**Files:**
- Modify: `candy_web.py`
- Test: `tests/test_web.py`

**Interfaces:**
- Consumes: `require_startable_program(program)` and `startable_programs(catalog)`.
- Changes: `StartCmd` gains `dry_run: bool = True`.
- Changes: `POST /api/start` returns `sent=False, dry_run=True` without transport unless `dry_run` is explicitly false.

- [ ] **Step 1: Add failing legacy-OFF API tests**

In `tests/test_web.py`, add a helper:

```python
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
```

Add tests that monkeypatch `get_program_catalog` to this helper and verify:

```python
def test_legacy_off_is_hidden_from_program_and_config_endpoints(monkeypatch):
    monkeypatch.setattr(candy_web, "get_program_catalog", catalog_with_off)

    programs = CLIENT.get("/api/programs")
    config = CLIENT.get("/api/config")

    assert programs.status_code == 200
    assert "dual-wm-wd-off" not in [item["name"] for item in programs.json()]
    assert "dual-wm-wd-off" not in config.json()["programs"]


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
```

- [ ] **Step 2: Add failing dry-run API tests**

Add one parameterized test for omission and explicit true:

```python
@pytest.mark.parametrize("body", [
    {"program": "cotone"},
    {"program": "cotone", "dry_run": True},
])
def test_start_is_dry_run_without_explicit_false(monkeypatch, body):
    monkeypatch.setattr(candy_web, "get_program_catalog", catalog)
    monkeypatch.setattr(candy_web.c, "getkey", forbid_network)
    monkeypatch.setattr(candy_web.c, "send_command", forbid_network)

    response = CLIENT.post("/api/start", json=body)

    assert response.status_code == 200
    assert response.json()["sent"] is False
    assert response.json()["dry_run"] is True
    assert response.json()["payload"].startswith("Write=1&StSt=1&")
```

Modify tests that intentionally exercise real transport to include
`"dry_run": False`, especially sender success, sender failure, device HTTP
error, and exact option-mask cases.

- [ ] **Step 3: Run new API tests and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_web.py -k "technical_off or legacy_off or dry_run_without" -q
```

Expected: OFF remains exposed or reaches the payload builder, and omitted
`dry_run` still reaches transport.

- [ ] **Step 4: Implement filtered endpoints and safe start semantics**

In `candy_web.py`:

```python
from candy_programs import (
    # existing imports
    require_startable_program,
    startable_programs,
)


class StartCmd(BaseModel):
    program: str
    temp: int | None = None
    spin: int | None = None
    soil: int | None = None
    options: list[str] = Field(default_factory=list)
    dry_run: bool = True
```

Use `startable_programs(get_program_catalog())` in `/api/config` and
`/api/programs`. In `_render_option_controls`, collect enabled options only
from `startable_programs(catalog)`. In `index`, set `catalog_ready` from whether
that tuple is nonempty.

Guard before payload construction and return early for dry-run:

```python
        program = require_startable_program(
            get_program_catalog().by_name(cmd.program)
        )
        payload = c.build_start_payload(...)
    # existing exception mapping

    if cmd.dry_run:
        return {
            "sent": False,
            "dry_run": True,
            "payload": payload,
            "program": program_to_api(program),
        }

    # existing transport block
    return {
        "sent": True,
        "dry_run": False,
        "payload": payload,
        "response": response,
        "program": program_to_api(program),
    }
```

- [ ] **Step 5: Align exact Web payload assertions**

Replace old `Pa/Sel/TmpDf/SpdDef/OptMsk` expectations in
`tests/test_web.py` with the same full default payload specified in Task 2.
For mask assertions use embedded fields because later parameters follow them:

```python
assert f"&OptMsk1={expected_mask}&OptMsk2=0&" in response.json()["payload"]
```

Add `"dry_run": False` to those requests and assert the real-send response has
both `sent is True` and `dry_run is False`.

- [ ] **Step 6: Run FastAPI API tests and checkpoint**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_web.py -q
```

Expected: API tests pass; UI tests may remain red until Task 4. Do not create a
Git commit.

---

### Task 4: Guarded real-send checkbox and Zoom UI

**Files:**
- Modify: `candy_web.py`
- Test: `tests/test_web.py`

**Interfaces:**
- Consumes: `POST /api/start` dry-run contract from Task 3.
- Produces: HTML checkbox `#real-send`, button `#start-button`, and JavaScript `updateStartMode()` / `resetRealSend()` behavior.

- [ ] **Step 1: Add failing UI safety tests**

Extend the existing HTML page tests with assertions that verify the static
contract without executing a browser or contacting the appliance:

```python
def test_real_send_checkbox_is_unchecked_and_controls_dry_run(monkeypatch):
    monkeypatch.setattr(candy_web, "get_program_catalog", catalog)

    response = CLIENT.get("/")
    state = page_state(response)

    assert state.elements["real-send"]["type"] == "checkbox"
    assert "checked" not in state.elements["real-send"]
    assert "dry_run:!realSend" in response.text
    assert "if(realSend && !confirm(" in response.text
    assert "resetRealSend()" in response.text
    assert "Simula programma" in response.text


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
```

Add an API Zoom test with an explicit real-send body and fake sender; assert
`"&OptMsk1=0&OptMsk2=1&"` is in the sent payload.

- [ ] **Step 2: Run UI/Zoom tests and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_web.py -k "real_send_checkbox or zoom" -q
```

Expected: checkbox is absent, Zoom lacks the explicit label, or the API test
does not yet have the intended fixture.

- [ ] **Step 3: Implement the checkbox and mode-dependent UI**

Add `"zoom": "Zoom"` to `OPTION_LABELS`. Insert an unchecked checkbox before
the buttons:

```html
<label class="real-send-control">
  <input id="real-send" type="checkbox" onchange="updateStartMode()">
  Invio reale
</label>
```

Change the start button's initial text to `▷ Simula programma`. Add JavaScript:

```javascript
function updateStartMode(){
  $('start-button').textContent=$('real-send').checked
    ? '▶ Avvia lavaggio' : '▷ Simula programma';
}
function resetRealSend(){
  $('real-send').checked=false;
  updateStartMode();
}
```

Replace `start()` so it computes `realSend`, requires confirmation only for
real mode, adds `dry_run:!realSend`, and resets the checkbox safely:

```javascript
async function start(){
  const realSend=$('real-send').checked;
  const programName=$('prog').value;
  if(realSend && !confirm('Inviare realmente il programma '+programName+'?')){
    resetRealSend();
    return;
  }
  const opts=[...document.querySelectorAll('.chip input:checked')].map(c=>c.value);
  const body={program:programName, temp:+$('temp').value, spin:+$('spin').value,
    soil:+$('soil').value, options:opts, dry_run:!realSend};
  msg(realSend?'Invio comando…':'Validazione payload…','info');
  try{
    const r=await fetch('/api/start',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    const d=await r.json();
    if(!r.ok) throw new Error(d.detail||('HTTP '+r.status));
    const p=d.program;
    if(d.sent){
      msg('✓ Avviato: '+p.prstr,'ok');
      setTimeout(loadStatus,1500);
    }else{
      msg('✓ Simulazione valida: comando non inviato.','ok');
    }
  }catch(e){
    msg('✗ '+e.message,'err');
  }finally{
    if(realSend) resetRealSend();
  }
}
```

- [ ] **Step 4: Run Web tests and verify GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_web.py -q
```

Expected: all Web tests pass with fake transport only.

- [ ] **Step 5: Verify the current local catalog through TestClient**

Run a local-only Python command that monkeypatches transport to fail, requests
`/api/programs`, then dry-runs a known program. Assert there are 18 exposed
programs, no `DUAL_WM_WD_OFF`, and `sent` is false. Do not call `/api/status`,
`/api/stop`, or use `dry_run: false` in this check.

Expected: 18 programs and a successful dry-run with no transport call.

---

### Task 5: Full regression verification

**Files:**
- Verify only; do not modify `programs.json`.

**Interfaces:**
- Consumes all completed tasks.
- Produces verification evidence only.

- [ ] **Step 1: Record that the catalog file is unchanged**

Compute and retain the SHA-256 hash of `programs.json` before final tests. After
all tests, compute it again and require an exact match.

- [ ] **Step 2: Run the complete test suite**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Expected: all tests pass; no test reaches Candy Cloud or the washer.

- [ ] **Step 3: Compile changed Python modules**

Run:

```powershell
.\.venv\Scripts\python.exe -m py_compile candy_programs.py candy_import_programs.py candy_sendprogram.py candy_web.py
```

Expected: exit code 0 with no output.

- [ ] **Step 4: Recheck the catalog hash and report**

Require the final `programs.json` SHA-256 to equal the hash from Step 1. Report
test totals, the 18-program local TestClient result, dry-run behavior, and the
fact that no real device command was sent. Do not claim success if any command
failed.
