pragma Singleton
import QtQuick

QtObject {
    property string name: "kde"

    readonly property bool isKde: name === "kde"
    readonly property bool isGnome: name === "gnome"
    readonly property bool isMacOS: name === "macos"
    readonly property bool compact: isKde
    readonly property bool comfortable: !compact
    readonly property string primaryModifierLabel: isMacOS ? "⌘" : "Ctrl"
}
