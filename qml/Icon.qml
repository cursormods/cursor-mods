import QtQuick
import QtQuick.Shapes

Item {
    id: root
    property string name: "cursor"
    property color color: backend.colors.ink
    property real lineWidth: 1.7
    readonly property var paths: ({
        cursor: "M5 3 L19 13 L12 14 L9 21 Z M12 14 L17 20",
        roblox: "M6 2 L22 6 L18 22 L2 18 Z M10 9 L15 10 L14 15 L9 14 Z",
        kitty: "M4 11 L4 3 L10 7 Q12 6 14 7 L20 3 L20 11 Q23 21 12 21 Q1 21 4 11 Z M8 12 L8 14 M16 12 L16 14 M10 17 Q12 19 14 17",
        settings: "M9 3 L15 3 L16 6 L19 7 L22 11 L20 14 L20 17 L16 20 L13 19 L10 21 L5 18 L5 15 L2 12 L4 7 L7 6 Z M16 12 A4 4 0 1 0 8 12 A4 4 0 1 0 16 12",
        upload: "M12 16 L12 3 M7 8 L12 3 L17 8 M4 15 L4 21 L20 21 L20 15",
        folder: "M3 6 L9 6 L11 9 L21 9 L21 20 L3 20 Z M3 6 L3 4 L10 4 L12 6 L19 6 L19 9",
        restore: "M4 10 A8 8 0 1 1 5 18 M4 4 L4 10 L10 10",
        close: "M6 6 L18 18 M18 6 L6 18",
        minimize: "M5 12 L19 12",
        maximize: "M5 5 L19 5 L19 19 L5 19 Z",
        check: "M4 12 L10 18 L20 6",
        plus: "M12 5 L12 19 M5 12 L19 12",
        pause: "M8 5 L8 19 M16 5 L16 19"
    })
    Shape {
        width: 24; height: 24
        scale: Math.min(root.width, root.height) / 24
        transformOrigin: Item.TopLeft
        antialiasing: true
        preferredRendererType: Shape.CurveRenderer
        ShapePath {
            strokeColor: root.color
            strokeWidth: root.lineWidth
            fillColor: "transparent"
            capStyle: ShapePath.RoundCap
            joinStyle: ShapePath.RoundJoin
            PathSvg { path: root.paths[root.name] || root.paths.cursor }
        }
    }
}
