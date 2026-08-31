package com.onyx.workoutapp;

import android.Manifest;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.util.Log;
import android.view.WindowManager;
import android.webkit.JavascriptInterface;
import android.webkit.WebView;
import android.widget.Toast;
import androidx.activity.OnBackPressedCallback;
import androidx.annotation.NonNull;
import androidx.core.view.WindowCompat;
import androidx.core.view.WindowInsetsCompat;
import androidx.core.view.WindowInsetsControllerCompat;
import com.getcapacitor.BridgeActivity;
import com.getcapacitor.WebViewListener;

public class MainActivity extends BridgeActivity {

    private static final String TAG = "OnyxDebug";
    private static final int PERMISSION_REQUEST_CODE = 1001;
    private boolean isWebViewListenerRegistered = false;

    public class AndroidTimerBridge {
        @JavascriptInterface
        public void startWorkout(String title, long startTimestampMs) {
            // No-op: Notch/background workout session tracking removed
        }

        @JavascriptInterface
        public void stopWorkout() {
            // No-op
        }

        @JavascriptInterface
        public void updateProgress(int completed, int total, int remaining) {
            // No-op
        }

        @JavascriptInterface
        public void startTimer(int durationSeconds, String title) {
            startTimerWithSound(durationSeconds, title, null);
        }

        @JavascriptInterface
        public void startTimerWithSound(int durationSeconds, String title, String soundUri) {
            Log.d(TAG, "AndroidTimer.startTimer called: duration=" + durationSeconds + "s, title=" + title + ", soundUri=" + soundUri);
            try {
                Intent serviceIntent = new Intent(MainActivity.this, TimerService.class);
                serviceIntent.setAction(TimerService.ACTION_START);
                serviceIntent.putExtra(TimerService.EXTRA_DURATION, durationSeconds);
                serviceIntent.putExtra(TimerService.EXTRA_TITLE, (title != null && !title.isEmpty()) ? title : "Recupero in corso");
                if (soundUri != null && !soundUri.isEmpty()) {
                    serviceIntent.putExtra(TimerService.EXTRA_SOUND_URI, soundUri);
                }
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                    startForegroundService(serviceIntent);
                } else {
                    startService(serviceIntent);
                }
                Log.d(TAG, "TimerService started/updated successfully");
            } catch (Exception e) {
                Log.e(TAG, "Error starting/updating TimerService: " + e.getMessage(), e);
            }
        }

        @JavascriptInterface
        public void pauseTimer() {
            Log.d(TAG, "AndroidTimer.pauseTimer called");
            try {
                Intent serviceIntent = new Intent(MainActivity.this, TimerService.class);
                serviceIntent.setAction(TimerService.ACTION_PAUSE);
                startService(serviceIntent);
            } catch (Exception e) {
                Log.e(TAG, "Error pausing TimerService: " + e.getMessage(), e);
            }
        }

        @JavascriptInterface
        public void resumeTimer() {
            Log.d(TAG, "AndroidTimer.resumeTimer called");
            try {
                Intent serviceIntent = new Intent(MainActivity.this, TimerService.class);
                serviceIntent.setAction(TimerService.ACTION_RESUME);
                startService(serviceIntent);
            } catch (Exception e) {
                Log.e(TAG, "Error resuming TimerService: " + e.getMessage(), e);
            }
        }

        @JavascriptInterface
        public void addSeconds(int seconds) {
            Log.d(TAG, "AndroidTimer.addSeconds called: " + seconds);
            try {
                Intent serviceIntent = new Intent(MainActivity.this, TimerService.class);
                serviceIntent.setAction(TimerService.ACTION_ADD_TIME);
                startService(serviceIntent);
            } catch (Exception e) {
                Log.e(TAG, "Error adding seconds to TimerService: " + e.getMessage(), e);
            }
        }

        @JavascriptInterface
        public void stopTimer() {
            Log.d(TAG, "AndroidTimer.stopTimer called");
            try {
                Intent serviceIntent = new Intent(MainActivity.this, TimerService.class);
                serviceIntent.setAction(TimerService.ACTION_STOP);
                startService(serviceIntent);
            } catch (Exception e) {
                Log.e(TAG, "Error stopping TimerService: " + e.getMessage(), e);
            }
        }

        @JavascriptInterface
        public void stopAlarm() {
            Log.d(TAG, "AndroidTimer.stopAlarm called");
            try {
                Intent serviceIntent = new Intent(MainActivity.this, TimerService.class);
                serviceIntent.setAction(TimerService.ACTION_STOP_ALARM);
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
        public void testNotification() {
            Log.d(TAG, "AndroidTimer.testNotification called (5 sec test)");
            startTimer(5, "Test Timer 5s");
        }
    }

    @Override
    public void onCreate(Bundle savedInstanceState) {
        registerPlugin(WorkoutTimerPlugin.class);
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

        // Handle open_timer notification intent
        handleOpenTimerIntent(getIntent());
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        handleOpenTimerIntent(intent);
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
            if (webView != null) {
                webView.addJavascriptInterface(new AndroidTimerBridge(), "AndroidTimer");
                Log.d(TAG, "AndroidTimer JavaScriptInterface bound to WebView");

                injectBridgeScript(webView);
            }

            if (!isWebViewListenerRegistered) {
                getBridge().addWebViewListener(new WebViewListener() {
                    @Override
                    public void onPageLoaded(WebView view) {
                        super.onPageLoaded(view);
                        Log.d(TAG, "WebViewListener.onPageLoaded: re-injecting bridge script");
                        if (view != null) {
                            view.addJavascriptInterface(new AndroidTimerBridge(), "AndroidTimer");
                            injectBridgeScript(view);
                        }
                    }

                    @Override
                    public void onPageStarted(WebView view) {
                        super.onPageStarted(view);
                        Log.d(TAG, "WebViewListener.onPageStarted: re-binding JavascriptInterface");
                        if (view != null) {
                            view.addJavascriptInterface(new AndroidTimerBridge(), "AndroidTimer");
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
            "  " +
            "  /* Periodic storage watcher */" +
            "  if (!window._onyxWatcherStarted) {" +
            "    window._onyxWatcherStarted = true;" +
            "    var lastKnownIsRunning = false;" +
            "    var lastKnownRemainingSec = -1;" +
            "    setInterval(function() {" +
            "      try {" +
            "        bindTimerHooks();" +
            "        var raw = localStorage.getItem('onyx_active_rest_timer');" +
            "        if (raw) {" +
            "          var s = JSON.parse(raw);" +
            "          if (s.isRunning && window.AndroidTimer) {" +
            "            var elapsed = s.startedAt ? (Date.now() - s.startedAt) : 0;" +
            "            var leftMs = Math.max(0, (s.remainingMs || 45000) - elapsed);" +
            "            var sec = Math.ceil(leftMs / 1000);" +
            "            if (!lastKnownIsRunning || Math.abs(sec - lastKnownRemainingSec) > 3) {" +
            "              if (sec > 0) {" +
            "                console.log('[OnyxBridge] Watcher detected active timer: ' + sec + 's');" +
            "                window.AndroidTimer.startTimer(sec, 'Recupero in corso');" +
            "                lastKnownRemainingSec = sec;" +
            "              }" +
            "            }" +
            "          }" +
            "          lastKnownIsRunning = !!s.isRunning;" +
            "        } else {" +
            "          if (lastKnownIsRunning && window.AndroidTimer) {" +
            "            window.AndroidTimer.stopTimer();" +
            "            window.AndroidTimer.stopAlarm();" +
            "          }" +
            "          lastKnownIsRunning = false;" +
            "          lastKnownRemainingSec = -1;" +
            "        }" +
            "      } catch(e) {}" +
            "    }, 1000);" +
            "  }" +
            "})();";

        webView.post(() -> webView.evaluateJavascript(injectionScript, null));
    }

    @Override
    public void onResume() {
        super.onResume();
        setupWebViewBridge();
    }
}
