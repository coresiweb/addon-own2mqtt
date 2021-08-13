import json, logging, sys, os
from openwebnet import OpenWebNet

from logging.handlers import TimedRotatingFileHandler

if len(sys.argv) > 1:
    options_path = sys.argv[1]
    logDir = '../../log'
else:
    options_path = '/data/options.json'
    logDir = '/data/log'
    os.mkdir(logDir)

with open(options_path) as json_file:
    options = json.load(json_file)

logger = logging.getLogger("own2mqtt")
logger.setLevel(options['log_level'])

logHandler = TimedRotatingFileHandler(filename=f"{logDir}/app.log", when="midnight", interval=1, backupCount=5)
logFormatter = logging.Formatter('%(asctime)s %(levelname)-2s [%(filename)s:%(lineno)d] %(message)s')
logHandler.setFormatter(logFormatter)
logHandler.suffix = "%Y-%m-%d.log"
logHandler.extMatch = r"^\d{4}-\d{2}-\d{2}\.log$"

streamHandler = logging.StreamHandler(sys.stderr)
streamHandler.setFormatter(logFormatter)

logger.addHandler(streamHandler)
#logger.addHandler(logHandler)


#logging.basicConfig(format='', datefmt='%Y-%m-%d:%H:%M:%S', stream=sys.stderr, level=options['log_level'])

OpenWebNet(options).run()

