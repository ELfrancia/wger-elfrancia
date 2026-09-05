# Onyx Mobile Hardening & HyperOS Super Island / Android 16 Live Updates Report

## 1. Executive Summary

This remediation completes the end-to-end hardening of the **Onyx Mobile App** (`mobile-app/`) integrated into the monorepo `wger-elfrancia` on branch `feat/mobile-island`. It delivers:
- **Build Infrastructure Hardening**: Pinned **AGP 8.13.0** + **Gradle 8.13**, OpenJDK 21 integration, release signing configuration (`keystore.properties`), and cross-platform build scripts (`build.ps1`, `build.sh`).
- **Native Live Island Engine**: Pure Java (`android.builtInKotlin=false`) foreground service (`OnyxLiveService`) and Capacitor plugin (`OnyxLivePlugin` / `@CapacitorPlugin(name = "WorkoutTimer")`) supporting both **Xiaomi HyperOS Super Island Focus Notifications** (`miui.focus.*` with RemoteViews ring progress) and **Android 16 Live Updates** (`POST_PROMOTED_NOTIFICATIONS`, `setRequestPromotedOngoing(true)`).
- **Dual-State Dynamic Lifecycle**: Workout session live tracking (`onyx_workout_progress_channel`, ID 1003) alongside Rest Countdown live notifications (`onyx_timer_live_channel`, ID 1001) and Looping Alarm (`onyx_timer_alarm_channel`, ID 1002).
- **Web App & Fallback Notch Integration**: Server templates and client JS with bidirectional bridge (`onyxNative`), pure math workout progress calculation, and conditional in-DOM dynamic notch fallback strictly displayed when native promoted ongoing notifications are unavailable.

---

## 2. Remediation Phase Table

| Phase | Description | Key Files Modified / Created | Status |
|---|---|---|---|
| **Phase 0** | Monorepo Baseline & Contract Definition | `mobile-app/`, `.gitignore`, `mobile-app/ISLAND_CONTRACT.md` | **COMPLETED** |
| **Phase 1** | Build Hardening & Gradle 8.13 Upgrade | `mobile-app/android/build.gradle`, `gradle-wrapper.properties`, `gradle.properties`, `app/build.gradle`, `build.ps1`, `build.sh`, `README.md`, `keystore.properties.example` | **COMPLETED** |
| **Phase 2** | Native HyperOS & Android 16 Live Layer | `AndroidManifest.xml`, `OnyxLiveService.java`, `OnyxLivePlugin.java`, `IslandNotificationFactory.java`, `HyperFocusExtras.java`, `DeviceCapabilities.java`, `island_ring.xml`, `island_ring_progress.xml`, `MainActivity.java`, `DeviceCapabilitiesTest.java` | **COMPLETED** |
| **Phase 3** | Web Bridge, Fallback Notch & Templates | `wger/manager/templates/workout/log_tailwind.html`, `wger/core/templates/navigation_tailwind.html`, `wger/core/templates/template_tailwind.html`, `wger/core/templates/sw.js` | **COMPLETED** |
| **Verification** | Gradle Tests, Django Suite & Dist Export | `mobile-app/dist/OnyxWorkout-debug-latest.apk`, 269 Django unit tests, Android unit tests | **COMPLETED** |

---

## 3. Poco F6 Pro (HyperOS / Android 16) Verification Checklist

Follow these exact steps to verify the build on your Xiaomi Poco F6 Pro:

### A. Sideloading & Installation
1. Locate the debug APK:
   `C:\Users\franc\Desktop\Codex\Workout_app\wger-elfrancia\mobile-app\dist\OnyxWorkout-debug-latest.apk`
2. Connect your Poco F6 Pro via USB or transfer via ADB:
   ```bash
   adb install -r dist/OnyxWorkout-debug-latest.apk
   ```

### B. Permissions & HyperOS Settings
1. Launch the Onyx app.
2. Grant **Notifiche** (`POST_NOTIFICATIONS`) and **Notifiche Promosse / Live Updates** (`POST_PROMOTED_NOTIFICATIONS`).
3. In HyperOS Settings:
   - Go to *Impostazioni -> Notifiche e barra di stato -> Notifiche Focus*.
   - Verify *Onyx Workout* is enabled for Focus Notifications (Super Island).
   - In *Impostazioni Batteria*, select *Nessuna restrizione* for Onyx Workout.

### C. Live Activity & Workout Progress Test
1. Start an active workout session from the app.
2. Observe the Super Island / Status Bar pill:
   - **Compressed Pill**: Displays the circular ring filling smoothly according to `completedSets / totalSets`.
   - **Expanded Pill**: Displays the workout title and current exercise name (e.g. `Panca Piana Bilanciere`).
3. Complete a set in the app -> Observe the ring progress and count update immediately.
4. Tap the notification / pill:
   - Opens the active workout logging screen directly.

### D. Rest Countdown & Alarm Test
1. Log a set to trigger the rest timer (e.g. 45s or 60s).
2. Lock the phone or swipe to Home:
   - Dynamic notification 1001 shows live countdown (`MM:SS`) with -30s / +30s and Pause/Resume action buttons.
3. Allow timer to reach `00:00`:
   - Notification transitions into full-screen high-priority alarm notification (1002) with sound and vibration.
   - Tap "Ferma Allarme" -> Alarm stops cleanly, notification dismisses, and workout session continues in background.

### E. In-DOM Fallback Test (Browser / Desktop)
1. Open the web version in Chrome / Safari (without native Android bridge).
2. Start a workout session:
   - The top in-DOM dynamic notch `#onyx-dynamic-notch` appears with smooth progress ring and remaining count.
   - When rest timer starts, the hourglass circle and seconds countdown take over the notch pill.

---

## 4. Release Keystore Generation Instructions

Per produrre una APK di Release firmata pronta per l'installazione o distribuzione:

### A. Generazione del Keystore (Operazione da eseguire una sola volta a mano)
Apri un terminale nella cartella `mobile-app/android/` ed esegui il comando seguente (disponibile con JDK 17/21):
```bash
keytool -genkeypair -v -keystore onyx-release-key.jks -alias onyx-release-key -keyalg RSA -keysize 2048 -validity 10000
```
> [!IMPORTANT]
> **PERCHÉ QUESTO FILE NON VA MAI PERSO:**
> Il keystore (`onyx-release-key.jks`) e le relative password definiscono l'identità crittografica dell'applicazione Android. Se questo file viene perso o sovrascritto, **non sarà più possibile aggiornare l'app già installata sul telefono** (Android blocca l'aggiornamento se la firma non coincide). L'utente sarebbe costretto a disinstallare l'app e reinstallarla da zero, **perdendo tutti i dati locali, le sessioni e le impostazioni**. Conserva questo file e le password in un luogo sicuro e protetto da backup.

### B. Configurazione `keystore.properties`
1. Copia il template:
   ```bash
   cp mobile-app/android/keystore.properties.example mobile-app/android/keystore.properties
   ```
2. Compila `keystore.properties` con le credenziali usate al punto A:
   ```properties
   storeFile=onyx-release-key.jks
   storePassword=LaTuaPasswordKeystore
   keyAlias=onyx-release-key
   keyPassword=LaTuaPasswordChiave
   ```
   *(Nota: `keystore.properties` e i file `.jks`/`.keystore` sono inclusi nel `.gitignore` e non devono mai essere committati nel repository Git).*

### C. Compilazione Release
Esegui la compilazione release:
- Via Gradle:
  ```bash
  cd mobile-app/android
  ./gradlew :app:assembleRelease
  ```
- Oppure tramite lo script di build:
  ```powershell
  powershell.exe -ExecutionPolicy Bypass -File .\build.ps1
  ```
L'APK release firmata sarà generata in:
`mobile-app/android/app/build/outputs/apk/release/app-release.apk` (o esportata in `mobile-app/dist/OnyxWorkout-release-latest.apk`).

---

## 5. Automated Test & Validation Results

- **Android Unit Tests (`testDebugUnitTest`)**: **100% PASSED** (`DeviceCapabilitiesTest` - capabilities structure, math boundary clamping, integer progress scaling).
- **Gradle Build (`assembleDebug`)**: **BUILD SUCCESSFUL** (AGP 8.13.0, Gradle 8.13, OpenJDK 21).
- **Django Manager & Core Test Suite**: **269/269 PASSED (0 failures, 0 errors)** (`python manage.py test wger.manager --settings=settings.ci`).
- **Artifact Generation**: Verified debug APK generated at `wger-elfrancia/mobile-app/dist/OnyxWorkout-debug-latest.apk` (4,286,140 bytes).
