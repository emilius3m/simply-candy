# Dalla manopola al cloud: come ho reso programmabile una Candy BWM 149PH7

*Un percorso tra API obsolete, OAuth Salesforce, decompilazione Android, bitmask e progettazione fail-safe.*

All’inizio il problema sembrava quasi banale: volevo inviare un programma di lavaggio a una Candy BWM 149PH7.

Non cercavo di costruire una piattaforma domotica universale. Volevo una cosa molto concreta: scegliere un ciclo da un’interfaccia locale, impostare i parametri consentiti e trasmetterlo alla mia lavatrice. In teoria, bastava capire quale numero corrispondesse a ciascun programma.

In pratica, il primo ostacolo non era nel software. Era la manopola.

## La manopola cambiava completamente il problema

Sulla BWM 149PH7 la posizione della manopola condiziona il controllo remoto. La strada più immediata — selezionare fisicamente una modalità remota e poi pilotare tutto da software — non era utilizzabile nel mio scenario. La manopola escludeva il controllo remoto, quindi non potevo fingere che il selettore meccanico fosse soltanto un dettaglio dell’interfaccia.

La domanda divenne più precisa: **come posso costruire il comando che l’ecosistema Candy associa a un programma reale, senza inventare una mappatura e senza affidarmi alla manopola come sorgente di verità?**

Servivano almeno tre elementi: il catalogo dei cicli riconosciuti per quel modello, la struttura esatta del comando e un modo attuale per autenticarsi al cloud Candy.

Proprio l’autenticazione fu il primo vicolo cieco.

## Le credenziali erano corrette, il client era sbagliato

Il primo importatore usava un vecchio flusso email e password verso un endpoint Heroku. Il server rispondeva `invalid_grant`. Il messaggio sembrava inequivocabile: credenziali rifiutate.

Eppure, con la stessa email e la stessa password, l’app Android Candy continuava ad accedere senza problemi. Avevo verificato le credenziali ed eseguito nuovamente il login dall’app.

Questo contrasto era l’indizio decisivo. Se il client ufficiale funzionava e lo script no, insistere sulla password significava probabilmente indagare il livello sbagliato. L’ipotesi più utile non era “la password è errata”, ma “lo script sta usando un percorso di autenticazione che l’app non usa più”.

Cambiare header o imitare superficialmente Android non bastava. Dovevo capire quale flusso eseguisse davvero la versione corrente dell’app.

## La decompilazione come mappa, non come risposta magica

Ho quindi svolto un’analisi statica mirata dell’APK Android Candy simply‑Fi 3.14.1. Non è stato un reverse engineering completo dell’applicazione e non ho cercato di aggirarne le protezioni. L’obiettivo era molto più circoscritto: ricostruire il percorso di login e la serializzazione dei comandi usati dal client ufficiale per il mio account e il mio elettrodomestico.

Dal codice decompilato emersero due percorsi distinti. Il vecchio login email/password era ancora riconoscibile, ma trattato come deprecato. Il percorso principale passava invece dal Salesforce Mobile SDK.

Alcuni dettagli tolsero ogni ambiguità. L’inizializzazione chiamava `setUseWebServerAuthentication(false)`, manteneva attiva l’autenticazione ibrida e costruiva una richiesta con `response_type=hybrid_token`. Il callback non restituiva un normale authorization code da scambiare con PKCE: il client recuperava i valori OAuth dal frammento dell’URL e usava il refresh token con il grant `hybrid_refresh`. L’`id_token` ottenuto diventava poi il bearer per le API Candy.

L’APK forniva inoltre la configurazione pubblica necessaria al client: server di login Candy/Salesforce, percorso di autorizzazione, redirect URI `candy://mobilesdk/detect/oauth/done`, scope e identificatore OAuth incorporato nell’app. Questi elementi non erano credenziali dell’utente, ma parametri distribuiti con il client mobile.

La decompilazione chiarì anche il lato comando. `Command.getParameterString()` mostrava che l’app non costruiva un payload minimo con il solo numero del programma. Serializzava un insieme completo e ordinato di campi. Nel codice comparivano inoltre `OPTION_MASK_1`, `OPTION_MASK_2` e il controllo `isZoom()`.

Era una svolta, ma non ancora una prova sufficiente. Il codice dell’app poteva supportare più famiglie di elettrodomestici e varianti non presenti sulla BWM 149PH7. Il decompile mi aveva dato una mappa teorica; ora dovevo confrontarla con i dati reali restituiti per la mia macchina.

## La pagina bianca su Windows conteneva il passaggio mancante

Il nuovo importatore apriva il login Candy nel browser. L’accesso riusciva, ma alla fine compariva una pagina bianca e non avveniva alcun reindirizzamento utilizzabile.

Il comportamento aveva una spiegazione semplice: Candy stava tentando di aprire un URL con schema personalizzato `candy://`. Su Android quello schema viene intercettato dall’app. Sul mio Windows non esisteva un’applicazione registrata per gestirlo.

La pagina non era però vuota dal punto di vista tecnico. Il sorgente HTML conteneva uno script che provava a eseguire il redirect verso il callback OAuth, con i valori temporanei nel frammento dell’URL.

Non serviva registrare un protocollo Windows, usare ADB o intercettare il traffico. Il flusso è diventato questo: autenticazione sulla pagina ufficiale Candy, copia locale dell’intero URL `candy://`, inserimento in un prompt del terminale con input nascosto e immediata estrazione del solo valore necessario al refresh ibrido.

Quel callback è sensibile quanto una credenziale temporanea. Non va incollato in una chat, in un issue tracker o in un log. Per questo lo script non lo mostra a video e i test controllano che token e callback non finiscano nell’output.

Superato questo confine, il cloud rispose. E iniziò una seconda indagine.

## Ogni errore di schema raccontava qualcosa del dominio

Il catalogo della BWM 149PH7 conteneva 19 record. La prima normalizzazione fallì perché alcuni `command_parameters` avevano una validazione vuota. Correggere il problema accettando qualsiasi cosa sarebbe stato facile, ma pericoloso: una stringa vuota in un campo opzionale non ha lo stesso significato di un valore mancante in `selector_position`, `pr_code` o nella temperatura predefinita.

La regola divenne quindi conservativa: i valori opzionali vuoti venivano trattati come assenti; quelli obbligatori continuavano a produrre un errore esplicito.

Il tentativo successivo mise in luce valori `null` in campi come tipo di asciugatura, vapore, dose di detersivo o capacità massima. Anche qui il punto non era “far passare il JSON”, ma distinguere ciò che serviva davvero a costruire un ciclo da metadati opzionali non valorizzati per quel programma.

Poi arrivò l’errore sui bit sconosciuti delle opzioni. Una diagnostica sicura stampò soltanto nomi dei programmi, maschere numeriche e tipi anomali. I risultati erano molto più utili di un’altra ipotesi:

- `available_options` occupava la prima maschera e usava combinazioni comprese tra 0 e 255;
- `available_options2` valeva 1 per sei programmi e 0 per gli altri;
- le anomalie `null` riguardavano campi opzionali;
- i campi necessari alla mappatura dei programmi erano presenti.

Il secondo valore non era rumore. Coincideva con ciò che il codice decompilato chiamava seconda maschera e con il controllo dedicato a Zoom.

## Due maschere, un payload completo e un falso programma

La mappatura finale delle opzioni usa quindi due insiemi di bit. `OptMsk1` contiene le opzioni tradizionali — prelavaggio, igiene, antipiega, risciacqui extra e Aqua Plus — mentre Zoom usa il bit 1 di `OptMsk2`.

Anche il comando di avvio è stato portato alla forma completa ricostruita dall’app. In forma abbreviata, la struttura è questa:

```text
Write / StSt
PrNm / PrCode / PrStr
TmpTgt / SLevTgt / SpdTgt
OptMsk1 / OptMsk2
Lang / Stm / Dry / ...
```

Non pubblico qui chiavi, identificativi o dati di rete: non servono per capire la conclusione tecnica. Il punto è che il “numero del programma” non era un’informazione sufficiente. Il comando dell’app porta con sé selettore, codice, nome logico, parametri effettivi e due maschere di opzioni.

Tra i 19 record compariva però `DUAL_WM_WD_OFF`. Il primo import lo aveva trasformato automaticamente nello slug `dual-wm-wd-off`, facendolo apparire come un normale programma. Una prova locale con il trasporto simulato dimostrò che FastAPI lo avrebbe accettato e avrebbe tentato di inviarlo.

`OFF` non è un normale ciclo da offrire all’utente. È uno stato tecnico. La soluzione finale applica una difesa in profondità: i nuovi import lo escludono, i cataloghi già creati restano leggibili, Web e CLI non lo mostrano e una richiesta API manuale viene rifiutata prima della costruzione del payload, del recupero della chiave e del trasporto.

Per questo il file originario può conservare 19 record mentre l’interfaccia espone 18 programmi avviabili. Non è una discrepanza: è la differenza tra dati ricevuti e azioni sicure offerte all’utente.

## Da endpoint funzionante a interfaccia fail-safe

La prima versione di `POST /api/start` aveva un altro problema: una richiesta valida veniva trasmessa immediatamente. Per un’API che controlla un dispositivo fisico, “funziona” non è un criterio sufficiente. Bisogna anche rendere difficile l’azione accidentale.

Ho invertito quindi il comportamento predefinito. Se `dry_run` manca, FastAPI valida il programma, costruisce il payload e lo restituisce, ma non recupera la chiave e non invia nulla. L’invio reale richiede `dry_run: false`.

Una revisione finale ha trovato un dettaglio ancora più sottile. Il tipo booleano standard di Pydantic accettava valori come `0`, `"0"` e `"false"`, convertendoli in `False`. In altre parole, valori che non erano il booleano JSON richiesto avrebbero potuto attraversare il confine dell’invio reale.

Il campo è diventato quindi un booleano rigoroso. Soltanto `true` e `false` autentici sono validi; stringhe, numeri, `null`, liste e oggetti ricevono HTTP 422 prima del payload e del trasporto.

Nella pagina Web ho aggiunto una spunta **Invio reale**, normalmente disattivata. Senza spunta il pulsante dice **Simula programma**. Con la spunta diventa **Avvia lavaggio**, ma prima della richiesta mostra una conferma con il programma selezionato. Dopo annullamento, successo o errore, la spunta torna automaticamente disattivata.

Il comando Stop è rimasto separato: è un’azione reale, protetta dalla propria conferma. Non ho cercato di uniformare artificialmente due operazioni con rischi e scopi differenti.

## Il risultato, e ciò che lo ha prodotto

Il risultato finale non è soltanto una tabella di numeri programma. È una piccola catena verificabile:

- il cloud fornisce il catalogo specifico della BWM 149PH7;
- 18 cicli sono esposti come avviabili;
- il record tecnico `OFF` viene filtrato e bloccato;
- Zoom è rappresentato da `OptMsk2=1`;
- il payload usa la struttura completa dell’app;
- FastAPI simula per impostazione predefinita;
- soltanto un booleano JSON `false` rigoroso abilita l’invio;
- l’interfaccia richiede una spunta e una conferma per l’azione reale.

La suite finale contiene 172 test superati. Verifica importazione, schema, autenticazione, callback, payload, maschere, CLI, FastAPI, pagina Web, valori booleani non validi e percorsi di stop. Durante i test nessun comando è stato inviato alla lavatrice. Il catalogo originale è rimasto byte per byte invariato, controllato tramite SHA‑256.

È importante anche dire cosa questo risultato **non** dimostra. Non è un protocollo ufficialmente supportato da Candy, non garantisce compatibilità con altri modelli e potrebbe cambiare con una nuova versione dell’app o del servizio cloud. È un’integrazione costruita per un elettrodomestico e un account sotto il controllo del proprietario, verificata in modo conservativo sul materiale disponibile.

La parte più interessante, però, non è il numero finale dei programmi. È il percorso che ha portato fin lì.

Un errore di autenticazione non indicava una password sbagliata, ma un client obsoleto. Una pagina bianca non era un flusso fallito, ma un redirect che Windows non sapeva gestire. I `null` e le stringhe vuote non erano sporcizia da cancellare, ma informazioni sulla differenza tra campi obbligatori e opzionali. Un bit sconosciuto non era necessariamente un errore: era la seconda maschera che mancava al modello. Il diciannovesimo record non era un programma in più, ma uno stato tecnico da non rendere azionabile.

La decompilazione è stata fondamentale, ma non ha “risolto tutto”. Ha fornito ipotesi precise. I dati reali hanno deciso quali fossero applicabili. I test hanno trasformato quelle decisioni in confini ripetibili. Infine, il design fail-safe ha riconosciuto una cosa che nei progetti IoT è facile dimenticare: dietro una richiesta HTTP non c’è soltanto una risposta JSON. C’è una macchina fisica che può partire davvero.

Ed è proprio per questo che il risultato finale non cerca di rendere l’invio invisibile. Lo rende esplicito.
