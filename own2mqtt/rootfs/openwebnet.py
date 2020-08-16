import binascii
import hashlib
import logging
import os
import regex
import socket
import threading

from resettabletimer import ResettableTimer

from own_frame_command import OWNFrameCommand
from own_frame_monitor import OWNFrameMonitor

TYPE_OF_MONITOR = 'MONITOR'
TYPE_OF_COMMAND = 'COMMAND'


class OpenWebNet(threading.Thread):
    def __init__(self, type_of, mqtt_client, options):
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
        self.KEEP_ALIVE = self.ACK
        self.type_of = type_of
        self.mqtt_client = mqtt_client
        self.mqtt_base_topic = options['mqtt_base_topic']
        self.thermo_zones = {}
        for thermo_zone in options['thermo_zones']:
            self.thermo_zones[str(thermo_zone)] = {}
        self.query_interval = options['query_interval']
        self.f520_ids = options['f520_ids']
        self.f522_ids = options['f522_ids']
        self.sock = None
        self.keep_alive_timer = None

    def run(self):
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            logging.info('Starting %s session with %s', self.type_of, self.own_server_address)

            self.sock.connect(self.own_server_address)
            data_received = self.sock.recv(4096)

            if data_received == self.ACK:
                if self.type_of == TYPE_OF_MONITOR:
                    self.sock.send(self.SET_MONITOR)
                elif self.type_of == TYPE_OF_COMMAND:
                    self.sock.send(self.SET_COMMAND)

                data_received = self.sock.recv(4096)

                if data_received == self.AUTH_START:
                    self.sock.send(self.ACK)

                    if self.__authenticate():
                        logging.info('%s started', self.type_of)

                        if self.type_of == TYPE_OF_MONITOR:
                            self.monitor()
                        elif self.type_of == TYPE_OF_COMMAND:
                            self.command()
        except Exception as e:
            self.run()

    def monitor(self):
        # Send command requests
        self.mqtt_client.publish(f'{self.mqtt_base_topic}/command_frame', payload=b'*#1*0##', qos=0, retain=False)

        for thermo_zone in self.thermo_zones.keys():
            self.mqtt_client.publish(f'{self.mqtt_base_topic}/command_frame', payload=('*#4*%s##' % thermo_zone).encode(), qos=0, retain=False)

        self.total_energy_query()
        self.f522_start_power_request()

        # Monitor each frame in socket
        while True:
            frames = self.read_socket()
            for frame in frames:
                OWNFrameMonitor(frame, self)
                self.mqtt_client.publish(f'{self.mqtt_base_topic}/last_frame', payload=frame, qos=0, retain=False)

    def command(self):
        self.keep_alive_timer = ResettableTimer(25.0, self.send_keep_alive)
        self.keep_alive_timer.start()

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
        self.keep_alive_timer.reset()

    def send_keep_alive(self):
        self.write_socket(self.KEEP_ALIVE)
        frames = self.read_socket()
        if len(frames) > 0:
            self.keep_alive_timer.reset()
        else:
            self.run()

    def total_energy_query(self):
        for (f520_id) in self.f520_ids:
            self.mqtt_client.publish(f'{self.mqtt_base_topic}/command_frame', payload=f'*#18*5{f520_id}*51##', qos=0, retain=False)
            self.mqtt_client.publish(f'{self.mqtt_base_topic}/command_frame', payload=f'*#18*5{f520_id}*53##', qos=0, retain=False)
            self.mqtt_client.publish(f'{self.mqtt_base_topic}/command_frame', payload=f'*#18*5{f520_id}*54##', qos=0, retain=False)
        threading.Timer(self.query_interval['total_energy_query'], self.total_energy_query).start()

    def f522_start_power_request(self):
        for (f522_id) in self.f522_ids:
            self.mqtt_client.publish(f'{self.mqtt_base_topic}/command_frame', payload=f'*#18*7{f522_id}#0*#1200#1*1##', qos=0, retain=False)

    def __authenticate(self):
        logging.info('Authenticating...')
        rb_hex = self.__create_rb_hex()
        rb = self.__hex_to_decimal_string(rb_hex)
        ra_search = regex.search(
            r'\*#(\d{128})##', self.sock.recv(4096).decode())
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
        self.sock.send(client_message.encode())

        server_hash = hashlib.new('sha256')
        server_hash.update(ra_hex.encode())
        server_hash.update(rb_hex.encode())
        server_hash.update(kab_hex.encode())
        server_digest = server_hash.hexdigest()
        server_digest_dec = self.__hex_to_decimal_string(server_digest)
        server_message = "*#%s##" % server_digest_dec

        if self.sock.recv(4096) == server_message.encode():
            self.sock.send(self.ACK)
            logging.info('Authenticated')
            return True
        return False

    def read_socket(self):
        try:
            data_received = ''
            while not data_received.endswith('##'):
                data_received = data_received + self.sock.recv(64).decode()
            return regex.findall(r"\*#?[\d\*]*#?0?[\d\*]+#?[\d\*]*##", data_received)
        except ConnectionResetError as e:
            self.run()

    def write_socket(self, content):
        try:
            self.sock.send(self.KEEP_ALIVE)
        except BrokenPipeError as e:
            self.run()

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
