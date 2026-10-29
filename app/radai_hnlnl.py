# -*- coding: utf-8 -*-
import os

VERSAO = "1.0"

SUFIXO = "_lnl"
INFIXO = "HNL_"
ROTULO_TPS = "AI_LNL_cervical"

MAPA_DOS_PESOS = {
    1: "Ia", 2: "Ib_L", 3: "Ib_R", 4: "II_L", 5: "II_R", 6: "III_L",
    7: "III_R", 8: "IVa_L", 9: "IVa_R", 10: "IVb_L", 11: "IVb_R", 12: "V_L",
    13: "V_R", 14: "VIa", 15: "VIb", 16: "VIIa", 17: "VIIb_L", 18: "VIIb_R",
    19: "VIII_L", 20: "VIII_R",
}

VERSAO_DOS_PESOS = {
    "release": "nnUnet_model_export",
    "tarefa": "Task110_HNLNFixed_MirrorBest",
    "plans_sha256": ("9e5a6de4f5edb8acf936cc2697fd91e6"
                     "c03c8888a0ddc6eae093937c9ad4eaa9"),
    "fold0_bytes": 246413947,
    "fold0_bytes_enxuto": 123319408,
}

# GUARDA: o nome sai daqui e de mais lugar nenhum; `nome_clinico` o leva
# intacto ao `_ai` (12 a 13 caracteres, abaixo do limite de 16).
NOMES_DO_AUTOR = dict((i, "Lvl_" + n) for i, n in MAPA_DOS_PESOS.items())

NOME_DA_UNIAO = "LNL_UNION"
NOME_DA_UNIAO_NEUTRA = "LNL_Union"

ROTULOS_DA_UNIAO = tuple(range(1, 19))
INDICE_DO_VIII = {"left": 19, "right": 20}
PAROTIDAS_DO_VIII = {"left": "parotid_lnl_left", "right": "parotid_lnl_right"}
PAROTIDAS_DO_TS = {"left": "parotid_gland_left", "right": "parotid_gland_right"}
ECM_DO_FULL = {"left": "sternocleidomastoid_left",
               "right": "sternocleidomastoid_right"}

CHAVES_NO_OAR = (NOME_DA_UNIAO,) + tuple(sorted(PAROTIDAS_DO_VIII.values()))

CLAVICULA_DO_IVB = {"Lvl_IVb_L": "clavicula_left",
                    "Lvl_IVb_R": "clavicula_right"}
LADO_DA_CLAVICULA = {"clavicula_left": u"esquerda",
                     "clavicula_right": u"direita"}

FORA_DA_UNIAO = (
    "mandible",
    "anterior_scalene_left", "anterior_scalene_right",
    "middle_scalene_left", "middle_scalene_right",
    "posterior_scalene_left", "posterior_scalene_right",
    "clavicula_left", "clavicula_right", "hyoid",
)


def _clavicula_final(masks, chave, forma):
    import numpy as np
    b = masks.get(chave) if hasattr(masks, "get") else None
    if b is None:
        return None
    b = np.asarray(b)
    b = b if b.dtype == bool else b.astype(bool)
    return b if b.shape == tuple(forma) and b.any() else None


def acabamento_do_ivb(nome, m, masks, grade, log=None):
    import numpy as np
    m = np.asarray(m, dtype=bool)
    chave = CLAVICULA_DO_IVB.get(str(nome))
    clav = _clavicula_final(masks, chave, m.shape) if chave else None
    if clav is None or not (m & clav).any():
        return None, None, {}
    vx = float(np.prod(grade.spacing)) / 1000.0
    cm3 = int((m & clav).sum()) * vx
    _dizer(log, u"   `%s`: sem a clavicula %s do mesmo lado, antes da uniao "
                u"(-%.2f cm3)" % (nome, LADO_DA_CLAVICULA[chave], cm3))
    return m & ~clav, None, {"clavicula_tirada_cm3": round(cm3, 2)}


def acabamento_da_uniao_sem_a_clavicula(ivb_crus, descricao_original=None):
    def _acabamento(nome, m, masks, grade, log=None):
        import numpy as np
        m = np.asarray(m, dtype=bool)
        sai, partes = None, []
        for n_ivb, chave in sorted(CLAVICULA_DO_IVB.items()):
            ivb = (ivb_crus or {}).get(n_ivb)
            clav = _clavicula_final(masks, chave, m.shape)
            if ivb is None or clav is None:
                continue
            ivb = np.asarray(ivb, dtype=bool)
            if ivb.shape != m.shape:
                continue
            s = m & ivb & clav
            if s.any():
                sai = s if sai is None else (sai | s)
                partes.append((n_ivb, LADO_DA_CLAVICULA[chave],
                               int(s.sum())))
        import radai_names
        descricao = ((descricao_original or descricao_da_uniao(
            nome == NOME_DA_UNIAO))
                     + u" Sem as interseccoes com mandibula, escalenos "
                     u"anteriores, medios e posteriores, claviculas e hioide "
                     u"das mascaras finais. Mantidas as interseccoes com "
                     u"esternocleidomastoideos e platismas.")
        fora = []
        for chave in sorted(masks or {}):
            if radai_names.casa_prefixo(chave, FORA_DA_UNIAO) is None:
                continue
            b = np.asarray(masks[chave], dtype=bool)
            if b.shape != m.shape:
                continue
            inter = m & b
            if inter.any():
                sai = inter.copy() if sai is None else (sai | inter)
                fora.append(str(chave))
        if sai is None:
            return None, descricao, {}
        vx = float(np.prod(grade.spacing)) / 1000.0
        tirados = round(int(sai.sum()) * vx, 2)
        _dizer(log, u"   `%s`: sem a interseccao com musculos e ossos "
                    u"adjacentes nas mascaras finais (-%.2f cm3; %s)"
               % (nome, tirados, u", ".join(fora)))
        return m & ~sai, descricao, {"vizinhos_tirados_cm3": tirados,
                                "vizinhos": fora,
                                "clavicula_tirada_cm3": round(
                                    sum(k for _n, _lado, k in partes) * vx, 2)}
    return _acabamento


NIVEIS = dict(
    (i, {"indice": i, "candidato": MAPA_DOS_PESOS[i], "confirmado": True,
         "quem_confirmou": u"mapa dos pesos (%s)"
                           % VERSAO_DOS_PESOS["tarefa"],
         "quando": VERSAO_DOS_PESOS["release"]})
    for i in range(1, 21))

# GUARDA: significa "mapa fixado pela versão dos pesos"; sem a versão
# (`fixado` falso) os neutros voltam, série a série.
ORDEM_CONFERIDA = True

CONJUNTO_DO_MODELO = {
    "impares": ("Ia", "VIa", "VIb", "VIIa"),
    "bilaterais": ("Ib", "II", "III", "IVa", "IVb", "V", "VIIb", "VIII"),
    "divisao": (u"Weissmann T, Huang Y, Fischer S, et al. (ultimo autor: "
                u"Putz F). Deep learning for automatic head and neck lymph "
                u"node level delineation provides expert-level accuracy. "
                u"Front Oncol 2023;13:1115258 (PMC9978473)"),
    "referencia": (u"Grégoire V, Ang K, Budach W, et al. Delineation of the "
                   u"neck node levels for head and neck tumors: a 2013 update. "
                   u"DAHANCA, EORTC, HKNPCSG, NCIC CTG, NCRI, RTOG, TROG "
                   u"consensus guidelines. Radiother Oncol 2014;110(1):172-81"),
}

# GUARDA: a ordem craniocaudal dos oito bilaterais, pelos limites de
# `gregoire2014` (a ancora da bibliografia); nao nomeia nada, o nome vem do
# mapa dos pesos.
ORDEM_BILATERAL = ("VIIb", "VIII", "II", "Ib", "III", "V", "IVa", "IVb")

POSTERIOR_DA_LINHA_MEDIA = "VIIa"
ANTERIORES_DA_LINHA_MEDIA = ("Ia", "VIa", "VIb")

# GUARDA: o descritor vai so na descricao da ROI; o nome vem do mapa dos
# pesos.
DESCRITOR_DO_NIVEL = {
    "Ia": u"submentoniano",
    "Ib": u"submandibular",
    "II": u"jugular superior",
    "III": u"jugular media",
    "IVa": u"jugular inferior",
    "IVb": u"supraclavicular medial",
    "V": u"triangulo posterior",
    "VIa": u"jugular anterior",
    "VIb": u"pre-laringeo/pre-traqueal/paratraqueal",
    "VIIa": u"retrofaringeo",
    "VIIb": u"retroestiloide",
    "VIII": u"parotideo",
}

PARES_DE_LADO = ((2, 3), (4, 5), (6, 7), (8, 9), (10, 11), (12, 13),
                 (17, 18), (19, 20))

_CORES_POR_NIVEL = {
    "Ia": ([77, 182, 235], None),
    "Ib": ([255, 202, 97], [184, 138, 48]),
    "II": ([229, 97, 255], [161, 48, 184]),
    "III": ([97, 176, 255], [48, 116, 184]),
    "IVa": ([255, 150, 97], [184, 93, 48]),
    "IVb": ([97, 242, 255], [48, 173, 184]),
    "V": ([255, 97, 163], [184, 48, 104]),
    "VIa": ([77, 235, 104], None),
    "VIb": ([117, 77, 235], None),
    "VIIa": ([169, 235, 77], None),
    "VIIb": ([97, 110, 255], [48, 59, 184]),
    "VIII": ([0, 221, 160], [0, 176, 128]),
}


def _cores():
    fora = {}
    for i, n in MAPA_DOS_PESOS.items():
        raiz, lado = (n[:-2], n[-2:]) if n.endswith(("_L", "_R")) else (n, "")
        claro, escuro = _CORES_POR_NIVEL[raiz]
        fora[NOMES_DO_AUTOR[i]] = list(escuro if lado == "_R" else claro)
    fora[PAROTIDAS_DO_VIII["left"]] = list(_CORES_POR_NIVEL["VIII"][0])
    fora[PAROTIDAS_DO_VIII["right"]] = list(_CORES_POR_NIVEL["VIII"][1])
    fora[NOME_DA_UNIAO] = [210, 210, 210]
    return fora


CORES_DOS_NIVEIS = _cores()

CORES_DA_PAROTIDA_TS = {PAROTIDAS_DO_TS["left"]: [110, 170, 150],
                        PAROTIDAS_DO_TS["right"]: [90, 140, 125]}


def cor_do_nivel(chave, sufixo=None):
    k = str(chave)
    if sufixo == "_ts" and k in CORES_DA_PAROTIDA_TS:
        return list(CORES_DA_PAROTIDA_TS[k])
    c = CORES_DOS_NIVEIS.get(k)
    return list(c) if c else None




def fixado(base):
    import hashlib
    import pickle
    try:
        with open(os.path.join(str(base), "plans.pkl"), "rb") as f:
            dados = f.read()
    except Exception as e:
        return False, u"sem o plans.pkl dos pesos (%s)" % type(e).__name__
    if hashlib.sha256(dados).hexdigest() != VERSAO_DOS_PESOS["plans_sha256"]:
        return False, (u"o plans.pkl instalado nao e o da versao do mapa "
                       u"(%s)" % VERSAO_DOS_PESOS["tarefa"])
    try:
        classes = [int(c) for c in (pickle.loads(dados).get("all_classes")
                                    or [])]
    except Exception as e:
        return False, u"nao li as classes do plans.pkl (%s)" % type(e).__name__
    if classes != list(range(1, 21)):
        return False, (u"o plans.pkl declara as classes %s, e o mapa e de 1 a "
                       u"20" % classes[:24])
    ck = os.path.join(str(base), "fold_0", "model_final_checkpoint.model")
    try:
        tam = os.path.getsize(ck)
    except OSError:
        return False, u"sem o checkpoint do fold 0"
    if tam not in (VERSAO_DOS_PESOS["fold0_bytes"],
                   VERSAO_DOS_PESOS.get("fold0_bytes_enxuto")):
        return False, (u"o checkpoint do fold 0 tem %d bytes, e o da versao do "
                       u"mapa tem %d (%s sem o estado do otimizador)"
                       % (tam, VERSAO_DOS_PESOS["fold0_bytes"],
                          VERSAO_DOS_PESOS.get("fold0_bytes_enxuto")))
    return True, (u"pesos na versao do mapa (%s, %s)"
                  % (VERSAO_DOS_PESOS["release"], VERSAO_DOS_PESOS["tarefa"]))


def nome_do_nivel(indice, fixado=True):
    i = int(indice)
    n = NIVEIS.get(i) or {}
    if fixado and n.get("confirmado") and n.get("candidato"):
        return "Lvl_" + str(n["candidato"])
    return "LNL%02d" % i


def nome_da_uniao(fixado=True):
    return NOME_DA_UNIAO if fixado else NOME_DA_UNIAO_NEUTRA


FONTE_DO_MODELO = (u"modelo de Weissmann et al. 2023 (pesos CC0, "
                   u"doi:10.3389/fonc.2023.1115258)")


def _nivel_e_lado(indice):
    n = MAPA_DOS_PESOS[int(indice)]
    if n.endswith("_L"):
        return n[:-2], u" esquerdo"
    if n.endswith("_R"):
        return n[:-2], u" direito"
    return n, u""


def descricao_do_nivel(indice, fixado=True):
    i = int(indice)
    if fixado:
        raiz, lado = _nivel_e_lado(i)
        return (u"Nivel %s%s (%s), Gregoire 2014. Rotulo %d de 20 do %s; mapa "
                u"rotulo->nivel fixado na versao dos pesos (%s) e conferido "
                u"pelo servico no TPS. Compartimento anatomico, nao e CTV. "
                u"SUGESTAO NAO APROVADA."
                % (raiz, lado, DESCRITOR_DO_NIVEL[raiz], i, FONTE_DO_MODELO,
                   VERSAO_DOS_PESOS["tarefa"]))
    return (u"Rotulo %d de 20 do %s. Os pesos instalados nao sao a versao em "
            u"que o mapa rotulo->nivel foi fixado (%s): o nivel anatomico "
            u"deste rotulo NAO foi atribuido. Confira a anatomia antes de "
            u"usa-lo como nivel. A uniao (%s) nao depende dessa atribuicao. "
            u"SUGESTAO NAO APROVADA."
            % (i, FONTE_DO_MODELO, VERSAO_DOS_PESOS["tarefa"],
               NOME_DA_UNIAO_NEUTRA))


def descricao_da_uniao(fixado=True):
    if fixado:
        return (u"Uniao anatomica nao aprovada dos niveis linfonodais "
                u"cervicais Ia a VIIb (rotulos 1 a 18, sem o nivel VIII "
                u"parotideo) do %s, depois do pos-processamento. NAO E OAR NEM "
                u"CTV: o volume eletivo e decisao medica. SUGESTAO NAO "
                u"APROVADA." % FONTE_DO_MODELO)
    return (u"Uniao dos 20 rotulos do %s, com pesos fora da versao do mapa "
            u"rotulo->nivel. Nao e OAR nem CTV. SUGESTAO NAO APROVADA."
            % FONTE_DO_MODELO)


def descricao_da_parotida(lado):
    return (u"Parotida %s: nivel VIII (parotideo) do %s menos o "
            u"esternocleidomastoideo, usada como contorno da glandula por "
            u"decisao do servico. SUGESTAO NAO APROVADA."
            % (u"esquerda" if lado == "left" else u"direita",
               FONTE_DO_MODELO))


def descricao_da_parotida_ts(lado, com_viii=True):
    return (u"Parotida %s do TotalSegmentator (head_glands_cavities), com o "
            u"pos-processamento do FULL (regras de gravacao e suavizacao): "
            u"nao e a crua do RadAI_TS, apesar do sufixo. Fica so no FULL, "
            u"para comparacao: a parotida do STUDY vem so do nivel VIII dos "
            u"niveis cervicais%s. SUGESTAO NAO APROVADA."
            % (u"esquerda" if lado == "left" else u"direita",
               u"" if com_viii else
               u", que nao a deu nesta serie, e o STUDY saiu sem ela"))


def observacoes_dos_niveis(nomes, extensao=None):
    if extensao is None:
        extensao = getattr(nomes, "extensao", None)
    medida = texto_da_extensao(extensao)
    fixados = dict((nome_do_nivel(i, True), i) for i in NIVEIS)
    neutros = dict((nome_do_nivel(i, False), i) for i in NIVEIS)
    parotidas = dict((v, k) for k, v in PAROTIDAS_DO_VIII.items())
    fora = {}
    for n in (nomes or ()):
        if n == NOME_DA_UNIAO:
            fora[n] = descricao_da_uniao(True)
        elif n == NOME_DA_UNIAO_NEUTRA:
            fora[n] = descricao_da_uniao(False)
        elif n in fixados:
            fora[n] = descricao_do_nivel(fixados[n], True)
        elif n in neutros:
            fora[n] = descricao_do_nivel(neutros[n], False)
        elif n in parotidas:
            fora[n] = descricao_da_parotida(parotidas[n])
            continue
        else:
            continue
        if medida:
            fora[n] = fora[n] + u" " + medida
    return fora


def _esquecer_candidatos():
    for n in NIVEIS.values():
        if not n.get("confirmado"):
            n["candidato"] = u""
            n.pop("proposto_por", None)
            n.pop("proposto_em", None)

MARCOS = {
    "cranial": ("skull",),
    "caudal": ("trachea",),
    "lateral": ("humerus_left", "humerus_right"),
}

OBRIGATORIOS = ("skull", "trachea", "humerus_left", "humerus_right")


def _tem(cruas, nome):
    try:
        return nome in cruas
    except Exception:
        return False


VOLUME_MINIMO_DE_ENCEFALO_CM3 = 100.0

FOLGA_ABAIXO_DA_CLAVICULA_MM = 30.0


class NiveisDaSerie(dict):

    def __init__(self, *a, **kw):
        dict.__init__(self, *a, **kw)
        self.extensao = None
        self.viii = {}
        self.fixado = True
        self.ilhas = []
        self._publicado = None
        self._rot_publicado = None
        self.sem_lado = set()

    # GUARDA: a camada publicada guarda o mapa de rotulos (int8) e monta as
    # mascaras so quando o `HNL_` e gravado; numa TC fina cada mascara cheia
    # tem 155 MB, e as duas camadas inteiras dobrariam o pico.
    @property
    def publicado(self):
        if self._publicado is not None or self._rot_publicado is None:
            return self._publicado
        m = NiveisDaSerie(masks_dos_niveis(self._rot_publicado,
                                           fixado=self.fixado,
                                           camada="publicado",
                                           sem_lado=self.sem_lado))
        conferir_saida(list(m))
        m.extensao = self.extensao
        m.fixado = self.fixado
        return m

    @publicado.setter
    def publicado(self, valor):
        self._publicado = valor


def serie_e_pescoco(cruas, grade=None):
    if cruas is None:
        return False, u"a task `total` não rodou nesta série"
    faltam = [n for n in OBRIGATORIOS if not _tem(cruas, n)]
    if faltam:
        return False, (u"faltam marcos do recorte do artigo: %s"
                       % ", ".join(faltam))
    cervicais = [n for n in ("vertebrae_C1", "vertebrae_C2", "vertebrae_C3",
                             "vertebrae_C4", "vertebrae_C5", "vertebrae_C6",
                             "vertebrae_C7") if _tem(cruas, n)]
    if len(cervicais) < 4:
        return False, (u"só %d vértebra(s) cervical(is) no campo — não é "
                       u"pescoço" % len(cervicais))

    if not _tem(cruas, "brain"):
        return False, (u"não há encéfalo no campo — é TC de tórax com o "
                       u"pescoço na borda, e não TC de cabeça e pescoço")
    if grade is not None:
        import numpy as np
        import radai_geom
        v = radai_geom.volume_cm3(np.asarray(cruas["brain"], dtype=bool), grade)
        if v < VOLUME_MINIMO_DE_ENCEFALO_CM3:
            return False, (u"só %.0f cm³ de encéfalo no campo (mínimo %.0f) — "
                           u"o campo não alcança a base frontal do crânio, que "
                           u"é o marco cranial do modelo"
                           % (v, VOLUME_MINIMO_DE_ENCEFALO_CM3))
        return True, (u"%d cervicais, os quatro marcos e %.0f cm³ de encéfalo "
                      u"no campo" % (len(cervicais), v))
    return True, (u"%d cervicais e os quatro marcos; encéfalo presente, mas "
                  u"sem grade para medir o volume dele" % len(cervicais))


def conferir_extensao(masks, cruas, grade):
    m = medir_extensao(masks, cruas, grade)
    return m["ok"], m["motivo"]


def medir_extensao(masks, cruas, grade):
    import numpy as np
    uniao = (masks or {}).get(NOME_DA_UNIAO)
    if uniao is None:
        uniao = (masks or {}).get(NOME_DA_UNIAO_NEUTRA)
    if uniao is None or not np.asarray(uniao).any():
        return {"ok": True, "motivo": u"nada a conferir", "desce_mm": None}
    clav = None
    for n in ("clavicula_left", "clavicula_right", "clavicula_l",
              "clavicula_r"):
        if _tem(cruas, n):
            m = np.asarray(cruas[n], dtype=bool)
            clav = m if clav is None else (clav | m)
    if clav is None or not clav.any():
        return {"ok": True, "desce_mm": None,
                "motivo": u"sem clavícula nesta série — não dá para conferir"}
    sup = grade.sentido[0] == "sup"
    zc = np.where(clav.any(axis=(1, 2)))[0]
    topo = int(zc.max()) if sup else int(zc.min())
    zu = np.where(np.asarray(uniao).any(axis=(1, 2)))[0]
    desce = ((topo - int(zu.min())) if sup else (int(zu.max()) - topo))
    desce_mm = max(0.0, desce * float(grade.spacing[0]))
    if desce_mm > FOLGA_ABAIXO_DA_CLAVICULA_MM:
        return {"ok": False, "desce_mm": desce_mm,
                "motivo": (u"a união desce %.0f mm abaixo do topo das "
                           u"clavículas (limite %.0f): nível cervical não faz "
                           u"isso, e o resultado não é confiável nesta série"
                           % (desce_mm, FOLGA_ABAIXO_DA_CLAVICULA_MM))}
    return {"ok": True, "desce_mm": desce_mm,
            "motivo": u"desce %.0f mm abaixo das clavículas" % desce_mm}


def texto_da_extensao(extensao):
    e = extensao or {}
    mm = e.get("desce_mm")
    if mm is None:
        return u""
    if e.get("ok", True):
        return (u"Nesta serie a uniao dos niveis termina %.0f mm abaixo do "
                u"topo das claviculas (dentro da folga de %.0f mm)."
                % (mm, FOLGA_ABAIXO_DA_CLAVICULA_MM))
    return (u"ESTUDO MARCADO: nesta serie a uniao dos niveis desce %.0f mm "
            u"abaixo do topo das claviculas, alem da folga de %.0f mm. O "
            u"nivel cervical mais baixo termina na clavicula: confira a "
            u"extensao caudal antes de usar qualquer nivel desta serie."
            % (mm, FOLGA_ABAIXO_DA_CLAVICULA_MM))




def caixa(cruas, forma, grade, margem_mm=10.0):
    import numpy as np

    faltam = [n for n in OBRIGATORIOS if not _tem(cruas, n)]
    if faltam:
        raise ValueError(
            u"nao da para montar o recorte do artigo: faltam %s. Rodar sem "
            u"ele poe o modelo fora da definicao de entrada em que foi "
            u"treinado." % ", ".join(faltam))

    def _lim(nome):
        m = np.asarray(cruas[nome], dtype=bool)
        if not m.any():
            raise ValueError(u"marco `%s` veio vazio nesta serie" % nome)
        idx = [np.where(m.any(axis=tuple(j for j in range(3) if j != i)))[0]
               for i in range(3)]
        return [(int(a.min()), int(a.max())) for a in idx]

    z_sk, _y_sk, _x_sk = _lim("skull")
    z_tr, _y_tr, _x_tr = _lim("trachea")
    _z_hl, _y_hl, x_hl = _lim("humerus_left")
    _z_hr, _y_hr, x_hr = _lim("humerus_right")

    sup = grade.sentido[0] == "sup"
    if sup:
        z0, z1 = min(z_tr), max(z_sk)
    else:
        z0, z1 = min(z_sk), max(z_tr)

    x0 = min(x_hl[0], x_hr[0])
    x1 = max(x_hl[1], x_hr[1])

    mz = int(round(margem_mm / max(grade.spacing[0], 1e-6)))
    mx = int(round(margem_mm / max(grade.spacing[2], 1e-6)))
    z0, z1 = max(0, z0 - mz), min(forma[0] - 1, z1 + mz)
    x0, x1 = max(0, x0 - mx), min(forma[2] - 1, x1 + mx)
    return (int(z0), int(z1) + 1, 0, int(forma[1]), int(x0), int(x1) + 1)


def primeiro_plano(vol, limiar_hu=-400.0, fechamento=9):
    import numpy as np
    from scipy import ndimage
    corpo = np.asarray(vol) > float(limiar_hu)
    if not corpo.any():
        return np.ones(np.asarray(vol).shape, dtype=bool)

    try:
        import radai_geom
        aberto = radai_geom.abrir_pontes(corpo, 2)
        if aberto.any():
            corpo = aberto
    except Exception:
        pass

    rot, n = ndimage.label(corpo)
    if n > 1:
        cont = np.bincount(rot.ravel())
        cont[0] = 0
        corpo = rot == int(np.argmax(cont))
    corpo = ndimage.binary_closing(
        corpo, structure=np.ones((1, 3, 3), dtype=bool),
        iterations=max(1, int(fechamento) // 3))
    for z in range(corpo.shape[0]):
        if corpo[z].any():
            corpo[z] = ndimage.binary_fill_holes(corpo[z])
    return corpo


def normalizar_ct(vol, plano_do_modelo):
    import numpy as np
    lo, hi = plano_do_modelo["clip"]
    v = np.clip(np.asarray(vol, dtype="float32"), lo, hi)
    return (v - plano_do_modelo["media"]) / plano_do_modelo["desvio"]




def fechar_ap(corpo, grade, margem_mm=10.0):
    import numpy as np
    c = np.asarray(corpo, dtype=bool)
    onde = np.where(c.any(axis=(0, 2)))[0]
    if not len(onde):
        return 0, int(c.shape[1])
    m = int(round(float(margem_mm) / max(float(grade.spacing[1]), 1e-6)))
    return (max(0, int(onde.min()) - m),
            min(int(c.shape[1]), int(onde.max()) + 1 + m))


def voltar_a_grade(rot_m, forma):
    import numpy as np
    from scipy import ndimage
    rot_m = np.asarray(rot_m)
    forma = tuple(int(v) for v in forma)
    escala = [((rot_m.shape[e] - 1) / float(forma[e] - 1)) if forma[e] > 1
              else 0.0 for e in range(3)]
    melhor = np.full(forma, -1.0, dtype=np.float32)
    fora = np.zeros(forma, dtype="int8")
    import warnings
    for r in np.unique(rot_m):
        ind = (rot_m == r).astype(np.float32)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            v = ndimage.affine_transform(ind, escala, offset=0.0,
                                         output_shape=forma, order=1,
                                         mode="nearest")
        troca = v > melhor
        melhor[troca] = v[troca]
        fora[troca] = int(r)
    return fora


def pasta_do_pos(base, modelo=None):
    modelo = modelo or MODELO_DOS_NIVEIS
    if modelo == "ensemble":
        raiz = os.path.dirname(os.path.dirname(os.path.dirname(str(base))))
        import radai_hnlnl_engine as HM
        return os.path.join(raiz, "ensembles", HM.TAREFA, HM.PASTA_DO_ENSEMBLE)
    return str(base)


def ler_pos_dos_pesos(pasta):
    import json
    try:
        with open(os.path.join(str(pasta), "postprocessing.json"), "rb") as f:
            return json.loads(f.read().decode("utf-8"))
    except Exception:
        return None


def pos_dos_pesos(rot, pasta, grade=None, log=None, cfg=None):
    import numpy as np
    from scipy import ndimage
    if cfg is None:
        cfg = ler_pos_dos_pesos(pasta)
    if not cfg:
        _dizer(log, u"  sem o postprocessing.json dos pesos (%s): o maior "
                    u"componente por classe nao foi aplicado" % pasta)
        return np.asarray(rot)
    rot = np.asarray(rot).copy()
    estrutura = ndimage.generate_binary_structure(3, 1)
    vol_vox = 1.0
    if grade is not None:
        vol_vox = float(np.prod([float(s) for s in grade.spacing]))
    # GUARDA: o nnU-Net v1 grava `"None"` (texto) quando nao ha minimo.
    minimos = cfg.get("min_valid_object_sizes")
    if not isinstance(minimos, dict):
        minimos = None
    for item in cfg.get("for_which_classes") or ():
        classes = tuple(int(c) for c in item) if isinstance(
            item, (list, tuple)) else (int(item),)
        m = np.isin(rot, classes)
        if not m.any():
            continue
        lab, n = ndimage.label(m, estrutura)
        if n < 2:
            continue
        tam = np.bincount(lab.ravel())[1:] * vol_vox
        maior = float(tam.max())
        minimo = None
        if minimos:
            chave = str(classes[0]) if len(classes) == 1 else str(classes)
            minimo = minimos.get(chave, minimos.get(classes[0]))
        for k in range(n):
            if float(tam[k]) == maior:
                continue
            if minimo is not None and float(tam[k]) >= float(minimo):
                continue
            rot[(lab == k + 1) & m] = 0
    return rot



GRUPOS_DE_CONFLITO = {
    "pares": ((18, 5), (17, 4), (5, 7), (4, 6), (7, 9), (6, 8)),
    "trios": ((11, 9, 13), (10, 8, 12)),
    "quadruplas": ((14, 1, 2, 3),),
}

# GUARDA: os 10 voxels do artigo estão na grade de 1,1716 mm do treino;
# em mm² o limiar não muda com o pixel da série.
LIMIAR_AREA_FATIA_MM2 = 10 * 1.1716 * 1.1716
QUEDA_DA_FATIA = 0.2


def _area(fatia, r):
    import numpy as np
    return int(np.count_nonzero(fatia == r))


def _moda_por_coluna(cima, grupo):
    import numpy as np
    moda = np.where(np.isin(cima, grupo), cima, 0).astype(cima.dtype)
    for x in range(moda.shape[1]):
        col = moda[:, x]
        nz = col[col > 0]
        if nz.size:
            cont = np.bincount(nz.astype(np.int64))
            col[col == 0] = int(np.argmax(cont))
        else:
            moda[:, x] = 0
    return moda


def pos_processar(rot, grade=None, log=None):
    import numpy as np
    rot = np.asarray(rot).copy()
    n = rot.shape[0]
    px = 1.1716 * 1.1716
    if grade is not None:
        px = float(grade.spacing[1]) * float(grade.spacing[2])
    pares = GRUPOS_DE_CONFLITO["pares"]
    grupos = ([(g, False) for g in GRUPOS_DE_CONFLITO["trios"]]
              + [(g, True) for g in GRUPOS_DE_CONFLITO["quadruplas"]])
    for z in range(n):
        f = rot[z]
        for a, b in pares:
            na, nb = _area(f, a), _area(f, b)
            if na > 0 and nb > 0:
                if na >= nb:
                    f[f == b] = a
                else:
                    f[f == a] = b
        for g, com_moda in grupos:
            p, outros = g[0], g[1:]
            npri = _area(f, p)
            nout = [_area(f, o) for o in outros]
            if not (npri > 0 and any(v > 0 for v in nout)):
                continue
            if npri >= sum(nout):
                for o in outros:
                    f[f == o] = p
                continue
            sel = f == p
            if z + 1 >= n:
                f[sel] = outros[int(np.argmax(nout))]
                continue
            cima = rot[z + 1].copy()
            if com_moda:
                moda = _moda_por_coluna(cima, outros)
                fora = (cima != 0) & ~np.isin(cima, outros)
                cima[fora] = moda[fora]
            else:
                cima[~np.isin(cima, outros)] = 0
            f[sel] = cima[sel]
        cont = int(np.count_nonzero(f))
        if cont * px <= LIMIAR_AREA_FATIA_MM2 + 1e-6:
            f[:] = 0
            continue
        baixo = int(np.count_nonzero(rot[z - 1])) if z > 0 else 0
        cima_n = int(np.count_nonzero(rot[z + 1])) if z + 1 < n else 0
        if baixo == 0 and cima_n > 0 and cont / float(cima_n) <= QUEDA_DA_FATIA:
            f[:] = 0
    return rot




def _centroides_em_mm(rot, grade):
    import numpy as np
    eixo_lat, s_lat = grade.eixo_sinal("esq")
    eixo_ap, s_ap = grade.eixo_sinal("post")
    eixo_cc, s_cc = grade.eixo_sinal("sup")
    arr = np.asarray(rot)
    fora = {}
    for i in range(1, 21):
        onde = np.nonzero(arr == i)
        if not len(onde[0]):
            continue
        centro = [float(np.mean(o)) for o in onde]
        fora[i] = (
            s_lat * centro[eixo_lat] * grade.spacing[eixo_lat],
            s_ap * centro[eixo_ap] * grade.spacing[eixo_ap],
            s_cc * centro[eixo_cc] * grade.spacing[eixo_cc],
        )
    return fora


def conferir_lado(rot, grade):
    try:
        cen = _centroides_em_mm(rot, grade)
    except Exception as e:
        return False, [u"nao consegui medir os centroides (%s): niveis nao "
                       u"entregues" % str(e)[:90]]
    presentes = [(a, b) for a, b in PARES_DE_LADO if a in cen and b in cen]
    trocados = [(a, b) for a, b in presentes if cen[a][0] <= cen[b][0]]
    if presentes and 2 * len(trocados) >= len(presentes):
        return False, [u"lados invertidos em %d de %d pares: orientacao "
                       u"suspeita, niveis nao entregues"
                       % (len(trocados), len(presentes))]
    laudo = [u"lados conferidos em %d par(es)" % len(presentes)]
    for a, b in trocados:
        laudo.append(u"ALERTA: o par %s/%s saiu com os lados trocados"
                     % (MAPA_DOS_PESOS[a], MAPA_DOS_PESOS[b]))
    return True, laudo


def lados_suspeitos(rot, grade):
    import numpy as np
    try:
        cen = _centroides_em_mm(rot, grade)
    except Exception as e:
        todos = set(i for par in PARES_DE_LADO for i in par)
        return todos, [u"nao consegui medir os centroides (%s): nenhum nivel "
                       u"sai com o lado no nome" % str(e)[:90]]
    if not cen:
        return set(), []
    medios = ([cen[i][0] for i in NIVEIS_DE_LINHA_MEDIA if i in cen]
              or [(cen[a][0] + cen[b][0]) / 2.0 for a, b in PARES_DE_LADO
                  if a in cen and b in cen])
    if not medios:
        return set(), []
    meio = float(np.median(medios))
    fora, laudo = set(), []
    for a, b in PARES_DE_LADO:
        if a in cen and b in cen and cen[a][0] <= cen[b][0]:
            fora.update((a, b))
            laudo.append(u"o par %s/%s saiu com os lados trocados: os dois "
                         u"ficam so na uniao, sem nome de lado"
                         % (MAPA_DOS_PESOS[a], MAPA_DOS_PESOS[b]))
    for i in sorted(cen):
        lado = _lado_esperado(i)
        if not lado or i in fora:
            continue
        if (cen[i][0] - meio) * lado < 0:
            fora.add(i)
            laudo.append(u"%s esta do outro lado da linha media (%.0f mm): "
                         u"fica so na uniao, sem nome de lado"
                         % (MAPA_DOS_PESOS[i], cen[i][0] - meio))
    return fora, laudo



NIVEIS_DE_LINHA_MEDIA = (1, 14, 15, 16)
TOLERANCIA_CC_CORTES = 1
FRACAO_DO_MAIOR = 0.25


def _lado_esperado(i):
    n = MAPA_DOS_PESOS[int(i)]
    if n.endswith("_L"):
        return 1.0
    if n.endswith("_R"):
        return -1.0
    return 0.0


def limpar_ilhas(rot, grade, log=None, removidos=None):
    import numpy as np
    from scipy import ndimage
    rot = np.asarray(rot).copy()
    cen = _centroides_em_mm(rot, grade)
    if not cen:
        return rot
    eixo_lat, s_lat = grade.eixo_sinal("esq")
    eixo_cc, _s = grade.eixo_sinal("sup")
    lats = sorted(v[0] for v in cen.values())
    meio = float(np.median(lats))
    estrutura = ndimage.generate_binary_structure(3, 1)
    vol_vox = float(np.prod([float(s) for s in grade.spacing]))
    for i in range(1, 21):
        m = rot == i
        if not m.any():
            continue
        lab, n = ndimage.label(m, estrutura)
        if n < 2:
            continue
        objs = ndimage.find_objects(lab)
        tam = np.bincount(lab.ravel())[1:]
        k_maior = int(np.argmax(tam))
        faixa = objs[k_maior][eixo_cc]
        lado = _lado_esperado(i)
        maior_m = None
        for k in range(n):
            if k == k_maior:
                continue
            fk = objs[k][eixo_cc]
            cruza = (fk.start <= faixa.stop - 1 + TOLERANCIA_CC_CORTES
                     and fk.stop - 1 >= faixa.start - TOLERANCIA_CC_CORTES)
            fica = cruza or tam[k] >= FRACAO_DO_MAIOR * tam[k_maior]
            if lado:
                onde = np.nonzero(lab[objs[k]] == k + 1)[eixo_lat]
                c_lat = s_lat * (float(np.mean(onde)) + objs[k][eixo_lat].start
                                 ) * grade.spacing[eixo_lat]
                if (c_lat - meio) * lado < 0:
                    fica = False
            if fica:
                continue
            comp = lab == k + 1
            if maior_m is None:
                maior_m = lab == k_maior + 1
            d = _distancia_mm(comp, maior_m, grade)
            rot[comp] = 0
            reg = (nome_do_nivel(i), round(float(tam[k]) * vol_vox / 1000.0, 3),
                   round(d, 1))
            if removidos is not None:
                removidos.append(reg)
            _dizer(log, u"  ilha tirada de %s: %.2f cm3 a %.0f mm do corpo "
                        u"principal" % reg)
    return rot


def _distancia_mm(a, b, grade):
    import numpy as np
    from scipy import ndimage
    junto = a | b
    lim = [np.where(junto.any(axis=tuple(j for j in range(3) if j != e)))[0]
           for e in range(3)]
    cx = tuple(slice(int(l.min()), int(l.max()) + 1) for l in lim)
    dist = ndimage.distance_transform_edt(~b[cx], sampling=grade.spacing)
    sel = a[cx]
    return float(dist[sel].min()) if sel.any() else 0.0


VASOS_POR_NIVEL = {
    4: ("internal_jugular_vein_left",),
    5: ("internal_jugular_vein_right",),
    6: ("internal_jugular_vein_left", "common_carotid_artery_left",
        "internal_carotid_artery_left"),
    7: ("internal_jugular_vein_right", "common_carotid_artery_right",
        "internal_carotid_artery_right"),
    8: ("internal_jugular_vein_left", "common_carotid_artery_left",
        "internal_carotid_artery_left"),
    9: ("internal_jugular_vein_right", "common_carotid_artery_right",
        "internal_carotid_artery_right"),
}
VASOS_DO_PESCOCO = tuple(sorted(set(v for vs in VASOS_POR_NIVEL.values()
                                    for v in vs)))
DISTANCIA_DO_VASO_MM = 3.0


def preencher_cavidade_vascular(rot, vasos, grade, log=None):
    import numpy as np
    from scipy import ndimage
    rot = np.asarray(rot).copy()
    vasos = vasos or {}
    sy, sx = float(grade.spacing[1]), float(grade.spacing[2])
    vol_vox = float(np.prod([float(s) for s in grade.spacing]))
    faltaram = set()
    for i, nomes in sorted(VASOS_POR_NIVEL.items()):
        zs = np.where((rot == i).any(axis=(1, 2)))[0]
        if not len(zs):
            continue
        vaso = None
        for nm in nomes:
            m = vasos.get(nm) if hasattr(vasos, "get") else None
            if m is None:
                faltaram.add(nm)
                continue
            m = np.asarray(m, dtype=bool)
            vaso = m.copy() if vaso is None else (vaso | m)
        antes = int(np.count_nonzero(rot == i))
        for z in zs:
            f = rot[z]
            nivel = f == i
            if vaso is not None:
                livre = vaso[z] & (f == 0)
                if livre.any():
                    dist = ndimage.distance_transform_edt(~nivel,
                                                          sampling=(sy, sx))
                    lab, n = ndimage.label(livre)
                    for k in range(1, n + 1):
                        comp = lab == k
                        if float(dist[comp].min()) <= DISTANCIA_DO_VASO_MM:
                            f[comp] = i
            cheio = ndimage.binary_fill_holes(f == i)
            f[cheio & (f == 0)] = i
        ganho = int(np.count_nonzero(rot == i)) - antes
        if ganho:
            _dizer(log, u"  cavidade vascular de %s: +%.2f cm3"
                        % (nome_do_nivel(i), ganho * vol_vox / 1000.0))
    if faltaram:
        _dizer(log, u"  cavidade vascular sem %s: so o preenchimento de "
                    u"buraco nesses niveis" % u", ".join(sorted(faltaram)))
    return rot


SUAVIZACAO_DOS_NIVEIS_MM = 0.8


def suavizar_niveis(rot, grade, mm=None, log=None):
    import numpy as np
    import radai_geom
    rot = np.asarray(rot)
    mm = SUAVIZACAO_DOS_NIVEIS_MM if mm is None else float(mm)
    presentes = [int(v) for v in np.unique(rot) if v]
    if not presentes or mm <= 0:
        return rot.copy()
    cheio = rot
    algo = rot != 0
    folga = [0] + [int(np.ceil(4 * mm / float(grade.spacing[e]))) + 2
                   for e in (1, 2)]
    cx = []
    for e in range(3):
        onde = np.where(algo.any(axis=tuple(j for j in range(3) if j != e)))[0]
        cx.append(slice(max(0, int(onde.min()) - folga[e]),
                        min(rot.shape[e], int(onde.max()) + 1 + folga[e])))
    cx = tuple(cx)
    del algo
    rot = cheio[cx]
    partes = dict((i, rot == i) for i in presentes)
    lisas = radai_geom.suavizar_conjunto(partes, mm, grade, so_no_plano=True)
    del partes
    sub = np.zeros(rot.shape, dtype=rot.dtype)
    for i in presentes:
        sub[lisas[i]] = i
    del lisas
    for i in presentes:
        tinha = (rot == i).any(axis=(1, 2))
        tem = (sub == i).any(axis=(1, 2))
        for z in np.where(tinha & ~tem)[0]:
            volta = (rot[z] == i) & (sub[z] == 0)
            sub[z][volta] = i
    fora = np.zeros(cheio.shape, dtype=cheio.dtype)
    fora[cx] = sub
    return fora


def _dizer(log, m):
    if log:
        try:
            log(m)
        except Exception:
            pass


def masks_dos_niveis(rot, minimo_voxels=10, fixado=True, camada="final",
                     sem_lado=()):
    import numpy as np
    rot = np.asarray(rot)
    if fixado:
        indices = range(1, 19) if camada == "final" else range(1, 21)
    else:
        indices = range(1, 21)
    sem_lado = set(int(i) for i in (sem_lado or ())) if fixado else set()
    saida = {}
    uniao = None
    for i in indices:
        m = rot == i
        if int(m.sum()) < int(minimo_voxels):
            continue
        if (not fixado) or i in ROTULOS_DA_UNIAO:
            uniao = m.copy() if uniao is None else (uniao | m)
        if i in sem_lado:
            continue
        saida[nome_do_nivel(i, fixado)] = m
    if uniao is not None:
        saida[nome_da_uniao(fixado)] = uniao
    return saida


def conferir_saida(nomes):
    permitidos = (set(nome_do_nivel(i, True) for i in range(1, 21))
                  | set(nome_do_nivel(i, False) for i in range(1, 21))
                  | {NOME_DA_UNIAO, NOME_DA_UNIAO_NEUTRA}
                  | set(PAROTIDAS_DO_VIII.values()))
    fora = [n for n in (nomes or []) if n not in permitidos]
    if fora:
        raise ValueError(
            u"PAREI: %d nome(s) fora dos niveis linfonodais: %s. Este motor "
            u"entrega compartimento anatomico, e nada alem disso."
            % (len(fora), ", ".join(sorted(fora)[:8])))
    return True


# GUARDA: menos que isto, depois da subtração, é lasca solta do ECM.
LASCA_DA_PAROTIDA_CM3 = 0.1
FRACAO_DA_LASCA = 0.05

# GUARDA: a parótida do VIII só substitui a do TotalSegmentator quando é
# plausível como glândula inteira; um resto do VIII viraria a restrição de
# dose de um fragmento.
PISO_DA_PAROTIDA_CM3 = 0.5
FRACAO_MINIMA_DO_TS = 0.5
SOBREPOSICAO_MINIMA_COM_O_TS = 0.3


def parotida_plausivel(p, ts, grade):
    import numpy as np
    vol_vox = float(np.prod([float(s) for s in grade.spacing])) / 1000.0
    p = np.asarray(p, dtype=bool)
    v_p = float(np.count_nonzero(p)) * vol_vox
    if ts is None or not np.asarray(ts).any():
        if v_p < PISO_DA_PAROTIDA_CM3:
            return False, (u"a do nivel VIII tem %.2f cm3, abaixo do piso de "
                           u"%.1f cm3" % (v_p, PISO_DA_PAROTIDA_CM3))
        return True, u""
    ts = np.asarray(ts, dtype=bool)
    v_ts = float(np.count_nonzero(ts)) * vol_vox
    comum = float(np.count_nonzero(p & ts)) * vol_vox
    menor = min(v_p, v_ts)
    if (v_p < PISO_DA_PAROTIDA_CM3 or v_p < FRACAO_MINIMA_DO_TS * v_ts
            or menor <= 0 or comum / menor < SOBREPOSICAO_MINIMA_COM_O_TS):
        return False, (u"a do nivel VIII nao e plausivel como a glandula: "
                       u"%.2f cm3 contra %.2f cm3 da do TotalSegmentator, "
                       u"%.0f%% da menor dentro da outra (pede %.1f cm3, %.0f%% "
                       u"do volume e %.0f%% de sobreposicao)"
                       % (v_p, v_ts, 100.0 * comum / menor if menor else 0.0,
                          PISO_DA_PAROTIDA_CM3, 100 * FRACAO_MINIMA_DO_TS,
                          100 * SOBREPOSICAO_MINIMA_COM_O_TS))
    return True, u""


def parotidas_do_viii(viii, ecm, grade, log=None, ts=None):
    import numpy as np
    from scipy import ndimage
    fora, motivos = {}, {}
    vol_vox = float(np.prod([float(s) for s in grade.spacing]))
    for lado in ("left", "right"):
        v = (viii or {}).get(lado)
        if v is None or not np.asarray(v).any():
            motivos[lado] = u"sem o nivel VIII deste lado"
            continue
        e = (ecm or {}).get(lado)
        if e is None or not np.asarray(e).any():
            motivos[lado] = (u"sem o esternocleidomastoideo deste lado (a "
                             u"headneck_muscles nao rodou)")
            continue
        p = np.asarray(v, dtype=bool) & ~np.asarray(e, dtype=bool)
        lab, n = ndimage.label(p, ndimage.generate_binary_structure(3, 1))
        if n > 1:
            tam = np.bincount(lab.ravel())[1:]
            maior = int(tam.max())
            for k in range(n):
                cm3 = tam[k] * vol_vox / 1000.0
                if (tam[k] < maior and cm3 < LASCA_DA_PAROTIDA_CM3
                        and tam[k] < FRACAO_DA_LASCA * maior):
                    p[lab == k + 1] = False
        if int(p.sum()) < 10:
            motivos[lado] = u"o nivel VIII ficou vazio depois do ECM"
            continue
        ok, motivo = parotida_plausivel(p, (ts or {}).get(lado), grade)
        if not ok:
            motivos[lado] = motivo
            continue
        fora[PAROTIDAS_DO_VIII[lado]] = p
    conferir_saida(list(fora))
    return fora, motivos




def disponivel():
    try:
        import radai_hnlnl_engine as HM
    except Exception as e:
        return False, u"nao consegui importar o motor (%s)" % type(e).__name__
    base = HM.pasta_dos_pesos()
    if not base:
        return False, (u"os pesos dos niveis cervicais nao estao nesta "
                       u"instalacao (a pasta `modelos\\hnlnl` nao tem o "
                       u"plans.pkl). O pacote do pipeline unico os traz: "
                       u"faltando, ele esta incompleto -- refaca o preparo "
                       u"(CONFIGURAR_AMBIENTE) ou reinstale o pacote")
    if MODELO_DOS_NIVEIS == "ensemble":
        faltam = HM.faltam_do_ensemble(base)
        if faltam:
            return False, (u"os pesos do %s estao incompletos nesta "
                           u"instalacao (faltam %d: %s). O pacote do "
                           u"pipeline unico os traz: refaca o preparo "
                           u"(CONFIGURAR_AMBIENTE) ou reinstale o pacote"
                           % (HM.REDE_DO_ENSEMBLE, len(faltam),
                              u", ".join(faltam[:3])))
    return True, base


MODELO_DOS_NIVEIS = "ensemble"


def rede_dos_niveis():
    import radai_hnlnl_engine as HM
    if MODELO_DOS_NIVEIS == "ensemble":
        return HM.REDE_DO_ENSEMBLE
    return u"3D fold 0 (1 peso, so referencia de medida)"


class _Canonicas(object):

    def __init__(self, cruas, grade):
        self._c = cruas if cruas is not None else {}
        self._g = grade

    def __contains__(self, k):
        try:
            return k in self._c
        except Exception:
            return False

    def __getitem__(self, k):
        import numpy as np
        import radai_geom
        return radai_geom.para_canonico(np.asarray(self._c[k], dtype=bool),
                                        self._g)

    def get(self, k, padrao=None):
        return self[k] if k in self else padrao


def _ext_por_nivel(rot, z0, cruas_c, grade, log):
    import numpy as np
    if "sternum" not in cruas_c:
        return
    est = np.asarray(cruas_c["sternum"], dtype=bool)
    zs = np.where(est.any(axis=(1, 2)))[0]
    if not len(zs):
        return
    topo = int(zs.max())
    partes = []
    for i in (10, 11, 12, 13):
        zi = np.where((rot == i).any(axis=(1, 2)))[0]
        if len(zi):
            partes.append(u"%s %+.0f mm" % (
                nome_do_nivel(i), (int(zi.min()) + z0 - topo)
                * float(grade.spacing[0])))
    if partes:
        _dizer(log, u"  fim caudal contra o topo do esterno (+ acima, - "
                    u"abaixo; so no log): %s" % u", ".join(partes))


def rodar_na_serie(volume_hu, cruas, forma, grade, device="cpu", log=None,
                   vasos=None):
    import numpy as np
    from scipy import ndimage
    import radai_geom
    import radai_hnlnl_engine as HM

    ok, base = disponivel()
    if not ok:
        _dizer(log, u"niveis cervicais: %s" % base)
        return {}

    e_pescoco, motivo = serie_e_pescoco(cruas, grade)
    if not e_pescoco:
        _dizer(log, u"niveis cervicais: nao roda nesta serie — %s" % motivo)
        return {}
    _dizer(log, u"niveis cervicais: %s" % motivo)
    fix, motivo_fix = fixado(base)
    _dizer(log, u"  mapa rotulo->nivel: %s%s" % (
        motivo_fix, u"" if fix else u" — nomes neutros"))
    _esquecer_candidatos()

    try:
        gc = radai_geom.grade_canonica(grade)
    except ValueError as e:
        _dizer(log, u"  niveis cervicais nao rodam: %s" % e)
        return {}
    vol_c = radai_geom.para_canonico(volume_hu, grade)
    cruas_c = _Canonicas(cruas, grade)
    vasos_c = _Canonicas(vasos, grade)

    z0, z1, y0, y1, x0, x1 = caixa(cruas_c, forma, gc)
    rec = np.asarray(vol_c)[z0:z1, y0:y1, x0:x1]
    corpo = primeiro_plano(rec)
    ya, yb = fechar_ap(corpo, gc)
    rec, corpo = rec[:, ya:yb], corpo[:, ya:yb]
    y0, y1 = y0 + ya, y0 + yb
    _dizer(log, u"  recorte pelos marcos do artigo, com o ap pelo corpo: %s "
                u"de %s" % (rec.shape, tuple(forma)))
    rec = np.where(corpo, rec, -1000.0).astype("float32")
    del corpo

    plano_m = HM.plano(base)
    fator = tuple(float(gc.spacing[i]) / float(plano_m["spacing"][i])
                  for i in range(3))
    _dizer(log, u"  reamostrando por %s (de %s mm para %s mm)"
           % (tuple(round(f, 3) for f in fator),
              tuple(round(float(s), 2) for s in gc.spacing),
              tuple(round(float(s), 2) for s in plano_m["spacing"])))
    vol = ndimage.zoom(rec, fator, order=1, mode="nearest")
    vol = normalizar_ct(vol, plano_m)

    _dizer(log, u"  rede: %s" % rede_dos_niveis())
    rot_m = HM.inferir_em_processo_separado(
        base, vol, fold="ensemble" if MODELO_DOS_NIVEIS == "ensemble" else 0,
        device=device, log=log)
    del vol
    rot = voltar_a_grade(rot_m, rec.shape)
    del rot_m, rec

    HM.conferir_niveis(np.unique(rot).tolist())

    rot = pos_dos_pesos(rot, pasta_do_pos(base), gc, log)
    rot = pos_processar(rot, gc, log)
    lado_ok, laudo_lado = conferir_lado(rot, gc)
    for _ln in laudo_lado:
        _dizer(log, u"  " + _ln)
    if not lado_ok:
        return {}
    sem_lado, laudo_sem_lado = lados_suspeitos(rot, gc) if fix else (set(), [])
    for _ln in laudo_sem_lado:
        _dizer(log, u"  " + _ln)
    publicado = rot.copy()

    removidos = []
    if fix:
        rot = limpar_ilhas(rot, gc, log, removidos)
        caixa_v = (slice(z0, z1), slice(y0, y1), slice(x0, x1))
        vasos_rec = dict((n, vasos_c[n][caixa_v]) for n in VASOS_DO_PESCOCO
                         if n in vasos_c)
        rot = preencher_cavidade_vascular(rot, vasos_rec, gc, log)
        rot = suavizar_niveis(rot, gc, log=log)
        _ext_por_nivel(rot, z0, cruas_c, gc, log)

    cheio = np.zeros(tuple(int(v) for v in forma), dtype="int8")
    cheio[z0:z1, y0:y1, x0:x1] = rot
    final = radai_geom.do_canonico(cheio, grade)
    cheio = np.zeros(tuple(int(v) for v in forma), dtype="int8")
    cheio[z0:z1, y0:y1, x0:x1] = publicado
    pub = radai_geom.do_canonico(cheio, grade)
    del cheio, rot, publicado

    masks = masks_dos_niveis(final, fixado=fix, camada="final",
                             sem_lado=sem_lado)
    conferir_saida(list(masks))

    ext = medir_extensao(masks, cruas, grade)
    fora = NiveisDaSerie(masks)
    fora.extensao = ext
    fora.fixado = fix
    fora.ilhas = removidos
    fora.sem_lado = set(sem_lado)
    fora._rot_publicado = pub
    if fix:
        fora.viii = dict((lado, final == i) for lado, i in INDICE_DO_VIII.items()
                         if i not in sem_lado
                         and int(np.count_nonzero(final == i)) >= 10)
    if not ext["ok"]:
        _dizer(log, u"  niveis cervicais MARCADOS (e nao recusados): %s — a "
                    u"medida vai na descricao de cada ROI" % ext["motivo"])
    _dizer(log, u"  %d nivel(is) com volume, mais a uniao (%s)"
           % (max(0, len(masks) - 1), ext["motivo"]))
    return fora
