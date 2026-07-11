import QtQuick
import QtQuick.Controls
import "."

TabButton {
    id: control
    implicitHeight: 44
    implicitWidth: Math.max(84, contentItem.implicitWidth + 28)
    font.family: Design.fontFamily
    font.pixelSize: Design.labelMediumSize
    font.weight: Font.DemiBold

    contentItem: Label {
        text: control.text.toUpperCase()
        font: control.font
        color: control.checked ? Design.primary : Design.foregroundMuted
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
    }
    background: Rectangle {
        color: control.hovered ? "#0dffffff" : "transparent"
        Rectangle {
            width: parent.width
            height: 3
            anchors.bottom: parent.bottom
            color: control.checked ? Design.primary : "transparent"
        }
    }
}
