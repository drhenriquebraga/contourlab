# -*- coding: utf-8 -*-
import json
import os
import time

NOME_REGISTRO_ANTIGO = "_overnight_servicos.json"


def apagar_registro_antigo(log=None, pasta=""):
    base = str(pasta or "").strip() or os.path.dirname(os.path.abspath(__file__))
    p = os.path.join(base, NOME_REGISTRO_ANTIGO)
    if not os.path.isfile(p):
        return False
    pausados = []
    try:
        with open(p, "r", encoding="utf-8") as f:
            d = json.load(f)
        pausados = [str(s.get("nome") or "")[:40]
                    for s in (d.get("servicos") or [])
                    if isinstance(s, dict) and s.get("acao") == "parado"]
    except Exception:
        pass
    try:
        os.remove(p)
    except Exception:
        return False
    if log:
        try:
            log(u"apagado o registro de um turno antigo que pausava servicos%s; "
                u"esta versao nao pausa servico nenhum, e o que ficou parado "
                u"volta no proximo arranque do Windows"
                % ((u" (%s)" % ", ".join(pausados)) if pausados else u""))
        except Exception:
            pass
    return True


def frota(status_dir, eu="", parado_min=20.0):
    fora = []
    base = str(status_dir or "").strip().strip('"')
    if not base:
        return fora
    eu = str(eu or "").strip().upper()
    try:
        nomes = sorted(os.listdir(base))
    except Exception:
        return fora
    agora = time.time()
    for n in nomes:
        if not n.lower().endswith(".json"):
            continue
        cam = os.path.join(base, n)
        try:
            with open(cam, "r", encoding="utf-8") as f:
                d = json.load(f)
            if not isinstance(d, dict):
                continue
        except Exception:
            fora.append({"maquina": n[:-5], "legivel": False, "muda_min": 0.0,
                         "atual": None, "concluidas": 0, "na_fila": 0,
                         "parada": True, "eu": (n[:-5].upper() == eu)})
            continue
        try:
            muda = max(0.0, (agora - os.path.getmtime(cam)) / 60.0)
        except Exception:
            muda = 0.0
        maq = str(d.get("maquina") or n[:-5])
        fora.append({
            "maquina": maq, "legivel": True, "muda_min": muda,
            "atual": d.get("atual"), "quando": d.get("quando") or "",
            "concluidas": int(d.get("concluidas_sessao") or 0),
            "na_fila": int(d.get("na_fila") or 0),
            "adiadas": int(d.get("adiadas") or 0),
            "pausado": bool(d.get("pausado")),
            "versao": str(d.get("versao") or ""),
            "erro": str(d.get("worker_erro") or "")[:200],
            "parada": muda > float(parado_min),
            "eu": (maq.upper() == eu),
        })
    return fora


def resumo_da_frota(maquinas):
    n = len(maquinas or ())
    paradas = len([m for m in (maquinas or ()) if m.get("parada")])
    trabalhando = len([m for m in (maquinas or ())
                       if not m.get("parada") and m.get("atual")])
    concluidas = sum(int(m.get("concluidas") or 0) for m in (maquinas or ()))
    adiadas = sum(int(m.get("adiadas") or 0) for m in (maquinas or ()))
    return {"n": n, "trabalhando": trabalhando, "paradas": paradas,
            "concluidas": concluidas, "adiadas": adiadas}
