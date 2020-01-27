import regex
import logging
from time import time


class OWNFrameMonitor:
    def __init__(self, frame, mqtt_client):
        self.frame = frame
        self.frame_type = None
        self.who = None
        self.what = None
        self.what_param = None
        self.where = None
        self.where_param = None
        self.dimension = None
        self.dimension_value = None
        self.mqtt_client = mqtt_client
        self.readFrame()

    def readFrame(self):
        state_command_match = regex.search(r"^\*(?P<who>\d+)\*(?P<what>\d+)(#(?P<what_param>\d+))*\*(?P<where>\d+)(#(?P<where_param>\d+))*##$", self.frame)
        if state_command_match:
            self.typeStateCommand(state_command_match)
        else:
            state_request_match = regex.search(r"^\*#(?P<who>\d+)\*(?P<where>\d+)##$", self.frame)
            if state_request_match:
                self.typeStateRequest(state_request_match)
            else:
                dimension_request_match = regex.search(r"^\*#(?P<who>\d+)\*(?P<where>\d+)\*(?P<dimension>\d+)\*?((?P<dimension_value>\d+)\*?)*##$", self.frame)
                if dimension_request_match:
                    self.typeDimensionRequest(dimension_request_match)
                else:
                    dimension_write_match = regex.search(r"^\*#(?P<who>\d+)\*(?P<where>\d+)\*#(?P<dimension>\d+)\*?((?P<dimension_value>\d+)\*?)*##$", self.frame)
                    if dimension_write_match:
                        self.typeDimensionWrite(dimension_write_match)
                    else:
                        logging.info('RX: %s', self.frame)

    def typeStateCommand(self, match):
        self.frame_type = 'state_command'
        self.who = match.group('who')
        self.what = match.group('what')
        self.what_param = match.captures('what_param')
        self.where = match.group('where')
        self.where_param = match.captures('where_param')
        # logging.debug(self.__explainStateCommandFrame())

        if self.who == '1':
            self.mqttStateCommandWho1()
        elif self.who == '2':
            self.mqttStateCommandWho2()
        elif self.who == '25':
            self.mqttStateCommandWho25()

    def typeStateRequest(self, match):
        self.frame_type = 'state_request'
        self.who = match.group('who')
        self.where = match.group('where')
        # logging.debug(self.__explainStateCommandFrame())

    def typeDimensionRequest(self, match):
        self.frame_type = 'dimension_request'
        self.who = match.group('who')
        self.where = match.group('where')
        self.dimension = match.group('dimension')
        self.dimension_value = match.captures('dimension_value')

        if self.who == '1':
            self.mqttDimensionRequestWho1()
        elif self.who == '2':
            self.mqttDimensionRequestWho2()

    def typeDimensionWrite(self, match):
        self.frame_type = 'dimension_write'
        self.who = match.group('who')
        self.where = match.group('where')
        self.dimension = match.group('dimension')
        self.dimension_value = match.captures('dimension_value')

    def mqttStateCommandWho1(self):
        if self.what == '34':
            self.mqtt_client.publish(f"openwebnet/who-1/{self.where}/presence", payload='ON', qos=0, retain=False)
        else:
            if self.what == '1':
                state = 'ON'
            elif self.what == '0':
                state = 'OFF'
            else:
                state = self.what
                logging.debug(self.__explainStateCommandFrame())
            self.mqtt_client.publish(f"openwebnet/who-1/{self.where}/state", payload=state, qos=0, retain=True)

    def mqttStateCommandWho2(self):
        if self.what == '1000':
            if self.what_param == ['0']:
                state = 'stop'
            elif self.what_param == ['1']:
                state = 'open'
            elif self.what_param == ['2']:
                state = 'closed'
            else:
                state = self.what_param
                logging.debug(self.__explainStateCommandFrame())
            self.mqtt_client.publish(f"openwebnet/who-2/{self.where}/state", payload=state, qos=0, retain=True)

    def mqttStateCommandWho25(self):
        if self.what == '21':
            pressure = 'short'
        elif self.what == '22':
            pressure = 'startextend'
        elif self.what == '23':
            pressure = 'extend'
        elif self.what == '24':
            pressure = 'endextend'
        else:
            pressure = self.what
            logging.debug(self.__explainStateCommandFrame())
        self.mqtt_client.publish(f"openwebnet/who-25/{pressure}", payload=f"{self.where}-{self.what_param[0]}", qos=0,
                                 retain=False)
        self.mqtt_client.publish(f"openwebnet/who-25/{self.where}/{self.what_param[0]}/{pressure}",
                                 payload=int(time() * 1000), qos=0, retain=False)

    def mqttDimensionRequestWho1(self):
        self.dimension_list = {
            'lightIntesity': self.dimension_value[0]
        }

        if self.dimension == '6':
            self.mqtt_client.publish(f"openwebnet/who-1/{self.where}/light", payload=self.dimension_list['lightIntesity'], qos=0, retain=False)

        logging.debug(self.__explainDimensionRequestFrame())

    def mqttDimensionRequestWho2(self):
        self.dimension_list = {
            'shutterStatus': self.dimension_value[0],
            'shutterLevel': self.dimension_value[1],
            'shutterPriority': self.dimension_value[2],
            'shutterInfo': self.dimension_value[3]
        }

        if self.dimension_list['shutterStatus'] == '10':
            state = 'stop'
        elif self.dimension_list['shutterStatus'] == '11':
            state = 'open'
        elif self.dimension_list['shutterStatus'] == '12':
            state = 'closed'
        else:
            state = self.dimension_list['shutterStatus']

        self.mqtt_client.publish(f"openwebnet/who-2/{self.where}/state", payload=state, qos=0, retain=True)
        self.mqtt_client.publish(f"openwebnet/who-2/{self.where}/position", payload=self.dimension_list['shutterLevel'], qos=0, retain=True)

        logging.debug(self.__explainDimensionRequestFrame())

    def __explainStateCommandFrame(self):
        return "TYPE: STATE_COMMAND | WHO: %s | WHAT: %s | WHAT_PARAM: %s | WHERE: %s | WHERE_PARAM: %s (%s)" % (
            self.who, self.what, ', '.join(self.what_param), self.where, ', '.join(self.where_param), self.frame)

    def __explainStateRequestFrame(self):
        return "TYPE: STATE_REQUEST | WHO: %s | WHERE: %s (%s)" % (self.who, self.where, self.frame)

    def __explainDimensionRequestFrame(self):
        return "TYPE: DIMENSION_REQUEST | WHO: %s | WHERE: %s | DIMENSION: %s | DIMENSION_VALUE: %s (%s)" % (
            self.who, self.where, self.dimension, self.dimension_list, self.frame)

    def __explainDimensionWriteFrame(self):
        return "TYPE: DIMENSION_WRITE | WHO: %s | WHERE: %s | DIMENSION: %s | DIMENSION_VALUE: %s (%s)" % (
            self.who, self.where, self.dimension, ', '.join(self.dimension_value), self.frame)
