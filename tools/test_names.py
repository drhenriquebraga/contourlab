# -*- coding: utf-8 -*-
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
os.environ["RADAI_CALIB_DIR"] = tempfile.mkdtemp(prefix="radai_ac_nomes_")
os.environ["TOTALSEG_HOME_DIR"] = tempfile.mkdtemp(prefix="radai_tshome_nomes_")
import _cleanup
_cleanup.adotar_prefixo("radai_ac_nomes_")
_cleanup.adotar_prefixo("radai_tshome_nomes_")

import engine as E
import radai_names as N
import radai_plausibility as P

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


CRUS_FORA_DO_MAPA = (
    "clavicula_left", "clavicula_right", "scapula_left", "scapula_right",
    "humerus_left", "humerus_right", "autochthon_left", "autochthon_right",
    "anterior_scalene_left", "platysma_left", "sternocleidomastoid_left",
    "trapezius_left", "levator_scapulae_left", "prevertebral_left",
    "sterno_thyroid_left", "thyrohyoid_left",
    "breast",
    "pectoralis_major_left", "latissimus_dorsi_left",
    "serratus_anterior_left",
    "rectus_abdominis_left", "external_oblique_left",
    "internal_oblique_left", "erector_spinae_left",
    "transversospinalis_left", "psoas_major_left",
    "quadratus_lumborum_left", "trapezius_right",
)


def vocabulario_do_full():
    nomes = set(E.TS_MAP) | set(E.COMPOSTOS) | set(E.CONSTRUCOES_POR_SAIDA())
    nomes.add(N.CHAVE_DO_CORACAO_DO_MODELO)
    for am in list(E.TS_MAP):
        nomes.update(N.crus_de(am))
    nomes.update(CRUS_FORA_DO_MAPA)
    nomes.update(getattr(E, "CHAVES_GLANDULA_POR_LADO", {}).values())
    return sorted(nomes)


def _consultas():
    return {
        "suavizacao (SUAVIZACAO)": lambda n: E.suavizacao_de(n),
        "refino (REFINO_POR_HU)": lambda n: E._familia_para_refino(n),
        "piso de volume (VOLUME_MINIMO_CM3)":
            lambda n: N.procurar(E.VOLUME_MINIMO_CM3, n,
                                 E.VOLUME_MINIMO_GERAL_CM3),
        "janela de densidade (JANELAS_HU)":
            lambda n: (P._declarada(n), P.janela_de(n)),
        "margem (MARGEM_OAR_MM)": lambda n: N.procurar(E.MARGEM_OAR_MM, n),
        "cor": lambda n: tuple(E._color(n)),
    }


def divergencias(nomes):
    fora = []
    for rotulo, f in sorted(_consultas().items()):
        for n in nomes:
            try:
                ref = f(n)
            except Exception as e:
                fora.append((rotulo, n, n, "excecao", type(e).__name__))
                continue
            for forma in N.formas(n):
                if forma == n:
                    continue
                try:
                    r = f(forma)
                except Exception as e:
                    r = "excecao %s" % type(e).__name__
                if (rotulo == "cor" and N.ALIAS_INTERNO.get(n) == forma):
                    continue
                if r != ref:
                    fora.append((rotulo, n, forma, ref, r))
    return fora


def teste_o_defeito_do_delgado():
    secao(u"o defeito que fez o tradutor existir")
    checar(u"o delgado cru acha a suavizacao do amigavel (1,0 mm, alca)",
           E.suavizacao_de("small_bowel") == E.suavizacao_de("small_intestine")
           == E._S_ALCA,
           u"cru %s, amigavel %s" % (E.suavizacao_de("small_bowel"),
                                     E.suavizacao_de("small_intestine")))
    checar(u"o delgado amigavel acha a recusa declarada da janela (cru)",
           P._declarada("small_intestine") and
           P.janela_de("small_intestine") is None)
    checar(u"  e com sufixo de procedencia tambem (`Bowel_Small_ai` nao; a "
           u"chave `small_intestine_ai`)",
           P._declarada("small_intestine_ai"))
    checar(u"o piso de volume do delgado vale para o cru",
           N.procurar(E.VOLUME_MINIMO_CM3, "small_bowel") ==
           E.VOLUME_MINIMO_CM3["small_intestine"])
    checar(u"os dois saem com o MESMO nome no TPS",
           E.nome_clinico("small_bowel") == E.nome_clinico("small_intestine")
           == "Bowel_Small_ai",
           u"%s / %s" % (E.nome_clinico("small_bowel"),
                         E.nome_clinico("small_intestine")))
    checar(u"  e com a MESMA cor", E._color("small_bowel") ==
           E._color("small_intestine"))
    for cru, am in (("inferior_pharyngeal_constrictor",
                     "pharyngeal_constrictor_inferior"),
                    ("lateral_rectus_muscle_left", "rectus_lateral_left"),
                    ("levator_palpebrae_superioris_left",
                     "levator_palpebrae_left")):
        checar(u"%s e %s: a mesma suavizacao e o mesmo nome" % (cru, am),
               E.suavizacao_de(cru) == E.suavizacao_de(am)
               and E.nome_clinico(cru) == E.nome_clinico(am),
               u"%s/%s" % (E.nome_clinico(cru), E.nome_clinico(am)))


def teste_a_invariancia_no_vocabulario_do_full():
    secao(u"toda consulta responde igual a todas as formas de cada nome")
    nomes = vocabulario_do_full()
    checar(u"o vocabulario do FULL tem as formas crua e amigavel",
           "small_bowel" in nomes and "small_intestine" in nomes
           and len(nomes) > 150, u"%d nomes" % len(nomes))
    d = divergencias(nomes)
    checar(u"nenhuma consulta muda de resposta conforme a forma do nome",
           not d, u" | ".join("%s: %s x %s" % (c, n, f)
                              for c, n, f, _a, _b in d[:6]))
    tabelas = {"SUAVIZACAO": E.SUAVIZACAO,
               "VOLUME_MINIMO_CM3": E.VOLUME_MINIMO_CM3,
               "JANELAS_HU": P.JANELAS_HU, "MARGEM_OAR_MM": E.MARGEM_OAR_MM,
               "TG263": E.TG263}
    perdidas = []
    for tn, t in sorted(tabelas.items()):
        for k in t:
            for forma in N.formas(k):
                if N.procurar(t, forma) != t[k] and forma not in t:
                    perdidas.append("%s[%s] por %s" % (tn, k, forma))
    checar(u"toda entrada de toda tabela e achada por todas as formas da chave",
           not perdidas, u", ".join(perdidas[:6]))


def teste_a_isca_da_consulta_direta():
    secao(u"(isca) a consulta direta de antes reprova a invariancia")
    velho = N.procurar

    def direto(tabela, nome, padrao=None):
        return (tabela or {}).get(N._limpo(nome), padrao)
    N.procurar = direto
    try:
        d = divergencias(vocabulario_do_full())
    finally:
        N.procurar = velho
    checar(u"sem o tradutor, a invariancia acusa (o delgado entre elas)",
           any(n in ("small_bowel", "small_intestine") for _c, n, _f, _a, _b in d),
           u"%d divergencias" % len(d))


def teste_o_coracao_do_modelo_tem_nome_proprio():
    secao(u"o coracao do modelo: as tabelas do `heart`, o nome dele")
    cm = N.CHAVE_DO_CORACAO_DO_MODELO
    checar(u"`%s` le a suavizacao do `heart`" % cm,
           E.suavizacao_de(cm) == E.suavizacao_de("heart"))
    checar(u"  e o piso de volume", N.procurar(E.VOLUME_MINIMO_CM3, cm) ==
           E.VOLUME_MINIMO_CM3["heart"])
    checar(u"mas sai com nome proprio no TPS, que cabe nos 16",
           E.nome_clinico(cm) == "Heart_Model_ai"
           and E.nome_clinico("heart") == "Heart_ai",
           u"%s / %s" % (E.nome_clinico(cm), E.nome_clinico("heart")))
    checar(u"  e com cor diferente do construido", E._color(cm) !=
           E._color("heart"))
    checar(u"o alias e de uma via: `heart` NAO vira `%s`" % cm,
           cm not in N.formas("heart"))


def teste_ambiguidade_e_recusada():
    secao(u"um cru reclamado por dois amigaveis nao vira alias")
    try:
        N.registrar({"a_amigo": {"t": ["cru_x"]}, "b_amigo": {"t": ["cru_x"]},
                     "c_amigo": {"t": ["cru_c"]}})
        checar(u"o ambiguo fica como veio", N.canonico("cru_x") == "cru_x")
        checar(u"  e o 1 para 1 traduz", N.canonico("cru_c") == "c_amigo")
        checar(u"o prefixo de motor e a chave de comparacao nao atrapalham",
               N.canonico("nv:cru_c") == "c_amigo"
               and N.canonico("cru_c@cads") == "c_amigo")
    finally:
        N.registrar(E.TS_MAP)
    checar(u"o mapa real volta registrado",
           N.canonico("small_bowel") == "small_intestine")


def teste_as_chaves_da_serie_pelo_tradutor():
    secao(u"desconto, contencao e marcos acham a chave em qualquer forma")
    import numpy as np
    import radai_geom
    g = radai_geom.Grade((3.0, 1.0, 1.0))
    rim = np.zeros((10, 20, 20), bool)
    rim[2:8, 4:16, 4:16] = True
    cisto = np.zeros_like(rim)
    cisto[3:6, 7:11, 7:11] = True
    m = {"kidney_left": rim.copy(), "kidney_cyst_left": cisto.copy()}
    E.aplicar_desconto(m, g)
    checar(u"o desconto do cisto acontece (a chave e a da tabela)",
           not (m["kidney_left"] & cisto).any())
    vol = E._volume_cm3({"kidney_left": rim}, ("kidney_left",), g)
    checar(u"o volume do marco e medido pela chave da serie", vol > 0)
    import radai_skin as _sk
    orgaos = set()
    for _cisto, _orgao in E.DESCONTADAS_DE.items():
        orgaos.update([_cisto, _orgao])
    for _reg, _marcos, _piso in E.MARCOS_DE_REGIAO:
        orgaos.update(_marcos)

    def _perdidos(achar):
        return [(o, f) for o in sorted(orgaos) for f in N.formas(o)
                if achar({f: 1}, o) != f]
    checar(u"cada forma de cada orgao de DESCONTADAS_DE e MARCOS_DE_REGIAO e "
           u"achada pelo tradutor (%d orgaos)" % len(orgaos),
           orgaos and not _perdidos(N.achar), str(_perdidos(N.achar)[:4]))
    checar(u"  isca: com o `achar` desligado, a checagem acusa",
           bool(_perdidos(lambda m, n: None)))
    vocab = vocabulario_do_full()

    def _crops_orfaos(prefixos):
        return [p for p in prefixos
                if not any(N.casa_prefixo(n, (p,)) is not None
                           for n in vocab)]
    checar(u"cada prefixo de CROPS_DA_PAREDE casa algum nome do vocabulario "
           u"do FULL", not _crops_orfaos(_sk.CROPS_DA_PAREDE),
           str(_crops_orfaos(_sk.CROPS_DA_PAREDE)))
    checar(u"  isca: um prefixo que nenhum nome casa e acusado",
           _crops_orfaos(tuple(_sk.CROPS_DA_PAREDE)
                         + ("prefixo_que_nao_existe_",))
           == ["prefixo_que_nao_existe_"])


ABDOMINAL_MUSCLES = tuple(
    "%s_%s" % (m, lado) for m in (
        "pectoralis_major", "rectus_abdominis", "serratus_anterior",
        "latissimus_dorsi", "trapezius", "external_oblique",
        "internal_oblique", "erector_spinae", "transversospinalis",
        "psoas_major", "quadratus_lumborum")
    for lado in ("right", "left"))


def _lado_consistente(nomes_finais):
    return sorted(n for n in nomes_finais
                  if n.endswith(("_left_ai", "_right_ai")))


def _mal_nomeados(nomes, tabela=None):
    tabela = E.TG263 if tabela is None else tabela
    fora = []
    for cru in nomes:
        base = tabela.get(cru)
        nome = E.nome_clinico(cru)
        lado = "_L" if cru.endswith("_left") else "_R"
        if base is None:
            fora.append((cru, nome, u"sem entrada no TG263 do motor"))
        elif nome != base + E.SUFIXO_AI:
            fora.append((cru, nome, u"truncado (a tabela diz %s)" % base))
        elif len(nome) > E.LIMITE_NOME:
            fora.append((cru, nome, u"passa de %d" % E.LIMITE_NOME))
        elif not nome.endswith(lado + E.SUFIXO_AI):
            fora.append((cru, nome, u"lado trocado ou por extenso"))
        elif cru not in E.TG263_A_CONFERIR:
            fora.append((cru, nome, u"forma nossa fora de TG263_A_CONFERIR"))
    return fora


def teste_os_nomes_da_abdominal_muscles():
    secao(u"os nomes da abdominal_muscles e o lado no FULL")
    ruins = _mal_nomeados(ABDOMINAL_MUSCLES)
    checar(u"os 22 da abdominal_muscles: forma do TG-263, inteira em 16 com "
           u"o `_ai`, o lado certo, a conferir", not ruins, str(ruins[:6]))
    finais = [E.nome_clinico(n) for n in ABDOMINAL_MUSCLES]
    checar(u"  e os 22 nomes sao distintos", len(set(finais)) == 22,
           str(sorted(finais)))
    outros = {}
    for n in vocabulario_do_full():
        if n in ABDOMINAL_MUSCLES:
            continue
        outros.setdefault(E.nome_clinico(n), set()).add(n)
    bate = sorted((f, sorted(outros[f])) for f in finais if f in outros)
    checar(u"  e nenhum colide com outro nome do FULL", not bate, str(bate))
    lado = _lado_consistente(E.nome_clinico(n) for n in vocabulario_do_full())
    checar(u"nenhum nome do FULL escreve o lado por extenso (humerus, "
           u"escapula, platisma...)", not lado, str(lado))
    checar(u"  o umero e a escapula saem `_L_ai`/`_R_ai`",
           [E.nome_clinico(n) for n in ("humerus_left", "scapula_right")]
           == ["humerus_L_ai", "scapula_R_ai"],
           str([E.nome_clinico(n) for n in ("humerus_left",
                                             "scapula_right")]))
    checar(u"  e o TS cru continua com o nome como o modelo escreve "
           u"(o lado por extenso quando cabe)",
           E.nome_clinico("humerus_left", sufixo="_ts") == "humerus_left_ts",
           E.nome_clinico("humerus_left", sufixo="_ts"))
    checar(u"ISCA: um `humerus_left_ai` no meio do FULL, a checagem do lado "
           u"acusa", _lado_consistente(finais + ["humerus_left_ai"])
           == ["humerus_left_ai"])
    sem = dict(E.TG263)
    sem.pop("erector_spinae_left", None)
    velho = E.TG263
    E.TG263 = sem
    try:
        ruins_i = _mal_nomeados(ABDOMINAL_MUSCLES, tabela=sem)
    finally:
        E.TG263 = velho
    checar(u"ISCA: sem a entrada do eretor da espinha, ele volta a sair "
           u"truncado e a checagem acusa",
           [r[0] for r in ruins_i] == ["erector_spinae_left"], str(ruins_i))


def _conferir_registro(testes):
    fonte = open(os.path.abspath(__file__), encoding="utf-8").read()
    import re
    definidos = set(re.findall(r"^def (teste_\w+)\(", fonte, re.M))
    faltam = sorted(definidos - set(t.__name__ for t in testes))
    checar(u"todo teste definido esta na lista do main", not faltam,
           ", ".join(faltam))


def main():
    print(u"test_names | o tradutor unico de nomes (radai_names)")
    testes = (teste_o_defeito_do_delgado,
              teste_a_invariancia_no_vocabulario_do_full,
              teste_a_isca_da_consulta_direta,
              teste_o_coracao_do_modelo_tem_nome_proprio,
              teste_ambiguidade_e_recusada,
              teste_as_chaves_da_serie_pelo_tradutor,
              teste_os_nomes_da_abdominal_muscles)
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
