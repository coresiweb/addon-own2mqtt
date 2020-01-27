import socket
import hashlib
import regex
import os
import binascii
import logging
import paho.mqtt.client as mqtt
from own_frame_monitor import OWNFrameMonitor

ACK = b'*#*1##'
NACK = b'*#*0##'
A_HEX = '736F70653E'
B_HEX = '636F70653E'


class OWNMonitor:
    def __init__(self, options):
        self.own_server_address = (options['own_server_ip'], options['own_server_port'])
        self.own_password = options['own_server_password']
        self.mqtt_server_ip = options['mqtt_server_ip']
        self.mqtt_server_port = options['mqtt_server_port']
        self.mqtt_server_user = options['mqtt_server_user']
        self.mqtt_server_password = options['mqtt_server_password']

    def startSession(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        logging.info('Starting MONITOR session with %s', self.own_server_address)

        self.sock.connect(self.own_server_address)

        data_received = self.sock.recv(4096)
        logging.debug('RX: %s', data_received)

        if data_received == ACK:
            data_sent = b'*99*1##'
            self.sock.send(data_sent)
            logging.debug('TX: %s', data_sent)

            data_received = self.sock.recv(4096)
            logging.debug('RX: %s', data_received)

            if data_received == b'*98*2##':
                self.sock.send(ACK)
                logging.debug('TX: %s', ACK)

                self.__authenticate()

                logging.info('Connecting to MQTT Server %s:%s', self.mqtt_server_ip, self.mqtt_server_port)

                mqtt_client = mqtt.Client()
                mqtt_client.username_pw_set(self.mqtt_server_user, self.mqtt_server_password)
                mqtt_client.connect(self.mqtt_server_ip, self.mqtt_server_port)

                logging.info('Monitoring...')
                while True:
                    data_received = self.sock.recv(4096).decode()
                    if data_received == b'':
                        return
                    else:
                        frame = OWNFrameMonitor(data_received, mqtt_client)
                        mqtt_client.publish('openwebnet/last_frame', payload=frame.frame, qos=0, retain=False)

    def __authenticate(self):
        logging.info('Authenticating...')
        rb_hex = self.__createRbHex()
        rb = self.__hexToDecimalString(rb_hex)
        ra_search = regex.search(r'\*#(\d{128})##', self.sock.recv(4096).decode())
        if not ra_search:
            return
        ra_hex = self.__decimalStringToHex(ra_search.group(1))
        kab_hex = hashlib.sha256(self.own_password.encode()).hexdigest()

        client_hash = hashlib.new('sha256')
        client_hash.update(ra_hex.encode())
        client_hash.update(rb_hex.encode())
        client_hash.update(A_HEX.encode())
        client_hash.update(B_HEX.encode())
        client_hash.update(kab_hex.encode())
        client_digest = client_hash.hexdigest()
        client_digest_dec = self.__hexToDecimalString(client_digest)

        client_message = "*#%s*%s##" % (rb, client_digest_dec)
        self.sock.send(client_message.encode())

        server_hash = hashlib.new('sha256')
        server_hash.update(ra_hex.encode())
        server_hash.update(rb_hex.encode())
        server_hash.update(kab_hex.encode())
        server_digest = server_hash.hexdigest()
        server_digest_dec = self.__hexToDecimalString(server_digest)
        server_message = "*#%s##" % server_digest_dec

        if self.sock.recv(4096) == server_message.encode():
            self.sock.send(ACK)
            logging.info('Authenticated')

    def __createRbHex(self):
        return binascii.hexlify(os.urandom(32)).decode()

    def __decimalStringToHex(self, s):
        hex_string = ''
        for (subchars) in regex.findall('..', s):
            hex_string += hex(int(subchars))[2:]
        return hex_string

    def __hexToDecimalString(self, h):
        dec_string = ''
        for (subchars) in regex.findall('.', h):
            dec_string += '{0:02d}'.format(int(subchars, 16))
        return dec_string
