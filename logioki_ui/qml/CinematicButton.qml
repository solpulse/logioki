import QtQuick
import QtQuick.Controls
import "."

Button {
    id: control
    property bool primary: false
    property bool destructive: false

    implicitHeight: 36
    leftPadding: 14
    rightPadding: 14
    topPadding: 8
    bottomPadding: 8
    font.family: Design.fontFamily
    font.pixelSize: Design.bodySize
    font.weight: Font.Medium

    contentItem: Label {
        text: control.text
        font: control.font
        color: !control.enabled ? Design.foregroundMuted
            : control.destructive ? Design.error
            : control.primary ? Design.primaryForeground : Design.foreground
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }

    background: Rectangle {
        radius: Design.radius
        color: !control.enabled ? Design.surfaceContainer
            : control.down ? (control.primary ? Design.primaryContainer : Design.surfaceBright)
            : control.hovered ? (control.primary ? Qt.lighter(Design.primary, 1.08) : Design.surfaceContainerHighest)
            : control.primary ? Design.primary : Design.surfaceContainerHigh
        border.width: control.activeFocus ? Design.focusWidth : 1
        border.color: control.activeFocus ? Design.primary
            : control.destructive ? Design.error : Design.outlineVariant
        opacity: control.enabled ? 1 : .55

        Rectangle {
            x: 1
            y: 1
            width: parent.width - 2
            height: 1
            color: control.primary ? "#55ffffff" : "#22ffffff"
            radius: parent.radius
        }
    }
}
