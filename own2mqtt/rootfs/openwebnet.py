import binascii
import hashlib
import logging
import os
import time

import regex
import socket
import threading
import paho.mqtt.client as mqtt

from own_frame_command import OWNFrameCommand
from own_frame_monitor import OWNFrameMonitor


class OpenWebNet:
    def __init__(self, options):
        self.logger = logging.getLogger("own2mqtt")

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

        self.mqtt_client = None
        self.mqtt_server_ip = options['mqtt_server_ip']
        self.mqtt_server_port = options['mqtt_server_port']
        self.mqtt_client_name = options['mqtt_client_name']
        self.mqtt_server_user = options['mqtt_server_user']
        self.mqtt_server_password = options['mqtt_server_password']
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

        self.mqtt_ready = self.monitor_ready = self.command_ready = False

    def run(self):
        try:
            self.logger.info('Connecting to MQTT Server %s:%s', self.mqtt_server_ip, self.mqtt_server_port)
            self.mqtt_client = mqtt.Client(self.mqtt_client_name, True, {'base_topic': self.mqtt_base_topic, 'own_instance': self})
            self.mqtt_client.username_pw_set(self.mqtt_server_user, self.mqtt_server_password)
            self.mqtt_client.on_connect = self.on_mqtt_connect
            self.mqtt_client.on_disconnect = self.on_mqtt_disconnect
            self.mqtt_client.on_message = self.on_mqtt_message
            self.mqtt_client.connect(self.mqtt_server_ip, self.mqtt_server_port)
            self.mqtt_client.loop_start()

            self.monitor_thread = threading.Thread(target=self.monitor_start)
            self.monitor_thread.start()

            while not (self.mqtt_ready and self.monitor_ready and self.command_ready):
                self.command_start()

            # self.monitor_thread.join()
            # self.command_thread.join()

        except (KeyboardInterrupt, SystemExit):
            self.mqtt_client.loop_stop()
            self.mqtt_client.disconnect()
            self.monitor_socket.close()
            self.monitor_ready = False
            self.command_socket.close()

    def monitor_start(self):
        logger = logging.getLogger("own2mqtt.monitor")
        while True:
            if self.mqtt_ready:
                self.monitor_ready = False
                try:
                    self.logger.info('Starting MONITOR session with %s', self.own_server_address)

                    self.monitor_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    self.monitor_socket.connect(self.own_server_address)
                    data_received = self.monitor_socket.recv(4096)

                    if data_received == self.ACK:
                        self.monitor_socket.send(self.SET_MONITOR)

                        data_received = self.monitor_socket.recv(4096)

                        if data_received == self.AUTH_START:
                            self.monitor_socket.send(self.ACK)

                            if self.__authenticate(self.monitor_socket):
                                last_frame = time.time()
                                self.logger.info('MONITOR started')
                                self.monitor_ready = True

                                # Monitor each frame in socket
                                while self.monitor_ready and (time.time() - last_frame) < 30:
                                    frames = self.read_monitor_socket()
                                    for frame in frames:
                                        last_frame = time.time()
                                        OWNFrameMonitor(frame, self)
                                        self.mqtt_client.publish(f'{self.mqtt_base_topic}/last_frame', payload=frame, qos=0, retain=False)
                                else:
                                    self.monitor_ready = False
                                    self.logger.info('MONITOR Disconnected')
                except Exception as e:
                    self.logger.info(e)
                    if self.debug:
                        if self.monitor_socket:
                            self.monitor_socket.close()
                            self.monitor_socket = None
                        raise e
                    time.sleep(5)

    def command_connect(self):
        self.logger.info('Starting COMMAND session with %s', self.own_server_address)

        self.command_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.command_socket.connect(self.own_server_address)
        data_received = self.command_socket.recv(4096)

        if data_received == self.ACK:
            self.command_socket.send(self.SET_COMMAND)

            data_received = self.command_socket.recv(4096)

            if data_received == self.AUTH_START:
                self.command_socket.send(self.ACK)

                if self.__authenticate(self.command_socket):
                    self.logger.info('COMMAND started')
                    self.command_ready = True

    def command_start(self):
        self.command_connect()

        # Send command requests
        self.write_socket(b'*#1*0##')

        for thermo_zone in self.thermo_zones.keys():
            self.write_socket(('*#4*%s##' % thermo_zone).encode())
            self.write_socket(('*#4*%s*60##' % thermo_zone).encode())

        self.total_energy_query()
        self.f522_start_power_request()

        frames = self.read_command_socket()
        self.logger.info(frames)
        if len(frames) > 0:
            last_frame = time.time()
        else:
            self.logger.info('COMMAND Disconnected')

    def write_socket(self, encoded_frame):
        while True:
            try:
                self.command_socket.send(encoded_frame)
                self.logger.debug('TX: %s' % encoded_frame.decode())
                break
            except (BrokenPipeError, IOError) as e:
                self.command_socket.close()
                self.command_socket = None
                self.command_ready = False
                self.command_connect()
                self.write_socket(encoded_frame)

    def f522_start_power_request(self):
        for (f522_id) in self.f522_ids:
            self.write_socket(f'*#18*7{f522_id}#0*#1200#1*1##'.encode())

    def total_energy_query(self):
        for (f520_id) in self.f520_ids:
            self.write_socket(f'*#18*5{f520_id}*51##'.encode())
            self.write_socket(f'*#18*5{f520_id}*53##'.encode())
            self.write_socket(f'*#18*5{f520_id}*54##'.encode())
        threading.Timer(self.query_interval['total_energy_query'], self.total_energy_query).start()

    def read_command_socket(self):
        return self.__read_socket(self.command_socket)

    def read_monitor_socket(self):
        return self.__read_socket(self.monitor_socket)

    def __authenticate(self, current_socket):
        self.logger.info('Authenticating...')
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
            self.logger.info('Authenticated')
            return True
        return False

    @staticmethod
    def on_mqtt_connect(client, userdata, flags, rc):
        logger = logging.getLogger("own2mqtt")
        logger.info('Connected to MQTT')
        userdata['own_instance'].mqtt_ready = True

        topics = [
            (f'{userdata["base_topic"]}/command_frame', 0),
            (f'{userdata["base_topic"]}/who-1/+/command', 0),
            (f'{userdata["base_topic"]}/who-2/+/command', 0),
            (f'{userdata["base_topic"]}/who-2/+/set_position', 0),
            (f'{userdata["base_topic"]}/who-4/zones/+/mode/set', 0),
            (f'{userdata["base_topic"]}/who-4/zones/+/temperature/set', 0),
        ]
        client.subscribe(topics)

    @staticmethod
    def on_mqtt_disconnect(client, userdata, rc):
        logger = logging.getLogger("own2mqtt")
        logger.info('MQTT Disconnected')
        userdata['own_instance'].mqtt_ready = False

    @staticmethod
    def on_mqtt_message(client, userdata, message):
        logger = logging.getLogger("own2mqtt")
        logger.debug('MQTT: TOPIC: %s | PAYLOAD: %s', message.topic, message.payload)
        OWNFrameCommand(userdata['own_instance'], message.topic, message.payload)

    @staticmethod
    def __read_socket(current_socket):
        data_received = ''
        while not data_received.endswith('##'):
            data_received = data_received + current_socket.recv(1).decode()
        return regex.findall(r"\*#?[\d\*]*#?0?[\d\*]+#?[\d\*]*##", data_received)

    @staticmethod
    def __create_rb_hex():
        return binascii.hexlify(os.urandom(32)).decode()

    @staticmethod
    def __decimal_string_to_hex(s):
        hex_string = ''
        for (chars) in regex.findall('..', s):
            hex_string += hex(int(chars))[2:]
        return hex_string

    @staticmethod
    def __hex_to_decimal_string(h):
        dec_string = ''
        for (chars) in regex.findall('.', h):
            dec_string += '{0:02d}'.format(int(chars, 16))
        return dec_string
