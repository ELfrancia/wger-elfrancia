package com.onyx.workoutapp;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.os.Build;
import android.util.Log;

/**
 * Exact-alarm backup for the "rest timer expired" event.
 *
 * <p>On HyperOS / MIUI the OS frequently freezes or kills a foreground service a few
 * seconds after the app is swiped away, so the in-service {@code CountDownTimer} never
 * reaches {@code onFinish()} and the alarm never rings. To make the expiry bullet-proof
 * {@link OnyxLiveService} <em>also</em> schedules an
 * {@code AlarmManager.setExactAndAllowWhileIdle()} for the exact target end time.
 * Whichever fires first wins; the service de-dupes the alarm.
 *
 * <p>This receiver just wakes {@link OnyxLiveService} back up with the
 * {@link #ACTION_TIMER_EXPIRED} action and lets the service decide whether the alarm is
 * still relevant (no-op if the timer was already stopped or already expired).
 */
public class TimerExpiryAlarmReceiver extends BroadcastReceiver {

    private static final String TAG = "OnyxDebug";

    /**
     * Action carried by both the AlarmManager broadcast PendingIntent and the service
     * intent this receiver starts. Kept as a plain literal (not a cross-class constant)
     * so this file compiles independently of the {@link OnyxLiveService} revision.
     */
    public static final String ACTION_TIMER_EXPIRED = "com.onyx.workoutapp.ALARM_TIMER_EXPIRED";

    @Override
    public void onReceive(Context context, Intent intent) {
        Log.d(TAG, "TimerExpiryAlarmReceiver: exact-alarm backup fired");
        try {
            Intent serviceIntent = new Intent(context, OnyxLiveService.class);
            serviceIntent.setAction(ACTION_TIMER_EXPIRED);
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                context.startForegroundService(serviceIntent);
            } else {
                context.startService(serviceIntent);
            }
        } catch (Exception e) {
            Log.e(TAG, "TimerExpiryAlarmReceiver: could not wake OnyxLiveService: " + e.getMessage(), e);
        }
    }
}
