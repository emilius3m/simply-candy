# Catalogo programmi Candy BWM 149PH7

Questo progetto importa il catalogo programmi dal cloud Candy e permette di
consultarlo, simulare un invio e usare una piccola interfaccia web locale.

## Installazione e flusso sicuro

In PowerShell, dalla cartella del progetto:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe candy_import_programs.py
.\.venv\Scripts\python.exe candy_sendprogram.py list
.\.venv\Scripts\python.exe candy_sendprogram.py start --program <nome> --dry-run
.\.venv\Scripts\python.exe candy_web.py
```

L'importazione apre nel browser la pagina ufficiale Candy. Accedi soltanto in
quella pagina; lo script non chiede email o password. Al termine il browser
prova ad aprire un indirizzo `candy://`: copia l'indirizzo completo e incollalo
nel prompt nascosto del terminale. Non incollarlo in chat, email o file perché
contiene credenziali temporanee. Dopo l'importazione chiudi la scheda del
callback.

Token e callback restano solo in memoria e non vengono salvati. Se Candy
aggiorna il catalogo, ripeti l'accesso dal browser per rigenerare
`programs.json`.

Il comando `list` mostra i nomi importati. Prima di un invio reale eseguire
sempre `start --program <nome> --dry-run`: l'importazione e il dry-run non
avviano la lavatrice. Il primo invio reale richiede che la lavatrice sia pronta
al controllo remoto, secondo le condizioni mostrate dall'app Candy.

## Dati da proteggere

`candy_key.cache` contiene una chiave locale dell'elettrodomestico e va
protetto come un segreto. Non allegare `programs.json`, `candy_key.cache` o
capture di rete a issue pubbliche.

Per la BWM 149PH7 non usare `candy_learn_programs.py`: la selezione con la
manopola esclude il controllo remoto. Il percorso supportato è
`candy_import_programs.py`.
