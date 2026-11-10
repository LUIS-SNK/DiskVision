import hashlib
import os
import stat
from collections import defaultdict

from .storage import fingerprint, reparse

BLOCK = 1024 * 1024


class Cancelled(Exception):
    pass


def check(stop):
    if stop.is_set():
        raise Cancelled


def verify(entry, info, descriptor=False):
    # Windows can expose different creation/change times via fstat and lstat.
    # Compare change time through lstat before and after opening the descriptor.
    fields = 4 if descriptor else 5
    if (reparse(info) or not stat.S_ISREG(info.st_mode)
            or fingerprint(info)[:fields] != entry.identity[:fields]):
        raise OSError("Arquivo alterado durante a análise.")


def open_entry(entry):
    parent = os.path.dirname(entry.path)
    while parent != os.path.dirname(parent):
        if reparse(os.lstat(parent)):
            raise OSError("Diretório redirecionado.")
        parent = os.path.dirname(parent)
    verify(entry, os.lstat(entry.path))
    return open(entry.path, "rb")


def digest(entry, stop):
    hashed = hashlib.sha256()
    with open_entry(entry) as stream:
        verify(entry, os.fstat(stream.fileno()), descriptor=True)
        for block in iter(lambda: stream.read(BLOCK), b""):
            check(stop)
            hashed.update(block)
        verify(entry, os.fstat(stream.fileno()), descriptor=True)
    verify(entry, os.lstat(entry.path))
    return hashed.digest()


def equal(first, second, stop):
    with open_entry(first) as left, open_entry(second) as right:
        verify(first, os.fstat(left.fileno()), descriptor=True)
        verify(second, os.fstat(right.fileno()), descriptor=True)
        while True:
            check(stop)
            a, b = left.read(BLOCK), right.read(BLOCK)
            if a != b:
                return False
            if not a:
                break
        verify(first, os.fstat(left.fileno()), descriptor=True)
        verify(second, os.fstat(right.fileno()), descriptor=True)
    verify(first, os.lstat(first.path))
    verify(second, os.lstat(second.path))
    return True


def find(files, stop, progress):
    sizes, hashes = defaultdict(list), defaultdict(list)
    groups, errors = [], 0
    seen = set()
    try:
        for entry in files:
            check(stop)
            key = entry.identity[:2]
            if entry.size and (not key[1] or key not in seen):
                sizes[entry.size].append(entry)
                seen.add(key)
        for same_size in sizes.values():
            if len(same_size) < 2:
                continue
            for entry in same_size:
                check(stop)
                progress(f"Calculando SHA-256  ·  {entry.path}")
                try:
                    hashes[entry.size, digest(entry, stop)].append(entry)
                except OSError:
                    errors += 1
        for bucket in hashes.values():
            if len(bucket) < 2:
                continue
            verified = []
            for entry in bucket:
                check(stop)
                try:
                    for group in verified:
                        if equal(group[0], entry, stop):
                            group.append(entry)
                            break
                    else:
                        verified.append([entry])
                except OSError:
                    errors += 1
            groups.extend(group for group in verified if len(group) > 1)
    except Cancelled:
        pass
    stable = []
    for group in groups:
        valid = []
        for entry in group:
            try:
                verify(entry, os.lstat(entry.path))
                valid.append(entry)
            except OSError:
                errors += 1
        if len(valid) > 1:
            stable.append(valid)
    return stable, errors, stop.is_set()
