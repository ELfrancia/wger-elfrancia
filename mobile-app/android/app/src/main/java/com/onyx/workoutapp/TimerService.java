package com.onyx.workoutapp;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
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
import android.os.Bundle;
import android.os.CountDownTimer;
import android.os.IBinder;
import android.os.PowerManager;
import android.os.VibrationEffect;
import android.os.Vibrator;
import android.os.VibratorManager;
import android.util.Log;
import androidx.annotation.Nullable;
import androidx.core.app.NotificationCompat;

public class TimerService extends Service {

    private static final String TAG = "OnyxDebug";

    public static final String ACTION_START = "com.onyx.workoutapp.ACTION_START";
    public static final String ACTION_STOP = "com.onyx.workoutapp.ACTION_STOP";
    public static final String ACTION_PAUSE = "com.onyx.workoutapp.ACTION_PAUSE";
    public static final String ACTION_RESUME = "com.onyx.workoutapp.ACTION_RESUME";
    public static final String ACTION_ADD_TIME = "com.onyx.workoutapp.ACTION_ADD_TIME";
    public static final String ACTION_STOP_ALARM = "com.onyx.workoutapp.ACTION_STOP_ALARM";

    public static final String EXTRA_DURATION = "extra_duration_seconds";
    public static final String EXTRA_TITLE = "extra_title";
    public static final String EXTRA_SOUND_URI = "extra_sound_uri";

    private static final String CHANNEL_TIMER = "onyx_timer_live_channel";
    private static final String CHANNEL_ALARM = "onyx_timer_alarm_channel";
    private static final int NOTIFICATION_ID_TIMER = 1001;
    private static final int NOTIFICATION_ID_ALARM = 1002;

    private NotificationManager notificationManager;
    private CountDownTimer countDownTimer;
    private MediaPlayer mediaPlayer;
    private Vibrator vibrator;
    private AudioManager audioManager;
    private AudioFocusRequest audioFocusRequest;
    private PowerManager.WakeLock wakeLock;

    private boolean isAlarmPlaying = false;
    private boolean isTimerRunning = false;
    private boolean isPaused = false;
    private long remainingTimeMs = 0;
    private long targetEndTimeMs = 0;
    private String currentTitle = "Recupero in corso";
    private String customSoundUri = null;
    private Bitmap appIconBitmap;

    @Override
    public void onCreate() {
        super.onCreate();
        notificationManager = (NotificationManager) getSystemService(Context.NOTIFICATION_SERVICE);
        audioManager = (AudioManager) getSystemService(Context.AUDIO_SERVICE);

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

        createNotificationChannels();
    }

    private void createNotificationChannels() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            // Live countdown channel
            NotificationChannel timerChannel = new NotificationChannel(
                    CHANNEL_TIMER,
                    "Timer Recupero Live",
                    NotificationManager.IMPORTANCE_HIGH
            );
            timerChannel.setDescription("Mostra il countdown di recupero in corso nella barra di stato");
            timerChannel.setSound(null, null);
            timerChannel.enableVibration(false);
            timerChannel.setShowBadge(true);
            timerChannel.setLockscreenVisibility(Notification.VISIBILITY_PUBLIC);
            notificationManager.createNotificationChannel(timerChannel);

            // Alarm channel (High importance with custom vibration, sound managed directly)
            NotificationChannel alarmChannel = new NotificationChannel(
                    CHANNEL_ALARM,
                    "Allarme Timer Esaurito",
                    NotificationManager.IMPORTANCE_HIGH
            );
            alarmChannel.setDescription("Allarme sonoro a ciclo continuo al termine del recupero");
            alarmChannel.setSound(null, null);
            alarmChannel.enableVibration(true);
            alarmChannel.setShowBadge(true);
            alarmChannel.setLockscreenVisibility(Notification.VISIBILITY_PUBLIC);
            notificationManager.createNotificationChannel(alarmChannel);
        }
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        if (intent == null || intent.getAction() == null) {
            return START_NOT_STICKY;
        }

        String action = intent.getAction();
        Log.d(TAG, "TimerService onStartCommand: action=" + action);

        if (ACTION_START.equals(action)) {
            int durationSeconds = intent.getIntExtra(EXTRA_DURATION, 45);
            String title = intent.getStringExtra(EXTRA_TITLE);
            String soundUri = intent.getStringExtra(EXTRA_SOUND_URI);
            if (title == null || title.isEmpty()) {
                title = "Recupero in corso";
            }
            this.customSoundUri = soundUri;
            startTimerCountdown(durationSeconds, title);
        } else if (ACTION_PAUSE.equals(action)) {
            pauseTimer();
        } else if (ACTION_RESUME.equals(action)) {
            resumeTimer();
        } else if (ACTION_ADD_TIME.equals(action)) {
            addSecondsToTimer(30);
        } else if (ACTION_STOP.equals(action)) {
            stopRestTimer();
        } else if (ACTION_STOP_ALARM.equals(action)) {
            stopAlarmOnly();
            if (!isTimerRunning) {
                stopTimerAndService();
            }
        }

        return START_NOT_STICKY;
    }

    private synchronized void stopRestTimer() {
        Log.d(TAG, "TimerService: Stopping rest countdown");
        if (countDownTimer != null) {
            countDownTimer.cancel();
            countDownTimer = null;
        }
        isTimerRunning = false;
        isPaused = false;
        remainingTimeMs = 0;
        stopAlarmOnly();
        stopTimerAndService();
    }

    private synchronized void startTimerCountdown(int durationSeconds, String title) {
        Log.d(TAG, "TimerService: Starting/Updating countdown for " + durationSeconds + " seconds (title=" + title + ")");
        
        stopAlarmOnly();
        if (notificationManager != null) {
            notificationManager.cancel(NOTIFICATION_ID_ALARM);
        }

        if (countDownTimer != null) {
            countDownTimer.cancel();
            countDownTimer = null;
        }

        this.currentTitle = title;
        this.remainingTimeMs = durationSeconds * 1000L;
        this.targetEndTimeMs = System.currentTimeMillis() + remainingTimeMs;
        this.isTimerRunning = true;
        this.isPaused = false;

        acquireWakeLock();
        updateNotificationAndForeground();

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
        updateNotificationAndForeground();
        WorkoutTimerPlugin.notifyTimerPaused();
    }

    private synchronized void resumeTimer() {
        if (!isTimerRunning || !isPaused) return;
        targetEndTimeMs = System.currentTimeMillis() + remainingTimeMs;
        isPaused = false;
        updateNotificationAndForeground();
        startInternalCountDown(remainingTimeMs);
        WorkoutTimerPlugin.notifyTimerResumed();
    }

    private synchronized void addSecondsToTimer(int extraSeconds) {
        if (!isTimerRunning) return;
        long currentLeft = isPaused ? remainingTimeMs : Math.max(0, targetEndTimeMs - System.currentTimeMillis());
        long newTotalMs = currentLeft + (extraSeconds * 1000L);
        startTimerCountdown((int) (newTotalMs / 1000), currentTitle);
    }

    private void startInternalCountDown(long durationMs) {
        countDownTimer = new CountDownTimer(durationMs, 500) {
            @Override
            public void onTick(long millisUntilFinished) {
                remainingTimeMs = millisUntilFinished;
            }

            @Override
            public void onFinish() {
                Log.d(TAG, "TimerService: CountDown finished! Triggering alarm now.");
                isTimerRunning = false;
                isPaused = false;
                remainingTimeMs = 0;
                triggerTimerFinishedAlarm();
            }
        }.start();
    }

    private void updateNotificationAndForeground() {
        Notification notification = buildLiveTimerNotification(targetEndTimeMs, currentTitle);
        try {
            if (Build.VERSION.SDK_INT >= 34) {
                startForeground(NOTIFICATION_ID_TIMER, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE);
            } else if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                startForeground(NOTIFICATION_ID_TIMER, notification, 0);
            } else {
                startForeground(NOTIFICATION_ID_TIMER, notification);
            }
            if (notificationManager != null) {
                notificationManager.notify(NOTIFICATION_ID_TIMER, notification);
            }
        } catch (Exception e) {
            Log.e(TAG, "Error posting foreground notification: " + e.getMessage(), e);
        }
    }

    private Notification buildLiveTimerNotification(long targetEndTime, String title) {
        Intent appIntent = new Intent(this, MainActivity.class);
        appIntent.setFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP | Intent.FLAG_ACTIVITY_CLEAR_TOP);
        appIntent.putExtra("open_timer", true);
        PendingIntent contentPendingIntent = PendingIntent.getActivity(
                this,
                0,
                appIntent,
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE
        );

        NotificationCompat.Builder builder = new NotificationCompat.Builder(this, CHANNEL_TIMER)
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

        if (isTimerRunning) {
            // MODE 1: Rest countdown is active
            builder.setContentTitle(title != null && !title.isEmpty() ? title : "Recupero in corso");
            
            // Action 1: Play / Pause
            Intent playPauseIntent = new Intent(this, TimerService.class);
            playPauseIntent.setAction(isPaused ? ACTION_RESUME : ACTION_PAUSE);
            PendingIntent playPausePendingIntent = PendingIntent.getService(
                    this,
                    10,
                    playPauseIntent,
                    PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE
            );
            int playPauseIcon = isPaused ? android.R.drawable.ic_media_play : android.R.drawable.ic_media_pause;
            String playPauseText = isPaused ? "Riprendi" : "Pausa";

            // Action 2: +30s
            Intent addTimeIntent = new Intent(this, TimerService.class);
            addTimeIntent.setAction(ACTION_ADD_TIME);
            PendingIntent addTimePendingIntent = PendingIntent.getService(
                    this,
                    11,
                    addTimeIntent,
                    PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE
            );

            // Action 3: Stop / Termina Recupero
            Intent stopIntent = new Intent(this, TimerService.class);
            stopIntent.setAction(ACTION_STOP);
            PendingIntent stopPendingIntent = PendingIntent.getService(
                    this,
                    12,
                    stopIntent,
                    PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE
            );

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
                long secLeft = (long) Math.max(0, Math.ceil(remainingTimeMs / 1000.0));
                long m = secLeft / 60;
                long s = secLeft % 60;
                builder.setContentText(String.format("In Pausa (%02d:%02d)", m, s));
            }

            builder.addAction(playPauseIcon, playPauseText, playPausePendingIntent);
            builder.addAction(android.R.drawable.ic_input_add, "+30s", addTimePendingIntent);
            builder.addAction(android.R.drawable.ic_menu_close_clear_cancel, "Stop", stopPendingIntent);
        }

        return builder.build();
    }

    private synchronized void triggerTimerFinishedAlarm() {
        if (countDownTimer != null) {
            countDownTimer.cancel();
            countDownTimer = null;
        }
        isTimerRunning = false;
        isPaused = false;

        if (notificationManager != null) {
            notificationManager.cancel(NOTIFICATION_ID_TIMER);
        }

        requestExclusiveAudioFocus();
        playLoopingAlarmSound();
        startAlarmVibration();

        Intent appIntent = new Intent(this, MainActivity.class);
        appIntent.setFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP | Intent.FLAG_ACTIVITY_CLEAR_TOP);
        appIntent.putExtra("open_timer", true);
        PendingIntent contentPendingIntent = PendingIntent.getActivity(
                this,
                0,
                appIntent,
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE
        );

        Intent stopAlarmIntent = new Intent(this, TimerService.class);
        stopAlarmIntent.setAction(ACTION_STOP_ALARM);
        PendingIntent stopAlarmPendingIntent = PendingIntent.getService(
                this,
                2,
                stopAlarmIntent,
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE
        );

        NotificationCompat.Builder alarmBuilder = new NotificationCompat.Builder(this, CHANNEL_ALARM)
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

        Notification alarmNotification = alarmBuilder.build();

        try {
            if (Build.VERSION.SDK_INT >= 34) {
                startForeground(NOTIFICATION_ID_ALARM, alarmNotification, ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE);
            } else if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                startForeground(NOTIFICATION_ID_ALARM, alarmNotification, 0);
            } else {
                startForeground(NOTIFICATION_ID_ALARM, alarmNotification);
            }
            if (notificationManager != null) {
                notificationManager.notify(NOTIFICATION_ID_ALARM, alarmNotification);
            }
        } catch (Exception e) {
            Log.e(TAG, "Error posting alarm foreground notification: " + e.getMessage(), e);
        }

        WorkoutTimerPlugin.notifyTimerExpired();
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

    private AudioTrack synthesizedAudioTrack = null;

    private void playLoopingAlarmSound() {
        try {
            stopAlarmSound();

            if ("vibration_only".equalsIgnoreCase(customSoundUri)) {
                Log.d(TAG, "Sound mode: vibration_only");
                return;
            }

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
            isAlarmPlaying = true;
        } catch (Exception e) {
            Log.e(TAG, "Error playing alarm sound: " + e.getMessage(), e);
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
                if (isAlarmPlaying) {
                    synthesizedAudioTrack.play();
                }
            } catch (Exception e) {
                Log.e(TAG, "Error playing synthesized tone: " + e.getMessage(), e);
            }
        }).start();
    }

    private void stopSynthesizedAudioTrack() {
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
                notificationManager.cancel(NOTIFICATION_ID_ALARM);
            } catch (Exception ignored) {}
        }
    }

    private synchronized void stopTimerAndService() {
        isTimerRunning = false;
        isPaused = false;
        if (countDownTimer != null) {
            countDownTimer.cancel();
            countDownTimer = null;
        }
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
            notificationManager.cancel(NOTIFICATION_ID_TIMER);
            notificationManager.cancel(NOTIFICATION_ID_ALARM);
        }
        stopSelf();
        WorkoutTimerPlugin.notifyTimerStopped();
    }

    private void acquireWakeLock() {
        try {
            if (wakeLock == null) {
                PowerManager powerManager = (PowerManager) getSystemService(Context.POWER_SERVICE);
                if (powerManager != null) {
                    wakeLock = powerManager.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "OnyxWorkout::TimerWakeLock");
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
        stopTimerAndService();
        super.onDestroy();
    }

    @Nullable
    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }
}
