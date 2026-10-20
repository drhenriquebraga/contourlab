# -*- coding: utf-8 -*-
import ast
import inspect
import io
import os
import shutil
import sys
import tempfile
import traceback
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


APP = pasta_app(AQUI)
sys.path.insert(0, APP)
sys.path.insert(0, AQUI)
os.environ["RADAI_CALIB_DIR"] = tempfile.mkdtemp(prefix="radai_ac_motor2_")
os.environ["TOTALSEG_HOME_DIR"] = tempfile.mkdtemp(prefix="radai_tsh_motor2_")
import _cleanup
import _componentes
_cleanup.adotar_prefixo("radai_ac_motor2_")
_cleanup.adotar_prefixo("radai_tsh_motor2_")
_cleanup.adotar_prefixo("radai_t_motor2_")

import numpy as np
import pydicom
from scipy import ndimage
import engine as E
import radai_constructs as RC
import radai_geom
import radai_output as RO
import radai_sets as RS
from make_test_series import escreve_serie

_RES = []
VERBOSO = "-v" in sys.argv
Z, Y, X = 30, 128, 128
G = radai_geom.Grade((3.0, 2.0, 2.0))


def checar(nome, cond, detalhe=""):
    ok = bool(cond)
    _RES.append((nome, ok, detalhe))
    if VERBOSO or not ok:
        print(u"  %s  %s%s" % (u"OK   " if ok else u"FALHA", nome,
                              (u"  [%s]" % detalhe) if detalhe else u""))
    return ok


def secao(t):
    print(u"\n-- %s --" % t)


def caixa(z0, z1, y0, y1, x0, x1, forma=(Z, Y, X)):
    m = np.zeros(forma, bool)
    m[z0:z1, y0:y1, x0:x1] = True
    return m


def _cruas(itens):
    por_task = {}
    for rot, task, m in itens:
        por_task.setdefault(task, []).append((rot, m))
    fora = {}
    for task, lista in por_task.items():
        lab = np.zeros((Z, Y, X), np.int16)
        idx = {}
        for i, (rot, m) in enumerate(lista, start=1):
            lab[m] = i
            idx[i] = rot
        fora[task] = E.MasksCruas(lab, idx)
    return fora


def _origem(chave):
    k = chave
    if k not in E.TS_MAP and k in E.COMPOSTOS:
        k = E.COMPOSTOS[k][0]
    d = E.TS_MAP[k]
    task = sorted(d)[0]
    return ("total_v3" if task == "total" else task), d[task][0]


def _serie(base):
    serie = os.path.join(base, "serie")
    escreve_serie(serie, "PAC_MOTOR2", datetime.now(), Z)
    return serie


def _rodar(base, serie, cruas, **kw):
    import SimpleITK as sitk
    ref = E.load_sitk(serie)
    vol = sitk.GetArrayFromImage(ref)
    linhas = []
    dest = os.path.join(base, "saida_%d" % len(os.listdir(base)))
    os.makedirs(dest)
    sd = RO.Saida(E, serie, dest, "RS_RadAI_20261011_1a2b3c4d.dcm",
                  tasks=["total_v3"], versao="bateria", suavizar_mm=1.5,
                  log=lambda m: linhas.append(str(m)), modalidade="CT")
    sd.devolver_mascaras = True
    r = sd.full_e_oar(cruas, volume_hu=vol, **kw)
    return sd, r, linhas


def _nomes_rs(caminho):
    return [str(x.ROIName) for x in
            pydicom.dcmread(caminho).StructureSetROISequence]


def _obs(caminho):
    ds = pydicom.dcmread(caminho)
    num = dict((int(r.ROINumber), str(r.ROIName))
               for r in ds.StructureSetROISequence)
    return dict((num.get(int(o.ReferencedROINumber)),
                 str(getattr(o, "ROIObservationDescription", "")))
                for o in getattr(ds, "RTROIObservationsSequence", []))


def _sem_indice_26(nomes):
    return not [n for n in nomes if n.lower().startswith(
        ("vertebrae_l6", "vertebrae_s1"))]


def _pelve(nome26="vertebrae_L6", com_26=True):
    itens = [("sacrum", "total_v3", caixa(6, 24, 60, 72, 58, 70)),
             ("hip_left", "total_v3", caixa(6, 27, 55, 75, 70, 84)),
             ("hip_right", "total_v3", caixa(6, 27, 55, 75, 44, 58)),
             ("colon", "total_v3", caixa(0, 15, 50, 58, 60, 68)),
             ("gluteus_maximus_left", "total_v3", caixa(4, 22, 78, 90, 75, 92)),
             ("iliopsoas_left", "total_v3", caixa(10, 28, 46, 54, 74, 84)),
             ("adrenal_gland_left", "total_v3", caixa(18, 22, 30, 34, 80, 84)),
             ("kidney_left", "total_v3", caixa(14, 22, 34, 44, 78, 90))]
    if com_26:
        itens.append((nome26, "total_v3", caixa(26, 29, 60, 72, 58, 70)))
    return _cruas(itens)


def teste_o_indice_26_na_cadeia():
    secao(u"C4: o indice 26 fundido ao sacro, em todo RTSTRUCT")
    base = tempfile.mkdtemp(prefix="radai_t_motor2_")
    try:
        serie = _serie(base)
        l6 = caixa(26, 29, 60, 72, 58, 70)
        for nome26 in ("vertebrae_L6", "vertebrae_S1"):
            sd, r, linhas = _rodar(base, serie, _pelve(nome26))
            mf = dict((k, np.asarray(v, bool))
                      for k, v in sd.meta_do_full["mascaras"].items())
            full, oar = _nomes_rs(r["full"]), _nomes_rs(r["oar"])
            cru = sd.totalsegmentator_cru(_pelve(nome26))
            nomes_cru = _nomes_rs(cru)
            checar(u"%s: nenhuma ROI do indice 26 no FULL, no OAR e no "
                   u"STUDY_ts" % nome26,
                   _sem_indice_26(full) and _sem_indice_26(oar)
                   and _sem_indice_26(nomes_cru),
                   str([n for n in full + oar + nomes_cru if "ertebrae" in n]))
            checar(u"  o Sacrum_ai do FULL leva os voxels do indice 26",
                   "sacrum" in mf and (mf["sacrum"] & l6).sum()
                   >= 0.9 * l6.sum(), str(int((mf.get("sacrum", l6 * 0)
                                               & l6).sum())))
            checar(u"  e o Bone_Pelvic_ai tambem",
                   "bone_pelvic" in mf and (mf["bone_pelvic"] & l6).sum()
                   >= 0.9 * l6.sum())
            checar(u"  e o STUDY_ts leva o indice 26 no Sacrum_ts",
                   "Sacrum_ts" in nomes_cru, str(nomes_cru))
            checar(u"  e a descricao do Sacrum_ts diz a fusao",
                   u"indice 26" in _obs(cru).get("Sacrum_ts", u""),
                   _obs(cru).get("Sacrum_ts", u"-")[:160])
            obs = _obs(r["full"])
            checar(u"  a descricao do sacro e do osso da pelve diz «indice 26»",
                   u"indice 26" in obs.get("Sacrum_ai", u"")
                   and u"indice 26" in obs.get("Bone_Pelvic_ai", u""),
                   obs.get("Sacrum_ai", u"-")[:200])
            checar(u"  o log diz a fusao",
                   any(l.startswith(u"indice 26 fundido ao sacro") for l in
                       linhas))
            sessao = None
            try:
                import radai_rt
                sessao = radai_rt.abrir(serie, r["full"])
                checar(u"  na volta RTSTRUCT -> mascara (radai_rt), nenhuma ROI "
                       u"do indice 26", _sem_indice_26(list(sessao.nomes)),
                       str(sessao.nomes))
            finally:
                if sessao is not None:
                    shutil.rmtree(getattr(sessao, "pasta_limpa", ""),
                                  ignore_errors=True)
        velho = E.ORDEM_DO_FULL
        E.ORDEM_DO_FULL = tuple(p for p in velho
                                if p[0] != "fusao_do_indice_26")
        try:
            sd2, r2, _l2 = _rodar(base, serie, _pelve())
        finally:
            E.ORDEM_DO_FULL = velho
        m2 = np.asarray(sd2.meta_do_full["mascaras"].get("sacrum"), bool)
        checar(u"ISCA: sem o passo da fusao, o Sacrum_ai fica sem o indice 26",
               not (m2 & l6).any())
        linhas = []
        mk = {"sacrum": caixa(6, 24, 60, 72, 58, 70), "vertebrae_L6": l6}
        stage = os.path.join(base, "serie")
        _rs, nomes = E.build_rtstruct(stage, mk, versao_worker="isca",
                                      log=linhas.append)
        checar(u"o gravador recusa `vertebrae_L6` e diz no log",
               "vertebrae_L6" not in nomes and any(
                   u"indice 26 deveria ter sido fundido" in l for l in linhas),
               str(nomes))
        velho26 = E.INDICE_26
        E.INDICE_26 = ()
        try:
            _rs2, nomes2 = E.build_rtstruct(stage, dict(mk),
                                            versao_worker="isca")
        finally:
            E.INDICE_26 = velho26
        checar(u"ISCA: sem a trava, `Vertebrae_L6_ai` seria gravada",
               "vertebrae_L6" in nomes2, str(nomes2))
    finally:
        shutil.rmtree(base, ignore_errors=True)


def _sacro_obliquo():
    g = radai_geom.Grade((3.0, 1.0, 1.0))
    forma = (40, 120, 80)
    zz, yy, xx = np.mgrid[0:forma[0], 0:forma[1], 0:forma[2]]
    zmm, ymm = zz * 3.0, yy * 1.0
    tg = np.tan(np.radians(35.0))
    topo = 75.0 + (ymm - 70.0) * tg
    sacro = ((xx >= 25) & (xx <= 55) & (yy >= 70) & (yy <= 105)
             & (zz >= 5) & (zmm <= topo))
    s1 = sacro & (zmm > topo - 12.0)
    return g, sacro & ~s1, s1, sacro


def teste_o_plato_e_o_mesmo_nas_duas_versoes():
    secao(u"C4: o plano do plato do sacro e o mesmo com S1 e com L6")
    g, baixo, s1, inteiro = _sacro_obliquo()
    ref, _m = E.plano_do_plato_do_sacro({"sacrum": inteiro}, g)
    planos = {}
    for nome in ("vertebrae_S1", "vertebrae_L6"):
        m = {"sacrum": baixo.copy(), nome: s1.copy()}
        E.fundir_indice_26_no_sacro(m, g)
        planos[nome], _x = E.plano_do_plato_do_sacro(m, g)
    checar(u"com a fusao, S1 e L6 dao o mesmo plano, o do sacro inteiro",
           ref is not None and planos["vertebrae_S1"] == planos["vertebrae_L6"]
           == ref, str(planos))
    sem = {}
    for nome in ("vertebrae_S1", "vertebrae_L6"):
        sem[nome], _x = E.plano_do_plato_do_sacro(
            {"sacrum": baixo.copy(), nome: s1.copy()}, g)
    checar(u"ISCA: sem a fusao, o nome L6 da outro plano (o platô lia so a S1)",
           sem["vertebrae_S1"] != sem["vertebrae_L6"], str(sem))


def teste_a_derivacao_roda_uma_vez_e_antes_da_bag():
    secao(u"cadeia: o reto e feito no FULL, uma vez, antes da no_fim")
    nomes = [e for e, _v in E.ORDEM_DO_FULL]
    checar(u"`derivadas` vem logo antes de `construcoes no_fim`",
           nomes.index("derivadas") + 1 == E.ORDEM_DO_FULL.index(
               ("construcoes", "no_fim")))
    base = tempfile.mkdtemp(prefix="radai_t_motor2_")
    velho = E.aplicar_derivadas
    chamadas = []

    def _conta(masks, grade, **kw):
        out = velho(masks, grade, **kw)
        chamadas.append(np.asarray(masks["rectum"], bool).copy()
                        if "rectum" in masks else None)
        return out
    viu = {}
    velho_c = RC.bag_bowel_oar

    def _espia(masks, grade, **kw):
        viu["rectum"] = (np.asarray(masks["rectum"], bool).copy()
                         if "rectum" in masks else None)
        return velho_c(masks, grade, **kw)
    cav = ("abdominal_cavity", "trunk_cavities", caixa(0, 29, 30, 60, 40, 90))
    try:
        serie = _serie(base)
        cruas = _pelve(com_26=False)
        cruas.update(_cruas([cav]))
        E.aplicar_derivadas = _conta
        RC.bag_bowel_oar = _espia
        try:
            sd, r, linhas = _rodar(base, serie, cruas)
        finally:
            E.aplicar_derivadas = velho
            RC.bag_bowel_oar = velho_c
        checar(u"aplicar_derivadas roda UMA vez na cadeia do FULL",
               len(chamadas) == 1, str(len(chamadas)))
        checar(u"a construcao da Bag_Bowel_OAR ve o reto pronto",
               viu.get("rectum") is not None and viu["rectum"].any())
        checar(u"  e e o mesmo reto que a derivacao fez (voxel a voxel)",
               viu.get("rectum") is not None and chamadas
               and chamadas[0] is not None
               and np.array_equal(viu["rectum"], chamadas[0]))
        checar(u"o reto continua no FULL e no OAR (Rectum_ai)",
               "Rectum_ai" in r["estruturas_full"]
               and "Rectum_ai" in r["estruturas"])
        velho_o = E.ORDEM_DO_FULL
        viu.clear()
        E.ORDEM_DO_FULL = tuple(p for p in velho_o if p[0] != "derivadas")
        RC.bag_bowel_oar = _espia
        try:
            _rodar(base, serie, cruas)
        finally:
            E.ORDEM_DO_FULL = velho_o
            RC.bag_bowel_oar = velho_c
        checar(u"ISCA: sem o passo das derivadas, a Bag_Bowel_OAR nao ve o "
               u"reto", viu.get("rectum") is None)
        velho_b = E.build_rtstruct
        chamadas[:] = []

        def _sem_meta(*a, **kw):
            mt = kw.get("meta")
            if isinstance(mt, dict):
                mt.pop("derivadas", None)
            return velho_b(*a, **kw)
        E.build_rtstruct = _sem_meta
        E.aplicar_derivadas = _conta
        try:
            _rodar(base, serie, cruas)
        finally:
            E.build_rtstruct = velho_b
            E.aplicar_derivadas = velho
        checar(u"ISCA: sem o pulo no gravador, a derivacao roda DUAS vezes",
               len(chamadas) == 2, str(len(chamadas)))
    finally:
        E.aplicar_derivadas = velho
        RC.bag_bowel_oar = velho_c
        shutil.rmtree(base, ignore_errors=True)


_PARA_COMPARAR = ("ROIName", "ROIGenerationDescription")


def _conteudo(caminho):
    ds = pydicom.dcmread(caminho)
    num = dict((int(r.ROINumber), str(r.ROIName))
               for r in ds.StructureSetROISequence)
    cont = {}
    for c in getattr(ds, "ROIContourSequence", []):
        pts = tuple(tuple(str(v) for v in s.ContourData)
                    for s in getattr(c, "ContourSequence", []))
        cont[num[int(c.ReferencedROINumber)]] = (
            pts, tuple(int(v) for v in c.ROIDisplayColor))
    obs = _obs(caminho)
    return cont, obs


def teste_o_reto_na_cadeia_e_o_de_antes():
    secao(u"cadeia: o FULL de uma pelve sem o indice 26 e o de antes")
    base = tempfile.mkdtemp(prefix="radai_t_motor2_")
    try:
        serie = _serie(base)
        _sd, r, _l = _rodar(base, serie, _pelve(com_26=False))
        velho = E.ORDEM_DO_FULL
        E.ORDEM_DO_FULL = tuple(p for p in velho if p[0] != "derivadas")
        try:
            _sd2, r2, _l2 = _rodar(base, serie, _pelve(com_26=False))
        finally:
            E.ORDEM_DO_FULL = velho
        a, oa = _conteudo(r["full"])
        b, ob = _conteudo(r2["full"])
        checar(u"as mesmas ROIs, os mesmos pontos, as mesmas cores e "
               u"observacoes (a derivacao no gravador, de antes, contra a da "
               u"cadeia)", a == b and oa == ob,
               str(sorted(set(a) ^ set(b)))[:200] or
               str([k for k in a if a.get(k) != b.get(k)])[:200])
    finally:
        shutil.rmtree(base, ignore_errors=True)


def teste_adrenais_e_muscles_so_no_full():
    secao(u"C3: adrenais e Muscles_ai so no FULL")
    for k in ("adrenal_gland_left", "adrenal_gland_right", "pelvic_muscles"):
        checar(u"`%s` fora do OAR e do OAR_Fast" % k,
               k not in RS.PERMITIDOS_NO_OAR
               and k not in RS.PERMITIDOS_NO_OAR_FAST)
    checar(u"o REGIAO_EXIGIDA_NO_OAR e o osso da pelve, as cristas e o anus",
           E.REGIAO_EXIGIDA_NO_OAR == {"bone_pelvic": "pelve",
                                       "iliac_crest_left": "pelve",
                                       "iliac_crest_right": "pelve",
                                       "anus": "pelve"},
           str(E.REGIAO_EXIGIDA_NO_OAR))
    checar(u"FORA_DO_OAR_FAST: a Bag_Bowel_OAR e o Anus, que sai da "
           u"Bag_Bowel_ai (a Bag_Bowel_ai nem esta no OAR)",
           RS.FORA_DO_OAR_FAST == frozenset(["bag_bowel_oar", "anus"]))
    base = tempfile.mkdtemp(prefix="radai_t_motor2_")
    try:
        serie = _serie(base)
        sd, r, _l = _rodar(base, serie, _pelve(com_26=False))
        full, oar = set(r["estruturas_full"]), set(r["estruturas"])
        adr = E.nome_clinico("adrenal_gland_left")
        checar(u"%s e Muscles_ai no FULL e fora do OAR" % adr,
               {adr, "Muscles_ai"} <= full
               and not ({adr, "Muscles_ai"} & oar),
               str(sorted(oar)))
        sdf, rf, _lf = _rodar(base, serie, _pelve(com_26=False), modo="fast")
        checar(u"  e fora do OAR_Fast",
               not ({adr, "Muscles_ai"}
                    & set(rf["estruturas"])), str(sorted(rf["estruturas"])))
        rim_full = np.asarray(sd.meta_do_full["mascaras"]["kidney_left"], bool)
        rim_fast = np.asarray(sdf.meta_do_fast["mascaras"]["kidney_left"],
                              bool)
        checar(u"FAST: o rim encostado na adrenal sai igual ao do FULL (a "
               u"adrenal fica como insumo da particao)",
               np.array_equal(rim_full, rim_fast),
               u"%d voxels diferentes" % int((rim_full ^ rim_fast).sum()))
        velho = E.insumos_da_particao
        E.insumos_da_particao = lambda alvo: set()
        try:
            sdi, _ri, _li = _rodar(base, serie, _pelve(com_26=False),
                                   modo="fast")
        finally:
            E.insumos_da_particao = velho
        rim_i = np.asarray(sdi.meta_do_fast["mascaras"]["kidney_left"], bool)
        checar(u"ISCA: sem o insumo da adrenal, o rim do FAST muda na borda",
               not np.array_equal(rim_full, rim_i))
        velho_p = RS.PERMITIDOS_NO_OAR
        RS.PERMITIDOS_NO_OAR = frozenset(set(velho_p) | {"adrenal_gland_left"})
        try:
            _s3, r3, _l3 = _rodar(base, serie, _pelve(com_26=False))
        finally:
            RS.PERMITIDOS_NO_OAR = velho_p
        checar(u"ISCA: a adrenal de volta a lista, ela vai ao OAR",
               adr in set(r3["estruturas"]))
    finally:
        shutil.rmtree(base, ignore_errors=True)


NA_LISTA_DO_PESCOCO = sorted(E.FORA_DO_OAR_NA_REGIAO["cabeca_pescoco"])
CONSTRITORES = ("pharyngeal_constrictor_superior",
                "pharyngeal_constrictor_middle",
                "pharyngeal_constrictor_inferior")


def _vertebras_do_pescoco(mandibula=True, c1=True):
    fora = {"vertebrae_C2": caixa(20, 25, 80, 90, 59, 69),
            "vertebrae_C3": caixa(14, 19, 80, 90, 59, 69),
            "vertebrae_C4": caixa(8, 13, 80, 90, 59, 69)}
    if c1:
        fora["vertebrae_C1"] = caixa(25, 28, 80, 90, 59, 69)
    if mandibula:
        fora["mandible"] = caixa(13, 29, 45, 70, 92, 112)
    return fora


def _grade_de_caixas(chaves):
    fora = {}
    for i, k in enumerate(chaves):
        y0 = 30 + 8 * (i // 8)
        x0 = 30 + 9 * (i % 8)
        fora[k] = caixa(10, 13, y0, y0 + 4, x0, x0 + 4)
    return fora


def _torax(m, z_pulmao=(5, 30)):
    m = dict(m)
    m["lung_left"] = caixa(z_pulmao[0], z_pulmao[1], 95, 125, 0, 100,
                           forma=(Z, Y, X))
    m["clavicula_left"] = caixa(26, 28, 40, 44, 80, 90)
    m["scapula_left"] = caixa(14, 24, 70, 80, 90, 100)
    return m


def teste_o_oar_do_pescoco_por_topografia():
    secao(u"C10: o OAR do pescoco, por topografia")
    todas = NA_LISTA_DO_PESCOCO + list(E.FORA_DO_OAR_NO_PESCOCO_SEM_TORAX)
    checar(u"34 chaves: 32 da lista e os dois grandes vasos sem torax (a "
           u"carotida saiu da lista: ela vai so ao FULL em toda regiao)",
           len(NA_LISTA_DO_PESCOCO) == 32 and len(todas) == 34
           and "carotids" not in todas and "carotids" not in
           RS.PERMITIDOS_NO_OAR, str(len(todas)))
    checar(u"todas estao em PERMITIDOS_NO_OAR (senao a regra e inerte)",
           set(todas) <= RS.PERMITIDOS_NO_OAR,
           str(sorted(set(todas) - RS.PERMITIDOS_NO_OAR)))
    checar(u"nenhuma e constritor da faringe",
           not [k for k in todas if k.startswith("pharyngeal_constrictor")])
    src = inspect.getsource(E.fora_do_oar_por_regiao)
    arv = ast.parse(src.lstrip())
    chama = any(isinstance(n, ast.Attribute) and n.attr == "anatomia_da_base"
                for n in ast.walk(arv))
    checar(u"fora_do_oar_por_regiao mede pela radai_topography."
           u"anatomia_da_base", chama and "regioes_no_campo(" not in src)
    base = dict(_vertebras_do_pescoco())
    base.update(_grade_de_caixas(todas + list(CONSTRITORES)))
    sem_m = dict(base)
    sem_m.pop("mandible")
    checar(u"ISCA: sem a mandibula no campo, nao e pescoco (nada da lista sai)",
           not (set(todas) & set(E.fora_do_oar_por_regiao(sem_m, G))))
    fora = E.fora_do_oar_por_regiao(base, G)
    checar(u"pescoco sem torax: as 34 saem do OAR",
           set(todas) <= set(fora), str(sorted(set(todas) - set(fora))))
    checar(u"  e os constritores ficam",
           not (set(CONSTRITORES) & set(fora)))
    checar(u"  e o motivo diz a regiao",
           all(u"cabeca_pescoco" in fora[k] for k in todas if k in fora))
    ft = E.fora_do_oar_por_regiao(_torax(base), G)
    checar(u"pescoco com torax: os grandes vasos ficam, as 32 saem",
           set(NA_LISTA_DO_PESCOCO) <= set(ft)
           and not ({"great_arteries", "great_veins"} & set(ft)),
           str(sorted(set(ft) & {"great_arteries", "great_veins"})))
    cranio = dict(_grade_de_caixas(todas))
    cranio["brain"] = caixa(0, 29, 20, 110, 20, 110)
    fc = E.fora_do_oar_por_regiao(cranio, G)
    checar(u"cranio sem pescoco: nada da lista sai",
           not (set(todas) & set(fc)), str(sorted(fc)))
    tor = _torax(_grade_de_caixas(todas))
    fx = E.fora_do_oar_por_regiao(tor, G)
    checar(u"torax sem pescoco: nada da lista sai (a lista nao e global)",
           not (set(todas) & set(fx)), str(sorted(fx)))
    velho = E.FORA_DO_OAR_NA_REGIAO
    E.FORA_DO_OAR_NA_REGIAO = {"torax": tuple(NA_LISTA_DO_PESCOCO)}
    try:
        fxi = E.fora_do_oar_por_regiao(tor, G)
    finally:
        E.FORA_DO_OAR_NA_REGIAO = velho
    checar(u"ISCA: a lista aplicada fora do pescoco tira do torax",
           set(NA_LISTA_DO_PESCOCO) <= set(fxi))
    itens = [(_origem(k)[1], _origem(k)[0], m)
             for k, m in sorted(base.items())]
    tmp = tempfile.mkdtemp(prefix="radai_t_motor2_")
    try:
        serie = _serie(tmp)
        _sd, r, linhas = _rodar(tmp, serie, _cruas(itens))
        full, oar = set(r["estruturas_full"]), set(r["estruturas"])
        for k in ("tongue", "skull", "great_arteries"):
            nome = E.nome_clinico(k)
            checar(u"cadeia: `%s` no FULL e fora do OAR" % nome,
                   nome in full and nome not in oar,
                   u"FULL %s | OAR %s" % (nome in full, nome in oar))
        cons = E.nome_clinico("pharyngeal_constrictor_superior")
        checar(u"cadeia: `%s` no OAR" % cons, cons in oar, str(sorted(oar)))
        checar(u"  e o log diz cada uma com o motivo da regiao",
               any(l.startswith(u"OAR desta serie SEM %s"
                                % E.nome_clinico("tongue"))
                   and u"cabeca_pescoco" in l for l in linhas))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    _pescoco_com_torax_na_cadeia(base)


def _pescoco_com_torax_na_cadeia(base):
    tor = _torax(base)
    itens = [(_origem(k)[1], _origem(k)[0], m)
             for k, m in sorted(tor.items())
             if k not in ("clavicula_left", "scapula_left")]
    itens.append(("clavicula_left", "total_v3", tor["clavicula_left"]))
    itens.append(("scapula_left", "total_v3", tor["scapula_left"]))
    vasos = [E.nome_clinico(k) for k in ("great_arteries", "great_veins")]

    def _uma(tmp):
        sub = tempfile.mkdtemp(dir=tmp)
        serie = _serie(sub)
        _sd, r, _l = _rodar(sub, serie, _cruas(itens))
        return set(r["estruturas"]), dict(r.get("oar_fora_por_regiao") or {})

    tmp = tempfile.mkdtemp(prefix="radai_t_motor2_")
    try:
        oar, fora = _uma(tmp)
        checar(u"cadeia, pescoco com torax: os grandes vasos ficam no OAR",
               all(v in oar for v in vasos)
               and not ({"great_arteries", "great_veins"} & set(fora)),
               u"OAR %s | fora %s" % ([v in oar for v in vasos], sorted(fora)))
        checar(u"  e a carotida nao esta no OAR (so no FULL, em toda regiao)",
               E.nome_clinico("carotids") not in oar)
        velho = RO.vocabulario_do_full

        def _sem_marcos(cruas, *a, **k):
            v = velho(cruas, *a, **k)
            pares = dict((c, v._pares[c]) for c in v
                         if not c.startswith(("clavicula", "scapula")))
            return RO._VistaDeRotulos(pares)
        RO.vocabulario_do_full = _sem_marcos
        try:
            oar_i, _f = _uma(tmp)
        finally:
            RO.vocabulario_do_full = velho
        checar(u"ISCA: sem clavicula e escapula na camada do FULL, os "
               u"grandes vasos saem", not any(v in oar_i for v in vasos))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _figado(cm3, z0=15):
    n = int(round(cm3 * 1000.0 / 12.0))
    m = np.zeros((Z, Y, X), bool)
    lado = max(1, int(round((n / 3.0) ** 0.5)))
    m[z0:z0 + 3, 40:40 + lado, 40:40 + lado] = True
    return m


def teste_o_orgao_solido_espurio():
    secao(u"C5: o orgao solido espurio sai pela R4")
    pisos = [v[1] for v in E.ORGAOS_SOLIDOS_DO_TRONCO.values()]
    checar(u"pisos por orgao: nao ha um piso universal, e nenhum chega a 500",
           len(set(pisos)) > 1 and max(pisos) < 500, str(pisos))
    fig = _figado(1.3)
    pesc = dict(_vertebras_do_pescoco())
    m = dict(pesc, liver=fig.copy())
    linhas = []
    rel = E.aplicar_regras_de_gravacao(m, G, log=linhas.append)
    checar(u"pescoco com figado de 1,3 cm3: o figado sai",
           "liver" not in m and "liver" in rel["saiu"], str(rel["saiu"]))
    checar(u"  e o log diz a R4 com o motivo",
           any(u"R4 portao de regiao: `liver` saiu" in l
               and u"orgao solido do tronco" in l for l in linhas))
    velho = E.ORGAOS_SOLIDOS_DO_TRONCO
    E.ORGAOS_SOLIDOS_DO_TRONCO = {}
    try:
        mi = dict(pesc, liver=fig.copy())
        E.aplicar_regras_de_gravacao(mi, G)
    finally:
        E.ORGAOS_SOLIDOS_DO_TRONCO = velho
    checar(u"ISCA: sem o portao, o figado fica", "liver" in mi)
    mt = _torax(dict(pesc, liver=fig.copy()))
    E.aplicar_regras_de_gravacao(mt, G)
    checar(u"o mesmo figado numa TC de torax que sobe ao pescoco (a base do "
           u"pulmao no campo): fica", "liver" in mt)
    apices = (0, 12)
    mp = _torax(dict(pesc, liver=fig.copy()), z_pulmao=apices)
    lp = []
    relp = E.aplicar_regras_de_gravacao(mp, G, log=lp.append)
    checar(u"cabeca e pescoco com os apices (torax identificado, o pulmao na "
           u"borda caudal) e o figado longe dela: o figado sai",
           "liver" not in mp and "liver" in relp["saiu"], str(relp["saiu"]))
    checar(u"  e o motivo diz que o torax nao o explica",
           any(u"`liver` saiu" in l and u"o torax nao o explica" in l
               for l in lp))
    velho_t = E._o_torax_explica_o_orgao
    E._o_torax_explica_o_orgao = lambda *a, **k: (True, u"isca")
    try:
        mpi = _torax(dict(pesc, liver=fig.copy()), z_pulmao=apices)
        E.aplicar_regras_de_gravacao(mpi, G)
    finally:
        E._o_torax_explica_o_orgao = velho_t
    checar(u"ISCA: com o torax valendo como regiao do figado sempre, ele fica",
           "liver" in mpi)
    mb = _torax(dict(pesc, liver=_figado(1.3, z0=2)), z_pulmao=apices)
    E.aplicar_regras_de_gravacao(mb, G)
    checar(u"os apices e o figado na borda caudal (continua abaixo do campo): "
           u"fica", "liver" in mb)
    mg = dict(pesc, liver=_figado(150.0))
    E.aplicar_regras_de_gravacao(mg, G)
    checar(u"pescoco com figado de 150 cm3: fica (o volume e a segunda "
           u"condicao)", "liver" in mg)
    ma = dict(pesc, adrenal_gland_left=_figado(2.0))
    E.aplicar_regras_de_gravacao(ma, G)
    checar(u"adrenal de 2 cm3 no pescoco: fica (nao e da tabela)",
           "adrenal_gland_left" in ma)
    mm = {"femur_left": caixa(0, 29, 40, 60, 40, 60), "liver": fig.copy()}
    E.aplicar_regras_de_gravacao(mm, G)
    checar(u"sem cabeca nem pescoco no campo (membro), o portao nao age",
           "liver" in mm)


def teste_oculomotor_so_por_ato_declarado():
    secao(u"C6: os oculomotores so por ato declarado")
    import itertools
    import radai_modes as MD
    import radai_topography as TP
    reg = ("cranio", "cabeca_pescoco", "torax", "abdome", "pelve", "membros")
    achou = []
    for n in range(0, len(reg) + 1):
        for combo in itertools.combinations(reg, n):
            for mod in ("CT", "MR"):
                try:
                    t = TP.tasks_da_anatomia(combo, modalidade=mod)[0]
                except Exception as e:
                    t = ["erro %s" % type(e).__name__]
                try:
                    f = MD.tasks_do_fast(combo, modalidade=mod)
                except Exception as e:
                    f = ["erro %s" % type(e).__name__]
                try:
                    v = MD.tasks_da_topografia(combo, mod)
                except Exception as e:
                    v = ["erro %s" % type(e).__name__]
                if "oculomotor_muscles" in list(t) + list(f) + list(v):
                    achou.append((combo, mod))
    checar(u"nenhuma combinacao de regioes, nas duas modalidades, roda os "
           u"oculomotores no AUTO nem no FAST", not achou, str(achou[:3]))
    checar(u"nenhum protocolo os arrasta",
           not [p["cod"] for p in MD.PROTOCOLOS
                if "oculomotor_muscles" in tuple(p.get("tasks") or ())])
    checar(u"nenhuma chave de fabrica os liga",
           not any("oculomotor_muscles" in tuple(v)
                   for v in MD.LIGADAS_DE_FABRICA_NO_PERSO.values()))
    p = MD.tasks_do_personalizado(chaves={"oculomotor_muscles": 1})
    p0 = MD.tasks_do_personalizado(chaves={})
    checar(u"no PERSONALIZADO, so com a chave ligada",
           "oculomotor_muscles" in list(p)
           and "oculomotor_muscles" not in list(p0))
    _cfg = os.path.join(tempfile.mkdtemp(prefix="radai_t_motor2_"),
                        "radai_watcher.config")
    io.open(_cfg, "w", encoding="utf-8").write(u"ROOT=\n")
    os.environ["RADAI_CONFIG"] = _cfg
    os.environ["LOCALAPPDATA"] = tempfile.mkdtemp(prefix="radai_t_motor2_")
    import radai_watcher as W
    velho = dict(W.CFG)
    try:
        W.CFG["TASKS"] = "total_v3 oculomotor_muscles"
        W.aplicar_cfg()
        checar(u"um config com TASKS=... oculomotor_muscles nao muda a lista "
               u"do vigia", "oculomotor_muscles" not in list(W.TASKS),
               str(W.TASKS))
    finally:
        W.CFG.clear()
        W.CFG.update(velho)
        W.aplicar_cfg()
    velho_t = MD.TASKS_POR_TOPOGRAFIA
    MD.TASKS_POR_TOPOGRAFIA = dict(velho_t)
    MD.TASKS_POR_TOPOGRAFIA["cabeca_pescoco"] = (
        tuple(velho_t.get("cabeca_pescoco") or ()) + ("oculomotor_muscles",))
    try:
        ti = MD.tasks_da_topografia(("cabeca_pescoco",), "CT")
    finally:
        MD.TASKS_POR_TOPOGRAFIA = velho_t
    checar(u"ISCA: com a task na tabela do pescoco, ela roda no AUTO",
           "oculomotor_muscles" in list(ti), str(ti))


def _orbita():
    zz, yy, xx = np.mgrid[0:Z, 0:Y, 0:X]
    d = np.sqrt(((zz - 15) * 3.0) ** 2 + ((yy - 40) * 2.0) ** 2
                + ((xx - 50) * 2.0) ** 2)
    globo = d <= 12.0
    lente = (((zz - 15) * 3.0) ** 2 / 9.0 + ((yy - 35) * 2.0) ** 2 / 9.0
             + ((xx - 50) * 2.0) ** 2 / 16.0) <= 1.0
    olho = globo & ~lente & ~(yy >= 45)
    olho[15, 40:42, 52:54] = False
    olho |= caixa(13, 17, 36, 42, 56, 58)
    nervo = caixa(14, 17, 45, 54, 48, 53)
    return olho, lente & globo, nervo


def _superficie_por_volume(m):
    m = np.asarray(m, bool)
    borda = m & ~ndimage.binary_erosion(m)
    return float(borda.sum()) / float(m.sum())


def teste_o_globo_ocular():
    secao(u"C9: o olho e o globo inteiro, com o cristalino")
    olho, lente, nervo = _orbita()
    g = radai_geom.preencher_buracos(olho | lente, por_fatia=False,
                                     triplanar=True)
    esfera = RC._esfera_de_mesmo_volume(g, G)
    globo = RC.globo_ocular(olho, lente, G)
    checar(u"o globo contem o cristalino inteiro",
           globo is not None and not (lente & ~globo).any())
    checar(u"  e nao tem cavidade", globo is not None and np.array_equal(
        ndimage.binary_fill_holes(globo), globo))
    rg, re_, rf = (_superficie_por_volume(g), _superficie_por_volume(esfera),
                   _superficie_por_volume(globo))
    checar(u"a irregularidade fica ENTRE a do olho do modelo e a da esfera",
           re_ < rf < rg, u"modelo %.3f, globo %.3f, esfera %.3f"
           % (rg, rf, re_))
    for f, rot in ((1.0, u"so o modelo"), (0.0, u"so a esfera")):
        gi = RC.globo_ocular(olho, lente, G, fator=f)
        ri = _superficie_por_volume(gi)
        checar(u"ISCA: fator %g (%s) sai do meio" % (f, rot),
               not (re_ < ri < rg), u"%.3f" % ri)
    vel = RC.radai_geom.preencher_buracos
    RC.radai_geom.preencher_buracos = lambda m, **kw: np.asarray(m, bool)
    try:
        gb = RC.globo_ocular(olho, lente, G, fator=1.0)
    finally:
        RC.radai_geom.preencher_buracos = vel
    checar(u"ISCA: sem preencher (e so o modelo), a cavidade fica",
           not np.array_equal(ndimage.binary_fill_holes(gb), gb))
    gv = RC.globo_ocular(olho, lente, G, vizinhos=nervo)
    gs = RC.globo_ocular(olho, lente, G)
    checar(u"com o nervo optico encostado, o globo nao invade o nervo",
           not (gv & nervo & ~(olho | lente)).any())
    checar(u"ISCA: sem os vizinhos, o globo invadiria o nervo",
           bool((gs & nervo & ~(olho | lente)).any()))
    spec = E.CONSTRUCOES_POR_SAIDA()["eye_left"]
    checar(u"no OAR estrito, Eye x Lens nao alarma",
           not E.sobreposicoes({"eye_left": globo, "eye_lens_left": lente}, G,
                               construcoes={"eye_left": spec}, estrito=True))
    sem = dict(spec)
    sem["contem"] = ()
    velho_ce = E.CONTIDAS_EM
    E.CONTIDAS_EM = {}
    try:
        so_contem = E.sobreposicoes({"eye_left": globo, "eye_lens_left": lente},
                                    G, construcoes={"eye_left": spec},
                                    estrito=True)
        nada = E.sobreposicoes({"eye_left": globo, "eye_lens_left": lente}, G,
                               construcoes={"eye_left": sem}, estrito=True)
    finally:
        E.CONTIDAS_EM = velho_ce
    checar(u"  e e o `contem` da construcao que cala o par (sem a contencao "
           u"do cristalino na tabela)", not so_contem, str(so_contem))
    checar(u"ISCA: sem o `contem` e sem a contencao, o par alarma",
           bool(nada))
    tmp = tempfile.mkdtemp(prefix="radai_t_motor2_")
    sessao = None
    try:
        serie = _serie(tmp)
        cruas = _cruas([("eye_left", "head_glands_cavities", olho),
                        ("eye_lens_left", "head_glands_cavities", lente),
                        ("optic_nerve_left", "head_glands_cavities", nervo),
                        ("spinal_cord", "total_v3", caixa(0, 29, 90, 96,
                                                          60, 66))])
        sd, r, _l = _rodar(tmp, serie, cruas)
        mf = sd.meta_do_full["mascaras"]
        eye, lens = np.asarray(mf["eye_left"], bool), np.asarray(
            mf["eye_lens_left"], bool)
        checar(u"cadeia: o Eye_L_ai do FULL contem o Lens_L_ai final",
               lens.any() and not (lens & ~eye).any())
        checar(u"  e os dois vao ao OAR",
               {"Eye_L_ai", "Lens_L_ai"} <= set(r["estruturas"]))
        checar(u"  e a descricao do Eye_L_ai diz o globo",
               u"Globo ocular" in _obs(r["oar"]).get("Eye_L_ai", u""))
        import radai_rt
        sessao = radai_rt.abrir(serie, r["oar"])
        ev, lv = sessao.mascara("Eye_L_ai"), sessao.mascara("Lens_L_ai")
        checar(u"na volta RTSTRUCT -> mascara, o Lens fica dentro do Eye",
               lv.any() and (lv & ev).sum() >= 0.98 * lv.sum(),
               u"%.3f" % ((lv & ev).sum() / float(max(1, lv.sum()))))
    finally:
        if sessao is not None:
            shutil.rmtree(sessao.pasta_limpa, ignore_errors=True)
        shutil.rmtree(tmp, ignore_errors=True)


def _abdome(com_ilha=False):
    m = {
        "abdominal_cavity": caixa(0, 30, 30, 101, 25, 104),
        "small_intestine": (caixa(8, 22, 36, 60, 42, 87)
                            | caixa(12, 17, 70, 78, 70, 79)),
        "colon": caixa(9, 27, 40, 51, 30, 39),
        "duodenum": caixa(20, 27, 60, 67, 60, 71),
        "rectum": caixa(0, 9, 72, 81, 60, 69),
        "psoas_major_left": caixa(5, 26, 78, 89, 70, 79),
        "psoas_major_right": caixa(5, 26, 78, 89, 44, 53),
        "vertebrae_L4": caixa(12, 30, 88, 101, 58, 71),
        "aorta": caixa(10, 30, 80, 87, 60, 67),
        "inferior_vena_cava": caixa(10, 30, 80, 87, 53, 59),
        "kidney_left": caixa(18, 29, 70, 91, 85, 98),
        "kidney_right": caixa(18, 29, 70, 91, 31, 44),
        "sacrum": caixa(0, 11, 85, 101, 54, 75),
        "femur_left": caixa(0, 5, 60, 81, 90, 101),
        "femur_right": caixa(0, 5, 60, 81, 28, 39),
        "urinary_bladder": caixa(0, 7, 35, 51, 55, 76),
        "prostate": caixa(0, 4, 52, 61, 60, 69),
        "stomach": caixa(22, 28, 34, 47, 78, 95),
        "pancreas": caixa(22, 27, 50, 59, 72, 89),
        "liver": caixa(27, 30, 32, 61, 26, 51),
    }
    if com_ilha:
        m["small_intestine"] = m["small_intestine"] | caixa(2, 5, 96, 100,
                                                            40, 47)
    skin = caixa(0, 30, 20, 113, 15, 116) & ~caixa(0, 30, 32, 111, 27, 114)
    m["Skin"] = skin
    return m, skin


def _alcas_de(m):
    return m["small_intestine"] | m["colon"] | m["duodenum"]


def _bag(m, construidas=None, log=None):
    c = RC.bag_bowel_oar(dict(m), G, log=log,
                         construidas=construidas or {"Skin": m["Skin"]})
    return None if c is None else np.asarray(c.mascara, bool), c


def teste_a_bag_bowel_oar_e_construcao_registrada():
    secao(u"v8.5: a Bag_Bowel_OAR e uma construcao registrada")
    c = [x for x in E.CONSTRUCOES if x.get("cod") == "bag_bowel_oar"]
    checar(u"a entrada existe, no_fim, exige a cavidade abdominal",
           len(c) == 1 and c[0]["momento"] == "no_fim"
           and tuple(c[0]["exige"]) == ("abdominal_cavity",))
    cods = [x.get("cod") for x in E.CONSTRUCOES]
    checar(u"  e vem depois da pele (recebe a Skin pronta)",
           cods.index("bag_bowel_oar") > cods.index("pele_e_parede"))
    checar(u"  e o nome antigo nao e mais construido",
           "bag_bowel_test" not in cods
           and "bag_bowel_test" not in E.CONSTRUCOES_POR_SAIDA())
    nome = E.nome_clinico("bag_bowel_oar")
    checar(u"o nome e Bag_Bowel_OAR_ai (16), e nao colide com Bag_Bowel_ai",
           nome == "Bag_Bowel_OAR_ai" and len(nome) <= 16
           and nome != E.nome_clinico("bag_bowel"), nome)
    velho = E.TG263["bag_bowel_oar"]
    E.TG263["bag_bowel_oar"] = "Bag_Bowel_OARx"
    try:
        ni = E.nome_clinico("bag_bowel_oar")
    finally:
        E.TG263["bag_bowel_oar"] = velho
    checar(u"ISCA: com um caractere a mais o nome passaria de 16 e seria "
           u"cortado", ni != "Bag_Bowel_OARx_ai" and len(ni) <= 16, ni)
    checar(u"no OAR e fora do OAR_Fast",
           "bag_bowel_oar" in RS.PERMITIDOS_NO_OAR
           and "bag_bowel_oar" not in RS.PERMITIDOS_NO_OAR_FAST)
    checar(u"a Bag_Bowel_ai de antes fica so no FULL (fora do OAR e do FAST)",
           "bag_bowel" not in RS.PERMITIDOS_NO_OAR
           and "bag_bowel" not in RS.PERMITIDOS_NO_OAR_FAST
           and any(x.get("cod") == "bag_bowel" for x in E.CONSTRUCOES))
    checar(u"o nome esta marcado a conferir (forma nossa)",
           "bag_bowel_oar" in E.TG263_A_CONFERIR)
    checar(u"a cor e outra que a da Bag_Bowel",
           E._color("bag_bowel_oar", False) != E._color("bag_bowel", False))
    import hashlib
    src = inspect.getsource(RC.bag_bowel)
    h = hashlib.sha256(ast.dump(_sem_docstrings(ast.parse(src))).encode(
        "utf-8")).hexdigest()
    checar(u"a receita da Bag_Bowel_ai nao mudou (a comparacao)",
           h == HASH_DA_BAG_BOWEL, h[:16])
    hi = hashlib.sha256(ast.dump(_sem_docstrings(ast.parse(src.replace(
        "SUAVIZACAO_BAG_MM if", "SUAVIZACAO_BAG_OAR_MM if")))).encode(
        "utf-8")).hexdigest()
    hd = hashlib.sha256(ast.dump(_sem_docstrings(ast.parse(src.replace(
        "):\n", "):\n    u\"\"\"uma docstring nova\"\"\"\n", 1)))).encode(
        "utf-8")).hexdigest()
    checar(u"  e uma docstring nova nao muda a impressao (so o codigo conta)",
           hd == h)
    checar(u"ISCA: a receita da Bag_Bowel_ai mexida muda a impressao",
           hi != HASH_DA_BAG_BOWEL)
    checar(u"a suavizacao final e de 20 mm (o dobro dos 10 de antes)",
           RC.SUAVIZACAO_BAG_OAR_MM == 20.0)
    checar(u"a folga dos vizinhos e de 5 mm",
           RC.FOLGA_DOS_VIZINHOS_DA_BAG_MM == 5.0)


HASH_DA_BAG_BOWEL = (
    "3458dedfee9226736d62f0c5a86fa77973cc480f8ce7cbc9dcd1de03da3c5c96")


def _sem_docstrings(arv):
    for n in ast.walk(arv):
        if isinstance(n, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                          ast.ClassDef)) and n.body \
                and isinstance(n.body[0], ast.Expr) \
                and isinstance(getattr(n.body[0], "value", None), ast.Constant) \
                and isinstance(n.body[0].value.value, str):
            n.body.pop(0)
            if not n.body:
                n.body.append(ast.Pass())
    return arv


_NOME_NA_DESCRICAO_DA_BAG_OAR = dict(
    [("liver", u"figado"), ("gallbladder", u"vesicula"),
     ("urinary_bladder", u"bexiga"), ("spleen", u"baco"),
     ("kidney_", u"rins"), ("adrenal_gland_", u"adrenais"),
     ("prostate", u"prostata"), ("Skin", u"pele"),
     ("aorta", u"grandes vasos"), ("inferior_vena_cava", u"grandes vasos"),
     ("iliac_artery_", u"grandes vasos"), ("iliac_vena_", u"grandes vasos")]
    + [(n, u"orgaos do torax")
       for n in ("esophagus", "heart", "pericardium", "lung_")]
    + [(n, u"musculos")
       for n in ("quadratus_lumborum", "gluteus_", "autochthon",
                 "erector_spinae", "rectus_abdominis", "external_oblique",
                 "internal_oblique", "transversus", "piriformis",
                 "obturator", "levator_ani")]
    + [(n, u"psoas") for n in ("psoas",)]
    + [(n, u"iliopsoas") for n in ("iliopsoas_",)]
    + [(n, u"ossos")
       for n in ("vertebrae_", "sacrum", "hip_", "femur_", "coccyx")])


def _o_que_a_descricao_da_bag_oar_esquece(texto):
    texto = texto or u""
    falta = []
    for tupla in (RC.ORGAOS_FORA_DA_BAG, RC.ORGAOS_DO_TORAX_FORA_DA_BAG,
                  RC.ORGAOS_FORA_DA_BAG_OAR, RC.MUSCULOS_FORA_DA_BAG_OAR,
                  RC.OSSOS_FORA_DA_BAG_OAR, RC.CONSTRUCOES_FORA_DA_BAG_OAR,
                  RC.PSOAS, RC.LOJA_RENAL, RC.ILIOPSOAS, RC.BACO,
                  RC.GRANDES_VASOS_DO_RETROPERITONIO):
        for n in tupla:
            pt = _NOME_NA_DESCRICAO_DA_BAG_OAR.get(n)
            if pt is None or pt not in texto:
                falta.append(n)
    if RC.vasos_do_motor() and u"vasos" not in texto:
        falta.append("vasos")
    for frase in (u"grandes veias", u"grandes arterias", u"Veia porta"):
        if frase not in texto:
            falta.append(frase)
    return falta


def teste_a_bag_bowel_ai_declara_a_prostata():
    secao(u"a Bag_Bowel_ai diz na descricao a prostata que contem")
    m, skin = _abdome()
    m["abdominal_cavity"] = m["abdominal_cavity"] | m["prostate"]
    linhas = []
    c = RC.bag_bowel_declarada(dict(m), G, log=linhas.append)
    bag = np.asarray(c.mascara, bool)
    dentro = bool((bag & m["prostate"]).any())
    checar(u"(pre-condicao) a receita de comparacao deixa a prostata dentro",
           dentro)
    checar(u"a descricao diz quanto da prostata ficou e que nao e descontada",
           u"da prostata, que nao e descontada" in c.descricao, c.descricao)
    checar(u"  e o log tambem", any(u"prostata" in l for l in linhas))
    puro = RC.bag_bowel(dict(m), G)
    checar(u"  ISCA: a receita sozinha nao diz", u"prostata"
           not in puro.descricao)
    checar(u"  e a mascara e a da receita com o pancreas inteiro (a prostata "
           u"so muda a frase)",
           np.array_equal(np.asarray(puro.mascara, bool) | m["pancreas"],
                          bag))
    fonte = inspect.getsource(E._construir_bag_bowel)
    checar(u"o motor monta a Bag_Bowel_ai pela versao que declara",
           "bag_bowel_declarada" in fonte)


def teste_a_receita_da_bag_bowel_oar():
    secao(u"v8.5: a receita da Bag_Bowel_OAR, no fantoma abdominopelvico")
    m, skin = _abdome()
    linhas = []
    bag, c = _bag(m, log=linhas.append)
    checar(u"a Bag_Bowel_OAR sai", bag is not None and bag.any(),
           u" | ".join(linhas)[:300])
    if bag is None:
        return
    seis = ndimage.generate_binary_structure(3, 1)
    checar(u"um componente 3D (6 vizinhos)",
           int(ndimage.label(bag, structure=seis)[1]) == 1)
    alcas = _alcas_de(m) | m["stomach"] | m["pancreas"]
    meso = RC.compartimento_mesorretal(m["rectum"], m["sacrum"], G)
    checar(u"nada do compartimento mesorretal (fora das alcas)",
           not (bag & meso & ~alcas).any(),
           u"%d voxels" % int((bag & meso & ~alcas).sum()))
    velho = RC.compartimento_mesorretal
    RC.compartimento_mesorretal = lambda *a, **k: None
    try:
        bi, _c = _bag(m)
    finally:
        RC.compartimento_mesorretal = velho
    checar(u"ISCA: sem o mesorreto, a Bag entra no espaco pre-sacral",
           bool((bi & meso & ~alcas).any()))
    ps = m["psoas_major_left"] | m["psoas_major_right"]
    atras = radai_geom.expandir(ps, {"post": 20.0}, G) & ~ps
    checar(u"nada dentro do psoas nem ate 20 mm atras dele (fora das alcas)",
           not (bag & ps).any() and not (bag & atras & ~alcas).any())
    duros = (m["kidney_left"] | m["kidney_right"] | m["aorta"]
             | m["inferior_vena_cava"])
    loja = (radai_geom.expandir(m["kidney_left"] | m["kidney_right"],
                                {"post": 30.0}, G)
            & ~(m["kidney_left"] | m["kidney_right"]))
    checar(u"nada nos rins, na aorta, na cava, nem atras da loja renal",
           not (bag & duros).any() and not (bag & loja & ~alcas).any())
    perto = (radai_geom.expandir(m["aorta"] | m["inferior_vena_cava"], 5.0, G)
             & ~(m["aorta"] | m["inferior_vena_cava"]))
    checar(u"nada a 5 mm da aorta nem da cava (fora dos orgaos inteiros)",
           not (bag & perto & ~alcas).any(),
           u"%d voxels" % int((bag & perto & ~alcas).sum()))
    velho_f = RC.FOLGA_DOS_VIZINHOS_DA_BAG_MM
    RC.FOLGA_DOS_VIZINHOS_DA_BAG_MM = 0.5
    try:
        bf, _c = _bag(m)
    finally:
        RC.FOLGA_DOS_VIZINHOS_DA_BAG_MM = velho_f
    checar(u"ISCA: sem a folga de 5 mm, a Bag encosta na aorta e na cava",
           bool((bf & perto & ~alcas).any()))
    velho_r = RC.reaplicar_exclusoes
    RC.reaplicar_exclusoes = lambda b, livre: b
    try:
        bi3, _c = _bag(m)
    finally:
        RC.reaplicar_exclusoes = velho_r
    checar(u"ISCA: sem reaplicar as exclusoes, a suavizacao devolve a lamina",
           bool((bi3 & (duros | ps)).any()))
    cav = m["abdominal_cavity"]
    ant = np.where(cav.any(axis=1), cav.argmax(axis=1), 10 ** 6)
    yy = np.arange(Y)[None, :, None]
    longe = cav & (yy > ant[:, None, :] + int(round(50.0 / 2.0)))
    longe[5:] = False
    checar(u"sem a sacroiliaca no fantoma, do polo da cabeca femoral para "
           u"baixo nada a mais de 50 mm da parede anterior (fora das alcas)",
           not (bag & longe & ~alcas).any())
    checar(u"  e a descricao diz que o caudal foi pela cabeca femoral",
           RC.NOTA_DO_CAUDAL_PELO_FEMUR in c.descricao)
    velho_c = RC.caudal_posterior
    RC.caudal_posterior = lambda *a, **k: None
    try:
        bi4, _c = _bag(m)
    finally:
        RC.caudal_posterior = velho_c
    checar(u"ISCA: sem o corte caudal, a Bag desce atras",
           bool((bi4 & longe & ~alcas).any()))
    for nome in ("small_intestine", "colon", "duodenum", "stomach",
                 "pancreas"):
        checar(u"cobertura de `%s`: 100%%" % nome,
               not (m[nome] & ~bag).any())
    checar(u"  e sem conflito no log", not any(u"CONFLITO" in l
                                              for l in linhas))
    checar(u"nada na prostata nem na pele",
           not (bag & m["prostate"]).any() and not (bag & skin).any())
    d = c.descricao
    for palavra in (u"estomago", u"pancreas", u"Orton", u"exclui",
                    u"prostata", u"figado", u"bexiga", u"rins", u"adrenais",
                    u"vasos", u"musculos", u"psoas", u"ossos", u"pele",
                    u"loja perirrenal", u"retroperitonio", u"mesorreto",
                    u"cabeca femoral", u"sacroiliaca", u"Veia porta",
                    u"5 mm", u"20 mm", u"inteiros",
                    u"doi:10.1016/j.adro.2022.101031", u"Cobertura:"):
        checar(u"a descricao diz «%s»" % palavra, palavra in d)
    checar(u"a descricao nao diz mais EXPERIMENTAL", u"EXPERIMENTAL" not in d)
    checar(u"a descricao cita cada exclusao da receita (conferida contra as "
           u"tuplas)", not _o_que_a_descricao_da_bag_oar_esquece(d),
           str(_o_que_a_descricao_da_bag_oar_esquece(d)))
    checar(u"ISCA: a frase sem «prostata» e acusada",
           _o_que_a_descricao_da_bag_oar_esquece(
               d.replace(u"prostata, ", u"")) == ["prostate"])
    velho = RC.MUSCULOS_FORA_DA_BAG_OAR
    RC.MUSCULOS_FORA_DA_BAG_OAR = velho + ("musculo_novo",)
    try:
        novo = _o_que_a_descricao_da_bag_oar_esquece(d)
    finally:
        RC.MUSCULOS_FORA_DA_BAG_OAR = velho
    checar(u"ISCA: musculo novo na receita sem nome nesta regua e acusado",
           novo == ["musculo_novo"], str(novo))
    todas = {"delgado": 0.5, "colon": 0.5, "duodeno": 0.5, "estomago": 0.5,
             "pancreas": 0.5}
    longa = RC.descricao_da_bag_oar(
        todas, [("delgado", 123.4, u"x"), ("colon", 44.0, u"y")],
        [u"sem Rectum_ai, compartimento mesorretal nao aplicado",
         RC.NOTA_DO_COLON_SEM_RETO % 999.9, RC.NOTA_DO_CAUDAL_PELO_FEMUR])
    checar(u"a frase mais longa da serie cabe no campo DICOM com folga",
           len(longa) <= 1000, str(len(longa)))
    longa2 = RC.descricao_da_bag_oar(
        todas, [("delgado", 123.4, u"x"), ("colon", 44.0, u"y")],
        [u"sem Rectum_ai, compartimento mesorretal nao aplicado",
         RC.NOTA_SEM_CAUDAL, RC.NOTA_DO_COLON_INTEIRO])
    checar(u"  e a sem marco caudal nenhum tambem", len(longa2) <= 1000,
           str(len(longa2)))
    m2 = dict(m)
    for k in ("rectum", "femur_left", "femur_right"):
        m2.pop(k)
    _b2, c2 = _bag(m2)
    checar(u"sem reto e sem femur, a descricao diz o que nao foi aplicado",
           c2 is not None and u"sem Rectum_ai, compartimento mesorretal nao "
           u"aplicado" in c2.descricao and RC.NOTA_SEM_CAUDAL
           in c2.descricao, (c2.descricao if c2 else u"-")[-200:])


def _com_baco_e_iliopsoas(m):
    m = dict(m)
    m["spleen"] = caixa(20, 27, 40, 52, 96, 104)
    m["iliopsoas_left"] = m.pop("psoas_major_left")
    m["iliopsoas_right"] = m.pop("psoas_major_right")
    m["stomach"] = caixa(20, 28, 34, 47, 88, 96)
    return m


def teste_a_folga_dos_vizinhos_e_os_orgaos_inteiros():
    secao(u"v8.5: 5 mm do iliopsoas e do baco antes da suavizacao, e os "
          u"orgaos ocos inteiros depois")
    m, _skin = _abdome()
    m = _com_baco_e_iliopsoas(m)
    bag, c = _bag(m)
    il = m["iliopsoas_left"] | m["iliopsoas_right"]
    alcas = _alcas_de(m) | m["stomach"] | m["pancreas"]
    perto_il = radai_geom.expandir(il, 5.0, G) & ~il
    checar(u"nada a 5 mm do iliopsoas (fora dos orgaos inteiros)",
           bag is not None and not (bag & perto_il & ~alcas).any(),
           u"%d voxels" % int((bag & perto_il & ~alcas).sum())
           if bag is not None else u"-")
    perto_b = radai_geom.expandir(m["spleen"], 5.0, G) & ~m["spleen"]
    checar(u"nada a 5 mm do baco (fora dos orgaos inteiros)",
           not (bag & perto_b & ~alcas).any(),
           u"%d voxels" % int((bag & perto_b & ~alcas).sum()))
    checar(u"o estomago, encostado no baco, entra INTEIRO mesmo assim",
           not (m["stomach"] & ~bag).any()
           and bool((m["stomach"] & perto_b).any()))
    velho = RC.INTEIROS_DEPOIS_DA_SUAVIZACAO
    RC.INTEIROS_DEPOIS_DA_SUAVIZACAO = ()
    try:
        bi, _c = _bag(m)
    finally:
        RC.INTEIROS_DEPOIS_DA_SUAVIZACAO = velho
    checar(u"ISCA: sem somar os inteiros, a folga do baco come o estomago",
           bi is not None and bool((m["stomach"] & ~bi).any()))
    novo, _desc, cob, _conf = RC.acabamento_da_bag_oar(bag, dict(m), G)
    novo = np.asarray(novo, bool)
    checar(u"o acabamento (segunda passada) devolve os inteiros e mantem a "
           u"folga", not (m["stomach"] & ~novo).any()
           and not (novo & perto_il & ~alcas).any())


def teste_a_veia_porta_fora_de_toda_conta():
    secao(u"v8.5: a veia porta nao entra em conta nenhuma da Bag_Bowel_OAR")
    m, _skin = _abdome()
    porta = caixa(22, 27, 48, 52, 52, 60)
    m["portal_vein_and_splenic_vein"] = porta
    m["great_veins"] = porta | m["inferior_vena_cava"]
    bag, c = _bag(m)
    checar(u"a porta fica dentro da bag (nem exclusao, nem folga)",
           bag is not None and not (porta & ~bag).any(),
           u"%d voxels fora" % int((porta & ~bag).sum())
           if bag is not None else u"-")
    checar(u"  e as listas da bag nao a citam",
           not any(n.startswith("portal") for n in RC.vasos_da_bag_oar())
           and not any(n.startswith("portal")
                       for n in RC.vizinhos_com_margem_da_bag())
           and "great_veins" not in RC.vasos_da_bag_oar())
    velho = RC.vasos_da_bag_oar
    RC.vasos_da_bag_oar = lambda: velho() + ("portal_vein_and_splenic_vein",
                                             "great_veins")
    try:
        bi, _c = _bag(m)
    finally:
        RC.vasos_da_bag_oar = velho
    checar(u"ISCA: com a porta entre as exclusoes (como era), a bag fura",
           bi is not None and bool((porta & ~bi).any()))
    spec = E.CONSTRUCOES_POR_SAIDA()["bag_bowel_oar"]
    checar(u"o recorte da segunda passada nao cita a porta nem o composto "
           u"das grandes veias",
           not any(str(n).startswith("portal") or n == "great_veins"
                   for n in spec["recortar_por"]))
    checar(u"  e a contencao declara as grandes veias e a porta (sem alarme "
           u"no OAR)", {"great_veins", "portal_vein_and_splenic_vein"}
           <= set(spec["contem"]))


def teste_o_corte_caudal_pela_sacroiliaca():
    secao(u"v8.5: a exclusao infero-posterior sobe para a borda inferior da "
          u"sacroiliaca")
    m, _skin = _abdome()
    m["hip_left"] = caixa(6, 16, 80, 100, 76, 90)
    m["hip_right"] = caixa(6, 16, 80, 100, 39, 53)
    m["sacrum"] = caixa(0, 16, 85, 101, 54, 75)
    j = E.desenhar_juncao_sacroiliaca(m, G)
    checar(u"(pre-condicao) o fantoma tem a juncao sacroiliaca",
           j is not None and j.any())
    z_inf = int(np.flatnonzero(j.any(axis=(1, 2))).min()) if j is not None \
        else -1
    z_lim, marco, nota = RC.marco_caudal(m, G)
    checar(u"o marco caudal e a borda inferior da sacroiliaca",
           marco == RC.MARCO_CAUDAL_SACROILIACA and z_lim == z_inf
           and nota is None, u"%s %s %s" % (z_lim, z_inf, marco))
    bag, c = _bag(m)
    cav = m["abdominal_cavity"]
    alcas = _alcas_de(m) | m["stomach"] | m["pancreas"]
    ant = np.where(cav.any(axis=1), cav.argmax(axis=1), 10 ** 6)
    yy = np.arange(Y)[None, :, None]
    longe = cav & (yy > ant[:, None, :] + int(round(50.0 / 2.0)))
    longe[z_inf + 1:] = False
    checar(u"da borda inferior da sacroiliaca para baixo, nada a mais de "
           u"50 mm da parede anterior (fora das alcas)",
           bag is not None and not (bag & longe & ~alcas).any())
    m2 = dict(m)
    for k in ("hip_left", "hip_right"):
        m2.pop(k)
    z2, marco2, nota2 = RC.marco_caudal(m2, G)
    checar(u"ISCA: sem a sacroiliaca, o marco volta ao polo da cabeca "
           u"femoral (mais baixo)", marco2 == RC.MARCO_CAUDAL_FEMUR
           and z2 is not None and z2 < z_lim
           and nota2 == RC.NOTA_DO_CAUDAL_PELO_FEMUR, u"%s %s" % (z2, z_lim))


def teste_a_bag_oar_sem_reto_separado():
    secao(u"v8.5: sem Rectum_ai, o reto nao volta pela alca do colon")
    m, _skin = _abdome()
    reto = m.pop("rectum")
    m["colon"] = m["colon"] | reto
    caudal = caixa(0, 5, 0, Y, 0, X)
    reto_baixo = reto & caudal
    linhas = []
    bag, c = _bag(m, log=linhas.append)
    checar(u"o reto abaixo do marco caudal fica fora da bag",
           bag is not None and not (bag & reto_baixo).any(),
           u"%d voxel(s)" % (int((bag & reto_baixo).sum())
                             if bag is not None else -1))
    checar(u"  e o resto do colon e o delgado voltam inteiros",
           bag is not None
           and not ((m["colon"] & ~reto) & ~bag).any()
           and not (m["small_intestine"] & ~bag).any())
    checar(u"  a descricao diz que o reto nao foi separado",
           c is not None and u"o reto nao foi separado" in c.descricao,
           (c.descricao if c else u"-")[-240:])
    checar(u"  e o colon retido nao vira conflito",
           c is not None and not [x for x in c.extras["conflitos"]
                                  if x[0] == "colon"],
           str(c.extras["conflitos"] if c else None))
    novo, desc, _cob, _conf = RC.acabamento_da_bag_oar(bag, dict(m), G)
    checar(u"  e a segunda passada nao o devolve",
           not (np.asarray(novo, bool) & reto_baixo).any()
           and u"o reto nao foi separado" in desc)
    velho = RC._alcas_que_voltam

    def _todas(masks, cav, grade, cru=None):
        a = None
        for _r, b in RC._alcas(masks, cru):
            a = b.copy() if a is None else (a | b)
        return a, None, None, None
    RC._alcas_que_voltam = _todas
    try:
        bi, _ci = _bag(m)
    finally:
        RC._alcas_que_voltam = velho
    checar(u"ISCA: com o colon inteiro voltando, o reto baixo entra na bag",
           bi is not None and (bi & reto_baixo).any())
    m3 = dict(m)
    for k in ("femur_left", "femur_right"):
        m3.pop(k)
    _b3, c3 = _bag(m3)
    checar(u"sem reto e sem femur: a descricao diz que o colon volta "
           u"inteiro, reto incluido",
           c3 is not None and RC.NOTA_DO_COLON_INTEIRO in c3.descricao)


NOMES_DO_QUE_O_FAST_NAO_LEVA = {"bag_bowel_oar": u"Bag_Bowel_OAR",
                                "anus": u"Anus"}


def _diz_o_que_o_fast_nao_leva(texto, fora):
    return (all(k in NOMES_DO_QUE_O_FAST_NAO_LEVA
                and NOMES_DO_QUE_O_FAST_NAO_LEVA[k] in texto for k in fora)
            and u"Muscles_ai" not in texto
            and u"Bag_Bowel_test" not in texto)


def teste_os_textos_do_fast_dizem_o_que_ele_nao_leva():
    secao(u"os textos do OAR_Fast dizem o que ele nao leva")
    fora = sorted(RS.FORA_DO_OAR_FAST)
    checar(u"toda chave de FORA_DO_OAR_FAST tem nome na regua desta checagem",
           set(fora) <= set(NOMES_DO_QUE_O_FAST_NAO_LEVA), str(fora))
    fast = RS.POR_COD["fast"]
    for campo in ("rotulo", "ajuda"):
        checar(u"radai_sets: o `%s` do FAST diz o que ele nao leva" % campo,
               _diz_o_que_o_fast_nao_leva(fast[campo], fora), fast[campo])
    velha = (u"entregue ao TPS (modo FAST) — o OAR sem a Bag_Bowel e a "
             u"Bag_Bowel_test, compostos suavizados inteiros")
    checar(u"ISCA: o texto de antes (com a Bag_Bowel_test) reprova",
           not _diz_o_que_o_fast_nao_leva(velha, fora))
    t = E._textos_do_oar_fast(None, u"x", u"_ai", [], [], 1.5,
                              0.2)["StructureSetDescription"]
    checar(u"o StructureSetDescription do OAR_Fast nomeia o que sai, pelo "
           u"nome no TPS, e nao diz Muscles_ai",
           all(E.nome_clinico(k) in t for k in fora)
           and u"Muscles_ai" not in t, t[:200])
    velho = RS.FORA_DO_OAR_FAST
    RS.FORA_DO_OAR_FAST = frozenset()
    try:
        ti = E._textos_do_oar_fast(None, u"x", u"_ai", [], [], 1.5,
                                   0.2)["StructureSetDescription"]
    finally:
        RS.FORA_DO_OAR_FAST = velho
    checar(u"ISCA: o texto do DICOM sai do conjunto (sem nada fora, a "
           u"Bag_Bowel_OAR some do texto)",
           E.nome_clinico("bag_bowel_oar") not in ti, ti[:200])


def teste_a_bag_oar_sem_ponte():
    secao(u"v8.5: alca isolada vira conflito, e nao ponte")
    m, _skin = _abdome(com_ilha=True)
    linhas = []
    bag, c = _bag(m, log=linhas.append)
    ilha = caixa(2, 5, 96, 100, 40, 47)
    entre = caixa(2, 5, 56, 96, 40, 47)
    seis = ndimage.generate_binary_structure(3, 1)
    checar(u"continua um componente", bag is not None and int(
        ndimage.label(bag, structure=seis)[1]) == 1)
    checar(u"a alca isolada fica fora, e o log diz CONFLITO",
           not (bag & ilha).any()
           and any(u"CONFLITO" in l and u"delgado" in l for l in linhas),
           u" | ".join(l for l in linhas if u"Bag" in l)[:300])
    checar(u"  e a descricao diz o conflito",
           u"Conflito:" in c.descricao and u"revisar" in c.descricao)
    checar(u"nenhuma ponte entre a alca e o corpo da Bag",
           not (bag & entre).any())
    velho = radai_geom.maior_componente
    radai_geom.maior_componente = lambda mk, conectividade=1, abrir=0: \
        np.asarray(mk, bool).copy()
    try:
        bi, _c = _bag(m)
    finally:
        radai_geom.maior_componente = velho
    checar(u"ISCA: sem o «um volume», a Bag sai em dois pedacos",
           int(ndimage.label(bi, structure=seis)[1]) >= 2)

    def _fecha(mk, conectividade=1, abrir=0):
        mk = np.asarray(mk, bool)
        return radai_geom.contrair(radai_geom.expandir(mk, 60.0, G), 60.0, G)
    radai_geom.maior_componente = _fecha
    try:
        bi2, _c = _bag(m)
    finally:
        radai_geom.maior_componente = velho
    checar(u"ISCA: um fechamento depois das alcas cria a ponte",
           bool((bi2 & entre).any()))


def teste_a_contencao_declarada_da_bag_oar():
    secao(u"v8.5: a sobreposicao esperada da Bag_Bowel_OAR, no FULL estrito")
    spec = E.CONSTRUCOES_POR_SAIDA()["bag_bowel_oar"]
    spec_v = E.CONSTRUCOES_POR_SAIDA()["bag_bowel"]
    a = caixa(5, 20, 40, 80, 40, 80)
    b = caixa(5, 20, 45, 85, 40, 80)
    par = E.sobreposicoes({"bag_bowel": a, "bag_bowel_oar": b}, G,
                          construcoes={"bag_bowel": spec_v,
                                       "bag_bowel_oar": spec}, estrito=True)
    checar(u"Bag_Bowel_ai x Bag_Bowel_OAR_ai nao alarma no FULL", not par,
           str(par))
    sem = dict(spec)
    sem["contem"] = tuple(x for x in spec["contem"] if x != "bag_bowel")
    par_i = E.sobreposicoes({"bag_bowel": a, "bag_bowel_oar": b}, G,
                            construcoes={"bag_bowel": spec_v,
                                         "bag_bowel_oar": sem}, estrito=True)
    checar(u"ISCA: sem `bag_bowel` no contem, o par alarma", bool(par_i))
    checar(u"o reto NAO esta no contem (reto dentro da Bag e alarme)",
           "rectum" not in spec["contem"])


def _o_acabamento_vai_ao_registro(meta_do_full):
    import radai_batch as RB
    import radai_records as RG
    import radai_watcher as W
    pr = RB.processamento_do_caso({}, "auto", meta_entrega=meta_do_full)
    ac = [x for x in (pr.get("acabamento") or [])
          if x.get("estrutura") == "bag_bowel_oar"]
    checar(u"registro (Rodar agora): a cobertura final da Bag_Bowel_OAR vai "
           u"ao processamento do caso",
           ac and set(ac[0]["cobertura"]) >= {"delgado", "colon"}
           and "conflitos" in ac[0], str(pr.get("acabamento"))[:200])
    caso = RG.Caso()
    caso.processamento(**pr)
    checar(u"  e o caso a guarda (campo permitido, e nao ignorado)",
           caso.d["processamento"].get("acabamento") == pr["acabamento"]
           and "acabamento" not in (caso.d["processamento"].get(
               "campos_ignorados") or []))
    pego = {}
    velho = RG.registrar_serie

    def _pega(**kw):
        pego.update(kw)
        return u""
    RG.registrar_serie = _pega
    try:
        W._montar_e_registrar_caso(
            {"uid": u"1.2.826.0.1.3680043.2.1125.1", "pid": u"SINTETICO"},
            0.0, {"ok": True,
                  "acabamento": dict(meta_do_full.get("acabamento") or {})},
            None)
    finally:
        RG.registrar_serie = velho
    checar(u"registro (vigia): a mesma medida, pela mesma funcao",
           (pego.get("processamento") or {}).get("acabamento")
           == pr["acabamento"],
           str((pego.get("processamento") or {}).get("acabamento"))[:200])
    vc = RG.CAMPOS_DO_PROCESSAMENTO
    RG.CAMPOS_DO_PROCESSAMENTO = tuple(c for c in vc if c != "acabamento")
    try:
        ci = RG.Caso()
        ci.processamento(**pr)
    finally:
        RG.CAMPOS_DO_PROCESSAMENTO = vc
    checar(u"ISCA: sem o campo permitido, o caso o ignora",
           "acabamento" not in ci.d["processamento"])
    conf = RG.acabamento_do_caso(
        {"bag_bowel_oar": {"cobertura": {"delgado": 0.98765},
                           "conflitos": [("delgado", 1.234,
                                          u"sobre exclusao dura")]}})
    checar(u"o conflito vai ao caso com a alca, os cm3 e o motivo",
           conf == [{"estrutura": "bag_bowel_oar",
                     "cobertura": {"delgado": 0.9877},
                     "conflitos": [{"alca": "delgado", "cm3": 1.23,
                                    "motivo": u"sobre exclusao dura"}]}],
           str(conf))


def teste_a_bag_oar_na_volta_do_rtstruct():
    secao(u"v8.5: a Bag_Bowel_OAR na cadeia e na volta RTSTRUCT -> mascara")
    tmp = tempfile.mkdtemp(prefix="radai_t_motor2_")
    sessao = None
    try:
        serie = _serie(tmp)
        itens = [("abdominal_cavity", "trunk_cavities",
                  caixa(0, 30, 35, 96, 35, 96)),
                 ("small_bowel", "total_v3", caixa(8, 21, 40, 61, 45, 86)),
                 ("colon", "total_v3", caixa(8, 25, 40, 51, 36, 44)),
                 ("kidney_left", "total_v3", caixa(14, 25, 70, 86, 80, 93)),
                 ("aorta", "total_v3", caixa(5, 30, 75, 81, 60, 66)),
                 ("prostate", "total_v3", caixa(0, 4, 35, 42, 46, 53)),
                 ("urinary_bladder", "total_v3", caixa(0, 6, 35, 56, 55, 76))]
        sd, r, linhas = _rodar(tmp, serie, _cruas(itens))
        full, oar = set(r["estruturas_full"]), set(r["estruturas"])
        checar(u"Bag_Bowel_OAR_ai no FULL e no OAR; a Bag_Bowel_ai so no FULL",
               {"Bag_Bowel_OAR_ai", "Bag_Bowel_ai"} <= full
               and "Bag_Bowel_OAR_ai" in oar and "Bag_Bowel_ai" not in oar,
               str(sorted(oar)))
        obs = _obs(r["oar"]).get("Bag_Bowel_OAR_ai", u"")
        checar(u"a descricao no DICOM traz a receita e a cobertura medida "
               u"depois da segunda passada",
               u"Bag_Bowel_OAR: cavidade abdominal" in obs
               and u"Cobertura: delgado" in obs, obs[:200])
        checar(u"  e cita no DICOM cada exclusao da receita",
               not _o_que_a_descricao_da_bag_oar_esquece(obs),
               str(_o_que_a_descricao_da_bag_oar_esquece(obs)))
        checar(u"a medida final vai ao meta do FULL",
               "bag_bowel_oar" in (sd.meta_do_full.get("acabamento") or {}))
        _o_acabamento_vai_ao_registro(sd.meta_do_full)
        import radai_rt
        sessao = radai_rt.abrir(serie, r["full"])
        bag = sessao.mascara("Bag_Bowel_OAR_ai")
        for roi in ("Bowel_Small_ai", "Bowel_Large_ai"):
            alca = sessao.mascara(roi)
            f = (alca & bag).sum() / float(max(1, alca.sum()))
            checar(u"relida: `%s` dentro da Bag" % roi, f >= 0.97,
                   u"%.3f" % f)
        for roi in (E.nome_clinico("kidney_left"), E.nome_clinico("prostate"),
                    E.nome_clinico("urinary_bladder")):
            if roi not in sessao.nomes:
                checar(u"relida: `%s` existe no FULL" % roi, False,
                       str(sessao.nomes))
                continue
            o = sessao.mascara(roi)
            plano = np.zeros((3, 3, 3), bool)
            plano[1] = True
            miolo = ndimage.binary_erosion(o, structure=plano, iterations=2)
            n = int((miolo & bag).sum())
            checar(u"relida: a Bag nao entra em `%s` (alem da borda "
                   u"comum do poligono: meio pixel e Taubin, ate 2%%)" % roi,
                   miolo.any() and n <= 0.02 * o.sum(),
                   u"%d de %d voxels" % (n, int(o.sum())))
        sdf, rf, _lf = _rodar(tmp, serie, _cruas(itens), modo="fast")
        checar(u"no FAST nenhuma das duas sai",
               not ({"Bag_Bowel_OAR_ai", "Bag_Bowel_ai"}
                    & set(rf["estruturas"])))
    finally:
        if sessao is not None:
            shutil.rmtree(sessao.pasta_limpa, ignore_errors=True)
        shutil.rmtree(tmp, ignore_errors=True)


def teste_o_pescoco_exige_a_mandibula():
    secao(u"v8.5: o pescoco exige C2 a C4 E (a mandibula na faixa OU o cranio "
          u"acima do C1)")
    import radai_topography as TP
    import radai_modes as MD
    torax_ate_c1 = dict(_vertebras_do_pescoco(mandibula=False))
    torax_ate_c1["skull"] = caixa(13, 29, 45, 60, 95, 110)
    v = E.mandibula_no_campo_cm3(torax_ate_c1, G)
    tem, laudo = E.pescoco_no_campo(torax_ate_c1, G)
    checar(u"a TC de torax que sobe ao C1 (mandibula de %.0f cm3, abaixo do "
           u"piso de %.0f) NAO e pescoco" % (v, E.VOLUME_MINIMO_DA_MANDIBULA_CM3),
           not tem and v < E.VOLUME_MINIMO_DA_MANDIBULA_CM3, laudo)
    checar(u"  e o laudo diz a mandibula, a faixa e o piso",
           u"mandibula no campo (do topo do C1 ao fim do C4)" in laudo
           and (u"piso %.0f" % E.VOLUME_MINIMO_DA_MANDIBULA_CM3) in laudo,
           laudo)
    checar(u"  e o cranio acima do C1, o piso dele e o caminho (nenhum)",
           u"cranio acima do topo do C1" in laudo
           and (u"piso %.0f" % E.VOLUME_MINIMO_DO_CRANIO_ACIMA_DO_C1_CM3)
           in laudo and u"confirmado por: nenhum" in laudo
           and E.cranio_acima_do_c1_cm3(torax_ate_c1, G)
           < E.VOLUME_MINIMO_DO_CRANIO_ACIMA_DO_C1_CM3, laudo)
    velho_c = E.VOLUME_MINIMO_DO_CRANIO_ACIMA_DO_C1_CM3
    E.VOLUME_MINIMO_DO_CRANIO_ACIMA_DO_C1_CM3 = 0.0
    try:
        isca_c = E.pescoco_no_campo(torax_ate_c1, G)[0]
    finally:
        E.VOLUME_MINIMO_DO_CRANIO_ACIMA_DO_C1_CM3 = velho_c
    checar(u"ISCA: sem o piso do cranio, a ponta de osso acima do C1 da TC de "
           u"torax viraria pescoco", isca_c)
    band = dict(_vertebras_do_pescoco(mandibula=False))
    band["skull"] = caixa(13, 27, 45, 65, 85, 103)
    v_band = E._cm3_da_mascara(band["skull"], G)
    tem_b, laudo_b = E.pescoco_no_campo(band, G)
    checar(u"TC de torax ate o C1 com %.0f cm3 de osso so na faixa (abaixo do "
           u"piso da mandibula, acima do piso do cranio): NAO e pescoco, e o "
           u"cranio acima do C1 e zero" % v_band,
           not tem_b and E.cranio_acima_do_c1_cm3(band, G) == 0.0
           and E.VOLUME_MINIMO_DO_CRANIO_ACIMA_DO_C1_CM3 <= v_band
           < E.VOLUME_MINIMO_DA_MANDIBULA_CM3, laudo_b)
    velha_c = E.cranio_acima_do_c1_cm3
    E.cranio_acima_do_c1_cm3 = (
        lambda masks, grade, cru=None: E._cm3_da_mascara(
            E._osso_da_cabeca(masks, cru), grade))
    try:
        isca_b = E.pescoco_no_campo(band, G)[0]
    finally:
        E.cranio_acima_do_c1_cm3 = velha_c
    checar(u"ISCA: medindo o osso inteiro, e nao so acima do C1, a mesma TC "
           u"de torax viraria pescoco", isca_b)
    com = dict(_vertebras_do_pescoco())
    checar(u"com a mandibula inteira no campo e pescoco",
           E.pescoco_no_campo(com, G)[0])
    velho = E.VOLUME_MINIMO_DA_MANDIBULA_CM3
    E.VOLUME_MINIMO_DA_MANDIBULA_CM3 = 0.0
    try:
        isca = E.pescoco_no_campo(torax_ate_c1, G)[0]
    finally:
        E.VOLUME_MINIMO_DA_MANDIBULA_CM3 = velho
    checar(u"ISCA: sem o piso da mandibula, a TC de torax ate C1 viraria "
           u"pescoco (o gatilho de antes)", isca)
    an = TP.anatomia_da_base(torax_ate_c1, G, motor=E)
    tasks = TP.tasks_da_anatomia(an["regioes"], "CT")[0]
    checar(u"sem pescoco, nenhuma task de cabeca e pescoco no AUTO",
           not (set(tasks) & set(MD.TASKS_POR_TOPOGRAFIA["cabeca_pescoco"])),
           str(tasks))
    checar(u"  e o FAST tambem nao as roda",
           not (set(MD.tasks_do_fast(an["regioes"], None, "CT"))
                & set(MD.TASKS_POR_TOPOGRAFIA["cabeca_pescoco"])))
    vert = dict(_vertebras_do_pescoco(mandibula=False))
    checar(u"a mandibula vem do skull da base ou da craniofacial (a uniao)",
           E.mandibula_no_campo_cm3(dict(vert, mandible=com["mandible"]), G)
           == E.mandibula_no_campo_cm3(dict(vert, skull=com["mandible"]), G)
           > 0)
    checar(u"  e sem C1 nem C2 nao ha faixa: a medida e zero",
           E.mandibula_no_campo_cm3({"mandible": com["mandible"]}, G) == 0.0)

    alto = (60, Y, X)

    def _caixa_alta(z0, z1, y0, y1, x0, x1):
        return caixa(z0, z1, y0, y1, x0, x1, forma=alto)
    cervicais = {"vertebrae_C1": _caixa_alta(25, 28, 80, 90, 59, 69),
                 "vertebrae_C2": _caixa_alta(20, 25, 80, 90, 59, 69),
                 "vertebrae_C3": _caixa_alta(14, 19, 80, 90, 59, 69),
                 "vertebrae_C4": _caixa_alta(8, 13, 80, 90, 59, 69)}
    cranio = _caixa_alta(28, 60, 20, 110, 20, 110)
    mand = _caixa_alta(13, 29, 45, 70, 92, 112)
    so_cranio = dict(cervicais, skull=cranio)
    v_cr = E.mandibula_no_campo_cm3(so_cranio, G)
    tem_cr, laudo_cr = E.pescoco_no_campo(so_cranio, G)
    checar(u"o cranio sem a mandibula (C1 a C4 no campo, %.0f cm3 de cranio "
           u"acima do C1) e pescoco pelo cranio: a faixa da mandibula nao tem "
           u"osso, e a cabeca esta no campo" % E._cm3_da_mascara(cranio, G),
           tem_cr and v_cr == 0.0
           and u"confirmado por: o cranio acima do C1" in laudo_cr, laudo_cr)
    cp = dict(cervicais, skull=cranio | mand)
    v_cp = E.mandibula_no_campo_cm3(cp, G)
    esperado = E._cm3_da_mascara(mand[8:28], G)
    tem_cp, laudo_cp = E.pescoco_no_campo(cp, G)
    checar(u"cabeca e pescoco (o cranio e a mandibula no campo): e pescoco, "
           u"pelos dois caminhos, e a medida e so a mandibula da faixa (%.0f "
           u"cm3)" % esperado,
           tem_cp and abs(v_cp - esperado) < 1e-6
           and u"confirmado por: a mandibula e o cranio" in laudo_cp,
           u"%.1f cm3; %s" % (v_cp, laudo_cp))
    pequena = _caixa_alta(13, 16, 45, 70, 92, 112)
    hn_pequena = dict(cervicais, skull=cranio | pequena)
    v_pq = E.mandibula_no_campo_cm3(hn_pequena, G)
    tem_pq, laudo_pq = E.pescoco_no_campo(hn_pequena, G)
    checar(u"cabeca e pescoco com a mandibula pequena ou desdentada (%.0f cm3 "
           u"na faixa, abaixo do piso de %.0f): e pescoco pelo cranio acima do "
           u"C1" % (v_pq, E.VOLUME_MINIMO_DA_MANDIBULA_CM3),
           tem_pq and v_pq < E.VOLUME_MINIMO_DA_MANDIBULA_CM3
           and u"confirmado por: o cranio acima do C1" in laudo_pq, laudo_pq)
    E.VOLUME_MINIMO_DO_CRANIO_ACIMA_DO_C1_CM3 = float("inf")
    try:
        isca_pq = E.pescoco_no_campo(hn_pequena, G)[0]
    finally:
        E.VOLUME_MINIMO_DO_CRANIO_ACIMA_DO_C1_CM3 = velho_c
    checar(u"ISCA: so pela mandibula (a regra da 2c), a mesma TC de cabeca e "
           u"pescoco perderia o pescoco -- o risco clinico que o cranio fecha",
           not isca_pq)
    queixo = dict(cervicais, mandible=pequena)
    checar(u"so a ponta do queixo na faixa (%.0f cm3), sem cranio acima do "
           u"C1: NAO e pescoco" % E.mandibula_no_campo_cm3(queixo, G),
           not E.pescoco_no_campo(queixo, G)[0])
    sem_pescoco = {"vertebrae_C1": cervicais["vertebrae_C1"],
                   "vertebrae_C2": cervicais["vertebrae_C2"],
                   "skull": cranio | mand}
    tem_sp, laudo_sp = E.pescoco_no_campo(sem_pescoco, G)
    checar(u"cranio sem pescoco (cranio, mandibula, C1 e C2, sem C3 e C4): "
           u"NAO e pescoco -- faltam as vertebras",
           not tem_sp and u"confirmado por: nenhum: faltam C2, C3 ou C4"
           in laudo_sp, laudo_sp)
    sem_c1 = dict(com)
    sem_c1.pop("vertebrae_C1")
    checar(u"sem o C1, a faixa comeca no topo do C2 (a mandibula acima dele "
           u"nao conta)", E.mandibula_no_campo_cm3(sem_c1, G)
           == E._cm3_da_mascara(com["mandible"][8:25], G))
    checar(u"  e o cranio acima dele tambem se mede do topo do C2",
           E.cranio_acima_do_c1_cm3(sem_c1, G)
           == E._cm3_da_mascara(com["mandible"][25:], G))

    def _uniao_de_antes(masks, grade, cru=None):
        acc = None
        for n in ("skull", "mandible"):
            m = masks.get(n)
            if m is not None:
                b = np.asarray(m, bool)
                acc = b.copy() if acc is None else (acc | b)
        return E._cm3_da_mascara(acc, grade)
    fora_da_faixa = dict(cervicais,
                         skull=_caixa_alta(28, 33, 20, 40, 20, 45),
                         mandible=_caixa_alta(0, 8, 45, 70, 85, 110))
    checar(u"cranio pequeno acima do C1 (%.0f cm3) e osso abaixo do C4 (%.0f "
           u"cm3): NAO e pescoco (a faixa nao tem osso, o cranio nao passa do "
           u"piso)" % (E.cranio_acima_do_c1_cm3(fora_da_faixa, G),
                       E._cm3_da_mascara(fora_da_faixa["mandible"], G)),
           not E.pescoco_no_campo(fora_da_faixa, G)[0])
    velha = E.mandibula_no_campo_cm3
    E.mandibula_no_campo_cm3 = _uniao_de_antes
    try:
        isca_cr = E.pescoco_no_campo(fora_da_faixa, G)[0]
    finally:
        E.mandibula_no_campo_cm3 = velha
    checar(u"ISCA: com a medida de antes (skull e mandible inteiros, fora da "
           u"faixa), o osso fora do pescoco viraria pescoco", isca_cr)

    motivo = E.portao_da_regiao("headneck_muscles", torax_ate_c1, grade=G)
    checar(u"os constritores (headneck_muscles) nao rodam sem o pescoco "
           u"confirmado, e o motivo diz", bool(motivo)
           and u"pescoco confirmado" in motivo, motivo)
    checar(u"  e rodam com ele",
           E.portao_da_regiao("headneck_muscles", com, grade=G) is None)
    ref = _volume_do_portao()
    chamadas = []

    def _rodar(ref_, t, dev, jid, **kw):
        chamadas.append(t)
        return dict(torax_ate_c1) if t == "total_v3" else {}
    jid = E._job_new()
    try:
        res = E.rodar_tasks(ref, ["total_v3", "headneck_muscles"], "cpu", jid,
                            rodar=_rodar)
        log = list(E._job(jid).get("log") or [])
    finally:
        E._job_del(jid)
    checar(u"ligada a mao, a trava vence: a task e pulada, com a linha no log",
           "headneck_muscles" not in chamadas
           and any(p.get("task") == "headneck_muscles" for p in res["puladas"])
           and any(u"headneck_muscles" in l and u"pulada" in l for l in log),
           (chamadas, res["puladas"]))
    velho_r = dict(E.REGIAO_DA_TASK)
    E.REGIAO_DA_TASK.pop("headneck_muscles", None)
    chamadas[:] = []
    try:
        jid = E._job_new()
        try:
            E.rodar_tasks(ref, ["total_v3", "headneck_muscles"], "cpu", jid,
                          rodar=_rodar)
        finally:
            E._job_del(jid)
    finally:
        E.REGIAO_DA_TASK.clear()
        E.REGIAO_DA_TASK.update(velho_r)
    checar(u"ISCA: sem a trava, a task dos constritores rodaria",
           "headneck_muscles" in chamadas)
    checar(u"a A_Carotid_ai vai so ao FULL, em toda regiao",
           "carotids" not in RS.PERMITIDOS_NO_OAR
           and "carotids" not in RS.PERMITIDOS_NO_OAR_FAST)


def _torax_fino():
    g = radai_geom.Grade((1.0, 0.5, 0.5))
    f = (20, 60, 60)

    def cx(z0, z1, y0, y1, x0, x1):
        return caixa(z0, z1, y0, y1, x0, x1, forma=f)
    m = {"aorta": cx(2, 18, 20, 30, 20, 30),
         "lung_upper_lobe_left": cx(2, 18, 20, 30, 30, 50),
         "esophagus": cx(2, 18, 30, 36, 20, 30),
         "trachea": cx(2, 18, 10, 20, 20, 30),
         "vertebrae_T5": cx(2, 18, 40, 55, 15, 35)}
    return g, m


def teste_a_aorta_sai_recortada_depois_da_margem():
    secao(u"v8.5: a aorta, depois da margem, sai recortada dos pulmoes, do "
          u"esofago e da traqueia")
    g, m = _torax_fino()
    original = m["aorta"].copy()
    viz = m["lung_upper_lobe_left"] | m["esophagus"] | m["trachea"]
    fora, meta = E.preparar_full(dict(m), grade=g)
    ao = np.asarray(fora["aorta"], bool)
    viz = (np.asarray(fora["lung_upper_lobe_left"], bool)
           | np.asarray(fora["esophagus"], bool)
           | np.asarray(fora["trachea"], bool))
    checar(u"a aorta nao entra no pulmao, no esofago nem na traqueia (a "
           u"traqueia ja com a margem dela)",
           not (ao & viz).any(), u"%d voxels" % int((ao & viz).sum()))
    checar(u"  e continua com a margem onde nao ha vizinho",
           (ao & ~original & ~viz).any())
    checar(u"  e do modelo so sai o que o vizinho final ocupa",
           not (original & ~ao & ~viz).any())
    velha = E.recortar_aorta_dos_vizinhos
    E.recortar_aorta_dos_vizinhos = lambda *a, **k: 0.0
    try:
        fi, _mi = E.preparar_full(dict(m), grade=g)
    finally:
        E.recortar_aorta_dos_vizinhos = velha
    checar(u"ISCA: sem o recorte, a margem da aorta entra nos vizinhos",
           bool((np.asarray(fi["aorta"], bool) & viz).any()))
    linhas = []
    sem = dict(m)
    sem["aorta"] = m["lung_upper_lobe_left"].copy()
    E.recortar_aorta_dos_vizinhos(sem, g, log=linhas.append)
    checar(u"a aorta que ficaria vazia sai como estava, e o log diz",
           np.array_equal(sem["aorta"], m["lung_upper_lobe_left"])
           and any(u"ficaria VAZIA" in l for l in linhas), str(linhas))
    checar(u"a lista do recorte e a dos pulmoes, do esofago e da traqueia",
           set(E.RECORTE_DA_AORTA_DEPOIS_DA_MARGEM)
           >= {"lung_upper_lobe_left", "lung_left", "esophagus", "trachea"})


def teste_o_pancreas_entra_nas_duas_bags():
    secao(u"v8.5: o pancreas entra inteiro na Bag_Bowel_ai e na "
          u"Bag_Bowel_OAR_ai")
    m, skin = _abdome()
    m["pancreas"] = caixa(22, 27, 92, 106, 72, 89)
    m["portal_vein_and_splenic_vein"] = caixa(22, 27, 90, 93, 70, 92)
    pan = m["pancreas"]
    c = RC.bag_bowel_declarada(dict(m), G)
    puro = RC.bag_bowel(dict(m), G)
    checar(u"(pre-condicao) a receita sozinha deixa parte do pancreas fora "
           u"(fora da cavidade e na veia)",
           puro is not None and bool((pan & ~puro.mascara).any()))
    checar(u"a Bag_Bowel_ai do motor leva o pancreas inteiro, e a descricao "
           u"diz", c is not None and not (pan & ~np.asarray(c.mascara,
                                                             bool)).any()
           and u"pancreas entra inteiro" in c.descricao,
           c.descricao if c is not None else u"")
    spec = E.CONSTRUCOES_POR_SAIDA()["bag_bowel"]
    checar(u"  e a segunda passada o devolve depois do recorte pelos vasos "
           u"(`reune`)", "pancreas" in tuple(spec.get("reune") or ()))

    def _segunda(sp):
        mm = {"bag_bowel": np.asarray(c.mascara, bool).copy(),
              "pancreas": pan, "portal_vein_and_splenic_vein":
                  m["portal_vein_and_splenic_vein"]}
        E._suavizar_construcoes(mm, G, 1.5, {"bag_bowel": dict(sp)}, [], [])
        return np.asarray(mm["bag_bowel"], bool)
    b2 = _segunda(spec)
    checar(u"  na segunda passada, com a veia sobre o pancreas, ele continua "
           u"inteiro na bag", not (pan & ~b2).any(),
           u"%d voxels fora" % int((pan & ~b2).sum()))
    sem_reune = dict((k, v) for k, v in spec.items() if k != "reune")
    bi = _segunda(sem_reune)
    checar(u"ISCA: sem o `reune`, o recorte pela veia tira o pancreas da bag",
           bool((pan & ~bi).any()))
    tmp = tempfile.mkdtemp(prefix="radai_t_motor2_")
    try:
        serie = _serie(tmp)
        itens = [("abdominal_cavity", "trunk_cavities",
                  caixa(0, 30, 35, 96, 35, 96)),
                 ("small_bowel", "total_v3", caixa(8, 21, 40, 61, 45, 86)),
                 ("colon", "total_v3", caixa(8, 25, 40, 51, 36, 44)),
                 ("pancreas", "total_v3", caixa(21, 27, 84, 102, 60, 80)),
                 ("portal_vein_and_splenic_vein", "total_v3",
                  caixa(21, 27, 82, 85, 58, 82)),
                 ("aorta", "total_v3", caixa(5, 30, 75, 81, 60, 66))]
        sd, r, linhas = _rodar(tmp, serie, _cruas(itens))
        mf = sd.meta_do_full["mascaras"]
        p = np.asarray(mf["pancreas"], bool)
        for chave in ("bag_bowel", "bag_bowel_oar"):
            b = np.asarray(mf[chave], bool)
            checar(u"na cadeia: `%s` leva o pancreas final inteiro" % chave,
                   p.any() and not (p & ~b).any(),
                   u"%d de %d voxels fora" % (int((p & ~b).sum()),
                                               int(p.sum())))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _itens_da_pelve(com_cav=True, femur_esq=True):
    it = [("hip_left", "total_v3", caixa(8, 27, 50, 80, 70, 90)),
          ("hip_right", "total_v3", caixa(8, 27, 50, 80, 38, 58)),
          ("sacrum", "total_v3", caixa(14, 28, 80, 95, 56, 72)
           | caixa(20, 26, 70, 80, 56, 74)),
          ("femur_right", "total_v3", caixa(0, 16, 55, 75, 38, 53)),
          ("colon", "total_v3", caixa(0, 25, 60, 70, 60, 68)),
          ("small_bowel", "total_v3", caixa(18, 28, 30, 50, 50, 80))]
    if femur_esq:
        it.append(("femur_left", "total_v3", caixa(0, 14, 55, 75, 75, 90)))
    if com_cav:
        it.append(("abdominal_cavity", "trunk_cavities",
                   caixa(0, 30, 25, 100, 30, 98)))
    return it


def teste_as_cristas_vao_ao_oar_so_com_a_pelve():
    secao(u"IliacCrest_L/R_ai e Anus_ai vao ao OAR so com a pelve "
          u"identificada; no FULL saem sempre")
    abd = [("hip_left", "total_v3", caixa(0, 5, 50, 80, 70, 90)),
           ("hip_right", "total_v3", caixa(0, 5, 50, 80, 38, 58)),
           ("liver", "total_v3", caixa(10, 30, 30, 90, 30, 70)),
           ("colon", "total_v3", caixa(0, 25, 60, 70, 60, 68))]
    novas = {"IliacCrest_L_ai", "IliacCrest_R_ai"}
    tmp = tempfile.mkdtemp(prefix="radai_t_motor2_")
    try:
        serie = _serie(tmp)
        sd, r, linhas = _rodar(tmp, serie, _cruas(abd))
        fr = dict(getattr(sd, "meta_do_full", {}) or {}).get(
            "fora_do_oar_por_regiao") or {}
        checar(u"TC de abdome alto que pega a ponta do quadril: as cristas "
               u"saem no FULL", novas <= set(r["estruturas_full"]),
               str(sorted(r["estruturas_full"])))
        checar(u"  e nao vao ao OAR (a pelve nao foi identificada)",
               not (novas & set(r["estruturas"])),
               str(sorted(r["estruturas"])))
        velho = dict(E.REGIAO_EXIGIDA_NO_OAR)
        E.REGIAO_EXIGIDA_NO_OAR.clear()
        E.REGIAO_EXIGIDA_NO_OAR["bone_pelvic"] = "pelve"
        try:
            _sdi, ri, _li = _rodar(tmp, serie, _cruas(abd))
        finally:
            E.REGIAO_EXIGIDA_NO_OAR.clear()
            E.REGIAO_EXIGIDA_NO_OAR.update(velho)
        checar(u"(isca) sem as cristas no portao de regiao, elas iriam ao OAR "
               u"(o defeito)", novas <= set(ri["estruturas"]),
               str(sorted(ri["estruturas"])))
        sdf, rf, _lf = _rodar(tmp, serie, _cruas(abd), modo="fast")
        checar(u"  e o OAR_Fast segue a mesma regra",
               not (novas & set(rf["estruturas"])),
               str(sorted(rf["estruturas"])))
        _s2, r2, _l2 = _rodar(tmp, serie, _cruas(_itens_da_pelve()))
        checar(u"com a pelve identificada, as tres vao ao OAR",
               {"IliacCrest_L_ai", "IliacCrest_R_ai", "Anus_ai"}
               <= set(r2["estruturas"]), str(sorted(r2["estruturas"])))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    import radai_batch as RB
    sem_pelve, _f = RB.estruturas_do_oar_possiveis(
        "perso", ("trunk_cavities",), "CT", regioes=("abdome",))
    com_pelve, _f = RB.estruturas_do_oar_possiveis(
        "perso", ("trunk_cavities",), "CT", regioes=("abdome", "pelve"))
    tres = {"iliac_crest_left", "iliac_crest_right", "anus"}
    checar(u"a previa do PERSONALIZADO acompanha: sem a pelve, nenhuma das "
           u"tres; com ela, as tres",
           not (tres & set(e["chave"] for e in sem_pelve))
           and tres <= set(e["chave"] for e in com_pelve))
    sem_med, _f = RB.estruturas_do_oar_possiveis(
        "perso", ("trunk_cavities",), "CT")
    por = dict((e["chave"], e) for e in sem_med)
    checar(u"  e sem a regiao medida, as tres levam a condicao da pelve",
           all(por.get(k, {}).get("condicao")
               == RB.CONDICAO_DA_REGIAO_NA_PREVIA["pelve"] for k in tres),
           str([por.get(k) for k in tres]))


def teste_as_cristas_iliacas_e_o_anus():
    secao(u"v8.5: IliacCrest_L/R_ai e Anus_ai, so por recorte do FULL")
    for k in ("iliac_crest_left", "iliac_crest_right", "anus"):
        n = E.nome_clinico(k)
        checar(u"`%s` -> `%s`: ate 16 caracteres ASCII" % (k, n),
               len(n) <= 16 and all(ord(ch) < 128 for ch in n))
        checar(u"  no OAR", k in RS.PERMITIDOS_NO_OAR)
    checar(u"as cristas tambem no OAR_Fast (as fontes, quadril, sacro e femur, "
           u"vem da base); o Anus nao (a Bag_Bowel_ai, a fonte, o FAST nao "
           u"monta)", "iliac_crest_left" in RS.PERMITIDOS_NO_OAR_FAST
           and "iliac_crest_right" in RS.PERMITIDOS_NO_OAR_FAST
           and "anus" in RS.FORA_DO_OAR_FAST
           and "anus" not in RS.PERMITIDOS_NO_OAR_FAST)
    checar(u"os nomes do TPS sao os decididos",
           [E.nome_clinico(k) for k in ("iliac_crest_left",
                                        "iliac_crest_right", "anus")]
           == [u"IliacCrest_L_ai", u"IliacCrest_R_ai", u"Anus_ai"])
    for k in ("iliac_crest_left", "iliac_crest_right"):
        r_, g_, b_ = E._color(k)
        checar(u"`%s` e verde-claro" % k, g_ >= 230 and r_ < g_ - 60
               and b_ < g_ - 60, str((r_, g_, b_)))
    checar(u"o filtro do FAST nao monta a Bag_Bowel_ai (nem o Anus)",
           not ({"anus", "bag_bowel", "bag_bowel_oar"}
                & E.construcoes_para(RS.PERMITIDOS_NO_OAR_FAST))
           and "crista_iliaca" in E.construcoes_para(
               RS.PERMITIDOS_NO_OAR_FAST))
    m = dict((rot, mm) for rot, _t, mm in _itens_da_pelve())
    m["bag_bowel"] = m["abdominal_cavity"].copy()
    cl = RC.crista_iliaca(m, G, "iliac_crest_left")
    esperado = m["hip_left"] & ~m["sacrum"]
    esperado[:14] = False
    checar(u"a crista esquerda e o quadril menos o sacro menos o femur "
           u"esquerdo para baixo (do corte 13, o topo dele, inclusive)",
           bool(cl) and np.array_equal(np.asarray(cl.mascara, bool),
                                       esperado))
    cr = RC.crista_iliaca(m, G, "iliac_crest_right")
    zr = np.flatnonzero(np.asarray(cr.mascara, bool).any(axis=(1, 2)))
    checar(u"  e a direita corta pelo femur direito (topo no corte 15): "
           u"comeca no 16", bool(cr) and int(zr.min()) == 16, str(zr[:3]))
    checar(u"  e nenhuma leva o sacro",
           not (np.asarray(cl.mascara, bool) & m["sacrum"]).any())
    sem_f = dict(m)
    sem_f.pop("femur_left")
    c0 = RC.crista_iliaca(sem_f, G, "iliac_crest_left")
    checar(u"sem o femur do lado, com o quadril inteiro no campo: nao sai, e "
           u"diz por que", not c0 and c0.faltou
           and u"nao tem marco" in c0.faltou[0], str(c0.faltou))
    corte = dict((k, v[8:].copy()) for k, v in sem_f.items())
    c1 = RC.crista_iliaca(corte, G, "iliac_crest_left")
    checar(u"sem o femur, com o quadril saindo pela borda caudal: sai o "
           u"quadril menos o sacro, e a descricao diz",
           bool(c1) and u"sem femur do lado" in c1.descricao
           and np.array_equal(np.asarray(c1.mascara, bool),
                              corte["hip_left"] & ~corte["sacrum"]))
    an = RC.anus(m, G)
    za = np.flatnonzero(np.asarray(an.mascara, bool).any(axis=(1, 2)))
    checar(u"o Anus e a Bag_Bowel do ultimo corte do osso pelvico (8) para "
           u"baixo, inclusive", bool(an) and int(za.max()) == 8
           and np.array_equal(np.asarray(an.mascara, bool)[:9],
                              m["bag_bowel"][:9]), str(za[-3:]))
    a0 = RC.anus(dict((k, v[8:].copy()) for k, v in m.items()), G)
    checar(u"  com o osso pelvico na borda caudal da serie, nao sai, e diz",
           not a0 and u"borda caudal" in a0.faltou[0], str(a0.faltou))
    a1 = RC.anus(dict((k, v) for k, v in m.items() if k != "bag_bowel"), G)
    checar(u"  sem a Bag_Bowel_ai, nao sai, e diz",
           not a1 and u"Bag_Bowel_ai" in a1.faltou[0], str(a1.faltou))

    tmp = tempfile.mkdtemp(prefix="radai_t_motor2_")
    try:
        serie = _serie(tmp)
        sd, r, linhas = _rodar(tmp, serie, _cruas(_itens_da_pelve()))
        novas = {"IliacCrest_L_ai", "IliacCrest_R_ai", "Anus_ai"}
        checar(u"as tres saem no FULL e no OAR",
               novas <= set(r["estruturas_full"])
               and novas <= set(r["estruturas"]), str(sorted(r["estruturas"])))
        mf = sd.meta_do_full["mascaras"]
        crf = np.asarray(mf["iliac_crest_left"], bool)
        esp = np.asarray(mf["hip_left"], bool) & ~np.asarray(mf["sacrum"],
                                                             bool)
        zf = np.flatnonzero(np.asarray(mf["femur_left"], bool).any(
            axis=(1, 2)))
        esp[:int(zf.max()) + 1] = False
        checar(u"no FULL, a crista e o recorte do Bone_Pelvic_L FINAL (depois "
               u"da suavizacao), voxel a voxel", np.array_equal(crf, esp))
        anf = np.asarray(mf["anus"], bool)
        zq = np.flatnonzero((np.asarray(mf["hip_left"], bool)
                             | np.asarray(mf["hip_right"], bool)).any(
            axis=(1, 2)))
        esp_a = np.asarray(mf["bag_bowel"], bool).copy()
        esp_a[int(zq.min()) + 1:] = False
        checar(u"  e o Anus, o recorte da Bag_Bowel_ai FINAL",
               np.array_equal(anf, esp_a))
        obs = _obs(r["oar"])
        checar(u"a descricao da ROI diz a receita",
               u"menos o sacro" in obs.get("IliacCrest_L_ai", u"")
               and u"Recorte do FULL" in obs.get("Anus_ai", u""),
               str(obs.get("Anus_ai"))[:120])
        ds = pydicom.dcmread(r["full"])
        num = dict((str(x.ROIName), int(x.ROINumber))
                   for x in ds.StructureSetROISequence)
        cor = dict((int(x.ReferencedROINumber), list(x.ROIDisplayColor))
                   for x in ds.ROIContourSequence)
        checar(u"no DICOM, a cor da crista e a verde-clara da tabela",
               cor.get(num.get("IliacCrest_L_ai"))
               == [int(v) for v in E._color("iliac_crest_left")],
               str(cor.get(num.get("IliacCrest_L_ai"))))
        sdf, rf, _lf = _rodar(tmp, serie,
                              _cruas(_itens_da_pelve(com_cav=False)),
                              modo="fast")
        checar(u"FAST sem a cavidade do tronco: as cristas saem, o Anus nao "
               u"(a fonte nao existe), e nenhuma bag",
               {"IliacCrest_L_ai", "IliacCrest_R_ai"} <= set(rf["estruturas"])
               and not ({"Anus_ai", "Bag_Bowel_ai", "Bag_Bowel_OAR_ai"}
                        & set(rf["estruturas"])), str(sorted(rf["estruturas"])))
        sdf2, rf2, _lf2 = _rodar(tmp, serie, _cruas(_itens_da_pelve()),
                                 modo="fast")
        filtro = dict((sdf2.meta_do_fast or {}).get("filtro") or {})
        checar(u"FAST com a cavidade do tronco: as cristas saem, o Anus nao, e "
               u"a Bag_Bowel_ai nem e montada",
               {"IliacCrest_L_ai", "IliacCrest_R_ai"}
               <= set(rf2["estruturas"])
               and not ({"Anus_ai", "Bag_Bowel_ai", "Bag_Bowel_OAR_ai"}
                        & set(rf2["estruturas"]))
               and "bag_bowel" in (filtro.get("fora_do_filtro") or ()),
               str(sorted(rf2["estruturas"])))
        velho = RS.PERMITIDOS_NO_OAR_FAST
        RS.PERMITIDOS_NO_OAR_FAST = frozenset(velho | {"anus"})
        try:
            sdi, ri, _li = _rodar(tmp, serie, _cruas(_itens_da_pelve()),
                                  modo="fast")
        finally:
            RS.PERMITIDOS_NO_OAR_FAST = velho
        checar(u"ISCA: sem o Anus em FORA_DO_OAR_FAST, o filtro o pede e ele "
               u"nao sai (a fonte nao existe no FAST): a lista e a que "
               u"impede o pedido calado", "Anus_ai" not in set(
                   ri["estruturas"])
               and any(c == "anus" for c, _m in
                       (sdi.meta_do_fast.get("nao_sairam") or ())),
               str(sdi.meta_do_fast.get("nao_sairam"))[:200])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    import radai_batch as RB
    pp = RB.estruturas_do_oar_possiveis("perso", ("trunk_cavities",), "CT")
    chaves = set(x.get("chave") for x in (pp[0] if isinstance(pp, tuple)
                                          else pp))
    checar(u"a previa do PERSONALIZADO com a cavidade do tronco mostra as "
           u"tres", {"iliac_crest_left", "iliac_crest_right", "anus"}
           <= chaves)
    ps = RB.estruturas_do_oar_possiveis("perso", (), "CT")
    chaves_s = set(x.get("chave") for x in (ps[0] if isinstance(ps, tuple)
                                            else ps))
    checar(u"  e sem ela, so as cristas (o Anus depende da cavidade)",
           {"iliac_crest_left", "iliac_crest_right"} <= chaves_s
           and "anus" not in chaves_s)

    def _no_fast():
        pf = RB.estruturas_do_oar_possiveis("fast", ("trunk_cavities",), "CT")
        return set(x.get("chave") for x in (pf[0] if isinstance(pf, tuple)
                                            else pf))
    chaves_f = _no_fast()
    checar(u"  e a previa do FAST mostra as cristas e nao o Anus",
           {"iliac_crest_left", "iliac_crest_right"} <= chaves_f
           and "anus" not in chaves_f)
    velho = RS.PERMITIDOS_NO_OAR_FAST
    RS.PERMITIDOS_NO_OAR_FAST = frozenset(velho | {"anus"})
    try:
        isca_f = _no_fast()
    finally:
        RS.PERMITIDOS_NO_OAR_FAST = velho
    checar(u"ISCA: com o Anus no OAR_Fast, a previa do FAST o prometeria",
           "anus" in isca_f)


def _volume_do_portao():
    import SimpleITK as sitk
    v = sitk.GetImageFromArray(np.zeros((Z, Y, X), np.int16))
    v.SetSpacing((G.spacing[2], G.spacing[1], G.spacing[0]))
    return v


def teste_a_bibliografia_tem_o_atlas():
    secao(u"C2: o atlas de Orton na bibliografia, com a ancora viva")
    import json
    caminho = _componentes.fonte("app/data/bibliography.json")
    dados = json.load(io.open(caminho, encoding="utf-8"))
    itens = dados if isinstance(dados, list) else dados.get(
        "artigos", dados.get("itens", []))
    o = [x for x in itens if isinstance(x, dict)
         and x.get("id", x.get("chave")) == "orton2022"]
    checar(u"`orton2022` existe, com o DOI conferido",
           len(o) == 1 and u"10.1016/j.adro.2022.101031" in json.dumps(o[0]),
           str(o)[:200])


def main():
    print(u"=" * 68)
    print(u"test_motor2 | estruturas da trilha MOTOR2 (indice 26, reto na "
          u"cadeia, abdome, pescoco, orgao espurio, oculomotores, olhos, "
          u"Bag_Bowel_OAR)")
    print(u"=" * 68)
    testes = (teste_o_indice_26_na_cadeia,
              teste_o_plato_e_o_mesmo_nas_duas_versoes,
              teste_a_derivacao_roda_uma_vez_e_antes_da_bag,
              teste_o_reto_na_cadeia_e_o_de_antes,
              teste_adrenais_e_muscles_so_no_full,
              teste_o_oar_do_pescoco_por_topografia,
              teste_o_pescoco_exige_a_mandibula,
              teste_o_orgao_solido_espurio,
              teste_oculomotor_so_por_ato_declarado,
              teste_o_globo_ocular,
              teste_a_bag_bowel_oar_e_construcao_registrada,
              teste_a_bag_bowel_ai_declara_a_prostata,
              teste_a_receita_da_bag_bowel_oar,
              teste_a_folga_dos_vizinhos_e_os_orgaos_inteiros,
              teste_a_veia_porta_fora_de_toda_conta,
              teste_o_corte_caudal_pela_sacroiliaca,
              teste_a_bag_oar_sem_reto_separado,
              teste_os_textos_do_fast_dizem_o_que_ele_nao_leva,
              teste_a_bag_oar_sem_ponte,
              teste_a_contencao_declarada_da_bag_oar,
              teste_a_bag_oar_na_volta_do_rtstruct,
              teste_a_aorta_sai_recortada_depois_da_margem,
              teste_o_pancreas_entra_nas_duas_bags,
              teste_as_cristas_iliacas_e_o_anus,
              teste_as_cristas_vao_ao_oar_so_com_a_pelve,
              teste_a_bibliografia_tem_o_atlas)
    so = [a for a in sys.argv[1:] if a.startswith("teste_")]
    for t in testes:
        if so and t.__name__ not in so:
            continue
        try:
            t()
        except Exception as e:
            checar(u"%s chegou ao fim" % t.__name__, False,
                   u"%s: %s" % (type(e).__name__, e))
            traceback.print_exc()
    falhas = [x for x in _RES if not x[1]]
    print()
    if falhas:
        print(u"FALHOU: %d de %d checagens" % (len(falhas), len(_RES)))
        for n, _ok, d in falhas:
            print(u"  - %s%s" % (n, (u"  [%s]" % d) if d else u""))
        return 1
    print(u"OK: %d checagens, todas passaram" % len(_RES))
    return 0


if __name__ == "__main__":
    sys.exit(main())
