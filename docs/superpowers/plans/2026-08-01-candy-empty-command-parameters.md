# Candy Empty Command Parameters Compatibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Import the real BWM 149PH7 catalog when Candy includes empty non-essential command-parameter values, while rejecting empty mandatory mapping values.

**Architecture:** Keep `flatten_parameters()` responsible only for structural validation and indexing. Treat an empty-string value as absent, then let the existing semantic consumers enforce mandatory integers and apply existing optional fallbacks.

**Tech Stack:** Python 3, pytest, existing `CatalogError` and catalog normalization pipeline.

## Global Constraints

- Modify only catalog-normalization behavior and its offline tests.
- A parameter `name` must remain a non-empty string and `validation` must remain a string.
- Duplicate parameter names remain invalid even if one value is empty.
- Empty mandatory selector, program code, temperature, spin, or soil defaults remain invalid.
- Do not change authentication, cloud headers, token handling, local catalog schema, payload generation, transport, or appliance behavior.
- Do not print or persist raw cloud responses, callbacks, or tokens.
- Do not open a real browser, contact Candy cloud, or issue an appliance command during implementation or automated verification.
- The workspace is not Git; do not initialize Git or create commits.

---

### Task 1: Treat empty cloud values as absent without weakening required fields

**Files:**

- Modify: `tests/test_import.py`
- Modify: `candy_import_programs.py:118-139`
- Verify: all Python tests

**Interfaces:**

- Consumes: `flatten_parameters(program: dict[str, object]) -> dict[str, str]` and `normalize_catalog(appliance: dict[str, object], *, imported_at: datetime) -> ProgramCatalog`.
- Produces: the same public signatures; flattened mappings omit entries whose `validation` is exactly `""` while downstream semantic checks remain unchanged.

- [x] **Step 1: Add behavior-first regression tests**

Add these cases to `tests/test_import.py` using `first_appliance()` and the existing fixture helpers:

```python
def test_empty_unused_parameter_is_ignored_during_normalization():
    appliance = first_appliance()
    appliance["programs"][0]["program"]["command_parameters"].append(
        {
            "command_parameter": {
                "name": "unused_cloud_metadata",
                "validation": "",
            }
        }
    )

    catalog = normalize_catalog(appliance, imported_at=IMPORTED_AT)

    assert catalog.programs[0].name == "cotone"


def test_empty_optional_option_mask_uses_absence_fallback():
    appliance = first_appliance()
    parameters = appliance["programs"][0]["program"]["command_parameters"]
    next(
        item
        for item in parameters
        if item["command_parameter"]["name"] == "available_options"
    )["command_parameter"]["validation"] = ""

    program = normalize_catalog(appliance, imported_at=IMPORTED_AT).programs[0]

    assert program.allowed.options == ()


def test_empty_required_parameter_is_rejected_by_semantic_name():
    appliance = first_appliance()
    parameters = appliance["programs"][0]["program"]["command_parameters"]
    next(
        item
        for item in parameters
        if item["command_parameter"]["name"] == "default_temperature"
    )["command_parameter"]["validation"] = ""

    with pytest.raises(CatalogError, match="default_temperature"):
        normalize_catalog(appliance, imported_at=IMPORTED_AT)


def test_duplicate_parameter_name_is_rejected_when_first_value_is_empty():
    raw_program = first_appliance()["programs"][0]["program"]
    raw_program["command_parameters"].insert(
        0,
        {"command_parameter": {"name": "pr_code", "validation": ""}},
    )

    with pytest.raises(CatalogError, match="pr_code.*duplicato"):
        flatten_parameters(raw_program)
```

- [x] **Step 2: Run the focused regression tests and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_import.py -q -o cache_dir=.pytest-empty-params-red
```

Expected: the two acceptance tests fail at the old non-empty structural check. The mandatory and duplicate cases may already pass; record their results separately rather than weakening them.

- [x] **Step 3: Implement the minimal structural correction**

In `flatten_parameters()`, validate type and duplicate status before deciding whether to omit an empty value:

```python
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
    if not isinstance(validation, str):
        raise CatalogError(f"{path}.validation: stringa obbligatoria")
    if name in seen_names:
        raise CatalogError(f"command_parameters.{name}: nome duplicato")
    seen_names.add(name)
    if validation == "":
        continue
    parameters[name] = validation
return parameters
```

Do not change `_required_int()`, `_allowed_ints()`, `_allowed_options()`, or catalog persistence.

- [x] **Step 4: Run focused tests and verify GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_import.py -q -o cache_dir=.pytest-empty-params-green
```

Expected: every importer test passes, including all four new cases.

- [x] **Step 5: Run syntax and full offline verification**

Run:

```powershell
.\.venv\Scripts\python.exe -m py_compile candy_import_programs.py
.\.venv\Scripts\python.exe -m pytest -q -o cache_dir=.pytest-empty-params-final
```

Expected: compilation exits 0; the complete suite passes with only the existing accepted Starlette/TestClient deprecation warning.

- [x] **Step 6: Review scope and record evidence**

Confirm that only `tests/test_import.py`, `candy_import_programs.py`, this plan, and the approved design were changed. Record the RED result, focused GREEN result, full-suite count, known warning, and `No browser, Candy cloud, or appliance command executed during automated verification` in:

```text
.superpowers/sdd/2026-08-01-candy-empty-command-parameters/task-1-report.md
```

Because the workspace is not Git, record `commits unavailable — no Git repository` instead of committing.
