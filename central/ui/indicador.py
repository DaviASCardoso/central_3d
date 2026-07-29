"""Indicador discreto de geração em andamento.

A seção 11 do CENTRAL.md é explícita: nunca um spinner que cobre a tela, nunca
a viewport ficando vazia. Enquanto o worker trabalha, a peça anterior
permanece visível com opacidade reduzida e este indicador aparece no canto.
"""

from __future__ import annotations

import math

from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPaintEvent
from PySide6.QtWidgets import QWidget

from central.ui import tema

TAMANHO = 18
MARGEM = 14
INTERVALO_EM_MS = 60
PONTOS = 8


class IndicadorDeGeracao(QWidget):
    """Anel de pontinhos que gira no canto da viewport."""

    def __init__(self, pai: QWidget | None = None) -> None:
        """Cria o indicador já escondido.

        Args:
            pai: Widget pai, tipicamente a viewport.
        """
        super().__init__(pai)
        self.setFixedSize(TAMANHO, TAMANHO)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.hide()

        self._fase = 0
        self._temporizador = QTimer(self)
        self._temporizador.setInterval(INTERVALO_EM_MS)
        self._temporizador.timeout.connect(self._avancar)

    def iniciar(self) -> None:
        """Mostra o indicador e começa a animação."""
        self.reposicionar()
        self.show()
        self.raise_()
        self._temporizador.start()

    def parar(self) -> None:
        """Para a animação e esconde o indicador."""
        self._temporizador.stop()
        self.hide()

    def esta_ativo(self) -> bool:
        """Diz se o indicador está animando."""
        return self._temporizador.isActive()

    def reposicionar(self) -> None:
        """Encosta o indicador no canto superior direito do pai."""
        pai = self.parentWidget()
        if pai is None:
            return
        self.move(QPoint(pai.width() - TAMANHO - MARGEM, MARGEM))

    def _avancar(self) -> None:
        self._fase = (self._fase + 1) % PONTOS
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 -- nome do Qt
        """Desenha o anel de pontinhos."""
        del event
        pintor = QPainter(self)
        pintor.setRenderHint(QPainter.RenderHint.Antialiasing)
        pintor.setPen(Qt.PenStyle.NoPen)

        base = QColor(tema.paleta_atual().destaque)
        centro = TAMANHO / 2
        raio = TAMANHO / 2 - 3
        tamanho_do_ponto = 2.4

        for indice in range(PONTOS):
            angulo = 2 * math.pi * indice / PONTOS
            x = centro + raio * math.cos(angulo)
            y = centro + raio * math.sin(angulo)
            opacidade = 0.15 + 0.85 * (((indice - self._fase) % PONTOS) / PONTOS)
            cor = QColor(base)
            cor.setAlphaF(opacidade)
            pintor.setBrush(cor)
            pintor.drawEllipse(
                QPoint(int(x), int(y)), int(tamanho_do_ponto), int(tamanho_do_ponto)
            )
