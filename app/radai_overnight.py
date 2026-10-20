# -*- coding: utf-8 -*-
import json
import os
import socket
import time

VERSAO_OVERNIGHT = "1.0"

NOME_REGISTRO = "_overnight_servicos.json"

ENCERRAMENTOS = ("encerrada", "interrompida")


def _maquina():
    try:
        return (os.environ.get("COMPUTERNAME") or socket.gethostname()
                or "maquina")
    except Exception:
        return "maquina"


def caminho_do_registro(pasta=""):
    base = str(pasta or "").strip()
    if not base:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, NOME_REGISTRO)


def _ler(pasta=""):
    try:
        p = caminho_do_registro(pasta)
        if not os.path.isfile(p):
            return None
        with open(p, "r", encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else None
    except Exception:
        return None


def _gravar(dado, pasta=""):
    p = caminho_do_registro(pasta)
    tmp = "%s.%d.parcial" % (p, os.getpid())
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(dado, f, ensure_ascii=False, indent=1)
        os.replace(tmp, p)
        return True
    except Exception:
        try:
            os.remove(tmp)
        except Exception:
            pass
        return False


def _apagar(pasta=""):
    try:
        os.remove(caminho_do_registro(pasta))
        return True
    except Exception:
        return False


def ha_registro(pasta=""):
    return _ler(pasta) is not None


def estado(pasta=""):
    d = _ler(pasta) or {}
    servicos = d.get("servicos") or []
    pausados = [s for s in servicos if s.get("acao") == "parado"]
    desde = float(d.get("desde") or 0)
    return {
        "ativo": bool(d),
        "maquina": d.get("maquina") or _maquina(),
        "desde": desde,
        "horas": (max(0.0, time.time() - desde) / 3600.0) if desde else 0.0,
        "servicos": servicos,
        "pausados": [s.get("nome") for s in pausados],
        "n_pausados": len(pausados),
        "versao": d.get("versao") or "",
    }


def iniciar(pausar_servicos=True, log=None, pasta=""):
    def _diz(m):
        if log:
            try:
                log(m)
            except Exception:
                pass

    ja = _ler(pasta)
    if ja:
        _diz(u"o overnight run desta máquina já estava aberto desde %s"
             % _quando(ja.get("desde")))
        return {"ok": True, "ja_estava": True,
                "servicos": ja.get("servicos") or [],
                "msg": u"já estava aberto"}

    servicos = []
    if pausar_servicos:
        try:
            import radai_cleaner
            for s in radai_cleaner.estado_dos_servicos():
                servicos.append({"nome": s["nome"], "antes": s["estado"],
                                 "acao": "", "msg": ""})
        except Exception as e:
            _diz(u"não consegui ler o estado dos serviços (%s) — a noite abre "
                 u"assim mesmo, sem pausar nada" % str(e)[:120])
            servicos = []

    dado = {"versao": VERSAO_OVERNIGHT, "maquina": _maquina(),
            "desde": time.time(), "pid": os.getpid(), "servicos": servicos}
    if not _gravar(dado, pasta):
        _diz(u"não consegui gravar o registro do overnight run — os serviços "
             u"NÃO foram pausados, para não mexer na estação sem rastro")
        return {"ok": False, "ja_estava": False, "servicos": [],
                "msg": u"não consegui gravar o registro"}

    if not servicos:
        _diz(u"overnight run aberto (sem pausar serviço nenhum)")
        return {"ok": True, "ja_estava": False, "servicos": [],
                "msg": u"aberto"}

    import radai_cleaner
    parados = 0
    for s in servicos:
        if s["antes"] != "rodando":
            s["acao"] = "nao_mexido"
            continue
        r = radai_cleaner.parar_servico(s["nome"])
        s["acao"] = "parado" if r.get("ok") else "falhou"
        s["msg"] = str(r.get("msg") or "")[:160]
        if r.get("ok"):
            parados += 1
        _gravar(dado, pasta)
    _diz(u"overnight run aberto — %d serviço(s) pausado(s) para liberar "
         u"memória" % parados)
    return {"ok": True, "ja_estava": False, "servicos": servicos,
            "msg": u"%d pausado(s)" % parados}


def encerrar(log=None, pasta="", motivo="encerrada"):
    def _diz(m):
        if log:
            try:
                log(m)
            except Exception:
                pass

    d = _ler(pasta)
    if not d:
        return {"ok": True, "religados": 0, "falhas": [],
                "msg": u"não havia overnight run aberto"}

    servicos = d.get("servicos") or []
    religados, falhas = 0, []
    try:
        import radai_cleaner
    except Exception as e:
        _diz(u"não consegui carregar o limpador para religar os serviços "
             u"(%s). O registro FICA, e a próxima abertura do programa "
             u"tenta de novo." % str(e)[:120])
        return {"ok": False, "religados": 0,
                "falhas": [s.get("nome") for s in servicos],
                "msg": u"limpador indisponível"}

    for s in servicos:
        if s.get("acao") != "parado":
            continue
        r = radai_cleaner.iniciar_servico(s.get("nome"))
        if r.get("ok"):
            religados += 1
        else:
            falhas.append(u"%s (%s)" % (s.get("nome"), r.get("msg") or ""))
    _apagar(pasta)
    if falhas:
        _diz(u"overnight run %s — %d serviço(s) religado(s); %d não voltaram "
             u"e voltam sozinhos no próximo arranque da estação: %s"
             % (motivo, religados, len(falhas), "; ".join(falhas[:4])))
    else:
        _diz(u"overnight run %s — %d serviço(s) religado(s), a estação está "
             u"como estava" % (motivo, religados))
    return {"ok": True, "religados": religados, "falhas": falhas,
            "msg": u"%d religado(s)" % religados}


def restaurar_se_pendente(log=None, pasta=""):
    d = _ler(pasta)
    if not d:
        return {"ok": True, "havia": False, "religados": 0, "falhas": []}
    if log:
        try:
            log(u"havia um overnight run aberto desde %s que não foi "
                u"encerrado — a estação caiu ou o programa foi fechado à "
                u"força. Devolvendo os serviços." % _quando(d.get("desde")))
        except Exception:
            pass
    r = encerrar(log=log, pasta=pasta, motivo="interrompida")
    r["havia"] = True
    return r


def _quando(ts):
    try:
        return time.strftime("%d/%m %H:%M", time.localtime(float(ts or 0)))
    except Exception:
        return "?"


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
