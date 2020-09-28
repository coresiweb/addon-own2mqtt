import binascii
import hashlib
import logging
import os
import regex
import socket
import threading
import paho.mqtt.client as mqtt

from resettabletimer import ResettableTimer

from own_frame_command import OWNFrameCommand
from own_frame_monitor import OWNFrameMonitor

TYPE_OF_MONITOR = 'MONITOR'
TYPE_OF_COMMAND = 'COMMAND'


class OpenWebNet:
    def __init__(self, options):
        threading.Thread.__init__(self)
        self.own_server_address = (options['own_server_ip'], options['own_server_port'])
        self.own_password = options['own_server_password']
        self.ACK = b'*#*1##'
        self.NACK = b'*#*0##'
        self.A_HEX = '736F70653E'
        self.B_HEX = '636F70653E'
        self.AUTH_START = b'*98*2##'
        self.SET_COMMAND = b'*99*0##'
        self.SET_MONITOR = b'*99*1##'
        self.KEEP_ALIVE = b'*#13**22##'

        self.mqtt_client = mqtt.Client(options['mqtt_client_name'])
        self.mqtt_client.username_pw_set(options['mqtt_server_user'], options['mqtt_server_password'])
        self.mqtt_client.connect(options['mqtt_server_ip'], options['mqtt_server_port'])
        self.mqtt_base_topic = options['mqtt_base_topic']

        self.thermo_zones = {}
        for thermo_zone in options['thermo_zones']:
            self.thermo_zones[str(thermo_zone)] = {}
        self.query_interval = options['query_interval']
        self.f520_ids = options['f520_ids']
        self.f522_ids = options['f522_ids']
        self.debug = options['debug']

        self.command_thread = self.monitor_thread = None
        self.command_socket = self.monitor_socket = None

        self.command_timer = ResettableTimer(25.0, self.command_keep_alive)
        self.monitor_timer = ResettableTimer(25.0, self.monitor_start)

    def run(self):

        self.command_thread = threading.Thread(target=self.command_start)
        self.command_thread.start()

        self.monitor_thread = threading.Thread(target=self.monitor_start)
        self.monitor_thread.start()

    def monitor_start(self):
        logging.info('Starting MONITOR session with %s', self.own_server_address)
        self.monitor_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.monitor_socket.connect(self.own_server_address)
        data_received = self.monitor_socket.recv(4096)

        if data_received == self.ACK:
            self.monitor_socket.send(self.SET_MONITOR)

            data_received = self.monitor_socket.recv(4096)

            if data_received == self.AUTH_START:
                self.monitor_socket.send(self.ACK)

                if self.__authenticate(self.monitor_socket):
                    logging.info('MONITOR started')
                    # If no frame received restart the monitor
                    self.monitor_timer.start()

                    # Send command requests
                    self.mqtt_client.publish(f'{self.mqtt_base_topic}/command_frame', payload=b'*#1*0##', qos=1, retain=False)

                    for thermo_zone in self.thermo_zones.keys():
                        self.mqtt_client.publish(f'{self.mqtt_base_topic}/command_frame', payload=('*#4*%s##' % thermo_zone).encode(), qos=1, retain=False)

                    self.total_energy_query()
                    self.f522_start_power_request()

                    # Monitor each frame in socket
                    while True:
                        frames = self.read_socket(self.monitor_socket)
                        for frame in frames:
                            self.monitor_timer.reset()
                            OWNFrameMonitor(frame, self)
                            self.mqtt_client.publish(f'{self.mqtt_base_topic}/last_frame', payload=frame, qos=0, retain=False)

    def command_start(self):
        logging.info('Starting COMMAND session with %s', self.own_server_address)

        self.command_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.command_socket.connect(self.own_server_address)
        data_received = self.command_socket.recv(4096)

        if data_received == self.ACK:
            self.command_socket.send(self.SET_COMMAND)

            data_received = self.command_socket.recv(4096)

            if data_received == self.AUTH_START:
                self.command_socket.send(self.ACK)

                if self.__authenticate(self.command_socket):
                    logging.info('COMMAND started')
                    self.command_timer.start()

                    topics = [
                        (f'{self.mqtt_base_topic}/command_frame', 0),
                        (f'{self.mqtt_base_topic}/who-1/+/command', 0),
                        (f'{self.mqtt_base_topic}/who-2/+/command', 0),
                        (f'{self.mqtt_base_topic}/who-2/+/set_position', 0),
                        (f'{self.mqtt_base_topic}/who-4/zones/+/mode/set', 0),
                        (f'{self.mqtt_base_topic}/who-4/zones/+/temperature/set', 0),
                    ]
                    self.mqtt_client.on_message = self.on_message
                    self.mqtt_client.subscribe(topics)
                    self.mqtt_client.loop_forever()

    def on_message(self, client, userdata, message):
        logging.debug('MQTT: TOPIC: %s | PAYLOAD: %s', message.topic, message.payload)
        OWNFrameCommand(self, message.topic, message.payload)

    def command_keep_alive(self):
        try:
            logging.debug('KA')
            self.command_socket.send(self.KEEP_ALIVE)
            frames = self.read_socket(self.command_socket)
            if len(frames) > 0:
                self.command_timer.reset()
            else:
                self.command_start()
        except BrokenPipeError:
            self.command_start()

    def total_energy_query(self):
        for (f520_id) in self.f520_ids:
            self.mqtt_client.publish(f'{self.mqtt_base_topic}/command_frame', payload=f'*#18*5{f520_id}*51##', qos=1, retain=False)
            self.mqtt_client.publish(f'{self.mqtt_base_topic}/command_frame', payload=f'*#18*5{f520_id}*53##', qos=1, retain=False)
            self.mqtt_client.publish(f'{self.mqtt_base_topic}/command_frame', payload=f'*#18*5{f520_id}*54##', qos=1, retain=False)
        threading.Timer(self.query_interval['total_energy_query'], self.total_energy_query).start()

    def f522_start_power_request(self):
        for (f522_id) in self.f522_ids:
            self.mqtt_client.publish(f'{self.mqtt_base_topic}/command_frame', payload=f'*#18*7{f522_id}#0*#1200#1*1##', qos=1, retain=False)

    def __authenticate(self, current_socket):
        logging.info('Authenticating...')
        rb_hex = self.__create_rb_hex()
        rb = self.__hex_to_decimal_string(rb_hex)
        ra_search = regex.search(
            r'\*#(\d{128})##', current_socket.recv(4096).decode())
        if not ra_search:
            return False
        ra_hex = self.__decimal_string_to_hex(ra_search.group(1))
        kab_hex = hashlib.sha256(self.own_password.encode()).hexdigest()

        client_hash = hashlib.new('sha256')
        client_hash.update(ra_hex.encode())
        client_hash.update(rb_hex.encode())
        client_hash.update(self.A_HEX.encode())
        client_hash.update(self.B_HEX.encode())
        client_hash.update(kab_hex.encode())
        client_digest = client_hash.hexdigest()
        client_digest_dec = self.__hex_to_decimal_string(client_digest)

        client_message = "*#%s*%s##" % (rb, client_digest_dec)
        current_socket.send(client_message.encode())

        server_hash = hashlib.new('sha256')
        server_hash.update(ra_hex.encode())
        server_hash.update(rb_hex.encode())
        server_hash.update(kab_hex.encode())
        server_digest = server_hash.hexdigest()
        server_digest_dec = self.__hex_to_decimal_string(server_digest)
        server_message = "*#%s##" % server_digest_dec

        if current_socket.recv(4096) == server_message.encode():
            current_socket.send(self.ACK)
            logging.info('Authenticated')
            return True
        return False

    @staticmethod
    def read_socket(current_socket):
        data_received = ''
        while not data_received.endswith('##'):
            data_received = data_received + current_socket.recv(64).decode()
        return regex.findall(r"\*#?[\d\*]*#?0?[\d\*]+#?[\d\*]*##", data_received)

    @staticmethod
    def __create_rb_hex():
        return binascii.hexlify(os.urandom(32)).decode()

    @staticmethod
    def __decimal_string_to_hex(s):
        hex_string = ''
        for (subchars) in regex.findall('..', s):
            hex_string += hex(int(subchars))[2:]
        return hex_string

    @staticmethod
    def __hex_to_decimal_string(h):
        dec_string = ''
        for (subchars) in regex.findall('.', h):
            dec_string += '{0:02d}'.format(int(subchars, 16))
        return dec_string
