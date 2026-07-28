"""Produto de teste que importa bem mas esquece de expor MANIFESTO."""

from __future__ import annotations

from typing import Any


def gerar(valores: dict[str, Any]) -> dict[str, Any]:
    """Existe, mas nunca é alcançada porque não há manifesto."""
    return valores
