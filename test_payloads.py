#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Test sistematico di varianti di payload per avviare perfect-rapid-59.
Prova formati diversi documentati dalla community, per scoprire quale
(se mai) il firmware del BWM 149PH7 accetta davvero.

Per ogni variante: invia, aspetta, legge lo stato, confronta con i valori
attesi (Pr=15, Temp=40, SLevel=0) e fa lo STOP.
"""

import sys
import time
import json
import candy_sendprogram as c

c.CANDY_IP = '192.168.1.235'
TIMEOUT = 10

# valori attesi per perfect-rapid-59
EXPECTED = {"Pr": "15", "PrCode": "8", "Temp": "40", "SLevel": "0"}

# payload completi (presi dalla documentazione community smulle48)
PAYLOADS = [
    # 1) formato originale community (completo, con tutti i campi)
    ("community-full",
     "Write=1&StSt=1&DelVl=0&PrNm=15&PrCode=8&PrStr=Perfect Rapid 59&"
     "TmpTgt=40&SLevTgt=0&SpdTgt=10&OptMsk1=0&OptMsk2=0&Lang=1&Stm=0&"
     "Dry=0&RecipeId=0&StartCheckUp=0&DispTestOn=1"),
    # 2) senza Write e senza DelVl (variante minimale)
    ("minimal-nocode",
     "StSt=1&PrNm=15&PrCode=8&TmpTgt=40&SLevTgt=0&SpdTgt=10"),
    # 3) con RecipeId esplicito (alcuni firmware lo richiedono)
    ("with-recipe",
     "Write=1&StSt=1&PrNm=15&PrCode=8&PrStr=PerfectRapid59&"
     "TmpTgt=40&SLevTgt=0&SpdTgt=10&RecipeId=0&RecipeStep=0"),
    # 4) formato key=value senza Write (alcuni modelli vecchi)
    ("no-write",
     "StSt=1&PrNm=15&PrCode=8&TmpTgt=40&SLevTgt=0&SpdTgt=10&OptMsk=0"),
    # 5) con Pa (pause) e Sel (selector) espliciti
    ("with-pasel",
     "Write=1&Pa=0&Sel=0&StSt=1&PrNm=15&PrCode=8&"
     "TmpTgt=40&SLevTgt=0&SpdTgt=10&OptMsk=0"),
    # 6) formato con Pr e non PrNm (alcuni firmware usano Pr)
    ("using-pr",
     "Write=1&StSt=1&Pr=15&PrCode=8&TmpTgt=40&SLevTgt=0&SpdTgt=10"),
    # 7) solo PrNm + StSt (formato piu' semplice possibile)
    ("bare-minimum",
     "StSt=1&PrNm=15"),
]


def leggi_stato(key):
    raw = __import__('requests').get(
        "http://" + c.CANDY_IP + "/http-read.json?encrypted=1",
        timeout=TIMEOUT).text
    return json.loads(c.xor_decode(raw, key))["statusLavatrice"]


def accettato(stato):
    """True se lo stato riflette i parametri inviati."""
    return (stato.get("Pr") == EXPECTED["Pr"]
            and stato.get("Temp") == EXPECTED["Temp"]
            and stato.get("SLevel") == EXPECTED["SLevel"])


def stop(key):
    payload = "Write=1&StSt=0&PrNm=15"
    try:
        c.send_command(payload, key)
    except Exception:
        pass
    time.sleep(3)


def main():
    key = c.getkey()
    print("Chiave:", key)
    print("Atteso per perfect-rapid-59:", EXPECTED)
    print("=" * 60)

    risultati = []
    for nome, payload in PAYLOADS:
        print("\n>>> TEST: %s" % nome)
        print("    payload: %s" % payload[:80] + ("..." if len(payload) > 80 else ""))
        try:
            # stato prima
            prima = leggi_stato(key)
            # invia
            resp = c.send_command(payload, key)
            print("    risposta raw:", resp[:16], "...")
            try:
                dec = c.xor_decode(resp, key)
                print("    risposta dec:", dec)
            except Exception:
                pass
            # aspetta e leggi
            time.sleep(4)
            dopo = leggi_stato(key)
            print("    stato dopo: Pr=%s Temp=%s SLevel=%s MachMd=%s" % (
                dopo.get("Pr"), dopo.get("Temp"), dopo.get("SLevel"), dopo.get("MachMd")))
            ok = accettato(dopo)
            print("    >> RISULTATO: %s" % ("ACCETTATO!" if ok else "ignorato"))
            risultati.append((nome, ok))
            # se e' partito, fermalo
            if dopo.get("MachMd") == "2":
                print("    fermo il programma...")
                stop(key)
        except Exception as e:
            print("    ERRORE:", type(e).__name__, e)
            risultati.append((nome, False))

    print("\n" + "=" * 60)
    print("RIEPILOGO TEST PAYLOAD:")
    for nome, ok in risultati:
        print("  %-20s %s" % (nome, "ACCETTATO" if ok else "ignorato"))
    if not any(ok for _, ok in risultati):
        print("\nNESSUN payload e' stato accettato dal firmware.")
        print("Conferma: l'API locale del BWM 149PH7 non supporta l'avvio programmi.")


if __name__ == "__main__":
    main()
