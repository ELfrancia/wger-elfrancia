package com.onyx.workoutapp;

import android.app.NotificationManager;
import android.content.Context;
import android.content.Intent;
import android.os.Build;
import android.service.notification.StatusBarNotification;
import android.util.Log;
import com.getcapacitor.JSArray;
import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;
import java.util.Map;
import org.json.JSONArray;
import org.json.JSONException;

@CapacitorPlugin(name = "WorkoutTimer")
public class OnyxLivePlugin extends Plugin {

    private static final String TAG = "OnyxDebug";
    private static OnyxLivePlugin instance;

    @Override
    public void load() {
        super.load();
        instance = this;
    }

    // ==========================================
    // REST TIMER METHODS
    // ==========================================

    @PluginMethod
    public void startTimer(PluginCall call) {
        int durationSeconds = call.getInt("durationSeconds", 45);
        String title = call.getString("title", "Recupero in corso");
        String soundUri = call.getString("soundUri", null);

        Log.d(TAG, "OnyxLivePlugin.startTimer: duration=" + durationSeconds + "s, title=" + title);
        Context context = getContext();
        Intent serviceIntent = new Intent(context, OnyxLiveService.class);
        serviceIntent.setAction(OnyxLiveService.ACTION_START);
        serviceIntent.putExtra(OnyxLiveService.EXTRA_DURATION, durationSeconds);
        serviceIntent.putExtra(OnyxLiveService.EXTRA_TITLE, title);
        if (soundUri != null && !soundUri.isEmpty()) {
            serviceIntent.putExtra(OnyxLiveService.EXTRA_SOUND_URI, soundUri);
        }

        try {
            startLiveService(context, serviceIntent);
            call.resolve();
        } catch (Exception e) {
            Log.e(TAG, "OnyxLivePlugin failed to start timer: " + e.getMessage(), e);
            call.reject("Failed to start timer service: " + e.getMessage(), e);
        }
    }

    @PluginMethod
    public void updateTimer(PluginCall call) {
        int durationSeconds = call.getInt("durationSeconds", 45);
        int remainingSeconds = call.getInt("remainingSeconds", durationSeconds);
        try {
            Context context = getContext();
            Intent serviceIntent = new Intent(context, OnyxLiveService.class);
            serviceIntent.setAction(OnyxLiveService.ACTION_UPDATE_TIMER);
            serviceIntent.putExtra(OnyxLiveService.EXTRA_DURATION, durationSeconds);
            serviceIntent.putExtra(OnyxLiveService.EXTRA_REMAINING_SECONDS, remainingSeconds);
            startLiveService(context, serviceIntent);
            call.resolve();
        } catch (Exception e) {
            Log.e(TAG, "OnyxLivePlugin failed to update timer: " + e.getMessage(), e);
            call.reject("Failed to update timer: " + e.getMessage(), e);
        }
    }

    @PluginMethod
    public void updateNotification(PluginCall call) {
        updateTimer(call);
    }

    @PluginMethod
    public void pauseTimer(PluginCall call) {
        try {
            Context context = getContext();
            Intent serviceIntent = new Intent(context, OnyxLiveService.class);
            serviceIntent.setAction(OnyxLiveService.ACTION_PAUSE);
            startLiveService(context, serviceIntent);
            call.resolve();
        } catch (Exception e) {
            Log.e(TAG, "OnyxLivePlugin failed to pause timer: " + e.getMessage(), e);
            call.reject("Failed to pause timer: " + e.getMessage(), e);
        }
    }

    @PluginMethod
    public void resumeTimer(PluginCall call) {
        try {
            Context context = getContext();
            Intent serviceIntent = new Intent(context, OnyxLiveService.class);
            serviceIntent.setAction(OnyxLiveService.ACTION_RESUME);
            startLiveService(context, serviceIntent);
            call.resolve();
        } catch (Exception e) {
            Log.e(TAG, "OnyxLivePlugin failed to resume timer: " + e.getMessage(), e);
            call.reject("Failed to resume timer: " + e.getMessage(), e);
        }
    }

    @PluginMethod
    public void addSeconds(PluginCall call) {
        int seconds = call.getInt("seconds", 30);
        try {
            Context context = getContext();
            Intent serviceIntent = new Intent(context, OnyxLiveService.class);
            serviceIntent.setAction(OnyxLiveService.ACTION_ADD_TIME);
            serviceIntent.putExtra(OnyxLiveService.EXTRA_DURATION, seconds);
            startLiveService(context, serviceIntent);
            call.resolve();
        } catch (Exception e) {
            Log.e(TAG, "OnyxLivePlugin failed to add seconds: " + e.getMessage(), e);
            call.reject("Failed to add seconds: " + e.getMessage(), e);
        }
    }

    @PluginMethod
    public void stopTimer(PluginCall call) {
        try {
            Context context = getContext();
            Intent serviceIntent = new Intent(context, OnyxLiveService.class);
            serviceIntent.setAction(OnyxLiveService.ACTION_STOP);
            startLiveService(context, serviceIntent);
            call.resolve();
        } catch (Exception e) {
            Log.e(TAG, "OnyxLivePlugin failed to stop timer: " + e.getMessage(), e);
            call.reject("Failed to stop timer: " + e.getMessage(), e);
        }
    }

    @PluginMethod
    public void stopAlarm(PluginCall call) {
        try {
            Context context = getContext();
            Intent serviceIntent = new Intent(context, OnyxLiveService.class);
            serviceIntent.setAction(OnyxLiveService.ACTION_STOP_ALARM);
            startLiveService(context, serviceIntent);
            call.resolve();
        } catch (Exception e) {
            Log.e(TAG, "OnyxLivePlugin failed to stop alarm: " + e.getMessage(), e);
            call.reject("Failed to stop alarm: " + e.getMessage(), e);
        }
    }


    // ==========================================
    // WORKOUT ISLAND METHODS (Android 16 / HyperOS)
    // ==========================================

    @PluginMethod
    public void startWorkoutIsland(PluginCall call) {
        String title = call.getString("title", "Sessione di Allenamento");
        int totalSets = call.getInt("totalSets", 0);
        int completedSets = call.getInt("completedSets", 0);
        String currentExerciseName = call.getString("currentExerciseName", "");
        long startedAt = call.getLong("startedAt", System.currentTimeMillis());

        int[] slotBoundaries = null;
        JSArray boundariesArr = call.getArray("slotBoundaries", null);
        if (boundariesArr != null) {
            slotBoundaries = new int[boundariesArr.length()];
            for (int i = 0; i < boundariesArr.length(); i++) {
                slotBoundaries[i] = boundariesArr.optInt(i, 0);
            }
        }

        Log.d(TAG, "OnyxLivePlugin.startWorkoutIsland: title=" + title + ", totalSets=" + totalSets + ", completed=" + completedSets + ", currentExercise=" + currentExerciseName);

        Context context = getContext();
        Intent serviceIntent = new Intent(context, OnyxLiveService.class);
        serviceIntent.setAction(OnyxLiveService.ACTION_WORKOUT_START);
        serviceIntent.putExtra(OnyxLiveService.EXTRA_TITLE, title);
        serviceIntent.putExtra(OnyxLiveService.EXTRA_TOTAL_SETS, totalSets);
        serviceIntent.putExtra(OnyxLiveService.EXTRA_COMPLETED_SETS, completedSets);
        serviceIntent.putExtra(OnyxLiveService.EXTRA_CURRENT_EXERCISE, currentExerciseName);
        serviceIntent.putExtra(OnyxLiveService.EXTRA_STARTED_AT, startedAt);
        if (slotBoundaries != null) {
            serviceIntent.putExtra(OnyxLiveService.EXTRA_SLOT_BOUNDARIES, slotBoundaries);
        }

        try {
            startLiveService(context, serviceIntent);
            call.resolve();
        } catch (Exception e) {
            Log.e(TAG, "OnyxLivePlugin failed to start workout island: " + e.getMessage(), e);
            call.reject("Failed to start workout island: " + e.getMessage(), e);
        }
    }

    @PluginMethod
    public void updateWorkoutIsland(PluginCall call) {
        int totalSets = call.getInt("totalSets", 0);
        int completedSets = call.getInt("completedSets", 0);
        String currentExerciseName = call.getString("currentExerciseName", null);

        Log.d(TAG, "OnyxLivePlugin.updateWorkoutIsland: totalSets=" + totalSets + ", completed=" + completedSets + ", currentExercise=" + currentExerciseName);

        Context context = getContext();
        Intent serviceIntent = new Intent(context, OnyxLiveService.class);
        serviceIntent.setAction(OnyxLiveService.ACTION_WORKOUT_UPDATE);
        serviceIntent.putExtra(OnyxLiveService.EXTRA_TOTAL_SETS, totalSets);
        serviceIntent.putExtra(OnyxLiveService.EXTRA_COMPLETED_SETS, completedSets);
        if (currentExerciseName != null) {
            serviceIntent.putExtra(OnyxLiveService.EXTRA_CURRENT_EXERCISE, currentExerciseName);
        }

        try {
            context.startService(serviceIntent);
            call.resolve();
        } catch (Exception e) {
            Log.e(TAG, "OnyxLivePlugin failed to update workout island: " + e.getMessage(), e);
            call.reject("Failed to update workout island: " + e.getMessage(), e);
        }
    }

    @PluginMethod
    public void stopWorkoutIsland(PluginCall call) {
        Log.d(TAG, "OnyxLivePlugin.stopWorkoutIsland called");
        try {
            Context context = getContext();
            Intent serviceIntent = new Intent(context, OnyxLiveService.class);
            serviceIntent.setAction(OnyxLiveService.ACTION_WORKOUT_STOP);
            context.startService(serviceIntent);
            call.resolve();
        } catch (Exception e) {
            Log.e(TAG, "OnyxLivePlugin failed to stop workout island: " + e.getMessage(), e);
            call.reject("Failed to stop workout island: " + e.getMessage(), e);
        }
    }

    @PluginMethod
    public void getCapabilities(PluginCall call) {
        try {
            Map<String, Object> capsMap = DeviceCapabilities.getCapabilitiesMap(getContext());
            JSObject res = new JSObject();
            for (Map.Entry<String, Object> entry : capsMap.entrySet()) {
                res.put(entry.getKey(), entry.getValue());
            }
            call.resolve(res);
        } catch (Exception e) {
            call.reject("Failed to query device capabilities: " + e.getMessage(), e);
        }
    }

    @PluginMethod
    public void hasActiveOngoingNotification(PluginCall call) {
        JSObject ret = new JSObject();
        boolean active = OnyxLiveService.hasActiveOngoingNotification();
        if (!active) {
            try {
                NotificationManager nm = (NotificationManager) getContext().getSystemService(Context.NOTIFICATION_SERVICE);
                if (nm != null) {
                    StatusBarNotification[] notifications = nm.getActiveNotifications();
                    if (notifications != null) {
                        for (StatusBarNotification sbn : notifications) {
                            int id = sbn.getId();
                            if ((id == IslandNotificationFactory.NOTIFICATION_ID_TIMER || id == IslandNotificationFactory.NOTIFICATION_ID_WORKOUT) && sbn.isOngoing()) {
                                active = true;
                                break;
                            }
                        }
                    }
                }
            } catch (Throwable ignored) {}
        }
        ret.put("value", active);
        call.resolve(ret);
    }

    private void startLiveService(Context context, Intent intent) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            context.startForegroundService(intent);
        } else {
            context.startService(intent);
        }
    }

    // ==========================================
    // EVENT NOTIFIERS
    // ==========================================

    public static void notifyTimerExpired() {
        if (instance != null) {
            JSObject ret = new JSObject();
            ret.put("event", "timerExpired");
            instance.notifyListeners("onTimerExpired", ret);
        }
    }

    public static void notifyTimerStopped() {
        if (instance != null) {
            JSObject ret = new JSObject();
            ret.put("event", "timerStopped");
            instance.notifyListeners("onTimerStopped", ret);
        }
    }

    public static void notifyTimerPaused() {
        if (instance != null) {
            JSObject ret = new JSObject();
            ret.put("event", "timerPaused");
            instance.notifyListeners("onTimerPaused", ret);
        }
    }

    public static void notifyTimerResumed() {
        if (instance != null) {
            JSObject ret = new JSObject();
            ret.put("event", "timerResumed");
            instance.notifyListeners("onTimerResumed", ret);
        }
    }

    public static void notifyWorkoutIslandTapped() {
        if (instance != null) {
            JSObject ret = new JSObject();
            ret.put("event", "workoutIslandTapped");
            instance.notifyListeners("onWorkoutIslandTapped", ret);
        }
    }
}
