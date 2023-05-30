import configparser
import os

from dotenv import load_dotenv


def execute():
    load_dotenv()
    config = configparser.ConfigParser()
    env_var = os.getenv('IMAGE_COMPARER_CONFIG')
    config.read(env_var)

    try:
        run_ids = dict(config['Standard Run ID'])
    except KeyError:
        print("Section 'Standard Run ID' not found in the config file.")
        return None

    return run_ids

print(execute())