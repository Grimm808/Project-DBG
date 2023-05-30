import configparser
import os

from dotenv import load_dotenv


def execute(project_name, new_run_id):
    load_dotenv()
    config = configparser.ConfigParser()
    env_var = os.getenv('IMAGE_COMPARER_CONFIG')
    config.read(env_var)

    if project_name in config['Standard Run ID']:
        config['Standard Run ID'][project_name] = new_run_id

        with open(env_var, 'w') as configfile:
            config.write(configfile)
        return True
    else:
        return False
    
""" if __name__ == '__main__':
    project_name = 'AgriculturalTrailer'
    new_run_id = 'poo :)'
    execute(project_name, new_run_id) """