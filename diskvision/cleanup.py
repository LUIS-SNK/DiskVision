import os
import time


def classify(files, stop, progress):
    temporary = []
    candidates = []
    local = os.environ.get("LOCALAPPDATA")
    standard = os.path.normcase(os.path.join(local, "Temp")) if local else None
    expiry = time.time_ns() - 7 * 86400 * 10**9
    for entry in files:
        if stop.is_set():
            break
        path = os.path.normcase(entry.path)
        if standard and path.startswith(standard + os.sep) and entry.stamp < expiry:
            temporary.append(entry)
        elif entry.extension in {".tmp", ".dmp", ".old", ".bak"}:
            candidates.append(entry)
    return temporary, candidates, stop.is_set()
