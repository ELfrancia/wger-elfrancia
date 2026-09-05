# ISLAND_CONTRACT.md — Contratto Condiviso Isola / Live Updates Onyx

Questo documento definisce il contratto tecnico congelato tra il layer nativo Android (Java / Capacitor) e il layer web/PWA (Django Tailwind Templates & JavaScript client-side).

---

## 1. Plugin Capacitor: `WorkoutTimer`

Il plugin nativo risponde al nome JavaScript `"WorkoutTimer"` (mantenendo piena retrocompatibilità con i chiamanti esistenti) ed è esposto da `OnyxLivePlugin.java`.

### 1.1 Metodi Timer Recupero (Invariati)
- `startTimer({ durationSeconds: number, title?: string, soundUri?: string }): Promise<void>`
- `pauseTimer(): Promise<void>`
- `resumeTimer(): Promise<void>`
- `addSeconds({ seconds?: number }): Promise<void>` (default +30s)
- `stopTimer(): Promise<void>`
- `stopAlarm(): Promise<void>`

`soundUri` accetta: assente/vuoto (default — traccia bundle `onyx_alarm`, vedi §3.4), `"system_alarm"` (suoneria di sistema), `"gong"`/`"boxing"`/`"whistle"`/`"beep"` (toni sintetizzati), `"vibration_only"`, oppure un URI `content://` esplicito.

### 1.2 Metodi Workout Island (Nuovi)
- `startWorkoutIsland({ title: string, totalSets: number, completedSets: number, currentExerciseName?: string, startedAt?: number, slotBoundaries?: number[] }): Promise<void>`
- `updateWorkoutIsland({ completedSets: number, totalSets: number, currentExerciseName?: string }): Promise<void>`
- `stopWorkoutIsland(): Promise<void>`

### 1.2.1 Teardown incondizionato e query stato (Nuovi)
- `stopAll(): Promise<void>` — ferma timer, allarme e isola workout in un colpo solo: cancella le notifiche 1001/1002/1003, l'exact alarm di backup e le SharedPreferences di stato persistite, poi `stopForeground(STOP_FOREGROUND_REMOVE)` + `stopSelf()`. **Non dipende dallo stato in memoria** (unico caso in cui il nativo può concludere "non c'è niente" senza prima fare restore) ed è **idempotente**: può arrivare più volte di fila (fine allenamento + riconciliazione server) senza effetti collaterali. Lato non-Capacitor: `window.AndroidTimer.stopAll()` (nessun valore di ritorno).
- `getTimerState(): Promise<TimerStateResult>` — stato reale letto sincronicamente dal mirror statico di `OnyxLiveService` (fonte di verità, non la copia lato web):
  ```typescript
  {
    isRunning: boolean,
    isPaused: boolean,
    isWorkoutActive: boolean,
    deadlineEpochMs: number | null,   // assoluto (System.currentTimeMillis() + remaining); null se non isRunning o se in pausa
    remainingSeconds: number | null,  // fallback comodo; quando isRunning && !isPaused la fonte di verità resta deadlineEpochMs
    title?: string
  }
  ```
  Se nessun timer è attivo: `{ isRunning: false, isPaused: false, isWorkoutActive: false, deadlineEpochMs: null, remainingSeconds: null }`.
  Lato non-Capacitor: `window.AndroidTimer.getTimerState()` è **sincrono** e ritorna una **stringa JSON** (i `@JavascriptInterface` non possono restituire una Promise/oggetto nativo) — `JSON.parse(window.AndroidTimer.getTimerState())`.

### 1.2.2 `AndroidTimer` — Bridge Fallback Non-Capacitor
`window.AndroidTimer` (`MainActivity.AndroidTimerBridge`, `@JavascriptInterface`) è il path usato quando il plugin Capacitor `WorkoutTimer` non è disponibile. Rispecchia gli stessi metodi di `WorkoutTimer` ma **sincroni** (nessuna Promise):
- `startWorkout(title, startTimestampMs)` — legacy, isola parte "0/totalSets" finché non arriva il primo `updateProgress`.
- `startWorkoutWithProgress(title, startTimestampMs, totalSets, completedSets)` — **preferire questo quando il chiamante conosce già i conteggi** (es. `initOnyxWorkoutIsland` in `log_tailwind.html`, che li calcola dal DOM prima di chiamare `onyxNative.workoutStart(...)`).
- `stopWorkout()`, `updateProgress(completed, total, remaining)`, `updateProgressWithExercise(completed, total, remaining, currentExercise)`
- `startTimer(durationSeconds, title)`, `startTimerWithSound(durationSeconds, title, soundUri)`, `updateTimer(durationSeconds)`, `updateNotification(durationSeconds, remainingSeconds)`, `pauseTimer()`, `resumeTimer()`, `addSeconds(seconds)`, `stopTimer()`, `stopAlarm()`
- `stopAll()` — vedi §1.2.1, stessa semantica incondizionata/idempotente.
- `getTimerState()` — vedi §1.2.1, ritorna una **stringa JSON** (sincrono).
- `hasActiveOngoingNotification()`, `isBatteryUnrestricted()`, `isXiaomiDevice()`, `requestBatteryExemption()`, `openXiaomiAutostart()`, `openXiaomiBatterySaver()`, `areNotificationsEnabled()`, `canPostPromotedNotifications()`, `requestAllPermissions()`, `openNotificationSettings()`, `testNotification()`.

### 1.3 Feature Detection
- `getCapabilities(): Promise<CapabilitiesResult>`
  - `CapabilitiesResult`:
    ```typescript
    {
      platform: "android" | "web" | "ios",
      sdkInt: number,
      promotedOngoing: boolean,       // true su Android 16+ con permesso POST_PROMOTED_NOTIFICATIONS concesso
      hyperOsFocus: boolean,          // true se Xiaomi / HyperOS con supporto notifica focus
      manufacturer: string,           // es. "Xiaomi", "Google", "Samsung"
      notificationsEnabled: boolean
    }
    ```

### 1.4 Eventi Plugin
- `onTimerExpired`: `{ event: "timerExpired" }`
- `onTimerStopped`: `{ event: "timerStopped" }`
- `onTimerPaused`: `{ event: "timerPaused" }`
- `onTimerResumed`: `{ event: "timerResumed" }`
- `onWorkoutIslandTapped`: `{ event: "workoutIslandTapped" }`

---

## 2. Intent Service (`OnyxLiveService`)

Foreground Service nativo unificato per il ciclo di vita di allenamento e recupero.

### 2.1 Action Strings
- `com.onyx.workoutapp.ACTION_START`
- `com.onyx.workoutapp.ACTION_PAUSE`
- `com.onyx.workoutapp.ACTION_RESUME`
- `com.onyx.workoutapp.ACTION_ADD_TIME`
- `com.onyx.workoutapp.ACTION_STOP`
- `com.onyx.workoutapp.ACTION_STOP_ALARM`
- `com.onyx.workoutapp.ACTION_WORKOUT_START`
- `com.onyx.workoutapp.ACTION_WORKOUT_UPDATE`
- `com.onyx.workoutapp.ACTION_WORKOUT_STOP`
- `com.onyx.workoutapp.ACTION_STOP_ALL` — teardown incondizionato e idempotente (vedi §1.2.1); ignora lo stato in memoria/persistito, non fa mai restore.

### 2.2 Intent Extra Keys
- `extra_duration_seconds` (`int`)
- `extra_title` (`String`)
- `extra_sound_uri` (`String`)
- `extra_completed_sets` (`int`)
- `extra_total_sets` (`int`)
- `extra_current_exercise` (`String`)
- `extra_started_at` (`long`)
- `extra_slot_boundaries` (`int[]`)

---

## 3. Notifiche & Canali

### 3.1 ID Notifiche
- `1001`: Notifica Live Recupero (Drain progress, countdown `ProgressStyle` su Android 16, azioni Pause / +30s / Stop).
- `1002`: Notifica Allarme Sonoro & Vibrazione (Full-screen intent, pulsante "DISATTIVA ALLARME").
- `1003`: Notifica Live Workout (Fill progress `completedSets / totalSets`, pill compressa solo cerchio, testo esercizio espanso).

### 3.2 Canali Notifica
- `onyx_timer_live_channel`: `IMPORTANCE_HIGH`, no sound, no vibration (suono gestito dal service allarme).
- `onyx_timer_alarm_channel`: `IMPORTANCE_HIGH`, vibrazione attiva.
- `onyx_workout_progress_channel_v2`: `IMPORTANCE_DEFAULT`, silent (v2: bumpato da `IMPORTANCE_LOW`, immutabile dopo la creazione — il canale v1 pre-esistente viene ripulito best-effort).

### 3.3 Regola Anchor FGS (Foreground Service)
- Se una sessione di workout è attiva: la notifica `1003` fa da **anchor** per `startForeground(1003, ...)`. La notifica recupero `1001` viene pubblicata e cancellata via `NotificationManager.notify(1001, ...)` / `cancel(1001)` senza abbattere il service.
- Se nessun workout è attivo: la notifica recupero `1001` fa da **anchor** per `startForeground(1001, ...)`.
- Quando il timer scade, `1002` (allarme) viene promosso / notificato.

### 3.4 Sincronizzazione Countdown & Refresh Periodico
Il testo del countdown (`setWhen`/`setUsesChronometer(true)`/`setChronometerCountDown(true)`) è renderizzato dal sistema a partire dalla deadline assoluta (`targetEndTimeMs`), quindi resta sempre live indipendentemente da quando la notifica viene ri-renderizzata. La barra `ProgressStyle`, invece, è un valore statico impostato all'ultimo `notify()` — per evitare che resti visivamente ferma tra un cambio di stato esplicito e l'altro (pausa/+30s/stop), `OnyxLiveService` ri-renderizza la notifica ogni **5s** (`NOTIFICATION_TICK_MS`) mentre il timer è attivo e non in pausa. Cadenza deliberatamente non al secondo: la barra deve solo "sembrare viva", un `notify()` al secondo brucerebbe batteria/IPC senza beneficio percepibile (il testo, che è ciò che l'utente legge davvero, è già live).

### 3.5 Suono Allarme
Risorsa bundle di default: `res/raw/onyx_alarm.ogg` (traccia originale composta per il progetto — stab supersaw + kick in quattro, stile EDM/riser, 3.75s esatti/2 battute a 128 BPM, loop senza click grazie all'assenza di padding dell'encoder OGG; nessun problema di licenza, non è un brano di terze parti). Riprodotta via `MediaPlayer` con `AudioAttributes(USAGE_ALARM, CONTENT_TYPE_SONIFICATION)`, `setLooping(true)`. Fallback a cascata se la risorsa non carica: URI di sistema (`TYPE_ALARM` → `TYPE_RINGTONE` → `TYPE_NOTIFICATION`) → tono sintetizzato (`AudioTrack`, nessun asset esterno). `soundUri = "system_alarm"` salta direttamente alla suoneria di sistema. Copia gemella per il lato web: `wger/core/static/sounds/onyx_alarm.ogg` (+ `.mp3`).

---

## 4. Deep-Link & Navigazione

### 4.1 Extra Intent MainActivity
- `open_timer`: `boolean` -> apre l'overlay del timer di recupero (`#rest-timer`).
- `open_workout`: `boolean` -> porta la WebView in primo piano sulla sessione di allenamento attiva (`session_url` o reload sessione corrente).

---

## 5. Stato Client-Side (`localStorage`)

### 5.1 `onyx_active_rest_timer`
```json
{
  "durationSeconds": 90,
  "remainingMs": 85000,
  "startedAt": 1725120000000,
  "isRunning": true,
  "hasNotifiedZero": false,
  "expiredAt": null,
  "updatedAt": 1725120005000
}
```

### 5.2 `onyx_workout_progress`
```json
{
  "total": 16,
  "completed": 5,
  "remaining": 11,
  "currentExerciseName": "Panca Piana Bilanciere"
}
```
Usato dalla capsula di fallback in-DOM `#onyx-dynamic-notch` quando il rendering nativo Live Updates non è disponibile o non è abilitato.
