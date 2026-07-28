"""Janela principal.

Casca da aplicação: monta as abas, liga os sinais entre elas e nada mais.
Nenhuma regra de negócio mora aqui. Ver a seção 11 do CENTRAL.md.

As abas Lote e Catálogo pertencem às entregas 5 e 6 e por isso não existem —
nem como aba vazia.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel, QMainWindow, QTabWidget, QWidget

from central import __version__
from central.log import obter
from central.nucleo import Registro, descobrir
from central.ui import tema

_log = obter(__name__)

TITULO = "Central"
LARGURA_INICIAL = 1400
ALTURA_INICIAL = 900

ABA_BIBLIOTECA = 0
ABA_EDITOR = 1


class JanelaPrincipal(QMainWindow):
    """A janela da Central, com uma aba por tela.

    Attributes:
        registro: O registro de produtos descobertos, compartilhado pelas abas.
    """

    def __init__(self, registro: Registro | None = None) -> None:
        """Monta a janela.

        Args:
            registro: Registro já descoberto. Por padrão, faz a descoberta
                agora, no diretório `produtos/` do repositório.
        """
        super().__init__()
        self.registro = registro if registro is not None else descobrir()

        self.setWindowTitle(f"{TITULO} {__version__}")
        self.resize(LARGURA_INICIAL, ALTURA_INICIAL)

        self._abas = QTabWidget(self)
        self._abas.addTab(self._montar_biblioteca(), "Biblioteca")
        self._abas.addTab(self._montar_editor(), "Editor")
        self.setCentralWidget(self._abas)

        self.statusBar().showMessage(self._resumo_do_registro())
        _log.info("janela montada com %d produto(s)", len(self.registro))

    def _montar_biblioteca(self) -> QWidget:
        """Cria o conteúdo da aba Biblioteca.

        A grade de cards chega no commit da biblioteca; até lá fica um resumo
        textual, para que a janela seja funcional em vez de mentir sobre um
        painel que ainda não existe.
        """
        return QLabel(
            self._resumo_do_registro(), alignment=Qt.AlignmentFlag.AlignCenter
        )

    def _montar_editor(self) -> QWidget:
        """Cria o conteúdo da aba Editor.

        Os três painéis chegam no commit do editor.
        """
        return QLabel(
            "Escolha um produto na Biblioteca.",
            alignment=Qt.AlignmentFlag.AlignCenter,
        )

    def _resumo_do_registro(self) -> str:
        """Frase de uma linha com a contagem de produtos e de falhas."""
        quantidade = len(self.registro)
        plural = "produto" if quantidade == 1 else "produtos"
        resumo = f"{quantidade} {plural} no catálogo"
        if self.registro.falhas:
            resumo += f", {len(self.registro.falhas)} com falha ao carregar"
        return resumo

    def ir_para(self, indice: int) -> None:
        """Troca a aba visível.

        Args:
            indice: `ABA_BIBLIOTECA` ou `ABA_EDITOR`.
        """
        self._abas.setCurrentIndex(indice)

    def aba_atual(self) -> int:
        """Devolve o índice da aba visível."""
        return self._abas.currentIndex()

    def nomes_das_abas(self) -> list[str]:
        """Devolve os rótulos das abas, na ordem em que aparecem."""
        return [self._abas.tabText(i) for i in range(self._abas.count())]


def criar_janela(registro: Registro | None = None) -> JanelaPrincipal:
    """Cria a janela principal com o tema já aplicado.

    Args:
        registro: Registro de produtos, ou `None` para descobrir agora.

    Returns:
        A janela, ainda não exibida.
    """
    aplicacao = QApplication.instance()
    if aplicacao is not None:
        tema.aplicar(aplicacao)  # type: ignore[arg-type]
    return JanelaPrincipal(registro)
