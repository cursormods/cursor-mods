import QtQuick
import QtQuick.Controls

Slider {
    id: control
    implicitHeight: 34
    leftPadding: 10; rightPadding: 10
    background: Rectangle {
        x: control.leftPadding; y: control.topPadding + control.availableHeight / 2 - height / 2
        width: control.availableWidth; height: 5; radius: 3
        color: Qt.alpha(backend.colors.ink, .12)
        Rectangle { width: control.visualPosition * parent.width; height: parent.height; radius: 3; color: backend.colors.accent }
    }
    handle: Rectangle {
        x: control.leftPadding + control.visualPosition * (control.availableWidth - width)
        y: control.topPadding + control.availableHeight / 2 - height / 2
        width: 21; height: 21; radius: 11
        border.color: "#ccffffff"; border.width: 1
        gradient: Gradient {
            GradientStop { position: 0; color: "#fffdf7" }
            GradientStop { position: 1; color: backend.colors.accent }
        }
        scale: control.pressed ? 1.12 : 1
        Behavior on scale { NumberAnimation { duration: 100 } }
    }
}
