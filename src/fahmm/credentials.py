"""Windows Credential Manager access for optional provider API keys."""

from __future__ import annotations

import ctypes
import re
import sys
from ctypes import wintypes

CRED_TYPE_GENERIC = 1
CRED_PERSIST_LOCAL_MACHINE = 2
ERROR_NOT_FOUND = 1168


class CREDENTIALW(ctypes.Structure):
    _fields_ = [
        ("Flags", wintypes.DWORD),
        ("Type", wintypes.DWORD),
        ("TargetName", wintypes.LPWSTR),
        ("Comment", wintypes.LPWSTR),
        ("LastWritten", wintypes.FILETIME),
        ("CredentialBlobSize", wintypes.DWORD),
        ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
        ("Persist", wintypes.DWORD),
        ("AttributeCount", wintypes.DWORD),
        ("Attributes", ctypes.c_void_p),
        ("TargetAlias", wintypes.LPWSTR),
        ("UserName", wintypes.LPWSTR),
    ]


PCREDENTIALW = ctypes.POINTER(CREDENTIALW)


class WindowsCredentialStore:
    def __init__(self) -> None:
        if sys.platform != "win32":
            raise RuntimeError("Windows Credential Manager is unavailable")
        try:
            self.api = ctypes.WinDLL("Advapi32", use_last_error=True)
            self.api.CredWriteW.argtypes = [PCREDENTIALW, wintypes.DWORD]
            self.api.CredWriteW.restype = wintypes.BOOL
            self.api.CredReadW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD,
                                           wintypes.DWORD, ctypes.POINTER(PCREDENTIALW)]
            self.api.CredReadW.restype = wintypes.BOOL
            self.api.CredDeleteW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
            self.api.CredDeleteW.restype = wintypes.BOOL
            self.api.CredFree.argtypes = [ctypes.c_void_p]
            self.api.CredFree.restype = None
        except (AttributeError, OSError) as exc:
            raise RuntimeError("Windows Credential Manager is unavailable") from exc

    @staticmethod
    def _target(profile_id: str) -> str:
        if not re.fullmatch(r"[0-9a-f]{32}", profile_id):
            raise ValueError("Invalid provider profile ID")
        return f"fahmm:provider:{profile_id}"

    def set_key(self, profile_id: str, key: str) -> None:
        if not isinstance(key, str) or not key:
            raise ValueError("API key must contain text")
        blob = key.encode("utf-8")
        if len(blob) > 2560:
            raise ValueError("API key is too long for Windows Credential Manager")
        buffer = ctypes.create_string_buffer(blob)
        credential = CREDENTIALW()
        credential.Type = CRED_TYPE_GENERIC
        credential.TargetName = self._target(profile_id)
        credential.CredentialBlobSize = len(blob)
        credential.CredentialBlob = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte))
        credential.Persist = CRED_PERSIST_LOCAL_MACHINE
        credential.UserName = "fahmm"
        try:
            if not self.api.CredWriteW(ctypes.byref(credential), 0):
                raise RuntimeError("Could not save API key in Windows Credential Manager")
        finally:
            ctypes.memset(buffer, 0, len(buffer))

    def get_key(self, profile_id: str) -> str | None:
        pointer = PCREDENTIALW()
        if not self.api.CredReadW(self._target(profile_id), CRED_TYPE_GENERIC, 0,
                                  ctypes.byref(pointer)):
            if ctypes.get_last_error() == ERROR_NOT_FOUND:
                return None
            raise RuntimeError("Could not read API key from Windows Credential Manager")
        try:
            credential = pointer.contents
            return ctypes.string_at(credential.CredentialBlob,
                                    credential.CredentialBlobSize).decode("utf-8")
        finally:
            self.api.CredFree(pointer)

    def delete_key(self, profile_id: str) -> None:
        if (not self.api.CredDeleteW(self._target(profile_id), CRED_TYPE_GENERIC, 0)
                and ctypes.get_last_error() != ERROR_NOT_FOUND):
            raise RuntimeError("Could not remove API key from Windows Credential Manager")
