package com.onyx.workoutapp;

import android.content.Context;
import android.os.Bundle;
import android.util.Log;
import android.view.View;
import android.widget.RemoteViews;
import androidx.core.app.NotificationCompat;

public class HyperFocusExtras {

    private static final String TAG = "OnyxDebug";

    /**
     * Applies Xiaomi HyperOS Super Island focus parameters and custom ring RemoteViews to notification builder.
     * All calls are fully wrapped in try/catch to guarantee no-op behavior on unsupported devices.
     */
    public static void applyRing(
            NotificationCompat.Builder builder,
            Context context,
            float ratio,
            String centerText,
            int accentColor,
            boolean isCountdown
    ) {
        if (builder == null || context == null) return;

        try {
            if (!DeviceCapabilities.isXiaomiHyperOs()) {
                return;
            }

            Bundle focusExtras = new Bundle();
            
            // HyperOS Focus notification attributes
            focusExtras.putBoolean("miui.focus.enable", true);
            focusExtras.putInt("miui.focus.type", 1); // Live activity mode
            focusExtras.putInt("miui.focus.version", 1);
            focusExtras.putFloat("miui.focus.progress", Math.max(0.0f, Math.min(1.0f, ratio)));

            // RemoteViews for ring pill icon
            RemoteViews remoteViews = new RemoteViews(context.getPackageName(), R.layout.island_ring);
            int progressVal = Math.round(Math.max(0.0f, Math.min(1.0f, ratio)) * 1000f);
            remoteViews.setProgressBar(R.id.island_ring_progress_bar, 1000, progressVal, false);

            if (centerText != null && !centerText.trim().isEmpty()) {
                remoteViews.setViewVisibility(R.id.island_ring_center_text, View.VISIBLE);
                remoteViews.setTextViewText(R.id.island_ring_center_text, centerText);
            } else {
                remoteViews.setViewVisibility(R.id.island_ring_center_text, View.GONE);
            }

            focusExtras.putParcelable("miui.focus.pic", remoteViews);
            builder.addExtras(focusExtras);
        } catch (Throwable t) {
            Log.d(TAG, "HyperFocusExtras.applyRing skipped gracefully: " + t.getMessage());
        }
    }
}
