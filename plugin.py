"""
<plugin key="MotionShades" name="Motion rolling shades by Coulisse" author="ESCape" version="2.0" externallink="https://github.com/d-EScape/MotionShades-for-Domoticz">
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
        The status gets updated on every movement of the blinds. The forced update every [configurable] hours ensures that the battery level and signal level get updated even if the blinds never moved.
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
from motionblinds import MotionMulticast, MotionGateway

class BasePlugin:
    enabled = False
    def __init__(self):
        self.updaterrunning=True
        self.timetoupdate=True
        self.updatefailed=False
        self.update_thread = threading.Thread(name="UpdateThread", target=BasePlugin.background_updater, args=(self,))
        return

    def update_domoticz_blinds(self):
        self.countdown=self.interval #reset the poll countdown when new info is received
        for blind in self.gateway.device_list.values():
            Domoticz.Debug("mac=" + str(blind.mac))
            Domoticz.Debug("position=" + str(blind.position))
            Domoticz.Debug("battery level=" + str(blind.battery_level))
            Domoticz.Debug("battery voltage=" + str(blind.battery_voltage))
            Domoticz.Debug("signal level=" + str(blind.RSSI) + " translates to " + str(rssi_to_signal(blind.RSSI)))
            if blind.position == 100:
                statevalue=1
            elif blind.position > 0:
                statevalue=2
            else:
                statevalue=0
            Domoticz.Log("Updating blinds values for:" + str(blind.mac) + " to " + str(blind.position) + "%; battery voltage=" + str(blind.battery_voltage))
            Devices[self.unit_fromb_blind[blind.mac]].Update(SignalLevel=rssi_to_signal(blind.RSSI), BatteryLevel=int(blind.battery_level), nValue=int(statevalue), sValue=str(blind.position))     

    def status_handler(self):
        Domoticz.Debug("status handler called !!")
        self.update_domoticz_blinds()
        
    def background_updater(self):
        #This is run in a separate thread, because a timeout on the bridge could block the plugin for 5 seconds per blind.
        #We don't have to wait for the output, because the real values are send in a multicast massage that is handled by status_handler
        Domoticz.Status("... Background updater thread starting")
        while self.updaterrunning:
            if self.timetoupdate:
                Domoticz.Debug("Forcing blinds status update")
                self.timetoupdate=False
                try:
                    for blind in self.allblinds:
                        self.allblinds[blind].Update()
                except Exception as err:
                    Domoticz.Error("Error updating blind status: "+str(err))
                    self.updatefailed=True
        Domoticz.Status("... Background updater thread stopped!")
        
    def onStart(self):
        if Parameters["Mode6"] != "0":
            Domoticz.Debugging(int(Parameters["Mode6"]))
            DumpConfigToLog()
        Domoticz.Debug("onStart called with debugging on")
        self.unit_fromb_blind={}
        self.allblinds={}
        self.interval=int(Parameters["Mode5"]) * 180 #how many heartbeats does 1 hour take? 20 seconds heartbeat = 3 per minute = 180 per hour
        self.countdown=self.interval #update once when starting
        self.motion_multicast = MotionMulticast()
        self.motion_multicast.Start_listen()
        self.gateway = MotionGateway(ip = Parameters["Address"], key = Parameters["Password"], multicast = self.motion_multicast)
        self.gateway.Update()
        for blind in self.gateway.device_list.values():
#            blind.Update_from_cache()
            Domoticz.Debug(str(blind))
#            Domoticz.Debug("battery_level=" + str(blind.battery_level))
            myunit=get_or_create_unit(blind.mac)
            self.allblinds[myunit]=blind
            self.unit_fromb_blind[blind.mac]=myunit
            Domoticz.Debug("Register handler for " + str(myunit))
            self.allblinds[myunit].Register_callback("1", self.status_handler)
        Domoticz.Debug("Found: " + str(self.unit_fromb_blind))
        self.update_thread.start()
        if Parameters["Mode6"] != "0":
            Domoticz.Error("WARNING: using a faster hearbeat for debugging (20 times normal interval)")
            Domoticz.Heartbeat(1)
        else:
            Domoticz.Heartbeat(20)
        
    def onStop(self):
        Domoticz.Debug("onStop called")
        self.motion_multicast.Stop_listen()
        #wait for the update threads to end (thay can run for up to 5 seconds)
        self.updaterrunning=False
        self.update_thread.join()

    def onConnect(self, Connection, Status, Description):
        Domoticz.Debug("onConnect called")

    def onMessage(self, Connection, Data):
        Domoticz.Debug("onMessage called")

    def onCommand(self, Unit, Command, Level, Hue):
        Domoticz.Debug("onCommand called for Unit " + str(Unit) + ": Parameter '" + str(Command) + "', Level: " + str(Level))
        if Command == "Off":
            self.allblinds[Unit].Open()
        elif Command == "On":
            self.allblinds[Unit].Close()
        elif Command == "Set Level":
            self.allblinds[Unit].Set_position(Level)
            

    def onNotification(self, Name, Subject, Text, Status, Priority, Sound, ImageFile):
        Domoticz.Debug("Notification: " + Name + "," + Subject + "," + Text + "," + Status + "," + str(Priority) + "," + Sound + "," + ImageFile)

    def onDisconnect(self, Connection):
        Domoticz.Debug("onDisconnect called")

    def onHeartbeat(self):
        Domoticz.Debug("onHeartbeat called")
        Domoticz.Debug("Update Thread:" + str(self.update_thread))
        Domoticz.Debug(str(self.countdown) + " heartbeats until next update")
        #Request an update from the blinds every once in a while, to get the battery and signal strength, even if they have not been moved. 
        if self.countdown==0:
            Domoticz.Debug("Request full update")
            self.timetoupdate=True
        else:
            self.countdown=self.countdown-1

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