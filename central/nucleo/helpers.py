"""Utilitários de geometria oferecidos pela Central aos produtos.

O único que os produtos precisam conhecer é `texto_solido`. Converter texto em
contorno vetorial no OCCT é caro, e num produto de nome personalizado é
justamente a operação repetida a cada ajuste de altura ou diâmetro. O helper é
memoizado, de modo que mudar o diâmetro do porta-lápis deixa de recomputar as
letras. Ver a seção 6 do CENTRAL.md.

O resto é usado pelo pipeline de geração, não pelos produtos.
"""

from __future__ import annotations

from functools import lru_cache

from build123d import Align, Compound, Location, Text, extrude
from OCP.Font import Font_FontMgr  # type: ignore[import-untyped]

from central.log import obter
from central.nucleo.erros import ErroDeGeometria

_log = obter(__name__)

TAMANHO_DO_CACHE_DE_TEXTO = 256
"""Quantas combinações de texto memoizar. Cada entrada é um sólido do OCCT."""


@lru_cache(maxsize=1)
def fontes_disponiveis() -> frozenset[str]:
    """Devolve os nomes de fonte que o OCCT enxerga nesta máquina.

    Returns:
        Conjunto dos nomes de família de fonte registrados no gestor do OCCT.
    """
    gestor = Font_FontMgr.GetInstance_s()
    nomes = {
        fonte.FontName().ToCString()
        for fonte in gestor.GetAvailableFonts()
    }
    _log.debug("%d fontes disponíveis no gestor do OCCT", len(nomes))
    return frozenset(nomes)


def conferir_fonte(fonte: str) -> None:
    """Recusa uma fonte que o OCCT substituiria em silêncio.

    Fonte inexistente não levanta erro no OCCT: o gestor troca por Arial e
    apenas emite um aviso. Isso quebraria a exigência de determinismo da seção
    4, porque a mesma entrada produziria geometria diferente em máquinas com
    conjuntos de fontes distintos, corrompendo o cache indexado por hash dos
    parâmetros sem nenhum sinal.

    Args:
        fonte: Nome da família de fonte, como "Arial".

    Raises:
        ErroDeGeometria: Se a fonte não está disponível nesta máquina.
    """
    disponiveis = fontes_disponiveis()
    if fonte in disponiveis:
        return
    parecidas = sorted(n for n in disponiveis if fonte.lower() in n.lower())
    sugestao = f" Parecidas: {', '.join(parecidas[:5])}." if parecidas else ""
    raise ErroDeGeometria(
        f"a fonte {fonte!r} não existe nesta máquina e o OCCT a substituiria "
        f"em silêncio, quebrando o determinismo.{sugestao}"
    )


@lru_cache(maxsize=TAMANHO_DO_CACHE_DE_TEXTO)
def texto_solido(
    texto: str,
    fonte: str,
    tamanho: float,
    espessura: float,
) -> Compound:
    """Devolve o texto como sólido extrudado, memoizado pela tupla exata.

    O sólido volta centrado na origem em X e Y, com a base em Z igual a zero,
    para que o produto o posicione com uma translação simples.

    Como o resultado é compartilhado entre chamadas, ele **não deve ser
    mutado**. Operações do build123d como translação e booleana devolvem
    objetos novos e são seguras.

    Args:
        texto: O texto a gravar. Não pode ser vazio.
        fonte: Nome da família de fonte, que precisa existir nesta máquina.
        tamanho: Altura nominal da fonte em milímetros.
        espessura: Altura da extrusão em milímetros, o relevo da letra.

    Returns:
        O sólido do texto.

    Raises:
        ErroDeGeometria: Se o texto é vazio, a fonte não existe, alguma medida
            não é positiva, ou o contorno resultante não tem área.
    """
    if not texto.strip():
        raise ErroDeGeometria("texto vazio não produz sólido")
    if tamanho <= 0:
        raise ErroDeGeometria(f"tamanho de fonte precisa ser positivo, veio {tamanho}")
    if espessura <= 0:
        raise ErroDeGeometria(f"espessura precisa ser positiva, veio {espessura}")
    conferir_fonte(fonte)

    contorno = Text(
        txt=texto,
        font_size=tamanho,
        font=fonte,
        align=(Align.CENTER, Align.CENTER),
    )
    if not contorno.faces():
        raise ErroDeGeometria(
            f"o texto {texto!r} na fonte {fonte!r} não produziu contorno com área"
        )

    solido = extrude(contorno, amount=espessura)
    _log.debug("texto %r gerado em %s, %d faces", texto, fonte, len(solido.faces()))
    return solido


def dimensoes(forma: Compound) -> tuple[float, float, float]:
    """Devolve as dimensões do bounding box em milímetros.

    Args:
        forma: Qualquer sólido ou composto do build123d.

    Returns:
        A tupla `(x, y, z)` com o tamanho em cada eixo.
    """
    tamanho = forma.bounding_box().size
    return (tamanho.X, tamanho.Y, tamanho.Z)


def assentar_na_mesa(forma: Compound) -> Compound:
    """Translada a forma para que ela caia assentada e centralizada na mesa.

    A menor cota em Z vai para exatamente zero e o centro do bounding box em XY
    vai para a origem. É o último passo da orientação, aplicado depois da
    transformação declarada no manifesto. Ver a seção 6 do CENTRAL.md.

    Args:
        forma: A forma já orientada na posição de impressão.

    Returns:
        Uma forma nova, transladada. A original não é modificada.
    """
    caixa = forma.bounding_box()
    return Location((-caixa.center().X, -caixa.center().Y, -caixa.min.Z)) * forma
