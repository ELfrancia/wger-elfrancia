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
- `stopAll(): Promise<void>` — ferma timer, allarme e isola workout in un colpo solo: cancella la notifica `1001` (+ gli id legacy), l'exact alarm di backup e le SharedPreferences di stato persistite, poi `stopForeground(STOP_FOREGROUND_REMOVE)` + `stopSelf()` (incondizionato, non `stopSelfResult()`: un `ACTION_WORKOUT_UPDATE` già in coda non deve resuscitare la notifica). Gli intent di solo *aggiornamento* (`ACTION_WORKOUT_UPDATE`, `ACTION_UPDATE_TIMER`, fg/bg) che arrivano entro **2s** da uno `stopAll()` vengono scartati per la stessa ragione; un `startTimer()` / `startWorkoutIsland()` nuovo non viene mai bloccato. **Non dipende dallo stato in memoria** (unico caso in cui il nativo può concludere "non c'è niente" senza prima fare restore) ed è **idempotente**: può arrivare più volte di fila (fine allenamento + riconciliazione server) senza effetti collaterali. Lato non-Capacitor: `window.AndroidTimer.stopAll()` (nessun valore di ritorno).
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

### 3.1 ID Notifica — UNA SOLA
- `1001` (`IslandNotificationFactory.NOTIFICATION_ID_LIVE`): **l'unica notifica che l'app posta, in qualunque stato**. Il contenuto è funzione dello stato, con questa priorità:
  1. **allarme** (recupero scaduto): card lime "TEMPO SCADUTO!", full-screen intent, azione "DISATTIVA ALLARME";
  2. **timer di recupero** attivo/in pausa: countdown `ProgressStyle` + azioni Pausa / +30s / Stop;
  3. **allenamento in corso**: fill progress `completedSets / totalSets` + azione "Termina" (→ `ACTION_STOP_ALL`).
  Il contesto allenamento (serie / esercizio) viene inglobato come `subText`/`contentText` nei rendering 1 e 2: **non esiste più una seconda notifica**.
- `1000` / `1002` / `1003` sono **legacy** (`LEGACY_NOTIFICATION_IDS`): nessun percorso li posta più, vengono solo `cancel()`ati a ogni `onCreate()`, a ogni post e a ogni teardown, per ripulire installazioni aggiornate a caldo.

> Storico: i tre id separati + l'anchor 1000 erano la causa delle **3 notifiche Onyx simultanee** (timer + "allenamento in corso" + serie).

### 3.2 Canale Notifica — UNO SOLO
- `onyx_live_v3`: `IMPORTANCE_HIGH`, `setSound(null, null)`, vibrazione disattivata (suono e vibrazione dell'allarme sono pilotati a mano dal service), `showBadge(false)`, `VISIBILITY_PUBLIC`.
- I canali precedenti (`onyx_timer_live_channel`, `onyx_timer_alarm_channel`, `onyx_workout_progress_channel`, `onyx_workout_progress_channel_v2`) vengono cancellati con `deleteNotificationChannel()` al primo avvio di questa build.

### 3.3 Regola Anchor FGS (Foreground Service)
- `startForeground(1001, ...)` **sempre**, in ogni stato. Non esiste più un anchor separato: anche l'anchor minimale di un service ricreato a freddo senza stato usa l'id `1001`, quindi non può coesistere con la notifica reale.
- Quando lo stato cambia (workout → timer → allarme) la stessa notifica viene sostituita con `notify(1001, ...)`, così la Super Island di HyperOS aggiorna la pill esistente invece di crearne una nuova.

### 3.4 Sincronizzazione Countdown & Refresh Periodico
Il testo del countdown (`setWhen`/`setUsesChronometer(true)`/`setChronometerCountDown(true)`) è renderizzato dal sistema a partire dalla deadline assoluta (`targetEndTimeMs`), quindi resta sempre live indipendentemente da quando la notifica viene ri-renderizzata. La barra `ProgressStyle`, invece, è un valore statico impostato all'ultimo `notify()`, quindi va rinfrescata.

Regole di cadenza (vincolanti, per batteria e calore):
- il ticker gira **solo** mentre il timer di recupero è attivo e non in pausa — mai per il solo allenamento in corso, mai a timer fermo, mai come polling di stato;
- **mai più di 1 `notify()` al secondo**: `TICK_BG_MS = 1000ms` con app in background (la Super Island deve sembrare fluida), `TICK_FG_MS = 5000ms` con app in foreground (dove a mostrare il timer è già la notch in-app);
- la notifica dell'allenamento è **event-driven**: si ri-renderizza solo su `updateWorkoutIsland()`, cambio di stato o transizione foreground/background.

### 3.4.1 Consegna dell'allarme di fine recupero (idempotente)
Tre percorsi possono far scattare l'allarme: `CountDownTimer.onFinish()`, il broadcast dell'exact alarm (`TimerExpiryAlarmReceiver`) e un riavvio a freddo che trova la deadline già passata. L'idempotenza è su `targetEndTimeMs` (`alarmDeliveredForTargetMs`), **non** sul flag "sta suonando qualcosa": con `soundUri = "vibration_only"` non suona mai nulla. Lo stato logico `isAlarmActive` è separato dal flag audio `isAlarmPlaying`.

L'exact alarm usa `setExactAndAllowWhileIdle(RTC_WAKEUP, ...)` con `PendingIntent.FLAG_IMMUTABLE`, previo `canScheduleExactAlarms()` su Android 12+ (fallback a `setAndAllowWhileIdle`). Se il receiver non riesce ad avviare il foreground service (restrizioni background-FGS su Android 12+), posta **lui stesso** la card "TEMPO SCADUTO" sull'id `1001`: stesso id ⇒ nessun duplicato possibile.

### 3.4.2 Wakelock, chiusura app e policy di restart
- `PARTIAL_WAKE_LOCK` **solo** per la durata effettiva del countdown (timeout = `remaining + 5s`, tetto 30 min) o della suoneria (2 min). Mai per un allenamento in corso. Rilasciato in `finally` e azzerato (`wakeLock = null`) appena non è più held.
- `onTaskRemoved()` (swipe-up dalle recenti): se **non** c'è un allenamento attivo né un countdown vivo né un allarme, teardown completo (notifica, exact alarm, wakelock, stato persistito) + `stopSelf()`. Non dipende da nessun percorso JS. Se un allenamento è attivo il service resta, ma senza wakelock e senza ticker.
- `onStartCommand()` ritorna `START_REDELIVER_INTENT` **solo** se c'è un countdown vivo o un allarme in corso; altrimenti `START_NOT_STICKY`, così il processo muore davvero invece di essere resuscitato all'infinito dopo ogni kill.
- `FLAG_KEEP_SCREEN_ON` viene applicato solo mentre c'è un allenamento o un timer attivo, non per tutta la permanenza in app.

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
