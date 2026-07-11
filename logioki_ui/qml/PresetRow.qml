import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."

Item {
    id: root
    required property int rowIndex
    required property string name
    required property bool builtin
    required property bool editable
    signal applyRequested()
    signal saveRequested()
    signal deleteRequested()

    implicitHeight: Math.max(Design.rowHeight, row.implicitHeight + Design.spaceCompact * 2)

    RowLayout {
        id: row
        anchors.fill: parent
        anchors.margins: Design.spaceCompact
        spacing: Design.space
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 2
            Label { text: root.name; font.pixelSize: Design.rowTitleSize; font.weight: Font.Medium; color: Design.text }
            Label { text: root.builtin ? (root.name === "Default" ? "Camera-reported defaults · Read-only" : "Editable starter preset") : "Custom preset"; font.pixelSize: Design.supportingSize; color: Design.mutedText; wrapMode: Text.Wrap; Layout.fillWidth: true }
        }
        Row {
            spacing: Design.spaceCompact
            Button { text: "Apply"; Accessible.name: "Apply " + root.name; onClicked: root.applyRequested() }
            Button { text: "Save current"; visible: root.editable; Accessible.name: "Save current values to " + root.name; onClicked: root.saveRequested() }
            Button { text: "Delete"; visible: !root.builtin; Accessible.name: "Delete " + root.name; onClicked: root.deleteRequested() }
        }
    }
}
