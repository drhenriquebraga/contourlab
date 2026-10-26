# -*- coding: utf-8 -*-
import hashlib
import io
import json
import os
import sys
import tempfile

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

AQUI = os.path.dirname(os.path.abspath(__file__))


def pasta_app(aqui):
    for c in (os.path.join(aqui, "..", "app"), os.path.join(aqui, "..")):
        if os.path.exists(os.path.join(c, "engine.py")):
            return os.path.abspath(c)
    return os.path.abspath(os.path.join(aqui, "..", "app"))


sys.path.insert(0, pasta_app(AQUI))
sys.path.insert(0, AQUI)
os.environ["RADAI_CALIB_DIR"] = tempfile.mkdtemp(prefix="radai_ac_veloc_")
os.environ["RADAI_REGISTRO_DIR"] = tempfile.mkdtemp(prefix="radai_ac_veloc_reg_")
os.environ["TOTALSEG_HOME_DIR"] = tempfile.mkdtemp(prefix="radai_tshome_veloc_")
import _cleanup
_cleanup.adotar_prefixo("radai_ac_veloc_")
_cleanup.adotar_prefixo("radai_tshome_veloc_")
_cleanup.adotar_prefixo("radai_t_veloc_")

import numpy as np
import pydicom
from pydicom.dataset import Dataset, FileDataset
from pydicom.uid import ExplicitVRLittleEndian

import engine as E
import radai_output as RO

REFERENCIA = os.path.join(AQUI, "data", "velocidade_referencia.json")
_RESULTADOS = []
VERBOSO = "-v" in sys.argv


def checar(nome, condicao, detalhe=""):
    ok = bool(condicao)
    _RESULTADOS.append((nome, ok, detalhe))
    if VERBOSO or not ok:
        print("  %s  %s%s" % ("OK   " if ok else "FALHA", nome,
                              ("  [%s]" % detalhe) if detalhe else ""))
    return ok


Z, N, PX, ESP = 40, 112, 3.0, 5.0
RAIZ_UID = "1.2.826.0.1.3680043.8.498.7700"

_TOTAL = (
    "lung_upper_lobe_left", "lung_lower_lobe_left", "lung_upper_lobe_right",
    "lung_middle_lobe_right", "lung_lower_lobe_right", "heart", "aorta",
    "superior_vena_cava", "inferior_vena_cava", "pulmonary_vein", "trachea",
    "esophagus", "spinal_cord", "sternum", "liver", "stomach", "spleen",
    "kidney_left", "kidney_right", "small_bowel", "colon", "clavicula_left",
    "clavicula_right", "scapula_left", "scapula_right", "autochthon_left",
    "autochthon_right", "vertebrae_T6", "vertebrae_T8", "vertebrae_T10",
    "vertebrae_T12", "rib_left_5", "rib_right_5", "rib_left_8", "rib_right_8",
)
_CAVIDADES = ("abdominal_cavity", "mediastinum", "thoracic_cavity",
              "pericardium")


def _elipse(cy, cx, ry, rx):
    yy, xx = np.mgrid[0:N, 0:N]
    return ((yy - cy) / ry) ** 2 + ((xx - cx) / rx) ** 2 <= 1.0


def _anatomia():
    c = N / 2.0
    vol = np.full((Z, N, N), -1000, np.int16)
    tot = np.zeros((Z, N, N), np.int16)
    cav = np.zeros((Z, N, N), np.int16)
    corpo = _elipse(c, c, 34, 48)
    musculo = _elipse(c, c, 31, 45)
    pulmao_e = _elipse(c - 2, c + 21, 20, 15)
    pulmao_d = _elipse(c - 2, c - 21, 20, 15)
    for z in range(Z):
        vol[z][corpo] = -90
        vol[z][musculo] = 35
    idx = dict((n, i + 1) for i, n in enumerate(_TOTAL))

    def pinta(nome, zs, m, hu=None):
        for z in zs:
            tot[z][m & (tot[z] == 0)] = idx[nome]
            if hu is not None:
                vol[z][m] = hu

    sup = range(20, 36)
    inf = range(8, 20)
    pinta("lung_upper_lobe_left", sup, pulmao_e, -830)
    pinta("lung_lower_lobe_left", inf, pulmao_e, -830)
    pinta("lung_upper_lobe_right", range(25, 36), pulmao_d, -830)
    pinta("lung_middle_lobe_right", range(19, 25), pulmao_d, -830)
    pinta("lung_lower_lobe_right", inf, pulmao_d, -830)
    coracao = _elipse(c - 9, c + 5, 12, 14)
    pinta("heart", range(12, 26), coracao, 45)
    pinta("aorta", range(4, 34), _elipse(c + 10, c + 4, 4, 4), 190)
    pinta("aorta", range(30, 34), _elipse(c - 10, c + 2, 4, 4), 190)
    pinta("superior_vena_cava", range(24, 34), _elipse(c - 8, c - 7, 3, 3), 60)
    pinta("inferior_vena_cava", range(4, 13), _elipse(c, c - 8, 3, 3), 60)
    pinta("pulmonary_vein", range(19, 22), _elipse(c - 3, c + 12, 2, 5), 60)
    pinta("trachea", range(28, 40), _elipse(c - 6, c, 3, 3), -950)
    pinta("esophagus", range(4, 40), _elipse(c + 6, c - 1, 2, 2), 30)
    pinta("spinal_cord", range(0, 40), _elipse(c + 20, c, 2, 2), 30)
    pinta("sternum", range(14, 32), _elipse(c - 30, c, 2, 4), 600)
    pinta("liver", range(0, 10), _elipse(c, c - 16, 18, 22), 60)
    pinta("stomach", range(0, 9), _elipse(c - 6, c + 18, 9, 10), 25)
    pinta("spleen", range(0, 8), _elipse(c + 10, c + 30, 6, 6), 50)
    pinta("kidney_left", range(0, 4), _elipse(c + 14, c + 18, 5, 4), 35)
    pinta("kidney_right", range(0, 4), _elipse(c + 14, c - 18, 5, 4), 35)
    pinta("small_bowel", range(0, 3), _elipse(c - 14, c + 4, 8, 12), 20)
    pinta("colon", range(0, 4), _elipse(c - 22, c - 2, 4, 16), -300)
    pinta("clavicula_left", range(36, 40), _elipse(c - 22, c + 22, 2, 12), 700)
    pinta("clavicula_right", range(36, 40), _elipse(c - 22, c - 22, 2, 12), 700)
    pinta("scapula_left", range(24, 38), _elipse(c + 24, c + 30, 2, 10), 700)
    pinta("scapula_right", range(24, 38), _elipse(c + 24, c - 30, 2, 10), 700)
    pinta("autochthon_left", range(0, 40), _elipse(c + 26, c + 7, 4, 4), 40)
    pinta("autochthon_right", range(0, 40), _elipse(c + 26, c - 7, 4, 4), 40)
    corpo_vert = _elipse(c + 16, c, 5, 6)
    for i, nome in enumerate(("vertebrae_T12", "vertebrae_T10",
                              "vertebrae_T8", "vertebrae_T6")):
        pinta(nome, range(2 + 9 * i, 9 + 9 * i), corpo_vert, 750)
    anel = _elipse(c, c, 32, 46) & ~_elipse(c, c, 30, 44)
    for lado, sinal in (("left", 1), ("right", -1)):
        meia = np.zeros((N, N), bool)
        if sinal > 0:
            meia[:, int(c) + 3:] = True
        else:
            meia[:, :int(c) - 3] = True
        pinta("rib_%s_8" % lado, (14, 15), anel & meia, 700)
        pinta("rib_%s_5" % lado, (26, 27), anel & meia, 700)
    for z in range(Z):
        if z >= 8:
            cav[z][_elipse(c - 2, c, 26, 40) & (tot[z] != idx["sternum"])] = 3
            cav[z][_elipse(c - 4, c + 2, 10, 9)] = 2
        else:
            cav[z][_elipse(c, c, 26, 40)] = 1
        if 12 <= z < 26:
            cav[z][_elipse(c - 9, c + 5, 13, 15)] = 4
    idx_tot = dict((i, n) for n, i in idx.items())
    idx_cav = dict((i + 1, n) for i, n in enumerate(_CAVIDADES))
    return vol, tot, idx_tot, cav, idx_cav


def escrever_serie(pasta, vol):
    os.makedirs(pasta)
    estudo, serie, quadro = (RAIZ_UID + ".1", RAIZ_UID + ".2",
                             RAIZ_UID + ".3")
    for i in range(Z):
        meta = Dataset()
        meta.MediaStorageSOPClassUID = "1.2.840.10008.5.1.4.1.1.2"
        meta.MediaStorageSOPInstanceUID = "%s.4.%d" % (RAIZ_UID, i + 1)
        meta.TransferSyntaxUID = ExplicitVRLittleEndian
        meta.ImplementationClassUID = RAIZ_UID + ".5"
        ds = FileDataset(None, {}, file_meta=meta, preamble=b"\0" * 128)
        ds.SOPClassUID = meta.MediaStorageSOPClassUID
        ds.SOPInstanceUID = meta.MediaStorageSOPInstanceUID
        ds.Modality = "CT"
        ds.PatientName = "FANTOMA^VELOCIDADE"
        ds.PatientID = "PAC_VELOCIDADE"
        ds.PatientBirthDate = ""
        ds.PatientSex = "O"
        ds.StudyInstanceUID, ds.SeriesInstanceUID = estudo, serie
        ds.FrameOfReferenceUID = quadro
        ds.StudyID, ds.SeriesNumber, ds.InstanceNumber = "1", 1, i + 1
        ds.StudyDescription = "FANTOMA SINTETICO - TESTE RadAI"
        ds.SeriesDescription = "CT fantoma sintetico velocidade"
        ds.StudyDate = ds.SeriesDate = "20261025"
        ds.StudyTime = ds.SeriesTime = "120000"
        ds.ImagePositionPatient = [-N * PX / 2.0, -N * PX / 2.0, i * ESP]
        ds.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
        ds.PatientPosition = "HFS"
        ds.SliceThickness = ESP
        ds.SpacingBetweenSlices = ESP
        ds.PixelSpacing = [PX, PX]
        ds.Rows = ds.Columns = N
        ds.SamplesPerPixel = 1
        ds.PhotometricInterpretation = "MONOCHROME2"
        ds.BitsAllocated, ds.BitsStored, ds.HighBit = 16, 16, 15
        ds.PixelRepresentation = 1
        ds.RescaleIntercept, ds.RescaleSlope = 0, 1
        ds.PixelData = np.ascontiguousarray(vol[i]).tobytes()
        ds.save_as(os.path.join(pasta, "CT_%04d.dcm" % (i + 1)),
                   enforce_file_format=True)


def montar(base, rotulo):
    import SimpleITK as sitk
    vol, tot, idx_tot, cav, idx_cav = _anatomia()
    serie = os.path.join(base, "serie")
    if not os.path.isdir(serie):
        escrever_serie(serie, vol)
    ref = E.load_sitk(serie)
    hu = sitk.GetArrayFromImage(ref)
    cruas = {"total_v3": E.MasksCruas(tot, idx_tot),
             "trunk_cavities": E.MasksCruas(cav, idx_cav)}
    dest = os.path.join(base, "saida_" + rotulo)
    os.makedirs(dest)
    linhas = []
    sd = RO.Saida(E, serie, dest, "RS_RadAI_20261025_velocida.dcm",
                  tasks=["total_v3", "trunk_cavities"], versao="bateria",
                  suavizar_mm=1.0, log=lambda m: linhas.append(u"%s" % m),
                  modalidade="CT")
    sd.devolver_mascaras = True
    r = sd.full_e_oar(cruas, volume_hu=hu, cads={}, cervicais=None,
                      modo="auto", extras=None)
    ms = dict((getattr(sd, "meta_do_full", None) or {}).get("mascaras") or {})
    return r, ms, linhas


def _hash(*partes):
    h = hashlib.sha256()
    for p in partes:
        h.update(p if isinstance(p, bytes) else str(p).encode("utf-8"))
        h.update(b"|")
    return h.hexdigest()[:24]


def impressao_do_rtstruct(caminho):
    ds = pydicom.dcmread(caminho)
    nomes = dict((int(r.ROINumber), str(r.ROIName))
                 for r in ds.StructureSetROISequence)
    ordem = [(int(r.ROINumber), str(r.ROIName))
             for r in ds.StructureSetROISequence]
    rois = {}
    for rc in getattr(ds, "ROIContourSequence", None) or []:
        num = int(rc.ReferencedROINumber)
        partes = [str(list(rc.ROIDisplayColor))]
        for c in getattr(rc, "ContourSequence", None) or []:
            ref = ""
            for it in getattr(c, "ContourImageSequence", None) or []:
                ref = str(it.ReferencedSOPInstanceUID)
            el = c["ContourData"]
            partes.append("%s;%s;%s;%s" % (
                c.ContourGeometricType, c.NumberOfContourPoints, ref,
                "\\".join(str(v) for v in el.value)))
        rois[nomes.get(num, str(num))] = _hash(*partes)
    return {"ordem": ordem, "rois": rois}


def impressao_das_mascaras(ms):
    fora = {}
    for k in sorted(ms, key=str):
        m = np.asarray(ms[k], dtype=bool)
        fora[str(k)] = _hash(m.shape, np.packbits(m.ravel()).tobytes())
    return fora


def impressao(r, ms):
    return {"study": impressao_do_rtstruct(r["oar"]),
            "full": impressao_do_rtstruct(r["full"]),
            "mascaras": impressao_das_mascaras(ms)}


def diferencas(a, b):
    dif = []
    for conj in ("study", "full"):
        if [list(x) for x in a[conj]["ordem"]] != \
                [list(x) for x in b[conj]["ordem"]]:
            dif.append(u"%s: a ordem das ROIs" % conj)
        for k in sorted(set(a[conj]["rois"]) | set(b[conj]["rois"])):
            if a[conj]["rois"].get(k) != b[conj]["rois"].get(k):
                dif.append(u"%s: contornos de %s" % (conj, k))
    for k in sorted(set(a["mascaras"]) | set(b["mascaras"])):
        if a["mascaras"].get(k) != b["mascaras"].get(k):
            dif.append(u"mascara de %s" % k)
    return dif


def versoes():
    import scipy
    import SimpleITK as sitk
    try:
        import cv2
        v_cv = cv2.__version__
    except Exception:
        v_cv = u"?"
    try:
        from importlib import metadata
        v_rt = metadata.version("rt_utils")
    except Exception:
        v_rt = u"?"
    return {"numpy": np.__version__, "scipy": scipy.__version__,
            "pydicom": pydicom.__version__, "opencv": v_cv,
            "SimpleITK": sitk.Version_VersionString(), "rt_utils": v_rt}


def _so_o_pydicom():
    salvos = (E._gravar_pontos, E._pontos_lidos_em_float, E._adicionar_roi)

    def _gravar(c, valores):
        c.ContourData = valores

    def _add_roi_do_rt_utils(rt, mb, nome, cor):
        rt.add_roi(mask=mb, name=nome, color=cor)

    E._gravar_pontos = _gravar
    E._pontos_lidos_em_float = lambda ds: None
    E._adicionar_roi = _add_roi_do_rt_utils
    return salvos


def _devolver(salvos):
    E._gravar_pontos, E._pontos_lidos_em_float, E._adicionar_roi = salvos


def _sabotar_um_voxel():
    original = E._suavizar_individuais
    feito = []

    def _um_voxel_a_menos(masks, nomes, *a, **kw):
        tratadas = original(masks, nomes, *a, **kw)
        for nm in sorted(tratadas, key=str):
            m = np.asarray(masks[nm], dtype=bool)
            if feito or int(m.sum()) < 50:
                continue
            m = m.copy()
            m[tuple(int(v[0]) for v in np.nonzero(m))] = False
            masks[nm] = m
            feito.append(str(nm))
        return tratadas

    E._suavizar_individuais = _um_voxel_a_menos
    return original, feito


def _contra_a_referencia(base, agora):
    with io.open(REFERENCIA, encoding="utf-8") as f:
        ref = json.load(f)
    v_ref, v_agora = ref.get("versoes") or {}, versoes()
    outras = sorted(k for k in set(v_ref) | set(v_agora)
                    if v_ref.get(k) != v_agora.get(k))
    if outras:
        print(u"  PULADO: a comparacao com a montagem de antes da otimizacao "
              u"(%s) — as bibliotecas desta maquina nao sao as da referencia "
              u"(%s)" % (os.path.basename(REFERENCIA), u", ".join(
                  u"%s %s != %s" % (k, v_agora.get(k), v_ref.get(k))
                  for k in outras)))
        return
    dif_ref = diferencas(ref["impressao"], agora)
    checar(u"FULL, STUDY e mascaras identicos a montagem de antes da "
           u"otimizacao, estrutura a estrutura (%d no FULL)"
           % len(agora["full"]["rois"]), not dif_ref, u"; ".join(dif_ref[:6]))
    isca = json.loads(json.dumps(ref["impressao"]))
    nome = sorted(isca["mascaras"])[0]
    isca["mascaras"][nome] = _hash(u"um voxel a mais")
    checar(u"ISCA: a referencia com uma mascara trocada e acusada",
           diferencas(isca, agora) == [u"mascara de %s" % nome])


def _contra_o_pydicom(base, agora):
    salvos = _so_o_pydicom()
    try:
        r2, ms2, _l2 = montar(base, "pydicom")
    finally:
        _devolver(salvos)
    dif = diferencas(agora, impressao(r2, ms2))
    checar(u"o ContourData pelo caminho rapido e o mesmo do pydicom e do "
           u"add_roi do rt_utils, valor a valor (FULL, STUDY e mascaras)",
           not dif, u"; ".join(dif[:6]))
    checar(u"e o caminho rapido rodou de verdade (o rt_utils desta maquina e "
           u"o %s da montagem rapida)" % E.RT_UTILS_DA_MONTAGEM_RAPIDA,
           E._rt_utils_instalado() == E.RT_UTILS_DA_MONTAGEM_RAPIDA,
           E._rt_utils_instalado())


def _isca_de_um_voxel(base, agora):
    original, feito = _sabotar_um_voxel()
    try:
        r3, ms3, _l3 = montar(base, "isca")
    finally:
        E._suavizar_individuais = original
    dif3 = diferencas(agora, impressao(r3, ms3))
    checar(u"ISCA: uma otimizacao que tira UM voxel de uma estrutura e "
           u"acusada (na mascara e no contorno)",
           feito and any(d.startswith(u"mascara") for d in dif3)
           and any(u"contornos" in d for d in dif3),
           u"tirado de %s; acusado: %s" % (u", ".join(feito),
                                           u"; ".join(dif3[:4])))


def main():
    if "--gravar-referencia" in sys.argv:
        base = tempfile.mkdtemp(prefix="radai_t_veloc_")
        r, ms, _l = montar(base, "ref")
        dados = {"versoes": versoes(), "impressao": impressao(r, ms)}
        os.makedirs(os.path.dirname(REFERENCIA), exist_ok=True)
        with io.open(REFERENCIA, "w", encoding="utf-8") as f:
            json.dump(dados, f, ensure_ascii=False, indent=1, sort_keys=True)
        print(u"referencia gravada: %d estruturas no FULL, %d no STUDY, %d "
              u"mascaras" % (len(dados["impressao"]["full"]["rois"]),
                             len(dados["impressao"]["study"]["rois"]),
                             len(dados["impressao"]["mascaras"])))
        return 0

    print(u"\n-- a montagem do FULL e do STUDY: o caminho rapido entrega o "
          u"mesmo voxel e o mesmo contorno --")
    base = tempfile.mkdtemp(prefix="radai_t_veloc_")
    r, ms, _linhas = montar(base, "rapido")
    agora = impressao(r, ms)
    checar(u"o fantoma da um FULL e um STUDY de verdade",
           len(agora["full"]["rois"]) >= 20
           and len(agora["study"]["rois"]) >= 10
           and len(agora["mascaras"]) >= 20,
           u"FULL %d, STUDY %d, mascaras %d" % (
               len(agora["full"]["rois"]), len(agora["study"]["rois"]),
               len(agora["mascaras"])))
    checar(u"e o FULL foi gravado inteiro", not r.get("parcial"),
           str(r.get("parcial")))
    for parte in (_contra_a_referencia, _contra_o_pydicom, _isca_de_um_voxel):
        try:
            parte(base, agora)
        except Exception as e:
            import traceback
            checar(u"%s (excecao inesperada)" % parte.__name__, False,
                   u"%s: %s" % (type(e).__name__, e))
            traceback.print_exc()

    falhas = [(n, d) for n, ok, d in _RESULTADOS if not ok]
    print("\n" + "=" * 64)
    if falhas:
        print("FALHOU: %d de %d checagens" % (len(falhas), len(_RESULTADOS)))
        for n, d in falhas:
            print("  - %s%s" % (n, ("  [%s]" % d) if d else ""))
    else:
        print("OK: %d checagens, todas passaram" % len(_RESULTADOS))
    print("=" * 64)
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
