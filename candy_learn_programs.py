#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Acquisizione guidata dei programmi del TUO modello di lavatrice Candy.

Uso:
    python candy_learn_programs.py

Procedura (per ogni programma):
    1. Gira la manopola della lavatrice per selezionare il programma
    2. Torna qui e premi INVIO
    3. Digita un nome comodo per quel programma (es. "cotone", "rapidi30")
       - OPPURE premi INVIO senza nome per usare il codice "Pr" automatico
       - OPPURE scrivi 'q' per terminare
Lo script legge Pr/PrCode/Temp/SpinSp/SLevel dalla macchina e li salva in
'programs.json'. Alla fine puoi copiare la tabella in candy_sendprogram.py.
"""

import argparse
import json
import os
import re
import sys
import candy_sendprogram as c

PROG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         'programs.json')


def load_existing():
    if os.path.exists(PROG_FILE):
        try:
            with open(PROG_FILE, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save(programs):
    with open(PROG_FILE, "w", encoding="utf-8") as f:
        json.dump(programs, f, indent=2, ensure_ascii=False)


def read_program():
    """Legge un programma dalla macchina. Ritorna dict o None se offline."""
    try:
        key = c.getkey()
        d = json.loads(c.read_status(key))["statusLavatrice"]
        return {
            "prnm": int(d.get("Pr", 0)),
            "prcode": int(d.get("PrCode", 0)),
            "temp": int(d.get("Temp", 0)),
            "spin": int(d.get("SpinSp", 0)),
            "soil": int(d.get("SLevel", 2)),
        }
    except Exception as e:
        print("  ! Impossibile leggere dalla lavatrice: %s" % e)
        return None


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
        print(
            "La BWM 149PH7 esclude il controllo remoto quando si usa la manopola.",
            file=sys.stderr,
        )
        print("Usa invece: python candy_import_programs.py", file=sys.stderr)
        return 2
    return legacy_main()


def legacy_main():
    c.CANDY_IP = '192.168.1.235'
    programs = load_existing()
    print("=" * 56)
    print(" ACQUISIZIONE PROGRAMMI LAVATRICE CANDY")
    print("=" * 56)
    print("IP:", c.CANDY_IP)
    if programs:
        print("Programmi gia' acquisiti:", len(programs))
        for n, p in sorted(programs.items(), key=lambda x: x[1]["prnm"]):
            print("   %-14s Pr=%-2d Code=%-2d %d°C spin=%s" %
                  (n, p["prnm"], p["prcode"], p["temp"], p["spin"]))
    print("-" * 56)
    print("PROCEDURA:")
    print(" 1) Gira la manopola della lavatrice sul programma desiderato")
    print(" 2) Torna qui e premi INVIO")
    print(" 3) Dai un nome (es. cotone) / INVIO=usa Pr / 'q'=esci")
    print("-" * 56)

    while True:
        ans = input("\nManopola impostata? Premi INVIO per leggere (q=esci): ").strip()
        if ans.lower() == 'q':
            break
        prog = read_program()
        if not prog:
            print("  Riprova tra qualche secondo (la lavatrice potrebbe essere offline).")
            continue

        default_name = "prog_%d" % prog["prnm"]
        print("  Letto: Pr=%d  PrCode=%d  Temp=%d°C  SpinSp=%d  SLevel=%d" %
              (prog["prnm"], prog["prcode"], prog["temp"], prog["spin"], prog["soil"]))
        name = input("  Nome per questo programma [INVIO=%s, q=annulla]: " % default_name).strip()
        if name.lower() == 'q':
            continue
        name = name or default_name
        programs[name] = prog
        save(programs)
        print("  -> Salvato '%s' in programs.json" % name)

    # riepilogo finale + frammento python da incollare
    print("\n" + "=" * 56)
    print(" ACQUISIZIONE COMPLETATA: %d programmi" % len(programs))
    print("=" * 56)
    if programs:
        print("\nCopia questo blocco in candy_sendprogram.py (variabile PROGRAMS):\n")
        print("PROGRAMS = {")
        for n in sorted(programs, key=lambda x: programs[x]["prnm"]):
            p = programs[n]
            print("    %-16r: (%d, %2d, %-16r, %2d, %2d, %d)," %
                  (n, p["prnm"], p["prcode"],
                   _prstr_guess(n, p), p["temp"], p["spin"], p["soil"]))
        print("}")
        print("\nSalvato anche in: %s" % PROG_FILE)
    return 0


def _prstr_guess(name, p):
    """Tenta un nome leggibile per PrStr dal nome dato."""
    m = {"cotone": "Cotton", "cotone_eco": "Cotton Eco",
         "sintetici": "Synthetics", "delicati": "Delicates",
         "lana": "Wool", "risciacquo": "Rinse", "centrifuga": "Spin",
         "rapidi30": "Rapid 30", "sport": "Sport"}
    return m.get(name, name.title())


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nInterrotto. I dati sono comunque salvati in programs.json.")
        raise SystemExit(130)
