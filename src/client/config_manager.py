import keyring
import configparser

class ConfigManager:

    def __init__(self, service_name: str = "patcher"):
        self.service_name = service_name
        self.config = configparser.ConfigParser()

    def get_credential(self, key: str) -> str:
        return keyring.get_password(self.service_name, key)

    def set_credential(self, key: str, value: str):
        keyring.set_password(self.service_name, key, value)



