# -*- coding: utf-8 -*-
import io
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime

try:
    sys.stdout.reconfigure(errors="replace")
except Exception:
    pass

import numpy as np

AQUI = os.path.dirname(os.path.abspath(__file__))


def pasta_app(aqui):
    for c in (os.path.join(aqui, "..", "app"), os.path.join(aqui, "..")):
        if os.path.exists(os.path.join(c, "engine.py")):
            return os.path.abspath(c)
    return os.path.abspath(os.path.join(aqui, "..", "app"))


sys.path.insert(0, pasta_app(AQUI))
APP_DIR = pasta_app(AQUI)

sys.path.insert(0, AQUI)

os.environ["RADAI_CALIB_DIR"] = tempfile.mkdtemp(prefix="radai_ac_motor_")
os.environ["TOTALSEG_HOME_DIR"] = tempfile.mkdtemp(prefix="radai_tshome_motor_")
import atexit
atexit.register(shutil.rmtree, os.environ["TOTALSEG_HOME_DIR"], True)

import engine as M
from make_test_series import escreve_serie

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _cleanup
import _componentes
_cleanup.adotar_prefixo('radai_teste_')
_cleanup.adotar_prefixo('radai_ac_motor_')
_cleanup.adotar_prefixo('radai_tshome_motor_')


VERBOSO = "-v" in sys.argv
_RESULTADOS = []


def checar(nome, condicao, detalhe=""):
    ok = bool(condicao)
    _RESULTADOS.append((nome, ok, detalhe))
    if VERBOSO or not ok:
        print("  %s  %s%s" % ("OK   " if ok else "FALHA", nome,
                              ("  [%s]" % detalhe) if detalhe else ""))
    return ok


def teste_nome_clinico():
    checar("TG-263 aplicado: heart -> Heart_ai", M.nome_clinico("heart") == "Heart_ai",
           M.nome_clinico("heart"))

    checar(u"a NOSSA entrega diz area, e nao orgao",
           M.nome_clinico("prostate") == "ProstaticArea_ai",
           M.nome_clinico("prostate"))
    checar(u"e cabe nos 16 com o sufixo",
           len("ProstaticArea_ai") == 16)
    for suf, esperado in ((M.SUFIXO_TS, "Prostate_ts"),
                          ("_v3D", "Prostate_v3D"),
                          ("_cds", "Prostate_cds")):
        checar(u"o conjunto `%s` mantem o nome do modelo" % suf,
               M.nome_clinico("prostate", sufixo=suf) == esperado,
               M.nome_clinico("prostate", sufixo=suf))
    checar(u"a tabela e SO do `_ai`, e esta declarada",
           hasattr(M, "TG263_SO_NOSSO") and "prostate" in M.TG263_SO_NOSSO)
    checar("TG-263 com lado: lung_left -> Lung_L_ai",
           M.nome_clinico("lung_left") == "Lung_L_ai", M.nome_clinico("lung_left"))
    checar("TG-263: parotida", M.nome_clinico("parotid_gland_right") == "Parotid_R_ai",
           M.nome_clinico("parotid_gland_right"))
    checar("TG-263: adrenal (nome oficial, com a raiz encurtada)",
           M.nome_clinico("adrenal_gland_left") == "Glnd_Adrena_L_ai",
           M.nome_clinico("adrenal_gland_left"))
    checar("e a cauda (lado + procedencia) sobreviveu ao truncamento",
           M.nome_clinico("adrenal_gland_left").endswith("_L_ai"))

    checar(u"o rotulo CRU chega ao TG-263 no `_ai`: "
           u"small_bowel -> Bowel_Small_ai",
           M.nome_clinico("small_bowel") == "Bowel_Small_ai",
           M.nome_clinico("small_bowel"))
    checar(u"  e o entregue continua igual (ele ja vinha pelo amigavel)",
           M.nome_clinico("small_intestine") == M.nome_clinico("small_bowel"),
           "%s vs %s" % (M.nome_clinico("small_intestine"),
                         M.nome_clinico("small_bowel")))
    checar(u"  brainstem -> Brainstem_ai",
           M.nome_clinico("brainstem") == "Brainstem_ai",
           M.nome_clinico("brainstem"))
    for suf in ("_ts", "_nv", "_cds", "_mse"):
        checar(u"o conjunto `%s` guarda o nome do motor dele" % suf,
               M.nome_clinico("small_bowel", sufixo=suf) == "small_bowel" + suf,
               M.nome_clinico("small_bowel", sufixo=suf))
    checar(u"a tabela e DERIVADA do `TS_MAP` e nao esta vazia",
           hasattr(M, "ALIAS_DO_CRU") and len(M.ALIAS_DO_CRU) > 0,
           str(len(getattr(M, "ALIAS_DO_CRU", ()))))
    checar(u"  e nenhum rotulo cru dela e chave do proprio `TS_MAP` "
           u"(senao o alias reescreveria um nome que ja e amigavel)",
           not [c for c in M.ALIAS_DO_CRU if c in M.TS_MAP],
           ", ".join([c for c in M.ALIAS_DO_CRU if c in M.TS_MAP][:3]))
    _nomes = [M.nome_clinico(c) for c in sorted(M.ALIAS_DO_CRU)]
    _repetidos = sorted(n for n in set(_nomes) if _nomes.count(n) > 1)
    checar(u"os %d nomes do alias nascem DISTINTOS depois do truncamento, "
           u"sem precisar de desempate" % len(M.ALIAS_DO_CRU),
           not _repetidos, ", ".join(_repetidos[:3]))

    _crus = set()
    for _por_task in M.TS_MAP.values():
        if isinstance(_por_task, dict):
            for _lista in _por_task.values():
                _crus.update(_lista)
    _todos = [M.nome_clinico(c) for c in sorted(_crus)]
    _col = sorted(n for n in set(_todos) if _todos.count(n) > 1)
    checar(u"no `_full` com os %d rotulos crus do motor, nenhum nome colide"
           % len(_crus), not _col, ", ".join(_col[:3]))

    import ast as _a
    _f = io.open(_componentes.fonte("app/engine.py"),
                 encoding="utf-8", errors="replace").read()
    _arv = _a.parse(_f)
    _run = [n for n in _a.walk(_arv)
            if isinstance(n, _a.FunctionDef) and n.name == "run_ts_task"]
    checar(u"`run_ts_task` existe", bool(_run))
    if _run:
        _asserts = [n for n in _a.walk(_run[0]) if isinstance(n, _a.Assert)]
        checar(u"a trava da resolucao cheia NAO e um `assert` "
               u"(`python -O` os remove)", not _asserts,
               u"%d assert(s) dentro de `run_ts_task`" % len(_asserts))
        _raises = [n for n in _a.walk(_run[0]) if isinstance(n, _a.Raise)]
        checar(u"  e ela LEVANTA", bool(_raises))
    checar(u"o motivo clínico está num GUARDA: no ponto, e não só o técnico",
           any(u"GUARDA:" in a and u"radioterapia" in a + b
               for a, b in zip(_f.splitlines(), _f.splitlines()[1:])))
    checar(u"e os dois modos estão nomeados",
           "--fastest" in _f and "--fast" in _f)

    sem_tg = sorted(n for n in M.TS_MAP if n not in M.TG263)
    if sem_tg:
        alvo = sem_tg[0]
        checar("sem TG-263 mantem o nome do TS (exemplo vivo: %s)" % alvo,
               M.nome_clinico(alvo) == (alvo + "_ai")[:16]
               or M.nome_clinico(alvo).endswith("_ai"),
               M.nome_clinico(alvo))
    else:
        checar("todas as estruturas do TS_MAP tem TG-263", True,
               "nao ha mais exemplo de 'sem TG-263'")
    checar("`hypopharynx` ganhou TG-263",
           M.nome_clinico("hypopharynx") == "Pharynx_Hypo_ai",
           M.nome_clinico("hypopharynx"))
    checar("`nasopharynx` tambem",
           M.nome_clinico("nasopharynx") == "Pharynx_Naso_ai",
           M.nome_clinico("nasopharynx"))
    checar("nome do TS longo demais e encurtado pela raiz",
           M.nome_clinico("costal_cartilages").endswith("_ai") and
           len(M.nome_clinico("costal_cartilages")) <= 16,
           M.nome_clinico("costal_cartilages"))

    consts = [M.nome_clinico("pharyngeal_constrictor_%s" % s)
              for s in ("superior", "middle", "inferior")]
    checar("constritores mantem S/M/I no truncamento",
           all(any(c.endswith(q + "_ai") for q in ("_S", "_M", "_I")) for c in consts),
           ", ".join(consts))
    checar("os tres constritores tem nomes distintos", len(set(consts)) == 3, ", ".join(consts))

    longo = M.nome_clinico("submandibular_gland_left")
    checar("nome longo cabe no limite do Eclipse (16)", len(longo) <= 16,
           "%s (%d)" % (longo, len(longo)))
    checar("truncamento preserva o sufixo _ai", longo.endswith("_ai"), longo)
    checar("truncamento preserva o lado _L", "_L_ai" in longo, longo)

    todos = [M.nome_clinico(n) for n in sorted(M.TS_MAP.keys())]
    checar("TODA estrutura do catalogo cabe em 16 caracteres",
           all(len(n) <= 16 for n in todos),
           "estouram: %s" % [n for n in todos if len(n) > 16])
    checar("TODA estrutura do catalogo leva o sufixo _ai",
           all(n.endswith("_ai") for n in todos),
           "sem sufixo: %s" % [n for n in todos if not n.endswith("_ai")])
    def tem_lado(nome, curto, longo):
        return curto in nome or longo in nome

    esq = [M.nome_clinico(n) for n in M.TS_MAP if n.endswith("_left")]
    dir_ = [M.nome_clinico(n) for n in M.TS_MAP if n.endswith("_right")]
    checar("nenhuma estrutura esquerda perde o lado no truncamento",
           all(tem_lado(n, "_L", "_left") for n in esq),
           "sem lado: %s" % [n for n in esq if not tem_lado(n, "_L", "_left")])
    checar("nenhuma estrutura direita perde o lado no truncamento",
           all(tem_lado(n, "_R", "_right") for n in dir_),
           "sem lado: %s" % [n for n in dir_ if not tem_lado(n, "_R", "_right")])

    usados = set()
    a = M.nome_clinico("submandibular_gland_left", usados)
    b = M.nome_clinico("submandibular_gland_left", usados)
    checar("colisao de nome e desambiguada", a != b, "%s vs %s" % (a, b))
    checar("nome desambiguado ainda cabe", len(b) <= 16, b)

    todos_usados = set()
    finais = [M.nome_clinico(n, todos_usados) for n in sorted(M.TS_MAP)]
    checar("o catalogo inteiro gera nomes UNICOS",
           len(set(finais)) == len(finais),
           "%d nomes, %d unicos" % (len(finais), len(set(finais))))
    checar("nenhuma estrutura fica so com o sufixo",
           all(len(n) > len("_ai") + 2 for n in finais))
    checar("ha uma lista de correspondencias TG-263 para revisao medica",
           len(M.tg263_a_conferir()) > 0, "%d a conferir" % len(M.tg263_a_conferir()))


def teste_nivel_numerado_sobrevive():
    import re
    niveis = (["vertebrae_c%d" % i for i in range(1, 8)] +
              ["vertebrae_t%d" % i for i in range(1, 13)] +
              ["vertebrae_l%d" % i for i in range(1, 6)] + ["vertebrae_s1"] +
              ["rib_%d_%s" % (i, lado) for i in range(1, 13)
               for lado in ("left", "right")])

    for sufixo in (M.SUFIXO_AI, M.SUFIXO_NV):
        usados = set()
        saida = {n: M.nome_clinico(n, usados, sufixo=sufixo) for n in niveis}

        checar("%s: todos cabem em 16" % sufixo,
               all(len(v) <= 16 for v in saida.values()),
               str([v for v in saida.values() if len(v) > 16]))
        checar("%s: todos mantem o sufixo de procedencia" % sufixo,
               all(v.endswith(sufixo) for v in saida.values()),
               str([v for v in saida.values() if not v.endswith(sufixo)]))
        checar("%s: nomes unicos" % sufixo,
               len(set(saida.values())) == len(saida),
               "%d nomes, %d unicos" % (len(saida), len(set(saida.values()))))

        def numero(txt):
            if txt.endswith(sufixo):
                txt = txt[:-len(sufixo)]
            achados = re.findall(r"\d+", txt)
            return achados[-1] if achados else ""
        errados = {n: v for n, v in saida.items()
                   if numero(v) != numero(n.replace("_left", "").replace("_right", ""))}
        checar("%s: o numero do nivel chega inteiro ao nome final" % sufixo,
               not errados, str(sorted(errados.items())[:5]))

        checar("%s: T1 e T10 continuam distintos" % sufixo,
               saida["vertebrae_t1"] != saida["vertebrae_t10"],
               "%s vs %s" % (saida["vertebrae_t1"], saida["vertebrae_t10"]))
        checar("%s: e as costelas nao perdem o lado" % sufixo,
               all(("_L" in saida["rib_%d_left" % i] or
                    "left" in saida["rib_%d_left" % i]) and
                   ("_R" in saida["rib_%d_right" % i] or
                    "right" in saida["rib_%d_right" % i])
                   for i in range(1, 13)),
               str([saida["rib_%d_left" % i] for i in range(1, 13)][:3]))


def teste_contorno_degenerado_vira_poligono():
    print("\n-- contorno de menos de 3 pontos --")

    class Item(object):
        def __init__(self, dados):
            self.ContourData = list(dados)

    class Contorno(object):
        def __init__(self, roi, seq):
            self.ReferencedROINumber = roi
            self.ContourSequence = seq

    class Roi(object):
        def __init__(self, n):
            self.ROINumber = n
            self.ROIName = "R%d" % n

    class Obs(object):
        def __init__(self, n):
            self.ReferencedROINumber = n

    class DS(object):
        pass

    bom = [0, 0, 5, 2, 0, 5, 2, 2, 5, 0, 2, 5]
    ds = DS()
    ds.ROIContourSequence = [
        Contorno(1, [Item(bom), Item([10, 20, 5])]),
        Contorno(2, [Item([0, 0, 3, 1, 0, 3])]),
        Contorno(3, [Item(bom)]),
        Contorno(4, []),
    ]
    ds.StructureSetROISequence = [Roi(n) for n in (1, 2, 3, 4)]
    ds.RTROIObservationsSequence = [Obs(n) for n in (1, 2, 3, 4)]

    n = M._reparar_contornos_degenerados(ds, "pasta_que_nao_existe")
    checar("conta os reparados", n == 2, str(n))

    por_roi = {int(rc.ReferencedROINumber): rc for rc in ds.ROIContourSequence}
    checar("nenhuma fatia foi perdida", len(por_roi[1].ContourSequence) == 2,
           str(len(por_roi[1].ContourSequence)))
    d = por_roi[1].ContourSequence[1].ContourData
    checar("o ponto virou 4 pontos", len(d) == 12, str(len(d)))
    checar("no mesmo z", d[2] == 5 and d[5] == 5 and d[11] == 5, str(d))
    checar("centrado onde estava", abs((min(d[0::3]) + max(d[0::3])) / 2 - 10) < 1e-6
           and abs((min(d[1::3]) + max(d[1::3])) / 2 - 20) < 1e-6, str(d))
    checar("com um voxel de lado (sem PixelSpacing, 1 mm)",
           abs((max(d[0::3]) - min(d[0::3])) - 1.0) < 1e-6, str(d))
    checar("e o contador de pontos foi corrigido",
           por_roi[1].ContourSequence[1].NumberOfContourPoints == 4)

    d2 = por_roi[2].ContourSequence[0].ContourData
    checar("o de 2 pontos vira retangulo que cobre os dois",
           abs((max(d2[0::3]) - min(d2[0::3])) - 2.0) < 1e-6, str(d2))
    checar("a ROI boa fica intacta",
           por_roi[3].ContourSequence[0].ContourData == bom)
    checar("a ROI vazia SAI", 4 not in por_roi, str(sorted(por_roi)))
    checar("e sai tambem do StructureSetROISequence",
           [r.ROINumber for r in ds.StructureSetROISequence] == [1, 2, 3])
    checar("e das observacoes (senao o TPS acha ROI sem contorno)",
           [o.ReferencedROINumber for o in ds.RTROIObservationsSequence] == [1, 2, 3])
    checar("nenhum contorno degenerado sobrou",
           all(len(c.ContourData) // 3 >= M.MIN_PONTOS_CONTORNO
               for rc in ds.ROIContourSequence for c in rc.ContourSequence))

    checar("dataset sem contornos nao explode",
           M._reparar_contornos_degenerados(DS(), "x") == 0)
    fonte = open(os.path.join(pasta_app(AQUI), "engine.py"), encoding="utf-8").read()
    checar("roda ANTES de formatar o ContourData",
           _reparo_vem_antes_da_formatacao(fonte))
    import ast as _ast
    _linhas = fonte.splitlines(True)
    _no = next((n for n in _ast.walk(_ast.parse(fonte))
                if isinstance(n, _ast.Expr) and isinstance(n.value, _ast.Call)
                and getattr(n.value.func, "id", "")
                == "_reparar_contornos_degenerados"), None)
    _linha = ("".join(_linhas[_no.lineno - 1:_no.end_lineno])
              if _no is not None else "")
    _isca = fonte.replace(_linha, "", 1) if _linha else fonte
    _isca = _isca.replace("        _laudo_dec = None\n",
                          "        _laudo_dec = None\n" + _linha, 1)
    checar("  (isca) o reparo movido para DEPOIS do laco e acusado",
           _isca != fonte and not _reparo_vem_antes_da_formatacao(_isca))
    checar("o GUARDA: diz que o contorno degenerado se repara, nunca se "
           "descarta", any("GUARDA:" in l and "REPARA" in l
                           for l in fonte.splitlines()))


def _grupo_recusa_a_fina(fonte):
    import ast
    arv = ast.parse(fonte)
    fn = next((n for n in ast.walk(arv) if isinstance(n, ast.FunctionDef)
               and n.name == "suavizar_em_grupos"), None)
    if fn is None:
        return False
    mede = any(isinstance(no, ast.Call)
               and getattr(no.func, "id", None) == "estrutura_fina"
               and no.args and isinstance(no.args[0], ast.Subscript)
               and getattr(no.args[0].value, "id", None) == "grupo"
               for no in ast.walk(fn))
    zera = False
    for no in ast.walk(fn):
        if (isinstance(no, ast.If) and isinstance(no.test, ast.Name)
                and no.test.id == "_fina"):
            for sub in ast.walk(no):
                if (isinstance(sub, ast.Assign)
                        and any(isinstance(t, ast.Subscript)
                                and getattr(t.value, "id", None) == "porcada"
                                for t in sub.targets)
                        and isinstance(sub.value, ast.Constant)
                        and sub.value.value == 0.0):
                    zera = True
    return mede and zera


def _reparo_vem_antes_da_formatacao(fonte):
    import ast
    arv = ast.parse(fonte)
    fn = next((n for n in ast.walk(arv) if isinstance(n, ast.FunctionDef)
               and n.name == "build_rtstruct"), None)
    if fn is None:
        return False
    reparo, depois = [], []
    for no in ast.walk(fn):
        if isinstance(no, ast.Call):
            nome = getattr(no.func, "id", None) or getattr(no.func, "attr",
                                                           None)
            if nome == "_reparar_contornos_degenerados":
                reparo.append(no.lineno)
            elif nome == "_suavizar_contornos":
                depois.append(no.lineno)
        elif isinstance(no, ast.Assign):
            for alvo in no.targets:
                if isinstance(alvo, ast.Attribute) and \
                        alvo.attr == "ContourData":
                    depois.append(no.lineno)
    return bool(reparo and depois) and max(reparo) < min(depois)


def teste_cor_separa_os_dois_modelos():
    for orgao in ("spinal_cord", "lung_left", "heart", "liver"):
        nosso = M._color(orgao, False)
        nv = M._color(orgao, True)
        checar("%s: as duas versoes tem cores diferentes" % orgao,
               nosso != nv, "%s vs %s" % (nosso, nv))
        checar("%s: o nosso e escuro e o do VISTA e claro" % orgao,
               sum(nv) > sum(nosso), "%s vs %s" % (nosso, nv))
        folga = 765 - sum(nosso)
        dif = sum(nv) - sum(nosso)
        checar("%s: a diferenca usa a folga disponivel" % orgao,
               folga <= 0 or dif >= 0.60 * folga,
               "%s vs %s (dif %d de %d de folga)" % (nosso, nv, dif, folga))
        checar("%s: o nosso nao e claro demais para se ver no CT" % orgao,
               max(nosso) >= 90, str(nosso))
        checar("%s: componentes validos 0-255" % orgao,
               all(0 <= v <= 255 for v in nv + nosso), str(nv + nosso))

    checar("orgao sem cor propria tambem se separa",
           M._color("xpto_qualquer", False) != M._color("xpto_qualquer", True))
    checar("o matiz sai da chave CRUA, nao do nome ja truncado",
           M._color("thyroid_gland") != M._color("Glnd_Thyroid"),
           "%s vs %s" % (M._color("thyroid_gland"), M._color("Glnd_Thyroid")))
    checar("e a chave crua cai na cor NOMEADA da tireoide",
           M._color("thyroid_gland") == [int(round(v * M._ESCURO))
                                         for v in M._CORES["thyroid_gland"]],
           str(M._color("thyroid_gland")))
    checar("a regra 'escuro = nosso' vale para toda a paleta",
           all(sum(M._color(k, False)) < sum(M._color(k, True))
               for k in M._CORES))


def teste_desempate_nao_estraga_o_sufixo():
    usados = set()
    saida = [M.nome_clinico("submandibular_gland_left", usados,
                            sufixo=M.SUFIXO_NV) for _ in range(4)]
    checar("quatro colisoes geram quatro nomes", len(set(saida)) == 4, str(saida))
    checar("e TODOS terminam em _v3D",
           all(n.endswith(M.SUFIXO_NV) for n in saida), str(saida))
    checar("nenhum termina em digito depois do sufixo",
           not any(n.endswith(M.SUFIXO_NV + d) for n in saida
                   for d in "0123456789"), str(saida))
    checar("e o lado sobrevive em todos",
           all("_L" in n for n in saida), str(saida))


def teste_task_que_nao_alimenta_o_entregue():
    checar("total alimenta o entregue", M.alimenta_o_entregue("total"))
    checar("head_glands_cavities tambem", M.alimenta_o_entregue("head_glands_cavities"))
    checar("headneck_muscles tambem", M.alimenta_o_entregue("headneck_muscles"))
    checar("lung_vessels NAO alimenta — ela vai para o _tx",
           not M.alimenta_o_entregue("lung_vessels"))
    checar("task inexistente tambem nao", not M.alimenta_o_entregue("nao_existe"))

    fonte = open(os.path.join(pasta_app(AQUI), "engine.py"), encoding="utf-8").read()
    corpo = re.split(r"\n(?=\S)", fonte.split("def alimenta_o_entregue(")[1])[0]
    checar("e a resposta sai do proprio TS_MAP", "TS_MAP" in corpo)
    checar("sem lista de excecoes por nome",
           "lung_vessels" not in corpo.split('"""')[-1], corpo[-90:])


def teste_masks_da_task():
    forma = (8, 16, 16)
    arr = np.zeros(forma, dtype=np.int16)
    idx_to_name = {1: "lung_upper_lobe_left", 2: "lung_lower_lobe_left",
                   3: "heart", 4: "liver", 5: "rib_left_1", 6: "rib_left_2"}
    arr[0:2] = 1
    arr[2:4] = 2
    arr[4:5] = 3
    arr[5:6] = 5
    arr[6:7] = 6

    masks = M.masks_da_task(arr, "total", idx_to_name)

    checar("o lobo superior esquerdo sai sozinho", "lung_upper_lobe_left" in masks)
    checar("e com o volume dele", "lung_upper_lobe_left" in masks and
           int(masks["lung_upper_lobe_left"].sum()) == int((arr == 1).sum()))
    checar("o lobo inferior esquerdo tambem", "lung_lower_lobe_left" in masks)

    checar("lung_left continua existindo, como composto", "lung_left" in masks)
    checar("e e exatamente a uniao dos dois lobos",
           int(masks["lung_left"].sum()) == int((arr == 1).sum() + (arr == 2).sum()),
           "%d voxels" % int(masks.get("lung_left", np.zeros(1)).sum()))
    checar("compor nao esvaziou as partes",
           int(masks["lung_upper_lobe_left"].sum()) > 0 and
           int(masks["lung_lower_lobe_left"].sum()) > 0)

    checar("merge une costelas em ribs_left",
           "ribs_left" in masks and
           int(masks["ribs_left"].sum()) == int((arr == 5).sum() + (arr == 6).sum()))
    checar("estrutura simples passa direto", "heart" in masks)
    checar("estrutura ausente do volume nao aparece", "liver" not in masks)

    declarados = set(M.TS_MAP) | set(getattr(M, "COMPOSTOS", {}))
    vazados = sorted(k for k in masks if k not in declarados)
    checar("sub-rotulo cru NUNCA vaza para a saida", not vazados, ", ".join(vazados))
    checar("a costela individual EXISTE no dado",
           any(k.startswith("rib_left_") for k in masks),
           ", ".join(sorted(masks.keys())))
    oar = M.para_oar(masks)
    checar("mas NAO entra no AI_OAR (o composto leva)",
           not any(k.startswith("rib_left_") for k in oar)
           and "ribs_left" in oar, ", ".join(sorted(oar)))
    checar("e o AI_completo, que sai de `cruas`, continua com ela",
           any(k.startswith("rib_left_") for k in masks))
    checar("toda saida esta no TS_MAP ou e composta declarada",
           all(k in declarados for k in masks), ", ".join(sorted(masks.keys())))


def teste_nenhum_campo_estoura_o_limite_do_VR():
    import pydicom
    from pydicom.valuerep import MAX_VALUE_LEN
    tmp = tempfile.mkdtemp(prefix="radai_teste_")
    try:
        serie = os.path.join(tmp, "serie")
        escreve_serie(serie, "FANTOMA_VR", datetime(2026, 3, 15, 10, 30), 8)
        forma = (8, 64, 64)
        zz, yy, xx = np.ogrid[0:forma[0], 0:forma[1], 0:forma[2]]
        masks = {"heart": ((zz - 4) ** 2 + (yy - 32) ** 2 + (xx - 32) ** 2) <= 100}

        import radai_sets as CJ
        rotulos = [None] + ["STUDY_" + c["cod"] for c in CJ.CONJUNTOS
                            if c["cod"] != "oar"]
        try:
            import radai_hnlnl as _hn
            rotulos.append(_hn.ROTULO_TPS)
        except Exception:
            pass

        estouros = []
        for rot in rotulos:
            caminho, _ = M.build_rtstruct(serie, masks, tasks=["total"],
                                          versao_worker="teste", rotulo=rot)
            ds = pydicom.dcmread(caminho)
            for el in ds:
                teto = MAX_VALUE_LEN.get(el.VR)
                if not teto or el.value in (None, ""):
                    continue
                vals = el.value if isinstance(el.value, (list, tuple)) else [el.value]
                for v in vals:
                    if isinstance(v, str) and len(v) > teto:
                        estouros.append(u"%s (%s, %d > %d) em rotulo=%s"
                                        % (el.keyword or el.tag, el.VR,
                                           len(v), teto, rot))
        checar(u"nenhum campo passa do teto do proprio VR",
               not estouros, u"; ".join(estouros[:4]))
        checar(u"  e a checagem sabe reprovar (isca)",
               len("x" * 65) > MAX_VALUE_LEN["LO"])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def teste_marco_interno_nao_vira_estrutura():
    import pydicom
    tmp = tempfile.mkdtemp(prefix="radai_teste_")
    try:
        m = {M.NOME_JUNCAO_SI: np.ones((4, 4, 4), bool),
             "heart": np.ones((4, 4, 4), bool)}
        M.aplicar_derivadas(m, None)
        checar("aplicar_derivadas devolve o dicionario SEM o marco interno",
               M.NOME_JUNCAO_SI not in m, sorted(m))
        checar("  e sem tocar no resto", "heart" in m)

        serie = os.path.join(tmp, "serie")
        escreve_serie(serie, "FANTOMA_JSI", datetime(2026, 3, 15, 10, 30), 24)
        forma = (24, 128, 128)
        zz, yy, xx = np.ogrid[0:forma[0], 0:forma[1], 0:forma[2]]
        bola = (((zz - 12) * 3.0) ** 2 + ((yy - 64) * 2.0) ** 2
                + ((xx - 64) * 2.0) ** 2 <= 25.0 ** 2)
        masks = {"heart": bola, M.NOME_JUNCAO_SI: bola.copy()}
        caminho, _nomes = M.build_rtstruct(serie, masks, tasks=["total"],
                                           versao_worker="t")
        rois = [str(r.ROIName) for r in
                pydicom.dcmread(caminho).StructureSetROISequence]
        checar("o RTSTRUCT nao leva nome com `_` na frente",
               not any(r.startswith("_") for r in rois), ", ".join(rois))
        checar("  e leva o resto", "Heart_ai" in rois, ", ".join(rois))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def teste_build_rtstruct():
    import pydicom
    tmp = tempfile.mkdtemp(prefix="radai_teste_")
    try:
        serie = os.path.join(tmp, "serie")
        escreve_serie(serie, "FANTOMA_01", datetime(2026, 3, 15, 10, 30), 24)
        n = len([f for f in os.listdir(serie) if f.endswith(".dcm")])
        checar("serie sintetica criada", n == 24, "%d cortes" % n)

        forma = (24, 128, 128)
        zz, yy, xx = np.ogrid[0:forma[0], 0:forma[1], 0:forma[2]]
        def bola(cz, cy, cx, r):
            return ((zz - cz) * 3.0) ** 2 + ((yy - cy) * 2.0) ** 2 + ((xx - cx) * 2.0) ** 2 <= r * r
        masks = {"heart": bola(12, 64, 64, 25.0),
                 "lung_left": bola(12, 64, 40, 20.0),
                 "submandibular_gland_left": bola(6, 40, 80, 12.0)}

        caminho, nomes = M.build_rtstruct(serie, masks, tasks=["total"], versao_worker="2.0")
        checar("RTSTRUCT gerado", os.path.exists(caminho))
        checar("build_rtstruct devolve o mapa de nomes", len(nomes) == 3, str(nomes))

        ds = pydicom.dcmread(caminho)
        checar("modalidade RTSTRUCT", ds.Modality == "RTSTRUCT")
        checar("ApprovalStatus = UNAPPROVED",
               getattr(ds, "ApprovalStatus", None) == "UNAPPROVED",
               str(getattr(ds, "ApprovalStatus", "AUSENTE")))
        legiveis = " ".join(str(getattr(ds, c, "")) for c in
                            ("StructureSetLabel", "StructureSetName",
                             "StructureSetDescription", "SeriesDescription"))
        checar("o entregue diz em texto que e sugestao nao aprovada",
               "sugestao" in legiveis.lower() and
               "nao aprovada" in legiveis.lower(), legiveis[:120])
        checar("e o rotulo nao afirma o contrario",
               not any(x in str(ds.StructureSetLabel).lower()
                       for x in ("aprovad", "revisad", "final", "definitiv")),
               str(ds.StructureSetLabel))
        checar("StructureSetLabel cabe em SH (16)", len(str(ds.StructureSetLabel)) <= 16)
        checar("descricao diz NAO APROVADA",
               "NAO APROVADA" in str(getattr(ds, "StructureSetDescription", "")).upper())
        checar("SeriesDescription avisa no import",
               "NAO APROVADA" in str(getattr(ds, "SeriesDescription", "")).upper(),
               str(getattr(ds, "SeriesDescription", "")))

        rois = [str(r.ROIName) for r in ds.StructureSetROISequence]
        checar("todas as ROIs levam o sufixo _ai", all(r.endswith("_ai") for r in rois),
               ", ".join(rois))
        checar("nome TG-263 no RTSTRUCT", "Heart_ai" in rois, ", ".join(rois))
        checar("lateralidade preservada", any("_L_ai" in r for r in rois), ", ".join(rois))
        checar("nenhum nome cru do TotalSegmentator no arquivo",
               not any(r.startswith("heart") or r.startswith("lung_") for r in rois),
               ", ".join(rois))
        checar("ROIGenerationAlgorithm = AUTOMATIC",
               all(str(getattr(r, "ROIGenerationAlgorithm", "")) == "AUTOMATIC"
                   for r in ds.StructureSetROISequence))
        checar("ha contornos de verdade",
               all(len(getattr(rc, "ContourSequence", [])) > 0 for rc in ds.ROIContourSequence),
               "%d ROIs" % len(ds.ROIContourSequence))

        ref = pydicom.dcmread(os.path.join(serie, sorted(os.listdir(serie))[0]),
                              stop_before_pixels=True)
        checar("StudyInstanceUID herdado da serie",
               ds.StudyInstanceUID == ref.StudyInstanceUID)
        checar("FrameOfReferenceUID herdado da serie",
               ds.FrameOfReferenceUID == ref.FrameOfReferenceUID)
        checar("PatientID herdado (import casa com a serie)",
               str(ds.PatientID) == str(ref.PatientID))
        checar("SeriesInstanceUID e proprio (nao colide com a CT)",
               ds.SeriesInstanceUID != ref.SeriesInstanceUID)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def teste_falha_do_ts_levanta():
    import SimpleITK as sitk
    vol = sitk.GetImageFromArray(np.zeros((8, 16, 16), dtype=np.int16))
    vol.SetSpacing((2.0, 2.0, 3.0))
    jid = M._job_new()
    t0 = datetime.now()
    try:
        M.run_ts_task(vol, "total", device="cpu", jid=jid, timeout_s=5)
        checar("task que falha LEVANTA excecao", False, "retornou sem erro")
    except RuntimeError as e:
        checar("task que falha LEVANTA excecao (nao devolve {})", True)
        checar("a mensagem diz qual task falhou", "total" in str(e), str(e)[:90])
        checar("a mensagem traz o diagnostico (codigo de saida ou tempo limite)",
               len(str(e)) > 40, str(e)[:90])
    except Exception as e:
        checar("task que falha levanta RuntimeError", False,
               "%s: %s" % (type(e).__name__, e))
    dt = (datetime.now() - t0).total_seconds()
    checar("nao ficou preso no subprocesso", dt < 90, "%.1fs" % dt)

    M._job_del(jid)
    checar("_job_del limpa o job (sem vazamento em execucao longa)",
           M._job(jid) == {})


def teste_constritores_da_faringe_sao_entrega_obrigatoria():
    print(u"\n-- cabeca e pescoco: os constritores da faringe --")
    engine = M

    CHAVES = ("pharyngeal_constrictor_superior",
              "pharyngeal_constrictor_middle",
              "pharyngeal_constrictor_inferior")

    for k in CHAVES:
        checar(u"%s esta no TS_MAP" % k, k in engine.TS_MAP)
        if k in engine.TS_MAP:
            checar(u"  e vem da headneck_muscles",
                   "headneck_muscles" in engine.TS_MAP[k],
                   str(list(engine.TS_MAP[k].keys())))

    import os
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    vig = open(_componentes.fonte("app/radai_watcher.py"),
                  encoding="utf-8").read()
    import radai_topography as _tp
    checar(u"headneck_muscles NAO roda por padrao (o vigia nao le TASKS do "
           u"config desde a v8.4: roda a base e a anatomia)",
           re.search(r"(?m)^TASKS=", vig) is None
           and "TASKS = [base_do_vigia()]" in vig)
    checar(u"  e e alcancavel pelo protocolo de cabeca e pescoco",
           "headneck_muscles" in _tp.TASKS_DO_PESCOCO)
    checar(u"  e o protocolo a acrescenta de verdade",
           "headneck_muscles" in _tp.tasks_de(
               [_tp.CABECA_PESCOCO], ("total",)))
    cfg = os.path.join(raiz, "build", "configurar_ambiente.py")
    if os.path.exists(cfg):
        import importlib
        import sys as _sys
        _b = os.path.join(raiz, "build")
        if _b not in _sys.path:
            _sys.path.insert(0, _b)
        try:
            _ca = importlib.import_module("configurar_ambiente")
            _tasks = set(getattr(_ca, "TASKS", ()))
            erro = ""
        except Exception as e:
            _tasks, erro = set(), "%s: %s" % (type(e).__name__, e)
        checar(u"e nos pesos que o pacote baixa",
               "headneck_muscles" in _tasks,
               erro or (u"%d tasks no preparador" % len(_tasks)))

    usados = set()
    nomes = []
    for k in CHAVES:
        n = engine.nome_clinico(k, usados)
        usados.add(n)
        nomes.append(n)
        checar(u"%s cabe em 16 caracteres" % n, len(n) <= 16, str(len(n)))
        checar(u"  e mantem o sufixo _ai", n.endswith("_ai"), n)
    checar(u"os tres nomes sao distintos", len(set(nomes)) == 3,
           u", ".join(nomes))
    for n, lado in zip(nomes, ("_S", "_M", "_I")):
        checar(u"%s preserva o lado %s" % (n, lado), lado in n, n)


def teste_cavidades_e_derrame():
    print(u"\n-- torax: cavidades (anatomia) e derrame (achado) --")
    engine = M

    for chave, task in (("pericardium", "trunk_cavities"),
                        ("mediastinum", "trunk_cavities"),
                        ("thoracic_cavity", "trunk_cavities"),
                        ("abdominal_cavity", "trunk_cavities")):
        checar(u"%s esta no TS_MAP" % chave, chave in engine.TS_MAP)
        if chave in engine.TS_MAP:
            checar(u"  e vem da %s" % task, task in engine.TS_MAP[chave],
                   str(list(engine.TS_MAP[chave].keys())))
        n = engine.nome_clinico(chave, set())
        checar(u"  %s cabe em 16 e mantem o _ai" % n,
               len(n) <= 16 and n.endswith("_ai"), u"%s (%d)" % (n, len(n)))

    import os
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    vig = open(_componentes.fonte("app/radai_watcher.py"),
               encoding="utf-8").read()
    import re
    import radai_modes as _MD0
    padrao = ([_MD0.base_de("CT")]
              if (re.search(r"(?m)^TASKS=", vig) is None
                  and "TASKS = [base_do_vigia()]" in vig) else [])
    checar(u"as TASKS padrao sao `total_v3`, e so ela",
           padrao == ["total_v3"], u" ".join(padrao))
    checar(u"  e a `total_v2` NAO roda por padrao",
           "total_v2" not in padrao,
           u"ela e a rede de seguranca, eleita em execucao")
    for t in ("trunk_cavities", "head_glands_cavities", "headneck_muscles",
              "headneck_bones_vessels", "head_muscles", "lung_vessels"):
        checar(u"%s NAO roda por padrao" % t, t not in padrao)

    import radai_tasks as _T
    import radai_modes as _MD
    achados = sorted(engine.TASKS_DE_ACHADO)
    checar(u"engine declara as tasks de ACHADO", bool(achados),
           u", ".join(achados))
    for _t in ("lung_nodules",):
        checar(u"  `%s` esta declarada como achado" % _t, _t in achados)
    checar(u"  e o derrame NAO e achado (v8.4: anatomia do torax, Q2)",
           "pleural_pericard_effusion" not in achados)
    checar(u"  e `cerebral_bleed` NAO esta mais declarada",
           "cerebral_bleed" not in achados,
           u"ela saiu do aplicativo; tabela apontando para o que nao existe")
    checar(u"  e todo achado declarado esta entre as PERMITIDAS",
           achados <= sorted(M.TASKS_PERMITIDAS) or
           set(achados) <= set(M.TASKS_PERMITIDAS),
           u", ".join(sorted(set(achados) - set(M.TASKS_PERMITIDAS))))
    for t in achados:
        checar(u"%s: fora do TASKS= do DEFAULT_CFG" % t, t not in padrao)
        checar(u"  e fora de radai_tasks.PADRAO", t not in _T.PADRAO,
               u" ".join(_T.PADRAO))
    for _mod in ("CT", "MR"):
        for reg in _MD.TOPOGRAFIAS:
            saiu = _MD.tasks_da_topografia(
                [reg], _mod, permitidas=engine.TASKS_PERMITIDAS,
                achados=engine.TASKS_DE_ACHADO)
            intrusas = sorted(set(saiu) & engine.TASKS_DE_ACHADO)
            checar(u"a lista da anatomia (%s) em %s nao monta achado"
                   % (_mod, reg),
                   not intrusas, u", ".join(intrusas) or u" ".join(saiu))

    checar(u"a task do derrame E permitida (regra B)",
           "pleural_pericard_effusion" in engine.TASKS_PERMITIDAS)
    checar(u"e NAO esta declarada como ACHADO (v8.4)",
           "pleural_pericard_effusion" not in engine.TASKS_DE_ACHADO)
    checar(u"e NAO esta em TASKS_FORA_DE_ESCOPO (ela saiu de recusada)",
           "pleural_pericard_effusion" not in engine.TASKS_FORA_DE_ESCOPO,
           str(sorted(engine.TASKS_FORA_DE_ESCOPO)))
    checar(u"nenhuma task de achado sobrou em TASKS_FORA_DE_ESCOPO",
           not (set(engine.TASKS_FORA_DE_ESCOPO) & engine.TASKS_DE_ACHADO))

    checar(u"os dois rotulos de derrame estao no TS_MAP (v8.4: FULL e OAR)",
           sorted(n for n in engine.TS_MAP if "effusion" in n)
           == ["pericardial_effusion", "pleural_effusion"],
           str([n for n in engine.TS_MAP if "effusion" in n]))
    checar(u"e `alimenta_o_entregue` diz isso ao run_ts_task",
           engine.alimenta_o_entregue("pleural_pericard_effusion"))

    checar(u"SO_COMPARACAO existe", hasattr(engine, "SO_COMPARACAO"))
    checar(u"e esta VAZIA -- nenhuma estrutura recortada hoje",
           len(engine.SO_COMPARACAO) == 0, str(sorted(engine.SO_COMPARACAO)))
    import ast as _ast
    fonte = open(_componentes.fonte("app/engine.py"), encoding="utf-8").read()
    usa = False
    for no in _ast.walk(_ast.parse(fonte)):
        if not (isinstance(no, _ast.FunctionDef) and no.name == "build_rtstruct"):
            continue
        for sub in _ast.walk(no):
            if (isinstance(sub, _ast.Compare)
                    and any(isinstance(o, _ast.In) for o in sub.ops)
                    and any(isinstance(c, _ast.Name) and c.id == "SO_COMPARACAO"
                            for c in sub.comparators)):
                usa = True
    checar(u"build_rtstruct testa `in SO_COMPARACAO` (AST, nao substring)", usa)

    checar(u"o pericardio nao esta barrado (e anatomia, nao achado)",
           "pericardium" not in engine.SO_COMPARACAO)


def teste_so_comparacao_recorta_o_entregue_e_nao_o_cru():
    import pydicom
    print(u"\n-- SO_COMPARACAO: recorta o entregue, e nao o cru --")

    tmp = tempfile.mkdtemp(prefix="radai_teste_")
    original = M.SO_COMPARACAO
    try:
        serie = os.path.join(tmp, "serie")
        escreve_serie(serie, "FANTOMA_SC", datetime(2026, 9, 13, 8, 0), 24)

        forma = (24, 128, 128)
        zz, yy, xx = np.ogrid[0:forma[0], 0:forma[1], 0:forma[2]]

        def bola(cz, cy, cx, r):
            return (((zz - cz) * 3.0) ** 2 + ((yy - cy) * 2.0) ** 2
                    + ((xx - cx) * 2.0) ** 2) <= r * r

        masks = {"kidney_left": bola(12, 60, 44, 18.0),
                 "kidney_right": bola(12, 60, 84, 18.0)}
        for k, v in masks.items():
            checar(u"o fantoma %s tem massa" % k, int(v.sum()) > 200,
                   u"%d voxels" % int(v.sum()))

        def rois(**kw):
            caminho, _ = M.build_rtstruct(serie, dict(masks), tasks=["total"],
                                          versao_worker="teste", **kw)
            ds = pydicom.dcmread(caminho)
            fora = [str(r.ROIName) for r in ds.StructureSetROISequence]
            shutil.rmtree(os.path.dirname(caminho), ignore_errors=True)
            return fora

        M.SO_COMPARACAO = frozenset()
        antes = rois()
        rim_e = [r for r in antes if r.startswith("Kidney") and "_L" in r]
        checar(u"com a lista vazia, o rim esquerdo SAI no entregue",
               bool(rim_e), u", ".join(antes))

        M.SO_COMPARACAO = frozenset(["kidney_left"])
        depois = rois()
        checar(u"injetado em SO_COMPARACAO, ele nao sai mais",
               not [r for r in depois if r.startswith("Kidney") and "_L" in r],
               u", ".join(depois))
        checar(u"e o rim DIREITO continua saindo (a trava e por nome)",
               [r for r in depois if r.startswith("Kidney") and "_R" in r],
               u", ".join(depois))

        cru = rois(origem={"kidney_left": "ts", "kidney_right": "ts"})
        checar(u"pela procedencia `ts`, o mesmo rim SAI (sufixo _ts)",
               [r for r in cru if r.startswith("Kidney") and "_L" in r],
               u", ".join(cru))
    finally:
        M.SO_COMPARACAO = original
        shutil.rmtree(tmp, ignore_errors=True)
    checar(u"SO_COMPARACAO foi restaurada ao sair",
           M.SO_COMPARACAO is original, str(sorted(M.SO_COMPARACAO)))


def teste_estrutura_vazia_nao_entra():
    pass
def teste_o_conjunto_cru_nao_recebe_nada_nosso():
    print(u"\n-- o conjunto cru nao recebe nada nosso --")
    import radai_sets
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    checar(u"o `_ts` esta declarado CRU no registro",
           bool(radai_sets.POR_COD["ts"].get("cru")))
    outros = [c["cod"] for c in radai_sets.CONJUNTOS
              if c["cod"] != "ts" and c.get("cru")]
    checar(u"e ele e o unico", not outros, str(outros))

    fonte_out = open(_componentes.fonte("app/radai_output.py"),
                     encoding="utf-8").read()
    checar(u"e `radai_output` o repassa ao motor",
           "cru=bool(reg.get(" in fonte_out)

    base = tempfile.mkdtemp()
    serie = os.path.join(base, "s")
    escreve_serie(serie, "PAC_CRU", datetime.now(), 12)
    forma = (12, 64, 64)
    rim = np.zeros(forma, bool)
    rim[3:9, 20:44, 20:44] = True
    cisto = np.zeros(forma, bool)
    cisto[4:8, 26:34, 26:34] = True
    dentro = int((cisto & rim).sum())
    checar(u"o fantoma tem cisto DENTRO do rim", dentro > 0, str(dentro))

    def roda(cru):
        linhas = []
        M.build_rtstruct(serie, {"kidney_left": rim.copy(),
                                 "kidney_cyst_left": cisto.copy()},
                         tasks=["total"], versao_worker="teste",
                         log=lambda t: linhas.append(str(t)), cru=cru,
                         descontar=True)
        return u" | ".join(linhas)

    log_nosso = roda(False)
    log_cru = roda(True)
    checar(u"no conjunto NOSSO o rim e descontado do cisto",
           "descontado" in log_nosso, log_nosso[-160:] or u"(log vazio)")
    checar(u"e no CRU nao ha desconto nenhum, mesmo pedindo",
           "descontado" not in log_cru, log_cru[-160:] or u"(log vazio)")

    fonte = open(_componentes.fonte("app/engine.py"),
                 encoding="utf-8").read()
    corpo = fonte[fonte.index("def build_rtstruct("):]
    corpo = corpo[:corpo.index("aplicar_contencao(masks")]
    checar(u"o portao e o `cru`, e nao a suavizacao",
           "and not cru" in corpo,
           corpo[-200:].replace("\n", " ")[:160])


    print(u"\n-- so entra estrutura COM contorno --")
    import pydicom
    base = tempfile.mkdtemp()
    serie = os.path.join(base, "s")
    escreve_serie(serie, "PAC_V", datetime.now(), 12)
    forma = (12, 64, 64)

    cheia = np.zeros(forma, bool)
    cheia[4:8, 20:40, 20:40] = True
    vazia = np.zeros(forma, bool)
    ruido = np.zeros(forma, bool)
    ruido[0, 0, 0:5] = True

    rs, mapa = M.build_rtstruct(
        serie, {"heart": cheia,
                "pharyngeal_constrictor_superior": vazia,
                "pericardium": ruido},
        tasks=["total"], versao_worker="teste")

    checar(u"a estrutura vazia nao recebe nem nome", "Heart_ai" in mapa.values()
           and len(mapa) == 1, str(sorted(mapa.values())))

    ds = pydicom.dcmread(str(rs))
    nomes = set(r.ROIName for r in ds.StructureSetROISequence)
    por_num = dict((r.ROINumber, r.ROIName) for r in ds.StructureSetROISequence)
    com_contorno = set()
    for c in getattr(ds, "ROIContourSequence", []):
        if getattr(c, "ContourSequence", None):
            com_contorno.add(por_num.get(c.ReferencedROINumber))

    checar(u"a estrutura cheia entrou", "Heart_ai" in nomes, str(sorted(nomes)))
    checar(u"a VAZIA nao entrou",
           not any(n.startswith("Musc_Constr") for n in nomes),
           str(sorted(nomes)))
    checar(u"e o ruido de 5 voxels tambem nao",
           not any(n.startswith("Pericardium") for n in nomes),
           str(sorted(nomes)))
    checar(u"nenhuma ROI declarada sem contorno no arquivo",
           not (nomes - com_contorno), str(sorted(nomes - com_contorno)))


def teste_sem_desconto_o_grupo_disjunto_nao_recorta_o_orgao():
    import numpy as np
    import radai_geom
    forma = (40, 96, 96)
    grade = radai_geom.Grade((3.0, 1.0, 1.0))

    def fantoma():
        rim = np.zeros(forma, bool)
        rim[10:30, 30:70, 30:70] = True
        cisto = np.zeros(forma, bool)
        cisto[16:24, 44:56, 44:56] = True
        return rim, cisto

    rim0, cisto0 = fantoma()
    dentro = int((cisto0 & rim0).sum())
    checar(u"o fantoma tem o cisto INTEIRO dentro do rim",
           dentro == int(cisto0.sum()) and dentro > 0,
           u"%d de %d" % (dentro, int(cisto0.sum())))

    rim, cisto = fantoma()
    m = {"kidney_left": rim, "kidney_cyst_left": cisto}
    M.suavizar_em_grupos(m, grade, 1.5, descontou=False)
    sobrou = int((np.asarray(m["kidney_left"]) & cisto0).sum())
    checar(u"sem desconto, o rim do `_full` NAO perde o cisto",
           sobrou >= dentro * 0.9, u"cobre %d dos %d voxels" % (sobrou, dentro))

    rim, cisto = fantoma()
    m2 = {"kidney_left": rim, "kidney_cyst_left": cisto}
    M.aplicar_desconto(m2, grade)
    vazado = int((np.asarray(m2["kidney_left"]) & cisto0).sum())
    antes = int(np.asarray(m2["kidney_left"]).sum())
    M.suavizar_em_grupos(m2, grade, 1.5, descontou=True)
    checar(u"com desconto, o rim ja nao contem o cisto ao entrar no grupo",
           vazado == 0, u"%d voxel(s) sobraram" % vazado)
    checar(u"e o grupo disjunto continua negociando a fronteira",
           antes > 0 and int(np.asarray(m2["kidney_left"]).sum()) > 0)

    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    fonte = open(_componentes.fonte("app/engine.py"),
                 encoding="utf-8").read()
    corpo = fonte.split("def suavizar_em_grupos", 1)[1].split("for rotulo,", 1)[0]
    checar(u"a excecao deriva de `DESCONTADAS_DE`, nao de lista escrita a mao",
           "set(DESCONTADAS_DE)" in corpo, corpo[-200:])


def teste_o_desconto_do_cisto_e_do_OAR_e_nao_do_orgao():
    import numpy as np
    import radai_sets

    oar = radai_sets.POR_COD["oar"]
    full = radai_sets.POR_COD["full"]
    checar(u"o `oar` declara que desconta", bool(oar.get("desconta")),
           repr(oar.get("desconta")))
    checar(u"e o `full` tambem (Q6: rim descontado + cisto no FULL)",
           bool(full.get("desconta")), repr(full.get("desconta")))
    fast = radai_sets.POR_COD.get("fast") or {}
    checar(u"e o `fast` (o RadAI_OAR_Fast) tambem, como o OAR de que ele sai",
           bool(fast.get("desconta")) and bool(fast.get("entregue")),
           repr(fast))
    for cod, reg in radai_sets.POR_COD.items():
        if cod in ("oar", "full", "fast"):
            continue
        checar(u"   nenhum outro desconta: %s" % cod,
               not reg.get("desconta"), repr(reg.get("desconta")))

    base = tempfile.mkdtemp()
    serie = os.path.join(base, "s")
    escreve_serie(serie, "PAC_CISTO", datetime.now(), 12)
    forma = (12, 64, 64)
    rim = np.zeros(forma, bool)
    rim[3:9, 20:44, 20:44] = True
    cisto = np.zeros(forma, bool)
    cisto[4:8, 26:34, 26:34] = True
    checar(u"o fantoma tem cisto DENTRO do rim",
           int((cisto & rim).sum()) > 0)

    def roda(descontar):
        linhas = []
        M.build_rtstruct(serie, {"kidney_left": rim.copy(),
                                 "kidney_cyst_left": cisto.copy()},
                         tasks=["total"], versao_worker="teste",
                         log=lambda t: linhas.append(str(t)),
                         cru=False, descontar=descontar)
        return u" | ".join(linhas)

    log_oar = roda(True)
    log_full = roda(False)
    checar(u"com `descontar` o rim perde o cisto",
           "descontado" in log_oar, log_oar[-160:] or u"(log vazio)")
    checar(u"SEM `descontar` o orgao sai inteiro",
           "descontado" not in log_full, log_full[-160:] or u"(log vazio)")

    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    fonte_out = open(_componentes.fonte("app/radai_output.py"),
                     encoding="utf-8").read()
    checar(u"e `radai_output` repassa a chave ao motor",
           "descontar=bool(reg.get(" in fonte_out)


def _grade_pelve():
    import radai_geom
    return radai_geom.Grade((2.0, 1.0, 1.0))


def _fantoma_pelve(sem=()):
    Z, Y, X = 100, 60, 60

    def caixa(z0, z1, y0, y1, x0, x1):
        m = np.zeros((Z, Y, X), dtype=bool)
        m[z0:z1, y0:y1, x0:x1] = True
        return m

    m = {"colon": caixa(10, 91, 28, 34, 28, 34),
         "hip_left": caixa(20, 60, 20, 26, 10, 20),
         "hip_right": caixa(20, 60, 20, 26, 40, 50),
         "sacrum": caixa(35, 71, 18, 28, 19, 41),
         "vertebrae_S1": caixa(46, 58, 38, 52, 22, 42)}
    for k in sem:
        m.pop(k, None)
    return m


def teste_pisos_de_volume_vieram_do_artigo():
    for nome, esperado in ((u"esophagus", 20.0), (u"trachea", 20.0),
                           (u"urinary_bladder", 40.0), (u"sacrum", 100.0),
                           (u"stomach", 70.0), (u"femur_left", 90.0),
                           (u"hip_right", 100.0), (u"colon", 100.0)):
        checar(u"piso de %s = %g cm3 (Tabela S1)" % (nome, esperado),
               M.VOLUME_MINIMO_CM3.get(nome) == esperado,
               str(M.VOLUME_MINIMO_CM3.get(nome)))
    checar(u"heart = a soma das cinco camaras do v1, e nao a maior",
           M.VOLUME_MINIMO_CM3.get("heart") == 300.0,
           str(M.VOLUME_MINIMO_CM3.get("heart")))
    checar(u"brain fica com o nosso 700, e nao com o 1 do artigo",
           M.VOLUME_MINIMO_CM3.get("brain") == 700.0,
           str(M.VOLUME_MINIMO_CM3.get("brain")))
    checar(u"sao mais de 50 estruturas com piso",
           len(M.VOLUME_MINIMO_CM3) >= 50, str(len(M.VOLUME_MINIMO_CM3)))


def teste_truncada_pelo_campo_nao_e_suspeita():
    import radai_geom
    grade = radai_geom.Grade((1.0, 1.0, 1.0))

    def caixa(z0, z1, y0, y1, x0, x1, forma=(40, 40, 40)):
        m = np.zeros(forma, dtype=bool)
        m[z0:z1, y0:y1, x0:x1] = True
        return m

    cortado = caixa(0, 20, 10, 30, 10, 30)
    inteiro = caixa(10, 30, 10, 30, 10, 30)
    checar(u"a mascara que encosta na face do volume e detectada",
           M.toca_a_borda(cortado) is True)
    checar(u"e a que nao encosta, nao",
           M.toca_a_borda(inteiro) is False)

    susp, trunc = M.implausiveis({"liver": cortado}, grade)
    checar(u"figado cortado pelo campo NAO entra em suspeitas",
           susp == [], str(susp))
    checar(u"ele entra na lista de truncadas, sem veredito",
           trunc == ["liver"], str(trunc))

    susp2, trunc2 = M.implausiveis({"liver": inteiro}, grade)
    checar(u"figado colapsado NO MEIO DO CAMPO continua sendo suspeita",
           len(susp2) == 1 and susp2[0][0] == "liver", str(susp2))
    checar(u"e nao aparece como truncado", trunc2 == [], str(trunc2))

    checar(u"nenhuma mascara foi alterada",
           int(cortado.sum()) == 20 * 20 * 20
           and int(inteiro.sum()) == 20 * 20 * 20)


def teste_ilha_distante_e_marcada_e_anatomia_nao():
    import radai_geom
    g = radai_geom.Grade((1.0, 1.0, 1.0))

    def vazio():
        return np.zeros((160, 80, 80), dtype=bool)

    orgao = vazio()
    orgao[60:90, 30:50, 30:50] = True
    com_ilha = orgao.copy()
    com_ilha[8:12, 38:42, 38:42] = True
    perto = orgao.copy()
    perto[92:96, 38:42, 38:42] = True

    carotidas = vazio()
    carotidas[40:120, 30:40, 20:26] = True
    carotidas[40:120, 30:40, 54:60] = True
    costelas = vazio()
    for i in range(12):
        costelas[20 + i * 10:26 + i * 10, 20:24, 10:60] = True

    r = M.componentes_distantes({"eye": com_ilha}, g)
    checar(u"a ilha pequena e longe e marcada", len(r) == 1, str(r))
    if r:
        checar(u"e o laudo diz a distancia e a fracao",
               r[0][2] > 40 and r[0][3] < 0.05,
               u"%.0f mm, %.3f do volume" % (r[0][2], r[0][3]))

    checar(u"orgao limpo nao e marcado",
           M.componentes_distantes({"eye": orgao}, g) == [])
    checar(u"pedaco pequeno mas PERTO nao e ilha (e borda picotada)",
           M.componentes_distantes({"eye": perto}, g) == [],
           str(M.componentes_distantes({"eye": perto}, g)))
    checar(u"carotidas (duas metades comparaveis) nao sao marcadas",
           M.componentes_distantes({"carotids": carotidas}, g) == [],
           str(M.componentes_distantes({"carotids": carotidas}, g)))
    checar(u"12 costelas nao sao marcadas",
           M.componentes_distantes({"ribs_left": costelas}, g) == [],
           str(M.componentes_distantes({"ribs_left": costelas}, g)))

    antes = int(com_ilha.sum())
    M.componentes_distantes({"eye": com_ilha}, g)
    checar(u"o guarda nao mexe na mascara", int(com_ilha.sum()) == antes)


def teste_classe_de_achado_do_nv_exige_ato_declarado():
    import radai_nv_engine as VM

    MAPA = {}
    for i, n in ((1, "liver"), (6, "aorta"), (11, "esophagus"),
                 (115, "heart"), (121, "spinal cord"), (132, "airway"),
                 (23, "lung tumor"), (24, "pancreatic tumor"),
                 (26, "hepatic tumor"), (27, "colon cancer primaries"),
                 (128, "bone lesion"), (116, "left kidney cyst"),
                 (117, "right kidney cyst"), (129, "kidney mass"),
                 (130, "liver tumor")):
        MAPA[n] = i
    IDS_DE_ACHADO = {23, 24, 26, 27, 128, 116, 117, 129, 130}

    checar(u"existe uma lista de classes PERMITIDAS (o que o codigo ACEITA)",
           isinstance(getattr(VM, "CLASSES_PERMITIDAS", None), frozenset)
           and len(VM.CLASSES_PERMITIDAS) > 0)
    checar(u"existe uma lista de classes DE ENTREGA (o que a rotina PEDE)",
           isinstance(getattr(VM, "CLASSES_DE_ENTREGA", None), frozenset)
           and len(VM.CLASSES_DE_ENTREGA) > 0)
    checar(u"a ENTREGA tem as 115 anatomicas do nv_segment_ct",
           len(VM.CLASSES_DE_ENTREGA) == 115, len(VM.CLASSES_DE_ENTREGA))
    checar(u"e as PERMITIDAS sao as 132 (115 + 9 de achado + 8 fora)",
           len(VM.CLASSES_PERMITIDAS) == 132, len(VM.CLASSES_PERMITIDAS))
    checar(u"e as tres listas nao se cruzam e somam 132",
           len(set(VM.CLASSES_DE_ENTREGA)) + len(set(VM.CLASSES_DE_ACHADO))
           + len(set(VM.CLASSES_FORA_DA_ENTREGA)) == 132)
    checar(u"sao DUAS listas, e nao a mesma com outro nome",
           VM.CLASSES_DE_ENTREGA != VM.CLASSES_PERMITIDAS)
    checar(u"nenhuma classe de achado vazou para a ENTREGA",
           not (set(VM.CLASSES_DE_ACHADO) & set(VM.CLASSES_DE_ENTREGA)),
           u", ".join(sorted(set(VM.CLASSES_DE_ACHADO)
                             & set(VM.CLASSES_DE_ENTREGA))) or u"nenhuma")

    for nome in ("lung tumor", "pancreatic tumor", "hepatic tumor",
                 "colon cancer primaries", "bone lesion",
                 "kidney mass", "liver tumor",
                 "left kidney cyst", "right kidney cyst"):
        checar(u"`%s` esta declarada como ACHADO" % nome,
               nome in VM.CLASSES_DE_ACHADO)
        checar(u"  e NAO esta em CLASSES_DE_ENTREGA",
               nome not in VM.CLASSES_DE_ENTREGA)

    ids = VM.ids_permitidos(por_nome=MAPA)
    checar(u"`ids_permitidos` nao devolve nenhuma das nove",
           not (set(ids) & IDS_DE_ACHADO),
           str(sorted(set(ids) & IDS_DE_ACHADO)) or u"nenhuma")
    checar(u"e ela devolve a anatomia que a ENTREGA declara",
           set(ids) == {1, 6, 11, 115, 121}, str(ids))
    try:
        VM.conferir_classes(ids, por_nome=MAPA)
        ok = True
    except ValueError:
        ok = False
    checar(u"e o que ela devolve passa na propria trava", ok)

    for nome in sorted(VM.CLASSES_DE_ACHADO):
        if nome not in MAPA:
            continue
        try:
            VM.conferir_classes([MAPA[nome]], por_nome=MAPA)
            passa = True
        except ValueError:
            passa = False
        checar(u"`%s` PASSA quando e pedida pelo id (regra B)" % nome, passa)

    MAIS = dict(MAPA)
    MAIS["prostate lesion"] = 201
    try:
        VM.conferir_classes([201], por_nome=MAIS)
        passou = True
    except ValueError:
        passou = False
    checar(u"classe INVENTADA cai (a lista e de permitidos)", not passou)

    try:
        VM.conferir_classes([201], por_nome=MAIS)
        msg = ""
    except ValueError as e:
        msg = str(e)
    checar(u"a recusa nomeia a classe e cita a regra 6",
           "prostate lesion" in msg and "regra 6" in msg, msg[:130])

    try:
        VM.conferir_classes([1, 6, 11, 115, 121, 132], por_nome=MAPA)
        ok = True
    except ValueError as e:
        ok, msg = False, str(e)
    checar(u"figado, aorta, esofago, coracao, medula e via aerea passam", ok)

    try:
        VM.conferir_classes([999], por_nome=MAPA)
        passou = True
    except ValueError as e:
        passou, msg = False, str(e)
    checar(u"id fora do labels.json e recusado, e nao ignorado", not passou)
    checar(u"e a mensagem diz o id", "999" in msg, msg[:90])

    import ast as _ast
    import io as _io
    fonte = _io.open(VM.__file__, encoding="utf-8", errors="replace").read()
    corpo = ""
    for no in _ast.walk(_ast.parse(fonte)):
        if isinstance(no, _ast.FunctionDef) and no.name == "rodar":
            corpo = _ast.dump(no)
    checar(u"`rodar` chama conferir_classes (a lista sem a chamada e enfeite)",
           "conferir_classes" in corpo)


def teste_o_cads_so_nomeia_o_que_alguem_conferiu():
    print("\n-- o CADS so nomeia o que alguem conferiu")
    import radai_cads as CD
    import radai_cads_engine as CE

    permitidos = set(CD.estruturas())
    checar(u"`estruturas()` nao esta vazia", bool(permitidos),
           u"%d" % len(permitidos))
    checar(u"e ela e o CONTRADOMINIO do DE_PARA, e nao uma segunda lista",
           permitidos == set(CD.DE_PARA.values()),
           u"duas listas divergem, e a que fica para tras e a que ninguem rele")

    try:
        CE.conferir_rotulos(sorted(permitidos))
        ok = True
    except ValueError:
        ok = False
    checar(u"o vocabulario inteiro do motor passa na propria trava", ok)

    for forjado in (u"lung_nodule", u"prostate_lesion", u"uterus"):
        try:
            CE.conferir_rotulos([forjado])
            passou, msg = True, u""
        except ValueError as e:
            passou, msg = False, u"%s" % e
        checar(u"`%s` cai (a lista e de permitidos)" % forjado, not passou)
        checar(u"  e a recusa diz qual foi", forjado in msg, msg[:110])

    algum = sorted(permitidos)[0]
    try:
        CE.conferir_rotulos([algum, u"bone_lesion"])
        passou = True
    except ValueError:
        passou = False
    checar(u"um rotulo desconhecido no meio de bons derruba o conjunto",
           not passou)

    import ast as _ast2
    import io as _io2
    fonte = _io2.open(CE.__file__, encoding="utf-8", errors="replace").read()
    corpo = ""
    for no in _ast2.walk(_ast2.parse(fonte)):
        if isinstance(no, _ast2.FunctionDef) and no.name == "masks_da_saida":
            corpo = _ast2.dump(no)
    checar(u"`masks_da_saida` chama conferir_rotulos", "conferir_rotulos" in corpo)
    i_trava = fonte.find("conferir_rotulos(tabela.values()")
    i_laco = fonte.find("for idx, nome in tabela.items()")
    checar(u"e ela vem ANTES do laco que cria as mascaras",
           i_trava > 0 and i_laco > i_trava, u"%d < %d" % (i_trava, i_laco))


def teste_estrutura_fina_nao_e_suavizada():
    import numpy as np
    import radai_geom as rg
    print(u"\n-- estrutura fina: a ponta que o TS entrega fica --")

    g = rg.Grade((3.0, 0.98, 0.98))

    def cone(raios):
        m = np.zeros((24, 48, 48), bool)
        yy, xx = np.ogrid[:48, :48]
        for i, r in enumerate(raios):
            m[5 + i] = ((yy - 24) ** 2 + (xx - 24) ** 2) <= r * r
        return m

    def ext_mm(m):
        z = np.where(np.asarray(m).any(axis=(1, 2)))[0]
        return (z.max() - z.min() + 1) * 3.0 if len(z) else 0.0

    casos = (
        (u"estiloide", [2, 2, 1.6, 1.3, 1, .8, .6, .5], 15.0),
        (u"lamina", [2, 1.5, 1, 1, .7, .5, .5, .5], 12.0),
        (u"agulha", [1.5, 1.2, 1, .8, .6, .5, .5, .5], 9.0),
    )
    for nome, raios, esperado_1_5 in casos:
        m = cone(raios)
        checar(u"%s: o fantoma tem 24 mm de extensao" % nome,
               abs(ext_mm(m) - 24.0) < 1e-6, "%.1f" % ext_mm(m))

        r15 = rg.suavizar(m.copy(), 1.5, g)
        r_teto = rg.suavizar(m.copy(), 0.92, g)
        checar(u"%s: a 1,50 mm a extensao cai para %.1f mm"
               % (nome, esperado_1_5),
               abs(ext_mm(r15) - esperado_1_5) < 1e-6, "%.1f" % ext_mm(r15))
        checar(u"%s: e o TETO de 0,92 mm amputa o MESMO tanto" % nome,
               abs(ext_mm(r_teto) - esperado_1_5) < 1e-6,
               "%.1f" % ext_mm(r_teto))

        checar(u"%s: e o volume sai IGUAL (a massa andou, nao sumiu)" % nome,
               int(r15.sum()) == int(m.sum()),
               "%d -> %d" % (int(m.sum()), int(r15.sum())))

        r04 = rg.suavizar(m.copy(), 0.4, g)
        checar(u"%s: so a 0,40 mm (sub-voxel) a ponta sobrevive" % nome,
               abs(ext_mm(r04) - 24.0) < 1e-6, "%.1f" % ext_mm(r04))

        fina, raio = M.estrutura_fina(m, g)
        checar(u"%s: `estrutura_fina` a reconhece" % nome, fina,
               "raio %.2f mm" % raio)

    figado = np.zeros((24, 48, 48), bool)
    figado[6:20, 8:40, 8:40] = True
    fina, raio = M.estrutura_fina(figado, g)
    checar(u"figado NAO e fino, e continua suavizado", not fina,
           "raio %.2f mm" % raio)

    checar(u"mascara vazia nao e tratada como fina",
           M.estrutura_fina(np.zeros((4, 4, 4), bool), g) == (False, 0.0))

    fonte = open(_componentes.fonte("app/engine.py"),
                 encoding="utf-8").read()
    checar(u"`estrutura_fina` chama `radai_geom.espessura_mm`",
           "radai_geom.espessura_mm(mask, grade)" in fonte)
    corpo = fonte[fonte.index("def teto_de_suavizacao("):]
    corpo = corpo[:corpo.index("\ndef ")]
    checar(u"e o teto parou de refazer a conta inline",
           "espessura_mm" in corpo and "distance_transform_edt" not in corpo)

    checar(u"a recusa esta no caminho individual",
           "_fina, _raio = estrutura_fina(m, grade)" in fonte)
    checar(u"e tambem no caminho de grupo",
           _grupo_recusa_a_fina(fonte))
    _isca_g = fonte.replace("estrutura_fina(grupo[_k], grade)",
                            "(False, 0.0)", 1)
    checar(u"  (isca) sem a medida do membro, a checagem reprova",
           _isca_g != fonte and not _grupo_recusa_a_fina(_isca_g))
    checar(u"e o log diz que nao suavizou, e por que",
           "estrutura fina: %d nao suavizada(s)" in fonte)


def teste_pedacos_no_ar_saem_das_nossas_entregas():
    import numpy as np
    import radai_geom as RG
    print(u"\n-- os pedacos no ar saem das nossas entregas --")

    g = RG.Grade((2.0, 1.0, 1.0))
    Z, Y, X = 60, 120, 120
    vol = np.full((Z, Y, X), -1000.0, dtype="float32")
    yy, xx = np.ogrid[:Y, :X]
    corpo = ((yy - 60) ** 2 + (xx - 60) ** 2) <= 40 ** 2
    vol[:] = np.where(corpo, 40.0, -1000.0)

    dentro = np.zeros((Z, Y, X), bool)
    dentro[20:40, 50:70, 50:70] = True
    ruido = np.zeros((Z, Y, X), bool)
    ruido[5:7, 5:7, 5:7] = True
    ruido[50:52, 110:112, 110:112] = True

    masks = {"aorta": (dentro | ruido).copy()}
    tirados = M.limpar_fora_do_corpo(masks, vol, g)
    agora = np.asarray(masks["aorta"])
    checar(u"o ruido no ar saiu", not bool((agora & ruido).any()))
    checar(u"e o que estava dentro ficou INTEIRO",
           int(agora.sum()) == int(dentro.sum()),
           "%d de %d" % (int(agora.sum()), int(dentro.sum())))
    checar(u"e o log sabe quantos pedacos e quanto volume",
           tirados and tirados[0][0] == "aorta" and tirados[0][1] == 2,
           str(tirados))

    encosta = np.zeros((Z, Y, X), bool)
    encosta[30:32, 18:26, 58:62] = True
    m2 = {"pele_vizinha": (dentro | encosta).copy()}
    M.limpar_fora_do_corpo(m2, vol, g)
    checar(u"pedaco que ENCOSTA no corpo fica",
           int(np.asarray(m2["pele_vizinha"]).sum())
           == int((dentro | encosta).sum()))

    linhas = []
    so_fora = {"x": ruido.copy(), "aorta": (dentro | ruido).copy()}
    tirados_x = M.limpar_fora_do_corpo(so_fora, vol, g, log=linhas.append)
    checar(u"estrutura inteiramente fora SAI (R3)", "x" not in so_fora,
           sorted(so_fora))
    checar(u"e o log diz a regra, o nome e o volume",
           any(u"R3 fora do corpo" in l and u"`x`" in l and u"cm3" in l
               for l in linhas), str(linhas)[:160])
    checar(u"e o retorno a lista junto com a parcial",
           sorted(t[0] for t in tirados_x) == ["aorta", "x"],
           str(tirados_x))

    fonte = open(_componentes.fonte("app/engine.py"),
                 encoding="utf-8").read()
    corpo_fn = fonte[fonte.index("def limpar_fora_do_corpo("):]
    corpo_fn = corpo_fn[:corpo_fn.index("\ndef ")]
    for n in ("Skin", "ChestWall_L", "ChestWall_R"):
        checar(u"`%s` fica de fora da limpeza" % n, ('"%s"' % n) in corpo_fn)

    bloco = fonte[fonte.index("def build_rtstruct("):]
    bloco = bloco[:bloco.index("limpar_fora_do_corpo(masks")]
    checar(u"a limpeza roda DENTRO do portao `cru`",
           "and not cru" in bloco)


def teste_contencao_e_buraco_triplanar():
    import numpy as np
    print(u"")
    print(u"  -- contencao anatomica e buraco triplanar --")

    Z, Y, X = 30, 40, 40
    import radai_geom
    g = radai_geom.Grade((1.0, 1.0, 1.0))

    def cx(z0, z1, y0, y1, x0, x1):
        m = np.zeros((Z, Y, X), bool)
        m[z0:z1, y0:y1, x0:x1] = True
        return m

    olho = cx(10, 20, 10, 20, 10, 20)
    lente = cx(13, 17, 13, 17, 16, 26)
    fora_antes = int((lente & ~olho).sum())
    masks = {"eye_left": olho.copy(), "eye_lens_left": lente.copy()}
    aj = M.aplicar_contencao(masks, g)
    dentro = np.asarray(masks["eye_lens_left"])
    checar(u"o cristalino vazava do olho", fora_antes > 0, str(fora_antes))
    checar(u"e foi recortado para dentro",
           int((dentro & ~olho).sum()) == 0)
    checar(u"o que sobrou dele continua la", dentro.any())
    checar(u"e o ajuste foi registrado, com o quanto",
           len(aj) == 1 and aj[0][2] == fora_antes, str(aj))
    checar(u"o OLHO nao foi tocado",
           bool((np.asarray(masks["eye_left"]) == olho).all()))

    longe = {"eye_left": olho.copy(), "eye_lens_left": cx(0, 4, 0, 4, 0, 4)}
    antes = np.asarray(longe["eye_lens_left"]).copy()
    M.aplicar_contencao(longe, g)
    checar(u"recorte que ZERARIA a estrutura nao acontece",
           bool((np.asarray(longe["eye_lens_left"]) == antes).all()))

    checar(u"o nervo optico NAO esta na tabela de contencao",
           not any("optic" in k for k in M.CONTIDAS_EM))

    rim = cx(10, 26, 10, 26, 10, 26)
    cisto = cx(14, 20, 14, 20, 22, 30)
    dentro_antes = int((cisto & rim).sum())
    fora_do_rim = int((cisto & ~rim).sum())
    checar(u"o cisto tem parte DENTRO do rim", dentro_antes > 0,
           str(dentro_antes))
    checar(u"e parte EXOFITICA, fora dele", fora_do_rim > 0, str(fora_do_rim))

    md = {"kidney_left": rim.copy(), "kidney_cyst_left": cisto.copy()}
    ajd = M.aplicar_desconto(md, g)
    rim_depois = np.asarray(md["kidney_left"])
    checar(u"o rim perdeu exatamente o volume do cisto",
           int((rim_depois & cisto).sum()) == 0
           and int(rim_depois.sum()) == int(rim.sum()) - dentro_antes,
           u"%d -> %d, cisto dentro %d"
           % (int(rim.sum()), int(rim_depois.sum()), dentro_antes))
    checar(u"o CISTO nao foi tocado -- inclusive a parte exofitica",
           bool((np.asarray(md["kidney_cyst_left"]) == cisto).all()))
    checar(u"e o ajuste foi registrado, com o quanto",
           len(ajd) == 1 and ajd[0][2] == dentro_antes, str(ajd))

    tudo = {"kidney_left": rim.copy(), "kidney_cyst_left": rim.copy()}
    M.aplicar_desconto(tudo, g)
    checar(u"desconto que ZERARIA o rim nao acontece",
           bool((np.asarray(tudo["kidney_left"]) == rim).all()))

    checar(u"o cisto NAO esta na tabela de contencao",
           not any("cyst" in k for k in M.CONTIDAS_EM),
           str(sorted(M.CONTIDAS_EM)))
    checar(u"e ESTA na de desconto, com o rim do lado certo",
           M.DESCONTADAS_DE.get("kidney_cyst_left") == "kidney_left"
           and M.DESCONTADAS_DE.get("kidney_cyst_right") == "kidney_right",
           str(M.DESCONTADAS_DE))

    for n in ("kidney_cyst_left", "kidney_cyst_right"):
        checar(u"%s NAO e mais rotulo de achado" % n,
               n not in M.ROTULOS_DE_ACHADO)
        checar(u"%s tem nome TG-263 nosso, marcado a conferir" % n,
               M.TG263.get(n, "").startswith("Kidney_Cyst")
               and n in M.TG263_A_CONFERIR, M.TG263.get(n, "(sem nome)"))
    import radai_plausibility as _pl
    for n in ("kidney_cyst_left", "kidney_cyst_right"):
        checar(u"%s esta DECLARADO em JANELAS_HU" % n, n in _pl.JANELAS_HU)
        checar(u"e a janela dele e RECUSADA (None)", _pl.JANELAS_HU[n] is None)

    bloco = cx(5, 25, 10, 30, 10, 30)
    bloco[:, 18:22, 18:22] = False
    n_canal = int((~bloco & cx(5, 25, 18, 22, 18, 22)).sum())
    checar(u"o fantoma tem um canal atravessando", n_canal > 0, str(n_canal))

    ax = radai_geom.preencher_buracos(bloco, por_fatia=True)
    d3 = radai_geom.preencher_buracos(bloco, por_fatia=False)
    tri = radai_geom.preencher_buracos(bloco, triplanar=True)

    bloco2 = cx(5, 25, 10, 30, 10, 30)
    bloco2[10:14, 18:22, :] = False
    n_tunel = int(cx(10, 14, 18, 22, 10, 30).sum())
    ax2 = radai_geom.preencher_buracos(bloco2, por_fatia=True)
    d32 = radai_geom.preencher_buracos(bloco2, por_fatia=False)
    tri2 = radai_geom.preencher_buracos(bloco2, triplanar=True)

    checar(u"o tunel atravessa o bloco", n_tunel > 0, str(n_tunel))
    checar(u"o AXIAL nao o fecha (ele toca a borda em cada corte)",
           int(ax2.sum()) == int(bloco2.sum()),
           u"axial fechou %d" % (int(ax2.sum()) - int(bloco2.sum())))
    checar(u"o 3D tambem nao (nao e cavidade fechada no volume)",
           int(d32.sum()) == int(bloco2.sum()),
           u"3D fechou %d" % (int(d32.sum()) - int(bloco2.sum())))
    checar(u"e o TRIPLANAR fecha", int(tri2.sum()) > int(bloco2.sum()),
           u"triplanar fechou %d voxel(s)" % (int(tri2.sum()) - int(bloco2.sum())))
    checar(u"o triplanar nunca REMOVE voxel",
           bool(((tri2 | bloco2) == tri2).all()))


def teste_coracao_de_radioterapia():
    import numpy as np
    print(u"")
    print(u"  -- o coracao da radioterapia --")

    Z, Y, X = 40, 80, 80
    import radai_geom
    g = radai_geom.Grade((3.0, 1.0, 1.0))

    def cx(z0, z1, y0, y1, x0, x1):
        m = np.zeros((Z, Y, X), bool)
        m[z0:z1, y0:y1, x0:x1] = True
        return m

    coracao = cx(8, 25, 20, 50, 25, 55)
    asc = cx(18, 30, 12, 19, 36, 46)
    desc = cx(0, 34, 58, 66, 36, 46)
    aorta = asc | desc
    cava = cx(18, 26, 12, 19, 48, 54)

    masks = {"heart": coracao, "aorta": aorta, "superior_vena_cava": cava,
             "liver": cx(0, 8, 20, 60, 20, 60)}
    vox = float(np.prod(g.spacing)) / 1000.0

    rt, d = M.coracao_de_radioterapia(dict(masks), g)
    checar(u"o composto e construido", rt is not None)
    if rt is None:
        return

    sobra = float((rt & desc).sum()) * vox
    checar(u"a aorta DESCENDENTE nao entra no coracao", sobra < 0.5,
           u"%.1f cm3 dela entraram" % sobra)
    checar(u"e ela e devolvida para virar GreatVes",
           d is not None and d.any())
    esperado = float((desc & (np.arange(Z)[:, None, None] <= 24)).sum()) * vox
    saiu = float(d.sum()) * vox
    checar(u"e ela vem quase inteira (abaixo do topo do coracao)",
           abs(saiu - esperado) < esperado * 0.15,
           u"%.0f de %.0f cm3" % (saiu, esperado))

    dentro = float((rt & asc).sum()) * vox
    checar(u"a aorta ASCENDENTE entra", dentro > 0.5, u"%.1f cm3" % dentro)
    acima = float((rt & asc & (np.arange(Z)[:, None, None] > 24)).sum()) * vox
    checar(u"e so o que esta ABAIXO do topo do coracao", acima < 0.5,
           u"%.1f cm3 acima entraram" % acima)

    checar(u"a veia cava superior entra", float((rt & cava).sum()) > 0)
    checar(u"o coracao original esta inteiro dentro",
           bool((rt & coracao == coracao).all()))
    checar(u"e o composto e MAIOR que o coracao do modelo",
           float(rt.sum()) > float(coracao.sum()))

    oar = M.para_oar(dict(masks), grade=g)
    checar(u"`superior_vena_cava` sai do conjunto de OAR",
           "superior_vena_cava" not in oar)
    checar(u"e a `aorta` que fica e a DESCENDENTE",
           "aorta" in oar and float((oar["aorta"] & asc).sum()) * vox < 0.5)
    checar(u"o figado nao foi tocado",
           bool((np.asarray(oar["liver"]) == masks["liver"]).all()))

    antigo = M.para_oar(dict(masks))
    checar(u"sem grade, o `heart` continua o do modelo",
           bool((np.asarray(antigo["heart"]) == coracao).all()))
    checar(u"e a aorta continua inteira", "aorta" in antigo and
           bool((np.asarray(antigo["aorta"]) == aorta).all()))
    checar(u"e a veia cava continua la", "superior_vena_cava" in antigo)

    r2, _d2 = M.coracao_de_radioterapia({"aorta": aorta}, g)
    checar(u"serie sem coracao: nao compoe nada", r2 is None)


def teste_coracao_nao_desce_com_a_cava():
    import numpy as np
    print(u"")
    print(u"  -- a cava inferior nao estica o coracao para baixo --")

    Z, Y, X = 40, 80, 80
    import radai_geom
    g = radai_geom.Grade((3.0, 1.0, 1.0))

    def cx(z0, z1, y0, y1, x0, x1):
        m = np.zeros((Z, Y, X), bool)
        m[z0:z1, y0:y1, x0:x1] = True
        return m

    coracao = cx(8, 25, 20, 50, 25, 55)
    cava_inf = cx(0, 20, 12, 19, 48, 54)
    desc = cx(0, 34, 58, 66, 36, 46)
    masks = {"heart": coracao, "aorta": desc,
             "inferior_vena_cava": cava_inf}
    vox = float(np.prod(g.spacing)) / 1000.0

    rt, d = M.coracao_de_radioterapia(dict(masks), g)
    checar(u"o composto e construido", rt is not None)
    if rt is None:
        return

    zs = np.where(rt.any(axis=(1, 2)))[0]
    zc = np.where(coracao.any(axis=(1, 2)))[0]
    checar(u"o composto nao desce abaixo do apice do coracao",
           int(zs.min()) >= int(zc.min()),
           u"composto comeca em z=%d e o coracao em z=%d"
           % (int(zs.min()), int(zc.min())))
    fora = float((rt & cava_inf & ~np.isin(
        np.arange(Z), zc).reshape(-1, 1, 1)).sum()) * vox
    checar(u"  e nenhum voxel de cava abaixo do apice entrou",
           fora < 0.01, u"%.2f cm3 entraram" % fora)

    dentro = float((rt & cava_inf).sum()) * vox
    checar(u"  e a cava DENTRO da janela foi absorvida",
           dentro > 0.5, u"%.2f cm3" % dentro)

    checar(u"a aorta descendente e devolvida", d is not None and d.any())
    if d is not None and d.any():
        zd = np.where(d.any(axis=(1, 2)))[0]
        checar(u"  e ela continua descendo abaixo do apice do coracao",
               int(zd.min()) < int(zc.min()),
               u"a descendente comeca em z=%d e o apice em z=%d"
               % (int(zd.min()), int(zc.min())))


def teste_o_reto_sai_uma_vez_so():
    import numpy as np
    print(u"")
    print(u"  -- o reto sai uma vez so, e nada do CADS entra --")

    Z, Y, X = 40, 60, 60

    def bloco(z0, z1, y0, y1, x0, x1):
        m = np.zeros((Z, Y, X), bool)
        m[z0:z1, y0:y1, x0:x1] = True
        return m

    nossas = {"colon": bloco(5, 30, 20, 40, 20, 40),
              "rectum": bloco(5, 12, 22, 38, 22, 38),
              "urinary_bladder": bloco(6, 14, 10, 20, 24, 36)}
    por_motor = {"cads": {"rectum": bloco(4, 13, 21, 39, 21, 39),
                          "spinal_canal": bloco(2, 38, 45, 52, 27, 33),
                          "larynx": bloco(33, 39, 25, 33, 26, 34),
                          "seminal_vesicles": bloco(7, 11, 30, 36, 28, 34)}}

    masks, origem = M.curar(nossas, por_motor)

    retos = sorted(k for k in masks if "rectum" in k)
    checar(u"sai UM reto so", len(retos) == 1, ", ".join(retos))
    checar(u"e ele e o NOSSO, a derivacao geometrica",
           origem.get("rectum") == M.FONTE_PADRAO, str(origem.get("rectum")))
    checar(u"nenhuma chave `@cads` sobrou",
           not any("@" in k for k in masks), ", ".join(sorted(masks)))

    for x in ("spinal_canal", "larynx", "seminal_vesicles"):
        checar(u"`%s` do CADS NAO entra no entregue" % x, x not in masks,
               "ele so sai no STUDY_cads, em arquivo proprio")
        checar(u"  e o motivo de ela ter saido esta registrado",
               x in getattr(M, "CANDIDATAS_AO_FULL", {}))

    n_nosso = M.nome_clinico(M.TG263.get("rectum", "rectum"), usados=set(),
                             sufixo=M.SUFIXO_AI)
    n_cads = M.nome_clinico(M.TG263.get("rectum", "rectum"), usados=set(),
                            sufixo=M.SUFIXO_POR_MOTOR["cads"])
    checar(u"os dois nomes continuam se distinguindo", n_nosso != n_cads,
           "%s / %s" % (n_nosso, n_cads))
    checar(u"e os dois cabem em %d caracteres" % M.LIMITE_NOME,
           max(len(n_nosso), len(n_cads)) <= M.LIMITE_NOME,
           "%s(%d) %s(%d)" % (n_nosso, len(n_nosso), n_cads, len(n_cads)))
    checar(u"nenhum carrega o `@` interno",
           "@" not in n_nosso and "@" not in n_cads)


def teste_achado_nao_sai_pelo_caminho_cru():
    import numpy as _np

    FANTOMA = "rotulo_de_achado_fantoma"
    VIZINHO = "kidney_left"
    ORIGEM = "lung_nodules"

    def volume():
        arr = _np.zeros((4, 4, 4), dtype="int16")
        arr[0, 0, 0] = 1
        arr[1, 1, 1] = 2
        return arr, {1: FANTOMA, 2: VIZINHO}

    arr, idx = volume()
    checar(u"antes da injecao, o fantoma SAI pelo cru",
           FANTOMA in sorted(M.MasksCruas(arr, idx).keys()),
           str(sorted(M.MasksCruas(arr, idx).keys())))

    guarda_rot = M.ROTULOS_DE_ACHADO
    guarda_org = dict(getattr(M, "ORIGEM_DO_ACHADO", {}))
    try:
        M.ROTULOS_DE_ACHADO = frozenset(set(guarda_rot) | {FANTOMA})
        M.ORIGEM_DO_ACHADO[FANTOMA] = ORIGEM

        arr, idx = volume()
        cru = M.MasksCruas(arr, idx)
        saiu = sorted(cru.keys())
        checar(u"o orgao vizinho continua saindo", VIZINHO in saiu, str(saiu))
        checar(u"e o achado injetado NAO sai pelo cru", FANTOMA not in saiu,
               str(saiu))
        vazou = [k for k in saiu if k in M.ROTULOS_DE_ACHADO]
        checar(u"nenhum nome da lista atravessa o cru", not vazou,
               u", ".join(vazou) or u"nenhum")

        conhecidas = set(M.TASKS_PERMITIDAS) | set(M.TASKS_FORA_DE_ESCOPO)

        def orfaos_de(nomes):
            fora = []
            for nome in nomes:
                if nome in M.TS_MAP:
                    continue
                t = getattr(M, "ORIGEM_DO_ACHADO", {}).get(nome)
                if t and t in conhecidas:
                    continue
                fora.append(nome)
            return fora

        orfaos = orfaos_de(sorted(M.ROTULOS_DE_ACHADO))
        checar(u"todo rotulo de achado tem procedencia declarada",
               not orfaos, u", ".join(orfaos) or u"nenhum orfao")

        del M.ORIGEM_DO_ACHADO[FANTOMA]
        checar(u"e um rotulo SEM origem declarada e acusado como orfao",
               orfaos_de([FANTOMA]) == [FANTOMA])
        M.ORIGEM_DO_ACHADO[FANTOMA] = "task_que_nao_existe_2027"
        checar(u"  e origem apontando task que o motor nao conhece tambem",
               orfaos_de([FANTOMA]) == [FANTOMA])
    finally:
        M.ROTULOS_DE_ACHADO = guarda_rot
        M.ORIGEM_DO_ACHADO.clear()
        M.ORIGEM_DO_ACHADO.update(guarda_org)

    checar(u"a lista de producao foi restaurada ao sair",
           M.ROTULOS_DE_ACHADO is guarda_rot
           and FANTOMA not in M.ORIGEM_DO_ACHADO,
           str(sorted(M.ROTULOS_DE_ACHADO))[:80])


def teste_a_base_eleita_cai_para_a_v2():
    E = M
    import radai_tasks as K

    velho = K.baixados
    try:
        K.baixados = lambda base=None: set(
            [291, 292, 293, 294, 295, 831, 832, 833, 834, 835])
        checar(u"com as duas no disco, vence a v3",
               E.base_eleita("CT") == "total_v3", E.base_eleita("CT"))

        K.baixados = lambda base=None: set([291, 292, 293, 294, 295])
        ditas = []
        r = E.base_eleita("CT", log=ditas.append)
        checar(u"sem a v3 no disco, cai para a v2", r == "total_v2", r)
        checar(u"  e a queda é ESCRITA no log",
               any("total_v2" in m for m in ditas),
               u"base trocada sem rastro é a pior falha que isto pode ter")

        K.baixados = lambda base=None: set(
            [291, 292, 293, 294, 295, 831, 832, 833, 834, 835])
        ditas = []
        E.base_eleita("CT", log=ditas.append)
        checar(u"  e quando NÃO cai, não escreve nada", not ditas,
               u" | ".join(ditas[:2]))

        K.baixados = lambda base=None: set()
        checar(u"disco vazio devolve a preferida, e não a rede",
               E.base_eleita("CT") == "total_v3", E.base_eleita("CT"))

        def _explode(base=None):
            raise OSError("a pasta de pesos nao respondeu")
        K.baixados = _explode
        checar(u"erro ao ler o disco não derruba para a v2",
               E.base_eleita("CT") == "total_v3",
               u"trocar a base por causa de um `listdir` seria o defeito")
        checar(u"  e hoje o `baixados` real nem levanta",
               velho("__pasta_que_nao_existe__") == set(),
               u"o `except` de `base_eleita` é a rede para o dia em que "
               u"alguém tirar o `try` de `_pastas_no_disco`")
    finally:
        K.baixados = velho

    checar(u"`total_v2` vira `total` para a biblioteca",
           E._nome_biblioteca("total_v2") == "total")
    checar(u"  e `total_v3` passa igual",
           E._nome_biblioteca("total_v3") == "total_v3")
    checar(u"as duas são da MESMA família anatômica",
           E._familia("total_v2") == E._familia("total_v3") == "total",
           u"sem isto o `TS_MAP` devolve {} e a série sai sem estrutura")
    for _b in tuple(K.BASES_CT) + tuple(K.BASES_MR):
        checar(u"  `%s` está em TASKS_PERMITIDAS" % _b,
               _b in E.TASKS_PERMITIDAS,
               u"a eleição pode devolvê-la, e `conferir_tasks` a recusaria")
        E.conferir_tasks([_b])

    for _b in K.BASES_CT:
        checar(u"`%s` alimenta o entregue" % _b, E.alimenta_o_entregue(_b),
               u"pelo contrato C5, `False` aqui derruba a série")
    for _b in K.BASES_MR:
        checar(u"`%s` alimenta o entregue, e PELO MAPA" % _b,
               E.alimenta_o_entregue(_b)
               and any(_b in _tm for _tm in E.TS_MAP.values()),
               u"a RM entra no TS_MAP desde 22/09/2026 (quantos rotulos: "
               u"teste_o_mapa_da_rm_leva_40_dos_50)")


def teste_task_de_deteccao_exige_ato_declarado():
    import ast as _ast
    import io as _io
    import re as _re
    import radai_tasks as _T
    import radai_modes as _MD

    checar(u"existe uma lista de tasks PERMITIDAS",
           isinstance(getattr(M, "TASKS_PERMITIDAS", None), dict)
           and len(M.TASKS_PERMITIDAS) > 0)
    checar(u"existe uma lista de tasks DE ACHADO",
           isinstance(getattr(M, "TASKS_DE_ACHADO", None), frozenset)
           and len(M.TASKS_DE_ACHADO) > 0,
           u", ".join(sorted(getattr(M, "TASKS_DE_ACHADO", ()))))

    checar(u"lung_nodules ESTA entre as permitidas (regra B)",
           "lung_nodules" in M.TASKS_PERMITIDAS)
    checar(u"e esta declarada como ACHADO",
           "lung_nodules" in M.TASKS_DE_ACHADO)
    checar(u"e nenhuma permitida e nome que o modelo nao conhece",
           "lung_nodules_1_5mm" not in M.TASKS_PERMITIDAS)

    def recusa(t):
        try:
            M.conferir_tasks([t])
            return False
        except ValueError:
            return True

    checar(u"`conferir_tasks` deixa `lung_nodules` passar (ato declarado)",
           not recusa("lung_nodules"))
    checar(u"e `lung_vessels_LEGACY` tambem (o comportamento antigo)",
           not recusa("lung_vessels_LEGACY"))
    checar(u"task com nome INVENTADO tambem cai (a lista e de permitidos)",
           recusa("deteccao_de_qualquer_coisa_2027"))

    for t in sorted(M.TASKS_DE_ACHADO):
        checar(u"%s fora de radai_tasks.PADRAO" % t, t not in _T.PADRAO,
               u" ".join(_T.PADRAO))

    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    vig = _io.open(_componentes.fonte("app/radai_watcher.py"),
                   encoding="utf-8").read()
    m = _re.search(r"(?m)^TASKS=(.*)$", vig)
    checar(u"o DEFAULT_CFG NAO tem linha TASKS= (v8.4: o vigia roda a base e "
           u"a anatomia)", m is None
           and u"TASKS = [base_do_vigia()]" in vig)
    import radai_modes as _MD1
    de_fabrica = [_MD1.base_de("CT")] if m is None else m.group(1).split()
    for t in sorted(M.TASKS_DE_ACHADO):
        checar(u"%s fora do TASKS= de fabrica" % t, t not in de_fabrica,
               u" ".join(de_fabrica))

    import inspect as _insp
    _params = set(_insp.signature(_MD.tasks_da_topografia).parameters)
    checar(u"a lista da anatomia nao tem por onde receber uma caixa marcada",
           not (_params & {"escolhidas", "marcadas", "extras", "tasks"}),
           u", ".join(sorted(_params)))
    for _mod in ("CT", "MR"):
        for reg in _MD.TOPOGRAFIAS:
            saiu = _MD.tasks_da_topografia([reg], _mod,
                                           permitidas=M.TASKS_PERMITIDAS,
                                           achados=M.TASKS_DE_ACHADO)
            checar(u"a lista da anatomia (%s) em %s nao devolve lung_nodules"
                   % (_mod, reg), "lung_nodules" not in saiu, u" ".join(saiu))
        todas = _MD.tasks_da_topografia(list(_MD.TOPOGRAFIAS), _mod,
                                        permitidas=M.TASKS_PERMITIDAS,
                                        achados=M.TASKS_DE_ACHADO)
        checar(u"nem com o corpo inteiro no campo (%s)" % _mod,
               not (set(todas) & M.TASKS_DE_ACHADO), u" ".join(todas))
    try:
        _MD.conferir_regra_a(_MD.ANATOMIA, ["total_v3", "lung_nodules"],
                             M.TASKS_DE_ACHADO)
        _levantou = False
    except Exception:
        _levantou = True
    checar(u"`conferir_regra_a` LEVANTA com achado na origem ANATOMIA",
           _levantou)
    try:
        _MD.conferir_regra_a(_MD.MARCADO, ["total_v3", "lung_nodules"],
                             M.TASKS_DE_ACHADO)
        _passou = True
    except Exception:
        _passou = False
    checar(u"  (isca) e passa com a caixa MARCADA, que e ato declarado",
           _passou)
    checar(u"e o TASKS= de fabrica que o vigia le e o Padrao",
           sorted(set(_T.traduzir_apelidos(de_fabrica)))
           == sorted(set(_T.PADRAO)),
           u"%s contra %s" % (de_fabrica, _T.PADRAO))

    try:
        M.conferir_tasks(list(de_fabrica) + ["head_glands_cavities",
                                             "headneck_muscles",
                                             "headneck_bones_vessels",
                                             "head_muscles"])
        ok, msg = True, ""
    except ValueError as e:
        ok, msg = False, str(e)
    checar(u"as tasks do config de fabrica e do protocolo H&P passam", ok,
           msg[:120])

    try:
        M.run_ts_task(None, "deteccao_de_qualquer_coisa_2027", "cpu", "jid_teste")
        parou = False
    except ValueError:
        parou = True
    except Exception:
        parou = False
    checar(u"`run_ts_task` recusa task fora do vocabulario ANTES do TS", parou)

    fonte = _io.open(M.__file__, encoding="utf-8", errors="replace").read()
    alvo = None
    for no in _ast.walk(_ast.parse(fonte)):
        if isinstance(no, _ast.FunctionDef) and no.name == "run_ts_task":
            alvo = no
    checar(u"`run_ts_task` existe no engine", alvo is not None)

    linha_anuncio, linha_popen = None, None
    if alvo is not None:
        for sub in _ast.walk(alvo):
            if (isinstance(sub, _ast.If)
                    and isinstance(sub.test, _ast.Compare)
                    and any(isinstance(o, _ast.In) for o in sub.test.ops)
                    and any(isinstance(c, _ast.Name)
                            and c.id == "TASKS_DE_ACHADO"
                            for c in sub.test.comparators)):
                texto = " ".join(
                    n.value for n in _ast.walk(sub)
                    if isinstance(n, _ast.Constant) and isinstance(n.value, str))
                chama_log = any(isinstance(n, _ast.Call)
                                and isinstance(n.func, _ast.Name)
                                and n.func.id == "_log"
                                for n in _ast.walk(sub))
                if chama_log and "ACHADO" in texto.upper():
                    linha_anuncio = sub.lineno
            if (isinstance(sub, _ast.Call)
                    and isinstance(sub.func, _ast.Attribute)
                    and sub.func.attr == "Popen"):
                linha_popen = sub.lineno

    checar(u"run_ts_task anuncia no log quando a task e de ACHADO",
           linha_anuncio is not None, str(linha_anuncio))
    checar(u"e o `Popen` do TotalSegmentator foi localizado",
           linha_popen is not None, str(linha_popen))
    checar(u"o anuncio vem ANTES de chamar o TotalSegmentator",
           linha_anuncio is not None and linha_popen is not None
           and linha_anuncio < linha_popen,
           u"anuncio na %s, Popen na %s" % (linha_anuncio, linha_popen))


def teste_sobreposicao_e_medida_e_nao_aparada():
    import radai_geom
    g = radai_geom.Grade((1.0, 1.0, 1.0))

    def cx(z0, z1, y0, y1, x0, x1):
        m = np.zeros((60, 60, 60), dtype=bool)
        m[z0:z1, y0:y1, x0:x1] = True
        return m

    masks = {
        "liver": cx(10, 40, 10, 40, 10, 40),
        "stomach": cx(35, 55, 10, 40, 10, 40),
        "kidney_left": cx(10, 30, 45, 55, 10, 30),
        "lung_upper_lobe_left": cx(5, 20, 5, 20, 45, 55),
        "lung_lower_lobe_left": cx(18, 30, 5, 20, 45, 55),
    }
    masks["lung_left"] = (masks["lung_upper_lobe_left"]
                          | masks["lung_lower_lobe_left"])

    antes = dict((k, int(v.sum())) for k, v in masks.items())
    r = M.sobreposicoes(masks, g)
    pares = set(tuple(sorted((a, b))) for a, b, _, _ in r)

    checar(u"acusa figado e estomago sobrepostos",
           ("liver", "stomach") in pares, str(sorted(pares)))
    checar(u"e os dois lobos na fissura",
           ("lung_lower_lobe_left", "lung_upper_lobe_left") in pares)
    checar(u"NAO acusa o composto contra as proprias partes",
           not any("lung_left" in p for p in pares), str(sorted(pares)))
    checar(u"estrutura longe nao entra (a caixa filtra antes)",
           not any("kidney_left" in p for p in pares))

    for a, b, vol, fr in r:
        if (a, b) == ("liver", "stomach"):
            checar(u"o laudo diz o volume em cm3", abs(vol - 4.5) < 0.01, str(vol))
            checar(u"e a fracao da menor", abs(fr - 0.25) < 0.01, str(fr))

    depois = dict((k, int(v.sum())) for k, v in masks.items())
    checar(u"nenhuma mascara foi alterada", antes == depois)


def teste_curadoria_ganha_da_derivacao():
    masks = _fantoma_pelve()
    do_modelo = np.zeros_like(masks["colon"])
    do_modelo[14:52, 26:36, 26:36] = True
    masks["rectum"] = do_modelo.copy()

    msgs = []
    criadas = M.aplicar_derivadas(masks, _grade_pelve(),
                                  log=msgs.append, protegidas={"rectum"})
    checar(u"o reto do modelo NAO entra na lista de criadas",
           "rectum" not in criadas, str(criadas))
    checar(u"o reto entregue e byte a byte o do modelo",
           masks["rectum"].sum() == do_modelo.sum()
           and bool((masks["rectum"] == do_modelo).all()),
           u"%d voxels contra %d" % (masks["rectum"].sum(), do_modelo.sum()))
    checar(u"o log diz que ficou com o do modelo",
           any(u"ficou com o do modelo" in m for m in msgs),
           " | ".join(msgs))

    colon = masks["colon"]
    checar(u"o colon nao encosta no reto do modelo",
           int((colon & do_modelo).sum()) == 0,
           u"%d voxels sobrepostos" % int((colon & do_modelo).sum()))

    m2 = _fantoma_pelve()
    m2["rectum"] = do_modelo.copy()
    M.aplicar_derivadas(m2, _grade_pelve())
    checar(u"sem `protegidas`, a derivacao de fato sobrescreve (o defeito era real)",
           not bool((m2["rectum"] == do_modelo).all()),
           u"o reto ficou igual ao do modelo mesmo sem proteger — "
           u"entao esta checagem nao prova nada")


def teste_curadoria_atravessa_o_build():
    cheia = np.ones((4, 4, 4), dtype=bool)
    fora, origem = M.curar({"rectum": cheia.copy(), "bladder": cheia.copy()},
                           {"cads": {"rectum": cheia.copy(),
                                     "seminal_vesicles": cheia.copy()}})
    prot = set(k for k, v in origem.items()
               if v not in ("", M.FONTE_PADRAO, "derivada"))
    checar(u"nenhuma estrutura do CADS entra no entregue", not prot,
           str(sorted(prot)))
    checar(u"a vesicula seminal do CADS e IGNORADA (era `MELHOR_FONTE`)",
           "seminal_vesicles" not in fora, str(sorted(fora)))
    checar(u"e o reto do CADS tambem (era `AMBOS`)",
           "rectum@cads" not in fora and "rectum@cads" not in origem,
           str(sorted(fora)))
    checar(u"sai UM reto so, e ele e o nosso",
           "rectum" in fora and origem.get("rectum") == M.FONTE_PADRAO,
           str(origem.get("rectum")))
    checar(u"e o que saiu de `MELHOR_FONTE` ficou registrado",
           len(getattr(M, "CANDIDATAS_AO_FULL", {})) == 10,
           str(len(getattr(M, "CANDIDATAS_AO_FULL", {}))))
    checar(u"o reto esta la, com a decisao escrita",
           "rectum" in getattr(M, "CANDIDATAS_AO_FULL", {}))
    checar(u"o sufixo por motor continua sabendo nomear o do CADS",
           M.nome_clinico("rectum", set(),
                          sufixo=M.SUFIXO_POR_MOTOR["cads"]) == "Rectum_cds")
    checar(u"e a bexiga continua nossa", origem["bladder"] == M.FONTE_PADRAO)


def teste_derivadas_particionam_o_colon():
    masks = _fantoma_pelve()
    colon_antes = int(masks["colon"].sum())
    import radai_geom as _G
    _j = M.desenhar_juncao_sacroiliaca(masks, _grade_pelve())
    marcos = {"juncao": None if _j is None else _j.copy()}
    criadas = M.aplicar_derivadas(masks, _grade_pelve())
    checar(u"criou o reto (o canal anal saiu em 04/09)", set(criadas) == {"rectum"},
           str(criadas))
    reto = masks.get("rectum")
    canal = masks.get("anal_canal")
    colon = masks["colon"]
    if reto is None or canal is None:
        return
    z = lambda m: np.where(m.any(axis=(1, 2)))[0]
    checar(u"canal anal vai do fundo ate a tuberosidade",
           z(canal).min() == 10 and z(canal).max() == 20,
           u"%d..%d" % (z(canal).min(), z(canal).max()))
    checar(u"o marco da juncao foi desenhado", marcos["juncao"] is not None)
    if marcos["juncao"] is None:
        return
    fim_si = int(z(marcos["juncao"]).min())
    checar(u"reto vai da tuberosidade ao FIM da juncao sacroiliaca",
           z(reto).min() == 21 and z(reto).max() == fim_si,
           u"%d..%d, fim da juncao em %d"
           % (z(reto).min(), z(reto).max(), fim_si))
    checar(u"o colon recomeca logo acima do reto",
           z(colon).min() == fim_si + 1,
           u"%d, esperado %d" % (z(colon).min(), fim_si + 1))
    _topo_s1 = int(z(masks["vertebrae_S1"]).max()) if "vertebrae_S1" in masks else None
    if _topo_s1 is not None:
        checar(u"  e ele fica ABAIXO do promontorio (o marco antigo)",
               fim_si < _topo_s1, u"juncao %d, promontorio %d"
               % (fim_si, _topo_s1))
    checar(u"as tres somam o colon original",
           int((reto | canal | colon).sum()) == colon_antes,
           u"%d de %d" % (int((reto | canal | colon).sum()), colon_antes))
    for a, b, rot in ((reto, canal, u"reto x canal"),
                      (reto, colon, u"reto x colon"),
                      (canal, colon, u"canal x colon")):
        checar(u"%s nao se tocam" % rot, not (a & b).any(),
               u"%d voxels em comum" % int((a & b).sum()))
    checar(u"a mae encolheu (o reto nao e entregue duas vezes)",
           int(colon.sum()) < colon_antes,
           u"%d -> %d" % (colon_antes, int(colon.sum())))


def teste_derivadas_sem_marco_nao_inventam():
    for sem, rot in (((u"sacrum",), u"sem sacro (sem juncao sacroiliaca)"),
                     ((u"hip_left", u"hip_right"), u"sem iliaco"),
                     ((u"colon",), u"sem colon")):
        masks = _fantoma_pelve(sem=sem)
        msgs = []
        criadas = M.aplicar_derivadas(masks, _grade_pelve(), log=msgs.append)
        checar(u"%s: nao deriva nada" % rot, not criadas, str(criadas))
        if u"colon" not in sem:
            checar(u"%s: diz por que" % rot,
                   bool(msgs) and (u"nao ha" in msgs[0]
                                   or u"juncao sacroiliaca" in msgs[0]),
                   (msgs[0][:70] if msgs else u"(calado)"))


def teste_derivada_nao_se_chama_ai():
    import radai_sets as RS
    checar(u"a constante do sufixo de derivada saiu do motor",
           not hasattr(M, "SUFIXO_DER"), getattr(M, "SUFIXO_DER", ""))
    for conj in (M.SUFIXO_AI, "_cds", "_nv"):
        got = M.sufixo_de_procedencia("rectum", {"rectum": "derivada"}, "",
                                      conj)
        checar(u"a derivada leva o sufixo do conjunto (%s)" % conj,
               got == conj, u"devolveu %r" % got)
    checar(u"reto -> Rectum_ai", M.nome_clinico("rectum") == "Rectum_ai",
           M.nome_clinico("rectum"))
    checar(u"o colon que sobra -> Bowel_Large_ai",
           M.nome_clinico("colon") == "Bowel_Large_ai",
           M.nome_clinico("colon"))
    checar(u"canal anal -> Canal_Anal_ai (nome oficial do TG-263)",
           M.nome_clinico("anal_canal") == "Canal_Anal_ai",
           M.nome_clinico("anal_canal"))
    checar(u"o sufixo aposentado continua na leitura de arquivo antigo",
           "_der" in [x.lower() for x in RS.SUFIXOS_APOSENTADOS]
           and RS.raiz_sem_sufixo("Rectum_der") == "rectum",
           RS.raiz_sem_sufixo("Rectum_der"))
    checar(u"  e nao e sufixo vivo de conjunto nenhum",
           "_der" not in [x.lower() for x in RS.SUFIXOS_VIVOS])
    import inspect
    src = inspect.getsource(M.sufixo_de_procedencia)
    alvo = u'    return sufixo_do_conjunto\n'
    checar(u"  (isca) o retorno esta onde a isca o procura",
           src.count(alvo) == 1)
    isca = src.replace(alvo, u'    if marca == "derivada":\n'
                             u'        return "_der"\n' + alvo)
    ns = dict(vars(M))
    exec(compile(isca, "<isca-derivada>", "exec"), ns)
    checar(u"ISCA: com o ramo de antes, o reto sairia com o sufixo aposentado "
           u"(a checagem reprovaria)",
           ns["sufixo_de_procedencia"]("rectum", {"rectum": "derivada"}, "",
                                       M.SUFIXO_AI) == "_der")
    for k in ("rectum", "anal_canal"):
        checar(u"%s nao finge vir de task nenhuma" % k, k not in M.TS_MAP, u"")


def teste_conjunto_cru_nao_recebe_derivada():
    import inspect
    sig = inspect.signature(M.build_rtstruct)
    p = sig.parameters.get("derivar")
    checar(u"build_rtstruct tem `derivar`", p is not None, u"")
    if p is not None:
        checar(u"e nasce DESLIGADO", p.default is False, repr(p.default))
    fonte = inspect.getsource(M.build_rtstruct)
    checar(u"so deriva quando pedem", u"if derivar and grade is not None" in fonte, u"")
    import io as _io
    for arq, liga in ((u"radai_output.py", True),
                      (u"radai_rt.py", False)):
        caminho = os.path.join(os.path.dirname(os.path.dirname(M.__file__)),
                               "app", arq)
        if not os.path.isfile(caminho):
            caminho = os.path.join(os.path.dirname(M.__file__), arq)
        txt = _io.open(caminho, encoding="utf-8", errors="replace").read()
        tem = "derivar=True" in txt
        checar(u"%s %s derivar=True" % (arq, u"liga" if liga else u"NAO liga"),
               tem == liga, u"")


def teste_a_sobreposicao_orgao_e_construcao():
    print(u"\n-- a sobreposicao: orgao x construcao (A4) --")
    import radai_geom
    g = radai_geom.Grade((1.0, 1.0, 1.0))
    forma = (10, 20, 20)

    def caixa(z0, z1, y0, y1, x0, x1):
        a = np.zeros(forma, bool)
        a[z0:z1, y0:y1, x0:x1] = True
        return a
    m = {"heart": caixa(2, 8, 4, 14, 4, 14),
         "heart_model": caixa(3, 7, 5, 12, 5, 12),
         "esophagus": caixa(2, 8, 12, 16, 8, 11)}
    c = {"heart": {"contem": ("heart_model",)}}
    pares_full = M.sobreposicoes(m, g, construcoes=c)
    checar(u"no FULL, construcao x orgao sai da lista (os dois pares)",
           not pares_full, str(pares_full))
    pares_oar = M.sobreposicoes(m, g, construcoes=c, estrito=True)
    nomes = set(tuple(sorted(p[:2])) for p in pares_oar)
    checar(u"no OAR (estrito), o esofago dentro do coracao e ALARME",
           ("esophagus", "heart") in nomes, str(pares_oar))
    checar(u"  e o coracao do modelo, que ele declara conter, nao",
           ("heart", "heart_model") not in nomes, str(pares_oar))
    pares_antes = M.sobreposicoes(m, g)
    checar(u"sem `construcoes`, a regra de antes: os dois pares acusam",
           len(pares_antes) == 2, str(pares_antes))
    c2 = {"heart": {"contem": ("heart_model",)}, "esophagus": {}}
    checar(u"  (isca) duas construcoes sobrepostas acusam no FULL",
           any(tuple(sorted(p[:2])) == ("esophagus", "heart")
               for p in M.sobreposicoes(m, g, construcoes=c2)))


def teste_nenhum_nome_clinico_colide():
    for sufixo in (M.SUFIXO_AI, M.SUFIXO_NV, M.SUFIXO_TS):
        por_nome = {}
        for k in M.TS_MAP:
            por_nome.setdefault(M.nome_clinico(k, sufixo=sufixo), []).append(k)
        colisoes = dict((a, b) for a, b in por_nome.items() if len(b) > 1)
        checar(u"sufixo %s: %d nomes, nenhuma colisao" % (sufixo, len(por_nome)),
               not colisoes,
               u"; ".join(u"%s <- %s" % (a, b) for a, b in colisoes.items())[:150])

def teste_suavizar_conjunto_e_particao():
    import radai_geom
    grade = _grade_pelve()
    masks = _fantoma_pelve()
    M.aplicar_derivadas(masks, grade)
    tri = ["rectum", "colon"]
    p = dict((k, masks[k]) for k in tri)
    d = radai_geom.suavizar_conjunto(p, 2.0, grade)
    for i, a in enumerate(tri):
        for b in tri[i + 1:]:
            checar("suavizado em conjunto: %s x %s nao se tocam" % (a, b),
                   not (d[a] & d[b]).any(),
                   "%d voxels" % int((d[a] & d[b]).sum()))
    checar("nenhuma parte foi apagada",
           all(d[k].any() for k in tri),
           str(dict((k, int(d[k].sum())) for k in tri)))
    uni_antes = np.zeros_like(p[tri[0]])
    uni_dep = np.zeros_like(d[tri[0]])
    for _k in tri:
        uni_antes = uni_antes | p[_k]
        uni_dep = uni_dep | d[_k]
    checar("o volume total da uniao e preservado",
           int(uni_dep.sum()) == int(uni_antes.sum()),
           "%d -> %d" % (int(uni_antes.sum()), int(uni_dep.sum())))
    uma = dict((k, radai_geom.suavizar(p[k], 2.0, grade)) for k in tri)
    sobrepoe_uma = sum(int((uma[a] & uma[b]).sum())
                       for i, a in enumerate(tri) for b in tri[i + 1:])
    checar("a garantia do joint: particao, que uma a uma so cumpre por sorte",
           True, "uma a uma sobrepos %d voxels neste caso" % sobrepoe_uma)
    try:
        radai_geom.suavizar_conjunto(
            {"a": masks["colon"], "b": masks["colon"]}, 2.0, grade)
        checar("recusa entrada sobreposta", False, "aceitou")
    except ValueError:
        checar("recusa entrada sobreposta", True, "")

def _todas_as_fontes_de_nome():
    import json
    fontes = [(k, M.SUFIXO_AI, "TS_MAP") for k in sorted(M.TS_MAP)]
    for k in sorted(M.COMPOSTOS):
        if k not in M.TS_MAP:
            fontes.append((k, M.SUFIXO_AI, "COMPOSTOS"))
    for mae, regra in M.DERIVADAS.items():
        for plano in regra["planos"]:
            fontes.append((plano[3], M.SUFIXO_AI, "DERIVADAS"))
    p = ""
    base = os.path.abspath(os.path.join(pasta_app(AQUI), ".."))
    rabo = ("vista3d_monai", "docs", "labels.json")
    for _ in range(4):
        for meio in (("_montagem", "AUTO_CONTORNO", "modelos"), ("modelos",)):
            c = os.path.join(base, *(meio + rabo))
            if os.path.isfile(c):
                p = c
                break
        if p:
            break
        base = os.path.abspath(os.path.join(base, ".."))
    if os.path.isfile(p):
        import radai_terms
        for v in sorted(json.load(open(p, encoding="utf-8"))):
            fontes.append((radai_terms.normalizar(v), M.SUFIXO_NV, "VISTA-3D"))
    return fontes


def teste_nenhum_nome_colapsa_no_arquivo_real():
    fontes = _todas_as_fontes_de_nome()
    checar("ha o que auditar (>150 nomes)", len(fontes) > 150, str(len(fontes)))
    por_nome = {}
    for chave, sufixo, onde in fontes:
        por_nome.setdefault(M.nome_clinico(chave, sufixo=sufixo), []).append(
            "%s/%s" % (onde, chave))
    col = dict((a, b) for a, b in por_nome.items() if len(b) > 1)
    checar("nenhum colapso entre %d nomes" % len(fontes), not col,
           "; ".join("%s <- %s" % (a, b) for a, b in col.items())[:200])
    baixo = {}
    for nome in por_nome:
        baixo.setdefault(nome.lower(), []).append(nome)
    cx = dict((a, b) for a, b in baixo.items() if len(b) > 1)
    checar("nenhuma colisao ignorando maiuscula/minuscula", not cx, str(cx)[:150])
    nomes = sorted(por_nome)
    suspeitos = []
    for i, a in enumerate(nomes):
        for b in nomes[i + 1:]:
            if len(a) == len(b) and a[:-1] == b[:-1] and a != b:
                if not ({a[-1], b[-1]} <= set("LRSMI")
                        or (a[-1].isdigit() and b[-1].isdigit())):
                    suspeitos.append((a, b))
    checar("vizinhos de 1 caractere sao so lateralidade/nivel",
           not suspeitos, str(suspeitos)[:150])


def teste_o_desempate_preserva_a_procedencia():
    usados = set()
    a = M.nome_clinico("prostate", usados, sufixo=M.SUFIXO_AI)
    usados.add(a)
    b = M.nome_clinico("prostate", usados, sufixo=M.SUFIXO_AI)
    checar("o desempate muda o nome", a != b, "%s / %s" % (a, b))
    checar("e o sufixo sobrevive", b.endswith(M.SUFIXO_AI), b)
    checar("cabe no limite", len(b) <= M.LIMITE_NOME, "%s (%d)" % (b, len(b)))


def teste_suavizacao_e_por_estrutura():
    checar("ha tabela por estrutura", len(M.SUAVIZACAO) > 40, str(len(M.SUAVIZACAO)))
    checar("o padrao e 1,5 mm", abs(M.SUAVIZACAO_PADRAO_MM - 1.5) < 1e-9,
           str(M.SUAVIZACAO_PADRAO_MM))
    osso = M.suavizacao_de("vertebrae_lumbar")
    alca = M.suavizacao_de("colon")
    ar = M.suavizacao_de("trachea")
    vaso = M.suavizacao_de("carotids")
    paren = M.suavizacao_de("liver")
    fora = M.suavizacao_de("estrutura_que_nao_existe")
    checar("osso e mais conservador que parenquima", osso < paren,
           "osso %.1f, parenquima %.1f" % (osso, paren))
    checar("alca intestinal e conservadora (a haustracao e o orgao)",
           alca < paren, "alca %.1f" % alca)
    checar("via aerea e conservadora (ar-tecido nao tem ruido a tirar)",
           ar < paren, "ar %.1f" % ar)
    checar("vaso fica no meio", osso < vaso <= paren,
           "osso %.1f, vaso %.1f, parenquima %.1f" % (osso, vaso, paren))
    checar("estrutura fora da tabela cai no padrao",
           abs(fora - M.SUAVIZACAO_PADRAO_MM) < 1e-9, str(fora))
    checar("escala 0 desliga tudo", M.suavizacao_de("liver", 0.0) == 0.0, "")
    checar("escala 3,0 dobra, mantendo a proporcao",
           abs(M.suavizacao_de("liver", 3.0) - 2 * paren) < 1e-6,
           "%.2f vs %.2f" % (M.suavizacao_de("liver", 3.0), 2 * paren))
    checar("a proporcao osso/parenquima sobrevive a escala",
           abs(M.suavizacao_de("vertebrae_lumbar", 3.0) /
               M.suavizacao_de("liver", 3.0) - osso / paren) < 1e-6, "")


def teste_o_piso_por_volume_saiu():
    import inspect
    sig = inspect.signature(M.build_rtstruct)
    checar("build_rtstruct nao tem mais suavizar_min_cm3",
           "suavizar_min_cm3" not in sig.parameters, str(list(sig.parameters)))
    app = pasta_app(AQUI)
    vivos = []
    for arq in ("engine.py", "radai_watcher.py", "radai_batch.py", "radai_panel.py"):
        caminho = _componentes.fonte("app/" + arq)
        if not os.path.isfile(caminho):
            continue
        txt = open(caminho, encoding="utf-8", errors="replace").read()
        for k, linha in enumerate(txt.split("\n"), 1):
            baixo = linha.lstrip()
            if baixo.startswith("#") or baixo.startswith("//"):
                continue
            if "SUAVIZAR_MIN_CM3" in linha or "suavizar_min_cm3" in linha:
                vivos.append("%s:%d" % (arq, k))
    checar("nenhuma linha viva ainda o cita", not vivos, str(vivos)[:160])


def teste_suavizacao_usa_distancia_com_sinal():
    import radai_geom
    from scipy import ndimage as _ndi
    checar("existe distancia_com_sinal",
           hasattr(radai_geom, "distancia_com_sinal"), "")
    grade = radai_geom.Grade((1.0, 1.0, 1.0))
    m = np.zeros((30, 40, 40), dtype=bool)
    m[10:20, 15:25, 15:25] = True
    d = radai_geom.distancia_com_sinal(m, grade)
    checar("negativa dentro", d[15, 20, 20] < 0, "%.2f" % d[15, 20, 20])
    checar("positiva fora", d[2, 2, 2] > 0, "%.2f" % d[2, 2, 2])
    checar("zero perto da borda", abs(d[10, 20, 20]) <= 1.01, "%.2f" % d[10, 20, 20])
    tubo = np.zeros((60, 60, 60), dtype=bool)
    yy, xx = np.ogrid[:60, :60]
    for z in range(5, 55):
        tubo[z] = ((yy - 30) ** 2 + (xx - 30) ** 2) < 6.25
    g2 = radai_geom.Grade((2.5, 1.0, 1.0))
    for mm in (1.5, 3.0, 6.0):
        s = radai_geom.suavizar(tubo, mm, g2)
        checar("tubo de 2,5 mm inteiro com suavizacao de %.1f mm" % mm,
               s.any() and int(_ndi.label(s)[1]) == 1,
               "%d ilhas" % int(_ndi.label(s)[1]))
        checar("  e o volume nao muda", int(s.sum()) == int(tubo.sum()),
               "%d -> %d" % (int(tubo.sum()), int(s.sum())))

def _pelve_realista(**mud):
    Z, Y, X = 140, 90, 90

    def caixa(z0, z1, y0, y1, x0, x1):
        m = np.zeros((Z, Y, X), dtype=bool)
        m[z0:z1, y0:y1, x0:x1] = True
        return m

    m = {"colon": caixa(10, 130, 42, 52, 42, 52),
         "hip_left": caixa(20, 70, 30, 40, 10, 26),
         "hip_right": caixa(20, 70, 30, 40, 64, 80),
         "sacrum": caixa(40, 76, 28, 42, 24, 66),
         "vertebrae_S1": caixa(60, 74, 58, 74, 34, 60),
         "vertebrae_lumbar": caixa(76, 128, 58, 74, 34, 60)}
    m.update(mud)
    m["_caixa"] = caixa
    caixa_fn = m.pop("_caixa")
    return m, caixa_fn


def teste_derivada_recusa_marco_duvidoso():
    import radai_geom
    grade = radai_geom.Grade((2.0, 1.0, 1.0))
    base, caixa = _pelve_realista()
    checar("o sacro do fantoma tem tamanho de sacro",
           radai_geom.volume_cm3(base["sacrum"], grade) > 8.0,
           "%.1f cm3" % radai_geom.volume_cm3(base["sacrum"], grade))

    criadas = M.aplicar_derivadas(dict(base), grade)
    checar("marco bom: DERIVA", set(criadas) == {"rectum"},
           str(criadas))

    ruins = [
        ("sacro acima da lombar (nivel trocado)",
         {"sacrum": caixa(130, 160, 28, 42, 24, 66)}, "acima"),
        ("sacro colapsado",
         {"sacrum": caixa(64, 66, 30, 34, 44, 48)}, "pequeno"),
        ("sacro fragmentado",
         {"sacrum": (caixa(40, 46, 28, 42, 24, 66)
                     | caixa(50, 56, 28, 42, 24, 66)
                     | caixa(60, 66, 28, 42, 24, 66)
                     | caixa(70, 74, 28, 42, 24, 46))}, "fragment"),
        ("sem quadril (nao ha juncao)",
         {"hip_left": np.zeros_like(base["hip_left"]),
          "hip_right": np.zeros_like(base["hip_right"])}, "juncao"),
        ("colon partido abaixo da juncao",
         {"colon": (caixa(10, 16, 42, 52, 42, 52)
                    | caixa(20, 26, 42, 52, 42, 52)
                    | caixa(30, 34, 42, 52, 42, 52)
                    | caixa(38, 42, 42, 52, 42, 52)
                    | caixa(46, 130, 42, 52, 42, 52))}, "partido"),
    ]
    for rot, mud, pista in ruins:
        m2, _ = _pelve_realista(**mud)
        msgs = []
        c2 = M.aplicar_derivadas(m2, grade, log=msgs.append)
        checar("%s: NAO deriva" % rot, not c2, str(c2))
        checar("  e diz qual marco reprovou",
               bool(msgs) and pista in msgs[0].lower(),
               (msgs[0][:78] if msgs else "(calado)"))
        checar("  e o colon fica INTEIRO no RTSTRUCT",
               "rectum" not in m2, "")

    curta = dict(base)
    curta.pop("vertebrae_lumbar")
    c3 = M.aplicar_derivadas(curta, grade)
    checar("TC curta, sem coluna lombar: ainda deriva",
           set(c3) == {"rectum"}, str(c3))

    partes = list(M.COMPOSTOS.get("vertebrae_lumbar", ()))
    checar("o composto lombar tem as cinco partes (L1..L5)",
           [p for p in partes if p.startswith("vertebrae_L")] and
           len(partes) >= 5, str(partes))

    def _so_partes(**mud):
        m, _cx = _pelve_realista(**mud)
        lombar = m.pop("vertebrae_lumbar")
        z = np.where(lombar.any(axis=(1, 2)))[0]
        fatias = np.array_split(np.arange(int(z.min()), int(z.max()) + 1),
                                len(partes))
        for nome, zz in zip(partes, fatias):
            p = np.zeros_like(lombar)
            p[zz] = lombar[zz]
            m[nome] = p
        return m
    alto = {"sacrum": caixa(130, 160, 28, 42, 24, 66)}
    msgs = []
    c4 = M.aplicar_derivadas(_so_partes(**alto), grade, log=msgs.append)
    checar("so com L1..L5 e o sacro acima: NAO deriva", not c4, str(c4))
    checar("  e diz que o sacro saiu ACIMA da lombar (a conferencia rodou "
           "pelas partes)", bool(msgs) and "acima" in msgs[0].lower(),
           (msgs[0][:90] if msgs else "(calado)"))
    ok_bom = M._marco_confiavel(_so_partes(), grade)[0]
    checar("  e com o sacro no lugar, as partes nao atrapalham (deriva)",
           ok_bom and set(M.aplicar_derivadas(_so_partes(), grade))
           == {"rectum"})
    guardado = M.COMPOSTOS.get("vertebrae_lumbar")
    M.COMPOSTOS["vertebrae_lumbar"] = ()
    try:
        msgs_i = []
        M.aplicar_derivadas(_so_partes(**alto), grade, log=msgs_i.append)
    finally:
        M.COMPOSTOS["vertebrae_lumbar"] = guardado
    checar("ISCA: sem o bloco das partes, o motivo NAO e «acima» (a "
           "checagem reprovaria)",
           not (msgs_i and "acima" in msgs_i[0].lower()),
           (msgs_i[0][:90] if msgs_i else "(calado)"))

ROTULOS_TOTAL_MR = (
    "adrenal_gland_left", "adrenal_gland_right", "aorta", "autochthon_left",
    "autochthon_right", "brain", "clavicula_left", "clavicula_right", "colon",
    "duodenum", "esophagus", "femur_left", "femur_right", "gallbladder",
    "gluteus_maximus_left", "gluteus_maximus_right", "gluteus_medius_left",
    "gluteus_medius_right", "gluteus_minimus_left", "gluteus_minimus_right",
    "heart", "hip_left", "hip_right", "humerus_left", "humerus_right",
    "iliac_artery_left", "iliac_artery_right", "iliac_vena_left",
    "iliac_vena_right", "iliopsoas_left", "iliopsoas_right",
    "inferior_vena_cava", "intervertebral_discs", "kidney_left",
    "kidney_right", "liver", "lung_left", "lung_right", "pancreas",
    "portal_vein_and_splenic_vein", "prostate", "sacrum", "scapula_left",
    "scapula_right", "small_bowel", "spinal_cord", "spleen", "stomach",
    "urinary_bladder", "vertebrae")

FORA_DO_ENTREGUE_MR = frozenset([
    "autochthon_left", "autochthon_right", "clavicula_left",
    "clavicula_right", "humerus_left", "humerus_right", "scapula_left",
    "scapula_right", "vertebrae", "intervertebral_discs"])

COMPOSTO_DIRETO_NA_RM = frozenset(["lung_left", "lung_right"])


def teste_o_mapa_da_rm_leva_40_dos_50():
    print(u"\n-- a RM no TS_MAP: 40 dos 50 rotulos --")
    try:
        from totalsegmentator.map_to_binary import class_map as _cm
        checar(u"os 50 rotulos escritos aqui sao os da biblioteca instalada",
               sorted(_cm["total_mr"].values()) == sorted(ROTULOS_TOTAL_MR),
               u"a lista medida envelheceu: releia o class_map")
    except ImportError:
        pass
    checar(u"a lista medida tem 50 rotulos distintos",
           len(set(ROTULOS_TOTAL_MR)) == 50, str(len(set(ROTULOS_TOTAL_MR))))
    por_rotulo = {}
    for amig, tm in M.TS_MAP.items():
        for l in tm.get("total_mr", []):
            por_rotulo[l] = amig
    entraram = sorted(por_rotulo)
    checar(u"40 rotulos da RM entram no mapa", len(entraram) == 40,
           u"%d: fora %s" % (len(entraram),
                             sorted(set(ROTULOS_TOTAL_MR) - set(entraram))))
    checar(u"  e os 10 de fora sao os declarados, com motivo",
           set(ROTULOS_TOTAL_MR) - set(entraram) == FORA_DO_ENTREGUE_MR,
           str(sorted(set(ROTULOS_TOTAL_MR) - set(entraram))))
    mesmo = [l for l, a in por_rotulo.items()
             if a not in COMPOSTO_DIRETO_NA_RM
             and M.TS_MAP[a].get("total") != [l]]
    checar(u"  cada rotulo da RM mora na MESMA entrada que o da TC",
           not mesmo, str(mesmo))
    sem_tg = [a for a in por_rotulo.values() if a not in M.TG263]
    checar(u"  e todas tem nome TG-263 (o mesmo da TC)", not sem_tg,
           str(sem_tg))
    comp_rm = set(a for a in por_rotulo.values() if a in M.COMPOSTOS)
    checar(u"  os unicos rotulos da RM que sao nome de composto sao os dois "
           u"pulmoes", comp_rm == COMPOSTO_DIRETO_NA_RM, str(sorted(comp_rm)))
    partes_na_rm = [p for c in comp_rm for p in M.COMPOSTOS[c]
                    if "total_mr" in M.TS_MAP.get(p, {})]
    checar(u"  e a RM nao fornece NENHUMA parte deles (senao disputariam o "
           u"nome -- a checagem [9])", not partes_na_rm, str(partes_na_rm))
    idx = dict((i + 1, n) for i, n in enumerate(ROTULOS_TOTAL_MR))
    nome_idx = dict((n, i) for i, n in idx.items())
    arr = np.zeros((6, 8, 8), dtype=np.int16)
    arr[0] = nome_idx["femur_left"]
    arr[1] = nome_idx["small_bowel"]
    arr[2] = nome_idx["lung_left"]
    arr[3] = nome_idx["urinary_bladder"]
    out = M.masks_da_task(arr, "total_mr", idx)
    checar(u"masks_da_task traduz a RM: femur, intestino, bexiga",
           {"femur_left", "small_intestine", "urinary_bladder"} <= set(out),
           str(sorted(out)))
    checar(u"  e o pulmao da RM, um rotulo so, chega inteiro (fatia 2)",
           "lung_left" in out and int(np.asarray(out["lung_left"]).sum()) == 64
           and bool(np.asarray(out["lung_left"])[2].all()), str(sorted(out)))
    velho = dict(M.TS_MAP)
    try:
        for k in list(M.TS_MAP):
            if "total_mr" in M.TS_MAP[k]:
                M.TS_MAP[k] = dict((t, v) for t, v in M.TS_MAP[k].items()
                                   if t != "total_mr")
        vazio = M.masks_da_task(arr, "total_mr", idx)
        checar(u"ISCA: sem a RM no mapa, a mesma RM nao entrega nada",
               not vazio and not M.alimenta_o_entregue("total_mr"),
               str(sorted(vazio)))
    finally:
        M.TS_MAP.clear()
        M.TS_MAP.update(velho)


def _serie_rm(destino, n=24):
    import pydicom
    escreve_serie(destino, "FANTOMA_RM", datetime(2026, 9, 22, 10, 0), n)
    for f in sorted(os.listdir(destino)):
        c = os.path.join(destino, f)
        ds = pydicom.dcmread(c)
        a = ds.pixel_array.astype(np.int32) + 1000
        a = np.clip(a, 0, 4000).astype(np.int16)
        ds.PixelData = a.tobytes()
        ds.Modality = "MR"
        ds.SOPClassUID = "1.2.840.10008.5.1.4.1.1.4"
        ds.file_meta.MediaStorageSOPClassUID = ds.SOPClassUID
        ds.save_as(c)
    return destino


def _mascaras_de_pelve(forma):
    zz, yy, xx = np.ogrid[0:forma[0], 0:forma[1], 0:forma[2]]

    def bola(cz, cy, cx, r):
        return (((zz - cz) * 3.0) ** 2 + ((yy - cy) * 2.0) ** 2
                + ((xx - cx) * 2.0) ** 2) <= r * r
    return {
        "femur_left": bola(12, 70, 44, 10.0),
        "femur_right": bola(12, 70, 84, 10.0),
        "hip_left": bola(17, 60, 44, 12.0),
        "hip_right": bola(17, 60, 84, 12.0),
        "urinary_bladder": bola(12, 50, 64, 12.0),
        "kidney_left": bola(18, 70, 44, 9.0),
        "liver": bola(18, 50, 80, 14.0),
        "heart": bola(20, 50, 60, 12.0),
        "aorta": bola(14, 80, 64, 5.0),
        "inferior_vena_cava": bola(14, 80, 74, 5.0),
        "spinal_cord": bola(12, 90, 64, 4.0),
        "colon": bola(8, 50, 64, 8.0),
        "gluteus_maximus_left": bola(10, 90, 40, 9.0),
        "vertebrae_L5": bola(14, 92, 64, 6.0),
    }


def teste_a_rm_passa_pelo_pos_processamento_sem_hu():
    print(u"\n-- a RM passa pelo pos-processamento, sem HU --")
    import pydicom
    import SimpleITK as sitk
    import radai_geom
    tmp = tempfile.mkdtemp(prefix="radai_teste_")
    try:
        serie = _serie_rm(os.path.join(tmp, "rm"))
        checar(u"a serie sintetica e RM no cabecalho",
               M._modalidade_da_serie(serie) == "MR",
               str(M._modalidade_da_serie(serie)))
        ref = M.load_sitk(serie)
        vol = sitk.GetArrayFromImage(ref)
        grade = radai_geom.Grade.de_sitk(ref)
        checar(u"e a escala nao tem ar em HU (minimo >= 0)",
               int(vol.min()) >= 0, str(int(vol.min())))
        ok_hu, pq = M._hu_valido(vol)
        checar(u"sem modalidade, a ESCALA diz que nao e HU", not ok_hu, pq)
        checar(u"  com modalidade MR tambem",
               not M._hu_valido(vol, "MR")[0])
        checar(u"  e uma TC (ar em -1000) continua sendo HU",
               M._hu_valido(vol.astype(np.int32) - 1000)[0]
               and M._hu_valido(vol, "CT")[0])

        masks = _mascaras_de_pelve(vol.shape)
        v_vert = int(masks["vertebrae_L5"].sum())
        d = []
        oar = M.para_oar(dict(masks), grade=grade, log=d.append,
                         volume_hu=vol, modalidade="MR")
        checar(u"para_oar termina numa RM, com as estruturas",
               "femur_left" in oar and "urinary_bladder" in oar
               and "heart" in oar, str(sorted(oar)))
        checar(u"  e o log diz que pele e refino NAO rodaram, e por que",
               any("NAO rodaram" in m and "MR" in m for m in d),
               u" | ".join(d)[:200])
        checar(u"  a vertebra NAO cresceu (o refino nao rodou)",
               int(np.asarray(oar["vertebrae_L5"]).sum()) == v_vert,
               u"%d -> %d" % (v_vert, int(np.asarray(oar["vertebrae_L5"])
                                          .sum())))
        dp = []
        novos = M.acrescentar_pele_e_parede(dict(masks), grade, vol,
                                            log=dp.append, modalidade="MR")
        checar(u"  acrescentar_pele_e_parede recusa a RM e diz",
               novos == [] and any("nao rodou" in m for m in dp),
               u" | ".join(dp))
        dq = []
        M.acrescentar_pele_e_parede(dict(masks), grade, vol, log=dq.append,
                                    modalidade="CT")
        checar(u"ISCA: lida como TC, a pele entra no calculo (sem a recusa)",
               not any("nao rodou" in m for m in dq), u" | ".join(dq)[:160])
        d2 = []
        oar2 = M.para_oar(dict(masks), grade=grade, log=d2.append,
                          volume_hu=vol)
        checar(u"sem `modalidade`, a escala do volume segura a mesma guarda",
               int(np.asarray(oar2["vertebrae_L5"]).sum()) == v_vert
               and any("NAO rodaram" in m for m in d2),
               u" | ".join(d2)[:160])
        d3 = []
        oar3 = M.para_oar(dict(masks), grade=grade, log=d3.append,
                          volume_hu=vol, modalidade="CT")
        cresceu = int(np.asarray(oar3["vertebrae_L5"]).sum()) > v_vert
        checar(u"ISCA: lida como TC, a vertebra CRESCE para o tecido da RM",
               cresceu, u"%d -> %d" % (v_vert,
                                       int(np.asarray(oar3["vertebrae_L5"])
                                           .sum())))
        regs, laudo = M.regioes_no_campo(oar, grade=grade)
        checar(u"regioes_no_campo responde numa RM (nao derruba)",
               isinstance(regs, tuple) and laudo, str(regs))
        d4 = []
        caminho, nomes = M.build_rtstruct(serie, oar, tasks=["total_mr"],
                                          versao_worker="teste", log=d4.append,
                                          derivar=True, suavizar_mm=1.5)
        ds = pydicom.dcmread(caminho)
        rois = [str(r.ROIName) for r in ds.StructureSetROISequence]
        checar(u"a RM entrega RTSTRUCT, UNAPPROVED, com _ai",
               ds.ApprovalStatus == "UNAPPROVED" and rois
               and all(r.endswith("_ai") for r in rois),
               u", ".join(rois))
        checar(u"  com os nomes TG-263 da TC (Femur_L, Bladder)",
               "Femur_L_ai" in rois and "Bladder_ai" in rois,
               u", ".join(rois))
        checar(u"  e o log diz que a sustentacao por densidade NAO rodou",
               any("sustentacao por densidade: NAO rodaram" in m
                   and "MR" in m for m in d4), u" | ".join(d4)[-240:])
        checar(u"  e nenhuma estrutura foi JULGADA por densidade",
               not any(m.startswith(u"sustentacao:") for m in d4),
               u" | ".join(m for m in d4 if "sustenta" in m)[:200])
        obs = [str(getattr(o, "ROIObservationDescription", ""))
               for o in getattr(ds, "RTROIObservationsSequence", [])]
        checar(u"  e nenhuma ROI leva veredito de densidade no DICOM",
               not any("mediana" in o for o in obs), str(obs[:2]))
        d5 = []
        M.build_rtstruct(serie, oar, tasks=["total_mr"], versao_worker="t",
                         log=d5.append, derivar=True, suavizar_mm=1.5,
                         modalidade="CT")
        checar(u"ISCA: declarada TC, a sustentacao julga a RM",
               any(m.startswith(u"sustentacao:") for m in d5),
               u" | ".join(m for m in d5 if "sustenta" in m)[:200])
        d6 = []
        n = M.aplicar_refino_por_hu(dict(masks), grade, vol, log=d6.append,
                                    modalidade="MR")
        checar(u"aplicar_refino_por_hu recusa a RM por conta propria",
               n == 0 and any("nao rodou" in m for m in d6),
               u" | ".join(d6))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _rois_de(caminho):
    import pydicom
    ds = pydicom.dcmread(caminho)
    return ds, [str(r.ROIName) for r in ds.StructureSetROISequence]


def teste_o_pulmao_da_rm_chega_ao_rtstruct():
    print(u"\n-- o pulmao da RM chega ao RTSTRUCT; o da TC e a uniao dos lobos --")
    import SimpleITK as sitk
    import radai_geom
    tmp = tempfile.mkdtemp(prefix="radai_teste_")
    try:
        serie = _serie_rm(os.path.join(tmp, "rm"))
        ref = M.load_sitk(serie)
        forma = sitk.GetArrayFromImage(ref).shape
        grade = radai_geom.Grade.de_sitk(ref)
        idx = dict((i + 1, n) for i, n in enumerate(ROTULOS_TOTAL_MR))
        num = dict((n, i) for i, n in idx.items())
        z0, z1 = forma[0] // 4, 3 * forma[0] // 4
        rot = np.zeros(forma, dtype=np.int16)
        rot[z0:z1, 30:70, 20:55] = num["lung_left"]
        rot[z0:z1, 30:70, 73:108] = num["lung_right"]
        rot[z0:z1, 72:95, 50:78] = num["liver"]

        def rm_ate_o_rtstruct(pasta_saida):
            masks = M.masks_da_task(rot, "total_mr", idx)
            vol = sitk.GetArrayFromImage(ref)
            oar = M.para_oar(dict(masks), grade=grade, volume_hu=vol,
                             modalidade="MR")
            caminho, _nomes = M.build_rtstruct(
                serie, oar, tasks=["total_mr"], versao_worker="teste",
                derivar=True, suavizar_mm=1.5, modalidade="MR")
            destino = os.path.join(tmp, pasta_saida)
            os.makedirs(destino)
            alvo = os.path.join(destino, os.path.basename(caminho))
            shutil.move(caminho, alvo)
            shutil.rmtree(os.path.dirname(caminho), ignore_errors=True)
            return masks, oar, alvo
        masks, oar, caminho = rm_ate_o_rtstruct("saida_rm")
        v_esq = int(np.count_nonzero(rot == num["lung_left"]))
        checar(u"RM: masks_da_task entrega o pulmao que veio num rotulo so",
               "lung_left" in masks and "lung_right" in masks
               and int(np.asarray(masks["lung_left"]).sum()) == v_esq,
               str(sorted(masks)))
        checar(u"  e para_oar nao o apaga (sem lobos, a uniao seria vazia)",
               "lung_left" in oar
               and int(np.asarray(oar["lung_left"]).sum()) == v_esq,
               str(sorted(oar)))
        ds, rois = _rois_de(caminho)
        checar(u"  e ele chega ao RTSTRUCT: Lung_L_ai e Lung_R_ai, UNAPPROVED",
               "Lung_L_ai" in rois and "Lung_R_ai" in rois
               and ds.ApprovalStatus == "UNAPPROVED", u", ".join(rois))
        velhas = dict((k, M.TS_MAP[k]) for k in ("lung_left", "lung_right"))
        try:
            for k in velhas:
                del M.TS_MAP[k]
            _m1, _o1, cam1 = rm_ate_o_rtstruct("saida_isca1")
            _ds1, rois1 = _rois_de(cam1)
        finally:
            M.TS_MAP.update(velhas)
        checar(u"ISCA: sem `total_mr` no mapa do pulmao, a MESMA RM sai sem ele",
               "Lung_L_ai" not in rois1 and "Lung_R_ai" not in rois1,
               u", ".join(rois1))
        real_aplicar = M.aplicar_compostos

        def ingenua(ms):
            for nome, partes in M.COMPOSTOS.items():
                ped = [ms[p] for p in partes if p in ms]
                if ped:
                    ms[nome] = np.logical_or.reduce(ped)
                else:
                    ms.pop(nome, None)
            return ms
        M.aplicar_compostos = ingenua
        try:
            m2 = M.masks_da_task(rot, "total_mr", idx)
        finally:
            M.aplicar_compostos = real_aplicar
        checar(u"ISCA: uma montagem que refaz o composto sempre apaga o "
               u"pulmao da RM", "lung_left" not in m2, str(sorted(m2)))
        serie_ct = os.path.join(tmp, "ct")
        escreve_serie(serie_ct, "FANTOMA_CT", datetime(2026, 9, 22, 10, 0), 24)
        ref_ct = M.load_sitk(serie_ct)
        forma_ct = sitk.GetArrayFromImage(ref_ct).shape
        grade_ct = radai_geom.Grade.de_sitk(ref_ct)
        idx_ct = {1: "lung_upper_lobe_left", 2: "lung_lower_lobe_left",
                  3: "lung_upper_lobe_right", 4: "lung_middle_lobe_right",
                  5: "lung_lower_lobe_right", 6: "liver"}
        a, b = forma_ct[0] // 4, 3 * forma_ct[0] // 4
        meio = (a + b) // 2
        rct = np.zeros(forma_ct, dtype=np.int16)
        rct[a:meio, 30:70, 20:55] = 1
        rct[meio:b, 30:70, 20:55] = 2
        rct[a:a + 3, 30:70, 73:108] = 3
        rct[a + 3:meio, 30:70, 73:108] = 4
        rct[meio:b, 30:70, 73:108] = 5
        rct[a:b, 72:95, 50:78] = 6
        mct = M.masks_da_task(rct, "total_v3", idx_ct)
        uniao = (rct == 1) | (rct == 2)
        checar(u"TC: lung_left e EXATAMENTE a uniao dos dois lobos",
               "lung_left" in mct
               and np.array_equal(np.asarray(mct["lung_left"]), uniao),
               str(sorted(mct)))
        oar_ct = M.para_oar(dict(mct), grade=grade_ct,
                            volume_hu=sitk.GetArrayFromImage(ref_ct),
                            modalidade="CT")
        checar(u"  e no entregue o composto fica e as partes saem",
               "lung_left" in oar_ct and "lung_upper_lobe_left" not in oar_ct
               and np.array_equal(np.asarray(oar_ct["lung_left"]), uniao),
               str(sorted(oar_ct)))
        cam_ct, _n = M.build_rtstruct(serie_ct, oar_ct, tasks=["total_v3"],
                                      versao_worker="teste", derivar=True,
                                      suavizar_mm=1.5, modalidade="CT")
        _dsc, rois_ct = _rois_de(cam_ct)
        shutil.rmtree(os.path.dirname(cam_ct), ignore_errors=True)
        checar(u"  e o RTSTRUCT da TC leva Lung_L_ai (o composto)",
               "Lung_L_ai" in rois_ct and "Lung_R_ai" in rois_ct,
               u", ".join(rois_ct))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


class _OsEspiao(object):

    def __init__(self, real, vistos):
        self._real, self._vistos = real, vistos

    def __getattr__(self, nome):
        return getattr(self._real, nome)

    def replace(self, a, b):
        self._vistos.append(a)
        return self._real.replace(a, b)


def teste_o_rascunho_da_estatistica_e_de_quem_grava():
    print(u"\n-- o rascunho da estatistica de uso e de quem grava --")
    import threading
    pasta = tempfile.mkdtemp(prefix="radai_teste_")
    arq = os.path.join(pasta, "config.json")
    vistos = []

    def _religar():
        with io.open(arq, "w", encoding="utf-8") as f:
            f.write(u'{"totalseg_id": "totalseg_FANTOMA", "send_usage_stats": true}')

    real = M.os
    M.os = _OsEspiao(real, vistos)
    try:
        _religar()
        r1 = M.estatistica_do_ts(desligar=True, pasta=pasta)
        _religar()
        r2 = M.estatistica_do_ts(desligar=True, pasta=pasta)
        _religar()
        caixa = {}
        th = threading.Thread(target=lambda: caixa.setdefault(
            "r", M.estatistica_do_ts(desligar=True, pasta=pasta)))
        th.start()
        th.join(30)
    finally:
        M.os = real
    checar(u"as tres gravacoes gravaram",
           r1.get("gravou") and r2.get("gravou") and (caixa.get("r") or {}).get("gravou"),
           str((r1, r2, caixa.get("r")))[:200])
    checar(u"tres gravacoes, tres rascunhos diferentes (mesma thread e outra)",
           len(vistos) == 3 and len(set(vistos)) == 3, str(vistos))
    checar(u"  e cada um ao lado do arquivo, com o PID (quem gravou)",
           all(v.startswith(arq + ".radai_%d_" % os.getpid()) for v in vistos),
           str(vistos))
    sobras = [n for n in os.listdir(pasta) if n != "config.json"]
    checar(u"  e nenhum rascunho sobra na pasta", not sobras, str(sobras))


def _conferir_registro(chamados):
    todos = set(k for k, v in globals().items()
                if k.startswith("teste_") and callable(v))
    fora = sorted(todos - set(f.__name__ for f in chamados))
    checar(u"todo teste do arquivo esta na lista do main()", not fora,
           u"nunca chamados: " + ", ".join(fora))


def teste_o_grupo_disjunto_le_a_tabela_por_estrutura():
    print(u"  -- o grupo disjunto le a tabela por estrutura --")
    import radai_geom
    engine = M
    grade = radai_geom.Grade((3.0, 1.0, 1.0))
    Z, Y, X = 36, 180, 180
    costela = np.zeros((Z, Y, X), dtype=bool)
    for k in range(14, 18):
        for ang in np.linspace(0.18, 2.60, 1200):
            yy, xx = 90 + 72 * np.sin(ang), 90 + 72 * np.cos(ang)
            t = min(ang - 0.18, 2.60 - ang) / 0.45
            raio = 0.7 + 1.1 * min(1.0, t)
            rr = int(np.ceil(raio))
            for dy in range(-rr, rr + 1):
                for dx in range(-rr, rr + 1):
                    if dy * dy + dx * dx <= raio * raio:
                        costela[k, int(round(yy + dy)), int(round(xx + dx))] = True
    zz, yy, xx = np.mgrid[0:Z, 0:Y, 0:X]
    outra = (((zz - 16) / 5.0) ** 2 + ((yy - 30) / 12.0) ** 2
             + ((xx - 30) / 12.0) ** 2) <= 1.0

    def eixo(m):
        i = np.argwhere(m)
        return int(i[:, 2].max() - i[:, 2].min() + 1)

    checar("a tabela da 0,8 mm a costela e 2,5 ao coracao (o Heart_ai ganha "
           "+3 mm na construcao)",
           abs(engine.suavizacao_de("rib_left_5", 1.5) - 0.8) < 1e-9 and
           abs(engine.suavizacao_de("heart", 1.5) - 2.5) < 1e-9 and
           engine.CONSTRUCOES_POR_SAIDA()["heart"].get("suavizar_a_mais_mm")
           == 3.0,
           "costela %.2f, coracao %.2f" % (engine.suavizacao_de("rib_left_5", 1.5),
                                           engine.suavizacao_de("heart", 1.5)))

    e0 = eixo(costela)
    m = {"rib_left_5": costela.copy(), "rib_left_6": outra.copy()}
    feitas = engine.suavizar_em_grupos(m, grade, 1.5)
    checar("as duas foram suavizadas em grupo", len(feitas) == 2,
           "%d de 2" % len(feitas))
    checar("a costela sai do grupo com o eixo longo INTEIRO",
           eixo(m["rib_left_5"]) == e0,
           "eixo %d -> %d mm (com o cursor de 1,5 mm ela encolhia)"
           % (e0, eixo(m["rib_left_5"])))

    checar("o cursor ESCALA a tabela (2x cursor = 2x cada estrutura)",
           abs(engine.suavizacao_de("rib_left_5", 3.0)
               - 2 * engine.suavizacao_de("rib_left_5", 1.5)) < 1e-9
           and abs(engine.suavizacao_de("heart", 3.0)
                   - 2 * engine.suavizacao_de("heart", 1.5)) < 1e-9,
           "costela %.2f->%.2f, coracao %.2f->%.2f"
           % (engine.suavizacao_de("rib_left_5", 1.5),
              engine.suavizacao_de("rib_left_5", 3.0),
              engine.suavizacao_de("heart", 1.5),
              engine.suavizacao_de("heart", 3.0)))
    m2 = {"rib_left_5": costela.copy(), "rib_left_6": outra.copy()}
    engine.suavizar_em_grupos(m2, grade, 3.0)
    checar("e nem com o cursor DOBRADO a costela perde a ponta",
           eixo(m2["rib_left_5"]) == e0,
           "eixo %d -> %d mm (o teto de espessura segura)"
           % (e0, eixo(m2["rib_left_5"])))
    checar("e o grupo continua estanque",
           not (m["rib_left_5"] & m["rib_left_6"]).any())


def teste_a_adrenal_nao_e_comida_pelo_rim():
    print(u"  -- a adrenal sobrevive ao rim e ao figado --")
    import radai_geom
    grade = radai_geom.Grade((2.0, 0.98, 0.98))
    FORMA = (60, 120, 120)

    def lamina(z0, z1, y0, y1, x0, x1):
        m = np.zeros(FORMA, dtype=bool)
        m[z0:z1, y0:y1, x0:x1] = True
        return m

    base = {"adrenal_gland_left": lamina(24, 30, 44, 49, 30, 61),
            "kidney_left": lamina(20, 34, 49, 75, 25, 66),
            "liver": lamina(18, 36, 20, 44, 20, 70)}
    n0 = dict((k, int(v.sum())) for k, v in base.items())
    checar("as tres entram disjuntas",
           not (base["adrenal_gland_left"] & base["kidney_left"]).any()
           and not (base["adrenal_gland_left"] & base["liver"]).any())

    t = M.teto_de_suavizacao(base["adrenal_gland_left"], grade)
    checar("o teto da adrenal e da ordem da espessura dela, e nao da caixa",
           t is not None and 0.3 < t < 2.0, "%.2f mm" % (t or -1))
    t_rim = M.teto_de_suavizacao(base["kidney_left"], grade)
    checar("  e o rim, que e grosso, nem encosta no teto da tabela",
           t_rim is not None and t_rim > M.suavizacao_de("kidney_left", 1.5),
           "teto %.2f vs tabela %.2f"
           % (t_rim or -1, M.suavizacao_de("kidney_left", 1.5)))

    masks = dict((k, v.copy()) for k, v in base.items())
    M.suavizar_em_grupos(masks, grade, 1.5)
    perdas = {}
    for k in base:
        n1 = int(M._bool_seguro(masks[k]).sum())
        perdas[k] = 100.0 * (n1 - n0[k]) / n0[k]
    checar("a adrenal NAO perde volume para os vizinhos",
           abs(perdas["adrenal_gland_left"]) < 5.0,
           "%+.1f%% (era -18,5%% no fantoma, -63,6%% na serie real)"
           % perdas["adrenal_gland_left"])
    checar("  e os vizinhos grandes continuam suavizados",
           abs(perdas["kidney_left"]) < 3.0 and abs(perdas["liver"]) < 3.0,
           "rim %+.1f%%, figado %+.1f%%"
           % (perdas["kidney_left"], perdas["liver"]))
    checar("  e o grupo continua estanque",
           not (M._bool_seguro(masks["adrenal_gland_left"])
                & M._bool_seguro(masks["kidney_left"])).any())

    velho = M._DIVISOR_DO_RAIO
    velha_fn = M.estrutura_fina
    try:
        M._DIVISOR_DO_RAIO = 1e-9
        M.estrutura_fina = lambda mask, grade: (False, 0.0)
        m2 = dict((k, v.copy()) for k, v in base.items())
        M.suavizar_em_grupos(m2, grade, 1.5)
        n1 = int(M._bool_seguro(m2["adrenal_gland_left"]).sum())
        p2 = 100.0 * (n1 - n0["adrenal_gland_left"]) / n0["adrenal_gland_left"]
        checar("sem teto E sem a recusa, a adrenal volta a ser comida (isca)",
               p2 < -8.0, "%+.1f%%" % p2)

        M.estrutura_fina = velha_fn
        m3 = dict((k, v.copy()) for k, v in base.items())
        M.suavizar_em_grupos(m3, grade, 1.5)
        n2 = int(M._bool_seguro(m3["adrenal_gland_left"]).sum())
        p3 = 100.0 * (n2 - n0["adrenal_gland_left"]) / n0["adrenal_gland_left"]
        checar("  e `estrutura_fina` sozinha ja impede o dano",
               p3 > -3.0, "%+.1f%%" % p3)
    finally:
        M._DIVISOR_DO_RAIO = velho
        M.estrutura_fina = velha_fn


def teste_o_coracao_e_um_saco_e_nao_a_uniao_das_camaras():
    print(u"  -- o coracao e um saco, e nao a uniao das camaras --")
    import radai_geom as RG
    from scipy import ndimage
    SP = (2.0, 0.98, 0.98)
    grade = RG.Grade(SP)
    Z, Y, X = 80, 200, 200
    zz, yy, xx = np.mgrid[0:Z, 0:Y, 0:X]
    my, mx, mz = (yy - 100.0) * SP[1], (xx - 100.0) * SP[2], zz * SP[0]

    def bolha(z0, rz, y0, ry, x0, rx):
        return (((mz - z0) / rz) ** 2 + ((my - y0) / ry) ** 2
                + ((mx - x0) / rx) ** 2 <= 1.0)

    ae = bolha(114, 18.0, -10.0, 20.0, 22.0, 20.0)
    ad = bolha(106, 20.0, 16.0, 20.0, -26.0, 18.0)
    ve = bolha(62, 34.0, -18.0, 26.0, 18.0, 24.0)
    vd = bolha(70, 30.0, 20.0, 22.0, -28.0, 22.0)
    camaras = ae | ad | ve | vd
    aorta_asc = (((mx - 4.0) ** 2 + (my + 26.0) ** 2) <= 225.0) & (mz >= 100)
    aorta_desc = ((mx + 8.0) ** 2 + (my - 48.0) ** 2) <= 144.0
    vcs = (((mx + 28.0) ** 2 + (my + 6.0) ** 2) <= 121.0) & (mz >= 108)
    pulmao = ((((mx - 105.0) / 50.0) ** 2 + (my / 60.0) ** 2 <= 1.0)
              | (((mx + 105.0) / 50.0) ** 2 + (my / 60.0) ** 2 <= 1.0))
    masks = {"heart": camaras, "aorta": aorta_asc | aorta_desc,
             "superior_vena_cava": vcs,
             "lung_left": pulmao, "lung_right": np.zeros_like(pulmao)}
    checar(u"o fantoma tem as camaras separadas",
           ndimage.label(camaras)[1] >= 3,
           u"%d componente(s)" % ndimage.label(camaras)[1])
    checar(u"  e elas nao encostam no pulmao", not (camaras & pulmao).any())

    def concavidade(m):
        f = RG.contrair(RG.expandir(m, 20.0, grade), 20.0, grade)
        return RG.volume_cm3(f & ~m, grade)

    rt, desc = M.coracao_de_radioterapia(dict(masks), grade)
    checar(u"o coracao de radioterapia saiu", rt is not None and rt.any())
    if rt is None:
        return
    checar(u"e ele e UM volume so", ndimage.label(rt)[1] == 1,
           u"%d componente(s)" % ndimage.label(rt)[1])
    buracos = 0
    for k in range(Z):
        if rt[k].any():
            buracos += int(ndimage.binary_fill_holes(rt[k]).sum() - rt[k].sum())
    checar(u"  e nao sobrou vao preso entre as partes", buracos == 0,
           u"%d voxel(s)" % buracos)
    c_uniao = concavidade(camaras | (aorta_asc & (mz <= mz[camaras].max()))
                          | (vcs & (mz <= mz[camaras].max())))
    c_saco = concavidade(rt)
    checar(u"  e ele e MENOS entalhado que a uniao crua",
           c_saco < c_uniao * 0.75,
           u"uniao %.0f cm3, saco %.0f cm3" % (c_uniao, c_saco))

    for rotulo, alvo in ((u"pulmao", pulmao), (u"aorta descendente", aorta_desc)):
        v = RG.volume_cm3(rt & alvo, grade)
        checar(u"nao engole %s" % rotulo, v < 0.5, u"%.2f cm3" % v)
    perdeu = RG.volume_cm3(camaras & ~rt, grade)
    checar(u"nenhuma camara foi perdida no recorte", perdeu < 0.5,
           u"%.2f cm3 fora" % perdeu)

    velho = M.FECHAMENTO_PERICARDIO_MM
    try:
        M.FECHAMENTO_PERICARDIO_MM = 0.0
        r2, _ = M.coracao_de_radioterapia(dict(masks), grade)
        checar(u"sem o fechamento volta a ser varios pedacos (isca)",
               r2 is not None and ndimage.label(r2)[1] > 1,
               u"%d componente(s)" % (ndimage.label(r2)[1] if r2 is not None else -1))
    finally:
        M.FECHAMENTO_PERICARDIO_MM = velho


def teste_o_femur_do_oar_para_na_tuberosidade():
    print(u"  -- o femur do OAR para na tuberosidade isquiatica --")
    import radai_geom
    grade = radai_geom.Grade((3.0, 1.0, 1.0))
    F = (60, 90, 90)

    def cx(z0, z1, y0, y1, x0, x1):
        m = np.zeros(F, dtype=bool)
        m[z0:z1, y0:y1, x0:x1] = True
        return m

    masks = {"hip_left": cx(30, 45, 40, 60, 20, 40),
             "hip_right": cx(32, 45, 40, 60, 50, 70),
             "femur_left": cx(8, 47, 42, 58, 22, 38),
             "femur_right": cx(8, 47, 42, 58, 52, 68)}
    antes = dict((k, int(v.sum())) for k, v in masks.items())
    n = M.aplicar_recorte_de_oar(masks, grade)
    checar(u"os dois femures foram recortados", n == 2, u"%d" % n)

    zs = {}
    for k in ("femur_left", "femur_right"):
        z = np.where(masks[k].any(axis=(1, 2)))[0]
        zs[k] = (int(z.min()), int(z.max()))
        checar(u"%s encolheu" % k, int(masks[k].sum()) < antes[k])
        checar(u"  e o topo nao se moveu (o trocanter fica)",
               zs[k][1] == 46, u"z=%d" % zs[k][1])
    checar(u"os dois param no MESMO plano (a tuberosidade mais baixa)",
           zs["femur_left"][0] == zs["femur_right"][0],
           u"%s vs %s" % (zs["femur_left"], zs["femur_right"]))
    checar(u"e o plano e o da tuberosidade ESQUERDA (a mais inferior)",
           zs["femur_left"][0] in (30, 31), u"z=%d" % zs["femur_left"][0])

    so_femur = {"femur_left": cx(8, 47, 42, 58, 22, 38)}
    inteiro = int(so_femur["femur_left"].sum())
    checar(u"sem `hip` na serie, nao corta nada",
           M.aplicar_recorte_de_oar(so_femur, grade) == 0)
    checar(u"  e a estrutura sai como o modelo a deu",
           int(so_femur["femur_left"].sum()) == inteiro)

    m3 = {"hip_left": cx(30, 45, 40, 60, 20, 40),
          "femur_left": cx(8, 47, 42, 58, 22, 38)}
    checar(u"sem grade, nao corta", M.aplicar_recorte_de_oar(m3, None) == 0)

    import io as _io
    _raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    fonte = _io.open(_componentes.fonte("app/engine.py"),
                     encoding="utf-8").read()
    import json as _json
    _bib = _json.load(_io.open(_componentes.fonte("app/data/bibliography.json"),
                               encoding="utf-8"))
    _gay = [a for a in _bib.get("artigos") or [] if a.get("id") == "gay2012"]
    checar(u"a bibliografia amarra o atlas (Gay 2012) a `RECORTE_DE_OAR`",
           bool(_gay) and _gay[0].get("doi") == "10.1016/j.ijrobp.2012.01.023"
           and "app/engine.py::RECORTE_DE_OAR" in (_gay[0].get("influencia")
                                                  or []),
           str(_gay[0].get("influencia") if _gay else None))


def teste_o_composto_cede_o_que_o_coracao_levou():
    print(u"  -- o great_vessels cede o que o coracao levou --")
    import radai_geom
    grade = radai_geom.Grade((3.0, 1.0, 1.0))
    FORMA = (48, 100, 100)

    def cx(z0, z1, y0, y1, x0, x1):
        m = np.zeros(FORMA, dtype=bool)
        m[z0:z1, y0:y1, x0:x1] = True
        return m

    base = {"heart": cx(10, 26, 40, 70, 35, 70),
            "aorta": cx(10, 40, 44, 52, 40, 48),
            "superior_vena_cava": cx(18, 30, 30, 38, 50, 58),
            "inferior_vena_cava": cx(6, 20, 72, 80, 45, 53),
            "pulmonary_vein": cx(16, 24, 55, 63, 25, 33),
            "brachiocephalic_trunk": cx(30, 44, 44, 52, 60, 68)}
    masks = M.aplicar_compostos(dict(base))
    checar("o composto great_arteries foi montado",
           "great_arteries" in masks)
    checar("o composto great_veins foi montado", "great_veins" in masks)

    vx = 3.0 * 1.0 * 1.0 / 1000.0
    oar = M.para_oar(dict(masks), grade=grade)
    h = M._bool_seguro(oar["heart"])
    checar("o coracao de radioterapia cresceu com os vasos",
           h.sum() > M._bool_seguro(base["heart"]).sum())
    checar("os vasos individuais sairam do entregue",
           not any(k in oar for k in ("superior_vena_cava", "pulmonary_vein",
                                      "inferior_vena_cava")),
           str(sorted(oar)))
    ga = oar.get("great_arteries")
    checar("e o great_arteries continua existindo", ga is not None)
    if ga is not None:
        ga = M._bool_seguro(ga)
        inter = float((h & ga).sum()) * vx
        checar("coracao e great_arteries NAO se sobrepoem",
               inter < 1e-9, "%.2f cm3 em comum" % inter)
        checar("  e o que sobrou dele nao e vazio (a descendente fica)",
               ga.any(), "%.1f cm3" % (ga.sum() * vx))
    gvn = oar.get("great_veins")
    if gvn is not None:
        gvn = M._bool_seguro(gvn)
        i3 = float((h & gvn).sum()) * vx
        checar("coracao e great_veins NAO se sobrepoem",
               i3 < 1e-9, "%.2f cm3 em comum" % i3)

    oar2 = M.para_oar(dict(masks), grade=None)
    if "great_arteries" in oar2 and "heart" in oar2:
        i2 = float((M._bool_seguro(oar2["heart"])
                    & M._bool_seguro(oar2["great_arteries"])).sum()) * vx
        checar("sem grade nao ha composicao, e nao ha o que separar (isca)",
               i2 >= 0.0, "%.2f cm3" % i2)


def teste_a_descendente_fica_nos_grandes_vasos():
    print(u"  -- a descendente fica nos grandes vasos (B3, a regra) --")
    import ast
    import radai_geom
    grade = radai_geom.Grade((3.0, 1.0, 1.0))
    FORMA = (40, 90, 90)

    def cx(z0, z1, y0, y1, x0, x1):
        m = np.zeros(FORMA, dtype=bool)
        m[z0:z1, y0:y1, x0:x1] = True
        return m
    cor = cx(10, 22, 30, 60, 30, 60)
    asc = cx(14, 32, 32, 38, 62, 68)
    arco = cx(32, 35, 32, 76, 62, 68)
    desc = cx(4, 34, 70, 76, 62, 68)
    m = {"heart": cor, "aorta": (asc | arco | desc) & ~cor,
         "brachiocephalic_trunk": cx(35, 39, 32, 38, 62, 68)}
    _piso = M.VOLUME_MINIMO_CORACAO_CM3
    M.VOLUME_MINIMO_CORACAO_CM3 = 1.0
    try:
        fora, meta = M.preparar_full(dict(m), grade=grade)
    finally:
        M.VOLUME_MINIMO_CORACAO_CM3 = _piso
    h = np.asarray(fora["heart"], bool)
    ga = np.asarray(fora.get("great_arteries", np.zeros(FORMA, bool)), bool)
    janela = np.zeros(FORMA, bool)
    janela[10:22] = True
    checar(u"a descendente INTEIRA esta em great_arteries (inclusive o "
           u"trecho colado ao coracao)", not (desc & ~ga).any(),
           u"%d voxels fora" % int((desc & ~ga).sum()))
    checar(u"a ascendente, na janela do coracao, esta no Heart_ai",
           not ((asc & janela) & ~h).any(),
           u"%d voxels fora" % int(((asc & janela) & ~h).sum()))
    checar(u"  e fora dos grandes vasos (o composto e a soma MENOS o "
           u"Heart_ai)", not ((asc & janela) & ga).any())
    checar(u"a aorta INTEIRA continua no FULL com o nome dela, com a margem "
           u"(o FULL tem o orgao; o OAR leva o composto)", "aorta" in fora
           and not (m["aorta"] & ~np.asarray(fora["aorta"], bool)).any()
           and int(np.asarray(fora["aorta"], bool).sum())
           > int(m["aorta"].sum()))

    com = M.aplicar_compostos(dict(m))
    oar = M.para_oar(dict(com), grade=grade)
    checar(u"para_oar: com o composto, `aorta` nao sai e a descendente esta "
           u"no composto", "aorta" not in oar and not (
               desc & ~np.asarray(oar.get("great_arteries"), bool)).any())
    sem = dict((k, v) for k, v in m.items() if k != "brachiocephalic_trunk")
    oar2 = M.para_oar(sem, grade=grade)
    checar(u"para_oar: SEM o composto, a descendente sai como `aorta`",
           "aorta" in oar2 and not (np.asarray(oar2["aorta"], bool)
                                    & asc & janela).any())

    fonte = io.open(_componentes.fonte("app/engine.py"),
                    encoding="utf-8").read()
    checar(u"para_oar so grava `aorta = desc` quando NAO ha composto "
           u"(`great_arteries` na condicao)", _grava_desc_so_sem_composto(fonte))
    isca = (u"def para_oar(fora, desc):\n"
            u"    if desc is not None and desc.any():\n"
            u"        fora['aorta'] = desc\n")
    checar(u"  ISCA: a gravacao incondicional (a de antes) e acusada",
           not _grava_desc_so_sem_composto(isca))


def _grava_desc_so_sem_composto(fonte):
    import ast
    arv = ast.parse(fonte)
    f = [n for n in ast.walk(arv)
         if isinstance(n, ast.FunctionDef) and n.name == "para_oar"]
    if not f:
        return False
    achou = []

    def andar(no, sob):
        for filho in ast.iter_child_nodes(no):
            s = sob
            if isinstance(filho, ast.If):
                txt = ast.dump(filho.test)
                s = sob or ("great_arteries" in txt)
            if (isinstance(filho, ast.Assign) and filho.targets
                    and isinstance(filho.targets[0], ast.Subscript)
                    and isinstance(filho.value, ast.Name)
                    and filho.value.id == "desc"):
                achou.append(sob)
            andar(filho, s)
    andar(f[0], False)
    return bool(achou) and all(achou)


def teste_o_nvidia_smi_tem_uma_regra_so():
    print(u"  -- o nvidia-smi tem uma regra so (radai_devices) --")
    import ast
    import radai_devices as D
    checar(u"o motor responde o mesmo que radai_devices",
           M._achar_nvidia_smi() == D.achar_nvidia_smi())
    fonte = io.open(_componentes.fonte("app/engine.py"),
                    encoding="utf-8").read()
    checar(u"`_achar_nvidia_smi` chama `radai_devices.achar_nvidia_smi` e "
           u"nao monta caminho proprio", _delega_o_nvidia_smi(fonte))
    isca = (u"def _achar_nvidia_smi():\n"
            u"    import os\n"
            u"    c = os.path.join(os.environ.get('SystemRoot'), 'System32',"
            u" 'nvidia-smi.exe')\n"
            u"    return c if os.path.isfile(c) else 'nvidia-smi'\n")
    checar(u"  ISCA: a copia da regra (a de antes) e acusada",
           not _delega_o_nvidia_smi(isca))
    tmp = tempfile.mkdtemp(prefix="radai_teste_smi_")
    velho = os.environ.get("SystemRoot")
    try:
        os.makedirs(os.path.join(tmp, "System32"))
        exe = os.path.join(tmp, "System32", "nvidia-smi.exe")
        open(exe, "wb").close()
        os.environ["SystemRoot"] = tmp
        checar(u"com o executavel no System32 da sessao, o motor o acha pela "
               u"regra de radai_devices", M._achar_nvidia_smi() == exe,
               M._achar_nvidia_smi())
    finally:
        if velho is None:
            os.environ.pop("SystemRoot", None)
        else:
            os.environ["SystemRoot"] = velho
        shutil.rmtree(tmp, ignore_errors=True)


def _delega_o_nvidia_smi(fonte):
    import ast
    arv = ast.parse(fonte)
    f = [n for n in ast.walk(arv)
         if isinstance(n, ast.FunctionDef) and n.name == "_achar_nvidia_smi"]
    if not f:
        return False
    chama = any(isinstance(n, ast.Call)
                and getattr(n.func, "attr", "") == "achar_nvidia_smi"
                for n in ast.walk(f[0]))
    literais = [n.value for n in ast.walk(f[0])
                if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    monta = any("System32" in s or "NVSMI" in s for s in literais
                if not s.strip().startswith(("u\"", "═")) and len(s) < 40)
    return chama and not monta


def teste_o_leitor_entende_a_linha_do_executor():
    print(u"  -- o leitor do log entende a linha do executor --")
    tmp = tempfile.mkdtemp(prefix="radai_teste_executor_")
    try:
        cam, dar = _leitor_com_relogio(tmp)
        L = M._LeitorDoLogTS(cam, agora=0)
        dar(L, 1, u"Predicting part 1 of 5 ...",
            u"RADAI|rede|dataset=831|ordem=1|device=cpu|resultados=ram",
            u"RADAI|executor|dataset=831|backend=openvino_gpu|precisao=f32|"
            u"ir=convertido|preparar_s=70.0|compilar_s=28.8|threads=-",
            u"RADAI|executor|dataset=831|conferido=1|concordancia=1.00000|"
            u"max_dif_logit=0.00016|primeira_s=126.0|referencia_torch_s=11.0")
        ex = L.executor.get("831") or {}
        checar(u"o leitor guarda o executor da rede 831",
               ex.get("backend") == "openvino_gpu"
               and ex.get("conferido") == "1"
               and ex.get("concordancia") == "1.00000", str(ex))
        checar(u"  e a linha vira evento do log da serie",
               any(u"executor da rede 831" in e and u"openvino_gpu" in e
                   for e in L.eventos), str(L.eventos)[-200:])
        checar(u"  e conta como sinal de vida", L.t_sinal == 1)
        dar(L, 5, u"  Predicted in 4.00s")
        M._JOBS["teste_exec"] = {"partes": []}
        try:
            M._guardar_etapas("teste_exec", "total_v3", L, 1, "cpu")
            partes = (M._JOBS.get("teste_exec") or {}).get("partes") or []
        finally:
            M._JOBS.pop("teste_exec", None)
        checar(u"a etapa do job leva o executor (o dispositivo e o PEDIDO; o "
               u"executor e quem fez)", partes and
               (partes[-1].get("executor") or {}).get("backend")
               == "openvino_gpu", str(partes)[:200])

        class _Antes(M._LeitorDoLogTS):
            def _radai(self, t, agora):
                if t.split("|")[1:2] == ["executor"]:
                    return
                return M._LeitorDoLogTS._radai(self, t, agora)
        cam2, dar2 = _leitor_com_relogio(tmp)
        L2 = _Antes(cam2, agora=0)
        dar2(L2, 1, u"RADAI|executor|dataset=831|backend=xpu|mover_s=30.0")
        checar(u"ISCA: sem o ramo, o executor some (reprovaria)",
               not L2.executor and not any(u"executor" in e
                                           for e in L2.eventos))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def teste_o_contorno_sai_na_aresta_da_celula_e_nao_no_centro():
    print(u"  -- o contorno entregue sai na aresta da celula --")
    import radai_geom
    engine = M
    import pydicom
    ds = pydicom.dataset.Dataset()
    quad = [10.0, 10.0, 0.0, 14.0, 10.0, 0.0, 14.0, 13.0, 0.0, 10.0, 13.0, 0.0]
    def _monta():
        c = pydicom.dataset.Dataset()
        c.ContourData = list(quad)
        c.NumberOfContourPoints = 4
        rc = pydicom.dataset.Dataset()
        rc.ContourSequence = [c]
        d = pydicom.dataset.Dataset()
        d.ROIContourSequence = [rc]
        return d, c

    d, c = _monta()
    engine._suavizar_contornos(d, (1.0, 1.0))
    p = np.reshape([float(v) for v in c.ContourData], (-1, 3))[:, :2]
    checar("poligono de 4 pontos (abaixo do piso do Taubin) e expandido",
           abs(abs(radai_geom.area_poligono(p)) - 20.0) < 1e-6,
           "%.3f mm2, esperado 5 x 4" % abs(radai_geom.area_poligono(p)))

    d, c = _monta()
    engine._suavizar_contornos(d, (1.0, 1.0), suavizar=False)
    p = np.reshape([float(v) for v in c.ContourData], (-1, 3))[:, :2]
    checar("com a suavizacao desligada o meio pixel continua valendo",
           abs(abs(radai_geom.area_poligono(p)) - 20.0) < 1e-6,
           "%.3f mm2" % abs(radai_geom.area_poligono(p)))

    d, c = _monta()
    engine._suavizar_contornos(d, None)
    p = np.reshape([float(v) for v in c.ContourData], (-1, 3))[:, :2]
    checar("sem espacamento nada e expandido (o de antes)",
           abs(abs(radai_geom.area_poligono(p)) - 12.0) < 1e-6,
           "%.3f mm2" % abs(radai_geom.area_poligono(p)))

    checar("o z nao e tocado",
           all(abs(float(v)) < 1e-12 for v in c.ContourData[2::3]))


def teste_o_rotulo_de_conjunto_cabe_nos_16_e_nao_colide():
    print(u"  -- o rotulo de conjunto cabe nos 16 e nao colide --")
    import radai_sets
    vistos = {}
    for c in radai_sets.CONJUNTOS:
        cod = str(c["cod"])
        if cod == "oar":
            continue
        r = ("STUDY_" + cod)[:16]
        checar(u"`STUDY_%s` cabe nos 16" % cod,
               len("STUDY_" + cod) <= 16,
               "%d caracteres" % len("STUDY_" + cod))
        checar(u"e nao colide com `%s`" % vistos.get(r, "-"),
               r not in vistos, "%s ja e de %s" % (r, vistos.get(r)))
        vistos[r] = cod
    checar(u"o entregue leva RadAI_OAR e ele cabe", len("RadAI_OAR") <= 16)
    checar(u"e o entregue NAO leva rotulo de estudo",
           "RadAI_OAR" not in vistos)


def teste_a_lamina_do_pericardio_sobrevive_ao_coracao():
    print(u"  -- a lamina do pericardio sobrevive ao coracao --")
    import radai_geom
    grade = radai_geom.Grade((3.0, 1.0, 1.0))
    Z, Y, X = 40, 160, 160
    zz, yy, xx = np.mgrid[0:Z, 0:Y, 0:X]
    r = np.sqrt(((zz - 20) / 9.0) ** 2 + ((yy - 80) / 34.0) ** 2
                + ((xx - 80) / 30.0) ** 2)
    coracao = r <= 1.00
    lamina = (r > 1.00) & (r <= 1.09)
    n0 = int(lamina.sum())

    s = radai_geom.suavizar_conjunto(
        {"heart": coracao.copy(), "pericardium": lamina.copy()},
        {"heart": 2.5, "pericardium": 0.8}, grade)
    p = s["pericardium"]
    checar(u"o pericardio nao e apagado", bool(p.any()))
    checar(u"e nao perde volume para o coracao",
           int(p.sum()) >= n0, "%d -> %d voxels" % (n0, int(p.sum())))
    checar(u"nem um voxel da lamina e comido",
           int((lamina & ~p).sum()) == 0,
           "%d comidos" % int((lamina & ~p).sum()))
    checar(u"e os dois continuam disjuntos",
           not (p & s["heart"]).any())
    u1 = radai_geom.suavizar_conjunto(
        {"heart": coracao.copy(), "pericardium": lamina.copy()}, 1.5, grade)
    checar(u"com o cursor unico ele PERDIA voxels (o antes)",
           int((lamina & ~u1["pericardium"]).sum()) > 0,
           "%d comidos com 1,5 mm para os dois"
           % int((lamina & ~u1["pericardium"]).sum()))


def teste_a_cor_diz_qual_orgao_e_qual_estrutura():
    print(u"  -- a cor diz qual orgao e qual estrutura --")
    nomes = sorted(set(M.TG263.keys()))
    cores = {}
    for n in nomes:
        cores.setdefault(tuple(M._color(n)), []).append(n)
    checar(u"quase toda estrutura tem cor propria",
           len(cores) >= int(len(nomes) * 0.90),
           "%d cores para %d estruturas" % (len(cores), len(nomes)))
    maior = max((len(v) for v in cores.values()), default=0)
    checar(u"e nenhuma cor e a lata de lixo de dezenas delas",
           maior <= 3, "a cor mais repetida serve %d estruturas" % maior)

    costelas = set(tuple(M._color("rib_left_%d" % i)) for i in range(1, 13))
    checar(u"as 12 costelas esquerdas tem 12 cores",
           len(costelas) == 12, "%d cores" % len(costelas))
    vert = set(tuple(M._color("vertebrae_T%d" % i)) for i in range(1, 13))
    checar(u"as 12 vertebras toracicas tem 12 cores",
           len(vert) == 12, "%d cores" % len(vert))

    for n in ("rib_left_5", "rib_right_9", "vertebrae_T7", "sternum",
              "femur_left"):
        c = M._color(n)
        checar(u"`%s` continua parecendo osso (R>=G>=B)" % n,
               c[0] >= c[1] >= c[2] and c[2] < c[0], str(c))
    for n in ("lung_left", "lung_upper_lobe_right", "trachea"):
        c = M._color(n)
        checar(u"`%s` continua parecendo ar (B>=G>=R)" % n,
               c[2] >= c[1] >= c[0] and c[0] < c[2], str(c))
    for n in ("liver", "aorta"):
        c = M._color(n)
        checar(u"`%s` tem o vermelho na frente" % n, c[0] > c[1] and c[0] > c[2],
               str(c))

    checar(u"a mesma estrutura sai da mesma cor",
           M._color("rib_left_5") == M._color("rib_left_5"))
    checar(u"e o VISTA-3D sai no mesmo matiz, mais claro",
           all(a <= b for a, b in zip(M._color("liver"),
                                      M._color("liver", do_nv=True))),
           "%s -> %s" % (M._color("liver"), M._color("liver", True)))

    checar(u"a tabela declara o que ainda precisa de aval",
           len(M.cores_a_conferir()) > 0,
           "%d cores marcadas" % len(M.cores_a_conferir()))


def teste_o_log_diz_quanto_cada_estrutura_mudou():
    print(u"  -- o log diz quanto cada estrutura mudou --")
    import radai_geom
    grade = radai_geom.Grade((3.0, 1.0, 1.0))
    Z, Y, X = 30, 90, 90
    zz, yy, xx = np.mgrid[0:Z, 0:Y, 0:X]
    a = (((zz - 15) / 6.0) ** 2 + ((yy - 40) / 16.0) ** 2
         + ((xx - 40) / 16.0) ** 2) <= 1.0
    b = (((zz - 15) / 5.0) ** 2 + ((yy - 40) / 12.0) ** 2
         + ((xx - 70) / 12.0) ** 2) <= 1.0

    det = []
    m = {"liver": a.copy(), "spleen": b.copy()}
    M.suavizar_em_grupos(m, grade, 1.5, detalhe=det)
    checar(u"o grupo devolve metrica das duas", len(det) == 2, str(len(det)))
    for nm, mm, a_n, d_n, mant in det:
        checar(u"`%s`: o mm aplicado e o da tabela" % nm,
               abs(mm - M.suavizacao_de(nm, 1.5)) < 1e-9, str(mm))
        checar(u"  e traz antes, depois e mantido", a_n > 0 and d_n > 0
               and 0.0 <= mant <= 1.0, "%d -> %d, %.3f" % (a_n, d_n, mant))

    longe = np.zeros_like(a)
    longe[5:10, 5:15, 5:15] = True
    perto = np.zeros_like(a)
    perto[20:25, 60:70, 60:70] = True
    n = int(longe.sum())
    checar(u"as duas tem o mesmo volume", int(perto.sum()) == n)
    mant = int((longe & perto).sum()) / float(n)
    checar(u"e `mantido` acusa o deslocamento que o volume esconde",
           mant == 0.0, "%.3f" % mant)


def teste_refino_por_densidade_adjacente():
    import numpy as np
    from scipy import ndimage as ndi
    import radai_geom

    PX, PZ = 0.7, 3.0
    NX, NY, NZ = 160, 160, 20
    grade = radai_geom.Grade(spacing_zyx=(PZ, PX, PX))

    zz, yy, xx = np.mgrid[0:NZ, 0:NY, 0:NX]
    mx = (xx - NX / 2.0) * PX
    my = (yy - NY / 2.0) * PX
    mz = (zz - NZ / 2.0) * PZ
    ang = np.arctan2(my, mx)
    r_plano = np.sqrt(mx ** 2 + my ** 2)
    verdade = ((np.sqrt((r_plano - 45.0) ** 2 + (mz + 26.0 * ang) ** 2)
                <= 1.9) & (np.abs(ang) <= 1.2))
    verdade = np.ascontiguousarray(verdade)

    hu = np.full((NZ, NY, NX), 40.0, np.float32)
    hu[verdade] = 950.0
    hu = ndi.gaussian_filter(hu, (0.5, 0.9, 0.9))

    rede = np.ascontiguousarray(hu > 550)
    checar(u"o fantoma reproduz a perda (a rede ve menos que a verdade)",
           rede.sum() < verdade.sum() * 0.75,
           u"%d de %d voxels" % (int(rede.sum()), int(verdade.sum())))

    refinado = M.refinar_por_hu(rede, hu, grade, 300.0)

    def dsc(a, b):
        a, b = np.asarray(a, bool), np.asarray(b, bool)
        return 2.0 * (a & b).sum() / max(1, a.sum() + b.sum())

    d0, d1 = dsc(rede, verdade), dsc(refinado, verdade)
    checar(u"o refino aproxima da verdade", d1 > d0 + 0.10,
           u"DSC %.4f -> %.4f" % (d0, d1))
    checar(u"e ele nao ultrapassa a verdade em volume",
           refinado.sum() <= verdade.sum() * 1.25,
           u"%+.1f%%" % (100.0 * (refinado.sum() - verdade.sum())
                         / verdade.sum()))

    vizinho = np.zeros_like(verdade)
    vizinho[NZ // 2, NY // 2 + 30:NY // 2 + 36, NX // 2 + 30:NX // 2 + 36] = True
    hu2 = hu.copy()
    hu2[vizinho] = 950.0
    ref2 = M.refinar_por_hu(rede, hu2, grade, 300.0)
    checar(u"osso vizinho solto NAO e' adotado",
           not (np.asarray(ref2, bool) & vizinho).any(),
           u"%d voxel(s) do vizinho entraram"
           % int((np.asarray(ref2, bool) & vizinho).sum()))

    longe = np.zeros_like(verdade)
    longe[NZ // 2, 4:9, 4:9] = True
    hu3 = hu.copy()
    hu3[longe] = 950.0
    ref3 = M.refinar_por_hu(rede, hu3, grade, 300.0)
    checar(u"osso longe da mascara nem e' olhado",
           not (np.asarray(ref3, bool) & longe).any())

    checar(u"costela recebe refino", M._familia_para_refino("rib_left_4"))
    checar(u"e pulmao NAO recebe",
           not M._familia_para_refino("lung_left"))
    checar(u"nem traqueia", not M._familia_para_refino("trachea"))
    checar(u"e a cartilagem costal esta DECLARADA e recusada",
           "costal_cartilages" in M.REFINO_POR_HU
           and not M.REFINO_POR_HU["costal_cartilages"])

    igual = M.refinar_por_hu(rede, None, grade, 300.0)
    checar(u"sem volume de HU, devolve a mascara intacta",
           int(np.asarray(igual, bool).sum()) == int(rede.sum()))
    ms = {"rib_left_4": rede.copy()}
    checar(u"e `aplicar_refino_por_hu` sem imagem nao mexe em nada",
           M.aplicar_refino_por_hu(ms, grade, None) == 0)


def teste_a_memoria_da_serie_sai_no_log_uma_vez():
    print(u"  -- a memoria da serie sai no log, e uma vez so --")
    import engine as M
    import inspect
    checar(u"existe medidor de memoria no motor",
           hasattr(M, "_memoria_agora"))
    m = M._memoria_agora()
    checar(u"  e ele MEDE nesta maquina",
           bool(m) and m[0] > 0 and 0 <= m[2] <= 100, str(m))
    _fonte = inspect.getsource(M._memoria_agora)
    _sem_prosa = _fonte.replace(inspect.getdoc(M._memoria_agora) or "~", "")
    checar(u"  e ele delega a `radai_cleaner`, sem segunda implementacao",
           "radai_cleaner" in _sem_prosa and "ctypes" not in _sem_prosa,
           u"a mesma conta em dois lugares: a que ficar para tras mente com "
           u"cara de medida")

    src = inspect.getsource(M.run_ts_task)
    checar(u"o pico e acumulado durante o laco", "_pior" in src)
    _i_while = src.index("while proc.poll() is None:")
    _i_res = src.index("memoria: %.1f GB livres no inicio")
    _i_fim = src.index("if proc.returncode:")
    checar(u"  e o resumo sai DEPOIS do laco, uma vez",
           _i_res > _i_fim > _i_while,
           u"240 linhas iguais enchem as 800 do buffer do painel")
    checar(u"  e o aviso de memoria apertada e uma vez por task",
           "_avisou_mem = True" in src and "not _avisou_mem" in src,
           u"aviso que se repete ensina a ignorar o proximo")
    checar(u"  e a linha declara que a conta inclui o resto da estacao",
           "com tudo o que rodou junto" in src)


def teste_o_indice_26_e_fundido_ao_sacro():
    print(u"  -- o indice 26 e fundido ao sacro --")
    import engine as M
    import radai_sets as RS
    import radai_geom
    checar(u"`vertebrae_L6` continua no TS_MAP (sem ela o rotulo cai fora "
           u"antes de ser fundido)",
           M.TS_MAP.get("vertebrae_L6") == {"total": ["vertebrae_L6"]})
    checar(u"  e o TG263 continua lendo o nome (arquivo antigo)",
           M.TG263.get("vertebrae_L6") == "Vertebrae_L6")
    checar(u"  e saiu da lista a conferir (nao ha mais nome a conferir)",
           "vertebrae_L6" not in M.TG263_A_CONFERIR)
    checar(u"a ressalva «nao foi fundida» saiu",
           "vertebrae_L6" not in M.RESSALVA_DE_ROI)
    checar(u"o OAR nao lista o indice 26",
           not ({"vertebrae_L6", "vertebrae_S1"} & RS.PERMITIDOS_NO_OAR))
    checar(u"o passo da fusao vem logo depois das regras, antes do refino, "
           u"dos compostos e das derivadas",
           [e for e, _v in M.ORDEM_DO_FULL][:2] == ["regras",
                                                   "fusao_do_indice_26"]
           and [e for e, _v in M.ORDEM_DO_FULL].index("fusao_do_indice_26")
           < min([e for e, _v in M.ORDEM_DO_FULL].index(x)
                 for x in ("refino", "compostos", "derivadas")))
    g = radai_geom.Grade((3.0, 2.0, 2.0))
    sac = np.zeros((40, 64, 64), bool)
    sac[2:14, 30:44, 24:40] = True
    l6 = np.zeros_like(sac)
    l6[15:19, 26:42, 24:40] = True
    for nome in ("vertebrae_L6", "vertebrae_S1"):
        m = {"sacrum": sac.copy(), nome: l6.copy()}
        rel = M.fundir_indice_26_no_sacro(m, g)
        checar(u"`%s`: some e entra no sacro, com a peca separada contada"
               % nome, nome not in m and bool((m["sacrum"] & l6).sum()
                                              == l6.sum())
               and rel["pecas_novas"] == 1 and rel["cm3"] > 0, str(rel))
    m = {"vertebrae_L6": l6.copy()}
    M.fundir_indice_26_no_sacro(m, g)
    checar(u"sem sacro, o indice 26 vira o sacro",
           list(m) == ["sacrum"] and bool(m["sacrum"].sum() == l6.sum()))
    vista = M.vista_com_indice_26_fundido({"sacrum": sac, "vertebrae_L6": l6})
    checar(u"a vista do cru esconde o indice 26 e o mostra no sacro",
           list(vista) == ["sacrum"] and "vertebrae_L6" not in vista
           and int(vista["sacrum"].sum()) == int((sac | l6).sum()))
    tres = sac.copy()
    tres[4] = False
    tres[8] = False
    pedacos = {"sacrum": tres}
    _ok0, mot0 = M._marco_confiavel(pedacos, g)
    _ok1, mot1 = M._marco_confiavel(pedacos, g, tolerancia_de_pecas=1)
    checar(u"o sacro em tres pedacos e recusado sem tolerancia",
           u"fragmentado" in mot0, mot0)
    checar(u"  e passa da fragmentacao com a peca que a fusao acrescentou",
           u"fragmentado" not in mot1, mot1)
    lascas = sac.copy()
    for z, y, x in ((20, 10, 10), (24, 50, 50), (28, 10, 50)):
        lascas[z, y, x] = True
    _okl, motl = M._marco_confiavel({"sacrum": lascas}, g)
    checar(u"o sacro inteiro com tres lascas de um voxel nao e fragmentado",
           u"fragmentado" not in motl, motl)
    velho = M.PISO_DE_PECA_DO_SACRO_CM3
    try:
        M.PISO_DE_PECA_DO_SACRO_CM3 = 0.0
        _oki, moti = M._marco_confiavel({"sacrum": lascas}, g)
    finally:
        M.PISO_DE_PECA_DO_SACRO_CM3 = velho
    checar(u"  ISCA: contando toda lasca como pedaco, ele seria recusado",
           u"fragmentado" in moti, moti)


def teste_a_linha_da_computacao_nao_se_contradiz():
    print(u"  -- a linha da computacao roda, e nao afirma os dois lados --")
    import engine

    inv = engine.inventario_de_computacao()
    motivo = str(inv.get("smi") or u"")
    nossos = [n for n in (u"NameError", u"AttributeError", u"TypeError",
                          u"ImportError")
              if n in motivo]
    checar(u"a consulta do nvidia-smi EXECUTA (nao levanta por nossa causa)",
           not nossos,
           u"o motivo de `placas` vazia foi %s -- isso e defeito nosso, "
           u"nao ausencia de placa" % (u", ".join(nossos) or u"-"))
    checar(u"  e o inventario devolve as chaves que a linha le",
           all(k in inv for k in ("placas", "torch_ve", "smi", "driver")),
           str(sorted(inv)))
    checar(u"  e o nvidia-smi e PROCURADO, nao so invocado pelo PATH",
           bool(engine._achar_nvidia_smi()),
           u"o lancador da estacao nao herda o PATH do usuario")

    BASE = {"nucleos": 8, "ram_gb": 16.0, "ram_livre_gb": 8.0,
            "placas": [], "torch_ve": 0, "torch_cuda": "", "torch_versao": "",
            "driver": "", "smi": u"", "escolhido": "", "porque": ""}
    APERTADA = {"nome": "Quadro P2200", "vram_mb": "5120", "usada_mb": "3067"}
    FOLGADA = {"nome": "RTX A4000", "vram_mb": "16376", "usada_mb": "900"}
    orig = engine.inventario_de_computacao
    try:
        def _com(**kw):
            engine.inventario_de_computacao = lambda _i=dict(BASE, **kw): dict(_i)
            return engine.diagnostico_de_computacao()

        campo = _com(torch_ve=1, torch_versao="2.5.1+cu121",
                     torch_cuda="12.1", smi=u"nvidia-smi nao esta no PATH")
        checar(u"torch enxerga e smi nao responde: NAO diz «sem GPU»",
               u"sem GPU" not in campo and u"USANDO: gpu" in campo,
               campo[:130])
        checar(u"  e diz por que nao mediu",
               u"nao esta no PATH" in campo, campo[:130])

        apertada = _com(torch_ve=1, torch_versao="2.5.1+cu121",
                        torch_cuda="12.1", placas=[APERTADA], driver="528.86")
        checar(u"placa com 2,0 GB livres: a linha AVISA",
               u"ATENCAO" in apertada and u"2.0 GB" in apertada,
               apertada[-120:])
        folgada = _com(torch_ve=1, torch_versao="2.5.1+cu121",
                       torch_cuda="12.1", placas=[FOLGADA], driver="550.00")
        checar(u"  e com 15,1 GB livres NAO avisa",
               u"ATENCAO" not in folgada,
               u"aviso que dispara sempre e aviso que ninguem le")

        sem = _com(torch_versao="2.5.1+cu121", torch_cuda="12.1",
                   smi=u"nvidia-smi respondeu e nao listou placa")
        checar(u"maquina sem placa: diz «sem GPU» e usa CPU",
               u"sem GPU" in sem and u"USANDO: cpu" in sem, sem[:120])
    finally:
        engine.inventario_de_computacao = orig


def teste_refino_na_caixa_da_estrutura():
    print(u"  -- o refino por densidade roda na caixa, e da a MESMA matriz --")
    try:
        import numpy as np
        from scipy import ndimage as ndi
    except Exception as e:
        checar(u"PULADO: sem numpy/scipy", True, str(e))
        return

    class _G(object):
        def __init__(self, sp):
            self.spacing = sp

    def _ingenua(m, hu, g, limiar):
        m = np.asarray(m, bool)
        esp = tuple(abs(float(v)) for v in g.spacing)
        banda = float(M.BANDA_REFINO_MM)
        dist = ndi.distance_transform_edt(~m, sampling=esp)
        cand = m | ((dist <= banda) & (np.asarray(hu) >= float(limiar)))
        rot, _n = ndi.label(cand)
        vivos = sorted(set(np.unique(rot[m & (rot > 0)])) - {0})
        if not vivos:
            return m
        return np.asarray(np.isin(rot, vivos), bool)

    ESP = (5.0, 0.98, 0.98)
    FORMA = (24, 96, 96)
    hu = np.full(FORMA, -1000.0, np.float32)
    hu[:, 20:76, 20:76] = 40.0

    casos = []

    m = np.zeros(FORMA, bool)
    m[6:18, 40:44, 40:44] = True
    hu[m] = 700.0
    viz = np.zeros(FORMA, bool)
    viz[6:18, 44:48, 40:44] = True
    hu[viz] = 650.0
    casos.append((u"vizinho denso encostado", m.copy(), 300.0))

    m2 = np.zeros(FORMA, bool)
    m2[0:3, 20:24, 20:24] = True
    hu[m2] = 700.0
    casos.append((u"colada na borda do volume", m2, 300.0))

    m3 = np.zeros(FORMA, bool)
    m3[10:14, 30:34, 30:34] = True
    hu[m3] = 700.0
    longe = np.zeros(FORMA, bool)
    longe[10:14, 60:64, 60:64] = True
    hu[longe] = 700.0
    casos.append((u"denso longe fica de fora", m3, 300.0))

    m4 = np.zeros(FORMA, bool)
    m4[12, 50, 50] = True
    hu[m4] = 700.0
    casos.append((u"mascara de um voxel", m4, 300.0))

    g = _G(ESP)
    for nome, m, limiar in casos:
        esperado = _ingenua(m, hu, g, limiar)
        obtido = np.asarray(M.refinar_por_hu(m, hu, g, limiar), bool)
        igual = bool(np.array_equal(esperado, obtido))
        dif = 0 if igual else int(np.logical_xor(esperado, obtido).sum())
        checar(u"%s: identico a conta no volume todo" % nome, igual,
               u"%d voxel(is) de diferenca (esperado %d, obtido %d)"
               % (dif, int(esperado.sum()), int(obtido.sum())))

    import ast as _ast
    fonte = io.open(_componentes.fonte("app/engine.py"),
                    encoding="utf-8").read()
    corpo = u""
    for n in _ast.walk(_ast.parse(fonte)):
        if isinstance(n, _ast.FunctionDef) and n.name == "refinar_por_hu":
            corpo = _ast.get_source_segment(fonte, n) or u""
    checar(u"a funcao recorta antes de transformar",
           u"m[fatia]" in corpo and u"hu[fatia]" in corpo,
           u"sem o recorte a conta volta ao volume inteiro")
    checar(u"  e a folga da caixa e em MILIMETROS, nao em voxels",
           u"banda / max(esp[eixo]" in corpo,
           u"a TC e anisotropica: folga em voxels da caixa curta em z")


_FALSO_TS = u'''# -*- coding: utf-8 -*-
import json, os, sys, time
args = sys.argv[1:]
def arg(nome):
    return args[args.index(nome) + 1] if nome in args else None
ENTRADA, SAIDA, TASK = arg("-i"), arg("-o"), arg("--task")
CORPO = "--body_seg" in args
REG = os.environ.get("FALSO_REGISTRO")
if REG:
    with open(REG, "a") as f:
        f.write(json.dumps({"task": TASK, "args": args}) + "\\n")
def linha(t):
    sys.stdout.write(t + "\\n")
    sys.stdout.flush()
def gravar_saida(vazia=False):
    import numpy as np
    import SimpleITK as sitk
    img = sitk.ReadImage(ENTRADA)
    a = np.zeros(sitk.GetArrayFromImage(img).shape, np.uint8)
    if not vazia:
        a[2:6, 3:9, 3:9] = 1
        a[2:6, 9:14, 9:14] = 2
    o = sitk.GetImageFromArray(a)
    o.CopyInformation(img)
    sitk.WriteImage(o, SAIDA)
'''


def _pesos_do_body(base, com_peso=True):
    import radai_tasks as _T
    d = os.path.join(base, _T.DATASET_DO_BODY_PASTA)
    if com_peso:
        cam = os.path.join(d, _T.PESO_DO_BODY)
        os.makedirs(os.path.dirname(cam), exist_ok=True)
        open(cam, "wb").close()
    else:
        os.makedirs(d, exist_ok=True)
    return base


class _TrocaM(object):

    def __init__(self, alvo, **novos):
        self.alvo, self.novos, self.velhos = alvo, novos, {}

    def __enter__(self):
        for k, v in self.novos.items():
            self.velhos[k] = getattr(self.alvo, k)
            setattr(self.alvo, k, v)
        return self

    def __exit__(self, *a):
        for k, v in self.velhos.items():
            setattr(self.alvo, k, v)
        return False


def _rodar_falso(tmp, corpo, task, pesos, device="cpu", recorte=None,
                 mapa=None, timeout_s=60, **trocas):
    import json as _json
    import SimpleITK as _sitk
    falso = os.path.join(tmp, "ts_falso_%d.py" % len(os.listdir(tmp)))
    with io.open(falso, "w", encoding="utf-8") as f:
        f.write(_FALSO_TS + corpo)
    reg = os.path.join(tmp, "reg_%d.jsonl" % len(os.listdir(tmp)))
    vol = _sitk.GetImageFromArray(np.zeros((8, 16, 16), dtype=np.int16))
    vol.SetSpacing((2.0, 2.0, 3.0))
    mapa = mapa or {M._nome_biblioteca(task): {1: "liver", 2: "spleen"}}
    novos = dict(TS_CMD=[sys.executable, falso], TS_CLASS_MAP=mapa,
                 base_eleita=lambda modalidade="CT", **k: None)
    novos.update(trocas)
    velho = {k: os.environ.get(k) for k in ("FALSO_REGISTRO",
                                            "TOTALSEG_WEIGHTS_PATH")}
    os.environ["FALSO_REGISTRO"] = reg
    os.environ["TOTALSEG_WEIGHTS_PATH"] = pesos
    jid = M._job_new()
    try:
        with _TrocaM(M, **novos):
            try:
                r = M.run_ts_task(vol, task, device, jid, timeout_s=timeout_s,
                                  suavizar=False, recorte_no_corpo=recorte)
            except Exception as e:
                r = e
        job = M._job(jid)
        try:
            with io.open(reg, encoding="utf-8") as f:
                regs = [_json.loads(l) for l in f if l.strip()]
        except OSError:
            regs = []
        return r, list(job.get("log") or []), regs, job
    finally:
        for k, v in velho.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        M._job_del(jid)


def teste_o_recorte_no_corpo_no_comando():
    print(u"  -- o recorte no corpo entra no comando so onde deve --")
    tmp = tempfile.mkdtemp(prefix="radai_teste_corpo_")
    com = _pesos_do_body(tempfile.mkdtemp(prefix="radai_teste_pesos_"))
    sem = tempfile.mkdtemp(prefix="radai_teste_pesos_")
    corpo = u"gravar_saida()\n"
    mr = {"total_mr": {1: "liver", 2: "spleen"}}
    try:
        checar(u"o padrao de fabrica do motor e LIGADO",
               M.RECORTE_NO_CORPO_PADRAO is True)
        r, log, reg, job = _rodar_falso(tmp, corpo, "total_v3", com)
        checar(u"TC com o Dataset300: --body_seg no comando",
               reg and "--body_seg" in reg[0]["args"], str(reg[:1])[:200])
        checar(u"  e a linha do log diz «ligado (Dataset300, 6 mm)»",
               [l for l in log if u"TS total_v3 recorte no corpo: ligado "
                u"(Dataset300, 6 mm)" in l], u"\n".join(log[:6]))
        checar(u"  e a serie sai", isinstance(r, dict) and "liver" in r,
               repr(r)[:120])
        checar(u"  e a trava de resolucao continua valendo (sem --fast)",
               reg and not ({"--fast", "--fastest"} & set(reg[0]["args"])))
        checar(u"  e a decisao fica no job",
               (job.get("recorte_no_corpo") or {}).get("total_v3", {})
               .get("estado") == "ligado", str(job.get("recorte_no_corpo")))

        r, log, reg, job = _rodar_falso(tmp, corpo, "total_mr", com, mapa=mr)
        checar(u"RM: sem --body_seg", reg and "--body_seg" not in reg[0]["args"],
               str(reg[:1])[:200])
        checar(u"  e a linha diz «nao se aplica (RM...)»",
               [l for l in log if u"TS total_mr recorte no corpo: nao se "
                u"aplica (RM" in l], u"\n".join(log[:6]))

        r, log, reg, job = _rodar_falso(tmp, corpo, "total_v3", com,
                                        recorte=False)
        checar(u"recorte_no_corpo=False: sem --body_seg",
               reg and "--body_seg" not in reg[0]["args"])
        checar(u"  e a linha diz «desligado» com o porque",
               [l for l in log if u"recorte no corpo: desligado (quem chamou"
                in l], u"\n".join(log[:6]))

        r, log, reg, job = _rodar_falso(tmp, corpo, "total_v3", sem)
        checar(u"TC SEM o Dataset300: sem --body_seg (nao tenta baixar)",
               reg and "--body_seg" not in reg[0]["args"])
        al = [l for l in log if u"! TS total_v3 recorte no corpo: DESLIGADO "
              u"nesta task, faltam os pesos do Dataset300" in l]
        checar(u"  e a linha e de ALERTA, e diz que roda a TC inteira",
               al and u"rodando a TC inteira" in al[0], u"\n".join(log[:6]))
        checar(u"  e a serie sai assim mesmo", isinstance(r, dict) and r,
               repr(r)[:120])
        _pesos_do_body(sem, com_peso=False)
        r, log, reg, job = _rodar_falso(tmp, corpo, "total_v3", sem)
        checar(u"a pasta do 300 SEM o checkpoint tambem nao passa a flag",
               reg and "--body_seg" not in reg[0]["args"]
               and [l for l in log if u"interrompido" in l])

        hgc = {"head_glands_cavities": {1: "parotid_gland_left",
                                        2: "parotid_gland_right"}}
        r, log, reg, job = _rodar_falso(tmp, corpo, "head_glands_cavities",
                                        com, mapa=hgc)
        checar(u"task com localizador proprio: sem --body_seg",
               reg and "--body_seg" not in reg[0]["args"])
        checar(u"  e a linha diz «nao se aplica» e qual localizador",
               [l for l in log if u"recorte no corpo: nao se aplica (a task "
                u"ja recorta no proprio localizador (Dataset298))" in l],
               u"\n".join(log[:6]))

        import radai_tasks as _T
        with _TrocaM(_T, pesos_do_recorte_no_corpo=lambda p=None: (True, u"isca")):
            r, log, reg, job = _rodar_falso(tmp, corpo, "total_v3",
                                            tempfile.mkdtemp(
                                                prefix="radai_teste_pesos_"))
        checar(u"ISCA: sem olhar o peso, a flag vai para a estacao sem o 300",
               reg and "--body_seg" in reg[0]["args"])

        import inspect as _insp
        fonte = _insp.getsource(M.run_ts_task)
        checar(u"o GUARDA: diz que o --body_seg recorta a REGIAO e NAO "
               u"reduz resolucao", u"NAO reduz" in fonte
               and u"recorta a REGIAO" in fonte and u"GUARDA:" in fonte)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


_CORPO_E_PARTES = u'''
if CORPO:
    linha("Generating rough body segmentation...")
    linha("RADAI|rede|dataset=300|ordem=1|device=cpu|resultados=ram")
    linha("Predicting...")
    linha("RADAI|pulso|parte=?|dataset=300|rss_mb=900")
    time.sleep(4)
    linha("  Predicted in 3.10s")
    linha("Rough body segmentation generated in 3.50s")
    linha("  cropping from (16, 16, 8) to (12, 12, 8)")
    time.sleep(3)
linha("Predicting part 1 of 5 ...")
linha("RADAI|rede|dataset=831|ordem=2|device=cpu|resultados=ram")
time.sleep(4)
linha("Predicting part 2 of 5 ...")
linha("RADAI|rede|dataset=832|ordem=3|device=cpu|resultados=ram")
time.sleep(3)
linha("  Predicted in 7.20s")
gravar_saida()
'''


def teste_a_predicao_grosseira_nao_e_a_parte_1():
    print(u"  -- a predicao grosseira nao e a parte 1 de 5 --")
    tmp = tempfile.mkdtemp(prefix="radai_teste_corpo_")
    com = _pesos_do_body(tempfile.mkdtemp(prefix="radai_teste_pesos_"))

    def avaliar(log):
        i_rec = [i for i, l in enumerate(log)
                 if u"| recorte do corpo (6 mm) |" in l]
        i_pronto = [i for i, l in enumerate(log)
                    if u"| recorte do corpo pronto |" in l]
        i_p1 = [i for i, l in enumerate(log) if u"| parte 1/5" in l]
        return {
            "diz_recorte": bool(i_rec),
            "parte1_depois": bool(i_rec and i_pronto and i_p1
                                  and max(i_rec) < min(i_pronto) < min(i_p1)),
            "sem_deslocar": not [l for l in log if u"| parte 3/5" in l],
            "sem_rede_300": not [l for l in log if u"| rede 300" in l],
        }
    try:
        r, log, reg, job = _rodar_falso(tmp, _CORPO_E_PARTES, "total_v3", com)
        checar(u"a serie sai", isinstance(r, dict) and "liver" in r,
               str(r)[-400:] if isinstance(r, Exception) else "")
        a = avaliar(log)
        checar(u"o batimento diz «recorte do corpo (6 mm)» enquanto ela roda",
               a["diz_recorte"], u"\n".join(log[:14]))
        checar(u"  e a parte 1/5 so aparece DEPOIS do recorte pronto",
               a["parte1_depois"], u"\n".join(log[:16]))
        checar(u"  e as partes nao se deslocam (nenhuma «parte 3/5» num "
               u"falso de duas)", a["sem_deslocar"])
        checar(u"  e nenhuma linha diz «rede 300» (o dataset do recorte nao "
               u"vira nome de parte)", a["sem_rede_300"])
        checar(u"a rede do Dataset300 e anunciada como o recorte do corpo",
               [l for l in log if u"rede carregada: dataset 300" in l
                and u"recorte do corpo" in l])
        partes = job.get("partes") or []
        etapas = [p.get("etapa") for p in partes]
        checar(u"o job guarda as etapas: o recorte e as duas partes",
               etapas[:3] == [u"recorte do corpo (6 mm)", u"parte 1/5 (orgaos)",
                              u"parte 2/5 (vertebras)"], str(etapas))
        checar(u"  o recorte e etapa propria (parte None), e a parte 1 e a 1",
               len(partes) >= 2 and partes[0].get("parte") is None
               and partes[1].get("parte") == 1 and partes[1].get("de") == 5,
               str(partes[:2]))
        checar(u"  com o dataset de cada uma e um tempo medido",
               len(partes) >= 3 and partes[0].get("dataset") == "300"
               and partes[1].get("dataset") == "831"
               and all(p.get("segundos", -1) >= 0 for p in partes)
               and partes[0]["segundos"] >= 2.0, str(partes))
        checar(u"  e a ultima parte fecha no «Predicted in» (nao incompleta)",
               len(partes) >= 3 and not partes[2].get("incompleta"),
               str(partes[2:3]))
        checar(u"o plano do job existe mesmo em CPU (o registro le dali)",
               (job.get("plano") or {}).get("modo") == "cpu"
               and "total_v3" in (job.get("planos") or {}),
               str(job.get("plano")))
        checar(u"o que a biblioteca disse do recorte chega ao log (o "
               u"«cropping from» e o tempo dele)",
               [l for l in log if u"cropping from" in l]
               and [l for l in log if u"Rough body segmentation generated"
                    in l], u"\n".join(log[-10:]))

        Base = M._LeitorDoLogTS

        class PelaOrdem(Base):
            def _radai(self, t, agora):
                Base._radai(self, t, agora)
                if t.startswith("RADAI|rede|"):
                    kv = dict(c.split("=", 1) for c in t.split("|")[2:]
                              if "=" in c)
                    self.parte = (int(kv.get("ordem", 0)), 5)
        r2, log2, _, _ = _rodar_falso(tmp, _CORPO_E_PARTES, "total_v3", com,
                                      _LeitorDoLogTS=PelaOrdem)
        a2 = avaliar(log2)
        checar(u"ISCA: pela `ordem` da rede, o recorte conta como a parte 1 "
               u"e as partes se deslocam",
               not (a2["parte1_depois"] and a2["sem_deslocar"]),
               u"\n".join(log2[:16]))

        class SemRecorte(Base):
            @property
            def recorte(self):
                return None

            @recorte.setter
            def recorte(self, v):
                pass
        r3, log3, _, job3 = _rodar_falso(tmp, _CORPO_E_PARTES, "total_v3",
                                         com, _LeitorDoLogTS=SemRecorte)
        a3 = avaliar(log3)
        checar(u"ISCA: sem o estado do recorte, o batimento diz «rede 300» e "
               u"nao diz o recorte",
               not a3["diz_recorte"] and not a3["sem_rede_300"],
               u"\n".join(log3[:12]))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _leitor_com_relogio(tmp):
    cam = os.path.join(tmp, "ts_%d.log" % len(os.listdir(tmp)))
    io.open(cam, "wb").close()

    def dar(leitor, agora, *linhas):
        with io.open(cam, "ab") as f:
            f.write((u"\n".join(linhas) + u"\n").encode("utf-8"))
        leitor.ler(agora)
    return cam, dar


_CORPO_E_REDE_UNICA = u'''
if CORPO:
    linha("Generating rough body segmentation...")
    linha("Predicting...")
    linha("RADAI|rede|dataset=300|ordem=1|device=cpu|resultados=ram")
    time.sleep(3)
    linha("  Predicted in 2.90s")
    linha("Rough body segmentation generated in 3.20s")
    linha("  cropping from (16, 16, 8) to (12, 12, 8)")
linha("Predicting...")
linha("RADAI|rede|dataset=527|ordem=2|device=cpu|resultados=ram")
time.sleep(7)
linha("  Predicted in 7.00s")
gravar_saida()
'''


def teste_a_rede_unica_recortada_tem_etapa_propria():
    print(u"  -- a rede unica recortada tem etapa propria --")
    tmp = tempfile.mkdtemp(prefix="radai_teste_rede_unica_")
    Base = M._LeitorDoLogTS

    def correr(classe=Base, envelope=True, corpo=True):
        cam, dar = _leitor_com_relogio(tmp)
        L = classe(cam, agora=0)
        rede = [u"RADAI|rede|dataset=300|ordem=1|device=cpu|resultados=ram"]
        onde = {}
        if corpo:
            dar(L, 0, u"Generating rough body segmentation...",
                u"Resampling...", u"Predicting...",
                *(rede if envelope else []))
            onde["recorte"] = L.onde("breasts")
            dar(L, 100, u"  Predicted in 100.00s")
            onde["recorte_predito"] = L.onde("breasts")
            dar(L, 130, u"Rough body segmentation generated in 130.00s",
                u"  cropping from (512, 512, 97) to (400, 300, 97)")
            onde["pronto"] = L.onde("breasts")
        dar(L, 140, u"Resampling...", u"Predicting...")
        onde["predizendo"] = L.onde("breasts")
        if envelope:
            dar(L, 150, u"RADAI|rede|dataset=527|ordem=2|device=cpu|"
                        u"resultados=ram")
        onde["rede"] = L.onde("breasts")
        linha10 = M._linha_do_batimento("breasts", L, 600, "cpu", 600)
        dar(L, 750, u"  Predicted in 610.00s")
        return L, onde, linha10

    def etapas_no_job(L):
        jid = M._job_new()
        try:
            M._guardar_etapas(jid, "breasts", L, 1, "cpu")
            return M._job(jid).get("partes") or []
        finally:
            M._job_del(jid)

    try:
        L, onde, l10 = correr()
        checar(u"durante a predicao do corpo: «recorte do corpo (6 mm)»",
               onde["recorte"] == u"recorte do corpo (6 mm)"
               and onde["recorte_predito"] == u"recorte do corpo (6 mm)",
               str(onde))
        checar(u"  entre o recorte e a rede da task: «recorte do corpo pronto»",
               onde["pronto"] == u"recorte do corpo pronto", str(onde))
        checar(u"  e a rede da task, depois: «rede 527» (e nao «pronto»)",
               onde["rede"] == u"rede 527", str(onde))
        checar(u"a linha dos 10 min diz «rede 527», e nao o «pronto»",
               u"| rede 527 |" in l10 and u"pronto" not in l10, l10)
        p = etapas_no_job(L)
        checar(u"o job guarda o recorte E a rede da task",
               [x.get("etapa") for x in p] == [u"recorte do corpo (6 mm)",
                                               u"rede 527"], str(p))
        checar(u"  a rede com o tempo da inferencia, e sem numero de parte",
               len(p) == 2 and p[1].get("segundos") == 610.0
               and p[1].get("parte") is None and p[1].get("dataset") == "527"
               and not p[1].get("incompleta"), str(p[1:]))
        checar(u"  e o recorte com o tempo que a BIBLIOTECA mede (130 s, ate "
               u"«Rough body segmentation generated»)",
               p and p[0].get("segundos") == 130.0
               and p[0].get("dataset") == "300", str(p[:1]))

        L2, onde2, l102 = correr(envelope=False)
        checar(u"sem o envelope: «rede unica», e nao «pronto»",
               onde2["rede"] == u"rede unica" and u"| rede unica |" in l102,
               l102)
        checar(u"  e a etapa vai ao job do mesmo jeito",
               [x.get("etapa") for x in etapas_no_job(L2)]
               == [u"recorte do corpo (6 mm)", u"rede unica"])
        L3, onde3, l103 = correr(corpo=False)
        checar(u"sem o recorte: «rede 527» e a etapa dela no job",
               onde3["rede"] == u"rede 527" and [x.get("etapa") for x in
                                                 etapas_no_job(L3)]
               == [u"rede 527"], str(onde3))

        class ProntoAntes(Base):
            def onde(self, task):
                if self.recorte == "feito" and not self.parte:
                    return u"recorte do corpo pronto"
                return Base.onde(self, task)
        _, oi, li = correr(ProntoAntes)
        checar(u"ISCA: com o «pronto» antes da rede, os 10 min dizem «pronto»",
               not (u"| rede 527 |" in li and u"pronto" not in li), li)

        class SemEtapaDeRede(Base):
            def _abrir_etapa(self, tipo, agora, parte=None, dataset=None):
                if tipo == "rede":
                    self.rede_unica = True
                    return
                Base._abrir_etapa(self, tipo, agora, parte, dataset)
        Li, _, _ = correr(SemEtapaDeRede)
        checar(u"ISCA: sem a etapa de rede, o job fica so com o recorte",
               [x.get("etapa") for x in etapas_no_job(Li)]
               == [u"recorte do corpo (6 mm)"])

        class FechaNoPredito(Base):
            def _saida_ts(self, t, agora):
                if u"Predicted in" in t and self.recorte == "rodando":
                    self._fechar_etapa(agora)
                Base._saida_ts(self, t, agora)
        Li3, _, _ = correr(FechaNoPredito)
        pi3 = etapas_no_job(Li3)
        checar(u"ISCA: fechando no «Predicted in», o recorte mede 100 s e nao "
               u"os 130 da biblioteca", pi3 and pi3[0].get("segundos") == 100.0,
               str(pi3[:1]))

        com = _pesos_do_body(tempfile.mkdtemp(prefix="radai_teste_pesos_"))
        r, log, reg, job = _rodar_falso(tmp, _CORPO_E_REDE_UNICA, "breasts",
                                        com, BATIMENTO_TS_S=1)
        checar(u"a serie de rede unica recortada sai",
               isinstance(r, dict),
               str(r)[-300:] if isinstance(r, Exception) else "")
        checar(u"  com --body_seg no comando",
               reg and "--body_seg" in reg[0]["args"], str(reg[:1])[:200])
        bat = [l for l in log if u"TS breasts |" in l]
        i_rede = [i for i, l in enumerate(bat) if u"| rede 527 |" in l]
        checar(u"  o batimento chega a «rede 527»", i_rede,
               u"\n".join(bat[-6:]))
        checar(u"  e, dali em diante, nenhuma linha diz «recorte do corpo "
               u"pronto»", i_rede and not [l for l in bat[min(i_rede):]
                                           if u"pronto" in l],
               u"\n".join(bat[-6:]))
        et = [x.get("etapa") for x in (job.get("partes") or [])]
        checar(u"  e o job tem o recorte e a rede 527",
               et == [u"recorte do corpo (6 mm)", u"rede 527"], str(et))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


_PLACA_CAI_NO_FALSO = u'''
if arg("--device") == "gpu":
    linha("Predicting part 2 of 5 ...")
    sys.stderr.write("RuntimeError: CUDA error: an illegal memory access "
                     "was encountered\\n")
    sys.stderr.flush()
    sys.exit(1)
gravar_saida()
'''


def teste_o_recuo_para_a_cpu_fica_no_job():
    print(u"  -- o recuo para a CPU fica no job --")
    tmp = tempfile.mkdtemp(prefix="radai_teste_recuo_")
    com = _pesos_do_body(tempfile.mkdtemp(prefix="radai_teste_pesos_"))
    plano = {"modo": "gpu_resultado_na_cpu", "motivo": u"gpu: dublado",
             "indice": 0, "capacidade": "6.1"}
    try:
        r, log, reg, job = _rodar_falso(
            tmp, _PLACA_CAI_NO_FALSO, "total_v3", com, device="gpu",
            recorte=False, plano_de_dispositivo=lambda *a, **k: dict(plano))
        checar(u"a serie sai (a CPU refez)", isinstance(r, dict) and r,
               str(r)[-300:] if isinstance(r, Exception) else "")
        checar(u"  em duas tentativas, gpu e depois cpu",
               [x["args"][x["args"].index("--device") + 1] for x in reg]
               == ["gpu", "cpu"], str([x["args"][-6:] for x in reg]))
        pl = job.get("plano") or {}
        checar(u"o `modo` do plano do job e CPU -- o que VALEU",
               pl.get("modo") == "cpu", str(pl)[:240])
        checar(u"  e o que o plano tinha escolhido fica em `modo_do_plano`",
               pl.get("modo_do_plano") == "gpu_resultado_na_cpu",
               str(pl)[:240])
        rc = pl.get("recuo_cpu") or {}
        checar(u"  com onde a placa caiu, a prova e quanto ela durou",
               u"parte 2/5" in (rc.get("onde") or u"")
               and u"CUDA error" in (rc.get("prova") or u"")
               and isinstance(rc.get("segundos_na_placa"), float), str(rc))
        checar(u"  e o motivo diz que a task foi refeita em CPU",
               u"refeita INTEIRA em CPU" in (pl.get("motivo") or u"")
               and u"gpu: dublado" in (pl.get("motivo") or u""),
               pl.get("motivo"))
        checar(u"  e o plano POR TASK diz o mesmo",
               ((job.get("planos") or {}).get("total_v3") or {})
               .get("modo") == "cpu", str(job.get("planos"))[:200])
        pts = job.get("partes") or []
        checar(u"  e a etapa da placa fica no job, incompleta, como gpu",
               [p for p in pts if p.get("tentativa") == 1
                and p.get("dispositivo") == "gpu" and p.get("incompleta")],
               str(pts))

        jid = M._job_new()
        try:
            M._anotar_no_job(jid, "total_v3", plano=dict(plano))
            M._anotar_no_job(jid, "head_glands_cavities", plano=dict(plano))
            M._anotar_no_job(jid, "head_glands_cavities",
                             recuo_cpu={"onde": u"rede 775", "prova": u"x"})
            j = M._job(jid)
            checar(u"recuo na SEGUNDA task: o plano da base fica o da placa",
                   j["plano"]["modo"] == "gpu_resultado_na_cpu"
                   and j["plano"]["task"] == "total_v3"
                   and j["planos"]["head_glands_cavities"]["modo"] == "cpu"
                   and j["planos"]["total_v3"]["modo"]
                   == "gpu_resultado_na_cpu", str(j.get("planos"))[:240])
        finally:
            M._job_del(jid)

        _anotar = M._anotar_no_job

        def sem_recuo(*a, **k):
            k.pop("recuo_cpu", None)
            return _anotar(*a, **k)
        r2, log2, reg2, job2 = _rodar_falso(
            tmp, _PLACA_CAI_NO_FALSO, "total_v3", com, device="gpu",
            recorte=False, plano_de_dispositivo=lambda *a, **k: dict(plano),
            _anotar_no_job=sem_recuo)
        checar(u"ISCA: sem a anotacao, a serie feita em CPU fica como de placa",
               (job2.get("plano") or {}).get("modo") == "gpu_resultado_na_cpu",
               str(job2.get("plano"))[:200])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def teste_o_plano_diz_que_o_recorte_reduz_o_volume():
    print(u"  -- o plano diz que o recorte reduz o volume real --")
    tmp = tempfile.mkdtemp(prefix="radai_teste_corpo_")
    com = _pesos_do_body(tempfile.mkdtemp(prefix="radai_teste_pesos_"))
    plano = {"modo": "gpu_resultado_na_cpu", "motivo": u"gpu: dublado",
             "indice": 0, "capacidade": "6.1"}
    try:
        r, log, reg, job = _rodar_falso(
            tmp, u"gravar_saida()\n", "total_v3", com, device="gpu",
            plano_de_dispositivo=lambda *a, **k: dict(plano))
        d = [l for l in log if u"TS total_v3 dispositivo:" in l]
        checar(u"o motivo logado diz que o recorte reduz o volume real",
               d and u"com o recorte no corpo o volume real e menor" in d[0]
               and u"gpu: dublado" in d[0], d[0] if d else u"")
        checar(u"  e o plano do job e o mesmo que foi logado",
               (job.get("plano") or {}).get("modo") == "gpu_resultado_na_cpu"
               and u"volume real e menor" in (job.get("plano") or {})
               .get("motivo", u""), str(job.get("plano"))[:160])
        r, log, reg, job = _rodar_falso(
            tmp, u"gravar_saida()\n", "total_v3", com, device="gpu",
            recorte=False, plano_de_dispositivo=lambda *a, **k: dict(plano))
        d = [l for l in log if u"TS total_v3 dispositivo:" in l]
        checar(u"ISCA: sem o recorte, o motivo nao fala dele",
               d and u"volume real e menor" not in d[0], d[0] if d else u"")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


_CORPO_VAZIO = u'''
if CORPO:
    linha("Generating rough body segmentation...")
    linha("Rough body segmentation generated in 1.00s")
    linha("INFO: Crop is empty. Returning empty segmentation.")
    gravar_saida(vazia=True)
else:
    gravar_saida()
'''


def teste_o_recorte_vazio_refaz_sem_ele():
    print(u"  -- o recorte vazio refaz a task sem ele --")
    tmp = tempfile.mkdtemp(prefix="radai_teste_corpo_")
    com = _pesos_do_body(tempfile.mkdtemp(prefix="radai_teste_pesos_"))
    try:
        r, log, reg, job = _rodar_falso(tmp, _CORPO_VAZIO, "total_v3", com)
        checar(u"a serie sai", isinstance(r, dict) and "liver" in r,
               repr(r)[:120])
        checar(u"  em duas tentativas: com a flag, e depois sem",
               [("--body_seg" in x["args"]) for x in reg] == [True, False],
               str([("--body_seg" in x["args"]) for x in reg]))
        checar(u"  e o log diz que o recorte saiu VAZIO e que refez sem ele",
               [l for l in log if u"o recorte do corpo saiu VAZIO" in l
                and u"SEM o recorte" in l], u"\n".join(log[-8:]))
        _rc = (job.get("recorte_no_corpo") or {}).get("total_v3") or {}
        checar(u"  e o job diz o que VALEU: desligado, pela mascara vazia",
               _rc.get("estado") == "desligado" and u"vazia" in
               (_rc.get("motivo") or u""), str(_rc))
        r2, log2, reg2, _ = _rodar_falso(tmp, _CORPO_VAZIO, "total_v3", com,
                                         _RECORTE_VAZIO="frase-que-nao-casa")
        checar(u"ISCA: sem reconhecer a frase, a serie cai",
               isinstance(r2, RuntimeError) and u"nenhuma estrutura" in str(r2),
               repr(r2)[:140])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def teste_a_observacao_de_quem_chama_chega_ao_dicom():
    print(u"  -- a observacao de quem chama chega ao DICOM --")
    import pydicom
    tmp = tempfile.mkdtemp(prefix="radai_teste_")
    try:
        serie = os.path.join(tmp, "serie")
        escreve_serie(serie, "FANTOMA_OBS", datetime(2026, 9, 23, 10, 0), 24)
        forma = (24, 128, 128)
        zz, yy, xx = np.ogrid[0:forma[0], 0:forma[1], 0:forma[2]]

        def bola(cz, cy, cx, r):
            return (((zz - cz) * 3.0) ** 2 + ((yy - cy) * 2.0) ** 2
                    + ((xx - cx) * 2.0) ** 2 <= r * r)
        masks = {"kidney_right": bola(12, 90, 64, 14.0),
                 "liver": bola(12, 64, 30, 16.0)}
        texto_rim = u"numero 7 e o rotulo do modelo — nivel nao atribuido"
        obs = {"kidney_right": texto_rim, "liver": u"so a observacao",
               "estrutura_que_nao_existe": u"nao sai"}
        L = []
        caminho, nomes = M.build_rtstruct(serie, masks, tasks=["total"],
                                          versao_worker="t", log=L.append,
                                          observacoes=obs)
        ds = pydicom.dcmread(caminho)
        por_num = dict((int(r.ROINumber), str(r.ROIName))
                       for r in ds.StructureSetROISequence)
        desc = dict((por_num.get(int(o.ReferencedROINumber)),
                     str(getattr(o, "ROIObservationDescription", "") or ""))
                    for o in ds.RTROIObservationsSequence)
        rim, fig = desc.get(nomes.get("kidney_right"), u""), \
            desc.get(nomes.get("liver"), u"")
        checar(u"o rim leva o laudo de densidade E a observacao",
               u"mediana" in rim and u"nivel nao atribuido" in rim, rim[:200])
        checar(u"  o laudo primeiro, a observacao depois, cada um com o seu "
               u"«RadAI:»", rim.find(u"mediana") < rim.find(u"nivel nao")
               and rim.count(u"RadAI:") >= 2, rim[:200])
        _dela = rim[rim.find(u"numero 7"):]
        checar(u"  e o travessao foi transliterado (latin-1, sem «?»)",
               u"—" not in _dela and u" - " in _dela
               and u"?" not in _dela, _dela[:120])
        checar(u"o figado, sem laudo, leva so a observacao",
               fig == u"RadAI: so a observacao", fig)
        checar(u"a chave que nao virou ROI e dita no log",
               [m for m in L if u"observacao sem ROI" in m
                and u"estrutura_que_nao_existe" in m], u" | ".join(L)[-200:])
        longa = u"inicio da observacao " + u"x" * 900 + u" FIM-DA-OBSERVACAO"
        caminho2, nomes2 = M.build_rtstruct(serie, masks, tasks=["total"],
                                            versao_worker="t",
                                            observacoes={"kidney_right": longa})
        ds2 = pydicom.dcmread(caminho2)
        por_num2 = dict((int(r.ROINumber), str(r.ROIName))
                        for r in ds2.StructureSetROISequence)
        rim2 = [str(o.ROIObservationDescription)
                for o in ds2.RTROIObservationsSequence
                if por_num2.get(int(o.ReferencedROINumber))
                == nomes2.get("kidney_right")][0]
        checar(u"a observacao longa chega INTEIRA, e o campo cabe em 1024",
               rim2.endswith(u"FIM-DA-OBSERVACAO") and len(rim2) <= 1024,
               u"%d caracteres | ...%s" % (len(rim2), rim2[-40:]))
        checar(u"  e o laudo de antes foi encurtado com «...», e nao sumiu",
               rim2.startswith(u"RadAI:") and u"..." in rim2, rim2[:120])
        ingenua = (rim + u" RadAI: " + longa)[:1024]
        checar(u"ISCA: a juncao ingenua perderia o fim da observacao",
               not ingenua.endswith(u"FIM-DA-OBSERVACAO"), ingenua[-40:])
        caminho3, nomes3 = M.build_rtstruct(serie, masks, tasks=["total"],
                                            versao_worker="t")
        ds3 = pydicom.dcmread(caminho3)
        checar(u"sem `observacoes`, nenhuma ROI leva texto de quem chama",
               not [o for o in ds3.RTROIObservationsSequence
                    if u"nivel nao atribuido" in str(
                        getattr(o, "ROIObservationDescription", ""))])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def teste_a_citacao_dos_niveis_e_do_artigo():
    print(u"  -- a citacao dos niveis cervicais e a do artigo --")
    fonte = io.open(_componentes.fonte("app/engine.py"), encoding="utf-8").read()
    checar(u"o ROTULO_MOTOR dos niveis diz Weissmann et al. 2023",
           u'"hnlnl": "Radioterapia.AI / HNLNL (Weissmann et al. 2023)"'
           in fonte)
    checar(u"  e cabe nos 64 do ROIGenerationDescription",
           len(u"Radioterapia.AI / HNLNL (Weissmann et al. 2023)") <= 64)
    import re as _re
    vivas = [l for l in fonte.splitlines()
             if _re.search(u"Putz et al", l)]
    checar(u"nenhuma linha do motor cita «Putz et al.» como o artigo",
           not vivas, u" | ".join(vivas)[:200])


def _componentes_distantes_de_antes(masks, grade,
                                    fracao=None, distancia_mm=None):
    from scipy import ndimage
    fracao = M.FRACAO_DE_ILHA if fracao is None else fracao
    distancia_mm = (M.DISTANCIA_DE_ILHA_MM if distancia_mm is None
                    else distancia_mm)
    esp = getattr(grade, "spacing", (1.0, 1.0, 1.0))
    fora = []
    for nome in sorted(masks):
        try:
            m = masks[nome]
            if m is None or not m.any():
                continue
            rot, quantos = ndimage.label(m)
            if quantos < 2:
                continue
            tam = ndimage.sum(m, rot, range(1, quantos + 1))
            total = float(tam.sum())
            maior = int(tam.argmax()) + 1
            centros = ndimage.center_of_mass(m, rot, range(1, quantos + 1))
            c0 = centros[maior - 1]
            pior_d, pior_f, n_ilhas = 0.0, 0.0, 0
            for k in range(1, quantos + 1):
                if k == maior:
                    continue
                f = float(tam[k - 1]) / total if total else 0.0
                if f > fracao:
                    continue
                c = centros[k - 1]
                d = sum(((c[i] - c0[i]) * esp[i]) ** 2
                        for i in range(len(esp))) ** 0.5
                if d < distancia_mm:
                    continue
                n_ilhas += 1
                if d > pior_d:
                    pior_d, pior_f = d, f
            if n_ilhas:
                fora.append((nome, n_ilhas, round(pior_d, 1),
                             round(pior_f, 4)))
        except Exception:
            continue
    return fora


def _implausiveis_de_antes(masks, grade):
    import radai_geom
    fora, cortadas = [], []
    for nome in sorted(masks):
        try:
            m = masks[nome]
            base = str(nome).split(":")[-1]
            piso = M._nomes.procurar(M.VOLUME_MINIMO_CM3, base,
                                     M.VOLUME_MINIMO_GERAL_CM3)
            v = radai_geom.volume_cm3(m, grade)
            if v >= piso:
                continue
            if M.toca_a_borda(m):
                cortadas.append(nome)
            else:
                fora.append((nome, round(v, 2), piso))
        except Exception:
            continue
    return fora, cortadas


def _mascaras_das_conferencias():
    rng = np.random.default_rng(20260925)
    sh = (40, 90, 90)

    def cx(z0, z1, y0, y1, x0, x1):
        m = np.zeros(sh, dtype=bool)
        m[z0:z1, y0:y1, x0:x1] = True
        return m

    masks = {
        "liver": cx(10, 30, 10, 50, 10, 50),
        "stomach": cx(28, 38, 10, 50, 10, 50),
        "spleen": cx(10, 20, 55, 70, 60, 80),
        "kidney_left": cx(0, 12, 60, 80, 10, 30),
        "adrenal_gland_left": cx(12, 13, 60, 62, 10, 12),
        "pancreas": cx(5, 10, 40, 50, 40, 60),
        "lung_upper_lobe_left": cx(20, 34, 60, 88, 55, 89),
        "lung_lower_lobe_left": cx(33, 40, 60, 88, 55, 89),
    }
    masks["lung_left"] = (masks["lung_upper_lobe_left"]
                          | masks["lung_lower_lobe_left"])
    olho = cx(20, 26, 20, 30, 20, 30)
    olho[0:2, 80:82, 80:82] = True
    olho[27:28, 24:26, 24:26] = True
    masks["eyeball_left"] = olho
    gemeos = cx(5, 9, 5, 9, 5, 9) | cx(30, 34, 70, 74, 70, 74)
    gemeos[20, 45, 45] = True
    masks["eyeball_right"] = gemeos
    rala = (rng.random(sh) < 0.004).astype(np.uint8) * 3
    rala[15:25, 30:40, 60:70] = 3
    masks["small_bowel"] = rala
    return masks


def teste_as_conferencias_na_caixa_sao_as_de_antes():
    print(u"  -- as conferencias na caixa sao as de antes (spec F3) --")
    import radai_geom
    g = radai_geom.Grade((2.5, 0.9, 0.9))
    masks = _mascaras_das_conferencias()
    antes = dict((k, np.asarray(v).copy()) for k, v in masks.items())

    ref_c = _componentes_distantes_de_antes(masks, g)
    novo_c = M.componentes_distantes(masks, g)
    checar(u"componentes_distantes: igual ao de antes (volume inteiro)",
           novo_c == ref_c and len(ref_c) >= 1, u"%s | %s" % (novo_c, ref_c))
    ref_i = _implausiveis_de_antes(masks, g)
    checar(u"implausiveis: igual ao de antes",
           M.implausiveis(masks, g) == ref_i and ref_i[0],
           u"%s | %s" % (M.implausiveis(masks, g), ref_i))
    lento = radai_geom.Caixas(masks, folga=None)
    for rot, kw in ((u"FULL", {"construcoes": {}}),
                    (u"sem construcoes", {}),
                    (u"estrito, selecao", {"construcoes": {}, "estrito": True,
                                           "so": set(["liver", "stomach",
                                                      "lung_left",
                                                      "kidney_left"])})):
        r1 = M.sobreposicoes(masks, g, **kw)
        r2 = M.sobreposicoes(masks, g, caixas=lento, **kw)
        checar(u"sobreposicoes (%s): na caixa == no volume inteiro" % rot,
               r1 == r2 and r1, u"%s | %s" % (r1, r2))
    cxs = radai_geom.Caixas(masks)
    checar(u"a caixa justa e a de `engine._caixa` em toda estrutura",
           all(cxs.justa(k) == M._caixa(M._bool_seguro(masks[k]))
               for k in masks))
    checar(u"e nenhuma conferencia mexeu nas mascaras",
           all(np.array_equal(antes[k], masks[k]) for k in masks))

    class _CaixaCurta(radai_geom.Caixas):
        def _calcular(self, nome):
            orig, m, cx, n, lim = radai_geom.Caixas._calcular(self, nome)
            if cx is not None:
                cx = (slice(cx[0].start, max(cx[0].start + 1,
                                             cx[0].stop - 2)),) + cx[1:]
                n = int(m[cx].sum())
            self._memo[nome] = (orig, m, cx, n, lim)
            return self._memo[nome]
    checar(u"ISCA: a caixa curta muda as pecas soltas",
           M.componentes_distantes(masks, g,
                                   caixas=_CaixaCurta(masks)) != ref_c)
    checar(u"ISCA: e muda o piso de volume",
           M.implausiveis(masks, g, caixas=_CaixaCurta(masks)) != ref_i)

    class _JustaSemFim(radai_geom.Caixas):
        def justa(self, nome):
            j = radai_geom.Caixas.justa(self, nome)
            return None if j is None else [(a, b - 1) for a, b in j]
    r_ok = M.sobreposicoes(masks, g, construcoes={})
    r_isca = M.sobreposicoes(masks, g, construcoes={},
                             caixas=_JustaSemFim(masks))
    checar(u"ISCA: a caixa justa sem o +1 do fim muda a sobreposicao",
           r_isca != r_ok, u"%s | %s" % (r_isca, r_ok))
    from scipy import ndimage
    rng = np.random.default_rng(0)
    certos, depois_difere, casos = 0, 0, 0
    for _t in range(200):
        sub = rng.random((7, 9, 11)) < 0.3
        rot, n = ndimage.label(sub)
        if n == 0:
            continue
        origem = tuple(int(v) for v in rng.integers(50, 300, size=3))
        grande = np.zeros(tuple(o + s + 2 for o, s in zip(origem, sub.shape)),
                          bool)
        grande[origem[0]:origem[0] + 7, origem[1]:origem[1] + 9,
               origem[2]:origem[2] + 11] = sub
        rg, ng = ndimage.label(grande)
        ref = [tuple(c) for c in
               ndimage.center_of_mass(grande, rg, range(1, ng + 1))]
        casos += 1
        certos += ([tuple(c) for c in M._centros_na_caixa(
            sub, rot, range(1, n + 1), origem)] == ref)
        local = ndimage.center_of_mass(sub, rot, range(1, n + 1))
        depois_difere += ([tuple(c[i] + origem[i] for i in range(3))
                           for c in local] != ref)
    checar(u"o centro na caixa e BIT A BIT o do volume inteiro (%d de %d)"
           % (certos, casos), certos == casos and casos > 150)
    checar(u"ISCA: o centro local somado a origem depois difere em %d"
           % depois_difere, depois_difere > 0)


def _limpar_fora_do_corpo_de_antes(masks, externo, grade, log=None):
    from scipy import ndimage
    tirados = []
    externo = np.asarray(externo, dtype=bool)
    for nome in sorted(masks):
        if nome in ("Skin", "ChestWall_L", "ChestWall_R"):
            continue
        m = np.asarray(masks[nome])
        m = m if m.dtype == bool else m.astype(bool)
        if not m.any():
            continue
        fora = m & ~externo
        if not fora.any():
            continue
        rot, n = ndimage.label(m)
        if n <= 0:
            continue
        dentro = np.bincount(rot[externo].ravel(), minlength=n + 1)
        soltos = [i for i in range(1, n + 1) if dentro[i] == 0]
        if not soltos:
            continue
        sai = np.isin(rot, soltos)
        novo = m & ~sai
        vox = int(sai.sum())
        if not novo.any():
            if log:
                log("vazia %s" % nome)
            del masks[nome]
            tirados.append((nome, len(soltos), vox))
            continue
        masks[nome] = novo
        tirados.append((nome, len(soltos), vox))
    return tirados


def teste_a_limpeza_do_ar_na_caixa_e_a_de_antes():
    print(u"  -- a limpeza do ar na caixa e a de antes (spec F3) --")
    import radai_geom
    g = radai_geom.Grade((2.0, 1.0, 1.0))
    Z, Y, X = 40, 90, 90
    yy, xx = np.ogrid[:Y, :X]
    corpo = ((yy - 45) ** 2 + (xx - 45) ** 2) <= 32 ** 2
    externo = np.broadcast_to(corpo, (Z, Y, X)).copy()
    vol = np.where(externo, 40.0, -1000.0).astype("float32")
    rng = np.random.default_rng(9)
    masks = {}
    for i in range(14):
        m = np.zeros((Z, Y, X), bool)
        z, y, x = (int(rng.integers(2, Z - 6)), int(rng.integers(20, 60)),
                   int(rng.integers(20, 60)))
        m[z:z + 5, y:y + 9, x:x + 9] = True
        if i % 2:
            m[int(rng.integers(0, Z)), int(rng.integers(0, 6)),
              int(rng.integers(0, 6))] = True
        if i % 5 == 0:
            m[Z - 1, Y - 1, X - 2:X] = True
        masks["s%02d" % i] = m
    so_fora = np.zeros((Z, Y, X), bool)
    so_fora[1:3, 1:3, 1:3] = True
    masks["so_no_ar"] = so_fora
    masks["uint8"] = (masks["s01"] * 3).astype(np.uint8)
    a = dict((k, v.copy()) for k, v in masks.items())
    b = dict((k, v.copy()) for k, v in masks.items())
    la, lb = [], []
    ta = M.limpar_fora_do_corpo(a, vol, g, externo=externo, log=la.append)
    tb = _limpar_fora_do_corpo_de_antes(b, externo, g, log=lb.append)
    checar(u"o que saiu e o mesmo do de antes (%d estruturas limpas)"
           % len(ta), ta == tb and len(ta) >= 4, u"%s | %s" % (ta, tb))
    checar(u"  e as mascaras sao bit a bit as mesmas (e as mesmas sairam)",
           set(a) == set(b)
           and all(np.array_equal(np.asarray(a[k]), np.asarray(b[k]))
                   for k in a), u"%s | %s" % (sorted(set(a) ^ set(b)), ""))
    checar(u"  e a que so tem ar SAIU nos dois (R3)",
           "so_no_ar" not in a and "so_no_ar" not in b and len(lb) == 1)
    velho = M.radai_geom._limites if hasattr(M, "radai_geom") else None
    import radai_geom as _RG
    orig = _RG._limites

    def _curta(mask):
        lim = orig(mask)
        if lim is None:
            return None
        return ((lim[0][0], max(lim[0][0], lim[0][1] - 1)),) + tuple(lim[1:])
    c = dict((k, v.copy()) for k, v in masks.items())
    _RG._limites = _curta
    try:
        tc = M.limpar_fora_do_corpo(c, vol, g, externo=externo)
    finally:
        _RG._limites = orig
    checar(u"ISCA: a caixa sem o ultimo corte muda a limpeza",
           tc != tb, u"%s | %s" % (tc, tb))
    del velho


def teste_o_teto_reaproveita_o_raio():
    print(u"  -- o teto reaproveita o raio de estrutura_fina (spec F3) --")
    import radai_geom
    g = radai_geom.Grade((3.0, 0.8, 0.8))
    rng = np.random.default_rng(3)
    ruins = []
    for i in range(25):
        m = np.zeros((20, 60, 60), bool)
        c = [int(v) for v in rng.integers(4, 16, size=1)] + \
            [int(v) for v in rng.integers(10, 50, size=2)]
        r = [int(v) for v in rng.integers(1, 8, size=3)]
        m[max(0, c[0] - r[0]):c[0] + r[0], max(0, c[1] - r[1]):c[1] + r[1],
          max(0, c[2] - r[2]):c[2] + r[2]] = True
        _f, raio = M.estrutura_fina(m, g)
        if M.teto_de_suavizacao(m, g, raio=raio) != \
                M.teto_de_suavizacao(m, g):
            ruins.append(i)
    checar(u"teto com o raio ja medido == teto medido de novo (25 formas)",
           not ruins, str(ruins))
    m = np.zeros((10, 20, 20), bool)
    m[2:8, 5:15, 5:15] = True
    checar(u"raio 0.0 (nao medido) refaz a medida, e nao devolve teto zero",
           M.teto_de_suavizacao(m, g, raio=0.0) == M.teto_de_suavizacao(m, g)
           and M.teto_de_suavizacao(m, g) > 0)
    checar(u"ISCA: o raio de outra estrutura muda o teto",
           M.teto_de_suavizacao(m, g, raio=9.0) != M.teto_de_suavizacao(m, g))


def teste_o_contorno_suavizado_recebe_o_texto_final():
    print(u"  -- o contorno suavizado recebe o texto final (spec F3) --")
    import pydicom

    def _monta(n, semente=5):
        rng = np.random.default_rng(semente)
        d = pydicom.dataset.Dataset()
        rcs = []
        for j in range(n):
            ang = np.linspace(0, 2 * np.pi, 20 + j, endpoint=False)
            r = 12.0 + rng.normal(0, 1.3, ang.size)
            pts = np.stack([100.123 + r * np.cos(ang),
                            -50.77 + r * np.sin(ang),
                            np.full(ang.size, -123.4567)], axis=1)
            c = pydicom.dataset.Dataset()
            c.ContourData = [float(v) for v in pts.ravel()]
            rc = pydicom.dataset.Dataset()
            rc.ContourSequence = [c]
            rcs.append(rc)
        d.ROIContourSequence = rcs
        return d

    def _o_laco(d, pular=()):
        for rc in d.ROIContourSequence:
            for c in rc.ContourSequence:
                if id(c) not in pular:
                    c.ContourData = ["%.4f" % float(v) for v in c.ContourData]

    def _textos(d):
        return [[str(v) for v in c.ContourData]
                for rc in d.ROIContourSequence for c in rc.ContourSequence]

    for dxdy in ((0.9, 0.9), None):
        a = _monta(12)
        b = _monta(12)
        M._suavizar_contornos(a, dxdy)
        _o_laco(a)
        fmt = set()
        M._suavizar_contornos(b, dxdy, formatados=fmt)
        _o_laco(b, pular=fmt)
        ta, tb = _textos(a), _textos(b)
        checar(u"o texto final e o mesmo (dxdy=%s), %d contornos, %d ja "
               u"formatados" % (dxdy, len(ta), len(fmt)),
               ta == tb and len(fmt) == len(ta), str(len(fmt)))
    c0 = _monta(1).ROIContourSequence[0].ContourSequence[0]
    d0 = pydicom.dataset.Dataset()
    rc0 = pydicom.dataset.Dataset()
    rc0.ContourSequence = [c0]
    d0.ROIContourSequence = [rc0]
    M._suavizar_contornos(d0, (0.9, 0.9))
    checar(u"sem `formatados`, a suavizacao grava numero (o de antes)",
           not getattr(c0.ContourData[0], "original_string", None),
           str(getattr(c0.ContourData[0], "original_string", None)))
    b = _monta(12)
    M._suavizar_contornos(b, (0.9, 0.9), formatados=set())
    c1 = b.ROIContourSequence[3].ContourSequence[0]
    v = [str(x) for x in c1.ContourData]
    v[4] = "%.4f" % (float(v[4]) + 0.0001)
    c1.ContourData = v
    a = _monta(12)
    M._suavizar_contornos(a, (0.9, 0.9))
    _o_laco(a)
    checar(u"ISCA: um decimo de micrometro num ponto e acusado",
           _textos(a) != _textos(b))


def _suavizar_individuais_de_antes(masks, nomes, grade, suavizar_mm, detalhe,
                                   finas):
    import radai_geom
    tratadas = set()
    for nm in nomes:
        try:
            m = M._bool_seguro(masks[nm])
            tratadas.add(nm)
            mm_dela = M.suavizacao_de(str(nm).split(":")[-1], suavizar_mm)
            if mm_dela > 0:
                _fina, _raio = M.estrutura_fina(m, grade)
                if _fina:
                    finas.append((str(nm), _raio))
                    mm_dela = 0.0
            if mm_dela <= 0 or int(m.sum()) < 10:
                continue
            antes_n = int(m.sum())
            s = radai_geom.suavizar(m, mm_dela, grade)
            if not s.any():
                continue
            depois_n = int(s.sum())
            comum = int((m & s).sum())
            detalhe.append((str(nm), float(mm_dela), antes_n, depois_n,
                            (comum / float(antes_n)) if antes_n else 1.0))
            masks[nm] = s
        except Exception:
            continue
    return tratadas


def _suavizar_construcoes_de_antes(masks, grade, suavizar_mm, construcoes,
                                   detalhe, finas, log=None):
    import radai_geom
    tratadas = set()
    nomes_constr = set(construcoes)
    for nome in sorted(construcoes):
        if nome not in masks:
            continue
        spec = construcoes.get(nome) or {}
        try:
            m = M._bool_seguro(masks[nome])
            if not m.any():
                continue
            tratadas.add(nome)
            mm = spec.get("suavizar_mm")
            mm = (M.suavizacao_de(nome, suavizar_mm) if mm is None
                  else float(mm))
            if mm > 0:
                _fina, _raio = M.estrutura_fina(m, grade)
                if _fina:
                    finas.append((str(nome), _raio))
                    mm = 0.0
            if mm > 0 and int(m.sum()) >= 10:
                antes_n = int(m.sum())
                s = radai_geom.suavizar(m, mm, grade)
                if s.any():
                    comum = int((m & s).sum())
                    detalhe.append((str(nome), float(mm), antes_n,
                                    int(s.sum()),
                                    (comum / float(antes_n)) if antes_n
                                    else 1.0))
                    m = s
            recorte = tuple(spec.get("recortar_por") or ())
            if recorte:
                viz = None
                for k in list(masks):
                    if k == nome or k in nomes_constr or str(k).startswith("_"):
                        continue
                    if M._nomes.casa_prefixo(k, recorte) is None:
                        continue
                    b = M._bool_seguro(masks[k])
                    viz = b.copy() if viz is None else (viz | b)
                if viz is not None:
                    novo = m & ~viz
                    if novo.any():
                        tirou = int(m.sum() - novo.sum())
                        m = novo
                        if log and tirou:
                            vx = float(np.prod(grade.spacing)) / 1000.0
                            log(u"   `%s` recortado de novo depois de "
                                u"suavizado: -%.1f cm3 nos vizinhos"
                                % (nome, tirou * vx))
                    elif log:
                        log(u"   `%s` ficaria VAZIO no recorte depois da "
                            u"suavizacao — nao recortei" % nome)
            reune = tuple(spec.get("reune") or ())
            if reune:
                volta = None
                for k in list(masks):
                    if k == nome or str(k).startswith("_"):
                        continue
                    if M._nomes.casa_prefixo(k, reune) is None:
                        continue
                    b = M._bool_seguro(masks[k])
                    volta = b.copy() if volta is None else (volta | b)
                if volta is not None:
                    fora_dela = int((volta & ~m).sum())
                    if fora_dela:
                        m = m | volta
                        if log:
                            vx = float(np.prod(grade.spacing)) / 1000.0
                            log(u"   `%s`: +%.2f cm3 do que ela contem por "
                                u"definicao (%s), que a suavizacao tinha "
                                u"deixado de fora" % (nome, fora_dela * vx,
                                                      u", ".join(reune)))
            masks[nome] = m
        except Exception as e:
            if log:
                log(u"   construcao `%s` na segunda passada: %s — sai como "
                    u"estava" % (nome, str(e)[:100]))
    return tratadas


def teste_a_suavizacao_em_threads_e_a_serial():
    print(u"  -- a suavizacao em threads e a serial (spec F3/S4) --")
    import threading
    import radai_geom
    g = radai_geom.Grade((2.5, 0.9, 0.9))
    sh = (30, 80, 80)
    rng = np.random.default_rng(42)

    def bloco(z0, z1, y0, y1, x0, x1, ruido=0.0):
        m = np.zeros(sh, bool)
        m[z0:z1, y0:y1, x0:x1] = True
        if ruido:
            m &= rng.random(sh) > ruido
        return m

    base = {
        "parotid_gland_left": bloco(5, 12, 10, 25, 10, 25, 0.1),
        "parotid_gland_right": bloco(5, 12, 10, 25, 50, 65, 0.1),
        "hyoid": bloco(14, 15, 30, 32, 30, 40),
        "brainstem": bloco(18, 28, 35, 45, 35, 45, 0.05),
        "spinal_cord": bloco(0, 30, 60, 63, 38, 41),
        "thyroid_gland": bloco(10, 16, 40, 50, 30, 50, 0.05),
        "lung_upper_lobe_left": bloco(15, 30, 5, 40, 45, 75),
        "lung_lower_lobe_left": bloco(5, 15, 5, 40, 45, 75),
        "heart": bloco(8, 18, 42, 60, 42, 60),
        "esophagus": bloco(0, 30, 62, 66, 45, 49),
        "pericardium": bloco(7, 19, 40, 62, 40, 62),
        "ChestWall_L": bloco(5, 25, 2, 45, 70, 79, 0.02),
    }
    constr = {"pericardium": {"suavizar_mm": None,
                              "recortar_por": ("esophagus",),
                              "reune": ("heart",)},
              "ChestWall_L": {"suavizar_mm": 3.0,
                              "recortar_por": ("lung_",)}}
    orgaos = ["parotid_gland_left", "parotid_gland_right", "hyoid",
              "brainstem", "spinal_cord", "thyroid_gland"]
    velho = M.THREADS_DO_POS
    saidas = {}
    try:
        for n in ("antes", 4):
            M.THREADS_DO_POS = 1 if n == "antes" else n
            ind = (_suavizar_individuais_de_antes if n == "antes"
                   else M._suavizar_individuais)
            con = (_suavizar_construcoes_de_antes if n == "antes"
                   else M._suavizar_construcoes)
            m = dict((k, v.copy()) for k, v in base.items())
            det, fin, log = [], [], []
            trat = ind(m, orgaos, g, 1.5, det, fin)
            M.suavizar_em_grupos(m, g, 1.5, log=log.append, detalhe=det,
                                 excluir=set(constr))
            trat2 = con(m, g, 1.5, constr, det, fin, log.append)
            saidas[n] = (m, det, fin, log, trat, trat2)
    finally:
        M.THREADS_DO_POS = velho
    a, b = saidas["antes"], saidas[4]
    checar(u"as mascaras sao bit a bit as de antes (serial, 4 threads)",
           set(a[0]) == set(b[0])
           and all(np.array_equal(a[0][k], b[0][k]) for k in a[0]))
    checar(u"  e mudaram de fato (a suavizacao rodou)",
           not np.array_equal(a[0]["brainstem"], base["brainstem"])
           and not np.array_equal(a[0]["ChestWall_L"], base["ChestWall_L"]))
    checar(u"o `detalhe` e o mesmo, NA MESMA ORDEM (%d linhas)" % len(a[1]),
           a[1] == b[1] and len(a[1]) >= 5, str(a[1][:2]))
    checar(u"as `finas` sao as mesmas, na mesma ordem (%d)" % len(a[2]),
           a[2] == b[2] and len(a[2]) >= 2, str(a[2]))
    checar(u"o log e o mesmo, linha por linha", a[3] == b[3] and a[3],
           u" | ".join(a[3][:3]))
    checar(u"e o que foi tratado tambem", a[4] == b[4] and a[5] == b[5])
    checar(u"ISCA: o `detalhe` na ordem de chegada (invertida) e acusado",
           list(reversed(b[1])) != a[1])
    try:
        gr = {}
        for n in (1, 4):
            M.THREADS_DO_POS = n
            m = dict((k, v.copy()) for k, v in base.items())
            det, log = [], []
            M.suavizar_em_grupos(m, g, 1.5, log=log.append, detalhe=det)
            gr[n] = (m, det, log)
    finally:
        M.THREADS_DO_POS = velho
    checar(u"o grupo disjunto: 1 e 4 threads, mascaras, detalhe e log iguais",
           all(np.array_equal(gr[1][0][k], gr[4][0][k]) for k in gr[1][0])
           and gr[1][1] == gr[4][1] and gr[1][2] == gr[4][2] and gr[1][1])
    try:
        M.THREADS_DO_POS = 4
        ordem = M._em_paralelo(lambda i: i * i, range(40))
        quem = set(M._em_paralelo(
            lambda i: (__import__("time").sleep(0.02),
                       threading.get_ident())[1], range(12)))
    finally:
        M.THREADS_DO_POS = velho
    checar(u"_em_paralelo devolve na ordem dos itens",
           ordem == [i * i for i in range(40)])
    checar(u"  e roda em mais de uma thread (%d)" % len(quem), len(quem) > 1)
    try:
        M.THREADS_DO_POS = 1
        um = set(M._em_paralelo(lambda i: threading.get_ident(), range(5)))
    finally:
        M.THREADS_DO_POS = velho
    checar(u"  e com THREADS_DO_POS = 1 e o laco de antes (esta thread)",
           um == {threading.get_ident()})


def _ref_do_recorte(direcao=None, origem=(0.0, 0.0, 0.0)):
    import SimpleITK as sitk
    img = sitk.GetImageFromArray(np.zeros((40, 60, 50), np.int16))
    img.SetSpacing((1.0, 1.5, 2.5))
    img.SetOrigin(origem)
    if direcao is not None:
        img.SetDirection(direcao)
    return img


def teste_a_caixa_do_recorte_e_em_mm_e_so_quando_medida():
    caixa_de = getattr(M, "caixa_de_recorte", None)
    if caixa_de is None:
        checar(u"engine.caixa_de_recorte existe", False)
        return
    ref = _ref_do_recorte()
    m = np.zeros((40, 60, 50), bool)
    m[10:21, 20:31, 15:26] = True
    fontes = {"lung_upper_lobe_left": m}
    reg = {"tteste": {"ancora": "pulmoes", "eixos": "zyx", "margem_mm": 5.0,
                      "medido": False, "numeros": None}}
    cx, mot = caixa_de("tteste", fontes, ref, registro=reg)
    checar(u"task sem medida NAO recorta (e diz por que)",
           cx is None and u"medid" in mot, mot)
    cx, mot = caixa_de("tteste", fontes, ref, registro=reg, forcar=True)
    esperado = ((8, 23), (16, 35), (10, 31))
    checar(u"a margem e em MM, por eixo, arredondada para cima",
           cx is not None and tuple(cx["zyx"]) == esperado,
           u"%s x %s" % (cx and cx["zyx"], esperado))
    checar(u"  e a caixa diz a fracao do volume",
           cx is not None and 0 < cx.get("fracao", 0) < 1,
           str(cx and cx.get("fracao")))
    reg_z = {"tteste": dict(reg["tteste"], eixos="z")}
    cz, _ = caixa_de("tteste", fontes, ref, registro=reg_z, forcar=True)
    checar(u"eixos «z»: so o craniocaudal e recortado",
           cz is not None and tuple(cz["zyx"]) == ((8, 23), (0, 60), (0, 50)),
           str(cz and cz["zyx"]))
    reg_ok = {"tteste": dict(reg["tteste"], medido=True,
                             numeros={"dice_min": 0.995})}
    cm, _ = caixa_de("tteste", fontes, ref, registro=reg_ok)
    checar(u"medida no registro: recorta sem forcar", cm is not None)
    c0, m0 = caixa_de("tteste", {}, ref, registro=reg_ok)
    checar(u"sem a ancora nas mascaras, NAO recorta (e diz)",
           c0 is None and u"ancora" in m0, m0)
    tudo = np.ones((40, 60, 50), bool)
    ct, mt = caixa_de("tteste", {"lung_upper_lobe_left": tudo}, ref,
                      registro=reg_ok)
    checar(u"a caixa que e a serie inteira NAO recorta",
           ct is None and u"inteira" in mt, mt)
    reg_b = {"total_v3": dict(reg_ok["tteste"])}
    cb, mb = caixa_de("total_v3", fontes, ref, registro=reg_b, forcar=True)
    checar(u"a BASE nunca e recortada, nem forcando", cb is None, mb)
    reg_t = {"teeth": dict(reg_ok["tteste"])}
    ctt, mtt = caixa_de("teeth", fontes, ref, registro=reg_t, forcar=True)
    checar(u"task com crop_model proprio fica fora, nem forcando",
           ctt is None, mtt)
    g = np.zeros((40, 60, 50), bool)
    g[18:23, 5:15, 5:45] = True
    reg_f = {"tteste": dict(reg_ok["tteste"],
                            fast={"ancora": "glandula", "eixos": "z",
                                  "margem_mm": 5.0})}
    cf, _ = caixa_de("tteste", {"breast": g, "lung_upper_lobe_left": m}, ref,
                     registro=reg_f, modo="fast")
    checar(u"no FAST vale a variante do registro (a glandula, so em z)",
           cf is not None and tuple(cf["zyx"]) == ((16, 25), (0, 60), (0, 50))
           and cf.get("ancora") == "glandula", str(cf and cf["zyx"]))
    reg_v = {"tteste": dict(reg["tteste"],
                            fast={"ancora": "glandula", "eixos": "z",
                                  "margem_mm": 5.0, "medido": True,
                                  "numeros": {"dice_min": 0.9926}})}
    fontes_v = {"breast": g, "lung_upper_lobe_left": m}
    cv, _ = caixa_de("tteste", fontes_v, ref, registro=reg_v, modo="fast")
    checar(u"variante MEDIDA com a task NAO medida: no FAST recorta sem "
           u"forcar", cv is not None and cv.get("medido") is True
           and cv.get("ancora") == "glandula", str(cv and cv.get("ancora")))
    cn, mn = caixa_de("tteste", fontes_v, ref, registro=reg_v)
    checar(u"  e FORA do FAST a mesma task roda inteira (a medida da "
           u"variante nao vale para ela)", cn is None and u"medid" in mn, mn)
    reg_x = {"tteste": dict(reg_ok["tteste"],
                            fast={"ancora": "glandula", "eixos": "z",
                                  "margem_mm": 5.0, "medido": False,
                                  "numeros": None})}
    cx2, mx2 = caixa_de("tteste", fontes_v, ref, registro=reg_x, modo="fast")
    checar(u"  e a variante que DIZ nao medida nao herda o «medido» da task",
           cx2 is None and u"medid" in mx2, mx2)


def teste_recortar_e_colar_devolvem_a_mesma_geometria():
    rec = getattr(M, "recortar_imagem", None)
    col = getattr(M, "colar_na_grade", None)
    if rec is None or col is None:
        checar(u"engine.recortar_imagem e engine.colar_na_grade existem",
               False)
        return
    import SimpleITK as sitk
    import math
    c, s = math.cos(0.3), math.sin(0.3)
    for rotulo, ref in (
            (u"axial", _ref_do_recorte()),
            (u"obliqua, origem qualquer", _ref_do_recorte(
                direcao=(c, -s, 0.0, s, c, 0.0, 0.0, 0.0, 1.0),
                origem=(-250.3, 118.7, -612.25)))):
        caixa = {"zyx": ((5, 17), (11, 40), (7, 33))}
        r = rec(ref, caixa)
        checar(u"%s: o recorte tem o tamanho da caixa" % rotulo,
               r.GetSize() == (26, 29, 12), str(r.GetSize()))
        checar(u"  a origem e o primeiro voxel da caixa, e o espacamento e "
               u"a direcao sao os da serie",
               np.allclose(r.GetOrigin(),
                           ref.TransformIndexToPhysicalPoint((7, 11, 5)))
               and r.GetSpacing() == ref.GetSpacing()
               and np.allclose(r.GetDirection(), ref.GetDirection()),
               u"%s" % (r.GetOrigin(),))
        a = np.zeros((12, 29, 26), np.uint8)
        a[0, 0, 0] = 3
        a[11, 28, 25] = 4
        a[4:7, 10:12, 3:9] = 1
        lab = sitk.GetImageFromArray(a)
        lab.CopyInformation(r)
        v = col(lab, ref, caixa)
        va = sitk.GetArrayFromImage(v)
        checar(u"  a colagem tem a grade da serie",
               v.GetSize() == ref.GetSize()
               and np.allclose(v.GetOrigin(), ref.GetOrigin())
               and np.allclose(v.GetDirection(), ref.GetDirection())
               and v.GetSpacing() == ref.GetSpacing())
        esperado = np.zeros((40, 60, 50), np.uint8)
        esperado[5:17, 11:40, 7:33] = a
        checar(u"  cada rotulo volta ao voxel de onde veio, e zero fora "
               u"(inclusive os cantos da caixa)",
               np.array_equal(va, esperado),
               u"%d voxels diferentes" % int((va != esperado).sum()))
    ref = _ref_do_recorte()
    caixa = {"zyx": ((5, 17), (11, 40), (7, 33))}
    torta = sitk.GetImageFromArray(np.zeros((12, 29, 25), np.uint8))
    torta.CopyInformation(rec(ref, {"zyx": ((5, 17), (11, 40), (7, 32))}))
    try:
        col(torta, ref, caixa)
        recusou = u""
    except ValueError as e:
        recusou = u"%s" % e
    checar(u"ISCA: a imagem que nao e a caixa e RECUSADA na colagem, pela "
           u"conferencia (e nao pelo numpy)",
           u"a imagem a colar" in recusou, recusou[:160])
    ao_lado = sitk.GetImageFromArray(np.ones((12, 29, 26), np.uint8))
    ao_lado.CopyInformation(rec(ref, {"zyx": ((5, 17), (11, 40), (8, 34))}))
    try:
        col(ao_lado, ref, caixa)
        recusou2 = u""
    except ValueError as e:
        recusou2 = u"%s" % e
    checar(u"ISCA: a imagem do tamanho da caixa com a origem UM VOXEL ao lado "
           u"e recusada (colada por indice, o rotulo iria para o lugar errado)",
           u"a imagem a colar" in recusou2, recusou2[:160])


def teste_o_registro_do_recorte_nasce_desligado():
    reg = getattr(M, "RECORTE_POR_TASK", None)
    if reg is None:
        checar(u"engine.RECORTE_POR_TASK existe", False)
        return
    import radai_tasks as RT
    checar(u"as quatro tasks da medida estao no registro",
           all(t in reg for t in ("breasts", "trunk_cavities",
                                  "abdominal_muscles", "lung_vessels")),
           str(sorted(reg)))
    bases = set(RT.BASES_CT) | set(RT.BASES_MR) | {"total"}
    checar(u"nenhuma base no registro", not (bases & set(reg)),
           str(sorted(bases & set(reg))))
    crop_model = [t for t, ds in RT.RECORTAM.items() if len(ds) > 1]
    checar(u"as tasks de crop_model do upstream sao as declaradas no motor",
           sorted(crop_model) == sorted(M.TASKS_COM_CROP_MODEL),
           u"%s x %s" % (sorted(crop_model), sorted(M.TASKS_COM_CROP_MODEL)))
    checar(u"  e nenhuma delas esta no registro",
           not (set(M.TASKS_COM_CROP_MODEL) & set(reg)))
    sem = [t for t, e in reg.items() if e.get("medido") and not e.get("numeros")]
    checar(u"sem numero nao ha «medido»", not sem, str(sem))
    ligadas = [t for t, e in reg.items() if e.get("medido")]
    checar(u"de fabrica, NENHUMA task nasce recortada pela ancora (medido no "
           u"cache P19/P20: nenhuma passa Dice >= 0,99 por rotulo)",
           not ligadas, str(ligadas))
    checar(u"a variante FAST da abdominal_muscles saiu com a Breast_OAR (a "
           u"estrutura que a media)", not [t for t, e in reg.items()
                                           if e.get("fast")])
    laterais = sorted(t for t, e in reg.items() if e.get("lateral_pelo_corpo"))
    checar(u"as tres tasks que so recortavam em z recortam tambem nas "
           u"laterais pelo corpo",
           laterais == ["abdominal_muscles", "breasts", "trunk_cavities"]
           and all(reg[t].get("eixos") == "z" for t in laterais),
           str(laterais))
    ancoras = set(M.ANCORAS_DO_RECORTE)
    fora = []
    for t, e in reg.items():
        if e.get("ancora") not in ancoras:
            fora.append((t, e.get("ancora")))
        if e.get("eixos") not in ("z", "zyx"):
            fora.append((t, e.get("eixos")))
        if float(e.get("margem_mm") or 0) != 30.0:
            fora.append((t, e.get("margem_mm")))
    checar(u"toda entrada tem ancora conhecida, eixos z|zyx e margem de "
           u"30 mm", not fora, str(fora))


def _ref_com_corpo():
    import SimpleITK as sitk
    a = np.full((40, 60, 120), -1000, np.int16)
    a[:, 20:44, 30:90] = 40
    img = sitk.GetImageFromArray(a)
    img.SetSpacing((1.0, 1.5, 2.5))
    return img


def teste_a_lista_recorta_nas_laterais_pelo_corpo():
    rodar_tasks = getattr(M, "rodar_tasks", None)
    if rodar_tasks is None:
        checar(u"engine.rodar_tasks existe", False)
        return
    ref = _ref_com_corpo()

    def _falso(chamadas):
        def rodar(ref_, task, device, jid, **kw):
            chamadas.append((task, kw.get("caixa")))
            return {}
        return rodar

    tasks = ("breasts", "trunk_cavities", "abdominal_muscles", "lung_vessels")
    for modo in ("fast", "auto", "perso", None):
        ch = []
        res = rodar_tasks(ref, list(tasks), "cpu", None, rodar=_falso(ch),
                          modo=modo)
        cx = dict(ch)
        ok = True
        for t in ("breasts", "trunk_cavities", "abdominal_muscles"):
            c = cx.get(t)
            ok = ok and c is not None and c.get("pelo_corpo") is True \
                and c["zyx"][0] == (0, 40) \
                and c["zyx"][1][0] > 0 and c["zyx"][1][1] < 60 \
                and c["zyx"][2][0] > 0 and c["zyx"][2][1] < 120
        checar(u"%s: as tres tasks recebem a caixa do corpo nas laterais (z "
               u"inteiro)" % (modo or u"sem modo"), ok,
               str(dict((t, (cx.get(t) or {}).get("zyx")) for t in tasks)))
        checar(u"  e a lung_vessels (sem medida) roda inteira",
               "lung_vessels" in cx and cx["lung_vessels"] is None)
        checar(u"  e o resultado registra o recorte (para o registro de "
               u"casos)", sorted(res.get("recortes") or {})
               == ["abdominal_muscles", "breasts", "trunk_cavities"],
               str(sorted(res.get("recortes") or {})))
    c = dict(_rodar_e_pegar(rodar_tasks, _ref_com_corpo(), _falso))
    zyx = c["trunk_cavities"]["zyx"]
    esp_y, esp_x = 1.5, 1.0
    my = int(np.ceil(M.MARGEM_DO_CORPO_MM / esp_y))
    mx = int(np.ceil(M.MARGEM_DO_CORPO_MM / esp_x))
    checar(u"a caixa contem o corpo inteiro com a margem (nada do corpo fica "
           u"fora)", zyx[1][0] <= 20 - my and zyx[1][1] >= 44 + my - 1
           and zyx[2][0] <= 30 - mx and zyx[2][1] >= 90 + mx - 1, str(zyx))
    velho = M.caixa_do_corpo_xy
    M.caixa_do_corpo_xy = lambda ref, margem_mm=None: None
    try:
        ci = dict(_rodar_e_pegar(rodar_tasks, _ref_com_corpo(), _falso))
    finally:
        M.caixa_do_corpo_xy = velho
    checar(u"ISCA: sem a caixa do corpo, a trunk_cavities roda inteira",
           "trunk_cavities" in ci and ci["trunk_cavities"] is None,
           str(ci.get("trunk_cavities")))
    import SimpleITK as sitk
    cheio = sitk.GetImageFromArray(np.zeros((40, 60, 50), np.int16))
    cc = dict(_rodar_e_pegar(rodar_tasks, cheio, _falso))
    checar(u"corpo ocupando o campo inteiro: nada a recortar, roda inteira",
           cc.get("trunk_cavities") is None, str(cc.get("trunk_cavities")))


def _ref_com_corpo_mesa_e_acessorio():
    import SimpleITK as sitk
    a = np.full((40, 140, 140), -1000, np.int16)
    a[:, 20:100, 30:120] = 40
    a[:, 100:102, 4:136] = 300
    a[:, 30:90, 8:10] = 200
    img = sitk.GetImageFromArray(a)
    img.SetSpacing((1.0, 1.0, 2.5))
    return img


def teste_a_caixa_lateral_e_a_do_contorno_externo():
    print(u"\n  -- v8.5: a caixa lateral e a do contorno externo, sem a mesa "
          u"e sem o acessorio --")
    ref = _ref_com_corpo_mesa_e_acessorio()
    cx = M.caixa_do_corpo_xy(ref)
    m = int(np.ceil(M.MARGEM_DO_CORPO_MM / 1.0))
    checar(u"a caixa contem o corpo inteiro, com a margem",
           cx is not None and cx[0][0] <= 20 - m and cx[0][1] >= 100 + m - 1
           and cx[1][0] <= 30 - m and cx[1][1] >= 120 + m - 1, str(cx))
    checar(u"  e deixa de fora a largura da mesa e o acessorio lateral "
           u"(o corpo vai de 30 a 120 em x; a mesa de 4 a 136, o acessorio "
           u"em 8)", cx is not None and cx[1][0] > 10 and cx[1][1] < 136,
           str(cx))
    velho = M.corpo_da_amostra
    M.corpo_da_amostra = lambda hu, esp: hu > M.LIMIAR_DO_CORPO_HU
    try:
        ci = M.caixa_do_corpo_xy(ref)
    finally:
        M.corpo_da_amostra = velho
    checar(u"ISCA: pelo limiar de antes, a caixa leva a mesa e o acessorio",
           ci is not None and ci[1][0] <= 8 and ci[1][1] >= 136, str(ci))
    pequeno = _ref_com_corpo()
    import SimpleITK as sitk
    arr = sitk.GetArrayFromImage(pequeno)
    esp = [float(v) for v in pequeno.GetSpacing()][::-1]
    p = int(M.PASSO_DA_AMOSTRA_DO_CORPO)
    hu = arr[::2, ::p, ::p]
    checar(u"corpo abaixo do piso do contorno externo: a caixa volta ao "
           u"limiar (nunca corta o corpo)",
           np.array_equal(M.corpo_da_amostra(hu, (esp[0] * 2, esp[1] * p,
                                                  esp[2] * p)),
                          hu > M.LIMIAR_DO_CORPO_HU))


def _rodar_e_pegar(rodar_tasks, ref, fabrica):
    ch = []
    rodar_tasks(ref, ["trunk_cavities"], "cpu", None, rodar=fabrica(ch),
                modo="auto")
    return ch


def _drenar_log_de_antes(jid, escrever, parar, a_cada_s=None, intervalo=3.0):
    mostradas = 0
    filtro = M.FiltroProgresso(a_cada_s)
    while not parar.is_set():
        try:
            linhas = (M._job(jid) or {}).get("log") or []
            for ln in linhas[mostradas:]:
                if filtro.passa(ln):
                    try:
                        escrever(str(ln))
                    except Exception:
                        pass
            mostradas = len(linhas)
        except Exception:
            pass
        parar.wait(intervalo)


def teste_o_drenador_le_uma_ultima_vez_ao_parar():
    print(u"  -- o drenador le uma ultima vez ao parar --")
    import threading as _th

    def _correr(drenar):
        jid = M._job_new()
        vistas, primeira = [], _th.Event()

        def escrever(ln):
            vistas.append(ln)
            if u"primeira linha" in ln:
                primeira.set()
        try:
            M._log(jid, u"TS abdominal_muscles primeira linha")
            parar = _th.Event()
            t = _th.Thread(target=drenar, args=(jid, escrever, parar),
                           kwargs={"intervalo": 30.0}, daemon=True)
            t.start()
            primeira.wait(10.0)
            M._log(jid, u"TS abdominal_muscles Predicted in 559.5 s")
            M._log(jid, u"TS abdominal_muscles: 22 rotulo(s)")
            parar.set()
            t.join(10.0)
            return vistas, (not t.is_alive())
        finally:
            M._job_del(jid)

    vistas, saiu = _correr(M.drenar_log)
    checar(u"o drenador sai quando mandam parar (sem esperar os 30 s)", saiu)
    checar(u"  e a linha escrita depois da ultima volta CHEGA (o «Predicted "
           u"in» da ultima task)",
           any(u"Predicted in" in v for v in vistas), str(vistas)[-200:])
    checar(u"  e a contagem de rotulos tambem, uma vez so",
           sum(1 for v in vistas if u"22 rotulo(s)" in v) == 1,
           str(vistas)[-200:])
    vistas_i, _s = _correr(_drenar_log_de_antes)
    checar(u"ISCA: o drenador de antes (sem a ultima leitura) perde o fim da "
           u"task -- a checagem sabe reprovar",
           any(u"primeira linha" in v for v in vistas_i)
           and not any(u"Predicted in" in v for v in vistas_i),
           str(vistas_i)[-200:])


def teste_a_linha_da_task_fora_do_mapa_diz_para_onde_vai():
    print(u"  -- a task fora do TS_MAP diz para onde vao os rotulos --")
    import radai_sets as RS
    d = M.destino_dos_rotulos_fora_do_mapa
    for t in ("breasts", "abdominal_muscles", "trunk_cavities"):
        checar(u"%s: os rotulos alimentam o FULL e o entregue" % t,
               RS.task_do_full(t) and u"alimentam o FULL" in d(t)
               and u"nao alimenta" not in d(t), d(t))
    _plug = sorted(t for t in RS.PLUGIN_DA_TASK if not RS.task_do_full(t))
    checar(u"um plugin (%s): o arquivo proprio da task, e nao o FULL"
           % (_plug[:1] or [u"?"])[0],
           bool(_plug) and u"arquivo proprio" in d(_plug[0])
           and u"nao alimenta o FULL" in d(_plug[0]),
           d(_plug[0]) if _plug else u"sem plugin no registro")
    checar(u"task que nao e nem uma coisa nem outra: so o cru",
           u"so ao conjunto cru" in d("task_que_nao_existe"))
    tmp = tempfile.mkdtemp(prefix="radai_teste_foramapa_")
    com = _pesos_do_body(tempfile.mkdtemp(prefix="radai_teste_pesos_"))
    try:
        r, log, _reg, _job = _rodar_falso(tmp, u"gravar_saida()\n", "breasts",
                                          com)
        ln = [l for l in log if u"TS breasts:" in l and u"TS_MAP" in l]
        checar(u"run_ts_task da `breasts`: a serie segue (dicionario vazio)",
               isinstance(r, dict) and not r, repr(r)[:120])
        checar(u"  e a linha diz que os rotulos alimentam o FULL, e nao que "
               u"ela «nao alimenta o RTSTRUCT entregue»",
               ln and u"alimentam o FULL" in ln[0]
               and u"nao alimenta" not in ln[0], u" | ".join(ln)[:240])
        _antes = (lambda t: u"so para o conjunto cru (esta task nao alimenta o "
                            u"RTSTRUCT entregue)")
        _r, log_i, _g, _j = _rodar_falso(
            tmp, u"gravar_saida()\n", "breasts", com,
            destino_dos_rotulos_fora_do_mapa=_antes)
        ln_i = [l for l in log_i if u"TS breasts:" in l and u"TS_MAP" in l]
        checar(u"ISCA: com a frase de antes, o log volta a dizer que a mama "
               u"nao alimenta o entregue (a checagem reprova)",
               ln_i and u"nao alimenta" in ln_i[0], u" | ".join(ln_i)[:240])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _rotulos_da_base(forma=(40, 60, 50)):
    nomes = ("liver", "spleen", "aorta", "iliac_artery_left",
             "iliac_artery_right", "vertebrae_L1", "vertebrae_L2")
    rotulos = [n for n in nomes if "total" in M.TS_MAP.get(n, {})]
    idx = dict((i + 1, M.TS_MAP[n]["total"][0])
               for i, n in enumerate(rotulos))
    arr = np.zeros(forma, np.uint8)
    for i in sorted(idx):
        z0 = 2 + 4 * i
        arr[z0:z0 + 6, 5 + 3 * i:15 + 3 * i, 4 + 2 * i:12 + 2 * i] = i
    return arr, idx


def teste_as_mascaras_por_task_ficam_na_caixa():
    print(u"  -- CA-17: as mascaras por task ficam na caixa delas --")
    arr, idx = _rotulos_da_base()
    cheias = M.masks_da_task(arr, "total_v3", idx)
    comp = M.masks_compactas_da_task(arr, "total_v3", idx)
    checar(u"as mesmas chaves, compostos inclusive",
           sorted(cheias) == sorted(comp) and "great_arteries" in comp,
           u"%s x %s" % (sorted(cheias), sorted(comp)))
    iguais = all(np.array_equal(np.asarray(comp[k]), cheias[k])
                 and int(comp[k].sum()) == int(cheias[k].sum())
                 and bool(comp[k].any()) == bool(cheias[k].any())
                 for k in cheias)
    checar(u"voxel a voxel iguais as de grade inteira (soma e any tambem)",
           iguais)
    m = comp["liver"]
    outra = cheias["spleen"]
    checar(u"numpy enxerga a mascara compacta como a cheia (|, &, ~, astype)",
           np.array_equal(m | outra, cheias["liver"] | outra)
           and np.array_equal(outra & m, outra & cheias["liver"])
           and np.array_equal(~m, ~cheias["liver"])
           and np.asarray(m, dtype=np.uint8).dtype == np.uint8
           and m.shape == arr.shape)
    c = m.copy()
    c[:] = True
    checar(u"a copia e independente", int(m.sum()) == int(cheias["liver"].sum()))
    d = dict(comp)
    d["liver"] |= outra
    checar(u"o |= pelo dicionario fica gravado",
           np.array_equal(np.asarray(d["liver"]), cheias["liver"] | outra))
    checar(u"nao expoe a interface de memoria de uma copia temporaria",
           not hasattr(m, "__array_interface__")
           and not hasattr(m, "__array_struct__"))
    b_c = M.bytes_das_mascaras(comp)
    b_g = M.bytes_das_mascaras(cheias)
    checar(u"guardam uma fracao da grade inteira (aqui, menos de um quinto)",
           b_c * 5 < b_g, u"%d x %d bytes" % (b_c, b_g))
    checar(u"ISCA: as cheias guardam uma grade por estrutura",
           b_g >= len([k for k in cheias if k not in M.COMPOSTOS])
           * arr.size, b_g)
    with _TrocarNoMotor(TS_CLASS_MAP={M._nome_biblioteca("total_v3"): idx}):
        jid = M._job_new()
        try:
            r = M._mascaras_do_arr(arr, "total_v3", jid, {}, False)
        finally:
            M._job_del(jid)
    checar(u"a porta da task (_mascaras_do_arr) entrega as compactas",
           r and all(isinstance(v, M.MascaraCompacta) for v in r.values()),
           sorted(type(v).__name__ for v in r.values())[:3])


class _TrocarNoMotor(object):
    def __init__(self, **kw):
        self.kw, self.velhos = kw, {}

    def __enter__(self):
        for k, v in self.kw.items():
            self.velhos[k] = getattr(M, k)
            setattr(M, k, v)
        return self

    def __exit__(self, *a):
        for k, v in self.velhos.items():
            setattr(M, k, v)
        return False


def teste_o_rtstruct_e_gravado_em_fluxo():
    print(u"  -- o RTSTRUCT e gravado em fluxo, sem a segunda copia --")
    import filecmp
    import pydicom
    import pydicom.filewriter as FW
    d = tempfile.mkdtemp(prefix="radai_teste_")
    try:
        serie = os.path.join(d, "serie")
        escreve_serie(serie, "FANTOMA_FLUXO", datetime(2026, 3, 15, 10, 30),
                      12)
        m = np.zeros((12, 128, 128), bool)
        m[3:9, 40:80, 40:80] = True
        n = np.zeros((12, 128, 128), bool)
        n[2:10, 85:100, 30:60] = True
        caminho, _nomes = M.build_rtstruct(serie, {"liver": m, "spleen": n},
                                           tasks=["total_v3"],
                                           versao_worker="fluxo")
        for rotulo, kw in ((u"Eclipse", {}),
                           (u"Monaco", {"implicit_vr": True,
                                        "little_endian": True})):
            a = os.path.join(d, "a.dcm")
            b = os.path.join(d, "b.dcm")
            pydicom.dcmread(caminho).save_as(a, **kw)
            M.gravar_dicom_em_fluxo(pydicom.dcmread(caminho), b, **kw)
            checar(u"%s: os mesmos bytes do pydicom" % rotulo,
                   filecmp.cmp(a, b, shallow=False),
                   u"%d x %d bytes" % (os.path.getsize(a), os.path.getsize(b)))
        vistos = []
        velho = FW.write_data_element

        def _espia(fp, elem, *x, **k):
            vistos.append(int(elem.tag))
            return velho(fp, elem, *x, **k)
        FW.write_data_element = _espia
        try:
            lido = pydicom.dcmread(caminho)
            _sq = lido.ROIContourSequence
            M.gravar_dicom_em_fluxo(lido, os.path.join(d, "c.dcm"))
            fluxo = list(vistos)
            del vistos[:]
            lido2 = pydicom.dcmread(caminho)
            _sq2 = lido2.ROIContourSequence
            lido2.save_as(os.path.join(d, "e.dcm"))
            inteiro = list(vistos)
        finally:
            FW.write_data_element = velho
        checar(u"a sequencia dos contornos nao passa pelo buffer do elemento "
               u"(vai item a item ao arquivo)", 0x30060039 not in fluxo
               and 0x30060040 in fluxo, [hex(t) for t in fluxo[:6]])
        checar(u"ISCA: o save_as do pydicom a monta inteira num buffer",
               0x30060039 in inteiro)
        checar(u"o gravador do TPS usa o fluxo",
               u"gravar_dicom_em_fluxo(" in _fonte_de(M.gravar_rtstruct)
               and u"save_as(" not in _fonte_de(M.gravar_rtstruct))
    finally:
        shutil.rmtree(d, ignore_errors=True)


def _fonte_de(f):
    import inspect
    return inspect.getsource(f)


def teste_o_pico_e_as_versoes():
    print(u"  -- o pico de memoria (nulo, nunca 0,0) e as versoes --")
    checar(u"sem medida o pico e nulo, e a frase diz nao medido",
           M._inteiro_ou_nulo("?") is None and M._inteiro_ou_nulo("0") is None
           and M._inteiro_ou_nulo(None) is None
           and u"nao medido" in M.frase_do_pico(None)
           and u"nao medido" in M.frase_do_pico({"commit_mb": None,
                                                  "ws_mb": None}))
    checar(u"  e com medida, em GiB", u"2,0 GiB de commit"
           in M.frase_do_pico({"commit_mb": 2048, "ws_mb": None}))
    d = tempfile.mkdtemp(prefix="radai_teste_")
    try:
        log = os.path.join(d, "ts.log")
        with io.open(log, "w", encoding="utf-8") as f:
            f.write(u"RADAI|pico|commit_mb=3072|ws_mb=?\nRADAI|fim|codigo=0\n")
        lt = M._LeitorDoLogTS(log)
        lt.ler()
        checar(u"o leitor do log le a linha do pico do envelope",
               lt.pico == {"commit_mb": 3072, "ws_mb": None}
               and lt.fim == 0, (lt.pico, lt.fim))
    finally:
        shutil.rmtree(d, ignore_errors=True)
    import radai_ts_runner as R
    fonte = _fonte_de(R._fim)
    checar(u"o envelope manda o pico antes da linha do fim",
           u'"pico|' in fonte and fonte.index(u'"pico|')
           < fonte.index(u'"fim|'))
    c, w = R.pico_do_processo_mb()
    checar(u"a API do Windows mede o pico deste processo (ou devolve nulo)",
           (c is None or c > 0) and (w is None or w > 0), (c, w))
    import numpy
    checar(u"as versoes vem do pacote instalado (importlib.metadata)",
           M.versao_do_pacote("numpy") == numpy.__version__
           and R.versao_do_pacote("numpy") == numpy.__version__
           and M.versao_do_pacote("pacote_que_nao_existe_radai") == u""
           and R.versao_do_pacote("pacote_que_nao_existe_radai") == u"?")


def main():
    print("test_engine | engine.py sem TotalSegmentator")
    _TESTES = (teste_refino_na_caixa_da_estrutura,
              teste_a_linha_da_computacao_nao_se_contradiz,
              teste_a_memoria_da_serie_sai_no_log_uma_vez,
              teste_o_indice_26_e_fundido_ao_sacro,
              teste_derivada_recusa_marco_duvidoso,
              teste_suavizacao_e_por_estrutura,
              teste_o_piso_por_volume_saiu,
              teste_suavizacao_usa_distancia_com_sinal,
              teste_nenhum_nome_colapsa_no_arquivo_real,
              teste_o_desempate_preserva_a_procedencia,
              teste_suavizar_conjunto_e_particao,
              teste_derivadas_particionam_o_colon,
              teste_derivadas_sem_marco_nao_inventam,
              teste_derivada_nao_se_chama_ai,
              teste_conjunto_cru_nao_recebe_derivada,
              teste_a_sobreposicao_orgao_e_construcao,
              teste_nenhum_nome_clinico_colide,
              teste_nome_clinico, teste_nivel_numerado_sobrevive,
              teste_desempate_nao_estraga_o_sufixo,
              teste_cor_separa_os_dois_modelos,
              teste_contorno_degenerado_vira_poligono,
              teste_task_que_nao_alimenta_o_entregue,
              teste_masks_da_task, teste_build_rtstruct,
              teste_marco_interno_nao_vira_estrutura,
              teste_o_conjunto_cru_nao_recebe_nada_nosso,
              teste_o_desconto_do_cisto_e_do_OAR_e_nao_do_orgao,
              teste_sem_desconto_o_grupo_disjunto_nao_recorta_o_orgao,
              teste_nenhum_campo_estoura_o_limite_do_VR,
              teste_a_adrenal_nao_e_comida_pelo_rim,
              teste_o_coracao_e_um_saco_e_nao_a_uniao_das_camaras,
              teste_o_femur_do_oar_para_na_tuberosidade,
              teste_o_composto_cede_o_que_o_coracao_levou,
              teste_a_descendente_fica_nos_grandes_vasos,
              teste_o_nvidia_smi_tem_uma_regra_so,
              teste_o_leitor_entende_a_linha_do_executor,
              teste_falha_do_ts_levanta,
              teste_constritores_da_faringe_sao_entrega_obrigatoria,
              teste_cavidades_e_derrame,
              teste_so_comparacao_recorta_o_entregue_e_nao_o_cru,
              teste_estrutura_vazia_nao_entra,
              teste_pisos_de_volume_vieram_do_artigo, teste_truncada_pelo_campo_nao_e_suspeita,
              teste_curadoria_ganha_da_derivacao, teste_curadoria_atravessa_o_build,
              teste_ilha_distante_e_marcada_e_anatomia_nao,
              teste_estrutura_fina_nao_e_suavizada,
              teste_pedacos_no_ar_saem_das_nossas_entregas,
              teste_contencao_e_buraco_triplanar,
              teste_coracao_de_radioterapia,
              teste_coracao_nao_desce_com_a_cava,
              teste_o_reto_sai_uma_vez_so,
              teste_refino_por_densidade_adjacente,
              teste_a_base_eleita_cai_para_a_v2,
              teste_o_mapa_da_rm_leva_40_dos_50,
              teste_a_rm_passa_pelo_pos_processamento_sem_hu,
              teste_o_pulmao_da_rm_chega_ao_rtstruct,
              teste_o_rascunho_da_estatistica_e_de_quem_grava,
              teste_task_de_deteccao_exige_ato_declarado,
              teste_classe_de_achado_do_nv_exige_ato_declarado,
              teste_o_cads_so_nomeia_o_que_alguem_conferiu,
              teste_achado_nao_sai_pelo_caminho_cru,
              teste_sobreposicao_e_medida_e_nao_aparada,
              teste_o_grupo_disjunto_le_a_tabela_por_estrutura,
              teste_o_contorno_sai_na_aresta_da_celula_e_nao_no_centro,
              teste_o_rotulo_de_conjunto_cabe_nos_16_e_nao_colide,
              teste_a_lamina_do_pericardio_sobrevive_ao_coracao,
              teste_a_cor_diz_qual_orgao_e_qual_estrutura,
              teste_o_log_diz_quanto_cada_estrutura_mudou,
              teste_o_recorte_no_corpo_no_comando,
              teste_a_predicao_grosseira_nao_e_a_parte_1,
              teste_a_rede_unica_recortada_tem_etapa_propria,
              teste_o_recuo_para_a_cpu_fica_no_job,
              teste_o_plano_diz_que_o_recorte_reduz_o_volume,
              teste_o_recorte_vazio_refaz_sem_ele,
              teste_a_observacao_de_quem_chama_chega_ao_dicom,
              teste_a_citacao_dos_niveis_e_do_artigo,
              teste_as_conferencias_na_caixa_sao_as_de_antes,
              teste_o_teto_reaproveita_o_raio,
              teste_o_contorno_suavizado_recebe_o_texto_final,
              teste_a_suavizacao_em_threads_e_a_serial,
              teste_a_limpeza_do_ar_na_caixa_e_a_de_antes,
              teste_a_caixa_do_recorte_e_em_mm_e_so_quando_medida,
              teste_recortar_e_colar_devolvem_a_mesma_geometria,
              teste_o_registro_do_recorte_nasce_desligado,
              teste_a_lista_recorta_nas_laterais_pelo_corpo,
              teste_a_caixa_lateral_e_a_do_contorno_externo,
              teste_as_mascaras_por_task_ficam_na_caixa,
              teste_o_rtstruct_e_gravado_em_fluxo,
              teste_o_pico_e_as_versoes,
              teste_o_drenador_le_uma_ultima_vez_ao_parar,
              teste_a_linha_da_task_fora_do_mapa_diz_para_onde_vai)
    _conferir_registro(_TESTES)
    for t in _TESTES:
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
