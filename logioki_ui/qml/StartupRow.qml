import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."

Item {
    id: root
    required property string title
    required property string supporting
    required property bool checked
    property string switchObjectName: ""
    signal changed(bool checked)

    implicitHeight: Math.max(Design.rowHeight, row.implicitHeight + Design.spaceCompact * 2)
    Rectangle { anchors.fill: parent; radius: Design.radius; color: Design.surfaceContainer; border.width: 1; border.color: Design.outlineVariant }
    RowLayout {
        id: row
        anchors.fill: parent
        anchors.margins: Design.spaceCompact
        spacing: Design.space
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 2
            Label { id: titleLabel; text: root.title; font.family: Design.fontFamily; font.pixelSize: Design.rowTitleSize; font.weight: Font.DemiBold; color: Design.foreground; wrapMode: Text.Wrap }
            Label { text: root.supporting; font.family: Design.fontFamily; font.pixelSize: Design.supportingSize; color: Design.foregroundMuted; wrapMode: Text.Wrap; Layout.fillWidth: true }
        }
        Switch {
            id: startupSwitch
            objectName: root.switchObjectName
            checked: root.checked
            Accessible.name: root.title
            Accessible.labelledBy: titleLabel
            onClicked: root.changed(checked)
            indicator: Rectangle {
                implicitWidth: 42
                implicitHeight: 24
                radius: 12
                color: startupSwitch.checked ? Design.primary : Design.surfaceContainerHighest
                border.width: parent.activeFocus ? Design.focusWidth : 1
                border.color: parent.activeFocus ? Design.primary : Design.outlineVariant
                Rectangle {
                    width: 18; height: 18; radius: 9
                    y: 3
                    x: startupSwitch.checked ? parent.width - width - 3 : 3
                    color: startupSwitch.checked ? Design.primaryForeground : Design.foreground
                    Behavior on x { NumberAnimation { duration: Design.transition } }
                }
            }
        }
    }
}
