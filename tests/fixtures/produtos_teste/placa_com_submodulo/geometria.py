"""Submódulo importado relativamente pelo pacote do produto."""

from __future__ import annotations

from typing import Any


def gerar(valores: dict[str, Any]) -> dict[str, Any]:
    """Devolve os valores recebidos, marcando a origem."""
    return {**valores, "origem": "submodulo"}
