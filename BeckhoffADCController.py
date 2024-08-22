from tango import DeviceProxy
from sardana.pool.controller import (
    CounterTimerController,
    OneDController,
    Type,
    Description,
    DefaultValue,
    AcqSynch,
)
from sardana import State
import time


class BeckhoffADCCtrlMixin:
    """
    Controller for 1D trace measurements on Beckhoff/tango DS at PETRAIII/P04.
    """

    MaxDevice = 16

    ATTR_NPTS = "ADCBufferSize"
    ATTR_INDEX = "ADC1BufferIndex"
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
    }

    axis_attributes = {
        "ads_symbol_array": {
            Type: str,
            Description: "full ADS symbol name of data array",
            DefaultValue: "MAIN.ADC1.valuebuffer.values",
        },
    }

    def __init__(self, ctrl_class):
        """Constructor"""
        self._ctrl_class = ctrl_class
        self._proxy = DeviceProxy(self.tango_server)
        self._axes = {}
        self.acq_rate = 1000
        self._latency_time = 1 / self.acq_rate

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

    def GetCtrlPar(self, name):
        if name == "latency_time":
                return self._latency_time
        else:
            return super().GetCtrlPar(name)
    
    def SetAxisPar(self, axis, name, value):
        self._ctrl_class.SetAxisPar(self, axis, name, value)
    
    def GetAxisPar(self, axis, name):
        self._ctrl_class.GetAxisPar(self, axis, name)

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

    def LoadOne(self, axis, exposure, repetitions, latency):
        """Configure Beckhoff for buffered measurement of given size"""
        self._log.info(f'LoadOne {axis=} {exposure=} {repetitions=} {latency=}')

        if exposure < (1 / self.acq_rate):
            raise ValueError(f"Minimum exposure time is {1 / self.acq_rate:.3f}!")
        
        self._npts_average = int(exposure * self.acq_rate)
        self._latency_time = max(1 / self.acq_rate, exposure)
        npts = int(self._npts_average * repetitions)
        
        if npts > self.MAXLENGTH:
            raise ValueError(f"Maxmimum number of acquisitions is {self.MAXLENGTH}!")
        self._npts = npts

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


class BeckhoffADCOneDController(BeckhoffADCCtrlMixin, OneDController):

    def __init__(self, inst, props, *args, **kwargs):
        OneDController.__init__(self, inst, props, *args, **kwargs)
        BeckhoffADCCtrlMixin.__init__(self, OneDController)
        self._synchronization = AcqSynch.SoftwareTrigger

    def ReadOne(self, axis):
        """Get the specified counter value"""
        self._log.debug("In ReadOne")
        ads_symbol = self._axes[axis]["ads_symbol_array"]
        if self.state == State.On:
            npts = self._proxy.read_attribute(self.ATTR_INDEX).value
            data = self._proxy.read_float_array([[npts], [ads_symbol]])
            return data

    def GetAxisPar(self, axis, name):
        name = name.lower()
        if name == "shape":
            return (self._npts,)
        elif name == "synchronization":
            return AcqSynch.SoftwareTrigger
        else:
            return BeckhoffADCCtrlMixin.GetAxisPar(self, axis, name)

    def SetAxisPar(self, axis, name, value):
        if name.lower() == "synchronization" and value != AcqSynch.SoftwareTrigger:
            raise ValueError("Only sofware trigger synchronization allowed!")
        BeckhoffADCCtrlMixin.SetAxisPar(self, axis, name, value)


class BeckhoffADCCTController(BeckhoffADCCtrlMixin, CounterTimerController):

    def __init__(self, inst, props, *args, **kwargs):
        CounterTimerController.__init__(self, inst, props, *args, **kwargs)
        BeckhoffADCCtrlMixin.__init__(self, OneDController)
        self._synchronization = AcqSynch.SoftwareStart
    
    def StartOne(self, axis, value):
        self._axes[axis]["samples_returned"] = 0
        BeckhoffADCCtrlMixin.StartOne(self, axis, value)

    def StartAll(self):
        BeckhoffADCCtrlMixin.StartAll(self)
    
    def ReadOne(self, axis):
        self._log.debug("In ReadOne")
        ads_symbol = self._axes[axis]["ads_symbol_array"]
        npts = self._proxy.read_attribute(self.ATTR_INDEX).value
        data = self._proxy.read_float_array([[npts], [ads_symbol]])
        samples_returned = self._axes[axis]["samples_returned"]
        
        full_samples = len(data) // self._npts_average
        n0 = samples_returned * self._npts_average
        n1 = full_samples * self._npts_average
        self._log.debug(f"{data.shape=} {full_samples=} {n0=} {n1=}")
        data = data[n0:n1].reshape((-1, self._npts_average)).mean(axis=1)
        values = data.tolist()
        self._axes[axis]["samples_returned"] = full_samples
        self._log.debug(f"  returning {len(values)} samples")
        return values

    def GetAxisPar(self, axis, name):
        name = name.lower()
        if name == "synchronization":
            return AcqSynch.SoftwareStart
        else:
            return BeckhoffADCCtrlMixin.GetAxisPar(self, axis, name)

    def SetAxisPar(self, axis, name, value):
        if name.lower() == "synchronization" and value != AcqSynch.SoftwareStart:
            raise ValueError("Only software start synchronization allowed!")
        BeckhoffADCCtrlMixin.SetAxisPar(self, axis, name, value)