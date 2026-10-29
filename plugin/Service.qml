import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Wayland

// Shake-to-find cursor. cursor-bridge.py streams pointer positions from
// Hyprland; this service detects a shake from how much path the pointer covers
// inside a small area. While the shake lasts it hides the real cursor and
// draws an arrow that grows on an overlay, then hands back to the real one.
//
// Resizing the real cursor with `setcursor` does not redraw the cursor that is
// already showing (it only changes when the app under it sets a new shape),
// and every step reloads the whole cursor theme, so the overlay does the
// scaling instead.
Item {
  id: root

  readonly property string pluginId: "io.github.robbieuk1.optimouse-shake"
  readonly property string shellConfigPath: Quickshell.env("HOME") + "/.config/optimouse/settings.json"
  readonly property string bridgePath: decodeURIComponent(
    String(Qt.resolvedUrl("cursor-bridge.py")).replace(/^file:\/\//, ""))

  // Settings are read from ~/.config/optimouse/settings.json,
  // updated by the OptiMouse GTK settings app.
  property bool shakeEnabled: true
  property bool followTheme: true
  property string selectedColor: "#71FACC"
  property string lastPreviewToken: ""
  property bool settingsLoaded: false
  property int maxSize: 96
  property real sensitivity: 2.5
  property int growMs: 300
  property int holdMs: 500
  property int shrinkMs: 350
  property int baseSize: root.environmentSize()

  // Shake detection works on the last few hundred milliseconds of movement.
  readonly property int shakeWindowMs: 500
  readonly property int minimumShakeSpan: 80
  readonly property int minimumReversals: 2

  property var samples: []
  property real cursorX: 0
  property real cursorY: 0
  property bool cursorReady: false
  property real level: 0
  property bool animating: false
  property double lastShakeMs: 0
  property double previewUntilMs: 0
  property double lastTickMs: 0
  property bool cursorHidden: false
  // Sampled from the current cursor theme by the bridge; these match the arrow
  // drawn by the cursor themes Omarchy ships with until the first reply lands.
  property color cursorFill: "#000000"
  property color cursorStroke: "#ffffff"

  readonly property bool enlarged: root.level > 0 && root.cursorReady
  readonly property real currentSize: root.baseSize
    + (root.maxSize - root.baseSize) * (1 - Math.pow(1 - root.level, 3))

  function environmentSize() {
    var size = Number(Quickshell.env("HYPRCURSOR_SIZE") || Quickshell.env("XCURSOR_SIZE"))
    return isFinite(size) && size > 0 ? Math.round(size) : 24
  }

  function numberSetting(entry, key, fallback, minimum, maximum) {
    var value = Number(entry[key])
    if (entry[key] === undefined || !isFinite(value)) value = fallback
    return Math.max(minimum, Math.min(maximum, value))
  }

  // The entry lives in the bar layout when the bar widget is placed, and in
  // `plugins` otherwise.
  function findEntry(config) {
    var lists = [Array.isArray(config.plugins) ? config.plugins : []]
    var layout = config.bar && config.bar.layout ? config.bar.layout : {}
    for (var section in layout) {
      if (Array.isArray(layout[section])) lists.push(layout[section])
    }

    for (var i = 0; i < lists.length; i++) {
      for (var j = 0; j < lists[i].length; j++) {
        if (lists[i][j] && lists[i][j].id === root.pluginId) return lists[i][j]
      }
    }
    return {}
  }

  function applySettings(raw) {
    var entry
    try {
      entry = JSON.parse(String(raw || "{}"))
    } catch (error) {
      // Keep the current settings while shell.json is mid-edit.
      return
    }

    root.baseSize = Math.round(root.numberSetting(entry, "size", root.environmentSize(), 8, 256))
    root.maxSize = Math.round(root.numberSetting(entry, "shake_max", 160, root.baseSize, 256))
    root.sensitivity = root.numberSetting(entry, "sensitivity", 2.5, 1.5, 10)
    root.growMs = Math.round(root.numberSetting(entry, "growMs", 300, 16, 5000))
    root.holdMs = Math.round(root.numberSetting(entry, "holdMs", 500, 0, 10000))
    root.shrinkMs = Math.round(root.numberSetting(entry, "shrinkMs", 350, 16, 5000))
    root.shakeEnabled = entry.shake === undefined ? false : Boolean(entry.shake)
    root.followTheme = entry.follow_theme === undefined ? true : Boolean(entry.follow_theme)
    var chosen = String(entry.color || "#71FACC")
    root.selectedColor = /^#[0-9A-Fa-f]{6}$/.test(chosen) ? chosen : "#71FACC"
    if (!root.followTheme) {
      root.cursorFill = root.selectedColor
      root.cursorStroke = "#121c18"
    } else root.refreshCursorColors()
    var nextPreview = String(entry.preview_token || "")
    if (!root.settingsLoaded) {
      root.lastPreviewToken = nextPreview
      root.settingsLoaded = true
    } else if (nextPreview !== "" && nextPreview !== root.lastPreviewToken) {
      root.lastPreviewToken = nextPreview
      root.preview()
    }
  }

  // Grow to the current maximum and back, so the size can be judged while a
  // slider is moved.
  function preview() {
    root.previewUntilMs = Date.now() + root.growMs
    root.animating = true
  }

  function addSample(line) {
    var parts = String(line || "").trim().split(/\s+/)
    var x = Number(parts[0])
    var y = Number(parts[1])
    if (parts.length !== 2 || !isFinite(x) || !isFinite(y)) return

    root.cursorX = x
    root.cursorY = y
    root.cursorReady = true

    var next = root.samples
    next.push({ x: x, y: y, t: Date.now() })
    root.samples = next
    root.animating = true
  }

  function pruneSamples(now) {
    var next = root.samples
    while (next.length > 0 && now - next[0].t > root.shakeWindowMs) next.shift()
    root.samples = next
  }

  // A shake covers far more distance than the box it stays inside, and keeps
  // turning back. One fast flick is long but straight; a single there-and-back
  // has only one reversal.
  function isShaking() {
    var points = root.samples
    if (points.length < 4) return false

    var distance = 0
    var left = points[0].x, right = points[0].x
    var top = points[0].y, bottom = points[0].y
    var reversalsX = 0, reversalsY = 0
    var lastDx = 0, lastDy = 0

    for (var i = 1; i < points.length; i++) {
      var dx = points[i].x - points[i - 1].x
      var dy = points[i].y - points[i - 1].y
      distance += Math.sqrt(dx * dx + dy * dy)
      left = Math.min(left, points[i].x)
      right = Math.max(right, points[i].x)
      top = Math.min(top, points[i].y)
      bottom = Math.max(bottom, points[i].y)

      // Ignore jitter when counting changes of direction.
      if (Math.abs(dx) >= 4) {
        if (lastDx !== 0 && (dx > 0) !== (lastDx > 0)) reversalsX++
        lastDx = dx
      }
      if (Math.abs(dy) >= 4) {
        if (lastDy !== 0 && (dy > 0) !== (lastDy > 0)) reversalsY++
        lastDy = dy
      }
    }

    var span = Math.sqrt((right - left) * (right - left) + (bottom - top) * (bottom - top))
    if (span < root.minimumShakeSpan) return false
    if (Math.max(reversalsX, reversalsY) < root.minimumReversals) return false
    return distance / span >= root.sensitivity
  }

  function tick() {
    var now = Date.now()
    var dt = root.lastTickMs > 0 ? Math.min(100, now - root.lastTickMs) : 16
    root.lastTickMs = now

    root.pruneSamples(now)
    if ((root.shakeEnabled && root.isShaking()) || now < root.previewUntilMs) root.lastShakeMs = now

    // Grow for as long as the shake continues, so a longer shake gets a
    // bigger cursor, then hold briefly before shrinking back.
    if (now - root.lastShakeMs < 60) root.level = Math.min(1, root.level + dt / root.growMs)
    else if (now - root.lastShakeMs > root.holdMs) root.level = Math.max(0, root.level - dt / root.shrinkMs)

    if (root.level === 0 && root.samples.length === 0 && now >= root.previewUntilMs) {
      root.animating = false
      root.lastTickMs = 0
    }
  }

  function setCursorHidden(hidden) {
    if (hidden === root.cursorHidden) return
    root.cursorHidden = hidden
    if (bridge.running) bridge.write(hidden ? "cursor hide\n" : "cursor show\n")
  }

  // The theme can change at runtime, so ask again when a shake starts; the
  // startup request only fills in the colors for the first shake.
  function refreshCursorColors() {
    if (bridge.running) bridge.write("colors\n")
  }

  function handleLine(line) {
    var parts = String(line || "").trim().split(/\s+/)
    if (parts.length === 3 && parts[0] === "colors") {
      if (root.followTheme) {
        root.cursorFill = parts[1]
        root.cursorStroke = parts[2]
      }
      return
    }
    root.addSample(line)
  }

  onEnlargedChanged: {
    root.setCursorHidden(root.enlarged)
    if (root.enlarged) root.refreshCursorColors()
  }

  Timer {
    interval: 8
    repeat: true
    running: root.animating
    onTriggered: root.tick()
  }

  // Mapped only while enlarged, so an idle overlay never sits above
  // fullscreen apps.
  Variants {
    model: Quickshell.screens

    PanelWindow {
      id: overlay
      required property var modelData
      screen: modelData
      visible: root.enlarged && cursorOnScreen
      color: "transparent"
      anchors {
        top: true
        bottom: true
        left: true
        right: true
      }

      WlrLayershell.namespace: root.pluginId
      WlrLayershell.layer: WlrLayer.Overlay
      WlrLayershell.keyboardFocus: WlrKeyboardFocus.None
      exclusionMode: ExclusionMode.Ignore
      mask: Region {}

      readonly property bool cursorOnScreen: root.cursorX >= modelData.x
        && root.cursorX < modelData.x + modelData.width
        && root.cursorY >= modelData.y
        && root.cursorY < modelData.y + modelData.height

      CursorArrow {
        x: root.cursorX - overlay.modelData.x
        y: root.cursorY - overlay.modelData.y
        size: root.currentSize
        fillColor: root.cursorFill
        strokeColor: root.cursorStroke
      }
    }
  }

  Process {
    id: bridge
    command: ["python3", "-u", root.bridgePath]
    running: true
    stdinEnabled: true

    stdout: SplitParser {
      onRead: line => root.handleLine(line)
    }

    // The bridge shows the cursor again when it exits, so a restarted bridge
    // starts from a visible cursor.
    onExited: {
      root.cursorHidden = false
      bridgeRestart.restart()
    }
    onRunningChanged: if (running) {
      root.refreshCursorColors()
      if (root.enlarged) root.setCursorHidden(true)
    }
  }

  Timer {
    id: bridgeRestart
    interval: 2000
    onTriggered: bridge.running = true
  }

  FileView {
    path: root.shellConfigPath
    watchChanges: true
    printErrors: false
    onLoaded: root.applySettings(text())
    // text() is stale inside the change signal, so reload and parse on load.
    onFileChanged: reload()
  }

  Component.onDestruction: {
    if (root.cursorHidden)
      Quickshell.execDetached(["hyprctl", "eval", "hl.config({ cursor = { invisible = false } })"])
  }
}
