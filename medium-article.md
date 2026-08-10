# Il diario di un reverse engineering: perché mi sono scritto un'app per la lavatrice

*Qualche sera fa ho aperto il terminale contro la mia lavatrice. Non per gioco — perché l'app ufficiale, ancora una volta, non l'avviava. Questo è il diario di cosa ho trovato dentro quel dispositivo, delle teorie sbagliate che mi sono raccontato, e del momento in cui ha finalmente fatto quello che le chiedevo.*

---

## Giorno 0 — Il perché

L'app **Candy simply-Fi** della mia lavatrice (una BWM 149PH7) ha un comportamento che conosco a memoria: premo "Avvia", vedo lo spinner, a volte ricevo un "operazione completata", e **la lavatrice non parte**. Oppure parte il programma sbagliato. Oppure non si connette proprio. È la terza sera di fila che mi tocca alzarmi e andare a girare la manopola fisica.

Sono sviluppatore. La cosa mi rode per un motivo preciso: ho pagato per un dispositivo "smart", dipendo da un'app che non funziona, e **non ho alternative**. Non posso debuggarla, non posso patcharla, non posso fare altro che riavviarla e sperare.

Stasera ho deciso che basta. Se non posso aggiustare l'app di Candy, mi scrivo la mia. Ma per farlo devo prima capire come parlano tra loro. Apro il terminale.

## Giorno 1 — Dentro la lavatrice c'è un server HTTP

Il primo passo è capire dove si trova la lavatrice sulla rete e cosa espone. `nmap`, un po' di tentativi, e scopro che il modulo WiFi, una volta connesso, tiene aperto un **server HTTP sulla porta 80**. Niente HTTPS, niente auth: chiunque sulla LAN ci parla.

Due endpoint fanno quasi tutto:

```
GET /http-read.json?encrypted=1      → stato (cifrato)
GET /http-write.json?encrypted=1&data=<hex>  → comando (cifrato)
```

La parola chiave è *cifrato*. Le risposte sono byte esadecimali senza senso apparente. Ma il protocollo di queste Candy è noto nella community (ci sono repo GitHub e thread su Home Assistant): **XOR con chiave ripetuta a 16 byte**. Debole, se conosci plaintext.

Lo stato, decifrato, è un JSON pulito:

```json
{ "statusLavatrice": { "MachMd": "2", "Pr": "16", "Temp": "30", "RemTime": "1800", ... } }
```

In dieci righe di Python ho un monitor funzionante. Lo provo: leggo lo stato, vedo "lavaggio in corso", temperatura 30°C, 30 minuti residui. Funziona. Pensavo di essere a metà dell'opera.

Ero all'inizio.

## Giorno 2 — Avviare un programma: l'incubo

Leggere è facile. **Scrivere** — avviare un programma — è il problema vero, ed è esattamente quello che l'app ufficiale fa male.

Dalla community ho il formato del comando: una querystring (`PrNm`, `PrCode`, `TmpTgt`, `SLevTgt`, ...) cifrata XOR e spedita come `data=<hex>`. Per costruirla mi servono i valori giusti di ogni programma. La via più naturale mi sembra **leggerli dallo stato**: giro la manopola su un programma, leggo `Pr` e `SLevel`, e li metto nel comando remoto.

Invio. La lavatrice risponde `{"response":"SUCCESS"}`. Perfetto, penso. Guardo il display: non è cambiato nulla. Riprovo. Stessa risposta. Stesso nulla. Provo un altro programma. `SUCCESS`. Niente.

Qui comincia la parte umiliante. Per ore costruisco teorie su teorie per spiegare il fallimento, e **sbaglio tutte**:

- *"L'API locale non accetta l'avvio programmi, il firmware è in sola lettura."* — Sbagliato.
- *"Serve per forza il cloud hOn con OAuth, l'API locale è limitata."* — Sbagliato.
- *"Il firmware ignora i parametri e avvia l'ultimo programma in memoria."* — Sbagliato.

L'assistente AI con cui sto lavorando mi propone ognuna di queste teorie, io le accetto, le testo, falliscono, ne propone un'altra. È un loop. A un certo punto mi fa notare una cosa banale che mi era sfuggita: quando cambio programma dalla **manopola fisica**, lo stato cambia correttamente. Quindi *qualcuno* riesce a scegliere il programma. Solo che non sono io.

Se la manopola ci riesce e io no, il problema non è il firmware. È il mio comando.

## Giorno 3 — Decompilare l'APK (la svolta)

C'è qualcuno che sa avviare i programmi: l'app ufficiale. Anche se lo fa male, *qualche volta* lo fa. Quindi il segreto è nel suo codice.

Scarico l'APK di Candy simply-Fi e lo passo a **jadx**, il decompilatore Java. Apro la cartella dei sorgenti generati: migliaia di file. Ma so cosa cercare — le stringhe degli endpoint.

Trovo `CommandService.java`. Per ogni comando (start, stop, ...) ci sono due canali:

```java
@GET("http-write.json")        // CANALE LOCALE
@POST("api/v1/commands.json")  // CANALE CLOUD
```

E la scelta tra i due è tre righe sotto:

```java
protected boolean canUseLocal() {
    return CandyNetworkUtility.isLocalNetwork(this.mContext)
        && URLUtil.isValidUrl(this.mAddress);
}
```

**Quando sono a casa, sullo stesso WiFi della lavatrice, l'app ufficiale usa lo stesso identico endpoint HTTP locale nostro.** Niente magia cloud. La mia teoria del "serve il cloud" era sbagliata dalla prima all'ultima riga.

Ma il vero oro è un altro file: `Command.getParameterString()`. Lì dentro vedo costruire il payload. Ed è il momento in cui capisco il mio errore. Il mio payload era **incompleto**. Mandavo `PrNm` + qualche parametro; l'app ne invia **18, in ordine fisso**:

```
Write=1&StSt=1&DelVl=0&PrNm=<...>&PrCode=<...>&PrStr=<nome>
&TmpTgt=<...>&SLevTgt=<...>&SpdTgt=<...>
&OptMsk1=<...>&OptMsk2=<...>&Lang=1&Stm=<...>&Dry=<...>
&ED=0&RecipeId=0&StartCheckUp=0&DispTestOn=1
```

Il firmware del mio modello **richiede il payload completo** per validare il comando. Con un payload parziale risponde `{"response":"SUCCESS"}` — educatamente — e poi lo ignora, avviando l'ultimo programma che aveva in memoria. Ecco perché "partiva sempre l'ultimo": non era un bug del firmware, era il **mio** comando che veniva scartato in silenzio.

Ironia: l'app ufficiale probabilmente fallisce per altri motivi (timeout, retry mal gestiti), ma il *formato* che usa è quello giusto. Ce l'avevo sotto gli occhi da ore.

## Giorno 3, sera — I valori giusti non sono quelli che leggi

Payload completo ricostruito. Testo. Non funziona ancora del tutto. C'è un secondo problema, più subdolo.

I programmi "Rapid" della mia lavatrice condividono `PrNm=16, PrCode=7` e si distinguono solo per `SLevel`:

| Programma | SLevel da stato locale | SLevel da cloud |
|-----------|------------------------|-----------------|
| Rapid 14 | 1 | 1 ✅ |
| Rapid 30 | 2 | **9** ❌ |
| Rapid 44 | — | **9** |

Quel `9` non è un livello sporco (che va 0-3): è un **codice speciale** che il firmware usa per distinguere la durata. Leggendo lo stato vedevo `2`, e infatti la macchina non riconosceva il programma. Non l'avrei mai indovinato. Servivano i **valori ufficiali** del cloud.

## Giorno 3, notte — Reverse engineering del login cloud

Per ottenere i 19 programmi con i parametri esatti devo replicare il flusso OAuth dell'app. Torno nell'APK. I sorgenti decompilati mi danno tutto:

- Il backend auth è **Salesforce CIAM** (variante di OIDC, `grant_type=hybrid_refresh` — una cosiddetta).
- Il `client_id` è **hardcoded** nell'APK.
- Dopo il login nel browser, il redirect è a uno schema custom: `candy://mobilesdk/detect/oauth/done#refresh_token=...`.
- Con il `refresh_token` si scambia un `id_token` via POST.
- Con l'`id_token` come Bearer, si chiama `https://simply-fi.herokuapp.com/api/v1/appliances.json?with_programs=1`, con header fissi (`Salesforce-Auth: 1`, `Brand: 0`, `Device-Family: android`, versioni app) che altrimenti il backend rifiuta.

Implemento il flusso in Python, faccio il login con le mie credenziali simply-Fi, e in risposta arrivano **19 programmi** con tutti i parametri reali del mio modello: `selector_position`, `pr_code`, temperature e spin ammessi, opzioni come bitmask (`available_options` e `available_options2`). Li normalizzo e li salvo in un `programs.json`.

Per la prima volta ho i valori giusti.

## Giorno 4 — Il primo successo

Payload completo a 18 campi. Valori cloud corretti. Invio `rapid-14` (`PrNm=16, PrCode=7, SLevel=1`).

```
Risposta: {"response":"SUCCESS"}
Display lavatrice: parte Rapid 14 min ✅
```

Funziona. Non "parte l'ultimo programma". Non "silenzio". Il programma giusto. Premo di nuovo, con un altro programma. Parte quello. Cambio override della temperatura. Parte con la temperatura giusta.

L'API locale del BWM 149PH7 **può** scegliere il programma. Serviva solo il formato esatto — quello che l'app di Candy usa quando decide di funzionare. Tutte le teorie che mi ero raccontato per dare la colpa al firmware erano proiezioni della mia ignoranza del protocollo.

## Dopo — Da script a un'app

Avevo un backend Python con web UI, ma volevo qualcosa di **standalone** sul telefono, senza un server acceso sul PC. Ho portato tutto in **Flutter** (multipiattaforma: Android, iOS, Windows, macOS, Linux). Porting fedele del protocollo in Dart — XOR a 16 byte, derivazione chiave a 3 livelli, payload a 18 campi, due maschere di opzioni, login OAuth cloud con intercettazione del deep link `candy://`.

Build verificata: APK Android da 49 MB sul telefono, eseguibile Windows da 30 MB. L'app fa login cloud direttamente dal dispositivo, parla in HTTP con la lavatrice, ha i 19 programmi pre-caricati come fallback.

Adesso, quando devo avviare un lavaggio, non prego l'app ufficiale di degnarsi di funzionare. Apro la mia, premo avvia, e parte. **Affidabile**, che era l'unica cosa che avevo chiesto dal giorno zero.

## Cosa porto a casa

- **Non dare la colpa all'hardware.** Se un comando non funziona, la causa più probabile è il tuo payload, non il firmware. Ho perso ore a teorizzare limitazioni inesistenti.
- **Leggere lo stato non significa sapere cosa inviare.** I valori mostrati non sono quelli accettati in ingresso. Per i parametri giusti serve la fonte autorevole.
- **Decompila l'app ufficiale.** Se esiste un client che funziona (anche male), il suo codice è la documentazione migliore che esista. `jadx` + due classi chiave hanno risolto in un'ora quello che tentativi non avevano scalfito.
- **Un "successo" può mentire.** La lavatrice rispondeva `SUCCESS` a comandi che poi ignorava. Un 200 o un OK non sono conferme di esecuzione: verifica sempre l'effetto reale.
- **A volte la soluzione va scritta da sola.** Non potevo patchare l'app di Candy. Non potevo aspettare un aggiornamento. Potevo capire il protocollo e costruirmi lo strumento. E adesso funziona.

## Un'ultima cosa

Questa non è la storia di un hackeraggio. È la storia di un utente che ha comprato un prodotto "smart", ha ricevuto in cambio un'esperienza rotta, e ha deciso di **riprendersi il controllo** di qualcosa che gli appartiene. Il dispositivo è mio, la rete è mia, il tempo che ci ho investito è mio. Adesso anche il modo di usarlo è mio.

Se anche tu hai un'app di un elettrodomestico che ti fa dannare — lavatrice, forno, robot aspirapolvere — sappi che probabilmente sotto c'è un protocollo. Spesso è più semplice di quanto i produttori vorrebbero. E a volte, scriverlo da soli è la soluzione più veloce.

---

*Se questo diario ti ha parlato — magari perché anche tu hai un'app smart che non ne vuole sapere di funzionare — batti quel ❤️. Nei commenti: qual è l'elettrodomestico "smart" più frustrante che avete a casa, e quanto vi ha fatto tribolare?*

*Disclaimer: tutto il lavoro descritto è fatto sul mio dispositivo, sulla mia rete, per uso personale. Non accedere a dispositivi che non vi appartengono.*
