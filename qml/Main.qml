import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window

Window {
    id: window
    objectName: "mainWindow"
    visible: true
    width: Math.min(Screen.desktopAvailableWidth, Math.max(720, backend.settings.window_width || 940))
    height: Math.min(Screen.desktopAvailableHeight, Math.max(560, backend.settings.window_height || 790))
    minimumWidth: 720; minimumHeight: 560
    color: "transparent"
    title: backend.testMode ? "Cursor Mods · Isolated test" : "Cursor Mods"
    flags: Qt.Window | Qt.FramelessWindowHint | (backend.settings.always_on_top ? Qt.WindowStaysOnTopHint : 0)
    property int pageIndex: 0
    readonly property bool maximized: visibility === Window.Maximized
    readonly property real gutter: width < 800 ? 25 : 38
    onClosing: function(event) { event.accepted = backend.requestClose() }
    onWidthChanged: resizeTimer.restart()
    onHeightChanged: resizeTimer.restart()
    onVisibilityChanged: resizeTimer.restart()
    Timer { id: resizeTimer; interval: 20; onTriggered: { backend.updateCorners(); backend.rememberSize(window.width, window.height) } }
    function toggleMaximize() { maximized ? showNormal() : showMaximized() }

    Rectangle {
        anchors.fill: parent
        radius: window.maximized ? 0 : 26
        color: Qt.alpha(backend.colors.base, backend.settings.glass_opacity)
        border.width: 1
        border.color: Qt.rgba(1,1,1, backend.colors.light ? .7 : .36)
        Rectangle {
            anchors.fill: parent; anchors.margins: 1; radius: parent.radius
            gradient: Gradient {
                GradientStop { position: 0; color: "#25ffffff" }
                GradientStop { position: .30; color: "#03ffffff" }
                GradientStop { position: 1; color: "#13000000" }
            }
        }
    }
    Item {
        id: titleBar
        width: parent.width; height: 61
        MouseArea { anchors.fill: parent; onPressed: window.startSystemMove(); onDoubleClicked: window.toggleMaximize() }
        Row {
            x: window.gutter; anchors.verticalCenter: parent.verticalCenter; spacing: 10
            Icon { name: "kitty"; width: 20; height: 20 }
            Text { text: backend.testMode ? "Cursor Mods · Test window" : "Cursor Mods"; color: backend.colors.ink; font.family: "Segoe UI"; font.pixelSize: 13; font.weight: Font.DemiBold }
        }
        Row {
            anchors.right: parent.right; anchors.rightMargin: 17; anchors.verticalCenter: parent.verticalCenter; spacing: 3
            Repeater {
                model: ["minimize", "maximize", "close"]
                Rectangle {
                    required property string modelData
                    width: 36; height: 32; radius: 10
                    color: hit.containsMouse ? modelData === "close" ? "#aaad4545" : Qt.alpha(backend.colors.ink, .12) : "transparent"
                    Icon { anchors.centerIn: parent; name: modelData; width: 15; height: 15 }
                    MouseArea {
                        id: hit; anchors.fill: parent; hoverEnabled: true
                        onClicked: modelData === "close" ? window.close() : modelData === "maximize" ? window.toggleMaximize() : window.showMinimized()
                    }
                }
            }
        }
    }
    Item {
        id: header
        x: window.gutter; y: 72; width: parent.width - window.gutter * 2; height: 42
        Column {
            width: parent.width; spacing: 5
            Text { text: ["Roblox", "Kitty", "Settings"][window.pageIndex]; color: backend.colors.ink; font.family: "Segoe UI"; font.pixelSize: 30; font.weight: Font.DemiBold }
        }
    }
    Flickable {
        id: scroll
        objectName: "pageScroll"
        x: window.gutter - 10; y: 130
        width: parent.width - window.gutter * 2 + 20
        height: Math.max(80, dock.y - y - statusArea.height - 13)
        contentWidth: width
        contentHeight: page.height + 28
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        flickableDirection: Flickable.VerticalFlick
        Loader {
            id: page
            x: 10; y: 3; width: parent.width - 20
            sourceComponent: [robloxPage, kittyPage, settingsPage][window.pageIndex]
            onLoaded: { scroll.contentY = 0; pageEnter.restart() }
            NumberAnimation { id: pageEnter; target: page; property: "opacity"; from: 0; to: 1; duration: 180 }
        }
        ScrollBar.vertical: ScrollBar {
            id: themedScroll
            width: 5; padding: 0; hoverEnabled: true; minimumSize: .08
            policy: ScrollBar.AsNeeded
            contentItem: Rectangle { implicitWidth: 5; radius: 3; color: Qt.alpha(backend.colors.ink, .45); opacity: themedScroll.active || themedScroll.hovered ? 1 : 0; Behavior on opacity { NumberAnimation { duration: 220 } } }
            background: Item {}
        }
    }
    Item {
        id: statusArea
        x: window.gutter; width: window.width - window.gutter * 2
        y: dock.y - height - 5
        height: Math.min(53, Math.max(22, statusText.implicitHeight + 8))
        Rectangle {
            anchors.fill: parent; radius: 10
            visible: backend.statusKind === "error" || backend.busy
            color: Qt.alpha(backend.colors.base, .94)
            border.color: backend.statusKind === "error" ? "#ba8c6f" : Qt.alpha(backend.colors.ink, .16)
        }
        Rectangle {
            x: 11; y: 10; width: 5; height: 5; radius: 3
            color: backend.statusKind === "error" ? "#e7a481" : backend.colors.accent
            SequentialAnimation on opacity { running: backend.busy; loops: Animation.Infinite; NumberAnimation { to: .25; duration: 650 } NumberAnimation { to: 1; duration: 650 } }
        }
        Text {
            id: statusText
            x: 25; y: 4; width: parent.width - 35
            text: backend.status; color: backend.colors.ink
            font.family: "Segoe UI"; font.pixelSize: 11
            wrapMode: Text.WordWrap; maximumLineCount: 3; elide: Text.ElideRight
        }
    }
    LiquidDock {
        id: dock
        objectName: "bottomDock"
        width: Math.min(410, parent.width - 100); height: 106
        anchors.horizontalCenter: parent.horizontalCenter
        y: parent.height - height - 19
        currentIndex: window.pageIndex
        onSelected: function(index) { window.pageIndex = index }
    }
    Item {
        id: keyCapture
        focus: backend.recording.length > 0
        Keys.onPressed: function(event) { if (backend.recording.length > 0) { backend.recordKey(event.key, event.modifiers); event.accepted = true } }
        Connections { target: backend; function onChanged() { if (backend.recording.length > 0) keyCapture.forceActiveFocus() } }
    }
    Repeater {
        model: [Qt.LeftEdge, Qt.TopEdge, Qt.RightEdge, Qt.BottomEdge, Qt.TopEdge | Qt.LeftEdge, Qt.TopEdge | Qt.RightEdge, Qt.BottomEdge | Qt.LeftEdge, Qt.BottomEdge | Qt.RightEdge]
        MouseArea {
            required property int index
            required property int modelData
            enabled: !window.maximized
            x: index === 2 || index === 5 || index === 7 ? window.width - width : 0
            y: index === 3 || index === 6 || index === 7 ? window.height - height : 0
            width: index >= 4 ? 15 : index === 0 || index === 2 ? 6 : window.width
            height: index >= 4 ? 15 : index === 1 || index === 3 ? 6 : window.height
            cursorShape: index >= 4 ? index === 4 || index === 7 ? Qt.SizeFDiagCursor : Qt.SizeBDiagCursor : index === 0 || index === 2 ? Qt.SizeHorCursor : Qt.SizeVerCursor
            onPressed: window.startSystemResize(modelData)
        }
    }

    Component {
        id: windowsPage
        Column {
            spacing: 20
            PackSection { objectName: "windowsCursorSection"; width: parent.width }
            GlassPanel {
                width: parent.width
                Column {
                    width: parent.width; spacing: 17
                    SettingRow { width: parent.width; title: "Windows cursor size"; Text { text: backend.settings.cursor_size + " px"; color: backend.colors.ink; font.family: "Segoe UI"; font.pixelSize: 14 } }
                    GlassSlider { width: parent.width; from: 16; to: 96; stepSize: 1; value: backend.settings.cursor_size; onMoved: backend.setSetting("cursor_size", value) }
                    Row { spacing: 10; GlassButton { text: "Reset size"; onClicked: backend.resetCursorSize() } GlassButton { text: "Restore Windows cursors"; iconName: "restore"; enabled: !backend.busy; onClicked: backend.unapply("windows") } }
                }
            }
        }
    }
    Component {
        id: robloxPage
        Column {
            spacing: 16
            GridLayout {
                id: robloxGrid
                objectName: "robloxGrid"
                width: parent.width; columns: 2; rowSpacing: 16; columnSpacing: 16
                Repeater {
                    model: [{kind: "cursor", title: "Roblox Cursor"}, {kind: "ui", title: "UI Wheel"}, {kind: "sky", title: "Skybox"}, {kind: "font", title: "Font"}]
                    PackSection {
                        required property var modelData
                        objectName: "robloxSection_" + modelData.kind
                        Layout.fillWidth: true; Layout.preferredWidth: (robloxGrid.width - 16) / 2; Layout.alignment: Qt.AlignTop
                        kind: modelData.kind; title: modelData.title
                    }
                }
            }
            RowLayout {
                width: parent.width
                GlassButton { text: "Restore Roblox"; iconName: "restore"; enabled: !backend.busy; onClicked: backend.restoreRoblox() }
                Text { Layout.fillWidth: true; Layout.leftMargin: 8; text: "Restart Roblox after changes."; wrapMode: Text.WordWrap; color: backend.colors.muted; font.family: "Segoe UI"; font.pixelSize: 11 }
            }
        }
    }
    Component {
        id: kittyPage
        Column {
            spacing: 20
            GlassPanel {
                width: parent.width
                Column {
                    width: parent.width; spacing: 25
                    SettingRow { width: parent.width; title: "Enable Kitty"; description: "Follow the pointer."; GlassToggle { checked: backend.settings.enabled; onToggled: backend.setSetting("enabled", checked) } }
                    Rectangle { width: parent.width; height: 1; color: Qt.alpha(backend.colors.ink, .10) }
                    Column {
                        width: parent.width; spacing: 10
                        SettingRow { width: parent.width; title: "Kitty size"; Text { text: backend.settings.cat_size + " px"; color: backend.colors.ink; font.family: "Segoe UI"; font.pixelSize: 13 } }
                        GlassSlider { width: parent.width; from: 16; to: 96; stepSize: 1; value: backend.settings.cat_size; onMoved: backend.setSetting("cat_size", value) }
                    }
                    Column {
                        width: parent.width; spacing: 10
                        SettingRow { width: parent.width; title: "Following speed"; Text { text: backend.settings.speed; color: backend.colors.ink; font.family: "Segoe UI"; font.pixelSize: 13 } }
                        GlassSlider { width: parent.width; from: 2; to: 30; stepSize: 1; value: backend.settings.speed; onMoved: backend.setSetting("speed", value) }
                    }
                    SettingRow { width: parent.width; title: "Pause Kitty"; GlassButton { text: "Freeze / resume"; iconName: "pause"; enabled: backend.settings.enabled; onClicked: backend.freezeKitty() } }
                    SettingRow { width: parent.width; title: "Freeze shortcut"; description: backend.recording === "freeze_hotkey" ? "Press your shortcut. Esc cancels." : "Works while you use other apps."; GlassButton { text: backend.recording === "freeze_hotkey" ? "Listening…" : backend.settings.freeze_hotkey; onClicked: backend.captureHotkey("freeze_hotkey") } }
                }
            }
        }
    }
    Component {
        id: settingsPage
        Column {
            spacing: 20
            GlassPanel {
                width: parent.width
                Column {
                    width: parent.width; spacing: 22
                    Text { text: "Appearance"; color: backend.colors.ink; font.family: "Segoe UI"; font.pixelSize: 18; font.weight: Font.DemiBold }
                    Grid {
                        width: parent.width; columns: 3; rowSpacing: 10; columnSpacing: 10
                        Repeater {
                            model: backend.themes
                            Rectangle {
                                required property int index
                                required property string modelData
                                width: (parent.width - 20) / 3; height: 49; radius: 12
                                color: Qt.alpha(backend.colors.ink, backend.settings.theme === modelData ? .12 : .035)
                                border.color: backend.settings.theme === modelData ? Qt.alpha(backend.colors.ink, .65) : Qt.alpha(backend.colors.ink, .12)
                                Row {
                                    anchors.centerIn: parent; spacing: 9
                                    Rectangle { width: 15; height: 15; radius: 8; color: ["#383739", "#efede8", "#314d66", "#584361", "#3f6250", "#e6bbce"][index]; border.color: "#80ffffff" }
                                    Text { text: modelData; color: backend.colors.ink; font.family: "Segoe UI"; font.pixelSize: 12 }
                                }
                                MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: backend.setTheme(modelData) }
                            }
                        }
                    }
                    Column {
                        width: parent.width; spacing: 9
                        SettingRow { width: parent.width; title: "Glass opacity"; Text { text: Math.round(backend.settings.glass_opacity * 100) + "%"; color: backend.colors.ink; font.family: "Segoe UI"; font.pixelSize: 14 } }
                        GlassSlider { objectName: "opacitySlider"; width: parent.width; from: .2; to: 1; stepSize: .01; value: backend.settings.glass_opacity; onMoved: backend.setSetting("glass_opacity", value) }
                    }
                }
            }
            GlassPanel {
                width: parent.width
                Column {
                    width: parent.width; spacing: 23
                    SettingRow { width: parent.width; title: "Always on top"; GlassToggle { checked: backend.settings.always_on_top; onToggled: backend.setSetting("always_on_top", checked) } }
                    SettingRow { width: parent.width; title: "Start with Windows"; GlassToggle { checked: backend.settings.startup; onToggled: backend.setSetting("startup", checked) } }
                    SettingRow { width: parent.width; title: "Show / hide shortcut"; description: backend.recording === "toggle_hotkey" ? "Press a shortcut. Esc cancels." : ""; GlassButton { text: backend.recording === "toggle_hotkey" ? "Listening…" : backend.settings.toggle_hotkey; onClicked: backend.captureHotkey("toggle_hotkey") } }
                }
            }
            Loader { width: parent.width; sourceComponent: windowsPage }
        }
    }
}
