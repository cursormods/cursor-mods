import QtQuick
import QtQuick.Shapes
import QtQuick.Effects

Item {
    id: root
    property int currentIndex: 0
    signal selected(int index)
    readonly property real cellWidth: (width - 32) / 3
    property real indicatorX: 16 + (currentIndex + .5) * cellWidth
    Behavior on indicatorX { NumberAnimation { duration: 300; easing.type: Easing.OutCubic } }
    implicitHeight: 106
    Shape {
        id: dock
        anchors.fill: parent
        antialiasing: true
        preferredRendererType: Shape.CurveRenderer
        layer.enabled: true
        layer.effect: MultiEffect { shadowEnabled: true; shadowColor: "#40000000"; shadowVerticalOffset: 8; shadowBlur: .7 }
        ShapePath {
            strokeColor: Qt.rgba(1,1,1, backend.colors.light ? .7 : .34)
            strokeWidth: 1
            fillColor: Qt.alpha(backend.colors.base, .87)
            startX: 23; startY: 30
            PathLine { x: root.indicatorX - 49; y: 30 }
            PathCubic { x: root.indicatorX; y: 66; control1X: root.indicatorX - 30; control1Y: 30; control2X: root.indicatorX - 35; control2Y: 66 }
            PathCubic { x: root.indicatorX + 49; y: 30; control1X: root.indicatorX + 35; control1Y: 66; control2X: root.indicatorX + 30; control2Y: 30 }
            PathLine { x: root.width - 23; y: 30 }
            PathQuad { x: root.width - 1; y: 52; controlX: root.width - 1; controlY: 30 }
            PathLine { x: root.width - 1; y: root.height - 23 }
            PathQuad { x: root.width - 23; y: root.height - 1; controlX: root.width - 1; controlY: root.height - 1 }
            PathLine { x: 23; y: root.height - 1 }
            PathQuad { x: 1; y: root.height - 23; controlX: 1; controlY: root.height - 1 }
            PathLine { x: 1; y: 52 }
            PathQuad { x: 23; y: 30; controlX: 1; controlY: 30 }
        }
    }
    Rectangle {
        x: root.indicatorX - 29; y: 0
        width: 58; height: 58; radius: 29
        color: backend.colors.base
        border.color: "#e6ffffff"
        layer.enabled: true
        layer.effect: MultiEffect { shadowEnabled: true; shadowColor: "#55000000"; shadowVerticalOffset: 5; shadowBlur: .6 }
        Rectangle {
            anchors.fill: parent; anchors.margins: 1; radius: 28
            gradient: Gradient {
                GradientStop { position: 0; color: "#80ffffff" }
                GradientStop { position: 1; color: "#14ffffff" }
            }
        }
        Icon { anchors.centerIn: parent; width: 25; height: 25; name: ["roblox", "kitty", "settings"][root.currentIndex] }
    }
    Repeater {
        model: ["Roblox", "Kitty", "Settings"]
        Item {
            required property int index
            required property string modelData
            x: 16 + index * root.cellWidth
            width: root.cellWidth; height: root.height
            Icon {
                anchors.horizontalCenter: parent.horizontalCenter
                y: 44; width: 23; height: 23
                name: ["roblox", "kitty", "settings"][index]
                opacity: root.currentIndex === index ? 0 : hit.containsMouse ? 1 : .68
                Behavior on opacity { NumberAnimation { duration: 120 } }
            }
            Text {
                anchors.horizontalCenter: parent.horizontalCenter; y: 78
                text: modelData; color: root.currentIndex === index ? backend.colors.ink : backend.colors.muted
                font.family: "Segoe UI"; font.pixelSize: 12
                font.weight: root.currentIndex === index ? Font.DemiBold : Font.Normal
            }
            MouseArea { id: hit; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: root.selected(index) }
        }
    }
}
