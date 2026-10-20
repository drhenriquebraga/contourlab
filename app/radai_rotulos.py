# -*- coding: utf-8 -*-
import io
import json
import os
import time

import numpy as np

VERSAO_FORMATO = 1
PASTA = "_RadAI"
PREFIXO = "rotulos_"
EXTENSAO = ".npz"
# GUARDA: as duas tasks de vasos e vias aereas do pulmao devolvem nomes
# iguais; a antiga sai com sufixo para nao colidir com a nova.
SUFIXO_POR_TASK = {"lung_vessels_LEGACY": "_legacy"}


def nome_do_arquivo(uid):
    u = str(uid or "")
    return "%s%s%s" % (PREFIXO, u[-8:] if u else "semuid", EXTENSAO)


def caminho(pasta_serie, uid):
    return os.path.join(str(pasta_serie), PASTA, nome_do_arquivo(uid))


def _nome(task, rotulo, usados):
    nome = "%s%s" % (rotulo, SUFIXO_POR_TASK.get(task, ""))
    if nome in usados:
        nome = "%s__%s" % (nome, task)
    k = 2
    base = nome
    while nome in usados:
        nome = "%s_%d" % (base, k)
        k += 1
    return nome


def _volume_da_task(mapa):
    arr = getattr(mapa, "_arr", None)
    nomes = getattr(mapa, "_nomes", None)
    if arr is not None and isinstance(nomes, dict):
        a = np.asarray(arr)
        keep = np.zeros(int(a.max()) + 1 if a.size else 1, dtype=np.uint16)
        idx = {}
        for i, (rot, v) in enumerate(sorted(nomes.items(),
                                            key=lambda kv: kv[1]), start=1):
            if 0 <= int(v) < keep.size:
                keep[int(v)] = i
                idx[i] = rot
        return keep[np.clip(a, 0, keep.size - 1).astype(np.int64)], idx
    vol, idx = None, {}
    for i, rot in enumerate(sorted(mapa), start=1):
        m = np.asarray(mapa[rot], dtype=bool)
        if vol is None:
            vol = np.zeros(m.shape, dtype=np.uint16)
        vol[m] = i
        idx[i] = rot
    return vol, idx


def montar(cruas, achados=()):
    achados = set(achados or ())
    volumes, tabela, usados = {}, [], set()
    for n, task in enumerate(sorted(cruas or {})):
        mapa = cruas[task]
        if not mapa:
            continue
        vol, idx = _volume_da_task(mapa)
        if vol is None or not idx:
            continue
        chave = "t%d" % n
        volumes[chave] = vol
        for i in sorted(idx):
            nome = _nome(task, idx[i], usados)
            usados.add(nome)
            tabela.append({"chave": chave, "indice": int(i), "nome": nome,
                           "task": task, "rotulo": idx[i],
                           "achado": task in achados})
    return volumes, tabela


def geometria_de(ref):
    if ref is None:
        return None
    try:
        return {"spacing": [float(v) for v in ref.GetSpacing()],
                "origin": [float(v) for v in ref.GetOrigin()],
                "direction": [float(v) for v in ref.GetDirection()],
                "size": [int(v) for v in ref.GetSize()]}
    except Exception:
        return None


def gravar(pasta_serie, uid, cruas, ref=None, protocolos=(), modalidade="",
           achados=(), versao=""):
    volumes, tabela = montar(cruas, achados)
    if not volumes:
        raise ValueError(u"nenhuma task com rótulo para gravar")
    meta = {"formato": VERSAO_FORMATO, "uid": str(uid or ""),
            "protocolos": [str(p) for p in (protocolos or ())],
            "modalidade": str(modalidade or ""),
            "geometria": geometria_de(ref), "versao": str(versao or ""),
            "gravado": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "tabela": tabela}
    alvo = caminho(pasta_serie, uid)
    os.makedirs(os.path.dirname(alvo), exist_ok=True)
    tmp = alvo + ".parcial"
    with io.open(tmp, "wb") as f:
        np.savez_compressed(f, _meta=np.frombuffer(
            json.dumps(meta, ensure_ascii=True).encode("ascii"),
            dtype=np.uint8), **volumes)
    os.replace(tmp, alvo)
    return alvo


class Mapa(object):

    def __init__(self, meta, volumes):
        self.meta = meta
        self.tabela = list(meta.get("tabela") or ())
        self._vol = volumes
        self._por_nome = dict((t["nome"], t) for t in self.tabela)
        self.nomes = [t["nome"] for t in self.tabela]

    def mascara(self, nome):
        t = self._por_nome[nome]
        return np.asarray(self._vol[t["chave"]]) == int(t["indice"])

    def achados(self):
        return [t["nome"] for t in self.tabela if t.get("achado")]


def ler(pasta_serie, uid):
    alvo = caminho(pasta_serie, uid)
    if not os.path.isfile(alvo):
        return None
    try:
        with np.load(alvo, allow_pickle=False) as z:
            meta = json.loads(bytes(z["_meta"]).decode("ascii"))
            volumes = dict((k, np.array(z[k])) for k in z.files
                           if k != "_meta")
    except Exception:
        return None
    if int(meta.get("formato") or 0) != VERSAO_FORMATO:
        return None
    if uid and meta.get("uid") and str(meta["uid"]) != str(uid):
        return None
    return Mapa(meta, volumes)


def existe(pasta_serie, uid):
    return ler(pasta_serie, uid) is not None


def meta(pasta_serie, uid):
    alvo = caminho(pasta_serie, uid)
    if not os.path.isfile(alvo):
        return None
    try:
        with np.load(alvo, allow_pickle=False) as z:
            m = json.loads(bytes(z["_meta"]).decode("ascii"))
    except Exception:
        return None
    if not isinstance(m, dict) or int(m.get("formato") or 0) != VERSAO_FORMATO:
        return None
    if uid and m.get("uid") and str(m["uid"]) != str(uid):
        return None
    return m
