# -*- coding: utf-8 -*-
import io
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "app"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
import _cleanup
_cleanup.adotar_prefixo('radai_ac_sust')

import radai_geom
import radai_plausibility as S
import _componentes

_R = []


def checar(nome, ok, detalhe=""):
    _R.append((nome, bool(ok), detalhe))
    print("  %s  %s%s" % ("OK   " if ok else "FALHA", nome,
                          ("  [%s]" % detalhe) if detalhe else ""))
    return bool(ok)


def secao(t):
    print(u"\n  ── %s ─────────────────────────" % t)


ESP = (3.75, 0.9, 0.9)
SH = (60, 120, 120)
C = (30, 60, 60)
G = radai_geom.Grade(spacing_zyx=ESP)
RNG = np.random.default_rng(20260903)


def elipsoide(raios_mm, centro=C):
    zz, yy, xx = np.ogrid[:SH[0], :SH[1], :SH[2]]
    return ((((zz - centro[0]) * ESP[0]) / raios_mm[0]) ** 2 +
            (((yy - centro[1]) * ESP[1]) / raios_mm[1]) ** 2 +
            (((xx - centro[2]) * ESP[2]) / raios_mm[2]) ** 2) <= 1.0


RIM = elipsoide((55.0, 30.0, 28.0))
GORDURA = RNG.normal(-95.0, 22.0, SH)


def volume_com(mask, media, dp=18.0):
    return np.where(mask, RNG.normal(media, dp, SH), GORDURA)


def julgar(mask, hu, nome="kidney_right"):
    return S.conferir_sustentacao({nome: mask}, G, hu)[nome]


def teste_pega_gordura_e_ar():
    secao(u"o que ela pega")
    r = julgar(RIM, GORDURA.copy())
    checar(u"leito de nefrectomia (só gordura) é marcado",
           r["cod"] == "interior_fora_da_janela",
           u"saiu %s, mediana %s HU" % (r["cod"], r.get("mediana_hu")))
    checar(u"e a mediana medida é de gordura",
           r.get("mediana_hu") is not None and r["mediana_hu"] < -50)

    r = julgar(RIM, volume_com(RIM, -780.0, 60.0))
    checar(u"interior de ar é marcado",
           r["cod"] == "interior_fora_da_janela", u"saiu " + r["cod"])

    r = julgar(RIM, volume_com(RIM, 35.0))
    checar(u"rim presente com contorno certo NÃO é marcado",
           r["cod"] == "sustentada", u"saiu " + r["cod"])


def teste_orgao_atipico_nao_cai():
    secao(u"órgão presente e atípico não pode ser marcado")
    for nome, media in ((u"esteatose grave (0 HU)", 0.0),
                        (u"esteatose muito grave (−15 HU)", -15.0),
                        (u"hidronefrose (8 HU)", 8.0),
                        (u"rim policístico (10 HU)", 10.0),
                        (u"vesícula hidrópica (5 HU)", 5.0)):
        r = julgar(RIM, volume_com(RIM, media, 14.0))
        checar(u"%s continua sustentada" % nome, r["cod"] == "sustentada",
               u"saiu %s, fração %s" % (r["cod"], r.get("fracao")))


def teste_inflado_nao_e_confundido_com_leito():
    secao(u"contorno inflado não é lido como ausência")
    from scipy import ndimage as ndi
    d = ndi.distance_transform_edt(~RIM, sampling=ESP)
    inflado = (d <= 20.0)
    hu = volume_com(RIM, 35.0)
    r = julgar(inflado, hu)
    checar(u"rim presente inflado 20 mm sai como `super_segmentada`",
           r["cod"] == "super_segmentada",
           u"saiu %s (mediana %s, fração %s)"
           % (r["cod"], r.get("mediana_hu"), r.get("fracao")))
    checar(u"e a frase fala de contorno, não de ausência",
           "grande demais" in r.get("frase", ""))
    checar(u"a densidade sozinha NÃO os separaria",
           r.get("mediana_hu") is not None and r["mediana_hu"] < -50,
           u"mediana %s HU, igual à de um leito" % r.get("mediana_hu"))
    perfil = S._perfil_de_erosao(inflado, hu, G, S.JANELA_PARENQUIMA_HU)
    checar(u"a sonda alcança o parênquima sob 20 mm de inflação",
           perfil is not None and (perfil[-1] - perfil[0]) >= 0.25,
           u"perfil %s" % (perfil,))
    perfil_leito = S._perfil_de_erosao(RIM, GORDURA.copy(), G,
                                       S.JANELA_PARENQUIMA_HU)
    checar(u"e no leito ela fica plana",
           perfil_leito is not None
           and (perfil_leito[-1] - perfil_leito[0]) < 0.25,
           u"perfil %s" % (perfil_leito,))


def teste_a_cobertura_e_verdadeira():
    secao(u"a cobertura declarada é verdadeira")
    for nome, media in ((u"leito com seroma (12 HU)", 12.0),
                        (u"leito com alça e contraste (60 HU)", 60.0),
                        (u"psoas ocupando o leito (48 HU)", 48.0)):
        r = julgar(RIM, volume_com(RIM, media, 16.0))
        checar(u"%s NÃO é pego — e a cobertura diz isso" % nome,
               r["cod"] == "sustentada", u"saiu " + r["cod"])
    for palavra in (u"gordura", u"AR", u"seroma", u"grande demais"):
        checar(u"a COBERTURA nomeia «%s»" % palavra,
               palavra.lower() in S.COBERTURA.lower())


def teste_o_que_nao_e_julgado():
    secao(u"o que fica de fora, e por quê")
    lau = S.conferir_sustentacao({"rib_left_4": RIM, "aorta": RIM,
                                  "vertebrae_T8": RIM}, G, GORDURA.copy())
    checar(u"estrutura sem janela declarada não é julgada nem citada",
           lau == {}, repr(lau)[:80])

    for oca in ("colon", "stomach", "urinary_bladder", "esophagus",
                "small_bowel", "duodenum", "lung_left", "trachea"):
        r = S.conferir_sustentacao({oca: RIM}, G, GORDURA.copy())[oca]
        checar(u"`%s` é declarada e recusada" % oca,
               r["cod"] == "sem_janela_declarada", u"saiu " + r["cod"])
    checar(u"e as recusadas estão no dicionário, com valor None",
           all(S.JANELAS_HU.get(k) is None for k in
               ("colon", "stomach", "urinary_bladder", "lung_right")))

    r = julgar(elipsoide((1.0, 1.2, 20.0)), volume_com(RIM, 35.0))
    checar(u"lâmina sem interior sai como `interior_insuficiente`",
           r["cod"] == "interior_insuficiente", u"saiu " + r["cod"])
    checar(u"e ela não recebe veredito nenhum",
           r.get("mediana_hu") is None and r.get("fracao") is None)


def teste_a_fronteira():
    secao(u"a fronteira: mede a nossa saída, não afirma sobre o paciente")
    try:
        S.conferir_ancoragem(["kidney_left"], {"kidney_right": RIM})
        checar(u"a ancoragem recusa nome que nenhum motor desenhou", False)
    except ValueError:
        checar(u"a ancoragem recusa nome que nenhum motor desenhou", True)
    checar(u"e aceita o que foi desenhado",
           S.conferir_ancoragem(["kidney_right"], {"kidney_right": RIM}))

    try:
        S.frase("orgao_ausente")
        checar(u"o vocabulário recusa código de fora", False)
    except ValueError:
        checar(u"o vocabulário recusa código de fora", True)
    checar(u"e toda frase entregue sai do dicionário fechado",
           all(S.frase(c) == S.MOTIVOS[c] for c in S.MOTIVOS))

    junto = u" ".join(S.MOTIVOS.values()).lower() + u" " + S.COBERTURA.lower()
    for proibida in (u"ausente", u"ausência", u"removido", u"nefrectomia",
                     u"tumor", u"lesão", u"neoplasia", u"maligno",
                     u"cisto", u"não há"):
        checar(u"nenhuma frase diz «%s»" % proibida, proibida not in junto)


def teste_marca_e_nao_retira():
    secao(u"ela marca, e entrega assim mesmo")
    masks = {"kidney_right": RIM, "kidney_left": RIM, "spleen": RIM}
    antes = dict((k, int(v.sum())) for k, v in masks.items())
    lau = S.conferir_sustentacao(masks, G, GORDURA.copy())
    checar(u"as três foram marcadas",
           sum(1 for r in lau.values()
               if r["cod"] == "interior_fora_da_janela") == 3)
    checar(u"e nenhuma máscara foi tocada",
           all(int(masks[k].sum()) == antes[k] for k in antes))
    checar(u"nem uma chave foi removida", set(masks) == set(antes))

    res = S.resumo(lau)
    checar(u"o resumo lista as marcadas", len(res["marcadas"]) == 3)
    checar(u"e leva a cobertura junto", res["cobertura"] == S.COBERTURA)

    txt = io.open(_componentes.fonte("app/radai_plausibility.py"),
                  encoding="utf-8").read()
    checar(u"o módulo não tem chave de retenção",
           "RETER_NAO_SUSTENTADA" not in txt and "del masks" not in txt)


def teste_nunca_levanta():
    secao(u"ela nunca derruba a montagem do RTSTRUCT")
    for desc, args in (
            (u"sem grade", ({"kidney_right": RIM}, None, GORDURA)),
            (u"sem volume", ({"kidney_right": RIM}, G, None)),
            (u"máscara vazia", ({"kidney_right": np.zeros(SH, bool)}, G,
                                GORDURA)),
            (u"formas diferentes", ({"kidney_right": np.zeros((4, 4, 4), bool)},
                                    G, GORDURA)),
            (u"dicionário vazio", ({}, G, GORDURA))):
        try:
            S.conferir_sustentacao(*args)
            checar(u"%s: responde sem levantar" % desc, True)
        except Exception as e:
            checar(u"%s: responde sem levantar" % desc, False,
                   "%s: %s" % (type(e).__name__, e))

    try:
        S.conferir_ancoragem(["nao_desenhado"], {"kidney_right": RIM})
        checar(u"a trava da regra 6 SOBE, e não é engolida", False)
    except ValueError:
        checar(u"a trava da regra 6 SOBE, e não é engolida", True)


def teste_a_ancoragem_guarda_o_que_SAI():
    secao(u"a ancoragem alcança o caminho de execução")

    class SoDeSaida(dict):
        def __contains__(self, k):
            return False

    m = SoDeSaida({"kidney_right": RIM})
    try:
        S.conferir_sustentacao(m, G, GORDURA.copy())
        checar(u"a trava está no caminho de execução, e não só no arquivo",
               False, u"`conferir_sustentacao` não levantou")
    except ValueError as e:
        checar(u"a trava está no caminho de execução, e não só no arquivo",
               True, str(e)[:56])

    fonte = io.open(_componentes.fonte("app/radai_plausibility.py"),
                    encoding="utf-8").read()
    alvo = u"        conferir_ancoragem("
    i = fonte.find(alvo)
    checar(u"achei a chamada da ancoragem na fonte", i > 0)
    if i > 0:
        injetado = (fonte[:i] +
                    u'        laudo["nome_que_nenhum_motor_desenhou"] = '
                    u'{"cod": "sustentada", "frase": ""}\n' + fonte[i:])
        ns = {"__name__": "radai_sustentacao_injetado"}
        try:
            exec(compile(injetado, "<injetado>", "exec"), ns)
            ns["conferir_sustentacao"]({"kidney_right": RIM}, G,
                                       GORDURA.copy())
            checar(u"nome fabricado no laudo faz a trava levantar", False,
                   u"a ancoragem não olha o que a função DEVOLVE")
        except ValueError as e:
            checar(u"nome fabricado no laudo faz a trava levantar", True,
                   str(e)[:56])

    codigo = u"\n".join(l for l in fonte.splitlines()
                        if not l.lstrip().startswith(u"#"))
    checar(u"a chamada ancora `laudo`, que é o que a função devolve",
           u"conferir_ancoragem(list(laudo), masks)" in codigo)
    checar(u"e não há mais lista intermediária para ancorar",
           u"julgados" not in codigo,
           u"lista alimentada das chaves de `masks` é sempre subconjunto")


def teste_o_texto_chega_legivel_no_eclipse():
    secao(u"o texto atravessa a tabela do RTSTRUCT sem virar `?`")
    import engine
    for cod, texto in list(S.MOTIVOS.items()) + [("COBERTURA", S.COBERTURA)]:
        saiu = engine._para_dicom(texto)
        checar(u"`%s` atravessa o latin-1" % cod,
               "?" not in saiu and saiu.encode("latin-1", "strict"),
               saiu[-40:])
    _cob = engine._para_dicom(S.COBERTURA)
    checar(u"e o acento vira a letra sem acento, e o texto sai ASCII",
           u"compativel" in _cob and u"orgao" in _cob and _cob.isascii(),
           _cob[-40:])
    checar(u"o travessão vira hífen, e não some",
           "-" in engine._para_dicom(u"a — b"))
    mt = io.open(_componentes.fonte("app/engine.py"), encoding="utf-8").read()
    checar(u"e `build_rtstruct` escreve por ela",
           u"o.ROIObservationDescription = _para_dicom(" in mt)


def teste_a_medida_viaja_com_a_frase():
    secao(u"a medida viaja junto com a frase")
    mt = io.open(_componentes.fonte("app/engine.py"), encoding="utf-8").read()
    i = mt.find(u'o.ROIObservationDescription = _para_dicom(')
    trecho = mt[max(0, i - 900):i + 300] if i > 0 else u""
    for peca in (u"mediana %s HU", u"dentro da janela declarada",
                 u'_r["mediana_hu"]', u'_r.get("fracao")',
                 u'_r.get("voxels")'):
        checar(u"o texto leva «%s»" % peca[:34], peca in trecho)
    checar(u"e a cobertura continua junto",
           u"radai_plausibility.COBERTURA" in trecho)


def teste_fora_da_tc_ela_nao_julga():
    secao(u"fora da TC ela não julga")
    hu = GORDURA.copy()
    d = []
    lau = S.conferir_sustentacao({"kidney_right": RIM}, G, hu, log=d.append,
                                 modalidade="MR")
    checar(u"numa RM o laudo sai VAZIO", lau == {}, str(lau)[:80])
    checar(u"  e o log diz que não rodou, e por quê",
           any(u"nao rodou" in m and u"MR" in m for m in d), u" | ".join(d))
    d2 = []
    lau2 = S.conferir_sustentacao({"kidney_right": RIM}, G, hu,
                                  log=d2.append, modalidade="CT")
    checar(u"ISCA: o mesmo rim, declarado TC, é julgado e marcado",
           (lau2.get("kidney_right") or {}).get("cod")
           in ("interior_fora_da_janela", "super_segmentada", "duvidosa"),
           str(lau2.get("kidney_right"))[:100])
    checar(u"sem `modalidade`, o contrato de antes (quem chama sabe que é TC)",
           S.conferir_sustentacao({"kidney_right": RIM}, G, hu)
           .get("kidney_right", {}).get("cod") == (lau2.get("kidney_right")
                                                   or {}).get("cod"))


def _medir_de_antes(mask, volume_hu, grade, janela=None):
    from scipy import ndimage as ndi
    fora = {"mediana": None, "fracao": None, "voxels": 0,
            "cod": "interior_insuficiente"}
    m = np.asarray(mask, bool)
    hu = np.asarray(volume_hu)
    if m.shape != hu.shape or not m.any():
        return fora
    esp = tuple(abs(float(v)) for v in grade.spacing)
    dist = ndi.distance_transform_edt(m, sampling=esp)
    interior = dist >= float(S.EROSAO_INTERIOR_MM)
    n = int(interior.sum())
    fora["voxels"] = n
    if n < S.INTERIOR_MINIMO_VOXELS:
        return fora
    vals = hu[interior].astype(float)
    lo, hi = janela or S.JANELA_PARENQUIMA_HU
    fora["mediana"] = float(np.median(vals))
    fora["fracao"] = float(((vals >= lo) & (vals <= hi)).mean())
    fora["cod"] = None
    return fora


def _perfil_de_antes(mask, volume_hu, grade, janela):
    from scipy import ndimage as ndi
    m = np.asarray(mask, bool)
    hu = np.asarray(volume_hu)
    esp = tuple(abs(float(v)) for v in grade.spacing)
    dist = ndi.distance_transform_edt(m, sampling=esp)
    rmax = float(dist.max())
    if rmax <= S.EROSAO_INTERIOR_MM:
        return None
    lo, hi = janela
    fracs = []
    for f in (0.15, 0.45, 0.75):
        mm = max(S.EROSAO_INTERIOR_MM, rmax * f)
        dentro = dist >= mm
        if int(dentro.sum()) < S.INTERIOR_MINIMO_VOXELS:
            break
        v = hu[dentro].astype(float)
        fracs.append(float(((v >= lo) & (v <= hi)).mean()))
    if len(fracs) < 2:
        return None
    return fracs


def _cuboide_com_casca_de_gordura():
    from scipy import ndimage as ndi
    m = np.zeros(SH, bool)
    m[20:40, 30:90, 30:90] = True
    d = ndi.distance_transform_edt(m, sampling=ESP)
    hu = np.where(m, np.where(d < 3.0, -110.0, 40.0), -95.0)
    return m, hu


def teste_a_medida_na_caixa_e_a_do_volume():
    secao(u"a medida na caixa é a medida do volume (spec F3)")
    from scipy import ndimage as ndi
    d = ndi.distance_transform_edt(~RIM, sampling=ESP)
    casos = [
        (u"leito", RIM, GORDURA.copy()),
        (u"ar", RIM, volume_com(RIM, -780.0, 60.0)),
        (u"rim presente", RIM, volume_com(RIM, 35.0)),
        (u"esteatose", RIM, volume_com(RIM, -15.0, 14.0)),
        (u"inflado 20 mm", d <= 20.0, volume_com(RIM, 35.0)),
        (u"inflado 6 mm", d <= 6.0, volume_com(RIM, 35.0)),
    ]
    borda = np.zeros(SH, bool)
    borda[0:12, 0:40, 80:120] = True
    casos.append((u"na borda do volume", borda, volume_com(borda, 20.0)))
    casos.append((u"cuboide com casca",) + _cuboide_com_casca_de_gordura())
    import radai_geom
    difere = []
    for nome, m, hu in casos:
        j = S.JANELA_PARENQUIMA_HU
        if S.medir(m, hu, G, j) != _medir_de_antes(m, hu, G, j):
            difere.append(nome + u" (medir)")
        if S._perfil_de_erosao(m, hu, G, j) != _perfil_de_antes(m, hu, G, j):
            difere.append(nome + u" (perfil)")
        masks = {"kidney_right": m, "liver": m}
        rapido = S.conferir_sustentacao(masks, G, hu)
        lento = S.conferir_sustentacao(
            masks, G, hu, caixas=radai_geom.Caixas(masks, folga=None))
        if rapido != lento:
            difere.append(nome + u" (laudo)")
    checar(u"medir, perfil e laudo iguais ao de antes em %d casos"
           % len(casos), not difere, u", ".join(difere))
    cods = set(S.conferir_sustentacao({"kidney_right": m}, G, hu)
               ["kidney_right"]["cod"] for _n, m, hu in casos)
    checar(u"  e os casos cobrem sustentada, fora da janela e super-segmentada",
           {"sustentada", "interior_fora_da_janela",
            "super_segmentada"} <= cods, str(sorted(cods)))
    m, hu = _cuboide_com_casca_de_gordura()
    masks = {"kidney_right": m}
    certo = S.conferir_sustentacao(masks, G, hu)["kidney_right"]
    sem_folga = S.conferir_sustentacao(
        masks, G, hu, caixas=radai_geom.Caixas(masks, folga=0))["kidney_right"]
    checar(u"ISCA: sem o voxel de fundo em volta, a medida MUDA",
           certo != sem_folga,
           u"certo %s/%s, sem folga %s/%s" % (
               certo.get("fracao"), certo.get("voxels"),
               sem_folga.get("fracao"), sem_folga.get("voxels")))


def main():
    print("=" * 70)
    print(u" a densidade do interior — o que ela mede, e o que ela não diz")
    print("=" * 70)
    for t in (teste_pega_gordura_e_ar, teste_orgao_atipico_nao_cai,
              teste_inflado_nao_e_confundido_com_leito,
              teste_a_cobertura_e_verdadeira, teste_o_que_nao_e_julgado,
              teste_a_fronteira, teste_marca_e_nao_retira,
              teste_nunca_levanta, teste_a_ancoragem_guarda_o_que_SAI,
              teste_o_texto_chega_legivel_no_eclipse,
              teste_a_medida_viaja_com_a_frase,
              teste_fora_da_tc_ela_nao_julga,
              teste_a_medida_na_caixa_e_a_do_volume):
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
