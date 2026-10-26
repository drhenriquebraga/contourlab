# -*- coding: utf-8 -*-
import json
import os
import threading

import radai_batch
import radai_sets
import radai_viewer
import radai_web

ROTA = "/verseg"


CURTO_DA_TELA = dict(radai_sets.NOME_NA_TELA)
ROTULO_DA_TELA = {
    "oar": u"STUDY — a seleção do FULL voltada para radioterapia",
    "fast": u"STUDY_Fast — a seleção do modo FAST voltada para radioterapia",
    "full": u"FULL — todo o pós-processamento, partes e compostos",
}

COD_MAPA = u"rotulos"
CURTO_MAPA = u"Estudo 3D"
ROTULO_MAPA = (u"Estudo 3D — o mapa de rótulos dos protocolos de estudo, "
               u"sem RTSTRUCT")

ORDEM = ("oar", "fast", "full", "ts", "nv", "cads", "mse", "hnl")



def _conjunto_do_arquivo(nome):
    nome = str(nome or "")
    if not nome.startswith("RS_RadAI_"):
        return None
    try:
        import radai_sets
        return radai_sets.do_arquivo(nome)
    except Exception:
        return None


def _plugins():
    try:
        import radai_sets
        return tuple(p["cod"] for p in getattr(radai_sets, "PLUGINS", ()))
    except Exception:
        return ()


def rotulo_do_arquivo(nome):
    c = _conjunto_do_arquivo(nome)
    if not c:
        return {"cod": u"", "curto": str(nome or u""),
                "rotulo": u"arquivo que esta versão não reconhece",
                "entregue": False, "plugin": False}
    cod = str(c.get("cod") or u"")
    return {"cod": cod,
            "curto": CURTO_DA_TELA.get(cod) or c.get("rotulo_curto") or nome,
            "rotulo": ROTULO_DA_TELA.get(cod) or c.get("rotulo") or nome,
            "entregue": bool(c.get("entregue")),
            "plugin": cod in _plugins()}


def _posicao(item):
    cod = item.get("cod") or u""
    if cod in ORDEM:
        return (0, ORDEM.index(cod), item.get("arquivo", u""))
    if cod == COD_MAPA:
        return (0, len(ORDEM), item.get("arquivo", u""))
    pl = _plugins()
    if cod in pl:
        return (1, pl.index(cod), item.get("arquivo", u""))
    return (2, 0, item.get("arquivo", u""))


def _da_serie(nomes, uid, outros=()):
    uid = str(uid or u"")
    if not uid:
        return list(nomes)
    alvo = set([uid[-8:], uid.replace(u".", u"")[-8:]])

    def cauda(n):
        base = n[:-4] if n.lower().endswith(u".dcm") else n
        return base.rsplit(u"_", 1)[-1]
    meus = [n for n in nomes if cauda(n) in alvo]
    if meus:
        return meus
    deles = set()
    for o in outros or ():
        o = str(o or u"")
        if o and o != uid:
            deles.update((o[-8:], o.replace(u".", u"")[-8:]))

    def de_outra(n):
        return any((u"_" + d) in n for d in deles)
    return [n for n in nomes if not de_outra(n)]


def _rs_da_pasta(pasta, uid, outros=()):
    return _da_serie(radai_batch._rs_existente(pasta), uid, outros)


def series_contornadas(pasta, sem_contorno=False):
    alvo, erro = _resolver(pasta)
    if erro:
        return [], erro
    try:
        series = radai_batch.varrer(alvo, modalidades=("CT", "MR"),
                                    min_cortes=2, incluir_zips=True)
    except Exception as e:
        return [], u"Não consegui varrer %s: %s" % (alvo, e)

    out = []
    reais = []
    por_pasta = {}
    for s in series:
        real, e2 = radai_batch.resolver_pasta(s)
        reais.append((s, real, e2))
        if real and not e2:
            por_pasta.setdefault(os.path.normcase(os.path.abspath(real)),
                                 []).append(s.get("uid"))
    for s, real, e2 in reais:
        if e2 or not real:
            continue
        _outros = por_pasta.get(os.path.normcase(os.path.abspath(real)), ())
        arquivos = arquivos_contornados(real, s.get("uid"), _outros)
        if not arquivos and not sem_contorno:
            continue
        out.append({
            "uid": s.get("uid"), "pasta": real, "curto": (s.get("uid") or "")[-12:],
            "pid": s.get("pid", ""), "date": s.get("date", ""),
            "desc": s.get("desc", ""), "cortes": s.get("cortes", 0),
            "espessura_mm": s.get("espessura_mm"), "kernel": s.get("kernel", ""),
            "modalidade": s.get("modalidade") or "CT",
            "rs": arquivos, "sem_contorno": not arquivos,
        })
    if not out:
        return [], (u"Nenhuma série contornada em %s. Séries sem RTSTRUCT ao "
                    u"lado não aparecem aqui — processe antes." % alvo)
    return out, ""


def arquivos_contornados(real, uid, outros=()):
    arquivos = []
    for nome in _rs_da_pasta(real, uid, outros):
        r = rotulo_do_arquivo(nome)
        arquivos.append({"arquivo": nome, "cod": r["cod"],
                         "curto": r["curto"], "rotulo": r["rotulo"],
                         "entregue": r["entregue"], "plugin": r["plugin"]})
    mapa = _item_do_mapa(real, uid)
    if mapa:
        arquivos.append(mapa)
    arquivos.sort(key=_posicao)
    return arquivos


def lembrar_modalidade(b, modalidade):
    _MODALIDADE[str(b or u"")] = modalidade or "CT"


def resolver_pasta_do_exame(caminho):
    return _resolver(caminho)


def anotar_bilhete(it):
    import radai_thumbnail
    it["b"] = radai_thumbnail.bilhete(it.get("pasta", u""), it.get("uid", u""))
    lembrar_modalidade(it["b"], it.get("modalidade"))
    return it


def _erro_da_serie_para_o_log(erro, pasta, zip_):
    texto = u"%s" % (erro or u"")
    try:
        import radai_records
        texto = radai_records.higienizar(
            texto, (), marca=u"<pasta da serie>",
            isolados=radai_records.pastas_para_trocar([pasta, zip_]))[0]
    except Exception as e:
        return u"(mensagem omitida: sem o higienizador, %s)" % type(e).__name__
    if zip_:
        texto = radai_batch.sem_detalhe_do_zip(texto, de_zip=True)
    return texto


def abrir_um_eixo(pasta, zip_, uid):
    import radai_thumbnail
    quem = u"%s\x00%s\x00%s" % (pasta or u"", zip_ or u"", uid or u"")
    try:
        real, erro = radai_batch.resolver_pasta(
            {"pasta": str(pasta or ""), "zip": str(zip_ or "")})
    except Exception as e:
        radai_thumbnail.registrar_falha(u"visor de um eixo, abrir", e,
                                        bilhete=quem)
        return {"erro": u"não consegui abrir a série", "tipo": type(e).__name__}
    if erro or not real:
        if erro:
            radai_thumbnail.registrar_falha(
                u"visor de um eixo, abrir",
                ValueError(_erro_da_serie_para_o_log(erro, pasta, zip_)),
                bilhete=quem)
        return {"erro": u"não achei a pasta da série"}
    try:
        return radai_thumbnail.preparar_visor(real, uid)
    except Exception as e:
        radai_thumbnail.registrar_falha(u"visor de um eixo, abrir", e,
                                        bilhete=quem)
        return {"erro": u"não consegui abrir a série", "tipo": type(e).__name__}


def _resolver(caminho):
    caminho = (caminho or "").strip().strip('"')
    if not caminho:
        return "", u"Informe a pasta."
    if os.path.isdir(caminho):
        return caminho, ""
    if os.path.isfile(caminho) and caminho.lower().endswith(".zip"):
        return radai_batch.preparar_zip(caminho)
    return "", u"Não achei %s." % caminho


_SERIE = {"chave": None, "ct": None, "img": None, "geo": None, "auto": None}
_TRAVA_SERIE = threading.Lock()

_RS = {}
_RS_ORDEM = []
_TETO_RS = 6
_TRAVA_RS = threading.Lock()
_TRAVA_LEITURA = threading.Lock()

_MODALIDADE = {}


def _geometria(img):
    import numpy as np
    o = np.asarray(img.GetOrigin(), dtype=np.float64)
    sp = np.asarray(img.GetSpacing(), dtype=np.float64)
    d = np.asarray(img.GetDirection(), dtype=np.float64).reshape(3, 3)
    m = np.linalg.inv(d.dot(np.diag(sp)))
    tam = tuple(int(v) for v in img.GetSize())
    return {"o": o, "m": m, "sp": sp, "tam": tam,
            "chave": (tuple(np.round(o, 4)), tuple(np.round(sp, 5)),
                      tuple(np.round(d.ravel(), 5)), tam)}


def sentido_cranial(img):
    import numpy as np
    d = np.asarray(img.GetDirection(), dtype=np.float64).reshape(3, 3)
    # GUARDA: em LPS o +z e cranial; a terceira coluna da direcao diz para onde o indice do corte cresce (FFS inverte).
    return -1 if float(d[2, 2]) < -0.5 else 1


def _serie(pasta, uid):
    chave = (str(pasta), str(uid))
    with _TRAVA_SERIE:
        if _SERIE["chave"] != chave:
            ct, img = radai_batch._abrir_ct(pasta, uid)
            _SERIE.update({"chave": chave, "ct": ct, "img": img,
                           "geo": _geometria(img), "auto": None})
        return _SERIE["ct"], _SERIE["img"], _SERIE["geo"]


def _janela_auto(ct):
    import numpy as np
    with _TRAVA_SERIE:
        if _SERIE.get("auto") is not None and _SERIE.get("ct") is ct:
            return _SERIE["auto"]
    a = np.asarray(ct)[::4, ::4, ::4].astype(np.float32)
    lo, hi = (float(v) for v in np.percentile(a, [1.0, 99.5]))
    if hi <= lo:
        hi = lo + 1.0
    with _TRAVA_SERIE:
        if _SERIE.get("ct") is ct:
            _SERIE["auto"] = (lo, hi)
    return lo, hi


def _png_cinza(a):
    import struct
    import zlib
    import numpy as np
    a = np.ascontiguousarray(a, dtype=np.uint8)
    alt, larg = a.shape
    linhas = np.zeros((alt, larg + 1), dtype=np.uint8)
    linhas[:, 1:] = a

    def bloco(tipo, dados):
        return (struct.pack(">I", len(dados)) + tipo + dados
                + struct.pack(">I", zlib.crc32(tipo + dados) & 0xFFFFFFFF))
    return (b"\x89PNG\r\n\x1a\n"
            + bloco(b"IHDR", struct.pack(">IIBBBBB", larg, alt, 8, 0, 0, 0, 0))
            + bloco(b"IDAT", zlib.compress(linhas.tobytes(), 6))
            + bloco(b"IEND", b""))


def corte_png(pasta, uid, corte, janela=u"mediastino", hu=True):
    import numpy as np
    ct, _img, _geo = _serie(pasta, uid)
    n = int(ct.shape[0])
    z = max(0, min(n - 1, int(corte)))
    j = radai_viewer.JANELAS.get(str(janela or u""))
    if j is None:
        j = radai_viewer.JANELAS["mediastino"] if hu else _janela_auto(ct)
    lo, hi = float(j[0]), float(j[1])
    f = (np.asarray(ct[z], dtype=np.float32) - lo) * (255.0 / max(hi - lo, 1e-6))
    return _png_cinza(np.clip(f, 0, 255).astype(np.uint8)), z, n


def _bruto_dos_pontos(contorno):
    from pydicom.tag import Tag
    try:
        el = contorno.get_item(Tag(0x3006, 0x0050))
    except Exception:
        return b""
    if el is None:
        return b""
    v = el.value
    if isinstance(v, (bytes, bytearray)):
        return bytes(v).strip(b" \x00")
    try:
        return b"\\".join(repr(float(x)).encode("ascii") for x in (v or ()))
    except Exception:
        return b""


def _nome_padrao_da_roi(item):
    try:
        import radai_sets
        return radai_sets.nome_padrao_da_descricao(
            getattr(item, "ROIDescription", u"")) or None
    except Exception:
        return None


def _ler_rs(caminho, geo):
    import numpy as np
    import pydicom
    ds = pydicom.dcmread(str(caminho), force=True)
    rotulo = str(getattr(ds, "StructureSetLabel", "") or "")
    nomes, padroes = {}, {}
    for r in getattr(ds, "StructureSetROISequence", None) or []:
        try:
            nomes[int(r.ROINumber)] = str(r.ROIName)
        except Exception:
            continue
        padroes[int(r.ROINumber)] = _nome_padrao_da_roi(r)
    rois, brutos, donos = [], [], []
    for rc in getattr(ds, "ROIContourSequence", None) or []:
        try:
            num = int(getattr(rc, "ReferencedROINumber", 0) or 0)
        except Exception:
            continue
        nome = nomes.get(num)
        if not nome:
            continue
        try:
            cor = [int(v) for v in (getattr(rc, "ROIDisplayColor", None)
                                    or [255, 255, 0])][:3]
        except Exception:
            cor = [255, 255, 0]
        rois.append({"nome": nome, "cor": cor, "cortes": {},
                     "padrao": padroes.get(num) or nome,
                     "a": 0.0, "ax": 0.0, "ay": 0.0, "az": 0.0})
        for c in getattr(rc, "ContourSequence", None) or []:
            b = _bruto_dos_pontos(c)
            if b:
                brutos.append(b)
                donos.append(len(rois) - 1)
    vistos = set(r["nome"] for r in rois)
    for num in sorted(nomes):
        if nomes[num] not in vistos:
            rois.append({"nome": nomes[num], "cor": [160, 160, 160],
                         "cortes": {}, "a": 0.0, "ax": 0.0, "ay": 0.0,
                         "az": 0.0})
    if brutos:
        contas = [b.count(b"\\") + 1 for b in brutos]
        try:
            vals = np.array(b"\\".join(brutos).split(b"\\"), dtype=np.float64)
        except ValueError:
            vals, contas = [], []
            for b in brutos:
                v = [float(x) for x in b.split(b"\\") if x.strip()]
                contas.append(len(v))
                vals.extend(v)
            vals = np.asarray(vals, dtype=np.float64)
        nz = geo["tam"][2]
        ini = 0
        for dono, k in zip(donos, contas):
            bloco = vals[ini:ini + k]
            ini += k
            if bloco.size < 9 or bloco.size % 3:
                continue
            idx = (bloco.reshape(-1, 3) - geo["o"]).dot(geo["m"].T)
            z = int(round(float(np.median(idx[:, 2]))))
            if not (0 <= z < nz):
                continue
            pts = (idx[:, :2] + 0.5).astype(np.float32)
            roi = rois[dono]
            roi["cortes"].setdefault(z, []).append(pts)
            x, y = idx[:, 0], idx[:, 1]
            cruz = x * np.roll(y, -1) - np.roll(x, -1) * y
            a = 0.5 * float(cruz.sum())
            if abs(a) < 1e-9:
                continue
            cx = float(((x + np.roll(x, -1)) * cruz).sum()) / (6.0 * a)
            cy = float(((y + np.roll(y, -1)) * cruz).sum()) / (6.0 * a)
            a = abs(a)
            roi["a"] += a
            roi["ax"] += a * cx
            roi["ay"] += a * cy
            roi["az"] += a * z
    return {"rotulo": rotulo, "rois": rois}


def _rs_lido(caminho, geo):
    st = os.stat(caminho)
    k = (os.path.normcase(os.path.abspath(caminho)), st.st_mtime_ns,
         st.st_size, geo["chave"])
    with _TRAVA_RS:
        if k in _RS:
            _RS_ORDEM.remove(k)
            _RS_ORDEM.append(k)
            return _RS[k]
    with _TRAVA_LEITURA:
        with _TRAVA_RS:
            if k in _RS:
                return _RS[k]
        lido = _ler_rs(caminho, geo)
        with _TRAVA_RS:
            _RS[k] = lido
            _RS_ORDEM.append(k)
            while len(_RS_ORDEM) > _TETO_RS:
                _RS.pop(_RS_ORDEM.pop(0), None)
    return lido


def _arquivo_rs(pasta, uid, rs):
    rs = str(rs or u"")
    if (not pasta or not rs or rs in (u".", u"..")
            or any(ch in rs for ch in (u"/", u"\\", u":", u"\x00"))
            or os.path.basename(rs) != rs):
        return None
    if rs not in _rs_da_pasta(pasta, uid):
        return None
    return os.path.join(pasta, rs)


def _nome_do_mapa(uid):
    import radai_rotulos
    return radai_rotulos.nome_do_arquivo(uid)


def _meta_do_mapa(caminho):
    import numpy as np
    try:
        with np.load(caminho, allow_pickle=False) as z:
            return json.loads(bytes(z["_meta"]).decode("ascii"))
    except Exception:
        return None


def _caminho_do_mapa(pasta, uid):
    if not pasta or not uid:
        return None
    try:
        import radai_rotulos
        c = radai_rotulos.caminho(pasta, uid)
        if not os.path.isfile(c):
            return None
        meta = _meta_do_mapa(c)
        if not isinstance(meta, dict):
            return None
        if int(meta.get("formato") or 0) != radai_rotulos.VERSAO_FORMATO:
            return None
        # GUARDA: o nome leva só 8 caracteres do UID; o de dentro decide.
        if meta.get("uid") and str(meta["uid"]) != str(uid):
            return None
        return c
    except Exception:
        return None


def _item_do_mapa(pasta, uid):
    c = _caminho_do_mapa(pasta, uid)
    if not c:
        return None
    return {"arquivo": os.path.basename(c), "cod": COD_MAPA,
            "curto": CURTO_MAPA, "rotulo": ROTULO_MAPA, "entregue": False,
            "plugin": False, "mapa": True}


def _e_o_mapa(pasta, uid, rs):
    return bool(rs) and rs == _nome_do_mapa(uid) and bool(
        _caminho_do_mapa(pasta, uid))


def _cor_do_indice(i):
    import colorsys
    h = (i * 0.618033988749895) % 1.0
    r, g, b = colorsys.hls_to_rgb(h, 0.6, 0.75)
    return [int(round(r * 255)), int(round(g * 255)), int(round(b * 255))]


def bordas_svg(m, oy=0, ox=0):
    import numpy as np
    m = np.asarray(m, dtype=bool)
    if not m.any():
        return u""
    p = np.pad(m, 1)
    hor = p[1:, 1:-1] != p[:-1, 1:-1]
    ver = p[1:-1, 1:] != p[1:-1, :-1]
    partes = []

    def corridas(linha):
        d = np.diff(np.concatenate(([0], linha.astype(np.int8), [0])))
        return zip(np.flatnonzero(d == 1), np.flatnonzero(d == -1))
    for r in np.flatnonzero(hor.any(axis=1)):
        for a, b in corridas(hor[r]):
            partes.append(u"M%d %dh%d" % (ox + a, oy + r, b - a))
    for c in np.flatnonzero(ver.any(axis=0)):
        for a, b in corridas(ver[:, c]):
            partes.append(u"M%d %dv%d" % (ox + c, oy + a, b - a))
    return u"".join(partes)


class _MapaLeve(object):

    def __init__(self, caminho, forma):
        import numpy as np
        forma = tuple(int(v) for v in forma)
        with np.load(caminho, allow_pickle=False) as z:
            meta = json.loads(bytes(z["_meta"]).decode("ascii"))
            tabela = [t for t in (meta.get("tabela") or ())
                      if isinstance(t, dict) and t.get("nome")]
            self.meta = meta
            self.fatias = {}
            self.info = {}
            por_chave = {}
            for i, t in enumerate(tabela):
                por_chave.setdefault(str(t.get("chave")), {})[
                    int(t.get("indice") or 0)] = t
                self.info[t["nome"]] = {
                    "nome": t["nome"], "chave": str(t.get("chave")),
                    "indice": int(t.get("indice") or 0),
                    "achado": bool(t.get("achado")),
                    "cor": _cor_do_indice(i), "cortes": set(), "n": 0.0,
                    "sz": 0.0, "sy": 0.0, "sx": 0.0}
            for chave, idx in por_chave.items():
                if chave not in z.files:
                    continue
                vol = z[chave]
                if tuple(vol.shape) != forma:
                    raise ValueError(u"o mapa de rótulos não tem a forma "
                                     u"desta série")
                tam = int(vol.max()) + 1 if vol.size else 1
                tipo = np.uint8 if tam <= 256 else np.uint16
                cortes = {}
                for zi in range(forma[0]):
                    sl = vol[zi]
                    lin = np.flatnonzero(sl.any(axis=1))
                    if not lin.size:
                        continue
                    col = np.flatnonzero(sl.any(axis=0))
                    y0, y1, x0, x1 = (int(lin[0]), int(lin[-1]) + 1,
                                      int(col[0]), int(col[-1]) + 1)
                    sub = np.ascontiguousarray(sl[y0:y1, x0:x1]).astype(tipo)
                    cortes[zi] = (y0, x0, sub)
                    rot = sub.ravel().astype(np.int64)
                    yy, xx = np.indices(sub.shape)
                    cnt = np.bincount(rot, minlength=tam)
                    sy = np.bincount(rot, weights=(yy + y0).ravel(), minlength=tam)
                    sx = np.bincount(rot, weights=(xx + x0).ravel(), minlength=tam)
                    for k in np.flatnonzero(cnt[1:]) + 1:
                        t = idx.get(int(k))
                        if not t:
                            continue
                        inf = self.info[t["nome"]]
                        inf["cortes"].add(zi)
                        inf["n"] += float(cnt[k])
                        inf["sz"] += float(cnt[k]) * zi
                        inf["sy"] += float(sy[k])
                        inf["sx"] += float(sx[k])
                self.fatias[chave] = cortes

    def estruturas(self):
        es = [{"nome": i["nome"], "cor": i["cor"], "cortes": len(i["cortes"]),
               "achado": i["achado"]} for i in self.info.values()]
        es.sort(key=lambda e: e["nome"].lower())
        return es

    def contornos(self, z):
        fora = []
        for i in self.info.values():
            if z not in i["cortes"]:
                continue
            f = self.fatias.get(i["chave"], {}).get(z)
            if not f:
                continue
            y0, x0, sub = f
            d = bordas_svg(sub == i["indice"], y0, x0)
            if d:
                fora.append({"n": i["nome"], "c": i["cor"], "d": d})
        return fora

    def centro(self, nome):
        i = self.info.get(nome)
        if not i:
            return {"erro": u"a estrutura não está neste arquivo", "nome": nome}
        if i["n"] <= 0:
            return {"erro": u"a estrutura não tem contorno nesta série",
                    "nome": nome}
        zs = sorted(i["cortes"])
        return {"nome": nome, "z": i["sz"] / i["n"], "y": i["sy"] / i["n"],
                "x": i["sx"] / i["n"], "cortes": len(zs), "primeiro": zs[0],
                "ultimo": zs[-1]}


_MAPA = {"chave": None, "mapa": None}
_TRAVA_MAPA = threading.Lock()


def _mapa_lido(pasta, uid):
    import numpy as np
    c = _caminho_do_mapa(pasta, uid)
    if not c:
        raise ValueError(u"arquivo não encontrado nesta série")
    ct, _img, _geo = _serie(pasta, uid)
    st = os.stat(c)
    forma = tuple(int(v) for v in np.asarray(ct).shape)
    k = (os.path.normcase(os.path.abspath(c)), st.st_mtime_ns, st.st_size, forma)
    with _TRAVA_MAPA:
        if _MAPA["chave"] == k:
            return _MAPA["mapa"]
        _MAPA["chave"], _MAPA["mapa"] = None, None
        m = _MapaLeve(c, forma)
        _MAPA["chave"], _MAPA["mapa"] = k, m
        return m


SEM_UID = u"sem_uid"
SEM_SEGMENTACAO = u"sem_segmentacao"


def _e_desta_serie(nome, uid):
    base = nome[:-4] if nome.lower().endswith(u".dcm") else nome
    cauda = base.rsplit(u"_", 1)[-1]
    return bool(uid) and cauda in (uid[-8:], uid.replace(u".", u"")[-8:])


def _mascara_do_poligono(poligono, altura, largura):
    import math
    import numpy as np
    alt, larg = int(altura), int(largura)
    m = np.zeros((alt, larg), dtype=bool)
    pts = [(float(x), float(y)) for x, y in (poligono or ())]
    if len(pts) < 3:
        return m
    xs_p = [p[0] for p in pts]
    ys_p = [p[1] for p in pts]
    c0 = max(0, int(math.floor(min(xs_p) - 0.5)))
    c1 = min(larg, int(math.ceil(max(xs_p) - 0.5)) + 1)
    l0 = max(0, int(math.floor(min(ys_p) - 0.5)))
    l1 = min(alt, int(math.ceil(max(ys_p) - 0.5)) + 1)
    if c1 <= c0 or l1 <= l0:
        return m
    p = np.asarray(pts, dtype=np.float64)
    ax, ay = p[:, 0], p[:, 1]
    bx, by = np.roll(ax, -1), np.roll(ay, -1)
    ok = ay != by
    ax, ay, bx, by = ax[ok], ay[ok], bx[ok], by[ok]
    xs = np.arange(c0, c1, dtype=np.float64) + 0.5
    yc = np.arange(l0, l1, dtype=np.float64)[:, None] + 0.5
    cruza = (ay[None, :] > yc) != (by[None, :] > yc)
    linha, aresta = np.nonzero(cruza)
    if not linha.size:
        return m
    yy = yc[linha, 0]
    # GUARDA: o pixel conta a aresta que cruza à direita do centro dele (a mesma conta do radai_nidus).
    xint = ((bx[aresta] - ax[aresta]) * (yy - ay[aresta])
            / (by[aresta] - ay[aresta]) + ax[aresta])
    k = np.searchsorted(xs, xint, side="left")
    h = np.zeros((l1 - l0, c1 - c0 + 1), dtype=np.int32)
    np.add.at(h, (linha, k), 1)
    direita = h[:, ::-1].cumsum(axis=1)[:, ::-1][:, 1:]
    m[l0:l1, c0:c1] = (direita % 2) == 1
    return m


def _mascara_dos_cortes(cortes, forma, destino):
    import numpy as np
    for z, polis in (cortes or {}).items():
        z = int(z)
        if not 0 <= z < forma[0]:
            continue
        plano = np.zeros(forma[1:], dtype=bool)
        for p in polis or ():
            # GUARDA: paridade entre os contornos do corte; o furo (por XOR ou por fenda) fica furo.
            plano ^= _mascara_do_poligono([(float(x), float(y)) for x, y in p],
                                          forma[1], forma[2])
        destino[z] |= plano
    return destino


def mascaras_da_serie(pasta, uid, img, aceita=None, conjuntos=(u"full",),
                      com_mapa=True):
    import numpy as np
    uid = str(uid or u"")
    if not uid:
        return None, {"tem": False, "motivo": SEM_UID}
    tam = tuple(int(v) for v in img.GetSize())
    forma = (tam[2], tam[1], tam[0])
    quer = aceita if callable(aceita) else (lambda nome: True)
    if not pasta or not os.path.isdir(pasta):
        return None, {"tem": False, "motivo": SEM_SEGMENTACAO}
    # GUARDA: o arquivo de outra série da mesma pasta não serve; o nome termina no UID desta.
    nomes = [n for n in _rs_da_pasta(pasta, uid) if _e_desta_serie(n, uid)]
    for cod in conjuntos or ():
        for nome in nomes:
            r = rotulo_do_arquivo(nome)
            if (r.get("cod") or u"") != cod:
                continue
            caminho = _arquivo_rs(pasta, uid, nome)
            if not caminho:
                continue
            lido = _rs_lido(caminho, _geometria(img))
            m = np.zeros(forma, dtype=bool)
            usadas = []
            for roi in lido.get("rois") or ():
                # GUARDA: no STUDY com nome proprio quem decide e o nome padrao, guardado na descricao da ROI.
                if not roi.get("cortes") or not quer(roi.get("padrao")
                                                     or roi.get("nome")):
                    continue
                usadas.append(roi["nome"])
                _mascara_dos_cortes(roi["cortes"], forma, m)
            if usadas and m.any():
                return m, {"tem": True, "fonte": r.get("curto") or cod,
                           "cod": cod, "arquivo": nome,
                           "estruturas": len(usadas), "nomes": usadas}
    if com_mapa:
        c = _caminho_do_mapa(pasta, uid)
        mapa = None
        if c:
            try:
                mapa = _MapaLeve(c, forma)
            except ValueError:
                mapa = None
        if mapa is not None:
            m = np.zeros(forma, dtype=bool)
            usadas = []
            for nome, inf in mapa.info.items():
                if not quer(nome):
                    continue
                usadas.append(nome)
                for z, (y0, x0, sub) in mapa.fatias.get(inf["chave"], {}).items():
                    m[z, y0:y0 + sub.shape[0], x0:x0 + sub.shape[1]] |= (
                        sub == inf["indice"])
            if usadas and m.any():
                return m, {"tem": True, "fonte": CURTO_MAPA, "cod": COD_MAPA,
                           "arquivo": os.path.basename(c),
                           "estruturas": len(usadas), "nomes": usadas}
    return None, {"tem": False, "motivo": SEM_SEGMENTACAO}


def _caminho_svg(pts):
    s = [u"%.1f %.1f" % (float(x), float(y)) for x, y in pts.tolist()]
    return u"M" + s[0] + u"L" + u"L".join(s[1:]) + u"Z"


def estruturas_do_arquivo(pasta, uid, rs):
    if _e_o_mapa(pasta, uid, rs):
        return {"rs": rs, "rotulo_dicom": u"", "mapa": True,
                "estruturas": _mapa_lido(pasta, uid).estruturas()}
    caminho = _arquivo_rs(pasta, uid, rs)
    if not caminho:
        return {"rs": rs, "erro": u"arquivo não encontrado nesta série",
                "estruturas": []}
    _ct, _img, geo = _serie(pasta, uid)
    lido = _rs_lido(caminho, geo)
    es = [{"nome": r["nome"], "cor": r["cor"], "cortes": len(r["cortes"])}
          for r in lido["rois"]]
    es.sort(key=lambda e: e["nome"].lower())
    return {"rs": rs, "rotulo_dicom": lido["rotulo"], "estruturas": es}


def contornos_do_corte(pasta, uid, rs, corte):
    if _e_o_mapa(pasta, uid, rs):
        return {"rs": rs, "corte": int(corte),
                "estruturas": _mapa_lido(pasta, uid).contornos(int(corte))}
    caminho = _arquivo_rs(pasta, uid, rs)
    if not caminho:
        return {"rs": rs, "corte": corte, "estruturas": [],
                "erro": u"arquivo não encontrado nesta série"}
    _ct, _img, geo = _serie(pasta, uid)
    lido = _rs_lido(caminho, geo)
    z = int(corte)
    fora = []
    for r in lido["rois"]:
        polis = r["cortes"].get(z)
        if not polis:
            continue
        fora.append({"n": r["nome"], "c": r["cor"],
                     "d": u" ".join(_caminho_svg(p) for p in polis)})
    return {"rs": rs, "corte": z, "estruturas": fora}


def centro_do_arquivo(pasta, uid, rs, nome):
    if _e_o_mapa(pasta, uid, rs):
        return _mapa_lido(pasta, uid).centro(nome)
    caminho = _arquivo_rs(pasta, uid, rs)
    if not caminho:
        return {"erro": u"arquivo não encontrado nesta série"}
    _ct, _img, geo = _serie(pasta, uid)
    lido = _rs_lido(caminho, geo)
    for r in lido["rois"]:
        if r["nome"] != nome:
            continue
        if r["a"] <= 0:
            return {"erro": u"a estrutura não tem contorno nesta série",
                    "nome": nome}
        zs = sorted(r["cortes"])
        return {"nome": nome, "z": r["az"] / r["a"], "y": r["ay"] / r["a"],
                "x": r["ax"] / r["a"], "cortes": len(zs),
                "primeiro": zs[0], "ultimo": zs[-1]}
    return {"erro": u"a estrutura não está neste arquivo", "nome": nome}


ROTA_DA_RECONSTRUCAO = u"/recon3d/anatomia"


def ficha_para_a_reconstrucao(pasta, uid, rs, estruturas):
    import radai_fichas
    mapa = _e_o_mapa(pasta, uid, rs)
    if not mapa and not _arquivo_rs(pasta, uid, rs):
        return {"erro": u"arquivo não encontrado nesta série"}
    tem = set(e["nome"] for e in
              (estruturas_do_arquivo(pasta, uid, rs).get("estruturas") or ()))
    pedidas = []
    for n in estruturas or ():
        n = u"%s" % (n or u"")
        if n in tem and n not in pedidas:
            pedidas.append(n)
    if not pedidas:
        return {"erro": u"ligue ao menos uma estrutura para levar à "
                        u"Reconstrução 3D"}
    ficha = radai_fichas.guardar({
        "origem": u"verseg", "pasta": u"%s" % pasta, "uid": u"%s" % uid,
        "arquivo": u"%s" % rs, "tipo": u"rotulos" if mapa else u"rtstruct",
        "estruturas": pedidas})
    return {"ficha": ficha, "url": u"%s?ficha=%s" % (ROTA_DA_RECONSTRUCAO,
                                                     ficha)}


def _hu_do_bilhete(b, ct):
    mod = _MODALIDADE.get(str(b or u""))
    if mod:
        return str(mod).upper() == u"CT"
    try:
        import numpy as np
        return float(np.asarray(ct)[::8, ::8, ::8].min()) < -500.0
    except Exception:
        return True


def forma_da_serie(pasta, uid, b=u""):
    import numpy as np
    ct, img, geo = _serie(pasta, uid)
    z, y, x = (int(v) for v in np.asarray(ct).shape)
    sx, sy, sz = (float(v) for v in geo["sp"])
    return {"forma": [z, y, x], "sp": [sz, sy, sx],
            "hu": bool(_hu_do_bilhete(b, ct)), "cranial": sentido_cranial(img)}


def _sufixos_para_o_js():
    import radai_sets
    todos = set(s.lower() for s in radai_sets.SUFIXOS_DE_TODAS_AS_GERACOES)
    apos = list(radai_sets.SUFIXOS_APOSENTADOS)
    ordem = lambda s: (-len(s), s.lower())
    return sorted(todos, key=ordem), sorted(apos, key=ordem)


_JS_MOLDE = u"""
var CP_SUFIXOS = @CP_SUFIXOS@;
var CP_APOSENTADOS = @CP_APOSENTADOS@;
var CP_TETO_CACHE = 600;
var CP_ZOOM_MAX = 8;
var CP_ZOOM_INICIAL = 1.25;
var CP_ICO_MIRA = '<svg class="ui-ic" viewBox="0 0 24 24" width="14" height="14"'
 + ' fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"'
 + ' aria-hidden="true"><circle cx="12" cy="12" r="7"/><circle cx="12" cy="12"'
 + ' r="1.6"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3"/></svg>';
var CP = {montado: false, serie: null, forma: [0, 0, 0], sp: [1, 1, 1],
          hu: true, corte: 0, janela: 'mediastino', zoom: 1, px: 0, py: 0,
          cranial: 1, lados: [], cacheCont: {}, ordemCache: [], emVoo: false,
          querido: false, ultimo: null, carregando: false};

function cpDoc(){ return (typeof document !== 'undefined') ? document : null; }
function cpJan(){ return (typeof window !== 'undefined') ? window : null; }
function cpEl(id){
 var d = cpDoc();
 return (d && d.getElementById) ? d.getElementById(id) : null;
}
function cpEsc(s){
 return String(s == null ? '' : s).replace(/&/g, '&amp;')
  .replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
function cpTexto(el, t){
 if(!el) return;
 var w = cpJan();
 if(w && w.uiTexto) w.uiTexto(el, t); else el.textContent = t;
}
function cpHTML(el, h){
 if(!el) return;
 var w = cpJan();
 if(w && w.uiHTML) w.uiHTML(el, h); else el.innerHTML = h;
}
// GUARDA: texto reescrito por JS perde a marca do tradutor; sem pedir a
// tradução na hora, ele fica em português até a próxima passada.
function cpRetraduzir(){
 var w = cpJan();
 try{ if(w && w.radaiRetraduzir) w.radaiRetraduzir(); }catch(x){}
}
function cpMsg(t, erro){
 var e = cpEl('cp_msg'); if(!e) return;
 cpTexto(e, t || '');
 if(e.classList) e.classList.toggle('cp-erro', !!erro);
 cpRetraduzir();
}
function cpQs(o){
 var p = [];
 for(var k in o){
  if(Object.prototype.hasOwnProperty.call(o, k))
   p.push(encodeURIComponent(k) + '=' + encodeURIComponent(o[k] == null ? '' : o[k]));
 }
 return p.join('&');
}

function cpBase(nome){
 var n = String(nome || '').toLowerCase();
 for(var i = 0; i < CP_SUFIXOS.length; i++){
  var s = CP_SUFIXOS[i];
  if(n.length > s.length && n.slice(-s.length) === s) return n.slice(0, -s.length);
 }
 return n;
}
function cpAposentado(nome){
 var n = String(nome || '').toLowerCase();
 for(var i = 0; i < CP_APOSENTADOS.length; i++){
  var s = CP_APOSENTADOS[i], sl = s.toLowerCase();
  if(n.length > sl.length && n.slice(-sl.length) === sl) return s;
 }
 return '';
}

function cpPadroes(rs){
 rs = rs || [];
 function de(cod){
  for(var i = 0; i < rs.length; i++) if(rs[i].cod === cod) return rs[i].arquivo;
  return '';
 }
 var esq = de('full') || (rs[0] ? rs[0].arquivo : '');
 var dir = '', pref = ['oar', 'fast', 'ts'];
 for(var i = 0; i < pref.length && !dir; i++){
  var a = de(pref[i]);
  if(a && a !== esq) dir = a;
 }
 for(var k = 0; k < rs.length && !dir; k++) if(rs[k].arquivo !== esq) dir = rs[k].arquivo;
 return [esq, dir || esq];
}

function cpNovoLado(i){
 return {i: i, arq: '', rotuloDicom: '', estruturas: [], ligadas: {}, filtro: ''};
}

function cpDefinirForma(forma, sp, hu){
 CP.forma = [forma[0] | 0, forma[1] | 0, forma[2] | 0];
 CP.sp = (sp && sp.length === 3) ? [+sp[0] || 1, +sp[1] || 1, +sp[2] || 1] : [1, 1, 1];
 CP.hu = (hu !== false);
 CP.corte = Math.max(0, Math.min(CP.forma[0] - 1, CP.corte | 0));
 if(!CP.hu) CP.janela = 'auto';
 else if(CP.janela === 'auto') CP.janela = 'mediastino';
 var rg = cpEl('cp_rg');
 if(rg){ rg.max = String(Math.max(0, CP.forma[0] - 1)); rg.value = String(CP.corte); }
 for(var i = 0; i < 2; i++){
  var svg = cpEl('cp_svg' + i);
  if(svg) svg.setAttribute('viewBox', '0 0 ' + CP.forma[2] + ' ' + CP.forma[1]);
 }
 var jc = cpEl('cp_janela_cx');
 if(jc && jc.classList) jc.classList.toggle('cp-oculto', !CP.hu);
 cpAjustarPalcos();
}

function cpCarregando(ligado, texto){
 CP.carregando = !!ligado;
 var w = cpJan();
 if(!w || !w.uiCarregando) return;
 for(var i = 0; i < 2; i++){
  var v = cpEl('cp_visor' + i);
  if(v) w.uiCarregando(v, ligado ? true : false, texto || '');
 }
}
function cpAbrirSerie(s){
 if(!s) return;
 CP.serie = s; CP.cacheCont = {}; CP.ordemCache = []; CP.ultimo = null;
 CP.zoom = CP_ZOOM_INICIAL; CP.px = 0; CP.py = 0; CP.corte = 0;
 var p = cpPadroes(s.rs || []);
 CP.lados = [cpNovoLado(0), cpNovoLado(1)];
 CP.lados[0].arq = p[0]; CP.lados[1].arq = p[1];
 cpPreencherSeletores();
 var vazio = cpEl('cp_vazio'), raiz = cpEl('cp_raiz');
 if(vazio && vazio.classList) vazio.classList.add('cp-oculto');
 if(raiz && raiz.classList){
  raiz.classList.remove('cp-oculto');
  raiz.classList.toggle('cp-sem-arquivos', !(s.rs || []).length);
 }
 cpAplicarZoom();
 var w = cpJan();
 if(w && w.requestAnimationFrame) w.requestAnimationFrame(cpAjustarPalcos);
 cpMsg('');
 cpCarregando(true, 'abrindo a série…');
 fetch('/api/verseg/forma?' + cpQs({b: s.b || ''}))
  .then(function(r){ return r.json(); })
  .catch(function(){ return null; })
  .then(function(d){
   if(CP.serie !== s) return;              // outra serie foi aberta no meio
   var forma = d && d.forma;
   if(!forma || !forma[0]) forma = [s.cortes || 1, 512, 512];
   CP.cranial = (d && d.cranial === -1) ? -1 : 1;
   cpDefinirForma(forma, d && d.sp, !(d && d.hu === false));
   CP.corte = Math.floor(CP.forma[0] / 2);
   cpSincronizarBarra();
   if(d && d.erro){ cpCarregando(false); cpMsg(d.erro, true); }
   else if(s.sem_contorno || !(s.rs || []).length)
    cpMsg('Esta série ainda não foi segmentada: rode-a no Rodar agora para ver os contornos.');
   cpCarregarLado(CP.lados[0]);
   cpCarregarLado(CP.lados[1]);
   cpPedirMostrar();
  });
}

function cpUrlCT(z){
 return '/api/verseg/ct?' + cpQs({b: CP.serie.b || '', corte: z, j: CP.janela});
}

function cpGuardar(chave, d){
 if(!CP.cacheCont[chave]) CP.ordemCache.push(chave);
 CP.cacheCont[chave] = d;
 while(CP.ordemCache.length > CP_TETO_CACHE) delete CP.cacheCont[CP.ordemCache.shift()];
}
function cpContornos(lado, z){
 if(!lado || !lado.arq || !CP.serie) return Promise.resolve(null);
 var chave = (CP.serie.b || '') + '|' + lado.arq + '|' + z;
 if(CP.cacheCont[chave]) return Promise.resolve(CP.cacheCont[chave]);
 var url = '/api/verseg/contornos?' + cpQs({b: CP.serie.b || '', rs: lado.arq,
                                            corte: z});
 return fetch(url).then(function(r){ return r.json(); }).then(function(d){
  if(d && !d.erro) cpGuardar(chave, d);
  return d;
 }).catch(function(){ return null; });
}

function cpPedirMostrar(){
 if(!CP.serie || !CP.forma[0]) return;
 CP.querido = true;
 if(CP.emVoo) return;
 cpMostrar();
}
function cpMostrar(){
 CP.querido = false; CP.emVoo = true;
 var z = CP.corte, url = cpUrlCT(z), lados = CP.lados.slice();
 var carga = new Promise(function(ok){
  var img = new Image();
  img.onload = function(){ ok(true); };
  img.onerror = function(){ ok(false); };
  img.src = url;
 });
 Promise.all([carga, cpContornos(lados[0], z), cpContornos(lados[1], z)])
  .then(function(r){
   CP.emVoo = false;
   CP.ultimo = {z: z, url: url, dados: [r[1], r[2]], imagem: r[0]};
   cpPintar(z, url, [r[1], r[2]]);
   if(CP.carregando) cpCarregando(false);
   if(!r[0]) cpMsg('não consegui carregar a imagem deste corte', true);
   if(CP.querido) cpMostrar();
  }, function(){
   CP.emVoo = false;
   if(CP.carregando) cpCarregando(false);
   if(CP.querido) cpMostrar();
  });
}

function cpVisiveis(lado, d){
 if(!lado || !d || !lado.arq || d.rs !== lado.arq) return [];
 var fora = [], es = d.estruturas || [];
 for(var i = 0; i < es.length; i++) if(lado.ligadas[es[i].n]) fora.push(es[i]);
 return fora;
}
function cpSvgDe(lista){
 var h = '';
 for(var i = 0; i < (lista || []).length; i++){
  var e = lista[i], c = e.c || [255, 255, 0];
  h += '<path d="' + cpEsc(e.d) + '" stroke="rgb(' + c.join(',') + ')"/>';
 }
 return h;
}
function cpPintar(z, url, dados){
 for(var i = 0; i < 2; i++){
  var lado = CP.lados[i]; if(!lado) continue;
  var img = cpEl('cp_img' + i);
  if(img && img.getAttribute('src') !== url) img.setAttribute('src', url);
  var svg = cpEl('cp_svg' + i);
  if(svg) svg.innerHTML = cpSvgDe(cpVisiveis(lado, dados[i]));
  cpMarcarNoCorte(lado, dados[i]);
 }
}
function cpRepintar(){
 var u = CP.ultimo;
 if(u) cpPintar(u.z, u.url, u.dados);
}

function cpAndar(d){
 if(!CP.forma[0]) return;
 var n = Math.max(0, Math.min(CP.forma[0] - 1, CP.corte + d));
 if(n === CP.corte) return;
 CP.corte = n;
 cpSincronizarBarra();
 cpPedirMostrar();
}
function cpIrCorte(n){
 if(!CP.forma[0]) return;
 cpAndar(Math.round(+n || 0) - CP.corte);
}
function cpRumoCaudal(n){ return -n * (CP.cranial === -1 ? -1 : 1); }
function cpRoda(ev, i){
 if(!CP.forma[0]) return;
 if(ev.preventDefault) ev.preventDefault();
 if(ev.ctrlKey){
  var p = cpEl('cp_palco' + i), r = (p && p.getBoundingClientRect) ? p.getBoundingClientRect() : null;
  var fx = r && r.width ? ((ev.clientX - r.left) / r.width - 0.5) * CP.zoom : 0;
  var fy = r && r.height ? ((ev.clientY - r.top) / r.height - 0.5) * CP.zoom : 0;
  cpZoom(ev.deltaY < 0 ? 1.15 : 1 / 1.15, fx, fy);
  return;
 }
 if(!ev.deltaY) return;
 cpAndar(cpRumoCaudal((ev.deltaY > 0 ? 1 : -1) * (ev.shiftKey ? 10 : 1)));
}
function cpTecla(ev){
 var c = {ArrowDown: 1, ArrowUp: -1, PageDown: 10, PageUp: -10}[ev.key];
 var d = c ? cpRumoCaudal(c) : {ArrowRight: 1, ArrowLeft: -1}[ev.key];
 if(!d) return;
 if(ev.preventDefault) ev.preventDefault();
 cpAndar(d);
}
function cpSincronizarBarra(){
 var rg = cpEl('cp_rg');
 if(rg && String(rg.value) !== String(CP.corte)) rg.value = String(CP.corte);
 var n = cpEl('cp_num');
 if(n) n.textContent = CP.forma[0] ? ((CP.corte + 1) + ' / ' + CP.forma[0]) : '—';
}

function cpJanela(j){
 if(!j || j === CP.janela) return;
 CP.janela = j;
 var s = cpEl('cp_janela');
 if(s && s.value !== j) s.value = j;
 cpPedirMostrar();
}

function cpAlternar(lado, nome){
 if(!lado) return;
 if(lado.ligadas[nome]) delete lado.ligadas[nome];
 else lado.ligadas[nome] = 1;
 if(!cpMarcarBotao(lado, nome)) cpDesenharLista(lado);
 cpRepintar();
}
function cpMarcarBotao(lado, nome){
 var alvo = cpEl('cp_chips' + lado.i);
 if(!alvo || !alvo.querySelectorAll) return false;
 var bs = alvo.querySelectorAll('[data-cp-nome]'), achou = false;
 for(var i = 0; i < bs.length; i++){
  if(bs[i].getAttribute('data-cp-nome') !== nome) continue;
  var on = !!lado.ligadas[nome];
  bs[i].classList.toggle('on', on);
  bs[i].setAttribute('aria-pressed', on ? 'true' : 'false');
  achou = true;
 }
 cpContagem(lado);
 return achou;
}
function cpContagem(lado){
 var n = cpEl('cp_n' + lado.i); if(!n) return;
 var lig = 0;
 (lado.estruturas || []).forEach(function(e){ if(lado.ligadas[e.nome]) lig++; });
 n.textContent = lig + ' / ' + (lado.estruturas || []).length;
}
function cpFiltradas(lado){
 var f = String(lado.filtro || '').toLowerCase();
 return (lado.estruturas || []).filter(function(e){
  return !f || e.nome.toLowerCase().indexOf(f) >= 0;
 });
}
function cpLigarTodas(lado, ligar){
 if(!lado) return;
 cpFiltradas(lado).forEach(function(e){
  if(ligar) lado.ligadas[e.nome] = 1; else delete lado.ligadas[e.nome];
 });
 cpDesenharLista(lado);
 cpRepintar();
}
function cpCopiar(de, para){
 if(!de || !para) return;
 var bases = {};
 for(var n in de.ligadas) if(de.ligadas[n]) bases[cpBase(n)] = 1;
 var novo = {};
 (para.estruturas || []).forEach(function(e){
  if(bases[cpBase(e.nome)]) novo[e.nome] = 1;
 });
 para.ligadas = novo;
 cpDesenharLista(para);
 cpRepintar();
}

function cpVisiveisDoLado(lado){
 var fora = [];
 (lado && lado.estruturas || []).forEach(function(e){
  if(lado.ligadas[e.nome] && e.cortes) fora.push(e.nome);
 });
 return fora;
}
function cpParaReconstrucao(lado){
 if(!lado || !CP.serie || !lado.arq) return Promise.resolve(null);
 if(lado.carregando){
  cpMsg('carregando as estruturas…');
  return Promise.resolve(null);
 }
 var nomes = cpVisiveisDoLado(lado), arqDoVisor = lado.arq;
 if(!nomes.length){
  cpMsg('ligue ao menos uma estrutura para levar à Reconstrução 3D', true);
  return Promise.resolve(null);
 }
 return fetch('/api/verseg/recon3d', {method: 'POST',
   headers: {'Content-Type': 'application/json'},
   body: JSON.stringify({b: CP.serie.b || '', rs: arqDoVisor, estruturas: nomes})})
  .then(function(r){ return r.json(); })
  .catch(function(){ return null; })
  .then(function(d){
   if(!d || d.erro || !d.ficha){
    cpMsg((d && d.erro) || 'não consegui preparar a Reconstrução 3D', true);
    return null;
   }
   var w = cpJan();
   if(w && w.location) w.location.href = '/recon3d/anatomia?ficha=' + encodeURIComponent(d.ficha);
   return d.ficha;
  });
}

function cpTrocarArquivo(i, arq){
 var lado = CP.lados[i];
 if(!lado || lado.arq === arq) return;
 lado.arq = arq;
 cpCarregarLado(lado);
 cpPedirMostrar();
}
function cpCarregarLado(lado){
 if(!lado || !CP.serie) return;
 var serie = CP.serie, arq = lado.arq;
 lado.estruturas = []; lado.ligadas = {}; lado.rotuloDicom = '';
 cpEtiqueta(lado);
 if(!arq){ lado.carregando = false; cpDesenharLista(lado, 'sem'); return; }
 lado.carregando = true;
 cpDesenharLista(lado, 'carregando');
 fetch('/api/verseg/estruturas?' + cpQs({b: serie.b || '', rs: arq}))
  .then(function(r){ return r.json(); })
  .catch(function(){ return null; })
  .then(function(d){
   if(CP.serie !== serie || lado.arq !== arq) return;   // trocou no meio
   lado.carregando = false;
   if(!d || d.erro){
    cpDesenharLista(lado, 'erro');
    return;
   }
   lado.estruturas = d.estruturas || [];
   lado.rotuloDicom = d.rotulo_dicom || '';
   var lig = {};
   lado.estruturas.forEach(function(e){ if(e.cortes) lig[e.nome] = 1; });
   lado.ligadas = lig;
   cpEtiqueta(lado);
   cpDesenharLista(lado);
   cpRepintar();
  });
}
function cpItemDoArq(arq){
 var rs = (CP.serie && CP.serie.rs) || [];
 for(var i = 0; i < rs.length; i++) if(rs[i].arquivo === arq) return rs[i];
 return null;
}
function cpEtiqueta(lado){
 var it = cpItemDoArq(lado.arq);
 var e = cpEl('cp_etq' + lado.i);
 if(e) e.textContent = it ? (it.curto || it.arquivo) : '';
 var dc = cpEl('cp_dicom' + lado.i);
 if(dc){
  var h = '';
  if(lado.rotuloDicom) h += '<code>' + cpEsc(lado.rotuloDicom) + '</code> ';
  if(it && it.rotulo) h += '<span>' + cpEsc(it.rotulo) + '</span>';
  cpHTML(dc, h);
 }
 cpRetraduzir();
}
function cpPreencherSeletores(){
 var rs = (CP.serie && CP.serie.rs) || [];
 for(var i = 0; i < 2; i++){
  var sel = cpEl('cp_sel' + i), lado = CP.lados[i];
  if(!sel || !lado) continue;
  sel.innerHTML = rs.map(function(r){
   return '<option value="' + cpEsc(r.arquivo) + '"'
    + (r.arquivo === lado.arq ? ' selected' : '') + ' title="'
    + cpEsc(r.arquivo) + '">' + cpEsc(r.curto || r.arquivo) + '</option>';
  }).join('');
  sel.value = lado.arq;
  cpEtiqueta(lado);
 }
}

function cpDesenharLista(lado, estado){
 var alvo = cpEl('cp_chips' + lado.i); if(!alvo) return;
 var n = cpEl('cp_n' + lado.i);
 if(estado === 'carregando'){
  cpHTML(alvo, '<p class="sub">carregando as estruturas…</p>');
  if(n) n.textContent = '';
  return;
 }
 if(estado === 'erro'){
  cpHTML(alvo, '<p class="sub">não consegui ler este arquivo</p>');
  if(n) n.textContent = '';
  return;
 }
 if(estado === 'sem'){
  cpHTML(alvo, '<p class="sub">nenhum arquivo de contorno nesta série</p>');
  if(n) n.textContent = '';
  return;
 }
 var es = cpFiltradas(lado);
 cpContagem(lado);
 if(!(lado.estruturas || []).length){
  cpHTML(alvo, '<p class="sub">nenhuma estrutura neste arquivo</p>');
  return;
 }
 if(!es.length){
  cpHTML(alvo, '<p class="sub">nenhuma estrutura com esse nome</p>');
  return;
 }
 var h = es.map(function(e){
  var on = !!lado.ligadas[e.nome], c = e.cor || [120, 120, 120];
  var apos = cpAposentado(e.nome);
  return '<div class="cp-linha' + (e.cortes ? '' : ' cp-sem') + '">'
   + '<button type="button" class="cp-est' + (on ? ' on' : '') + '" data-cp-lado="'
   + lado.i + '" data-cp-nome="' + cpEsc(e.nome) + '" aria-pressed="' + on + '">'
   + '<span class="sw" style="--c:rgb(' + c.join(',') + ')"></span>'
   + '<span class="nm">' + cpEsc(e.nome) + '</span>'
   + (apos ? '<span class="cp-apos" title="' + cpEsc(apos)
      + '">aposentado</span>' : '')
   + (e.achado ? '<span class="cp-apos cp-achado">ACHADO</span>' : '')
   + '</button>'
   + (e.cortes ? '<button type="button" class="cp-ir" data-cp-lado="' + lado.i
      + '" data-cp-ir="' + cpEsc(e.nome) + '" title="ir ao centro da estrutura"'
      + ' aria-label="ir ao centro da estrutura">' + CP_ICO_MIRA + '</button>' : '')
   + '</div>';
 }).join('');
 cpHTML(alvo, h);
 cpMarcarNoCorte(lado, CP.ultimo ? CP.ultimo.dados[lado.i] : null);
}
function cpMarcarNoCorte(lado, d){
 var alvo = cpEl('cp_chips' + lado.i);
 if(!alvo || !alvo.querySelectorAll) return;
 var aqui = {};
 if(d && d.rs === lado.arq) (d.estruturas || []).forEach(function(e){ aqui[e.n] = 1; });
 var bs = alvo.querySelectorAll('[data-cp-nome]');
 for(var i = 0; i < bs.length; i++){
  bs[i].classList.toggle('aqui', !!aqui[bs[i].getAttribute('data-cp-nome')]);
 }
}

function cpIrPara(lado, nome){
 if(!lado || !CP.serie || !lado.arq) return;
 var arq = lado.arq;
 fetch('/api/verseg/centro?' + cpQs({b: CP.serie.b || '', rs: arq, nome: nome}))
  .then(function(r){ return r.json(); })
  .catch(function(){ return null; })
  .then(function(d){
   if(!d || d.erro || d.z == null){ cpMsg((d && d.erro) || 'não achei o centro da estrutura', true); return; }
   if(!lado.ligadas[nome]){ lado.ligadas[nome] = 1; cpDesenharLista(lado); }
   cpMsg('');
   cpIrCorte(Math.round(d.z));
   cpRepintar();
  });
}

function cpAjustarPalcos(){
 cpRepintarAbas();
 if(!CP.forma[0]) return;
 var ar = (CP.forma[2] * CP.sp[2]) / Math.max(1e-6, CP.forma[1] * CP.sp[1]);
 for(var i = 0; i < 2; i++){
  var v = cpEl('cp_visor' + i), p = cpEl('cp_palco' + i);
  if(!v || !p) continue;
  var W = v.clientWidth, H = v.clientHeight;
  if(!W || !H) continue;
  var w = W, h = W / ar;
  if(h > H){ h = H; w = H * ar; }
  p.style.width = w + 'px'; p.style.height = h + 'px';
  p.style.left = ((W - w) / 2) + 'px'; p.style.top = ((H - h) / 2) + 'px';
 }
 cpAplicarZoom();
}
function cpRepintarAbas(){
 var cx = cpEl('cp_janela_cx');
 if(!cx || !cx.querySelector) return;
 var a = cx.querySelector('.ui-abas');
 if(a && a._uiPintar){ try{ a._uiPintar(); }catch(e){} }
}
function cpAplicarZoom(){
 for(var i = 0; i < 2; i++){
  var p = cpEl('cp_palco' + i); if(!p) continue;
  var w = p.offsetWidth || 0, h = p.offsetHeight || 0;
  p.style.transform = 'translate(' + (CP.px * w) + 'px,' + (CP.py * h) + 'px) scale(' + CP.zoom + ')';
 }
 var z = cpEl('cp_zoom_n');
 if(z) z.textContent = Math.round(CP.zoom * 100) + '%';
}
function cpZoom(fator, fx, fy){
 var novo = Math.max(1, Math.min(CP_ZOOM_MAX, CP.zoom * fator));
 if(novo === CP.zoom) return;
 fx = fx || 0; fy = fy || 0;
 var k = novo / CP.zoom;
 CP.px = fx - (fx - CP.px) * k;
 CP.py = fy - (fy - CP.py) * k;
 CP.zoom = novo;
 if(CP.zoom === 1){ CP.px = 0; CP.py = 0; }
 cpAplicarZoom();
}
function cpAjustar(){ CP.zoom = 1; CP.px = 0; CP.py = 0; cpAplicarZoom(); }

function cpMira(fx, fy){
 for(var i = 0; i < 2; i++){
  var m = cpEl('cp_mira' + i); if(!m) continue;
  if(fx == null){ m.style.display = 'none'; continue; }
  m.style.display = 'block';
  m.style.left = (fx * 100) + '%'; m.style.top = (fy * 100) + '%';
 }
}

function cpMontar(){
 var raiz = cpEl('cp_raiz');
 if(!raiz){ CP.montado = false; return false; }
 var sec = cpEl('cx_verseg') || raiz;
 sec.addEventListener('click', function(ev){
  var t = ev.target;
  if(!t || !t.closest) return;
  var b = t.closest('[data-cp-nome]');
  if(b){ cpAlternar(CP.lados[+b.getAttribute('data-cp-lado')], b.getAttribute('data-cp-nome')); return; }
  b = t.closest('[data-cp-ir]');
  if(b){ cpIrPara(CP.lados[+b.getAttribute('data-cp-lado')], b.getAttribute('data-cp-ir')); return; }
  b = t.closest('[data-cp-todas]');
  if(b){ cpLigarTodas(CP.lados[+b.getAttribute('data-cp-todas')], true); return; }
  b = t.closest('[data-cp-nenhuma]');
  if(b){ cpLigarTodas(CP.lados[+b.getAttribute('data-cp-nenhuma')], false); return; }
  b = t.closest('[data-cp-copiar]');
  if(b){ var i = +b.getAttribute('data-cp-copiar'); cpCopiar(CP.lados[i], CP.lados[1 - i]); return; }
  b = t.closest('[data-cp-recon]');
  if(b){ cpParaReconstrucao(CP.lados[+b.getAttribute('data-cp-recon')]); return; }
  b = t.closest('[data-cp-zoom]');
  if(b){
   var z = +b.getAttribute('data-cp-zoom');
   if(z > 0) cpZoom(1.25); else if(z < 0) cpZoom(0.8); else cpAjustar();
   return;
  }
  b = t.closest('[data-cp-passo]');
  if(b){ cpAndar(+b.getAttribute('data-cp-passo')); return; }
 });
 var rg = cpEl('cp_rg');
 if(rg) rg.addEventListener('input', function(){ cpIrCorte(+rg.value); });
 var js = cpEl('cp_janela');
 if(js) js.addEventListener('change', function(){ cpJanela(js.value); });
 [0, 1].forEach(function(i){
  var sel = cpEl('cp_sel' + i);
  if(sel) sel.addEventListener('change', function(){ cpTrocarArquivo(i, sel.value); });
  var f = cpEl('cp_filtro' + i);
  if(f) f.addEventListener('input', function(){
   var lado = CP.lados[i]; if(!lado) return;
   lado.filtro = f.value || ''; cpDesenharLista(lado);
  });
  var v = cpEl('cp_visor' + i);
  if(!v) return;
  v.addEventListener('wheel', function(ev){ cpRoda(ev, i); }, {passive: false});
  v.addEventListener('keydown', cpTecla);
  var arr = null;
  v.addEventListener('pointerdown', function(ev){
   if(ev.button !== 0 || CP.zoom <= 1) return;
   var p = cpEl('cp_palco' + i);
   arr = {x: ev.clientX, y: ev.clientY, px: CP.px, py: CP.py,
          w: (p && p.offsetWidth) || 1, h: (p && p.offsetHeight) || 1};
   try{ v.setPointerCapture(ev.pointerId); }catch(e){}
   v.classList.add('cp-arrasta');
  });
  v.addEventListener('pointermove', function(ev){
   var p = cpEl('cp_palco' + i);
   if(arr){
    CP.px = arr.px + (ev.clientX - arr.x) / arr.w;
    CP.py = arr.py + (ev.clientY - arr.y) / arr.h;
    cpAplicarZoom();
   }
   if(!p) return;
   var r = p.getBoundingClientRect();
   if(!r.width || !r.height) return;
   var fx = (ev.clientX - r.left) / r.width, fy = (ev.clientY - r.top) / r.height;
   if(fx < 0 || fx > 1 || fy < 0 || fy > 1) cpMira(null); else cpMira(fx, fy);
  });
  function soltar(){ arr = null; v.classList.remove('cp-arrasta'); }
  v.addEventListener('pointerup', soltar);
  v.addEventListener('pointercancel', soltar);
  v.addEventListener('pointerleave', function(){ cpMira(null); });
 });
 var w = cpJan();
 if(w && w.addEventListener) w.addEventListener('resize', cpAjustarPalcos);
 try{
  if(w && w.ResizeObserver){
   var ro = new w.ResizeObserver(function(){ cpAjustarPalcos(); });
   [0, 1].forEach(function(i){ var v = cpEl('cp_visor' + i); if(v) ro.observe(v); });
  }
 }catch(e){}
 CP.montado = true;
 return true;
}
(function(){
 var d = cpDoc();
 if(!d) return;
 if(d.readyState === 'loading' && d.addEventListener) d.addEventListener('DOMContentLoaded', cpMontar);
 else cpMontar();
})();
"""

_SUF_TODOS, _SUF_APOS = _sufixos_para_o_js()
JS = (_JS_MOLDE.replace(u"@CP_SUFIXOS@", json.dumps(_SUF_TODOS))
               .replace(u"@CP_APOSENTADOS@", json.dumps(_SUF_APOS)))


CSS = u"""
.cp-oculto{display:none !important}
.cp-raiz{display:flex;flex-direction:column;gap:10px;margin-top:6px}
.cp-msg.cp-erro{color:var(--perigo,#E96A5C)}
.cp-vazio{border:1px dashed var(--line);border-radius:10px;padding:22px;
 text-align:center;color:var(--text-dim);font-size:12.5px;line-height:1.6}
.cp-barra{display:flex;align-items:center;gap:14px;flex-wrap:wrap;
 padding:8px 10px;border:1px solid var(--line);border-radius:var(--r-lg,8px);
 background:var(--panel-2,#0f1729)}
.cp-grupo{display:flex;align-items:center;gap:6px}
.cp-grupo > .cp-lbl{font-family:var(--mono,monospace);font-size:9.5px;
 letter-spacing:.12em;text-transform:uppercase;color:var(--text-dim)}
.cp-corte{flex:1 1 260px;min-width:0}
.cp-corte input[type=range]{flex:1;min-width:120px;accent-color:var(--accent)}
.cp-num{font-family:var(--mono,monospace);font-size:11.5px;color:var(--text-muted);
 min-width:72px;text-align:right;font-variant-numeric:tabular-nums}
.cp-bt{font:inherit;font-family:var(--mono,monospace);font-size:11px;
 padding:4px 9px;border-radius:var(--r-sm,5px);border:1px solid var(--line-strong);
 background:transparent;color:var(--text-muted);cursor:pointer;line-height:1.2}
.cp-bt:hover{border-color:var(--accent);color:var(--text)}
.cp-bt:focus-visible,.cp-est:focus-visible,.cp-ir:focus-visible,
.cp-visor:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.cp-bt.cp-passo{min-width:26px;padding:3px 0;font-size:15px;text-align:center}
#cp_zoom_n{font-family:var(--mono,monospace);font-size:11px;color:var(--text-muted);
 min-width:40px;text-align:center}
.cp-dica{margin-left:auto;font-size:10.5px;color:var(--text-dim)}
.cp-duas{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}
@media (max-width:900px){.cp-duas{grid-template-columns:minmax(0,1fr)}}
.cp-lado{display:flex;flex-direction:column;gap:8px;min-width:0}
.cp-visor{position:relative;width:100%;aspect-ratio:1/1;max-height:66vh;
 background:#000;border:1px solid var(--line);border-radius:var(--r-md,6px);
 overflow:hidden;touch-action:none;cursor:crosshair}
.cp-visor.cp-arrasta{cursor:grabbing}
.cp-palco{position:absolute;left:0;top:0;width:100%;height:100%;
 transform-origin:50% 50%}
.cp-palco img{position:absolute;inset:0;width:100%;height:100%;display:block;
 user-select:none;-webkit-user-drag:none}
.cp-svg{position:absolute;inset:0;width:100%;height:100%;overflow:visible;
 pointer-events:none}
.cp-svg path{fill:none;stroke-width:1.4px;vector-effect:non-scaling-stroke;
 stroke-linejoin:round}
.cp-mira{position:absolute;display:none;width:15px;height:15px;margin:-7px 0 0 -7px;
 pointer-events:none;border:1px solid rgba(255,255,255,.85);border-radius:999px;
 box-shadow:0 0 0 1px rgba(0,0,0,.6)}
.cp-etq{position:absolute;top:7px;left:9px;font-family:var(--mono,monospace);
 font-size:10px;letter-spacing:.08em;text-transform:uppercase;color:#e6edf7;
 background:rgba(0,0,0,.55);padding:2px 7px;border-radius:4px;pointer-events:none}
.cp-arq{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.cp-arq label{font-family:var(--mono,monospace);font-size:9.5px;letter-spacing:.12em;
 text-transform:uppercase;color:var(--text-dim)}
.cp-arq select{flex:1 1 180px;min-width:0;font:inherit;font-size:12.5px;
 padding:5px 8px;border-radius:var(--r-md,6px);border:1px solid var(--line-strong);
 background:var(--panel,#0c1322);color:var(--text)}
.cp-dicom{flex:1 1 100%;font-size:11px;color:var(--text-dim);line-height:1.45}
.cp-dicom code{font-family:var(--mono,monospace);font-size:10.5px;color:var(--text-muted)}
.cp-acoes{display:flex;align-items:center;gap:6px;flex-wrap:wrap}
.cp-acoes input[type=search]{flex:1 1 150px;min-width:0;font:inherit;font-size:12px;
 padding:5px 8px;border-radius:var(--r-md,6px);border:1px solid var(--line-strong);
 background:var(--panel,#0c1322);color:var(--text)}
.cp-n{font-family:var(--mono,monospace);font-size:10.5px;color:var(--text-dim);
 margin-left:auto;font-variant-numeric:tabular-nums}
.cp-chips{display:grid;grid-template-columns:repeat(auto-fill,minmax(170px,1fr));
 gap:2px 8px;max-height:280px;overflow:auto;padding:6px;border:1px solid var(--line);
 border-radius:var(--r-md,6px);align-content:start}
.cp-linha{display:flex;align-items:center;min-width:0}
.cp-est{flex:1;min-width:0;display:flex;align-items:center;gap:7px;text-align:left;
 padding:3px 6px;border-radius:4px;border:0;background:none;cursor:pointer;
 font-family:var(--mono,monospace);font-size:11.5px;color:var(--text-dim)}
.cp-est .nm{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.cp-est .sw{flex:none;width:10px;height:10px;border-radius:2px;
 border:1.5px solid var(--c);background:transparent}
.cp-est.on{color:var(--text)}
.cp-est.on .sw{background:var(--c)}
.cp-est:hover{background:var(--panel-2,#0f1729);color:var(--text)}
.cp-est.aqui .nm{font-weight:650}
.cp-est.aqui::after{content:"";flex:none;width:5px;height:5px;border-radius:999px;
 background:var(--accent);margin-left:auto}
.cp-sem .cp-est{opacity:.55}
.cp-apos{flex:none;font-size:9px;letter-spacing:.06em;text-transform:uppercase;
 padding:1px 5px;border-radius:999px;border:1px solid var(--aviso,#E8A33D);
 color:var(--aviso,#E8A33D)}
.cp-ir{flex:none;border:0;background:none;cursor:pointer;color:var(--text-dim);
 font-size:13px;padding:2px 5px;border-radius:4px;line-height:1;opacity:.3;
 transition:opacity .12s}
.cp-linha:hover .cp-ir,.cp-ir:focus-visible{opacity:1}
.cp-ir:hover{color:var(--accent);background:var(--panel-2,#0f1729)}
@media (hover:none){.cp-ir{opacity:.85}}
.cp-ir .ui-ic,.cp-passo .ui-ic{margin:0;display:block}
.cp-bt.cp-passo{display:inline-grid;place-items:center;min-height:26px}
.cp-achado{border-color:var(--perigo,#E96A5C);color:var(--perigo,#E96A5C)}
div.cp-bloco{margin-top:22px}
.cp-bt.cp-recon{border-color:var(--mod-recon);color:var(--mod-recon);font-weight:600}
.cp-bt.cp-recon:hover{background:var(--mod-recon-fraco);color:var(--mod-recon);
 border-color:var(--mod-recon)}
.cp-vazio.ui-organico-alvo{min-height:220px}
.cp-sem-arquivos .cp-arq,.cp-sem-arquivos .cp-acoes{display:none}
.cp-chips p.sub{grid-column:1/-1;margin:4px 2px;font-size:12.5px;
 color:var(--text-dim)}
"""




def _lado(k, nome):
    return (u"""
   <section class="cp-lado" data-lado="%(k)s" aria-label="%(nome)s">
    <div class="cp-visor" id="cp_visor%(k)s" tabindex="0">
     <div class="cp-palco" id="cp_palco%(k)s">
      <img id="cp_img%(k)s" alt="" draggable="false">
      <svg id="cp_svg%(k)s" class="cp-svg" viewBox="0 0 512 512"
           preserveAspectRatio="none" aria-hidden="true"></svg>
      <span class="cp-mira" id="cp_mira%(k)s"></span>
     </div>
     <span class="cp-etq" id="cp_etq%(k)s"></span>
    </div>
    <div class="cp-arq">
     <label for="cp_sel%(k)s">Arquivo</label>
     <select id="cp_sel%(k)s"></select>
     <div class="cp-dicom" id="cp_dicom%(k)s"></div>
    </div>
    <div class="cp-acoes">
     <input type="search" id="cp_filtro%(k)s" spellcheck="false"
            placeholder="filtrar estruturas" aria-label="filtrar estruturas">
     <button type="button" class="cp-bt" data-cp-todas="%(k)s">ligar todas</button>
     <button type="button" class="cp-bt" data-cp-nenhuma="%(k)s">desligar todas</button>
     <button type="button" class="cp-bt" data-cp-copiar="%(k)s"
             title="liga do outro lado as estruturas de mesmo nome">espelhar com o outro lado</button>
     <span class="cp-n" id="cp_n%(k)s"></span>
     <button type="button" class="cp-bt cp-recon" data-cp-recon="%(k)s"
             title="leva a série e as estruturas ligadas neste visor às Reconstruções 3D">Reconstrução 3D</button>
    </div>
    <div class="cp-chips" id="cp_chips%(k)s"></div>
   </section>""" % {"k": k, "nome": nome})


def bloco(numero=u"2"):
    return (u"""
<div class="ps-cx fechado cp-bloco" id="cx_verseg">
 <h2 class="ps-cab" id="h_verseg" data-cx="cx_verseg" tabindex="0" role="button"><span class="ps-num">@NUM@</span>
  <span data-radai-frase>Ver segmentação</span>
  <span class="ui-ajuda dir" tabindex="0" aria-label="ajuda">?<span class="ui-balao"><p>Cada visor desenha <b>só o arquivo escolhido abaixo dele</b>. O corte, a janela e o zoom andam juntos nos dois.</p><p>A roda do mouse troca o corte (Shift anda de dez em dez); Ctrl com a roda aproxima; arrastar move a imagem aproximada.</p><p>Aqui se olha: nada nesta tela mede, aprova ou grava.</p></span></span>
  <span class="ps-seta">&#9662;</span></h2>
 <div class="ps-corpo" id="c_verseg">
  <div class="sub" id="cp_qual"></div>
  <div class="sub cp-msg" id="cp_msg" role="status" aria-live="polite"></div>
  <div class="cp-vazio" id="cp_vazio">Escolha uma série no item 1 para abrir os dois visores.</div>
  <div class="cp-raiz cp-oculto" id="cp_raiz">
   <div class="cp-barra">
    <div class="cp-grupo cp-corte">
     <label class="cp-lbl" for="cp_rg">corte</label>
     <button type="button" class="cp-bt cp-passo" data-cp-passo="-1" title="corte anterior" aria-label="corte anterior">@ICO_ESQUERDA@</button>
     <input type="range" id="cp_rg" min="0" max="0" value="0" step="1">
     <button type="button" class="cp-bt cp-passo" data-cp-passo="1" title="próximo corte" aria-label="próximo corte">@ICO_DIREITA@</button>
     <span class="cp-num" id="cp_num">—</span>
    </div>
    <div class="cp-grupo" id="cp_janela_cx">
     <span class="cp-lbl">janela</span>
     <select id="cp_janela" data-ui-abas aria-label="janela">
      <option value="mediastino">mediastino</option>
      <option value="pulmao">pulmão</option>
      <option value="osso">osso</option>
     </select>
    </div>
    <div class="cp-grupo">
     <span class="cp-lbl">zoom</span>
     <button type="button" class="cp-bt" data-cp-zoom="-1" aria-label="afastar">−</button>
     <span id="cp_zoom_n">100%</span>
     <button type="button" class="cp-bt" data-cp-zoom="1" aria-label="aproximar">+</button>
     <button type="button" class="cp-bt" data-cp-zoom="0">ajustar</button>
    </div>
   </div>
   <div class="cp-duas">@LADOS@
   </div>
  </div>
 </div>
</div>""").replace(u"@LADOS@", _lado(u"0", u"lado esquerdo")
                   + _lado(u"1", u"lado direito")).replace(
                       u"@NUM@", u"%s" % numero).replace(
                       u"@ICO_ESQUERDA@", _icone(u"esquerda")).replace(
                       u"@ICO_DIREITA@", _icone(u"direita"))


def _icone(nome):
    try:
        import radai_ui
        return radai_ui.icone(nome)
    except Exception:
        return {u"esquerda": u"&#8249;", u"direita": u"&#8250;"}.get(nome, u"")


def montar(app):
    from fastapi import Request
    from fastapi.responses import Response

    def _pasta(b, uid=u""):
        import radai_thumbnail
        caminho, uid_b = radai_thumbnail.resolver(b)
        if not caminho:
            return u"", u""
        return caminho, (uid_b or uid or u"")

    def _falha(onde, e, b):
        try:
            import radai_thumbnail
            radai_thumbnail.registrar_falha(u"ver segmentação, %s" % onde, e,
                                            bilhete=b)
        except Exception:
            pass

    @app.get("/api/verseg/forma")
    def _forma(b: str = "", uid: str = ""):
        pasta, uid = _pasta(b, uid)
        if not pasta:
            return {"erro": u"a série não está mais aberta — recarregue a "
                            u"lista", "forma": [0, 0, 0]}
        try:
            return forma_da_serie(pasta, uid, b)
        except Exception as e:
            _falha(u"forma", e, b)
            return {"erro": u"não consegui abrir a série", "forma": [0, 0, 0]}

    @app.get("/api/verseg/ct")
    def _ct(b: str = "", uid: str = "", corte: int = 0, j: str = ""):
        pasta, uid = _pasta(b, uid)
        if not pasta:
            return Response(status_code=404, headers={"Cache-Control": "no-store"})
        try:
            ct, _img, _geo = _serie(pasta, uid)
            png, z, n = corte_png(pasta, uid, corte, j, _hu_do_bilhete(b, ct))
        except Exception as e:
            _falha(u"corte", e, b)
            return Response(status_code=500,
                            headers={"X-RadAI-Erro": type(e).__name__,
                                     "Cache-Control": "no-store"})
        return Response(content=png, media_type="image/png",
                        headers={"Cache-Control": "private, max-age=3600",
                                 "X-RadAI-Corte": str(z),
                                 "X-RadAI-Cortes": str(n)})

    @app.get("/api/verseg/estruturas")
    def _estruturas(b: str = "", rs: str = ""):
        pasta, uid = _pasta(b)
        if not pasta:
            return {"rs": rs, "estruturas": [],
                    "erro": u"a série não está mais aberta — recarregue a lista"}
        try:
            return estruturas_do_arquivo(pasta, uid, rs)
        except Exception as e:
            _falha(u"estruturas", e, b)
            return {"rs": rs, "estruturas": [],
                    "erro": u"não consegui ler este arquivo"}

    @app.get("/api/verseg/contornos")
    def _contornos(b: str = "", uid: str = "", rs: str = "", corte: int = 0):
        pasta, uid = _pasta(b, uid)
        if not pasta:
            return {"rs": rs, "corte": corte, "estruturas": [],
                    "erro": u"a série não está mais aberta — recarregue a lista"}
        try:
            return contornos_do_corte(pasta, uid, rs, corte)
        except Exception as e:
            _falha(u"contornos", e, b)
            return {"rs": rs, "corte": corte, "estruturas": [],
                    "erro": u"não consegui ler este arquivo"}

    @app.get("/api/verseg/centro")
    def _centro(b: str = "", uid: str = "", rs: str = "", nome: str = ""):
        pasta, uid = _pasta(b, uid)
        if not pasta:
            return {"erro": u"a série não está mais aberta — recarregue a lista"}
        try:
            return centro_do_arquivo(pasta, uid, rs, nome)
        except Exception as e:
            _falha(u"centro", e, b)
            return {"erro": u"não consegui ler este arquivo"}

    @app.post("/api/verseg/recon3d")
    async def _para_a_reconstrucao(request: Request):
        try:
            c = await request.json() or {}
            b = str((c or {}).get("b") or "")
            pasta, uid = _pasta(b)
            if not pasta:
                return {"erro": u"a série não está mais aberta — recarregue a "
                                u"lista"}
            return await radai_web.no_threadpool(
                ficha_para_a_reconstrucao, pasta, uid,
                str((c or {}).get("rs") or ""),
                list((c or {}).get("estruturas") or [])[:2000])
        except Exception as e:
            _falha(u"reconstrução 3D", e, u"")
            return {"erro": u"não consegui preparar a Reconstrução 3D"}

    @app.post("/api/verseg/nuvem3d")
    async def _nuvem3d(request: Request):
        try:
            c = await request.json() or {}
            import radai_viewer3d
            return await radai_web.no_threadpool(
                radai_viewer3d.nuvem_da_serie,
                str(c.get("pasta") or ""), str(c.get("rs") or ""),
                list(c.get("estruturas") or []))
        except Exception as e:
            return {"itens": [], "erro": "%s: %s" % (type(e).__name__, str(e)[:200])}


    @app.post("/api/umeixo/abrir")
    async def _um_eixo_abrir(request: Request):
        try:
            c = await request.json() or {}
            return await radai_web.no_threadpool(
                abrir_um_eixo, c.get("pasta", ""), c.get("zip", ""),
                c.get("uid", ""))
        except Exception as e:
            import radai_thumbnail
            radai_thumbnail.registrar_falha(u"visor de um eixo, abrir", e)
            return {"erro": u"não consegui abrir a série",
                    "tipo": type(e).__name__}

    def _cab(t):
        return (t or u"").encode("ascii", "replace").decode("ascii")[:200]

    @app.get("/api/umeixo/corte")
    def _um_eixo_corte(request: Request, b: str = "", corte: int = 0,
                       janela: str = "mediastino"):
        import radai_thumbnail
        janela = str(janela or "mediastino")
        try:
            etag = radai_thumbnail.etiqueta_do_corte(
                b, corte, janela, radai_thumbnail.LADO_VISOR)
            anterior = (request.headers.get("if-none-match") or "").strip()
            cabs = {"Cache-Control": "private, max-age=86400"}
            if etag:
                cabs["ETag"] = _cab(etag)
                if anterior and anterior == etag:
                    return Response(status_code=304, headers=cabs)
            dados, info = radai_thumbnail.png(
                b, corte, janela, lado=radai_thumbnail.LADO_VISOR)
        except Exception as e:
            radai_thumbnail.registrar_falha(u"visor de um eixo, corte", e,
                                            bilhete=b)
            return Response(status_code=500,
                            headers={"X-RadAI-Erro": _cab(type(e).__name__)})
        if not dados:
            if info.get("sem_imagem"):
                status = 204
            elif info.get("cortes") is None:
                status = 404
            else:
                status = 422
            return Response(status_code=status,
                            headers={"X-RadAI-Erro": _cab(info.get("erro")),
                                     "Cache-Control": "no-store"})
        cabs["X-RadAI-Corte"] = str(info.get("corte", 0))
        cabs["X-RadAI-Cortes"] = str(info.get("cortes", 0))
        return Response(content=dados, media_type="image/png", headers=cabs)

    return app
