# -*- coding: utf-8 -*-
import io
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _cleanup
import _componentes
_cleanup.adotar_prefixo('radai_pesos_')

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "app"))

_ok = 0
_falhou = 0
_falhas = []


def secao(t):
    print(u"")
    print(u"── %s %s" % (t, u"─" * max(0, 58 - len(t))))


def checar(rotulo, cond, detalhe=u""):
    global _ok, _falhou
    if cond:
        _ok += 1
        print(u"  OK     %s" % rotulo)
    else:
        _falhou += 1
        _falhas.append(rotulo)
        print(u"  FALHA  %s  %s"
              % (rotulo, str(detalhe).replace("\n", " | ")[:150]))


def teste_a_tela_nao_oferece_o_que_o_motor_recusa():
    secao(u"a tela nao oferece o que o motor recusa")
    import engine
    import radai_tasks

    cat = radai_tasks.estado()
    checar(u"o catalogo diz se cada task e permitida",
           all("permitida" in t for t in cat))
    perm = set(engine.TASKS_PERMITIDAS)
    erradas = [t["task"] for t in cat
               if (t["task"] in perm) != (t.get("permitida") is True)]
    checar(u"e o que ele diz bate com o motor", not erradas, erradas)

    proibidas = [t for t in cat if t.get("permitida") is False]
    checar(u"o catalogo NAO oferece nenhuma task que o motor recusa",
           not proibidas, [t["task"] for t in proibidas][:4] or
           u"caixa marcavel que baixa peso e depois recusa rodar")

    _fant = {"task": "body", "rotulo": u"(fantoma da bateria)", "classes": 2,
             "modalidade": "CT", "comercial": False, "datasets": [299],
             "mb": 233, "rt": "fora"}
    radai_tasks.CATALOGO.append(_fant)
    radai_tasks.POR_NOME[_fant["task"]] = _fant
    try:
        com_fantoma = [t for t in radai_tasks.estado()
                       if t.get("permitida") is False]
        checar(u"  (fantoma) uma task fora do motor SAI como nao permitida",
               [t["task"] for t in com_fantoma] == ["body"],
               [t["task"] for t in com_fantoma][:4] or
               u"`permitida` seria constante True e nada acusaria")
        checar(u"  (fantoma) e ela traz o motivo, vindo do motor",
               all(t.get("porque_nao") for t in com_fantoma),
               [t.get("porque_nao") for t in com_fantoma][:1])
    finally:
        radai_tasks.CATALOGO.remove(_fant)
        radai_tasks.POR_NOME.pop(_fant["task"], None)
    checar(u"  e a tabela voltou ao estado de origem",
           not any(t["task"] == "body" for t in radai_tasks.CATALOGO))

    import engine as _E
    _dets = sorted(set(_E.TASKS_DE_ACHADO) & set(t["task"] for t in cat))
    checar(u"ha task de ACHADO no catalogo para servir de exemplo",
           bool(_dets),
           u"sem nenhuma, o par da REGRA B nao mede nada e some calado")
    for _n in _dets:
        dete = [t for t in cat if t["task"] == _n]
        checar(u"REGRA B: `%s` E' oferecida na tela" % _n,
               dete[0].get("permitida") is True, dete[0].get("porque_nao"))
        checar(u"  e `%s` vem com o selo `achado`" % _n,
               dete[0].get("achado") is True, dete[0].get("achado"))

    nomes = set(t["task"] for t in cat)
    do_motor = set(engine.TASKS_DE_ACHADO) & nomes
    checar(u"ha task de achado no catalogo", bool(do_motor),
           u"TASKS_DE_ACHADO=%s" % sorted(engine.TASKS_DE_ACHADO))
    sem_selo = sorted(t["task"] for t in cat
                      if t["task"] in do_motor and t.get("achado") is not True)
    checar(u"toda task de `TASKS_DE_ACHADO` sai com `achado=True`",
           not sem_selo, sem_selo)
    selados = set(t["task"] for t in cat if t.get("achado") is True)
    checar(u"e toda task com `achado=True` esta em `TASKS_DE_ACHADO`",
           selados == do_motor, sorted(selados - do_motor))
    indefinidas = sorted(t["task"] for t in cat if t.get("achado") is None)
    checar(u"e nenhuma fica com `achado=None` (o motor carregou)",
           not indefinidas, indefinidas)

    import radai_provenance_screen as _PS
    js = _PS.JS
    _pr = js[js.find(u"function prBib("):]
    _pr = _pr[:_pr.find(u"\nfunction ", 10)]
    checar(u"a Procedencia le o campo `permitida` (a lista saiu da /config)",
           u"t.permitida === false" in _pr, u"%d caracteres de prBib" % len(_pr))
    checar(u"e marca a task recusada, em vez de esconde-la (a linha fica)",
           u"não roda nesta instalação" in _pr
           and u"(b.tasks || []).forEach(" in _pr
           and u".filter(" not in _pr)
    checar(u"e mostra o motivo", u"prEsc(t.porque_nao)" in _pr)
    checar(u"  e o servidor manda o motivo junto (`bibliotecas`)",
           all("porque_nao" in t for t in (_PS.bibliotecas({}).get("tasks")
                                            or [{}])))


def teste_as_duas_listas_batem():
    secao(u"o catalogo e a lista de permitidos descrevem o mesmo conjunto")
    import engine
    import radai_tasks

    cat = set(t["task"] for t in radai_tasks.estado())
    perm = set(engine.TASKS_PERMITIDAS)

    reservas = set(getattr(radai_tasks, "RESERVAS", frozenset()))
    orfas = sorted(perm - cat - reservas)
    checar(u"toda task PERMITIDA esta no catalogo", not orfas,
           u"%s — a tela nao tem como oferece-la, e o operador nao consegue "
           u"liga-la" % u", ".join(orfas))
    for _r in sorted(reservas):
        checar(u"a reserva `%s` E permitida" % _r, _r in perm,
               u"sem isso a estacao que caiu para ela morre em "
               u"`conferir_tasks`, uma serie por vez")
        checar(u"  e NAO e oferecida na tela", _r not in cat,
               u"duas linhas «Corpo inteiro» marcaveis rodam a base 2x")

    extras = sorted(cat - perm)
    checar(u"e as do catalogo que nao rodam sao rotuladas",
           all(t.get("porque_nao") for t in radai_tasks.estado()
               if t["task"] in extras),
           u"%d sem motivo" % len([t for t in radai_tasks.estado()
                                   if t["task"] in extras
                                   and not t.get("porque_nao")]))


def teste_permitida_e_disponivel_sao_perguntas_diferentes():
    secao(u"permitida e disponivel sao perguntas DIFERENTES")
    import engine
    import radai_tasks

    cat = radai_tasks.estado()
    por_nome = dict((t["task"], t) for t in cat)
    checar(u"o catalogo diz se cada task esta disponivel",
           all("disponivel" in t for t in cat))

    _antes = dict(radai_tasks.EXIGEM_TS)
    try:
        radai_tasks.EXIGEM_TS.clear()
        radai_tasks.EXIGEM_TS.update(_antes)
        if not radai_tasks.EXIGEM_TS:
            _perm = sorted(t["task"] for t in cat if t.get("permitida") is True)
            checar(u"ha task permitida para servir de fantoma", bool(_perm))
            if not _perm:
                raise SystemExit(0)
            _alvo = _perm[0]
            radai_tasks.EXIGEM_TS[_alvo] = "99.0.0"
            cat = radai_tasks.estado()
            por_nome = dict((t["task"], t) for t in cat)
            checar(u"(fantoma) o mecanismo de `EXIGEM_TS` continua vivo",
                   por_nome[_alvo].get("disponivel") is False,
                   u"tabela vazia nao pode virar mecanismo morto")
        for task, versao in sorted(radai_tasks.EXIGEM_TS.items()):
            item = por_nome.get(task)
            checar(u"`%s` esta no catalogo" % task, bool(item))
            if not item:
                continue
            checar(u"  e sai com `disponivel=False`",
                   item.get("disponivel") is False, item.get("disponivel"))
            porque = item.get("porque_indisponivel") or u""
            checar(u"  e o motivo cita a versao (`%s`)" % versao,
                   versao in porque, porque[:90])
            checar(u"  e cita o TotalSegmentator pelo nome",
                   u"TotalSegmentator" in porque, porque[:90])
            checar(u"  e `exige_ts` traz a versao para a tela",
                   item.get("exige_ts") == versao, item.get("exige_ts"))

        _b = {"task": "body", "rotulo": u"(fantoma da bateria)", "classes": 2,
              "modalidade": "CT", "comercial": False, "datasets": [],
              "mb": 233, "rt": "fora"}
        radai_tasks.CATALOGO.append(_b)
        radai_tasks.POR_NOME[_b["task"]] = _b
        try:
            cat2 = radai_tasks.estado()
        finally:
            radai_tasks.CATALOGO.remove(_b)
            radai_tasks.POR_NOME.pop(_b["task"], None)
        perm_indisp = sorted(t["task"] for t in cat
                             if t.get("permitida") is True
                             and t.get("disponivel") is False)
        naoperm_disp = sorted(t["task"] for t in cat2
                              if t.get("permitida") is False
                              and t.get("disponivel") is True)
        checar(u"ha task PERMITIDA e INDISPONIVEL", bool(perm_indisp),
               u"sem ela, `disponivel` poderia ser apelido de `permitida`")
        checar(u"(fantoma) ha task NAO permitida e DISPONIVEL",
               bool(naoperm_disp),
               u"sem ela, `permitida` poderia ser apelido de `disponivel`")
    finally:
        radai_tasks.EXIGEM_TS.clear()
        radai_tasks.EXIGEM_TS.update(_antes)
    cat = radai_tasks.estado()
    checar(u"a tabela voltou ao estado de origem",
           dict(radai_tasks.EXIGEM_TS) == _antes)
    if perm_indisp and naoperm_disp:
        checar(u"  e os dois conjuntos sao disjuntos",
               not (set(perm_indisp) & set(naoperm_disp)),
               u"%s | %s" % (perm_indisp[:3], naoperm_disp[:3]))
    checar(u"as duas fontes nao descrevem o mesmo conjunto",
           set(radai_tasks.EXIGEM_TS) != set(engine.TASKS_PERMITIDAS))

    sujas = sorted(t["task"] for t in cat
                   if t.get("disponivel") is True
                   and (t.get("porque_indisponivel") or t.get("exige_ts")))
    checar(u"task disponivel nao carrega motivo de indisponibilidade",
           not sujas, sujas)
    mudas = sorted(t["task"] for t in cat
                   if t.get("disponivel") is False
                   and not (t.get("porque_indisponivel") or u"").strip())
    checar(u"e TODA indisponivel traz o motivo", not mudas, mudas)


def teste_a_escolha_da_tela_chega_ao_download():
    secao(u"a escolha de «não instalar» chega ao download")
    sys.path.insert(0, os.path.join(_componentes.raiz_da_suite(), "build"))
    import configurar_ambiente as C

    checar(u"`dispensados` existe", hasattr(C, "dispensados"))
    checar(u"e há ponte do nome da licença para o id do registro",
           hasattr(C, "IDENT_DISPENSAVEL"))

    d = tempfile.mkdtemp(prefix="radai_pesos_disp_")
    try:
        arq = os.path.join(d, "LICENCAS_ACEITAS.txt")
        io.open(arq, "w", encoding="utf-8").write(
            u"[ACEITA] TotalSegmentator - Apache 2.0\n"
            u"[DISPENSADO] nnInteractive - CC BY-NC-SA 4.0\n"
            u"[ACEITA] CADS - CC BY-SA 4.0\n"
            u"[DISPENSADO] VISTA-3D - NVIDIA License, clausula 3.3\n")
        from pathlib import Path
        lidos = C.dispensados(Path(arq))
        checar(u"com a lista vazia, nenhum `[DISPENSADO]` e' honrado",
               not lidos, u"%s" % lidos)
        _od, _oi = tuple(C.DISPENSAVEIS), dict(C.IDENT_DISPENSAVEL)
        try:
            C.DISPENSAVEIS = (u"nnInteractive",)
            C.IDENT_DISPENSAVEL = dict(_oi, **{u"nnInteractive": u"nninteractive"})
            _lidos2 = C.dispensados(Path(arq))
            checar(u"injetado, ele le o `[DISPENSADO]` da tela",
                   u"nnInteractive" in _lidos2, u"%s" % _lidos2)
            checar(u"e a ponte traduz nome de tela para id do registro",
                   C.IDENT_DISPENSAVEL.get(u"nnInteractive") == u"nninteractive")
        finally:
            C.DISPENSAVEIS, C.IDENT_DISPENSAVEL = _od, _oi
        _orig = dict(_oi)
        checar(u"e hoje a ponte esta VAZIA (nao ha componente restrito)",
               not _orig, repr(_orig))
        checar(u"e o que saiu do registro não vira id",
               C.IDENT_DISPENSAVEL.get(u"VISTA-3D") is None,
               repr(C.IDENT_DISPENSAVEL))
        checar(u"e `[ACEITA]` não vira dispensado", u"CADS" not in lidos)
        io.open(arq, "w", encoding="utf-8").write(u"[ACEITA] tudo\n")
        checar(u"sem dispensa, a lista é vazia", C.dispensados(Path(arq)) == [])
        checar(u"arquivo ausente devolve lista vazia, e não tudo",
               C.dispensados(Path(os.path.join(d, "nao_existe.txt"))) == [])
    finally:
        shutil.rmtree(d, ignore_errors=True)

    fonte = io.open(os.path.join(_componentes.raiz_da_suite(), "build", "configurar_ambiente.py"),
                    encoding="utf-8").read()
    i = fonte.find(u"def etapa_pesos(")
    corpo = fonte[i:fonte.find(u"\ndef ", i + 10)] if i >= 0 else u""
    checar(u"`etapa_pesos` chama `dispensados`", u"dispensados(" in corpo,
           u"a escolha da tela não alcançaria o download")
    checar(u"  e entrega a escolha ao laço do registro",
           u"baixar_modelos_do_registro(ctx, radai_models, fora_por_escolha)" in corpo)
    j = fonte.find(u"def baixar_modelos_do_registro(")
    corpo += fonte[j:fonte.find(u"\ndef ", j + 10)] if j >= 0 else u""

    import ast as _ast
    achou = []
    for no in _ast.walk(_ast.parse(fonte)):
        if not (isinstance(no, _ast.FunctionDef)
                and no.name in ("etapa_pesos", "baixar_modelos_do_registro")):
            continue
        for dentro in _ast.walk(no):
            if not isinstance(dentro, _ast.If):
                continue
            t = dentro.test
            if not (isinstance(t, _ast.Compare) and len(t.ops) == 1
                    and isinstance(t.ops[0], _ast.In)):
                continue
            alvo = t.comparators[0]
            if getattr(alvo, "id", "") != "fora_por_escolha":
                continue
            if any(isinstance(c, _ast.Continue) for c in dentro.body):
                achou.append(dentro.lineno)
    checar(u"e o laço PULA o dispensado (`in` + `continue`, sem `and`)",
           len(achou) == 1, u"%d ocorrência(s)" % len(achou))
    checar(u"o log diz DISPENSADO, e não «não baixado»",
           u"DISPENSADO por escolha" in corpo)
    checar(u"e o resumo separa os três desfechos",
           u"o que este pacote leva" in corpo
           and u"NAO BAIXADO" in corpo)


def main():
    print(u"=" * 66)
    print(u"test_weights | o catalogo de tasks: permitida, disponivel e a escolha do preparo")
    print(u"=" * 66)
    teste_a_escolha_da_tela_chega_ao_download()
    teste_a_tela_nao_oferece_o_que_o_motor_recusa()
    teste_as_duas_listas_batem()
    teste_permitida_e_disponivel_sao_perguntas_diferentes()
    print(u"\n" + u"=" * 66)
    if _falhou:
        print(u"FALHOU: %d de %d checagens" % (_falhou, _ok + _falhou))
        for f in _falhas:
            print(u"  - %s" % f)
    else:
        print(u"OK: %d checagens, todas passaram" % _ok)
    print(u"=" * 66)
    return 1 if _falhou else 0


if __name__ == "__main__":
    sys.exit(main())
