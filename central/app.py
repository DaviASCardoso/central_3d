"""Ponto de entrada do aplicativo.

Cria a `QApplication`, aplica o tema, descobre os produtos e abre a janela.
Tudo que é lógica de valor já aconteceu antes de qualquer widget existir.
"""

from __future__ import annotations

import logging
import sys

from PySide6.QtWidgets import QApplication

from central import __version__, log
from central.nucleo import descobrir
from central.nucleo.erros import ErroCentral
from central.ui import tema
from central.ui.janela import JanelaPrincipal

_log = log.obter(__name__)

NOME_DO_APLICATIVO = "Central"
ORGANIZACAO = "Central"


def principal(argv: list[str] | None = None) -> int:
    """Abre a janela da Central e roda o laço de eventos.

    Args:
        argv: Argumentos de linha de comando repassados ao Qt. Por padrão,
            `sys.argv`.

    Returns:
        O código de saída do laço de eventos do Qt.
    """
    log.configurar(logging.INFO)

    aplicacao = QApplication(argv if argv is not None else sys.argv)
    aplicacao.setApplicationName(NOME_DO_APLICATIVO)
    aplicacao.setApplicationVersion(__version__)
    aplicacao.setOrganizationName(ORGANIZACAO)

    tema.aplicar(aplicacao)

    try:
        registro = descobrir()
    except ErroCentral:
        _log.exception("não foi possível descobrir os produtos")
        return 1

    janela = JanelaPrincipal(registro)
    janela.show()

    _log.info("Central %s aberta", __version__)
    return aplicacao.exec()


if __name__ == "__main__":
    sys.exit(principal())
