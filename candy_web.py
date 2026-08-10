#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Interfaccia web per la lavatrice Candy (FastAPI) — auto-reload attivo.

Avvio:
    python candy_web.py
Poi apri:  http://localhost:8000

Riutilizza la logica di candy_sendprogram.py (crittografia XOR, lettura
stato, costruzione payload). Lo stato si aggiorna SOLO su richiesta
(pulsante "Aggiorna").
"""

import json
from dataclasses import asdict
from html import escape
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field, StrictBool

import candy_sendprogram as c
from candy_programs import (
    OPTION_BITS,
    CatalogUnavailableError,
    OverrideError,
    UnknownProgramError,
    load_catalog,
    require_startable_program,
    startable_programs,
)

app = FastAPI(title="Candy Lavatrice")

# IP configurabile a runtime (default dal modulo importato)
candy_ip = c.CANDY_IP
PROGRAMS_PATH = Path("programs.json")
OPTION_LABELS = {
    "prewash": "Prewash",
    "hygiene": "Hygiene+",
    "anti_crease": "Antipiega",
    "good_night": "Good Night",
    "extra_rinse_1": "Risciacquo extra 1",
    "extra_rinse_2": "Risciacquo extra 2",
    "extra_rinse_3": "Risciacquo extra 3",
    "aquaplus": "Aqua Plus",
    "zoom": "Zoom",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _set_ip(ip: str):
    global candy_ip
    candy_ip = ip or c.CANDY_IP
    c.CANDY_IP = candy_ip  # le funzioni del modulo leggono da qui


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


def _render_option_controls(catalog):
    enabled = {
        option
        for program in startable_programs(catalog)
        for option in program.allowed.options
    }
    return "\n".join(
        '<label class="chip"><input type="checkbox" value="%s"> %s</label>'
        % (escape(identifier), escape(OPTION_LABELS.get(identifier, identifier)))
        for identifier in OPTION_BITS
        if identifier in enabled
    )


def _status_raw():
    """Legge stato grezzo: ritorna dict con chiavi 'online' e (se online) i dati."""
    try:
        c.CANDY_IP = candy_ip
        key = c.getkey()
        stato = json.loads(c.read_status(key))
        return {"online": True, "key_ok": True,
                "data": stato.get("statusLavatrice", stato)}
    except Exception as e:
        # prova almeno a capire se e' un problema di rete
        return {"online": False, "key_ok": False, "error": str(e)}


def _machmd_label(v):
    return {
        "1": "Inattiva", "2": "In funzione", "3": "Pausa",
        "5": "Avvio ritardato", "6": "Errore", "9": "Terminato",
    }.get(str(v), "Sconosciuto (" + str(v) + ")")


def _prph_label(v):
    return {
        "0": "Attesa", "1": "Prelavaggio", "2": "Lavaggio",
        "3": "Risciacquo", "4": "Centrifuga", "5": "Antipiegga",
        "6": "Vapore", "7": "Terminato",
    }.get(str(v), "Fase " + str(v))


# ---------------------------------------------------------------------------
# Schemi API
# ---------------------------------------------------------------------------
class StartCmd(BaseModel):
    program: str
    dry_run: StrictBool = True
    temp: int | None = None
    spin: int | None = None
    soil: int | None = None
    options: list[str] = Field(default_factory=list)


class IpCmd(BaseModel):
    ip: str


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------
@app.get("/api/config")
def get_config():
    try:
        programs = [
            program.name for program in startable_programs(get_program_catalog())
        ]
    except CatalogUnavailableError:
        return {"ip": candy_ip, "programs": [], "catalog_ready": False}
    return {"ip": candy_ip, "programs": programs, "catalog_ready": bool(programs)}


@app.post("/api/config")
def set_config(cmd: IpCmd):
    _set_ip(cmd.ip)
    return {"ip": candy_ip}


@app.get("/api/status")
def api_status():
    raw = _status_raw()
    if not raw["online"]:
        raise HTTPException(503, "Lavatrice non raggiungibile: " +
                            raw.get("error", "errore sconosciuto"))
    d = raw["data"]
    # arricchisce con etichette leggibili
    try:
        total = int(d.get("DelVal", 0)) * 60 + int(d.get("RemTime", 0))
    except (TypeError, ValueError):
        total = 0
    return {
        "online": True,
        "raw": d,
        "machmd": _machmd_label(d.get("MachMd")),
        "phase": _prph_label(d.get("PrPh")),
        "remaining_min": total,
        "rem_time_str": "%d:%02d" % (total // 60, total % 60),
    }


@app.post("/api/start")
def api_start(cmd: StartCmd):
    try:
        program = require_startable_program(
            get_program_catalog().by_name(cmd.program)
        )
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

    if cmd.dry_run:
        return {
            "sent": False,
            "dry_run": True,
            "payload": payload,
            "program": program_to_api(program),
        }

    try:
        c.CANDY_IP = candy_ip
        response_text = c.send_command(payload, c.getkey())
    except Exception as error:
        raise HTTPException(502, f"Invio comando fallito: {error}") from None

    try:
        response = json.loads(response_text)
    except ValueError:
        response = {"raw": response_text}
    return {
        "sent": True,
        "dry_run": False,
        "payload": payload,
        "response": response,
        "program": program_to_api(program),
    }


@app.post("/api/stop")
def api_stop():
    try:
        c.CANDY_IP = candy_ip
        key = c.getkey()
        stato = json.loads(c.read_status(key))["statusLavatrice"]
        prnm = stato.get("Pr", "0")
        payload = "Write=1&StSt=0&PrNm=%s" % prnm
        resp = c.send_command(payload, key)
    except Exception as e:
        raise HTTPException(502, "Stop fallito: " + str(e))
    try:
        parsed = json.loads(resp)
    except ValueError:
        parsed = {"raw": resp}
    return {"sent": True, "payload": payload, "response": parsed}


# ---------------------------------------------------------------------------
# Pagina HTML (singola)
# ---------------------------------------------------------------------------
HTML = """<!doctype html>
<html lang="it">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Candy Lavatrice</title>
<style>
  :root{
    --bg:#0f172a; --card:#1e293b; --accent:#38bdf8; --accent2:#0ea5e9;
    --green:#22c55e; --red:#ef4444; --amber:#f59e0b; --txt:#e2e8f0; --mut:#94a3b8;
  }
  *{box-sizing:border-box}
  body{margin:0;font-family:system-ui,Segoe UI,Roboto,sans-serif;background:var(--bg);
       color:var(--txt);min-height:100vh;display:flex;justify-content:center;padding:24px}
  .wrap{width:100%;max-width:680px}
  h1{margin:0 0 4px;font-size:26px;display:flex;align-items:center;gap:10px}
  .dot{width:12px;height:12px;border-radius:50%;background:var(--mut);box-shadow:0 0 0 0 rgba(34,197,94,.5)}
  .dot.online{background:var(--green);animation:pulse 2s infinite}
  .dot.offline{background:var(--red)}
  @keyframes pulse{0%{box-shadow:0 0 0 0 rgba(34,197,94,.5)}70%{box-shadow:0 0 0 10px rgba(34,197,94,0)}100%{box-shadow:0 0 0 0 rgba(34,197,94,0)}}
  .sub{color:var(--mut);font-size:13px;margin-bottom:20px}
  .card{background:var(--card);border-radius:16px;padding:20px;margin-bottom:16px;
        box-shadow:0 1px 3px rgba(0,0,0,.3)}
  .card h2{margin:0 0 16px;font-size:15px;text-transform:uppercase;letter-spacing:.06em;color:var(--accent)}
  .grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}
  .stat{background:rgba(0,0,0,.2);border-radius:10px;padding:12px 14px}
  .stat .k{font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:var(--mut)}
  .stat .v{font-size:20px;font-weight:600;margin-top:2px}
  .stat .v.big{font-size:30px;color:var(--accent)}
  .row{display:flex;gap:12px;align-items:center;margin-bottom:14px;flex-wrap:wrap}
  label{font-size:13px;color:var(--mut);min-width:90px}
  input,select{background:#0f172a;border:1px solid #334155;color:var(--txt);
        border-radius:8px;padding:9px 11px;font-size:14px;width:100%}
  select{cursor:pointer}
  .opts{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin:6px 0 14px}
  .chip{display:flex;align-items:center;gap:8px;background:rgba(0,0,0,.2);
        padding:9px 12px;border-radius:8px;cursor:pointer;font-size:14px}
  .chip input{width:auto}
  .real-send-control{display:flex;align-items:center;gap:8px;margin-top:12px;font-size:14px}
  .real-send-control input{width:auto}
  .btns{display:flex;gap:12px;margin-top:8px}
  button{flex:1;border:0;border-radius:10px;padding:13px;font-size:15px;font-weight:600;cursor:pointer;transition:.15s}
  button:disabled{opacity:.5;cursor:not-allowed}
  .btn-go{background:var(--green);color:#06210f}
  .btn-go:hover{background:#16a34a}
  .btn-stop{background:var(--red);color:#2a0808}
  .btn-stop:hover{background:#dc2626}
  .btn-ghost{background:#334155;color:var(--txt);flex:0 0 auto;padding:13px 18px}
  .btn-ghost:hover{background:#475569}
  .ipbar{display:flex;gap:8px;align-items:center;margin-bottom:6px}
  .ipbar input{max-width:180px}
  #msg{font-size:13px;margin-top:12px;min-height:18px}
  .ok{color:var(--green)} .err{color:var(--red)} .info{color:var(--amber)}
  .skel{color:var(--mut);font-style:italic}
  @media(max-width:520px){.grid{grid-template-columns:1fr}.opts{grid-template-columns:1fr}}
</style>
</head>
<body data-catalog-ready="__CATALOG_READY__">
<div class="wrap">
  <h1>🫧 Candy Lavatrice <span id="dot" class="dot"></span></h1>
  <div class="sub">Controllo locale · stato su richiesta</div>

  <div class="ipbar">
    <input id="ip" placeholder="192.168.1.235">
    <button class="btn-ghost" onclick="saveIp()">Salva IP</button>
    <button class="btn-ghost" onclick="loadStatus()">↻ Aggiorna</button>
  </div>

  <!-- STATO -->
  <div class="card">
    <h2>Stato attuale</h2>
    <div class="grid">
      <div class="stat"><div class="k">Stato macchina</div><div class="v" id="s_md">—</div></div>
      <div class="stat"><div class="k">Fase</div><div class="v" id="s_ph">—</div></div>
      <div class="stat"><div class="k">Tempo residuo</div><div class="v big" id="s_rem">—</div></div>
      <div class="stat"><div class="k">Programma (Pr/Code)</div><div class="v" id="s_pr">—</div></div>
      <div class="stat"><div class="k">Temperatura</div><div class="v" id="s_tmp">— °C</div></div>
      <div class="stat"><div class="k">Centrifuga</div><div class="v" id="s_spn">—</div></div>
    </div>
  </div>

  <!-- NUOVO LAVAGGIO -->
  <div class="card">
    <h2>Nuovo lavaggio</h2>
    <div class="row">
      <label>Programma</label>
      <select id="prog" onchange="onProg()"></select>
    </div>
    <div class="row">
      <label>Temperatura</label>
      <select id="temp">
        <option value="0">Freddo</option><option>20</option><option>30</option>
        <option>40</option><option>60</option><option>90</option>
      </select>
      <label style="min-width:60px">Centrif.</label>
      <select id="spin">
        <option value="0">No</option><option>4</option><option>6</option>
        <option>8</option><option>10</option><option>12</option>
        <option>14</option>
      </select>
    </div>
    <div class="row">
      <label>Livello sporco</label>
      <select id="soil"><option value="1">Leggero</option>
        <option value="2" selected>Medio</option><option value="3">Forte</option></select>
    </div>
    <div class="opts">
      __OPTION_CONTROLS__
    </div>
    <label class="real-send-control">
      <input id="real-send" type="checkbox" onchange="updateStartMode()">
      Invio reale
    </label>
    <div class="btns">
      <button id="start-button" class="btn-go" __START_DISABLED__ onclick="start()">▷ Simula programma</button>
      <button class="btn-stop" onclick="stop()">■ Ferma</button>
    </div>
    <div id="catalog-recovery" class="info" __RECOVERY_HIDDEN__>Catalogo programmi non disponibile. Esegui: python candy_import_programs.py</div>
    <div id="msg"></div>
  </div>
</div>

<script>
const $ = id => document.getElementById(id);
let programs = {};

async function init(){
  try{
    const r = await fetch('/api/config').then(r=>r.json());
    $('ip').value = r.ip;
    programs = {};
    const programsResponse = await fetch('/api/programs');
    if(!programsResponse.ok){
      const error = await programsResponse.json().catch(()=>({}));
      throw new Error(error.detail||('HTTP '+programsResponse.status));
    }
    const list = await programsResponse.json();
    if(!r.catalog_ready || list.length===0){
      throw new Error('nessun programma avviabile');
    }
    const sel = $('prog');
    sel.innerHTML='';
    for(const p of list){
      const o=document.createElement('option');
      o.value=p.name; o.textContent=p.prstr+' ('+p.defaults.temp+'°C, '+p.defaults.spin+' rpm)';
      sel.appendChild(o);
    }
    programs = Object.fromEntries(list.map(p=>[p.name,p]));
    onProg();
    $('catalog-recovery').hidden=true;
    $('start-button').disabled=list.length===0;
  }catch(e){
    $('catalog-recovery').hidden=false;
    $('start-button').disabled=true;
    msg('Catalogo non caricato: '+e.message,'err');
  }
  loadStatus();
}
function onProg(){
  const p = programs[$('prog').value];
  if(!p) return;
  fillSelect('temp',p.allowed.temp,p.defaults.temp);
  fillSelect('spin',p.allowed.spin,p.defaults.spin);
  fillSelect('soil',p.allowed.soil,p.defaults.soil);
  document.querySelectorAll('.chip input').forEach(input=>{
    input.checked=false;
    input.disabled=!p.allowed.options.includes(input.value);
  });
}
function fillSelect(id,values,selected){
  const select=$(id);
  select.innerHTML='';
  for(const value of values){
    const option=document.createElement('option');
    option.value=String(value); option.textContent=String(value);
    select.appendChild(option);
  }
  select.value=String(selected);
}
function msg(t,cls){ $('msg').textContent=t; $('msg').className=cls||''; }
function updateStartMode(){
  $('start-button').textContent=$('real-send').checked
    ? '▶ Avvia lavaggio' : '▷ Simula programma';
}
function resetRealSend(){
  $('real-send').checked=false;
  updateStartMode();
}

async function saveIp(){
  await fetch('/api/config',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({ip:$('ip').value})});
  msg('IP salvato.','ok'); loadStatus();
}

async function loadStatus(){
  $('dot').className='dot';
  msg('Aggiornamento…','info');
  try{
    const r = await fetch('/api/status');
    if(!r.ok){const e=await r.json().catch(()=>({})); throw new Error(e.detail||('HTTP '+r.status));}
    const d = await r.json();
    $('dot').className='dot online';
    $('s_md').textContent=d.machmd;
    $('s_ph').textContent=d.phase;
    $('s_rem').textContent=d.rem_time_str;
    const rr=d.raw||{};
    $('s_pr').textContent=(rr.Pr||'?')+' / '+(rr.PrCode||'?');
    $('s_tmp').textContent=(rr.Temp||'?')+' °C';
    $('s_spn').textContent=rr.SpinSp||'?';
    msg('','');
  }catch(e){
    $('dot').className='dot offline';
    ['s_md','s_ph','s_rem','s_pr'].forEach(i=>$(i).textContent='—');
    $('s_tmp').textContent='— °C'; $('s_spn').textContent='—';
    msg('Offline: '+e.message,'err');
  }
}

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

async function stop(){
  if(!confirm('Fermare il ciclo corrente?')) return;
  msg('Invio stop…','info');
  try{
    const r=await fetch('/api/stop',{method:'POST'});
    const d=await r.json();
    if(!r.ok) throw new Error(d.detail||('HTTP '+r.status));
    msg('■ Stop inviato.','ok');
    setTimeout(loadStatus,1500);
  }catch(e){ msg('✗ '+e.message,'err'); }
}

init();
</script>
</body>
</html>"""


@app.get("/api/programs")
def api_programs():
    try:
        return [
            program_to_api(program)
            for program in startable_programs(get_program_catalog())
        ]
    except CatalogUnavailableError as error:
        raise HTTPException(503, str(error)) from None


@app.get("/", response_class=HTMLResponse)
def index():
    try:
        catalog = get_program_catalog()
        catalog_ready = bool(startable_programs(catalog))
        option_controls = _render_option_controls(catalog)
    except CatalogUnavailableError:
        catalog_ready = False
        option_controls = ""
    return (
        HTML.replace("__CATALOG_READY__", str(catalog_ready).lower())
        .replace("__START_DISABLED__", "" if catalog_ready else "disabled")
        .replace("__RECOVERY_HIDDEN__", "hidden" if catalog_ready else "")
        .replace("__OPTION_CONTROLS__", option_controls)
    )


def _free_port(preferred=8000, host="127.0.0.1"):
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind((host, preferred))
            return preferred
        except OSError:
            pass
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return sock.getsockname()[1]


def main(*, uvicorn_runner=None, port_finder=_free_port):
    if uvicorn_runner is None:
        import uvicorn

        uvicorn_runner = uvicorn.run
    port = port_finder()
    print("Apri nel browser:  http://localhost:%d" % port)
    print("IP lavatrice:", candy_ip, "(modificabile dalla pagina)")
    print("Auto-reload ATTIVO: salvando i file il server si riavvia da solo.")
    print("CTRL+C per fermare.")
    # 'reload=True' richiede l'app come stringa di import (modulo:oggetto)
    uvicorn_runner("candy_web:app", host="127.0.0.1", port=port, reload=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
