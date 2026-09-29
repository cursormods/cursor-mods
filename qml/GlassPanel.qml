import QtQuick
import QtQuick.Effects

Item {
    id: root
    default property alias content: body.data
    property real padding: 24
    property real cornerRadius: 22
    implicitHeight: body.childrenRect.height + padding * 2
    Rectangle {
        anchors.fill: plate
        anchors.topMargin: 7
        anchors.bottomMargin: -7
        radius: root.cornerRadius
        color: "#30000000"
        layer.enabled: true
        layer.effect: MultiEffect { blurEnabled: true; blurMax: 32; blur: 0.65 }
    }
    Rectangle {
        id: plate
        anchors.fill: parent
        radius: root.cornerRadius
        color: Qt.alpha(backend.colors.base, 0.62 + 0.24 * backend.settings.glass_opacity)
        border.width: 1
        border.color: Qt.rgba(1, 1, 1, backend.colors.light ? 0.64 : 0.30)
        Rectangle {
            anchors.fill: parent
            anchors.margins: 1
            radius: parent.radius - 1
            gradient: Gradient {
                GradientStop { position: 0; color: Qt.rgba(1,1,1, backend.colors.light ? 0.36 : 0.12) }
                GradientStop { position: 0.55; color: "#02ffffff" }
                GradientStop { position: 1; color: "#12ffffff" }
            }
        }
    }
    Item { id: body; x: root.padding; y: root.padding; width: root.width - root.padding * 2; height: childrenRect.height }
}
