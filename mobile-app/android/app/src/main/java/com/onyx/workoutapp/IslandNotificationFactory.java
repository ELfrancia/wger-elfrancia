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
import java.lang.reflect.Method;

public class IslandNotificationFactory {

    private static final String TAG = "OnyxDebug";

    public static final String CHANNEL_TIMER = "onyx_timer_live_channel";
    public static final String CHANNEL_ALARM = "onyx_timer_alarm_channel";
    public static final String CHANNEL_WORKOUT = "onyx_workout_progress_channel";

    public static final int NOTIFICATION_ID_TIMER = 1001;
    public static final int NOTIFICATION_ID_ALARM = 1002;
    public static final int NOTIFICATION_ID_WORKOUT = 1003;

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

        // 3. Workout progress live activity channel
        NotificationChannel workoutChannel = new NotificationChannel(
                CHANNEL_WORKOUT,
                "Progresso Allenamento Live",
                NotificationManager.IMPORTANCE_LOW
        );
        workoutChannel.setDescription("Mostra l'anello di avanzamento delle serie nella Super Island e barra di stato");
        workoutChannel.setSound(null, null);
        workoutChannel.enableVibration(false);
        workoutChannel.setShowBadge(false);
        workoutChannel.setLockscreenVisibility(Notification.VISIBILITY_PUBLIC);
        notificationManager.createNotificationChannel(workoutChannel);
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

    private static void setPromotedOngoingIfSupported(NotificationCompat.Builder builder, Context context) {
        if (builder == null || context == null) return;
        try {
            if (DeviceCapabilities.canPromoteOngoing(context)) {
                try {
                    Method m = builder.getClass().getMethod("setRequestPromotedOngoing", boolean.class);
                    m.invoke(builder, true);
                } catch (NoSuchMethodException ignored) {
                    // Method not available in this exact core version, fallback to setOngoing
                    builder.setOngoing(true);
                }
            }
        } catch (Throwable t) {
            Log.d(TAG, "setPromotedOngoing skipped: " + t.getMessage());
        }
    }

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
                .setSmallIcon(R.mipmap.ic_launcher)
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

        setPromotedOngoingIfSupported(builder, context);

        builder.setContentTitle(title != null && !title.isEmpty() ? title : "Recupero in corso");

        // Action 1: Play / Pause
        Intent playPauseIntent = new Intent(context, OnyxLiveService.class);
        playPauseIntent.setAction(isPaused ? OnyxLiveService.ACTION_RESUME : OnyxLiveService.ACTION_PAUSE);
        PendingIntent playPausePendingIntent = serviceActionPendingIntent(context, 10, playPauseIntent);
        int playPauseIcon = isPaused ? android.R.drawable.ic_media_play : android.R.drawable.ic_media_pause;
        String playPauseText = isPaused ? "Riprendi" : "Pausa";

        // Action 2: +30s
        Intent addTimeIntent = new Intent(context, OnyxLiveService.class);
        addTimeIntent.setAction(OnyxLiveService.ACTION_ADD_TIME);
        PendingIntent addTimePendingIntent = serviceActionPendingIntent(context, 11, addTimeIntent);

        // Action 3: Stop
        Intent stopIntent = new Intent(context, OnyxLiveService.class);
        stopIntent.setAction(OnyxLiveService.ACTION_STOP);
        PendingIntent stopPendingIntent = serviceActionPendingIntent(context, 12, stopIntent);

        float ratio = totalDurationMs > 0 ? (float) remainingMs / (float) totalDurationMs : 0f;
        ratio = Math.max(0.0f, Math.min(1.0f, ratio));

        if (!isPaused) {
            long now = System.currentTimeMillis();
            if (targetEndTime > now) {
                builder.setContentText("Tocca per aprire")
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
            builder.setUsesChronometer(false);
            builder.setShowWhen(false);
            long secLeft = (long) Math.max(0, Math.ceil(remainingMs / 1000.0));
            long m = secLeft / 60;
            long s = secLeft % 60;
            builder.setContentText(String.format("In Pausa (%02d:%02d)", m, s));
        }

        builder.addAction(playPauseIcon, playPauseText, playPausePendingIntent);
        builder.addAction(android.R.drawable.ic_input_add, "+30s", addTimePendingIntent);
        builder.addAction(android.R.drawable.ic_menu_close_clear_cancel, "Stop", stopPendingIntent);

        // Apply HyperOS ring
        HyperFocusExtras.applyRing(builder, context, ratio, null, 0xFFCAF300, true);

        return builder.build();
    }

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
                .setSmallIcon(R.mipmap.ic_launcher)
                .setContentIntent(contentPendingIntent)
                .setOngoing(true)
                .setOnlyAlertOnce(true)
                .setCategory(NotificationCompat.CATEGORY_WORKOUT)
                .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
                .setPriority(NotificationCompat.PRIORITY_LOW)
                .setDefaults(0)
                .setSilent(true);

        if (appIconBitmap != null) {
            builder.setLargeIcon(appIconBitmap);
        }

        setPromotedOngoingIfSupported(builder, context);

        builder.setContentTitle(title != null && !title.isEmpty() ? title : "Sessione di Allenamento");

        int safeTotal = Math.max(1, totalSets);
        int safeCompleted = Math.max(0, Math.min(safeTotal, completedSets));
        float ratio = (float) safeCompleted / (float) safeTotal;

        // Expanded view shows current exercise name (Decision D4)
        if (currentExerciseName != null && !currentExerciseName.trim().isEmpty()) {
            builder.setContentText(currentExerciseName);
            builder.setSubText(safeCompleted + "/" + safeTotal + " serie");
        } else {
            builder.setContentText(safeCompleted + "/" + safeTotal + " serie completate");
        }

        builder.setProgress(safeTotal, safeCompleted, false);

        if (startedAt > 0) {
            builder.setWhen(startedAt);
            builder.setShowWhen(true);
            builder.setUsesChronometer(true);
            builder.setChronometerCountDown(false);
        }

        // Apply HyperOS ring (centerText empty -> pure circle ring per Decision D4)
        HyperFocusExtras.applyRing(builder, context, ratio, "", 0xFFCAF300, false);

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
                .setSmallIcon(R.mipmap.ic_launcher)
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
                .setSmallIcon(R.mipmap.ic_launcher)
                .setContentTitle("TEMPO SCADUTO! 🏋️")
                .setContentText("Il recupero è terminato. Tocca per disattivare l'allarme.")
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

        return alarmBuilder.build();
    }
}
