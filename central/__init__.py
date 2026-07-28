"""Central — catálogo executável de produtos paramétricos para impressão 3D.

As camadas têm dependência estritamente unidirecional, de cima para baixo:
`contrato` não importa nada do resto, `nucleo` conhece o contrato e geometria,
`servicos` lida com o mundo externo e `ui` só monta widgets. Ver CENTRAL.md,
seção 3.
"""

from __future__ import annotations

__version__ = "0.1.0"

__all__ = ["__version__"]
