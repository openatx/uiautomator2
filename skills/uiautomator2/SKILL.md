---
name: uiautomator2
description: >
  Android device automation via uiautomator2. Use this skill whenever the user wants to
  click/tap elements, swipe screens, start or stop apps, press hardware keys, type text,
  take screenshots, inspect UI hierarchy, or perform any actions on an Android device.
---

# uiautomator2

This skill helps you automate Android devices using the `u2cli` provided by the `uiautomator2` Python package.

## General Usage

- Use `u2cli <command> [args]` to run commands.
- Use `u2cli -s <serial> <command> [args]` when multiple Android devices are connected.
- Examples below show only `<command> [args]`; prepend `u2cli` when running them.

## Commands

### Device Commands

- `dump-hierarchy`: Dump current UI hierarchy for analysis and element selection. Prefer the default output first because u2cli compresses it before returning, which is usually enough and works well with `grep`, for example `dump-hierarchy | grep -i "keyword"`. Only use `dump-hierarchy --raw` when you explicitly need the full uncompressed hierarchy.
- `screenshot`: Capture current screen and save to a local file. The output is the file path and size of the screenshot. Example: `screenshot /tmp/screenshot.jpg`.
- `app-current`: Get the current foreground app package name and activity.
- `device-info`: Show device information.
- `window-size`: Show screen window size.
- `shell`: Run a shell command on the device. Use `--timeout <seconds>` to set command timeout. Example: `shell "pm list packages"`.

### App Commands

- `app-start`: Start an application by package name. Options: `--activity <activity>`, `--wait`, `--stop`. Example: `app-start com.android.settings --activity .Settings --wait`.
- `app-list`: List installed packages.
- `app-stop`: Stop an application by package name. Example: `app-stop com.example.app`.
- `app-install`: Install an APK. Example: `app-install ./app-debug.apk`.
- `app-uninstall`: Uninstall an application by package name. Example: `app-uninstall com.example.app`.
- `app-clear`: Clear application data by package name. Example: `app-clear com.example.app`.

### Input Commands

- `press`: Press a hardware or Android key. Example: `press home`.
- `send-keys`: Type text into the focused input. By default it clears before typing; use `--no-clear` to preserve existing text. Example: `send-keys "hello world"`.
- `clear-text`: Clear focused input text. Example: `clear-text`.
- `click`: Click coordinates or a selector. Use `X Y` for coordinates, or selector options like `--text`, `--resource-id`, `--description`, and `--class-name`. Example: `click 500 1200`; ratio example: `click 0.5 0.5`; selector example: `click --text Gmail`.
- `double-click`: Double click coordinates. Options: `--duration <seconds>` for the delay between taps. This command requires `X Y`; selector options are not supported. Example: `double-click 500 1200`; ratio example: `double-click 0.5 0.5`.
- `long-click`: Long click coordinates or a selector. Options: `--duration <seconds>` and `--timeout <seconds>`. Example: `long-click 500 1200`; ratio example: `long-click 0.5 0.5`; selector example: `long-click --text Gmail`.
- `swipe`: Swipe from one coordinate to another. Arguments are `FX FY TX TY`. Options: `--duration <seconds>`, `--steps <number>`, `--scale <number>`. Example: `swipe 500 1800 500 400 --duration 0.3`; ratio example: `swipe 0.5 0.8 0.5 0.2 --duration 0.3`.
- `drag`: Drag from one coordinate to another. Arguments are `SX SY EX EY`. Options: `--duration <seconds>`. Example: `drag 300 1200 800 1200`; ratio example: `drag 0.3 0.5 0.8 0.5`.

### Selector Commands

- `exists`: Check whether a selector exists. Options: `--timeout <seconds>` plus selector options. Example: `exists --text Gmail --timeout 3`.
- `wait`: Wait for a selector to appear. Use `--gone` to wait until it disappears. Options: `--timeout <seconds>` plus selector options. Example: `wait --text Gmail --timeout 10`; gone example: `wait --text Loading --gone --timeout 10`.
- `scroll`: Scroll a selector. Options: `--direction vert|horiz`, `--action forward|backward|toEnd|toBeginning`, `--max-swipes <number>`, `--to-text <text>`, plus selector options. Example: `scroll --scrollable --direction vert --action forward`; scroll-to-text example: `scroll --scrollable --to-text Settings`.

### System UI Commands

- `open-notification`: Open the notification shade.
- `open-quick-settings`: Open quick settings.
- `open-url`: Open a URL on the device. Example: `open-url https://example.com`.

### Common Selector Options

Use these options with selector-based commands such as `click`, `long-click`, `exists`, `wait`, and `scroll`.

- Text selectors: `--text <text>`, `--text-contains <text>`, `--text-matches <regex>`, `--text-starts-with <text>`.
- Description selectors: `--description <text>`, `--description-contains <text>`.
- Resource and class selectors: `--resource-id <id>`, `--class-name <class>`, `--package <package>`.
- State selectors: `--selected`, `--focused`, `--enabled`, `--scrollable`, `--clickable`, `--checked`, `--checkable`.
- Position selectors: `--instance <number>`, `--index <number>`.
- Child selectors: use `--child KEY=VALUE [KEY=VALUE ...]` or child-specific options like `--child-text`, `--child-resource-id`, `--child-class-name`, `--child-clickable`, and `--child-index` to append a child selector level. Example: `click --resource-id com.example:id/list --child text=OK`.
