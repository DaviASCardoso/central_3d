"""Biblioteca de produtos.

Grade de cards com filtro por categoria e busca em texto livre sobre nome,
descrição e tags. Um produto que falhou ao carregar aparece como card vermelho
com o traceback a um clique, porque o operador precisa ver o erro em vez de
ver o produto sumir. Ver as seções 5 e 11 do CENTRAL.md.

As miniaturas renderizadas são da entrega 7; aqui o card usa a inicial do
produto como marca tipográfica.
"""

from __future__ import annotations

import unicodedata

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from central.contrato import Produto
from central.log import obter
from central.nucleo import ProdutoComFalha, Registro
from central.ui import tema

_log = obter(__name__)

TODAS_AS_CATEGORIAS = "Todas as categorias"
COLUNAS = 3
LARGURA_DO_CARD = 280
ALTURA_DO_CARD = 190


def _sem_acento(texto: str) -> str:
    """Devolve o texto em minúsculas e sem acentos, para busca tolerante."""
    decomposto = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in decomposto if not unicodedata.combining(c)).casefold()


def corresponde(produto: Produto, busca: str) -> bool:
    """Diz se um produto casa com um termo de busca livre.

    A busca ignora acentos e caixa, e varre nome, descrição e tags.

    Args:
        produto: O manifesto a testar.
        busca: O termo digitado pelo operador.

    Returns:
        Verdadeiro se o termo aparece em algum dos campos pesquisáveis.
    """
    termo = _sem_acento(busca).strip()
    if not termo:
        return True
    campos = (produto.nome, produto.descricao, produto.categoria, *produto.tags)
    return any(termo in _sem_acento(campo) for campo in campos)


class DialogoDeTraceback(QDialog):
    """Mostra o traceback de um produto que falhou, em texto selecionável."""

    def __init__(self, falha: ProdutoComFalha, pai: QWidget | None = None) -> None:
        """Monta o diálogo.

        Args:
            falha: A falha a exibir.
            pai: Widget pai.
        """
        super().__init__(pai)
        self.setWindowTitle(f"Falha em {falha.id}")
        self.resize(900, 520)

        disposicao = QVBoxLayout(self)
        disposicao.addWidget(QLabel(str(falha.caminho)))

        self.texto = QPlainTextEdit(falha.traceback_completo or falha.mensagem)
        self.texto.setReadOnly(True)
        self.texto.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        disposicao.addWidget(self.texto)

        fechar = QPushButton("Fechar")
        fechar.clicked.connect(self.accept)
        rodape = QHBoxLayout()
        rodape.addStretch(1)
        rodape.addWidget(fechar)
        disposicao.addLayout(rodape)


class CardDeProduto(QFrame):
    """Card clicável de um produto válido."""

    escolhido = Signal(str)

    def __init__(self, produto: Produto, pai: QWidget | None = None) -> None:
        """Monta o card.

        Args:
            produto: O manifesto a exibir.
            pai: Widget pai.
        """
        super().__init__(pai)
        self.produto = produto
        self.setObjectName("cardDeProduto")
        self.setFixedSize(LARGURA_DO_CARD, ALTURA_DO_CARD)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        paleta = tema.paleta_atual()
        self.setStyleSheet(
            f"""
            QFrame#cardDeProduto {{
                background: {paleta.fundo_elevado};
                border: 1px solid {paleta.borda};
                border-radius: {tema.RAIO * 2}px;
            }}
            QFrame#cardDeProduto:hover {{
                border: 1px solid {paleta.destaque};
            }}
            """
        )

        disposicao = QVBoxLayout(self)
        disposicao.setContentsMargins(
            tema.ESPACAMENTO * 2, tema.ESPACAMENTO * 2, tema.ESPACAMENTO * 2, tema.ESPACAMENTO * 2
        )
        disposicao.setSpacing(tema.ESPACAMENTO // 2)

        inicial = QLabel(produto.nome[:1].upper())
        inicial.setStyleSheet(
            f"font-size: 34px; font-weight: 600; color: {paleta.destaque};"
        )
        disposicao.addWidget(inicial)

        titulo = QLabel(produto.nome)
        titulo.setStyleSheet(f"font-size: 15px; font-weight: 600; color: {paleta.texto};")
        titulo.setWordWrap(True)
        disposicao.addWidget(titulo)

        descricao = QLabel(produto.descricao)
        descricao.setStyleSheet(f"color: {paleta.texto_fraco};")
        descricao.setWordWrap(True)
        descricao.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding
        )
        disposicao.addWidget(descricao)

        rodape = QLabel(f"{produto.categoria}  ·  v{produto.versao}")
        rodape.setStyleSheet(f"color: {paleta.texto_fraco}; font-size: 11px;")
        disposicao.addWidget(rodape)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802 -- nome do Qt
        """Emite `escolhido` no clique com o botão esquerdo."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.escolhido.emit(self.produto.id)
        super().mousePressEvent(event)


class CardDeFalha(QFrame):
    """Card vermelho de um produto que não carregou."""

    traceback_pedido = Signal(str)

    def __init__(self, falha: ProdutoComFalha, pai: QWidget | None = None) -> None:
        """Monta o card de falha.

        Args:
            falha: A falha a exibir.
            pai: Widget pai.
        """
        super().__init__(pai)
        self.falha = falha
        self.setObjectName("cardDeFalha")
        self.setFixedSize(LARGURA_DO_CARD, ALTURA_DO_CARD)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        paleta = tema.paleta_atual()
        self.setStyleSheet(
            f"""
            QFrame#cardDeFalha {{
                background: {paleta.fundo_elevado};
                border: 1px solid {paleta.erro};
                border-radius: {tema.RAIO * 2}px;
            }}
            """
        )

        disposicao = QVBoxLayout(self)
        disposicao.setContentsMargins(
            tema.ESPACAMENTO * 2, tema.ESPACAMENTO * 2, tema.ESPACAMENTO * 2, tema.ESPACAMENTO * 2
        )
        disposicao.setSpacing(tema.ESPACAMENTO // 2)

        titulo = QLabel(falha.id)
        titulo.setStyleSheet(f"font-size: 15px; font-weight: 600; color: {paleta.erro};")
        disposicao.addWidget(titulo)

        mensagem = QLabel(falha.mensagem)
        mensagem.setStyleSheet(f"color: {paleta.texto_fraco};")
        mensagem.setWordWrap(True)
        mensagem.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding
        )
        disposicao.addWidget(mensagem)

        self.botao = QPushButton("Ver traceback")
        self.botao.clicked.connect(lambda: self.traceback_pedido.emit(falha.id))
        disposicao.addWidget(self.botao)


class Biblioteca(QWidget):
    """A tela de biblioteca inteira: filtros mais grade."""

    produto_escolhido = Signal(str)

    def __init__(self, registro: Registro, pai: QWidget | None = None) -> None:
        """Monta a biblioteca a partir de um registro já descoberto.

        Args:
            registro: Produtos descobertos e falhas.
            pai: Widget pai.
        """
        super().__init__(pai)
        self.registro = registro

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(
            tema.ESPACAMENTO * 2, tema.ESPACAMENTO * 2, tema.ESPACAMENTO * 2, tema.ESPACAMENTO
        )
        raiz.setSpacing(tema.ESPACAMENTO * 2)

        raiz.addLayout(self._montar_filtros())

        self._grade_widget = QWidget()
        self._grade = QGridLayout(self._grade_widget)
        self._grade.setSpacing(tema.ESPACAMENTO * 2)
        self._grade.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

        rolagem = QScrollArea()
        rolagem.setWidgetResizable(True)
        rolagem.setWidget(self._grade_widget)
        raiz.addWidget(rolagem, 1)

        self._vazio = QLabel("Nenhum produto corresponde ao filtro.")
        self._vazio.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._vazio.setStyleSheet(f"color: {tema.paleta_atual().texto_fraco};")
        raiz.addWidget(self._vazio)

        self.atualizar()

    def _montar_filtros(self) -> QHBoxLayout:
        """Monta a linha de busca e o combo de categoria."""
        self.busca = QLineEdit()
        self.busca.setPlaceholderText("Buscar por nome, descrição ou tag")
        self.busca.setClearButtonEnabled(True)
        self.busca.textChanged.connect(self.atualizar)

        self.categoria = QComboBox()
        self.categoria.addItem(TODAS_AS_CATEGORIAS)
        self.categoria.addItems(self.registro.categorias())
        self.categoria.currentTextChanged.connect(self.atualizar)

        linha = QHBoxLayout()
        linha.setSpacing(tema.ESPACAMENTO)
        linha.addWidget(self.busca, 1)
        linha.addWidget(self.categoria)
        return linha

    def produtos_visiveis(self) -> list[Produto]:
        """Devolve os produtos que passam pelo filtro e pela busca atuais."""
        categoria = self.categoria.currentText()
        termo = self.busca.text()
        return [
            produto
            for produto in self.registro.ordenados()
            if (categoria == TODAS_AS_CATEGORIAS or produto.categoria == categoria)
            and corresponde(produto, termo)
        ]

    def atualizar(self) -> None:
        """Reconstrói a grade a partir do registro e dos filtros."""
        self._esvaziar_grade()

        visiveis = self.produtos_visiveis()
        cards: list[QWidget] = []

        for produto in visiveis:
            card = CardDeProduto(produto)
            card.escolhido.connect(self.produto_escolhido)
            cards.append(card)

        # As falhas ficam ao final e ignoram os filtros: um produto quebrado
        # não tem manifesto para casar com busca nenhuma, e escondê-lo seria
        # exatamente o comportamento que a seção 5 proíbe.
        for falha in self.registro.falhas.values():
            card_falha = CardDeFalha(falha)
            card_falha.traceback_pedido.connect(self.mostrar_traceback)
            cards.append(card_falha)

        for posicao, card in enumerate(cards):
            self._grade.addWidget(card, posicao // COLUNAS, posicao % COLUNAS)

        self._vazio.setVisible(not cards)
        _log.debug("biblioteca exibindo %d card(s)", len(cards))

    def _esvaziar_grade(self) -> None:
        """Remove e destrói todos os cards da grade."""
        while self._grade.count():
            item = self._grade.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

    def mostrar_traceback(self, id_da_falha: str) -> None:
        """Abre o diálogo com o traceback de uma falha.

        Args:
            id_da_falha: Nome do pacote que falhou ao carregar.
        """
        falha = self.registro.falhas.get(id_da_falha)
        if falha is None:
            return
        DialogoDeTraceback(falha, self).exec()

    def quantidade_de_cards(self) -> int:
        """Total de cards na grade, incluindo os de falha."""
        return self._grade.count()

    def cards(self) -> list[QWidget]:
        """Devolve os cards atualmente na grade, na ordem em que aparecem."""
        return [
            self._grade.itemAt(i).widget()
            for i in range(self._grade.count())
            if self._grade.itemAt(i).widget() is not None
        ]
