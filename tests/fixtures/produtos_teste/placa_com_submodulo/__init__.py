"""Produto de teste válido que usa import relativo, como os produtos reais."""

from __future__ import annotations

from central.contrato import Param, Produto, TipoParam

from .geometria import gerar

MANIFESTO = Produto(
    id="placa_com_submodulo",
    nome="Placa com Submódulo",
    versao="2.1.0",
    descricao="Produto de teste que separa a geometria num submódulo.",
    categoria="Papelaria",
    tags=("placa",),
    params=(
        Param(chave="nome", rotulo="Nome", tipo=TipoParam.TEXTO, padrao="Ana"),
    ),
    gerar=gerar,
)
