/**
 *  Fish Tank
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
	definition (name: "Raspberry Pi Fish Tank", namespace: "srpape", author: "Stephen Pape") {
        capability "Switch"
	    capability "SwitchLevel"
        capability "Temperature Measurement"
        capability "pH Measurement"
        capability "Water Sensor"
        capability "Refresh"
        
        command "refresh"
        command "change_water"
	}

    tiles(scale: 2) {
    	// Top light, level, and temperature display
		multiAttributeTile(name:"switch", type: "lighting", width: 6, height: 4, canChangeIcon: true){
			tileAttribute ("device.switch", key: "PRIMARY_CONTROL") {
				attributeState "on", label:'${name}', action:"switch.off", icon:"st.lights.philips.hue-single", backgroundColor:"#79b821"
				attributeState "off", label:'${name}', action:"switch.on", icon:"st.lights.philips.hue-single", backgroundColor:"#ffffff"
			}
            tileAttribute("device.temperature", key: "SECONDARY_CONTROL") {
       			attributeState("temperature", label:'${currentValue}°', unit:"F", defaultState: true)
    		}
            tileAttribute ("device.level", key: "SLIDER_CONTROL", height: 1, width: 2) {
				attributeState "level", action:"switch level.setLevel"
			}
		}
        
        // pH display
        valueTile("pH", "device.pH", width: 2, height: 2) {
            state("pH", label:'pH: ${currentValue}',
                backgroundColors:[
                    [value: 6, color: "#FF0000"],
                    [value: 7, color: "#DCDCDC"],
                    [value: 8, color: "#0000FF"]
                ]
            )
        }
 
		valueTile("WaterLevel", "device.water", width: 2, height: 2, decoration: "flat") {
			state ("low", label: "Low", icon: "st.alarm.water.wet", action:"refresh", backgroundColor: "#ffffff")
			state ("full", label: "Full", icon: "st.alarm.water.dry", action:"refresh", backgroundColor: "#00A0DC")
		}
        
        standardTile("Water Change", "device.switch", inactiveLabel: false, width: 2, height: 2) {
			state "default", label:"Change Water", action:"change_water", icon: "st.Bath.bath20"
		}
        
        
        valueTile("Padding1", "device.power", decoration: "flat",  height: 3, width: 1)    
        valueTile("DrainLabel", "device.power", decoration: "flat",  height: 1, width: 2) {
        	state "power", label:'Drain Valve'
        }        
        valueTile("FillLabel", "device.power", decoration: "flat",  height: 1, width: 2) {
        	state "power", label:'Fill Valve'
        } 
        valueTile("Padding1", "device.power", decoration: "flat",  height: 3, width: 1)         

        childDeviceTile("valve/drain", "valve/drain", height: 2, width: 2)        
        childDeviceTile("valve/fill", "valve/fill", height: 2, width: 2) 
    }
}

def installed() {
	log.debug "installed()"
	addChildDevices()
}

private addFishTankDevice(String deviceId, String deviceType, String deviceName) {
    def newdevice = addChildDevice(deviceType, deviceId, null, [componentName: deviceId, label: deviceName, componentLabel: deviceName, completedSetup: true, isComponent: true])
    newdevice.setPath(deviceId)
    log.debug("Added device: ${deviceId}")
}

private addChildDevices() {
	log.debug "Adding fishtank child devices"  
  	addFishTankDevice("valve/drain", "Fish Tank Valve", "Fish Tank Drain Valve")
  	addFishTankDevice("valve/fill", "Fish Tank Valve", "Fish Tank Fill Valve")
}

// parse events into attributes
def parse_json(deviceId, json) {
	def children = getChildDevices()

	// Built in    
    if (deviceId == "light/tank") {
        parse_light(json)
	} else if (deviceId == "temperature/tank") {
    	def newTemp = 0.0
    	if (location.temperatureScale == "F") {
        	newTemp = json.temperatureF
        } else if (location.temperatureScale == "C") {
        	newTemp = json.temperatureC
        }
        log.debug "Updating temperature value: ${newTemp}"
        sendEvent(name: "temperature", value: newTemp, "unit": location.temperatureScale)
    } else if (deviceId == "ph/tank") {
        log.debug "Updating pH value: ${json.pH}" 
		sendEvent(name: "pH", value: json.pH)
    } else if (deviceId == "water_level/tank") {
        log.debug "Updating water level value: ${json.state}" 
		if (json.state == 0) {
        	// Not full
            log.debug "Water level is low"
            sendEvent(name: "water", value: "low")
        } else if (json.state == 1) {
        	// Full
            log.debug "Water level is full"
            sendEvent(name: "water", value: "full")
        }
    } else {
    	// Try our child devices
		children.each { child ->
    		if (child.getPath() == deviceId) {
        		child.parse_json(json)
				return
       		}
        }
	}	
}

private parse_light(command) {
  log.debug("parse(): command=${command}")
  
  def newState = command.state.toInteger()
  if (newState != state.internal_level) {
    log.debug("newState: ${newState}")
    if (newState == 0) {
      state.internal_level = newState
      sendEvent(name: "switch", value: "off")
    } else if(newState == 1) {
      state.internal_level = newState
      sendEvent(name: "switch", value: "on")
      state.level = 49
      sendEvent(name: "level", value: state.level)
    } else if(newState == 2) {
      state.internal_level = newState
      sendEvent(name: "switch", value: "on")
      state.level = 100
      sendEvent(name: "level", value: state.level)
    } else {
      log.debug "Invalid state : ${command.state}"
    }
  } else {
    log.debug "State not updated : ${command.state}"
  }
}

def change_water() {
	log.debug "Sending water change command"
	parent.post("action/change_water", "")
}

public def refresh() {
    refresh("light/tank")
    refresh("valve/drain")
    refresh("valve/fill")
    refresh("water_level/tank")
    refresh("temperature/tank")
    refresh("ph/tank")
}

public refresh(String deviceId) {
  log.debug "Refreshing ${deviceId}"
  parent.query(deviceId)
}

public setState(String deviceId, state) {
  log.debug "Setting ${deviceId} to ${state}"
  parent.post(deviceId, "state=${state}")
}

// handle commands
public def setLevel(value) {
  log.debug "setLevel(): ${value}"
  
  if (value >= 50) {
    state.internal_level = 2
    state.level = 100
  } else if (value >= 1) {
    state.internal_level = 1
    state.level = 49
  } else {
  	state.internal_level = 0
  	state.level = 0
  }
  
  setState("light/tank", state.internal_level)
}

def off() {
  sendEvent(name: "switch", value: "off")
  state.internal_level = 0
  setState("light/tank", 0)
}

def on() {
  if (state.internal_level == null || state.internal_level == 0) {
    // The level is set to off, resume the previous level
    if (state.level == null || state.level == 0) {
      state.level = 100
    }
    if (state.level > 50) {
      state.internal_level = 2
      state.level = 100
    } else {
      state.internal_level = 1
      state.level = 49
    }
    log.debug "Updating level to ${state.level}"
    sendEvent(name: "level", value: state.level)
  }
  setState("light/tank", state.internal_level)
  sendEvent(name: "switch", value: "on")
}