import ctypes
import os
import stat
from ctypes import wintypes

from .storage import fingerprint, reparse

SYSTEM_ROOTS = {
    "windows", "windows.old", "program files", "program files (x86)", "programdata",
    "system volume information", "$recycle.bin", "recovery", "boot", "efi",
    "documents and settings", "config.msi", "perflogs", "$windows.~bt",
}
CRITICAL = {"pagefile.sys", "hiberfil.sys", "swapfile.sys", "bootmgr", "bootnxt",
            "ntuser.dat", "usrclass.dat", "bcd", "desktop.ini"}
CRITICAL_EXTENSIONS = {".sys", ".efi", ".dll", ".drv"}
RESERVED = {"con", "prn", "aux", "nul", "conin$", "conout$"} | {
    f"{prefix}{digit}" for prefix in ("com", "lpt") for digit in "123456789¹²³"
}


def inspect_path(path):
    if os.name != "nt":
        raise OSError("A exclusão segura está disponível somente no Windows.")
    path = os.path.normpath(path)
    drive, tail = os.path.splitdrive(path)
    parts = tail.lstrip("\\").split("\\")
    if len(drive) != 2 or drive[1] != ":" or not tail.startswith("\\") or not parts[0]:
        raise OSError("Raízes de volumes e caminhos não locais são protegidos.")
    if parts[0].casefold() in SYSTEM_ROOTS:
        raise OSError("Diretório essencial protegido.")
    normalized = os.path.normcase(path)
    for variable in ("SystemRoot", "ProgramFiles", "ProgramFiles(x86)", "ProgramData"):
        root = os.environ.get(variable)
        if root:
            root = os.path.normcase(os.path.normpath(root))
            if normalized == root or normalized.startswith(root + "\\"):
                raise OSError("Diretório essencial protegido.")
    users = os.path.join(os.environ.get("SystemDrive", "C:"), "\\Users")
    if os.path.normcase(users) == normalized or (
        normalized.startswith(os.path.normcase(users) + "\\") and len(parts) == 2
    ):
        raise OSError("A raiz de um perfil de usuário é protegida.")
    lower_parts = [part.casefold() for part in parts]
    if "appdata" in lower_parts:
        appdata = lower_parts.index("appdata")
        if lower_parts[appdata + 1:appdata + 3] != ["local", "temp"] or len(parts) <= appdata + 3:
            raise OSError("Dados de aplicativos protegidos fora da pasta Temp.")
    drive_info = os.lstat(drive + "\\")
    if reparse(drive_info):
        raise OSError("Raiz redirecionada.")
    current = drive + "\\"
    for part in parts:
        if part.endswith((" ", ".")) or ":" in part or part.split(".")[0].casefold() in RESERVED:
            raise OSError("Nome de caminho não suportado.")
        current = os.path.join(current, part)
        info = os.lstat(current)
        name = part.casefold()
        if (reparse(info) or getattr(info, "st_file_attributes", 0) & 0x4
                or name in CRITICAL or name.startswith(("ntuser.dat.", "usrclass.dat."))
                or os.path.splitext(name)[1] in CRITICAL_EXTENSIONS):
            raise OSError(f"Item protegido ou redirecionado: {current}")
    return info


def probe(path, folder):
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    create = kernel.CreateFileW
    create.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
                       wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    create.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    flags = 0x00200000 | (0x02000000 if folder else 0)  # Open reparse point, directory access.
    handle = create(path, 0x10000 | 0x80, 0, None, 3, flags, None)
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    kernel.CloseHandle(handle)


def validate(entry, stop):
    pending = [entry]
    while pending:
        if stop.is_set():
            raise OSError("Operação cancelada.")
        node = pending.pop()
        info = inspect_path(node.path)
        if fingerprint(info) != node.identity:
            raise OSError(f"Item alterado após a análise: {node.path}")
        if node.folder != stat.S_ISDIR(info.st_mode):
            raise OSError("Tipo do item alterado.")
        if getattr(info, "st_file_attributes", 0) & 1 and not node.folder:
            raise OSError(f"Arquivo somente leitura: {node.path}")
        if node.folder:
            with os.scandir(node.path) as items:
                if {item.name for item in items} != {child.name for child in node.children}:
                    raise OSError(f"Conteúdo novo ou não verificado: {node.path}")
            pending.extend(node.children)
        probe(node.path, node.folder)


def collapse(entries):
    unique = {os.path.normcase(e.path): e for e in entries}
    result = []
    for path, item in unique.items():
        parent = os.path.dirname(path)
        while parent != os.path.dirname(parent) and parent not in unique:
            parent = os.path.dirname(parent)
        if parent not in unique or parent == path:
            result.append(item)
    return result


def recycle(entries, stop, progress):
    from PySide6.QtCore import QFile

    sent, errors = [], []
    for index, entry in enumerate(entries, 1):
        if stop.is_set():
            break
        progress(f"Verificando {index}/{len(entries)}  ·  {entry.path}")
        try:
            check_bin(entry.path)
            validate(entry, stop)
            if stop.is_set():
                break
            if fingerprint(inspect_path(entry.path)) != entry.identity:
                raise OSError("Item alterado durante a verificação.")
            target = QFile(entry.path)
            if not target.moveToTrash():
                raise OSError(target.errorString())
            sent.append(entry.path)
        except (OSError, ValueError) as exc:
            errors.append(f"{entry.path} — {exc}")
    return sent, errors


def check_bin(path):
    if os.name != "nt":
        raise OSError("A Lixeira do Windows não está disponível.")

    class BinInfo(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("bytes", ctypes.c_longlong),
                    ("items", ctypes.c_longlong)]

    query = ctypes.windll.shell32.SHQueryRecycleBinW
    query.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(BinInfo)]
    query.restype = ctypes.c_long
    root = os.path.splitdrive(path)[0] + "\\"
    info = BinInfo(ctypes.sizeof(BinInfo))
    if query(root, ctypes.byref(info)) != 0:
        raise OSError("O Windows não disponibilizou a Lixeira para esta unidade.")
