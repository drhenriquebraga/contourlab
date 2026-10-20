# -*- coding: utf-8 -*-
import hashlib
import os
import shutil
import sys
import tempfile
import threading

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

AQUI = os.path.dirname(os.path.abspath(__file__))


def pasta_app(aqui):
    for c in (os.path.join(aqui, "..", "app"), os.path.join(aqui, "..")):
        if os.path.exists(os.path.join(c, "radai_watcher.py")):
            return os.path.abspath(c)
    return os.path.abspath(os.path.join(aqui, "..", "app"))


APP = pasta_app(AQUI)
sys.path.insert(0, AQUI)
sys.path.insert(0, APP)

import numpy as np
import pydicom
from pydicom.dataset import Dataset
from pydicom.uid import generate_uid

import _cleanup
_cleanup.adotar_prefixo("radai_cdd_")
_cleanup.adotar_prefixo("radai_cdd_acervo_")
_cleanup.adotar_prefixo("radai_x_")
_cleanup.adotar_prefixo("radai_y_")
_cleanup.adotar_prefixo("radai_z_")
_cleanup.adotar_prefixo("radai_viz_")
_cleanup.adotar_prefixo("radai_falha_")
_cleanup.adotar_prefixo("radai_isca_")
_cleanup.adotar_prefixo("radai_monaco_")
_cleanup.adotar_prefixo("radai_serie_")
os.environ["RADAI_CALIB_DIR"] = tempfile.mkdtemp(prefix="radai_cdd_acervo_")

import engine
import radai_archive
import _componentes

VERBOSO = "-v" in sys.argv
_RESULTADOS = []


def checar(nome, condicao, detalhe=""):
    ok = bool(condicao)
    _RESULTADOS.append((nome, ok, detalhe))
    if VERBOSO or not ok:
        print("  %s  %s%s" % ("OK   " if ok else "FALHA", nome,
                              ("  [%s]" % detalhe) if detalhe else ""))
    return ok


def temp(prefixo="radai_cdd_"):
    return _cleanup.temporaria(prefixo)


LADO = 64
PIXEL_MM = 2.0
CORTE_MM = 3.0


def _corte(i, n):
    yy, xx = np.mgrid[0:LADO, 0:LADO]
    r = np.sqrt((yy - LADO / 2.0) ** 2 + (xx - LADO / 2.0) ** 2)
    img = np.full((LADO, LADO), -1000, dtype=np.int16)
    img[r < LADO * 0.4] = 0
    img[r < LADO * 0.4] += int(20 * np.sin(3.14 * i / max(1, n)))
    return img


def serie_da_clinica(pasta, n=24, com_dir=True, embaralhar=True,
                     nome="FANTOMA^SINTETICO", repertorio="ISO_IR 100"):
    os.makedirs(pasta, exist_ok=True)
    estudo, serie, quadro = generate_uid(), generate_uid(), generate_uid()
    arquivos, sops = [], []
    ordem = list(range(n))
    if embaralhar:
        ordem = ordem[::2] + ordem[1::2]
    escritos = {}
    for i in ordem:
        ds = Dataset()
        ds.SpecificCharacterSet = repertorio
        ds.SOPClassUID = "1.2.840.10008.5.1.4.1.1.2"
        ds.SOPInstanceUID = generate_uid()
        ds.StudyDate = ds.SeriesDate = "20260930"
        ds.StudyTime = ds.SeriesTime = "120000"
        ds.Modality = "CT"
        ds.PatientName = nome
        ds.PatientID = "FANTOMA_CDD"
        ds.StudyInstanceUID = estudo
        ds.SeriesInstanceUID = serie
        ds.FrameOfReferenceUID = quadro
        ds.StudyID = "1"
        ds.SeriesNumber = 2
        ds.InstanceNumber = i + 1
        ds.ImagePositionPatient = [-LADO * PIXEL_MM / 2.0,
                                   -LADO * PIXEL_MM / 2.0, i * CORTE_MM]
        ds.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
        ds.PatientPosition = "HFS"
        ds.SliceThickness = CORTE_MM
        ds.PixelSpacing = [PIXEL_MM, PIXEL_MM]
        ds.Rows = ds.Columns = LADO
        ds.SamplesPerPixel = 1
        ds.PhotometricInterpretation = "MONOCHROME2"
        ds.BitsAllocated = ds.BitsStored = 16
        ds.HighBit = 15
        ds.PixelRepresentation = 1
        ds.RescaleIntercept = 0
        ds.RescaleSlope = 1
        ds.PixelData = _corte(i, n).tobytes()
        caminho = os.path.join(pasta, "CT_%s" % ds.SOPInstanceUID)
        pydicom.dcmwrite(caminho, ds, implicit_vr=True, little_endian=True,
                         enforce_file_format=False)
        escritos[i] = (caminho, ds.SOPInstanceUID)
    for i in range(n):
        arquivos.append(escritos[i][0])
        sops.append(escritos[i][1])
    if com_dir:
        with open(os.path.join(pasta, "RTDIR.dir"), "w", encoding="ascii") as f:
            f.write("!Version 1\nIndice inventado para teste\n")
        with open(os.path.join(pasta, "CT_%s.dir" % serie), "w",
                  encoding="ascii") as f:
            f.write("%s\n" % serie + "\n".join(os.path.basename(a)
                                               for a in arquivos) + "\n")
    return serie, arquivos, sops


def _hashes(pasta):
    saida = {}
    for nome in sorted(os.listdir(pasta)):
        with open(os.path.join(pasta, nome), "rb") as f:
            saida[nome] = hashlib.sha1(f.read()).hexdigest()
    return saida


def _tem_preambulo(caminho):
    with open(caminho, "rb") as f:
        return f.read(132)[128:132] == b"DICM"


def _esfera(forma, raio, centro=None):
    nz, ny, nx = forma
    c = centro or (nz / 2.0, ny / 2.0, nx / 2.0)
    zz, yy, xx = np.ogrid[0:nz, 0:ny, 0:nx]
    return (((zz - c[0]) * CORTE_MM) ** 2 + ((yy - c[1]) * PIXEL_MM) ** 2
            + ((xx - c[2]) * PIXEL_MM) ** 2) <= raio ** 2


def _copia_de_antes(arquivos, destino):
    os.makedirs(destino, exist_ok=True)
    for i, f in enumerate(engine.sort_dcm(arquivos)):
        shutil.copy(f, os.path.join(destino, "slice_%04d.dcm" % i))


def teste_copia_local_vira_parte_10():
    pasta = os.path.join(temp(), "SEM_DCM")
    uid, arquivos, sops = serie_da_clinica(pasta)
    antes = _hashes(pasta)
    stage = temp()
    engine.copy_sorted(list(reversed(arquivos)), stage)
    copiados = sorted(os.listdir(stage))
    checar("copia local: um arquivo por corte", len(copiados) == len(arquivos),
           "%d de %d" % (len(copiados), len(arquivos)))
    checar("copia local: todo corte ganha o preambulo e a meta (Parte 10)",
           all(_tem_preambulo(os.path.join(stage, c)) for c in copiados))
    lidos = [pydicom.dcmread(os.path.join(stage, c), stop_before_pixels=True)
             for c in copiados]
    checar("copia local: os MESMOS SOPInstanceUID, na ordem de z",
           [str(d.SOPInstanceUID) for d in lidos] == sops)
    checar("copia local: a meta concorda com o corte",
           all(str(d.file_meta.MediaStorageSOPInstanceUID) == str(d.SOPInstanceUID)
               and str(d.file_meta.MediaStorageSOPClassUID) == str(d.SOPClassUID)
               for d in lidos))
    checar("copia local: o mesmo SeriesInstanceUID",
           all(str(d.SeriesInstanceUID) == uid for d in lidos))
    checar("copia local: os pixels nao mudam",
           np.array_equal(pydicom.dcmread(os.path.join(stage, copiados[5]))
                          .pixel_array, _corte(5, len(arquivos))))
    checar("os originais ficam intocados (nada renomeado, nada acrescentado)",
           _hashes(pasta) == antes)


def teste_copia_local_preserva_quem_ja_tem_preambulo():
    from make_test_series import escreve_serie
    from datetime import datetime
    pasta = os.path.join(temp(), "COM_DCM")
    escreve_serie(pasta, "FANTOMA_P10", datetime(2026, 9, 30), 22)
    arquivos = sorted(os.path.join(pasta, a) for a in os.listdir(pasta))
    stage = temp()
    engine.copy_sorted(arquivos, stage)
    origem = set(_hashes(pasta).values())
    copia = set(_hashes(stage).values())
    checar("arquivo que ja e Parte 10 e copiado byte a byte", origem == copia)


def teste_ordem_da_serie_sem_preambulo():
    pasta = os.path.join(temp(), "SEM_DCM_ORDEM")
    _uid, arquivos, _sops = serie_da_clinica(pasta, n=12)
    embaralhados = sorted(arquivos)
    ordenados = engine.sort_dcm(embaralhados)
    checar("sort_dcm ordena pelo z a serie sem preambulo",
           ordenados == arquivos)


def teste_rtstruct_da_serie_sem_preambulo():
    pasta = os.path.join(temp(), "SEM_DCM_RS")
    _uid, arquivos, sops = serie_da_clinica(pasta)
    stage = temp()
    engine.copy_sorted(arquivos, stage)
    img = engine.load_sitk(stage)
    forma = tuple(int(v) for v in reversed(img.GetSize()))
    mascara = _esfera(forma, 18.0)
    rs = None
    erro = ""
    try:
        rs, _nomes = engine.build_rtstruct(stage, {"liver": mascara},
                                           versao_worker="teste",
                                           descontar=False)
    except Exception as e:
        erro = "%s: %s" % (type(e).__name__, str(e)[:120])
    checar("o RTSTRUCT sai da serie sem preambulo", rs and os.path.isfile(rs),
           erro)
    if rs:
        ds = pydicom.dcmread(rs)
        refs = set()
        for fr in ds.ReferencedFrameOfReferenceSequence:
            for st in fr.RTReferencedStudySequence:
                for se in st.RTReferencedSeriesSequence:
                    for im in se.ContourImageSequence:
                        refs.add(str(im.ReferencedSOPInstanceUID))
        checar("o RTSTRUCT referencia os cortes ORIGINAIS (os mesmos UIDs)",
               refs == set(sops), "%d de %d" % (len(refs & set(sops)), len(sops)))

    isca = temp()
    _copia_de_antes(arquivos, isca)
    caiu = False
    try:
        engine.build_rtstruct(isca, {"liver": mascara}, versao_worker="teste",
                              descontar=False)
    except Exception:
        caiu = True
    checar("isca: a copia de antes (bytes como estao) nao grava o RTSTRUCT",
           caiu)


def teste_espacamento_le_sem_preambulo():
    pasta = temp()
    _uid, arquivos, _sops = serie_da_clinica(os.path.join(pasta, "x"), n=6,
                                             com_dir=False)
    crus = os.path.join(pasta, "crus")
    os.makedirs(crus)
    for i, a in enumerate(arquivos):
        shutil.copy(a, os.path.join(crus, "slice_%04d.dcm" % i))
    dx, dy = engine._espacamento_no_plano(crus, padrao=9.0)
    checar("o espacamento no plano le o corte sem preambulo",
           (dx, dy) == (PIXEL_MM, PIXEL_MM), "%r" % ((dx, dy),))


class _Ambiente(object):
    def __init__(self, **kv):
        self.kv = kv
        self.antes = {}

    def __enter__(self):
        for k, v in self.kv.items():
            self.antes[k] = os.environ.get(k)
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        return self

    def __exit__(self, *a):
        for k, v in self.antes.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def teste_tps_de_destino():
    pasta = temp()
    cfg = os.path.join(pasta, "radai_watcher.config")
    casos = [("TPS_DESTINO=Monaco\n", "monaco"),
             ("TPS_DESTINO=eclipse   # o de sempre\n", "eclipse"),
             ("TPS_DESTINO=pinnacle\n", "eclipse"),
             ("ROOT=\n", "eclipse")]
    for texto, esperado in casos:
        with open(cfg, "w", encoding="utf-8") as f:
            f.write(texto)
        with _Ambiente(RADAI_CONFIG=cfg, RADAI_TPS_DESTINO=None):
            obtido = engine.tps_destino()
        checar("TPS de destino pelo config: %r -> %s" % (texto.strip(), esperado),
               obtido == esperado, obtido)
    with _Ambiente(RADAI_CONFIG=os.path.join(pasta, "nao_existe.config"),
                   RADAI_TPS_DESTINO="MONACO"):
        checar("RADAI_TPS_DESTINO vence o config",
               engine.tps_destino() == "monaco")


def teste_tps_nao_escolhido_avisa_a_cada_gravacao():
    pasta = temp()
    cfg = os.path.join(pasta, "radai_watcher.config")
    with open(cfg, "w", encoding="utf-8") as f:
        f.write("TPS_DESTINO=\n")
    stage = _cenario_tps()["stage"]
    alvo = _cenario_tps()["alvo"]
    resultados = {}
    for rotulo, amb in (("vazio", dict(RADAI_CONFIG=cfg,
                                       RADAI_TPS_DESTINO=None)),
                        ("eclipse", dict(RADAI_CONFIG=cfg,
                                         RADAI_TPS_DESTINO="eclipse")),
                        ("monaco", dict(RADAI_CONFIG=cfg,
                                        RADAI_TPS_DESTINO="monaco"))):
        linhas = []
        with _Ambiente(**amb):
            escolhido = engine.tps_escolhido()
            engine.build_rtstruct(stage, {"liver": alvo},
                                  versao_worker="teste", descontar=False,
                                  log=linhas.append)
        resultados[rotulo] = (escolhido, linhas)
    escolhido, linhas = resultados["vazio"]
    checar("TPS_DESTINO vazio: nao escolhido, e a gravacao avisa no log",
           not escolhido and any(engine.AVISO_DO_TPS_NAO_ESCOLHIDO in l
                                 for l in linhas))
    escolhido, linhas = resultados["eclipse"]
    checar("  ISCA: com o Eclipse escolhido, nenhum aviso",
           escolhido and not any(engine.AVISO_DO_TPS_NAO_ESCOLHIDO in l
                                 for l in linhas))
    import radai_config
    rot_e = radai_config.rotulo_do_tps("eclipse")
    rot_m = radai_config.rotulo_do_tps("monaco")
    checar("o aviso chama as duas opcoes pelo nome da tela (%s; %s)"
           % (rot_e, rot_m),
           rot_e and rot_m and rot_e in engine.AVISO_DO_TPS_NAO_ESCOLHIDO
           and rot_m in engine.AVISO_DO_TPS_NAO_ESCOLHIDO
           and u"Num Monaco" not in engine.AVISO_DO_TPS_NAO_ESCOLHIDO,
           engine.AVISO_DO_TPS_NAO_ESCOLHIDO)

    def _diz_o_tps(linhas, valor):
        rot = radai_config.rotulo_do_tps(valor)
        return (any(l.startswith(u"TPS de destino %s:" % rot)
                    and u"Implicit VR Little Endian" in l for l in linhas)
                and not any(u"TPS de destino Monaco" in l for l in linhas))
    for valor in ("eclipse", "monaco"):
        _e, linhas = resultados[valor]
        checar("TPS_DESTINO=%s: o log diz o TPS pelo nome da tela e a "
               "sintaxe Implicit VR, que vale para os dois" % valor,
               _diz_o_tps(linhas, valor),
               [l for l in linhas if u"TPS de destino" in l][:2])
    velha = [u"TPS de destino Monaco: 2 furo(s) por fenda, texto so ASCII, "
             u"Implicit VR Little Endian"]
    checar("  ISCA: a linha de antes, que chamava o valor monaco de Monaco, "
           "reprova", not _diz_o_tps(velha, "monaco"))


def _enrolamento(p, xy):
    x, y = p
    w = 0
    n = len(xy)
    for k in range(n):
        x0, y0 = xy[k]
        x1, y1 = xy[(k + 1) % n]
        lado = (x1 - x0) * (y - y0) - (x - x0) * (y1 - y0)
        if y0 <= y < y1 and lado > 0:
            w += 1
        elif y1 <= y < y0 and lado < 0:
            w -= 1
    return w


def _sem_inverter(pai, furo):
    from scipy.spatial import cKDTree
    dist, j = cKDTree(furo[:, :2]).query(pai[:, :2])
    i = int(np.argmin(dist))
    j = int(j[i])
    return np.concatenate([pai[:i + 1], furo[j:], furo[:j + 1], pai[i:]])


def _anel_com_ilha(forma, z0, z1):
    nz, ny, nx = forma
    zz, yy, xx = np.ogrid[0:nz, 0:ny, 0:nx]
    r = np.sqrt(((yy - ny / 2.0) * PIXEL_MM) ** 2
                + ((xx - nx / 2.0) * PIXEL_MM) ** 2)
    faixa = (zz >= z0) & (zz <= z1)
    anel = (r <= 22.0) & (r >= 12.0) & faixa
    ilha = (r <= 5.0) & faixa
    return np.ascontiguousarray(anel | ilha)


_CENARIO_TPS = {}


def _cenario_tps():
    if _CENARIO_TPS:
        return _CENARIO_TPS
    pasta = os.path.join(temp(), "PAC_TPS", "CT")
    _uid, arquivos, _sops = serie_da_clinica(pasta, n=20,
                                             nome=u"JOÃO^FANTOMA")
    stage = temp()
    engine.copy_sorted(arquivos, stage)
    img = engine.load_sitk(stage)
    forma = tuple(int(v) for v in reversed(img.GetSize()))
    alvo = _anel_com_ilha(forma, 6, 13)
    saidas = {}
    for tps in ("eclipse", "monaco"):
        with _Ambiente(RADAI_TPS_DESTINO=tps):
            rs, mapa = engine.build_rtstruct(
                stage, {"liver": alvo}, versao_worker="teste",
                descontar=False,
                observacoes={"liver": u"não aprovado — 5 cm³ ±1 °"})
        destino = os.path.join(temp(), "RS_%s.dcm" % tps)
        shutil.copy2(rs, destino)
        saidas[tps] = (destino, mapa["liver"])
    _CENARIO_TPS.update({"pasta": pasta, "stage": stage, "forma": forma,
                         "alvo": alvo, "saidas": saidas})
    return _CENARIO_TPS


def _contornos_por_z(rs, nome):
    ds = pydicom.dcmread(rs)
    num = [int(s.ROINumber) for s in ds.StructureSetROISequence
           if str(s.ROIName) == nome][0]
    rc = [r for r in ds.ROIContourSequence
          if int(r.ReferencedROINumber) == num][0]
    por_z = {}
    for c in rc.ContourSequence:
        p = np.asarray([float(v) for v in c.ContourData]).reshape(-1, 3)
        por_z.setdefault(round(float(p[0, 2]), 2), []).append(p)
    return ds, por_z


def _todo_texto(ds):
    textos = []
    for el in ds.iterall():
        if el.VR in ("AE", "AS", "CS", "DA", "DT", "LO", "LT", "PN", "SH",
                     "ST", "TM", "UC", "UT") and el.value is not None:
            v = el.value
            textos.extend([str(x) for x in v] if isinstance(v, (list, tuple))
                          or type(v).__name__ == "MultiValue" else [str(v)])
    return textos


def teste_monaco_furo_por_fenda():
    c = _cenario_tps()
    rs_e, nome_e = c["saidas"]["eclipse"]
    rs_m, nome_m = c["saidas"]["monaco"]
    _ds_e, z_e = _contornos_por_z(rs_e, nome_e)
    ds_m, z_m = _contornos_por_z(rs_m, nome_m)
    checar("eclipse: anel + furo + ilha = tres contornos por corte",
           z_e and all(len(v) == 3 for v in z_e.values()),
           str(sorted(set(len(v) for v in z_e.values()))))
    checar("monaco: o furo entra no contorno por fenda (dois por corte: o "
           "anel com a fenda e a ilha)",
           z_m and all(len(v) == 2 for v in z_m.values()),
           str(sorted(set(len(v) for v in z_m.values()))))
    checar("monaco: os mesmos cortes que o eclipse", set(z_m) == set(z_e))
    ok_furo, ok_massa, ok_ilha, isca_pega = True, True, True, False
    for z, contornos in z_m.items():
        anel = max(contornos, key=lambda p: len(p))
        ilha = min(contornos, key=lambda p: len(p))
        centro = anel[:, :2].mean(axis=0)
        p_furo = centro + np.array([8.5, 0.0])
        p_massa = centro + np.array([17.0, 0.0])
        if _enrolamento(p_furo, anel[:, :2]) != 0:
            ok_furo = False
        if abs(_enrolamento(p_massa, anel[:, :2])) != 1:
            ok_massa = False
        if abs(_enrolamento(centro, ilha[:, :2])) != 1:
            ok_ilha = False
    checar("monaco: no furo o enrolamento e zero (o furo fica vazio na regra "
           "diferente de zero)", ok_furo)
    checar("monaco: no anel o enrolamento e um", ok_massa)
    checar("monaco: a ilha dentro do furo continua contorno proprio", ok_ilha)
    _ds_e2, z_e2 = _contornos_por_z(rs_e, nome_e)
    for contornos in z_e2.values():
        ordenados = sorted(contornos, key=lambda p: -abs(engine._area_assinada(p[:, :2])))
        externo, furo = ordenados[0], ordenados[1]
        mesmo_sentido = furo if ((engine._area_assinada(externo[:, :2]) > 0)
                                 == (engine._area_assinada(furo[:, :2]) > 0)) \
            else furo[::-1]
        errado = _sem_inverter(externo, mesmo_sentido)
        centro = externo[:, :2].mean(axis=0) + np.array([8.5, 0.0])
        if _enrolamento(centro, errado[:, :2]) != 0:
            isca_pega = True
        break
    checar("isca: a fenda sem inverter o sentido do furo o preencheria",
           isca_pega)
    from pydicom.uid import ImplicitVRLittleEndian
    checar("monaco: Implicit VR Little Endian",
           str(ds_m.file_meta.TransferSyntaxUID) == ImplicitVRLittleEndian)
    checar("monaco: identidade com acento declara ISO_IR 100 (e so ela)",
           str(getattr(ds_m, "SpecificCharacterSet", "")) == "ISO_IR 100")
    _fora = [t for t in _todo_texto(ds_m) if not t.isascii()]
    checar("monaco: todo texto fora da identidade e ASCII",
           all(t == str(ds_m.PatientName) for t in _fora), str(_fora[:3]))


def teste_texto_ascii_para_todos():
    c = _cenario_tps()
    for tps in ("eclipse", "monaco"):
        rs, nome = c["saidas"][tps]
        ds = pydicom.dcmread(rs)
        obs = " ".join(str(getattr(o, "ROIObservationDescription", ""))
                       for o in ds.RTROIObservationsSequence)
        checar("%s: a observacao sai em ASCII, transliterada" % tps,
               obs.isascii() and all(p in obs for p in (
                   "nao aprovado", " - ", "5 cm3", "+/-1", "graus")),
               obs[-60:])
        nossos = [t for t in _todo_texto(ds)
                  if t not in (str(ds.PatientName), str(ds.PatientID))]
        checar("%s: todo texto nosso e ASCII" % tps,
               all(t.isascii() for t in nossos),
               str([t for t in nossos if not t.isascii()][:3]))
    ds_e = pydicom.dcmread(c["saidas"]["eclipse"][0])
    checar("eclipse: a identidade copiada da imagem fica como veio",
           str(ds_e.PatientName) == u"JOÃO^FANTOMA", str(ds_e.PatientName))


def teste_a_volta_fecha_nos_dois_tps():
    import radai_rt
    c = _cenario_tps()
    voltas = {}
    for tps in ("eclipse", "monaco"):
        rs, nome = c["saidas"][tps]
        sessao = radai_rt.abrir(c["pasta"], rs)
        try:
            volta = sessao.mascara(nome)
            m = radai_rt.medir_ciclo(c["alvo"], volta, sessao.grade)
            voltas[tps] = volta
            checar("%s: a volta fecha (DSC 1,0)" % tps, m["dsc"] >= 0.9999,
                   str(m["dsc"]))
            checar("%s: sem deslocamento em z" % tps,
                   m["desloc_z_voxels"] == 0.0)
        finally:
            sessao.fechar()
    checar("monaco e eclipse voltam a MESMA mascara, voxel a voxel",
           len(voltas) == 2 and np.array_equal(voltas["eclipse"],
                                               voltas["monaco"]))


def teste_o_furo_nao_perde_uma_volta_de_material():
    import radai_geom
    import radai_rt
    quad = np.array([[0, 0], [10, 0], [10, 10], [0, 10]], dtype=float)
    fora = radai_geom.expandir_meio_pixel(quad, 1.0, 1.0)
    dentro = radai_geom.expandir_meio_pixel(quad, 1.0, 1.0, furo=True)
    checar("meio pixel: o contorno externo cresce",
           radai_geom.area_poligono(fora) > 100.0)
    checar("meio pixel: o contorno do furo encolhe (vai para dentro do furo)",
           radai_geom.area_poligono(dentro) < 100.0)
    c = _cenario_tps()
    original = engine._furos_da_roi
    engine._furos_da_roi = lambda *a, **k: set()
    try:
        rs, mapa = engine.build_rtstruct(c["stage"], {"liver": c["alvo"]},
                                         versao_worker="teste",
                                         descontar=False)
    finally:
        engine._furos_da_roi = original
    destino = os.path.join(temp(), "RS_isca.dcm")
    shutil.copy2(rs, destino)
    sessao = radai_rt.abrir(c["pasta"], destino)
    try:
        m = radai_rt.medir_ciclo(c["alvo"], sessao.mascara(mapa["liver"]),
                                 sessao.grade)
    finally:
        sessao.fechar()
    checar("isca: o furo expandido para fora come a volta interna do anel",
           m["dsc"] < 0.99, str(m["dsc"]))


def teste_temporario_no_disco_com_mais_espaco():
    base = temp()
    a = os.path.join(base, "A", "tmp")
    b = os.path.join(base, "B", "tmp")
    nuvem = os.path.join(base, "NUVEM", "tmp")
    livres = {a: 15.5, b: 748.0, nuvem: 2000.0}
    escolhida = radai_archive.escolher_temporaria(
        [a, nuvem, b], livre=lambda c: livres.get(c),
        sincroniza=lambda c: c == nuvem)
    checar("o temporario vai para o disco com mais espaco livre", escolhida == b,
           str(escolhida))
    checar("e a pasta que sincroniza fica de fora, mesmo com mais espaco",
           escolhida != nuvem)
    checar("a escolhida aceita escrita (foi criada e provada)",
           os.path.isdir(b) and not os.path.exists(os.path.join(b, ".radai_escrita")))
    checar("a de rede fica de fora",
           radai_archive.escolher_temporaria(
               [r"\\servidor\share\tmp", a],
               livre=lambda c: 9999.0 if c.startswith("\\\\") else 1.0,
               sincroniza=lambda c: False) == a)
    empate = radai_archive.escolher_temporaria(
        [a, b], livre=lambda c: 100.0, sincroniza=lambda c: False)
    checar("empate fica com o primeiro da ordem (a instalacao)", empate == a)
    recusa = radai_archive.escolher_temporaria(
        [b, a], livre=lambda c: livres.get(c), sincroniza=lambda c: False,
        provar=lambda c: c != b)
    checar("a que nao aceita escrita cede para a seguinte", recusa == a)
    isca = sorted([a, b], key=lambda c: [a, b].index(c))[0]
    checar("isca: a ordem fixa de antes ficaria no disco cheio", isca != escolhida)
    cands = radai_archive.candidatos_temporarios()
    checar("os candidatos incluem o RADIOTERAPIA_AI\\tmp de cada disco local",
           any(c.upper().endswith(r"\RADIOTERAPIA_AI\TMP") for c in cands)
           or os.name != "nt", str(cands))
    with _Ambiente(RADAI_TMP=os.path.join(base, "EXPLICITA")):
        checar("RADAI_TMP continua mandando",
               os.path.normcase(radai_archive.pasta_temporaria_local(
                   marcar_ambiente=False))
               == os.path.normcase(os.path.join(base, "EXPLICITA")))


def teste_temporaria_da_serie_sai_ao_fim():
    raiz = temp()
    with _Ambiente(TMPDIR=raiz, TEMP=raiz, TMP=raiz):
        tempfile.tempdir = None
        try:
            fora = {}
            criadas = {}
            with radai_archive.TemporariaDaSerie() as serie:
                criadas["d"] = tempfile.mkdtemp(prefix="radai_x_")
                fd, criadas["f"] = tempfile.mkstemp(prefix="radai_y_")
                os.close(fd)
                criadas["ctx"] = tempfile.TemporaryDirectory(prefix="radai_z_").name
                criadas["env"] = radai_archive.ambiente_da_serie({})
                criadas["em_uso"] = radai_archive.pasta_temporaria_em_uso(
                    serie.pasta, 6)[0]
                criadas["isca"] = radai_archive._DESVIO["mkdtemp"](
                    prefix="radai_isca_")

                def _vizinha():
                    fora["d"] = tempfile.mkdtemp(prefix="radai_viz_")
                t = threading.Thread(target=_vizinha)
                t.start()
                t.join()
                pasta = serie.pasta
            dentro = [criadas["d"], criadas["f"], criadas["ctx"]]
            checar("o que a serie cria no temporario cai na pasta dela",
                   all(os.path.normcase(p).startswith(os.path.normcase(pasta))
                       for p in dentro), str(dentro))
            checar("o processo filho recebe o TEMP da serie",
                   criadas["env"].get("TEMP") == pasta
                   and criadas["env"].get("TMPDIR") == pasta)
            checar("a faxina ve a pasta da serie em uso enquanto ela roda",
                   criadas["em_uso"])
            checar("ao fim da serie a pasta dela sai inteira",
                   not os.path.exists(pasta) and serie.apagada)
            checar("a serie vizinha (outra thread) nao e desviada nem apagada",
                   fora.get("d") and not os.path.normcase(fora["d"]).startswith(
                       os.path.normcase(pasta)) and os.path.isdir(fora["d"]))
            checar("isca: sem o desvio, o temporario fica na raiz e sobra",
                   criadas.get("isca") and os.path.isdir(criadas["isca"])
                   and not os.path.normcase(criadas["isca"]).startswith(
                       os.path.normcase(pasta)))
            pasta2 = None
            try:
                with radai_archive.TemporariaDaSerie() as s2:
                    pasta2 = s2.pasta
                    tempfile.mkdtemp(prefix="radai_falha_")
                    raise RuntimeError("a serie falhou")
            except RuntimeError:
                pass
            checar("a serie que falha tambem apaga o temporario dela",
                   pasta2 and not os.path.exists(pasta2))
            solta = tempfile.mkdtemp(prefix="radai_cdd_")
            checar("fora da serie o desvio nao age",
                   os.path.normcase(os.path.abspath(os.path.dirname(solta)))
                   == os.path.normcase(os.path.abspath(raiz)), solta)
        finally:
            tempfile.tempdir = None


def teste_aquecimento_confere_espaco_e_escrita():
    pasta = temp()
    arq = os.path.join(pasta, "x.bin")
    with open(arq, "wb") as f:
        f.write(b"\0" * 1000000)
    original = radai_archive._livre_gb
    try:
        radai_archive._livre_gb = lambda c: 0.5
        erro = None
        try:
            radai_archive.conferir_espaco_da_serie([arq], pasta)
        except radai_archive.TemporarioCurto as e:
            erro = str(e)
        checar("falta de espaco no temporario levanta TemporarioCurto, que diz "
               "que a serie foi adiada", erro and "adiada" in erro, str(erro))
        checar("e a mensagem nao leva caminho", erro and pasta not in erro)
        radai_archive._livre_gb = lambda c: 500.0
        precisa, livre = radai_archive.conferir_espaco_da_serie([arq], pasta)
        checar("com espaco a serie segue, e a conta e devolvida",
               livre == 500.0 and precisa > 0)
    finally:
        radai_archive._livre_gb = original
    checar("a conta da serie cresce com o tamanho dela",
           radai_archive.espaco_da_serie_gb(10 ** 9)
           > radai_archive.espaco_da_serie_gb(10 ** 6))
    radai_archive.conferir_escrita_no_destino(pasta)
    checar("a sonda de escrita nao deixa arquivo para tras",
           sorted(os.listdir(pasta)) == ["x.bin"])
    erro = None
    try:
        radai_archive.conferir_escrita_no_destino(os.path.join(pasta, "nao_ha"))
    except radai_archive.DestinoSemEscrita as e:
        erro = str(e)
    checar("pasta da serie que nao aceita escrita levanta DestinoSemEscrita",
           erro is not None, str(erro))
    checar("e a mensagem nao leva caminho", erro and pasta not in erro)
    import radai_watcher
    checar("no vigia, falta de espaco adia sem gastar tentativa (recurso)",
           radai_watcher.classificar_erro(radai_archive.TemporarioCurto("x"))
           == radai_watcher.RECURSO)
    checar("no vigia, destino sem escrita adia sem gastar tentativa (recurso)",
           radai_watcher.classificar_erro(radai_archive.DestinoSemEscrita("x"))
           == radai_watcher.RECURSO)
    checar("isca: um erro qualquer continua deterministico",
           radai_watcher.classificar_erro(RuntimeError("x"))
           == radai_watcher.DETERMINISTICO)


def _rodar_agora_uma_serie(s, copias):
    import radai_batch
    log = []
    marcadores = {"has_marker": lambda p, u, k: False,
                  "claim": lambda p, u, info: True,
                  "renovar": lambda p, u, extra=None: True,
                  "unclaim": lambda p, u: None}
    original = engine.copy_sorted
    engine.copy_sorted = lambda a, d: copias.append(len(a))
    try:
        res = radai_batch._uma_serie(s, False, ["total_v3"], "cpu",
                                     sys.executable, 60, 60, log.append,
                                     marcadores, "TESTE_CDD", 3600)
    finally:
        engine.copy_sorted = original
    return res, log


def teste_rodar_agora_adia_antes_de_copiar():
    raiz = temp()
    pasta = os.path.join(raiz, "PAC", "CT")
    uid, arquivos, _sops = serie_da_clinica(pasta, n=8, com_dir=False)
    s = {"uid": uid, "pasta": pasta, "pid": "FANTOMA_CDD", "curto": uid[-8:],
         "modalidade": "CT", "count": len(arquivos)}
    with _Ambiente(RADAI_REGISTRO_DIR=os.path.join(raiz, "registro"),
                   LOCALAPPDATA=os.path.join(raiz, "local"),
                   RADAI_NOTIFICACAO="0"):
        original = radai_archive._livre_gb
        radai_archive._livre_gb = lambda c: 0.01
        try:
            copias = []
            res, log = _rodar_agora_uma_serie(dict(s), copias)
            checar("Rodar agora: sem espaco no temporario a serie e adiada "
                   "antes de copiar", "adiada" in (res.get("erro") or "")
                   and not copias, "%r %r" % (res.get("erro"), copias))
            checar("Rodar agora: o log diz ADIADA",
                   any("ADIADA" in str(l) for l in log))
            confere = radai_archive.conferir_espaco_da_serie
            radai_archive.conferir_espaco_da_serie = lambda *a, **k: (0.0, 0.0)
            try:
                copias_isca = []
                _rodar_agora_uma_serie(dict(s), copias_isca)
            finally:
                radai_archive.conferir_espaco_da_serie = confere
            checar("isca: sem a conferencia, a serie copia mesmo sem espaco",
                   bool(copias_isca))
        finally:
            radai_archive._livre_gb = original
        sem = dict(s, pasta=os.path.join(raiz, "PAC", "SUMIU"))
        copias = []
        res, log = _rodar_agora_uma_serie(sem, copias)
        checar("Rodar agora: destino sem escrita para antes de copiar",
               "nao consigo gravar" in (res.get("erro") or "") and not copias,
               str(res.get("erro")))
    restos = [n for n in os.listdir(pasta) if n.startswith(".radai_escrita")]
    checar("a sonda de escrita nao fica na pasta da serie", not restos)


def teste_ferramenta_do_monaco():
    import gerar_serie_monaco as G
    destino = temp()
    antes = sys.argv
    sys.argv = ["gerar_serie_monaco.py", destino]
    try:
        G.main()
    finally:
        sys.argv = antes
    raiz = os.path.join(destino, "MONACO_TESTE")
    serie = os.path.join(raiz, "SERIE")
    nomes = os.listdir(serie)
    cortes = [n for n in nomes if n.startswith("CT_") and not n.endswith(".dir")]
    dirs = [n for n in nomes if n.endswith(".dir")]
    rs = [n for n in nomes if n.startswith("RS_RadAI_")]
    checar("Monaco: os cortes CT_<UID>, sem extensao .dcm",
           len(cortes) == G.CORTES and not any(n.lower().endswith(".dcm")
                                               for n in cortes))
    checar("Monaco: nenhum corte tem preambulo",
           not any(_tem_preambulo(os.path.join(serie, n)) for n in cortes))
    checar("Monaco: RTDIR.dir e CT_<serie>.dir ao lado", len(dirs) == 2
           and "RTDIR.dir" in dirs, str(dirs))
    ao_lado = os.listdir(os.path.join(raiz, "RTSTRUCT_AO_LADO"))
    checar("Monaco: o RTSTRUCT nas duas posicoes, o mesmo arquivo",
           len(rs) == 1 and ao_lado == rs and _hashes(serie)[rs[0]]
           == _hashes(os.path.join(raiz, "RTSTRUCT_AO_LADO"))[rs[0]])
    ds = pydicom.dcmread(os.path.join(serie, rs[0]))
    refs = set()
    for fr in ds.ReferencedFrameOfReferenceSequence:
        for st in fr.RTReferencedStudySequence:
            for se in st.RTReferencedSeriesSequence:
                for im in se.ContourImageSequence:
                    refs.add("CT_%s" % im.ReferencedSOPInstanceUID)
    checar("Monaco: o RTSTRUCT referencia os cortes da pasta",
           refs == set(cortes))
    checar("Monaco: o arquivo e o do Monaco (sem SpecificCharacterSet, "
           "UNAPPROVED)", "SpecificCharacterSet" not in ds
           and ds.ApprovalStatus == "UNAPPROVED")
    xor = pydicom.dcmread(os.path.join(raiz, "COMPARACAO_FURO_XOR", rs[0]))
    n_m = sum(len(r.ContourSequence) for r in ds.ROIContourSequence)
    n_x = sum(len(r.ContourSequence) for r in xor.ROIContourSequence)
    checar("Monaco: a comparacao do Eclipse tem o furo como contorno a mais",
           n_x > n_m, "%d x %d" % (n_x, n_m))
    checar("Monaco: o roteiro sai junto",
           os.path.isfile(os.path.join(raiz, "ROTEIRO_MONACO.txt")))
    checar("Monaco: a identificacao e a do fantoma",
           str(ds.PatientID) == G.ID)


def teste_a_conta_do_aquecimento_e_a_do_arranque():
    import radai_cleaner
    iguais = all(
        radai_archive.espaco_da_serie_gb(5 * 10 ** 8, n) + 1e-9
        >= radai_cleaner.disco_necessario_gb(1, n) for n in range(1, 26))
    checar("a conta do aquecimento nunca pede menos que a do arranque "
           "(uma fonte, as mesmas tasks)", iguais)
    checar("e as constantes moram num lugar so",
           getattr(radai_archive, "GB_POR_TASK", None)
           == radai_cleaner.GB_POR_TASK
           and getattr(radai_archive, "GB_FOLGA", None)
           == radai_cleaner.GB_FOLGA
           and getattr(radai_archive, "GB_POR_SERIE", None)
           == radai_cleaner.GB_POR_SERIE)
    pasta = temp()
    arq = os.path.join(pasta, "x.bin")
    with open(arq, "wb") as f:
        f.write(b"\0" * 1000)
    original = radai_archive._livre_gb
    radai_archive._livre_gb = lambda c: 15.5
    try:
        precisa, _livre = radai_archive.conferir_espaco_da_serie(
            [arq], pasta, n_tasks=22)
        checar("15,5 GB livres e 22 tasks pedidas: cabe, porque a conta e a "
               "de UMA task em voo (elas rodam em serie)",
               precisa < 15.5, str(precisa))
        radai_archive._livre_gb = lambda c: 6.0
        adiou = False
        try:
            radai_archive.conferir_espaco_da_serie([arq], pasta, n_tasks=1)
        except radai_archive.TemporarioCurto:
            adiou = True
        checar("6 GB livres: o aquecimento adia, como o arranque avisa",
               adiou)
    finally:
        radai_archive._livre_gb = original
    checar("a conta ainda cresce com a serie grande",
           radai_archive.espaco_da_serie_gb(4 * 10 ** 9, 1)
           > radai_archive.espaco_da_serie_gb(10 ** 6, 1))


def _chamadas_da_funcao(fonte, nome):
    import ast
    arvore = ast.parse(fonte)
    func = [n for n in ast.walk(arvore)
            if isinstance(n, ast.FunctionDef) and n.name == nome][0]

    def nome_da_chamada(no):
        f = no.func
        if isinstance(f, ast.Attribute):
            base = f.value.id if isinstance(f.value, ast.Name) else ""
            return "%s.%s" % (base, f.attr)
        return getattr(f, "id", "")

    todas = [nome_da_chamada(n) for n in ast.walk(func)
             if isinstance(n, ast.Call)]
    no_finally = []
    for t in ast.walk(func):
        if isinstance(t, ast.Try):
            for corpo in t.finalbody:
                no_finally += [nome_da_chamada(n) for n in ast.walk(corpo)
                               if isinstance(n, ast.Call)]
    return todas, no_finally


def _ligacoes_do_vigia(fonte):
    todas, fin = _chamadas_da_funcao(fonte, "process_series")
    return {
        "escrita": any(c.endswith(".conferir_escrita_no_destino")
                       for c in todas),
        "espaco": any(c.endswith(".conferir_espaco_da_serie") for c in todas),
        "temporaria": any(c.endswith(".TemporariaDaSerie") for c in todas),
        "abre": "_tmp_serie.abrir" in todas,
        "fecha_no_finally": "_tmp_serie.fechar" in fin,
    }


def teste_o_vigia_liga_o_aquecimento_e_a_temporaria():
    with open(_componentes.fonte("app/radai_watcher.py"), encoding="utf-8") as f:
        fonte = f.read()
    lig = _ligacoes_do_vigia(fonte)
    checar("vigia: process_series confere a escrita, o espaco e abre a "
           "temporaria da serie", lig["escrita"] and lig["espaco"]
           and lig["temporaria"] and lig["abre"], str(lig))
    checar("vigia: a temporaria da serie fecha no finally (entregue ou nao)",
           lig["fecha_no_finally"])
    checar("vigia: o aquecimento passa as tasks da serie para a conta",
           "conferir_espaco_da_serie(arquivos, n_tasks=" in fonte)
    isca = fonte.replace("_tmp_serie.fechar()", "pass")
    isca = isca.replace("_arq.conferir_espaco_da_serie(", "len(")
    lig_isca = _ligacoes_do_vigia(isca)
    checar("isca: sem a chamada, a checagem do vigia reprova",
           not lig_isca["fecha_no_finally"] and not lig_isca["espaco"])


def teste_rodar_agora_apaga_a_temporaria_da_serie():
    with open(_componentes.fonte("app/radai_batch.py"), encoding="utf-8") as f:
        fonte = f.read()
    _todas, fin = _chamadas_da_funcao(fonte, "_uma_serie")
    checar("Rodar agora: _uma_serie fecha a temporaria no finally",
           "_tmp_serie.fechar" in fin)
    checar("Rodar agora: o aquecimento passa as tasks da serie para a conta",
           "conferir_espaco_da_serie(arquivos, n_tasks=" in fonte)
    raiz = temp()
    pasta = os.path.join(raiz, "PAC", "CT")
    uid, arquivos, _sops = serie_da_clinica(pasta, n=8, com_dir=False)
    s = {"uid": uid, "pasta": pasta, "pid": "FANTOMA_CDD", "curto": uid[-8:],
         "modalidade": "CT", "count": len(arquivos)}
    abertas = []
    Original = radai_archive.TemporariaDaSerie

    class Espia(Original):
        def abrir(self):
            p = Original.abrir(self)
            abertas.append(p)
            return p

    def rodar(classe):
        del abertas[:]
        radai_archive.TemporariaDaSerie = classe
        livre = radai_archive._livre_gb
        radai_archive._livre_gb = lambda c: 0.01
        try:
            with _Ambiente(RADAI_REGISTRO_DIR=os.path.join(raiz, "registro"),
                           LOCALAPPDATA=os.path.join(raiz, "local"),
                           RADAI_NOTIFICACAO="0"):
                _rodar_agora_uma_serie(dict(s), [])
        finally:
            radai_archive.TemporariaDaSerie = Original
            radai_archive._livre_gb = livre
        return list(abertas)

    pastas = rodar(Espia)
    checar("Rodar agora: a serie adiada abriu a temporaria e ela saiu",
           len(pastas) == 1 and not os.path.exists(pastas[0]), str(pastas))

    class SemFechar(Espia):
        def fechar(self):
            return False

    pastas = rodar(SemFechar)
    checar("isca: sem o fechar a temporaria fica no disco",
           len(pastas) == 1 and os.path.exists(pastas[0]))
    for p in pastas:
        shutil.rmtree(p, ignore_errors=True)
        radai_archive.soltar_em_uso(p)
    radai_archive._DA_SERIE.pasta = None


def _disco_cheio(forma, z0, z1):
    nz, ny, nx = forma
    zz, yy, xx = np.ogrid[0:nz, 0:ny, 0:nx]
    r = np.sqrt(((yy - ny / 2.0) * PIXEL_MM) ** 2
                + ((xx - nx / 2.0) * PIXEL_MM) ** 2)
    return np.ascontiguousarray((r <= 18.0) & (zz >= z0) & (zz <= z1))


def teste_o_conserto_do_furo_so_muda_roi_com_furo():
    c = _cenario_tps()
    disco = _disco_cheio(c["forma"], 6, 13)

    def gravar(sem_furo):
        original = engine._furos_da_roi
        if sem_furo:
            engine._furos_da_roi = lambda *a, **k: set()
        try:
            with _Ambiente(RADAI_TPS_DESTINO="eclipse"):
                rs, mapa = engine.build_rtstruct(
                    c["stage"], {"liver": c["alvo"], "spleen": disco},
                    versao_worker="teste", descontar=False)
        finally:
            engine._furos_da_roi = original
        destino = os.path.join(temp(), "RS_furo_%d.dcm" % int(sem_furo))
        shutil.copy2(rs, destino)
        return destino, mapa

    novo, mapa = gravar(False)
    velho, _m = gravar(True)
    _d, z_novo = _contornos_por_z(novo, mapa["spleen"])
    _d, z_velho = _contornos_por_z(velho, mapa["spleen"])
    iguais = sorted(z_novo) == sorted(z_velho) and all(
        len(z_novo[z]) == len(z_velho[z]) and all(
            np.array_equal(a, b) for a, b in zip(z_novo[z], z_velho[z]))
        for z in z_novo)
    checar("eclipse: a ROI sem furo sai igual a de antes do conserto, ponto "
           "a ponto", iguais)
    _d, a_novo = _contornos_por_z(novo, mapa["liver"])
    _d, a_velho = _contornos_por_z(velho, mapa["liver"])
    mudou = any(not all(np.array_equal(a, b)
                        for a, b in zip(a_novo[z], a_velho[z]))
                for z in a_novo)
    checar("eclipse: a ROI com furo muda (a volta interna do anel volta)",
           mudou)


def teste_monaco_a_identidade_fica_como_a_da_imagem():
    c = _cenario_tps()
    ds_m = pydicom.dcmread(c["saidas"]["monaco"][0])
    ds_e = pydicom.dcmread(c["saidas"]["eclipse"][0])
    checar("monaco: o nome do paciente fica como o da imagem (JOÃO)",
           str(ds_m.PatientName) == u"JOÃO^FANTOMA", str(ds_m.PatientName))
    checar("monaco e eclipse levam a mesma identidade",
           str(ds_m.PatientName) == str(ds_e.PatientName))
    checar("monaco: com acento na identidade, o conjunto de caracteres e "
           "declarado", str(getattr(ds_m, "SpecificCharacterSet", ""))
           == "ISO_IR 100")
    nossos = [t for t in _todo_texto(ds_m)
              if t not in (str(ds_m.PatientName), str(ds_m.PatientID))]
    checar("monaco: o resto do texto continua ASCII",
           all(t.isascii() for t in nossos))


def teste_temporario_fora_de_disco_externo():
    if os.name != "nt":
        checar("(fora do Windows: sem unidades a escolher)", True)
        return
    todas = radai_archive._unidades_locais(e_externa=lambda r: False)
    checar("ha ao menos uma unidade fixa local nesta maquina", bool(todas),
           str(todas))
    checar("disco externo (USB) fica fora do temporario",
           radai_archive._unidades_locais(e_externa=lambda r: True) == [])
    sistema = (os.environ.get("SystemDrive") or "C:") + "\\"
    checar("o disco do sistema desta maquina nao e externo",
           radai_archive._unidade_externa(sistema) is False)


def teste_a_temporaria_e_uma_por_processo():
    import time as _t
    import radai_bridge_entrada as E
    import radai_thumbnail as TH
    base = temp()
    a = os.path.join(base, "discoA", "tmp")
    b = os.path.join(base, "discoB", "tmp")
    usuario = os.path.join(base, "usuario")
    for p in (a, b, usuario):
        os.makedirs(p)
    livres = {a: 100.0, b: 90.0}
    velhos = (radai_archive.candidatos_temporarios, radai_archive._livre_gb)
    radai_archive.candidatos_temporarios = lambda: [a, b]
    radai_archive._livre_gb = lambda c: livres.get(str(c))
    try:
        with _Ambiente(RADAI_TMP=None, RADAI_RAIZ_INSTALACAO=None,
                       TEMP=usuario, TMP=usuario, TMPDIR=usuario):
            tempfile.tempdir = None
            radai_archive.esquecer_temporaria()
            p1 = radai_archive.pasta_temporaria_local(marcar_ambiente=False)
            livres[a] = 80.0
            p2 = radai_archive.pasta_temporaria_local(marcar_ambiente=False)
            checar("com o espaco livre invertido no meio, a mesma pasta",
                   p1 == p2 == a, str((p1, p2)))
            checar("isca: a escolha refeita trocaria de disco",
                   radai_archive.escolher_temporaria([a, b]) == b)

            TH._pasta_cache(None)
            checar("a miniatura nao reaponta o TEMP do processo",
                   os.environ.get("TEMP") == usuario
                   and tempfile.gettempdir() == usuario,
                   os.environ.get("TEMP"))

            r = E.receber(None, "x/parte1.dcm", 0, b"1")
            sessao = r["sessao"]
            radai_archive.esquecer_temporaria()
            checar("isca: sem a base da sessao, a raiz agora seria a do "
                   "outro disco", E.raiz(criar=False).startswith(b))
            E.receber(sessao, "x/parte2.dcm", 0, b"2")
            pasta_a = os.path.join(a, E.PASTA, sessao)
            checar("as duas partes do envio ficam na mesma base",
                   os.path.isfile(os.path.join(pasta_a, "x", "parte1.dcm"))
                   and os.path.isfile(os.path.join(pasta_a, "x",
                                                   "parte2.dcm")))
            checar("o limpar apaga a sessao inteira",
                   E.limpar(sessao) is True and not os.path.exists(pasta_a))
            checar("  e nao cria a base do outro disco",
                   not os.path.exists(os.path.join(b, E.PASTA)))

            antigo = _t.time() - 30 * 3600
            restos = []
            for d in (a, b):
                p = os.path.join(d, "radai_resto_velho")
                os.makedirs(p)
                os.utime(p, (antigo, antigo))
                restos.append(p)
            radai_archive.limpar_temporaria(caminho=b)
            checar("isca: a faxina de uma pasta so deixa o resto do outro "
                   "disco", os.path.isdir(restos[0])
                   and not os.path.isdir(restos[1]))
            os.makedirs(restos[1])
            os.utime(restos[1], (antigo, antigo))
            radai_archive.limpar_temporaria()
            checar("a faxina passa por todas as temporarias possiveis",
                   not any(os.path.isdir(p) for p in restos),
                   str([p for p in restos if os.path.isdir(p)]))
    finally:
        radai_archive.candidatos_temporarios, radai_archive._livre_gb = velhos
        radai_archive.esquecer_temporaria()
        tempfile.tempdir = None


def _bytes_do_nome(caminho):
    ds = pydicom.dcmread(caminho, stop_before_pixels=True, force=True)
    el = ds.get_item("PatientName")
    return (str(ds.get("SpecificCharacterSet", "")),
            bytes(el.value) if isinstance(el.value, (bytes, bytearray))
            else str(el.value).encode("utf-8"))


def teste_a_identidade_sai_no_repertorio_da_tc():
    pasta = os.path.join(temp(), "PAC_UTF8", "CT")
    _uid, arquivos, _sops = serie_da_clinica(
        pasta, n=20, nome=u"JOÃO^FANTOMA", repertorio="ISO_IR 192")
    rep_tc, nome_tc = _bytes_do_nome(arquivos[0])
    stage = temp()
    engine.copy_sorted(arquivos, stage)
    img = engine.load_sitk(stage)
    forma = tuple(int(v) for v in reversed(img.GetSize()))
    alvo = _esfera(forma, 4)

    def _gravar(tps, isca=False):
        velho = engine.acabamento_para_o_tps
        if isca:
            def _antes(ds, tps=None, **k):
                k.pop("charset", None)
                return velho(ds, tps, **k)
            engine.acabamento_para_o_tps = _antes
        try:
            with _Ambiente(RADAI_TPS_DESTINO=tps):
                rs, _m = engine.build_rtstruct(stage, {"liver": alvo},
                                               versao_worker="teste")
        finally:
            engine.acabamento_para_o_tps = velho
        return _bytes_do_nome(rs)
    checar("a TC de fantoma declara ISO_IR 192, com o nome em UTF-8",
           rep_tc == "ISO_IR 192" and u"JOÃO".encode("utf-8") in nome_tc)
    for tps in ("eclipse", "monaco"):
        rep, nome = _gravar(tps)
        checar("%s: o RTSTRUCT declara o repertorio da TC (ISO_IR 192)" % tps,
               rep == "ISO_IR 192", rep)
        checar("%s:   e o PatientName sai com os mesmos bytes da TC" % tps,
               nome == nome_tc, repr(nome[:20]))
    rep_i, nome_i = _gravar("monaco", isca=True)
    checar("ISCA: com o ISO_IR 100 fixo de antes, os bytes do nome divergem "
           "dos da TC", rep_i == "ISO_IR 100" and nome_i != nome_tc,
           "%s %r" % (rep_i, nome_i[:20]))


TESTES = [teste_copia_local_vira_parte_10,
          teste_copia_local_preserva_quem_ja_tem_preambulo,
          teste_ordem_da_serie_sem_preambulo,
          teste_rtstruct_da_serie_sem_preambulo,
          teste_espacamento_le_sem_preambulo,
          teste_tps_de_destino,
          teste_tps_nao_escolhido_avisa_a_cada_gravacao,
          teste_monaco_furo_por_fenda,
          teste_texto_ascii_para_todos,
          teste_a_volta_fecha_nos_dois_tps,
          teste_o_furo_nao_perde_uma_volta_de_material,
          teste_temporario_no_disco_com_mais_espaco,
          teste_temporaria_da_serie_sai_ao_fim,
          teste_aquecimento_confere_espaco_e_escrita,
          teste_rodar_agora_adia_antes_de_copiar,
          teste_ferramenta_do_monaco,
          teste_a_conta_do_aquecimento_e_a_do_arranque,
          teste_o_vigia_liga_o_aquecimento_e_a_temporaria,
          teste_rodar_agora_apaga_a_temporaria_da_serie,
          teste_o_conserto_do_furo_so_muda_roi_com_furo,
          teste_monaco_a_identidade_fica_como_a_da_imagem,
          teste_temporario_fora_de_disco_externo,
          teste_a_temporaria_e_uma_por_processo,
          teste_a_identidade_sai_no_repertorio_da_tc]


def main():
    print("test_caminho_dos_dados | serie sem preambulo, TPS de destino, "
          "temporario da serie e aquecimento")
    for t in TESTES:
        try:
            t()
        except Exception as e:
            import traceback
            checar("%s (excecao inesperada)" % t.__name__, False,
                   "%s: %s" % (type(e).__name__, e))
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
