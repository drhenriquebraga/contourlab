# -*- coding: utf-8 -*-
import io
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "app"))

import numpy as np

import tempfile as _tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _cleanup
import _componentes
OFICINA = _componentes.oficina("hnlnl", __file__)
_cleanup.adotar_prefixo('radai_ac_hnlnl')
_cleanup.adotar_prefixo('radai_chk_')
os.environ["RADAI_CALIB_DIR"] = _tempfile.mkdtemp(prefix="radai_ac_hnlnl_")


_R = []


def checar(nome, ok, detalhe=""):
    _R.append((nome, bool(ok), detalhe))
    print("  %s  %s%s" % ("OK   " if ok else "FALHA", nome,
                          ("  [%s]" % detalhe) if detalhe else ""))
    return bool(ok)


def secao(t):
    print(u"\n  ── %s ─────────────────────────" % t)


class Cruas(dict):
    pass


def _grade(esp=(3.0, 1.0, 1.0), sentido=("sup", "post", "esq")):
    import radai_geom
    return radai_geom.Grade(esp, sentido)


def _bloco(forma, z, y, x):
    m = np.zeros(forma, dtype=bool)
    m[z[0]:z[1], y[0]:y[1], x[0]:x[1]] = True
    return m


def _pescoco_sintetico(forma=(60, 120, 140)):
    c = Cruas()
    c["skull"] = _bloco(forma, (44, 60), (30, 90), (40, 100))
    c["brain"] = _bloco(forma, (46, 58), (30, 90), (40, 100))
    c["trachea"] = _bloco(forma, (10, 46), (55, 65), (65, 75))
    c["humerus_left"] = _bloco(forma, (5, 25), (50, 80), (5, 20))
    c["humerus_right"] = _bloco(forma, (5, 25), (50, 80), (120, 135))
    c["clavicula_left"] = _bloco(forma, (24, 28), (45, 70), (20, 60))
    c["clavicula_right"] = _bloco(forma, (24, 28), (45, 70), (80, 120))
    for i in range(1, 8):
        c["vertebrae_C%d" % i] = _bloco(forma, (28 + i * 2, 30 + i * 2),
                                        (70, 80), (65, 75))
    return c, forma


def teste_portao():
    secao(u"o portao: TC de torax NAO e TC de cabeca e pescoco")
    import radai_hnlnl as HN
    g = _grade()
    c, forma = _pescoco_sintetico()

    ok, motivo = HN.serie_e_pescoco(c, g)
    checar(u"pescoco sintetico PASSA", ok, motivo)

    sem_cerebro = Cruas(c)
    del sem_cerebro["brain"]
    ok2, motivo2 = HN.serie_e_pescoco(sem_cerebro, g)
    checar(u"TC de torax (sem encefalo) e RECUSADA", not ok2, motivo2[:64])
    checar(u"  e o motivo diz `encefalo`", "encéfalo" in motivo2)

    pouco = Cruas(c)
    pouco["brain"] = _bloco(forma, (57, 58), (40, 44), (50, 54))
    ok3, motivo3 = HN.serie_e_pescoco(pouco, g)
    checar(u"encefalo so raspando o campo tambem e recusado", not ok3,
           motivo3[:64])

    for falta in ("skull", "trachea", "humerus_left", "humerus_right"):
        cc = Cruas(c)
        del cc[falta]
        ok4, m4 = HN.serie_e_pescoco(cc, g)
        checar(u"sem `%s` o portao fecha" % falta, not ok4)
        checar(u"  e nomeia o marco que falta", falta in m4, m4[:50])

    poucas = Cruas(c)
    for i in range(1, 6):
        del poucas["vertebrae_C%d" % i]
    ok5, m5 = HN.serie_e_pescoco(poucas, g)
    checar(u"com 2 cervicais o portao fecha", not ok5, m5[:56])

    checar(u"sem a task `total` o portao fecha",
           not HN.serie_e_pescoco(None, g)[0])
    ok6, m6 = HN.serie_e_pescoco(c, None)
    checar(u"sem grade responde e avisa que nao mediu", ok6 and "sem grade" in m6,
           m6[:60])


def teste_recorte():
    secao(u"o recorte por marcos: obrigatorio, e levanta quando falta")
    import radai_hnlnl as HN
    g = _grade()
    c, forma = _pescoco_sintetico()

    z0, z1, y0, y1, x0, x1 = HN.caixa(c, forma, g)
    checar(u"a caixa cobre da carina ao cranio",
           z0 < 20 and z1 > 55, "z %d..%d" % (z0, z1))
    checar(u"e vai de um umero ao outro",
           x0 <= 5 and x1 >= 135, "x %d..%d" % (x0, x1))
    checar(u"o eixo y fica inteiro (o limite dorsal e o primeiro plano)",
           y0 == 0 and y1 == forma[1], "y %d..%d" % (y0, y1))
    checar(u"a caixa cabe no volume",
           0 <= z0 < z1 <= forma[0] and 0 <= x0 < x1 <= forma[2])

    for falta in HN.OBRIGATORIOS:
        cc = Cruas(c)
        del cc[falta]
        try:
            HN.caixa(cc, forma, g)
            checar(u"sem `%s` a caixa LEVANTA" % falta, False,
                   "montou o recorte sem o marco")
        except ValueError as e:
            checar(u"sem `%s` a caixa LEVANTA" % falta, True)
            checar(u"  e o erro nomeia o marco", falta in str(e))

    vazio = Cruas(c)
    vazio["skull"] = np.zeros(forma, dtype=bool)
    try:
        HN.caixa(vazio, forma, g)
        checar(u"marco vazio LEVANTA", False)
    except ValueError as e:
        checar(u"marco vazio LEVANTA", True, str(e)[:44])


def teste_orientacao():
    secao(u"o recorte respeita o SENTIDO da serie")
    import radai_hnlnl as HN
    c, forma = _pescoco_sintetico()
    sup = HN.caixa(c, forma, _grade(sentido=("sup", "post", "esq")))
    inf = HN.caixa(c, forma, _grade(sentido=("inf", "post", "esq")))
    checar(u"os dois sentidos dao caixas diferentes", sup[:2] != inf[:2],
           "sup z %s | inf z %s" % (sup[:2], inf[:2]))
    checar(u"as duas caixas cabem no volume",
           0 <= sup[0] < sup[1] <= forma[0] and 0 <= inf[0] < inf[1] <= forma[0])


def _grade_do_treino(esp_z=3.0):
    import radai_geom
    return radai_geom.Grade((esp_z, 1.1716, 1.1716))


# GUARDA: o algoritmo dos autores (Adjust3DCNNcontoursToCTslicePlaneOrientation,
# CC0) transcrito em numpy como REFERENCIA, com os defeitos de borda dele.
def _ajuste_dos_autores(arr):
    a = np.asarray(arr).copy()
    pares = [[18, 5], [17, 4], [5, 7], [4, 6], [7, 9], [6, 8]]
    trios = [[11, 9, 13], [10, 8, 12]]
    quads = [[14, 1, 2, 3]]

    def area(f, r):
        return int((f == r).sum())

    for z in range(a.shape[0]):
        f = a[z]
        for p in pares:
            if area(f, p[0]) > 0 and area(f, p[1]) > 0:
                if area(f, p[0]) >= area(f, p[1]):
                    a[z][a[z] == p[1]] = p[0]
                else:
                    a[z][a[z] == p[0]] = p[1]
        for p in trios:
            if area(f, p[0]) > 0 and (area(f, p[1]) > 0 or area(f, p[2]) > 0):
                if area(f, p[0]) >= area(f, p[1]) + area(f, p[2]):
                    a[z][a[z] == p[1]] = p[0]
                    a[z][a[z] == p[2]] = p[0]
                else:
                    cima = a[z + 1].copy()
                    for j in range(1, 21):
                        if j != p[1] and j != p[2]:
                            cima[cima == j] = 0
                    a[z][a[z] == p[0]] = cima[a[z] == p[0]]
        for p in quads:
            if area(f, p[0]) > 0 and (area(f, p[1]) > 0 or area(f, p[2]) > 0
                                      or area(f, p[3]) > 0):
                if area(f, p[0]) >= area(f, p[1]) + area(f, p[2]) + area(
                        f, p[3]):
                    for o in p[1:]:
                        a[z][a[z] == o] = p[0]
                else:
                    cima = a[z + 1].copy()
                    moda = cima.copy()
                    for j in range(1, 21):
                        if j not in p[1:]:
                            moda[moda == j] = 0
                    for c in range(moda.shape[1]):
                        col = moda.T[c]
                        nz = col[col > 0]
                        if len(nz):
                            col[col == 0] = int(np.argmax(np.bincount(nz)))
                        else:
                            moda.T[c] = 0
                    for j in range(1, 21):
                        if j not in p[1:]:
                            cima[cima == j] = moda[cima == j]
                    a[z][a[z] == p[0]] = cima[a[z] == p[0]]
        atual = int((a[z] > 0).sum())
        if atual <= 10:
            a[z] = 0
        if atual > 10:
            baixo = int((a[z - 1] > 0).sum())
            cima_n = int((a[z + 1] > 0).sum())
            with np.errstate(divide="ignore", invalid="ignore"):
                razao = np.float64(atual) / np.float64(cima_n)
            if baixo == 0 and razao <= 0.2:
                a[z] = 0
    return a


def _pos_da_v83(rot, minimo_por_fatia=10, queda=0.8):
    rot = np.asarray(rot).copy()
    n = rot.shape[0]
    for z in range(n):
        fatia = rot[z]
        vals = [v for v in np.unique(fatia) if v != 0]
        if len(vals) < 2:
            continue
        areas = dict((int(v), int((fatia == v).sum())) for v in vals)
        dom = max(areas, key=lambda k: areas[k])
        for v, a in areas.items():
            if v != dom and a * 10 < areas[dom] and a <= minimo_por_fatia:
                fatia[fatia == v] = 0
    conta = np.array([int((rot[z] != 0).sum()) for z in range(n)])
    for z in range(n):
        if 0 < conta[z] <= minimo_por_fatia:
            rot[z] = 0
            conta[z] = 0
    return rot


def _mapas_aleatorios(n=200, semente=7):
    rng = np.random.RandomState(semente)
    fora = []
    for _ in range(n):
        a = np.zeros((14, 40, 40), dtype="int8")
        for z in range(1, 13):
            for _k in range(rng.randint(1, 7)):
                r = int(rng.randint(1, 21))
                y0, x0 = rng.randint(0, 34, size=2)
                h, w = rng.randint(1, 9, size=2)
                a[z, y0:y0 + h, x0:x0 + w] = r
        fora.append(a)
    return fora


def teste_o_ajuste_e_o_dos_autores():
    secao(u"o ajuste aos planos da TC e o dos autores (C7-PLANOS)")
    import radai_hnlnl as HN
    g = _grade_do_treino()
    mapas = _mapas_aleatorios()
    iguais = sum(1 for m in mapas
                 if np.array_equal(HN.pos_processar(m, g),
                                   _ajuste_dos_autores(m)))
    checar(u"200 mapas aleatorios com os 20 rotulos: igual aos autores, voxel "
           u"a voxel (fatias extremas vazias)", iguais == len(mapas),
           u"%d de %d" % (iguais, len(mapas)))
    com_conflito = sum(1 for m in mapas
                       if not np.array_equal(_ajuste_dos_autores(m), m))
    checar(u"  e os mapas exercitam o algoritmo (ele muda a maioria)",
           com_conflito > 150, str(com_conflito))
    iguais_v83 = sum(1 for m in mapas
                     if np.array_equal(_pos_da_v83(m), _ajuste_dos_autores(m)))
    checar(u"  ISCA: o pos_processar da v8.3 nao e o dos autores",
           iguais_v83 < len(mapas), u"%d de %d" % (iguais_v83, len(mapas)))

    a = np.zeros((3, 20, 20), dtype="int8")
    a[1, 0:6, 0:10] = 4
    a[1, 10:14, 0:10] = 6
    r = HN.pos_processar(a, g)
    checar(u"II_L 60 + III_L 40 no mesmo corte: tudo vira II_L",
           int((r[1] == 4).sum()) == 100 and not (r[1] == 6).any())
    checar(u"  ISCA: a v8.3 deixava os dois no corte",
           (_pos_da_v83(a)[1] == 6).any())

    a = np.zeros((4, 20, 20), dtype="int8")
    a[1, 0:3, 0:10] = 10
    a[1, 5:10, 0:10] = 8
    a[1, 12:14, 0:10] = 12
    a[2, 0:2, 0:10] = 8
    a[2, 2:3, 0:10] = 12
    a[2, 5:10, 0:10] = 8
    r = HN.pos_processar(a, g)
    checar(u"IVb_L 30 contra IVa_L 50 + V_L 20: o IVb_L herda o corte de cima",
           not (r[1] == 10).any() and (r[1, 0:2, 0:10] == 8).all()
           and (r[1, 2, 0:10] == 12).all(), str(np.unique(r[1])))

    a = np.zeros((4, 20, 20), dtype="int8")
    a[1, 0:4, 0:20] = 14
    a[1, 10:16, 0:20] = 1
    a[2, 0:2, 0:5] = 2
    a[2, 2:3, 0:5] = 3
    a[2, 0:1, 5:10] = 7
    a[2, 5:7, 5:10] = 1
    a[2, 8:10, 5:10] = 2
    r = HN.pos_processar(a, g)
    checar(u"VIa contra Ia/Ib: herda o corte de cima preenchido pela moda da "
           u"coluna", np.array_equal(r, _ajuste_dos_autores(a))
           and not (r[1] == 14).any()
           and (r[1, 0:1, 5:10] == 1).all() and (r[1, 0:2, 0:5] == 2).all()
           and (r[1, 2:4, 10:20] == 0).all())


def teste_as_fatias_extremas():
    secao(u"as fatias extremas (C7-EXTREMOS)")
    import radai_hnlnl as HN
    g = _grade_do_treino()
    a = np.zeros((3, 20, 20), dtype="int8")
    a[1, 0:3, 0:10] = 2
    a[2, 0:3, 0:10] = 10
    a[2, 5:10, 0:10] = 8
    a[2, 12:14, 0:10] = 12
    try:
        r = HN.pos_processar(a, g)
        checar(u"conflito de trio no topo nao levanta, e resolve pela area "
               u"(o IVb vai ao IVa, o maior dos outros)",
               not (r[2] == 10).any() and (r[2, 0:3, 0:10] == 8).all())
    except Exception as e:
        checar(u"conflito de trio no topo nao levanta", False, str(e))
    levantou = False
    try:
        _ajuste_dos_autores(a)
    except IndexError:
        levantou = True
    checar(u"  ISCA: o script dos autores levanta IndexError nesse caso "
           u"(o caso existe)", levantou)

    a = np.zeros((5, 30, 30), dtype="int8")
    a[0, 0:4, 0:5] = 4
    a[1, 0:10, 0:20] = 4
    a[2, 0:10, 0:20] = 4
    a[4, 0:1, 0:5] = 4
    r = HN.pos_processar(a, g)
    checar(u"corte 0 com 20 voxels e o corte 1 com 200 (topo nao vazio): o "
           u"corte 0 sai", not r[0].any())
    checar(u"  e os autores nao o tirariam (leem o topo como o corte de baixo)",
           _ajuste_dos_autores(a)[0].any())

    a = np.zeros((5, 30, 30), dtype="int8")
    a[2, 0:10, 0:5] = 4
    try:
        r = HN.pos_processar(a, g)
        checar(u"corte de cima vazio nao divide por zero, e nao remove",
               int((r[2] == 4).sum()) == 50)
    except ZeroDivisionError:
        checar(u"corte de cima vazio nao divide por zero", False)
    checar(u"o limiar e de area (mm2), e nao de voxels: 10 voxels de 1,1716 mm",
           abs(HN.LIMIAR_AREA_FATIA_MM2 - 10 * 1.1716 ** 2) < 1e-9)
    a = np.zeros((3, 30, 30), dtype="int8")
    a[1, 0:4, 0:5] = 4
    r_fino = HN.pos_processar(a, _grade((3.0, 0.5, 0.5)))
    checar(u"  20 voxels de 0,5 mm (5 mm2) saem; com o limiar em voxels "
           u"ficariam", not r_fino[1].any())


def teste_o_mapa_e_o_dos_autores():
    secao(u"o mapa rotulo -> nivel e o dos autores, preso aos pesos (C7-MAPA)")
    import hashlib
    import pickle
    import radai_hnlnl as HN
    autores = ("Level_1a", "Level_1b_left", "Level_1b_right", "Level_2_left",
               "Level_2_right", "Level_3_left", "Level_3_right",
               "Level_4a_left", "Level_4a_right", "Level_4b_left",
               "Level_4b_right", "Level_5_left", "Level_5_right", "Level_6a",
               "Level_6b", "Level_7a", "Level_7b_left", "Level_7b_right",
               "Level_8_left", "Level_8_right")
    romano = {"1a": "Ia", "1b": "Ib", "2": "II", "3": "III", "4a": "IVa",
              "4b": "IVb", "5": "V", "6a": "VIa", "6b": "VIb", "7a": "VIIa",
              "7b": "VIIb", "8": "VIII"}

    def _do_autor(n):
        p = n.split("_")[1:]
        return romano[p[0]] + ({"left": "_L", "right": "_R"}[p[1]]
                               if len(p) > 1 else "")
    esperado = dict((i + 1, _do_autor(n)) for i, n in enumerate(autores))
    checar(u"os 20 nomes batem com a LevelNameList dos autores",
           HN.MAPA_DOS_PESOS == esperado,
           str(sorted(set(HN.MAPA_DOS_PESOS.items()) ^ set(esperado.items()))))
    def _nomes_batem():
        return all(HN.nome_do_nivel(i) == "Lvl_" + esperado[i]
                   for i in range(1, 21))
    checar(u"os nomes que saem (nome_do_nivel 1 a 20) sao os dos autores",
           _nomes_batem())
    velho_niveis = HN.NIVEIS
    try:
        isca = dict((i, dict(n)) for i, n in HN.NIVEIS.items())
        isca[2]["candidato"], isca[3]["candidato"] = (
            isca[3]["candidato"], isca[2]["candidato"])
        HN.NIVEIS = isca
        reprova = not _nomes_batem()
    finally:
        HN.NIVEIS = velho_niveis
    checar(u"  ISCA: com 2 e 3 trocados no registro dos niveis, os nomes que "
           u"saem reprovam", reprova)
    checar(u"o nome sai do mapa com o mapa fixado (Lvl_IVa_L para o 8)",
           HN.nome_do_nivel(8) == "Lvl_IVa_L")
    checar(u"  e sem ele volta ao neutro (LNL08)",
           HN.nome_do_nivel(8, False) == "LNL08")
    checar(u"ORDEM_CONFERIDA significa mapa fixado pela versao dos pesos",
           HN.ORDEM_CONFERIDA is True)

    oficina = _cleanup.temporaria("radai_chk_hnl_")
    with io.open(os.path.join(oficina, "plans.pkl"), "wb") as f:
        pickle.dump({"all_classes": list(range(1, 21)), "num_classes": 20}, f)
    os.makedirs(os.path.join(oficina, "fold_0"))
    with io.open(os.path.join(oficina, "fold_0",
                              "model_final_checkpoint.model"), "wb") as f:
        f.write(b"x" * 1234)
    ok, motivo = HN.fixado(oficina)
    checar(u"um plans.pkl de outro sha256 nao fixa o mapa", not ok, motivo)
    checar(u"  e os nomes dessa serie voltam a LNL07, com a descricao neutra",
           HN.nome_do_nivel(7, ok) == "LNL07"
           and u"NAO foi atribuido" in HN.descricao_do_nivel(7, ok))
    sha = hashlib.sha256(io.open(os.path.join(oficina, "plans.pkl"),
                                 "rb").read()).hexdigest()
    velho = dict(HN.VERSAO_DOS_PESOS)
    try:
        HN.VERSAO_DOS_PESOS.update({"plans_sha256": sha, "fold0_bytes": 1234})
        checar(u"com o sha e o tamanho registrados, fixa",
               HN.fixado(oficina)[0], HN.fixado(oficina)[1])
        HN.VERSAO_DOS_PESOS["fold0_bytes"] = 999
        checar(u"  e o tamanho do fold 0 diferente nao fixa",
               not HN.fixado(oficina)[0])
        HN.VERSAO_DOS_PESOS.update({"fold0_bytes": 5000,
                                    "fold0_bytes_enxuto": 1234})
        checar(u"o fold 0 sem o estado do otimizador (o tamanho enxuto "
               u"registrado) fixa", HN.fixado(oficina)[0],
               HN.fixado(oficina)[1])
        HN.VERSAO_DOS_PESOS["fold0_bytes_enxuto"] = 999
        checar(u"  ISCA: tamanho que nao e nem o original nem o enxuto nao "
               u"fixa", not HN.fixado(oficina)[0])
        with io.open(os.path.join(oficina, "plans.pkl"), "wb") as f:
            pickle.dump({"all_classes": list(range(1, 22))}, f)
        HN.VERSAO_DOS_PESOS.update({"plans_sha256": hashlib.sha256(io.open(
            os.path.join(oficina, "plans.pkl"), "rb").read()).hexdigest(),
            "fold0_bytes": 1234})
        ok2, m2 = HN.fixado(oficina)
        checar(u"  ISCA: all_classes 1..21 nao fixa (mesmo com o sha "
               u"registrado)", not ok2, m2)
    finally:
        HN.VERSAO_DOS_PESOS.clear()
        HN.VERSAO_DOS_PESOS.update(velho)
    checar(u"a versao registrada e a da release nnUnet_model_export",
           HN.VERSAO_DOS_PESOS["release"] == "nnUnet_model_export"
           and HN.VERSAO_DOS_PESOS["plans_sha256"].startswith("9e5a6de4")
           and HN.VERSAO_DOS_PESOS["fold0_bytes"] == 246413947)
    import radai_models as RM
    reg = RM.MODELOS["hnlnl"]
    fold0 = ("3d_fullres/Task110_HNLNFixed_MirrorBest/"
             "nnUNetTrainerV2__nnUNetPlansv2.1/fold_0/"
             "model_final_checkpoint.model")
    checar(u"o tamanho do fold 0 e o do registro, nas duas formas (original "
           u"e sem o estado do otimizador)",
           dict(reg["conteudo"]).get(fold0) == HN.VERSAO_DOS_PESOS["fold0_bytes"]
           and (reg.get("enxuto") or {}).get(fold0, (None,))[0]
           == HN.VERSAO_DOS_PESOS.get("fold0_bytes_enxuto"))
    import radai_hnlnl_engine as HM
    base = HM.pasta_dos_pesos()
    if base:
        checar(u"os pesos desta instalacao estao na versao do mapa",
               HN.fixado(base)[0], HN.fixado(base)[1])


def teste_nomes_finais():
    secao(u"os nomes finais e as descricoes (C7-NOMES)")
    import engine as E
    import radai_hnlnl as HN
    tabela = {1: "Lvl_Ia_ai", 2: "Lvl_Ib_L_ai", 3: "Lvl_Ib_R_ai",
              4: "Lvl_II_L_ai", 5: "Lvl_II_R_ai", 6: "Lvl_III_L_ai",
              7: "Lvl_III_R_ai", 8: "Lvl_IVa_L_ai", 9: "Lvl_IVa_R_ai",
              10: "Lvl_IVb_L_ai", 11: "Lvl_IVb_R_ai", 12: "Lvl_V_L_ai",
              13: "Lvl_V_R_ai", 14: "Lvl_VIa_ai", 15: "Lvl_VIb_ai",
              16: "Lvl_VIIa_ai", 17: "Lvl_VIIb_L_ai", 18: "Lvl_VIIb_R_ai"}
    usados = set()
    saiu = dict((i, E.nome_clinico(HN.nome_do_nivel(i), usados))
                for i in range(1, 19))
    saiu["u"] = E.nome_clinico(HN.NOME_DA_UNIAO, usados)
    saiu["pl"] = E.nome_clinico(HN.PAROTIDAS_DO_VIII["left"], usados)
    saiu["pr"] = E.nome_clinico(HN.PAROTIDAS_DO_VIII["right"], usados)
    saiu["tl"] = E.nome_clinico(HN.PAROTIDAS_DO_TS["left"], usados,
                                sufixo="_ts")
    esperado = dict(tabela)
    esperado.update({"u": "LNL_UNION_ai", "pl": "Parotid_L_ai",
                     "pr": "Parotid_R_ai", "tl": "Parotid_L_ts"})
    checar(u"os 18 + a uniao + as 2 parotidas saem EXATAMENTE como na tabela "
           u"do autor (e a do TS com _ts)", saiu == esperado,
           str(sorted((k, v) for k, v in saiu.items() if esperado[k] != v)))
    checar(u"  todos cabem em 16", all(len(v) <= E.LIMITE_NOME
                                       for v in saiu.values()))
    desemp = E.nome_clinico(HN.nome_do_nivel(4), {"Lvl_II_L_ai"})
    checar(u"  ISCA: com o nome ja usado, nome_clinico devolve um desempate "
           u"que a tabela reprova", desemp != tabela[4], desemp)
    checar(u"o HNL_ leva Lvl_VIII_L_lnl",
           E.nome_clinico(HN.nome_do_nivel(19), sufixo=HN.SUFIXO)
           == "Lvl_VIII_L_lnl")
    todos = ([HN.nome_do_nivel(i) for i in range(1, 21)]
             + [HN.NOME_DA_UNIAO] + list(HN.PAROTIDAS_DO_VIII.values()))
    checar(u"conferir_saida aceita todos", HN.conferir_saida(todos))
    for ruim in ("Lvl_IX_L", "II_L", "Nodulo_suspeito", "LNL21"):
        try:
            HN.conferir_saida(["Lvl_Ia", ruim])
            checar(u"conferir_saida recusa `%s`" % ruim, False, "aceitou")
        except ValueError:
            checar(u"conferir_saida recusa `%s`" % ruim, True)
    nomes_gregoire = {8: u"jugular inferior", 10: u"supraclavicular medial",
                      14: u"jugular anterior", 15: u"paratraqueal",
                      16: u"retrofaringeo", 19: u"parotideo",
                      4: u"jugular superior", 6: u"jugular media"}
    for i in range(1, 21):
        d = HN.descricao_do_nivel(i)
        ok = (all(ord(c) < 128 for c in d) and len(d) < 700
              and u"NAO APROVADA" in d and u"nao e CTV" in d
              and u"10.3389/fonc.2023.1115258" in d and u"Putz" not in d
              and u"Henrique" not in d)
        if i in nomes_gregoire:
            ok = ok and nomes_gregoire[i] in d
        checar(u"a descricao do %s e ASCII, < 700, NAO APROVADA, nao e CTV, "
               u"doi, sem nome de pessoa" % HN.nome_do_nivel(i), ok, d[:80])
    checar(u"  ISCA: o IVa descrito como «superior» (a letra antiga) reprova",
           u"superior" not in HN.descricao_do_nivel(8)
           and u"superior" not in HN.descricao_do_nivel(9))
    du = HN.descricao_da_uniao()
    checar(u"a uniao diz que NAO E OAR NEM CTV, sem o VIII, e NAO APROVADA",
           u"NAO E OAR NEM CTV" in du and u"sem o nivel VIII" in du
           and u"NAO APROVADA" in du and all(ord(c) < 128 for c in du))
    dp = HN.descricao_da_parotida("left")
    checar(u"a parotida do VIII diz de onde vem e que tirou o ECM",
           u"nivel VIII" in dp and u"esternocleidomastoideo" in dp
           and u"NAO APROVADA" in dp and all(ord(c) < 128 for c in dp))
    pegos = []
    for n in todos:
        b = n
        for q in E._QUALIFICADORES:
            if b.endswith(q):
                b = b[:-len(q)]
                break
        if E._NIVEL.search(b):
            pegos.append(n)
    checar(u"nenhum nome cai em `_NIVEL` (numero de nivel vertebral)",
           not pegos, str(pegos))
    checar(u"e nenhum termina em `_I` (o qualificador de inferior)",
           not any(n.endswith("_I") for n in todos))


POS_3D = [1, 11, 17, 18, 19, 2, 20, 3, 4, 5, 6, 7, 8, 9]
POS_2D = [1, 10, 11, 17, 18, 19, 2, 20, 5, 6, 7]
POS_ENSEMBLE = [1, 10, 11, 13, 17, 18, 19, 2, 20, 6, 7]


def _json_do_pos(pasta, classes):
    import json
    if not os.path.isdir(pasta):
        os.makedirs(pasta)
    with io.open(os.path.join(pasta, "postprocessing.json"), "w",
                 encoding="utf-8") as f:
        f.write(json.dumps({"for_which_classes": classes,
                            "min_valid_object_sizes": "None"}))
    return pasta


def teste_o_pos_dos_pesos():
    secao(u"o postprocessing.json dos pesos em uso (C7-NNPP)")
    import radai_hnlnl as HN
    import radai_hnlnl_engine as HM
    g = _grade((3.0, 1.0, 1.0))
    oficina = _cleanup.temporaria("radai_chk_hnl_")
    p3 = _json_do_pos(os.path.join(oficina, "3d"), POS_3D)
    p2 = _json_do_pos(os.path.join(oficina, "2d"), POS_2D)
    rot = np.zeros((60, 40, 200), dtype="int8")
    rot[5:15, 10:20, 10:30] = 8
    rot[50:52, 10:12, 170:172] = 8
    rot[20:30, 20:30, 60:70] = 16
    rot[20:30, 20:30, 120:129] = 16
    rot[35:40, 5:10, 60:70] = 15
    rot[35:40, 5:10, 120:130] = 15
    r = HN.pos_dos_pesos(rot, p3, g)
    checar(u"classe 8 com uma ilha a 140 mm do corpo principal: a ilha sai",
           int((r == 8).sum()) == 2000 and not r[50, 10, 170])
    checar(u"classe 16 (VIIa) com os dois lados: os dois ficam",
           int((r == 16).sum()) == 1900)
    checar(u"classe 15 (VIb) idem", int((r == 15).sum()) == 500)
    todas = HN.pos_dos_pesos(rot, None, g, cfg={
        "for_which_classes": list(range(1, 21))})
    checar(u"  ISCA: o maior componente em TODAS as classes apaga um lado do "
           u"16", int((todas == 16).sum()) == 1000)
    r2 = HN.pos_dos_pesos(rot, p2, g)
    checar(u"  ISCA: o JSON do 2D (que nao lista o 8) deixa a ilha",
           bool(r2[50, 10, 170]))
    linhas = []
    r3 = HN.pos_dos_pesos(rot, os.path.join(oficina, "nada"), g,
                          log=linhas.append)
    checar(u"sem o arquivo: nao aplica, e o log diz",
           np.array_equal(r3, rot) and any(u"postprocessing.json" in l
                                           for l in linhas))
    r4 = HN.pos_dos_pesos(rot, None, g, cfg={
        "for_which_classes": [8], "min_valid_object_sizes": {"8": 5.0}})
    checar(u"min_valid_object_sizes (mm3) poupa o componente acima do minimo",
           bool(r4[50, 10, 170]))
    checar(u"a pasta do pos e a dos pesos em uso: a do ensemble",
           HN.pasta_do_pos(os.path.join("x", "3d_fullres", "T", "Tr"))
           .endswith(HM.PASTA_DO_ENSEMBLE))
    checar(u"  ISCA: a do 3D so no fold 0 de referencia",
           HN.pasta_do_pos("/x/3d_fullres/T/Tr", "3d_fold0")
           == "/x/3d_fullres/T/Tr")
    base = HM.pasta_dos_pesos()
    if base:
        cfg = HN.ler_pos_dos_pesos(base) or {}
        checar(u"o postprocessing.json do 3D desta instalacao e o transcrito",
               sorted(cfg.get("for_which_classes") or []) == sorted(POS_3D),
               str(cfg.get("for_which_classes")))
        cfg = HN.ler_pos_dos_pesos(HN.pasta_do_pos(base)) or {}
        checar(u"  e o do ensemble, o que a cadeia le, tambem",
               sorted(cfg.get("for_which_classes") or [])
               == sorted(POS_ENSEMBLE), str(cfg.get("for_which_classes")))


def teste_a_volta_nao_desloca():
    secao(u"a volta a grade original (C7-VOLTA)")
    from scipy import ndimage
    import radai_hnlnl as HN
    for esp, forma in (((2.0, 0.98, 0.98), (40, 70, 80)),
                       ((5.0, 0.7, 0.7), (16, 90, 100))):
        rot = np.zeros(forma, dtype="int8")
        rot[10:26, 20:41, 30:57] = 5
        rot[forma[0] // 2:, 50:60, 10:25] = 12
        fator = tuple(esp[i] / s for i, s in enumerate((3.0, 1.1716, 1.1716)))
        ida = ndimage.zoom(rot, fator, order=0, mode="nearest")
        volta = HN.voltar_a_grade(ida, forma)
        c0 = ndimage.center_of_mass(rot == 5)
        c1 = ndimage.center_of_mass(volta == 5)
        d = max(abs(a - b) for a, b in zip(c0, c1))
        checar(u"grade %s: o centroide volta a <= 0,5 voxel" % (esp,),
               d <= 0.5, u"%.2f voxel" % d)
        checar(u"  e nenhum rotulo que nao existia aparece",
               set(np.unique(volta)) <= set(np.unique(rot)),
               str(np.unique(volta)))
        checar(u"  e a forma e a do recorte", volta.shape == forma)
        inverso = tuple(forma[i] / float(ida.shape[i]) for i in range(3))
        velha = ndimage.zoom(ida, inverso, order=0, mode="nearest")
        velha = np.pad(velha[1:], ((0, 1), (0, 0), (0, 0)))
        cv = ndimage.center_of_mass(velha == 5)
        checar(u"  ISCA: a volta com o recorte deslocado de um voxel reprova "
               u"o centroide", max(abs(a - b) for a, b in zip(c0, cv)) > 0.5)


def _elipsoides_vizinhos(forma, esp):
    z, y, x = np.indices(forma).astype(float)
    zc, yc, xc = [n / 2.0 for n in forma]
    rot = np.zeros(forma, dtype="int8")
    defs = ((3, (0, 0, -18), (30, 12, 10)), (4, (0, 0, 18), (30, 12, 10)),
            (5, (-25, 0, -18), (18, 10, 9)), (6, (-25, 0, 18), (18, 10, 9)),
            (7, (20, 6, -30), (22, 8, 6)), (8, (20, 6, 30), (22, 8, 6)),
            (1, (-40, -15, 0), (8, 6, 12)), (17, (25, -12, 0), (10, 5, 6)))
    for r, (dz, dy, dx), (az, ay, ax) in defs:
        e = ((((z - zc) * esp[0] - dz) / az) ** 2
             + (((y - yc) * esp[1] - dy) / ay) ** 2
             + (((x - xc) * esp[2] - dx) / ax) ** 2)
        rot[(e <= 1.0) & (rot == 0)] = r
    return rot


def _volta_pelo_vizinho(rot_m, forma):
    from scipy import ndimage
    escala = [((rot_m.shape[e] - 1) / float(forma[e] - 1)) if forma[e] > 1
              else 0.0 for e in range(3)]
    return ndimage.affine_transform(np.asarray(rot_m), escala, offset=0.0,
                                    output_shape=forma, order=0,
                                    mode="nearest")


def teste_a_volta_linear_contra_o_vizinho():
    secao(u"a volta linear com argmax contra o vizinho mais proximo (L11)")
    from scipy import ndimage
    import radai_hnlnl as HN

    def _dsc_medio(volta, rot):
        ds = []
        for r in sorted(set(np.unique(rot).tolist()) - {0}):
            a, b = rot == r, volta == r
            ds.append(2.0 * (a & b).sum() / float(a.sum() + b.sum()))
        return float(np.mean(ds))

    for esp, forma in (((2.0, 0.98, 0.98), (60, 80, 110)),
                       ((5.0, 0.7, 0.7), (26, 110, 150)),
                       ((0.62, 0.66, 0.66), (160, 90, 120))):
        rot = _elipsoides_vizinhos(forma, esp)
        fator = tuple(esp[i] / s for i, s in enumerate((3.0, 1.1716, 1.1716)))
        ida = ndimage.zoom(rot, fator, order=0, mode="nearest")
        lin = _dsc_medio(HN.voltar_a_grade(ida, forma), rot)
        viz = _dsc_medio(_volta_pelo_vizinho(ida, forma), rot)
        checar(u"grade %s: a volta linear fica mais perto do original que o "
               u"vizinho (DSC medio)" % (esp,), lin > viz + 0.005,
               u"linear %.4f, vizinho %.4f" % (lin, viz))
    velho = HN.voltar_a_grade
    try:
        HN.voltar_a_grade = _volta_pelo_vizinho
        isca = _dsc_medio(HN.voltar_a_grade(ida, forma), rot)
    finally:
        HN.voltar_a_grade = velho
    checar(u"  ISCA: com a volta trocada pelo vizinho, a checagem reprova",
           not (isca > viz + 0.005), u"%.4f" % isca)


def teste_lado_invertido_recusa():
    secao(u"a conferencia de lado (C7-LADO)")
    import radai_hnlnl as HN
    g = _grade((3.0, 1.0, 1.0))
    rot = np.zeros((20, 40, 60), dtype="int8")
    for k, (a, b) in enumerate(HN.PARES_DE_LADO):
        rot[2 + 2 * k, 5:15, 40:50] = a
        rot[2 + 2 * k, 5:15, 10:20] = b
    ok, laudo = HN.conferir_lado(rot, g)
    checar(u"os pares no lado certo passam", ok, u" | ".join(laudo))
    trocado = rot[:, :, ::-1].copy()
    ok2, laudo2 = HN.conferir_lado(trocado, g)
    checar(u"o mesmo com x invertido depois da rede: recusa", not ok2,
           u" | ".join(laudo2))
    checar(u"  e o log diz lados invertidos e que nao entrega",
           any(u"lados invertidos em 8 de 8" in l and u"nao entregues" in l
               for l in laudo2))
    um = rot.copy()
    um[rot == 2] = 3
    um[rot == 3] = 2
    ok3, laudo3 = HN.conferir_lado(um, g)
    checar(u"um par trocado (menos da metade): entrega, com ALERTA",
           ok3 and any(u"ALERTA" in l for l in laudo3), u" | ".join(laudo3))
    velho_pares = HN.PARES_DE_LADO
    try:
        HN.PARES_DE_LADO = tuple((b, a) for a, b in velho_pares)
        ok_isca, _l = HN.conferir_lado(rot, g)
    finally:
        HN.PARES_DE_LADO = velho_pares
    checar(u"  ISCA: com a convencao de lado invertida nos pares, o volume "
           u"certo e recusado", not ok_isca)


def teste_par_trocado_perde_o_nome_de_lado():
    secao(u"um par trocado, ou um rotulo do lado errado, nao sai com _L/_R")
    import radai_hnlnl as HN
    g = _grade((3.0, 1.0, 1.0))
    rot = np.zeros((20, 40, 60), dtype="int8")
    for k, (a, b) in enumerate(HN.PARES_DE_LADO):
        rot[2 + 2 * k, 5:15, 40:50] = a
        rot[2 + 2 * k, 5:15, 10:20] = b
    fora, _l = HN.lados_suspeitos(rot, g)
    checar(u"os pares certos: nenhum suspeito", not fora, str(sorted(fora)))
    viii = rot.copy()
    viii[rot == 19] = 20
    viii[rot == 20] = 19
    ok, _l = HN.conferir_lado(viii, g)
    fora, laudo = HN.lados_suspeitos(viii, g)
    checar(u"7 pares certos e o VIII trocado: a serie passa, e o VIII e "
           u"suspeito", ok and fora == {19, 20}, u" | ".join(laudo))
    pub = HN.masks_dos_niveis(viii, minimo_voxels=1, camada="publicado",
                              sem_lado=fora)
    inteiro = HN.masks_dos_niveis(viii, minimo_voxels=1, camada="publicado")
    checar(u"  o HNL_ sai sem Lvl_VIII_L/Lvl_VIII_R",
           "Lvl_VIII_L" not in pub and "Lvl_VIII_R" not in pub
           and "Lvl_II_L" in pub, str(sorted(pub)))
    checar(u"  ISCA: sem `sem_lado`, o VIII trocado sairia com o nome",
           "Lvl_VIII_L" in inteiro)
    ib = rot.copy()
    ib[rot == 2] = 3
    ib[rot == 3] = 2
    fin = HN.masks_dos_niveis(ib, minimo_voxels=1, camada="final",
                              sem_lado=HN.lados_suspeitos(ib, g)[0])
    checar(u"um par da uniao trocado: sai sem nome e continua na uniao",
           "Lvl_Ib_L" not in fin and "Lvl_Ib_R" not in fin
           and int(fin[HN.NOME_DA_UNIAO].sum())
           == int(((ib >= 1) & (ib <= 18)).sum()), str(sorted(fin)))
    so = rot.copy()
    so[rot == 20] = 0
    so[rot == 19] = 0
    so[2 + 2 * 7, 5:15, 10:20] = 19
    ok_so, laudo_so = HN.conferir_lado(so, g)
    fora_so, laudo2 = HN.lados_suspeitos(so, g)
    checar(u"o VIII_L sozinho do lado direito: o par nao o confere, e a linha "
           u"media o acusa", ok_so and not any(u"ALERTA" in l for l in laudo_so)
           and fora_so == {19}, u" | ".join(laudo2))
    meio = rot.copy()
    meio[3, 20:30, 28:32] = 14
    meio[4, 20:30, 28:32] = 16
    meio[rot == 20] = 0
    meio[rot == 19] = 0
    meio[2 + 2 * 7, 5:15, 10:20] = 19
    checar(u"  com os niveis de linha media presentes, a linha e a deles",
           HN.lados_suspeitos(meio, g)[0] == {19})

    c, forma = _pescoco_sintetico()
    saida, linhas, ch = _cadeia_com_filho_falso("viii_trocado", c, forma, g,
                                                fixar=True)
    pub = getattr(saida, "publicado", None) or {}
    checar(u"na cadeia: o VIII trocado nao vira parotida (`viii` vazio)",
           saida and not getattr(saida, "viii", None)
           and "Lvl_Ib_L" in saida, str(sorted(saida)))
    checar(u"  nem sai com o nome no HNL_",
           "Lvl_VIII_L" not in pub and "Lvl_VIII_R" not in pub
           and "Lvl_Ib_L" in pub, str(sorted(pub)))
    checar(u"  e o log diz por que", any(u"VIII_L/VIII_R" in l
                                         and u"sem nome de lado" in l
                                         for l in linhas))


def teste_ilhas_por_nivel():
    secao(u"ilhas por nivel, preservando o bilateral (C7-ILHAS)")
    import radai_geom
    import radai_hnlnl as HN
    g = _grade((3.0, 1.0, 1.0))
    rot = np.zeros((60, 40, 100), dtype="int8")
    rot[20:30, 10:20, 80:90] = 12
    rot[20:24, 10:14, 10:14] = 12
    rot[30:34, 25:30, 45:48] = 15
    rot[30:34, 25:30, 52:55] = 15
    rot[30:40, 5:15, 45:55] = 14
    rot[10:12, 5:8, 48:51] = 14
    rot[40:50, 30:36, 40:46] = 16
    rot[40:47, 30:35, 54:59] = 16
    rot[20:30, 10:20, 15:25] = 13
    rot[40:50, 10:20, 65:75] = 2
    rot[40:50, 10:20, 25:35] = 3
    sai = []
    r = HN.limpar_ilhas(rot, g, removidos=sai)
    checar(u"V_L (fora do JSON do 3D) com uma ilha do lado direito: sai",
           int((r == 12).sum()) == 1000, str(int((r == 12).sum())))
    checar(u"VIb com os dois paratraqueais na mesma altura: ficam",
           int((r == 15).sum()) == int((rot == 15).sum()))
    checar(u"VIa com uma ilha 60 mm abaixo e 5% do volume: sai",
           int((r == 14).sum()) == 1000 and not r[10:12, 5:8, 48:51].any())
    checar(u"VIIa bilateral com um lado de 30%: fica",
           int((r == 16).sum()) == int((rot == 16).sum()))
    checar(u"o que sai vai ao registro (nivel, cm3, distancia em mm)",
           len(sai) == 2 and all(len(t) == 3 for t in sai), str(sai))
    m = dict((i, rot == i) for i in (12, 14, 15, 16))
    isca = np.zeros_like(rot)
    for i, mm in m.items():
        isca[radai_geom.maior_componente(mm)] = i
    checar(u"  ISCA: o maior componente em todos apaga o VIb legitimo",
           int((isca == 15).sum()) < int((rot == 15).sum()))


def teste_cavidade_vascular():
    secao(u"a cavidade vascular de II/III/IVa, por corte (C7-VASO)")
    import radai_hnlnl as HN
    g = _grade((3.0, 1.0, 1.0))
    forma = (20, 60, 100)
    yy, xx = np.mgrid[0:forma[1], 0:forma[2]]

    def _circ(cy, cx, r2):
        return ((yy - cy) ** 2 + (xx - cx) ** 2) <= r2

    def _em(arr, z0, z1, m2, v):
        for z in range(z0, z1):
            arr[z][m2] = v
    disco = _circ(30, 70, 16)
    anel = _circ(30, 70, 64) & ~disco
    perto_r = _circ(30, 80, 4)
    longe = _circ(30, 94, 9)
    centro = _circ(30, 70, 1)
    buraco_ib = _circ(30, 20, 36) & ~_circ(30, 20, 4)
    rot = np.zeros(forma, dtype="int8")
    _em(rot, 4, 10, anel, 6)
    _em(rot, 4, 10, centro, 12)
    _em(rot, 4, 10, perto_r, 0)
    _em(rot, 4, 10, buraco_ib, 2)
    jug_l = np.zeros(forma, bool)
    _em(jug_l, 4, 14, disco, True)
    _em(jug_l, 4, 10, longe, True)
    jug_r = np.zeros(forma, bool)
    _em(jug_r, 4, 10, perto_r, True)
    vasos = {"internal_jugular_vein_left": jug_l,
             "internal_jugular_vein_right": jug_r}
    r = HN.preencher_cavidade_vascular(rot, vasos, g)
    d_ok = disco & ~centro
    checar(u"o disco da jugular esquerda entra nos 6 cortes do nivel",
           all((r[z][d_ok] == 6).all() for z in range(4, 10)))
    checar(u"  e NAO nos 4 cortes de cima, sem o nivel",
           not any((r[z] == 6).any() for z in range(10, 14)))
    checar(u"a jugular direita no mesmo corte nao entra",
           not any((r[z][perto_r] == 6).any() for z in range(4, 10)))
    checar(u"o vaso longe do nivel nao entra",
           not any((r[z][longe] == 6).any() for z in range(4, 10)))
    checar(u"o voxel do vaso ja rotulado V_L continua V_L",
           int((r == 12).sum()) == int((rot == 12).sum()))
    checar(u"o Ib (2) com buraco nao e preenchido",
           int((r == 2).sum()) == int((rot == 2).sum()))
    com_nivel = rot.copy()
    _em(com_nivel, 10, 14, anel, 6)
    r_isca = HN.preencher_cavidade_vascular(com_nivel, vasos, g)
    checar(u"  ISCA: com o nivel tambem nos 4 cortes de cima, o disco entra "
           u"neles (o corte sem o nivel e o que o deixa fora)",
           all((r_isca[z][d_ok] == 6).all() for z in range(10, 14)))
    trocado = HN.preencher_cavidade_vascular(
        rot, {"internal_jugular_vein_left": jug_r}, g)
    checar(u"  ISCA: com o vaso do lado trocado, a jugular direita entraria",
           any((trocado[z][perto_r] == 6).any() for z in range(4, 10)))
    linhas = []
    HN.preencher_cavidade_vascular(rot, {}, g, log=linhas.append)
    checar(u"sem a task dos vasos: so o preenchimento de buraco, e o log diz "
           u"qual vaso faltou", any(u"internal_jugular_vein_left" in l
                                    for l in linhas), u" | ".join(linhas))


def teste_suavizacao_dos_niveis():
    secao(u"o acabamento de pequenas estruturas: so no plano (C7-PEQ)")
    import radai_geom
    import radai_hnlnl as HN
    g = _grade((3.0, 0.5, 0.5))
    forma = (12, 80, 80)
    rot = np.zeros(forma, dtype="int8")
    yy, xx = np.mgrid[0:80, 0:80]
    for z in range(1, 11):
        corte = (xx > 10) & (xx < 70) & (yy > 10) & (yy < 70)
        rot[z][corte & ((xx // 3) + (yy // 3) + z < 30)] = 4
        rot[z][corte & ((xx // 3) + (yy // 3) + z >= 30)] = 6
    rot[11][20:30, 20:30] = 6
    r = HN.suavizar_niveis(rot, g)
    mesmos = all(set(np.unique(r[z])) == set(np.unique(rot[z]))
                 for z in range(forma[0]))
    checar(u"o conjunto de rotulos de cada corte e identico antes e depois",
           mesmos)
    for i in (4, 6):
        v0, v1 = int((rot == i).sum()), int((r == i).sum())
        checar(u"o volume de %s fica a +-3%%" % HN.nome_do_nivel(i),
               abs(v1 - v0) <= 0.03 * v0, u"%d -> %d" % (v0, v1))

    def _perimetro(m):
        return int(np.count_nonzero(m[:, 1:] != m[:, :-1])
                   + np.count_nonzero(m[1:, :] != m[:-1, :]))
    p0 = sum(_perimetro(rot[z] == 4) for z in range(forma[0]))
    p1 = sum(_perimetro(r[z] == 4) for z in range(forma[0]))
    checar(u"a serrilha (perimetro 2D) cai", p1 < p0, u"%d -> %d" % (p0, p1))
    partes = dict((i, rot == i) for i in (4, 6))
    isca = radai_geom.suavizar_conjunto(partes, 3.0, g)
    checar(u"  ISCA: com sigma em z o II aparece num corte so de III",
           bool(isca[4][11].any()))
    checar(u"a constante e a das pequenas estruturas (0,8 mm)",
           HN.SUAVIZACAO_DOS_NIVEIS_MM == 0.8)
    import engine as E
    checar(u"os nomes novos nunca sao podados (`lvl_`) e nao sao suavizados "
           u"de novo no FULL", "lvl_" in E.NUNCA_PODA_PREFIXOS
           and E.SUAVIZACAO.get("Lvl_II_L") == 0.0
           and E.SUAVIZACAO.get("LNL_UNION") == 0.0)


def _delta_e(a, b):
    def lab(c):
        def lin(v):
            v = v / 255.0
            return ((v + 0.055) / 1.055) ** 2.4 if v > 0.04045 else v / 12.92
        r, g_, b_ = (lin(float(x)) for x in c)
        x = (0.4124 * r + 0.3576 * g_ + 0.1805 * b_) / 0.95047
        y = (0.2126 * r + 0.7152 * g_ + 0.0722 * b_) / 1.0
        z = (0.0193 * r + 0.1192 * g_ + 0.9505 * b_) / 1.08883

        def f(t):
            return t ** (1.0 / 3) if t > 0.008856 else 7.787 * t + 16.0 / 116
        return (116 * f(y) - 16, 500 * (f(x) - f(y)), 200 * (f(y) - f(z)))
    la, lb = lab(a), lab(b)
    return sum((p - q) ** 2 for p, q in zip(la, lb)) ** 0.5


VIZINHOS_DE_MATIZ = (("Ia", "Ib"), ("Ib", "II"), ("II", "III"),
                     ("III", "IVa"), ("IVa", "IVb"), ("IVa", "V"),
                     ("IVb", "V"), ("II", "V"), ("III", "V"), ("II", "VIb"),
                     ("VIa", "VIb"), ("IVa", "VIb"), ("II", "VIIb"),
                     ("II", "VIII"))


def teste_cores_dos_niveis():
    secao(u"uma cor por nivel, tons por lado (C7-CORES)")
    import colorsys
    import engine as E
    import radai_hnlnl as HN
    tabela = {"Ia": ([77, 182, 235], None),
              "Ib": ([255, 202, 97], [184, 138, 48]),
              "II": ([229, 97, 255], [161, 48, 184]),
              "III": ([97, 176, 255], [48, 116, 184]),
              "IVa": ([255, 150, 97], [184, 93, 48]),
              "IVb": ([97, 242, 255], [48, 173, 184]),
              "V": ([255, 97, 163], [184, 48, 104]),
              "VIa": ([77, 235, 104], None), "VIb": ([117, 77, 235], None),
              "VIIa": ([169, 235, 77], None),
              "VIIb": ([97, 110, 255], [48, 59, 184])}
    certas = True
    for raiz, (cl, es) in tabela.items():
        if es is None:
            certas &= E._color("Lvl_" + raiz) == cl
        else:
            certas &= (E._color("Lvl_%s_L" % raiz) == cl
                       and E._color("Lvl_%s_R" % raiz) == es)
    checar(u"cada nivel tem a cor da tabela (pelo motor)", certas)
    checar(u"a parotida do VIII e a uniao tambem",
           E._color("parotid_lnl_left") == [0, 221, 160]
           and E._color("parotid_lnl_right") == [0, 176, 128]
           and E._color("LNL_UNION") == [210, 210, 210])
    lados = True
    for raiz, (cl, es) in tabela.items():
        if es is None:
            continue
        h1, _s1, v1 = colorsys.rgb_to_hsv(*[c / 255.0 for c in cl])
        h2, _s2, v2 = colorsys.rgb_to_hsv(*[c / 255.0 for c in es])
        dh = min(abs(h1 - h2), 1 - abs(h1 - h2)) * 360
        lados &= dh <= 10 and abs(v1 - v2) > 0.1
    checar(u"_L e _R do mesmo nivel: matiz a +-10 graus e V diferente", lados)
    viz = set()
    for a, b in HN.GRUPOS_DE_CONFLITO["pares"]:
        viz.add((a, b))
    for g in (HN.GRUPOS_DE_CONFLITO["trios"]
              + HN.GRUPOS_DE_CONFLITO["quadruplas"]):
        for o in g[1:]:
            viz.add((g[0], o))
    piores = []
    for a, b in sorted(viz):
        d = _delta_e(E._color(HN.nome_do_nivel(a)),
                     E._color(HN.nome_do_nivel(b)))
        if d < 25:
            piores.append((HN.nome_do_nivel(a), HN.nome_do_nivel(b),
                           round(d, 1)))
    checar(u"dE76 >= 25 entre todo par vizinho (os grupos de conflito)",
           not piores, str(piores))

    def _matiz(c):
        return colorsys.rgb_to_hsv(*[x / 255.0 for x in c])[0] * 360

    def _perto(tab):
        fora = []
        for a, b in VIZINHOS_DE_MATIZ:
            for la in ((0, 1) if tab[a][1] else (0,)):
                for lb in ((0, 1) if tab[b][1] else (0,)):
                    d = abs(_matiz(tab[a][la]) - _matiz(tab[b][lb]))
                    d = min(d, 360 - d)
                    if d < 30:
                        fora.append((a, b, round(d)))
        return fora
    checar(u"vizinhos anatomicos com matizes a 30 graus ou mais",
           not _perto(HN._CORES_POR_NIVEL), str(_perto(HN._CORES_POR_NIVEL)))
    velha = dict(HN._CORES_POR_NIVEL)
    velha["IVb"] = ([255, 97, 215], [184, 48, 150])
    velha["VIb"] = ([182, 77, 235], None)
    checar(u"  ISCA: a tabela de antes (IVb rosa ao lado do V, VIb ao lado do "
           u"II) reprova", len(_perto(velha)) >= 2, str(_perto(velha)))
    hashes = [n for n in HN.CORES_DOS_NIVEIS
              if E._color(n) == E._cor_derivada(
                  E._nomes.canonico(n).lower(), E.familia_de(
                      E._nomes.canonico(n).lower()))]
    checar(u"nenhuma vem de `_cor_derivada`", not hashes, str(hashes))
    checar(u"e todas estao em `CORES_A_CONFERIR`",
           set(HN.CORES_DOS_NIVEIS) <= set(E.CORES_A_CONFERIR))
    velho = dict(E._CORES_NIVEIS)
    try:
        E._CORES_NIVEIS.clear()
        checar(u"  ISCA: sem a tabela, o nivel cai na cor derivada",
               E._color("Lvl_II_L") != [229, 97, 255])
    finally:
        E._CORES_NIVEIS.update(velho)


def teste_textos_dos_niveis():
    secao(u"as frases de tela dos niveis (C7-TEXTOS)")
    import radai_batch as B
    import radai_modes as M
    import radai_phrases as P
    import radai_sets as S
    hn = M.MOT_POR_COD.get("hnlnl") or {}
    fontes = {u"modes.caixa": hn.get("caixa") or u"",
              u"modes.ajuda": hn.get("ajuda") or u"",
              u"sets.hnl": S.POR_COD["hnl"].get("ajuda") or u"",
              u"protocolo.cabeca_pescoco": next(
                  (p.get("ajuda") for p in M.PROTOCOLOS
                   if p.get("cod") == "cabeca_pescoco"), u"") or u""}
    est = B._estruturas_dos_niveis()
    checar(u"nenhuma fonte diz «LNL01 a LNL20» nem «ainda não atribuído»",
           not any(u"LNL01 a LNL20" in t or u"ainda não atribuído" in t
                   for t in fontes.values()),
           str([k for k, t in fontes.items() if u"LNL01" in t]))
    checar(u"  e a caixa diz a uniao e as parotidas no OAR",
           u"união" in fontes[u"modes.caixa"]
           and u"parótidas" in fontes[u"modes.caixa"])
    checar(u"  e a ajuda diz que a uniao nao e OAR nem CTV",
           u"não é OAR nem CTV" in fontes[u"modes.ajuda"])
    _pc = fontes[u"protocolo.cabeca_pescoco"]
    checar(u"  e a ajuda do protocolo C&P nao nega o OAR: diz a uniao e as "
           u"parotidas do VIII", u"nunca no OAR" not in _pc
           and u"LNL_UNION" in _pc and u"parótidas do nível VIII" in _pc, _pc)
    checar(u"a lista de estruturas do motor e a dos nomes novos",
           est[:2] == ["Lvl_Ia", "Lvl_Ib_L"] and "LNL_UNION" in est
           and "Parotid_L" in est and not any(e.startswith("LNL0")
                                              for e in est), str(est))
    d = P.construir()
    for chave in sorted(fontes):
        pt = P.normalizar(fontes[chave])
        faltam = [c for c in P.CODIGOS if pt not in d[c]]
        checar(u"%s traduzida nos onze idiomas" % chave, not faltam,
               str(faltam))
    checar(u"  ISCA: a frase velha nao tem mais traducao (saiu da tabela)",
           not any(u"LNL01 a LNL20" in k for k in d["en"]))
    checar(u"  ISCA: a ajuda velha do protocolo C&P saiu da tabela",
           not any(u"(no FULL, nunca no OAR)" in k for k in d["en"]))


def teste_uniao():
    secao(u"a LNL_UNION e o OR exato das mascaras finais 01-18 (C8-UNIAO)")
    import radai_hnlnl as HN
    rot = np.zeros((6, 30, 30), dtype="int8")
    rot[2, 5:15, 5:15] = 1
    rot[3, 5:15, 15:25] = 2
    rot[4, 0:1, 0:2] = 3
    rot[1, 20:30, 0:10] = 19
    rot[1, 20:30, 20:30] = 20
    masks = HN.masks_dos_niveis(rot)
    partes = [k for k in masks if k != HN.NOME_DA_UNIAO]
    ou = np.zeros(rot.shape, bool)
    for k in partes:
        ou |= masks[k]
    checar(u"os niveis com volume viram mascara com o nome do mapa",
           sorted(partes) == ["Lvl_Ia", "Lvl_Ib_L"], str(sorted(partes)))
    checar(u"a uniao e o OR exato das mascaras entregues 01-18",
           np.array_equal(masks[HN.NOME_DA_UNIAO], ou))
    checar(u"  o nivel abaixo do minimo nao entra nela",
           not masks[HN.NOME_DA_UNIAO][4].any())
    checar(u"  e os voxels do VIII nao estao nela",
           not masks[HN.NOME_DA_UNIAO][1].any())
    checar(u"  e o VIII nao vai ao FULL como nivel",
           "Lvl_VIII_L" not in masks)
    checar(u"  ISCA: a uniao de antes (rot != 0) tem o VIII e o descartado",
           not np.array_equal(rot != 0, ou))
    pub = HN.masks_dos_niveis(rot, camada="publicado")
    checar(u"a camada publicada (HNL_) leva o VIII como Lvl_VIII_L/R, e a "
           u"mesma uniao dos 18", "Lvl_VIII_L" in pub and "Lvl_VIII_R" in pub
           and np.array_equal(pub[HN.NOME_DA_UNIAO], ou))
    neutro = HN.masks_dos_niveis(rot, fixado=False)
    checar(u"sem o mapa fixado: os 20 neutros e a uniao neutra dos 20",
           "LNL19" in neutro and HN.NOME_DA_UNIAO_NEUTRA in neutro
           and neutro[HN.NOME_DA_UNIAO_NEUTRA][1].any())
    checar(u"volume nenhum vira uniao vazia",
           not HN.masks_dos_niveis(np.zeros((4, 8, 8), dtype="int8")))


def teste_parotidas_do_viii_unidade():
    secao(u"a parotida do VIII menos o ECM, por lado (C8-PAROT)")
    import radai_hnlnl as HN
    g = _grade((3.0, 1.0, 1.0))
    forma = (10, 40, 60)
    v_l = np.zeros(forma, bool)
    v_l[2:8, 10:20, 40:50] = True
    v_r = np.zeros(forma, bool)
    v_r[2:8, 10:20, 10:20] = True
    ecm_l = np.zeros(forma, bool)
    ecm_l[2:8, 15:20, 40:50] = True
    v_l[2, 10:12, 30:32] = True
    feitas, motivos = HN.parotidas_do_viii(
        {"left": v_l, "right": v_r}, {"left": ecm_l}, g)
    p = feitas.get("parotid_lnl_left")
    checar(u"a parotida esquerda = VIII menos o ECM (sobreposicao zero)",
           p is not None and not (p & ecm_l).any(), str(sorted(feitas)))
    checar(u"  a lasca solta (< 0,1 cm3 e < 5% do maior) sai",
           p is not None and not p[2, 10:12, 30:32].any()
           and int(p.sum()) == 300, str(None if p is None else int(p.sum())))
    ecm_longe = np.zeros(forma, bool)
    ecm_longe[2:8, 30:35, 40:50] = True
    f_isca, _m = HN.parotidas_do_viii({"left": v_l}, {"left": ecm_longe}, g)
    p_isca = f_isca.get("parotid_lnl_left")
    checar(u"  ISCA: com o ECM em outro lugar, a regiao que ele tirava fica "
           u"na parotida", p_isca is not None and bool((p_isca & ecm_l).any()))
    checar(u"sem o ECM direito, o lado direito nao e substituido, e diz",
           "parotid_lnl_right" not in feitas
           and u"esternocleidomastoideo" in motivos.get("right", u""))
    f2, m2 = HN.parotidas_do_viii({"right": v_r}, {"right": ecm_l}, g)
    checar(u"sem o VIII esquerdo, o esquerdo nao sai, e diz",
           "parotid_lnl_left" not in f2 and u"nivel VIII" in m2.get("left"))


def teste_extensao():
    secao(u"a regua dos 30 mm, sobre a uniao 01-18 (C7-EXT)")
    import radai_hnlnl as HN
    g = _grade()
    c, forma = _pescoco_sintetico()
    perto = {HN.NOME_DA_UNIAO: _bloco(forma, (22, 50), (40, 60), (50, 90))}
    ok, m = HN.conferir_extensao(perto, c, g)
    checar(u"uniao que para perto da clavicula passa", ok, m)
    longe = {HN.NOME_DA_UNIAO: _bloco(forma, (0, 50), (40, 60), (50, 90))}
    ok2, m2 = HN.conferir_extensao(longe, c, g)
    checar(u"uniao que desce ate o torax e MARCADA", not ok2, m2[:60])
    checar(u"  e o motivo traz os milimetros", "mm abaixo" in m2)
    sem_clav = Cruas(c)
    del sem_clav["clavicula_left"]
    del sem_clav["clavicula_right"]
    ok3, m3 = HN.conferir_extensao(longe, sem_clav, g)
    checar(u"sem clavicula ela nao reprova, e diz por que", ok3, m3[:50])
    checar(u"e uniao vazia nao quebra", HN.conferir_extensao({}, c, g)[0])
    rot = np.zeros(forma, dtype="int8")
    rot[30:50, 40:60, 50:70] = 4
    rot[0:50, 40:60, 80:90] = 19
    masks = HN.masks_dos_niveis(rot)
    med = HN.medir_extensao(masks, c, g)
    checar(u"um VIII que desce ate o torax nao move a medida (a uniao e 01-18)",
           med["ok"] and (med["desce_mm"] or 0) == 0, str(med))
    isca = HN.medir_extensao({HN.NOME_DA_UNIAO: rot != 0}, c, g)
    checar(u"  ISCA: medir rot != 0 marcaria o estudo", not isca["ok"])
    med = HN.medir_extensao(longe, c, g)
    checar(u"a medida devolve o NUMERO (mm abaixo do topo das claviculas)",
           med["ok"] is False and med["desce_mm"] is not None
           and med["desce_mm"] > HN.FOLGA_ABAIXO_DA_CLAVICULA_MM, str(med))
    txt = HN.texto_da_extensao(med)
    checar(u"a frase da medida diz ESTUDO MARCADO, o numero e a folga, em "
           u"ASCII", u"ESTUDO MARCADO" in txt
           and (u"%.0f mm" % med["desce_mm"]) in txt
           and all(ord(ch) < 128 for ch in txt), txt)
    niv = HN.NiveisDaSerie({"Lvl_IVb_L": longe[HN.NOME_DA_UNIAO],
                            HN.NOME_DA_UNIAO: longe[HN.NOME_DA_UNIAO]})
    niv.extensao = med
    obs = HN.observacoes_dos_niveis(niv)
    checar(u"a medida vai na descricao de CADA ROI (nivel e uniao), lida do "
           u"dicionario", all(u"ESTUDO MARCADO" in v for v in obs.values())
           and set(obs) == {"Lvl_IVb_L", HN.NOME_DA_UNIAO}, str(sorted(obs)))
    checar(u"  e cabe no campo (ST, 1024)",
           all(len(v) < 1024 for v in obs.values()),
           str(max(len(v) for v in obs.values())))
    checar(u"ISCA: com `list()` a medida se perde (quem chama passa o "
           u"dicionario)", not any(u"ESTUDO MARCADO" in v for v in
                                   HN.observacoes_dos_niveis(
                                       list(niv)).values()))
    fonte = io.open(_componentes.fonte("app/radai_hnlnl.py"),
                    encoding="utf-8").read()
    checar(u"`rodar_na_serie` NAO recusa pela extensao: devolve o estudo com "
           u"a medida (`NiveisDaSerie`)", _marca_em_vez_de_recusar(fonte))


def _plans_sintetico(base, patch=(8, 16, 16)):
    import pickle as _pickle
    with io.open(os.path.join(base, "plans.pkl"), "wb") as f:
        _pickle.dump({
            "plans_per_stage": {0: {"patch_size": list(patch),
                                    "current_spacing": [3.0, 1.0, 1.0],
                                    "pool_op_kernel_sizes": [[1, 2, 2]]}},
            "dataset_properties": {"intensityproperties": {0: {
                "percentile_00_5": -1000.0, "percentile_99_5": 2000.0,
                "mean": 0.0, "sd": 100.0}}},
            "num_classes": 20}, f)


def _cadeia_com_filho_falso(modo, cruas, forma, grade, vol=None, vasos=None,
                            fixar=False):
    import radai_hnlnl as HN
    import radai_hnlnl_engine as HM
    oficina = _cleanup.temporaria("radai_chk_hnl_")
    script = os.path.join(oficina, "filho_falso.py")
    with io.open(script, "w", encoding="utf-8") as f:
        f.write(_FILHO_FALSO)
    base = os.path.join(oficina, "pesos")
    os.makedirs(base)
    _plans_sintetico(base)
    with io.open(os.path.join(base, "modo.txt"), "w") as f:
        f.write(modo)
    guard = (HM._SCRIPT_DO_FILHO, HN.disponivel, HN.fixado)
    linhas = []
    try:
        HM._SCRIPT_DO_FILHO = script
        HN.disponivel = lambda: (True, base)
        if fixar:
            HN.fixado = lambda b: (True, u"mapa fixado (bateria)")
        if vol is None:
            vol = np.full(forma, 40.0, dtype="float32")
        saida = HN.rodar_na_serie(vol, cruas, forma, grade, log=linhas.append,
                                  vasos=vasos)
    finally:
        HM._SCRIPT_DO_FILHO, HN.disponivel, HN.fixado = guard
    try:
        with io.open(os.path.join(base, "chamadas.jsonl")) as f:
            import json as _json
            ch = [_json.loads(l) for l in f if l.strip()]
    except (IOError, OSError):
        ch = []
    return saida, linhas, ch


def _lat_media(m, grade):
    eixo, s = grade.eixo_sinal("esq")
    onde = np.nonzero(np.asarray(m))[eixo]
    return s * float(np.mean(onde)) * grade.spacing[eixo]


def _virar(c, eixos):
    fora = Cruas()
    for k in c:
        fora[k] = np.flip(np.asarray(c[k]), eixos).copy()
    return fora


def teste_a_rede_ve_sempre_a_mesma_orientacao():
    secao(u"a rede ve sempre a orientacao canonica (C7-ORIENT)")
    import radai_geom
    c, forma = _pescoco_sintetico()
    casos = (("sup/post/esq", (), ("sup", "post", "esq")),
             ("dir (x invertido)", (2,), ("sup", "post", "dir")),
             ("inf e dir (z e x)", (0, 2), ("inf", "post", "dir")))
    for nome, eixos, sentido in casos:
        g = _grade(sentido=sentido)
        cr = _virar(c, eixos) if eixos else c
        saida, linhas, ch = _cadeia_com_filho_falso("metade", cr, forma, g)
        ok = ("LNL02" in saida and "LNL03" in saida
              and _lat_media(saida["LNL02"], g) > _lat_media(saida["LNL03"], g))
        checar(u"%s: o rotulo 2 sai do lado ESQUERDO do paciente" % nome, ok,
               u" | ".join(l for l in linhas if u"lado" in l)[:160]
               or str(sorted(saida)))
    velho = (radai_geom.para_canonico, radai_geom.grade_canonica)
    try:
        radai_geom.para_canonico = lambda a, g: np.asarray(a)
        radai_geom.grade_canonica = lambda g: g
        g = _grade(sentido=("sup", "post", "dir"))
        saida, linhas, ch = _cadeia_com_filho_falso("metade", _virar(c, (2,)),
                                                    forma, g)
        certo = ("LNL02" in saida and "LNL03" in saida and
                 _lat_media(saida["LNL02"], g) > _lat_media(saida["LNL03"], g))
        checar(u"  ISCA: sem a canonizacao, a serie em dir nao sai com o 2 a "
               u"esquerda", not certo, str(sorted(saida)))
    finally:
        radai_geom.para_canonico, radai_geom.grade_canonica = velho


def teste_hnl_e_o_publicado():
    secao(u"o HNL_ e o metodo publicado; o FULL e o acabado (C7-HNL)")
    import radai_hnlnl as HN
    c, forma = _pescoco_sintetico()
    g = _grade()
    saida, linhas, ch = _cadeia_com_filho_falso("anel", c, forma, g,
                                                fixar=True)
    pub = getattr(saida, "publicado", None) or {}
    fim = saida.get("Lvl_III_L")
    p = pub.get("Lvl_III_L")
    checar(u"as duas camadas saem: o final no dicionario, o publicado ao lado",
           fim is not None and p is not None, str(sorted(saida)))
    if fim is None or p is None:
        return
    buraco = fim & ~p
    checar(u"o FULL tem a cavidade preenchida, e o HNL_ nao", buraco.any()
           and not (p & buraco).any(), u"%d voxels" % int(buraco.sum()))
    import radai_output as RO
    ped = _pedido_de("niveis_cervicais", saida)
    gravada = (ped.get("_masks") or {}).get("Lvl_III_L")
    checar(u"a Saida grava no HNL_ a camada publicada",
           gravada is not None and np.array_equal(gravada, p))
    isca = _pedido_de("niveis_cervicais", dict(saida))
    gravada = (isca.get("_masks") or {}).get("Lvl_III_L")
    checar(u"  ISCA: gravar o final no HNL_ seria outro conjunto",
           gravada is not None and not np.array_equal(gravada, p))
    checar(u"o filho e chamado UMA vez, no ensemble 2D+3D dos autores",
           _so_o_ensemble(ch), str(ch))


def teste_a_cadeia_na_ordem():
    secao(u"a cadeia e uma so, na ordem P0-P13 (C7-ORDEM)")
    import ast as _ast
    ordem = ("para_canonico", "caixa", "inferir_em_processo_separado",
             "voltar_a_grade", "conferir_niveis", "pos_dos_pesos",
             "pos_processar", "conferir_lado", "lados_suspeitos",
             "limpar_ilhas",
             "preencher_cavidade_vascular", "suavizar_niveis", "do_canonico",
             "masks_dos_niveis", "conferir_saida", "medir_extensao")

    def _linhas(fonte):
        arv = _ast.parse(fonte)
        f = [n for n in _ast.walk(arv) if isinstance(n, _ast.FunctionDef)
             and n.name == "rodar_na_serie"]
        primeira = {}
        for n in _ast.walk(f[0]):
            if isinstance(n, _ast.Call):
                nm = getattr(n.func, "id", None) or getattr(n.func, "attr", "")
                primeira[nm] = min(primeira.get(nm, 10 ** 9), n.lineno)
        return [primeira.get(k, 0) for k in ordem]
    fonte = io.open(_componentes.fonte("app/radai_hnlnl.py"),
                    encoding="utf-8").read()
    ln = _linhas(fonte)
    checar(u"as chamadas aparecem na ordem da especificacao",
           all(ln) and ln == sorted(ln), str(dict(zip(ordem, ln))))
    isca = fonte.replace(u"    rot = pos_processar(rot, gc, log)\n", u"")
    isca = isca.replace(u"    vol = normalizar_ct(vol, plano_m)\n",
                        u"    vol = normalizar_ct(vol, plano_m)\n"
                        u"    vol = pos_processar(vol)\n")
    li = _linhas(isca)
    checar(u"  ISCA: pos_processar antes da volta (a v8.3) reprova",
           not (all(li) and li == sorted(li)))


def teste_recorte_ap():
    secao(u"o recorte antero-posterior pelo corpo (C11-AP)")
    import radai_hnlnl as HN
    g = _grade((3.0, 1.0, 1.0))
    vol = np.full((8, 120, 60), -1000.0, dtype="float32")
    vol[:, 40:80, 10:50] = 40.0
    vol[:, 100:104, 5:55] = 300.0
    corpo = HN.primeiro_plano(vol)
    y0, y1 = HN.fechar_ap(corpo, g)
    checar(u"a caixa y cobre o corpo + 10 mm, e nao a imagem inteira",
           y0 == 30 and y1 == 90, u"%d..%d" % (y0, y1))
    checar(u"  e o volume que vai ao filho encolhe",
           (y1 - y0) < vol.shape[1])
    yi0, yi1 = HN.fechar_ap(vol > -400.0, g)
    checar(u"  ISCA: o corpo pelo limiar cru leva a mesa, e a caixa reprova",
           not (yi0 == 30 and yi1 == 90), u"%d..%d" % (yi0, yi1))
    c, forma = _pescoco_sintetico()
    saida, linhas, ch = _cadeia_com_filho_falso("ok", c, forma, _grade())
    checar(u"o log da cadeia diz o recorte com o ap pelo corpo",
           any(u"ap pelo corpo" in l for l in linhas), u" | ".join(linhas)[:200])


def _so_o_ensemble(chamadas):
    return [str(x.get("fold")) for x in chamadas] == ["ensemble"]


def teste_ensemble_e_o_padrao():
    secao(u"o ensemble 2D+3D dos autores e o padrao dos niveis (C11)")
    import radai_hnlnl as HN
    import radai_hnlnl_engine as HM
    checar(u"o padrao de fabrica e o ensemble 2D+3D",
           HN.MODELO_DOS_NIVEIS == "ensemble")
    c, forma = _pescoco_sintetico()
    _s, linhas, ch = _cadeia_com_filho_falso("ok", c, forma, _grade())
    checar(u"  e a cadeia pede ao filho o ensemble, uma vez",
           _so_o_ensemble(ch), str(ch))
    checar(u"  e o log diz a rede: %s" % HM.REDE_DO_ENSEMBLE,
           any(HM.REDE_DO_ENSEMBLE in l for l in linhas),
           u" | ".join(linhas)[:200])
    velho_modelo = HN.MODELO_DOS_NIVEIS
    try:
        HN.MODELO_DOS_NIVEIS = "3d_fold0"
        _s, linhas2, ch2 = _cadeia_com_filho_falso("ok", c, forma, _grade())
    finally:
        HN.MODELO_DOS_NIVEIS = velho_modelo
    checar(u"  ISCA: com o fold 0 de referencia, a cadeia reprova",
           not _so_o_ensemble(ch2)
           and [str(x.get("fold")) for x in ch2] == ["0"], str(ch2))
    checar(u"  ISCA: e o log nao diz o ensemble",
           not any(HM.REDE_DO_ENSEMBLE in l for l in linhas2))
    checar(u"o ramo do ensemble existe no motor, com cinco folds por rede",
           callable(getattr(HM, "inferir_ensemble", None))
           and len(HM.FOLDS) == 5)
    checar(u"a frase da rede diz os 10 pesos",
           HM.REDE_DO_ENSEMBLE == u"ensemble 2D+3D (10 pesos)"
           and HN.rede_dos_niveis() == HM.REDE_DO_ENSEMBLE)
    try:
        import torch
    except Exception:
        print(u"  PULADO  a rede 2D (sem torch neste runtime): rode esta "
              u"bateria com o Python do bundle")
        torch = None
    if torch is not None:
        import collections
        sd = collections.OrderedDict()
        k = (3, 3)
        cs = [(1, 4), (4, 4), (4, 8), (8, 8)]
        sd["conv_blocks_context.0.blocks.0.conv.weight"] = torch.zeros(4, 1, *k)
        for nome, (ci, co) in (("conv_blocks_context.0.blocks.1", cs[1]),
                               ("conv_blocks_context.1.blocks.0", cs[2]),
                               ("conv_blocks_context.1.blocks.1", cs[3])):
            sd[nome + ".conv.weight"] = torch.zeros(co, ci, *k)
        sd["conv_blocks_context.0.blocks.0.conv.bias"] = torch.zeros(4)
        for nome, co in (("conv_blocks_context.0.blocks.1", 4),
                         ("conv_blocks_context.1.blocks.0", 8),
                         ("conv_blocks_context.1.blocks.1", 8)):
            sd[nome + ".conv.bias"] = torch.zeros(co)
        for nome, co in (("conv_blocks_context.0.blocks.0", 4),
                         ("conv_blocks_context.0.blocks.1", 4),
                         ("conv_blocks_context.1.blocks.0", 8),
                         ("conv_blocks_context.1.blocks.1", 8)):
            sd[nome + ".instnorm.weight"] = torch.ones(co)
            sd[nome + ".instnorm.bias"] = torch.zeros(co)
        sd["tu.0.weight"] = torch.zeros(8, 4, 2, 2)
        for nome, (ci, co) in (("conv_blocks_localization.0.0.blocks.0",
                                (8, 4)),
                               ("conv_blocks_localization.0.1.blocks.0",
                                (4, 4))):
            sd[nome + ".conv.weight"] = torch.zeros(co, ci, *k)
            sd[nome + ".conv.bias"] = torch.zeros(co)
            sd[nome + ".instnorm.weight"] = torch.ones(co)
            sd[nome + ".instnorm.bias"] = torch.zeros(co)
        sd["seg_outputs.0.weight"] = torch.zeros(21, 4, 1, 1)
        rede = HM._classes(torch, 2)(sd, [[2, 2]])
        rede.load_state_dict(sd, strict=True)
        y = rede(torch.zeros(1, 1, 16, 16))
        checar(u"a rede 2D monta com strict=True e devolve 21 canais",
               tuple(y.shape) == (1, 21, 16, 16), str(tuple(y.shape)))
        b3 = HM.pasta_dos_pesos()
        b2 = HM.pastas_do_ensemble(b3)[1] if b3 else ""
        if b2 and os.path.isfile(os.path.join(b2, "plans.pkl")):
            for f in HM.FOLDS:
                try:
                    rede2, p2 = HM.carregar(b2, fold=f)
                    ok2d = p2.get("canais") == 21
                    det = u"%d canais" % p2.get("canais", -1)
                except Exception as e:
                    ok2d, det = False, u"%s: %s" % (type(e).__name__,
                                                   str(e)[:120])
                checar(u"os pesos 2D reais do fold %d carregam com strict=True"
                       % f, ok2d, det)
        else:
            print(u"  PULADO  os pesos 2D reais (nao instalados neste "
                  u"runtime)")
    if OFICINA is None:
        _componentes.pulado(u"a ferramenta de medida do ensemble (da oficina)")
    else:
        OFICINA.ferramenta_de_medida(sys.modules[__name__])


def _arvore_do_ensemble(raiz, faltando=()):
    import radai_hnlnl_engine as HM
    for rel in HM.arquivos_do_ensemble():
        if rel in faltando:
            continue
        p = os.path.join(raiz, *rel.split("/"))
        if not os.path.isdir(os.path.dirname(p)):
            os.makedirs(os.path.dirname(p))
        if rel.endswith("plans.pkl"):
            _plans_sintetico(os.path.dirname(p))
        else:
            with io.open(p, "wb") as f:
                f.write(b"x")
    return os.path.join(raiz, "3d_fullres", HM.TAREFA, HM.TREINADOR)


def teste_sem_os_pesos_do_ensemble_nao_roda():
    secao(u"sem os pesos do ensemble, os niveis nao rodam (tudo ou nada)")
    import radai_hnlnl as HN
    import radai_hnlnl_engine as HM
    arqs = HM.arquivos_do_ensemble()
    pesos = [a for a in arqs if a.endswith("/model_final_checkpoint.model")]
    checar(u"o ensemble pede os 10 pesos (5 do 3D e 5 do 2D), os dois planos "
           u"e o pos-processamento do ensemble",
           len(pesos) == 10
           and len([a for a in pesos if a.startswith("3d_fullres/")]) == 5
           and len([a for a in pesos if a.startswith("2d/")]) == 5
           and len([a for a in arqs if a.endswith("/plans.pkl")]) == 2
           and ("ensembles/%s/%s/postprocessing.json"
                % (HM.TAREFA, HM.PASTA_DO_ENSEMBLE)) in arqs, str(arqs))
    raiz = _cleanup.temporaria("radai_chk_hnl_")
    b3 = _arvore_do_ensemble(raiz)
    checar(u"com a arvore inteira, nada falta",
           HM.faltam_do_ensemble(b3) == [], str(HM.faltam_do_ensemble(b3)))
    velho = HM.pasta_dos_pesos
    try:
        HM.pasta_dos_pesos = lambda *a, **k: b3
        ok, b = HN.disponivel()
        checar(u"  e os niveis estao disponiveis", ok and b == b3, str(b))
        um = [a for a in pesos if a.startswith("2d/") and "/fold_3/" in a][0]
        os.remove(os.path.join(raiz, *um.split("/")))
        ok2, motivo = HN.disponivel()
        checar(u"sem um peso do 2D, os niveis nao rodam, e o motivo manda "
               u"refazer o preparo",
               not ok2 and u"CONFIGURAR_AMBIENTE" in motivo
               and u"fold_3" in motivo, motivo)
        velho_m = HN.MODELO_DOS_NIVEIS
        try:
            HN.MODELO_DOS_NIVEIS = "3d_fold0"
            ok3, m3 = HN.disponivel()
        finally:
            HN.MODELO_DOS_NIVEIS = velho_m
        checar(u"  ISCA: a pergunta do fold 0 sozinho deixava passar", ok3,
               m3)
    finally:
        HM.pasta_dos_pesos = velho


def _portas_que_pedem_o_fold(fontes):
    import ast as _ast
    fora = []
    for nome, src in fontes:
        for n in _ast.walk(_ast.parse(src)):
            if isinstance(n, _ast.Assign):
                for t in n.targets:
                    alvo = getattr(t, "attr", None) or getattr(t, "id", None)
                    if alvo == "MODELO_DOS_NIVEIS" and not (
                            isinstance(n.value, _ast.Constant)
                            and n.value.value == "ensemble"):
                        fora.append(u"%s:%d MODELO_DOS_NIVEIS" % (nome,
                                                                  n.lineno))
            if not isinstance(n, _ast.Call):
                continue
            f = getattr(n.func, "attr", None) or getattr(n.func, "id", None)
            if f not in ("rodar_na_serie", "inferir_em_processo_separado"):
                continue
            for k in n.keywords:
                if (k.arg == "fold" and isinstance(k.value, _ast.Constant)
                        and k.value.value != "ensemble"):
                    fora.append(u"%s:%d %s(fold=%r)" % (nome, n.lineno, f,
                                                        k.value.value))
            if f == "inferir_em_processo_separado" and len(n.args) > 2:
                fora.append(u"%s:%d %s com o fold posicional" % (nome,
                                                                  n.lineno, f))
    return fora


def teste_a_porta_nao_pede_o_fold_0():
    secao(u"nenhuma porta pede o fold 0 sozinho (o vigia, o Rodar agora, o "
          u"protocolo)")
    import inspect
    import radai_hnlnl as HN
    fontes = []
    pasta = os.path.join(RAIZ, "app")
    for n in sorted(os.listdir(pasta)):
        if n.endswith(".py") and n != "radai_hnlnl_engine.py":
            fontes.append((n, io.open(os.path.join(pasta, n),
                                      encoding="utf-8").read()))
    fora = _portas_que_pedem_o_fold(fontes)
    checar(u"app/ nao pede o fold 0 nem troca a rede dos niveis", not fora,
           u" | ".join(fora))
    checar(u"  e `rodar_na_serie` nao tem parametro de fold",
           "fold" not in inspect.signature(HN.rodar_na_serie).parameters)
    for isca in (u"HN.rodar_na_serie(vol, base, forma, grade, fold=0)\n",
                 u"HM.inferir_em_processo_separado(base, vol, fold=0)\n",
                 u"HM.inferir_em_processo_separado(base, vol, 0)\n",
                 u"HN.MODELO_DOS_NIVEIS = '3d_fold0'\n"):
        checar(u"  ISCA: %s reprova" % isca.strip(),
               bool(_portas_que_pedem_o_fold([(u"isca.py", isca)])))


def _ensemble_de_antes(base3d, vol, carregar, inferir):
    import radai_hnlnl_engine as HM
    b3, b2 = HM.pastas_do_ensemble(base3d)
    soma = None
    for base in (b3, b2):
        media = None
        for f in HM.FOLDS:
            rede, p = carregar(base, fold=f)
            pr = inferir(rede, vol, p, probabilidades=True)
            if media is None:
                media = pr
            else:
                media += pr
            del pr
        media /= float(len(HM.FOLDS))
        if soma is None:
            soma = media
        else:
            soma += media
        del media
    return np.argmax(soma, axis=0).astype("int8")


def teste_o_ensemble_soma_as_dez_redes():
    secao(u"o ensemble: as dez redes num acumulador so (memoria)")
    import weakref
    import radai_hnlnl_engine as HM
    raiz = _cleanup.temporaria("radai_chk_hnl_")
    b3 = os.path.join(raiz, "3d_fullres", HM.TAREFA, HM.TREINADOR)
    vol = np.zeros((2, 3, 4), dtype="float32")
    rng = np.random.RandomState(7)
    saidas = [rng.rand(4, 2, 3, 4).astype("float32") for _ in range(10)]
    estado = {"chamadas": [], "vivos": [], "pico": 0, "i": 0}

    def _carregar(base, fold=0, device="cpu"):
        estado["chamadas"].append((base, fold))
        return object(), {}

    def _inferir(rede, v, p, device="cpu", log=None, probabilidades=False):
        vivos = sum(1 for r in estado["vivos"] if r() is not None)
        estado["pico"] = max(estado["pico"], vivos)
        a = saidas[estado["i"]].copy()
        estado["i"] += 1
        estado["vivos"].append(weakref.ref(a))
        return a

    velhos = (HM.carregar, HM.inferir, HM.plano)
    try:
        HM.carregar, HM.inferir = _carregar, _inferir
        HM.plano = lambda b: {"spacing": (3.0, 1.0, 1.0)}
        rot = HM.inferir_ensemble(b3, vol)
        pico_novo = estado["pico"]
        chamadas = list(estado["chamadas"])
        estado.update(chamadas=[], vivos=[], pico=0, i=0)
        rot_antes = _ensemble_de_antes(b3, vol, _carregar, _inferir)
        pico_antes = estado["pico"]
    finally:
        HM.carregar, HM.inferir, HM.plano = velhos
    b2 = HM.pastas_do_ensemble(b3)[1]
    checar(u"roda os cinco folds do 3D e os cinco do 2D",
           chamadas == [(b3, f) for f in HM.FOLDS] + [(b2, f)
                                                      for f in HM.FOLDS],
           str(chamadas))
    esperado = np.argmax(np.mean(saidas[:5], axis=0)
                         + np.mean(saidas[5:], axis=0), axis=0)
    checar(u"  e o rotulo e o argmax da media do 3D mais a media do 2D (o "
           u"nnUNet_ensemble)", np.array_equal(rot, esperado)
           and np.array_equal(rot_antes, esperado))
    checar(u"  com UM acumulador vivo enquanto a rede seguinte roda",
           pico_novo == 1, u"pico %d" % pico_novo)
    checar(u"  ISCA: a media por rede de antes segurava dois",
           pico_antes == 2, u"pico %d" % pico_antes)


def teste_o_teto_cobre_o_ensemble():
    secao(u"o teto do filho cobre o ensemble (C11)")
    import radai_hnlnl_engine as HM
    janela_lenta_s = 106.0
    janelas_3d_do_recorte_mediano = 27
    razao_medida = 1036.0 / 183.0
    preciso = janela_lenta_s * janelas_3d_do_recorte_mediano * razao_medida
    checar(u"o teto passa do ensemble na maquina lenta medida (%.1f h)"
           % (preciso / 3600.0), HM.TEMPO_LIMITE_S >= preciso,
           u"teto %.1f h" % (HM.TEMPO_LIMITE_S / 3600.0))
    checar(u"  ISCA: o teto do fold 0 (3 h) nao cobria", 3 * 3600 < preciso)
    checar(u"  e o filho espera o teto do motor quando ninguem passa outro",
           u"timeout_s or TEMPO_LIMITE_S" in io.open(
               _componentes.fonte("app/radai_hnlnl_engine.py"),
               encoding="utf-8").read())


def teste_o_registro_diz_o_ensemble():
    secao(u"o done, o caso e o log dizem a rede dos niveis")
    import radai_records as RG
    import radai_hnlnl_engine as HM
    cd = RG.campos_do_done(modalidade="CT", motores_fora_do_ts=["hnlnl"])
    checar(u"o done diz %s quando os niveis desenharam" % HM.REDE_DO_ENSEMBLE,
           cd.get("rede_dos_niveis") == HM.REDE_DO_ENSEMBLE, str(cd))
    checar(u"  ISCA: sem os niveis, o done nao diz rede nenhuma",
           "rede_dos_niveis" not in RG.campos_do_done(
               modalidade="CT", motores_fora_do_ts=["cranio_ct"]))
    base = _cleanup.temporaria("radai_chk_hnl_")
    c = RG.Caso(uid="1.2.3", identificadores=(), base=base)
    c.processamento(niveis_cervicais={"rodam": True, "motivo": u"C2 a C4"})
    nc = c.d["processamento"]["niveis_cervicais"]
    checar(u"o caso diz a rede quando os niveis rodam",
           nc.get("rede") == HM.REDE_DO_ENSEMBLE and nc.get("rodam") is True,
           str(nc))
    c.processamento(niveis_cervicais={"rodam": False, "motivo": u"torax"})
    nc = c.d["processamento"]["niveis_cervicais"]
    checar(u"  e nao diz quando nao rodam", "rede" not in nc, str(nc))
    import radai_output as RO
    linhas = []
    velho = RO.cruas_da_base
    try:
        import radai_hnlnl as HN
        velho_d, velho_r = HN.disponivel, HN.rodar_na_serie
        HN.disponivel = lambda: (True, base)
        HN.rodar_na_serie = lambda *a, **k: {"LNL_Union": np.ones((1, 1, 1),
                                                                   bool)}
        RO.cruas_da_base = lambda c: {"x": 1}
        import SimpleITK as sitk
        ref = sitk.Image(4, 4, 2, sitk.sitkInt16)
        RO.niveis_cervicais_da_serie(ref, {}, log=linhas.append)
    finally:
        RO.cruas_da_base = velho
        HN.disponivel, HN.rodar_na_serie = velho_d, velho_r
    checar(u"a linha final do log dos niveis diz a rede",
           any(u"contorno(s)" in l and HM.REDE_DO_ENSEMBLE in l
               for l in linhas), u" | ".join(linhas))


def _marca_em_vez_de_recusar(fonte):
    import ast
    arv = ast.parse(fonte)
    f = [n for n in ast.walk(arv)
         if isinstance(n, ast.FunctionDef) and n.name == "rodar_na_serie"]
    if not f:
        return False
    corpo = f[0]
    mede = any(isinstance(n, ast.Call) and getattr(n.func, "id", "") in
               ("medir_extensao",) for n in ast.walk(corpo))
    embrulha = any(isinstance(n, ast.Call)
                   and getattr(n.func, "id", "") == "NiveisDaSerie"
                   for n in ast.walk(corpo))
    recusa = False
    for n in ast.walk(corpo):
        if isinstance(n, ast.If):
            teste = ast.dump(n.test)
            if "ext" in teste and any(
                    isinstance(r, ast.Return) and isinstance(r.value, ast.Dict)
                    and not r.value.keys for r in ast.walk(n)):
                recusa = True
    return mede and embrulha and not recusa


def teste_travas():
    secao(u"as DUAS travas da regra 6, e elas olham coisas diferentes")
    import radai_hnlnl as HN
    import radai_hnlnl_engine as HM

    checar(u"os indices 0..20 passam", HM.conferir_niveis(list(range(21))))
    try:
        HM.conferir_niveis([0, 1, 21])
        checar(u"a classe 21 e recusada", False, "aceitou classe nova")
    except ValueError as e:
        checar(u"a classe 21 e recusada", True)
        checar(u"  e o erro cita a RDC 751/2022", "751/2022" in str(e))

    checar(u"os nomes neutros passam",
           HN.conferir_saida(["LNL01", "LNL20", HN.NOME_DA_UNIAO]))
    for ruim in ("Nodulo_suspeito", "LNL21", "metastatic_level"):
        try:
            HN.conferir_saida(["LNL01", ruim])
            checar(u"`%s` e recusado" % ruim, False, "aceitou")
        except ValueError:
            checar(u"`%s` e recusado" % ruim, True)

    txt = io.open(_componentes.fonte("app/radai_hnlnl_engine.py"),
                  encoding="utf-8").read()
    checar(u"a trava do motor e por INDICE", "INDICES_PERMITIDOS" in txt)
    checar(u"ha teto de classes", "TETO_DE_CLASSES" in txt)
    import tokenize
    codigo = []
    try:
        for tok in tokenize.generate_tokens(io.StringIO(txt).readline):
            if tok.type not in (tokenize.COMMENT, tokenize.STRING):
                codigo.append(tok.string)
    except Exception:
        codigo = [txt]
    codigo = " ".join(codigo).lower()
    checar(u"nao existe caminho de espelhamento no CODIGO do motor",
           "flip" not in codigo and "mirror" not in codigo,
           "espelhar religaria exatamente o que o treino evitou")


def teste_normalizacao():
    secao(u"a normalizacao usa os numeros DO TREINO")
    import radai_hnlnl as HN
    p = {"clip": (-148.0, 302.0), "media": 14.79, "desvio": 97.7386}
    v = np.array([[[-2000.0, -148.0, 14.79, 302.0, 5000.0]]], dtype="float32")
    n = HN.normalizar_ct(v, p)
    checar(u"recorta em baixo", abs(float(n[0, 0, 0]) - float(n[0, 0, 1])) < 1e-6)
    checar(u"recorta em cima", abs(float(n[0, 0, 3]) - float(n[0, 0, 4])) < 1e-6)
    checar(u"a media do treino vira zero", abs(float(n[0, 0, 2])) < 1e-3,
           "%.4f" % float(n[0, 0, 2]))


def teste_primeiro_plano():
    secao(u"o primeiro plano tira a mesa, e nao o paciente")
    import radai_hnlnl as HN
    vol = np.full((8, 40, 40), -1000.0, dtype="float32")
    vol[:, 10:30, 10:30] = 40.0
    vol[:, 34:36, 5:35] = 200.0
    vol[:, 18:22, 18:22] = -900.0
    corpo = HN.primeiro_plano(vol)
    checar(u"o paciente fica", bool(corpo[:, 20, 20].all()))
    checar(u"o ar interno volta para dentro do corpo",
           bool(corpo[4, 19, 19]), "buraco interno nao e fora do paciente")
    checar(u"a mesa sai", not bool(corpo[4, 35, 20]),
           "%d voxels de mesa sobraram" % int(corpo[:, 34:36, 5:35].sum()))
    checar(u"volume so de ar nao quebra",
           HN.primeiro_plano(np.full((4, 8, 8), -1000.0, dtype="float32")).all())


def teste_rede_reconstruida():
    secao(u"a rede montada a partir dos PESOS (so onde ha torch)")
    try:
        import torch
    except Exception:
        checar(u"torch nao esta neste runtime — a rede e provada no bundle",
               True, "rodar_com_bundle.cmd cobre esta parte")
        return
    import radai_hnlnl_engine as HM
    base = HM.pasta_dos_pesos()
    if not base:
        checar(u"pesos nao instalados — nada a provar aqui", True,
               "o pacote do pipeline unico os traz (modelos\\hnlnl)")
        return
    p = HM.plano(base)
    checar(u"o plano traz o patch", len(p["patch"]) == 3, str(p["patch"]))
    checar(u"e o espacamento de trabalho", len(p["spacing"]) == 3,
           str(tuple(round(x, 2) for x in p["spacing"])))
    rede, p = HM.carregar(base, fold=0)
    checar(u"a rede carregou com strict=True", rede is not None)
    checar(u"os canais vem dos PESOS, e nao do plano", p.get("canais") == 21,
           str(p.get("canais")))
    import torch as _t
    with _t.no_grad():
        y = rede(_t.zeros(1, 1, *p["patch"]))
    checar(u"o forward devolve 21 canais no tamanho do patch",
           tuple(y.shape) == (1, 21) + tuple(p["patch"]), str(tuple(y.shape)))


def teste_registro():
    secao(u"o conjunto esta no registro, e nao vai para o TPS")
    import radai_sets as C
    import radai_hnlnl as HN
    c = C.POR_COD.get("hnl")
    checar(u"o conjunto `hnl` existe", bool(c))
    if not c:
        return
    checar(u"o infixo do arquivo bate com o modulo", c["infixo"] == HN.INFIXO,
           "%s vs %s" % (c["infixo"], HN.INFIXO))
    checar(u"o sufixo das estruturas bate", c["sufixo"] == HN.SUFIXO)
    checar(u"ele NAO e o entregue ao TPS", not c["entregue"])
    checar(u"e sai CRU, sem a nossa suavizacao", not c["suavizado"],
           "compartimento e definido por planos; arredondar a quina muda o "
           "que entra no volume eletivo")
    checar(u"o arquivo dele e reconhecido pelo registro",
           C.do_arquivo("RS_RadAI_HNL_20260824_11.dcm")["cod"] == "hnl")
    checar(u"e `e_entregue` diz que nao",
           not C.e_entregue("RS_RadAI_HNL_20260824_11.dcm"))


def _casas_da_chave(fonte, chave):
    import ast
    fora = {"texto": False, "defaults": False, "aplicar": False,
            "obsoleta": u""}
    for no in ast.parse(fonte).body:
        if isinstance(no, ast.Assign):
            for alvo in no.targets:
                if not isinstance(alvo, ast.Name):
                    continue
                v = no.value
                if alvo.id == "DEFAULT_CFG" and isinstance(v, ast.Constant):
                    for linha in str(v.value).splitlines():
                        linha = linha.strip()
                        if (linha and not linha.startswith("#") and "=" in linha
                                and linha.split("=", 1)[0].strip() == chave):
                            fora["texto"] = True
                if alvo.id == "DEFAULTS" and isinstance(v, ast.Dict):
                    fora["defaults"] = any(
                        isinstance(k, ast.Constant) and k.value == chave
                        for k in v.keys)
                if alvo.id == "CHAVES_OBSOLETAS" and isinstance(v, ast.Dict):
                    for k, x in zip(v.keys, v.values):
                        if (isinstance(k, ast.Constant) and k.value == chave
                                and isinstance(x, ast.Constant)):
                            fora["obsoleta"] = str(x.value)
        if isinstance(no, ast.FunctionDef) and no.name == "aplicar_cfg":
            fora["aplicar"] = any(isinstance(n, ast.Constant)
                                  and n.value == chave for n in ast.walk(no))
    return fora


def _hnlnl_fora_da_anatomia(fonte):
    import ast
    try:
        arv = ast.parse(fonte)
    except SyntaxError as e:
        return [u"o fonte nao parseia (%s)" % e]
    pai = {}
    for n in ast.walk(arv):
        for f in ast.iter_child_nodes(n):
            pai[f] = n
    ruins = []

    def _chama(no, nome):
        return any(isinstance(c, ast.Call)
                   and getattr(c.func, "id", getattr(c.func, "attr", "")) == nome
                   for c in ast.walk(no))

    chamadas = [n for n in ast.walk(arv) if isinstance(n, ast.Call)
                and getattr(n.func, "id", "") == "_rodar_hnlnl"]
    if not chamadas:
        ruins.append(u"ninguem chama `_rodar_hnlnl`")
    for ch in chamadas:
        n, guardada = ch, False
        while n in pai:
            filho, n = n, pai[n]
            if (isinstance(n, ast.If) and filho is not n.test
                    and any(filho is b for b in n.body)):
                t = n.test
                so_o_portao = (isinstance(t, ast.Call)
                               and getattr(t.func, "id", "")
                               == "_niveis_cervicais_nesta_serie")
                if so_o_portao:
                    guardada = True
                    break
        if not guardada:
            ruins.append(u"`_rodar_hnlnl` (linha %d) fora do `if "
                         u"_niveis_cervicais_nesta_serie(...)`" % ch.lineno)
    portao = [n for n in arv.body if isinstance(n, ast.FunctionDef)
              and n.name == "_niveis_cervicais_nesta_serie"]
    if not portao:
        ruins.append(u"o portao `_niveis_cervicais_nesta_serie` sumiu")
    for f in portao:
        if not _chama(f, "pescoco_no_campo"):
            ruins.append(u"o portao nao pergunta a anatomia (`pescoco_no_campo`)")
        corpo = list(f.body)
        if (corpo and isinstance(corpo[0], ast.Expr)
                and isinstance(corpo[0].value, ast.Constant)):
            corpo = corpo[1:]
        for st in corpo:
            for n in ast.walk(st):
                if ((isinstance(n, ast.Name) and n.id in ("CFG", "INCLUIR_HNLNL"))
                        or (isinstance(n, ast.Constant)
                            and n.value == "INCLUIR_HNLNL")):
                    ruins.append(u"o portao le o config (linha %d)" % n.lineno)
    for n in ast.walk(arv):
        if isinstance(n, (ast.If, ast.IfExp, ast.While)) and any(
                isinstance(x, ast.Name) and x.id == "INCLUIR_HNLNL"
                for x in ast.walk(n.test)):
            ruins.append(u"ramo testando INCLUIR_HNLNL (linha %d)" % n.lineno)
    return ruins


def teste_costura_no_vigia():
    secao(u"o vigia chama pela anatomia, e a chave saiu dos tres lugares")
    vig = io.open(_componentes.fonte("app/radai_watcher.py"),
                  encoding="utf-8").read()
    casas = _casas_da_chave(vig, "INCLUIR_HNLNL")
    checar(u"`INCLUIR_HNLNL` saiu do texto do config, do DEFAULTS e de "
           u"`aplicar_cfg`",
           not (casas["texto"] or casas["defaults"] or casas["aplicar"]),
           str(casas))
    checar(u"  e esta em CHAVES_OBSOLETAS, com o motivo (o pescoco)",
           u"pescoco" in casas["obsoleta"], casas["obsoleta"] or u"ausente")
    _isca_casas = vig.replace(u'"SUAVIZAR_MM": "1.0"}',
                              u'"SUAVIZAR_MM": "1.0", "INCLUIR_HNLNL": "0"}', 1)
    checar(u"  ISCA (a chave de volta ao DEFAULTS) e acusada",
           _isca_casas != vig
           and _casas_da_chave(_isca_casas, "INCLUIR_HNLNL")["defaults"])
    ruins = _hnlnl_fora_da_anatomia(vig)
    checar(u"o laco so chama `_rodar_hnlnl` atras do portao da anatomia "
           u"(`_niveis_cervicais_nesta_serie` -> `pescoco_no_campo`)",
           not ruins, u"; ".join(ruins))
    _se = u"if _niveis_cervicais_nesta_serie(masks, cruas, ref, info):"
    checar(u"  (o `if` do portao esta no vigia, para as iscas o trocarem)",
           _se in vig)
    for de, para, rot in (
            (_se, u"if True:", u"o `if` do portao trocado por `True`"),
            (_se, u"if _niveis_cervicais_nesta_serie(masks, cruas, ref, info)"
                  u" or INCLUIR_HNLNL:",
             u"um `or` com a chave velha"),
            (u"    try:\n        if str(info.get(\"modalidade\")",
             u"    try:\n        if CFG.get(\"INCLUIR_HNLNL\"):\n"
             u"            return True\n        if str(info.get(\"modalidade\")",
             u"o portao lendo o config")):
        isca = vig.replace(de, para, 1)
        checar(u"  ISCA (%s) e acusada" % rot,
               isca != vig and bool(_hnlnl_fora_da_anatomia(isca)),
               u"a troca nao achou o trecho" if isca == vig else u"")
    import engine as _E
    g = _grade(esp=(1.0, 1.0, 1.0))
    forma = (160, 100, 100)
    faixas = {"C4": (10, 20), "C3": (20, 30), "C2": (30, 40), "C1": (40, 45)}

    def _bloco(z0, z1, cm3):
        bloco = np.zeros(forma, bool)
        bloco[z0:z1].reshape(-1)[:int(round(cm3 * 1000.0))] = True
        return bloco

    def _vertebras(cranio=0.0, mandibula=0.0, **cm3):
        m = {}
        for nome, v in sorted(cm3.items()):
            m["vertebrae_" + nome] = _bloco(faixas[nome][0], faixas[nome][1],
                                            v)
        ossos = []
        if mandibula:
            ossos.append(_bloco(15, 45, mandibula))
        if cranio:
            ossos.append(_bloco(45, 160, cranio))
        if ossos:
            m["skull"] = np.logical_or.reduce(ossos)
        return m
    for rot, vols, espera in (
            (u"cabeca e pescoco (as cervicais do P07, o cranio e 90 cm3 de "
             u"mandibula na faixa)",
             dict(C1=4.0, C2=20.2, C3=14.5, C4=15.0, cranio=600.0,
                  mandibula=90.0), True),
            (u"as cervicais do P07 e o cranio, sem a mandibula (a cabeca no "
             u"campo confirma pelo cranio acima do C1)",
             dict(C1=4.0, C2=20.2, C3=14.5, C4=15.0, cranio=600.0), True),
            (u"o cranio com C1 e C2, sem C3 nem C4 (cranio sem pescoco)",
             dict(C1=4.0, C2=20.2, cranio=600.0), False),
            (u"P19 (C2 17,2, C3 11,0, C4 11,5, so 57,4 cm3 de mandibula: a "
             u"TC de torax que sobe ao C1)",
             dict(C2=17.2, C3=11.0, C4=11.5, mandibula=57.4), False),
            (u"P20 (C2 0,2, C3 9,2, C4 13,1)",
             dict(C2=0.2, C3=9.2, C4=13.1, mandibula=41.4), False),
            (u"sem cervical nenhuma", {}, False)):
        tem, laudo = _E.pescoco_no_campo(_vertebras(**vols), g)
        checar(u"  a anatomia decide: %s -> %s" % (rot, u"rodam" if espera
                                                     else u"nao rodam"),
               bool(tem) is espera, laudo)
    checar(u"o laco chama `_rodar_hnlnl`", "_rodar_hnlnl(" in vig)
    checar(u"e `_rodar_hnlnl` delega a `radai_output.niveis_cervicais_da_serie`",
           "radai_output.niveis_cervicais_da_serie(" in vig
           and "HN.rodar_na_serie(" not in vig,
           u"uma segunda cadeia no vigia divergiria da do lote")
    checar(u"e o cofre da vez existe", "_HNLNL_DA_VEZ" in vig)
    _codigo_vig = u"\n".join(l for l in vig.splitlines()
                             if not l.lstrip().startswith(u"#"))
    checar(u"o vigia manda os niveis ao FULL (`cervicais=` de `full_e_oar`, "
           u"com o cofre da vez)",
           u'cervicais=_HNLNL_DA_VEZ.get("masks")' in _codigo_vig)
    checar(u"  e NAO grava o `HNL_` ao lado (o `niveis_cervicais` da `Saida` "
           u"so no PERSONALIZADO do «Rodar agora»)",
           u"sd.niveis_cervicais(" not in _codigo_vig)
    _isca_hnl = _codigo_vig.replace(
        u"    _HNLNL_DA_VEZ[\"masks\"] = None\n",
        u"    sd.niveis_cervicais(_HNLNL_DA_VEZ.get(\"masks\"))\n"
        u"    _HNLNL_DA_VEZ[\"masks\"] = None\n", 1)
    checar(u"  ISCA: a gravacao do `HNL_` de volta no vigia e acusada",
           _isca_hnl != _codigo_vig and u"sd.niveis_cervicais(" in _isca_hnl)
    import numpy as _np
    import radai_hnlnl as _hn
    _ped = _pedido_de("niveis_cervicais", {"LNL07": _np.ones((2, 2, 2), bool)})
    checar(u"e ele e gravado CRU (suavizar_mm=0,0)",
           float(_ped.get("suavizar_mm", -1)) == 0.0,
           "pediu %r" % (_ped.get("suavizar_mm"),))
    checar(u"e sem derivar (nada nosso entra num nivel)",
           _ped.get("derivar") is False, "pediu %r" % (_ped.get("derivar"),))
    checar(u"com o rotulo proprio dos niveis, e nao `STUDY_`",
           str(_ped.get("rotulo") or "") == _hn.ROTULO_TPS,
           str(_ped.get("rotulo")))
    checar(u"os rotulos crus sao coletados tambem por causa dos niveis "
           u"(sempre, desde a v8.2)", _cruas_nao_dependem_so_do_ts(vig),
           "prender a coleta ao `_ts` faria os niveis pararem em silencio")
    _CHAMA = u"    engine.run_ts_task(r, t, cruas=cruas)\n"
    for isca, rot in (
            (u"def outra():\n    cruas = {}\n"
             u"def process_series():\n    cruas = None\n" + _CHAMA,
             u"`cruas = None` na funcao que chama, `{}` noutra funcao"),
            (u"def process_series():\n"
             u"    cruas = None if INCLUIR_HNLNL else {}\n" + _CHAMA,
             u"o IfExp invertido: `{}` so com os niveis DESLIGADOS"),
            (u"def process_series():\n    cruas = {}\n    cruas = None\n"
             + _CHAMA,
             u"`{}` seguido de `None` antes da chamada"),
            (u"def process_series():\n    cruas = {}\n"
             u"    for t in tasks:\n" + u"    " + _CHAMA
             + u"        cruas = None\n",
             u"`None` depois da chamada, dentro do laco (vale na volta "
             u"seguinte)"),
            (u"def process_series():\n"
             u"    cruas = {} if not INCLUIR_HNLNL else None\n" + _CHAMA,
             u"a condicao NEGA os niveis"),
            (u"def process_series():\n"
             u"    cruas = {} if (ENTREGAR_TS and INCLUIR_HNLNL) else None\n"
             + _CHAMA,
             u"a condicao exige o `_ts` JUNTO com os niveis"),
            (u"def process_series():\n    cruas = {}\n"
             u"    for cruas in ([None],):\n        pass\n" + _CHAMA,
             u"religada por um `for`"),
            (u"def process_series():\n"
             u"    engine.run_ts_task(r, t, cruas={})\n",
             u"um `{}` literal na chamada, que ninguem le depois"),
            (u"cruas = {} if ENTREGAR_TS else None\n"
             u"engine.run_ts_task(r, t, cruas=cruas)\n",
             u"a coleta presa ao `_ts`"),
            (u"engine.run_ts_task(r, t, cruas=None)\n",
             u"sem coleta nenhuma")):
        import ast as _a
        try:
            _a.parse(isca)
            _parseia = True
        except SyntaxError:
            _parseia = False
        checar(u"  ISCA (%s) e acusada" % rot,
               _parseia and not _cruas_nao_dependem_so_do_ts(isca),
               u"" if _parseia else u"a isca nao parseia")
    checar(u"  e a forma de antes (`ENTREGAR_TS or INCLUIR_HNLNL`) continua "
           u"aceita", _cruas_nao_dependem_so_do_ts(
               u"cruas = {} if (ENTREGAR_TS or INCLUIR_HNLNL) else None\n"
               u"engine.run_ts_task(r, t, cruas=cruas)\n"))
    checar(u"  e a de hoje (`{}` incondicional, na funcao que chama) tambem",
           _cruas_nao_dependem_so_do_ts(
               u"def outra():\n    cruas = None\n"
               u"def process_series():\n    cruas = {}\n" + _CHAMA))
    import ast as _ast
    _linhas = vig.splitlines(True)
    _alvos = [n.lineno for n in _ast.walk(_ast.parse(vig))
              if isinstance(n, _ast.Assign)
              and any(isinstance(t, _ast.Name) and t.id == "cruas"
                      for t in n.targets)
              and isinstance(n.value, _ast.Dict) and not n.value.keys]
    for _l in _alvos:
        _linhas[_l - 1] = _linhas[_l - 1].replace("{}", "None", 1)
    checar(u"  ISCA (o `cruas = {}` do vigia real trocado por `None`) e "
           u"acusada", bool(_alvos)
           and not _cruas_nao_dependem_so_do_ts("".join(_linhas)),
           u"%d atribuicao(oes) trocada(s)" % len(_alvos))


def _cruas_nao_dependem_so_do_ts(fonte):
    import ast
    try:
        arv = ast.parse(fonte)
    except SyntaxError:
        return False
    pai = {}
    for n in ast.walk(arv):
        for f in ast.iter_child_nodes(n):
            pai[f] = n
    _ESCOPOS = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda,
                ast.ClassDef)

    def _escopo(n):
        while n in pai:
            n = pai[n]
            if isinstance(n, _ESCOPOS) or isinstance(n, ast.Module):
                return n
        return n

    def _no_escopo(esc):
        pilha = list(ast.iter_child_nodes(esc))
        while pilha:
            n = pilha.pop()
            yield n
            if not isinstance(n, _ESCOPOS):
                pilha.extend(ast.iter_child_nodes(n))

    def _vazio(v):
        return isinstance(v, ast.Dict) and not v.keys

    def _liga_os_niveis(t):
        if isinstance(t, ast.Name):
            return t.id == "INCLUIR_HNLNL"
        if isinstance(t, ast.Attribute):
            return t.attr == "INCLUIR_HNLNL"
        if (isinstance(t, ast.Call) and getattr(t.func, "id", "") == "bool"
                and len(t.args) == 1 and not t.keywords):
            return _liga_os_niveis(t.args[0])
        if isinstance(t, ast.BoolOp) and isinstance(t.op, ast.Or):
            return any(_liga_os_niveis(v) for v in t.values)
        return False

    def _valor_aceito(v):
        if _vazio(v):
            return True
        return (isinstance(v, ast.IfExp) and _vazio(v.body)
                and _liga_os_niveis(v.test))

    def _pos(n):
        return (getattr(n, "lineno", 0), getattr(n, "col_offset", 0))

    chamadas = [n for n in ast.walk(arv)
                if isinstance(n, ast.Call)
                and getattr(n.func, "attr", getattr(n.func, "id", ""))
                in ("run_ts_task", "rodar_tasks")
                and any(k.arg == "cruas" for k in n.keywords)]
    if not chamadas:
        return False
    for ch in chamadas:
        x = [k.value for k in ch.keywords if k.arg == "cruas"][0]
        if not isinstance(x, ast.Name):
            return False
        nome = x.id
        antes = False
        for n in _no_escopo(_escopo(ch)):
            if isinstance(n, _ESCOPOS):
                for d in ast.walk(n):
                    if (isinstance(d, (ast.Nonlocal, ast.Global))
                            and nome in d.names):
                        return False
                continue
            if isinstance(n, (ast.Nonlocal, ast.Global)) and nome in n.names:
                return False
            if not (isinstance(n, ast.Name) and n.id == nome
                    and isinstance(n.ctx, (ast.Store, ast.Del))):
                continue
            st = pai.get(n)
            if not (isinstance(st, (ast.Assign, ast.AnnAssign))
                    and st.value is not None and _valor_aceito(st.value)):
                return False
            if _pos(st) < _pos(ch):
                antes = True
        if not antes:
            return False
    return True



def teste_comparacao_cobre_os_tres_motores():
    secao(u"a comparacao medida deixou de ser so contra o VISTA")
    import radai_archive as AC
    import inspect
    a = inspect.signature(AC.registrar_comparacao).parameters
    checar(u"o registro sabe QUAL motor esta no segundo painel",
           "motor_b" in a)
    checar(u"e o padrao dele e `nv` — comparacao NOVA e contra o NV",
           a["motor_b"].default == "nv")
    checar(u"e o registro ANTIGO continua legivel (a migracao e em radai_archive)",
           "vista" in io.open(_componentes.fonte("app/radai_archive.py"),
                              encoding="utf-8").read())


    vig = io.open(_componentes.fonte("app/radai_watcher.py"),
                  encoding="utf-8").read()
    _COMPARACAO = ("nv", "cads", "mse")
    _PONTES = ("enfileirar_cads(", "radai_nv_engine.", "radai_cads_engine.",
               "radai_moose_engine.", "rodar_para_entrega(")

    def _pontes_no_vigia(fonte):
        codigo = u"\n".join(l for l in fonte.splitlines()
                            if not l.lstrip().startswith("#"))
        return [p for p in _PONTES if p in codigo]
    checar(u"o vigia nao chama motor de comparacao (NV, CADS, MOOSE)",
           not _pontes_no_vigia(vig), str(_pontes_no_vigia(vig)))
    checar(u"  ISCA (o `enfileirar_cads(` de volta ao laco) e acusada",
           bool(_pontes_no_vigia(vig + u"\n    CP.enfileirar_cads(uid, m, c, g)\n")))
    for chave in ("INCLUIR_NV", "INCLUIR_CADS", "INCLUIR_MOOSE"):
        casas = _casas_da_chave(vig, chave)
        checar(u"`%s` saiu das tres casas e esta em CHAVES_OBSOLETAS" % chave,
               not (casas["texto"] or casas["defaults"] or casas["aplicar"])
               and bool(casas["obsoleta"]), str(casas))
    import radai_modes as _MD

    def _comparacao_arrastada(protocolos):
        return sorted(set(m for p in protocolos
                          for m in (p.get("motores") or ())
                          if m in _COMPARACAO))
    checar(u"nenhum protocolo do PERSONALIZADO arrasta motor de comparacao",
           not _comparacao_arrastada(_MD.PROTOCOLOS),
           str(_comparacao_arrastada(_MD.PROTOCOLOS)))
    checar(u"  ISCA (um protocolo forjado ligando o NV) e acusada",
           _comparacao_arrastada(tuple(_MD.PROTOCOLOS) + (
               {"cod": "isca", "motores": ("nv",)},)) == ["nv"])
    _todos = tuple(p["cod"] for p in _MD.PROTOCOLOS)
    checar(u"  e todos os protocolos ligados juntos nao ligam comparacao "
           u"(so os niveis e os motores que entram no FULL)",
           set(_MD.motores_dos_protocolos(_todos, "CT"))
           <= ({"hnlnl"} | set(_MD.MOTORES_NO_FULL))
           and not set(_MD.MOTORES_NO_FULL) & set(_COMPARACAO),
           str(_MD.motores_dos_protocolos(_todos, "CT")))
    checar(u"  e sem caixa marcada, nenhum motor roda",
           _MD.motores_da_escolha((), "CT") == ())


def teste_a_ressalva_chega_ao_dicom():
    secao(u"a ressalva de cada nivel chega ao DICOM")
    import radai_hnlnl as HN
    import radai_output as RO

    m = np.zeros((2, 2, 2), bool)
    m[0, 0, 0] = True
    ped = _pedido_de("niveis_cervicais",
                     {"Lvl_III_R": m, HN.NOME_DA_UNIAO: m.copy()})
    obs = ped.get("observacoes") or {}
    checar(u"a Saida PEDE `observacoes` ao motor, com a chave da mascara",
           set(obs) == {"Lvl_III_R", HN.NOME_DA_UNIAO}, sorted(obs))
    checar(u"  e o texto do 7 diz o nivel, o rotulo e que nao e CTV",
           u"Nivel III direito (jugular media)" in (obs.get("Lvl_III_R")
                                                   or u"")
           and u"Rotulo 7 de 20" in (obs.get("Lvl_III_R") or u"")
           and u"nao e CTV" in (obs.get("Lvl_III_R") or u""))
    checar(u"  e a uniao leva o texto dela",
           u"Uniao anatomica nao aprovada" in (obs.get(HN.NOME_DA_UNIAO)
                                               or u""))
    checar(u"nome desconhecido nao ganha texto inventado",
           HN.observacoes_dos_niveis(["Nodulo", "LNL03"]).keys() == {"LNL03"})

    import tempfile as _tf
    base = _tf.mkdtemp(prefix="radai_chk_")

    class _MotorAntigo(object):
        def __init__(self):
            self.kw = []

        def build_rtstruct(self, stage, masks, tasks=None, versao_worker="",
                           origem=None, derivar=False, log=None, cru=False,
                           descontar=False, sufixo_do_conjunto=None,
                           suavizar_mm=None, rotulo=None):
            self.kw.append(dict(rotulo=rotulo))
            p = os.path.join(base, "velho.dcm")
            io.open(p, "wb").write(b"x")
            return p, dict((k, k) for k in masks)
    linhas = []
    velho = _MotorAntigo()
    sd = RO.Saida(velho, base, base, "RS_RadAI_x.dcm", log=linhas.append,
                  copiar=lambda o, d: None, grade=object())
    alvo = sd.niveis_cervicais({"LNL07": m})
    checar(u"motor sem `observacoes`: o conjunto SAI assim mesmo",
           bool(alvo) and velho.kw, str(alvo))
    checar(u"  e o log DIZ que saiu sem a descricao",
           any(u"nao aceita a descricao" in l for l in linhas),
           u" | ".join(linhas)[:160])

    try:
        import pydicom
        import engine as E
        sys.path.insert(0, os.path.join(RAIZ, "tools"))
        from make_test_series import escreve_serie
        from datetime import datetime as _dt
    except Exception as e:
        checar(u"motor de verdade importa neste runtime", False,
               u"%s: %s" % (type(e).__name__, e))
        return
    serie = os.path.join(base, "serie")
    escreve_serie(serie, "FANTOMA_HNL", _dt(2026, 9, 23, 10, 0), 24)
    zz, yy, xx = np.ogrid[0:24, 0:128, 0:128]
    bola = (((zz - 12) * 3.0) ** 2 + ((yy - 64) * 2.0) ** 2
            + ((xx - 64) * 2.0) ** 2) <= 20.0 ** 2
    destino = os.path.join(base, "saida")
    os.makedirs(destino)
    sd = RO.Saida(E, serie, destino, "RS_RadAI_20260923_hnl.dcm",
                  tasks=("total_v3",), versao="teste", log=linhas.append)
    meia = np.zeros_like(bola)
    meia[:, :, :64] = True
    parte_a, parte_b = bola & meia, bola & ~meia
    _ini = len(linhas)
    alvo = sd.niveis_cervicais({"Lvl_III_R": parte_a, "Lvl_II_R": parte_b,
                                HN.NOME_DA_UNIAO: bola.copy()})
    _sob = [l for l in linhas[_ini:] if u"SOBREPOSICAO" in l]
    checar(u"no HNL_, a uniao nao alarma sobreposicao com os niveis que ela "
           u"contem", not any(HN.NOME_DA_UNIAO in l for l in _sob),
           u" | ".join(_sob)[:200])
    if not (alvo and os.path.isfile(alvo)):
        checar(u"o conjunto dos niveis foi gravado pelo motor de verdade",
               False, u" | ".join(linhas[-4:])[:200])
        return
    ds = pydicom.dcmread(alvo)
    nome_de = dict((int(r.ROINumber), str(r.ROIName))
                   for r in ds.StructureSetROISequence)
    desc = dict((nome_de.get(int(o.ReferencedROINumber)),
                 str(getattr(o, "ROIObservationDescription", "") or ""))
                for o in ds.RTROIObservationsSequence)
    d7 = desc.get("Lvl_III_R" + HN.SUFIXO) or u""
    checar(u"no DICOM, `Lvl_III_R_lnl` diz o nivel e o rotulo 7 de 20",
           u"Nivel III direito" in d7 and u"Rotulo 7 de 20" in d7,
           d7[:120] or sorted(desc))
    checar(u"  e que e compartimento anatomico, nao CTV", u"nao e CTV" in d7)
    du = desc.get(HN.NOME_DA_UNIAO + HN.SUFIXO) or u""
    checar(u"  e a uniao diz que nao e OAR nem CTV",
           u"NAO E OAR NEM CTV" in du, du[:120])
    checar(u"  e os nomes sao os do mapa",
           sorted(nome_de.values()) == sorted(
               ["Lvl_III_R" + HN.SUFIXO, "Lvl_II_R" + HN.SUFIXO,
                HN.NOME_DA_UNIAO + HN.SUFIXO]), sorted(nome_de.values()))
    try:
        import radai_rt
        ses = radai_rt.abrir(serie, alvo, com_ct=False)
        lidas = dict((n, np.asarray(ses.mascara(n), bool))
                     for n in nome_de.values())
        ou = (lidas["Lvl_III_R" + HN.SUFIXO]
              | lidas["Lvl_II_R" + HN.SUFIXO])
        uni = lidas[HN.NOME_DA_UNIAO + HN.SUFIXO]
        d = 2.0 * float((ou & uni).sum()) / max(1.0, float(ou.sum()
                                                          + uni.sum()))
        checar(u"a volta pelo RTSTRUCT: DSC(uniao, OR das partes lidas) "
               u">= 0,99", d >= 0.99, u"%.4f" % d)
    except Exception as e:
        checar(u"a volta pelo RTSTRUCT abre", False,
               u"%s: %s" % (type(e).__name__, str(e)[:120]))
    _ini2 = len(linhas)
    sd.niveis_cervicais({"Lvl_III_R": parte_a, "Lvl_IVa_R": parte_a.copy(),
                         HN.NOME_DA_UNIAO: parte_a.copy()})
    checar(u"  ISCA: dois niveis sobrepostos continuam alarmando",
           any(u"SOBREPOSICAO" in l and u"Lvl_III_R" in l and u"Lvl_IVa_R" in l
               for l in linhas[_ini2:]),
           u" | ".join(l for l in linhas[_ini2:] if u"SOBREP" in l)[:200])


def teste_a_cadeia_e_uma_so():
    secao(u"a cadeia dos niveis e uma so, para as duas portas")
    import ast as _ast
    import SimpleITK as sitk
    import radai_hnlnl as HN
    import radai_hnlnl_engine as HM
    import radai_output as RO

    ref = sitk.Image(16, 12, 8, sitk.sitkInt16)
    ref.SetSpacing((1.0, 1.0, 3.0))
    pedidos, linhas = [], []
    guard = (HN.disponivel, HN.rodar_na_serie)
    try:
        HN.disponivel = lambda: (True, "pesos")

        def _rodar(vol, cruas, forma, grade, device="cpu", log=None, fold=0, **kw):
            pedidos.append({"cruas": cruas, "forma": forma, "device": device,
                            "vol": tuple(vol.shape)})
            return {"LNL01": np.ones(forma, bool)}
        HN.rodar_na_serie = _rodar
        saida = RO.niveis_cervicais_da_serie(
            ref, {"lung_vessels": "OUTRA", "total_v3": "A_BASE"},
            device="gpu", log=linhas.append)
        checar(u"com a base em `total_v3`, a cadeia recebe os crus DELA",
               pedidos and pedidos[-1]["cruas"] == "A_BASE",
               pedidos[-1]["cruas"] if pedidos else u"nao chamou")
        checar(u"  com a forma (z, y, x)",
               pedidos and pedidos[-1]["forma"] == (8, 12, 16)
               and pedidos[-1]["vol"] == (8, 12, 16),
               str(pedidos[-1] if pedidos else None))
        checar(u"  e `gpu` chega ao modelo como `cuda` (o nome do `torch`)",
               pedidos and pedidos[-1]["device"] == "cuda",
               str(pedidos[-1]["device"] if pedidos else None))
        checar(u"  e devolve o que ela devolveu", list(saida) == ["LNL01"])
        RO.niveis_cervicais_da_serie(ref, {"total_v3": "A_BASE"},
                                     device="cpu", log=linhas.append)
        checar(u"  e `cpu` chega como `cpu`",
               pedidos and pedidos[-1]["device"] == "cpu",
               str(pedidos[-1]["device"] if pedidos else None))

        def _placa_cheia(vol, cruas, forma, grade, device="cpu", log=None,
                         fold=0, **kw):
            pedidos.append({"device": device})
            if device != "cpu":
                raise RuntimeError("CUDA out of memory. Tried to allocate "
                                   "1.20 GiB")
            return {"LNL02": np.ones(forma, bool)}
        HN.rodar_na_serie = _placa_cheia
        n = len(pedidos)
        saida, subiu = {}, u""
        try:
            saida = RO.niveis_cervicais_da_serie(
                ref, {"total_v3": "A_BASE"}, device="gpu", log=linhas.append)
        except Exception as e:
            subiu = u" | subiu %s: %s" % (type(e).__name__, str(e)[:60])
        checar(u"a placa falha: a cadeia tenta na placa e refaz em CPU",
               [p["device"] for p in pedidos[n:]] == ["cuda", "cpu"],
               str(pedidos[n:]) + subiu)
        checar(u"  e entrega o que a CPU devolveu", list(saida) == ["LNL02"],
               str(list(saida or {})))
        checar(u"  e o log diz que a placa falhou, e por que",
               any(u"a placa falhou" in l and u"out of memory" in l
                   for l in linhas), u" | ".join(linhas[-3:])[:200])

        def _forma_errada(vol, cruas, forma, grade, device="cpu", log=None,
                          fold=0, **kw):
            pedidos.append({"device": device})
            raise ValueError("a forma do recorte nao bate com o plano")
        HN.rodar_na_serie = _forma_errada
        n = len(pedidos)
        subiu = None
        try:
            RO.niveis_cervicais_da_serie(ref, {"total_v3": "A_BASE"},
                                         device="gpu", log=linhas.append)
        except ValueError as e:
            subiu = str(e)
        checar(u"erro que nao e da placa sobe como veio, sem refazer em CPU",
               subiu is not None and len(pedidos) - n == 1,
               u"subiu=%r, chamadas=%d" % (subiu, len(pedidos) - n))
        def _sempre_cuda(vol, cruas, forma, grade, device="cpu", log=None,
                         fold=0, **kw):
            pedidos.append({"device": device})
            raise RuntimeError("CUDA error: no kernel image is available")
        HN.rodar_na_serie = _sempre_cuda
        n = len(pedidos)
        subiu = None
        try:
            RO.niveis_cervicais_da_serie(ref, {"total_v3": "A_BASE"},
                                         device="cpu", log=linhas.append)
        except RuntimeError as e:
            subiu = str(e)
        checar(u"  e em CPU nao ha para onde recuar: sobe, sem refazer",
               subiu is not None and len(pedidos) - n == 1,
               u"subiu=%r, chamadas=%d" % (subiu, len(pedidos) - n))
        HN.rodar_na_serie = _rodar
        n = len(pedidos)
        RO.niveis_cervicais_da_serie(ref, {"total_mr": "RM"},
                                     log=linhas.append)
        checar(u"`total_mr` nao passa por base — o modelo nao roda",
               len(pedidos) == n)
        checar(u"  e o log nomeia a FAMILIA que faltou",
               u"familia `total`" in (linhas[-1] if linhas else u""),
               linhas[-1] if linhas else u"")
        HN.disponivel = lambda: (False, u"os pesos nao estao instalados")
        RO.niveis_cervicais_da_serie(ref, {"total_v3": "A_BASE"},
                                     log=linhas.append)
        checar(u"sem os pesos nao roda, e o log diz o motivo",
               len(pedidos) == n and u"nao estao instalados" in linhas[-1],
               linhas[-1] if linhas else u"")
    finally:
        HN.disponivel, HN.rodar_na_serie = guard

    def _chamadas(arq, nome):
        arv = _ast.parse(io.open(_componentes.fonte("app/" + arq),
                                 encoding="utf-8").read())
        return [n for n in _ast.walk(arv) if isinstance(n, _ast.Call)
                and isinstance(n.func, _ast.Attribute) and n.func.attr == nome]
    for arq in ("radai_watcher.py", "radai_batch.py"):
        checar(u"[%s] chama `radai_output.niveis_cervicais_da_serie`" % arq,
               len(_chamadas(arq, "niveis_cervicais_da_serie")) == 1,
               len(_chamadas(arq, "niveis_cervicais_da_serie")))
        checar(u"[%s] e nao chama `rodar_na_serie` por fora" % arq,
               not _chamadas(arq, "rodar_na_serie"))


def teste_o_device_do_torch():
    secao(u"o motor fala `cuda`, e o projeto fala `gpu`")
    import ast as _ast
    import radai_hnlnl_engine as HM
    casos = [("gpu", "cuda"), ("GPU ", "cuda"), ("cuda", "cuda"),
             ("cuda:1", "cuda:1"), ("cpu", "cpu"), ("", "cpu"), (None, "cpu"),
             ("auto", "cpu")]
    for de, para in casos:
        checar(u"%r vira %r" % (de, para), HM._torch_device(de) == para,
               repr(HM._torch_device(de)))

    placa = [RuntimeError("CUDA out of memory. Tried to allocate 2.00 GiB"),
             AssertionError("Torch not compiled with CUDA enabled"),
             RuntimeError("Found no NVIDIA driver on your system"),
             RuntimeError("cuDNN error: CUDNN_STATUS_NOT_INITIALIZED")]
    for e in placa:
        checar(u"%s e erro de placa" % type(e).__name__
               + (u" (`torch` sem CUDA)" if "compiled" in str(e) else u""),
               bool(HM.erro_de_placa(e)), str(e))
    for e in (ValueError("a forma do recorte nao bate com o plano"),
              IOError("nao achei os pesos do fold 0"),
              KeyError("seg_outputs.0.weight")):
        checar(u"%s NAO e erro de placa (nao justifica refazer)"
               % type(e).__name__, HM.erro_de_placa(e) is None, str(e))

    arv = _ast.parse(io.open(os.path.join(RAIZ, "app",
                                          "radai_hnlnl_engine.py"),
                             encoding="utf-8").read())
    for nome in ("carregar", "inferir"):
        fn = [n for n in arv.body if isinstance(n, _ast.FunctionDef)
              and n.name == nome]
        traduz = bool(fn) and any(
            isinstance(n, _ast.Assign)
            and any(isinstance(t, _ast.Name) and t.id == "device"
                    for t in n.targets)
            and isinstance(n.value, _ast.Call)
            and isinstance(n.value.func, _ast.Name)
            and n.value.func.id == "_torch_device"
            for n in _ast.walk(fn[0]))
        checar(u"`%s` traduz o device antes de usa-lo" % nome, traduz)


def teste_os_candidatos_nao_atravessam_series():
    secao(u"o candidato de uma serie nao atravessa para a seguinte")
    import ast as _ast
    import radai_hnlnl as HN
    antes = dict((i, dict(d)) for i, d in HN.NIVEIS.items())
    try:
        HN.NIVEIS[3]["confirmado"] = False
        HN.NIVEIS[3]["candidato"] = u"II_L"
        HN._esquecer_candidatos()
        checar(u"o candidato NAO confirmado sai",
               HN.NIVEIS[3]["candidato"] == u"")
        checar(u"  e o CONFIRMADO (o mapa dos pesos) fica",
               HN.NIVEIS[4]["candidato"] == u"II_L")
    finally:
        for i, d in antes.items():
            HN.NIVEIS[i] = d
    checar(u"os 20 nascem confirmados pelo mapa dos pesos",
           all(HN.NIVEIS[i]["confirmado"] for i in range(1, 21)))
    arv = _ast.parse(io.open(_componentes.fonte("app/radai_hnlnl.py"),
                             encoding="utf-8").read())
    corpo = [n for n in _ast.walk(arv) if isinstance(n, _ast.FunctionDef)
             and n.name == "rodar_na_serie"]
    linhas = {}
    for n in _ast.walk(corpo[0] if corpo else arv):
        if isinstance(n, _ast.Call) and isinstance(n.func, _ast.Name):
            linhas.setdefault(n.func.id, n.lineno)
    checar(u"e `rodar_na_serie` limpa ANTES de nomear",
           0 < linhas.get("_esquecer_candidatos", 0)
           < linhas.get("masks_dos_niveis", 0),
           str(dict((k, linhas.get(k)) for k in
                    ("_esquecer_candidatos", "masks_dos_niveis"))))


_FILHO_FALSO = u'''# -*- coding: utf-8 -*-
import json, os, sys, time
import numpy as np
base, fold, entrada, saida, device = sys.argv[2:7]
with open(os.path.join(base, "chamadas.jsonl"), "a") as f:
    f.write(json.dumps({"pid": os.getpid(), "device": device, "fold": fold,
                        "bandeira": sys.argv[1]}) + "\\n")
modo = open(os.path.join(base, "modo.txt")).read().strip()
if modo == "placa" and device != "cpu":
    print("HNLNL|erro|OutOfMemoryError: CUDA out of memory. Tried to "
          "allocate 1.20 GiB", flush=True)
    sys.exit(3)
if modo == "valor":
    print("HNLNL|erro|ValueError: a forma do recorte nao bate", flush=True)
    sys.exit(3)
if modo == "mudo":
    sys.exit(7)
if modo == "dorme":
    time.sleep(300)
vol = np.load(entrada)
print("HNLNL|pulso|janela 10/20", flush=True)
rot = np.zeros(vol.shape, dtype="int8")
zc, yc, xc = [s // 2 for s in vol.shape]
if modo == "metade":
    rot[..., xc:] = 2
    rot[..., :xc] = 3
elif modo == "anel":
    yy, xx = np.mgrid[0:vol.shape[1], 0:vol.shape[2]]
    r2 = (yy - yc) ** 2 + (xx - xc) ** 2
    anel = (r2 <= 64) & (r2 > 16)
    for z in range(zc - 3, zc + 3):
        rot[z][anel] = 6
elif modo == "viii_trocado":
    for k, (a, b) in enumerate(((2, 3), (8, 9), (12, 13), (20, 19))):
        y0 = yc - 14 + 8 * k
        rot[zc - 3:zc + 3, y0:y0 + 6, xc + 4:xc + 12] = a
        rot[zc - 3:zc + 3, y0:y0 + 6, xc - 12:xc - 4] = b
else:
    rot[zc - 3:zc + 3, yc - 10:yc + 10, xc - 12:xc - 2] = 3
    rot[zc - 3:zc + 3, yc - 10:yc + 10, xc + 2:xc + 12] = 4
np.save(saida, rot)
print("HNLNL|ok", flush=True)
'''


def teste_a_rede_roda_em_processo_separado():
    secao(u"a rede dos niveis roda num processo filho, e a placa volta com ele")
    import ast as _ast
    import glob as _glob
    import json as _json
    import pickle as _pickle
    import time as _time
    import SimpleITK as sitk
    import radai_hnlnl as HN
    import radai_hnlnl_engine as HM
    import radai_output as RO

    arv = _ast.parse(io.open(_componentes.fonte("app/radai_hnlnl.py"),
                             encoding="utf-8").read())
    corpo = [n for n in _ast.walk(arv) if isinstance(n, _ast.FunctionDef)
             and n.name == "rodar_na_serie"]
    chamadas = set()
    for n in _ast.walk(corpo[0] if corpo else arv):
        if isinstance(n, _ast.Call) and isinstance(n.func, _ast.Attribute):
            chamadas.add(n.func.attr)
    checar(u"`rodar_na_serie` nao chama `carregar` nem `inferir` (a rede "
           u"nao sobe no processo do vigia)",
           not (chamadas & {"carregar", "inferir"}), str(sorted(chamadas)))
    checar(u"  e chama `inferir_em_processo_separado`",
           "inferir_em_processo_separado" in chamadas)
    for arq in ("radai_output.py", "radai_watcher.py", "radai_batch.py"):
        a = _ast.parse(io.open(_componentes.fonte("app/" + arq),
                               encoding="utf-8").read())
        diretas = [n.lineno for n in _ast.walk(a) if isinstance(n, _ast.Call)
                   and isinstance(n.func, _ast.Attribute)
                   and n.func.attr in ("carregar", "inferir")
                   and isinstance(n.func.value, _ast.Name)
                   and n.func.value.id in ("HM", "radai_hnlnl_engine")]
        checar(u"[%s] nao roda a rede dos niveis por fora" % arq,
               not diretas, str(diretas))

    oficina = _cleanup.temporaria("radai_chk_hnl_")
    script = os.path.join(oficina, "filho_falso.py")
    with io.open(script, "w", encoding="utf-8") as f:
        f.write(_FILHO_FALSO)
    base = os.path.join(oficina, "pesos")
    os.makedirs(base)

    def _modo(m):
        with io.open(os.path.join(base, "modo.txt"), "w") as f:
            f.write(m)
        try:
            os.remove(os.path.join(base, "chamadas.jsonl"))
        except OSError:
            pass

    def _chamadas():
        try:
            with io.open(os.path.join(base, "chamadas.jsonl")) as f:
                return [_json.loads(l) for l in f if l.strip()]
        except (IOError, OSError):
            return []

    tmp = __import__("tempfile").gettempdir()

    def _sobras():
        return set(_glob.glob(os.path.join(tmp, "radai_hnlnl_*")))

    guard = (HM._SCRIPT_DO_FILHO, HN.disponivel)
    try:
        HM._SCRIPT_DO_FILHO = script
        vol = np.zeros((20, 40, 50), dtype="float32")
        linhas = []
        _modo("ok")
        antes = _sobras()
        rot = HM.inferir_em_processo_separado(base, vol, fold=0, device="gpu",
                                              log=linhas.append)
        ch = _chamadas()
        checar(u"o filho e OUTRO processo",
               len(ch) == 1 and ch[0]["pid"] != os.getpid(), str(ch))
        checar(u"  recebe a bandeira `--filho` e o `cuda` do torch (e nao "
               u"`gpu`)", ch and ch[0]["bandeira"] == "--filho"
               and ch[0]["device"] == "cuda", str(ch))
        checar(u"  e o mapa de rotulos volta inteiro, na forma do volume",
               tuple(rot.shape) == vol.shape
               and sorted(int(v) for v in np.unique(rot)) == [0, 3, 4],
               "%s %s" % (rot.shape, np.unique(rot)))
        checar(u"  o andamento do filho chega ao log do pai",
               any(u"janela 10/20" in l for l in linhas), u" | ".join(linhas))
        checar(u"  e o log diz que a rede rodou em processo separado",
               any(u"processo separado" in l for l in linhas),
               u" | ".join(linhas))
        checar(u"  e a pasta temporaria dele sai", _sobras() <= antes,
               str(sorted(_sobras() - antes)))

        _modo("placa")
        erro = None
        try:
            HM.inferir_em_processo_separado(base, vol, device="cuda")
        except HM.FalhaNoProcessoDaRede as e:
            erro = e
        checar(u"a falha do filho vira `FalhaNoProcessoDaRede`, com o texto "
               u"do filho", erro is not None
               and u"OutOfMemoryError: CUDA out of memory" in str(erro),
               str(erro))
        checar(u"  e OutOfMemory no filho continua sendo erro de placa aqui "
               u"(a refeita em CPU dispara)",
               erro is not None and bool(HM.erro_de_placa(erro)), str(erro))
        _modo("valor")
        erro = None
        try:
            HM.inferir_em_processo_separado(base, vol, device="cuda")
        except HM.FalhaNoProcessoDaRede as e:
            erro = e
        checar(u"erro que nao e da placa, no filho, NAO vira erro de placa",
               erro is not None and HM.erro_de_placa(erro) is None
               and u"ValueError" in str(erro), str(erro))
        _modo("mudo")
        erro = None
        try:
            HM.inferir_em_processo_separado(base, vol)
        except HM.FalhaNoProcessoDaRede as e:
            erro = e
        checar(u"filho que morre sem dizer nada: o codigo de saida aparece",
               erro is not None and u"codigo 7" in str(erro), str(erro))
        _modo("dorme")
        erro, t0 = None, _time.time()
        try:
            HM.inferir_em_processo_separado(base, vol, timeout_s=2)
        except HM.FalhaNoProcessoDaRede as e:
            erro = e
        dt = _time.time() - t0
        checar(u"o tempo-limite interrompe o filho (e o vigia nao fica preso)",
               erro is not None and u"interrompida" in str(erro) and dt < 90,
               u"%.1f s: %s" % (dt, erro))
        checar(u"  e tempo esgotado NAO passa por erro de placa",
               erro is not None and HM.erro_de_placa(erro) is None, str(erro))
        checar(u"  e nenhuma pasta temporaria sobra, nem dos que falharam",
               _sobras() <= antes, str(sorted(_sobras() - antes)))

        HM._SCRIPT_DO_FILHO = None
        erro = None
        try:
            HM.inferir_em_processo_separado(os.path.join(oficina, "sem_pesos"),
                                            vol, timeout_s=300)
        except HM.FalhaNoProcessoDaRede as e:
            erro = e
        checar(u"o filho de verdade (`--filho`) roda e devolve o erro dele "
               u"pela fronteira", erro is not None and any(
                   t in str(erro) for t in ("ModuleNotFoundError",
                                            "FileNotFoundError", "IOError",
                                            "OSError")), str(erro))
        HM._SCRIPT_DO_FILHO = script

        with io.open(os.path.join(base, "plans.pkl"), "wb") as f:
            _pickle.dump({
                "plans_per_stage": {0: {"patch_size": [8, 16, 16],
                                        "current_spacing": [3.0, 1.0, 1.0],
                                        "pool_op_kernel_sizes": [[1, 2, 2]]}},
                "dataset_properties": {"intensityproperties": {0: {
                    "percentile_00_5": -1000.0, "percentile_99_5": 2000.0,
                    "mean": 0.0, "sd": 100.0}}},
                "num_classes": 20}, f)
        HN.disponivel = lambda: (True, base)
        cruas, forma = _pescoco_sintetico()
        ref = sitk.Image(forma[2], forma[1], forma[0], sitk.sitkInt16)
        ref.SetSpacing((1.0, 1.0, 3.0))
        _modo("placa")
        log_cadeia = []
        antes = _sobras()
        saida = RO.niveis_cervicais_da_serie(ref, {"total_v3": cruas},
                                             device="gpu",
                                             log=log_cadeia.append)
        ch = _chamadas()
        checar(u"a cadeia inteira: tenta na placa, o filho cai, refaz em CPU",
               [c["device"] for c in ch] == ["cuda", "cpu"], str(ch))
        checar(u"  os dois filhos sao processos separados do vigia",
               len(ch) == 2 and all(c["pid"] != os.getpid() for c in ch)
               and ch[0]["pid"] != ch[1]["pid"], str(ch))
        checar(u"  e o log diz que a placa falhou, com o texto do filho",
               any(u"a placa falhou" in l and u"out of memory" in l
                   for l in log_cadeia), u" | ".join(log_cadeia)[-300:])
        checar(u"  e os niveis saem, nomeados e conferidos pelo pai "
               u"(neutros: os pesos de mentira nao sao a versao do mapa)",
               sorted(saida) == sorted([HN.nome_do_nivel(3, False),
                                        HN.nome_do_nivel(4, False),
                                        HN.NOME_DA_UNIAO_NEUTRA]),
               str(sorted(saida)))
        checar(u"  e nada do filho sobra na pasta temporaria",
               _sobras() <= antes, str(sorted(_sobras() - antes)))
    finally:
        HM._SCRIPT_DO_FILHO, HN.disponivel = guard


class _MotorEspiao(object):
    def __init__(self):
        self.chamadas = []

    def build_rtstruct(self, stage, masks, **kw):
        self.chamadas.append(dict(kw, _n=len(masks), _masks=masks))
        return (__import__("os").path.join(stage, "falso.dcm"),
                dict((k, k) for k in masks))

    def curar(self, masks, outros, log=None):
        return masks, {}


def _pedido_de(metodo, masks, **extra):
    import tempfile, os as _os
    esp = _MotorEspiao()
    base = tempfile.mkdtemp(prefix="radai_chk_")
    import radai_output
    sd = radai_output.Saida(esp, base, base, "RS_RadAI_x.dcm",
                           tasks=("total",), versao="teste", suavizar_mm=1.5,
                           copiar=lambda o, d: None, grade=object())
    getattr(sd, metodo)(masks, **extra)
    return esp.chamadas[0] if esp.chamadas else {}


def main():
    print("=" * 70)
    print(u" niveis linfonodais cervicais (Weissmann et al. 2023, CC0-1.0)")
    print("=" * 70)
    for t in (teste_portao, teste_recorte, teste_orientacao,
              teste_o_ajuste_e_o_dos_autores, teste_as_fatias_extremas,
              teste_o_mapa_e_o_dos_autores, teste_nomes_finais,
              teste_o_pos_dos_pesos, teste_a_volta_nao_desloca,
              teste_a_volta_linear_contra_o_vizinho,
              teste_lado_invertido_recusa,
              teste_par_trocado_perde_o_nome_de_lado, teste_ilhas_por_nivel,
              teste_cavidade_vascular, teste_suavizacao_dos_niveis,
              teste_cores_dos_niveis, teste_textos_dos_niveis,
              teste_uniao, teste_parotidas_do_viii_unidade,
              teste_a_rede_ve_sempre_a_mesma_orientacao,
              teste_hnl_e_o_publicado, teste_a_cadeia_na_ordem,
              teste_recorte_ap, teste_ensemble_e_o_padrao,
              teste_sem_os_pesos_do_ensemble_nao_roda,
              teste_a_porta_nao_pede_o_fold_0,
              teste_o_ensemble_soma_as_dez_redes,
              teste_o_teto_cobre_o_ensemble,
              teste_o_registro_diz_o_ensemble,
              teste_extensao, teste_travas, teste_normalizacao,
              teste_primeiro_plano, teste_rede_reconstruida,
              teste_registro, teste_costura_no_vigia,
              teste_a_ressalva_chega_ao_dicom, teste_a_cadeia_e_uma_so,
              teste_o_device_do_torch,
              teste_a_rede_roda_em_processo_separado,
              teste_os_candidatos_nao_atravessam_series,
              teste_comparacao_cobre_os_tres_motores):
        try:
            t()
        except Exception as e:
            import traceback
            checar(u"%s (excecao)" % t.__name__, False,
                   "%s: %s" % (type(e).__name__, e))
            traceback.print_exc()
    falhas = [(n, d) for n, ok, d in _R if not ok]
    print("\n" + "=" * 70)
    if falhas:
        print(u"FALHOU: %d de %d checagens" % (len(falhas), len(_R)))
        for n, d in falhas:
            print(u"  - %s%s" % (n, ("  [%s]" % d) if d else ""))
    else:
        print(u"OK: %d checagens, todas passaram" % len(_R))
    print("=" * 70)
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
