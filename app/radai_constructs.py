# -*- coding: utf-8 -*-

import inspect

import numpy as np

import radai_geom
import radai_names
from radai_skin import _bool, _tem, uniao_por_nome


CHAVE_PERICARDIO = "pericardium"
CHAVE_CORACAO_AI = "heart"
CHAVE_BAG_BOWEL = "bag_bowel"

CHAVE_CORACAO_DO_MODELO = radai_names.CHAVE_DO_CORACAO_DO_MODELO


class Construcao(object):

    __slots__ = ("chave", "mascara", "descricao", "entrou", "faltou",
                 "extras")

    def __init__(self, chave, mascara, descricao, entrou=(), faltou=(),
                 extras=None):
        self.chave = chave
        self.mascara = mascara
        self.descricao = descricao
        self.entrou = list(entrou)
        self.faltou = list(faltou)
        self.extras = dict(extras or {})

    def __bool__(self):
        return _tem(self.mascara)

    __nonzero__ = __bool__

    def __repr__(self):
        return "Construcao(%r, %d voxels)" % (
            self.chave, int(np.asarray(self.mascara).sum())
            if self.mascara is not None else 0)


def _cm3(m, grade):
    return radai_geom.volume_cm3(m, grade) if _tem(m) else 0.0


def _falar(log, texto):
    if log:
        try:
            log(texto)
        except Exception:
            pass


def _motor():
    import engine
    return engine


_VIZINHOS_AMIGAVEIS = ("ribs_",)


def _vizinhos_do_coracao(masks, cru=None):
    E = _motor()
    return uniao_por_nome(masks, tuple(E.FORA_DO_PERICARDIO)
                          + _VIZINHOS_AMIGAVEIS, cru=cru)


def _exata(masks, nome, cru=None):
    return uniao_por_nome(masks, (nome,), cru=cru, exato=True)


def _coracao_do_modelo(masks, cru=None):
    for fonte in (masks, cru):
        if fonte is None:
            continue
        for nome in (CHAVE_CORACAO_DO_MODELO, "heart"):
            m = uniao_por_nome(fonte, (nome,), exato=True)
            if m is not None:
                return m, nome
    return None, None


def _aorta_descendente(masks, grade, cru=None):
    cor, _n = _coracao_do_modelo(masks, cru)
    ao = _exata(masks, "aorta", cru)
    if not _tem(cor) or not _tem(ao):
        return None
    ao = radai_geom.limitar_por_plano(ao, "sup", cor, grade=grade)
    _asc, desc = _motor()._aorta_ascendente(ao, cor, grade)
    return desc


def pericardio_corrigido(masks, grade, log=None, cru=None):
    try:
        if grade is None:
            _falar(log, u"pericardio corrigido: nao sai — sem grade")
            return None
        peri = _exata(masks, "pericardium", cru)
        if not _tem(peri):
            _falar(log, u"pericardio corrigido: nao sai — o `pericardium` so "
                        u"existe na task `trunk_cavities`, e ela nao rodou "
                        u"nesta serie")
            return None
        cor, nome_cor = _coracao_do_modelo(masks, cru)
        if not _tem(cor):
            _falar(log, u"pericardio corrigido: nao sai — o coracao do modelo "
                        u"(`%s`, ou `heart` no dicionario de antes) nao veio "
                        u"nesta serie, e a correcao existe para conte-lo; o "
                        u"pericardio da task trunk_cavities nao e corrigido"
                   % CHAVE_CORACAO_DO_MODELO)
            return None
        laa = _exata(masks, "atrial_appendage_left", cru)
        coracao = cor.copy()
        entrou = [u"pericardium (trunk_cavities)", u"heart"]
        faltou = []
        if _tem(laa):
            coracao |= laa
            entrou.append(u"atrial_appendage_left")
        else:
            faltou.append(u"atrial_appendage_left")
        uniao = peri | coracao
        vizinhos = _vizinhos_do_coracao(masks, cru)
        desc = _aorta_descendente(masks, grade, cru)
        tirar = None
        for m in (vizinhos, desc):
            if _tem(m):
                tirar = m.copy() if tirar is None else (tirar | m)
        antes = uniao.copy()
        encostado = 0.0
        if tirar is not None:
            uniao &= ~tirar
            encostado = _cm3(coracao & tirar, grade)
            uniao |= coracao
        v_peri, v_fim = _cm3(peri, grade), _cm3(uniao, grade)
        ganho = _cm3(uniao & ~peri, grade)
        perdido = _cm3(antes & ~uniao, grade)
        _falar(log, u"pericardio corrigido: %.1f cm3 (o da trunk_cavities "
                    u"tinha %.1f; +%.1f cm3 de coracao que estava fora dele; "
                    u"-%.1f cm3 de pulmao, esofago, vias aereas, aorta "
                    u"descendente e os outros vizinhos do coracao)%s"
               % (v_fim, v_peri, ganho, perdido,
                  (u"; %.1f cm3 do coracao encostavam num vizinho e ficaram "
                   u"(o coracao fica dentro do pericardio)" % encostado)
                  if encostado else u""))
        descr = (u"Pericardio: o da task trunk_cavities unido ao coracao do "
                 u"modelo (%s), menos pulmoes, esofago, vias aereas, aorta "
                 u"descendente e os vizinhos do coracao. O coracao fica "
                 u"dentro do pericardio." % ", ".join(entrou[1:]))
        return Construcao(CHAVE_PERICARDIO, uniao, descr, entrou, faltou,
                          extras={"aorta_descendente": desc,
                                  "coracao_do_modelo": nome_cor})
    except Exception as e:
        _falar(log, u"nao consegui o pericardio corrigido (%s: %s) — ele sai "
                    u"como a task entregou" % (type(e).__name__, str(e)[:100]))
        return None


_CHAVE_ENXUTA = "heart"


def _mesclagem_do_motor(E, enxuto, grade, log):
    try:
        aceita = "chave" in inspect.signature(
            E.coracao_de_radioterapia).parameters
    except (TypeError, ValueError):
        aceita = False
    if aceita:
        return E.coracao_de_radioterapia(enxuto, grade, log=log,
                                         chave=_CHAVE_ENXUTA)
    return E.coracao_de_radioterapia(enxuto, grade, log=log)


CAMARAS_DO_CORACAO = ("heart_atrium_left", "heart_atrium_right",
                      "heart_ventricle_left", "heart_ventricle_right")


def _marco_superior_do_coracao(masks, cor, laa, grade, cru=None):
    partes = [(u"coracao do modelo", _bool(cor))]
    for nome in CAMARAS_DO_CORACAO:
        m = _exata(masks, nome, cru)
        if _tem(m):
            partes.append((nome, _bool(m)))
    if _tem(laa):
        partes.append((u"apendice atrial esquerdo", _bool(laa)))
    marco = partes[0][1].copy()
    for _n, m in partes[1:]:
        marco |= m
    try:
        topo = radai_geom.indice_do_extremo(marco, "sup", grade)
        dono = [n for n, m in partes
                if _tem(m)
                and radai_geom.indice_do_extremo(m, "sup", grade) == topo]
    except Exception:
        dono = []
    sem_laa = u"" if _tem(laa) else (u"; sem o apendice atrial esquerdo "
                                     u"nesta serie")
    qual = (u"corte mais alto das camaras (atrios e ventriculos) e do "
            u"apendice atrial esquerdo, que nesta serie e o do %s%s"
            % (dono[0] if dono else partes[0][0], sem_laa))
    return marco, qual


APENDICE_COMPATIVEL_CM3 = (2.0, 20.0)


def _acima(a, b, grade):
    _eixo, sinal = grade.eixo_sinal("sup")
    return (int(a) - int(b)) * sinal > 0


def marco_pelo_apendice(laa, cor, grade):
    if not _tem(laa):
        return None, u"sem o apendice atrial esquerdo nesta serie"
    v = _cm3(laa, grade)
    lo, hi = APENDICE_COMPATIVEL_CM3
    if not (lo <= v <= hi):
        return None, (u"apendice atrial esquerdo com %.1f cm3, fora de %g a "
                      u"%g cm3" % (v, lo, hi))
    if _tem(cor):
        try:
            t_l = radai_geom.indice_do_extremo(laa, "sup", grade)
            t_c = radai_geom.indice_do_extremo(cor, "sup", grade)
            b_c = radai_geom.indice_do_extremo(cor, "inf", grade)
        except Exception:
            return None, u"nao consegui medir o topo do apendice"
        if _acima(t_l, t_c, grade) or not _acima(t_l, b_c, grade):
            return None, (u"o topo do apendice atrial esquerdo cai fora da "
                          u"altura do coracao do modelo")
    return _bool(laa), (u"topo do apendice atrial esquerdo (AtrialApp_L, "
                        u"%.1f cm3)" % v)


def _derrame_pericardico(masks, cru=None):
    d = _exata(masks, "pericardial_effusion", cru)
    return _bool(d) if _tem(d) else None


def coracao_ai(masks, grade, log=None, cru=None, pericardio=None):
    try:
        if grade is None:
            _falar(log, u"coracao de radioterapia (Heart_ai): nao sai — sem "
                        u"grade")
            return None
        E = _motor()
        cor, nome_cor = _coracao_do_modelo(masks, cru)
        if not _tem(cor):
            _falar(log, u"coracao de radioterapia (Heart_ai): nao sai — o "
                        u"coracao do modelo (`%s`, ou `heart` no dicionario "
                        u"de antes) nao veio nesta serie"
                   % CHAVE_CORACAO_DO_MODELO)
            return None

        enxuto = {_CHAVE_ENXUTA: cor}
        ao = _exata(masks, "aorta", cru)
        if _tem(ao):
            enxuto["aorta"] = ao
        for nome, _inteiro in E.VASOS_DO_CORACAO:
            v = _exata(masks, nome, cru)
            if _tem(v):
                enxuto[nome] = v
        viz = _vizinhos_do_coracao(masks, cru)
        if _tem(viz):
            enxuto[E.FORA_DO_PERICARDIO[0]] = viz
        rt, desc = _mesclagem_do_motor(E, enxuto, grade, log)
        if rt is None or not _tem(rt):
            _falar(log, u"coracao de radioterapia (Heart_ai): a mesclagem do "
                        u"motor nao devolveu nada — nao sai")
            return None
        entrou = [u"heart"]
        if _tem(ao):
            entrou.append(u"aorta ascendente")
        entrou += [n for n, _i in E.VASOS_DO_CORACAO if n in enxuto]
        faltou = []
        mesclagem = np.array(rt, dtype=bool)
        v_motor = _cm3(mesclagem, grade)

        peri = None
        if pericardio is None:
            c = pericardio_corrigido(masks, grade, log=log, cru=cru)
            peri = c.mascara if c else None
            if _tem(peri):
                sem_peri = u""
            elif _tem(_exata(masks, "pericardium", cru)):
                sem_peri = (u"o pericardio corrigido nao saiu nesta serie "
                            u"(ver a linha anterior do log)")
            else:
                sem_peri = u"a task trunk_cavities nao rodou nesta serie"
        elif pericardio is False:
            sem_peri = u"quem montou o conjunto pediu sem pericardio"
        else:
            peri = getattr(pericardio, "mascara", pericardio)
            sem_peri = (u"" if _tem(peri) else
                        u"o pericardio entregue a esta construcao veio vazio")

        derrame = _derrame_pericardico(masks, cru)
        if not _tem(peri):
            if derrame is not None:
                mesclagem = mesclagem | derrame
                entrou.append(u"derrame pericardico")
            faltou.append(u"pericardio (%s)" % sem_peri)
            _falar(log, u"coracao de radioterapia: Heart_ai %.0f cm3 = a "
                        u"mesclagem do motor, como ate hoje (SEM pericardio: "
                        u"%s; sem o apendice atrial esquerdo e sem o plano "
                        u"superior no corte mais alto das camaras e do "
                        u"apendice, que sao da receita com pericardio). "
                        u"Entraram: %s"
                   % (v_motor, sem_peri, ", ".join(entrou)))
            descr = (u"Heart_ai: coracao de radioterapia como ate a v8.1, "
                     u"montado a partir dos rotulos do TotalSegmentator (%s), "
                     u"fechamento de %.0f mm, recortado nos vizinhos e na "
                     u"aorta descendente. SEM pericardio: %s, e o volume sai "
                     u"menor que o da definicao (Feng: com o pericardio "
                     u"completo)."
                     % (", ".join(entrou),
                        float(E.FECHAMENTO_PERICARDIO_MM), sem_peri))
            if derrame is not None:
                descr += (u" Inclui o derrame pericardico (PericardEff, %.1f "
                          u"cm3)." % _cm3(derrame, grade))
            return Construcao(CHAVE_CORACAO_AI, mesclagem, descr, entrou,
                              faltou,
                              extras={"aorta_descendente": desc,
                                      "com_pericardio": False,
                                      "coracao_do_modelo": nome_cor})

        heart_ai = mesclagem.copy()
        laa = _exata(masks, "atrial_appendage_left", cru)
        if _tem(laa):
            heart_ai |= laa
            entrou.append(u"atrial_appendage_left")
        else:
            faltou.append(u"atrial_appendage_left")
        heart_ai |= _bool(peri)
        entrou.append(u"pericardio corrigido (trunk_cavities)")
        if derrame is not None:
            heart_ai |= derrame
            entrou.append(u"derrame pericardico")

        marco, qual = marco_pelo_apendice(laa, cor, grade)
        if marco is None:
            _pq_apendice = qual
            marco, qual = _marco_superior_do_coracao(masks, cor, laa, grade,
                                                     cru)
            qual = u"%s (limite de antes: %s)" % (qual, _pq_apendice)
        antes_do_corte = heart_ai
        heart_ai = radai_geom.limitar_por_plano(heart_ai, "sup", marco,
                                                grade=grade)
        v_cortado = _cm3(antes_do_corte & ~heart_ai, grade)

        from scipy import ndimage as _ndi
        _rot, n_ped = _ndi.label(heart_ai)
        um = radai_geom.maior_componente(heart_ai)
        v_caiu = _cm3(heart_ai & ~um, grade)
        heart_ai = um
        if not heart_ai.any():
            _falar(log, u"coracao de radioterapia (Heart_ai): nada sobrou "
                        u"depois do plano — nao sai")
            return None

        v_fim = _cm3(heart_ai, grade)
        _falar(log, u"coracao de radioterapia: Heart_ai %.0f cm3 (mesclagem "
                    u"do motor %.0f cm3; com o pericardio corrigido; cortado "
                    u"acima do %s: -%.1f cm3; um volume: %d pedaco(s) a "
                    u"menos, -%.1f cm3). Entraram: %s%s"
               % (v_fim, v_motor, qual, v_cortado, max(0, n_ped - 1), v_caiu,
                  ", ".join(entrou),
                  (u". Faltaram: " + ", ".join(faltou)) if faltou else u""))
        descr = (u"Heart_ai: coracao de radioterapia montado a partir dos "
                 u"rotulos do TotalSegmentator (%s), fechamento de %.0f mm, "
                 u"recortado nos vizinhos e na aorta descendente, cortado "
                 u"acima do %s, buracos de cada corte preenchidos, um "
                 u"volume. Inclui o pericardio."
                 % (", ".join(entrou), float(E.FECHAMENTO_PERICARDIO_MM), qual))
        if derrame is not None:
            v_der = _cm3(heart_ai & derrame, grade)
            if v_der > 0:
                descr += (u" Inclui o derrame pericardico (PericardEff, %.1f "
                          u"cm3)." % v_der)
        return Construcao(CHAVE_CORACAO_AI, heart_ai, descr, entrou, faltou,
                          extras={"aorta_descendente": desc,
                                  "com_pericardio": True,
                                  "coracao_do_modelo": nome_cor})
    except Exception as e:
        _falar(log, u"nao consegui o Heart_ai (%s: %s) — o coracao sai como "
                    u"o modelo entregou" % (type(e).__name__, str(e)[:100]))
        return None


ORGAOS_FORA_DA_BAG = ("liver", "gallbladder", "urinary_bladder", "spleen",
                      "kidney_", "adrenal_gland_")
SUAVIZACAO_BAG_MM = 5.0

ORGAOS_DO_TORAX_FORA_DA_BAG = ("esophagus", "heart", "pericardium", "lung_")


_VIA_AEREA = ("trachea",)


def vasos_do_motor():
    return tuple(n for n in _motor().MARGEM_OAR_MM if n not in _VIA_AEREA)


def compostos_de_vaso():
    vasos = set(vasos_do_motor())
    return tuple(sorted(c for c, p in _motor().COMPOSTOS.items()
                        if p and all(x in vasos for x in p)))


def _vasos_para_tirar():
    return vasos_do_motor() + compostos_de_vaso()


def bag_bowel(masks, grade, log=None, cru=None, suavizar_mm=None):
    try:
        if grade is None:
            _falar(log, u"Bag_Bowel: nao sai — sem grade")
            return None
        mm = SUAVIZACAO_BAG_MM if suavizar_mm is None else float(suavizar_mm)
        cav = _exata(masks, "abdominal_cavity", cru)
        if not _tem(cav):
            _falar(log, u"Bag_Bowel: nao sai — a cavidade abdominal "
                        u"(`abdominal_cavity`) so existe na task "
                        u"`trunk_cavities`, e ela nao rodou nesta serie")
            return None
        tirar = uniao_por_nome(masks, ORGAOS_FORA_DA_BAG
                               + ORGAOS_DO_TORAX_FORA_DA_BAG, cru=cru)
        vasos = uniao_por_nome(masks, _vasos_para_tirar(), cru=cru)
        if _tem(vasos):
            tirar = vasos.copy() if tirar is None else (tirar | vasos)
        faltou = [rot for rot, pref in ((u"figado", ("liver",)),
                                        (u"vesicula", ("gallbladder",)),
                                        (u"bexiga", ("urinary_bladder",)),
                                        (u"baco", ("spleen",)),
                                        (u"rins", ("kidney_",)),
                                        (u"adrenais", ("adrenal_gland_",)))
                  if not _tem(uniao_por_nome(masks, pref, cru=cru))]
        bag = cav.copy()
        if tirar is not None:
            bag &= ~tirar
        if not bag.any():
            _falar(log, u"Bag_Bowel: nao sai — os orgaos tirados cobriam a "
                        u"cavidade inteira")
            return None
        v_sub = _cm3(bag, grade)
        bag = radai_geom.suavizar(bag, mm, grade)
        if tirar is not None:
            bag &= ~tirar
        bag &= cav
        from scipy import ndimage as _ndi
        _rot, n_ped = _ndi.label(bag)
        um = radai_geom.maior_componente(bag)
        v_caiu = _cm3(bag & ~um, grade)
        bag = um
        if not bag.any():
            _falar(log, u"Bag_Bowel: nada sobrou depois da suavizacao — nao "
                        u"sai")
            return None
        _falar(log, u"Bag_Bowel: %.0f cm3 (cavidade abdominal %.0f cm3; "
                    u"depois de tirar figado, vesicula, bexiga, baco, vasos, "
                    u"rins, adrenais e o que e do torax (esofago, coracao, "
                    u"pericardio, pulmao) %.0f cm3; suavizada %.1f mm e "
                    u"recortada de "
                    u"novo; um volume: %d pedaco(s) a menos, -%.1f cm3)%s"
               % (_cm3(bag, grade), _cm3(cav, grade), v_sub, mm,
                  max(0, n_ped - 1), v_caiu,
                  (u". Nao vieram nesta serie: " + ", ".join(faltou))
                  if faltou else u""))
        descr = (u"Bag_Bowel: cavidade abdominal da task trunk_cavities "
                 u"menos figado, vesicula, bexiga, baco, vasos, rins, "
                 u"adrenais, esofago, coracao, pericardio e pulmao; mantem "
                 u"alcas, pancreas e estomago; suavizada %.0f mm; um volume. "
                 u"Sobrepoe os orgaos abdominais." % mm)
        return Construcao(CHAVE_BAG_BOWEL, bag, descr,
                          entrou=[u"abdominal_cavity (trunk_cavities)"],
                          faltou=faltou)
    except Exception as e:
        _falar(log, u"nao consegui a Bag_Bowel (%s: %s)"
               % (type(e).__name__, str(e)[:100]))
        return None


# GUARDA: a receita da `bag_bowel` fica intocada (é a comparação da
# Bag_Bowel_OAR); o que ela contém e não desconta vai na descrição por aqui,
# e o que entra inteiro depois dela (INTEIROS_NA_BAG) também.
NAO_DESCONTADOS_DA_BAG = (("prostate", u"prostata"),)
INTEIROS_NA_BAG = (("pancreas", u"pancreas"),)


def bag_bowel_declarada(masks, grade, log=None, cru=None, suavizar_mm=None):
    c = bag_bowel(masks, grade, log=log, cru=cru, suavizar_mm=suavizar_mm)
    if not c:
        return c
    try:
        bag = _bool(c.mascara)
        for chave, rotulo in INTEIROS_NA_BAG:
            m = _exata(masks, chave, cru)
            if not _tem(m) or _bool(m).shape != bag.shape:
                continue
            ganho = _bool(m) & ~bag
            bag = bag | _bool(m)
            c.mascara = bag
            c.descricao = (u"%s O %s entra inteiro (+%.1f cm3 fora da "
                           u"cavidade ou da suavizacao)."
                           % (c.descricao, rotulo, _cm3(ganho, grade)))
            _falar(log, u"Bag_Bowel: o %s entra inteiro (+%.1f cm3)"
                   % (rotulo, _cm3(ganho, grade)))
    except Exception as e:
        _falar(log, u"Bag_Bowel: nao consegui juntar o que entra inteiro (%s)"
               % str(e)[:100])
    try:
        bag = _bool(c.mascara)
        for chave, rotulo in NAO_DESCONTADOS_DA_BAG:
            m = _exata(masks, chave, cru)
            if not _tem(m):
                continue
            v = _cm3(bag & _bool(m), grade)
            if v > 0:
                c.descricao = (u"%s Contem %.1f cm3 da %s, que nao e "
                               u"descontada." % (c.descricao, v, rotulo))
                _falar(log, u"Bag_Bowel: contem %.1f cm3 da %s (nao "
                            u"descontada; a descricao da ROI diz)"
                       % (v, rotulo))
    except Exception as e:
        _falar(log, u"Bag_Bowel: nao consegui medir o que ela contem (%s)"
               % str(e)[:100])
    return c




FATOR_DO_GLOBO = 0.5
OLHOS = {"eye_left": ("eye_lens_left", "left"),
         "eye_right": ("eye_lens_right", "right")}
VIZINHOS_DO_GLOBO = ("optic_nerve_", "rectus_", "oblique_",
                     "levator_palpebrae_", "skull")
DESCRICAO_DO_GLOBO = (u"Globo ocular: o olho do modelo unido ao cristalino, "
                      u"cavidades preenchidas, suavizado a meio caminho de uma "
                      u"esfera de mesmo volume (fator %g). Contem o Lens do "
                      u"mesmo lado (sobreposicao intencional)." % FATOR_DO_GLOBO)


def _esfera_de_mesmo_volume(g, grade):
    zz, yy, xx = np.nonzero(g)
    sp = np.asarray(grade.spacing, dtype=float)
    c = np.array([zz.mean(), yy.mean(), xx.mean()]) * sp
    vol = float(g.sum()) * float(np.prod(sp))
    r = (3.0 * vol / (4.0 * np.pi)) ** (1.0 / 3.0)
    idx = np.indices(g.shape, dtype=float)
    d2 = sum(((idx[i] * sp[i]) - c[i]) ** 2 for i in range(3))
    return d2 <= r * r


def globo_ocular(olho, cristalino, grade, vizinhos=None, fator=None):
    f = FATOR_DO_GLOBO if fator is None else float(fator)
    o = _bool(olho) if _tem(olho) else None
    if o is None:
        return None
    g = o.copy()
    if _tem(cristalino):
        g |= _bool(cristalino)
    g = radai_geom.preencher_buracos(g, por_fatia=False, triplanar=True)
    caixa = radai_geom._bbox_folgado(g, tuple(
        int(np.ceil(6.0 / s)) + 2 for s in grade.spacing))
    sub = g[caixa]
    sub_g = radai_geom.Grade(grade.spacing, grade.sentido)
    esfera = _esfera_de_mesmo_volume(sub, sub_g)
    d = (f * radai_geom.distancia_com_sinal(sub, sub_g)
         + (1.0 - f) * radai_geom.distancia_com_sinal(esfera, sub_g))
    g2 = np.zeros_like(g)
    g2[caixa] = d <= 0
    if _tem(vizinhos):
        g2 &= ~(_bool(vizinhos) & ~g)
    if _tem(cristalino):
        g2 |= _bool(cristalino)
    g2 = radai_geom.maior_componente(g2)
    return g2 if g2.any() else None


def olhos(masks, grade, log=None, cru=None):
    fora = {}
    for chave, (lente, _lado) in sorted(OLHOS.items()):
        try:
            olho = _exata(masks, chave, cru)
            if not _tem(olho):
                continue
            cris = _exata(masks, lente, cru)
            viz = uniao_por_nome(masks, VIZINHOS_DO_GLOBO, cru=cru)
            g = globo_ocular(olho, cris, grade, viz)
            if g is None:
                continue
            _falar(log, u"globo ocular %s: %.2f cm3 (olho do modelo %.2f, "
                        u"cristalino %.2f)" % (chave, _cm3(g, grade),
                                               _cm3(olho, grade),
                                               _cm3(cris, grade)))
            fora[chave] = Construcao(chave, g, DESCRICAO_DO_GLOBO,
                                     entrou=[chave, lente] if _tem(cris)
                                     else [chave],
                                     faltou=[] if _tem(cris)
                                     else [u"%s: sem cristalino" % chave])
        except Exception as e:
            _falar(log, u"globo ocular %s: %s: %s — sai como o modelo deu"
                   % (chave, type(e).__name__, str(e)[:100]))
    return fora


CHAVE_BAG_BOWEL_OAR = "bag_bowel_oar"
SUAVIZACAO_BAG_OAR_MM = 20.0
FOLGA_DOS_VIZINHOS_DA_BAG_MM = 5.0
RECUO_ATRAS_DO_PSOAS_MM = 20.0
EXTENSAO_DA_LOJA_RENAL_MM = {"ant": 5.0, "post": 30.0, "lat": 15.0,
                           "sup": 10.0, "inf": 10.0}
RECUO_ATRAS_DOS_GRANDES_VASOS_MM = 20.0
FOLGA_DO_CORPO_VERTEBRAL_MM = 3.0
ALCANCE_MESORRETAL_MM = 10.0
FAIXA_ANTERIOR_DO_SACRO_MM = 5.0
FAIXA_ANTERIOR_CAUDAL_MM = 50.0
CONFLITO_DE_COBERTURA_CM3 = 0.5
VEIA_PORTA = ("portal_vein_and_splenic_vein",)
ORGAOS_FORA_DA_BAG_OAR = ("prostate",)
MUSCULOS_FORA_DA_BAG_OAR = ("iliopsoas_", "psoas", "quadratus_lumborum",
                            "gluteus_", "autochthon", "erector_spinae",
                            "rectus_abdominis", "external_oblique",
                            "internal_oblique", "transversus", "piriformis",
                            "obturator", "levator_ani")
OSSOS_FORA_DA_BAG_OAR = ("vertebrae_", "sacrum", "hip_", "femur_", "coccyx")
CONSTRUCOES_FORA_DA_BAG_OAR = ("Skin",)
ILIOPSOAS = ("iliopsoas_",)
BACO = ("spleen",)
PSOAS = ("iliopsoas_", "psoas")
LOJA_RENAL = ("kidney_", "adrenal_gland_")
GRANDES_VASOS_DO_RETROPERITONIO = ("aorta", "inferior_vena_cava",
                                   "iliac_artery_", "iliac_vena_")
ALCAS_DA_BAG_OAR = (("delgado", ("small_intestine", "small_bowel")),
                    ("colon", ("colon",)),
                    ("duodeno", ("duodenum",)),
                    ("estomago", ("stomach",)),
                    ("pancreas", ("pancreas",)))
INTEIROS_DEPOIS_DA_SUAVIZACAO = ("delgado", "duodeno", "estomago", "pancreas")
DESCRICAO_DA_BAG_OAR = (
    u"Bag_Bowel_OAR: cavidade abdominal menos figado, "
    u"vesicula, bexiga, prostata, baco, rins, adrenais, orgaos do torax, "
    u"vasos, musculos (psoas +%g mm atras), ossos e pele; menos %g mm de "
    u"grandes veias, grandes arterias, iliopsoas e baco; menos loja "
    u"perirrenal, retroperitonio atras dos grandes vasos, mesorreto (reto +%g "
    u"mm ate o sacro) e, abaixo da borda inferior da sacroiliaca (sem ela, da "
    u"cabeca femoral), o que passa de %g mm da parede anterior. Veia porta "
    u"fora de toda conta. Suavizada %g mm; depois, estomago, duodeno, "
    u"pancreas e delgado inteiros e colon sem reto; um volume. Ref. Orton "
    u"2022 doi:10.1016/j.adro.2022.101031 (exclui estomago e pancreas)."
    % (RECUO_ATRAS_DO_PSOAS_MM, FOLGA_DOS_VIZINHOS_DA_BAG_MM,
       ALCANCE_MESORRETAL_MM, FAIXA_ANTERIOR_CAUDAL_MM,
       SUAVIZACAO_BAG_OAR_MM))


def _sem_a_porta(nomes):
    return tuple(n for n in nomes
                 if not radai_names.casa_prefixo(n, VEIA_PORTA))


def vasos_da_bag_oar():
    E = _motor()
    com_porta = set(c for c, partes in E.COMPOSTOS.items()
                    if any(p in VEIA_PORTA for p in (partes or ())))
    return _sem_a_porta(tuple(vasos_do_motor())
                        + tuple(c for c in compostos_de_vaso()
                                if c not in com_porta))


def vizinhos_com_margem_da_bag():
    E = _motor()
    partes = []
    for comp in ("great_veins", "great_arteries"):
        for p in E.COMPOSTOS.get(comp) or ():
            if p not in partes:
                partes.append(p)
    return _sem_a_porta(tuple(partes)) + ILIOPSOAS + BACO


def exclusoes_duras_da_bag_oar(masks, cru=None, construidas=None):
    nomes = (ORGAOS_FORA_DA_BAG + ORGAOS_DO_TORAX_FORA_DA_BAG
             + ORGAOS_FORA_DA_BAG_OAR + vasos_da_bag_oar()
             + MUSCULOS_FORA_DA_BAG_OAR + OSSOS_FORA_DA_BAG_OAR
             + CONSTRUCOES_FORA_DA_BAG_OAR)
    h = uniao_por_nome(masks, nomes, cru=cru)
    for k, m in sorted((construidas or {}).items()):
        if (radai_names.casa_prefixo(k, CONSTRUCOES_FORA_DA_BAG_OAR
                                     + ORGAOS_DO_TORAX_FORA_DA_BAG)
                and _tem(m)):
            h = _bool(m).copy() if h is None else (h | _bool(m))
    return h


def margem_dos_vizinhos_da_bag(masks, grade, cru=None):
    viz = uniao_por_nome(masks, vizinhos_com_margem_da_bag(), cru=cru)
    if not _tem(viz):
        return None
    return radai_geom.expandir(_bool(viz), FOLGA_DOS_VIZINHOS_DA_BAG_MM,
                               grade)


def _hull_por_corte(pontos_bool):
    from scipy.spatial import ConvexHull, Delaunay
    ys, xs = np.nonzero(pontos_bool)
    if ys.size < 3:
        return pontos_bool.copy()
    pts = np.c_[ys, xs].astype(float)
    try:
        hull = ConvexHull(pts)
        tri = Delaunay(pts[hull.vertices])
    except Exception:
        return pontos_bool.copy()
    y0, y1, x0, x1 = ys.min(), ys.max(), xs.min(), xs.max()
    gy, gx = np.mgrid[y0:y1 + 1, x0:x1 + 1]
    dentro = tri.find_simplex(np.c_[gy.ravel(), gx.ravel()].astype(float),
                              tol=1e-9) >= 0
    fora = pontos_bool.copy()
    fora[y0:y1 + 1, x0:x1 + 1] |= dentro.reshape(gy.shape)
    return fora


def compartimento_mesorretal(reto, sacro, grade):
    from radai_skin import _para_canonico, _de_canonico, _espacamento_canonico
    if not _tem(reto):
        return None
    r = _bool(reto)
    rd = radai_geom.expandir(r, ALCANCE_MESORRETAL_MM, grade)
    cr = _para_canonico(r, grade)
    crd = _para_canonico(rd, grade)
    cs = _para_canonico(_bool(sacro), grade) if _tem(sacro) else None
    _sz, sy, _sx = _espacamento_canonico(grade)
    faixa = int(round(FAIXA_ANTERIOR_DO_SACRO_MM / sy))
    out = np.zeros(cr.shape, dtype=bool)
    for z in np.flatnonzero(cr.any(axis=(1, 2))):
        u = crd[z].copy()
        if cs is not None and cs[z].any():
            s = cs[z]
            ymin = np.where(s.any(axis=0), s.argmax(axis=0), 10 ** 9)
            yy = np.arange(s.shape[0])[:, None]
            u |= s & (yy <= ymin[None, :] + faixa)
        h = _hull_por_corte(u)
        y_ant = int(np.flatnonzero(cr[z].any(axis=1)).min())
        h[:y_ant, :] = False
        out[z] = h
    return _de_canonico(out, grade)


MARCO_CAUDAL_SACROILIACA = u"borda inferior da articulacao sacroiliaca"
MARCO_CAUDAL_FEMUR = u"polo superior da cabeca femoral"
NOTA_DO_CAUDAL_PELO_FEMUR = u"caudal pela cabeca femoral (sem a sacroiliaca)"
NOTA_SEM_CAUDAL = u"sem sacroiliaca nem femur, caudal nao cortado"


def juncao_sacroiliaca(masks, grade, cru=None):
    E = _motor()
    for fonte in (masks, cru):
        if fonte is None:
            continue
        try:
            j = fonte.get(E.NOME_JUNCAO_SI) if hasattr(fonte, "get") else None
        except Exception:
            j = None
        if _tem(j):
            return _bool(j)
    try:
        sac = uniao_por_nome(masks, ("sacrum",), cru=cru, exato=True)
        qua = uniao_por_nome(masks, ("hip_left", "hip_right"), cru=cru,
                             exato=True)
        if not _tem(sac) or not _tem(qua):
            return None
        j = E.desenhar_juncao_sacroiliaca({"sacrum": sac, "hip_left": qua},
                                          grade)
    except Exception:
        return None
    return _bool(j) if _tem(j) else None


def marco_caudal(masks, grade, cru=None):
    from radai_skin import _para_canonico
    j = juncao_sacroiliaca(masks, grade, cru)
    if _tem(j):
        cj = _para_canonico(j, grade)
        return (int(np.flatnonzero(cj.any(axis=(1, 2))).min()),
                MARCO_CAUDAL_SACROILIACA, None)
    fem = uniao_por_nome(masks, ("femur_left", "femur_right"), cru=cru,
                         exato=True)
    if _tem(fem):
        cf = _para_canonico(_bool(fem), grade)
        return (int(np.flatnonzero(cf.any(axis=(1, 2))).max()),
                MARCO_CAUDAL_FEMUR, NOTA_DO_CAUDAL_PELO_FEMUR)
    return None, None, NOTA_SEM_CAUDAL


def caudal_posterior(cav, z_limite, grade):
    from radai_skin import _para_canonico, _de_canonico, _espacamento_canonico
    if z_limite is None or not _tem(cav):
        return None
    cc = _para_canonico(_bool(cav), grade)
    _sz, sy, _sx = _espacamento_canonico(grade)
    faixa = int(round(FAIXA_ANTERIOR_CAUDAL_MM / sy))
    out = np.zeros(cc.shape, dtype=bool)
    yy = np.arange(cc.shape[1])[:, None]
    for z in range(0, min(int(z_limite), cc.shape[0] - 1) + 1):
        c = cc[z]
        if not c.any():
            continue
        ymin = np.where(c.any(axis=0), c.argmax(axis=0), 10 ** 9)
        out[z] = c & (yy > ymin[None, :] + faixa)
    return _de_canonico(out, grade)


def exclusoes_moles_da_bag_oar(masks, cav, grade, cru=None):
    s = np.zeros(cav.shape, dtype=bool)
    notas = []
    viz = margem_dos_vizinhos_da_bag(masks, grade, cru)
    if viz is not None:
        s |= viz
    ps = uniao_por_nome(masks, PSOAS, cru=cru)
    if _tem(ps):
        s |= radai_geom.expandir(ps, {"post": RECUO_ATRAS_DO_PSOAS_MM},
                                 grade)
    loja = uniao_por_nome(masks, LOJA_RENAL, cru=cru)
    if _tem(loja):
        s |= radai_geom.expandir(loja, EXTENSAO_DA_LOJA_RENAL_MM, grade)
    gv = uniao_por_nome(masks, GRANDES_VASOS_DO_RETROPERITONIO, cru=cru)
    if _tem(gv):
        s |= radai_geom.expandir(
            gv, {"post": RECUO_ATRAS_DOS_GRANDES_VASOS_MM}, grade)
    osso = uniao_por_nome(masks, ("vertebrae_", "sacrum"), cru=cru)
    if _tem(osso):
        s |= radai_geom.expandir(osso, FOLGA_DO_CORPO_VERTEBRAL_MM, grade)
    reto = _exata(masks, "rectum", cru)
    sac = uniao_por_nome(masks, ("sacrum", "coccyx"), cru=cru)
    meso = compartimento_mesorretal(reto, sac, grade)
    if meso is None:
        notas.append(u"sem Rectum_ai, compartimento mesorretal nao aplicado")
    else:
        s |= meso
    z_lim, _marco, nota = marco_caudal(masks, grade, cru)
    cau = caudal_posterior(cav, z_lim, grade)
    if nota:
        notas.append(nota)
    if cau is not None:
        s |= cau
    return s, notas


def _alcas(masks, cru=None):
    fora = []
    for rot, nomes in ALCAS_DA_BAG_OAR:
        m = uniao_por_nome(masks, nomes, cru=cru, exato=True)
        if _tem(m):
            fora.append((rot, _bool(m)))
    return fora


NOTA_DO_COLON_SEM_RETO = (u"o reto nao foi separado: abaixo do marco caudal "
                          u"o colon so volta na faixa anterior, %.1f cm3 "
                          u"fora")
NOTA_DO_COLON_INTEIRO = u"o reto nao foi separado: colon inteiro, reto incluido"


def _alcas_que_voltam(masks, cav, grade, cru=None):
    lista = _alcas(masks, cru)
    if not lista:
        return None, None, None, None
    inteiros = None
    for r, b in lista:
        if r in INTEIROS_DEPOIS_DA_SUAVIZACAO:
            inteiros = b.copy() if inteiros is None else (inteiros | b)
    colon = dict(lista).get("colon")
    if colon is None or _tem(_exata(masks, "rectum", cru)):
        return inteiros, colon, None, None
    z_lim, _marco, _nota = marco_caudal(masks, grade, cru)
    cau = caudal_posterior(cav, z_lim, grade) if _tem(cav) else None
    if cau is None:
        return inteiros, colon, None, NOTA_DO_COLON_INTEIRO
    retido = colon & _bool(cau)
    if not retido.any():
        return inteiros, colon, None, None
    return (inteiros, colon & ~retido, retido,
            NOTA_DO_COLON_SEM_RETO % _cm3(retido, grade))


def cobertura_da_bag_oar(bag, masks, grade, duras=None, cru=None,
                         colon_retido=None):
    cob, conf = {}, []
    for rot, b in _alcas(masks, cru):
        if rot == "colon" and _tem(colon_retido):
            b = b & ~_bool(colon_retido)
        n = int(b.sum())
        cob[rot] = int((b & bag).sum()) / float(n) if n else 1.0
        fora_cm3 = _cm3(b & ~bag, grade)
        if fora_cm3 > CONFLITO_DE_COBERTURA_CM3:
            sobre = (_cm3(b & ~bag & _bool(duras), grade)
                     if _tem(duras) else 0.0)
            motivo = (u"sobre exclusao dura" if sobre >= fora_cm3 / 2.0
                      else u"em pedaco que o um volume descartou")
            conf.append((rot, round(fora_cm3, 2), motivo))
    return cob, conf


def descricao_da_bag_oar(cob, conf, notas):
    texto = DESCRICAO_DA_BAG_OAR + u" Cobertura: %s." % (
        u", ".join(u"%s %.0f%%" % (r, 100.0 * cob[r])
                   for r, _n in ALCAS_DA_BAG_OAR if r in cob)
        or u"sem alcas")
    extra = list(notas or ())
    if conf:
        extra.append(u"Conflito: %.1f cm3 de alca fora (revisar)"
                     % sum(c[1] for c in conf))
    if extra:
        texto += u" Nesta serie: %s." % u"; ".join(extra)
    return texto


def reaplicar_exclusoes(bag, livre):
    return bag & livre


def _devolver_alcas(bag, inteiros, colon, cav, h):
    if inteiros is not None:
        bag = bag | inteiros
    if colon is not None:
        bag = bag | (colon & ~h if cav is None else (colon & cav & ~h))
    return bag


def bag_bowel_oar(masks, grade, log=None, cru=None, construidas=None):
    try:
        if grade is None:
            _falar(log, u"Bag_Bowel_OAR: nao sai — sem grade")
            return None
        cav = _exata(masks, "abdominal_cavity", cru)
        if not _tem(cav):
            _falar(log, u"Bag_Bowel_OAR: nao sai — a cavidade abdominal "
                        u"(`abdominal_cavity`) so existe na task "
                        u"`trunk_cavities`, e ela nao rodou nesta serie")
            return None
        cav = _bool(cav)
        duras = exclusoes_duras_da_bag_oar(masks, cru, construidas)
        h = np.zeros(cav.shape, bool) if duras is None else _bool(duras)
        s, notas = exclusoes_moles_da_bag_oar(masks, cav, grade, cru)
        livre = cav & ~h & ~s
        if not livre.any():
            _falar(log, u"Bag_Bowel_OAR: nao sai — as exclusoes cobriam a "
                        u"cavidade inteira")
            return None
        bag = radai_geom.suavizar(livre, SUAVIZACAO_BAG_OAR_MM, grade)
        bag = reaplicar_exclusoes(bag, livre)
        inteiros, colon, retido, nota_colon = _alcas_que_voltam(
            masks, cav, grade, cru)
        if nota_colon:
            notas.append(nota_colon)
        bag = _devolver_alcas(bag, inteiros, colon, cav, h)
        from scipy import ndimage as _ndi
        n_ped = int(_ndi.label(bag)[1])
        um = radai_geom.maior_componente(bag, conectividade=1)
        caiu = bag & ~um
        bag = um
        if not bag.any():
            _falar(log, u"Bag_Bowel_OAR: nada sobrou — nao sai")
            return None
        cob, conf = cobertura_da_bag_oar(bag, masks, grade, h, cru,
                                         colon_retido=retido)
        _alca = None
        for _m in (inteiros, colon):
            if _m is not None:
                _alca = _m.copy() if _alca is None else (_alca | _m)
        _falar(log, u"Bag_Bowel_OAR: %.0f cm3 (cavidade %.0f cm3; livre %.0f "
                    u"cm3; um volume: %d pedaco(s) a menos, -%.1f cm3, %.1f "
                    u"cm3 de alca)%s%s"
               % (_cm3(bag, grade), _cm3(cav, grade), _cm3(livre, grade),
                  max(0, n_ped - 1), _cm3(caiu, grade),
                  _cm3(caiu & _alca, grade) if _alca is not None else 0.0,
                  (u". " + u"; ".join(notas)) if notas else u"",
                  u"".join(u". CONFLITO: %s %.1f cm3 fora (%s)" % c
                           for c in conf)))
        return Construcao(CHAVE_BAG_BOWEL_OAR, bag,
                          descricao_da_bag_oar(cob, conf, notas),
                          entrou=[u"abdominal_cavity (trunk_cavities)"],
                          faltou=list(notas),
                          extras={"duras": h, "moles": s, "cobertura": cob,
                                  "conflitos": conf})
    except Exception as e:
        _falar(log, u"nao consegui a Bag_Bowel_OAR (%s: %s)"
               % (type(e).__name__, str(e)[:100]))
        return None


def acabamento_da_bag_oar(bag, masks, grade, log=None):
    bag = _bool(bag)
    duras = exclusoes_duras_da_bag_oar(masks)
    h = np.zeros(bag.shape, bool) if duras is None else _bool(duras)
    viz = margem_dos_vizinhos_da_bag(masks, grade)
    fora = h if viz is None else (h | _bool(viz))
    cav = _exata(masks, "abdominal_cavity")
    cav = _bool(cav) if _tem(cav) else None
    inteiros, colon, retido, nota_colon = _alcas_que_voltam(masks, cav, grade)
    novo = _devolver_alcas(bag & ~fora, inteiros, colon, cav, h)
    novo = radai_geom.maior_componente(novo, conectividade=1)
    if not novo.any():
        novo = bag
    cob, conf = cobertura_da_bag_oar(novo, masks, grade, h,
                                     colon_retido=retido)
    notas = []
    if not _tem(_exata(masks, "rectum")):
        notas.append(u"sem Rectum_ai, compartimento mesorretal nao aplicado")
    _z, _marco, nota = marco_caudal(masks, grade)
    if nota:
        notas.append(nota)
    if nota_colon:
        notas.append(nota_colon)
    for c in conf:
        _falar(log, u"   Bag_Bowel_OAR: CONFLITO: %s %.1f cm3 fora (%s)" % c)
    return novo, descricao_da_bag_oar(cob, conf, notas), cob, conf


CRISTAS_ILIACAS = {"iliac_crest_left": ("hip_left", "femur_left", u"L"),
                   "iliac_crest_right": ("hip_right", "femur_right", u"R")}
SACRO_FORA_DA_CRISTA = ("sacrum",)
DESCRICAO_DA_CRISTA = (
    u"IliacCrest_%s: o osso do quadril do lado (Bone_Pelvic_%s do FULL) menos "
    u"o sacro e menos a porcao do corte mais cranial em que aparece o femur "
    u"do mesmo lado, inclusive, para caudal. Recorte do FULL: nenhum modelo "
    u"novo.")
NOTA_DA_CRISTA_SEM_FEMUR = (
    u"sem femur do lado no campo, e o quadril encosta na borda caudal da "
    u"serie: a serie termina acima da cabeca femoral, e nada foi cortado "
    u"embaixo")

CHAVE_ANUS = "anus"
QUADRIS = ("hip_left", "hip_right")
DESCRICAO_DO_ANUS = (
    u"Anus: a Bag_Bowel_ai do FULL do ultimo corte inferior do osso pelvico "
    u"(o mais caudal entre o quadril esquerdo e o direito), inclusive, para "
    u"baixo. Recorte do FULL: nenhum modelo novo.")


def _cortes_canonicos(m, grade):
    from radai_skin import _para_canonico
    c = _para_canonico(_bool(m), grade)
    return np.flatnonzero(c.any(axis=(1, 2)))


def crista_iliaca(masks, grade, chave, log=None, cru=None):
    from radai_skin import _para_canonico, _de_canonico
    quadril, femur, lado = CRISTAS_ILIACAS[chave]
    nome = u"IliacCrest_%s" % lado
    if grade is None:
        return Construcao(chave, None, u"", faltou=[u"%s: sem grade" % nome])
    q = _exata(masks, quadril, cru)
    if not _tem(q):
        return Construcao(chave, None, u"",
                          faltou=[u"%s: sem %s nesta serie" % (nome, quadril)])
    crista = _bool(q).copy()
    sac = uniao_por_nome(masks, SACRO_FORA_DA_CRISTA, cru=cru, exato=True)
    if _tem(sac) and _bool(sac).shape == crista.shape:
        crista &= ~_bool(sac)
    nota = None
    f = _exata(masks, femur, cru)
    cq = _para_canonico(crista, grade).copy()
    if _tem(f) and _bool(f).shape == crista.shape:
        zf = _cortes_canonicos(f, grade)
        cq[:int(zf.max()) + 1] = False
    else:
        zq = _cortes_canonicos(q, grade)
        if not zq.size or int(zq.min()) > 0:
            return Construcao(chave, None, u"", faltou=[
                u"%s: sem %s nesta serie, com o quadril inteiro no campo — "
                u"o recorte do acetabulo nao tem marco" % (nome, femur)])
        nota = NOTA_DA_CRISTA_SEM_FEMUR
    m = _de_canonico(cq, grade)
    if not m.any():
        return Construcao(chave, None, u"", faltou=[
            u"%s: nada do quadril fica acima do femur" % nome])
    descr = DESCRICAO_DA_CRISTA % (lado, lado)
    if nota:
        descr = u"%s Nesta serie: %s." % (descr, nota)
    _falar(log, u"%s: %.1f cm3 (do quadril, %.1f cm3)%s"
           % (nome, _cm3(m, grade), _cm3(q, grade),
              (u"; " + nota) if nota else u""))
    return Construcao(chave, m, descr, entrou=[quadril],
                      faltou=[nota] if nota else [])


def cristas_iliacas(masks, grade, log=None, cru=None):
    return dict((k, crista_iliaca(masks, grade, k, log=log, cru=cru))
                for k in sorted(CRISTAS_ILIACAS))


def anus(masks, grade, log=None, cru=None, bag=None):
    from radai_skin import _para_canonico, _de_canonico
    if grade is None:
        return Construcao(CHAVE_ANUS, None, u"", faltou=[u"Anus: sem grade"])
    if bag is None:
        bag = _exata(masks, CHAVE_BAG_BOWEL, cru)
    if not _tem(bag):
        return Construcao(CHAVE_ANUS, None, u"", faltou=[
            u"Anus: sem a Bag_Bowel_ai nesta serie"])
    qs = uniao_por_nome(masks, QUADRIS, cru=cru, exato=True)
    if not _tem(qs) or _bool(qs).shape != _bool(bag).shape:
        return Construcao(CHAVE_ANUS, None, u"", faltou=[
            u"Anus: sem o osso do quadril nesta serie"])
    zq = _cortes_canonicos(qs, grade)
    z_baixo = int(zq.min())
    if z_baixo <= 0:
        return Construcao(CHAVE_ANUS, None, u"", faltou=[
            u"Anus: o osso pelvico encosta na borda caudal da serie — o fim "
            u"dele nao esta no campo"])
    cb = _para_canonico(_bool(bag), grade).copy()
    cb[z_baixo + 1:] = False
    m = _de_canonico(cb, grade)
    if not m.any():
        return Construcao(CHAVE_ANUS, None, u"", faltou=[
            u"Anus: a Bag_Bowel_ai nao desce ate o ultimo corte do osso "
            u"pelvico"])
    _falar(log, u"Anus: %.1f cm3 (a Bag_Bowel_ai do ultimo corte do osso "
                u"pelvico para baixo)" % _cm3(m, grade))
    return Construcao(CHAVE_ANUS, m, DESCRICAO_DO_ANUS,
                      entrou=[CHAVE_BAG_BOWEL])
