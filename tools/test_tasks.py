# -*- coding: utf-8 -*-
import shutil
import os
import sys
import tempfile

AQUI = os.path.dirname(os.path.abspath(__file__))
APP = os.path.join(os.path.dirname(AQUI), "app")
sys.path.insert(0, APP)

import radai_tasks as T

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _cleanup
_cleanup.adotar_prefixo('radai_ac_tasks')
_cleanup.adotar_prefixo('radai_pesos_')
_cleanup.adotar_prefixo('radai_dcm_')

import tempfile as _tempfile
import _componentes
os.environ["RADAI_CALIB_DIR"] = _tempfile.mkdtemp(prefix="radai_ac_tasks_")



OK = FALHAS = 0


def _pino_do_totalsegmentator():
    import re
    caminho = os.path.join(os.path.dirname(AQUI), "build",
                           "requirements-demo.txt")
    try:
        with open(caminho, encoding="utf-8-sig", errors="replace") as f:
            m = re.search(r"^TotalSegmentator==([0-9][0-9.]*)", f.read(), re.M)
        return m.group(1) if m else u"?"
    except OSError:
        return u"?"


def secao(t):
    print("\n== %s ==" % t)


def checar(nome, cond, detalhe=""):
    global OK, FALHAS
    if cond:
        OK += 1
        print("  ok     %s" % nome)
    else:
        FALHAS += 1
        print("  FALHA  %s  [%s]" % (nome, detalhe))


def teste_catalogo_coerente():
    secao("catalogo: forma dos dados")
    checar("tem tasks", len(T.CATALOGO) >= 10, str(len(T.CATALOGO)))
    checar("indice bate com a lista", len(T.POR_NOME) == len(T.CATALOGO))
    nomes = [d["task"] for d in T.CATALOGO]
    checar("sem nome repetido", len(set(nomes)) == len(nomes))
    for d in T.CATALOGO:
        t = d["task"]
        checar("%s: tem rotulo em portugues" % t, len(d["rotulo"]) > 5, d["rotulo"])
        checar("%s: tem numero de classes" % t, d["classes"] >= 1, str(d["classes"]))
        checar("%s: modalidade e CT ou MR" % t, d["modalidade"] in ("CT", "MR"),
               d["modalidade"])
        if t in T.EXIGEM_TS:
            checar("%s: nao existe neste pacote, entao nao inventa dataset" % t,
                   d["datasets"] == [], str(d["datasets"]))
        else:
            checar("%s: tem ao menos um dataset" % t, len(d["datasets"]) >= 1)
        checar("%s: datasets sao numeros" % t,
               all(isinstance(n, int) for n in d["datasets"]), str(d["datasets"]))
    for t, v in T.EXIGEM_TS.items():
        checar("%s: esta em EXIGEM_TS e declara a versao" % t,
               isinstance(v, str) and v[0].isdigit(), str(v))
        checar("%s: e esta mesmo no catalogo" % t, t in T.POR_NOME)


def teste_licenca_marcada():
    secao("catalogo: licenca")
    com = [d["task"] for d in T.CATALOGO if d["comercial"]]
    checar("o campo `comercial` continua existindo no catalogo",
           all("comercial" in d for d in T.CATALOGO))
    checar("e NENHUMA task do catalogo exige chave", not com, str(com))
    _fantasma = dict(T.CATALOGO[0])
    _fantasma["comercial"] = True
    checar("  (fantoma) o campo ainda distingue comercial de livre",
           bool(_fantasma["comercial"]) and not bool(T.CATALOGO[0]["comercial"]))
    for t in (T.BASES_CT[0], "head_glands_cavities", "headneck_muscles",
              T.BASES_MR[0]):
        checar("%s e livre" % t, not T.POR_NOME[t]["comercial"])

    _alvo = T.CATALOGO[0]["task"]
    guardado = T.tem_licenca
    _com = T.POR_NOME[_alvo]["comercial"]
    try:
        T.POR_NOME[_alvo]["comercial"] = True
        T.tem_licenca = lambda: False
        try:
            T.baixar(_alvo)
            checar("(fantoma) sem licenca, baixar() recusa a comercial",
                   False, "nao levantou")
        except RuntimeError as e:
            checar("(fantoma) sem licenca, baixar() recusa a comercial",
                   "licenca" in str(e), str(e))
        except ImportError:
            checar("recusa ANTES de importar o TotalSegmentator", False,
                   "tentou importar totalsegmentator")
    finally:
        T.tem_licenca = guardado
        T.POR_NOME[_alvo]["comercial"] = _com
    checar("  e o catalogo voltou ao estado de origem",
           not T.POR_NOME[_alvo]["comercial"])

    for ruim in ("", "   ", "nvapi-1234", "abc"):
        try:
            T.gravar_licenca(ruim)
            checar("recusa chave %r" % ruim, False, "nao levantou")
        except ValueError as e:
            checar("recusa chave %r" % ruim, True)
        except ImportError:
            checar("recusa chave %r ANTES de importar o TS" % ruim, False,
                   "chegou a importar totalsegmentator")
    checar("a chave academica comeca com aca_",
           "aca_" in open(_componentes.fonte("app/radai_tasks.py"), encoding="utf-8").read())
    checar("tem_licenca nao explode sem arquivo",
           isinstance(T.tem_licenca(), bool))
    fonte = open(_componentes.fonte("app/radai_tasks.py"), encoding="utf-8").read()
    checar("a licenca vai para o config do proprio TotalSegmentator",
           "set_license_number" in fonte)
    import types as _types
    recebida = []
    _mods = {k: sys.modules.get(k) for k in ("totalsegmentator",
                                             "totalsegmentator.config")}
    _pacote = _types.ModuleType("totalsegmentator")
    _cfg = _types.ModuleType("totalsegmentator.config")
    _cfg.set_license_number = recebida.append
    _pacote.config = _cfg
    sys.modules["totalsegmentator"] = _pacote
    sys.modules["totalsegmentator.config"] = _cfg
    _tem = T.tem_licenca
    T.tem_licenca = lambda: True
    _cfg_vigia = _componentes.fonte("app/radai_watcher.config")
    _antes = (os.path.getmtime(_cfg_vigia) if os.path.isfile(_cfg_vigia)
              else None)
    try:
        T.gravar_licenca("aca_TESTE0000")
    finally:
        T.tem_licenca = _tem
        for k, v in _mods.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v
    _depois = (os.path.getmtime(_cfg_vigia) if os.path.isfile(_cfg_vigia)
               else None)
    import ast as _ast
    import inspect as _inspect
    _chamadas = {getattr(n.func, "id", getattr(n.func, "attr", ""))
                 for n in _ast.walk(_ast.parse(_inspect.getsource(
                     T.gravar_licenca))) if isinstance(n, _ast.Call)}
    checar("e NAO para o radai_watcher.config: a chave vai so ao "
           "set_license_number, e o config do vigia nao muda",
           recebida == ["aca_TESTE0000"] and _antes == _depois
           and not (_chamadas & {"open", "escrever", "gravar", "write"}),
           "%r %r" % (recebida, sorted(_chamadas)))
    try:
        T.baixar("inexistente_xyz")
        checar("baixar() recusa task desconhecida", False, "nao levantou")
    except ValueError:
        checar("baixar() recusa task desconhecida", True)


def teste_modalidade():
    secao("catalogo: CT e RM")
    mr = [d["task"] for d in T.CATALOGO if d["modalidade"] == "MR"]
    checar("ha bibliotecas de RM", len(mr) >= 1, str(mr))
    checar("a base de RM e de RM",
           T.POR_NOME[T.BASES_MR[0]]["modalidade"] == "MR")
    checar("a base de CT e de CT",
           T.POR_NOME[T.BASES_CT[0]]["modalidade"] == "CT")
    mr_livres = [d["task"] for d in T.CATALOGO
                 if d["modalidade"] == "MR" and not d["comercial"]]
    checar("ha biblioteca de RM livre", bool(mr_livres), str(mr_livres))
    checar("e a `total_mr` esta entre elas (ela e a BASE da modalidade)",
           "total_mr" in mr_livres, str(mr_livres))
    com_chave_mr = [d["task"] for d in T.CATALOGO
                    if d["modalidade"] == "MR" and d["comercial"]]
    checar("nenhuma de RM exige chave de licenca", not com_chave_mr,
           str(com_chave_mr))


def teste_recorte():
    secao("catalogo: dependencia do recorte")
    checar("head_glands_cavities recorta", "head_glands_cavities" in T.RECORTAM)
    for _b in tuple(T.BASES_CT) + tuple(T.BASES_MR):
        checar("%s NAO recorta" % _b, _b not in T.RECORTAM)
    checar("quem recorta exige o dataset do recorte",
           T.DATASET_RECORTE in T.datasets_necessarios("head_glands_cavities"),
           str(T.datasets_necessarios("head_glands_cavities")))
    checar("quem nao recorta, nao exige",
           T.DATASET_RECORTE not in T.datasets_necessarios(T.BASES_CT[0]),
           str(T.datasets_necessarios(T.BASES_CT[0])))
    checar("task desconhecida devolve lista vazia",
           T.datasets_necessarios("xyz") == [])

    checar("abdominal_muscles recorta no `body`, e nao no total de 6 mm",
           T.DATASET_BODY in T.datasets_necessarios("abdominal_muscles"),
           str(T.datasets_necessarios("abdominal_muscles")))
    checar("  e ela NAO pede o Dataset298",
           T.DATASET_RECORTE not in T.datasets_necessarios("abdominal_muscles"),
           str(T.datasets_necessarios("abdominal_muscles")))
    checar("liver_lesions declara `robust_crop`, entao e o total de 3 mm",
           T.DATASET_RECORTE_ROBUSTO in T.datasets_necessarios("liver_lesions"),
           str(T.datasets_necessarios("liver_lesions")))
    checar("teeth recorta numa TASK, e leva o peso dela E o recorte dela",
           set(T.datasets_necessarios("teeth")) == {113, 115, T.DATASET_RECORTE},
           str(T.datasets_necessarios("teeth")))
    checar("e quem recorta no comum continua no 298",
           T.datasets_necessarios("head_glands_cavities") == [775, T.DATASET_RECORTE],
           str(T.datasets_necessarios("head_glands_cavities")))

    _velho = dict(T.RECORTAM)
    try:
        T.RECORTAM = dict((k, (T.DATASET_RECORTE,)) for k in _velho)
        _errado = T.datasets_necessarios("abdominal_muscles")
        checar("  (isca) com localizador unico ela pede o dataset ERRADO",
               T.DATASET_BODY not in _errado and T.DATASET_RECORTE in _errado,
               "a isca nao mudou nada: %s" % _errado)
    finally:
        T.RECORTAM = _velho
    checar("  e a tabela voltou ao estado de origem",
           T.RECORTAM == _velho
           and T.DATASET_BODY in T.datasets_necessarios("abdominal_muscles"))

    _base = tempfile.mkdtemp(prefix="radai_pesos_")
    checar("o custo do `abdominal_muscles` inclui o localizador dele",
           T.custo_mb(["abdominal_muscles"], _base)
           == T.POR_NOME["abdominal_muscles"]["mb"] + T.CUSTO_DO_RECORTE[T.DATASET_BODY],
           str(T.custo_mb(["abdominal_muscles"], _base)))


    _naoclass = sorted(set(T.POR_NOME) - set(T.RECORTAM) - set(T.SEM_RECORTE))
    checar("toda task do catalogo esta classificada quanto ao recorte",
           not _naoclass,
           "sem resposta em RECORTAM nem em SEM_RECORTE: %s" % _naoclass)
    _ambas = sorted(set(T.RECORTAM) & set(T.SEM_RECORTE))
    checar("  e nenhuma esta nas DUAS listas", not _ambas, str(_ambas))

    _velho, _velhoS = dict(T.RECORTAM), frozenset(T.SEM_RECORTE)
    try:
        T.RECORTAM = dict((k, v) for k, v in _velho.items()
                          if k != "liver_lesions_mr")
        _orfas = sorted(set(T.POR_NOME) - set(T.RECORTAM) - set(T.SEM_RECORTE))
        checar("  (isca) sem a linha dela a trava ACUSA a task esquecida",
               _orfas == ["liver_lesions_mr"],
               "a isca nao acusou nada: %s" % _orfas)
        checar("  (isca) e ai `datasets_necessarios` esconde o 852",
               T.DATASET_RECORTE_MR not in T.datasets_necessarios("liver_lesions_mr"),
               "a isca nao mudou nada")
    finally:
        T.RECORTAM, T.SEM_RECORTE = _velho, _velhoS
    checar("  e as tabelas voltaram ao estado de origem",
           T.RECORTAM == _velho and T.SEM_RECORTE == _velhoS
           and T.DATASET_RECORTE_MR in T.datasets_necessarios("liver_lesions_mr"))

    for _t, _ids in sorted(T.RECORTAM.items()):
        if _t.endswith("_mr"):
            checar(u"`%s` recorta no localizador de RM" % _t,
                   tuple(_ids) == (T.DATASET_RECORTE_MR,), str(_ids))
        else:
            checar(u"  `%s` nao pede o localizador de RM" % _t,
                   T.DATASET_RECORTE_MR not in _ids, str(_ids))

    _div = T._recortes_divergentes()
    checar("RECORTAM bate com o `map_tasks_config` do upstream, quando ele existe",
           not _div,
           "; ".join("%s: upstream %s, tabela %s" % d for d in _div)
           or "(biblioteca ausente: nada a comparar)")


def teste_pacote_leva_os_localizadores():
    secao("catalogo: o pacote leva os localizadores de recorte")
    tasks = [d["task"] for d in T.CATALOGO if d["datasets"]]
    pacote = T.datasets_do_pacote(tasks)
    checar("sem dataset repetido", len(pacote) == len(set(pacote)),
           str(pacote))
    faltam = sorted(set(n for t in tasks for n in T.datasets_necessarios(t))
                    - set(pacote))
    checar("todo dataset exigido entra no pacote", not faltam, str(faltam))
    checar("o localizador comum (298) entra", T.DATASET_RECORTE in pacote)
    checar("o do `body` (300) entra — ele nao tem carona no `-t total`",
           T.DATASET_BODY in pacote,
           "o preparador baixa por task, e nenhuma task lista o 300")
    checar("o robusto (297) entra — idem",
           T.DATASET_RECORTE_ROBUSTO in pacote, str(pacote))

    _velho = dict(T.RECORTAM)
    _velho_rc = T.recorte_no_corpo_se_aplica
    try:
        T.RECORTAM = {}
        _sem = T.datasets_do_pacote(tasks)
        checar("  (isca) sem `RECORTAM`, o 298 e o 297 somem do pacote",
               not ({T.DATASET_RECORTE, T.DATASET_RECORTE_ROBUSTO} & set(_sem)),
               "a isca nao mudou nada: %s" % sorted(set(_sem) & {
                   T.DATASET_RECORTE, T.DATASET_RECORTE_ROBUSTO}))
        checar("  e o 300 FICA: a base recorta no corpo (23/09/2026)",
               T.DATASET_BODY in _sem, str(_sem))
        T.recorte_no_corpo_se_aplica = lambda t: (False, u"isca")
        _sem2 = T.datasets_do_pacote(tasks)
        checar("  (isca) sem `RECORTAM` E sem o recorte no corpo, os tres "
               "somem", not ({T.DATASET_RECORTE, T.DATASET_BODY,
                              T.DATASET_RECORTE_ROBUSTO} & set(_sem2)),
               "a isca nao mudou nada: %s" % sorted(set(_sem2) & {
                   T.DATASET_RECORTE, T.DATASET_BODY, T.DATASET_RECORTE_ROBUSTO}))
    finally:
        T.RECORTAM = _velho
        T.recorte_no_corpo_se_aplica = _velho_rc
    checar("  e a tabela voltou ao estado de origem",
           T.RECORTAM == _velho
           and T.DATASET_BODY in T.datasets_do_pacote(tasks))

    _prep = _componentes.fonte("build/configurar_ambiente.py")
    try:
        with open(_prep, encoding="utf-8", errors="replace") as f:
            _txt = f.read()
    except OSError:
        _txt = ""
    import ast as _ast
    try:
        _arv = _ast.parse(_txt)
        _chama = any(
            isinstance(n, _ast.Call)
            and (getattr(n.func, "attr", None) == "datasets_do_pacote"
                 or getattr(n.func, "id", None) == "datasets_do_pacote")
            for n in _ast.walk(_arv))
    except SyntaxError as _e:
        _chama, _txt = False, "nao compilou: %s" % _e
    checar("a etapa 4 do preparador CHAMA os localizadores",
           _chama,
           "sem isto o pacote sai sem o 297/300 e a estacao trava offline, "
           "com SUCESSO no log do preparo")


def teste_estado_no_disco():
    secao("catalogo: o que esta baixado")
    base = tempfile.mkdtemp(prefix="radai_pesos_")
    mentem = [d["task"] for d in T.estado(base) if d["baixado"]]
    checar("pasta vazia: nada baixado", not mentem,
           "dizem estar baixadas com a pasta vazia: %s" % ", ".join(mentem))
    checar("pasta inexistente nao explode", T.baixados(base + "_nao_existe") == set())

    os.makedirs(os.path.join(base, "Dataset775_head_glands_cavities_492subj"))
    os.makedirs(os.path.join(base, "__MACOSX"))
    open(os.path.join(base, "leia-me.txt"), "w").close()
    checar("acha o dataset pelo numero", T.baixados(base) == {775}, str(T.baixados(base)))

    e = {d["task"]: d for d in T.estado(base)}
    checar("sem o recorte, a task que recorta NAO conta como baixada",
           not e["head_glands_cavities"]["baixado"],
           str(e["head_glands_cavities"]["faltando"]))
    checar("e o que falta e o dataset do recorte",
           e["head_glands_cavities"]["faltando"] == [T.DATASET_RECORTE],
           str(e["head_glands_cavities"]["faltando"]))
    checar("mas ela nao aparece como PARCIAL (o recorte e compartilhado)",
           not e["head_glands_cavities"]["parcial"])

    os.makedirs(os.path.join(base, "Dataset298_TotalSegmentator_total_6mm_1559subj"))
    e = {d["task"]: d for d in T.estado(base)}
    checar("com o recorte, ela conta como baixada", e["head_glands_cavities"]["baixado"])

    os.makedirs(os.path.join(base, "Dataset778_headneck_muscles_part1_492subj"))
    e = {d["task"]: d for d in T.estado(base)}
    checar("meia biblioteca aparece como PARCIAL", e["headneck_muscles"]["parcial"],
           str(e["headneck_muscles"]))
    checar("e nao como baixada", not e["headneck_muscles"]["baixado"])
    os.makedirs(os.path.join(base, "Dataset779_headneck_muscles_part2_492subj"))
    e = {d["task"]: d for d in T.estado(base)}
    checar("com as duas partes, baixada", e["headneck_muscles"]["baixado"])
    checar("e nao mais parcial", not e["headneck_muscles"]["parcial"])

    r = T.resumo(base)
    contadas = [d["task"] for d in T.estado(base) if d["baixado"]]
    checar("resumo conta as baixadas", r["baixadas"] == 2,
           "%s | contou: %s" % (r, ", ".join(contadas)))
    checar("resumo diz que o recorte esta ok", r["recorte_ok"] is True, str(r))


def teste_a_lista_que_vai_rodar():
    secao(u"a lista que vai rodar: eleicao, ato declarado e repeticao")
    velho = T.baixados
    try:
        COMPLETO = set([291, 292, 293, 294, 295, 831, 832, 833, 834, 835])
        SO_V2 = set([291, 292, 293, 294, 295])
        PREF, RES = T.BASES_CT[0], T.BASES_CT[-1]

        T.baixados = lambda base=None: set(COMPLETO)
        d = []
        checar(u"com as duas no disco, roda a preferida",
               T.lista_para_rodar([PREF], log=d.append) == [PREF])
        checar(u"  e nao escreve nada no log", not d, u" | ".join(d))

        checar(u"a reserva escrita a mao NAO vira a preferida",
               T.lista_para_rodar([RES]) == [RES],
               u"trocar o que a pessoa digitou desfaz o ato declarado")

        d = []
        r = T.lista_para_rodar([PREF, RES], log=d.append)
        checar(u"as duas juntas rodam UMA vez", r == [PREF], str(r))
        checar(u"  e o log diz qual foi ignorada",
               any(RES in m and "familia" in m for m in d), u" | ".join(d))
        checar(u"  e a ordem inversa respeita quem veio primeiro",
               T.lista_para_rodar([RES, PREF]) == [RES],
               str(T.lista_para_rodar([RES, PREF])))

        T.baixados = lambda base=None: set(SO_V2)
        d = []
        r = T.lista_para_rodar([PREF], log=d.append)
        checar(u"sem o peso da preferida, roda a reserva", r == [RES], str(r))
        checar(u"  e a queda e ESCRITA no log",
               any(RES in m and PREF in m for m in d), u" | ".join(d))

        T.baixados = lambda base=None: set(COMPLETO)
        pedido = ["lung_vessels", PREF, "teeth"]
        checar(u"o que nao e base passa intacto e na ordem",
               T.lista_para_rodar(pedido) == pedido, str(pedido))
        checar(u"a base de RM nao colide com a de TC",
               T.lista_para_rodar([PREF, T.BASES_MR[0]])
               == [PREF, T.BASES_MR[0]])
        checar(u"lista vazia devolve lista vazia",
               T.lista_para_rodar([]) == [] and T.lista_para_rodar(None) == [])
    finally:
        T.baixados = velho

    _na_tela = set(d["task"] for d in T.estado())
    for _r in sorted(T.RESERVAS):
        checar(u"a reserva `%s` nao aparece em `estado()`" % _r,
               _r not in _na_tela,
               u"a tela desenha uma caixa marcavel por linha de `estado()`")
        checar(u"  mas continua no CATALOGO", _r in T.POR_NOME,
               u"e de la que `garantir_base` descobre o que baixar")


def _casos_da_serie(f):
    out = []

    def caso(nome, tarefas, modal, esperado, frase=None):
        d = []
        try:
            r = f(tarefas, modal, log=d.append)
        except Exception as e:
            r = u"%s: %s" % (type(e).__name__, e)
        ok = (r == esperado)
        if ok and frase:
            ok = any(frase in m for m in d)
        out.append((nome, ok, u"%s -> %s | log: %s"
                    % (tarefas, r, u" | ".join(d))))
    caso(u"[total_v3] numa RM vira [total_mr]", ["total_v3"], "MR",
         ["total_mr"])
    caso(u"[total_v3, head_glands_cavities] numa RM vira [total_mr], e o log "
         u"diz que a de TC nao roda",
         ["total_v3", "head_glands_cavities"], "MR", ["total_mr"],
         frase=u"head_glands_cavities e de CT; nao roda nesta serie MR")
    caso(u"[total_mr] numa TC vira [total_v3]", ["total_mr"], "CT",
         ["total_v3"])
    caso(u"lista vazia numa TC vira [total_v3]", [], "CT", ["total_v3"])
    caso(u"lista vazia numa RM vira [total_mr]", [], "MR", ["total_mr"])
    caso(u"a base entra NA FRENTE quando ninguem a escreveu",
         ["head_glands_cavities"], "CT",
         ["total_v3", "head_glands_cavities"])
    caso(u"a base escrita depois vai para a frente",
         ["head_glands_cavities", "total_v3"], "CT",
         ["total_v3", "head_glands_cavities"])
    caso(u"a reserva declarada numa TC passa como veio (REGRA B)",
         ["total_v2"], "CT", ["total_v2"])
    caso(u"a mesma familia duas vezes roda UMA", ["total_v3", "total_v2"],
         "CT", ["total_v3"], frase=u"mesma familia")
    caso(u"task fora do catalogo passa como veio (nao e aqui que se julga)",
         ["uma_task_que_nao_existe"], "MR",
         ["total_mr", "uma_task_que_nao_existe"])
    caso(u"o apelido `total` numa RM vira a base da RM", ["total"], "MR",
         ["total_mr"])
    caso(u"«RM» e aceito como MR", ["total_v3"], "RM", ["total_mr"])
    return out


def teste_a_regra_de_base_por_modalidade():
    secao(u"a regra de base por modalidade (tasks_da_serie)")
    import inspect
    sig = inspect.signature(T.tasks_da_serie)
    checar(u"a assinatura e a combinada com a frente B",
           list(sig.parameters) == ["tarefas", "modalidade", "pasta_pesos",
                                    "log"]
           and sig.parameters["pasta_pesos"].default is None
           and sig.parameters["log"].default is None, str(sig))
    velho = T.baixados
    try:
        T.baixados = lambda base=None: set([291, 292, 293, 294, 295, 831, 832,
                                            833, 834, 835, 850, 851])
        for nome, ok, det in _casos_da_serie(T.tasks_da_serie):
            checar(nome, ok, det)
        pedidos = (["head_glands_cavities"], ["lung_vessels", "teeth"], [],
                   ["total_mr", "headneck_muscles"])
        for p in pedidos:
            for modal in ("CT", "MR"):
                r = T.tasks_da_serie(p, modal)
                base = T.base_no_disco(modal)
                novos = [t for t in r if t not in p and t != base]
                checar(u"REGRA A: %s em %s nao ganha task nova (so a base)"
                       % (p, modal), not novos, str(r))
        T.baixados = lambda base=None: set([291, 292, 293, 294, 295])
        d = []
        r = T.tasks_da_serie(["total_v3"], "CT", log=d.append)
        checar(u"sem o peso da v3 a TC roda a v2, e o log DIZ",
               r == ["total_v2"] and any("total_v2" in m and "total_v3" in m
                                         for m in d),
               u"%s | %s" % (r, u" | ".join(d)))
        T.baixados = lambda base=None: set([291, 292, 293, 294, 295, 831, 832,
                                            833, 834, 835, 850, 851])
        sem_regra = lambda tarefas, modalidade, pasta_pesos=None, log=None: \
            list(tarefas or [])
        reprovados = [n for n, ok, _ in _casos_da_serie(sem_regra) if not ok]
        checar(u"ISCA: sem a regra (a lista como veio) os casos de "
               u"modalidade reprovam",
               len(reprovados) >= 6
               and u"[total_v3] numa RM vira [total_mr]" in reprovados,
               u"%d reprovaram" % len(reprovados))
    finally:
        T.baixados = velho


def teste_normalizar():
    secao("catalogo: leitura do TASKS do config")
    B = T.BASES_CT[0]
    checar("separado por espaco",
           T.normalizar("%s head_glands_cavities" % B)
           == [B, "head_glands_cavities"])
    checar("separado por virgula",
           T.normalizar("%s,head_glands_cavities" % B)
           == [B, "head_glands_cavities"])
    checar("misturado e com espacos sobrando",
           T.normalizar("  %s ,, headneck_muscles  " % B)
           == [B, "headneck_muscles"])
    checar("descarta nome que nao existe",
           T.normalizar("%s xpto" % B) == [B])
    checar("nao repete", T.normalizar("%s %s" % (B, B)) == [B])
    checar("preserva a ordem pedida",
           T.normalizar("headneck_muscles %s" % B) == ["headneck_muscles", B])
    checar("aceita lista", T.normalizar([B]) == [B])

    for velho, novo in sorted(T.APELIDOS.items()):
        checar("o apelido `%s` vira `%s`" % (velho, novo),
               T.normalizar(velho) == [novo],
               str(T.normalizar(velho)))
        checar("  e o novo existe no catalogo", novo in T.POR_NOME)
        checar("  e o velho NAO esta no catalogo", velho not in T.POR_NOME,
               "apelido que ainda e task e nome duplicado, nao apelido")
    checar("o apelido nao duplica quando os dois vem juntos",
           T.normalizar("total %s" % B) == [B],
           str(T.normalizar("total %s" % B)))
    checar("vazio devolve vazio", T.normalizar("") == [] and T.normalizar(None) == [])
    checar("o padrao e valido", T.normalizar(T.PADRAO) == T.PADRAO)


def teste_uso_em_radioterapia():
    secao("catalogo: uso em radioterapia")
    for d in T.CATALOGO:
        checar("%s: uso em RT declarado" % d["task"], d["rt"] in T.USOS_RT, d["rt"])
        checar("%s: uso em RT tem explicacao" % d["task"], d["rt"] in T.AJUDA_RT)
    nucleo = [d["task"] for d in T.CATALOGO if d["rt"] == "nucleo"]
    for t in (T.BASES_CT[0], "head_glands_cavities", "headneck_muscles"):
        checar("%s e nucleo" % t, t in nucleo, str(nucleo))
    try:
        import engine as _E
        perm = set(_E.TASKS_PERMITIDAS)
    except Exception:
        perm = None
    if perm is not None:
        sobra = sorted(set(d["task"] for d in T.CATALOGO) - perm)
        checar("toda task oferecida e uma que o motor aceita", not sobra,
               ", ".join(sobra) or "caixa que baixa peso e depois recusa rodar")
    fora = [d["task"] for d in T.CATALOGO if d["rt"] == "fora"]
    checar("ha task classificada como `fora`", bool(fora),
           "lista vazia faria este laco passar sem medir nada")
    for t in ("hip_implant",):
        checar("%s fica de fora (nao e estrutura de planejamento)" % t, t in fora)
    checar("nenhuma comercial esta no nucleo",
           not [d for d in T.CATALOGO if d["rt"] == "nucleo" and d["comercial"]])


def teste_tamanho_declarado():
    secao("catalogo: tamanho do download")
    livres = [d for d in T.CATALOGO if not d["comercial"]]
    existem = [d for d in livres if d["task"] not in T.EXIGEM_TS]
    ainda_nao = [d for d in livres if d["task"] in T.EXIGEM_TS]
    checar("toda livre que existe neste pacote tem tamanho medido",
           all(d["mb"] > 0 for d in existem),
           str([d["task"] for d in existem if not d["mb"]]))
    checar("e a que nao existe nao tem tamanho inventado",
           all(d["mb"] == 0 for d in ainda_nao),
           str([(d["task"], d["mb"]) for d in ainda_nao if d["mb"]]))
    checar("a base e a maior",
           max(livres, key=lambda d: d["mb"])["task"] == T.BASES_CT[0],
           max(livres, key=lambda d: d["mb"])["task"])
    checar("headneck_muscles custa ~2x uma parte (sao dois datasets)",
           T.POR_NOME["headneck_muscles"]["mb"] > 1.8 * T.POR_NOME["head_muscles"]["mb"])

    base = tempfile.mkdtemp(prefix="radai_pesos_")
    c1 = T.custo_mb(["head_glands_cavities"], base)
    checar("o custo inclui o recorte compartilhado", c1 > 300, str(c1))
    c2 = T.custo_mb(["head_glands_cavities", "head_muscles"], base)
    checar("mas o recorte NAO e cobrado duas vezes",
           c2 < c1 + T.custo_mb(["head_muscles"], base),
           "%d juntas vs %d somadas em separado"
           % (c2, c1 + T.custo_mb(["head_muscles"], base)))
    checar("o que ja esta no disco nao custa nada",
           T.custo_mb([], base) == 0)

    os.makedirs(os.path.join(base, "Dataset298_x"))
    c3 = T.custo_mb(["head_glands_cavities"], base)
    checar("com o recorte ja baixado, o custo cai", c3 < c1, "%d vs %d" % (c3, c1))
    checar("task desconhecida nao entra na conta", T.custo_mb(["xpto"], base) == 0)


def teste_sugerir_dentro_do_teto():
    secao("catalogo: sugestao dentro do teto")
    base = tempfile.mkdtemp(prefix="radai_pesos_")
    checar("o nucleo do zero passa de 2 GB",
           T.sugerir(base=base)["mb_nucleo"] > 2000,
           str(T.sugerir(base=base)["mb_nucleo"]))
    nucleo_mb = T.sugerir(base=base)["mb_nucleo"]
    menor = [d["mb"] for d in T.CATALOGO
             if d["rt"] in ("util", "situacional") and d["modalidade"] == "CT"]
    folga = (min(menor) if menor else 200) * 3
    s = T.sugerir(teto_mb=nucleo_mb + folga, base=base)
    checar("respeita o teto", s["mb"] <= nucleo_mb + folga, str(s["mb"]))
    checar("comeca pelo nucleo", s["tasks"][0] == T.BASES_CT[0],
           str(s["tasks"][:3]))
    checar("nunca sugere as de fora",
           not ({"cerebral_bleed", "hip_implant"} & set(s["tasks"])), str(s["tasks"]))
    checar("nem as comerciais por padrao",
           not [t for t in s["tasks"] if T.POR_NOME[t]["comercial"]], str(s["tasks"]))
    checar("so CT por padrao",
           all(T.POR_NOME[t]["modalidade"] == "CT" for t in s["tasks"]))

    mr_mb = T.POR_NOME[T.BASES_MR[0]]["mb"]
    teto_mr = nucleo_mb + mr_mb + folga
    mr = T.sugerir(teto_mb=teto_mr, modalidades=("CT", "MR"), base=base)
    checar("pedindo RM com folga, a base de RM entra",
           T.BASES_MR[0] in mr["tasks"], str(mr["tasks"]))
    checar("sem pedir RM, ela nao entra",
           T.BASES_MR[0] not in T.sugerir(teto_mb=teto_mr,
                                          base=base)["tasks"])

    apertado = T.sugerir(teto_mb=nucleo_mb // 4, base=base)
    checar("teto apertado ainda leva a base",
           T.BASES_CT[0] in apertado["tasks"], str(apertado["tasks"]))
    checar("e avisa que estourou", apertado["estourou"] is True, str(apertado))
    checar("dizendo quanto o nucleo custa",
           apertado["mb_nucleo"] > nucleo_mb // 4,
           str(apertado["mb_nucleo"]))
    checar("teto menor leva menos bibliotecas",
           len(apertado["tasks"]) < len(s["tasks"]))
    checar("e diz o que ficou de fora", len(apertado["fora"]) > 0)
    checar("com folga, nao estoura", s["estourou"] is False, str(s))

    livre = T.sugerir(base=base)
    checar("sem teto, leva tudo que serve para RT",
           len(livre["tasks"]) >= len(s["tasks"]))
    checar("com licenca, `sugerir` continua devolvendo o nucleo",
           T.BASES_CT[0] in T.sugerir(com_licenca=True, base=base)["tasks"])

    zero = T.sugerir(teto_mb=0, base=base)
    checar("teto zero ainda entrega o nucleo",
           [d["task"] for d in T.CATALOGO if d["rt"] == "nucleo"] == zero["tasks"],
           str(zero["tasks"]))
    checar("marcado como estourado", zero["estourou"] is True)


def teste_contraste_por_estrutura():
    secao("contraste: por estrutura")
    checar("aorta nao exige (e grande o bastante)",
           T.contraste_da_estrutura("aorta") == "ajuda")
    checar("medula nao depende de contraste",
           T.contraste_da_estrutura("spinal_cord") == "nao")
    checar("pulmao tambem nao", T.contraste_da_estrutura("lung_left") == "nao")
    checar("osso tambem nao", T.contraste_da_estrutura("vertebrae_T1") == "nao")
    checar("veia porta EXIGE",
           T.contraste_da_estrutura("portal_vein_and_splenic_vein") == "exige")
    checar("carotidas EXIGEM", T.contraste_da_estrutura("carotids") == "exige")
    checar("pancreas fica pior sem",
           T.contraste_da_estrutura("pancreas") == "ajuda")
    checar("nome vazio nao explode",
           T.contraste_da_estrutura("") == "nao" and T.contraste_da_estrutura(None) == "nao")
    checar("ha uma lista das que exigem",
           len(T.estruturas_que_exigem_contraste()) >= 8)


def teste_contraste_com_nome_truncado():
    secao("contraste: nomes truncados do RTSTRUCT")
    exigem = ["portal_vein_v3D", "pulmonary_ve_v3D", "atrial_app_L_v3D",
              "brachiocepha_v3D", "brachiocep_L_v3D", "brachiocep_R_v3D",
              "common_car_L_v3D", "common_car_R_v3D", "subclavian_L_v3D",
              "subclavian_R_v3D", "A_Carotid_ai"]
    for n in exigem:
        checar("%s: exige contraste" % n,
               T.contraste_da_estrutura(n) == "exige",
               T.contraste_da_estrutura(n))
    for n in ("SpinalCord_ai", "Lung_L_ai", "Heart_v3D", "Skull_ai",
              "vertebra_t10_v3D", "rib_10_left_v3D", "Sternum_ai"):
        checar("%s: nao depende" % n, T.contraste_da_estrutura(n) == "nao",
               T.contraste_da_estrutura(n))
    for n in ("Kidney_L_ai", "Adrenal_R_v3D", "Liver_ai", "Esophagus_ai",
              "kidney_cys_L_v3D"):
        checar("%s: fica pior sem contraste" % n,
               T.contraste_da_estrutura(n) == "ajuda",
               T.contraste_da_estrutura(n))
    checar("raiz curta nao casa por prefixo",
           T.contraste_da_estrutura("col") == "nao")
    checar("mas colon casa", T.contraste_da_estrutura("colon") == "ajuda")


def teste_alertas_so_quando_se_sabe():
    secao("contraste: quando alertar")
    nomes = ["portal_vein_v3D", "SpinalCord_ai", "Kidney_L_ai"]
    checar("sem contraste: alerta so as que EXIGEM",
           [a["estrutura"] for a in T.alertas_de_contraste(nomes, False)]
           == ["portal_vein_v3D"])
    checar("com contraste: nao alerta nada",
           T.alertas_de_contraste(nomes, True) == [])
    checar("sem saber: nao alerta nada",
           T.alertas_de_contraste(nomes, None) == [])
    checar("lista vazia nao explode", T.alertas_de_contraste([], False) == [])
    checar("o alerta explica o motivo",
           "não está na imagem" in T.alertas_de_contraste(nomes, False)[0]["aviso"])

    for d in T.CATALOGO:
        checar("%s: dependencia de contraste declarada" % d["task"],
               T.CONTRASTE_TASK.get(d["task"]) in T.AJUDA_CONTRASTE,
               "ausente de CONTRASTE_TASK" if d["task"] not in T.CONTRASTE_TASK
               else str(T.CONTRASTE_TASK.get(d["task"])))
    checar("coronarias exigem contraste (e angio-TC)",
           T.CONTRASTE_TASK["coronary_arteries"] == "exige")
    checar("vaso hepatico tambem", T.CONTRASTE_TASK["liver_vessels"] == "exige")
    checar("a base e mista", T.CONTRASTE_TASK[T.BASES_CT[0]] == "misto")


def teste_deteccao_de_contraste():
    secao("contraste: leitura da tag DICOM")
    vazio = tempfile.mkdtemp(prefix="radai_dcm_")
    tem, motivo = T.detectar_contraste(vazio)
    checar("pasta sem DICOM devolve 'nao sei'", tem is None, str((tem, motivo)))
    checar("com o motivo escrito", len(motivo) > 8, motivo)
    tem, motivo = T.detectar_contraste(os.path.join(vazio, "nao_existe"))
    checar("pasta inexistente tambem nao explode", tem is None, str((tem, motivo)))
    fonte = open(_componentes.fonte("app/radai_tasks.py"), encoding="utf-8").read()
    checar("le a tag ContrastBolusAgent", "ContrastBolusAgent" in fonte)
    try:
        import pydicom
        from pydicom.dataset import Dataset, FileMetaDataset
        from pydicom.uid import ExplicitVRLittleEndian, generate_uid
    except ImportError:
        pydicom = None
    if pydicom is None:
        checar("e distingue 'nao sei' de 'nao teve' (pydicom ausente)", False)
        return

    def _fantoma(pasta, agente):
        os.makedirs(pasta, exist_ok=True)
        meta = FileMetaDataset()
        meta.MediaStorageSOPClassUID = "1.2.840.10008.5.1.4.1.1.2"
        meta.MediaStorageSOPInstanceUID = generate_uid()
        meta.TransferSyntaxUID = ExplicitVRLittleEndian
        ds = Dataset()
        ds.file_meta = meta
        ds.SOPClassUID = meta.MediaStorageSOPClassUID
        ds.SOPInstanceUID = meta.MediaStorageSOPInstanceUID
        ds.Modality = "CT"
        if agente:
            ds.ContrastBolusAgent = agente
        caminho = os.path.join(pasta, "fantoma.dcm")
        try:
            ds.save_as(caminho, enforce_file_format=True)
        except TypeError:
            ds.is_little_endian, ds.is_implicit_VR = True, False
            ds.save_as(caminho, write_like_original=False)
        return pasta

    sem = T.detectar_contraste(_fantoma(os.path.join(vazio, "sem"), ""))
    com = T.detectar_contraste(_fantoma(os.path.join(vazio, "com"), "IODO"))
    checar("e distingue 'nao sei' (None) de 'nao teve' (False) e de 'teve'",
           sem[0] is False and com[0] is True,
           "%r %r" % (sem, com))


def teste_so_biblioteca_padrao():
    secao("catalogo: so stdlib")
    import ast
    fonte = open(_componentes.fonte("app/radai_tasks.py"), encoding="utf-8").read()
    arvore = ast.parse(fonte)
    proibidos = {"numpy", "SimpleITK", "pydicom", "fastapi", "torch",
                 "totalsegmentator", "rt_utils", "uvicorn"}
    topo = []
    for no in arvore.body:
        if isinstance(no, ast.Import):
            topo += [a.name.split(".")[0] for a in no.names]
        elif isinstance(no, ast.ImportFrom) and no.module:
            topo.append(no.module.split(".")[0])
    checar("nenhum import pesado no topo do modulo",
           not (set(topo) & proibidos), str(sorted(set(topo) & proibidos)))
    checar("o import do TotalSegmentator e preguicoso",
           "from totalsegmentator.libs import" in fonte
           and "    from totalsegmentator" in fonte)


def teste_contra_a_biblioteca():
    secao("catalogo x biblioteca instalada")
    ok, msgs = T.conferir_contra_biblioteca()
    checar("catalogo coerente com o TotalSegmentator", ok, " | ".join(msgs))
    print("       %s" % msgs[0])
    comparou = msgs[0] != "biblioteca ausente: nada a comparar"
    print("       (comparou de verdade: %s)" % ("sim" if comparou else
                                                "NAO -- ver a checagem abaixo"))


def teste_a_conferencia_contra_a_biblioteca_sabe_reprovar():
    secao("a conferencia contra a biblioteca sabe reprovar")
    import types

    def com_biblioteca_dublada(class_map):
        pai = types.ModuleType("totalsegmentator")
        filho = types.ModuleType("totalsegmentator.map_to_binary")
        filho.class_map = class_map
        pai.map_to_binary = filho
        antes = {k: sys.modules.get(k) for k in
                 ("totalsegmentator", "totalsegmentator.map_to_binary")}
        sys.modules["totalsegmentator"] = pai
        sys.modules["totalsegmentator.map_to_binary"] = filho
        try:
            return T.conferir_contra_biblioteca()
        finally:
            for k, v in antes.items():
                if v is None:
                    sys.modules.pop(k, None)
                else:
                    sys.modules[k] = v

    fiel = {T.nome_na_biblioteca(d["task"]):
            {i + 1: "r%d" % i for i in range(d["classes"])}
            for d in T.CATALOGO}

    ok, msgs = com_biblioteca_dublada(fiel)
    checar(u"com a biblioteca dublada ela COMPARA (nao diz 'ausente')",
           msgs and msgs[0] != "biblioteca ausente: nada a comparar",
           str(msgs[:1]))
    checar(u"catalogo identico a biblioteca: aprova", ok, " | ".join(msgs))

    alvo = T.CATALOGO[0]["task"]
    torto = dict(fiel)
    torto[alvo] = {i + 1: "r%d" % i for i in range(len(fiel[alvo]) + 1)}
    ok_t, msgs_t = com_biblioteca_dublada(torto)
    checar(u"isca: contagem de classes trocada REPROVA", not ok_t,
           u"a guarda passou com `%s` declarando %d e a biblioteca %d"
           % (alvo, len(fiel[alvo]), len(torto[alvo])))
    checar(u"  e a mensagem nomeia a task", any(alvo in m for m in msgs_t),
           " | ".join(msgs_t))

    sem = {k: v for k, v in fiel.items() if k != alvo}
    ok_s, msgs_s = com_biblioteca_dublada(sem)
    checar(u"isca: task que a biblioteca nao tem mais REPROVA", not ok_s,
           u"a guarda passou com `%s` ausente da biblioteca" % alvo)
    checar(u"  e a mensagem diz que a biblioteca nao a tem",
           any("nao tem mais" in m for m in msgs_s), " | ".join(msgs_s))

    a_mais = dict(fiel)
    a_mais["tissue_types"] = {1: "r0"}
    a_mais["liver_vessels"] = {1: "r0", 2: "r1"}
    ok_m, msgs_m = com_biblioteca_dublada(a_mais)
    checar(u"biblioteca com tasks que o catalogo nao oferece: APROVA", ok_m,
           " | ".join(msgs_m[:3]))
    checar(u"  e mesmo assim relata as que ficaram de fora",
           sum(1 for m in msgs_m if "nao oferece" in m) == 2,
           " | ".join(msgs_m))
    checar(u"  e o resumo diz quantas sao", "2 tasks" in msgs_m[0],
           msgs_m[0])

    checar(u"a dublagem foi desmontada no fim",
           "totalsegmentator.map_to_binary" not in sys.modules
           or getattr(sys.modules["totalsegmentator.map_to_binary"],
                      "__file__", None) is not None)


def teste_permitida_nao_quer_dizer_que_existe():
    secao(u"permitida nao quer dizer que existe neste pacote")
    import engine as MT

    if MT.tasks_do_motor() is None:
        checar(u"sem o pacote instalado, ela nao acusa ninguem",
               MT.conferir_tasks_existem(["qualquer_coisa"]) is None)

    import types
    falso = types.ModuleType("totalsegmentator.map_to_binary")
    falso.class_map = {"total": {}, "lung_vessels": {},
                       "head_glands_cavities": {}, "headneck_muscles": {}}
    pai = types.ModuleType("totalsegmentator")
    velho_pai = sys.modules.get("totalsegmentator")
    velho_map = sys.modules.get("totalsegmentator.map_to_binary")
    sys.modules["totalsegmentator"] = pai
    sys.modules["totalsegmentator.map_to_binary"] = falso
    try:
        checar(u"o catalogo e lido do pacote instalado",
               MT.tasks_do_motor() == set(falso.class_map))
        MT.conferir_tasks_existem(["total", "lung_vessels"])
        checar(u"as quatro do pacote passam", True)
        try:
            MT.conferir_tasks_existem(["total", "trunk_cavities"])
            checar(u"`trunk_cavities` e recusada", False, u"passou")
        except ValueError as e:
            checar(u"`trunk_cavities` e recusada", True)
            txt = str(e)
            checar(u"  e a mensagem fala de VERSAO, e nao de permissao",
                   "versao" in txt.lower() and "permitida" not in txt.lower(),
                   txt[:90])
            checar(u"  e avisa que derruba a fila",
                   "fila" in txt.lower() or "serie" in txt.lower(), txt[:90])
        falso.class_map["face"] = {}
        try:
            MT.conferir_tasks_existem(["face"])
            checar(u"existir nao libera: `face` passa por ESTA e "
                   u"cai na nossa regra", True)
        except ValueError:
            checar(u"existir nao libera (esta checagem e so de ambiente)",
                   False, u"a de ambiente recusou uma task que existe")
        try:
            MT.conferir_tasks(["face"])
            checar(u"  e a nossa regra recusa `face`", False, u"passou")
        except ValueError as e:
            checar(u"  e a nossa regra recusa `face`", True)
            checar(u"    dizendo que e de ESCOPO, e nao «nao esta na lista»",
                   "escopo" in str(e).lower(), str(e)[:90])

        checar(u"o pacote injetado nao conhece `lung_nodules` (como o 2.4.0)",
               "lung_nodules" not in falso.class_map)
        try:
            MT.conferir_tasks(["lung_nodules"])
            checar(u"a nossa regra PERMITE `lung_nodules` (regra B)", True)
        except ValueError as e:
            checar(u"a nossa regra PERMITE `lung_nodules` (regra B)", False,
                   str(e)[:90])
        try:
            MT.conferir_tasks_existem(["lung_nodules"])
            checar(u"  e mesmo assim ela NAO existe neste pacote", False,
                   u"passou")
        except ValueError as e:
            checar(u"  e mesmo assim ela NAO existe neste pacote", True)
            checar(u"    e a mensagem fala de VERSAO, e nao de permissao",
                   "versao" in str(e).lower()
                   and "permitida" not in str(e).lower(), str(e)[:90])

        _antes_ts = dict(T.EXIGEM_TS)
        try:
            T.EXIGEM_TS["lung_nodules"] = "99.0.0"
            e_nod = {d["task"]: d for d in T.estado(tempfile.mkdtemp(
                prefix="radai_pesos_"))}
            for nome in ("lung_nodules",):
                d = e_nod.get(nome)
                checar(u"%s esta no catalogo" % nome, d is not None)
                if d is None:
                    continue
                checar(u"  (fantoma) sai `disponivel=False`",
                       d["disponivel"] is False, str(d.get("disponivel")))
                checar(u"  com `exige_ts` declarado",
                       d["exige_ts"] == "99.0.0", str(d.get("exige_ts")))
                checar(u"  e o motivo cita a versao que falta",
                       "99.0.0" in d["porque_indisponivel"],
                       d["porque_indisponivel"][:90])
        finally:
            T.EXIGEM_TS.clear()
            T.EXIGEM_TS.update(_antes_ts)
        checar(u"  e a tabela voltou ao estado de origem",
               dict(T.EXIGEM_TS) == _antes_ts)
        _real = {d["task"]: d for d in T.estado(tempfile.mkdtemp(
            prefix="radai_pesos_"))}
        checar(u"  e com a tabela REAL ela esta disponivel (pino %s)"
               % _pino_do_totalsegmentator(),
               _real["lung_nodules"]["disponivel"] is True)
    finally:
        for k, v in (("totalsegmentator", velho_pai),
                     ("totalsegmentator.map_to_binary", velho_map)):
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v

    import io as _io
    fonte = _io.open(_componentes.fonte("app/radai_watcher.py"),
                     encoding="utf-8").read()
    corpo = fonte[fonte.index("def conferir_ambiente("):]
    corpo = corpo[:corpo.index("\ndef ", 10)]
    checar(u"`conferir_ambiente` chama `conferir_tasks_existem`",
           "conferir_tasks_existem(" in corpo)
    checar(u"  e continua chamando a guarda clinica antes",
           corpo.index("conferir_tasks(") < corpo.index("conferir_tasks_existem("))


def _com_o_peso_do_body(base, checkpoint=True):
    d = os.path.join(base, T.DATASET_DO_BODY_PASTA)
    if checkpoint:
        cam = os.path.join(d, T.PESO_DO_BODY)
        os.makedirs(os.path.dirname(cam), exist_ok=True)
        open(cam, "wb").close()
    else:
        os.makedirs(d, exist_ok=True)
    return d


def teste_recorte_no_corpo():
    secao("recorte no corpo (--body_seg): quem recorta, e o 300 na conta")
    PREF, RES, MR = T.BASES_CT[0], T.BASES_CT[-1], T.BASES_MR[0]
    for t in sorted(T.POR_NOME):
        d = T.POR_NOME[t]
        aplica, porque = T.recorte_no_corpo_se_aplica(t)
        if d["modalidade"] == "MR":
            checar(u"`%s` (RM): a biblioteca ignora -- nao se aplica" % t,
                   not aplica and u"RM" in porque, porque)
            checar(u"  e o 300 NAO entra na conta dela", T.DATASET_BODY
                   not in T.datasets_necessarios(t),
                   str(T.datasets_necessarios(t)))
        elif t in T.RECORTAM:
            checar(u"`%s` recorta no proprio localizador -- nao se aplica" % t,
                   not aplica and u"localizador" in porque, porque)
            checar(u"  e o 300 so entra se ELE for o localizador dela",
                   (T.DATASET_BODY in T.datasets_necessarios(t))
                   == (T.DATASET_BODY in T.RECORTAM[t]),
                   str(T.datasets_necessarios(t)))
        else:
            checar(u"`%s` (TC, sem localizador): recorta no corpo" % t,
                   aplica, porque)
            checar(u"  e passa a exigir o Dataset300",
                   T.DATASET_BODY in T.datasets_necessarios(t),
                   str(T.datasets_necessarios(t)))
    checar(u"a base de TC esta entre as que recortam",
           T.recorte_no_corpo_se_aplica(PREF)[0]
           and T.recorte_no_corpo_se_aplica(RES)[0])
    checar(u"o apelido `total` e de TC, e recorta",
           T.recorte_no_corpo_se_aplica("total")[0])
    _nao, _pq = T.recorte_no_corpo_se_aplica("task_que_nao_existe")
    checar(u"task fora do catalogo: NAO, com «nao sei» (e nao «sim»)",
           not _nao and u"nao sei" in _pq, _pq)
    checar(u"sem o recorte na conta, a base volta aos pesos dela",
           T.DATASET_BODY not in T.datasets_necessarios(
               PREF, recorte_no_corpo=False))
    checar(u"o pacote de fabrica (so o PADRAO) leva o 300",
           T.DATASET_BODY in T.datasets_do_pacote(T.PADRAO),
           str(T.datasets_do_pacote(T.PADRAO)))

    _velho = T.recorte_no_corpo_se_aplica
    try:
        T.recorte_no_corpo_se_aplica = lambda t: (
            T.POR_NOME.get(t, {}).get("modalidade") == "CT", u"isca")
        base = tempfile.mkdtemp(prefix="radai_pesos_")
        for n in (775, T.DATASET_RECORTE):
            os.makedirs(os.path.join(base, "Dataset%d_x" % n))
        e = {d["task"]: d for d in T.estado(base)}
        checar(u"  (isca) com o 300 para toda TC, uma task que recorta no "
               u"proprio localizador aparece NAO BAIXADA",
               not e["head_glands_cavities"]["baixado"],
               str(e["head_glands_cavities"]["faltando"]))
    finally:
        T.recorte_no_corpo_se_aplica = _velho
    e = {d["task"]: d for d in T.estado(base)}
    checar(u"  e com a regra da biblioteca ela e BAIXADA sem o 300",
           e["head_glands_cavities"]["baixado"],
           str(e["head_glands_cavities"]["faltando"]))

    base = tempfile.mkdtemp(prefix="radai_pesos_")
    for n in T.POR_NOME[PREF]["datasets"]:
        os.makedirs(os.path.join(base, "Dataset%d_x" % n))
    e = {d["task"]: d for d in T.estado(base)}
    checar(u"a base sem o Dataset300: NAO baixada, e o que falta e o 300",
           not e[PREF]["baixado"] and e[PREF]["faltando"] == [T.DATASET_BODY],
           str(e[PREF]["faltando"]))
    checar(u"  e o custo dela conta os 124 MB do 300",
           T.custo_mb([PREF], base) == T.CUSTO_DO_RECORTE[T.DATASET_BODY],
           str(T.custo_mb([PREF], base)))
    _velho = T.recorte_no_corpo_se_aplica
    try:
        T.recorte_no_corpo_se_aplica = lambda t: (False, u"isca")
        checar(u"  (isca) sem o recorte na conta, o custo esconde o 300",
               T.custo_mb([PREF], base) == 0, str(T.custo_mb([PREF], base)))
    finally:
        T.recorte_no_corpo_se_aplica = _velho
    _com_o_peso_do_body(base)
    e = {d["task"]: d for d in T.estado(base)}
    checar(u"com o Dataset300 no disco, a base e BAIXADA", e[PREF]["baixado"],
           str(e[PREF]["faltando"]))
    checar(u"  e o resumo diz que o recorte no corpo esta pronto",
           T.resumo(base)["recorte_no_corpo_ok"] is True)

    base = tempfile.mkdtemp(prefix="radai_pesos_")
    ok, fr = T.pesos_do_recorte_no_corpo(base)
    checar(u"sem a pasta: ausente, e a frase diz qual pasta",
           not ok and T.DATASET_DO_BODY_PASTA in fr, fr)
    _com_o_peso_do_body(base, checkpoint=False)
    ok, fr = T.pesos_do_recorte_no_corpo(base)
    checar(u"pasta sem o checkpoint (download interrompido): ausente",
           not ok and u"interrompido" in fr, fr)
    _com_o_peso_do_body(base)
    ok, fr = T.pesos_do_recorte_no_corpo(base)
    checar(u"com o checkpoint: presente", ok, fr)
    checar(u"pasta que nao existe nao explode",
           T.pesos_do_recorte_no_corpo(base + "_nao_existe")[0] is False)

    velho = T.baixados
    try:
        SO_V2 = set(T.POR_NOME[RES]["datasets"])
        T.baixados = lambda base=None: set(SO_V2)
        checar(u"a reserva completa SEM o 300 ainda e eleita (o 300 e so "
               u"otimizacao: sem ele a base roda sem o recorte)",
               T.base_no_disco("CT") == RES, T.base_no_disco("CT"))
        _dn = T.datasets_necessarios
        T.datasets_necessarios = lambda t, recorte_no_corpo=True: \
            _dn(t, recorte_no_corpo=True)
        try:
            checar(u"  (isca) contando o 300 na eleicao, a estacao desiste da "
                   u"reserva completa", T.base_no_disco("CT") == PREF,
                   T.base_no_disco("CT"))
        finally:
            T.datasets_necessarios = _dn
    finally:
        T.baixados = velho

    checar(u"TOTALSEG_WEIGHTS_PATH manda",
           T.pasta_pesos({"TOTALSEG_WEIGHTS_PATH": "P", "TOTALSEG_HOME_DIR": "H"})
           == "P")
    checar(u"  sem ela, a casa do TotalSegmentator (TOTALSEG_HOME_DIR)",
           T.pasta_pesos({"TOTALSEG_HOME_DIR": "H"})
           == os.path.join("H", "nnunet", "results"))
    checar(u"  sem as duas, a pasta do usuario",
           T.pasta_pesos({}).endswith(os.path.join(".totalsegmentator",
                                                   "nnunet", "results")))

    SO_CORPO = u"só o corpo, sem o ar em volta"
    CONDICIONAL = u"só o corpo, quando o recorte no corpo está ligado"
    INTEIRA = u"a série inteira"

    def campo(t, **k):
        return [x["val"] for x in T.ficha(t, **k)
                if x["rot"] == u"campo de trabalho"]
    velho_amb = os.environ.get("TOTALSEG_WEIGHTS_PATH")
    com_300 = tempfile.mkdtemp(prefix="radai_pesos_")
    _com_o_peso_do_body(com_300)
    sem_300 = tempfile.mkdtemp(prefix="radai_pesos_")
    try:
        os.environ["TOTALSEG_WEIGHTS_PATH"] = com_300
        checar(u"ficha da base de TC, chave ligada e o 300 no disco: so o "
               u"corpo", campo(PREF, recorte_no_corpo=True) == [SO_CORPO],
               str(campo(PREF, recorte_no_corpo=True)))
        checar(u"  chave DESLIGADA: a serie inteira",
               campo(PREF, recorte_no_corpo=False) == [INTEIRA],
               str(campo(PREF, recorte_no_corpo=False)))
        checar(u"  chave nao informada (quem chama esqueceu): condicional, e "
               u"nao afirma", campo(PREF) == [CONDICIONAL], str(campo(PREF)))
        os.environ["TOTALSEG_WEIGHTS_PATH"] = sem_300
        checar(u"  SEM o 300, com a chave ligada: a serie inteira",
               campo(PREF, recorte_no_corpo=True) == [INTEIRA],
               str(campo(PREF, recorte_no_corpo=True)))
        checar(u"  sem o 300 e sem a chave: a serie inteira tambem",
               campo(PREF) == [INTEIRA], str(campo(PREF)))
        checar(u"ficha da base de RM: a serie inteira, com qualquer chave",
               campo(MR) == [INTEIRA]
               and campo(MR, recorte_no_corpo=True) == [INTEIRA],
               str(campo(MR)))
        checar(u"ficha de quem recorta no localizador: recorta antes",
               campo("head_glands_cavities", recorte_no_corpo=False)
               == [u"recorta antes de rodar"])
        _velho = T.pesos_do_recorte_no_corpo
        try:
            T.pesos_do_recorte_no_corpo = lambda pasta=None: (True, u"isca")
            checar(u"  (isca) sem olhar o peso, a estacao sem o 300 le «so o "
                   u"corpo»", campo(PREF, recorte_no_corpo=True) == [SO_CORPO],
                   str(campo(PREF, recorte_no_corpo=True)))
        finally:
            T.pesos_do_recorte_no_corpo = _velho
    finally:
        if velho_amb is None:
            os.environ.pop("TOTALSEG_WEIGHTS_PATH", None)
        else:
            os.environ["TOTALSEG_WEIGHTS_PATH"] = velho_amb
    _por = [x["val"] for x in T.ficha(PREF) if x["rot"] == u"por quê"]
    checar(u"o «por que» da base pesada diz as duas pontas (corpo OU serie)",
           _por and u"corpo inteiro" in _por[0] and u"série inteira" in _por[0],
           str(_por))


def teste_o_arranque_diz_o_recorte():
    secao("o arranque diz o recorte no corpo")
    import radai_arranque as RA
    base = tempfile.mkdtemp(prefix="radai_pesos_")
    for n in T.POR_NOME[T.BASES_CT[0]]["datasets"]:
        os.makedirs(os.path.join(base, "Dataset%d_x" % n))
    velho = os.environ.get("TOTALSEG_WEIGHTS_PATH")
    os.environ["TOTALSEG_WEIGHTS_PATH"] = base

    def passo(**ctx):
        rel = {"dados": {}, "avisos": [], "pendencias": []}
        ctx.setdefault("tasks", [T.BASES_CT[0]])
        return RA._p_pesos(ctx, rel), rel

    def alcance_certo(texto):
        return (u"sem localizador proprio" in texto
                and u"recortam no proprio localizador nao mudam" in texto
                and u"toda task de TC" not in texto
                and u"do mesmo jeito" not in texto)
    try:
        L, rel = passo(recorte_no_corpo=True)
        linha = [l for l in L if l.startswith(u"recorte no corpo (--body_seg)")]
        checar(u"a linha existe, e diz ligado e AUSENTE",
               linha and u": ligado" in linha[0] and u"AUSENTE" in linha[0],
               str(linha))
        al = [a for a in rel["avisos"] if a.startswith(u"ALERTA")
              and u"Dataset300" in a and u"TC INTEIRA" in a]
        checar(u"  e o ALERTA vai para os avisos do bloco", al,
               str(rel["avisos"]))
        checar(u"  e o ALERTA diz o ALCANCE certo: a base e as sem "
               u"localizador; as que recortam no localizador nao mudam",
               al and alcance_certo(al[0]), al[0] if al else u"")
        checar(u"  e diz que o contorno e o da TC inteira, com a diferenca "
               u"na borda", al and u"contorno da TC inteira" in al[0]
               and u"borda" in al[0], al[0] if al else u"")
        checar(u"  e NAO vira pendencia de falha (a serie roda sem o recorte)",
               not rel["pendencias"], str(rel["pendencias"]))
        bl = u"\n".join(RA.bloco(rel))
        checar(u"  e o BLOCO (o que se cola num chat) tem a linha da decisao "
               u"e o alerta", u"Recorte no corpo (--body_seg): ligado" in bl
               and u"Dataset300 AUSENTE" in bl and u"ALERTA" in bl, bl[-400:])
        _lb = [l for l in bl.splitlines()
               if l.startswith(u"Recorte no corpo (--body_seg)")]
        checar(u"  e a linha do bloco diz o MESMO alcance do alerta",
               _lb and alcance_certo(_lb[0]), str(_lb))
        checar(u"  (isca) o alerta de antes («toda task de TC ... do mesmo "
               u"jeito») reprova", not alcance_certo(
                   u"ALERTA: ... - toda task de TC vai rodar a TC INTEIRA, sem "
                   u"o recorte: mais lenta (...); o contorno sai do mesmo "
                   u"jeito."))
        checar(u"  (isca) a linha do bloco de antes reprova", not alcance_certo(
            u"Recorte no corpo (--body_seg): ligado (x); Dataset300 AUSENTE - "
            u"as series de TC rodam a TC inteira"))
        L, rel = passo(recorte_no_corpo=False)
        linha = [l for l in L if l.startswith(u"recorte no corpo (--body_seg)")]
        checar(u"desligado no config: a linha diz desligado, sem alerta",
               linha and u": desligado" in linha[0] and not rel["avisos"],
               str(linha) + str(rel["avisos"]))
        _lb = [l for l in RA.bloco(rel)
               if l.startswith(u"Recorte no corpo (--body_seg)")]
        checar(u"  e o bloco nao culpa a falta do 300 (a TC ja roda inteira "
               u"pela chave)", _lb and u"desligado" in _lb[0]
               and u"TC INTEIRA" not in _lb[0], str(_lb))
        _com_o_peso_do_body(base)
        L, rel = passo(recorte_no_corpo=True)
        linha = [l for l in L if l.startswith(u"recorte no corpo (--body_seg)")]
        checar(u"com o 300: ligado e presente, sem alerta",
               linha and u"Dataset300 presente" in linha[0]
               and not rel["avisos"], str(linha))
        L, rel = passo(carregar_engine=lambda: type(
            "E", (), {"RECORTE_NO_CORPO_PADRAO": True}))
        linha = [l for l in L if l.startswith(u"recorte no corpo (--body_seg)")]
        checar(u"sem a chave do vigia: o padrao do motor, e a linha diz",
               linha and u": ligado (padrao do motor" in linha[0], str(linha))
        shutil.rmtree(os.path.join(base, T.DATASET_DO_BODY_PASTA))
        _dn = T.datasets_necessarios
        T.datasets_necessarios = lambda t, recorte_no_corpo=True: \
            _dn(t, recorte_no_corpo=True)
        try:
            L, rel = passo(recorte_no_corpo=True)
            checar(u"  (isca) o 300 na conta da task cria a pendencia falsa",
                   [p for p in rel["pendencias"] if u"300" in p],
                   str(rel["pendencias"]))
        finally:
            T.datasets_necessarios = _dn
    finally:
        if velho is None:
            os.environ.pop("TOTALSEG_WEIGHTS_PATH", None)
        else:
            os.environ["TOTALSEG_WEIGHTS_PATH"] = velho


def teste_a_velocidade_sai_da_medida():
    secao("a velocidade: fast / regular / slow / ultra-slow")
    checar("as quatro etiquetas, na ordem",
           tuple(T.VELOCIDADES) == ("fast", "regular", "slow", "ultra-slow"),
           str(T.VELOCIDADES))
    bordas = ((0.0, "fast"), (0.249, "fast"), (0.25, "regular"),
              (0.749, "regular"), (0.75, "slow"), (1.0, "slow"),
              (1.999, "slow"), (2.0, "ultra-slow"), (9.0, "ultra-slow"))
    for r, tag in bordas:
        checar("  razao %.3f -> %s" % (r, tag),
               T.velocidade_da_razao(r) == tag, str(T.velocidade_da_razao(r)))
    checar("  razao ilegivel -> None (nao «fast»)",
           T.velocidade_da_razao("x") is None)

    vb = T.velocidade(T.REFERENCIA_DE_VELOCIDADE)
    checar("a base e a regua: medida, razao 1,0, `slow`",
           vb and vb["medida"] and vb["razao"] == 1.0 and vb["tag"] == "slow",
           str(vb))
    for t, tag in (("trunk_cavities", "regular"), ("breasts", "regular"),
                   ("abdominal_muscles", "ultra-slow")):
        v = T.velocidade(t)
        checar("`%s` e %s, MEDIDA" % (t, tag),
               v and v["medida"] and v["tag"] == tag, str(v))
    _va = T.velocidade("abdominal_muscles")
    checar("  e a da `abdominal_muscles` e DIRETA: 2,62 bases na P20, sem ponte",
           _va.get("ponte") is False and _va.get("cota") is False
           and _va.get("razao") == round(3464.6 / 1324.2, 2) == 2.62,
           str(_va))
    checar("    e a fonte diz de onde veio (a serie, os dois tempos) e guarda "
           "a ponte como registro",
           u"3.464,6 s" in _va.get("fonte", "")
           and u"1.324,2 s" in _va.get("fonte", "")
           and u"P20" in _va.get("fonte", "")
           and u"ponte" in _va.get("fonte", ""), _va.get("fonte", "")[:160])
    for t, m in T.TEMPO_MEDIDO.items():
        checar("  a medida de `%s` e de uma task do catalogo, com fonte" % t,
               t in T.POR_NOME and bool(m.get("fonte")), str(m)[:80])
    sem = [d["task"] for d in T.CATALOGO if not T.velocidade(d["task"])]
    checar("toda task do catalogo tem etiqueta", not sem, str(sem))
    est_ultra = [d["task"] for d in T.CATALOGO
                 if (T.velocidade(d["task"]) or {}).get("medida") is False
                 and T.velocidade(d["task"])["tag"] == "ultra-slow"]
    checar("  e nenhuma ESTIMADA e ultra-slow", not est_ultra, str(est_ultra))
    checar("  e o selo da estimada leva `~`, o da medida nao",
           T.rotulo_de_velocidade(T.velocidade("teeth")).startswith("~")
           and not T.rotulo_de_velocidade(T.velocidade("breasts"))
           .startswith("~"),
           "%s / %s" % (T.rotulo_de_velocidade(T.velocidade("teeth")),
                        T.rotulo_de_velocidade(T.velocidade("breasts"))))
    checar("  task fora do catalogo nao tem etiqueta (nao sei != fast)",
           T.velocidade("xpto") is None)

    def _linhas(task):
        return dict((r["rot"], r["val"]) for r in T.ficha(task))
    fm, fe = _linhas("breasts"), _linhas("teeth")
    checar("a ficha da medida diz a razao e que ela foi medida",
           fm.get("velocidade") == "regular"
           and fm.get("tempo contra a base", "").endswith(u"×")
           and u"medida contra a base" in fm.get("de onde vem a velocidade",
                                                 ""), str(fm)[:200])
    checar("  e a da estimada diz que nao foi medida",
           fe.get("velocidade", "").startswith("~")
           and u"não medida" in fe.get("de onde vem a velocidade", ""),
           str(fe)[:200])
    checar("  e a da `abdominal_muscles` diz que foi medida contra a base",
           u"medida contra a base" in _linhas("abdominal_muscles").get(
               "de onde vem a velocidade", ""),
           str(_linhas("abdominal_muscles"))[:200])
    T.TEMPO_MEDIDO["_ponte_forjada"] = {"razao": 0.5, "cota": False,
                                        "ponte": True, "fonte": u"forjada"}
    _pn = dict(T.POR_NOME)
    try:
        T.POR_NOME["_ponte_forjada"] = dict(T.POR_NOME["breasts"],
                                            task="_ponte_forjada")
        _vf = T.velocidade("_ponte_forjada")
        checar("  e uma medida POR PONTE (forjada) se declara ponte na ficha",
               _vf and _vf.get("ponte") is True
               and u"por ponte" in _linhas("_ponte_forjada").get(
                   "de onde vem a velocidade", ""), str(_vf))
    finally:
        T.TEMPO_MEDIDO.pop("_ponte_forjada", None)
        T.POR_NOME.clear()
        T.POR_NOME.update(_pn)

    guardado = T.TEMPO_MEDIDO.pop("abdominal_muscles")
    try:
        v = T.velocidade("abdominal_muscles")
        checar("(isca) sem a medida, a abdominal_muscles seria ~fast -- a "
               "forma nao sabe o tamanho da saida",
               v and v["medida"] is False and v["tag"] == "fast", str(v))
    finally:
        T.TEMPO_MEDIDO["abdominal_muscles"] = guardado


def teste_os_segmentos_hepaticos_da_rm_entram_medidos():
    secao("a liver_segments_mr, medida")
    d = T.POR_NOME.get("liver_segments_mr")
    checar("esta no catalogo", bool(d))
    if not d:
        return
    checar("  de RM, com oito classes e o Dataset576",
           d["modalidade"] == "MR" and d["classes"] == 8
           and d["datasets"] == [576], str(d))
    checar("  e o peso MEDIDO (229.689.699 bytes -> 230 MB, a conta das "
           "outras linhas)", d["mb"] == int(round(229689699 / 1e6)),
           str(d["mb"]))
    checar("  recorta no localizador de RM de 3 mm (852)",
           T.RECORTAM.get("liver_segments_mr") == (T.DATASET_RECORTE_MR,),
           str(T.RECORTAM.get("liver_segments_mr")))
    checar("  e declara o contraste (RM: o iodado nao entra)",
           T.CONTRASTE_TASK.get("liver_segments_mr") == "nao")
    checar("  e o espacamento do modelo (3,0 mm: nao pede corte fino)",
           T.Z_DO_MODELO.get("liver_segments_mr") == 3.0
           and T.pede_corte_fino("liver_segments_mr") is None)
    checar("  e nao exige chave", not d["comercial"])


def teste_o_peso_em_bases_e_a_estimativa_da_noite():
    print(u"%s-- o peso em bases e a estimativa da noite --" % chr(10))
    import inspect
    import textwrap
    esperado = (("head_glands_cavities", 0.25),
                ("craniofacial_structures", 0.75),
                ("total_mr", 2.0),
                ("total_v3", 1.0),
                ("task_que_nao_existe", 1.0))

    def _erradas(fn):
        return [(t, fn(t)) for t, v in esperado if abs(fn(t) - v) > 1e-9]
    for t, v in esperado:
        checar(u"%s pesa %.2f base(s)" % (t, v),
               abs(T.peso_em_bases(t) - v) < 1e-9, T.peso_em_bases(t))
    checar(u"a medida vale a razao medida (abdominal_muscles > 2 bases)",
           T.peso_em_bases("abdominal_muscles") > 2.0,
           T.peso_em_bases("abdominal_muscles"))
    src = textwrap.dedent(inspect.getsource(T.peso_em_bases))
    alvo = u"            return float(teto)"
    ns = dict(vars(T))
    exec(compile(src.replace(alvo, u"            return 1.0"), "<isca-peso>",
                 "exec"), ns)
    checar(u"ISCA: com a estimada valendo 1,0, a checagem acusa as tres "
           u"estimadas", alvo in src and len(_erradas(ns["peso_em_bases"]))
           == 3, str(_erradas(ns["peso_em_bases"])))

    import radai_review as RV
    if RV.MIN_POR_MVOXEL_CPU is None:
        checar(u"(a regua de CPU nao carregou: a estimativa nao se mede aqui)",
               True)
        return
    frac = RV.estimativa(1, 6.6, "cpu")[0]
    inteiro = RV.estimativa(1, 6, "cpu")[0]
    checar(u"a estimativa com 6,6 bases e maior que com 6 (nao trunca)",
           frac > inteiro, u"%s contra %s" % (frac, inteiro))
    src = textwrap.dedent(inspect.getsource(RV.estimativa))
    alvo = u"n_tasks = max(1.0, float(n_tasks))"
    ns = dict(vars(RV))
    exec(compile(src.replace(alvo, u"n_tasks = max(1, int(float(n_tasks)))"),
                 "<isca-trunca>", "exec"), ns)
    checar(u"ISCA: com o `n_tasks` truncado, 6,6 e 6 dao o mesmo numero (a "
           u"checagem acima sabe reprovar)", alvo in src
           and ns["estimativa"](1, 6.6, "cpu")[0]
           == ns["estimativa"](1, 6, "cpu")[0])


def _achados_do_motor():
    try:
        import engine as _E
        return set(_E.TASKS_DE_ACHADO), True
    except Exception:
        return set(["lung_nodules",
                    "liver_lesions", "liver_lesions_mr"]), False


def teste_os_modos_e_os_protocolos_da_v83():
    secao("os modos e os protocolos da v8.3 (spec 1.1 a 1.3)")
    import radai_modes as M
    achados, do_motor = _achados_do_motor()
    checar("os achados vieram do motor (`engine.TASKS_DE_ACHADO`)", do_motor,
           "sem o motor, a lista fixa de hoje")
    M.conferir_protocolos(T.CATALOGO, achados)
    checar("os protocolos conferem contra o catalogo", True)
    esperado = {
        "cranio": ("CT", ("head_glands_cavities", "craniofacial_structures"),
                   ("cranio_ct",)),
        "cabeca_pescoco": ("CT", ("head_glands_cavities", "headneck_muscles",
                                  "headneck_bones_vessels", "head_muscles",
                                  "craniofacial_structures"),
                           ("hnlnl", "cranio_ct")),
        "torax_mama": ("CT", ("trunk_cavities", "breasts",
                              "pleural_pericard_effusion"), ()),
        "sbrt": ("CT", ("trunk_cavities", "breasts", "liver_segments",
                        "pleural_pericard_effusion"), ()),
        "abdome": ("CT", ("trunk_cavities", "liver_segments",
                          "abdominal_muscles"), ()),
        "pelve": ("CT", ("trunk_cavities",), ()),
        "coluna": ("CT", ("vertebrae_body",), ()),
        "coluna_rm": ("MR", ("vertebrae_mr",), ()),
        "abdome_rm": ("MR", ("liver_segments_mr",), ()),
    }
    reais = dict((p["cod"], (p["modalidade"], tuple(p["tasks"]),
                             tuple(p.get("motores") or ())))
                 for p in M.PROTOCOLOS)
    checar("os protocolos sao os da tabela 1.2, com as tasks e os motores",
           reais == esperado, str(sorted(set(reais) ^ set(esperado))))
    checar("  e nao ha protocolo de prostata (a total_mr ja a entrega)",
           not any("prost" in c for c in reais))
    checar("  orbita e dentes ficam fora do Cabeca e Pescoco avancado",
           not ({"oculomotor_muscles", "teeth"}
                & set(reais["cabeca_pescoco"][1])))
    checar("  o SBRT arrasta a glandula SEM os musculos (so a glandula)",
           "abdominal_muscles" not in reais["sbrt"][1])
    checar("  a abdominal_muscles so no Abdomen (e no estudo 3D toracico): "
           "fora do Torax/Mama",
           [c for c, v in sorted(reais.items())
            if "abdominal_muscles" in v[1]] == ["abdome"]
           and "abdominal_muscles" in M.PROT_3D_POR_COD[
               "anatomia_toracica"]["tasks"])
    checar("  nenhum texto de ajuda de protocolo fala da mama de restricao",
           not any(u"Breast_OAR" in (p.get("ajuda") or u"")
                   for p in M.PROTOCOLOS + M.PROTOCOLOS_3D))
    checar("protocolos_de: a RM so ve os dela",
           [p["cod"] for p in M.protocolos_de("MR")]
           == ["coluna_rm", "abdome_rm"])
    checar("motores_dos_protocolos: o C&P avancado liga os niveis cervicais "
           "e o encefalo em TC",
           M.motores_dos_protocolos(["cabeca_pescoco"], "CT")
           == ("hnlnl", "cranio_ct")
           and M.motores_dos_protocolos(["cabeca_pescoco"], "MR") == ())

    P = M.tasks_do_personalizado
    checar("PERSONALIZADO sem nada, na TC: a base e a cavidade do tronco "
           "(o pericardio do Heart_ai nasce ligado)",
           P([], {}, "CT", achados=achados) == ("total_v3", "trunk_cavities",
                                                 "pleural_pericard_effusion"),
           str(P([], {}, "CT", achados=achados)))
    checar("  e o payload sem a chave vale ligada (`None` e `{}` iguais)",
           P([], None, "CT", achados=achados) == P([], {}, "CT",
                                                   achados=achados))
    checar("  a chave em 0 e o ato que a tira (e so ele)",
           P([], {"trunk_cavities": 0}, "CT", achados=achados)
           == ("total_v3", "pleural_pericard_effusion")
           and "trunk_cavities" not in P(["torax_mama"], {"trunk_cavities": 0},
                                         "CT", achados=achados))
    checar("  na RM nada muda: so a total_mr (a cavidade e modelo de TC)",
           P([], {}, "MR", achados=achados) == ("total_mr",)
           and M.ligadas_de_fabrica("MR") == ()
           and M.ligadas_de_fabrica("CT") == ("trunk_cavities",
                                               "pleural_pericard_effusion"))
    checar("  o derrame nasce ligado e desliga com a chave em 0 (v8.4, Q2)",
           "pleural_pericard_effusion" not in P(
               [], {"pleural_pericard_effusion": 0}, "CT", achados=achados))
    checar("  `pericardio_desligado_a_mao`: so a chave em 0, e so na TC",
           M.pericardio_desligado_a_mao({"trunk_cavities": 0}, "CT") is True
           and M.pericardio_desligado_a_mao({}, "CT") is False
           and M.pericardio_desligado_a_mao(None, "CT") is False
           and M.pericardio_desligado_a_mao({"trunk_cavities": 1}, "CT")
           is False
           and M.pericardio_desligado_a_mao({"trunk_cavities": 0}, "MR")
           is False)
    _velha_fab = M.LIGADAS_DE_FABRICA_NO_PERSO
    try:
        M.LIGADAS_DE_FABRICA_NO_PERSO = {}
        _isca_fab = P([], {}, "CT", achados=achados)
    finally:
        M.LIGADAS_DE_FABRICA_NO_PERSO = _velha_fab
    checar("  (isca) sem a tabela de fabrica, o PERSONALIZADO voltava a rodar "
           "so a base -- a checagem discrimina", _isca_fab == ("total_v3",),
           str(_isca_fab))
    _velha_fab = M.LIGADAS_DE_FABRICA_NO_PERSO
    try:
        M.LIGADAS_DE_FABRICA_NO_PERSO = {"CT": ("trunk_cavities",
                                                "lung_nodules")}
        try:
            P([], {}, "CT", achados=achados)
            lev = False
        except M.AchadoSemPedido:
            lev = True
    finally:
        M.LIGADAS_DE_FABRICA_NO_PERSO = _velha_fab
    checar("ISCA: achado forjado na tabela de fabrica do PERSONALIZADO PARA a "
           "lista (REGRA A: ninguem ligou a chave)", lev)
    checar("  o protocolo arrasta as dele",
           P(["torax_mama"], {}, "CT", achados=achados)
           == ("total_v3", "trunk_cavities", "breasts",
               "pleural_pericard_effusion"))
    checar("  a chave da task VENCE o protocolo (mama em 0)",
           "breasts" not in P(["torax_mama"], {"breasts": 0}, "CT",
                              achados=achados))
    checar("  um protocolo nao desliga o que outro ligou",
           "liver_segments" in P(["torax_mama", "sbrt"], {}, "CT",
                                 achados=achados))
    checar("  a base nao desliga (chave travada em 1)",
           P([], {"total_v3": 0}, "CT", achados=achados)[0] == "total_v3")
    checar("  a `breasts` ligada A MAO nao arrasta mais os musculos",
           "abdominal_muscles" not in P([], {"breasts": 1}, "CT",
                                        achados=achados)
           and M.DEPENDENCIAS_AO_LIGAR == {} and M.ao_ligar("breasts") == ())
    _velha_dep = M.DEPENDENCIAS_AO_LIGAR
    try:
        M.DEPENDENCIAS_AO_LIGAR = {"breasts": ("abdominal_muscles",)}
        _isca_dep = P([], {"breasts": 1}, "CT", achados=achados)
    finally:
        M.DEPENDENCIAS_AO_LIGAR = _velha_dep
    checar("    ISCA: com a regra de antes, os musculos voltariam",
           "abdominal_muscles" in _isca_dep, str(_isca_dep))
    checar("  a chave de ACHADO em 1 roda (ato declarado, regra B)",
           "lung_nodules" in P([], {"lung_nodules": 1}, "CT",
                               achados=achados))
    checar("  protocolo de TC numa RM nao arrasta nada",
           P(["torax_mama"], {}, "MR", achados=achados) == ("total_mr",))

    F = M.tasks_do_fast
    checar("FAST no torax: a base e as tres do OAR_Fast, sem os musculos",
           F({"torax"}, 700.0, "CT", achados=achados)
           == ("total_v3", "trunk_cavities", "breasts",
               "pleural_pericard_effusion"))
    checar("AUTO no torax: sem a abdominal_muscles",
           M.tasks_da_topografia({"torax"}, "CT", achados=achados)
           == ("total_v3", "trunk_cavities", "breasts",
               "pleural_pericard_effusion"))
    checar("FAST sem torax, coracao de 150 cm3: a base e a trunk_cavities",
           F({"abdome"}, 150.0, "CT", achados=achados)
           == ("total_v3", "trunk_cavities"))
    checar("FAST sem torax e sem coracao (ou nao medido): so a base",
           F({"abdome"}, 20.0, "CT", achados=achados) == ("total_v3",)
           and F({"pelve"}, None, "CT", achados=achados) == ("total_v3",))
    checar("FAST no cranio: so a base",
           F({"cabeca_pescoco"}, None, "CT", achados=achados)
           == ("total_v3",))
    checar("FAST na RM: so a total_mr",
           F({"torax"}, 700.0, "MR", achados=achados) == ("total_mr",))
    checar("o FAST esta CONTIDO no AUTO do torax (nada que o AUTO nao "
           "rodaria)", set(M.TASKS_DO_FAST["torax"])
           <= set(M.TASKS_POR_TOPOGRAFIA["torax"]))

    checar("AUTO na pelve: a trunk_cavities (a Bag_Bowel na pelve pura)",
           M.tasks_da_topografia({"pelve"}, "CT", achados=achados)
           == ("total_v3", "trunk_cavities"))
    checar("  e a hip_implant continua fora (so quando pedida)",
           "hip_implant" not in M.tasks_da_topografia(
               {"pelve"}, "CT", achados=achados))
    checar("AUTO: coracao de 150 cm3 sem torax traz a trunk_cavities",
           "trunk_cavities" in M.tasks_da_topografia(
               {"cabeca_pescoco"}, "CT", achados=achados, coracao_cm3=150.0)
           and "trunk_cavities" not in M.tasks_da_topografia(
               {"cabeca_pescoco"}, "CT", achados=achados, coracao_cm3=40.0))
    checar("normalizar_modo: o que nao se entende e AUTO (e nunca FAST)",
           M.normalizar_modo("PERSONALIZADO") == "perso"
           and M.normalizar_modo(None) == "auto"
           and M.normalizar_modo("rapido") == "auto"
           and M.normalizar_modo("FAST") == "fast")

    for origem in (M.PROTOCOLO, M.FAST):
        try:
            M.conferir_regra_a(origem, ("total_v3", "lung_nodules"),
                               achados)
            lev = False
        except M.AchadoSemPedido:
            lev = True
        checar("a origem `%s` levanta com achado (omissao)" % origem, lev)
    velho = M.PROT_POR_COD["torax_mama"]["tasks"]
    M.PROT_POR_COD["torax_mama"]["tasks"] = tuple(velho) + ("lung_nodules",)
    try:
        try:
            P(["torax_mama"], {}, "CT", achados=achados)
            lev = False
        except M.AchadoSemPedido:
            lev = True
        checar("ISCA: achado forjado num protocolo PARA a lista", lev)
        try:
            M.conferir_protocolos(T.CATALOGO, achados)
            lev = False
        except M.AchadoSemPedido:
            lev = True
        checar("ISCA: e a conferencia da tabela tambem levanta", lev)
    finally:
        M.PROT_POR_COD["torax_mama"]["tasks"] = velho
    velho_f = M.TASKS_DO_FAST["torax"]
    M.TASKS_DO_FAST["torax"] = tuple(velho_f) + ("lung_nodules",)
    try:
        try:
            F({"torax"}, 700.0, "CT", achados=achados)
            lev = False
        except M.AchadoSemPedido:
            lev = True
        checar("ISCA: achado forjado no FAST PARA a lista", lev)
    finally:
        M.TASKS_DO_FAST["torax"] = velho_f
    velha_dep = M.DEPENDENCIAS_AO_LIGAR.get("breasts")
    M.DEPENDENCIAS_AO_LIGAR["breasts"] = ("abdominal_muscles", "lung_nodules")
    try:
        try:
            P([], {"breasts": 1}, "CT", achados=achados)
            lev = False
        except M.AchadoSemPedido:
            lev = True
        checar("ISCA: a regra da mama arrastando achado PARA a lista", lev)
    finally:
        M.DEPENDENCIAS_AO_LIGAR["breasts"] = velha_dep


_FRASES_DO_TASKS_COMO_ATO = (u"TASKS do config", u"no TASKS", u"lista TASKS",
                             u"in TASKS", u"`TASKS` do config")


def _literais_que_a_tela_mostra(caminho):
    import ast
    import io
    arv = ast.parse(io.open(caminho, encoding="utf-8").read())
    docstrings = set()
    for n in ast.walk(arv):
        if isinstance(n, (ast.Module, ast.FunctionDef, ast.ClassDef)):
            corpo = getattr(n, "body", [])
            if corpo and isinstance(corpo[0], ast.Expr) and isinstance(
                    getattr(corpo[0], "value", None), ast.Constant):
                docstrings.add(id(corpo[0].value))
    return [n.value for n in ast.walk(arv)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)
            and id(n) not in docstrings]


def teste_a_tela_nao_ensina_o_tasks_do_config():
    secao(u"v8.4: a tela nao ensina o TASKS do config como ato declarado")
    achados = []
    for nome in ("radai_modules.py", "radai_provenance_screen.py"):
        for s in _literais_que_a_tela_mostra(_componentes.fonte("app/" + nome)):
            if any(f in s for f in _FRASES_DO_TASKS_COMO_ATO):
                achados.append(u"%s: %s" % (nome, s[:90]))
    checar(u"nenhum literal da porta nem da Procedencia cita o TASKS do "
           u"config", not achados, achados[:4])
    isca = (u"Ligar detecção é escolha declarada: a chave da própria "
            u"tarefa no PERSONALIZADO de uma série, ou o nome dela no TASKS "
            u"do config, que vale para o vigia.")
    checar(u"ISCA: a frase da v8.3 seria pega",
           any(f in isca for f in _FRASES_DO_TASKS_COMO_ATO))
    import radai_provenance_screen as PS
    b = PS.bibliotecas({"em_uso": lambda: {"TASKS": "total_v3 lung_nodules",
                                           "RECORTE_NO_CORPO": 1}})
    checar(u"a Procedencia nao devolve mais `tasks_no_arquivo`",
           "tasks_no_arquivo" not in b, sorted(b))


def main():
    print("test_tasks | catalogo de bibliotecas do TotalSegmentator")
    for t in (teste_catalogo_coerente, teste_licenca_marcada, teste_modalidade,
              teste_recorte, teste_pacote_leva_os_localizadores,
              teste_recorte_no_corpo, teste_o_arranque_diz_o_recorte,
              teste_estado_no_disco, teste_normalizar,
              teste_a_lista_que_vai_rodar,
              teste_a_regra_de_base_por_modalidade,
              teste_uso_em_radioterapia, teste_tamanho_declarado,
              teste_sugerir_dentro_do_teto,
              teste_contraste_por_estrutura, teste_contraste_com_nome_truncado,
              teste_alertas_so_quando_se_sabe, teste_deteccao_de_contraste,
              teste_so_biblioteca_padrao, teste_contra_a_biblioteca,
              teste_a_conferencia_contra_a_biblioteca_sabe_reprovar,
              teste_permitida_nao_quer_dizer_que_existe,
              teste_a_velocidade_sai_da_medida,
              teste_os_segmentos_hepaticos_da_rm_entram_medidos,
              teste_o_peso_em_bases_e_a_estimativa_da_noite,
              teste_os_modos_e_os_protocolos_da_v83,
              teste_a_tela_nao_ensina_o_tasks_do_config):
        try:
            t()
        except Exception as e:
            import traceback
            checar("%s (excecao inesperada)" % t.__name__, False,
                   "%s: %s" % (type(e).__name__, e))
            traceback.print_exc()
    print()
    if FALHAS:
        print("FALHOU: %d de %d checagens" % (FALHAS, OK + FALHAS))
        return 1
    print("OK: %d checagens, todas passaram" % OK)
    return 0


if __name__ == "__main__":
    sys.exit(main())
