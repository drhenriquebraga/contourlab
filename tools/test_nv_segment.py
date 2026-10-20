# -*- coding: utf-8 -*-
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")

AQUI = os.path.dirname(os.path.abspath(__file__))
APP = os.environ.get("RADAI_APP") or os.path.join(os.path.dirname(AQUI), "app")
sys.path.insert(0, APP)

import tempfile
sys.path.insert(0, AQUI)
import _cleanup
_cleanup.adotar_prefixo('radai_nvseg')
os.environ.setdefault("RADAI_CALIB_DIR",
                      tempfile.mkdtemp(prefix="radai_nvseg"))

import engine
import radai_output
import radai_sets
import radai_nv_engine as ve

OK = [0]
RUIM = []


def checar(nome, cond, detalhe=""):
    OK[0] += 1
    if not cond:
        RUIM.append("%s %s" % (nome, detalhe))
        print("  FALHA: %s %s" % (nome, detalhe))


def teste_sufixo_de_procedencia():
    f = getattr(engine, "sufixo_de_procedencia", None)
    checar("a decisao do sufixo e uma funcao", callable(f))
    if not callable(f):
        return
    A = engine.SUFIXO_AI
    casos = [
        ("liver", {"liver": "cads"}, "", "_cds", "_cds"),
        ("LNL01", {"LNL01": "hnlnl"}, "", "_lnl", "_lnl"),
        ("liver", {"liver": "ts"}, "", "_ts", "_ts"),
        ("rectum", {"rectum": "derivada"}, "", A, A),
        ("rectum", {"rectum": "derivada"}, "", "_cds", "_cds"),
        ("nv:liver", {}, "", A, "_nv"),
        ("rectum", {}, "cads", A, "_cds"),
        ("liver", {"liver": "nosso"}, "", A, A),
    ]
    for chave, origem, motor_alt, conj, esperado in casos:
        got = f(chave, origem, motor_alt, conj)
        checar("sufixo de %r (conjunto %s)" % (chave, conj),
               got == esperado, "devolveu %r, esperava %r" % (got, esperado))


def teste_quem_executa_chama():
    import inspect
    src = inspect.getsource(engine.build_rtstruct)
    checar("build_rtstruct chama sufixo_de_procedencia",
           "sufixo_de_procedencia(" in src)
    checar("build_rtstruct aceita o sufixo do conjunto",
           "sufixo_do_conjunto" in inspect.getsource(engine.build_rtstruct)
           or "sufixo_do_conjunto" in str(
               inspect.signature(engine.build_rtstruct)))
    for morto in ('elif origem.get(nm) == "ts":',
                  'elif origem.get(nm) == "derivada":',
                  "sufixo = SUFIXO_AI"):
        checar("a cadeia velha saiu (%s)" % morto[:28], morto not in src)


def teste_o_conjunto_manda_o_sufixo_do_registro():
    recebido = {}

    class MotorDublado(object):
        def build_rtstruct(self, stage, masks, **kw):
            recebido.update(kw)
            return ("rt_falso", {"x": "X_ai"})

    class Saida(radai_output.Saida):
        def _gravar_arquivo(self, rt_local, alvo):
            pass

    for cod in ("oar", "full", "ts", "nv", "cads", "hnl"):
        recebido.clear()
        s = Saida(MotorDublado(), "stage", ".", "RS_RadAI_x.dcm", log=None)
        s.conjunto(cod, {"x": 1}, "nosso")
        checar("o conjunto %r manda o sufixo do registro" % cod,
               recebido.get("sufixo_do_conjunto")
               == radai_sets.POR_COD[cod]["sufixo"],
               "chegou %r, registro diz %r"
               % (recebido.get("sufixo_do_conjunto"),
                  radai_sets.POR_COD[cod]["sufixo"]))


def teste_o_entregue_nao_ganha_sufixo_de_motor():
    import numpy as np
    cheia = np.zeros((4, 4, 4), bool)
    cheia[1:3, 1:3, 1:3] = True
    nossas = {"liver": cheia.copy(), "rectum": cheia.copy()}
    por_motor = {"cads": {"rectum": cheia.copy(), "larynx": cheia.copy(),
                          "seminal_vesicles": cheia.copy()}}
    _m, _a = engine.MELHOR_FONTE, engine.AMBOS
    engine.MELHOR_FONTE = {"larynx": ("cads", u"veiculo do teste"),
                           "seminal_vesicles": ("cads", u"veiculo do teste")}
    engine.AMBOS = {"rectum": ("cads", u"veiculo do teste")}
    try:
        masks, origem = engine.curar(nossas, por_motor, tabela={})
    finally:
        engine.MELHOR_FONTE, engine.AMBOS = _m, _a
    checar("curar marca as exclusivas do cads como `cads`",
           origem.get("larynx") == "cads" and
           origem.get("seminal_vesicles") == "cads",
           str(dict(origem)))
    for nm in ("larynx", "seminal_vesicles"):
        suf = engine.sufixo_de_procedencia(nm, origem, "", engine.SUFIXO_AI)
        checar("%s continua `_ai` no entregue" % nm, suf == engine.SUFIXO_AI,
               "saiu %r -- o RTSTRUCT do plano mudaria de nome" % suf)
    suf = engine.sufixo_de_procedencia("rectum@cads", origem, "cads",
                                       engine.SUFIXO_AI)
    checar("o reto em dobro continua `_cds`", suf == "_cds", "saiu %r" % suf)


def teste_o_rastro_do_v3d_saiu():
    velho = "RS_RadAI_V3D_20260914_19564257.dcm"
    checar("o `V3D_` deixou de ser reconhecido",
           radai_sets.do_arquivo(velho) is None,
           repr(radai_sets.do_arquivo(velho)))
    checar("e ele nao passa por entregue", not radai_sets.e_entregue(velho))
    checar("`V3D_` nao ficou como infixo historico",
           "V3D_" not in radai_sets.INFIXOS_DE_OUTRO_CONSUMIDOR,
           repr(radai_sets.INFIXOS_DE_OUTRO_CONSUMIDOR))
    checar("nenhum conjunto usa o infixo `V3D_`",
           "V3D_" not in radai_sets.INFIXOS, repr(radai_sets.INFIXOS))
    checar("nenhum conjunto usa o sufixo `_v3D`",
           "_v3D" not in radai_sets.SUFIXOS, repr(radai_sets.SUFIXOS))
    novo = radai_sets.nome_do_arquivo("nv", "20260914", "19564257")
    c = radai_sets.do_arquivo(novo)
    checar("e o `NV_` E reconhecido", bool(c) and c["cod"] == "nv",
           "%s -> %r" % (novo, c and c["cod"]))


def teste_todo_sufixo_de_procedencia_cabe_em_tres():
    for c in radai_sets.CONJUNTOS:
        s = c["sufixo"]
        checar("o sufixo de `%s` tem no maximo 3 + `_`" % c["cod"],
               len(s) <= 4 and s.startswith("_"), "%r (%d)" % (s, len(s)))
    checar("o do segundo motor e `_nv`",
           radai_sets.POR_COD["nv"]["sufixo"] == "_nv",
           repr(radai_sets.POR_COD["nv"]["sufixo"]))
    checar("`engine.SUFIXO_NV` e o mesmo do registro",
           engine.SUFIXO_NV == radai_sets.POR_COD["nv"]["sufixo"],
           "%r vs %r" % (engine.SUFIXO_NV,
                         radai_sets.POR_COD["nv"]["sufixo"]))
    checar("e `SUFIXO_POR_MOTOR` usa a chave `nv`",
           engine.SUFIXO_POR_MOTOR.get("nv") == "_nv",
           repr(engine.SUFIXO_POR_MOTOR))

MAPA_NV = {}


def _mapa():
    if MAPA_NV:
        return MAPA_NV
    p = os.path.join(AQUI, "data", "nv_segment_ct_labels.json")
    if not os.path.exists(p):
        raise AssertionError("falta tools/data/nv_segment_ct_labels.json")
    MAPA_NV.update(json.load(open(p, encoding="utf-8")))
    return MAPA_NV


def teste_a_fixture_e_o_mapa_de_132():
    mapa = _mapa()
    checar("a fixture do NV tem 132 classes", len(mapa) == 132,
           "tem %d" % len(mapa))


def teste_duas_listas_do_nv():
    l = ve.listas("nv_segment_ct")
    ent, ach = l["entrega"], l["achado"]
    checar("entrega e achado nao se cruzam", not (set(ent) & set(ach)),
           repr(sorted(set(ent) & set(ach))))
    for n in (u"lung tumor", u"pancreatic tumor", u"hepatic tumor",
              u"colon cancer primaries", u"bone lesion", u"kidney mass",
              u"liver tumor", u"left kidney cyst", u"right kidney cyst"):
        checar("%r e achado no NV" % n, n in ach)
        checar("%r NAO esta na entrega do NV" % n, n not in ent)


def teste_achado_exige_ato_declarado():
    mapa = _mapa()
    ids = ve.ids_permitidos("nv_segment_ct", por_nome=mapa)
    ach = ve.listas("nv_segment_ct")["achado"]
    de_id = dict((int(i), n) for n, i in mapa.items())
    vazou = sorted(de_id[i] for i in ids if de_id.get(i) in ach)
    checar("ids_permitidos do NV nao devolve achado", not vazou, repr(vazou))
    checar("ids_permitidos do NV devolve os 115 conferidos", len(ids) == 115,
           "devolveu %d" % len(ids))
    for n in (u"kidney", u"lung", u"bone", u"prostate or uterus",
              u"rectum", u"vertebrae L6",
              u"hepatic vessel", u"airway"):
        checar("%r nao entra por omissao" % n,
               mapa.get(n) is None or int(mapa[n]) not in ids)


def teste_trava_do_vocabulario():
    mapa = _mapa()
    ve.conferir_classes([mapa[u"liver"]], ident="nv_segment_ct", por_nome=mapa)
    ve.conferir_classes([mapa[u"kidney mass"]], ident="nv_segment_ct",
                        por_nome=mapa)
    ve.conferir_classes([mapa[u"kidney"]], ident="nv_segment_ct", por_nome=mapa)
    for ruim in ([999], [133]):
        try:
            ve.conferir_classes(ruim, ident="nv_segment_ct", por_nome=mapa)
            checar("conferir_classes recusa %r" % ruim, False, "nao levantou")
        except ValueError:
            checar("conferir_classes recusa %r" % ruim, True)


def teste_listas_sao_por_modelo():
    mapa = _mapa()
    for ident in ("modelo_que_nao_existe", "vista3d_monai"):
        try:
            ve.ids_permitidos(ident=ident, por_nome=mapa)
            checar("ids_permitidos exige registro (%s)" % ident, False,
                   "aceitou ident sem registro")
        except ValueError:
            checar("ids_permitidos exige registro (%s)" % ident, True)
        try:
            ve.conferir_classes([1], ident=ident, por_nome=mapa)
            checar("conferir_classes exige registro (%s)" % ident, False,
                   "aceitou ident sem registro")
        except ValueError:
            checar("conferir_classes exige registro (%s)" % ident, True)
    checar("o achado do nv tem 9",
           len(ve.listas("nv_segment_ct")["achado"]) == 9,
           "tem %d" % len(ve.listas("nv_segment_ct")["achado"]))
    checar("e `vista3d_monai` nao tem registro nenhum",
           "vista3d_monai" not in ve.POR_MODELO, repr(sorted(ve.POR_MODELO)))
    ent = set(ve.CLASSES_DE_ENTREGA)
    ach = set(ve.CLASSES_DE_ACHADO)
    fora = set(ve.CLASSES_FORA_DA_ENTREGA)
    checar("entrega 115 + achado 9 + fora 8 = 132",
           (len(ent), len(ach), len(fora)) == (115, 9, 8),
           "%d/%d/%d" % (len(ent), len(ach), len(fora)))
    checar("as tres nao se cruzam",
           not (ent & ach) and not (ent & fora) and not (ach & fora))
    checar("e a uniao e exatamente o mapa de 132",
           (ent | ach | fora) == set(mapa),
           repr(sorted((ent | ach | fora) ^ set(mapa))))


def main():
    for t in (teste_sufixo_de_procedencia, teste_quem_executa_chama,
              teste_o_conjunto_manda_o_sufixo_do_registro,
              teste_o_entregue_nao_ganha_sufixo_de_motor,
              teste_o_rastro_do_v3d_saiu,
              teste_todo_sufixo_de_procedencia_cabe_em_tres,
              teste_a_fixture_e_o_mapa_de_132, teste_duas_listas_do_nv,
              teste_achado_exige_ato_declarado, teste_trava_do_vocabulario,
              teste_listas_sao_por_modelo):
        try:
            t()
        except Exception as e:
            RUIM.append("%s levantou %s: %s" % (t.__name__, type(e).__name__, e))
            print("  ERRO em %s: %s: %s" % (t.__name__, type(e).__name__, e))
    if RUIM:
        print("FALHOU: %d de %d checagens" % (len(RUIM), OK[0]))
        return 1
    print("OK: %d checagens" % OK[0])
    return 0


if __name__ == "__main__":
    sys.exit(main())
