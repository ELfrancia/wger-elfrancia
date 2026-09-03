package com.onyx.workoutapp;

import android.content.Context;
import android.os.Build;
import android.os.PowerManager;
import android.util.Log;

import androidx.core.app.NotificationManagerCompat;

import java.lang.reflect.Method;
import java.util.HashMap;
import java.util.Map;

public class DeviceCapabilities {

    private static final String TAG = "OnyxDebug";

    public static boolean isAndroid16Plus() {
        return Build.VERSION.SDK_INT >= 36;
    }

    public static boolean isXiaomiHyperOs() {
        String manufacturer = Build.MANUFACTURER != null ? Build.MANUFACTURER.toLowerCase() : "";
        String brand = Build.BRAND != null ? Build.BRAND.toLowerCase() : "";

        if (manufacturer.contains("xiaomi") || manufacturer.contains("poco") || manufacturer.contains("redmi") ||
            brand.contains("xiaomi") || brand.contains("poco") || brand.contains("redmi")) {
            return true;
        }

        try {
            Class<?> systemProperties = Class.forName("android.os.SystemProperties");
            Method getMethod = systemProperties.getMethod("get", String.class);
            String miuiVersion = (String) getMethod.invoke(null, "ro.miui.ui.version.name");
            String hyperOsVersion = (String) getMethod.invoke(null, "ro.mi.os.version.name");
            return (miuiVersion != null && !miuiVersion.isEmpty()) || (hyperOsVersion != null && !hyperOsVersion.isEmpty());
        } catch (Throwable ignored) {
            return false;
        }
    }

    /**
     * Whether the app may post an Android 16 "Live Update" (promoted ongoing) notification.
     * Uses the real {@link NotificationManagerCompat#canPostPromotedNotifications()} on
     * Android 16+ (no reflection needed with androidx.core 1.17.0).
     */
    public static boolean canPromoteOngoing(Context context) {
        if (context == null) return false;

        NotificationManagerCompat nmc = NotificationManagerCompat.from(context);
        if (!nmc.areNotificationsEnabled()) {
            return false;
        }

        if (isAndroid16Plus()) {
            try {
                return nmc.canPostPromotedNotifications();
            } catch (Throwable t) {
                Log.w(TAG, "canPostPromotedNotifications() threw: " + t.getMessage());
                // Permission is normal-protection and declared in the manifest; assume OK.
                return true;
            }
        }

        // Pre-16: no promoted chip, but Xiaomi HyperOS still renders the focus island.
        return isXiaomiHyperOs();
    }

    /** True when the app is exempt from Doze / standby battery restrictions. */
    public static boolean isIgnoringBatteryOptimizations(Context context) {
        if (context == null || Build.VERSION.SDK_INT < Build.VERSION_CODES.M) return true;
        try {
            PowerManager pm = (PowerManager) context.getSystemService(Context.POWER_SERVICE);
            return pm != null && pm.isIgnoringBatteryOptimizations(context.getPackageName());
        } catch (Throwable t) {
            return false;
        }
    }

    public static Map<String, Object> getCapabilitiesMap(Context context) {
        Map<String, Object> caps = new HashMap<>();
        caps.put("platform", "android");
        caps.put("sdkInt", Build.VERSION.SDK_INT);
        caps.put("manufacturer", Build.MANUFACTURER != null ? Build.MANUFACTURER : "Unknown");
        caps.put("hyperOsFocus", isXiaomiHyperOs());
        caps.put("isAndroid16Plus", isAndroid16Plus());

        boolean notifEnabled = false;
        boolean canPromote = false;
        if (context != null) {
            try {
                notifEnabled = NotificationManagerCompat.from(context).areNotificationsEnabled();
                canPromote = canPromoteOngoing(context);
            } catch (Throwable ignored) {}
        }
        caps.put("notificationsEnabled", notifEnabled);
        caps.put("promotedOngoing", canPromote);
        caps.put("batteryUnrestricted", isIgnoringBatteryOptimizations(context));

        return caps;
    }
}
