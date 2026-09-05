# Guida Firma APK Release - Onyx Workout

Questa guida descrive i passi per generare il Keystore di produzione e compilare l'APK di Release firmata.

---

## 1. Generazione del Keystore di Produzione (Una tantum)

Apri un terminale nella directory `mobile-app/android/` ed esegui il seguente comando `keytool` (incluso in JDK 17 / 21):

```bash
keytool -genkeypair -v -keystore onyx-release-key.jks -alias onyx-release-key -keyalg RSA -keysize 2048 -validity 10000
```

### Parametri del comando:
- `-keystore onyx-release-key.jks`: Nome del file archivio delle chiavi.
- `-alias onyx-release-key`: Identificatore univoco della chiave all'interno del keystore.
- `-keyalg RSA -keysize 2048`: Algoritmo crittografico standard e dimensione della chiave.
- `-validity 10000`: Validità del certificato in giorni (~27 anni, richiesto da Android per garantire aggiornamenti continuativi).

> [!WARNING]
> **PERCHÉ QUESTO FILE NON DEVE MAI ESSERE PERSO:**
> Il file `.jks` e le relative password costituiscono l'identità crittografica dell'applicazione Android.
> Se questo file viene perso o cancellato, **non sarà più possibile pubblicare o installare aggiornamenti sopra l'app esistente**: il sistema operativo Android bloccherà l'installazione per discrepanza di firma (`INSTALL_FAILED_UPDATE_INCOMPATIBLE`). L'utente sarà costretto a disinstallare manualmente l'app e reinstallarla da zero, **perdendo tutti i dati locali, le impostazioni e la cronologia degli allenamenti**.
> Conserva il file `.jks` e le password in una cartella sicura e protetta da backup (es. password manager, cloud storage protetto).

---

## 2. Configurazione Credenziali (`keystore.properties`)

1. Nella cartella `mobile-app/android/`, crea il file `keystore.properties` partendo dal template:
   ```bash
   cp keystore.properties.example keystore.properties
   ```
2. Compila i 4 campi con le credenziali utilizzate al punto 1:
   ```properties
   storeFile=onyx-release-key.jks
   storePassword=LaTuaKeystorePassword
   keyAlias=onyx-release-key
   keyPassword=LaTuaKeyPassword
   ```

> [!NOTE]
> Il file `keystore.properties` e tutti i file `.jks` / `.keystore` sono inclusi in `.gitignore` e **non verranno mai committati** nel repository Git.

---

## 3. Compilazione dell'APK Release

### Tramite Gradle (consigliato)
```bash
cd mobile-app/android
./gradlew :app:assembleRelease
```
*(Su Windows PowerShell: `.\gradlew.bat :app:assembleRelease`)*

L'APK release firmata e pronta per l'installazione verrà generata in:
`mobile-app/android/app/build/outputs/apk/release/app-release.apk`

### Comportamento di sicurezza di Gradle:
- Se `keystore.properties` **non è presente**, `assembleDebug` continua a funzionare regolarmente per lo sviluppo quotidiano.
- Se si tenta di eseguire `assembleRelease` **senza** `keystore.properties` (o con un percorso keystore inesistente), Gradle si interrompe immediatamente fornendo un messaggio di errore chiaro e dettagliato con le istruzioni da seguire.
