"""
<plugin key="MotionShades" name="Motion rolling shades by Coulisse" author="ESCape" version="2.3" externallink="https://github.com/d-EScape/MotionShades-for-Domoticz">
    <description>
        <h2>Motion rolling shades</h2><br/>
        See the current status of shades en control them from Domoticz. Requires a WiFi bridge for the shades and the motionblinds python module from https://github.com/starkillerOG/motion-blinds.
        The module -written by starkillerOG- does all the heavy lifting. This plugin makes it work with Domoticz. 
        Communication with the bridge is asynchronous and relies on IGMP multitast. In some networks that can be a problem. In my Asus aiMesh setup i had to disable IGMP snooping on the 2.4 Wifi interface to get it to work.
        <h3>Devices</h3>
        <ul style="list-style-type:square">
            <li>Only supports rolling shades for now. But might also work with comparable device types based on the same hardware.</li>
            <li>Please add different types of curtains and blinds as a pull request on github!</li>
            <li>Motion device types can be identified in the api but are not checked by this plugin yet (it will asume rolling shades).</li>
        </ul>
        <h3>Configuration</h3>
        The plugin needs to communicate to the wifi bridge for the motion (bi-directional) 433MHz controller, using a api key you can find in the official motion app. In the (configured!) app go to settings > about and tap the screen several times. It will show the api-key in a window called "reminder".
        The status gets updated on every movement of the blinds.
        The forced update every [configurable] hours ensures that the battery level and signal level get updated once in a while, even if the blinds never moved. Every 24 hours could be often enough for that purpose and probably saves batteries. 
    </description>
    <params>
        <param field="Address" label="WiFi bridge IP Address" width="200px"/>
        <param field="Password" label="API key of the bridge" width="200px"/>
        <param field="Mode5" label="Force status update" width="150px">
            <options>
                <option label="every hour" value=1 />
                <option label="every 6 hours" value=6 />
                <option label="every 12 hours" value=12  default="true" />
                <option label="every 24 hours" value=24 />
            </options>
        </param>
        <param field="Mode6" label="Debug" width="150px">
            <options>
                <option label="None" value="0"  default="true" />
                <option label="Python Only" value="2"/>
                <option label="Basic Debugging" value="62"/>
                <option label="Basic+Messages" value="126"/>
                <option label="Connections Only" value="16"/>
                <option label="Connections+Queue" value="144"/>
                <option label="All" value="-1"/>
            </options>
        </param>
    </params>
</plugin>
"""
import Domoticz
#from Domoticz import Devices, Parameters
import threading
from datetime import datetime, timedelta
from motionblinds import MotionMulticast, MotionGateway

class BasePlugin:
    enabled = False
    def __init__(self):
        return
        
    class BlindHandler:
        #This wrapper class is needed to bind the callback to a specific blind, 
        #so not all blinds need to be updated every time a individual blind communicates
        def __init__(self, unitid, thisblind):
            self.myid=unitid
            self.blind=thisblind
            self.last_seen = datetime.now()-timedelta(days=1)
            self.enable_updates = True
            Domoticz.Debug("Created handler for: " + str(self.myid) + " and blind " + str(self.blind))
            self.blind.Register_callback("1", self.update_handler)
            Domoticz.Debug("Registered handler for " + str(self.myid) + ": " + str(self.update_handler))
            self.update_thread = threading.Thread(name="UpdateThread", target=BasePlugin.BlindHandler._background_updater, args=(self,))
                        
        def _background_updater(self):
            Domoticz.Debug("Have not seen " + self.blind.mac+ " for a long time. Request an update.")
            try:
                self.blind.Update_trigger()
            except Exception as err:
                Domoticz.Error("Error updating blind (" + self.blind.mac + ") status: "+str(err))
        
        def _update_domoticz(self):
            Domoticz.Debug("Update is for Domoticz unit: " + str(self.myid))
            if self.blind.position == 100:
                statevalue=0
            elif self.blind.position > 0:
                statevalue=2
            else:
                statevalue=1
            domposition=100-self.blind.position
            Domoticz.Log("Updating blinds values for:" + str(self.blind.mac) + " to " + str(self.blind.position) + "%; battery voltage=" + str(self.blind.battery_voltage) + " (" + str(self.blind.battery_level) + "%)" + "; RSSI=" + str(self.blind.RSSI))
            Devices[self.myid].Update(SignalLevel=rssi_to_signal(self.blind.RSSI), BatteryLevel=int(self.blind.battery_level), nValue=int(statevalue), sValue=str(domposition))   

        def update_handler(self):
            self.last_seen = datetime.now()            
            self._update_domoticz()
        
        def request_update_when_needed(self, interval):
            timesince=(datetime.now()-self.last_seen).total_seconds()
            Domoticz.Debug("Time since update for " + self.blind.mac + " is " + str(timesince))
            if  timesince > interval and self.enable_updates:
                self.last_seen = datetime.now() #just assume it will succeed to prevent flooding the 433MHz network with requests
                Domoticz.Debug("Time to update " + self.blind.mac)
                self.update_thread = threading.Thread(name="UpdateThread", target=BasePlugin.BlindHandler._background_updater, args=(self,))
                self.update_thread.start()
                
        def disable_updates(self):
            self.enable_updates = False
            
        def await_thread(self):
            if self.update_thread.is_alive():
                self.update_thread.join()
                
    def onStart(self):
        if Parameters["Mode6"] != "0":
            Domoticz.Debugging(int(Parameters["Mode6"]))
            DumpConfigToLog()
        self.allblinds={}
        self.interval=int(Parameters["Mode5"]) * 3600 #hours to seconds
        Domoticz.Debug("interval:" + str(self.interval))
        self.motion_multicast = MotionMulticast(interface = "any")
        self.motion_multicast.Start_listen()
        self.gateway = MotionGateway(ip = Parameters["Address"], key = Parameters["Password"], multicast = self.motion_multicast)
        self.gateway.Update()
        for blind in self.gateway.device_list.values():
            Domoticz.Debug(str(blind))
            myunit=get_or_create_unit(blind.mac)
            self.allblinds[myunit]=self.BlindHandler(myunit, blind)
        if Parameters["Mode6"] != "0":
            Domoticz.Error("WARNING: using a faster heartbeat for debugging (10 times normal interval)")
            Domoticz.Heartbeat(2)
        else:
            Domoticz.Heartbeat(20)
        
    def onStop(self):
        # wait for the background_updater threads to end (can run for up to 5 seconds per blind if timed-out!)
        for unitid in self.allblinds:
            self.allblinds[unitid].disable_updates()
        for unitid in self.allblinds:
            self.allblinds[unitid].await_thread()
        self.motion_multicast.Stop_listen()
            
    def onConnect(self, Connection, Status, Description):
        Domoticz.Debug("onConnect called")

    def onMessage(self, Connection, Data):
        Domoticz.Debug("onMessage called")

    def onCommand(self, Unit, Command, Level, Hue):
        Domoticz.Debug("onCommand called for Unit " + str(Unit) + ": Parameter '" + str(Command) + "', Level: " + str(Level))
        if Command == "Open":
            self.allblinds[Unit].blind.Open()
        elif Command == "Close":
            self.allblinds[Unit].blind.Close()
        elif Command == "Set Level":
            hwLevel=100-Level
            self.allblinds[Unit].blind.Set_position(hwLevel)
            

    def onNotification(self, Name, Subject, Text, Status, Priority, Sound, ImageFile):
        Domoticz.Debug("Notification: " + Name + "," + Subject + "," + Text + "," + Status + "," + str(Priority) + "," + Sound + "," + ImageFile)

    def onDisconnect(self, Connection):
        Domoticz.Debug("onDisconnect called")

    def onHeartbeat(self):
        #Request an update from the blinds every once in a while, to get the battery and signal strength, even if they have not been moved.
        for unitid in self.allblinds:
            self.allblinds[unitid].request_update_when_needed(self.interval)

global _plugin
_plugin = BasePlugin()

def onStart():
    global _plugin
    _plugin.onStart()

def onStop():
    global _plugin
    _plugin.onStop()

def onConnect(Connection, Status, Description):
    global _plugin
    _plugin.onConnect(Connection, Status, Description)

def onMessage(Connection, Data):
    global _plugin
    _plugin.onMessage(Connection, Data)

def onCommand(Unit, Command, Level, Hue):
    global _plugin
    _plugin.onCommand(Unit, Command, Level, Hue)

def onNotification(Name, Subject, Text, Status, Priority, Sound, ImageFile):
    global _plugin
    _plugin.onNotification(Name, Subject, Text, Status, Priority, Sound, ImageFile)

def onDisconnect(Connection):
    global _plugin
    _plugin.onDisconnect(Connection)

def onHeartbeat():
    global _plugin
    _plugin.onHeartbeat()

    # Generic helper functions
def DumpConfigToLog():
    for x in Parameters:
        if Parameters[x] != "":
            Domoticz.Debug( "'" + x + "':'" + str(Parameters[x]) + "'")
    Domoticz.Debug("Device count: " + str(len(Devices)))
    for x in Devices:
        Domoticz.Debug("Device:           " + str(x) + " - " + str(Devices[x]))
        Domoticz.Debug("Device ID:       '" + str(Devices[x].ID) + "'")
        Domoticz.Debug("Device Name:     '" + Devices[x].Name + "'")
        Domoticz.Debug("Device nValue:    " + str(Devices[x].nValue))
        Domoticz.Debug("Device sValue:   '" + Devices[x].sValue + "'")
        Domoticz.Debug("Device LastLevel: " + str(Devices[x].LastLevel))
    return

    
def get_or_create_unit(blinds_mac):
    for d in Devices:
        if Devices[d].DeviceID == blinds_mac:
            return d
    new_unit=find_available_unit()
    Domoticz.Device(Name=blinds_mac, Unit=new_unit, DeviceID=blinds_mac, TypeName="Switch", Switchtype=13, Used=1).Create()
    Domoticz.Status("Created device for " + blinds_mac + " with unit " + str(new_unit))
    return new_unit
    
def find_available_unit():
    for num in range(1,200):
        if num not in Devices:
            return num
    return None
    
def rssi_to_signal(rssi):
    #Don't remember where i found this calculation. Kudos to anonymous ;-) 
    #This is actually for wifi, so might not be accurate for 433MHz blinds
    if rssi > -50:
        return 10
    elif rssi < -98:
        return 0
    else:
        return int(((rssi + 97) / 5) + 1)