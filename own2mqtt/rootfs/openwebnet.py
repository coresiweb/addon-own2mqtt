import socket, hashlib, regex, os, binascii, logging
from own_frame_monitor import OWNFrameMonitor
from own_frame_command import OWNFrameCommand
from threading import Thread
from resettabletimer import ResettableTimer

TYPE_OF_MONITOR = 'MONITOR'
TYPE_OF_COMMAND = 'COMMAND'

class OpenWebNet(Thread):
    def __init__(self, type_of, mqtt_client, options):
        Thread.__init__(self)
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

    def run(self):
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

    def monitor(self):
        while True:
            data_received = self.sock.recv(4096).decode()
            if data_received == b'':
                return
            else:
                frame = OWNFrameMonitor(data_received, self.mqtt_client)
                self.mqtt_client.publish('openwebnet/last_frame', payload=frame.frame, qos=0, retain=False)

    def command(self):
        self.timer = ResettableTimer(25.0, self.sendKeepAlive)
        self.timer.start()

        topics = [
            ('openwebnet/command_frame', 0),
            ('openwebnet/who-1/+/command', 0),
            ('openwebnet/who-2/+/command', 0),
            ('openwebnet/who-2/+/set_position', 0),
        ]
        self.mqtt_client.on_message=self.on_message
        self.mqtt_client.subscribe(topics)
        self.mqtt_client.loop_forever()

    def on_message(self, client, userdata, message):
        logging.debug('MQTT: TOPIC: %s | PAYLOAD: %s', message.topic, message.payload)
        OWNFrameCommand(client, self.sock, self.timer, message.topic, message.payload)

    def sendKeepAlive(self):
        self.sock.send(self.KEEP_ALIVE)
        logging.debug(b'KA: %b' % self.KEEP_ALIVE)
        data_received = self.sock.recv(256)
        logging.debug(b'RX: %b' % data_received)
        self.timer.reset()

    def __authenticate(self):
        logging.info('Authenticating...')
        rb_hex = self.__createRbHex()
        rb = self.__hexToDecimalString(rb_hex)
        ra_search = regex.search(
            r'\*#(\d{128})##', self.sock.recv(4096).decode())
        if not ra_search:
            return False
        ra_hex = self.__decimalStringToHex(ra_search.group(1))
        kab_hex = hashlib.sha256(self.own_password.encode()).hexdigest()

        client_hash = hashlib.new('sha256')
        client_hash.update(ra_hex.encode())
        client_hash.update(rb_hex.encode())
        client_hash.update(self.A_HEX.encode())
        client_hash.update(self.B_HEX.encode())
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
            self.sock.send(self.ACK)
            logging.info('Authenticated')
            return True
        return False

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