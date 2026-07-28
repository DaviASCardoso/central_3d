"""Produto de teste válido, sem submódulos."""

from __future__ import annotations

from typing import Any

from central.contrato import Param, Produto, TipoParam


def gerar(valores: dict[str, Any]) -> dict[str, Any]:
    """Devolve os valores recebidos; geometria de verdade não interessa aqui."""
    return valores


MANIFESTO = Produto(
    id="cubo_simples",
    nome="Cubo Simples",
    versao="1.0.0",
    descricao="Produto de teste sem submódulos.",
    categoria="Teste",
    tags=("cubo", "teste"),
    params=(
        Param(chave="lado", rotulo="Lado", tipo=TipoParam.DECIMAL, padrao=10.0),
    ),
    gerar=gerar,
)
