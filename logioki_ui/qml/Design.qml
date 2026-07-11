pragma Singleton
import QtQuick

QtObject {
    property SystemPalette systemPalette: SystemPalette {}
    readonly property bool compact: PlatformProfile.compact
    property int colorSchemeOverride: -1
    readonly property bool dark: colorSchemeOverride === 1 || (colorSchemeOverride < 0 && Application.styleHints.colorScheme === Qt.ColorScheme.Dark)
    property bool highContrast: false
    property bool reducedMotion: false

    readonly property color brand: highContrast ? text : (dark ? "#9ca1ff" : "#4f57d9")
    readonly property color accent: systemPalette.highlight
    readonly property color surface: dark ? "#202126" : "#ffffff"
    readonly property color surfaceRaised: dark ? "#292b31" : "#f7f8fb"
    readonly property color canvas: dark ? "#17181c" : "#eef0f5"
    readonly property color text: dark ? "#f3f4f7" : "#20222a"
    readonly property color border: highContrast ? text : (dark ? "#41444d" : "#d7dae3")
    readonly property color control: dark ? "#32343b" : "#f2f3f7"
    readonly property color controlHover: dark ? "#41444d" : "#e7e9f0"
    readonly property color selectedText: "#ffffff"
    readonly property color mutedText: dark ? "#b3b6c0" : "#616673"
    readonly property color success: "#2e9b68"
    readonly property color warning: "#c47c16"
    readonly property color error: "#d04a54"
    readonly property color previewBackdrop: "#090a0c"
    readonly property color previewText: "#ffffff"
    readonly property color previewMutedText: "#b9bbc2"

    readonly property int spaceCompact: compact ? 6 : 8
    readonly property int space: compact ? 12 : 16
    readonly property int spaceRoomy: compact ? 20 : 24
    readonly property int rowHeight: compact ? 48 : 56
    readonly property int radius: compact ? 9 : 12
    readonly property int focusWidth: highContrast ? 3 : 2
    readonly property int transition: reducedMotion ? 0 : 160
    readonly property int bodySize: compact ? 10 : 11
    readonly property int supportingSize: compact ? 9 : 10
    readonly property int rowTitleSize: compact ? 10 : 11
    readonly property int sectionSize: compact ? 15 : 16
    readonly property int displaySize: compact ? 20 : 22
}
