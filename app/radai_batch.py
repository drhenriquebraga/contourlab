# -*- coding: utf-8 -*-
import os
import re
import shutil
import tempfile
import threading
import time
import zipfile
from datetime import datetime

import radai_menu
import radai_web

VERSAO_LOTE = "1.0"

_TRAVA = threading.Lock()
_JOB = {"rodando": False, "cancelar": False, "pausar": False,
        "total": 0, "feitas": 0,
        "atual": "", "etapa": "", "comecou": "", "terminou": "",
        "resultados": [], "erro": "",
        "serie_desde": 0.0, "parte": ""}


_EXTRAIDOS = {}

_NAO_E_IMAGEM = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".ico", ".pdf",
                 ".html", ".htm", ".txt", ".xml", ".log", ".dll", ".ocx",
                 ".exe", ".lic", ".manifest", ".ini", ".cfg", ".zip", ".chm",
                 ".css", ".js"}


def _destino_pode_receber_paciente(destino):
    alvo = os.path.abspath(str(destino))
    raiz = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
    if _dentro(alvo, raiz):
        return (u"Não extraio exame para dentro da pasta do programa (%s). "
                u"Escolha uma pasta de trabalho fora dela." % raiz)
    sincronizada = os.environ.get("RADAI_ARVORE_SINCRONIZADA", "")
    if sincronizada and _dentro(alvo, os.path.abspath(sincronizada)):
        return (u"Não extraio exame para dentro de %s: essa árvore sincroniza "
                u"com a nuvem, e o exame iria junto." % os.path.abspath(sincronizada))
    return ""


def _dentro(alvo, pasta):
    return alvo == pasta or alvo.startswith(pasta + os.sep)


def preparar_zip(caminho, destino=None):
    caminho = str(caminho)
    if not os.path.isfile(caminho):
        return "", u"Não achei o arquivo %s." % caminho

    fora = _NAO_E_IMAGEM
    chave, estavel = None, None
    if destino is None:
        try:
            st = os.stat(caminho)
            chave = (os.path.abspath(caminho), int(st.st_mtime), st.st_size)
            import radai_archive as _arq
            estavel = _arq.pasta_da_extracao_do_zip(caminho) or None
        except Exception:
            chave, estavel = None, None
        if chave in _EXTRAIDOS and os.path.isdir(_EXTRAIDOS[chave]):
            return _EXTRAIDOS[chave], ""
        if estavel and os.path.isdir(estavel) and os.listdir(estavel):
            _EXTRAIDOS[chave] = estavel
            return estavel, ""

    base = destino or estavel or tempfile.mkdtemp(prefix="radai_portal_")
    if base is estavel:
        os.makedirs(base, exist_ok=True)
    erro = _destino_pode_receber_paciente(base)
    if erro:
        return "", erro
    try:
        with zipfile.ZipFile(caminho) as z:
            n = 0
            for info in z.infolist():
                if info.is_dir():
                    continue
                if os.path.splitext(info.filename)[1].lower() in fora:
                    continue
                alvo = os.path.abspath(os.path.join(base, info.filename))
                if not alvo.startswith(os.path.abspath(base) + os.sep):
                    continue
                z.extract(info, base)
                n += 1
    except zipfile.BadZipFile:
        return "", u"O arquivo não é um .zip válido."
    except Exception as e:
        return "", u"Não consegui extrair: %s" % e
    if not n:
        return "", u"O .zip não tem nenhum arquivo que possa ser imagem."
    if chave is not None:
        _EXTRAIDOS[chave] = base
    return base, ""


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


PASTAS_DE_SISTEMA = frozenset((
    "windows", "program files", "program files (x86)", "programdata",
    "$recycle.bin", "system volume information", "recovery",
    "msocache", "perflogs", "appdata", "site-packages", "__pycache__",
    ".git", "node_modules",
))

TETO_ARQUIVOS = 200_000

_TAGS = ["SeriesInstanceUID", "Modality", "PatientID", "PatientName",
         "SeriesDate", "SeriesTime",
         "StudyDate",
         "SeriesDescription", "SeriesNumber", "SliceThickness",
         "ConvolutionKernel", "StudyInstanceUID", "ImagePositionPatient",
         "ImageOrientationPatient"]


def _nome_de_pessoa(valor):
    try:
        if valor is None:
            return ""
        partes = [p.strip() for p in str(valor).split("^")]
        familia = partes[0] if partes else ""
        dados = " ".join(x for x in partes[1:3] if x)
        nome = ("%s %s" % (dados, familia)).strip()
        return " ".join(nome.split())[:60]
    except Exception:
        return ""


def _cabecalho(fonte):
    import pydicom
    if isinstance(fonte, str):
        try:
            import radai_dicom
            vale, _porque = radai_dicom.vale_abrir(fonte)
            if not vale:
                return None
        except Exception:
            pass
    try:
        return pydicom.dcmread(fonte, stop_before_pixels=True, force=True,
                               specific_tags=_TAGS)
    except Exception:
        return None


def _juntar(achados, ds, pasta, zip_="", modalidades=("CT",)):
    if ds is None:
        return False
    mod = str(getattr(ds, "Modality", "")).upper()
    if mod not in modalidades:
        return False
    uid = str(getattr(ds, "SeriesInstanceUID", "") or "")
    if not uid:
        return False
    k = getattr(ds, "ConvolutionKernel", "")
    if isinstance(k, (list, tuple)):
        k = k[0] if k else ""
    s = achados.setdefault(uid, {
        "uid": uid, "pasta": pasta, "zip": zip_, "cortes": 0,
        "modalidade": mod,
        "pid": str(getattr(ds, "PatientID", "") or ""),
        "nome": _nome_de_pessoa(getattr(ds, "PatientName", None)),
        "date": str(getattr(ds, "SeriesDate", "")
                    or getattr(ds, "StudyDate", "") or ""),
        "hora": str(getattr(ds, "SeriesTime", "") or "")[:6],
        "desc": str(getattr(ds, "SeriesDescription", "") or "")[:60],
        "numero": _num(getattr(ds, "SeriesNumber", None)),
        "espessura_mm": _num(getattr(ds, "SliceThickness", None)),
        "kernel": str(k or "")[:20],
        "estudo": str(getattr(ds, "StudyInstanceUID", "") or ""),
        "_zs": set(), "axial": _e_axial(ds)})
    s["cortes"] += 1
    try:
        s["_zs"].add(_posicao_na_normal(ds))
    except Exception:
        pass
    return True


def _posicao_na_normal(ds):
    p = [float(v) for v in getattr(ds, "ImagePositionPatient")]
    try:
        o = [float(v) for v in getattr(ds, "ImageOrientationPatient")]
    except Exception:
        o = []
    if len(o) != 6 or len(p) != 3:
        return round(p[2], 3)
    r, c = o[:3], o[3:]
    n = (r[1] * c[2] - r[2] * c[1],
         r[2] * c[0] - r[0] * c[2],
         r[0] * c[1] - r[1] * c[0])
    norma = (n[0] ** 2 + n[1] ** 2 + n[2] ** 2) ** 0.5
    if norma < 1e-6:
        return round(p[2], 3)
    return round((p[0] * n[0] + p[1] * n[1] + p[2] * n[2]) / norma, 3)


def _e_axial(ds):
    import radai_triage
    return radai_triage.orientacao_axial(
        getattr(ds, "ImageOrientationPatient", None))


def _espessura_real(s):
    zs = s.get("_zs") or set()
    if len(zs) < 2:
        return None
    d = (max(zs) - min(zs)) / (len(zs) - 1)
    return d if 0.05 <= d <= 20.0 else None


def espiar_zip(caminho, teto=500, modalidades=("CT",)):
    achados = {}
    try:
        with zipfile.ZipFile(caminho) as z:
            for info in z.infolist():
                if info.is_dir() or info.file_size < 256:
                    continue
                if os.path.splitext(info.filename)[1].lower() in _NAO_E_IMAGEM:
                    continue
                try:
                    with z.open(info) as f:
                        ds = _cabecalho(f)
                except Exception:
                    continue
                _juntar(achados, ds, os.path.dirname(info.filename),
                        zip_=caminho, modalidades=modalidades)
                if len(achados) > teto:
                    break
    except zipfile.BadZipFile:
        return [], u"%s não é um .zip válido." % os.path.basename(caminho)
    except Exception as e:
        return [], u"Não consegui ler %s: %s" % (os.path.basename(caminho), e)
    return list(achados.values()), ""


def resolver_pasta(s):
    if not (s or {}).get("zip"):
        return (s or {}).get("pasta", ""), ""
    ja = (s or {}).get("pasta") or ""
    if ja and os.path.isabs(ja) and os.path.isdir(ja):
        return ja, ""
    base, erro = preparar_zip(s["zip"])
    if erro:
        return "", erro
    dentro = os.path.join(base, *[p for p in (s.get("pasta") or "").split("/") if p])
    return (dentro if os.path.isdir(dentro) else base), ""


MODALIDADES_DA_TELA = ("CT", "MR")


def pulada_no_lote(nome):
    return nome == "_RadAI" or nome.lower() in PASTAS_DE_SISTEMA


def ler_pasta_do_lote(achados, zips, raiz, arquivos, modalidades=("CT",),
                      incluir_zips=False, teto=500, parar=None, ao_ler=None,
                      ao_atualizar=None, finalizar_encontradas=False):
    vistos = 0
    aceitas_ao_parar = None
    ultima = 0.0
    for nome in arquivos:
        if parar is not None and parar():
            if not finalizar_encontradas:
                break
            if aceitas_ao_parar is None:
                aceitas_ao_parar = set(achados)
            if not aceitas_ao_parar:
                break
        fp = os.path.join(raiz, nome)
        if incluir_zips and nome.lower().endswith(".zip"):
            zips.append(fp)
            continue
        vistos += 1
        if ao_ler is not None:
            ao_ler()
        ds = _cabecalho(fp)
        if aceitas_ao_parar is not None and str(getattr(ds, "SeriesInstanceUID", "")) not in aceitas_ao_parar:
            continue
        _juntar(achados, ds, raiz, modalidades=modalidades)
        if (ao_atualizar is not None and any(s["cortes"] >= 2 for s in achados.values())
                and time.monotonic() - ultima >= 0.25):
            ao_atualizar(achados)
            ultima = time.monotonic()
        if len(achados) > teto:
            break
    return vistos


def varrer(pasta, modalidades=("CT",), min_cortes=20, teto=500, marcadores=None,
           incluir_zips=False, descartadas=None):
    achados = {}
    zips = []
    vistos = 0
    for raiz, dirs, arquivos in os.walk(str(pasta)):
        dirs[:] = [d for d in dirs if not pulada_no_lote(d)]
        vistos += ler_pasta_do_lote(achados, zips, raiz, arquivos, modalidades,
                                    incluir_zips, teto)
        if vistos > TETO_ARQUIVOS:
            print("[varrer] parei em %d arquivos vistos em %s - o teto "
                  "e %d. Aponte a pasta do exame, e nao a raiz do disco."
                  % (vistos, pasta, TETO_ARQUIVOS))
            break
    return fechar_varredura_do_lote(achados, zips, modalidades, min_cortes,
                                    teto, marcadores, descartadas)


def fechar_varredura_do_lote(achados, zips, modalidades=("CT",), min_cortes=20,
                             teto=500, marcadores=None, descartadas=None,
                             parar=None):
    fora = [s for s in achados.values() if s["cortes"] >= min_cortes]
    if descartadas is not None:
        for s in achados.values():
            if s["cortes"] < min_cortes:
                descartadas.append({"cortes": s["cortes"],
                                    "pasta": s.get("pasta", "")})
    for s in fora:
        s["curto"] = s["uid"][-8:]
        s["tem_rs"] = bool(_rs_da_serie(s["pasta"], s["uid"]))
        _fixar_espessura(s)
        s.update(_situacao(s, marcadores))

    for z in zips:
        if parar is not None and parar():
            break
        dentro, erro = espiar_zip(z, teto=teto, modalidades=modalidades)
        if erro:
            continue
        for s in dentro:
            if s["cortes"] < min_cortes:
                continue
            s["curto"] = s["uid"][-8:]
            _fixar_espessura(s)
            s["tem_rs"] = False
            s.update(_situacao(s, None))
            fora.append(s)

    try:
        import radai_topography as _tp
        for x in fora:
            x["radai_na_pasta"] = _tp.entregas_a_substituir(
                _rs_da_serie(x.get("pasta"), x.get("uid")))
    except Exception:
        for x in fora:
            x.setdefault("radai_na_pasta", [])
    return sorted(fora, key=lambda s: (s["pid"], s["date"], s["uid"]))


TETO_SERIES_DA_TELA = 500


def _lote_iniciar(job):
    alvo = job["pasta"]
    if alvo.lower().endswith(".zip") and os.path.isfile(alvo):
        alvo, erro = preparar_zip(alvo)
        if erro:
            job["erro"] = erro
            return
    job["raiz"] = alvo
    job["dados"] = {"achados": {}, "zips": [],
                    "piso": int(_CFG.get("min_cortes", 20)),
                    "trava": threading.RLock(), "parciais": {}, "prontas": []}


def _lote_ler(job, pasta, nomes):
    import radai_varrer
    d = job["dados"]
    achados, zips = {}, []
    def parcial(atual):
        with d["trava"]:
            d["parciais"][pasta] = [dict(s) for s in atual.values() if s["cortes"] >= 2]
        radai_varrer.publicar(job, _lote_linhas(job))
    n = ler_pasta_do_lote(
        achados, zips, pasta, nomes, MODALIDADES_DA_TELA, True,
        TETO_SERIES_DA_TELA, parar=lambda: job["parado"],
        ao_ler=lambda: radai_varrer.contar_arquivo(job),
        ao_atualizar=parcial, finalizar_encontradas=True)
    with d["trava"]:
        d["parciais"].pop(pasta, None)
        d["zips"].extend(zips)
        for uid, s in achados.items():
            if uid in d["achados"]:
                antes = d["achados"][uid]
                antes["cortes"] += s["cortes"]
                antes["_zs"].update(s.get("_zs") or ())
            else:
                d["achados"][uid] = s
        copia = {u: dict(s, _zs=set(s.get("_zs") or ())) for u, s in d["achados"].items()}
        fechadas = fechar_varredura_do_lote(copia, [], MODALIDADES_DA_TELA,
                                            d["piso"], TETO_SERIES_DA_TELA,
                                            _CFG.get("marcadores"))
        d["prontas"] = completar_da_tela(fechadas, job["raiz"], d["piso"], [])["series"]
    return n > 0


def _lote_linhas(job):
    d = job["dados"]
    with d["trava"]:
        fora = [dict(s, carregando=False) for s in d["prontas"]]
        for grupo in d["parciais"].values():
            fora.extend({"curto": s["uid"][-8:], "desc": s.get("desc") or u"",
                         "modalidade": s.get("modalidade") or u"",
                         "cortes": s["cortes"], "date": s.get("date") or u"",
                         "carregando": True, "bilhete": None,
                         "recusa": u"Lendo os cortes da série…"} for s in grupo)
        return fora


def _lote_fechar(job):
    d = job["dados"]
    curtas = []
    series = fechar_varredura_do_lote(
        d["achados"], d["zips"], MODALIDADES_DA_TELA, d["piso"],
        TETO_SERIES_DA_TELA, _CFG.get("marcadores"), curtas,
        parar=lambda: job["parado"])
    r = completar_da_tela(series, job["raiz"], d["piso"], curtas)
    return r.pop("series"), r


def completar_da_tela(series, alvo, piso, curtas):
    estudos = set(s.get("estudo") or s.get("pid") or "" for s in series)
    um_exame = len(estudos) == 1 and len(series) > 1
    try:
        import radai_triage
        series = radai_triage.escolher_para_contorno(series)
    except Exception:
        pass
    try:
        import radai_dicom as _rd
        for _s in series:
            _s["espessura_laudo"] = _rd.laudo_de_espessura(
                _s.get("espessura_mm"))
    except Exception:
        pass
    _com_bilhete(series)
    return {"series": series, "pasta": alvo, "um_exame": um_exame,
            "piso": piso,
            "curtas": sorted((c["cortes"] for c in curtas),
                             reverse=True)[:20]}


def _fixar_espessura(s):
    real = _espessura_real(s)
    s["espessura_declarada_mm"] = s.get("espessura_mm")
    if real is not None:
        s["espessura_mm"] = round(real, 2)
    s["posicoes"] = len(s.get("_zs") or ())
    s.pop("_zs", None)
    return s


def _maquina_desta_estacao():
    return str(_CFG.get("maquina") or "")





def _desconto_do_entregue():
    try:
        import radai_sets
        return radai_sets.desconto_do_entregue()
    except Exception:
        return False


CHAVES_DA_COMPARACAO = ("ts", "nv", "cads", "mse")
MOTORES_DO_LOTE = ("nv", "cads", "mse", "hnlnl", "cranio_ct")
CHAVES_DOS_MOTORES_DO_FULL = ("cranio_ct",)
MOTORES_DA_COMPARACAO = ("nv", "cads", "mse")
CHAVE_DOS_NIVEIS = "hnlnl"
PROTOCOLO_TORAX = "torax_mama"
CHAVES_LEGADAS_DA_V82 = ("estudos", "tasks_extra", "motores_extra",
                         "modo_v81", "topo", "topo_motivo")
TETO_OAR_FORA = 300


def _md():
    import radai_modes
    return radai_modes


def _sim(v):
    if isinstance(v, bool):
        return v
    try:
        return str(v).strip().lower() in ("1", "true", "sim", "on", "yes")
    except Exception:
        return False


def _modalidade_da_serie(serie):
    return _md()._modalidade((serie or {}).get("modalidade") or "CT")


def normalizar_comparacao(valor, modalidade="CT"):
    fora = dict((k, 0) for k in CHAVES_DA_COMPARACAO)
    if isinstance(valor, dict):
        for k in CHAVES_DA_COMPARACAO:
            fora[k] = 1 if _sim(valor.get(k)) else 0
    elif valor:
        for k in _md().normalizar_escolhidas(valor):
            if k in fora:
                fora[k] = 1
    if _md()._modalidade(modalidade) == "MR":
        for k in MOTORES_DA_COMPARACAO:
            fora[k] = 0
    return fora


def normalizar_oar_fora(valor):
    fora = []
    for k in _md().normalizar_escolhidas(valor):
        k = str(k)[:64]
        if k and k not in fora:
            fora.append(k)
        if len(fora) >= TETO_OAR_FORA:
            break
    return tuple(fora)


def escolha_da_serie(serie):
    md = _md()
    s = serie or {}
    mod = md._modalidade(s.get("modalidade") or "CT")
    modo = md.normalizar_modo(s.get("modo"))
    e = {"modo": modo, "modalidade": mod, "protocolos": (), "tasks": {},
         "comparacao": normalizar_comparacao({}, mod), "oar_fora": (),
         "protocolos_3d": (), "protocolo_proprio": u"",
         "achado_declarado": False}
    if modo != md.MODO_PERSO:
        return e
    e["protocolo_proprio"] = str(s.get("protocolo_proprio") or u"")[:64]
    # GUARDA: so o `true` literal: a tela so o manda depois da confirmacao.
    e["achado_declarado"] = s.get("achado_declarado") is True
    e["protocolos"] = (() if e["protocolo_proprio"] else
                       tuple(md.normalizar_protocolos(s.get("protocolos"),
                                                      mod)))
    e["protocolos_3d"] = tuple(md.normalizar_protocolos_3d(
        s.get("protocolos_3d"), mod))
    e["tasks"] = dict(md.normalizar_chaves(s.get("tasks")))
    e["comparacao"] = normalizar_comparacao(s.get("comparacao"), mod)
    e["oar_fora"] = normalizar_oar_fora(s.get("oar_fora"))
    return e


def tela_declarou(serie):
    return bool(str((serie or {}).get("modo") or u"").strip())


def quem_decide_as_tasks(lista_explicita, serie):
    return "lista" if (lista_explicita and not tela_declarou(serie)) \
        else "modo"


def base_alimenta_o_entregue(modalidade):
    import engine
    import radai_modes as _md
    return bool(engine.alimenta_o_entregue(_md.base_de(modalidade)))


def _achados_e_permitidas():
    try:
        import engine
        return (getattr(engine, "TASKS_PERMITIDAS", None),
                tuple(getattr(engine, "TASKS_DE_ACHADO", ()) or ()))
    except Exception:
        return None, ()


def _chaves_de_task(escolha):
    return dict((t, v) for t, v in (escolha.get("tasks") or {}).items()
                if t != CHAVE_DOS_NIVEIS
                and t not in CHAVES_DOS_MOTORES_DO_FULL)


def protocolo_proprio_da_escolha(escolha, log=None):
    ident = (escolha or {}).get("protocolo_proprio")
    if not ident:
        return None
    try:
        import radai_sets as _rs
        p = _rs.protocolo_proprio(ident, (escolha or {}).get("modalidade")
                                  or "CT")
    except Exception:
        p = None
    if p is None and log:
        log(u"ALERTA: o protocolo proprio %s nao existe nesta estacao para "
            u"esta modalidade: o STUDY sai pela lista padrao" % ident)
    return p


def tasks_do_protocolo_proprio(escolha, achados=()):
    p = protocolo_proprio_da_escolha(escolha)
    if p is None:
        return (), ()
    import radai_sets as _rs
    ts = _rs.tasks_do_protocolo(p)
    ach = set(achados or ())
    return (tuple(t for t in ts if t not in ach),
            tuple(t for t in ts if t in ach))


def tasks_do_perso(escolha, permitidas=None, achados=(), catalogo=None):
    md = _md()
    fora = list(md.tasks_do_personalizado(
        escolha.get("protocolos") or (), _chaves_de_task(escolha),
        escolha.get("modalidade") or "CT", permitidas=permitidas,
        achados=achados, catalogo=catalogo))
    anat, de_achado = tasks_do_protocolo_proprio(escolha, achados)
    md.conferir_regra_a(md.PROTOCOLO, anat, achados)
    # GUARDA: o achado do protocolo proprio roda so declarado nesta execucao.
    extra = list(anat) + (list(de_achado) if escolha.get("achado_declarado")
                          else [])
    if extra:
        extra = list(md._filtrar(extra, md._modalidade(
            escolha.get("modalidade") or "CT"), permitidas, catalogo))
        md.conferir_regra_a(md.MARCADO, extra, ())
    for t in extra:
        if t not in fora:
            fora.append(t)
    return tuple(fora)


def motores_do_perso(escolha, com_estudo=True):
    md = _md()
    mod = escolha.get("modalidade") or "CT"
    comp = escolha.get("comparacao") or {}
    fora = dict((m, bool(comp.get(m))) for m in MOTORES_DA_COMPARACAO)
    hnl = CHAVE_DOS_NIVEIS in md.motores_dos_protocolos(
        escolha.get("protocolos") or (), mod)
    chaves = escolha.get("tasks") or {}
    if CHAVE_DOS_NIVEIS in chaves:
        hnl = bool(chaves[CHAVE_DOS_NIVEIS])
    if com_estudo and CHAVE_DOS_NIVEIS in md.motores_do_estudo_3d(
            escolha.get("protocolos_3d") or (), mod):
        hnl = True
    fora["hnlnl"] = bool(hnl) and md._modalidade(mod) == "CT"
    dos_protocolos = md.motores_dos_protocolos(escolha.get("protocolos") or (),
                                               mod)
    for c in CHAVES_DOS_MOTORES_DO_FULL:
        liga = c in dos_protocolos
        if c in chaves:
            liga = bool(chaves[c])
        fora[c] = bool(liga) and md._modalidade(mod) == "CT"
    _pp = protocolo_proprio_da_escolha(escolha)
    if _pp is not None and md._modalidade(mod) == "CT":
        import radai_sets as _rs
        for c in _rs.motores_do_protocolo(_pp):
            if c in fora:
                fora[c] = True
    return fora


def niveis_so_do_estudo(serie):
    e = escolha_da_serie(serie)
    if e["modo"] != _md().MODO_PERSO or not e["protocolos_3d"]:
        return False
    return (motores_do_perso(e)["hnlnl"]
            and not motores_do_perso(e, com_estudo=False)["hnlnl"])


def motores_da_serie(serie, incluir_nv=None, regioes=()):
    e = escolha_da_serie(serie)
    if e["modo"] == _md().MODO_PERSO:
        return motores_do_perso(e), e["modo"]
    fora = dict((m, False) for m in MOTORES_DO_LOTE)
    if e["modo"] == _md().MODO_FAST:
        for c in _md().motores_do_fast(regioes, e["modalidade"]):
            fora[c] = True
    return fora, e["modo"]


def ts_cru_pedido(serie):
    e = escolha_da_serie(serie)
    return e["modo"] == _md().MODO_PERSO and bool(e["comparacao"].get("ts"))


def torax_pedido(serie):
    e = escolha_da_serie(serie)
    if e["modo"] == _md().MODO_PERSO and PROTOCOLO_TORAX in e["protocolos"]:
        return True
    return None


def tasks_iniciais(serie, lista_explicita=None, log=None):
    md = _md()
    s = serie or {}
    lista = [t for t in (lista_explicita or ()) if t]
    mod = _modalidade_da_serie(s)
    if quem_decide_as_tasks(lista, s) == "lista":
        if log:
            log("lista explicita do chamador: %s (a serie nao declarou modo)"
                % ", ".join(lista))
        return _pela_modalidade(lista, mod, log), "lista"
    e = escolha_da_serie(s)
    if e["modo"] != md.MODO_PERSO:
        return _pela_modalidade((md.base_de(mod),), mod, log), e["modo"]
    permitidas, achados = _achados_e_permitidas()
    tasks = tasks_do_perso(e, permitidas=permitidas, achados=achados,
                           catalogo=_catalogo_de_tasks())
    if log:
        log(md.descricao_da_escolha(md.MARCADO, tasks, achados,
                                    protocolos=e["protocolos"]))
        _fr_per = md.frase_do_pericardio_desligado(
            _chaves_de_task(e), e.get("modalidade") or mod,
            protocolos=e.get("protocolos") or (),
            protocolos_3d=e.get("protocolos_3d") or ())
        if _fr_per:
            log(_fr_per)
        _pp = protocolo_proprio_da_escolha(e, log=log)
        if _pp is not None:
            _anat, _ach = tasks_do_protocolo_proprio(e, achados)
            log(u"protocolo proprio «%s»: tasks %s"
                % (_pp.get("nome") or e["protocolo_proprio"],
                   u", ".join(_anat) or u"so a base"))
            if _ach and e.get("achado_declarado"):
                log(u"ACHADO: %s declarado no protocolo proprio «%s» nesta "
                    u"execucao" % (u", ".join(_ach), _pp.get("nome") or u"?"))
            elif _ach:
                log(u"ACHADO do protocolo proprio «%s» (%s) NAO roda: a "
                    u"deteccao nao foi declarada nesta execucao"
                    % (_pp.get("nome") or u"?", u", ".join(_ach)))
    if e["protocolos_3d"]:
        est = md.tasks_do_estudo_3d(e["protocolos_3d"], mod,
                                    permitidas=permitidas, achados=achados,
                                    catalogo=_catalogo_de_tasks())
        if log:
            log(md.descricao_da_escolha(md.ESTUDO, est, achados,
                                        protocolos=e["protocolos_3d"]))
        tasks = tuple(tasks) + tuple(t for t in est if t not in tasks)
    return _pela_modalidade(tasks, mod, log), e["modo"]


def tasks_so_do_estudo(serie):
    try:
        e = escolha_da_serie(serie)
        if e["modo"] != _md().MODO_PERSO or not e["protocolos_3d"]:
            return ()
        permitidas, achados = _achados_e_permitidas()
        mod = e.get("modalidade") or "CT"
        rt = set(tasks_do_perso(e, permitidas=permitidas, achados=achados,
                                catalogo=_catalogo_de_tasks()))
        est = _md().tasks_do_estudo_3d(e["protocolos_3d"], mod,
                                       permitidas=permitidas,
                                       achados=achados,
                                       catalogo=_catalogo_de_tasks())
        return tuple(t for t in est if t not in rt)
    except Exception:
        return ()


def cruas_do_entregue(cruas, so_do_estudo):
    fora = set(so_do_estudo or ())
    return dict((t, v) for t, v in (cruas or {}).items() if t not in fora)


ORDEM_DO_FAST = ("trunk_cavities", "breasts", "pleural_pericard_effusion")


def _na_ordem_do_fast(tasks):
    pos = dict((t, i) for i, t in enumerate(ORDEM_DO_FAST))
    return sorted(tasks, key=lambda t: (pos.get(t, len(pos)),
                                        list(tasks).index(t)))


def tasks_depois_da_base(modo, regioes, coracao_cm3=None, modalidade="CT",
                         permitidas=None, achados=(), catalogo=None):
    md = _md()
    if modo == md.MODO_FAST:
        lista = md.tasks_do_fast(regioes, coracao_cm3, modalidade,
                                 permitidas=permitidas, achados=achados,
                                 catalogo=catalogo)
        return tuple(_na_ordem_do_fast(list(lista[1:])))
    if modo == md.MODO_AUTO:
        lista = md.tasks_da_topografia(regioes, modalidade,
                                       permitidas=permitidas,
                                       achados=achados, catalogo=catalogo,
                                       coracao_cm3=coracao_cm3)
        return tuple(lista[1:])
    return ()


def tasks_previstas(serie, lista_explicita=None):
    try:
        tasks, _origem = tasks_iniciais(serie, lista_explicita)
    except Exception:
        raise
    return tuple(tasks)


def recorte_no_corpo_da_estacao():
    v = _CFG.get("recorte_no_corpo")
    return None if v is None else bool(v)


def _pela_modalidade(tasks, modalidade, log=None):
    try:
        import radai_tasks as _rt
        fn = _rt.tasks_da_serie
    except Exception as e:
        if log:
            log("nao consegui aplicar a regra da modalidade (%s: %s) - a "
                "lista segue como veio: %s"
                % (type(e).__name__, str(e)[:80], ", ".join(tasks)))
        return tuple(tasks)
    saida = tuple(fn(list(tasks), modalidade, log=log) or ())
    if log and list(saida) != list(tasks):
        log("pela modalidade da serie (%s): %s -> %s"
            % (modalidade, ", ".join(tasks) or "(vazio)",
               ", ".join(saida) or "(vazio)"))
    return saida


def _com_escolhas_da_tela(corpo):
    md = _md()
    series = list((corpo or {}).get("series") or [])
    modo_do_corpo = str((corpo or {}).get("modo") or u"").strip()
    fora = []
    for s in series:
        d = dict(s or {})
        legado = [k for k in CHAVES_LEGADAS_DA_V82 if k in d]
        for k in legado:
            d.pop(k, None)
        if not str(d.get("modo") or u"").strip() and modo_do_corpo:
            d["modo"] = modo_do_corpo
        e = escolha_da_serie(d)
        d["modo"] = e["modo"]
        if e["modo"] == md.MODO_PERSO:
            d["protocolos"] = list(e["protocolos"])
            d["tasks"] = dict(e["tasks"])
            d["comparacao"] = dict(e["comparacao"])
            d["oar_fora"] = list(e["oar_fora"])
            if e["protocolos_3d"]:
                d["protocolos_3d"] = list(e["protocolos_3d"])
            else:
                d.pop("protocolos_3d", None)
            for k in ("protocolo_proprio", "achado_declarado"):
                if e[k]:
                    d[k] = e[k]
                else:
                    d.pop(k, None)
        else:
            for k in ("protocolos", "tasks", "comparacao", "oar_fora",
                      "protocolos_3d", "protocolo_proprio",
                      "achado_declarado"):
                d.pop(k, None)
        if legado:
            d["legado_v82"] = sorted(legado)
        else:
            d.pop("legado_v82", None)
        if d.get("substituir") is True:
            d["substituir"] = True
        else:
            d.pop("substituir", None)
        fora.append(d)
    return fora


def _catalogo_de_tasks():
    try:
        import radai_tasks
        return radai_tasks.CATALOGO
    except Exception:
        return None



AJUDA_DOS_MODOS = (u"FAST e AUTO decidem sozinhos, pela anatomia que a base "
                   u"desenhou; o PERSONALIZADO abre as escolhas desta série. "
                   u"Nenhum modo roda ACHADO sem a chave da própria task.")
MODOS_DA_TELA = (
    {"cod": "fast", "rotulo": u"FAST",
     "ajuda": (u"Só o que o STUDY precisa, o mais rápido: a base e, no tórax, "
               u"as cavidades, a mama e o derrame (o pericárdico entra no "
               u"coração, e o pleural sai dos pulmões). Grava só o "
               u"RadAI_STUDY_Fast, com os pontos de cada contorno reduzidos "
               u"— sem FULL, sem TS cru, sem plugins e sem comparação.")},
    {"cod": "auto", "rotulo": u"AUTO",
     "ajuda": (u"O que a anatomia pede: a base roda primeiro, mede as regiões "
               u"do corpo na série e roda as tasks que completam o FULL "
               u"naquela região, e os níveis cervicais quando o pescoço "
               u"aparece. Grava o FULL e o RadAI_STUDY. É o que o vigia roda "
               u"toda noite.")},
    {"cod": "perso", "rotulo": u"PERSONALIZADO",
     "ajuda": (u"Você escolhe: protocolos, task a task e a comparação com "
               u"outros modelos. Grava o FULL, o RadAI_STUDY (menos o que você "
               u"tirar com o «x»), um arquivo por plugin pedido e, se "
               u"ligados, o TS cru e os modelos de comparação.")},
)

COMPARACAO_DA_TELA = (
    {"cod": "ts", "rotulo": u"TS cru (não corrigido)", "modelo": None,
     "so_tc": False,
     "ajuda": (u"A saída do TotalSegmentator como ela é, sem nenhum "
               u"pós-processamento nosso, num arquivo próprio (RadAI_TS). É "
               u"a linha de base para comparar com o FULL.")},
    {"cod": "nv", "rotulo": u"NV-Segment-CT", "modelo": "nv_segment_ct",
     "so_tc": True, "ajuda": None},
    {"cod": "cads", "rotulo": u"CADS", "modelo": "cads_open",
     "so_tc": True, "ajuda": None},
    {"cod": "mse", "rotulo": u"MOOSE", "modelo": "moose",
     "so_tc": True, "ajuda": None},
)


FONTE_DA_VELOCIDADE_DO_MOTOR = (u"declarada lenta no registro do motor; não "
                                u"medida contra a base")


def versao_do_totalsegmentator():
    try:
        from importlib import metadata
        return str(metadata.version("TotalSegmentator"))
    except Exception:
        pass
    try:
        import json
        import radai_records as _rg
        p = os.path.join(_rg._raiz_do_programa(), "_requisitos.json")
        if os.path.isfile(p):
            with open(p, encoding="utf-8") as f:
                v = json.load(f).get("totalsegmentator")
            if v:
                return str(v)
    except Exception:
        pass
    return None


def estruturas_da_task(task):
    try:
        import engine
        import radai_tasks as _rt
    except Exception:
        return [], u""
    try:
        cm = (engine.TS_CLASS_MAP or {}).get(
            _rt.nome_na_biblioteca(task))
        if cm:
            return [str(v) for _k, v in sorted(dict(cm).items())], u"class_map"
    except Exception:
        pass
    try:
        fam = _rt.familia_da_task(task)
        nomes = sorted(k for k, fontes in (engine.TS_MAP or {}).items()
                       if task in (fontes or {}) or fam in (fontes or {}))
        if nomes:
            return nomes, u"ts_map"
    except Exception:
        pass
    return [], u""


def _o_que_alimenta(task):
    try:
        import radai_sets as _rs
        if _rs.task_do_full(task):
            return "full", u"FULL"
        p = _rs.PLUGIN_DA_TASK.get(task)
        if p:
            return "arquivo", p.get("nome") or task
    except Exception:
        pass
    return "", u""


def _avisos_da_task(task, item):
    fora = []
    if item.get("achado"):
        fora.append(u"ACHADO: detecção de alteração; só roda com a chave da "
                    u"própria task.")
    c = item.get("contraste")
    if c and c != "nao":
        try:
            import radai_tasks as _rt
            txt = _rt.AJUDA_CONTRASTE.get(c)
        except Exception:
            txt = None
        fora.append(txt or (u"contraste: %s" % c))
    try:
        import radai_tasks as _rt
        fino = _rt.pede_corte_fino(task)
        if fino:
            fora.append(u"treinado em corte mais fino que a TC de "
                        u"planejamento")
    except Exception:
        pass
    return fora


def _item_da_tela(task, d, achados, permitidas, est, contraste, entregues,
                  recorte, versao_ts, protocolos=(), travada=False):
    md = _md()
    it = md._item_de_task(task, d, achados, permitidas, est, contraste,
                          entregues, recorte)
    nomes, fonte = estruturas_da_task(task)
    alim, arquivo = _o_que_alimenta(task)
    try:
        import radai_tasks as _rt
        na_bib = _rt.nome_na_biblioteca(task)
    except Exception:
        na_bib = task
    it.update({
        "estruturas": nomes, "estruturas_fonte": fonte,
        "alimenta": alim, "arquivo": arquivo,
        "modelo": {"nome": u"TotalSegmentator", "versao": versao_ts,
                   "task": na_bib},
        "avisos": _avisos_da_task(task, it),
        "protocolos": [p for p in protocolos],
        "arrasta": list(md.ao_ligar(task)),
        "motor": False, "travada": bool(travada),
    })
    return it


def _item_dos_niveis(modalidade="CT"):
    md = _md()
    if md._modalidade(modalidade) != "CT":
        return None
    m = md.MOT_POR_COD.get("hnlnl") or {}
    protos = [p["cod"] for p in md.protocolos_de(modalidade)
              if "hnlnl" in (p.get("motores") or ())]
    try:
        import radai_models
        inst = bool(radai_models.estado_do_modelo("hnlnl").get("instalado"))
    except Exception:
        inst = None
    return {"task": CHAVE_DOS_NIVEIS, "rotulo": m.get("rotulo") or u"hnlnl",
            "caixa": m.get("caixa") or m.get("rotulo") or u"",
            "motor": True, "achado": False, "permitida": True,
            "instalado": inst, "ajuda": m.get("ajuda") or u"",
            "estruturas": _estruturas_dos_niveis(),
            "estruturas_fonte": u"motor",
            "alimenta": "full", "arquivo": u"FULL",
            "modelo": {"nome": u"níveis cervicais (Weissmann et al. 2023)",
                       "versao": None, "task": "hnlnl"},
            "avisos": [u"só sai com a cabeça no campo; os níveis entram no "
                       u"FULL, e no STUDY só a união e as parótidas do nível "
                       u"VIII"],
            "protocolos": protos, "arrasta": [],
            "velocidade": None, "velocidade_rotulo": u"", "ficha": [],
            "travada": False}


def _estruturas_dos_niveis():
    try:
        import radai_hnlnl as _hn
        return ([_hn.nome_do_nivel(i) for i in _hn.ROTULOS_DA_UNIAO]
                + [_hn.NOME_DA_UNIAO, u"Parotid_L", u"Parotid_R"])
    except Exception:
        return []


MODELO_DOS_MOTORES_DO_FULL = {
    "cranio_ct": (u"CT Brain Segmentation Radiotherapy (Buti et al. 2025)",
                  "cranio_buti"),
}
AVISO_DOS_MOTORES_DO_FULL = {
    "cranio_ct": u"só sai com o encéfalo no campo; tronco e quiasma vão também "
                 u"ao STUDY",
}


def _itens_dos_motores_do_full(modalidade="CT"):
    md = _md()
    if md._modalidade(modalidade) != "CT":
        return []
    try:
        import radai_motores_full as _rmf
        no_full = _rmf.estruturas_no_full()
    except Exception:
        no_full = {}
    fora = []
    for cod in CHAVES_DOS_MOTORES_DO_FULL:
        m = md.MOT_POR_COD.get(cod) or {}
        protos = [p["cod"] for p in md.protocolos_de(modalidade)
                  if cod in (p.get("motores") or ())]
        nome, ident = MODELO_DOS_MOTORES_DO_FULL[cod]
        try:
            import radai_models
            inst = bool(radai_models.estado_do_modelo(ident).get("instalado"))
        except Exception:
            inst = None
        fora.append({
            "task": cod, "rotulo": m.get("rotulo") or cod,
            "caixa": m.get("caixa") or m.get("rotulo") or u"",
            "motor": True, "achado": False, "permitida": True,
            "instalado": inst, "ajuda": m.get("ajuda") or u"",
            "estruturas": list(no_full.get(cod, ())),
            "estruturas_fonte": u"motor",
            "alimenta": "full", "arquivo": u"FULL",
            "modelo": {"nome": nome, "versao": None, "task": cod},
            "avisos": [AVISO_DOS_MOTORES_DO_FULL[cod]],
            "protocolos": protos, "arrasta": [],
            "velocidade": "slow" if m.get("lento") else None,
            "velocidade_rotulo": u"~slow" if m.get("lento") else u"",
            "ficha": [], "travada": False})
    return fora


def comparacao_da_tela(modalidade="CT"):
    md = _md()
    mod = md._modalidade(modalidade)
    try:
        import engine
        alimentam = tuple(engine.motores_que_alimentam())
    except Exception:
        alimentam = None
    fora = []
    for c in COMPARACAO_DA_TELA:
        it = {"cod": c["cod"], "rotulo": c["rotulo"], "so_tc": c["so_tc"],
              "velocidade": None, "velocidade_rotulo": u"",
              "velocidade_fonte": u""}
        if c["modelo"]:
            it["ajuda"] = md.ajuda_do_motor(c["cod"], alimentam)
            if (md.MOT_POR_COD.get(c["cod"]) or {}).get("lento"):
                it.update({"velocidade": "slow",
                           "velocidade_rotulo": u"~slow",
                           "velocidade_fonte": FONTE_DA_VELOCIDADE_DO_MOTOR})
            try:
                import radai_models
                em = radai_models.estado_do_modelo(c["modelo"])
                it["instalado"] = bool(em.get("instalado"))
                it["licenca"] = em.get("licenca") or u""
            except Exception:
                it["instalado"], it["licenca"] = None, u""
        else:
            it["ajuda"] = c["ajuda"]
            it["instalado"], it["licenca"] = True, u"Apache-2.0"
        pode = (mod == "CT") or not c["so_tc"]
        it["disponivel"] = bool(pode)
        it["porque_nao"] = (u"" if pode else
                            u"só em TC: os pesos deste modelo são de "
                            u"tomografia")
        fora.append(it)
    return fora


def opcoes_da_tela(modalidade="CT"):
    md = _md()
    mod = md._modalidade(modalidade)
    permitidas, achados, entregues = None, (), None
    recorte = recorte_no_corpo_da_estacao()
    try:
        import engine
        permitidas = getattr(engine, "TASKS_PERMITIDAS", None)
        achados = tuple(getattr(engine, "TASKS_DE_ACHADO", ()) or ())
        if recorte is None:
            recorte = getattr(engine, "RECORTE_NO_CORPO_PADRAO", None)
        inv = {}
        for _amigavel, _fontes in (getattr(engine, "TS_MAP", {}) or {}).items():
            for _t in (_fontes or {}):
                inv[_t] = inv.get(_t, 0) + 1
        entregues = {d["task"]: inv.get(d["task"], 0)
                     for d in (_catalogo_de_tasks() or ())}
    except Exception:
        pass
    cat = _catalogo_de_tasks()
    if cat:
        md.conferir_protocolos(cat, achados)
    try:
        import radai_tasks as _rt
        _vels = list(getattr(_rt, "VELOCIDADES", ()) or ())
        reservas = set(getattr(_rt, "RESERVAS", ()) or ())
        contraste = dict(getattr(_rt, "CONTRASTE_TASK", {}) or {})
    except Exception:
        _vels, reservas, contraste = [], set(), {}
    est = {}
    try:
        import radai_tasks as _rt
        for x in (_rt.estado() or ()):
            est[x.get("task")] = x
    except Exception:
        est = {}
    versao_ts = versao_do_totalsegmentator()
    protos = md.protocolos_de(mod)
    por_task_prot = {}
    for p in protos:
        for t in p.get("tasks") or ():
            por_task_prot.setdefault(t, []).append(p["cod"])
    base = md.base_de(mod)
    por_nome = dict((d.get("task"), d) for d in (cat or ()))
    ordem = []
    for p in protos:
        for t in p.get("tasks") or ():
            if t not in ordem:
                ordem.append(t)
    avulsas, de_achado = [], []
    for d in (cat or ()):
        t = d.get("task")
        if (t in ordem or t == base or t in reservas
                or md._modalidade(d.get("modalidade")) != mod):
            continue
        (de_achado if t in achados else avulsas).append(t)
    tasks = []
    for t in ordem + avulsas + de_achado:
        d = por_nome.get(t)
        if d is None and cat:
            continue
        if d is not None and md._modalidade(d.get("modalidade")) != mod:
            continue
        tasks.append(_item_da_tela(t, d, achados, permitidas, est, contraste,
                                   entregues, recorte, versao_ts,
                                   protocolos=por_task_prot.get(t, ())))
    niveis = _item_dos_niveis(mod)
    if niveis is not None:
        tasks.append(niveis)
    tasks.extend(_itens_dos_motores_do_full(mod))
    base_item = _item_da_tela(base, por_nome.get(base), achados, permitidas,
                              est, contraste, entregues, recorte, versao_ts,
                              travada=True)
    base_item["por_que_travada"] = POR_QUE_A_BASE_RODA_SEMPRE
    return {
        "modalidade": mod,
        "modos": [dict(m) for m in MODOS_DA_TELA],
        "modo_de_fabrica": md.MODO_DE_FABRICA,
        "ajuda_dos_modos": AJUDA_DOS_MODOS,
        "base": base,
        "base_item": base_item,
        "protocolos": [dict(p) for p in protos],
        "tasks": tasks,
        "ao_ligar": dict((t, list(v))
                         for t, v in md.DEPENDENCIAS_AO_LIGAR.items()),
        "ligadas_de_fabrica": list(md.ligadas_de_fabrica(mod)),
        "comparacao": comparacao_da_tela(mod),
        "categorias": [dict(c) for c in md.CATEGORIAS_DE_PROTOCOLO],
        "protocolos_3d": [{"cod": p["cod"], "rotulo": p["rotulo"],
                           "ajuda": p.get("ajuda") or u""}
                          for p in md.protocolos_3d_de(mod)],
        "velocidades": _vels,
        "chave_dos_niveis": CHAVE_DOS_NIVEIS,
        "protocolos_proprios": protocolos_proprios_da_tela(mod),
    }


def protocolos_proprios_da_tela(modalidade="CT"):
    md = _md()
    mod = md._modalidade(modalidade)
    try:
        import radai_config as _c
        import radai_sets as _rs
        lista = list(_c.protocolos_proprios(mod) or ())
    except Exception:
        return []
    _perm, achados = _achados_e_permitidas()
    fora = []
    for p in lista:
        p = dict(p or {})
        if not p.get("id") or md._modalidade(p.get("modalidade")) != mod:
            continue
        try:
            ts = _rs.tasks_do_protocolo(p)
            mot = _rs.motores_do_protocolo(p)
        except Exception:
            continue
        ach = [t for t in ts if t in set(achados or ())]
        fora.append({"id": (u"%s" % p["id"])[:64],
                     "nome": u"%s" % (p.get("nome") or p["id"]),
                     "tasks": [t for t in ts if t not in ach],
                     "motores": list(mot), "achados": ach,
                     "tem_achado": bool(ach),
                     "n_estruturas": len(p.get("estruturas") or ()),
                     "n_unioes": len(p.get("merges") or ())})
    return fora


POR_QUE_A_BASE_RODA_SEMPRE = (
    u"A base roda em toda série e não se desliga: é dela que saem a anatomia "
    u"que decide as outras tasks, o contorno do corpo e os órgãos do FULL. "
    u"Sem ela não há o que pós-processar.")


def _liga_por_omissao(motor):
    try:
        import engine
        return motor in engine.motores_que_alimentam()
    except Exception:
        return False



EXIGENCIAS_NA_PREVIA = {
    "ChestWall_L": {"tasks": ("trunk_cavities",), "torax": True,
                    "so_tc": True},
    "ChestWall_R": {"tasks": ("trunk_cavities",), "torax": True,
                    "so_tc": True},
    "breast_left": {"tasks": ("breasts",)},
    "breast_right": {"tasks": ("breasts",)},
    "bag_bowel_oar": {"tasks": ("trunk_cavities",),
                      "fora_do_modo": ("fast",)},
    "Skin": {"tasks": ("base",), "so_tc": True},
    "rectum": {"estruturas": ("colon",)},
    # GUARDA: a parotida do VIII exige tambem o ECM (headneck_muscles), que
    # a recorta.
    "LNL_UNION": {"tasks": ("hnlnl",), "so_tc": True},
    "parotid_lnl_left": {"tasks": ("hnlnl", "headneck_muscles"),
                         "so_tc": True},
    "parotid_lnl_right": {"tasks": ("hnlnl", "headneck_muscles"),
                          "so_tc": True},
}


def _tasks_da_estrutura(nome, engine=None):
    try:
        import engine as _e
        engine = engine or _e
    except Exception:
        return set()
    fora = set()
    for f in ((engine.TS_MAP or {}).get(nome) or {}):
        fora.add(f)
    for parte in (getattr(engine, "COMPOSTOS", {}) or {}).get(nome) or ():
        if parte != nome:
            fora |= _tasks_da_estrutura(parte, engine)
    return fora


def _roda(task_ou_familia, rodam):
    try:
        import radai_tasks as _rt
        fam = _rt.familia_da_task
    except Exception:
        fam = lambda t: t
    alvo = fam(task_ou_familia)
    return any(t == task_ou_familia or fam(t) == alvo for t in rodam)


def _estrutura_possivel(nome, rodam, engine):
    for alt in str(nome).split("|"):
        fontes = _tasks_da_estrutura(alt, engine)
        if any(_roda(f, rodam) for f in fontes):
            return True
    return False


CONDICAO_DA_REGIAO_NA_PREVIA = {
    "pelve": u"só com a pelve identificada",
    None: u"só com a região identificada pela anatomia",
}
CONDICAO_DO_ENCEFALO_NA_PREVIA = u"só com o encéfalo no campo"
CONDICAO_DO_PESCOCO_NA_PREVIA = u"só com o pescoço confirmado"
REGIAO_DO_PESCOCO_NA_PREVIA = "pescoco"


def _tasks_com_portao(regiao, engine):
    return set(t for t, r in (getattr(engine, "REGIAO_DA_TASK", None)
                              or {}).items() if r == regiao)


def so_com_o_pescoco(k, rodam, engine):
    presas = _tasks_com_portao(REGIAO_DO_PESCOCO_NA_PREVIA, engine)
    if not presas:
        return False
    ex = EXIGENCIAS_NA_PREVIA.get(k)
    if ex is not None and ex.get("tasks"):
        return any(t in presas for t in ex["tasks"])
    fontes = set()
    for alt in str(k).split("|"):
        fontes |= _tasks_da_estrutura(alt, engine)
    vivas = [f for f in fontes if _roda(f, rodam)]
    return bool(vivas) and all(f in presas for f in vivas)


def estruturas_dos_motores_no_oar(modo, modalidade, motores, oar_fora=()):
    md = _md()
    if md._modalidade(modalidade) != "CT":
        return []
    try:
        import engine
        import radai_motores_full as _rmf
        import radai_sets as _rs
        no_oar = _rmf.estruturas_no_oar()
    except Exception:
        return []
    permitidos = (_rs.PERMITIDOS_NO_OAR_FAST
                  if md.normalizar_modo(modo) == md.MODO_FAST
                  else _rs.PERMITIDOS_NO_OAR)
    fora = []
    for cod in md.MOTORES_NO_FULL:
        if not (motores or {}).get(cod):
            continue
        for k in no_oar.get(cod, ()):
            if k not in permitidos or k in set(oar_fora or ()):
                continue
            try:
                nome = engine.nome_clinico(k)
            except Exception:
                nome = k
            fora.append({"chave": k, "nome": nome, "construcao": False,
                         "condicao": CONDICAO_DO_ENCEFALO_NA_PREVIA})
    return fora

CHAVE_DO_HEART_AI_NA_PREVIA = "heart"
VARIANTE_DO_HEART_AI_NA_PREVIA = {
    "com": u"com pericárdio",
    "desligada": u"sem pericárdio: a cavidade do tronco foi desligada",
    "rm": u"sem pericárdio: na RM a cavidade do tronco não roda",
}


def _variante_do_heart_ai(modalidade, rodam):
    md = _md()
    if md._modalidade(modalidade) != "CT":
        return False, VARIANTE_DO_HEART_AI_NA_PREVIA["rm"]
    if _roda(md.TASK_DO_PERICARDIO, rodam):
        return True, VARIANTE_DO_HEART_AI_NA_PREVIA["com"]
    return False, VARIANTE_DO_HEART_AI_NA_PREVIA["desligada"]


def estruturas_do_oar_possiveis(modo, tasks, modalidade="CT", torax=None,
                                oar_fora=(), regioes=None):
    md = _md()
    try:
        import engine
        import radai_sets as _rs
    except Exception:
        return [], []
    mod = md._modalidade(modalidade)
    base = md.base_de(mod)
    rodam = [base] + [t for t in (tasks or ()) if t and t != base]
    fast = md.normalizar_modo(modo) == md.MODO_FAST
    lista = _rs.PERMITIDOS_NO_OAR_FAST if fast else _rs.PERMITIDOS_NO_OAR
    saidas = {}
    for c in getattr(engine, "CONSTRUCOES", ()) or ():
        for k in (c.get("saidas") or {}):
            saidas[k] = c
    possiveis = []
    for k in sorted(lista):
        ex = EXIGENCIAS_NA_PREVIA.get(k)
        c = saidas.get(k)
        if ex is not None:
            if ex.get("so_tc") and mod != "CT":
                continue
            if fast and "fast" in (ex.get("fora_do_modo") or ()):
                continue
            ok = all(_roda(base if t == "base" else t, rodam)
                     for t in ex.get("tasks") or ())
            ok = ok and all(_estrutura_possivel(n, rodam, engine)
                            for n in ex.get("estruturas") or ())
            if ex.get("torax"):
                if torax is not True and regioes is not None \
                        and "torax" not in set(regioes):
                    ok = False
            if not ok:
                continue
        elif c is not None:
            if c.get("exige_hu") and mod != "CT":
                continue
            if not all(_estrutura_possivel(n, rodam, engine)
                       for n in (c.get("exige") or ())):
                continue
        elif not _estrutura_possivel(k, rodam, engine):
            continue
        _reg_exigida = (getattr(engine, "REGIAO_EXIGIDA_NO_OAR", {})
                        or {}).get(k)
        if (_reg_exigida and regioes is not None
                and _reg_exigida not in set(regioes)):
            continue
        if (regioes is not None and "cabeca_pescoco" not in set(regioes)
                and so_com_o_pescoco(k, rodam, engine)):
            continue
        if k in (getattr(engine, "FORA_DO_OAR_NA_MODALIDADE", None)
                 or {}).get(mod, ()):
            continue
        possiveis.append(k)
    _subst = dict(getattr(_rs, "MESMA_ROI_NO_OAR", None) or {})
    possiveis = [k for k in possiveis
                 if not any(v == k and s in possiveis
                            for s, v in _subst.items())]
    tiradas = set()
    if not fast and oar_fora:
        try:
            import radai_output as _ro
            perm, _tir = _ro.permitidos_do_oar(oar_fora, engine=engine)
            tiradas = set(k for k in possiveis if k not in set(perm))
        except Exception:
            tiradas = set(k for k in possiveis if k in set(oar_fora))

    def _item(k):
        try:
            nome = engine.nome_clinico(k)
        except Exception:
            nome = k
        it = {"chave": k, "nome": nome,
              "construcao": bool(k in saidas or k in EXIGENCIAS_NA_PREVIA)}
        _cod = (getattr(engine, "REGIAO_EXIGIDA_NO_OAR", {}) or {}).get(k)
        if _cod and regioes is None:
            it["condicao"] = CONDICAO_DA_REGIAO_NA_PREVIA.get(
                _cod, CONDICAO_DA_REGIAO_NA_PREVIA[None])
        elif so_com_o_pescoco(k, rodam, engine):
            it["condicao"] = CONDICAO_DO_PESCOCO_NA_PREVIA
        if k == CHAVE_DO_HEART_AI_NA_PREVIA:
            it["pericardio"], it["variante"] = _variante_do_heart_ai(mod,
                                                                     rodam)
        return it
    return ([_item(k) for k in possiveis if k not in tiradas],
            [_item(k) for k in possiveis if k in tiradas])


ROTULO_DO_MAPA_3D = u"mapa de rótulos das Reconstruções 3D"


def arquivos_da_escolha(serie, tasks=(), motores=None):
    md = _md()
    import radai_sets as _rs
    e = escolha_da_serie(serie)
    s = serie or {}
    data = _rs.data_do_nome(s)
    curto = str(s.get("curto") or (s.get("uid") or u"")[-8:] or u"serie")

    def _arq(cod):
        reg = _rs.POR_COD.get(cod) or {}
        try:
            nome = _rs.nome_do_arquivo(cod, data, curto)
        except Exception:
            nome = u"RS_RadAI_%s%s_%s.dcm" % (reg.get("infixo", u""),
                                             data or _rs.SEM_DATA, curto)
        return {"cod": cod, "nome": reg.get("rotulo_curto") or cod,
                "arquivo": nome, "entregue": bool(reg.get("entregue"))}
    if e["modo"] == md.MODO_FAST:
        return [_arq("fast")]
    fora = [_arq("oar"), _arq("full")]
    if e["modo"] != md.MODO_PERSO:
        return fora
    so_do_estudo = set(tasks_so_do_estudo(s))
    for t in tasks or ():
        if t in so_do_estudo:
            continue
        if not _rs.task_do_full(t) and t in _rs.PLUGIN_DA_TASK:
            fora.append(_arq(_rs.PLUGIN_DA_TASK[t]["cod"]))
    if e.get("protocolos_3d"):
        try:
            import radai_rotulos
            nome_rot = radai_rotulos.nome_do_arquivo(s.get("uid"))
        except Exception:
            nome_rot = u"rotulos_%s.npz" % curto
        fora.append({"cod": "rotulos", "nome": ROTULO_DO_MAPA_3D,
                     "arquivo": u"_RadAI/" + nome_rot, "entregue": False})
    mot = motores if motores is not None else motores_do_perso(e)
    if e["comparacao"].get("ts"):
        fora.append(_arq("ts"))
    for cod in ("nv", "cads", "mse"):
        if mot.get(cod):
            fora.append(_arq(cod))
    if mot.get("hnlnl"):
        fora.append(_arq("hnl"))
    return fora


def estruturas_do_protocolo_na_previa(protocolo, oar_fora=()):
    import radai_sets as _rs
    try:
        import engine
        _nome = engine.nome_clinico
    except Exception:
        _nome = lambda k: k
    sel = _rs.selecao_do_protocolo(protocolo)
    tiradas = set(oar_fora or ())
    ests, fora = [], []
    for k in sel["chaves"]:
        it = {"chave": k, "nome": _nome(k), "construcao": False}
        (fora if k in tiradas else ests).append(it)
    for u in sel["unioes"]:
        ests.append({"chave": u"uniao:%s" % u["nome"], "nome": u["nome"],
                     "construcao": True, "uniao": True,
                     "de": [_nome(k) for k in u["de"]]})
    return ests, fora


def _com_os_nomes_proprios(ests, fora):
    import radai_sets as _rs
    proprios = _rs.nomes_proprios_em_vigor()
    if not proprios:
        return ests, fora
    todos = list(ests) + list(fora)
    aceitos, _r = _rs.validar_nomes_proprios(
        proprios, [x["nome"] for x in todos if not x.get("uniao")],
        outros=[x["nome"] for x in todos if x.get("uniao")])

    def _troca(x):
        if x.get("uniao") or x["nome"] not in aceitos:
            return x
        return dict(x, nome=aceitos[x["nome"]], nome_padrao=x["nome"])
    return [_troca(x) for x in ests], [_troca(x) for x in fora]


def previa_da_entrega(serie):
    md = _md()
    s = dict(serie or {})
    e = escolha_da_serie(s)
    mod = e["modalidade"]
    permitidas, achados = _achados_e_permitidas()
    cat = _catalogo_de_tasks()
    tasks, _origem = tasks_iniciais(s, None)
    tasks = list(tasks)
    possiveis = []
    if e["modo"] == md.MODO_FAST:
        possiveis = list(md.tasks_do_fast(md.TOPOGRAFIAS, None, mod,
                                          permitidas=permitidas,
                                          achados=achados,
                                          catalogo=cat)[1:])
    elif e["modo"] == md.MODO_AUTO:
        possiveis = list(md.tasks_da_topografia(
            md.TOPOGRAFIAS, mod, permitidas=permitidas, achados=achados,
            catalogo=cat)[1:])
    todas = tasks + [t for t in possiveis if t not in tasks]
    mot, _o = motores_da_serie(s)
    if e["modo"] == md.MODO_AUTO and mod == "CT":
        mot = dict(mot, hnlnl=True)
        for _c in md.motores_do_auto(md.TOPOGRAFIAS, mod):
            mot[_c] = True
    elif e["modo"] == md.MODO_FAST:
        for _c in md.motores_do_fast(md.TOPOGRAFIAS, mod):
            mot[_c] = True
    arquivos = arquivos_da_escolha(s, todas, mot)
    so_do_estudo = set(tasks_so_do_estudo(s))
    # GUARDA: a uniao e as parotidas do VIII so existem com o motor dos
    # niveis entregando ao FULL (e nao so ao estudo 3D).
    _niv = ([CHAVE_DOS_NIVEIS] if (mot.get(CHAVE_DOS_NIVEIS)
                                   and not niveis_so_do_estudo(s)) else [])
    ests, fora = estruturas_do_oar_possiveis(
        e["modo"], [t for t in todas if t not in so_do_estudo] + _niv, mod,
        torax=torax_pedido(s), oar_fora=e["oar_fora"])
    _ja = set(x["chave"] for x in ests)
    ests = ests + [x for x in estruturas_dos_motores_no_oar(
        e["modo"], mod, mot, e["oar_fora"]) if x["chave"] not in _ja]
    _pp = protocolo_proprio_da_escolha(e)
    if _pp is not None:
        ests, fora = estruturas_do_protocolo_na_previa(_pp, e["oar_fora"])
    ests, fora = _com_os_nomes_proprios(ests, fora)
    arq_oar = next((a for a in arquivos if a.get("entregue")), None)
    anat = e["modo"] != md.MODO_PERSO
    return {"modo": e["modo"], "modalidade": mod,
            "tasks": tasks, "tasks_depois_da_base": possiveis,
            "motores": mot, "arquivos": arquivos,
            "oar": {"arquivo": arq_oar, "estruturas": ests, "fora": fora},
            "depende_da_anatomia": True,
            "nota": (u"a base mede a anatomia da série e decide quais tasks "
                     u"rodam; aqui está o que esta escolha pode produzir"
                     if anat else
                     u"o que existe na série depende da anatomia: aqui está "
                     u"o que esta escolha pode produzir")}


def pos_refazivel(done):
    done = done or {}
    fora = {"refazivel": False, "motivo": u"", "receita_mudou": False}
    try:
        import engine as _e
        atual = getattr(_e, "VERSAO_DA_RECEITA_POS", u"")
    except Exception:
        atual = u""
    rec = done.get("receita_pos")
    fora["receita_mudou"] = bool(rec and atual and rec != atual)
    if str(done.get("modo") or u"") not in ("auto", "fast"):
        fora["motivo"] = (u"refazer so o pos-processamento serve ao AUTO e "
                          u"ao FAST; o PERSONALIZADO refaz a serie inteira")
        return fora
    chaves = dict(done.get("cache_das_tasks") or {})
    if not chaves:
        fora["motivo"] = u"a entrega nao guardou o cache das tasks"
        return fora
    # GUARDA: o que desenhou fora do TotalSegmentator nao tem cache por task;
    # refazer so o pos rodaria a inferencia dele de novo.
    fora_do_ts = [u"%s" % m for m in (done.get("motores_fora_do_ts") or ())
                  if m]
    if fora_do_ts:
        fora["motivo"] = (u"%s rodou fora do TotalSegmentator e nao tem cache "
                          u"por task: refaca a serie inteira"
                          % u", ".join(sorted(fora_do_ts)))
        return fora
    try:
        import radai_cache_tasks as _ct
        if not _ct.armado():
            fora["motivo"] = u"o cache por task esta desligado nesta estacao"
            return fora
        pasta = _ct.pasta()
        faltam = [t for t, c in chaves.items()
                  if not os.path.isdir(os.path.join(str(pasta), str(c)))]
    except Exception as e:
        fora["motivo"] = u"nao consegui ler o cache (%s)" % type(e).__name__
        return fora
    if faltam:
        fora["motivo"] = (u"sem o cache de %s nesta estacao: refaca a serie "
                          u"inteira" % u", ".join(sorted(faltam)))
        return fora
    fora["refazivel"] = True
    return fora


def _falharam_do_done(done):
    fora = []
    for f in (done or {}).get("tasks_falharam") or ():
        if isinstance(f, dict) and f.get("task"):
            fora.append({"task": u"%s" % f["task"],
                         "erro": u"%s" % (f.get("erro") or u""),
                         "classe": u"%s" % (f.get("classe") or u"")})
    return fora


def _situacao(s, marcadores):
    d = {"situacao": "livre", "detalhe": ""}
    if not marcadores:
        return d
    try:
        _sem_rs = marcadores.get("sem_rtstruct")
        _afastado = marcadores.get("sem_rtstruct_afastado")
        sem_rs = bool((_sem_rs and _sem_rs(s["pasta"], s["uid"]))
                      or (_afastado and _afastado(s["pasta"], s["uid"])))
        if sem_rs:
            d = {"situacao": "refazer", "detalhe": ""}
        if (not sem_rs
                and marcadores["has_marker"](s["pasta"], s["uid"], "done")):
            reg = (marcadores.get("read_marker") or (lambda *a: None))(
                s["pasta"], s["uid"], "done") or {}
            fora = {"situacao": "concluida",
                    "detalhe": "%s · %s" % (reg.get("finished", ""),
                                            reg.get("machine", "")),
                    "pos": pos_refazivel(reg)}
            try:
                import radai_records as _rg_s
                _falt = _rg_s.nomes_do_faltou(reg)
            except Exception:
                _falt = []
            if _falt:
                fora["faltou"] = _falt[:60]
            return fora
        if marcadores["has_marker"](s["pasta"], s["uid"], "lock"):
            reg = (marcadores.get("read_marker") or (lambda *a: None))(
                s["pasta"], s["uid"], "lock") or {}
            quem = reg.get("machine", "?")
            desde = reg.get("start", "?")
            diag = marcadores.get("diagnostico")
            if diag:
                try:
                    estado, dado = diag(s["pasta"], s["uid"])
                except Exception:
                    estado, dado = "trabalhando", {}
                if estado in ("travado", "morto"):
                    import time as _t
                    hb = float(dado.get("heartbeat") or 0)
                    min_parado = (_t.time() - hb) / 60.0 if hb else 0.0
                    minha = str(quem) == str(_maquina_desta_estacao())
                    return {"situacao": "retomavel", "minha": bool(minha),
                            "detalhe": ("%s parou aqui em %s"
                                        % (quem, desde)
                                        + (" — sem sinal de vida há %.0f min"
                                           % min_parado if min_parado else "")
                                        + ("; incluir retoma do começo"
                                           if minha else
                                           "; incluir ASSUME a série dela"))}
            return {"situacao": "processando",
                    "detalhe": "%s desde %s" % (quem, desde)}
    except Exception:
        pass
    return d


def _rs_existente(pasta):
    try:
        return sorted(p for p in os.listdir(str(pasta))
                      if p.startswith("RS_RadAI_") and p.lower().endswith(".dcm"))
    except Exception:
        return []


def _rs_da_serie(pasta, uid):
    import radai_sets as _rs_s
    return _rs_s.arquivos_da_serie(_rs_existente(pasta), uid)


def estado():
    with _TRAVA:
        d = dict(_JOB)
    d["resultados"] = list(d["resultados"])[-60:]
    d["fila"] = [{"uid": i["serie"].get("uid", ""),
                  "curto": (i["serie"].get("uid") or "")[-12:],
                  "cortes": i["serie"].get("cortes", 0)}
                 for i in list(_FILA)]
    d["ultimo_erro"] = ""
    for r in reversed(d["resultados"]):
        if (r or {}).get("erro"):
            d["ultimo_erro"] = r["erro"]
            break
    return d


DETALHE_DO_ZIP_OMITIDO = (u"(o detalhe do .zip foi omitido: ele nomeia um "
                          u"arquivo de dentro dele, que pode ser o do "
                          u"paciente)")
_FRASES_DA_EXTRACAO = (u"Não consegui extrair: ", u"Nao consegui extrair: ",
                       u"não consegui extrair: ", u"nao consegui extrair: ")


def sem_detalhe_do_zip(texto, de_zip=False):
    s = u"%s" % (texto or u"")
    if de_zip:
        if u": " in s:
            return s.split(u": ", 1)[0] + u": " + DETALHE_DO_ZIP_OMITIDO
        return s
    for frase in _FRASES_DA_EXTRACAO:
        i = s.find(frase)
        if i >= 0:
            return s[:i + len(frase)] + DETALHE_DO_ZIP_OMITIDO
    return s


def pausar(valor=True):
    with _TRAVA:
        _JOB["pausar"] = bool(valor)
        rodando = bool(_JOB["rodando"])
    return {"ok": True, "pausado": bool(valor), "rodando": rodando}


def cancelar():
    with _TRAVA:
        if not _JOB["rodando"]:
            return {"ok": False, "erro": "nao ha nada rodando"}
        _JOB["cancelar"] = True
        jid = _JOB.get("jid")
    matou = False
    if jid:
        try:
            import engine
            engine._set(jid, cancelar=True)
            matou = True
        except Exception:
            pass
    with _TRAVA:
        descartadas = len(_FILA)
        del _FILA[:]
    return {"ok": True, "matou_a_atual": matou, "descartadas": descartadas,
            "aviso": ("interrompendo a série em curso (até 2 s)" if matou
                      else "vai parar ao terminar a série atual")
                     + ((" e descartando %d da fila" % descartadas)
                        if descartadas else "")}


def _passo(etapa, atual=None):
    with _TRAVA:
        _JOB["etapa"] = etapa
        if atual is not None:
            _JOB["atual"] = atual
        _JOB["parte"] = ""
    _cronometrar(etapa)
    lg, caso = _DA_SERIE_DO_LOTE
    if lg is not None:
        lg(u"etapa: %s" % etapa)
    if caso is not None:
        caso.etapa(etapa)


_DA_SERIE_DO_LOTE = [None, None]


def _abrir_log_e_caso_do_lote(s, marcadores, log):
    _DA_SERIE_DO_LOTE[:] = [None, None]
    try:
        import radai_records as _rg_and
    except Exception:
        return log
    lg = None
    try:
        lock = marcadores["m_path"](s["pasta"], s["uid"], "lock")
        lg = _rg_and.LogDaSerie(
            os.path.dirname(str(lock)), s["uid"],
            identificadores=(s.get("pid", ""), s.get("uid", ""),
                             s.get("nome", ""), s.get("nascimento", "")),
            so_trocar=_pastas_para_trocar(s))
        if not lg.abrir():
            if log:
                log("log da serie: nao abri o arquivo na _RadAI (%s) - o log "
                    "geral continua" % lg.erro)
            lg = None
    except Exception as e:
        lg = None
        if log:
            log("log da serie: indisponivel nesta serie (%s) - o log geral "
                "continua" % type(e).__name__)
    caso = None
    try:
        caso = _rg_and.CasoEmAndamento(uid=s.get("uid", ""),
                                       origem=u"rodar agora",
                                       modo=s.get("modo") or None)
        if not caso.abrir():
            caso = None
    except Exception:
        caso = None
    _DA_SERIE_DO_LOTE[:] = [lg, caso]
    if lg is None:
        return log

    def _log_com_arquivo(msg):
        if log:
            log(msg)
        lg(msg)
    _CRONOMETRO_DA_SERIE[1] = (_log_com_arquivo
                               if _CRONOMETRO_DA_SERIE[0] is not None
                               else _CRONOMETRO_DA_SERIE[1])
    return _log_com_arquivo


def _fechar_log_e_caso_do_lote(res=None):
    lg, caso = _DA_SERIE_DO_LOTE
    _DA_SERIE_DO_LOTE[:] = [None, None]
    if lg is not None:
        r = res or {}
        if r.get("erro"):
            fim = u"falhou: %s" % (u"%s" % r["erro"])[:160]
        elif r.get("cancelado"):
            fim = u"interrompida pelo operador"
        elif r.get("pulada"):
            fim = u"pulada: %s" % (u"%s" % r["pulada"])[:120]
        else:
            fim = u"pronta"
        lg(u"fim da serie: %s; trava solta" % fim)
        lg.fechar()
    if caso is not None:
        try:
            caso.fechar()
        except Exception:
            pass


_CRONOMETRO_DA_SERIE = [None, None]


def _abrir_cronometro(log):
    try:
        import radai_etapas
        c = radai_etapas.Cronometro()
        c.etapa(u"preparo")
        _CRONOMETRO_DA_SERIE[:] = [c, log]
    except Exception:
        _CRONOMETRO_DA_SERIE[:] = [None, None]


def _cronometrar(etapa):
    c, log = _CRONOMETRO_DA_SERIE
    if c is None or not log:
        return
    try:
        import radai_etapas
        fechada = c.etapa(etapa)
        if fechada:
            log(radai_etapas.linha(fechada))
    except Exception:
        pass


def _fechar_cronometro():
    c, log = _CRONOMETRO_DA_SERIE
    _CRONOMETRO_DA_SERIE[:] = [None, None]
    if c is None or not log:
        return
    try:
        import radai_etapas
        fechada = c.fechar()
        if fechada:
            log(radai_etapas.linha(fechada))
        log(c.resumo())
    except Exception:
        pass


def andamento():
    with _TRAVA:
        rodando = bool(_JOB.get("rodando"))
        desde = float(_JOB.get("serie_desde") or 0.0)
        return {"rodando": rodando,
                "pausar": bool(_JOB.get("pausar")),
                "cancelar": bool(_JOB.get("cancelar")),
                "etapa": str(_JOB.get("etapa") or ""),
                "parte": str(_JOB.get("parte") or ""),
                "segundos": (int(max(0.0, time.time() - desde))
                             if (rodando and desde) else None),
                "feitas": int(_JOB.get("feitas") or 0),
                "total": int(_JOB.get("total") or 0),
                "terminando": bool(_JOB.get("terminando"))}


_PARTE = re.compile(r"\bpart[e]?\s*(\d{1,3})\s*(?:/|de|of)\s*(\d{1,3})\b",
                    re.I)


_SONDA_AVISOU = []


def _sondar_parte(linha):
    try:
        m = _PARTE.search(str(linha or ""))
        if m and 0 < int(m.group(1)) <= int(m.group(2)):
            with _TRAVA:
                _JOB["parte"] = "%s/%s" % (m.group(1), m.group(2))
    except Exception as e:
        if not _SONDA_AVISOU:
            _SONDA_AVISOU.append(1)
            try:
                print(u"[lote] a sonda da parte i/N falhou (%s: %s) -- o card "
                      u"segue so com a etapa e o relogio"
                      % (type(e).__name__, str(e)[:120]))
            except Exception:
                pass


def _com_sonda(log):
    if not log:
        return log

    def _log(msg):
        _sondar_parte(msg)
        return log(msg)
    return _log


MARCADORES_EXIGIDOS = ("claim", "unclaim", "has_marker", "m_path", "renovar")

_RECADO_AMBIENTE = (
    u"Este Python não consegue rodar o TotalSegmentator, então não há como "
    u"segmentar aqui — e NENHUMA série foi marcada como falha: o problema é do "
    u"ambiente, não das imagens.\n\n%s\n\n"
    u"Rode o aplicativo com o Python do bundle (start_watcher.cmd na pasta "
    u"instalada, ou rodar_com_bundle.cmd no repositório).")


def pode_segmentar(python_exe=None):
    import subprocess
    import sys
    exe = python_exe or sys.executable
    try:
        r = subprocess.run([exe, "-c", "import totalsegmentator"],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           timeout=300)
        if r.returncode == 0:
            return True, ""
        saida = (r.stderr or b"").decode("utf-8", "replace").strip()
        return False, (saida.splitlines()[-1] if saida
                       else "codigo %d" % r.returncode)[:300]
    except Exception as e:
        return False, "%s: %s" % (type(e).__name__, e)

_CFG = {}


_FILA = []


def fila():
    with _TRAVA:
        return [dict(i["serie"]) for i in _FILA]


def enfileirar(serie, tasks=None, incluir_nv=None):
    with _TRAVA:
        rodando = _JOB["rodando"]
        if rodando:
            uid = (serie or {}).get("uid")
            if uid and (uid == (_JOB.get("uid_atual") or "")
                        or any(i["serie"].get("uid") == uid for i in _FILA)):
                return {"ok": True, "enfileirada": True, "duplicada": True,
                        "posicao": len(_FILA),
                        "aviso": u"essa série já está na fila"}
            _FILA.append({"serie": dict(serie or {}), "tasks": tasks,
                          "incluir_vista": incluir_nv})
            return {"ok": True, "enfileirada": True, "posicao": len(_FILA)}
    r = iniciar_uma(serie, tasks=tasks, incluir_nv=incluir_nv) or {}
    r["enfileirada"] = False
    return r


def _proxima_da_fila():
    with _TRAVA:
        if _JOB["cancelar"] or not _FILA:
            return False
        item = _FILA.pop(0)
    r = iniciar_uma(item["serie"], tasks=item["tasks"],
                    incluir_nv=item["incluir_vista"])
    return bool((r or {}).get("ok"))


def iniciar_uma(serie, tasks=None, incluir_nv=None):
    if not _CFG:
        return {"ok": False,
                "erro": "o lote nao foi montado nesta instalacao — nao tenho a "
                        "coordenacao por marcadores para processar com seguranca"}
    return iniciar([serie],
                   incluir_nv=incluir_nv,
                   tasks=tasks,
                   device=_CFG.get("device", "auto"),
                   python_exe=_CFG.get("python_exe"),
                   timeout_task_s=_CFG.get("timeout_task_s", 10800),
                   timeout_nv_s=_CFG.get("timeout_task_s", 10800),
                   log=_CFG.get("log"), marcadores=_CFG.get("marcadores"),
                   maquina=_CFG.get("maquina", ""),
                   heartbeat_s=_CFG.get("heartbeat_s", 300),
                   suavizar_mm=_CFG.get("suavizar_mm", 1.5))


INTERVALO_DO_RELOGIO_S = 300.0
_RELOGIO = {"thread": None}


def _memoria_livre_gib():
    try:
        import radai_cleaner
        m = radai_cleaner.memoria_da_estacao() or {}
        if m.get("livre_mb"):
            return float(m["livre_mb"]) / 1024.0
    except Exception:
        pass
    return None


def tentar_complemento(livre_gib=None, agora=None):
    if not _CFG:
        return None
    with _TRAVA:
        if _JOB["rodando"]:
            return None
    try:
        oc = _CFG["ocupado"]() if callable(_CFG.get("ocupado")) else None
    except Exception:
        oc = {"quem": "?"}
    if oc:
        return None
    try:
        import radai_queue_state as _fila
    except Exception:
        return None
    if _fila.ha_manual_esperando() or _fila.quem_tem_a_vez().get("dono"):
        return None
    livre = _memoria_livre_gib() if livre_gib is None else livre_gib
    c = _fila.complemento_na_vez(livre, agora=agora)
    if not c:
        return None
    pendentes = list(c.get("pendentes_por_memoria") or ())
    s = _fila.preparar_complemento(c["id"])
    if not s:
        return None
    log = _CFG.get("log")
    if callable(log):
        try:
            log(u"a task que ficou de fora por memoria cabe agora (%.1f GiB "
                u"livres): rodo o complemento da serie ...%s, e a entrega "
                u"parcial e substituida" % (float(livre or 0),
                                             str(s.get("uid") or "")[-8:]))
        except Exception:
            pass
    r = iniciar([s], ja_na_fila=True, incluir_nv=None, tasks=None,
                device=_CFG.get("device", "auto"),
                python_exe=_CFG.get("python_exe"),
                timeout_task_s=_CFG.get("timeout_task_s", 10800),
                timeout_nv_s=_CFG.get("timeout_task_s", 10800),
                log=log, marcadores=_CFG.get("marcadores"),
                maquina=_CFG.get("maquina", ""),
                heartbeat_s=_CFG.get("heartbeat_s", 300),
                suavizar_mm=_CFG.get("suavizar_mm", 1.0),
                ocupado=_CFG.get("ocupado")) or {}
    if not r.get("ok"):
        _fila.marcar(s.get("uid"), "parcial", s.get("pasta") or u"",
                     pendentes=pendentes)
    return r


def _relogio_do_complemento():
    while True:
        time.sleep(INTERVALO_DO_RELOGIO_S)
        try:
            tentar_complemento()
        except Exception:
            pass


def armar_relogio_do_complemento():
    if _RELOGIO["thread"] is not None:
        return False
    t = threading.Thread(target=_relogio_do_complemento, daemon=True)
    t.start()
    _RELOGIO["thread"] = t
    return True


def por_na_fila(series):
    try:
        import radai_queue_state as _fila
    except Exception as e:
        return {"ok": False, "erro": u"%s: %s" % (type(e).__name__, e)}
    lista = list(series or [])
    if not lista:
        return {"ok": False, "erro": u"nenhuma serie foi incluida"}
    conta = _fila.acrescentar_series(lista)
    _and = andamento()
    return {"ok": True, "enfileiradas": conta.get("novos", 0),
            "repetidas": conta.get("repetidas", 0),
            "atualizadas": conta.get("atualizadas", 0),
            "cards": _fila.com_andamento(_fila.para_tela(_fila.cards()), _and),
            "resumo": _fila.resumo(), "lote": _fila.botoes_do_lote(_and)}


def iniciar(series, incluir_nv=None, tasks=None, device="auto",
            python_exe=None, timeout_task_s=10800, timeout_nv_s=10800,
            log=None, marcadores=None, maquina="", heartbeat_s=300,
            suavizar_mm=1.5, ocupado=None, ja_na_fila=False):
    try:
        oc = ocupado() if callable(ocupado) else None
    except Exception:
        oc = None
    faltam = [k for k in MARCADORES_EXIGIDOS if k not in (marcadores or {})]
    if faltam:
        return {"ok": False,
                "erro": ("sem a coordenacao por marcadores (%s): nao vou processar "
                         "sem lock, senao duas estacoes podem pegar a mesma serie"
                         % ", ".join(faltam))}
    if series:
        ok, detalhe = pode_segmentar(python_exe)
        if not ok:
            return {"ok": False, "ambiente": True, "erro": _RECADO_AMBIENTE % detalhe}
    with _TRAVA:
        if _JOB["rodando"]:
            return {"ok": False, "erro": "ja ha um processamento rodando nesta estacao"}
        _JOB.update({"rodando": True, "cancelar": False, "pausar": False,
                     "parou_ao_fechar": False,
                     "total": len(series or []),
                     "feitas": 0, "atual": "", "etapa": "preparando",
                     "comecou": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                     "terminou": "", "resultados": [], "erro": ""})
    try:
        import radai_queue_state as _fila
        _fila.querer_a_vez("lote")
        if not ja_na_fila:
            _fila.pedir(list(series or []))
    except Exception:
        pass
    def _alvo():
        try:
            _rodar_tudo(list(series or []), bool(incluir_nv), tasks, device,
                        python_exe, timeout_task_s, timeout_nv_s, log,
                        dict(marcadores), str(maquina or ""), float(heartbeat_s),
                        float(suavizar_mm or 0), da_fila=bool(ja_na_fila))
        except BaseException as e:
            with _TRAVA:
                _JOB["erro"] = "%s: %s" % (type(e).__name__, str(e)[:250])
                _JOB["rodando"] = False
                _JOB["etapa"] = "erro"
                _JOB["terminou"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            _soltar_a_vez_do_lote()

    threading.Thread(target=_alvo, daemon=True).start()
    fora = {"ok": True, "total": len(series or [])}
    if oc and oc.get("quem") == "vigia":
        fora["espera_o_vigia"] = True
        fora["aviso"] = (u"a série do vigia em curso termina primeiro; as "
                         u"pedidas à mão começam logo depois")
    return fora




FRASE_DO_CANCELADO = (u"interrompida pelo operador; o que ela fez foi "
                      u"descartado")


def _fila_diz(o_que, uid, dono=u"", pasta=u"", motivo=u"", faltou=None,
              sem_estrutura=None, nao_contornavel=u"", mensagem=u"",
              pendentes=None, parcial=u""):
    if not uid:
        return
    try:
        import radai_queue_state as fila
    except Exception:
        return
    try:
        if o_que == "skipped":
            fila.skipped(uid, dono=dono, motivo=motivo)
        elif o_que == "cancelado":
            fila.marcar(uid, "cancelado", pasta, mensagem=FRASE_DO_CANCELADO)
        elif o_que == "concluida":
            fila.marcar(uid, "pronto", pasta, ja_concluida=True)
        else:
            fila.marcar(uid, o_que, pasta, faltou=faltou,
                        sem_estrutura=sem_estrutura,
                        nao_contornavel=nao_contornavel,
                        mensagem=mensagem, pendentes=pendentes,
                        parcial=parcial)
            if o_que in ("pronto", "feito"):
                fila.copiar_entrega(uid, pasta)
    except Exception:
        pass


def _soltar_a_vez_do_lote():
    try:
        import radai_queue_state as _fila
        _fila.soltar_a_vez("lote")
    except Exception:
        pass


def _parar_de_esperar():
    with _TRAVA:
        return bool(_JOB.get("cancelar") or _JOB.get("pausar"))


def _esperar_a_vez_do_lote(log=None):
    try:
        import radai_queue_state as _fila
    except Exception:
        return True

    def _ao_esperar(dono):
        with _TRAVA:
            _JOB["etapa"] = u"esperando a série do vigia terminar"
        try:
            _fila.avisar_espera()
        except Exception:
            pass
        if log:
            try:
                log(u"a serie do vigia em curso termina primeiro; as pedidas "
                    u"a mao comecam em seguida (ela nao e interrompida)")
            except Exception:
                pass
    ok = _fila.esperar_a_vez("lote", parar=_parar_de_esperar,
                             ao_esperar=_ao_esperar)
    try:
        _fila.apagar_aviso_de_espera()
    except Exception:
        pass
    return ok


def _pendentes_por_memoria(*fontes):
    fora, vistas = [], set()
    for f in fontes:
        for p in ((f or {}).get("tasks_puladas_por_memoria") or ()):
            if isinstance(p, dict) and p.get("task") \
                    and p["task"] not in vistas:
                vistas.add(p["task"])
                fora.append(dict(p))
    return fora


def _fila_assume(s, log=None):
    uid = str((s or {}).get("uid") or "")
    if not uid:
        return None
    try:
        import radai_queue_state as fila
    except Exception:
        return None
    try:
        return fila.assumir(uid, str((s or {}).get("pasta") or ""))
    except Exception as e:
        if log:
            try:
                log(u"a fila nao marcou o comeco da serie ...%s (%s: %s) -- "
                    u"ela roda sem o card acender" % (uid[-8:],
                                                      type(e).__name__,
                                                      str(e)[:120]))
            except Exception:
                pass
        return None


_MAX_RETOMADAS = 2


def _dono_do_lock(s, marcadores):
    ler = (marcadores or {}).get("read_marker")
    if not ler:
        return u""
    try:
        reg = ler((s or {}).get("pasta", ""), (s or {}).get("uid", ""),
                  "lock") or {}
        return str(reg.get("machine") or u"")
    except Exception:
        return u""


def _dono_da_entrega(s, marcadores, motivo=u"", maquina=u""):
    eu = u"%s" % (maquina or u"")
    ler = (marcadores or {}).get("read_marker")
    if ler is not None:
        try:
            reg = ler((s or {}).get("pasta", ""), (s or {}).get("uid", ""),
                      "entrega") or {}
            quem = u"%s" % (reg.get("machine") or u"")
            if quem and quem != eu:
                return quem
        except Exception:
            pass
    m = re.search(u"`([^`]{1,60})`", u"%s" % (motivo or u""))
    if m and m.group(1) != eu:
        return m.group(1)
    return u""


def _lock_liberou(carga, marcadores):
    m = marcadores or {}
    s = dict(carga or {})
    if not s.get("uid") or "has_marker" not in m:
        return False
    try:
        if s.get("zip"):
            real, erro = resolver_pasta(s)
            if erro or not real:
                return False
            s["pasta"] = real
        pasta, uid = s.get("pasta", ""), s["uid"]
        if m["has_marker"](pasta, uid, "done"):
            return True
        if not m["has_marker"](pasta, uid, "lock"):
            return True
        diag = m.get("diagnostico")
        if not diag:
            return False
        estado, _dado = diag(pasta, uid)
        return estado in ("livre", "travado", "morto")
    except Exception:
        return False


def _devolver_os_liberados(fila, marcadores, tentadas, retomadas, log=None):
    def _livre(carga):
        chave = (str(carga.get("uid") or ""), str(carga.get("pasta") or ""))
        if retomadas.get(chave, 0) >= _MAX_RETOMADAS:
            return False
        return _lock_liberou(carga, marcadores)
    try:
        voltaram = fila.troca_de_paciente(livre=_livre) or []
    except Exception as e:
        if log:
            try:
                log(u"a troca de paciente nao devolveu os pulados (%s: %s) -- "
                    u"eles ficam pulados" % (type(e).__name__, str(e)[:120]))
            except Exception:
                pass
        return []
    for chave in voltaram:
        tentadas.discard(chave)
        retomadas[chave] = retomadas.get(chave, 0) + 1
        if log:
            try:
                log(u"serie ...%s voltou a esperar: o lock que a pulou "
                    u"liberou (concluida, solto ou sem sinal de vida)"
                    % str(chave[0])[-8:])
            except Exception:
                pass
    return voltaram


def _series_a_rodar(series, da_fila, marcadores=None, log=None):
    try:
        import radai_queue_state as fila
    except Exception:
        fila = None
    if da_fila and fila is not None:
        tentadas = set()
        retomadas = {}
        while True:
            if _fechando_ao_fim(fila, log):
                return
            _devolver_os_liberados(fila, marcadores, tentadas, retomadas, log)
            try:
                s = fila.proxima_esperando(excluir=tentadas)
            except Exception as e:
                raise RuntimeError(
                    u"a fila nao foi lida (%s: %s) -- o lote parou, e as "
                    u"series que esperavam continuam na fila"
                    % (type(e).__name__, str(e)[:160]))
            if not s:
                return
            tentadas.add((str(s.get("uid") or ""), str(s.get("pasta") or "")))
            yield s
        return
    for s in (series or ()):
        if _fechando_ao_fim(fila, log):
            return
        if fila is not None:
            try:
                quer = fila.ainda_esperando((s or {}).get("uid", ""),
                                            (s or {}).get("pasta", ""))
            except Exception:
                quer = True
            if not quer and (s or {}).get("uid"):
                continue
        yield s


FRASE_DO_FECHAR_AO_FIM = (u"o navegador foi fechado: o lote nao comeca a "
                          u"proxima serie, e o programa se encerra")
FRASE_DO_LOTE_RETOMADO = (u"uma tela voltou a responder: o encerramento foi "
                          u"cancelado, e o lote que parou entre series segue")


def _fechando_ao_fim(fila, log=None):
    try:
        sim = bool(fila is not None and fila.fechando_ao_fim())
    except Exception:
        sim = False
    if sim:
        with _TRAVA:
            _JOB["parou_ao_fechar"] = True
        if log:
            try:
                log(FRASE_DO_FECHAR_AO_FIM)
            except Exception:
                pass
    return sim


def _rodar_tudo(series, incluir_nv, tasks, device, python_exe,
                timeout_task_s, timeout_nv_s, log, marcadores, maquina,
                heartbeat_s, suavizar_mm, da_fila=False):
    if log:
        try:
            import engine as _eng
            log(u"calibracao de arranque: %s"
                % _eng.diagnostico_de_computacao(device))
        except Exception as _e:
            try:
                log(u"calibracao de arranque nao mediu (%s) — a fila segue"
                    % type(_e).__name__)
            except Exception:
                pass
    try:
        _tem_a_vez = _esperar_a_vez_do_lote(log)
        if not _tem_a_vez and log:
            try:
                log(u"o lote parou antes de comecar: pausado ou cancelado "
                    u"enquanto esperava a serie do vigia")
            except Exception:
                pass
        for s in (_series_a_rodar(series, da_fila, marcadores=marcadores,
                                  log=log) if _tem_a_vez else ()):
            _restam = None
            if da_fila:
                try:
                    import radai_queue_state as _fq
                    _restam = len(_fq.series_esperando())
                except Exception:
                    _restam = None
            with _TRAVA:
                if _JOB["cancelar"]:
                    break
                if _restam is not None:
                    _JOB["total"] = int(_JOB.get("feitas") or 0) + _restam
                if _JOB.get("pausar"):
                    if log:
                        try:
                            log(u"pausado pelo operador — a serie atual "
                                u"terminou e a proxima nao comeca")
                        except Exception:
                            pass
                    break
            if _fila_assume(s, log) is False:
                if log:
                    try:
                        log(u"serie ...%s saiu da fila antes de comecar -- "
                            u"nao roda" % str((s or {}).get("uid", ""))[-8:])
                    except Exception:
                        pass
                continue
            with _TRAVA:
                _JOB["uid_atual"] = (s or {}).get("uid", "")
                _JOB["serie_desde"] = time.time()
                _JOB["parte"] = ""
            try:
                import radai_archive as _arq
                _n, _e = _arq.limpar_temporaria()
                if _n and log:
                    log("faxina: %d pasta(s) temporaria(s) de execucoes "
                        "anteriores removida(s)%s"
                        % (_n, (" (%d recusaram)" % _e) if _e else ""))
            except Exception:
                pass
            r = _uma_serie(s, incluir_nv, tasks, device, python_exe,
                           timeout_task_s, timeout_nv_s, log, marcadores,
                           maquina, heartbeat_s, suavizar_mm)
            with _TRAVA:
                _JOB["resultados"].append(r)
                _JOB["feitas"] += 1
            _uid = (s or {}).get("uid", "")
            _pst = (s or {}).get("pasta", "")
            if (r or {}).get("cancelado"):
                _fila_diz("cancelado", _uid, pasta=_pst)
            elif (r or {}).get("pulo") == "outra":
                _fila_diz("skipped", _uid, dono=(r or {}).get("dono", ""),
                          pasta=_pst, motivo=(r or {}).get("pulada", ""))
            elif (r or {}).get("pulo") == "concluida":
                _fila_diz("concluida", _uid, pasta=_pst)
            elif (r or {}).get("pulada"):
                _fila_diz("feito", _uid, pasta=_pst)
            elif (r or {}).get("erro"):
                _fila_diz("falhou", _uid, pasta=_pst,
                          nao_contornavel=(r or {}).get("nao_contornavel")
                          or u"",
                          mensagem=_sem_caminho_nem_uid(
                              u"%s" % ((r or {}).get("erro") or u""))[:200])
            else:
                _voltou = _CFG.get("recurso_voltou")
                if callable(_voltou):
                    try:
                        _voltou()
                    except Exception:
                        pass
                _fila_diz("pronto", _uid, pasta=_pst,
                          faltou=[f.get("estrutura") for f in
                                  (r or {}).get("faltou") or ()],
                          sem_estrutura=[f.get("task") for f in
                                         (r or {}).get("tasks_sem_estrutura")
                                         or ()],
                          pendentes=_pendentes_por_memoria(r),
                          parcial=((r or {}).get("parcial") or {}).get(
                              "motivo") or u"")
    except Exception as e:
        with _TRAVA:
            _JOB["erro"] = "%s: %s" % (type(e).__name__, str(e)[:250])
        if log:
            try:
                log(u"o lote parou: %s: %s" % (type(e).__name__, str(e)[:250]))
            except Exception:
                pass
    finally:
        with _TRAVA:
            _JOB["terminando"] = True
            _JOB["rodando"] = False
            _JOB["etapa"] = "pronto"
            _JOB["uid_atual"] = ""
            _JOB["serie_desde"] = 0.0
            _JOB["parte"] = ""
            _JOB["terminou"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            _erro_do_lote = _JOB.get("erro") or u""
        try:
            import radai_queue_state as _fq_fim
            _fq_fim.fechar_rodando_do_lote(
                (u"o lote parou: " + _sem_caminho_nem_uid(_erro_do_lote)[:160])
                if _erro_do_lote else u"o lote parou no meio desta serie")
        except Exception:
            pass
        _soltar_a_vez_do_lote()
        soltar_extracoes_do_lote()
        _comecou_outra = False
        try:
            try:
                _comecou_outra = bool(_proxima_da_fila())
            except Exception:
                pass
            if not _comecou_outra:
                _turno_na_vez(log)
        finally:
            with _TRAVA:
                _JOB["terminando"] = False


def retomar_o_lote_que_parou_ao_fechar(log=None):
    with _TRAVA:
        if not _JOB.get("parou_ao_fechar"):
            return None
        _JOB["parou_ao_fechar"] = False
        if _JOB["rodando"] or _JOB.get("cancelar"):
            return None
    try:
        import radai_queue_state as _fila
        if _fila.fechando_ao_fim():
            return None
        series = _fila.series_esperando()
    except Exception:
        return None
    if not series or not _CFG:
        return None
    if log:
        try:
            log(FRASE_DO_LOTE_RETOMADO)
        except Exception:
            pass
    return iniciar(series, ja_na_fila=True, incluir_nv=None, tasks=None,
                   device=_CFG.get("device", "auto"),
                   python_exe=_CFG.get("python_exe"),
                   timeout_task_s=_CFG.get("timeout_task_s", 10800),
                   timeout_nv_s=_CFG.get("timeout_task_s", 10800),
                   log=_CFG.get("log"), marcadores=_CFG.get("marcadores"),
                   maquina=_CFG.get("maquina", ""),
                   heartbeat_s=_CFG.get("heartbeat_s", 300),
                   suavizar_mm=_CFG.get("suavizar_mm", 1.0),
                   ocupado=_CFG.get("ocupado"))


def _turno_na_vez(log=None):
    with _TRAVA:
        if (_JOB.get("rodando") or _JOB.get("cancelar") or _JOB.get("pausar")
                or _JOB.get("erro")):
            return None
    abrir = _CFG.get("abrir_turno")
    if not callable(abrir):
        return None
    try:
        import radai_queue_state as _fila
        if not _fila.turno_na_vez():
            return None
    except Exception:
        return None
    if log:
        try:
            log(u"a fila chegou no card do Overnight Run: abrindo o turno")
        except Exception:
            pass
    try:
        return abrir()
    except Exception as e:
        motivo = _sem_caminho_nem_uid(u"%s: %s" % (type(e).__name__,
                                                   str(e)[:200]))
        try:
            import radai_queue_state as _fila
            _fila.fechar_turno("falhou", motivo)
        except Exception:
            pass
        if log:
            try:
                log(u"o turno da noite nao abriu: %s" % motivo)
            except Exception:
                pass
        return {"ok": False, "erro": motivo}


def _pastas_para_trocar(s):
    import radai_records
    try:
        tmp = [tempfile.gettempdir()]
    except Exception:
        tmp = []
    return radai_records.pastas_para_trocar(
        [(s or {}).get("pasta"), (s or {}).get("zip")], prefixos=tmp)





def bater_lock(renovar, pasta, uid, parar, intervalo_s, log=None,
               entrega=None):
    falhas = 0
    u8 = str(uid or "")[-8:]
    while not parar.is_set():
        try:
            ok = bool(renovar(pasta, uid))
        except Exception:
            ok = False
        if ok:
            if falhas >= 2 and log:
                log("   o sinal de vida da serie ...%s voltou a ser gravado "
                    "(falhou %d vez(es) seguidas)" % (u8, falhas))
            falhas = 0
        else:
            falhas += 1
            if falhas == 2 and log:
                log("   NAO consigo gravar o sinal de vida da serie ...%s ha "
                    "%.0f min. Se o lock envelhecer, outra maquina pode "
                    "assumir esta serie e o trabalho sai dobrado. Confira o "
                    "acesso de escrita a pasta _RadAI."
                    % (u8, falhas * float(intervalo_s) / 60.0))
        if entrega is not None:
            try:
                entrega()
            except Exception:
                pass
        parar.wait(intervalo_s)


class PrimeiraEntregaValeu(Exception):
    pass


def reservar_a_entrega(marcadores, pasta, uid, log=None):
    m = marcadores or {}
    u8 = str(uid or "")[-8:]
    reservar = m.get("reservar_entrega")
    if reservar is None:
        if log:
            log("   serie ...%s: sem a reserva de entrega (o vigia desta "
                "estacao nao a injeta) -- publico sem conferir se outra "
                "maquina ja entregou" % u8)
        return True, False, u""
    try:
        pode, motivo = reservar(pasta, uid)
    except Exception as e:
        return False, False, (u"nao consegui reservar a entrega (%s)"
                              % type(e).__name__)
    if not pode:
        return False, False, (str(motivo or u"")[:200]
                              or u"outra maquina entregou esta serie")
    meu = m.get("lock_e_meu")
    if meu is not None:
        try:
            e_meu, dono = meu(pasta, uid)
        except Exception:
            e_meu, dono = True, u""
        if not e_meu and log:
            log("   serie ...%s: o lock agora e de `%s` (o sinal de vida "
                "desta maquina falhou e ela assumiu). Ninguem entregou "
                "ainda, e a primeira entrega vale: esta maquina publica, e a "
                "outra descarta quando terminar." % (u8, str(dono)[:60]))
    return True, True, u""


def _afastar_o_done(marcadores, pasta, uid, maquina=u""):
    m = marcadores or {}
    if not m["has_marker"](pasta, uid, "done"):
        return None
    atual = str(m["m_path"](pasta, uid, "done"))
    quem = re.sub(r"[^A-Za-z0-9_-]", u"", u"%s" % (maquina or u""))[:40]
    lado = u"%s.substituido.%s.%d" % (atual, quem or u"maquina", os.getpid())
    os.replace(atual, lado)
    return lado


def _devolver_o_done(marcadores, pasta, uid, lado, entregou, log=None):
    if not lado:
        return
    m = marcadores or {}
    try:
        if entregou or m["has_marker"](pasta, uid, "done"):
            os.remove(lado)
        else:
            os.replace(lado, str(m["m_path"](pasta, uid, "done")))
            if log:
                log("   serie ...%s: esta execucao nao entregou -- o marcador "
                    "de conclusao anterior voltou, e a serie fica como "
                    "estava" % str(uid or "")[-8:])
    except Exception as e:
        if log:
            log("   serie ...%s: nao consegui arrumar o marcador de conclusao "
                "anterior (%s)" % (str(uid or "")[-8:], type(e).__name__))


def _soltar_a_entrega(marcadores, pasta, uid):
    f = (marcadores or {}).get("soltar_entrega")
    if f is None:
        return
    try:
        f(pasta, uid)
    except Exception:
        pass


def _extracao_em_uso(caminho):
    try:
        import radai_archive as _arq
        _arq.marcar_em_uso(caminho)
    except Exception:
        return
    with _TRAVA:
        _JOB.setdefault("em_uso", []).append(str(caminho))


def soltar_extracoes_do_lote():
    with _TRAVA:
        lista = list(_JOB.get("em_uso") or [])
        _JOB["em_uso"] = []
    try:
        import radai_archive as _arq
    except Exception:
        return
    for c in lista:
        try:
            _arq.soltar_em_uso(c)
        except Exception:
            pass


def _task_marcada_pode_falhar(e):
    if type(e).__name__ == "Cancelado":
        return False
    with _TRAVA:
        if _JOB.get("cancelar"):
            return False
    f = _CFG.get("erro_de_ambiente")
    if callable(f):
        try:
            if f(e):
                return False
        except Exception:
            pass
    return True


def _classe_do_erro(e):
    f = _CFG.get("classificar_erro")
    if callable(f):
        try:
            return str(f(e))
        except Exception:
            pass
    return u"nao_classificada"


def _motivo_do_erro(e):
    txt = u"%s: %s" % (type(e).__name__, e)
    f = _CFG.get("limpar_erro")
    if callable(f):
        try:
            txt = str(f(txt)) or type(e).__name__
        except Exception:
            pass
    return _sem_caminho_nem_uid(txt)


_UID_NO_TEXTO = re.compile(r"(?<![\d.])\d+(?:\.\d+){4,}(?![\d.])")


def _sem_caminho_nem_uid(texto):
    t = str(texto or u"")
    if not t:
        return t
    try:
        import radai_records
        t = radai_records.sem_caminhos(t)
    except Exception:
        t = re.sub(r"(?:[A-Za-z]:[\\/]|\\\\[^\\/\s]+[\\/])[^\r\n]*",
                   u"<caminho>", t)
    return _UID_NO_TEXTO.sub(u"<uid>", t)


def _trava_do_lote():
    t = _CFG.get("trava")
    if not isinstance(t, dict):
        return None
    fora = {}
    for k_min, k_s in (("sem_pulso_min", "sem_pulso_s"),
                       ("paginando_min", "paginando_s")):
        try:
            if t.get(k_min) is not None:
                fora[k_min] = float(t[k_min])
            elif t.get(k_s) is not None:
                fora[k_min] = float(t[k_s]) / 60.0
        except (TypeError, ValueError):
            pass
    try:
        if t.get("ram_pct") is not None:
            fora["ram_pct"] = float(t["ram_pct"])
    except (TypeError, ValueError):
        pass
    return fora or None





MOTIVO_DOS_NIVEIS_FORA_DO_MODO = {
    "fast": u"o FAST nao roda os niveis cervicais: ele grava so o "
            u"RadAI_STUDY_Fast, e os niveis vao ao FULL, que o FAST nao monta",
    "lista": u"a lista do chamador nao pede os niveis cervicais",
}


def processamento_do_caso(escolha, origem, tasks=(), travamentos=(),
                          recortes=None, meta_entrega=None, oar_fora=(),
                          niveis=None, do_job=None, log_motor=(),
                          dispositivo=None, oar_fora_por_regiao=None):
    import radai_records as _RG
    md = _md()
    e = escolha or {}
    pr = {"modo": origem if origem in md.MODOS_DA_SERIE else None,
          "tasks_ligadas": [t for t in (tasks or ()) if t]}
    if origem == md.MODO_PERSO:
        pr["protocolos"] = list(e.get("protocolos") or ())
        pr["tasks_desligadas"] = sorted(
            t for t, v in (e.get("tasks") or {}).items() if not v)
        pr["comparacao"] = dict(e.get("comparacao") or {})
        pr["oar_fora"] = list(oar_fora or ())
    elif origem in md.MODOS_DA_SERIE:
        pr["comparacao"] = dict((k, 0) for k in CHAVES_DA_COMPARACAO)
    try:
        import engine
        _entrada = getattr(engine, "entrada_do_recorte", None)
    except Exception:
        _entrada = None
    cb = _RG.clip_box_do_caso(recortes, modo=origem, entrada=_entrada)
    if cb:
        pr["clip_box"] = cb
    m = meta_entrega or {}
    if "regras_de_gravacao" in m:
        pr["remocoes"] = _RG.remocoes_do_full(m.get("regras_de_gravacao"))
    if "ilhas_em_revisao" in m:
        pr["ilhas_em_revisao"] = _RG.ilhas_do_full(m.get("ilhas_em_revisao"))
    if m.get("acabamento"):
        pr["acabamento"] = _RG.acabamento_do_caso(m.get("acabamento"))
    if oar_fora_por_regiao is not None:
        pr["oar_fora_por_regiao"] = _RG.oar_fora_por_regiao_do_caso(
            oar_fora_por_regiao)
    trv = []
    for x in travamentos or ():
        x = dict(x or {})
        trv.append({"task": x.get("task"), "motivo": x.get("motivo"),
                    "onde": x.get("onde"), "retomada": x.get("retomada"),
                    "numeros": x.get("numeros")})
    pr["travamentos"] = trv
    try:
        pico = _RG.pico_de_memoria(log_motor)
    except Exception:
        pico = None
    if pico:
        pr["pico_memoria"] = pico
    dj = do_job or {}
    _pl = _RG.plano_do_caso(dj.get("plano"), dj.get("_planos"),
                            dispositivo=dispositivo)
    if _pl:
        pr["plano_dispositivo"] = _pl
    if niveis:
        pr["niveis_cervicais"] = dict(niveis)
    return pr


def _notificar_a_serie(chave_texto, s, log, gravados=None):
    try:
        import radai_notify as _rn
        args = [str((s or {}).get("uid") or u"")[-8:]]
        if chave_texto == "ok":
            args.append(u" + ".join(_rn.rotulo_do_gravado(g)
                                    for g in list(gravados or [])))
        return _rn.notificar(
            "titulo_ok" if chave_texto == "ok" else "titulo_erro",
            chave_texto, *args, log=log)
    except Exception:
        return False


def _uma_serie(s, incluir_nv, tasks, device, python_exe,
               timeout_task_s, timeout_nv_s, log, marcadores, maquina,
               heartbeat_s, suavizar_mm=1.5):
    import engine
    t0 = time.time()
    _coletor = None
    try:
        import radai_records
        _coletor = radai_records.Coletor(log)
        log = _coletor
    except Exception:
        pass
    log = _com_sonda(log)
    rotulo = "%s · %s" % (s.get("pid", "?"), s.get("curto", ""))
    _abrir_cronometro(log)

    if s.get("zip"):
        _real, _erro_zip = resolver_pasta(s)
        if _erro_zip or not _real or not os.path.isabs(_real):
            res = {"uid": s["uid"], "pid": s.get("pid", ""),
                   "curto": s.get("curto", ""), "pasta": s.get("pasta", ""),
                   "rs": "", "estruturas": 0, "v3d": 0, "segundos": 0.0,
                   "pulada": "", "pulo": "", "erro": ""}
            res["erro"] = ("nao consegui abrir o pacote da serie (%s) — nada "
                           "foi gravado" % (_erro_zip or "caminho relativo"))
            if log:
                log("pulei %s: %s" % (rotulo, res["erro"]))
            return res
        s = dict(s)
        s["pasta"] = _real
        _extracao_em_uso(_real)

    res = {"uid": s["uid"], "pid": s.get("pid", ""), "curto": s.get("curto", ""),
           "pasta": s["pasta"], "rs": "", "estruturas": 0, "v3d": 0,
           "segundos": 0.0, "erro": "", "pulada": "", "pulo": ""}
    stage, tenho_lock, parar_hb = None, False, threading.Event()
    import radai_archive as _arq_serie
    _tmp_serie = _arq_serie.TemporariaDaSerie()

    _substituir = (s.get("substituir") is True)
    _subst = {"lado": None, "entregou": False}
    _resolver_afastado = (marcadores or {}).get("resolver_done_afastado")
    if _resolver_afastado is not None:
        try:
            _resolver_afastado(s["pasta"], s["uid"])
        except Exception:
            pass
    _afastar_sem_rs = (marcadores or {}).get("afastar_sem_rtstruct")
    if _afastar_sem_rs is not None:
        try:
            if _afastar_sem_rs(s["pasta"], s["uid"]) and log:
                log("%s tinha o marcador de pronta sem nenhum RTSTRUCT RadAI "
                    "no disco: nao vale como pronta, e eu refaco" % rotulo)
        except Exception:
            pass
    try:
        if (marcadores["has_marker"](s["pasta"], s["uid"], "done")
                and _substituir):
            if log:
                log("%s ja estava concluida, e o «Substituir» foi confirmado "
                    "na tela: refaco. O marcador anterior sai so na hora de "
                    "gravar, e volta se esta execucao nao entregar" % rotulo)
        elif marcadores["has_marker"](s["pasta"], s["uid"], "done"):
            res["pulada"] = "ja concluida (marcador done)"
            res["pulo"] = "concluida"
            if log:
                log("pulei %s: %s" % (rotulo, res["pulada"]))
            return res
    except Exception:
        pass

    try:
        tenho_lock = bool(marcadores["claim"](
            s["pasta"], s["uid"],
            {"machine": maquina, "origem": "rodar agora",
             "start": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}))
    except Exception as e:
        res["erro"] = "nao consegui reivindicar: %s" % str(e)[:150]
        return res
    if not tenho_lock:
        res["pulada"] = "outra estacao esta processando (ou pasta sem permissao)"
        res["pulo"] = "outra"
        res["dono"] = _dono_do_lock(s, marcadores)
        if log:
            log("pulei %s: %s%s" % (rotulo, res["pulada"],
                                    (" -- lock de %s" % res["dono"])
                                    if res["dono"] else ""))
        return res

    _entrega = {"reservada": False}
    _entrega_trava = threading.Lock()
    _renovar_entrega = marcadores.get("renovar_entrega")

    def _bater_entrega():
        with _entrega_trava:
            if _entrega["reservada"] and _renovar_entrega is not None:
                _renovar_entrega(s["pasta"], s["uid"])
    _hb = None
    dev = None
    _do_job = {}
    _escolha_da_serie = None
    _passos_do_full = None
    _seg_full = None
    _etapas_ts = []
    _tasks_ok = []
    _tasks_falharam = []
    _medidas = {}
    _esc = None
    _origem = None
    _anat = {"regioes": (), "coracao_cm3": None, "pescoco": None,
             "laudo": []}
    _niveis = None
    _mot = None
    _travamentos = []
    _recortes = {}
    _puladas = []
    _meta_da_entrega = {}
    _sem_estrutura = []
    _do_cache = []
    _chaves_do_cache = {}
    _faltou = []
    _pul_mem = []
    _parcial_da_entrega = {}
    _oar_fora_valeu = []
    _fora_por_regiao = [None]
    _log_motor = []
    # GUARDA: tudo o que pode levantar depois do claim fica dentro do try; so o finally solta a trava.
    try:
        log = _abrir_log_e_caso_do_lote(s, marcadores, log)
        _hb = threading.Thread(
            target=bater_lock,
            args=(marcadores["renovar"], s["pasta"], s["uid"], parar_hb,
                  heartbeat_s, log),
            kwargs={"entrega": _bater_entrega},
            daemon=True)
        _hb.start()
        _arq_serie.conferir_escrita_no_destino(s["pasta"])
        _passo("copiando a serie", rotulo)
        pasta_real, erro_zip = resolver_pasta(s)
        if erro_zip:
            raise RuntimeError("nao consegui abrir o pacote da serie: %s"
                               % erro_zip)
        if not pasta_real or not os.path.isdir(pasta_real):
            raise RuntimeError("nao achei a pasta da serie (%s)"
                               % (pasta_real or s.get("pasta") or "?"))
        arquivos = [os.path.join(pasta_real, f)
                    for f in sorted(os.listdir(pasta_real))
                    if os.path.isfile(os.path.join(pasta_real, f))]
        if not s.get("modalidade"):
            _mod_lida = _modalidade_lida_dos_cortes(arquivos, s["uid"])
            if _mod_lida:
                s = dict(s)
                s["modalidade"] = _mod_lida
        arquivos = _so_da_serie(arquivos, s["uid"], s.get("modalidade"))
        if len(arquivos) < 5:
            fundo = []
            for raiz, _d, fs in os.walk(pasta_real):
                fundo += [os.path.join(raiz, f) for f in sorted(fs)]
            if len(fundo) > len(arquivos):
                arquivos = _so_da_serie(fundo, s["uid"], s.get("modalidade"))
        if len(arquivos) < 5:
            raise RuntimeError(
                "achei so %d corte(s) da serie em %s"
                % (len(arquivos), pasta_real))
        _tmp_serie.abrir()
        _arq_serie.conferir_espaco_da_serie(arquivos, n_tasks=len(tasks or []))
        stage = tempfile.mkdtemp(prefix="radai_lote_")
        engine.copy_sorted(arquivos, stage)
        ref = engine.load_sitk(stage)
        engine.conferir_volume_contornavel(
            ref, min_cortes=5, modalidade=str(s.get("modalidade") or "CT"))
        try:
            import radai_records as _reg_med
            _medidas.update(_reg_med.medidas_da_imagem(ref, len(arquivos)))
        except Exception:
            pass

        dev = engine._resolve_device(device)
        masks = {}
        jid = engine._job_new()
        with _TRAVA:
            _JOB["jid"] = jid

        parar_dren = threading.Event()
        _drenador = None
        if log:
            _drenador = threading.Thread(
                target=engine.drenar_log,
                args=(jid, (lambda ln: log("   " + ln)), parar_dren),
                daemon=True)
            _drenador.start()
        import radai_modes as _md

        _esc = escolha_da_serie(s)
        _escolha_da_serie = {"modo": _esc["modo"]}
        if _esc["modo"] == _md.MODO_PERSO:
            _escolha_da_serie.update({
                "protocolos": list(_esc["protocolos"]),
                "tasks": dict(_esc["tasks"]),
                "comparacao": dict(_esc["comparacao"]),
                "oar_fora": list(_esc["oar_fora"])})
        if log and s.get("legado_v82"):
            log("a serie veio com a escolha da v8.2 (%s), que saiu: ela roda "
                "no modo %s" % (", ".join(s.get("legado_v82") or ()),
                                _esc["modo"].upper()))
        modalidade = str(s.get("modalidade") or "CT")
        base = _md.base_de(modalidade)
        try:
            import radai_tasks as _rt
            base = (_rt.lista_para_rodar([base], log=log) or [base])[0]
        except Exception:
            pass

        if not base_alimenta_o_entregue(modalidade):
            raise RuntimeError(
                "a base desta modalidade nao chega ao contorno entregue "
                "(%s -> %s): %s nao tem rotulo em engine.TS_MAP, entao o "
                "RTSTRUCT sairia vazio. Falta mapear as estruturas de %s "
                "para TG-263." % (modalidade, base, base, base))

        _lista_explicita = [t for t in (tasks or ()) if t]

        _recorte = recorte_no_corpo_da_estacao()
        cruas = {}

        tasks, _origem = tasks_iniciais(s, _lista_explicita, log)
        try:
            tasks = list(_rt.lista_para_rodar(list(tasks), log=log))
        except Exception:
            tasks = list(tasks)
        try:
            _fam_base = _rt.familia_da_task(base)
            tasks = [base] + [t for t in tasks
                              if _rt.familia_da_task(t) != _fam_base]
        except Exception:
            tasks = [base] + [t for t in tasks if t != base]
        if log:
            log("modo da serie: %s | base | %s" % (
                {"fast": "FAST", "auto": "AUTO",
                 "perso": "PERSONALIZADO"}.get(_origem, _origem), base))

        _anat = {"regioes": (), "coracao_cm3": None, "pescoco": None,
                 "laudo": []}
        permitidas_, achados_ = _achados_e_permitidas()

        def _depois_da_base(t, masks_ate_aqui, cruas_ate_aqui):
            try:
                if _rt.familia_da_task(t) != _rt.familia_da_task(base):
                    return []
            except Exception:
                if t != base:
                    return []
            try:
                import radai_geom as _geom
                _grade_b = _geom.Grade.de_sitk(ref)
            except Exception:
                _grade_b = None
            import radai_topography as _tp_anat
            _an = _tp_anat.anatomia_da_base(
                masks_ate_aqui, _grade_b, cruas=cruas_ate_aqui, motor=engine)
            reg, laudo = _an["regioes"], list(_an["laudo"])
            cor, pes = _an["coracao_cm3"], _an["pescoco"]
            _anat.update({"regioes": tuple(reg), "laudo": list(laudo),
                          "coracao_cm3": cor, "pescoco": pes})
            if log:
                log("anatomia da serie (depois da base): %s"
                    % (", ".join(reg) or "nenhuma regiao com lista"))
                for ln in laudo:
                    log("   " + ln)
            if _origem not in (_md.MODO_FAST, _md.MODO_AUTO):
                return []
            novas = list(tasks_depois_da_base(
                _origem, reg, cor, modalidade, permitidas=permitidas_,
                achados=achados_, catalogo=_catalogo_de_tasks()))
            try:
                novas = list(_rt.lista_para_rodar(novas, log=log))
            except Exception:
                pass
            if _origem == _md.MODO_FAST:
                novas = _na_ordem_do_fast(novas)
            if log:
                log("pela anatomia (%s): %s"
                    % (_origem.upper(), ", ".join(novas) or "so a base"))
            return novas

        _obrig = tuple(tasks) if _origem == "lista" else ()
        _erros_das_tasks = {}
        _falharam_antes = dict(
            (f["task"], f) for f in (s.get("so_pos_falharam") or ())
            if isinstance(f, dict) and f.get("task")) if s.get("so_pos") else {}

        def _rodar_uma(ref_, t, device_, jid_, **kw):
            if s.get("so_pos"):
                kw["so_cache"] = True
            try:
                return engine.run_ts_task(ref_, t, device=device_, jid=jid_,
                                          **kw)
            except BaseException as _e_t:
                _erros_das_tasks[t] = _e_t
                raise

        def _ao_terminar(t, dados):
            try:
                import radai_records as _reg_t
                try:
                    _job_t = engine._job(jid) or {}
                except Exception:
                    _job_t = {}
                _etapas_ts.append(_reg_t.etapa_da_task(
                    t, float(dados.get("segundos") or 0.0),
                    maquina or _maquina_desta_estacao(),
                    _reg_t.dispositivo_da_task(_job_t, t, dev),
                    falhou=not dados.get("ok")))
            except Exception:
                pass
            if dados.get("ok"):
                _passo("segmentando: %s (pronta)" % t, rotulo)

        def _ao_falhar(t, e_t):
            if not _task_marcada_pode_falhar(e_t):
                return True
            if type(e_t).__name__ == "SemCacheParaOPos":
                # GUARDA: a task que ja tinha falhado na entrega volta como
                # a mesma falha registrada; qualquer outra sem cache derruba.
                if t not in _falharam_antes:
                    return True
                if log:
                    log("a task `%s` tinha falhado na entrega e nao esta no "
                        "cache: fica de fora de novo, com o mesmo motivo" % t)
                return False
            if log:
                log("a task `%s` FALHOU nesta serie (%s: %s) — a serie "
                    "segue: o entregue sai sem o que ela daria"
                    % (t, _classe_do_erro(e_t), _motivo_do_erro(e_t)[:200]))
                try:
                    import traceback as _tb
                    for _l in _tb.format_exception(
                            type(e_t), e_t, e_t.__traceback__):
                        for _ll in str(_l).rstrip().splitlines():
                            log("   " + _ll)
                except Exception:
                    pass
            return False

        _passo("segmentando: %s" % base, rotulo)
        try:
            _res_t = engine.rodar_tasks(
                ref, tasks, dev, jid, timeout_s=timeout_task_s,
                trava=_trava_do_lote(), rodar=_rodar_uma,
                depois_de=_depois_da_base, ao_terminar=_ao_terminar,
                ao_falhar=_ao_falhar, classificar=_classe_do_erro,
                obrigatorias=_obrig, modo=_origem, cruas=cruas,
                recorte_no_corpo=_recorte)
            masks = dict(_res_t.get("masks") or {})
            _tasks_ok.extend(_res_t.get("rodaram") or ())
            for _f in _res_t.get("falharam") or ():
                _t = (_f or {}).get("task")
                _ex = _erros_das_tasks.get(_t)
                if (_t in _falharam_antes
                        and type(_ex).__name__ == "SemCacheParaOPos"):
                    _tasks_falharam.append(dict(_falharam_antes[_t]))
                    continue
                _tasks_falharam.append({
                    "task": _t,
                    "erro": (_motivo_do_erro(_ex) if _ex is not None
                             else _sem_caminho_nem_uid(
                                 str((_f or {}).get("erro") or u"")))[:300],
                    "classe": str((_f or {}).get("classe") or u"")})
            _travamentos.extend(dict(x) for x in
                                (_res_t.get("travamentos") or ()))
            _recortes.update(dict(_res_t.get("recortes") or {}))
            _puladas.extend(dict(x) for x in (_res_t.get("puladas") or ()))
            _pul_mem[:] = _pendentes_por_memoria({"tasks_puladas_por_memoria":
                                                  _pul_mem}, _res_t)
            _sem_estrutura.extend(dict(x) for x in
                                  (_res_t.get("ausentes") or ()))
            tasks = list(tasks) + [t for t in _tasks_ok if t not in tasks] \
                + [f.get("task") for f in _tasks_falharam
                   if f.get("task") not in tasks]
        finally:
            parar_dren.set()
            if _drenador is not None:
                try:
                    _drenador.join(timeout=10.0)
                except Exception:
                    pass
            try:
                import radai_records as _reg
                _job_fim = engine._job(jid)
                del _log_motor[:]
                _log_motor.extend(str(x) for x in
                                  ((_job_fim or {}).get("log") or ()))
                _do_job.update(_reg.do_job(_job_fim))
                _pul_mem[:] = _pendentes_por_memoria(
                    {"tasks_puladas_por_memoria": _pul_mem}, _job_fim)
                for _k in ("planos", "travamentos", "recortes"):
                    if (_job_fim or {}).get(_k):
                        _do_job.setdefault("_" + _k, _job_fim.get(_k))
                _do_cache[:] = sorted(
                    t for t, v in dict((_job_fim or {}).get("cache")
                                       or {}).items()
                    if (v or {}).get("lido"))
                _chaves_do_cache.update(
                    (t, (v or {}).get("chave")) for t, v in
                    dict((_job_fim or {}).get("cache") or {}).items()
                    if (v or {}).get("chave"))
            except Exception as _e:
                _do_job["job_ilegivel"] = type(_e).__name__
            try:
                engine._job_del(jid)
            except Exception:
                pass
        if not masks:
            raise RuntimeError("nenhuma estrutura gerada")
        if log:
            log("%d mascara(s) da inferencia (do modelo, antes do "
                "pos-processamento do FULL)" % len(masks))

        import radai_sets as _rs_nome
        rs_name = "RS_RadAI_%s_%s.dcm" % (_rs_nome.data_do_nome(s),
                                          s.get("curto", "serie"))

        _mot, _mot_origem = motores_da_serie(s, incluir_nv, _anat["regioes"])
        _niveis = {"rodam": False, "motivo": u""}
        if _origem == _md.MODO_AUTO:
            _pes = _anat.get("pescoco")
            if str(modalidade).upper() in ("MR", "MRI", "RM"):
                _niveis = {"rodam": False,
                           "motivo": u"so em TC (o modelo dos niveis e de "
                                     u"tomografia)"}
            elif _pes is not None:
                _niveis = {"rodam": bool(_pes[0]), "motivo": _pes[1]}
            else:
                _niveis = {"rodam": False,
                           "motivo": u"nao consegui medir o pescoco"}
            _mot["hnlnl"] = bool(_niveis["rodam"])
            for _c in _md.motores_do_auto(_anat["regioes"], modalidade):
                _mot[_c] = True
        elif _origem == _md.MODO_PERSO:
            _niveis = {"rodam": bool(_mot.get("hnlnl")),
                       "motivo": u"pela escolha da serie (protocolo ou chave)"}
        else:
            _niveis = {"rodam": False,
                       "motivo": MOTIVO_DOS_NIVEIS_FORA_DO_MODO.get(
                           _origem, MOTIVO_DOS_NIVEIS_FORA_DO_MODO["lista"])}
        if log:
            _ligados = [m for m in MOTORES_DO_LOTE if _mot.get(m)]
            log("motores adicionais desta serie: %s (%s)"
                % (", ".join(_ligados) or "nenhum",
                   {"perso": "pela escolha da serie, no PERSONALIZADO",
                    "auto": "no AUTO os niveis cervicais pelo pescoco e o "
                            "encefalo em TC pela anatomia",
                     "fast": "encefalo em TC pela anatomia; sem motores de comparacao",
                    "lista": "a lista do chamador nao pede motor"}.get(
                        _mot_origem, _mot_origem)))
            if (_origem in (_md.MODO_AUTO, _md.MODO_FAST)
                    and _niveis.get("motivo")):
                log("niveis cervicais: %s — %s"
                    % (u"rodam (vao para o FULL, nunca para o STUDY)"
                       if _niveis["rodam"] else u"nao rodam",
                       _niveis["motivo"]))

        try:
            import radai_geom
            _grade = radai_geom.Grade.de_sitk(ref)
        except Exception:
            _grade = None

        def _rodar_cads():
            try:
                import radai_cads_engine as CM
                _passo("CADS (comparacao)", rotulo)
                return CM.contornar(
                    stage, python_exe=python_exe,
                    dispositivo=engine._resolve_device(device),
                    timeout_s=None, log=log,
                    cancelado=lambda: bool(_JOB.get("cancelar"))) or {}
            except Exception as e:
                if log:
                    log("CADS nao rodou nesta serie (%s) — os outros "
                        "conjuntos nao foram afetados" % str(e)[:120])
                return {}
        cads_da_vez = {}
        _cads_antes = bool(_mot.get("cads")) and _liga_por_omissao("cads")
        if _cads_antes:
            cads_da_vez = _rodar_cads()

        try:
            import SimpleITK as _sitk
            _hu = _sitk.GetArrayFromImage(ref)
        except Exception:
            _hu = None
        _mod_serie = str(s.get("modalidade") or "").strip().upper() or None

        try:
            import radai_topography as _tp
            _velhos = list(_tp.entregas_a_substituir(
                _rs_da_serie(s["pasta"], s["uid"])))
        except Exception as _e:
            _velhos = []
            if log:
                log("nao consegui listar a entrega anterior (%s)" % str(_e)[:100])

        hnl_da_vez = {}
        if _mot.get("hnlnl") and _origem != _md.MODO_FAST:
            try:
                _passo("niveis cervicais", rotulo)
                import radai_output as _ro_hnl
                hnl_da_vez = _ro_hnl.niveis_cervicais_da_serie(
                    ref, cruas, device=dev, log=log) or {}
            except Exception as e:
                hnl_da_vez = {}
                if log:
                    log("niveis cervicais nao rodaram nesta serie (%s) — os "
                        "outros conjuntos nao foram afetados" % str(e)[:140])

        extras_da_vez = None
        _motores_full = [c for c in _md.MOTORES_NO_FULL if _mot.get(c)
                         and (_origem != _md.MODO_FAST or c in
                              _md.motores_do_fast(_anat["regioes"], modalidade))]
        if _motores_full:
            try:
                _passo("encefalo em TC" if _origem == _md.MODO_FAST
                       else "motores do FULL", rotulo)
                import radai_motores_full as _rmf
                extras_da_vez = _rmf.motores_na_serie(
                    ref, cruas, _motores_full, device=dev, log=log,
                    modalidade=_mod_serie or "CT", python_exe=python_exe)
            except Exception as e:
                extras_da_vez = None
                if log:
                    log("motores do FULL nao rodaram nesta serie (%s) — os "
                        "outros conjuntos nao foram afetados" % str(e)[:140])
                try:
                    import radai_motores_full as _rmf
                    extras_da_vez = _rmf.falha_de_todos(
                        _motores_full, _rmf.FALHOU,
                        "%s: %s" % (type(e).__name__, str(e)[:140]))
                except Exception:
                    extras_da_vez = None

        if _substituir:
            try:
                _subst["lado"] = _afastar_o_done(marcadores, s["pasta"],
                                                 s["uid"], maquina)
            except Exception as _e_sub:
                raise RuntimeError(
                    "nao consegui tirar o marcador de conclusao anterior "
                    "(%s): a entrega anterior fica como estava"
                    % type(_e_sub).__name__)
        _pode, _entrega["reservada"], _porque = reservar_a_entrega(
            marcadores, s["pasta"], s["uid"], log)
        if not _pode:
            raise PrimeiraEntregaValeu(_porque)
        import radai_output
        sd = radai_output.Saida(
            engine, stage, s["pasta"], rs_name, tasks=tasks,
            versao="lote " + VERSAO_LOTE, suavizar_mm=suavizar_mm,
            log=log, grade=_grade, modalidade=_mod_serie)
        _passo("montando o STUDY_Fast" if _origem == _md.MODO_FAST
               else "montando o FULL e o STUDY", rotulo)
        _torax = torax_pedido(s)
        if _torax and log:
            log("protocolo Torax / Mama pedido nesta serie: a parede toracica "
                "sai pela escolha, sem esperar a anatomia (ainda exige a "
                "cavidade toracica)")
        _modo_da_saida = (_origem if _origem in _md.MODOS_DA_SERIE
                          else _md.MODO_AUTO)
        # GUARDA: o estudo 3D nunca chega ao TPS. O entregue e os conjuntos
        # ao lado recebem so as tasks da escolha RT; o mapa recebe tudo.
        _so_estudo = tasks_so_do_estudo(s)
        _hnl_so_estudo = niveis_so_do_estudo(s)
        cruas_ent = cruas_do_entregue(cruas, _so_estudo)
        if log and _so_estudo:
            log("estudo 3D: %s so no mapa de rotulos, fora do entregue"
                % ", ".join(_so_estudo))
        _pp_da_vez = protocolo_proprio_da_escolha(_esc)
        entrega = sd.full_e_oar(cruas_ent, volume_hu=_hu, cads=cads_da_vez,
                                cervicais=(None if _hnl_so_estudo
                                           else (hnl_da_vez or None)),
                                torax=_torax, modo=_modo_da_saida,
                                oar_fora=list(_esc["oar_fora"]) or None,
                                extras=extras_da_vez,
                                **({"protocolo": _pp_da_vez}
                                   if _pp_da_vez is not None else {})) or {}
        if isinstance(entrega.get("parcial"), dict):
            _parcial_da_entrega.update(entrega["parcial"])
        _passos_do_full = list(entrega.get("etapas") or [])
        _seg_full = entrega.get("segundos")
        _m_ent = getattr(sd, "meta_do_fast" if _modo_da_saida == _md.MODO_FAST
                         else "meta_do_full", None)
        _meta_da_entrega.clear()
        if isinstance(_m_ent, dict):
            _meta_da_entrega.update(_m_ent)
        if isinstance(entrega.get("decimacao"), dict):
            _meta_da_entrega["decimacao"] = dict(entrega["decimacao"])
        try:
            import radai_records as _rg_f
            import radai_motores_full as _rmf_f
            _faltou[:] = _rg_f.faltou_da_serie(
                _tasks_falharam, _meta_da_entrega.get("nao_sairam"),
                estruturas_da_task=engine.estruturas_da_task,
                saidas_da_construcao=engine.saidas_da_construcao,
                motores_falharam=_rmf_f.falhas_dos_extras(extras_da_vez),
                estruturas_do_motor=_rmf_f.estruturas_do_motor)
            if _faltou and log:
                log(_rg_f.linha_do_parcial(rotulo, _faltou))
        except Exception as _e_f:
            if log:
                log("nao consegui montar o que faltou nesta serie (%s)"
                    % type(_e_f).__name__)
        del _oar_fora_valeu[:]
        _oar_fora_valeu.extend(entrega.get("oar_fora") or [])
        if "oar_fora_por_regiao" in entrega:
            _fora_por_regiao[0] = dict(entrega.get("oar_fora_por_regiao")
                                       or {})
        nomes = dict((i, n) for i, n in
                     enumerate(entrega.get("estruturas") or []))
        res["estruturas"] = len(nomes)
        rs_entregue = (os.path.basename(str(entrega.get("entregue") or u""))
                       or rs_name)
        res["rs"] = rs_entregue

        if _origem == _md.MODO_PERSO:
            if ts_cru_pedido(s):
                _passo("gravando o TotalSegmentator cru", rotulo)
                sd.totalsegmentator_cru(cruas_ent)
            _passo("gravando os plugins pedidos", rotulo)
            sd.plugins(cruas_ent)
            if _mot.get("nv"):
                _passo("NV-Segment-CT (comparacao)", rotulo)
                nv_da_vez = _rodar_nv(s, stage, ref, masks, python_exe,
                                      timeout_task_s, res, log,
                                      rs_name=rs_name)
                if nv_da_vez is not None and len(nv_da_vez):
                    sd.nv(nv_da_vez)
            if _mot.get("cads"):
                if not _cads_antes:
                    cads_da_vez = _rodar_cads()
                if cads_da_vez:
                    sd.cads(cads_da_vez)
            if hnl_da_vez and not _hnl_so_estudo:
                try:
                    sd.niveis_cervicais(hnl_da_vez)
                except Exception as e:
                    if log:
                        log("nao consegui gravar os niveis cervicais (%s) — "
                            "os outros conjuntos nao foram afetados"
                            % str(e)[:140])
            if _mot.get("mse"):
                try:
                    import radai_moose_engine as MM
                    _passo("MOOSE (camaras cardiacas e composicao corporal)",
                           rotulo)
                    mse_da_vez = MM.contornar(
                        stage, python_exe=python_exe,
                        dispositivo=engine._resolve_device(device),
                        timeout_s=timeout_task_s, log=log) or {}
                    if mse_da_vez:
                        sd.moose(mse_da_vez)
                except Exception as e:
                    if log:
                        log("MOOSE nao rodou nesta serie (%s) — os outros "
                            "conjuntos nao foram afetados" % str(e)[:120])
            if _esc["protocolos_3d"]:
                _passo("gravando o mapa de rotulos do estudo 3D", rotulo)
                try:
                    _para_mapa = dict(cruas)
                    if hnl_da_vez:
                        _para_mapa[CHAVE_DOS_NIVEIS] = hnl_da_vez
                    _mapa = sd.mapa_de_rotulos(
                        _para_mapa, s["uid"], pasta_serie=s["pasta"],
                        protocolos=list(_esc["protocolos_3d"]),
                        achados=list(achados_))
                    res["rotulos"] = os.path.basename(str(_mapa or u""))
                except Exception as e:
                    if log:
                        log("nao consegui gravar o mapa de rotulos do estudo "
                            "3D (%s: %s) — o entregue nao foi afetado"
                            % (type(e).__name__, str(e)[:140]))
        if _origem != _md.MODO_FAST:
            sd.pelvicos(masks)
        if log:
            log(radai_output.relatorio(sd.gravados))
        res["conjuntos"] = list(sd.gravados or [])
        # GUARDA: marcador de pronta so com RTSTRUCT conferido no disco.
        exigir_rtstruct_no_disco(sd, u"%s" % (_parcial_da_entrega.get("motivo")
                                              or u""))
        _subst["entregou"] = True

        try:
            import radai_sets as _rc
            _novos = set()
            for _c in (sd.gravados or []):
                _reg = _rc.POR_COD.get(_c)
                if _reg is not None:
                    _novos.add(os.path.basename(sd._alvo(_reg["infixo"])))
            _sobras = [v for v in _velhos if v not in _novos]
            for _v in _sobras:
                try:
                    os.remove(os.path.join(s["pasta"], _v))
                except Exception as _e:
                    if log:
                        log("nao consegui apagar %s (%s) — ele fica ao lado "
                            "da entrega nova" % (_v, str(_e)[:80]))
            if log and (_velhos or _sobras):
                log("substituindo: %d arquivo(s) RadAI da execucao anterior "
                    "reescritos, %d apagados por nao terem sido produzidos "
                    "agora%s" % (len(_velhos) - len(_sobras), len(_sobras),
                                 (" (%s)" % ", ".join(_sobras[:4]))
                                 if _sobras else ""))
        except Exception as _e:
            if log:
                log("nao consegui limpar a entrega anterior (%s)" % str(_e)[:100])

        res["tx"] = ""

        _campos_done = None
        try:
            import radai_records as _rg_done
            import radai_output as _ro_done
            _pai_done = (_ro_done.PAI_DO_FAST
                         if _modo_da_saida == _md.MODO_FAST
                         else _ro_done.PAI_DOS_PASSOS)
            _campos_done = _rg_done.campos_do_done(
                modalidade=modalidade, tasks_da_serie=tasks,
                plano=_do_job.get("plano"), dispositivo=dev,
                gravados=getattr(sd, "gravados", None),
                travamentos=_travamentos, regioes=_anat.get("regioes"),
                protocolos=(list(_esc["protocolos"])
                            + list(_esc["protocolos_3d"])),
                tasks_sem_estrutura=_sem_estrutura, faltou=_faltou,
                tasks_do_cache=_do_cache,
                receita_pos=getattr(engine, "VERSAO_DA_RECEITA_POS", u""),
                cache_das_tasks=_chaves_do_cache,
                motores_fora_do_ts=_rg_done.motores_que_desenharam(
                    hnl_da_vez, extras_da_vez),
                etapas=list(_etapas_ts) + [{
                    "etapa": _pai_done,
                    "segundos": float(_seg_full or 0.0),
                    "maquina": maquina or _maquina_desta_estacao(),
                    "dispositivo": "cpu"}])
        except Exception as _e_cd:
            if log:
                log("o `done` desta serie sai sem os campos do vigia (%s)"
                    % type(_e_cd).__name__)
        if _campos_done is not None:
            if _pul_mem:
                _campos_done["tasks_puladas_por_memoria"] = [
                    dict(f) for f in _pul_mem]
            if _parcial_da_entrega:
                _campos_done["parcial"] = {
                    "conjunto": u"%s" % (_parcial_da_entrega.get("conjunto")
                                         or u""),
                    "motivo": _sem_caminho_nem_uid(u"%s" % (
                        _parcial_da_entrega.get("motivo") or u""))[:240]}
        _marcar_done(s, marcadores, maquina, rs_entregue,
                     sorted(nomes.values()),
                     len(arquivos), tasks, int(time.time() - t0), log,
                     tasks_ok=_tasks_ok, tasks_falharam=_tasks_falharam,
                     modo=(_origem if _origem in _md.MODOS_DA_SERIE
                           else _md.MODO_AUTO), campos=_campos_done)
        if _tasks_falharam:
            res["tasks_falharam"] = [dict(f) for f in _tasks_falharam]
        if _faltou:
            res["faltou"] = [dict(f) for f in _faltou]
        if _pul_mem:
            res["tasks_puladas_por_memoria"] = [dict(f) for f in _pul_mem]
        if _parcial_da_entrega:
            res["parcial"] = dict(_parcial_da_entrega)
        if _sem_estrutura:
            res["tasks_sem_estrutura"] = [dict(f) for f in _sem_estrutura]
        with _entrega_trava:
            if _entrega["reservada"]:
                _soltar_a_entrega(marcadores, s["pasta"], s["uid"])
                _entrega["reservada"] = False
        try:
            import radai_archive
            radai_archive.registrar_serie(
                uid=s["uid"], pasta=s["pasta"], rs=rs_entregue,
                date=s.get("date", ""),
                pid=s.get("pid", ""), estruturas=len(nomes),
                secs=int(time.time() - t0), maquina=maquina, ver="lote " + VERSAO_LOTE)
        except Exception as e:
            if log:
                log("nao anotei %s no acervo (%s) — o RTSTRUCT esta gravado" % (rotulo, e))
        if log:
            log("OK %s -> %s (%d estruturas)%s"
                % (rotulo, rs_entregue, len(nomes),
                   (" | SEM a task: %s" % ", ".join(
                       f.get("task", "?") for f in _tasks_falharam))
                   if _tasks_falharam else ""))
        _notificar_a_serie("ok", s, log,
                           gravados=getattr(sd, "gravados", None))
    except (_arq_serie.TemporarioCurto, _arq_serie.DestinoSemEscrita) as e:
        res["erro"] = str(e)[:250]
        if log:
            log("ADIADA %s: %s" % (rotulo, res["erro"]))
        _notificar_a_serie("falhou_lote", s, log)
    except PrimeiraEntregaValeu as e:
        res["pulada"] = "a primeira entrega vale: %s" % str(e)[:200]
        try:
            _feita = bool(marcadores["has_marker"](s["pasta"], s["uid"],
                                                   "done"))
        except Exception:
            _feita = False
        res["pulo"] = "concluida" if _feita else "outra"
        if not _feita:
            res["dono"] = _dono_da_entrega(s, marcadores, str(e), maquina)
        if log:
            log("DESCARTADA %s: %s -- nada foi gravado, e nao conta como "
                "falha" % (rotulo, str(e)[:200]))
    except Exception as e:
        if type(e).__name__ == "Cancelado":
            res["cancelado"] = True
            if log:
                log("INTERROMPIDO %s: %s" % (rotulo, str(e)[:160]))
        else:
            res["erro"] = _motivo_do_erro(e)[:250]
            try:
                import radai_falhas as _fa
                res["classe"] = _fa.classificar_falha(e)
                res["assinatura"] = _fa.assinatura_da_falha(e, res["classe"])
                res["tipo_da_falha"] = _fa.causa_da_falha(e)[0]
                if res["classe"] == _fa.INELEGIVEL:
                    _mot = getattr(e, "motivo", None) or res["erro"]
                    res["nao_contornavel"] = _sem_caminho_nem_uid(
                        getattr(e, "tela", None) or _mot)[:200]
                    res["erro"] = (u"Não contornável: %s"
                                   % _sem_caminho_nem_uid(_mot))[:250]
            except Exception:
                pass
            if log:
                log("FALHOU %s: %s%s" % (rotulo, res["erro"],
                                         (" | %s, assinatura %s"
                                          % (res.get("classe"),
                                             res.get("assinatura")))
                                         if res.get("assinatura") else ""))
            _notificar_a_serie("falhou_lote", s, log)
    finally:
        parar_hb.set()
        if _hb is not None:
            try:
                _hb.join(timeout=30.0)
            except Exception:
                pass
        res["segundos"] = round(time.time() - t0, 1)
        if stage:
            shutil.rmtree(stage, ignore_errors=True)
        _fechar_cronometro()
        _tmp_serie.fechar()
        _devolver_o_done(marcadores, s["pasta"], s["uid"], _subst["lado"],
                         _subst["entregou"], log)
        if _entrega["reservada"]:
            _soltar_a_entrega(marcadores, s["pasta"], s["uid"])
            _entrega["reservada"] = False
        if tenho_lock:
            try:
                marcadores["unclaim"](s["pasta"], s["uid"])
            except Exception:
                pass
        _fechar_log_e_caso_do_lote(res)
        try:
            import radai_records
            _linhas = list(_coletor.linhas) if _coletor is not None else []
            _pedido = recorte_no_corpo_da_estacao()
            if _pedido is None:
                _pedido = getattr(engine, "RECORTE_NO_CORPO_PADRAO", None)
            _execucao = {
                "origem": "rodar agora",
                "modalidade": (str(s.get("modalidade") or "").upper()
                               or None),
                "escolha_da_serie": _escolha_da_serie,
                "dispositivo_pedido": str(device or "auto"),
                "dispositivo": dev,
            }
            _execucao.update(radai_records.execucao_do_motor(
                _do_job, recorte_pedido=_pedido))
            _execucao.update({
                "fallbacks": radai_records.achar_fallbacks(_linhas),
                "tasks_pedidas": list(tasks or []),
                "tasks_rodadas": list(_tasks_ok),
                "tasks_falharam": [dict(f) for f in _tasks_falharam],
            })
            import radai_output as _ro_caso
            _etapas_do_caso = _ro_caso.etapas_do_caso(
                list(_etapas_ts), _passos_do_full, segundos=_seg_full) + [
                    {"etapa": "serie inteira",
                     "segundos": res.get("segundos")}]
            _proc = None
            try:
                _proc = processamento_do_caso(
                    _esc, _origem, tasks=(_tasks_ok or tasks or ()),
                    travamentos=_travamentos, recortes=_recortes,
                    meta_entrega=_meta_da_entrega, oar_fora=_oar_fora_valeu,
                    niveis=_niveis, do_job=_do_job, log_motor=_log_motor,
                    dispositivo=dev, oar_fora_por_regiao=_fora_por_regiao[0])
            except Exception as _e_pr:
                if log:
                    log("registro de casos: o processamento nao entrou no "
                        "caso (%s)" % type(_e_pr).__name__)
            radai_records.registrar_serie(
                uid=s.get("uid", ""),
                identificadores=(s.get("pid", ""), s.get("uid", ""),
                                 s.get("nome", ""), s.get("nascimento", "")),
                so_trocar=_pastas_para_trocar(s),
                serie=radai_records.medir_serie(s, dict(res, **_medidas),
                                                origem=u"rodar agora"),
                resultado={"ok": not res.get("erro"),
                           "erro": res.get("erro", ""),
                           "cancelado": bool(res.get("cancelado")),
                           "estruturas": res.get("estruturas"),
                           "v3d": res.get("v3d"),
                           "conjuntos": res.get("conjuntos"),
                           "pulada": res.get("pulada", ""),
                           **radai_records.resultado_do_campo({
                               "faltou": _faltou,
                               "tasks_sem_estrutura": _sem_estrutura,
                               "regioes": _anat.get("regioes"),
                               "tasks_do_cache": _do_cache,
                               "classe": res.get("classe"),
                               "assinatura": res.get("assinatura"),
                               "tipo_da_falha": res.get("tipo_da_falha")})},
                etapas=_etapas_do_caso,
                execucao=_execucao,
                processamento=_proc,
                coletor=_coletor,
                tasks=tuple(_tasks_ok or tasks or ()),
                segundos_totais=res.get("segundos"),
                log=(_coletor._log if _coletor else None))
        except Exception as e:
            if log:
                try:
                    log("registro de casos: nao consegui montar o caso desta "
                        "serie (%s) - o contorno nao foi afetado"
                        % type(e).__name__)
                except Exception:
                    pass
    return res


FRASE_SEM_RTSTRUCT_NO_DISCO = (
    u"nenhum RTSTRUCT RadAI desta serie esta gravado no disco%s: a serie NAO "
    u"e marcada pronta nem parcial, e conta como falha")


def rtstruct_no_disco(sd):
    import radai_sets as _rs_cf
    conferidos, faltam = [], []
    for cod in list(getattr(sd, "gravados", None) or ()):
        reg = _rs_cf.POR_COD.get(cod)
        if not reg:
            continue
        try:
            alvo = sd._alvo(reg["infixo"])
        except Exception:
            continue
        nome = os.path.basename(str(alvo))
        if not (nome.startswith(u"RS_RadAI_") and nome.lower().endswith(".dcm")):
            continue
        try:
            if os.path.getsize(alvo) > 0:
                with open(alvo, "rb") as f:
                    f.read(132)
                conferidos.append(cod)
                continue
        except OSError:
            pass
        faltam.append(cod)
    return conferidos, faltam


def exigir_rtstruct_no_disco(sd, motivo_do_parcial=u""):
    conferidos, faltam = rtstruct_no_disco(sd)
    if conferidos:
        return conferidos
    partes = []
    if faltam:
        partes.append(u"%d conjunto(s) anunciado(s) sem arquivo: %s"
                      % (len(faltam), u", ".join(faltam[:6])))
    if motivo_do_parcial:
        partes.append(u"a entrega disse: %s" % motivo_do_parcial[:160])
    raise RuntimeError(FRASE_SEM_RTSTRUCT_NO_DISCO
                       % ((u" (%s)" % u"; ".join(partes)) if partes else u""))


def _marcar_done(s, marcadores, maquina, rs_name, estruturas, cortes, tasks,
                 secs, log, tasks_ok=None, tasks_falharam=None, modo=None,
                 campos=None):
    import json
    try:
        done = {"uid": s["uid"], "date": s.get("date", ""), "pid": s.get("pid", ""),
                "machine": maquina, "origem": "rodar agora",
                "finished": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "secs": secs, "rs": rs_name, "tasks": list(tasks or []),
                "tasks_ok": list(tasks if tasks_ok is None else tasks_ok),
                "cortes": cortes,
                "structures": estruturas, "ver": "lote " + VERSAO_LOTE,
                "dry_run": False}
        if campos:
            done.update(dict(campos))
        if modo:
            done["modo"] = str(modo)
        if s.get("so_pos"):
            done["origem"] = "refeito_pos"
        import radai_records as _reg_done
        done["tasks_falharam"] = []
        for f in (tasks_falharam or []):
            done["tasks_falharam"].append({
                "task": str((f or {}).get("task") or u""),
                "erro": _reg_done.sem_caminhos(
                    str((f or {}).get("erro") or u""))[:300],
                "classe": str((f or {}).get("classe") or u"")})
        marcadores["m_path"](s["pasta"], s["uid"], "done", criar=True).write_text(
            json.dumps(done, ensure_ascii=False), encoding="utf-8")
        _tirar = marcadores.get("tirar_sem_rtstruct")
        if _tirar is not None:
            _tirar(s["pasta"], s["uid"])
    except Exception as e:
        if log:
            log("nao consegui marcar %s como concluida (%s): o vigia pode "
                "refazer esta serie de madrugada" % (s.get("curto", ""), e))


def _modalidade_lida_dos_cortes(arquivos, uid, teto=400):
    try:
        import pydicom
    except Exception:
        return ""
    for fp in list(arquivos or ())[:teto]:
        try:
            ds = pydicom.dcmread(fp, stop_before_pixels=True, force=True,
                                 specific_tags=["SeriesInstanceUID", "Modality"])
        except Exception:
            continue
        if str(getattr(ds, "SeriesInstanceUID", "")) == uid:
            m = str(getattr(ds, "Modality", "") or "").upper()
            if m:
                return m
    return ""


def _so_da_serie(arquivos, uid, modalidade="CT"):
    import pydicom
    alvo = str(modalidade or "CT").upper()
    fora = []
    for fp in arquivos:
        try:
            ds = pydicom.dcmread(fp, stop_before_pixels=True, force=True,
                                 specific_tags=["SeriesInstanceUID", "Modality"])
            if (str(getattr(ds, "Modality", "")).upper() == alvo
                    and str(getattr(ds, "SeriesInstanceUID", "")) == uid):
                fora.append(fp)
        except Exception:
            pass
    return fora


def _rodar_nv(s, stage, ref, masks, python_exe, timeout_s, res, log,
                 rs_name=""):
    try:
        import radai_compare
        import radai_geom
        forma = tuple(int(v) for v in reversed(ref.GetSize()))
        grade = radai_geom.Grade.de_sitk(ref)
        nv, r = radai_compare.rodar_para_entrega(
            pasta_limpa=stage, forma=forma, grade=grade, uid=s["uid"],
            masks_nossas=masks, pasta_serie=s["pasta"], rs_nome=rs_name,
            python_exe=python_exe, log=log, timeout_s=timeout_s)
        if r.get("erro"):
            if log:
                log("VISTA-3D nao rodou (%s) — segue so com o nosso" % r["erro"])
            return None
        res["v3d"] = r.get("classes", 0)
        return nv if len(nv) else None
    except Exception as e:
        if log:
            log("VISTA-3D falhou (%s) — segue so com o nosso" % str(e)[:150])
        return None


def conferir_pasta_sem_gravar(caminho):
    r = {"vazio": False, "existe": False, "leitura": False, "erro": u"",
         "codigo": u""}
    c = (u"%s" % (caminho or u"")).strip().strip('"')
    if not c:
        r["vazio"] = True
        return r
    try:
        if not os.path.isdir(c):
            r["erro"] = u"A pasta não existe ou não está acessível desta máquina."
            r["codigo"] = u"nao_existe"
            return r
        r["existe"] = True
        with os.scandir(c) as it:
            next(iter(it), None)
        r["leitura"] = True
    except Exception as e:
        r["erro"] = u"Não consegui ler a pasta (%s)." % type(e).__name__
        r["codigo"] = u"sem_leitura"
    return r


def _abrir_ct(pasta, uid):
    import SimpleITK as sitk
    import numpy as np
    import engine
    todos = [os.path.join(pasta, f) for f in sorted(os.listdir(pasta))
             if os.path.isfile(os.path.join(pasta, f))]
    arquivos = _so_da_serie(todos, uid,
                            _modalidade_lida_dos_cortes(todos, uid) or "CT")
    if len(arquivos) < 3:
        raise ValueError("nao achei cortes da serie em %s" % pasta)
    stage = tempfile.mkdtemp(prefix="radai_prev_")
    try:
        engine.copy_sorted(arquivos, stage)
        img = engine.load_sitk(stage)
        a = sitk.GetArrayFromImage(img)
        if a.dtype != np.int16 and a.size and (a.max() > 32767
                                               or a.min() < -32768):
            a = np.clip(a, -32768, 32767)
        return a.astype(np.int16, copy=False), img
    finally:
        shutil.rmtree(stage, ignore_errors=True)


PAGINA = u"""<!doctype html><html><head><meta charset="utf-8">
<title>Rodar agora · Radioterapia.AI</title><style>
:root{--bg-0:var(--bg-0,#060d1a);--bg-1:var(--bg-1,#0a1120);--panel:var(--panel,#0c1322);--panel-2:var(--panel-2,#0f1729);--line:var(--line,#1e293b);
--line-strong:var(--line-strong,#2a3a55);--text:var(--text,#e6edf7);--text-muted:var(--text-muted,#a3b1c6);--text-dim:var(--text-dim,#72829b);
--accent:var(--accent,#4DA3FF);--accent-soft:rgba(77,163,255,.10);--accent-line:rgba(77,163,255,.35);
--success:#5BC57F;--warn:#E1B23B;--error:var(--perigo,#E96A5C);--r-md:10px;--r-xl:18px;
--font-display:'Inter',system-ui,'Segoe UI',Arial,sans-serif;
--font-mono:'JetBrains Mono',ui-monospace,Consolas,monospace}
*{box-sizing:border-box}
.sit-parcial{display:inline-block;margin-left:4px;padding:0 5px;border:1px solid var(--warn);
 border-radius:4px;color:var(--warn);font-size:10.5px;line-height:1.5;cursor:help}
html,body{background:var(--bg-0);color:var(--text);font-family:var(--font-display);margin:0}
.wrap{max-width:1320px;margin:0 auto;padding-bottom:30px}
 .col-pipe{max-height:none;overflow:visible}
}
.rt-topbar{display:flex;align-items:center;justify-content:space-between;padding:16px 28px;
border-bottom:1px solid var(--line);background:var(--bg-1)}
.rt-logo{font-size:15px;font-weight:700}.rt-logo .ai{color:var(--accent)}
a.rt-gear{text-decoration:none;color:var(--text-muted);background:var(--panel);
border:1px solid var(--line);border-radius:var(--r-md);padding:7px 12px;font-size:12px}
a.rt-gear:hover{color:var(--text);border-color:var(--accent-line)}
h1{font-size:26px;margin:24px 28px 4px;font-weight:800;letter-spacing:-0.02em}
.sub{color:var(--text-muted);font-size:13px;margin:0 28px 14px;line-height:1.55}
.sub b{color:var(--text)}
.cx{background:var(--panel);border:1px solid var(--line);border-radius:var(--r-xl);
padding:20px;margin:0 28px 14px}
.cx h2{font-size:12px;margin:0 0 10px;color:var(--accent);text-transform:uppercase;
letter-spacing:.5px;font-family:var(--font-mono)}

.tab-rola{overflow-x:auto;-webkit-overflow-scrolling:touch}

.ov-frota-aviso{margin:14px 0 0;font-size:12px;line-height:1.55;
 color:var(--text-dim,#72829b)}
.ov-frota-aviso[hidden]{display:none}
.ov-frota:empty{display:none}
.ov-form .rc-fronteira{margin-top:16px}

.ov-frota{display:flex;gap:8px;flex-wrap:wrap;margin:10px 0 0}
.ov-frota.so-eu{display:block;font-size:12px;line-height:1.5;
 color:var(--text-dim,#72829b);padding:9px 11px;border-radius:var(--r-md,6px);
 background:var(--panel-2,#0f1729);border:1px solid var(--line,#1e293b)}
.ov-chip{display:inline-flex;align-items:baseline;gap:5px;padding:5px 10px;
 border-radius:99px;background:var(--panel-2,#0f1729);
 border:1px solid var(--line,#1e293b);font-size:11.5px;
 color:var(--text-dim,#72829b)}
.ov-chip b{color:var(--text,#e6edf7);font:600 13px/1 var(--font-display,inherit);
 font-variant-numeric:tabular-nums}
.ov-form button{margin:0}
.ov-campo{margin:14px 0 0}
.ov-rot{display:block;margin:0 0 6px;font:600 10.5px/1.3 var(--font-mono);
 letter-spacing:.5px;text-transform:uppercase;color:var(--text-dim)}
.ov-root{display:flex;gap:8px;align-items:stretch}
.ov-root input{flex:1 1 auto;min-width:0}
#ov_roots{display:flex;flex-direction:column;gap:8px}
#ov_interromper[hidden]{display:none}
.lt-num{display:inline-block;font-variant-numeric:tabular-nums}
.lt-num.nova{animation:lt-num-entra .18s ease-out}
@keyframes lt-num-entra{from{opacity:0;transform:translateY(4px) scale(.92)}to{opacity:1;transform:none}}
@media(prefers-reduced-motion:reduce){.lt-num.nova{animation:none}}
.ov-laudo{margin:6px 0 0;min-height:16px;font-size:11.5px;line-height:1.45;
 color:var(--text-dim)}
.ov-laudo.ok{color:var(--success)}
.ov-laudo.ruim{color:var(--error)}
.ov-laudo.aviso{color:var(--warn)}
.ov-dois{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:16px}
.ov-seg{display:inline-flex;border:1px solid var(--line-strong);
 border-radius:var(--r-md);overflow:hidden}
.ov-seg button{border:0;border-radius:0;padding:7px 12px;font-size:12px;
 font-weight:600;background:var(--panel-2);color:var(--text-muted);cursor:pointer}
.ov-seg button + button{border-left:1px solid var(--line-strong)}
.ov-seg button[aria-checked="true"]{background:var(--accent-soft);
 color:var(--text);box-shadow:inset 0 -2px 0 var(--accent)}
.ov-seg button:focus-visible{outline:2px solid var(--accent);outline-offset:-2px}
.ov-num{display:inline-flex;align-items:stretch}
.ov-num button{width:34px;padding:0;font-size:15px;line-height:1}
.ov-num button:first-child{border-radius:var(--r-md) 0 0 var(--r-md)}
.ov-num button:last-child{border-radius:0 var(--r-md) var(--r-md) 0}
.ov-num input{width:76px;text-align:center;border-radius:0;
 border-left:0;border-right:0}
.ov-dica{display:block;margin:6px 0 0;font-size:11px;color:var(--text-dim)}
.ov-aviso{margin:14px 0 2px;padding:9px 11px;border-radius:var(--r-md);
 border:1px solid var(--borda-aviso,#4a3a18);background:var(--fundo-aviso,#1c1608);
 color:var(--aviso,#E8A33D);font-size:12px;line-height:1.5}
.ov-aviso[hidden]{display:none}
@media (max-width:520px){.ov-dois{grid-template-columns:minmax(0,1fr)}}
.rc-cards{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;
 margin:0 28px 16px}
@media (max-width:900px){.rc-cards{grid-template-columns:1fr}}
.rc-card{display:flex;align-items:flex-start;gap:12px;padding:14px 16px;
 background:var(--panel);border:1px solid var(--line);border-radius:var(--r-xl)}
.rc-card{text-decoration:none;color:inherit}
.rc-card.acao{cursor:pointer;transition:border-color .16s ease,
 background .16s ease,transform .16s ease}
.rc-card.acao:hover{border-color:var(--accent-line);background:var(--panel-2);
 transform:translateY(-1px)}
.rc-card.acao:active{transform:none}
.rc-card.acao:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.rc-card-ic{flex:0 0 auto;width:30px;height:30px;display:grid;place-items:center;
 border-radius:50%;background:var(--accent-soft);color:var(--accent);font-size:15px}
.rc-card-tx{min-width:0}
.rc-card-tx b{display:block;font-size:13px;margin:0 0 3px}
.rc-card-tx .tec2{display:block;font-size:11.5px;line-height:1.45;
 color:var(--text-dim)}
.rc-card.ligado{border-color:var(--accent);background:var(--accent-soft)}
.rc-card.ligado .rc-card-ic{background:var(--accent);color:var(--bg-0)}

.lt-filtro{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin:10px 0 0}
#lt_ler[hidden],#lt_form[hidden]{display:none}
.lt-ler-bts{display:flex;justify-content:center;gap:8px;margin:12px 0 0}
.lt-dica{margin:10px 0 0;text-align:center;font-size:12px;color:var(--text-dim)}
#lt_ler.feito .lt-dica,#lt_ler.feito .lt-ler-bts{visibility:hidden}
.lt-ler-bts button{margin:0}
.lt-fora{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin:8px 0 0;
 font-size:12.5px;color:var(--text-muted)}
.lt-fora:empty{display:none}
.lt-fora button{margin:0}

.cart-cx{display:flex;align-items:center;gap:10px;margin:14px 0 0;
 padding:10px 12px;border-radius:var(--r-md);font-size:12.5px;
 background:var(--accent-soft);border:1px solid var(--accent-line);
 color:var(--text-muted);flex-wrap:wrap}
.cart-cx b{color:var(--text)}
.cart-ic{color:var(--accent);flex:0 0 auto;display:grid;place-items:center;
 width:30px;height:30px;border-radius:var(--r-md);background:var(--accent-fraco)}
.cart-cx #cartxt{flex:1 1 220px;min-width:0}
.cart-acoes{display:flex;align-items:center;gap:6px;margin-left:auto;
 flex:0 0 auto;flex-wrap:wrap;justify-content:flex-end}
.cart-acoes button{margin:0}
#cartmsg{flex:1 0 100%;min-height:0}
#cartmsg:empty{display:none}
@media (max-width:640px){.cart-acoes{flex:1 1 100%;justify-content:stretch}
 .cart-acoes button{flex:1 1 auto}}
.cart-lista{margin:8px 0 0;max-height:210px;overflow-y:auto;
 border:1px solid var(--line);border-radius:var(--r-md);background:var(--panel-2)}
.cart-l{display:flex;align-items:center;gap:10px;padding:6px 10px;
 border-bottom:1px solid var(--line);font-size:12px}
.cart-l:last-child{border-bottom:0}
.cart-l b{flex:0 0 auto;color:var(--text)}
.cart-l .tec2{flex:1 1 0;min-width:0;overflow:hidden;text-overflow:ellipsis;
 white-space:nowrap}
.cart-l button{flex:0 0 auto}
label{display:block;font-size:11px;color:var(--text-dim);margin:10px 0 4px;
font-family:var(--font-mono);text-transform:uppercase;letter-spacing:.3px}
input,select{width:100%;box-sizing:border-box;background:var(--panel-2);color:var(--text);
border:1px solid var(--line);border-radius:var(--r-md);padding:9px 10px;font-size:13px;
font-family:var(--font-mono)}
input:focus,select:focus{outline:0;border-color:var(--accent)}
button{background:var(--panel-2);color:var(--text);border:1px solid var(--line-strong);
border-radius:var(--r-md);padding:10px 15px;font-size:13px;font-weight:600;cursor:pointer;
margin-right:6px;margin-top:10px}
button.pri{background:var(--ok);border-color:var(--ok);color:var(--ok-txt)}
button.pri:hover:not(:disabled){filter:brightness(1.08)}
button:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
button.perigo{background:transparent;border-color:rgba(233,106,92,.5);color:var(--error)}
button:disabled{background:transparent;border-style:dashed;color:var(--text-dim);cursor:default}
button.mini{padding:5px 10px;font-size:12px;margin:0}
table{width:100%;border-collapse:collapse;font-size:12px;margin-top:8px}
td.mod{white-space:nowrap;font-family:var(--font-mono);letter-spacing:.5px}
td.modo{white-space:nowrap;text-align:right;padding-right:10px !important}
.md-cx{position:relative;display:inline-flex;align-items:center;gap:7px;
 vertical-align:middle}
.md-cx button{margin:0}
.md-cx select{width:auto}
.md-cx .ui-seg>button{padding:5px 10px;font-size:11px;letter-spacing:.04em;
 font-weight:600}
.md-cx.md-off .ui-seg{filter:grayscale(1);opacity:.45}
.md-cx.md-off .ui-seg>button{cursor:not-allowed}
.md-aj{position:relative;flex:0 0 auto;width:20px;height:20px;padding:0;
 border-radius:50%;border:1px solid var(--line-strong);background:transparent;
 color:var(--text-dim);font:600 11px/1 var(--font-display);cursor:pointer;
 display:inline-grid;place-items:center;
 transition:color .16s ease,border-color .16s ease,background .16s ease}
.md-aj::after{content:'';position:absolute;inset:-4px}
.md-aj:hover,.md-aj:focus-visible,.md-aj[aria-expanded="true"]{
 color:var(--accent);border-color:var(--accent);background:var(--accent-soft);
 outline:0}
#md_balao{position:fixed;z-index:60;width:min(390px,calc(100vw - 32px));
 max-height:min(70vh,520px);overflow:auto;padding:13px 15px;
 border-radius:var(--r-md);border:1px solid var(--line-strong);
 background:var(--panel);color:var(--text-muted);font-size:12.5px;
 line-height:1.55;box-shadow:var(--sombra,0 18px 48px rgba(0,0,0,.5));
 white-space:normal;text-align:left}
#md_balao[hidden]{display:none}
#md_balao:focus{outline:0}
#md_balao .mb-tit{margin:0 0 9px;font:700 13px/1.3 var(--font-display);
 color:var(--text)}
#md_balao dl{margin:0}
#md_balao dt{font:700 10.5px/1.3 var(--font-mono);letter-spacing:.6px;
 color:var(--accent);margin:0 0 2px}
#md_balao dd{margin:0 0 10px}
#md_balao .mb-rodape{margin:2px 0 0;padding-top:9px;
 border-top:1px solid var(--line);color:var(--text-dim);font-size:11.5px}

tr.perso>td{background:var(--bg-1);padding:14px 16px 16px !important;
 white-space:normal;border-bottom:1px solid var(--line-strong)}
.p4{position:sticky;left:0;box-sizing:border-box;width:var(--p4-larg,100%);
 display:grid;gap:12px;
 grid-template-columns:minmax(0,.9fr) minmax(0,1.45fr) minmax(0,1fr) minmax(0,1.35fr)}
.p4 button{margin:0}
.p4-col{min-width:0;display:flex;flex-direction:column;
 background:var(--panel);border:1px solid var(--line);
 border-radius:var(--r-md);padding:12px 14px 13px}
.p4-col h4{display:flex;align-items:center;gap:8px;margin:0 0 9px;
 font:600 10.5px/1.3 var(--font-mono);letter-spacing:.6px;
 text-transform:uppercase;color:var(--accent)}
.p4-col h4 .p4-n{margin-left:auto;color:var(--text-dim);letter-spacing:0;
 font-weight:500;text-transform:none}
.p4-rola{max-height:400px;overflow-y:auto;margin-right:-8px;padding-right:8px}
.p4-ln{display:flex;align-items:center;flex-wrap:wrap;gap:4px 8px;
 min-height:30px;padding:3px 0}
.p4-grupo{margin:12px 0 3px;font:600 9.5px/1.3 var(--font-mono);
 letter-spacing:.5px;text-transform:uppercase;color:var(--text-dim)}
.p4-rola>.p4-grupo:first-child{margin-top:0}
.p4-grupo.achado{color:var(--warn)}
.p4-nota{margin:10px 0 0;padding-top:9px;border-top:1px dashed var(--line);
 font-size:11px;line-height:1.5;color:var(--text-dim)}
.p4-vazio{margin:0;font-size:11.5px;color:var(--text-dim)}
.p4-trava{order:3;flex:1 0 100%;padding-left:43px;margin-top:-4px;
 font-size:10.5px;line-height:1.3;color:var(--text-dim)}
.p4 label.sw{display:flex;align-items:center;gap:9px;flex:1 1 0;min-width:0;
 margin:0;cursor:pointer;font:500 12.5px/1.35 var(--font-display);
 color:var(--text);text-transform:none;letter-spacing:0}
.p4 label.sw input{position:absolute;opacity:0;width:1px;height:1px;
 margin:0;padding:0;border:0}
.p4 label.sw .tr{flex:none;position:relative;width:34px;height:19px;
 border-radius:10px;background:var(--panel-2);
 border:1px solid var(--line-strong);transition:background .16s,border-color .16s}
.p4 label.sw .tr::after{content:"";position:absolute;top:1px;left:1px;
 width:15px;height:15px;border-radius:50%;background:var(--text-muted);
 transition:transform .2s cubic-bezier(.22,1,.36,1),background .16s}
.p4 label.sw input:checked + .tr{background:var(--ok);border-color:var(--ok)}
.p4 label.sw input:checked + .tr::after{transform:translateX(15px);
 background:var(--ok-txt,#fff)}
.p4 label.sw input:focus-visible + .tr{outline:2px solid var(--accent);
 outline-offset:2px}
.p4 label.sw input:disabled + .tr{opacity:.5}
.p4 label.sw.travada{cursor:default;color:var(--text-dim)}
.p4 .sw-rot{min-width:0;overflow:hidden;white-space:normal;
 display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical}
.oar-tags{display:flex;flex-wrap:wrap;gap:9px 8px;padding:6px 6px 2px 0}
.oar-tag{position:relative;display:inline-flex;align-items:center;
 padding:3px 10px;border-radius:999px;font:500 11px/1.4 var(--font-mono);
 color:var(--success);background:var(--fundo-ok);border:1px solid var(--borda-ok)}
.oar-tag.fora{color:var(--text-dim);background:transparent;
 border-style:dashed;border-color:var(--line-strong)}
.oar-tag.fora .oar-nome{text-decoration:line-through}
.oar-cond{margin-left:6px;font:italic 400 10px/1.3 var(--font-display);
 color:var(--text-dim)}
.oar-var.sem{font-style:normal;font-weight:600;color:var(--text-muted)}
.oar-x,.oar-volta{position:absolute;top:-7px;right:-7px;width:16px;
 height:16px;padding:0;border-radius:50%;display:grid;place-items:center;
 font:700 10px/1 var(--font-display);cursor:pointer;
 background:var(--panel);color:var(--text-dim);border:1px solid var(--line-strong);
 transition:background .14s,color .14s,border-color .14s}
.oar-x::after,.oar-volta::after{content:'';position:absolute;inset:-5px}
.oar-x:hover,.oar-x:focus-visible{background:var(--perigo);border-color:var(--perigo);
 color:var(--ok-txt,#fff);outline:0}
.oar-volta:hover,.oar-volta:focus-visible{background:var(--ok);border-color:var(--ok);
 color:var(--ok-txt,#fff);outline:0}
.p4-ent-corpo{transition:opacity .16s ease}
.p4-ent-corpo.carregando{opacity:.55}
.ent-arqs{list-style:none;margin:0 0 10px;padding:0;display:flex;
 flex-direction:column;gap:5px}
.ent-arq{display:flex;flex-direction:column;gap:1px;padding:6px 9px;
 border-radius:var(--r-sm,5px);border:1px solid var(--line);
 background:var(--panel-2)}
.ent-arq.entregue{border-color:var(--ok);background:var(--fundo-ok)}
.ent-rot{font-size:12px;font-weight:600;color:var(--text)}
.ent-nome{font:400 10.5px/1.35 var(--font-mono);color:var(--text-dim);
 overflow-wrap:anywhere}
.ent-sub{margin:8px 0 2px;font-size:11px;color:var(--text-muted)}
.ent-sub b{color:var(--text);font-variant-numeric:tabular-nums}
.ent-nota{margin:10px 0 0;font-size:11px;line-height:1.45;color:var(--text-dim)}
.ent-erro{margin:0;font-size:12px;color:var(--error)}
.p4-rola.ent-rola{max-height:360px}
.sr{position:absolute;width:1px;height:1px;margin:-1px;padding:0;
 overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap;border:0}
@media (prefers-reduced-motion:reduce){
 .p4 label.sw .tr,.p4 label.sw .tr::after{transition:none}
}
@media (max-width:1180px){
 .p4{grid-template-columns:minmax(0,1fr) minmax(0,1fr)}
}
@media (max-width:640px){
 .p4{grid-template-columns:minmax(0,1fr)}
 tr.perso>td{padding:10px 8px 12px !important}
}
td,th{padding:6px 7px;border-bottom:1px solid var(--line);text-align:left}
th{color:var(--text-dim);font-size:10px;text-transform:uppercase;letter-spacing:.4px;
font-family:var(--font-mono)}
.linha{display:flex;gap:10px;align-items:flex-end;flex-wrap:wrap}
.linha>div{flex:1;min-width:220px}
#msg{font-size:12px;min-height:16px;margin-top:8px}
#lt_achou{margin:0 0 10px}
#lt_achou:empty{display:none}
#lt_achou .lt-conta{font-size:12.5px;color:var(--success,#5BC57F)}
.aviso{background:var(--panel-2);border:1px solid var(--accent-line);
border-radius:var(--r-md);padding:11px 13px;font-size:12px;color:var(--text-muted);
line-height:1.55;margin-top:10px}
.aviso b{color:var(--text)}
.aviso.clin{border-left-color:var(--warn,#E1B23B);margin-top:0;
 margin-bottom:12px}
.aviso.clin code{font-size:11.5px;color:var(--text-dim,#72829b)}
.mpr{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:12px;
margin-top:10px}
.mpr img{width:100%;image-rendering:pixelated;background:#000;border-radius:var(--r-md);
border:1px solid var(--line);display:block}
.mpr .rot{font-size:10px;font-weight:700;letter-spacing:.5px;color:var(--accent);
margin-bottom:4px;font-family:var(--font-mono)}
.mpr input[type=range]{width:100%;margin-top:6px}
.mpr .cnt{margin:2px 0 0}
.pin{display:inline-block;width:9px;height:9px;border-radius:2px;flex:0 0 auto}

.tec2{font-size:10.5px;font-family:var(--font-mono,monospace);color:var(--text-dim)}
td.acoes{text-align:right}
td.acoes .acoes-bts{display:inline-flex;flex-wrap:wrap;justify-content:flex-end;
 gap:5px;vertical-align:middle}
td.acoes .mini{margin:0;white-space:nowrap}
td.desc{width:210px;min-width:160px}
td.desc .desc-cx{width:0;min-width:100%}
td.desc .desc-t{display:-webkit-box;-webkit-box-orient:vertical;
 -webkit-line-clamp:2;line-clamp:2;overflow:hidden;overflow-wrap:anywhere}
td.desc .desc-l{display:block;white-space:nowrap;overflow:hidden;
 text-overflow:ellipsis;margin:0}
.mini.dentro{border-color:var(--borda-ok,#24422f);background:var(--fundo-ok,#0d1a12);color:var(--success,#5BC57F)}
tr.linhaon td{background:rgba(91,197,127,.05);--text-dim:var(--text-muted)}
.fora-nota{margin-top:8px;padding:8px 12px;border-radius:var(--r-md,6px);
 border:1px solid var(--line,#1e293b);background:var(--panel-2,#0f1729);
 color:var(--text-muted,#a3b1c6);font-size:12.5px;line-height:1.5}
.prev-cx{padding:10px 12px !important;background:var(--bg-0,#060d1a)}
.prev-cx .ue-caixa{max-width:min(640px,calc(100vw - 64px))}
.selo-achado{font-family:var(--font-mono,monospace);font-size:9.5px;
 letter-spacing:.6px;padding:2px 6px;border-radius:4px;
 border:1px solid rgba(225,178,59,.45);color:var(--warn,#E1B23B);
 background:rgba(225,178,59,.08);flex:0 0 auto}
.selo-vel{font-family:var(--font-mono,monospace);font-size:9.5px;
 letter-spacing:.4px;padding:2px 6px;border-radius:4px;flex:0 0 auto;
 white-space:nowrap;border:1px solid var(--line,#1e293b);
 color:var(--text-dim,#72829b)}
.selo-vel.fast{color:var(--success,#5BC57F);border-color:rgba(91,197,127,.38);
 background:rgba(91,197,127,.08)}
.selo-vel.slow{color:var(--warn,#E1B23B);border-color:rgba(225,178,59,.38);
 background:rgba(225,178,59,.08)}
.selo-vel.ultra-slow{color:var(--perigo,#E96A5C);
 border-color:rgba(233,106,92,.45);background:rgba(233,106,92,.08)}
.selo-vel.estimada{border-style:dashed;background:transparent}
.tk-aj{margin-left:auto;flex:0 0 auto;position:relative;
 width:18px;height:18px;padding:0;border-radius:50%;cursor:pointer;
 border:1px solid var(--line,#1e293b);background:transparent;
 color:var(--text-dim,#72829b);font-family:inherit;font-size:11px;
 line-height:1;display:flex;align-items:center;justify-content:center;
 transition:color .16s ease,border-color .16s ease,background .16s ease}
.tk-aj::after{content:'';position:absolute;top:-4px;left:-4px;
 right:-4px;bottom:-4px}
.tk-aj:hover,.tk-aj:focus-visible{color:var(--accent);
 border-color:var(--accent);background:rgba(125,176,255,.08)}
.tk-b{font-size:12px;line-height:1.5}
.tk-cod{font-family:var(--font-mono,monospace);font-size:10.5px;
 color:var(--text-dim,#72829b);margin:0 0 10px;
 padding-bottom:9px;border-bottom:1px solid var(--line,#1e293b)}
.tk-l{display:flex;gap:10px;align-items:baseline;margin:0 0 6px}
.tk-k{flex:1 1 auto;color:var(--text-dim,#72829b);min-width:0}
.tk-v{flex:0 0 auto;max-width:58%;text-align:right;color:var(--text,#e6edf7)}
.tk-avisos{margin:0 0 11px;padding:8px 10px;
 border-radius:var(--r-sm,5px);border:1px solid var(--borda-aviso,#4a3a18);
 background:var(--fundo-aviso,#1c1608);color:var(--aviso,#E8A33D);
 font-size:11.5px;line-height:1.45}
.tk-avisos>div{margin:0 0 3px}
.tk-avisos>div:last-child{margin-bottom:0}
.tk-sec{margin:10px 0 8px}
.tk-sec .tk-k{display:block;margin:0 0 5px}
.tk-est{display:flex;flex-wrap:wrap;gap:4px;max-height:132px;overflow:auto}
.tk-est span{font:400 10.5px/1.4 var(--font-mono,monospace);padding:1px 6px;
 border-radius:4px;border:1px solid var(--line,#1e293b);
 color:var(--text-muted,#a3b1c6);background:var(--panel-2,#0f1729)}
.tk-vazio{font-size:11.5px;color:var(--text-dim,#72829b)}
.tk-sep{margin:12px 0 7px;padding-top:9px;border-top:1px solid var(--line,#1e293b);
 font:600 9.5px/1.3 var(--font-mono,monospace);letter-spacing:.5px;
 text-transform:uppercase;color:var(--text-dim,#72829b)}
@media (max-width:420px){
 .tk-l{display:block;margin:0 0 9px}
 .tk-v{max-width:none;text-align:left;display:block}
}
@VISORCSS@

.wrap > .ui-fn{margin:28px 28px 22px}
.cam-rot{margin:2px 0 6px}
.cam-linha{align-items:center;flex-wrap:wrap;row-gap:4px}
.cam-linha > input{flex:1 1 260px;min-width:0;display:block}
.cam-linha button{margin:0;flex:0 0 auto;white-space:nowrap}
.rc-card-tx .tec2{font-family:var(--font-display);letter-spacing:0}
.ps-cab #cx2_n:not(:empty){margin-left:10px}
.rc-gancho{margin:44px 28px 0;line-height:1.7}
.rc-gancho .sep{margin:0 8px;color:var(--text-dim)}
td.serie{width:76px;padding-top:4px !important;padding-bottom:4px !important}
.mini-serie{display:block;width:64px;height:64px;padding:0;margin:0;
 border-radius:var(--r-md);border:1px solid var(--line-strong);background:#000;
 overflow:hidden;cursor:zoom-in;transition:border-color .16s ease,transform .16s ease}
.mini-serie img{display:block;width:100%;height:100%;object-fit:contain;
 user-select:none;-webkit-user-drag:none}
.mini-serie:hover{border-color:var(--accent);transform:translateY(-1px)}
.mini-serie:active{transform:none}
.mini-serie.sem{background:var(--panel-2);cursor:default}
.mini-serie.sem img{visibility:hidden}
.p4-col h4.p4-h3d{margin-top:16px;padding-top:12px;border-top:1px solid var(--line)}
.p4-rt3d{margin:8px 0 4px;padding:8px 10px;border-radius:var(--r-md);
 background:var(--panel-2);border:1px solid var(--line);font-size:12.5px;
 line-height:1.5;color:var(--text)}
.p4 select.p4-pp-sel{margin:4px 0 2px;font-size:12px}
.p4 select.p4-pp-sel:disabled{opacity:.55;cursor:not-allowed}
.p4-pp-nota{display:flex;align-items:baseline;gap:7px;margin:8px 0 2px;
 font-size:11.5px;line-height:1.45;color:var(--text-muted)}
.oar-tag.uniao{color:var(--text);background:var(--panel-2);
 border-color:var(--line-strong)}
#tab.p4-estreito .p4{grid-template-columns:minmax(0,1fr) minmax(0,1fr)}
@media (max-width:640px){#tab.p4-estreito .p4{grid-template-columns:minmax(0,1fr)}}
.tk-trava{margin:0 0 10px;padding:8px 10px;border-radius:var(--r-md);
 background:var(--panel-2);border:1px solid var(--line);font-size:12.5px;
 line-height:1.5;color:var(--text)}
@media (prefers-reduced-motion:reduce){.mini-serie{transition:none}}
</style></head><body><div class="wrap">
<header class="rc-topo"><a class="rc-marca" href="/" title="Radioterapia.AI Local"><span class="rc-nome">radioterapia<span class="g">.ai</span></span><span class="rc-sub" data-radai-frase>Local Suite</span></a><span class="rc-seta">&#8594;</span><span class="rc-tela">Rodar agora</span><div class="dir"><a class="rc-voltar" href="/">&#8592; Voltar ao menu</a></div></header>

@CABECA@

<div class="rc-cards">
 <div class="rc-card acao" id="cd_add" role="button" tabindex="0" onclick="novasSeries()">
  <div class="rc-card-ic">@ICO_MAIS@</div>
  <div class="rc-card-tx">
   <b data-radai-frase>Adicionar novas s&eacute;ries</b>
   <span class="tec2" data-radai-frase>Carregue imagens a partir de uma pasta
   e adicione &agrave; fila segmenta&ccedil;&otilde;es</span></div>
 </div>
 <div class="rc-card acao" id="cd_night" role="button" tabindex="0" onclick="folhaOvernight()">
  <div class="rc-card-ic">@ICO_LUA@</div>
  <div class="rc-card-tx">
   <b data-radai-frase>Incluir Overnight Run</b>
   <span id="cd_night_tx" class="tec2" data-radai-frase>Entra como
   &uacute;ltimo card da fila: quando ela chegar nele, a esta&ccedil;&atilde;o
   passa a varrer sozinha.</span></div>
 </div>
</div>
<button id="ov_interromper" type="button" class="ui-bt perigo" hidden
 onclick="ovInterromper()" data-radai-frase>Interromper Overnight Run</button>
@FOLHA_TURNO@

@ESCOLHA@

<div class="ps-cx fechado" id="cx2">
 <h2 class="ps-cab" data-cx="cx2"><span class="ps-num">2</span>
  <span id="cx2_tit" data-radai-frase>Séries encontradas</span><span class="ps-sub" id="cx2_n"></span>
  <span class="ui-ajuda" tabindex="0" aria-label="ajuda">?<span class="ui-balao"><p>A coordenação é a mesma do vigia: enquanto uma série processa, ela fica marcada como em processamento para todas as estações, e ao terminar fica concluída — o lote da madrugada não vai refazê-la.</p><p>Série travada por outra estação não pode ser selecionada aqui; série já concluída não vem marcada. Reprocessar <b>substitui</b>: os RTSTRUCT RadAI que estiverem na pasta são apagados e os novos entram no lugar — a tela pergunta antes. O exame, e contorno que outra pessoa tenha posto ali, não são tocados.</p></span></span><span class="ps-seta">&#9662;</span></h2>
 <div class="ps-corpo">
 <div id="lt_achou" role="status"></div>
 <div class="tab-rola"><table id="tab"></table></div>
 <div id="cartcx" class="cart-cx">
  <span class="cart-ic" aria-hidden="true">@ICO_CARRINHO@</span>
  <span id="cartxt"></span>
  <div class="cart-acoes">
   <button class="pri" id="btrodar" onclick="rodar()" data-radai-frase>Adicionar as selecionadas à fila</button>
   <button class="mini" id="cartsel" onclick="marcar(true)" data-radai-frase>Selecionar todas as séries</button>
   <button class="mini" id="cartesv" onclick="esvaziarSelecao()" data-radai-frase>Esvaziar seleção</button>
  </div>
  <span id="cartmsg" class="tec2" role="status"></span>
 </div>
 </div>
</div>


<div class="rc-nota rc-gancho">
 <b><span data-radai-frase>Terminou de processar?</span></b>
 <span data-radai-frase>Exercite o aprendizado em:</span>
 <a href="/ver">Ver segmenta&ccedil;&atilde;o</a><span class="sep" aria-hidden="true">&middot;</span><a href="/recon3d">Reconstru&ccedil;&otilde;es 3D</a>
</div>

@ALERTA@

<template id="fp_ico">@ICO_PASTA@</template>
<script>@VISORJS@</script>
<script>
var SERIES=[], INCL={};

var CARRINHO = {};
var VISTAS = {};

function chaveDe(s){
 if(!s) return '';
 return [s.pasta||'', s.uid||s.curto||'', (s.n==null?'':s.n)]
        .join(String.fromCharCode(1));
}
function noCarrinho(s){ return !!CARRINHO[chaveDe(s)] }
function porNoCarrinho(s, dentro){
 if(dentro && (s.carregando || s.b === null || s.bilhete === null)) return;
 var k = chaveDe(s); if(!k) return;
 if(dentro){
  if(!s._raiz) s._raiz = window.PASTA_VARRIDA || '';
  CARRINHO[k] = s;
  var e = escolhaDe(s);
  if(!e.modo) e.modo = MODO_DE_FABRICA;
 } else { delete CARRINHO[k] }
}
function carrinhoLista(){
 return Object.keys(CARRINHO).map(function(k){ return CARRINHO[k] });
}
function carrinhoRaizes(){
 var r = {}, n = 0;
 carrinhoLista().forEach(function(s){
   var v = s._raiz || s.pasta || ''; if(!r[v]){ r[v] = true; n++ } });
 return n;
}
function sincronizarIncl(){
 INCL = {};
 SERIES.forEach(function(s,i){ if(noCarrinho(s)) INCL[i] = true });
}
function perguntar(o){
 o = o || {};
 if(window.uiPainel) return window.uiPainel(o);
 var txt = [o.titulo, o.corpo].filter(Boolean).join(String.fromCharCode(10,10));
 var ok = confirm(txt);
 try{ if(ok && o.aoSim) o.aoSim(); else if(!ok && o.aoNao) o.aoNao(); }catch(e){}
 return null;
}

function limparSelecao(){
 CARRINHO = {}; sincronizarIncl(); pintarTabela();
}
// GUARDA: esvaziar tira so as series da lista a vista, sem pergunta; as de outras pastas e a fila ficam.
function esvaziarSelecao(){
 var desta = SERIES.filter(noCarrinho);
 if(!desta.length) return;
 desta.forEach(function(s){ porNoCarrinho(s, false) });
 sincronizarIncl(); pintarTabela();
}
function el(i){return document.getElementById(i)}

var LT_CHEGOU_COM_SERIES = false;
function ltEscolha(){
 var p = window.uiPopupSerie ? uiPopupSerie('cx1') : null;
 if(p) p.abrir(el('cd_add'));
 return p;
}
function novasSeries(){
 SERIES = []; window.CURTAS = []; window.PASTA_VARRIDA = '';
 SELECAO_DA_FICHA = false;
 try{ sessionStorage.removeItem('radai_lote_pasta') }catch(e){}
 var c = el('pasta'); if(c) c.value = FP_FAV || '';
 if(LT_VARRE && LT_VARRE.vivo()) LT_VARRE.parar(true);
 LT_LER = null; _ltModo(false); _ltFora(null, 0);
 _notaNoPopup('');
 _achouNaTela('', '');
 msg(FP_FAV ? 'pasta favorita preenchida — clique em «Varrer séries»' : '', true);
 sincronizarIncl(); pintarTabela(); _tituloDoPasso2(false);
 if(window.psFechar) psFechar('cx2');
 ltEscolha();
 try{ if(c) c.focus() }catch(e){}
}
var SELECAO_DA_FICHA = false;
function _tituloDoPasso2(daFicha){
 SELECAO_DA_FICHA = !!daFicha;
 var t = el('cx2_tit'), n = el('cx2_n');
 if(t) uiTexto(t, daFicha ? 'Séries selecionadas' : 'Séries encontradas');
 if(n) uiTexto(n, SERIES.length ? '%s série(s) nesta lista'.replace('%s', SERIES.length) : '');
 try{ if(window.radaiRetraduzir) window.radaiRetraduzir() }catch(e){}
}

function esqueleto(alvo, linhas){
 if(!alvo) return;
 var h = '';
 for(var i = 0; i < (linhas || 4); i++)
  h += '<div class="ui-esqueleto ui-esq-l"></div>';
 alvo.innerHTML = '<tr><td colspan="10">' + h + '</td></tr>';
}
function esc(s){return String(s==null?'':s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/"/g,'&quot;')}
function msg(t, ok){
 var m = el('msg'); if(!m) return;
 if(window.uiTexto) uiTexto(m, t); else m.textContent = t;
 m.style.color = ok ? 'var(--success,#5BC57F)' : 'var(--perigo,#E96A5C)';
}

function dataBr(d){
 d = (d==null?'':(''+d)).trim();
 var m = /^(\\d{4})(\\d{2})(\\d{2})/.exec(d);
 return m ? (m[3]+'/'+m[2]+'/'+m[1]) : d;
}
function horaBr(t){
 t = (t==null?'':(''+t)).trim();
 var m = /^(\\d{2})(\\d{2})/.exec(t);
 return m ? (m[1]+':'+m[2]) : '';
}

var LT_VARRE = null, LT_LER = null, LT_FECHOU_A_MAO = false;
var LT_CONFIRMACAO_MS = 900;
function _ltModo(lendo){
 var f = el('lt_form'), l = el('lt_ler'), b = el('lt_parar');
 if(f) f.hidden = !!lendo;
 if(l){ l.hidden = !lendo; l.classList.remove('feito') }
 if(b) b.disabled = false;
}
function _ltContas(d){
 var p = [uiMolde('%s pasta(s) olhada(s)', [d.pastas || 0]),
          uiMolde('%s arquivo(s) lido(s)', [d.arquivos || 0]),
          uiMolde('%s série(s) achada(s)', [d.series || 0])];
 if(d.fora_da_data)
  p.push(uiMolde('%s pasta(s) ficaram fora do filtro de data.', [d.fora_da_data]));
 return p;
}
var LT_CONTAGENS = {};
function _ltViva(s){
 var m = modalidadeDe(s);
 var chave = s.uid || s.curto || s.desc || '', n = s.cortes || 0;
 var mudou = LT_CONTAGENS[chave] !== n; LT_CONTAGENS[chave] = n;
 return '<span class="md">' + (m === 'MR' ? 'RM' : (m === 'CT' ? 'TC' : '—')) + '</span>'
  + '<span class="ds">' + esc(s.desc || '') + '</span>'
  + '<span class="nm"><span class="lt-num' + (mudou ? ' nova' : '') + '">' + esc(n)
  + '</span> <span data-radai-frase>cortes</span></span>'
  + '<span class="nm">' + esc(dataBr(s.date)) + '</span>';
}
function _ltFora(d, dias){
 var f = el('lt_fora'); if(!f) return;
 if(!(d && d.fora_da_data && dias)){ f.innerHTML = ''; return }
 uiHTML(f, '<span data-radai-frase>'
  + esc(uiMolde('%s pasta(s) ficaram fora do filtro de data.', [d.fora_da_data]))
  + '</span><button type="button" class="mini" onclick="ltTodasAsDatas()"'
  + ' data-radai-frase>Ler todas as datas</button>');
 try{ if(window.radaiRetraduzir) window.radaiRetraduzir() }catch(e){}
}
function ltTodasAsDatas(){
 if(window.uiDias) uiDias('lt_dias', 0);
 varrer();
}
function ltParar(){
 var b = el('lt_parar'); if(b) b.disabled = true;
 if(LT_VARRE && LT_VARRE.vivo()) LT_VARRE.parar();
}
function _ltAoFecharPopup(){
 if(LT_VARRE && LT_VARRE.vivo()){ LT_FECHOU_A_MAO = true; ltParar() }
}
var LT_ABERTURAS = 0;
function _ltAoAbrirPopup(){
 LT_ABERTURAS++;
 if(!(LT_VARRE && LT_VARRE.vivo())) _ltModo(false);
}

function varrer(o){
 o = o || {};
 LT_CONTAGENS = {};
 var p = el('pasta').value;
 if(!p){ msg('informe a pasta', false); uiTremer(el('pasta')); return }
 var dias = window.uiDias ? uiDias('lt_dias') : 7;
 msg('', true); _ltFora(null, 0); _notaNoPopup('');
 LT_FECHOU_A_MAO = false;
 esqueleto(el('tab'), 5);
 var ler = null;
 if(!o.quieto){
  ltEscolha();
  _ltModo(true);
  ler = uiLeitura('lt_ler_cx');
  ler.estados(['Lendo os cabeçalhos dos arquivos…', 'Procurando séries nas subpastas…']);
  ler.conta(_ltContas({}));
 }
 LT_LER = ler;
 LT_VARRE = uiVarrer({uso: 'lote', chave: 'lote', pasta: p, dias: dias,
  aoProgresso: function(d){
   if(!ler || LT_LER !== ler) return;
   if(d.etapa === 'fechando') ler.estados(['Conferindo as séries achadas…']);
   ler.conta(_ltContas(d));
  },
  aoParcial: function(linhas, d){
   if(ler && LT_LER === ler && !d.final) ler.series(linhas, _ltViva);
  },
  aoFim: function(linhas, d){ _ltFim(linhas, d, ler, dias, p, o) },
  aoErro: function(m){
   if(LT_LER !== ler) return;
   _ltModo(false); ltEscolha(); msg('ERRO: ' + m, false);
  }});
}
function _ltFim(linhas, d, ler, dias, p, o){
 if(LT_LER !== ler) return;
 d = d || {};
 var r = d.extra || {};
 window.CURTAS = r.curtas || []; window.PISO = r.piso || 20;
 var nota = _notaDasCurtas();
 var interrompida = !!d.parado;
 var series = d.final ? (linhas || []) : [];
 if(!series.length){
  SERIES = [];
  sincronizarIncl(); pintarTabela(); _tituloDoPasso2(false);
  if(window.psFechar) psFechar('cx2');
  _achouNaTela('', '');
  _ltModo(false);
  if(LT_FECHOU_A_MAO) return;
  ltEscolha();
  msg(interrompida ? 'A busca foi interrompida: a lista tem só o que foi achado até ali.'
                   : 'Nenhuma série nesta pasta.', false);
  _notaNoPopup(nota);
  _ltFora(d, dias);
  return;
 }
 SERIES = series;
 window.PASTA_VARRIDA = r.pasta || p;
 try{ sessionStorage.setItem('radai_lote_pasta', window.PASTA_VARRIDA); }
 catch(e){}
 if(!o.quieto) psAbrir('cx2', true);
 var umExame = !!r.um_exame;
 var molde = umExame
   ? '%s série(s) encontrada(s) — mesmo exame, reconstruído várias vezes'
   : '%s série(s) encontrada(s)';
 _achouNaTela(molde.replace('%s', SERIES.length), nota,
              interrompida ? 'A busca foi interrompida: a lista tem só o que foi achado até ali.' : '');
 _tituloDoPasso2(false);
 SERIES.forEach(function(s){
   var k = chaveDe(s);
   if(VISTAS[k]) return;
   VISTAS[k] = true;
   if(s.situacao!=='processando' && s.situacao!=='concluida'
      && !(s.situacao==='retomavel' && !s.minha)
      && (!umExame || s.sugerida)) porNoCarrinho(s, true)});
 SERIES.forEach(function(s){
   var k = chaveDe(s); if(!CARRINHO[k]) return;
   var ant = CARRINHO[k];
   s._raiz = ant._raiz || window.PASTA_VARRIDA || '';
   CARRINHO[k] = s});
 sincronizarIncl(); pintarTabela();
 var popup = window.uiPopupSerie ? uiPopupSerie('cx1') : null;
 function fechar(){ if(popup) popup.fechar(); _ltModo(false) }
 if(ler && !interrompida && popup && popup.aberto()){
  var cx = el('lt_ler'); if(cx) cx.classList.add('feito');
  var vez = LT_ABERTURAS;
  ler.pronto(molde.replace('%s', SERIES.length)).then(function(){
   // GUARDA: popup reaberto durante a confirmação é da pessoa; o fechamento automático não o leva.
   setTimeout(function(){ if(LT_LER === ler && LT_ABERTURAS === vez) fechar() }, LT_CONFIRMACAO_MS);
  });
 } else fechar();
}
function _notaDasCurtas(){
 if(!(window.CURTAS && CURTAS.length)) return '';
 return '<b>'+CURTAS.length+'</b> série(s) desta pasta não '
  +'aparecem na lista: elas têm menos de '+PISO+' cortes (a maior tem '
  +CURTAS[0]+'). São localizadores, capturas de tela e reconstruções '
  +'parciais — não exames.'
  +'<span class="ui-ajuda" tabindex="0" aria-label="ajuda">?'
  +'<span class="ui-balao"><p>O piso existe para a lista não encher de '
  +'coisa que não se contorna.</p><p>Se você espera uma série de verdade '
  +'aqui e ela não apareceu, o piso não é a causa: nenhum arquivo é '
  +'descartado por não ser lido.</p></span></span>';
}
function _notaNoPopup(h){
 var fora = el('fpFora'); if(!fora) return;
 fora.style.display = h ? '' : 'none';
 fora.innerHTML = h || '';
}
function _achouNaTela(t, nota, aviso){
 var r = el('lt_achou'); if(!r) return;
 r.innerHTML = '';
 if(t){
  var c = document.createElement('div'); c.className = 'lt-conta';
  if(window.uiTexto) uiTexto(c, t); else c.textContent = t;
  r.appendChild(c);
 }
 if(aviso){
  var a = document.createElement('div'); a.className = 'fora-nota';
  a.setAttribute('data-radai-frase', '');
  a.textContent = aviso; r.appendChild(a);
 }
 if(nota){
  var n = document.createElement('div'); n.className = 'fora-nota';
  n.innerHTML = nota; r.appendChild(n);
 }
}


function modalidadeDe(s){
 var m = String((s&&s.modalidade)||'').toUpperCase();
 return (m==='MR'||m==='MRI') ? 'MR' : (m==='CT' ? 'CT' : '');
}
function celulaModalidade(s){
 var m = modalidadeDe(s);
 if(m) return '<td class="mod">'+(m==='MR'?'RM':'TC')+'</td>';
 return '<td class="mod"><span title="o cabeçalho desta série não declarou a modalidade; o processamento vai seguir como TC">—</span></td>';
}

function cartMsg(h, ok){
 var m = el('cartmsg'); if(!m) return;
 uiHTML(m, h || '');
 m.style.color = ok ? 'var(--success,#5BC57F)' : 'var(--perigo,#E96A5C)';
}
function pintarCarrinho(){
 var L = carrinhoLista(), cx = el('cartcx');
 if(!cx) return;
 var r = carrinhoRaizes();
 if(cx.dataset.n !== String(L.length)){
  cx.dataset.n = String(L.length);
  cx.classList.remove('ui-brilho'); void cx.offsetWidth;
  cx.classList.add('ui-brilho');
 }
 if(!L.length){
  uiHTML(cx.querySelector('#cartxt'),
    '<span data-radai-frase>Nenhuma série no carrinho — selecione na tabela acima.</span>');
 } else {
  var _fr = (r > 1) ? '%s série(s) no carrinho, de %s pastas'
                    : '%s série(s) no carrinho';
  var _vs = (r > 1) ? [L.length, r] : [L.length];
  uiHTML(cx.querySelector('#cartxt'), '<span data-radai-frase>'
    + _fr.replace(/%s/g, function(){ return '<b>' + _vs.shift() + '</b>' })
    + '</span>');
 }
 var be = el('cartesv'), bs = el('cartsel'), bt = el('btrodar');
 if(be) be.disabled = !SERIES.some(noCarrinho);
 var livres = SERIES.filter(function(s){ return s.situacao !== 'processando' });
 if(bs) bs.disabled = !livres.length
   || livres.every(function(s){ return noCarrinho(s) });
}

function pintarTabela(){
 pintarCarrinho();
 _soltarSeletores();
 el('tab').innerHTML='<tr><th>Paciente</th><th>Data</th><th>Modalidade</th>'
  +'<th>Cortes</th>'
  +'<th>Corte</th><th>Descrição</th><th>Série</th><th>Situação</th>'
  +'<th>Ações</th><th>Modo</th></tr>'
  +gruposDeEstudo().map(function(g){
    return g.itens.map(linhaDaSerie).join('');
   }).join('');
 if(!SERIES.length){
  var txt;
  if((window.CURTAS||[]).length){
   txt = 'achei '+CURTAS.length+' série(s) nesta pasta, mas a maior tem '
       +CURTAS[0]+' corte(s) e o mínimo é '+PISO+'. '
       +'Abaixo disso entram localizador e captura de tela, e o modelo '
       +'devolve contorno para elas. Se você copiou só um arquivo de '
       +'exemplo, traga a série inteira; se o exame é curto mesmo, baixe '
       +'o mínimo de cortes em Configurações.';
  } else {
   txt = 'nenhuma série de imagem nesta pasta. '
       +'Se o exame veio empacotado, aponte a pasta onde o <code>.zip</code> '
       +'foi salvo — ele é lido sem precisar extrair.';
  }
  el('tab').innerHTML += '<tr><td colspan=10 style="color:var(--text-dim,#72829b)">'
   +txt+'</td></tr>';
 }
 _montarSeletores();
 _reporPaineis();
 _reporPrevias();
}

function estudoDe(s){
 return String((s && (s.estudo || s.dir || s.pasta)) || '');
}
function gruposDeEstudo(){
 var grupos = [], porChave = {};
 SERIES.forEach(function(s, i){
  var k = estudoDe(s);
  if(!porChave[k]){ porChave[k] = {chave:k, ref:s, itens:[]}; grupos.push(porChave[k]) }
  porChave[k].itens.push(i);
 });
 return grupos;
}

function linhaDaSerie(i){
   var s = SERIES[i];
   if(!s) return '';
   var trava = (s.situacao==='processando');
   var feita = (s.situacao==='concluida');
   var retom = (s.situacao==='retomavel');
   var refaz = (s.situacao==='refazer');
   var cor = trava?'var(--perigo,#E96A5C)'
      :((retom||refaz)?'var(--aviso,#E1B23B)'
      :(feita?'var(--success,#5BC57F)':(s.tem_rs?'var(--warn,#E1B23B)':'var(--text-dim,#72829b)')));
   function sit(glifo, frase, det){
    return (glifo ? '<span aria-hidden="true">'+glifo+'</span> ' : '')
     + '<span data-radai-frase>'+frase+'</span>'
     + (det ? ' · <span>'+esc(det)+'</span>' : '');
   }
   var txt = trava?sit('&#9210;','em processamento',s.detalhe)
      :(retom?sit('&#8635;','parou no meio',s.detalhe)
      :(refaz?sit('&#8635;','a refazer: marcador sem RTSTRUCT','')
      :(feita?sit('&#10003;','já segmentada',s.detalhe)
      :(s.tem_rs?sit('&#9888;','já tem um RTSTRUCT na pasta'):sit('','livre')))));
   if(feita && s.faltou && s.faltou.length){
    var ftx = (window.radaiFrase ? window.radaiFrase('Faltou nesta série: %s')
               : 'Faltou nesta série: %s').replace('%s', s.faltou.join(', '));
    txt += ' <span class="sit-parcial" data-radai-frase title="' + esc(ftx)
      + '">Parcial</span><br><span class="tec2 sit-faltou">' + esc(ftx) + '</span>';
   }
   if(feita && s.pos){
    if(s.pos.receita_mudou) txt += '<br><span class="tec2" data-radai-frase>'
      + 'a receita do pós-processamento mudou desde a entrega</span>';
    if(s.pos.refazivel) txt += '<br><button class="mini" type="button" '
      + 'onclick="refazerPos('+i+')" data-radai-frase>'
      + 'Refazer só o pós-processamento</button>';
   }
   var lau = s.espessura_laudo || {};
   var marca = (lau.nivel === 'acima' || lau.nivel === 'muito_acima')
             ? ' <span class="tec2" style="opacity:.75">&#9432;</span>' : '';
   var tec = '<span class="tec2"'
           + (lau.frase ? ' title="' + esc(lau.frase.split('**').join(''))
                        + (lau.fonte ? ' — ' + esc(lau.fonte) : '') + '"' : '')
           + '>'
           + (s.espessura_mm!=null? Number(s.espessura_mm).toFixed(2).replace('.',',')+' mm':'—')
           + (s.kernel? ' · '+esc(s.kernel):'') + marca + '</span>';
   var pq = (s.axial===false && modalidadeDe(s)!=='MR')
      ? '<span class="tec2 desc-l" style="color:var(--text-dim,#72829b)" data-radai-frase title="reconstrução coronal ou sagital, não a série axial da aquisição">reconstrução coronal ou sagital, não a série axial da aquisição</span>'
      : (s.sugerida?'<span class="sub desc-l" style="color:var(--success,#5BC57F)" data-radai-frase title="melhor reconstrução deste exame">melhor reconstrução deste exame</span>'
          +(s.porque_sugerida?'<span class="tec2 desc-l" style="color:var(--text-dim,#72829b)">'
            +String(s.porque_sugerida).split('; ').map(function(f){
               return '<span data-radai-frase title="'+esc(f)+'">'+esc(f)+'</span>' }).join('; ')
            +'</span>':''):'');
   var dentro = !!INCL[i];
   var bt = trava
     ? '<button class="mini" disabled title="outra estação está com esta série">travada</button>'
     : '<button class="mini'+(dentro?' dentro':'')+'" onclick="alternar('+i+')">'
       +(dentro?'<span aria-hidden="true">&#10003;</span> <span data-radai-frase>selecionada</span>'
               :'selecionar para processar')+'</button>';
   var ver = s.tem_rs
     ? '<button class="mini" onclick="verNoPasso4('+i+')">ver contornos</button>'
     : '<button class="mini" id="vi_'+i+'" onclick="verNoPasso4('+i+')">'
       +(PREV_ABERTA[chaveDe(s)] ? 'fechar visualizador' : 'ver imagens')
       +'</button>';
   return '<tr id="linha_'+i+'"'+(dentro?' class="linhaon"':'')+'>'
    +'<td>'+(s.nome? ('<b>'+esc(s.nome)+'</b><br><span class="tec2">'
                      +esc(s.pid)+'</span>') : esc(s.pid))+'</td>'
    +'<td>'+esc(dataBr(s.date))
      + (horaBr(s.hora) ? ('<div class="tec2">'+esc(horaBr(s.hora))+'</div>')
                        : '')
      +'</td>'+celulaModalidade(s)
    +'<td>'+esc(s.cortes)+'</td>'
    +'<td class="sub">'+tec+'</td>'
    +'<td class="desc"><div class="desc-cx"><span class="desc-t" data-radai-t="1" title="'
      +esc(s.desc)+'">'+esc(s.desc)+'</span>'+pq+'</div></td><td class="serie">'+celulaSerie(i)+'</td>'
    +'<td style="color:'+cor+'">'+txt+'</td>'
    +'<td class="acoes"><span class="acoes-bts">'+bt+ver+'</span></td>'
    +'<td class="modo">'+celulaModo(i)+'</td></tr>';
}

function celulaSerie(i){
 var s = SERIES[i]; if(!s) return '';
 if(!s.b) return '<span class="tec2">' + esc(s.curto || '') + '</span>';
 return '<button type="button" class="mini-serie" data-mini-i="' + i + '"'
  + ' title="duplo clique abre a série" aria-label="duplo clique abre a série">'
  + '<img loading="lazy" decoding="async" alt="" draggable="false"'
  + ' src="/api/lote/miniatura?b=' + encodeURIComponent(s.b) + '"></button>';
}
document.addEventListener('error', function(ev){
 var t = ev.target;
 if(t && t.tagName === 'IMG' && t.parentNode && t.parentNode.classList
    && t.parentNode.classList.contains('mini-serie')) t.parentNode.classList.add('sem');
}, true);
function _janelasDoVisor(s){
 return modalidadeDe(s) === 'MR'
  ? [{chave:'auto', rotulo:'automática'}]
  : [{chave:'mediastino', rotulo:'mediastino'}, {chave:'pulmao', rotulo:'pulmão'},
     {chave:'osso', rotulo:'osso'}];
}
function abrirVisorDaSerie(i, origem){
 var s = SERIES[i]; if(!s || s.carregando || !s.b || !window.uiVisor) return null;
 var jan = _janelasDoVisor(s), m = modalidadeDe(s);
 var esp = (s.espessura_mm != null)
   ? Number(s.espessura_mm).toFixed(2).replace('.', ',') + ' mm' : '';
 var cab = [['Paciente', s.nome || ''], ['ID', s.pid || ''],
  ['Data', (dataBr(s.date) + ' ' + horaBr(s.hora)).trim()],
  ['Modalidade', m === 'MR' ? 'RM' : (m === 'CT' ? 'TC' : '—')],
  ['Descrição', s.desc || ''], ['Cortes', String(s.cortes || '')],
  ['Espessura', esp], ['Kernel', s.kernel || ''],
  ['Série', s.numero != null ? String(s.numero) : (s.curto || '')]]
  .filter(function(p){ return p[1] !== '' });
 var v = window.uiVisor({
  titulo: s.desc || 'Série', total: Number(s.cortes) || 1,
  janelas: jan, janela: jan[0].chave, cabecalho: cab, origem: origem,
  carregando: 'abrindo a série…', cranial: s.cranial,
  src: function(k, j){
   return '/api/lote/corte?b=' + encodeURIComponent(s.b) + '&corte=' + k
     + '&janela=' + encodeURIComponent(j);
  }});
 if(s.cranial == null && v && v.definirSentido){
  fetch('/api/lote/sentido', {method: 'POST',
    headers: {'Content-Type': 'application/json'}, body: JSON.stringify({b: s.b})})
   .then(function(r){ return r.json() })
   .then(function(d){
    if(!d || (d.cranial !== 1 && d.cranial !== -1)) return;
    s.cranial = d.cranial; v.definirSentido(d.cranial);
   })
   .catch(function(){});
 }
 return v;
}
document.addEventListener('dblclick', function(ev){
 var b = ev.target && ev.target.closest ? ev.target.closest('.mini-serie') : null;
 if(!b) return;
 ev.preventDefault();
 abrirVisorDaSerie(parseInt(b.getAttribute('data-mini-i'), 10), b);
});
document.addEventListener('keydown', function(ev){
 if(ev.key !== 'Enter') return;
 var b = ev.target && ev.target.closest ? ev.target.closest('.mini-serie') : null;
 if(!b || b !== ev.target) return;
 ev.preventDefault();
 abrirVisorDaSerie(parseInt(b.getAttribute('data-mini-i'), 10), b);
});

function alternar(i){
 var s = SERIES[i]; if(!s || s.carregando || s.b === null || s.bilhete === null) return;
 porNoCarrinho(s, !noCarrinho(s));
 sincronizarIncl(); pintarTabela() }

// GUARDA: marcar e esvaziar mexem so nas series desta lista; esvaziar o que veio de outra pasta seria apagar escolha que a tela nao mostra.
function marcar(v){
 SERIES.forEach(function(s){
   if(s.situacao !== 'processando' && !s.carregando && s.b !== null && s.bilhete !== null) porNoCarrinho(s, !!v) });
 sincronizarIncl(); pintarTabela()}

function incluidas(){ return carrinhoLista() }

function rodar(){
 var sel=incluidas();
 if(!sel.length){
  cartMsg('<span data-radai-frase>Inclua pelo menos uma série na tabela acima.</span>', false);
  uiTremer(el('btrodar'));
  return }

 var refeitas=sel.filter(function(s){
   return s.situacao==='concluida' || s.tem_rs
       || (s.radai_na_pasta && s.radai_na_pasta.length)});
 if(refeitas.length){
  var nArq=refeitas.reduce(function(a,s){
    return a + ((s.radai_na_pasta||[]).length)}, 0);
  var lista=refeitas.slice(0,6).map(function(s){
    return '  · '+(s.nome||s.pid||'?')+'  ...'+(s.curto||'')
         +((s.radai_na_pasta&&s.radai_na_pasta.length)
           ? ('  ('+s.radai_na_pasta.length+' arquivo(s))') : '')}).join('\\n')
   +(refeitas.length>6?('\\n  · e mais '+(refeitas.length-6)):'');
  perguntar({
   titulo: 'Séries já segmentadas',
   corpo: refeitas.length+' das series marcadas JA FORAM SEGMENTADAS:\\n\\n'+lista
    +'\\n\\nRodar de novo leva o mesmo tempo da primeira vez, e vai APAGAR '
    +(nArq?(nArq+' arquivo(s) RadAI da pasta delas'):'a entrega anterior')
    +' para gravar a nova no lugar.\\n\\nO exame e o que nao e nosso nao sao '
    +'tocados.',
   ok: 'Substituir', perigo: true,
   aoSim: function(){ mandarParaAFila(sel, refeitas) }
  });
  return;
 }
 mandarParaAFila(sel);
}

var CAMPOS_DA_ESCOLHA = ['estudos', 'tasks_extra', 'motores_extra', 'modo',
                         'protocolos', 'protocolos_3d', 'tasks', 'comparacao',
                         'oar_fora', 'protocolo_proprio', 'achado_declarado'];
function payloadDaSerie(s){
 var d = {};
 for(var c in s){
  if(Object.prototype.hasOwnProperty.call(s, c) && c.charAt(0) !== '_') d[c] = s[c];
 }
 CAMPOS_DA_ESCOLHA.forEach(function(k){ delete d[k] });
 delete d.substituir;
 var e = escolhaDe(s);
 d.modo = modoDe(s);
 if(d.modo === 'perso' && _opcDaSerie(s)){
  d.protocolos = protocolosLigados(s, e);
  d.protocolos_3d = protocolos3dLigados(s, e);
  d.tasks = chavesFinais(s, e);
  d.comparacao = comparacaoDe(s, e);
  d.oar_fora = Object.keys(e.oar_fora).filter(function(k){ return e.oar_fora[k] });
  var pp = _ppDaSerie(s, e);
  if(pp) d.protocolo_proprio = pp.id;
 }
 return d;
}

function _abrirAFila(){
 if(typeof radaiTfAbrirAba === 'function') radaiTfAbrirAba('fila');
 else if(window.uiDireita) window.uiDireita('0');
}
function refazerPos(i){
 var s = SERIES[i]; if(!s) return;
 perguntar({
  titulo: 'Refazer só o pós-processamento',
  corpo: 'O RTSTRUCT entregue desta série será substituído por um novo, refeito do cache desta estação, sem inferência. O exame não é tocado.',
  ok: 'Substituir', perigo: true,
  aoSim: function(){ _refazerPosJa(s) }
 });
}
function _refazerPosJa(s){
 fetch('/api/lote/refazer_pos',{method:'POST',
   headers:{'Content-Type':'application/json'},
   body:JSON.stringify({series:[payloadDaSerie(s)]})})
 .then(function(r){return r.json()}).then(function(d){
  if(!d.ok){ cartMsg(esc('ERRO: '+(d.erro||'')), false); return }
  if(typeof radaiFilaPintar === 'function') radaiFilaPintar(d);
  _abrirAFila();
 }).catch(function(e){ cartMsg(esc('ERRO: '+e), false) });
}
function _achadosAPedir(sel){
 var itens = [];
 sel.forEach(function(s){
  var pp = _ppDaSerie(s);
  var t = pp && pp.tem_achado ? (pp.nome + ' · ' + (pp.achados || []).join(', ')) : '';
  if(t && itens.indexOf(t) < 0) itens.push(t);
 });
 return itens;
}
function _pedirADeclaracao(itens, aoSim){
 perguntar({titulo: 'Detecção (ACHADO) no protocolo próprio', ok: 'Declarar e enviar à fila',
  html: '<div class="tk-b"><p data-radai-frase>A detecção (ACHADO) roda só por ato declarado, e se declara de novo a cada envio à fila. O resultado sai no arquivo próprio do achado, nunca no STUDY.</p>'
   + _chipsHTML(itens) + '</div>',
  aoSim: aoSim});
}
function mandarParaAFila(sel, refazer, declarado){
 sel = (sel || []).filter(function(s){ return !s.carregando && s.b !== null && s.bilhete !== null });
 if(!sel.length) return;
 var itens = declarado ? [] : _achadosAPedir(sel);
 if(itens.length){
  _pedirADeclaracao(itens, function(){ mandarParaAFila(sel, refazer, true) });
  return;
 }
 var series = sel.map(payloadDaSerie);
 if(refazer) series.forEach(function(d, k){
   if(refazer.indexOf(sel[k]) >= 0) d.substituir = true });
 if(declarado) series.forEach(function(d, k){
   var pp = _ppDaSerie(sel[k]);
   if(pp && pp.tem_achado) d.achado_declarado = true });
 var bt = el('btrodar'); if(bt) bt.disabled = true;
 fetch('/api/lote/enfileirar',{method:'POST',
   headers:{'Content-Type':'application/json'},
   body:JSON.stringify({series:series, incluir_vista:null})})
 .then(function(r){return r.json()}).then(function(d){
  if(bt) bt.disabled = false;
  if(!d.ok){ cartMsg(esc('ERRO: '+(d.erro||'')), false); return }
  if(typeof radaiFilaPintar === 'function') radaiFilaPintar(d);
  _abrirAFila();
  limparSelecao();
  var h = '<b>' + (d.enfileiradas||0) + '</b> <span data-radai-frase>enviada(s) para a fila</span>';
  if(d.atualizadas) h += ' · <b>' + d.atualizadas + '</b> <span data-radai-frase>já esperava(m) na fila, e a escolha foi atualizada</span>';
  if(d.repetidas) h += ' · <b>' + d.repetidas + '</b> <span data-radai-frase>já estava(m) na fila</span>';
  cartMsg(h, true);
 }).catch(function(e){
  if(bt) bt.disabled = false;
  cartMsg(esc('ERRO: '+e), false);
 });
}

var PREV_ABERTA = {};
function _rotuloVer(i, aberto){
 var b = el('vi_'+i);
 if(b) uiTexto(b, aberto ? 'fechar visualizador' : 'ver imagens');
 try{ if(window.radaiRetraduzir) window.radaiRetraduzir() }catch(e){}
}
function _linhaPrevia(i){
 var cx = el('prev_'+i);
 if(cx) return cx;
 cx = document.createElement('tr');
 cx.id = 'prev_'+i;
 cx.innerHTML = '<td colspan="10" class="prev-cx"></td>';
 var depois = el('perso_'+i) || el('linha_'+i);
 if(!depois || !depois.parentNode) return null;
 depois.parentNode.insertBefore(cx, depois.nextSibling);
 return cx;
}
function _serieDoVisor(s){
 return {pasta: s.pasta, zip: s.zip || '', uid: s.uid};
}
function _reporPrevias(){
 for(var i = 0; i < SERIES.length; i++){
  var k = chaveDe(SERIES[i]);
  if(!PREV_ABERTA[k]) continue;
  var cx = _linhaPrevia(i); if(!cx) continue;
  umEixoNaCelula(cx.querySelector('td'), k, _serieDoVisor(SERIES[i]));
 }
 umEixoVarrer();
}
function verNoPasso4(i){
 var s = SERIES[i]; if(!s || s.carregando || s.b === null || s.bilhete === null) return;
 if(s.tem_rs){
  try{
   sessionStorage.setItem('radai_ver_pasta', s.pasta || el('pasta').value || '');
   sessionStorage.setItem('radai_ver_uid', s.uid || '');
  }catch(e){}
  location.href = '/ver';
  return;
 }
 var k = chaveDe(s);
 if(PREV_ABERTA[k]){                       // segundo clique fecha
  delete PREV_ABERTA[k];
  umEixoSoltar(k);
  var velha = el('prev_'+i);
  if(velha && velha.parentNode) velha.parentNode.removeChild(velha);
  _rotuloVer(i, false);
  return;
 }
 PREV_ABERTA[k] = true;
 var cx = _linhaPrevia(i);
 if(!cx){ delete PREV_ABERTA[k]; return }
 _rotuloVer(i, true);
 umEixoNaCelula(cx.querySelector('td'), k, _serieDoVisor(s));
}

(function(){
 try{
  var p = sessionStorage.getItem('radai_lote_pasta');
  if(!p) return;
  var campo = el('pasta');
  if(!campo || campo.value) return;   // já preenchida: não atropela
  campo.value = p;
  LT_CHEGOU_COM_SERIES = true;
  if(new URLSearchParams(location.search).get('ficha')) return;
  setTimeout(function(){ varrer({quieto: true}) }, 60);
 }catch(e){}
})();

if(window.uiPopupSerie)
 uiPopupSerie('cx1', {sozinho: function(){ return !LT_CHEGOU_COM_SERIES }});
if(window.uiPopupSerie) uiPopupSerie('cx1', {aoFechar: _ltAoFecharPopup,
 aoAbrir: function(){ _ltAoAbrirPopup() }});
['cx2'].forEach(function(id){
 var c = el(id); if(c) c.classList.add('fechado');
});

var NIGHT_ON = false;

var OV = {cfg: null, painel: null, laudo: null, t: null, pai: '', pasta: '',
          escuta: null, turno: false, pendente: false, rootAdiado: false,
          tremerAoAbrir: false};
function _ovQ(sel){ return document.querySelector('.ui-pnl ' + sel) }
function _ovMod(v){
 v = String(v || 'CT').toUpperCase().replace(/;/g, ',').replace(/ /g, ',')
     .split(',').filter(function(x){ return x }).sort().join(',');
 return (v === 'CT' || v === 'MR' || v === 'CT,MR') ? v : 'CT';
}
function _ovValores(){
 var r = _ovQ('#ov_root'), d = _ovQ('#ov_dias'), m = _ovQ('#ov_mod [aria-checked="true"]');
 var dias = Math.max(0, Math.min(3650, parseInt((d && d.value) || '0', 10) || 0));
 var pastas = [];
 Array.prototype.forEach.call(document.querySelectorAll('.ui-pnl [data-ov-root]'), function(e){
  var p = String(e.value || '').trim();
  if(p && !pastas.some(function(q){ return p.toLowerCase() === q.toLowerCase() })) pastas.push(p);
 });
 if(!pastas.length && r && r.value.trim()) pastas.push(r.value.trim());
 return {ROOT: pastas[0] || '', ROOTS: JSON.stringify(pastas),
         MODALITIES: m ? m.getAttribute('data-ov-mod') : 'CT',
         DAYS_BACK: String(dias)};
}
function _ovEscolherMod(v){
 Array.prototype.forEach.call(document.querySelectorAll('.ui-pnl #ov_mod [data-ov-mod]'), function(b){
  var sel = (b.getAttribute('data-ov-mod') === v);
  b.setAttribute('aria-checked', sel ? 'true' : 'false');
  b.tabIndex = sel ? 0 : -1;
 });
}
function _ovLaudo(txt, cls){
 var l = _ovQ('#ov_root_laudo'); if(!l) return;
 l.className = 'ov-laudo' + (cls ? (' ' + cls) : '');
 uiTexto(l, txt);
}
// GUARDA: abrir a folha só lê a pasta; o teste de escrita cria um arquivo na árvore dos pacientes e só acontece ao salvar.
function _ovTestar(){
 clearTimeout(OV.t);
 OV.laudo = null; _ovEstado();
 OV.t = setTimeout(function(){
  var valores = _ovValores(), v = valores.ROOT, pastas = JSON.parse(valores.ROOTS || JSON.stringify(v ? [v] : []));
  if(!v){
   OV.laudo = {vazio: true}; _ovLaudo('Sem pasta, o turno não tem o que varrer.', 'aviso'); _ovEstado();
   if(OV.tremerAoAbrir){ OV.tremerAoAbrir = false; _ovTremerRoot() }
   return;
  }
  OV.tremerAoAbrir = false;
  _ovLaudo('conferindo a pasta…', '');
  Promise.all(pastas.map(function(p){
   return fetch('/api/lote/conferir_pasta', {method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({caminho: p})}).then(function(r){ return r.json() });
  })).then(function(laudos){
   if(_ovValores().ROOTS !== valores.ROOTS) return;
   var d = laudos.filter(function(l){ return !(l && l.existe && l.leitura) })[0];
   OV.laudo = d || {existe:true, leitura:true};
   if(!d) _ovLaudo('As pastas existem e leem. A escrita será conferida ao salvar.', 'ok');
   else _ovLaudo((d && (d.erro || d.aviso)) || 'Não consegui conferir a pasta.', 'ruim');
   _ovEstado();
  }).catch(function(){ OV.laudo = {}; _ovLaudo('Não consegui conferir a pasta.', 'ruim'); _ovEstado() });
 }, 450);
}
function _ovLaudoBom(){ var l = OV.laudo; return !!(l && l.existe && l.leitura) }
function _ovTremerRoot(){
 var r = _ovQ('#ov_root');
 if(r && window.uiTremer) window.uiTremer(r);
}
function _ovConferirEscrita(v){
 if(!v.ROOT) return Promise.resolve(true);
 var pastas; try{ pastas = JSON.parse(v.ROOTS || '[]') }catch(e){ pastas = [] }
 if(!pastas.length) pastas = [v.ROOT];
 return Promise.all(pastas.map(function(p){ return fetch('/api/config/testar', {method:'POST', headers:{'Content-Type':'application/json'},
   body: JSON.stringify({caminho: p})})
  .then(function(r){ return r.json() }).then(function(d){
   if(d && d.existe && d.leitura && d.escrita) return true;
   throw new Error((d && (d.erro || d.aviso)) || 'A pasta não grava: o turno não foi salvo.');
  }) }));
}
// GUARDA: Salvar e iniciar so com o config lido e a pasta boa.
function _ovEstado(){
 var sim = document.getElementById('ui-pnl-sim');
 if(sim) sim.disabled = !(OV.cfg && _ovLaudoBom());
}
function _ovPreencher(){
 fetch('/api/config').then(function(r){ return r.json() }).then(function(d){
  var v = (d && d.valores) || {}, p = (d && d.padroes) || {};
  var root = String(v.ROOT != null ? v.ROOT : (p.ROOT || '')).trim();
  var mod = _ovMod(v.MODALITIES != null ? v.MODALITIES : p.MODALITIES);
  var dias = String(Math.max(0, parseInt(v.DAYS_BACK != null ? v.DAYS_BACK : (p.DAYS_BACK || '0'), 10) || 0));
  var roots; try{ roots = JSON.parse(v.ROOTS || p.ROOTS || '[]') }catch(e){ roots = [] }
  if(!Array.isArray(roots)) roots = [];
  roots = [root].concat(roots).filter(function(x, i, a){ return x && a.indexOf(x) === i });
  OV.cfg = {ROOT: root, ROOTS: JSON.stringify(roots), MODALITIES: mod, DAYS_BACK: dias};
  var r = _ovQ('#ov_root'), di = _ovQ('#ov_dias');
  if(r) r.value = root;
  roots.filter(function(x){ return x !== root }).forEach(_ovAdicionarRaiz);
  if(di) di.value = dias;
  OV.tremerAoAbrir = !root;
  _ovEscolherMod(mod);
  _ovTestar();
 }).catch(function(){
  _ovLaudo('Não consegui ler a configuração desta estação.', 'ruim');
 });
}
function _ovAdicionarRaiz(valor){
 var lista = _ovQ('#ov_roots'); if(!lista) return;
 var linha = document.createElement('div'); linha.className = 'ov-root';
 var input = document.createElement('input'); input.setAttribute('data-ov-root', '1');
 input.setAttribute('aria-label', 'Pasta adicional'); input.spellcheck = false; input.autocomplete = 'off';
 input.value = typeof valor === 'string' ? valor : '';
 var procurar = document.createElement('button'); procurar.type = 'button'; procurar.className = 'ui-bt';
 procurar.setAttribute('data-ov-procurar', '1'); uiTexto(procurar, 'Procurar…');
 var tirar = document.createElement('button'); tirar.type = 'button'; tirar.className = 'ui-bt';
 uiTexto(tirar, 'Remover'); tirar.onclick = function(){ linha.remove(); _ovTestar() };
 linha.appendChild(input); linha.appendChild(procurar); linha.appendChild(tirar); lista.appendChild(linha);
 if(!valor) input.focus();
 _ovTestar();
}
function _ovAbrirPastas(alvo){
 if(!window.uiExplorador) return;
 uiExplorador({titulo: 'Pasta que o turno varre', inicial: _ovValores().ROOT || '',
  origem: _ovQ('#ov_root_bt'),
  aoUsar: function(c){
   var r = alvo || _ovQ('#ov_root'); if(!r || !c) return;
   r.value = c; _ovTestar();
  }});
}
function _ovLigar(){
 var v = document.querySelector('.ui-pnl-veu'); if(!v) return;
 _ovSoltar();
 var tecla = function(ev){
  if(ev.key === 'Enter'){
   ev.stopPropagation();
   var alvo = ev.target;
   if(!_ovValores().ROOT && !(alvo && alvo.matches && alvo.matches('button,a,[role]')))
    _ovTremerRoot();
   return;
  }
  var r = ev.target && ev.target.closest && ev.target.closest('#ov_mod [data-ov-mod]');
  if(r && (ev.key === 'ArrowLeft' || ev.key === 'ArrowRight')){
   ev.preventDefault();
   var bs = Array.prototype.slice.call(document.querySelectorAll('.ui-pnl #ov_mod [data-ov-mod]'));
   var k = (bs.indexOf(r) + (ev.key === 'ArrowRight' ? 1 : bs.length - 1)) % bs.length;
   _ovEscolherMod(bs[k].getAttribute('data-ov-mod')); bs[k].focus(); _ovEstado();
  }
 };
 var clique = function(ev){
  var t = ev.target; if(!t || !t.closest) return;
  var m = t.closest('#ov_mod [data-ov-mod]');
  if(m){ _ovEscolherMod(m.getAttribute('data-ov-mod')); _ovEstado(); return }
  var dd = t.closest('[data-ov-dias]');
  if(dd){
   var di = _ovQ('#ov_dias');
   if(di) di.value = String(Math.max(0, Math.min(3650,
     (parseInt(di.value, 10) || 0) + parseInt(dd.getAttribute('data-ov-dias'), 10))));
   _ovEstado(); return;
  }
  if(t.closest('#ov_root_bt')){ _ovAbrirPastas(); return }
  if(t.closest('#ov_root_add')){ _ovAdicionarRaiz(); return }
  var procurar = t.closest('[data-ov-procurar]');
  if(procurar){ _ovAbrirPastas(procurar.closest('.ov-root').querySelector('[data-ov-root]')); return }
 };
 var digito = function(ev){
  var t = ev.target; if(!t) return;
  if(t.id === 'ov_root' || t.hasAttribute('data-ov-root')) _ovTestar();
  else if(t.id === 'ov_dias') _ovEstado();
 };
 v.addEventListener('keydown', tecla, true);
 v.addEventListener('click', clique);
 v.addEventListener('input', digito);
 OV.escuta = {v: v, tecla: tecla, clique: clique, digito: digito};
}
function _ovSoltar(){
 var e = OV.escuta; if(!e) return;
 e.v.removeEventListener('keydown', e.tecla, true);
 e.v.removeEventListener('click', e.clique);
 e.v.removeEventListener('input', e.digito);
 OV.escuta = null;
}
function _ovTravarSalvar(){
 var sim = document.getElementById('ui-pnl-sim');
 if(sim) sim.disabled = true;
}
function _ovSemBotao(){
 var sim = document.getElementById('ui-pnl-sim');
 if(sim) sim.disabled = false;
 _ovSoltar();
}
function folhaOvernight(){
 if(NIGHT_ON){ _ovJaNaFila(); return }
 var corpo = document.getElementById('ov_folha_corpo');
 OV.cfg = null; OV.laudo = null; OV.tremerAoAbrir = false;
 OV.painel = uiPainel({
  titulo: 'Incluir Overnight Run',
  html: corpo ? corpo.innerHTML : '',
  ok: 'Salvar e incluir na fila',
  cancelar: 'Cancelar',
  debaixo: true,
  fecharFora: false,
  aoSim: function(){ var v = _ovValores();
                     _ovSemBotao(); ovIniciar(true, v) },
  aoNao: function(){ _ovSemBotao() }
 });
 _ovTravarSalvar();
 _ovLigar();
 var fav = _ovQ('[data-ui-fav]');
 if(fav && window.uiFavoritaLigar) uiFavoritaLigar(fav);
 _ovPreencher();
 if(window.uiRevelar) window.uiRevelar(_ovQ('.ov-form'), true);
 try{ if(window.radaiRetraduzir) window.radaiRetraduzir() }catch(x){}
 fetch('/api/overnight/frota').then(function(r){return r.json()})
  .then(function(d){
   var alvo = _ovQ('#ov_frota');
   if(!alvo) return;
   var r = (d && d.resumo) || {};
   var av = _ovQ('#ov_frota_aviso');
   if(d && d.configurado === false){
    alvo.className = 'ov-frota'; alvo.innerHTML = '';
    if(av){ av.hidden = false; if(d.aviso) uiTexto(av, d.aviso) }
    return;
   }
   if(av) av.hidden = true;
   alvo.className = 'ov-frota';
   alvo.innerHTML = '';
   [['máquinas', r.n || 0], ['trabalhando', r.trabalhando || 0],
    ['paradas', r.paradas || 0]].forEach(function(par){
    var c = document.createElement('span');
    c.className = 'ov-chip';
    var n = document.createElement('b'); n.textContent = String(par[1]);
    var t = document.createElement('span');
    t.setAttribute('data-radai-frase', ''); t.textContent = par[0];
    c.appendChild(n); c.appendChild(t); alvo.appendChild(c);
   });
   if(typeof window.radaiRetraduzir === 'function') window.radaiRetraduzir();
  }).catch(function(){});
}
function _ovCard(txt){ var tx = el('cd_night_tx'); if(tx && txt) uiTexto(tx, txt) }
function _ovErro(msg){
 perguntar({titulo: 'Overnight Run', corpo: String(msg || ''), ok: 'Fechar', so_ok: true});
}
function ovIniciar(salvar, valores){
 var v = valores || _ovValores();
 _ovCard('Preparando o Overnight Run…');
 var passo = Promise.resolve(true);
 if(salvar){
  passo = _ovConferirEscrita(v).then(function(){
   return fetch('/api/config', {method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({valores: v, confirmar_root: true})});
  })
  .then(function(r){ return r.json() }).then(function(r){
   if(!r || !r.ok) throw new Error((r && r.erro) || 'Não consegui gravar a configuração.');
   if(!(r.salvos || []).length) return true;
   return fetch('/api/reiniciar', {method:'POST'}).then(function(){ return true });
  });
 }
 passo.then(function(){ return _ovPorNaFila() })
  .catch(function(e){ filaEstado(); _ovErro((e && e.message) || e) });
}
function _ovPorNaFila(){
 return filaOvernight(true).then(function(d){
  if(!d || d.erro) throw new Error((d && d.erro) || 'Não consegui incluir o turno na fila.');
  _ovCard('Na fila, aguardando INICIAR.');
 });
}
function _ovTextoAberto(){
 if(OV.rootAdiado)
  return 'Overnight Run aberto: a pasta nova vale a partir do próximo turno, e este segue na pasta em que abriu. Clique para encerrar.';
 return OV.pendente
  ? 'Overnight Run aberto: a configuração nova vale quando a série em curso terminar. Clique para encerrar.'
  : 'Overnight Run aberto: a estação está varrendo sozinha. Clique para encerrar.';
}
function _ovJaNaFila(){
 fetch('/api/status').then(function(r){ return r.json() }).catch(function(){ return {} })
 .then(function(st){
  if(!(st && st.overnight)){ filaOvernight(false); return }
  perguntar({
   titulo: 'Encerrar o Overnight Run',
   corpo: 'A série em curso termina e a estação deixa de varrer sozinha.',
   ok: 'Encerrar o turno',
   aoSim: function(){
    fetch('/api/overnight/encerrar', {method:'POST'}).then(function(r){ return r.json() })
    .catch(function(){ return {} }).then(function(){ OV.turno = false; filaOvernight(false) });
   }
  });
 });
}
function ovInterromper(){
 perguntar({titulo:'Interromper Overnight Run',
  corpo:'A série em curso será interrompida; as concluídas serão preservadas.',
  ok:'Interromper', perigo:true, aoSim:function(){
   fetch('/api/overnight/interromper', {method:'POST'}).then(function(r){return r.json()})
    .then(function(d){ if(d && d.ok){ OV.turno=false; filaOvernight(false) } })
    .catch(function(e){ _ovErro(String(e)) });
  }});
}

function filaOvernight(){
 var quero = (arguments.length ? !!arguments[0] : !NIGHT_ON);
 var corpo = {ligado:quero};
 return fetch('/api/fila/overnight',{method:'POST',
  headers:{'Content-Type':'application/json'},
  body:JSON.stringify(corpo)})
 .then(function(r){return r.json()}).then(function(d){
  filaEstadoPintar(d);
  if(typeof radaiFilaPintar === 'function') radaiFilaPintar(d);
  return d;
 }).catch(function(){ return null });
}
function filaEstadoPintar(d){
 var L = (d && d.cards) || [], r = (d && d.resumo) || {};
 var cardTurno = null;
 L.forEach(function(c){ if(c.tipo === 'overnight') cardTurno = c });
 NIGHT_ON = !!cardTurno;
 if(!NIGHT_ON){ OV.turno = false; OV.pendente = false; OV.rootAdiado = false }
 if(cardTurno && cardTurno.estado === 'rodando') OV.turno = true;
 var parar = el('ov_interromper'); if(parar) parar.hidden = !(NIGHT_ON && OV.turno);
 var cd = el('cd_night'), tx = el('cd_night_tx');
 if(cd) cd.classList.toggle('ligado', NIGHT_ON);
 if(tx) uiTexto(tx, (NIGHT_ON && OV.turno)
   ? _ovTextoAberto()
   : (cardTurno && cardTurno.estado === 'falhou'
      ? 'O turno não abriu: o motivo está no card da fila e no log. Clique para tirar.'
      : (NIGHT_ON
         ? (!cardTurno.iniciar_pedido ? 'Na fila, aguardando INICIAR.' : 'Na fila, como último card. Clique para tirar.')
         : 'Entra como último card da fila: quando ela chegar nele, a '
           + 'estação passa a varrer sozinha.')));
}
function filaEstado(){
 fetch('/api/fila').then(function(r){return r.json()})
  .then(function(d){
   filaEstadoPintar(d);
   if(!NIGHT_ON) return;
   return fetch('/api/status').then(function(r){ return r.json() }).then(function(st){
    OV.turno = !!(st && st.overnight);
    OV.pendente = !!(st && st.overnight && st.recarga_pendente);
    OV.rootAdiado = !!(st && st.overnight && st.root_no_proximo_turno);
    filaEstadoPintar(d);
   });
  }).catch(function(){});
}
filaEstado(); setInterval(filaEstado, 15000);

fetch('/api/lote/favorita',{method:'POST',
 headers:{'Content-Type':'application/json'},body:'{}'})
.then(function(r){return r.json()}).then(function(d){
 FP_FAV = d.favorita || '';
 var campo = el('pasta');
 if(FP_FAV && campo && !campo.value){
  campo.value = FP_FAV;
  msg('pasta favorita preenchida \u2014 clique em «Varrer s\u00e9ries»', true);
 }
}).catch(function(){});

(function(){
 var f = null;
 try{ f = new URLSearchParams(location.search).get('ficha') }catch(e){}
 if(!f) return;
 LT_CHEGOU_COM_SERIES = true;
 fetch('/api/lote/selecao/abrir', {method:'POST', headers:{'Content-Type':'application/json'},
   body: JSON.stringify({ficha: f})})
 .then(function(r){ return r.json() }).then(function(d){
  var L = (d && d.series) || [];
  if(!(d && d.ok) || !L.length){
   ltEscolha();
   msg((d && d.erro) || 'a seleção não está mais disponível — escolha as séries de novo no DicomBridge', false);
   return;
  }
  SERIES = L; window.PASTA_VARRIDA = d.pasta || '';
  SERIES.forEach(function(s){
   VISTAS[chaveDe(s)] = true;
   if(s.situacao !== 'processando') porNoCarrinho(s, true);
  });
  sincronizarIncl(); pintarTabela(); _tituloDoPasso2(true);
  _achouNaTela('', '');
  if(window.uiPopupSerie) uiPopupSerie('cx1').fechar();
  psAbrir('cx2', true);
  if(d.aviso) cartMsg('<span data-radai-frase>' + esc(d.aviso) + '</span>', false);
 }).catch(function(e){ ltEscolha(); msg('ERRO: ' + e, false) });
})();

var FP_FAV = '';
function ltProcurar(bt){
 if(!window.uiExplorador){ msg('não consegui abrir o seletor de pastas', false); return }
 window.uiExplorador({titulo: 'Escolher a pasta', origem: bt || el('lt_procurar'),
  inicial: ((el('pasta') || {}).value || FP_FAV || '').trim(),
  aoUsar: function(c){
   if(!c) return;
   el('pasta').value = c;
   varrer();
  }});
}

var OPC={};
var MODALIDADES=['CT','MR'];
var MODO_DE_FABRICA='auto';
var MODOS_RESERVA=[{cod:'fast', rotulo:'FAST'}, {cod:'auto', rotulo:'AUTO'},
                   {cod:'perso', rotulo:'PERSONALIZADO'}];

function carregarOpcoes(){
 MODALIDADES.forEach(function(m){
  fetch('/api/lote/opcoes?modalidade='+encodeURIComponent(m))
  .then(function(r){return r.json()}).then(function(d){
   if(d.erro){
    cartMsg(esc('Nao consegui montar as opcoes: '+d.erro), false);
    return}
   OPC[m]=d;
   if(d.modo_de_fabrica) MODO_DE_FABRICA = d.modo_de_fabrica;
   pintarTabela();
  }).catch(function(e){
   cartMsg(esc('Nao consegui falar com o servidor ('+e+').'), false);
  });
 });
}

var ESCOLHA = {};
function escolhaDe(s){
 var k = chaveDe(s || {});
 if(!ESCOLHA[k]) ESCOLHA[k] = {modo:'', prot:{}, p3d:{}, mao:{}, comp:{}, oar_fora:{},
                               livre:false, pp:''};
 if(!ESCOLHA[k].p3d) ESCOLHA[k].p3d = {};
 return ESCOLHA[k];
}
function _ppsDaSerie(s){ return ((_opcDaSerie(s) || {}).protocolos_proprios || []) }
function _ppDaSerie(s, e){
 var id = (e || escolhaDe(s)).pp, achou = null;
 if(!id) return null;
 _ppsDaSerie(s).forEach(function(p){ if(p.id === id) achou = p });
 return achou;
}
// GUARDA: as tasks que as estruturas do protocolo proprio exigem ficam ligadas e travadas; o achado dele nao entra aqui (so com a declaracao no envio).
function _travadasPeloPp(s, e){
 var pp = _ppDaSerie(s, e), por = _porTask(_opcDaSerie(s) || {}), fora = {};
 if(!pp) return fora;
 (pp.tasks || []).concat(pp.motores || []).forEach(function(t){
  if(por[t] && por[t].permitida !== false && !por[t].achado) fora[t] = 1;
 });
 return fora;
}
function ligarProtocoloProprio(s, e, ligar, id){
 if(!ligar){ e.pp = ''; e.mao = {}; return }
 var lista = _ppsDaSerie(s), p = null;
 lista.forEach(function(x){ if(x.id === id) p = x });
 if(!p) p = lista[0];
 if(!p) return;
 e.pp = p.id; e.prot = {}; e.livre = false;
 _soAsDele(s, e, (p.tasks || []).concat(p.motores || []));
}
function _opcDaSerie(s){ return OPC[modalidadeDe(s) || 'CT'] || null }
function modoDe(s){ return escolhaDe(s).modo || MODO_DE_FABRICA }
function _porTask(d){
 var p = {};
 ((d && d.tasks) || []).forEach(function(t){ p[t.task] = t });
 return p;
}
function _arrastavel(t){ return !!t && !t.achado && t.permitida !== false }

function tasksLigadas(s, e){
 var d = _opcDaSerie(s) || {}, por = _porTask(d), on = {}, arr = {};
 (d.protocolos || []).forEach(function(p){
  if(!e.prot[p.cod]) return;
  (p.tasks || []).concat(p.motores || []).forEach(function(t){
   if(_arrastavel(por[t])){ on[t] = 1; arr[t] = 1 }
  });
 });
 (d.ligadas_de_fabrica || []).forEach(function(t){
  if(_arrastavel(por[t])) on[t] = 1;
 });
 Object.keys(e.mao).forEach(function(t){
  if(!por[t] || por[t].permitida === false) return;
  if(e.mao[t] === 1) on[t] = 1; else delete on[t];
 });
 var dep = d.ao_ligar || {};
 Object.keys(dep).forEach(function(t){
  if(e.mao[t] !== 1 || arr[t]) return;
  (dep[t] || []).forEach(function(x){
   if(e.mao[x] === undefined && _arrastavel(por[x])) on[x] = 1;
  });
 });
 var trava = _travadasPeloPp(s, e);
 Object.keys(trava).forEach(function(t){ on[t] = 1 });
 return on;
}
function _soAsDele(s, e, lista){
 var d = _opcDaSerie(s) || {}, quer = {};
 (lista || []).forEach(function(t){ quer[t] = 1 });
 e.mao = {};
 (d.tasks || []).forEach(function(t){ if(!quer[t.task]) e.mao[t.task] = 0 });
}
function ligarProtocolo(s, e, cod, ligar){
 var d = _opcDaSerie(s) || {}, p = null;
 (d.protocolos || []).forEach(function(x){ if(x.cod === cod) p = x });
 if(!p) return;
 if(!ligar){ delete e.prot[cod]; e.mao = {}; return }
 e.prot = {}; e.prot[cod] = true;
 e.p3d = {}; e.livre = false; e.pp = '';
 _soAsDele(s, e, (p.tasks || []).concat(p.motores || []));
}
function ligarSelecaoLivre(s, e, ligar){
 if(!ligar){ e.livre = false; e.mao = {}; return }
 e.pp = '';
 var d = _opcDaSerie(s) || {}, on = tasksLigadas(s, e);
 e.mao = {};
 (d.tasks || []).forEach(function(t){ e.mao[t.task] = on[t.task] ? 1 : 0 });
 e.prot = {}; e.p3d = {}; e.livre = true;
}
function chaveDaTask(s, e, t, ligar){
 if(e.pp){ e.mao[t] = ligar ? 1 : 0; return }
 if(!e.livre) ligarSelecaoLivre(s, e, true);
 e.mao[t] = ligar ? 1 : 0;
}
function protocolos3dLigados(s, e){
 return ((_opcDaSerie(s) || {}).protocolos_3d || [])
  .filter(function(p){ return (e.p3d || {})[p.cod] })
  .map(function(p){ return p.cod });
}
// GUARDA: ligar um protocolo das Reconstruções 3D zera a comparação de modelos.
function ligarProtocolo3d(s, e, cod, ligar){
 if(!e.p3d) e.p3d = {};
 if(!ligar){ delete e.p3d[cod]; e.mao = {}; return }
 e.p3d = {}; e.p3d[cod] = true; e.comp = {};
 e.prot = {}; e.livre = false;
 _soAsDele(s, e, []);
}
function protocolosLigados(s, e){
 return ((_opcDaSerie(s) || {}).protocolos || [])
  .filter(function(p){ return e.prot[p.cod] })
  .map(function(p){ return p.cod });
}
function chavesFinais(s, e){
 var d = _opcDaSerie(s) || {}, on = tasksLigadas(s, e), fora = {};
 (d.tasks || []).forEach(function(t){
  fora[t.task] = (on[t.task] && t.permitida !== false) ? 1 : 0;
 });
 return fora;
}
function _compBloqueada(c){ return c.disponivel === false || c.instalado === false }
function comparacaoDe(s, e){
 var fora = {ts:0, nv:0, cads:0, mse:0};
 ((_opcDaSerie(s) || {}).comparacao || []).forEach(function(c){
  if(!_compBloqueada(c) && e.comp[c.cod]) fora[c.cod] = 1;
 });
 return fora;
}
function resumoDoModo(s){
 var d = _opcDaSerie(s) || {}, m = modoDe(s), fora = [];
 (d.modos || MODOS_RESERVA).forEach(function(x){ if(x.cod === m) fora.push(x.rotulo) });
 if(m === 'perso'){
  var e = escolhaDe(s);
  (d.protocolos || []).forEach(function(p){ if(e.prot[p.cod]) fora.push(p.rotulo) });
  (d.protocolos_3d || []).forEach(function(p){ if((e.p3d || {})[p.cod]) fora.push(p.rotulo) });
  var pp = _ppDaSerie(s, e);
  if(pp) fora.push(pp.nome);
 }
 return fora;
}

function celulaModo(i){
 var s = SERIES[i]; if(!s) return '';
 var inc = !!INCL[i], m = modoDe(s), d = _opcDaSerie(s);
 var h = '<div class="md-cx' + (inc ? '' : ' md-off') + '">'
   + '<select class="md-sel" data-md-i="' + i + '"'
   + ' aria-label="modo de processamento desta série"' + (inc ? '' : ' disabled') + '>';
 ((d && d.modos) || MODOS_RESERVA).forEach(function(x){
  h += '<option value="' + esc(x.cod) + '"' + (x.cod === m ? ' selected' : '')
     + (x.ajuda ? ' data-ui-balao="' + esc(x.ajuda) + '"' : '') + '>'
     + esc(x.rotulo) + '</option>';
 });
 return h + '</select>'
   + '<button type="button" class="md-aj" data-md-aj="' + i + '"'
   + ' aria-label="o que faz cada modo" aria-haspopup="dialog"'
   + ' aria-expanded="false" aria-controls="md_balao">?</button></div>';
}
function _montarSeletores(){
 if(!window.uiSegmentado) return;
 Array.prototype.forEach.call(document.querySelectorAll('#tab select.md-sel'), function(sel){
  var i = parseInt(sel.getAttribute('data-md-i'), 10);
  var cx = window.uiSegmentado(sel, {embaralhar: true});
  if(!cx) return;
  cx.setAttribute('aria-label', 'modo de processamento desta série');
  sel.tabIndex = -1;
  sel.setAttribute('aria-hidden', 'true');
  if(!INCL[i]){
   cx.setAttribute('aria-disabled', 'true');
   Array.prototype.forEach.call(cx.querySelectorAll('button'), function(b){
    b.disabled = true; b.tabIndex = -1;
   });
  }
 });
 _larguraDoPainel();
}
function _soltarSeletores(){
 Array.prototype.forEach.call(document.querySelectorAll('#tab .ui-seg'), function(cx){
  if(cx._uiSoltar) cx._uiSoltar();
  else if(cx._uiPintar) window.removeEventListener('resize', cx._uiPintar);
 });
}
function _voltarSeletor(sel, valor){
 sel.value = valor;
 var cx = sel.previousElementSibling;
 if(cx && cx._uiPintar) cx._uiPintar();
}
function _mudouModo(sel){
 var i = parseInt(sel.getAttribute('data-md-i'), 10), s = SERIES[i];
 if(!s) return;
 if(!INCL[i]){ _voltarSeletor(sel, modoDe(s)); return }
 if(sel.value === 'perso' && !_opcDaSerie(s)){
  _voltarSeletor(sel, modoDe(s));
  cartMsg('<span data-radai-frase>O PERSONALIZADO precisa das opções desta modalidade, e o servidor ainda não as mandou.</span>', false);
  return;
 }
 escolhaDe(s).modo = sel.value;
 _acertarPainel(i);
 pintarCarrinho();
}

var MD_BALAO_DE = null;
function _balaoDosModos(){
 var b = el('md_balao');
 if(b) return b;
 b = document.createElement('div');
 b.id = 'md_balao'; b.className = 'ui-morf';
 b.setAttribute('role', 'dialog'); b.setAttribute('aria-modal', 'false');
 b.setAttribute('aria-labelledby', 'md_balao_tit');
 b.tabIndex = -1; b.hidden = true;
 document.body.appendChild(b);
 return b;
}
function _posicionarBalao(b, bt){
 var r = bt.getBoundingClientRect();
 var W = window.innerWidth, H = window.innerHeight;
 var w = b.offsetWidth || 390, h = b.offsetHeight || 240;
 var x = Math.min(Math.max(16, r.right - w), W - w - 16);
 var y = r.bottom + 8;
 if(y + h > H - 16 && r.top - 8 - h > 16) y = r.top - 8 - h;
 b.style.left = Math.max(16, x) + 'px';
 b.style.top = Math.max(16, y) + 'px';
}
function balaoDosModos(bt){
 var b = _balaoDosModos();
 if(MD_BALAO_DE === bt && !b.hidden){ fecharBalaoDosModos(true); return }
 var d = OPC.CT || OPC.MR || {};
 var h = '<div class="mb-tit" id="md_balao_tit" data-radai-frase>Os três modos</div><dl>';
 (d.modos || MODOS_RESERVA).forEach(function(m){
  h += '<dt>' + esc(m.rotulo) + '</dt>'
     + (m.ajuda ? ('<dd data-radai-frase>' + esc(m.ajuda) + '</dd>') : '');
 });
 h += '</dl>';
 if(d.ajuda_dos_modos)
  h += '<p class="mb-rodape" data-radai-frase>' + esc(d.ajuda_dos_modos) + '</p>';
 uiHTML(b, h);
 if(MD_BALAO_DE && MD_BALAO_DE !== bt) MD_BALAO_DE.setAttribute('aria-expanded', 'false');
 MD_BALAO_DE = bt;
 bt.setAttribute('aria-expanded', 'true');
 b.hidden = false;
 b.classList.remove('on');
 try{ if(window.radaiRetraduzir) window.radaiRetraduzir() }catch(x){}
 _posicionarBalao(b, bt);
 void b.offsetWidth;
 b.classList.add('on');
 try{ b.focus({preventScroll: true}) }catch(x){ try{ b.focus() }catch(y){} }
}
function fecharBalaoDosModos(devolverFoco){
 var b = el('md_balao');
 if(!b || b.hidden) return;
 b.classList.remove('on');
 b.hidden = true;
 if(MD_BALAO_DE){
  MD_BALAO_DE.setAttribute('aria-expanded', 'false');
  if(devolverFoco){ try{ MD_BALAO_DE.focus() }catch(x){} }
 }
 MD_BALAO_DE = null;
}
document.addEventListener('keydown', function(ev){
 if(ev.key === 'Escape' && el('md_balao') && !el('md_balao').hidden){
  ev.preventDefault(); fecharBalaoDosModos(true);
 }
});
document.addEventListener('keydown', function(ev){
 if(ev.key !== 'Enter' && ev.key !== ' ') return;
 var c = ev.target && ev.target.closest
   ? ev.target.closest('.rc-card.acao[role="button"]') : null;
 if(!c || c !== ev.target) return;
 ev.preventDefault(); c.click();
});
document.addEventListener('scroll', function(ev){
 var b = el('md_balao'), t = ev.target;
 if(!b || b.hidden || !MD_BALAO_DE) return;
 if(!(t === document || t === document.documentElement || t === document.body
      || (t && t.contains && t.contains(MD_BALAO_DE)))) return;
 var r = MD_BALAO_DE.getBoundingClientRect();
 if(r.bottom < 0 || r.top > window.innerHeight || r.right < 0
    || r.left > window.innerWidth){ fecharBalaoDosModos(false); return }
 _posicionarBalao(b, MD_BALAO_DE);
}, true);
window.addEventListener('resize', function(){ fecharBalaoDosModos(false); _larguraDoPainel() });

function _larguraDoPainel(){
 var r = document.querySelector('.tab-rola'), t = el('tab');
 if(!r || !t) return;
 var w = r.clientWidth - 34;
 if(w > 200) t.style.setProperty('--p4-larg', w + 'px');
 t.classList.toggle('p4-estreito', w > 200 && w < 1040);
}
function _painelAberto(i){
 var s = SERIES[i];
 return !!(s && INCL[i] && modoDe(s) === 'perso' && _opcDaSerie(s));
}
function _swHTML(cls, dado, ligada, travada, rotulo, frase){
 return '<label class="sw' + (travada ? ' travada' : '') + '">'
  + '<input type="checkbox" role="switch" class="' + cls + '" ' + dado
  + (ligada ? ' checked' : '') + (travada ? ' disabled' : '') + '>'
  + '<span class="tr" aria-hidden="true"></span>'
  + '<span class="sw-rot"' + (frase ? ' data-radai-frase' : '') + '>'
  + esc(rotulo) + '</span></label>';
}
function _nomeNaTela(t){
 try{ return window.radaiFrase ? window.radaiFrase(t) : t }catch(x){ return t }
}
function _ajHTML(tipo, cod, rotulo){
 var rot = 'abrir a ajuda de %s'.replace('%s', _nomeNaTela(String(rotulo || cod)));
 return '<button type="button" class="tk-aj" data-p4-aj="' + tipo + '" data-cod="'
  + esc(cod) + '" aria-label="' + esc(rot) + '" title="' + esc(rot) + '">?</button>';
}
function _linhaTask(t, ligada, base, travada){
 var proibida = (t.permitida === false);
 var h = '<div class="p4-ln' + (t.achado ? ' p4-achado' : '') + '" data-ln-task="'
   + esc(t.task) + '">'
   + _swHTML('p4-task-ck', 'data-task="' + esc(t.task) + '"',
             base || travada || (ligada && !proibida), base || proibida || travada,
             t.rotulo || t.task, true);
 if(t.achado) h += '<span class="selo-achado">ACHADO</span>';
 if(travada && !base) h += '<span class="p4-trava" data-radai-frase>exigida pelo protocolo próprio</span>';
 if(!base && proibida) h += '<span class="p4-trava" data-radai-frase>não permitida neste motor</span>';
 return h + _ajHTML('task', t.task, t.rotulo || t.task) + '</div>';
}
function painelPerso(i){
 var s = SERIES[i], e = escolhaDe(s), d = _opcDaSerie(s) || {};
 var on = tasksLigadas(s, e);
 var h = '<div class="p4" data-i="' + i + '">';

 var cats = {};
 (d.categorias || []).forEach(function(c){ cats[c.cod] = c.rotulo });
 h += '<section class="p4-col p4-prot" aria-labelledby="p4h_p_' + i + '">'
   + '<h4 id="p4h_p_' + i + '"><span data-radai-frase>' + esc(cats.rt || 'PROTOCOLOS RT')
   + '</span></h4><div>';
 var protos = d.protocolos || [];
 if(!protos.length)
  h += '<p class="p4-vazio" data-radai-frase>Nenhum protocolo nesta modalidade.</p>';
 protos.forEach(function(p){
  h += '<div class="p4-ln">'
    + _swHTML('p4-prot-ck', 'data-prot="' + esc(p.cod) + '"', !!e.prot[p.cod], false,
              p.rotulo || p.cod, true)
    + _ajHTML('prot', p.cod, p.rotulo || p.cod) + '</div>';
 });
 h += '</div>';
 var p3d = d.protocolos_3d || [];
 if(p3d.length){
  h += '<h4 class="p4-h3d" id="p4h_r_' + i + '"><span data-radai-frase>'
    + esc(cats.reconstrucoes_3d || 'PROTOCOLOS RECONSTRUÇÕES 3D') + '</span></h4>'
    + '<div role="group" aria-labelledby="p4h_r_' + i + '">';
  p3d.forEach(function(p){
   h += '<div class="p4-ln">'
     + _swHTML('p4-p3d-ck', 'data-p3d="' + esc(p.cod) + '"', !!(e.p3d || {})[p.cod], false,
               p.rotulo || p.cod, true)
     + _ajHTML('p3d', p.cod, p.rotulo || p.cod) + '</div>';
  });
  h += '</div>';
  if(protocolos3dLigados(s, e).length)
   h += '<p class="p4-rt3d" role="note" data-radai-frase>Com um protocolo das Reconstruções 3D ligado, o RTSTRUCT sai só com o que estiver ligado nas colunas de RT; as tasks do protocolo 3D vão só ao mapa de rótulos das Reconstruções 3D, e não ao RTSTRUCT.</p>';
 }
 h += '<div class="p4-ln p4-livre">'
   + _swHTML('p4-livre-ck', 'data-livre="1"', !!e.livre, false, 'Seleção livre', true)
   + _ajHTML('livre', 'livre', 'Seleção livre') + '</div>';
 var pps = d.protocolos_proprios || [], ppAt = _ppDaSerie(s, e);
 if(pps.length){
  h += '<h4 class="p4-h3d" id="p4h_pp_' + i + '"><span data-radai-frase>PROTOCOLO PRÓPRIO</span></h4>'
    + '<div class="p4-ln">'
    + _swHTML('p4-pp-ck', 'data-pp="1"', !!ppAt, false, 'Protocolo próprio', true)
    + _ajHTML('pp', 'pp', 'Protocolo próprio') + '</div>'
    + '<select class="p4-pp-sel" aria-labelledby="p4h_pp_' + i + '"' + (ppAt ? '' : ' disabled') + '>';
  pps.forEach(function(p){
   h += '<option value="' + esc(p.id) + '"' + (ppAt && ppAt.id === p.id ? ' selected' : '') + '>'
     + esc(p.nome) + (p.tem_achado ? (' · ' + esc(_nomeNaTela('ACHADO'))) : '') + '</option>';
  });
  h += '</select>';
  if(ppAt && ppAt.tem_achado)
   h += '<p class="p4-pp-nota" role="note"><span class="selo-achado">ACHADO</span> <span data-radai-frase>Este protocolo inclui detecção: ela é declarada a cada envio à fila.</span></p>';
 }
 h += '</section>';

 var trava = _travadasPeloPp(s, e);
 var dos = [], avulsas = [], achados = [];
 (d.tasks || []).forEach(function(t){
  (t.achado ? achados : ((t.protocolos || []).length ? dos : avulsas)).push(t);
 });
 h += '<section class="p4-col p4-tasks" aria-labelledby="p4h_t_' + i + '">'
   + '<h4 id="p4h_t_' + i + '"><span data-radai-frase>Tasks</span>'
   + '<span class="p4-n" id="p4n_' + i + '"></span></h4><div class="p4-rola">';
 if(d.base_item) h += '<div class="p4-grupo" data-radai-frase>base</div>'
                   + _linhaTask(d.base_item, true, true);
 if(dos.length){
  h += '<div class="p4-grupo" data-radai-frase>dos protocolos</div>';
  dos.forEach(function(t){ h += _linhaTask(t, !!on[t.task], false, !!trava[t.task]) });
 }
 if(avulsas.length){
  h += '<div class="p4-grupo" data-radai-frase>avulsas</div>';
  avulsas.forEach(function(t){ h += _linhaTask(t, !!on[t.task], false, !!trava[t.task]) });
 }
 if(achados.length){
  h += '<div class="p4-grupo achado" data-radai-frase>achado: só com a chave da própria task</div>';
  achados.forEach(function(t){ h += _linhaTask(t, !!on[t.task], false) });
 }
 h += '</div></section>';

 h += '<section class="p4-col p4-comp" aria-labelledby="p4h_c_' + i + '">'
   + '<h4 id="p4h_c_' + i + '"><span data-radai-frase>Comparação de modelos</span></h4><div>';
 (d.comparacao || []).forEach(function(c){
  var bloq = _compBloqueada(c);
  var motivo = (c.disponivel === false) ? 'só em TC'
             : ((c.instalado === false) ? 'não instalado' : '');
  h += '<div class="p4-ln">'
    + _swHTML('p4-comp-ck', 'data-comp="' + esc(c.cod) + '"', !bloq && !!e.comp[c.cod],
              bloq, c.rotulo || c.cod, true)
    + (motivo ? ('<span class="p4-trava" data-radai-frase>' + esc(motivo) + '</span>') : '')
    + _ajHTML('comp', c.cod, c.rotulo || c.cod) + '</div>';
 });
 h += '</div></section>';

 h += '<section class="p4-col p4-ent" aria-labelledby="p4h_e_' + i + '">'
   + '<h4 id="p4h_e_' + i + '"><span data-radai-frase>Entregas</span></h4>'
   + '<div class="p4-ent-corpo p4-rola ent-rola" id="p4e_' + i + '">'
   + '<div class="ui-esqueleto ui-esq-l"></div><div class="ui-esqueleto ui-esq-l"></div>'
   + '<div class="ui-esqueleto ui-esq-l"></div></div>'
   + '<p class="sr" id="p4v_' + i + '" aria-live="polite"></p></section>';
 return h + '</div>';
}
var P4_VISTO = {};
function _acertarPainel(i){
 var tr = el('perso_' + i);
 if(!_painelAberto(i)){
  if(tr && tr.parentNode) tr.parentNode.removeChild(tr);
  if(SERIES[i]) delete P4_VISTO[chaveDe(SERIES[i])];
  return;
 }
 var k = chaveDe(SERIES[i]), novo = !P4_VISTO[k];
 P4_VISTO[k] = true;
 if(!tr){
  var linha = el('linha_' + i);
  if(!linha || !linha.parentNode) return;
  tr = document.createElement('tr');
  tr.className = 'perso'; tr.id = 'perso_' + i;
  tr.setAttribute('data-i', String(i));
  var td = document.createElement('td'); td.colSpan = 10;
  tr.appendChild(td);
  linha.parentNode.insertBefore(tr, linha.nextSibling);
 }
 uiHTML(tr.firstChild, painelPerso(i));
 _larguraDoPainel();
 _acertarChaves(i);
 var ult = PREV_ULT[chaveDe(SERIES[i])];
 if(ult) _pintarEntregas(i, ult);
 if(novo && window.uiRevelar) window.uiRevelar(tr.querySelector('.p4'), true);
 try{ if(window.radaiRetraduzir) window.radaiRetraduzir() }catch(x){}
 pedirPrevia(i);
}
function _reporPaineis(){
 for(var i = 0; i < SERIES.length; i++) if(_painelAberto(i)) _acertarPainel(i);
}
function _acertarChaves(i){
 var tr = el('perso_' + i), s = SERIES[i];
 if(!tr || !s) return;
 var e = escolhaDe(s), on = tasksLigadas(s, e), n = 0, tot = 0;
 Array.prototype.forEach.call(tr.querySelectorAll('input.p4-task-ck'), function(x){
  if(x.disabled) return;
  x.checked = !!on[x.getAttribute('data-task')];
  tot++; if(x.checked) n++;
 });
 Array.prototype.forEach.call(tr.querySelectorAll('input.p4-prot-ck'), function(x){
  x.checked = !!e.prot[x.getAttribute('data-prot')];
 });
 Array.prototype.forEach.call(tr.querySelectorAll('input.p4-p3d-ck'), function(x){
  x.checked = !!(e.p3d || {})[x.getAttribute('data-p3d')];
 });
 Array.prototype.forEach.call(tr.querySelectorAll('input.p4-livre-ck'), function(x){
  x.checked = !!e.livre;
 });
 Array.prototype.forEach.call(tr.querySelectorAll('input.p4-pp-ck'), function(x){
  x.checked = !!e.pp;
 });
 var c = el('p4n_' + i);
 if(c) c.textContent = n + '/' + tot;
}

var PREV_T = {}, PREV_SEQ = {}, PREV_ULT = {};
function _indiceDaChave(k){
 for(var i = 0; i < SERIES.length; i++) if(chaveDe(SERIES[i]) === k) return i;
 return -1;
}
function pedirPrevia(i){
 var s = SERIES[i]; if(!s) return;
 var k = chaveDe(s);
 var alvo = el('p4e_' + i); if(alvo) alvo.classList.add('carregando');
 clearTimeout(PREV_T[k]);
 PREV_T[k] = setTimeout(function(){
  var seq = PREV_SEQ[k] = (PREV_SEQ[k] || 0) + 1;
  var j0 = _indiceDaChave(k); if(j0 < 0) return;
  fetch('/api/lote/previa_da_entrega', {method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({serie: payloadDaSerie(SERIES[j0])})})
  .then(function(r){ return r.json() }).then(function(d){
   if(PREV_SEQ[k] !== seq) return;
   PREV_ULT[k] = d;
   var j = _indiceDaChave(k); if(j >= 0) _pintarEntregas(j, d);
  }).catch(function(x){
   if(PREV_SEQ[k] !== seq) return;
   var j = _indiceDaChave(k); if(j >= 0) _pintarEntregas(j, {erro: String(x)});
  });
 }, 260);
}
function _condHTML(it){
 return (it.condicao ? '<span class="oar-cond" data-radai-frase>' + esc(it.condicao) + '</span>' : '')
  + (it.variante ? '<span class="oar-cond oar-var' + (it.pericardio === false ? ' sem' : '')
     + '" data-radai-frase>' + esc(it.variante) + '</span>' : '');
}
function _tagHTML(it, fora){
 var nome = esc(it.nome || it.chave);
 if(it.uniao)
  return '<span class="oar-tag uniao" role="listitem" title="' + esc((it.de || []).join(' + ')) + '">'
   + '<span class="oar-nome">' + nome + '</span></span>';
 if(fora){
  var rv = 'devolver %s ao STUDY'.replace('%s', it.nome || it.chave);
  return '<span class="oar-tag fora" role="listitem"><span class="oar-nome">' + nome + '</span>' + _condHTML(it)
   + '<button type="button" class="oar-volta" data-oar-volta="' + esc(it.chave) + '"'
   + ' aria-label="' + esc(rv) + '" title="' + esc(rv) + '">+</button></span>';
 }
 var rx = 'tirar %s do STUDY desta série'.replace('%s', it.nome || it.chave);
 return '<span class="oar-tag" role="listitem"><span class="oar-nome">' + nome + '</span>' + _condHTML(it)
   + '<button type="button" class="oar-x" data-oar-x="' + esc(it.chave) + '"'
   + ' aria-label="' + esc(rx) + '" title="' + esc(rx) + '">&times;</button></span>';
}
function _porNome(a, b){
 var x = String(a.nome || a.chave).toLowerCase(), y = String(b.nome || b.chave).toLowerCase();
 return x < y ? -1 : (x > y ? 1 : 0);
}
function _pintarEntregas(i, d, focar){
 var alvo = el('p4e_' + i); if(!alvo) return;
 var at = document.activeElement, foco = focar || null;
 if(!foco && at && alvo.contains(at)){
  foco = at.getAttribute('data-oar-x') ? ['data-oar-x', at.getAttribute('data-oar-x')]
       : (at.getAttribute('data-oar-volta') ? ['data-oar-volta', at.getAttribute('data-oar-volta')] : null);
 }
 alvo.classList.remove('carregando');
 if(!d || d.erro){
  uiHTML(alvo, '<p class="ent-erro">' + esc('ERRO: ' + ((d && d.erro) || '')) + '</p>');
  return;
 }
 var h = '<ul class="ent-arqs">';
 (d.arquivos || []).forEach(function(a){
  h += '<li class="ent-arq' + (a.entregue ? ' entregue' : '') + '">'
     + '<span class="ent-rot">' + esc(a.nome || a.cod) + '</span>'
     + '<code class="ent-nome">' + esc(a.arquivo || '') + '</code></li>';
 });
 h += '</ul>';
 var oar = d.oar || {};
 var ests = (oar.estruturas || []).slice().sort(_porNome);
 var fora = (oar.fora || []).slice().sort(_porNome);
 h += '<div class="ent-sub"><b>' + ests.length + '</b> <span data-radai-frase>estruturas no STUDY desta série</span></div>'
    + '<div class="oar-tags" role="list">' + ests.map(function(x){ return _tagHTML(x, false) }).join('') + '</div>';
 if(fora.length)
  h += '<div class="ent-sub"><b>' + fora.length + '</b> <span data-radai-frase>fora do STUDY desta série (continuam no FULL)</span></div>'
     + '<div class="oar-tags" role="list">' + fora.map(function(x){ return _tagHTML(x, true) }).join('') + '</div>';
 if(d.nota) h += '<p class="ent-nota" data-radai-frase>' + esc(d.nota) + '</p>';
 uiHTML(alvo, h);
 var viva = el('p4v_' + i);
 if(viva){
  var fv = '%s estruturas no STUDY, %s fora'.replace('%s', ests.length)
            .replace('%s', fora.length);
  if(window.uiTexto) window.uiTexto(viva, fv); else viva.textContent = fv;
 }
 if(foco){
  var b = alvo.querySelector('[' + foco[0] + '="' + foco[1] + '"]')
       || (foco[2] != null ? alvo.querySelectorAll('[data-oar-x]')[foco[2]] : null)
       || alvo.querySelector('[data-oar-x]') || alvo.querySelector('[data-oar-volta]');
  if(b){ try{ b.focus({preventScroll: true}) }catch(x){ b.focus() } }
 }
 try{ if(window.radaiRetraduzir) window.radaiRetraduzir() }catch(x){}
}
function _tirarDoOar(bt, tirar){
 var cx = bt.closest('.p4'); if(!cx) return;
 var i = parseInt(cx.getAttribute('data-i'), 10), s = SERIES[i]; if(!s) return;
 var e = escolhaDe(s), k = bt.getAttribute(tirar ? 'data-oar-x' : 'data-oar-volta');
 var lista = Array.prototype.slice.call(cx.querySelectorAll(tirar ? '[data-oar-x]' : '[data-oar-volta]'));
 var pos = lista.indexOf(bt);
 if(tirar) e.oar_fora[k] = true; else delete e.oar_fora[k];
 var ult = PREV_ULT[chaveDe(s)];
 if(ult && ult.oar){
  var d = JSON.parse(JSON.stringify(ult)), de = tirar ? 'estruturas' : 'fora',
      para = tirar ? 'fora' : 'estruturas', it = null;
  d.oar[de] = (d.oar[de] || []).filter(function(x){ if(x.chave === k){ it = x; return false } return true });
  if(it) (d.oar[para] = d.oar[para] || []).push(it);
  PREV_ULT[chaveDe(s)] = d;
  _pintarEntregas(i, d, tirar ? ['data-oar-x', '', Math.max(0, Math.min(pos, lista.length - 2))]
                             : ['data-oar-x', k]);
 }
 pedirPrevia(i);
 pintarCarrinho();
}

function _chipsHTML(nomes){
 return '<div class="tk-est">' + (nomes || []).map(function(n){
  return '<span>' + esc(n) + '</span>' }).join('') + '</div>';
}
function _fichaHTML(t){
 var h = '<div class="tk-b"><div class="tk-cod">' + esc(t.task)
   + ((t.datasets || []).length ? (' · Dataset' + esc(t.datasets[0])) : '') + '</div>';
 if(t.por_que_travada)
  h += '<p class="tk-trava" data-f="trava" data-radai-frase>' + esc(t.por_que_travada) + '</p>';
 var avisos = (t.avisos || []).slice();
 if(t.permitida === false) avisos.unshift('não permitida neste motor' + (t.porque_nao ? (': ' + t.porque_nao) : ''));
 else if(t.disponivel === false && t.porque_nao) avisos.push(t.porque_nao);
 if(avisos.length)
  h += '<div class="tk-avisos" data-f="avisos">' + avisos.map(function(a){
   return '<div data-radai-frase>' + esc(a) + '</div>' }).join('') + '</div>';
 var sv = _seloVel(t);
 if(sv) h += '<div class="tk-l" data-f="tempo"><span class="tk-k" data-radai-frase>tempo</span>'
          + '<span class="tk-v">' + sv.outerHTML + '</span></div>';
 if(t.alimenta)
  h += '<div class="tk-l" data-f="alimenta"><span class="tk-k" data-radai-frase>alimenta</span>'
     + '<span class="tk-v">' + (t.alimenta === 'full' ? 'FULL'
        : ('<span data-radai-frase>arquivo próprio</span> · ' + esc(t.arquivo || ''))) + '</span></div>';
 var m = t.modelo || {};
 if(m.nome)
  h += '<div class="tk-l" data-f="modelo"><span class="tk-k" data-radai-frase>modelo de origem</span>'
     + '<span class="tk-v">' + esc(m.nome) + '</span></div>'
     + '<div class="tk-l" data-f="versao"><span class="tk-k" data-radai-frase>versão</span>'
     + '<span class="tk-v">' + esc(m.versao || '—') + '</span></div>'
     + '<div class="tk-l" data-f="task"><span class="tk-k" data-radai-frase>task na biblioteca</span>'
     + '<span class="tk-v">' + esc(m.task || t.task) + '</span></div>';
 h += '<div class="tk-sec" data-f="segmenta"><span class="tk-k" data-radai-frase>o que segmenta</span>'
    + ((t.estruturas || []).length ? _chipsHTML(t.estruturas)
       : '<div class="tk-vazio" data-radai-frase>a lista sai da biblioteca instalada na estação</div>')
    + '</div>';
 var resto = (t.ficha || []).filter(function(r){ return r.rot !== 'modelo' });
 if(resto.length){
  var fc = _fichaCorpo({task: t.task, ficha: resto}), cod = fc.querySelector('.tk-cod');
  if(cod) fc.removeChild(cod);
  h += '<div class="tk-sep" data-radai-frase>ficha técnica</div>' + fc.innerHTML;
 }
 return h + '</div>';
}
function _ajudaDoPainel(q){
 var cx = q.closest('.p4'); if(!cx) return;
 var s = SERIES[parseInt(cx.getAttribute('data-i'), 10)]; if(!s) return;
 var d = _opcDaSerie(s) || {}, tipo = q.getAttribute('data-p4-aj'), cod = q.getAttribute('data-cod');
 if(tipo === 'task'){
  var t = (d.base_item && d.base_item.task === cod) ? d.base_item : _porTask(d)[cod];
  if(t) perguntar({titulo: t.rotulo || t.task, html: _fichaHTML(t), ok: 'Fechar', so_ok: true});
  return;
 }
 if(tipo === 'prot'){
  var p = null; (d.protocolos || []).forEach(function(x){ if(x.cod === cod) p = x });
  if(!p) return;
  var por = _porTask(d), nomes = (p.tasks || []).concat(p.motores || []).map(function(x){
   return (por[x] && por[x].rotulo) || x });
  perguntar({titulo: p.rotulo || p.cod, ok: 'Fechar', so_ok: true,
   html: '<div class="tk-b">' + (p.ajuda ? ('<p data-radai-frase>' + esc(p.ajuda) + '</p>') : '')
    + '<div class="tk-sec"><span class="tk-k" data-radai-frase>ligar este protocolo liga</span>'
    + _chipsHTML(nomes) + '</div></div>'});
  return;
 }
 if(tipo === 'p3d'){
  var q3 = null; (d.protocolos_3d || []).forEach(function(x){ if(x.cod === cod) q3 = x });
  if(!q3) return;
  perguntar({titulo: q3.rotulo || q3.cod, ok: 'Fechar', so_ok: true,
   html: '<div class="tk-b">' + (q3.ajuda ? ('<p data-radai-frase>' + esc(q3.ajuda) + '</p>') : '')
    + '</div>'});
  return;
 }
 if(tipo === 'livre'){
  perguntar({titulo: 'Seleção livre', ok: 'Fechar', so_ok: true,
   html: '<div class="tk-b"><p data-radai-frase>Cada protocolo liga só as tasks dele e desliga o resto. Mexer à mão numa task desliga o protocolo e liga a Seleção livre: daí em diante vale o que estiver marcado.</p></div>'});
  return;
 }
 if(tipo === 'pp'){
  perguntar({titulo: 'Protocolo próprio', ok: 'Fechar', so_ok: true,
   html: '<div class="tk-b"><p data-radai-frase>O protocolo próprio é a seleção de estruturas do STUDY que a estação montou em Configurações, Estruturas e Protocolos, com as uniões e os nomes próprios dela.</p>'
    + '<p data-radai-frase>Ligar a chave desliga os protocolos RT e a Seleção livre; as tasks que as estruturas do protocolo exigem ficam ligadas e travadas. O FULL não muda.</p></div>'});
  return;
 }
 if(tipo === 'comp'){
  var c = null; (d.comparacao || []).forEach(function(x){ if(x.cod === cod) c = x });
  if(!c) return;
  var h = '<div class="tk-b">';
  var av = [];
  if(c.disponivel === false && c.porque_nao) av.push(c.porque_nao);
  if(c.instalado === false) av.push('não instalado');
  if(av.length) h += '<div class="tk-avisos">' + av.map(function(a){
   return '<div data-radai-frase>' + esc(a) + '</div>' }).join('') + '</div>';
  if(c.ajuda) String(c.ajuda).split('\\n').forEach(function(l){
   if(l) h += '<p data-radai-frase>' + esc(l) + '</p>' });
  h += '<p data-radai-frase>Cada modelo grava um arquivo próprio; nenhum entra no RadAI_STUDY.</p>';
  if(c.licenca) h += '<div class="tk-l"><span class="tk-k" data-radai-frase>licença</span>'
                  + '<span class="tk-v">' + esc(c.licenca) + '</span></div>';
  perguntar({titulo: c.rotulo || c.cod, html: h + '</div>', ok: 'Fechar', so_ok: true});
 }
}

document.addEventListener('change', function(ev){
 var t = ev.target; if(!t || !t.classList) return;
 if(t.classList.contains('md-sel')){ _mudouModo(t); return }
 var cx = t.closest && t.closest('.p4'); if(!cx) return;
 var i = parseInt(cx.getAttribute('data-i'), 10), s = SERIES[i];
 if(!s) return;
 var e = escolhaDe(s);
 if(t.classList.contains('p4-p3d-ck')){
  ligarProtocolo3d(s, e, t.getAttribute('data-p3d'), t.checked);
  _acertarPainel(i); pedirPrevia(i); pintarCarrinho(); return;
 }
 if(t.classList.contains('p4-pp-ck') || t.classList.contains('p4-pp-sel')){
  var selPp = cx.querySelector('select.p4-pp-sel');
  if(t.classList.contains('p4-pp-ck')) ligarProtocoloProprio(s, e, t.checked, selPp ? selPp.value : '');
  else if(e.pp) ligarProtocoloProprio(s, e, true, t.value);
  _acertarPainel(i); pedirPrevia(i); pintarCarrinho(); return;
 }
 var tinhaPp = !!e.pp;
 if(t.classList.contains('p4-prot-ck')) ligarProtocolo(s, e, t.getAttribute('data-prot'), t.checked);
 else if(t.classList.contains('p4-livre-ck')) ligarSelecaoLivre(s, e, t.checked);
 else if(t.classList.contains('p4-task-ck')) chaveDaTask(s, e, t.getAttribute('data-task'), t.checked);
 else if(t.classList.contains('p4-comp-ck')) e.comp[t.getAttribute('data-comp')] = t.checked ? 1 : 0;
 else return;
 if(tinhaPp !== !!e.pp){ _acertarPainel(i); pedirPrevia(i); pintarCarrinho(); return }
 _acertarChaves(i);
 pedirPrevia(i);
 pintarCarrinho();
});
document.addEventListener('click', function(ev){
 var t = ev.target; if(!t || !t.closest) return;
 var aj = t.closest('[data-md-aj]');
 if(aj){ ev.preventDefault(); balaoDosModos(aj); return }
 var x = t.closest('[data-oar-x]');
 if(x){ ev.preventDefault(); _tirarDoOar(x, true); return }
 var v = t.closest('[data-oar-volta]');
 if(v){ ev.preventDefault(); _tirarDoOar(v, false); return }
 var q = t.closest('[data-p4-aj]');
 if(q){ ev.preventDefault(); _ajudaDoPainel(q); return }
 if(!t.closest('#md_balao')) fecharBalaoDosModos(false);
});

function _fichaCorpo(t){
 var b=document.createElement('div'); b.className='tk-b';
 var c=document.createElement('div'); c.className='tk-cod';
 c.textContent=t.task; b.appendChild(c);
 (t.ficha||[]).forEach(function(r){
  var li=document.createElement('div'); li.className='tk-l';
  var k=document.createElement('span'); k.className='tk-k';
  k.setAttribute('data-radai-frase',''); k.textContent=r.rot;
  var v=document.createElement('span'); v.className='tk-v';
  if(r.frase) v.setAttribute('data-radai-frase','');
  var val = (r.val === null || r.val === undefined) ? '' : String(r.val);
  if(r.rot === 'velocidade' && val.charAt(0) === '~'){
   v.appendChild(document.createTextNode('~'));
   var vt=document.createElement('span'); vt.textContent=val.slice(1);
   v.appendChild(vt);
  } else {
   v.textContent=val;
  }
  li.appendChild(k); li.appendChild(v); b.appendChild(li);
 });
 return b;
}

function _seloVel(t){
 if(!t || !t.velocidade) return null;
 var s=document.createElement('span');
 s.className='selo-vel ' + t.velocidade + (t.velocidade_medida ? '' : ' estimada');
 var rot = String(t.velocidade_rotulo || t.velocidade);
 if(rot.charAt(0) === '~'){ s.appendChild(document.createTextNode('~')); rot = rot.slice(1) }
 var tg=document.createElement('span'); tg.textContent = rot; s.appendChild(tg);
 var de = '';
 (t.ficha||[]).forEach(function(r){
  if(r.rot === 'de onde vem a velocidade') de = r.val });
 if(!de && t.velocidade_fonte) de = t.velocidade_fonte;
 s.title = de || (t.velocidade_medida ? 'medida contra a base, na mesma série e na mesma máquina'
                                      : 'estimada pela forma do modelo; não medida');
 return s;
}

carregarOpcoes();
</script></div></body></html>"""


FRASE_DA_TELA = (u"Utilize esta ferramenta de segmentação para iniciar os "
                 u"estudos dentro do aplicativo (alimenta os módulos de "
                 u"comparação de segmentações e de reconstruções 3D).")
AJUDA_DA_TELA = (
    u"Escolha uma pasta (ou o .zip do exame), marque as séries e o modo de "
    u"cada uma, e adicione à fila. Quem inicia, pausa e cancela é a barra "
    u"à direita.",
    u"O RTSTRUCT é gravado na pasta de cada série, ao lado dos DICOMs — ele "
    u"acompanha a pasta quando ela é copiada ou importada.",
)
ALERTA_DA_TELA = (u"Material de estudo — <b>100% local</b>. Nenhuma imagem "
                  u"sai desta rede")
def _cabeca_da_tela():
    import radai_ui
    return radai_ui.cabeca_de_funcao(
        radai_ui.icone(u"rodar"), u"Rodar agora", FRASE_DA_TELA,
        radai_ui.ajuda(*AJUDA_DA_TELA), u"autocontorno")


def _alerta_da_tela():
    import radai_ui
    return radai_ui.alerta(ALERTA_DA_TELA)


def tag_da_fronteira(ident=u""):
    import radai_review
    return radai_review.tag_da_fronteira(ident)


ESCOLHA_HTML = u"""<div id="lt_form">
 <label class="cam-rot" for="pasta">Caminho — pasta, ou o <b>.zip</b> do exame</label>
 <div class="linha cam-linha">
  <input id="pasta" autofocus spellcheck="false" placeholder="C:\\...  ou  \\\\servidor\\share\\...  ou  C:\\...\\EXAME.zip">
  @FAV@
  <button id="lt_procurar" onclick="ltProcurar(this)">Procurar…</button>
  <button class="pri" onclick="varrer()">Varrer séries</button>
 </div>
 <div class="lt-filtro">@FILTRO@</div>
 <div id="msg" role="status"></div>
 <div id="lt_fora" class="lt-fora"></div>
 <div id="fpFora" class="fora-nota" style="display:none"></div>
</div>
<div id="lt_ler" hidden>
 <div id="lt_ler_cx"></div>
 <p class="lt-dica" data-radai-frase>Varrendo a pasta: o cabeçalho de cada arquivo é lido, e uma pasta grande pode levar alguns minutos.</p>
 <div class="lt-ler-bts"><button type="button" id="lt_parar" onclick="ltParar()">Parar a leitura</button></div>
</div>
"""


def _escolha():
    import radai_ui
    corpo = (ESCOLHA_HTML.replace(u"@FAV@", radai_ui.botao_favorita(u"pasta"))
             .replace(u"@FILTRO@", radai_ui.filtro_de_data(u"lt_dias")))
    return radai_ui.popup_de_serie(u"cx1", corpo, titulo=u"Carregar imagens",
                                   sozinho=True, largura=860)


def _pagina():
    css, js = u"", u""
    try:
        import radai_viewer
        css, js = radai_viewer.CSS, radai_viewer.JS
    except Exception:
        pass
    return (PAGINA.replace("@VISORCSS@", css)
                  .replace("@VISORJS@", js)
                  .replace("@CABECA@", _cabeca_da_tela())
                  .replace("@ALERTA@", _alerta_da_tela())
                  .replace("@FOLHA_TURNO@", _corpo_da_folha_do_turno())
                  .replace("@ESCOLHA@", _escolha()))


def sentido_do_bilhete(b):
    import radai_thumbnail
    return radai_thumbnail.sentido_cranial(radai_thumbnail.serie_do_bilhete(b))


def _com_bilhete(series):
    try:
        import radai_thumbnail
    except Exception:
        return series
    for s in series or ():
        try:
            if s.get("pasta") and s.get("uid"):
                s["b"] = radai_thumbnail.bilhete(s["pasta"], s["uid"])
        except Exception:
            pass
    return series


def series_da_selecao(pedidas, encontradas):
    fora, vistos = [], set()
    for p in pedidas or ():
        uid = str((p or {}).get("uid") or "")
        pasta = os.path.normcase(os.path.abspath(str((p or {}).get("pasta") or "")))
        for s in encontradas or ():
            if str(s.get("uid") or "") != uid or uid in vistos:
                continue
            sp = os.path.normcase(os.path.abspath(str(s.get("pasta") or "")))
            if sp == pasta or sp.startswith(pasta + os.sep) \
                    or pasta.startswith(sp + os.sep):
                fora.append(s)
                vistos.add(uid)
                break
    return fora


def normalizar_selecao(corpo):
    fora, vistos = [], set()
    for s in ((corpo or {}).get("series") or [])[:TETO_SELECAO]:
        if not isinstance(s, dict):
            continue
        pasta = str(s.get("pasta") or "").strip().strip('"')
        uid = str(s.get("uid") or "").strip()
        if not pasta or not uid or (pasta, uid) in vistos:
            continue
        vistos.add((pasta, uid))
        fora.append({"pasta": pasta, "uid": uid})
    return fora


TETO_SELECAO = 200
JANELAS_DO_VISOR = ("mediastino", "pulmao", "osso", "cerebro", "auto")


def _no_threadpool(fn, *a, **kw):
    from starlette.concurrency import run_in_threadpool
    return run_in_threadpool(fn, *a, **kw)


AVISO_SEM_STATUS_DIR = (u"Sem STATUS_DIR em Configurações, cada estação só "
                        u"enxerga a si mesma. Combine uma pasta comum com o "
                        u"TI para ver a noite inteira numa tela.")


def _corpo_da_folha_do_turno():
    import radai_ui
    campos = (
        u'<div class="ov-campo">'
        u'<label class="ov-rot" for="ov_root" data-radai-frase>Pasta que o '
        u'turno varre</label>'
        u'<div id="ov_roots"><div class="ov-root"><input id="ov_root" data-ov-root="1" spellcheck="false" '
        u'autocomplete="off" aria-describedby="ov_root_laudo">'
        + radai_ui.botao_favorita(u"ov_root") +
        u'<button type="button" class="ui-bt" id="ov_root_bt" '
        u'aria-haspopup="dialog">Procurar…</button>'
        u'</div></div>'
        u'<button type="button" class="ui-bt" id="ov_root_add" '
        u'aria-label="Adicionar pasta">+</button>'
        u'<div class="ov-laudo" id="ov_root_laudo" role="status" '
        u'aria-live="polite"></div>'
        u'</div>'
        u'<div class="ov-dois">'
        u'<div class="ov-campo">'
        u'<span class="ov-rot" id="ov_mod_rot" data-radai-frase>Modalidades'
        u'</span>'
        u'<div class="ov-seg" id="ov_mod" role="radiogroup" '
        u'aria-labelledby="ov_mod_rot">'
        u'<button type="button" role="radio" data-ov-mod="CT" '
        u'aria-checked="true">TC</button>'
        u'<button type="button" role="radio" data-ov-mod="MR" '
        u'aria-checked="false" tabindex="-1">RM</button>'
        u'<button type="button" role="radio" data-ov-mod="CT,MR" '
        u'aria-checked="false" tabindex="-1">TC e RM</button>'
        u'</div></div>'
        u'<div class="ov-campo">'
        u'<label class="ov-rot" for="ov_dias" data-radai-frase>Dias para '
        u'trás</label>'
        u'<div class="ov-num">'
        u'<button type="button" class="ui-bt" data-ov-dias="-1" '
        u'aria-label="menos um dia">&#8722;</button>'
        u'<input id="ov_dias" type="number" min="0" max="3650" step="1" '
        u'inputmode="numeric" value="0">'
        u'<button type="button" class="ui-bt" data-ov-dias="1" '
        u'aria-label="mais um dia">+</button></div>'
        u'<span class="ov-dica" data-radai-frase>0 = todo o histórico, pela '
        u'data da série</span>'
        u'</div></div>')
    return (
        u'<template id="ov_folha_corpo"><div class="ov-form">'
        u'<p data-radai-frase>O turno entra como <b>último card da fila</b>. '
        u'Quando ela chegar nele, esta estação passa a varrer sozinha e a '
        u'pegar o caso mais recente primeiro.</p>'
        u'%(campos)s'
        u'<p class="ov-frota-aviso" id="ov_frota_aviso" hidden '
        u'data-radai-frase>%(frota)s</p>'
        u'<div class="ov-frota" id="ov_frota"></div>'
        u'%(fronteira)s'
        u'</div></template>'
        % {"campos": campos,
           "frota": AVISO_SEM_STATUS_DIR,
           "fronteira": tag_da_fronteira()})


TETO_PASTAS = 1500
_UNIDADES = {"quando": 0.0, "lista": []}
_TRAVA_UNIDADES = threading.Lock()

_TIPO_DE_UNIDADE = {2: "removivel", 3: "fixa", 4: "rede", 5: "optica",
                    6: "ram"}


def _letras_montadas():
    try:
        import ctypes
        mapa = int(ctypes.windll.kernel32.GetLogicalDrives())
        return [chr(65 + i) for i in range(26) if mapa & (1 << i)]
    except Exception:
        return [chr(65 + i) for i in range(26)]


def _tipo_da_unidade(raiz):
    try:
        import ctypes
        return _TIPO_DE_UNIDADE.get(
            int(ctypes.windll.kernel32.GetDriveTypeW(str(raiz))), "")
    except Exception:
        return ""


def unidades_do_explorador(teto_s=1.5, validade_s=20.0):
    if os.name != "nt":
        return [{"raiz": "/", "tipo": "fixa", "ok": True}]
    agora = time.time()
    with _TRAVA_UNIDADES:
        if _UNIDADES["lista"] and agora - _UNIDADES["quando"] < validade_s:
            return [dict(u) for u in _UNIDADES["lista"]]
    raizes = ["%s:\\" % l for l in _letras_montadas()]
    achou = {}

    def _sondar(r):
        try:
            achou[r] = bool(os.path.exists(r))
        except Exception:
            achou[r] = False

    fios = []
    for r in raizes:
        t = threading.Thread(target=_sondar, args=(r,), daemon=True)
        t.start()
        fios.append((r, t))
    prazo = agora + float(teto_s)
    for r, t in fios:
        t.join(max(0.0, prazo - time.time()))
    fora = []
    for r in raizes:
        ok = achou.get(r)
        tipo = _tipo_da_unidade(r)
        if r[0] in "AB" and ok is not True:
            continue
        if ok is False and tipo not in ("rede", "removivel", "optica"):
            continue
        fora.append({"raiz": r, "tipo": tipo, "ok": ok})
    with _TRAVA_UNIDADES:
        _UNIDADES["quando"] = time.time()
        _UNIDADES["lista"] = [dict(u) for u in fora]
    return fora


def _sem_acento(s):
    import unicodedata
    return u"".join(c for c in unicodedata.normalize("NFD", str(s or "").lower())
                    if unicodedata.category(c) != "Mn")


_OCULTAS = frozenset(("$recycle.bin", "system volume information",
                      "$windows.~bt", "$windows.~ws", "$sysreset"))


def listar_pastas_do_explorador(caminho="", busca="", ordem="nome",
                                sentido="asc", teto=TETO_PASTAS, teto_s=8.0):
    ordem = "data" if str(ordem or "").lower() == "data" else "nome"
    sentido = "desc" if str(sentido or "").lower() == "desc" else "asc"
    r = {"caminho": "", "pai": "", "pastas": [], "erro": "", "busca": "",
         "achados": -1, "total": 0, "ordem": ordem, "sentido": sentido,
         "mostrando": 0, "dica": ""}
    bruto = str(caminho or "").strip().strip('"')
    if not bruto:
        return r
    resultado = {}

    def _listar():
        try:
            if not os.path.isdir(bruto):
                resultado["erro"] = u"não é uma pasta acessível desta máquina"
                return
            itens = []
            for e in os.scandir(bruto):
                try:
                    if not e.is_dir():
                        continue
                    if e.name.lower() in _OCULTAS:
                        continue
                    try:
                        mt = float(e.stat().st_mtime)
                    except Exception:
                        mt = None
                    itens.append((e.name, mt))
                except Exception:
                    continue
            resultado["itens"] = itens
        except PermissionError:
            resultado["erro"] = u"sem permissão para listar esta pasta"
        except Exception as e:
            resultado["erro"] = u"a pasta não pôde ser listada"
            resultado["tipo"] = type(e).__name__

    t = threading.Thread(target=_listar, daemon=True)
    t.start()
    t.join(float(teto_s))
    if t.is_alive():
        r["erro"] = (u"a pasta não respondeu a tempo — share fora do ar ou "
                     u"unidade de rede desconectada")
        return r
    if resultado.get("erro"):
        r["erro"] = resultado["erro"]
        if resultado.get("tipo"):
            r["tipo"] = resultado["tipo"]
        return r
    r["caminho"] = os.path.abspath(bruto)
    pai = os.path.dirname(r["caminho"])
    if pai and os.path.abspath(pai) != r["caminho"]:
        r["pai"] = pai
    itens = list(resultado.get("itens") or [])
    termo = _sem_acento(busca).strip()
    if termo:
        itens = [x for x in itens if termo in _sem_acento(x[0])]
        r["busca"] = str(busca or "").strip()
        r["achados"] = len(itens)
    if ordem == "data":
        com = sorted([x for x in itens if x[1] is not None],
                     key=lambda x: x[1], reverse=(sentido == "desc"))
        itens = com + sorted([x for x in itens if x[1] is None],
                             key=lambda x: x[0].lower())
    else:
        itens.sort(key=lambda x: x[0].lower(), reverse=(sentido == "desc"))
    r["total"] = len(itens)
    for nome, mt in itens[:int(teto)]:
        r["pastas"].append({
            "nome": nome, "caminho": os.path.join(r["caminho"], nome),
            "data": (datetime.fromtimestamp(mt).strftime("%Y-%m-%d %H:%M")
                     if mt is not None else u"")})
    if len(itens) > int(teto):
        r["mostrando"] = int(teto)
        r["dica"] = (u"refine a busca" if termo else
                     u"use a busca ou a ordem por data")
    return r


def conferencia_das_series(series, lista_explicita=None):
    md = _md()
    tasks, mot = [], dict((m, False) for m in MOTORES_DO_LOTE)
    mot["ts"] = False
    modos, problemas = {}, []
    for s in series or ():
        u8 = str((s or {}).get("uid") or "")[-8:]
        try:
            _so_estudo = set(tasks_so_do_estudo(s))
            for t in tasks_previstas(s, lista_explicita):
                if t not in tasks and t not in _so_estudo:
                    tasks.append(t)
        except Exception as e:
            problemas.append({"uid8": u8, "o_que": "tasks",
                              "erro": "%s: %s" % (type(e).__name__,
                                                  str(e)[:160])})
        try:
            m, _ = motores_da_serie(s)
            for k in mot:
                mot[k] = mot[k] or bool(m.get(k))
        except Exception as e:
            problemas.append({"uid8": u8, "o_que": "motores",
                              "erro": "%s: %s" % (type(e).__name__,
                                                  str(e)[:160])})
        if quem_decide_as_tasks(lista_explicita, s) == "lista":
            modos[""] = modos.get("", 0) + 1
            continue
        e = escolha_da_serie(s)
        modos[e["modo"]] = modos.get(e["modo"], 0) + 1
        if e["modo"] == md.MODO_AUTO and e["modalidade"] == "CT":
            mot["hnlnl"] = True
        if e["modo"] == md.MODO_PERSO:
            if (e.get("comparacao") or {}).get("ts"):
                mot["ts"] = True
            for p in (e["protocolos"] or ()):
                k = u"perso:%s" % p
                modos[k] = modos.get(k, 0) + 1
            for p in (e.get("protocolos_3d") or ()):
                k = u"perso3d:%s" % p
                modos[k] = modos.get(k, 0) + 1
    return tasks, mot, modos, problemas


def montar(app, opcoes=None):
    from fastapi import Request
    from fastapi.responses import HTMLResponse

    cfg = dict(opcoes or {})
    _CFG.clear()
    _CFG.update(cfg)

    def _erro(e):
        return {"erro": "%s: %s" % (type(e).__name__, str(e)[:300])}

    @app.get("/lote", response_class=HTMLResponse)
    def _tela():
        pag = radai_menu.aplicar(_pagina(), "lote")
        try:
            import radai_review
            pag = radai_review.aplicar(pag)
        except Exception:
            pass
        return pag

    async def _varredura(alvo):
        try:
            if alvo.lower().endswith(".zip") and os.path.isfile(alvo):
                alvo, erro = await _no_threadpool(preparar_zip, alvo)
                if erro:
                    return {"series": [], "erro": erro}
            piso = int(cfg.get("min_cortes", 20))
            curtas = []
            series = await _no_threadpool(
                varrer, alvo, modalidades=MODALIDADES_DA_TELA, min_cortes=piso,
                marcadores=cfg.get("marcadores"), incluir_zips=True,
                descartadas=curtas)
            return completar_da_tela(series, alvo, piso, curtas)
        except Exception as e:
            return _erro(e)

    try:
        import radai_varrer
        uso_lote = radai_varrer.registrar("lote", _lote_ler, _lote_linhas,
                                         fechar=_lote_fechar, iniciar=_lote_iniciar,
                                         pular=pulada_no_lote)
        uso_lote.paralela = True
    except Exception as e:
        if callable(cfg.get("log")):
            cfg["log"](u"a varredura em segundo plano do Rodar agora nao "
                       u"subiu: %s: %s" % (type(e).__name__, e))

    @app.post("/api/lote/selecao")
    async def _selecao(request: Request):
        try:
            c = await request.json() or {}
        except Exception:
            c = {}
        series = normalizar_selecao(c)
        if not series:
            return {"ok": False, "erro": u"nenhuma série na seleção"}
        import radai_fichas
        return {"ok": True, "ficha": radai_fichas.guardar(
            {"tipo": "lote_selecao", "series": series}), "n": len(series)}

    @app.post("/api/lote/selecao/abrir")
    async def _selecao_abrir(request: Request):
        try:
            c = await request.json() or {}
        except Exception:
            c = {}
        import radai_fichas
        d = radai_fichas.ler(str((c or {}).get("ficha") or ""))
        if not isinstance(d, dict) or d.get("tipo") != "lote_selecao":
            return {"ok": False, "series": [],
                    "erro": u"a seleção não está mais disponível — escolha "
                            u"as séries de novo no DicomBridge"}
        pedidas = d.get("series") or []
        achadas, pastas, erros = [], [], []
        for p in pedidas:
            if p["pasta"] not in pastas:
                pastas.append(p["pasta"])
        for pasta in pastas:
            r = await _varredura(pasta)
            if r.get("erro"):
                erros.append(r["erro"])
            achadas.extend(r.get("series") or [])
        series = series_da_selecao(pedidas, achadas)
        fora = {"ok": True, "series": series, "pedidas": len(pedidas),
                "pasta": pastas[0] if len(pastas) == 1 else u""}
        if len(series) < len(pedidas):
            fora["aviso"] = u"%s série(s) da seleção não foram achadas" \
                % (len(pedidas) - len(series))
        if erros and not series:
            fora["erro"] = erros[0]
        return fora

    @app.api_route("/api/lote/miniatura", methods=["GET", "HEAD"])
    def _miniatura(b: str = ""):
        from fastapi.responses import Response
        import radai_thumbnail
        try:
            dados, info = radai_thumbnail.png_central(b)
        except Exception:
            return Response(status_code=500)
        if not dados:
            return Response(status_code=204 if info.get("sem_imagem") else 404)
        return Response(content=dados, media_type="image/png", headers={
            "Cache-Control": "private, max-age=86400",
            "X-RadAI-Cortes": str(info.get("cortes", 0))})

    @app.post("/api/lote/sentido")
    async def _sentido_do_visor(request: Request):
        try:
            c = await request.json() or {}
        except Exception:
            c = {}
        b = str((c or {}).get("b") or "")
        try:
            return {"cranial": await radai_web.no_threadpool(
                sentido_do_bilhete, b)}
        except Exception as e:
            import radai_thumbnail
            radai_thumbnail.registrar_falha(u"Rodar agora, sentido do visor",
                                            e, bilhete=b)
            return {"cranial": 0}

    @app.get("/api/lote/corte")
    def _corte_do_visor(b: str = "", corte: int = 0, janela: str = "mediastino"):
        from fastapi.responses import Response
        import radai_thumbnail
        if janela not in JANELAS_DO_VISOR:
            janela = "mediastino"
        try:
            dados, info = radai_thumbnail.png(
                b, corte, janela, lado=radai_thumbnail.LADO_VISOR)
        except Exception as e:
            radai_thumbnail.registrar_falha(u"Rodar agora, visor da série", e,
                                            bilhete=b)
            return Response(status_code=500)
        if not dados:
            return Response(status_code=204 if info.get("sem_imagem") else 404)
        return Response(content=dados, media_type="image/png", headers={
            "X-RadAI-Cortes": str(info.get("cortes", 0)),
            "Cache-Control": "no-store"})

    @app.post("/api/lote/favorita")
    async def _favorita(request: Request):
        try:
            c = await request.json() or {}
        except Exception:
            c = {}
        alvo = str((c or {}).get("caminho") or "").strip().strip('"')
        import radai_config
        if not alvo:
            return {"favorita": radai_config.pasta_favorita()}
        if not os.path.isdir(alvo):
            return {"erro": u"esta pasta nao esta acessivel agora"}
        ok, erro = radai_config.escrever(radai_config.caminho_padrao(),
                                         {"PASTA_FAVORITA": alvo})
        if not ok:
            return {"erro": erro or u"nao consegui gravar o config"}
        reg = cfg.get("log")
        if callable(reg):
            reg(u"pasta favorita do «Rodar agora» trocada pela tela")
        return {"favorita": alvo}

    @app.get("/api/lote/opcoes")
    def _opcoes(modalidade: str = "CT"):
        try:
            return opcoes_da_tela(modalidade)
        except Exception as e:
            reg = cfg.get("log")
            if callable(reg):
                try:
                    reg(u"as opcoes do «Rodar agora» nao foram montadas: "
                        u"%s: %s" % (type(e).__name__, str(e)[:400]))
                except Exception:
                    pass
            return _erro(e)

    @app.post("/api/lote/previa_da_entrega")
    async def _previa_da_entrega(request: Request):
        try:
            c = await request.json() or {}
        except Exception:
            c = {}
        try:
            ser = c.get("serie") if isinstance(c.get("serie"), dict) else c
            s = (_com_escolhas_da_tela({"series": [ser or {}]}) or [{}])[0]
            return await radai_web.no_threadpool(previa_da_entrega, s)
        except Exception as e:
            return _erro(e)

    def _pausar_vigia(valor):
        f = cfg.get("pausar_vigia")
        if not callable(f):
            return None
        try:
            return f(valor)
        except Exception:
            return None

    @app.post("/api/pipeline/pausar")
    def _pipeline_pausar():
        vig = _pausar_vigia(True)
        lote = pausar(True)
        return {"ok": True, "pausado": True, "lote": lote, "vigia": vig}

    @app.post("/api/pipeline/cancelar")
    def _pipeline_cancelar():
        try:
            oc = cfg["ocupado"]() if callable(cfg.get("ocupado")) else None
        except Exception:
            oc = None
        if oc and oc.get("quem") == "vigia" and callable(
                cfg.get("cancelar_vigia")):
            lote_espera = bool(andamento().get("rodando"))
            try:
                r = dict(cfg["cancelar_vigia"](not lote_espera) or {})
            except Exception as e:
                return dict(_erro(e), ok=False)
            r.setdefault("ok", True)
            r["lote_segue"] = lote_espera
            return r
        vig = _pausar_vigia(True)
        r = cancelar()
        r["vigia"] = vig
        return r

    @app.post("/api/lote/pastas")
    async def _pastas(request: Request):
        try:
            c = await request.json() or {}
        except Exception:
            c = {}
        try:
            d = await _no_threadpool(
                listar_pastas_do_explorador, c.get("caminho") or "",
                c.get("busca") or "", c.get("ordem") or "nome",
                c.get("sentido") or "asc")
            if c.get("unidades"):
                d["unidades"] = await _no_threadpool(
                    unidades_do_explorador, 1.5,
                    0.0 if c.get("fresco") is True else 20.0)
            return d
        except Exception as e:
            return _erro(e)

    @app.get("/api/pipeline/revisao")
    def _pipeline_revisao():
        try:
            import radai_queue_state as _fila
            series = _fila.series_esperando()
        except Exception:
            series = []
        try:
            import radai_review
        except Exception:
            return {"ok": True, "revisao": None}
        _tasks, _mot, _modos, _problemas = conferencia_das_series(series)
        return {"ok": True, "n": len(series),
                "revisao": radai_review.montar(
                    series,
                    tasks=(tuple(_tasks) if series
                           else tuple(cfg.get("tasks") or ())),
                    device=cfg.get("device", "auto"),
                    incluir_nv=_mot["nv"], incluir_cads=_mot["cads"],
                    incluir_moose=_mot["mse"],
                    incluir_hnlnl=_mot["hnlnl"], origem="lote",
                    estudos=_modos, problemas=_problemas,
                    incluir_ts=_mot.get("ts"))}

    @app.post("/api/pipeline/iniciar")
    def _pipeline_iniciar():
        _pausar_vigia(False)
        pausar(False)
        try:
            import radai_queue_state as _fila
            series = _fila.series_esperando()
            turno = _fila.autorizar_turno()
        except Exception as e:
            return dict(_erro(e), ok=False)
        if turno and andamento().get("rodando"):
            return {"ok": True, "turno_agendado": True}
        if not series:
            if turno:
                with _TRAVA:
                    _JOB.update({"cancelar": False, "pausar": False, "erro": ""})
                resposta = _turno_na_vez(cfg.get("log"))
                return resposta or {"ok": True, "turno_agendado": True}
            return {"ok": False, "vazia": True,
                    "erro": u"a fila está vazia — use «Adicionar as selecionadas à fila»"}
        return iniciar(series, ja_na_fila=True,
                       incluir_nv=None,
                       tasks=None, device=cfg.get("device", "auto"),
                       python_exe=cfg.get("python_exe"),
                       timeout_task_s=cfg.get("timeout_task_s", 10800),
                       timeout_nv_s=cfg.get("timeout_task_s", 10800),
                       log=cfg.get("log"), marcadores=cfg.get("marcadores"),
                       maquina=cfg.get("maquina", ""),
                       heartbeat_s=cfg.get("heartbeat_s", 300),
                       suavizar_mm=cfg.get("suavizar_mm", 1.0),
                       ocupado=cfg.get("ocupado"))

    @app.post("/api/lote/enfileirar")
    async def _enfileirar(request: Request):
        try:
            return por_na_fila(_com_escolhas_da_tela(await request.json() or {}))
        except Exception as e:
            return _erro(e)

    @app.post("/api/lote/refazer_pos")
    async def _refazer_pos(request: Request):
        from fastapi.responses import JSONResponse as _JR
        try:
            series = _com_escolhas_da_tela(await request.json() or {})
            marc = cfg.get("marcadores") or {}
            ler = marc.get("read_marker") or (lambda *a: None)
            prontas = []
            for s in series:
                done = ler(s.get("pasta"), s.get("uid"), "done") or {}
                pos = pos_refazivel(done)
                if not pos["refazivel"]:
                    return _JR({"ok": False, "erro": pos["motivo"]},
                               status_code=409)
                d = dict(s, substituir=True, so_pos=True,
                         modo=str(done.get("modo")),
                         so_pos_falharam=_falharam_do_done(done))
                prontas.append(d)
            if not prontas:
                return _JR({"ok": False, "erro": u"nenhuma serie"},
                           status_code=409)
            return por_na_fila(prontas)
        except Exception as e:
            return _erro(e)

    @app.post("/api/lote/conferir_pasta")
    async def _conferir_pasta(request: Request):
        try:
            c = await request.json() or {}
        except Exception:
            c = {}
        return conferir_pasta_sem_gravar((c or {}).get("caminho", u""))

    return app
