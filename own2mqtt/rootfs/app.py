import json, logging, sys, socket
from openwebnet_monitor import OWNMonitor

options_path = sys.argv[1] if len(sys.argv) > 1 else '/data/options.json'

print(options_path)

with open(options_path) as json_file:
    options = json.load(json_file)

logging.basicConfig(format='%(asctime)s,%(msecs)d %(levelname)-8s [%(filename)s:%(lineno)d] %(message)s',
                    datefmt='%Y-%m-%d:%H:%M:%S', stream=sys.stderr, level=options['log_level'])

while True:
    try:
        monitor = OWNMonitor(options)
        monitor.startSession()
    except socket.error:
        logging.error("Caught exception socket.error")
