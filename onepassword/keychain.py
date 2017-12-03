import json
import os
from fuzzywuzzy import process
import time
import uuid

from encryption_key import EncryptionKey

class Keychain(object):
    def __init__(self, path):
        self._path = os.path.expanduser(path)
        self._load_encryption_keys()
        self._load_item_list()
        self._locked = True

    def unlock(self, password):
        unlocker = lambda key: key.unlock(password)
        unlock_results = map(unlocker, self._encryption_keys.values())
        result = reduce(lambda x, y: x and y, unlock_results)
        self._locked = not result
        return result

    def get_items(self):
        return sorted(self._items.keys())

    def item(self, name, fuzzy_threshold=100):
        """
        Extract a password from an unlocked Keychain using fuzzy
        matching. ``fuzzy_threshold`` can be an integer between 0 and
        100, where 100 is an exact match.
        """
        match = process.extractOne(
            name,
            self._items.keys(),
            score_cutoff=(fuzzy_threshold-1),
        )
        if match:
            exact_name = match[0]
            item = self._items[exact_name]
            item.decrypt_with(self)
            return item
        else:
            return None

    def key(self, identifier=None, security_level=None):
        """
        Tries to find an encryption key, first using the ``identifier`` and
        if that fails or isn't provided using the ``security_level``.
        Returns ``None`` if nothing matches.
        """
        if identifier:
            try:
                return self._encryption_keys[identifier]
            except KeyError:
                pass
        if security_level:
            for key in self._encryption_keys.values():
                if key.level == security_level:
                    return key

    @property
    def locked(self):
        return self._locked

    def _load_encryption_keys(self):
        path = os.path.join(self._path, "data", "default", "encryptionKeys.js")
        with open(path, "r") as f:
            key_data = json.load(f)

        self._encryption_keys = {}
        for key_definition in key_data["list"]:
            key = EncryptionKey(**key_definition)
            self._encryption_keys[key.identifier] = key

    def _load_item_list(self):
        path = os.path.join(self._path, "data", "default", "contents.js")
        with open(path, "r") as f:
            item_list = json.load(f)

        self._items = {}
        for item_definition in item_list:
            item = KeychainItem.build(item_definition, self._path)
            self._items[item.name] = item


class KeychainItem(object):
    @classmethod
    def build(cls, row, path):
        identifier = row[0]
        type = row[1]
        name = row[2]
        if type == "webforms.WebForm":
            return WebFormKeychainItem(identifier, name, path, type)
        elif type == "passwords.Password" or type == "wallet.onlineservices.GenericAccount":
            return PasswordKeychainItem(identifier, name, path, type)
        else:
            return KeychainItem(identifier, name, path, type)

    def __init__(self, identifier, name, path, type):
        self.identifier = identifier
        self.name = name
        self.password = None
        self.username = None
        self._path = path
        self._type = type

    @property
    def key_identifier(self):
        return self._lazily_load("_key_identifier")

    @property
    def security_level(self):
        return self._lazily_load("_security_level")

    def decrypt_with(self, keychain):
        key = keychain.key(
            identifier=self.key_identifier,
            security_level=self.security_level,
        )
        encrypted_json = self._lazily_load("_encrypted_json")
        decrypted_json = key.decrypt(self._encrypted_json)
        self._data = json.loads(decrypted_json.strip('\x10'))
        self.password = self._find_password()
        self.username = self._find_username()

    def encrypt_with(self, keychain):
        key = keychain.key(
            identifier=self.key_identifier,
            security_level=self.security_level,
        )
        slef._encrypted_json = key.encrypt(json.dumps(self._data))
        
    def _find_password(self):
        raise Exception("Cannot extract a password from this type of"
                        " keychain item (%s)" % self._type)

    def _find_username(self):
        raise Exception("Cannot extract a username from this type of"
                        " keychain item (%s)" % self._type)

    def _lazily_load(self, attr):
        if not hasattr(self, attr):
            self._read_data_file()
        return getattr(self, attr)

    def _read_data_file(self):
        filename = "%s.1password" % self.identifier
        path = os.path.join(self._path, "data", "default", filename)
        with open(path, "r") as f:
            item_data = json.load(f)

        self._key_identifier = item_data.get("keyID")
        self._security_level = item_data.get("securityLevel")
        self._encrypted_json = item_data["encrypted"]
        
    def _write_data_file(self):
        filename = "%s.1password" % self.identifier
        path = os.path.join(self._path, "data", "default", filename)
        timestamp = int(time.time())
        uuid = str(uuid.uuid1().hex).upper()
        item_data = {
          "encrypted": self._encrypted_json,
          "createdAt": int(time.time()),
          "location": "https://www.protectmyid.com",
          "locationKey": "protectmyid.com",
          "securityLevel": "SL5",
          "title": "Experian",
          "txTimestamp": timestamp,
          "typeName": "webforms.WebForm",
          "updatedAt": timestamp,
          "uuid": uuid
        } 
        with open(path, 'w') as f:
            json.dump(item_data, f)

        
class WebFormKeychainItem(KeychainItem):
    def _find_password(self):
        for field in self._data["fields"]:
            if field.get("designation") == "password" or \
               field.get("name") == "Password":
                return field["value"]

    def _find_username(self):
        for field in self._data["fields"]:
            if field.get("designation") == "username" or \
               field.get("name") == "username":
                return field["value"]


class PasswordKeychainItem(KeychainItem):
    def _find_password(self):
        return self._data.get("password")

    def _find_username(self):
        return self._data.get("username")
