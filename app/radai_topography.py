# -*- coding: utf-8 -*-

import re
import unicodedata


TOTAL = "total"
CABECA_PESCOCO = "cabeca_pescoco"

PROTOCOLOS = (
    {"cod": TOTAL, "rotulo": u"Total",
     "ajuda": u"a rotina de sempre: segmenta tudo o que o exame cobrir"},
    {"cod": CABECA_PESCOCO, "rotulo": u"Cabeça e pescoço",
     "ajuda": (u"acrescenta as bibliotecas de cabeça e pescoço — glândulas e "
               u"cavidades, musculatura, ossos e vasos, músculos da "
               u"mastigação")},
)

TASKS_DO_PESCOCO = ("head_glands_cavities", "headneck_muscles",
                    "headneck_bones_vessels", "head_muscles")




_PALAVRAS = (
    "pescoco", "cervical", "cervicais", "laringe", "faringe", "orofaringe",
    "nasofaringe", "hipofaringe", "tireoide", "parotida", "cranio", "face",
    "seios da face", "mandibula", "maxila", "boca", "lingua", "amigdala",
    "tonsila", "glote", "supraglotica", "cabeca e pescoco",
    "neck", "head and neck", "headneck", "larynx", "pharynx", "oropharynx",
    "nasopharynx", "hypopharynx", "thyroid", "parotid", "skull", "facial",
    "sinus", "mandible", "maxilla", "tongue", "tonsil", "glottis",
    "hn", "h&n", "cp",
)

_NEGATIVAS = ("craniocaudal", "cranio caudal", "craniocaud",
              "cp ap", "cpre", "corpo inteiro", "whole body", "body")


def _normalizar(texto):
    t = unicodedata.normalize("NFD", str(texto or ""))
    t = u"".join(c for c in t if unicodedata.category(c) != "Mn").lower()
    return u" " + re.sub(r"[^a-z0-9&]+", u" ", t).strip() + u" "




def _lista(protocolos):
    if protocolos is None:
        vals = []
    elif isinstance(protocolos, (list, tuple, set, frozenset)):
        vals = list(protocolos)
    else:
        vals = [protocolos]
    fora = [TOTAL]
    for v in vals:
        c = normalizar_cod(v)
        if c not in fora:
            fora.append(c)
    return fora


def detectar(*textos):
    junto = _normalizar(u" ".join(str(t or "") for t in textos))
    for ruim in _NEGATIVAS:
        if u" %s " % ruim in junto or junto.startswith(u" %s " % ruim):
            return [TOTAL], u""
    for p in _PALAVRAS:
        if u" %s " % p in junto:
            return [TOTAL, CABECA_PESCOCO], (
                u"o exame diz «%s» — o protocolo de cabeça e pescoço "
                u"acrescenta as bibliotecas da região" % p)
    return [TOTAL], u""


def tasks_de(protocolos, tasks_base):
    escolhidos = _lista(protocolos)
    if CABECA_PESCOCO in escolhidos:
        fora = [t for t in (tasks_base or ()) if t]
        for t in TASKS_DO_PESCOCO:
            if t not in fora:
                fora.append(t)
    else:
        fora = [t for t in (tasks_base or ()) if t and t not in TASKS_DO_PESCOCO]
    return tuple(fora)


def rotulo_de(protocolos):
    escolhidos = _lista(protocolos)
    nomes = [p["rotulo"] for p in PROTOCOLOS if p["cod"] in escolhidos]
    return u" + ".join(nomes) if nomes else PROTOCOLOS[0]["rotulo"]


def so_o_padrao(protocolos):
    return _lista(protocolos) == [TOTAL]


def normalizar_cod(valor):
    v = str(valor or "").strip().lower()
    return CABECA_PESCOCO if v == CABECA_PESCOCO else TOTAL


NOMES_DA_TABELA = ("TASKS_POR_TOPOGRAFIA",)
NOMES_DA_TABELA_MR = ("TASKS_POR_TOPOGRAFIA_MR",)


class AchadoPorOmissao(ValueError):
    pass


def _modalidade_rm(modalidade):
    return str(modalidade or "").strip().upper() in ("MR", "RM")


def tabela_da_topografia(modalidade="CT"):
    try:
        import radai_modes as _M
    except Exception:
        return u"", {}
    fn = getattr(_M, "tabela_da_modalidade", None)
    if fn is not None:
        try:
            t = fn(u"MR" if _modalidade_rm(modalidade) else u"CT")
            if isinstance(t, dict):
                nome = (u"TASKS_POR_TOPOGRAFIA_MR" if _modalidade_rm(modalidade)
                        else u"TASKS_POR_TOPOGRAFIA")
                return nome, dict((k, tuple(v or ())) for k, v in t.items())
        except Exception:
            pass
    nomes = NOMES_DA_TABELA_MR if _modalidade_rm(modalidade) else NOMES_DA_TABELA
    for nome in nomes:
        t = getattr(_M, nome, None)
        if isinstance(t, dict):
            return nome, dict((k, tuple(v or ())) for k, v in t.items())
    return u"", {}


def _alimenta_o_full(task):
    try:
        import radai_sets
        return bool(radai_sets.task_do_full(task))
    except Exception:
        return False


def _achados_do_motor():
    import sys as _sys
    eng = _sys.modules.get("engine")
    if eng is None:
        return set()
    return set(getattr(eng, "TASKS_DE_ACHADO", ()) or ())


def conferir_regra_a(tasks, achados=None):
    tasks = [t for t in (tasks or ()) if t]
    achados = set(_achados_do_motor() if achados is None else (achados or ()))
    intrusas = sorted(set(tasks) & achados)
    try:
        import radai_modes as _M
        fn = getattr(_M, "conferir_regra_a", None)
        origem = getattr(_M, "ANATOMIA", None) or getattr(_M, "PADRAO", None)
        if fn is not None and origem is not None:
            fn(origem, tuple(tasks), achados)
    except TypeError:
        pass
    except Exception as e:
        raise AchadoPorOmissao(u"%s" % e)
    if intrusas:
        raise AchadoPorOmissao(
            u"a lista por topografia do vigia trouxe %d task(s) de ACHADO sem "
            u"ninguem ter pedido: %s. De fabrica nada detecta (REGRA A); "
            u"deteccao roda por ato declarado -- o TASKS do config, ou a caixa "
            u"no «Rodar agora». A serie NAO roda com esta lista, e o vigia "
            u"pausa: e erro de configuracao, e nao da serie."
            % (len(intrusas), u", ".join(intrusas)))


def tasks_governadas(modalidade="CT"):
    _nome, tabela = tabela_da_topografia(modalidade)
    fora = set()
    for ts in tabela.values():
        for t in ts:
            if _alimenta_o_full(t):
                fora.add(t)
    return frozenset(fora)


CRANIO = "cranio"
TORAX = "torax"


def _o_motor(motor):
    if motor is not None:
        return motor
    import engine
    return engine


def coracao_do_modelo_cm3(masks, grade, motor=None):
    if grade is None:
        return None
    try:
        import radai_names as _nm
        nomes = [k for k in (_nm.CHAVE_DO_CORACAO_DO_MODELO, "heart")
                 if k in (masks or {})]
        if not nomes:
            return 0.0
        return round(float(_o_motor(motor)._volume_cm3(masks, nomes, grade)),
                     1)
    except Exception:
        return None


def _cru_da_base(cruas):
    if not cruas:
        return None
    try:
        import radai_output
        return radai_output.cruas_da_base(cruas)
    except Exception:
        return None


def anatomia_da_base(masks, grade, cruas=None, motor=None):
    regioes, laudo = set(), []
    try:
        motor = _o_motor(motor)
    except Exception as e:
        return {"regioes": (), "coracao_cm3": None, "pescoco": None,
                "laudo": [u"anatomia: o motor nao carregou (%s: %s)"
                          % (type(e).__name__, str(e)[:80])]}
    cru = _cru_da_base(cruas)
    encefalo = False
    try:
        r, l = motor.regioes_no_campo(masks, grade=grade)
        for cod in (r or ()):
            if cod == CABECA_PESCOCO:
                encefalo = True
            elif cod != TORAX:
                regioes.add(cod)
        for linha in (l or ()):
            if linha.startswith(u"torax"):
                continue
            laudo.append(linha.replace(u"cabeca_pescoco:",
                                       u"cabeca (encefalo):", 1))
    except Exception as e:
        laudo.append(u"cabeca, abdome e pelve: nao consegui medir (%s: %s)"
                     % (type(e).__name__, str(e)[:80]))
    pescoco = None
    try:
        tem, pq = motor.pescoco_no_campo(masks, grade, cru=cru)
        pescoco = (bool(tem), pq)
        laudo.append(pq)
    except Exception as e:
        laudo.append(u"pescoco: nao consegui medir (%s)" % type(e).__name__)
    if pescoco is not None and pescoco[0]:
        regioes.add(CABECA_PESCOCO)
    elif encefalo:
        regioes.add(CRANIO)
        laudo.append(u"cranio: sim (o encefalo esta no campo e o pescoco nao "
                     u"— a lista do cranio, e nao a de cabeca e pescoco)")
    try:
        import radai_skin
        tem, pq = radai_skin.torax_identificado(masks, grade, cru=cru)
        if tem:
            regioes.add(TORAX)
        laudo.append(u"torax: %s (%s)" % (u"sim" if tem else u"nao", pq))
    except Exception as e:
        laudo.append(u"torax: nao consegui medir (%s: %s)"
                     % (type(e).__name__, str(e)[:80]))
    coracao = coracao_do_modelo_cm3(masks, grade, motor)
    laudo.append(u"coracao do modelo: %s" % (
        u"nao medido" if coracao is None else (u"%.1f cm3" % coracao)))
    return {"regioes": tuple(sorted(regioes)), "laudo": laudo,
            "coracao_cm3": coracao, "pescoco": pescoco}


def tasks_da_anatomia(regioes, modalidade="CT", achados=None,
                      coracao_cm3=None):
    nome, tabela = tabela_da_topografia(modalidade)
    candidatas = None
    try:
        import radai_modes as _M
        fn = getattr(_M, "tasks_da_topografia", None)
        if fn is not None:
            base = getattr(_M, "base_de", lambda m: u"")(
                u"MR" if _modalidade_rm(modalidade) else u"CT")
            ach = (_achados_do_motor() if achados is None
                   else set(achados or ()))
            extra = {}
            if coracao_cm3 is not None:
                extra["coracao_cm3"] = coracao_cm3
            candidatas = [t for t in fn(regioes, modalidade, achados=ach,
                                        **extra)
                          if t and t != base]
    except Exception as e:
        if type(e).__name__ == "AchadoSemPedido":
            raise AchadoPorOmissao(u"%s" % e)
        candidatas = None
    if candidatas is None:
        candidatas = []
        try:
            import radai_modes as _M2
            ordem = list(getattr(_M2, "TOPOGRAFIAS", ()) or ())
        except Exception:
            ordem = []
        pedidas = set(regioes or ())
        for r in ordem + sorted(pedidas - set(ordem)):
            if r not in pedidas:
                continue
            for t in tabela.get(r, ()):
                if t and t not in candidatas:
                    candidatas.append(t)
    tasks, fora = [], []
    for t in candidatas:
        if not t or t in tasks:
            continue
        if not _alimenta_o_full(t):
            if not any(f[0] == t for f in fora):
                fora.append((t, u"nao alimenta o FULL: e plugin, e so "
                                u"roda quando pedido"))
            continue
        tasks.append(t)
    conferir_regra_a(tasks, achados)
    return tuple(tasks), fora, nome


def tasks_da_escolha_manual(protocolos):
    if CABECA_PESCOCO not in _lista(protocolos):
        return ()
    tasks, _fora, _nome = tasks_da_anatomia([CABECA_PESCOCO], "CT")
    return tasks


PREFIXO_NOSSO = "RS_RadAI_"


def entregas_a_substituir(arquivos):
    fora = []
    for nome in (arquivos or ()):
        n = str(nome)
        if n.startswith(PREFIXO_NOSSO) and n.lower().endswith((".dcm", ".txt")):
            fora.append(n)
    return sorted(fora)


def aviso_de_substituicao(protocolo, arquivos, feito_em=""):
    lista = entregas_a_substituir(arquivos)
    if not lista:
        return u""
    return (u"Esta série já foi segmentada%s pelo protocolo <b>Total</b>, e há "
            u"%d arquivo(s) RadAI na pasta dela.<br><br>"
            u"Rodar de novo com <b>%s</b> vai <b>apagar</b> esses arquivos e "
            u"gravar os novos no lugar. O que não é nosso — o exame, e "
            u"qualquer contorno que outra pessoa tenha posto ali — não é "
            u"tocado.<br><br><code>%s</code>"
            % ((u" em %s" % feito_em) if feito_em else u"",
               len(lista), rotulo_de(protocolo),
               u"<br>".join(lista[:8])
               + (u"<br>… e mais %d" % (len(lista) - 8) if len(lista) > 8
                  else u"")))
