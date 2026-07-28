"""Diretórios do aplicativo.

Nenhum caminho absoluto aparece em código: tudo passa por `pathlib.Path`
resolvido a partir do diretório do aplicativo ou do diretório de dados do
usuário, conforme a seção 18 do CENTRAL.md.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from central.log import obter

_log = obter(__name__)

NOME_DO_APLICATIVO = "Central"

_sobrescrita_de_dados: Path | None = None


def raiz_do_repositorio() -> Path:
    """Devolve a raiz do repositório, resolvida a partir deste arquivo."""
    return Path(__file__).resolve().parent.parent.parent


def diretorio_de_dados() -> Path:
    """Devolve o diretório de dados do usuário, criando-o se preciso.

    No Windows é `%LOCALAPPDATA%/Central`; no Linux, o equivalente XDG. Uma
    sobrescrita definida por `definir_diretorio_de_dados` tem precedência, o
    que é como os testes evitam sujar o perfil real.

    Returns:
        O diretório, garantidamente existente.
    """
    if _sobrescrita_de_dados is not None:
        _sobrescrita_de_dados.mkdir(parents=True, exist_ok=True)
        return _sobrescrita_de_dados

    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))

    destino = base / NOME_DO_APLICATIVO
    destino.mkdir(parents=True, exist_ok=True)
    return destino


def diretorio_de_cache() -> Path:
    """Devolve o diretório de cache de malhas, criando-o se preciso."""
    destino = diretorio_de_dados() / "cache"
    destino.mkdir(parents=True, exist_ok=True)
    return destino


def definir_diretorio_de_dados(caminho: Path | None) -> None:
    """Redireciona o diretório de dados, ou volta ao padrão com `None`.

    Args:
        caminho: Diretório a usar, ou `None` para desfazer a sobrescrita.
    """
    global _sobrescrita_de_dados
    _sobrescrita_de_dados = caminho
    _log.debug("diretório de dados redirecionado para %s", caminho)
