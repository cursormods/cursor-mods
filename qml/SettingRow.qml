import QtQuick

Item {
    id: root
    property string title
    property string description: ""
    default property alias control: controls.data
    implicitHeight: Math.max(copy.height, controls.childrenRect.height)
    Column {
        id: copy
        width: parent.width - controls.width - 24
        spacing: 4
        Text { width: parent.width; text: root.title; color: backend.colors.ink; wrapMode: Text.WordWrap; font.family: "Segoe UI"; font.pixelSize: 14; font.weight: Font.Medium }
        Text { width: parent.width; visible: text.length > 0; text: root.description; color: backend.colors.muted; wrapMode: Text.WordWrap; font.family: "Segoe UI"; font.pixelSize: 12 }
    }
    Item { id: controls; anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter; width: childrenRect.width; height: childrenRect.height }
}
