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

    implicitHeight: content.implicitHeight + Design.stackGap * 2

    Rectangle {
        anchors.fill: parent
        radius: Design.radius
        color: root.enabled ? Design.surfaceContainer : Design.surfaceContainerLow
        border.width: 1
        border.color: Design.outlineVariant
    }

    ColumnLayout {
        id: content
        anchors.fill: parent
        anchors.margins: Design.stackGap
        spacing: Design.controlInnerGap
        RowLayout {
            Layout.fillWidth: true
            spacing: Design.controlInnerGap
            Rectangle {
                implicitWidth: 4
                implicitHeight: 24
                radius: 2
                color: root.editable ? Design.primary : Design.outline
            }
            Label {
                text: root.name
                font.family: Design.fontFamily
                font.pixelSize: Design.rowTitleSize
                font.weight: Font.DemiBold
                color: Design.foreground
                Layout.fillWidth: true
            }
            Label {
                text: root.builtin ? "BUILT IN" : "CUSTOM"
                font.family: Design.fontFamily
                font.pixelSize: Design.labelSmallSize
                font.weight: Font.DemiBold
                color: Design.primary
            }
        }
        Label {
            text: root.builtin ? (root.name === "Default" ? "Camera-reported defaults · Read-only" : "Editable starting point") : "Saved camera configuration"
            font.family: Design.fontFamily
            font.pixelSize: Design.supportingSize
            color: Design.foregroundMuted
            wrapMode: Text.Wrap
            Layout.fillWidth: true
        }
        RowLayout {
            Layout.fillWidth: true
            spacing: Design.spaceCompact
            Item { Layout.fillWidth: true }
            CinematicButton { text: "Apply"; primary: true; Accessible.name: "Apply " + root.name; onClicked: root.applyRequested() }
            CinematicButton { text: "Save"; visible: root.editable; Accessible.name: "Save current values to " + root.name; onClicked: root.saveRequested() }
            CinematicButton { text: "Delete"; destructive: true; visible: !root.builtin; Accessible.name: "Delete " + root.name; onClicked: root.deleteRequested() }
        }
    }
}
