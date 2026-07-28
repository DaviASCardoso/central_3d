"""Testes da exportação.

O 3MF é inspecionado abrindo o zip e lendo `3D/3dmodel.model`, e não pelo
round-trip do `Mesher.read()` do build123d, que não restaura nome nem cor.
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path
from typing import Any

import pytest
import trimesh
from build123d import Box, Pos

from central.contrato import Corpo, Param, Produto, Resultado, TipoParam
from central.nucleo.erros import ErroDeExportacao
from central.nucleo.exportacao import Formato, escrever_3mf, escrever_stl, exportar
from central.nucleo.geracao import gerar_sincrono
from central.nucleo.tesselagem import NivelTesselagem, tesselar

MODELO = "3D/3dmodel.model"


def ler_modelo(caminho: Path) -> str:
    with zipfile.ZipFile(caminho) as pacote:
        return pacote.read(MODELO).decode("utf-8")


def objetos(xml: str) -> list[str]:
    return re.findall(r"<object [^>]*>", xml)


def materiais(xml: str) -> list[str]:
    return re.findall(r"<base [^>]*/>", xml)


@pytest.fixture
def dois_corpos() -> tuple[dict[str, trimesh.Trimesh], list[Corpo]]:
    base = Corpo(nome="base", forma=Box(20, 20, 10), cor="#8AB4F8")
    tampa = Corpo(nome="tampa", forma=Pos(0, 0, 7.5) * Box(20, 20, 5), cor="#F28B82")
    corpos = [base, tampa]
    malhas = {
        c.nome: tesselar(c.forma, NivelTesselagem.EXPORTACAO) for c in corpos
    }
    return malhas, corpos


# --- 3MF -----------------------------------------------------------------


def test_dois_corpos_viram_dois_objetos_nomeados(dois_corpos, tmp_path: Path) -> None:
    malhas, corpos = dois_corpos
    xml = ler_modelo(escrever_3mf(malhas, corpos, tmp_path / "peca.3mf"))

    encontrados = objetos(xml)
    assert len(encontrados) == 2
    assert any('name="base"' in o for o in encontrados)
    assert any('name="tampa"' in o for o in encontrados)


def test_cores_viram_basematerials(dois_corpos, tmp_path: Path) -> None:
    malhas, corpos = dois_corpos
    xml = ler_modelo(escrever_3mf(malhas, corpos, tmp_path / "peca.3mf"))

    encontrados = materiais(xml)
    assert len(encontrados) == 2
    assert any("#8AB4F8FF" in m for m in encontrados)
    assert any("#F28B82FF" in m for m in encontrados)


def test_unidade_e_milimetro(dois_corpos, tmp_path: Path) -> None:
    malhas, corpos = dois_corpos
    xml = ler_modelo(escrever_3mf(malhas, corpos, tmp_path / "peca.3mf"))
    assert 'unit="millimeter"' in xml


def test_ha_um_build_item_por_corpo(dois_corpos, tmp_path: Path) -> None:
    malhas, corpos = dois_corpos
    xml = ler_modelo(escrever_3mf(malhas, corpos, tmp_path / "peca.3mf"))
    assert len(re.findall(r"<item ", xml)) == 2


def test_triangulos_gravados_sao_os_da_malha_validada(dois_corpos, tmp_path: Path) -> None:
    """A garantia central: o que o portão de qualidade valida é o que se grava."""
    malhas, corpos = dois_corpos
    xml = ler_modelo(escrever_3mf(malhas, corpos, tmp_path / "peca.3mf"))

    esperados = sum(len(malhas[c.nome].faces) for c in corpos)
    assert len(re.findall(r"<triangle ", xml)) == esperados


def test_um_corpo_produz_um_objeto(tmp_path: Path) -> None:
    corpo = Corpo(nome="placa", forma=Box(10, 10, 2))
    malhas = {"placa": tesselar(corpo.forma, NivelTesselagem.EXPORTACAO)}
    xml = ler_modelo(escrever_3mf(malhas, [corpo], tmp_path / "u.3mf"))
    assert len(objetos(xml)) == 1
    assert 'name="placa"' in xml


def test_arquivo_e_um_zip_valido_com_as_partes_do_3mf(dois_corpos, tmp_path: Path) -> None:
    malhas, corpos = dois_corpos
    caminho = escrever_3mf(malhas, corpos, tmp_path / "peca.3mf")
    with zipfile.ZipFile(caminho) as pacote:
        nomes = pacote.namelist()
    assert MODELO in nomes
    assert "[Content_Types].xml" in nomes
    assert "_rels/.rels" in nomes


def test_diretorio_inexistente_e_criado(dois_corpos, tmp_path: Path) -> None:
    malhas, corpos = dois_corpos
    destino = tmp_path / "a" / "b" / "peca.3mf"
    assert escrever_3mf(malhas, corpos, destino).is_file()


def test_corpo_sem_malha_e_recusado(tmp_path: Path) -> None:
    corpo = Corpo(nome="orfao", forma=Box(1, 1, 1))
    with pytest.raises(ErroDeExportacao, match="não tem malha"):
        escrever_3mf({}, [corpo], tmp_path / "x.3mf")


def test_lista_vazia_e_recusada(tmp_path: Path) -> None:
    with pytest.raises(ErroDeExportacao, match="não há corpo nenhum"):
        escrever_3mf({}, [], tmp_path / "x.3mf")


def test_cor_invalida_cai_no_padrao_sem_quebrar(tmp_path: Path) -> None:
    corpo = Corpo(nome="placa", forma=Box(10, 10, 2), cor="azul")
    malhas = {"placa": tesselar(corpo.forma, NivelTesselagem.EXPORTACAO)}
    xml = ler_modelo(escrever_3mf(malhas, [corpo], tmp_path / "u.3mf"))
    assert "#8AB4F8FF" in xml


def test_cor_de_tres_digitos_e_expandida(tmp_path: Path) -> None:
    corpo = Corpo(nome="placa", forma=Box(10, 10, 2), cor="#f00")
    malhas = {"placa": tesselar(corpo.forma, NivelTesselagem.EXPORTACAO)}
    xml = ler_modelo(escrever_3mf(malhas, [corpo], tmp_path / "u.3mf"))
    assert "#FF0000FF" in xml


# --- STL -----------------------------------------------------------------


def test_stl_relido_tem_o_volume_do_solido(tmp_path: Path) -> None:
    corpo = Corpo(nome="caixa", forma=Box(20, 30, 40))
    malhas = {"caixa": tesselar(corpo.forma, NivelTesselagem.EXPORTACAO)}
    caminho = tmp_path / "caixa.stl"
    escrever_stl(malhas, [corpo], caminho)
    relida = trimesh.load(caminho)
    assert relida.volume == pytest.approx(24000.0, rel=0.005)


def test_stl_funde_os_corpos(dois_corpos, tmp_path: Path) -> None:
    malhas, corpos = dois_corpos
    caminho = escrever_stl(malhas, corpos, tmp_path / "conjunto.stl")
    relida = trimesh.load(caminho)
    esperado = sum(malhas[c.nome].volume for c in corpos)
    assert relida.volume == pytest.approx(esperado, rel=0.005)


# --- exportar ------------------------------------------------------------


def _produto() -> Produto:
    def gerar(valores: dict[str, Any]) -> Resultado:
        lado = valores["lado"]
        return Resultado(corpos=[Corpo(nome="cubo", forma=Box(lado, lado, lado))])

    return Produto(
        id="cubo",
        nome="Cubo",
        versao="1.0.0",
        descricao="",
        categoria="Teste",
        params=(Param(chave="lado", rotulo="Lado", tipo=TipoParam.DECIMAL, padrao=20.0),),
        gerar=gerar,
    )


def test_exportar_acrescenta_a_extensao(tmp_path: Path) -> None:
    geracao = gerar_sincrono(_produto(), {}, NivelTesselagem.EXPORTACAO)
    escrito = exportar(geracao, tmp_path / "sem_extensao")
    assert escrito.suffix == ".3mf"
    assert escrito.is_file()


def test_exportar_respeita_a_extensao_dada(tmp_path: Path) -> None:
    geracao = gerar_sincrono(_produto(), {}, NivelTesselagem.EXPORTACAO)
    escrito = exportar(geracao, tmp_path / "peca.stl", Formato.STL)
    assert escrito.name == "peca.stl"


def test_exportar_recusa_malha_de_preview(tmp_path: Path) -> None:
    geracao = gerar_sincrono(_produto(), {}, NivelTesselagem.PREVIEW)
    with pytest.raises(ErroDeExportacao, match="nível de exportação|exige"):
        exportar(geracao, tmp_path / "peca.3mf")


def test_ponta_a_ponta_da_placa_nome(tmp_path: Path) -> None:
    from central.nucleo import descobrir

    produto = descobrir().obter("placa_nome")
    geracao = gerar_sincrono(produto, {"nome": "Helena"}, NivelTesselagem.EXPORTACAO)
    caminho = exportar(geracao, tmp_path / "placa.3mf")

    xml = ler_modelo(caminho)
    assert 'name="placa"' in xml
    assert 'unit="millimeter"' in xml
    assert len(objetos(xml)) == 1
