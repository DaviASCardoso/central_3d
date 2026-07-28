"""Janela principal.

Casca da aplicação: monta as abas, liga os sinais entre elas e nada mais.
Nenhuma regra de negócio mora aqui. Ver a seção 11 do CENTRAL.md.

As abas Lote e Catálogo pertencem às entregas 5 e 6 e por isso não existem —
nem como aba vazia.
"""

from __future__ import annotations

from PySide6.QtGui import QCloseEvent, QShowEvent
from PySide6.QtWidgets import QApplication, QMainWindow, QTabWidget

from central import __version__
from central.log import obter
from central.nucleo import Registro, descobrir
from central.ui import tema
from central.ui.biblioteca import Biblioteca
from central.ui.editor import Editor

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

        self.biblioteca = Biblioteca(self.registro)
        self.biblioteca.produto_escolhido.connect(self.abrir_no_editor)

        self.editor = Editor()

        self._abas = QTabWidget(self)
        self._abas.addTab(self.biblioteca, "Biblioteca")
        self._abas.addTab(self.editor, "Editor")
        self.setCentralWidget(self._abas)

        self.statusBar().showMessage(self._resumo_do_registro())
        _log.info("janela montada com %d produto(s)", len(self.registro))

    def abrir_no_editor(self, id_produto: str) -> None:
        """Abre um produto no Editor e troca para essa aba.

        Args:
            id_produto: Identificador do produto escolhido na biblioteca.
        """
        if id_produto not in self.registro:
            _log.warning("produto '%s' não está no registro", id_produto)
            return
        _log.info("produto '%s' escolhido na biblioteca", id_produto)
        self.ir_para(ABA_EDITOR)
        self.editor.abrir(self.registro.obter(id_produto))

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802 -- nome do Qt
        """Inicializa a viewport assim que a janela ganha um contexto gráfico."""
        super().showEvent(event)
        self.editor.iniciar()

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 -- nome do Qt
        """Solta os recursos do VTK antes de fechar.

        Sem isto o processo pode não terminar, porque o VTK segura o contexto
        de OpenGL depois de o widget Qt ter ido embora.
        """
        self.editor.encerrar()
        super().closeEvent(event)

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
