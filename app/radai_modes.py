# -*- coding: utf-8 -*-

import re


ANATOMIA = "anatomia"
MARCADO = "marcado"
PROTOCOLO = "protocolo"
FAST = "fast"
# GUARDA: o vigia nao le o TASKS do config. Os atos declarados sao a chave da
# task no PERSONALIZADO e o protocolo de ESTUDO das Reconstrucoes 3D, que roda
# achado com o selo ACHADO e nunca grava RTSTRUCT (so o mapa de rotulos).
ESTUDO = "estudo"
ATOS_DECLARADOS = (MARCADO, ESTUDO)

PADRAO = "padrao"


CABECA_PESCOCO = "cabeca_pescoco"
TORAX = "torax"
ABDOME = "abdome"
PELVE = "pelve"
MEMBROS = "membros"

REGIOES = (CABECA_PESCOCO, TORAX, ABDOME, PELVE, MEMBROS)

CRANIO = "cranio"
TOPOGRAFIAS = (CRANIO, CABECA_PESCOCO, TORAX, ABDOME, PELVE, MEMBROS)

ROTULO_REGIAO = {
    CRANIO: u"crânio",
    CABECA_PESCOCO: u"cabeça e pescoço",
    TORAX: u"tórax",
    ABDOME: u"abdome",
    PELVE: u"pelve",
    MEMBROS: u"membros",
}


BASE_DA_MODALIDADE = {"CT": "total_v3", "MR": "total_mr"}


def base_de(modalidade):
    return BASE_DA_MODALIDADE.get(_modalidade(modalidade), "total_v3")


def _modalidade(v):
    m = str(v or "").strip().upper()
    return "MR" if m in ("MR", "MRI", "RM") else "CT"


def _cabe_na_modalidade(item, mod):
    c = item.get("modalidade")
    return (c is None) or (_modalidade(c) == mod)


TASKS_POR_TOPOGRAFIA = {
    CRANIO: ("head_glands_cavities", "craniofacial_structures"),
    CABECA_PESCOCO: ("head_glands_cavities", "headneck_muscles",
                     "headneck_bones_vessels", "head_muscles",
                     "craniofacial_structures",
                     ),
    TORAX: ("trunk_cavities", "breasts", "pleural_pericard_effusion"),
    ABDOME: ("trunk_cavities",),
    PELVE: ("trunk_cavities",),
    MEMBROS: (),
}

CORACAO_MINIMO_CM3 = 100.0
TASKS_DO_CORACAO_SEM_TORAX = ("trunk_cavities",)

TASKS_POR_TOPOGRAFIA_MR = {
    CRANIO: (),
    CABECA_PESCOCO: (),
    TORAX: (),
    ABDOME: (),
    PELVE: (),
    MEMBROS: (),
}


def tabela_da_modalidade(modalidade):
    return (TASKS_POR_TOPOGRAFIA_MR if _modalidade(modalidade) == "MR"
            else TASKS_POR_TOPOGRAFIA)


MOTORES = (
    {"cod": "cads", "rotulo": u"CADS",
     "lento": True, "modalidade": "CT",
     "ajuda": (u"reto, próstata, vesículas seminais e sigmoide, num arquivo "
               u"próprio (sufixo _cds). Pesos CC BY-SA 4.0. É o mais lento do "
               u"acervo — numa TC de planejamento ele sozinho costuma custar "
               u"mais que todo o resto junto")},
    {"cod": "nv", "rotulo": u"NV-Segment-CT",
     "lento": True, "modalidade": "CT",
     "ajuda": (u"anatomia completa para comparação, num arquivo próprio "
               u"(sufixo _nv). Pesos sob NVIDIA Open Model License, de uso "
               u"comercial — e o cartão do modelo diz que é para pesquisa, "
               u"não para uso clínico")},
    {"cod": "mse", "rotulo": u"MOOSE",
     "lento": False, "modalidade": "CT",
     "ajuda": (u"câmaras cardíacas e composição corporal, num arquivo "
               u"próprio (sufixo _mse). Nove estruturas que nenhuma outra fonte "
               u"do pacote tem: as quatro câmaras, o miocárdio, a artéria "
               u"pulmonar, o músculo esquelético e as duas gorduras. Pesos "
               u"CC BY 4.0")},
    {"cod": "hnlnl", "rotulo": u"Níveis cervicais",
     "lento": False, "regiao": CABECA_PESCOCO, "modalidade": "CT",
     "caixa": (u"Níveis cervicais — só em série com a cabeça no campo; "
               u"nomes de Grégoire pelo mapa dos autores, e no STUDY só a "
               u"união e as parótidas do nível VIII"),
     "ajuda": (u"os 20 níveis linfonodais cervicais, com os nomes de Grégoire "
               u"(Lvl_Ia a Lvl_VIIb) pelo mapa dos autores do modelo. Só saem "
               u"em série com a cabeça no campo: o portão exige o encéfalo, e "
               u"numa TC de tórax não sai nada — o log diz por quê. Os níveis "
               u"entram no FULL; no STUDY entram a LNL_UNION, união anatômica "
               u"não aprovada que não é OAR nem CTV, e as parótidas do nível "
               u"VIII menos o esternocleidomastoide. Pesos CC0 (Weissmann et "
               u"al. 2023)")},
    {"cod": "cranio_ct", "rotulo": u"Encéfalo em TC", "lento": False,
     "regiao": CRANIO, "modalidade": "CT", "no_full": True,
     "caixa": (u"Encéfalo em TC — tronco encefálico, quiasma, cerebelo, "
               u"ventrículos e linha média; só com o encéfalo no campo"),
     "ajuda": (u"Tronco encefálico e quiasma óptico (FULL e STUDY); cerebelo, "
               u"ventrículos e linha média (só FULL). Só com o encéfalo no "
               u"campo. Pesos MIT (Buti et al. 2025)")},
)

MOTORES_NO_FULL = tuple(m["cod"] for m in MOTORES if m.get("no_full"))
MOTORES_DO_AUTO_POR_REGIAO = {CRANIO: ("cranio_ct",),
                              CABECA_PESCOCO: ("cranio_ct",)}


def motores_do_auto(regioes, modalidade="CT"):
    if _modalidade(modalidade) != "CT":
        return ()
    fora = []
    for r in (regioes or ()):
        for c in MOTORES_DO_AUTO_POR_REGIAO.get(r, ()):
            if c not in fora:
                fora.append(c)
    return tuple(fora)

MOT_POR_COD = dict((m["cod"], m) for m in MOTORES)


def motores_da_escolha(marcados, modalidade="CT"):
    mod = _modalidade(modalidade)
    pedidos = set(normalizar_escolhidas(marcados))
    return tuple(m["cod"] for m in MOTORES
                 if m["cod"] in pedidos and _cabe_na_modalidade(m, mod))


def ajuda_do_motor(cod, alimentam=None):
    m = MOT_POR_COD.get(cod)
    if m is None:
        return u""
    base = m.get("ajuda") or u""
    if alimentam is None:
        return base
    if cod in set(alimentam):
        frase = (u"Ele entrega estrutura que entra no conjunto final.")
    else:
        frase = (u"Nenhuma estrutura dele entra no conjunto final: ele roda "
                 u"só quando marcado, num arquivo separado.")
    return (base + u"\n" + frase) if base else frase



def _item_de_task(t, d, achados, permitidas, est, contraste, entregues,
                  recorte_no_corpo, topografia=None, sugerida=False):
    def _rt():
        try:
            import radai_tasks as _m
            return _m
        except Exception:
            return None
    rt = _rt()
    custo = rotulo_custo = None
    ficha = []
    vel = None
    if rt is not None:
        try:
            custo = rt.custo_relativo(t)
            rotulo_custo = rt.ROTULO_CUSTO.get(custo, u"") if custo else u""
        except Exception:
            custo, rotulo_custo = None, u""
        try:
            ficha = rt.ficha(t, entregues=(entregues or {}).get(t),
                             recorte_no_corpo=recorte_no_corpo)
        except Exception:
            ficha = []
        try:
            vel = rt.velocidade(t)
        except Exception:
            vel = None
    e = est.get(t) or {}
    return {
        "task": t,
        "rotulo": (d or {}).get("rotulo") or e.get("rotulo") or t,
        "achado": t in achados,
        "permitida": (None if permitidas is None
                      else bool(t in (permitidas or ()))),
        "disponivel": e.get("disponivel"),
        "porque_nao": e.get("porque_nao") or u"",
        "sugerida": bool(sugerida) and t not in achados
                    and not (permitidas is not None
                             and t not in (permitidas or ())),
        "datasets": list((d or {}).get("datasets") or ()),
        "classes": (d or {}).get("classes"),
        "mb": (d or {}).get("mb"),
        "contraste": contraste.get(t) or "",
        "regiao": topografia,
        "custo": custo,
        "custo_rotulo": rotulo_custo or u"",
        "velocidade": (vel or {}).get("tag"),
        "velocidade_medida": bool((vel or {}).get("medida")),
        "velocidade_rotulo": (rt.rotulo_de_velocidade(vel)
                              if (rt is not None and vel) else u""),
        "ficha": ficha,
    }


def item_da_base(modalidade="CT", catalogo=None, entregues=None,
                 recorte_no_corpo=None, contraste=None):
    t = base_de(modalidade)
    d = None
    for x in (catalogo or ()):
        if x.get("task") == t:
            d = x
    if contraste is None:
        try:
            import radai_tasks as _rt
            contraste = getattr(_rt, "CONTRASTE_TASK", {})
        except Exception:
            contraste = {}
    return _item_de_task(t, d, set(), None, {}, dict(contraste or {}),
                         entregues, recorte_no_corpo)



def _filtrar(fora, mod, permitidas=None, catalogo=None):
    if permitidas is not None:
        fora = [t for t in fora if t in permitidas]
    if catalogo:
        por_nome = dict((d.get("task"), d) for d in catalogo)
        fora = [t for t in fora
                if t not in por_nome
                or _modalidade(por_nome[t].get("modalidade")) == mod]
    return fora


def _coracao_fora_do_torax(regioes, coracao_cm3, mod):
    if mod != "CT" or TORAX in set(regioes or ()):
        return ()
    try:
        cm3 = float(coracao_cm3)
    except (TypeError, ValueError):
        return ()
    return TASKS_DO_CORACAO_SEM_TORAX if cm3 >= CORACAO_MINIMO_CM3 else ()


def tasks_da_topografia(regioes, modalidade="CT", permitidas=None, achados=(),
                        catalogo=None, coracao_cm3=None):
    mod = _modalidade(modalidade)
    regioes = set(regioes or ())
    achados = set(achados or ())
    tabela = tabela_da_modalidade(mod)
    fora = [base_de(mod)]
    for r in TOPOGRAFIAS:
        if r not in regioes:
            continue
        for t in tabela.get(r, ()):
            if t and t not in fora:
                fora.append(t)
    for t in _coracao_fora_do_torax(regioes, coracao_cm3, mod):
        if t not in fora:
            fora.append(t)
    fora = tuple(_filtrar(fora, mod, permitidas, catalogo))
    conferir_regra_a(ANATOMIA, fora, achados)
    return fora


def tasks_do_modo(modo, modalidade="CT", regioes=(), escolhidas=(),
                  permitidas=None, achados=(), catalogo=None):
    if str(modo or "").strip().lower() != PADRAO:
        raise ValueError(
            u"os modos Personalizado e Completo da v8.1 sairam em 24/09/2026 "
            u"(v8.2): o «Rodar agora» roda o modo da serie -- FAST, AUTO ou "
            u"PERSONALIZADO (MODOS_DA_SERIE, tasks_do_personalizado) -- e o "
            u"vigia, a tabela por topografia (tasks_da_topografia). Pedido: %r"
            % (modo,))
    return tasks_da_topografia(regioes, modalidade, permitidas=permitidas,
                               achados=achados, catalogo=catalogo)





class AchadoSemPedido(Exception):
    pass


def conferir_regra_a(origem, tasks, achados):
    o = str(origem or "").strip().lower()
    if o in ATOS_DECLARADOS:
        return
    intrusas = sorted(set(tasks or ()) & set(achados or ()))
    if intrusas:
        raise AchadoSemPedido(
            u"a lista montada por %s trouxe %d task(s) de achado sem ninguem "
            u"ter pedido: %s. O que roda por omissao nao procura achado -- a "
            u"regra 6 (13/09/2026) permite deteccao POR ATO DECLARADO, que e "
            u"a chave da task ligada no PERSONALIZADO do «Rodar agora». O "
            u"vigia nao le task do config. Nao e pela tabela por topografia "
            u"(TASKS_POR_TOPOGRAFIA), nem pela pre-marcacao de um estudo, nem "
            u"pelo que um protocolo arrasta, nem pelo modo FAST."
            % (o or u"(origem vazia)", len(intrusas), ", ".join(intrusas)))


def descricao_da_escolha(origem, tasks=(), achados=(), protocolos=()):
    o = str(origem or "").strip().lower()
    quem = {MARCADO: u"marcado na tela",
            ESTUDO: u"protocolo de estudo (Reconstrucoes 3D)",
            ANATOMIA: u"pela anatomia",
            PROTOCOLO: u"arrastado pelo protocolo",
            FAST: u"modo FAST"}.get(o, o or u"?")
    txt = u"%s: %d biblioteca(s)" % (quem, len(tasks or ()))
    prot = [p for p in normalizar_escolhidas(protocolos)]
    if prot:
        txt += u" | protocolos: %s" % u", ".join(prot)
    achou = sorted(set(tasks or ()) & set(achados or ()))
    if achou:
        txt += (u" | ACHADO: %s — rodando porque %s"
                % (u", ".join(achou),
                   u"foi marcado" if o == MARCADO
                   else u"o estudo 3D foi pedido" if o == ESTUDO else u"?"))
    return txt




MODO_FAST = "fast"
MODO_AUTO = "auto"
MODO_PERSO = "perso"
MODOS_DA_SERIE = (MODO_FAST, MODO_AUTO, MODO_PERSO)
MODO_DE_FABRICA = MODO_AUTO


def normalizar_modo(valor):
    v = str(valor or "").strip().lower()
    if v in ("personalizado", "personalizar", "custom"):
        v = MODO_PERSO
    return v if v in MODOS_DA_SERIE else MODO_DE_FABRICA


TASKS_DO_FAST = {
    TORAX: ("trunk_cavities", "breasts", "pleural_pericard_effusion"),
}


def tasks_do_fast(regioes, coracao_cm3=None, modalidade="CT", permitidas=None,
                  achados=(), catalogo=None):
    mod = _modalidade(modalidade)
    regioes = set(regioes or ())
    fora = [base_de(mod)]
    if mod == "CT":
        extra = (TASKS_DO_FAST.get(TORAX, ()) if TORAX in regioes
                 else _coracao_fora_do_torax(regioes, coracao_cm3, mod))
        for t in extra:
            if t and t not in fora:
                fora.append(t)
    fora = tuple(_filtrar(fora, mod, permitidas, catalogo))
    conferir_regra_a(FAST, fora, achados)
    return fora


PROTOCOLOS = (
    {"cod": "cranio", "rotulo": u"Crânio", "modalidade": "CT",
     "ajuda": (u"Glândulas e cavidades da cabeça (olhos, cristalinos, nervos "
               u"ópticos, conduto auditivo), as estruturas craniofaciais e o "
               u"encéfalo em TC (tronco e quiasma também no STUDY)."),
     "tasks": ("head_glands_cavities", "craniofacial_structures"),
     "motores": ("cranio_ct",)},
    {"cod": "cabeca_pescoco", "rotulo": u"Cabeça e Pescoço avançado",
     "modalidade": "CT",
     "ajuda": (u"As cinco bibliotecas acima da clavícula, os 20 níveis "
               u"cervicais (no FULL; no STUDY só a LNL_UNION, que não é OAR nem "
               u"CTV, e as parótidas do nível VIII) e o encéfalo em TC. "
               u"Órbita e dentes são tasks avulsas, cada uma no seu arquivo."),
     "tasks": ("head_glands_cavities", "headneck_muscles",
               "headneck_bones_vessels", "head_muscles",
               "craniofacial_structures"),
     "motores": ("hnlnl", "cranio_ct")},
    {"cod": "torax_mama", "rotulo": u"Tórax / Mama", "modalidade": "CT",
     "ajuda": (u"A cavidade do tronco, a glândula mamária e o derrame: com "
               u"elas saem o coração com o pericárdio, a parede torácica e "
               u"as mamas (Breast_L e Breast_R) como o TotalSegmentator as "
               u"entrega, suavizadas."),
     "tasks": ("trunk_cavities", "breasts", "pleural_pericard_effusion"),
     "motores": ()},
    {"cod": "sbrt", "rotulo": u"SBRT Pulmão / Fígado", "modalidade": "CT",
     "ajuda": (u"A cavidade do tronco, a glândula mamária, o derrame e os "
               u"segmentos hepáticos, estes num arquivo próprio."),
     "tasks": ("trunk_cavities", "breasts", "liver_segments",
               "pleural_pericard_effusion"),
     "motores": ()},
    {"cod": "abdome", "rotulo": u"Abdômen", "modalidade": "CT",
     "ajuda": (u"A cavidade abdominal, de onde saem a Bag_Bowel_OAR (no OAR; "
               u"a Bag_Bowel fica só no FULL) e o recorte da parede, os "
               u"segmentos hepáticos, num arquivo próprio, e os músculos do "
               u"tronco."),
     "tasks": ("trunk_cavities", "liver_segments", "abdominal_muscles"),
     "motores": ()},
    {"cod": "pelve", "rotulo": u"Pelve", "modalidade": "CT",
     "ajuda": (u"A cavidade abdominal, de onde saem a Bag_Bowel_OAR (no OAR; "
               u"a Bag_Bowel fica só no FULL) e o Anus_ai, recortado da "
               u"Bag_Bowel abaixo do osso pélvico. A prótese de quadril é "
               u"task avulsa, só quando pedida."),
     "tasks": ("trunk_cavities",),
     "motores": ()},
    {"cod": "coluna", "rotulo": u"Coluna", "modalidade": "CT",
     "ajuda": (u"O corpo vertebral, separado dos elementos posteriores, e os "
               u"discos intervertebrais, num arquivo próprio."),
     "tasks": ("vertebrae_body",),
     "motores": ()},
    {"cod": "coluna_rm", "rotulo": u"Coluna", "modalidade": "MR",
     "ajuda": (u"As vértebras C1 a L5 e os discos na RM, num arquivo "
               u"próprio — a total_mr não as nomeia."),
     "tasks": ("vertebrae_mr",),
     "motores": ()},
    {"cod": "abdome_rm", "rotulo": u"Abdômen", "modalidade": "MR",
     "ajuda": (u"Os oito segmentos de Couinaud na RM, num arquivo próprio."),
     "tasks": ("liver_segments_mr",),
     "motores": ()},
)

PROT_POR_COD = dict((p["cod"], p) for p in PROTOCOLOS)

DEPENDENCIAS_AO_LIGAR = {}


def ao_ligar(task):
    return tuple(DEPENDENCIAS_AO_LIGAR.get(str(task or ""), ()))


LIGADAS_DE_FABRICA_NO_PERSO = {"CT": ("trunk_cavities",
                                      "pleural_pericard_effusion")}
TASK_DO_PERICARDIO = "trunk_cavities"
FRASE_DO_PERICARDIO_DESLIGADO = (
    u"a chave da trunk_cavities foi DESLIGADA %s no PERSONALIZADO: o "
    u"Heart_ai desta serie sai SEM pericardio (so os rotulos cardiacos do "
    u"modelo) -- e o unico caso, numa TC, em que isso acontece por ato")
QUEM_DESLIGOU_A_MAO = u"a mao"


def quem_desligou_o_pericardio(chaves, modalidade="CT", protocolos=(),
                               protocolos_3d=()):
    if not pericardio_desligado_a_mao(chaves, modalidade):
        return u""
    try:
        mod = _modalidade(modalidade)
        rt = normalizar_protocolos(protocolos, mod)
        p3 = normalizar_protocolos_3d(protocolos_3d, mod)
    except Exception:
        return QUEM_DESLIGOU_A_MAO
    if rt and not any(TASK_DO_PERICARDIO in (PROT_POR_COD[c].get("tasks")
                                             or ()) for c in rt):
        return u"pelo protocolo %s" % u", ".join(
            u"«%s»" % PROT_POR_COD[c]["rotulo"] for c in rt)
    if p3 and not rt:
        return u"pelo protocolo das Reconstrucoes 3D %s" % u", ".join(
            u"«%s»" % PROT_3D_POR_COD[c]["rotulo"] for c in p3)
    return QUEM_DESLIGOU_A_MAO


def frase_do_pericardio_desligado(chaves, modalidade="CT", protocolos=(),
                                  protocolos_3d=()):
    quem = quem_desligou_o_pericardio(chaves, modalidade, protocolos,
                                      protocolos_3d)
    return (FRASE_DO_PERICARDIO_DESLIGADO % quem) if quem else u""


def ligadas_de_fabrica(modalidade="CT"):
    return tuple(LIGADAS_DE_FABRICA_NO_PERSO.get(_modalidade(modalidade), ()))


def pericardio_desligado_a_mao(chaves, modalidade="CT"):
    try:
        return bool(TASK_DO_PERICARDIO in ligadas_de_fabrica(modalidade)
                    and normalizar_chaves(chaves).get(TASK_DO_PERICARDIO)
                    == 0)
    except Exception:
        return False


def conferir_protocolos(catalogo=None, achados=()):
    import radai_tasks
    por_nome = dict((d["task"], d)
                    for d in (catalogo or radai_tasks.CATALOGO))
    ruins, vistos = [], set()
    for p in PROTOCOLOS:
        ts = tuple(p.get("tasks") or ())
        ms = tuple(p.get("motores") or ())
        if p["cod"] in vistos:
            ruins.append(u"`%s` aparece duas vezes" % p["cod"])
        vistos.add(p["cod"])
        if not ts and not ms:
            ruins.append(u"`%s` nao arrasta task nem motor" % p["cod"])
            continue
        fantasmas = [t for t in ts if t not in por_nome]
        if fantasmas:
            ruins.append(u"`%s` arrasta %s, fora do catalogo"
                         % (p["cod"], u", ".join(fantasmas)))
        outra = [t for t in ts if t in por_nome and _modalidade(
            por_nome[t].get("modalidade")) != _modalidade(p.get("modalidade"))]
        if outra:
            ruins.append(u"`%s` (%s) arrasta task de outra modalidade: %s"
                         % (p["cod"], p.get("modalidade"), u", ".join(outra)))
        mfant = [m for m in ms if m not in MOT_POR_COD]
        if mfant:
            ruins.append(u"`%s` liga o motor %s, que nao existe"
                         % (p["cod"], u", ".join(mfant)))
        if base_de(p.get("modalidade")) in ts:
            ruins.append(u"`%s` arrasta a base, que ja roda sempre" % p["cod"])
    if ruins:
        raise ValueError(u"protocolo inconsistente: %s" % u"; ".join(ruins))
    for p in PROTOCOLOS:
        conferir_regra_a(PROTOCOLO, p.get("tasks") or (), achados)
    for t, deps in DEPENDENCIAS_AO_LIGAR.items():
        conferir_regra_a(PROTOCOLO, deps, achados)


def protocolos_de(modalidade="CT"):
    mod = _modalidade(modalidade)
    fora = []
    for p in PROTOCOLOS:
        if not _cabe_na_modalidade(p, mod):
            continue
        fora.append({
            "cod": p["cod"], "rotulo": p["rotulo"],
            "ajuda": p.get("ajuda") or u"",
            "modalidade": _modalidade(p.get("modalidade")),
            "tasks": list(p.get("tasks") or ()),
            "motores": [m for m in (p.get("motores") or ())
                        if m in MOT_POR_COD
                        and _cabe_na_modalidade(MOT_POR_COD[m], mod)],
        })
    return tuple(fora)


def normalizar_protocolos(valor, modalidade=None):
    mod = _modalidade(modalidade) if modalidade else None
    pedidos = set(c.lower() for c in normalizar_escolhidas(valor))
    return tuple(p["cod"] for p in PROTOCOLOS
                 if p["cod"] in pedidos
                 and (mod is None or _cabe_na_modalidade(p, mod)))


def tasks_dos_protocolos(cods, modalidade="CT", permitidas=None, achados=(),
                         catalogo=None):
    mod = _modalidade(modalidade)
    fora = [base_de(mod)]
    arrastadas = []
    for c in normalizar_protocolos(cods, mod):
        for t in PROT_POR_COD[c].get("tasks") or ():
            if t not in arrastadas:
                arrastadas.append(t)
    conferir_regra_a(PROTOCOLO, arrastadas, achados)
    for t in arrastadas:
        if t not in fora:
            fora.append(t)
    return tuple(_filtrar(fora, mod, permitidas, catalogo))


def motores_dos_protocolos(cods, modalidade="CT"):
    mod = _modalidade(modalidade)
    pedidos = set()
    for c in normalizar_protocolos(cods, mod):
        pedidos.update(PROT_POR_COD[c].get("motores") or ())
    return tuple(m["cod"] for m in MOTORES
                 if m["cod"] in pedidos and _cabe_na_modalidade(m, mod))


def normalizar_chaves(valor):
    fora = {}
    if not isinstance(valor, dict):
        return fora
    for k, v in valor.items():
        t = str(k or "").strip()
        if not t:
            continue
        if isinstance(v, bool):
            fora[t] = 1 if v else 0
            continue
        s = str(v).strip().lower()
        if s in ("1", "true", "sim", "on"):
            fora[t] = 1
        elif s in ("0", "false", "nao", "não", "off"):
            fora[t] = 0
    return fora


def tasks_do_personalizado(protocolos=(), chaves=None, modalidade="CT",
                           permitidas=None, achados=(), catalogo=None):
    mod = _modalidade(modalidade)
    base = base_de(mod)
    ch = normalizar_chaves(chaves)
    arrastadas = []
    for c in normalizar_protocolos(protocolos, mod):
        for t in PROT_POR_COD[c].get("tasks") or ():
            if t not in arrastadas:
                arrastadas.append(t)
    de_fabrica = [t for t in ligadas_de_fabrica(mod) if t not in arrastadas]
    conferir_regra_a(PROTOCOLO, arrastadas + de_fabrica, achados)
    fora = [base]
    for t in arrastadas + de_fabrica:
        if ch.get(t, 1) and t not in fora:
            fora.append(t)
    for t, v in ch.items():
        if v and t != base and t not in fora:
            fora.append(t)
    dependentes = []
    for t, v in ch.items():
        if v and t not in arrastadas:
            for d in ao_ligar(t):
                if d not in ch and d not in fora and d not in dependentes:
                    dependentes.append(d)
    conferir_regra_a(PROTOCOLO, dependentes, achados)
    fora.extend(dependentes)
    fora = tuple(_filtrar(fora, mod, permitidas, catalogo))
    conferir_regra_a(MARCADO, fora, ())
    return fora


def normalizar_escolhidas(valor):
    if valor is None:
        return ()
    if isinstance(valor, (list, tuple, set, frozenset)):
        itens = list(valor)
    else:
        itens = re.split(r"[,;\s]+", str(valor))
    fora = []
    for t in itens:
        t = str(t or "").strip()
        if t and t not in fora:
            fora.append(t)
    return tuple(fora)


# GUARDA: os protocolos das Reconstrucoes 3D sao ato declarado de ESTUDO
# (origem `ESTUDO`). Rodam achado com o selo ACHADO, nao ligam comparacao de
# modelos e a saida e so o mapa de rotulos em `_RadAI` (`radai_rotulos`): nada
# vai ao TPS. `tasks` "todas" quer dizer todo o catalogo da modalidade.
TODAS = "todas"
SAIDA_ROTULOS = "rotulos"
PROTOCOLOS_3D = (
    {"cod": "anatomia_geral", "rotulo": u"Anatomia Geral", "modalidade": "CT",
     "ajuda": (u"Todas as tasks do catálogo, achados e níveis cervicais "
               u"inclusive, para ver cada estrutura nas Reconstruções 3D. "
               u"Sem comparação de modelos e sem RTSTRUCT: só o mapa de "
               u"rótulos do aplicativo."),
     "tasks": TODAS, "motores": ("hnlnl",)},
    {"cod": "anatomia_geral_rm", "rotulo": u"Anatomia Geral",
     "modalidade": "MR",
     "ajuda": (u"Todas as tasks de ressonância do catálogo, para ver cada "
               u"estrutura nas Reconstruções 3D. Sem RTSTRUCT: só o mapa de "
               u"rótulos do aplicativo."),
     "tasks": TODAS, "motores": ()},
    {"cod": "anatomia_toracica", "rotulo": u"Anatomia Torácica",
     "modalidade": "CT",
     "ajuda": (u"O tórax inteiro para a Anatomia Torácica: cavidades do "
               u"tronco e mediastino, mamas, músculos da parede, corpos "
               u"vertebrais e discos, os vasos e vias aéreas (novo e legado), "
               u"o derrame e os nódulos pulmonares. Sem parede torácica, sem "
               u"comparação de modelos e sem RTSTRUCT."),
     "tasks": ("trunk_cavities", "breasts", "abdominal_muscles",
               "vertebrae_body", "lung_vessels", "lung_vessels_LEGACY",
               "pleural_pericard_effusion", "lung_nodules"),
     "motores": ()},
)
PROT_3D_POR_COD = dict((p["cod"], p) for p in PROTOCOLOS_3D)

CATEGORIAS_DE_PROTOCOLO = (
    {"cod": "rt", "rotulo": u"PROTOCOLOS RT", "tabela": "PROTOCOLOS"},
    {"cod": "reconstrucoes_3d", "rotulo": u"PROTOCOLOS RECONSTRUÇÕES 3D",
     "tabela": "PROTOCOLOS_3D"},
)


def protocolos_3d_de(modalidade="CT"):
    mod = _modalidade(modalidade)
    return tuple(dict(p, tasks=list(_tasks_do_3d(p, mod)),
                      motores=list(p.get("motores") or ()),
                      saida=SAIDA_ROTULOS)
                 for p in PROTOCOLOS_3D if _cabe_na_modalidade(p, mod))


def _tasks_do_3d(p, mod, catalogo=None):
    if p.get("tasks") != TODAS:
        return tuple(p.get("tasks") or ())
    import radai_tasks
    base = base_de(mod)
    fora = []
    for d in (catalogo or radai_tasks.CATALOGO):
        t = d.get("task")
        if not t or t == base or t in fora:
            continue
        try:
            if radai_tasks.familia_da_task(t) == radai_tasks.familia_da_task(
                    base):
                continue
        except Exception:
            pass
        if _modalidade(d.get("modalidade")) != mod:
            continue
        fora.append(t)
    return tuple(fora)


def normalizar_protocolos_3d(valor, modalidade=None):
    mod = _modalidade(modalidade) if modalidade else None
    pedidos = set(c.lower() for c in normalizar_escolhidas(valor))
    return tuple(p["cod"] for p in PROTOCOLOS_3D
                 if p["cod"] in pedidos
                 and (mod is None or _cabe_na_modalidade(p, mod)))


def tasks_do_estudo_3d(cods, modalidade="CT", permitidas=None, achados=(),
                       catalogo=None):
    mod = _modalidade(modalidade)
    fora = [base_de(mod)]
    for c in normalizar_protocolos_3d(cods, mod):
        for t in _tasks_do_3d(PROT_3D_POR_COD[c], mod, catalogo):
            if t not in fora:
                fora.append(t)
    fora = tuple(_filtrar(fora, mod, permitidas, catalogo))
    conferir_regra_a(ESTUDO, fora, achados)
    return fora


def motores_do_estudo_3d(cods, modalidade="CT"):
    mod = _modalidade(modalidade)
    pedidos = set()
    for c in normalizar_protocolos_3d(cods, mod):
        pedidos.update(PROT_3D_POR_COD[c].get("motores") or ())
    return tuple(m["cod"] for m in MOTORES
                 if m["cod"] in pedidos and _cabe_na_modalidade(m, mod))
