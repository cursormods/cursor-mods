import QtQuick
import QtQuick.Controls
import QtQuick.Effects

Button {
    id: control
    property bool primary: false
    property bool compact: false
    property string iconName: ""
    implicitHeight: compact ? 34 : 43
    implicitWidth: Math.max(compact ? 36 : 70, label.implicitWidth + (iconName ? 32 : 0) + 32)
    hoverEnabled: true
    padding: 12
    opacity: enabled ? 1 : 0.42
    scale: down ? 0.98 : 1
    Behavior on scale { NumberAnimation { duration: 100 } }
    contentItem: Row {
        spacing: 8
        Icon { visible: !!control.iconName; name: control.iconName; width: visible ? 18 : 0; height: 18; anchors.verticalCenter: parent.verticalCenter }
        Text {
            id: label
            text: control.text
            color: backend.colors.ink
            font.family: "Segoe UI"
            font.pixelSize: control.compact ? 12 : 13
            font.weight: control.primary ? Font.DemiBold : Font.Medium
            anchors.verticalCenter: parent.verticalCenter
        }
    }
    background: Item {
        Rectangle {
            x: 2; y: control.down ? 2 : 6
            width: parent.width; height: parent.height - 1
            radius: 13
            color: control.enabled ? "#38000000" : "transparent"
            layer.enabled: true
            layer.effect: MultiEffect { blurEnabled: true; blurMax: 24; blur: 0.55 }
        }
        Rectangle {
            anchors.fill: parent
            radius: 13
            color: Qt.alpha(backend.colors.base, control.down ? 0.72 : 0.35)
            border.color: Qt.rgba(1,1,1, control.hovered ? 0.85 : control.primary ? 0.65 : 0.35)
            border.width: 1
            Rectangle {
                anchors.fill: parent; anchors.margins: 1; radius: 12
                gradient: Gradient {
                    GradientStop { position: 0; color: Qt.rgba(1,1,1, control.hovered ? .38 : control.primary ? .28 : .14) }
                    GradientStop { position: .6; color: "#08ffffff" }
                    GradientStop { position: 1; color: Qt.rgba(1,1,1, control.primary ? .2 : .08) }
                }
            }
        }
        Rectangle {
            visible: control.primary || control.hovered
            anchors.horizontalCenter: parent.horizontalCenter
            y: parent.height - 2
            width: parent.width * .55; height: 2; radius: 1
            color: Qt.alpha(backend.colors.accent, .9)
            layer.enabled: true
            layer.effect: MultiEffect { blurEnabled: true; blurMax: 12; blur: .4 }
        }
    }
}
