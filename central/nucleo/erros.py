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
    """Os valores recebidos não satisfazem a declaração de parâmetros.

    Attributes:
        erros_por_chave: Mensagens indexadas pela chave do parâmetro culpado,
            que é o que permite ao inspetor grifar o campo certo.
    """

    def __init__(
        self, mensagem: str, erros_por_chave: dict[str, list[str]] | None = None
    ) -> None:
        """Cria o erro, opcionalmente carregando os culpados.

        Args:
            mensagem: Resumo legível, já achatado.
            erros_por_chave: Erros indexados por chave de parâmetro.
        """
        super().__init__(mensagem)
        self.erros_por_chave = erros_por_chave or {}


class ErroDeGeracao(ErroCentral):
    """A função `gerar` de um produto falhou ou devolveu algo inutilizável."""


class ErroDeGeometria(ErroCentral):
    """Uma operação geométrica do núcleo falhou."""


class ErroDeExportacao(ErroCentral):
    """A escrita do arquivo de saída falhou."""
