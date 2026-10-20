# -*- coding: utf-8 -*-

CHAVE_DO_CORACAO_DO_MODELO = "heart_model"

ALIAS_INTERNO = {
    CHAVE_DO_CORACAO_DO_MODELO: "heart",
}

_MAPA = {"cru_para_amigavel": {}, "amigavel_para_crus": {},
         "registrado": False}


def registrar(ts_map):
    candidatos = {}
    amigavel_para_crus = {}
    for amigavel, por_task in (ts_map or {}).items():
        if not isinstance(por_task, dict):
            continue
        crus = set()
        for lista in por_task.values():
            crus.update(lista or ())
        amigavel_para_crus[str(amigavel)] = tuple(sorted(crus))
        if len(crus) != 1:
            continue
        cru = next(iter(crus))
        candidatos.setdefault(cru, set()).add(str(amigavel))
    cru_para_amigavel = {}
    for cru, amigaveis in candidatos.items():
        if len(amigaveis) != 1:
            continue
        am = next(iter(amigaveis))
        if cru != am and cru in (ts_map or {}):
            continue
        cru_para_amigavel[cru] = am
    _MAPA["cru_para_amigavel"] = cru_para_amigavel
    _MAPA["amigavel_para_crus"] = amigavel_para_crus
    _MAPA["registrado"] = True
    return sum(1 for c, a in cru_para_amigavel.items() if c != a)


def _garantir():
    if _MAPA["registrado"]:
        return
    try:
        import engine
    except Exception:
        _MAPA["registrado"] = True


def _limpo(nome):
    n = str(nome or "")
    if ":" in n:
        n = n.split(":")[-1]
    if "@" in n:
        n = n.split("@", 1)[0]
    return n


def canonico(nome):
    _garantir()
    n = _limpo(nome)
    return _MAPA["cru_para_amigavel"].get(n, n)


def formas(nome):
    _garantir()
    n = _limpo(nome)
    fora = []

    def _add(x):
        if x and x not in fora:
            fora.append(x)

    _add(n)
    c = _MAPA["cru_para_amigavel"].get(n, n)
    _add(c)
    for base in (n, c):
        i = ALIAS_INTERNO.get(base)
        if i:
            _add(i)
            _add(_MAPA["cru_para_amigavel"].get(i, i))
    for am in list(fora):
        for cru in _MAPA["amigavel_para_crus"].get(am, ()):
            _add(cru)
    return tuple(fora)


def procurar(tabela, nome, padrao=None):
    if not tabela:
        return padrao
    for f in formas(nome):
        if f in tabela:
            return tabela[f]
    return padrao


def tem(tabela, nome):
    if not tabela:
        return False
    return any(f in tabela for f in formas(nome))


def achar(masks, nome):
    if not masks:
        return None
    for f in formas(nome):
        try:
            if f in masks:
                return f
        except Exception:
            continue
    return None


def casa_prefixo(nome, prefixos):
    fs = formas(nome)
    for p in prefixos or ():
        for f in fs:
            if f == p or f.startswith(p):
                return p
    return None


def crus_de(nome):
    _garantir()
    return tuple(_MAPA["amigavel_para_crus"].get(canonico(nome), ()))
