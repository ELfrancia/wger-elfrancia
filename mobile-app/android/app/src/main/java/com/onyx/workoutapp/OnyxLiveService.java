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
import android.os.IBinder;
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

    /** Throwaway foreground anchor used when a cold-recreated service has no live state. */
    private static final int NOTIFICATION_ID_ANCHOR = 1000;

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

    // Rest timer state
    private boolean isAlarmPlaying = false;
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
     * Reports an ACTIVE PROMOTED ongoing notification: a timer/workout is live AND the app
     * is backgrounded (so the native island is what the user sees). While the app is in the
     * foreground this returns false so the web keeps showing its in-app notch instead.
     */
    public static boolean hasActiveOngoingNotification() {
        return hasActiveOngoingNotification && !IslandNotificationFactory.appInForeground;
    }

    private Bitmap appIconBitmap;

    @Override
    public void onCreate() {
        super.onCreate();
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
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        boolean redelivered = (flags & START_FLAG_REDELIVERY) != 0;
        String action = intent != null ? intent.getAction() : null;

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
            if (restoreStateFromPrefs()) {
                resumeFromRestoredState();
            }
            if (!isTimerRunning && !isWorkoutActive && !isAlarmPlaying) {
                stopAllAndService();
                return START_NOT_STICKY;
            }
            return START_REDELIVER_INTENT;
        }

        Log.d(TAG, "OnyxLiveService onStartCommand: action=" + action);

        // App foreground/background transitions only re-render existing notifications
        // (promote when bg, demote when fg). They never start or stop the service.
        if (ACTION_APP_FOREGROUND.equals(action) || ACTION_APP_BACKGROUND.equals(action)) {
            IslandNotificationFactory.appInForeground = ACTION_APP_FOREGROUND.equals(action);
            if (isTimerRunning || isWorkoutActive || isAlarmPlaying) {
                updateForegroundState();
            } else {
                stopAllAndService();
                return START_NOT_STICKY;
            }
            return START_REDELIVER_INTENT;
        }

        try {
            handleAction(action, intent);
        } catch (Exception e) {
            Log.e(TAG, "onStartCommand handler crashed for action " + action + ": " + e.getMessage(), e);
        }

        // If the action left nothing live to display, drop the (possibly minimal) anchor.
        if (!isTimerRunning && !isWorkoutActive && !isAlarmPlaying) {
            stopAllAndService();
            return START_NOT_STICKY;
        }

        // Something is live -> ask the OS to restart us (and redeliver) if it kills us.
        // The redelivered intent is ignored on the way back in; state comes from prefs.
        return START_REDELIVER_INTENT;
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
                    acquireWakeLock();
                    triggerTimerFinishedAlarm();
                    return;
                }
                remainingTimeMs = left;
                acquireWakeLock();
                updateForegroundState();
                startInternalCountDown(remainingTimeMs);
            } else if (isTimerRunning) { // paused
                acquireWakeLock();
                updateForegroundState();
            }
            if (isWorkoutActive) {
                acquireWakeLock();
                updateForegroundState();
            }
        } catch (Exception e) {
            Log.e(TAG, "resumeFromRestoredState failed: " + e.getMessage(), e);
        }
    }

    private void ensureForegroundAnchor() {
        try {
            if (isTimerRunning || isWorkoutActive || isAlarmPlaying) {
                updateForegroundState();
            } else {
                postAsForegroundAnchor(NOTIFICATION_ID_ANCHOR, IslandNotificationFactory.buildMinimalAnchor(this));
            }
        } catch (Exception e) {
            Log.e(TAG, "ensureForegroundAnchor failed: " + e.getMessage(), e);
        }
    }

    private void handleAction(String action, Intent intent) {
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
                // Exact-alarm backup fired (see TimerExpiryAlarmReceiver). If we were
                // cold-started by it, our fields are at defaults -> restore first.
                if (!isTimerRunning && !isAlarmPlaying && !isWorkoutActive) {
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
                    acquireWakeLock();
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
                acquireWakeLock();
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
                if (notificationManager != null) {
                    try {
                        notificationManager.cancel(IslandNotificationFactory.NOTIFICATION_ID_WORKOUT);
                    } catch (Exception ignored) {}
                }
                if (!isTimerRunning && !isAlarmPlaying) {
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
        if (notificationManager != null) {
            try {
                notificationManager.cancel(IslandNotificationFactory.NOTIFICATION_ID_ALARM);
            } catch (Exception ignored) {}
        }

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

        acquireWakeLock();
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
        updateForegroundState();
        OnyxLivePlugin.notifyTimerPaused();
    }

    private synchronized void resumeTimer() {
        if (!isTimerRunning || !isPaused) return;
        targetEndTimeMs = System.currentTimeMillis() + remainingTimeMs;
        isPaused = false;
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
        if (notificationManager != null) {
            try {
                notificationManager.cancel(IslandNotificationFactory.NOTIFICATION_ID_ALARM);
            } catch (Exception ignored) {}
        }

        this.totalDurationMs = Math.max(1, durationSeconds) * 1000L;
        this.remainingTimeMs = Math.max(0, remainingSeconds * 1000L);
        this.targetEndTimeMs = System.currentTimeMillis() + remainingTimeMs;
        this.isTimerRunning = remainingTimeMs > 0;
        this.isPaused = false;

        acquireWakeLock();
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

        if (notificationManager != null) {
            try {
                notificationManager.cancel(IslandNotificationFactory.NOTIFICATION_ID_TIMER);
            } catch (Exception ignored) {}
        }

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
     * Centralized Foreground Service Anchor management:
     * - Workout active -> 1003 is FGS anchor; 1001 / 1002 posted as secondary.
     * - No workout, Timer active -> 1001 is FGS anchor.
     * - No workout, Alarm active -> 1002 is FGS anchor.
     */
    private synchronized void updateForegroundState() {
        if (notificationManager == null) return;

        hasActiveOngoingNotification = isWorkoutActive || isTimerRunning;

        try {
            if (isWorkoutActive) {
                Notification workoutNotification = IslandNotificationFactory.buildWorkoutNotification(
                        this, workoutTitle, currentExerciseName, completedSets, totalSets, slotBoundaries, workoutStartedAt, appIconBitmap
                );
                postAsForegroundAnchor(IslandNotificationFactory.NOTIFICATION_ID_WORKOUT, workoutNotification);

                // Reconcile the timer / alarm slots independently — never let a state
                // update silently drop the "rest running" or "time's up" notification.
                if (isTimerRunning) {
                    Notification timerNotification = IslandNotificationFactory.buildRestNotification(
                            this, targetEndTimeMs, remainingTimeMs, totalDurationMs, currentTitle, isPaused, appIconBitmap
                    );
                    notificationManager.notify(IslandNotificationFactory.NOTIFICATION_ID_TIMER, timerNotification);
                    cancelQuietly(IslandNotificationFactory.NOTIFICATION_ID_ALARM);
                } else if (isAlarmPlaying) {
                    // Rest timer expired mid-workout: keep the alarm notification visible and tappable.
                    Notification alarmNotification = IslandNotificationFactory.buildAlarmNotification(this, appIconBitmap);
                    notificationManager.notify(IslandNotificationFactory.NOTIFICATION_ID_ALARM, alarmNotification);
                    cancelQuietly(IslandNotificationFactory.NOTIFICATION_ID_TIMER);
                } else {
                    cancelQuietly(IslandNotificationFactory.NOTIFICATION_ID_TIMER);
                    cancelQuietly(IslandNotificationFactory.NOTIFICATION_ID_ALARM);
                }
            } else if (isTimerRunning) {
                Notification timerNotification = IslandNotificationFactory.buildRestNotification(
                        this, targetEndTimeMs, remainingTimeMs, totalDurationMs, currentTitle, isPaused, appIconBitmap
                );
                postAsForegroundAnchor(IslandNotificationFactory.NOTIFICATION_ID_TIMER, timerNotification);
                cancelQuietly(IslandNotificationFactory.NOTIFICATION_ID_ALARM);
            } else if (isAlarmPlaying) {
                Notification alarmNotification = IslandNotificationFactory.buildAlarmNotification(this, appIconBitmap);
                postAsForegroundAnchor(IslandNotificationFactory.NOTIFICATION_ID_ALARM, alarmNotification);
                cancelQuietly(IslandNotificationFactory.NOTIFICATION_ID_TIMER);
            }
        } catch (Exception e) {
            Log.e(TAG, "Error updating foreground notifications: " + e.getMessage(), e);
        }

        // Mirror the live state so a killed/redelivered service can rebuild it.
        persistState();
    }

    private void cancelQuietly(int id) {
        if (notificationManager == null) return;
        try {
            notificationManager.cancel(id);
        } catch (Exception ignored) {}
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
                // Once a real anchor is live, drop the throwaway one.
                if (id != NOTIFICATION_ID_ANCHOR) {
                    try {
                        notificationManager.cancel(NOTIFICATION_ID_ANCHOR);
                    } catch (Exception ignored) {}
                }
            }
        } catch (Exception e) {
            Log.e(TAG, "Error posting foreground anchor notification (" + id + "): " + e.getMessage(), e);
        }
    }

    private synchronized void triggerTimerFinishedAlarm() {
        // Guard against double-firing (onFinish + a stray manual call): the alarm
        // is already ringing, don't restart sound/vibration or re-post the notification.
        if (isAlarmPlaying) return;

        if (countDownTimer != null) {
            countDownTimer.cancel();
            countDownTimer = null;
        }
        cancelExpiryAlarm();
        isTimerRunning = false;
        isPaused = false;
        hasActiveOngoingNotification = isWorkoutActive;

        if (notificationManager != null) {
            try {
                notificationManager.cancel(IslandNotificationFactory.NOTIFICATION_ID_TIMER);
            } catch (Exception ignored) {}
        }

        requestExclusiveAudioFocus();
        playLoopingAlarmSound();
        startAlarmVibration();

        Notification alarmNotification = IslandNotificationFactory.buildAlarmNotification(this, appIconBitmap);
        if (isWorkoutActive) {
            // Keep workout as anchor, notify alarm
            if (notificationManager != null) {
                notificationManager.notify(IslandNotificationFactory.NOTIFICATION_ID_ALARM, alarmNotification);
            }
        } else {
            postAsForegroundAnchor(IslandNotificationFactory.NOTIFICATION_ID_ALARM, alarmNotification);
        }

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

            Uri alertUri = null;
            if (customSoundUri != null && !customSoundUri.isEmpty() && !"system_alarm".equalsIgnoreCase(customSoundUri)) {
                try {
                    alertUri = Uri.parse(customSoundUri);
                } catch (Exception e) {
                    Log.w(TAG, "Invalid custom sound URI: " + customSoundUri);
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
        isAlarmPlaying = false;
        stopAlarmSound();
        stopAlarmVibration();
        releaseAudioFocus();
        if (notificationManager != null) {
            try {
                notificationManager.cancel(IslandNotificationFactory.NOTIFICATION_ID_ALARM);
            } catch (Exception ignored) {}
        }
    }

    private synchronized void stopAllAndService() {
        hasActiveOngoingNotification = false;
        isRunning = false;
        isTimerRunning = false;
        isPaused = false;
        isWorkoutActive = false;

        if (countDownTimer != null) {
            countDownTimer.cancel();
            countDownTimer = null;
        }
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
                notificationManager.cancel(NOTIFICATION_ID_ANCHOR);
                notificationManager.cancel(IslandNotificationFactory.NOTIFICATION_ID_TIMER);
                notificationManager.cancel(IslandNotificationFactory.NOTIFICATION_ID_ALARM);
                notificationManager.cancel(IslandNotificationFactory.NOTIFICATION_ID_WORKOUT);
            } catch (Exception ignored) {}
        }
        stopSelf();
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
    }

    /** @return true if an active timer or workout was restored into the fields. */
    private boolean restoreStateFromPrefs() {
        try {
            SharedPreferences p = getSharedPreferences(STATE_PREFS, MODE_PRIVATE);
            if (!p.contains("savedAt")) return false;

            boolean timerRunning = p.getBoolean("timerRunning", false);
            boolean workoutActive = p.getBoolean("workoutActive", false);
            if (!timerRunning && !workoutActive) return false;

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
            this.workoutStartedAt = p.getLong("workoutStartedAt", 0L);

            Log.d(TAG, "restoreStateFromPrefs: timer=" + isTimerRunning + " paused=" + isPaused
                    + " workout=" + isWorkoutActive + " remainingMs=" + remainingTimeMs);
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
    }

    private void acquireWakeLock() {
        try {
            if (wakeLock == null) {
                PowerManager powerManager = (PowerManager) getSystemService(Context.POWER_SERVICE);
                if (powerManager != null) {
                    wakeLock = powerManager.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "OnyxWorkout::LiveServiceWakeLock");
                    wakeLock.setReferenceCounted(false);
                }
            }
            if (wakeLock != null && !wakeLock.isHeld()) {
                wakeLock.acquire(30 * 60 * 1000L);
            }
        } catch (Exception e) {
            Log.e(TAG, "Error acquiring WakeLock: " + e.getMessage(), e);
        }
    }

    private void releaseWakeLock() {
        try {
            if (wakeLock != null && wakeLock.isHeld()) {
                wakeLock.release();
            }
        } catch (Exception e) {
            Log.e(TAG, "Error releasing WakeLock: " + e.getMessage(), e);
        }
    }

    @Override
    public void onDestroy() {
        stopAllAndService();
        super.onDestroy();
    }

    @Nullable
    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }
}
