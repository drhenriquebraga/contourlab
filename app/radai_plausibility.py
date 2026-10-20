# -*- coding: utf-8 -*-

JANELA_PARENQUIMA_HU = (-30.0, 300.0)

JANELAS_HU = {
    "kidney_left": JANELA_PARENQUIMA_HU,
    "kidney_right": JANELA_PARENQUIMA_HU,
    "spleen": JANELA_PARENQUIMA_HU,
    "liver": JANELA_PARENQUIMA_HU,
    "pancreas": JANELA_PARENQUIMA_HU,
    "gallbladder": JANELA_PARENQUIMA_HU,
    "thyroid_gland": JANELA_PARENQUIMA_HU,
    "uterus": JANELA_PARENQUIMA_HU,
    "prostate": JANELA_PARENQUIMA_HU,
    "adrenal_gland_left": JANELA_PARENQUIMA_HU,
    "adrenal_gland_right": JANELA_PARENQUIMA_HU,

    "esophagus": None,
    "stomach": None,
    "colon": None,
    "small_bowel": None,
    "duodenum": None,
    "urinary_bladder": None,
    "lung_left": None,
    "lung_right": None,
    "trachea": None,

    "kidney_cyst_left": None,
    "kidney_cyst_right": None,
}

EROSAO_INTERIOR_MM = 2.0

FRACAO_FORA = 0.35
FRACAO_DUVIDOSA = 0.70

INTERIOR_MINIMO_VOXELS = 40

MOTIVOS = {
    "sustentada": u"a densidade do interior está dentro da janela declarada",
    "duvidosa": (u"parte do interior está fora da janela declarada — pode ser "
                 u"contorno grande demais, e pode ser outra coisa"),
    "interior_fora_da_janela": (
        u"a densidade do interior é compatível com gordura ou ar, e não com a "
        u"janela declarada para esta estrutura"),
    "super_segmentada": (
        u"o contorno parece grande demais: a densidade sai da janela à medida "
        u"que se afasta do centro, o que é o perfil de um contorno inflado e "
        u"não o de um leito"),
    "interior_insuficiente": (
        u"a estrutura é fina demais nesta espessura de corte para ter interior "
        u"medível — nada foi julgado"),
    "sem_janela_declarada": (
        u"esta estrutura não tem janela de densidade declarada, e por isso não "
        u"é julgada"),
}

COBERTURA = (
    u"Esta medida só enxerga interior compatível com GORDURA ou AR. Leito com "
    u"líquido, seroma, alça, músculo ou órgão vizinho deslocado lê como "
    u"sustentado. E órgão presente com contorno grande demais também sai da "
    u"janela — por outro motivo.")


def conferir_ancoragem(nomes, masks):
    fora = [n for n in (nomes or ()) if n not in (masks or {})]
    if fora:
        raise ValueError(
            u"sustentacao: nome fora do dicionario do motor (%s). Esta guarda "
            u"julga o que ja foi desenhado, e nunca procura o que nao foi."
            % u", ".join(sorted(fora)[:4]))
    return True


def conferir_motivo(cod):
    if cod not in MOTIVOS:
        raise ValueError(u"sustentacao: motivo fora do vocabulario: %r" % cod)
    return True


def frase(cod):
    conferir_motivo(cod)
    return MOTIVOS[cod]


def _base(nome):
    n = str(nome or "")
    if ":" in n:
        n = n.split(":", 1)[1]
    try:
        import radai_sets
        s = radai_sets.raiz_sem_sufixo(n)
        if len(s) < len(n):
            return n[:len(s)]
        return n
    except Exception:
        pass
    for sufixo in ("_ai", "_ts", "_nv", "_cds", "_lnl", "_pel"):
        if n.endswith(sufixo):
            n = n[:-len(sufixo)]
            break
    return n


def _declarada(nome):
    try:
        import radai_names
        return radai_names.tem(JANELAS_HU, _base(nome))
    except Exception:
        return _base(nome) in JANELAS_HU


def janela_de(nome):
    try:
        import radai_names
        return radai_names.procurar(JANELAS_HU, _base(nome))
    except Exception:
        return JANELAS_HU.get(_base(nome))


def medir(mask, volume_hu, grade, janela=None):
    fora = {"mediana": None, "fracao": None, "voxels": 0,
            "cod": "interior_insuficiente"}
    try:
        import numpy as np
        from scipy import ndimage as ndi
    except Exception:
        return fora
    if volume_hu is None or grade is None:
        return fora
    try:
        rec = _no_recorte(mask, volume_hu, grade)
        if rec is None:
            return fora
        return _medir_no_recorte(rec[0], rec[1], janela, fora)
    except Exception:
        return fora


def _no_recorte(mask, volume_hu, grade, caixas=None, nome=None):
    import numpy as np
    from scipy import ndimage as ndi
    import radai_geom
    if caixas is not None and nome is not None:
        m, cx, _n = caixas.de(nome)
    else:
        m = np.asarray(mask, bool)
        cx = radai_geom.Caixas({0: m}).de(0)[1]
    hu = np.asarray(volume_hu)
    if m.shape != hu.shape or cx is None:
        return None
    esp = tuple(abs(float(v)) for v in grade.spacing)
    dist = ndi.distance_transform_edt(m[cx], sampling=esp)
    return dist, hu[cx]


def _medir_no_recorte(dist, hu, janela, fora):
    import numpy as np
    interior = dist >= float(EROSAO_INTERIOR_MM)
    n = int(interior.sum())
    fora["voxels"] = n
    if n < INTERIOR_MINIMO_VOXELS:
        return fora
    vals = hu[interior].astype(float)
    lo, hi = janela or JANELA_PARENQUIMA_HU
    fora["mediana"] = float(np.median(vals))
    fora["fracao"] = float(((vals >= lo) & (vals <= hi)).mean())
    fora["cod"] = None
    return fora


def _perfil_de_erosao(mask, volume_hu, grade, janela):
    try:
        rec = _no_recorte(mask, volume_hu, grade)
        if rec is None:
            return None
        return _perfil_no_recorte(rec[0], rec[1], janela)
    except Exception:
        return None


def _perfil_no_recorte(dist, hu, janela):
    try:
        rmax = float(dist.max())
        if rmax <= EROSAO_INTERIOR_MM:
            return None
        lo, hi = janela
        fracs = []
        for f in (0.15, 0.45, 0.75):
            mm = max(EROSAO_INTERIOR_MM, rmax * f)
            dentro = dist >= mm
            if int(dentro.sum()) < INTERIOR_MINIMO_VOXELS:
                break
            v = hu[dentro].astype(float)
            fracs.append(float(((v >= lo) & (v <= hi)).mean()))
        if len(fracs) < 2:
            return None
        return fracs
    except Exception:
        return None


def conferir_sustentacao(masks, grade, volume_hu, log=None, modalidade=None,
                         caixas=None):
    laudo = {}
    _m = str(modalidade or "").strip().upper()
    if _m and _m != "CT":
        if log:
            log(u"sustentacao: nao rodou — a serie e %s, e a janela e em HU "
                u"(na RM o valor do pixel nao e grandeza fisica)" % _m)
        return laudo
    if grade is None or volume_hu is None or not masks:
        return laudo
    if caixas is None:
        try:
            import radai_geom
            caixas = radai_geom.Caixas(masks)
        except Exception:
            caixas = None
    try:
        for nome in sorted(masks):
            j = janela_de(nome)
            if not _declarada(nome):
                continue
            if j is None:
                laudo[nome] = {"cod": "sem_janela_declarada",
                               "frase": frase("sem_janela_declarada")}
                continue
            rec = None
            try:
                rec = _no_recorte(masks[nome], volume_hu, grade,
                                  caixas=caixas, nome=nome)
            except Exception:
                rec = None
            m = {"mediana": None, "fracao": None, "voxels": 0,
                 "cod": "interior_insuficiente"}
            if rec is not None:
                try:
                    m = _medir_no_recorte(rec[0], rec[1], j, m)
                except Exception:
                    m = {"mediana": None, "fracao": None, "voxels": 0,
                         "cod": "interior_insuficiente"}
            if m["cod"] == "interior_insuficiente":
                laudo[nome] = {"cod": "interior_insuficiente",
                               "frase": frase("interior_insuficiente"),
                               "voxels": m["voxels"]}
                continue
            fr, med = m["fracao"], m["mediana"]
            if fr >= FRACAO_DUVIDOSA:
                cod = "sustentada"
            elif fr >= FRACAO_FORA:
                cod = "duvidosa"
            else:
                perfil = _perfil_no_recorte(rec[0], rec[1], j)
                sobe = bool(perfil and (perfil[-1] - perfil[0]) >= 0.25)
                cod = "super_segmentada" if sobe else "interior_fora_da_janela"
            laudo[nome] = {"cod": cod, "frase": frase(cod),
                           "mediana_hu": round(med, 1) if med is not None else None,
                           "fracao": round(fr, 3) if fr is not None else None,
                           "janela_hu": list(j), "voxels": m["voxels"]}
        conferir_ancoragem(list(laudo), masks)
    except ValueError:
        raise
    except Exception:
        return laudo
    if log:
        _julgadas = [r for r in laudo.values()
                     if r["cod"] not in ("sem_janela_declarada",)]
        _marcadas = [r for r in laudo.values()
                     if r["cod"] in ("duvidosa", "interior_fora_da_janela",
                                     "super_segmentada")]
        if _julgadas:
            log(u"sustentacao: %d estrutura(s) medidas por densidade do "
                u"interior, %d marcada(s) para revisao"
                % (len(_julgadas), len(_marcadas)))
        for nome, r in sorted(laudo.items()):
            if r["cod"] in ("sustentada", "sem_janela_declarada"):
                continue
            if r["cod"] == "interior_insuficiente":
                continue
            log(u"sustentacao: %s — %s (mediana %s HU, %s%% do interior na "
                u"janela %s a %s). ENTREGUE assim mesmo, marcada para revisão."
                % (nome, r["frase"], r.get("mediana_hu"),
                   int(100 * (r.get("fracao") or 0)),
                   r.get("janela_hu", [None, None])[0],
                   r.get("janela_hu", [None, None])[1]))
    return laudo


def resumo(laudo):
    marcadas = sorted(n for n, r in (laudo or {}).items()
                      if r.get("cod") in ("duvidosa", "interior_fora_da_janela",
                                          "super_segmentada"))
    return {"julgadas": len(laudo or {}), "marcadas": marcadas,
            "cobertura": COBERTURA}
