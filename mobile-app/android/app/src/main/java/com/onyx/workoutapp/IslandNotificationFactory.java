package com.onyx.workoutapp;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.graphics.Bitmap;
import android.os.Build;
import android.util.Log;

import androidx.core.app.NotificationCompat;
import androidx.core.graphics.drawable.IconCompat;

import java.util.ArrayList;
import java.util.List;

/**
 * Builds THE notification the app posts for its "live" surface.
 *
 * <h3>One notification, always</h3>
 * There is exactly one notification id ({@link #NOTIFICATION_ID_LIVE}) on exactly one
 * channel ({@link #CHANNEL_LIVE}). Its content is a pure function of the current state,
 * resolved by {@link #buildLive(Context, LiveState)} with this priority:
 * <ol>
 *   <li>rest timer expired (alarm ringing) — "TEMPO SCADUTO";</li>
 *   <li>rest timer running/paused — countdown ring;</li>
 *   <li>workout in progress — set-progress ring.</li>
 * </ol>
 * Workout context (sets / exercise) is folded into the timer and alarm renderings instead
 * of being posted as a second notification. The previous design used three ids on three
 * channels and posted a secondary {@code notify()} alongside the foreground anchor, which
 * is how users ended up with up to three simultaneous Onyx notifications.
 *
 * <h3>Android 16 "Live Updates"</h3>
 * A notification is eligible for the prominent Live Update treatment (status-bar chip +
 * always-on-display presence) when it:
 * <ul>
 *   <li>uses a supported style — here {@link NotificationCompat.ProgressStyle};</li>
 *   <li>calls {@link NotificationCompat.Builder#setRequestPromotedOngoing(boolean)} (androidx.core 1.17.0+);</li>
 *   <li>is {@code setOngoing(true)} + {@code setOnlyAlertOnce(true)} with a non-null title;</li>
 *   <li>declares {@code android.permission.POST_PROMOTED_NOTIFICATIONS} in the manifest.</li>
 * </ul>
 *
 * <h3>Xiaomi HyperOS Super Island / Focus notifications</h3>
 * Delegated to {@link HyperFocusExtras}, which attaches the {@code miui.focus.*} extras.
 */
public class IslandNotificationFactory {

    private static final String TAG = "OnyxDebug";

    /**
     * The one and only channel. v3: single channel replacing the old timer/alarm/workout
     * trio. IMPORTANCE_HIGH so it reaches the status bar and the HyperOS Focus island;
     * sound and vibration are disabled on the channel because the expiry alarm drives
     * its own MediaPlayer/Vibrator from {@link OnyxLiveService}.
     */
    public static final String CHANNEL_LIVE = "onyx_live_v3";

    /** Channels created by earlier builds — deleted on first run of this one. */
    private static final String[] LEGACY_CHANNELS = {
            "onyx_timer_live_channel",
            "onyx_timer_alarm_channel",
            "onyx_workout_progress_channel",
            "onyx_workout_progress_channel_v2",
    };

    /** The one and only notification id. */
    public static final int NOTIFICATION_ID_LIVE = 1001;

    /**
     * Ids posted by earlier builds (throwaway anchor 1000, alarm 1002, workout 1003).
     * Cancelled unconditionally whenever we post or tear down, so an upgrade over a live
     * session can never leave an orphan behind.
     */
    public static final int[] LEGACY_NOTIFICATION_IDS = {1000, 1002, 1003};

    /** Onyx accent (lime). */
    private static final int ACCENT = 0xFFCAF300;
    /** Dim track colour for spent / upcoming progress segments. */
    private static final int TRACK_DIM = 0xFF3A3D24;

    /**
     * Set by {@link OnyxLiveService} from MainActivity's start/stop callbacks. While the
     * app is on screen the rich in-app "notch" already shows the timer/workout, so we
     * suppress the promoted status-bar chip / HyperOS island to avoid a visible duplicate.
     * The (silent) ongoing notification still exists — a foreground service requires one.
     */
    public static volatile boolean appInForeground = false;

    /**
     * Everything the single notification needs to render itself. Filled by
     * {@link OnyxLiveService#updateForegroundState()} from its live fields.
     */
    public static final class LiveState {
        public boolean alarmActive;
        public boolean timerRunning;
        public boolean timerPaused;
        public long targetEndTimeMs;
        public long remainingMs;
        public long totalDurationMs;
        public String timerTitle;

        public boolean workoutActive;
        public String workoutTitle;
        public String exerciseName;
        public int completedSets;
        public int totalSets;
        public long workoutStartedAt;

        public Bitmap appIcon;

        /** True when there is anything at all to show. */
        public boolean hasContent() {
            return alarmActive || timerRunning || workoutActive;
        }
    }

    public static void createNotificationChannels(NotificationManager notificationManager) {
        if (notificationManager == null || Build.VERSION.SDK_INT < Build.VERSION_CODES.O) {
            return;
        }

        NotificationChannel live = new NotificationChannel(
                CHANNEL_LIVE,
                "Onyx Live",
                NotificationManager.IMPORTANCE_HIGH
        );
        live.setDescription("Allenamento in corso, timer di recupero e allarme di fine recupero");
        live.setSound(null, null);
        live.enableVibration(false);
        live.setShowBadge(false);
        live.setLockscreenVisibility(Notification.VISIBILITY_PUBLIC);
        notificationManager.createNotificationChannel(live);

        for (String legacy : LEGACY_CHANNELS) {
            try {
                notificationManager.deleteNotificationChannel(legacy);
            } catch (Exception ignored) {}
        }
    }

    /** Cancels every id this app has ever posted except the live one. */
    public static void cancelLegacyNotifications(NotificationManager notificationManager) {
        if (notificationManager == null) return;
        for (int id : LEGACY_NOTIFICATION_IDS) {
            try {
                notificationManager.cancel(id);
            } catch (Exception ignored) {}
        }
    }

    /**
     * Builds a PendingIntent that targets OnyxLiveService. On API >= 26 we must use
     * getForegroundService(), otherwise tapping a notification action after the OS has
     * reclaimed the service delivers a plain background startService() which is either
     * blocked (ForegroundServiceStartNotAllowedException) or killed 5s later
     * (ForegroundServiceDidNotStartInTimeException).
     */
    private static PendingIntent serviceActionPendingIntent(Context context, int requestCode, String action) {
        Intent intent = new Intent(context, OnyxLiveService.class);
        intent.setAction(action);
        int flags = PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            return PendingIntent.getForegroundService(context, requestCode, intent, flags);
        }
        return PendingIntent.getService(context, requestCode, intent, flags);
    }

    private static PendingIntent contentPendingIntent(Context context, String extraFlag) {
        Intent appIntent = new Intent(context, MainActivity.class);
        appIntent.setFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP | Intent.FLAG_ACTIVITY_CLEAR_TOP);
        appIntent.putExtra(extraFlag, true);
        return PendingIntent.getActivity(
                context,
                NOTIFICATION_ID_LIVE,
                appIntent,
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE
        );
    }

    /**
     * Real (non-reflection) promoted-ongoing request. Safe on every API level: the
     * androidx.core wrapper is a no-op below Android 16 and simply records the intent
     * in the compat extras, and the OS ignores it unless the notification is otherwise
     * eligible + the POST_PROMOTED_NOTIFICATIONS permission is held.
     */
    private static void requestPromotedOngoing(NotificationCompat.Builder builder, String shortCriticalText, boolean force) {
        if (builder == null) return;
        builder.setOngoing(true);
        // Foreground: keep it a plain ongoing notification, no chip / island (the in-app
        // notch is already showing this). Background: request the full Live Update.
        boolean promote = force || !appInForeground;
        try {
            builder.setRequestPromotedOngoing(promote);
            if (promote && shortCriticalText != null && !shortCriticalText.isEmpty()) {
                builder.setShortCriticalText(shortCriticalText);
            }
        } catch (Throwable t) {
            Log.d(TAG, "requestPromotedOngoing skipped: " + t.getMessage());
        }
    }

    private static IconCompat safeIcon(Context context, int resId) {
        try {
            return IconCompat.createWithResource(context, resId);
        } catch (Throwable t) {
            return null;
        }
    }

    private static String setsSuffix(LiveState s) {
        if (!s.workoutActive || s.totalSets <= 0) return "";
        int safeTotal = Math.max(1, s.totalSets);
        int safeCompleted = Math.max(0, Math.min(safeTotal, s.completedSets));
        return safeCompleted + "/" + safeTotal + " serie";
    }

    // ----------------------------------------------------------------------------------
    // THE notification
    // ----------------------------------------------------------------------------------

    /**
     * Single entry point: renders the one live notification for the given state.
     * Never returns null as long as {@link LiveState#hasContent()} is true; when it is
     * false the caller should be tearing the service down, and gets the minimal anchor.
     */
    public static Notification buildLive(Context context, LiveState s) {
        if (s == null || !s.hasContent()) {
            return buildMinimalAnchor(context);
        }
        if (s.alarmActive) {
            return buildAlarm(context, s);
        }
        if (s.timerRunning) {
            return buildRest(context, s);
        }
        return buildWorkout(context, s);
    }

    // ---- 1. rest timer expired -------------------------------------------------------

    private static Notification buildAlarm(Context context, LiveState s) {
        PendingIntent tap = contentPendingIntent(context, "open_timer");
        PendingIntent stopAlarm = serviceActionPendingIntent(context, 2, OnyxLiveService.ACTION_STOP_ALARM);

        String sets = setsSuffix(s);
        String body = "Il recupero è terminato. Tocca per disattivare l'allarme.";

        NotificationCompat.Builder builder = new NotificationCompat.Builder(context, CHANNEL_LIVE)
                .setSmallIcon(R.drawable.ic_stat_onyx)
                .setColor(ACCENT)
                // Full lime card, black auto-contrast text — mirrors the in-app yellow notch.
                .setColorized(true)
                .setContentTitle("TEMPO SCADUTO!")
                .setContentText(body)
                .setStyle(new NotificationCompat.BigTextStyle()
                        .setBigContentTitle("TEMPO SCADUTO!")
                        .bigText(body))
                .setContentIntent(tap)
                .setFullScreenIntent(tap, true)
                .setOnlyAlertOnce(true)
                .setUsesChronometer(false)
                .setShowWhen(false)
                .setCategory(NotificationCompat.CATEGORY_ALARM)
                .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
                .setPriority(NotificationCompat.PRIORITY_MAX)
                .addAction(android.R.drawable.ic_lock_power_off, "DISATTIVA ALLARME", stopAlarm);

        if (!sets.isEmpty()) {
            builder.setSubText(sets);
        }
        if (s.appIcon != null) {
            builder.setLargeIcon(s.appIcon);
        }

        // The "time's up" alarm is always prominent — even if the app is in the foreground.
        requestPromotedOngoing(builder, "Scaduto", true);
        HyperFocusExtras.applyAlarmFocus(builder, context, ACCENT);
        return builder.build();
    }

    // ---- 2. rest timer running / paused ----------------------------------------------

    private static Notification buildRest(Context context, LiveState s) {
        NotificationCompat.Builder builder = new NotificationCompat.Builder(context, CHANNEL_LIVE)
                .setSmallIcon(R.drawable.ic_stat_onyx)
                .setColor(ACCENT)
                .setColorized(false)
                .setContentIntent(contentPendingIntent(context, "open_timer"))
                .setOngoing(true)
                .setOnlyAlertOnce(true)
                .setCategory(NotificationCompat.CATEGORY_STOPWATCH)
                .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
                .setPriority(NotificationCompat.PRIORITY_MAX)
                .setDefaults(0)
                .setSilent(true)
                .setContentTitle("ONYX");

        if (s.appIcon != null) {
            builder.setLargeIcon(s.appIcon);
        }

        boolean isPaused = s.timerPaused;
        int totalSec = (int) Math.max(1, Math.round(s.totalDurationMs / 1000.0));
        long secLeft = (long) Math.max(0, Math.ceil(s.remainingMs / 1000.0));
        int elapsedSec = (int) Math.max(0, Math.min(totalSec, totalSec - secLeft));
        String mmss = String.format("%02d:%02d", secLeft / 60, secLeft % 60);
        String safeTitle = (s.timerTitle != null && !s.timerTitle.isEmpty()) ? s.timerTitle : "Recupero in corso";
        String sets = setsSuffix(s);
        String withSets = sets.isEmpty() ? safeTitle : (safeTitle + " • " + sets);

        if (!isPaused) {
            long now = System.currentTimeMillis();
            if (s.targetEndTimeMs > now) {
                builder.setContentText(withSets)
                       .setSubText(mmss)
                       .setUsesChronometer(true)
                       .setChronometerCountDown(true)
                       .setWhen(s.targetEndTimeMs)
                       .setShowWhen(true);
            } else {
                builder.setContentText("Tempo Scaduto! • Tocca per aprire")
                       .setUsesChronometer(false)
                       .setShowWhen(false);
            }
        } else {
            builder.setUsesChronometer(false)
                   .setShowWhen(false)
                   .setSubText("Pausa (" + mmss + ")")
                   .setContentText("In Pausa • " + withSets);
        }

        // Android 16 ProgressStyle: one segment spanning the full duration, tracker at
        // the elapsed position so the bar "fills up" as the rest runs out.
        try {
            NotificationCompat.ProgressStyle progressStyle = new NotificationCompat.ProgressStyle()
                    .setProgressSegments(java.util.Collections.singletonList(
                            new NotificationCompat.ProgressStyle.Segment(totalSec).setColor(ACCENT)))
                    .setProgress(elapsedSec)
                    .setProgressIndeterminate(false)
                    .setStyledByProgress(true);
            IconCompat tracker = safeIcon(context, R.drawable.ic_stat_onyx);
            if (tracker != null) {
                progressStyle.setProgressTrackerIcon(tracker);
            }
            builder.setStyle(progressStyle);
        } catch (Throwable t) {
            Log.d(TAG, "ProgressStyle (rest) unavailable, falling back: " + t.getMessage());
            builder.setProgress(totalSec, elapsedSec, false);
        }

        builder.addAction(
                isPaused ? android.R.drawable.ic_media_play : android.R.drawable.ic_media_pause,
                isPaused ? "Riprendi" : "Pausa",
                serviceActionPendingIntent(context, 10,
                        isPaused ? OnyxLiveService.ACTION_RESUME : OnyxLiveService.ACTION_PAUSE));
        builder.addAction(android.R.drawable.ic_input_add, "+30s",
                serviceActionPendingIntent(context, 11, OnyxLiveService.ACTION_ADD_TIME));
        builder.addAction(android.R.drawable.ic_menu_close_clear_cancel, "Stop",
                serviceActionPendingIntent(context, 12, OnyxLiveService.ACTION_STOP));

        // Status-bar chip fallback text (chronometer wins when running).
        requestPromotedOngoing(builder, isPaused ? ("Pausa " + mmss) : mmss, false);

        float ratio = s.totalDurationMs > 0 ? (float) s.remainingMs / (float) s.totalDurationMs : 0f;
        HyperFocusExtras.applyRestFocus(builder, context, ratio, s.targetEndTimeMs, secLeft, isPaused,
                safeTitle, ACCENT);

        return builder.build();
    }

    // ---- 3. workout in progress ------------------------------------------------------

    private static Notification buildWorkout(Context context, LiveState s) {
        NotificationCompat.Builder builder = new NotificationCompat.Builder(context, CHANNEL_LIVE)
                .setSmallIcon(R.drawable.ic_stat_onyx)
                .setColor(ACCENT)
                .setColorized(false)
                .setContentIntent(contentPendingIntent(context, "open_workout"))
                .setOngoing(true)
                .setOnlyAlertOnce(true)
                .setCategory(NotificationCompat.CATEGORY_WORKOUT)
                .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
                .setPriority(NotificationCompat.PRIORITY_DEFAULT)
                .setDefaults(0)
                .setSilent(true)
                .setContentTitle("ONYX");

        if (s.appIcon != null) {
            builder.setLargeIcon(s.appIcon);
        }

        int safeTotal = Math.max(1, s.totalSets);
        int safeCompleted = Math.max(0, Math.min(safeTotal, s.completedSets));
        float ratio = (float) safeCompleted / (float) safeTotal;
        String title = s.workoutTitle;

        builder.setSubText(safeCompleted + "/" + safeTotal + " serie");
        if (s.exerciseName != null && !s.exerciseName.trim().isEmpty()) {
            builder.setContentText(s.exerciseName);
        } else {
            builder.setContentText(title != null && !title.isEmpty() ? title : "Sessione di Allenamento");
        }

        // Pre-16 progress bar fallback.
        builder.setProgress(safeTotal, safeCompleted, false);

        if (s.workoutStartedAt > 0) {
            builder.setWhen(s.workoutStartedAt);
            builder.setShowWhen(true);
            builder.setUsesChronometer(true);
            builder.setChronometerCountDown(false);
        }

        // Android 16 ProgressStyle: one segment per set (a segmented "pill" bar) when the
        // count is reasonable, otherwise a single segment.
        try {
            NotificationCompat.ProgressStyle progressStyle = new NotificationCompat.ProgressStyle()
                    .setProgressIndeterminate(false)
                    .setStyledByProgress(true);

            if (safeTotal <= 30) {
                List<NotificationCompat.ProgressStyle.Segment> segments = new ArrayList<>(safeTotal);
                for (int i = 0; i < safeTotal; i++) {
                    segments.add(new NotificationCompat.ProgressStyle.Segment(1)
                            .setColor(i < safeCompleted ? ACCENT : TRACK_DIM));
                }
                progressStyle.setProgressSegments(segments);
            } else {
                progressStyle.setProgressSegments(java.util.Collections.singletonList(
                        new NotificationCompat.ProgressStyle.Segment(safeTotal).setColor(ACCENT)));
            }
            progressStyle.setProgress(safeCompleted);

            IconCompat tracker = safeIcon(context, R.drawable.ic_stat_onyx);
            if (tracker != null) {
                progressStyle.setProgressTrackerIcon(tracker);
            }
            builder.setStyle(progressStyle);
        } catch (Throwable t) {
            Log.d(TAG, "ProgressStyle (workout) unavailable, falling back: " + t.getMessage());
        }

        // Escape hatch for the "zombie session" case: the user can always end the session
        // (and with it this notification) straight from the shade.
        builder.addAction(android.R.drawable.ic_menu_close_clear_cancel, "Termina",
                serviceActionPendingIntent(context, 13, OnyxLiveService.ACTION_STOP_ALL));

        requestPromotedOngoing(builder, safeCompleted + "/" + safeTotal, false);

        HyperFocusExtras.applyWorkoutFocus(builder, context, ratio, safeCompleted, safeTotal,
                title, s.exerciseName, s.workoutStartedAt, ACCENT);

        return builder.build();
    }

    /**
     * Bare-bones silent notification used only to satisfy the startForeground()
     * obligation when a cold-recreated service has no live state left to display. Posted
     * on the SAME id as the real notification so it can never coexist with it; the caller
     * tears the service down immediately afterwards.
     */
    public static Notification buildMinimalAnchor(Context context) {
        return new NotificationCompat.Builder(context, CHANNEL_LIVE)
                .setSmallIcon(R.drawable.ic_stat_onyx)
                .setContentTitle("Onyx")
                .setPriority(NotificationCompat.PRIORITY_MIN)
                .setCategory(NotificationCompat.CATEGORY_SERVICE)
                .setSilent(true)
                .setOngoing(false)
                .build();
    }

    /**
     * Standalone "TEMPO SCADUTO" notification posted directly by
     * {@link TimerExpiryAlarmReceiver} when it cannot legally start the foreground
     * service (background-FGS-start restrictions). Same id as everything else, so when
     * the service does come up its own render simply replaces this one.
     */
    public static Notification buildAlarmFallback(Context context) {
        LiveState s = new LiveState();
        s.alarmActive = true;
        return buildAlarm(context, s);
    }
}
