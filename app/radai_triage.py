# -*- coding: utf-8 -*-
import math

import numpy as np

try:
    from scipy import ndimage as ndi
except Exception:
    ndi = None

LOBOS = [
    ("lung_upper_lobe_right",  "Lung_RUL", "Lobo superior direito",  "D"),
    ("lung_middle_lobe_right", "Lung_RML", "Lobo médio",             "D"),
    ("lung_lower_lobe_right",  "Lung_RLL", "Lobo inferior direito",  "D"),
    ("lung_upper_lobe_left",   "Lung_LUL", "Lobo superior esquerdo", "E"),
    ("lung_lower_lobe_left",   "Lung_LLL", "Lobo inferior esquerdo", "E"),
]
CHAVES_LOBO = [l[0] for l in LOBOS]
ROTULO_LOBO = dict((l[0], l[2]) for l in LOBOS)
LADO_LOBO = dict((l[0], l[3]) for l in LOBOS)

ESPESSURA_MAXIMA_MM = 1.25
ESPESSURA_RECUSA_MM = 3.0


def avaliar_protocolo(espessura_mm, contraste=False, pixel_mm=None):
    motivos, bloqueia = [], set()
    try:
        esp = float(espessura_mm)
    except (TypeError, ValueError):
        esp = None

    if esp is None:
        return {"estado": "recusado", "bloqueia": {"tudo"},
                "motivos": [u"A espessura de corte não foi encontrada no DICOM. "
                            u"Sem ela não dá para afirmar nada sobre a geometria."]}
    if esp > ESPESSURA_RECUSA_MM:
        return {"estado": "recusado", "bloqueia": {"tudo"},
                "motivos": [u"Espessura de corte de %.2f mm, acima do limite de "
                            u"%.2f mm. Nessa espessura o volume parcial inviabiliza "
                            u"a fronteira entre lobos e a volumetria do achado. "
                            u"Executar produziria número com aparência de precisão "
                            u"e sem lastro geométrico." % (esp, ESPESSURA_RECUSA_MM)]}
    if esp > ESPESSURA_MAXIMA_MM:
        motivos.append(u"Espessura de corte de %.2f mm, acima de %.2f mm. A "
                       u"fronteira entre lobos fica menos confiável e a medida do "
                       u"achado carrega volume parcial."
                       % (esp, ESPESSURA_MAXIMA_MM))
        bloqueia.add("fronteira_fina")
    if not contraste:
        motivos.append(u"Aquisição sem contraste. Separar artéria de veia exige "
                       u"fase contrastada — as distâncias vasculares não são "
                       u"estimadas.")
        bloqueia.add("arteria_veia")
    if pixel_mm:
        try:
            if float(pixel_mm) > 1.0:
                motivos.append(u"Pixel de %.2f mm no plano. Achado pequeno fica "
                               u"abaixo da resolução útil." % float(pixel_mm))
                bloqueia.add("achado_pequeno")
        except (TypeError, ValueError):
            pass
    return {"estado": "degradado" if motivos else "conforme",
            "motivos": motivos, "bloqueia": bloqueia}



TASKS_DO_MODULO = ("total", "lung_vessels")

MIN_CORTES_TORAX = 60

_KERNEL_AFIADO = ("lung", "bone", "edge", "sharp", "detail",
                  "b60", "b70", "b80", "bl5", "bl6", "br6", "br7",
                  "ya", "yb", "yc", "yd")


def kernel_afiado(kernel):
    k = str(kernel or "").strip().lower()
    if not k:
        return False
    if any(k.startswith(p) or p in k for p in _KERNEL_AFIADO):
        return True
    if k.startswith("fc") and k[2:].strip()[:2].isdigit():
        return int(k[2:].strip()[:2]) >= 30
    return False


def avaliar_serie(s):
    cortes = int(s.get("cortes") or 0)
    try:
        esp = float(s.get("espessura_mm") or 0)
    except (TypeError, ValueError):
        esp = 0.0
    kernel = s.get("kernel") or ""

    impedimentos, porques, nota = [], [], 0.0

    motivos = []
    if not esp:
        motivos.append((u"sem espessura", u"espessura de corte ausente no DICOM"))
    elif esp > ESPESSURA_RECUSA_MM:
        motivos.append((u"fora do protocolo",
                        u"corte de %.2f mm, acima do limite de %.2f mm"
                        % (esp, ESPESSURA_RECUSA_MM)))
    if cortes < MIN_CORTES_TORAX:
        motivos.append((u"não cobre o tórax",
                        u"%d corte(s): não cobre o tórax" % cortes))

    if orientacao_recusada(s):
        motivos.append((u"reconstrução",
                        u"reconstrução coronal ou sagital, não a série axial "
                        u"da aquisição"))

    if motivos:
        return {"serve": False, "nota": -1.0, "porques": [],
                "selo": motivos[0][0],
                "impedimentos": [m[1] for m in motivos]}

    nota -= min(cortes, 600) / 100.0
    porques.append(u"%d cortes — a mais rápida entre as que servem" % cortes)

    porques.append(u"corte de %.2f mm" % esp)
    if esp <= ESPESSURA_MAXIMA_MM:
        porques.append(u"dentro do protocolo, sem restrição")
        nota += 1.0

    if kernel_afiado(kernel):
        nota -= 0.5
        porques.append(u"kernel %s é de realce de borda — bom para ler, "
                       u"pior para medir" % kernel)
    elif kernel:
        nota += 0.5
        porques.append(u"kernel %s, de partes moles" % kernel)

    return {"serve": True, "nota": nota, "porques": porques, "impedimentos": []}


MIN_CORTES_CONTORNO = 20


def escolher_para_contorno(series):
    fora = []
    for s in (series or []):
        d = dict(s)
        d.setdefault("sugerida", False)
        d["sugerida"] = False
        d["porque_sugerida"] = u""
        fora.append(d)

    aptas = [x for x in fora if int(x.get("cortes") or 0) >= MIN_CORTES_CONTORNO]
    if not aptas:
        return fora
    escolhidas = escolher_simulacao(aptas)
    for x in fora:
        motivo = escolhidas.get(str(x.get("uid") or ""))
        if motivo:
            x["sugerida"] = True
            x["porque_sugerida"] = motivo
    return fora


def classificar_series(series, ordenar=True):
    fora = []
    for s in (series or []):
        d = dict(s)
        d["torax"] = avaliar_serie(s)
        d["sugerida"] = False
        fora.append(d)
    if ordenar:
        fora.sort(key=lambda x: (not x["torax"]["serve"], -x["torax"]["nota"]))
        melhor = fora[0] if fora else None
    else:
        aptas = [x for x in fora if x["torax"]["serve"]]
        melhor = max(aptas, key=lambda x: x["torax"]["nota"]) if aptas else None
    if melhor is not None and melhor["torax"]["serve"]:
        melhor["sugerida"] = True
    return fora


FRACAO_MINIMA_LOBO = 0.025


SIM_PISO_MM = 1.0
SIM_TETO_MM = 5.0
SIM_FOLGA_MM = 0.05

SIM_COBERTURA_MAX_MM = 1000.0

COBERTURA_MINIMA = 0.85

EMPATE_ESPESSURA = 0.20

QUATRO_D_MIN_SERIES = 10

MARCAS_DE_AVG = ("AVE", "AVG")


def espessura_varrida(s):
    try:
        n = int(s.get("count") or s.get("cortes") or 0)
        z0, z1 = s.get("z0"), s.get("z1")
        if n > 1 and z0 is not None and z1 is not None:
            passo = abs(float(z1) - float(z0)) / (n - 1)
            if passo > 0:
                return passo
    except Exception:
        pass
    for chave in ("esp_dec", "espessura_mm"):
        try:
            v = float(s.get(chave) or 0)
        except Exception:
            v = 0.0
        if v > 0:
            return v
    return 0.0


def _chave_do_exame(s):
    return str(s.get("estudo") or s.get("dir") or s.get("pasta") or "")


def _pode_ser_tc(s):
    return str(s.get("modalidade") or "").strip().upper() in ("", "CT")


def _quando(s):
    d = str(s.get("date") or s.get("data") or "").strip()
    h = str(s.get("hora") or s.get("time") or "").strip()
    try:
        n = int(s.get("n") or s.get("numero") or 0)
    except Exception:
        n = 0
    return (d, h, n)


def _e_media(s):
    import re as _re
    texto = u" ".join(str(s.get(k) or "") for k in ("desc", "descricao", "serie_desc"))
    for p in _re.split(r"[^A-Za-z0-9]+", texto.upper()):
        if p in MARCAS_DE_AVG or p.startswith("AVERAGE") or p.startswith("AVEIP"):
            return True
    return False


COS_MINIMO_AXIAL = 0.95
SOP_DE_CAPTURA_SECUNDARIA = "1.2.840.10008.5.1.4.1.1.7"


def orientacao_axial(iop):
    try:
        o = [float(v) for v in iop]
    except Exception:
        return None
    if len(o) != 6:
        return None
    nz = o[0] * o[4] - o[1] * o[3]
    return abs(nz) >= COS_MINIMO_AXIAL


def captura_secundaria(image_type, sop_class=None):
    try:
        if isinstance(image_type, str):
            partes = image_type.upper().replace("/", "\\").split("\\")
        else:
            partes = [str(v).upper() for v in (image_type or ())]
    except Exception:
        partes = []
    return ("SECONDARY" in partes
            or str(sop_class or "").startswith(SOP_DE_CAPTURA_SECUNDARIA))


def e_rm(s):
    return str(s.get("modalidade") or "").strip().upper() in ("MR", "MRI",
                                                              "RM")


def orientacao_recusada(s):
    return s.get("axial") is False and not e_rm(s)


def _nao_e_volume_de_contorno(s):
    return (orientacao_recusada(s) or s.get("colorida") is True
            or s.get("secundaria") is True)


def escolher_simulacao(series, so_axial=True):
    if isinstance(series, dict):
        itens = [(u, dict(s, uid=u)) for u, s in series.items()]
    else:
        itens = [(str(s.get("uid") or ""), dict(s)) for s in (series or [])]

    por_exame = {}
    for uid, s in itens:
        por_exame.setdefault(_chave_do_exame(s), []).append((uid, s))

    escolhidas = {}
    for _pasta, grupo in por_exame.items():
        cand = [(u, s) for u, s in grupo
                if not (so_axial and _nao_e_volume_de_contorno(s))
                and _pode_ser_tc(s)]
        if not cand:
            continue

        medidas = [(u, s, espessura_varrida(s)) for u, s in cand]
        com = [(u, s, e) for u, s, e in medidas if e > 0]
        if not com:
            for u, s in cand:
                escolhidas[u] = u"sem espessura legivel: nao da para escolher"
            continue

        piso = SIM_PISO_MM - SIM_FOLGA_MM
        teto = SIM_TETO_MM + SIM_FOLGA_MM

        def _cobertura(rec, esp):
            try:
                return int(rec.get("cortes") or rec.get("count") or 0) * esp
            except Exception:
                return 0.0

        aptas = [x for x in com
                 if x[2] >= piso
                 and _cobertura(x[1], x[2]) <= SIM_COBERTURA_MAX_MM]
        if not aptas:
            continue

        _cobs = [(x, _cobertura(x[1], x[2])) for x in aptas]
        _maxc = max((c for _x, c in _cobs), default=0.0)
        if _maxc > 0:
            aptas = [x for x, c in _cobs if c >= _maxc * COBERTURA_MINIMA]
        _cortadas = len(_cobs) - len(aptas)

        na_faixa = [x for x in aptas if x[2] <= teto]
        if na_faixa:
            melhor = max(na_faixa, key=lambda x: (x[2], x[1].get("cortes")
                                                  or x[1].get("count") or 0))
        else:
            melhor = min(aptas, key=lambda x: (x[2], -(x[1].get("cortes")
                                                       or x[1].get("count") or 0)))
        _pq_extra = u""

        base = [x for x in (na_faixa or aptas) if x[2] > 0]
        if base and melhor[2] > 0:
            perto = [x for x in base
                     if abs(x[2] - melhor[2]) <= melhor[2] * EMPATE_ESPESSURA]
            if len(perto) > 1:
                recente = max(perto, key=lambda x: _quando(x[1]))
                if recente[0] != melhor[0] and _quando(recente[1]) > _quando(melhor[1]):
                    melhor = recente
                    _pq_extra = (u"; entre %d reconstrucoes de espessura "
                                 u"equivalente (ate %s), a mais recente"
                                 % (len(perto),
                                    u"%d%%" % int(EMPATE_ESPESSURA * 100)))

        if len(grupo) >= QUATRO_D_MIN_SERIES:
            medias = [x for x in (na_faixa or aptas) if _e_media(x[1])]
            if medias:
                melhor = max(medias, key=lambda x: (x[2], x[1].get("cortes")
                                                    or x[1].get("count") or 0))
                _pq_extra = (u"; estudo com %d series (4D): a AVG e' a media "
                             u"das fases, e e' nela que se planeja"
                             % len(grupo))
        if _cortadas:
            _pq = (u"; e a que cobre mais o paciente -- %d serie(s) cobrem "
                   u"menos e ficaram de fora da sugestao (fases de 4D, "
                   u"reconstrucoes parciais)" % _cortadas)
        elif len(medidas) > 1:
            _pq = (u"; a mais grossa das %d series axiais que cobrem o mesmo, "
                   u"com piso em %s mm" % (len(medidas), u"%.2f" % SIM_PISO_MM))
        else:
            _pq = u""
        escolhidas[melhor[0]] = (
            u"TC de simulacao do exame: %s mm" % (u"%.2f" % melhor[2])
            + _pq + _pq_extra)
    return escolhidas
