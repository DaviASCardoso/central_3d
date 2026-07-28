"""Editor: a tela onde o tempo é gasto.

Três painéis. À esquerda, estreito e recolhível, a árvore de corpos com
visibilidade alternável. Ao centro, a viewport. À direita, o inspetor. Abaixo
de tudo, uma barra de status com o estado da geração, o resultado da checagem,
os avisos do produto e as dimensões finais. Ver a seção 11 do CENTRAL.md.

A geração aqui é síncrona, com o travamento momentâneo aceito. O worker com
cancelamento e debounce é da entrega 3.

Nenhuma regra de negócio mora neste módulo: ele chama o núcleo e exibe o que
volta.
"""

from __future__ import annotations

import traceback
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QSplitter,
    QStackedWidget,
    QToolBar,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from central.contrato import Produto
from central.log import obter
from central.nucleo.erros import ErroCentral, ErroDeValidacao
from central.nucleo.geracao import ResultadoGeracao, gerar_sincrono
from central.nucleo.impressora import VOLUME_DE_CONSTRUCAO
from central.nucleo.tesselagem import NivelTesselagem
from central.nucleo.validacao import CHAVE_CRUZADA, validar
from central.ui import tema
from central.ui.inspetor import Inspetor
from central.ui.viewport import Viewport

_log = obter(__name__)

LARGURA_DA_ARVORE = 220
LARGURA_DO_INSPETOR = 340

PAGINA_VIEWPORT = 0
PAGINA_ERRO = 1


class ArvoreDeCorpos(QTreeWidget):
    """Lista os corpos do resultado atual, com visibilidade por corpo."""

    visibilidade_mudou = Signal(str, bool)

    def __init__(self, pai: QWidget | None = None) -> None:
        """Monta a árvore vazia.

        Args:
            pai: Widget pai.
        """
        super().__init__(pai)
        self.setHeaderLabels(["Corpo"])
        self.setRootIsDecorated(False)
        self.itemChanged.connect(self._item_mudou)

    def preencher(self, resultado: ResultadoGeracao) -> None:
        """Recria a lista a partir de um resultado de geração.

        Args:
            resultado: A geração cujos corpos devem ser listados.
        """
        self.blockSignals(True)
        self.clear()
        for corpo in resultado.resultado.corpos:
            item = QTreeWidgetItem([corpo.nome])
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(0, Qt.CheckState.Checked)
            item.setData(0, Qt.ItemDataRole.UserRole, corpo.nome)
            self.addTopLevelItem(item)
        self.blockSignals(False)

    def _item_mudou(self, item: QTreeWidgetItem, coluna: int) -> None:
        """Traduz a marcação do item num sinal de visibilidade."""
        del coluna
        nome = item.data(0, Qt.ItemDataRole.UserRole)
        self.visibilidade_mudou.emit(nome, item.checkState(0) == Qt.CheckState.Checked)

    def nomes(self) -> list[str]:
        """Devolve os nomes dos corpos listados."""
        return [
            self.topLevelItem(i).data(0, Qt.ItemDataRole.UserRole)
            for i in range(self.topLevelItemCount())
        ]


class BarraDeStatus(QWidget):
    """A faixa inferior: estado, avisos e dimensões."""

    def __init__(self, pai: QWidget | None = None) -> None:
        """Monta os três rótulos da barra.

        Args:
            pai: Widget pai.
        """
        super().__init__(pai)
        paleta = tema.paleta_atual()

        self.estado = QLabel("Pronto")
        self.avisos = QLabel("")
        self.avisos.setStyleSheet(f"color: {paleta.aviso};")
        self.dimensoes = QLabel("")
        self.dimensoes.setStyleSheet(f"color: {paleta.texto_fraco};")

        disposicao = QHBoxLayout(self)
        disposicao.setContentsMargins(
            tema.ESPACAMENTO * 2, tema.ESPACAMENTO // 2, tema.ESPACAMENTO * 2, tema.ESPACAMENTO // 2
        )
        disposicao.setSpacing(tema.ESPACAMENTO * 2)
        disposicao.addWidget(self.estado)
        disposicao.addWidget(self.avisos, 1)
        disposicao.addWidget(self.dimensoes)

    def mostrar_geracao(self, resultado: ResultadoGeracao) -> None:
        """Reflete uma geração bem-sucedida.

        Args:
            resultado: A geração recém-concluída.
        """
        paleta = tema.paleta_atual()
        self.estado.setStyleSheet(f"color: {paleta.texto};")
        corpos = len(resultado.resultado.corpos)
        self.estado.setText(f"Gerado — {corpos} corpo(s)")
        self.avisos.setText("  ·  ".join(resultado.avisos))

        largura, profundidade, altura = resultado.dimensoes
        texto = f"{largura:.1f} × {profundidade:.1f} × {altura:.1f} mm"
        if not VOLUME_DE_CONSTRUCAO.cabe(resultado.dimensoes):
            texto += "  ·  excede o volume de construção"
            self.dimensoes.setStyleSheet(f"color: {paleta.erro};")
        else:
            self.dimensoes.setStyleSheet(f"color: {paleta.texto_fraco};")
        self.dimensoes.setText(texto)

    def mostrar_erro(self, mensagem: str) -> None:
        """Reflete uma falha.

        Args:
            mensagem: Resumo de uma linha.
        """
        self.estado.setStyleSheet(f"color: {tema.paleta_atual().erro};")
        self.estado.setText(mensagem)
        self.avisos.setText("")
        self.dimensoes.setText("")

    def mostrar_estado(self, mensagem: str) -> None:
        """Escreve uma mensagem neutra no campo de estado.

        Args:
            mensagem: O texto a exibir.
        """
        self.estado.setStyleSheet(f"color: {tema.paleta_atual().texto};")
        self.estado.setText(mensagem)


class PainelDeErro(QWidget):
    """Substitui a viewport quando a geração falha, com traceback copiável."""

    def __init__(self, pai: QWidget | None = None) -> None:
        """Monta o painel vazio.

        Args:
            pai: Widget pai.
        """
        super().__init__(pai)
        paleta = tema.paleta_atual()

        self.titulo = QLabel("")
        self.titulo.setStyleSheet(
            f"color: {paleta.erro}; font-size: 15px; font-weight: 600;"
        )
        self.detalhe = QPlainTextEdit()
        self.detalhe.setReadOnly(True)

        disposicao = QVBoxLayout(self)
        disposicao.setContentsMargins(
            tema.ESPACAMENTO * 3, tema.ESPACAMENTO * 3, tema.ESPACAMENTO * 3, tema.ESPACAMENTO * 3
        )
        disposicao.addWidget(self.titulo)
        disposicao.addWidget(self.detalhe, 1)

    def mostrar(self, titulo: str, detalhe: str) -> None:
        """Exibe uma falha.

        Args:
            titulo: Resumo de uma linha.
            detalhe: Traceback ou lista de erros, selecionável e copiável.
        """
        self.titulo.setText(titulo)
        self.detalhe.setPlainText(detalhe)


class Editor(QWidget):
    """A tela de edição de um produto."""

    gerado = Signal(object)
    falhou = Signal(str)

    def __init__(self, pai: QWidget | None = None) -> None:
        """Monta os três painéis, ainda sem produto aberto.

        Args:
            pai: Widget pai.
        """
        super().__init__(pai)
        self.produto: Produto | None = None
        self.inspetor: Inspetor | None = None
        self.ultima_geracao: ResultadoGeracao | None = None

        self.barra_de_ferramentas = QToolBar()
        self.acao_restaurar = self.barra_de_ferramentas.addAction("Restaurar padrões")
        self.acao_restaurar.triggered.connect(self.restaurar_padroes)
        self.acao_restaurar.setEnabled(False)

        self.arvore = ArvoreDeCorpos()
        self.arvore.setFixedWidth(LARGURA_DA_ARVORE)
        self.arvore.visibilidade_mudou.connect(self._alternar_corpo)

        self.viewport = Viewport()
        self.painel_de_erro = PainelDeErro()
        self.pilha = QStackedWidget()
        self.pilha.addWidget(self.viewport)
        self.pilha.addWidget(self.painel_de_erro)

        self._area_do_inspetor = QWidget()
        self._disposicao_do_inspetor = QVBoxLayout(self._area_do_inspetor)
        self._disposicao_do_inspetor.setContentsMargins(0, 0, 0, 0)
        self._area_do_inspetor.setFixedWidth(LARGURA_DO_INSPETOR)

        self.divisor = QSplitter(Qt.Orientation.Horizontal)
        self.divisor.addWidget(self.arvore)
        self.divisor.addWidget(self.pilha)
        self.divisor.addWidget(self._area_do_inspetor)
        self.divisor.setStretchFactor(1, 1)
        self.divisor.setCollapsible(0, True)
        self.divisor.setCollapsible(1, False)

        self.status = BarraDeStatus()

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.setSpacing(0)
        raiz.addWidget(self.barra_de_ferramentas)
        raiz.addWidget(self.divisor, 1)
        raiz.addWidget(self.status)

        self._vazio = QLabel(
            "Escolha um produto na Biblioteca.", alignment=Qt.AlignmentFlag.AlignCenter
        )
        self._disposicao_do_inspetor.addWidget(self._vazio)

    # --- ciclo de vida ---------------------------------------------------

    def iniciar(self) -> None:
        """Inicializa a viewport. Precisa acontecer depois de a janela existir."""
        self.viewport.iniciar()

    def encerrar(self) -> None:
        """Solta os recursos do VTK."""
        self.viewport.encerrar()

    # --- abertura de produto ---------------------------------------------

    def abrir(self, produto: Produto, valores: dict[str, Any] | None = None) -> None:
        """Abre um produto no editor e gera pela primeira vez.

        Args:
            produto: O manifesto a editar.
            valores: Valores iniciais. Por padrão, os do manifesto.
        """
        self.produto = produto
        self.viewport.limpar()
        self.viewport.esquecer_enquadramento()

        if self.inspetor is not None:
            self._disposicao_do_inspetor.removeWidget(self.inspetor)
            self.inspetor.deleteLater()
        self._vazio.setVisible(False)

        self.inspetor = Inspetor(produto)
        self.inspetor.valores_mudaram.connect(self.gerar)
        self._disposicao_do_inspetor.addWidget(self.inspetor)

        self.acao_restaurar.setEnabled(True)

        if valores:
            self.inspetor.definir_valores(valores)

        _log.info("editor abriu o produto '%s'", produto.id)
        self.gerar(self.inspetor.valores())

    def restaurar_padroes(self) -> None:
        """Devolve todos os campos ao padrão declarado e regenera."""
        if self.inspetor is not None:
            self.inspetor.restaurar_padroes()

    # --- geração ---------------------------------------------------------

    def gerar(self, valores: dict[str, Any]) -> None:
        """Valida, gera e exibe. Síncrono nesta entrega.

        Args:
            valores: Valores correntes do inspetor.
        """
        if self.produto is None or self.inspetor is None:
            return

        validacao = validar(self.produto, valores)
        self.inspetor.grifar_erros(validacao.erros)
        if not validacao.valido:
            self._mostrar_invalido(validacao.erros)
            return

        self.status.mostrar_estado("Gerando…")
        try:
            resultado = gerar_sincrono(self.produto, valores, NivelTesselagem.PREVIEW)
        except ErroDeValidacao as erro:
            self._mostrar_invalido({CHAVE_CRUZADA: [str(erro)]})
            return
        except ErroCentral as erro:
            self._mostrar_falha(erro)
            return

        self.ultima_geracao = resultado
        self.pilha.setCurrentIndex(PAGINA_VIEWPORT)
        self.arvore.preencher(resultado)
        self.viewport.mostrar(
            resultado.malhas,
            cores={c.nome: c.cor for c in resultado.resultado.corpos},
            excede_volume=not VOLUME_DE_CONSTRUCAO.cabe(resultado.dimensoes),
        )
        self.status.mostrar_geracao(resultado)
        self.gerado.emit(resultado)

    def _mostrar_invalido(self, erros: dict[str, list[str]]) -> None:
        """Mostra erros de validação sem trocar a peça que está na viewport."""
        mensagens = [f"{chave}: {m}" for chave, ms in erros.items() for m in ms]
        resumo = f"{len(mensagens)} valor(es) inválido(s)"
        self.status.mostrar_erro(resumo)
        _log.debug("validação recusou: %s", mensagens)
        self.falhou.emit(resumo)

    def _mostrar_falha(self, erro: Exception) -> None:
        """Troca a viewport pelo painel de erro, mantendo o inspetor ativo.

        O inspetor continua funcional de propósito: o operador precisa poder
        corrigir o valor e tentar de novo sem reabrir o produto.
        """
        detalhe = "".join(
            traceback.format_exception(type(erro), erro, erro.__traceback__)
        )
        self.painel_de_erro.mostrar(str(erro), detalhe)
        self.pilha.setCurrentIndex(PAGINA_ERRO)
        self.status.mostrar_erro("Falha na geração")
        _log.warning("geração falhou: %s", erro)
        self.falhou.emit(str(erro))

    # --- corpos ----------------------------------------------------------

    def _alternar_corpo(self, nome: str, visivel: bool) -> None:
        """Liga ou desliga a visibilidade de um corpo na viewport."""
        self.viewport.definir_visibilidade(nome, visivel)

    def alternar_arvore(self) -> None:
        """Recolhe ou mostra o painel esquerdo."""
        self.arvore.setVisible(not self.arvore.isVisible())
