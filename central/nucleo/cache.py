"""Cache de geometria.

A chave é um SHA-256 do `id` do produto, da sua `versao`, do nível de
tesselagem e do dicionário de valores serializado de forma canônica,
considerando apenas os parâmetros com `afeta_geometria` verdadeiro. Ver a
seção 6 do CENTRAL.md.

A chave carrega o `id` do produto como prefixo legível. Isso torna trivial
invalidar tudo de um produto no recarregamento a quente, e faz o cache de
disco render nomes de arquivo que um humano consegue inspecionar.
"""

from __future__ import annotations

import hashlib
import json
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any

from central.contrato import Produto
from central.log import obter
from central.nucleo.geracao import ResultadoGeracao
from central.nucleo.tesselagem import NivelTesselagem

_log = obter(__name__)

SEPARADOR = "/"
"""Separa o prefixo de produto do hash dentro da chave."""

ENTRADAS_EM_MEMORIA = 32
"""Quantas gerações manter em memória. Cada uma segura sólidos do OCCT."""


def valores_que_afetam_geometria(
    produto: Produto, valores: dict[str, Any]
) -> dict[str, Any]:
    """Filtra os valores que de fato mudam a geometria.

    Args:
        produto: O manifesto, que declara `afeta_geometria` em cada `Param`.
        valores: Valores já validados e coeridos.

    Returns:
        Apenas os pares cujo parâmetro afeta a geometria, completados com o
        padrão quando ausentes.
    """
    return {
        param.chave: valores.get(param.chave, param.padrao)
        for param in produto.params
        if param.afeta_geometria
    }


def chave(
    produto: Produto,
    valores: dict[str, Any],
    nivel: NivelTesselagem = NivelTesselagem.PREVIEW,
) -> str:
    """Calcula a chave de cache de uma geração.

    Espera valores **já validados**, porque a coerção de tipo é o que garante
    que `3` e `3.0` não produzam chaves diferentes para o mesmo parâmetro.

    Args:
        produto: O manifesto do produto.
        valores: Valores validados dos parâmetros.
        nivel: Nível de tesselagem, que faz parte da identidade da malha.

    Returns:
        A chave no formato `id_do_produto/hash_sha256`.
    """
    conteudo = json.dumps(
        {
            "id": produto.id,
            "versao": produto.versao,
            "nivel": str(nivel),
            "valores": valores_que_afetam_geometria(produto, valores),
        },
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        default=repr,
    )
    digest = hashlib.sha256(conteudo.encode("utf-8")).hexdigest()
    return f"{produto.id}{SEPARADOR}{digest}"


def produto_da_chave(chave_completa: str) -> str:
    """Extrai o `id` do produto de uma chave.

    Args:
        chave_completa: Chave no formato devolvido por `chave`.

    Returns:
        O identificador do produto.
    """
    return chave_completa.split(SEPARADOR, 1)[0]


@dataclass(slots=True)
class Estatisticas:
    """Contagem de acertos e erros de um cache.

    Attributes:
        acertos: Quantas buscas encontraram a entrada.
        erros: Quantas buscas não encontraram.
        descartes: Quantas entradas saíram por limite de tamanho.
    """

    acertos: int = 0
    erros: int = 0
    descartes: int = 0

    @property
    def taxa_de_acerto(self) -> float:
        """Fração de buscas que acertaram, ou zero se não houve busca."""
        total = self.acertos + self.erros
        return self.acertos / total if total else 0.0


class CacheEmMemoria:
    """Cache LRU de gerações completas, incluindo os sólidos do OCCT."""

    def __init__(self, maximo: int = ENTRADAS_EM_MEMORIA) -> None:
        """Cria o cache vazio.

        Args:
            maximo: Quantas entradas manter antes de descartar a mais antiga.
        """
        self._maximo = maximo
        self._entradas: OrderedDict[str, ResultadoGeracao] = OrderedDict()
        self.estatisticas = Estatisticas()

    def obter(self, chave_completa: str) -> ResultadoGeracao | None:
        """Busca uma geração e a promove a mais recentemente usada.

        Args:
            chave_completa: A chave calculada por `chave`.

        Returns:
            A geração guardada, ou `None` se não há entrada.
        """
        resultado = self._entradas.get(chave_completa)
        if resultado is None:
            self.estatisticas.erros += 1
            return None
        self._entradas.move_to_end(chave_completa)
        self.estatisticas.acertos += 1
        return resultado

    def guardar(self, chave_completa: str, resultado: ResultadoGeracao) -> None:
        """Guarda uma geração, descartando a mais antiga se preciso.

        Args:
            chave_completa: A chave calculada por `chave`.
            resultado: A geração a guardar.
        """
        self._entradas[chave_completa] = resultado
        self._entradas.move_to_end(chave_completa)
        while len(self._entradas) > self._maximo:
            descartada, _ = self._entradas.popitem(last=False)
            self.estatisticas.descartes += 1
            _log.debug("cache em memória descartou %s", descartada)

    def invalidar_produto(self, id_produto: str) -> int:
        """Remove todas as entradas de um produto.

        É o que o recarregamento a quente chama quando um módulo muda: o
        código da geometria mudou sem que a versão do manifesto precisasse
        mudar, então tudo daquele produto vira lixo.

        Args:
            id_produto: Identificador do produto.

        Returns:
            Quantas entradas foram removidas.
        """
        alvos = [c for c in self._entradas if produto_da_chave(c) == id_produto]
        for alvo in alvos:
            del self._entradas[alvo]
        if alvos:
            _log.info("cache invalidado para o produto '%s': %d entrada(s)", id_produto, len(alvos))
        return len(alvos)

    def limpar(self) -> None:
        """Esvazia o cache, preservando as estatísticas."""
        self._entradas.clear()

    def __len__(self) -> int:
        """Quantidade de entradas guardadas."""
        return len(self._entradas)

    def __contains__(self, chave_completa: object) -> bool:
        """Diz se uma chave está guardada, sem contar como busca."""
        return chave_completa in self._entradas

    def chaves(self) -> list[str]:
        """Devolve as chaves guardadas, da menos à mais recentemente usada."""
        return list(self._entradas)
