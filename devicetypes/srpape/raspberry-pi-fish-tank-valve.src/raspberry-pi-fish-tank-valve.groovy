/**
 *  Fish Tank Valve
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
  definition (name: "Raspberry Pi Fish Tank Valve", namespace: "srpape", author: "Stephen Pape") {
    capability "Valve"  
  }

  tiles {
    standardTile("contact", "device.contact", width: 2, height: 2, canChangeIcon: true) {
      state "closed", label: '${name}', action: "valve.open", icon: "st.valves.water.closed", backgroundColor: "#e86d13"
      state "open", label: '${name}', action: "valve.close", icon: "st.valves.water.open", backgroundColor: "#53a7c0"
    }
  }
}

public getPath() {
  return state.deviceId
}

// Called when we're created
public setPath(String deviceId) {
  state.deviceId = deviceId
  
  // TODO: Hacky
  if (state.deviceId == "valve/fill") {
      state.device_label = "Fill"
  }
  if (state.deviceId == "valve/drain") {
      state.device_label = "Drain"
  }
}

def open() {
  parent.setState(state.deviceId, "open")
}

def close() {
  parent.setState(state.deviceId, "closed")
}

// parse events into attributes
def parse_json(command) {
  if (command.state != state.valve) {
    if (command.state == "open") {
      state.valve = command.state
      sendEvent(name: "contact", value: "open")
    } else if (command.state == "closed") {
      state.valve = command.state
      sendEvent(name: "contact", value: "closed")
    }      
  }
}
