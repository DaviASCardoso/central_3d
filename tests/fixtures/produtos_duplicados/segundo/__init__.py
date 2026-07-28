"""Segundo produto a declarar o id `colidido`, que deve virar falha."""

from __future__ import annotations

from typing import Any

from central.contrato import Produto


def gerar(valores: dict[str, Any]) -> dict[str, Any]:
    """Devolve os valores recebidos."""
    return valores


MANIFESTO = Produto(
    id="colidido",
    nome="Segundo",
    versao="1.0.0",
    descricao="Colide com o id do primeiro.",
    categoria="Teste",
    params=(),
    gerar=gerar,
)
