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
 * Builds every notification the app posts for its "live" surfaces.
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
 * The prominent chip itself only renders on Android 16 QPR1+; on plain API 36 the
 * notification still posts and behaves as a normal ongoing notification.
 *
 * <h3>Xiaomi HyperOS Super Island / Focus notifications</h3>
 * Delegated to {@link HyperFocusExtras}, which attaches the {@code miui.focus.*} extras.
 */
public class IslandNotificationFactory {

    private static final String TAG = "OnyxDebug";

    public static final String CHANNEL_TIMER = "onyx_timer_live_channel";
    public static final String CHANNEL_ALARM = "onyx_timer_alarm_channel";
    // v2: bumped from IMPORTANCE_LOW to DEFAULT so the workout progress notification
    // actually reaches the status bar / HyperOS Focus island. A channel's importance is
    // immutable once created, hence the new id.
    public static final String CHANNEL_WORKOUT = "onyx_workout_progress_channel_v2";

    public static final int NOTIFICATION_ID_TIMER = 1001;
    public static final int NOTIFICATION_ID_ALARM = 1002;
    public static final int NOTIFICATION_ID_WORKOUT = 1003;

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

    public static void createNotificationChannels(NotificationManager notificationManager) {
        if (notificationManager == null || Build.VERSION.SDK_INT < Build.VERSION_CODES.O) {
            return;
        }

        // 1. Live rest countdown channel
        NotificationChannel timerChannel = new NotificationChannel(
                CHANNEL_TIMER,
                "Timer Recupero Live",
                NotificationManager.IMPORTANCE_HIGH
        );
        timerChannel.setDescription("Mostra il countdown di recupero e l'anello dinamico nella barra di stato");
        timerChannel.setSound(null, null);
        timerChannel.enableVibration(false);
        timerChannel.setShowBadge(true);
        timerChannel.setLockscreenVisibility(Notification.VISIBILITY_PUBLIC);
        notificationManager.createNotificationChannel(timerChannel);

        // 2. Alarm channel
        NotificationChannel alarmChannel = new NotificationChannel(
                CHANNEL_ALARM,
                "Allarme Timer Esaurito",
                NotificationManager.IMPORTANCE_HIGH
        );
        alarmChannel.setDescription("Allarme sonoro al termine del recupero");
        alarmChannel.setSound(null, null);
        alarmChannel.enableVibration(true);
        alarmChannel.setShowBadge(true);
        alarmChannel.setLockscreenVisibility(Notification.VISIBILITY_PUBLIC);
        notificationManager.createNotificationChannel(alarmChannel);

        // 3. Workout progress live activity channel. DEFAULT importance (silenced on the
        // builder) so it gets a status-bar slot + HyperOS Focus island while backgrounded.
        NotificationChannel workoutChannel = new NotificationChannel(
                CHANNEL_WORKOUT,
                "Progresso Allenamento Live",
                NotificationManager.IMPORTANCE_DEFAULT
        );
        workoutChannel.setDescription("Mostra l'anello di avanzamento delle serie nella Super Island e barra di stato");
        workoutChannel.setSound(null, null);
        workoutChannel.enableVibration(false);
        workoutChannel.setShowBadge(false);
        workoutChannel.setLockscreenVisibility(Notification.VISIBILITY_PUBLIC);
        notificationManager.createNotificationChannel(workoutChannel);

        // Best-effort cleanup of the pre-v2 low-importance channel.
        try {
            notificationManager.deleteNotificationChannel("onyx_workout_progress_channel");
        } catch (Exception ignored) {}
    }

    /**
     * Builds a PendingIntent that targets OnyxLiveService. On API >= 26 we must use
     * getForegroundService(), otherwise tapping a notification action after the OS has
     * reclaimed the service delivers a plain background startService() which is either
     * blocked (ForegroundServiceStartNotAllowedException) or killed 5s later
     * (ForegroundServiceDidNotStartInTimeException).
     */
    private static PendingIntent serviceActionPendingIntent(Context context, int requestCode, Intent intent) {
        int flags = PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            return PendingIntent.getForegroundService(context, requestCode, intent, flags);
        }
        return PendingIntent.getService(context, requestCode, intent, flags);
    }

    /**
     * Real (non-reflection) promoted-ongoing request. Safe on every API level: the
     * androidx.core wrapper is a no-op below Android 16 and simply records the intent
     * in the compat extras, and the OS ignores it unless the notification is otherwise
     * eligible + the POST_PROMOTED_NOTIFICATIONS permission is held.
     */
    private static void requestPromotedOngoing(NotificationCompat.Builder builder, Context context, String shortCriticalText) {
        if (builder == null) return;
        builder.setOngoing(true);
        // Foreground: keep it a plain ongoing notification, no chip / island (the in-app
        // notch is already showing this). Background: request the full Live Update.
        boolean promote = !appInForeground;
        try {
            builder.setRequestPromotedOngoing(promote);
            if (promote && shortCriticalText != null && !shortCriticalText.isEmpty()) {
                // Text shown inside the collapsed status-bar chip when there is no
                // chronometer to display or as the critical status text.
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

    // ----------------------------------------------------------------------------------
    // Rest countdown
    // ----------------------------------------------------------------------------------

    public static Notification buildRestNotification(
            Context context,
            long targetEndTime,
            long remainingMs,
            long totalDurationMs,
            String title,
            boolean isPaused,
            Bitmap appIconBitmap
    ) {
        Intent appIntent = new Intent(context, MainActivity.class);
        appIntent.setFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP | Intent.FLAG_ACTIVITY_CLEAR_TOP);
        appIntent.putExtra("open_timer", true);
        PendingIntent contentPendingIntent = PendingIntent.getActivity(
                context,
                NOTIFICATION_ID_TIMER,
                appIntent,
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE
        );

        NotificationCompat.Builder builder = new NotificationCompat.Builder(context, CHANNEL_TIMER)
                .setSmallIcon(R.drawable.ic_stat_onyx)
                .setColor(ACCENT)
                .setColorized(false)
                .setContentIntent(contentPendingIntent)
                .setOngoing(true)
                .setOnlyAlertOnce(true)
                .setCategory(NotificationCompat.CATEGORY_STOPWATCH)
                .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
                .setPriority(NotificationCompat.PRIORITY_MAX)
                .setDefaults(0)
                .setSilent(true);

        if (appIconBitmap != null) {
            builder.setLargeIcon(appIconBitmap);
        }

        builder.setContentTitle("ONYX");

        // ---- Actions -------------------------------------------------------------------
        Intent playPauseIntent = new Intent(context, OnyxLiveService.class);
        playPauseIntent.setAction(isPaused ? OnyxLiveService.ACTION_RESUME : OnyxLiveService.ACTION_PAUSE);
        PendingIntent playPausePendingIntent = serviceActionPendingIntent(context, 10, playPauseIntent);
        int playPauseIcon = isPaused ? android.R.drawable.ic_media_play : android.R.drawable.ic_media_pause;
        String playPauseText = isPaused ? "Riprendi" : "Pausa";

        Intent addTimeIntent = new Intent(context, OnyxLiveService.class);
        addTimeIntent.setAction(OnyxLiveService.ACTION_ADD_TIME);
        PendingIntent addTimePendingIntent = serviceActionPendingIntent(context, 11, addTimeIntent);

        Intent stopIntent = new Intent(context, OnyxLiveService.class);
        stopIntent.setAction(OnyxLiveService.ACTION_STOP);
        PendingIntent stopPendingIntent = serviceActionPendingIntent(context, 12, stopIntent);

        // ---- Progress + text ----------------------------------------------------------
        int totalSec = (int) Math.max(1, Math.round(totalDurationMs / 1000.0));
        long secLeft = (long) Math.max(0, Math.ceil(remainingMs / 1000.0));
        int elapsedSec = (int) Math.max(0, Math.min(totalSec, totalSec - secLeft));
        String mmss = String.format("%02d:%02d", secLeft / 60, secLeft % 60);
        String safeTitle = (title != null && !title.isEmpty()) ? title : "Recupero in corso";

        if (!isPaused) {
            long now = System.currentTimeMillis();
            if (targetEndTime > now) {
                builder.setContentText(safeTitle)
                       .setSubText(mmss)
                       .setUsesChronometer(true)
                       .setChronometerCountDown(true)
                       .setWhen(targetEndTime)
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
                   .setContentText(String.format("In Pausa • %s", safeTitle));
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

        builder.addAction(playPauseIcon, playPauseText, playPausePendingIntent);
        builder.addAction(android.R.drawable.ic_input_add, "+30s", addTimePendingIntent);
        builder.addAction(android.R.drawable.ic_menu_close_clear_cancel, "Stop", stopPendingIntent);

        // Status-bar chip fallback text (chronometer wins when running).
        requestPromotedOngoing(builder, context, isPaused ? ("Pausa " + mmss) : mmss);

        // Xiaomi HyperOS focus / Super Island payload.
        float ratio = totalDurationMs > 0 ? (float) remainingMs / (float) totalDurationMs : 0f;
        HyperFocusExtras.applyRestFocus(builder, context, ratio, targetEndTime, secLeft, isPaused,
                title, ACCENT);

        return builder.build();
    }

    // ----------------------------------------------------------------------------------
    // Workout progress
    // ----------------------------------------------------------------------------------

    public static Notification buildWorkoutNotification(
            Context context,
            String title,
            String currentExerciseName,
            int completedSets,
            int totalSets,
            int[] slotBoundaries,
            long startedAt,
            Bitmap appIconBitmap
    ) {
        Intent appIntent = new Intent(context, MainActivity.class);
        appIntent.setFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP | Intent.FLAG_ACTIVITY_CLEAR_TOP);
        appIntent.putExtra("open_workout", true);
        PendingIntent contentPendingIntent = PendingIntent.getActivity(
                context,
                NOTIFICATION_ID_WORKOUT,
                appIntent,
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE
        );

        NotificationCompat.Builder builder = new NotificationCompat.Builder(context, CHANNEL_WORKOUT)
                .setSmallIcon(R.drawable.ic_stat_onyx)
                .setColor(ACCENT)
                .setColorized(false)
                .setContentIntent(contentPendingIntent)
                .setOngoing(true)
                .setOnlyAlertOnce(true)
                .setCategory(NotificationCompat.CATEGORY_WORKOUT)
                .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
                .setPriority(NotificationCompat.PRIORITY_DEFAULT)
                .setDefaults(0)
                .setSilent(true);

        if (appIconBitmap != null) {
            builder.setLargeIcon(appIconBitmap);
        }

        builder.setContentTitle("ONYX");

        int safeTotal = Math.max(1, totalSets);
        int safeCompleted = Math.max(0, Math.min(safeTotal, completedSets));
        float ratio = (float) safeCompleted / (float) safeTotal;

        builder.setSubText(safeCompleted + "/" + safeTotal + " serie");
        if (currentExerciseName != null && !currentExerciseName.trim().isEmpty()) {
            builder.setContentText(currentExerciseName);
        } else {
            builder.setContentText(title != null && !title.isEmpty() ? title : "Sessione di Allenamento");
        }

        // Pre-16 progress bar fallback.
        builder.setProgress(safeTotal, safeCompleted, false);

        if (startedAt > 0) {
            builder.setWhen(startedAt);
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

        requestPromotedOngoing(builder, context, safeCompleted + "/" + safeTotal);

        HyperFocusExtras.applyWorkoutFocus(builder, context, ratio, safeCompleted, safeTotal,
                title, currentExerciseName, startedAt, ACCENT);

        return builder.build();
    }

    /**
     * Bare-bones silent notification used only to satisfy the startForeground()
     * obligation when a cold-recreated service is handed an action (PAUSE / RESUME /
     * +30s / STOP_ALARM) but has no live state left to display. The caller posts it
     * and then immediately tears the service down.
     */
    public static Notification buildMinimalAnchor(Context context) {
        return new NotificationCompat.Builder(context, CHANNEL_WORKOUT)
                .setSmallIcon(R.drawable.ic_stat_onyx)
                .setContentTitle("Onyx")
                .setPriority(NotificationCompat.PRIORITY_MIN)
                .setCategory(NotificationCompat.CATEGORY_SERVICE)
                .setSilent(true)
                .setOngoing(false)
                .build();
    }

    public static Notification buildAlarmNotification(
            Context context,
            Bitmap appIconBitmap
    ) {
        Intent appIntent = new Intent(context, MainActivity.class);
        appIntent.setFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP | Intent.FLAG_ACTIVITY_CLEAR_TOP);
        appIntent.putExtra("open_timer", true);
        PendingIntent contentPendingIntent = PendingIntent.getActivity(
                context,
                NOTIFICATION_ID_ALARM,
                appIntent,
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE
        );

        Intent stopAlarmIntent = new Intent(context, OnyxLiveService.class);
        stopAlarmIntent.setAction(OnyxLiveService.ACTION_STOP_ALARM);
        PendingIntent stopAlarmPendingIntent = serviceActionPendingIntent(context, 2, stopAlarmIntent);

        NotificationCompat.Builder alarmBuilder = new NotificationCompat.Builder(context, CHANNEL_ALARM)
                .setSmallIcon(R.drawable.ic_stat_onyx)
                .setColor(ACCENT)
                // Full lime card, black auto-contrast text — mirrors the in-app yellow notch.
                .setColorized(true)
                .setContentTitle("TEMPO SCADUTO!")
                .setContentText("Il recupero è terminato. Tocca per disattivare l'allarme.")
                .setStyle(new NotificationCompat.BigTextStyle()
                        .setBigContentTitle("TEMPO SCADUTO!")
                        .bigText("Il recupero è terminato. Tocca per disattivare l'allarme."))
                .setContentIntent(contentPendingIntent)
                .setFullScreenIntent(contentPendingIntent, true)
                .setOngoing(true)
                .setUsesChronometer(false)
                .setShowWhen(false)
                .setCategory(NotificationCompat.CATEGORY_ALARM)
                .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
                .setPriority(NotificationCompat.PRIORITY_MAX)
                .addAction(android.R.drawable.ic_lock_power_off, "DISATTIVA ALLARME", stopAlarmPendingIntent);

        if (appIconBitmap != null) {
            alarmBuilder.setLargeIcon(appIconBitmap);
        }

        // The "time's up" alarm is always prominent — even if the app is in the
        // foreground — so it bypasses the appInForeground suppression above.
        try {
            alarmBuilder.setRequestPromotedOngoing(true);
            alarmBuilder.setShortCriticalText("Scaduto");
        } catch (Throwable t) {
            Log.d(TAG, "alarm promoted-ongoing skipped: " + t.getMessage());
        }
        HyperFocusExtras.applyAlarmFocus(alarmBuilder, context, ACCENT);

        return alarmBuilder.build();
    }
}
