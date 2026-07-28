"""Hierarquia de exceções do núcleo.

A seção 18 do CENTRAL.md proíbe `except` nu: todo erro é capturado por tipo
específico e registrado. Estes tipos existem para que a captura seja específica
sem virar caça a `Exception` genérica.
"""

from __future__ import annotations


class ErroCentral(Exception):
    """Base de todos os erros próprios da Central."""


class ErroDeDescoberta(ErroCentral):
    """O diretório de produtos não pôde ser varrido."""


class ErroDeValidacao(ErroCentral):
    """Os valores recebidos não satisfazem a declaração de parâmetros."""


class ErroDeGeracao(ErroCentral):
    """A função `gerar` de um produto falhou ou devolveu algo inutilizável."""


class ErroDeGeometria(ErroCentral):
    """Uma operação geométrica do núcleo falhou."""


class ErroDeExportacao(ErroCentral):
    """A escrita do arquivo de saída falhou."""
