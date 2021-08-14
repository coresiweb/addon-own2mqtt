import regex
import logging
from time import time
from datetime import datetime, timedelta


class OWNFrameMonitor:
    def __init__(self, frame, own_instance):
        self.logger = logging.getLogger("own2mqtt")

        self.frame = frame
        self.frame_type = None
        self.who = None
        self.what = None
        self.what_param = None
        self.where = None
        self.where_param = None
        self.dimension = None
        self.dimension_value = None
        self.dimension_list = {}
        self.own_instance = own_instance
        self.mqtt_client = own_instance.mqtt_client
        self.mqtt_base_topic = own_instance.mqtt_base_topic
        self.read_frame()

    def read_frame(self):
        state_command_regex = r"^\*(?P<who>\d+)\*(?P<what>\d+)(#(?P<what_param>\d+))*\*(?P<where>\d+)(#(?P<where_param>\d+))*##$"
        state_command_match = regex.search(state_command_regex, self.frame)
        if state_command_match:
            self.type_state_command(state_command_match)
        else:
            state_request_regex = r"^\*#(?P<who>\d+)\*(?P<where>\d+)##$"
            state_request_match = regex.search(state_request_regex, self.frame)
            if state_request_match:
                self.type_state_request(state_request_match)
            else:
                dimension_request_regex = r"^\*#(?P<who>\d+)\*(?P<where>\d+(#\d+)?)?\*(?P<dimension>\d+)\*?((?P<dimension_value>\d+)\*?)*##$"
                dimension_request_match = regex.search(dimension_request_regex, self.frame)
                if dimension_request_match:
                    self.type_dimension_request(dimension_request_match)
                else:
                    dimension_write_regex = r"^\*#(?P<who>\d+)\*(?P<where>\d+)\*#(?P<dimension>\d+)\*?((?P<dimension_value>\d+)\*?)*##$"
                    dimension_write_match = regex.search(dimension_write_regex, self.frame)
                    if dimension_write_match:
                        self.type_dimension_write(dimension_write_match)
                    else:
                        self.logger.debug('RX: %s', self.frame)

    def type_state_command(self, match):
        self.frame_type = 'state_command'
        self.who = match.group('who')
        self.what = match.group('what')
        self.what_param = match.captures('what_param')
        self.where = match.group('where')
        self.where_param = match.captures('where_param')
        self.logger.debug(self.__explain_state_command_frame())

        if self.who == '1':
            self.mqtt_state_command_who_1()
        elif self.who == '2':
            self.mqtt_state_command_who_2()
        elif self.who == '4':
            self.mqtt_state_command_who_4()
        elif self.who == '25':
            self.mqtt_state_command_who_25()

    def type_state_request(self, match):
        self.frame_type = 'state_request'
        self.who = match.group('who')
        self.where = match.group('where')
        self.logger.debug(self.__explain_state_request_frame())

    def type_dimension_request(self, match):
        self.frame_type = 'dimension_request'
        self.who = match.group('who')
        self.where = match.group('where')
        self.dimension = match.group('dimension')
        self.dimension_value = match.captures('dimension_value')

        if self.who == '1':
            self.mqtt_dimension_request_who_1()
        elif self.who == '2':
            self.mqtt_dimension_request_who_2()
        elif self.who == '4':
            self.mqtt_dimension_request_who_4()
        elif self.who == '13':
            self.mqtt_dimension_request_who_13()
        elif self.who == '18':
            self.mqtt_dimension_request_who_18()

    def type_dimension_write(self, match):
        self.frame_type = 'dimension_write'
        self.who = match.group('who')
        self.where = match.group('where')
        self.dimension = match.group('dimension')
        self.dimension_value = match.captures('dimension_value')

        self.__explain_dimension_write_frame()

    def mqtt_state_command_who_1(self):
        if self.what == '34':
            self.mqtt_client.publish(f"{self.mqtt_base_topic}/who-1/{self.where}/presence", payload='ON', qos=1,
                                     retain=False)
        else:
            if self.what == '1':
                state = 'ON'
            elif self.what == '0':
                state = 'OFF'
            else:
                state = self.what
                self.logger.debug(self.__explain_state_command_frame())
            self.mqtt_client.publish(f"{self.mqtt_base_topic}/who-1/{self.where}/state", payload=state, qos=1,
                                     retain=True)

    def mqtt_state_command_who_2(self):
        if self.what == '1000':
            if self.what_param == ['0']:
                state = 'stopped'
            elif self.what_param == ['1']:
                state = 'opening'
            elif self.what_param == ['2']:
                state = 'closing'
            else:
                state = self.what_param
                self.logger.debug(self.__explain_state_command_frame())
            self.mqtt_client.publish(f"{self.mqtt_base_topic}/who-2/{self.where}/state", payload=state, qos=1,
                                     retain=True)

    def mqtt_state_command_who_4(self):
        if self.what == '4002':
            return
        else:
            if self.what == '1':
                mode = 'heat'
            elif self.what == '0':
                mode = 'cool'
            else:
                mode = 'off'
            self.mqtt_client.publish(f"{self.mqtt_base_topic}/who-4/zones/{self.where}/mode/current", payload=mode,
                                     qos=1, retain=True)
            self.mqtt_client.publish(f"{self.mqtt_base_topic}/who-4/zones/{self.where}/mode/raw", payload=self.what,
                                     qos=1, retain=True)

    def mqtt_state_command_who_25(self):
        if self.what == '21':
            pressure = 'short'
            self.mqtt_client.publish(f"{self.mqtt_base_topic}/who-25/{self.where}/{self.what_param[0]}/short",
                                     payload='on', qos=1, retain=False)
            self.mqtt_client.publish(f"{self.mqtt_base_topic}/who-25/{self.where}/{self.what_param[0]}/short",
                                     payload='off', qos=1, retain=False)
        elif self.what == '22':
            pressure = 'startextend'
            self.mqtt_client.publish(f"{self.mqtt_base_topic}/who-25/{self.where}/{self.what_param[0]}/long",
                                     payload='on', qos=1, retain=False)
        elif self.what == '23':
            pressure = 'extend'
        elif self.what == '24':
            pressure = 'endextend'
            self.mqtt_client.publish(f"{self.mqtt_base_topic}/who-25/{self.where}/{self.what_param[0]}/long",
                                     payload='off', qos=1, retain=False)
        else:
            pressure = self.what
            self.logger.debug(self.__explain_state_command_frame())
        self.mqtt_client.publish(f"{self.mqtt_base_topic}/who-25/{pressure}",
                                 payload=f"{self.where}-{self.what_param[0]}", qos=1,
                                 retain=False)

    def mqtt_dimension_request_who_1(self):
        self.dimension_list = {
            'lightIntesity': self.dimension_value[0]
        }

        if self.dimension == '6':
            self.mqtt_client.publish(f"{self.mqtt_base_topic}/who-1/{self.where}/light",
                                     payload=self.dimension_list['lightIntesity'], qos=1, retain=False)

        self.logger.debug(self.__explain_dimension_request_frame())

    def mqtt_dimension_request_who_2(self):
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

        self.mqtt_client.publish(f"{self.mqtt_base_topic}/who-2/{self.where}/state", payload=state, qos=1, retain=True)
        self.mqtt_client.publish(f"{self.mqtt_base_topic}/who-2/{self.where}/position",
                                 payload=self.dimension_list['shutterLevel'],
                                 qos=1, retain=True)

        self.logger.debug(self.__explain_dimension_request_frame())

    def mqtt_dimension_request_who_4(self):
        if self.dimension == '0':
            temperature = str_temp_to_float(self.dimension_value[0])
            self.dimension_list = {
                'temperature': temperature,
            }
            self.mqtt_client.publish(f"{self.mqtt_base_topic}/who-4/zones/{self.where}/temperature/current",
                                     payload=self.dimension_list['temperature'], qos=1, retain=True)
        if self.dimension == '12':
            temperature = str_temp_to_float(self.dimension_value[0])
            self.dimension_list = {
                'target_temperature': temperature,
            }
            self.mqtt_client.publish(f"{self.mqtt_base_topic}/who-4/zones/{self.where}/temperature/target",
                                     payload=self.dimension_list['target_temperature'], qos=1, retain=True)
        if self.dimension == '14':
            temperature = str_temp_to_float(self.dimension_value[0])
            self.dimension_list = {
                'target_temperature': temperature,
            }
            self.mqtt_client.publish(f"{self.mqtt_base_topic}/who-4/zones/{self.where}/temperature/target",
                                     payload=self.dimension_list['target_temperature'], qos=1, retain=True)
        if self.dimension == '19':
            self.dimension_list = {
                'conditioning': int(self.dimension_value[0]),
                'status': int(self.dimension_value[1]),
            }
            self.mqtt_client.publish(f"{self.mqtt_base_topic}/who-4/valves/{self.where}/conditioning",
                                     payload=self.dimension_list['conditioning'], qos=1, retain=True)
            self.mqtt_client.publish(f"{self.mqtt_base_topic}/who-4/valves/{self.where}/status",
                                     payload=self.dimension_list['status'], qos=1, retain=True)
        if self.dimension == '20':
            zone, actuator = self.where.split('#')
            self.dimension_list = {
                'status': int(self.dimension_value[0])
            }
            self.mqtt_client.publish(f"{self.mqtt_base_topic}/who-4/actuators/{actuator}/{zone}/status",
                                     payload=self.dimension_list['status'], qos=1, retain=True)
        if self.dimension == '60':
            humidity = str_humi_to_float(self.dimension_value[0])
            self.dimension_list = {
                'humidity': humidity,
            }
            self.mqtt_client.publish(f"{self.mqtt_base_topic}/who-4/zones/{self.where}/humidity/current",
                                     payload=self.dimension_list['humidity'], qos=1, retain=True)
        self.logger.debug(self.__explain_dimension_request_frame())

    def mqtt_dimension_request_who_13(self):
        if self.dimension == '19':
            self.dimension_list = {
                'days': int(self.dimension_value[0]),
                'hours': int(self.dimension_value[1]),
                'minutes': int(self.dimension_value[2]),
                'seconds': int(self.dimension_value[3]),
            }
            received_uptime = timedelta(days=self.dimension_list['days'], hours=self.dimension_list['hours'], minutes=self.dimension_list['minutes'], seconds=self.dimension_list['seconds'])
            self.mqtt_client.publish(f"{self.mqtt_base_topic}/who-13/uptime", payload=received_uptime.total_seconds(), qos=1, retain=False)
        if self.dimension == '22':
            self.dimension_list = {
                'hours': int(self.dimension_value[0]),
                'minutes': int(self.dimension_value[1]),
                'seconds': int(self.dimension_value[2]),
                'time_zone': int(self.dimension_value[3]),
                'day_of_week': int(self.dimension_value[4]),
                'day': int(self.dimension_value[5]),
                'month': int(self.dimension_value[6]),
                'year': int(self.dimension_value[7]),
            }
            received_datetime = datetime(self.dimension_list['year'], self.dimension_list['month'], self.dimension_list['day'], self.dimension_list['hours'], self.dimension_list['minutes'], self.dimension_list['seconds'])
            self.mqtt_client.publish(f"{self.mqtt_base_topic}/who-13/datetime", payload=received_datetime.isoformat(), qos=1, retain=False)
        self.logger.debug(self.__explain_dimension_request_frame())

    def mqtt_dimension_request_who_18(self):
        self.where = self.where.replace('#0', '')
        if self.dimension == '51':
            self.mqtt_client.publish(f"{self.mqtt_base_topic}/who-18/{self.where}/total_energy",
                                     payload=self.dimension_value[0], qos=1,
                                     retain=True)
        if self.dimension == '53':
            self.mqtt_client.publish(f"{self.mqtt_base_topic}/who-18/{self.where}/current_month_energy",
                                     payload=self.dimension_value[0], qos=1,
                                     retain=True)
        if self.dimension == '54':
            self.mqtt_client.publish(f"{self.mqtt_base_topic}/who-18/{self.where}/current_day_energy",
                                     payload=self.dimension_value[0], qos=1,
                                     retain=True)
        if self.dimension == '72':
            self.mqtt_client.publish(f"{self.mqtt_base_topic}/who-18/{self.where}/current_day_energy",
                                     payload=self.dimension_value[0], qos=1,
                                     retain=True)
        if self.dimension == '113':
            self.mqtt_client.publish(f"{self.mqtt_base_topic}/who-18/{self.where}/active_power",
                                     payload=self.dimension_value[0], qos=1,
                                     retain=False)

    def __explain_state_command_frame(self):
        return "RX: %s (TYPE: STATE_COMMAND | WHO: %s | WHAT: %s | WHAT_PARAM: %s | WHERE: %s | WHERE_PARAM: %s)" % (
            self.frame, self.who, self.what, ', '.join(self.what_param), self.where, ', '.join(self.where_param))

    def __explain_state_request_frame(self):
        return "RX: %s (TYPE: STATE_REQUEST | WHO: %s | WHERE: %s)" % (self.frame, self.who, self.where)

    def __explain_dimension_request_frame(self):
        return "RX: %s (TYPE: DIMENSION_REQUEST | WHO: %s | WHERE: %s | DIMENSION: %s | DIMENSION_VALUE: %s)" % (
            self.frame, self.who, self.where, self.dimension, self.dimension_list)

    def __explain_dimension_write_frame(self):
        return "RX: %s (TYPE: DIMENSION_WRITE | WHO: %s | WHERE: %s | DIMENSION: %s | DIMENSION_VALUE: %s)" % (
            self.frame, self.who, self.where, self.dimension, ', '.join(self.dimension_value))


def str_temp_to_float(temp_str):
    temp_float = int(temp_str) / 10.0
    return temp_float


def str_humi_to_float(humi_str):
    humi_float = int(humi_str) / 1.0
    return humi_float
