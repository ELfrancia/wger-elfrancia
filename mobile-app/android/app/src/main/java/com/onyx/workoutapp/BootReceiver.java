package com.onyx.workoutapp;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.util.Log;

/**
 * Receives BOOT_COMPLETED / MY_PACKAGE_REPLACED.
 *
 * <p>Declaring this receiver is what lets MIUI/HyperOS list the app under
 * "Autostart" — without a boot receiver the toggle is often hidden entirely.
 * We intentionally do <b>not</b> auto-restart a workout/timer after a reboot
 * (a countdown that survived a phone restart is almost never wanted); the hook
 * exists only so the Autostart permission is grantable and future
 * "resume ongoing session" logic has a place to live.
 */
public class BootReceiver extends BroadcastReceiver {

    private static final String TAG = "OnyxDebug";

    @Override
    public void onReceive(Context context, Intent intent) {
        String action = intent != null ? intent.getAction() : null;
        Log.d(TAG, "BootReceiver: received " + action + " (no-op)");
    }
}
