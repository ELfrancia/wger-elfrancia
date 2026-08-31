package com.onyx.workoutapp;

import android.content.Context;
import android.content.Intent;
import android.os.Build;
import android.util.Log;
import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;

@CapacitorPlugin(name = "WorkoutTimer")
public class WorkoutTimerPlugin extends Plugin {

    private static final String TAG = "OnyxDebug";
    private static WorkoutTimerPlugin instance;

    @Override
    public void load() {
        super.load();
        instance = this;
    }

    @PluginMethod
    public void startTimer(PluginCall call) {
        int durationSeconds = call.getInt("durationSeconds", 45);
        String title = call.getString("title", "Recupero in corso");
        String soundUri = call.getString("soundUri", null);

        Log.d(TAG, "WorkoutTimerPlugin.startTimer: duration=" + durationSeconds + "s, title=" + title);
        Context context = getContext();
        Intent serviceIntent = new Intent(context, TimerService.class);
        serviceIntent.setAction(TimerService.ACTION_START);
        serviceIntent.putExtra(TimerService.EXTRA_DURATION, durationSeconds);
        serviceIntent.putExtra(TimerService.EXTRA_TITLE, title);
        if (soundUri != null && !soundUri.isEmpty()) {
            serviceIntent.putExtra(TimerService.EXTRA_SOUND_URI, soundUri);
        }

        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                context.startForegroundService(serviceIntent);
            } else {
                context.startService(serviceIntent);
            }
            call.resolve();
        } catch (Exception e) {
            Log.e(TAG, "WorkoutTimerPlugin failed to start timer: " + e.getMessage(), e);
            call.reject("Failed to start timer service: " + e.getMessage(), e);
        }
    }

    @PluginMethod
    public void pauseTimer(PluginCall call) {
        try {
            Context context = getContext();
            Intent serviceIntent = new Intent(context, TimerService.class);
            serviceIntent.setAction(TimerService.ACTION_PAUSE);
            context.startService(serviceIntent);
            call.resolve();
        } catch (Exception e) {
            Log.e(TAG, "WorkoutTimerPlugin failed to pause timer: " + e.getMessage(), e);
            call.reject("Failed to pause timer: " + e.getMessage(), e);
        }
    }

    @PluginMethod
    public void resumeTimer(PluginCall call) {
        try {
            Context context = getContext();
            Intent serviceIntent = new Intent(context, TimerService.class);
            serviceIntent.setAction(TimerService.ACTION_RESUME);
            context.startService(serviceIntent);
            call.resolve();
        } catch (Exception e) {
            Log.e(TAG, "WorkoutTimerPlugin failed to resume timer: " + e.getMessage(), e);
            call.reject("Failed to resume timer: " + e.getMessage(), e);
        }
    }

    @PluginMethod
    public void addSeconds(PluginCall call) {
        try {
            Context context = getContext();
            Intent serviceIntent = new Intent(context, TimerService.class);
            serviceIntent.setAction(TimerService.ACTION_ADD_TIME);
            context.startService(serviceIntent);
            call.resolve();
        } catch (Exception e) {
            Log.e(TAG, "WorkoutTimerPlugin failed to add seconds: " + e.getMessage(), e);
            call.reject("Failed to add seconds: " + e.getMessage(), e);
        }
    }

    @PluginMethod
    public void stopTimer(PluginCall call) {
        stopTimerService();
        call.resolve();
    }

    @PluginMethod
    public void stopAlarm(PluginCall call) {
        try {
            Context context = getContext();
            Intent serviceIntent = new Intent(context, TimerService.class);
            serviceIntent.setAction(TimerService.ACTION_STOP_ALARM);
            context.startService(serviceIntent);
            call.resolve();
        } catch (Exception e) {
            Log.e(TAG, "WorkoutTimerPlugin failed to stop alarm: " + e.getMessage(), e);
            call.reject("Failed to stop alarm: " + e.getMessage(), e);
        }
    }

    private void stopTimerService() {
        try {
            Context context = getContext();
            Intent serviceIntent = new Intent(context, TimerService.class);
            serviceIntent.setAction(TimerService.ACTION_STOP);
            context.startService(serviceIntent);
        } catch (Exception e) {
            Log.e(TAG, "WorkoutTimerPlugin failed to stop timer service: " + e.getMessage(), e);
        }
    }

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
}

