/**
 *  Fish Tank Light
 *
 *  Copyright 2018 Stephen Pape
 *
 *  Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except
 *  in compliance with the License. You may obtain a copy of the License at:
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 *  Unless required by applicable law or agreed to in writing, software distributed under the License is distributed
 *  on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the License
 *  for the specific language governing permissions and limitations under the License.
 *
 */
metadata {
  definition (name: "Fish Tank pH Sensor", namespace: "srpape", author: "Stephen Pape") {
    capability "pH Measurement"
    capability "Refresh"      
    command "refresh"
  }

  tiles {
    valueTile("pH", "device.pH", width: 2, height: 2) {
      state("pH", label:'${currentValue}',
        backgroundColors:[
          [value: 6, color: "#ff0000"],
          [value: 7, color: "#D3D3D3"],
          [value: 8, color: "#0000ff"],
        ]
      )
    }
    standardTile("refresh", "command.refresh", inactiveLabel: false) {
      state "default", label:'refresh', action:"refresh.refresh", icon:"st.secondary.refresh-icon"
    }
  }
}

// parse events into attributes
def parse(command) {
  if (command.pH != null) {
    sendEvent(name: "pH", value: command.pH)
  }
}

public setPath(String deviceId) {
  state.deviceId = deviceId
}

def refresh() {
  parent.refresh(state.deviceId)
}