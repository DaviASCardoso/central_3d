"""Testes da chave de cache e do cache em memória."""

from __future__ import annotations

import subprocess
import sys
from dataclasses import replace
from typing import Any

import pytest
from build123d import Box

from central.contrato import Param, Produto, TipoParam
from central.nucleo.cache import (
    CacheEmMemoria,
    chave,
    produto_da_chave,
    valores_que_afetam_geometria,
)
from central.nucleo.geracao import gerar_sincrono
from central.nucleo.tesselagem import NivelTesselagem

PROGRAMA_DETERMINISMO = """
from central.contrato import Param, Produto, TipoParam
from central.nucleo.cache import chave

produto = Produto(
    id="teste", nome="Teste", versao="1.0.0", descricao="", categoria="Teste",
    params=(
        Param(chave="lado", rotulo="Lado", tipo=TipoParam.DECIMAL, padrao=10.0),
        Param(chave="nome", rotulo="Nome", tipo=TipoParam.TEXTO, padrao="Ana"),
    ),
    gerar=lambda v: v,
)
print(chave(produto, {"lado": 12.5, "nome": "Helena"}))
"""


def produto_de_teste(**extras: Any) -> Produto:
    base: dict[str, Any] = {
        "id": "teste",
        "nome": "Teste",
        "versao": "1.0.0",
        "descricao": "",
        "categoria": "Teste",
        "params": (
            Param(chave="lado", rotulo="Lado", tipo=TipoParam.DECIMAL, padrao=10.0),
            Param(chave="nome", rotulo="Nome", tipo=TipoParam.TEXTO, padrao="Ana"),
            Param(
                chave="cor",
                rotulo="Cor",
                tipo=TipoParam.COR,
                padrao="#8AB4F8",
                afeta_geometria=False,
            ),
        ),
        "gerar": lambda valores: Box(valores["lado"], 10, 10),
    }
    base.update(extras)
    return Produto(**base)


# --- chave ---------------------------------------------------------------


def test_mesma_entrada_mesma_chave() -> None:
    produto = produto_de_teste()
    valores = {"lado": 12.5, "nome": "Helena", "cor": "#FFFFFF"}
    assert chave(produto, valores) == chave(produto, valores)


def test_chave_e_estavel_entre_processos() -> None:
    """O cache de disco sobrevive ao fechamento do app; a chave precisa também."""
    execucao = subprocess.run(
        [sys.executable, "-c", PROGRAMA_DETERMINISMO],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    produto = Produto(
        id="teste",
        nome="Teste",
        versao="1.0.0",
        descricao="",
        categoria="Teste",
        params=(
            Param(chave="lado", rotulo="Lado", tipo=TipoParam.DECIMAL, padrao=10.0),
            Param(chave="nome", rotulo="Nome", tipo=TipoParam.TEXTO, padrao="Ana"),
        ),
        gerar=lambda v: v,
    )
    esperada = chave(produto, {"lado": 12.5, "nome": "Helena"})
    assert execucao.stdout.strip() == esperada


def test_ordem_das_chaves_no_dicionario_nao_importa() -> None:
    produto = produto_de_teste()
    primeira = chave(produto, {"lado": 1.0, "nome": "Ana", "cor": "#000000"})
    segunda = chave(produto, {"cor": "#000000", "nome": "Ana", "lado": 1.0})
    assert primeira == segunda


def test_valor_diferente_muda_a_chave() -> None:
    produto = produto_de_teste()
    assert chave(produto, {"lado": 1.0}) != chave(produto, {"lado": 2.0})


def test_versao_diferente_invalida() -> None:
    produto = produto_de_teste()
    outra = replace(produto, versao="1.1.0")
    assert chave(produto, {"lado": 1.0}) != chave(outra, {"lado": 1.0})


def test_id_diferente_muda_a_chave() -> None:
    produto = produto_de_teste()
    outro = replace(produto, id="outro")
    assert chave(produto, {"lado": 1.0}) != chave(outro, {"lado": 1.0})


def test_parametro_que_nao_afeta_geometria_nao_invalida() -> None:
    produto = produto_de_teste()
    azul = chave(produto, {"lado": 1.0, "cor": "#8AB4F8"})
    vermelho = chave(produto, {"lado": 1.0, "cor": "#FF0000"})
    assert azul == vermelho


def test_nivel_faz_parte_da_chave() -> None:
    produto = produto_de_teste()
    leve = chave(produto, {"lado": 1.0}, NivelTesselagem.PREVIEW)
    fina = chave(produto, {"lado": 1.0}, NivelTesselagem.EXPORTACAO)
    assert leve != fina


def test_valor_ausente_usa_o_padrao_e_da_a_mesma_chave() -> None:
    produto = produto_de_teste()
    assert chave(produto, {}) == chave(produto, {"lado": 10.0, "nome": "Ana"})


def test_chave_tem_o_id_como_prefixo() -> None:
    produto = produto_de_teste()
    completa = chave(produto, {})
    assert completa.startswith("teste/")
    assert produto_da_chave(completa) == "teste"


def test_hash_tem_o_tamanho_de_um_sha256() -> None:
    produto = produto_de_teste()
    assert len(chave(produto, {}).split("/", 1)[1]) == 64


def test_filtro_de_valores_ignora_os_que_nao_afetam() -> None:
    produto = produto_de_teste()
    filtrados = valores_que_afetam_geometria(produto, {"lado": 2.0, "cor": "#FFF"})
    assert set(filtrados) == {"lado", "nome"}


# --- cache em memória ----------------------------------------------------


def _geracao(lado: float = 10.0):
    return gerar_sincrono(produto_de_teste(), {"lado": lado})


def test_guardar_e_obter() -> None:
    cache = CacheEmMemoria()
    resultado = _geracao()
    cache.guardar("teste/abc", resultado)
    assert cache.obter("teste/abc") is resultado


def test_obter_inexistente_devolve_none() -> None:
    cache = CacheEmMemoria()
    assert cache.obter("teste/nao_existe") is None


def test_estatisticas_contam_acertos_e_erros() -> None:
    cache = CacheEmMemoria()
    cache.guardar("teste/abc", _geracao())
    cache.obter("teste/abc")
    cache.obter("teste/xyz")
    assert cache.estatisticas.acertos == 1
    assert cache.estatisticas.erros == 1
    assert cache.estatisticas.taxa_de_acerto == pytest.approx(0.5)


def test_taxa_de_acerto_sem_busca_e_zero() -> None:
    assert CacheEmMemoria().estatisticas.taxa_de_acerto == 0.0


def test_lru_descarta_a_entrada_mais_antiga() -> None:
    cache = CacheEmMemoria(maximo=2)
    resultado = _geracao()
    cache.guardar("teste/a", resultado)
    cache.guardar("teste/b", resultado)
    cache.guardar("teste/c", resultado)

    assert "teste/a" not in cache
    assert "teste/b" in cache
    assert "teste/c" in cache
    assert cache.estatisticas.descartes == 1


def test_usar_uma_entrada_a_protege_do_descarte() -> None:
    cache = CacheEmMemoria(maximo=2)
    resultado = _geracao()
    cache.guardar("teste/a", resultado)
    cache.guardar("teste/b", resultado)
    cache.obter("teste/a")
    cache.guardar("teste/c", resultado)

    assert "teste/a" in cache
    assert "teste/b" not in cache


def test_invalidar_produto_remove_so_o_dele() -> None:
    cache = CacheEmMemoria()
    resultado = _geracao()
    cache.guardar("teste/a", resultado)
    cache.guardar("teste/b", resultado)
    cache.guardar("outro/c", resultado)

    assert cache.invalidar_produto("teste") == 2
    assert cache.chaves() == ["outro/c"]


def test_invalidar_produto_sem_entradas_nao_lanca() -> None:
    assert CacheEmMemoria().invalidar_produto("nao_existe") == 0


def test_limpar_esvazia_mas_preserva_estatisticas() -> None:
    cache = CacheEmMemoria()
    cache.guardar("teste/a", _geracao())
    cache.obter("teste/a")
    cache.limpar()

    assert len(cache) == 0
    assert cache.estatisticas.acertos == 1


def test_ponta_a_ponta_com_o_produto_de_verdade() -> None:
    from central.nucleo import descobrir

    produto = descobrir().obter("placa_nome")
    cache = CacheEmMemoria()

    valores = {"nome": "Helena"}
    completa = chave(produto, valores)
    assert cache.obter(completa) is None

    cache.guardar(completa, gerar_sincrono(produto, valores))
    assert cache.obter(completa) is not None

    # Mudar só a cor não deve gerar de novo.
    assert chave(produto, {"nome": "Helena", "cor": "#FF0000"}) == completa
