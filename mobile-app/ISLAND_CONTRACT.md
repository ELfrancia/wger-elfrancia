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

### 1.2 Metodi Workout Island (Nuovi)
- `startWorkoutIsland({ title: string, totalSets: number, completedSets: number, currentExerciseName?: string, startedAt?: number, slotBoundaries?: number[] }): Promise<void>`
- `updateWorkoutIsland({ completedSets: number, totalSets: number, currentExerciseName?: string }): Promise<void>`
- `stopWorkoutIsland(): Promise<void>`

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
- `onyx_workout_progress_channel`: `IMPORTANCE_LOW`, silent.

### 3.3 Regola Anchor FGS (Foreground Service)
- Se una sessione di workout è attiva: la notifica `1003` fa da **anchor** per `startForeground(1003, ...)`. La notifica recupero `1001` viene pubblicata e cancellata via `NotificationManager.notify(1001, ...)` / `cancel(1001)` senza abbattere il service.
- Se nessun workout è attivo: la notifica recupero `1001` fa da **anchor** per `startForeground(1001, ...)`.
- Quando il timer scade, `1002` (allarme) viene promosso / notificato.

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
