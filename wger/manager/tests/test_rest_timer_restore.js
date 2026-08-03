const fs = require('fs');
const assert = require('assert');

const template = fs.readFileSync('wger/manager/templates/workout/log_tailwind.html', 'utf8');
const start = template.indexOf('function restoreTimerFromStorage()');
assert.notStrictEqual(start, -1, 'restoreTimerFromStorage must exist');
let depth = 0;
let end = start;
for (; end < template.length; end += 1) {
  if (template[end] === '{') depth += 1;
  if (template[end] === '}' && --depth === 0) {
    end += 1;
    break;
  }
}

let defaultDuration = 45;
let durationSeconds = 45;
let remainingMs = 45_000;
let startedAt = 'sentinel';
let isRunning = true;
let hasNotifiedZero = false;
let displayUpdated = false;
const expiredState = {
  durationSeconds: 45,
  remainingMs: 0,
  startedAt: null,
  isRunning: false,
  hasNotifiedZero: true,
  expiredAt: 123,
};
global.localStorage = { getItem: () => JSON.stringify(expiredState) };
global.updateDisplay = () => { displayUpdated = true; };
global.startCountdown = () => { throw new Error('expired timer must not restart'); };
global.saveTimerStateToStorage = () => {};

eval(template.slice(start, end));
restoreTimerFromStorage();

assert.strictEqual(remainingMs, 0, 'expired timer must restore 00:00');
assert.strictEqual(isRunning, false, 'expired timer must remain stopped');
assert.strictEqual(startedAt, null, 'expired timer must not gain a start time');
assert.strictEqual(hasNotifiedZero, true, 'expired notification state must persist');
assert.strictEqual(displayUpdated, true, 'restored expired state must render');
