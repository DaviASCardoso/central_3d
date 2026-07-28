"""Primeiro produto a declarar o id `colidido`."""

from __future__ import annotations

from typing import Any

from central.contrato import Produto


def gerar(valores: dict[str, Any]) -> dict[str, Any]:
    """Devolve os valores recebidos."""
    return valores


MANIFESTO = Produto(
    id="colidido",
    nome="Primeiro",
    versao="1.0.0",
    descricao="Chega primeiro na ordem alfabética de pacote.",
    categoria="Teste",
    params=(),
    gerar=gerar,
)
