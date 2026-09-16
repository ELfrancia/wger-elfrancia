package com.onyx.workoutapp;

import android.app.AlarmManager;
import android.app.Notification;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.ServiceInfo;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.media.AudioAttributes;
import android.media.AudioFormat;
import android.media.AudioFocusRequest;
import android.media.AudioManager;
import android.media.AudioTrack;
import android.media.MediaPlayer;
import android.media.RingtoneManager;
import android.net.Uri;
import android.os.Build;
import android.os.CountDownTimer;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import android.os.PowerManager;
import android.os.VibrationEffect;
import android.os.Vibrator;
import android.os.VibratorManager;
import android.util.Log;
import androidx.annotation.Nullable;

public class OnyxLiveService extends Service {

    private static final String TAG = "OnyxDebug";

    public static final String ACTION_START = "com.onyx.workoutapp.ACTION_START";
    public static final String ACTION_STOP = "com.onyx.workoutapp.ACTION_STOP";
    public static final String ACTION_PAUSE = "com.onyx.workoutapp.ACTION_PAUSE";
    public static final String ACTION_RESUME = "com.onyx.workoutapp.ACTION_RESUME";
    public static final String ACTION_ADD_TIME = "com.onyx.workoutapp.ACTION_ADD_TIME";
    public static final String ACTION_UPDATE_TIMER = "com.onyx.workoutapp.ACTION_UPDATE_TIMER";
    public static final String ACTION_STOP_ALARM = "com.onyx.workoutapp.ACTION_STOP_ALARM";

    /**
     * Unconditional "stop everything" — cancels timer/alarm/workout notifications,
     * the exact-alarm backup and the persisted state snapshot regardless of what the
     * in-memory flags currently say, then tears the service down. The one action
     * allowed to conclude "nothing is here" without first restoring state: the caller
     * (web session-end or server reconciliation) is asserting it explicitly. Must be
     * safe to receive twice in a row (finish button + reconciliation both call it).
     */
    public static final String ACTION_STOP_ALL = "com.onyx.workoutapp.ACTION_STOP_ALL";

    /**
     * Fired by {@link TimerExpiryAlarmReceiver} from an exact AlarmManager alarm. Backup
     * path for when the OS froze/killed the service before its CountDownTimer reached
     * onFinish() (routine on HyperOS after the app is swiped away). Kept byte-identical to
     * {@link TimerExpiryAlarmReceiver#ACTION_TIMER_EXPIRED}.
     */
    public static final String ACTION_ALARM_BACKUP = "com.onyx.workoutapp.ALARM_TIMER_EXPIRED";

    /** Sent by MainActivity.onStart / onStop so the service can promote (bg) or demote (fg) its island. */
    public static final String ACTION_APP_FOREGROUND = "com.onyx.workoutapp.ACTION_APP_FOREGROUND";
    public static final String ACTION_APP_BACKGROUND = "com.onyx.workoutapp.ACTION_APP_BACKGROUND";

    public static final String ACTION_WORKOUT_START = "com.onyx.workoutapp.ACTION_WORKOUT_START";
    public static final String ACTION_WORKOUT_UPDATE = "com.onyx.workoutapp.ACTION_WORKOUT_UPDATE";
    public static final String ACTION_WORKOUT_STOP = "com.onyx.workoutapp.ACTION_WORKOUT_STOP";

    public static final String EXTRA_DURATION = "extra_duration_seconds";
    public static final String EXTRA_REMAINING_SECONDS = "extra_remaining_seconds";
    public static final String EXTRA_TITLE = "extra_title";
    public static final String EXTRA_SOUND_URI = "extra_sound_uri";
    public static final String EXTRA_COMPLETED_SETS = "extra_completed_sets";
    public static final String EXTRA_TOTAL_SETS = "extra_total_sets";
    public static final String EXTRA_CURRENT_EXERCISE = "extra_current_exercise";
    public static final String EXTRA_STARTED_AT = "extra_started_at";
    public static final String EXTRA_SLOT_BOUNDARIES = "extra_slot_boundaries";

    /**
     * THE notification id. There is exactly one, on exactly one channel, for every state
     * the service can be in (workout in progress / rest timer running / rest timer
     * expired). Even the throwaway "foreground anchor" posted by a cold-recreated service
     * with no live state uses it, so a second Onyx notification can never appear.
     */
    private static final int NOTIFICATION_ID_ANCHOR = IslandNotificationFactory.NOTIFICATION_ID_LIVE;

    /** SharedPreferences file that mirrors the live state so a killed service can restore it. */
    private static final String STATE_PREFS = "onyx_live_service_state";
    private static final int REQ_EXPIRY_ALARM = 7001;

    private NotificationManager notificationManager;
    private AlarmManager alarmManager;
    private CountDownTimer countDownTimer;
    private MediaPlayer mediaPlayer;
    private Vibrator vibrator;
    private AudioManager audioManager;
    private AudioFocusRequest audioFocusRequest;
    private PowerManager.WakeLock wakeLock;
    private AudioTrack synthesizedAudioTrack;

    /** Serializes all AudioTrack lifecycle calls (worker thread build/play vs main-thread stop). */
    private final Object audioLock = new Object();

    /** Re-renders the live notification periodically: 1s while in background/island, 5s in foreground. */
    private static final long TICK_BG_MS = 1000L;
    private static final long TICK_FG_MS = 5000L;
    private final Handler tickHandler = new Handler(Looper.getMainLooper());
    private final Runnable notificationTicker = new Runnable() {
        @Override
        public void run() {
            if (!isTimerRunning || isPaused) return;
            updateForegroundState();
            long interval = (!IslandNotificationFactory.appInForeground && isTimerRunning && !isPaused) ? TICK_BG_MS : TICK_FG_MS;
            tickHandler.postDelayed(this, interval);
        }
    };

    private void startNotificationTicker() {
        tickHandler.removeCallbacks(notificationTicker);
        long interval = (!IslandNotificationFactory.appInForeground && isTimerRunning && !isPaused) ? TICK_BG_MS : TICK_FG_MS;
        tickHandler.postDelayed(notificationTicker, interval);
    }

    private void stopNotificationTicker() {
        tickHandler.removeCallbacks(notificationTicker);
    }

    // Rest timer state
    /**
     * AUDIO flag only: true while a MediaPlayer/AudioTrack is actually producing sound.
     * It is deliberately NOT the "the rest timer expired" state — with the
     * {@code vibration_only} sound mode nothing ever plays, so this stays false. The old
     * code used this single flag for both meanings, which is why the "tempo scaduto"
     * notification sometimes never appeared: the expiry handler posted it, then
     * onStartCommand's "is anything still live?" check read alarm=false, concluded the
     * service had nothing to show and tore it (and the notification) down milliseconds later.
     */
    private boolean isAlarmPlaying = false;
    /** LOGICAL alarm state: the rest window expired and the user hasn't dismissed it yet. */
    private boolean isAlarmActive = false;
    /**
     * targetEndTimeMs the expiry alarm has already been delivered for. Makes delivery
     * idempotent across the three racing paths (CountDownTimer.onFinish, the exact-alarm
     * broadcast, and a cold restart that finds an elapsed deadline).
     */
    private long alarmDeliveredForTargetMs = 0L;
    private boolean isTimerRunning = false;
    private boolean isPaused = false;
    private long remainingTimeMs = 0;
    private long targetEndTimeMs = 0;
    private long totalDurationMs = 0;
    private String currentTitle = "Recupero in corso";
    private String customSoundUri = null;

    // Workout session state
    private boolean isWorkoutActive = false;
    private String workoutTitle = "Sessione di Allenamento";
    private String currentExerciseName = "";
    private int completedSets = 0;
    private int totalSets = 0;
    private int[] slotBoundaries = null;
    private long workoutStartedAt = 0;

    /** Tracks whether an ongoing promoted notification (1001 rest timer or 1003 workout progress) is actively posted. */
    public static volatile boolean hasActiveOngoingNotification = false;

    /** True between onCreate and teardown — lets MainActivity skip fg/bg pings when idle. */
    public static volatile boolean isRunning = false;

    /**
     * startId of the onStartCommand() currently being handled. Fed to
     * {@link #stopSelfResult(int)} so a teardown NEVER kills a start command the OS has
     * already accepted but not yet delivered to us.
     *
     * <p>This is the whole reason the rest timer used to die on arrival: the web calls
     * {@code stopAlarm()} and {@code startTimer()} back-to-back in a single JS turn, so
     * AMS holds both ACTION_STOP_ALARM (id N) and ACTION_START (id N+1) before the
     * service's looper has run either. ACTION_STOP_ALARM found nothing live, tore down
     * and called the unconditional {@code stopSelf()} (== {@code stopSelf(-1)}), which
     * commits the stop regardless of N+1. ACTION_START then ran normally — started the
     * countdown, posted the notification, armed the exact alarm — and milliseconds later
     * ActivityThread.handleStopService() destroyed the service anyway, taking the alarm,
     * the notification and the persisted snapshot with it. {@code stopSelfResult(N)}
     * returns false while N+1 is pending, so the service survives to serve it.
     */
    private int currentStartId = -1;

    /** When the last explicit ACTION_STOP_ALL was served (0 = never). See {@link #isStaleAfterStopAll}. */
    private long stopAllAtMs = 0L;

    /** How long "update"-class intents are ignored after an explicit teardown. */
    private static final long STOP_ALL_GRACE_MS = 2000L;

    /**
     * True for an intent that can only be a leftover of a session we were just told to
     * end: it updates or ticks an existing session rather than starting a new one, and it
     * arrived within {@link #STOP_ALL_GRACE_MS} of an ACTION_STOP_ALL.
     */
    private boolean isStaleAfterStopAll(String action) {
        if (stopAllAtMs == 0L || action == null) return false;
        if (System.currentTimeMillis() - stopAllAtMs > STOP_ALL_GRACE_MS) {
            stopAllAtMs = 0L;
            return false;
        }
        return ACTION_WORKOUT_UPDATE.equals(action)
                || ACTION_UPDATE_TIMER.equals(action)
                || ACTION_APP_FOREGROUND.equals(action)
                || ACTION_APP_BACKGROUND.equals(action);
    }

    // ---------------------------------------------------------------------------------
    // Public state mirror — read synchronously by OnyxLivePlugin.getTimerState() and
    // AndroidTimerBridge.getTimerState() so the web can resync to the real deadline
    // instead of trusting its own localStorage after a resume. Kept in lockstep with the
    // instance fields from every place that changes them (persistState() / clearPersistedState()).
    // ---------------------------------------------------------------------------------
    public static volatile boolean sTimerRunning = false;
    public static volatile boolean sPaused = false;
    public static volatile long sTargetEndTimeMs = 0L;
    public static volatile long sRemainingTimeMs = 0L;
    public static volatile String sTitle = null;
    public static volatile boolean sWorkoutActive = false;

    private void mirrorPublicState() {
        sTimerRunning = isTimerRunning;
        sPaused = isPaused;
        sTargetEndTimeMs = targetEndTimeMs;
        sRemainingTimeMs = remainingTimeMs;
        sTitle = currentTitle;
        sWorkoutActive = isWorkoutActive;
    }

    /**
     * Reports an ACTIVE PROMOTED ongoing notification: a timer/workout is live AND the app
     * is backgrounded (so the native island is what the user sees). While the app is in the
     * foreground this returns false so the web keeps showing its in-app notch instead.
     */
    public static boolean hasActiveOngoingNotification() {
        return hasActiveOngoingNotification && !IslandNotificationFactory.appInForeground;
    }

    private static volatile OnyxLiveService sInstance = null;

    public static OnyxLiveService getInstance() {
        return sInstance;
    }

    /**
     * Centralized visibility state manager.
     * Logs every transition explicitly, updates the volatile flag, and immediately
     * reconciles the ongoing notification without waiting for the periodic ticker.
     */
    public static synchronized void setAppInForeground(boolean foreground, String reason) {
        boolean previous = IslandNotificationFactory.appInForeground;
        IslandNotificationFactory.appInForeground = foreground;
        Log.i(TAG, "APP VISIBILITY TRANSITION: [" + (previous ? "FOREGROUND" : "BACKGROUND")
                + " -> " + (foreground ? "FOREGROUND" : "BACKGROUND") + "] via " + reason);

        OnyxLiveService instance = sInstance;
        if (instance != null) {
            instance.onVisibilityChanged(foreground, reason);
        }
    }

    private void onVisibilityChanged(boolean foreground, String reason) {
        tickHandler.post(() -> {
            Log.d(TAG, "onVisibilityChanged triggered: foreground=" + foreground + " reason=" + reason
                    + " (isTimerRunning=" + isTimerRunning + " isPaused=" + isPaused + " isWorkoutActive=" + isWorkoutActive + ")");
            if (isTimerRunning || isWorkoutActive || isAlarmActive) {
                updateForegroundState();
                if (isTimerRunning && !isPaused) {
                    startNotificationTicker();
                }
            }
        });
    }

    private Bitmap appIconBitmap;

    @Override
    public void onCreate() {
        super.onCreate();
        sInstance = this;
        isRunning = true;
        notificationManager = (NotificationManager) getSystemService(Context.NOTIFICATION_SERVICE);
        audioManager = (AudioManager) getSystemService(Context.AUDIO_SERVICE);
        alarmManager = (AlarmManager) getSystemService(Context.ALARM_SERVICE);

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            VibratorManager vibratorManager = (VibratorManager) getSystemService(Context.VIBRATOR_MANAGER_SERVICE);
            if (vibratorManager != null) {
                vibrator = vibratorManager.getDefaultVibrator();
            }
        } else {
            vibrator = (Vibrator) getSystemService(Context.VIBRATOR_SERVICE);
        }

        try {
            appIconBitmap = BitmapFactory.decodeResource(getResources(), R.mipmap.ic_launcher);
        } catch (Exception e) {
            Log.e(TAG, "Error loading app icon bitmap: " + e.getMessage());
        }

        IslandNotificationFactory.createNotificationChannels(notificationManager);
        // An upgrade over a live session can leave 1000/1002/1003 on screen forever —
        // nothing posts them any more, so nothing would ever cancel them either.
        IslandNotificationFactory.cancelLegacyNotifications(notificationManager);
    }

    /**
     * The user swiped the app away from recents. Nothing on the JS side runs at this
     * point (the WebView is gone), so the decision has to be made here.
     *
     * <p>If no rest timer is counting and no alarm is ringing, there is nothing this
     * process needs to stay alive for — including the case of a workout that is still
     * flagged "active" but that the user has just dismissed. We tear everything down
     * (notification, exact alarm, wakelock, persisted snapshot) and stop the service, so
     * the process actually goes away instead of lingering and being restarted forever by
     * the sticky-service contract. That lingering process, still holding a wakelock and
     * still ticking its notification, is the "app won't close / phone gets hot" report.
     *
     * <p>A live rest countdown is the one exception: it is short, bounded and the whole
     * point of the feature is that it survives the app being swiped away.
     */
    @Override
    public void onTaskRemoved(Intent rootIntent) {
        super.onTaskRemoved(rootIntent);
        Log.i(TAG, "onTaskRemoved: app swiped away from recents (timer=" + isTimerRunning
                + " paused=" + isPaused + " workout=" + isWorkoutActive + " alarm=" + isAlarmActive + ")");
        setAppInForeground(false, "Service.onTaskRemoved");

        boolean liveCountdown = isTimerRunning && !isPaused;
        if (!isWorkoutActive && !liveCountdown && !isAlarmActive) {
            Log.i(TAG, "onTaskRemoved: no workout, no countdown, no alarm -> full teardown");
            stopAllAndService(true);
            return;
        }
        // Something legitimate is still running, so the foreground service stays. Make
        // sure it stays cheap: no wakelock unless a countdown is actually counting, and
        // no notification ticker for a workout (its notification is event-driven).
        if (!liveCountdown && !isAlarmActive) {
            stopNotificationTicker();
            releaseWakeLock();
        }
        persistState();
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        boolean redelivered = (flags & START_FLAG_REDELIVERY) != 0;
        String action = intent != null ? intent.getAction() : null;
        // A teardown that lost the stopSelfResult() race leaves isRunning=false on a
        // service that is very much still alive — re-assert it on every entry.
        currentStartId = startId;
        isRunning = true;
        Log.d(TAG, "DIAG onStartCommand enter: action=" + action + " redelivered=" + redelivered
                + " flags(before)=[timer=" + isTimerRunning + " paused=" + isPaused
                + " workout=" + isWorkoutActive + " alarm=" + isAlarmActive + "]");

        // ACTION_STOP_ALL is the one action allowed to conclude "nothing is here"
        // without ever consulting in-memory or persisted state — it bypasses restore
        // entirely (there is nothing to legitimately resurrect on the way to killing
        // it) and never falls through to the generic handling below.
        if (ACTION_STOP_ALL.equals(action)) {
            Log.d(TAG, "OnyxLiveService onStartCommand: ACTION_STOP_ALL (unconditional teardown)");
            // Satisfy the startForeground() obligation first: this may have been
            // launched via startForegroundService() with nothing actually live.
            postAsForegroundAnchor(NOTIFICATION_ID_ANCHOR, IslandNotificationFactory.buildMinimalAnchor(this));
            stopAllAtMs = System.currentTimeMillis();
            stopAllAndService(true);
            return START_NOT_STICKY;
        }

        // The web fires workout progress updates constantly, so when the user hits
        // "termina allenamento" the OS usually still has one or two ACTION_WORKOUT_UPDATE
        // intents queued behind the ACTION_STOP_ALL. Serving them would re-set
        // isWorkoutActive=true and re-post the notification we just removed — the exact
        // "zombie notification" the user sees. Anything that merely UPDATES an existing
        // session is dropped for a moment after an explicit teardown; a genuinely new
        // session (ACTION_WORKOUT_START / ACTION_START) is never blocked.
        if (isStaleAfterStopAll(action)) {
            Log.i(TAG, "OnyxLiveService onStartCommand: dropping stale " + action
                    + " queued behind ACTION_STOP_ALL");
            postAsForegroundAnchor(NOTIFICATION_ID_ANCHOR, IslandNotificationFactory.buildMinimalAnchor(this));
            stopAllAndService(true);
            return START_NOT_STICKY;
        }

        // A cold-recreated service (process killed by the OS, e.g. after the app is
        // swiped away on HyperOS) has every state field at its Java default. Restore the
        // persisted snapshot BEFORE ensureForegroundAnchor() picks what to post: doing the
        // restore AFTER (the old order) meant the very first startForeground() frame of
        // this service's lifecycle was always the silent, colorless buildMinimalAnchor(),
        // with the real (colorized/promoted) notification following a few ms later in the
        // same onStartCommand(). HyperOS's Super Island latches onto that first frame and
        // never picks up the same-cycle switch to a different notification id, leaving a
        // permanent empty black pill instead of the lime "TEMPO SCADUTO" card.
        //
        // Restored unconditionally on EVERY cold entry (not just redelivered/null/backup
        // actions): a notification button tap (Pausa/+30s/Stop/DISATTIVA ALLARME) on a
        // stale notification left on screen after an OEM kill also cold-starts the
        // service with an arbitrary action and default fields. Gating the restore on the
        // action string meant that tap concluded "nothing is running" out of ignorance
        // (state was simply never loaded) and then destroyed the real backup alarm and
        // persisted snapshot as a side effect — the two things that were supposed to
        // save the timer. A "fresh" action (ACTION_START / ACTION_WORKOUT_START)
        // immediately overwrites every restored field anyway, so restoring first is
        // always safe. Any teardown decision made further down now happens only after
        // this honest attempt to find out what's really there.
        if (!isTimerRunning && !isWorkoutActive && !isAlarmActive) {
            restoreStateFromPrefs();
        }

        // Satisfy the startForeground() obligation IMMEDIATELY, before any work or early
        // return. A cold-recreated service handed a notification action (PAUSE / RESUME /
        // +30s / STOP_ALARM) has all state fields at defaults, so the action handlers below
        // may early-return without ever calling startForeground() -> the OS would kill us
        // with ForegroundServiceDidNotStartInTimeException.
        ensureForegroundAnchor();

        if (redelivered || action == null) {
            // The OS restarted us after a low-memory / OEM kill: START_REDELIVER_INTENT
            // re-delivers the last intent (redelivered=true), a plain sticky restart
            // delivers null. Either way the carried action is stale — rebuild from the
            // persisted snapshot instead of replaying it.
            Log.d(TAG, "OnyxLiveService onStartCommand: restart (redelivered=" + redelivered + ", action=" + action + ")");
            // State was already restored above (before ensureForegroundAnchor); resume
            // timers / notifications from it now. A no-op if nothing was persisted.
            resumeFromRestoredState();
            if (!isTimerRunning && !isWorkoutActive && !isAlarmActive) {
                stopAllAndService();
                return START_NOT_STICKY;
            }
            return restartPolicy();
        }

        Log.d(TAG, "OnyxLiveService onStartCommand: action=" + action);

        // App foreground/background transitions only re-render existing notifications
        // (promote when bg, demote when fg). They never start or stop the service.
        if (ACTION_APP_FOREGROUND.equals(action) || ACTION_APP_BACKGROUND.equals(action)) {
            setAppInForeground(ACTION_APP_FOREGROUND.equals(action), "Intent." + action);
            if (!isTimerRunning && !isWorkoutActive && !isAlarmActive) {
                stopAllAndService();
                return START_NOT_STICKY;
            }
            return restartPolicy();
        }

        try {
            handleAction(action, intent);
        } catch (Exception e) {
            Log.e(TAG, "onStartCommand handler crashed for action " + action + ": " + e.getMessage(), e);
        }

        // If the action left nothing live to display, drop the (possibly minimal) anchor.
        if (!isTimerRunning && !isWorkoutActive && !isAlarmActive) {
            stopAllAndService();
            return START_NOT_STICKY;
        }

        // Something is live -> see restartPolicy(). The redelivered intent is ignored on
        // the way back in; state comes from prefs.
        return restartPolicy();
    }

    /**
     * Restart policy.
     *
     * <p>Only a live (or ringing) rest countdown is worth resurrecting: it is short,
     * time-critical, and the persisted snapshot lets a restarted service rebuild it
     * exactly. A workout session is NOT — it can last an hour, and asking the OS to
     * restart us for it means the process comes back again and again after every kill and
     * after the user swipes the app away, which is what kept the app "alive forever" and
     * draining the battery. For that case we return START_NOT_STICKY and let the process
     * die for good; the web re-arms the island the next time the user opens the session.
     */
    private int restartPolicy() {
        boolean timeCritical = (isTimerRunning && !isPaused) || isAlarmActive;
        return timeCritical ? START_REDELIVER_INTENT : START_NOT_STICKY;
    }

    /**
     * Re-arms timers / notifications from fields just populated by
     * {@link #restoreStateFromPrefs()} after an OS kill.
     */
    private synchronized void resumeFromRestoredState() {
        try {
            if (isTimerRunning && !isPaused) {
                long left = targetEndTimeMs - System.currentTimeMillis();
                if (left <= 0) {
                    // The rest window elapsed while the service was dead.
                    remainingTimeMs = 0;
                    isTimerRunning = false;
                    triggerTimerFinishedAlarm();
                    return;
                }
                remainingTimeMs = left;
                acquireTimerWakeLock(remainingTimeMs);
                updateForegroundState();
                startInternalCountDown(remainingTimeMs);
            } else if (isTimerRunning) { // paused — nothing is counting, so no wakelock
                updateForegroundState();
            }
            if (isAlarmActive || isWorkoutActive) {
                updateForegroundState();
            }
        } catch (Exception e) {
            Log.e(TAG, "resumeFromRestoredState failed: " + e.getMessage(), e);
        }
    }

    private void ensureForegroundAnchor() {
        try {
            Log.d(TAG, "DIAG ensureForegroundAnchor enter: timer=" + isTimerRunning + " paused=" + isPaused
                    + " workout=" + isWorkoutActive + " alarm=" + isAlarmActive);
            if (isTimerRunning && !isPaused && targetEndTimeMs > 0
                    && targetEndTimeMs <= System.currentTimeMillis()) {
                // Restored state shows the rest window already elapsed while the service
                // was dead (cold start via ACTION_ALARM_BACKUP or a plain OEM-kill
                // restart). Skip straight to the alarm-fired state so the very FIRST
                // startForeground() call of this lifecycle already posts the real
                // colorized/promoted "TEMPO SCADUTO" notification instead of a stale
                // countdown card or the silent minimal anchor.
                isTimerRunning = false;
                triggerTimerFinishedAlarm();
            } else if (isTimerRunning || isWorkoutActive || isAlarmActive) {
                updateForegroundState();
            } else {
                postAsForegroundAnchor(NOTIFICATION_ID_ANCHOR, IslandNotificationFactory.buildMinimalAnchor(this));
            }
        } catch (Exception e) {
            Log.e(TAG, "ensureForegroundAnchor failed: " + e.getMessage(), e);
        }
    }

    void handleAction(String action, Intent intent) {
        switch (action) {
            case ACTION_START: {
                int durationSeconds = intent.getIntExtra(EXTRA_DURATION, 45);
                String title = intent.getStringExtra(EXTRA_TITLE);
                String soundUri = intent.getStringExtra(EXTRA_SOUND_URI);
                if (title == null || title.isEmpty()) {
                    title = "Recupero in corso";
                }
                this.customSoundUri = soundUri;
                startTimerCountdown(durationSeconds, title);
                break;
            }
            case ACTION_PAUSE:
                pauseTimer();
                break;
            case ACTION_RESUME:
                resumeTimer();
                break;
            case ACTION_ADD_TIME:
                addSecondsToTimer(intent.getIntExtra(EXTRA_DURATION, 30));
                break;
            case ACTION_UPDATE_TIMER: {
                int durationSeconds = intent.getIntExtra(EXTRA_DURATION, 45);
                int remainingSeconds = intent.getIntExtra(EXTRA_REMAINING_SECONDS, durationSeconds);
                updateTimerDuration(durationSeconds, remainingSeconds);
                break;
            }
            case ACTION_STOP:
                stopRestTimer();
                break;
            case ACTION_ALARM_BACKUP: {
                // Exact-alarm backup fired (see TimerExpiryAlarmReceiver). onStartCommand
                // already restored from prefs on this cold entry if fields were at
                // defaults; this is just a defensive no-op re-check.
                if (!isTimerRunning && !isAlarmActive && !isWorkoutActive) {
                    restoreStateFromPrefs();
                }
                long msLeft = targetEndTimeMs - System.currentTimeMillis();
                if (isTimerRunning && !isPaused && msLeft <= 1000L) {
                    Log.d(TAG, "ACTION_ALARM_BACKUP: forcing timer-finished alarm (msLeft=" + msLeft + ")");
                    if (countDownTimer != null) {
                        countDownTimer.cancel();
                        countDownTimer = null;
                    }
                    isTimerRunning = false;
                    triggerTimerFinishedAlarm();
                } else {
                    Log.d(TAG, "ACTION_ALARM_BACKUP: ignored (running=" + isTimerRunning
                            + ", paused=" + isPaused + ", msLeft=" + msLeft + ")");
                }
                break;
            }
            case ACTION_STOP_ALARM:
                stopAlarmOnly();
                if (!isTimerRunning && !isWorkoutActive) {
                    stopAllAndService();
                } else {
                    updateForegroundState();
                }
                break;
            case ACTION_WORKOUT_START: {
                String title = intent.getStringExtra(EXTRA_TITLE);
                this.workoutTitle = (title != null && !title.isEmpty()) ? title : "Sessione di Allenamento";
                this.totalSets = intent.getIntExtra(EXTRA_TOTAL_SETS, 0);
                this.completedSets = intent.getIntExtra(EXTRA_COMPLETED_SETS, 0);
                this.currentExerciseName = intent.getStringExtra(EXTRA_CURRENT_EXERCISE);
                this.workoutStartedAt = intent.getLongExtra(EXTRA_STARTED_AT, System.currentTimeMillis());
                this.slotBoundaries = intent.getIntArrayExtra(EXTRA_SLOT_BOUNDARIES);
                this.isWorkoutActive = true;
                // Deliberately NO wakelock: a workout runs for an hour and the foreground
                // service alone keeps the process alive. A PARTIAL_WAKE_LOCK held for that
                // long is exactly the battery drain / heat this was reported for. Only the
                // rest countdown (seconds to minutes) takes one.
                updateForegroundState();
                break;
            }
            case ACTION_WORKOUT_UPDATE: {
                this.totalSets = intent.getIntExtra(EXTRA_TOTAL_SETS, this.totalSets);
                this.completedSets = intent.getIntExtra(EXTRA_COMPLETED_SETS, this.completedSets);
                String exercise = intent.getStringExtra(EXTRA_CURRENT_EXERCISE);
                if (exercise != null) {
                    this.currentExerciseName = exercise;
                }
                this.isWorkoutActive = true;
                updateForegroundState();
                break;
            }
            case ACTION_WORKOUT_STOP: {
                this.isWorkoutActive = false;
                this.workoutStartedAt = 0L;
                this.completedSets = 0;
                this.totalSets = 0;
                this.currentExerciseName = "";
                if (!isTimerRunning && !isAlarmActive) {
                    stopAllAndService();
                } else {
                    updateForegroundState();
                }
                break;
            }
        }
    }

    private synchronized void startTimerCountdown(int durationSeconds, String title) {
        Log.d(TAG, "OnyxLiveService: Starting/Updating countdown for " + durationSeconds + "s (" + title + ")");
        
        stopAlarmOnly();

        if (countDownTimer != null) {
            countDownTimer.cancel();
            countDownTimer = null;
        }

        this.currentTitle = title;
        this.totalDurationMs = durationSeconds * 1000L;
        this.remainingTimeMs = totalDurationMs;
        this.targetEndTimeMs = System.currentTimeMillis() + remainingTimeMs;
        this.isTimerRunning = true;
        this.isPaused = false;
        this.alarmDeliveredForTargetMs = 0L;

        acquireTimerWakeLock(remainingTimeMs);
        updateForegroundState();

        startInternalCountDown(remainingTimeMs);
    }

    private synchronized void pauseTimer() {
        if (!isTimerRunning || isPaused) return;
        if (countDownTimer != null) {
            countDownTimer.cancel();
            countDownTimer = null;
        }
        remainingTimeMs = Math.max(0, targetEndTimeMs - System.currentTimeMillis());
        isPaused = true;
        cancelExpiryAlarm();
        stopNotificationTicker();
        releaseWakeLock();
        updateForegroundState();
        OnyxLivePlugin.notifyTimerPaused();
    }

    private synchronized void resumeTimer() {
        if (!isTimerRunning || !isPaused) return;
        targetEndTimeMs = System.currentTimeMillis() + remainingTimeMs;
        isPaused = false;
        alarmDeliveredForTargetMs = 0L;
        acquireTimerWakeLock(remainingTimeMs);
        updateForegroundState();
        startInternalCountDown(remainingTimeMs);
        OnyxLivePlugin.notifyTimerResumed();
    }

    private synchronized void addSecondsToTimer(int extraSeconds) {
        if (!isTimerRunning) return;
        long currentLeft = isPaused ? remainingTimeMs : Math.max(0, targetEndTimeMs - System.currentTimeMillis());
        long newRemainingMs = currentLeft + (extraSeconds * 1000L);
        totalDurationMs += (extraSeconds * 1000L);
        updateTimerDuration((int) (totalDurationMs / 1000L), (int) (newRemainingMs / 1000L));
    }

    private synchronized void updateTimerDuration(int durationSeconds, int remainingSeconds) {
        Log.d(TAG, "OnyxLiveService: Updating timer to duration=" + durationSeconds + "s, remaining=" + remainingSeconds + "s");
        if (countDownTimer != null) {
            countDownTimer.cancel();
            countDownTimer = null;
        }

        stopAlarmOnly();

        this.totalDurationMs = Math.max(1, durationSeconds) * 1000L;
        this.remainingTimeMs = Math.max(0, remainingSeconds * 1000L);
        this.targetEndTimeMs = System.currentTimeMillis() + remainingTimeMs;
        this.isTimerRunning = remainingTimeMs > 0;
        this.isPaused = false;
        this.alarmDeliveredForTargetMs = 0L;

        acquireTimerWakeLock(remainingTimeMs);
        updateForegroundState();

        if (isTimerRunning) {
            startInternalCountDown(remainingTimeMs);
        } else {
            stopRestTimer();
        }
    }

    private synchronized void stopRestTimer() {
        Log.d(TAG, "OnyxLiveService: Stopping rest countdown");
        if (countDownTimer != null) {
            countDownTimer.cancel();
            countDownTimer = null;
        }
        isTimerRunning = false;
        isPaused = false;
        remainingTimeMs = 0;
        cancelExpiryAlarm();
        stopAlarmOnly();
        stopNotificationTicker();
        releaseWakeLock();

        if (!isWorkoutActive) {
            stopAllAndService();
        } else {
            updateForegroundState();
        }
        OnyxLivePlugin.notifyTimerStopped();
    }

    private void startInternalCountDown(long durationMs) {
        // Belt-and-braces: also arm an exact AlarmManager alarm for the same target time
        // so the "time's up" alarm still fires if this CountDownTimer is frozen/killed.
        scheduleExpiryAlarm();
        startNotificationTicker();
        countDownTimer = new CountDownTimer(durationMs, 500) {
            @Override
            public void onTick(long millisUntilFinished) {
                remainingTimeMs = Math.max(0, millisUntilFinished);
            }

            @Override
            public void onFinish() {
                Log.d(TAG, "OnyxLiveService: CountDown finished! Triggering alarm.");
                remainingTimeMs = 0;
                triggerTimerFinishedAlarm();
            }
        }.start();
    }

    /**
     * Renders THE single live notification.
     *
     * <p>One id, one channel, content chosen by state priority:
     * alarm ringing &gt; rest timer running &gt; workout in progress. Workout context
     * (sets / exercise) is folded into the timer and alarm renderings. The previous
     * version posted the workout notification as the foreground anchor and then
     * {@code notify()}'d the timer or alarm on a second id, which is how the user could
     * end up looking at three Onyx notifications at once (plus the throwaway 1000 anchor
     * whenever a cold start lost the race to cancel it).
     */
    private synchronized void updateForegroundState() {
        if (notificationManager == null) return;
        Log.d(TAG, "DIAG updateForegroundState enter: timer=" + isTimerRunning + " paused=" + isPaused
                + " workout=" + isWorkoutActive + " alarm=" + isAlarmActive);

        hasActiveOngoingNotification = isWorkoutActive || isTimerRunning || isAlarmActive;
        if (isTimerRunning && !isPaused && targetEndTimeMs > 0) {
            remainingTimeMs = Math.max(0L, targetEndTimeMs - System.currentTimeMillis());
        }

        try {
            if (!isWorkoutActive && !isTimerRunning && !isAlarmActive) {
                // Nothing to show. Post the minimal anchor on the SAME id (the caller is
                // about to tear the service down) rather than leaving a stale render up.
                postAsForegroundAnchor(NOTIFICATION_ID_ANCHOR, IslandNotificationFactory.buildMinimalAnchor(this));
                return;
            }
            postAsForegroundAnchor(IslandNotificationFactory.NOTIFICATION_ID_LIVE,
                    IslandNotificationFactory.buildLive(this, snapshotLiveState()));
        } catch (Exception e) {
            Log.e(TAG, "Error updating the live notification: " + e.getMessage(), e);
        }

        // Mirror the live state so a killed/redelivered service can rebuild it.
        persistState();
    }

    /** Packs the current fields into the render input for {@link IslandNotificationFactory}. */
    private IslandNotificationFactory.LiveState snapshotLiveState() {
        IslandNotificationFactory.LiveState s = new IslandNotificationFactory.LiveState();
        s.alarmActive = isAlarmActive;
        s.timerRunning = isTimerRunning;
        s.timerPaused = isPaused;
        s.targetEndTimeMs = targetEndTimeMs;
        s.remainingMs = remainingTimeMs;
        s.totalDurationMs = totalDurationMs;
        s.timerTitle = currentTitle;
        s.workoutActive = isWorkoutActive;
        s.workoutTitle = workoutTitle;
        s.exerciseName = currentExerciseName;
        s.completedSets = completedSets;
        s.totalSets = totalSets;
        s.workoutStartedAt = workoutStartedAt;
        s.appIcon = appIconBitmap;
        return s;
    }

    private void postAsForegroundAnchor(int id, Notification notification) {
        try {
            if (Build.VERSION.SDK_INT >= 34) {
                startForeground(id, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE);
            } else if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                startForeground(id, notification, 0);
            } else {
                startForeground(id, notification);
            }
            if (notificationManager != null) {
                notificationManager.notify(id, notification);
                IslandNotificationFactory.cancelLegacyNotifications(notificationManager);
            }
        } catch (Exception e) {
            Log.e(TAG, "Error posting foreground anchor notification (" + id + "): " + e.getMessage(), e);
        }
    }

    /**
     * Delivers the "rest is over" alarm exactly once per deadline.
     *
     * <p>Three paths race to call this — {@code CountDownTimer.onFinish()}, the exact
     * AlarmManager broadcast, and a cold restart that finds an already-elapsed deadline —
     * and on HyperOS two of them routinely fire for the same timer. Idempotency is keyed
     * on {@link #targetEndTimeMs} rather than on "is something currently ringing", because
     * the {@code vibration_only} sound mode never sets the audio flag at all.
     */
    private synchronized void triggerTimerFinishedAlarm() {
        long deadline = targetEndTimeMs;
        if (isAlarmActive && deadline != 0 && deadline == alarmDeliveredForTargetMs) {
            Log.d(TAG, "triggerTimerFinishedAlarm: already delivered for target=" + deadline + " (idempotent no-op)");
            // Still re-render: a duplicate delivery is also our chance to repair a
            // notification an OEM kill may have dropped. Same id, so it replaces.
            updateForegroundState();
            return;
        }

        if (countDownTimer != null) {
            countDownTimer.cancel();
            countDownTimer = null;
        }
        cancelExpiryAlarm();
        stopNotificationTicker();
        isTimerRunning = false;
        isPaused = false;
        isAlarmActive = true;
        alarmDeliveredForTargetMs = deadline;
        hasActiveOngoingNotification = true;

        // The ring is short and bounded — this is the one place a wakelock is justified.
        acquireTimerWakeLock(ALARM_WAKELOCK_MS);

        requestExclusiveAudioFocus();
        playLoopingAlarmSound();
        startAlarmVibration();

        // ONE notification, same id as the countdown it replaces.
        updateForegroundState();

        // Keep the persisted snapshot in sync with the just-flipped isTimerRunning=false:
        // without this, a process death right after the alarm starts ringing would leave
        // a stale "timer still running, deadline in the past" snapshot on disk, which is
        // harmless (the next cold start just re-fires the alarm) but noisy to debug.
        persistState();

        OnyxLivePlugin.notifyTimerExpired();
    }

    private void requestExclusiveAudioFocus() {
        if (audioManager == null) return;
        try {
            AudioAttributes playbackAttributes = new AudioAttributes.Builder()
                    .setUsage(AudioAttributes.USAGE_ALARM)
                    .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
                    .build();

            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                audioFocusRequest = new AudioFocusRequest.Builder(AudioManager.AUDIOFOCUS_GAIN_TRANSIENT_EXCLUSIVE)
                        .setAudioAttributes(playbackAttributes)
                        .setAcceptsDelayedFocusGain(false)
                        .setOnAudioFocusChangeListener(focusChange -> {})
                        .build();
                audioManager.requestAudioFocus(audioFocusRequest);
            } else {
                audioManager.requestAudioFocus(null, AudioManager.STREAM_ALARM, AudioManager.AUDIOFOCUS_GAIN_TRANSIENT_EXCLUSIVE);
            }
        } catch (Exception e) {
            Log.e(TAG, "Error requesting audio focus: " + e.getMessage(), e);
        }
    }

    private void releaseAudioFocus() {
        if (audioManager == null) return;
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O && audioFocusRequest != null) {
                audioManager.abandonAudioFocusRequest(audioFocusRequest);
                audioFocusRequest = null;
            } else {
                audioManager.abandonAudioFocus(null);
            }
        } catch (Exception e) {
            Log.e(TAG, "Error releasing audio focus: " + e.getMessage(), e);
        }
    }

    private void playLoopingAlarmSound() {
        try {
            stopAlarmSound();

            if ("vibration_only".equalsIgnoreCase(customSoundUri)) {
                Log.d(TAG, "Sound mode: vibration_only");
                return;
            }

            isAlarmPlaying = true;

            if ("gong".equalsIgnoreCase(customSoundUri) ||
                "boxing".equalsIgnoreCase(customSoundUri) ||
                "whistle".equalsIgnoreCase(customSoundUri) ||
                "beep".equalsIgnoreCase(customSoundUri)) {
                playSynthesizedTone(customSoundUri);
                return;
            }

            boolean wantsSystemAlarm = "system_alarm".equalsIgnoreCase(customSoundUri);
            Uri alertUri = null;
            if (customSoundUri != null && !customSoundUri.isEmpty() && !wantsSystemAlarm) {
                try {
                    alertUri = Uri.parse(customSoundUri);
                } catch (Exception e) {
                    Log.w(TAG, "Invalid custom sound URI: " + customSoundUri);
                }
            }

            // Default (no explicit soundUri, or the caller asked for "system_alarm" and
            // we still try our own track first): the bundled Onyx alarm — an original,
            // in-house EDM-style riser/stab loop (no third-party rights involved), 3.75s
            // exact-bar loop with encoder-padding-free OGG so setLooping() doesn't click.
            if (alertUri == null && !wantsSystemAlarm) {
                try {
                    if (playRawAlarmResource()) return;
                } catch (Exception e) {
                    Log.w(TAG, "Bundled onyx_alarm resource unavailable, falling back: " + e.getMessage());
                }
            }

            if (alertUri == null) {
                alertUri = RingtoneManager.getDefaultUri(RingtoneManager.TYPE_ALARM);
            }
            if (alertUri == null) {
                alertUri = RingtoneManager.getDefaultUri(RingtoneManager.TYPE_RINGTONE);
            }
            if (alertUri == null) {
                alertUri = RingtoneManager.getDefaultUri(RingtoneManager.TYPE_NOTIFICATION);
            }

            mediaPlayer = new MediaPlayer();
            mediaPlayer.setDataSource(this, alertUri);
            mediaPlayer.setAudioAttributes(new AudioAttributes.Builder()
                    .setUsage(AudioAttributes.USAGE_ALARM)
                    .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
                    .build());
            mediaPlayer.setLooping(true);
            mediaPlayer.prepare();
            mediaPlayer.start();
        } catch (Exception e) {
            Log.e(TAG, "Error playing alarm sound: " + e.getMessage(), e);
            try {
                isAlarmPlaying = true;
                playSynthesizedTone("beep");
            } catch (Exception ignored) {}
        }
    }

    /** @return true if the bundled onyx_alarm.ogg raw resource started playing. */
    private boolean playRawAlarmResource() {
        try {
            AudioAttributes attrs = new AudioAttributes.Builder()
                    .setUsage(AudioAttributes.USAGE_ALARM)
                    .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
                    .build();
            MediaPlayer player = MediaPlayer.create(this, R.raw.onyx_alarm, attrs, 0);
            if (player == null) return false;
            player.setLooping(true);
            mediaPlayer = player;
            mediaPlayer.start();
            return true;
        } catch (Exception e) {
            Log.w(TAG, "playRawAlarmResource failed: " + e.getMessage());
            if (mediaPlayer != null) {
                try { mediaPlayer.release(); } catch (Exception ignored) {}
                mediaPlayer = null;
            }
            return false;
        }
    }

    private void playSynthesizedTone(String soundType) {
        new Thread(() -> {
            try {
                int sampleRate = 44100;
                int numSamples;
                double[] sample;

                if ("boxing".equalsIgnoreCase(soundType)) {
                    double duration = 1.2;
                    numSamples = (int) (duration * sampleRate);
                    sample = new double[numSamples];
                    for (int i = 0; i < numSamples; ++i) {
                        double t = (double) i / sampleRate;
                        double bell1 = Math.exp(-6.0 * t) * Math.sin(2 * Math.PI * 880 * t);
                        double bell2 = (t > 0.28) ? Math.exp(-6.0 * (t - 0.28)) * Math.sin(2 * Math.PI * 880 * (t - 0.28)) : 0;
                        sample[i] = bell1 + bell2;
                    }
                } else if ("gong".equalsIgnoreCase(soundType)) {
                    double duration = 2.0;
                    numSamples = (int) (duration * sampleRate);
                    sample = new double[numSamples];
                    for (int i = 0; i < numSamples; ++i) {
                        double t = (double) i / sampleRate;
                        double f1 = Math.sin(2 * Math.PI * 180 * t);
                        double f2 = 0.5 * Math.sin(2 * Math.PI * 360 * t);
                        double f3 = 0.25 * Math.sin(2 * Math.PI * 540 * t);
                        sample[i] = Math.exp(-2.0 * t) * (f1 + f2 + f3);
                    }
                } else if ("whistle".equalsIgnoreCase(soundType)) {
                    double duration = 1.0;
                    numSamples = (int) (duration * sampleRate);
                    sample = new double[numSamples];
                    for (int i = 0; i < numSamples; ++i) {
                        double t = (double) i / sampleRate;
                        double mod = Math.sin(2 * Math.PI * 25 * t);
                        sample[i] = Math.exp(-1.2 * t) * Math.sin(2 * Math.PI * (2300 + 180 * mod) * t);
                    }
                } else {
                    double duration = 0.8;
                    numSamples = (int) (duration * sampleRate);
                    sample = new double[numSamples];
                    for (int i = 0; i < numSamples; ++i) {
                        double t = (double) i / sampleRate;
                        boolean on = (t < 0.15) || (t > 0.22 && t < 0.37) || (t > 0.44 && t < 0.59);
                        sample[i] = on ? Math.sin(2 * Math.PI * 1200 * t) : 0;
                    }
                }

                byte[] generatedSnd = new byte[2 * numSamples];
                int idx = 0;
                for (final double dVal : sample) {
                    final short val = (short) (dVal * 32767);
                    generatedSnd[idx++] = (byte) (val & 0x00ff);
                    generatedSnd[idx++] = (byte) ((val & 0xff00) >>> 8);
                }

                if (!isAlarmPlaying) {
                    return;
                }

                synchronized (audioLock) {
                    if (!isAlarmPlaying) {
                        return;
                    }
                    stopSynthesizedAudioTrack();
                    synthesizedAudioTrack = new AudioTrack.Builder()
                            .setAudioAttributes(new AudioAttributes.Builder()
                                    .setUsage(AudioAttributes.USAGE_ALARM)
                                    .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
                                    .build())
                            .setAudioFormat(new AudioFormat.Builder()
                                    .setEncoding(AudioFormat.ENCODING_PCM_16BIT)
                                    .setSampleRate(sampleRate)
                                    .setChannelMask(AudioFormat.CHANNEL_OUT_MONO)
                                    .build())
                            .setBufferSizeInBytes(generatedSnd.length)
                            .setTransferMode(AudioTrack.MODE_STATIC)
                            .build();

                    synthesizedAudioTrack.write(generatedSnd, 0, generatedSnd.length);
                    if (isAlarmPlaying && synthesizedAudioTrack != null
                            && synthesizedAudioTrack.getState() == AudioTrack.STATE_INITIALIZED) {
                        synthesizedAudioTrack.play();
                    }
                }
            } catch (Exception e) {
                Log.e(TAG, "Error playing synthesized tone: " + e.getMessage(), e);
            }
        }).start();
    }

    private void stopSynthesizedAudioTrack() {
        synchronized (audioLock) {
            if (synthesizedAudioTrack != null) {
                try {
                    synthesizedAudioTrack.pause();
                    synthesizedAudioTrack.flush();
                    synthesizedAudioTrack.stop();
                } catch (Exception ignored) {}
                try {
                    synthesizedAudioTrack.release();
                } catch (Exception ignored) {}
                synthesizedAudioTrack = null;
            }
        }
    }

    private void stopAlarmSound() {
        isAlarmPlaying = false;
        stopSynthesizedAudioTrack();
        if (mediaPlayer != null) {
            try {
                mediaPlayer.stop();
            } catch (Exception ignored) {}
            try {
                mediaPlayer.reset();
            } catch (Exception ignored) {}
            try {
                mediaPlayer.release();
            } catch (Exception ignored) {}
            mediaPlayer = null;
        }
    }

    private void startAlarmVibration() {
        if (vibrator == null || !vibrator.hasVibrator()) return;
        try {
            long[] timings = {0, 400, 200, 400, 200, 800};
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                vibrator.vibrate(VibrationEffect.createWaveform(timings, 0));
            } else {
                vibrator.vibrate(timings, 0);
            }
        } catch (Exception e) {
            Log.e(TAG, "Error starting vibration: " + e.getMessage(), e);
        }
    }

    private void stopAlarmVibration() {
        if (vibrator != null) {
            try {
                vibrator.cancel();
            } catch (Exception e) {
                Log.e(TAG, "Error canceling vibration: " + e.getMessage(), e);
            }
        }
    }

    private void stopAlarmOnly() {
        isAlarmActive = false;
        alarmDeliveredForTargetMs = 0L;
        stopAlarmSound();
        stopAlarmVibration();
        releaseAudioFocus();
        releaseWakeLock();
    }

    private synchronized void stopAllAndService() {
        stopAllAndService(false);
    }

    /**
     * @param force when true the service stops even if the OS still has a start command
     *              queued for us ({@code stopSelf()} instead of {@code stopSelfResult()}).
     *              Used by the explicit end-of-workout paths (ACTION_STOP_ALL,
     *              onTaskRemoved), where the caller is asserting "nothing should survive
     *              this" and a queued stale ACTION_WORKOUT_UPDATE must not resurrect the
     *              notification. The soft variant is kept for the implicit "nothing left
     *              to show" teardowns, where a pending ACTION_START legitimately wins.
     */
    private synchronized void stopAllAndService(boolean force) {
        Log.w(TAG, "DIAG stopAllAndService enter (force=" + force + " timer=" + isTimerRunning
                + " paused=" + isPaused
                + " workout=" + isWorkoutActive + " alarm=" + isAlarmActive + ")",
                new Throwable("DIAG call site"));
        hasActiveOngoingNotification = false;
        isRunning = false;
        isTimerRunning = false;
        isPaused = false;
        isWorkoutActive = false;
        isAlarmActive = false;
        alarmDeliveredForTargetMs = 0L;
        workoutStartedAt = 0L;
        remainingTimeMs = 0L;
        targetEndTimeMs = 0L;

        if (countDownTimer != null) {
            countDownTimer.cancel();
            countDownTimer = null;
        }
        stopNotificationTicker();
        cancelExpiryAlarm();
        clearPersistedState();
        stopAlarmOnly();
        releaseWakeLock();

        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.N) {
                stopForeground(STOP_FOREGROUND_REMOVE);
            } else {
                stopForeground(true);
            }
        } catch (Exception e) {
            Log.e(TAG, "Error in stopForeground: " + e.getMessage(), e);
        }

        if (notificationManager != null) {
            try {
                notificationManager.cancel(IslandNotificationFactory.NOTIFICATION_ID_LIVE);
            } catch (Exception ignored) {}
            // Anything an older build of the app may still have on screen.
            IslandNotificationFactory.cancelLegacyNotifications(notificationManager);
        }
        if (force) {
            stopSelf();
            return;
        }
        // Only stop if no newer start command is already queued for us. stopSelf() would
        // commit the stop unconditionally and destroy whatever that queued command is
        // about to set up (see currentStartId).
        boolean stopped = stopSelfResult(currentStartId);
        if (!stopped) {
            Log.d(TAG, "stopAllAndService: stop deferred — a newer start command is pending"
                    + " (startId=" + currentStartId + ")");
        }
    }

    // ---------------------------------------------------------------------------------
    // Exact-alarm backup for timer expiry
    // ---------------------------------------------------------------------------------

    private PendingIntent expiryAlarmPendingIntent() {
        Intent i = new Intent(this, TimerExpiryAlarmReceiver.class);
        i.setAction(ACTION_ALARM_BACKUP);
        return PendingIntent.getBroadcast(this, REQ_EXPIRY_ALARM, i,
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
    }

    private void scheduleExpiryAlarm() {
        if (alarmManager == null) return;
        try {
            if (!isTimerRunning || isPaused || targetEndTimeMs <= System.currentTimeMillis()) {
                cancelExpiryAlarm();
                return;
            }
            PendingIntent pi = expiryAlarmPendingIntent();
            boolean canExact = Build.VERSION.SDK_INT < Build.VERSION_CODES.S
                    || alarmManager.canScheduleExactAlarms();
            if (canExact) {
                alarmManager.setExactAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, targetEndTimeMs, pi);
            } else {
                // No exact-alarm grant: still far better than nothing on Doze.
                alarmManager.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, targetEndTimeMs, pi);
            }
            Log.d(TAG, "scheduleExpiryAlarm: +" + (targetEndTimeMs - System.currentTimeMillis())
                    + "ms (exact=" + canExact + ")");
        } catch (Exception e) {
            Log.e(TAG, "scheduleExpiryAlarm failed: " + e.getMessage(), e);
        }
    }

    private void cancelExpiryAlarm() {
        if (alarmManager == null) return;
        try {
            alarmManager.cancel(expiryAlarmPendingIntent());
        } catch (Exception e) {
            Log.e(TAG, "cancelExpiryAlarm failed: " + e.getMessage(), e);
        }
    }

    // ---------------------------------------------------------------------------------
    // State persistence (survives an OEM / low-memory kill)
    // ---------------------------------------------------------------------------------

    private void persistState() {
        try {
            SharedPreferences.Editor e = getSharedPreferences(STATE_PREFS, MODE_PRIVATE).edit();
            e.putBoolean("timerRunning", isTimerRunning);
            e.putBoolean("paused", isPaused);
            e.putLong("targetEndTimeMs", targetEndTimeMs);
            e.putLong("totalDurationMs", totalDurationMs);
            e.putLong("remainingTimeMs", remainingTimeMs);
            e.putString("title", currentTitle);
            e.putString("soundUri", customSoundUri);
            e.putBoolean("alarmActive", isAlarmActive);
            e.putLong("alarmDeliveredForTargetMs", alarmDeliveredForTargetMs);
            e.putBoolean("workoutActive", isWorkoutActive);
            e.putString("workoutTitle", workoutTitle);
            e.putString("exerciseName", currentExerciseName);
            e.putInt("completedSets", completedSets);
            e.putInt("totalSets", totalSets);
            e.putLong("workoutStartedAt", workoutStartedAt);
            e.putLong("savedAt", System.currentTimeMillis());
            e.apply();
        } catch (Exception ex) {
            Log.e(TAG, "persistState failed: " + ex.getMessage());
        }
        mirrorPublicState();
    }

    /** A restored workout older than this has no business being resurrected — either the
     *  process sat dead for that long (unlikely to still be a real session) or the web
     *  side never called stopWorkoutIsland/stopAll for a page that was opened but never
     *  turned into a real workout. Reconciliation cleans it up instead of restoring it. */
    private static final long STALE_WORKOUT_MS = 12L * 60 * 60 * 1000L;

    /** A rest timer is always short (seconds to a few minutes). A restored deadline more
     *  than this far in the past isn't an OEM-kill-and-recover case (those land within
     *  seconds), it's a genuine device reboot (AlarmManager entries don't survive one) or
     *  a very long-abandoned process — ring a same-minute alarm, not one hours late. */
    private static final long STALE_TIMER_MS = 60L * 60 * 1000L;

    /** @return true if an active timer or workout was restored into the fields. */
    private boolean restoreStateFromPrefs() {
        try {
            SharedPreferences p = getSharedPreferences(STATE_PREFS, MODE_PRIVATE);
            if (!p.contains("savedAt")) return false;

            boolean timerRunning = p.getBoolean("timerRunning", false);
            boolean workoutActive = p.getBoolean("workoutActive", false);
            // An alarm that was ringing when the process died: restore it so the user
            // still gets the "tempo scaduto" card instead of silence.
            boolean alarmActive = p.getBoolean("alarmActive", false);
            long workoutStartedAt = p.getLong("workoutStartedAt", 0L);
            long savedTargetEndTimeMs = p.getLong("targetEndTimeMs", 0L);
            long savedAt = p.getLong("savedAt", 0L);
            long now = System.currentTimeMillis();

            if (workoutActive && workoutStartedAt > 0 && now - workoutStartedAt > STALE_WORKOUT_MS) {
                Log.d(TAG, "restoreStateFromPrefs: discarding stale workout (startedAt="
                        + workoutStartedAt + ") instead of resurrecting it");
                workoutActive = false;
            }
            if (timerRunning) {
                boolean paused = p.getBoolean("paused", false);
                // Paused has no live deadline to judge by (it's frozen) — fall back to
                // how long ago the snapshot itself was written.
                long staleness = paused ? (now - savedAt) : (now - savedTargetEndTimeMs);
                if (staleness > STALE_TIMER_MS) {
                    Log.d(TAG, "restoreStateFromPrefs: discarding stale timer (staleness="
                            + staleness + "ms) instead of ringing a hours-late alarm");
                    timerRunning = false;
                }
            }
            if (alarmActive && savedAt > 0 && now - savedAt > STALE_TIMER_MS) {
                alarmActive = false;
            }
            if (!timerRunning && !workoutActive && !alarmActive) {
                // Confirmed empty (or only a stale workout we're refusing to restore) —
                // drop whatever the snapshot said so a future restore attempt doesn't
                // re-evaluate the same stale entry.
                clearPersistedState();
                return false;
            }

            this.isAlarmActive = alarmActive;
            this.alarmDeliveredForTargetMs = alarmActive ? p.getLong("alarmDeliveredForTargetMs", 0L) : 0L;
            this.isPaused = p.getBoolean("paused", false);
            this.targetEndTimeMs = p.getLong("targetEndTimeMs", 0L);
            this.totalDurationMs = p.getLong("totalDurationMs", 0L);
            this.isTimerRunning = timerRunning;
            this.remainingTimeMs = isPaused
                    ? p.getLong("remainingTimeMs", 0L)
                    : Math.max(0L, targetEndTimeMs - System.currentTimeMillis());
            this.currentTitle = p.getString("title", "Recupero in corso");
            this.customSoundUri = p.getString("soundUri", null);

            this.isWorkoutActive = workoutActive;
            this.workoutTitle = p.getString("workoutTitle", "Sessione di Allenamento");
            this.currentExerciseName = p.getString("exerciseName", "");
            this.completedSets = p.getInt("completedSets", 0);
            this.totalSets = p.getInt("totalSets", 0);
            this.workoutStartedAt = workoutActive ? workoutStartedAt : 0L;
            mirrorPublicState();

            Log.d(TAG, "restoreStateFromPrefs: timer=" + isTimerRunning + " paused=" + isPaused
                    + " workout=" + isWorkoutActive + " alarm=" + isAlarmActive
                    + " remainingMs=" + remainingTimeMs);
            return true;
        } catch (Exception ex) {
            Log.e(TAG, "restoreStateFromPrefs failed: " + ex.getMessage());
            return false;
        }
    }

    private void clearPersistedState() {
        try {
            getSharedPreferences(STATE_PREFS, MODE_PRIVATE).edit().clear().apply();
        } catch (Exception ignored) {}
        sTimerRunning = false;
        sPaused = false;
        sTargetEndTimeMs = 0L;
        sRemainingTimeMs = 0L;
        sTitle = null;
        sWorkoutActive = false;
    }

    /** Hard ceiling on any wakelock we take: a rest timer longer than this isn't a rest timer. */
    private static final long MAX_WAKELOCK_MS = 30 * 60 * 1000L;
    /** How long the expiry alarm is allowed to keep the CPU awake while it rings. */
    private static final long ALARM_WAKELOCK_MS = 2 * 60 * 1000L;

    /**
     * Takes a PARTIAL_WAKE_LOCK for the duration of the rest countdown (or of the ringing
     * alarm) and no longer. It is never taken for a workout: the foreground service is
     * what keeps the process alive, and a wakelock held for a whole training session is
     * pure battery drain and heat. Always timeout-bounded, so even a lost release path
     * cannot pin the CPU awake indefinitely.
     */
    private synchronized void acquireTimerWakeLock(long durationMs) {
        try {
            long timeout = Math.min(MAX_WAKELOCK_MS, Math.max(1000L, durationMs + 5000L));
            if (wakeLock == null) {
                PowerManager powerManager = (PowerManager) getSystemService(Context.POWER_SERVICE);
                if (powerManager != null) {
                    wakeLock = powerManager.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "OnyxWorkout::LiveServiceWakeLock");
                    wakeLock.setReferenceCounted(false);
                }
            }
            if (wakeLock == null) return;
            // Re-acquiring a non-reference-counted lock just refreshes its timeout.
            wakeLock.acquire(timeout);
            Log.d(TAG, "acquireTimerWakeLock: held for at most " + timeout + "ms");
        } catch (Exception e) {
            Log.e(TAG, "Error acquiring WakeLock: " + e.getMessage(), e);
        }
    }

    private synchronized void releaseWakeLock() {
        try {
            if (wakeLock != null && wakeLock.isHeld()) {
                wakeLock.release();
            }
        } catch (Exception e) {
            Log.e(TAG, "Error releasing WakeLock: " + e.getMessage(), e);
        } finally {
            // Never hold on to a released/expired lock object: a later isHeld() on a
            // timed-out lock returns false and the old code then simply leaked it.
            if (wakeLock != null && !wakeLock.isHeld()) {
                wakeLock = null;
            }
        }
    }

    /**
     * Releases only what lives inside this process — never the exact-alarm backup, the
     * persisted snapshot or the posted notifications. Used by {@link #onDestroy()}.
     */
    private void releaseLocalResources() {
        isRunning = false;
        if (countDownTimer != null) {
            countDownTimer.cancel();
            countDownTimer = null;
        }
        stopNotificationTicker();
        stopAlarmSound();
        stopAlarmVibration();
        releaseAudioFocus();
        releaseWakeLock();
    }

    @Override
    public void onDestroy() {
        // Deliberately NOT stopAllAndService(). onDestroy fires on an OEM/low-memory kill
        // too (routine on HyperOS once the app is swiped away), and the old code answered
        // that by cancelling the exact-alarm backup and wiping the persisted snapshot —
        // i.e. by destroying the exact two mechanisms that exist to make the timer survive
        // being killed. A deliberate teardown has already cleaned all of that up before
        // calling stopSelfResult(); an involuntary one must leave it standing so the alarm
        // still rings and a restarted service can rebuild its state.
        Log.d(TAG, "onDestroy: releasing local resources only (timer=" + isTimerRunning
                + " paused=" + isPaused + " workout=" + isWorkoutActive + " alarm=" + isAlarmActive + ")");
        if (sInstance == this) {
            sInstance = null;
        }
        releaseLocalResources();
        super.onDestroy();
    }

    @Nullable
    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }
}
