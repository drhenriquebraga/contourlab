# -*- coding: utf-8 -*-
import hashlib
import json
import os
import shutil
import time
from pathlib import Path

NOME_DA_PASTA = "cache_tasks"
TTL_DIAS = 14
TETO_GB = 20.0
FOLGA_DO_DISCO_GB = 5.0
VERSAO_DO_CACHE = 1
ARQUIVO_DOS_ROTULOS = "rotulos.npz"
ARQUIVO_DA_META = "meta.json"
_IMPRESSOES_DE_VOLUME = {}
_ARMADO = [False]


def armar(sim=True):
    _ARMADO[0] = bool(sim)


def armado():
    return bool(_ARMADO[0])


def pasta():
    bruto = (os.environ.get("RADAI_CACHE_TASKS_DIR") or "").strip().strip('"')
    if bruto:
        return Path(bruto)
    import radai_archive
    return Path(radai_archive.raiz()).parent / NOME_DA_PASTA


def _pastas_clinicas():
    saida = []
    try:
        import radai_config
        for k in ("ROOT", "OUT_DIR"):
            v = radai_config.chave_configurada(k)
            if v:
                saida.append(v)
    except Exception:
        pass
    return saida


def _dentro(p, raiz):
    try:
        a = os.path.normcase(os.path.abspath(str(p)))
        b = os.path.normcase(os.path.abspath(str(raiz)))
        return os.path.commonpath([a, b]) == b
    except Exception:
        return False


def conferir_pasta(p=None, clinicas=None):
    p = Path(p) if p is not None else pasta()
    try:
        import radai_archive
        sinc, _marca = radai_archive.em_pasta_sincronizada(str(p))
        if sinc:
            return False, (u"a pasta do cache sincroniza com a nuvem (%s): o "
                           u"cache fica desligado — dado derivado de paciente "
                           u"nao sai da estacao" % p)
        # GUARDA: mapa de rotulos de paciente nao vai a pasta de rede nem a
        # arvore das series (escrita no share exige combinar com a TI).
        if radai_archive._e_rede(str(p)):
            return False, (u"a pasta do cache e de rede: o cache fica "
                           u"desligado — dado derivado de paciente fica no "
                           u"disco desta estacao")
        for c in (_pastas_clinicas() if clinicas is None else clinicas):
            if _dentro(p, c):
                return False, (u"a pasta do cache fica dentro da pasta das "
                               u"series (ROOT ou OUT_DIR): o cache fica "
                               u"desligado")
    except Exception as e:
        return False, u"nao consegui conferir a pasta do cache (%s)" % (
            type(e).__name__,)
    return True, u""


def impressao_do_volume(img):
    import weakref
    chave = id(img)
    guardada = _IMPRESSOES_DE_VOLUME.get(chave)
    if guardada and guardada[0]() is img:
        return guardada[1]
    import numpy as np
    import SimpleITK as sitk
    h = hashlib.sha256()
    h.update(repr((tuple(img.GetSize()), tuple(round(float(v), 6) for v in
                                                img.GetSpacing()),
                   tuple(round(float(v), 4) for v in img.GetOrigin()),
                   tuple(round(float(v), 6) for v in img.GetDirection()),
                   img.GetPixelIDTypeAsString())).encode("utf-8"))
    # GUARDA: sem copia do volume -- a serie grande e onde a RAM aperta. A
    # vista e lida corte a corte, nos mesmos bytes que o `.tobytes()` daria.
    vista = sitk.GetArrayViewFromImage(img)
    if vista.flags.c_contiguous:
        h.update(memoryview(vista).cast("B"))
    else:
        for corte in vista:
            h.update(np.ascontiguousarray(corte).tobytes())
    del vista
    valor = h.hexdigest()
    _IMPRESSOES_DE_VOLUME.clear()
    try:
        # GUARDA: referencia fraca -- a imagem da serie nao fica viva no
        # vigia depois que a serie acaba.
        _IMPRESSOES_DE_VOLUME[chave] = (weakref.ref(img), valor)
    except TypeError:
        pass
    return valor


def _versao(dist):
    try:
        from importlib import metadata
        return metadata.version(dist)
    except Exception:
        return u"?"


def impressao_dos_pesos(task, recorte_no_corpo=True):
    partes = []
    try:
        import radai_tasks as _rt
        base = _rt.pasta_pesos()
        nums = sorted(_rt.datasets_necessarios(task, recorte_no_corpo) or ())
        nomes = sorted(os.listdir(base)) if base and os.path.isdir(base) else []
        for n in nums:
            pref = "Dataset%03d_" % int(n)
            achou = [d for d in nomes if d.startswith(pref)]
            for d in achou:
                tot, cont, mt = 0, 0, 0.0
                for raiz, _x, fs in os.walk(os.path.join(base, d)):
                    for f in fs:
                        try:
                            st = os.stat(os.path.join(raiz, f))
                        except OSError:
                            continue
                        tot += st.st_size
                        cont += 1
                        mt = max(mt, st.st_mtime)
                partes.append((d, cont, tot, int(mt)))
            if not achou:
                partes.append(("Dataset%03d" % int(n), 0, 0, 0))
    except Exception as e:
        partes.append(("?", type(e).__name__))
    return hashlib.sha256(repr(partes).encode("utf-8")).hexdigest()


def impressao_do_envelope(caminho):
    try:
        with open(str(caminho), "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()[:16]
    except Exception:
        return u"sem envelope"


def receita(task, recorte_no_corpo=False, caixa=None, envelope=None,
            codigo=None):
    return {"versao_do_cache": VERSAO_DO_CACHE,
            "codigo_da_grade": codigo or u"?",
            "totalsegmentator": _versao("TotalSegmentator"),
            "nnunetv2": _versao("nnunetv2"), "task": task,
            "pesos": impressao_dos_pesos(task, bool(recorte_no_corpo)),
            "body_seg": bool(recorte_no_corpo),
            "clip_box": [list(p) for p in (caixa or {}).get("zyx") or ()],
            "envelope": impressao_do_envelope(envelope) if envelope
            else u"sem envelope"}


def chave(impressao_volume, task, rec):
    base = json.dumps([impressao_volume, task, rec], sort_keys=True)
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def _livre_gb(p):
    try:
        return shutil.disk_usage(str(p)).free / 1e9
    except Exception:
        return None


def ler(ch, p=None):
    d = (Path(p) if p is not None else pasta()) / ch
    try:
        import numpy as np
        with open(str(d / ARQUIVO_DA_META), encoding="utf-8") as f:
            meta = json.load(f)
        with np.load(str(d / ARQUIVO_DOS_ROTULOS)) as z:
            arr = z["arr"]
        try:
            os.utime(str(d), None)
        except OSError:
            pass
        return arr, meta
    except Exception:
        return None


def gravar(ch, arr, meta, p=None):
    raiz = Path(p) if p is not None else pasta()
    ok, motivo = conferir_pasta(raiz)
    if not ok:
        return False, motivo
    try:
        import numpy as np
        raiz.mkdir(parents=True, exist_ok=True)
        livre = _livre_gb(raiz)
        tam = float(getattr(arr, "nbytes", 0)) / 1e9
        if livre is not None and livre < tam + FOLGA_DO_DISCO_GB:
            return False, (u"o disco do cache tem %.1f GB livres: nao gravo"
                           % livre)
        final = raiz / ch
        tmp = raiz / (u"_gravando_%s_%d" % (ch[:12], os.getpid()))
        if tmp.exists():
            shutil.rmtree(str(tmp), ignore_errors=True)
        tmp.mkdir()
        np.savez_compressed(str(tmp / ARQUIVO_DOS_ROTULOS),
                            arr=np.asarray(arr, dtype=np.int16))
        m = dict(meta or {})
        m["gravado_em"] = time.strftime("%Y-%m-%d %H:%M:%S")
        m["bytes"] = int(os.path.getsize(str(tmp / ARQUIVO_DOS_ROTULOS)))
        with open(str(tmp / ARQUIVO_DA_META), "w", encoding="utf-8") as f:
            json.dump(m, f, ensure_ascii=False)
        if final.exists():
            shutil.rmtree(str(final), ignore_errors=True)
        os.replace(str(tmp), str(final))
        return True, u""
    except Exception as e:
        return False, u"nao gravei no cache (%s: %s)" % (type(e).__name__,
                                                         str(e)[:120])


def _entradas(raiz):
    fora = []
    try:
        for nome in os.listdir(str(raiz)):
            d = os.path.join(str(raiz), nome)
            if not os.path.isdir(d):
                continue
            tam = 0
            for f in os.listdir(d):
                try:
                    tam += os.path.getsize(os.path.join(d, f))
                except OSError:
                    pass
            try:
                quando = os.path.getmtime(d)
            except OSError:
                quando = 0.0
            fora.append((quando, tam, d))
    except OSError:
        return []
    return sorted(fora)


def faxina(ttl_dias=TTL_DIAS, teto_gb=TETO_GB, agora=None, p=None):
    raiz = Path(p) if p is not None else pasta()
    agora = time.time() if agora is None else float(agora)
    apagadas = 0
    ents = _entradas(raiz)
    vivas = []
    for quando, tam, d in ents:
        if (agora - quando > ttl_dias * 86400.0
                or os.path.basename(d).startswith("_gravando_")
                and agora - quando > 3600.0):
            shutil.rmtree(d, ignore_errors=True)
            apagadas += 1
        else:
            vivas.append((quando, tam, d))
    total = sum(t for _q, t, _d in vivas)
    teto = float(teto_gb) * 1e9
    for quando, tam, d in list(vivas):
        if total <= teto:
            break
        shutil.rmtree(d, ignore_errors=True)
        apagadas += 1
        total -= tam
        vivas.remove((quando, tam, d))
    return {"apagadas": apagadas, "ocupado_gb": round(total / 1e9, 2),
            "entradas": len(vivas)}


def estado(p=None):
    raiz = Path(p) if p is not None else pasta()
    ok, motivo = conferir_pasta(raiz)
    ents = _entradas(raiz) if ok else []
    return {"pasta": str(raiz), "ligado": ok, "motivo": motivo,
            "entradas": len(ents),
            "ocupado_gb": round(sum(t for _q, t, _d in ents) / 1e9, 2),
            "ttl_dias": TTL_DIAS, "teto_gb": TETO_GB}
