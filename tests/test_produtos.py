"""Teste genérico de todos os produtos do catálogo, mais o específico da placa.

A fixture parametrizada da seção 15 do CENTRAL.md é o que impede regressão
silenciosa quando um produto é editado, e é barata justamente porque o contrato
garante que todos os produtos são chamáveis da mesma forma. Nenhum produto
precisa escrever este teste à mão.
"""

from __future__ import annotations

from typing import Any

import pytest

from central.contrato import Produto
from central.nucleo import descobrir
from central.nucleo.erros import ErroDeValidacao
from central.nucleo.geracao import gerar_sincrono
from central.nucleo.impressora import VOLUME_DE_CONSTRUCAO
from central.nucleo.tesselagem import NivelTesselagem
from central.nucleo.validacao import validar

REGISTRO = descobrir()


def ids_dos_produtos() -> list[str]:
    return sorted(REGISTRO.produtos)


@pytest.fixture(params=ids_dos_produtos())
def produto(request) -> Produto:
    return REGISTRO.obter(request.param)


# --- teste genérico, fornecido pela Central ------------------------------


def test_nenhum_produto_falha_ao_carregar() -> None:
    assert REGISTRO.falhas == {}


def test_ha_ao_menos_um_produto() -> None:
    assert len(REGISTRO) >= 1


def test_padroes_sao_validos(produto: Produto) -> None:
    """O contrato exige que `padrao` seja sempre válido segundo as restrições."""
    resultado = validar(produto, {})
    assert resultado.valido, resultado.mensagens()


def test_gera_com_os_padroes(produto: Produto) -> None:
    saida = gerar_sincrono(produto, {}, NivelTesselagem.EXPORTACAO)
    assert saida.resultado.corpos


def test_malha_dos_padroes_e_estanque(produto: Produto) -> None:
    saida = gerar_sincrono(produto, {}, NivelTesselagem.EXPORTACAO)
    for nome, malha in saida.malhas.items():
        assert malha.is_watertight, f"corpo '{nome}' não é estanque"
        assert malha.volume > 0, f"corpo '{nome}' tem volume não positivo"


def test_peca_dos_padroes_cabe_no_volume_de_construcao(produto: Produto) -> None:
    saida = gerar_sincrono(produto, {}, NivelTesselagem.EXPORTACAO)
    assert VOLUME_DE_CONSTRUCAO.cabe(saida.dimensoes), saida.dimensoes


def test_peca_sai_assentada_na_mesa(produto: Produto) -> None:
    saida = gerar_sincrono(produto, {}, NivelTesselagem.EXPORTACAO)
    menor_z = min(c.forma.bounding_box().min.Z for c in saida.resultado.corpos)
    assert menor_z == pytest.approx(0.0, abs=1e-6)


def test_id_do_manifesto_bate_com_o_indice(produto: Produto) -> None:
    assert REGISTRO.obter(produto.id) is produto


def test_manifesto_tem_metadados_de_biblioteca(produto: Produto) -> None:
    assert produto.nome
    assert produto.descricao
    assert produto.categoria
    assert produto.versao.count(".") == 2


def test_parametros_tem_chave_unica(produto: Produto) -> None:
    chaves = [p.chave for p in produto.params]
    assert len(chaves) == len(set(chaves))


def test_geracao_e_deterministica(produto: Produto) -> None:
    """Mesma entrada, mesmo volume — o cache depende disso."""
    primeira = gerar_sincrono(produto, {}, NivelTesselagem.EXPORTACAO)
    segunda = gerar_sincrono(produto, {}, NivelTesselagem.EXPORTACAO)
    for nome, malha in primeira.malhas.items():
        assert malha.volume == pytest.approx(segunda.malhas[nome].volume, rel=1e-12)
        assert len(malha.faces) == len(segunda.malhas[nome].faces)


# --- específicos da placa_nome ------------------------------------------


def placa() -> Produto:
    return REGISTRO.obter("placa_nome")


def gerar_placa(**valores: Any):
    return gerar_sincrono(placa(), valores, NivelTesselagem.PREVIEW)


def test_placa_respeita_as_dimensoes_pedidas() -> None:
    saida = gerar_placa(largura=100.0, profundidade=30.0, espessura=5.0, relevo=1.0)
    largura, profundidade, altura = saida.dimensoes
    assert largura == pytest.approx(100.0)
    assert profundidade == pytest.approx(30.0)
    assert altura == pytest.approx(6.0)


def test_relevo_soma_a_altura_total() -> None:
    baixo = gerar_placa(espessura=4.0, relevo=0.6).dimensoes[2]
    alto = gerar_placa(espessura=4.0, relevo=2.0).dimensoes[2]
    assert alto - baixo == pytest.approx(1.4, abs=1e-6)


def test_nome_longo_e_comprimido_com_aviso() -> None:
    saida = gerar_placa(nome="Bartolomeu Nascimento", largura=60.0)
    assert any("comprimido" in aviso for aviso in saida.avisos)
    assert saida.dimensoes[0] == pytest.approx(60.0)
    assert saida.malhas["placa"].is_watertight


def test_compressao_preserva_altura_do_texto_e_relevo() -> None:
    """Comprimir em X não pode achatar o relevo abaixo do mínimo físico."""
    curto = gerar_placa(nome="Ana", largura=80.0, espessura=4.0, relevo=1.0)
    longo = gerar_placa(nome="Bartolomeu Nascimento", largura=60.0, espessura=4.0, relevo=1.0)
    assert curto.dimensoes[2] == pytest.approx(longo.dimensoes[2])


def test_nome_curto_nao_gera_aviso() -> None:
    assert gerar_placa(nome="Ana", largura=80.0).avisos == []


def test_sem_chanfro_a_placa_tem_mais_volume() -> None:
    com = gerar_placa(chanfro=3.0).malhas["placa"].volume
    sem = gerar_placa(chanfro=0.0).malhas["placa"].volume
    assert sem > com


def test_cor_nao_afeta_geometria() -> None:
    param = next(p for p in placa().params if p.chave == "cor")
    assert param.afeta_geometria is False


def test_corpo_leva_a_cor_declarada() -> None:
    saida = gerar_placa(cor="#F28B82")
    assert saida.resultado.corpos[0].cor == "#F28B82"


def test_metadados_contam_os_caracteres() -> None:
    assert gerar_placa(nome="Helena").resultado.metadados["caracteres"] == 6


# --- validação cruzada da placa -----------------------------------------


@pytest.mark.parametrize("nome", ["", "   "])
def test_nome_vazio_e_recusado(nome: str) -> None:
    with pytest.raises(ErroDeValidacao, match="não pode ser vazio"):
        gerar_placa(nome=nome)


def test_texto_maior_que_a_placa_e_recusado() -> None:
    with pytest.raises(ErroDeValidacao, match="não cabe numa placa"):
        gerar_placa(altura_texto=20.0, profundidade=15.0)


def test_chanfro_maior_que_a_espessura_e_recusado() -> None:
    with pytest.raises(ErroDeValidacao, match="cortaria a placa ao meio"):
        gerar_placa(espessura=2.0, chanfro=3.0)


def test_muitas_letras_em_placa_estreita_e_recusado() -> None:
    with pytest.raises(ErroDeValidacao, match="abaixo de 0,8 mm"):
        gerar_placa(nome="Aparecida", largura=25.0, profundidade=40.0)


def test_relevo_abaixo_do_minimo_fisico_e_recusado() -> None:
    with pytest.raises(ErroDeValidacao, match="mínimo de 0.6 mm"):
        gerar_placa(relevo=0.3)


def test_altura_de_texto_abaixo_do_minimo_fisico_e_recusada() -> None:
    with pytest.raises(ErroDeValidacao, match="mínimo de 4 mm"):
        gerar_placa(altura_texto=2.0)


def test_fonte_fora_das_opcoes_e_recusada() -> None:
    with pytest.raises(ErroDeValidacao, match="não está entre as opções"):
        gerar_placa(fonte="Comic Sans MS")
