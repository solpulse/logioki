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
    RowLayout {
        id: row
        anchors.fill: parent
        anchors.margins: Design.spaceCompact
        spacing: Design.space
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 2
            Label { id: titleLabel; text: root.title; font.pixelSize: Design.rowTitleSize; font.weight: Font.Medium; color: Design.text; wrapMode: Text.Wrap }
            Label { text: root.supporting; font.pixelSize: Design.supportingSize; color: Design.mutedText; wrapMode: Text.Wrap; Layout.fillWidth: true }
        }
        Switch {
            objectName: root.switchObjectName
            checked: root.checked
            Accessible.name: root.title
            Accessible.labelledBy: titleLabel
            onClicked: root.changed(checked)
        }
    }
}
