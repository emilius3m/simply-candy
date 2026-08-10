# Candy Lavatrice - App Flutter

App multi-piattaforma per controllare la lavatrice **Candy BWM 149PH7** via API
WiFi locale. Parla **direttamente** con la lavatrice (HTTP in chiaro), senza
alcun server intermedio.

## Funzionalità

- 📊 **Monitoraggio stato**: stato macchina, fase, tempo residuo, temperatura,
  centrifuga, programma corrente.
- ▶️ **Avvio programmi**: selezione da catalogo + override temperatura/centrifuga/
  livello sporco + opzioni (prewash, hygiene, aquaplus, ...).
- ■ **Stop** del ciclo in corso.
- ☁️ **Import programmi dal cloud Candy**: login OAuth integrato, scarica il
  catalogo ufficiale del tuo modello.
- 💾 **Catalogo pre-caricato**: l'app funziona subito con i 19 programmi del
  BWM 149PH7 bundled come asset (fallback se non si fa il login cloud).

## Piattaforme

Compilabile per: **Android, iOS, Windows, macOS, Linux**.

## Build

### Prerequisiti
- Flutter 3.44+ (https://docs.flutter.dev/get-started/install)
- Per Windows: Visual Studio con workload "Desktop development with C++"
- Per Android: Android SDK (impostare ANDROID_HOME)

### Comandi

```bash
cd flutter_app
flutter pub get

# Windows (exe)
flutter build windows
# -> build\windows\x64\runner\Release\candy_app.exe

# Android (APK)
flutter build apk --release
# -> build\app\outputs\flutter-apk\app-release.apk

# macOS
flutter build macos

# Linux
flutter build linux
```

## Avvio rapido

1. Avvia l'app.
2. (Opzionale) **Impostazioni → Indirizzo IP**: imposta l'IP della lavatrice
   (default `192.168.1.235`).
3. **Stato → ↻ Aggiorna**: legge lo stato corrente.
4. **Avvio**: seleziona un programma, eventuali override, premi **Avvia**.

### Importare i programmi dal cloud (consigliato al primo avvio)

L'app include già i 19 programmi del BWM 149PH7, ma per ottenere il catalogo
aggiornato dal tuo account Candy:

1. **Impostazioni → Importa programmi dal cloud**.
2. Si apre il browser per il login Candy (account simply-Fi/hOn).
3. Dopo il login, il browser reindirizza a `candy://...`:
   - **Mobile**: l'app intercetta il deep link automaticamente.
   - **Desktop**: copia l'URL `candy://...` e incollalo nel campo dell'app.
4. L'app scarica e salva il catalogo aggiornato.

> ⚠️ **Conflitto deep link**: se sul telefono è installata l'app Candy simply-Fi
> ufficiale, quella potrebbe intercettare il deep link `candy://`. In tal caso
> Android mostra un selettore: scegli questa app. In alternativa usa il fallback
> manuale (copia/incolla).

## Architettura

```
lib/
├── main.dart                    # UI (Stato, Avvio, Impostazioni) + routing
├── core/
│   ├── crypto.dart              # XOR encode/decode + getkey (3 livelli: cache, BM=1, known-plaintext)
│   ├── candy_local.dart         # client HTTP locale (read/write/stop, payload completo 18 campi)
│   ├── candy_cloud.dart         # OAuth CIAM + fetch appliances + normalizzazione catalogo
│   └── programs.dart            # modelli catalogo + OPTION_BITS (2 maschere) + validazione
├── data/
│   └── app_state.dart           # stato Provider (IP, chiave cache, catalogo persistito)
└── assets/
    └── programs.json            # 19 programmi del BWM 149PH7 (fallback)
```

### Protocollo

Porting fedele dei moduli Python (vedi cartella genitore `C:\xampp\candy`):

- **Cifratura XOR** a 16 byte, chiave fissa per dispositivo, derivata via
  endpoint `BM=1` o attacco known-plaintext sul read endpoint.
- **Comandi**: GET in chiaro, payload cifrato XOR → hex nell'URL
  (`http-write.json?encrypted=1&data=<hex>`).
- **Payload di avvio**: 18 campi in ordine fisso (come l'app ufficiale):
  `Write, StSt, DelVl, PrNm, PrCode, PrStr, TmpTgt, SLevTgt, SpdTgt, OptMsk1,
  OptMsk2, Lang, Stm, Dry, ED, RecipeId, StartCheckUp, DispTestOn`.

## Sicurezza

- Il callback OAuth (`candy://...`) contiene token sensibili. Non condividerlo.
- IP e chiave cache sono persistiti localmente in `getApplicationSupportDirectory`.
- L'app non invia dati a terzi: comunica solo con la lavatrice (LAN) e,
  durante l'import, con i server Candy/Simply-Fi.
