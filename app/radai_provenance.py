# -*- coding: utf-8 -*-
import json
import os
import unicodedata

ARQUIVO = "procedencia.json"

MOTORES = {
    "ts": {
        "nome": u"TotalSegmentator",
        "sufixo": "_ai",
        "licenca": u"Apache-2.0",
    },
    "cads": {
        "nome": u"CADS (variante open)",
        "sufixo": "_cds",
        "licenca": u"CC BY-SA 4.0",
    },
    "vista": {
        "nome": u"NV-Segment-CT (NVIDIA)",
        "sufixo": "_nv",
        "licenca": u"NVIDIA Open Model License — uso comercial permitido",
    },
    "derivada": {
        "nome": u"derivada por marco anatômico",
        "sufixo": "_ai",
        "licenca": u"nossa",
    },
}

DERIVADA_USA_O_CURSOR = True


CORACAO = "heart"
AORTA = "aorta"
PELE_E_PAREDE = ("Skin", "ChestWall_L", "ChestWall_R")


AVISOS = {
    "conjuntos": u"Não consegui ler os conjuntos de RTSTRUCT: o desconto do "
                 u"entregue e a lista do que se suaviza ficaram sem resposta, "
                 u"e não como «não».",
    "refino": u"O refino por densidade não respondeu para algumas estruturas, "
              u"e a coluna do entregue pode estar incompleta nelas.",
    "nome_tps": u"O nome no TPS não respondeu para algumas estruturas.",
    "cursor_processo": u"O vigia não informou o valor em uso: o valor "
                       u"mostrado veio do arquivo ou do padrão de fábrica.",
    "arquivo": u"Não consegui ler o arquivo de configuração.",
    "limites": u"Não consegui ler o intervalo que o vigia aceita para a "
               u"suavização.",
    "cursor_limite": u"O valor lido está fora do intervalo que o vigia aceita, "
                     u"e o vigia aplica o limite: a tela mostra o valor "
                     u"aplicado.",
    "tabela": u"O arquivo da tabela assinada existe e não foi lido: o motor "
              u"também não o lê, e vale o padrão de fábrica.",
    "derivadas": u"Um plano de derivação do motor tem uma forma que o espelho "
                 u"não lê: a estrutura dele pode aparecer como vinda do "
                 u"modelo, ou como só de outro motor.",
    "bibliotecas": u"Não consegui ler o catálogo das bibliotecas do "
                   u"TotalSegmentator: a tabela delas ficou vazia, e não "
                   u"«sem nenhuma».",
}


def aviso(parte, detalhe=u""):
    return {"parte": parte, "texto": AVISOS.get(parte, parte),
            "detalhe": u"%s" % (detalhe or u"")}


def _erro(ex):
    return u"%s: %s" % (type(ex).__name__, str(ex)[:160])


def caminho(base=None):
    if base:
        return os.path.join(base, ARQUIVO)
    try:
        import radai_archive
        return os.path.join(str(radai_archive.raiz()), ARQUIVO)
    except Exception:
        return ARQUIVO


def _ler(base=None):
    p = caminho(base)
    if not os.path.exists(p):
        return {}, None
    try:
        with open(p, encoding="utf-8-sig") as f:
            d = json.load(f)
        linhas = d.get("linhas") if isinstance(d, dict) else d
        return dict((str(x["estrutura"]), x) for x in (linhas or [])
                    if isinstance(x, dict) and x.get("estrutura")), None
    except Exception as ex:
        return {}, _erro(ex)


def ler(base=None):
    try:
        return _ler(base)[0]
    except Exception:
        return {}


_LIMITES_CACHE = {}


def limites_do_cursor(fonte=None, chave="SUAVIZAR_MM"):
    import ast
    if fonte is None:
        p = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "radai_watcher.py")
        chave_cache = (p, os.path.getmtime(p), chave)
        if chave_cache in _LIMITES_CACHE:
            return _LIMITES_CACHE[chave_cache]
        with open(p, encoding="utf-8-sig") as f:
            fonte = f.read()
    else:
        chave_cache = None
    achados = set()
    for no in ast.walk(ast.parse(fonte)):
        if not (isinstance(no, ast.Call) and getattr(no.func, "id", None) == "_num"
                and len(no.args) >= 5):
            continue
        a = no.args
        if not (isinstance(a[1], ast.Constant) and a[1].value == chave):
            continue
        try:
            lo, hi = float(ast.literal_eval(a[3])), float(ast.literal_eval(a[4]))
        except Exception as ex:
            raise ValueError(u"a chamada de `_num` para %s não tem limites "
                             u"literais (%s)" % (chave, _erro(ex)))
        achados.add((lo, hi))
    if len(achados) != 1:
        raise ValueError(u"%d chamada(s) de `_num` para %s no vigia"
                         % (len(achados), chave))
    r = achados.pop()
    if chave_cache is not None:
        _LIMITES_CACHE[chave_cache] = r
    return r


def _numero(v):
    if v is None:
        return None
    try:
        return float(str(v).split("#")[0].strip().replace(",", "."))
    except (TypeError, ValueError):
        return None


def _mm(v):
    if v is None:
        return u"?"
    r = round(float(v), 2)
    return (u"%.2f" % r).rstrip(u"0").rstrip(u".") if r != int(r) \
        else u"%.1f" % r


def ascii_(texto):
    s = u"%s" % (texto if texto is not None else u"")
    for a, b in ((u"—", u"-"), (u"–", u"-"), (u"×", u"x"), (u"÷", u"/"),
                 (u"≥", u">="), (u"«", u'"'), (u"»", u'"'), (u"→", u"->")):
        s = s.replace(a, b)
    s = unicodedata.normalize("NFKD", s)
    return s.encode("ascii", "ignore").decode("ascii")


def _rotulos_por_valor(E):
    fora = {}
    for k in sorted(dir(E)):
        if not k.startswith("_S_"):
            continue
        v = getattr(E, k, None)
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            continue
        fora.setdefault(float(v), []).append(k[3:].lower())
    return fora


def _derivadas(E, falhas=None):
    fora = {}
    for mae, d in sorted((getattr(E, "DERIVADAS", None) or {}).items()):
        for p in (d or {}).get("planos") or ():
            try:
                marcos, extremo, nome = p[0], p[1], p[3]
            except (IndexError, TypeError) as ex:
                if falhas is not None:
                    falhas.append((str(mae), _erro(ex)))
                continue
            fora[str(nome)] = {
                "de": str(mae),
                "marcos": ([str(m) for m in marcos]
                           if isinstance(marcos, (list, tuple)) else [str(marcos)]),
                "extremo": str(extremo),
                "exige": [str(x) for x in ((d or {}).get("exige") or ())]}
    return fora


def _escolhas(E, tabela):
    esc = {}
    for nome, par in (getattr(E, "MELHOR_FONTE", None) or {}).items():
        motor = par[0] if isinstance(par, (list, tuple)) else par
        porque = par[1] if isinstance(par, (list, tuple)) and len(par) > 1 else u""
        esc[str(nome)] = {"motor": str(motor), "porque": u"%s" % porque,
                          "assinada": None}
    assinadas = {}
    for nome, linha in (tabela or {}).items():
        linha = linha or {}
        if not linha.get("assinado_por"):
            continue
        m = str(linha.get("modelo") or "")
        info = {"modelo": m or "ts",
                "quem": u"%s" % (linha.get("assinado_por") or u""),
                "quando": u"%s" % (linha.get("assinado_em") or u""),
                "motivo": u"%s" % (linha.get("motivo") or u"")}
        assinadas[str(nome)] = info
        if m and m != "ts":
            esc[str(nome)] = {"motor": m,
                              "porque": info["motivo"] or u"assinada",
                              "assinada": info}
        else:
            esc.pop(str(nome), None)
    return esc, assinadas


def _motor(chave):
    m = MOTORES.get(chave) or {}
    return {"chave": chave, "nome": m.get("nome") or chave,
            "licenca": m.get("licenca") or u"", "restrito": bool(m.get("restrito"))}


def _nome_da_funcao(f):
    try:
        return str(getattr(f, "__name__", None) or f)
    except Exception:
        return u"?"


def _registro_de_construcoes(E):
    reg = getattr(E, "CONSTRUCOES", None)
    if not isinstance(reg, (list, tuple)):
        return None
    ordem = [v for e, v in (getattr(E, "ORDEM_DO_FULL", None) or ())
             if e == "construcoes"]
    fora = []
    for momento in ordem + [None]:
        for c in reg:
            m = c.get("momento")
            if (momento is None and m in ordem) or (
                    momento is not None and m != momento):
                continue
            saidas = {}
            for nome, s in sorted((c.get("saidas") or {}).items()):
                s = s or {}
                saidas[str(nome)] = {
                    "descricao": u"%s" % (s.get("descricao") or u""),
                    "contem": [str(x) for x in (s.get("contem") or ())],
                    "recortar_por": [str(x) for x in
                                     (s.get("recortar_por") or ())],
                    "suavizar_mm": (None if s.get("suavizar_mm") is None
                                    else float(s["suavizar_mm"]))}
            fora.append({"cod": str(c.get("cod", "?")),
                         "funcao": _nome_da_funcao(c.get("funcao")),
                         "momento": (str(m) if m in ordem else
                                     u"%s (fora da ordem: nunca roda)" % m),
                         "so_tc": bool(c.get("exige_hu")),
                         "exige": [str(x) for x in (c.get("exige") or ())],
                         "saidas": saidas})
    return fora


def _construcoes(E, compostos):
    reg = _registro_de_construcoes(E)
    coracao = None
    if callable(getattr(E, "coracao_de_radioterapia", None)):
        vasos = []
        for v in (getattr(E, "VASOS_DO_CORACAO", None) or ()):
            nome = v[0] if isinstance(v, (list, tuple)) else v
            vasos.append(str(nome))
        absorvidos = set(vasos) | {AORTA}
        menos = getattr(E, "COMPOSTOS_MENOS", None)
        if isinstance(menos, dict):
            cedem = sorted(c for c, cs in menos.items()
                           if CORACAO in (cs or ()) and c in compostos)
        else:
            cedem = sorted(c for c, ps in compostos.items()
                           if absorvidos & set(str(p) for p in ps))
        funcao = "coracao_de_radioterapia"
        com_peri = None
        if reg is not None:
            c_cor = [c for c in reg if CORACAO in c["saidas"]]
            if c_cor:
                funcao = c_cor[0]["funcao"]
                antes = reg[:reg.index(c_cor[0])]
                com_peri = any("pericardium" in c["saidas"] for c in antes)
        coracao = {"funcao": funcao, "estrutura": CORACAO,
                   "aorta": AORTA, "vasos": vasos, "cedem": cedem,
                   "com_pericardio": com_peri,
                   "fechamento_mm": _numero(getattr(E, "FECHAMENTO_PERICARDIO_MM",
                                                    None))}
    pele = None
    if reg is not None:
        c_pele = [c for c in reg if "Skin" in c["saidas"]]
        if c_pele:
            pele = {"funcao": c_pele[0]["funcao"],
                    "nomes": sorted(c_pele[0]["saidas"])}
    elif callable(getattr(E, "acrescentar_pele_e_parede", None)):
        nomes = getattr(E, "PELE_E_PAREDE", None) or PELE_E_PAREDE
        pele = {"funcao": "acrescentar_pele_e_parede",
                "nomes": [str(n) for n in nomes]}
    partes_de = {}
    for c, ps in sorted(compostos.items()):
        for p in ps:
            partes_de.setdefault(str(p), []).append(str(c))
    return coracao, pele, partes_de


def espelho(suavizar_mm=None, fabrica=None, no_arquivo=None, engine=None,
            base=None, tabela=None, origem_do_cursor=None, avisos=None,
            limites=None):
    E = engine
    if E is None:
        import engine as E
    av = list(avisos or [])
    if tabela is None:
        tabela, erro_tab = _ler(base)
        if erro_tab:
            av.append(aviso("tabela", erro_tab))
    ref = float(getattr(E, "SUAVIZACAO_PADRAO_MM", 1.5))
    cursor = _numero(suavizar_mm)
    cursor_lido = cursor is not None
    origem_c = origem_do_cursor or ("processo" if cursor_lido else None)
    if cursor is None:
        cursor = _numero(fabrica)
        if cursor is not None:
            origem_c = "fabrica"
    if cursor is None:
        cursor = ref
        origem_c = "referencia"
    lim = limites
    if lim is None:
        try:
            lim = limites_do_cursor()
        except Exception as ex:
            lim = None
            av.append(aviso("limites", _erro(ex)))
    cursor_lido_mm = cursor
    arquivo_mm = _numero(no_arquivo)
    arquivo_aplicado = arquivo_mm
    if lim is not None:
        lo, hi = float(lim[0]), float(lim[1])
        aplicado = min(max(cursor, lo), hi)
        if aplicado != cursor:
            av.append(aviso("cursor_limite", u"%s -> %s (%s a %s)"
                            % (_mm(cursor), _mm(aplicado), _mm(lo), _mm(hi))))
            cursor = aplicado
        if arquivo_mm is not None:
            arquivo_aplicado = min(max(arquivo_mm, lo), hi)
            if arquivo_aplicado != arquivo_mm and arquivo_mm != cursor_lido_mm:
                av.append(aviso("cursor_limite", u"arquivo %s -> %s (%s a %s)"
                                % (_mm(arquivo_mm), _mm(arquivo_aplicado),
                                   _mm(lo), _mm(hi))))
    tab_suav = dict(getattr(E, "SUAVIZACAO", None) or {})
    suav_de = E.suavizacao_de

    rot = _rotulos_por_valor(E)
    por_valor = {}
    for nome, v in tab_suav.items():
        por_valor.setdefault(float(v), []).append(str(nome))
    grupos = []
    for v in sorted(por_valor):
        nomes = sorted(por_valor[v])
        grupos.append({"tabela_mm": v,
                       "efetivo_mm": float(suav_de(nomes[0], cursor)),
                       "rotulos": rot.get(v, []),
                       "n": len(nomes), "exemplos": nomes[:4]})

    falhas_der = []
    derivadas = _derivadas(E, falhas_der)
    if falhas_der:
        av.append(aviso("derivadas", u"%d plano(s), o primeiro de %s -- %s"
                        % (len(falhas_der), falhas_der[0][0], falhas_der[0][1])))
    grupo_derivacao = set(getattr(E, "DERIVADAS", None) or {}) | set(derivadas)
    esc, assinadas = _escolhas(E, tabela)
    ambos = dict(getattr(E, "AMBOS", None) or {})
    ts_map = dict(getattr(E, "TS_MAP", None) or {})
    compostos = dict(getattr(E, "COMPOSTOS", None) or {})
    descontadas = dict(getattr(E, "DESCONTADAS_DE", None) or {})
    contidas = dict(getattr(E, "CONTIDAS_EM", None) or {})
    recortes = dict(getattr(E, "RECORTE_DE_OAR", None) or {})
    margens = dict(getattr(E, "MARGEM_OAR_MM", None) or {})
    refino_de = getattr(E, "_familia_para_refino", None)
    grupo_disjunto = {}
    for g, membros in sorted((getattr(E, "GRUPOS_DISJUNTOS", None) or {}).items()):
        for n in membros:
            grupo_disjunto.setdefault(str(n), g)
    no_oar = None
    try:
        import radai_sets
        desconta_no_entregue = bool(radai_sets.desconto_do_entregue())
        conjuntos = [{"cod": c.get("cod"), "nome": c.get("nome"),
                      "suavizado": bool(c.get("suavizado")),
                      "cru": bool(c.get("cru")),
                      "entregue": bool(c.get("entregue"))}
                     for c in radai_sets.CONJUNTOS]
        no_oar = set(str(x) for x in
                     (getattr(radai_sets, "PERMITIDOS_NO_OAR", None) or ()))
    except Exception as ex:
        desconta_no_entregue, conjuntos = None, None
        av.append(aviso("conjuntos", _erro(ex)))

    coracao, pele, partes_de = _construcoes(E, compostos)
    pele_nomes = list((pele or {}).get("nomes") or [])
    cedem = set((coracao or {}).get("cedem") or ())
    vasos_cor = set((coracao or {}).get("vasos") or ())
    reg = _registro_de_construcoes(E)
    por_saida = {}
    for c in (reg or ()):
        for nome in c["saidas"]:
            por_saida.setdefault(nome, c)
    chave_modelo = None
    if reg is not None and CORACAO in por_saida and CORACAO in ts_map:
        try:
            import radai_names
            chave_modelo = radai_names.CHAVE_DO_CORACAO_DO_MODELO
        except Exception:
            chave_modelo = "heart_model"
    recorte_de = {}
    if reg is not None:
        for orgao, destino in sorted(
                (getattr(E, "NOME_DO_RECORTE", None) or {}).items()):
            if orgao in recortes and destino in por_saida:
                recorte_de[str(destino)] = str(orgao)
        recortes = dict((d, recortes[o]) for d, o in recorte_de.items())
    recortado_em = dict((o, d) for d, o in recorte_de.items())

    nomes = (set(ts_map) | set(compostos) | set(derivadas) | set(esc)
             | set(ambos) | set(assinadas) | set(pele_nomes)
             | set(por_saida) | ({chave_modelo} if chave_modelo else set()))
    linhas = []
    conta = {"modelo": 0, "composta": 0, "derivada": 0, "outro_motor": 0,
             "construida": 0, "nenhum": 0}
    falhas_refino, falhas_tps = [], []
    for n in sorted(nomes):
        if n in derivadas:
            base_ = dict({"tipo": "derivada"}, **derivadas[n])
        elif n in por_saida:
            c = por_saida[n]
            base_ = {"tipo": "construida", "funcao": c["funcao"],
                     "cod": c["cod"], "so_tc": c["so_tc"]}
            if n in ts_map:
                base_["a_partir_de"] = sorted(str(t) for t in ts_map[n])
        elif chave_modelo and n == chave_modelo:
            base_ = {"tipo": "modelo", "motor": _motor("ts"),
                     "tarefas": sorted(str(t) for t in ts_map[CORACAO])}
        elif n in compostos:
            base_ = {"tipo": "composta", "partes": [str(p) for p in compostos[n]]}
            if n in ts_map:
                base_["direto_do_modelo_em"] = sorted(str(t) for t in ts_map[n])
        elif n in ts_map:
            base_ = {"tipo": "modelo", "motor": _motor("ts"),
                     "tarefas": sorted(str(t) for t in ts_map[n])}
        elif n in pele_nomes:
            base_ = {"tipo": "construida", "funcao": pele["funcao"],
                     "so_tc": True}
        else:
            base_ = {"tipo": "nenhum"}
        origem = dict(base_)
        if n in esc:
            origem = {"tipo": "outro_motor", "motor": _motor(esc[n]["motor"]),
                      "porque": esc[n]["porque"], "assinada": esc[n]["assinada"],
                      "sem_ele": base_}
        conta[origem["tipo"]] += 1
        if n in ambos:
            par = ambos[n]
            motor_alt = par[0] if isinstance(par, (list, tuple)) else par
            origem["comparacao_com"] = _motor(str(motor_alt))
        tab = tab_suav.get(n)
        efetivo = float(suav_de(n, cursor))
        na_derivacao = n in grupo_derivacao
        if na_derivacao and DERIVADA_USA_O_CURSOR:
            efetivo_der = float(cursor)
        else:
            efetivo_der = efetivo
        entregue = {}
        if desconta_no_entregue is not False:
            perde = sorted(d for d, f in descontadas.items() if f == n)
            if perde:
                entregue["perde_o_que_ocupa"] = perde
            if n in descontadas:
                entregue["descontada_de"] = str(descontadas[n])
            if desconta_no_entregue is None and (perde or n in descontadas):
                entregue["desconto_incerto"] = True
        if n in contidas:
            entregue["contida_em"] = str(contidas[n])
        if n in recortes:
            marcos, extremo, off = recortes[n]
            entregue["recorte"] = {"marcos": [str(m) for m in marcos],
                                   "extremo": str(extremo), "off_mm": float(off or 0)}
            if n in recorte_de:
                entregue["recorte"]["de"] = recorte_de[n]
        if n in recortado_em:
            entregue["recortado_em"] = recortado_em[n]
        if n in margens and float(margens[n] or 0):
            entregue["margem_mm"] = float(margens[n])
            if n == AORTA and getattr(
                    E, "RECORTE_DA_AORTA_DEPOIS_DA_MARGEM", None):
                entregue["recortada_depois_da_margem"] = [
                    str(x) for x in E.RECORTE_DA_AORTA_DEPOIS_DA_MARGEM]
        if refino_de is not None:
            try:
                lim_hu = refino_de(n)
            except Exception as ex:
                lim_hu = None
                falhas_refino.append((n, _erro(ex)))
            if lim_hu:
                entregue["refino_hu"] = float(lim_hu)
        if no_oar is not None:
            entregue["no_oar"] = n in no_oar
        if n in por_saida:
            c = por_saida[n]
            entregue["construida"] = {"funcao": c["funcao"], "cod": c["cod"],
                                      "so_tc": c["so_tc"],
                                      "momento": c["momento"]}
        elif n in pele_nomes:
            entregue["construida"] = {"funcao": pele["funcao"], "so_tc": True}
        if coracao and n == coracao["estrutura"]:
            entregue["reconstruida"] = {
                "funcao": coracao["funcao"], "aorta": coracao["aorta"],
                "vasos": list(coracao["vasos"]),
                "com_pericardio": coracao.get("com_pericardio"),
                "fechamento_mm": coracao["fechamento_mm"]}
        if coracao and n == coracao["aorta"]:
            if reg is not None:
                entregue["descendente_em"] = sorted(
                    c for c in cedem if AORTA in compostos.get(c, ()))
            else:
                entregue["so_a_descendente"] = True
        if n in vasos_cor:
            entregue["absorvida_pelo_coracao"] = True
        if n in cedem:
            entregue["cede_ao_coracao"] = True
        if n in partes_de:
            entregue["sai_dentro_de"] = list(partes_de[n])
        if n in compostos:
            entregue["no_lugar_das_partes"] = True
        try:
            nome_tps = E.nome_clinico(n)
        except Exception as ex:
            nome_tps = u"?"
            falhas_tps.append((n, _erro(ex)))
        linhas.append({
            "estrutura": n, "nome_tps": nome_tps, "origem": origem,
            "suavizacao": {"tabela_mm": (None if tab is None else float(tab)),
                           "efetivo_mm": efetivo_der,
                           "tabela_x_cursor_mm": efetivo,
                           "na_derivacao": na_derivacao,
                           "grupo_disjunto": grupo_disjunto.get(n, u"")},
            "entregue": entregue})

    for parte, falhas in (("refino", falhas_refino), ("nome_tps", falhas_tps)):
        if falhas:
            av.append(aviso(parte, u"%d estrutura(s), a primeira %s -- %s"
                            % (len(falhas), falhas[0][0], falhas[0][1])))

    sem_tabela = [x["estrutura"] for x in linhas
                  if x["suavizacao"]["tabela_mm"] is None]
    motores_usados = sorted(set(
        x["origem"]["motor"]["chave"] for x in linhas
        if isinstance(x["origem"].get("motor"), dict)))
    return {
        "avisos": av,
        "suavizacao": {
            "cursor_mm": float(cursor), "cursor_lido": cursor_lido,
            "origem": origem_c, "lido_mm": float(cursor_lido_mm),
            "limites": (None if lim is None else [float(lim[0]), float(lim[1])]),
            "fabrica_mm": _numero(fabrica), "no_arquivo_mm": arquivo_mm,
            "no_arquivo_aplicado_mm": arquivo_aplicado,
            "referencia_mm": ref, "grupos": grupos,
            "sem_tabela": {"n": len(sem_tabela), "efetivo_mm": float(cursor),
                           "exemplos": sem_tabela[:4]},
            "fina_mm": _numero(getattr(E, "ESPESSURA_FINA_MM", None)),
            "divisor_do_raio": _numero(getattr(E, "_DIVISOR_DO_RAIO", None)),
            "derivacao": {"usa_o_cursor": bool(DERIVADA_USA_O_CURSOR),
                          "membros": sorted(grupo_derivacao)},
            "conjuntos": conjuntos},
        "origem": {"conta": conta, "assinadas": assinadas,
                   "arquivo_assinado": ARQUIVO,
                   "arquivo_assinado_caminho": caminho(base),
                   "melhor_fonte": sorted(getattr(E, "MELHOR_FONTE", None) or {}),
                   "ambos": sorted(ambos),
                   "motores": dict((k, _motor(k)) for k in motores_usados)},
        "entregue": {
            "desconta": desconta_no_entregue,
            "descontadas": sorted(descontadas.items()),
            "contidas": sorted(contidas.items()),
            "recortes": sorted((k, [str(m) for m in v[0]], str(v[1]))
                               for k, v in recortes.items()),
            "recorte_de": (dict(recorte_de) if reg is not None else None),
            "margens": sorted((k, float(v)) for k, v in margens.items()
                              if float(v or 0)),
            "recorte_da_aorta": [str(x) for x in (getattr(
                E, "RECORTE_DA_AORTA_DEPOIS_DA_MARGEM", None) or ())],
            "refino": sorted((k, float(v)) for k, v in
                             (getattr(E, "REFINO_POR_HU", None) or {}).items()
                             if v),
            "pele_e_parede": pele,
            "coracao": coracao,
            "compostos": sorted((k, [str(p) for p in v])
                                for k, v in compostos.items()),
            "construcoes": reg,
            "ordem": ([list(p) for p in (getattr(E, "ORDEM_DO_FULL", None)
                                         or ())] or None),
            "compostos_menos": (sorted(
                (str(k), [str(x) for x in (v or ())]) for k, v in
                (getattr(E, "COMPOSTOS_MENOS", None) or {}).items())
                if isinstance(getattr(E, "COMPOSTOS_MENOS", None), dict)
                else None),
            "no_oar": (None if no_oar is None else sorted(no_oar))},
        "estruturas": linhas,
        "total": len(linhas),
    }


def _rotulo_do_grupo(g):
    if g["rotulos"]:
        return u"/".join(g["rotulos"])
    if not g["tabela_mm"]:
        return u"sem suavizacao (%s)" % u", ".join(g["exemplos"][:2] + [u"..."])
    return u"tabela %s" % _mm(g["tabela_mm"])


def linhas_para_arranque(suavizar_mm, fabrica=None, engine=None, base=None):
    try:
        e = espelho(suavizar_mm, fabrica=fabrica, engine=engine, base=base)
    except Exception as ex:
        return [ascii_(u"procedencia: espelho nao montado (%s: %s)"
                       % (type(ex).__name__, str(ex)[:120]))]
    s = e["suavizacao"]
    L = []
    for a in e.get("avisos") or ():
        L.append(u"procedencia: AVISO -- %s%s"
                 % (a["texto"], (u" (%s)" % a["detalhe"]) if a["detalhe"] else u""))
    grupos = u"; ".join(u"%s %s mm" % (_rotulo_do_grupo(g), _mm(g["efetivo_mm"]))
                        for g in s["grupos"])
    rot_origem = {"processo": u"", "arquivo": u" (do arquivo)",
                  "fabrica": u" (de fabrica)", "referencia": u" (nao lido)"}
    L.append(u"suavizacao: cursor %s%s (fabrica %s; tabela x cursor/%s) | %s | "
             u"%d sem entrada na tabela: %s mm"
             % (_mm(s["cursor_mm"]), rot_origem.get(s.get("origem"), u""),
                _mm(s["fabrica_mm"]) if s["fabrica_mm"] is not None else u"?",
                _mm(s["referencia_mm"]), grupos, s["sem_tabela"]["n"],
                _mm(s["sem_tabela"]["efetivo_mm"])))
    cj = s["conjuntos"]
    if cj is None:
        suav_t, cru_t = u"?", u"?"
    else:
        suav_t = u", ".join(c["nome"] for c in cj if c["suavizado"]) or u"-"
        cru_t = u", ".join(c["nome"] for c in cj if not c["suavizado"]) or u"-"
    L.append(u"suavizacao na serie: estrutura cujo maior raio inscrito e menor "
             u"que %s mm nao e suavizada; nas demais o sigma nao passa de "
             u"raio inscrito/%s | suaviza: %s | sai sem suavizar: %s"
             % (_mm(s["fina_mm"]), _mm(s["divisor_do_raio"]), suav_t, cru_t))
    d = s["derivacao"]
    if d["usa_o_cursor"] and d["membros"]:
        tab = [x for x in e["estruturas"] if x["estrutura"] in d["membros"]]
        L.append(u"suavizacao: derivacao (%s) suavizada junta com o cursor "
                 u"inteiro, %s mm -- a tabela daria %s"
                 % (u", ".join(d["membros"]), _mm(s["cursor_mm"]),
                    u", ".join(u"%s %s mm" % (x["estrutura"],
                                               _mm(x["suavizacao"]["tabela_x_cursor_mm"]))
                               for x in tab)))
    o = e["origem"]
    c = o["conta"]
    L.append(u"procedencia: %d estruturas | modelo %d, composta %d, derivada %d, "
             u"construida %d, de outro motor %d | MELHOR_FONTE: %s | "
             u"comparacao aberta: %s"
             % (e["total"], c["modelo"], c["composta"], c["derivada"],
                c.get("construida", 0), c["outro_motor"],
                u", ".join(o["melhor_fonte"]) or u"vazia",
                u", ".join(o["ambos"]) or u"nenhuma"))
    if o["assinadas"]:
        L.append(u"procedencia: ATENCAO -- %s tem %d linha(s) assinada(s), "
                 u"e o motor as aplica em toda serie: %s | para voltar ao "
                 u"padrao de fabrica, apague ou renomeie este arquivo: o motor "
                 u"o rele a cada serie"
                 % (o.get("arquivo_assinado_caminho") or o["arquivo_assinado"],
                    len(o["assinadas"]),
                    u"; ".join(u"%s -> %s (%s)" % (k, v["modelo"], v["quando"] or u"?")
                               for k, v in sorted(o["assinadas"].items())[:8])))
    else:
        L.append(u"procedencia: nenhuma linha assinada no acervo -- vale o padrao "
                 u"de fabrica")
    t = e["entregue"]
    partes = []
    _no = u"FULL" if t.get("construcoes") is not None else u"entregue"
    if t["desconta"] is not False and t["descontadas"]:
        partes.append(u"desconto (%s%s) " % (_no, u", ?" if t["desconta"] is None
                                              else u"") + u", ".join(
            u"%s-%s" % (f, d_) for d_, f in t["descontadas"]))
    if t["contidas"]:
        partes.append(u"contencao (todos menos o cru) " + u", ".join(
            u"%s em %s" % (d_, f) for d_, f in t["contidas"]))
    if t["recortes"]:
        _de = t.get("recorte_de") or {}
        partes.append(u"recorte (%s) " % (u"FULL, como Femur_OAR ao lado do "
                                          u"inteiro" if _no == u"FULL"
                                          else _no) + u", ".join(
            u"%s%s no %s de %s" % (k, (u" (de %s, que fica inteiro)" % _de[k])
                                   if k in _de else u"", x, u"|".join(m))
            for k, m, x in t["recortes"]))
    if t["margens"]:
        _ao = t.get("recorte_da_aorta") or ()
        partes.append(u"margem (%s) " % _no + u", ".join(
            u"%s +%s mm" % (k, _mm(v)) for k, v in t["margens"])
            + ((u"; depois dela a aorta sai recortada de %s"
                % u", ".join(_ao)) if _ao else u""))
    if t["refino"]:
        partes.append(u"refino por HU (%s, so TC) " % _no + u", ".join(
            u"%s>=%d" % (k, int(v)) for k, v in t["refino"]))
    L.append(u"alem da suavizacao: " + (u" | ".join(partes) or u"nada"))
    reg = t.get("construcoes")
    cor = t.get("coracao")
    if reg is not None:
        cons = []
        for c in reg:
            cons.append(u"%s (%s%s)" % (c["cod"], u", ".join(sorted(c["saidas"])),
                                        u"; so TC" if c["so_tc"] else u""))
        L.append(u"construcoes do FULL, na ordem: " + (u" -> ".join(cons)
                                                        or u"nenhuma"))
        if cor:
            vs = u", ".join(cor["vasos"]) or u"-"
            L.append(u"coracao: %s = mesclagem do coracao do modelo com a "
                     u"ascendente de %s e %s no intervalo dele (ja com a "
                     u"margem), saco fechado em %s mm%s; %s fica INTEIRA no "
                     u"FULL, e a descendente dentro de %s (B3); %s = soma dos "
                     u"vasos prontos menos o Heart_ai"
                     % (cor["estrutura"], cor["aorta"], vs,
                        _mm(cor["fechamento_mm"]),
                        (u", com o pericardio corrigido quando a "
                         u"trunk_cavities rodou") if cor.get("com_pericardio")
                        else u"", cor["aorta"],
                        u", ".join(k for k, v in (t.get("compostos") or ())
                                   if cor["aorta"] in v
                                   and k in cor["cedem"]) or u"-",
                        u", ".join(cor["cedem"]) or u"-"))
        oar = t.get("no_oar")
        L.append(u"OAR: %s estrutura(s) permitida(s) "
                 u"(radai_sets.PERMITIDOS_NO_OAR), gravadas das mascaras "
                 u"finais do FULL antes dele, iguais as do FULL; no FULL saem "
                 u"as partes E o composto, no OAR so o composto"
                 % (u"?" if oar is None else len(oar)))
        return [ascii_(x) for x in L]
    cons = []
    if t.get("pele_e_parede"):
        cons.append(u"%s (entregue, so TC)" % u", ".join(t["pele_e_parede"]["nomes"]))
    if cor:
        vs = u", ".join(cor["vasos"]) or u"-"
        cons.append(u"%s reconstruido (entregue): absorve a ascendente de %s e %s "
                    u"no intervalo dele, saco fechado em %s mm; %s sai so a "
                    u"descendente; %s nao saem separados; cedem ao coracao: %s"
                    % (cor["estrutura"], cor["aorta"], vs,
                       _mm(cor["fechamento_mm"]), cor["aorta"], vs,
                       u", ".join(cor["cedem"]) or u"-"))
    if t.get("compostos"):
        cons.append(u"no entregue o composto sai no lugar das partes: " + u", ".join(
            u"%s(%d)" % (k, len(v)) for k, v in t["compostos"]))
    L.append(u"construcoes do entregue: " + (u" | ".join(cons) or u"nenhuma"))
    return [ascii_(x) for x in L]
