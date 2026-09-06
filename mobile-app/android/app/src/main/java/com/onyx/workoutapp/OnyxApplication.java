package com.onyx.workoutapp;

import android.app.Activity;
import android.app.Application;
import android.os.Bundle;
import android.util.Log;

public class OnyxApplication extends Application {

    private static final String TAG = "OnyxDebug";
    private int startedActivityCount = 0;

    @Override
    public void onCreate() {
        super.onCreate();
        Log.i(TAG, "OnyxApplication.onCreate: registering ActivityLifecycleCallbacks");

        registerActivityLifecycleCallbacks(new ActivityLifecycleCallbacks() {
            @Override
            public void onActivityCreated(Activity activity, Bundle savedInstanceState) {
                Log.d(TAG, "Lifecycle.onActivityCreated: " + activity.getClass().getSimpleName());
            }

            @Override
            public void onActivityStarted(Activity activity) {
                startedActivityCount++;
                Log.d(TAG, "Lifecycle.onActivityStarted: " + activity.getClass().getSimpleName() + " (count=" + startedActivityCount + ")");
                OnyxLiveService.setAppInForeground(true, "ActivityLifecycle.onActivityStarted");
            }

            @Override
            public void onActivityResumed(Activity activity) {
                Log.d(TAG, "Lifecycle.onActivityResumed: " + activity.getClass().getSimpleName());
                OnyxLiveService.setAppInForeground(true, "ActivityLifecycle.onActivityResumed");
            }

            @Override
            public void onActivityPaused(Activity activity) {
                Log.d(TAG, "Lifecycle.onActivityPaused: " + activity.getClass().getSimpleName());
            }

            @Override
            public void onActivityStopped(Activity activity) {
                startedActivityCount = Math.max(0, startedActivityCount - 1);
                Log.d(TAG, "Lifecycle.onActivityStopped: " + activity.getClass().getSimpleName() + " (count=" + startedActivityCount + ")");
                if (startedActivityCount == 0) {
                    OnyxLiveService.setAppInForeground(false, "ActivityLifecycle.onActivityStopped");
                }
            }

            @Override
            public void onActivitySaveInstanceState(Activity activity, Bundle outState) {}

            @Override
            public void onActivityDestroyed(Activity activity) {
                Log.d(TAG, "Lifecycle.onActivityDestroyed: " + activity.getClass().getSimpleName() + " finishing=" + activity.isFinishing());
                if (activity.isFinishing() || startedActivityCount <= 0) {
                    startedActivityCount = 0;
                    OnyxLiveService.setAppInForeground(false, "ActivityLifecycle.onActivityDestroyed");
                }
            }
        });
    }
}
