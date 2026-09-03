package com.onyx.workoutapp;

import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.net.Uri;
import android.os.Build;
import android.provider.Settings;
import android.util.Log;

/**
 * One-stop helper for the permissions/settings a workout timer needs to survive being
 * swiped away, with special handling for the aggressive OEM battery managers (Xiaomi /
 * HyperOS, but the generic paths help Oppo/Vivo/Huawei too).
 *
 * <p>Nothing here can be granted silently — every method just launches the right Settings
 * screen. Each has a chain of fallbacks because OEM intents disappear/rename between
 * versions; the last fallback is always the plain app-details page.
 *
 * <p>References:
 * <ul>
 *   <li>https://dev.to/stoyan_minchev/what-android-oems-do-to-background-apps-and-the-11-layers-i-built-to-survive-it-28bb</li>
 *   <li>https://adguard.com/kb/adguard-for-android/solving-problems/background-work/</li>
 *   <li>https://developer.android.com/training/monitoring-device-state/doze-standby</li>
 * </ul>
 */
public final class XiaomiOptimizationGuide {

    private static final String TAG = "OnyxDebug";

    private XiaomiOptimizationGuide() {}

    /**
     * Ask the system to exempt us from battery optimization (Doze). This is the one
     * "permission-like" prompt Google actually allows for a foreground-service app that
     * legitimately needs to run while the screen is off.
     *
     * @return true if a screen was launched, false if already exempt / not applicable.
     */
    public static boolean requestIgnoreBatteryOptimizations(Context context) {
        if (context == null || Build.VERSION.SDK_INT < Build.VERSION_CODES.M) return false;
        if (DeviceCapabilities.isIgnoringBatteryOptimizations(context)) return false;
        try {
            Intent intent = new Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS);
            intent.setData(Uri.parse("package:" + context.getPackageName()));
            launch(context, intent);
            return true;
        } catch (Throwable t) {
            Log.w(TAG, "requestIgnoreBatteryOptimizations failed, opening list: " + t.getMessage());
            return openBatteryOptimizationList(context);
        }
    }

    /** Generic "battery optimization" list (user picks the app manually). */
    public static boolean openBatteryOptimizationList(Context context) {
        if (context == null) return false;
        try {
            launch(context, new Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS));
            return true;
        } catch (Throwable t) {
            return openAppDetails(context);
        }
    }

    /**
     * MIUI/HyperOS "Autostart" (a.k.a. "Auto launch") — off by default and the single
     * biggest reason background services die on Xiaomi. No public API; deep-link into the
     * Security app with fallbacks.
     */
    public static boolean openAutostartSettings(Context context) {
        if (context == null) return false;

        ComponentName[] candidates = new ComponentName[]{
                new ComponentName("com.miui.securitycenter",
                        "com.miui.permcenter.autostart.AutoStartManagementActivity"),
                new ComponentName("com.miui.securitycenter",
                        "com.miui.permcenter.autostart.AutoStartDetailManagementActivity"),
                // Older MIUI
                new ComponentName("com.miui.securitycenter",
                        "com.miui.securityscan.MainActivity"),
                // Letv / generic clones sometimes ship this
                new ComponentName("com.letv.android.letvsafe",
                        "com.letv.android.letvsafe.AutobootManageActivity"),
        };
        for (ComponentName cn : candidates) {
            Intent intent = new Intent();
            intent.setComponent(cn);
            if (tryLaunch(context, intent)) return true;
        }

        // HyperOS "Other permissions" page as a softer fallback.
        Intent perm = new Intent("miui.intent.action.APP_PERM_EDITOR");
        perm.setClassName("com.miui.securitycenter",
                "com.miui.permcenter.permissions.PermissionsEditorActivity");
        perm.putExtra("extra_pkgname", context.getPackageName());
        if (tryLaunch(context, perm)) return true;

        return openAppDetails(context);
    }

    /**
     * MIUI/HyperOS per-app battery saver ("No restrictions" / "Nessuna restrizione").
     * The dedicated activity moved around a lot; fall back to power settings then
     * app details.
     */
    public static boolean openXiaomiBatterySaver(Context context) {
        if (context == null) return false;

        Intent powerHide = new Intent();
        powerHide.setComponent(new ComponentName("com.miui.powerkeeper",
                "com.miui.powerkeeper.ui.HiddenAppsConfigActivity"));
        powerHide.putExtra("package_name", context.getPackageName());
        powerHide.putExtra("package_label", loadLabel(context));
        if (tryLaunch(context, powerHide)) return true;

        Intent powerMain = new Intent();
        powerMain.setComponent(new ComponentName("com.miui.powerkeeper",
                "com.miui.powerkeeper.ui.PowerMainActivity"));
        if (tryLaunch(context, powerMain)) return true;

        return openBatteryOptimizationList(context);
    }

    /** Plain system app-details page — the universal last resort. */
    public static boolean openAppDetails(Context context) {
        if (context == null) return false;
        try {
            Intent intent = new Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS);
            intent.setData(Uri.parse("package:" + context.getPackageName()));
            launch(context, intent);
            return true;
        } catch (Throwable t) {
            Log.e(TAG, "openAppDetails failed: " + t.getMessage());
            return false;
        }
    }

    // ---------------------------------------------------------------------------------

    private static boolean tryLaunch(Context context, Intent intent) {
        try {
            if (intent.resolveActivity(context.getPackageManager()) == null) return false;
            launch(context, intent);
            return true;
        } catch (Throwable t) {
            Log.d(TAG, "tryLaunch " + intent.getComponent() + " -> " + t.getMessage());
            return false;
        }
    }

    private static void launch(Context context, Intent intent) {
        if (!(context instanceof android.app.Activity)) {
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        }
        context.startActivity(intent);
    }

    private static String loadLabel(Context context) {
        try {
            return context.getApplicationInfo()
                    .loadLabel(context.getPackageManager()).toString();
        } catch (Throwable t) {
            return "Onyx Workout";
        }
    }
}
