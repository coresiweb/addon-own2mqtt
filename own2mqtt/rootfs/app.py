import json, logging, sys, errno
from openwebnet import OpenWebNet

options_path = sys.argv[1] if len(sys.argv) > 1 else '/data/options.json'

with open(options_path) as json_file:
    options = json.load(json_file)

logging.basicConfig(format='%(asctime)s %(levelname)-2s [%(filename)s:%(lineno)d] %(message)s',
                    datefmt='%Y-%m-%d:%H:%M:%S', stream=sys.stderr, level=options['log_level'])

OpenWebNet(options).run()
