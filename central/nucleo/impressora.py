"""Características físicas da impressora alvo.

Números que aparecem em três lugares — a mesa desenhada na viewport, o portão
de qualidade e o teste genérico de produtos — e que por isso não podem viver
espalhados como literal.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True, slots=True)
class VolumeDeConstrucao:
    """Caixa útil da impressora, em milímetros.

    Attributes:
        x: Largura da mesa.
        y: Profundidade da mesa.
        z: Altura máxima imprimível.
    """

    x: float
    y: float
    z: float

    def cabe(self, dimensoes: tuple[float, float, float]) -> bool:
        """Diz se uma peça cabe no volume.

        Args:
            dimensoes: Tamanho da peça em milímetros, na ordem x, y, z.

        Returns:
            Verdadeiro se nenhuma dimensão excede a caixa.
        """
        largura, profundidade, altura = dimensoes
        return largura <= self.x and profundidade <= self.y and altura <= self.z


VOLUME_DE_CONSTRUCAO: Final = VolumeDeConstrucao(x=256.0, y=256.0, z=256.0)
"""Volume da Bambu Lab série X1 e P1, conforme a seção 7 do CENTRAL.md."""

PASSO_DA_GRADE: Final[float] = 10.0
"""Espaçamento da marcação da mesa desenhada na viewport, em milímetros."""

DIAMETRO_DO_BICO: Final[float] = 0.4
"""Bico assumido ao codificar os limites físicos da seção 8, em milímetros."""
