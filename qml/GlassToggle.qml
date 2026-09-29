import QtQuick
import QtQuick.Controls

Switch {
    id: control
    implicitWidth: 52; implicitHeight: 30
    padding: 0
    indicator: Rectangle {
        width: 52; height: 30; radius: 15
        color: control.checked ? Qt.alpha(backend.colors.accent, .55) : Qt.alpha(backend.colors.ink, .09)
        border.color: Qt.rgba(1,1,1,.65)
        Rectangle {
            x: control.checked ? 25 : 3; y: 3
            width: 24; height: 24; radius: 12
            gradient: Gradient {
                GradientStop { position: 0; color: "#fffefb" }
                GradientStop { position: 1; color: "#cac6c1" }
            }
            border.color: "#eeffffff"
            Behavior on x { NumberAnimation { duration: 180; easing.type: Easing.OutCubic } }
        }
    }
}
