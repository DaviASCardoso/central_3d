"""Núcleo da Central.

Faz descoberta de produtos, validação de parâmetros, orquestração da geração,
cache, tesselagem, checagem de qualidade da malha e exportação. Conhece o
contrato e conhece geometria, mas não conhece interface — toda a lógica de
valor mora aqui e por isso é testável sem abrir uma janela.
"""

from __future__ import annotations

from central.nucleo.registro import ProdutoComFalha, Registro, descobrir

__all__ = ["ProdutoComFalha", "Registro", "descobrir"]
