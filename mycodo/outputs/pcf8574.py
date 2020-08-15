# coding=utf-8
#
# pcf8574.py - Output for PCF8574
#
import os

from flask_babel import lazy_gettext

from mycodo.outputs.base_output import AbstractOutput

# Measurements
measurements_dict = {
    0: {
        'measurement': 'duration_time',
        'unit': 's'
    }
}

# Output information
OUTPUT_INFORMATION = {
    'output_name_unique': 'pcf8574',
    'output_name': 'PCF8574 (8-channel)',
    'measurements_dict': measurements_dict,
    'output_types': ['on_off'],

    'message': 'Switch 8 channels on the PCF8574.',

    'options_enabled': [
        'i2c_location',
        'on_off_state_on',
        'on_off_state_startup',
        'on_off_state_shutdown',
        'trigger_functions_startup',
        'current_draw',
        'button_on',
        'button_send_duration'
    ],
    'options_disabled': ['interface'],

    'interfaces': ['I2C'],
    'i2c_location': [
        '0x20', '0x21', '0x22', '0x23', '0x24', '0x25', '0x26', '0x27',
        '0x38', '0x39', '0x3a', '0x3b', '0x3c', '0x3d', '0x3e', '0x3f'
    ],
    'i2c_address_editable': False,
    'i2c_address_default': '0x20',

    'custom_options': [
        {
            'id': 'channel',
            'type': 'select',
            'default_value': '1',
            'options_select': [
                ('1', 'Channel 1'),
                ('2', 'Channel 2'),
                ('3', 'Channel 3'),
                ('4', 'Channel 4'),
                ('5', 'Channel 5'),
                ('6', 'Channel 6'),
                ('7', 'Channel 7'),
                ('8', 'Channel 8')
            ],
            'name': lazy_gettext('Channel'),
            'phrase': lazy_gettext('Select the channel to control')
        }
    ]
}


class OutputModule(AbstractOutput):
    """
    An output support class that operates an output
    """
    def __init__(self, output, testing=False):
        super(OutputModule, self).__init__(output, testing=testing, name=__name__)

        self.sensor = None
        self.output_state = None
        self.output_on_state = None
        self.state_startup = None
        self.state_shutdown = None
        self.lock_file = None
        self.state_file = None

        self.channel = None
        self.setup_custom_options(OUTPUT_INFORMATION['custom_options'], output)

    def setup_output(self):
        import smbus2

        self.setup_on_off_output(OUTPUT_INFORMATION)
        self.output_on_state = self.output.on_state
        self.state_startup = self.output.state_startup
        self.state_shutdown = self.output.state_shutdown
        self.channel = int(self.channel)

        if self.output.i2c_location:
            self.lock_file = '/var/lock/pcf8574_{}_{}'.format(
                self.output.i2c_bus, self.output.i2c_location)
            self.state_file = '{}.states'.format(self.lock_file)
            self.sensor = PCF8574(
                smbus2, self.output.i2c_bus, int(str(self.output.i2c_location), 16))
            self.output_setup = True

        if self.state_startup == '1':
            self.output_switch('on')
        elif self.state_startup == '0':
            self.output_switch('off')

    def output_switch(self,
                      state,
                      output_type=None,
                      amount=None,
                      duty_cycle=None,
                      output_channel=None):
        if self.channel is None:
            self.logger.error("Output channel needs to be specified")
            return

        try:
            # Lock device
            if self.lock_acquire(self.lock_file, timeout=60):
                try:
                    # Get current states of device
                    list_states = []
                    # open file of states and read it, populate list of states

                    # open file and read the content in a list
                    if os.path.exists(self.state_file):
                        with open(self.state_file, 'r') as f:
                            for line in f:
                                read_state = line[:-1]
                                if read_state == "None":
                                    list_states.append(None)
                                elif read_state == "True":
                                    list_states.append(True)
                                elif read_state == "False":
                                    list_states.append(False)
                    else:
                        list_states = [None for _ in range(8)]

                    self.logger.debug("Read states: {}: {}".format(self.state_file, list_states))

                    # Check states were read
                    if len(list_states) != 8:
                        self.logger.error("State list does ot contain 8 elements")
                        return

                    if state == 'on':
                        self.output_state = self.output_on_state
                    elif state == 'off':
                        self.output_state = not self.output_on_state
                    else:
                        self.logger.error("Unrecognized state: {}".format(state))
                        return

                    # only manipulate single channel in list
                    list_states[self.channel - 1] = self.output_state

                    self.logger.debug("Write states: {}: {}".format(self.state_file, list_states))

                    # Write list to file
                    with open(self.state_file, 'w') as f:
                        for write_state in list_states:
                            f.write('{}\n'.format(write_state))

                    # Send array of states to device to only switch a single channel
                    self.sensor.port = list_states
                finally:
                    self.lock_release(self.lock_file)
        except Exception as e:
            self.logger.error("State change error: {}".format(e))

    def is_on(self, output_channel=None):
        if self.is_setup():
            return self.output_state

    def is_setup(self):
        return self.output_setup

    def stop_output(self):
        """ Called when Output is stopped """
        if self.state_shutdown == '1':
            self.output_switch('on')
        elif self.state_shutdown == '0':
            self.output_switch('off')
        self.running = False


class IOPort(list):
    """ Represents the PCF8574 IO port as a list of boolean values """

    def __init__(self, pcf8574, *args, **kwargs):
        super(IOPort, self).__init__(*args, **kwargs)
        self.pcf8574 = pcf8574

    def __setitem__(self, key, value):
        """ Set an individual output pin """
        self.pcf8574.set_output(key, value)

    def __repr__(self):
        """ Represent port as a list of booleans """
        state = self.pcf8574.bus.read_byte(self.pcf8574.address)
        ret = []
        for i in range(8):
            ret.append(bool(state & 1 << 7 - i))
        return repr(ret)

    def __len__(self):
        return 8

    def __iter__(self):
        for i in range(8):
            yield self[i]

    def __reversed__(self):
        for i in range(8):
            yield self[7 - i]


class PCF8574(object):
    """ A software representation of a single PCF8574 IO expander chip """

    def __init__(self, smbus, i2c_bus, i2c_address):
        self.bus_no = i2c_bus
        self.bus = smbus.SMBus(i2c_bus)
        self.address = i2c_address

    def __repr__(self):
        return "PCF8574(i2c_bus_no=%r, address=0x%02x)" % (self.bus_no, self.address)

    @property
    def port(self):
        """ Represent IO port as a list of boolean values """
        return IOPort(self)

    @port.setter
    def port(self, value):
        """ Set the whole port using a list """
        assert isinstance(value, list)
        assert len(value) == 8
        new_state = 0
        for i, val in enumerate(value):
            if val:
                new_state |= 1 << 7 - i
        self.bus.write_byte(self.address, new_state)

    def set_output(self, output_number, value):
        """ Set a specific output high (True) or low (False) """
        assert output_number in range(8), "Output number must be an integer between 0 and 7"
        current_state = self.bus.read_byte(self.address)
        bit = 1 << 7 - output_number
        new_state = current_state | bit if value else current_state & (~bit & 0xff)
        self.bus.write_byte(self.address, new_state)
