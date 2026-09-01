package com.onyx.workoutapp;

import android.Manifest;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.util.Log;
import android.view.ViewGroup;
import android.view.WindowManager;
import android.webkit.JavascriptInterface;
import android.webkit.RenderProcessGoneDetail;
import android.webkit.WebView;
import android.widget.Toast;
import androidx.activity.OnBackPressedCallback;
import androidx.annotation.NonNull;
import androidx.annotation.RequiresApi;
import androidx.core.view.WindowCompat;
import androidx.core.view.WindowInsetsCompat;
import androidx.core.view.WindowInsetsControllerCompat;
import com.getcapacitor.BridgeActivity;
import com.getcapacitor.BridgeWebViewClient;
import com.getcapacitor.WebViewListener;

public class MainActivity extends BridgeActivity {

    private static final String TAG = "OnyxDebug";
    private static final int PERMISSION_REQUEST_CODE = 1001;
    private boolean isWebViewListenerRegistered = false;
    private boolean isBridgeInterfaceBound = false;
    private boolean isRenderCrashClientInstalled = false;

    public class AndroidTimerBridge {
        @JavascriptInterface
        public void startWorkout(String title, long startTimestampMs) {
            Log.d(TAG, "AndroidTimer.startWorkout called: " + title);
            try {
                Intent serviceIntent = new Intent(MainActivity.this, OnyxLiveService.class);
                serviceIntent.setAction(OnyxLiveService.ACTION_WORKOUT_START);
                serviceIntent.putExtra(OnyxLiveService.EXTRA_TITLE, (title != null && !title.isEmpty()) ? title : "Sessione di Allenamento");
                serviceIntent.putExtra(OnyxLiveService.EXTRA_STARTED_AT, startTimestampMs > 0 ? startTimestampMs : System.currentTimeMillis());
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                    startForegroundService(serviceIntent);
                } else {
                    startService(serviceIntent);
                }
            } catch (Exception e) {
                Log.e(TAG, "Error starting workout in OnyxLiveService: " + e.getMessage(), e);
            }
        }

        @JavascriptInterface
        public void stopWorkout() {
            Log.d(TAG, "AndroidTimer.stopWorkout called");
            try {
                Intent serviceIntent = new Intent(MainActivity.this, OnyxLiveService.class);
                serviceIntent.setAction(OnyxLiveService.ACTION_WORKOUT_STOP);
                startService(serviceIntent);
            } catch (Exception e) {
                Log.e(TAG, "Error stopping workout in OnyxLiveService: " + e.getMessage(), e);
            }
        }

        @JavascriptInterface
        public void updateProgress(int completed, int total, int remaining) {
            updateProgressWithExercise(completed, total, remaining, null);
        }

        @JavascriptInterface
        public void updateProgressWithExercise(int completed, int total, int remaining, String currentExercise) {
            Log.d(TAG, "AndroidTimer.updateProgress: completed=" + completed + ", total=" + total + ", ex=" + currentExercise);
            try {
                Intent serviceIntent = new Intent(MainActivity.this, OnyxLiveService.class);
                serviceIntent.setAction(OnyxLiveService.ACTION_WORKOUT_UPDATE);
                serviceIntent.putExtra(OnyxLiveService.EXTRA_COMPLETED_SETS, completed);
                serviceIntent.putExtra(OnyxLiveService.EXTRA_TOTAL_SETS, total);
                if (currentExercise != null && !currentExercise.isEmpty()) {
                    serviceIntent.putExtra(OnyxLiveService.EXTRA_CURRENT_EXERCISE, currentExercise);
                }
                startService(serviceIntent);
            } catch (Exception e) {
                Log.e(TAG, "Error updating workout progress in OnyxLiveService: " + e.getMessage(), e);
            }
        }

        @JavascriptInterface
        public void startTimer(int durationSeconds, String title) {
            startTimerWithSound(durationSeconds, title, null);
        }

        @JavascriptInterface
        public void startTimerWithSound(int durationSeconds, String title, String soundUri) {
            Log.d(TAG, "AndroidTimer.startTimer called: duration=" + durationSeconds + "s, title=" + title + ", soundUri=" + soundUri);
            try {
                Intent serviceIntent = new Intent(MainActivity.this, OnyxLiveService.class);
                serviceIntent.setAction(OnyxLiveService.ACTION_START);
                serviceIntent.putExtra(OnyxLiveService.EXTRA_DURATION, durationSeconds);
                serviceIntent.putExtra(OnyxLiveService.EXTRA_TITLE, (title != null && !title.isEmpty()) ? title : "Recupero in corso");
                if (soundUri != null && !soundUri.isEmpty()) {
                    serviceIntent.putExtra(OnyxLiveService.EXTRA_SOUND_URI, soundUri);
                }
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                    startForegroundService(serviceIntent);
                } else {
                    startService(serviceIntent);
                }
                Log.d(TAG, "OnyxLiveService started/updated successfully");
            } catch (Exception e) {
                Log.e(TAG, "Error starting/updating OnyxLiveService: " + e.getMessage(), e);
            }
        }

        @JavascriptInterface
        public void pauseTimer() {
            Log.d(TAG, "AndroidTimer.pauseTimer called");
            try {
                Intent serviceIntent = new Intent(MainActivity.this, OnyxLiveService.class);
                serviceIntent.setAction(OnyxLiveService.ACTION_PAUSE);
                startService(serviceIntent);
            } catch (Exception e) {
                Log.e(TAG, "Error pausing OnyxLiveService: " + e.getMessage(), e);
            }
        }

        @JavascriptInterface
        public void resumeTimer() {
            Log.d(TAG, "AndroidTimer.resumeTimer called");
            try {
                Intent serviceIntent = new Intent(MainActivity.this, OnyxLiveService.class);
                serviceIntent.setAction(OnyxLiveService.ACTION_RESUME);
                startService(serviceIntent);
            } catch (Exception e) {
                Log.e(TAG, "Error resuming OnyxLiveService: " + e.getMessage(), e);
            }
        }

        @JavascriptInterface
        public void addSeconds(int seconds) {
            Log.d(TAG, "AndroidTimer.addSeconds called: " + seconds);
            try {
                Intent serviceIntent = new Intent(MainActivity.this, OnyxLiveService.class);
                serviceIntent.setAction(OnyxLiveService.ACTION_ADD_TIME);
                serviceIntent.putExtra(OnyxLiveService.EXTRA_DURATION, seconds);
                startService(serviceIntent);
            } catch (Exception e) {
                Log.e(TAG, "Error adding seconds to OnyxLiveService: " + e.getMessage(), e);
            }
        }

        @JavascriptInterface
        public void stopTimer() {
            Log.d(TAG, "AndroidTimer.stopTimer called");
            try {
                Intent serviceIntent = new Intent(MainActivity.this, OnyxLiveService.class);
                serviceIntent.setAction(OnyxLiveService.ACTION_STOP);
                startService(serviceIntent);
            } catch (Exception e) {
                Log.e(TAG, "Error stopping OnyxLiveService: " + e.getMessage(), e);
            }
        }

        @JavascriptInterface
        public void stopAlarm() {
            Log.d(TAG, "AndroidTimer.stopAlarm called");
            try {
                Intent serviceIntent = new Intent(MainActivity.this, OnyxLiveService.class);
                serviceIntent.setAction(OnyxLiveService.ACTION_STOP_ALARM);
                startService(serviceIntent);
            } catch (Exception e) {
                Log.e(TAG, "Error stopping alarm: " + e.getMessage(), e);
            }
        }

        @JavascriptInterface
        public void requestAllPermissions() {
            Log.d(TAG, "AndroidTimer.requestAllPermissions called");
            runOnUiThread(() -> {
                requestNotificationPermission();
                requestBatteryOptimizationExemption();
            });
        }

        @JavascriptInterface
        public void openNotificationSettings() {
            Log.d(TAG, "AndroidTimer.openNotificationSettings called");
            runOnUiThread(() -> openAppNotificationSettings());
        }

        @JavascriptInterface
        public boolean areNotificationsEnabled() {
            try {
                return androidx.core.app.NotificationManagerCompat.from(MainActivity.this).areNotificationsEnabled();
            } catch (Exception e) {
                return true;
            }
        }

        @JavascriptInterface
        public boolean canPostPromotedNotifications() {
            return DeviceCapabilities.canPromoteOngoing(MainActivity.this);
        }

        @JavascriptInterface
        public void testNotification() {
            Log.d(TAG, "AndroidTimer.testNotification called (5 sec test)");
            startTimer(5, "Test Timer 5s");
        }
    }

    @Override
    public void onCreate(Bundle savedInstanceState) {
        registerPlugin(OnyxLivePlugin.class);
        super.onCreate(savedInstanceState);

        // Enable Chrome DevTools remote debugging (chrome://inspect on PC)
        WebView.setWebContentsDebuggingEnabled(true);
        Log.d(TAG, "WebContentsDebuggingEnabled set to TRUE");

        // Ensure status bar is always visible (NO FULLSCREEN)
        getWindow().clearFlags(WindowManager.LayoutParams.FLAG_FULLSCREEN);
        WindowCompat.setDecorFitsSystemWindows(getWindow(), true);
        WindowInsetsControllerCompat insetsController = new WindowInsetsControllerCompat(getWindow(), getWindow().getDecorView());
        insetsController.setAppearanceLightStatusBars(false);
        insetsController.show(WindowInsetsCompat.Type.statusBars());

        // Explicitly request Notification permission for Android 13+ (Poco / Xiaomi HyperOS)
        requestNotificationPermission();

        // Configure Back press handling (modals -> webView.goBack -> moveTaskToBack)
        setupBackPressHandler();

        // Register direct JavaScriptInterface and inject bridge watcher
        setupWebViewBridge();

        // Handle open_timer and open_workout notification intents
        handleOpenTimerIntent(getIntent());
        handleOpenWorkoutIntent(getIntent());
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        handleOpenTimerIntent(intent);
        handleOpenWorkoutIntent(intent);
    }

    private void handleOpenWorkoutIntent(Intent intent) {
        if (intent != null && intent.getBooleanExtra("open_workout", false)) {
            Log.d(TAG, "handleOpenWorkoutIntent: open_workout flag detected");
            try {
                WebView webView = getBridge() != null ? getBridge().getWebView() : null;
                if (webView != null) {
                    String js = "(function() {" +
                                "  try {" +
                                "    console.log('[OnyxWorkout] Deep-link to active workout received');" +
                                "    if (typeof window.focusActiveWorkoutSession === 'function') {" +
                                "      window.focusActiveWorkoutSession();" +
                                "    } else if (window.location.hash.includes('rest-timer')) {" +
                                "      if (typeof window.closeRestTimerOverlay === 'function') window.closeRestTimerOverlay();" +
                                "    }" +
                                "  } catch(e) { console.error('[OnyxWorkout] Open workout error:', e); }" +
                                "})();";
                    webView.post(() -> webView.evaluateJavascript(js, null));
                }
            } catch (Exception e) {
                Log.e(TAG, "Error handling open_workout intent: " + e.getMessage(), e);
            }
        }
    }

    private void handleOpenTimerIntent(Intent intent) {
        if (intent != null && intent.getBooleanExtra("open_timer", false)) {
            Log.d(TAG, "handleOpenTimerIntent: open_timer flag detected, executing openOverlay()");
            try {
                WebView webView = getBridge() != null ? getBridge().getWebView() : null;
                if (webView != null) {
                    String js = "(function() {" +
                                "  try {" +
                                "    if (typeof window.openOverlay === 'function') {" +
                                "      window.openOverlay();" +
                                "    } else {" +
                                "      sessionStorage.setItem('open_timer_overlay', 'true');" +
                                "      if (!window.location.hash.includes('rest-timer')) {" +
                                "        window.location.hash = '#rest-timer';" +
                                "      }" +
                                "    }" +
                                "  } catch(e) { console.error('[OnyxTimer] Open overlay error:', e); }" +
                                "})();";
                    webView.post(() -> webView.evaluateJavascript(js, null));
                }
            } catch (Exception e) {
                Log.e(TAG, "Error handling open_timer intent: " + e.getMessage(), e);
            }
        }
    }

    private void setupBackPressHandler() {
        getOnBackPressedDispatcher().addCallback(this, new OnBackPressedCallback(true) {
            @Override
            public void handleOnBackPressed() {
                try {
                    WebView webView = getBridge() != null ? getBridge().getWebView() : null;
                    if (webView == null) {
                        moveTaskToBack(true);
                        return;
                    }

                    String checkAndCloseModalJs =
                        "(function() {" +
                        "  try {" +
                        "    var specificIds = [" +
                        "      'rest-timer-overlay'," +
                        "      'global-timer-options-modal'," +
                        "      'custom-exercise-modal'," +
                        "      'onyx-quick-action-overlay'," +
                        "      'exercise-detail-modal'," +
                        "      'workout-summary-modal'," +
                        "      'settings-modal'" +
                        "    ];" +
                        "    for (var i = 0; i < specificIds.length; i++) {" +
                        "      var el = document.getElementById(specificIds[i]);" +
                        "      if (el) {" +
                        "        var style = window.getComputedStyle(el);" +
                        "        var isVisible = style.display !== 'none' && style.visibility !== 'hidden' && !el.classList.contains('hidden') && parseFloat(style.opacity || '1') > 0;" +
                        "        if (isVisible) {" +
                        "          var closeBtn = el.querySelector('[data-close], .close-btn, .btn-close, button[onclick*=\"close\"], button[onclick*=\"hide\"], .close-modal');" +
                        "          if (closeBtn) { closeBtn.click(); return true; }" +
                        "          if (specificIds[i] === 'rest-timer-overlay' && typeof window.closeRestTimerOverlay === 'function') {" +
                        "            window.closeRestTimerOverlay(); return true;" +
                        "          }" +
                        "          if (typeof window.closeModal === 'function') {" +
                        "            window.closeModal(specificIds[i]); return true;" +
                        "          }" +
                        "          el.classList.add('hidden');" +
                        "          el.style.display = 'none';" +
                        "          return true;" +
                        "        }" +
                        "      }" +
                        "    }" +
                        "    var dialogs = document.querySelectorAll('dialog[open]');" +
                        "    if (dialogs && dialogs.length > 0) {" +
                        "      dialogs[dialogs.length - 1].close();" +
                        "      return true;" +
                        "    }" +
                        "    var activeModals = document.querySelectorAll('.modal.active, .modal.show, .modal-open, [data-modal].active, [data-modal].show, .drawer.open, .drawer.active');" +
                        "    for (var j = activeModals.length - 1; j >= 0; j--) {" +
                        "      var m = activeModals[j];" +
                        "      var mStyle = window.getComputedStyle(m);" +
                        "      if (mStyle.display !== 'none' && mStyle.visibility !== 'hidden') {" +
                        "        var mClose = m.querySelector('[data-close], .close-btn, .btn-close, button[onclick*=\"close\"], button[onclick*=\"hide\"]');" +
                        "        if (mClose) { mClose.click(); }" +
                        "        else { m.classList.remove('active', 'show', 'modal-open', 'open'); m.style.display = 'none'; }" +
                        "        return true;" +
                        "      }" +
                        "    }" +
                        "  } catch (e) {" +
                        "    console.error('[OnyxBackPress] Error checking modal:', e);" +
                        "  }" +
                        "  return false;" +
                        "})();";

                    webView.evaluateJavascript(checkAndCloseModalJs, value -> {
                        boolean modalClosed = "true".equalsIgnoreCase(value) || "\"true\"".equalsIgnoreCase(value);
                        if (modalClosed) {
                            Log.d(TAG, "Back pressed: modal/overlay closed");
                        } else {
                            if (webView.canGoBack()) {
                                Log.d(TAG, "Back pressed: navigating webView back");
                                webView.goBack();
                            } else {
                                Log.d(TAG, "Back pressed: on main screen, moving task to back");
                                moveTaskToBack(true);
                            }
                        }
                    });
                } catch (Exception e) {
                    Log.e(TAG, "Error handling back press: " + e.getMessage(), e);
                    moveTaskToBack(true);
                }
            }
        });
    }

    private void requestNotificationPermission() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            boolean granted = checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED;
            Log.d(TAG, "POST_NOTIFICATIONS permission status: " + (granted ? "GRANTED" : "NOT GRANTED"));
            if (!granted) {
                Log.d(TAG, "Requesting POST_NOTIFICATIONS permission from user...");
                requestPermissions(new String[]{
                        Manifest.permission.POST_NOTIFICATIONS
                }, PERMISSION_REQUEST_CODE);
            }
        }
    }

    private void requestBatteryOptimizationExemption() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            try {
                android.os.PowerManager pm = (android.os.PowerManager) getSystemService(Context.POWER_SERVICE);
                if (pm != null && !pm.isIgnoringBatteryOptimizations(getPackageName())) {
                    Intent intent = new Intent(android.provider.Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS);
                    intent.setData(android.net.Uri.parse("package:" + getPackageName()));
                    startActivity(intent);
                }
            } catch (Exception e) {
                Log.e(TAG, "Error requesting battery optimization exemption: " + e.getMessage());
            }
        }
    }

    public void openAppNotificationSettings() {
        try {
            Intent intent = new Intent();
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                intent.setAction(android.provider.Settings.ACTION_APP_NOTIFICATION_SETTINGS);
                intent.putExtra(android.provider.Settings.EXTRA_APP_PACKAGE, getPackageName());
            } else {
                intent.setAction(android.provider.Settings.ACTION_APPLICATION_DETAILS_SETTINGS);
                intent.setData(android.net.Uri.parse("package:" + getPackageName()));
            }
            startActivity(intent);
        } catch (Exception e) {
            Log.e(TAG, "Error opening app notification settings: " + e.getMessage());
        }
    }

    @Override
    public void onRequestPermissionsResult(int requestCode, @NonNull String[] permissions, @NonNull int[] grantResults) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults);
        if (requestCode == PERMISSION_REQUEST_CODE) {
            if (grantResults.length > 0 && grantResults[0] == PackageManager.PERMISSION_GRANTED) {
                Log.d(TAG, "POST_NOTIFICATIONS permission GRANTED by user");
                Toast.makeText(this, "Notifiche abilitate", Toast.LENGTH_SHORT).show();
            } else {
                Log.w(TAG, "POST_NOTIFICATIONS permission DENIED by user");
                Toast.makeText(this, "Attenzione: Notifiche disabilitate", Toast.LENGTH_LONG).show();
            }
        }
    }

    private void setupWebViewBridge() {
        try {
            if (getBridge() == null) return;
            WebView webView = getBridge().getWebView();
            if (webView == null) return;

            // Bind the @JavascriptInterface object EXACTLY once, on the UI thread. Re-adding it
            // on every resume / page load leaked bridge objects and, if a WebViewListener
            // callback ever ran off the UI thread, could crash with
            // "Calling View methods on another thread".
            if (!isBridgeInterfaceBound) {
                runOnUiThread(() -> {
                    try {
                        webView.addJavascriptInterface(new AndroidTimerBridge(), "AndroidTimer");
                        isBridgeInterfaceBound = true;
                        Log.d(TAG, "AndroidTimer JavaScriptInterface bound to WebView (once)");
                    } catch (Exception e) {
                        Log.e(TAG, "Error binding AndroidTimer interface: " + e.getMessage(), e);
                    }
                });
            }

            installRenderCrashClient();
            injectBridgeScript(webView);

            if (!isWebViewListenerRegistered) {
                getBridge().addWebViewListener(new WebViewListener() {
                    @Override
                    public void onPageLoaded(WebView view) {
                        super.onPageLoaded(view);
                        Log.d(TAG, "WebViewListener.onPageLoaded: re-injecting bridge script");
                        if (view != null) {
                            // Interface object survives navigations; only the injected helper
                            // script needs re-running after a full page load.
                            injectBridgeScript(view);
                        }
                    }
                });
                isWebViewListenerRegistered = true;
                Log.d(TAG, "Capacitor WebViewListener registered successfully");
            }
        } catch (Exception e) {
            Log.e(TAG, "Error in setupWebViewBridge: " + e.getMessage(), e);
        }
    }

    /**
     * Recover from WebView renderer crashes (common on low-RAM Xiaomi / HyperOS devices)
     * instead of letting the Activity die and the app "close by itself".
     */
    private void installRenderCrashClient() {
        if (isRenderCrashClientInstalled || getBridge() == null) return;
        try {
            getBridge().setWebViewClient(new BridgeWebViewClient(getBridge()) {
                @RequiresApi(Build.VERSION_CODES.O)
                @Override
                public boolean onRenderProcessGone(WebView view, RenderProcessGoneDetail detail) {
                    boolean didCrash = detail != null && detail.didCrash();
                    Log.e(TAG, "WebView render process gone (didCrash=" + didCrash + "). Rebuilding activity.");
                    try {
                        if (view != null) {
                            ViewGroup parent = (ViewGroup) view.getParent();
                            if (parent != null) parent.removeView(view);
                            view.destroy();
                        }
                    } catch (Exception e) {
                        Log.e(TAG, "Error tearing down dead WebView: " + e.getMessage(), e);
                    }
                    isBridgeInterfaceBound = false;
                    runOnUiThread(() -> {
                        try {
                            recreate();
                        } catch (Exception e) {
                            Log.e(TAG, "recreate() after render crash failed: " + e.getMessage(), e);
                        }
                    });
                    return true;
                }
            });
            isRenderCrashClientInstalled = true;
            Log.d(TAG, "Render-crash WebViewClient installed");
        } catch (Exception e) {
            Log.e(TAG, "Could not install render-crash WebViewClient: " + e.getMessage(), e);
        }
    }

    private void injectBridgeScript(WebView webView) {
        String injectionScript =
            "(function() {" +
            "  console.log('[OnyxBridge] Initializing webview timer bridge...');" +
            "  window._onyxBridgeInjected = true;" +
            "  " +
            "  /* Hide any leftover fullscreen button */" +
            "  var style = document.getElementById('onyx-hide-fullscreen-style');" +
            "  if (!style) {" +
            "    style = document.createElement('style');" +
            "    style.id = 'onyx-hide-fullscreen-style';" +
            "    style.innerHTML = '.fullscreen-toggle-icon, button[onclick*=\"toggleAppFullscreen\"] { display: none !important; }';" +
            "    document.head.appendChild(style);" +
            "  }" +
            "  " +
            "  function bindTimerHooks() {" +
            "    /* Hook into timer execution startCountdown */" +
            "    var origStart = window.startCountdown;" +
            "    if (typeof origStart === 'function' && !origStart._hooked) {" +
            "      window.startCountdown = function() {" +
            "        console.log('[OnyxBridge] startCountdown intercepted');" +
            "        var res = origStart.apply(this, arguments);" +
            "        try {" +
            "          var raw = localStorage.getItem('onyx_active_rest_timer');" +
            "          if (raw && window.AndroidTimer) {" +
            "            var s = JSON.parse(raw);" +
            "            var sec = Math.ceil((s.remainingMs || 45000) / 1000);" +
            "            console.log('[OnyxBridge] Calling AndroidTimer.startTimer(' + sec + ')');" +
            "            window.AndroidTimer.startTimer(sec, 'Recupero in corso');" +
            "          }" +
            "        } catch(e) { console.error('[OnyxBridge] Error:', e); }" +
            "        return res;" +
            "      };" +
            "      window.startCountdown._hooked = true;" +
            "    }" +
            "    " +
            "    /* Hook into stopTimer */" +
            "    var origStop = window.stopTimer;" +
            "    if (typeof origStop === 'function' && !origStop._hooked) {" +
            "      window.stopTimer = function() {" +
            "        console.log('[OnyxBridge] stopTimer intercepted');" +
            "        var res = origStop.apply(this, arguments);" +
            "        try {" +
            "          if (window.AndroidTimer) {" +
            "            window.AndroidTimer.stopTimer();" +
            "            window.AndroidTimer.stopAlarm();" +
            "          }" +
            "        } catch(e) { console.error('[OnyxBridge] Error:', e); }" +
            "        return res;" +
            "      };" +
            "      window.stopTimer._hooked = true;" +
            "    }" +
            "  }" +
            "  " +
            "  bindTimerHooks();" +
            "  " +
            "  /* Hook into SPA navigation */" +
            "  if (!window._onyxHistoryPatched) {" +
            "    window._onyxHistoryPatched = true;" +
            "    var origPush = history.pushState;" +
            "    var origReplace = history.replaceState;" +
            "    if (origPush) {" +
            "      history.pushState = function() {" +
            "        var res = origPush.apply(this, arguments);" +
            "        setTimeout(bindTimerHooks, 100);" +
            "        return res;" +
            "      };" +
            "    }" +
            "    if (origReplace) {" +
            "      history.replaceState = function() {" +
            "        var res = origReplace.apply(this, arguments);" +
            "        setTimeout(bindTimerHooks, 100);" +
            "        return res;" +
            "      };" +
            "    }" +
            "    window.addEventListener('popstate', function() { setTimeout(bindTimerHooks, 100); });" +
            "    window.addEventListener('hashchange', function() { setTimeout(bindTimerHooks, 100); });" +
            "  }" +
            /* The old 1-second "storage watcher" that re-issued AndroidTimer.startTimer() on
               >3s drift was removed: it fought the web countdown and caused start/stop
               ping-pong plus notification chronometer jumps. Native timer state is now driven
               only by explicit user actions via onyxNative + native->web events. */
            "})();";

        webView.post(() -> webView.evaluateJavascript(injectionScript, null));
    }

    @Override
    public void onResume() {
        super.onResume();
        setupWebViewBridge();
    }
}
