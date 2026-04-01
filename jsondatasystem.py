import json
import os

from basestorage import BaseStorage


class JSONStorage(BaseStorage):
    def __init__(self, filepath):
        self.filepath = filepath

    def load(self, **kwargs):
        if not os.path.exists(self.filepath):
            return []
        with open(self.filepath, 'r') as f:
            return json.load(f)

    def save(self, data, **kwargs):
        with open(self.filepath, 'w') as f:
            json.dump(data, f, indent=4)

    def append(self, record, **kwargs):
        data = self.load()
        data.append(record)
        self.save(data)

    def remove(self, record, **kwargs):
        data = self.load()
        if record in data:
            data.remove(record)
        self.save(data)

    def getfilepath(self):
        return self.filepath