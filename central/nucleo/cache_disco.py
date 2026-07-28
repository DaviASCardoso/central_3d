"""Cache de malhas em disco, content-addressed.

Guardado em `%LOCALAPPDATA%/Central/cache/` no Windows e no equivalente XDG no
Linux, com a chave de hash no nome do arquivo e a malha serializada em binário
compacto. Um teto configurável de tamanho, com padrão de dois gigabytes,
dispara limpeza por menos-recentemente-usado. Ver a seção 6 do CENTRAL.md.

**O cache de disco guarda apenas o nível de preview.** Ele serializa malhas, e
malha não é sólido: uma geração recuperada daqui não tem B-rep, e exportar
STEP ou qualquer coisa que precise da geometria exata exigiria regenerar.
Restringindo o disco ao preview, a exportação nunca cai nesse caso — ou é
acerto no cache em memória, que guarda a geração inteira, ou é geração nova.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import trimesh

from central.contrato import Corpo, Resultado
from central.log import obter
from central.nucleo.cache import produto_da_chave
from central.nucleo.geracao import ResultadoGeracao
from central.nucleo.tesselagem import NivelTesselagem
from central.servicos.caminhos import diretorio_de_cache

_log = obter(__name__)

SUFIXO = ".npz"
TETO_PADRAO_EM_BYTES = 2 * 1024**3
"""Dois gigabytes, o padrão da seção 6."""

CHAVE_DOS_METADADOS = "__meta__"
SEPARADOR_DE_CAMPO = "\x1f"
"""Separa nome de corpo e campo dentro da chave do npz, sem colidir com nomes."""


@dataclass(slots=True)
class MalhasEmCache:
    """O que o disco guarda de uma geração.

    Attributes:
        ordem: Nomes dos corpos, na ordem em que o produto os devolveu.
        malhas: Malha de cada corpo.
        cores: Cor de exibição de cada corpo.
        dimensoes: Tamanho do conjunto em milímetros.
        avisos: Mensagens do produto ao operador.
        metadados: Informação livre devolvida pelo produto.
        valores: Os valores que geraram este resultado.
    """

    ordem: list[str]
    malhas: dict[str, trimesh.Trimesh]
    cores: dict[str, str]
    dimensoes: tuple[float, float, float]
    avisos: list[str]
    metadados: dict[str, Any]
    valores: dict[str, Any]

    def como_geracao(self) -> ResultadoGeracao:
        """Reconstrói uma `ResultadoGeracao` sem os sólidos.

        Returns:
            A geração com `tem_solidos` falso e `corpo.forma` igual a `None`.
        """
        corpos = [
            Corpo(nome=nome, forma=None, cor=self.cores.get(nome, "#8AB4F8"))
            for nome in self.ordem
        ]
        return ResultadoGeracao(
            resultado=Resultado(
                corpos=corpos, avisos=list(self.avisos), metadados=dict(self.metadados)
            ),
            malhas=dict(self.malhas),
            valores=dict(self.valores),
            nivel=NivelTesselagem.PREVIEW,
            dimensoes=self.dimensoes,
            avisos=list(self.avisos),
            tem_solidos=False,
        )

    @classmethod
    def de_geracao(cls, geracao: ResultadoGeracao) -> MalhasEmCache:
        """Extrai de uma geração o que cabe no disco.

        Args:
            geracao: A geração a serializar.

        Returns:
            O payload serializável.
        """
        corpos = geracao.resultado.corpos
        return cls(
            ordem=[c.nome for c in corpos],
            malhas=dict(geracao.malhas),
            cores={c.nome: c.cor for c in corpos},
            dimensoes=geracao.dimensoes,
            avisos=list(geracao.avisos),
            metadados=dict(geracao.resultado.metadados),
            valores=dict(geracao.valores),
        )


class CacheEmDisco:
    """Malhas de preview persistidas entre execuções."""

    def __init__(
        self,
        diretorio: Path | None = None,
        teto_em_bytes: int = TETO_PADRAO_EM_BYTES,
    ) -> None:
        """Cria o cache, garantindo que o diretório exista.

        Args:
            diretorio: Onde guardar. Por padrão, o diretório de cache do
                usuário.
            teto_em_bytes: Tamanho máximo antes da limpeza por
                menos-recentemente-usado.
        """
        self.diretorio = diretorio or diretorio_de_cache()
        self.diretorio.mkdir(parents=True, exist_ok=True)
        self.teto_em_bytes = teto_em_bytes
        self.acertos = 0
        self.erros = 0
        self.descartes = 0

    # --- endereçamento ---------------------------------------------------

    def caminho_de(self, chave_completa: str) -> Path:
        """Traduz uma chave de cache em caminho de arquivo.

        Args:
            chave_completa: Chave no formato `id_do_produto/hash`.

        Returns:
            O caminho do arquivo correspondente, existindo ou não.
        """
        id_produto = produto_da_chave(chave_completa)
        digest = chave_completa.split("/", 1)[1]
        return self.diretorio / f"{id_produto}_{digest}{SUFIXO}"

    # --- leitura e escrita ----------------------------------------------

    def obter(self, chave_completa: str) -> MalhasEmCache | None:
        """Busca uma geração no disco.

        Args:
            chave_completa: A chave calculada por `cache.chave`.

        Returns:
            O payload guardado, ou `None` se não há entrada ou se o arquivo
            está corrompido — corrupção nunca derruba a Central, o arquivo é
            descartado e a geração acontece de novo.
        """
        caminho = self.caminho_de(chave_completa)
        if not caminho.is_file():
            self.erros += 1
            return None

        try:
            payload = self._ler(caminho)
        except (OSError, ValueError, KeyError, EOFError) as erro:
            _log.warning("entrada de cache corrompida em %s: %s", caminho.name, erro)
            caminho.unlink(missing_ok=True)
            self.erros += 1
            return None

        caminho.touch()
        self.acertos += 1
        return payload

    def guardar(self, chave_completa: str, geracao: ResultadoGeracao) -> Path | None:
        """Persiste uma geração de preview.

        Gerações no nível de exportação são recusadas de propósito: ver o
        cabeçalho deste módulo.

        Args:
            chave_completa: A chave calculada por `cache.chave`.
            geracao: A geração a guardar.

        Returns:
            O caminho escrito, ou `None` se a geração foi recusada.
        """
        if geracao.nivel is not NivelTesselagem.PREVIEW:
            _log.debug("cache de disco ignora o nível %s", geracao.nivel)
            return None
        if not geracao.tem_solidos:
            _log.debug("geração já veio do disco; não regravando")
            return None

        caminho = self.caminho_de(chave_completa)
        try:
            self._escrever(caminho, MalhasEmCache.de_geracao(geracao))
        except OSError as erro:
            _log.warning("não foi possível gravar o cache em %s: %s", caminho.name, erro)
            return None

        self.aplicar_teto()
        return caminho

    def _ler(self, caminho: Path) -> MalhasEmCache:
        """Desserializa um arquivo de cache."""
        with np.load(caminho, allow_pickle=False) as arquivo:
            meta = json.loads(str(arquivo[CHAVE_DOS_METADADOS].item()))
            malhas = {
                nome: trimesh.Trimesh(
                    vertices=arquivo[f"{nome}{SEPARADOR_DE_CAMPO}v"],
                    faces=arquivo[f"{nome}{SEPARADOR_DE_CAMPO}f"],
                    process=False,
                )
                for nome in meta["ordem"]
            }
        return MalhasEmCache(
            ordem=list(meta["ordem"]),
            malhas=malhas,
            cores=dict(meta["cores"]),
            dimensoes=tuple(meta["dimensoes"]),  # type: ignore[arg-type]
            avisos=list(meta["avisos"]),
            metadados=dict(meta["metadados"]),
            valores=dict(meta["valores"]),
        )

    def _escrever(self, caminho: Path, payload: MalhasEmCache) -> None:
        """Serializa um payload em binário compacto."""
        arrays: dict[str, np.ndarray] = {}
        for nome in payload.ordem:
            malha = payload.malhas[nome]
            arrays[f"{nome}{SEPARADOR_DE_CAMPO}v"] = np.asarray(
                malha.vertices, dtype=np.float32
            )
            arrays[f"{nome}{SEPARADOR_DE_CAMPO}f"] = np.asarray(
                malha.faces, dtype=np.uint32
            )

        meta = json.dumps(
            {
                "ordem": payload.ordem,
                "cores": payload.cores,
                "dimensoes": list(payload.dimensoes),
                "avisos": payload.avisos,
                "metadados": payload.metadados,
                "valores": payload.valores,
            },
            ensure_ascii=False,
            default=repr,
        )
        arrays[CHAVE_DOS_METADADOS] = np.array(meta)

        temporario = caminho.with_suffix(".parcial")
        with temporario.open("wb") as destino:
            np.savez_compressed(destino, **arrays)
        temporario.replace(caminho)

    # --- manutenção ------------------------------------------------------

    def arquivos(self) -> list[Path]:
        """Devolve as entradas em disco, da mais antiga à mais recente."""
        entradas = [p for p in self.diretorio.glob(f"*{SUFIXO}") if p.is_file()]
        return sorted(entradas, key=lambda p: p.stat().st_mtime)

    def tamanho_em_bytes(self) -> int:
        """Soma o tamanho de todas as entradas."""
        return sum(p.stat().st_size for p in self.arquivos())

    def aplicar_teto(self) -> int:
        """Apaga as entradas mais antigas até caber no teto.

        Returns:
            Quantas entradas foram apagadas.
        """
        entradas = self.arquivos()
        total = sum(p.stat().st_size for p in entradas)
        apagadas = 0

        for caminho in entradas:
            if total <= self.teto_em_bytes:
                break
            tamanho = caminho.stat().st_size
            caminho.unlink(missing_ok=True)
            total -= tamanho
            apagadas += 1
            self.descartes += 1
            _log.debug("cache de disco descartou %s", caminho.name)

        if apagadas:
            _log.info("cache de disco liberou %d entrada(s) para caber no teto", apagadas)
        return apagadas

    def invalidar_produto(self, id_produto: str) -> int:
        """Apaga todas as entradas de um produto.

        Args:
            id_produto: Identificador do produto.

        Returns:
            Quantas entradas foram apagadas.
        """
        alvos = list(self.diretorio.glob(f"{id_produto}_*{SUFIXO}"))
        for alvo in alvos:
            alvo.unlink(missing_ok=True)
        if alvos:
            _log.info(
                "cache de disco invalidado para '%s': %d entrada(s)", id_produto, len(alvos)
            )
        return len(alvos)

    def limpar(self) -> int:
        """Apaga todas as entradas.

        Returns:
            Quantas entradas foram apagadas.
        """
        entradas = self.arquivos()
        for caminho in entradas:
            caminho.unlink(missing_ok=True)
        return len(entradas)

    def __len__(self) -> int:
        """Quantidade de entradas em disco."""
        return len(self.arquivos())
