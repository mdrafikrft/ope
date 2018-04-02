import QtQuick 2.9
import QtQuick.Controls 2.2

ApplicationWindow {
    visible: true
    id: window
    objectName: "window"
    width: 900
    height: 600
    title: qsTr("Drop Test")

    Rectangle {
        id: dropFileTarget
        color: "#ff0000"
        anchors.fill: parent

        Text {
            text: "Drop Target"

        }
        DropArea {
            id: fileDropArea
            anchors.fill: parent

            //keys: ["text/plain", ]
            onDropped: {

                console.log("drop hastext " + drop.hasText + " - " + drop.text)
                console.log("Drop action " + drop.proposedAction)
                console.log(drop.urls)
                console.log("Source "+ drop.source)
                //console.log("Formats " + drop.formats)
            }
        }
        states: [
            State {
                when: fileDropArea.containsDrag

            }

        ]
    }


}
