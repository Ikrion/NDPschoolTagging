from abc import ABC, abstractmethod
class BaseStorage(ABC):
    @abstractmethod
    def load(self, **kwargs):
        pass

    @abstractmethod
    def save(self, data, **kwargs):
        pass

    @abstractmethod
    def append(self, record, **kwargs):
        pass

    @abstractmethod
    def remove(self, record, **kwargs):
        pass

    @abstractmethod
    def getfilepath(self):
        pass