# -*- coding: utf-8 -*-
import io
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")

import numpy as np

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.abspath(os.path.join(AQUI, ".."))
APP = os.path.join(RAIZ, "app")
sys.path.insert(0, APP)
sys.path.insert(0, AQUI)

import radai_geom as G
import radai_skin as P
import engine as M
import _componentes

OK = FALHAS = 0
FALHOU = []


def secao(t):
    print(u"\n  -- %s --" % t)


def checar(rotulo, cond, detalhe=""):
    global OK, FALHAS
    if cond:
        OK += 1
        print(u"  ok     %s" % rotulo)
    else:
        FALHAS += 1
        FALHOU.append(rotulo)
        print(u"  FALHA  %s  [%s]" % (rotulo, detalhe))


SP = (2.0, 0.98, 0.98)
Z, Y, X = 120, 200, 280

_CACHE = {}


def montar_fantoma(folga=2, escala=1):
    chave = (int(folga), int(escala))
    if chave not in _CACHE:
        if int(escala) == 1:
            _CACHE[chave] = _montar_fantoma(folga)
        else:
            g, hu, masks, ex = montar_fantoma(folga, 1)
            e = int(escala)
            fatia = (slice(None, None, e),) * 3
            _CACHE[chave] = (
                G.Grade(tuple(s * e for s in g.spacing), g.sentido),
                np.ascontiguousarray(hu[fatia]),
                dict((k, np.ascontiguousarray(v[fatia]))
                     for k, v in masks.items()),
                dict((k, np.ascontiguousarray(v[fatia]))
                     for k, v in ex.items()))
    g, hu, masks, ex = _CACHE[chave]
    return g, hu, dict(masks), dict(ex)


def _montar_fantoma(folga=2):
    grade = G.Grade(SP)
    zz, yy, xx = np.mgrid[0:Z, 0:Y, 0:X]
    cy, cx = 90.0, 140.0

    def my(v):
        return (v - cy) * SP[1]

    def mx(v):
        return (v - cx) * SP[2]

    tronco = (mx(xx) / 138.0) ** 2 + (my(yy) / 90.0) ** 2 <= 1.0
    y0 = 181 + int(folga)
    mesa = (yy >= y0) & (yy < y0 + 3) & (np.abs(mx(xx)) <= 180.0)

    hu = np.full((Z, Y, X), -1000.0, np.float32)
    hu[tronco] = 40.0
    hu[mesa] = 300.0

    def elip(zc, rz, y0, ry, x0, rx):
        return (((zz - zc) * SP[0] / rz) ** 2 + ((my(yy) - y0) / ry) ** 2
                + ((mx(xx) - x0) / rx) ** 2 <= 1.0)

    pul_d = elip(85, 62.0, -8.0, 48.0, -62.0, 38.0) & tronco
    pul_e = elip(85, 62.0, -8.0, 48.0, 62.0, 38.0) & tronco
    hu[pul_d | pul_e] = -800.0

    ang = np.arctan2(my(yy), mx(xx))
    r = (mx(xx) / 132.0) ** 2 + (my(yy) / 82.0) ** 2
    casca = (r <= 1.0) & (r >= 0.78)
    ponta = (my(yy) < 0) & (np.abs(mx(xx)) <= 45.0)
    costelas = {}
    cart = np.zeros_like(casca)
    for i in range(1, 13):
        z0 = 106 - (i - 1) * 8
        arco = casca & (zz >= z0) & (zz < z0 + 4) & (np.abs(ang) > 0.55)
        if i <= 10:
            cart |= arco & ponta & (np.abs(mx(xx)) > 18.0)
        arco = arco & ~ponta
        costelas["rib_right_%d" % i] = arco & (mx(xx) < 0)
        costelas["rib_left_%d" % i] = arco & (mx(xx) >= 0)
    for m in costelas.values():
        hu[m] = 700.0
    hu[cart] = 300.0

    vert = (np.abs(mx(xx)) <= 20.0) & (my(yy) >= 40.0) & (my(yy) <= 76.0)
    est = ((np.abs(mx(xx)) <= 18.0) & (my(yy) <= -62.0) & (my(yy) >= -84.0)
           & (zz >= 62) & (zz < 108))
    fig = elip(36, 38.0, 8.0, 60.0, -50.0, 60.0) & tronco
    rim = elip(28, 22.0, 48.0, 22.0, -46.0, 19.0) & tronco
    hu[vert] = 700.0
    hu[est] = 700.0
    hu[fig] = 60.0
    hu[rim] = 35.0

    pulmoes = pul_d | pul_e
    clav = ((zz >= 110) & (zz <= 116) & (my(yy) >= -80.0) & (my(yy) <= -58.0)
            & (np.abs(mx(xx)) >= 22.0) & (np.abs(mx(xx)) <= 100.0)
            & tronco & ~casca)
    esc = ((zz >= 70) & (zz <= 112) & (my(yy) >= 38.0) & (my(yy) <= 82.0)
           & (np.abs(mx(xx)) >= 70.0) & (np.abs(mx(xx)) <= 125.0)
           & tronco & (r > 1.03))
    auto = ((np.abs(mx(xx)) >= 22.0) & (np.abs(mx(xx)) <= 55.0)
            & (my(yy) >= 50.0) & (my(yy) <= 88.0) & tronco & ~casca & ~vert)
    cor = elip(80, 40.0, -22.0, 33.0, 12.0, 42.0) & tronco & ~pulmoes
    peri = G.expandir(cor, 4.0, grade) & ~cor & tronco
    medi = ((np.abs(mx(xx)) <= 22.0) & (my(yy) >= -60.0) & (my(yy) <= 38.0)
            & (zz >= 60) & (zz <= 116) & tronco & ~cor & ~peri & ~pulmoes)
    cav = elip(22, 44.0, 0.0, 70.0, 0.0, 118.0) & tronco & ~vert & (zz < 50)
    delg = elip(20, 16.0, -35.0, 22.0, 10.0, 40.0) & cav
    hu[cor] = 45.0

    masks = {"lung_right": pul_d, "lung_left": pul_e, "vertebrae_T8": vert,
             "sternum": est, "liver": fig, "kidney_right": rim,
             "costal_cartilages": cart,
             "clavicula_left": clav & (mx(xx) >= 0),
             "clavicula_right": clav & (mx(xx) < 0),
             "scapula_left": esc & (mx(xx) >= 0),
             "scapula_right": esc & (mx(xx) < 0),
             "autochthon_left": auto & (mx(xx) >= 0),
             "autochthon_right": auto & (mx(xx) < 0),
             "heart": cor, "pericardium": peri, "mediastinum": medi,
             "abdominal_cavity": cav, "small_bowel": delg}
    masks.update(costelas)
    extras = {"tronco": tronco, "mesa": mesa, "pulmoes": pulmoes}
    gradil = cart.copy()
    for m in costelas.values():
        gradil |= m
    extras["gradil"] = gradil
    return grade, hu, masks, extras


def faixa_z(m):
    z = np.where(m.any(axis=(1, 2)))[0]
    return (int(z.min()), int(z.max())) if len(z) else (-1, -1)


def teste_contorno_externo_deixa_a_mesa_de_fora():
    secao(u"o contorno externo deixa a mesa de fora")
    grade, hu, masks, ex = montar_fantoma()
    ext = P.contorno_externo(hu, grade)
    checar(u"o contorno externo saiu", ext is not None)
    if ext is None:
        return
    fora_do_corpo = ex["mesa"] & ~ex["tronco"]
    pct_mesa = (100.0 * float((ext & fora_do_corpo).sum())
                / max(1, fora_do_corpo.sum()))
    pct_corpo = 100.0 * float((ext & ex["tronco"]).sum()) / ex["tronco"].sum()
    checar(u"a mesa fica de fora (colchao de 2 mm, o caso real)",
           pct_mesa < 1.0, u"%.1f%% dentro" % pct_mesa)
    checar(u"e o tronco entra inteiro", pct_corpo > 99.0,
           u"%.1f%% coberto" % pct_corpo)
    dentro = 100.0 * float((ext & ex["pulmoes"]).sum()) / ex["pulmoes"].sum()
    checar(u"o pulmao (ar interno) fica DENTRO do contorno externo",
           dentro > 99.0, u"%.1f%%" % dentro)
    gc, huc, _mc, exc = montar_fantoma(folga=0)
    fora_c = exc["mesa"] & ~exc["tronco"]
    velho = P.EROSAO_DA_MESA_MM
    try:
        P.EROSAO_DA_MESA_MM = 0.2
        e2 = P.contorno_externo(huc, gc)
        p2 = (100.0 * float((e2 & fora_c).sum())
              / max(1, fora_c.sum()) if e2 is not None else 0.0)
        checar(u"  em contato, sem erosao a mesa volta INTEIRA (isca)",
               p2 > 90.0, u"%.1f%%" % p2)
    finally:
        P.EROSAO_DA_MESA_MM = velho

    e3 = P.contorno_externo(huc, gc)
    p3 = (100.0 * float((e3 & fora_c).sum()) / max(1, fora_c.sum())
          if e3 is not None else 0.0)
    checar(u"em contato DIRETO sobra uma saia, e nao a mesa inteira",
           p3 < 30.0, u"%.1f%% (medido: 15,7%%)" % p3)
    checar(u"  e o tronco continua inteiro mesmo assim",
           e3 is not None
           and (e3 & exc["tronco"]).sum() > 0.99 * exc["tronco"].sum())


def teste_a_pele_e_uma_casca_e_nao_um_solido():
    secao(u"a pele e uma casca, e nao um solido")
    grade, hu, masks, ex = montar_fantoma()
    ext = P.contorno_externo(hu, grade)
    casca = P.pele(ext, grade)
    checar(u"a pele saiu", casca is not None and casca.any())
    if casca is None:
        return
    v_casca = G.volume_cm3(casca, grade)
    v_solido = G.volume_cm3(ext, grade)
    checar(u"ela e MUITO menor que o solido", v_casca < 0.25 * v_solido,
           u"%.0f contra %.0f cm3" % (v_casca, v_solido))
    checar(u"e e oca: o miolo do paciente NAO esta nela",
           not casca[Z // 2, 90, 140],
           u"o centro do tronco entrou na pele")
    checar(u"ela esta contida no contorno externo", not (casca & ~ext).any())
    from scipy import ndimage
    esp = 2.0 * ndimage.distance_transform_edt(
        casca[Z // 2], sampling=SP[1:]).max()
    alvo = P.ESPESSURA_PELE_MM
    checar(u"a espessura fica perto dos %.1f mm da constante" % alvo,
           (alvo - 1.5) <= esp <= (alvo + 1.5), u"%.2f mm" % esp)


def teste_a_parede_desce_abaixo_do_pulmao_e_nao_se_sobrepoe():
    secao(u"a parede desce abaixo do pulmao, e os dois lados sao disjuntos")
    grade, hu, masks, ex = montar_fantoma()
    ext = P.contorno_externo(hu, grade)
    pa = P.parede_toracica(masks, ext, grade)
    checar(u"sairam os dois lados", sorted(pa) == ["ChestWall_L", "ChestWall_R"],
           str(sorted(pa)))
    if len(pa) != 2:
        return
    inter = G.volume_cm3(pa["ChestWall_L"] & pa["ChestWall_R"], grade)
    checar(u"os dois lados NAO se sobrepoem", inter < 0.05,
           u"%.2f cm3 em comum" % inter)

    z_par = min(faixa_z(m)[0] for m in pa.values())
    z_pul = faixa_z(ex["pulmoes"])[0]
    z_grad = faixa_z(ex["gradil"])[0]
    checar(u"ela desce ABAIXO do ultimo corte com pulmao",
           z_par < z_pul, u"parede ate z=%d, pulmao ate z=%d" % (z_par, z_pul))
    checar(u"  e nao passa da ultima costela",
           z_par >= z_grad - 1, u"parede z=%d, gradil z=%d" % (z_par, z_grad))

    for rotulo, alvo in ((u"pulmao", ex["pulmoes"]),
                         (u"mesa", ex["mesa"]),
                         (u"vertebra", masks["vertebrae_T8"]),
                         (u"esterno", masks["sternum"]),
                         (u"figado", masks["liver"]),
                         (u"rim", masks["kidney_right"])):
        pior = max(G.volume_cm3(m & alvo, grade) for m in pa.values())
        checar(u"nao invade %s" % rotulo, pior < 0.5, u"%.2f cm3" % pior)
    dentro = G.contrair(ext, P.ESPESSURA_PELE_MM, grade)
    pior = max(G.volume_cm3(m & ~dentro, grade) for m in pa.values())
    checar(u"nao passa da pele", pior < 0.5, u"%.2f cm3 fora" % pior)

    so_osso = dict((k, v) for k, v in masks.items() if not k.startswith("lung"))
    pa2 = P.parede_toracica(so_osso, ext, grade)
    checar(u"sem pulmao, a anatomia NAO identifica torax e a parede nao sai",
           pa2 == {}, str(sorted(pa2)))
    pa2 = P.parede_toracica(so_osso, ext, grade, torax=True)
    checar(u"  e, pedida pelo Estudo Torax, o gradil sozinho ainda a entrega",
           len(pa2) == 2, str(sorted(pa2)))

    checar(u"sem contorno externo ela nao sai (a face externa ficaria solta)",
           P.parede_toracica(masks, None, grade) == {})


def teste_o_contorno_externo_nao_pode_ser_gravado():
    secao(u"o contorno externo nao pode ser gravado")
    passam = ["Skin", "ChestWall_L", "ChestWall_R", "heart", "lung_left",
              "Lung_L_ai", "Skin_ai", "ChestWall_L_ai"]
    for n in passam:
        try:
            M.conferir_sem_body([n])
            checar(u"`%s` passa" % n, True)
        except Exception as e:
            checar(u"`%s` passa" % n, False, str(e)[:80])
    recusam = ["body", "BODY", "Body_ai", "body_trunc", "body_extremities",
               "external", "External_ai", "externo", "contorno_externo",
               "corpo", "patient", "v3d:body", "outercontour"]
    for n in recusam:
        try:
            M.conferir_sem_body([n])
            checar(u"`%s` e RECUSADO" % n, False, u"passou")
        except ValueError:
            checar(u"`%s` e recusado" % n, True)
    try:
        M.conferir_sem_body(["body"])
    except ValueError as e:
        txt = str(e)
        checar(u"a mensagem diz o que sai no lugar",
               "Skin" in txt and "ChestWall" in txt, txt[:90])
        checar(u"  e diz por que (dose)", "dose" in txt.lower(), txt[:90])

    fonte = io.open(_componentes.fonte("app/engine.py"), encoding="utf-8").read()
    corpo = fonte[fonte.index("def build_rtstruct("):]
    corpo = corpo[:corpo.index("\ndef ", 10)]
    checar(u"`build_rtstruct` CHAMA `conferir_sem_body`",
           "conferir_sem_body(" in corpo, u"a funcao existe e ninguem a chama")
    checar(u"  e chama antes de montar o arquivo",
           corpo.index("conferir_sem_body(") < corpo.index("RTStructBuilder"),
           u"recusar depois de montar nao evita nada")


def teste_a_traqueia_entregue_leva_a_margem_da_parede():
    secao(u"a traqueia entregue leva a margem")
    grade = G.Grade(SP)
    zz, yy, xx = np.ogrid[0:60, 0:80, 0:80]
    lumen = ((((yy - 40) * 0.98) ** 2 + ((xx - 40) * 0.98) ** 2 <= 81.0)
             & (zz >= 10) & (zz < 40))
    checar(u"a traqueia esta na tabela de margens do motor",
           "trachea" in M.MARGEM_OAR_MM)
    checar(u"  e a margem e a que ela mediu (2 mm)",
           abs(M.MARGEM_OAR_MM.get("trachea", 0) - 2.0) < 1e-9,
           str(M.MARGEM_OAR_MM.get("trachea")))
    m = {"trachea": lumen.copy()}
    n = M.aplicar_margens_de_oar(m, grade)
    checar(u"uma estrutura ganhou margem", n == 1, str(n))
    v0 = G.volume_cm3(lumen, grade)
    v1 = G.volume_cm3(m["trachea"], grade)
    checar(u"o volume cresceu", v1 > v0 * 1.2, u"%.1f -> %.1f cm3" % (v0, v1))
    checar(u"e o lumen continua dentro", not (lumen & ~m["trachea"]).any())
    fonte = io.open(_componentes.fonte("app/engine.py"), encoding="utf-8").read()
    checar(u"a margem da traqueia e aplicada no FULL (`preparar_full`), de "
           u"onde o entregue e selecionado",
           _aplica_a_traqueia(fonte, "preparar_full"),
           u"nenhuma chamada de `aplicar_margens_de_oar` com a traqueia")
    for isca, rot in ((u"def preparar_full(m, g):\n"
                       u"    aplicar_margens_de_oar(m, g, so=('aorta',))\n",
                       u"so com os vasos no `so`"),
                      (u"def preparar_full(m, g):\n    return m\n",
                       u"sem chamada nenhuma"),
                      (u"def outra(m, g):\n"
                       u"    aplicar_margens_de_oar(m, g)\n",
                       u"a chamada em outra funcao")):
        checar(u"  isca: %s e acusada" % rot,
               not _aplica_a_traqueia(isca, "preparar_full"))


def _aplica_a_traqueia(fonte, funcao):
    import ast
    for no in ast.walk(ast.parse(fonte)):
        if not (isinstance(no, ast.FunctionDef) and no.name == funcao):
            continue
        for c in ast.walk(no):
            if not isinstance(c, ast.Call):
                continue
            alvo = getattr(c.func, "id", None) or getattr(c.func, "attr", "")
            if alvo != "aplicar_margens_de_oar":
                continue
            so = [k for k in c.keywords if k.arg == "so"]
            if not so:
                return True
            v = so[0].value
            if isinstance(v, (ast.Tuple, ast.List, ast.Set)) and any(
                    isinstance(e, ast.Constant) and e.value == "trachea"
                    for e in v.elts):
                return True
    return False


def teste_os_conjuntos_de_estudo_perderam_o_RadAI():
    secao(u"os rotulos dos conjuntos vem de um lugar so (radai_sets)")
    fonte = io.open(_componentes.fonte("app/radai_output.py"),
                    encoding="utf-8").read()
    codigo = re.sub(r"(?m)^\s*#.*$", "", fonte)
    checar(u"o rotulo padrao vem de `radai_sets.rotulo_dicom`",
           "radai_sets.rotulo_dicom(cod)" in codigo, "")
    checar(u"  e nao sobrou `\"STUDY_\" + cod` no codigo",
           '"STUDY_" + cod' not in codigo, "")
    import radai_sets as CJ
    for c in CJ.CONJUNTOS:
        r = CJ.rotulo_dicom(c["cod"])
        checar(u"`%s` cabe no SH de 16" % r, len(r) <= 16,
               u"%d caracteres" % len(r))
    checar(u"o entregue e o RadAI_STUDY, e o FULL o RadAI_FULL",
           CJ.rotulo_dicom("oar") == "RadAI_STUDY"
           and CJ.rotulo_dicom("full") == "RadAI_FULL")


_EXT = {}


def _fantoma2():
    return montar_fantoma(escala=2)


def _externo2():
    if "e2" not in _EXT:
        g, hu, _m, _x = _fantoma2()
        _EXT["e2"] = P.contorno_externo(hu, g)
    return _EXT["e2"]


def _cols_esq(g, forma):
    xs = np.arange(forma[2]) * (g.spacing[2] / SP[2])
    return np.broadcast_to((xs >= 140)[None, None, :], forma)


def teste_o_gatilho_de_torax():
    secao(u"o gatilho de torax")
    g, hu, masks, ex = _fantoma2()
    tem, pq = P.torax_identificado(masks, g)
    checar(u"o fantoma de torax e identificado", tem, pq)
    checar(u"  e o laudo diz os tres marcos",
           all(w in pq for w in (u"pulmao", u"clavicula", u"escapula")), pq)
    sem_cla = dict((k, v) for k, v in masks.items()
                   if not k.startswith("clavicula"))
    tem, pq = P.torax_identificado(sem_cla, g)
    checar(u"sem clavicula NAO e torax, e o motivo diz", not tem
           and u"clavicula" in pq, pq)
    sem_esc = dict((k, v) for k, v in masks.items()
                   if not k.startswith("scapula"))
    tem, pq = P.torax_identificado(sem_esc, g)
    checar(u"sem escapula NAO e torax, e o motivo diz", not tem
           and u"escapula" in pq, pq)
    ponta = dict(masks)
    for k in ("lung_left", "lung_right"):
        m = np.zeros_like(masks[k])
        m[30:33, 30:33, 30:33] = True
        ponta[k] = m
    tem, pq = P.torax_identificado(ponta, g)
    checar(u"com uma ponta de pulmao (abaixo do piso) NAO e torax",
           not tem and u"piso" in pq, pq)
    tem, pq = P.torax_identificado(masks, None)
    checar(u"sem grade, nao (nao ha cm3 sem espacamento)", not tem, pq)
    amig = dict((k, v) for k, v in masks.items()
                if not k.startswith(("clavicula", "scapula")))
    cru = dict((k, v) for k, v in masks.items()
               if k.startswith(("clavicula", "scapula")))
    tem, pq = P.torax_identificado(amig, g, cru=cru)
    checar(u"clavicula e escapula lidas do `cru` quando o processado nao as tem",
           tem, pq)

    ext = _externo2()
    linhas = []
    pa = P.parede_toracica(sem_cla, ext, g, log=linhas.append)
    checar(u"a parede NAO sai quando o torax nao e identificado", pa == {},
           str(sorted(pa)))
    checar(u"  e o log diz por que (a clavicula)",
           any(l.startswith(u"parede toracica: nao sai") and u"clavicula" in l
               for l in linhas), str(linhas)[:160])
    pa = P.parede_toracica(sem_cla, ext, g, torax=True)
    checar(u"o Estudo Torax pedido (`torax=True`) dispensa a anatomia",
           sorted(pa) == ["ChestWall_L", "ChestWall_R"], str(sorted(pa)))
    linhas = []
    pa = P.parede_toracica(masks, ext, g, torax=False, log=linhas.append)
    checar(u"`torax=False` nao entrega, mesmo com torax no campo",
           pa == {} and any(u"nao foi pedida" in l for l in linhas),
           str(linhas)[:120])
    pa = P.parede_toracica(amig, ext, g, cru=cru)
    checar(u"com o `cru`, o dicionario amigavel tambem entrega a parede",
           sorted(pa) == ["ChestWall_L", "ChestWall_R"], str(sorted(pa)))
    if pa:
        clav = cru["clavicula_left"] | cru["clavicula_right"]
        pior = max(int((m & clav).sum()) for m in pa.values())
        checar(u"  e recorta a clavicula que so existe no `cru`", pior == 0,
               u"%d voxels de clavicula na parede" % pior)


def teste_sem_cavidade_a_parede_nao_sai():
    secao(u"sem a cavidade abdominal a parede nao sai")
    g, hu, masks, ex = _fantoma2()
    ext = _externo2()
    sem = dict((k, v) for k, v in masks.items() if k != "abdominal_cavity")
    linhas = []
    pa = P.parede_toracica(sem, ext, g, torax=True, log=linhas.append)
    checar(u"sem `abdominal_cavity` nao sai, nem pedida", pa == {},
           str(sorted(pa)))
    checar(u"  e o log nomeia a task que falta",
           any(u"trunk_cavities" in l and u"nao sai" in l for l in linhas),
           str(linhas)[:160])
    checar(u"  e nenhuma linha manda escolher um modo que nao existe mais",
           not any(u"modo Completo" in l for l in linhas), str(linhas)[:160])
    troca = dict(sem)
    troca["bag_bowel"] = masks["abdominal_cavity"]
    checar(u"uma `bag_bowel` no lugar da cavidade crua nao conta",
           P.parede_toracica(troca, ext, g, torax=True) == {})
    cav = masks["abdominal_cavity"]
    alcance = G.expandir(ex["gradil"], P.MARGEM_PAREDE_MM, g) & cav
    checar(u"(fantoma) a expansao do gradil alcanca a cavidade",
           alcance.sum() > 0, u"%d voxels" % int(alcance.sum()))
    pa = P.parede_toracica(masks, ext, g)
    pior = max([int((m & cav).sum()) for m in pa.values()] or [-1])
    checar(u"com a cavidade, a parede nao entra nela", pior == 0,
           u"%d voxels" % pior)


def teste_a_parede_recorta_os_nomes_que_existem():
    secao(u"a parede recorta os nomes que existem, nos dois vocabularios")
    g, hu, masks, ex = _fantoma2()
    ext = _externo2()
    linhas = []
    pa = P.parede_toracica(masks, ext, g, log=linhas.append)
    checar(u"sairam os dois lados", len(pa) == 2, str(sorted(pa)))
    alvos = ((u"clavicula", ("clavicula_left", "clavicula_right")),
             (u"escapula", ("scapula_left", "scapula_right")),
             (u"coracao", ("heart",)), (u"pericardio", ("pericardium",)),
             (u"mediastino", ("mediastinum",)),
             (u"intestino delgado", ("small_bowel",)))
    for rot, chaves in alvos:
        alvo = np.zeros_like(masks["heart"])
        for k in chaves:
            alvo = alvo | masks[k]
        pior = max([int((m & alvo).sum()) for m in pa.values()] or [-1])
        checar(u"nao invade %s" % rot, pior == 0, u"%d voxels" % pior)
    checar(u"o log final comeca por «parede toracica:» (o registro de casos "
           u"o reconhece)",
           any(l.startswith(u"parede toracica: ChestWall_") for l in linhas),
           str(linhas)[-1:])
    velho = P.CROPS_DA_PAREDE
    try:
        P.CROPS_DA_PAREDE = tuple(c for c in velho
                                  if c not in ("pericardium", "mediastinum",
                                               "small_intestine"))
        pv = P.parede_toracica(masks, ext, g)
    finally:
        P.CROPS_DA_PAREDE = velho
    inv = sum(int((m & (masks["pericardium"] | masks["mediastinum"])).sum())
              for m in pv.values())
    checar(u"  isca: com a lista da v8.1 a parede INVADE pericardio e "
           u"mediastino", inv > 0, u"%d voxels" % inv)

    import radai_constructs as C
    import radai_names
    amig = dict(masks)
    amig["small_intestine"] = amig.pop("small_bowel")
    cm = radai_names.CHAVE_DO_CORACAO_DO_MODELO
    amig[cm] = amig.pop("heart")
    amig[C.CHAVE_CORACAO_AI] = G.expandir(masks["heart"], 4.0, g)
    amig["trunk_cavities:Pericardium"] = amig.pop("pericardium")
    checar(u"(fantoma) as duas chaves de coracao sao diferentes e as duas "
           u"estao no dicionario", cm != C.CHAVE_CORACAO_AI
           and cm in amig and C.CHAVE_CORACAO_AI in amig)
    viz, faltaram = P.vizinhos_da_parede(amig)
    for rot, chave in ((u"`small_intestine`", "small_intestine"),
                       (u"o coracao do modelo (`%s`)" % cm, cm),
                       (u"a chave do Heart_ai (`%s`)" % C.CHAVE_CORACAO_AI,
                        C.CHAVE_CORACAO_AI),
                       (u"`trunk_cavities:Pericardium`",
                        "trunk_cavities:Pericardium")):
        dentro = viz is not None and not (amig[chave] & ~viz).any()
        checar(u"%s entra no recorte" % rot, dentro)
    checar(u"  e nenhum dos seis grupos e dado como ausente", faltaram == [],
           str(faltaram))
    _v, faltaram = P.vizinhos_da_parede({"bowel_small": masks["small_bowel"],
                                         "heart": masks["heart"]})
    checar(u"nome que a lista nao conhece NAO casa, e o log o nomeia",
           u"intestino" in faltaram and u"coracao" not in faltaram,
           str(faltaram))
    pa2 = P.parede_toracica(amig, ext, g)
    pior = max([int((m & (masks["heart"] | masks["pericardium"]
                          | amig[C.CHAVE_CORACAO_AI])).sum())
                for m in pa2.values()] or [-1])
    checar(u"com os nomes amigaveis a parede tambem nao invade coracao (o do "
           u"modelo nem o Heart_ai) nem pericardio",
           len(pa2) == 2 and pior == 0, u"%d voxels" % pior)


def teste_a_cartilagem_esta_na_base():
    secao(u"a cartilagem costal entra na base, partida pela linha media")
    g, hu, masks, ex = _fantoma2()
    ext = _externo2()
    orig = P.maior_contorno_por_corte
    try:
        P.maior_contorno_por_corte = (lambda mm, gr, **kw: (np.asarray(mm, bool)
                                                      .copy(), 0))
        pa = P.parede_toracica(masks, ext, g)
    finally:
        P.maior_contorno_por_corte = orig
    if len(pa) != 2:
        checar(u"sairam os dois lados", False, str(sorted(pa)))
        return
    cart = masks["costal_cartilages"]
    esq = _cols_esq(g, cart.shape)
    ce, cd = cart & esq, cart & ~esq
    f_e = float((pa["ChestWall_L"] & ce).sum()) / max(1, ce.sum())
    f_d = float((pa["ChestWall_R"] & cd).sum()) / max(1, cd.sum())
    checar(u"a cartilagem esquerda esta na parede esquerda", f_e >= 0.8,
           u"%.0f%%" % (100 * f_e))
    checar(u"a cartilagem direita esta na parede direita", f_d >= 0.8,
           u"%.0f%%" % (100 * f_d))
    cruz = int((pa["ChestWall_L"] & cd).sum() + (pa["ChestWall_R"] & ce).sum())
    checar(u"  e nenhuma metade vai para o lado errado", cruz == 0,
           u"%d voxels" % cruz)
    sem = dict((k, v) for k, v in masks.items() if k != "costal_cartilages")
    try:
        P.maior_contorno_por_corte = (lambda mm, gr, **kw: (np.asarray(mm, bool)
                                                      .copy(), 0))
        ps = P.parede_toracica(sem, ext, g)
    finally:
        P.maior_contorno_por_corte = orig
    f_s = (float((ps.get("ChestWall_L", np.zeros_like(cart)) & ce).sum())
           / max(1, ce.sum()))
    checar(u"  isca: sem a cartilagem na base, a parede cobre MENOS dela",
           f_s < f_e - 0.1, u"%.0f%% contra %.0f%%" % (100 * f_s, 100 * f_e))


def _violacoes_do_plano(parede, esterno, lado, alcance_vox):
    s = esterno
    zs = np.where(s.any(axis=(1, 2)))[0]
    n = 0
    for z in range(parede.shape[0]):
        if not parede[z].any():
            continue
        zz = zs[int(np.argmin(np.abs(zs - z)))]
        cols = np.where(s[zz].any(axis=0))[0]
        rows = np.where(s[zz].any(axis=1))[0]
        ate = int(rows.max()) + alcance_vox + 1
        if lado == "esq":
            n += int(parede[z][:ate, :int(cols.max()) + 1].sum())
        else:
            n += int(parede[z][:ate, int(cols.min()):].sum())
    return n


def teste_o_plano_medial_na_borda_do_esterno():
    secao(u"o plano medial explicito na borda lateral do esterno")
    g, hu, masks, ex = _fantoma2()
    ext = _externo2()
    est = masks["sternum"]
    alc = int(round(P.MARGEM_PAREDE_MM / g.spacing[1]))
    pa = P.parede_toracica(masks, ext, g)
    for nome, lado in (("ChestWall_L", "esq"), ("ChestWall_R", "dir")):
        n = _violacoes_do_plano(pa.get(nome, np.zeros_like(est)), est, lado,
                                alc)
        checar(u"`%s` nao passa da borda lateral do esterno" % nome, n == 0,
               u"%d voxels mediais" % n)
    orig = P.lateral_ao_esterno
    try:
        P.lateral_ao_esterno = (lambda forma, *a, **k:
                                np.asarray(forma, dtype=bool).copy())
        px = P.parede_toracica(masks, ext, g)
    finally:
        P.lateral_ao_esterno = orig
    n = sum(_violacoes_do_plano(px.get(nm, np.zeros_like(est)), est, ld, alc)
            for nm, ld in (("ChestWall_L", "esq"), ("ChestWall_R", "dir")))
    checar(u"  isca: sem o plano, a faixa medial aparece (e a parede CHAMA a "
           u"funcao)", n > 0, u"%d voxels" % n)

    gg = G.Grade((1.0, 1.0, 1.0))
    forma = np.ones((10, 20, 30), bool)
    esterno = np.zeros_like(forma)
    esterno[3:7, 2:5, 12:17] = True
    copia = forma.copy()
    r = P.lateral_ao_esterno(forma, esterno, gg, "esq")
    checar(u"esquerda: fica so o que esta alem da ultima coluna do esterno",
           r[:, :, :17].sum() == 0 and r[:, :, 17:].all())
    checar(u"  e os cortes sem esterno herdam a borda do mais proximo",
           not r[0, :, 16].any() and not r[9, :, 16].any())
    r = P.lateral_ao_esterno(forma, esterno, gg, "esq", offset_mm=10.0)
    checar(u"os 10 mm da mama deslocam a borda 10 voxels para fora",
           r[:, :, :27].sum() == 0 and r[:, :, 27:].all())
    r = P.lateral_ao_esterno(forma, esterno, gg, "dir")
    checar(u"direita: fica o que esta aquem da primeira coluna",
           r[:, :, 12:].sum() == 0 and r[:, :, :12].all())
    r = P.lateral_ao_esterno(forma, esterno, gg, "esq",
                             alcance_posterior_mm=3.0)
    checar(u"com alcance, atras de (face posterior + alcance) nada e cortado",
           r[:, 8:, :].all() and r[:, :8, :17].sum() == 0)
    checar(u"a entrada nao foi tocada", np.array_equal(forma, copia))
    r = P.lateral_ao_esterno(forma, np.zeros_like(forma), gg, "esq")
    checar(u"sem esterno, a forma volta como veio (em copia)",
           r.all() and r is not forma)
    gl = G.Grade((1.0, 1.0, 1.0), ("sup", "post", "dir"))
    fl = np.ascontiguousarray(forma[:, :, ::-1])
    el = np.ascontiguousarray(esterno[:, :, ::-1])
    rc = P.lateral_ao_esterno(forma, esterno, gg, "esq")
    rl = P.lateral_ao_esterno(fl, el, gl, "esq")
    checar(u"serie espelhada: a borda ESQUERDA do paciente continua a esquerda",
           np.array_equal(rl[:, :, ::-1], rc))


def teste_o_autoctone_fica():
    secao(u"o autoctone fica dentro da parede")
    g, hu, masks, ex = _fantoma2()
    ext = _externo2()
    auto = masks["autochthon_left"] | masks["autochthon_right"]
    antes = dict((k, hash(v.tobytes())) for k, v in masks.items())
    ext_antes = hash(ext.tobytes())
    pa = P.parede_toracica(masks, ext, g)
    checar(u"a parede nao muta nenhuma mascara de entrada nem o externo",
           antes == dict((k, hash(v.tobytes())) for k, v in masks.items())
           and ext_antes == hash(ext.tobytes()))
    v = sum(G.volume_cm3(m & auto, g) for m in pa.values())
    checar(u"a parede contem autoctone", v > 1.0, u"%.1f cm3" % v)
    velho = P.CROPS_DA_PAREDE
    try:
        P.CROPS_DA_PAREDE = velho + ("autochthon",)
        pv = P.parede_toracica(masks, ext, g)
    finally:
        P.CROPS_DA_PAREDE = velho
    vv = sum(G.volume_cm3(m & auto, g) for m in pv.values())
    checar(u"  isca: com o autoctone na lista de recortes, ele sai", vv == 0.0,
           u"%.1f cm3" % vv)
    import ast
    arv = ast.parse(io.open(_componentes.fonte("app/radai_skin.py"),
                            encoding="utf-8").read())
    lista = None
    for no in arv.body:
        if (isinstance(no, ast.Assign) and len(no.targets) == 1
                and getattr(no.targets[0], "id", "") == "CROPS_DA_PAREDE"):
            lista = [e.value for e in no.value.elts
                     if isinstance(e, ast.Constant)]
    checar(u"o literal `CROPS_DA_PAREDE` existe", lista is not None)
    checar(u"  e nao tem nada de `FICAM_NA_PAREDE`",
           lista is not None and not any(
               c.startswith(f) or f.startswith(c)
               for c in lista for f in P.FICAM_NA_PAREDE), str(lista))


def teste_a_base_e_lida_e_a_receita_esta_ligada():
    secao(u"a receita esta ligada na funcao que executa")
    listas = (P.PULMAO_ESQ + P.PULMAO_DIR + P.COSTELAS_ESQ + P.COSTELAS_DIR
              + P.CARTILAGENS + P.CAVIDADE_TORACICA)
    checar(u"todo nome de `BASE_DA_PAREDE` esta numa lista por lado",
           all(n in listas for n in P.BASE_DA_PAREDE)
           and "costal_cartilages" in P.BASE_DA_PAREDE
           and "thoracic_cavity" in P.BASE_DA_PAREDE)
    import ast
    arv = ast.parse(io.open(_componentes.fonte("app/radai_skin.py"),
                            encoding="utf-8").read())
    fn = [n for n in arv.body if isinstance(n, ast.FunctionDef)
          and n.name == "parede_toracica"][0]
    nomes = set(getattr(n, "id", None) for n in ast.walk(fn))
    for alvo in ("PULMAO_ESQ", "PULMAO_DIR", "COSTELAS_ESQ", "COSTELAS_DIR",
                 "CARTILAGENS", "CAVIDADES_PROIBIDAS", "torax_identificado",
                 "lateral_ao_esterno", "vizinhos_da_parede",
                 "separar_por_lado", "CAVIDADE_TORACICA", "cavidade_por_lado",
                 "_cavidade_pleural", "maior_contorno_por_corte",
                 "SUAVIZACAO_PAREDE_MM"):
        checar(u"`parede_toracica` usa `%s`" % alvo, alvo in nomes)


def teste_a_parede_nao_depende_da_orientacao():
    secao(u"a parede nao depende da orientacao da serie")
    g, hu, masks, ex = _fantoma2()
    ext = _externo2()
    pa = P.parede_toracica(masks, ext, g)
    for rot, sentido, fatia in (
            (u"feet-first", ("inf", "post", "esq"),
             (slice(None, None, -1), slice(None), slice(None))),
            (u"espelhada (x cresce para a direita)", ("sup", "post", "dir"),
             (slice(None), slice(None), slice(None, None, -1)))):
        gf = G.Grade(g.spacing, sentido)
        mf = dict((k, np.ascontiguousarray(v[fatia]))
                  for k, v in masks.items())
        pf = P.parede_toracica(mf, np.ascontiguousarray(ext[fatia]), gf)
        for nome in ("ChestWall_L", "ChestWall_R"):
            if nome not in pa or nome not in pf:
                checar(u"%s: `%s` saiu" % (rot, nome), False)
                continue
            d = G.dsc(pa[nome], pf[nome][fatia])
            checar(u"%s: `%s` igual a da serie canonica" % (rot, nome),
                   d >= 0.995, u"DSC %.4f" % d)


_DERRAME = {}
APICE_Z = 100


def montar_fantoma_com_derrame():
    if "d" in _DERRAME:
        g, hu, masks, ex = _DERRAME["d"]
        return g, hu, dict(masks), dict(ex)
    g, hu0, masks, ex = montar_fantoma(escala=2)
    hu = np.array(hu0, copy=True)
    forma = hu.shape
    zz, yy, xx = np.mgrid[0:forma[0], 0:forma[1], 0:forma[2]]
    zf, yf, xf = zz * 2, yy * 2, xx * 2
    my = (yf - 90.0) * SP[1]
    mx = (xf - 140.0) * SP[2]
    tronco = ex["tronco"]
    r = (mx / 132.0) ** 2 + (my / 82.0) ** 2
    apice = zf < APICE_Z
    pul_d = masks["lung_right"] & apice
    pul_e = masks["lung_left"] & apice
    hu[(masks["lung_right"] | masks["lung_left"]) & ~apice] = 40.0
    vert = masks["vertebrae_T8"]
    espaco = ((((zf - 85) * SP[0]) / 62.0) ** 2
              + ((my - 4.0) / 62.0) ** 2 + ((mx + 62.0) / 48.0) ** 2 <= 1.0)
    derrame = (espaco & (r < 0.78) & tronco & ~pul_d & ~vert & (my > 20.0)
               & (mx < -20.0) & apice)
    hu[derrame] = 15.0
    traqueia = ((np.abs(mx) <= 9.0) & (my >= -45.0) & (my <= -27.0)
                & tronco & (zf >= 60))
    hu[traqueia] = -900.0
    tubo = ((np.abs(mx) <= 22.0) & (my >= -55.0) & (my <= -17.0) & tronco
            & ~traqueia & (zf >= 96))
    masks["lung_right"] = pul_d
    masks["lung_left"] = pul_e
    masks["trachea"] = traqueia
    masks["mediastinum"] = masks["mediastinum"] & ~tubo & ~traqueia
    masks["thoracic_cavity"] = pul_d | pul_e | derrame | tubo
    ex = dict(ex)
    ex.update({"derrame": derrame, "tubo": tubo, "pulmoes": pul_d | pul_e,
               "zf": zf, "mx": mx, "my": my})
    _DERRAME["d"] = (g, hu, masks, ex)
    return g, hu, dict(masks), dict(ex)


def _externo_derrame():
    if "e" not in _DERRAME:
        g, hu, _m, _x = montar_fantoma_com_derrame()
        _DERRAME["e"] = P.contorno_externo(hu, g)
    return _DERRAME["e"]


def _componentes_por_corte(m, g):
    from scipy import ndimage
    eixo = g.eixo_sinal("sup")[0]
    v = np.moveaxis(np.asarray(m, bool), eixo, 0)
    pior = 0
    for k in range(v.shape[0]):
        if v[k].any():
            pior = max(pior, int(ndimage.label(v[k])[1]))
    return pior


def _pedacos_por_regiao(m, pulmao, gradil, g):
    from scipy import ndimage
    eixo, sinal = g.eixo_sinal("sup")
    v = np.moveaxis(np.asarray(m, bool), eixo, 0)
    vp = np.moveaxis(np.asarray(pulmao, bool), eixo, 0)
    vg = np.moveaxis(np.asarray(gradil, bool), eixo, 0)
    kp = np.where(vp.any(axis=(1, 2)))[0]

    def _e_abaixo(k):
        return bool(len(kp)) and ((k < kp.min()) if sinal > 0
                                  else (k > kp.max()))
    ab = np.array([_e_abaixo(k) for k in range(v.shape[0])])
    bloco = v & ab[:, None, None]
    rot3, _n3 = ndimage.label(bloco)
    com_cost = set(int(x) for x in np.unique(rot3[bloco & vg]) if x > 0)
    com, abaixo, sem = 0, 0, 0
    for k in range(v.shape[0]):
        if not v[k].any():
            continue
        rot, n = ndimage.label(v[k])
        if ab[k]:
            abaixo = max(abaixo, n)
            sem += sum(1 for j in range(1, n + 1)
                       if not com_cost.intersection(
                           int(x) for x in np.unique(rot3[k][rot == j])))
        else:
            com = max(com, n)
    return com, abaixo, sem


def teste_a_parede_nao_engole_o_derrame():
    secao(u"v8.3: a parede nao engole o derrame (a cavidade inteira sai)")
    g, hu, masks, ex = montar_fantoma_com_derrame()
    ext = _externo_derrame()
    der = ex["derrame"]
    checar(u"(fantoma) ha derrame, e ele esta dentro da cavidade",
           der.sum() > 200 and not (der & ~masks["thoracic_cavity"]).any(),
           u"%d voxels" % int(der.sum()))
    linhas = []
    pa = P.parede_toracica(masks, ext, g, log=linhas.append)
    checar(u"sairam os dois lados", sorted(pa) == ["ChestWall_L", "ChestWall_R"],
           str(sorted(pa)))
    if len(pa) != 2:
        return
    dentro = sum(int((m & der).sum()) for m in pa.values())
    checar(u"a parede NAO contem voxel de derrame", dentro == 0,
           u"%d voxels" % dentro)
    cav = sum(int((m & masks["thoracic_cavity"]).sum()) for m in pa.values())
    checar(u"  nem de cavidade toracica nenhuma (pulmao, derrame, tubo)",
           cav == 0, u"%d voxels" % cav)
    viz, _f = P.vizinhos_da_parede(masks)
    anel = (G.expandir(der, 4.0, g) & ~masks["thoracic_cavity"]
            & G.contrair(ext, P.ESPESSURA_PELE_MM, g) & ~viz
            & (ex["my"] > 45.0))
    cob = float((pa["ChestWall_R"] & anel).sum()) / max(1, int(anel.sum()))
    checar(u"a parede direita encosta no derrame por fora (>= 80%% do anel "
           u"de 4 mm)", cob >= 0.8, u"%.0f%% de %d voxels"
           % (100 * cob, int(anel.sum())))
    checar(u"o log diz que a base foi a cavidade toracica",
           any(u"cavidade toracica" in l and u"base" in l for l in linhas),
           str([l for l in linhas if l.startswith(u"parede")])[:200])
    sem = dict((k, v) for k, v in masks.items() if k != "thoracic_cavity")
    li = []
    pi = P.parede_toracica(sem, ext, g, log=li.append)
    engole = sum(int((m & der).sum()) for m in pi.values())
    checar(u"  isca: sem a cavidade (o recuo, a receita da v8.2) a parede "
           u"ENGOLE o derrame", engole > 0, u"%d voxels" % engole)
    checar(u"  e o recuo diz no log que a base foi pulmao + costelas",
           any(u"sem a cavidade toracica" in l for l in li),
           str([l for l in li if l.startswith(u"parede")])[:200])


def teste_o_derrame_da_task_entra_na_cavidade_da_parede():
    secao(u"v8.4: o derrame da task entra na cavidade da parede")
    g, hu, masks, ex = montar_fantoma_com_derrame()
    ext = _externo_derrame()
    der = ex["derrame"]
    sem_cav = dict((k, v) for k, v in masks.items() if k != "thoracic_cavity")
    com = dict(sem_cav, pleural_effusion_right=der)
    linhas = []
    pa = P.parede_toracica(com, ext, g, log=linhas.append)
    dentro = sum(int((m & der).sum()) for m in pa.values())
    checar(u"sem a cavidade, o derrame da task sai da parede", bool(pa)
           and dentro == 0, u"%d voxels, %s" % (dentro, sorted(pa)))
    checar(u"  e o log diz que o derrame entrou na cavidade",
           any(u"derrame pleural" in l for l in linhas),
           str([l for l in linhas if l.startswith(u"parede")])[:200])
    pi = P.parede_toracica(sem_cav, ext, g)
    engole = sum(int((m & der).sum()) for m in pi.values())
    checar(u"  isca: sem o derrame da task, a parede engole o liquido",
           engole > 0, u"%d voxels" % engole)
    com2 = dict(masks, pleural_effusion=der)
    pc = P.parede_toracica(com2, ext, g)
    checar(u"  com a cavidade e o derrame juntos, nada muda de lado",
           sorted(pc) == ["ChestWall_L", "ChestWall_R"]
           and sum(int((m & der).sum()) for m in pc.values()) == 0)


def teste_a_cavidade_se_divide_pelo_pulmao_mais_proximo():
    secao(u"v8.3: a cavidade se divide pelo pulmao mais proximo")
    g, hu, masks, ex = montar_fantoma_com_derrame()
    linha = P.linha_media_por_corte(masks, g)
    esq, dir_ = P.cavidade_por_lado(masks["thoracic_cavity"],
                                    masks["lung_left"], masks["lung_right"],
                                    g, linha)
    der = ex["derrame"]
    checar(u"o derrame inteiro vai para a DIREITA", not (der & ~dir_).any(),
           u"%d voxels fora" % int((der & ~dir_).sum()))
    checar(u"cada pulmao fica com o seu lado",
           not (masks["lung_left"] & ~esq).any()
           and not (masks["lung_right"] & ~dir_).any())
    checar(u"nenhum voxel vai para os dois lados, nenhum se perde",
           not (esq & dir_).any()
           and np.array_equal(esq | dir_, masks["thoracic_cavity"]))

    gg = G.Grade((1.0, 1.0, 1.0))
    forma = (10, 40, 60)
    pd_ = np.zeros(forma, bool)
    pe = np.zeros(forma, bool)
    pd_[0:6, 10:20, 18:33] = True
    pe[0:6, 10:20, 36:50] = True
    der2 = np.zeros(forma, bool)
    der2[0:6, 20:24, 30:34] = True
    baixo_d = np.zeros(forma, bool)
    baixo_d[7:10, 12:18, 20:27] = True
    baixo_e = np.zeros(forma, bool)
    baixo_e[7:10, 12:18, 34:41] = True
    cav2 = pd_ | pe | der2 | baixo_d | baixo_e
    linha2 = np.full(forma[0], 30.0)
    e2, d2 = P.cavidade_por_lado(cav2, pe, pd_, gg, linha2)
    checar(u"o derrame que passou da linha media fica com o pulmao DIREITO",
           not (der2 & ~d2).any(), u"%d voxels no lado errado"
           % int((der2 & ~d2).sum()))
    checar(u"sem pulmao no corte, a linha media decide",
           not (baixo_d & ~d2).any() and not (baixo_e & ~e2).any())
    ei, di = P.separar_por_lado(cav2, gg, linha2)
    checar(u"  isca: so pela linha media, o derrame iria para a ESQUERDA",
           (der2 & ei).any(), u"%d voxels" % int((der2 & ei).sum()))
    checar(u"  e a entrada nao foi tocada",
           int(cav2.sum()) == int((pd_ | pe | der2 | baixo_d | baixo_e).sum()))


def teste_a_cavidade_do_pescoco_nao_e_base():
    secao(u"v8.3: o tubo de cavidade do pescoco nao vira parede")
    g, hu, masks, ex = montar_fantoma_com_derrame()
    ext = _externo_derrame()
    traq = masks["trachea"]
    tubo = ex["tubo"]
    perto = (G.expandir(tubo, 12.0, g) & ~tubo & ~traq
             & (ex["zf"] >= APICE_Z))
    checar(u"(fantoma) o tubo sobe acima do apice, em volta da traqueia",
           bool((tubo & (ex["zf"] >= APICE_Z)).any()))
    pa = P.parede_toracica(masks, ext, g)
    n = sum(int((m & perto).sum()) for m in pa.values())
    sem = dict((k, v) for k, v in masks.items() if k != "thoracic_cavity")
    ps = P.parede_toracica(sem, ext, g)
    ns = sum(int((m & perto).sum()) for m in ps.values())
    checar(u"a cavidade nao acrescenta parede no anel de 12 mm em volta do "
           u"tubo acima do apice (nem um voxel alem do recuo)", n <= ns,
           u"%d voxels, contra %d sem a cavidade" % (n, ns))
    orig = P._cavidade_pleural
    try:
        P._cavidade_pleural = lambda cav, *a, **k: np.asarray(cav, bool)
        pi = P.parede_toracica(masks, ext, g)
    finally:
        P._cavidade_pleural = orig
    ni = sum(int((m & perto).sum()) for m in pi.values())
    checar(u"  isca: com a cavidade inteira na base, a parede sobe em volta "
           u"da traqueia", ni > ns, u"%d voxels, contra %d sem a cavidade"
           % (ni, ns))


def teste_um_contorno_por_corte():
    secao(u"v8.3: um contorno por corte, o maior")
    gg = G.Grade((2.0, 1.0, 1.0))
    m = np.zeros((6, 30, 30), bool)
    m[1, 2:12, 2:12] = True
    m[1, 20:24, 20:24] = True
    m[3, 5:9, 5:9] = True
    m[4, 2:6, 2:6] = True
    m[4, 6:10, 6:10] = True
    m[5, 2:12, 2:12] = True
    m[5, 5:9, 5:9] = False
    copia = m.copy()
    r, tirou = P.maior_contorno_por_corte(m, gg)
    checar(u"o corte com duas ilhas fica com a maior",
           r[1].sum() == 100 and not r[1, 20:24, 20:24].any())
    checar(u"  o corte com um pedaco so fica como estava",
           np.array_equal(r[3], m[3]))
    checar(u"  a quina nao liga: dois pedacos (4-conexo), fica um",
           int(r[4].sum()) == 16, str(int(r[4].sum())))
    from scipy import ndimage as _nd
    checar(u"  o anel perde o furo (aberto por uma fenda ate fora), e nao e "
           u"preenchido", np.array_equal(_nd.binary_fill_holes(r[5]), r[5])
           and not r[5, 5:9, 5:9].any() and int(_nd.label(r[5])[1]) == 1,
           u"%d voxels" % int(r[5].sum()))
    checar(u"  a fenda e a mais curta: 3 voxels do anel de 84",
           int(m[5].sum()) - int(r[5].sum()) == 3,
           str(int(m[5].sum()) - int(r[5].sum())))
    checar(u"  devolve os voxels tirados, e nunca acrescenta",
           tirou == 35 and not (r & ~m).any(), str(tirou))
    checar(u"  e a entrada nao foi tocada", np.array_equal(m, copia))
    orig_f = P._abrir_furos
    try:
        P._abrir_furos = lambda c: (np.asarray(c, bool).copy(), 0)
        ri, _t = P.maior_contorno_por_corte(m, gg)
    finally:
        P._abrir_furos = orig_f
    checar(u"  isca: sem abrir o furo, o anel continua com furo (dois "
           u"contornos no RTSTRUCT)",
           not np.array_equal(_nd.binary_fill_holes(ri[5]), ri[5]))

    ram = np.zeros((10, 30, 40), bool)
    ram[6:10, 5:15, 2:38] = True
    for k in range(0, 6):
        ram[k, 5:15, 2:12] = True
        if k % 2 == 0:
            ram[k, 5:15, 26:37] = True
        else:
            ram[k, 5:15, 30:37] = True
    rr, _t = P.maior_contorno_por_corte(ram, gg)
    checar(u"dois ramos: a parede nao se parte em 3D (um pedaco so)",
           int(_nd.label(rr)[1]) == 1, str(int(_nd.label(rr)[1])))
    checar(u"  e o ramo que fica e o de maior area SOMADA (A), em todos os "
           u"cortes -- tambem nos pares, onde B e maior no corte",
           all(rr[k, 5:15, 2:12].all() and not rr[k, :, 20:].any()
               for k in range(0, 6)))
    checar(u"  e ainda um pedaco por corte",
           max(int(_nd.label(rr[k])[1]) for k in range(10)) == 1)
    velha = np.zeros_like(ram)
    for k in range(10):
        velha[k] = P._maior_pedaco(ram[k])
    checar(u"  isca: o maior de cada corte sozinho parte a parede em 3D",
           int(_nd.label(velha)[1]) > 1, str(int(_nd.label(velha)[1])))
    gt = G.Grade((1.0, 1.0, 2.0), ("post", "esq", "sup"))
    mt = np.ascontiguousarray(np.moveaxis(m, 0, 2))
    rt, _t = P.maior_contorno_por_corte(mt, gt)
    checar(u"com o eixo cranio-caudal em outra posicao, o mesmo resultado",
           np.array_equal(np.moveaxis(rt, 2, 0), r))

    dois = np.zeros((10, 30, 50), bool)
    dois[6:10, 5:15, 2:48] = True
    dois[7, 5:15, 22:24] = False
    for k in range(0, 6):
        dois[k, 5:15, 2:14] = True
        cb = slice(31, 43) if k else slice(32, 43)
        dois[k, 5:15, cb] = True
        dois[k, 20:24, 20:24] = True
    dois[0, 5:15, 16:29] = True
    pul = np.zeros_like(dois)
    pul[6:10, 18:28, 10:30] = True
    cost = np.zeros_like(dois)
    cost[:, 8:10, 4:6] = True
    cost[:, 8:10, 36:38] = True
    cost[3, 8:10, 36:38] = False
    laudo = {}
    rd, _t = P.maior_contorno_por_corte(dois, gg, pulmao=pul, costelas=cost,
                                        laudo=laudo)
    ok_ab = all(rd[k, 5:15, 2:14].all() and rd[k, 5:15, 36:38].all()
                for k in range(0, 6))
    checar(u"abaixo da base do pulmao, os DOIS ramos com costela ficam",
           ok_ab)
    checar(u"  inclusive no espaco intercostal (corte 3: o ramo B nao tem "
           u"costela NESTE corte, e o ramo em 3D tem)",
           rd[3, 5:15, 31:43].all() and not cost[3, 5:15, 31:43].any())
    checar(u"  e o pedaco sem costela sai (C, e D no corte 0, que e maior "
           u"que o ramo B dali)",
           not any(rd[k, 20:24, 20:24].any() for k in range(0, 6))
           and not rd[0, 5:15, 16:29].any())
    checar(u"  no maximo dois pedacos por corte abaixo, e UM onde ha pulmao",
           max(int(_nd.label(rd[k])[1]) for k in range(0, 6)) <= 2
           and max(int(_nd.label(rd[k])[1]) for k in range(6, 10)) == 1)
    checar(u"  e o laudo diz em quantos cortes o segundo ramo ficou (6)",
           laudo.get("cortes_com_dois_ramos") == 6, str(laudo))
    checar(u"  e a parede continua UM pedaco em 3D",
           int(_nd.label(rd)[1]) == 1, str(int(_nd.label(rd)[1])))
    r0, _t = P.maior_contorno_por_corte(dois, gg)
    checar(u"ISCA: sem o pulmao, abaixo da base fica um ramo so (a checagem "
           u"dos dois ramos reprovaria)",
           not all(r0[k, 5:15, 2:14].all() and r0[k, 5:15, 36:38].all()
                   for k in range(0, 6)))
    r1, _t = P.maior_contorno_por_corte(dois, gg, pulmao=pul)
    checar(u"ISCA: sem as costelas, o pedaco D (sem costela) entra no corte 0 "
           u"(a checagem do pedaco sem costela reprovaria)",
           bool(r1[0, 5:15, 16:29].any()))
    gf = G.Grade((2.0, 1.0, 1.0), ("inf", "post", "esq"))
    rf, _t = P.maior_contorno_por_corte(dois[::-1].copy(), gf,
                                        pulmao=pul[::-1].copy(),
                                        costelas=cost[::-1].copy())
    checar(u"com a serie pes-primeiro (indice para baixo), o mesmo resultado",
           np.array_equal(rf[::-1], rd))
    piso = np.zeros((4, 30, 20), bool)
    piso[:, 5:15, 2:14] = True
    piso[0, 15:22, 2:4] = True
    piso[1, 20:22, 2:4] = True
    pul2 = np.zeros_like(piso)
    pul2[2:4, 16:26, 10:18] = True
    cst2 = np.zeros_like(piso)
    cst2[:, 8:10, 4:6] = True
    rp, _t = P.maior_contorno_por_corte(piso, gg, pulmao=pul2, costelas=cst2)
    checar(u"o pedaco de 4 mm2 ligado ao ramo com costela NAO vira segundo "
           u"contorno (piso de %.0f mm2)" % P.AREA_MINIMA_DO_SEGUNDO_RAMO_MM2,
           not rp[1, 20:22, 2:4].any() and rp[1, 5:15, 2:14].all())
    velho_piso = P.AREA_MINIMA_DO_SEGUNDO_RAMO_MM2
    try:
        P.AREA_MINIMA_DO_SEGUNDO_RAMO_MM2 = 0.0
        ri2, _t = P.maior_contorno_por_corte(piso, gg, pulmao=pul2,
                                             costelas=cst2)
    finally:
        P.AREA_MINIMA_DO_SEGUNDO_RAMO_MM2 = velho_piso
    checar(u"ISCA: sem o piso, o pedaco de 4 mm2 vira segundo contorno (a "
           u"checagem de cima reprovaria)", bool(ri2[1, 20:22, 2:4].any()))

    g, hu, masks, ex = montar_fantoma_com_derrame()
    ext = _externo_derrame()
    placa = ((ex["zf"] >= 80) & (ex["zf"] <= 84) & (np.abs(ex["my"]) <= 3.0)
             & (ex["mx"] <= -95.0))
    masks["scapula_right_placa"] = placa
    linhas = []
    pa = P.parede_toracica(masks, ext, g, log=linhas.append)
    checar(u"sairam os dois lados", len(pa) == 2, str(sorted(pa)))
    for nome, v in sorted(pa.items()):
        pul, grd = P.ramos_da_parede(nome, masks)
        com, abaixo, sem = _pedacos_por_regiao(v, pul, grd, g)
        checar(u"`%s`: um pedaco por corte onde ha pulmao" % nome,
               com <= 1, u"%d pedacos" % com)
        checar(u"  e abaixo da base do pulmao no maximo dois, todos com "
               u"costela", abaixo <= 2 and sem == 0,
               u"%d pedacos, %d sem costela" % (abaixo, sem))
    checar(u"o log diz os cm3 descartados pela regra",
           any(u"um contorno por corte" in l and u"cm3" in l for l in linhas),
           str([l for l in linhas if u"corte" in l])[:200])
    orig = P.maior_contorno_por_corte
    try:
        P.maior_contorno_por_corte = (lambda mm, gr, **kw: (np.asarray(mm, bool)
                                                      .copy(), 0))
        pi = P.parede_toracica(masks, ext, g)
    finally:
        P.maior_contorno_por_corte = orig
    checar(u"  isca: sem a regra, a placa deixa DOIS pedacos num corte da "
           u"parede direita",
           _componentes_por_corte(pi.get("ChestWall_R", np.zeros(1, bool)),
                                  g) >= 2)


def teste_os_recortes_crus_e_os_pos_processados():
    secao(u"v8.3: os recortes pelas formas crua e processada, sem vasos")
    g, hu, masks, ex = montar_fantoma_com_derrame()
    med = masks["mediastinum"]
    menor = G.contrair(med, 4.0, g)
    no_full = dict(masks)
    no_full["mediastinum"] = menor
    cru = {"trunk_cavities:mediastinum": med}
    viz, _f = P.vizinhos_da_parede(no_full, cru=cru)
    checar(u"o recorte leva o mediastino do FULL E o cru",
           viz is not None and not (med & ~viz).any(),
           u"%d voxels do cru fora" % int((med & ~viz).sum()))
    velho = P.uniao_por_nome
    try:
        P.uniao_por_nome = (lambda mm, pref, cru=None, exato=False,
                            ambas=False: velho(mm, pref, cru=cru,
                                               exato=exato, ambas=False))
        vi, _f = P.vizinhos_da_parede(no_full, cru=cru)
    finally:
        P.uniao_por_nome = velho
    checar(u"  isca: consultando o cru so na falta, o mediastino cru ficava "
           u"de fora", vi is not None and bool((med & ~vi).any()))
    vasos = ("aorta", "inferior_vena_cava", "portal_vein", "superior_vena_cava",
             "subclavian", "brachiocephalic", "pulmonary_vein",
             "common_carotid", "great_arteries", "great_veins")
    lista = [c for c in P.CROPS_DA_PAREDE
             if any(c.startswith(v) or v.startswith(c) for v in vasos)]
    checar(u"nenhum vaso nos recortes da parede (decisao do autor)", not lista,
           str(lista))
    seg = P.RECORTES_DA_SEGUNDA_PASSADA
    checar(u"a segunda passada recorta pelos mesmos vizinhos, pelas "
           u"cavidades, pelos pulmoes e pela Bag_Bowel",
           all(c in seg for c in P.CROPS_DA_PAREDE)
           and all(c in seg for c in P.CAVIDADES_PROIBIDAS
                   + P.CAVIDADE_TORACICA + P.PULMOES + ("bag_bowel",)),
           str(seg)[:120])
    checar(u"  e nao tem nada do que a parede CONTEM",
           not any(c.startswith(f) or f.startswith(c) for c in seg
                   for f in P.FICAM_NA_PAREDE + ("rib_", "costal_")))


def teste_a_suavizacao_e_a_pele_da_v83():
    secao(u"v8.3: suavizacao de 8 mm e pele de 5 mm")
    checar(u"`SUAVIZACAO_PAREDE_MM` e 8 mm", P.SUAVIZACAO_PAREDE_MM == 8.0,
           str(P.SUAVIZACAO_PAREDE_MM))
    checar(u"`ESPESSURA_PELE_MM` e 5 mm", P.ESPESSURA_PELE_MM == 5.0,
           str(P.ESPESSURA_PELE_MM))
    fonte = io.open(_componentes.fonte("app/radai_skin.py"), encoding="utf-8").read()
    import json as _json
    _bib = _json.load(io.open(_componentes.fonte("app/data/bibliography.json"),
                              encoding="utf-8"))
    _mir = [a for a in _bib.get("artigos") or [] if a.get("id") == "mir2020"]
    checar(u"  e a bibliografia amarra a fonte da pele (Mir 2020) a "
           u"`ESPESSURA_PELE_MM`",
           bool(_mir) and _mir[0].get("doi") == u"10.1016/j.radonc.2020.05.038"
           and u"app/radai_skin.py::ESPESSURA_PELE_MM"
           in (_mir[0].get("influencia") or []),
           str(_mir[0].get("influencia") if _mir else None))
    import ast
    arv = ast.parse(fonte)
    fn = [n for n in arv.body if isinstance(n, ast.FunctionDef)
          and n.name == "parede_toracica"][0]
    chamadas = [c for c in ast.walk(fn) if isinstance(c, ast.Call)
                and getattr(c.func, "attr", None) == "suavizar"]
    le = [c for c in chamadas if len(c.args) >= 2
          and getattr(c.args[1], "id", None) == "SUAVIZACAO_PAREDE_MM"]
    checar(u"`parede_toracica` suaviza com a CONSTANTE (e nao um literal)",
           chamadas and len(le) == len(chamadas),
           u"%d chamadas, %d com a constante" % (len(chamadas), len(le)))
    g, hu, masks, ex = montar_fantoma_com_derrame()
    ext = _externo_derrame()
    pa = P.parede_toracica(masks, ext, g)
    velho = P.SUAVIZACAO_PAREDE_MM
    try:
        P.SUAVIZACAO_PAREDE_MM = 3.0
        p3 = P.parede_toracica(masks, ext, g)
    finally:
        P.SUAVIZACAO_PAREDE_MM = velho

    def _sup(m):
        from scipy import ndimage
        return int((m & ~ndimage.binary_erosion(m)).sum())
    for nome in ("ChestWall_L", "ChestWall_R"):
        if nome in pa and nome in p3:
            a8 = _sup(pa[nome]) / float(max(1, pa[nome].sum()))
            a3 = _sup(p3[nome]) / float(max(1, p3[nome].sum()))
            checar(u"`%s` com 8 mm tem menos superficie por volume que com 3"
                   % nome, a8 < a3, u"%.3f contra %.3f" % (a8, a3))


def _componentes_8(permitido, semente, grade):
    from scipy import ndimage
    p = np.asarray(permitido, bool)
    s = np.asarray(semente, bool) & p
    eixo = int(grade.eixo_sinal("sup")[0])
    vp, vs = np.moveaxis(p, eixo, 0), np.moveaxis(s, eixo, 0)
    fora = np.zeros(vp.shape, bool)
    for k in np.flatnonzero(vs.any(axis=(1, 2))):
        rot, _n = ndimage.label(vp[k], structure=np.ones((3, 3), int))
        ids = [i for i in np.unique(rot[vs[k]]) if i > 0]
        fora[k] = np.isin(rot, ids)
    return np.moveaxis(fora, 0, eixo)


def problemas_do_preenchimento(func):
    gg = G.Grade((2.0, 1.0, 1.0))
    perm = np.zeros((5, 20, 20), bool)
    perm[1, 2:8, 2:8] = True
    perm[1, 12:18, 12:18] = True
    perm[1, 8:11, 8:11] = True
    perm[2, 2:18, 2:18] = True
    perm[3, 2:8, 2:8] = True
    sem = np.zeros_like(perm)
    sem[1, 4, 4] = True
    sem[3, 10, 10] = True
    copia_p, copia_s = perm.copy(), sem.copy()
    r = func(perm, sem, gg)
    fora = []
    a = np.zeros((20, 20), bool)
    a[2:8, 2:8] = True
    if not np.array_equal(r[1], a):
        fora.append(u"o corte da semente nao e so A (%d voxels a mais)"
                    % int((r[1] & ~a).sum()))
    if r[2].any():
        fora.append(u"o corte sem semente nao saiu vazio")
    if r[3].any():
        fora.append(u"semente fora do permitido abriu caminho")
    if (r & ~perm).any():
        fora.append(u"saiu fora do permitido")
    if not (np.array_equal(perm, copia_p) and np.array_equal(sem, copia_s)):
        fora.append(u"mutou a entrada")
    gt = G.Grade((1.0, 2.0, 1.0), ("post", "sup", "esq"))
    rt = func(np.transpose(perm, (1, 0, 2)), np.transpose(sem, (1, 0, 2)), gt)
    if not np.array_equal(np.transpose(rt, (1, 0, 2)), r):
        fora.append(u"com os eixos trocados o resultado mudou")
    return fora


def teste_o_preenchimento_da_mama():
    secao(u"v8.3: o preenchimento da mama (componentes que tocam a semente)")
    p = problemas_do_preenchimento(P.componentes_que_tocam)
    checar(u"so a regiao tocada, 4-conexa, por corte, dentro do permitido, "
           u"sem mutar e em qualquer orientacao", not p, u"; ".join(p))
    p = problemas_do_preenchimento(_componentes_8)
    checar(u"isca: com vizinhanca de 8, a quina une C a A e a checagem acusa",
           any(u"so A" in x for x in p), u"; ".join(p))


_SP_MEMBROS = (5.0, 2.0, 2.0)


def _pernas(r_esq=35, r_dir=36):
    z, y, x = 40, 120, 200
    yy, xx = np.ogrid[:y, :x]
    cy = 58
    coxa_d = ((yy - cy) ** 2 + (xx - 55) ** 2) <= r_dir ** 2
    coxa_e = ((yy - cy) ** 2 + (xx - 145) ** 2) <= r_esq ** 2
    femur_d = ((yy - cy) ** 2 + (xx - 55) ** 2) <= 8 ** 2
    femur_e = ((yy - cy) ** 2 + (xx - 145) ** 2) <= 8 ** 2
    mesa = np.zeros((y, x), bool)
    mesa[cy + 38:cy + 40, 5:195] = True
    corte = np.full((y, x), -1000.0, np.float32)
    corte[mesa] = 400.0
    corte[coxa_d | coxa_e] = 40.0
    corte[femur_d | femur_e] = 700.0
    hu = np.broadcast_to(corte, (z, y, x)).copy()

    def _3d(m):
        return np.broadcast_to(m, (z, y, x)).copy()
    return (G.Grade(_SP_MEMBROS), hu,
            {"coxa_d": _3d(coxa_d), "coxa_e": _3d(coxa_e),
             "femur_d": _3d(femur_d), "femur_e": _3d(femur_e),
             "mesa": _3d(mesa)})


def _torax_com_bracos():
    z, y, x = 40, 130, 290
    yy, xx = np.ogrid[:y, :x]
    cy, cx = 62, 145
    tronco = (((yy - cy) / 55.0) ** 2 + ((xx - cx) / 85.0) ** 2) <= 1.0
    pulmoes = ((((yy - cy) / 28.0) ** 2 + ((xx - cx + 42) / 24.0) ** 2)
               <= 1.0) | ((((yy - cy) / 28.0) ** 2
                           + ((xx - cx - 42) / 24.0) ** 2) <= 1.0)
    braco_d = ((yy - cy) ** 2 + (xx - (cx - 117)) ** 2) <= 22 ** 2
    braco_e = ((yy - cy) ** 2 + (xx - (cx + 117)) ** 2) <= 22 ** 2
    mesa = np.zeros((y, x), bool)
    mesa[cy + 57:cy + 59, 3:287] = True
    corte = np.full((y, x), -1000.0, np.float32)
    corte[mesa] = 400.0
    corte[tronco | braco_d | braco_e] = 40.0
    corte[pulmoes & tronco] = -800.0
    hu = np.broadcast_to(corte, (z, y, x)).copy()

    def _3d(m):
        return np.broadcast_to(m, (z, y, x)).copy()
    return (G.Grade(_SP_MEMBROS), hu,
            {"tronco": _3d(tronco), "braco_d": _3d(braco_d),
             "braco_e": _3d(braco_e), "mesa": _3d(mesa & ~tronco)})


def _cobre(maior, parte):
    return 100.0 * float((maior & parte).sum()) / max(1, int(parte.sum()))


def teste_o_corpo_da_r3_leva_os_membros_comparaveis():
    secao(u"v8.3: o corpo da R3 leva as duas pernas, e deixa o braco de fora")
    g, hu, ex = _pernas()
    so = P.contorno_externo(hu, g)
    par = None
    try:
        par = P.contorno_externo(hu, g, com_o_corpo=True)
    except TypeError as e:
        checar(u"`contorno_externo` aceita `com_o_corpo=True`", False,
               u"%s" % e)
        return
    checar(u"com `com_o_corpo=True` ele devolve o par (externo, corpo)",
           isinstance(par, tuple) and len(par) == 2, repr(type(par)))
    if not (isinstance(par, tuple) and len(par) == 2):
        return
    externo, corpo = par
    checar(u"o externo do par e o de sempre, bit a bit (a pele e a parede "
           u"nao mudam)", so is not None and externo is not None
           and np.array_equal(so, externo))
    a, b = (_cobre(so, ex["coxa_d"]), _cobre(so, ex["coxa_e"]))
    checar(u"  e ele continua com UMA perna so (o maior componente)",
           max(a, b) > 99.0 and min(a, b) < 1.0,
           u"coxa D %.1f%%, coxa E %.1f%%" % (a, b))
    vd = float(ex["coxa_d"].sum()) * g.volume_voxel_mm3 / 1000.0
    ve = float(ex["coxa_e"].sum()) * g.volume_voxel_mm3 / 1000.0
    checar(u"o corpo da R3 leva as DUAS coxas (%.0f e %.0f cm3, %.0f%% da "
           u"maior)" % (vd, ve, 100.0 * min(vd, ve) / max(vd, ve)),
           corpo is not None and _cobre(corpo, ex["coxa_d"]) > 99.0
           and _cobre(corpo, ex["coxa_e"]) > 99.0,
           u"coxa D %.1f%%, coxa E %.1f%%" % (
               _cobre(corpo, ex["coxa_d"]) if corpo is not None else 0,
               _cobre(corpo, ex["coxa_e"]) if corpo is not None else 0))
    checar(u"  e os dois femures inteiros dentro dele",
           corpo is not None and _cobre(corpo, ex["femur_d"]) == 100.0
           and _cobre(corpo, ex["femur_e"]) == 100.0)
    checar(u"  sem a mesa (a erosao continua valendo para os dois)",
           corpo is not None and _cobre(corpo, ex["mesa"]) < 1.0,
           u"%.1f%%" % (_cobre(corpo, ex["mesa"]) if corpo is not None else 0))
    checar(u"  e o corpo contem o externo (a R3 nunca tira o que a pele cobre)",
           corpo is not None and not (externo & ~corpo).any())

    gt, hut, et = _torax_com_bracos()
    vt = float(et["tronco"].sum()) * gt.volume_voxel_mm3 / 1000.0
    vb = float(et["braco_d"].sum()) * gt.volume_voxel_mm3 / 1000.0
    razao = 100.0 * vb / vt
    ext_t, corpo_t = P.contorno_externo(hut, gt, com_o_corpo=True)
    checar(u"no torax, o braco solto tem bem menos que metade do tronco "
           u"(medido: %.1f%%, %.0f de %.0f cm3)" % (razao, vb, vt),
           razao < 25.0, u"%.1f%%" % razao)
    checar(u"  e o corpo da R3 e o proprio externo: os bracos ficam FORA "
           u"(a decisao escrita do autor)",
           ext_t is not None and corpo_t is not None
           and np.array_equal(ext_t, corpo_t)
           and _cobre(corpo_t, et["braco_d"]) < 1.0
           and _cobre(corpo_t, et["braco_e"]) < 1.0
           and _cobre(corpo_t, et["tronco"]) > 99.0,
           u"braco D %.1f%%, braco E %.1f%%" % (
               _cobre(corpo_t, et["braco_d"]) if corpo_t is not None else -1,
               _cobre(corpo_t, et["braco_e"]) if corpo_t is not None else -1))
    checar(u"  (e o pulmao, ar DENTRO do tronco, continua dentro)",
           corpo_t is not None and _cobre(corpo_t, et["tronco"]) > 99.0)

    velho = P.FRACAO_DO_MAIOR_NO_CORPO
    try:
        P.FRACAO_DO_MAIOR_NO_CORPO = 1.01
        _e2, c2 = P.contorno_externo(hu, g, com_o_corpo=True)
        checar(u"ISCA: so com o maior (fracao > 1), a outra coxa sai do "
               u"corpo (a checagem das duas coxas reprovaria)",
               c2 is not None and min(_cobre(c2, ex["coxa_d"]),
                                      _cobre(c2, ex["coxa_e"])) < 1.0)
        P.FRACAO_DO_MAIOR_NO_CORPO = 0.05
        _e3, c3 = P.contorno_externo(hut, gt, com_o_corpo=True)
        checar(u"ISCA: com um piso de 5%, o braco solto entra no corpo (a "
               u"checagem do torax reprovaria)",
               c3 is not None and _cobre(c3, et["braco_d"]) > 99.0)
    finally:
        P.FRACAO_DO_MAIOR_NO_CORPO = velho
    checar(u"a fracao de fabrica e metade do maior",
           P.FRACAO_DO_MAIOR_NO_CORPO == 0.5, repr(P.FRACAO_DO_MAIOR_NO_CORPO))


def _torax_magro(pele_mm=6.0):
    sp = (3.0, 1.5, 1.5)
    nz, ny, nx = 50, 130, 190
    g = G.Grade(sp)
    zz, yy, xx = np.mgrid[0:nz, 0:ny, 0:nx]
    my = (yy - 62.0) * sp[1]
    mx = (xx - 95.0) * sp[2]
    a, b = 125.0, 80.0
    tronco = (mx / a) ** 2 + (my / b) ** 2 <= 1.0
    hu = np.full((nz, ny, nx), -1000.0, np.float32)
    hu[tronco] = 40.0
    ao, bo = a - pele_mm, b - pele_mm
    ai, bi = ao - 5.0, bo - 5.0
    anel = (((mx / ao) ** 2 + (my / bo) ** 2 <= 1.0)
            & ((mx / ai) ** 2 + (my / bi) ** 2 > 1.0))
    costelas = {}
    for i in range(1, 9):
        z0 = 44 - (i - 1) * 5
        arco = anel & (zz >= z0) & (zz < z0 + 2) & (my < 50.0) & (
            np.abs(mx) > 25.0)
        costelas["rib_right_%d" % i] = arco & (mx < 0)
        costelas["rib_left_%d" % i] = arco & (mx >= 0)
    s = np.sqrt(np.clip(1.0 - ((zz - 25.0) * sp[0] / 70.0) ** 2, 0, None))
    with np.errstate(divide="ignore", invalid="ignore"):
        pulmao = (((mx / (ai * s)) ** 2 + (my / (bi * s)) ** 2 <= 1.0)
                  & (s > 0))
    pulmao &= (np.abs(mx) > 20.0) & (my < 45.0)
    hu[pulmao] = -800.0
    for m in costelas.values():
        hu[m] = 700.0
    vert = (np.abs(mx) <= 18.0) & (my >= 40.0) & (my <= 70.0)
    est = ((np.abs(mx) <= 15.0) & (my <= -(bi - 12)) & (my >= -bo)
           & (zz >= 15) & (zz < 46))
    hu[vert] = 700.0
    hu[est] = 700.0
    masks = {"lung_right": pulmao & (mx < 0), "lung_left": pulmao & (mx > 0),
             "vertebrae_T8": vert, "sternum": est,
             "abdominal_cavity": tronco & (zz < 3) & ~vert}
    masks.update(costelas)
    return g, hu, masks


def _cobertura_por_corte(pa, masks, g, ext):
    dentro = G.contrair(ext, P.ESPESSURA_PELE_MM, g)
    pior, vazios = {}, {}
    for nome in ("ChestWall_L", "ChestWall_R"):
        pul, cost = P.ramos_da_parede(nome, masks)
        w = pa.get(nome)
        w = np.zeros(cost.shape, bool) if w is None else w
        cobs, sem = [], 0
        for k in range(cost.shape[0]):
            if not (pul[k].any() and cost[k].any()):
                continue
            ref = cost[k] & dentro[k]
            if not w[k].any():
                sem += 1
            if ref.any():
                cobs.append(float((ref & w[k]).sum()) / float(ref.sum()))
        pior[nome] = min(cobs) if cobs else 1.0
        vazios[nome] = sem
    return pior, vazios


def teste_a_parede_da_paciente_magra():
    secao(u"v8.5: a parede da paciente magra nao some dos cortes com costela "
          u"e pulmao")
    g, hu, masks = _torax_magro()
    ext = P.contorno_externo(hu, g)
    velho = P.garantir_os_cortes
    try:
        P.garantir_os_cortes = lambda *a, **k: {}
        pi = P.parede_toracica(masks, ext, g, torax=True)
    finally:
        P.garantir_os_cortes = velho
    pior_i, _vaz_i = _cobertura_por_corte(pi, masks, g, ext)
    checar(u"(pre-condicao) a suavizacao de %g mm, sozinha, tira a parede de "
           u"cima das costelas da paciente magra (pior corte: %.0f%%)"
           % (P.SUAVIZACAO_PAREDE_MM, 100.0 * min(pior_i.values())),
           min(pior_i.values()) < P.COBERTURA_MINIMA_DAS_COSTELAS,
           str(pior_i))
    linhas = []
    pa = P.parede_toracica(masks, ext, g, torax=True, log=linhas.append)
    pior, vazios = _cobertura_por_corte(pa, masks, g, ext)
    checar(u"nenhum corte com costela e pulmao do lado fica sem parede",
           sorted(pa) == ["ChestWall_L", "ChestWall_R"]
           and not any(vazios.values()), str(vazios))
    checar(u"  e em todo corte a parede cobre pelo menos %.0f%% das costelas "
           u"(pior: %.0f%%)" % (100.0 * P.COBERTURA_MINIMA_DAS_COSTELAS,
                                100.0 * min(pior.values())),
           min(pior.values()) >= P.COBERTURA_MINIMA_DAS_COSTELAS, str(pior))
    pulmoes = masks["lung_left"] | masks["lung_right"]
    dentro = G.contrair(ext, P.ESPESSURA_PELE_MM, g)
    checar(u"  sem entrar no pulmao nem passar da pele",
           all(not (v & pulmoes).any() and not (v & ~dentro).any()
               for v in pa.values()))
    checar(u"  e os dois lados continuam disjuntos",
           not (pa["ChestWall_L"] & pa["ChestWall_R"]).any())
    com = max(_pedacos_por_regiao(v, *P.ramos_da_parede(n, masks) + (g,))[0]
              for n, v in pa.items())
    checar(u"  e um pedaco por corte onde ha pulmao", com <= 1, str(com))
    checar(u"o log diz quantos cortes voltaram, por lado",
           any(u"o pedaco sem suavizar voltou" in l for l in linhas),
           str([l for l in linhas if u"voltou" in l]))
    gn, hun, mn, _exn = montar_fantoma()
    extn = P.contorno_externo(hun, gn)
    ln = []
    pn = P.parede_toracica(mn, extn, gn, log=ln.append)
    checar(u"no torax de espessura normal a parede fica como estava (nada "
           u"volta)", len(pn) == 2
           and not any(u"o pedaco sem suavizar voltou" in l for l in ln),
           str([l for l in ln if u"voltou" in l]))
    texto = M.descricao_da_parede()
    checar(u"a descricao da ROI diz a regra",
           u"nenhum corte com costela e pulmao" in texto, texto[:120])


def _fantoma_do_estoma():
    sp = (2.5, 1.0, 1.0)
    nz, ny, nx = 24, 130, 220
    g = G.Grade(sp)
    zz, yy, xx = np.mgrid[0:nz, 0:ny, 0:nx]
    my = (yy - 60.0) * sp[1]
    mx = (xx - 100.0) * sp[2]
    tronco = (mx / 75.0) ** 2 + (my / 50.0) ** 2 <= 1.0
    vert = (np.abs(mx) <= 12) & (my >= 25) & (my <= 45)
    cav = ((mx / 71.0) ** 2 + (my / 46.0) ** 2 <= 1.0) & ~vert
    r = np.sqrt(mx ** 2 + (my + 32.0) ** 2)
    colon = r <= 14.0
    lumen = r <= 11.0
    hu = np.full((nz, ny, nx), -1000.0, np.float32)
    hu[tronco] = 40.0
    hu[vert] = 700.0
    zs = (zz >= 10) & (zz < 16)
    broto = zs & (np.abs(mx) <= 9) & (my >= -56) & (my <= -40)
    colon = colon | broto
    canal = zs & (np.abs(mx) <= 4) & (my >= -70) & (my <= -21)
    hu[broto] = 40.0
    lumen = lumen | (canal & (my >= -56))
    hu[canal] = -1000.0
    fenda = zs & (np.abs(mx) <= 6) & (my < -46) & tronco & ~broto
    hu[fenda] = -1000.0
    hu[lumen] = -1000.0
    mesa = (my >= 52) & (my <= 55) & (np.abs(mx) <= 90)
    hu[mesa] = 300.0
    braco = ((mx - 100.0) / 10.0) ** 2 + (my / 15.0) ** 2 <= 1.0
    umero = ((mx - 100.0) / 5.0) ** 2 + (my / 5.0) ** 2 <= 1.0
    hu[braco] = 40.0
    hu[umero] = 700.0
    masks = {"abdominal_cavity": cav, "colon": colon, "vertebrae_L3": vert,
             "humerus_left": umero}
    ex = {"mesa": mesa, "braco": braco, "fundo": G.contrair(tronco, 8.0, g),
          "parede": (tronco & ~cav & (my < -40) & (np.abs(mx) < 20)
                     & ~(zs & (np.abs(mx) <= 6)))}
    return g, hu, masks, ex


def teste_o_corpo_da_pele_leva_as_estruturas():
    secao(u"v8.5: o corpo da pele leva as estruturas segmentadas e fecha o "
          u"contorno anterior (estoma, parede fina sobre a alca)")
    import time
    g, hu, masks, ex = _fantoma_do_estoma()
    ext = P.contorno_externo(hu, g)
    checar(u"(pre-condicao) so pelo limiar, o corpo perde a alca e a parede "
           u"fina, e a pele entra fundo no ar da alca",
           (masks["colon"] & ~ext).any() and (ex["parede"] & ~ext).any()
           and (P.pele(ext, g) & ex["fundo"]).any())
    linhas = []
    t0 = time.time()
    corpo = P.corpo_da_pele(ext, masks, g, volume_hu=hu, log=linhas.append)
    seg = time.time() - t0
    checar(u"o corpo leva a alca inteira (o estoma tambem)",
           not (masks["colon"] & ~corpo).any(),
           str(int((masks["colon"] & ~corpo).sum())))
    checar(u"  e a parede fina sobre o ar da alca",
           not (ex["parede"] & ~corpo).any(),
           str(int((ex["parede"] & ~corpo).sum())))
    pl = P.pele(corpo, g)
    checar(u"  e a pele nao entra no fundo do corpo",
           not (pl & ex["fundo"]).any(), str(int((pl & ex["fundo"]).sum())))
    checar(u"  sem levar a mesa nem o braco separado (que tem o umero "
           u"segmentado)", not (corpo & ex["mesa"]).any()
           and not (corpo & ex["braco"]).any())
    checar(u"  e e rapido: %.2f s neste fantoma (%d voxels)"
           % (seg, int(hu.size)), seg < 10.0)
    checar(u"  e o log diz o ganho e o tempo",
           any(u"o corpo inicial leva" in l and u" s" in l for l in linhas),
           str(linhas))
    velho = P.ANCORAS_DO_FECHAMENTO
    try:
        P.ANCORAS_DO_FECHAMENTO = ()
        ci = P.corpo_da_pele(ext, masks, g, volume_hu=hu)
    finally:
        P.ANCORAS_DO_FECHAMENTO = velho
    checar(u"ISCA: sem a ancora das alcas, a parede fina sobre o ar fica de "
           u"fora", bool((ex["parede"] & ~ci).any()))
    velha = P._uniao_das_estruturas
    try:
        P._uniao_das_estruturas = lambda masks, forma: (
            np.zeros(forma, bool), 0)
        cu = P.corpo_da_pele(ext, masks, g, volume_hu=hu)
    finally:
        P._uniao_das_estruturas = velha
    checar(u"ISCA: sem as estruturas, o corpo e o do limiar e perde a alca",
           bool((masks["colon"] & ~cu).any()))
    s = M._construir_pele_e_parede(dict(masks), g, volume_hu=hu)
    pele_m = s.get("Skin")
    pele_m = pele_m[0] if isinstance(pele_m, tuple) else pele_m
    checar(u"o motor monta a Skin por esse corpo",
           pele_m is not None and np.array_equal(np.asarray(pele_m, bool), pl))


def main():
    print(u"=" * 68)
    print(u"test_skin | pele, parede toracica e a trava do contorno externo")
    print(u"=" * 68)
    for t in (teste_contorno_externo_deixa_a_mesa_de_fora,
              teste_a_pele_e_uma_casca_e_nao_um_solido,
              teste_a_parede_desce_abaixo_do_pulmao_e_nao_se_sobrepoe,
              teste_o_contorno_externo_nao_pode_ser_gravado,
              teste_a_traqueia_entregue_leva_a_margem_da_parede,
              teste_os_conjuntos_de_estudo_perderam_o_RadAI,
              teste_o_gatilho_de_torax,
              teste_sem_cavidade_a_parede_nao_sai,
              teste_a_parede_recorta_os_nomes_que_existem,
              teste_a_cartilagem_esta_na_base,
              teste_o_plano_medial_na_borda_do_esterno,
              teste_o_autoctone_fica,
              teste_a_base_e_lida_e_a_receita_esta_ligada,
              teste_a_parede_nao_depende_da_orientacao,
              teste_a_parede_nao_engole_o_derrame,
              teste_o_derrame_da_task_entra_na_cavidade_da_parede,
              teste_a_cavidade_se_divide_pelo_pulmao_mais_proximo,
              teste_a_cavidade_do_pescoco_nao_e_base,
              teste_um_contorno_por_corte,
              teste_os_recortes_crus_e_os_pos_processados,
              teste_a_suavizacao_e_a_pele_da_v83,
              teste_o_preenchimento_da_mama,
              teste_o_corpo_da_r3_leva_os_membros_comparaveis,
              teste_a_parede_da_paciente_magra,
              teste_o_corpo_da_pele_leva_as_estruturas):
        try:
            t()
        except Exception as e:
            import traceback
            checar("%s (excecao inesperada)" % t.__name__, False,
                   "%s: %s" % (type(e).__name__, e))
            traceback.print_exc()
    print()
    if FALHAS:
        print(u"FALHOU: %d de %d checagens" % (FALHAS, OK + FALHAS))
        for f in FALHOU:
            print(u"  - %s" % f)
        return 1
    print(u"OK: %d checagens, todas passaram" % OK)
    return 0


if __name__ == "__main__":
    sys.exit(main())
