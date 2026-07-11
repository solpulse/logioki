pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."

Item {
    id: root
    objectName: "camera-control-row-" + controlId
    required property string controlId
    required property string name
    required property string kind
    required property string group
    required property bool showGroup
    required property int value
    required property int minimum
    required property int maximum
    required property int step
    required property bool available
    required property string reason
    required property var menuItems
    signal edited(string controlId, int value, bool final)

    implicitHeight: content.implicitHeight + Design.spaceCompact * 2
    opacity: available ? 1 : .58
    Behavior on opacity { NumberAnimation { duration: Design.transition } }

    ColumnLayout {
        id: content
        anchors.fill: parent
        anchors.margins: Design.spaceCompact
        spacing: Design.spaceCompact

        Label {
            text: root.group
            visible: root.showGroup
            font.pixelSize: Design.sectionSize
            font.weight: Font.DemiBold
            color: Design.text
            Layout.topMargin: root.showGroup ? Design.spaceCompact : 0
        }

        RowLayout {
            id: row
            Layout.fillWidth: true
            Layout.minimumHeight: Design.rowHeight
            spacing: Design.space

            ColumnLayout {
                Layout.fillWidth: true
                Layout.minimumWidth: 100
                spacing: 2
                Label { id: titleLabel; text: root.name; font.pixelSize: Design.rowTitleSize; font.weight: Font.Medium; color: Design.text; wrapMode: Text.Wrap }
                Label { visible: !root.available; text: root.reason; font.pixelSize: Design.supportingSize; color: Design.mutedText; wrapMode: Text.Wrap; Layout.fillWidth: true }
            }

            Loader {
                Layout.preferredWidth: Math.min(300, root.width * .55)
                Layout.minimumWidth: Math.min(180, root.width * .42)
                Layout.alignment: Qt.AlignVCenter
                sourceComponent: root.kind === "toggle" ? toggleEditor : root.kind === "menu" ? menuEditor : numberEditor
            }
        }
    }

    Component {
        id: toggleEditor
        Switch {
            objectName: "control-" + root.controlId
            anchors.right: parent.right
            checked: root.value !== 0
            enabled: root.available
            Accessible.name: root.name
            Accessible.labelledBy: titleLabel
            onClicked: root.edited(root.controlId, checked ? 1 : 0, true)
        }
    }

    Component {
        id: menuEditor
        ComboBox {
            objectName: "control-" + root.controlId
            width: parent.width
            model: root.menuItems
            textRole: "label"
            readonly property int hardwareValue: currentIndex >= 0 ? Number(root.menuItems[currentIndex]["value"]) : root.value
            function indexForHardwareValue(value) {
                for (let index = 0; index < root.menuItems.length; ++index) {
                    if (Number(root.menuItems[index]["value"]) === Number(value))
                        return index
                }
                return -1
            }
            enabled: root.available
            Accessible.name: root.name
            Accessible.labelledBy: titleLabel
            currentIndex: indexForHardwareValue(root.value)
            onActivated: root.edited(root.controlId, hardwareValue, true)
        }
    }

    Component {
        id: numberEditor
        RowLayout {
            width: parent.width
            Slider {
                objectName: "control-" + root.controlId
                Layout.fillWidth: true
                from: root.minimum
                to: root.maximum
                stepSize: root.step
                value: root.value
                enabled: root.available
                Accessible.name: root.name
                Accessible.labelledBy: titleLabel
                onMoved: root.edited(root.controlId, Math.round(value), false)
                onPressedChanged: if (!pressed) root.edited(root.controlId, Math.round(value), true)
            }
            SpinBox {
                objectName: "control-exact-" + root.controlId
                from: root.minimum
                to: root.maximum
                stepSize: root.step
                value: root.value
                enabled: root.available
                editable: true
                Accessible.name: root.name + " exact value"
                Accessible.labelledBy: titleLabel
                onValueModified: root.edited(root.controlId, value, true)
            }
        }
    }
}
