import os
import sys
import re
import brave.exceptions
from brave.helpers import get_logger
from gi.repository import Gst, GObject
from brave.inputs import InputCollection
from brave.outputs import OutputCollection
from brave.overlays import OverlayCollection
from brave.mixers import MixerCollection
from brave.connections import ConnectionCollection
import brave.config as config
assert Gst.VERSION_MINOR > 13, f'GStreamer is version 1.{Gst.VERSION_MINOR}, must be 1.14 or higher'
PERIODIC_MESSAGE_FREQUENCY = 60
singleton = None


class Session(object):
    '''
    Class to provide the 'session' which allows live AV manipulation.
    '''

    def __init__(self):
        self.logger = get_logger('session')
        self.items_recently_updated = []
        self.items_recently_deleted = []

        self.inputs = InputCollection(self)
        self.outputs = OutputCollection(self)
        self.overlays = OverlayCollection(self)
        self.mixers = MixerCollection(self)
        self.connections = ConnectionCollection(self)

    def start(self):
        self._setup_initial_inputs_outputs_mixers_and_overlays()
        self.mainloop = GObject.MainLoop()
        GObject.timeout_add(PERIODIC_MESSAGE_FREQUENCY * 1000, self.periodic_message)
        self.mainloop.run()
        self.logger.debug('Mainloop has ended')

    def end(self, restart=False):
        '''
        Called when the user has requested the service to end.
        '''
        for name, input in self.inputs.items():
            input.set_state(Gst.State.NULL)
        for name, output in self.outputs.items():
            output.set_state(Gst.State.NULL)
        for name, mixer in self.mixers.items():
            mixer.set_state(Gst.State.NULL)
        if hasattr(self, 'mainloop'):
            self.mainloop.quit()
        if restart:
            os.execl(sys.executable, sys.executable, *sys.argv)

    def _setup_initial_inputs_outputs_mixers_and_overlays(self):
        '''
        Create the inputs/outputs/mixers/overlays declared in the config file.
        '''
        for mixer_config in config.default_mixers():
            self.mixers.add(**mixer_config)

        for input_config in config.default_inputs():
            input = self.inputs.add(**input_config)
            input.setup()

        for output_config in config.default_outputs():
            self.outputs.add(**output_config)

        for id, mixer in self.mixers.items():
            mixer.setup_initial_sources()

        if config.enable_video():
            for overlay_config in config.default_overlays():
                self.overlays.add(**overlay_config)

        for name, mixer in self.mixers.items():
            mixer.set_state(Gst.State.PLAYING)

    def print_state_summary(self):
        '''
        Prints the state of all elements to STDOUT.
        '''
        self.inputs.print_state_summary()
        self.outputs.print_state_summary()
        self.overlays.print_state_summary()
        self.mixers.print_state_summary()

    def periodic_message(self):
        self.print_state_summary()
        self.logger.debug('...state will print out every %d seconds...' % PERIODIC_MESSAGE_FREQUENCY)
        GObject.timeout_add(PERIODIC_MESSAGE_FREQUENCY * 1000, self.periodic_message)

    def uid_to_block(self, uid, error_if_not_exists=False):
        '''
        Given a UID (e.g. 'input2') returns the instance of the relevant block.
        '''
        match = re.search(r'^(input|mixer|output)(\d+)$', uid) if isinstance(uid, str) else None
        if not match:
            raise brave.exceptions.InvalidConfiguration(
                'Invalid uid "%s", it must be input/mixer/output then a number' % uid)

        type, id = match.group(1), int(match.group(2))
        block = self.get_block_by_type(type, id)
        if error_if_not_exists and not block:
            raise brave.exceptions.InvalidConfiguration('"%s" does not exist' % uid)
        return block

    def get_block_by_type(self, type, id):
        '''
        Given the block type as a string (input/mixer/output/overlay) and an ID (integer) returns the block instance.
        '''
        if type == 'input':
            collection = self.inputs
        elif type == 'mixer':
            collection = self.mixers
        elif type == 'output':
            collection = self.outputs
        elif type == 'overlay':
            collection = self.overlays
        else:
            raise ValueError('Invalid block type "%s"' % type)

        return collection[id] if id in collection else None

    def report_deleted_item(self, item):
        self.items_recently_deleted.append({'id': item.id, 'block_type': item.input_output_overlay_or_mixer()})


def init():
    Gst.init(None)
    global singleton
    singleton = Session()
    return singleton


def get_session():
    global singleton
    return singleton
