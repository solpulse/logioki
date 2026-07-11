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
    Rectangle {
        anchors.fill: parent
        radius: Design.radius
        color: Design.surfaceContainer
        border.width: 1
        border.color: Design.outlineVariant
    }

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
            color: Design.primary
            Layout.topMargin: root.showGroup ? Design.spaceCompact : 0
        }

        Item {
            id: titleRow
            Layout.fillWidth: true
            implicitHeight: Math.max(titleColumn.implicitHeight, root.kind === "toggle" ? 32 : 0)

            ColumnLayout {
                id: titleColumn
                anchors.left: parent.left
                anchors.top: parent.top
                anchors.right: toggleLoader.visible ? toggleLoader.left : parent.right
                anchors.rightMargin: toggleLoader.visible ? Design.controlInnerGap : 0
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                spacing: 2
                Label { id: titleLabel; text: root.name; font.family: Design.fontFamily; font.pixelSize: Design.rowTitleSize; font.weight: Font.DemiBold; color: Design.foreground; wrapMode: Text.Wrap }
                Label { visible: !root.available; text: root.reason; font.family: Design.fontFamily; font.pixelSize: Design.supportingSize; color: Design.foregroundMuted; wrapMode: Text.Wrap; Layout.fillWidth: true }
            }

            Loader {
                id: toggleLoader
                visible: root.kind === "toggle" && root.available
                width: 42
                height: 24
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                sourceComponent: toggleEditor
            }
        }

        Loader {
            visible: root.kind !== "toggle" && root.available
            Layout.fillWidth: true
            Layout.preferredHeight: visible ? 36 : 0
            sourceComponent: root.kind === "menu" ? menuEditor : numberEditor
        }
    }

    Component {
        id: toggleEditor
        AbstractButton {
            id: toggle
            objectName: "control-" + root.controlId
            width: 42
            height: 24
            padding: 0
            checkable: true
            checked: root.value !== 0
            enabled: root.available
            Accessible.name: root.name
            Accessible.labelledBy: titleLabel
            onClicked: root.edited(root.controlId, checked ? 1 : 0, true)
            contentItem: Item {}
            background: Rectangle {
                anchors.fill: parent
                radius: 12
                color: toggle.checked ? Design.primary : Design.surfaceContainerHighest
                border.width: toggle.activeFocus ? Design.focusWidth : 1
                border.color: toggle.activeFocus ? Design.primary : Design.outlineVariant
                Rectangle {
                    width: 18; height: 18; radius: 9; y: 3
                    x: toggle.checked ? parent.width - width - 3 : 3
                    color: toggle.checked ? Design.primaryForeground : Design.foreground
                    Behavior on x { NumberAnimation { duration: Design.transition } }
                }
            }
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
            font.family: Design.fontFamily
            font.pixelSize: Design.bodySize
            background: Rectangle { radius: Design.radius; color: Design.surfaceContainerLowest; border.width: parent.activeFocus ? Design.focusWidth : 1; border.color: parent.activeFocus ? Design.primary : Design.outlineVariant }
        }
    }

    Component {
        id: numberEditor
        RowLayout {
            width: parent.width
            Slider {
                id: slider
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
                background: Rectangle {
                    x: slider.leftPadding
                    y: slider.topPadding + slider.availableHeight / 2 - height / 2
                    width: slider.availableWidth
                    height: 4
                    radius: 2
                    color: Design.surfaceContainerHighest
                    Rectangle { width: slider.visualPosition * parent.width; height: parent.height; radius: parent.radius; color: Design.primary }
                }
                handle: Rectangle {
                    x: slider.leftPadding + slider.visualPosition * (slider.availableWidth - width)
                    y: slider.topPadding + slider.availableHeight / 2 - height / 2
                    implicitWidth: 14; implicitHeight: 14; radius: 7
                    color: Design.foreground
                    border.width: parent.activeFocus ? Design.focusWidth : 1
                    border.color: parent.activeFocus ? Design.primary : Design.outline
                }
            }
            SpinBox {
                objectName: "control-exact-" + root.controlId
                from: root.minimum
                to: root.maximum
                stepSize: root.step
                value: root.value
                enabled: root.available
                editable: true
                Layout.preferredWidth: 76
                Accessible.name: root.name + " exact value"
                Accessible.labelledBy: titleLabel
                onValueModified: root.edited(root.controlId, value, true)
                font.family: Design.monoFamily
                font.pixelSize: Design.monoSize
                background: Rectangle { radius: Design.radius; color: Design.surfaceContainerLowest; border.width: parent.activeFocus ? Design.focusWidth : 1; border.color: parent.activeFocus ? Design.primary : Design.outlineVariant }
            }
        }
    }
}
