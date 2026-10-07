import logging
from logging.handlers import RotatingFileHandler


def configure(config, name):
    data = config.path(config['paths']['data_dir'])
    data.mkdir(parents=True, exist_ok=True)
    settings = config['logging']
    logging.basicConfig(level=settings['level'],
                        format='%(asctime)s %(levelname)s %(message)s',
                        handlers=[logging.StreamHandler(), RotatingFileHandler(
                            data / (name + '.log'), maxBytes=settings['max_bytes'],
                            backupCount=settings['backup_count'])])
