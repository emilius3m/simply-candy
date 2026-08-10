# Design editoriale: articolo Medium sulla Candy BWM 149PH7

Data: 2026-08-02

## Obiettivo

Raccontare dall'inizio alla fine come un problema apparentemente semplice —
inviare programmi a una Candy BWM 149PH7 — abbia richiesto di correggere il
modello mentale del sistema, analizzare in modo mirato l'APK Android, osservare
i dati cloud reali e costruire un'interfaccia fail-safe.

L'articolo deve spiegare non soltanto cosa e stato realizzato, ma quali evidenze
hanno portato a ogni cambio di direzione e perche il risultato finale assume la
forma attuale.

## Pubblico e tono

- Pubblico: sviluppatori, maker e lettori interessati a IoT e reverse
  engineering, senza richiedere conoscenze pregresse del protocollo Candy.
- Voce: prima persona, cronaca tecnica onesta e accessibile.
- Tono: investigativo, concreto, senza sensazionalismo.
- Lunghezza indicativa: 1.800–2.400 parole.
- Formato: Markdown compatibile con Medium, con sezioni brevi, un sottotitolo,
  pochi frammenti di codice e una conclusione trasferibile ad altri progetti.

## Titolo e promessa

Titolo principale:

**Dalla manopola al cloud: come ho reso programmabile una Candy BWM 149PH7**

Sottotitolo:

**Un percorso tra API obsolete, OAuth Salesforce, decompilazione Android,
bitmask e progettazione fail-safe.**

La promessa al lettore e mostrare come si passa da errori apparentemente
scollegati a un modello verificato del sistema, senza presentare il risultato
come una scorciatoia o una mappatura indovinata.

## Arco narrativo

### 1. Il vincolo fisico che cambia il problema

La manopola della BWM 149PH7 esclude il controllo remoto. La strada iniziale
basata sulla posizione fisica della manopola non e quindi praticabile. Il
problema diventa: ottenere dal cloud i programmi riconosciuti dalla macchina e
costruire i comandi corretti senza affidarsi a una selezione manuale.

### 2. Credenziali corrette, autenticazione sbagliata

L'app Android accede correttamente, mentre il vecchio password grant Heroku
risponde `invalid_grant`. Questo dimostra che le credenziali non sono il punto
principale: il client sta usando il percorso di autenticazione sbagliato.

### 3. Decompilazione mirata dell'APK

Spiegare in modo trasparente che e stata svolta analisi statica mirata dell'APK
Candy simply-Fi 3.14.1, non un reverse engineering completo e non un bypass
delle protezioni dell'app.

Le evidenze recuperate includono:

- il percorso principale Salesforce Mobile SDK;
- la natura deprecata del login email/password;
- `setUseWebServerAuthentication(false)`;
- `response_type=hybrid_token` e refresh `hybrid_refresh`;
- endpoint CIAM, redirect URI, scope e identificatori pubblici distribuiti
  nell'APK;
- `Command.getParameterString()` e l'ordine completo dei campi del comando;
- `OPTION_MASK_1`, `OPTION_MASK_2` e il controllo Zoom.

Sottolineare che il decompile fornisce una mappa teorica, non la prova finale
del comportamento del modello specifico.

### 4. OAuth nel browser Windows e la pagina bianca

Raccontare il redirect verso lo schema personalizzato `candy://`, che Windows
non sa aprire. La pagina bianca contiene in realta lo script di redirect. Il
callback viene copiato localmente nel terminale con input nascosto, senza
registrare protocolli Windows e senza condividere token.

Non mostrare callback, token, client-specific user ID, indirizzi IP pubblici o
altri valori sensibili comparsi durante l'indagine.

### 5. Il catalogo reale e gli errori di schema

Il cloud restituisce 19 record. La normalizzazione incontra:

- validazioni come stringhe vuote;
- campi opzionali `null`;
- bit opzione inizialmente considerati sconosciuti;
- differenza tra valori obbligatori e valori opzionali assenti.

Ogni errore viene trattato come informazione sullo schema. I campi obbligatori
restano fail-closed; soltanto i valori opzionali vuoti o null ricevono il
fallback previsto.

### 6. Due maschere e Zoom

I valori reali mostrano che una sola maschera non basta. `OptMsk1` contiene le
opzioni tradizionali; `OptMsk2` usa il bit 1 per Zoom. Il payload parziale viene
sostituito con quello completo ricostruito da `Command.getParameterString()`.

Inserire un frammento conciso e non operativo con i soli nomi dei campi
principali, senza chiavi o dati di rete.

### 7. Il diciannovesimo record: OFF non e un programma

`DUAL_WM_WD_OFF` e un record tecnico. Esporlo come ciclo avviabile sarebbe
fuorviante e potenzialmente pericoloso. La soluzione usa difesa in profondita:

- i nuovi import lo escludono;
- i cataloghi legacy restano leggibili;
- Web, API e CLI lo filtrano;
- un POST manuale viene rifiutato prima di payload, chiave e trasporto.

Il risultato visibile e quindi 18 programmi avviabili, pur mantenendo intatto
il catalogo gia importato con 19 record.

### 8. FastAPI e il principio fail-safe

La prima versione di `/api/start` inviava immediatamente. Il design viene
invertito: omissione di `dry_run` significa simulazione. L'invio reale richiede
il booleano JSON rigoroso `false`; numeri e stringhe simili a booleani vengono
rifiutati con 422.

La pagina aggiunge una spunta `Invio reale`, disattivata di default. La spunta:

- cambia il testo del pulsante;
- richiede conferma con il programma selezionato;
- abilita l'invio soltanto dopo conferma;
- si disattiva dopo annullamento, successo o errore.

Lo stop resta un comando reale separato con conferma, come da scope approvato.

### 9. Verifica e risultato

Riportare i risultati finali verificati:

- 18 programmi esposti;
- nessun `OFF` avviabile;
- Zoom in `OptMsk2=1`;
- dry-run predefinito;
- valori `dry_run` non booleani rifiutati;
- 172 test superati;
- catalogo originale invariato tramite SHA-256;
- nessun comando reale inviato durante i test.

### 10. Perche si e arrivati proprio a questo risultato

La conclusione deve collegare il risultato a quattro principi:

1. un errore di autenticazione puo indicare il client sbagliato, non password
   sbagliate;
2. il decompile aiuta a formulare ipotesi, ma i dati reali decidono;
3. gli errori di schema sono osservazioni sul dominio, non rumore da ignorare;
4. nei sistemi fisici l'interfaccia deve rendere l'azione pericolosa esplicita,
   stretta e reversibile fino all'ultimo momento.

## Accuratezza e limiti

- Non affermare che il protocollo sia ufficialmente supportato o stabile.
- Non presentare l'analisi come valida per ogni modello Candy.
- Distinguere sempre dati osservati, informazioni recuperate dall'APK e scelte
  progettuali conservative.
- Non pubblicare credenziali, bearer token, refresh token, callback reali,
  identificativi personali o segreti applicativi.
- Gli identificatori pubblici incorporati nell'app possono essere descritti,
  ma non e necessario riprodurli nell'articolo.
- Non fornire una procedura pronta a comandare apparecchi altrui; il racconto
  riguarda una macchina e un account sotto il controllo del proprietario.

## Criteri editoriali di accettazione

- La decompilazione appare come snodo centrale, ma non come unica fonte della
  soluzione.
- Ogni cambio di direzione e legato a un'evidenza concreta.
- Il lettore comprende la differenza tra 19 record cloud e 18 cicli avviabili.
- Il dry-run e il booleano rigoroso sono spiegati come scelte di sicurezza, non
  come dettagli cosmetici.
- L'articolo termina con lezioni generalizzabili e non soltanto con un elenco
  di risultati.

