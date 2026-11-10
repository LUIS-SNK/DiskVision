import ctypes
import os
import shutil
import stat
import time
from dataclasses import dataclass, field


@dataclass(slots=True)
class Entry:
    path: str
    name: str
    folder: bool
    size: int
    stamp: int
    identity: tuple
    children: list = field(default_factory=list)

    @property
    def extension(self):
        return "" if self.folder else os.path.splitext(self.name)[1].lower()


@dataclass(slots=True)
class Scan:
    root: Entry
    files: list
    errors: int
    skipped: int
    count: int
    partial: bool


def units():
    if os.name != "nt":
        return [os.path.abspath(os.sep)]
    kernel = ctypes.windll.kernel32
    kernel.GetDriveTypeW.argtypes = [ctypes.c_wchar_p]
    mask = kernel.GetLogicalDrives()
    return [root for i in range(26) if mask & (1 << i)
            and kernel.GetDriveTypeW(root := f"{chr(65+i)}:\\") in (2, 3, 5, 6)]


def capacities(stop, progress):
    result = []
    for root in units():
        if stop.is_set():
            break
        try:
            result.append((root, shutil.disk_usage(root)))
        except OSError:
            result.append((root, None))
    return result


def reparse(info):
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0) & 0x400
    )


def fingerprint(info):
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns


def scan(root, stop, progress):
    info = os.lstat(root)
    if reparse(info) or not stat.S_ISDIR(info.st_mode):
        raise ValueError("A raiz precisa ser um diretório local sem redirecionamento.")
    top = Entry(root, root, True, 0, info.st_mtime_ns, fingerprint(info))
    files, stack = [], [(top, None)]
    errors = skipped = count = 0
    last = 0.0
    try:
        while stack and not stop.is_set():
            node, iterator = stack[-1]
            try:
                if iterator is None:
                    current = os.lstat(node.path)
                    if reparse(current) or fingerprint(current)[:2] != node.identity[:2]:
                        raise OSError("Diretório alterado")
                    iterator = os.scandir(node.path)
                    stack[-1] = node, iterator
                item = next(iterator)
            except (StopIteration, OSError) as exc:
                errors += isinstance(exc, OSError)
                if iterator is not None:
                    iterator.close()
                stack.pop()
                if stack:
                    stack[-1][0].size += node.size
                continue
            count += 1
            now = time.monotonic()
            if now - last > 0.2:
                progress(f"{count:,} itens examinados  ·  {node.path}")
                last = now
            try:
                # On Windows DirEntry.stat leaves device and inode fields unset.
                info = os.lstat(item.path)
            except OSError:
                errors += 1
                continue
            folder = stat.S_ISDIR(info.st_mode)
            if reparse(info) or not (folder or stat.S_ISREG(info.st_mode)):
                skipped += 1
                continue
            child = Entry(item.path, item.name, folder, 0 if folder else info.st_size,
                          info.st_mtime_ns, fingerprint(info))
            node.children.append(child)
            if folder:
                stack.append((child, None))
            else:
                files.append(child)
                node.size += child.size
    finally:
        while stack:
            node, iterator = stack.pop()
            if iterator is not None:
                iterator.close()
            if stack:
                stack[-1][0].size += node.size
    return Scan(top, files, errors, skipped, count, stop.is_set())


def byte_text(size):
    value = float(size)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB", "PiB"):
        if value < 1024 or unit == "PiB":
            return f"{value:.1f} {unit}".replace(".", ",") if unit != "B" else f"{size} B"
        value /= 1024


def remove_entries(scan, paths):
    """Remove recycled entries and adjust the logical sizes of their ancestors."""
    removed = set()
    root_path = os.path.normcase(scan.root.path)
    for path in paths:
        path = os.path.normcase(path)
        if path == root_path or not path.startswith(root_path.rstrip(os.sep) + os.sep):
            continue
        parts = os.path.relpath(path, root_path).split(os.sep)
        ancestors = [scan.root]
        for part in parts:
            child = next((item for item in ancestors[-1].children
                          if os.path.normcase(item.name) == part), None)
            if child is None:
                break
            ancestors.append(child)
        else:
            target = ancestors.pop()
            parent = ancestors[-1]
            parent.children = [item for item in parent.children if item is not target]
            for folder in ancestors:
                folder.size -= target.size
            # Removing a direct child changes the parent directory's metadata.
            try:
                info = os.lstat(parent.path)
                if not reparse(info) and fingerprint(info)[:2] == parent.identity[:2]:
                    parent.identity = fingerprint(info)
                    parent.stamp = info.st_mtime_ns
            except OSError:
                pass
            pending = [target]
            while pending:
                item = pending.pop()
                removed.add(id(item))
                pending.extend(item.children)
    if removed:
        scan.files = [item for item in scan.files if id(item) not in removed]
    return removed
