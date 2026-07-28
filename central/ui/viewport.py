"""Viewport 3D, o único módulo que fala VTK.

Todo o boilerplate do VTK fica concentrado aqui, conforme a seção 2 do
CENTRAL.md. O resto da interface conhece apenas `Viewport.mostrar()`.

Um detalhe que muda a percepção de qualidade: quando uma nova malha chega, a
câmera nunca se reposiciona sozinha, exceto no primeiro carregamento do
produto. Trocar de parâmetro e ver a câmera pular destrói o senso de edição
contínua. Por isso a troca de malha é um swap de `vtkPolyData` no mesmo ator,
sem recriar a cena. Ver a seção 7.
"""

from __future__ import annotations

import numpy as np
import trimesh

# O binding precisa ser fixado antes do import do interactor: a detecção
# automática do VTK varre PySide6, PyQt6, PyQt5 e outros nesta ordem, e
# depender dessa ordem é frágil. Ver docs/NOTAS_VERIFICACAO.md.
import vtkmodules.qt

vtkmodules.qt.PyQtImpl = "PySide6"

import vtkmodules.vtkInteractionStyle  # noqa: F401  -- registra os estilos
import vtkmodules.vtkRenderingFreeType  # noqa: F401  -- registra as fontes
import vtkmodules.vtkRenderingOpenGL2  # noqa: F401  -- registra o backend
from PySide6.QtWidgets import QVBoxLayout, QWidget
from vtkmodules.qt.QVTKRenderWindowInteractor import QVTKRenderWindowInteractor
from vtkmodules.vtkCommonCore import vtkPoints, vtkUnsignedCharArray
from vtkmodules.vtkCommonDataModel import vtkCellArray, vtkPolyData
from vtkmodules.vtkFiltersCore import vtkPolyDataNormals
from vtkmodules.vtkInteractionStyle import vtkInteractorStyleTrackballCamera
from vtkmodules.vtkRenderingCore import (
    vtkActor,
    vtkLight,
    vtkPolyDataMapper,
    vtkRenderer,
)

from central.log import obter
from central.nucleo.impressora import PASSO_DA_GRADE, VOLUME_DE_CONSTRUCAO
from central.ui import tema

_log = obter(__name__)

OPACIDADE_NORMAL = 1.0
OPACIDADE_GERANDO = 0.55
"""Enquanto o worker trabalha, a peça anterior permanece visível, mais fraca."""

COR_EXCEDE_VOLUME = (0.94, 0.45, 0.42)
OPACIDADE_EXCEDE_VOLUME = 0.45

_CINZA_GRADE = (90, 93, 100)
_CINZA_PERIMETRO = (150, 154, 163)
_CINZA_VOLUME = (104, 108, 118)


def _hex_para_rgb(cor: str) -> tuple[float, float, float]:
    """Converte `#RRGGBB` em três floats de 0 a 1."""
    texto = cor.lstrip("#")
    if len(texto) == 3:
        texto = "".join(c * 2 for c in texto)
    if len(texto) < 6:
        return (0.54, 0.71, 0.97)
    try:
        return tuple(int(texto[i : i + 2], 16) / 255.0 for i in (0, 2, 4))  # type: ignore[return-value]
    except ValueError:
        _log.warning("cor %r não é hexadecimal; usando a cor padrão", cor)
        return (0.54, 0.71, 0.97)


def malha_para_polydata(malha: trimesh.Trimesh) -> vtkPolyData:
    """Converte uma malha do trimesh em `vtkPolyData`.

    Args:
        malha: A malha tesselada pelo núcleo.

    Returns:
        A geometria pronta para um mapper do VTK.
    """
    pontos = vtkPoints()
    pontos.SetNumberOfPoints(len(malha.vertices))
    for indice, vertice in enumerate(malha.vertices):
        pontos.SetPoint(indice, float(vertice[0]), float(vertice[1]), float(vertice[2]))

    triangulos = vtkCellArray()
    for face in malha.faces:
        triangulos.InsertNextCell(3)
        for indice in face:
            triangulos.InsertCellPoint(int(indice))

    polydata = vtkPolyData()
    polydata.SetPoints(pontos)
    polydata.SetPolys(triangulos)
    return polydata


def _linhas(
    segmentos: list[tuple[tuple[float, float, float], tuple[float, float, float]]],
    cor: tuple[int, int, int],
) -> vtkPolyData:
    """Monta um `vtkPolyData` de segmentos de reta de uma cor só."""
    pontos = vtkPoints()
    celulas = vtkCellArray()
    cores = vtkUnsignedCharArray()
    cores.SetNumberOfComponents(3)

    for inicio, fim in segmentos:
        primeiro = pontos.InsertNextPoint(*inicio)
        segundo = pontos.InsertNextPoint(*fim)
        celulas.InsertNextCell(2)
        celulas.InsertCellPoint(primeiro)
        celulas.InsertCellPoint(segundo)
        cores.InsertNextTuple3(*cor)

    polydata = vtkPolyData()
    polydata.SetPoints(pontos)
    polydata.SetLines(celulas)
    polydata.GetCellData().SetScalars(cores)
    return polydata


class Viewport(QWidget):
    """A cena 3D: mesa, volume de construção e a peça assentada nela."""

    def __init__(self, pai: QWidget | None = None) -> None:
        """Monta a cena com a mesa, o volume e a iluminação.

        Args:
            pai: Widget pai, ou `None`.
        """
        super().__init__(pai)

        self._interactor = QVTKRenderWindowInteractor(self)
        disposicao = QVBoxLayout(self)
        disposicao.setContentsMargins(0, 0, 0, 0)
        disposicao.addWidget(self._interactor)

        self._renderer = vtkRenderer()
        fundo = _hex_para_rgb(tema.paleta_atual().viewport)
        self._renderer.SetBackground(*fundo)
        self._renderer.SetUseDepthPeeling(True)
        self._interactor.GetRenderWindow().AddRenderer(self._renderer)
        self._interactor.SetInteractorStyle(vtkInteractorStyleTrackballCamera())

        self._atores_da_peca: dict[str, vtkActor] = {}
        self._ja_enquadrou = False

        self._montar_mesa()
        self._montar_volume()
        self._montar_iluminacao()
        self._enquadrar_a_mesa()

    # --- cena fixa -------------------------------------------------------

    def _montar_mesa(self) -> None:
        """Desenha a grade da mesa com marcação a cada dez milímetros."""
        largura, profundidade = VOLUME_DE_CONSTRUCAO.x, VOLUME_DE_CONSTRUCAO.y
        meia_largura, meia_profundidade = largura / 2, profundidade / 2

        internos: list[tuple[tuple[float, float, float], tuple[float, float, float]]] = []
        passo = PASSO_DA_GRADE
        quantidade_x = int(largura // passo)
        quantidade_y = int(profundidade // passo)

        for i in range(1, quantidade_x):
            x = -meia_largura + i * passo
            internos.append(((x, -meia_profundidade, 0.0), (x, meia_profundidade, 0.0)))
        for i in range(1, quantidade_y):
            y = -meia_profundidade + i * passo
            internos.append(((-meia_largura, y, 0.0), (meia_largura, y, 0.0)))

        self._ator_grade = self._ator_de_linhas(_linhas(internos, _CINZA_GRADE), 1.0)

        quinas = [
            (-meia_largura, -meia_profundidade, 0.0),
            (meia_largura, -meia_profundidade, 0.0),
            (meia_largura, meia_profundidade, 0.0),
            (-meia_largura, meia_profundidade, 0.0),
        ]
        perimetro = [(quinas[i], quinas[(i + 1) % 4]) for i in range(4)]
        self._ator_perimetro = self._ator_de_linhas(
            _linhas(perimetro, _CINZA_PERIMETRO), 2.0
        )

    def _montar_volume(self) -> None:
        """Desenha as arestas verticais do volume de construção."""
        meia_largura = VOLUME_DE_CONSTRUCAO.x / 2
        meia_profundidade = VOLUME_DE_CONSTRUCAO.y / 2
        altura = VOLUME_DE_CONSTRUCAO.z

        segmentos = []
        quinas = [
            (-meia_largura, -meia_profundidade),
            (meia_largura, -meia_profundidade),
            (meia_largura, meia_profundidade),
            (-meia_largura, meia_profundidade),
        ]
        for x, y in quinas:
            segmentos.append(((x, y, 0.0), (x, y, altura)))
        for indice, (x, y) in enumerate(quinas):
            proximo_x, proximo_y = quinas[(indice + 1) % 4]
            segmentos.append(((x, y, altura), (proximo_x, proximo_y, altura)))

        self._ator_volume = self._ator_de_linhas(_linhas(segmentos, _CINZA_VOLUME), 1.0)

    def _ator_de_linhas(self, polydata: vtkPolyData, espessura: float) -> vtkActor:
        """Cria e adiciona à cena um ator de linhas que não recebe iluminação."""
        mapper = vtkPolyDataMapper()
        mapper.SetInputData(polydata)
        ator = vtkActor()
        ator.SetMapper(mapper)
        ator.GetProperty().SetLineWidth(espessura)
        ator.GetProperty().SetLighting(False)
        ator.PickableOff()
        self._renderer.AddActor(ator)
        return ator

    def _montar_iluminacao(self) -> None:
        """Três luzes direcionais suaves, em vez do padrão do VTK.

        Plástico brilhante demais engana sobre o resultado impresso, então o
        material dos corpos é fosco com leve especularidade e a luz é difusa.
        """
        self._renderer.AutomaticLightCreationOff()
        self._renderer.RemoveAllLights()

        direcoes = ((1.0, 0.6, 1.0), (-1.0, 0.3, 0.6), (0.2, -1.0, 0.4))
        intensidades = (0.85, 0.45, 0.35)

        self._luzes = []
        for direcao, intensidade in zip(direcoes, intensidades, strict=True):
            luz = vtkLight()
            luz.SetLightTypeToCameraLight()
            luz.SetPosition(*direcao)
            luz.SetFocalPoint(0.0, 0.0, 0.0)
            luz.SetIntensity(intensidade)
            luz.SetColor(1.0, 1.0, 1.0)
            self._renderer.AddLight(luz)
            self._luzes.append(luz)

    # --- peça ------------------------------------------------------------

    def mostrar(
        self,
        malhas: dict[str, trimesh.Trimesh],
        cores: dict[str, str] | None = None,
        excede_volume: bool = False,
    ) -> None:
        """Põe uma peça na cena, reaproveitando os atores quando possível.

        Quando os nomes dos corpos não mudam, só o `vtkPolyData` é trocado
        dentro dos atores existentes e a câmera fica onde está. A câmera só se
        reposiciona no primeiro carregamento.

        Args:
            malhas: Malha de cada corpo, indexada pelo nome do corpo.
            cores: Cor hexadecimal de cada corpo. Ausentes usam a cor padrão.
            excede_volume: Se verdadeiro, a peça é pintada de vermelho
                translúcido para sinalizar que não cabe na mesa.
        """
        cores = cores or {}

        for nome in set(self._atores_da_peca) - set(malhas):
            self._renderer.RemoveActor(self._atores_da_peca.pop(nome))

        for nome, malha in malhas.items():
            polydata = malha_para_polydata(malha)
            normais = vtkPolyDataNormals()
            normais.SetInputData(polydata)
            normais.SetFeatureAngle(45.0)
            normais.ConsistencyOn()
            normais.Update()

            ator = self._atores_da_peca.get(nome)
            if ator is None:
                ator = vtkActor()
                ator.SetMapper(vtkPolyDataMapper())
                self._renderer.AddActor(ator)
                self._atores_da_peca[nome] = ator

            ator.GetMapper().SetInputData(normais.GetOutput())
            self._pintar(ator, cores.get(nome, "#8AB4F8"), excede_volume)

        if not self._ja_enquadrou and malhas:
            self.enquadrar_peca()
            self._ja_enquadrou = True

        self.redesenhar()
        _log.debug("viewport mostrando %d corpo(s)", len(malhas))

    def _pintar(self, ator: vtkActor, cor: str, excede_volume: bool) -> None:
        """Aplica o material fosco com leve especularidade a um ator."""
        propriedade = ator.GetProperty()
        if excede_volume:
            propriedade.SetColor(*COR_EXCEDE_VOLUME)
            propriedade.SetOpacity(OPACIDADE_EXCEDE_VOLUME)
        else:
            propriedade.SetColor(*_hex_para_rgb(cor))
            propriedade.SetOpacity(OPACIDADE_NORMAL)
        propriedade.SetDiffuse(0.85)
        propriedade.SetSpecular(0.15)
        propriedade.SetSpecularPower(20.0)
        propriedade.SetAmbient(0.18)

    def definir_visibilidade(self, nome: str, visivel: bool) -> None:
        """Mostra ou esconde um corpo pelo nome.

        Args:
            nome: Nome do corpo, como veio do resultado.
            visivel: Se ele deve aparecer.
        """
        ator = self._atores_da_peca.get(nome)
        if ator is None:
            return
        ator.SetVisibility(visivel)
        self.redesenhar()

    def definir_opacidade_de_geracao(self, gerando: bool) -> None:
        """Esmaece a peça anterior enquanto uma nova geração acontece.

        Args:
            gerando: Verdadeiro enquanto o worker trabalha.
        """
        opacidade = OPACIDADE_GERANDO if gerando else OPACIDADE_NORMAL
        for ator in self._atores_da_peca.values():
            ator.GetProperty().SetOpacity(opacidade)
        self.redesenhar()

    def limpar(self) -> None:
        """Remove a peça da cena, mantendo mesa, volume e câmera."""
        for ator in self._atores_da_peca.values():
            self._renderer.RemoveActor(ator)
        self._atores_da_peca.clear()
        self.redesenhar()

    # --- câmera ----------------------------------------------------------

    def _enquadrar_a_mesa(self) -> None:
        """Põe a câmera numa isométrica que mostra a mesa inteira."""
        camera = self._renderer.GetActiveCamera()
        camera.SetPosition(
            VOLUME_DE_CONSTRUCAO.x * 1.1,
            -VOLUME_DE_CONSTRUCAO.y * 1.1,
            VOLUME_DE_CONSTRUCAO.z * 0.8,
        )
        camera.SetFocalPoint(0.0, 0.0, VOLUME_DE_CONSTRUCAO.z * 0.15)
        camera.SetViewUp(0.0, 0.0, 1.0)
        self._renderer.ResetCameraClippingRange()

    def enquadrar_peca(self) -> None:
        """Enquadra a peça atual, mantendo a direção de vista."""
        if not self._atores_da_peca:
            self._enquadrar_a_mesa()
            return
        limites = self._limites_da_peca()
        self._renderer.ResetCamera(limites)
        self.redesenhar()

    def _limites_da_peca(self) -> tuple[float, float, float, float, float, float]:
        """Bounding box do conjunto de atores da peça."""
        caixas = np.array(
            [ator.GetBounds() for ator in self._atores_da_peca.values()], dtype=float
        )
        return (
            float(caixas[:, 0].min()),
            float(caixas[:, 1].max()),
            float(caixas[:, 2].min()),
            float(caixas[:, 3].max()),
            float(caixas[:, 4].min()),
            float(caixas[:, 5].max()),
        )

    def posicao_da_camera(self) -> tuple[float, float, float]:
        """Devolve a posição atual da câmera, usada nos testes de estabilidade."""
        return self._renderer.GetActiveCamera().GetPosition()

    # --- ciclo de vida ---------------------------------------------------

    def redesenhar(self) -> None:
        """Pede um novo quadro."""
        self._renderer.ResetCameraClippingRange()
        self._interactor.GetRenderWindow().Render()

    def iniciar(self) -> None:
        """Inicializa o interactor. Precisa acontecer depois de a janela existir."""
        self._interactor.Initialize()

    def encerrar(self) -> None:
        """Solta a janela de renderização do VTK.

        Sem isto o processo pode não terminar, porque o VTK segura o contexto
        de OpenGL depois de o widget Qt ter ido embora.
        """
        self._interactor.GetRenderWindow().Finalize()
        self._interactor.close()

    def quantidade_de_atores(self) -> int:
        """Total de atores na cena, incluindo mesa e volume."""
        return self._renderer.GetActors().GetNumberOfItems()

    def ator_do_corpo(self, nome: str) -> vtkActor | None:
        """Devolve o ator de um corpo, ou `None` se ele não está na cena."""
        return self._atores_da_peca.get(nome)
