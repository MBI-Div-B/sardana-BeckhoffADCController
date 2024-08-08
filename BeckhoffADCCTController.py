from tango import DeviceProxy
from sardana.pool.controller import (
    OneDController,
    Type,
    Description,
    DefaultValue,
)
from sardana import State
import time


class BeckhoffADCOneDController(OneDController):
    """
    Controller for 1D trace measurements on Beckhoff/tango DS at PETRAIII/P04.
    """

    MaxDevice = 16

    ATTR_NPTS = "ADCBufferSize"
    ATTR_PREPARE = "ADCPrepare"
    ATTR_START = "ADCStart"
    ATTR_STOP = "ADCStop"
    ATTR_STATE = "ADC1BufferState"
    MAXLENGTH = 100_000

    ctrl_properties = {
        "tango_server": {
            Type: str,
            Description: "The FQDN of the tango Beckhoff device",
            DefaultValue: "domain/family/member",
        },
        "attr_rate": {
            Type: str,
            Description: "tango attribute name to set acquisition rate (Hz)",
            DefaultValue: "fast.femto1_rate",
        },
    }

    axis_attributes = {
        "ads_symbol_array": {
            Type: str,
            Description: "full ADS symbol name of data array",
            DefaultValue: "MAIN.ADC1.valuebuffer.values",
        },
    }

    def __init__(self, inst, props, *args, **kwargs):
        """Constructor"""
        super().__init__(inst, props, *args, **kwargs)
        self._log.info("BeckhoffADCCTController init")
        self._proxy = DeviceProxy(self.tango_server)
        self._axes = {}
        self.acq_rate = 1000
        self._npts = self._proxy.read_attribute(self.ATTR_NPTS).value

    def AddDevice(self, axis):
        self._log.debug(f"Adding axis {axis}")
        self._axes[axis] = {}

    def DeleteDevice(self, axis):
        self._log.debug(f"Deleting axis {axis}")
        self._axes.pop(axis)

    def SetAxisExtraPar(self, axis, name, value):
        self._log.debug(f"setting {name} = {value} on axis {axis}")
        name = name.lower()
        if name == "ads_symbol_array":
            self._axes[axis]["ads_symbol_array"] = value

    def GetAxisExtraPar(self, axis, name):
        name = name.lower()
        if name == "ads_symbol_array":
            return self._axes[axis]["ads_symbol_array"]

    def GetAxisPar(self, axis, name):
        name = name.lower()
        if name == "shape":
            return (self._npts,)
        else:
            return super().GetAxisPar(name)

    def GetCtrlPar(self, name):
        if name == "latency_time":
                return 0.1
        else:
            return super().GetCtrlPar(name)

    def ReadOne(self, axis):
        """Get the specified counter value"""
        self._log.debug("In ReadOne")
        data = self._proxy.read_float_array([[self._npts], [self._axes[axis]["ads_symbol_array"]]])
        return data

    def StateAll(self):
        state = self._proxy.read_attribute(self.ATTR_STATE).value
        self._log.debug(f"StateAll: {state=}")
        if state in [1, 3]:
            self.state = State.On
            self.status = "Detector ready"
        elif state == 2:
            self.state = State.Moving
            self.status = "Detector acquiring"
        else:
            self.state = State.Fault
            self.status = f"Unxepected state: {state}"

    def StateOne(self, axis):
        return self.state, self.status

    def LoadOne(self, axis, value, repetitions, latency):
        self._log.debug("In LoadOne")
        """Configure Beckhoff for buffered measurement of given size"""
        npts = int(value * self.acq_rate)
        if npts > self.MAXLENGTH:
            raise ValueError(f"Maxmimum number of acquisitions is {self.MAXLENGTH}!")
        else:
            self._npts = npts
        return value

    def LoadAll(self):
        self._log.debug("In LoadAll")
        self._proxy.write_attribute(self.ATTR_NPTS, self._npts)
        self._proxy.write_attribute(self.ATTR_PREPARE, True)

    def StartOne(self, axis, value):
        pass

    def StartAll(self):
        self._log.debug(f"In StartAll")
        self._proxy.write_attribute(self.ATTR_START, True)

    def AbortOne(self, axis):
        self._proxy.write_attribute(self.ATTR_STOP, True)

    def StopOne(self, axis):
        self._proxy.write_attribute(self.ATTR_STOP, True)

    def StopAll(self):
        # self._proxy.write_attribute(self.attr_start, 0)
        self._log.debug("In StopAll")
