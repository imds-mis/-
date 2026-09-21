from __future__ import annotations

from pathlib import Path


class LocalStorage:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def write(self, key: str, data: bytes, *, overwrite: bool = False) -> str:
        path = self.root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and not overwrite:
            raise FileExistsError(key)
        path.write_bytes(data)
        return key

    def read(self, key: str) -> bytes:
        return (self.root / key).read_bytes()

    def path(self, key: str) -> Path:
        return self.root / key
