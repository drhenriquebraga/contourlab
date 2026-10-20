# -*- coding: utf-8 -*-
import re

VERSAO_TERMOS = "1.0"

_LADOS = ("left", "right")


def normalizar(nome):
    t = re.sub(r"[^a-z0-9]+", "_", str(nome or "").lower()).strip("_")
    for lado in _LADOS:
        if t.startswith(lado + "_"):
            t = t[len(lado) + 1:] + "_" + lado
            break
    return t


SINONIMOS = {
    "bladder": "urinary_bladder",
    "small_bowel": "small_intestine",
    "iliac_vena_left": "iliac_vein_left",
    "iliac_vena_right": "iliac_vein_right",
}


def canonico(nome):
    k = normalizar(nome)
    return SINONIMOS.get(k, k)

FUNDIDAS = {
    "lung_left": ["left lung upper lobe", "left lung lower lobe"],
    "lung_right": ["right lung upper lobe", "right lung middle lobe",
                   "right lung lower lobe"],
    "carotids": ["left common carotid artery", "right common carotid artery"],
    "ribs_left": ["left rib %d" % i for i in range(1, 13)],
    "ribs_right": ["right rib %d" % i for i in range(1, 13)],
    "vertebrae_cervical": ["vertebrae C%d" % i for i in range(1, 8)],
    "vertebrae_thoracic": ["vertebrae T%d" % i for i in range(1, 13)],
    "vertebrae_lumbar": ["vertebrae L%d" % i for i in range(1, 6)],
    "great_vessels": ["aorta", "superior vena cava", "inferior vena cava",
                      "pulmonary vein", "brachiocephalic trunk",
                      "left brachiocephalic vein", "right brachiocephalic vein",
                      "left subclavian artery", "right subclavian artery"],
}


def _indice(nomes):
    fora = {}
    for n in nomes:
        fora.setdefault(canonico(n), []).append(n)
    return fora


def comparar(nomes_ts, nomes_nv):
    ts = list(nomes_ts or [])
    nv = list(nomes_nv or [])
    idx_nv = _indice(nv)
    usados_nv = set()

    exatas, fundidas = [], []
    for nome in sorted(ts):
        if nome in FUNDIDAS:
            pedacos = [p for p in FUNDIDAS[nome] if p in nv]
            if pedacos:
                fundidas.append({"ts": nome, "nv": pedacos,
                                 "relacao": "fundida",
                                 "nota": u"o nosso nome junta %d rótulo(s) do NV-Segment-CT"
                                         % len(pedacos)})
                usados_nv.update(pedacos)
            continue
        alvo = idx_nv.get(canonico(nome))
        if alvo:
            exatas.append({"ts": nome, "nv": alvo, "relacao": "exata",
                           "nota": ""})
            usados_nv.update(alvo)

    cobertos_ts = set(e["ts"] for e in exatas) | set(f["ts"] for f in fundidas)
    return {
        "exatas": exatas,
        "fundidas": fundidas,
        "so_ts": sorted(n for n in ts if n not in cobertos_ts),
        "so_nv": sorted(n for n in nv if n not in usados_nv),
    }


def comparaveis(nomes_ts, nomes_nv):
    c = comparar(nomes_ts, nomes_nv)
    return c["exatas"] + c["fundidas"]


def resumo(nomes_ts, nomes_nv):
    c = comparar(nomes_ts, nomes_nv)
    return {"exatas": len(c["exatas"]), "fundidas": len(c["fundidas"]),
            "so_ts": len(c["so_ts"]), "so_nv": len(c["so_nv"]),
            "comparaveis": len(c["exatas"]) + len(c["fundidas"])}
