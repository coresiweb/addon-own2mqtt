import regex
import logging
from time import time

ACK = b'*#*1##'

class OWNFrameCommand:
  def __init__(self, mqtt_client, sock, timer, topic, payload):
    self.mqtt_client = mqtt_client
    self.sock = sock
    self.topic = topic
    self.payload = payload
    self.topic_parts = topic.split('/')
    self.timer = timer
    self.createFrame()
    
  def createFrame(self):
    if self.topic_parts[1] == 'command_frame':
      self.frame = self.payload
      self.sendFrame()
      logging.debug(f'RX: {self.sock.recv(256)}')
    elif self.topic_parts[1].startswith('who-'):
      self.who = self.topic_parts[1].replace('who-','')
      if self.who == '1':
        logging.debug('WHO %s' % self.who)
        self.sendFrameWho1()
      elif self.who == '2':
        logging.debug('WHO %s' % self.who)
        self.sendFrameWho2()

  def sendFrame(self):
    logging.debug('TX: %s' % self.frame)
    self.sock.send(self.frame)
    self.timer.reset()

  def sendFrameWho1(self):
    self.where = self.topic_parts[2]
    if self.payload == b'ON':
      self.frame = ('*1*1*%s##' % self.where).encode()
    elif self.payload == b'OFF':
      self.frame = ('*1*0*%s##' % self.where).encode()

    self.sendFrame()
    data_received = self.sock.recv(256)

    if data_received == ACK:
      self.mqtt_client.publish(f'openwebnet/who-1/{self.where}/state', payload=self.payload, qos=0, retain=True)

  def sendFrameWho2(self):
    self.where = self.topic_parts[2]
    if self.topic_parts[3] == 'command':
      if self.payload == b'STOP':
        logging.debug('WHo 2 STOP')
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
    self.sendFrame()
    data_received = self.sock.recv(256)
  
    logging.debug('RX: %s' % data_received)

    # state_command_match = regex.search(r"^\*(?P<who>\d+)\*(?P<what>\d+)(#(?P<what_param>\d+))*\*(?P<where>\d+)(#(?P<where_param>\d+))*##$", self.frame)
    # if state_command_match:
    #   self.typeStateCommand(state_command_match)
    # else:
    #   state_request_match = regex.search(r"^\*#(?P<who>\d+)\*(?P<where>\d+)##$", self.frame)
    #   if state_request_match:
    #     self.typeStateRequest(state_request_match)
    #   else:
    #     dimension_request_match = regex.search(r"^\*#(?P<who>\d+)\*(?P<where>\d+)\*(?P<dimension>\d+)\*?((?P<dimension_value>\d+)\*?)*##$", self.frame)
    #     if dimension_request_match:
    #       self.typeDimensionRequest(dimension_request_match)
    #     else:
    #       dimension_write_match = regex.search(r"^\*#(?P<who>\d+)\*(?P<where>\d+)\*#(?P<dimension>\d+)\*?((?P<dimension_value>\d+)\*?)*##$", self.frame)
    #       if dimension_write_match:
    #         self.typeDimensionWrite(dimension_write_match)
    #       else:
    #         logging.info('RX: %s', self.frame)
