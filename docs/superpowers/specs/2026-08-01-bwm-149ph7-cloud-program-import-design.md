# Importazione cloud dei programmi Candy BWM 149PH7

## Obiettivo

Permettere al progetto locale di inviare i programmi remoti corretti alla Candy
BWM 149PH7 senza ricavare la mappatura dalla manopola e senza provare comandi
sulla lavatrice. La fonte attendibile sarà il catalogo associato al dispositivo
nell'account Candy simply-Fi.

Il risultato dell'importazione sarà un `programs.json` verificato, usato sia
dalla CLI sia dall'interfaccia web al posto dell'attuale tabella dimostrativa.

## Ambito

L'importatore acquisirà tutti i programmi che il cloud dichiara avviabili da
remoto per lo specifico dispositivo. La macchina espone 21 contatori numerati,
quindi ci si aspetta una base di 21 programmi; eventuali ricette speciali
aggiuntive verranno incluse soltanto quando la risposta cloud contiene tutti i
campi necessari per costruire un comando locale.

Sono esclusi:

- l'acquisizione tramite manopola;
- l'avvio di cicli di prova durante l'importazione;
- la cattura del traffico Android;
- modifiche al firmware o alla configurazione Wi-Fi della lavatrice;
- tentativi automatici di combinazioni `PrNm`/`PrCode` non restituite dal cloud.

## Componenti

### Client cloud

Un modulo isolato gestirà autenticazione e richieste alle API Candy simply-Fi
usate dall'app Android. Riceverà email e password a runtime, manterrà token e
sessione soltanto in memoria, elencherà gli elettrodomestici registrati e
scaricherà il catalogo programmi del dispositivo selezionato.

Se nell'account è presente una sola lavatrice compatibile, verrà selezionata
automaticamente. Con più lavatrici, la CLI mostrerà modello e identificatore
mascherato e chiederà quale importare.

### Importatore CLI

Il comando `python candy_import_programs.py`:

1. chiederà l'email e leggerà la password con input nascosto;
2. accederà al cloud Candy;
3. individuerà la BWM 149PH7 registrata;
4. scaricherà e normalizzerà i programmi avviabili da remoto;
5. mostrerà un riepilogo senza dati di autenticazione;
6. scriverà atomicamente `programs.json` solo dopo una validazione completa.

Le credenziali, i token e le risposte di autenticazione non saranno scritti su
file né inclusi nei log o nei messaggi di errore. L'importazione non contatterà
l'endpoint locale di scrittura della lavatrice.

La password non potrà essere passata come argomento della riga di comando o
variabile d'ambiente: sarà accettata esclusivamente dal prompt nascosto, così da
non finire nella cronologia della shell o nell'elenco dei processi.

### Modello dati normalizzato

Il file avrà una radice versionata che lega esplicitamente il catalogo al
dispositivo:

```json
{
  "schema_version": 1,
  "source": "candy-cloud",
  "appliance": {
    "model": "BWM 149PH7",
    "id_masked": "***1234"
  },
  "imported_at": "2026-08-01T12:00:00+02:00",
  "programs": []
}
```

L'identificatore completo del dispositivo non sarà salvato. La data sarà
generata al momento dell'importazione. Ogni elemento di `programs` conterrà
almeno:

```json
{
  "name": "rapid_30",
  "prnm": 5,
  "prcode": 7,
  "prstr": "Rapid 30min",
  "defaults": {
    "temp": 30,
    "spin": 10,
    "soil": 2,
    "steam": 0,
    "dry": 0
  },
  "allowed": {
    "temp": [20, 30, 40],
    "spin": [0, 4, 6, 8, 10, 12, 14],
    "soil": [1, 2, 3],
    "options": []
  },
  "source": "candy-cloud"
}
```

I valori dell'esempio descrivono la struttura, non la mappatura effettiva del
modello. I valori reali saranno accettati esclusivamente dalla risposta cloud.
Se il cloud non espone un insieme `allowed`, il campo verrà limitato al valore
predefinito anziché inventare combinazioni.

Il nome locale sarà uno slug stabile e univoco. `prnm`, `prcode` e `prstr`
resteranno quelli forniti dal cloud, senza rinumerazione.

### Validazione e persistenza

Prima della scrittura verranno verificati:

- presenza e tipo di `prnm`, `prcode`, `prstr` e valori predefiniti;
- unicità del nome locale e della coppia `prnm`/`prcode`;
- coerenza dei valori predefiniti con gli insiemi ammessi;
- assenza di valori nulli nei campi necessari al payload;
- presenza di almeno un programma remoto valido.

Una risposta parziale o incoerente farà fallire l'intera importazione. Un
`programs.json` già valido verrà preservato come `programs.json.bak` prima della
sostituzione atomica. Il file di destinazione non verrà alterato se
l'autenticazione, il download o la validazione falliscono.

### Integrazione con CLI e interfaccia web

`candy_sendprogram.py` caricherà `programs.json` tramite un unico loader
condiviso. `candy_web.py` userà lo stesso loader per `/api/programs`, evitando
due rappresentazioni divergenti.

La tabella `PROGRAMS` dimostrativa non sarà più utilizzata per inviare comandi.
Se il file manca o non è valido:

- `list` e la pagina web spiegheranno come eseguire l'importazione;
- l'avvio tramite nome programma sarà disabilitato;
- nessun valore dimostrativo verrà usato come fallback silenzioso.

Prima di costruire il payload, i parametri scelti dall'utente verranno
confrontati con `allowed`. Un valore non consentito verrà rifiutato con un
messaggio leggibile, senza inviare richieste alla lavatrice.

## Flusso dei dati

```text
Credenziali inserite a runtime
          |
          v
API Candy simply-Fi -> dispositivo BWM 149PH7 -> catalogo remoto
                                                |
                                                v
                                      normalizzazione e validazione
                                                |
                                                v
                                         programs.json
                                           /        \
                                          v          v
                               candy_sendprogram  candy_web
                                          \          /
                                           v        v
                                      payload locale validato
```

L'importazione e l'invio sono operazioni separate. Scaricare il catalogo non
produce mai un payload di avvio.

## Gestione degli errori

- Credenziali errate: messaggio sintetico, nessun dettaglio sensibile.
- Cloud non raggiungibile: il file esistente resta invariato.
- Dispositivo assente: elenco dei soli modelli compatibili trovati, con
  identificatori mascherati.
- Catalogo vuoto o schema cambiato: importazione rifiutata e diagnostica del
  campo non riconosciuto, senza stampare token o dati dell'account.
- Programmi duplicati o incompleti: nessuna importazione parziale.
- File locale non valido: invio bloccato fino a una nuova importazione valida.

## Verifica

I test automatici useranno risposte cloud simulate e non richiederanno
credenziali reali. Copriranno:

- autenticazione riuscita e fallita;
- selezione con uno o più dispositivi;
- normalizzazione del catalogo;
- rifiuto di record incompleti, duplicati o incoerenti;
- scrittura atomica e conservazione del file precedente in caso di errore;
- caricamento condiviso da CLI e web;
- blocco dei parametri fuori dall'insieme ammesso;
- costruzione in dry-run del payload usando esattamente la mappatura importata.

Una verifica manuale finale confronterà il numero e i nomi dei programmi
importati con quelli visibili nell'app Android. Il primo invio reale resterà una
azione esplicita dell'utente e non farà parte dell'importazione o dei test.

## Criteri di accettazione

- L'importatore recupera il catalogo associato alla BWM 149PH7 dell'utente.
- Nessuna credenziale o token resta su disco o compare nei log.
- L'importazione non invia comandi alla lavatrice.
- CLI e web mostrano gli stessi programmi caricati da `programs.json`.
- I dati dimostrativi non possono essere usati accidentalmente per un avvio.
- Mappature incomplete o parametri non consentiti bloccano l'invio.
- I nomi importati possono essere confrontati direttamente con l'app Android.
