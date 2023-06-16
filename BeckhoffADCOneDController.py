from tango import DeviceProxy
from sardana.pool.controller import OneDController, Type, Description, DefaultValue
from sardana import State
import time


class BeckhoffADCOneDController(OneDController):
    """
    Controller for 1D trace measurements on Beckhoff/tango DS at PETRAIII/P04.
    """

    MaxDevice = 3

    ctrl_properties = {
        "tango_server": {
            Type: str,
            Description: "The FQDN of the tango Beckhoff device",
            DefaultValue: "domain/family/member",
        },
        "attr_npts": {
            Type: str,
            Description: "tango attribute name to define number of points",
            DefaultValue: "fast.femto1.target_index",
        },
        "attr_start": {
            Type: str,
            Description: "tango attribute name to start measurement",
            DefaultValue: "fast.femto1_start",
        },
        "attr_reset": {
            Type: str,
            Description: "tango attribute name to reset data arrays",
            DefaultValue: "fast.femto1_reset",
        },
        "acq_rate": {
            Type: int,
            Description: "acquisition rate (samples per second) of Beckhoff ADC",
            DefaultValue: 1000,
        },
    }

    axis_attributes = {
        "attr_array": {
            Type: str,
            Description: "attribute name of data array",
            DefaultValue: "fast.femto1.femto_array1",
        },
    }

    def __init__(self, inst, props, *args, **kwargs):
        """Constructor"""
        super(BeckhoffADCOneDController, self).__init__(
            inst, props, *args, **kwargs
        )
        self._log.debug("BeckhoffADCOneDController init")
        self._proxy = DeviceProxy(self.tango_server)
        self._log.debug("Setting Beckhoff filter value to '1' (50 Hz)")
        self._proxy.write_attribute("main.write_filter_elm_ch1.nValue", 1)
        self._proxy.write_attribute("main.write_filter_elm_ch2.nValue", 1)
        self._proxy.write_attribute("main.write_filter_elm_execute", 0)
        self._proxy.write_attribute("main.write_filter_elm_execute", 1)
        self._axes = {}
        self._npts = 1

    def AddDevice(self, axis):
        self._log.debug(f"Adding axis {axis}")
        self._axes[axis] = {}

    def DeleteDevice(self, axis):
        self._log.debug(f"Deleting axis {axis}")
        self._axes.pop(axis)

    def SetAxisExtraPar(self, axis, name, value):
        self._log.debug(f"setting {name} = {value} on axis {axis}")
        name = name.lower()
        if name == "attr_array":
            self._axes[axis]["attr_array"] = value

    def GetAxisExtraPar(self, axis, name):
        name = name.lower()
        if name == "attr_array":
            return self._axes[axis]["attr_array"]

    def GetAxisPar(self, axis, name):
        name = name.lower()
        if name == "shape":
            return (self._npts,)

    def GetCtrlPar(self, par):
        if par == "latency_time":
            return 0.4
        else:
            return super().GetCtrlPar(name)

    def ReadOne(self, axis):
        """Get the specified counter value"""
        self._log.debug("In ReadOne")
        data = self._proxy.read_attribute(self._axes[axis]["attr_array"]).value
        num_valid = (data != 0).sum()
        if num_valid != self._npts:
            self._log.warning(
                "Mismatch between number of points configured and measured "
                f"(measured: {num_valid}, configured: {self._npts})"
            )
        return data[:self._npts]

    def StateAll(self):
        val_start = self._proxy.read_attribute(self.attr_start).value
        self._log.debug(f"StateAll: {val_start}")
        if val_start == 0:
            self.state = State.On
            self.status = "Detector ready"
        elif val_start == 1:
            self.state == State.Moving
            self.status = "Detector acquiring"
        else:
            self.state = State.Fault
            self.status = "Detector in unexpected state"

    def StateOne(self, axis):
        return self.state, self.status

    def LoadOne(self, axis, value, repetitions, latency):
        self._log.debug("In LoadOne")
        """Configure Beckhoff for buffered measurement of given size"""
        npts = int(value * self.acq_rate)
        if npts > 10_000:
            raise ValueError("Maxmimum number of acquisitions is 10000!")
        else:
            self._npts = npts
        return value

    def LoadAll(self):
        self._log.debug("In LoadAll")
        self._proxy.write_attribute(self.attr_reset, 1)
        self._proxy.write_attribute(self.attr_reset, 0)
        self._proxy.write_attribute(self.attr_npts, self._npts)

    def StartOne(self, axis, value):
        pass

    def StartAll(self):
        self._log.debug(f"In StartAll")
        self._proxy.write_attribute(self.attr_start, 0)
        self._proxy.write_attribute(self.attr_start, 1)

    def AbortOne(self, axis):
        self._proxy.write_attribute(self.attr_start, 0)

    # def AbortAll(self):
    #     self._proxy.write_attribute(self.attr_start, 0)

    def StopOne(self, axis):
        self._proxy.write_attribute(self.attr_start, 0)

    def StopAll(self):
        # self._proxy.write_attribute(self.attr_start, 0)
        self._log.debug("In StopAll")
