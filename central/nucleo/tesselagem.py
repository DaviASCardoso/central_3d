"""Conversão de sólido B-rep em malha triangular.

O desvio linear é **absoluto, em milímetros**, o que exige `isRelative=False`
na chamada ao OCCT. Com o padrão `isRelative=True` o valor viraria fração do
tamanho da aresta e os números da seção 6 do CENTRAL.md perderiam o sentido.

O OCCT emite a triangulação por face, com vértices duplicados nas costuras.
Sem soldar os vértices a malha nunca é estanque e o portão de qualidade
reprovaria tudo. A soldagem acontece aqui, uma vez, e não no portão.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Final

import numpy as np
import trimesh
from build123d import Shape
from OCP.BRep import BRep_Tool  # type: ignore[import-untyped]
from OCP.BRepMesh import BRepMesh_IncrementalMesh  # type: ignore[import-untyped]
from OCP.BRepTools import BRepTools  # type: ignore[import-untyped]
from OCP.TopAbs import TopAbs_Orientation  # type: ignore[import-untyped]
from OCP.TopLoc import TopLoc_Location  # type: ignore[import-untyped]

from central.log import obter
from central.nucleo.erros import ErroDeGeometria

_log = obter(__name__)


class NivelTesselagem(StrEnum):
    """Qual das duas malhas se quer.

    O preview precisa ser leve o bastante para atualizar em tempo real; a
    exportação precisa ser fiel o bastante para imprimir. Ver a seção 6.
    """

    PREVIEW = "preview"
    EXPORTACAO = "exportacao"


@dataclass(frozen=True, slots=True)
class Desvio:
    """Tolerâncias de uma tesselagem.

    Attributes:
        linear: Desvio linear máximo em milímetros, absoluto.
        angular: Desvio angular máximo em radianos.
    """

    linear: float
    angular: float


# Ponto único de calibração. A seção 19 do CENTRAL.md avisa que estes valores
# são ponto de partida razoável, não medida: devem ser ajustados olhando o
# resultado real na viewport e no arquivo exportado.
DESVIOS: Final[dict[NivelTesselagem, Desvio]] = {
    NivelTesselagem.PREVIEW: Desvio(linear=0.08, angular=0.5),
    NivelTesselagem.EXPORTACAO: Desvio(linear=0.015, angular=0.2),
}


def tesselar(
    forma: Shape,
    nivel: NivelTesselagem = NivelTesselagem.PREVIEW,
) -> trimesh.Trimesh:
    """Converte um sólido em malha triangular soldada.

    Args:
        forma: Sólido ou composto do build123d.
        nivel: Qual jogo de tolerâncias usar.

    Returns:
        A malha com vértices soldados, pronta para a viewport ou para o portão
        de qualidade.

    Raises:
        ErroDeGeometria: Se a forma não produz triângulo nenhum.
    """
    desvio = DESVIOS[nivel]
    vertices, triangulos = _triangular(forma, desvio)

    if len(triangulos) == 0:
        raise ErroDeGeometria(f"a forma não produziu triângulos no nível {nivel}")

    malha = trimesh.Trimesh(vertices=vertices, faces=triangulos, process=False)
    malha.merge_vertices()

    # O malhador do OCCT emite triângulos de área zero onde a superfície
    # degenera — o polo de uma esfera é o caso típico. Eles deixam arestas com
    # contagem de faces diferente de dois e fazem `is_watertight` mentir. São
    # artefato da tesselagem, não defeito do produto, então saem aqui em vez de
    # virar aviso no portão de qualidade.
    degeneradas = int((~malha.nondegenerate_faces()).sum())
    if degeneradas:
        malha.update_faces(malha.nondegenerate_faces())
        malha.remove_unreferenced_vertices()
        _log.debug("%d triângulo(s) degenerado(s) descartado(s) da tesselagem", degeneradas)

    _log.debug(
        "tesselagem %s: %d triângulos, %d vértices",
        nivel,
        len(malha.faces),
        len(malha.vertices),
    )
    return malha


def _triangular(forma: Shape, desvio: Desvio) -> tuple[np.ndarray, np.ndarray]:
    """Roda o malhador do OCCT e recolhe vértices e triângulos por face."""
    # O OCCT guarda a triangulação dentro da própria forma e só remalha uma
    # face cuja malha existente seja pior que a pedida. Sem limpar antes,
    # tesselar em EXPORTACAO e depois em PREVIEW devolveria a malha fina — o
    # resultado passaria a depender da ordem das chamadas, o que é veneno para
    # um cache indexado por hash dos parâmetros.
    BRepTools.Clean_s(forma.wrapped)

    BRepMesh_IncrementalMesh(
        theShape=forma.wrapped,
        theLinDeflection=desvio.linear,
        isRelative=False,
        theAngDeflection=desvio.angular,
        isInParallel=True,
    )

    localizacao = TopLoc_Location()
    vertices: list[tuple[float, float, float]] = []
    triangulos: list[tuple[int, int, int]] = []
    deslocamento = 0

    for face in forma.faces():
        triangulacao = BRep_Tool.Triangulation_s(face.wrapped, localizacao)
        if triangulacao is None:
            _log.debug("face sem triangulação, ignorada")
            continue

        transformacao = localizacao.Transformation()
        quantidade = triangulacao.NbNodes()
        for indice in range(1, quantidade + 1):
            ponto = triangulacao.Node(indice).Transformed(transformacao)
            vertices.append((ponto.X(), ponto.Y(), ponto.Z()))

        # Face invertida tem os nós na ordem contrária; corrigir aqui é o que
        # mantém as normais coerentes e o `is_winding_consistent` verdadeiro.
        invertida = face.wrapped.Orientation() == TopAbs_Orientation.TopAbs_REVERSED
        ordem = (1, 3, 2) if invertida else (1, 2, 3)
        for triangulo in triangulacao.Triangles():
            triangulos.append(
                tuple(triangulo.Value(i) + deslocamento - 1 for i in ordem)  # type: ignore[misc]
            )

        deslocamento += quantidade

    return (
        np.array(vertices, dtype=np.float64).reshape(-1, 3),
        np.array(triangulos, dtype=np.int64).reshape(-1, 3),
    )
