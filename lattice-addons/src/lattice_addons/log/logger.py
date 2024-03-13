import os
import logging


def get_logger(name: str) -> logging.Logger:
    LOGLEVEL = os.environ.get('LATTICE_LOGLEVEL', 'WARNING').upper()
    logger = logging.getLogger(name)
    logger.setLevel(LOGLEVEL)

    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('%(asctime)s %(name)s:%(lineno)d %(levelname)s: %(message)s'))
    logger.addHandler(handler)

    return logger
