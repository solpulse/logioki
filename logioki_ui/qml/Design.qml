pragma Singleton
import QtQuick

QtObject {
    property SystemPalette systemPalette: SystemPalette {}
    readonly property bool compact: PlatformProfile.compact
    property int colorSchemeOverride: -1
    readonly property bool dark: colorSchemeOverride === 1 || (colorSchemeOverride < 0 && Application.styleHints.colorScheme === Qt.ColorScheme.Dark)
    property bool highContrast: false
    property bool reducedMotion: false

    // Plasma Cinematic color roles from DESIGN.md.
    readonly property color surfaceDim: "#111415"
    readonly property color surfaceBright: "#373a3b"
    readonly property color surfaceContainerLowest: "#0c0f10"
    readonly property color surfaceContainerLow: "#191c1d"
    readonly property color surfaceContainer: "#1d2021"
    readonly property color surfaceContainerHigh: "#282a2b"
    readonly property color surfaceContainerHighest: "#333536"
    readonly property color foreground: "#e1e2e4"
    readonly property color foregroundMuted: "#bec8d1"
    readonly property color outline: "#88929a"
    readonly property color outlineVariant: "#3e484f"
    readonly property color primary: "#84cfff"
    readonly property color primaryForeground: "#00344c"
    readonly property color primaryContainer: "#3daee9"
    readonly property color primaryContainerForeground: "#003f5a"
    readonly property color secondary: "#c5c6ca"
    readonly property color secondaryContainer: "#494c4f"
    readonly property color error: "#ffb4ab"
    readonly property color errorForeground: "#690005"
    readonly property color errorContainer: "#93000a"
    readonly property color background: "#111415"
    readonly property color glass: "#e61d2021"
    readonly property color success: "#72d6a0"
    readonly property color warning: "#ffbf69"

    // Compatibility aliases keep every component on the same semantic palette.
    readonly property color brand: highContrast ? foreground : primary
    readonly property color accent: primary
    readonly property color surface: surfaceContainerLow
    readonly property color surfaceRaised: surfaceContainer
    readonly property color canvas: background
    readonly property color text: foreground
    readonly property color border: highContrast ? foreground : outlineVariant
    readonly property color control: surfaceContainerHigh
    readonly property color controlHover: surfaceContainerHighest
    readonly property color selectedText: primaryForeground
    readonly property color mutedText: foregroundMuted
    readonly property color previewBackdrop: surfaceContainerLowest
    readonly property color previewText: foreground
    readonly property color previewMutedText: foregroundMuted

    // 4px baseline grid and fixed professional-workspace dimensions.
    readonly property int grid: 4
    readonly property int spaceCompact: 8
    readonly property int space: 16
    readonly property int spaceRoomy: 20
    readonly property int stackGap: 12
    readonly property int controlInnerGap: 8
    readonly property int containerPadding: 20
    readonly property int sidebarLeft: 280
    readonly property int sidebarRight: 320
    readonly property int rowHeight: 52
    readonly property int radiusSmall: 4
    readonly property int radius: 8
    readonly property int radiusContainer: 12
    readonly property int radiusOverlay: 16
    readonly property int radiusFull: 9999
    readonly property int focusWidth: highContrast ? 3 : 2
    readonly property int transition: reducedMotion ? 0 : 160

    // DESIGN.md typography scale. Qt falls back cleanly if Inter is unavailable.
    readonly property string fontFamily: "Inter"
    readonly property string monoFamily: "JetBrains Mono"
    readonly property int headlineLargeSize: 24
    readonly property int headlineMediumSize: 18
    readonly property int bodyLargeSize: 16
    readonly property int bodySize: 14
    readonly property int labelMediumSize: 12
    readonly property int labelSmallSize: 11
    readonly property int monoSize: 12
    readonly property int supportingSize: labelSmallSize
    readonly property int rowTitleSize: bodySize
    readonly property int sectionSize: headlineMediumSize
    readonly property int displaySize: headlineLargeSize
}
