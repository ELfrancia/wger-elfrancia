package com.onyx.workoutapp;

import android.content.Context;
import android.graphics.drawable.Icon;
import android.os.Bundle;
import android.util.Log;

import androidx.core.app.NotificationCompat;

import org.json.JSONArray;
import org.json.JSONObject;

/**
 * Attaches Xiaomi HyperOS <b>Focus Notification</b> / <b>Super Island</b> metadata to a
 * notification builder.
 *
 * <p>HyperOS does not expose a public SDK for this. The island is driven entirely by
 * magic {@code miui.focus.*} keys placed in {@code Notification.extras} while the app
 * process is alive. The schema below is the community-reverse-engineered one used by
 * <a href="https://github.com/D4vidDf/HyperIsland-ToolKit">HyperIsland-ToolKit</a> and
 * documented at
 * <a href="https://dev.mi.com/xiaomihyperos/documentation/detail?pId=2131">dev.mi.com</a>.
 *
 * <ul>
 *   <li><b>miui.focus.param</b> — JSON string, the whole island description. HyperOS 2
 *       reads the flat form; HyperOS 3 reads the {@code param_v2} object. We emit both.</li>
 *   <li><b>miui.focus.pics</b> — {@code Bundle} of {name → Icon} referenced by
 *       {@code picInfo.pic} / {@code baseInfo} icons.</li>
 *   <li><b>miui.focus.enable / miui.focus.type</b> — legacy HyperOS 1 booleans, kept as a
 *       last-ditch fallback.</li>
 * </ul>
 *
 * <p>Tap targets: HyperOS renders the notification's own {@code actions[]} and
 * {@code contentIntent} in the expanded island, so we deliberately do <i>not</i> try to
 * serialise PendingIntents into {@code miui.focus.param} (that path is version-fragile and
 * has open bugs — see HyperBridge issue #161).
 *
 * <p>Every method is wrapped so it is a pure no-op on non-Xiaomi devices and can never
 * break notification posting.
 */
public class HyperFocusExtras {

    private static final String TAG = "OnyxDebug";

    private static final String ICON_NAME = "onyx_island_icon";

    // ---------------------------------------------------------------------------------
    // Public entry points (one per notification kind)
    // ---------------------------------------------------------------------------------

    /** Rest countdown island: circular progress + live countdown timer text. */
    public static void applyRestFocus(
            NotificationCompat.Builder builder,
            Context context,
            float ratioRemaining,
            long targetEndTimeMs,
            long secondsLeft,
            boolean isPaused,
            String title,
            int accentColor
    ) {
        if (!guard(builder, context)) return;
        try {
            String safeTitle = (title != null && !title.isEmpty()) ? title : "Recupero in corso";
            String hex = argb(accentColor);
            int progressPct = clampPct(Math.round((1f - clamp01(ratioRemaining)) * 100f));
            String mmss = String.format("%02d:%02d", secondsLeft / 60, secondsLeft % 60);

            JSONObject base = new JSONObject()
                    .put("type", 1)
                    .put("title", "ONYX")
                    .put("content", isPaused ? ("In pausa (" + mmss + ")") : safeTitle)
                    .put("colorTitle", "#FFFFFFFF")
                    .put("colorContent", hex);

            JSONObject progress = new JSONObject()
                    .put("progress", progressPct)
                    .put("colorProgress", hex)
                    .put("colorProgressEnd", hex)
                    .put("isCCW", false);

            JSONObject pic = new JSONObject().put("type", 1).put("pic", ICON_NAME);

            JSONObject paramV2 = new JSONObject()
                    .put("protocol", 1)
                    .put("enableFloat", true)
                    .put("updatable", true)
                    .put("ticker", "ONYX " + (isPaused ? ("Pausa " + mmss) : mmss))
                    .put("baseInfo", base)
                    .put("progressInfo", progress)
                    .put("picInfo", pic)
                    .put("colorBg", "#FF000000")
                    .put("bgColor", "#FF000000");

            if (!isPaused && targetEndTimeMs > System.currentTimeMillis()) {
                // timerType 1 = count down. HyperOS renders a self-ticking mm:ss.
                paramV2.put("timerInfo", new JSONObject()
                        .put("timerType", 1)
                        .put("timerWhen", targetEndTimeMs)
                        .put("timerSystemCurrent", System.currentTimeMillis())
                        .put("colorTimer", hex));
            } else {
                paramV2.put("timerInfo", new JSONObject().put("timerType", 0));
                base.put("content", isPaused
                        ? String.format("In pausa (%s)", mmss)
                        : "Tempo scaduto");
            }

            attach(builder, context, paramV2, "ONYX " + mmss);
        } catch (Throwable t) {
            Log.d(TAG, "applyRestFocus skipped: " + t.getMessage());
        }
    }

    /** Workout progress island: segmented set-progress ring + elapsed time. */
    public static void applyWorkoutFocus(
            NotificationCompat.Builder builder,
            Context context,
            float ratioDone,
            int completedSets,
            int totalSets,
            String title,
            String currentExerciseName,
            long startedAtMs,
            int accentColor
    ) {
        if (!guard(builder, context)) return;
        try {
            String safeTitle = (title != null && !title.isEmpty()) ? title : "Sessione di Allenamento";
            String hex = argb(accentColor);
            String content = (currentExerciseName != null && !currentExerciseName.trim().isEmpty())
                    ? (currentExerciseName + " (" + completedSets + "/" + totalSets + ")")
                    : (completedSets + "/" + totalSets + " serie");

            JSONObject base = new JSONObject()
                    .put("type", 1)
                    .put("title", "ONYX")
                    .put("content", content)
                    .put("colorTitle", "#FFFFFFFF")
                    .put("colorContent", hex);

            JSONObject progress = new JSONObject()
                    .put("progress", clampPct(Math.round(clamp01(ratioDone) * 100f)))
                    .put("colorProgress", hex)
                    .put("colorProgressEnd", hex)
                    .put("isCCW", false)
                    .put("progressDesc", completedSets + "/" + totalSets);

            JSONObject paramV2 = new JSONObject()
                    .put("protocol", 1)
                    .put("enableFloat", true)
                    .put("updatable", true)
                    .put("ticker", "ONYX " + completedSets + "/" + totalSets)
                    .put("baseInfo", base)
                    .put("progressInfo", progress)
                    .put("picInfo", new JSONObject().put("type", 1).put("pic", ICON_NAME))
                    .put("colorBg", "#FF000000")
                    .put("bgColor", "#FF000000");

            if (startedAtMs > 0) {
                // timerType 2 = count up (elapsed).
                paramV2.put("timerInfo", new JSONObject()
                        .put("timerType", 2)
                        .put("timerWhen", startedAtMs)
                        .put("timerSystemCurrent", System.currentTimeMillis())
                        .put("colorTimer", "#FFFFFFFF"));
            }

            attach(builder, context, paramV2, "ONYX " + safeTitle);
        } catch (Throwable t) {
            Log.d(TAG, "applyWorkoutFocus skipped: " + t.getMessage());
        }
    }

    /** "Time's up" alarm island: static alert state, full accent fill. */
    public static void applyAlarmFocus(
            NotificationCompat.Builder builder,
            Context context,
            int accentColor
    ) {
        if (!guard(builder, context)) return;
        try {
            String hex = argb(accentColor);          // lime
            String black = "#FF000000";
            JSONObject base = new JSONObject()
                    .put("type", 1)
                    .put("title", "TEMPO SCADUTO!")
                    .put("content", "Tocca per disattivare l'allarme")
                    // Black text on a lime fill — matches the in-app yellow "TEMPO SCADUTO" notch.
                    .put("colorTitle", black)
                    .put("colorContent", black)
                    .put("colorContentBg", hex)
                    .put("colorBg", hex)
                    .put("bgColor", hex);

            JSONObject paramV2 = new JSONObject()
                    .put("protocol", 1)
                    .put("enableFloat", true)
                    .put("updatable", true)
                    .put("ticker", "TEMPO SCADUTO!")
                    .put("colorBg", hex)
                    .put("bgColor", hex)
                    .put("baseInfo", base)
                    .put("progressInfo", new JSONObject()
                            .put("progress", 100)
                            .put("colorProgress", black)
                            .put("colorProgressEnd", black)
                            .put("isCCW", false))
                    .put("picInfo", new JSONObject().put("type", 1).put("pic", ICON_NAME));

            attach(builder, context, paramV2, "TEMPO SCADUTO!");
        } catch (Throwable t) {
            Log.d(TAG, "applyAlarmFocus skipped: " + t.getMessage());
        }
    }

    // ---------------------------------------------------------------------------------
    // Internals
    // ---------------------------------------------------------------------------------

    private static boolean guard(NotificationCompat.Builder builder, Context context) {
        if (builder == null || context == null) return false;
        try {
            return DeviceCapabilities.isXiaomiHyperOs();
        } catch (Throwable t) {
            return false;
        }
    }

    /**
     * Writes the {@code miui.focus.*} extras. Emits {@code param_v2} wrapped for HyperOS 3
     * and the same object flattened at top level for HyperOS 2, plus the legacy booleans
     * and the icon bundle.
     */
    private static void attach(NotificationCompat.Builder builder, Context context,
                               JSONObject paramV2, String ticker) throws Exception {
        JSONObject root = new JSONObject();
        // HyperOS 3 Super Island
        root.put("param_v2", paramV2);
        // HyperOS 2 Focus reads several of these keys at the top level too.
        root.put("protocol", 1);
        root.put("enableFloat", true);
        root.put("updatable", true);
        root.put("ticker", ticker);
        if (paramV2.has("baseInfo")) root.put("baseInfo", paramV2.getJSONObject("baseInfo"));
        if (paramV2.has("progressInfo")) root.put("progressInfo", paramV2.getJSONObject("progressInfo"));
        if (paramV2.has("timerInfo")) root.put("timerInfo", paramV2.getJSONObject("timerInfo"));
        if (paramV2.has("picInfo")) root.put("picInfo", paramV2.getJSONObject("picInfo"));
        if (paramV2.has("colorBg")) root.put("colorBg", paramV2.getString("colorBg"));
        if (paramV2.has("bgColor")) root.put("bgColor", paramV2.getString("bgColor"));

        Bundle extras = new Bundle();
        extras.putString("miui.focus.param", root.toString());
        // Legacy HyperOS 1 fallbacks.
        extras.putBoolean("miui.focus.enable", true);
        extras.putInt("miui.focus.type", 1);
        extras.putInt("miui.focus.version", 1);
        if (paramV2.has("progressInfo")) {
            extras.putFloat("miui.focus.progress",
                    clamp01(paramV2.getJSONObject("progressInfo").optInt("progress", 0) / 100f));
        }

        // Icon bundle referenced by picInfo.pic == ICON_NAME.
        try {
            Icon icon = Icon.createWithResource(context, R.drawable.ic_stat_onyx);
            Bundle pics = new Bundle();
            pics.putParcelable(ICON_NAME, icon);
            extras.putBundle("miui.focus.pics", pics);
        } catch (Throwable t) {
            Log.d(TAG, "HyperFocus icon bundle skipped: " + t.getMessage());
        }

        builder.addExtras(extras);
    }

    private static String argb(int color) {
        return String.format("#%08X", color);
    }

    private static float clamp01(float v) {
        return Math.max(0f, Math.min(1f, v));
    }

    private static int clampPct(int v) {
        return Math.max(0, Math.min(100, v));
    }
}
