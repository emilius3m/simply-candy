#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Diagnostica: stampa i valori available_options/available_options2 dei programmi
che il cloud restituisce per capire quali bit non sono mappati in OPTION_BITS.
NON salva nulla, serve solo a ispezionare."""

from __future__ import annotations
import getpass
import sys
from pathlib import Path
import webbrowser

from candy_ciam import begin_ciam_login, complete_ciam_login, CiamAuthError
from candy_cloud import CandyCloudClient, CandyCloudError
from candy_import_programs import find_matching_washers


def diagnostic_parameters(raw):
    """Indicizza i valori validi e descrive quelli anomali senza dati grezzi."""
    params = {}
    anomalies = []
    records = raw.get("command_parameters", [])
    if not isinstance(records, list):
        return params, ["command_parameters non-lista"]
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            anomalies.append("[%d] record %s" % (index, type(record).__name__))
            continue
        value = record.get("command_parameter", record)
        if not isinstance(value, dict):
            anomalies.append("[%d] wrapper %s" % (index, type(value).__name__))
            continue
        name = value.get("name")
        validation = value.get("validation")
        if not isinstance(name, str) or not name:
            anomalies.append("[%d] nome %s" % (index, type(name).__name__))
            continue
        if isinstance(validation, str):
            params[name] = validation
            continue
        if validation is None:
            rendered = "<null>"
        elif isinstance(validation, (int, float, bool)):
            rendered = repr(validation)
        else:
            rendered = "<%s>" % type(validation).__name__
        anomalies.append(
            "[%d] %s: %s (%s)"
            % (index, name, rendered, type(validation).__name__)
        )
    return params, anomalies


def set_bits(value):
    try:
        number = int(value)
    except (TypeError, ValueError):
        return []
    return [bit for bit in range(32) if number & (1 << bit)]


def main():
    print("=== Login Candy (stesso flusso di candy_import_programs.py) ===")
    pending = begin_ciam_login()
    print("Apri questa pagina per accedere a Candy:")
    print(pending.authorization_url)
    try:
        webbrowser.open(pending.authorization_url)
    except Exception:
        pass
    print("Dopo l'accesso copia l'indirizzo candy:// e incollalo QUI (input nascosto).")
    callback_url = getpass.getpass("Callback Candy (input nascosto): ")
    id_token = complete_ciam_login(pending, callback_url)

    client = CandyCloudClient(id_token)
    records = client.fetch_appliances()
    matches = find_matching_washers(records, "BWM 149PH7")
    if not matches:
        print("Nessuna BWM 149PH7 trovata.")
        return 1

    appliance = matches[0]
    programs = appliance.get("programs", [])
    print("\n" + "=" * 60)
    print("Trovati %d programmi. Valori opzioni:" % len(programs))
    print("=" * 60)
    for idx, precord in enumerate(programs):
        raw = precord.get("program", precord) if isinstance(precord, dict) else {}
        name = raw.get("name", "?")
        params, anomalies = diagnostic_parameters(raw)
        m1 = params.get("available_options", "?")
        m2 = params.get("available_options2", "?")
        print(
            "[%2d] %-45s opt1=%-6s bits1=%-24s opt2=%-6s bits2=%s"
            % (idx, str(name)[:45], m1, set_bits(m1), m2, set_bits(m2))
        )
        for anomaly in anomalies:
            print("     ANOMALIA %s" % anomaly)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (CiamAuthError, CandyCloudError) as e:
        print("Errore cloud: %s" % e, file=sys.stderr)
        sys.exit(3)
