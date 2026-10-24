from __future__ import annotations

from persona.maid_archive import MaidArchive


class Migration:
    from_version: int = -1
    to_version: int = -1

    def upgrade(self, archive: MaidArchive) -> None:
        raise NotImplementedError

    def describe(self) -> str:
        return f"migration v{self.from_version} -> v{self.to_version}"
