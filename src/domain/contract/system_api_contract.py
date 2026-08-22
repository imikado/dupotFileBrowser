from abc import ABC, abstractmethod

from domain.entity.file_entry_entity import FileEntryEntity
from domain.entity.file_properties_entity import FilePropertiesEntity
from domain.entity.trash_entry_entity import TrashEntryEntity


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
    def open_with_chooser(self, path: str) -> bool:
        pass

    @abstractmethod
    def open_terminal(self, path: str) -> bool:
        pass

    @abstractmethod
    def set_wallpaper(self, path: str) -> bool:
        pass

    @abstractmethod
    def get_uri(self, path: str) -> str:
        pass

    @abstractmethod
    def get_content_type(self, path: str) -> str:
        pass

    @abstractmethod
    def get_file_properties(self, path: str) -> FilePropertiesEntity:
        pass

    @abstractmethod
    def get_dir_size(self, path: str) -> int:
        pass

    @abstractmethod
    def set_file_permissions(self, path: str, mode: int) -> bool:
        pass

    @abstractmethod
    def copy_path(self, source: str, destination: str) -> str | None:
        pass

    @abstractmethod
    def move_path(self, source: str, destination: str) -> str | None:
        pass

    @abstractmethod
    def compress_path(self, source: str, destination: str, archive_format: str) -> str | None:
        pass

    @abstractmethod
    def get_trash_dir(self) -> str:
        pass

    @abstractmethod
    def trash_path(self, path: str) -> bool:
        pass

    @abstractmethod
    def list_trash(self) -> list[TrashEntryEntity]:
        pass

    @abstractmethod
    def restore_trash_entry(self, trashed_path: str, original_path: str) -> bool:
        pass

    @abstractmethod
    def delete_trash_entry(self, trashed_path: str) -> bool:
        pass

    @abstractmethod
    def empty_trash(self) -> bool:
        pass

    @abstractmethod
    def add_colored_path(self, directory: str, name: str, color: str):
        pass

    @abstractmethod
    def remove_colored_path(self, directory: str, name: str):
        pass

    @abstractmethod
    def get_colored_path_map(self, directory: str) -> dict:
        pass

    @abstractmethod
    def set_folder_color(self, directory: str, color: str | None) -> bool:
        pass

    @abstractmethod
    def get_folder_color(self, directory: str) -> str | None:
        pass
