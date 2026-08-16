from domain.contract.system_api_contract import SystemApiContract
from domain.entity.file_entry_entity import FileEntryEntity


class ListDirectoryUc:
    """Mirrors the Flutter app's PathView.loadData(): list a directory,
    hide dotfiles, sort entries by name."""

    def __init__(self, system_api: SystemApiContract):
        self._system_api = system_api

    def get_entry_list(self, path: str) -> list[FileEntryEntity]:
        entry_list = [
            entry
            for entry in self._system_api.list_dir(path)
            if not entry.name.startswith(".")
        ]
        entry_list.sort(key=lambda entry: entry.name)
        return entry_list
