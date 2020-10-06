import logging
from own_frame_monitor import OWNFrameMonitor


class OWNFrameCommand:
    def __init__(self, own_instance, topic, payload):
        self.own_instance = own_instance
        self.topic = topic
        self.payload = payload
        self.topic_parts = topic.split('/')
        self.frame = None
        self.who = None
        self.where = None
        self.create_frame()

    def create_frame(self):
        if self.topic_parts[1] == 'command_frame':
            self.frame = self.payload
            self.own_instance.write_socket(self.frame)
            self.own_instance.__read_socket(self.own_instance.command_socket)

        elif self.topic_parts[1].startswith('who-'):
            self.who = self.topic_parts[1].replace('who-', '')
            if self.who == '1':
                logging.debug('WHO %s' % self.who)
                self.send_frame_who_1()
            elif self.who == '2':
                logging.debug('WHO %s' % self.who)
                self.send_frame_who_2()
            elif self.who == '4':
                logging.debug('WHO %s' % self.who)
                self.send_frame_who_4()

    def send_frame_who_1(self):
        self.where = self.topic_parts[2]
        if self.payload == b'ON':
            self.frame = ('*1*1*%s##' % self.where).encode()
        elif self.payload == b'OFF':
            self.frame = ('*1*0*%s##' % self.where).encode()

        self.own_instance.write_socket(self.frame)
        response_frames = self.own_instance.__read_socket(self.own_instance.command_socket)

        if self.own_instance.ACK.decode() in response_frames:
            self.own_instance.mqtt_client.publish(f'{self.own_instance.mqtt_base_topic}/who-1/{self.where}/state',
                                                  payload=self.payload, qos=1, retain=True)

    def send_frame_who_2(self):
        self.where = self.topic_parts[2]
        if self.topic_parts[3] == 'command':
            if self.payload == b'STOP':
                logging.debug('WHO 2 STOP')
                self.frame = ('*2*0*%s##' % self.where).encode()
            elif self.payload == b'OPEN':
                logging.debug('WHO 2 OPEN')
                self.frame = ('*2*1*%s##' % self.where).encode()
            elif self.payload == b'CLOSE':
                logging.debug('WHO 2 CLOSE')
                self.frame = ('*2*2*%s##' % self.where).encode()
        elif self.topic_parts[3] == 'set_position':
            logging.debug('WHO 2 Set Position')
            self.frame = ('*#2*%s*#11#001*%s##' % (self.where, self.payload.decode())).encode()
        self.own_instance.write_socket(self.frame)
        self.own_instance.__read_socket(self.own_instance.command_socket)

    def send_frame_who_4(self):
        default_temperature = 21.0
        default_temperatur_str = int(default_temperature * 10.0)
        self.where = self.topic_parts[3]
        if self.topic_parts[4] == 'mode':
            if self.payload == b'heat':
                logging.debug('WHO 4 - SET HEATING')
                self.frame = f'*#4*{self.where}*#14*0{default_temperatur_str}*1##'.encode()
            elif self.payload == b'cool':
                logging.debug('WHO 4 - SET COOL')
                self.frame = f'*#4*{self.where}*#14*0{default_temperatur_str}*2##'.encode()
            elif self.payload == b'off':
                logging.debug('WHO 4 - SET OFF')
                # Set "Antifreeze" mode inspite of "Generic OFF"
                self.frame = f'*4*303*{self.where}##'.encode()
            self.own_instance.write_socket(self.frame)
            response_frames = self.own_instance.__read_socket(self.own_instance.command_socket)

            if self.own_instance.ACK.decode() in response_frames:
                self.own_instance.mqtt_client.publish(f'{self.own_instance.mqtt_base_topic}/who-4/zones/{self.where}/mode/current', payload=self.payload, qos=1, retain=True)
                self.own_instance.mqtt_client.publish(f'{self.own_instance.mqtt_base_topic}/who-4/zones/{self.where}/temperature/target', payload=default_temperature, qos=1, retain=True)

        if self.topic_parts[4] == 'temperature':
            temperature_str = int(float(self.payload.decode()) * 10.0)
            self.frame = f'*#4*{self.where}*#14*0{temperature_str}*3##'.encode()
            self.own_instance.write_socket(self.frame)
            response_frames = self.own_instance.__read_socket()

            if self.own_instance.ACK.decode() in response_frames:
                self.own_instance.mqtt_client.publish(f'{self.own_instance.mqtt_base_topic}/who-4/zones/{self.where}/temperature/target', payload=self.payload, qos=1, retain=True)