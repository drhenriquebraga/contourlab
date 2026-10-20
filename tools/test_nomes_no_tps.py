# -*- coding: utf-8 -*-
import os
import sys
import traceback

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
import _componentes

import engine as E
import radai_sets as RS

_RES = []
VERBOSO = "-v" in sys.argv
TETO = 16


def checar(nome, cond, detalhe=""):
    ok = bool(cond)
    _RES.append((nome, ok, detalhe))
    if VERBOSO or not ok:
        print(u"  %s  %s%s" % (u"ok   " if ok else u"FALHA", nome,
                              (u"  [%s]" % detalhe) if detalhe else u""))
    return ok


def secao(t):
    print(u"\n-- %s --" % t)


def problemas(pares, permitidos=()):
    longos, nao_ascii, por_nome = [], [], {}
    for chave, nome in pares:
        if len(nome) > TETO:
            longos.append((chave, nome))
        if any(ord(c) > 127 for c in nome) or u"\\" in nome:
            nao_ascii.append((chave, nome))
        por_nome.setdefault(nome, set()).add(chave)
    juntos = set(frozenset(p) for p in permitidos)
    repetidos = sorted((n, sorted(ks)) for n, ks in por_nome.items()
                       if len(ks) > 1 and frozenset(ks) not in juntos)
    return longos, nao_ascii, repetidos


def _relatar(rotulo, pares, permitidos=()):
    longos, nao_ascii, repetidos = problemas(pares, permitidos)
    checar(u"%s: %d nome(s), todos com no maximo %d caracteres"
           % (rotulo, len(pares), TETO), not longos, str(longos[:6]))
    checar(u"%s: todos ASCII, sem contrabarra" % rotulo, not nao_ascii,
           str(nao_ascii[:6]))
    checar(u"%s: nenhum nome repetido entre chaves diferentes" % rotulo,
           not repetidos, str(repetidos[:6]))


def _roda(task):
    perm = set(E.TASKS_PERMITIDAS)
    return task in perm or E._familia(task) in perm or any(
        E._familia(p) == E._familia(task) for p in perm)


def chaves_do_ts():
    return set(k for k, d in E.TS_MAP.items()
               if isinstance(d, dict) and any(_roda(t) for t in d))


def chaves_do_full():
    chaves = chaves_do_ts() | set(E.COMPOSTOS)
    chaves |= set(E.CONSTRUCOES_POR_SAIDA())
    chaves |= set(E.NOME_DO_RECORTE.values())
    chaves |= set(E.CHAVES_DERRAME_POR_LADO.values())
    chaves |= set(E.CHAVES_GLANDULA_POR_LADO.values())
    for regra in E.DERIVADAS.values():
        for _m, _e, _o, nome in regra.get("planos") or ():
            chaves.add(nome)
    chaves.add(E._nomes.CHAVE_DO_CORACAO_DO_MODELO)
    try:
        import radai_cranio_engine as CR
        chaves |= set(CR.PARA_O_FULL.values())
    except Exception:
        pass
    try:
        import radai_hnlnl as HN
        chaves |= set(HN.nome_do_nivel(i) for i in range(1, 21))
        chaves |= set(HN.CHAVES_NO_OAR)
    except Exception:
        pass
    return sorted(c for c in chaves if not str(c).startswith("_"))


def teste_o_full_e_o_oar():
    secao(u"FULL, OAR e OAR_Fast (sufixo _ai): todo nome que pode ser gravado")
    chaves = chaves_do_full()
    pares = [(k, E.nome_clinico(k)) for k in chaves]
    _relatar(u"FULL", pares, RS.MESMA_ROI_NO_OAR.items())
    mortas = set(E.TS_MAP) - chaves_do_ts()
    so_do_oar = set(RS.PERMITIDOS_NO_OAR) - set(chaves) - mortas
    checar(u"o OAR e o OAR_Fast sao selecoes do FULL (nenhuma chave so deles)",
           so_do_oar <= {"Skin"}, str(sorted(so_do_oar)))
    fora = sorted(set(E.TS_MAP) - chaves_do_ts())
    checar(u"(as chaves de task fora do catalogo, que nunca rodam, ficam fora "
           u"da regua: %d)" % len(fora), all(not _roda(t) for k in fora
                                             for t in E.TS_MAP[k]), str(fora))
    checar(u"a Bag_Bowel_OAR_ai tem exatamente o teto",
           E.nome_clinico("bag_bowel_oar") == u"Bag_Bowel_OAR_ai"
           and len(E.nome_clinico("bag_bowel_oar")) == TETO)


def teste_os_conjuntos_ao_lado():
    secao(u"conjuntos ao lado: o TotalSegmentator cru, os plugins e os "
          u"motores de comparacao")
    crus = sorted(set(x for d in E.TS_MAP.values() for t, l in d.items()
                      if _roda(t) for x in l))
    _relatar(u"TS cru (_ts)",
             [(x, E.nome_clinico(x, sufixo=E.SUFIXO_TS)) for x in crus])
    for p in RS.PLUGINS:
        rotulos = sorted(set(x for d in E.TS_MAP.values()
                             for t, l in d.items() if t == p["task"]
                             for x in l))
        if not rotulos:
            continue
        _relatar(u"plugin %s (%s)" % (p["cod"], p["sufixo"]),
                 [(x, E.nome_clinico(x, sufixo=p["sufixo"]))
                  for x in rotulos])
    try:
        import radai_moose as MO
        _relatar(u"MOOSE (_mse)",
                 [(v, E.nome_clinico(v, sufixo=u"_mse"))
                  for v in sorted(set(MO.DE_PARA.values()))])
    except ImportError:
        pass
    try:
        import radai_cads as CA
        _relatar(u"CADS (_cds)",
                 [(v, E.nome_clinico(v, sufixo=u"_cds"))
                  for v in sorted(set(CA.DE_PARA.values()))])
    except ImportError:
        pass
    try:
        import radai_hnlnl as HN
        _relatar(u"niveis cervicais (_lnl)",
                 [(HN.nome_do_nivel(i), E.nome_clinico(HN.nome_do_nivel(i),
                                                       sufixo=u"_lnl"))
                  for i in range(1, 21)]
                 + [(HN.NOME_DA_UNIAO, E.nome_clinico(HN.NOME_DA_UNIAO,
                                                      sufixo=u"_lnl"))])
    except ImportError:
        pass


def teste_os_nomes_de_geracoes_anteriores():
    secao(u"o nome antigo continua sendo lido (a lista so cresce)")
    antigos = RS.NOMES_DE_ROI_DE_GERACOES_ANTERIORES
    checar(u"a Bag_Bowel_tst_ai de antes e lida como a Bag_Bowel_OAR de hoje",
           RS.chave_de_roi_antiga(u"Bag_Bowel_tst_ai") == "bag_bowel_oar")
    vivos = set(E.nome_clinico(k) for k in chaves_do_full())
    checar(u"nenhum nome antigo e gravado hoje (senao nao e antigo)",
           not (set(antigos) & vivos), str(sorted(set(antigos) & vivos)))
    checar(u"toda chave de destino existe hoje",
           set(antigos.values()) <= set(chaves_do_full()),
           str(sorted(set(antigos.values()) - set(chaves_do_full()))))
    checar(u"ISCA: nome que nunca existiu nao vira chave nenhuma",
           RS.chave_de_roi_antiga(u"Nome_Inventado_ai") is None)


def teste_a_regua_sabe_reprovar():
    secao(u"a regua sabe reprovar (iscas)")
    longos, _a, _r = problemas([("x", u"Nome_De_Dezessete")])
    checar(u"ISCA: 17 caracteres reprovam", longos)
    _l, nao_ascii, _r = problemas([("x", u"Pâncreas_ai")])
    checar(u"ISCA: acento reprova", nao_ascii)
    _l, _a, rep = problemas([("a", u"Glnd_Subman_L_ai"),
                             ("b", u"Glnd_Subman_L_ai")])
    checar(u"ISCA: duas chaves com o mesmo nome reprovam", rep)
    _l, _a, rep2 = problemas([("a", u"Parotid_L_ai"), ("b", u"Parotid_L_ai")],
                             [("a", "b")])
    checar(u"  e o par declarado (a mesma ROI no OAR) passa", not rep2)
    velho = dict(E.TG263)
    try:
        E.TG263["isca_um"] = u"Glnd_Submandibular_Esq"
        E.TG263["isca_dois"] = u"Glnd_Submandibular_Dir"
        pares = [(k, E.nome_clinico(k)) for k in ("isca_um", "isca_dois")]
    finally:
        E.TG263.clear()
        E.TG263.update(velho)
    _l, _a, rep3 = problemas(pares)
    checar(u"ISCA: dois nomes que o corte dos 16 junta sao acusados", rep3,
           str(pares))


def main():
    print(u"=" * 68)
    print(u"test_nomes_no_tps | todo nome gravado tem no maximo 16 caracteres "
          u"ASCII e e unico")
    print(u"=" * 68)
    for t in (teste_o_full_e_o_oar, teste_os_conjuntos_ao_lado,
              teste_os_nomes_de_geracoes_anteriores,
              teste_a_regua_sabe_reprovar):
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
