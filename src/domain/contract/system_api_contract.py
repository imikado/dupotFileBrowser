from abc import ABC, abstractmethod

from domain.entity.file_entry_entity import FileEntryEntity


class SystemApiContract(ABC):

    @abstractmethod
    def file_exists(self, path: str) -> bool:
        pass

    @abstractmethod
    def is_dir(self, path: str) -> bool:
        pass

    @abstractmethod
    def read_json_file_obj(self, path: str) -> object:
        pass

    @abstractmethod
    def write_file(self, path: str, content: str):
        pass

    @abstractmethod
    def create_dir(self, path: str):
        pass

    @abstractmethod
    def list_dir(self, path: str) -> list[FileEntryEntity]:
        pass

    @abstractmethod
    def get_home_dir(self) -> str:
        pass

    @abstractmethod
    def get_parent_dir(self, path: str) -> str:
        pass

    @abstractmethod
    def open_path(self, path: str) -> bool:
        pass

    @abstractmethod
    def get_uri(self, path: str) -> str:
        pass

    @abstractmethod
    def get_content_type(self, path: str) -> str:
        pass

    @abstractmethod
    def get_copy_call(self, source: str, destination: str) -> list:
        pass

    @abstractmethod
    def get_move_call(self, source: str, destination: str) -> list:
        pass
