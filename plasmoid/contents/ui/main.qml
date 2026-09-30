import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as QQC2
import org.kde.plasma.plasmoid
import org.kde.plasma.components as PlasmaComponents
import org.kde.plasma.plasma5support as P5Support
import org.kde.kirigami as Kirigami

PlasmoidItem {
    id: root

    // Path to the launcher written by install.sh.
    readonly property string cli: "$HOME/.local/bin/vr-noise-mask"
    property bool running: false
    property bool active: false
    property bool enabled: true
    property int volume: 10
    property string device: ""

    toolTipMainText: "VR Noise Mask"
    toolTipSubText: !running ? "Not running (starts with Envision)"
                   : !enabled ? "Disabled"
                   : active ? "Playing at " + volume + "%"
                   : "Waiting for device"

    Plasmoid.icon: Qt.resolvedUrl("../icon.svg")

    compactRepresentation: MouseArea {
        onClicked: root.expanded = !root.expanded
        Kirigami.Icon {
            anchors.fill: parent
            source: Plasmoid.icon
            opacity: root.active && root.enabled ? 1.0 : 0.4  // dim when silent
        }
    }

    P5Support.DataSource {
        id: exec
        engine: "executable"
        connectedSources: []
        onNewData: (source, data) => {
            disconnectSource(source)
            if (source.indexOf(" get") > 0 && data["exit code"] === 0) {
                const s = JSON.parse(data["stdout"])
                root.running = s.running
                root.active = s.active
                root.enabled = s.enabled
                root.device = s.device_match
                if (!slider.pressed)
                    root.volume = s.volume_pct
            }
        }
    }

    function run(args) { exec.connectSource(cli + " " + args) }

    Timer {
        interval: 2000
        running: true
        repeat: true
        triggeredOnStart: true
        onTriggered: root.run("get")
    }

    fullRepresentation: ColumnLayout {
        Layout.minimumWidth: Kirigami.Units.gridUnit * 16
        Layout.minimumHeight: Kirigami.Units.gridUnit * 8
        spacing: Kirigami.Units.smallSpacing

        PlasmaComponents.Switch {
            text: "Enabled"
            checked: root.enabled
            onToggled: { root.enabled = checked; root.run("set --enabled " + (checked ? "on" : "off")) }
        }

        RowLayout {
            Layout.fillWidth: true
            PlasmaComponents.Label { text: "Volume" }
            PlasmaComponents.Slider {
                id: slider
                Layout.fillWidth: true
                from: 0
                to: 50
                stepSize: 1
                value: root.volume
                onMoved: root.volume = value
                onPressedChanged: if (!pressed) root.run("set --volume " + Math.round(value))
            }
            PlasmaComponents.Label { text: root.volume + "%"; Layout.minimumWidth: Kirigami.Units.gridUnit * 2 }
        }

        PlasmaComponents.Label {
            Layout.fillWidth: true
            wrapMode: Text.Wrap
            opacity: 0.7
            text: (!root.running ? "Not running — it starts with Envision."
                   : root.active ? "Playing on “" + root.device + "”"
                   : "Waiting for output device “" + root.device + "”")
        }
    }
}
