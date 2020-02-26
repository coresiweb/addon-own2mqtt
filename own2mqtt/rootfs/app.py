import json, logging, sys, socket
import paho.mqtt.client as mqtt
from openwebnet import OpenWebNet, TYPE_OF_MONITOR, TYPE_OF_COMMAND

options_path = sys.argv[1] if len(sys.argv) > 1 else '/data/options.json'

print(options_path)

with open(options_path) as json_file:
    options = json.load(json_file)

logging.basicConfig(format='%(asctime)s,%(msecs)d %(levelname)-8s [%(filename)s:%(lineno)d] %(message)s',
                    datefmt='%Y-%m-%d:%H:%M:%S', stream=sys.stderr, level=options['log_level'])

logging.info('Connecting to MQTT Server %s:%s', options['mqtt_server_ip'], options['mqtt_server_port'])

mqtt_client = mqtt.Client('own2mqtt')
mqtt_client.username_pw_set(options['mqtt_server_user'], options['mqtt_server_password'])
mqtt_client.connect(options['mqtt_server_ip'], options['mqtt_server_port'])

command_client = OpenWebNet(TYPE_OF_COMMAND, mqtt_client, options)
command_client.start()

monitor_client = OpenWebNet(TYPE_OF_MONITOR, mqtt_client, options)
monitor_client.start()
