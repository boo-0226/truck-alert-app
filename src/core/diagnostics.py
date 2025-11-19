# file path: /src/core/diagnostics.py
from typing import List, Dict
_errors: List[Dict] = []

def add_error(site: str, where: str, msg: str):
    _errors.append({"site": site, "where": where, "msg": msg})

def list_errors() -> List[Dict]:
    return list(_errors)

def clear_errors():
    _errors.clear()
