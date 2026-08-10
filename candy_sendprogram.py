#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Invio programmi di lavaggio alla lavatrice Candy via API locale.

Protocollo:
  - La chiave si ottiene da http://<ip>/http-write.json?encrypted=1&BM=1
    (XOR tra i 16 byte restituiti e la stringa nota '{"response":"SUCCESS"}').
  - Il payload di comando (plaintext) viene XOR-cifrato con la chiave
    (ripetuta) e convertito in esadecimale, poi inviato come:
    http://<ip>/http-write.json?encrypted=1&data=<hex>

I payload di avvio vengono costruiti esclusivamente dai programmi
importati dal cloud e dalle rispettive opzioni consentite.
"""

import os
import sys
import json
import argparse
from collections.abc import Iterable
from pathlib import Path

import requests

from candy_programs import (
    OPTION_BITS,
    CatalogError,
    OverrideError,
    ProgramDefinition,
    load_catalog,
    require_startable_program,
    startable_programs,
    validate_overrides,
)

CANDY_IP = '192.168.1.235'
TIMEOUT = 10

# stringa nota usata per ricavare la chiave di cifratura
KNOWN_RESPONSE = '{"response":"SUCCESS"}'

# plaintext noto all'inizio della risposta di stato (per fallback + validazione)
KNOWN_STATUS_PREFIX = '{\r\n\t"statusLavatrice":{\r\n\t\t"WiFiStatus":"'

# file di cache della chiave (la chiave e' fissa per dispositivo)
_KEY_CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          'candy_key.cache')


# ----------------------------------------------------------------------------
# Crittografia / comunicazione
# ----------------------------------------------------------------------------
def _key_valid(key):
    """Verifica che la chiave decodifichi correttamente lo stato corrente."""
    try:
        response = requests.get(
            "http://" + CANDY_IP + "/http-read.json?encrypted=1",
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        raw = response.text
        return '"statusLavatrice"' in xor_decode(raw, key)
    except Exception:
        return False


def _key_from_read():
    """Recupera la chiave dal read endpoint via attacco known-plaintext.
    Usa il prefisso noto della risposta di stato per derivare tutti i 16 byte."""
    try:
        response = requests.get(
            "http://" + CANDY_IP + "/http-read.json?encrypted=1",
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        raw = response.text
    except Exception:
        return None
    known = KNOWN_STATUS_PREFIX
    partial = {}
    for i in range(len(known)):
        k = chr(int(raw[i * 2:i * 2 + 2], 16) ^ ord(known[i]))
        pos = i % 16
        if pos in partial and partial[pos] != k:
            return None  # incoerente: plaintext non combacia
        partial[pos] = k
    if len(partial) == 16:
        return "".join(partial[i] for i in range(16))
    return None


def _save_cache(key):
    try:
        with open(_KEY_CACHE, "w") as f:
            f.write(key)
    except Exception:
        pass


def _load_cache():
    try:
        with open(_KEY_CACHE) as f:
            return f.read().strip()
    except Exception:
        return None


def getkey():
    """Recupera la chiave di cifratura in modo robusto:
    1) cache su disco (se valida)
    2) estrazione da BM=1 (se valida)
    3) fallback known-plaintext sul read endpoint
    La prima chiave valida trovata viene cachata per gli usi successivi."""
    # 1) cache
    cached = _load_cache()
    if cached and _key_valid(cached):
        return cached

    # 2) BM=1
    try:
        response = requests.get(
            "http://" + CANDY_IP + "/http-write.json?encrypted=1&BM=1",
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        hex_in = response.text
        key = "".join(
            chr(ord(KNOWN_RESPONSE[i]) ^ int(hex_in[i * 2:i * 2 + 2], 16))
            for i in range(0, min(16, len(KNOWN_RESPONSE))))[:16]
        if _key_valid(key):
            _save_cache(key)
            return key
    except Exception:
        pass

    # 3) fallback known-plaintext
    key = _key_from_read()
    if key:
        _save_cache(key)
        return key

    # nessuna via ha validato: best-effort con BM=1 grezzo
    return key


def xor_decode(hex_text, key):
    """Decifra una risposta esadecimale in testo."""
    return "".join(
        chr(ord(key[idx % len(key)]) ^ int(hex_text[i:i + 2], 16))
        for idx, i in enumerate(range(0, len(hex_text), 2)))


def xor_encode(plaintext, key):
    """Cifra un testo in chiaro -> stringa esadecimale (per il parametro data)."""
    return "".join(
        format(ord(plaintext[i]) ^ ord(key[i % len(key)]), '02x')
        for i in range(len(plaintext)))


def send_command(payload, key):
    """Invia un payload di comando cifrato alla lavatrice e restituisce la risposta."""
    hex_data = xor_encode(payload, key)
    url = "http://" + CANDY_IP + "/http-write.json?encrypted=1&data=" + hex_data
    response = requests.get(url, timeout=TIMEOUT)
    response.raise_for_status()
    return response.text


def read_status(key):
    """Legge lo stato corrente della lavatrice (json decifrato)."""
    response = requests.get(
        "http://" + CANDY_IP + "/http-read.json?encrypted=1",
        timeout=TIMEOUT,
    )
    response.raise_for_status()
    raw = response.text
    return xor_decode(raw, key)


# ----------------------------------------------------------------------------
# Costruzione payload
# ----------------------------------------------------------------------------
def build_start_payload(
    program: ProgramDefinition,
    *,
    temp: int | None = None,
    spin: int | None = None,
    soil: int | None = None,
    options: Iterable[str] = (),
) -> str:
    """Costruisce il payload di avvio IDENTICO a quello dell'app Candy.

    Formato ricavato dal codice decompilato dell'app (CommandService +
    Command.getParameterString). Il firmware del BWM 149PH7 richiede il
    payload completo (con PrCode, PrStr, OptMsk1/2, Lang, Stm, Dry,
    RecipeId, StartCheckUp, DispTestOn, ED) per accettare il cambio
    programma; un payload parziale viene ignorato e la macchina avvia
    l'ultimo programma in memoria."""
    selected_options = tuple(options)
    validate_overrides(
        program,
        temp=temp,
        spin=spin,
        soil=soil,
        options=selected_options,
    )
    # risolve il valore effettivo: override se fornito, altrimenti default
    effective_temp = temp if temp is not None else program.defaults.temp
    effective_spin = spin if spin is not None else program.defaults.spin
    effective_soil = soil if soil is not None else program.defaults.soil

    if effective_spin % 100 or program.defaults.spin % 100:
        raise OverrideError("Centrifuga non rappresentabile dal protocollo Candy.")

    # bitmask opzioni: OptMsk1 (bit 0-7) e OptMsk2 (bit 0-N seconda maschera)
    mask1 = 0
    mask2 = 0
    for name in selected_options:
        which, bit = OPTION_BITS[name]
        if which == 1:
            mask1 |= bit
        else:
            mask2 |= bit

    # payload completo come da Command.getParameterString() dell'app
    parts = [
        "Write=1",
        f"StSt=1",
        f"DelVl=0",                              # DelVl: delay (nessun ritardo)
        f"PrNm={program.prnm}",                  # selectorPosition
        f"PrCode={program.prcode}",              # programCode
        f"PrStr={program.prstr}",                # nome localizzato
        f"TmpTgt={effective_temp}",              # temperatura target
        f"SLevTgt={effective_soil}",             # livello sporco target
        f"SpdTgt={effective_spin // 100}",       # centrifuga / 100
        f"OptMsk1={mask1}",                      # bitmask opzioni (maschera 1)
        f"OptMsk2={mask2}",                      # seconda bitmask
        f"Lang=1",                               # lingua (1=italiano)
        f"Stm={program.defaults.steam}",         # steam
        f"Dry={program.defaults.dry}",           # asciugatura
        f"ED=0",                                 # extra dose
        f"RecipeId=0",                           # recipe id
        f"StartCheckUp=0",                       # checkup
        f"DispTestOn=1",                         # display test
    ]
    return "&".join(parts)


def start_named_program(
    name,
    *,
    catalog_path=Path("programs.json"),
    temp=None,
    spin=None,
    soil=None,
    options=(),
    dry_run=False,
    key_provider=getkey,
    sender=send_command,
) -> str:
    """Valida un avvio nominato prima di accedere a chiave o trasporto."""
    try:
        catalog = load_catalog(catalog_path)
    except CatalogError as error:
        raise CatalogError(
            "Catalogo programmi non disponibile. "
            "Esegui: python candy_import_programs.py"
        ) from error
    program = require_startable_program(catalog.by_name(name))
    payload = build_start_payload(
        program,
        temp=temp,
        spin=spin,
        soil=soil,
        options=options,
    )
    if not dry_run:
        sender(payload, key_provider())
    return payload


# ----------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------
def cmd_status(args, key):
    print(read_status(key))


def cmd_list(args, key):
    catalog = load_catalog(Path("programs.json"))
    print("Programmi disponibili dal catalogo importato:\n")
    print("%-12s %-6s %-7s %-16s %-5s %-5s %-5s" %
          ("NOME", "PrNm", "PrCode", "PrStr", "Temp", "Spin", "Soil"))
    print("-" * 60)
    for program in sorted(startable_programs(catalog), key=lambda item: item.name):
        print("%-12s %-6d %-7d %-16s %-5d %-5d %-5d" %
              (program.name, program.prnm, program.prcode, program.prstr,
               program.defaults.temp, program.defaults.spin,
               program.defaults.soil))


def cmd_start(args, key):
    payload = start_named_program(
        args.program,
        temp=args.temp,
        spin=args.spin,
        soil=args.soil,
        options=args.options,
        dry_run=args.dry_run,
        key_provider=getkey,
        sender=send_command,
    )

    if args.dry_run:
        print("DRY-RUN - comando NON inviato.\n")
        print("Payload (plaintext):")
        print("  " + payload)
        return

    print("Avvio programma '%s' inviato." % args.program)


def cmd_stop(args, key):
    """Ferma il ciclo corrente: StSt=0 con il programma attualmente in uso."""
    stato = json.loads(read_status(key))["statusLavatrice"]
    prnm = stato.get("Pr", "0")
    payload = "Write=1&StSt=0&PrNm=%s" % prnm

    if args.dry_run:
        print("DRY-RUN - comando NON inviato.\n")
        print("Payload (plaintext):\n  " + payload)
        print("\nPayload cifrato (hex):\n  " + xor_encode(payload, key))
        return

    print("Invio comando di STOP (PrNm=%s)..." % prnm)
    resp = send_command(payload, key)
    print("Risposta dispositivo:")
    try:
        print(json.dumps(json.loads(resp), indent=2))
    except ValueError:
        print(resp)


def main(argv=None):
    global CANDY_IP
    p = argparse.ArgumentParser(
        description="Invio programmi di lavaggio alla lavatrice Candy via API locale.")
    p.add_argument("--ip", default=CANDY_IP, help="IP della lavatrice (default: %s)" % CANDY_IP)
    sub = p.add_subparsers(dest="command")
    sub.required = True

    # status
    sp = sub.add_parser("status", help="Mostra lo stato corrente")
    sp.set_defaults(func=cmd_status)

    # list
    sp = sub.add_parser("list", help="Elenca i programmi disponibili")
    sp.set_defaults(func=cmd_list)

    # start
    sp = sub.add_parser("start", help="Avvia un programma di lavaggio")
    sp.add_argument("--program", "-p", required=True,
                    help="Nome programma importato (vedi list)")
    sp.add_argument("--temp", type=int, help="Temperatura °C (TmpTgt)")
    sp.add_argument("--spin", type=int, help="Centrifuga espressa in rpm")
    sp.add_argument("--soil", type=int, help="Livello sporco (1-3)")
    sp.add_argument("--options", "-o", nargs="*", default=(),
                    help="Opzioni ammesse dal programma importato")
    sp.add_argument("--dry-run", action="store_true",
                    help="Mostra il payload senza inviarlo")
    sp.set_defaults(func=cmd_start)

    # stop
    sp = sub.add_parser("stop", help="Ferma il ciclo corrente")
    sp.add_argument("--dry-run", action="store_true",
                    help="Mostra il payload senza inviarlo")
    sp.set_defaults(func=cmd_stop)

    args = p.parse_args(argv)
    CANDY_IP = args.ip

    # 'list' non necessita di connessione
    if args.command == "list":
        try:
            args.func(args, None)
        except CatalogError as error:
            print(error)
            return 2
        return 0

    if args.command == "start":
        try:
            args.func(args, None)
        except CatalogError as error:
            print(error)
            return 2
        except Exception as error:
            print("Impossibile inviare il comando a %s: %s" % (CANDY_IP, error))
            return 1
        return 0

    try:
        key = getkey()
    except Exception as e:
        print("Impossibile ottenere la chiave da %s: %s" % (CANDY_IP, e))
        return 1

    args.func(args, key)
    return 0


if __name__ == "__main__":
    sys.exit(main())
