# -*- coding: utf-8 -*-
import json
import os
import subprocess
import sys
import tempfile

VERSAO_FASE = "1.0"

FASES = ("native", "arterial_early", "arterial_late", "portal_venous",
         "delayed")

ROTULO_FASE = {
    "native": u"sem contraste",
    "arterial_early": u"arterial precoce",
    "arterial_late": u"arterial tardia",
    "portal_venous": u"portal-venosa",
    "delayed": u"tardia",
}

MODALIDADES = ("ct", "mr")


def _exe(python_exe=None):
    return python_exe or sys.executable


def _desligar_estatistica():
    try:
        import engine
        r = engine.estatistica_do_ts(desligar=True)
    except Exception as e:
        return (u"nao consegui desligar a estatistica de uso do "
                u"TotalSegmentator (%s: %s)" % (type(e).__name__, str(e)[:120]))
    if r.get("valor") is False:
        return u""
    return (u"a estatistica de uso do TotalSegmentator nao ficou desligada: %s"
            % (r.get("erro") or u"o arquivo continua sem send_usage_stats=false"))


def _rodar(modulo, args, python_exe=None, timeout_s=900):
    motivo = _desligar_estatistica()
    if motivo:
        return None, (u"nao rodei %s: %s -- o CLI faria uma chamada de rede "
                      u"para stats.totalsegmentator.com" % (modulo, motivo))[:300]
    saida = None
    try:
        fd, saida = tempfile.mkstemp(suffix=".json", prefix="radai_fase_")
        os.close(fd)
        cmd = [_exe(python_exe), "-m", modulo] + list(args) + ["-o", saida, "-q"]
        r = subprocess.run(cmd, capture_output=True, timeout=timeout_s)
        if r.returncode != 0:
            msg = (r.stderr or b"").decode("utf-8", "replace").strip()
            ult = msg.splitlines()[-1] if msg else u"codigo %d" % r.returncode
            return None, ult[:200]
        with open(saida, encoding="utf-8") as f:
            return json.load(f), u""
    except subprocess.TimeoutExpired:
        return None, u"passou de %d s" % timeout_s
    except Exception as e:
        return None, u"%s: %s" % (type(e).__name__, e)
    finally:
        if saida:
            try:
                os.unlink(saida)
            except OSError:
                pass


def modalidade(nifti, python_exe=None, dispositivo="cpu"):
    d, erro = _rodar("totalsegmentator.bin.totalseg_get_modality",
                     ["-i", str(nifti), "-d", dispositivo],
                     python_exe=python_exe, timeout_s=600)
    if erro:
        return u"", erro
    m = str((d or {}).get("modality") or "").strip().lower()
    if m not in MODALIDADES:
        return u"", u"modalidade nao reconhecida: %r" % m
    return m, u""


def fase(nifti, estatisticas=None, python_exe=None, dispositivo="cpu"):
    args = ["-i", str(nifti), "-d", dispositivo]
    if estatisticas and os.path.isfile(str(estatisticas)):
        args += ["-s", str(estatisticas)]
    d, erro = _rodar("totalsegmentator.bin.totalseg_get_phase", args,
                     python_exe=python_exe, timeout_s=1800)
    if erro:
        return {}, erro
    f = str((d or {}).get("phase") or "").strip().lower()
    if f not in FASES:
        return {}, u"fase nao reconhecida: %r" % f
    return {"fase": f,
            "rotulo": ROTULO_FASE.get(f, f),
            "probabilidade": (d or {}).get("probability"),
            "pi_time": (d or {}).get("pi_time"),
            "com_contraste": f != "native"}, u""


def conferir_contraste(tasks, medida, catalogo=None):
    import radai_tasks
    cat = catalogo or radai_tasks.CONTRASTE_TASK
    fora = []
    if not medida or not medida.get("fase"):
        return fora
    tem = bool(medida.get("com_contraste"))
    for t in (tasks or ()):
        precisa = cat.get(t)
        if precisa == "exige" and not tem:
            fora.append({
                "task": t, "gravidade": "alta",
                "texto": (u"`%s` exige contraste e a série foi medida como "
                          u"%s. O limite que ela procura não existe nesta "
                          u"imagem." % (t, medida.get("rotulo")))})
        elif precisa == "ajuda" and not tem:
            fora.append({
                "task": t, "gravidade": "baixa",
                "texto": (u"`%s` sai sem contraste e sai melhor com ele. "
                          u"Série medida como %s."
                          % (t, medida.get("rotulo")))})
    return fora


def disponivel(python_exe=None):
    try:
        r = subprocess.run(
            [_exe(python_exe), "-c",
             "import xgboost, totalsegmentator.bin.totalseg_get_modality"],
            capture_output=True, timeout=120)
        if r.returncode == 0:
            return True, u""
        msg = (r.stderr or b"").decode("utf-8", "replace").strip()
        return False, (msg.splitlines()[-1] if msg else u"nao importa")[:160]
    except Exception as e:
        return False, u"%s: %s" % (type(e).__name__, e)
