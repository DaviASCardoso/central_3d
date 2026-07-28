"""Tema da interface.

Tema escuro por padrão, respeitando a preferência do sistema, tipografia do
próprio sistema operacional em vez de fonte embutida, e densidade média. A cor
de destaque é usada com parcimônia, reservada para o estado ativo e para o
botão primário de cada tela. Ver a seção 11 do CENTRAL.md.

O polimento completo do visual é da entrega 7; aqui está o mínimo para a
janela não parecer quebrada.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

from central.log import obter

_log = obter(__name__)


class Esquema(StrEnum):
    """Qual variante de cor usar."""

    ESCURO = "escuro"
    CLARO = "claro"


@dataclass(frozen=True, slots=True)
class Paleta:
    """Cores de uma variante do tema, em hexadecimal.

    Attributes:
        fundo: Fundo das janelas e dos painéis.
        fundo_elevado: Fundo de campos, listas e cards, um passo acima.
        borda: Linhas divisórias e contorno de campo.
        texto: Texto normal.
        texto_fraco: Rótulo secundário, unidade, dica.
        texto_desabilitado: Texto de controle inativo.
        destaque: Cor de acento, para estado ativo e botão primário.
        destaque_texto: Texto sobre a cor de acento.
        aviso: Avisos do produto e da checagem de qualidade.
        erro: Falha de validação, de geração e de qualidade.
        viewport: Fundo da cena 3D.
    """

    fundo: str
    fundo_elevado: str
    borda: str
    texto: str
    texto_fraco: str
    texto_desabilitado: str
    destaque: str
    destaque_texto: str
    aviso: str
    erro: str
    viewport: str


ESCURA = Paleta(
    fundo="#1E1F22",
    fundo_elevado="#2B2D30",
    borda="#3C3F41",
    texto="#DFE1E5",
    texto_fraco="#9DA0A8",
    texto_desabilitado="#6B6E76",
    destaque="#4C8DF6",
    destaque_texto="#FFFFFF",
    aviso="#E3B341",
    erro="#F0736A",
    viewport="#26282C",
)

CLARA = Paleta(
    fundo="#F4F5F7",
    fundo_elevado="#FFFFFF",
    borda="#D5D8DE",
    texto="#1F2128",
    texto_fraco="#5C6070",
    texto_desabilitado="#A0A4AE",
    destaque="#2B6FD4",
    destaque_texto="#FFFFFF",
    aviso="#8A6100",
    erro="#B3261E",
    viewport="#E8EAEE",
)

PALETAS: dict[Esquema, Paleta] = {Esquema.ESCURO: ESCURA, Esquema.CLARO: CLARA}

ESPACAMENTO = 8
"""Unidade de espaçamento em pixels. Densidade média: nem CAD, nem web."""

RAIO = 4
"""Arredondamento de canto em pixels."""


def esquema_do_sistema() -> Esquema:
    """Lê a preferência de cor do sistema operacional.

    Returns:
        O esquema preferido; escuro quando o sistema não informa, que é o
        padrão da Central.
    """
    aplicacao = QApplication.instance()
    if aplicacao is None:
        return Esquema.ESCURO
    if aplicacao.styleHints().colorScheme() == Qt.ColorScheme.Light:
        return Esquema.CLARO
    return Esquema.ESCURO


def _montar_palette(paleta: Paleta) -> QPalette:
    """Traduz a paleta da Central para a QPalette do Qt."""
    qt = QPalette()
    grupos = (QPalette.ColorGroup.Active, QPalette.ColorGroup.Inactive)

    for grupo in grupos:
        qt.setColor(grupo, QPalette.ColorRole.Window, QColor(paleta.fundo))
        qt.setColor(grupo, QPalette.ColorRole.Base, QColor(paleta.fundo_elevado))
        qt.setColor(grupo, QPalette.ColorRole.AlternateBase, QColor(paleta.fundo))
        qt.setColor(grupo, QPalette.ColorRole.Button, QColor(paleta.fundo_elevado))
        qt.setColor(grupo, QPalette.ColorRole.WindowText, QColor(paleta.texto))
        qt.setColor(grupo, QPalette.ColorRole.Text, QColor(paleta.texto))
        qt.setColor(grupo, QPalette.ColorRole.ButtonText, QColor(paleta.texto))
        qt.setColor(grupo, QPalette.ColorRole.ToolTipBase, QColor(paleta.fundo_elevado))
        qt.setColor(grupo, QPalette.ColorRole.ToolTipText, QColor(paleta.texto))
        qt.setColor(grupo, QPalette.ColorRole.PlaceholderText, QColor(paleta.texto_fraco))
        qt.setColor(grupo, QPalette.ColorRole.Highlight, QColor(paleta.destaque))
        qt.setColor(
            grupo, QPalette.ColorRole.HighlightedText, QColor(paleta.destaque_texto)
        )
        qt.setColor(grupo, QPalette.ColorRole.Link, QColor(paleta.destaque))

    desabilitado = QPalette.ColorGroup.Disabled
    for papel in (
        QPalette.ColorRole.WindowText,
        QPalette.ColorRole.Text,
        QPalette.ColorRole.ButtonText,
    ):
        qt.setColor(desabilitado, papel, QColor(paleta.texto_desabilitado))

    return qt


def folha_de_estilo(paleta: Paleta) -> str:
    """Monta a folha de estilo que a QPalette sozinha não cobre.

    Args:
        paleta: A variante de cor em uso.

    Returns:
        A folha de estilo em sintaxe Qt.
    """
    return f"""
    QMainWindow, QWidget {{
        font-size: 13px;
    }}
    QTabWidget::pane {{
        border: none;
        border-top: 1px solid {paleta.borda};
    }}
    QTabBar::tab {{
        background: transparent;
        color: {paleta.texto_fraco};
        padding: {ESPACAMENTO}px {ESPACAMENTO * 2}px;
        border: none;
        border-bottom: 2px solid transparent;
    }}
    QTabBar::tab:hover {{
        color: {paleta.texto};
    }}
    QTabBar::tab:selected {{
        color: {paleta.texto};
        border-bottom: 2px solid {paleta.destaque};
    }}
    QGroupBox {{
        border: 1px solid {paleta.borda};
        border-radius: {RAIO}px;
        margin-top: {ESPACAMENTO + 4}px;
        padding-top: {ESPACAMENTO}px;
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        left: {ESPACAMENTO}px;
        color: {paleta.texto_fraco};
    }}
    QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QPlainTextEdit, QTextEdit {{
        background: {paleta.fundo_elevado};
        border: 1px solid {paleta.borda};
        border-radius: {RAIO}px;
        padding: {ESPACAMENTO // 2}px {ESPACAMENTO}px;
        selection-background-color: {paleta.destaque};
    }}
    QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
        border: 1px solid {paleta.destaque};
    }}
    QPushButton {{
        background: {paleta.fundo_elevado};
        border: 1px solid {paleta.borda};
        border-radius: {RAIO}px;
        padding: {ESPACAMENTO // 2}px {ESPACAMENTO * 2}px;
    }}
    QPushButton:hover {{
        border: 1px solid {paleta.destaque};
    }}
    QPushButton:disabled {{
        color: {paleta.texto_desabilitado};
        border: 1px solid {paleta.borda};
    }}
    QPushButton[primario="true"] {{
        background: {paleta.destaque};
        color: {paleta.destaque_texto};
        border: 1px solid {paleta.destaque};
    }}
    QToolBar {{
        border: none;
        border-bottom: 1px solid {paleta.borda};
        spacing: {ESPACAMENTO // 2}px;
        padding: {ESPACAMENTO // 2}px;
    }}
    QStatusBar {{
        border-top: 1px solid {paleta.borda};
        color: {paleta.texto_fraco};
    }}
    QScrollArea {{
        border: none;
    }}
    QSplitter::handle {{
        background: {paleta.borda};
    }}
    """


_esquema_aplicado: Esquema | None = None


def aplicar(aplicacao: QApplication, esquema: Esquema | None = None) -> Esquema:
    """Aplica o tema à aplicação inteira.

    A tipografia fica a cargo do sistema operacional: nenhuma fonte é embutida
    nem forçada, apenas o tamanho é normalizado pela folha de estilo.

    Args:
        aplicacao: A instância de `QApplication`.
        esquema: Qual variante usar. Por padrão, a preferência do sistema.

    Returns:
        O esquema efetivamente aplicado.
    """
    global _esquema_aplicado

    escolhido = esquema or esquema_do_sistema()
    paleta = PALETAS[escolhido]

    aplicacao.setStyle("Fusion")
    aplicacao.setPalette(_montar_palette(paleta))
    aplicacao.setStyleSheet(folha_de_estilo(paleta))

    _esquema_aplicado = escolhido
    _log.debug("tema %s aplicado", escolhido)
    return escolhido


def esquema_atual() -> Esquema:
    """Devolve o esquema em vigor, ou a preferência do sistema se nenhum foi aplicado."""
    return _esquema_aplicado or esquema_do_sistema()


def paleta_atual() -> Paleta:
    """Devolve a paleta do esquema em vigor.

    Returns:
        A paleta em uso, para quem precisa de cor fora da folha de estilo —
        tipicamente a viewport, que pinta com VTK e não com Qt.
    """
    return PALETAS[esquema_atual()]
