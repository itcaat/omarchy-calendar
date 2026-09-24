import QtQuick
import QtQuick.Controls
import qs.Commons
import qs.Ui

// The calendar's settings page, shown in place of the month grid.
//
// Kept in its own file rather than folded into Panel.qml: the panel is
// already long, and everything here is presentation over values the panel
// owns. This component reads state and emits intent, it never writes
// shell.json itself.
Column {
  id: root

  property color foreground: "white"
  property string fontFamily: ""

  property var calendars: []
  property var hiddenCalendars: []
  property bool showYearProgress: false
  property bool weekStartsMonday: true
  property bool showWorkingLocation: false
  property bool hideDeclined: false
  property int announceLeadMinutes: 15

  property string syncedAt: ""
  property int eventCount: 0
  property string syncState: "missing"
  property bool icalBusy: false
  property string icalAction: "add"
  property string icalMessage: ""
  property var icalColors: [
    "#4285f4", "#34a853", "#ea4335", "#fbbc04", "#a142f4",
    "#24c1e0", "#f538a0", "#ff8c42", "#7cb342"
  ]
  property string selectedIcalColor: icalColors[Math.floor(Math.random() * icalColors.length)]

  signal calendarToggled(string calendarId)
  signal yearProgressToggled()
  signal weekStartToggled()
  signal workingLocationToggled()
  signal hideDeclinedToggled()
  signal leadMinutesPicked(int minutes)
  signal icalAddRequested(string url, string color)
  signal icalRemoveRequested(string calendarId)

  readonly property color muted: Qt.darker(foreground, 1.5)
  readonly property color faint: Qt.darker(foreground, 1.9)

  spacing: Style.space(10)

  component SectionTitle: Text {
    color: root.faint
    font.family: root.fontFamily
    font.pixelSize: Style.font.caption
    font.letterSpacing: 1
    font.bold: true
  }

  // A row that reads as a switch without pulling in a control library the
  // rest of this plugin does not use.
  component ToggleRow: Rectangle {
    id: toggle

    property string label: ""
    property string hint: ""
    property bool checked: false
    property color swatch: "transparent"
    property bool removable: false
    property bool showCheck: true
    readonly property bool hasSwatch: toggle.swatch.a > 0.001

    signal activated()
    signal removeRequested()

    width: parent ? parent.width : 0
    height: toggleBody.height + Style.space(6)
    radius: Style.cornerRadius
    color: hovered.hovered
      ? Qt.rgba(root.foreground.r, root.foreground.g, root.foreground.b, 0.06)
      : "transparent"

    HoverHandler { id: hovered }
    TapHandler { onTapped: toggle.activated() }

    Item {
      id: toggleBody
      anchors.left: parent.left
      anchors.right: parent.right
      anchors.leftMargin: Style.space(3)
      anchors.rightMargin: Style.space(3)
      anchors.verticalCenter: parent.verticalCenter
      height: toggleText.implicitHeight + (toggle.hint !== "" ? Style.space(15) : 0)

      Text {
        id: toggleCheck
        anchors.verticalCenter: parent.verticalCenter
        visible: toggle.showCheck
        width: toggle.showCheck ? Style.space(14) : 0
        text: toggle.checked ? "✓" : ""
        color: Qt.darker(root.foreground, 2.8)
        font.family: root.fontFamily
        font.pixelSize: Style.font.bodySmall
      }

      Rectangle {
        anchors.verticalCenter: parent.verticalCenter
        x: Style.space(18)
        visible: toggle.hasSwatch
        width: Style.space(4)
        height: width
        radius: width / 2
        color: toggle.checked ? toggle.swatch : "transparent"
        border.width: Style.spacing.hairline
        border.color: toggle.swatch
      }

      Column {
        id: toggleText
        anchors.verticalCenter: parent.verticalCenter
        anchors.left: parent.left
        anchors.leftMargin: toggle.hasSwatch
          ? Style.space(26)
          : (toggle.showCheck ? Style.space(18) : 0)
        anchors.right: parent.right
        anchors.rightMargin: toggle.removable ? Style.space(30) : 0
        spacing: Style.space(1)

        Text {
          width: parent.width
          text: toggle.label
          color: toggle.checked ? root.foreground : root.muted
          font.family: root.fontFamily
          font.pixelSize: Style.font.bodySmall
          elide: Text.ElideRight
        }

        Text {
          width: parent.width
          visible: toggle.hint !== ""
          text: toggle.hint
          color: root.faint
          font.family: root.fontFamily
          font.pixelSize: Style.font.caption
          elide: Text.ElideRight
        }
      }

      Rectangle {
        visible: toggle.removable
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        width: Style.space(22)
        height: width
        radius: width / 2
        color: removeHover.hovered
          ? Qt.rgba(root.foreground.r, root.foreground.g, root.foreground.b, 0.12)
          : "transparent"

        Text {
          anchors.centerIn: parent
          text: "×"
          color: root.faint
          font.family: root.fontFamily
          font.pixelSize: Style.font.bodySmall
        }

        HoverHandler { id: removeHover }
        TapHandler {
          onTapped: toggle.removeRequested()
        }
      }
    }
  }

  // ---- Calendars

  SectionTitle { text: qsTr("CALENDARS") }

  Text {
    width: parent.width
    visible: root.calendars.length === 0
    text: qsTr("Nothing synced yet, so there is nothing to choose from.")
    color: root.faint
    font.family: root.fontFamily
    font.pixelSize: Style.font.caption
    wrapMode: Text.WordWrap
  }

  Repeater {
    model: root.calendars

    ToggleRow {
      required property var modelData

      label: modelData.name
      swatch: modelData.color
      checked: root.hiddenCalendars.indexOf(modelData.id) === -1
      removable: true
      showCheck: false
      onActivated: root.calendarToggled(modelData.id)
      onRemoveRequested: root.icalRemoveRequested(modelData.id)
    }
  }

  Text {
    width: parent.width
    text: qsTr("Add an iCal subscription")
    color: root.muted
    font.family: root.fontFamily
    font.pixelSize: Style.font.caption
  }

  Row {
    id: icalInputRow
    width: parent.width
    spacing: Style.space(6)

    TextField {
      id: icalUrl
      width: icalInputRow.width - colorPicker.width - icalInputRow.spacing
      placeholderText: qsTr("https://… or webcal://…")
      foreground: root.foreground
      font.family: root.fontFamily
      onAccepted: root.addIcal()
    }

    Rectangle {
      id: colorPicker
      width: Style.space(72)
      height: icalUrl.height
      z: colorMenu.visible ? 10 : 0
      radius: Style.cornerRadius
      color: colorPickerHover.containsMouse
        ? Qt.rgba(root.foreground.r, root.foreground.g, root.foreground.b, 0.08)
        : "transparent"
      border.width: Style.spacing.hairline
      border.color: root.muted

      Rectangle {
        anchors.left: parent.left
        anchors.leftMargin: Style.space(7)
        anchors.verticalCenter: parent.verticalCenter
        width: Style.space(10)
        height: width
        radius: width / 2
        color: root.selectedIcalColor
      }

      Text {
        anchors.left: parent.left
        anchors.leftMargin: Style.space(23)
        anchors.verticalCenter: parent.verticalCenter
        text: "▾"
        color: root.faint
        font.family: root.fontFamily
        font.pixelSize: Style.font.caption
      }

      MouseArea {
        id: colorPickerHover
        anchors.fill: parent
        hoverEnabled: true
        onClicked: colorMenu.visible ? colorMenu.close() : colorMenu.open()
      }

      Popup {
        id: colorMenu
        x: colorPicker.mapToItem(null, 0, colorPicker.height + Style.space(2)).x
        y: colorPicker.mapToItem(null, 0, colorPicker.height + Style.space(2)).y
        width: colorPicker.width
        height: root.icalColors.length * Style.space(24) + Style.space(4)
        padding: Style.space(2)
        modal: true
        dim: false
        closePolicy: Popup.CloseOnPressOutside | Popup.CloseOnEscape

        background: Rectangle {
          color: Qt.darker(root.foreground, 2.8)
          border.width: Style.spacing.hairline
          border.color: root.muted
        }

        Column {
          anchors.fill: parent

          Repeater {
            model: root.icalColors

            Rectangle {
              required property string modelData
              width: colorMenu.availableWidth
              height: Style.space(24)
              color: colorMenuItemMouse.containsMouse
                ? Qt.rgba(0, 0, 0, 0.12)
                : "transparent"

              Rectangle {
                anchors.left: parent.left
                anchors.leftMargin: Style.space(5)
                anchors.verticalCenter: parent.verticalCenter
                width: Style.space(10)
                height: width
                radius: width / 2
                color: modelData
              }

              MouseArea {
                id: colorMenuItemMouse
                anchors.fill: parent
                hoverEnabled: true
                onClicked: {
                  root.selectedIcalColor = modelData
                  colorMenu.close()
                }
              }
            }
          }
        }
      }
    }
  }

  Rectangle {
    width: addIcalLabel.width + Style.space(12)
    height: addIcalLabel.height + Style.space(6)
    radius: height / 2
    color: addHover.hovered
      ? Qt.rgba(root.foreground.r, root.foreground.g, root.foreground.b, 0.14)
      : "transparent"
    border.width: Style.spacing.hairline
    border.color: root.muted

    Text {
      id: addIcalLabel
      anchors.centerIn: parent
      text: root.icalBusy
        ? (root.icalAction === "remove" ? qsTr("Removing…") : qsTr("Adding…"))
        : qsTr("Add calendar")
      color: root.foreground
      font.family: root.fontFamily
      font.pixelSize: Style.font.caption
    }

    HoverHandler { id: addHover }
    TapHandler {
      enabled: !root.icalBusy
      onTapped: root.addIcal()
    }
  }

  Text {
    width: parent.width
    visible: root.icalMessage !== ""
    text: root.icalMessage
    color: root.faint
    font.family: root.fontFamily
    font.pixelSize: Style.font.caption
    wrapMode: Text.WordWrap
  }

  function addIcal() {
    var url = String(icalUrl.text).trim()
    if (url === "") return
    root.icalAddRequested(url, root.selectedIcalColor)
    icalUrl.text = ""
    root.selectedIcalColor = root.icalColors[Math.floor(Math.random() * root.icalColors.length)]
  }

  // ---- Display

  SectionTitle { text: qsTr("DISPLAY") }

  ToggleRow {
    label: qsTr("Week starts on Monday")
    hint: qsTr("Off starts the week on Sunday")
    checked: root.weekStartsMonday
    onActivated: root.weekStartToggled()
  }

  ToggleRow {
    label: qsTr("Working location events")
    hint: qsTr("Work-from-home markers, hidden by default")
    checked: root.showWorkingLocation
    onActivated: root.workingLocationToggled()
  }

  ToggleRow {
    // Every row on this page reads "checked means shown". Phrasing this one as
    // "Hide ..." inverted that and made the page contradict itself.
    label: qsTr("Declined invitations")
    hint: qsTr("Shown struck through when on")
    checked: !root.hideDeclined
    onActivated: root.hideDeclinedToggled()
  }

  ToggleRow {
    label: qsTr("Year and life progress")
    hint: qsTr("The upstream clock's bars, off by default")
    checked: root.showYearProgress
    onActivated: root.yearProgressToggled()
  }

  // ---- Bar

  SectionTitle { text: qsTr("BAR LABEL") }

  Text {
    width: parent.width
    text: qsTr("How early the bar gives up the clock to announce what is next.")
    color: root.faint
    font.family: root.fontFamily
    font.pixelSize: Style.font.caption
    wrapMode: Text.WordWrap
  }

  Row {
    spacing: Style.space(3)

    Repeater {
      model: [0, 5, 15, 30, 60]

      Rectangle {
        required property var modelData

        readonly property bool active: modelData === root.announceLeadMinutes

        width: leadLabel.width + Style.space(8)
        height: leadLabel.height + Style.space(4)
        radius: height / 2
        color: active
          ? Qt.rgba(root.foreground.r, root.foreground.g, root.foreground.b, 0.14)
          : "transparent"
        border.width: Style.spacing.hairline
        border.color: active ? root.muted : Qt.darker(root.foreground, 2.4)

        Text {
          id: leadLabel
          anchors.centerIn: parent
          text: modelData === 0 ? qsTr("Never") : modelData + qsTr("min")
          color: active ? root.foreground : root.faint
          font.family: root.fontFamily
          font.pixelSize: Style.font.caption
        }

        TapHandler { onTapped: root.leadMinutesPicked(modelData) }
      }
    }
  }

  // ---- Sync status

  SectionTitle { text: qsTr("SYNC") }

  Text {
    width: parent.width
    color: root.faint
    font.family: root.fontFamily
    font.pixelSize: Style.font.caption
    wrapMode: Text.WordWrap

    text: {
      if (root.syncState === "missing") return qsTr("No iCal calendars connected. Add one above.")
      if (root.syncState === "version") return qsTr("The events file was written by a newer version of this plugin.")

      var line = root.eventCount + qsTr(" events from iCal")
      if (root.syncState === "stale") {
        return line + qsTr("\nLast sync looks old. Check: journalctl --user -u omarchy-calendar-sync")
      }
      return line + qsTr("\nLast sync ") + root.syncedAt
    }
  }
}
