from basestorage import BaseStorage


class DataManager:
    def __init__(self, storage: BaseStorage):
        self.storage = storage

    def add_record(self, record, **kwargs):
        self.storage.append(record, **kwargs)

    def remove_record(self, record, **kwargs):
        self.storage.remove(record, **kwargs)

    def get_all(self, **kwargs):
        return self.storage.load(**kwargs)

    def find_by_key(self, key, value, **kwargs):
        data = self.get_all(**kwargs)
        return [item for item in data if item.get(key) == value]

    def save_all(self, data, **kwargs):
        """Allows for bulk saving, like committing a multi-sheet dictionary."""
        self.storage.save(data, **kwargs)