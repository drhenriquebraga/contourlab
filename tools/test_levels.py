# -*- coding: utf-8 -*-
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
RAIZ = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    ".."))
sys.path.insert(0, os.path.join(RAIZ, "app"))

import numpy as np
import radai_geom as G
import radai_hnlnl as H

_OK = [0]
_FALHAS = []


def checar(nome, ok, detalhe=""):
    _OK[0] += 1
    if not ok:
        _FALHAS.append(nome)
    print("  %s  %s%s" % ("OK   " if ok else "FALHA", nome,
                          ("  [%s]" % detalhe) if detalhe else ""))
    return bool(ok)


GRADE = G.Grade((2.0, 1.5, 1.5))
_Z_DOS_PARES = (72, 66, 60, 54, 46, 38, 30, 22)


def _fantoma():
    vol = np.zeros((80, 120, 120), dtype="int8")

    def por(i, z, y, x):
        vol[z - 2:z + 2, y - 3:y + 3, x - 3:x + 3] = i
    for i, (z, y) in zip((1, 14, 15, 16), ((70, 40), (55, 42), (40, 44),
                                           (68, 80))):
        por(i, z, y, 60)
    for k, (esq, dir_) in enumerate(H.PARES_DE_LADO):
        por(esq, _Z_DOS_PARES[k], 60, 85)
        por(dir_, _Z_DOS_PARES[k], 60, 35)
    return vol


def teste_o_mapa_nomeia_os_20():
    print("\n[1] O mapa dos autores nomeia os 20")
    nomes = [H.nome_do_nivel(i) for i in range(1, 21)]
    checar("os 20 nomes sao distintos e todos `Lvl_`",
           len(set(nomes)) == 20 and all(n.startswith("Lvl_") for n in nomes))
    checar("o 2 e o Ib esquerdo e o 3 o direito (a ordem dos autores)",
           (H.nome_do_nivel(2), H.nome_do_nivel(3)) == ("Lvl_Ib_L",
                                                        "Lvl_Ib_R"))
    checar("os quatro impares saem sem lado",
           [H.MAPA_DOS_PESOS[i] for i in (1, 14, 15, 16)]
           == ["Ia", "VIa", "VIb", "VIIa"])
    checar("cada par de PARES_DE_LADO e o mesmo nivel, _L e _R",
           all(H.MAPA_DOS_PESOS[a][:-2] == H.MAPA_DOS_PESOS[b][:-2]
               and H.MAPA_DOS_PESOS[a].endswith("_L")
               and H.MAPA_DOS_PESOS[b].endswith("_R")
               for a, b in H.PARES_DE_LADO))
    checar("sem o mapa fixado, o nome e o neutro",
           H.nome_do_nivel(7, False) == "LNL07"
           and u"NAO foi atribuido" in H.descricao_do_nivel(7, False))
    checar("e a uniao neutra e outra chave (LNL_Union)",
           H.nome_da_uniao(False) == "LNL_Union"
           and H.nome_da_uniao(True) == "LNL_UNION")


def teste_a_conferencia_de_lado():
    print("\n[2] A conferencia de lado mede em mm anatomicos")
    vol = _fantoma()
    ok, laudo = H.conferir_lado(vol, GRADE)
    checar("o fantoma com os lados certos passa", ok, u" | ".join(laudo))
    g_dir = G.Grade((2.0, 1.5, 1.5), ("sup", "post", "dir"))
    ok2, laudo2 = H.conferir_lado(vol, g_dir)
    checar("o mesmo arranjo lido com o eixo x apontando para a direita "
           "RECUSA (a matriz de direcao manda)", not ok2, u" | ".join(laudo2))
    meio = vol.copy()
    for a, b in H.PARES_DE_LADO[:3]:
        meio[vol == a], meio[vol == b] = b, a
    ok3, laudo3 = H.conferir_lado(meio, GRADE)
    checar("3 de 8 pares trocados: entrega, com um ALERTA por par",
           ok3 and sum(u"ALERTA" in l for l in laudo3) == 3,
           u" | ".join(laudo3))
    for a, b in H.PARES_DE_LADO[3:4]:
        meio[vol == a], meio[vol == b] = b, a
    ok4, laudo4 = H.conferir_lado(meio, GRADE)
    checar("4 de 8 (metade): recusa", not ok4 and u"4 de 8" in laudo4[0],
           u" | ".join(laudo4))
    so_um = np.where(np.isin(vol, (2,)), vol, 0)
    checar("sem par completo nao ha o que conferir: passa",
           H.conferir_lado(so_um, GRADE)[0])


def teste_o_que_sai_continua_permitido():
    print("\n[3] Nomear nao afrouxa a trava de saida")
    try:
        H.conferir_saida(["Nodulo_suspeito"])
        checar("nome inventado e recusado pela trava de saida", False,
               "passou")
    except Exception:
        checar("nome inventado e recusado pela trava de saida", True)
    try:
        H.conferir_saida(["LNL07", "LNL_Union", "Lvl_III_R", "LNL_UNION",
                          "parotid_lnl_left"])
        checar("o neutro, o nomeado, as unioes e a parotida do VIII passam",
               True)
    except Exception as e:
        checar("o neutro, o nomeado, as unioes e a parotida do VIII passam",
               False, str(e)[:60])


def teste_o_conjunto_do_modelo_fecha():
    print("\n[4] As tabelas de nome batem com o conjunto do modelo")
    conj = set(H.CONJUNTO_DO_MODELO["impares"]) | set(
        H.CONJUNTO_DO_MODELO["bilaterais"])
    usados = set(n[:-2] if n.endswith(("_L", "_R")) else n
                 for n in H.MAPA_DOS_PESOS.values())
    checar("os niveis do mapa sao os do artigo",
           usados == conj, u", ".join(sorted(usados ^ conj)) or u"iguais")
    checar("e a ordem bilateral tem os mesmos oito",
           set(H.ORDEM_BILATERAL) == set(H.CONJUNTO_DO_MODELO["bilaterais"]))
    checar("4 + 8x2 = 20", 4 + 2 * len(H.ORDEM_BILATERAL) == 20
           and len(H.MAPA_DOS_PESOS) == 20)
    div = H.CONJUNTO_DO_MODELO.get("divisao") or u""
    checar("a divisao cita o artigo do modelo (PMC9978473), e nao Gregoire",
           u"PMC9978473" in div and u"2013 update" not in div, div[:90])
    checar("e os nomes citam Gregoire (o «2013 update»)",
           u"2013 update" in H.CONJUNTO_DO_MODELO["referencia"])
    checar("cada nivel tem o nome de Gregoire na descricao",
           set(H.DESCRITOR_DO_NIVEL) == conj)


def teste_a_ordem_segue_a_extensao_dos_limites():
    print("\n[5] A ordem craniocaudal segue a extensao dos limites")
    o = list(H.ORDEM_BILATERAL)
    checar("o II vem ANTES do Ib (o II comeca em C1, acima da submandibular)",
           o.index("II") < o.index("Ib"), str(o))
    checar("o III vem ANTES do V (o V desce ate 2 cm acima do manubrio)",
           o.index("III") < o.index("V"), str(o))
    checar("  e o V continua ANTES do IVa (o IVa comeca na cricoide)",
           o.index("V") < o.index("IVa"), str(o))
    checar("  e as pontas: VIIb no topo, IVb no fim",
           o[0] == "VIIb" and o[-1] == "IVb", str(o))
    checar("o mapa e fixado pela versao dos pesos (ORDEM_CONFERIDA)",
           H.ORDEM_CONFERIDA is True)


def main():
    print("test_levels | os nomes dos niveis cervicais: o mapa e o lado")
    teste_o_mapa_nomeia_os_20()
    teste_a_conferencia_de_lado()
    teste_o_que_sai_continua_permitido()
    teste_o_conjunto_do_modelo_fecha()
    teste_a_ordem_segue_a_extensao_dos_limites()
    print("")
    if _FALHAS:
        print("FALHAS: %d de %d" % (len(_FALHAS), _OK[0]))
        for f in _FALHAS:
            print("  - %s" % f)
        return 1
    print("OK: %d checagens, todas passaram" % _OK[0])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
