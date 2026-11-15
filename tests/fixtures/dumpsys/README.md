# dumpsys activity fixtures

Test data for `app_current()`. Files are excerpts of real `adb shell dumpsys
activity activities` output; only unrelated trailing sections were removed.
Each excerpt is contiguous, so the nesting and spacing are exactly as printed by
the device.

## Captured from an emulator

Device: `Pixel_5_API_34_LARGE` AVD, `sdk_gphone64_arm64`, Android 14 (SDK 34).
Captured on 2026-11-15 with:

```bash
adb shell dumpsys activity activities
```

| File | State when captured |
| --- | --- |
| `android14-settings-foreground.txt` | Settings in the foreground, Chrome still alive in a `visible=false` task behind it. |
| `android14-multi-display.txt` | A simulated secondary display (`settings put global overlay_display_devices "1280x720/160"`, display id 2) showing Chrome, while Settings was the primary display task. Android prints display 2 before display 0. |
| `android14-primary-display-without-resumed.txt` | Screen off after `am force-stop com.android.settings` while Chrome was on the simulated secondary display. The launcher task on display 0 is visible but only has `mLastPausedActivity`, no `topResumedActivity`; the tail `ResumedActivity:` belongs to Chrome on display 2. |

## Captured by other people

These are real device outputs published in public reports. The URL is the source
of the excerpt.

| File | Source |
| --- | --- |
| `android13-top-level-resumed.txt` | <https://stackoverflow.com/posts/74851209/revisions> (Android 13+ output where the resumed activity is printed before the task blocks and the task has no `topResumedActivity=` line) |
| `android10-stack.txt` | <http://www.k-beta.com/dump_activity.html> (Android 10 style `Stack #`/`TaskRecord` output, no `visible=` field) |
