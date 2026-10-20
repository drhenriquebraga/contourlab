# -*- coding: utf-8 -*-
import shutil
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _cleanup
_cleanup.adotar_prefixo('radai_ac_procedenc')
_cleanup.adotar_prefixo('proc_')
_cleanup.adotar_prefixo('proc2_')


try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

AQUI = os.path.dirname(os.path.abspath(__file__))


def pasta_app(aqui):
    for c in (os.path.join(aqui, "..", "app"), os.path.join(aqui, "..")):
        if os.path.exists(os.path.join(c, "radai_watcher.py")):
            return os.path.abspath(c)
    return os.path.abspath(os.path.join(aqui, "..", "app"))


APP = pasta_app(AQUI)
sys.path.insert(0, APP)

import tempfile as _tempfile
import _componentes
os.environ["RADAI_CALIB_DIR"] = _tempfile.mkdtemp(prefix="radai_ac_procedenc_")



class _TabelasDe(object):
    def __init__(self, mod, melhor=None, ambos=None):
        self.mod = mod
        self.melhor, self.ambos = melhor or {}, ambos or {}

    def __enter__(self):
        self._m, self._a = self.mod.MELHOR_FONTE, self.mod.AMBOS
        self.mod.MELHOR_FONTE, self.mod.AMBOS = self.melhor, self.ambos
        return self

    def __exit__(self, *a):
        self.mod.MELHOR_FONTE, self.mod.AMBOS = self._m, self._a
        return False


_VEICULO_MELHOR = {"seminal_vesicles": ("cads", u"veiculo do teste")}
_VEICULO_AMBOS = {"rectum": ("cads", u"veiculo do teste")}


_RESULTADOS = []


def checar(nome, ok, detalhe=""):
    _RESULTADOS.append((nome, bool(ok), detalhe))
    if not ok:
        print("  FALHA  %s%s" % (nome, ("  [%s]" % detalhe) if detalhe else ""))
    return bool(ok)


def secao(t):
    print("\n-- %s --" % t)


def teste_linha_sem_assinatura_nao_manda():
    secao("linha sem assinatura e padrao, nao escolha")
    import numpy as np
    import engine as M
    cheia = np.ones((4, 4, 4), dtype=bool)
    nossas = {"liver": cheia.copy()}
    motores = {"cads": {"liver": cheia.copy()}}

    rascunho = {"liver": {"modelo": "cads", "motivo": "ainda pensando",
                          "assinado_por": ""}}
    _f, o = M.curar(nossas, motores, tabela=rascunho)
    checar(u"rascunho NAO cura", o["liver"] == M.FONTE_PADRAO, o["liver"])

    assinada = {"liver": {"modelo": "cads", "motivo": "tem modelo dedicado",
                          "assinado_por": "Medico de Teste"}}
    _f, o2 = M.curar(nossas, motores, tabela=assinada)
    checar(u"e a assinada cura", o2["liver"] == "cads", o2["liver"])


def teste_assinar_de_volta_para_o_nosso_reverte():
    secao("assinar para o nosso reverte o padrao de fabrica")
    import numpy as np
    import engine as M
    cheia = np.ones((4, 4, 4), dtype=bool)
    nossas = {"rectum": cheia.copy()}
    motores = {"cads": {"rectum": cheia.copy()}}

    with _TabelasDe(M, _VEICULO_MELHOR, _VEICULO_AMBOS):
        f, o = M.curar(nossas, motores, tabela={})
    checar(u"sem tabela, os DOIS retos saem (comparacao aberta)",
           "rectum" in f and "rectum@cads" in f, str(sorted(f)))
    checar(u"o nosso continua sendo o nosso",
           o["rectum"] == M.FONTE_PADRAO, o["rectum"])
    checar(u"e o do CADS vem marcado como do CADS",
           o["rectum@cads"] == "cads", o["rectum@cads"])

    fecha = {"rectum": {"modelo": "cads",
                        "motivo": u"o modelo treinado ficou melhor aqui",
                        "assinado_por": "Medico de Teste"}}
    f2, o2 = M.curar(dict(nossas), motores, tabela=fecha)
    checar(u"assinado para o CADS, ele substitui o nosso",
           o2["rectum"] == "cads", o2["rectum"])

    nossas2 = {"seminal_vesicles": cheia.copy()}
    motores2 = {"cads": {"seminal_vesicles": cheia.copy()}}
    with _TabelasDe(M, _VEICULO_MELHOR, _VEICULO_AMBOS):
        _f3, o3 = M.curar(nossas2, motores2, tabela={})
    checar(u"vesicula seminal: padrao de fabrica manda vir do CADS",
           o3["seminal_vesicles"] == "cads", o3["seminal_vesicles"])
    volta = {"seminal_vesicles": {
        "modelo": "ts", "motivo": u"o nosso ficou melhor aqui",
        "assinado_por": "Medico de Teste"}}
    _f4, o4 = M.curar(nossas2, motores2, tabela=volta)
    checar(u"assinado para o nosso, ele volta a ser nosso",
           o4["seminal_vesicles"] == M.FONTE_PADRAO, o4["seminal_vesicles"])


def teste_o_log_distingue_assinada_de_padrao():
    secao("o log distingue assinada de padrao de fabrica")
    import numpy as np
    import engine as M
    cheia = np.ones((4, 4, 4), dtype=bool)
    nossas = {"seminal_vesicles": cheia.copy()}
    motores = {"cads": {"seminal_vesicles": cheia.copy()}}

    m1 = []
    with _TabelasDe(M, _VEICULO_MELHOR, _VEICULO_AMBOS):
        M.curar(nossas, motores, log=m1.append, tabela={})
    checar(u"padrao de fabrica e dito como tal",
           any("padrao de fabrica" in x for x in m1), " | ".join(m1))

    m2 = []
    with _TabelasDe(M, _VEICULO_MELHOR, _VEICULO_AMBOS):
        M.curar(nossas, motores, log=m2.append,
            tabela={"seminal_vesicles": {"modelo": "cads", "motivo": "x",
                                         "assinado_por": "Dr. H"}})
    checar(u"e a assinada aparece como ASSINADA",
           any("ASSINADA" in x for x in m2), " | ".join(m2))

    m3 = []
    with _TabelasDe(M, _VEICULO_MELHOR, _VEICULO_AMBOS):
        M.curar({"rectum": cheia.copy()}, {"cads": {"rectum": cheia.copy()}},
                log=m3.append, tabela={})
    checar(u"a comparacao aberta e anunciada, e nao se disfarca de escolha",
           any("comparacao aberta" in x for x in m3), " | ".join(m3))


class _MotorFalso(object):
    SUAVIZACAO_PADRAO_MM = 2.0
    _S_BORDA_NOVA = 4.0
    SUAVIZACAO = {"orgao_novo": 4.0}
    TS_MAP = {"orgao_novo": {"familia_x": ["orgao_novo"]}}
    COMPOSTOS = {"par_novo": ["orgao_novo"]}
    DERIVADAS = {}
    MELHOR_FONTE = {}
    AMBOS = {}
    DESCONTADAS_DE = {}
    CONTIDAS_EM = {}
    RECORTE_DE_OAR = {"orgao_novo": (("marco_novo",), "sup", 0.0)}
    MARGEM_OAR_MM = {"orgao_novo": 3.0}
    GRUPOS_DISJUNTOS = {}
    REFINO_POR_HU = {}
    ESPESSURA_FINA_MM = 9.0
    _DIVISOR_DO_RAIO = 7.0

    @staticmethod
    def suavizacao_de(nome, padrao=None):
        base = 2.0 if padrao is None else float(padrao)
        v = _MotorFalso.SUAVIZACAO.get(nome)
        return base if v is None else v * base / 2.0

    @staticmethod
    def nome_clinico(nome):
        return nome + "_ai"


def teste_o_espelho_sai_das_tabelas_do_motor():
    secao(u"o espelho sai das tabelas do motor, e nao de lista escrita a mao")
    import engine as M
    import radai_provenance as P
    base = tempfile.mkdtemp(prefix="proc_")
    e = P.espelho(1.0, engine=M, base=base)
    nomes = set(x["estrutura"] for x in e["estruturas"])
    faltam = sorted(set(M.TS_MAP) - nomes)[:4]
    checar(u"todo nome do TS_MAP aparece", not faltam, ", ".join(faltam))
    faltam = sorted(set(M.COMPOSTOS) - nomes)[:4]
    checar(u"e todo composto", not faltam, ", ".join(faltam))
    saidas = set(p[3] for d in M.DERIVADAS.values() for p in d.get("planos", ()))
    checar(u"e toda estrutura derivada (`rectum` nao esta no TS_MAP)",
           saidas and saidas <= nomes and "rectum" not in M.TS_MAP,
           u"%s" % sorted(saidas))
    checar(u"nada esta assinado num acervo novo",
           not e["origem"]["assinadas"], str(e["origem"]["assinadas"]))

    f = P.espelho(3.0, engine=_MotorFalso, base=base, tabela={})
    por = dict((x["estrutura"], x) for x in f["estruturas"])
    checar(u"motor falso: a estrutura nova aparece", "orgao_novo" in por,
           str(sorted(por)))
    checar(u"  e o composto novo, como composto",
           (por.get("par_novo") or {}).get("origem", {}).get("tipo") == "composta")
    g = [x for x in f["suavizacao"]["grupos"] if x["tabela_mm"] == 4.0]
    checar(u"  o grupo de borda leva o NOME da constante do motor",
           bool(g) and g[0]["rotulos"] == ["borda_nova"],
           str(f["suavizacao"]["grupos"]))
    checar(u"  e o milimetro sai da funcao dele (4 x 3 / 2 = 6)",
           bool(g) and abs(g[0]["efetivo_mm"] - 6.0) < 1e-9,
           str(g and g[0]["efetivo_mm"]))
    ent = (por.get("orgao_novo") or {}).get("entregue", {})
    checar(u"  o recorte e a margem novos chegam a linha",
           ent.get("recorte", {}).get("marcos") == ["marco_novo"]
           and ent.get("margem_mm") == 3.0, str(ent))
    checar(u"  e as regras da serie sao as dele",
           f["suavizacao"]["fina_mm"] == 9.0
           and f["suavizacao"]["divisor_do_raio"] == 7.0,
           u"%s / %s" % (f["suavizacao"]["fina_mm"],
                         f["suavizacao"]["divisor_do_raio"]))


def teste_a_suavizacao_do_espelho_e_a_do_motor():
    secao(u"a suavizacao do espelho e a que o motor aplica")
    import engine as M
    import radai_provenance as P
    base = tempfile.mkdtemp(prefix="proc_")
    sem_tabela = sorted(n for n in M.TS_MAP if n not in M.SUAVIZACAO)[:1]
    amostra = ["heart", "femur_left", "liver", "vertebrae_T10",
               "kidney_cyst_left"] + sem_tabela
    derivacao = set(M.DERIVADAS) | set(
        p[3] for d in M.DERIVADAS.values() for p in d.get("planos", ()))
    for cursor in (1.0, 1.5, 0.5, 0.0):
        e = P.espelho(cursor, engine=M, base=base, tabela={})
        por = dict((x["estrutura"], x) for x in e["estruturas"])
        ruins = []
        for n in amostra:
            if n not in por:
                ruins.append(u"%s ausente" % n)
                continue
            vi = por[n]["suavizacao"]["efetivo_mm"]
            vm = M.suavizacao_de(n, cursor)
            if abs(vi - vm) > 1e-9:
                ruins.append(u"%s: tela %.3f, motor %.3f" % (n, vi, vm))
        checar(u"cursor %.1f: cada estrutura leva o que o motor aplica" % cursor,
               not ruins, u"; ".join(ruins))
        ruins = []
        for g in e["suavizacao"]["grupos"]:
            ex = g["exemplos"][0]
            if ex in derivacao:
                continue
            if abs(g["efetivo_mm"] - M.suavizacao_de(ex, cursor)) > 1e-9:
                ruins.append(u"%s" % g["rotulos"])
        checar(u"cursor %.1f: e cada grupo de borda tambem" % cursor,
               not ruins, u"; ".join(ruins))
    e = P.espelho("1.0", engine=M, base=base, tabela={})
    heart = [x for x in e["estruturas"] if x["estrutura"] == "heart"][0]
    checar(u"com o cursor de fabrica (1,0) o coracao NAO sai com o valor da "
           u"tabela", abs(heart["suavizacao"]["efetivo_mm"]
                          - M.SUAVIZACAO["heart"]) > 1e-6,
           u"%.3f" % heart["suavizacao"]["efetivo_mm"])


def _saida_do_build(ret):
    for x in (ret if isinstance(ret, (list, tuple)) else (ret,)):
        try:
            if x and os.path.isfile(str(x)):
                return str(x)
        except (TypeError, ValueError):
            pass
    return ""


def teste_a_derivacao_e_medida_no_motor():
    secao(u"a suavizacao da derivacao, medida no motor")
    import numpy as np
    import engine as M
    import radai_geom
    import radai_provenance as P
    sys.path.insert(0, AQUI)
    from datetime import datetime
    from make_test_series import escreve_serie

    base = tempfile.mkdtemp(prefix="proc_der_")
    serie = os.path.join(base, "FANTOMA", "CT")
    escreve_serie(serie, "FANTOMA", datetime.now(), 20)
    forma = tuple(reversed(M.load_sitk(serie).GetSize()))
    colon = np.zeros(forma, bool)
    colon[4:16, 20:40, 20:40] = True
    reto = np.zeros(forma, bool)
    reto[4:8, 22:36, 22:36] = True
    colon &= ~reto
    mae = sorted(M.DERIVADAS)[0] if M.DERIVADAS else "colon"
    filha = [p[3] for p in M.DERIVADAS.get(mae, {}).get("planos", ())][:1] \
        or ["rectum"]

    def _derivadas_dubladas(masks, grade, log=None, protegidas=()):
        masks[filha[0]] = reto
        return [filha[0]]

    chamadas = []
    orig_der, orig_cj = M.aplicar_derivadas, radai_geom.suavizar_conjunto

    def _espia(partes, mm, grade, *a, **k):
        chamadas.append((sorted(partes), mm))
        return orig_cj(partes, mm, grade, *a, **k)

    for cursor in (1.0, 1.5):
        del chamadas[:]
        M.aplicar_derivadas, radai_geom.suavizar_conjunto = \
            _derivadas_dubladas, _espia
        ret = None
        try:
            ret = M.build_rtstruct(serie, {mae: colon.copy()},
                                   tasks=["total_v3"], suavizar_mm=cursor,
                                   derivar=True)
        finally:
            M.aplicar_derivadas, radai_geom.suavizar_conjunto = \
                orig_der, orig_cj
            rs = _saida_do_build(ret)
            if rs and os.path.dirname(rs).startswith(tempfile.gettempdir()):
                shutil.rmtree(os.path.dirname(rs), ignore_errors=True)
        par = [c for c in chamadas if mae in c[0] and filha[0] in c[0]]
        checar(u"cursor %.1f: o motor suavizou a mae e a derivada JUNTAS"
               % cursor, bool(par), str(chamadas)[:200])
        if not par:
            continue
        mm = par[0][1]
        e = P.espelho(cursor, engine=M, base=base, tabela={})
        por = dict((x["estrutura"], x) for x in e["estruturas"])
        for n in (mae, filha[0]):
            dito = por[n]["suavizacao"]["efetivo_mm"]
            if isinstance(mm, dict):
                medido = float(mm.get(n, float("nan")))
            else:
                medido = float(mm)
            checar(u"cursor %.1f: `%s` -- o espelho diz o que o motor passou"
                   % (cursor, n), abs(dito - medido) < 1e-9,
                   u"espelho %.3f, motor %.3f -- DERIVADA_USA_O_CURSOR=%s"
                   % (dito, medido, P.DERIVADA_USA_O_CURSOR))


def teste_o_espelho_e_o_curar_concordam():
    secao(u"o espelho e o curar concordam sobre a origem")
    import numpy as np
    import engine as M
    import radai_provenance as P
    cheia = np.ones((4, 4, 4), dtype=bool)
    tabela = {
        "liver": {"estrutura": "liver", "modelo": "cads", "motivo": u"teste",
                  "assinado_por": u"bateria", "assinado_em": u"2026-09-22"},
        "spleen": {"estrutura": "spleen", "modelo": "cads", "motivo": u"rascunho",
                   "assinado_por": u""},
        "seminal_vesicles": {"estrutura": "seminal_vesicles", "modelo": "ts",
                             "motivo": u"o nosso", "assinado_por": u"bateria"},
    }
    nomes = ("liver", "spleen", "seminal_vesicles", "rectum")
    nossas = dict((n, cheia.copy()) for n in nomes)
    motores = {"cads": dict((n, cheia.copy()) for n in nomes)}
    with _TabelasDe(M, _VEICULO_MELHOR, _VEICULO_AMBOS):
        _f, origem = M.curar(dict(nossas), motores, tabela=tabela)
        e = P.espelho(1.0, engine=M, tabela=tabela)
    por = dict((x["estrutura"], x) for x in e["estruturas"])
    for n in ("liver", "spleen", "seminal_vesicles"):
        o = (por.get(n) or {}).get("origem") or {}
        diz = (o.get("motor") or {}).get("chave") if o.get("tipo") == "outro_motor" \
            else M.FONTE_PADRAO
        checar(u"`%s`: o espelho diz %s, o curar escolheu %s"
               % (n, diz, origem.get(n)), diz == origem.get(n))
    checar(u"a linha assinada aparece como ASSINADA no espelho",
           bool(((por.get("liver") or {}).get("origem") or {}).get("assinada")))
    checar(u"e a comparacao aberta do reto aparece",
           bool(((por.get("rectum") or {}).get("origem") or {})
                .get("comparacao_com")), str((por.get("rectum") or {}).get("origem")))


def teste_a_licenca_viaja_com_o_motor():
    secao("a licenca viaja com o motor")
    import radai_provenance as P
    for k in ("ts", "cads", "vista", "derivada"):
        checar(u"`%s` declara licenca" % k,
               bool(P.MOTORES[k].get("licenca")), str(P.MOTORES[k]))
    v = P.MOTORES["vista"]
    checar(u"o segundo motor declara a licenca dele",
           "NVIDIA" in v["licenca"], v["licenca"])
    checar(u"e ela nao e marcada como restrita (uso comercial permitido)",
           not v.get("restrito"), repr(v.get("restrito")))
    checar(u"nenhum motor da tabela e restrito hoje",
           not [k for k, m in P.MOTORES.items() if m.get("restrito")],
           repr([k for k, m in P.MOTORES.items() if m.get("restrito")]))
    with open(_componentes.fonte("app/radai_provenance_screen.py"),
              encoding="utf-8", errors="replace") as _f:
        tela = _f.read()
    checar(u"e a tela ainda sabe pintar um motor restrito",
           "restrito" in tela)
    checar(u"e o TotalSegmentator NAO e restrito",
           not P.MOTORES["ts"].get("restrito"))


def teste_nenhum_motor_anuncia_sufixo_aposentado():
    secao(u"nenhum motor anuncia sufixo aposentado")
    import radai_provenance as P
    import radai_sets as S
    aposentados = set(s.lower() for s in S.SUFIXOS_APOSENTADOS)
    maus = dict((k, m.get("sufixo")) for k, m in P.MOTORES.items()
                if str(m.get("sufixo") or "").lower() in aposentados)
    checar(u"nenhum sufixo de MOTORES está em SUFIXOS_APOSENTADOS", not maus,
           maus)
    checar(u"  e a derivada leva o sufixo do conjunto entregue (`_ai`)",
           P.MOTORES["derivada"].get("sufixo") == S.POR_COD["oar"]["sufixo"],
           P.MOTORES["derivada"].get("sufixo"))
    checar(u"  e continua dizendo que é derivada por marco",
           u"marco" in P.MOTORES["derivada"].get("nome", u""))


def teste_a_versao_declarada_e_a_que_roda():
    secao("a versao declarada e a que roda")
    import io as _io
    import json as _json
    import os as _os
    import re as _re
    raiz = _componentes.raiz_da_suite()

    req = _io.open(_os.path.join(raiz, "build", "requirements-demo.txt"),
                   encoding="utf-8-sig", errors="replace").read()
    m = _re.search(r"^TotalSegmentator==([0-9.]+)", req, _re.M)
    checar(u"o requirements pina o TotalSegmentator", m is not None)
    if not m:
        return
    pino = m.group(1)

    bib = _json.load(_io.open(
        _os.path.join(raiz, "app", "data", "bibliography.json"),
        encoding="utf-8"))
    ts = [x for x in bib.get("modelos", ())
          if x.get("nome", "").startswith("TotalSegmentator")]
    checar(u"a bibliografia declara o TotalSegmentator", bool(ts))
    if not ts:
        return
    nome = ts[0]["nome"]
    decl = _re.search(r"([0-9]+\.[0-9]+)", nome)
    checar(u"e o nome dela traz a versao", decl is not None, nome)
    if not decl:
        return
    checar(u"e ela e a versao pinada", pino.startswith(decl.group(1)),
           u"a tela diz %r e o pino e %r — a tela de procedencia atribuiria "
           u"o contorno a um modelo que nao o fez" % (nome, pino))

    not_ = _io.open(_os.path.join(raiz, "NOTICE"),
                    encoding="utf-8", errors="replace").read()
    mv = _re.search(r"^\s*Versao\s+([0-9.]+)", not_, _re.M)
    checar(u"o NOTICE declara a versao do TotalSegmentator", mv is not None)
    if mv:
        checar(u"e ela e a mesma do pino", mv.group(1) == pino,
               u"o NOTICE diz %r e o pino e %r — numa lista de atribuicao "
               u"isso credita trabalho a quem nao o fez"
               % (mv.group(1), pino))

    _art = _io.open(_os.path.join(raiz, "build", "artefatos.py"),
                    encoding="utf-8", errors="replace").read()
    ma = _re.search(r'"totalsegmentator"\s*:\s*"([0-9.]+)"', _art)
    checar(u"`artefatos.VERSOES` declara o TotalSegmentator", ma is not None)
    if ma:
        checar(u"e ela e a versao pinada", ma.group(1) == pino,
               u"`artefatos` diz %r e o pino e %r — e ESTE numero vai para a "
               u"impressao digital, entao duas estacoes de geracoes "
               u"diferentes comparariam iguais" % (ma.group(1), pino))

    import radai_tasks as _T
    espera = sorted(set(_T.nome_na_biblioteca(d["task"])
                        for d in _T.CATALOGO if d["datasets"]))
    mt = _re.search(r"^\s*Tarefas\s+(.+?)(?=\n\s*\n|\n\s{2}[A-Z])",
                    not_, _re.M | _re.S)
    checar(u"o NOTICE lista as tarefas", mt is not None)
    if mt:
        no_notice = sorted(x.strip() for x in mt.group(1).split(",")
                           if x.strip())
        faltam = sorted(set(espera) - set(no_notice))
        sobram = sorted(set(no_notice) - set(espera))
        checar(u"e a lista e a do catalogo", not faltam and not sobram,
               u"faltam=%s sobram=%s" % (faltam[:4], sobram[:4]))


def teste_le_a_tabela_que_o_motor_le():
    secao(u"a tabela assinada: o motor le, a tela nao escreve")
    import radai_provenance as P
    base = tempfile.mkdtemp(prefix="proc2_")
    with open(P.caminho(base), "w", encoding="utf-8") as f:
        json.dump({"versao": "1.0", "linhas": [
            {"estrutura": "rectum", "modelo": "cads",
             "processamento": "suave_taubin",
             "motivo": u"o CADS tem modelo dedicado",
             "assinado_por": "Medico de Teste", "assinado_em": "2026-08-23"}]},
            f, ensure_ascii=False)
    t = P.ler(base)
    checar(u"le o arquivo gravado pela versao anterior", "rectum" in t,
           str(sorted(t)))
    if "rectum" in t:
        checar(u"com o motivo intacto",
               t["rectum"]["motivo"] == u"o CADS tem modelo dedicado")
    with open(P.caminho(base), "w", encoding="utf-8") as f:
        f.write("{{{ nao sou json")
    checar(u"tabela corrompida devolve vazio em vez de levantar",
           P.ler(base) == {}, "")
    checar(u"e o modulo nao escreve mais a tabela",
           not hasattr(P, "gravar"),
           u"`gravar` sem tela que o chame e a porta que alguem religa")


def _app_da_tela(config):
    from fastapi import FastAPI
    import radai_provenance_screen as T
    app = FastAPI()
    T.montar(app, config)
    return app


def teste_a_tela_e_so_leitura():
    secao(u"a tela de procedencia e so leitura")
    import radai_provenance_screen as T
    p = T.pagina()
    baixa = p.lower()
    checar(u"a pagina nao tem controle de escolha",
           "<select" not in baixa and "type=\"checkbox\"" not in baixa
           and "type=\"range\"" not in baixa)
    checar(u"nem botao de salvar ou assinar",
           "salvar" not in baixa and "assinar" not in baixa
           and "<button" not in baixa)
    checar(u"e o script nao faz POST",
           "method:'post'" not in baixa.replace(" ", "")
           and "method:\"post\"" not in baixa.replace(" ", ""))
    try:
        app = _app_da_tela({})
    except Exception as e:
        checar(u"a tela monta num FastAPI", False, u"%s: %s" % (type(e).__name__, e))
        return
    escrita = sorted("%s %s" % (sorted(r.methods), r.path) for r in app.routes
                     if getattr(r, "methods", None)
                     and (set(r.methods) & {"POST", "PUT", "DELETE", "PATCH"}))
    checar(u"nenhuma rota de escrita", not escrita, u"; ".join(escrita))


def teste_nenhum_numero_digitado_na_tela():
    secao(u"a tela de procedencia nao escreve numero de suavizacao")
    import re
    import radai_provenance_screen as T
    p = T.pagina()
    achados = re.findall(r"\d+(?:[.,]\d+)?\s*mm\b", p)
    checar(u"nenhum `N mm` escrito na pagina, nem no script",
           not achados, str(achados[:5]))
    from html.parser import HTMLParser

    class _Texto(HTMLParser):
        def __init__(self):
            HTMLParser.__init__(self)
            self.pula, self.partes = 0, []

        def handle_starttag(self, tag, attrs):
            if tag in ("style", "script"):
                self.pula += 1

        def handle_endtag(self, tag):
            if tag in ("style", "script"):
                self.pula -= 1

        def handle_data(self, data):
            if not self.pula:
                self.partes.append(data)

    _t = _Texto()
    _t.feed(p)
    visivel = u" ".join(_t.partes)
    decimais = re.findall(r"\d+[.,]\d+", visivel)
    checar(u"e nenhum decimal no texto (o 1,5 que envelheceu era um)",
           not decimais, str(decimais[:5]))


def teste_a_rota_usa_o_cursor_em_uso():
    secao(u"a rota do espelho usa o cursor em uso")
    try:
        from starlette.testclient import TestClient
    except Exception as e:
        checar(u"cliente de teste disponivel", False, u"%s" % e)
        return
    import engine as M
    base = tempfile.mkdtemp(prefix="proc_")
    arq = os.path.join(base, "t.config")
    with open(arq, "w", encoding="utf-8") as f:
        f.write(u"# teste\nSUAVIZAR_MM=2.0\n")
    uso = {"SUAVIZAR_MM": "1.0"}
    app = _app_da_tela({"caminho": arq, "em_uso": lambda: dict(uso),
                        "padroes": {"SUAVIZAR_MM": "1.0"}})
    c = TestClient(app, raise_server_exceptions=False)
    for v in ("1.0", "0.5"):
        uso["SUAVIZAR_MM"] = v
        d = c.get("/api/procedencia").json()
        checar(u"cursor %s: a API responde sem erro" % v, not d.get("erro"),
               str(d.get("erro")))
        if d.get("erro"):
            continue
        s = d["suavizacao"]
        checar(u"cursor %s: a API usa o cursor em uso" % v,
               abs(s["cursor_mm"] - float(v)) < 1e-9, str(s["cursor_mm"]))
        checar(u"cursor %s: e diz que ele veio do processo" % v,
               s.get("origem") == "processo", str(s.get("origem")))
        heart = [x for x in d["estruturas"] if x["estrutura"] == "heart"][0]
        checar(u"cursor %s: o coracao sai com o que o motor aplica" % v,
               abs(heart["suavizacao"]["efetivo_mm"]
                   - M.suavizacao_de("heart", float(v))) < 1e-9,
               u"%.3f" % heart["suavizacao"]["efetivo_mm"])
        checar(u"cursor %s: e o do arquivo aparece como o que vale ao reiniciar" % v,
               s["no_arquivo_mm"] == 2.0 and s["fabrica_mm"] == 1.0,
               u"arquivo %s fabrica %s" % (s["no_arquivo_mm"], s["fabrica_mm"]))


def teste_as_linhas_do_arranque():
    secao(u"as linhas do log do arranque")
    import engine as M
    import radai_provenance as P
    base = tempfile.mkdtemp(prefix="proc_")
    L = P.linhas_para_arranque("1.0", fabrica="1.0", engine=M, base=base)
    t = u"\n".join(L)
    checar(u"so ASCII (o console do vigia e cp850)",
           all(ord(ch) < 128 for ch in t),
           u"".join(sorted(set(ch for ch in t if ord(ch) >= 128))))
    checar(u"diz o cursor em uso e o de fabrica",
           u"cursor 1.0" in t and u"fabrica 1.0" in t, L[0][:120])
    liver = P._mm(M.suavizacao_de("liver", 1.0))
    checar(u"e quanto vale o grupo do figado com este cursor (%s mm)" % liver,
           (u"parenquima %s mm" % liver) in t, L[0][:200])
    L2 = P.linhas_para_arranque("0.5", fabrica="1.0", engine=M, base=base)
    checar(u"outro cursor, outro numero",
           (u"parenquima %s mm" % P._mm(M.suavizacao_de("liver", 0.5)))
           in u"\n".join(L2), L2[0][:200])
    checar(u"sem tabela assinada, diz que vale o padrao de fabrica",
           u"nenhuma linha assinada" in t)
    with open(P.caminho(base), "w", encoding="utf-8") as f:
        json.dump({"linhas": [{"estrutura": "liver", "modelo": "cads",
                               "motivo": "x", "assinado_por": "bateria",
                               "assinado_em": "2026-09-22 10:00"}]}, f)
    t3 = u"\n".join(P.linhas_para_arranque("1.0", fabrica="1.0", engine=M,
                                            base=base))
    checar(u"com tabela assinada, a linha assinada e anunciada",
           u"ATENCAO" in t3 and u"liver -> cads" in t3, t3[-240:])
    aten = [x for x in t3.split(u"\n") if u"ATENCAO" in x]
    checar(u"  e a linha diz o CAMINHO do arquivo, e nao so o nome",
           aten and P.ascii_(P.caminho(base)) in aten[0], (aten or [u""])[0][:240])
    checar(u"  e como voltar ao padrao de fabrica (o motor rele a cada serie)",
           aten and u"apague ou renomeie este arquivo" in aten[0]
           and u"rele a cada serie" in aten[0], (aten or [u""])[0][-160:])
    checar(u"e nenhuma linha sai sem conteudo", all(x.strip() for x in L))
    serie = [x for x in L if x.startswith(u"suavizacao na serie")]
    checar(u"a regra da serie fala em RAIO INSCRITO, que e o que o motor mede",
           serie and u"raio inscrito" in serie[0] and u"espessura" not in serie[0],
           serie[0][:160] if serie else u"sem a linha")
    cons = [x for x in L if x.startswith(u"construcoes do FULL, na ordem:")]
    checar(u"ha uma linha com as construcoes do FULL, na ordem do motor",
           _linha_do_full_ok(cons), cons[0][:240] if cons else u"sem a linha")
    cor = [x for x in L if x.startswith(u"coracao:")]
    checar(u"  e a do coracao: os vasos absorvidos, e a descendente DENTRO dos "
           u"grandes vasos (B3)", cor and u"inferior_vena_cava" in cor[0]
           and u"descendente dentro de great_arteries" in cor[0]
           and u"so a descendente" not in cor[0],
           cor[0][:240] if cor else u"sem a linha")
    oar_l = [x for x in L if x.startswith(u"OAR: ")]
    checar(u"  e a do OAR: gravado das mascaras finais do FULL antes dele, "
           u"igual ao FULL (e nao copiado do arquivo)",
           oar_l and u"gravadas das mascaras finais do FULL antes dele" in
           oar_l[0] and u"copiadas sem reescrever" not in oar_l[0],
           oar_l[0][:200] if oar_l else u"sem a linha")
    alem = [x for x in L if x.startswith(u"alem da suavizacao:")]
    checar(u"  e a das margens diz que a aorta sai recortada depois dela",
           alem and u"depois dela a aorta sai recortada de" in alem[0]
           and u"esophagus" in alem[0] and u"trachea" in alem[0],
           alem[0][:240] if alem else u"sem a linha")
    esp = P.espelho("1.0", fabrica="1.0", engine=M, base=base)
    ao = [x for x in esp["estruturas"] if x["estrutura"] == "aorta"]
    checar(u"  e a linha da aorta no espelho leva o recorte",
           ao and "trachea" in (ao[0]["entregue"].get(
               "recortada_depois_da_margem") or ()), str(ao[:1])[:200])
    novas = dict((x["estrutura"], x) for x in esp["estruturas"]
                 if x["estrutura"] in ("iliac_crest_left",
                                       "iliac_crest_right", "anus"))
    checar(u"  e as estruturas novas do OAR aparecem como construidas, no OAR",
           sorted(novas) == ["anus", "iliac_crest_left", "iliac_crest_right"]
           and all(v["origem"]["tipo"] == "construida"
                   and v["entregue"].get("no_oar") for v in novas.values()),
           str(sorted(novas)))
    import types
    _SemRegistro = types.SimpleNamespace(**dict(
        (k, v) for k, v in vars(M).items()
        if not k.startswith("__") and k not in ("CONSTRUCOES",
                                                "ORDEM_DO_FULL")))
    L_i = P.linhas_para_arranque("1.0", fabrica="1.0", engine=_SemRegistro,
                                 base=base)
    cons_i = [x for x in L_i if x.startswith(u"construcoes do FULL, na ordem:")]
    checar(u"ISCA: sem o registro do motor, a linha do FULL nao existe "
           u"(reprovaria) e volta a do entregue",
           not _linha_do_full_ok(cons_i)
           and any(x.startswith(u"construcoes do entregue:") for x in L_i),
           u" | ".join(L_i)[-240:])
    class _Quebrado(object):
        pass
    L4 = P.linhas_para_arranque("1.0", engine=_Quebrado)
    checar(u"motor quebrado vira uma linha, e nao uma excecao",
           len(L4) == 1 and u"espelho nao montado" in L4[0], str(L4))


def _linha_do_full_ok(cons):
    if not cons:
        return False
    t = cons[0]
    pos = dict((k, t.find(k + u" (")) for k in (
        u"femur_oar", u"pericardio", u"coracao", u"bag_bowel",
        u"pele_e_parede", u"bag_bowel_oar"))
    return (all(v >= 0 for v in pos.values())
            and pos[u"pericardio"] < pos[u"coracao"] < pos[u"bag_bowel"]
            and pos[u"coracao"] < pos[u"pele_e_parede"] < pos[u"bag_bowel_oar"]
            and u"breast_oar" not in t and u"Skin; so TC" in t)


def teste_o_motor_rele_a_tabela_a_cada_serie():
    secao(u"o motor rele a tabela assinada a cada serie")
    import numpy as np
    import engine as M
    import radai_provenance as P
    arq = P.caminho()
    checar(u"o arquivo da tabela mora no acervo da bateria (nao no do operador)",
           os.environ.get("RADAI_CALIB_DIR", u"@") in arq, arq)
    cheia = np.ones((4, 4, 4), dtype=bool)
    with open(arq, "w", encoding="utf-8") as f:
        json.dump({"linhas": [{"estrutura": "liver", "modelo": "cads",
                               "motivo": "bateria", "assinado_por": "bateria"}]}, f)
    renomeado = arq + ".guardado"
    try:
        _f, o1 = M.curar({"liver": cheia.copy()}, {"cads": {"liver": cheia.copy()}})
        checar(u"com o arquivo no acervo, a serie sai com o motor assinado",
               o1.get("liver") == "cads", str(o1.get("liver")))
        os.replace(arq, renomeado)
        _f, o2 = M.curar({"liver": cheia.copy()}, {"cads": {"liver": cheia.copy()}})
        checar(u"renomeado, a serie seguinte ja volta ao padrao (sem reiniciar)",
               o2.get("liver") == M.FONTE_PADRAO, str(o2.get("liver")))
    finally:
        for p in (arq, renomeado):
            try:
                os.remove(p)
            except OSError:
                pass


def _pintar_no_node(dados):
    import shutil as _sh
    import subprocess
    node = _sh.which("node")
    if not node:
        return None
    import radai_provenance_screen as T
    prog = (u"var _els = {};\n"
            u"function _mk(i){ return _els[i] || (_els[i] = {id: i, innerHTML: '',"
            u" textContent: '', value: ''}); }\n"
            u"var document = {getElementById: _mk};\n"
            u"var window = {addEventListener: function(){}};\n"
            + T.JS +
            u"\nPR.d = %s;\n"
            u"prAvisos(); prSuav(); prOrigem(); prRegras();\n"
            u"var _por = {}; (PR.d.estruturas || []).forEach(function(e){ _por[e.estrutura] = e });\n"
            u"var _cel = {};\n"
            u"Object.keys(_por).forEach(function(k){ _cel[k] = {origem: prOrigemCelula(_por[k].origem || {}),"
            u" entregue: prEntregueCelula(_por[k].entregue || {})} });\n"
            u"console.log(JSON.stringify({avisos: _mk('pr_avisos').innerHTML,"
            u" suav: _mk('pr_suav').innerHTML, origem: _mk('pr_origem').innerHTML,"
            u" regras: _mk('pr_regras').innerHTML, celulas: _cel}));\n"
            % json.dumps(dados, ensure_ascii=False))
    d = tempfile.mkdtemp(prefix="proc_")
    alvo = os.path.join(d, "tela.js")
    with open(alvo, "w", encoding="utf-8") as f:
        f.write(prog)
    r = subprocess.run([node, alvo], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0:
        return {"erro": (r.stderr or u"")[-400:]}
    return json.loads(r.stdout.strip().splitlines()[-1])


def teste_a_tela_pinta_o_que_o_espelho_diz():
    secao(u"a tela da procedencia, executada: caminho, regua, coracao, RM")
    import engine as M
    import radai_provenance as P
    base = tempfile.mkdtemp(prefix="proc2_")
    with open(P.caminho(base), "w", encoding="utf-8") as f:
        json.dump({"linhas": [{"estrutura": "liver", "modelo": "cads",
                               "motivo": "x", "assinado_por": "bateria",
                               "assinado_em": "2026-09-23 09:00"}]}, f)
    e = P.espelho(1.0, fabrica="1.0", engine=M, base=base, limites=(0.0, 5.0))
    checar(u"o espelho leva o CAMINHO do arquivo assinado, e nao so o nome",
           e["origem"].get("arquivo_assinado_caminho") == P.caminho(base),
           str(e["origem"].get("arquivo_assinado_caminho")))
    t = _pintar_no_node(e)
    if t is None:
        print(u"  PULADO  sem node nesta maquina: a pintura da tela nao foi "
              u"executada (os dados acima foram)")
        return
    checar(u"o JS da tela roda sem erro no node", not t.get("erro"),
           str(t.get("erro"))[:300])
    if t.get("erro"):
        return
    orig = t["origem"]
    checar(u"o bloco ATENCAO mostra o caminho do arquivo em <code>",
           (u"<code>%s</code>" % P.caminho(base)) in orig, orig[:300])
    checar(u"  e diz quantas linhas, e como voltar ao padrao de fabrica",
           u"<b>1</b> <span>linha(s) assinada(s), lidas de</span>" in orig
           and u"apague ou renomeie este arquivo: o motor o relê a cada série"
           in orig, orig[-300:])
    suav = t["suav"]
    checar(u"a regua da tabela nao e mais pilula (o que se destaca e o em uso)",
           u"<span>referência da tabela</span>" not in suav
           and u"pr-nota" in suav, suav[:240])
    cel = t["celulas"]
    checar(u"o coracao diz «reconstruida; absorve:», e nao «reconstruida aorta»",
           u"reconstruída; absorve:" in (cel.get("heart") or {}).get("entregue", u""),
           (cel.get("heart") or {}).get("entregue", u"")[:200])
    lung = (cel.get("lung_left") or {}).get("origem", u"")
    checar(u"o pulmao da RM: composta na TC, e direto do modelo na total_mr",
           u"composta de" in lung and u"direto do modelo em" in lung
           and u"total_mr" in lung, lung[:240])


class _MotorQueTropeca(_MotorFalso):

    @staticmethod
    def _familia_para_refino(nome):
        raise RuntimeError(u"refino quebrado de proposito")

    @staticmethod
    def nome_clinico(nome):
        raise KeyError(nome)


def _partes(e):
    return [a.get("parte") for a in (e.get("avisos") or ())]


def teste_o_espelho_nao_engole_erro():
    secao(u"o espelho que degrada diz que degradou")
    import engine as M
    import radai_provenance as P
    import radai_provenance_screen as T
    base = tempfile.mkdtemp(prefix="proc_")

    guardado = sys.modules.get("radai_sets", "ausente")
    sys.modules["radai_sets"] = None
    try:
        e = P.espelho(1.0, engine=M, base=base, tabela={}, limites=(0.0, 5.0))
        L = P.linhas_para_arranque("1.0", fabrica="1.0", engine=M, base=base)
    finally:
        if guardado == "ausente":
            sys.modules.pop("radai_sets", None)
        else:
            sys.modules["radai_sets"] = guardado
    checar(u"radai_sets que nao responde vira AVISO",
           "conjuntos" in _partes(e), str(e.get("avisos")))
    det = [a["detalhe"] for a in e.get("avisos") or () if a["parte"] == "conjuntos"]
    checar(u"  com o erro ao lado (o tipo da excecao e o motivo)",
           bool(det) and u"Error:" in det[0] and u"radai_sets" in det[0], str(det))
    checar(u"  e o desconto fica «nao sei» (None), e nao «nao» (False)",
           e["entregue"]["desconta"] is None, repr(e["entregue"]["desconta"]))
    checar(u"  e os conjuntos ficam sem resposta, e nao vazios",
           e["suavizacao"]["conjuntos"] is None, repr(e["suavizacao"]["conjuntos"]))
    por = dict((x["estrutura"], x["entregue"]) for x in e["estruturas"])
    alvo = sorted(set(M.DESCONTADAS_DE.values()))[:1]
    ent = por.get(alvo[0], {}) if alvo else {}
    checar(u"  a estrutura que perde volume continua dizendo que perde, marcada "
           u"incerta (%s)" % (alvo[0] if alvo else u"?"),
           bool(alvo) and bool(ent.get("perde_o_que_ocupa"))
           and ent.get("desconto_incerto") is True, str(ent))
    t = u"\n".join(L)
    checar(u"  e o arranque escreve a linha de AVISO",
           any(x.startswith(u"procedencia: AVISO") and u"conjuntos" in x for x in L),
           t[:300])
    checar(u"  e nao diz que nada se suaviza: diz que nao sabe",
           u"suaviza: ?" in t, t[:400])

    class _MotorDerivacaoTorta(_MotorFalso):
        DERIVADAS = {"mae_nova": {"planos": [("so_um_campo",),
                                             (("marco",), "inf", 0.0, "filha_boa")]}}
    e1b = P.espelho(1.0, engine=_MotorDerivacaoTorta, tabela={},
                    limites=(0.0, 5.0))
    det1b = [a["detalhe"] for a in e1b.get("avisos") or ()
             if a["parte"] == "derivadas"]
    checar(u"plano de derivacao malformado vira AVISO, com a mae e o erro",
           len(det1b) == 1 and u"mae_nova" in det1b[0]
           and u"IndexError" in det1b[0], str(e1b.get("avisos")))
    checar(u"  e o plano bom da mesma mae continua sendo lido",
           any(x["estrutura"] == "filha_boa"
               and x["origem"]["tipo"] == "derivada" for x in e1b["estruturas"]),
           str([x["estrutura"] for x in e1b["estruturas"]]))
    e1c = P.espelho(1.0, engine=_MotorFalso, tabela={}, limites=(0.0, 5.0))
    checar(u"  e sem plano malformado nao ha esse aviso",
           "derivadas" not in _partes(e1c), str(e1c.get("avisos")))

    e2 = P.espelho(1.0, engine=_MotorQueTropeca, tabela={}, limites=(0.0, 5.0))
    p2 = _partes(e2)
    checar(u"o refino que levanta vira AVISO", "refino" in p2, str(p2))
    checar(u"o nome no TPS que levanta vira AVISO", "nome_tps" in p2, str(p2))
    det2 = u" ".join(a["detalhe"] for a in e2["avisos"])
    checar(u"  com quantas e o erro", u"RuntimeError" in det2
           and u"KeyError" in det2 and u"estrutura(s)" in det2, det2[:200])
    checar(u"  e UMA linha por parte, e nao uma por estrutura",
           p2.count("refino") == 1 and p2.count("nome_tps") == 1, str(p2))

    pasta = tempfile.mkdtemp(prefix="proc_")
    arq = os.path.join(pasta, "t.config")
    with open(arq, "w", encoding="utf-8") as f:
        f.write(u"# teste\nSUAVIZAR_MM=2.0\n")

    def _explode():
        raise ZeroDivisionError(u"o vigia nao respondeu")

    c = T.cursores({"caminho": arq, "em_uso": _explode,
                    "padroes": {"SUAVIZAR_MM": "1.0"}})
    checar(u"em_uso que levanta: o valor vem do arquivo, e a origem DIZ isso",
           c["origem"] == "arquivo" and str(c["em_uso"]) == "2.0", str(c))
    checar(u"  e a falha vira aviso, com o erro",
           [a["parte"] for a in c["avisos"]] == ["cursor_processo"]
           and u"ZeroDivisionError" in c["avisos"][0]["detalhe"], str(c["avisos"]))
    c2 = T.cursores({"caminho": arq, "em_uso": lambda: {"SUAVIZAR_MM": "1.0"},
                     "padroes": {"SUAVIZAR_MM": "1.0"}})
    checar(u"  e quando o vigia responde, a origem e o processo, sem aviso",
           c2["origem"] == "processo" and str(c2["em_uso"]) == "1.0"
           and not c2["avisos"], str(c2))
    try:
        from starlette.testclient import TestClient
        app = _app_da_tela({"caminho": arq, "em_uso": _explode,
                            "padroes": {"SUAVIZAR_MM": "1.0"}})
        d = TestClient(app, raise_server_exceptions=False).get(
            "/api/procedencia").json()
        checar(u"  a API leva a origem e o aviso ate a tela",
               d.get("suavizacao", {}).get("origem") == "arquivo"
               and "cursor_processo" in _partes(d), str(d.get("avisos"))[:200])
    except ImportError as ex:
        checar(u"cliente de teste disponivel", False, u"%s" % ex)

    base4 = tempfile.mkdtemp(prefix="proc2_")
    with open(P.caminho(base4), "w", encoding="utf-8") as f:
        f.write(u"{{{ nao sou json")
    e4 = P.espelho(1.0, engine=M, base=base4, limites=(0.0, 5.0))
    checar(u"a tabela assinada corrompida vira AVISO (o motor tambem nao a le)",
           "tabela" in _partes(e4), str(e4.get("avisos")))
    e5 = P.espelho(1.0, engine=M, base=tempfile.mkdtemp(prefix="proc2_"),
                   limites=(0.0, 5.0))
    checar(u"  e sem arquivo nenhum nao ha aviso (estacao que nunca assinou)",
           not e5.get("avisos"), str(e5.get("avisos")))

    import re
    js = T.JS
    m = re.search(r"function prCarregar\(\)\{(.*?)\n\}", js, re.S)
    checar(u"a tela tem onde pintar os avisos, e o carregador os pinta",
           'id="pr_avisos"' in T.PAGINA and m is not None
           and u"prAvisos()" in m.group(1), m.group(1)[:200] if m else u"")


def teste_o_entregue_do_coracao_e_o_do_motor():
    secao(u"o coracao, os vasos e a aorta: o espelho e a cadeia do FULL")
    import types
    import numpy as np
    import engine as M
    import radai_geom
    import radai_provenance as P
    import radai_sets as RS

    Z, Y, X = 40, 80, 90
    g = radai_geom.Grade((3.0, 1.0, 1.0))

    def cx(z0, z1, y0, y1, x0, x1):
        m = np.zeros((Z, Y, X), bool)
        m[z0:z1, y0:y1, x0:x1] = True
        return m

    coracao = cx(8, 25, 20, 50, 25, 55)
    asc = cx(18, 30, 12, 19, 36, 46)
    desc = cx(0, 34, 58, 66, 36, 46)
    janela = np.zeros((Z, Y, X), bool)
    janela[8:25] = True
    masks = {"heart": coracao, "aorta": asc | desc,
             "liver": cx(0, 8, 20, 60, 20, 60)}
    vasos = [str(v[0]) for v in M.VASOS_DO_CORACAO]
    for i, v in enumerate(vasos):
        x0 = 58 + 5 * i
        masks[v] = cx(0, 20, 12, 19, x0, x0 + 3)

    e = P.espelho(1.0, engine=M, tabela={}, limites=(0.0, 5.0))
    por = dict((x["estrutura"], x) for x in e["estruturas"])

    def ent(n):
        return (por.get(n) or {}).get("entregue") or {}

    def ori(n):
        return (por.get(n) or {}).get("origem") or {}

    checar(u"o coracao (Heart_ai) e dito CONSTRUIDO, pela construcao do "
           u"registro", ori("heart").get("tipo") == "construida"
           and ori("heart").get("funcao") == "_construir_coracao",
           str(ori("heart")))
    checar(u"  e o do modelo tem linha propria (`heart_model`, do modelo)",
           ori("heart_model").get("tipo") == "modelo", str(ori("heart_model")))
    rc = ent("heart").get("reconstruida") or {}
    checar(u"  com os vasos que ele absorve lidos da tabela, e o fechamento "
           u"do motor", sorted(rc.get("vasos") or []) == sorted(vasos)
           and rc.get("fechamento_mm") == float(M.FECHAMENTO_PERICARDIO_MM)
           and rc.get("com_pericardio") is True, str(rc))
    construidas = sorted(n for n in por if ori(n).get("tipo") == "construida")
    checar(u"as construidas do espelho sao as saidas do registro do motor "
           u"(Heart_ai, Pericardium, Bag_Bowel, Bag_Bowel_OAR, Femur_OAR, "
           u"Skin, ChestWall)", construidas == sorted(M.CONSTRUCOES_POR_SAIDA()),
           u"espelho %s, motor %s" % (construidas,
                                      sorted(M.CONSTRUCOES_POR_SAIDA())))
    for n in ("heart", "pericardium", "bag_bowel", "bag_bowel_oar",
              "femur_oar_left"):
        checar(u"  `%s` esta entre as construidas" % n, n in construidas)
    ruins = [n for n in por if ent(n).get("no_oar") is not
             (n in RS.PERMITIDOS_NO_OAR)]
    checar(u"«no OAR» / «so no FULL» e a lista de permitidos, estrutura por "
           u"estrutura", not ruins, str(ruins[:6]))

    _piso_de_fabrica = M.VOLUME_MINIMO_CORACAO_CM3
    M.VOLUME_MINIMO_CORACAO_CM3 = 1.0
    try:
        fora, meta = M.preparar_full(
            dict((k, v.copy()) for k, v in masks.items()), grade=g)
    finally:
        M.VOLUME_MINIMO_CORACAO_CM3 = _piso_de_fabrica
    checar(u"a cadeia do FULL construiu o Heart_ai no fantoma (o piso da R4 "
           u"baixado so em volta da chamada)", "heart" in fora,
           str(sorted(fora)[:12]))
    if "heart" not in fora:
        return
    h = np.asarray(fora["heart"], bool)
    ditas = sorted(n for n in masks if ent(n).get("absorvida_pelo_coracao"))
    checar(u"o espelho marca como absorvido cada vaso da tabela do motor",
           ditas == sorted(vasos), u"espelho %s, tabela %s" % (ditas,
                                                               sorted(vasos)))
    fora_do_full = [v for v in vasos if v not in fora]
    checar(u"  e no FULL cada um continua INTEIRO, com o nome dele",
           not fora_do_full, str(fora_do_full))
    nao_entrou = [v for v in vasos if (masks[v] & janela & ~h).any()]
    checar(u"  e o trecho dele no intervalo do coracao esta no Heart_ai",
           not nao_entrou, str(nao_entrou))
    ga = np.asarray(fora.get("great_arteries", np.zeros_like(h)), bool)
    checar(u"a aorta: o espelho diz «a descendente fica em great_arteries», "
           u"e nao «so a descendente»",
           ent("aorta").get("descendente_em") == ["great_arteries"]
           and not ent("aorta").get("so_a_descendente"), str(ent("aorta")))
    checar(u"  e na cadeia a descendente esta DENTRO de great_arteries, e a "
           u"ascendente da janela no Heart_ai",
           not (desc & ~ga).any() and not ((asc & janela) & ~h).any(),
           u"%d / %d voxels fora" % (int((desc & ~ga).sum()),
                                     int(((asc & janela) & ~h).sum())))
    cedem = sorted(n for n in por if ent(n).get("cede_ao_coracao"))
    checar(u"os compostos que cedem ao coracao sao os de `COMPOSTOS_MENOS`",
           cedem == sorted(c for c, cs in M.COMPOSTOS_MENOS.items()
                           if "heart" in cs), str(cedem))
    tocam = [c for c in cedem if c in fora
             and (np.asarray(fora[c], bool) & h).any()]
    checar(u"  e nenhum deles toca o Heart_ai na cadeia", not tocam,
           str(tocam))
    checar(u"o que a cadeia construiu nesta serie esta entre as construidas "
           u"do espelho", set(meta["construcoes"]) <= set(construidas),
           str(sorted(meta["construcoes"])))
    checar(u"e o que o motor nao toca continua «—» e fica so no FULL (o "
           u"figado vai ao OAR; o espelho diz)",
           not ent("liver").get("construida")
           and ent("liver").get("no_oar") is True and "liver" in fora,
           str(ent("liver")))

    sem_reg = types.SimpleNamespace(**dict(
        (k, v) for k, v in vars(M).items()
        if not k.startswith("__") and k not in ("CONSTRUCOES",
                                                "ORDEM_DO_FULL")))
    e1 = P.espelho(1.0, engine=sem_reg, tabela={}, limites=(0.0, 5.0))
    p1 = dict((x["estrutura"], x) for x in e1["estruturas"])
    checar(u"ISCA: sem o registro, o espelho volta a «so a descendente» e o "
           u"coracao deixa de ser construido (reprovaria)",
           (p1.get("aorta") or {}).get("entregue", {}).get("so_a_descendente")
           and (p1.get("heart") or {}).get("origem", {}).get("tipo")
           != "construida")
    sem_menos = types.SimpleNamespace(**dict(
        (k, v) for k, v in vars(M).items()
        if not k.startswith("__") and k != "COMPOSTOS_MENOS"))
    c2, _p, _pd = P._construcoes(sem_menos, dict(M.COMPOSTOS))
    checar(u"ISCA: sem `COMPOSTOS_MENOS`, o `cedem` sai da regra do para_oar "
           u"e diverge (reprovaria)",
           sorted(c2["cedem"]) != sorted(c for c, cs in
                                         M.COMPOSTOS_MENOS.items()
                                         if "heart" in cs), str(c2["cedem"]))

    class _ComCoracao(_MotorFalso):
        TS_MAP = dict(_MotorFalso.TS_MAP, vaso_novo={"f": ["vaso_novo"]})
        COMPOSTOS = {"par_novo": ["orgao_novo"], "tronco_novo": ["vaso_novo"]}
        VASOS_DO_CORACAO = (("vaso_novo", True),)
        FECHAMENTO_PERICARDIO_MM = 7.0

        @staticmethod
        def coracao_de_radioterapia(masks, grade, log=None):
            return None, None

    f = P.espelho(1.0, engine=_ComCoracao, tabela={}, limites=(0.0, 5.0))
    pf = dict((x["estrutura"], x["entregue"]) for x in f["estruturas"])
    checar(u"motor falso: o vaso novo da tabela aparece absorvido",
           pf.get("vaso_novo", {}).get("absorvida_pelo_coracao") is True,
           str(pf.get("vaso_novo")))
    checar(u"  e o composto dele cede ao coracao; o que nao tem vaso, nao",
           pf.get("tronco_novo", {}).get("cede_ao_coracao") is True
           and not pf.get("par_novo", {}).get("cede_ao_coracao"),
           u"%s / %s" % (pf.get("tronco_novo"), pf.get("par_novo")))
    checar(u"  e o fechamento e o dele",
           (f["entregue"]["coracao"] or {}).get("fechamento_mm") == 7.0,
           str(f["entregue"]["coracao"]))
    sem = P.espelho(1.0, engine=_MotorFalso, tabela={}, limites=(0.0, 5.0))
    checar(u"  e um motor sem `coracao_de_radioterapia` nao ganha coracao reconstruido",
           sem["entregue"]["coracao"] is None
           and not [x for x in sem["estruturas"]
                    if x["entregue"].get("absorvida_pelo_coracao")],
           str(sem["entregue"]["coracao"]))


class _MotorSemRegistro(object):

    def __init__(self, motor):
        self._m = motor

    def __getattr__(self, k):
        if k == "CONSTRUCOES":
            raise AttributeError(k)
        return getattr(self._m, k)


def _cortes_que_nao_cortam(e, entrada, saida):
    import numpy as np
    ditas = set(k for k, _m, _x in (e["entregue"].get("recortes") or ()))
    de = dict(e["entregue"].get("recorte_de") or {})
    for x in e["estruturas"]:
        r = (x.get("entregue") or {}).get("recorte")
        if r:
            ditas.add(x["estrutura"])
            if r.get("de"):
                de[x["estrutura"]] = r["de"]

    def _n(m):
        return 0 if m is None else int(np.asarray(m, bool).sum())
    ruins = []
    for n in sorted(ditas):
        if n not in saida:
            continue
        origem = de.get(n) or n
        if origem not in entrada:
            continue
        if not (_n(saida[n]) < _n(entrada[origem])):
            ruins.append(n)
    return ruins


def teste_o_recorte_e_do_femur_oar():
    secao(u"o recorte e do Femur_OAR, e o femur fica inteiro no FULL")
    import numpy as np
    import engine as M
    import radai_geom
    import radai_provenance as P
    import radai_sets as RS
    base = tempfile.mkdtemp(prefix="proc_rec_")
    e = P.espelho(1.0, engine=M, base=base, tabela={})
    por = dict((x["estrutura"], x) for x in e["estruturas"])

    def ent(n):
        return (por.get(n) or {}).get("entregue") or {}
    checar(u"o `femur_left` NAO leva a etiqueta de recorte",
           "recorte" not in ent("femur_left"), str(ent("femur_left")))
    checar(u"  e diz onde esta o recortado (`femur_oar_left`), inteiro no FULL",
           ent("femur_left").get("recortado_em") == "femur_oar_left"
           and ent("femur_left").get("no_oar") is False,
           str(ent("femur_left")))
    r = ent("femur_oar_left").get("recorte") or {}
    checar(u"o `femur_oar_left` leva o recorte, a partir do `femur_left`",
           r.get("de") == "femur_left"
           and sorted(r.get("marcos") or []) == ["hip_left", "hip_right"],
           str(r))
    checar(u"  e vai ao OAR",
           ent("femur_oar_left").get("no_oar") is True
           and "femur_oar_left" in RS.PERMITIDOS_NO_OAR)
    lista = sorted(k for k, _m, _x in e["entregue"]["recortes"])
    checar(u"a regra do recorte cita as estruturas CORTADAS",
           lista == ["femur_oar_left", "femur_oar_right"]
           and e["entregue"].get("recorte_de") == {
               "femur_oar_left": "femur_left",
               "femur_oar_right": "femur_right"}, str(lista))
    linhas = P.linhas_para_arranque(1.0, fabrica="1.0", engine=M, base=base)
    rec = [ln for ln in linhas if u"recorte (" in ln]
    checar(u"a linha do arranque diz o cortado E o orgao que fica inteiro",
           bool(rec) and u"femur_oar_left (de femur_left, que fica inteiro)"
           in rec[0] and u" femur_left no " not in rec[0],
           (rec or [u"(nenhuma)"])[0][:240])

    g = radai_geom.Grade((2.0, 1.0, 1.0))
    forma = (40, 30, 30)
    femur = np.zeros(forma, bool)
    femur[0:30, 10:16, 10:16] = True
    femur_d = np.zeros(forma, bool)
    femur_d[0:30, 10:16, 18:24] = True
    hip = np.zeros(forma, bool)
    hip[15:30, 5:9, 5:25] = True
    entrada = {"femur_left": femur, "femur_right": femur_d,
               "hip_left": hip, "hip_right": hip.copy()}
    saida, _meta = M.preparar_full(dict((k, v.copy())
                                        for k, v in entrada.items()), grade=g)
    checar(u"(fantoma) o `femur_left` sai do FULL IGUAL a entrada",
           np.array_equal(np.asarray(saida["femur_left"], bool), femur))
    ruins = _cortes_que_nao_cortam(e, entrada, saida)
    checar(u"toda estrutura que o espelho diz cortada saiu cortada do FULL",
           not ruins, str(ruins))
    velho = P.espelho(1.0, engine=_MotorSemRegistro(M), base=base, tabela={})
    isca = _cortes_que_nao_cortam(velho, entrada, saida)
    checar(u"ISCA: com o recorte de volta em `femur_left` (o espelho sem o "
           u"registro), a checagem do voxel reprova",
           "femur_left" in isca, str(isca))

    t = _pintar_no_node(e)
    if t is None:
        print(u"  PULADO  sem node nesta maquina: a pintura do recorte nao "
              u"foi executada (os dados acima foram)")
        return
    checar(u"o JS da tela roda sem erro no node", not t.get("erro"),
           str(t.get("erro"))[:300])
    if t.get("erro"):
        return
    import re

    def _cortadas_na_regra(html):
        return sorted(re.findall(
            r'<td class="est">([^<]*)</td><td><span>cortada no plano do '
            r'marco</span>', html))
    cortadas = _cortadas_na_regra(t["regras"])
    checar(u"a tela pinta a regra do recorte no `femur_oar_*`, e nao no femur",
           cortadas == ["femur_oar_left", "femur_oar_right"], str(cortadas))
    checar(u"  com o orgao de onde sai e onde vale (FULL e OAR)",
           u"<span>a partir do rótulo de</span> <code>femur_left</code>"
           in t["regras"] and re.search(
               r'<td class="est">femur_oar_left</td>.*?no FULL e no OAR',
               t["regras"]) is not None, t["regras"][:200])
    cel = t["celulas"]
    fl = (cel.get("femur_left") or {}).get("entregue", u"")
    checar(u"a celula do `femur_left` diz inteiro e o nome do recortado, sem "
           u"recorte", u"<span>inteiro; o recortado é</span> femur_oar_left"
           in fl and u"<span>recorte</span>" not in fl, fl[:240])
    ti = _pintar_no_node(velho)
    checar(u"ISCA: a tela pintada com o espelho sem o registro poe a regra no "
           u"`femur_left` (reprovaria)", bool(ti) and not ti.get("erro")
           and "femur_left" in _cortadas_na_regra(ti["regras"]),
           str(ti and _cortadas_na_regra(ti.get("regras", u""))))

    def _celulas_so_tc(cel):
        so_tc = u"<span>construída, só em TC</span>"
        return (so_tc in (cel.get("Skin") or {}).get("entregue", u""),
                so_tc in (cel.get("femur_oar_left") or {}).get("entregue", u""),
                u"<span>construída por função</span>"
                in (cel.get("femur_oar_left") or {}).get("entregue", u""))
    pele, femur_tc, femur_fn = _celulas_so_tc(cel)
    checar(u"a pele diz «construida, so em TC»; o Femur_OAR diz «construida "
           u"por funcao», sem «so em TC»", pele and not femur_tc and femur_fn,
           (cel.get("femur_oar_left") or {}).get("entregue", u"")[:200])
    import radai_provenance_screen as TELA
    js = TELA.JS
    fixa = (u" if(t.construida) h.push('<span class=\"tag aviso\"><span>"
            u"construída, só em TC</span></span>');\n")
    ini = js.index(u" if(t.construida) h.push(t.construida.so_tc === false")
    fim = js.index(u"\n", js.index(u"construída, só em TC", ini)) + 1
    try:
        TELA.JS = js[:ini] + fixa + js[fim:]
        tf = _pintar_no_node(e)
    finally:
        TELA.JS = js
    checar(u"ISCA: com a etiqueta fixa de antes, o Femur_OAR diria «so em TC» "
           u"(reprovaria)", bool(tf) and not tf.get("erro")
           and _celulas_so_tc(tf["celulas"])[1],
           str(tf and tf.get("erro")))


def teste_pele_e_parede_medidas_no_motor():
    secao(u"as construidas do espelho e a cadeia do FULL (pele, parede e cia.)")
    import types
    import numpy as np
    import engine as M
    import radai_provenance as P
    sys.path.insert(0, AQUI)
    import test_skin as S
    g, hu, masks, _x = S.montar_fantoma()
    e = P.espelho(1.0, engine=M, tabela={}, limites=(0.0, 5.0))
    por = dict((x["estrutura"], x) for x in e["estruturas"])
    constr = sorted(n for n in por
                    if por[n]["origem"]["tipo"] == "construida")
    checar(u"o espelho lista como construidas exatamente as saidas do "
           u"registro do motor", constr == sorted(M.CONSTRUCOES_POR_SAIDA()),
           u"motor %s, espelho %s" % (sorted(M.CONSTRUCOES_POR_SAIDA()),
                                      constr))
    so_tc = dict((n, bool(c.get("exige_hu"))) for c in M.CONSTRUCOES
                 for n in (c.get("saidas") or {}))
    errados = [n for n in constr
               if bool(por[n]["origem"].get("so_tc")) != so_tc.get(n)
               or bool(por[n]["entregue"].get("construida", {}).get("so_tc"))
               != so_tc.get(n)]
    checar(u"  cada uma com «so em TC» exatamente quando o registro diz que "
           u"ela le densidade", not errados, str(errados))
    fora, meta = M.preparar_full(dict(masks), grade=g, volume_hu=hu,
                                 modalidade="CT")
    checar(u"numa TC a cadeia constroi a pele (e o que ela construiu esta "
           u"no espelho)", "Skin" in meta["construcoes"]
           and set(meta["construcoes"]) <= set(constr),
           str(sorted(meta["construcoes"])))
    fora2, meta2 = M.preparar_full(dict(masks), grade=g, volume_hu=hu,
                                   modalidade="MR")
    cods_tc = [c["cod"] for c in M.CONSTRUCOES if c.get("exige_hu")]
    checar(u"e numa RM a cadeia nao faz as que leem densidade, e DIZ (o «so "
           u"em TC» e medido)",
           not any(n in meta2["construcoes"] for n in so_tc if so_tc[n])
           and all(any(c == cod and u"nao e TC" in m
                       for c, m in meta2["nao_sairam"]) for cod in cods_tc),
           str(meta2["nao_sairam"])[:240])
    checar(u"quem monta a pele e a parede e a cadeia do FULL (a construcao "
           u"`pele_e_parede` do registro)",
           any(c.get("cod") == "pele_e_parede"
               and c.get("funcao") is M._construir_pele_e_parede
               and {"Skin", "ChestWall_L", "ChestWall_R"}
               <= set(c.get("saidas") or {}) for c in M.CONSTRUCOES))
    sem_reg = types.SimpleNamespace(**dict(
        (k, v) for k, v in vars(M).items()
        if not k.startswith("__") and k not in ("CONSTRUCOES",
                                                "ORDEM_DO_FULL")))
    e_i = P.espelho(1.0, engine=sem_reg, tabela={}, limites=(0.0, 5.0))
    c_i = sorted(x["estrutura"] for x in e_i["estruturas"]
                 if x["origem"]["tipo"] == "construida")
    checar(u"ISCA: sem o registro, o espelho so conhece a pele e a parede "
           u"(reprovaria)", c_i != sorted(M.CONSTRUCOES_POR_SAIDA()), str(c_i))


def teste_o_limite_do_vigia():
    secao(u"o limite que o vigia aplica ao cursor")
    import engine as M
    import radai_provenance as P
    fonte = (u"x = _num(CFG, 'SUAVIZAR_MM', float, 0.0, 2.0)\n"
             u"y = _num(CFG, 'PORT', int, 1, 65535)\n")
    checar(u"o intervalo sai do codigo do vigia (fonte injetada)",
           P.limites_do_cursor(fonte=fonte) == (0.0, 2.0),
           str(P.limites_do_cursor(fonte=fonte)))
    try:
        lo, hi = P.limites_do_cursor()
        ok = lo < hi
    except Exception as ex:
        lo, hi, ok = 0.0, 0.0, False
        checar(u"o vigia de verdade tem o intervalo legivel", False, u"%s" % ex)
    checar(u"no vigia de verdade o intervalo existe", ok, u"%s a %s" % (lo, hi))
    if not ok:
        return
    e = P.espelho(hi + 2.0, engine=M, tabela={}, fabrica="1.0")
    s = e["suavizacao"]
    checar(u"acima do teto: o espelho usa o que o vigia aplica",
           abs(s["cursor_mm"] - hi) < 1e-9 and abs(s["lido_mm"] - (hi + 2.0)) < 1e-9,
           u"cursor %s, lido %s" % (s["cursor_mm"], s["lido_mm"]))
    heart = [x for x in e["estruturas"] if x["estrutura"] == "heart"][0]
    checar(u"  e o coracao sai com o que o motor aplica com o teto",
           abs(heart["suavizacao"]["efetivo_mm"] - M.suavizacao_de("heart", hi)) < 1e-9,
           u"%.3f" % heart["suavizacao"]["efetivo_mm"])
    checar(u"  e diz que limitou", "cursor_limite" in _partes(e), str(e.get("avisos")))
    e2 = P.espelho(lo + (hi - lo) / 2.0, engine=M, tabela={}, fabrica="1.0")
    checar(u"dentro do intervalo nao ha aviso de limite",
           "cursor_limite" not in _partes(e2), str(e2.get("avisos")))
    e3 = P.espelho(hi + 2.0, engine=M, tabela={}, fabrica="1.0",
                   no_arquivo=str(hi + 2.0))
    s3 = e3["suavizacao"]
    checar(u"o do arquivo fora do intervalo: vale ao reiniciar o que o vigia aplica",
           s3["no_arquivo_aplicado_mm"] == hi and s3["no_arquivo_mm"] == hi + 2.0,
           u"%s / %s" % (s3["no_arquivo_aplicado_mm"], s3["no_arquivo_mm"]))
    checar(u"  e o mesmo numero no processo e no arquivo da UM aviso, e nao dois",
           _partes(e3).count("cursor_limite") == 1, str(e3.get("avisos")))
    e4 = P.espelho(lo + (hi - lo) / 2.0, engine=M, tabela={}, fabrica="1.0",
                   no_arquivo=str(hi + 3.0))
    checar(u"  e o arquivo editado para fora do intervalo tambem avisa",
           e4["suavizacao"]["no_arquivo_aplicado_mm"] == hi
           and "cursor_limite" in _partes(e4), str(e4.get("avisos")))
    falhou = False
    try:
        P.limites_do_cursor(fonte=u"x = 1\n")
    except Exception:
        falhou = True
    checar(u"vigia sem a chamada: a leitura LEVANTA, e nao inventa um intervalo",
           falhou)


def _pintar_bibliotecas_no_node(js, dados):
    import shutil as _sh
    import subprocess
    node = _sh.which("node")
    if not node:
        return None
    prog = (u"var _els = {};\n"
            u"function _mk(i){ return _els[i] || (_els[i] = {id: i, innerHTML: '',"
            u" textContent: '', value: ''}); }\n"
            u"var document = {getElementById: _mk};\n"
            u"var window = {addEventListener: function(){}};\n"
            + js +
            u"\nPR.d = %s;\nprBib();\n"
            u"console.log(JSON.stringify({bib: _mk('pr_bib').innerHTML}));\n"
            % json.dumps(dados, ensure_ascii=False))
    d = tempfile.mkdtemp(prefix="proc_")
    alvo = os.path.join(d, "bib.js")
    with open(alvo, "w", encoding="utf-8") as f:
        f.write(prog)
    r = subprocess.run([node, alvo], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0:
        return {"erro": (r.stderr or u"")[-400:]}
    return json.loads(r.stdout.strip().splitlines()[-1])


def teste_as_bibliotecas_viram_informacao():
    secao(u"a procedencia recebe as bibliotecas do TotalSegmentator (v8.3)")
    import radai_provenance_screen as T
    import radai_tasks
    b = T.bibliotecas({"em_uso": lambda: {"TASKS": "total_v3 lung_nodules",
                                          "RECORTE_NO_CORPO": 1}})
    checar(u"o catalogo inteiro vem do `radai_tasks.estado`",
           len(b["tasks"]) == len(radai_tasks.estado()) and len(b["tasks"]) > 10,
           u"%d" % len(b["tasks"]))
    checar(u"  com o que a tabela mostra (e so isso)",
           all(set(t) == {"task", "rotulo", "classes", "modalidade", "mb",
                          "baixado", "rt", "achado", "permitida", "porque_nao"}
               for t in b["tasks"]))
    checar(u"o TASKS do config nao vai a tela (v8.4: o vigia e sempre AUTO)",
           "tasks_no_arquivo" not in b, sorted(b))
    checar(u"o recorte no corpo e o do processo", b["recorte_no_corpo"] == 1,
           repr(b["recorte_no_corpo"]))
    checar(u"a versao do TotalSegmentator diz algo mesmo sem o pacote",
           bool(b["versao_ts"]))
    orig = radai_tasks.estado
    try:
        def _explode():
            raise RuntimeError("catalogo em chamas")
        radai_tasks.estado = _explode
        bf = T.bibliotecas({})
    finally:
        radai_tasks.estado = orig
    checar(u"o catalogo que falha vira AVISO, e nao tabela vazia calada",
           [a["parte"] for a in bf["avisos"]] == ["bibliotecas"]
           and "chamas" in bf["avisos"][0]["detalhe"], str(bf["avisos"]))

    dados = {"bibliotecas": {"versao_ts": "2.18.0", "no_disco": 1,
                             "recorte_no_corpo": "1",
                             "tasks": [
        {"task": "total_v3", "rotulo": "Corpo inteiro", "classes": 117,
         "modalidade": "CT", "mb": 1773, "baixado": True, "rt": "nucleo",
         "achado": False, "permitida": True, "porque_nao": ""},
        {"task": "lung_nodules", "rotulo": "Nodulos pulmonares", "classes": 1,
         "modalidade": "CT", "mb": 765, "baixado": False, "rt": "fora",
         "achado": True, "permitida": True, "porque_nao": ""},
        {"task": "body", "rotulo": "Corpo (fantoma)", "classes": 2,
         "modalidade": "CT", "mb": 233, "baixado": False, "rt": "fora",
         "achado": False, "permitida": False,
         "porque_nao": "fantoma: fora de engine.TASKS_PERMITIDAS"}]}}
    r = _pintar_bibliotecas_no_node(T.JS, dados)
    if r is None:
        print(u"  PULADO  sem node nesta maquina (a pintura nao foi executada)")
    else:
        h = r.get("bib") or u""
        checar(u"a tela executa sem erro", "erro" not in r, str(r)[:200])
        checar(u"  pinta cada task", "total_v3" in h and "lung_nodules" in h)
        checar(u"  a task de achado leva o selo ACHADO, e so ela",
               h.count(u'class="tag achado"') == 1
               and h.index(u"lung_nodules") < h.index(u'class="tag achado"'),
               h[:200])
        checar(u"  diz o recorte no corpo, e nao o TASKS",
               u"RECORTE_NO_CORPO=1" in h and u"<code>TASKS</code>" not in h)
        checar(u"  e diz o que falta nesta estacao", u"falta nesta estação" in h)
        _linha_body = h[h.find(u"<td class=\"est\">body"):][:600]
        checar(u"  a task que o motor recusa aparece, marcada, e com o motivo",
               u"não roda nesta instalação" in _linha_body
               and u"fora de engine.TASKS_PERMITIDAS" in _linha_body,
               _linha_body[:200])
        checar(u"  e so ela leva a etiqueta",
               h.count(u"não roda nesta instalação") == 1)
        isca_m = T.JS.replace(u"prEsc(t.porque_nao)", u"''")
        rm = _pintar_bibliotecas_no_node(isca_m, dados) or {}
        checar(u"  (isca) sem o motivo no pintor, a checagem reprova",
               isca_m != T.JS
               and u"fora de engine.TASKS_PERMITIDAS" not in (rm.get("bib") or u""))
        checar(u"  e nao tem controle nenhum",
               u"<input" not in h and u"<select" not in h and u"<button" not in h)
        isca = T.JS.replace(
            u"(t.achado ? ' <span class=\"tag achado\">ACHADO</span>' : '')",
            u"''")
        ri = _pintar_bibliotecas_no_node(isca, dados) or {}
        checar(u"  (isca montada: o selo saiu do pintor)", isca != T.JS)
        checar(u"  (isca) sem o selo, a checagem reprova",
               (ri.get("bib") or u"").count(u'class="tag achado"') == 0)

    try:
        from starlette.testclient import TestClient
    except Exception as e:
        checar(u"cliente de teste disponivel", False, u"PULADO -- %s" % e)
        return
    c = TestClient(_app_da_tela({"em_uso": lambda: {"SUAVIZAR_MM": 1.0,
                                                    "TASKS": "total_v3",
                                                    "RECORTE_NO_CORPO": 1}}),
                   raise_server_exceptions=False)
    d = c.get("/api/procedencia").json()
    checar(u"a rota leva as bibliotecas junto",
           len((d.get("bibliotecas") or {}).get("tasks") or []) > 10,
           str(sorted(d))[:200])
    checar(u"  sem a lista de avisos dentro dela (os avisos vao ao topo)",
           "avisos" not in (d.get("bibliotecas") or {}))
    pag = c.get("/procedencia").text
    checar(u"a tela tem o bloco das bibliotecas", u'id="pr_bibliotecas"' in pag)
    checar(u"  e diz que nada ali e configuravel", u"Nada aqui é configurável" in pag)


def main():
    print("test_provenance | o espelho do codigo e a tabela assinada")
    try:
        import numpy
        import engine
    except Exception as e:
        print("  runtime sem numpy/motor (%s)" % type(e).__name__)
        print("\n" + "=" * 64)
        print("OK: 0 checagens (runtime incompleto)")
        print("=" * 64)
        return 0
    testes = [teste_linha_sem_assinatura_nao_manda,
              teste_assinar_de_volta_para_o_nosso_reverte,
              teste_o_log_distingue_assinada_de_padrao,
              teste_o_espelho_sai_das_tabelas_do_motor,
              teste_a_suavizacao_do_espelho_e_a_do_motor,
              teste_a_derivacao_e_medida_no_motor,
              teste_o_espelho_e_o_curar_concordam,
              teste_a_licenca_viaja_com_o_motor,
              teste_nenhum_motor_anuncia_sufixo_aposentado,
              teste_a_versao_declarada_e_a_que_roda,
              teste_le_a_tabela_que_o_motor_le,
              teste_a_tela_e_so_leitura,
              teste_nenhum_numero_digitado_na_tela,
              teste_as_bibliotecas_viram_informacao,
              teste_a_rota_usa_o_cursor_em_uso,
              teste_as_linhas_do_arranque,
              teste_o_motor_rele_a_tabela_a_cada_serie,
              teste_a_tela_pinta_o_que_o_espelho_diz,
              teste_o_espelho_nao_engole_erro,
              teste_o_entregue_do_coracao_e_o_do_motor,
              teste_o_recorte_e_do_femur_oar,
              teste_pele_e_parede_medidas_no_motor,
              teste_o_limite_do_vigia]
    todos = set(k for k, v in globals().items()
                if k.startswith("teste_") and callable(v))
    fora = sorted(todos - set(f.__name__ for f in testes))
    checar("todo teste do arquivo esta na lista do main()", not fora,
           ", ".join(fora))
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
