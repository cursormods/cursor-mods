import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

GlassPanel {
    id: root
    property string kind: "windows"
    property string title: "Windows Cursor"
    readonly property string formats: kind === "cursor" ? "PNG / ZIP / folder" : kind === "font" ? "TTF / OTF / ZIP / folder" : kind === "sky" ? "TEX pack / ZIP / folder" : kind === "ui" ? "Textures folder / ZIP" : "CUR / ANI pack / ZIP / folder"
    padding: 16
    Column {
        width: parent.width; spacing: 10
        Column {
            width: parent.width; spacing: 5
            Text { text: root.title; color: backend.colors.ink; font.family: "Segoe UI"; font.pixelSize: 17; font.weight: Font.DemiBold }
        }
        Rectangle {
            width: parent.width; height: 60; radius: 12
            color: Qt.alpha(backend.colors.ink, drop.containsDrag ? .12 : .035)
            border.color: Qt.alpha(backend.colors.ink, drop.containsDrag ? .65 : .19)
            border.width: 1
            Column {
                anchors.centerIn: parent; spacing: 5
                Text { anchors.horizontalCenter: parent.horizontalCenter; text: drop.containsDrag ? "Release to import" : "Drop files"; color: backend.colors.ink; font.family: "Segoe UI"; font.pixelSize: 13; font.weight: Font.Medium }
                Text { anchors.horizontalCenter: parent.horizontalCenter; text: root.formats; color: backend.colors.muted; font.family: "Segoe UI"; font.pixelSize: 11 }
            }
            DropArea { id: drop; objectName: "drop_" + root.kind; anchors.fill: parent; enabled: !backend.busy; onDropped: function(event) { if (event.hasUrls) { backend.importPaths(root.kind, event.urls); event.acceptProposedAction() } } }
        }
        Row {
            spacing: 10
            GlassButton { text: "Import"; compact: true; iconName: "plus"; primary: true; enabled: !backend.busy; onClicked: backend.browse(root.kind, false) }
            GlassButton { text: "Folder"; compact: true; iconName: "folder"; enabled: !backend.busy; onClicked: backend.browse(root.kind, true) }
        }
        Flickable {
            id: library
            width: parent.width; height: Math.min(92, entries.height)
            contentWidth: width; contentHeight: entries.height
            clip: true; boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
            Column {
            id: entries
            width: parent.width; spacing: 6
            Repeater {
                model: backend.packs[root.kind] || []
                Rectangle {
                    required property var modelData
                    width: parent.width; height: 43; radius: 10
                    color: Qt.alpha(backend.colors.ink, .045)
                    RowLayout {
                        anchors.fill: parent; anchors.margins: 8; spacing: 8
                        Rectangle { width: 5; height: 5; radius: 3; color: modelData.active ? backend.colors.accent : backend.colors.muted }
                        Text { text: modelData.name; color: backend.colors.ink; font.family: "Segoe UI"; font.pixelSize: 13; elide: Text.ElideRight; Layout.fillWidth: true }
                        Text { visible: modelData.active && root.width > 570; text: "APPLIED"; color: backend.colors.muted; font.family: "Segoe UI"; font.pixelSize: 9; font.letterSpacing: 1 }
                        GlassButton { compact: true; text: modelData.active ? "Unapply" : "Apply"; enabled: !backend.busy; onClicked: modelData.active ? backend.unapply(root.kind) : backend.applyPack(root.kind, modelData.name) }
                        GlassButton { compact: true; text: "Remove"; enabled: !backend.busy; onClicked: backend.removePack(root.kind, modelData.name) }
                    }
                }
            }
            }
        }
    }
}
