# Candy Empty Command Parameters Compatibility Design

**Date:** 2026-08-01  
**Status:** Implemented and verified with an authorized external baseline exception  
**Scope:** Allow the real BWM 149PH7 cloud catalog to contain command
parameters whose `validation` value is an empty string, without weakening the
required program mapping.

## Observed failure

The first successful Windows browser authentication and Candy cloud fetch
reached catalog normalization, then failed with:

```text
program.command_parameters[8].validation: stringa non vuota obbligatoria
```

No catalog was saved. This proves that the cloud response can contain an empty
`validation` value even though the fixture-only contract required every value
to be non-empty.

## Chosen behavior

`flatten_parameters()` continues to require every parameter record to contain
a non-empty string `name` and a string `validation`. It also continues to
reject duplicate names. When `validation == ""`, the parameter is treated as
absent and is not added to the flattened mapping.

Semantic validation remains downstream and fail-closed:

- `selector_position`, `pr_code`, `default_temperature`,
  `default_spin_speed`, and `default_soil_level` remain mandatory integers;
- an empty mandatory parameter is therefore rejected as missing by
  `_required_int()`;
- empty optional allowed-value lists fall back to the corresponding validated
  default;
- empty option masks behave as absent and therefore select no options;
- empty optional `steam` or `dry` values behave as absent and retain zero;
- non-string values, malformed records, and duplicate names remain errors.

This correction changes only catalog normalization. Authentication, cloud
headers, token handling, catalog schema, atomic saving, payload generation,
transport, and appliance behavior remain unchanged.

## Security and persistence

The correction does not log or persist the cloud response, callback, or
tokens. A failed normalization still occurs before `save_catalog_atomic()`, so
the current catalog and backup remain unchanged. Importing programs and all
offline tests issue no appliance command.

## Test design

Behavior-first tests will prove that:

1. an unused parameter with an empty string is ignored and a valid program is
   normalized successfully;
2. an optional recognized parameter with an empty string uses its documented
   absence fallback;
3. a mandatory parameter with an empty string is still rejected with its
   semantic field name;
4. duplicate names remain rejected even when one duplicate is empty;
5. the complete offline suite remains green.

The first new test must fail against the current implementation before the
production change is written. No real browser, Candy cloud, or appliance call
is part of automated verification.

## Acceptance criteria

1. The observed empty non-essential `validation` no longer rejects the real
   catalog.
2. Empty mandatory mapping values still reject the catalog before saving.
3. No token or raw cloud response is printed or persisted.
4. Existing catalog and payload behavior remain unchanged.
5. The full offline suite passes.

## Out of scope

- persisting raw cloud responses for diagnosis;
- loosening required selector, program code, or default values;
- changing the local catalog schema;
- changing program payload mapping or appliance transport;
- issuing a real washer start.
