"""Configuração central de logging.

A seção 18 do CENTRAL.md proíbe `print` em qualquer camada: todo diagnóstico
passa por `logging`. Este módulo é o único ponto que configura os handlers, e
deve ser chamado uma única vez pelo ponto de entrada (CLI ou aplicativo).
"""

from __future__ import annotations

import logging
import sys
from typing import Final

FORMATO: Final[str] = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"
FORMATO_DATA: Final[str] = "%H:%M:%S"

_configurado = False


def configurar(nivel: int = logging.INFO) -> None:
    """Configura o logging do processo, uma única vez.

    Chamadas repetidas são ignoradas, de modo que importar este módulo em
    testes ou em subcomandos não duplique handlers nem mensagens.

    Args:
        nivel: Nível mínimo registrado na raiz, como `logging.DEBUG`.
    """
    global _configurado
    if _configurado:
        return

    handler = logging.StreamHandler(stream=sys.stderr)
    handler.setFormatter(logging.Formatter(fmt=FORMATO, datefmt=FORMATO_DATA))

    raiz = logging.getLogger()
    raiz.setLevel(nivel)
    raiz.addHandler(handler)

    _configurado = True


def obter(nome: str) -> logging.Logger:
    """Devolve o logger de um módulo.

    Args:
        nome: Normalmente `__name__` do módulo chamador.

    Returns:
        O logger correspondente, sem configurar nada por conta própria.
    """
    return logging.getLogger(nome)
