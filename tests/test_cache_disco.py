"""Testes do cache de malhas em disco."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from build123d import Box

from central.contrato import Corpo, Param, Produto, Resultado, TipoParam
from central.nucleo.cache import chave
from central.nucleo.cache_disco import SUFIXO, CacheEmDisco, MalhasEmCache
from central.nucleo.geracao import gerar_sincrono
from central.nucleo.tesselagem import NivelTesselagem
from central.servicos import caminhos


def produto_de_teste(id_produto: str = "teste") -> Produto:
    def gerar(valores: dict[str, Any]) -> Resultado:
        lado = valores["lado"]
        return Resultado(
            corpos=[
                Corpo(nome="base", forma=Box(lado, lado, 5), cor="#8AB4F8"),
                Corpo(nome="tampa", forma=Box(lado, lado, 2), cor="#F28B82"),
            ],
            avisos=["um aviso"],
            metadados={"caracteres": 3},
        )

    return Produto(
        id=id_produto,
        nome="Teste",
        versao="1.0.0",
        descricao="",
        categoria="Teste",
        params=(
            Param(chave="lado", rotulo="Lado", tipo=TipoParam.DECIMAL, padrao=20.0),
        ),
        gerar=gerar,
    )


@pytest.fixture
def cache(tmp_path: Path) -> CacheEmDisco:
    return CacheEmDisco(diretorio=tmp_path / "cache")


@pytest.fixture
def geracao():
    return gerar_sincrono(produto_de_teste(), {"lado": 20.0}, NivelTesselagem.PREVIEW)


# --- ida e volta ---------------------------------------------------------


def test_guardar_e_obter(cache: CacheEmDisco, geracao) -> None:
    assert cache.obter("teste/abc") is None
    cache.guardar("teste/abc", geracao)
    assert cache.obter("teste/abc") is not None


def test_malha_recuperada_e_identica(cache: CacheEmDisco, geracao) -> None:
    cache.guardar("teste/abc", geracao)
    payload = cache.obter("teste/abc")

    for nome, original in geracao.malhas.items():
        recuperada = payload.malhas[nome]
        assert len(recuperada.faces) == len(original.faces)
        assert len(recuperada.vertices) == len(original.vertices)
        np.testing.assert_allclose(
            recuperada.vertices, original.vertices, rtol=1e-5, atol=1e-4
        )
        np.testing.assert_array_equal(recuperada.faces, original.faces)


def test_malha_recuperada_continua_estanque(cache: CacheEmDisco, geracao) -> None:
    cache.guardar("teste/abc", geracao)
    payload = cache.obter("teste/abc")
    assert all(m.is_watertight for m in payload.malhas.values())


def test_metadados_sobrevivem(cache: CacheEmDisco, geracao) -> None:
    cache.guardar("teste/abc", geracao)
    payload = cache.obter("teste/abc")

    assert payload.ordem == ["base", "tampa"]
    assert payload.cores == {"base": "#8AB4F8", "tampa": "#F28B82"}
    assert payload.avisos == ["um aviso"]
    assert payload.metadados == {"caracteres": 3}
    assert payload.valores == {"lado": 20.0}
    assert payload.dimensoes == pytest.approx(geracao.dimensoes)


def test_geracao_reconstruida_nao_tem_solidos(cache: CacheEmDisco, geracao) -> None:
    """Malha não é sólido: quem precisa de B-rep tem de gerar de novo."""
    cache.guardar("teste/abc", geracao)
    recuperada = cache.obter("teste/abc").como_geracao()

    assert recuperada.tem_solidos is False
    assert all(c.forma is None for c in recuperada.resultado.corpos)
    assert [c.nome for c in recuperada.resultado.corpos] == ["base", "tampa"]
    assert recuperada.dimensoes == pytest.approx(geracao.dimensoes)


def test_sobrevive_a_um_novo_objeto_de_cache(tmp_path: Path, geracao) -> None:
    """O cache de disco existe para sobreviver ao fechamento do aplicativo."""
    diretorio = tmp_path / "cache"
    CacheEmDisco(diretorio=diretorio).guardar("teste/abc", geracao)
    assert CacheEmDisco(diretorio=diretorio).obter("teste/abc") is not None


# --- nível de tesselagem -------------------------------------------------


def test_nivel_de_exportacao_e_recusado(cache: CacheEmDisco) -> None:
    fina = gerar_sincrono(produto_de_teste(), {}, NivelTesselagem.EXPORTACAO)
    assert cache.guardar("teste/fina", fina) is None
    assert cache.obter("teste/fina") is None


def test_geracao_vinda_do_disco_nao_e_regravada(cache: CacheEmDisco, geracao) -> None:
    cache.guardar("teste/abc", geracao)
    reconstruida = cache.obter("teste/abc").como_geracao()
    assert cache.guardar("teste/xyz", reconstruida) is None


# --- contabilidade -------------------------------------------------------


def test_contadores(cache: CacheEmDisco, geracao) -> None:
    cache.obter("teste/nao_existe")
    cache.guardar("teste/abc", geracao)
    cache.obter("teste/abc")

    assert cache.acertos == 1
    assert cache.erros == 1


def test_nome_do_arquivo_traz_o_produto(cache: CacheEmDisco, geracao) -> None:
    produto = produto_de_teste()
    completa = chave(produto, {"lado": 20.0})
    escrito = cache.guardar(completa, geracao)

    assert escrito.name.startswith("teste_")
    assert escrito.suffix == SUFIXO


# --- teto e limpeza ------------------------------------------------------


def test_teto_apaga_a_entrada_mais_antiga(tmp_path: Path, geracao) -> None:
    cache = CacheEmDisco(diretorio=tmp_path / "cache", teto_em_bytes=10**9)
    cache.guardar("teste/antiga", geracao)
    tamanho = cache.tamanho_em_bytes()

    antigo = time.time() - 3600
    os.utime(cache.caminho_de("teste/antiga"), (antigo, antigo))

    # Um teto pouco acima de uma entrada só deixa a mais recente sobreviver.
    cache.teto_em_bytes = int(tamanho * 1.5)
    cache.guardar("teste/recente", geracao)

    assert cache.caminho_de("teste/recente").is_file()
    assert not cache.caminho_de("teste/antiga").is_file()
    assert cache.descartes == 1


def test_teto_generoso_preserva_tudo(tmp_path: Path, geracao) -> None:
    cache = CacheEmDisco(diretorio=tmp_path / "cache", teto_em_bytes=10**9)
    cache.guardar("teste/a", geracao)
    cache.guardar("teste/b", geracao)
    assert len(cache) == 2


def test_usar_uma_entrada_a_protege(tmp_path: Path, geracao) -> None:
    cache = CacheEmDisco(diretorio=tmp_path / "cache", teto_em_bytes=10**9)
    cache.guardar("teste/a", geracao)
    cache.guardar("teste/b", geracao)

    # Envelhecer as duas explicitamente evita empate de timestamp: dois
    # arquivos escritos no mesmo instante têm a mesma mtime, e aí a ordem de
    # descarte passaria a depender do relógio em vez da política.
    antigo = time.time() - 3600
    for chave_completa in ("teste/a", "teste/b"):
        os.utime(cache.caminho_de(chave_completa), (antigo, antigo))

    cache.obter("teste/a")
    cache.teto_em_bytes = int(cache.tamanho_em_bytes() * 0.6)
    cache.aplicar_teto()

    assert cache.caminho_de("teste/a").is_file()
    assert not cache.caminho_de("teste/b").is_file()


def test_invalidar_produto_apaga_so_o_dele(tmp_path: Path, geracao) -> None:
    cache = CacheEmDisco(diretorio=tmp_path / "cache")
    outra = gerar_sincrono(produto_de_teste("outro"), {}, NivelTesselagem.PREVIEW)
    cache.guardar("teste/a", geracao)
    cache.guardar("teste/b", geracao)
    cache.guardar("outro/c", outra)

    assert cache.invalidar_produto("teste") == 2
    assert len(cache) == 1
    assert cache.obter("outro/c") is not None


def test_limpar_apaga_tudo(tmp_path: Path, geracao) -> None:
    cache = CacheEmDisco(diretorio=tmp_path / "cache")
    cache.guardar("teste/a", geracao)
    cache.guardar("teste/b", geracao)
    assert cache.limpar() == 2
    assert len(cache) == 0


# --- robustez ------------------------------------------------------------


def test_arquivo_corrompido_nao_derruba(cache: CacheEmDisco, geracao) -> None:
    cache.guardar("teste/abc", geracao)
    cache.caminho_de("teste/abc").write_bytes(b"isto nao e um npz")

    assert cache.obter("teste/abc") is None
    assert not cache.caminho_de("teste/abc").is_file()


def test_diretorio_e_criado_se_nao_existe(tmp_path: Path) -> None:
    destino = tmp_path / "a" / "b" / "cache"
    CacheEmDisco(diretorio=destino)
    assert destino.is_dir()


def test_arquivo_parcial_nao_vira_entrada(cache: CacheEmDisco, geracao) -> None:
    """A escrita é atômica: nada de entrada meio gravada virar acerto."""
    cache.guardar("teste/abc", geracao)
    assert list(cache.diretorio.glob("*.parcial")) == []


# --- diretório de dados --------------------------------------------------


def test_diretorio_de_cache_respeita_a_sobrescrita(tmp_path: Path) -> None:
    caminhos.definir_diretorio_de_dados(tmp_path / "dados")
    try:
        assert caminhos.diretorio_de_cache() == tmp_path / "dados" / "cache"
        assert caminhos.diretorio_de_cache().is_dir()
    finally:
        caminhos.definir_diretorio_de_dados(None)


def test_diretorio_de_dados_padrao_existe() -> None:
    assert caminhos.diretorio_de_dados().is_dir()


def test_payload_de_geracao_e_de_volta(geracao) -> None:
    payload = MalhasEmCache.de_geracao(geracao)
    assert payload.ordem == ["base", "tampa"]
    assert payload.como_geracao().nivel is NivelTesselagem.PREVIEW
