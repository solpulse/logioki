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
    readonly property bool darkMode: true
    readonly property bool highContrastMode: Design.highContrast
    readonly property bool reducedMotionMode: Design.reducedMotion
    readonly property int effectiveTransitionDuration: Design.transition
    readonly property string effectivePlatformProfile: PlatformProfile.name
    property int inspectorSection: 0
    objectName: "mainWindow"
    visible: true
    title: vm.hasCamera ? "Logioki — " + vm.cameraName : "Logioki"
    minimumWidth: 720
    minimumHeight: 600
    width: settings.windowWidth
    height: settings.windowHeight
    color: Design.background
    font.family: Design.fontFamily
    font.pixelSize: Design.bodySize
    palette.window: Design.background
    palette.windowText: Design.foreground
    palette.base: Design.surfaceContainerLowest
    palette.alternateBase: Design.surfaceContainer
    palette.text: Design.foreground
    palette.button: Design.surfaceContainerHigh
    palette.buttonText: Design.foreground
    palette.highlight: Design.primary
    palette.highlightedText: Design.primaryForeground
    onVisibilityChanged: vm.previewController.setVisible(window.visibility !== Window.Minimized && window.visibility !== Window.Hidden)
    Component.onCompleted: {
        PlatformProfile.name = vm.platformProfile
        Design.highContrast = vm.highContrast
        Design.reducedMotion = vm.reducedMotion
        Design.colorSchemeOverride = 1
    }
    onClosing: function(close) {
        settings.windowWidth = width
        settings.windowHeight = height
        vm.shutdown()
    }

    Settings {
        id: settings
        property int windowWidth: 1280
        property int windowHeight: 800
    }

    Connections {
        target: window.vm
        function onNotification(title, detail) {
            toastTitle.text = title
            toastDetail.text = detail
            toast.open()
        }
    }

    Popup {
        id: toast
        x: Math.max(Design.space, (parent.width - width) / 2)
        y: parent.height - height - Design.space
        width: Math.min(480, window.width - Design.spaceRoomy * 2)
        padding: Design.space
        modal: false
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        background: Rectangle {
            color: Design.glass
            radius: Design.radiusOverlay
            border.color: Design.outlineVariant
            border.width: 1
        }
        onOpened: toastTimer.restart()
        Timer { id: toastTimer; interval: 4200; onTriggered: toast.close() }
        ColumnLayout {
            width: parent.width
            spacing: Design.controlInnerGap
            Label { id: toastTitle; font.pixelSize: Design.headlineMediumSize; font.weight: Font.DemiBold; color: Design.foreground }
            Label { id: toastDetail; Layout.fillWidth: true; wrapMode: Text.Wrap; color: Design.foregroundMuted }
        }
    }

    Dialog {
        id: newPresetDialog
        title: "Create preset"
        modal: true
        anchors.centerIn: parent
        standardButtons: Dialog.Save | Dialog.Cancel
        onAccepted: {
            window.vm.createPreset(presetName.text)
            presetName.clear()
        }
        TextField {
            id: presetName
            width: 320
            placeholderText: "Preset name"
            Accessible.name: "Preset name"
        }
    }

    FileDialog {
        id: exportDialog
        title: "Export diagnostics"
        fileMode: FileDialog.SaveFile
        nameFilters: ["JSON files (*.json)"]
        defaultSuffix: "json"
        onAccepted: window.vm.exportDiagnostics(selectedFile.toString())
    }

    header: ToolBar {
        implicitHeight: 64
        padding: 0
        background: Rectangle {
            color: Design.surfaceContainerLow
            border.color: Design.outlineVariant
            border.width: 1
        }
        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: Design.containerPadding
            anchors.rightMargin: Design.containerPadding
            spacing: Design.stackGap

            RowLayout {
                spacing: Design.controlInnerGap
                Rectangle {
                    implicitWidth: 28; implicitHeight: 28; radius: Design.radius
                    color: Design.primary
                    Label {
                        anchors.centerIn: parent
                        text: "L"
                        color: Design.primaryForeground
                        font.pixelSize: Design.bodyLargeSize
                        font.weight: Font.Bold
                    }
                }
                Label {
                    text: "LOGIOKI"
                    font.pixelSize: Design.bodyLargeSize
                    font.weight: Font.DemiBold
                    font.letterSpacing: 1.2
                    color: Design.foreground
                }
            }

            Rectangle { implicitWidth: 1; Layout.fillHeight: true; Layout.topMargin: 16; Layout.bottomMargin: 16; color: Design.outlineVariant }

            ComboBox {
                Layout.preferredWidth: Math.min(260, window.width * .26)
                enabled: !window.vm.busy
                model: window.vm.cameras
                textRole: "label"
                currentIndex: window.vm.selectedCamera
                onActivated: window.vm.selectCamera(currentIndex)
                Accessible.name: "Camera selector"
                background: Rectangle {
                    radius: Design.radius
                    color: Design.surfaceContainerLowest
                    border.width: parent.activeFocus ? Design.focusWidth : 1
                    border.color: parent.activeFocus ? Design.primary : Design.outlineVariant
                }
            }

            ComboBox {
                visible: window.width >= 900
                Layout.preferredWidth: 220
                enabled: window.vm.hasCamera && !window.vm.busy
                model: window.vm.presets
                textRole: "name"
                displayText: "Scene · " + window.vm.activePreset
                onActivated: window.vm.applyPreset(currentIndex)
                Accessible.name: "Scene selector"
                background: Rectangle {
                    radius: Design.radius
                    color: Design.surfaceContainerLowest
                    border.width: parent.activeFocus ? Design.focusWidth : 1
                    border.color: parent.activeFocus ? Design.primary : Design.outlineVariant
                }
            }
            Item { Layout.fillWidth: true }

            Rectangle {
                implicitWidth: connectionRow.implicitWidth + 20
                implicitHeight: 32
                radius: Design.radiusFull
                color: Design.surfaceContainer
                border.width: 1
                border.color: Design.outlineVariant
                RowLayout {
                    id: connectionRow
                    anchors.centerIn: parent
                    spacing: 8
                    Rectangle {
                        implicitWidth: 8; implicitHeight: 8; radius: 4
                        color: window.vm.connectionState === "Connected" ? Design.success
                            : window.vm.connectionState === "No camera" ? Design.outline : Design.warning
                    }
                    Label {
                        text: window.vm.busy ? "Working…" : window.vm.connectionState
                        color: Design.foregroundMuted
                        font.pixelSize: Design.labelMediumSize
                        font.weight: Font.DemiBold
                    }
                }
            }
            CinematicButton {
                text: "Reset"
                enabled: window.vm.hasCamera && !window.vm.busy
                onClicked: window.vm.resetDefaults()
                Accessible.description: "Apply camera-reported factory defaults"
            }
            ToolButton {
                text: "⋮"
                font.pixelSize: 22
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

    Shortcut { sequences: [StandardKey.Quit]; onActivated: window.close() }

    Item {
        anchors.fill: parent
        anchors.margins: Design.stackGap

        RowLayout {
            id: wideLayout
            objectName: "wideLayout"
            anchors.fill: parent
            visible: window.width >= 1024
            spacing: Design.stackGap

            Item {
                id: widePreviewSlot
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.minimumWidth: 360
            }
            Loader {
                active: wideLayout.visible
                sourceComponent: detailedInspectorComponent
                Layout.preferredWidth: 420
                Layout.minimumWidth: 380
                Layout.fillHeight: true
            }
        }

        ColumnLayout {
            id: stackedLayout
            objectName: "stackedLayout"
            anchors.fill: parent
            visible: !wideLayout.visible
            spacing: Design.stackGap
            Item {
                id: stackedPreviewSlot
                Layout.fillWidth: true
                Layout.preferredHeight: Math.min(parent.height * .52, width * 9 / 16)
                Layout.minimumHeight: 240
            }
            Loader {
                active: stackedLayout.visible
                sourceComponent: responsiveInspectorComponent
                Layout.fillWidth: true
                Layout.fillHeight: true
            }
        }

        PreviewPane {
            id: previewPane
            parent: wideLayout.visible ? widePreviewSlot : stackedPreviewSlot
            anchors.fill: parent
        }
    }

    component PreviewPane: Card {
        padding: 0
        background: Rectangle {
            color: Design.surfaceContainerLowest
            radius: Design.radiusContainer
            border.width: 1
            border.color: Design.outlineVariant
        }
        Rectangle {
            anchors.fill: parent
            anchors.margins: 1
            color: Design.previewBackdrop
            radius: Design.radiusContainer
            clip: true

            VideoOutput {
                objectName: "previewOutput"
                anchors.fill: parent
                fillMode: VideoOutput.PreserveAspectFit
                Accessible.name: "Live camera preview"
                Component.onCompleted: window.vm.previewController.setVideoOutput(this)
            }

            Column {
                anchors.centerIn: parent
                visible: !window.vm.hasCamera || window.vm.previewController.state !== "Connected"
                spacing: Design.controlInnerGap
                Label {
                    anchors.horizontalCenter: parent.horizontalCenter
                    text: window.vm.hasCamera ? "Preview unavailable" : "Connect a camera"
                    color: Design.previewText
                    font.pixelSize: Design.headlineMediumSize
                    font.weight: Font.DemiBold
                }
                Label {
                    anchors.horizontalCenter: parent.horizontalCenter
                    text: window.vm.hasCamera ? "Controls remain available" : "Logioki will detect it automatically"
                    color: Design.previewMutedText
                }
            }

            Rectangle {
                anchors.left: parent.left
                anchors.top: parent.top
                anchors.margins: Design.stackGap
                width: feedLabel.implicitWidth + 24
                height: 32
                radius: Design.radius
                color: Design.glass
                border.width: 1
                border.color: Design.outlineVariant
                Label {
                    id: feedLabel
                    anchors.centerIn: parent
                    text: "●  LIVE FEED"
                    color: window.vm.previewController.state === "Connected" ? Design.success : Design.foregroundMuted
                    font.pixelSize: Design.labelMediumSize
                    font.weight: Font.DemiBold
                    font.letterSpacing: .8
                }
            }

            ColumnLayout {
                anchors.right: parent.right
                anchors.top: parent.top
                anchors.margins: Design.stackGap
                spacing: 4
                Label {
                    text: "PREVIEW MODE"
                    color: Design.foregroundMuted
                    font.pixelSize: Design.labelSmallSize
                    font.weight: Font.DemiBold
                    font.letterSpacing: .8
                    Layout.alignment: Qt.AlignRight
                }
                ComboBox {
                    id: previewFormatSelector
                    objectName: "previewFormatSelector"
                    Layout.preferredWidth: 230
                    model: window.vm.previewController.formatOptions
                    currentIndex: window.vm.previewController.currentFormatIndex
                    enabled: count > 0 && !window.vm.busy
                    onActivated: window.vm.previewController.selectFormat(currentIndex)
                    Accessible.name: "Preview resolution and frame rate"
                    font.family: Design.monoFamily
                    font.pixelSize: Design.monoSize
                    background: Rectangle {
                        radius: Design.radius
                        color: Design.glass
                        border.width: parent.activeFocus ? Design.focusWidth : 1
                        border.color: parent.activeFocus ? Design.primary : Design.outlineVariant
                    }
                }
            }

            Rectangle {
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.bottom: parent.bottom
                anchors.margins: Design.stackGap
                height: 44
                radius: Design.radius
                color: Design.glass
                border.width: 1
                border.color: Design.outlineVariant
                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 14
                    anchors.rightMargin: 14
                    spacing: Design.controlInnerGap
                    Rectangle {
                        implicitWidth: 8; implicitHeight: 8; radius: 4
                        color: window.vm.previewController.state === "Connected" ? Design.success : Design.warning
                    }
                    Label {
                        text: window.vm.previewController.state
                        color: Design.foreground
                        font.weight: Font.DemiBold
                    }
                    Item { Layout.fillWidth: true }
                    Label {
                        text: window.vm.previewController.format
                        color: Design.foregroundMuted
                        font.family: Design.monoFamily
                        font.pixelSize: Design.monoSize
                    }
                }
            }
        }
    }

    Component {
        id: detailedInspectorComponent
        Inspector { includePresets: true }
    }
    Component {
        id: responsiveInspectorComponent
        Inspector { includePresets: true }
    }

    component Inspector: Card {
        id: inspector
        required property bool includePresets
        padding: 0
        readonly property var tabNames: includePresets
            ? ["Presets", "Image", "Camera", "Device", "Firmware", "Startup"]
            : ["Image", "Camera", "Device", "Firmware", "Startup"]
        ColumnLayout {
            anchors.fill: parent
            spacing: 0
            TabBar {
                id: tabs
                objectName: "inspectorNavigation"
                Layout.fillWidth: true
                currentIndex: window.inspectorSection
                onCurrentIndexChanged: window.inspectorSection = currentIndex
                background: Rectangle {
                    color: "transparent"
                    Rectangle { anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom; height: 1; color: Design.outlineVariant }
                }
                Repeater {
                    model: inspector.tabNames
                    CinematicTabButton {
                        required property string modelData
                        text: modelData
                        implicitWidth: 0
                        width: inspector.width / inspector.tabNames.length
                        Accessible.name: modelData + " section"
                    }
                }
            }
            StackLayout {
                id: inspectorStack
                objectName: "inspectorStack"
                currentIndex: tabs.currentIndex + (inspector.includePresets ? 0 : 1)
                Layout.fillWidth: true
                Layout.fillHeight: true
                PresetsPage {}
                ControlsPage { pageName: "image"; controlModel: window.vm.imageControls }
                ControlsPage { pageName: "camera"; controlModel: window.vm.cameraControls }
                InfoPage {}
                EmptyPage {
                    heading: "Firmware"
                    eyebrow: "DEVICE SERVICE"
                    detail: window.vm.firmwareText + "\n\nLogioki does not reverse-engineer or flash firmware."
                }
                StartupPage {}
            }
        }
    }

    component PageFrame: ScrollView {
        clip: true
        topPadding: Design.space
        bottomPadding: Design.space
        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
        contentWidth: availableWidth
        Component.onCompleted: contentItem.boundsBehavior = Flickable.StopAtBounds
    }

    component PageHeading: ColumnLayout {
        property string eyebrow
        property string heading
        property string detail: ""
        spacing: 4
        Label {
            text: parent.eyebrow
            color: Design.primary
            font.pixelSize: Design.labelMediumSize
            font.weight: Font.DemiBold
            font.letterSpacing: 1
        }
        Label {
            text: parent.heading
            color: Design.foreground
            font.pixelSize: Design.headlineMediumSize
            font.weight: Font.DemiBold
            wrapMode: Text.Wrap
            Layout.fillWidth: true
        }
        Label {
            text: parent.detail
            visible: text.length > 0
            color: Design.foregroundMuted
            font.pixelSize: Design.supportingSize
            wrapMode: Text.Wrap
            Layout.fillWidth: true
        }
    }

    component EmptyPage: PageFrame {
        id: emptyPage
        property string eyebrow
        property string heading
        property string detail
        ColumnLayout {
            x: Design.containerPadding
            width: Math.max(0, emptyPage.availableWidth - Design.containerPadding * 2)
            spacing: Design.space
            PageHeading { eyebrow: emptyPage.eyebrow; heading: emptyPage.heading; detail: emptyPage.detail; Layout.fillWidth: true }
        }
    }

    component PresetsPage: PageFrame {
        id: presetsPage
        ColumnLayout {
            x: Design.stackGap
            width: Math.max(0, presetsPage.availableWidth - Design.stackGap * 2)
            spacing: Design.stackGap
            PageHeading {
                eyebrow: "SCENES"
                heading: window.vm.activePreset
                detail: "Streaming and Video Calls are editable starting points based on the current camera."
                Layout.fillWidth: true
            }
            Repeater {
                model: window.vm.presets
                delegate: Item {
                    id: presetWrapper
                    required property int index
                    required property string name
                    required property bool builtin
                    required property bool editable
                    Layout.fillWidth: true
                    implicitHeight: presetRow.implicitHeight
                    PresetRow {
                        id: presetRow
                        anchors.fill: parent
                        enabled: !window.vm.busy
                        rowIndex: presetWrapper.index
                        name: presetWrapper.name
                        builtin: presetWrapper.builtin
                        editable: presetWrapper.editable
                        onApplyRequested: window.vm.applyPreset(rowIndex)
                        onSaveRequested: window.vm.updatePreset(rowIndex)
                        onDeleteRequested: window.vm.deletePreset(rowIndex)
                    }
                }
            }
            CinematicButton { text: "+  New scene"; primary: true; enabled: !window.vm.busy; onClicked: newPresetDialog.open() }
        }
    }

    component ControlsPage: PageFrame {
        id: controlsPage
        objectName: "controlsPage-" + pageName
        required property string pageName
        required property var controlModel
        ColumnLayout {
            objectName: "controlsColumn-" + controlsPage.pageName
            x: Design.stackGap
            width: Math.max(0, controlsPage.availableWidth - Design.stackGap * 2)
            spacing: Design.controlInnerGap
            PageHeading {
                eyebrow: controlsPage.pageName === "image" ? "COLOR & LIGHT" : "OPTICS & CAPTURE"
                heading: controlsPage.pageName === "image" ? "Image adjustments" : "Camera controls"
                detail: controlsPage.pageName === "image" ? "Tune the visual character of the live feed." : "Control exposure, focus, and framing behavior."
                Layout.fillWidth: true
            }
            Repeater {
                objectName: "controlsRepeater-" + controlsPage.pageName
                model: controlsPage.controlModel
                delegate: Item {
                    id: controlWrapper
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
                    objectName: "control-wrapper-" + controlId
                    Layout.fillWidth: true
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
            x: Design.containerPadding
            width: Math.max(0, infoPage.availableWidth - Design.containerPadding * 2)
            spacing: Design.space
            PageHeading {
                eyebrow: "DEVICE"
                heading: "Camera diagnostics"
                detail: "Technical information for the connected capture device."
                Layout.fillWidth: true
            }
            Rectangle { Layout.fillWidth: true; implicitHeight: diagnosticsLabel.implicitHeight + 32; radius: Design.radius; color: Design.surfaceContainer; border.width: 1; border.color: Design.outlineVariant
                Label { id: diagnosticsLabel; anchors.fill: parent; anchors.margins: 16; text: window.vm.diagnosticsText; wrapMode: Text.Wrap; color: Design.foregroundMuted; font.family: Design.monoFamily; font.pixelSize: Design.monoSize }
            }
            Label { text: "Identity and USB details are redacted. Logs contain no frames and are never sent automatically."; wrapMode: Text.Wrap; Layout.fillWidth: true; color: Design.foregroundMuted; font.pixelSize: Design.supportingSize }
            CinematicButton { text: "Export diagnostics…"; primary: true; enabled: window.vm.hasCamera && !window.vm.busy; Accessible.name: "Export diagnostics"; onClicked: exportDialog.open() }
        }
    }

    component StartupPage: PageFrame {
        id: startupPage
        ColumnLayout {
            x: Design.stackGap
            width: Math.max(0, startupPage.availableWidth - Design.stackGap * 2)
            spacing: Design.stackGap
            PageHeading { eyebrow: "WORKFLOW"; heading: "Startup behavior"; detail: "Choose what Logioki restores when your session begins."; Layout.fillWidth: true }
            StartupRow { Layout.fillWidth: true; enabled: !window.vm.busy; title: "Restore settings at login"; supporting: "Runs the dependency-light headless restore service."; checked: window.vm.restoreAtLogin; switchObjectName: "restoreStartupSwitch"; onChanged: function(checked) { window.vm.setRestoreAtLogin(checked) } }
            StartupRow { Layout.fillWidth: true; enabled: !window.vm.busy; title: "Open Logioki at login"; supporting: "Opening the app also restores settings; duplicate restore writers are avoided."; checked: window.vm.openAtLogin; switchObjectName: "openStartupSwitch"; onChanged: function(checked) { window.vm.setOpenAtLogin(checked) } }
        }
    }
}
