# -*- coding: utf-8 -*-

import numpy as np

import radai_geom


LIMIAR_AR_HU = -300.0

EROSAO_DA_MESA_MM = 5.0

ABRIR_PONTES_VOXELS = 2

VOLUME_MINIMO_CM3 = 500.0

FRACAO_DO_MAIOR_NO_CORPO = 0.5

ESPESSURA_PELE_MM = 5.0

MARGEM_PAREDE_MM = 15.0

PULMAO_ESQ = ("lung_left", "lung_upper_lobe_left", "lung_lower_lobe_left")
PULMAO_DIR = ("lung_right", "lung_upper_lobe_right", "lung_middle_lobe_right",
              "lung_lower_lobe_right")
COSTELAS_ESQ = ("rib_left_", "ribs_left")
COSTELAS_DIR = ("rib_right_", "ribs_right")
CARTILAGENS = ("costal_cartilages",)
PULMOES = PULMAO_ESQ + PULMAO_DIR

CAVIDADE_TORACICA = ("thoracic_cavity",)
# GUARDA: o derrame pleural (inteiro ou ja partido por lado) entra na
# cavidade da parede: a parede nasce por fora dele e nunca o contem.
DERRAME_PLEURAL = ("pleural_effusion", "pleural_effusion_left",
                   "pleural_effusion_right")
BASE_DA_PAREDE = (PULMAO_ESQ + PULMAO_DIR + COSTELAS_ESQ + COSTELAS_DIR
                  + CARTILAGENS + CAVIDADE_TORACICA)

CROPS_DA_PAREDE = (
    "vertebrae_",
    "sternum",
    "scapula",
    "clavicula",
    "heart",
    "pericardium",
    "mediastinum",
    "esophagus", "trachea",
    "thyroid_gland",
    "liver", "spleen", "stomach", "duodenum", "pancreas",
    "kidney_left", "kidney_right", "adrenal_gland_left", "adrenal_gland_right",
    "colon", "small_bowel", "small_intestine", "urinary_bladder",
)

FICAM_NA_PAREDE = ("autochthon",)

RECORTES_QUE_O_LOG_NOMEIA = (
    (u"clavicula", ("clavicula",)),
    (u"escapula", ("scapula",)),
    (u"intestino", ("small_bowel", "small_intestine", "colon", "duodenum")),
    (u"coracao", ("heart",)),
    (u"pericardio", ("pericardium",)),
    (u"mediastino", ("mediastinum",)),
)

CAVIDADES_PROIBIDAS = ("abdominal_cavity",)

CLAVICULAS = ("clavicula",)
ESCAPULAS = ("scapula",)

ALCANCE_DO_PLANO_MEDIAL_MM = None

SUAVIZACAO_PAREDE_MM = 8.0

RECORTES_DA_SEGUNDA_PASSADA = (PULMOES + CAVIDADE_TORACICA
                               + CAVIDADES_PROIBIDAS + ("bag_bowel",)
                               + CROPS_DA_PAREDE)

FECHAMENTO_ANTERIOR_MM = 5.0
ALCANCE_DO_FECHAMENTO_MM = 2.0 * EROSAO_DA_MESA_MM
ANCORAS_DO_FECHAMENTO = ("abdominal_cavity", "small_bowel", "small_intestine",
                         "colon", "duodenum", "stomach", "rectum", "bag_bowel")
FORA_DO_CORPO_DA_PELE = ("skin", "chestwall_l", "chestwall_r")


def _bool(m):
    a = np.asarray(m)
    return a if a.dtype == bool else a.astype(bool)


def _componentes_comparaveis(mask, fracao):
    from scipy import ndimage
    mask = np.asarray(mask)
    mask = mask if mask.dtype == bool else mask.astype(bool)
    if not mask.any():
        return mask.copy(), None
    estrutura = ndimage.generate_binary_structure(3, 1)
    rotulos, n = ndimage.label(mask, structure=estrutura)
    if n <= 1:
        return mask.copy(), None
    contagens = np.bincount(rotulos.ravel())
    contagens[0] = 0
    grande = int(np.argmax(contagens))
    maior = rotulos == grande
    piso = float(fracao) * float(contagens[grande])
    outros = [i for i in range(1, n + 1)
              if i != grande and float(contagens[i]) >= piso]
    if not outros:
        return maior, None
    return maior, np.isin(rotulos, [grande] + outros)


def _corpo_com_os_membros(externo, nucleo_todos, bruto, grade, log=None):
    if nucleo_todos is None or externo is None:
        return externo
    try:
        todos = radai_geom.expandir(nucleo_todos, EROSAO_DA_MESA_MM,
                                    grade) & bruto
        _maior, todos_c = _componentes_comparaveis(todos,
                                                   FRACAO_DO_MAIOR_NO_CORPO)
        todos = _maior if todos_c is None else todos_c
        corpo = radai_geom.preencher_buracos(todos, por_fatia=True) | externo
        a_mais = corpo & ~externo
        if not a_mais.any():
            return externo
        if log:
            cm3 = radai_geom.volume_cm3(a_mais, grade)
            log("contorno externo: o corpo da R3 leva tambem %.0f cm3 de "
                "componente(s) com pelo menos %.0f%% do maior (os membros "
                "separados de uma TC so de membros); a pele e a parede "
                "continuam no maior" % (cm3, 100.0 * FRACAO_DO_MAIOR_NO_CORPO))
        return corpo
    except Exception as e:
        if log:
            log("contorno externo: nao consegui o corpo com os membros (%s) "
                "— a R3 usa so o maior componente" % str(e)[:120])
        return externo


def contorno_externo(volume_hu, grade, limiar=None, log=None,
                     com_o_corpo=False):
    nada = (None, None) if com_o_corpo else None
    try:
        lim = LIMIAR_AR_HU if limiar is None else float(limiar)
        arr = np.asarray(volume_hu)
        bruto = arr > lim
        if not bruto.any():
            return nada
        nucleo = radai_geom.contrair(bruto, EROSAO_DA_MESA_MM, grade)
        nucleo_todos = None
        if nucleo.any():
            if com_o_corpo:
                nucleo, nucleo_todos = _componentes_comparaveis(
                    nucleo, FRACAO_DO_MAIOR_NO_CORPO)
            else:
                nucleo = radai_geom.maior_componente(nucleo)
            corpo = radai_geom.expandir(nucleo, EROSAO_DA_MESA_MM, grade) & bruto
            corpo = radai_geom.maior_componente(corpo)
        else:
            sem_ponte = radai_geom.abrir_pontes(bruto, ABRIR_PONTES_VOXELS)
            corpo = radai_geom.maior_componente(
                sem_ponte if sem_ponte.any() else bruto)
        corpo = radai_geom.preencher_buracos(corpo, por_fatia=True)
        cm3 = radai_geom.volume_cm3(corpo, grade)
        if cm3 < VOLUME_MINIMO_CM3:
            if log:
                log("contorno externo: so %.0f cm3 (o minimo e %.0f) — nao "
                    "uso; a pele e a parede saem sem ele" % (cm3, VOLUME_MINIMO_CM3))
            return nada
        if log:
            log("contorno externo: %.0f cm3 (limiar %.0f HU) — insumo interno, "
                "NAO vai para nenhum RTSTRUCT" % (cm3, lim))
        if com_o_corpo:
            return corpo, _corpo_com_os_membros(corpo, nucleo_todos, bruto,
                                                grade, log=log)
        return corpo
    except Exception as e:
        if log:
            log("nao consegui o contorno externo (%s) — a pele e a parede "
                "ficam de fora desta serie" % str(e)[:120])
        return nada


def _uniao_das_estruturas(masks, forma):
    acc = np.zeros(forma, dtype=bool)
    n = 0
    for k in list(masks or ()):
        if str(k).startswith("_") or nome_normalizado(k) in FORA_DO_CORPO_DA_PELE:
            continue
        try:
            a = np.asarray(masks[k])
        except Exception:
            continue
        if a.shape != tuple(forma):
            continue
        a = a if a.dtype == bool else a.astype(bool)
        lim = radai_geom._limites(a)
        if lim is None:
            continue
        cx = tuple(slice(lo, hi + 1) for lo, hi in lim)
        acc[cx] |= a[cx]
        n += 1
    return acc, n


def _metade_anterior(corpo, grade):
    c = _para_canonico(_bool(corpo), grade)
    fora = np.zeros(c.shape, dtype=bool)
    for z in np.flatnonzero(c.any(axis=(1, 2))):
        ys = np.flatnonzero(c[z].any(axis=1))
        meio = (int(ys.min()) + int(ys.max())) // 2
        fora[z, :meio + 1, :] = True
    return _de_canonico(fora, grade)


def _perto_no_plano(m, mm, grade):
    from scipy import ndimage
    m = _bool(m)
    eixo = int(grade.eixo_sinal("sup")[0])
    plano = [e for e in range(3) if e != eixo]
    passo = min(float(grade.spacing[e]) for e in plano)
    n = max(1, int(round(float(mm) / passo)))
    lim = radai_geom._limites(m)
    if lim is None:
        return np.zeros(m.shape, dtype=bool)
    cx = tuple(slice(lo, hi + 1) if e == eixo
               else slice(max(0, lo - n), min(m.shape[e], hi + n + 1))
               for e, (lo, hi) in enumerate(lim))
    forma = [3, 3, 3]
    forma[eixo] = 1
    quadrado = np.ones(forma, dtype=bool)
    cruz = quadrado.copy()
    meio = [0 if e == eixo else 1 for e in range(3)]
    for a in plano:
        for b in plano:
            if a < b:
                for da in (0, 2):
                    for db in (0, 2):
                        idx = list(meio)
                        idx[a], idx[b] = da, db
                        cruz[tuple(idx)] = False
    sub = m[cx]
    for i in range(n):
        sub = ndimage.binary_dilation(sub, structure=cruz if i % 2 == 0
                                      else quadrado)
    fora = np.zeros(m.shape, dtype=bool)
    fora[cx] = sub
    return fora


def _fechar_no_plano(m, zona, mm, grade):
    from scipy import ndimage
    eixo = int(grade.eixo_sinal("sup")[0])
    raios = [0 if e == eixo else max(1, int(round(float(mm)
                                                   / float(grade.spacing[e]))))
             for e in range(3)]
    lim = radai_geom._limites(zona)
    if lim is None:
        return np.zeros(m.shape, dtype=bool)
    cx = tuple(slice(max(0, lo - 2 * raios[e]),
                     min(m.shape[e], hi + 2 * raios[e] + 1))
               for e, (lo, hi) in enumerate(lim))
    grades = np.ogrid[tuple(slice(-r, r + 1) for r in raios)]
    el = np.zeros(tuple(2 * r + 1 for r in raios), dtype=bool)
    soma = 0.0
    for e, g in enumerate(grades):
        if raios[e]:
            soma = soma + (g / float(raios[e])) ** 2
    el |= (soma <= 1.0)
    fora = np.zeros(m.shape, dtype=bool)
    fora[cx] = ndimage.binary_closing(m[cx], structure=el)
    return fora


def corpo_da_pele(externo, masks, grade, volume_hu=None, log=None):
    if externo is None:
        return None
    import time
    t0 = time.time()
    e = _bool(externo)
    try:
        from scipy import ndimage
        estr, n = _uniao_das_estruturas(masks, e.shape)
        if not n:
            return e
        corpo = e | estr
        ganho_estr = int((corpo & ~e).sum())
        ganho_tec = ganho_fecho = 0
        ancora = uniao_por_nome(masks, ANCORAS_DO_FECHAMENTO)
        if _tem(ancora) and _bool(ancora).shape == e.shape:
            zona = (_perto_no_plano(ancora, ALCANCE_DO_FECHAMENTO_MM, grade)
                    & _metade_anterior(corpo, grade))
            if (volume_hu is not None
                    and np.asarray(volume_hu).shape == e.shape):
                tecido = (zona & (np.asarray(volume_hu) > LIMIAR_AR_HU)
                          & ~corpo)
                if tecido.any():
                    corpo |= tecido
                    ganho_tec = int(tecido.sum())
            novo = (_fechar_no_plano(corpo, zona, FECHAMENTO_ANTERIOR_MM,
                                     grade) & zona & ~corpo)
            if novo.any():
                corpo |= novo
                ganho_fecho = int(novo.sum())
        corpo = radai_geom.preencher_buracos(corpo, por_fatia=True)
        rot, nr = ndimage.label(corpo)
        if nr > 1:
            vivos = np.unique(rot[e & corpo])
            vivos = vivos[vivos > 0]
            if vivos.size:
                corpo = np.isin(rot, vivos)
        if log:
            vx = float(np.prod(grade.spacing)) / 1000.0
            log(u"pele: o corpo inicial leva as %d estrutura(s) ja segmentadas "
                u"(+%.1f cm3) e fecha o contorno anterior junto das alcas e da "
                u"cavidade abdominal (tecido a ate %g mm: +%.1f cm3; "
                u"fechamento de %g mm: +%.1f cm3); total +%.1f cm3 em %.1f s"
                % (n, ganho_estr * vx, ALCANCE_DO_FECHAMENTO_MM, ganho_tec * vx,
                   FECHAMENTO_ANTERIOR_MM, ganho_fecho * vx,
                   int((corpo & ~e).sum()) * vx, time.time() - t0))
        return corpo
    except Exception as ex:
        if log:
            log(u"pele: nao consegui juntar as estruturas ao corpo (%s) — a "
                u"pele sai do contorno externo" % str(ex)[:120])
        return e


def pele(externo, grade, mm=None, log=None):
    try:
        if externo is None:
            return None
        e = _bool(externo)
        if not e.any():
            return None
        mm = ESPESSURA_PELE_MM if mm is None else float(mm)
        dentro = radai_geom.contrair(e, mm, grade)
        casca = e & ~dentro
        if not casca.any():
            return None
        if log:
            log("pele: %.0f cm3 (casca de %.1f mm do contorno externo)"
                % (radai_geom.volume_cm3(casca, grade), mm))
        return casca
    except Exception as e:
        if log:
            log("nao consegui a pele (%s)" % str(e)[:120])
        return None





def nome_normalizado(nome):
    return str(nome).split(":")[-1].strip().lower()


def _casa(nome, prefixo, exato=False):
    alvo = nome_normalizado(nome)
    p = str(prefixo).strip().lower()
    return alvo == p or (not exato and alvo.startswith(p))


def uniao_por_nome(masks, prefixos, cru=None, exato=False, ambas=False):
    fora = None
    for p in prefixos:
        achou = False
        for fonte in (masks, cru):
            if fonte is None or (achou and not ambas):
                continue
            for nome in list(fonte):
                if not _casa(nome, p, exato=exato):
                    continue
                achou = True
                b = _bool(fonte[nome])
                if fora is None:
                    fora = b.copy()
                elif fora.shape == b.shape:
                    fora |= b
                else:
                    fora = fora | b
    return fora


def _uniao(masks, prefixos):
    return uniao_por_nome(masks, prefixos)


def _tem(m):
    return m is not None and bool(np.asarray(m).any())




def _canonico(grade):
    eixos = []
    for lado in ("sup", "post", "esq"):
        eixos.append(grade.eixo_sinal(lado))
    perm = tuple(int(e) for e, _s in eixos)
    inverte = tuple(s < 0 for _e, s in eixos)
    return perm, inverte


def _para_canonico(a, grade):
    perm, inv = _canonico(grade)
    v = np.transpose(np.asarray(a), perm)
    return v[tuple(slice(None, None, -1) if f else slice(None) for f in inv)]


def _de_canonico(v, grade):
    perm, inv = _canonico(grade)
    v = np.asarray(v)[tuple(slice(None, None, -1) if f else slice(None)
                            for f in inv)]
    return np.ascontiguousarray(np.transpose(v, np.argsort(perm)))


def _espacamento_canonico(grade):
    perm, _inv = _canonico(grade)
    return tuple(float(grade.spacing[e]) for e in perm)


def _cortes_com(m, grade):
    if not _tem(m):
        return 0
    eixo = grade.eixo_sinal("sup")[0]
    outros = tuple(i for i in range(3) if i != eixo)
    return int(np.asarray(m).any(axis=outros).sum())


def torax_identificado(masks, grade, cru=None, log=None):
    if grade is None:
        return False, u"sem grade: nao da para medir o pulmao em cm3"
    try:
        import engine as _engine
        piso = float(_engine.VOLUME_MINIMO_PULMAO_CM3)
    except Exception as e:
        return False, (u"nao consegui ler o piso do pulmao no motor (%s)"
                       % type(e).__name__)
    try:
        pulmao = uniao_por_nome(masks, PULMOES, cru=cru)
        vol = radai_geom.volume_cm3(pulmao, grade) if _tem(pulmao) else 0.0
        n_cla = _cortes_com(uniao_por_nome(masks, CLAVICULAS, cru=cru), grade)
        n_esc = _cortes_com(uniao_por_nome(masks, ESCAPULAS, cru=cru), grade)
    except Exception as e:
        return False, u"nao consegui medir os marcos (%s: %s)" % (
            type(e).__name__, str(e)[:80])
    laudo = (u"pulmao %.0f cm3 (piso %.0f), clavicula em %d corte(s), "
             u"escapula em %d corte(s)" % (vol, piso, n_cla, n_esc))
    faltou = []
    if vol < piso:
        faltou.append(u"pulmao abaixo do piso")
    if not n_cla:
        faltou.append(u"nenhum corte de clavicula")
    if not n_esc:
        faltou.append(u"nenhum corte de escapula")
    if faltou:
        return False, u"%s — %s" % (", ".join(faltou), laudo)
    return True, laudo


def linha_media_por_corte(masks, grade, cru=None):
    ref = None
    for fonte in (masks, cru):
        if fonte is None:
            continue
        for nome in fonte:
            ref = np.asarray(fonte[nome]).shape
            break
        if ref is not None:
            break
    if ref is None:
        return None
    perm, _inv = _canonico(grade)
    nz, nx = ref[perm[0]], ref[perm[2]]
    meio = np.full(nz, np.nan)
    xs = np.arange(nx, dtype=np.float64)
    for prefixos in (("sternum",), ("vertebrae_",), PULMOES):
        m = uniao_por_nome(masks, prefixos, cru=cru)
        if not _tem(m):
            continue
        c = _para_canonico(m, grade)
        por_x = c.sum(axis=1).astype(np.float64)
        tot = por_x.sum(axis=1)
        faltam = np.isnan(meio) & (tot > 0)
        if faltam.any():
            meio[faltam] = (por_x[faltam] * xs).sum(axis=1) / tot[faltam]
    tem = ~np.isnan(meio)
    if not tem.any():
        return np.full(nz, (nx - 1) / 2.0)
    zs = np.where(tem)[0]
    for z in np.where(~tem)[0]:
        meio[z] = meio[zs[int(np.argmin(np.abs(zs - z)))]]
    return meio


def separar_por_lado(m, grade, linha_media):
    c = _para_canonico(_bool(m), grade)
    nx = c.shape[2]
    xs = np.arange(nx, dtype=np.float64)
    esq = c & (xs[None, None, :] > np.asarray(linha_media)[:, None, None])
    dir_ = c & ~esq
    return _de_canonico(esq, grade), _de_canonico(dir_, grade)


def cavidade_por_lado(cavidade, pulmao_esq, pulmao_dir, grade, linha_media):
    from scipy import ndimage
    c = np.array(_para_canonico(_bool(cavidade), grade), dtype=bool)
    nz, ny, nx = c.shape
    vazio = np.zeros(c.shape, dtype=bool)
    pe = (_para_canonico(_bool(pulmao_esq), grade) if _tem(pulmao_esq)
          else vazio)
    pd = (_para_canonico(_bool(pulmao_dir), grade) if _tem(pulmao_dir)
          else vazio)
    if linha_media is None:
        linha = np.full(nz, (nx - 1) / 2.0)
    else:
        linha = np.asarray(linha_media, dtype=np.float64)
    xs = np.arange(nx, dtype=np.float64)
    sp = _espacamento_canonico(grade)
    esq = np.zeros(c.shape, dtype=bool)
    if not c.any():
        return _de_canonico(esq, grade), _de_canonico(esq, grade)
    tudo = c | pe | pd
    ys = np.where(tudo.any(axis=(0, 2)))[0]
    xx = np.where(tudo.any(axis=(0, 1)))[0]
    caixa = (slice(int(ys.min()), int(ys.max()) + 1),
             slice(int(xx.min()), int(xx.max()) + 1))
    for z in np.where(c.any(axis=(1, 2)))[0]:
        pela_linha = np.broadcast_to(xs[None, :] > linha[z], (ny, nx))
        e_z = np.array(pela_linha, dtype=bool)
        if pe[z].any() and pd[z].any():
            de = ndimage.distance_transform_edt(~pe[z][caixa],
                                                sampling=(sp[1], sp[2]))
            dd = ndimage.distance_transform_edt(~pd[z][caixa],
                                                sampling=(sp[1], sp[2]))
            e_z[caixa] = np.where(de == dd, pela_linha[caixa], de < dd)
        e_z |= pe[z]
        e_z &= ~pd[z]
        esq[z] = c[z] & e_z
    dir_ = c & ~esq
    return _de_canonico(esq, grade), _de_canonico(dir_, grade)


def _cavidade_pleural(cavidade, pulmao, grade, lado, pulmoes=None):
    c = np.array(_para_canonico(_bool(cavidade), grade), dtype=bool)
    if not c.any():
        return _de_canonico(c, grade)
    lado = str(lado).lower()
    if lado not in ("esq", "dir"):
        raise ValueError(u"lado deve ser 'esq' ou 'dir': %r" % (lado,))
    p = _para_canonico(_bool(pulmao), grade) if _tem(pulmao) else None
    if p is not None and not p.any():
        p = None
    ref = p
    if ref is None and _tem(pulmoes):
        ref = _para_canonico(_bool(pulmoes), grade)
    if ref is None or not ref.any():
        return _de_canonico(c, grade)
    topo = int(np.where(ref.any(axis=(1, 2)))[0].max())
    c[topo + 1:] = False
    if p is not None:
        tem = p.any(axis=(1, 2))
        zs = np.where(tem)[0]
        por_x = p.any(axis=1)
        xs = np.arange(c.shape[2])
        for z in range(int(zs.min()), int(zs.max()) + 1):
            if not c[z].any():
                continue
            zr = z if tem[z] else int(zs[int(np.argmin(np.abs(zs - z)))])
            cols = np.where(por_x[zr])[0]
            if lado == "esq":
                c[z][:, xs < int(cols.min())] = False
            else:
                c[z][:, xs > int(cols.max())] = False
    return _de_canonico(c, grade)


def lateral_ao_esterno(forma, esterno, grade, lado, offset_mm=0.0,
                       alcance_posterior_mm=None):
    f = _bool(forma)
    if not _tem(esterno) or not f.any():
        return f.copy()
    lado = str(lado).lower()
    if lado not in ("esq", "dir"):
        raise ValueError(u"lado deve ser 'esq' ou 'dir': %r" % (lado,))
    c = np.array(_para_canonico(f, grade), dtype=bool)
    s = _para_canonico(_bool(esterno), grade)
    nz, ny, nx = c.shape
    tem = s.any(axis=(1, 2))
    zs = np.where(tem)[0]
    borda_esq = np.zeros(nz, dtype=np.int64)
    borda_dir = np.zeros(nz, dtype=np.int64)
    post = np.zeros(nz, dtype=np.int64)
    for z in zs:
        cols = np.where(s[z].any(axis=0))[0]
        rows = np.where(s[z].any(axis=1))[0]
        borda_esq[z], borda_dir[z] = int(cols.max()), int(cols.min())
        post[z] = int(rows.max())
    for z in np.where(~tem)[0]:
        perto = zs[int(np.argmin(np.abs(zs - z)))]
        borda_esq[z], borda_dir[z], post[z] = (borda_esq[perto],
                                               borda_dir[perto], post[perto])
    sp = _espacamento_canonico(grade)
    off = int(round(float(offset_mm or 0.0) / sp[2]))
    alc = (None if alcance_posterior_mm is None
           else int(round(float(alcance_posterior_mm) / sp[1])))
    xs = np.arange(nx)
    for z in range(nz):
        if not c[z].any():
            continue
        if lado == "esq":
            medial = xs <= borda_esq[z] + off
        else:
            medial = xs >= borda_dir[z] - off
        if alc is None:
            c[z][:, medial] = False
        else:
            ate = min(ny, post[z] + alc + 1)
            c[z][:ate, medial] = False
    return _de_canonico(c, grade)


def vizinhos_da_parede(masks, cru=None):
    uniao = uniao_por_nome(masks, CROPS_DA_PAREDE, cru=cru, ambas=True)
    faltaram = []
    for rotulo, prefixos in RECORTES_QUE_O_LOG_NOMEIA:
        achou = False
        for fonte in (masks, cru):
            if fonte is None:
                continue
            if any(_casa(n, p) for n in list(fonte) for p in prefixos):
                achou = True
                break
        if not achou:
            faltaram.append(rotulo)
    return uniao, faltaram


def _separar_os_lados(paredes, bases, grade, log=None):
    try:
        from scipy import ndimage
        inter = paredes["ChestWall_L"] & paredes["ChestWall_R"]
        if not inter.any():
            return paredes
        dist = {}
        for nome in ("ChestWall_L", "ChestWall_R"):
            b = bases.get(nome)
            if not _tem(b):
                return paredes
            dist[nome] = ndimage.distance_transform_edt(
                ~b, sampling=tuple(float(v) for v in grade.spacing))
        perto_de_L = dist["ChestWall_L"] <= dist["ChestWall_R"]
        cm3 = radai_geom.volume_cm3(inter, grade)
        paredes["ChestWall_L"] = paredes["ChestWall_L"] & ~(inter & ~perto_de_L)
        paredes["ChestWall_R"] = paredes["ChestWall_R"] & ~(inter & perto_de_L)
        if log:
            log("parede toracica: %.1f cm3 disputados entre os dois lados, "
                "entregues a quem estava mais perto (dois OAR sobrepostos "
                "fazem o DVH contar a mesma dose duas vezes)" % cm3)
        return paredes
    except Exception as e:
        if log:
            log("nao consegui separar os dois lados da parede (%s) — eles "
                "saem como estao" % str(e)[:100])
        return paredes


def _maior_pedaco(corte):
    from scipy import ndimage
    rot, n = ndimage.label(corte)
    if n <= 1:
        return corte
    tam = np.bincount(rot.ravel())
    tam[0] = 0
    return rot == int(np.argmax(tam))


FUROS_POR_CORTE_MAX = 256


def _abrir_furos(corte):
    from scipy import ndimage
    c = np.pad(np.asarray(corte, dtype=bool), 1)
    tirou = 0
    for _volta in range(FUROS_POR_CORTE_MAX):
        fundo, n = ndimage.label(~c)
        if n <= 1:
            break
        fora = int(fundo[0, 0])
        melhor = None
        for h in range(1, n + 1):
            if h == fora:
                continue
            ys, xs = np.where(fundo == h)
            for dy, dx, i in ((-1, 0, int(np.argmin(ys))),
                              (1, 0, int(np.argmax(ys))),
                              (0, -1, int(np.argmin(xs))),
                              (0, 1, int(np.argmax(xs)))):
                y, x = int(ys[i]), int(xs[i])
                caminho = []
                valido = False
                while True:
                    y += dy
                    x += dx
                    if c[y, x]:
                        caminho.append((y, x))
                        if melhor is not None and len(caminho) >= len(melhor):
                            break
                        continue
                    valido = int(fundo[y, x]) == fora
                    break
                if valido and (melhor is None or len(caminho) < len(melhor)):
                    melhor = caminho
        if not melhor:
            break
        for y, x in melhor:
            c[y, x] = False
        tirou += len(melhor)
    return c[1:-1, 1:-1], tirou


RAMOS_ABAIXO_DO_PULMAO = 2
AREA_MINIMA_DO_SEGUNDO_RAMO_MM2 = 100.0


def ramos_da_parede(nome, masks, cru=None):
    n = str(nome or u"")
    if n.endswith(u"_L"):
        pul, cost = PULMAO_ESQ, COSTELAS_ESQ
    elif n.endswith(u"_R"):
        pul, cost = PULMAO_DIR, COSTELAS_DIR
    else:
        return None, None
    return (uniao_por_nome(masks, pul, cru=cru),
            uniao_por_nome(masks, cost + CARTILAGENS, cru=cru))


def maior_contorno_por_corte(m, grade, pulmao=None, costelas=None,
                             laudo=None):
    from scipy import ndimage
    b = _bool(m)
    if isinstance(laudo, dict):
        laudo["cortes_com_dois_ramos"] = 0
    if not b.any():
        return b.copy(), 0
    eixo, sinal = (int(x) for x in grade.eixo_sinal("sup"))
    v = np.moveaxis(b, eixo, 0)
    fora = np.array(v, dtype=bool, copy=True)
    linhas = np.where(v.any(axis=(0, 2)))[0]
    colunas = np.where(v.any(axis=(0, 1)))[0]
    caixa = (slice(int(linhas.min()), int(linhas.max()) + 1),
             slice(int(colunas.min()), int(colunas.max()) + 1))
    ks = [int(k) for k in np.where(v.any(axis=(1, 2)))[0]]
    abaixo = set()
    vc = None
    px_mm2 = float(np.prod(grade.spacing)) / float(grade.spacing[eixo])
    if pulmao is not None and RAMOS_ABAIXO_DO_PULMAO > 1:
        vp = np.moveaxis(_bool(pulmao), eixo, 0)
        kp = np.where(vp.any(axis=(1, 2)))[0] if vp.shape == v.shape else ()
        if len(kp):
            if sinal > 0:
                abaixo = set(k for k in ks if k < int(kp.min()))
            else:
                abaixo = set(k for k in ks if k > int(kp.max()))
        if costelas is not None:
            vc = np.moveaxis(_bool(costelas), eixo, 0)
            if vc.shape != v.shape:
                vc = None
    ramo3d = None
    if abaixo and vc is not None:
        k0, k1 = min(abaixo), max(abaixo)
        bloco = v[k0:k1 + 1, caixa[0], caixa[1]]
        rot3, _n3 = ndimage.label(bloco)
        com_cost = np.unique(rot3[bloco & vc[k0:k1 + 1, caixa[0], caixa[1]]])
        ramo3d = (k0, rot3, set(int(x) for x in com_cost if x > 0))
    pedacos = {}
    for k in ks:
        rot, n = ndimage.label(v[k][caixa])
        areas = np.bincount(rot.ravel(), minlength=n + 1)
        areas[0] = 0
        pedacos[k] = (rot, n, areas)
    nota = {}
    for k in ks:
        rot, n, areas = pedacos[k]
        antes = pedacos.get(k - 1)
        for i in range(1, n + 1):
            soma, veio = 0, None
            if antes is not None:
                toca = np.unique(antes[0][rot == i])
                for j in (int(x) for x in toca if x > 0):
                    if nota[(k - 1, j)][0] > soma:
                        soma, veio = nota[(k - 1, j)][0], j
            nota[(k, i)] = (int(areas[i]) + soma, veio)
    escolha = {}
    if nota:
        fim = None
        for chave in sorted(nota):
            if fim is None or nota[chave][0] > nota[fim][0]:
                fim = chave
        k, i = fim
        while i is not None:
            escolha[k] = i
            i = nota[(k, i)][1]
            k -= 1
    tirou = 0
    for k in ks:
        s = v[k][caixa]
        rot, n, areas = pedacos[k]
        i = escolha.get(k)
        if i is None:
            i = int(np.argmax(areas)) if n > 1 else 1
        ramos = [s if n <= 1 else (rot == i)]
        if n > 1 and k in abaixo:
            outros = [j for j in range(1, n + 1) if j != i
                      and areas[j] * px_mm2 >= AREA_MINIMA_DO_SEGUNDO_RAMO_MM2]
            if ramo3d is not None:
                rk = ramo3d[1][k - ramo3d[0]]
                outros = [j for j in outros
                          if ramo3d[2].intersection(
                              int(x) for x in np.unique(rk[rot == j]))]
            outros.sort(key=lambda j: (-int(areas[j]), j))
            for j in outros[:RAMOS_ABAIXO_DO_PULMAO - 1]:
                ramos.append(rot == j)
            if len(ramos) > 1 and isinstance(laudo, dict):
                laudo["cortes_com_dois_ramos"] += 1
        fica = np.zeros(s.shape, dtype=bool)
        for r in ramos:
            r, fenda = _abrir_furos(r)
            if fenda:
                r = _maior_pedaco(r)
            fica |= r
        n = int(s.sum()) - int(fica.sum())
        if n:
            tirou += n
            fora[k][caixa] = fica
    return np.ascontiguousarray(np.moveaxis(fora, 0, eixo)), tirou


def componentes_que_tocam(permitido, semente, grade):
    from scipy import ndimage
    p = _bool(permitido)
    s = _bool(semente) & p
    if not s.any():
        return np.zeros(p.shape, dtype=bool)
    eixo = int(grade.eixo_sinal("sup")[0])
    vp = np.moveaxis(p, eixo, 0)
    vs = np.moveaxis(s, eixo, 0)
    fora = np.zeros(vp.shape, dtype=bool)
    for k in np.flatnonzero(vs.any(axis=(1, 2))):
        rot, _n = ndimage.label(vp[k])
        ids = np.unique(rot[vs[k]])
        ids = ids[ids > 0]
        if ids.size:
            fora[k] = np.isin(rot, ids)
    return np.ascontiguousarray(np.moveaxis(fora, 0, eixo))


COBERTURA_MINIMA_DAS_COSTELAS = 0.9


def _pedacos_com_costela(corte, costela, atual=None):
    from scipy import ndimage
    rot, n = ndimage.label(corte)
    if n <= 0:
        return corte
    areas = np.bincount(rot.ravel(), minlength=n + 1)
    areas[0] = 0
    com = [int(i) for i in np.unique(rot[corte & costela]) if i > 0]
    if atual is not None and atual.any():
        perto = ndimage.binary_dilation(atual, iterations=1)
        tocam = set(int(i) for i in np.unique(rot[perto]) if i > 0)
        com = [i for i in com if i in tocam]
        return np.isin(rot, com) if com else np.zeros(corte.shape, bool)
    if com:
        return rot == max(com, key=lambda i: (int(areas[i]), -i))
    return rot == int(np.argmax(areas))


def cortes_a_refazer(parede, pulmao, costelas, bruta, grade,
                     minimo=None):
    minimo = COBERTURA_MINIMA_DAS_COSTELAS if minimo is None else minimo
    eixo = int(grade.eixo_sinal("sup")[0])
    if not (_tem(pulmao) and _tem(costelas)):
        return []
    vp = np.moveaxis(_bool(pulmao), eixo, 0)
    vc = np.moveaxis(_bool(costelas), eixo, 0)
    vw = None if not _tem(parede) else np.moveaxis(_bool(parede), eixo, 0)
    vb = None if not _tem(bruta) else np.moveaxis(_bool(bruta), eixo, 0)
    fora = []
    for k in np.flatnonzero(vp.any(axis=(1, 2)) & vc.any(axis=(1, 2))):
        k = int(k)
        if vw is None or not vw[k].any():
            fora.append(k)
            continue
        if vb is None:
            continue
        ref = vc[k] & vb[k]
        n = int(ref.sum())
        if n and int((ref & vw[k]).sum()) < minimo * n:
            fora.append(k)
    return fora


def garantir_os_cortes(fora, brutas, masks, grade, cru=None, nunca=None):
    voltaram = {}
    eixo = int(grade.eixo_sinal("sup")[0])
    for nome, outro in (("ChestWall_L", "ChestWall_R"),
                        ("ChestWall_R", "ChestWall_L")):
        bruta = brutas.get(nome)
        pul, cost = ramos_da_parede(nome, masks, cru=cru)
        if not (_tem(pul) and _tem(cost)):
            continue
        atual = fora.get(nome)
        m = (np.zeros(_bool(pul).shape, dtype=bool) if atual is None
             else np.array(_bool(atual), dtype=bool, copy=True))
        ks = cortes_a_refazer(m, pul, cost, bruta, grade)
        if not ks:
            continue
        vm = np.moveaxis(m, eixo, 0)
        vc = np.moveaxis(_bool(cost), eixo, 0)
        vb = None if not _tem(bruta) else np.moveaxis(_bool(bruta), eixo, 0)
        vo = (None if not _tem(fora.get(outro))
              else np.moveaxis(_bool(fora[outro]), eixo, 0))
        vn = None if not _tem(nunca) else np.moveaxis(_bool(nunca), eixo, 0)
        n = 0
        for k in ks:
            s = (vb[k].copy() if vb is not None
                 else np.zeros(vc[k].shape, dtype=bool))
            if vo is not None:
                s &= ~vo[k]
            if not s.any() and not vm[k].any():
                s = vc[k].copy()
                if vn is not None:
                    s &= ~vn[k]
                if vo is not None:
                    s &= ~vo[k]
            if not s.any():
                continue
            falta = vc[k] & ~vm[k]
            novo = vm[k] | _pedacos_com_costela(
                s, falta if falta.any() else vc[k], atual=vm[k])
            if vo is not None:
                novo &= ~vo[k]
            if np.array_equal(novo, vm[k]):
                continue
            vm[k] = novo
            n += 1
        if n:
            fora[nome] = m
            voltaram[nome] = n
    return voltaram


def parede_toracica(masks, externo, grade, mm=None, log=None, torax=None,
                    cru=None):
    fora = {}
    try:
        if grade is None:
            return fora
        mm = MARGEM_PAREDE_MM if mm is None else float(mm)

        if torax is None:
            tem, pq = torax_identificado(masks, grade, cru=cru)
            if not tem:
                if log:
                    log(u"parede toracica: nao sai — torax nao identificado "
                        u"pela anatomia (%s)" % pq)
                return fora
            porque = u"torax identificado pela anatomia: %s" % pq
        elif not torax:
            if log:
                log(u"parede toracica: nao sai — nao foi pedida nesta serie")
            return fora
        else:
            porque = u"pedida pelo Estudo Torax"

        cavidade = uniao_por_nome(masks, CAVIDADES_PROIBIDAS, cru=cru,
                                  exato=True, ambas=True)
        if not _tem(cavidade):
            if log:
                log(u"parede toracica: nao sai — a cavidade abdominal "
                    u"(`abdominal_cavity`, da task `trunk_cavities`) nao veio "
                    u"nesta serie, e sem ela o limite inferior nao e "
                    u"anatomico. No «Rodar agora» ela vem com o Estudo Torax; "
                    u"no vigia, com a anatomia de torax")
            return fora

        if externo is None:
            if log:
                log("parede toracica: sem contorno externo, a face externa "
                    "ficaria sem limite — nao sai")
            return fora

        ambos = uniao_por_nome(masks, PULMOES, cru=cru)
        gradil = uniao_por_nome(masks, COSTELAS_ESQ + COSTELAS_DIR
                                + CARTILAGENS, cru=cru)
        if not _tem(ambos) and not _tem(gradil):
            if log:
                log("parede toracica: nao ha pulmao nem costela nesta serie "
                    "— nao sai")
            return fora

        vizinhos, faltaram = vizinhos_da_parede(masks, cru=cru)
        vizinhos = cavidade if vizinhos is None else (vizinhos | cavidade)
        dentro_da_pele = radai_geom.contrair(_bool(externo),
                                             ESPESSURA_PELE_MM, grade)
        esterno = uniao_por_nome(masks, ("sternum",), cru=cru)
        alcance = (mm if ALCANCE_DO_PLANO_MEDIAL_MM is None
                   else float(ALCANCE_DO_PLANO_MEDIAL_MM))

        cart = uniao_por_nome(masks, CARTILAGENS, cru=cru)
        cav_toda = uniao_por_nome(masks, CAVIDADE_TORACICA, cru=cru,
                                  exato=True, ambas=True)
        derrame = uniao_por_nome(masks, DERRAME_PLEURAL, cru=cru, exato=True,
                                 ambas=True)
        if _tem(derrame):
            if _tem(cav_toda):
                cav_toda = cav_toda | derrame
            else:
                cav_toda = derrame if not _tem(ambos) else (derrame | ambos)
            if log:
                log(u"parede toracica: o derrame pleural (%.0f cm3) entra na "
                    u"cavidade de cada lado" % radai_geom.volume_cm3(derrame,
                                                                     grade))
        tem_cav = _tem(cav_toda)
        linha = (linha_media_por_corte(masks, grade, cru=cru)
                 if (_tem(cart) or tem_cav) else None)
        cart_lado = {"ChestWall_L": None, "ChestWall_R": None}
        if _tem(cart) and linha is not None:
            e, d = separar_por_lado(cart, grade, linha)
            cart_lado = {"ChestWall_L": e, "ChestWall_R": d}
        cav_lado = {"ChestWall_L": None, "ChestWall_R": None}
        nunca = ambos
        if tem_cav:
            pul_e = uniao_por_nome(masks, PULMAO_ESQ, cru=cru)
            pul_d = uniao_por_nome(masks, PULMAO_DIR, cru=cru)
            ce, cd = cavidade_por_lado(cav_toda, pul_e, pul_d, grade, linha)
            cav_lado = {
                "ChestWall_L": _cavidade_pleural(ce, pul_e, grade, "esq",
                                                 pulmoes=ambos),
                "ChestWall_R": _cavidade_pleural(cd, pul_d, grade, "dir",
                                                 pulmoes=ambos)}
            nunca = cav_toda if not _tem(ambos) else (cav_toda | ambos)
            if log:
                log(u"parede toracica: base = cavidade toracica do lado "
                    u"(pulmao e derrame, %.0f cm3 nos dois lados, partida pelo "
                    u"pulmao mais proximo e sem o que sobe pelo pescoco) + "
                    u"costelas + metade da cartilagem; a cavidade inteira sai "
                    u"da parede" % radai_geom.volume_cm3(cav_toda, grade))
        elif log:
            log(u"parede toracica: sem a cavidade toracica (`thoracic_cavity`, "
                u"da task `trunk_cavities`) nesta serie — a base e pulmao + "
                u"costelas + cartilagens, como na v8.2, e um derrame pleural, "
                u"se houver, NAO e subtraido da parede")

        base_z = gradil if _tem(gradil) else ambos

        def _recortar(m, lado):
            if _tem(nunca):
                m = m & ~nunca
            m = m & ~vizinhos
            m = m & dentro_da_pele
            m = lateral_ao_esterno(m, esterno, grade, lado,
                                   alcance_posterior_mm=alcance)
            return radai_geom.limitar_por_plano(m, "inf", base_z, grade=grade)

        bases = {}
        brutas = {}
        for nome, lado, pulmao, costelas in (
                ("ChestWall_L", "esq", PULMAO_ESQ, COSTELAS_ESQ),
                ("ChestWall_R", "dir", PULMAO_DIR, COSTELAS_DIR)):
            base = None
            for pedaco in (uniao_por_nome(masks, pulmao, cru=cru),
                           uniao_por_nome(masks, costelas, cru=cru),
                           cart_lado[nome], cav_lado[nome]):
                if _tem(pedaco):
                    base = pedaco.copy() if base is None else (base | pedaco)
            if not _tem(base):
                continue
            bases[nome] = base
            m = radai_geom.expandir(base, mm, grade)
            m = _recortar(m, lado)
            if not m.any():
                continue
            brutas[nome] = m
            m = radai_geom.suavizar(m, SUAVIZACAO_PAREDE_MM, grade)
            m = _recortar(m, lado)
            m = radai_geom.maior_componente(m)
            if m.any():
                fora[nome] = m

        if len(fora) == 2:
            fora = _separar_os_lados(fora, bases, grade, log=log)

        tirados = []
        vx = float(np.prod(grade.spacing)) / 1000.0
        for nome in sorted(fora):
            pul, grd = ramos_da_parede(nome, masks, cru=cru)
            laudo_r = {}
            m, tirou = maior_contorno_por_corte(fora[nome], grade, pulmao=pul,
                                                costelas=grd, laudo=laudo_r)
            fora[nome] = m
            tirados.append(u"%s -%.1f cm3 (%d corte(s) com os dois ramos)"
                           % (nome, tirou * vx,
                              laudo_r.get("cortes_com_dois_ramos", 0)))
        if log and tirados:
            log(u"parede toracica: um contorno por corte onde ha pulmao (o "
                u"maior pedaco, e os furos abertos por uma fenda de 1 voxel); "
                u"abaixo da base do pulmao, ate %d ramos com costela: %s"
                % (RAMOS_ABAIXO_DO_PULMAO, u", ".join(tirados)))
        voltaram = garantir_os_cortes(fora, brutas, masks, grade, cru=cru,
                                      nunca=nunca)
        if log and voltaram:
            log(u"parede toracica: %s corte(s) com costela e pulmao do lado "
                u"em que a suavizacao tinha tirado a parede (ou parte dela) de "
                u"cima das costelas — o pedaco sem suavizar voltou"
                % u", ".join(u"%s %d" % kv for kv in sorted(voltaram.items())))
        if log:
            if faltaram:
                log(u"parede toracica: recortes que NAO vieram nesta serie: "
                    u"%s — o limite ali fica por conta dos outros recortes"
                    % ", ".join(faltaram))
            if not _tem(esterno):
                log(u"parede toracica: sem esterno nesta serie, o plano "
                    u"medial nao existe — o limite medial e o que sobra dos "
                    u"recortes")
            if fora:
                log(u"parede toracica: %s (%s; %s + %.1f mm, menos %s, "
                    u"recortada em vertebra, esterno, escapula, clavicula, "
                    u"coracao, pericardio, mediastino, esofago, traqueia, "
                    u"viscera, cavidade abdominal e pele — sem vasos; plano "
                    u"medial na borda lateral do esterno; suavizada %g mm; "
                    u"o autoctone fica)"
                    % (", ".join("%s %.0f cm3"
                                 % (k, radai_geom.volume_cm3(v, grade))
                                 for k, v in sorted(fora.items())),
                       porque,
                       (u"cavidade toracica + costelas + cartilagens"
                        if tem_cav else u"pulmao + costelas + cartilagens"),
                       mm,
                       (u"a cavidade toracica inteira" if tem_cav
                        else u"os pulmoes"),
                       SUAVIZACAO_PAREDE_MM))
    except Exception as e:
        if log:
            log("nao consegui a parede toracica (%s) — o contorno entregue "
                "nao foi afetado" % str(e)[:120])
        return {}
    return fora
