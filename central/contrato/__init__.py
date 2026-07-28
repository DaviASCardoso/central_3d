"""Contrato entre a Central e os módulos de produto.

Um módulo de produto importa daqui e de nada mais da Central. Ver
`CONTRATO.md` na raiz do repositório para o extrato canônico, e a seção 4 do
`CENTRAL.md` para o racional.
"""

from __future__ import annotations

from central.contrato.tipos import Corpo, Param, Produto, Resultado, TipoParam

__all__ = ["Corpo", "Param", "Produto", "Resultado", "TipoParam"]
