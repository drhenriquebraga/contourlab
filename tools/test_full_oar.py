# -*- coding: utf-8 -*-
import os
import sys
import shutil
import tempfile
from datetime import datetime

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
os.environ["RADAI_CALIB_DIR"] = tempfile.mkdtemp(prefix="radai_ac_fulloar_")
os.environ["RADAI_REGISTRO_DIR"] = tempfile.mkdtemp(prefix="radai_ac_fulloar_reg_")
os.environ["TOTALSEG_HOME_DIR"] = tempfile.mkdtemp(prefix="radai_tshome_fulloar_")
import _cleanup
_cleanup.adotar_prefixo("radai_ac_fulloar_")
_cleanup.adotar_prefixo("radai_tshome_fulloar_")
_cleanup.adotar_prefixo("radai_t_fulloar_")

import numpy as np
import pydicom
import engine as E
import radai_output as RO
import radai_sets as RS
from make_test_series import escreve_serie

PISO_DO_CORACAO_DE_FABRICA = E.VOLUME_MINIMO_CORACAO_CM3
E.VOLUME_MINIMO_CORACAO_CM3 = 1.0

_RESULTADOS = []
VERBOSO = "-v" in sys.argv


def checar(nome, condicao, detalhe=""):
    ok = bool(condicao)
    _RESULTADOS.append((nome, ok, detalhe))
    if VERBOSO or not ok:
        print("  %s  %s%s" % ("OK   " if ok else "FALHA", nome,
                              ("  [%s]" % detalhe) if detalhe else ""))
    return ok


def secao(t):
    print(u"\n-- %s --" % t)


Z, Y, X = 30, 128, 128
_TOTAL = (
    ("lung_upper_lobe_left", (14, 28, 40, 80, 70, 95)),
    ("lung_lower_lobe_left", (6, 14, 40, 80, 70, 95)),
    ("lung_upper_lobe_right", (16, 28, 40, 80, 30, 55)),
    ("lung_middle_lobe_right", (11, 16, 40, 80, 30, 55)),
    ("lung_lower_lobe_right", (6, 11, 40, 80, 30, 55)),
    ("heart", (8, 16, 45, 65, 57, 69)),
    ("aorta", (4, 26, 70, 76, 60, 66)),
    ("superior_vena_cava", (14, 22, 48, 54, 55, 57)),
    ("inferior_vena_cava", (2, 12, 60, 64, 52, 56)),
    ("trachea", (18, 28, 60, 64, 61, 65)),
    ("esophagus", (4, 28, 78, 82, 61, 64)),
    ("small_bowel", (0, 5, 40, 60, 40, 80)),
    ("kidney_left", (0, 6, 80, 95, 80, 95)),
    ("kidney_cyst_left", (2, 4, 84, 88, 84, 88)),
    ("clavicula_left", (27, 29, 40, 45, 70, 90)),
    ("atrial_appendage_left", (14, 16, 45, 48, 69, 71)),
    ("brachiocephalic_vein_left", (22, 26, 50, 54, 66, 72)),
)


def _cruas(com_plugins=True, extra=()):
    lab = np.zeros((Z, Y, X), np.int16)
    idx = {}
    for i, (nome, (z0, z1, y0, y1, x0, x1)) in enumerate(
            tuple(_TOTAL) + tuple(extra), start=1):
        lab[z0:z1, y0:y1, x0:x1] = i
        idx[i] = nome
    cruas = {"total_v3": E.MasksCruas(lab, idx)}
    tc = np.zeros((Z, Y, X), np.int16)
    tc[0:5, 30:40, 30:40] = 1
    tc[20:24, 50:60, 20:30] = 2
    tc[20:24, 50:60, 100:110] = 3
    tc[9:15, 43:67, 55:71] = 4
    cruas["trunk_cavities"] = E.MasksCruas(
        tc, {1: "abdominal_cavity", 2: "mediastinum", 3: "thoracic_cavity",
             4: "pericardium"})
    if com_plugins:
        oc = np.zeros((Z, Y, X), np.int16)
        oc[10:13, 60:64, 60:64] = 1
        cruas["oculomotor_muscles"] = E.MasksCruas(oc, {1: "eyeball_left"})
        am = np.zeros((Z, Y, X), np.int16)
        am[10:16, 30:36, 90:100] = 1
        am[10:16, 100:106, 60:70] = 2
        cruas["abdominal_muscles"] = E.MasksCruas(
            am, {1: "pectoralis_major_left", 2: "trapezius_left"})
        ef = np.zeros((Z, Y, X), np.int16)
        ef[6:9, 40:50, 40:50] = 1
        cruas["lung_nodules"] = E.MasksCruas(ef, {1: "lung_nodules"})
    return cruas


def _serie(base):
    serie = os.path.join(base, "serie")
    escreve_serie(serie, "PAC_FULLOAR", datetime.now(), Z)
    return serie


def _rodar(base, serie, cruas=None, suavizar_mm=1.5, **kw):
    import SimpleITK as sitk
    ref = E.load_sitk(serie)
    vol = sitk.GetArrayFromImage(ref)
    linhas = []
    dest = os.path.join(base, "saida_%d" % len(os.listdir(base)))
    os.makedirs(dest)
    sd = RO.Saida(E, serie, dest, "RS_RadAI_20260924_1a2b3c4d.dcm",
                  tasks=["total_v3"], versao="bateria", suavizar_mm=suavizar_mm,
                  log=lambda m: linhas.append(str(m)), modalidade="CT")
    sd.devolver_mascaras = True
    r = sd.full_e_oar(cruas if cruas is not None else _cruas(),
                      volume_hu=vol, **kw)
    return sd, r, linhas, dest


def _rois(ds):
    num = dict((int(x.ROINumber), str(x.ROIName))
               for x in ds.StructureSetROISequence)
    cont = dict((int(c.ReferencedROINumber), c)
                for c in getattr(ds, "ROIContourSequence", []))
    obs = dict((int(o.ReferencedROINumber), o)
               for o in getattr(ds, "RTROIObservationsSequence", []))
    return num, cont, obs


def teste_o_oar_e_uma_selecao_exata_do_full():
    secao(u"o OAR e uma selecao byte a byte do FULL")
    base = tempfile.mkdtemp(prefix="radai_t_fulloar_")
    try:
        serie = _serie(base)
        sd, r, linhas, dest = _rodar(base, serie)
        checar(u"os dois arquivos estao na pasta",
               os.path.isfile(r["oar"]) and os.path.isfile(r["full"]))
        checar(u"o OAR tem o nome do entregue (sem infixo)",
               RS.e_entregue(os.path.basename(r["oar"])),
               os.path.basename(r["oar"]))
        full = pydicom.dcmread(r["full"])
        oar = pydicom.dcmread(r["oar"])
        nf, cf, of = _rois(full)
        no, co, oo = _rois(oar)
        checar(u"toda ROI do OAR existe no FULL com o MESMO numero e nome",
               set(no.items()) <= set(nf.items()),
               str(sorted(set(no.items()) - set(nf.items()))[:4]))
        iguais = [no[n] for n in no
                  if n in cf and n in co
                  and cf[n].ContourSequence == co[n].ContourSequence
                  and list(cf[n].ROIDisplayColor) == list(co[n].ROIDisplayColor)]
        checar(u"os contornos e a cor sao os MESMOS, byte a byte",
               len(iguais) == len(no) and no,
               u"%d de %d" % (len(iguais), len(no)))
        obs_iguais = all(
            str(getattr(of.get(n), "ROIObservationDescription", "")) ==
            str(getattr(oo.get(n), "ROIObservationDescription", ""))
            for n in no)
        checar(u"e as observacoes (densidade, ressalva, descricao) tambem",
               obs_iguais)
        checar(u"o OAR e o entregue: rotulo `RadAI_STUDY`",
               oar.StructureSetLabel == "RadAI_STUDY", oar.StructureSetLabel)
        checar(u"  e `UNAPPROVED` (regra 1)",
               oar.ApprovalStatus == "UNAPPROVED")
        _forjado = os.path.join(base, "full_aprovado.dcm")
        _fa = pydicom.dcmread(r["full"])
        _fa.ApprovalStatus = "APPROVED"
        _fa.save_as(_forjado)
        try:
            E.selecionar_do_full(_forjado, dict((v, v) for v in nf.values()),
                                 set(nf.values()))
            _recusou = False
        except TypeError:
            _recusou = True
        checar(u"o OAR nao sai de arquivo nenhum: um FULL forjado `APPROVED` "
               u"no disco e recusado (o OAR nasce das mascaras, e nada "
               u"herda do FULL gravado)", _recusou)
        checar(u"  e serie 900, a do entregue", int(oar.SeriesNumber) == 900)
        checar(u"  e o nome e a descricao do entregue, com a versao DELE",
               str(oar.StructureSetName) == "RadAI STUDY"
               and "RadAI_STUDY" in str(oar.StructureSetDescription)
               and "material de revisao" not in str(oar.StructureSetDescription),
               str(oar.StructureSetDescription)[:160])
        checar(u"o FULL nao e o entregue: `RadAI_FULL`, serie 901",
               full.StructureSetLabel == "RadAI_FULL"
               and int(full.SeriesNumber) == 901)
        _novo = {"oar": "RadAI_STUDY", "full": "RadAI_FULL"}
        _velhos = []
        for _cod, _antigo in (("oar", "RadAI_OAR"), ("full", "STUDY_full")):
            _v = pydicom.dcmread(r[_cod])
            _v.StructureSetLabel = _antigo
            _velhos.append(_v.StructureSetLabel != _novo[_cod]
                           and RS.cod_do_rotulo(_v.StructureSetLabel) == _cod)
        checar(u"ISCA: o conjunto com o rotulo antigo (`RadAI_OAR`, "
               u"`STUDY_full`) reprova as duas checagens de cima, e o leitor "
               u"ainda o reconhece pelo cod de hoje (o acervo nao se regrava)",
               all(_velhos), str(_velhos))
        checar(u"UIDs proprios: o OAR nao e o mesmo objeto que o FULL",
               oar.SOPInstanceUID != full.SOPInstanceUID
               and oar.SeriesInstanceUID != full.SeriesInstanceUID
               and oar.file_meta.MediaStorageSOPInstanceUID ==
               oar.SOPInstanceUID)
        checar(u"  e o mesmo Frame of Reference e estudo (a mesma serie)",
               oar.FrameOfReferenceUID == full.FrameOfReferenceUID
               and oar.StudyInstanceUID == full.StudyInstanceUID)
        checar(u"nenhum contorno externo no OAR",
               not any(v.lower().startswith(("body", "external"))
                       for v in no.values()))
        n0 = sorted(no)[0]
        seq = cf[n0].ContourSequence[0]
        seq.ContourData = [str(float(seq.ContourData[0]) + 1.0)] + \
            list(seq.ContourData[1:])
        checar(u"  (isca) um ponto mexido no FULL e percebido",
               cf[n0].ContourSequence != co[n0].ContourSequence)

        oar_nomes = set(r["estruturas"])
        full_nomes = set(r["estruturas_full"])
        for fica in ("Heart_ai", "Lung_L_ai", "Lung_R_ai", "GreatVeins_ai",
                     "GreatArteries_ai", "Trachea_ai", "Esophagus_ai",
                     "Bowel_Small_ai", "Kidney_L_ai", "Kidney_Cyst_L_ai",
                     "Skin_ai"):
            checar(u"o OAR leva %s" % fica, fica in oar_nomes,
                   str(sorted(oar_nomes)))
        for sai in ("Lung_LUL_ai", "Lung_RML_ai", "A_Aorta_ai",
                    "V_Venacava_S_ai", "Heart_Model_ai", "Cavity_Abdomi_ai",
                    "clavicula_L_ai", "Mediastinum_ai", "Cavity_Thorac_ai",
                    "AtrialApp_L_ai"):
            checar(u"o OAR NAO leva %s (fica so no FULL)" % sai,
                   sai not in oar_nomes and sai in full_nomes,
                   u"no OAR: %s | no FULL: %s" % (sai in oar_nomes,
                                                  sai in full_nomes))
        checar(u"o log diz o que ficou fora da selecao",
               any(l.startswith("OAR: fora da selecao:") and "heart_model" in l
                   for l in linhas))
        checar(u"e a sobreposicao da SELECAO foi conferida (modo estrito)",
               any(l.startswith("OAR:") and "sobreposicao" in l.lower()
                   for l in linhas))
    finally:
        shutil.rmtree(base, ignore_errors=True)


def teste_o_full_faz_o_pos_processamento():
    secao(u"o FULL: coracao de RT e do modelo, compostos, vasos, rim, fora")
    base = tempfile.mkdtemp(prefix="radai_t_fulloar_")
    velho = E.build_rtstruct
    chamadas = []

    def _espia(*a, **k):
        chamadas.append(dict(k))
        return velho(*a, **k)
    try:
        serie = _serie(base)
        E.build_rtstruct = _espia
        try:
            sd, r, linhas, dest = _rodar(base, serie)
        finally:
            E.build_rtstruct = velho
        full_nomes = set(r["estruturas_full"])
        k_full = [k for k in chamadas if k.get("rotulo") == "RadAI_FULL"]
        checar(u"o FULL e montado UMA vez, com o desconto do cisto (Q6)",
               len(k_full) == 1 and k_full[0].get("descontar") is True,
               str([(k.get("rotulo"), k.get("descontar")) for k in chamadas]))
        checar(u"  com as construcoes, a selecao do OAR e a grade exigida",
               k_full and k_full[0].get("construcoes")
               and k_full[0].get("selecao") and k_full[0].get("exigir_grade"))
        checar(u"os DOIS coracoes: o de radioterapia e o do modelo",
               {"Heart_ai", "Heart_Model_ai"} <= full_nomes)
        checar(u"mediastino e cavidade toracica NO FULL (v8.3, spec 1.6)",
               {"Mediastinum_ai", "Cavity_Thorac_ai"} <= full_nomes,
               str(sorted(full_nomes)))
        checar(u"  e plugin tambem nao entra (a orbita, o derrame)",
               not any(n.startswith(("Eyeball", "pleural")) for n in full_nomes))
        checar(u"os insumos da mama entram (peitoral maior)",
               E.nome_clinico("pectoralis_major_left") in full_nomes,
               str(sorted(full_nomes)))
        checar(u"  e o trapezio da mesma task TAMBEM (a task inteira, v8.3)",
               E.nome_clinico("trapezius_left") in full_nomes,
               str(sorted(full_nomes)))
        mf = dict((k, np.asarray(v, bool))
                  for k, v in sd.meta_do_full["mascaras"].items())
        checar(u"o rim do FULL e o cisto nao se sobrepoem (rim descontado)",
               not (mf["kidney_left"] & mf["kidney_cyst_left"]).any())
        checar(u"o delgado e suavizado UMA vez, com 1,0 mm (alca)",
               _delgado_uma_vez(sd.meta_do_full),
               str(_entradas_do_delgado(sd.meta_do_full)))
        lung_l = mf["lung_left"]
        lobos = mf["lung_upper_lobe_left"] | mf["lung_lower_lobe_left"]
        checar(u"o pulmao do FULL e EXATAMENTE a uniao dos lobos suavizados "
               u"(A4: o composto nao e suavizado por conta propria)",
               np.array_equal(lung_l, lobos),
               u"%d voxels de diferenca" % int((lung_l ^ lobos).sum()))
        heart = mf["heart"]
        gv = mf["great_veins"]
        checar(u"as grandes veias sao a soma dos vasos prontos, inclusive "
               u"dentro do Heart_ai", np.array_equal(
                   gv, (mf["superior_vena_cava"] | mf["inferior_vena_cava"]
                        | mf["brachiocephalic_vein_left"])),
               u"%d voxels em comum com o coracao" % int((heart & gv).sum()))
        ga = mf["great_arteries"]
        checar(u"  e a aorta DESCENDENTE fica dentro dos grandes vasos (B3)",
               int((ga & mf["aorta"]).sum()) > 0.5 * int(mf["aorta"].sum()),
               u"%d de %d" % (int((ga & mf["aorta"]).sum()),
                              int(mf["aorta"].sum())))
        checar(u"o coracao de RT contem o do modelo",
               int((heart & mf["heart_model"]).sum())
               >= 0.9 * int(mf["heart_model"].sum()))
        checar(u"e ele nao entrou no grupo do orgao (A4): nao cedeu nada ao "
               u"coracao do modelo",
               not any("heart cedeu" in l for l in linhas))
    finally:
        shutil.rmtree(base, ignore_errors=True)


def teste_as_iscas_da_cadeia():
    secao(u"(iscas) a bateria reprova as versoes erradas da cadeia")
    base = tempfile.mkdtemp(prefix="radai_t_fulloar_")
    menos = dict(E.COMPOSTOS_MENOS)
    velho_rec = E.recompor_compostos
    try:
        serie = _serie(base)
        E.COMPOSTOS_MENOS["great_veins"] = ("heart",)
        try:
            sd, r, linhas, dest = _rodar(base, serie)
        finally:
            E.COMPOSTOS_MENOS.update(menos)
        mf = sd.meta_do_full["mascaras"]
        soma = (np.asarray(mf["superior_vena_cava"], bool)
                | np.asarray(mf["inferior_vena_cava"], bool)
                | np.asarray(mf["brachiocephalic_vein_left"], bool))
        perdidos = int((soma & ~np.asarray(mf["great_veins"], bool)).sum())
        checar(u"(isca) a regra antiga retiraria parte das grandes veias "
               u"que deve sobrepor o Heart_ai", perdidos > 0,
               u"%d voxels perdidos" % perdidos)

        def _so_uma_vez(masks, log=None, criar=False, **k):
            if criar:
                return velho_rec(masks, log=log, criar=criar, **k)
            return []
        E.recompor_compostos = _so_uma_vez
        try:
            sd, r, linhas, dest = _rodar(base, serie, suavizar_mm=6.0)
        finally:
            E.recompor_compostos = velho_rec
        mf = sd.meta_do_full["mascaras"]
        lung = np.asarray(mf["lung_left"], bool)
        lobos = (np.asarray(mf["lung_upper_lobe_left"], bool)
                 | np.asarray(mf["lung_lower_lobe_left"], bool))
        checar(u"(isca) sem a recomposicao, o pulmao NAO e a uniao dos lobos "
               u"suavizados", not np.array_equal(lung, lobos))
    finally:
        E.COMPOSTOS_MENOS.update(menos)
        E.recompor_compostos = velho_rec
        shutil.rmtree(base, ignore_errors=True)


def teste_margem_em_cada_vaso_e_composto_como_soma():
    secao(u"a margem e de cada vaso, e o composto e a soma dos prontos")
    import radai_geom
    g = radai_geom.Grade((1.0, 1.0, 1.0))
    forma = (20, 40, 40)
    m = {}

    def caixa(z0, z1, y0, y1, x0, x1):
        a = np.zeros(forma, bool)
        a[z0:z1, y0:y1, x0:x1] = True
        return a
    m["heart"] = caixa(6, 14, 14, 26, 14, 26)
    m["superior_vena_cava"] = caixa(10, 18, 10, 13, 18, 21)
    m["iliac_vena_left"] = caixa(0, 4, 30, 34, 5, 9)
    m["aorta"] = caixa(2, 18, 28, 32, 18, 22)
    m["trachea"] = caixa(12, 20, 30, 33, 30, 33)
    fora, meta = E.preparar_full(m, grade=g)
    checar(u"a chave do modelo trocou: `heart_model` e `heart` construido",
           "heart_model" in fora and "heart" in fora
           and "heart" in meta["construcoes"])
    checar(u"a VEIA ganhou 1 mm (Q7: «use 1mm»)",
           int(np.asarray(fora["iliac_vena_left"]).sum())
           > int(m["iliac_vena_left"].sum()))
    checar(u"a traqueia ganhou 2 mm",
           int(np.asarray(fora["trachea"]).sum()) > int(m["trachea"].sum()))
    gv = np.asarray(fora["great_veins"], bool)
    soma = (np.asarray(fora["superior_vena_cava"], bool)
            | np.asarray(fora["iliac_vena_left"], bool))
    checar(u"great_veins = soma inteira dos vasos prontos",
           np.array_equal(gv, soma))
    checar(u"a entrada nao foi mutada (a camada e do FULL)",
           int(m["iliac_vena_left"].sum()) == 4 * 4 * 4)


def teste_a_interface_das_construcoes():
    secao(u"a interface das construcoes (onda 2: C1 e C2 plugam aqui)")
    import radai_geom
    g = radai_geom.Grade((1.0, 1.0, 1.0))
    forma = (10, 20, 20)
    fig = np.zeros(forma, bool)
    fig[2:8, 2:10, 2:10] = True
    alca = np.zeros(forma, bool)
    alca[2:8, 11:18, 11:18] = True
    vistos = {}

    def bolsa(masks, grade, log=None):
        vistos["mutou"] = False
        k = radai_nomes_achar(masks, "small_bowel")
        return np.asarray(masks[k], bool).copy() if k else None

    def radai_nomes_achar(m, n):
        import radai_names
        return radai_names.achar(m, n)
    entrada = {"liver": fig.copy(), "small_intestine": alca.copy()}
    E.CONSTRUCOES.append({
        "cod": "isca_bolsa", "funcao": bolsa, "momento": "no_fim",
        "exige_hu": False, "exige": ("small_bowel",),
        "saidas": {"bag_bowel": {"suavizar_mm": 0.0, "recortar_por": (),
                                 "contem": ("small_intestine",),
                                 "descricao": u"isca"}}})
    E.CONSTRUCOES.append({
        "cod": "isca_sem_insumo", "funcao": bolsa, "momento": "no_fim",
        "exige_hu": False, "exige": ("abdominal_cavity",),
        "saidas": {"nada": {}}})
    linhas = []
    try:
        fora, meta = E.preparar_full(entrada, grade=g,
                                     log=lambda t: linhas.append(str(t)))
    finally:
        del E.CONSTRUCOES[-2:]
    checar(u"a funcao sem `volume_hu` roda (so recebe o que declara)",
           "bag_bowel" in meta["construcoes"], str(meta["nao_sairam"]))
    checar(u"  a mascara solta vai para a saida declarada, com a descricao",
           "bag_bowel" in fora and meta["observacoes"].get("bag_bowel")
           == u"isca")
    checar(u"  o insumo foi achado pelo tradutor (small_bowel -> "
           u"small_intestine)", np.array_equal(
               np.asarray(fora["bag_bowel"], bool), alca))
    checar(u"  e a entrada nao foi mutada",
           set(entrada) == {"liver", "small_intestine"})
    checar(u"sem o insumo, ela NAO sai e o log diz o que faltou (A7)",
           any("isca_sem_insumo" in l and "abdominal_cavity" in l
               for l in linhas), u" | ".join(linhas[-3:]))


def teste_o_femur_oar_e_o_inteiro():
    secao(u"o femur inteiro fica, e o recortado sai com nome proprio (Q7)")
    import radai_geom
    g = radai_geom.Grade((2.0, 1.0, 1.0))
    forma = (50, 30, 30)
    femur = np.zeros(forma, bool)
    femur[0:30, 10:16, 10:16] = True
    hip = np.zeros(forma, bool)
    hip[15:30, 5:9, 5:25] = True
    fora, meta = E.preparar_full({"femur_left": femur, "hip_left": hip},
                                 grade=g)
    checar(u"o femur inteiro continua inteiro",
           int(np.asarray(fora["femur_left"]).sum()) == int(femur.sum()))
    fo = np.asarray(fora.get("femur_oar_left"), bool)
    checar(u"o `femur_oar_left` para na tuberosidade (menor que o inteiro)",
           0 < int(fo.sum()) < int(femur.sum()))
    checar(u"  e sai como `Femur_OAR_L_ai` (<=16)",
           E.nome_clinico("femur_oar_left") == "Femur_OAR_L_ai")
    fora2, meta2 = E.preparar_full({"femur_left": femur}, grade=g)
    checar(u"sem o quadril, o recortado e o femur inteiro (e o log diz)",
           np.array_equal(np.asarray(fora2.get("femur_oar_left"), bool),
                          femur))

    def _afirma_recorte(obs):
        return u"recortado no nivel" in (obs or u"")

    def _diz_inteiro(obs):
        return u"INTEIRO" in (obs or u"") and u"NAO foi aplicado" in (obs or u"")

    obs1 = meta.get("observacoes", {}).get("femur_oar_left")
    checar(u"com o quadril, a ROI diz que foi recortada", _afirma_recorte(obs1),
           obs1)
    obs2 = meta2.get("observacoes", {}).get("femur_oar_left")
    checar(u"SEM o quadril, a ROI NAO diz «recortado» (o femur e o inteiro)",
           not _afirma_recorte(obs2), obs2)
    checar(u"  e diz que o recorte NAO foi aplicado, e por que (sem hip)",
           _diz_inteiro(obs2) and u"hip_left" in (obs2 or u""), obs2)
    alto = np.zeros(forma, bool)
    alto[35:40, 5:9, 5:25] = True
    fora3, meta3 = E.preparar_full({"femur_left": femur, "hip_left": alto},
                                   grade=g)
    obs3 = meta3.get("observacoes", {}).get("femur_oar_left")
    checar(u"com o plano acima do femur: inteiro, e a ROI diz por que",
           np.array_equal(np.asarray(fora3.get("femur_oar_left"), bool), femur)
           and _diz_inteiro(obs3) and u"acima" in (obs3 or u""), obs3)
    entrada = [c for c in E.CONSTRUCOES if c.get("cod") == "femur_oar"][0]
    velha = entrada["funcao"]

    def _como_era(masks, grade, volume_hu=None, log=None):
        s = velha(masks, grade, volume_hu=volume_hu, log=log)
        return dict((k, (v[0] if isinstance(v, tuple) else v))
                    for k, v in s.items())
    entrada["funcao"] = _como_era
    try:
        _f, meta_isca = E.preparar_full({"femur_left": femur}, grade=g)
    finally:
        entrada["funcao"] = velha
    obs_isca = meta_isca.get("observacoes", {}).get("femur_oar_left")
    checar(u"ISCA: a construcao sem a descricao da serie afirmaria o recorte "
           u"(a checagem reprovaria)", _afirma_recorte(obs_isca), obs_isca)


def _parede_do_fantoma(**kw):
    import SimpleITK as sitk
    import radai_geom
    base = tempfile.mkdtemp(prefix="radai_t_fulloar_")
    try:
        serie = _serie(base)
        ref = E.load_sitk(serie)
        vol = sitk.GetArrayFromImage(ref)
        g = radai_geom.Grade.de_sitk(ref)
    finally:
        shutil.rmtree(base, ignore_errors=True)
    cruas = _cruas(com_plugins=False)
    vocab = RO.vocabulario_do_full(cruas, E.TS_MAP)
    if kw.pop("_sem_mediastino_no_full", False):
        vocab = RO._VistaDeRotulos(dict(
            (k, vocab._pares[k]) for k in vocab if k != "mediastinum"))
    linhas = []
    fora, meta = E.preparar_full(vocab, grade=g, volume_hu=vol,
                                 modalidade="CT",
                                 log=lambda m: linhas.append(str(m)), **kw)
    med = np.asarray(cruas["trunk_cavities"]["mediastinum"], bool)
    paredes = [k for k in fora if str(k).startswith("ChestWall")]
    inter = sum(int((np.asarray(fora[k], bool) & med).sum()) for k in paredes)
    faltou = [l for l in linhas if u"recortes que NAO vieram" in l]
    return fora, paredes, inter, faltou, linhas, cruas


def _mediastino_dado_como_ausente(faltou):
    return any(u"mediastino" in l for l in faltou)


def teste_a_parede_recebe_o_mediastino_e_o_estudo_torax():
    secao(u"a parede: recortada pelo mediastino (fora do FULL) e pedida "
          u"pelo Estudo Torax (spec C)")
    cruas = _cruas()
    ins = RO.insumos_fora_do_full(cruas)
    nomes = list(ins)
    checar(u"os insumos fora do FULL NAO tem mais o mediastino nem a "
           u"cavidade toracica (v8.3: entraram no FULL)",
           "trunk_cavities:mediastinum" not in nomes
           and "trunk_cavities:thoracic_cavity" not in nomes, str(nomes))
    checar(u"  e NADA do que o FULL leva, nem o que tem plugin",
           not any(n.endswith(("abdominal_cavity", "trapezius_left",
                               "pectoralis_major_left", "eyeball_left"))
                   for n in nomes), str(nomes))
    checar(u"  preguicoso: a mascara so e lida quando pedida",
           isinstance(ins, RO._VistaDeRotulos))

    fora, paredes, inter, faltou, linhas, _c = _parede_do_fantoma(
        torax=True, cru=RO.insumos_fora_do_full(_cruas(com_plugins=False)))
    checar(u"com o Estudo Torax pedido, a parede sai (sem escapula no campo)",
           sorted(paredes) == ["ChestWall_L", "ChestWall_R"], str(paredes))
    checar(u"  e o log diz que foi pelo pedido",
           any(u"pedida pelo Estudo Torax" in l for l in linhas))
    checar(u"a parede NAO invade o mediastino (o recorte aconteceu)",
           inter == 0, u"%d voxel(s) em comum" % inter)
    checar(u"o log NAO da o mediastino como ausente (a task rodou)",
           not _mediastino_dado_como_ausente(faltou), u" | ".join(faltou))
    checar(u"e o mediastino esta NO FULL (v8.3), e nenhum insumo `task:` "
           u"entrou nele", "mediastinum" in fora
           and not any(":" in str(k) for k in fora),
           str([k for k in fora if "media" in str(k) or ":" in str(k)]))

    _f, paredes_i, inter_i, faltou_i, _l, _c = _parede_do_fantoma(
        torax=True, _sem_mediastino_no_full=True)
    checar(u"ISCA: sem o mediastino (nem no FULL nem no `cru`), a parede "
           u"invade o mediastino (a checagem reprovaria)",
           paredes_i and inter_i > 0, u"%d voxel(s)" % inter_i)
    checar(u"ISCA: sem ele, o log da o mediastino como ausente",
           _mediastino_dado_como_ausente(faltou_i), u" | ".join(faltou_i))

    _f, paredes_a, _i, _fa, linhas_a, _c = _parede_do_fantoma(
        cru=RO.insumos_fora_do_full(_cruas(com_plugins=False)))
    checar(u"sem o pedido, a anatomia decide: sem escapula, a parede NAO sai",
           not paredes_a and any(u"torax nao identificado" in l
                                 for l in linhas_a), str(paredes_a))


def teste_o_pedido_do_torax_chega_pela_porta_unica():
    secao(u"`full_e_oar(torax=...)` chega a `preparar_full`, com os insumos")
    base = tempfile.mkdtemp(prefix="radai_t_fulloar_")
    velho = E.preparar_full
    vistos = []

    class _Pare(Exception):
        pass

    def _espiao(*a, **k):
        vistos.append(dict(k))
        raise _Pare("espiao: parei antes do pos-processamento")
    try:
        serie = _serie(base)
        E.preparar_full = _espiao
        for torax in (True, None):
            sd = RO.Saida(E, serie, base, "RS_RadAI_20260924_1a2b3c4d.dcm",
                          log=lambda m: None, modalidade="CT")
            try:
                sd.full_e_oar(_cruas(com_plugins=False), torax=torax)
            except RuntimeError:
                pass
    finally:
        E.preparar_full = velho
        shutil.rmtree(base, ignore_errors=True)
    checar(u"as duas chamadas chegaram ao motor", len(vistos) == 2,
           str(len(vistos)))
    if len(vistos) == 2:
        checar(u"com o pedido, `torax=True` chega a `preparar_full`",
               vistos[0].get("torax") is True, str(vistos[0].get("torax")))
        checar(u"sem o pedido, `torax` nao chega (a anatomia decide)",
               vistos[1].get("torax") is None, str(vistos[1].get("torax")))
        checar(u"e o `cru` chega nos dois (a vista dos insumos fora do FULL)",
               all(isinstance(v.get("cru"), RO._VistaDeRotulos)
                   for v in vistos))

    import radai_batch as RB
    checar(u"o protocolo `torax_mama` no PERSONALIZADO e o pedido (lista ou "
           u"texto)",
           RB.torax_pedido({"modo": "perso", "protocolos": ["torax_mama"]})
           is True
           and RB.torax_pedido({"modo": "perso",
                                "protocolos": "cranio, TORAX_MAMA"}) is True)
    checar(u"sem protocolo, com outro, fora do PERSONALIZADO ou com a chave "
           u"velha: None (nunca False)",
           RB.torax_pedido({}) is None
           and RB.torax_pedido({"modo": "perso",
                                "protocolos": ["abdome"]}) is None
           and RB.torax_pedido({"modo": "auto",
                                "protocolos": ["torax_mama"]}) is None
           and RB.torax_pedido({"estudos": ["torax"]}) is None
           and RB.torax_pedido(None) is None)
    fonte = open(os.path.join(pasta_app(AQUI), "radai_batch.py"),
                 encoding="utf-8").read()
    i = fonte.find("entrega = sd.full_e_oar(")
    chamada = fonte[i:fonte.find(")", fonte.find("torax", i)) + 1] if i >= 0 else ""
    checar(u"`_uma_serie` passa o pedido da serie a `full_e_oar`",
           "torax=_torax" in chamada
           and "_torax = torax_pedido(s)" in fonte, chamada[:160])


def teste_o_cru_nao_recebe_nada():
    secao(u"o TS cru: nenhum pos-processamento, nem a leitura da imagem (A1)")
    base = tempfile.mkdtemp(prefix="radai_t_fulloar_")
    velho = E.load_sitk
    chamadas = []
    try:
        serie = _serie(base)
        cruas = _cruas()

        def _conta(*a, **k):
            chamadas.append(a)
            return velho(*a, **k)
        E.load_sitk = _conta
        linhas = []
        sd = RO.Saida(E, serie, base, "RS_RadAI_20260924_1a2b3c4d.dcm",
                      log=lambda m: linhas.append(str(m)), suavizar_mm=1.5)
        alvo = sd.totalsegmentator_cru(cruas)
        checar(u"o arquivo `TS_` saiu", alvo and os.path.isfile(alvo))
        checar(u"e ele NAO leu a imagem (nem a grade)", not chamadas,
               u"%d leitura(s)" % len(chamadas))
        ruido = [l for l in linhas if any(p in l for p in (
            "SOBREPOSICAO", "SUSPEITA", "suaviz", "sustentacao",
            "descontado", "fronteira"))]
        checar(u"e nenhuma conferencia nem suavizacao rodou", not ruido,
               u" | ".join(ruido[:3]))
        ds = pydicom.dcmread(alvo)
        nomes = [str(x.ROIName) for x in ds.StructureSetROISequence]
        checar(u"as travas ficam: UNAPPROVED, sufixo `_ts`",
               ds.ApprovalStatus == "UNAPPROVED"
               and all(n.endswith("_ts") for n in nomes))
        checar(u"e o cru tem o mediastino, cru (o FULL tambem o leva desde "
               u"a v8.3, pos-processado)",
               any(n.lower().startswith("mediastinum") for n in nomes),
               str(nomes))
    finally:
        E.load_sitk = velho
        shutil.rmtree(base, ignore_errors=True)


def teste_os_plugins_tem_arquivo_proprio():
    secao(u"cada plugin no seu arquivo, com o seu nome (D7)")
    base = tempfile.mkdtemp(prefix="radai_t_fulloar_")
    try:
        serie = _serie(base)
        sd, r, linhas, dest = _rodar(base, serie)
        feitos = sd.plugins(_cruas())
        checar(u"a orbita e o derrame sairam (e os musculos do tronco NAO: "
               u"eles vao ao FULL desde a v8.3)",
               set(feitos) == {"orb", "nod"}, str(feitos))
        arqs = sorted(os.listdir(dest))
        for cod in ("orb", "nod"):
            reg = RS.POR_COD[cod]
            alvo = [a for a in arqs if a.startswith("RS_RadAI_" + reg["infixo"])]
            checar(u"`%s` tem arquivo proprio (%s)" % (cod, reg["infixo"]),
                   len(alvo) == 1, str(arqs))
            if alvo:
                ds = pydicom.dcmread(os.path.join(dest, alvo[0]))
                nomes = [str(x.ROIName) for x in ds.StructureSetROISequence]
                checar(u"  com o sufixo `%s` e o rotulo `%s`"
                       % (reg["sufixo"], RS.rotulo_dicom(cod)),
                       all(n.endswith(reg["sufixo"]) for n in nomes)
                       and ds.StructureSetLabel == RS.rotulo_dicom(cod),
                       u"%s | %s" % (nomes, ds.StructureSetLabel))
                checar(u"  o rotulo e o de comparacao novo, `RadAI_%s`; o da "
                       u"geracao anterior (`STUDY_%s`) reprovaria, e continua "
                       u"legivel" % (cod.upper(), cod),
                       ds.StructureSetLabel == u"RadAI_" + cod.upper()
                       and (u"STUDY_" + cod) != ds.StructureSetLabel
                       and RS.cod_do_rotulo(u"STUDY_" + cod) == cod,
                       ds.StructureSetLabel)
                checar(u"  e reconhecido, e NUNCA como o entregue",
                       RS.do_arquivo(alvo[0])["cod"] == cod
                       and not RS.e_entregue(alvo[0]))
        checar(u"nenhum arquivo `RS_RadAI_ABM_*` (o plugin do tronco saiu)",
               not [a for a in arqs if a.startswith("RS_RadAI_ABM_")],
               str(arqs))
        checar(u"  e o registro nao o conhece mais (`abm` fora de "
               u"`radai_sets.PLUGINS`)", "abm" not in RS.POR_COD
               and "abdominal_muscles" not in RS.PLUGIN_DA_TASK)
        checar(u"a task de ACHADO e anunciada com a palavra",
               any(l.startswith("ACHADO:") and "lung_nodules" in l
                   for l in linhas))
        checar(u"o relatorio fala dos plugins que sairam",
               "orb" in RO.relatorio(sd.gravados))
    finally:
        shutil.rmtree(base, ignore_errors=True)


def teste_a_falha_do_entregue_levanta():
    secao(u"a falha do FULL/OAR LEVANTA, e o log traz o traceback")
    base = tempfile.mkdtemp(prefix="radai_t_fulloar_")
    velho = E.build_rtstruct
    try:
        serie = _serie(base)
        linhas = []
        sd = RO.Saida(E, serie, base, "RS_RadAI_20260924_1a2b3c4d.dcm",
                      log=lambda m: linhas.append(str(m)))
        try:
            sd.full_e_oar({})
            levantou = False
        except RuntimeError as e:
            levantou = "FULL/OAR" in str(e)
        checar(u"sem estrutura nenhuma, LEVANTA", levantou)

        def _quebra(*a, **k):
            raise ValueError("gravador quebrado de proposito")
        E.build_rtstruct = _quebra
        linhas[:] = []
        try:
            sd.full_e_oar(_cruas(com_plugins=False))
            levantou = False
        except RuntimeError as e:
            levantou = "gravador quebrado" in str(e)
        checar(u"com o gravador quebrado, LEVANTA com o motivo", levantou)
        checar(u"  e o traceback inteiro vai ao log",
               any("Traceback" in l for l in linhas))
        checar(u"  e nada foi gravado na pasta",
               not [a for a in os.listdir(base) if a.startswith("RS_RadAI")])

        E.build_rtstruct = velho
        velho_pre = E.preparar_full

        def _sem_memoria(*a, **k):
            raise MemoryError()
        E.preparar_full = _sem_memoria
        linhas[:] = []
        erro = None
        try:
            sd.full_e_oar(_cruas(com_plugins=False))
        except RuntimeError as e:
            erro = e
        finally:
            E.preparar_full = velho_pre

        def _diz_o_tipo(texto):
            return "MemoryError" in (texto or "")
        checar(u"MemoryError: LEVANTA RuntimeError com o TIPO na mensagem",
               erro is not None and _diz_o_tipo(str(erro)), repr(erro))
        checar(u"  e a causa fica encadeada (`raise ... from e`)",
               erro is not None and isinstance(erro.__cause__, MemoryError),
               repr(getattr(erro, "__cause__", None)))
        checar(u"  e a linha do log tambem diz o tipo",
               any("NAO SAIU" in l and _diz_o_tipo(l) for l in linhas),
               u" | ".join(l for l in linhas if "NAO SAIU" in l))
        antes = u"conjunto entregue (FULL/OAR) nao saiu: %s" % str(MemoryError())
        checar(u"ISCA: a mensagem de antes nao diz o tipo (reprovaria)",
               not _diz_o_tipo(antes), antes)
        checar(u"`motivo_do_erro` nunca devolve vazio",
               RO.motivo_do_erro(MemoryError()) == "MemoryError"
               and RO.motivo_do_erro(ValueError("x")) == "ValueError: x")
    finally:
        E.build_rtstruct = velho
        shutil.rmtree(base, ignore_errors=True)


def teste_a_grade_que_falta_e_dita():
    secao(u"a grade que nao carrega e dita, e o FULL nao sai sem ela (E4)")
    base = tempfile.mkdtemp(prefix="radai_t_fulloar_")
    velho = E.load_sitk
    try:
        serie = _serie(base)

        def _quebra(*a, **k):
            raise IOError("serie ilegivel de proposito")
        E.load_sitk = _quebra
        linhas = []
        m = {"liver": np.zeros((Z, Y, X), bool)}
        m["liver"][10:20, 40:80, 40:80] = True
        E.build_rtstruct(serie, m, versao_worker="t",
                         log=lambda t: linhas.append(str(t)),
                         suavizar_mm=1.5, rotulo="RadAI_NV")
        checar(u"um conjunto de estudo sai, e o log DIZ que a grade faltou",
               any("NAO carreguei a grade" in l for l in linhas),
               u" | ".join(linhas[:3]))
        try:
            E.build_rtstruct(serie, m, versao_worker="t", exigir_grade=True)
            levantou = False
        except RuntimeError as e:
            levantou = "grade" in str(e)
        checar(u"o conjunto de onde sai o entregue LEVANTA sem a grade",
               levantou)
    finally:
        E.load_sitk = velho
        shutil.rmtree(base, ignore_errors=True)


def teste_a_mascara_espelhada_nao_entra():
    secao(u"o `add_roi` que falha nao tenta de novo com a mascara espelhada")
    base = tempfile.mkdtemp(prefix="radai_t_fulloar_")
    velho = E._adicionar_roi
    chamadas = []
    try:
        serie = _serie(base)

        def _recusa(rt, mb, nome, cor):
            chamadas.append(nome)
            raise ValueError("recusada de proposito")
        E._adicionar_roi = _recusa
        linhas = []
        m = {"liver": np.zeros((Z, Y, X), bool)}
        m["liver"][10:20, 40:80, 40:80] = True
        E.build_rtstruct(serie, m, versao_worker="t",
                         log=lambda t: linhas.append(str(t)))
        checar(u"UMA tentativa por ROI, e nao duas", len(chamadas) == 1,
               str(chamadas))
        checar(u"e a recusa e dita no log, com o motivo",
               any("o add_roi recusou" in l and "recusada de proposito" in l
                   for l in linhas))
    finally:
        E._adicionar_roi = velho
        shutil.rmtree(base, ignore_errors=True)



def _entradas_do_delgado(meta):
    return [x for x in (meta or {}).get("suavizacao") or ()
            if str(x[0]).split(":")[-1] in ("small_intestine", "small_bowel")]


def _delgado_uma_vez(meta):
    e = _entradas_do_delgado(meta)
    return len(e) == 1 and abs(float(e[0][1]) - 1.0) < 1e-9


def teste_o_delgado_e_suavizado_uma_vez():
    secao(u"o delgado e suavizado UMA vez, com 1,0 mm (lido do meta)")
    base = tempfile.mkdtemp(prefix="radai_t_fulloar_")
    velho = E._suavizar_individuais
    try:
        serie = _serie(base)
        sd, r, linhas, dest = _rodar(base, serie)
        checar(u"o `meta` do FULL traz o detalhe da suavizacao",
               bool(sd.meta_do_full.get("suavizacao")))
        checar(u"UMA entrada do delgado, com 1,0 mm (cursor 1,5: a tabela de "
               u"alca, 1,0, vezes 1,5/1,5)", _delgado_uma_vez(sd.meta_do_full),
               str(_entradas_do_delgado(sd.meta_do_full)))
        checar(u"  e o delgado nao tem entrada com outro nome (small_bowel)",
               not [x for x in sd.meta_do_full["suavizacao"]
                    if str(x[0]) == "small_bowel"])

        def _duas_vezes(masks, nomes, grade, mm, detalhe, finas):
            velho(masks, nomes, grade, mm, detalhe, finas)
            return velho(masks, nomes, grade, mm, detalhe, finas)
        E._suavizar_individuais = _duas_vezes
        try:
            sd2, _r, _l, _d = _rodar(base, serie)
        finally:
            E._suavizar_individuais = velho
        checar(u"ISCA: suavizado duas vezes, a checagem reprova",
               not _delgado_uma_vez(sd2.meta_do_full),
               str(_entradas_do_delgado(sd2.meta_do_full)))
        sd3, _r, _l, _d = _rodar(base, serie, suavizar_mm=3.0)
        checar(u"ISCA: com outro cursor o numero muda, e a checagem reprova",
               not _delgado_uma_vez(sd3.meta_do_full),
               str(_entradas_do_delgado(sd3.meta_do_full)))
    finally:
        E._suavizar_individuais = velho
        shutil.rmtree(base, ignore_errors=True)


def _cruas_com_aorta_que_atravessa():
    lab = np.zeros((Z, Y, X), np.int16)
    asc = np.zeros((Z, Y, X), bool)
    asc[10:21, 46:52, 70:75] = True
    arco = np.zeros((Z, Y, X), bool)
    arco[21:24, 46:78, 70:75] = True
    desc = np.zeros((Z, Y, X), bool)
    desc[2:22, 72:78, 70:75] = True
    lab[8:16, 45:65, 57:69] = 1
    lab[asc | arco | desc] = 2
    lab[16:26, 30:40, 40:60] = 3
    idx = {1: "heart", 2: "aorta", 3: "lung_upper_lobe_left"}
    return {"total_v3": E.MasksCruas(lab, idx)}, asc, desc


def _a_aorta_no_lugar(mf, asc, desc, janela):
    h = np.asarray(mf.get("heart"), bool)
    ga = np.asarray(mf.get("great_arteries", np.zeros_like(h)), bool)
    a_j = asc & janela
    f = lambda m, alvo: float((m & alvo).sum()) / max(1, int(m.sum()))
    return f(a_j, h), f(a_j, ga), f(desc, ga)


def teste_a_aorta_que_atravessa_o_topo_do_coracao():
    secao(u"a aorta que atravessa o topo do coracao (B3)")
    base = tempfile.mkdtemp(prefix="radai_t_fulloar_")
    janela = np.zeros((Z, Y, X), bool)
    janela[8:16] = True
    velho = E._aorta_ascendente
    try:
        serie = _serie(base)
        cruas, asc, desc = _cruas_com_aorta_que_atravessa()
        sd, r, linhas, dest = _rodar(base, serie, cruas=cruas,
                                     suavizar_mm=0.0)
        mf = sd.meta_do_full["mascaras"]
        no_cor, no_ga, desc_ga = _a_aorta_no_lugar(mf, asc, desc, janela)
        checar(u"a ascendente, na janela do coracao, esta DENTRO do Heart_ai",
               no_cor == 1.0, u"%.0f%%" % (100 * no_cor))
        checar(u"  e NAO esta nos grandes vasos (o composto cede ao coracao)",
               no_ga == 0.0, u"%.0f%%" % (100 * no_ga))
        checar(u"a descendente INTEIRA esta nos grandes vasos, inclusive o "
               u"trecho na janela do coracao (a regra de B3)",
               desc_ga == 1.0, u"%.0f%%" % (100 * desc_ga))
        checar(u"  e os grandes vasos nao tocam o Heart_ai",
               not (np.asarray(mf["great_arteries"], bool)
                    & np.asarray(mf["heart"], bool)).any())
        checar(u"e a aorta inteira continua no FULL, com o nome dela",
               "A_Aorta_ai" in r["estruturas_full"]
               and "A_Aorta_ai" not in r["estruturas"],
               str(sorted(r["estruturas_full"]))[:200])
        sdS, _r, _l, _d = _rodar(base, serie, cruas=cruas)
        mS = sdS.meta_do_full["mascaras"]
        c_s, g_s, d_s = _a_aorta_no_lugar(mS, asc, desc, janela)
        checar(u"suavizado: a ascendente segue no Heart_ai (>= 70%% com os "
               u"5,5 mm de suavizacao do coracao) e o resto dela no composto, "
               u"sem nada nos dois",
               c_s >= 0.70 and c_s + g_s <= 1.0 + 1e-9
               and not (np.asarray(mS["great_arteries"], bool)
                        & np.asarray(mS["heart"], bool)).any(),
               u"%.0f%% no coracao, %.0f%% nos vasos" % (100 * c_s, 100 * g_s))
        checar(u"  e a descendente segue nos grandes vasos (>= 90%%)",
               d_s >= 0.90, u"%.0f%%" % (100 * d_s))

        menos = dict(E.COMPOSTOS_MENOS)
        E.COMPOSTOS_MENOS.clear()
        try:
            sd1, _r, _l, _d = _rodar(base, serie, cruas=cruas,
                                     suavizar_mm=0.0)
        finally:
            E.COMPOSTOS_MENOS.update(menos)
        _c, no_ga1, _g = _a_aorta_no_lugar(sd1.meta_do_full["mascaras"], asc,
                                           desc, janela)
        checar(u"ISCA: sem `COMPOSTOS_MENOS`, a ascendente aparece nos "
               u"grandes vasos (reprovaria)", no_ga1 > 0.0,
               u"%.0f%%" % (100 * no_ga1))

        def _tudo_ascendente(aorta, coracao, grade):
            return aorta.copy(), np.zeros_like(aorta)
        E._aorta_ascendente = _tudo_ascendente
        try:
            sd2, _r, _l, _d = _rodar(base, serie, cruas=cruas,
                                     suavizar_mm=0.0)
        finally:
            E._aorta_ascendente = velho
        _c, _g, desc_ga2 = _a_aorta_no_lugar(sd2.meta_do_full["mascaras"],
                                             asc, desc, janela)
        checar(u"ISCA: com o coracao levando a aorta toda, a descendente sai "
               u"dos grandes vasos (reprovaria)", desc_ga2 < 1.0,
               u"%.0f%%" % (100 * desc_ga2))
    finally:
        E._aorta_ascendente = velho
        shutil.rmtree(base, ignore_errors=True)


def teste_as_construcoes_da_onda_2_estao_ligadas():
    secao(u"as construcoes da onda 2 estao no registro, na ordem da spec")
    import ast
    import radai_constructs as C
    cods = [c["cod"] for c in E.CONSTRUCOES]
    for cod in ("femur_oar", "pericardio", "coracao", "bag_bowel",
                "pele_e_parede", "bag_bowel_oar"):
        checar(u"`%s` esta em engine.CONSTRUCOES" % cod, cod in cods,
               str(cods))
    por_cod = dict((c["cod"], c) for c in E.CONSTRUCOES)
    saidas = set(E.CONSTRUCOES_POR_SAIDA())
    checar(u"a mama de restricao saiu inteira (v8.5): nenhuma construcao a "
           u"monta, e nem o nome nem o modulo existem",
           not [c for c in cods if "breast" in c or "mama" in c]
           and not {"breast_oar_left", "breast_oar_right"} & saidas
           and "breast_oar_left" not in E.TG263
           and not os.path.exists(os.path.join(pasta_app(AQUI),
                                               "radai_breast.py")),
           str(cods))
    checar(u"o Heart_ai sai com a chave de `radai_constructs` (`heart`)",
           C.CHAVE_CORACAO_AI in (por_cod.get("coracao") or {}).get("saidas",
                                                                    {}))
    checar(u"o pericardio sai com o nome da task (`pericardium`)",
           C.CHAVE_PERICARDIO in (por_cod.get("pericardio") or {}).get(
               "saidas", {}))
    checar(u"a Bag_Bowel sai como `bag_bowel`",
           C.CHAVE_BAG_BOWEL in (por_cod.get("bag_bowel") or {}).get(
               "saidas", {}))
    bag_rec = tuple((por_cod.get("bag_bowel") or {}).get("saidas", {}).get(
        "bag_bowel", {}).get("recortar_por") or ())
    checar(u"  e recorta de novo pelos orgaos e vasos da receita (lidos de "
           u"radai_constructs, com a vesicula)",
           set(C.ORGAOS_FORA_DA_BAG) <= set(bag_rec)
           and "gallbladder" in bag_rec
           and set(C.vasos_do_motor()) <= set(bag_rec), str(bag_rec)[:160])
    checar(u"  e pelos orgaos do TORAX que a receita tira (esofago, coracao, "
           u"pericardio, pulmao)",
           set(C.ORGAOS_DO_TORAX_FORA_DA_BAG) <= set(bag_rec),
           str(bag_rec)[:160])

    passos = []
    for etapa, valor in E.ORDEM_DO_FULL:
        if etapa == "construcoes":
            passos.extend(c["cod"] for c in E.CONSTRUCOES
                          if c["momento"] == valor)
        else:
            passos.append(etapa)

    def antes(a, b):
        return a in passos and b in passos and passos.index(a) < passos.index(b)
    for a, b, porque in (
            ("refino", "femur_oar", u"o recorte vale sobre a ponta refinada"),
            ("margens", "pericardio", u"decisao (a): margem antes do coracao"),
            ("margens", "coracao", u"decisao (a): margem antes do coracao"),
            ("pericardio", "coracao", u"o Heart_ai recebe o pericardio pronto"),
            ("coracao", "compostos", u"o composto e a soma menos o Heart_ai"),
            ("compostos", "bag_bowel", u"a Bag tira os vasos prontos"),
            ("coracao", "pele_e_parede", u"a parede recorta o Heart_ai"),
            ("pericardio", "pele_e_parede", u"a parede recorta o pericardio")):
        checar(u"%s antes de %s (%s)" % (a, b, porque), antes(a, b),
               u" -> ".join(passos))
    checar(u"a Bag_Bowel_OAR e a ULTIMA construcao (recebe a pele pronta)",
           [p for p in passos if p in cods and p not in {
               c["cod"] for c in E.CONSTRUCOES if c.get("terminal")}][-1]
           == "bag_bowel_oar",
           u" -> ".join(passos))
    from unittest.mock import Mock
    import numpy as np
    import radai_geom
    terminal = next(c for c in E.CONSTRUCOES if c.get("cod") == "cauda_equina")
    fn = terminal["funcao"]
    espia = Mock(return_value={})
    try:
        terminal["funcao"] = espia
        E._rodar_construcoes(
            {"spinal_cord": np.ones((4, 4, 4), bool),
             "vertebrae_L2": np.ones((4, 4, 4), bool)},
            "no_fim", radai_geom.Grade((1.0, 1.0, 1.0)), None, False,
            {"construcoes": {}, "observacoes": {}}, None,
            so_cods={"cauda_equina"})
    finally:
        terminal["funcao"] = fn
    checar(u"Cauda e declarada, mas nunca executada na fase inicial das construcoes",
           espia.call_count == 0, str(espia.call_count))
    checar(u"todo momento do registro esta na ordem",
           all(c["momento"] in E.MOMENTOS_DAS_CONSTRUCOES
               for c in E.CONSTRUCOES))

    fonte = open(os.path.join(pasta_app(AQUI), "engine.py"),
                 encoding="utf-8").read()
    checar(u"`preparar_full` percorre `ORDEM_DO_FULL` e nao escreve momento "
           u"literal", _ordem_num_lugar_so(fonte))
    for isca, rot in (
            (u"def preparar_full(m):\n"
             u"    for e, v in ORDEM_DO_FULL:\n        pass\n"
             u"    _rodar_construcoes(m, 'no_fim', 1, 2, 3, 4, 5)\n",
             u"um momento literal ao lado do laco"),
            (u"def preparar_full(m):\n"
             u"    _rodar_construcoes(m, v, 1, 2, 3, 4, 5)\n",
             u"sem o laco sobre ORDEM_DO_FULL")):
        checar(u"  ISCA (%s) e acusada" % rot, not _ordem_num_lugar_so(isca))

    import radai_geom
    E.CONSTRUCOES.append({"cod": "isca_momento", "funcao": lambda m, g: {},
                          "momento": "momento_que_nao_existe",
                          "exige_hu": False, "exige": (), "saidas": {}})
    try:
        _f, meta = E.preparar_full({"liver": np.ones((4, 6, 6), bool)},
                                   grade=radai_geom.Grade((1.0, 1.0, 1.0)))
    finally:
        E.CONSTRUCOES.pop()
    checar(u"uma construcao com momento fora de ORDEM_DO_FULL e dita em "
           u"`nao_sairam`", any(c == "isca_momento" and u"ORDEM_DO_FULL" in m
                                for c, m in meta["nao_sairam"]),
           str(meta["nao_sairam"]))


def _ordem_num_lugar_so(fonte):
    import ast
    try:
        arv = ast.parse(fonte)
    except SyntaxError:
        return False
    f = [n for n in ast.walk(arv)
         if isinstance(n, ast.FunctionDef) and n.name == "preparar_full"]
    if not f:
        return False
    laco = any(isinstance(n, ast.For) and isinstance(n.iter, ast.Name)
               and n.iter.id == "ORDEM_DO_FULL" for n in ast.walk(f[0]))
    literal = False
    for n in ast.walk(f[0]):
        if (isinstance(n, ast.Call)
                and getattr(n.func, "id", "") == "_rodar_construcoes"
                and len(n.args) >= 2 and isinstance(n.args[1], ast.Constant)):
            literal = True
    return laco and not literal


def _fantoma_da_casca():
    import radai_geom
    g = radai_geom.Grade((2.0, 0.9, 0.9))
    forma = (30, 60, 60)
    m = {}

    def caixa(z0, z1, y0, y1, x0, x1):
        a = np.zeros(forma, bool)
        a[z0:z1, y0:y1, x0:x1] = True
        return a
    m["heart"] = caixa(6, 16, 20, 40, 20, 40)
    vcs = caixa(10, 26, 14, 20, 30, 36)
    m["superior_vena_cava"] = vcs & ~m["heart"]
    return g, m


def _casca(fora, lumen):
    import radai_geom
    h = np.asarray(fora["heart"], bool)
    gv = np.asarray(fora.get("great_veins", np.zeros_like(h)), bool)
    g = radai_geom.Grade((2.0, 0.9, 0.9))
    return gv & ~radai_geom.expandir(lumen & ~h, 1.0, g)


def teste_a_margem_vem_antes_do_coracao():
    secao(u"a margem de cada vaso vem antes do coracao (decisao (a))")
    g, m = _fantoma_da_casca()
    lumen = m["superior_vena_cava"].copy()
    fora, meta = E.preparar_full(dict(m), grade=g)
    checar(u"a grande veia conserva a parede, inclusive no Heart_ai",
           "great_veins" in fora and np.array_equal(
               fora["great_veins"], fora["superior_vena_cava"]))
    velha = E.ORDEM_DO_FULL
    try:
        _sem = [p for p in velha if p[0] != "margens"]
        _i = _sem.index(("construcoes", "depois_do_pericardio")) + 1
        E.ORDEM_DO_FULL = tuple(_sem[:_i] + [("margens", u"margem")]
                                + _sem[_i:])
        f2, _m2 = E.preparar_full(dict(m), grade=g)
    finally:
        E.ORDEM_DO_FULL = velha
    checar(u"ISCA: o coracao antes da margem difere do que usa os vasos "
           u"prontos", not np.array_equal(fora["heart"], f2["heart"]))


def teste_a_construcao_recebe_uma_camada():
    secao(u"a construcao recebe uma CAMADA, e nao o FULL")
    import radai_geom
    g = radai_geom.Grade((1.0, 1.0, 1.0))
    forma = (6, 10, 10)
    fig = np.zeros(forma, bool)
    fig[1:5, 2:8, 2:8] = True

    def vandala(masks, grade, log=None):
        masks["liver"] = np.zeros(forma, bool)
        try:
            del masks["spleen"]
        except Exception:
            pass
        return {"isca_saida": fig.copy()}
    entrada = {"cod": "isca_vandala", "funcao": vandala, "momento": "no_fim",
               "exige_hu": False, "exige": (),
               "saidas": {"isca_saida": {"suavizar_mm": 0.0,
                                         "recortar_por": (), "contem": (),
                                         "descricao": u""}}}

    def rodar():
        fora = {"liver": fig.copy(), "spleen": fig.copy()}
        meta = {"construcoes": {}, "observacoes": {}, "nao_sairam": [],
                "tempos": []}
        velho = E.CONSTRUCOES
        E.CONSTRUCOES = [entrada]
        try:
            E._rodar_construcoes(fora, "no_fim", g, None, False, meta, None)
        finally:
            E.CONSTRUCOES = velho
        return fora
    f = rodar()
    checar(u"o que a construcao ESCREVEU nao chegou ao FULL",
           np.array_equal(np.asarray(f["liver"], bool), fig)
           and "spleen" in f, str(sorted(f)))
    checar(u"  e o que ela DEVOLVEU entrou", "isca_saida" in f)
    velho_s = E._Sobreposto
    E._Sobreposto = lambda base: base
    try:
        f2 = rodar()
    finally:
        E._Sobreposto = velho_s
    checar(u"ISCA: sem a camada, a escrita chega ao FULL (reprovaria)",
           not np.asarray(f2["liver"], bool).any() or "spleen" not in f2)


def teste_o_contorno_externo_e_calculado_uma_vez():
    secao(u"o contorno externo e calculado UMA vez por serie")
    import radai_skin
    base = tempfile.mkdtemp(prefix="radai_t_fulloar_")
    velho = radai_skin.contorno_externo
    velho_ctx = E._contorno_externo_da_serie
    chamadas = []

    def _conta(*a, **k):
        chamadas.append(1)
        return velho(*a, **k)
    try:
        serie = _serie(base)
        radai_skin.contorno_externo = _conta
        sd, r, linhas, dest = _rodar(base, serie)
        n1 = len(chamadas)
        checar(u"UMA chamada por serie (pele, parede e a limpeza do FULL)",
               n1 == 1, u"%d chamada(s)" % n1)
        checar(u"  e o tempo dele tem linha propria no log",
               any(u"contorno externo (uma vez)" in l for l in linhas))

        def _sem_cache(ctx, volume_hu, grade, hu_ok, meta, log):
            ctx.pop("externo", None)
            return velho_ctx({}, volume_hu, grade, hu_ok, meta, log)
        E._contorno_externo_da_serie = _sem_cache
        chamadas[:] = []
        _rodar(base, serie)
        checar(u"ISCA: sem guardar, a serie o calcula mais de uma vez "
               u"(reprovaria)", len(chamadas) > 1,
               u"%d chamada(s)" % len(chamadas))
    finally:
        radai_skin.contorno_externo = velho
        E._contorno_externo_da_serie = velho_ctx
        shutil.rmtree(base, ignore_errors=True)


def teste_o_que_nao_saiu_tem_nome():
    secao(u"a construcao vazia diz por que (faltou -> nao_sairam)")
    import radai_geom
    g = radai_geom.Grade((1.0, 1.0, 1.0))
    forma = (6, 10, 10)
    fig = np.zeros(forma, bool)
    fig[1:5, 2:8, 2:8] = True

    def com_motivo(masks, grade, log=None):
        s = E._SaidaComFaltou()
        s.faltou.append(u"sem esterno nesta serie (isca)")
        return s

    def sem_motivo(masks, grade, log=None):
        return {}

    def rodar(fn):
        meta = {"construcoes": {}, "observacoes": {}, "nao_sairam": [],
                "tempos": []}
        velho = E.CONSTRUCOES
        E.CONSTRUCOES = [{"cod": "isca_vazia", "funcao": fn,
                          "momento": "no_fim", "exige_hu": False, "exige": (),
                          "saidas": {"isca_x": {}}}]
        try:
            E._rodar_construcoes({"liver": fig}, "no_fim", g, None, False,
                                 meta, None)
        finally:
            E.CONSTRUCOES = velho
        return meta
    m1 = rodar(com_motivo)
    checar(u"o motivo da construcao chega a `nao_sairam`",
           (u"isca_vazia", u"sem esterno nesta serie (isca)")
           in m1["nao_sairam"], str(m1["nao_sairam"]))
    checar(u"  e fica em `meta['faltou']`, para o registro de casos",
           m1.get("faltou", {}).get("isca_vazia") ==
           [u"sem esterno nesta serie (isca)"])
    m2 = rodar(sem_motivo)
    checar(u"ISCA: o `{}` de antes nao tem motivo (so a frase generica)",
           not any(u"esterno" in m for _c, m in m2["nao_sairam"])
           and any(c == "isca_vazia" for c, _m in m2["nao_sairam"]),
           str(m2["nao_sairam"]))
    fora, _p, _i, _f, linhas, _c = _parede_do_fantoma(
        cru=RO.insumos_fora_do_full(_cruas(com_plugins=False)))
    ditas = [l for l in linhas if l.startswith(u"FULL: `pele_e_parede`")]
    checar(u"a parede que nao sai (torax nao identificado) tem linha no FULL",
           "Skin" in fora and ditas and u"ChestWall" in ditas[0]
           and u"torax nao identificado" in ditas[0], str(ditas)[:220])
    checar(u"  e UMA linha, e nao uma por lado", len(ditas) == 1,
           str(len(ditas)))
    s = E._construir_pericardio({"pericardium": fig.copy()}, g)
    checar(u"o adaptador de radai_constructs devolve o motivo em `faltou`",
           not s and s.faltou and u"coracao do modelo" in s.faltou[0],
           str(getattr(s, "faltou", None)))


def _obs_do_arquivo(caminho):
    ds = pydicom.dcmread(caminho)
    nomes = dict((int(x.ROINumber), str(x.ROIName))
                 for x in ds.StructureSetROISequence)
    return dict((nomes.get(int(o.ReferencedROINumber)),
                 str(getattr(o, "ROIObservationDescription", "") or ""))
                for o in getattr(ds, "RTROIObservationsSequence", []))


def teste_a_descricao_da_serie_chega_ao_dicom():
    secao(u"a descricao de cada construcao chega ao DICOM (FULL e OAR)")
    base = tempfile.mkdtemp(prefix="radai_t_fulloar_")
    velho = E._construir_coracao
    try:
        serie = _serie(base)
        sd, r, linhas, dest = _rodar(base, serie)
        full = _obs_do_arquivo(r["full"])
        oar = _obs_do_arquivo(r["oar"])
        h = full.get("Heart_ai", u"")
        checar(u"o Heart_ai do FULL diz de que foi montado, COM o pericardio",
               u"Heart_ai:" in h and u"Inclui o pericardio" in h, h[:200])
        checar(u"  e o do OAR e a mesma frase", oar.get("Heart_ai") == h)
        p = full.get("Pericardium_ai", u"")
        checar(u"o pericardio corrigido esta no FULL, com a descricao dele",
               u"Pericardio:" in p, p[:160])
        checar(u"  e NAO esta no OAR (spec A5)", "Pericardium_ai" not in oar)
        checar(u"a Bag_Bowel esta so no FULL, com a descricao, e no OAR "
               u"vai a Bag_Bowel_OAR (v8.5)",
               u"Bag_Bowel:" in full.get("Bag_Bowel_ai", u"")
               and "Bag_Bowel_ai" not in oar
               and oar.get("Bag_Bowel_OAR_ai")
               == full.get("Bag_Bowel_OAR_ai") is not None,
               str(sorted(full))[:200])
        def _so_mascara(masks, grade, volume_hu=None, log=None, cru=None,
                        construidas=None):
            s = velho(masks, grade, volume_hu=volume_hu, log=log, cru=cru,
                      construidas=construidas)
            return dict((k, v[0] if isinstance(v, tuple) else v)
                        for k, v in s.items())
        ent = [c for c in E.CONSTRUCOES if c["cod"] == "coracao"][0]
        ent["funcao"] = _so_mascara
        try:
            sd2, r2, _l, _d = _rodar(base, serie)
        finally:
            ent["funcao"] = velho
        h2 = _obs_do_arquivo(r2["full"]).get("Heart_ai", u"")
        checar(u"ISCA: sem a descricao da serie, o DICOM nao diz o que a "
               u"construcao fez (reprovaria)", u"Inclui o pericardio" not in h2,
               h2[:160])
    finally:
        [c for c in E.CONSTRUCOES if c["cod"] == "coracao"][0]["funcao"] = velho
        shutil.rmtree(base, ignore_errors=True)


def teste_a_copia_temporaria_do_oar_e_apagada():
    secao(u"a copia temporaria do OAR tem prefixo e e apagada")
    base = tempfile.mkdtemp(prefix="radai_t_fulloar_")
    velho = E.selecionar_do_full
    velho_ap = RO._apagar_temp_do_oar
    vistos = []

    def _espia(*a, **k):
        r = velho(*a, **k)
        vistos.append(r[0])
        return r
    try:
        serie = _serie(base)
        E.selecionar_do_full = _espia
        _rodar(base, serie)
        pasta = os.path.dirname(vistos[-1]) if vistos else ""
        checar(u"a pasta temporaria do OAR tem o prefixo do motor",
               os.path.basename(pasta).startswith(E.PREFIXO_TEMP_DO_OAR),
               os.path.basename(pasta))
        checar(u"  e nao existe mais depois da gravacao",
               pasta and not os.path.exists(pasta))
        RO._apagar_temp_do_oar = lambda *a, **k: None
        vistos[:] = []
        _rodar(base, serie)
        pasta2 = os.path.dirname(vistos[-1]) if vistos else ""
        checar(u"ISCA: sem a faxina, a copia sobra no temporario (reprovaria)",
               pasta2 and os.path.exists(pasta2))
        shutil.rmtree(pasta2, ignore_errors=True)
        checar(u"a faxina NAO apaga pasta sem o prefixo (motor dublado)",
               _faxina_poupa_pasta_alheia(velho_ap))
    finally:
        E.selecionar_do_full = velho
        RO._apagar_temp_do_oar = velho_ap
        shutil.rmtree(base, ignore_errors=True)


def teste_a_copia_temporaria_do_oar_fast_e_apagada():
    secao(u"a copia temporaria do OAR_Fast tem prefixo e e apagada")
    base = tempfile.mkdtemp(prefix="radai_t_fulloar_")
    velho = E.build_rtstruct
    velho_ap = RO._apagar_temp_do_oar
    vistos = []

    def _espia(*a, **k):
        r = velho(*a, **k)
        vistos.append((k.get("modo"), r[0]))
        return r
    try:
        serie = _serie(base)
        E.build_rtstruct = _espia
        _rodar(base, serie, modo="fast")
        do_fast = [p for m, p in vistos if m == "fast"]
        pasta = os.path.dirname(str(do_fast[-1])) if do_fast else ""
        checar(u"a pasta temporaria do OAR_Fast tem o prefixo do motor",
               os.path.basename(pasta).startswith(E.PREFIXO_TEMP_DO_OAR),
               os.path.basename(pasta))
        checar(u"  e nao existe mais depois da gravacao",
               pasta and not os.path.exists(pasta), pasta)
        vistos[:] = []
        _rodar(base, serie, modo="auto")
        do_full = [getattr(p, "caminho", p) for m, p in vistos if m != "fast"]
        pasta_full = os.path.dirname(str(do_full[-1])) if do_full else ""
        checar(u"a pasta do FULL NAO leva o prefixo do entregue",
               pasta_full and not os.path.basename(pasta_full).startswith(
                   E.PREFIXO_TEMP_DO_OAR), os.path.basename(pasta_full))
        shutil.rmtree(pasta_full, ignore_errors=True)
        RO._apagar_temp_do_oar = lambda *a, **k: None
        vistos[:] = []
        _rodar(base, serie, modo="fast")
        do_fast2 = [p for m, p in vistos if m == "fast"]
        pasta2 = os.path.dirname(str(do_fast2[-1])) if do_fast2 else ""
        checar(u"ISCA: sem a faxina, a copia do OAR_Fast sobra no "
               u"temporario (reprovaria)", pasta2 and os.path.exists(pasta2))
        shutil.rmtree(pasta2, ignore_errors=True)
        RO._apagar_temp_do_oar = velho_ap
        vistos[:] = []
        velho_grava = RO.Saida._gravar_arquivo

        def _falha(self, rt, alvo):
            raise OSError(u"isca: o share caiu no meio da gravacao")
        RO.Saida._gravar_arquivo = _falha
        levantou = False
        try:
            _rodar(base, serie, modo="fast")
        except RuntimeError:
            levantou = True
        finally:
            RO.Saida._gravar_arquivo = velho_grava
        do_fast3 = [p for m, p in vistos if m == "fast"]
        pasta3 = os.path.dirname(str(do_fast3[-1])) if do_fast3 else ""
        checar(u"com a gravacao falhando o FAST levanta, e a copia sai "
               u"assim mesmo (com erro ou sem)",
               levantou and pasta3 and not os.path.exists(pasta3),
               u"levantou=%s pasta=%s existe=%s" % (
                   levantou, os.path.basename(pasta3),
                   bool(pasta3) and os.path.exists(pasta3)))
        vistos[:] = []
        import types
        _real = E.tempfile
        E.tempfile = types.SimpleNamespace(
            mkdtemp=lambda *a, **k: _real.mkdtemp(prefix="radai_t_fulloar_"),
            gettempdir=_real.gettempdir)
        try:
            _rodar(base, serie, modo="fast")
        finally:
            E.tempfile = _real
        do_fast4 = [p for m, p in vistos if m == "fast"]
        pasta4 = os.path.dirname(str(do_fast4[-1])) if do_fast4 else ""
        checar(u"ISCA: com o motor montando sem o prefixo, a pasta nao o tem "
               u"e SOBRA (as duas checagens de cima reprovariam)",
               pasta4 and not os.path.basename(pasta4).startswith(
                   E.PREFIXO_TEMP_DO_OAR) and os.path.exists(pasta4),
               os.path.basename(pasta4))
        shutil.rmtree(pasta4, ignore_errors=True)
    finally:
        E.build_rtstruct = velho
        RO._apagar_temp_do_oar = velho_ap
        shutil.rmtree(base, ignore_errors=True)


def _pastas_do_rs():
    try:
        return set(n for n in os.listdir(tempfile.gettempdir())
                   if n.startswith(E.PREFIXO_TEMP_DO_RS))
    except OSError:
        return set()


def teste_a_copia_temporaria_do_full_e_dos_conjuntos_e_apagada():
    secao(u"a copia temporaria do FULL e dos outros conjuntos tem o prefixo "
          u"da faxina e e apagada")
    base = tempfile.mkdtemp(prefix="radai_t_fulloar_")
    velho = E.build_rtstruct
    velho_rs = RO._apagar_temp_do_rs
    velho_salva = E._salvar_sem_escrever_no_console
    velho_sh = E.shutil
    vistos = []

    def _espia(*a, **k):
        r = velho(*a, **k)
        vistos.append(getattr(r[0], "caminho", r[0]))
        return r
    try:
        serie = _serie(base)
        E.build_rtstruct = _espia
        sd, r, _l, _d = _rodar(base, serie)
        pasta = os.path.dirname(str(vistos[0])) if vistos else ""
        checar(u"a pasta temporaria do FULL comeca por `radai_` (a faxina do "
               u"arranque a conhece)",
               E.PREFIXO_TEMP_DO_RS.startswith(u"radai_")
               and os.path.basename(pasta).startswith(E.PREFIXO_TEMP_DO_RS),
               os.path.basename(pasta))
        checar(u"  e nao existe mais depois da copia, com o FULL na pasta "
               u"da serie", pasta and not os.path.exists(pasta)
               and r.get("full") and os.path.isfile(r["full"]), pasta)
        vistos[:] = []
        alvo_ts = sd.totalsegmentator_cru(_cruas())
        pasta_ts = os.path.dirname(str(vistos[-1])) if vistos else ""
        checar(u"a copia de outro conjunto (o cru do TotalSegmentator) sai "
               u"logo depois de copiada",
               alvo_ts and os.path.isfile(alvo_ts) and pasta_ts
               and os.path.basename(pasta_ts).startswith(E.PREFIXO_TEMP_DO_RS)
               and not os.path.exists(pasta_ts), pasta_ts)

        def _sem_memoria_no_full(rt, caminho):
            if os.path.basename(os.path.dirname(str(caminho))).startswith(
                    E.PREFIXO_TEMP_DO_RS):
                raise MemoryError()
            return velho_salva(rt, caminho)
        E._salvar_sem_escrever_no_console = _sem_memoria_no_full
        vistos[:] = []
        antes = _pastas_do_rs()
        try:
            _sd3, r3, _l3, _d3 = _rodar(base, serie)
        finally:
            E._salvar_sem_escrever_no_console = velho_salva
        pasta3 = os.path.dirname(str(vistos[0])) if vistos else ""
        checar(u"o FULL que falha ao gravar (serie parcial) tambem nao deixa "
               u"a copia", (r3.get("parcial") or {}).get("conjunto") == "full"
               and pasta3 and not os.path.exists(pasta3),
               u"%s %s" % (r3.get("parcial"), pasta3))

        def _sem_memoria(rt, caminho):
            raise MemoryError()
        E._salvar_sem_escrever_no_console = _sem_memoria
        try:
            nada = sd.totalsegmentator_cru(_cruas())
        finally:
            E._salvar_sem_escrever_no_console = velho_salva
        checar(u"o conjunto que falha ao gravar nao deixa a pasta temporaria "
               u"(o motor a apaga antes de levantar)",
               nada is None and not (_pastas_do_rs() - antes),
               str(sorted(_pastas_do_rs() - antes)))

        class _ShutilSemApagar(object):
            def __getattr__(self, nome):
                return getattr(velho_sh, nome)

            def rmtree(self, *a, **k):
                return None
        E.shutil = _ShutilSemApagar()
        E._salvar_sem_escrever_no_console = _sem_memoria
        try:
            sd.totalsegmentator_cru(_cruas())
        finally:
            E._salvar_sem_escrever_no_console = velho_salva
            E.shutil = velho_sh
        sobra = _pastas_do_rs() - antes
        checar(u"ISCA: sem o motor apagar na falha, a pasta temporaria sobra "
               u"(a checagem de cima reprovaria)", bool(sobra), str(sobra))
        for n in sobra:
            shutil.rmtree(os.path.join(tempfile.gettempdir(), n),
                          ignore_errors=True)

        RO._apagar_temp_do_rs = lambda *a, **k: None
        vistos[:] = []
        _rodar(base, serie)
        sd.totalsegmentator_cru(_cruas())
        sobram = [os.path.dirname(str(p)) for p in vistos
                  if os.path.exists(os.path.dirname(str(p)))]
        checar(u"ISCA: sem a faxina da saida, a copia do FULL e a do cru "
               u"sobram no temporario (reprovaria)",
               len(sobram) == 2 and all(os.path.basename(p).startswith(
                   E.PREFIXO_TEMP_DO_RS) for p in sobram), str(sobram))
        for p in sobram:
            shutil.rmtree(p, ignore_errors=True)
    finally:
        E.build_rtstruct = velho
        RO._apagar_temp_do_rs = velho_rs
        E._salvar_sem_escrever_no_console = velho_salva
        E.shutil = velho_sh
        shutil.rmtree(base, ignore_errors=True)


def _faxina_poupa_pasta_alheia(faxina):
    d = tempfile.mkdtemp(prefix="radai_t_fulloar_")
    try:
        alvo = os.path.join(d, "RS.dcm")
        open(alvo, "w").close()
        faxina(alvo, E)
        return os.path.exists(alvo)
    finally:
        shutil.rmtree(d, ignore_errors=True)


def teste_os_niveis_cervicais_entram_crus_e_marcados():
    secao(u"os niveis cervicais: no FULL, crus, marcados; nenhum nivel no OAR")
    import radai_hnlnl as HN
    base = tempfile.mkdtemp(prefix="radai_t_fulloar_")
    try:
        serie = _serie(base)
        n1 = np.zeros((Z, Y, X), bool)
        n1[18:26, 24:32, 56:64] = True
        n2 = np.zeros((Z, Y, X), bool)
        n2[18:26, 24:32, 66:74] = True
        niv = HN.NiveisDaSerie({"Lvl_VIa": n1, "Lvl_VIb": n2,
                                HN.NOME_DA_UNIAO: n1 | n2})
        niv.extensao = {"ok": False, "desce_mm": 45.0,
                        "motivo": u"a uniao desce 45 mm (bateria)"}
        niv.ilhas = [("Lvl_VIa", 0.05, 60.0)]
        ctl = np.zeros((Z, Y, X), bool)
        ctl[18:26, 84:96, 56:70] = True
        cruas = _cruas(com_plugins=False,
                       extra=(("isca_caixa", (18, 26, 84, 96, 56, 70)),))
        sd, r, linhas, dest = _rodar(base, serie, cruas=cruas,
                                     cervicais=niv, suavizar_mm=6.0)
        mf = sd.meta_do_full["mascaras"]
        checar(u"os niveis entram no FULL com o nome do mapa",
               "Lvl_VIa_ai" in r["estruturas_full"]
               and "Lvl_VIb_ai" in r["estruturas_full"],
               str(sorted(r["estruturas_full"]))[:200])
        checar(u"  e NENHUM nivel um a um no OAR",
               not any(n.startswith("Lvl_") for n in r["estruturas"]))
        checar(u"  e a uniao do estudo marcado fica so no FULL",
               "LNL_UNION_ai" not in r["estruturas"]
               and "LNL_UNION_ai" in r["estruturas_full"],
               str(sorted(r["estruturas"]))[:200])
        import radai_records as _RG
        rem = _RG.remocoes_do_full(sd.meta_do_full.get("regras_de_gravacao"))
        checar(u"  a ilha que a limpeza tirou vai ao registro de casos (nunca "
               u"ao RTSTRUCT)", any(x["nome"] == "Lvl_VIa" and x["regra"] == "NIV"
                                    for x in rem), str(rem)[:160])
        checar(u"  CRUS: a mascara gravada e a que o motor deu, voxel a voxel",
               np.array_equal(np.asarray(mf.get("Lvl_VIa"), bool), n1)
               and np.array_equal(np.asarray(mf.get("Lvl_VIb"), bool), n2))
        ctl_f = mf.get("isca_caixa")
        checar(u"  (controle) a mesma caixa como orgao MUDA com a suavizacao",
               ctl_f is not None and not np.array_equal(
                   np.asarray(ctl_f, bool), ctl))
        obs = _obs_do_arquivo(r["full"])
        o1 = [v for k, v in obs.items() if str(k).startswith("Lvl_VIa")]
        checar(u"a medida da extensao vai na descricao de cada nivel",
               o1 and u"ESTUDO MARCADO" in o1[0] and u"45 mm" in o1[0],
               (o1 or [u""])[0][-200:])
        checar(u"  e na da uniao tambem",
               any(u"ESTUDO MARCADO" in v for k, v in obs.items()
                   if str(k).startswith("LNL_UNION")))
        checar(u"e a uniao nao acusa sobreposicao com os proprios niveis "
               u"(ela os CONTEM, e declara)",
               not any(u"SOBREPOSICAO" in l and u"LNL_UNION" in l
                       and u"Lvl_" in l for l in linhas),
               str([l for l in linhas if u"SOBREPOSICAO" in l])[:200])
        import radai_geom
        _g = radai_geom.Grade((3.0, 2.0, 2.0))
        _m = {"Lvl_VIa": n1, "Lvl_VIb": n2, HN.NOME_DA_UNIAO: n1 | n2}
        _sem = dict((k, {"suavizar_mm": 0.0, "recortar_por": (),
                         "contem": ()}) for k in _m)
        checar(u"ISCA: sem o `contem` da uniao, a conferencia do FULL a "
               u"acusaria", any(HN.NOME_DA_UNIAO in (a, b)
                                for a, b, _v, _f in E.sobreposicoes(
                                    _m, _g, construcoes=_sem)))
        obs_l = HN.observacoes_dos_niveis(list(niv))
        checar(u"ISCA: com `list()`, a medida se perde (reprovaria)",
               not any(u"ESTUDO MARCADO" in v for v in obs_l.values()))
    finally:
        shutil.rmtree(base, ignore_errors=True)


_PESCOCO = {
    "head_glands_cavities": (
        ("parotid_gland_left", (18, 26, 20, 28, 74, 78)),
        ("parotid_gland_right", (18, 26, 20, 28, 50, 54)),
        ("submandibular_gland_left", (18, 26, 34, 38, 66, 72))),
    "headneck_muscles": (
        ("sternocleidomastoid_left", (18, 26, 28, 34, 70, 84)),
        ("sternocleidomastoid_right", (18, 26, 28, 34, 44, 58))),
}


def _cervicais_do_pescoco(lados=("left", "right")):
    import radai_hnlnl as HN

    def caixa(z0, z1, y0, y1, x0, x1):
        m = np.zeros((Z, Y, X), bool)
        m[z0:z1, y0:y1, x0:x1] = True
        return m
    l2 = caixa(18, 26, 34, 40, 64, 76)
    r2 = caixa(18, 26, 34, 40, 50, 62)
    niv = HN.NiveisDaSerie({"Lvl_II_L": l2, "Lvl_II_R": r2,
                            HN.NOME_DA_UNIAO: l2 | r2})
    niv.extensao = {"ok": True, "desce_mm": 0.0, "motivo": u"bateria"}
    viii = {"left": caixa(18, 26, 22, 30, 72, 80),
            "right": caixa(18, 26, 22, 30, 48, 56)}
    niv.viii = dict((k, v) for k, v in viii.items() if k in lados)
    return niv, viii


def _cruas_do_pescoco(sem=()):
    cruas = _cruas(com_plugins=False)
    for task, rotulos in _PESCOCO.items():
        lab = np.zeros((Z, Y, X), np.int16)
        idx = {}
        k = 0
        for nome, (z0, z1, y0, y1, x0, x1) in rotulos:
            if nome in sem:
                continue
            k += 1
            lab[z0:z1, y0:y1, x0:x1] = k
            idx[k] = nome
        if idx:
            cruas[task] = E.MasksCruas(lab, idx)
    return cruas


def teste_o_oar_do_pescoco_com_niveis():
    secao(u"o OAR do pescoco: uniao e parotidas do VIII; o FULL com as _ts")
    import radai_hnlnl as HN
    base = tempfile.mkdtemp(prefix="radai_t_fulloar_")
    try:
        serie = _serie(base)
        niv, viii = _cervicais_do_pescoco()
        sd, r, linhas, dest = _rodar(base, serie, cruas=_cruas_do_pescoco(),
                                     cervicais=niv)
        full, oar = set(r["estruturas_full"]), set(r["estruturas"])
        checar(u"o FULL tem os niveis, a uniao, as parotidas do VIII e as do "
               u"TS como _ts", {"Lvl_II_L_ai", "Lvl_II_R_ai", "LNL_UNION_ai",
                                "Parotid_L_ai", "Parotid_R_ai",
                                "Parotid_L_ts", "Parotid_R_ts"} <= full,
               str(sorted(n for n in full if "arot" in n or "L_" in n)))
        checar(u"  e nenhum nome com desempate nem neutro",
               not any(n.startswith(("Parotid1", "Parotid2", "LNL0"))
                       or "Parotid_L2" in n for n in full), str(sorted(full)))
        checar(u"o OAR leva a LNL_UNION_ai e as duas parotidas do VIII",
               {"LNL_UNION_ai", "Parotid_L_ai", "Parotid_R_ai"} <= oar,
               str(sorted(oar)))
        checar(u"  e nenhum Lvl_* e nenhuma _ts",
               not any(n.startswith("Lvl_") or n.endswith("_ts")
                       for n in oar), str(sorted(oar)))
        mf = sd.meta_do_full["mascaras"]
        p_l = np.asarray(mf.get("parotid_lnl_left"), bool)
        ecm_l = np.asarray(mf.get("sternocleidomastoid_left"), bool)
        checar(u"Parotid_L_ai do VIII nao sobrepoe o ECM do FULL",
               p_l.any() and not (p_l & ecm_l).any(),
               u"%d voxels em comum" % int((p_l & ecm_l).sum()))
        checar(u"  e ela e o VIII (menos o ECM), e nao a do TS",
               not (p_l & ~viii["left"]).any()
               and int(p_l.sum()) >= int(viii["left"].sum()) // 2
               and not p_l[:, 20:22, 74:78].any())
        obs = _obs_do_arquivo(r["oar"])
        checar(u"  e no OAR a Parotid_L_ai diz que vem do nivel VIII",
               u"nivel VIII" in (obs.get("Parotid_L_ai") or u""),
               (obs.get("Parotid_L_ai") or u"")[:120])
        checar(u"  e a uniao diz que nao e OAR nem CTV",
               u"NAO E OAR NEM CTV" in (obs.get("LNL_UNION_ai") or u""))
        checar(u"a conferencia estrita da selecao nao alarma a uniao contra a "
               u"submandibular", not any(
                   u"SOBREPOSICAO" in l and u"LNL_UNION" in l
                   and u"submandibular" in l.lower() for l in linhas),
               str([l for l in linhas if u"SOBREPOSICAO" in l])[:240])
        _g = sd.grade()
        _m = {"LNL_UNION": np.asarray(mf.get("LNL_UNION"), bool),
              "submandibular_gland_left": np.asarray(
                  mf.get("submandibular_gland_left"), bool)}
        _c = {"LNL_UNION": {"suavizar_mm": 0.0, "recortar_por": (),
                            "contem": ("Lvl_",)}}
        velho = E.RECIPIENTES_NO_OAR
        try:
            E.RECIPIENTES_NO_OAR = ()
            alarma = E.sobreposicoes(_m, _g, construcoes=_c, estrito=True)
        finally:
            E.RECIPIENTES_NO_OAR = velho
        checar(u"  ISCA: sem `RECIPIENTES_NO_OAR` a selecao estrita alarmaria",
               bool(alarma), str(alarma))
        checar(u"o log da selecao diz que a do TS saiu do OAR por "
               u"substituicao", any(u"substituida pela parotida do nivel "
                                    u"VIII" in l for l in linhas))
        checar(u"a identidade OAR = selecao do FULL continua (a parotida do "
               u"OAR e a do FULL, byte a byte)",
               _contorno_igual(r["oar"], r["full"], "Parotid_L_ai"))
        checar(u"  ISCA: sem o sufixo por ROI as duas viram Parotid_L_ai e uma "
               u"ganharia desempate", E.nome_clinico(
                   "parotid_gland_left", {"Parotid_L_ai"}) != "Parotid_L_ai")
    finally:
        shutil.rmtree(base, ignore_errors=True)


def _contorno_igual(a, b, nome):
    def _dados(caminho):
        ds = pydicom.dcmread(caminho)
        num = dict((str(x.ROIName), int(x.ROINumber))
                   for x in ds.StructureSetROISequence)
        for rc in ds.ROIContourSequence:
            if int(rc.ReferencedROINumber) == num.get(nome):
                return [list(c.ContourData) for c in rc.ContourSequence]
        return None
    da, db = _dados(a), _dados(b)
    return da is not None and da == db


def teste_a_parotida_por_lado():
    secao(u"a parotida e substituida por lado, e so com o ECM daquele lado")
    base = tempfile.mkdtemp(prefix="radai_t_fulloar_")
    try:
        serie = _serie(base)
        niv, viii = _cervicais_do_pescoco()
        sd, r, linhas, dest = _rodar(
            base, serie, cruas=_cruas_do_pescoco(
                sem=("sternocleidomastoid_left",)), cervicais=niv)
        full, oar = set(r["estruturas_full"]), set(r["estruturas"])
        mf = sd.meta_do_full["mascaras"]
        checar(u"sem o ECM esquerdo, o OAR sai sem parotida esquerda, e a do "
               u"TS fica so no FULL, como _ts",
               "Parotid_L_ai" not in oar and "Parotid_L_ts" in full
               and "Parotid_L_ai" not in full
               and "parotid_lnl_left" not in mf, str(sorted(full)))
        checar(u"  e o direito e substituido",
               "Parotid_R_ts" in full and "Parotid_R_ai" in oar
               and "parotid_lnl_right" in mf)
        checar(u"  e o log diz o motivo do lado que ficou",
               any(u"parotida esquerda continua a do TotalSegmentator" in l
                   and u"esternocleidomastoideo" in l for l in linhas))
    finally:
        shutil.rmtree(base, ignore_errors=True)


def teste_a_margem_engolida_pela_grade_vai_na_descricao():
    secao(u"a margem que a grade engole vai na descricao da ROI")
    import radai_geom
    m = np.zeros((10, 40, 40), bool)
    m[3:7, 15:25, 15:25] = True
    res = {}
    for px in (0.98, 1.17, 1.37):
        masks = {"aorta": m.copy(), "trachea": m.copy()}
        r = {}
        E.aplicar_margens_de_oar(masks, radai_geom.Grade((3.0, px, px)),
                                 ressalvas=r)
        res[px] = (r, int(masks["aorta"].sum()))
    r98, v98 = res[0.98]
    checar(u"a 0,98 mm a margem cresce, e nada vai na descricao",
           v98 > int(m.sum()) and "aorta" not in r98, str(r98)[:120])
    for px in (1.17, 1.37):
        r, v = res[px]
        checar(u"a %.2f mm a aorta nao cresce, e a descricao diz que a margem "
               u"sumiu" % px, v == int(m.sum()) and u"0.00 mm no plano"
               in r.get("aorta", u"") and u"Entre cortes" in r["aorta"],
               r.get("aorta", u"")[:160])
        checar(u"  e a traqueia (2 mm, 1 voxel) nao e acusada",
               "trachea" not in r)
    import inspect
    fonte = inspect.getsource(E.preparar_full)
    checar(u"o FULL passa as ressalvas da margem para as observacoes",
           u'ressalvas=meta["observacoes"]' in fonte)
    base = tempfile.mkdtemp(prefix="radai_t_fulloar_")
    try:
        serie = _serie(base)
        sd, r, linhas, dest = _rodar(base, serie)
        obs = _obs_do_arquivo(r["oar"])
        com = sorted(k for k, v in obs.items() if u"Margem de convencao" in v)
        checar(u"na serie de pixel 2 mm, os vasos do OAR dizem a margem que "
               u"sumiu", "GreatArteries_ai" in com and "GreatVeins_ai" in com,
               str(com)[:160])
    finally:
        shutil.rmtree(base, ignore_errors=True)


def _tipos_do_arquivo(caminho):
    ds = pydicom.dcmread(caminho)
    nomes = dict((int(x.ROINumber), str(x.ROIName))
                 for x in ds.StructureSetROISequence)
    return dict((nomes.get(int(o.ReferencedROINumber)),
                 str(getattr(o, "RTROIInterpretedType", "") or ""))
                for o in getattr(ds, "RTROIObservationsSequence", []))


def teste_niveis_e_uniao_nao_saem_como_orgao():
    secao(u"os niveis e a uniao saem com RTROIInterpretedType CONTROL")
    base = tempfile.mkdtemp(prefix="radai_t_fulloar_")
    try:
        serie = _serie(base)
        niv, viii = _cervicais_do_pescoco()
        sd, r, linhas, dest = _rodar(base, serie, cruas=_cruas_do_pescoco(),
                                     cervicais=niv)
        full, oar = _tipos_do_arquivo(r["full"]), _tipos_do_arquivo(r["oar"])
        checar(u"no OAR a LNL_UNION_ai e CONTROL e a parotida e ORGAN",
               oar.get("LNL_UNION_ai") == "CONTROL"
               and oar.get("Parotid_L_ai") == "ORGAN",
               str(dict((k, v) for k, v in oar.items() if "L" in str(k)))[:200])
        checar(u"  e no FULL os Lvl_* tambem",
               full.get("Lvl_II_L_ai") == "CONTROL"
               and full.get("Lvl_II_R_ai") == "CONTROL")
        checar(u"  ISCA: um nome de orgao nao vira CONTROL",
               E.tipo_interpretado("parotid_lnl_left") == "ORGAN"
               and E.tipo_interpretado("LNL_UNION") == "CONTROL")
        o_ts = _obs_do_arquivo(r["full"]).get("Parotid_L_ts") or u""
        checar(u"a Parotid_L_ts do FULL diz que passou pelo pos do FULL (o "
               u"sufixo e o do cru)", u"pos-processamento do FULL" in o_ts
               and u"nao e a crua" in o_ts, o_ts[:160])
    finally:
        shutil.rmtree(base, ignore_errors=True)


def teste_a_uniao_marcada_nao_vai_ao_oar():
    secao(u"a uniao marcada pela regua fica no FULL e nao vai ao OAR")
    base = tempfile.mkdtemp(prefix="radai_t_fulloar_")
    try:
        resultados = {}
        for ok in (False, True):
            serie = _serie(base)
            niv, viii = _cervicais_do_pescoco()
            niv.extensao = {"ok": ok, "desce_mm": 0.0 if ok else 64.0,
                            "motivo": u"desce 64 mm abaixo das claviculas"}
            sd, r, linhas, dest = _rodar(base, serie,
                                         cruas=_cruas_do_pescoco(),
                                         cervicais=niv)
            resultados[ok] = (set(r["estruturas_full"]), set(r["estruturas"]),
                              linhas)
        full, oar, linhas = resultados[False]
        checar(u"marcado: a LNL_UNION_ai fica no FULL e nao vai ao OAR",
               "LNL_UNION_ai" in full and "LNL_UNION_ai" not in oar,
               str(sorted(n for n in oar if "LNL" in n)))
        checar(u"  e as parotidas do VIII continuam no OAR",
               {"Parotid_L_ai", "Parotid_R_ai"} <= oar)
        checar(u"  e o log diz o motivo", any(
            u"LNL_UNION" in l and u"estudo marcado" in l for l in linhas))
        checar(u"  ISCA: sem a marca, a uniao vai ao OAR",
               "LNL_UNION_ai" in resultados[True][1])
    finally:
        shutil.rmtree(base, ignore_errors=True)


def teste_um_resto_do_viii_nao_substitui_a_parotida():
    secao(u"um resto do nivel VIII nao substitui a parotida do TS no OAR")
    import radai_hnlnl as HN
    base = tempfile.mkdtemp(prefix="radai_t_fulloar_")

    def _com_resto():
        niv, viii = _cervicais_do_pescoco()
        resto = np.zeros((Z, Y, X), bool)
        resto[18:20, 22:25, 72:75] = True
        niv.viii = {"left": resto, "right": viii["right"]}
        return niv
    try:
        serie = _serie(base)
        sd, r, linhas, dest = _rodar(base, serie, cruas=_cruas_do_pescoco(),
                                     cervicais=_com_resto())
        full, oar = set(r["estruturas_full"]), set(r["estruturas"])
        mf = sd.meta_do_full["mascaras"]
        checar(u"o VIII residual: o OAR sai sem parotida esquerda, e a do TS "
               u"fica so no FULL, como _ts",
               "Parotid_L_ai" not in oar and "parotid_lnl_left" not in mf
               and "Parotid_L_ts" in full, str(sorted(full)))
        checar(u"  e o direito, plausivel, e substituido",
               "parotid_lnl_right" in mf and "Parotid_R_ts" in full)
        checar(u"  e o log diz por que, com os dois volumes",
               any(u"parotida esquerda continua a do TotalSegmentator" in l
                   and u"cm3 contra" in l for l in linhas))
        velho = (HN.PISO_DA_PAROTIDA_CM3, HN.FRACAO_MINIMA_DO_TS,
                 HN.SOBREPOSICAO_MINIMA_COM_O_TS)
        try:
            (HN.PISO_DA_PAROTIDA_CM3, HN.FRACAO_MINIMA_DO_TS,
             HN.SOBREPOSICAO_MINIMA_COM_O_TS) = (0.0, 0.0, 0.0)
            serie = _serie(base)
            sd2, r2, _l, _d = _rodar(base, serie, cruas=_cruas_do_pescoco(),
                                     cervicais=_com_resto())
        finally:
            (HN.PISO_DA_PAROTIDA_CM3, HN.FRACAO_MINIMA_DO_TS,
             HN.SOBREPOSICAO_MINIMA_COM_O_TS) = velho
        checar(u"  ISCA: sem a conferencia, o resto substituiria a glandula",
               "parotid_lnl_left" in sd2.meta_do_full["mascaras"])
    finally:
        shutil.rmtree(base, ignore_errors=True)


def teste_o_x_na_parotida_vale_para_as_duas_chaves():
    secao(u"o x na parotida tira a parotida do OAR pelas duas chaves")
    base = tempfile.mkdtemp(prefix="radai_t_fulloar_")
    try:
        casos = ((("parotid_lnl_left",), ()),
                 (("parotid_gland_left",), ()),
                 (("parotid_lnl_left",), ("sternocleidomastoid_left",)))
        for fora, sem in casos:
            serie = _serie(base)
            niv, viii = _cervicais_do_pescoco()
            sd, r, linhas, dest = _rodar(
                base, serie, cruas=_cruas_do_pescoco(sem=sem),
                cervicais=niv, oar_fora=list(fora))
            full, oar = set(r["estruturas_full"]), set(r["estruturas"])
            rot = u"%s%s" % (fora[0], u" sem o ECM esquerdo" if sem else u"")
            checar(u"[%s] o OAR sai sem a Parotid_L_ai e com a Parotid_R_ai"
                   % rot, "Parotid_L_ai" not in oar and "Parotid_R_ai" in oar,
                   str(sorted(n for n in oar if "arot" in n)))
            checar(u"[%s]   e ela fica no FULL" % rot,
                   ("Parotid_L_ts" if sem else "Parotid_L_ai") in full)
            shutil.rmtree(serie, ignore_errors=True)
    finally:
        shutil.rmtree(base, ignore_errors=True)
    import radai_sets as RS2
    perm, _t = RO.permitidos_do_oar(["parotid_gland_left"])
    checar(u"permitidos_do_oar tira as duas chaves da parotida esquerda",
           "parotid_gland_left" not in perm and "parotid_lnl_left" not in perm
           and "parotid_lnl_right" in perm)
    velho = RS2.MESMA_ROI_NO_OAR
    try:
        RS2.MESMA_ROI_NO_OAR = {}
        perm2, _t2 = RO.permitidos_do_oar(["parotid_gland_left"])
    finally:
        RS2.MESMA_ROI_NO_OAR = velho
    checar(u"ISCA: sem `radai_sets.MESMA_ROI_NO_OAR` o x na chave do TS "
           u"deixaria a parotida do VIII no OAR", "parotid_lnl_left" in perm2)


def teste_o_pescoco_sem_niveis():
    secao(u"o pescoco sem os niveis: o OAR sem parotida; a do TS so no FULL, "
          u"como _ts")
    base = tempfile.mkdtemp(prefix="radai_t_fulloar_")
    try:
        serie = _serie(base)
        sd, r, linhas, dest = _rodar(base, serie, cruas=_cruas_do_pescoco())
        full, oar = set(r["estruturas_full"]), set(r["estruturas"])
        checar(u"nenhuma parotida no OAR sem os niveis cervicais",
               not any(n.startswith("Parotid") for n in oar),
               str(sorted(n for n in oar if "arot" in n)))
        checar(u"  e no FULL as do TS como Parotid_L_ts e Parotid_R_ts, "
               u"sem nenhuma Parotid_*_ai", {"Parotid_L_ts", "Parotid_R_ts"}
               <= full and "Parotid_L_ai" not in full
               and "Parotid_R_ai" not in full, str(sorted(full)))
        checar(u"  e nenhuma LNL_UNION_ai",
               "LNL_UNION_ai" not in full
               and "parotid_lnl_left" not in sd.meta_do_full["mascaras"])
        o_ts = _obs_do_arquivo(r["full"]).get("Parotid_L_ts") or u""
        checar(u"  a descricao da Parotid_L_ts diz que o STUDY saiu sem ela",
               u"so do nivel VIII" in o_ts and u"STUDY saiu sem ela" in o_ts,
               o_ts[:200])
        checar(u"  e o log diz por que ela nao entra no OAR",
               any(u"Parotid_L_ts nao entra" in l
                   and u"so dos niveis cervicais" in l for l in linhas),
               str([l for l in linhas if u"Parotid" in l][:3]))
        velho_fn, velho_perm = RO._parotida_do_ts_so_no_full, \
            RS.PERMITIDOS_NO_OAR
        try:
            RO._parotida_do_ts_so_no_full = (
                lambda masks, suf, obs, fora, perm: perm)
            RS.PERMITIDOS_NO_OAR = frozenset(
                set(velho_perm) | {"parotid_gland_left", "parotid_gland_right"})
            serie = _serie(base)
            _sd, r2, _l, _d = _rodar(base, serie, cruas=_cruas_do_pescoco())
        finally:
            RO._parotida_do_ts_so_no_full = velho_fn
            RS.PERMITIDOS_NO_OAR = velho_perm
        checar(u"  ISCA: com a regra de antes, a do TS ia ao OAR como "
               u"Parotid_L_ai", "Parotid_L_ai" in set(r2["estruturas"]))
        serie = _serie(base)
        sd3, r3, l3, _d3 = _rodar(base, serie, cruas=_cruas_do_pescoco(),
                                  modo="fast")
        nomes3 = [str(x.ROIName) for x in pydicom.dcmread(
            r3["oar_fast"]).StructureSetROISequence]
        checar(u"no FAST (sem os niveis), o OAR_Fast sai sem parotida",
               not any(n.startswith("Parotid") for n in nomes3), str(nomes3))
        checar(u"  e o log do FAST diz por que",
               any(u"OAR_Fast: sem parotida" in l for l in l3))
    finally:
        shutil.rmtree(base, ignore_errors=True)


def teste_o_pericardio_reune_o_coracao_e_o_recipiente_nao_alarma():
    secao(u"o pericardio reune o coracao; o recipiente do FULL nao alarma")
    import radai_geom
    g = radai_geom.Grade((2.0, 1.0, 1.0))
    forma = (20, 40, 40)

    def caixa(z0, z1, y0, y1, x0, x1):
        a = np.zeros(forma, bool)
        a[z0:z1, y0:y1, x0:x1] = True
        return a
    peri = caixa(4, 16, 8, 30, 8, 30)
    hm = caixa(6, 14, 10, 31, 10, 28)
    spec = dict(E.CONSTRUCOES_POR_SAIDA()["pericardium"])
    checar(u"o pericardio declara `reune` com o coracao do modelo e o "
           u"apendice", "heart_model" in tuple(spec.get("reune") or ())
           and "atrial_appendage_left" in tuple(spec.get("reune") or ()),
           str(spec.get("reune")))

    def segunda_passada(sp):
        m = {"pericardium": peri.copy(), "heart_model": hm.copy()}
        E._suavizar_construcoes(m, g, 1.0, {"pericardium": sp}, [], [])
        return np.asarray(m["pericardium"], bool)
    p1 = segunda_passada(spec)
    checar(u"depois da segunda passada o coracao do modelo esta INTEIRO "
           u"dentro do pericardio", not (hm & ~p1).any(),
           u"%d voxels fora" % int((hm & ~p1).sum()))
    sem = dict(spec)
    sem.pop("reune", None)
    p2 = segunda_passada(sem)
    checar(u"ISCA: sem o `reune`, o coracao fica para fora (reprovaria)",
           (hm & ~p2).any(), u"%d voxels fora" % int((hm & ~p2).sum()))

    cav = caixa(2, 18, 2, 38, 2, 38)
    fig = caixa(4, 12, 6, 20, 6, 20)
    m = {"abdominal_cavity": cav, "liver": fig}
    checar(u"no FULL (regime A4) a cavidade x o que ela contem nao e alarme",
           not E.sobreposicoes(m, g, construcoes={}))
    checar(u"  e no modo ESTRITO (o OAR, se um dia a selecionar) e",
           bool(E.sobreposicoes(m, g, construcoes={}, estrito=True,
                                so=set(m))))
    checar(u"  e sem o regime A4 (os conjuntos de comparacao) tambem e",
           bool(E.sobreposicoes(m, g)))
    velho = E.RECIPIENTES_NO_FULL
    E.RECIPIENTES_NO_FULL = ()
    try:
        isca = E.sobreposicoes(m, g, construcoes={})
    finally:
        E.RECIPIENTES_NO_FULL = velho
    checar(u"ISCA: sem `RECIPIENTES_NO_FULL`, o FULL acusa a cavidade contra "
           u"o figado (reprovaria)", bool(isca), str(isca))


def teste_o_esofago_na_bag_continua_alarme():
    secao(u"o esofago dentro da Bag_Bowel continua alarme no OAR")
    import radai_geom
    g = radai_geom.Grade((2.0, 1.0, 1.0))
    forma = (40, 40, 40)

    def caixa(z0, z1, y0, y1, x0, x1):
        a = np.zeros(forma, bool)
        a[z0:z1, y0:y1, x0:x1] = True
        return a
    bag = caixa(0, 12, 4, 36, 4, 36)
    esof = caixa(8, 40, 18, 22, 18, 22)
    estom = caixa(2, 10, 6, 14, 6, 14)
    spec = dict(E.CONSTRUCOES_POR_SAIDA()["bag_bowel"])
    contem = tuple(spec.get("contem") or ())
    import radai_names as _N
    pendentes = ("esophagus", "heart", "heart_model", "lung_left",
                 "lung_lower_lobe_left", "lung_right", "pericardium")
    casados = [n for n in pendentes if _N.casa_prefixo(n, contem) is not None]
    checar(u"a Bag_Bowel nao declara conter o esofago, o coracao nem o "
           u"pulmao (pergunta ao autor, nao decisao)", not casados,
           str(casados))
    q37 = ("small_intestine", "small_bowel", "colon", "rectum", "stomach",
           "pancreas", "duodenum")
    checar(u"o `contem` da Bag e o da Q37: alcas, pancreas e estomago",
           set(contem) == set(q37), str(contem))

    m = {"bag_bowel": bag, "esophagus": esof, "stomach": estom}
    pares = E.sobreposicoes(m, g, construcoes={"bag_bowel": spec},
                            estrito=True, so=set(m))
    esof_par = [p for p in pares if set(p[:2]) == {"bag_bowel", "esophagus"}]
    checar(u"no OAR (estrito) o esofago dentro da Bag e ALARME",
           bool(esof_par) and abs(esof_par[0][3] - 0.125) < 1e-3,
           str(pares))
    checar(u"  e o estomago, que a Q37 manda manter, nao e",
           not [p for p in pares if "stomach" in p[:2]], str(pares))
    checar(u"  e no FULL (nao estrito) o par construcao x orgao e esperado",
           not E.sobreposicoes(m, g, construcoes={"bag_bowel": spec}))

    isca_spec = dict(spec, contem=contem + ("esophagus",))
    isca = E.sobreposicoes(m, g, construcoes={"bag_bowel": isca_spec},
                           estrito=True, so=set(m))
    checar(u"ISCA: com o esofago no `contem`, o OAR calaria o par "
           u"(reprovaria)", not [p for p in isca
                                 if set(p[:2]) == {"bag_bowel", "esophagus"}],
           str(isca))
    checar(u"a especificacao registrada da Bag e `_CONTEM_DA_BAG` (e nao uma "
           u"copia)", spec.get("contem") is E._CONTEM_DA_BAG)


_UIDS_E_HORAS = ("SOPInstanceUID", "MediaStorageSOPInstanceUID",
                 "SeriesInstanceUID", "StructureSetDate", "StructureSetTime",
                 "InstanceCreationDate", "InstanceCreationTime")


def _diferencas(a, b, caminho=""):
    fora = []
    ka, kb = set(e.tag for e in a), set(e.tag for e in b)
    for t in sorted(ka ^ kb):
        fora.append(u"%s/%s so num" % (caminho, t))
    for t in sorted(ka & kb):
        ea, eb = a[t], b[t]
        nome = ea.keyword or str(t)
        if nome in _UIDS_E_HORAS:
            continue
        if ea.VR == "SQ":
            if len(ea.value) != len(eb.value):
                fora.append(u"%s/%s: %d x %d" % (caminho, nome, len(ea.value),
                                                 len(eb.value)))
                continue
            for i, (ia, ib) in enumerate(zip(ea.value, eb.value)):
                fora.extend(_diferencas(ia, ib, u"%s/%s[%d]" % (caminho,
                                                              nome, i)))
        elif ea.value != eb.value:
            fora.append(u"%s/%s" % (caminho, nome))
    return fora


class _CaminhoDeAntes(object):

    def __enter__(self):
        import numpy as _np
        import radai_geom as _G
        self._G = _G
        self._guardados = [
            (_G.Caixas.__init__, "__defaults__", _G.Caixas.__init__.__defaults__),
            (_G, "_bbox_folgado", _G._bbox_folgado),
            (_G, "_limites", _G._limites),
            (E, "_suavizar_contornos", E._suavizar_contornos),
            (E, "teto_de_suavizacao", E.teto_de_suavizacao),
            (RO.Saida, "serie_lida", RO.Saida.serie_lida),
            (RO.Saida, "externo_da_serie", RO.Saida.externo_da_serie),
            (E, "THREADS_DO_POS", E.THREADS_DO_POS),
            (E, "_mascara_para_o_rt_utils", E._mascara_para_o_rt_utils)]
        RO.Saida.externo_da_serie = lambda self_: None
        E._mascara_para_o_rt_utils = lambda m: _np.ascontiguousarray(
            _np.transpose(m, (1, 2, 0)).astype(_np.bool_))
        _G.Caixas.__init__.__defaults__ = (None,)
        E.THREADS_DO_POS = 1
        RO.Saida.serie_lida = lambda self_: None

        def _bbox_de_antes(mask, folga_voxels):
            achou = _np.where(mask)
            if len(achou[0]) == 0:
                return None
            cortes = []
            for eixo in range(3):
                lo = int(achou[eixo].min()) - int(folga_voxels[eixo])
                hi = int(achou[eixo].max()) + int(folga_voxels[eixo]) + 1
                cortes.append(slice(max(0, lo), min(mask.shape[eixo], hi)))
            return tuple(cortes)
        _G._bbox_folgado = _bbox_de_antes

        def _limites_de_antes(mask):
            m = _np.asarray(mask)
            if not m.any():
                return None
            return tuple((0, int(n) - 1) for n in m.shape)
        _G._limites = _limites_de_antes
        _suav, _teto = E._suavizar_contornos, E.teto_de_suavizacao

        def _suav_de_antes(ds, dxdy=None, suavizar=True, formatados=None,
                           prontos=None):
            return _suav(ds, dxdy, suavizar, prontos=prontos)

        def _teto_de_antes(mask, grade, raio=None):
            return _teto(mask, grade)

        E._suavizar_contornos = _suav_de_antes
        E.teto_de_suavizacao = _teto_de_antes
        return self

    def __exit__(self, *a):
        for obj, nome, valor in self._guardados:
            setattr(obj, nome, valor)
        return False


def teste_o_caminho_rapido_e_o_de_antes():
    secao(u"o pos-processamento rapido e o de antes, byte a byte (F3)")
    import pydicom
    import radai_geom as _G
    base = tempfile.mkdtemp(prefix="radai_t_fulloar_")
    try:
        serie = _serie(base)
        sd1, r1, l1, _d1 = _rodar(base, serie)
        with _CaminhoDeAntes():
            checar(u"(o caminho de antes esta montado: Caixas sem folga)",
                   _G.Caixas({}).folga is None)
            sd2, r2, l2, _d2 = _rodar(base, serie)
        checar(u"(e desmontado depois: a folga de fabrica voltou)",
               _G.Caixas({}).folga == _G.FOLGA_DA_CONFERENCIA)
        for cod in ("full", "oar"):
            a = pydicom.dcmread(r1[cod])
            b = pydicom.dcmread(r2[cod])
            dif = _diferencas(a, b)
            checar(u"%s: nenhum elemento diferente (fora UID e hora), %d ROIs"
                   % (cod.upper(), len(a.StructureSetROISequence)),
                   not dif and len(a.StructureSetROISequence) > 10,
                   u"; ".join(dif[:4]))
        checar(u"os dois caminhos mediram densidade e sobreposicao",
               any(l.startswith(u"sustentacao:") for l in l1)
               and any(l.startswith(u"sustentacao:") for l in l2)
               and any(u"OAR:" in l and u"sobrepos" in l.lower() for l in l1))
        a = pydicom.dcmread(r1["full"])
        b = pydicom.dcmread(r2["full"])
        c = b.ROIContourSequence[0].ContourSequence[0]
        v = [str(x) for x in c.ContourData]
        v[0] = "%.4f" % (float(v[0]) + 0.0001)
        c.ContourData = v
        checar(u"ISCA: um ponto mexido de 0,0001 mm e acusado",
               bool(_diferencas(a, b)))
        import SimpleITK as _sitk
        import radai_skin as _SK
        vol = _sitk.GetArrayFromImage(E.load_sitk(serie))
        velho = E.load_sitk
        velho_ext = _SK.contorno_externo
        leituras = []
        externos = []

        def _conta(*a, **k):
            leituras.append(a)
            return velho(*a, **k)

        def _conta_ext(*a, **k):
            externos.append(1)
            return velho_ext(*a, **k)

        def _uma_serie(caminho_de_antes):
            del leituras[:]
            del externos[:]
            dest = os.path.join(base, "leituras_%d" % len(os.listdir(base)))
            os.makedirs(dest)
            sd = RO.Saida(E, serie, dest, "RS_RadAI_20260925_1a2b3c4d.dcm",
                          tasks=["total_v3"], versao="bateria",
                          suavizar_mm=1.5, log=lambda m: None,
                          modalidade="CT")
            import contextlib
            ctx = (_CaminhoDeAntes() if caminho_de_antes
                   else contextlib.nullcontext())
            E.load_sitk = _conta
            _SK.contorno_externo = _conta_ext
            try:
                with ctx:
                    sd.full_e_oar(_cruas(), volume_hu=vol)
                    _rim = np.array(_cruas()["total_v3"]["kidney_left"],
                                    dtype=bool)
                    _rim[0:2, 0:3, 0:3] = True
                    alvo_nv = sd.conjunto("nv", {"kidney_left": _rim}, "nv")
            finally:
                E.load_sitk = velho
                _SK.contorno_externo = velho_ext
            return len(leituras), alvo_nv, len(externos)
        n_agora, nv_agora, ext_agora = _uma_serie(False)
        n_antes, nv_antes, ext_antes = _uma_serie(True)
        checar(u"a serie e lida UMA vez para a grade, o FULL e um conjunto "
               u"ao lado (antes: %d)" % n_antes, n_agora == 1, str(n_agora))
        checar(u"  (isca) o caminho de antes relia a serie", n_antes >= 3,
               str(n_antes))
        if checar(u"o conjunto ao lado (NV) saiu nos dois caminhos",
                  bool(nv_agora) and bool(nv_antes)
                  and os.path.isfile(nv_agora) and os.path.isfile(nv_antes),
                  u"%s | %s" % (nv_agora, nv_antes)):
            a = pydicom.dcmread(nv_agora)
            b = pydicom.dcmread(nv_antes)
            dif = _diferencas(a, b)
            checar(u"NV: nenhum elemento diferente do caminho de antes (fora "
                   u"UID e hora)", not dif, u"; ".join(dif[:4]))
            c = b.ROIContourSequence[0].ContourSequence[0]
            v = [str(x) for x in c.ContourData]
            v[0] = "%.4f" % (float(v[0]) + 0.0001)
            c.ContourData = v
            checar(u"  ISCA: um ponto mexido de 0,0001 mm no NV e acusado",
                   bool(_diferencas(a, b)))
        checar(u"o contorno externo e calculado UMA vez para o FULL e o "
               u"conjunto ao lado (antes: %d)" % ext_antes, ext_agora == 1,
               str(ext_agora))
        checar(u"  (isca) o caminho de antes o calculava de novo no conjunto",
               ext_antes == 2, str(ext_antes))
        et = list(r1.get("etapas") or [])
        checar(u"o retorno traz as etapas no formato do registro de casos",
               et and all(set(e) >= {"etapa", "segundos", "parte_de"}
                          for e in et)
               and any(e["etapa"].startswith(u"FULL: densidade")
                       for e in et), str(et[:2]))
    finally:
        shutil.rmtree(base, ignore_errors=True)


def teste_a_densidade_fala_em_todo_arquivo_que_a_roda():
    secao(u"a densidade fala em todo arquivo que a roda (F3)")
    import numpy as np
    base = tempfile.mkdtemp(prefix="radai_t_fulloar_")
    try:
        serie = _serie(base)
        linhas = []
        dest = os.path.join(base, "saida_nv")
        os.makedirs(dest)
        sd = RO.Saida(E, serie, dest, "RS_RadAI_20260925_1a2b3c4d.dcm",
                      tasks=["total_v3"], versao="bateria", suavizar_mm=1.5,
                      log=lambda m: linhas.append(str(m)), modalidade="CT")
        rim = np.zeros((Z, Y, X), bool)
        rim[4:14, 40:70, 40:70] = True
        alvo = sd.conjunto("nv", {"kidney_left": rim}, "nv")
        checar(u"o conjunto de comparacao saiu", bool(alvo) and
               os.path.isfile(alvo))
        checar(u"e a densidade FALOU nele, com o rotulo do conjunto",
               any(l.startswith(u"RadAI_NV: sustentacao:") for l in linhas),
               u" | ".join(l for l in linhas if u"sustenta" in l)[:200])
        checar(u"e o tempo de cada passo saiu no log",
               any(u"por passo:" in l and u"densidade" in l for l in linhas),
               u" | ".join(linhas)[-240:])
        import radai_plausibility as _P
        velha = _P.conferir_sustentacao
        vezes = []

        def _conta(*a, **k):
            vezes.append(sorted(a[0]) if a else [])
            return velha(*a, **k)
        _P.conferir_sustentacao = _conta
        try:
            sd2, r2, l2, _d = _rodar(base, serie)
            medidas = [n for v in vezes for n in v]
            n_full_oar = len(vezes)
            sd2.totalsegmentator_cru(_cruas())
            n_cru = len(vezes) - n_full_oar
        finally:
            _P.conferir_sustentacao = velha
        checar(u"ISCA: o FULL fala sem prefixo, como sempre",
               any(l.startswith(u"sustentacao:") for l in l2)
               and not any(l.startswith(u"RadAI_FULL: sustentacao")
                           for l in l2))
        checar(u"na cadeia do entregue cada estrutura e medida UMA vez (o OAR "
               u"mede as dele, o FULL so as que faltam), e nenhuma no TS cru",
               1 <= n_full_oar <= 2 and n_cru == 0
               and len(medidas) == len(set(medidas))
               and set(r2["estruturas"]) <= set(r2["estruturas_full"]),
               u"FULL/OAR %d chamada(s), %d medida(s), %d repetida(s), cru %d"
               % (n_full_oar, len(medidas),
                  len(medidas) - len(set(medidas)), n_cru))
        import inspect as _insp
        _src = _insp.getsource(E.build_rtstruct)
        _de = u"\n                                      and k not in _densidade)"
        ns = dict(vars(E))
        exec(compile(_src.replace(_de, u")"), "<isca-densidade>", "exec"), ns)
        velho_b = E.build_rtstruct
        vezes[:] = []
        E.build_rtstruct = ns["build_rtstruct"]
        _P.conferir_sustentacao = _conta
        try:
            _rodar(base, serie)
        finally:
            E.build_rtstruct = velho_b
            _P.conferir_sustentacao = velha
        rep = [n for v in vezes for n in v]
        checar(u"ISCA: sem a lembranca das medidas, o FULL mede de novo as do "
               u"OAR", _src.count(_de) == 1 and len(rep) > len(set(rep)),
               u"%d medida(s), %d unica(s)" % (len(rep), len(set(rep))))
    finally:
        shutil.rmtree(base, ignore_errors=True)


def _marcas_do_build(fonte):
    import ast
    arv = ast.parse(fonte)
    fn = [n for n in ast.walk(arv)
          if isinstance(n, ast.FunctionDef) and n.name == "build_rtstruct"]
    saida = []
    for c in (ast.walk(fn[0]) if fn else ()):
        if (isinstance(c, ast.Call) and getattr(c.func, "id", "") == "_marca"
                and c.args):
            a0 = c.args[0]
            rot = a0.value if isinstance(a0, ast.Constant) else None
            saida.append((rot, any(k.arg == "rodou" for k in c.keywords)))
    return saida


def teste_o_cru_nao_diz_que_leu_a_serie():
    secao(u"o TS cru nao diz que leu a serie, nem que rodou o Taubin")
    base = tempfile.mkdtemp(prefix="radai_t_fulloar_")
    try:
        serie = _serie(base)
        meta_cru = {}
        juntas = RO.UniaoDeCruas([m for m in _cruas().values() if m])
        E.build_rtstruct(serie, juntas, tasks=["total_v3"],
                         versao_worker="bateria", cru=True, suavizar_mm=0.0,
                         meta=meta_cru, rotulo="RadAI_TS",
                         sufixo_do_conjunto="_ts")
        et_cru = [n for n, _s in meta_cru.get("etapas") or []]
        checar(u"o cru NAO anota a leitura da serie (ele nao le)",
               et_cru and u"serie, grade e imagem" not in et_cru, et_cru)
        contornos = [n for n in et_cru if n.startswith(u"contornos")]
        checar(u"  e o passo dos contornos nao diz Taubin (so o meio pixel)",
               contornos == [u"contornos (meio pixel) e cabecalho"],
               contornos)
        _sd, _r, _l, _d = _rodar(base, serie)
        et_full = [n for n, _s in (_sd.meta_do_full or {}).get("etapas")
                   or []]
        checar(u"controle: o FULL anota a leitura e o Taubin",
               u"serie, grade e imagem" in et_full
               and u"contornos (meio pixel, Taubin) e cabecalho" in et_full,
               et_full)
    finally:
        shutil.rmtree(base, ignore_errors=True)
    with open(os.path.join(pasta_app(AQUI), "engine.py"),
              encoding="utf-8") as f:
        fonte = f.read()
    marcas = _marcas_do_build(fonte)

    def _defeitos(ms):
        d = []
        if not any(r == u"serie, grade e imagem" and tem for r, tem in ms):
            d.append(u"a marca da leitura da serie sem `rodou=`")
        if any(r and u"Taubin" in r for r, _t in ms):
            d.append(u"um rotulo literal que afirma o Taubin")
        if not ms:
            d.append(u"nenhuma `_marca` achada em build_rtstruct")
        return d
    checar(u"por ast: a leitura tem `rodou=` e o rotulo dos contornos e "
           u"montado pelo que rodou", not _defeitos(marcas),
           u"; ".join(_defeitos(marcas)))
    forjada = fonte.replace(u'_marca(u"serie, grade e imagem", rodou=not cru)',
                            u'_marca(u"serie, grade e imagem")', 1)
    checar(u"  ISCA: a marca da leitura sem `rodou=` e acusada",
           forjada != fonte and _defeitos(_marcas_do_build(forjada)))
    i = fonte.find(u"_feitos_no_contorno = [")
    forjada2 = (fonte[:i] + u'_marca(u"contornos (meio pixel, Taubin) e '
                u'cabecalho")\n                ' + fonte[i:]) if i > 0 else fonte
    checar(u"  ISCA: o rotulo literal de antes, que afirma o Taubin, e "
           u"acusado", forjada2 != fonte
           and _defeitos(_marcas_do_build(forjada2)))


_NOME_NA_DESCRICAO = {"esophagus": u"esofago", "heart": u"coracao",
                      "pericardium": u"pericardio", "lung_": u"pulmao"}


def _o_que_a_descricao_esquece(texto):
    import radai_constructs as _RC
    falta = []
    for n in _RC.ORGAOS_DO_TORAX_FORA_DA_BAG:
        pt = _NOME_NA_DESCRICAO.get(n)
        if pt is None or pt not in (texto or u""):
            falta.append(n)
    return falta


def teste_a_descricao_da_bag_diz_o_que_a_receita_tira():
    secao(u"a descricao da Bag_Bowel diz o que a receita tira")
    spec = [s for c in E.CONSTRUCOES if c.get("cod") == "bag_bowel"
            for s in (c.get("saidas") or {}).values()]
    txt_spec = spec[0].get("descricao") if spec else u""
    checar(u"a descricao do registro (`engine.CONSTRUCOES`) cita todo orgao "
           u"do torax que a receita tira", spec
           and not _o_que_a_descricao_esquece(txt_spec),
           _o_que_a_descricao_esquece(txt_spec))
    base = tempfile.mkdtemp(prefix="radai_t_fulloar_")
    try:
        serie = _serie(base)
        _sd, r, _l, _d = _rodar(base, serie)
        for cod in ("full",):
            ds = pydicom.dcmread(r[cod])
            num = dict((int(x.ROINumber), str(x.ROIName))
                       for x in ds.StructureSetROISequence)
            obs = [str(getattr(o, "ROIObservationDescription", "") or "")
                   for o in getattr(ds, "RTROIObservationsSequence", [])
                   if num.get(int(o.ReferencedROINumber), "")
                   == u"Bag_Bowel_ai"]
            checar(u"%s: a Bag_Bowel saiu e a descricao dela no DICOM cita "
                   u"todo orgao do torax que a receita tira" % cod.upper(),
                   obs and not _o_que_a_descricao_esquece(obs[0]),
                   u"%s | falta %s" % (
                       (obs[:1] or [u"(sem Bag_Bowel)"])[0][:90],
                       _o_que_a_descricao_esquece(obs[0] if obs else u"")))
    finally:
        shutil.rmtree(base, ignore_errors=True)
    checar(u"ISCA: a frase de antes, sem o pericardio, e acusada",
           _o_que_a_descricao_esquece(
               u"Bag_Bowel: cavidade abdominal da task trunk_cavities menos "
               u"figado, vesicula, bexiga, baco, vasos, rins, adrenais, "
               u"esofago, coracao e pulmao. Sobrepoe os orgaos abdominais.")
           == ["pericardium"])


def _feito_do_vigia_em_25_09(etapas):
    return [
        {"task": str(e.get("task") or e.get("etapa") or ""),
         "dispositivo": str(e.get("dispositivo") or ""),
         "segundos": int(e.get("segundos") or 0)}
        for e in (etapas or []) if isinstance(e, dict)]


def _registrar_na_memoria(etapas):
    import time
    import radai_records as RR

    class _CasoNaMemoria(RR.Caso):
        def __init__(self, *a, **k):
            self.d = {"etapas": [], "serie": {}, "execucao": {},
                      "resultado": {}, "achados": []}
            self._ident, self._so_trocar, self._log = [], [], ""
            self._t0 = time.time()
            self.base = k.get("base", "")

        def gravar(self, segundos=None):
            self.d["segundos_totais"] = segundos
            return dict(self.d)
    velho = RR.Caso
    RR.Caso = _CasoNaMemoria
    try:
        d = RR.registrar_serie(uid="", identificadores=(), serie={},
                               resultado={"ok": True}, etapas=etapas,
                               segundos_totais=1.0)
    finally:
        RR.Caso = velho
    return d if isinstance(d, dict) else {}, RR


def teste_os_passos_da_cadeia_chegam_ao_registro_de_casos():
    secao(u"os passos da cadeia chegam ao registro de casos (F3)")
    base = tempfile.mkdtemp(prefix="radai_t_fulloar_")
    try:
        serie = _serie(base)
        _sd, r, _l, dest = _rodar(base, serie)
        passos = list(r.get("etapas") or [])
        nomes = set(p.get("etapa") for p in passos)
        pais = set(p.get(RO.PARTE_DE) for p in passos)
        checar(u"toda entrada de entrega['etapas'] e um passo (e_passo)",
               passos and all(RO.e_passo(p) for p in passos),
               str(passos[:2]))
        checar(u"a arvore dos passos fecha: todo pai e o topo ou outro passo",
               pais and all(p == RO.PAI_DOS_PASSOS or p in nomes
                            for p in pais), str(sorted(pais)))
        checar(u"ha passos da cadeia E da montagem do FULL",
               RO.PAI_DOS_PASSOS in pais and any(
                   n.startswith(u"FULL: ") for n in nomes), str(len(passos)))
        checar(u"os passos so tem etapa, segundos e parte_de",
               all(set(p) <= {"etapa", "segundos", RO.PARTE_DE}
                   for p in passos))
        texto = u" ".join(u"%s %s" % (p.get("etapa"), p.get(RO.PARTE_DE))
                          for p in passos)
        checar(u"nenhum passo leva caminho nem o nome do fantoma",
               "\\" not in texto and "/" not in texto
               and u"PAC_FULLOAR" not in texto
               and os.path.basename(dest) not in texto, texto[:160])
        topo = [{"etapa": "TS total_v3", "task": "total_v3",
                 "segundos": 812.4, "maquina": "M1", "dispositivo": "cpu"},
                {"etapa": RO.PAI_DOS_PASSOS, "segundos": r.get("segundos"),
                 "maquina": "M1", "dispositivo": "cpu"}]
        copia_do_topo = [dict(e) for e in topo]
        caso = RO.etapas_do_caso(topo, passos)
        checar(u"vigia: os passos entram LOGO DEPOIS de «FULL e OAR», na "
               u"ordem", caso[:2] == copia_do_topo and caso[2:] == passos,
               str([e.get("etapa") for e in caso[:4]]))
        checar(u"vigia: a lista do chamador nao muda (o lock e o done a "
               u"leem)", topo == copia_do_topo)
        checar(u"chamar de novo sobre o resultado nao duplica",
               RO.etapas_do_caso(caso, passos) == caso)
        linha_final = {"etapa": "serie inteira", "segundos": 900.0}
        checar(u"a linha «serie inteira» acrescentada depois fica no fim",
               RO.etapas_do_caso(topo + [linha_final], passos)[-1]
               == linha_final)
        checar(u"sem_os_passos devolve exatamente o topo",
               RO.sem_os_passos(caso) == copia_do_topo)
        cru = _feito_do_vigia_em_25_09(caso)
        filtrado = _feito_do_vigia_em_25_09(RO.sem_os_passos(caso))
        checar(u"ISCA: sem o filtro, o lock listaria os %d passos como "
               u"task feita" % len(passos),
               len(cru) - len(filtrado) == len(passos) > 0,
               u"%d contra %d" % (len(cru), len(filtrado)))
        checar(u"com o filtro, o lock lista as mesmas 2 entradas de hoje",
               [x["task"] for x in filtrado] == ["total_v3",
                                                  RO.PAI_DOS_PASSOS])
        so = RO.etapas_do_caso([], passos, segundos=r.get("segundos"))
        checar(u"rodar agora: sem a linha do pai, ela e criada com o tempo "
               u"da cadeia", so and so[0] == {
                   "etapa": RO.PAI_DOS_PASSOS,
                   "segundos": round(float(r.get("segundos")), 1)}
               and so[1:] == passos, str(so[:1]))
        checar(u"rodar agora: sem `segundos`, o pai sai sem numero (nao "
               u"inventa zero)",
               RO.etapas_do_caso([], passos)[0] == {
                   "etapa": RO.PAI_DOS_PASSOS})
        so_serie = [{"etapa": "serie inteira", "segundos": 5.0}]
        checar(u"sem passos (a cadeia falhou), a lista volta igual e sem pai",
               RO.etapas_do_caso(so_serie, None, segundos=3.0) == so_serie
               and RO.etapas_do_caso(so_serie, [], segundos=3.0) == so_serie)
        checar(u"entrada de topo nunca e passo (a linha do vigia, a serie)",
               not any(RO.e_passo(e) for e in copia_do_topo + so_serie))
        d, RR = _registrar_na_memoria(caso)
        md = RR.narrativa(d) if d else u""
        checar(u"o registro de casos guarda cada passo com o parte_de",
               len(d.get("etapas") or []) == len(caso)
               and sum(1 for e in d["etapas"] if e.get(RO.PARTE_DE))
               == len(passos), str(len(d.get("etapas") or [])))
        import re
        faltam = [p["etapa"] for p in passos
                  if not re.search(u"\\| ↳+ %s \\| %s \\|" % (
                      re.escape(p["etapa"]), re.escape(str(p["segundos"]))),
                      md)]
        checar(u"a tabela do caso.md tem uma linha por passo, com o tempo, "
               u"marcada como parte (↳)", md and not faltam,
               u", ".join(faltam[:3]))
        checar(u"  e a linha do pai («FULL e OAR») nao e marcada, e a nota "
               u"da soma aparece",
               (u"| %s |" % RO.PAI_DOS_PASSOS) in md
               and u"somar a coluna" in md)
        checar(u"  e os passos da montagem do FULL ficam um nivel abaixo "
               u"(↳↳)", any(u"| ↳↳ FULL: " in l for l in md.splitlines()))
        d0, _rr = _registrar_na_memoria(copia_do_topo)
        md0 = RR.narrativa(d0) if d0 else u""
        checar(u"ISCA: sem etapas_do_caso, o caso.md nao tem passo nenhum",
               md0 and not any(u"| %s |" % p["etapa"] in md0
                               for p in passos))
    finally:
        shutil.rmtree(base, ignore_errors=True)


def _conferir_registro(testes):
    import re
    fonte = open(os.path.abspath(__file__), encoding="utf-8").read()
    definidos = set(re.findall(r"^def (teste_\w+)\(", fonte, re.M))
    faltam = sorted(definidos - set(t.__name__ for t in testes))
    checar(u"todo teste definido esta na lista do main", not faltam,
           ", ".join(faltam))


def teste_a_parede_diz_o_que_aconteceu_nesta_serie():
    secao(u"a parede diz o que aconteceu nesta serie")
    import ast as _ast
    import inspect as _insp
    import textwrap as _tw
    import radai_skin
    d0 = E.DESCRICAO_DA_PAREDE
    checar(u"a margem da descricao e a de `radai_skin.MARGEM_PAREDE_MM`",
           (u"expandidos %.0f mm" % radai_skin.MARGEM_PAREDE_MM) in d0, d0[:90])
    arv = _ast.parse(_tw.dedent(_insp.getsource(radai_skin.parede_toracica)))
    suav = [n for n in _ast.walk(arv)
            if isinstance(n, _ast.Call)
            and getattr(n.func, "attr", None) == "suavizar"
            and len(n.args) >= 2]
    le = [n for n in suav
          if getattr(n.args[1], "id", None) == "SUAVIZACAO_PAREDE_MM"]
    checar(u"`parede_toracica` suaviza com `SUAVIZACAO_PAREDE_MM`, e so com "
           u"ela", bool(suav) and len(le) == len(suav),
           u"%d chamada(s), %d com a constante" % (len(suav), len(le)))
    checar(u"a suavizacao da descricao e a que `parede_toracica` aplica",
           (u"suavizada %g mm" % radai_skin.SUAVIZACAO_PAREDE_MM) in d0,
           d0[:200])
    _velha_s = radai_skin.SUAVIZACAO_PAREDE_MM
    try:
        radai_skin.SUAVIZACAO_PAREDE_MM = 2.5
        d25 = E.descricao_da_parede()
    finally:
        radai_skin.SUAVIZACAO_PAREDE_MM = _velha_s
    checar(u"  e a descricao LE a constante na hora (2,5 mm vira «2.5 mm», "
           u"e nao «2 mm»)", u"suavizada 2.5 mm" in d25, d25[:200])
    checar(u"a descricao diz a base da v8.3 (a cavidade toracica, o derrame) "
           u"e o contorno por corte, e que os vasos nao recortam",
           u"cavidade toracica do lado (pulmao e derrame)" in d0
           and u"um contorno por corte" in d0 and u"sem recorte por vasos" in d0,
           d0[:220])
    d_sem = E.descricao_da_parede(sem_cavidade=True)
    checar(u"  e, sem a cavidade na serie, a base de antes e a nota do derrame",
           u"pulmao, costelas e cartilagens costais expandidos" in d_sem
           and u"um derrame pleural nao foi subtraido" in d_sem,
           d_sem[:220])
    checar(u"a declarada e a da serie completa sao a MESMA frase (o RTSTRUCT "
           u"de uma serie completa nao muda)", E.descricao_da_parede() == d0)
    decl = [v.get("descricao") for c in E.CONSTRUCOES
            for k, v in (c.get("saidas") or {}).items()
            if k in ("ChestWall_L", "ChestWall_R")]
    checar(u"o registro das construcoes declara a mesma frase nos dois lados",
           decl == [d0, d0], str([x[:40] for x in decl]))
    checar(u"a descricao declara a sobreposicao com a mama (Breast_L/R), e "
           u"e ASCII e cabe no ST", u"Breast_L/R" in d0
           and u"Breast_OAR" not in d0 and u"conta nas duas" in d0
           and all(ord(c) < 128 for c in d0) and len(d0) <= 1024)
    pior = E.descricao_da_parede(
        [r for r, _p in radai_skin.RECORTES_QUE_O_LOG_NOMEIA], True)
    checar(u"  e mesmo com TUDO faltando cabe no ST e segue ASCII",
           len(pior) <= 1024 and all(ord(c) < 128 for c in pior), len(pior))

    base = tempfile.mkdtemp(prefix="radai_t_fulloar_")
    velha = E.descricao_da_parede
    try:
        serie = _serie(base)
        sd, r, linhas, dest = _rodar(base, serie, torax=True)
        full = _obs_do_arquivo(r["full"])
        oar = _obs_do_arquivo(r["oar"])
        paredes = sorted(n for n in full if n.startswith("ChestWall"))
        checar(u"(pre-condicao) a parede saiu dos dois lados no FULL",
               len(paredes) == 2, str(paredes))
        checar(u"(pre-condicao) o log diz que esta serie nao tem esterno nem "
               u"escapula", any(u"sem esterno nesta serie" in l
                                for l in linhas)
               and any(u"recortes que NAO vieram" in l and u"escapula" in l
                       for l in linhas))
        for n in paredes:
            d = full.get(n, u"")
            afirma, _sep, nota = d.partition(u"Nesta serie:")
            checar(u"%s: nao afirma o esterno nem a escapula que a serie nao "
                   u"teve" % n, u"esterno (plano" not in afirma
                   and u"escapula" not in afirma, afirma[:160])
            checar(u"  e diz, na nota da serie, o que faltou",
                   u"sem esterno" in nota and u"escapula" in nota, nota[:160])
            checar(u"  e continua com a margem e a sobreposicao com a mama",
                   (u"%.0f mm" % radai_skin.MARGEM_PAREDE_MM) in d
                   and u"Breast_L/R" in d, d[-120:])
            checar(u"  e o OAR copia a mesma frase", oar.get(n) == d,
                   str(oar.get(n))[:80])
        E.descricao_da_parede = lambda *a, **k: d0
        _sd, r_i, _l, _d = _rodar(base, serie, torax=True)
        full_i = _obs_do_arquivo(r_i["full"])
        di = full_i.get(paredes[0] if paredes else "ChestWall_L_ai", u"")
        checar(u"ISCA: com a descricao fixa, o DICOM volta a afirmar o "
               u"esterno que a serie nao tem (a checagem sabe reprovar)",
               u"esterno (plano" in di.partition(u"Nesta serie:")[0],
               di[:120])
    finally:
        E.descricao_da_parede = velha
        shutil.rmtree(base, ignore_errors=True)


def _pedacos_por_corte(m):
    from scipy import ndimage
    m = np.asarray(m, bool)
    pior = 0
    for k in range(m.shape[0]):
        if m[k].any():
            pior = max(pior, int(ndimage.label(m[k])[1]))
    return pior


def _furos_por_corte(m):
    from scipy import ndimage
    m = np.asarray(m, bool)
    return sum(1 for k in range(m.shape[0]) if m[k].any()
               and not np.array_equal(ndimage.binary_fill_holes(m[k]), m[k]))


def _registro_da_parede():
    return dict((k, v) for c in E.CONSTRUCOES
                for k, v in (c.get("saidas") or {}).items())


def teste_a_segunda_passada_recorta_a_parede_de_novo():
    secao(u"v8.3: a segunda passada recorta a parede de novo, e um contorno "
          u"por corte")
    import radai_geom as G
    import radai_skin
    reg = _registro_da_parede()
    for lado in ("ChestWall_L", "ChestWall_R"):
        s = reg.get(lado) or {}
        checar(u"`%s`: o registro recorta de novo por "
               u"`radai_skin.RECORTES_DA_SEGUNDA_PASSADA`" % lado,
               bool(s.get("recortar_por"))
               and tuple(s["recortar_por"])
               == tuple(radai_skin.RECORTES_DA_SEGUNDA_PASSADA),
               str(s.get("recortar_por"))[:120])
        checar(u"  e declara `um_contorno_por_corte`",
               s.get("um_contorno_por_corte") is True)

    g = G.Grade((2.0, 1.0, 1.0))
    forma = (6, 40, 40)
    parede = np.zeros(forma, bool)
    parede[:, 5:35, 5:12] = True
    pulmao_s = np.zeros(forma, bool)
    pulmao_s[:, 5:35, 11:25] = True
    vert = np.zeros(forma, bool)
    vert[2, 18:21, 0:15] = True
    bag = np.zeros(forma, bool)
    bag[:, 31:35, 5:12] = True

    def _rodar_passada(spec_parede):
        masks = {"ChestWall_L": parede.copy(),
                 "lung_upper_lobe_left": pulmao_s.copy(),
                 "vertebrae_T5": vert.copy(), "bag_bowel": bag.copy()}
        constr = {"ChestWall_L": spec_parede,
                  "bag_bowel": dict(reg.get("bag_bowel") or {})}
        linhas = []
        E._suavizar_construcoes(masks, g, 1.5, constr, [], [],
                                log=lambda t: linhas.append(str(t)))
        return np.asarray(masks["ChestWall_L"], bool), linhas

    w, linhas = _rodar_passada(dict(reg.get("ChestWall_L") or {}))
    checar(u"(pre-condicao) a parede continua existindo", bool(w.any()),
           str(int(w.sum())))
    checar(u"a parede nao fica dentro do pulmao suavizado",
           not (w & pulmao_s).any(), u"%d voxels" % int((w & pulmao_s).sum()))
    checar(u"  nem da vertebra suavizada", not (w & vert).any(),
           u"%d voxels" % int((w & vert).sum()))
    checar(u"  nem da Bag_Bowel pronta (construcao, recortada no fim)",
           not (w & bag).any(), u"%d voxels" % int((w & bag).sum()))
    checar(u"um contorno por corte depois dos dois recortes",
           _pedacos_por_corte(w) == 1, str(_pedacos_por_corte(w)))
    checar(u"  e o log diz os cm3 que a regra tirou",
           any(u"um contorno por corte depois da segunda passada" in l
               and u"cm3" in l for l in linhas),
           str([l for l in linhas if u"ChestWall" in l])[:200])

    sem = dict(reg.get("ChestWall_L") or {})
    sem["recortar_por"] = ()
    sem["um_contorno_por_corte"] = False
    wi, _l = _rodar_passada(sem)
    checar(u"ISCA: sem o recorte de novo, a parede fica dentro do pulmao "
           u"suavizado (a checagem reprovaria)", bool((wi & pulmao_s).any()),
           u"%d voxels" % int((wi & pulmao_s).sum()))
    so_rec = dict(reg.get("ChestWall_L") or {})
    so_rec["um_contorno_por_corte"] = False
    wi2, _l = _rodar_passada(so_rec)
    checar(u"ISCA: com o recorte e sem a regra, o corte partido fica com "
           u"DOIS pedacos", _pedacos_por_corte(wi2) >= 2,
           str(_pedacos_por_corte(wi2)))


def _contornos_por_corte_no_arquivo(caminho, prefixo):
    ds = pydicom.dcmread(caminho)
    num, cont, _obs = _rois(ds)
    fora = {}
    for n, nome in num.items():
        if not nome.startswith(prefixo) or n not in cont:
            continue
        por_z = {}
        for c in getattr(cont[n], "ContourSequence", []):
            z = round(float(c.ContourData[2]), 2)
            por_z[z] = por_z.get(z, 0) + 1
        fora[nome] = max(por_z.values()) if por_z else 0
    return fora


def teste_a_parede_na_cadeia_um_contorno_e_sem_vizinhos():
    secao(u"v8.3: a parede na cadeia -- um contorno por corte e sem vizinhos")
    import radai_skin
    base = tempfile.mkdtemp(prefix="radai_t_fulloar_")
    try:
        serie = _serie(base)
        sd, r, linhas, dest = _rodar(base, serie, torax=True)
        mf = sd.meta_do_full["mascaras"]
        paredes = sorted(k for k in mf if str(k).startswith("ChestWall"))
        checar(u"(pre-condicao) a parede saiu dos dois lados no FULL",
               paredes == ["ChestWall_L", "ChestWall_R"], str(paredes))
        checar(u"o log diz que a base foi a cavidade toracica",
               any(u"base = cavidade toracica" in l for l in linhas),
               str([l for l in linhas if u"parede toracica" in l])[:200])
        prefixos = tuple(radai_skin.RECORTES_DA_SEGUNDA_PASSADA)
        viz = [k for k in mf if not str(k).startswith("ChestWall")
               and not str(k).startswith("_")
               and E._nomes.casa_prefixo(k, prefixos) is not None]
        checar(u"(pre-condicao) ha vizinhos do recorte nas mascaras finais",
               len(viz) >= 5, str(sorted(viz)))
        for p in paredes:
            w = np.asarray(mf[p], bool)
            ruins = [(k, int((w & np.asarray(mf[k], bool)).sum()))
                     for k in sorted(viz)]
            ruins = [x for x in ruins if x[1]]
            checar(u"`%s` nao tem voxel de vizinho suavizado" % p, not ruins,
                   str(ruins))
            checar(u"  e um pedaco por corte nas mascaras finais",
                   _pedacos_por_corte(w) <= 1, str(_pedacos_por_corte(w)))
            checar(u"  e nenhum furo (furo e um segundo contorno no RTSTRUCT)",
                   _furos_por_corte(w) == 0, str(_furos_por_corte(w)))
        for cod in ("full", "oar"):
            n = _contornos_por_corte_no_arquivo(r[cod], u"ChestWall")
            checar(u"%s: as duas ChestWall gravadas, cada uma com UM contorno "
                   u"por corte" % cod.upper(),
                   len(n) == 2 and all(v == 1 for v in n.values()), str(n))
        velho = radai_skin._abrir_furos
        try:
            radai_skin._abrir_furos = lambda c: (np.asarray(c, bool).copy(), 0)
            _sd, ri, _l, _d = _rodar(base, serie, torax=True)
            ni = _contornos_por_corte_no_arquivo(ri["full"], u"ChestWall")
        finally:
            radai_skin._abrir_furos = velho
        checar(u"ISCA: sem abrir os furos, o FULL grava mais de um contorno "
               u"num corte (a checagem reprovaria)",
               any(v > 1 for v in ni.values()), str(ni))
    finally:
        shutil.rmtree(base, ignore_errors=True)


def teste_a_recusada_pelo_add_roi_nao_e_julgada():
    secao(u"a recusada pelo add_roi nao e julgada")
    import inspect as _insp
    extra = (("spleen", (2, 10, 34, 42, 60, 68)),)
    _orig = E._adicionar_roi

    def _recusa(rt, mb, nome, cor):
        if str(nome or u"").lower().startswith("spleen"):
            raise ValueError("bateria: recusei %s" % nome)
        return _orig(rt, mb, nome, cor)

    def _falam(linhas):
        return [l for l in linhas if "spleen" in l
                and ("SUSPEITA" in l or l.startswith("sustentacao")
                     or "SOBREPOSICAO" in l)]

    def _com_fonte(de, para):
        src = _insp.getsource(E.build_rtstruct)
        ns = dict(vars(E))
        exec(compile(src.replace(de, para), "<isca-recusa>", "exec"), ns)
        return src.count(de) == 1, ns["build_rtstruct"]

    base = tempfile.mkdtemp(prefix="radai_t_fulloar_")
    velho = E.build_rtstruct
    E._adicionar_roi = _recusa
    try:
        serie = _serie(base)
        _sd, _r, linhas, _d = _rodar(base, serie, cruas=_cruas(extra=extra))
        checar(u"(pre-condicao) o add_roi recusou a spleen, e o log diz",
               any(u"o add_roi recusou" in l and u"Spleen" in l
                   for l in linhas))
        checar(u"nenhuma conferencia (volume, densidade, sobreposicao) fala "
               u"da ROI recusada", not _falam(linhas), str(_falam(linhas)))
        achou, f1 = _com_fonte(u"    _no_arquivo = set(mapa_nomes)\n",
                               u"    _no_arquivo = set(masks)\n")
        E.build_rtstruct = f1
        _sd, _r, l1, _d = _rodar(base, serie, cruas=_cruas(extra=extra))
        E.build_rtstruct = velho
        checar(u"ISCA 1: sobre `masks` inteiro, o piso de volume e a "
               u"densidade voltam a falar da recusada", achou
               and any("SUSPEITA" in l for l in _falam(l1))
               and any(l.startswith("sustentacao") for l in _falam(l1)),
               str(_falam(l1)))
        achou, f2 = _com_fonte(
            u"if k in _no_arquivo\n"
            u"                                      and k not in _densidade)",
            u"if k not in _densidade)")
        E.build_rtstruct = f2
        _sd, _r, l2, _d = _rodar(base, serie, cruas=_cruas(extra=extra))
        E.build_rtstruct = velho
        checar(u"ISCA 2: so a densidade sobre `masks` inteiro — ela volta "
               u"sozinha (a checagem pega a quarta conferencia)", achou
               and any(l.startswith("sustentacao") for l in _falam(l2))
               and not any("SUSPEITA" in l for l in _falam(l2)),
               str(_falam(l2)))
    finally:
        E.build_rtstruct = velho
        E._adicionar_roi = _orig
        shutil.rmtree(base, ignore_errors=True)


def teste_a_bag_nao_guarda_o_coracao_suavizado():
    secao(u"a Bag_Bowel pronta nao guarda o coracao suavizado")
    import inspect as _insp
    import textwrap as _tw
    import radai_constructs as C
    import radai_geom
    g = radai_geom.Grade((3.0, 2.0, 2.0))
    fz, fy, fx = 20, 64, 64

    def _fantoma():
        heart = np.zeros((fz, fy, fx), bool)
        heart[4:16, 16:40, 16:40] = True
        heart[4:16, 30:40, 30:40] = False
        peri = np.zeros((fz, fy, fx), bool)
        peri[3:17, 14:42, 14:42] = True
        peri[3:17, 30:42, 30:42] = False
        bag = np.zeros((fz, fy, fx), bool)
        bag[4:16, 30:56, 30:56] = True
        bag &= ~(heart | peri)
        return {"heart": heart, "pericardium": peri, "bag_bowel": bag}

    def _specs(bag_recorte=None):
        sp = {}
        for c in E.CONSTRUCOES:
            for k, v in (c.get("saidas") or {}).items():
                if k in ("heart", "pericardium", "bag_bowel"):
                    sp[k] = dict(v)
        if bag_recorte is not None:
            sp["bag_bowel"]["recortar_por"] = tuple(bag_recorte)
        return sp

    def _sobra(fn=None, bag_recorte=None):
        m = _fantoma()
        log = []
        (fn or E._suavizar_construcoes)(m, g, 1.5, _specs(bag_recorte), [],
                                        [], log.append)
        b = np.asarray(m["bag_bowel"], bool)
        return (int((b & np.asarray(m["heart"], bool)).sum()),
                int((b & np.asarray(m["pericardium"], bool)).sum()),
                int(b.sum()), log)
    ch, cp, nb, log = _sobra()
    checar(u"a Bag pronta tem ZERO voxel do coracao e do pericardio",
           ch == 0 and cp == 0, u"coracao %d vx, pericardio %d vx" % (ch, cp))
    checar(u"  e nao ficou vazia (o recorte nunca esvazia)", nb > 0, nb)
    checar(u"  e o log diz o recorte pelas construcoes prontas",
           any(u"recortado pelas construcoes prontas" in l for l in log),
           [l for l in log if u"bag_bowel" in l][:2])

    src = _tw.dedent(_insp.getsource(E._suavizar_construcoes))
    ini = src.rfind(u"    for nome in sorted(construcoes):", 0,
                    src.find(u'(construcoes.get(nome) or {}).get("recortar_por")'))
    fim = src.rfind(u"    return tratadas")
    checar(u"  (isca) o bloco esta onde a isca o procura",
           0 < ini < fim, u"%d %d" % (ini, fim))
    ns = dict(vars(E))
    exec(compile(src[:ini] + src[fim:], "<isca-bag>", "exec"), ns)
    ch1, cp1, _nb, _l = _sobra(fn=ns["_suavizar_construcoes"])
    checar(u"ISCA: sem o recorte pelas construcoes prontas, o coracao "
           u"suavizado volta a entrar na Bag (o defeito da revisao)",
           ch1 > 0 or cp1 > 0, u"coracao %d vx, pericardio %d vx" % (ch1, cp1))
    velha = (tuple(C.ORGAOS_FORA_DA_BAG) + tuple(C.vasos_do_motor())
             + tuple(C.compostos_de_vaso()))
    ch2, cp2, _nb, _l = _sobra(bag_recorte=velha)
    checar(u"ISCA: com o `recortar_por` de antes, a sobreposicao volta (as "
           u"duas pecas do conserto sao necessarias)",
           ch2 > 0 or cp2 > 0, u"coracao %d vx, pericardio %d vx" % (ch2, cp2))


def teste_a_glandula_sai_por_lado_no_full():
    secao(u"a glandula mamaria sai por lado no FULL")
    import radai_geom
    base = tempfile.mkdtemp(prefix="radai_t_fulloar_")
    try:
        serie = _serie(base)
        cruas = _cruas()
        gl = np.zeros((Z, Y, X), np.int16)
        gl[10:18, 30:40, 30:100] = 1
        cruas["breasts"] = E.MasksCruas(gl, {1: "breast"})
        sd, r, linhas, dest = _rodar(base, serie, cruas=cruas)
        full = set(r["estruturas_full"])
        oar = set(r["estruturas"])
        checar(u"o FULL leva a glandula POR LADO: Breast_L_ai e Breast_R_ai",
               "Breast_L_ai" in full and "Breast_R_ai" in full,
               str(sorted(n for n in full if "reast" in n)))
        checar(u"  e nao mais o contorno bilateral (breast_ai)",
               "breast_ai" not in full,
               str(sorted(n for n in full if "reast" in n)))
        checar(u"  e os DOIS vao ao OAR (a glandula do TotalSegmentator, "
               u"suavizada; a Breast_OAR saiu na v8.5)",
               set(["Breast_L_ai", "Breast_R_ai"]) <= oar,
               str(sorted(n for n in oar if "reast" in n)))
        checar(u"o log diz a separacao",
               any(u"glandula mamaria por lado" in l for l in linhas))
        checar(u"as mamas tem 3 mm a mais de suavizacao (2,5 + 3 = 5,5 mm)",
               abs(E.suavizacao_de("breast_left", 1.5) - 5.5) < 1e-9
               and abs(E.suavizacao_de("breast_right", 1.5) - 5.5) < 1e-9
               and abs(E.suavizacao_de("liver", 1.5) - 2.5) < 1e-9,
               (E.suavizacao_de("breast_left", 1.5),
                E.suavizacao_de("liver", 1.5)))
        def _lados(sd_):
            mf_ = sd_.meta_do_full["mascaras"]
            bl_ = np.asarray(mf_.get("breast_left", np.zeros(1)), bool)
            br_ = np.asarray(mf_.get("breast_right", np.zeros(1)), bool)
            if bl_.ndim != 3 or br_.ndim != 3:
                return None
            return (bool(bl_[:, :, 70:].any()), bool(bl_[:, :, :56].any()),
                    bool(br_[:, :, :56].any()), bool(br_[:, :, 70:].any()))
        lados = _lados(sd)
        checar(u"  e cada lado no seu lado: `breast_left` na esquerda do "
               u"paciente (o lado do `lung_left`), `breast_right` na direita",
               lados == (True, False, True, False), str(lados))
        _sep = E.separar_glandula_por_lado

        def _trocada(m, g, *a, **k):
            r_ = _sep(m, g, *a, **k)
            if "breast_left" in m and "breast_right" in m:
                m["breast_left"], m["breast_right"] = (m["breast_right"],
                                                       m["breast_left"])
            return r_
        try:
            E.separar_glandula_por_lado = _trocada
            sd_t, _r, _l, _d = _rodar(base, serie, cruas=cruas)
        finally:
            E.separar_glandula_por_lado = _sep
        checar(u"ISCA: com os lados trocados, a checagem de lado reprova (a "
               u"de cima sabe reprovar)", _lados(sd_t) != lados
               and _lados(sd_t) is not None, str(_lados(sd_t)))
        velha = E.ORDEM_DO_FULL
        try:
            E.ORDEM_DO_FULL = tuple(p for p in velha
                                    if p[0] != "glandula_por_lado")
            _sd, r_i, _l, _d = _rodar(base, serie, cruas=cruas)
        finally:
            E.ORDEM_DO_FULL = velha
        full_i = set(r_i["estruturas_full"])
        checar(u"ISCA: sem o passo na ordem, o FULL volta a sair com o "
               u"`breast_ai` bilateral (o defeito da revisao, reproduzido)",
               "breast_ai" in full_i and "Breast_L_ai" not in full_i,
               str(sorted(n for n in full_i if "reast" in n)))
    finally:
        shutil.rmtree(base, ignore_errors=True)
    g = radai_geom.Grade((3.0, 2.0, 2.0))
    m = {"breast": np.zeros((Z, Y, X), bool),
         "lung_left": np.zeros((Z, Y, X), bool),
         "lung_right": np.zeros((Z, Y, X), bool),
         "breast_left": np.zeros((Z, Y, X), bool)}
    m["breast"][10:18, 30:40, 30:100] = True
    m["lung_left"][6:28, 40:80, 70:95] = True
    m["lung_right"][6:28, 40:80, 30:55] = True
    m["breast_left"][10:12, 30:32, 90:92] = True
    cads = m["breast_left"].copy()
    entraram = E.separar_glandula_por_lado(m, g)
    checar(u"com a mama da curadoria numa chave, ela NAO e sobrescrita, o "
           u"outro lado entra e o bilateral sai",
           entraram == ["breast_right"] and (m["breast_left"] == cads).all()
           and "breast" not in m, str(entraram))
    checar(u"sem glandula, nada acontece",
           E.separar_glandula_por_lado({"liver": m["lung_left"]}, g) == [])
    gl2 = np.zeros((Z, Y, X), bool)
    gl2[10:18, 30:40, 30:100] = True
    so = {"breast": gl2.copy()}
    ll = []
    r_so = E.separar_glandula_por_lado(so, g, log=ll.append)
    checar(u"sem referencia para a linha media, a glandula fica bilateral e o "
           u"log diz por que", r_so == [] and "breast" in so
           and "breast_left" not in so
           and any(u"sem referencia para a linha media" in l for l in ll),
           str((r_so, sorted(so), ll)))
    _tem = E._tem_linha_media
    try:
        E._tem_linha_media = lambda masks, cru=None: True
        so_i = {"breast": gl2.copy()}
        r_i = E.separar_glandula_por_lado(so_i, g)
    finally:
        E._tem_linha_media = _tem
    checar(u"ISCA: sem a pergunta pela referencia, a glandula e partida pelo "
           u"meio da imagem (o defeito da verificacao, reproduzido)",
           bool(r_i) and "breast" not in so_i, str(r_i))


def teste_as_conferencias_julgam_o_que_entrou():
    secao(u"as conferencias julgam o que entrou no arquivo")
    import inspect as _insp
    extra = (("prostate", (2, 3, 34, 36, 34, 36)),)

    def _alarmes(linhas):
        return [l for l in linhas
                if "prostate" in l and ("SOBREPOSICAO" in l
                                        or "SUSPEITA" in l)]

    base = tempfile.mkdtemp(prefix="radai_t_fulloar_")
    try:
        serie = _serie(base)
        sd, r, linhas, dest = _rodar(base, serie, cruas=_cruas(extra=extra))
        checar(u"(pre-condicao) a prostate de 4 voxels NAO entrou no arquivo",
               any("NAO ENTRARAM" in l and "prostate (4 vx)" in l
                   for l in linhas)
               and not [n for n in r["estruturas_full"]
                        if "rostat" in n.lower()],
               str([l[:120] for l in linhas if "NAO ENTRARAM" in l]))
        checar(u"nenhum alarme (sobreposicao do OAR, SUSPEITA de volume) fala "
               u"de uma ROI que o arquivo nao tem", not _alarmes(linhas),
               str(_alarmes(linhas)))
        src = _insp.getsource(E.build_rtstruct)
        alvo = u"    _no_arquivo = set(mapa_nomes)\n"
        checar(u"  (isca) o conserto esta onde a isca o procura",
               src.count(alvo) == 1)
        ns = dict(vars(E))
        exec(compile(src.replace(alvo, u"    _no_arquivo = set(masks)\n"),
                     "<isca-no-arquivo>", "exec"), ns)
        velho = E.build_rtstruct
        E.build_rtstruct = ns["build_rtstruct"]
        try:
            _sd, _r, linhas_i, _d = _rodar(base, serie,
                                           cruas=_cruas(extra=extra))
        finally:
            E.build_rtstruct = velho
        al = _alarmes(linhas_i)
        checar(u"ISCA: sobre `masks` inteiro, a prostate descartada volta "
               u"como «SUSPEITA» (o defeito da P20)",
               any("SUSPEITA" in l and "prostate" in l for l in al), str(al))
    finally:
        shutil.rmtree(base, ignore_errors=True)


_RZ, _RY, _RX = 60, 80, 80


def _grade_regras(esp=(2.0, 2.0, 2.0)):
    import radai_geom
    return radai_geom.Grade(esp)


def _vazio_regras():
    return np.zeros((_RZ, _RY, _RX), bool)


def _caixa_regras(z0, z1, y0, y1, x0, x1):
    m = _vazio_regras()
    m[z0:z1, y0:y1, x0:x1] = True
    return m


def _corpo_regras():
    yy, xx = np.ogrid[:_RY, :_RX]
    disco = ((yy - 40) ** 2 + (xx - 40) ** 2) <= 30 ** 2
    return np.broadcast_to(disco, (_RZ, _RY, _RX)).copy()


def _regras(masks, externo=None, cru=None, esp=(2.0, 2.0, 2.0)):
    linhas = []
    rel = E.aplicar_regras_de_gravacao(masks, _grade_regras(esp),
                                       externo=externo, cru=cru,
                                       log=linhas.append)
    return rel, linhas


class _Troca(object):

    def __init__(self, **kw):
        self.kw = kw
        self.velhos = {}

    def __enter__(self):
        for k, v in self.kw.items():
            self.velhos[k] = getattr(E, k)
            setattr(E, k, v)
        return self

    def __exit__(self, *a):
        for k, v in self.velhos.items():
            setattr(E, k, v)
        return False


def teste_as_regras_de_gravacao_fora_do_corpo():
    secao(u"R3: fora do corpo sai; a estrutura que esvazia nao sai")
    corpo = _corpo_regras()
    skull = _caixa_regras(20, 30, 0, 6, 0, 6)
    aorta_dentro = _caixa_regras(20, 40, 35, 45, 35, 45)
    aorta_fora = _caixa_regras(20, 22, 0, 3, 74, 77)
    atravessa = _caixa_regras(20, 24, 62, 75, 38, 42)
    pescoco = dict(("vertebrae_C%d" % n,
                    _caixa_regras(8 * (6 - n), 8 * (6 - n) + 7, 36, 46, 36,
                                  46))
                   for n in (2, 3, 4))
    pescoco["vertebrae_C1"] = _caixa_regras(40, 43, 36, 46, 36, 46)
    pescoco["mandible"] = _caixa_regras(28, 43, 24, 56, 24, 56)
    masks = {"skull": skull.copy(), "aorta": (aorta_dentro | aorta_fora),
             "pectoralis_major_left": atravessa.copy()}
    masks.update(dict((k, v.copy()) for k, v in pescoco.items()))
    rel, linhas = _regras(masks, externo=corpo)
    checar(u"a Skull inteiramente fora do corpo NAO sai (saiu do FULL)",
           "skull" not in masks, sorted(masks))
    r3 = [r for r in rel["removidas"] if r["nome"] == "skull"]
    checar(u"  e o registro diz a regra, o volume e que saiu inteira",
           r3 and r3[0]["inteira"] and r3[0]["regra"].startswith(u"R3")
           and abs(r3[0]["cm3"] - 10 * 6 * 6 / 125.0) < 0.01, str(r3))
    checar(u"  e o log diz, numa linha com o nome",
           any(u"R3" in l and u"skull" in l and u"saiu" in l
               for l in linhas), str(linhas)[:200])
    checar(u"a aorta perde SO o pedaco de fora; o de dentro fica inteiro",
           np.array_equal(np.asarray(masks["aorta"], bool), aorta_dentro))
    checar(u"o pedaco que ATRAVESSA a pele fica inteiro (borda nao e ruido)",
           np.array_equal(np.asarray(masks["pectoralis_major_left"], bool),
                          atravessa))
    checar(u"  e com o pescoco no campo, quem a tirou foi a R3 (e nao a R4)",
           [r["regra"][:2] for r in rel["removidas"]
            if r["nome"] == "skull"] == [u"R3"], str(rel["removidas"])[:200])
    m2 = {"skull": skull.copy()}
    m2.update(dict((k, v.copy()) for k, v in pescoco.items()))
    _regras(m2, externo=None)
    checar(u"ISCA: sem o contorno externo a Skull ficaria (a checagem de "
           u"cima reprovaria)", "skull" in m2)

    import radai_geom
    g = radai_geom.Grade((2.0, 2.0, 2.0))
    vol = np.where(corpo, 40.0, -1000.0).astype("float32")
    so_fora = {"x": skull.copy(), "aorta": (aorta_dentro | aorta_fora)}
    l2 = []
    E.limpar_fora_do_corpo(so_fora, vol, g, log=l2.append, externo=corpo)
    checar(u"`limpar_fora_do_corpo` tira a estrutura inteiramente fora",
           "x" not in so_fora, sorted(so_fora))
    checar(u"  e diz, com a regra", any(u"R3 fora do corpo" in l
                                          and u"`x`" in l for l in l2),
           str(l2)[:160])
    checar(u"  e a parcial continua perdendo so o pedaco",
           np.array_equal(np.asarray(so_fora["aorta"], bool), aorta_dentro))


_PERNA_MAIOR = (64, 33, 28)
_PERNA_MENOR = (64, 95, 27)
_RAIO_FEMUR = 6


def _disco(y, x, r):
    yy, xx = np.mgrid[0:Y, 0:X]
    return ((yy - y) ** 2 + (xx - x) ** 2) <= r ** 2


def _fatia_pernas(z_idx, n):
    img = np.full((Y, X), -1000, dtype=np.int16)
    for (y, x, r) in (_PERNA_MAIOR, _PERNA_MENOR):
        img[_disco(y, x, r)] = 40
        img[_disco(y, x, _RAIO_FEMUR)] = 700
    return img


def _serie_de_pernas(base):
    import make_test_series as _mts
    velho = _mts.fatia
    _mts.fatia = _fatia_pernas
    try:
        serie = os.path.join(base, "pernas")
        _mts.escreve_serie(serie, "PAC_PERNAS", datetime.now(), Z)
    finally:
        _mts.fatia = velho
    return serie


def _cruas_pernas():
    lab = np.zeros((Z, Y, X), np.int16)
    lab[:, _disco(_PERNA_MAIOR[0], _PERNA_MAIOR[1], _RAIO_FEMUR)] = 1
    lab[:, _disco(_PERNA_MENOR[0], _PERNA_MENOR[1], _RAIO_FEMUR)] = 2
    return {"total_v3": E.MasksCruas(lab, {1: "femur_right",
                                           2: "femur_left"})}


def teste_a_r3_numa_tc_so_de_membros():
    secao(u"R3 numa TC so de membros: as duas coxas ficam, e nenhum femur sai")
    import radai_skin
    base = tempfile.mkdtemp(prefix="radai_t_fulloar_")
    try:
        serie = _serie_de_pernas(base)
        sd, r, linhas, dest = _rodar(base, serie, cruas=_cruas_pernas())
        full = set(r.get("estruturas_full") or [])
        oar = set(r.get("estruturas") or [])
        checar(u"os dois femures chegam ao FULL",
               {"Femur_L_ai", "Femur_R_ai"} <= full, str(sorted(full)))
        checar(u"  e os dois Femur_OAR, no FULL e no OAR",
               {"Femur_OAR_L_ai", "Femur_OAR_R_ai"} <= (full & oar),
               u"FULL %s | OAR %s" % (sorted(full), sorted(oar)))
        r3 = [l for l in linhas if u"R3" in l or u"fora do corpo" in l]
        checar(u"  e nenhuma linha da R3 fala de femur (nem no FULL, nem na "
               u"limpeza do `build_rtstruct`)",
               not [l for l in r3 if u"femur" in l.lower()], str(r3)[:300])
        regras = (getattr(sd, "meta_do_full", None) or {}).get(
            "regras_de_gravacao") or []
        checar(u"  e o registro das regras nao tem remocao de femur",
               not [x for x in regras if u"femur" in str(x.get("nome"))],
               str(regras)[:200])
        checar(u"  e o log diz que o corpo da R3 levou o membro",
               any(u"corpo da R3 leva tambem" in l for l in linhas),
               str([l for l in linhas if u"contorno externo" in l])[:300])
        masc = (getattr(sd, "meta_do_full", None) or {}).get("mascaras") or {}
        pele = None
        for k, v in masc.items():
            if str(k).lower().startswith("skin"):
                pele = np.asarray(v, bool)
        menor = np.broadcast_to(_disco(*_PERNA_MENOR), (Z, Y, X))
        maior = np.broadcast_to(_disco(*_PERNA_MAIOR), (Z, Y, X))
        checar(u"a pele continua so na coxa maior (o externo de sempre)",
               pele is not None and pele.any() and not (pele & menor).any()
               and (pele & maior).any(),
               u"chaves %s" % sorted(masc)[:12])

        velho = radai_skin.FRACAO_DO_MAIOR_NO_CORPO
        radai_skin.FRACAO_DO_MAIOR_NO_CORPO = 1.01
        try:
            _sd2, r2, l2, _d2 = _rodar(base, serie, cruas=_cruas_pernas())
        finally:
            radai_skin.FRACAO_DO_MAIOR_NO_CORPO = velho
        full2 = set(r2.get("estruturas_full") or [])
        checar(u"ISCA: com o corpo = o maior componente, o femur da coxa "
               u"menor e o Femur_OAR dele saem (a checagem de cima reprovaria)",
               "Femur_L_ai" not in full2 and "Femur_OAR_L_ai" not in full2
               and "Femur_R_ai" in full2
               and any(u"R3" in l and u"femur_left" in l for l in l2),
               str(sorted(full2)))

        import inspect as _insp
        src = _insp.getsource(E.preparar_full)
        alvo = u'    _corpo = ctx.get("corpo", ctx.get("externo"))\n'
        checar(u"  (isca 2) a linha esta onde a isca a procura",
               src.count(alvo) == 1)
        ns = dict(vars(E))
        exec(compile(src.replace(alvo, u'    _corpo = ctx.get("externo")\n'),
                     "<isca-meta-externo>", "exec"), ns)
        velho_pf = E.preparar_full
        E.preparar_full = ns["preparar_full"]
        try:
            _sd3, r3x, l3, _d3 = _rodar(base, serie, cruas=_cruas_pernas())
        finally:
            E.preparar_full = velho_pf
        full3 = set(r3x.get("estruturas_full") or [])
        checar(u"ISCA 2: com o externo da pele em `meta[\"externo\"]`, a "
               u"limpeza do build_rtstruct tira o femur da coxa menor",
               "Femur_L_ai" not in full3 and "Femur_R_ai" in full3,
               str(sorted(full3)))
    finally:
        shutil.rmtree(base, ignore_errors=True)


def teste_a_limpeza_fora_do_corpo_calcula_o_corpo_da_r3():
    secao(u"R3 no build_rtstruct: sem o contorno pronto, o corpo da R3")
    import radai_geom
    import radai_skin
    g = radai_geom.Grade((3.0, 2.0, 2.0))
    vol = np.broadcast_to(_fatia_pernas(0, 1).astype("float32"),
                          (Z, Y, X)).copy()
    cr = _cruas_pernas()["total_v3"]
    base = {"femur_left": np.asarray(cr["femur_left"], bool),
            "femur_right": np.asarray(cr["femur_right"], bool)}
    m = dict((k, v.copy()) for k, v in base.items())
    linhas = []
    E.limpar_fora_do_corpo(m, vol, g, log=linhas.append)
    checar(u"sem o contorno pronto, os dois femures ficam",
           sorted(m) == ["femur_left", "femur_right"], str(sorted(m)))
    velho = radai_skin.FRACAO_DO_MAIOR_NO_CORPO
    radai_skin.FRACAO_DO_MAIOR_NO_CORPO = 1.01
    try:
        m2 = dict((k, v.copy()) for k, v in base.items())
        E.limpar_fora_do_corpo(m2, vol, g, log=linhas.append)
    finally:
        radai_skin.FRACAO_DO_MAIOR_NO_CORPO = velho
    checar(u"ISCA: com o corpo = o maior componente, o femur da coxa menor "
           u"sai (a checagem de cima reprovaria)",
           sorted(m2) == ["femur_right"], str(sorted(m2)))


def teste_as_regras_de_gravacao_borda_do_campo():
    secao(u"R1: a ponta de estrutura grande na borda do campo nao sai")
    g = _grade_regras()
    checar(u"a faixa e o maior entre 10 mm e 2 cortes (2 mm -> 5 cortes)",
           E.faixa_da_borda(g) == (0, 5), str(E.faixa_da_borda(g)))
    checar(u"  a 5 mm, 2 cortes; a 3,75 mm, 3; a 1 mm, 10",
           [E.faixa_da_borda(_grade_regras((e, 1.0, 1.0)))[1]
            for e in (5.0, 3.75, 1.0)] == [2, 3, 10])

    def _cenario():
        return {
            "lung_lower_lobe_left": _caixa_regras(0, 4, 30, 50, 30, 50),
            "liver": _caixa_regras(0, 12, 20, 40, 20, 40),
            "kidney_left": _caixa_regras(0, 3, 50, 60, 50, 60),
            "eye_lens_left": _caixa_regras(57, 59, 40, 42, 40, 42),
        }
    m = _cenario()
    rel, linhas = _regras(m)
    checar(u"o pulmao de 8 mm na borda SAI (12,8 cm3 < 300, inteiro na faixa)",
           "lung_lower_lobe_left" not in m, sorted(m))
    checar(u"  e o log diz a regra, o volume e a borda",
           any(u"R1" in l and u"lung_lower_lobe_left" in l and u"caudal" in l
               for l in linhas), str(linhas)[:200])
    checar(u"o figado que atravessa a faixa fica", "liver" in m)
    checar(u"o rim pequeno na borda fica (nao e estrutura grande)",
           "kidney_left" in m)
    checar(u"o cristalino na borda fica", "eye_lens_left" in m
           and int(np.asarray(m["eye_lens_left"]).sum()) == 8)
    with _Troca(FAIXA_DA_BORDA_MM=4.0):
        mi = _cenario()
        _regras(mi)
    checar(u"ISCA: com a faixa de 4 mm o pulmao de 8 mm ficaria (a "
           u"checagem de cima reprovaria)", "lung_lower_lobe_left" in mi)

    esp = (2.0, 3.0, 3.0)
    grande = {"lung_upper_lobe_right": _caixa_regras(55, 60, 5, 75, 5, 75)}
    cm3 = 5 * 70 * 70 * 18 / 1000.0
    rel2, _l = _regras(grande, esp=esp)
    checar(u"o pulmao de %.0f cm3 inteiro na borda cranial FICA" % cm3,
           "lung_upper_lobe_right" in grande and cm3 > 300)
    with _Troca(VOLUME_MAXIMO_NA_BORDA_CM3=1000.0):
        gi = {"lung_upper_lobe_right": _caixa_regras(55, 60, 5, 75, 5, 75)}
        _regras(gi, esp=esp)
    checar(u"ISCA: com o piso de 1000 cm3 ele sairia (a checagem de cima "
           u"reprovaria)", "lung_upper_lobe_right" not in gi)

    curta = {"liver": np.ones((8, 10, 10), bool)}
    E.aplicar_regras_de_gravacao(curta, g)
    checar(u"numa serie de 8 cortes (duas faixas cobrem tudo) a R1 nao tira "
           u"nada", "liver" in curta)


def teste_as_regras_de_gravacao_ilhas():
    secao(u"R2: ilhas -- poda por classe (Isensee 2021)")

    def _figado():
        principal = _caixa_regras(5, 45, 10, 35, 10, 35)
        miuda = _caixa_regras(50, 52, 70, 72, 70, 72)
        grande = _caixa_regras(47, 60, 50, 60, 50, 60)
        return principal, miuda, grande
    principal, miuda, grande = _figado()
    m = {"liver": principal | miuda | grande}
    rel, linhas = _regras(m)
    f = np.asarray(m["liver"], bool)
    checar(u"figado (PODA): a ilha miuda (<5%% e <10 cm3) SAI",
           not (f & miuda).any())
    checar(u"  a ilha de 10,4 cm3 (4,9%% do volume) FICA -- as duas condicoes "
           u"juntas", bool((f & grande).sum() == grande.sum()))
    checar(u"  e o corpo principal fica inteiro",
           bool((f & principal).sum() == principal.sum()))
    checar(u"  e o log diz a regra R2 e o nome",
           any(u"R2" in l and u"liver" in l for l in linhas),
           str(linhas)[:200])
    with _Troca(FRACAO_DA_PODA=0.0):
        mi = {"liver": principal | miuda | grande}
        _regras(mi)
    checar(u"ISCA: com a fracao 0 a ilha miuda ficaria (a checagem reprova)",
           bool((np.asarray(mi["liver"], bool) & miuda).any()))

    cubos = _vazio_regras()
    for i in range(25):
        z = 2 + (i // 5) * 12
        x = 2 + (i % 5) * 14
        cubos[z:z + 3, 10:13, x:x + 3] = True
    mc = {"kidney_left": cubos.copy()}
    _regras(mc)
    checar(u"com vinte e cinco pedacos iguais, a maior peca fica (a estrutura nao "
           u"some)", "kidney_left" in mc
           and int(np.asarray(mc["kidney_left"]).sum()) == 27)

    quina = principal.copy()
    quina[45, 35, 35] = True
    mq = {"liver": quina.copy()}
    _regras(mq)
    checar(u"o voxel que toca o corpo so pela quina NAO e ilha",
           bool(np.asarray(mq["liver"], bool)[45, 35, 35]))

    def _com_ilha():
        return (_caixa_regras(20, 24, 20, 25, 20, 25)
                | _caixa_regras(40, 41, 60, 61, 60, 61))
    for nome in ("aorta", "adrenal_gland_left", "eye_lens_left",
                 "optic_nerve_left", "common_carotid_artery_left",
                 "thyroid_gland", "rib_left_4", "vertebrae_T4", "LNL07"):
        mn = {nome: _com_ilha()}
        _r, ln = _regras(mn)
        checar(u"`%s` (NUNCA_PODA): a ilha fica" % nome,
               int(np.asarray(mn[nome]).sum()) == 101, ln[:1])
    with _Troca(nunca_poda=lambda n: None,
                PODA=dict(E.PODA, adrenal_gland_left=u"isca")):
        mi2 = {"adrenal_gland_left": _com_ilha()}
        _regras(mi2)
    checar(u"ISCA: com a adrenal em PODA a ilha dela sairia (a checagem "
           u"reprova)", int(np.asarray(mi2["adrenal_gland_left"]).sum())
           == 100)

    mr = {"colon": principal | miuda}
    rel_r, lr = _regras(mr)
    checar(u"colon (REVISAO): a ilha fica",
           bool((np.asarray(mr["colon"], bool) & miuda).any()))
    checar(u"  e o log diz «ilha mantida para revisao»",
           any(u"ilha mantida para revisao" in l and u"colon" in l
               for l in lr), str(lr)[:200])
    checar(u"  e o relatorio a lista em `revisao`",
           any(x["nome"] == "colon" for x in rel_r["revisao"]))

    checar(u"nenhum nome de PODA cai em NUNCA_PODA",
           not [n for n in E.PODA if E.nunca_poda(n)])
    checar(u"toda entrada de PODA e de GRANDES tem motivo",
           all(E.PODA.values()) and all(E.GRANDES.values()))
    for n in ("adrenal_gland_left", "adrenal_gland_right", "eye_lens_left",
              "eye_lens_right", "optic_nerve_left", "optic_nerve_right",
              "common_carotid_artery_left", "internal_carotid_artery_right",
              "thyroid_gland", "lung_vessels", "teeth_upper",
              "costal_cartilages", "kidney_cyst_left", "great_veins"):
        checar(u"`%s` e NUNCA_PODA (a letra do autor)" % n,
               E.classe_de_poda(n)[0] == "nunca", str(E.classe_de_poda(n)))


def teste_as_regras_de_gravacao_julgam_o_pulmao_e_nao_o_lobo():
    secao(u"R1 e R2 julgam o pulmao de cada lado, e nao o lobo")

    def _borda_mista():
        return {"lung_lower_lobe_right": _caixa_regras(40, 60, 20, 50, 20, 50),
                "lung_middle_lobe_right": _caixa_regras(56, 60, 50, 60, 20,
                                                        50)}
    m = _borda_mista()
    medio = m["lung_middle_lobe_right"].copy()
    rel, linhas = _regras(m)
    checar(u"R1: o lobo medio inteiro na borda FICA quando o pulmao direito "
           u"atravessa a faixa", "lung_middle_lobe_right" in m
           and np.array_equal(np.asarray(m["lung_middle_lobe_right"], bool),
                              medio), sorted(m))
    E.aplicar_compostos(m)
    cm3_pd = float(np.asarray(m.get("lung_right"), bool).sum()) * 0.008
    checar(u"  e o `lung_right` composto tem os dois lobos (153,6 cm3)",
           abs(cm3_pd - 153.6) < 0.01, "%.2f" % cm3_pd)
    checar(u"  e nenhuma remocao foi registrada", not rel["removidas"],
           str(rel["removidas"])[:200])
    with _Troca(ORGAOS_POR_PARTES=(),
                GRANDES=dict(E.GRANDES, lung_middle_lobe_right=u"isca")):
        mi = _borda_mista()
        _regras(mi)
    checar(u"ISCA: julgando o lobo sozinho, o medio sairia (a checagem de "
           u"cima reprovaria)", "lung_middle_lobe_right" not in mi)

    ml = {"lung_upper_lobe_left": _caixa_regras(56, 60, 20, 40, 50, 70),
          "lung_lower_lobe_left": _caixa_regras(56, 60, 40, 50, 50, 70),
          "liver": _caixa_regras(10, 50, 10, 40, 10, 40)}
    rel2, l2 = _regras(ml)
    checar(u"R1: o pulmao esquerdo inteiro na faixa (19,2 cm3) sai -- os "
           u"dois lobos", "lung_upper_lobe_left" not in ml
           and "lung_lower_lobe_left" not in ml, sorted(ml))
    checar(u"  e o registro diz cada lobo, inteiro, pela R1",
           sorted(r["nome"] for r in rel2["removidas"]
                  if r["regra"].startswith(u"R1") and r["inteira"])
           == ["lung_lower_lobe_left", "lung_upper_lobe_left"],
           str(rel2["removidas"])[:200])
    checar(u"  e o log diz o lobo, o pulmao e a borda",
           any(u"R1" in l and u"lung_upper_lobe_left" in l
               and u"lung_left" in l and u"cranial" in l for l in l2),
           str(l2)[:240])

    def _fissura():
        inf = _caixa_regras(10, 40, 20, 50, 20, 50)
        med = _caixa_regras(10, 40, 50, 60, 20, 50)
        erro = _caixa_regras(25, 27, 30, 32, 30, 32)
        inf &= ~erro
        med |= erro
        solta = _caixa_regras(50, 52, 70, 72, 70, 72)
        return {"lung_lower_lobe_right": inf | solta,
                "lung_middle_lobe_right": med}, erro, solta
    mf, erro, solta = _fissura()
    rel3, l3 = _regras(mf)
    checar(u"R2: a ilha do lobo medio DENTRO do inferior (erro de fissura) "
           u"fica -- o pulmao nao ganha buraco",
           bool((np.asarray(mf["lung_middle_lobe_right"], bool) & erro).sum()
                == erro.sum()))
    checar(u"  e a ilha do PULMAO (longe dos dois lobos) sai",
           not (np.asarray(mf["lung_lower_lobe_right"], bool) & solta).any())
    checar(u"  e o log diz a R2 com o lobo e o pulmao",
           any(u"R2" in l and u"lung_lower_lobe_right" in l
               and u"lung_right" in l for l in l3), str(l3)[:240])
    E.aplicar_compostos(mf)
    checar(u"  e o `lung_right` composto e o bloco inteiro (36.000 voxels, sem "
           u"buraco e sem a ilha solta)",
           int(np.asarray(mf["lung_right"], bool).sum()) == 36000,
           int(np.asarray(mf["lung_right"], bool).sum()))
    with _Troca(ORGAOS_POR_PARTES=(),
                PODA=dict(E.PODA, lung_middle_lobe_right=u"isca",
                          lung_lower_lobe_right=u"isca")):
        mfi, erro_i, _s = _fissura()
        _regras(mfi)
    checar(u"ISCA: julgando o lobo sozinho, a ilha da fissura sairia (a "
           u"checagem de cima reprovaria)",
           not (np.asarray(mfi["lung_middle_lobe_right"], bool)
                & erro_i).any())

    checar(u"os orgaos julgados pela uniao estao em GRANDES, em PODA e em "
           u"COMPOSTOS", all(o in E.GRANDES and o in E.PODA
                              and o in E.COMPOSTOS
                              for o in E.ORGAOS_POR_PARTES)
           and set(E.ORGAOS_POR_PARTES) == {"lung_left", "lung_right"},
           str(E.ORGAOS_POR_PARTES))
    lobos = [p for o in E.ORGAOS_POR_PARTES for p in E.COMPOSTOS[o]]
    checar(u"  e nenhum lobo tem entrada propria em GRANDES nem em PODA "
           u"(entrada de lobo seria o criterio da parte)",
           not [p for p in lobos if p in E.GRANDES or p in E.PODA])


def teste_as_regras_de_gravacao_portoes_de_regiao():
    secao(u"R4: os portoes de regiao (coracao, cranio, encefalo)")
    g = _grade_regras()

    def _pelve(coracao):
        return {"heart": coracao.copy(),
                "pericardium": _caixa_regras(29, 33, 28, 52, 28, 52),
                "hip_left": _caixa_regras(10, 30, 10, 30, 50, 70),
                "hip_right": _caixa_regras(10, 30, 10, 30, 10, 30),
                "urinary_bladder": _caixa_regras(10, 20, 35, 45, 35, 45)}
    dois_cortes = _caixa_regras(30, 32, 30, 50, 30, 50)
    with _Troca(VOLUME_MINIMO_CORACAO_CM3=PISO_DO_CORACAO_DE_FABRICA):
        linhas = []
        fora, meta = E.preparar_full(_pelve(dois_cortes), grade=g,
                                     log=linhas.append)
        checar(u"o coracao de 2 cortes numa pelve SAI: nem o do modelo nem o "
               u"Heart_ai", "heart_model" not in fora and "heart" not in fora,
               sorted(fora))
        checar(u"  e o pericardio sai com ele (o saco sem o coracao)",
               "pericardium" not in fora)
        r4 = [r for r in meta.get("regras_de_gravacao", [])
              if r["regra"].startswith(u"R4")]
        checar(u"  e o `meta` registra a R4 com o volume",
               any(r["nome"] == "heart_model" and abs(r["cm3"] - 6.4) < 0.01
                   for r in r4), str(r4)[:200])
        checar(u"  e o log diz a regra",
               any(u"R4" in l and u"heart_model" in l for l in linhas),
               str([l for l in linhas if u"R4" in l])[:200])
        nao = dict(meta.get("nao_sairam") or [])
        checar(u"  e o Heart_ai «nao saiu» PELA REGRA, e nao por falta do "
               u"modelo", u"R4" in (nao.get("coracao") or u""),
               nao.get("coracao"))
        grande = _caixa_regras(20, 35, 20, 60, 25, 50)
        fora2, _m2 = E.preparar_full(_pelve(grande), grade=g)
        checar(u"o coracao de 120 cm3 sem torax FICA, e o Heart_ai sai",
               "heart_model" in fora2 and "heart" in fora2, sorted(fora2))
        torax = _pelve(dois_cortes)
        torax.update({
            "lung_left": _caixa_regras(10, 50, 10, 70, 45, 60),
            "clavicula_left": _caixa_regras(48, 50, 10, 14, 45, 60),
            "scapula_left": _caixa_regras(40, 48, 70, 75, 45, 60)})
        fora3, _m3 = E.preparar_full(torax, grade=g)
        checar(u"o coracao pequeno COM torax identificado fica",
               "heart_model" in fora3, sorted(fora3))
    fora_i, _mi = E.preparar_full(_pelve(dois_cortes), grade=g)
    checar(u"ISCA: com o piso baixado a 1 cm3 o coracao de 2 cortes ficaria "
           u"(a checagem de cima reprovaria)", "heart_model" in fora_i)

    velha = E.aplicar_regras_de_gravacao
    cons = [c for c in E.CONSTRUCOES if c["cod"] == "coracao"][0]
    fn_velha = cons["funcao"]

    def _so_diz(masks, grade, **kw):
        return {"removidas": [], "revisao": [],
                "saiu": {"heart_model": u"R4 (isca: disse e nao apagou)"}}

    def _quebra(*a, **k):
        raise RuntimeError(u"isca")
    try:
        E.aplicar_regras_de_gravacao = _so_diz
        cons["funcao"] = _quebra
        fora_r, _mr = E.preparar_full(_pelve(dois_cortes), grade=g)
        E.aplicar_regras_de_gravacao = (
            lambda masks, grade, **kw: {"removidas": [], "revisao": [],
                                        "saiu": {}})
        fora_r2, _mr2 = E.preparar_full(_pelve(dois_cortes), grade=g)
    finally:
        E.aplicar_regras_de_gravacao = velha
        cons["funcao"] = fn_velha
    checar(u"o recuo `_passo_coracao_do_modelo` nao traz de volta o coracao "
           u"que a regra tirou", "heart" not in fora_r, sorted(fora_r))
    checar(u"ISCA: sem a regra ter dito, o recuo o traria (a checagem de "
           u"cima reprovaria)", "heart" in fora_r2, sorted(fora_r2))

    def _cabeca(**extra):
        m = {"skull": _caixa_regras(24, 36, 24, 56, 24, 56)}
        m.update(extra)
        return m
    sem = _cabeca(vertebrae_T4=_caixa_regras(10, 14, 38, 42, 38, 42))
    rel, linhas = _regras(sem)
    checar(u"a Skull numa serie sem cabeca e sem pescoco SAI",
           "skull" not in sem, sorted(sem))
    checar(u"  e o log diz a regra e o laudo do pescoco",
           any(u"R4" in l and u"skull" in l and u"pescoco" in l
               for l in linhas), str(linhas)[:200])
    c700 = lambda z0: _caixa_regras(z0, z0 + 7, 36, 46, 36, 46)
    c1 = _caixa_regras(34, 37, 36, 46, 36, 46)
    com_pescoco = _cabeca(vertebrae_C4=c700(10), vertebrae_C3=c700(18),
                          vertebrae_C2=c700(26), vertebrae_C1=c1)
    _regras(com_pescoco)
    checar(u"a Skull com C2, C3 e C4 (5,6 cm3 cada) e a mandibula no "
           u"campo (98 cm3 pelo skull, do C1 ao C4) FICA",
           "skull" in com_pescoco)
    pequena = {"skull": _caixa_regras(24, 34, 30, 50, 30, 50),
               "vertebrae_C4": c700(10), "vertebrae_C3": c700(18),
               "vertebrae_C2": c700(26), "vertebrae_C1": c1}
    _regras(pequena)
    checar(u"com C2, C3 e C4 mas so 32 cm3 de mandibula (a TC de torax que "
           u"sobe ao C1) nao e pescoco: a Skull SAI", "skull" not in pequena)
    c2_curta = _caixa_regras(26, 31, 36, 46, 36, 46)
    sem_c2 = _cabeca(vertebrae_C4=c700(10), vertebrae_C3=c700(18),
                     vertebrae_C2=c2_curta, vertebrae_C1=c1)
    _regras(sem_c2)
    checar(u"com a C2 de 4 cm3 (abaixo do piso) a Skull SAI (as tres juntas)",
           "skull" not in sem_c2)
    with _Troca(VOLUME_MINIMO_VERTEBRA_CERVICAL_CM3=10.0):
        pi = _cabeca(vertebrae_C4=c700(10), vertebrae_C3=c700(18),
                     vertebrae_C2=c700(26), vertebrae_C1=c1)
        _regras(pi)
    checar(u"ISCA: com o piso da cervical em 10 cm3 a Skull com pescoco "
           u"sairia (a checagem de cima reprovaria)", "skull" not in pi)
    enc = _caixa_regras(20, 46, 20, 50, 25, 50)
    com_cabeca = {"skull": _caixa_regras(46, 50, 20, 50, 25, 50),
                  "brain": enc.copy()}
    _regras(com_cabeca)
    checar(u"com o encefalo de 156 cm3 (cabeca), a Skull e o encefalo ficam",
           "skull" in com_cabeca and "brain" in com_cabeca)
    so_ponta = {"skull": _caixa_regras(20, 30, 20, 40, 20, 40),
                "brain": _caixa_regras(24, 26, 25, 35, 25, 35)}
    _regras(so_ponta)
    checar(u"o encefalo de 1,6 cm3 sem pescoco SAI, com a Skull",
           "brain" not in so_ponta and "skull" not in so_ponta,
           sorted(so_ponta))

    fonte = open(os.path.join(pasta_app(AQUI), "radai_watcher.py"),
                 encoding="utf-8").read()
    delega, copias = _pescoco_do_vigia(fonte)
    checar(u"o vigia DELEGA a medida do pescoco a engine.pescoco_no_campo",
           delega, fonte[fonte.find("def pescoco_no_campo"):][:200])
    checar(u"  e nao tem mais a copia das constantes nem da conta",
           not copias, copias)
    velho = (u"VERTEBRAS_DO_PESCOCO = (\"vertebrae_C2\", \"vertebrae_C3\")\n"
             u"def pescoco_no_campo(masks, grade, cru=None):\n"
             u"    vols = {}\n    return all(vols.values()), u''\n")
    checar(u"ISCA: o vigia com a copia de antes (constante e conta propria) "
           u"reprova as duas", _pescoco_do_vigia(velho) == (False,
                                                            ["VERTEBRAS_DO_PESCOCO"]),
           str(_pescoco_do_vigia(velho)))


def _pescoco_do_vigia(fonte):
    import ast
    arv = ast.parse(fonte)
    delega, copias = False, []
    for no in arv.body:
        if isinstance(no, ast.Assign):
            for t in no.targets:
                if isinstance(t, ast.Name) and t.id in (
                        "VERTEBRAS_DO_PESCOCO",
                        "VOLUME_MINIMO_VERTEBRA_CERVICAL_CM3", "CERVICAIS"):
                    copias.append(t.id)
        if isinstance(no, ast.FunctionDef) and no.name == "pescoco_no_campo":
            for sub in ast.walk(no):
                if (isinstance(sub, ast.Call)
                        and isinstance(sub.func, ast.Attribute)
                        and sub.func.attr == "pescoco_no_campo"
                        and isinstance(sub.func.value, ast.Name)
                        and sub.func.value.id == "engine"):
                    delega = True
    return delega, copias


def teste_a_ilha_em_revisao_so_de_quem_saiu_no_arquivo():
    secao(u"a ilha em revisao so de estrutura que saiu no arquivo")
    def _cenario():
        principal = _caixa_regras(40, 50, 30, 50, 30, 50)
        ilha = _caixa_regras(52, 54, 60, 62, 60, 62)
        colon = (_caixa_regras(5, 30, 10, 30, 50, 70)
                 | _caixa_regras(32, 33, 10, 12, 50, 52))
        return {"skull": principal | ilha, "colon": colon,
                "vertebrae_T4": _caixa_regras(10, 14, 38, 42, 38, 42)}
    m = _cenario()
    rel, linhas = _regras(m)
    nomes_rev = [x["nome"] for x in rel["revisao"]]
    checar(u"a R4 tirou o cranio (sem cabeca e sem pescoco)",
           "skull" not in m and "skull" in rel["saiu"], sorted(m))
    checar(u"  e ele NAO fica na lista de ilhas em revisao",
           "skull" not in nomes_rev, str(nomes_rev))
    checar(u"  e o colon, que ficou, continua nela (controle)",
           "colon" in nomes_rev and "colon" in m, str(nomes_rev))
    checar(u"  e o log diz que a entrada saiu da lista, com a regra",
           any(u"skull" in l and u"lista de revisao" in l and u"R4" in l
               for l in linhas),
           str([l for l in linhas if u"skull" in l])[:300])
    with _Troca(_so_revisao_do_que_ficou=lambda rel, masks, log=None: None):
        mi = _cenario()
        rel_i, _li = _regras(mi)
    checar(u"ISCA: sem a limpeza da lista, o cranio removido ficaria em "
           u"revisao (a checagem de cima reprovaria)",
           "skull" in [x["nome"] for x in rel_i["revisao"]],
           str(rel_i["revisao"]))
    _f, meta = E.preparar_full(_cenario(), grade=_grade_regras())
    checar(u"no `meta` de preparar_full o cranio tambem nao esta em revisao",
           "skull" not in [x["nome"] for x in
                           meta.get("ilhas_em_revisao") or []]
           and "colon" in [x["nome"] for x in
                           meta.get("ilhas_em_revisao") or []],
           str(meta.get("ilhas_em_revisao")))

    base = tempfile.mkdtemp(prefix="radai_t_fulloar_")
    try:
        serie = _serie(base)

        def _cruas_com_ilha():
            cr = _cruas()
            am = np.zeros((Z, Y, X), np.int16)
            am[10:16, 30:36, 90:100] = 1
            am[17:18, 30:32, 90:92] = 1
            am[10:16, 100:106, 60:70] = 2
            cr["abdominal_muscles"] = E.MasksCruas(
                am, {1: "pectoralis_major_left", 2: "trapezius_left"})
            return cr
        sd, r, l1, _d = _rodar(base, serie, cruas=_cruas_com_ilha())
        rev_full = [x["nome"] for x in
                    (sd.meta_do_full or {}).get("ilhas_em_revisao") or []]
        checar(u"AUTO: o peitoral com ilha esta em revisao (ele esta no "
               u"FULL) -- controle",
               "pectoralis_major_left" in rev_full, str(rev_full))
        sd2, r2, l2, _d2 = _rodar(base, serie, cruas=_cruas_com_ilha(),
                                  modo="fast")
        rev_fast = [x["nome"] for x in
                    (sd2.meta_do_fast or {}).get("ilhas_em_revisao") or []]
        checar(u"FAST: o peitoral NAO esta em revisao -- ele nao vai ao "
               u"RadAI_STUDY_Fast", "pectoralis_major_left" not in rev_fast
               and not any(u"Musc_PecMaj" in n or u"pectoralis" in n
                           for n in r2.get("estruturas") or []),
               u"%s | %s" % (rev_fast, r2.get("estruturas")))
        velho = RO._ilhas_do_arquivo
        RO._ilhas_do_arquivo = lambda ilhas, nomes, log=None: list(ilhas)
        try:
            sd3, r3, l3, _d3 = _rodar(base, serie, cruas=_cruas_com_ilha(),
                                      modo="fast")
        finally:
            RO._ilhas_do_arquivo = velho
        rev_i = [x["nome"] for x in
                 (sd3.meta_do_fast or {}).get("ilhas_em_revisao") or []]
        checar(u"ISCA: sem a reducao ao arquivo, o FAST listaria o peitoral "
               u"(a checagem de cima reprovaria)",
               "pectoralis_major_left" in rev_i, str(rev_i))
    finally:
        shutil.rmtree(base, ignore_errors=True)


def teste_as_regras_de_gravacao_rodam_primeiro_e_nao_vao_ao_dicom():
    secao(u"as regras rodam primeiro, e nada delas vai ao RTSTRUCT")
    checar(u"as regras de gravacao sao o PRIMEIRO passo de ORDEM_DO_FULL",
           E.ORDEM_DO_FULL[0][0] == "regras", str(E.ORDEM_DO_FULL[:2]))
    base = tempfile.mkdtemp(prefix="radai_t_fulloar_")
    try:
        serie = _serie(base)
        extra = (("skull", (10, 20, 0, 5, 0, 5)),
                 ("liver", (0, 2, 44, 60, 44, 60)))
        cruas = _cruas(com_plugins=False, extra=extra)
        sd, r, linhas, dest = _rodar(base, serie, cruas=cruas)
        full = set(r["estruturas_full"])
        checar(u"a Skull no ar nao chega ao FULL (R3)",
               not any(n.startswith("Skull") for n in full), sorted(full))
        checar(u"o figado de 2 cortes na borda nao chega ao FULL (R1)",
               not any(n.startswith("Liver") for n in full), sorted(full))
        checar(u"  e o log diz as duas",
               any(u"R3" in l and u"skull" in l for l in linhas)
               and any(u"R1" in l and u"liver" in l for l in linhas),
               str([l for l in linhas if u"R1" in l or u"R3" in l])[:240])
        textos = []
        for alvo in (r["full"], r["oar"]):
            ds = pydicom.dcmread(alvo)
            textos.append(str(getattr(ds, "StructureSetDescription", "")))
            textos.extend(str(getattr(o, "ROIObservationDescription", ""))
                          for o in getattr(ds, "RTROIObservationsSequence",
                                           []))
        junto = u" ".join(textos)
        checar(u"nenhuma palavra das regras vai ao DICOM (FULL e OAR)",
               not any(p in junto for p in (u"R1 ", u"R2 ", u"R3 ", u"R4 ",
                                            u"regras de gravacao",
                                            u"fora do corpo",
                                            u"borda do campo",
                                            u"ilha mantida")),
               junto[:200])
        regs = sd.meta_do_full.get("regras_de_gravacao") or []
        checar(u"o `meta` do FULL leva as remocoes para o registro de casos",
               set(x["nome"] for x in regs) >= {"skull", "liver"},
               str(regs)[:200])
        alvo_ts = sd.totalsegmentator_cru(cruas)
        nomes_ts = [str(x.ROIName) for x in
                    pydicom.dcmread(alvo_ts).StructureSetROISequence]
        checar(u"o TS cru NAO recebe as regras: a Skull e o figado estao la",
               any(n.lower().startswith("skull") for n in nomes_ts)
               and any(n.lower().startswith("liver") for n in nomes_ts),
               str(nomes_ts)[:200])
        velha = E.ORDEM_DO_FULL
        try:
            E.ORDEM_DO_FULL = tuple(p for p in velha if p[0] != "regras")
            _sd, r_i, _l, _d = _rodar(base, serie, cruas=cruas)
        finally:
            E.ORDEM_DO_FULL = velha
        full_i = set(r_i["estruturas_full"])
        checar(u"ISCA: sem o passo na ordem, o figado da borda volta ao FULL "
               u"(a checagem de cima reprovaria)",
               any(n.startswith("Liver") for n in full_i), sorted(full_i))
    finally:
        shutil.rmtree(base, ignore_errors=True)


def teste_o_heart_ai_com_pericardio_e_um_volume_depois_do_recorte():
    secao(u"o Heart_ai com pericardio e um volume depois do recorte (HT2)")
    import radai_geom
    from scipy import ndimage
    g = radai_geom.Grade((3.0, 2.0, 2.0))
    forma = (20, 64, 64)

    def _fantoma():
        heart = np.zeros(forma, bool)
        heart[4:16, 8:30, 10:30] = True
        heart[4:16, 30:42, 16:24] = True
        heart[4:16, 42:54, 12:28] = True
        lung = np.zeros(forma, bool)
        lung[:, 34:39, :] = True
        return {"heart": heart, "pericardium": heart.copy(),
                "lung_left": lung}

    def _specs(sem_chave=False, com_peri=True):
        sp = {}
        for c in E.CONSTRUCOES:
            for k, v in (c.get("saidas") or {}).items():
                if k == "heart" or (com_peri and k == "pericardium"):
                    sp[k] = dict(v)
        if sem_chave:
            for _k in ("um_volume_com", "um_volume", "acabamento"):
                sp["heart"].pop(_k, None)
        return sp

    def _pecas(sem_chave=False, com_peri=True):
        m = _fantoma()
        if not com_peri:
            del m["pericardium"]
        log = []
        E._suavizar_construcoes(m, g, 1.5, _specs(sem_chave, com_peri), [],
                                [], log.append)
        return ndimage.label(np.asarray(m["heart"], bool))[1], log
    n1, log1 = _pecas()
    checar(u"com o pericardio na serie, o Heart_ai sai em UMA peca",
           n1 == 1, u"%d peca(s)" % n1)
    checar(u"  e o log diz o que caiu",
           any(u"um volume depois do recorte" in l for l in log1),
           [l for l in log1 if u"heart" in l][:2])
    n2, _l2 = _pecas(com_peri=False)
    checar(u"sem o pericardio tambem uma peca (v8.5: so o maior pedaco)",
           n2 == 1, u"%d peca(s)" % n2)
    n3, _l3 = _pecas(sem_chave=True)
    checar(u"ISCA: sem `um_volume_com`, `um_volume` e o acabamento sobram "
           u"duas pecas (a checagem de cima reprovaria)", n3 == 2,
           u"%d peca(s)" % n3)


def _coracao_com_a_cava_por_baixo():
    forma = (20, 64, 64)
    corpo = np.zeros(forma, bool)
    corpo[7:17, 10:41, 10:41] = True
    apice = np.zeros(forma, bool)
    apice[3:7, 12:25, 12:25] = True
    cava = np.zeros(forma, bool)
    cava[0:12, 34:41, 34:41] = True
    janela = np.zeros(forma, bool)
    janela[3:17] = True
    heart = corpo | apice | (cava & janela)
    return heart, cava


def _pericardio_sem_a_cava_por_baixo():
    forma = (20, 64, 64)
    peri = np.zeros(forma, bool)
    peri[7:17, 10:41, 10:41] = True
    peri[3:7, 12:25, 12:25] = True
    return peri


def teste_o_heart_ai_sem_a_cava_inferior_por_baixo():
    secao(u"o Heart_ai: no corte com dois contornos sai o que cruza a veia "
          u"cava inferior e fica o do apice; os 3 mm a mais valem na saida")
    import radai_geom
    from scipy import ndimage
    g = radai_geom.Grade((3.0, 2.0, 2.0))

    def _specs(sem_a_mais=False):
        sp = {}
        for c in E.CONSTRUCOES:
            for k, v in (c.get("saidas") or {}).items():
                if k in ("heart", "pericardium"):
                    sp[k] = dict(v)
        if sem_a_mais:
            sp["heart"]["suavizar_a_mais_mm"] = 0.0
        return sp

    def _rodar_coracao(suav=1.5, cava_na_receita=False, isca=False,
                       sem_a_mais=False):
        heart, cava = _coracao_com_a_cava_por_baixo()
        m = {"heart": heart, "pericardium": _pericardio_sem_a_cava_por_baixo()}
        sp = _specs(sem_a_mais)
        if cava_na_receita:
            sp["heart"]["cava_inferior"] = cava
        else:
            m["inferior_vena_cava"] = cava
        detalhe, log = [], []
        velho = E.sem_a_cava_nos_cortes
        try:
            if isca:
                E.sem_a_cava_nos_cortes = lambda mm, c, gg, **_k: (mm, 0)
            E._suavizar_construcoes(m, g, suav, sp, detalhe, [], log.append)
        finally:
            E.sem_a_cava_nos_cortes = velho
        return np.asarray(m["heart"], bool), cava, detalhe, log

    def _pedacos(h, z):
        return ndimage.label(h[z], np.ones((3, 3), bool))[1]
    for rot, kw in ((u"cava nas mascaras", {}),
                    (u"cava so na receita (o FAST)",
                     {"cava_na_receita": True})):
        h, cava, detalhe, log = _rodar_coracao(**kw)
        checar(u"[%s] nos cortes abaixo da juncao (3 a 6), nada da cava "
               u"inferior no Heart_ai" % rot, not (h[3:7] & cava[3:7]).any(),
               u"%d voxels" % int((h[3:7] & cava[3:7]).sum()))
        checar(u"[%s]   e um contorno por corte, o do apice" % rot,
               all(_pedacos(h, z) == 1 for z in range(3, 7))
               and all(h[z, 12:25, 12:25].any() for z in range(3, 7)),
               str([_pedacos(h, z) for z in range(3, 7)]))
        checar(u"[%s]   e o log diz quanto saiu" % rot,
               any(u"veia cava inferior saiu" in l for l in log))
    checar(u"acima da juncao a cava continua no coracao (o atrio direito)",
           (h[8:12] & cava[8:12]).any())
    hi, cava_i, _d, _l = _rodar_coracao(isca=True)
    checar(u"ISCA: sem a regra, o Heart_ai leva a cava por baixo, em dois "
           u"contornos", (hi[3:7] & cava_i[3:7]).any()
           and any(_pedacos(hi, z) >= 2 for z in range(3, 7)),
           str([_pedacos(hi, z) for z in range(3, 7)]))
    for suav in (1.5, 3.0):
        _h, _c, detalhe, _l = _rodar_coracao(suav=suav)
        mm = [d[1] for d in detalhe if d[0] == "heart"]
        esperado = E.suavizacao_de("heart", suav) + 3.0
        checar(u"com SUAVIZAR_MM %.1f, o Heart_ai e suavizado %.1f mm (o do "
               u"parenquima escalado + 3 mm fixos)" % (suav, esperado),
               mm and abs(mm[0] - esperado) < 1e-9, str(mm))
    h3, _c, _d, _l = _rodar_coracao()
    h0, _c0, _d0, _l0 = _rodar_coracao(sem_a_mais=True)

    def _canto(h):
        return int(h[9:15, 10:14, 10:14].sum())
    checar(u"os 3 mm a mais mudam a mascara de saida (o canto do bloco sai "
           u"mais arredondado que sem eles)", not np.array_equal(h3, h0)
           and _canto(h3) < _canto(h0),
           u"canto %d contra %d voxels" % (_canto(h3), _canto(h0)))
    base = tempfile.mkdtemp(prefix="radai_t_fulloar_")
    try:
        serie = _serie(base)
        sd, r, linhas, dest = _rodar(base, serie)
        mm_c = [d[1] for d in (sd.meta_do_full.get("suavizacao") or [])
                if d[0] == "heart"]
        checar(u"na cadeia do entregue, o Heart_ai sai suavizado com os 3 mm "
               u"a mais", mm_c and abs(mm_c[0] - (E.suavizacao_de(
                   "heart", 1.5) + 3.0)) < 1e-9, str(mm_c))
    finally:
        shutil.rmtree(base, ignore_errors=True)


def _v86_sem_a_cava(m, cava, modelo, grade):
    from scipy import ndimage
    import radai_geom
    eixo, _s = grade.eixo_sinal("inf")
    viz = np.ones((3, 3), bool)
    m = np.asarray(m, bool)
    cava = np.asarray(cava, bool)
    novo = m.copy()
    for k in range(m.shape[eixo]):
        fatia = np.take(novo, k, axis=eixo)
        cv = np.take(cava, k, axis=eixo)
        if not (fatia & cv).any():
            continue
        rot, n = ndimage.label(fatia, viz)
        if n < 2:
            continue
        tam = np.bincount(rot.ravel(), minlength=n + 1)
        comum = np.bincount(rot[fatia & cv].ravel(), minlength=n + 1)
        cruzam = dict((j, comum[j] / float(tam[j])) for j in range(1, n + 1)
                      if comum[j])
        if len(cruzam) == n:
            del cruzam[min(cruzam, key=cruzam.get)]
        idx = [slice(None)] * m.ndim
        idx[eixo] = k
        novo[tuple(idx)] = fatia & ~np.isin(rot, list(cruzam))
    if modelo is None:
        return novo
    cava = radai_geom.expandir(
        cava, dict((l, 1.0) for l in ("ant", "post", "esq", "dir")), grade)
    modelo = np.asarray(modelo, bool)
    for k in range(m.shape[eixo]):
        fatia = np.take(novo, k, axis=eixo)
        cv = np.take(cava, k, axis=eixo)
        if not (fatia & cv).any():
            continue
        mh = np.take(modelo, k, axis=eixo) & fatia
        if (ndimage.binary_dilation(cv, viz)
                & np.take(modelo, k, axis=eixo)).any():
            continue
        rot, _n = ndimage.label(fatia, viz)
        regiao = np.isin(rot, [j for j in np.unique(rot[fatia & cv]) if j])
        resto = regiao & ~(cv & ~mh)
        rot2, _n2 = ndimage.label(resto, viz)
        vivos = [j for j in np.unique(rot2[resto & mh]) if j]
        fica = np.isin(rot2, vivos) if vivos else np.zeros_like(resto)
        idx = [slice(None)] * m.ndim
        idx[eixo] = k
        novo[tuple(idx)] = fatia & ~(regiao & ~fica)
    return novo


def _tres_casos_da_cava():
    import radai_geom
    g = radai_geom.Grade((3.0, 1.0, 1.0))
    forma = (10, 120, 120)
    yy, xx = np.mgrid[0:120, 0:120]

    def disco(cy, cx, r):
        return (yy - cy) ** 2 + (xx - cx) ** 2 <= r * r

    peri = np.zeros(forma, bool)
    modelo = np.zeros(forma, bool)
    for z in range(2, 10):
        peri[z] = disco(55, 55, 30)
        modelo[z] = disco(50, 62, 8)
    peri[3] |= disco(22, 40, 5) | ((yy >= 22) & (yy <= 32)
                                   & (xx >= 37) & (xx <= 43))
    peri[1] = disco(50, 80, 12)
    modelo[1] = disco(50, 82, 5)
    lumen = np.zeros(forma, bool)
    lumen[0:4] = disco(60, 28, 6)
    cava = radai_geom.expandir(lumen, 1.0, g)
    frag = np.zeros(forma, bool)
    frag[2] = disco(22, 40, 2)
    eso = np.zeros(forma, bool)
    eso[:] = disco(95, 55, 5)
    der = np.zeros(forma, bool)
    der[5:8, 80:100, 45:66] = True
    heart = peri | modelo | cava | frag
    masks = {"inferior_vena_cava": cava, "pericardium": peri,
             "heart_model": modelo, "esophagus": eso,
             "pericardial_effusion": der}
    return g, heart, masks, frag


def _checagens_dos_tres_casos(novo, heart, masks, frag):
    prot = masks["pericardium"] | masks["heart_model"]
    cava, eso = masks["inferior_vena_cava"], masks["esophagus"]
    der = masks["pericardial_effusion"]
    return {
        u"nenhum pixel do pericardio nem do coracao do modelo sai":
            not (heart & prot & ~novo).any(),
        u"corte so de cava (0): sai vazio": not novo[0].any(),
        u"dois contornos, apice e cava separados (1): a cava sai e o apice "
        u"fica": not (novo[1] & cava[1] & ~prot[1]).any()
            and not (prot[1] & ~novo[1]).any(),
        u"o saco com a cava encostada e um ponto solto (2): o saco fica "
        u"inteiro e o ponto sai": not (prot[2] & ~novo[2]).any()
            and not (novo[2] & frag[2]).any(),
        u"a cava fundida ao saco (3): sem edentacao, so sai a cava fora do "
        u"pericardio": not (prot[3] & ~novo[3]).any()
            and not (novo[3] & cava[3] & ~prot[3]).any(),
        u"o esofago sai (o derrame o trazia de volta)":
            not (novo & eso).any(),
        u"  e o derrame fora do esofago fica": not (der & ~eso & ~novo).any(),
    }


def teste_o_heart_ai_os_tres_casos_da_cava_e_sem_o_esofago():
    secao(u"o Heart_ai: nunca perde pixel do pericardio nem do Heart_Model; a "
          u"cava sai so onde esta separada do coracao; nenhum corte descarta o "
          u"contorno com pericardio; o esofago sai")
    from scipy import ndimage
    g, heart, masks, frag = _tres_casos_da_cava()
    log = []
    novo, _desc, info = E._acabamento_do_coracao("heart", heart, dict(masks),
                                                 g, log=log.append)
    novo = np.asarray(novo, bool)
    for rot, ok in sorted(_checagens_dos_tres_casos(novo, heart, masks,
                                                   frag).items()):
        checar(u"[acabamento] %s" % rot, ok)
    checar(u"[acabamento]   um volume so",
           ndimage.label(novo)[1] == 1, str(ndimage.label(novo)[1]))
    checar(u"[acabamento]   a medida diz quanto da cava saiu e o corte que "
           u"ficou vazio", info.get("cava_inferior_tirada_cm3", 0) > 0
           and info.get("cortes_so_de_cava") == 1, str(info))
    checar(u"[acabamento]   e o log diz a cava e o esofago",
           any(u"veia cava inferior saiu" in l for l in log)
           and any(u"esofago" in l for l in log), str(log)[:300])
    velho_c, velho_f = E.sem_a_cava_nos_cortes, E.FORA_DO_PERICARDIO
    try:
        E.sem_a_cava_nos_cortes = (
            lambda mm, c, gg, protegido=None, modelo=None:
            (_v86_sem_a_cava(mm, c, modelo, gg), 0))
        E.FORA_DO_PERICARDIO = ()
        vi, _d, _i = E._acabamento_do_coracao("heart", heart, dict(masks), g)
    finally:
        E.sem_a_cava_nos_cortes, E.FORA_DO_PERICARDIO = velho_c, velho_f
    isca = _checagens_dos_tres_casos(np.asarray(vi, bool), heart, masks, frag)
    checar(u"ISCA: com as regras da v8.6, o saco sai e fica o ponto, a cava "
           u"fundida morde o pericardio e o esofago fica (as checagens de "
           u"cima reprovariam)",
           not isca[u"nenhum pixel do pericardio nem do coracao do modelo "
                    u"sai"]
           and not isca[u"o saco com a cava encostada e um ponto solto (2): "
                        u"o saco fica inteiro e o ponto sai"]
           and not isca[u"a cava fundida ao saco (3): sem edentacao, so sai "
                        u"a cava fora do pericardio"]
           and not isca[u"o esofago sai (o derrame o trazia de volta)"],
           str(dict((k[:24], v) for k, v in isca.items())))
    h1, _t = E.sem_a_cava_nos_cortes(heart, masks["inferior_vena_cava"], g)
    checar(u"sem o protegido (sem pericardio nem coracao do modelo), so a "
           u"regra dos dois contornos vale: o contorno unico com a cava fica",
           bool((h1[3] & masks["inferior_vena_cava"][3]).any()))

    def _specs():
        sp = {}
        for c in E.CONSTRUCOES:
            for k, v in (c.get("saidas") or {}).items():
                if k in ("heart", "pericardium"):
                    sp[k] = dict(v)
        return sp

    def _rodar(na_receita=False, isca=False):
        _g, heart, masks, _frag = _tres_casos_da_cava()
        m = dict(masks)
        m["heart"] = heart
        sp = _specs()
        if na_receita:
            sp["heart"]["cava_inferior"] = m.pop("inferior_vena_cava")
            sp["heart"]["coracao_do_modelo"] = m.pop("heart_model")
        log = []
        velho, velho_f = E.sem_a_cava_nos_cortes, E.FORA_DO_PERICARDIO
        try:
            if isca:
                E.sem_a_cava_nos_cortes = (
                    lambda mm, c, gg, protegido=None, modelo=None:
                    (_v86_sem_a_cava(mm, c, modelo, gg), 0))
                E.FORA_DO_PERICARDIO = ()
            E._suavizar_construcoes(m, g, 1.5, sp, [], [], log.append)
        finally:
            E.sem_a_cava_nos_cortes, E.FORA_DO_PERICARDIO = velho, velho_f
        return np.asarray(m["heart"], bool), log

    nucleo = ndimage.binary_erosion(masks["pericardium"][3], iterations=6)

    def _cadeia(h):
        return {
            u"o pericardio do corte 3 (a cava fundida) sem edentacao":
                not (nucleo & ~h[3]).any(),
            u"nada do esofago": not (h & masks["esophagus"]).any(),
        }
    for rot, kw in ((u"cava e coracao do modelo nas mascaras", {}),
                    (u"os dois so na receita (o FAST)", {"na_receita": True})):
        h, log = _rodar(**kw)
        for nome, ok in sorted(_cadeia(h).items()):
            checar(u"[%s] suavizado: %s" % (rot, nome), ok)
        checar(u"[%s]   e o log diz quanto da cava saiu" % rot,
               any(u"veia cava inferior saiu" in l for l in log),
               [l for l in log if u"cava" in l][:2])
    hi, _l = _rodar(isca=True)
    isca_c = _cadeia(hi)
    checar(u"ISCA: com a regra da v8.6 na cadeia, a cava fundida morde o "
           u"pericardio e o esofago fica", not any(isca_c.values()),
           str(isca_c))
    _g, heart, masks2, _frag = _tres_casos_da_cava()
    m = {"heart": masks2["heart_model"].copy(),
         "inferior_vena_cava": masks2["inferior_vena_cava"],
         "pericardium": masks2["pericardium"]}
    _fora, meta = E.preparar_full(m, grade=g)
    spec = (meta.get("construcoes") or {}).get("heart") or {}
    checar(u"o preparo do FULL guarda na receita do Heart_ai a cava e o "
           u"coracao do modelo (o FAST os acha la)",
           spec.get("cava_inferior") is not None
           and spec.get("coracao_do_modelo") is not None, sorted(spec))


def teste_a_tireoide_e_delgada():
    secao(u"v8.7: a tireoide sem suavizacao, como os constritores (estruturas "
          u"delgadas)")
    import radai_geom
    checar(u"a tireoide e os tres constritores estao nas delgadas",
           {"thyroid_gland", "pharyngeal_constrictor_superior",
            "pharyngeal_constrictor_middle",
            "pharyngeal_constrictor_inferior"} <= set(E.ESTRUTURAS_DELGADAS))
    checar(u"  e a suavizacao da tireoide e zero com qualquer SUAVIZAR_MM",
           all(E.suavizacao_de("thyroid_gland", s) == 0.0
               for s in (1.5, 3.0, 6.0)))
    g = radai_geom.Grade((3.0, 1.0, 1.0))
    tire = np.zeros((10, 60, 60), bool)
    tire[2:8, 20:40, 10:50] = True
    tire[2:8, 26:40, 25:35] = False

    def _suaviza():
        m = {"thyroid_gland": tire.copy()}
        E._suavizar_individuais(m, ["thyroid_gland"], g, 1.5, [], [])
        return np.asarray(m["thyroid_gland"], bool)
    checar(u"a tireoide sai como o modelo a deu, istmo e bordas inteiros",
           np.array_equal(_suaviza(), tire))
    velho = E.SUAVIZACAO.get("thyroid_gland")
    E.SUAVIZACAO["thyroid_gland"] = 2.5
    try:
        mi = _suaviza()
    finally:
        E.SUAVIZACAO["thyroid_gland"] = velho
    checar(u"ISCA: com os 2,5 mm do parenquima, a tireoide mudaria (a "
           u"checagem de cima reprovaria)", not np.array_equal(mi, tire))


def _cervicais_com_clavicula():
    import radai_hnlnl as HN
    ivb_l = np.zeros((Z, Y, X), bool)
    ivb_l[24:29, 38:48, 72:84] = True
    ivb_r = np.zeros((Z, Y, X), bool)
    ivb_r[24:29, 38:48, 40:52] = True
    v_l = np.zeros((Z, Y, X), bool)
    v_l[24:29, 40:45, 85:90] = True
    niv = HN.NiveisDaSerie({"Lvl_IVb_L": ivb_l, "Lvl_IVb_R": ivb_r,
                            "Lvl_V_L": v_l,
                            HN.NOME_DA_UNIAO: ivb_l | ivb_r | v_l})
    niv.extensao = {"ok": True, "desce_mm": 0.0,
                    "motivo": u"desce 0 mm abaixo das claviculas"}
    return niv, ivb_l, ivb_r, v_l


def teste_o_ivb_sem_a_clavicula_antes_da_uniao():
    secao(u"v8.7: antes da uniao, o Lvl_IVb sai sem a clavicula do mesmo lado; "
          u"os outros niveis ficam como o modelo deu")
    import radai_hnlnl as HN
    base = tempfile.mkdtemp(prefix="radai_t_fulloar_")
    try:
        serie = _serie(base)
        cruas = _cruas(com_plugins=False, extra=(
            ("clavicula_right", (27, 29, 40, 45, 38, 58)),))

        def _vez():
            niv, ivb_l, ivb_r, v_l = _cervicais_com_clavicula()
            sd, r, linhas, _d = _rodar(base, serie, cruas=cruas,
                                       cervicais=niv)
            return sd.meta_do_full["mascaras"], linhas, ivb_l, ivb_r, v_l
        mf, linhas, ivb_l, ivb_r, v_l = _vez()
        cl = np.asarray(mf["clavicula_left"], bool)
        cr = np.asarray(mf["clavicula_right"], bool)
        un = np.asarray(mf[HN.NOME_DA_UNIAO], bool)

        def _sem(mf, un):
            return {
                u"o Lvl_IVb_L sem a clavicula esquerda":
                    not (np.asarray(mf["Lvl_IVb_L"], bool) & cl).any(),
                u"o Lvl_IVb_R sem a clavicula direita":
                    not (np.asarray(mf["Lvl_IVb_R"], bool) & cr).any(),
                u"a uniao sem a clavicula que o IVb tinha":
                    not (un & ((ivb_l & cl) | (ivb_r & cr))).any(),
            }
        for rot, ok in sorted(_sem(mf, un).items()):
            checar(rot, ok)
        checar(u"  e o resto do IVb fica",
               bool(np.asarray(mf["Lvl_IVb_L"], bool).any())
               and not (ivb_l & ~cl & ~np.asarray(mf["Lvl_IVb_L"],
                                                   bool)).any())
        checar(u"o Lvl_V original continua com a clavicula, mas a uniao "
               u"final retira toda a interseccao com ela",
               bool((np.asarray(mf["Lvl_V_L"], bool) & cl).any())
               and not (un & v_l & cl).any())
        checar(u"o log diz quanto saiu de cada lado",
               any(u"clavicula" in l and u"Lvl_IVb_L" in l for l in linhas)
               and any(u"clavicula" in l and u"Lvl_IVb_R" in l
                       for l in linhas),
               [l for l in linhas if u"clavicula" in l][:4])
        velho = HN.CLAVICULA_DO_IVB
        HN.CLAVICULA_DO_IVB = {}
        try:
            mfi, _l, _a, _b, _c = _vez()
        finally:
            HN.CLAVICULA_DO_IVB = velho
        isca = _sem(mfi, np.asarray(mfi[HN.NOME_DA_UNIAO], bool))
        checar(u"ISCA: sem o recorte do IVb, ele leva a clavicula, mas a "
               u"uniao continua protegida pelo acabamento final",
               not isca[u"o Lvl_IVb_L sem a clavicula esquerda"]
               and not isca[u"o Lvl_IVb_R sem a clavicula direita"]
               and isca[u"a uniao sem a clavicula que o IVb tinha"],
               str(isca))
        niv_m, _a, _b, _c = _cervicais_com_clavicula()
        niv_m.extensao = {"ok": False, "desce_mm": 45.0,
                          "motivo": u"a uniao desce 45 mm (bateria)"}
        _sd, r_m, _l, _dd = _rodar(base, serie, cruas=cruas, cervicais=niv_m)
        motivo = (r_m.get("oar_fora_por_regiao") or {}).get(
            HN.NOME_DA_UNIAO, u"")
        checar(u"a uniao que nao vai ao entregue leva o motivo ao resultado "
               u"que o registro de casos le (o estudo marcado pela regua)",
               u"regua" in motivo and "LNL_UNION_ai" not in r_m["estruturas"],
               motivo)
    finally:
        shutil.rmtree(base, ignore_errors=True)


_CAIXA_DO_ENCEFALO = (12, 28, 18, 40, 44, 84)


def teste_os_ventriculos_e_a_linha_media_dentro_do_brain():
    secao(u"v8.7: os ventriculos e a linha media do modelo do encefalo ficam "
          u"dentro do Brain_ai (recortados por ele, nas mascaras finais)")
    checar(u"CONTIDAS_EM declara os dois dentro do encefalo",
           E.CONTIDAS_EM.get("brain_ventricles") == "brain"
           and E.CONTIDAS_EM.get("brain_midline") == "brain")
    base = tempfile.mkdtemp(prefix="radai_t_fulloar_")
    try:
        serie = _serie(base)
        ven = np.zeros((Z, Y, X), bool)
        ven[20:24, 26:44, 60:70] = True
        lin = np.zeros((Z, Y, X), bool)
        lin[14:28, 16:42, 42:47] = True
        extras = {"orgaos": {"brain_ventricles": ven, "brain_midline": lin},
                  "alvos": {}, "observacoes": {},
                  "origem": {"brain_ventricles": "cranio_ct",
                             "brain_midline": "cranio_ct"}}
        cruas = _cruas(com_plugins=False,
                       extra=(("brain", _CAIXA_DO_ENCEFALO),))

        def _vez():
            sd, r, linhas, _d = _rodar(base, serie, cruas=cruas,
                                       extras=extras)
            mf = sd.meta_do_full["mascaras"]
            b = np.asarray(mf["brain"], bool)
            return {
                u"os ventriculos dentro do Brain_ai final":
                    not (np.asarray(mf["brain_ventricles"], bool) & ~b).any(),
                u"a linha media dentro do Brain_ai final":
                    not (np.asarray(mf["brain_midline"], bool) & ~b).any(),
            }, linhas
        ok, linhas = _vez()
        for rot, v in sorted(ok.items()):
            checar(rot, v)
        checar(u"  e o log diz o recorte",
               any(u"recortado para dentro de `brain`" in l for l in linhas))
        velho = dict(E.CONTIDAS_EM)
        for k in ("brain_ventricles", "brain_midline"):
            E.CONTIDAS_EM.pop(k, None)
        try:
            isca, _l = _vez()
        finally:
            E.CONTIDAS_EM.clear()
            E.CONTIDAS_EM.update(velho)
        checar(u"ISCA: sem a contencao, os dois passam do encefalo (as "
               u"checagens de cima reprovariam)", not any(isca.values()),
               str(isca))
        real = E.aplicar_contencao
        chamadas = []

        def _so_antes_da_suavizacao(masks, grade=None, log=None):
            chamadas.append(1)
            if len(chamadas) % 2 == 1:
                return real(masks, grade, log=log)
            return []
        E.aplicar_contencao = _so_antes_da_suavizacao
        try:
            isca2, _l2 = _vez()
        finally:
            E.aplicar_contencao = real
        checar(u"ISCA: so com a contencao antes da suavizacao, a linha media "
               u"passa do encefalo suavizado (por isso ela roda de novo nas "
               u"mascaras finais)", not all(isca2.values()), str(isca2))
    finally:
        shutil.rmtree(base, ignore_errors=True)


def _rodar_na_modalidade(base, serie, cruas, modalidade):
    import SimpleITK as sitk
    vol = sitk.GetArrayFromImage(E.load_sitk(serie))
    linhas = []
    dest = os.path.join(base, "saida_%d" % len(os.listdir(base)))
    os.makedirs(dest)
    sd = RO.Saida(E, serie, dest, "RS_RadAI_20260924_1a2b3c4d.dcm",
                  tasks=["total_v3"], versao="bateria", suavizar_mm=1.5,
                  log=lambda m: linhas.append(str(m)), modalidade=modalidade)
    sd.devolver_mascaras = True
    return sd.full_e_oar(cruas, volume_hu=vol), linhas


def teste_o_brain_da_rm_fica_so_no_full():
    secao(u"v8.7: o Brain_ai da RM fica so no FULL; o da TC vai ao entregue")
    base = tempfile.mkdtemp(prefix="radai_t_fulloar_")
    try:
        serie = _serie(base)
        cruas = _cruas(com_plugins=False,
                       extra=(("brain", _CAIXA_DO_ENCEFALO),))
        r_tc, _l = _rodar_na_modalidade(base, serie, cruas, "CT")
        checar(u"na TC o Brain_ai vai ao entregue",
               "Brain_ai" in r_tc["estruturas"], str(r_tc["estruturas"]))
        r_rm, l_rm = _rodar_na_modalidade(base, serie, cruas, "MR")
        checar(u"na RM o Brain_ai fica no FULL e nao vai ao entregue",
               "Brain_ai" in r_rm["estruturas_full"]
               and "Brain_ai" not in r_rm["estruturas"],
               str(r_rm["estruturas"]))
        checar(u"  e o motivo vai ao resultado e ao log",
               "brain" in (r_rm.get("oar_fora_por_regiao") or {})
               and any(u"Brain_ai" in l and u"RM" in l for l in l_rm),
               str(r_rm.get("oar_fora_por_regiao")))
        velho = E.FORA_DO_OAR_NA_MODALIDADE
        E.FORA_DO_OAR_NA_MODALIDADE = {}
        try:
            r_i, _li = _rodar_na_modalidade(base, serie, cruas, "MR")
        finally:
            E.FORA_DO_OAR_NA_MODALIDADE = velho
        checar(u"ISCA: sem a regra, o Brain_ai da RM iria ao entregue",
               "Brain_ai" in r_i["estruturas"])
        import radai_batch as L

        def _previa(mod):
            lista, _t = L.estruturas_do_oar_possiveis("auto", [],
                                                      modalidade=mod)
            return set(e["chave"] for e in lista)
        checar(u"a previa do entregue tambem: o encefalo na TC, e nao na RM",
               "brain" in _previa("CT") and "brain" not in _previa("MR"))
    finally:
        shutil.rmtree(base, ignore_errors=True)


def teste_os_pulmoes_somados_no_entregue():
    secao(u"v8.7: Lungs_ai = Lung_L + Lung_R; na cabeca e pescoco sem torax o "
          u"entregue leva o Lungs_ai no lugar dos dois")
    import radai_geom
    import radai_topography as TOPO
    base = tempfile.mkdtemp(prefix="radai_t_fulloar_")
    try:
        serie = _serie(base)
        sd, r, linhas, _d = _rodar(base, serie, cruas=_cruas(
            com_plugins=False))
        mf = sd.meta_do_full["mascaras"]
        soma = (np.asarray(mf["lung_left"], bool)
                | np.asarray(mf["lung_right"], bool))
        checar(u"o Lungs_ai do FULL e exatamente a soma dos pulmoes finais",
               "lungs" in mf and np.array_equal(np.asarray(mf["lungs"], bool),
                                                soma))
        checar(u"  e vai ao FULL e ao entregue",
               "Lungs_ai" in r["estruturas_full"]
               and "Lungs_ai" in r["estruturas"], str(r["estruturas"]))
        checar(u"  sem alarme de sobreposicao com os pulmoes (ele os contem)",
               not any(u"SOBREPOSICAO" in l and u"Lungs" in l
                       for l in linhas))
    finally:
        shutil.rmtree(base, ignore_errors=True)
    g = radai_geom.Grade((3.0, 2.0, 2.0))
    um = np.zeros((10, 20, 20), bool)
    um[2:5, 2:8, 2:8] = True
    masks = {"lung_left": um, "lung_right": um, "lungs": um}
    velho = TOPO.anatomia_da_base

    def _com(regioes):
        TOPO.anatomia_da_base = lambda *a, **k: {
            "regioes": tuple(regioes),
            "laudo": [u"pescoco: sim (bateria)", u"torax: (bateria)"]}
        try:
            return E.fora_do_oar_por_regiao(dict(masks), g)
        finally:
            TOPO.anatomia_da_base = velho
    so_cp = _com(("cabeca_pescoco",))
    checar(u"cabeca e pescoco sem torax: Lung_L e Lung_R ficam so no FULL, o "
           u"Lungs_ai vai", {"lung_left", "lung_right"} <= set(so_cp)
           and "lungs" not in so_cp, str(sorted(so_cp)))
    com_t = _com(("cabeca_pescoco", "torax"))
    checar(u"  com o torax, os dois pulmoes e o Lungs_ai vao",
           not ({"lung_left", "lung_right", "lungs"} & set(com_t)),
           str(sorted(com_t)))
    velho_l = E.FORA_DO_OAR_NO_PESCOCO_SEM_TORAX
    E.FORA_DO_OAR_NO_PESCOCO_SEM_TORAX = tuple(
        k for k in velho_l if not k.startswith("lung_"))
    try:
        isca = _com(("cabeca_pescoco",))
    finally:
        E.FORA_DO_OAR_NO_PESCOCO_SEM_TORAX = velho_l
    checar(u"ISCA: sem a regra, os dois pulmoes iriam junto com o Lungs_ai",
           "lung_left" not in isca)


def _cruas_de_cabeca_e_pescoco():
    cruas = _cruas(com_plugins=False)

    def _mapa(itens):
        lab = np.zeros((Z, Y, X), np.int16)
        idx = {}
        for i, (nome, m) in enumerate(itens, start=1):
            lab[m] = i
            idx[i] = nome
        return E.MasksCruas(lab, idx)

    def cx(z0, z1, y0, y1, x0, x1):
        a = np.zeros((Z, Y, X), bool)
        a[z0:z1, y0:y1, x0:x1] = True
        return a
    tire = cx(12, 20, 88, 98, 56, 72) & ~cx(12, 20, 90, 98, 58, 70)
    crico = cx(8, 13, 90, 100, 58, 70) & ~cx(8, 13, 92, 98, 60, 68)
    cruas["headneck_bones_vessels"] = _mapa((
        ("hyoid", cx(20, 21, 86, 92, 58, 70)),
        ("thyroid_cartilage", tire), ("cricoid_cartilage", crico),
        ("larynx_air", cx(8, 20, 92, 96, 62, 66))))
    cruas["head_glands_cavities"] = _mapa((
        ("hypopharynx", cx(12, 21, 98, 104, 58, 70)),))
    mand = np.zeros((Z, Y, X), bool)
    for x0, x1 in ((81, 86), (42, 47)):
        mand[10:13, 22:36, x0:x1] = True
        mand[13:21, 30:40, x0:x1] = True
        mand[21:25, 30:33, x0:x1] = True
        mand[21:27, 36:40, x0:x1] = True
    mand[10:13, 22:25, 42:86] = True
    cruas["craniofacial_structures"] = _mapa((
        ("mandible", mand), ("teeth_lower", cx(13, 15, 23, 26, 82, 85))))
    return cruas


def teste_as_estruturas_novas_chegam_ao_full_e_ao_oar():
    secao(u"v8.7: Larynx_ai, TMJ_L_ai, TMJ_R_ai, Lungs_ai e a mandibula cheia "
          u"no FULL e no entregue, com ate 16 caracteres e sem alarme")
    novas = (u"Larynx_ai", u"TMJ_L_ai", u"TMJ_R_ai", u"Lungs_ai",
             u"Bone_Mandible_ai")
    base = tempfile.mkdtemp(prefix="radai_t_fulloar_")
    try:
        serie = _serie(base)
        sd, r, linhas, _d = _rodar(base, serie,
                                   cruas=_cruas_de_cabeca_e_pescoco())
        for n in novas:
            checar(u"%s no FULL e no entregue (%d caracteres)" % (n, len(n)),
                   n in r["estruturas_full"] and n in r["estruturas"]
                   and len(n) <= 16, str(sorted(r["estruturas"]))[:240])
        mf = sd.meta_do_full["mascaras"]
        lar = np.asarray(mf.get("larynx"), bool)
        zs = np.flatnonzero(lar.any(axis=(1, 2))) if lar.ndim == 3 else []
        checar(u"a laringe da cadeia vai do ultimo corte da cricoide (8) ao "
               u"corte logo abaixo do hioide (19)",
               len(zs) and int(zs.min()) == 8 and int(zs.max()) == 19,
               str((int(zs.min()), int(zs.max())) if len(zs) else None))
        atm = np.asarray(mf.get("tmj_left"), bool)
        checar(u"a TMJ_L da cadeia nao leva o coronoide",
               atm.ndim == 3 and atm.any()
               and not atm[21:25, 30:33, 81:86].any())
        checar(u"o log da serie diz por onde passou o plano medio da ATM "
               u"(aqui, sem cranio, encefalo, C1 nem C2: a caixa da "
               u"mandibula)", any(u"TMJ:" in l and u"caixa da mandibula" in l
                                  for l in linhas),
               [l for l in linhas if u"TMJ" in l][:3])
        checar(u"a mandibula cheia leva os dentes inferiores",
               bool(np.asarray(mf["mandible"], bool)[13:15, 23:26,
                                                     82:85].all()))
        checar(u"nenhum alarme de sobreposicao no entregue com as estruturas "
               u"novas (o que elas contem esta declarado)",
               not any(l.startswith(u"OAR: SOBREPOSICAO") and any(
                   n[:-3] in l for n in novas) for l in linhas),
               [l for l in linhas if u"SOBREPOSICAO" in l][:4])
        velho = RS.PERMITIDOS_NO_OAR
        RS.PERMITIDOS_NO_OAR = frozenset(
            velho - {"larynx", "tmj_left", "tmj_right", "lungs"})
        try:
            _sd, ri, _l, _dd = _rodar(base, serie,
                                      cruas=_cruas_de_cabeca_e_pescoco())
        finally:
            RS.PERMITIDOS_NO_OAR = velho
        checar(u"ISCA: fora da lista de permitidos, elas ficariam so no FULL",
               u"Larynx_ai" not in ri["estruturas"]
               and u"Larynx_ai" in ri["estruturas_full"])
    finally:
        shutil.rmtree(base, ignore_errors=True)



_PELVE = (
    ("sacrum", (6, 27, 60, 72, 58, 70)),
    ("hip_left", (6, 27, 55, 75, 70, 84)),
    ("hip_right", (6, 27, 55, 75, 44, 58)),
    ("colon", (0, 15, 50, 58, 60, 68)),
    ("gluteus_maximus_left", (4, 22, 78, 90, 75, 92)),
    ("gluteus_maximus_right", (4, 22, 78, 90, 36, 53)),
    ("gluteus_medius_left", (8, 24, 38, 50, 86, 96)),
    ("iliopsoas_left", (10, 28, 46, 54, 74, 84)),
    ("iliopsoas_right", (10, 28, 46, 54, 44, 54)),
)


def _marcos_com_piso_da_pelve(piso):
    return tuple((c, n, (piso if c == "pelve" else p))
                 for c, n, p in E.MARCOS_DE_REGIAO)


def teste_os_compostos_da_pelve_so_vao_ao_oar_com_a_pelve():
    secao(u"os compostos da pelve so vao ao OAR com a pelve no campo")
    ponta = (("iliopsoas_left", (0, 6, 90, 96, 50, 58)),
             ("iliopsoas_right", (0, 6, 90, 96, 30, 38)),
             ("hip_left", (0, 6, 98, 104, 50, 58)),
             ("hip_right", (0, 6, 98, 104, 30, 38)),
             ("sacrum", (0, 6, 98, 104, 41, 47)))
    base = tempfile.mkdtemp(prefix="radai_t_fulloar_")
    try:
        serie = _serie(base)
        sd, r, linhas, _d = _rodar(base, serie, cruas=_cruas(extra=ponta))
        full, oar = set(r["estruturas_full"]), set(r["estruturas"])
        for n in ("Muscles_ai", "Bone_Pelvic_ai", "IliacCrest_L_ai",
                  "IliacCrest_R_ai"):
            checar(u"torax sem pelve: `%s` no FULL e FORA do OAR" % n,
                   n in full and n not in oar,
                   u"FULL: %s | OAR: %s" % (n in full, n in oar))
        ditas = [l for l in linhas if l.startswith(u"OAR desta serie SEM")
                 and u"pelve" in l]
        checar(u"  e o log diz o osso da pelve, com o motivo da regiao",
               any(u"Bone_Pelvic_ai" in l for l in ditas)
               and all(u"pelve: nao" in l for l in ditas), str(ditas)[:400])
        checar(u"  e o resultado o declara (`oar_fora_por_regiao`)",
               set(r.get("oar_fora_por_regiao") or {})
               == {"bone_pelvic", "iliac_crest_left", "iliac_crest_right"},
               str(r.get("oar_fora_por_regiao")))
        sdf, rf, lf, _df = _rodar(base, serie, cruas=_cruas(extra=ponta),
                                  modo="fast")
        checar(u"FAST sem pelve: nem Muscles_ai nem Bone_Pelvic_ai no "
               u"OAR_Fast", not ({"Muscles_ai", "Bone_Pelvic_ai"}
                                 & set(rf["estruturas"])),
               str(sorted(rf["estruturas"])))
        checar(u"  e o log do FAST diz o do Bone_Pelvic_ai",
               any(l.startswith(u"OAR_Fast desta serie SEM")
                   and u"Bone_Pelvic_ai" in l for l in lf),
               str([l for l in lf if u"SEM" in l])[:300])
        velho_m = E.MARCOS_DE_REGIAO
        E.MARCOS_DE_REGIAO = _marcos_com_piso_da_pelve(5.0)
        try:
            sd2, r2, l2, _d2 = _rodar(base, serie, cruas=_cruas(extra=ponta))
            sdf2, rf2, lf2, _df2 = _rodar(base, serie,
                                          cruas=_cruas(extra=ponta),
                                          modo="fast")
        finally:
            E.MARCOS_DE_REGIAO = velho_m
        checar(u"com a pelve identificada (piso do fantoma), o Bone_Pelvic_ai "
               u"vai ao OAR e o Muscles_ai nao",
               "Bone_Pelvic_ai" in set(r2["estruturas"])
               and "Muscles_ai" not in set(r2["estruturas"]),
               str(sorted(r2["estruturas"])))
        checar(u"  e o Bone_Pelvic_ai ao OAR_Fast (o Muscles_ai nunca)",
               "Bone_Pelvic_ai" in set(rf2["estruturas"])
               and "Muscles_ai" not in set(rf2["estruturas"]),
               str(sorted(rf2["estruturas"])))
        velho_f = E.fora_do_oar_por_regiao
        E.fora_do_oar_por_regiao = lambda masks, grade: {}
        try:
            sd3, r3, l3, _d3 = _rodar(base, serie, cruas=_cruas(extra=ponta))
        finally:
            E.fora_do_oar_por_regiao = velho_f
        checar(u"ISCA: sem o portao, o Bone_Pelvic_ai entra no OAR do torax "
               u"(a checagem de cima reprovaria)",
               "Bone_Pelvic_ai" in set(r3["estruturas"]),
               str(sorted(r3["estruturas"])))
        import radai_geom
        mc = _cruas_pelve()["total_v3"]
        tem, laudo = E.regioes_no_campo(
            dict((k, np.asarray(mc[k], bool)) for k in mc),
            grade=radai_geom.Grade((3.0, 2.0, 2.0)))
        checar(u"o fantoma de pelve E uma pelve pela medida (%s)"
               % [l for l in laudo if l.startswith(u"pelve")],
               "pelve" in tem)
    finally:
        shutil.rmtree(base, ignore_errors=True)


def _cruas_pelve(sem=()):
    lab = np.zeros((Z, Y, X), np.int16)
    idx = {}
    i = 0
    for nome, (z0, z1, y0, y1, x0, x1) in _PELVE:
        if nome in sem:
            continue
        i += 1
        lab[z0:z1, y0:y1, x0:x1] = i
        idx[i] = nome
    return {"total_v3": E.MasksCruas(lab, idx)}


def _geracao(caminho):
    ds = pydicom.dcmread(caminho)
    return dict((str(r.ROIName), str(getattr(r, "ROIGenerationDescription",
                                             "")))
                for r in ds.StructureSetROISequence)


def teste_o_full_leva_tudo():
    secao(u"v8.3: o FULL leva tudo (menos a `head`)")
    import radai_geom
    cruas = _cruas()
    cf = np.zeros((Z, Y, X), np.int16)
    cf[2:6, 40:60, 40:60] = 1
    cf[2:4, 60:64, 50:54] = 2
    cruas["craniofacial_structures"] = E.MasksCruas(
        cf, {1: "head", 2: "mandible"})
    am = np.zeros((Z, Y, X), np.int16)
    am[10:16, 30:36, 90:100] = 1
    am[10:16, 100:106, 60:70] = 2
    am[20:26, 90:96, 40:50] = 3
    cruas["abdominal_muscles"] = E.MasksCruas(
        am, {1: "pectoralis_major_left", 2: "trapezius_left",
             3: "psoas_major_left"})
    vocab = set(RO.vocabulario_do_full(cruas, E.TS_MAP))
    for n in ("mediastinum", "thoracic_cavity", "abdominal_cavity",
              "trapezius_left", "psoas_major_left", "pectoralis_major_left",
              "mandible"):
        checar(u"o FULL leva `%s`" % n, n in vocab, str(sorted(vocab))[:200])
    checar(u"e NAO leva a `head` (cabeca solida = contorno externo)",
           "head" not in vocab)
    checar(u"`ROTULOS_FORA_DO_FULL` so tem a `head` da craniofacial",
           RS.ROTULOS_FORA_DO_FULL == {"craniofacial_structures": ("head",)},
           str(RS.ROTULOS_FORA_DO_FULL))
    checar(u"  e `ROTULOS_SO_NO_FULL` ficou vazio (a abdominal_muscles "
           u"inteira)", RS.ROTULOS_SO_NO_FULL == {},
           str(RS.ROTULOS_SO_NO_FULL))
    checar(u"os insumos fora do FULL sao so a `head`",
           list(RO.insumos_fora_do_full(cruas))
           == ["craniofacial_structures:head"],
           str(list(RO.insumos_fora_do_full(cruas))))
    checar(u"o plugin `abm` nao existe (nem a task tem plugin)",
           "abm" not in RS.POR_COD
           and "abdominal_muscles" not in RS.PLUGIN_DA_TASK
           and not RS.rotulo_vai_ao_plugin("abdominal_muscles",
                                           "trapezius_left"))
    checar(u"  e o sufixo dele ficou para a leitura de arquivo antigo",
           "_abm" in RS.SUFIXOS_APOSENTADOS
           and "_abm" not in RS.SUFIXOS_VIVOS)
    velho_fora, velho_so = RS.ROTULOS_FORA_DO_FULL, RS.ROTULOS_SO_NO_FULL
    try:
        RS.ROTULOS_FORA_DO_FULL = {
            "trunk_cavities": ("thoracic_cavity", "mediastinum"),
            "craniofacial_structures": ("head",)}
        RS.ROTULOS_SO_NO_FULL = {
            "abdominal_muscles": ("pectoralis_major_left",
                                  "pectoralis_major_right")}
        vocab_i = set(RO.vocabulario_do_full(cruas, E.TS_MAP))
    finally:
        RS.ROTULOS_FORA_DO_FULL, RS.ROTULOS_SO_NO_FULL = velho_fora, velho_so
    checar(u"ISCA: com o registro da v8.2, o mediastino e o trapezio ficariam "
           u"fora (as checagens de cima reprovariam)",
           "mediastinum" not in vocab_i and "trapezius_left" not in vocab_i
           and "pectoralis_major_left" in vocab_i, str(sorted(vocab_i))[:160])

    g = radai_geom.Grade((3.0, 2.0, 2.0))
    cav = np.zeros((Z, Y, X), bool)
    cav[5:25, 30:90, 30:90] = True
    lobo = np.zeros((Z, Y, X), bool)
    lobo[8:20, 40:60, 35:55] = True
    for rec in ("thoracic_cavity", "mediastinum"):
        m = {rec: cav, "lung_upper_lobe_left": lobo}
        par = [p for p in E.sobreposicoes(m, g, construcoes={})
               if rec in p[:2]]
        checar(u"`%s` x o que esta dentro: esperado no FULL (recipiente)"
               % rec, not par, str(par))
        par_e = [p for p in E.sobreposicoes(m, g, construcoes={},
                                            estrito=True) if rec in p[:2]]
        checar(u"  e continua alarme no modo estrito (o OAR)", bool(par_e))
    velho_rec = E.RECIPIENTES_NO_FULL
    try:
        E.RECIPIENTES_NO_FULL = ("abdominal_cavity",)
        par_i = E.sobreposicoes({"mediastinum": cav,
                                 "lung_upper_lobe_left": lobo}, g,
                                construcoes={})
    finally:
        E.RECIPIENTES_NO_FULL = velho_rec
    checar(u"ISCA: sem o mediastino entre os recipientes, o par alarma no "
           u"FULL (a checagem de cima reprovaria)", bool(par_i), str(par_i))

    aut = np.zeros((Z, Y, X), bool)
    aut[5:20, 80:95, 60:75] = True
    ere = np.zeros((Z, Y, X), bool)
    ere[5:20, 82:95, 62:75] = True
    m3 = {"autochthon_left": aut, "erector_spinae_left": ere}
    checar(u"autoctone x eretor da espinha (a mesma estrutura por duas "
           u"tasks): esperado no FULL",
           not E.sobreposicoes(m3, g, construcoes={}))
    checar(u"  e continua alarme no modo estrito (se um dia for ao OAR)",
           bool(E.sobreposicoes(m3, g, construcoes={}, estrito=True)))
    velho_mm = E.MESMO_MUSCULO_NO_FULL
    try:
        E.MESMO_MUSCULO_NO_FULL = ()
        par_m = E.sobreposicoes(m3, g, construcoes={})
    finally:
        E.MESMO_MUSCULO_NO_FULL = velho_mm
    checar(u"ISCA: sem a tabela, o par alarma no FULL (a checagem de cima "
           u"reprovaria)", bool(par_m), str(par_m))
    checar(u"  e um par que NAO e o mesmo musculo continua alarme",
           bool(E.sobreposicoes({"autochthon_left": aut,
                                 "trapezius_left": ere}, g,
                                construcoes={})))

    grupo = list(E.GRUPOS_DISJUNTOS["cardiomediastinal"])
    checar(u"o mediastino saiu do grupo disjunto `cardiomediastinal`",
           "mediastinum" not in grupo, str(grupo))
    cor = np.zeros((Z, Y, X), bool)
    cor[8:18, 40:70, 50:80] = True
    med = np.zeros((Z, Y, X), bool)
    med[10:16, 45:60, 60:70] = True
    m2 = {"heart_model": cor.copy(), "mediastinum": med.copy()}
    g2, _aj = E._grupo_disjunto_da_serie(m2, grupo)
    g2i, _aji = E._grupo_disjunto_da_serie(m2, grupo + ["mediastinum"])
    checar(u"  e o coracao do modelo nao perde nada para ele",
           "mediastinum" not in g2)
    checar(u"ISCA: com o mediastino no grupo, o coracao perderia voxel para "
           u"ele (o defeito da spec A3, reproduzido)",
           "heart_model" in g2i
           and int(np.asarray(g2i["heart_model"]).sum()) < int(cor.sum()),
           str(int(np.asarray(g2i.get("heart_model", cor)).sum())))


def teste_o_apendice_atrial_e_roi_do_full():
    secao(u"v8.3: o apendice atrial esquerdo, ROI propria do FULL")
    checar(u"no `TS_MAP`, da familia `total`",
           E.TS_MAP.get("atrial_appendage_left")
           == {"total": ["atrial_appendage_left"]},
           str(E.TS_MAP.get("atrial_appendage_left")))
    nome = E.nome_clinico("atrial_appendage_left")
    checar(u"sai `AtrialApp_L_ai` (<= 16 com o sufixo)",
           nome == "AtrialApp_L_ai" and len(nome) <= 16, nome)
    checar(u"  e o nome esta marcado a conferir (forma nossa)",
           "atrial_appendage_left" in E.TG263_A_CONFERIR)
    checar(u"  e NAO esta entre os permitidos do OAR",
           "atrial_appendage_left" not in RS.PERMITIDOS_NO_OAR)
    velho = E.TG263.pop("atrial_appendage_left")
    try:
        nome_i = E.nome_clinico("atrial_appendage_left")
    finally:
        E.TG263["atrial_appendage_left"] = velho
    checar(u"ISCA: sem a entrada do TG263, sairia `atrial_appe_L_ai` (o nome "
           u"que a v8.2 gravava)", nome_i == "atrial_appe_L_ai", nome_i)
    base = tempfile.mkdtemp(prefix="radai_t_fulloar_")
    try:
        serie = _serie(base)
        _sd, r, _l, _d = _rodar(base, serie)
        checar(u"na cadeia: `AtrialApp_L_ai` no FULL e fora do OAR",
               "AtrialApp_L_ai" in r["estruturas_full"]
               and "AtrialApp_L_ai" not in r["estruturas"],
               str([n for n in r["estruturas_full"] if "trial" in n]))
    finally:
        shutil.rmtree(base, ignore_errors=True)


def teste_o_reto_e_os_compostos_da_pelve():
    secao(u"v8.3: o reto, os compostos da pelve e o nome do FULL")
    base = tempfile.mkdtemp(prefix="radai_t_fulloar_")
    try:
        serie = _serie(base)
        sd, r, linhas, dest = _rodar(base, serie, cruas=_cruas_pelve())
        full, oar = set(r["estruturas_full"]), set(r["estruturas"])
        mf = dict((k, np.asarray(v, bool))
                  for k, v in sd.meta_do_full["mascaras"].items())
        for n in ("Rectum_ai", "Bowel_Large_ai"):
            checar(u"`%s` no FULL e no OAR" % n, n in full and n in oar,
                   u"FULL: %s | OAR: %s" % (n in full, n in oar))
        checar(u"nenhuma ROI com o sufixo aposentado `_der`, nos dois",
               not [n for n in full | oar if n.endswith("_der")],
               str(sorted(n for n in full | oar if "ect" in n)))
        gf, go = _geracao(r["full"]), _geracao(r["oar"])
        checar(u"a procedencia do reto continua no ROIGenerationDescription "
               u"(FULL e OAR): derivada por marco",
               u"derivada por marco" in gf.get("Rectum_ai", u"")
               and u"derivada por marco" in go.get("Rectum_ai", u""),
               gf.get("Rectum_ai", u"-"))
        checar(u"  e o colon que sobra diz que e do TotalSegmentator",
               u"TotalSegmentator" in gf.get("Bowel_Large_ai", u""),
               gf.get("Bowel_Large_ai", u"-"))
        cru_colon = np.asarray(_cruas_pelve()["total_v3"]["colon"], bool)
        checar(u"reto e colon nao se sobrepoem (colon = colon - reto)",
               "rectum" in mf and "colon" in mf
               and not (mf["rectum"] & mf["colon"]).any())
        checar(u"  e o colon entregue e MENOR que o do modelo (perdeu o reto)",
               "colon" in mf and int(mf["colon"].sum()) < int(cru_colon.sum()),
               u"%d contra %d" % (int(mf.get("colon", cru_colon).sum()),
                                  int(cru_colon.sum())))
        checar(u"o log diz a derivacao", any(
            l.startswith(u"derivadas de colon: rectum") for l in linhas))
        checar(u"`Bone_Pelvic_ai` no FULL e no OAR",
               "Bone_Pelvic_ai" in full and "Bone_Pelvic_ai" in oar,
               u"FULL: %s | OAR: %s" % ("Bone_Pelvic_ai" in full,
                                        "Bone_Pelvic_ai" in oar))
        checar(u"`Muscles_ai` so no FULL (fora do OAR)",
               "Muscles_ai" in full and "Muscles_ai" not in oar,
               u"FULL: %s | OAR: %s" % ("Muscles_ai" in full,
                                        "Muscles_ai" in oar))
        for parte in ("Glute_Max_L_ai", "Glute_Med_L_ai", "Musc_Gluteus_ai",
                      "Musc_Iliops_L_ai", "Bone_Pelvic_L_ai",
                      "Bone_Pelvic_R_ai", "Sacrum_ai"):
            checar(u"a parte `%s` fica no FULL e NAO vai ao OAR" % parte,
                   parte in full and parte not in oar,
                   u"FULL: %s | OAR: %s" % (parte in full, parte in oar))
        partes_m = [p for p in E.COMPOSTOS["pelvic_muscles"] if p in mf]
        uniao = np.zeros_like(mf["pelvic_muscles"])
        for p in partes_m:
            uniao |= mf[p]
        checar(u"`Muscles_ai` e EXATAMENTE a uniao dos gluteos e iliopsoas "
               u"suavizados", np.array_equal(mf["pelvic_muscles"], uniao)
               and len(partes_m) == 5, u"%d parte(s)" % len(partes_m))
        osso = mf["hip_left"] | mf["hip_right"] | mf["sacrum"]
        checar(u"`Bone_Pelvic_ai` e EXATAMENTE quadril E + quadril D + sacro",
               np.array_equal(mf["bone_pelvic"], osso))
        checar(u"os marcos continuam lendo as partes (a derivacao achou o "
               u"sacro e o quadril)", "rectum" in mf)
        alarme = [l for l in linhas if u"SOBREPOSICAO" in l.upper()
                  and u"Musc" in l and u"Muscles" in l]
        checar(u"composto dentro de composto nao alarma no FULL (Muscles_ai x "
               u"Musc_Gluteus_ai)", not alarme, u" | ".join(alarme)[:200])
        ds_full = pydicom.dcmread(r["full"])
        desc = str(ds_full.StructureSetDescription)
        checar(u"o FULL diz o nome dele na StructureSetDescription (FULL, e "
               u"nao AI_completo)", u" FULL" in desc
               and u"AI_completo" not in desc, desc[:160])
        checar(u"  e o log de gravacao diz `FULL:`",
               any(l.startswith(u"FULL: ") and u"RS_RadAI_FULL_" in l
                   for l in linhas))
        checar(u"o registro: nome, rotulo e rotulo curto coerentes com o "
               u"RadAI_FULL", RS.POR_COD["full"]["nome"] == u"FULL"
               and RS.POR_COD["full"]["rotulo_curto"] == u"FULL"
               and RS.POR_COD["full"]["rotulo"].startswith(u"FULL"),
               str((RS.POR_COD["full"]["nome"],
                    RS.POR_COD["full"]["rotulo_curto"])))
        checar(u"  e o rotulo do OAR diz a selecao do FULL (e nao "
               u"«agrupado»)", u"agrupado" not in RS.POR_COD["oar"]["rotulo"]
               and u"FULL" in RS.POR_COD["oar"]["rotulo"],
               RS.POR_COD["oar"]["rotulo"])
        cru_alvo = sd.totalsegmentator_cru(_cruas_pelve())
        nomes_cru = [str(x.ROIName) for x in
                     pydicom.dcmread(cru_alvo).StructureSetROISequence]
        checar(u"o TS cru mantem o colon unico (`Bowel_Large_ts`), sem reto",
               u"Bowel_Large_ts" in nomes_cru
               and not any(u"ectum" in n for n in nomes_cru), str(nomes_cru))

        sd2, r2, linhas2, _d2 = _rodar(base, serie,
                                       cruas=_cruas_pelve(sem=("sacrum",)))
        full2 = set(r2["estruturas_full"])
        mf2 = sd2.meta_do_full["mascaras"]
        checar(u"sem o sacro nao ha reto, e o colon sai INTEIRO "
               u"(Bowel_Large_ai)", "Rectum_ai" not in full2
               and "Bowel_Large_ai" in full2
               and "Bowel_Large_ai" in set(r2["estruturas"]),
               str(sorted(n for n in full2 if "owel" in n or "ect" in n)))
        checar(u"  e o log diz por que", any(
            l.startswith(u"derivadas de colon: NAO DERIVADO") for l in linhas2),
            str([l for l in linhas2 if u"derivadas" in l])[:200])
        checar(u"  e o colon entregue tem o volume do modelo (nada tirado)",
               "rectum" not in mf2
               and abs(int(np.asarray(mf2["colon"], bool).sum())
                       - int(cru_colon.sum())) < 0.2 * int(cru_colon.sum()),
               u"%d contra %d" % (int(np.asarray(mf2.get("colon", 0)).sum()),
                                  int(cru_colon.sum())))

        velho_suf = E.sufixo_de_procedencia
        velho_nome = RS.POR_COD["full"]["nome"]

        def _suf_antigo(chave, origem=None, motor_alt="",
                        sufixo_do_conjunto=E.SUFIXO_AI):
            if (origem or {}).get(chave) == "derivada" and not motor_alt:
                return "_der"
            return velho_suf(chave, origem, motor_alt, sufixo_do_conjunto)
        try:
            E.sufixo_de_procedencia = _suf_antigo
            RS.POR_COD["full"]["nome"] = u"AI_completo"
            _sd3, r3, _l3, _d3 = _rodar(base, serie, cruas=_cruas_pelve())
        finally:
            E.sufixo_de_procedencia = velho_suf
            RS.POR_COD["full"]["nome"] = velho_nome
        full3 = set(r3["estruturas_full"])
        checar(u"ISCA: com o sufixo aposentado, o reto sairia `Rectum_der` (a "
               u"checagem do `_der` reprovaria)", "Rectum_der" in full3,
               str(sorted(n for n in full3 if "ect" in n)))
        desc3 = str(pydicom.dcmread(r3["full"]).StructureSetDescription)
        checar(u"ISCA: com o nome antigo, a descricao diria AI_completo (a "
               u"checagem do nome reprovaria)", u"AI_completo" in desc3,
               desc3[:120])
    finally:
        shutil.rmtree(base, ignore_errors=True)

    import radai_geom
    g = radai_geom.Grade((3.0, 2.0, 2.0))
    a = np.zeros((Z, Y, X), bool)
    a[5:10, 20:30, 20:30] = True
    b = np.zeros((Z, Y, X), bool)
    b[5:10, 30:40, 20:30] = True
    m = {"gluteus_maximus_left": a, "iliopsoas_left": b,
         "gluteus_muscles": a.copy(), "pelvic_muscles": a | b}
    par = [p for p in E.sobreposicoes(m, g, construcoes={})
           if {"gluteus_muscles", "pelvic_muscles"} == set(p[:2])]
    checar(u"composto contido em composto e esperado (FULL)", not par,
           str(par))
    velho = list(E.COMPOSTOS["pelvic_muscles"])
    try:
        E.COMPOSTOS["pelvic_muscles"] = [p for p in velho
                                         if p != "gluteus_maximus_left"]
        par_i = [p for p in E.sobreposicoes(m, g, construcoes={})
                 if {"gluteus_muscles", "pelvic_muscles"} == set(p[:2])]
    finally:
        E.COMPOSTOS["pelvic_muscles"] = velho
    checar(u"ISCA: sem a contencao pelas partes, o par alarma (a checagem de "
           u"cima reprovaria)", bool(par_i), str(par_i))
    checar(u"o osso da pelve esta no OAR, o Muscles_ai nao, e as partes nao",
           "bone_pelvic" in RS.PERMITIDOS_NO_OAR
           and "pelvic_muscles" not in RS.PERMITIDOS_NO_OAR
           and not ({"gluteus_muscles", "iliopsoas_left", "iliopsoas_right",
                     "hip_left", "hip_right", "sacrum"}
                    & RS.PERMITIDOS_NO_OAR))
    checar(u"  e a glandula por lado tambem (spec M-M)",
           {"breast_left", "breast_right"} <= RS.PERMITIDOS_NO_OAR)
    spec_skin = dict(E.CONSTRUCOES_POR_SAIDA().get("Skin") or {})
    checar(u"a Skin declara conter a glandula por lado, pelas chaves de "
           u"`CHAVES_GLANDULA_POR_LADO`",
           set(spec_skin.get("contem") or ())
           == set(E.CHAVES_GLANDULA_POR_LADO.values()),
           str(spec_skin.get("contem")))
    pele = np.zeros((Z, Y, X), bool)
    pele[5:10, 20:24, 20:60] = True
    gl = np.zeros((Z, Y, X), bool)
    gl[5:10, 20:30, 30:50] = True
    par = E.sobreposicoes({"Skin": pele, "breast_left": gl}, g,
                          construcoes={"Skin": spec_skin}, estrito=True)
    checar(u"Skin x glandula nao alarma no OAR (a pele a cobre por "
           u"definicao)", not par, str(par))
    sem = dict(spec_skin)
    sem["contem"] = ()
    par_i = E.sobreposicoes({"Skin": pele, "breast_left": gl}, g,
                            construcoes={"Skin": sem}, estrito=True)
    checar(u"ISCA: sem a declaracao, o par alarma no OAR (a checagem de cima "
           u"reprovaria)", bool(par_i), str(par_i))


def _so_o_fast(dest):
    arqs = sorted(a for a in os.listdir(dest) if a.endswith(".dcm"))
    return arqs, (len(arqs) == 1 and arqs[0].startswith("RS_RadAI_FAST_"))


def teste_o_fast_grava_so_o_oar_fast():
    secao(u"o FAST grava so o RadAI_STUDY_Fast (spec 1.1, 1.4)")
    base = tempfile.mkdtemp(prefix="radai_t_fulloar_")
    try:
        serie = _serie(base)
        sd, r, linhas, dest = _rodar(base, serie, modo="fast")
        arqs, so = _so_o_fast(dest)
        checar(u"o FAST grava SO o RS_RadAI_FAST_* (sem FULL, sem OAR, sem "
               u"TS cru)", so, str(arqs))
        checar(u"  e `gravados` diz so `fast` (nada de `ts`)",
               sd.gravados == ["fast"], str(sd.gravados))
        checar(u"  e o resultado: modo fast, o entregue e o OAR_Fast, sem "
               u"FULL nem OAR",
               r.get("modo") == "fast" and r.get("entregue") == r.get(
                   "oar_fast") and r.get("full") is None
               and r.get("oar") is None, str(dict(
                   (k, r.get(k)) for k in ("modo", "full", "oar"))))
        ds = pydicom.dcmread(r["oar_fast"])
        nomes = [str(x.ROIName) for x in ds.StructureSetROISequence]
        checar(u"rotulo `RadAI_STUDY_Fast`, UNAPPROVED, serie 900 (a do "
               u"entregue)", ds.StructureSetLabel == "RadAI_STUDY_Fast"
               and ds.ApprovalStatus == "UNAPPROVED"
               and int(ds.SeriesNumber) == 900,
               "%s %s %s" % (ds.StructureSetLabel, ds.ApprovalStatus,
                             ds.SeriesNumber))
        checar(u"  ISCA: o rotulo antigo `RadAI_OAR_Fast` reprovaria, e o "
               u"leitor ainda o reconhece como o FAST",
               "RadAI_OAR_Fast" != ds.StructureSetLabel
               and RS.cod_do_rotulo("RadAI_OAR_Fast") == "fast")
        checar(u"  toda ROI com o sufixo `_ai`, e nenhum contorno externo",
               nomes and all(n.endswith("_ai") for n in nomes)
               and not any(n.lower().startswith(("body", "external"))
                           for n in nomes), str(nomes))
        checar(u"  e a descricao diz que NAO e copia do FULL e que preservou os pontos",
               "NAO e copia" in str(ds.StructureSetDescription)
               and "Douglas-Peucker" not in str(ds.StructureSetDescription),
               str(ds.StructureSetDescription)[:200])
        _b = os.path.basename(r["oar_fast"])
        checar(u"o registro o reconhece: `fast`, e ENTREGUE",
               (RS.do_arquivo(_b) or {}).get("cod") == "fast"
               and RS.e_entregue(_b), _b)
        checar(u"  e ele fica FORA de `CONJUNTOS` (as telas nao o contam "
               u"como faltando numa serie AUTO)",
               "fast" not in [c["cod"] for c in RS.CONJUNTOS]
               and "fast" in RS.POR_COD)
        sd2, r2, l2, dest2 = _rodar(base, serie)
        retiradas = {E.nome_clinico(k) for k in (
            "bag_bowel_oar", "anus", "Skin", "ChestWall_L", "ChestWall_R",
            "ribs_left", "ribs_right", "costal_cartilages", "sternum")}
        esperado = set(r2["estruturas"]) - retiradas
        checar(u"o conteudo FAST exclui bag, anus, pele, paredes, costelas e cartilagem",
               set(r["estruturas"]) == esperado,
               u"so no FAST: %s | faltam: %s" % (
                   sorted(set(r["estruturas"]) - esperado),
                   sorted(esperado - set(r["estruturas"]))))
        checar(u"  (o fantoma tem a Bag_Bowel_OAR no AUTO: a diferenca e "
               u"medida)", "Bag_Bowel_OAR_ai" in r2["estruturas"]
               and "Bag_Bowel_ai" not in r2["estruturas"],
               str(r2["estruturas"]))
        filtro = dict((sd.meta_do_fast or {}).get("filtro") or {})
        checar(u"a Bag_Bowel nem foi montada no FAST (construcao fora do "
               u"filtro, e nao «nao saiu»)",
               "bag_bowel" in (filtro.get("fora_do_filtro") or ())
               and not any(c == "bag_bowel" for c, _m in
                           (sd.meta_do_fast.get("nao_sairam") or ())),
               str(filtro.get("fora_do_filtro")))
        checar(u"o pericardio e INSUMO: monta o Heart_ai e nao vira ROI",
               "pericardium" in (r.get("insumos") or ())
               and not any("ericard" in n for n in nomes)
               and "Heart_ai" in nomes, str(r.get("insumos")))
        sua_fast = set(x[0] for x in sd.meta_do_fast.get("suavizacao") or ())
        sua_full = set(x[0] for x in sd2.meta_do_full.get("suavizacao") or ())
        checar(u"os compostos sao suavizados INTEIROS no FAST (pulmao, "
               u"grandes arterias) — e refeitos das partes no FULL",
               {"lung_left", "great_arteries"} <= sua_fast
               and not ({"lung_left", "great_arteries"} & sua_full)
               and "lung_upper_lobe_left" in sua_full
               and "lung_upper_lobe_left" not in sua_fast,
               u"FAST: %s | FULL: %s" % (sorted(sua_fast)[:12],
                                         sorted(sua_full)[:12]))
        mf = sd.meta_do_fast.get("mascaras") or {}
        _h = np.asarray(mf.get("heart"), bool) if "heart" in mf else None
        _cruz = dict((c, int((_h & np.asarray(mf[c], bool)).sum()))
                     for c in ("great_arteries", "great_veins")
                     if _h is not None and c in mf)
        checar(u"  as grandes arterias perdem o Heart_ai; as veias podem "
               u"sobrepor o coracao tambem no FAST",
               _h is not None and _cruz and _cruz.get("great_arteries") == 0,
               str(_cruz))
        checar(u"o log diz que preservou os pontos e aplicou o filtro",
               any(u"sem decimacao de pontos" in l for l in linhas)
               and any(l.startswith(u"FAST: o filtro do OAR_Fast") for l in
                       linhas))
        velho = RO.normalizar_modo
        RO.normalizar_modo = lambda v: "auto"
        try:
            sd3, r3, l3, dest3 = _rodar(base, serie, modo="fast")
        finally:
            RO.normalizar_modo = velho
        arqs3, so3 = _so_o_fast(dest3)
        checar(u"ISCA: com o modo perdido no caminho, «so o OAR_Fast» "
               u"reprova (sai o FULL)", not so3, str(arqs3))
    finally:
        shutil.rmtree(base, ignore_errors=True)


def _funcoes_que_decimam(fonte):
    import ast
    fora = set()
    for no in ast.walk(ast.parse(fonte)):
        if not isinstance(no, ast.FunctionDef):
            continue
        for c in ast.walk(no):
            if isinstance(c, ast.Call) and any(
                    k.arg == "decimar_mm" for k in c.keywords):
                fora.add(no.name)
    return fora


def teste_as_entregas_nao_decimam():
    secao(u"FAST, AUTO e FULL sem decimacao de pontos")
    base = tempfile.mkdtemp(prefix="radai_t_fulloar_")
    try:
        serie = _serie(base)
        sd, r, linhas, dest = _rodar(base, serie, modo="fast")
        dec = r.get("decimacao") or {}
        checar(u"o FAST conserva os pontos do gravador comum", not dec, str(dec))
        ds = pydicom.dcmread(r["oar_fast"])
        ruins = []
        for rc in ds.ROIContourSequence:
            for c in rc.ContourSequence:
                n = len(c.ContourData) // 3
                if n < 3 or int(c.NumberOfContourPoints) != n:
                    ruins.append((int(rc.ReferencedROINumber), n,
                                  int(c.NumberOfContourPoints)))
        checar(u"  nenhum poligono com menos de 3 pontos, e o "
               u"NumberOfContourPoints acompanha", not ruins, str(ruins[:4]))
        checar(u"o FAST informa que nao decima", any(u"sem decimacao de pontos" in l for l in linhas))
        sd2, r2, l2, dest2 = _rodar(base, serie, modo="auto")

        def _sem_decimacao(sdx, lx):
            return ("decimacao" not in (sdx.meta_do_full or {})
                    and not any(u"decimacao" in l for l in lx))
        checar(u"o AUTO nao decima (nem o FULL, nem, portanto, o OAR)",
               _sem_decimacao(sd2, l2))
        nf, cf, _of = _rois(pydicom.dcmread(r2["full"]))
        no, co, _oo = _rois(pydicom.dcmread(r2["oar"]))
        checar(u"  e o OAR do AUTO continua a copia byte a byte do FULL",
               no and all(n in cf and cf[n].ContourSequence ==
                          co[n].ContourSequence for n in no))
        velho = E.build_rtstruct

        def _sempre(*a, **kw):
            kw["decimar_mm"] = 0.2
            return velho(*a, **kw)
        E.build_rtstruct = _sempre
        try:
            sd3, r3, l3, dest3 = _rodar(base, serie, modo="auto")
        finally:
            E.build_rtstruct = velho
        checar(u"ISCA: um build_rtstruct que decima sempre faz a checagem "
               u"do AUTO reprovar", not _sem_decimacao(sd3, l3))
        fonte = open(os.path.join(pasta_app(AQUI), "radai_output.py"),
                     encoding="utf-8").read()
        checar(u"nenhuma entrega passa decimar_mm ao gravador",
               not _funcoes_que_decimam(fonte),
               str(_funcoes_que_decimam(fonte)))
        _alvo = u"                selecao=permitidos,\n"
        checar(u"  (isca) a linha da chamada do FULL esta onde a isca a "
               u"procura", fonte.count(_alvo) == 1)
        _isca = fonte.replace(_alvo, _alvo + u"                "
                              u"decimar_mm=0.2,\n")
        checar(u"ISCA: com `decimar_mm=` na chamada do FULL, a ancora acusa",
               "full_e_oar" in _funcoes_que_decimam(_isca))
    finally:
        shutil.rmtree(base, ignore_errors=True)


def _ds_de_poligonos(poligonos):
    from pydicom.dataset import Dataset
    from pydicom.sequence import Sequence
    ds = Dataset()
    rcs = []
    for i, p in enumerate(poligonos, 1):
        c = Dataset()
        c.ContourGeometricType = "CLOSED_PLANAR"
        c.NumberOfContourPoints = int(p.shape[0])
        c.ContourData = ["%.4f" % float(x) for x in p.ravel()]
        rc = Dataset()
        rc.ReferencedROINumber = i
        rc.ContourSequence = Sequence([c])
        rcs.append(rc)
    ds.ROIContourSequence = Sequence(rcs)
    return ds


def _elipse(a, b, n, z=5.0):
    t = np.linspace(0, 2 * np.pi, n, endpoint=False)
    return np.c_[a * np.cos(t), b * np.sin(t), np.full(n, z)]


def teste_a_decimacao_poupa_a_estrutura_pequena():
    secao(u"a decimacao poupa a estrutura pequena (27/09/2026)")
    import radai_geom as G
    formas = {
        u"cristalino (9 x 4 mm)": _elipse(4.5, 2.0, 40),
        u"nervo optico no axial (24 x 3,6 mm)": _elipse(12.0, 1.8, 80),
        u"forma fina acima do piso (40 x 5 mm)": _elipse(20.0, 2.5, 120),
        u"orgao grande (40 mm)": _elipse(20.0, 20.0, 160),
    }
    nomes = list(formas)

    def _decimar(**kw):
        ds = _ds_de_poligonos([formas[n] for n in nomes])
        laudo = E._decimar_contornos(ds, E.DECIMACAO_FAST_MM, **kw)
        fora = {}
        for n, rc in zip(nomes, ds.ROIContourSequence):
            q = np.asarray([float(v) for v in rc.ContourSequence[0]
                            .ContourData]).reshape(-1, 3)
            p = formas[n]
            fora[n] = (int(q.shape[0]), G.area_poligono(q) / G.area_poligono(p)
                       - 1.0)
        return laudo, fora
    laudo, r = _decimar()
    for n in nomes[:3]:
        checar(u"%s: nenhum ponto sai, a área não anda" % n,
               r[n][0] == formas[n].shape[0] and abs(r[n][1]) < 1e-5,
               u"%d pontos, %+.2f%%" % (r[n][0], 100 * r[n][1]))
    n = nomes[3]
    checar(u"%s: decimado (menos pontos) e a área anda no máximo 1%%" % n,
           r[n][0] < formas[n].shape[0] and abs(r[n][1])
           <= E.PERDA_MAXIMA_DECIMACAO,
           u"%d pontos, %+.2f%%" % (r[n][0], 100 * r[n][1]))
    checar(u"o laudo conta os poupados: 2 pela área, 1 pela perda",
           laudo.get("poupados_area") == 2 and laudo.get("poupados_perda") == 1,
           str(dict((k, laudo.get(k)) for k in ("poupados_area",
                                                "poupados_perda"))))
    checar(u"o piso é 1 cm² e a perda máxima é 1% (as constantes do motor)",
           E.AREA_MINIMA_DECIMADA_MM2 == 100.0
           and E.PERDA_MAXIMA_DECIMACAO == 0.01)
    _l0, r0 = _decimar(area_minima=0, perda_maxima=None)
    cr = nomes[0]
    checar(u"ISCA: sem as guardas o cristalino perde área (%.1f%%) — a "
           u"checagem de cima reprovaria" % (100 * r0[cr][1]),
           r0[cr][0] < formas[cr].shape[0] and r0[cr][1] < -0.02,
           u"%d pontos, %+.2f%%" % (r0[cr][0], 100 * r0[cr][1]))
    _l1, r1 = _decimar(perda_maxima=None)
    fi = nomes[2]
    checar(u"ISCA: só com o piso de área, a forma fina acima dele perde "
           u"%.1f%% — por isso a segunda guarda" % (100 * r1[fi][1]),
           r1[fi][1] < -E.PERDA_MAXIMA_DECIMACAO, u"%+.2f%%" % (100 * r1[fi][1]))


def teste_o_oar_fora_so_tira_do_oar():
    secao(u"oar_fora so tira do OAR (spec 1.1, 1.6)")
    base = tempfile.mkdtemp(prefix="radai_t_fulloar_")
    try:
        serie = _serie(base)
        sd, r, linhas, dest = _rodar(base, serie, modo="perso",
                                     oar_fora=["heart", "Lung_L_ai",
                                               "nao_existe"])
        oar, full = set(r["estruturas"]), set(r["estruturas_full"])
        checar(u"Heart_ai e Lung_L_ai SAIRAM do OAR desta serie",
               "Heart_ai" not in oar and "Lung_L_ai" not in oar, str(oar))
        checar(u"  e FICARAM no FULL", {"Heart_ai", "Lung_L_ai"} <= full)
        checar(u"  e o resultado diz o que saiu, pela chave",
               r.get("oar_fora") == ["heart", "lung_left"]
               and r.get("modo") == "perso", str(r.get("oar_fora")))
        checar(u"  e a chave que nao e do OAR foi ignorada, com linha no log",
               any(u"ignorei nao_existe" in l for l in linhas))
        nf, cf, _of = _rois(pydicom.dcmread(r["full"]))
        no, co, _oo = _rois(pydicom.dcmread(r["oar"]))
        checar(u"o que sobrou no OAR continua a copia byte a byte do FULL",
               no and all(n in cf and cf[n].ContourSequence ==
                          co[n].ContourSequence for n in no))
        checar(u"  e a sobreposicao estrita foi conferida sobre o OAR desta "
               u"serie", any(l.startswith("OAR:") and "sobreposicao" in
                             l.lower() for l in linhas))
        sd2, r2, l2, dest2 = _rodar(base, serie, modo="perso")
        checar(u"ISCA: sem `oar_fora` o Heart_ai e o Lung_L_ai estao no OAR "
               u"(a checagem acima discrimina)",
               {"Heart_ai", "Lung_L_ai"} <= set(r2["estruturas"]))
        checar(u"sem `oar_fora`, a lista e a do registro (o MESMO objeto)",
               RO.permitidos_do_oar(None)[0] is RS.PERMITIDOS_NO_OAR)
        sd3, r3, l3, dest3 = _rodar(base, serie, modo="fast",
                                    oar_fora=["heart"])
        checar(u"no FAST `oar_fora` e ignorado (o Heart_ai fica), e o log "
               u"diz", "Heart_ai" in r3["estruturas"]
               and any(u"IGNORADA no modo FAST" in l for l in l3))
    finally:
        shutil.rmtree(base, ignore_errors=True)


def teste_os_compostos_inteiros_no_grupo_e_sem_o_coracao():
    secao(u"os compostos inteiros do FAST (no grupo, e sem o coracao)")
    forma = (10, 30, 30)
    ga = np.zeros(forma, bool)
    ga[2:8, 5:20, 5:20] = True
    co = np.zeros(forma, bool)
    co[2:8, 15:25, 15:25] = True
    m1 = {"great_arteries": ga.copy(), "heart": co.copy()}
    E.recompor_compostos(m1, so={"great_arteries"}, subtrair={"heart"},
                         inteiros=True)
    checar(u"o composto INTEIRO perde o que a construcao ocupa",
           not (m1["great_arteries"] & co).any()
           and m1["great_arteries"].any())
    m2 = {"great_arteries": ga.copy(), "heart": co.copy()}
    E.recompor_compostos(m2, so={"great_arteries"}, subtrair={"heart"})
    checar(u"ISCA: sem `inteiros`, a sobreposicao fica (o composto sem "
           u"parte nao e tocado)", (m2["great_arteries"] & co).any())
    m3 = {"great_arteries": ga.copy(), "heart": co.copy(),
          "aorta": ga.copy()}
    E.recompor_compostos(m3, so={"great_arteries"}, subtrair={"heart"},
                         inteiros=True)
    checar(u"  com a parte presente, ele e refeito DA PARTE (como no FULL)",
           (m3["great_arteries"] == (ga & ~co)).all())
    vazio = np.zeros(forma, bool)
    mm = {"ribs_left": vazio, "vertebrae_thoracic": vazio,
          "lung_left": vazio, "sternum": vazio}
    grupo = list(E.GRUPOS_DISJUNTOS["esqueleto_toracico"])
    entram = set(E._compostos_no_lugar_das_partes(mm, grupo))
    checar(u"no esqueleto toracico entram a costela e a vertebra INTEIRAS "
           u"(e nao o pulmao)",
           entram == {"ribs_left", "vertebrae_thoracic"}, str(entram))
    mm["rib_left_3"] = vazio
    checar(u"  com uma parte presente, o composto NAO entra (e refeito)",
           "ribs_left" not in E._compostos_no_lugar_das_partes(mm, grupo))
    import radai_geom
    grade = radai_geom.Grade((2.0, 2.0, 2.0))
    ri = np.zeros(forma, bool)
    ri[1:9, 4:16, 4:16] = True
    ve = np.zeros(forma, bool)
    ve[1:9, 12:26, 12:26] = True

    def _grupo(chave):
        mk = {"ribs_left": ri.copy(), "vertebrae_thoracic": ve.copy()}
        linhas = []
        E.suavizar_em_grupos(mk, grade, 1.0, log=linhas.append,
                             compostos_inteiros=chave)
        return mk, linhas
    mk, linhas = _grupo(True)
    checar(u"com `compostos_inteiros`, a costela e a vertebra inteiras saem "
           u"DISJUNTAS (o grupo `esqueleto_toracico`)",
           not (mk["ribs_left"] & mk["vertebrae_thoracic"]).any()
           and any(u"esqueleto_toracico" in l for l in linhas), linhas[:2])
    mk2, _l2 = _grupo(False)
    checar(u"ISCA: sem a chave, as duas ficam sobrepostas (nenhum grupo as "
           u"reparte)", (mk2["ribs_left"] & mk2["vertebrae_thoracic"]).any())
    base = tempfile.mkdtemp(prefix="radai_t_fulloar_")
    try:
        serie = _serie(base)
        sd, r, linhas, dest = _rodar(base, serie, modo="fast")
        checar(u"no FAST do fantoma, os pulmoes inteiros repartem a fronteira "
               u"no grupo dos lobos, e o vaso inteiro perde o coracao",
               any(u"`lobos_pulmonares`" in l for l in linhas)
               and any(u"composto inteiro `great_arteries`" in l
                       for l in linhas))
    finally:
        shutil.rmtree(base, ignore_errors=True)


def teste_o_ts_cru_nao_sai_do_entregue():
    secao(u"o TS cru nao sai de full_e_oar (spec 1.1)")
    base = tempfile.mkdtemp(prefix="radai_t_fulloar_")
    try:
        serie = _serie(base)
        for modo in ("auto", "perso", "fast"):
            sd, r, linhas, dest = _rodar(base, serie, modo=modo)
            arqs = [a for a in os.listdir(dest) if a.startswith("RS_RadAI_TS_")]
            checar(u"modo %s: nenhum RS_RadAI_TS_*, e `ts` fora de gravados"
                   % modo, not arqs and "ts" not in sd.gravados,
                   "%s %s" % (arqs, sd.gravados))
        sd, r, linhas, dest = _rodar(base, serie, modo="perso")
        alvo = sd.totalsegmentator_cru(_cruas())
        checar(u"  e o TS cru sai quando PEDIDO (totalsegmentator_cru)",
               alvo and os.path.basename(alvo).startswith("RS_RadAI_TS_"),
               str(alvo))
    finally:
        shutil.rmtree(base, ignore_errors=True)


def _cruas_com_derrame():
    cr = _cruas()
    cr.pop("lung_nodules", None)
    ef = np.zeros((Z, Y, X), np.int16)
    ef[6:9, 40:50, 40:50] = 1
    ef[6:9, 40:50, 75:85] = 1
    ef[10:13, 40:48, 58:62] = 2
    cr["pleural_pericard_effusion"] = E.MasksCruas(
        ef, {1: "pleural_effusion", 2: "pericardial_effusion"})
    return cr


def teste_o_derrame_e_anatomia_do_torax():
    secao(u"o derrame: por lado, no FULL e no OAR, e fora do pulmao (v8.4)")
    import radai_sets as _rs
    import radai_modes as _md
    checar(u"a task do derrame alimenta o FULL e nao e plugin",
           _rs.task_do_full("pleural_pericard_effusion")
           and "pleural_pericard_effusion" not in _rs.PLUGIN_DA_TASK)
    checar(u"  e nao e achado (roda sem ato declarado)",
           "pleural_pericard_effusion" not in E.TASKS_DE_ACHADO)
    checar(u"  e o sufixo `_eff` fica so para ler arquivo antigo",
           "_eff" in _rs.SUFIXOS_APOSENTADOS
           and "_eff" not in _rs.SUFIXOS_VIVOS)
    for k in ("pleural_effusion_left", "pleural_effusion_right",
              "pericardial_effusion"):
        checar(u"  `%s` so no FULL (fora do OAR e do OAR_Fast, v8.5)" % k,
               k not in _rs.PERMITIDOS_NO_OAR
               and k not in _rs.PERMITIDOS_NO_OAR_FAST)
    checar(u"  FAST e AUTO rodam o derrame no torax",
           "pleural_pericard_effusion" in _md.tasks_do_fast(("torax",), None)
           and "pleural_pericard_effusion" in _md.tasks_da_topografia(
               ("torax",)))
    checar(u"  e fora do torax nao rodam",
           "pleural_pericard_effusion" not in _md.tasks_do_fast(("pelve",),
                                                               None)
           and "pleural_pericard_effusion" not in _md.tasks_da_topografia(
               ("pelve",)))
    _p = _md.tasks_do_personalizado([], {}, "CT")
    _p0 = _md.tasks_do_personalizado([], {"pleural_pericard_effusion": 0},
                                     "CT")
    checar(u"  no PERSONALIZADO a chave nasce em 1 e desliga com 0",
           "pleural_pericard_effusion" in _p
           and "pleural_pericard_effusion" not in _p0, str((_p, _p0)))
    for cod in ("torax_mama", "sbrt"):
        checar(u"  o protocolo `%s` arrasta o derrame" % cod,
               "pleural_pericard_effusion"
               in _md.PROT_POR_COD[cod]["tasks"])

    base = tempfile.mkdtemp(prefix="radai_t_fulloar_")
    try:
        serie = _serie(base)
        sd, r, linhas, dest = _rodar(base, serie, cruas=_cruas_com_derrame())
        oar_nomes = set(r["estruturas"])
        full_nomes = set(r["estruturas_full"])
        for n in ("PleuralEff_L_ai", "PleuralEff_R_ai", "PericardEff_ai"):
            checar(u"%s sai so no FULL" % n,
                   n in full_nomes and n not in oar_nomes,
                   u"FULL %s | OAR %s" % (n in full_nomes, n in oar_nomes))
        checar(u"  e o derrame bilateral nao sai (foi partido)",
               "PleuralEff_ai" not in full_nomes)
        mf = (sd.meta_do_full or {}).get("mascaras") or {}
        der_r = mf.get("pleural_effusion_right")
        pul_r = mf.get("lung_right")
        _sobra = (int((np.asarray(der_r, bool) & np.asarray(pul_r, bool)).sum())
                  if der_r is not None and pul_r is not None else -1)
        checar(u"o pulmao direito do FULL nao contem o derrame", _sobra == 0,
               u"%d voxel(s) em comum" % _sobra)
        checar(u"o log diz o que o derrame tirou do pulmao",
               any(l.startswith(u"derrame pleural:") and u"lung_lower_lobe_"
                   u"right" in l for l in linhas),
               str([l for l in linhas if "derrame" in l][:3]))
        _alarme = [l for l in linhas if u"SOBREPOSICAO" in l
                   and u"heart e pericardial_effusion" in l]
        checar(u"o derrame pericardico dentro do Heart_ai e declarado: sem "
               u"alarme de dose dupla", not _alarme, str(_alarme[:1]))
        _obs = _obs_do_arquivo(r["oar"]).get("Heart_ai") or u""
        checar(u"  e a descricao do Heart_ai do OAR diz que o inclui",
               u"Inclui o derrame pericardico" in _obs, _obs[-120:])
        _h = np.asarray(mf.get("heart"), bool)
        _d = np.asarray(mf.get("pericardial_effusion"), bool)
        checar(u"o Heart_ai integra o derrame pericardico (todo ele dentro)",
               _d.any() and not (_d & ~_h).any(),
               u"%d voxel(s) fora" % int((_d & ~_h).sum()))
    finally:
        shutil.rmtree(base, ignore_errors=True)

    base = tempfile.mkdtemp(prefix="radai_t_fulloar_")
    _saida = [c for c in E.CONSTRUCOES if c["cod"] == "coracao"][0][
        "saidas"]["heart"]
    _velho = _saida["contem"]
    try:
        import radai_constructs as _RC
        _velho_d = _RC._derrame_pericardico
        _RC._derrame_pericardico = lambda masks, cru=None: None
        serie = _serie(base)
        try:
            _sdi, _ri, _li, _di = _rodar(base, serie,
                                         cruas=_cruas_com_derrame())
        finally:
            _RC._derrame_pericardico = _velho_d
        _mi = (_sdi.meta_do_full or {}).get("mascaras") or {}
        _hi = np.asarray(_mi.get("heart"), bool)
        _dd = np.asarray(_mi.get("pericardial_effusion"), bool)
        checar(u"  ISCA: sem integrar o derrame, ele fica fora do Heart_ai",
               _dd.any() and bool((_dd & ~_hi).any()))
    finally:
        _saida["contem"] = _velho
        shutil.rmtree(base, ignore_errors=True)

    base = tempfile.mkdtemp(prefix="radai_t_fulloar_")
    try:
        serie = _serie(base)
        ref = E.load_sitk(serie)
        import radai_geom
        grade = radai_geom.Grade.de_sitk(ref)
        lobo_d = np.zeros((Z, Y, X), bool)
        lobo_d[6:11, 40:80, 30:55] = True
        lobo_e = np.zeros((Z, Y, X), bool)
        lobo_e[6:14, 40:80, 70:95] = True
        der = np.zeros((Z, Y, X), bool)
        der[6:9, 40:50, 45:80] = True
        m = {"lung_lower_lobe_right": lobo_d.copy(),
             "lung_lower_lobe_left": lobo_e.copy(),
             "pleural_effusion": der.copy()}
        rel = E.separar_derrame_por_lado(m, grade)
        e_, d_ = m.get("pleural_effusion_left"), m.get("pleural_effusion_right")
        checar(u"o derrame que atravessa o meio sai nos dois lados",
               e_ is not None and d_ is not None and e_.any() and d_.any())
        if e_ is not None and d_ is not None:
            checar(u"  os dois lados sao disjuntos e somam o derrame",
                   not (e_ & d_).any() and bool(((e_ | d_) == der).all()))
            checar(u"  o lado e o do pulmao mais proximo",
                   bool(d_[6:9, 40:50, 45:55].all())
                   and bool(e_[6:9, 40:50, 70:80].all()),
                   u"direito junto do lobo direito: %d de %d; esquerdo junto "
                   u"do esquerdo: %d de %d" % (
                       int(d_[6:9, 40:50, 45:55].sum()),
                       int(der[6:9, 40:50, 45:55].sum()),
                       int(e_[6:9, 40:50, 70:80].sum()),
                       int(der[6:9, 40:50, 70:80].sum())))
        checar(u"  os lobos perdem o que o derrame ocupa",
               not (m["lung_lower_lobe_right"] & der).any()
               and not (m["lung_lower_lobe_left"] & der).any())
        checar(u"  e o relatorio diz quanto",
               set(rel.get("descontado_cm3") or {}) ==
               {"lung_lower_lobe_right", "lung_lower_lobe_left"},
               str(rel))
        import inspect as _insp
        _src = _insp.getsource(E.separar_derrame_por_lado)
        _alvo = u"            masks[nome] = novo\n"
        checar(u"  (isca) o desconto esta onde a isca o procura",
               _src.count(_alvo) == 1)
        _ns = dict(vars(E))
        exec(compile(_src.replace(_alvo, u"            pass\n"),
                     "<isca-derrame>", "exec"), _ns)
        m2 = {"lung_lower_lobe_right": lobo_d.copy(),
              "lung_lower_lobe_left": lobo_e.copy(),
              "pleural_effusion": der.copy()}
        _ns["separar_derrame_por_lado"](m2, grade)
        checar(u"ISCA: sem o desconto, o lobo fica com o derrame dentro",
               bool((m2["lung_lower_lobe_right"] & der).any()))
    finally:
        shutil.rmtree(base, ignore_errors=True)


def teste_os_orgaos_do_motor_do_cranio_chegam_ao_oar():
    secao(u"o tronco e o quiasma do motor do encefalo chegam ao FULL e ao OAR")
    base = tempfile.mkdtemp(prefix="radai_t_fulloar_")
    try:
        serie = _serie(base)
        tronco = np.zeros((Z, Y, X), bool)
        tronco[18:26, 56:66, 58:68] = True
        quiasma = np.zeros((Z, Y, X), bool)
        quiasma[22:24, 50:53, 58:68] = True
        extras = {"orgaos": {"brain_brainstem": tronco,
                             "optic_chiasm": quiasma},
                  "alvos": {}, "observacoes": {},
                  "origem": {"brain_brainstem": "cranio_ct",
                             "optic_chiasm": "cranio_ct"}}
        sd, r, linhas, _d = _rodar(base, serie, _cruas(com_plugins=False),
                                   extras=extras)
        full = set(_rois(pydicom.dcmread(r["full"]))[0].values())
        oar = set(_rois(pydicom.dcmread(r["oar"]))[0].values())
        tem = lambda conj, p: any(n.lower().startswith(p) for n in conj)
        checar(u"o tronco esta no FULL e no OAR",
               tem(full, "brainstem") and tem(oar, "brainstem"),
               u"%s | %s" % (sorted(full), sorted(oar)))
        checar(u"o quiasma esta no FULL e no OAR",
               tem(full, "opticchiasm") and tem(oar, "opticchiasm"),
               u"%s" % sorted(oar))
        sd2, r2, _l2, _d2 = _rodar(base, serie, _cruas(com_plugins=False))
        oar2 = set(_rois(pydicom.dcmread(r2["oar"]))[0].values())
        checar(u"isca: sem os extras, nem tronco nem quiasma",
               not tem(oar2, "brainstem") and not tem(oar2, "opticchiasm"),
               u"%s" % sorted(oar2))
    finally:
        shutil.rmtree(base, ignore_errors=True)


def _pelve_obliqua(alfa=35.0):
    import radai_geom
    g = radai_geom.Grade((3.0, 1.0, 1.0))
    forma = (40, 120, 80)
    zz, yy, xx = np.mgrid[0:forma[0], 0:forma[1], 0:forma[2]]
    zmm, ymm = zz * 3.0, yy * 1.0
    tg = np.tan(np.radians(alfa))
    sacro = ((xx >= 25) & (xx <= 55) & (yy >= 70) & (yy <= 105)
             & (zz >= 5) & (zmm <= 75.0 + (ymm - 70.0) * tg))
    tubo = (xx >= 35) & (xx <= 45) & (yy >= 55) & (yy <= 65) & (zz <= 20)
    alca = (xx >= 30) & (xx <= 50) & (yy >= 10) & (yy <= 25) \
        & (zz >= 15) & (zz <= 20)
    ponte = (xx >= 37) & (xx <= 43) & (yy >= 25) & (yy <= 55) \
        & (zz >= 15) & (zz <= 17)
    return g, {"sacrum": sacro}, tubo, alca, ponte


def teste_o_reto_pelo_plato_do_sacro():
    secao(u"o reto: abaixo do plano axial E do plano do plato do sacro (v8.4)")
    checar(u"a derivacao do colon declara o plano do plato do sacro",
           E.DERIVADAS["colon"].get("plano_do_sacro") == "rectum")
    checar(u"  e o FAST guarda o sacro e a S1 como insumo",
           set(E.PLATO_DO_SACRO) <= set(E.insumos_das_derivadas()))
    g, masks, tubo, alca, ponte = _pelve_obliqua(35.0)
    plano, motivo = E.plano_do_plato_do_sacro(masks, g)
    checar(u"a inclinacao do plato e medida no sacro da serie (35 graus)",
           plano is not None and abs(plano["alfa_graus"] - 35.0) < 6.0,
           str(plano or motivo))
    reto = tubo | alca | ponte
    linhas = []
    final, dev, info = E.limitar_reto_pelo_plato(reto, masks, g,
                                                 log=linhas.append)
    checar(u"a alca anterior sai do reto", not (final & alca).any(),
           u"%d voxels" % int((final & alca).sum()))
    checar(u"  e o reto colado ao sacro fica inteiro", not (tubo & ~final).any(),
           u"%d voxels" % int((tubo & ~final).sum()))
    checar(u"  e o que saiu volta ao colon (reto + devolvido = o de antes)",
           np.array_equal(final | dev, reto) and not (final & dev).any())
    from scipy import ndimage
    checar(u"  e o reto e um volume so", int(ndimage.label(final)[1]) == 1)
    checar(u"  e o log diz a inclinacao e os volumes",
           any(l.startswith(u"reto: plano do plato do sacro (inclinacao")
               for l in linhas), str(linhas[:2]))
    velho = E.INCLINACAO_DO_PLATO_GRAUS
    E.INCLINACAO_DO_PLATO_GRAUS = (80.0, 89.0)
    try:
        f2, _d2, i2 = E.limitar_reto_pelo_plato(reto, masks, g)
    finally:
        E.INCLINACAO_DO_PLATO_GRAUS = velho
    checar(u"ISCA: sem o plano do plato a alca anterior continua no reto",
           bool((f2 & alca).any()) and not i2.get("plano"))
    gp, mp, tp, ap, pp = _pelve_obliqua(0.0)
    l3 = []
    f3, d3, i3 = E.limitar_reto_pelo_plato(tp | ap | pp, mp, gp,
                                           log=l3.append)
    checar(u"sacro sem inclinacao: o reto fica como veio, e o log diz",
           np.array_equal(f3, tp | ap | pp) and not d3.any()
           and any(u"nao usado" in l for l in l3), str(l3[:1]))


def teste_o_oar_e_gravado_antes_e_o_full_pode_faltar():
    secao(u"v8.5: o OAR e gravado antes do FULL; sem o FULL, a serie e parcial")
    base = tempfile.mkdtemp(prefix="radai_t_fulloar_")
    velho = RO.Saida._gravar_arquivo
    ordem = []

    def _anota(self, rt_local, alvo):
        ordem.append(os.path.basename(alvo))
        return velho(self, rt_local, alvo)

    def _sem_full(self, rt_local, alvo):
        if os.path.basename(alvo).startswith("RS_RadAI_FULL_"):
            raise OSError("disco cheio (isca)")
        return velho(self, rt_local, alvo)
    try:
        serie = _serie(base)
        RO.Saida._gravar_arquivo = _anota
        try:
            _sd, r, _l, dest = _rodar(base, serie)
        finally:
            RO.Saida._gravar_arquivo = velho
        checar(u"o OAR sai primeiro, depois o FULL",
               len(ordem) == 2 and not ordem[0].startswith("RS_RadAI_FULL_")
               and ordem[1].startswith("RS_RadAI_FULL_"), str(ordem))
        checar(u"  e a serie inteira nao e parcial", r.get("parcial") is None)
        RO.Saida._gravar_arquivo = _sem_full
        try:
            sd2, r2, l2, dest2 = _rodar(base, serie)
        finally:
            RO.Saida._gravar_arquivo = velho
        arquivos = sorted(os.listdir(dest2))
        checar(u"sem o FULL o OAR fica, inteiro, e nao ha arquivo pela metade",
               r2.get("oar") and os.path.isfile(r2["oar"])
               and r2.get("full") is None
               and not [a for a in arquivos if a.startswith("RS_RadAI_FULL_")
                        or ".parcial" in a], str(arquivos))
        checar(u"  e a serie conta como parcial, com o motivo",
               (r2.get("parcial") or {}).get("conjunto") == "full"
               and u"disco cheio" in (r2.get("parcial") or {}).get("motivo",
                                                                     u"")
               and any(u"SERIE PARCIAL" in l for l in l2),
               str(r2.get("parcial")))
        checar(u"  e o registro do que foi gravado diz so o OAR",
               "oar" in sd2.gravados and "full" not in sd2.gravados,
               str(sd2.gravados))

        def _sem_oar(self, rt_local, alvo):
            if not os.path.basename(alvo).startswith("RS_RadAI_FULL_"):
                raise OSError("disco cheio (isca)")
            return velho(self, rt_local, alvo)
        RO.Saida._gravar_arquivo = _sem_oar
        try:
            try:
                _rodar(base, serie)
                levantou = False
            except RuntimeError:
                levantou = True
        finally:
            RO.Saida._gravar_arquivo = velho
        checar(u"ISCA: sem o OAR (o entregue) a serie falha: so o FULL pode "
               u"faltar", levantou)

        velho_salva = E._salvar_sem_escrever_no_console
        velho_sel = E.selecionar_do_full

        def _sem_memoria_no_full(rt, caminho):
            if not os.path.basename(os.path.dirname(str(caminho))).startswith(
                    E.PREFIXO_TEMP_DO_OAR):
                raise MemoryError()
            return velho_salva(rt, caminho)
        E._salvar_sem_escrever_no_console = _sem_memoria_no_full
        try:
            sd3, r3, l3, dest3 = _rodar(base, serie)
        finally:
            E._salvar_sem_escrever_no_console = velho_salva
        arquivos3 = sorted(os.listdir(dest3))
        checar(u"o FULL que estoura a memoria ao virar contorno (o caso de "
               u"campo) deixa o OAR gravado, inteiro, e a serie parcial com "
               u"o motivo",
               r3.get("oar") and os.path.isfile(r3["oar"])
               and r3.get("full") is None
               and (r3.get("parcial") or {}).get("conjunto") == "full"
               and u"MemoryError" in (r3.get("parcial") or {}).get("motivo",
                                                                     u"")
               and not [a for a in arquivos3
                        if a.startswith("RS_RadAI_FULL_")],
               u"%s | %s" % (arquivos3, r3.get("parcial")))
        if r3.get("oar") and os.path.isfile(r3["oar"]):
            oar3 = pydicom.dcmread(r3["oar"])
            checar(u"  e o OAR abre, com as estruturas do entregue",
                   len(oar3.StructureSetROISequence)
                   == len(r3["estruturas"]) > 0,
                   u"%d x %d" % (len(oar3.StructureSetROISequence),
                                 len(r3["estruturas"])))

        def _full_antes_do_oar(preparo, *a, **k):
            preparo.gravar()
            return velho_sel(preparo, *a, **k)
        antes4 = set(os.listdir(base))
        E._salvar_sem_escrever_no_console = _sem_memoria_no_full
        E.selecionar_do_full = _full_antes_do_oar
        try:
            try:
                _rodar(base, serie)
                levantou4 = False
            except RuntimeError:
                levantou4 = True
        finally:
            E._salvar_sem_escrever_no_console = velho_salva
            E.selecionar_do_full = velho_sel
        sobra4 = [a for d in sorted(set(os.listdir(base)) - antes4)
                  for a in os.listdir(os.path.join(base, d))
                  if a.startswith("RS_RadAI")]
        checar(u"ISCA: com o FULL montado antes do OAR (a ordem de antes), a "
               u"mesma falha derruba a serie e nao deixa arquivo nenhum",
               levantou4 and not sobra4, str(sobra4))
    finally:
        RO.Saida._gravar_arquivo = velho
        shutil.rmtree(base, ignore_errors=True)


def _oar_pelo_caminho_de_antes(rt_full, mapa_nomes, permitidos, meta, pasta):
    ds = pydicom.dcmread(str(rt_full))
    permitidos = set(permitidos or ())
    por_nome = dict((str(v), k) for k, v in (mapa_nomes or {}).items())
    ficam_num, ficam = set(), {}
    for roi in getattr(ds, "StructureSetROISequence", []):
        nome_roi = str(getattr(roi, "ROIName", ""))
        chave = por_nome.get(nome_roi, nome_roi)
        if chave in permitidos and not str(chave).startswith("_"):
            ficam_num.add(int(roi.ROINumber))
            ficam[chave] = nome_roi
    ds.StructureSetROISequence = pydicom.Sequence(
        [r for r in ds.StructureSetROISequence
         if int(r.ROINumber) in ficam_num])
    for r in ds.StructureSetROISequence:
        r.ROIDescription = RS.descricao_da_roi(str(r.ROIName))
    ds.ROIContourSequence = pydicom.Sequence(
        [r for r in ds.ROIContourSequence
         if int(getattr(r, "ReferencedROINumber", -1)) in ficam_num])
    ds.RTROIObservationsSequence = pydicom.Sequence(
        [r for r in ds.RTROIObservationsSequence
         if int(getattr(r, "ReferencedROINumber", -1)) in ficam_num])
    m = dict(meta or {})
    susp = [s for s in (m.get("suspeitas") or []) if s[0] in set(ficam)]
    txt = E._textos_do_conjunto(None, m.get("versao_worker", ""),
                                bool(m.get("tem_nv")), m.get("sufixo"), susp,
                                m.get("suavizadas", 0),
                                m.get("suavizar_mm", 0.0))
    for campo, valor in txt.items():
        setattr(ds, campo, valor)
    ds.ApprovalStatus = "UNAPPROVED"
    destino = os.path.join(pasta, "oar_de_antes_%d.dcm" % len(os.listdir(pasta)))
    E.gravar_rtstruct(ds, destino)
    return destino


def teste_o_study_vazio_da_rm_grava_o_full_e_a_serie_fica_pronta():
    secao(u"a RM so com o Brain_ai: o STUDY sai vazio, o FULL e gravado e a "
          u"serie fica pronta")
    import SimpleITK as sitk
    import radai_batch as L
    base = tempfile.mkdtemp(prefix="radai_t_fulloar_")
    try:
        serie = _serie(base)
        vol = sitk.GetArrayFromImage(E.load_sitk(serie))
        lab = np.zeros((Z, Y, X), np.int16)
        lab[8:22, 40:90, 40:90] = 1
        cruas = {"total_mr": E.MasksCruas(lab, {1: "brain"})}

        def _rodar_mod(mod):
            linhas = []
            dest = os.path.join(base, "saida_%s" % mod)
            os.makedirs(dest)
            sd = RO.Saida(E, serie, dest, "RS_RadAI_20260924_1a2b3c4d.dcm",
                          tasks=["total_mr"], versao="bateria",
                          suavizar_mm=1.5, log=lambda m: linhas.append(str(m)),
                          modalidade=mod)
            erro = None
            r = {}
            try:
                r = sd.full_e_oar(dict(cruas), volume_hu=vol) or {}
            except Exception as e:
                erro = e
            return sd, r, linhas, dest, erro
        sd, r, linhas, dest, erro = _rodar_mod("MR")
        checar(u"a serie NAO falha (a entrega nao levanta)", erro is None,
               repr(erro)[:300])
        arqs = sorted(a for a in os.listdir(dest) if a.endswith(".dcm"))
        checar(u"  o FULL e gravado, com o Brain_ai, e nenhum STUDY",
               arqs and all(a.startswith("RS_RadAI_FULL_") for a in arqs)
               and "Brain_ai" in (r.get("estruturas_full") or []),
               u"%s | %s" % (arqs, r.get("estruturas_full")))
        checar(u"  `gravados` diz so `full`, e o resultado diz o STUDY vazio",
               sd.gravados == ["full"] and r.get("oar") is None
               and r.get("study_vazio") and r.get("estruturas") == []
               and r.get("entregue") == r.get("full"),
               str((sd.gravados, r.get("study_vazio"), r.get("entregue"))))
        checar(u"  e uma linha no log diz que o STUDY saiu vazio",
               any(l.startswith(u"STUDY: saiu vazio") for l in linhas),
               u" | ".join(l for l in linhas if u"STUDY" in l)[:300])
        try:
            conferidos = L.exigir_rtstruct_no_disco(sd)
        except Exception as e:
            conferidos = repr(e)
        checar(u"o portao do marcador de pronta (RTSTRUCT no disco) passa com "
               u"o FULL: a serie e marcada pronta", conferidos == ["full"],
               str(conferidos)[:200])
        sd2, r2, l2, dest2, erro2 = _rodar_mod("CT")
        checar(u"(isca) a mesma mascara na TC leva o Brain_ai ao STUDY: o vazio "
               u"vem da regra da RM, e o fantoma exercita o ramo",
               erro2 is None and "Brain_ai" in (r2.get("estruturas") or [])
               and "oar" in sd2.gravados and not r2.get("study_vazio"),
               str((repr(erro2)[:120], r2.get("estruturas"))))
    finally:
        shutil.rmtree(base, ignore_errors=True)


def teste_o_oar_sai_igual_ao_caminho_de_antes():
    secao(u"v8.5: o OAR gravado das mascaras, antes do FULL, sai igual ao de "
          u"antes (a selecao relida do arquivo do FULL)")
    import copy
    base = tempfile.mkdtemp(prefix="radai_t_fulloar_")
    velho = E.build_rtstruct
    pedido = {}

    def _espia(stage, masks, **kw):
        if kw.get("rotulo") == "RadAI_FULL" and "kw" not in pedido:
            pedido["stage"] = stage
            pedido["masks"] = dict((k, np.array(masks[k], copy=True))
                                   for k in masks)
            pedido["kw"] = copy.deepcopy(dict(
                (k, v) for k, v in kw.items() if k not in ("log", "adiar")))
        return velho(stage, masks, **kw)

    def _de_antes():
        kw = copy.deepcopy(pedido["kw"])
        meta = kw.get("meta")
        if not isinstance(meta, dict):
            meta = {}
            kw["meta"] = meta
        rt_full, nomes_full = velho(pedido["stage"], copy.deepcopy(
            pedido["masks"]), **kw)
        m_oar = dict(meta)
        m_oar["versao_worker"] = "bateria " + RS.POR_COD["oar"]["nome"]
        oar = _oar_pelo_caminho_de_antes(rt_full, nomes_full, kw["selecao"],
                                         m_oar, base)
        return rt_full, oar

    def _comparar(r):
        rt_full, antigo = _de_antes()
        try:
            dif_full = _diferencas(pydicom.dcmread(rt_full),
                                   pydicom.dcmread(r["full"]))
        finally:
            shutil.rmtree(os.path.dirname(rt_full), ignore_errors=True)
        a = pydicom.dcmread(antigo)
        b = pydicom.dcmread(r["oar"])
        return dif_full, _diferencas(a, b), a, b
    try:
        serie = _serie(base)
        niv, _viii = _cervicais_do_pescoco()
        for rot, kw_cena in ((u"torax", {}),
                             (u"pescoco com os niveis e as parotidas do VIII",
                              {"cruas": _cruas_do_pescoco(),
                               "cervicais": niv})):
            pedido.clear()
            E.build_rtstruct = _espia
            try:
                sd, r, linhas, dest = _rodar(base, serie, **kw_cena)
            finally:
                E.build_rtstruct = velho
            if not checar(u"%s: (o pedido do FULL foi capturado)" % rot,
                          "kw" in pedido):
                return
            dif_full, dif, a, b = _comparar(r)
            checar(u"%s: o OAR de agora e o de antes, nenhum elemento "
                   u"diferente (fora UID e hora) — as mesmas ROIs, nomes, "
                   u"numeros, cores, descricoes e contornos, na mesma ordem "
                   u"(%d ROIs)" % (rot, len(b.StructureSetROISequence)),
                   not dif and len(b.StructureSetROISequence) >= 10,
                   u"; ".join(dif[:4]))
            checar(u"  e o FULL de agora e o de antes, igual",
                   not dif_full, u"; ".join(dif_full[:4]))
        c = b.ROIContourSequence[0].ContourSequence[0]
        v = [str(x) for x in c.ContourData]
        v[0] = "%.4f" % (float(v[0]) + 0.0001)
        c.ContourData = v
        checar(u"  (isca) um ponto mexido de 0,0001 mm no OAR e acusado",
               bool(_diferencas(a, b)))
        velho_num = E._renumerar_pelo_plano
        pedido.clear()
        E._renumerar_pelo_plano = lambda ds, numeros: 0
        E.build_rtstruct = _espia
        bloqueada = None
        try:
            _sd2, r2, _l2, _d2 = _rodar(base, serie)
        except RuntimeError as erro:
            if "o RTSTRUCT nao preservou o acabamento terminal na rasterizacao" not in str(erro):
                raise
            bloqueada = str(erro)
        finally:
            E._renumerar_pelo_plano = velho_num
            E.build_rtstruct = velho
        if bloqueada:
            checar(u"ISCA: sem renumeracao, a guarda terminal bloqueia o DICOM inconsistente",
                   "o RTSTRUCT nao preservou o acabamento terminal na rasterizacao" in bloqueada,
                   bloqueada)
        else:
            _df, dif2, _a, _b = _comparar(r2)
            checar(u"ISCA: sem o numero do plano, o OAR sai com outros numeros de "
                   u"ROI e a comparacao reprova",
                   any(u"ROINumber" in d or u"ObservationNumber" in d
                        for d in dif2), u"; ".join(dif2[:3]))
    finally:
        E.build_rtstruct = velho
        shutil.rmtree(base, ignore_errors=True)


def teste_a_gravacao_nao_guarda_duas_copias():
    secao(u"v8.5: o objeto do rt_utils morre antes da releitura, e o FULL e "
          u"lido uma vez")
    import inspect as _insp
    import weakref
    base = tempfile.mkdtemp(prefix="radai_t_fulloar_")
    velho_salva = E._salvar_sem_escrever_no_console
    velho_le = pydicom.dcmread
    vivos, lidos = [], []

    def _salva(rt, caminho):
        vivos.append(weakref.ref(rt))
        return velho_salva(rt, caminho)

    def _le(arq, *a, **k):
        if str(arq).endswith("RS.dcm"):
            lidos.append((str(arq), vivos[-1]() is None if vivos else None))
        return velho_le(arq, *a, **k)

    def _uma(build=None):
        del vivos[:]
        del lidos[:]
        velho_b = E.build_rtstruct
        E._salvar_sem_escrever_no_console = _salva
        pydicom.dcmread = _le
        if build is not None:
            E.build_rtstruct = build
        try:
            sd_, r_, _l, _d = _rodar(base, serie)
        finally:
            E._salvar_sem_escrever_no_console = velho_salva
            pydicom.dcmread = velho_le
            E.build_rtstruct = velho_b
        return r_
    try:
        serie = _serie(base)
        r = _uma()
        do_oar = [x for x in lidos if os.path.basename(os.path.dirname(
            x[0])).startswith(E.PREFIXO_TEMP_DO_OAR)]
        do_full = [x for x in lidos if x not in do_oar]
        checar(u"cada RTSTRUCT montado e relido UMA vez: o OAR uma, o FULL "
               u"uma (antes, o FULL era lido de novo para tirar o OAR)",
               len(do_oar) == 1 and len(do_full) == 1
               and len(set(p for p, _m in do_full)) == 1,
               u"OAR %d, FULL %d" % (len(do_oar), len(do_full)))
        checar(u"  e o objeto do rt_utils ja morreu quando o arquivo e relido",
               lidos and all(m is True for _p, m in lidos), str(lidos))
        src = _insp.getsource(E.build_rtstruct)
        de = u"        del rt\n"
        ns = dict(vars(E))
        exec(compile(src.replace(de, u"        pass\n"), "<isca-del-rt>",
                     "exec"), ns)
        ns["_salvar_sem_escrever_no_console"] = _salva
        _uma(ns["build_rtstruct"])
        checar(u"ISCA: sem o `del rt`, o objeto do rt_utils esta vivo na "
               u"releitura (as duas copias de antes)",
               src.count(de) == 1 and lidos
               and any(m is False for _p, m in lidos), str(lidos))
    finally:
        E._salvar_sem_escrever_no_console = velho_salva
        pydicom.dcmread = velho_le
        shutil.rmtree(base, ignore_errors=True)


def teste_as_carotidas_ficam_so_no_full():
    secao(u"as carotidas entram nas grandes arterias e continuam "
          u"separadas no FULL")
    checar(u"o composto dos grandes vasos leva as carotidas bilaterais",
           all(p in E.COMPOSTOS["great_arteries"] for p in (
               "common_carotid_artery_left", "common_carotid_artery_right",
               "internal_carotid_artery_left", "internal_carotid_artery_right")),
           str(E.COMPOSTOS["great_arteries"]))
    base = tempfile.mkdtemp(prefix="radai_t_fulloar_")
    velho_ga = list(E.COMPOSTOS["great_arteries"])

    def _cruas_com_carotidas():
        cruas = _cruas(extra=(("common_carotid_artery_left",
                               (20, 28, 66, 70, 68, 72)),))
        hbv = np.zeros((Z, Y, X), np.int16)
        hbv[22:29, 66:70, 76:80] = 1
        cruas["headneck_bones_vessels"] = E.MasksCruas(
            hbv, {1: "internal_carotid_artery_left"})
        return cruas

    def _medir(sd_):
        mf = sd_.meta_do_full["mascaras"]
        ga = np.asarray(mf.get("great_arteries", np.zeros((Z, Y, X))), bool)
        ci = np.asarray(mf.get("internal_carotid_artery_left",
                               np.zeros((Z, Y, X))), bool)
        cc = np.asarray(mf.get("common_carotid_artery_left",
                               np.zeros((Z, Y, X))), bool)
        return ga, ci, cc
    try:
        serie = _serie(base)
        sd, r, linhas, dest = _rodar(base, serie, cruas=_cruas_com_carotidas())
        ga, ci, cc = _medir(sd)
        checar(u"o GreatArteries_ai (o mesmo no FULL e no OAR) inclui "
               u"as carotidas", ga.any() and ci.any() and cc.any()
               and not ((ci | cc) & ~ga).any(),
               u"interna %d vx, comum %d vx, em comum %d vx"
               % (int(ci.sum()), int(cc.sum()), int((ga & (ci | cc)).sum())))
        full = set(r["estruturas_full"])
        checar(u"as carotidas continuam no FULL, cada uma com o seu nome",
               E.nome_clinico("internal_carotid_artery_left") in full
               and any(n.startswith("A_Carotid") and "Int" not in n
                       for n in full), str(sorted(n for n in full
                                                 if "arotid" in n)))
        checar(u"  e nenhuma vai ao OAR",
               not [n for n in r["estruturas"] if "arotid" in n]
               and "GreatArteries_ai" in r["estruturas"],
               str(sorted(r["estruturas"])))
        E.COMPOSTOS["great_arteries"] = [
            p for p in velho_ga if "carotid" not in p]
        try:
            sd_i, _r, _l, _d = _rodar(base, serie,
                                      cruas=_cruas_com_carotidas())
        finally:
            E.COMPOSTOS["great_arteries"] = velho_ga
        ga_i, ci_i, _cc = _medir(sd_i)
        checar(u"ISCA: sem a carotida interna no composto, ela desaparece "
               u"do GreatArteries_ai do STUDY", not (ga_i & ci_i).any())
    finally:
        E.COMPOSTOS["great_arteries"] = velho_ga
        shutil.rmtree(base, ignore_errors=True)


_PESCOCO_DE_UM_PIXEL = ("###......", "###......", "##.......", "##.......",
                        ".#....###", "####..###", "####..###", "#########")


def _desenho(fatia, linhas, y0, x0):
    d = np.array([[c == "#" for c in l] for l in linhas])
    fatia[y0:y0 + d.shape[0], x0:x0 + d.shape[1]] |= d


def _cruas_com_contornos_ruins():
    cruas = _cruas(com_plugins=False)
    lab = np.zeros((Z, Y, X), np.int16)
    idx = {}
    for i, (nome, (z0, z1, y0, y1, x0, x1)) in enumerate(_TOTAL, start=1):
        if nome != "small_bowel":
            lab[z0:z1, y0:y1, x0:x1] = i
        idx[i] = nome
    k_delgado = [i for i, n in idx.items() if n == "small_bowel"][0]
    k_tira, k_laco = len(idx) + 1, len(idx) + 2
    idx[k_tira], idx[k_laco] = "gallbladder", "pancreas"
    for z in range(1, 12):
        pesc = np.zeros((Y, X), bool)
        _desenho(pesc, _PESCOCO_DE_UM_PIXEL, 60, 100)
        lab[z][pesc] = k_delgado
        lab[z, 75, 100] = lab[z, 75, 101] = k_tira
        lab[z, 76, 102] = k_tira
        for yy, xx in ((85, 100), (85, 101), (86, 102), (87, 102),
                       (88, 101)):
            lab[z, yy, xx] = k_laco
    cruas["total_v3"] = E.MasksCruas(lab, idx)
    return cruas


def _defeitos_de_contorno(caminho):
    ds = pydicom.dcmread(caminho)
    area0 = repetido = cruza = 0
    for rc in getattr(ds, "ROIContourSequence", []):
        for c in getattr(rc, "ContourSequence", []):
            p = np.asarray([float(v) for v in c.ContourData]).reshape(-1, 3)
            xy = p[:, :2]
            n = len(xy)
            x, y = xy[:, 0], xy[:, 1]
            if abs(0.5 * (np.dot(x, np.roll(y, -1))
                          - np.dot(y, np.roll(x, -1)))) < 0.01:
                area0 += 1
            if n > 1 and (np.abs(np.diff(xy, axis=0)).max(axis=1)
                          < 1e-4).any():
                repetido += 1
            if n < 4:
                continue
            a, b = xy, np.roll(xy, -1, axis=0)
            i, j = np.triu_indices(n, 2)
            fora = (i == 0) & (j == n - 1)
            i, j = i[~fora], j[~fora]

            def giro(p1, p2, p3):
                return ((p2[:, 0] - p1[:, 0]) * (p3[:, 1] - p1[:, 1])
                        - (p2[:, 1] - p1[:, 1]) * (p3[:, 0] - p1[:, 0]))
            o1, o2 = giro(a[i], b[i], a[j]), giro(a[i], b[i], b[j])
            o3, o4 = giro(a[j], b[j], a[i]), giro(a[j], b[j], b[i])
            nulo = ((np.abs(o1) < 1e-9) | (np.abs(o2) < 1e-9)
                    | (np.abs(o3) < 1e-9) | (np.abs(o4) < 1e-9))
            if np.any((o1 * o2 < 0) & (o3 * o4 < 0) & ~nulo):
                cruza += 1
    return area0, repetido, cruza


def teste_o_entregue_nao_tem_contorno_degenerado_nem_cruzado():
    secao(u"o RTSTRUCT entregue sai sem contorno de area nula, vertice "
          u"repetido ou cruzamento proprio (o diagnostico do MOSAIQ)")
    base = tempfile.mkdtemp(prefix="radai_t_fulloar_")
    velho_tps = os.environ.get("RADAI_TPS_DESTINO")

    def _medir(tps, modo, isca=False):
        os.environ["RADAI_TPS_DESTINO"] = tps
        guardados = (E.acabar_contornos, E.contorno_degenerado)
        try:
            if isca:
                E.acabar_contornos = lambda ds, *a, **k: {}
                E.contorno_degenerado = lambda p: False
            serie = _serie(base)
            sd, r, linhas, dest = _rodar(
                base, serie, cruas=_cruas_com_contornos_ruins(), modo=modo)
        finally:
            E.acabar_contornos, E.contorno_degenerado = guardados
        chave = "oar_fast" if modo == "fast" else "oar"
        return _defeitos_de_contorno(r[chave]), linhas, r
    try:
        for tps in ("eclipse", "monaco"):
            for modo in ("fast", "auto"):
                (a0, rep, cr), linhas, r = _medir(tps, modo)
                checar(u"%s %s: 0 contorno de area nula, 0 com vertice "
                       u"repetido e 0 que cruza a si mesmo no entregue"
                       % (tps, modo), (a0, rep, cr) == (0, 0, 0),
                       u"area nula %d, repetido %d, cruza %d" % (a0, rep, cr))
                if modo == "auto":
                    checar(u"%s auto: o FULL tambem" % tps,
                           _defeitos_de_contorno(r["full"]) == (0, 0, 0),
                           str(_defeitos_de_contorno(r["full"])))
                checar(u"%s %s: o log diz o acabamento dos contornos"
                       % (tps, modo), any(u"contornos (meio pixel, Taubin)" in l
                                          for l in linhas),
                       str([l for l in linhas if u"acabamento" in l][:2]))
        (a0, rep, cr), _l, _r = _medir("eclipse", "auto", isca=True)
        checar(u"ISCA: com a reparacao de antes (so n < 3) o entregue tem "
               u"area nula ou cruzamento", a0 > 0 or cr > 0,
               u"area nula %d, cruza %d" % (a0, cr))
        ds = pydicom.Dataset()
        rc = pydicom.Dataset()
        c = pydicom.Dataset()
        c.ContourData = [0, 0, 5, 3.1, 1.6, 5, 1.55, 0.8, 5, 3.1, 1.6, 5]
        c.NumberOfContourPoints = 4
        rc.ContourSequence = pydicom.Sequence([c])
        ds.ROIContourSequence = pydicom.Sequence([rc])
        l_ = E.acabar_contornos(ds, {}, (0.78, 0.78))
        _pc = np.asarray([float(v) for v in c.ContourData]).reshape(-1, 3)
        checar(u"o contorno do log da clinica (4 pontos, 3 distintos, "
               u"colineares) vira o contorno dos pixels, sem sumir",
               l_.get("degenerados") == 1
               and int(c.NumberOfContourPoints) == len(_pc)
               and not E.contorno_degenerado(_pc)
               and not E.cruza_a_si_mesmo(_pc)
               and abs(E._area_assinada(_pc[:, :2])) > 1.0,
               str(list(c.ContourData)))
    finally:
        if velho_tps is None:
            os.environ.pop("RADAI_TPS_DESTINO", None)
        else:
            os.environ["RADAI_TPS_DESTINO"] = velho_tps
        shutil.rmtree(base, ignore_errors=True)


_CONSTRITORES = (("superior_pharyngeal_constrictor", range(20, 27)),
                 ("middle_pharyngeal_constrictor", range(14, 20)),
                 ("inferior_pharyngeal_constrictor", range(8, 14)))


def _cruas_com_constritores_finos():
    cruas = _cruas_do_pescoco()
    yy, xx = np.mgrid[0:Y, 0:X]
    r = np.sqrt((yy - 100) ** 2 + (xx - 64) ** 2)
    arco = (r >= 6) & (r < 7) & (yy >= 98)
    lab = np.zeros((Z, Y, X), np.int16)
    idx = {}
    entrada = {}
    for k, (nome, zs) in enumerate(_CONSTRITORES, start=1):
        idx[k] = nome
        for z in zs:
            lab[z][arco] = k
    lab[22:24, 104:109, 62:67] = 1
    idx[4], idx[5] = "sternocleidomastoid_left", "sternocleidomastoid_right"
    lab[18:26, 28:34, 70:84] = 4
    lab[18:26, 28:34, 44:58] = 5
    for k, (nome, zs) in enumerate(_CONSTRITORES, start=1):
        entrada[nome] = lab == k
    cruas["headneck_muscles"] = E.MasksCruas(lab, idx)
    return cruas, entrada


def _cortes_e_areas(caminho, prefixo):
    ds = pydicom.dcmread(caminho)
    nomes = dict((int(x.ROINumber), str(x.ROIName))
                 for x in ds.StructureSetROISequence)
    fora = {}
    for rc in ds.ROIContourSequence:
        n = nomes.get(int(rc.ReferencedROINumber), "")
        if not n.startswith(prefixo):
            continue
        for c in rc.ContourSequence:
            p = np.asarray([float(v) for v in c.ContourData]).reshape(-1, 3)
            x, y = p[:, 0], p[:, 1]
            a = abs(0.5 * (np.dot(x, np.roll(y, -1))
                           - np.dot(y, np.roll(x, -1))))
            z = int(round(float(p[0, 2]) / 3.0))
            fora.setdefault(n, {})[z] = fora.get(n, {}).get(z, 0.0) + a
    return fora


def teste_os_constritores_finos_nao_somem():
    secao(u"os constritores da faringe, finos, nao somem: cada corte do "
          u"modelo chega ao entregue com area")
    base = tempfile.mkdtemp(prefix="radai_t_fulloar_")

    def _rodar_constr(modo, isca=False, isca_suav=False):
        guardados = (dict(E.SUAVIZACAO), E.contorno_degenerado)
        try:
            if isca or isca_suav:
                for k in ("pharyngeal_constrictor_superior",
                          "pharyngeal_constrictor_middle",
                          "pharyngeal_constrictor_inferior"):
                    E.SUAVIZACAO[k] = E._S_AR
            if isca:
                E.contorno_degenerado = (
                    lambda p: len(np.asarray(p)) < E.MIN_PONTOS_CONTORNO)
            serie = _serie(base)
            cruas, entrada = _cruas_com_constritores_finos()
            sd, r, linhas, dest = _rodar(base, serie, cruas=cruas, modo=modo,
                                         suavizar_mm=6.0)
        finally:
            E.SUAVIZACAO.clear()
            E.SUAVIZACAO.update(guardados[0])
            E.contorno_degenerado = guardados[1]
        meta = sd.meta_do_fast if modo == "fast" else sd.meta_do_full
        arq = r["oar_fast"] if modo == "fast" else r["oar"]
        return _cortes_e_areas(arq, "Musc_Constr"), meta, entrada
    try:
        px = 2.0 * 2.0
        for modo in ("auto", "fast"):
            cortes, meta, entrada = _rodar_constr(modo)
            mf = meta.get("mascaras") or {}
            for nome, zs in _CONSTRITORES:
                chave = "pharyngeal_constrictor_" + nome.split("_")[0]
                roi = [n for n in cortes if n.startswith(
                    "Musc_Constr_" + nome[0].upper())]
                por_z = cortes.get(roi[0], {}) if roi else {}
                checar(u"%s %s: um contorno em cada um dos %d cortes do "
                       u"modelo" % (modo, chave, len(zs)),
                       sorted(por_z) == list(zs), str(sorted(por_z)))
                checar(u"%s %s:   e cada corte com area de ao menos os "
                       u"pixels do arco" % (modo, chave),
                       por_z and min(por_z.values()) >= 0.8 * px * int(
                           entrada[nome][list(zs)[0]].sum()),
                       u"%.1f mm2" % (min(por_z.values()) if por_z else 0))
                checar(u"%s %s:   e a mascara e a do modelo, sem suavizar"
                       % (modo, chave), chave in mf and np.array_equal(
                           np.asarray(mf[chave], bool), entrada[nome]))
        checar(u"os constritores, os nervos opticos e o quiasma estao na "
               u"lista das estruturas delgadas, com suavizacao zero",
               set(E.ESTRUTURAS_DELGADAS) >= {
                   "optic_nerve_left", "optic_nerve_right", "optic_chiasm",
                   "pharyngeal_constrictor_superior",
                   "pharyngeal_constrictor_middle",
                   "pharyngeal_constrictor_inferior"}
               and all(E.suavizacao_de(k, 1.5) == 0.0
                       for k in E.ESTRUTURAS_DELGADAS))
        cortes_i, meta_i, entrada_i = _rodar_constr("auto", isca=True)
        sup = [n for n in cortes_i if n.startswith("Musc_Constr_S")]
        por_z_i = cortes_i.get(sup[0], {}) if sup else {}
        checar(u"ISCA: com a suavizacao e o reparo de antes, o constritor "
               u"superior perde corte ou sai com area nula",
               sorted(por_z_i) != list(range(20, 27))
               or min(por_z_i.values()) < 1.0,
               str(dict((z, round(a, 1)) for z, a in sorted(por_z_i.items()))))
        _c, meta_s, entrada_s = _rodar_constr("auto", isca_suav=True)
        m_s = (meta_s.get("mascaras") or {}).get(
            "pharyngeal_constrictor_superior")
        checar(u"ISCA: com a suavizacao de antes, a mascara do superior (que "
               u"tem uma parte grossa) deixa de ser a do modelo",
               m_s is not None and not np.array_equal(
                   np.asarray(m_s, bool),
                   entrada_s["superior_pharyngeal_constrictor"]))
    finally:
        shutil.rmtree(base, ignore_errors=True)


def teste_as_cores_proprias_chegam_ao_study():
    secao(u"cor propria gravada no STUDY e cor padrao preservada no FULL")
    import radai_config as cfg
    base = tempfile.mkdtemp(prefix="radai_t_fulloar_")
    velho = cfg.ler_nomes
    try:
        cfg.ler_nomes = lambda *a, **k: {
            "modo": "proprios", "nomes": {}, "cores": {"Heart_ai": [7, 83, 191]}}
        serie = _serie(base)
        _sd, r, _l, _d = _rodar(base, serie)
        def cor(caminho, nome):
            ds = pydicom.dcmread(caminho)
            numero = next(int(roi.ROINumber) for roi in ds.StructureSetROISequence
                          if str(roi.ROIName) == nome)
            return next(tuple(int(v) for v in roi.ROIDisplayColor)
                        for roi in ds.ROIContourSequence
                        if int(roi.ReferencedROINumber) == numero)
        checar(u"mudar somente a cor, sem renomear, grava o RGB escolhido",
               cor(r["oar"], "Heart_ai") == (7, 83, 191))
        checar(u"o FULL conserva o RGB padrao da mesma estrutura",
               cor(r["full"], "Heart_ai") == tuple(E._color("heart")))
        cfg.ler_nomes = lambda *a, **k: {
            "modo": "padrao", "nomes": {}, "cores": {"Heart_ai": [7, 83, 191]}}
        _sd2, r2, _l2, _d2 = _rodar(base, serie)
        checar(u"modo padrao ignora o RGB proprio armazenado",
               cor(r2["oar"], "Heart_ai") == tuple(E._color("heart")))
    finally:
        cfg.ler_nomes = velho
        shutil.rmtree(base, ignore_errors=True)


def teste_os_nomes_neutros_de_apresentacao():
    secao(u"nomes neutros de apresentacao sem mudar a fronteira clinica")
    base = tempfile.mkdtemp(prefix="radai_t_fulloar_")
    try:
        serie = _serie(base)
        _sd, saidas, _l, _d = _rodar(base, serie)
        _sf, rapido, _lf, _df = _rodar(base, serie, modo="fast")
        for cod, caminho, nome, rotulo, numero in (
                ("STUDY", saidas["oar"], "RadAI STUDY", "RadAI_STUDY", 900),
                ("FULL", saidas["full"], "RadAI FULL", "RadAI_FULL", 901),
                ("FAST", rapido["oar_fast"], "RadAI STUDY Fast",
                 "RadAI_STUDY_Fast", 900)):
            ds = pydicom.dcmread(caminho)
            checar(u"%s: SeriesDescription e StructureSetName neutros" % cod,
                   str(ds.SeriesDescription) == nome
                   and str(ds.StructureSetName) == nome)
            checar(u"%s: rotulo e numero da serie preservados" % cod,
                   str(ds.StructureSetLabel) == rotulo
                   and int(ds.SeriesNumber) == numero)
            checar(u"%s: continua UNAPPROVED com a fronteira na descricao" % cod,
                   str(ds.ApprovalStatus) == "UNAPPROVED"
                   and "SUGESTAO NAO APROVADA" in str(ds.StructureSetDescription))
            checar(u"%s: ROIs automaticas preservam sufixo e proveniencia" % cod,
                   all(str(r.ROIName).endswith("_ai")
                       and str(r.ROIGenerationAlgorithm) == "AUTOMATIC"
                       for r in ds.StructureSetROISequence)
                   and all(getattr(r, "ROIGenerationDescription", "")
                           for r in ds.StructureSetROISequence))
            if cod != "FULL":
                checar(u"%s: a descricao da ROI guarda nome padrao e nao aprovacao" % cod,
                       all("sugestao IA nao aprovada" in str(getattr(r, "ROIDescription", ""))
                           for r in ds.StructureSetROISequence))
        for rotulo in ("RadAI_NV", "RadAI_MSE", "RadAI_HNL"):
            textos = E._textos_do_conjunto(rotulo, "teste", False, "_ai", [], 0, 0)
            checar(u"comparativo %s conserva seus textos anteriores" % rotulo,
                   textos["StructureSetName"] == rotulo + " - nao e o entregue"
                   and textos["SeriesDescription"].startswith(rotulo + " - nao e o entregue"))
        checar(u"os arquivos da Suite continuam com o prefixo RS_RadAI",
               all(os.path.basename(c).startswith("RS_RadAI_")
                   for c in (saidas["oar"], saidas["full"], rapido["oar_fast"])))
    finally:
        shutil.rmtree(base, ignore_errors=True)


def main():
    print(u"test_full_oar | a cadeia do entregue (FULL -> OAR), spec A1-A7")
    testes = (teste_o_oar_e_uma_selecao_exata_do_full,
              teste_o_full_faz_o_pos_processamento,
              teste_as_iscas_da_cadeia,
              teste_margem_em_cada_vaso_e_composto_como_soma,
              teste_a_interface_das_construcoes,
              teste_o_femur_oar_e_o_inteiro,
              teste_a_parede_recebe_o_mediastino_e_o_estudo_torax,
              teste_o_pedido_do_torax_chega_pela_porta_unica,
              teste_o_cru_nao_recebe_nada,
              teste_os_plugins_tem_arquivo_proprio,
              teste_a_falha_do_entregue_levanta,
              teste_a_grade_que_falta_e_dita,
              teste_a_mascara_espelhada_nao_entra,
              teste_o_delgado_e_suavizado_uma_vez,
              teste_a_aorta_que_atravessa_o_topo_do_coracao,
              teste_as_construcoes_da_onda_2_estao_ligadas,
              teste_a_margem_vem_antes_do_coracao,
              teste_a_construcao_recebe_uma_camada,
              teste_o_contorno_externo_e_calculado_uma_vez,
              teste_o_que_nao_saiu_tem_nome,
              teste_a_descricao_da_serie_chega_ao_dicom,
              teste_a_copia_temporaria_do_oar_e_apagada,
              teste_a_copia_temporaria_do_oar_fast_e_apagada,
              teste_a_copia_temporaria_do_full_e_dos_conjuntos_e_apagada,
              teste_os_niveis_cervicais_entram_crus_e_marcados,
              teste_o_oar_do_pescoco_com_niveis,
              teste_a_parotida_por_lado,
              teste_a_uniao_marcada_nao_vai_ao_oar,
              teste_niveis_e_uniao_nao_saem_como_orgao,
              teste_a_margem_engolida_pela_grade_vai_na_descricao,
              teste_um_resto_do_viii_nao_substitui_a_parotida,
              teste_o_x_na_parotida_vale_para_as_duas_chaves,
              teste_o_pescoco_sem_niveis,
              teste_o_pericardio_reune_o_coracao_e_o_recipiente_nao_alarma,
              teste_o_esofago_na_bag_continua_alarme,
              teste_o_caminho_rapido_e_o_de_antes,
              teste_a_densidade_fala_em_todo_arquivo_que_a_roda,
              teste_os_passos_da_cadeia_chegam_ao_registro_de_casos,
              teste_o_cru_nao_diz_que_leu_a_serie,
              teste_a_descricao_da_bag_diz_o_que_a_receita_tira,
              teste_a_bag_nao_guarda_o_coracao_suavizado,
              teste_a_recusada_pelo_add_roi_nao_e_julgada,
              teste_a_parede_diz_o_que_aconteceu_nesta_serie,
              teste_a_segunda_passada_recorta_a_parede_de_novo,
              teste_a_parede_na_cadeia_um_contorno_e_sem_vizinhos,
              teste_a_glandula_sai_por_lado_no_full,
              teste_as_conferencias_julgam_o_que_entrou,
              teste_as_regras_de_gravacao_fora_do_corpo,
              teste_a_r3_numa_tc_so_de_membros,
              teste_a_limpeza_fora_do_corpo_calcula_o_corpo_da_r3,
              teste_as_regras_de_gravacao_borda_do_campo,
              teste_as_regras_de_gravacao_ilhas,
              teste_as_regras_de_gravacao_julgam_o_pulmao_e_nao_o_lobo,
              teste_as_regras_de_gravacao_portoes_de_regiao,
              teste_a_ilha_em_revisao_so_de_quem_saiu_no_arquivo,
              teste_as_regras_de_gravacao_rodam_primeiro_e_nao_vao_ao_dicom,
              teste_o_heart_ai_com_pericardio_e_um_volume_depois_do_recorte,
              teste_o_heart_ai_sem_a_cava_inferior_por_baixo,
              teste_o_heart_ai_os_tres_casos_da_cava_e_sem_o_esofago,
              teste_a_tireoide_e_delgada,
              teste_o_ivb_sem_a_clavicula_antes_da_uniao,
              teste_os_ventriculos_e_a_linha_media_dentro_do_brain,
              teste_o_brain_da_rm_fica_so_no_full,
              teste_os_pulmoes_somados_no_entregue,
              teste_as_estruturas_novas_chegam_ao_full_e_ao_oar,
              teste_o_full_leva_tudo,
              teste_o_apendice_atrial_e_roi_do_full,
              teste_o_reto_e_os_compostos_da_pelve,
              teste_os_compostos_da_pelve_so_vao_ao_oar_com_a_pelve,
              teste_o_fast_grava_so_o_oar_fast,
              teste_as_entregas_nao_decimam,
              teste_a_decimacao_poupa_a_estrutura_pequena,
              teste_o_oar_fora_so_tira_do_oar,
              teste_os_compostos_inteiros_no_grupo_e_sem_o_coracao,
              teste_o_ts_cru_nao_sai_do_entregue,
              teste_o_derrame_e_anatomia_do_torax,
              teste_o_oar_e_gravado_antes_e_o_full_pode_faltar,
              teste_o_study_vazio_da_rm_grava_o_full_e_a_serie_fica_pronta,
              teste_o_oar_sai_igual_ao_caminho_de_antes,
              teste_a_gravacao_nao_guarda_duas_copias,
              teste_as_carotidas_ficam_so_no_full,
              teste_o_reto_pelo_plato_do_sacro,
              teste_os_orgaos_do_motor_do_cranio_chegam_ao_oar,
              teste_o_entregue_nao_tem_contorno_degenerado_nem_cruzado,
              teste_os_constritores_finos_nao_somem,
              teste_as_cores_proprias_chegam_ao_study,
              teste_os_nomes_neutros_de_apresentacao)
    _conferir_registro(testes)
    for t in testes:
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
