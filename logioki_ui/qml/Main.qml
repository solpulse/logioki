pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs
import QtCore
import QtMultimedia
import "."

ApplicationWindow {
    id: window
    required property var vm
    readonly property bool darkMode: Design.dark
    readonly property bool highContrastMode: Design.highContrast
    readonly property bool reducedMotionMode: Design.reducedMotion
    readonly property int effectiveTransitionDuration: Design.transition
    readonly property string effectivePlatformProfile: PlatformProfile.name
    objectName: "mainWindow"
    visible: true
    title: vm.hasCamera ? "Logioki — " + vm.cameraName : "Logioki"
    minimumWidth: 720
    minimumHeight: 560
    width: settings.windowWidth
    height: settings.windowHeight
    color: Design.canvas
    palette.window: Design.canvas
    palette.windowText: Design.text
    palette.base: Design.surface
    palette.alternateBase: Design.surfaceRaised
    palette.text: Design.text
    palette.button: Design.control
    palette.buttonText: Design.text
    palette.highlight: Design.accent
    palette.highlightedText: Design.selectedText
    onVisibilityChanged: vm.previewController.setVisible(window.visibility !== Window.Minimized && window.visibility !== Window.Hidden)
    Component.onCompleted: { PlatformProfile.name = vm.platformProfile; Design.highContrast = vm.highContrast; Design.reducedMotion = vm.reducedMotion; Design.colorSchemeOverride = vm.colorSchemeOverride }
    onClosing: function(close) { settings.windowWidth = width; settings.windowHeight = height; vm.shutdown() }

    Settings { id: settings; property int windowWidth: 1180; property int windowHeight: 760; property real paneRatio: .61 }

    Connections {
        target: window.vm
        function onNotification(title, detail) { toastTitle.text = title; toastDetail.text = detail; toast.open() }
    }

    Popup {
        id: toast
        x: Math.max(Design.space, (parent.width - width) / 2)
        y: parent.height - height - Design.spaceRoomy
        width: Math.min(440, window.width - Design.spaceRoomy * 2)
        padding: Design.space
        modal: false
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        background: Rectangle { color: Design.surfaceRaised; radius: Design.radius; border.color: Design.border; border.width: 1 }
        onOpened: toastTimer.restart()
        Timer { id: toastTimer; interval: 4200; onTriggered: toast.close() }
        ColumnLayout {
            width: parent.width
            Label { id: toastTitle; font.weight: Font.DemiBold; color: Design.text }
            Label { id: toastDetail; Layout.fillWidth: true; wrapMode: Text.Wrap; color: Design.text }
        }
    }

    Dialog {
        id: newPresetDialog
        title: "Create preset"
        modal: true
        anchors.centerIn: parent
        standardButtons: Dialog.Save | Dialog.Cancel
        onAccepted: { window.vm.createPreset(presetName.text); presetName.clear() }
        TextField { id: presetName; width: 320; placeholderText: "Preset name"; Accessible.name: "Preset name" }
    }

    FileDialog { id: exportDialog; title: "Export diagnostics"; fileMode: FileDialog.SaveFile; nameFilters: ["JSON files (*.json)"]; defaultSuffix: "json"; onAccepted: window.vm.exportDiagnostics(selectedFile.toString()) }

    header: ToolBar {
        implicitHeight: Design.compact ? 58 : 66
        background: Rectangle { color: Design.surface; border.color: Design.border; border.width: 1 }
        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: Design.space
            anchors.rightMargin: Design.space
            spacing: Design.space
            Label { text: "Logioki"; font.pixelSize: Design.displaySize; font.weight: Font.DemiBold; color: Design.brand }
            ComboBox {
                Layout.preferredWidth: Math.min(320, window.width * .3)
                enabled: !window.vm.busy
                model: window.vm.cameras
                textRole: "label"
                currentIndex: window.vm.selectedCamera
                onActivated: window.vm.selectCamera(currentIndex)
                Accessible.name: "Camera selector"
            }
            Label { text: window.vm.cameraName; color: Design.mutedText; elide: Text.ElideRight; Layout.fillWidth: true }
            Rectangle { implicitWidth: 8; implicitHeight: 8; radius: 4; color: window.vm.connectionState === "Connected" ? Design.success : window.vm.connectionState === "No camera" ? Design.mutedText : Design.warning }
            Label { text: window.vm.busy ? "Working…" : window.vm.connectionState; color: Design.mutedText }
            Button { text: "Reset"; icon.name: "edit-undo"; enabled: window.vm.hasCamera && !window.vm.busy; onClicked: window.vm.resetDefaults(); Accessible.description: "Apply camera-reported factory defaults" }
            ToolButton {
                text: "⋮"
                font.pixelSize: 20
                onClicked: overflow.open()
                Accessible.name: "More options"
                Menu {
                    id: overflow
                    MenuItem { text: "Export diagnostics…"; enabled: window.vm.hasCamera; onTriggered: exportDialog.open() }
                    MenuItem { text: "Keyboard help"; onTriggered: { toastTitle.text = "Keyboard help"; toastDetail.text = "Tab moves focus, arrow keys adjust controls, Ctrl+Q quits."; toast.open() } }
                    MenuSeparator {}
                    MenuItem { text: "About Logioki"; onTriggered: { toastTitle.text = "Logioki"; toastDetail.text = "A private, native UVC camera control panel. No telemetry and no video capture."; toast.open() } }
                }
            }
        }
    }

    Shortcut { sequence: StandardKey.Quit; onActivated: window.close() }

    Item {
        anchors.fill: parent
        anchors.margins: Design.space
        SplitView {
            id: wideLayout
            objectName: "wideLayout"
            anchors.fill: parent
            visible: window.width >= 940
            onResizingChanged: if (!resizing && width > 0) settings.paneRatio = previewWide.width / width
            PreviewPane { id: previewWide; SplitView.fillHeight: true; SplitView.preferredWidth: wideLayout.width * settings.paneRatio; SplitView.minimumWidth: 420 }
            Inspector { SplitView.fillHeight: true; SplitView.fillWidth: true; SplitView.minimumWidth: 370 }
        }
        ColumnLayout {
            id: stackedLayout
            objectName: "stackedLayout"
            anchors.fill: parent
            visible: !wideLayout.visible
            spacing: Design.space
            PreviewPane { Layout.fillWidth: true; Layout.preferredHeight: Math.min(parent.height * .45, width * 9 / 16 + 84) }
            Inspector { Layout.fillWidth: true; Layout.fillHeight: true }
        }
    }

    component PreviewPane: Card {
        padding: 0
        ColumnLayout {
            anchors.fill: parent
            spacing: 0
            Rectangle {
                Layout.fillWidth: true; Layout.fillHeight: true; Layout.minimumHeight: 220
                color: Design.previewBackdrop; radius: Design.radius
                VideoOutput { objectName: "previewOutput"; anchors.fill: parent; anchors.margins: 1; fillMode: VideoOutput.PreserveAspectFit; Accessible.name: "Live camera preview"; Component.onCompleted: window.vm.previewController.setVideoOutput(this) }
                Column { anchors.centerIn: parent; visible: !window.vm.hasCamera || window.vm.previewController.state !== "Connected"; spacing: 8
                    Label { anchors.horizontalCenter: parent.horizontalCenter; text: window.vm.hasCamera ? "Preview unavailable" : "Connect a camera"; color: Design.previewText; font.pixelSize: Design.sectionSize }
                    Label { anchors.horizontalCenter: parent.horizontalCenter; text: window.vm.hasCamera ? "Controls remain available." : "Logioki will detect it automatically."; color: Design.previewMutedText }
                }
            }
            RowLayout {
                Layout.fillWidth: true; Layout.margins: Design.space
                Label { text: window.vm.previewController.state; color: window.vm.previewController.state === "Connected" ? Design.success : Design.warning; font.weight: Font.Medium }
                Item { Layout.fillWidth: true }
                Label { text: window.vm.previewController.format; color: Design.mutedText; font.pixelSize: Design.supportingSize }
            }
        }
    }

    component Inspector: Card {
        padding: 0
        ColumnLayout {
            anchors.fill: parent
            spacing: 0
            TabBar {
                id: tabs
                objectName: "inspectorNavigation"
                Layout.fillWidth: true
                Repeater { model: ["Presets", "Image", "Camera", "Device", "Firmware", "Startup"]; TabButton { required property string modelData; text: modelData; implicitWidth: 82; font.pixelSize: Design.supportingSize; Accessible.name: modelData + " section" } }
            }
            StackLayout {
                id: inspectorStack
                objectName: "inspectorStack"
                currentIndex: tabs.currentIndex
                Layout.fillWidth: true; Layout.fillHeight: true
                PresetsPage {}
                ControlsPage { pageName: "image"; controlModel: window.vm.imageControls }
                ControlsPage { pageName: "camera"; controlModel: window.vm.cameraControls }
                InfoPage {}
                EmptyPage { heading: "Firmware"; detail: window.vm.firmwareText + "\n\nLogioki does not reverse-engineer or flash firmware." }
                StartupPage {}
            }
        }
    }

    component PageFrame: ScrollView { clip: true; ScrollBar.horizontal.policy: ScrollBar.AlwaysOff; contentWidth: availableWidth }
    component EmptyPage: PageFrame { id: emptyPage; property string heading; property string detail; ColumnLayout { x: Design.spaceRoomy; width: Math.max(0, emptyPage.availableWidth - Design.spaceRoomy * 2); spacing: Design.space; Label { text: emptyPage.heading; font.pixelSize: Design.sectionSize; font.weight: Font.DemiBold; color: Design.text } Label { text: emptyPage.detail; wrapMode: Text.Wrap; Layout.fillWidth: true; color: Design.mutedText } } }

    component PresetsPage: PageFrame {
        id: presetsPage
        ColumnLayout {
            x: Design.space; width: Math.max(0, presetsPage.availableWidth - Design.space * 2); spacing: Design.space
            Label { text: window.vm.activePreset; font.pixelSize: Design.sectionSize; font.weight: Font.DemiBold; color: Design.text }
            Label { text: "Streaming and Video Calls begin with the current camera settings. They are editable starting points, not universal tuning profiles."; wrapMode: Text.Wrap; Layout.fillWidth: true; color: Design.mutedText }
            Repeater { model: window.vm.presets; delegate: Item { id: presetWrapper; required property int index; required property string name; required property bool builtin; required property bool editable; Layout.fillWidth: true; Layout.preferredWidth: presetsPage.availableWidth; implicitWidth: presetsPage.availableWidth; implicitHeight: presetRow.implicitHeight; PresetRow { id: presetRow; anchors.fill: parent; enabled: !window.vm.busy; rowIndex: presetWrapper.index; name: presetWrapper.name; builtin: presetWrapper.builtin; editable: presetWrapper.editable; onApplyRequested: window.vm.applyPreset(rowIndex); onSaveRequested: window.vm.updatePreset(rowIndex); onDeleteRequested: window.vm.deletePreset(rowIndex) } } }
            Button { text: "New preset…"; enabled: !window.vm.busy; onClicked: newPresetDialog.open() }
        }
    }

    component ControlsPage: PageFrame {
        id: controlsPage
        objectName: "controlsPage-" + pageName
        required property string pageName
        required property var controlModel
        ColumnLayout {
            objectName: "controlsColumn-" + controlsPage.pageName
            x: Design.space; width: Math.max(0, controlsPage.availableWidth - Design.space * 2); spacing: 2
            Repeater {
                objectName: "controlsRepeater-" + controlsPage.pageName
                model: controlsPage.controlModel
                delegate: Item {
                    id: controlWrapper
                    required property string controlId; required property string name; required property string kind; required property string group; required property bool showGroup; required property int value; required property int minimum; required property int maximum; required property int step; required property bool available; required property string reason; required property var menuItems
                    objectName: "control-wrapper-" + controlId
                    Layout.fillWidth: true
                    Layout.preferredWidth: controlsPage.availableWidth
                    implicitWidth: controlsPage.availableWidth
                    implicitHeight: controlRow.implicitHeight
                    CameraControlRow {
                        id: controlRow
                        anchors.fill: parent
                        controlId: controlWrapper.controlId
                        name: controlWrapper.name
                        kind: controlWrapper.kind
                        group: controlWrapper.group
                        showGroup: controlWrapper.showGroup
                        value: controlWrapper.value
                        minimum: controlWrapper.minimum
                        maximum: controlWrapper.maximum
                        step: controlWrapper.step
                        available: controlWrapper.available
                        reason: controlWrapper.reason
                        menuItems: controlWrapper.menuItems
                        onEdited: function(controlId, value, final) { window.vm.setControl(controlId, value, final) }
                    }
                }
            }
        }
    }

    component InfoPage: PageFrame {
        id: infoPage
        ColumnLayout {
            x: Design.spaceRoomy
            width: Math.max(0, infoPage.availableWidth - Design.spaceRoomy * 2)
            spacing: Design.space
            Label { text: "Device & diagnostics"; font.pixelSize: Design.sectionSize; font.weight: Font.DemiBold; color: Design.text }
            Label { text: window.vm.diagnosticsText + "\n\nIdentity and USB details are redacted in exported diagnostics. Logs rotate locally, contain no frames, and are never sent automatically."; wrapMode: Text.Wrap; Layout.fillWidth: true; color: Design.mutedText }
            Button { text: "Export diagnostics…"; enabled: window.vm.hasCamera && !window.vm.busy; Accessible.name: "Export diagnostics"; onClicked: exportDialog.open() }
        }
    }
    component StartupPage: PageFrame { id: startupPage; ColumnLayout { x: Design.space; width: Math.max(0, startupPage.availableWidth - Design.space * 2); spacing: Design.space; Label { text: "Startup"; font.pixelSize: Design.sectionSize; font.weight: Font.DemiBold; color: Design.text } StartupRow { Layout.fillWidth: true; enabled: !window.vm.busy; title: "Restore settings at login"; supporting: "Runs the dependency-light headless restore service."; checked: window.vm.restoreAtLogin; switchObjectName: "restoreStartupSwitch"; onChanged: function(checked) { window.vm.setRestoreAtLogin(checked) } } StartupRow { Layout.fillWidth: true; enabled: !window.vm.busy; title: "Open Logioki at login"; supporting: "Opening the app also restores settings; duplicate restore writers are avoided."; checked: window.vm.openAtLogin; switchObjectName: "openStartupSwitch"; onChanged: function(checked) { window.vm.setOpenAtLogin(checked) } } } }
}
