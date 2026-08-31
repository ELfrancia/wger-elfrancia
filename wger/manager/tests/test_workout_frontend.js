const assert = require('assert');
const fs = require('fs');
const path = require('path');

const logHtmlPath = path.join(__dirname, '..', 'templates', 'workout', 'log_tailwind.html');
const content = fs.readFileSync(logHtmlPath, 'utf8');

// Test 1: L14 - Ensure only 1 custom-timer-modal ID exists in HTML
const modalMatches = content.match(/id=["']custom-timer-modal["']/g);
assert.strictEqual(modalMatches ? modalMatches.length : 0, 1, 'There must be exactly one #custom-timer-modal in log_tailwind.html');

// Test 2: H8 - Script is wrapped in an IIFE and exports OnyxWorkout
assert.ok(content.includes('(function() {'), 'Script must start with IIFE');
assert.ok(content.includes('window.OnyxWorkout = OnyxWorkout;'), 'Script must attach OnyxWorkout to window');
assert.ok(content.includes('window._onyxWorkoutTeardown = teardown;'), 'Script must export teardown handler');

// Test 3: H9 - autoSaveWorkoutSnapshot stops if window._workoutFinished is true
assert.ok(content.includes('if (window._workoutFinished) return;'), 'autoSaveWorkoutSnapshot must guard against finished workout');
assert.ok(content.includes('window._workoutFinished = true;'), 'onFinishWorkoutSubmitted must set _workoutFinished flag');

// Test 4: L15 - startSetCountdown correctly sets duration and starts preset
assert.ok(content.includes('function startSetCountdown(btn, evt, exerciseName) {'), 'startSetCountdown function exists');
assert.ok(content.includes('setTimerPreset(seconds);'), 'startSetCountdown must delegate to setTimerPreset');

// Test 5: M13 - collectWorkoutPayload parses numbers strictly and supports mode-time
assert.ok(content.includes('const rawReps = repsInput ? String(repsInput.value).trim().replace(\',\', \'.\') : \'\';'), 'Strict reps parsing');
assert.ok(content.includes('!Number.isFinite(parsedVal) || parsedVal <= 0'), 'Strict positive finite number check');
assert.ok(content.includes("mode: isTimeMode ? 'time' : 'reps'"), 'Exercise mode mapping in payload');

// Test 6: M15 - cleanupActiveStopwatches cleans up dangling intervals
assert.ok(content.includes('function cleanupActiveStopwatches()'), 'cleanupActiveStopwatches function exists');
assert.ok(content.includes('cleanupActiveStopwatches();'), 'cleanupActiveStopwatches called on htmx:afterSwap');

console.log('All Frontend Workout unit tests passed successfully!');
