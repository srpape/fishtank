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
	definition (name: "Fish Tank Temperature Sensor", namespace: "srpape", author: "Stephen Pape") {
		capability "Temperature Measurement"
        capability "Refresh"
        
        command "refresh"
	}

	tiles {
        valueTile("temperature", "device.temperature", width: 2, height: 2) {
            state("temperature", label:'${currentValue}', unit:"dF", icon:"st.Weather.weather2",
                backgroundColors:[
                    [value: 75, color: "#0000ff"],
                    [value: 80, color: "#D3D3D3"],
                    [value: 85, color: "#ff0000"],
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
  if (command.temperatureF != null) {
    log.debug "Updating temperature value: ${command.temperatureF}"
    sendEvent(name: "temperature", value: command.temperatureF)
  } else {
      log.debug "No temperatureF in comand: ${command}"
  }
}

public setPath(String deviceId) {
  state.deviceId = deviceId
}

def refresh() {
  parent.refresh(state.deviceId)
}