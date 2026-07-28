"""Geometria da placa com nome em relevo.

Três exigências pesam sobre `gerar`, e valem para todo produto da Central:

1. **Pura.** A mesma entrada produz sempre a mesma saída, sem efeito colateral.
   Sem I/O, sem estado global, sem randomização não semeada.
2. **Determinística inclusive na ordem das operações.** O cache é indexado por
   hash dos parâmetros; geometria que varia entre chamadas idênticas corrompe
   o cache em silêncio.
3. **Sem confiar na física dos valores recebidos.** Ela pode assumir que os
   tipos e as faixas declaradas em `Param` foram respeitados, mas se uma
   combinação legal produzir parede fina demais, cabe ao `validar` do manifesto
   recusar antes — não a `gerar` improvisar.

Este módulo importa apenas de `central.contrato` e das bibliotecas de
geometria, como manda a seção 18 do CENTRAL.md.
"""

from __future__ import annotations

from typing import Any

from build123d import Box, Part, Pos, chamfer

from central.contrato import Corpo, Resultado
from central.nucleo.helpers import texto_solido

MARGEM_LATERAL = 6.0
"""Folga mínima em milímetros entre o texto e a borda da placa, por lado."""

FRACAO_MAXIMA_DO_TEXTO = 0.82
"""Quanto da largura da placa o texto pode ocupar antes de ser comprimido."""


def gerar(valores: dict[str, Any]) -> Resultado:
    """Constrói uma placa retangular com o nome em relevo na face superior.

    Args:
        valores: Valores já validados e coeridos pelo núcleo, com as chaves
            declaradas em `MANIFESTO.params`.

    Returns:
        O resultado com um único corpo chamado `placa` e, quando o nome não
        coube na largura pedida, um aviso dizendo o quanto ele foi comprimido.
    """
    nome: str = valores["nome"]
    largura: float = valores["largura"]
    profundidade: float = valores["profundidade"]
    espessura: float = valores["espessura"]
    altura_texto: float = valores["altura_texto"]
    relevo: float = valores["relevo"]
    chanfro: float = valores["chanfro"]
    fonte: str = valores["fonte"]
    cor: str = valores["cor"]

    avisos: list[str] = []
    metadados: dict[str, Any] = {"caracteres": len(nome)}

    texto = texto_solido(nome, fonte, altura_texto, relevo)

    # O texto é gerado uma vez em tamanho nominal e comprimido depois, em vez
    # de gerado várias vezes buscando o tamanho que cabe: assim o helper
    # memoizado é reaproveitado quando só a largura da placa muda.
    disponivel = largura - 2 * MARGEM_LATERAL
    largura_texto = texto.bounding_box().size.X
    if largura_texto > disponivel:
        fator = disponivel / largura_texto
        # Comprimir só em X preserva a altura da letra e o relevo exatos, que
        # são justamente as duas medidas com piso físico na seção 8.
        texto = texto.scale((fator, 1.0, 1.0))
        avisos.append(
            f"o nome não coube na largura e foi comprimido em "
            f"{(1 - fator) * 100:.0f}%"
        )
        metadados["fator_de_compressao"] = round(fator, 4)

    corpo = Box(largura, profundidade, espessura)
    if chanfro > 0:
        verticais = corpo.edges().filter_by(lambda a: a.length == espessura)
        corpo = chamfer(verticais, length=chanfro)

    # A placa nasce centrada na origem, então sua face superior está em
    # espessura/2 e o texto assenta ali.
    placa: Part = corpo + Pos(0, 0, espessura / 2) * texto

    return Resultado(
        corpos=[Corpo(nome="placa", forma=placa, cor=cor)],
        avisos=avisos,
        metadados=metadados,
    )


def validar(valores: dict[str, Any]) -> list[str]:
    """Recusa combinações legais de valores que produziriam peça ruim.

    A defesa contra parede fina mora aqui, e não na Central, porque é aqui que
    se conhece a geometria. Ver a seção 8 do CENTRAL.md.

    Args:
        valores: Valores já validados individualmente contra cada `Param`.

    Returns:
        Lista de mensagens de erro; vazia significa válido.
    """
    erros: list[str] = []

    nome: str = valores["nome"]
    largura: float = valores["largura"]
    profundidade: float = valores["profundidade"]
    espessura: float = valores["espessura"]
    altura_texto: float = valores["altura_texto"]
    chanfro: float = valores["chanfro"]

    if not nome.strip():
        erros.append("o nome não pode ser vazio")

    if altura_texto + 2 * MARGEM_LATERAL > profundidade:
        erros.append(
            f"o texto de {altura_texto:g} mm não cabe numa placa de "
            f"{profundidade:g} mm de profundidade; aumente a profundidade para "
            f"ao menos {altura_texto + 2 * MARGEM_LATERAL:g} mm"
        )

    if chanfro * 2 >= min(largura, profundidade):
        erros.append(
            f"o chanfro de {chanfro:g} mm consome toda a placa; use menos de "
            f"{min(largura, profundidade) / 2:g} mm"
        )

    if chanfro >= espessura:
        erros.append(
            f"o chanfro de {chanfro:g} mm é maior que a espessura de "
            f"{espessura:g} mm e cortaria a placa ao meio"
        )

    # Com bico de 0,4 mm, traço de texto abaixo de 0,8 mm some. A altura de
    # fonte que garante isso depende do desenho da letra; 4 mm é o piso seguro
    # para as fontes de interface, e abaixo disso o texto vira borrão.
    if largura > 0 and len(nome) > 0:
        largura_por_caractere = (largura - 2 * MARGEM_LATERAL) / len(nome)
        if largura_por_caractere < 1.6:
            erros.append(
                f"{len(nome)} caracteres em {largura:g} mm deixam "
                f"{largura_por_caractere:.1f} mm por letra, e o traço sairia "
                "abaixo de 0,8 mm; use menos letras ou uma placa mais larga"
            )

    return erros
