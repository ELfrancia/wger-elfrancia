package com.onyx.workoutapp;

import android.app.NotificationManager;
import android.content.Context;
import android.content.pm.PackageManager;
import android.os.Build;
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

    public static boolean canPromoteOngoing(Context context) {
        if (context == null) return false;
        
        // 1. First ensure notifications are enabled in general
        if (!NotificationManagerCompat.from(context).areNotificationsEnabled()) {
            return false;
        }

        // 2. On Android 16+ (API 36+), check NotificationManager.canPostPromotedNotifications()
        if (isAndroid16Plus()) {
            try {
                NotificationManager nm = (NotificationManager) context.getSystemService(Context.NOTIFICATION_SERVICE);
                if (nm != null) {
                    try {
                        Method canPromoteMethod = nm.getClass().getMethod("canPostPromotedNotifications");
                        Object result = canPromoteMethod.invoke(nm);
                        if (result instanceof Boolean) {
                            return (Boolean) result;
                        }
                    } catch (NoSuchMethodException ignored) {
                        // Method not exposed in this exact API preview, default to true since notifications are enabled
                        return true;
                    }
                }
                return true;
            } catch (Throwable t) {
                Log.w(TAG, "DeviceCapabilities: Error checking promoted notification status: " + t.getMessage());
                return true;
            }
        }

        // On HyperOS 3 / Xiaomi devices with focus notifications, we can still render the custom pill
        return isXiaomiHyperOs();
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

        return caps;
    }
}
