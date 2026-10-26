# -*- coding: utf-8 -*-
import ast
import asyncio
import glob
import io
import json
import os
import subprocess
import sys
import tempfile
import time
import traceback
import urllib.request
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
os.environ["RADAI_CALIB_DIR"] = tempfile.mkdtemp(prefix="radai_ac_nomes_")
os.environ["RADAI_REGISTRO_DIR"] = tempfile.mkdtemp(prefix="radai_ac_nomes_reg_")
os.environ["TOTALSEG_HOME_DIR"] = tempfile.mkdtemp(prefix="radai_tshome_nomes_")
_CFG = os.path.join(os.environ["RADAI_CALIB_DIR"], "radai_watcher.config")
io.open(_CFG, "w", encoding="utf-8").write(u"ROOT=\n")
os.environ["RADAI_CONFIG"] = _CFG
import _cleanup
import _componentes
_cleanup.adotar_prefixo("radai_ac_nomes_")
_cleanup.adotar_prefixo("radai_tshome_nomes_")
_cleanup.adotar_prefixo("radai_t_nomes_")

import numpy as np
import pydicom
import engine as E
import radai_config as RC
import radai_output as RO
import radai_sets as RS
from make_test_series import escreve_serie

E.VOLUME_MINIMO_CORACAO_CM3 = 1.0

PORTA = 8863
BASE = "http://127.0.0.1:%d" % PORTA
_RES = []
VERBOSO = "-v" in sys.argv
_NADA = object()


def checar(nome, cond, detalhe=""):
    ok = bool(cond)
    _RES.append((nome, ok, detalhe))
    if VERBOSO or not ok:
        print(u"  %s  %s%s" % (u"ok   " if ok else u"FALHA", nome,
                              (u"  [%s]" % detalhe) if detalhe else u""))
    return ok


def secao(t):
    print(u"\n-- %s --" % t)


class Duble(object):

    def __init__(self, modo="proprios", nomes=None, protocolos=()):
        self.modo = modo
        self.nomes = dict(nomes or {})
        self.protocolos = [dict(p) for p in protocolos]
        self.velhos = {}

    def __enter__(self):
        for n in ("modo_dos_nomes", "nomes_proprios", "protocolos_proprios"):
            self.velhos[n] = getattr(RC, n, _NADA)
        RC.modo_dos_nomes = lambda: self.modo
        RC.nomes_proprios = lambda: (dict(self.nomes)
                                     if self.modo == "proprios" else {})
        RC.protocolos_proprios = lambda modalidade=None: [
            dict(p) for p in self.protocolos
            if modalidade is None or p.get("modalidade") == modalidade]
        return self

    def __exit__(self, *a):
        for n, v in self.velhos.items():
            if v is _NADA:
                try:
                    delattr(RC, n)
                except AttributeError:
                    pass
            else:
                setattr(RC, n, v)


Z, Y, X = 30, 128, 128
_TOTAL = (
    ("lung_upper_lobe_left", (14, 28, 40, 80, 70, 95)),
    ("lung_lower_lobe_left", (6, 14, 40, 80, 70, 95)),
    ("lung_upper_lobe_right", (16, 28, 40, 80, 30, 55)),
    ("lung_middle_lobe_right", (11, 16, 40, 80, 30, 55)),
    ("lung_lower_lobe_right", (6, 11, 40, 80, 30, 55)),
    ("heart", (8, 16, 45, 65, 57, 69)),
    ("aorta", (4, 26, 70, 76, 60, 66)),
    ("trachea", (18, 28, 60, 64, 61, 65)),
    ("esophagus", (4, 28, 78, 82, 61, 64)),
    ("kidney_left", (0, 6, 80, 95, 80, 95)),
)


def _cruas():
    lab = np.zeros((Z, Y, X), np.int16)
    idx = {}
    for i, (nome, (z0, z1, y0, y1, x0, x1)) in enumerate(_TOTAL, start=1):
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
    return cruas


def _serie(base):
    serie = os.path.join(base, "serie")
    escreve_serie(serie, "PAC_NOMES", datetime.now(), Z)
    return serie


def _rodar(base, serie, **kw):
    import SimpleITK as sitk
    vol = sitk.GetArrayFromImage(E.load_sitk(serie))
    linhas = []
    dest = os.path.join(base, "saida_%d" % len(os.listdir(base)))
    os.makedirs(dest)
    sd = RO.Saida(E, serie, dest, "RS_RadAI_20261025_1a2b3c4d.dcm",
                  tasks=["total_v3"], versao="bateria", suavizar_mm=1.5,
                  log=lambda m: linhas.append(str(m)), modalidade="CT")
    r = sd.full_e_oar(_cruas(), volume_hu=vol, **kw)
    return r, linhas


def _rois(caminho):
    ds = pydicom.dcmread(caminho)
    num = dict((str(x.ROIName), int(x.ROINumber))
               for x in ds.StructureSetROISequence)
    desc = dict((str(x.ROIName), str(getattr(x, "ROIDescription", "") or ""))
                for x in ds.StructureSetROISequence)
    alg = dict((str(x.ROIName), str(getattr(x, "ROIGenerationAlgorithm", "")))
               for x in ds.StructureSetROISequence)
    ger = dict((str(x.ROIName), str(getattr(x, "ROIGenerationDescription",
                                            "")))
               for x in ds.StructureSetROISequence)
    cont = dict((int(c.ReferencedROINumber),
                 len(getattr(c, "ContourSequence", []) or []))
                for c in getattr(ds, "ROIContourSequence", []))
    return ds, num, desc, alg, ger, cont


def teste_os_rotulos():
    secao(u"os rotulos: RadAI_FULL, RadAI_STUDY, RadAI_STUDY_Fast, e os antigos")
    checar(u"os tres rotulos novos, com o I maiusculo",
           (RS.ROTULO_FULL, RS.ROTULO_STUDY, RS.ROTULO_STUDY_FAST)
           == ("RadAI_FULL", "RadAI_STUDY", "RadAI_STUDY_Fast"))
    rot = dict((c, RS.rotulo_dicom(c)) for c in RS.POR_COD)
    checar(u"todo conjunto tem rotulo de no maximo 16 caracteres, com RadAI_",
           all(len(r) <= 16 and r.startswith("RadAI_") for r in rot.values()),
           str(sorted(rot.items())[:6]))
    checar(u"nenhum rotulo novo comeca por STUDY_ (o STUDY agora e o entregue)",
           not any(r.startswith("STUDY_") for r in rot.values()))
    checar(u"  ISCA: a regra antiga (STUDY_ + cod) seria acusada",
           any(("STUDY_" + c).startswith("STUDY_") for c in RS.POR_COD))
    checar(u"o FAST do registro usa a constante do lugar so",
           RS.POR_COD["fast"]["rotulo_dicom"] == RS.ROTULO_STUDY_FAST)
    checar(u"os rotulos antigos continuam reconhecidos (so cresce)",
           RS.cod_do_rotulo("RadAI_OAR") == "oar"
           and RS.cod_do_rotulo("RadAI_OAR_Fast") == "fast"
           and RS.cod_do_rotulo("STUDY_full") == "full"
           and RS.cod_do_rotulo("STUDY_ts") == "ts"
           and RS.cod_do_rotulo("RadAI_STUDY") == "oar"
           and RS.cod_do_rotulo("RadAI_TS") == "ts")
    checar(u"  ISCA: rotulo que ninguem gravou nao vira conjunto",
           RS.cod_do_rotulo("RadAi_xyz") is None)
    checar(u"na tela: STUDY, STUDY_Fast e FULL",
           (RS.nome_na_tela("oar"), RS.nome_na_tela("fast"),
            RS.nome_na_tela("full")) == ("STUDY", "STUDY_Fast", "FULL"))
    nomes = ["RS_RadAI_20260901_abcdef12.dcm", "RS_RadAI_FULL_20260901_abcdef12.dcm",
             "RS_RadAI_FAST_20260901_abcdef12.dcm"]
    checar(u"a serie segmentada com os nomes antigos conta como pronta (pelo "
           u"nome do arquivo, que nao mudou)",
           RS.arquivos_da_serie(nomes, "1.2.3.abcdef12") == nomes
           and RS.e_entregue(nomes[0]) and not RS.e_entregue(nomes[1]))
    leitores, isca = _leitores_do_rotulo()
    checar(u"nenhum leitor decide pelo StructureSetLabel: so o Ver segmentacao "
           u"o le, e so para mostrar", leitores == ["radai_viewseg.py"],
           str(leitores))
    checar(u"  ISCA: um `if ds.StructureSetLabel == ...` seria acusado", isca)


def _le_o_rotulo(arvore):
    for no in ast.walk(arvore):
        if (isinstance(no, ast.Attribute) and no.attr == "StructureSetLabel"
                and isinstance(no.ctx, ast.Load)):
            return True
        if (isinstance(no, ast.Call) and getattr(no.func, "id", "") == "getattr"
                and len(no.args) >= 2 and isinstance(no.args[1], ast.Constant)
                and no.args[1].value == "StructureSetLabel"):
            return True
    return False


def _leitores_do_rotulo():
    fora = []
    for pasta in _componentes.pastas("app"):
        for arq in glob.glob(os.path.join(pasta, "*.py")):
            nome = os.path.basename(arq)
            if " (" in nome:
                continue
            try:
                arvore = ast.parse(io.open(arq, encoding="utf-8").read())
            except Exception:
                continue
            if _le_o_rotulo(arvore):
                fora.append(nome)
    isca = _le_o_rotulo(ast.parse(
        u"if ds.StructureSetLabel == 'RadAI_OAR':\n    pronta = True\n"))
    return sorted(fora), isca


def teste_a_tabela():
    secao(u"os nomes: radai_sets.estruturas_para_tabela")
    t = RS.estruturas_para_tabela("CT")
    chaves = ("task", "nome_padrao", "chave_anatomica", "no_study")
    checar(u"cada linha tem as quatro chaves do contrato",
           t and all(all(k in x for k in chaves) for x in t), str(t[:1]))
    nomes = [x["nome_padrao"] for x in t]
    checar(u"nenhum nome padrao repetido", len(nomes) == len(set(nomes)),
           str(sorted(set(n for n in nomes if nomes.count(n) > 1))))
    anat = [x for x in t if not x["achado"]]
    checar(u"todo nome padrao cabe no TPS (16 ASCII)",
           all(len(x["nome_padrao"]) <= 16 and x["nome_padrao"].isascii()
               for x in anat))
    checar(u"no_study e exatamente a lista do STUDY",
           all(x["no_study"] == (x["chave_anatomica"] in RS.PERMITIDOS_NO_OAR)
               for x in anat))
    disp, _b = RS._disponiveis("CT")
    faltam = sorted(k for k in RS.PERMITIDOS_NO_OAR
                    if k in disp and k not in set(x["chave_anatomica"]
                                                  for x in t))
    checar(u"toda estrutura do STUDY que sai na TC esta na tabela", not faltam,
           str(faltam))
    por = dict((x["chave_anatomica"], x) for x in t)
    checar(u"inclusive as construidas (Skin, Heart, Bag_Bowel_OAR, mamas, "
           u"LNL_UNION, quiasma)",
           all(k in por for k in ("Skin", "heart", "bag_bowel_oar",
                                  "breast_left", "LNL_UNION", "optic_chiasm")))
    checar(u"  e o que so o FULL tem (um lobo) entra para o protocolo",
           "lung_upper_lobe_left" in por
           and not por["lung_upper_lobe_left"]["no_study"])
    checar(u"os niveis (Lvl_*) e a parotida do TotalSegmentator nunca",
           not any(k.startswith("Lvl_") or k.startswith("parotid_gland_")
                   for k in por))
    ach = [x for x in t if x["achado"]]
    checar(u"os achados entram so como ACHADO:<task>, fora do STUDY",
           ach and all(x["nome_padrao"].startswith(RS.PREFIXO_DO_ACHADO)
                       and not x["no_study"] for x in ach),
           str([x["nome_padrao"] for x in ach]))
    mr = dict((x["chave_anatomica"], x) for x in RS.estruturas_para_tabela("MR"))
    checar(u"na RM: o encefalo sim; pele, parede, niveis e quiasma (so TC) nao",
           "brain" in mr and not any(k in mr for k in (
               "Skin", "ChestWall_L", "LNL_UNION", "optic_chiasm")),
           str(sorted(mr)[:8]))


def teste_a_validacao():
    secao(u"a validacao das tags (16 caracteres, ASCII, sem repetir)")
    padroes = ["Heart_ai", "Lung_L_ai", "Lung_R_ai", "Liver_ai", "Kidney_L_ai",
               "SpinalCord_ai", "Esophagus_ai"]
    ok, rec = RS.validar_nomes_proprios(
        {"Heart_ai": "Coracao", "Lung_L_ai": "Heart_ai", "Lung_R_ai": "BODY",
         "Liver_ai": u"Fígado", "Kidney_L_ai": " Rim",
         "SpinalCord_ai": "Medula_com_17_car", "Esophagus_ai": "coracao"},
        padroes, outros=["Pulmoes"])
    checar(u"o nome bom passa", ok == {"Heart_ai": "Coracao"}, str(ok))
    checar(u"repetir o nome padrao de outra estrutura e recusado",
           rec.get("Lung_L_ai") == RS.MOTIVO_REPETIDO)
    checar(u"repetir outra tag (sem distinguir maiuscula) e recusado",
           rec.get("Esophagus_ai") == RS.MOTIVO_REPETIDO)
    checar(u"BODY e recusado (nenhum conjunto declara contorno externo)",
           rec.get("Lung_R_ai") == RS.MOTIVO_EXTERNO)
    checar(u"acento, espaco nas pontas e mais de 16 sao recusados com o motivo",
           rec.get("Liver_ai") == RS.MOTIVO_ASCII
           and rec.get("Kidney_L_ai") == RS.MOTIVO_ESPACO
           and rec.get("SpinalCord_ai") == RS.MOTIVO_LONGO, str(rec))
    ok2, _r = RS.validar_nomes_proprios({"Heart_ai": "Pulmoes"}, padroes,
                                        outros=["Pulmoes"])
    checar(u"a tag que repete o nome de uma uniao e recusada", not ok2)
    checar(u"a descricao guarda o nome padrao e volta a ele",
           RS.nome_padrao_da_descricao(RS.descricao_da_roi("Heart_ai"))
           == "Heart_ai"
           and RS.nome_padrao_da_descricao(
               RS.descricao_da_uniao(["Lung_L_ai", "Lung_R_ai"])) is None)
    import radai_rt as RT

    class _Roi(object):
        def __init__(self, nome, desc):
            self.ROIName, self.ROIDescription = nome, desc

    class _Rt(object):
        def __init__(self, rois):
            self.ds = type("D", (), {"StructureSetROISequence": rois})()

    com_desc = RT.SessaoRT(None, None, None, (1, 1, 1), ["Coracao", "Lung_L_ai"],
                           _Rt([_Roi("Coracao", RS.descricao_da_roi("Heart_ai")),
                                _Roi("Lung_L_ai", RS.descricao_da_roi("Lung_L_ai"))]))
    sem_desc = RT.SessaoRT(None, None, None, (1, 1, 1), ["Coracao"],
                           _Rt([_Roi("Coracao", "")]))
    checar(u"o leitor das Reconstrucoes acha a estrutura renomeada pelo nome "
           u"padrao guardado na descricao",
           com_desc.resolver("heart") == "Coracao"
           and com_desc.resolver("Heart_ai") == "Coracao"
           and com_desc.resolver("lung_left") == "Lung_L_ai",
           "%s %s" % (com_desc.resolver("heart"), com_desc.resolver("Heart_ai")))
    checar(u"  ISCA: sem a descricao, o nome proprio nao e achado",
           sem_desc.resolver("heart") is None)
    with Duble(modo="padrao", nomes={"Heart_ai": "Coracao"}):
        sem = RS.nomes_proprios_em_vigor()
    with Duble(modo="proprios", nomes={"Heart_ai": "Coracao"}):
        com = RS.nomes_proprios_em_vigor()
    checar(u"em Padrao nada vale; em Tags proprias, as tags",
           sem == {} and com == {"Heart_ai": "Coracao"}, "%s %s" % (sem, com))


def teste_o_study_com_nomes_proprios():
    secao(u"os nomes aplicados: o STUDY com as tags, o FULL como esta")
    base = tempfile.mkdtemp(prefix="radai_t_nomes_")
    serie = _serie(base)
    with Duble(nomes={"Heart_ai": "Coracao", "Esophagus_ai": "BODY"}):
        r, linhas = _rodar(base, serie)
    ds, num, desc, alg, ger, _c = _rois(r["oar"])
    full, numf, descf, _a, _g, _cf = _rois(r["full"])
    checar(u"o STUDY tem o rotulo RadAI_STUDY e o FULL, RadAI_FULL",
           str(ds.StructureSetLabel) == "RadAI_STUDY"
           and str(full.StructureSetLabel) == "RadAI_FULL",
           "%s %s" % (ds.StructureSetLabel, full.StructureSetLabel))
    checar(u"a tag entra no STUDY (Heart_ai vira Coracao)",
           "Coracao" in num and "Heart_ai" not in num, str(sorted(num)))
    checar(u"  e o FULL fica com o nome padrao", "Heart_ai" in numf
           and "Coracao" not in numf)
    checar(u"  com o MESMO numero de ROI do FULL",
           num.get("Coracao") == numf.get("Heart_ai"),
           "%s %s" % (num.get("Coracao"), numf.get("Heart_ai")))
    checar(u"a descricao da ROI renomeada guarda o nome padrao e a sugestao",
           desc.get("Coracao") == "Heart_ai - sugestao IA nao aprovada",
           desc.get("Coracao"))
    checar(u"toda ROI do STUDY guarda o nome padrao na descricao",
           all(RS.nome_padrao_da_descricao(desc[n]) for n in num),
           str([n for n in num if not RS.nome_padrao_da_descricao(desc[n])]))
    checar(u"e o algoritmo de geracao e AUTOMATIC",
           set(alg.values()) == {"AUTOMATIC"}, str(set(alg.values())))
    checar(u"a tag BODY foi recusada: o Esophagus_ai sai com o nome padrao",
           "Esophagus_ai" in num and "BODY" not in num
           and any(u"Esophagus_ai foi recusado" in l for l in linhas))
    checar(u"o conjunto diz que ha nome proprio e onde mora o padrao",
           u"nome proprio da estacao" in str(ds.StructureSetDescription))
    checar(u"UNAPPROVED", str(ds.ApprovalStatus) == "UNAPPROVED")
    with Duble(modo="padrao", nomes={"Heart_ai": "Coracao"}):
        r2, _l = _rodar(base, serie)
    _d2, num2, desc2, _a2, _g2, _c2 = _rois(r2["oar"])
    checar(u"em Padrao o STUDY sai com os nomes padrao (a tag nao se perde, "
           u"mas nao vale)", "Heart_ai" in num2 and "Coracao" not in num2)
    checar(u"  e mesmo assim cada ROI guarda o nome padrao na descricao",
           desc2.get("Heart_ai") == "Heart_ai - sugestao IA nao aprovada")


def teste_o_fast_com_nomes_proprios():
    secao(u"o STUDY_Fast com as tags")
    base = tempfile.mkdtemp(prefix="radai_t_nomes_")
    serie = _serie(base)
    with Duble(nomes={"Heart_ai": "Coracao"}):
        r, _l = _rodar(base, serie, modo="fast")
    ds, num, desc, alg, _g, _c = _rois(r["entregue"])
    checar(u"rotulo RadAI_STUDY_Fast", str(ds.StructureSetLabel)
           == "RadAI_STUDY_Fast", str(ds.StructureSetLabel))
    checar(u"a tag vale no STUDY_Fast, com o nome padrao na descricao",
           "Coracao" in num and desc.get("Coracao")
           == "Heart_ai - sugestao IA nao aprovada", str(sorted(num)))


PROTOCOLO = {"id": "p_torax", "nome": u"Tórax próprio", "modalidade": "CT",
             "estruturas": ["Heart_ai", "Lung_LUL_ai", "Lvl_Ia_lnl"],
             "merges": [{"nome": "Pulmoes", "de": ["Lung_L_ai", "Lung_R_ai"]},
                        {"nome": "Esophagus_ai", "de": ["Trachea_ai"]}],
             "tem_achado": False}


def _protocolo():
    p = json.loads(json.dumps(PROTOCOLO))
    p["estruturas"][1] = E.nome_clinico("lung_upper_lobe_left")
    return p


def teste_as_tasks_do_protocolo():
    secao(u"o protocolo: radai_sets.tasks_de_estruturas")
    checar(u"Heart_ai e Bag_Bowel_OAR_ai pedem a cavidade do tronco",
           RS.tasks_de_estruturas(["Heart_ai"]) == ("trunk_cavities",)
           and "trunk_cavities" in RS.tasks_de_estruturas(["Bag_Bowel_OAR_ai"]))
    checar(u"a mandibula pede a craniofacial; a mama, a breasts",
           RS.tasks_de_estruturas(["Bone_Mandible_ai"])
           == ("craniofacial_structures",)
           and RS.tasks_de_estruturas(["Breast_L_ai"]) == ("breasts",))
    checar(u"o pulmao sai da base (nenhuma task a mais)",
           RS.tasks_de_estruturas(["Lung_L_ai"]) == ())
    checar(u"a parotida do STUDY pede o motor dos niveis e o ECM",
           RS.tasks_de_estruturas(["Parotid_L_ai"]) == ("headneck_muscles",)
           and RS.motores_de_estruturas(["Parotid_L_ai"]) == ("hnlnl",))
    checar(u"o achado entra pela task dele", RS.tasks_de_estruturas(
        [RS.PREFIXO_DO_ACHADO + "lung_nodules"]) == ("lung_nodules",))
    checar(u"na RM nada de task da TC",
           RS.tasks_de_estruturas(["Heart_ai", "Bone_Mandible_ai"], "MR") == ())
    sel = RS.selecao_do_protocolo(_protocolo())
    checar(u"a selecao recusa o nivel (Lvl_*) e a uniao com nome repetido",
           "heart" in sel["chaves"]
           and not any(k.startswith("Lvl_") for k in sel["chaves"])
           and [u["nome"] for u in sel["unioes"]] == ["Pulmoes"]
           and any(n == "Esophagus_ai" for n, _m in sel["recusadas"]),
           str(sel))
    checar(u"as tasks do protocolo incluem as das unioes",
           RS.tasks_do_protocolo(_protocolo()) == ("trunk_cavities",))


def teste_o_study_do_protocolo():
    secao(u"o protocolo aplicado: o STUDY sai com as estruturas e as unioes do "
          u"protocolo")
    base = tempfile.mkdtemp(prefix="radai_t_nomes_")
    serie = _serie(base)
    p = _protocolo()
    with Duble(nomes={"Heart_ai": "Coracao"}, protocolos=[p]):
        r, linhas = _rodar(base, serie, protocolo=p,
                           oar_fora=[E.nome_clinico("lung_upper_lobe_left")])
        r2, _l2 = _rodar(base, serie, protocolo=p)
    ds, num, desc, alg, ger, cont = _rois(r2["oar"])
    _f, numf, _df, _af, _gf, _cf = _rois(r2["full"])
    lul = E.nome_clinico("lung_upper_lobe_left")
    checar(u"o STUDY tem so o que o protocolo pede (com as tags) e a uniao",
           set(num) == {"Coracao", lul, "Pulmoes"}, str(sorted(num)))
    checar(u"  o lobo, que o STUDY padrao nao leva, entra pelo protocolo",
           lul in num)
    checar(u"a uniao tem contorno, e a descricao diz de que ela e feita",
           cont.get(num.get("Pulmoes"), 0) > 0
           and desc.get("Pulmoes") ==
           "uniao de Lung_L_ai + Lung_R_ai - sugestao IA nao aprovada",
           desc.get("Pulmoes"))
    checar(u"  com a procedencia da uniao e o algoritmo AUTOMATIC",
           ger.get("Pulmoes") == "Radioterapia.AI (uniao, protocolo proprio)"
           and alg.get("Pulmoes") == "AUTOMATIC")
    checar(u"numeros de ROI unicos, e a uniao depois do plano do FULL",
           len(set(num.values())) == len(num)
           and num["Pulmoes"] > max(numf.values()),
           "%s %s" % (num, max(numf.values())))
    checar(u"o FULL nao muda: nem a uniao nem a tag entram nele",
           "Pulmoes" not in numf and "Heart_ai" in numf and "Coracao" not in numf)
    checar(u"o log diz a uniao recusada pelo nome repetido",
           any(u"Esophagus_ai" in l and u"nao entra" in l for l in _l2))
    _d, num_x, _de, _al, _ge, _co = _rois(r["oar"])
    checar(u"o «x» tira estrutura do protocolo nesta serie",
           lul not in num_x and "Coracao" in num_x, str(sorted(num_x)))


def teste_o_rodar_agora_com_protocolo():
    secao(u"o PERSONALIZADO do «Rodar agora»: a chave, as tasks travadas e o "
          u"achado declarado")
    import radai_batch as L
    import radai_review as R
    p = _protocolo()
    pa = dict(p, id="p_nod", nome=u"Com nódulo",
              estruturas=list(p["estruturas"])
              + [RS.PREFIXO_DO_ACHADO + "lung_nodules"])
    with Duble(nomes={"Heart_ai": "Coracao"},
               protocolos=[p, pa, dict(p, id="p_rm", modalidade="MR")]):
        s = {"modo": "perso", "modalidade": "CT", "uid": "1.2.3.4.5.6",
             "date": "20261025", "protocolos": ["torax_mama"],
             "protocolo_proprio": "p_torax"}
        e = L.escolha_da_serie(s)
        checar(u"ligar o protocolo proprio desliga os protocolos RT",
               e["protocolo_proprio"] == "p_torax" and e["protocolos"] == ())
        perm, ach = L._achados_e_permitidas()
        ts = L.tasks_do_perso(e, permitidas=perm, achados=ach)
        checar(u"as tasks que as estruturas exigem entram", "trunk_cavities"
               in ts, str(ts))
        sn = dict(s, protocolo_proprio="p_nod")
        ts_sem = L.tasks_do_perso(L.escolha_da_serie(sn), permitidas=perm,
                                  achados=ach)
        ts_com = L.tasks_do_perso(L.escolha_da_serie(
            dict(sn, achado_declarado=True)), permitidas=perm, achados=ach)
        ts_str = L.tasks_do_perso(L.escolha_da_serie(
            dict(sn, achado_declarado="true")), permitidas=perm, achados=ach)
        checar(u"o achado do protocolo roda so declarado nesta execucao",
               "lung_nodules" not in ts_sem and "lung_nodules" in ts_com,
               "%s | %s" % (ts_sem, ts_com))
        checar(u"  ISCA: o texto 'true' nao e declaracao (so o true literal)",
               "lung_nodules" not in ts_str)
        tela = L.protocolos_proprios_da_tela("CT")
        checar(u"a tela recebe so os protocolos da modalidade, com o achado "
               u"marcado", [x["id"] for x in tela] == ["p_torax", "p_nod"]
               and [x["tem_achado"] for x in tela] == [False, True]
               and tela[1]["achados"] == ["lung_nodules"]
               and "trunk_cavities" in tela[0]["tasks"], str(tela))
        checar(u"  e na RM so o de RM",
               [x["id"] for x in L.protocolos_proprios_da_tela("MR")]
               == ["p_rm"])
        checar(u"sem protocolo da modalidade, a chave nem aparece (lista vazia)",
               L.protocolos_proprios_da_tela("CT") != [] and Duble is not None)
        prev = L.previa_da_entrega(dict(s))
        nomes = [x["nome"] for x in prev["oar"]["estruturas"]]
        checar(u"a previa mostra o STUDY do protocolo, com a tag e a uniao",
               "Pulmoes" in nomes and "Coracao" in nomes
               and any(x.get("uniao") for x in prev["oar"]["estruturas"]),
               str(nomes))
        fila = L._com_escolhas_da_tela({"series": [dict(sn, achado_declarado=True)]})
        checar(u"o envio a fila leva o protocolo e a declaracao",
               fila[0].get("protocolo_proprio") == "p_nod"
               and fila[0].get("achado_declarado") is True, str(fila[0]))
        decl = R.achados_declarados([dict(sn, achado_declarado=True),
                                     dict(sn)])
        checar(u"o INICIAR mostra o achado declarado, e so o declarado",
               len(decl) == 1 and decl[0]["tasks"] == ["lung_nodules"]
               and decl[0]["protocolo"] == u"Com nódulo", str(decl))
        mot = L.motores_do_perso(L.escolha_da_serie(dict(
            s, protocolo_proprio="p_par")))
    with Duble(protocolos=[dict(p, id="p_par", estruturas=["Parotid_L_ai"],
                                merges=[])]):
        mot = L.motores_do_perso(L.escolha_da_serie(dict(
            s, protocolo_proprio="p_par")))
    checar(u"o motor que a estrutura exige (niveis) fica ligado",
           mot.get("hnlnl") is True, str(mot))
    with Duble(protocolos=[]):
        e0 = L.escolha_da_serie(dict(s, protocolo_proprio="sumiu"))
        linhas = []
        checar(u"protocolo que sumiu: o STUDY sai pela lista padrao, com alerta",
               L.protocolo_proprio_da_escolha(e0, log=linhas.append) is None
               and any(u"ALERTA" in l for l in linhas))


def _chromium():
    base = os.path.join(os.environ.get("LOCALAPPDATA", ""), "ms-playwright")
    if not os.path.isdir(base):
        return None
    for nome in sorted(os.listdir(base), reverse=True):
        if not nome.startswith("chromium-"):
            continue
        for sub in ("chrome-win64", "chrome-win"):
            exe = os.path.join(base, nome, sub, "chrome.exe")
            if os.path.isfile(exe):
                return exe
    return None


def _subir(tmp):
    from datetime import timedelta
    root = os.path.join(tmp, "share")
    for nome, dias, cortes in (("PAC_A", 1, 20), ("PAC_B", 2, 18)):
        escreve_serie(os.path.join(root, nome, "CT"), nome,
                      datetime.now() - timedelta(days=dias), cortes)
    calib = os.path.join(tmp, "calib")
    cfg = os.path.join(tmp, "t.config")
    io.open(cfg, "w", encoding="utf-8").write(
        u"ROOT=%s\nDRY_RUN=1\nMIN_SLICES=5\nQUIET_MIN=0\nTPS_DESTINO=eclipse\n"
        u"PORT=%d\nLOG_DIR=%s\nPASTA_FAVORITA=%s\n"
        % (root, PORTA, os.path.join(tmp, "log"), root))
    env = dict(os.environ, RADAI_CONFIG=cfg, RADAI_MACHINE="BATERIA_NOMES",
               RADAI_CALIB_DIR=calib, RADAI_REGISTRO_DIR=os.path.join(tmp, "reg"),
               LOCALAPPDATA=os.path.join(tmp, "ad"), RADAI_NOTIFICACAO="0",
               RADAI_URL_VERSOES="0", PYTHONIOENCODING="utf-8:replace",
               RADAI_FILA_DIR=os.path.join(tmp, "fila"))
    velho = os.environ.get("RADAI_CALIB_DIR")
    os.environ["RADAI_CALIB_DIR"] = calib
    try:
        import radai_consent
        radai_consent.registrar_aceite(u"bateria dos nomes proprios")
    finally:
        os.environ["RADAI_CALIB_DIR"] = velho
    saida = io.open(os.path.join(tmp, "vigia.log"), "wb")
    proc = subprocess.Popen([sys.executable,
                             _componentes.fonte("app/radai_watcher.py")],
                            env=env, stdout=saida, stderr=subprocess.STDOUT)
    for _ in range(90):
        try:
            urllib.request.urlopen(BASE + "/api/fila", timeout=2).read()
            return proc, root
        except Exception:
            time.sleep(1)
    proc.kill()
    return None, root


PROTS_DA_TELA = [
    {"id": "p1", "nome": u"Tórax próprio", "tasks": ["trunk_cavities"],
     "motores": [], "achados": [], "tem_achado": False, "n_estruturas": 3,
     "n_unioes": 1},
    {"id": "p2", "nome": u"Com nódulo", "tasks": ["trunk_cavities"],
     "motores": [], "achados": ["lung_nodules"], "tem_achado": True,
     "n_estruturas": 4, "n_unioes": 0},
]


async def _navegar(exe, root, prints):
    from playwright.async_api import async_playwright
    async with async_playwright() as pw:
        nav = await pw.chromium.launch(executable_path=exe, headless=True)
        try:
            ctx = await nav.new_context(viewport={"width": 1280, "height": 800})
            pg = await ctx.new_page()
            erros, enviados = [], []
            pg.on("pageerror", lambda e: erros.append(str(e)))

            async def _opcoes(route):
                resp = await route.fetch()
                d = await resp.json()
                if (d or {}).get("modalidade") == "CT":
                    d["protocolos_proprios"] = PROTS_DA_TELA
                await route.fulfill(response=resp, json=d)

            async def _fila(route):
                enviados.append(json.loads(route.request.post_data or "{}"))
                await route.fulfill(json={"ok": True, "enfileiradas": 1})

            await pg.route("**/api/lote/opcoes*", _opcoes)
            await pg.route("**/api/lote/enfileirar", _fila)
            await pg.goto(BASE + "/aceite", wait_until="domcontentloaded")
            await pg.evaluate("localStorage.setItem('radai_idioma', 'pt-BR')")
            await pg.goto(BASE + "/lote", wait_until="networkidle")
            await pg.wait_for_timeout(700)
            await pg.keyboard.press("Escape")
            await pg.wait_for_timeout(300)
            n = await pg.evaluate("""(root) => new Promise((ok) => {
              window.uiVarrer({uso: 'lote', chave: 'bateria', pasta: root, dias: 0,
                aoFim: (linhas) => {
                  SERIES = linhas || []; sincronizarIncl(); pintarTabela();
                  if(window.psAbrir) psAbrir('cx2', true);
                  ok(SERIES.length);
                },
                aoErro: () => ok(-1)});
            })""", root)
            checar(u"[tela] as series fantoma chegam a tabela", n == 2, str(n))
            await pg.wait_for_selector("#tab tr[id^=linha_]", timeout=30000)
            await pg.wait_for_timeout(800)
            await pg.click("#cartsel")
            await pg.wait_for_timeout(300)
            await pg.evaluate("""() => { const s = document.querySelector('#tab select.md-sel');
               s.value = 'perso'; s.dispatchEvent(new Event('change', {bubbles:true})); }""")
            await pg.wait_for_selector("tr.perso .p4", timeout=10000)
            await pg.wait_for_timeout(500)
            est = await pg.evaluate("""() => {
              const p = document.querySelector('tr.perso .p4');
              const sel = p.querySelector('select.p4-pp-sel');
              return {ck: p.querySelectorAll('input.p4-pp-ck').length,
                      sel: !!sel, desab: sel ? sel.disabled : null,
                      opts: sel ? [...sel.options].map(o => o.textContent) : []};
            }""")
            checar(u"[tela] a chave e o dropdown aparecem com protocolo da "
                   u"modalidade", est["ck"] == 1 and est["sel"]
                   and est["desab"] is True and len(est["opts"]) == 2,
                   json.dumps(est, ensure_ascii=False))
            checar(u"[tela]   e o dropdown marca o protocolo com achado",
                   any(u"ACHADO" in o for o in est["opts"][1:]),
                   json.dumps(est["opts"], ensure_ascii=False))
            await pg.evaluate("""() => { const x = document.querySelector('tr.perso input.p4-prot-ck');
               x.checked = true; x.dispatchEvent(new Event('change', {bubbles:true})); }""")
            await pg.wait_for_timeout(200)
            await pg.evaluate("""() => { const x = document.querySelector('tr.perso input.p4-pp-ck');
               x.checked = true; x.dispatchEvent(new Event('change', {bubbles:true})); }""")
            await pg.wait_for_timeout(500)
            est = await pg.evaluate("""() => {
              const p = document.querySelector('tr.perso .p4');
              const tc = p.querySelector('input.p4-task-ck[data-task=trunk_cavities]');
              return {prot: [...p.querySelectorAll('input.p4-prot-ck')].some(x => x.checked),
                      livre: p.querySelector('input.p4-livre-ck').checked,
                      pp: p.querySelector('input.p4-pp-ck').checked,
                      desab: p.querySelector('select.p4-pp-sel').disabled,
                      tc: tc ? {on: tc.checked, trava: tc.disabled} : null,
                      nota: !!p.querySelector('.p4-pp-nota')};
            }""")
            checar(u"[tela] ligar a chave desliga os protocolos RT e a Seleção "
                   u"livre", est["pp"] and not est["prot"] and not est["livre"]
                   and est["desab"] is False, json.dumps(est))
            checar(u"[tela]   e a task exigida fica ligada e travada",
                   est["tc"] and est["tc"]["on"] and est["tc"]["trava"],
                   json.dumps(est))
            pay = json.loads(await pg.evaluate(
                "JSON.stringify(payloadDaSerie(SERIES[0]))"))
            checar(u"[tela] o payload leva o protocolo_proprio e nenhum "
                   u"protocolo RT", pay.get("protocolo_proprio") == "p1"
                   and pay.get("protocolos") == []
                   and "achado_declarado" not in pay, json.dumps(pay)[:300])
            if prints:
                await _prints(pg, prints, u"protocolo_proprio")
            await pg.evaluate("""() => { const s = document.querySelector('tr.perso select.p4-pp-sel');
               s.value = 'p2'; s.dispatchEvent(new Event('change', {bubbles:true})); }""")
            await pg.wait_for_timeout(500)
            nota = await pg.evaluate(
                "!!document.querySelector('tr.perso .p4-pp-nota')")
            checar(u"[tela] o protocolo com achado mostra a nota da declaracao",
                   nota)
            await pg.click("#btrodar")
            await pg.wait_for_timeout(700)
            pnl = await pg.evaluate("""() => {
              const v = document.querySelector('.ui-pnl-veu.vis');
              return v ? (v.querySelector('#ui-pnl-tit')||{}).textContent : '';
            }""")
            checar(u"[tela] enviar à fila com achado pede a declaracao",
                   u"ACHADO" in (pnl or u"") and not enviados,
                   u"%s | %d" % (pnl, len(enviados)))
            if prints:
                await _prints(pg, prints, u"declaracao_do_achado", so_um=True)
            await pg.click("#ui-pnl-sim")
            await pg.wait_for_timeout(900)
            ss = (enviados[-1] if enviados else {}).get("series") or []
            com = [x for x in ss if x.get("protocolo_proprio") == "p2"]
            checar(u"[tela]   e o envio leva achado_declarado=true na serie do "
                   u"protocolo, e so nela",
                   com and all(x.get("achado_declarado") is True for x in com)
                   and not any("achado_declarado" in x for x in ss
                               if x not in com),
                   json.dumps([(x.get("protocolo_proprio"),
                                x.get("achado_declarado")) for x in ss]))
            rev = await pg.evaluate("""() => {
              radaiRevAbrir({n_series: 1, series: [{pid: 'PAC_A', uid8: '00000001', cortes: 20}],
                             tasks: ['total_v3', 'lung_nodules'], device: 'cpu', suavizar_mm: 1.5,
                             estimativa: '~5 min', conjuntos: [], estudos: [], problemas: [],
                             estacao: {}, achados_declarados: [{uid8: '00000001',
                               protocolo: 'Com nódulo', tasks: ['lung_nodules']}]},
                            function(){});
              const b = [...document.querySelectorAll('#radai_rev .rev-bl')]
                .find(x => (x.textContent || '').indexOf('lung_nodules') >= 0
                           && (x.textContent || '').indexOf('Com nódulo') >= 0);
              return {bloco: !!b, alerta: b ? b.classList.contains('rev-alerta') : false,
                      fronteira: !!document.getElementById('radai_rev_fronteira')};
            }""")
            checar(u"[tela] o INICIAR mostra o achado declarado do protocolo "
                   u"proprio, em alerta, com a frase da fronteira",
                   rev["bloco"] and rev["alerta"] and rev["fronteira"],
                   json.dumps(rev))
            if prints:
                await _prints(pg, prints, u"iniciar_com_achado", so_um=True)
            await pg.evaluate("radaiRevFechar()")
            checar(u"[tela] sem erro de JavaScript", not erros,
                   u" | ".join(erros[:3]))
        finally:
            await nav.close()


async def _prints(pg, pasta, nome, so_um=False):
    os.makedirs(pasta, exist_ok=True)
    combos = [("escuro",)] if so_um else [("escuro",), ("claro",)]
    for (tema,) in combos:
        await pg.evaluate("t => uiTema(t)", tema)
        await pg.wait_for_timeout(300)
        await pg.evaluate(
            "() => { const p = document.querySelector('tr.perso'); if(p) p.scrollIntoView({block:'center'}) }")
        await pg.screenshot(path=os.path.join(pasta, "nomes_%s_1280_%s.png"
                                              % (nome, tema)))
    await pg.evaluate("t => uiTema(t)", "escuro")


def teste_a_tela():
    secao(u"a tela renderizada (Chromium, vigia de verdade, series fantoma)")
    try:
        import playwright
    except Exception:
        print(u"  PULADO: sem Playwright neste Python")
        return
    exe = _chromium()
    if not exe:
        print(u"  PULADO: sem o Chromium do Playwright na maquina")
        return
    tmp = tempfile.mkdtemp(prefix="radai_t_nomes_")
    proc, root = _subir(tmp)
    if proc is None:
        checar(u"o vigia de teste subiu", False,
               io.open(os.path.join(tmp, "vigia.log"), encoding="utf-8",
                       errors="replace").read()[-400:])
        return
    try:
        asyncio.run(_navegar(exe, root,
                             os.environ.get("RADAI_PRINTS_DIR") or None))
    finally:
        try:
            urllib.request.urlopen(urllib.request.Request(
                BASE + "/api/encerrar", data=b"", method="POST"), timeout=5)
        except Exception:
            pass
        proc.kill()
        try:
            proc.wait(timeout=10)
        except Exception:
            pass


def main():
    print(u"=" * 68)
    print(u"test_nomes_proprios | os rotulos FULL/STUDY, as tags proprias e o "
          u"protocolo proprio")
    print(u"=" * 68)
    for t in (teste_os_rotulos, teste_a_tabela, teste_a_validacao,
              teste_o_study_com_nomes_proprios,
              teste_o_fast_com_nomes_proprios, teste_as_tasks_do_protocolo,
              teste_o_study_do_protocolo, teste_o_rodar_agora_com_protocolo,
              teste_a_tela):
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
