"""Pipeline de geração.

Toda geração passa pelo mesmo caminho: validar, gerar, normalizar, orientar,
tesselar. Esta é a versão síncrona; o worker com cancelamento entra na entrega
3 e reaproveita as mesmas etapas. Ver a seção 6 do CENTRAL.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import trimesh
from build123d import Compound, Location, Shape

from central.contrato import Corpo, Produto, Resultado
from central.log import obter
from central.nucleo.erros import ErroDeGeracao, ErroDeValidacao
from central.nucleo.helpers import dimensoes
from central.nucleo.tesselagem import NivelTesselagem, tesselar
from central.nucleo.validacao import ResultadoValidacao, validar

_log = obter(__name__)

PREFIXO_CORPO_ANONIMO = "corpo"
"""Prefixo dos nomes atribuídos quando o produto não nomeia seus corpos."""


@dataclass(slots=True)
class ResultadoGeracao:
    """Tudo que uma geração bem-sucedida produz.

    Attributes:
        resultado: Os corpos já orientados e assentados na mesa.
        malhas: Uma malha por corpo, indexada pelo nome do corpo.
        valores: Os valores validados e coeridos que geraram este resultado.
        nivel: Em que nível de tesselagem as malhas foram feitas.
        dimensoes: Tamanho do conjunto em milímetros, na ordem x, y, z.
        avisos: Mensagens do produto dirigidas ao operador.
    """

    resultado: Resultado
    malhas: dict[str, trimesh.Trimesh]
    valores: dict[str, Any]
    nivel: NivelTesselagem
    dimensoes: tuple[float, float, float]
    avisos: list[str] = field(default_factory=list)


def normalizar(saida: Any) -> Resultado:
    """Converte qualquer forma de retorno de `gerar` num `Resultado`.

    O produto pode devolver um sólido solto, uma lista de sólidos, uma lista de
    `Corpo` ou um `Resultado` completo. Corpos sem nome recebem `corpo_1`,
    `corpo_2` e assim por diante.

    Args:
        saida: O que a função `gerar` do produto devolveu.

    Returns:
        O resultado normalizado, sempre com ao menos um corpo.

    Raises:
        ErroDeGeracao: Se a saída é vazia ou de um tipo que não se reconhece.
    """
    if isinstance(saida, Resultado):
        resultado = saida
    elif isinstance(saida, Corpo):
        resultado = Resultado(corpos=[saida])
    elif isinstance(saida, Shape):
        resultado = Resultado(corpos=[Corpo(nome="", forma=saida)])
    elif isinstance(saida, (list, tuple)):
        resultado = Resultado(corpos=[_como_corpo(item) for item in saida])
    else:
        raise ErroDeGeracao(
            f"gerar devolveu {type(saida).__name__}, que não é sólido, lista de "
            "sólidos, Corpo nem Resultado"
        )

    if not resultado.corpos:
        raise ErroDeGeracao("gerar devolveu um resultado sem nenhum corpo")

    _nomear_anonimos(resultado.corpos)
    return resultado


def _como_corpo(item: Any) -> Corpo:
    """Converte um elemento de lista em `Corpo`."""
    if isinstance(item, Corpo):
        return item
    if isinstance(item, Shape):
        return Corpo(nome="", forma=item)
    raise ErroDeGeracao(
        f"a lista devolvida por gerar contém {type(item).__name__}, "
        "que não é sólido nem Corpo"
    )


def _nomear_anonimos(corpos: list[Corpo]) -> None:
    """Dá nome sequencial aos corpos que vieram sem, preservando os nomeados."""
    usados = {corpo.nome for corpo in corpos if corpo.nome}
    proximo = 1
    for corpo in corpos:
        if corpo.nome:
            continue
        while f"{PREFIXO_CORPO_ANONIMO}_{proximo}" in usados:
            proximo += 1
        corpo.nome = f"{PREFIXO_CORPO_ANONIMO}_{proximo}"
        usados.add(corpo.nome)
        proximo += 1


def orientar(resultado: Resultado, produto: Produto) -> Resultado:
    """Põe a peça na posição de impressão, assentada e centralizada.

    Aplica a transformação declarada no manifesto e depois translada o
    **conjunto** — não cada corpo isoladamente — para que a menor cota em Z
    fique em zero e o centro do bounding box em XY fique na origem. Mover cada
    corpo por conta própria destruiria o encaixe entre tampa e base.

    Args:
        resultado: Os corpos como o produto os devolveu.
        produto: O manifesto, de onde sai a transformação de orientação.

    Returns:
        O mesmo resultado, com as formas substituídas pelas orientadas.

    Raises:
        ErroDeGeracao: Se o conjunto não tem bounding box utilizável.
    """
    if produto.orientacao is not None:
        for corpo in resultado.corpos:
            corpo.forma = produto.orientacao * corpo.forma

    conjunto = Compound(children=[corpo.forma for corpo in resultado.corpos])
    caixa = conjunto.bounding_box()
    if caixa.size.Z <= 0 and caixa.size.X <= 0 and caixa.size.Y <= 0:
        raise ErroDeGeracao("o conjunto de corpos não tem volume")

    deslocamento = Location((-caixa.center().X, -caixa.center().Y, -caixa.min.Z))
    for corpo in resultado.corpos:
        corpo.forma = deslocamento * corpo.forma

    return resultado


def gerar_sincrono(
    produto: Produto,
    valores: dict[str, Any],
    nivel: NivelTesselagem = NivelTesselagem.PREVIEW,
) -> ResultadoGeracao:
    """Roda o pipeline inteiro e devolve corpos orientados com suas malhas.

    Args:
        produto: O manifesto do produto a gerar.
        valores: Valores crus dos parâmetros, ainda por validar.
        nivel: Nível de tesselagem das malhas devolvidas.

    Returns:
        O resultado da geração, com corpos, malhas e dimensões.

    Raises:
        ErroDeValidacao: Se os valores não passam na validação em duas etapas.
        ErroDeGeracao: Se `gerar` levanta, ou devolve algo inutilizável.
    """
    validacao = validar(produto, valores)
    if not validacao.valido:
        raise ErroDeValidacao("; ".join(validacao.mensagens()))

    resultado = orientar(normalizar(_invocar(produto, validacao)), produto)

    malhas = {corpo.nome: tesselar(corpo.forma, nivel) for corpo in resultado.corpos}
    conjunto = Compound(children=[corpo.forma for corpo in resultado.corpos])

    _log.info(
        "produto '%s' gerado: %d corpo(s), %d triângulo(s) no nível %s",
        produto.id,
        len(resultado.corpos),
        sum(len(malha.faces) for malha in malhas.values()),
        nivel,
    )

    return ResultadoGeracao(
        resultado=resultado,
        malhas=malhas,
        valores=validacao.valores,
        nivel=nivel,
        dimensoes=dimensoes(conjunto),
        avisos=list(resultado.avisos),
    )


def _invocar(produto: Produto, validacao: ResultadoValidacao) -> Any:
    """Chama a função `gerar` do produto, encapsulando qualquer falha dela.

    Erro dentro de um produto jamais derruba a Central e sempre chega ao
    operador com traceback legível — por isso a exceção original é encadeada
    em vez de engolida. Ver a seção 18 do CENTRAL.md.
    """
    try:
        return produto.gerar(validacao.valores)
    except Exception as erro:  # noqa: BLE001 -- falha do produto, não da Central
        raise ErroDeGeracao(
            f"a função gerar do produto '{produto.id}' falhou: "
            f"{type(erro).__name__}: {erro}"
        ) from erro
