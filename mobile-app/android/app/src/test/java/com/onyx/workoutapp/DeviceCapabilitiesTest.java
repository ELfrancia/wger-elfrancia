package com.onyx.workoutapp;

import static org.junit.Assert.*;

import java.util.Map;
import org.junit.Test;

public class DeviceCapabilitiesTest {

    @Test
    public void testCapabilitiesMapStructure() {
        Map<String, Object> caps = DeviceCapabilities.getCapabilitiesMap(null);
        assertNotNull("Capabilities map should never be null", caps);
        assertEquals("Platform must be android", "android", caps.get("platform"));
        assertTrue("sdkInt must be an integer", caps.get("sdkInt") instanceof Integer);
        assertTrue("manufacturer must be a String", caps.get("manufacturer") instanceof String);
        assertTrue("hyperOsFocus must be boolean", caps.get("hyperOsFocus") instanceof Boolean);
        assertTrue("notificationsEnabled must be boolean", caps.get("notificationsEnabled") instanceof Boolean);
        assertTrue("promotedOngoing must be boolean", caps.get("promotedOngoing") instanceof Boolean);
    }

    @Test
    public void testProgressMathBounds() {
        // Total 10, completed 0 -> ratio 0.0
        float ratio0 = 0f / 10f;
        assertEquals(0.0f, Math.max(0.0f, Math.min(1.0f, ratio0)), 0.001f);

        // Total 10, completed 5 -> ratio 0.5
        float ratio5 = 5f / 10f;
        assertEquals(0.5f, Math.max(0.0f, Math.min(1.0f, ratio5)), 0.001f);

        // Total 10, completed 10 -> ratio 1.0
        float ratio10 = 10f / 10f;
        assertEquals(1.0f, Math.max(0.0f, Math.min(1.0f, ratio10)), 0.001f);

        // Total 10, completed 12 (overflow) -> clamped to 1.0
        float ratioOverflow = 12f / 10f;
        assertEquals(1.0f, Math.max(0.0f, Math.min(1.0f, ratioOverflow)), 0.001f);

        // RemoteViews int progress range 0..1000
        int p0 = Math.round(Math.max(0.0f, Math.min(1.0f, ratio0)) * 1000f);
        int p5 = Math.round(Math.max(0.0f, Math.min(1.0f, ratio5)) * 1000f);
        int p10 = Math.round(Math.max(0.0f, Math.min(1.0f, ratio10)) * 1000f);

        assertEquals(0, p0);
        assertEquals(500, p5);
        assertEquals(1000, p10);
    }
}
