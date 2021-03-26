"""
<plugin key="MotionShades" name="Motion rolling shades by Coulisse" author="ESCape" version="1.0" externallink="https://github.com/d-EScape/MotionShades-for-Domoticz">
    <description>
        <h2>Motion rolling shades</h2><br/>
        See the current status of shades en control them from Domoticz. Requires a WiFi bridge for the shades and the motionblinds python module from https://github.com/starkillerOG/motion-blinds.
        The module -written by starkillerOG- does all the heavy lifting. This plugin makes it work with Domoticz. It would probably be better to write
        a plugin from scratch and use the plugin systems connector classes. But it is nog that big a deal, since the api is based on polling anyhow.
        <h3>Devices</h3>
        <ul style="list-style-type:square">
            <li>Only supports rolling shades for now. But might also work with comparable device types based on the same hardware.</li>
            <li>Please add different types of curtains and blinds as a pull request on github!</li>
            <li>Motion device types can be identified in the api but are not checked by this plugin yet (it will asume rolling shades).</li>
        </ul>
        <h3>Configuration</h3>
        The plugin needs to communicate to the wifi bridge for the motion (bi-directional) 433MHz controller, using a api key you can find in the official motion app. In the (configured!) app go to settings > about and tap the screen several times. It will show the api-key in a window called "reminder".
    </description>
    <params>
        <param field="Address" label="WiFi bridge IP Address" width="200px"/>
        <param field="Password" label="API key of the bridge" width="200px"/>
    </params>
</plugin>
"""
import Domoticz
#from Domoticz import Devices, Parameters

class BasePlugin:
    enabled = False
    def __init__(self):
        return

    def onStart(self):
        Domoticz.Debug("onStart called")
#        Domoticz.Debugging(1)
        self.unit_fromb_blind={}
        self.allblinds={}
        from motionblinds import MotionGateway
        self.gateway = MotionGateway(ip = Parameters["Address"], key = Parameters["Password"])
        self.gateway.Update()
        for blind in self.gateway.device_list.values():
            blind.Update_from_cache()
            Domoticz.Debug(str(blind))
            Domoticz.Debug("battery_level=" + str(blind.battery_level))
            myunit=get_or_create_unit(blind.mac)
            self.allblinds[myunit]=blind
            self.unit_fromb_blind[blind.mac]=myunit
        Domoticz.Debug("Found: " + str(self.unit_fromb_blind))
        Domoticz.Heartbeat(20)
        
    def onStop(self):
        Domoticz.Debug("onStop called")

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
        self.gateway.Update()
        for blind in self.gateway.device_list.values():
            blind.Update_from_cache()
            Domoticz.Debug("mac=" + str(blind.mac))
            Domoticz.Debug("position=" + str(blind.position))
            Domoticz.Debug("batteryLevel=" + str(blind.battery_level))
            Domoticz.Debug("SignalLevel=" + str(blind.RSSI) + " translates to " + str(rssi_to_signal(blind.RSSI)))
            if blind.position == 100:
                statevalue=1
            elif blind.position > 0:
                statevalue=2
            else:
                statevalue=0
            Devices[self.unit_fromb_blind[blind.mac]].Update(SignalLevel=rssi_to_signal(blind.RSSI), BatteryLevel=int(blind.battery_level), nValue=int(statevalue), sValue=str(blind.position))

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