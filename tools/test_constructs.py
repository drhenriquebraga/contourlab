# -*- coding: utf-8 -*-
import ast
import io
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")

import numpy as np
from scipy import ndimage

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.abspath(os.path.join(AQUI, ".."))
APP = os.path.join(RAIZ, "app")
sys.path.insert(0, APP)
sys.path.insert(0, AQUI)

import radai_geom as G
import radai_skin as P
import radai_constructs as C
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


SP = (3.0, 2.0, 2.0)
NZ, NY, NX = 70, 110, 150
_CACHE = {}


def montar():
    if "f" in _CACHE:
        g, masks, ex = _CACHE["f"]
        return g, dict(masks), dict(ex)
    g = G.Grade(SP)
    zi, yi, xi = np.ogrid[0:NZ, 0:NY, 0:NX]
    z = zi * SP[0]
    y = (yi - 55) * SP[1]
    x = (xi - 75) * SP[2]

    def elip(zc, yc, xc, rz, ry, rx):
        return ((z - zc) / rz) ** 2 + ((y - yc) / ry) ** 2 \
            + ((x - xc) / rx) ** 2 <= 1.0

    def cil(yc, xc, r, z0, z1):
        return ((y - yc) ** 2 + (x - xc) ** 2 <= r * r) & (z >= z0) & (z <= z1)

    corpo = (x / 140.0) ** 2 + (y / 100.0) ** 2 <= 1.0
    corpo = np.broadcast_to(corpo, (NZ, NY, NX)).copy()
    livre = corpo.copy()
    m = {}

    def poe(nome, forma):
        f = np.broadcast_to(forma, (NZ, NY, NX)) & livre
        m[nome] = f.copy()
        livre[f] = False
        return m[nome]

    r_cx = (x / 130.0) ** 2 + (y / 90.0) ** 2
    casca = np.broadcast_to((r_cx <= 1.0) & (r_cx >= 0.80), (NZ, NY, NX))
    vert = np.broadcast_to((np.abs(x) <= 18) & (y >= 40) & (y <= 70),
                           (NZ, NY, NX))
    poe("vertebrae_T6", vert & (z >= 105))
    poe("vertebrae_L1", vert & (z < 105))
    poe("sternum", (np.abs(x) <= 14) & (y >= -97) & (y <= -84)
        & (z >= 120) & (z <= 200))
    ponta = (np.abs(x) <= 40) & (y < 0)
    cart = np.zeros((NZ, NY, NX), bool)
    for i in range(1, 13):
        z0 = 200 - (i - 1) * 14
        faixa = casca & (z >= z0) & (z < z0 + 8) & ~((np.abs(x) <= 20) & (y > 0))
        if i <= 10:
            cart |= faixa & ponta & (np.abs(x) > 14)
        faixa = faixa & ~ponta
        poe("rib_left_%d" % i, faixa & (x > 0))
        poe("rib_right_%d" % i, faixa & (x < 0))
    poe("costal_cartilages", cart)
    clav = ((z >= 195) & (z <= 207) & (y >= -88) & (y <= -68)
            & (np.abs(x) >= 20) & (np.abs(x) <= 100))
    poe("clavicula_left", clav & (x > 0))
    poe("clavicula_right", clav & (x < 0))
    esc = ((z >= 150) & (z <= 200) & (y >= 30) & (y <= 80)
           & (np.abs(x) >= 70) & (np.abs(x) <= 125) & (r_cx > 1.02))
    poe("scapula_left", esc & (x > 0))
    poe("scapula_right", esc & (x < 0))
    pe = elip(160, -5, 85, 55, 45, 35)
    pd = elip(160, -5, -85, 55, 45, 35)
    poe("lung_upper_lobe_left", pe & (z > 160))
    poe("lung_lower_lobe_left", pe & (z <= 160))
    poe("lung_upper_lobe_right", pd & (z > 175))
    poe("lung_middle_lobe_right", pd & (z > 150) & (z <= 175))
    poe("lung_lower_lobe_right", pd & (z <= 150))
    poe("trachea", cil(0, 0, 9, 170, 210))
    poe("heart", elip(135, -25, 15, 30, 30, 40))
    poe("atrial_appendage_left", elip(150, -5, 45, 8, 8, 8))
    asc_c = cil(-30, -10, 12, 120, 185)
    t = np.clip(((y + 30) * 55 + (x + 10) * 35) / (55.0 ** 2 + 35.0 ** 2), 0, 1)
    arco = ((y - (-30 + 55 * t)) ** 2 + (x - (-10 + 35 * t)) ** 2 <= 11 ** 2) \
        & (z >= 185) & (z <= 197)
    desc_c = cil(25, 25, 10, 20, 190)
    poe("aorta", asc_c | arco | desc_c)
    poe("superior_vena_cava", cil(-15, -35, 8, 140, 200))
    poe("inferior_vena_cava", cil(0, -25, 10, 30, 125))
    poe("pulmonary_vein", elip(140, 8, 35, 7, 7, 7))
    poe("esophagus", cil(20, 0, 7, 60, 210))
    poe("iliac_artery_left", cil(20, 25, 6, 0, 20))
    poe("iliac_artery_right", cil(20, -25, 6, 0, 20))
    poe("liver", elip(75, -5, -60, 25, 50, 50))
    poe("gallbladder", elip(70, -40, -30, 10, 10, 10))
    poe("spleen", elip(80, 25, 80, 18, 18, 18))
    poe("kidney_left", elip(50, 35, 55, 25, 15, 15))
    poe("kidney_right", elip(50, 35, -55, 25, 15, 15))
    poe("adrenal_gland_left", elip(78, 30, 45, 6, 6, 6))
    poe("adrenal_gland_right", elip(78, 30, -45, 6, 6, 6))
    poe("portal_vein_and_splenic_vein", elip(68, -10, 0, 4, 4, 18))
    poe("stomach", elip(85, -35, 45, 15, 22, 28))
    poe("pancreas", elip(62, 5, 25, 8, 10, 30))
    poe("small_bowel", elip(30, -40, -10, 18, 25, 50))
    poe("colon", elip(40, -45, 65, 18, 15, 15))
    poe("urinary_bladder", elip(12, -40, 0, 8, 18, 22))
    poe("autochthon_left", (x >= 22) & (x <= 55) & (y >= 60) & (y <= 95))
    poe("autochthon_right", (x <= -22) & (x >= -55) & (y >= 60) & (y <= 95))

    cor = m["heart"]
    peri = G.expandir(cor, 6.0, g) & ~cor & (x <= 40)
    peri |= elip(130, 12, 0, 8, 8, 8)
    peri |= elip(135, -25, -35, 10, 10, 25)
    solto = elip(100, -60, -70, 6, 6, 6) & corpo
    peri |= solto
    m["pericardium"] = np.broadcast_to(peri, (NZ, NY, NX)) & corpo
    medi = ((np.abs(x) <= 25) & (y >= -80) & (y <= 35) & (z >= 150)
            & (z <= 210))
    m["mediastinum"] = (np.broadcast_to(medi, (NZ, NY, NX)) & corpo
                        & ~m["pericardium"])
    cav = elip(50, -5, 0, 55, 75, 115) & corpo & (z < 100) & ~vert
    ilha = elip(15, -60, 100, 5, 5, 5) & corpo & ~cav
    m["abdominal_cavity"] = np.broadcast_to(cav | ilha, (NZ, NY, NX)).copy()

    pulmoes = np.zeros((NZ, NY, NX), bool)
    for k in m:
        if k.startswith("lung_"):
            pulmoes |= m[k]
    ex = {"corpo": corpo, "pulmoes": pulmoes, "solto": np.broadcast_to(
        solto, (NZ, NY, NX)).copy(),
        "asc": m["aorta"] & np.broadcast_to(asc_c, (NZ, NY, NX)),
        "desc": m["aorta"] & np.broadcast_to(desc_c, (NZ, NY, NX)),
        "ilha": np.broadcast_to(ilha, (NZ, NY, NX)).copy()}
    _CACHE["f"] = (g, m, ex)
    return g, dict(m), dict(ex)


def _assinatura(masks):
    return dict((k, (int(np.asarray(v).sum()),
                     hash(np.asarray(v).tobytes()))) for k, v in masks.items())


def _uniao(masks, prefixos):
    u = np.zeros((NZ, NY, NX), bool)
    for k, v in masks.items():
        if any(k.startswith(p) for p in prefixos):
            u |= v
    return u


def _vizinhos_fantoma(masks):
    return _uniao(masks, tuple(M.FORA_DO_PERICARDIO))


def _topo(m):
    z = np.where(m.any(axis=(1, 2)))[0]
    return int(z.max())


def teste_os_nomes():
    secao(u"os nomes: cru, amigavel e task:rotulo pela mesma porta")
    a = np.zeros((4, 4, 4), bool)
    a[1, 1, 1] = True
    b = np.zeros((4, 4, 4), bool)
    b[2, 2, 2] = True
    checar(u"prefixo casa o cru e o composto amigavel",
           P.uniao_por_nome({"lung_upper_lobe_left": a, "Lung_Left": b},
                            ("lung_upper_lobe", "lung_left")).sum() == 2)
    checar(u"`task:rotulo` e caixa alta casam",
           P.uniao_por_nome({"trunk_cavities:Pericardium": a},
                            ("pericardium",)).sum() == 1)
    checar(u"`exato` nao casa por prefixo",
           P.uniao_por_nome({"abdominal_cavity_x": a},
                            ("abdominal_cavity",), exato=True) is None)
    checar(u"nome ausente devolve None (diferente de mascara vazia)",
           P.uniao_por_nome({"x": a}, ("heart",)) is None
           and P.uniao_por_nome({"heart": np.zeros_like(a)}, ("heart",))
           is not None)
    checar(u"o `cru` completa so o prefixo que o processado nao tem",
           P.uniao_por_nome({"heart": a}, ("heart", "clavicula"),
                            cru={"heart": b, "clavicula_left": b}).sum() == 2
           and not P.uniao_por_nome({"heart": a}, ("heart",),
                                    cru={"heart": b})[2, 2, 2])

    class Contador(object):

        def __init__(self, d):
            self.d, self.pedidos = d, []

        def __iter__(self):
            return iter(self.d)

        def __getitem__(self, k):
            self.pedidos.append(k)
            return self.d[k]

    cz = Contador({"heart": a, "liver": b, "spleen": b, "kidney_left": b})
    P.uniao_por_nome(cz, ("heart",))
    checar(u"so o que casa e materializado (nada de pedir as ~117)",
           cz.pedidos == ["heart"], str(cz.pedidos))


def teste_o_pericardio_corrigido():
    secao(u"B1: o pericardio corrigido")
    g, masks, ex = montar()
    antes = _assinatura(masks)
    peri, cor = masks["pericardium"], masks["heart"]
    checar(u"(fantoma) o pericardio da task NAO contem o coracao inteiro",
           (cor & ~peri).any())
    checar(u"(fantoma) o pericardio da task invade pulmao",
           (peri & ex["pulmoes"]).any())
    checar(u"(fantoma) e invade o esofago", (peri & masks["esophagus"]).any())
    linhas = []
    c = C.pericardio_corrigido(masks, g, log=linhas.append)
    checar(u"saiu", bool(c), repr(c))
    if not c:
        return
    r = c.mascara
    checar(u"a chave sugerida e `pericardium`", c.chave == "pericardium")
    checar(u"o coracao inteiro esta dentro («nao existe coracao fora do "
           u"pericardio»)", not (cor & ~r).any())
    checar(u"  e o apendice atrial esquerdo tambem",
           not (masks["atrial_appendage_left"] & ~r).any())
    for rot, alvo in ((u"pulmao", ex["pulmoes"]),
                      (u"esofago", masks["esophagus"]),
                      (u"traqueia", masks["trachea"]),
                      (u"os vizinhos do coracao (FORA_DO_PERICARDIO)",
                       _vizinhos_fantoma(masks)),
                      (u"a aorta descendente", ex["desc"])):
        n = int((r & alvo).sum())
        checar(u"nada de %s" % rot, n == 0, u"%d voxels" % n)
    tirar = _vizinhos_fantoma(masks) | ex["desc"]
    checar(u"todo o pericardio da task que nao e vizinho fica",
           not ((peri & ~tirar) & ~r).any())
    checar(u"e nada de fora do pericardio, do coracao e do apendice entra",
           not (r & ~(peri | cor | masks["atrial_appendage_left"])).any())
    checar(u"o log diz o ganho e a perda",
           any(l.startswith(u"pericardio corrigido:") for l in linhas),
           str(linhas)[:120])
    checar(u"a entrada nao foi tocada", _assinatura(masks) == antes)
    checar(u"  isca: so a soma (sem subtrair) invade o pulmao",
           ((peri | cor) & ex["pulmoes"]).any())

    amig = dict(masks)
    for lado, partes in (("lung_left", ("lung_upper_lobe_left",
                                        "lung_lower_lobe_left")),
                         ("lung_right", ("lung_upper_lobe_right",
                                         "lung_middle_lobe_right",
                                         "lung_lower_lobe_right"))):
        u = np.zeros((NZ, NY, NX), bool)
        for p in partes:
            u |= amig.pop(p)
        amig[lado] = u
    amig["trunk_cavities:pericardium"] = amig.pop("pericardium")
    c2 = C.pericardio_corrigido(amig, g)
    checar(u"com pulmao amigavel e `task:rotulo` sai o mesmo pericardio",
           c2 is not None and np.array_equal(c2.mascara, r))
    de_novo = dict(masks)
    de_novo[C.CHAVE_PERICARDIO] = r
    c3 = C.pericardio_corrigido(de_novo, g)
    checar(u"corrigir o ja corrigido devolve o mesmo (idempotente)",
           c3 is not None and np.array_equal(c3.mascara, r))

    linhas = []
    sem = dict((k, v) for k, v in masks.items() if k != "pericardium")
    checar(u"sem a trunk_cavities nao sai (None)",
           C.pericardio_corrigido(sem, g, log=linhas.append) is None)
    checar(u"  e o log nomeia a task",
           any(u"trunk_cavities" in l for l in linhas), str(linhas))

    linhas = []
    sem_cor = dict((k, v) for k, v in masks.items() if k != "heart")
    r_sem = C.pericardio_corrigido(sem_cor, g, log=linhas.append)
    checar(u"sem o coracao do modelo nao sai (None)", r_sem is None,
           repr(r_sem))
    checar(u"  e o log diz que foi o coracao do modelo que faltou",
           any(u"coracao do modelo" in l and u"nao sai" in l
               for l in linhas), str(linhas))
    fora_sem = int((cor & ~(peri & ~_vizinhos_fantoma(masks))).sum())
    checar(u"  isca: sem o coracao, o que sairia deixaria %d voxels de "
           u"coracao fora" % fora_sem, fora_sem > 1000)
    checar(u"toda descricao que sai afirma o que e verdade: o coracao "
           u"inteiro esta dentro", u"O coracao fica dentro" in c.descricao
           and not (cor & ~r).any())

    zi, yi, xi = np.ogrid[0:NZ, 0:NY, 0:NX]
    z, y, x = zi * SP[0], (yi - 55) * SP[1], (xi - 75) * SP[2]
    vaso = np.broadcast_to(((z - 135) / 20.0) ** 2 + ((y + 25) / 12.0) ** 2
                           + ((x - 57) / 8.0) ** 2 <= 1.0, (NZ, NY, NX)).copy()
    enc = dict(masks)
    enc["lung_vessels"] = vaso
    checar(u"(fantoma) o vaso pulmonar encosta no coracao",
           (vaso & cor).any(), u"%d voxels" % int((vaso & cor).sum()))
    linhas = []
    c5 = C.pericardio_corrigido(enc, g, log=linhas.append)
    checar(u"com um vizinho encostado, o coracao inteiro continua dentro",
           c5 is not None and not (cor & ~c5.mascara).any())
    checar(u"  e o vizinho, fora do coracao, sai",
           c5 is not None and not (c5.mascara & vaso & ~cor
                                   & ~masks["atrial_appendage_left"]).any())
    checar(u"  e o log diz quanto do coracao encostava",
           any(u"encostavam num vizinho" in l for l in linhas),
           str(linhas)[-1:])
    literal = ((peri | cor | masks["atrial_appendage_left"])
               & ~(_vizinhos_fantoma(enc) | ex["desc"]))
    checar(u"  isca: a formula na ordem literal deixaria coracao fora",
           (cor & ~literal).any(), u"%d voxels" % int((cor & ~literal).sum()))
    de_novo = dict(enc)
    de_novo[C.CHAVE_PERICARDIO] = c5.mascara
    c6 = C.pericardio_corrigido(de_novo, g)
    checar(u"  e continua idempotente",
           c6 is not None and np.array_equal(c6.mascara, c5.mascara))


def teste_o_heart_ai():
    secao(u"B2: o Heart_ai")
    g, masks, ex = montar()
    antes = _assinatura(masks)
    laa, cor = masks["atrial_appendage_left"], masks["heart"]
    t_laa = _topo(laa)
    checar(u"(fantoma) o topo do apendice fica abaixo do topo do coracao",
           t_laa < _topo(cor), u"%d contra %d" % (t_laa, _topo(cor)))
    t = max(_topo(cor), t_laa)
    checar(u"(fantoma) o pericardio da task sobe acima do topo do coracao "
           u"(o plano ainda tem o que cortar)",
           masks["pericardium"][t + 1:].any())
    linhas = []
    c = C.coracao_ai(masks, g, log=linhas.append)
    checar(u"saiu", bool(c), repr(c))
    if not c:
        return
    h = c.mascara
    checar(u"a chave sugerida comeca por `heart` (a parede recorta por "
           u"prefixo)", c.chave.startswith("heart")
           and any(c.chave.startswith(p) for p in P.CROPS_DA_PAREDE))
    _rot, n = ndimage.label(h)
    checar(u"UM volume", n == 1, u"%d pedacos" % n)
    checar(u"nada acima do corte mais alto das camaras e do apendice "
           u"(spec M-C)", not h[t + 1:].any(), u"topo do Heart_ai %d, marco %d"
           % (_topo(h), t))
    checar(u"o coracao do modelo esta INTEIRO dentro (o teto dos atrios "
           u"tambem)", not (cor & ~h).any(),
           u"%d voxels fora" % int((cor & ~h).sum()))
    checar(u"o apendice esta dentro", not (laa & ~h).any())
    corr = C.pericardio_corrigido(masks, g).mascara
    esperado = corr.copy()
    esperado[t + 1:] = False
    esperado &= ~ex["solto"]
    checar(u"o pericardio corrigido abaixo do marco esta dentro",
           not (esperado & ~h).any(), u"%d voxels fora"
           % int((esperado & ~h).sum()))
    checar(u"o pedaco solto do pericardio ficou de fora (um volume)",
           not (h & ex["solto"]).any())
    checar(u"  isca: o pedaco solto ESTAVA no pericardio corrigido",
           (corr & ex["solto"]).any())
    janela = np.zeros_like(cor)
    zc = np.where(cor.any(axis=(1, 2)))[0]
    janela[zc.min():min(zc.max(), t) + 1] = True
    asc = ex["asc"] & janela
    checar(u"a aorta ascendente abaixo do marco esta dentro",
           asc.any() and not (asc & ~h).any(),
           u"%d de %d" % (int((asc & h).sum()), int(asc.sum())))
    for rot, alvo in ((u"a aorta descendente", ex["desc"]),
                      (u"pulmao", ex["pulmoes"])):
        nn = int((h & alvo).sum())
        checar(u"nada de %s" % rot, nn == 0, u"%d voxels" % nn)
    checar(u"a descricao diz que o pericardio entrou e de que foi montado",
           u"Inclui o pericardio" in c.descricao
           and u"atrial_appendage_left" in c.descricao
           and u"TotalSegmentator" in c.descricao, c.descricao[:120])
    checar(u"  e diz o marco da v8.3, e de qual estrutura veio o corte",
           u"corte mais alto das camaras" in c.descricao
           and u"o do coracao do modelo" in c.descricao, c.descricao)
    checar(u"o log fala como o registro de casos reconhece",
           any(l.startswith(u"coracao de radioterapia: Heart_ai")
               for l in linhas), str(linhas)[-2:])
    checar(u"a entrada nao foi tocada", _assinatura(masks) == antes)

    rt, _d = M.coracao_de_radioterapia(dict(masks), g)
    checar(u"  isca: sem o plano, o pericardio corrigido passa do marco",
           corr[t + 1:].any())
    velho = C._marco_superior_do_coracao
    try:
        C._marco_superior_do_coracao = (
            lambda mk, cr, la, gr, cru=None: (la, u"topo do apendice"))
        ci = C.coracao_ai(masks, g)
    finally:
        C._marco_superior_do_coracao = velho
    checar(u"  isca: com o marco de antes (o topo do apendice), o teto do "
           u"coracao saia (a checagem de cima reprovaria)",
           ci is not None and (cor & ~ci.mascara).any(),
           u"%d voxels" % (int((cor & ~ci.mascara).sum())
                           if ci is not None else -1))
    alto = dict(masks)
    la2 = np.zeros_like(laa)
    la2[t_laa:_topo(cor) + 3, 51:54, 96:99] = True
    alto["atrial_appendage_left"] = laa | la2
    c_alto = C.coracao_ai(alto, g)
    checar(u"com o apendice acima do coracao, o marco sobe com ele",
           c_alto is not None
           and bool((c_alto.mascara & la2)[_topo(cor) + 2].any())
           and not c_alto.mascara[_topo(cor) + 3:].any()
           and u"o do apendice atrial esquerdo" in c_alto.descricao,
           (c_alto.descricao[-120:] if c_alto is not None else "-"))
    cam = dict(masks)
    at = np.zeros_like(cor)
    at[_topo(cor) + 1, 45:52, 70:80] = True
    cam["heart_atrium_left"] = at
    c_cam = C.coracao_ai(cam, g)
    checar(u"uma camara separada presente entra no marco (e a descricao diz "
           u"qual deu o corte)",
           c_cam is not None
           and u"o do heart_atrium_left" in c_cam.descricao,
           (c_cam.descricao[-120:] if c_cam is not None else "-"))

    sem = dict((k, v) for k, v in masks.items() if k != "pericardium")
    rt_sem, _d = M.coracao_de_radioterapia(dict(sem), g)
    linhas = []
    c2 = C.coracao_ai(sem, g, log=linhas.append)
    checar(u"sem pericardio sai EXATAMENTE a mesclagem do motor (spec B2, "
           u"Q35: «como estava ate hoje»)",
           c2 is not None and np.array_equal(c2.mascara, rt_sem),
           u"%s voxels diferentes" % (
               int((c2.mascara ^ rt_sem).sum()) if c2 is not None else "-"))
    antiga = G.maior_componente(G.limitar_por_plano(rt_sem | laa, "sup", laa,
                                                    grade=g))
    checar(u"  isca: a receita da primeira versao (apendice + plano + um "
           u"volume) da outra coisa", not np.array_equal(antiga, rt_sem),
           u"%d voxels" % int((antiga ^ rt_sem).sum()))
    checar(u"  e a descricao diz SEM pericardio, e por que",
           c2 is not None and u"SEM pericardio" in c2.descricao
           and u"trunk_cavities nao rodou" in c2.descricao,
           c2.descricao[-160:] if c2 is not None else "-")
    checar(u"  e o log tambem, com o prefixo que o registro reconhece",
           any(l.startswith(u"coracao de radioterapia: Heart_ai")
               and u"SEM pericardio" in l for l in linhas),
           str(linhas)[-1:])
    checar(u"  e nao afirma que o apendice ou o plano entraram",
           c2 is not None and u"atrial_appendage_left" not in c2.entrou
           and u"cortado acima" not in c2.descricao)
    c3 = C.coracao_ai(masks, g, pericardio=False)
    checar(u"`pericardio=False` ignora o pericardio presente e da a mesclagem",
           c3 is not None and np.array_equal(c3.mascara, rt)
           and u"pediu sem pericardio" in c3.descricao)

    linhas = []
    sem_laa = dict((k, v) for k, v in masks.items()
                   if k != "atrial_appendage_left")
    c4 = C.coracao_ai(sem_laa, g, log=linhas.append)
    checar(u"sem o apendice, nada acima do topo do coracao do modelo",
           c4 is not None and not c4.mascara[_topo(cor) + 1:].any())
    checar(u"  e o log diz que o marco foi o coracao, e que faltou o "
           u"apendice",
           any(u"o do coracao do modelo" in l
               and u"sem o apendice atrial esquerdo nesta serie" in l
               for l in linhas), str(linhas)[-200:])
    checar(u"sem o `heart` do modelo nao ha Heart_ai",
           C.coracao_ai(dict((k, v) for k, v in masks.items()
                             if k != "heart"), g) is None)

    gf = G.Grade(g.spacing, ("inf", "post", "esq"))
    mf = dict((k, np.ascontiguousarray(v[::-1])) for k, v in masks.items())
    cf = C.coracao_ai(mf, gf)
    d = G.dsc(cf.mascara[::-1], h) if cf is not None else 0.0
    checar(u"feet-first da o mesmo Heart_ai", d >= 0.999, u"DSC %.4f" % d)


def teste_o_vocabulario_do_full():
    secao(u"o vocabulario do FULL: heart_model e heart")
    import radai_names
    g, masks, ex = montar()
    ref_p = C.pericardio_corrigido(masks, g)
    ref_h = C.coracao_ai(masks, g)
    cm = radai_names.CHAVE_DO_CORACAO_DO_MODELO
    checar(u"a chave do coracao do modelo e a do tradutor (`%s`)" % cm,
           C.CHAVE_CORACAO_DO_MODELO == cm and cm != C.CHAVE_CORACAO_AI)

    p1 = dict(masks)
    p1[cm] = p1.pop("heart")
    linhas = []
    h1 = C.coracao_ai(p1, g, log=linhas.append)
    checar(u"so com `heart_model` o Heart_ai sai, igual ao do dicionario de "
           u"antes", h1 is not None and np.array_equal(h1.mascara,
                                                        ref_h.mascara),
           str(linhas)[-1:])
    p_1 = C.pericardio_corrigido(p1, g)
    checar(u"  e o pericardio corrigido tambem",
           p_1 is not None and np.array_equal(p_1.mascara, ref_p.mascara))
    checar(u"  e os dois dizem de qual nome veio o coracao",
           h1 is not None and h1.extras.get("coracao_do_modelo") == cm
           and ref_h.extras.get("coracao_do_modelo") == "heart")

    rt_p1, _d = M.coracao_de_radioterapia(dict(masks), g)
    p2 = dict(p1)
    p2["heart"] = rt_p1
    checar(u"(fantoma) o `heart` de RT tem aorta ascendente que o do modelo "
           u"nao tem", (rt_p1 & ex["asc"] & ~masks["heart"]).any())
    p_2 = C.pericardio_corrigido(p2, g)
    h2 = C.coracao_ai(p2, g)
    checar(u"com `heart_model` E o `heart` de RT, o pericardio usa o do "
           u"modelo", p_2 is not None and np.array_equal(p_2.mascara,
                                                        ref_p.mascara),
           u"%s voxels diferentes" % (
               int((p_2.mascara ^ ref_p.mascara).sum()) if p_2 else "-"))
    checar(u"  e o Heart_ai tambem",
           h2 is not None and np.array_equal(h2.mascara, ref_h.mascara))
    velha = C._coracao_do_modelo
    try:
        C._coracao_do_modelo = (lambda mk, cru=None: (
            P.uniao_por_nome(mk, ("heart",), cru=cru, exato=True), "heart"))
        p_v = C.pericardio_corrigido(p2, g)
        h_v = C.coracao_ai(dict((k, v) for k, v in p2.items() if k != "heart"),
                           g)
    finally:
        C._coracao_do_modelo = velha
    checar(u"  isca: procurando so `heart`, o pericardio absorve o coracao de "
           u"RT", p_v is not None and not np.array_equal(p_v.mascara,
                                                         ref_p.mascara),
           u"%s voxels a mais" % (int((p_v.mascara & ~ref_p.mascara).sum())
                                  if p_v else "-"))
    checar(u"  isca: procurando so `heart`, o FULL sem o de RT fica sem "
           u"Heart_ai", h_v is None)

    p3 = dict(p2)
    p3[cm] = np.zeros_like(masks["heart"])
    checar(u"`heart_model` vazio nao cai no `heart` de RT (nao ha Heart_ai "
           u"nem pericardio corrigido)",
           C.coracao_ai(p3, g) is None and C.pericardio_corrigido(p3, g)
           is None)
    p4 = dict(masks)
    p4["total_v3:heart_model"] = p4.pop("heart")
    h4 = C.coracao_ai(p4, g)
    checar(u"`total_v3:heart_model` tambem casa",
           h4 is not None and np.array_equal(h4.mascara, ref_h.mascara))
    p5 = dict((k, v) for k, v in masks.items() if k != "heart")
    h5 = C.coracao_ai(p5, g, cru={"heart": masks["heart"]})
    checar(u"sem coracao no dicionario, o do `cru` completa",
           h5 is not None and np.array_equal(h5.mascara, ref_h.mascara))

    saidas = (M.CONSTRUCOES_POR_SAIDA()
              if hasattr(M, "CONSTRUCOES_POR_SAIDA") else {})
    checar(u"a chave do Heart_ai (`%s`) e uma saida declarada no FULL do "
           u"motor" % C.CHAVE_CORACAO_AI, C.CHAVE_CORACAO_AI in saidas,
           str(sorted(saidas))[:160])
    checar(u"  e vira `Heart` no TG-263 (Heart_ai no TPS)",
           M.TG263.get(C.CHAVE_CORACAO_AI) == "Heart",
           str(M.TG263.get(C.CHAVE_CORACAO_AI)))
    checar(u"  isca: o nome da primeira versao (heart_rt) nao e saida do "
           u"FULL", "heart_rt" not in saidas)
    checar(u"a chave do pericardio corrigido e a da task no FULL",
           C.CHAVE_PERICARDIO == "pericardium")


def teste_a_bag_bowel():
    secao(u"D1: a Bag_Bowel")
    g, masks, ex = montar()
    antes = _assinatura(masks)
    cav = masks["abdominal_cavity"]
    fora = _uniao(masks, ("liver", "gallbladder", "urinary_bladder",
                          "spleen", "kidney_", "adrenal_gland_", "aorta",
                          "inferior_vena_cava", "portal_vein", "iliac_"))
    _r, n_cru = ndimage.label(cav & ~fora)
    checar(u"(fantoma) a cavidade menos os orgaos tem mais de um pedaco",
           n_cru > 1, u"%d" % n_cru)
    linhas = []
    c = C.bag_bowel(masks, g, log=linhas.append)
    checar(u"saiu", bool(c), repr(c))
    if not c:
        return
    b = c.mascara
    checar(u"a chave sugerida e `bag_bowel`", c.chave == "bag_bowel")
    checar(u"fica dentro da cavidade crua", not (b & ~cav).any())
    checar(u"(fantoma) a vesicula esta DENTRO da cavidade crua",
           (masks["gallbladder"] & cav).sum() > 0.9 * masks["gallbladder"].sum(),
           u"%d de %d" % (int((masks["gallbladder"] & cav).sum()),
                          int(masks["gallbladder"].sum())))
    for rot, pref in ((u"figado", ("liver",)),
                      (u"vesicula (decisao (b) da onda 2)", ("gallbladder",)),
                      (u"bexiga", ("urinary_bladder",)),
                      (u"baco", ("spleen",)), (u"rins", ("kidney_",)),
                      (u"adrenais", ("adrenal_gland_",)),
                      (u"vasos", ("aorta", "inferior_vena_cava",
                                  "portal_vein", "iliac_"))):
        nn = int((b & _uniao(masks, pref)).sum())
        checar(u"nada de %s" % rot, nn == 0, u"%d voxels" % nn)
    for rot, k in ((u"intestino delgado", "small_bowel"),
                   (u"colon", "colon"), (u"estomago", "stomach"),
                   (u"pancreas", "pancreas")):
        alvo = masks[k] & cav
        f = float((b & alvo).sum()) / max(1, alvo.sum())
        checar(u"mantem %s (%.0f%%)" % (rot, 100 * f), f >= 0.85,
               u"%.0f%%" % (100 * f))
    _r, n = ndimage.label(b)
    checar(u"UM volume", n == 1, u"%d" % n)
    checar(u"a ilha da cavidade ficou de fora", not (b & ex["ilha"]).any())
    v_cru = G.volume_cm3(cav & ~fora, g)
    v = G.volume_cm3(b, g)
    checar(u"o volume fica perto da subtracao crua (suavizar nao infla)",
           0.85 * v_cru <= v <= 1.02 * v_cru, u"%.0f contra %.0f" % (v, v_cru))
    checar(u"a suavizacao foi aplicada (a borda mudou)",
           bool((b ^ G.maior_componente(cav & ~fora)).any()))
    checar(u"a descricao diz que sobrepoe os orgaos abdominais",
           u"Sobrepoe os orgaos abdominais" in c.descricao, c.descricao)
    checar(u"o log diz o volume e o que caiu",
           any(l.startswith(u"Bag_Bowel:") for l in linhas))
    checar(u"a entrada nao foi tocada", _assinatura(masks) == antes)
    s = G.suavizar(cav & ~fora, C.SUAVIZACAO_BAG_MM, g)
    checar(u"  isca: sem o recorte depois da suavizacao, ela invade o figado",
           (s & masks["liver"]).any())
    velha = C.ORGAOS_FORA_DA_BAG
    C.ORGAOS_FORA_DA_BAG = tuple(o for o in velha if o != "gallbladder")
    try:
        c_isca = C.bag_bowel(masks, g)
    finally:
        C.ORGAOS_FORA_DA_BAG = velha
    checar(u"  isca: sem `gallbladder` na lista, a vesicula fica na "
           u"Bag_Bowel (reprovaria)", c_isca is not None
           and (c_isca.mascara & masks["gallbladder"]).any())
    checar(u"a descricao diz que a vesicula saiu",
           u"vesicula" in c.descricao, c.descricao)
    tor = dict(masks)
    zc, yc, xc = [int(v) for v in np.argwhere(cav).mean(axis=0)]
    for k, dz in (("esophagus", -2), ("heart", 0), ("lung_left", 2)):
        m = np.zeros_like(cav)
        m[zc + dz:zc + dz + 2, yc - 1:yc + 1, xc - 1:xc + 1] = True
        m &= cav
        tor[k] = m
    c_tor = C.bag_bowel(tor, g)
    for k in ("esophagus", "heart", "lung_left"):
        nn = int((c_tor.mascara & tor[k]).sum()) if c_tor else -1
        checar(u"nada de %s (o que e do torax sai)" % k, nn == 0,
               u"%d voxels" % nn)
    velha = C.ORGAOS_DO_TORAX_FORA_DA_BAG
    C.ORGAOS_DO_TORAX_FORA_DA_BAG = ()
    try:
        c_isca = C.bag_bowel(tor, g)
    finally:
        C.ORGAOS_DO_TORAX_FORA_DA_BAG = velha
    checar(u"  isca: sem a lista do torax, o esofago fica na Bag_Bowel "
           u"(reprovaria)", c_isca is not None
           and bool((c_isca.mascara & tor["esophagus"]).any()))
    checar(u"a descricao diz que o esofago, o coracao e o pulmao sairam",
           all(p in c.descricao for p in (u"esofago", u"coracao",
                                          u"pulmao")), c.descricao)
    checar(u"a falta do coracao NAO entra no `faltou` (e o campo)",
           not [f for f in (c.faltou or ()) if u"cora" in f], c.faltou)
    linhas = []
    sem = dict((k, v) for k, v in masks.items() if k != "abdominal_cavity")
    checar(u"sem a cavidade (trunk_cavities) nao sai",
           C.bag_bowel(sem, g, log=linhas.append) is None
           and any(u"trunk_cavities" in l for l in linhas))


_PARECE_VASO = ("artery", "arteria", "vein", "vena", "aorta", "trunk")
_FUNCOES_QUE_SAIRAM = ("aplicar_margens_por_vaso", "compostos_de_vasos",
                       "compostos_de_vasos_padrao")


def _tabelas_de_margem(fonte, vasos):
    achados = []
    arv = ast.parse(fonte)
    for no in arv.body:
        if isinstance(no, ast.FunctionDef) and no.name in _FUNCOES_QUE_SAIRAM:
            achados.append(no.name)
        if not isinstance(no, ast.Assign):
            continue
        nomes = [getattr(a, "id", "") for a in no.targets]
        if any("MARGEM" in n.upper() for n in nomes):
            achados.extend(nomes)
            continue
        if isinstance(no.value, ast.Dict):
            for k, v in zip(no.value.keys, no.value.values):
                if (isinstance(k, ast.Constant) and k.value in vasos
                        and not isinstance(v, (ast.Tuple, ast.List,
                                               ast.Dict))):
                    achados.extend(nomes)
                    break
    return achados


def _faltam_na_bag(compostos, lista):
    return sorted(p for c in compostos for p in M.COMPOSTOS.get(c, ())
                  if not any(P._casa(p, pref) for pref in lista))


def teste_os_vasos_tem_uma_fonte_so():
    secao(u"A3: os vasos tem uma fonte so, a do motor")
    vasos = set(M.MARGEM_OAR_MM)
    fonte = io.open(_componentes.fonte("app/radai_constructs.py"),
                    encoding="utf-8").read()
    achados = _tabelas_de_margem(fonte, vasos)
    checar(u"`radai_constructs` nao tem tabela de margem nem as funcoes que "
           u"sairam", achados == [], str(achados))
    for isca, rot in ((u'MARGEM_POR_VASO_MM = {"aorta": 1.0}\n',
                       u"a tabela da primeira versao"),
                      (u'TABELA = {"superior_vena_cava": 2.0}\n',
                       u"um dicionario de vaso -> mm com outro nome"),
                      (u"def aplicar_margens_por_vaso(m, g):\n    return m\n",
                       u"a funcao que saiu")):
        checar(u"  isca: %s e acusada" % rot,
               _tabelas_de_margem(isca, vasos) != [])
    checar(u"  e um dicionario de vaso -> lista (COMPOSTOS) nao e acusado",
           _tabelas_de_margem(u'X = {"aorta": ["a", "b"]}\n', vasos) == [])
    for nome in _FUNCOES_QUE_SAIRAM + ("MARGEM_POR_VASO_MM",):
        checar(u"`%s` nao existe mais no modulo" % nome,
               not hasattr(C, nome))

    vm = C.vasos_do_motor()
    checar(u"os vasos sao a tabela do motor menos a via aerea",
           sorted(vm) == sorted(k for k in M.MARGEM_OAR_MM
                                if k != "trachea"), str(sorted(vm)))
    nao = [n for n in vm if not any(s in n for s in _PARECE_VASO)]
    checar(u"  e todo nome da lista e vaso (a Bag_Bowel nao tira orgao por "
           u"engano)", nao == [], str(nao))
    falso = list(vm) + ["esophagus"]
    checar(u"  isca: um orgao na lista seria acusado",
           [n for n in falso if not any(s in n for s in _PARECE_VASO)]
           == ["esophagus"])
    cv = C.compostos_de_vaso()
    de_vaso = sorted(getattr(M, "COMPOSTOS_MENOS", {}) or
                     ("carotids", "great_arteries", "great_veins"))
    checar(u"os compostos de vaso do motor sao derivados (os que cedem ao "
           u"Heart_ai: %s)" % ", ".join(de_vaso),
           all(c in cv for c in de_vaso), str(cv))
    lista = C._vasos_para_tirar()
    checar(u"toda parte de composto de vaso sai da Bag_Bowel",
           _faltam_na_bag(de_vaso, lista) == [],
           str(_faltam_na_bag(de_vaso, lista)))
    checar(u"  isca: um vaso fora da lista seria acusado",
           _faltam_na_bag(de_vaso, [p for p in lista
                                    if p != "superior_vena_cava"])
           == ["superior_vena_cava"])


def teste_a_ordem_dos_vasos_e_a_casca():
    secao(u"A3: o composto dos prontos, e a casca que a ordem deixa")
    g0, masks, ex = montar()
    antes = _assinatura(masks)
    g = G.Grade((SP[0], 0.9, 0.9))
    vasos = C.vasos_do_motor()
    prontos = dict(masks)
    for v in vasos:
        if v in prontos and M.MARGEM_OAR_MM.get(v):
            prontos[v] = G.expandir(masks[v], float(M.MARGEM_OAR_MM[v]), g)

    def composto(d, heart, nome):
        s = np.zeros((NZ, NY, NX), bool)
        for p in M.COMPOSTOS[nome]:
            if p in d:
                s |= d[p]
        return s & ~heart

    def casca(comp, heart, nome):
        lum = np.zeros((NZ, NY, NX), bool)
        for p in M.COMPOSTOS[nome]:
            if p in masks:
                lum |= masks[p]
        return comp & ~G.expandir(lum & ~heart, 1.0, g)

    for rot, peri in ((u"sem pericardio", False), (u"com pericardio", None)):
        h_pr = C.coracao_ai(prontos, g, pericardio=peri)
        h_lu = C.coracao_ai(masks, g, pericardio=peri)
        if h_pr is None or h_lu is None:
            checar(u"%s: o Heart_ai saiu nas duas ordens" % rot, False)
            continue
        for nome in ("great_veins", "great_arteries"):
            k_pr = casca(composto(prontos, h_pr.mascara, nome),
                         h_pr.mascara, nome)
            k_lu = casca(composto(prontos, h_lu.mascara, nome),
                         h_lu.mascara, nome)
            checar(u"%s: `%s` = soma dos prontos − Heart_ai dos PRONTOS, sem "
                   u"casca" % (rot, nome), not k_pr.any(),
                   u"%.3f cm3" % G.volume_cm3(k_pr, g))
            checar(u"  isca: com o Heart_ai do LUMEN sobra casca (%.2f cm3)"
                   % G.volume_cm3(k_lu, g), k_lu.any())
    h = C.coracao_ai(prontos, g)
    ga = composto(prontos, h.mascara, "great_arteries")
    checar(u"a aorta DESCENDENTE fica nos grandes vasos (spec B3)",
           not (ex["desc"] & ~ga).any(),
           u"%d voxels fora" % int((ex["desc"] & ~ga).sum()))
    checar(u"  e o que esta no Heart_ai sai do composto",
           not (ga & h.mascara).any())
    checar(u"a entrada nao foi tocada", _assinatura(masks) == antes)


def teste_nunca_levanta():
    secao(u"nenhuma construcao levanta")
    g, masks, ex = montar()
    for rot, f in ((u"pericardio", C.pericardio_corrigido),
                   (u"Heart_ai", C.coracao_ai), (u"Bag_Bowel", C.bag_bowel)):
        try:
            r1 = f({}, g)
            r2 = f(masks, None)
            checar(u"%s: sem mascaras e sem grade devolve None" % rot,
                   r1 is None and r2 is None)
        except Exception as e:
            checar(u"%s nao levanta" % rot, False, repr(e))
    quebrado = dict(masks)
    quebrado["aorta"] = np.ones((3, 3, 3), bool)
    linhas = []
    try:
        r = C.coracao_ai(quebrado, g, log=linhas.append)
        checar(u"insumo de forma errada: None e uma linha de log",
               r is None and any(u"nao consegui" in l for l in linhas),
               str(linhas)[-1:])
    except Exception as e:
        checar(u"insumo de forma errada nao levanta", False, repr(e))
    linhas = []
    try:
        r = C.pericardio_corrigido({"pericardium": masks["pericardium"],
                                    "heart": np.ones((3, 3, 3), bool)}, g,
                                   log=linhas.append)
        checar(u"pericardio com insumo de forma errada: None e uma linha",
               r is None and any(u"nao consegui" in l for l in linhas),
               str(linhas)[-1:])
    except Exception as e:
        checar(u"pericardio com insumo de forma errada nao levanta", False,
               repr(e))


def teste_o_motor_e_chamado_e_nao_copiado():
    secao(u"o motor e chamado, e nao copiado")
    arv = ast.parse(io.open(_componentes.fonte("app/radai_constructs.py"),
                            encoding="utf-8").read())
    funcs = dict((n.name, n) for n in arv.body
                 if isinstance(n, ast.FunctionDef))

    def _chama_o_motor(no):
        return any(isinstance(n, ast.Call)
                   and getattr(n.func, "attr", "") ==
                   "coracao_de_radioterapia" for n in ast.walk(no))

    def _chamadas_locais(no):
        return set(getattr(n.func, "id", "") for n in ast.walk(no)
                   if isinstance(n, ast.Call)) & set(funcs)

    fn = funcs.get("coracao_ai")
    chama = fn is not None and (
        _chama_o_motor(fn) or any(_chama_o_motor(funcs[k])
                                  for k in _chamadas_locais(fn)))
    checar(u"`coracao_ai` chama `coracao_de_radioterapia` (direto ou por "
           u"uma funcao do modulo)", bool(chama))
    isca = ast.parse(u"def coracao_ai(m, g):\n    return _copia(m)\n"
                     u"def _copia(m):\n    return m\n")
    fi = dict((n.name, n) for n in isca.body)
    checar(u"  isca: uma copia que nao chama o motor e acusada",
           not (_chama_o_motor(fi["coracao_ai"])
                or _chama_o_motor(fi["_copia"])))
    definidos = set()
    for no in arv.body:
        if isinstance(no, ast.Assign):
            for alvo in no.targets:
                definidos.add(getattr(alvo, "id", ""))
    for nome in ("FECHAMENTO_PERICARDIO_MM", "VASOS_DO_CORACAO",
                 "FORA_DO_PERICARDIO", "COMPOSTOS", "COMPOSTOS_MENOS",
                 "MARGEM_OAR_MM"):
        checar(u"o modulo nao redefine `%s`" % nome, nome not in definidos)
    g, masks, ex = montar()
    parecida = dict((k, v) for k, v in masks.items()
                    if k != "abdominal_cavity")
    parecida["abdominal_cavity_ext"] = masks["abdominal_cavity"]
    checar(u"a cavidade e procurada por nome EXATO (um nome parecido nao "
           u"conta)", C.bag_bowel(parecida, g) is None)


def _chama_a_funcao_daqui(fn, nome):
    import inspect
    import textwrap
    try:
        arv = ast.parse(textwrap.dedent(inspect.getsource(fn)))
    except (OSError, TypeError, SyntaxError):
        return False
    return any(isinstance(n, ast.Attribute) and n.attr == nome
               for n in ast.walk(arv))


def teste_o_motor_registra_as_construcoes_daqui():
    secao(u"o motor registra as construcoes daqui, e as chama")
    g, masks, ex = montar()
    por_cod = dict((c["cod"], c) for c in M.CONSTRUCOES)
    for cod, nome in (("pericardio", "pericardio_corrigido"),
                      ("coracao", "coracao_ai"),
                      ("bag_bowel", "bag_bowel_declarada")):
        c = por_cod.get(cod)
        checar(u"`%s` esta no registro do motor" % cod, c is not None)
        if c is None:
            continue
        checar(u"  e o adaptador chama `radai_constructs.%s`" % nome,
               _chama_a_funcao_daqui(c["funcao"], nome))

    def _copia(masks, grade, log=None):
        return {"bag_bowel": masks["abdominal_cavity"]}
    checar(u"  isca: uma copia que nao chama a funcao daqui e acusada",
           not _chama_a_funcao_daqui(_copia, "bag_bowel"))
    s = M._construir_bag_bowel(masks, g)
    ref = C.bag_bowel_declarada(masks, g)
    checar(u"a Bag_Bowel do motor e a daqui (a receita declarada, com o "
           u"pancreas inteiro), voxel a voxel, com a descricao",
           ref is not None and "bag_bowel" in s
           and np.array_equal(np.asarray(s["bag_bowel"][0], bool),
                              ref.mascara)
           and s["bag_bowel"][1] == ref.descricao)
    peri = M._construir_pericardio(masks, g)
    ref_p = C.pericardio_corrigido(masks, g)
    checar(u"o pericardio do motor e o daqui",
           "pericardium" in peri and np.array_equal(
               np.asarray(peri["pericardium"][0], bool), ref_p.mascara))
    h = M._construir_coracao(masks, g, construidas={
        "pericardium": peri["pericardium"][0]})
    ref_h = C.coracao_ai(masks, g, pericardio=ref_p.mascara)
    checar(u"o Heart_ai do motor, com o pericardio que a construcao anterior "
           u"montou (`construidas`), e o daqui",
           "heart" in h and np.array_equal(np.asarray(h["heart"][0], bool),
                                           ref_h.mascara)
           and u"Inclui o pericardio" in h["heart"][1])
    sem = M._construir_coracao(
        dict((k, v) for k, v in masks.items() if k != "pericardium"), g)
    checar(u"sem a trunk_cavities, o Heart_ai do motor e a mesclagem de hoje "
           u"(Q35), e a descricao diz SEM pericardio",
           "heart" in sem and u"SEM pericardio" in sem["heart"][1])
    vazio = M._construir_bag_bowel(
        dict((k, v) for k, v in masks.items() if k != "abdominal_cavity"), g)
    checar(u"sem a cavidade, o adaptador devolve vazio COM o motivo "
           u"(`faltou`)", not vazio and vazio.faltou
           and u"trunk_cavities" in vazio.faltou[0], str(vazio.faltou))


def teste_o_heart_ai_da_v85():
    secao(u"v8.5: o Heart_ai pelo topo do apendice, com o derrame e sem "
          u"buraco por corte")
    g, masks, ex = montar()
    cor = masks["heart"]
    laa = G.expandir(masks["atrial_appendage_left"], 3.0, g)
    v = C._cm3(laa, g)
    checar(u"(fantoma) o apendice tem volume compativel (%.1f cm3)" % v,
           C.APENDICE_COMPATIVEL_CM3[0] <= v <= C.APENDICE_COMPATIVEL_CM3[1])
    m2 = dict(masks)
    m2["atrial_appendage_left"] = laa
    c = C.coracao_ai(m2, g)
    t_l = _topo(laa)
    checar(u"o limite superior e o topo do apendice: nada acima dele",
           c is not None and not c.mascara[t_l + 1:].any()
           and bool(cor[t_l + 1:].any()),
           u"topo do Heart_ai %s, do apendice %d" % (
               _topo(c.mascara) if c is not None else u"-", t_l))
    checar(u"  e a descricao diz o marco, com o volume do apendice",
           c is not None and u"topo do apendice atrial esquerdo (AtrialApp_L"
           in c.descricao, (c.descricao[-160:] if c is not None else u"-"))
    velho = C.APENDICE_COMPATIVEL_CM3
    C.APENDICE_COMPATIVEL_CM3 = (500.0, 600.0)
    try:
        ci = C.coracao_ai(m2, g)
    finally:
        C.APENDICE_COMPATIVEL_CM3 = velho
    checar(u"ISCA: com o apendice fora da faixa compativel, volta o limite de "
           u"antes (mais alto) e a descricao diz por que",
           ci is not None and bool(ci.mascara[t_l + 1:].any())
           and u"limite de antes" in ci.descricao)
    marco, pq = C.marco_pelo_apendice(laa, cor, g)
    checar(u"marco_pelo_apendice devolve o apendice compativel", marco is not None)
    alto = laa.copy()
    alto[_topo(cor) + 2:_topo(cor) + 4] = alto[t_l]
    _m, pq_alto = C.marco_pelo_apendice(alto, cor, g)
    checar(u"  e recusa o apendice cujo topo passa do coracao do modelo",
           _m is None and u"fora da altura" in pq_alto, pq_alto)
    _m2, pq_peq = C.marco_pelo_apendice(masks["atrial_appendage_left"]
                                        & (np.arange(NZ) < 50)[:, None, None],
                                        cor, g)
    checar(u"  e o apendice pequeno demais (sem volume compativel)",
           _m2 is None and u"fora de" in pq_peq, pq_peq)

    der = np.zeros_like(cor)
    zc = int(np.flatnonzero(cor.any(axis=(1, 2))).min()) + 3
    yy, xx = np.nonzero(cor[zc])
    der[zc:zc + 3, yy.min() - 8:yy.min() + 2, xx.min():xx.max()] = True
    m3 = dict(masks)
    m3["pericardial_effusion"] = der
    c3 = C.coracao_ai(m3, g)
    checar(u"o derrame pericardico entra no Heart_ai, e a descricao diz",
           c3 is not None and not (der & ~c3.mascara).any()
           and u"Inclui o derrame pericardico (PericardEff" in c3.descricao,
           (c3.descricao[-120:] if c3 is not None else u"-"))
    velho_d = C._derrame_pericardico
    C._derrame_pericardico = lambda mk, cru=None: None
    try:
        c3i = C.coracao_ai(m3, g)
    finally:
        C._derrame_pericardico = velho_d
    checar(u"ISCA: sem integrar, parte do derrame fica fora",
           c3i is not None and bool((der & ~c3i.mascara).any()))

    furado = c.mascara.copy()
    zf = (int(np.flatnonzero(furado.any(axis=(1, 2))).min())
          + int(np.flatnonzero(furado.any(axis=(1, 2))).max())) // 2
    yy, xx = np.nonzero(furado[zf])
    yc, xc = int(np.median(yy)), int(np.median(xx))
    furado[zf, yc - 2:yc + 3, xc - 2:xc + 3] = False
    ilha = np.zeros_like(furado)
    ilha[2:4, 5:8, 5:8] = True
    novo, _d, _i = M._acabamento_do_coracao("heart", furado | ilha, {}, g)
    checar(u"o acabamento preenche o buraco de cada corte",
           bool(novo[zf, yc, xc]) and not furado[zf, yc, xc])
    checar(u"  e deixa so o maior pedaco (sem a ilha)", not (novo & ilha).any())
    acima = np.zeros_like(furado)
    acima[_topo(furado) + 1:_topo(furado) + 3, yc, xc] = True
    dentro = np.zeros_like(furado)
    dentro[zf, yy.min() - 3:yy.min(), xc] = True
    novo2, _d, _i = M._acabamento_do_coracao(
        "heart", furado, {"pericardial_effusion": acima | dentro}, g)
    checar(u"  e devolve o derrame que a suavizacao tirou, sem passar do topo",
           not (dentro & ~novo2).any() and not (acima & novo2).any())


_FORMA_CP = (60, 80, 100)


def _cx(z0, z1, y0, y1, x0, x1, forma=_FORMA_CP):
    a = np.zeros(forma, bool)
    a[z0:z1, y0:y1, x0:x1] = True
    return a


def _laringe_do_fantoma():
    hioide = _cx(40, 43, 20, 30, 40, 60)
    tireoide = _cx(25, 42, 22, 34, 38, 62) & ~_cx(25, 42, 24, 34, 40, 60)
    cricoide = _cx(18, 26, 24, 36, 42, 58) & ~_cx(18, 26, 26, 34, 44, 56)
    ar = _cx(14, 40, 26, 32, 46, 54)
    hipofaringe = _cx(28, 44, 36, 42, 42, 58)
    return {"hyoid": hioide, "thyroid_cartilage": tireoide,
            "cricoid_cartilage": cricoide, "larynx_air": ar,
            "hypopharynx": hipofaringe}


def teste_a_laringe():
    secao(u"v8.7: Larynx_ai, do corte logo abaixo do hioide ao ultimo corte "
          u"da cricoide, somada e conectada")
    g = G.Grade((1.0, 1.0, 1.0))
    m = _laringe_do_fantoma()
    linhas = []
    c = C.laringe(dict(m), g, log=linhas.append)
    lar = np.asarray(c.mascara, bool) if c else None
    checar(u"a laringe sai", lar is not None and lar.any())
    if lar is None or not lar.any():
        return
    z = np.flatnonzero(lar.any(axis=(1, 2)))
    checar(u"o limite superior e o corte logo abaixo da borda inferior do "
           u"hioide (39)", int(z.max()) == 39, str((z.min(), z.max())))
    checar(u"  e o inferior, o ultimo corte com a cricoide (18): o ar abaixo "
           u"dele fica fora", int(z.min()) == 18 and not lar[:18].any())
    soma = (m["cricoid_cartilage"] | m["thyroid_cartilage"]
            | m["larynx_air"] | m["hypopharynx"])
    soma[:18] = False
    soma[40:] = False
    checar(u"  e leva as quatro partes inteiras dentro da faixa",
           not (soma & ~lar).any(), u"%d voxels" % int((soma & ~lar).sum()))
    checar(u"conectada: um volume (o fechamento une a hipofaringe a "
           u"cartilagem)", ndimage.label(lar)[1] == 1,
           str(ndimage.label(lar)[1]))
    checar(u"  e o espaco dentro do anel da cricoide entra (furo de cada "
           u"corte)", bool(lar[20, 33, 50]) and not soma[20, 33, 50])
    checar(u"o nome e Larynx_ai (<=16)", M.nome_clinico(C.CHAVE_LARINGE)
           == u"Larynx_ai", M.nome_clinico(C.CHAVE_LARINGE))
    checar(u"  e a descricao diz os marcos", u"hioide" in c.descricao
           and u"cricoide" in c.descricao, c.descricao[:160])
    velho = C.FECHAMENTO_DA_LARINGE_MM
    C.FECHAMENTO_DA_LARINGE_MM = 0.0
    try:
        ci = C.laringe(dict(m), g)
    finally:
        C.FECHAMENTO_DA_LARINGE_MM = velho
    checar(u"ISCA: sem conectar, a laringe sai em dois pedacos (a checagem "
           u"de um volume reprovaria)",
           ci and ndimage.label(np.asarray(ci.mascara, bool))[1] >= 2)
    sem = dict(m)
    del sem["hyoid"]
    cs = C.laringe(sem, g)
    checar(u"sem o hioide nao ha limite superior: nao sai, e diz por que",
           not cs and any(u"hioide" in f for f in (cs.faltou if cs is not None
                                                     else [])),
           str(cs.faltou if cs is not None else None))


def _mandibula_com_ramos(coronoide_alto=False):
    mand = np.zeros(_FORMA_CP, bool)
    for x0, x1 in ((70, 76), (24, 30)):
        mand[10:20, 10:40, x0:x1] = True
        mand[20:44, 30:46, x0:x1] = True
        mand[44:52, 30:35, x0:x1] = True
        mand[44:56, 40:46, x0:x1] = True
    mand[10:20, 10:16, 24:76] = True
    return mand


def teste_as_atms():
    secao(u"v8.7: TMJ_L_ai e TMJ_R_ai, o condilo do corte em que o ramo se "
          u"divide ao topo, com 1 mm em 3D")
    g = G.Grade((1.0, 1.0, 1.0))
    mand = _mandibula_com_ramos()
    linhas = []
    cs = C.atms({"mandible": mand}, g, log=linhas.append)
    for chave, x0, x1 in (("tmj_left", 70, 76), ("tmj_right", 24, 30)):
        c = cs.get(chave)
        atm = np.asarray(c.mascara, bool) if c else None
        checar(u"[%s] sai" % chave, atm is not None and atm.any())
        if atm is None or not atm.any():
            continue
        cond = _cx(44, 56, 40, 46, x0, x1)
        coro = _cx(44, 52, 30, 35, x0, x1)
        checar(u"[%s] leva o condilo inteiro, do corte da divisao (44) ao "
               u"topo (55)" % chave, not (cond & ~atm).any())
        checar(u"[%s]   e nada do coronoide" % chave,
               not (atm & coro).any(), u"%d voxels" % int((atm & coro).sum()))
        esperado = G.expandir(cond, 1.0, g)
        checar(u"[%s]   com 1 mm de margem em 3D (nem mais, nem menos)"
               % chave, np.array_equal(atm, esperado),
               u"%d de diferenca" % int((atm ^ esperado).sum()))
        checar(u"[%s]   e so do proprio lado" % chave,
               not atm[:, :, :50].any() if chave == "tmj_left"
               else not atm[:, :, 50:].any())
        checar(u"[%s] o nome tem ate 16 caracteres (%s)"
               % (chave, M.nome_clinico(chave)),
               M.nome_clinico(chave) in (u"TMJ_L_ai", u"TMJ_R_ai"))
    velho = C._mais_posterior
    C._mais_posterior = lambda comps: min(
        comps, key=lambda cc: float(np.nonzero(cc)[0].mean()))
    try:
        ci = C.atms({"mandible": mand}, g).get("tmj_left")
    finally:
        C._mais_posterior = velho
    checar(u"ISCA: escolhendo o contorno da frente, o coronoide entraria (a "
           u"checagem de cima reprovaria)",
           ci and bool((np.asarray(ci.mascara, bool)
                        & _cx(44, 52, 30, 35, 70, 76)).any()))
    sem_divisao = np.zeros(_FORMA_CP, bool)
    sem_divisao[10:56, 30:46, 70:76] = True
    sem_divisao[10:56, 30:46, 24:30] = True
    cn = C.atms({"mandible": sem_divisao}, g).get("tmj_left")
    checar(u"sem o ramo dividido em dois contornos, nao sai, e diz por que",
           not cn and any(u"divide" in f for f in cn.faltou), str(cn.faltou))


_CRANIO_DA_ATM = (56, 60, 20, 66, 18, 80)
_GIRO_DA_CABECA = -20.0


def _girada(m, graus=_GIRO_DA_CABECA):
    return ndimage.rotate(np.asarray(m, np.uint8), graus, axes=(1, 2),
                          reshape=False, order=0).astype(bool)


def _atms_pela_caixa(masks, g):
    velho = getattr(C, "ANCORAS_DO_PLANO_MEDIO_DA_ATM", ())
    C.ANCORAS_DO_PLANO_MEDIO_DA_ATM = ()
    try:
        return C.atms(masks, g)
    finally:
        C.ANCORAS_DO_PLANO_MEDIO_DA_ATM = velho


def _da(cs, chave):
    c = cs.get(chave)
    return np.asarray(c.mascara, bool) if c else None


def _resto_da_mandibulectomia():
    resto = _mandibula_com_ramos()
    resto[:, :, :70] = False
    return resto


def teste_o_plano_medio_da_atm():
    secao(u"v8.7: o plano medio da ATM pelo centro de uma estrutura mediana "
          u"(cranio, encefalo, C1, C2); o centro da caixa da mandibula so "
          u"como recuo")
    g = G.Grade((1.0, 1.0, 1.0))
    mand = _mandibula_com_ramos()
    cranio = _cx(*_CRANIO_DA_ATM)
    cond_e, cond_d = _cx(44, 56, 40, 46, 70, 76), _cx(44, 56, 40, 46, 24, 30)

    linhas = []
    novo = C.atms({"mandible": mand, "skull": cranio}, g, log=linhas.append)
    velho = _atms_pela_caixa({"mandible": mand, "skull": cranio}, g)
    for chave in ("tmj_left", "tmj_right"):
        a, b = _da(novo, chave), _da(velho, chave)
        checar(u"[%s] mandibula inteira, cabeca reta: o mesmo, voxel a voxel, "
               u"que pelo centro da caixa (o centro do cranio fica a 1 voxel "
               u"dele)" % chave,
               a is not None and b is not None and np.array_equal(a, b))
    checar(u"o log diz que o plano medio passou pelo centro do cranio",
           any(l.startswith(u"TMJ:") and u"(skull)" in l for l in linhas),
           str(linhas[:2]))

    resto = _resto_da_mandibulectomia()
    linhas = []
    cs = C.atms({"mandible": resto, "skull": cranio}, g, log=linhas.append)
    tl, tr = _da(cs, "tmj_left"), _da(cs, "tmj_right")
    checar(u"mandibulectomia (sobra o ramo esquerdo): a TMJ_L e o condilo "
           u"esquerdo inteiro com 1 mm, como na mandibula inteira",
           tl is not None and np.array_equal(tl, G.expandir(cond_e, 1.0, g)))
    checar(u"  e a TMJ_R nao sai, e diz que nao ha mandibula do lado direito",
           tr is None and any(u"TMJ_R" in f and u"sem mandibula" in f
                              for f in cs["tmj_right"].faltou),
           str(cs["tmj_right"].faltou))
    tri = _da(_atms_pela_caixa({"mandible": resto, "skull": cranio}, g),
              "tmj_right")
    checar(u"ISCA: pelo centro da caixa (a regra antiga) a TMJ_R sairia no "
           u"condilo ESQUERDO (a checagem de cima reprovaria)",
           tri is not None and bool((tri & cond_e).any())
           and not tri[:, :, :50].any())

    mand_g, cranio_g = _girada(mand), _girada(cranio)
    novo = C.atms({"mandible": mand_g, "skull": cranio_g}, g)
    velho = _atms_pela_caixa({"mandible": mand_g, "skull": cranio_g}, g)
    for chave, cond in (("tmj_left", cond_e), ("tmj_right", cond_d)):
        a, b = _da(novo, chave), _da(velho, chave)
        checar(u"[%s] cabeca girada %g graus, mandibula inteira: o condilo "
               u"girado do proprio lado com 1 mm, e o mesmo que pela caixa"
               % (chave, _GIRO_DA_CABECA),
               a is not None and b is not None and np.array_equal(a, b)
               and np.array_equal(a, G.expandir(_girada(cond), 1.0, g)))

    resto_g = _girada(resto)
    cs = C.atms({"mandible": resto_g, "skull": cranio_g}, g)
    tl, tr = _da(cs, "tmj_left"), _da(cs, "tmj_right")
    checar(u"cabeca girada e mandibulectomia: a TMJ_L e o condilo esquerdo "
           u"girado com 1 mm, e a TMJ_R nao sai",
           tl is not None and tr is None
           and np.array_equal(tl, G.expandir(_girada(cond_e), 1.0, g)))
    ci = _atms_pela_caixa({"mandible": resto_g, "skull": cranio_g}, g)
    tli, tri = _da(ci, "tmj_left"), _da(ci, "tmj_right")
    checar(u"ISCA: pela caixa, o condilo esquerdo inteiro sairia como TMJ_R, "
           u"e a TMJ_L nem sairia (a checagem de cima reprovaria)",
           tli is None and tri is not None
           and not (_girada(cond_e) & ~tri).any())

    plano = getattr(C, "plano_medio_da_atm", None)
    checar(u"o plano medio e uma funcao so (radai_constructs.plano_medio_da_"
           u"atm)", callable(plano))
    if not callable(plano):
        return
    ancoras = {"skull": cranio, "brain": _cx(56, 60, 25, 60, 21, 80),
               "vertebrae_C1": _cx(30, 40, 50, 60, 42, 60),
               "vertebrae_C2": _cx(20, 30, 50, 60, 43, 62)}
    esperado = (("skull", 48.5), ("brain", 50.0), ("vertebrae_C1", 50.5),
                ("vertebrae_C2", 52.0))
    m = {"mandible": mand}
    m.update(ancoras)
    for nome, x in esperado:
        r = plano(m, mand, g)
        checar(u"a ancora e %s quando e a primeira que existe (x=%g)"
               % (nome, x), r[1] == nome and abs(r[0] - x) < 1e-9, str(r))
        del m[nome]
    r = plano(m, mand, g)
    checar(u"sem cranio, encefalo, C1 nem C2, nao ha ancora (o recuo e a "
           u"caixa)", r == (None, None), str(r))
    linhas = []
    C.atms({"mandible": mand}, g, log=linhas.append)
    checar(u"  e o log diz que o plano passou pelo centro da caixa da "
           u"mandibula", any(l.startswith(u"TMJ:") and u"caixa da mandibula"
                              in l for l in linhas), str(linhas[:2]))
    r = plano({"mandible": mand}, mand, g, cru={"skull": cranio})
    checar(u"o cranio que so esta no cru tambem ancora",
           r[1] == "skull" and abs(r[0] - 48.5) < 1e-9, str(r))
    r = plano({"mandible": mand, "skull": np.ones((5, 5, 5), bool),
               "brain": ancoras["brain"]}, mand, g)
    checar(u"ancora em outra grade fica de fora (vale a seguinte)",
           r[1] == "brain", str(r))
    junto = cranio | resto
    r = plano({"mandible": resto, "skull": junto}, resto, g)
    xs = np.arange(junto.shape[2])
    ingenuo = float((junto.sum(axis=(0, 1)) * xs).sum()) / junto.sum()
    checar(u"o cranio da base que contem a mandibula: o centro sai sem ela "
           u"(48,5; com ela seria %.1f, puxado para o lado que sobrou)"
           % ingenuo, r[1] == "skull" and abs(r[0] - 48.5) < 1e-9
           and ingenuo - r[0] > 2.0, str(r))


def teste_os_pulmoes_somados():
    secao(u"v8.7: Lungs_ai e a soma dos pulmoes")
    g = G.Grade((1.0, 1.0, 1.0))
    pe = _cx(10, 40, 20, 60, 60, 90)
    pd = _cx(10, 40, 20, 60, 10, 40)
    c = C.pulmoes({"lung_left": pe, "lung_right": pd}, g)
    checar(u"Lungs_ai = Lung_L + Lung_R",
           c and np.array_equal(np.asarray(c.mascara, bool), pe | pd))
    c1 = C.pulmoes({"lung_left": pe}, g)
    checar(u"  com um pulmao so, e esse, e a descricao diz",
           c1 and np.array_equal(np.asarray(c1.mascara, bool), pe)
           and u"so o" in c1.descricao, c1.descricao if c1 else u"-")
    checar(u"  e o nome e Lungs_ai", M.nome_clinico(C.CHAVE_PULMOES)
           == u"Lungs_ai")
    cz = C.pulmoes({}, g)
    checar(u"sem pulmao nao sai", not cz)


def _mandibula_com_dente():
    mand = _cx(10, 20, 10, 40, 24, 76) & ~_cx(10, 20, 16, 40, 30, 70)
    canal = _cx(12, 16, 25, 30, 71, 74)
    alveolo = _cx(16, 20, 20, 26, 71, 75)
    mand = mand & ~canal & ~alveolo
    raiz = _cx(16, 20, 21, 25, 72, 74)
    coroa = _cx(20, 24, 20, 26, 71, 75)
    return mand, raiz | coroa, canal, alveolo


def teste_a_mandibula_cheia():
    secao(u"v8.7: a mandibula cheia, com os dentes inferiores por cima, e a "
          u"suavizacao que nunca perde area")
    g = G.Grade((1.0, 1.0, 1.0))
    mand, dentes, canal, alveolo = _mandibula_com_dente()
    c = C.mandibula_cheia({"mandible": mand, "teeth_lower": dentes}, g)
    m = np.asarray(c.mascara, bool) if c else None
    checar(u"sai, com a mandibula e os dentes inteiros",
           m is not None and not ((mand | dentes) & ~m).any())
    if m is None:
        return
    checar(u"  o canal fechado e preenchido", not (canal & ~m).any())
    checar(u"  e o espaco entre a raiz e o alveolo tambem",
           not (alveolo & ~m).any(), u"%d voxels" % int((alveolo & ~m).sum()))
    checar(u"  e a descricao diz que inclui os dentes",
           u"dentes inferiores" in c.descricao, c.descricao[:200])
    c2 = C.mandibula_cheia({"mandible": mand}, g)
    checar(u"sem os dentes carregados, a mandibula sai sem eles e diz",
           c2 and not (np.asarray(c2.mascara, bool) & _cx(20, 24, 20, 26, 71,
                                                           75)).any()
           and u"sem os dentes" in c2.descricao)
    spec = dict(M.CONSTRUCOES_POR_SAIDA()["mandible"])
    bloco = _cx(10, 30, 20, 50, 30, 70)
    masks = {"mandible": bloco.copy()}
    M._suavizar_construcoes(masks, g, 1.5, {"mandible": spec}, [], [])
    fim = np.asarray(masks["mandible"], bool)
    checar(u"a segunda passada suaviza sem perder area (a uniao da suavizada "
           u"com a cheia)", not (bloco & ~fim).any(),
           u"%d voxels perdidos" % int((bloco & ~fim).sum()))
    spec_i = dict(spec)
    spec_i.pop("sem_perder_area", None)
    masks_i = {"mandible": bloco.copy()}
    M._suavizar_construcoes(masks_i, g, 1.5, {"mandible": spec_i}, [], [])
    checar(u"ISCA: sem a uniao, a suavizacao come a quina (a checagem de "
           u"cima reprovaria)",
           bool((bloco & ~np.asarray(masks_i["mandible"], bool)).any()))


def main():
    print(u"=" * 68)
    print(u"test_constructs | pericardio, Heart_ai, Bag_Bowel e vasos (v8.2)")
    print(u"=" * 68)
    for t in (teste_os_nomes,
              teste_o_pericardio_corrigido,
              teste_o_heart_ai,
              teste_o_heart_ai_da_v85,
              teste_o_vocabulario_do_full,
              teste_a_bag_bowel,
              teste_os_vasos_tem_uma_fonte_so,
              teste_a_ordem_dos_vasos_e_a_casca,
              teste_nunca_levanta,
              teste_o_motor_e_chamado_e_nao_copiado,
              teste_o_motor_registra_as_construcoes_daqui,
              teste_a_laringe,
              teste_as_atms,
              teste_o_plano_medio_da_atm,
              teste_os_pulmoes_somados,
              teste_a_mandibula_cheia):
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
