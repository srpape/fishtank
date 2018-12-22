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
  definition (name: "Fish Tank Light", namespace: "srpape", author: "Stephen Pape") {
    capability "Switch"
    capability "SwitchLevel"
    capability "Refresh"    
    command "refresh"
  }
    
  tiles {
    standardTile("actionFlat", "device.switch", width: 2, height: 2, decoration: "flat") {
      state "off", label: 'Off', action: "switch.on", icon: "st.switches.light.off", backgroundColor: "#ffffff"
      state "on", label: 'On', action: "switch.off", icon: "st.switches.light.on", backgroundColor: "#00a0dc"
    }
    controlTile("levelSliderControl", "device.level", "slider", height: 2, width: 1) {
      state "level", action:"switch level.setLevel"
    }
    standardTile("refresh", "command.refresh", inactiveLabel: false) {
      state "default", label:'refresh', action:"refresh.refresh", icon:"st.secondary.refresh-icon"
    }
  }
}

// parse events into attributes
def parse(command) {
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

// handle commands
public def setLevel(value) {
  log.debug "setLevel(): ${value}"
  
  def is_on = (state.internal_level != 0)
  
  if (value >= 50) {
    state.internal_level = 2
    state.level = 100
    if (!is_on) {
      sendEvent(name: "switch", value: "on")
    }
  } else if (value >= 1) {
    state.internal_level = 1
    state.level = 49
    if (!is_on) {
      sendEvent(name: "switch", value: "on")
    }
  } else {
  	state.internal_level = 0
  	state.level = 0
    if (is_on) {
      sendEvent(name: "switch", value: "off")
    }
  }
  
  parent.setState(state.deviceId, state.internal_level)
  sendEvent(name: "level", value: state.level)
}

def off() {
  sendEvent(name: "switch", value: "off")
  state.internal_level = 0
  parent.setState(state.deviceId, 0)
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
  parent.setState(state.deviceId, state.internal_level)
  sendEvent(name: "switch", value: "on")
}

public setPath(String deviceId) {
  state.deviceId = deviceId
}

def refresh() {
  parent.refresh(state.deviceId)
}