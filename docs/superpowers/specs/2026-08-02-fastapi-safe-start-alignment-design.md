# Allineamento sicuro dell'avvio programmi FastAPI

Data: 2026-08-02

## Contesto

Il catalogo Candy reale della BWM 149PH7 contiene 19 record. Uno di questi,
`DUAL_WM_WD_OFF`, e un record tecnico e non un ciclo di lavaggio avviabile. Il
catalogo corrente lo espone come `dual-wm-wd-off` e l'endpoint FastAPI
`POST /api/start` lo accetta, costruisce il payload e raggiunge il trasporto.

Lo stesso endpoint invia immediatamente qualsiasi richiesta valida. Inoltre il
codice di produzione usa gia il payload completo con `OptMsk1` e `OptMsk2`, ma
alcuni test FastAPI e del mittente verificano ancora il vecchio formato con
`OptMsk`. L'opzione Candy Zoom e gia mappata al bit 1 di `OptMsk2`, ma non ha
un'etichetta esplicita nell'interfaccia.

## Obiettivi

- Rendere impossibile avviare il record tecnico `OFF` da Web, API e CLI.
- Rendere `POST /api/start` non trasmissivo per impostazione predefinita.
- Conservare un percorso esplicito per l'invio reale tramite API.
- Esporre Zoom in modo coerente con `OptMsk2=1`.
- Allineare i test al payload completo attuale senza contattare la lavatrice.
- Far produrre ai futuri import un catalogo di 18 programmi avviabili.

## Non obiettivi

- Modificare il protocollo di arresto `/api/stop`.
- Inviare comandi reali durante sviluppo o verifica.
- Riscrivere automaticamente il `programs.json` gia importato.

## Disegno

### Classificazione condivisa dei programmi avviabili

`candy_programs.py` conterra una singola definizione condivisa dei programmi
tecnici non avviabili, inizialmente `DUAL_WM_WD_OFF`, e funzioni per:

- riconoscere se un `ProgramDefinition` e avviabile;
- ottenere soltanto i programmi avviabili da un catalogo;
- rifiutare esplicitamente un programma tecnico con `OverrideError`.

La classificazione usa `prstr`, l'identificatore stabile restituito dal cloud,
e non lo slug locale. Il parser continuera a validare fedelmente anche un
catalogo esistente che contiene `OFF`; il filtro verra applicato dai consumer.
In questo modo il file corrente resta leggibile, ma `OFF` non puo raggiungere
il payload o il trasporto.

`candy_import_programs.normalize_catalog` scartera i programmi tecnici dopo la
normalizzazione e prima della verifica dei duplicati. Se dopo il filtro non
rimane alcun programma avviabile, l'import fallira con un errore di catalogo.
Un nuovo import della BWM 149PH7 salvera quindi 18 programmi.

### Protezione di Web, API e CLI

FastAPI usera l'elenco condiviso dei programmi avviabili in:

- `GET /api/programs`;
- il campo `programs` di `GET /api/config`;
- la generazione dei controlli opzione nella pagina HTML.

`POST /api/start` cerchera il nome nel catalogo e applichera subito il controllo
di avviabilita, prima di costruire il payload e prima di richiedere la chiave.
Un tentativo di avviare `OFF` restituira HTTP 422 con un messaggio esplicito.
Un nome assente restera HTTP 404.

La stessa guardia verra applicata a `start_named_program`; anche il comando CLI
`list` mostrera soltanto i programmi avviabili. Questa difesa condivisa evita
che un catalogo vecchio possa aggirare la protezione FastAPI.

### Dry-run sicuro per impostazione predefinita

Lo schema `StartCmd` aggiungera:

```text
dry_run: bool = True
```

La richiesta verra sempre risolta e validata e il payload verra sempre
costruito. Quando `dry_run` e vero, l'endpoint non chiamera `getkey` ne
`send_command` e restituira:

```json
{
  "sent": false,
  "dry_run": true,
  "payload": "...",
  "program": {"...": "..."}
}
```

L'invio reale richiedera esplicitamente `"dry_run": false`. Soltanto in questo
caso FastAPI acquisira la chiave, inviera il comando e restituira `sent: true`,
`dry_run: false`, la risposta del dispositivo, il payload e il programma.
Errori di trasporto continueranno a produrre HTTP 502 senza dichiarare
falsamente l'invio riuscito.

Il cambio e intenzionalmente fail-safe: anche client esistenti che omettono il
nuovo campo smettono di trasmettere automaticamente.

### Interfaccia Web

L'interfaccia aggiungera una spunta `Invio reale`, inizialmente e normalmente
disattivata. Il testo del pulsante principale riflettera la modalita corrente:
`Simula programma` senza spunta e `Avvia lavaggio` con la spunta attiva.

Senza spunta, la funzione JavaScript inviera `dry_run: true`, mostrera che il
payload e stato validato ma non inviato e non avviera un aggiornamento
differito dello stato macchina.

Con la spunta attiva, prima della richiesta JavaScript mostrera una conferma
esplicita con il programma selezionato. Solo dopo la conferma inviera
`dry_run: false`. Dopo il tentativo di invio, riuscito o fallito, la spunta
tornera automaticamente disattivata e il pulsante tornera a `Simula
programma`; in caso di successo verra aggiornato lo stato della macchina.
Annullare la conferma non inviera alcuna richiesta di avvio e disattivera la
spunta.

L'etichetta `Zoom` verra aggiunta a `OPTION_LABELS`; la selezione continuera a
essere delegata al builder condiviso, che genera `OptMsk2=1`.

### Compatibilita del catalogo corrente

Il `programs.json` corrente puo continuare a contenere 19 record. Tutti i punti
di esposizione e invio useranno il filtro condiviso, quindi il server mostrera
18 programmi e rifiutera comunque un POST manuale verso lo slug di `OFF`. Il
prossimo import rigenerera naturalmente il file con 18 record, senza una
migrazione distruttiva del file esistente.

## Gestione degli errori

- catalogo mancante o invalido: comportamento esistente HTTP 503;
- nome programma sconosciuto: HTTP 404;
- programma tecnico non avviabile o override non ammesso: HTTP 422;
- dry-run valido: HTTP 200, `sent: false`, nessun accesso al trasporto;
- invio reale fallito: HTTP 502;
- risposta non JSON del dispositivo: mantenimento del fallback `{"raw": ...}`.

## Strategia di test

I test seguiranno TDD e useranno esclusivamente trasporti sostitutivi che
falliscono se viene effettuato un accesso non previsto.

Copertura richiesta:

1. l'importatore esclude `DUAL_WM_WD_OFF` e rifiuta un catalogo senza cicli
   avviabili;
2. i consumer condivisi riconoscono e rifiutano `OFF`;
3. `/api/programs`, `/api/config` e la pagina Web non espongono `OFF` anche con
   un catalogo legacy che lo contiene;
4. `/api/start` senza `dry_run` e con `dry_run: true` restituisce il payload ma
   non chiama chiave o trasporto;
5. `/api/start` con `dry_run: false` chiama chiave e trasporto soltanto dopo la
   validazione;
6. un tentativo di avvio di `OFF` termina con 422 prima di ogni accesso alla
   rete;
7. Zoom appare nell'HTML e produce `OptMsk2=1` con `OptMsk1` invariato;
8. la spunta di invio reale e disattivata di default, controlla `dry_run`,
   richiede conferma e torna disattivata dopo annullamento, successo o errore;
9. le asserzioni obsolete vengono allineate al payload completo corrente,
   inclusi `OptMsk1` e `OptMsk2`;
10. l'intera suite viene eseguita senza server reale, cloud o lavatrice.

## Criteri di accettazione

- Con il catalogo corrente FastAPI espone 18 programmi, mai `OFF`.
- Nessuna richiesta a `/api/start` invia un comando se `dry_run: false` non e
  presente esplicitamente.
- La pagina Web invia `dry_run: false` soltanto quando la spunta e attiva e la
  conferma e stata accettata; la spunta non resta armata dopo il tentativo.
- `OFF` non raggiunge mai `build_start_payload`, `getkey` o `send_command`.
- Zoom e leggibile nell'interfaccia e rappresentato da `OptMsk2=1`.
- La suite aggiornata passa interamente in locale con il trasporto simulato.
