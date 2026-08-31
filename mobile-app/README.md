# Onyx Mobile App (Android / Capacitor)

Wrapper Capacitor Android per l'applicazione di allenamento Onyx (PWA Django `wger-elfrancia`).
Include il supporto nativo completo a **Live Updates di Android 16** e all'anello dinamico **HyperOS Super Island** (Xiaomi).

---

## 1. Requisiti di Sistema

- **Node.js**: v18+ (con npm)
- **JDK**: Java 21 o Java 25 (è sufficiente il JBR incluso in Android Studio: `C:\Program Files\Android\Android Studio\jbr`)
- **Android SDK**: `API Level 36` (Android 16) con Build-Tools compatibili
- **Variabili d'ambiente**:
  - `ANDROID_HOME`: cartella SDK (es. `%LOCALAPPDATA%\Android\Sdk` su Windows o `~/Android/Sdk` su Linux)
  - `JAVA_HOME`: percorso JDK / JBR

---

## 2. Configurazione Rapida

### 2.1 File `local.properties` (opzionale se `ANDROID_HOME` è esportato)
Crea `mobile-app/android/local.properties`:
```properties
sdk.dir=C\:\\Users\\<tuo_utente>\\AppData\\Local\\Android\\Sdk
```

### 2.2 Installazione Dipendenze
```bash
cd mobile-app
npm install
```

---

## 3. Build dell'Applicazione

### 3.1 Script Automatici
Gli script gestiscono l'intero ciclo: `npm install` (se necessario), `npx cap sync android`, compilazione Gradle e copia degli APK in `mobile-app/dist/`.

- **Windows (PowerShell)**:
  ```powershell
  cd mobile-app
  .\build.ps1
  ```

- **Linux / macOS / Git Bash**:
  ```bash
  cd mobile-app
  chmod +x build.sh
  ./build.sh
  ```

Gli APK generati si troveranno in `mobile-app/dist/`:
- `OnyxWorkout-debug-latest.apk`
- `OnyxWorkout-release-latest.apk` (se `keystore.properties` è presente)

---

## 4. Firma Release (Keystore)

Per motivi di sicurezza, il keystore di produzione e le password non sono tracciati in Git.

### 4.1 Generazione Keystore con `keytool`
Esegui da riga di comando:
```bash
keytool -genkeypair -v \
  -keystore mobile-app/android/app/onyx-release-key.keystore \
  -alias onyx-release-key \
  -keyalg RSA \
  -keysize 2048 \
  -validity 10000
```

### 4.2 Configurazione `keystore.properties`
Copia il file template:
```bash
cp mobile-app/android/keystore.properties.example mobile-app/android/keystore.properties
```
Compila `mobile-app/android/keystore.properties` con i valori scelti:
```properties
storeFile=app/onyx-release-key.keystore
storePassword=TuaPasswordSicuraStore
keyAlias=onyx-release-key
keyPassword=TuaPasswordSicuraKey
```
Una volta configurato, `build.ps1` o `build.sh` genererà automaticamente l'APK release firmato.

---

## 5. Sideload & Installazione sul Device

1. Abilita **Opzioni Sviluppatore** e **Debug USB** sul dispositivo (es. Poco F6 Pro).
2. Collega il telefono via USB o WiFi ADB.
3. Installa l'APK debug con:
   ```bash
   adb install -r mobile-app/dist/OnyxWorkout-debug-latest.apk
   ```

---

## 6. Incremento Versione

Per rilasciare un aggiornamento:
1. Modifica `mobile-app/android/app/build.gradle`:
   - Incrementa `versionCode` (es. `2`)
   - Modifica `versionName` (es. `"1.1"`)
2. Rigenera il build con `.\build.ps1`.

---

## 7. Nota Fondamentale su Capacitor

I file nelle seguenti cartelle sono generati automaticamente da Capacitor (`npx cap sync android`):
- `mobile-app/android/capacitor.build.gradle`
- `mobile-app/android/capacitor.settings.gradle`
- `mobile-app/android/capacitor-cordova-android-plugins/`

**NON editare a mano questi file.** Qualsiasi modifica deve essere apportata in `capacitor.config.json` o nel modulo `:app`.
