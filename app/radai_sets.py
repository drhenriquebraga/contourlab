# -*- coding: utf-8 -*-

CONJUNTOS = (
    {"cod": "oar", "infixo": "", "sufixo": "_ai",
     "nome": "Radioterapia.ai_OAR",
     "rotulo": u"entregue ao TPS — seleção do FULL para o plano, TG-263",
     "rotulo_curto": "Radioterapia.ai_OAR",
     "entregue": True, "agrupado": True, "suavizado": True,
     "desconta": True,
     "motor": "Radioterapia.AI / TotalSegmentator",
     "ajuda": (u"Uma seleção do FULL, com as mesmas estruturas byte a byte: "
               u"os órgãos de risco e os compostos que o plano usa (pulmão, "
               u"coluna por segmento, costelas por lado, osso da "
               u"pelve), sem as partes. É o que o plano precisa: contornar "
               u"dose num conjunto com 24 costelas separadas é trabalho "
               u"inútil.")},

    {"cod": "full", "infixo": "FULL_", "sufixo": "_ai",
     "nome": "FULL",
     "rotulo": u"FULL — todo o pós-processamento, partes e compostos",
     "rotulo_curto": "FULL",
     "entregue": False, "agrupado": False, "suavizado": True,
     "desconta": True,
     "motor": "Radioterapia.AI / TotalSegmentator",
     "ajuda": ("Cada lobo, cada costela e cada vértebra em separado, E os "
               "compostos, com todo o pós-processamento (refino por "
               "densidade, margens, coração de radioterapia, pele e "
               "parede). É o que a revisão precisa: a mesclada esconde qual "
               "parte saiu ruim — a costela 12 sai com Dice 0,904 e a "
               "primeira com 0,970. O conjunto entregue (OAR) é uma seleção "
               "deste arquivo, com as mesmas estruturas.")},

    {"cod": "ts", "infixo": "TS_", "sufixo": "_ts",
     "nome": "TotalSegmentator",
     "rotulo": "TotalSegmentator cru — sem pós-processamento",
     "rotulo_curto": "TS cru",
     "entregue": False, "agrupado": False, "suavizado": False,
     "cru": True,
     "motor": "TotalSegmentator (rotulos crus)",
     "ajuda": ("A saída do modelo como ela é, sem suavização, sem agrupamento "
               "e sem nome clínico: a linha de base da comparação. A única "
               "mudança é o índice 26, que entra no sacro, para nenhum "
               "arquivo ter Vertebrae_L6.")},

    {"cod": "nv", "infixo": "NV_", "sufixo": "_nv",
     "nome": "NV-Segment-CT",
     "rotulo": "NV-Segment-CT (NVIDIA) — segundo motor",
     "rotulo_curto": "NV-Segment-CT",
     "entregue": False, "agrupado": False, "suavizado": True,
     "motor": "Radioterapia.AI / NV-Segment-CT",
     "ajuda": ("Segundo motor, para comparação. Os pesos são da NVIDIA Open "
               "Model License, que permite uso comercial — o cartão do modelo "
               "continua dizendo que é para pesquisa, e não para uso clínico, "
               "e por isso ele sai em arquivo próprio.")},

    {"cod": "cads", "infixo": "CADS_", "sufixo": "_cds",
     "nome": "CADS",
     "rotulo": "CADS — reto, próstata e vesículas",
     "rotulo_curto": "CADS",
     "entregue": False, "agrupado": False, "suavizado": True,
     "motor": "Radioterapia.AI / CADS",
     "ajuda": ("Já esteve no projeto e saiu por ser lento e entregar menos; "
               "volta como COMPARADOR, e com o mesmo pós-processamento dos "
               "nossos — o cru dele pedia muito ajuste.")},

    {"cod": "mse", "infixo": "MSE_", "sufixo": "_mse",
     "nome": "MOOSE",
     "rotulo": u"MOOSE — câmaras cardíacas e composição corporal",
     "rotulo_curto": "MOOSE",
     "entregue": False, "agrupado": False, "suavizado": True,
     "motor": "Radioterapia.AI / MOOSE (ENHANCE.PET)",
     "ajuda": (u"Dezesseis estruturas que o TotalSegmentator livre não "
               u"entrega: as quatro câmaras do coração, o miocárdio, a "
               u"artéria pulmonar, e músculo esquelético com as gorduras "
               u"subcutânea e visceral separadas. Pesos CC BY 4.0. Sai em "
               u"arquivo próprio porque o protocolo de delineamento dele é de "
               u"medicina nuclear, e não de radioterapia.")},

    {"cod": "hnl", "infixo": "HNL_", "sufixo": "_lnl",
     "nome": "Níveis linfonodais cervicais",
     "rotulo": u"Níveis cervicais — modelo de Weissmann et al. (2023)",
     "rotulo_curto": "Níveis cervicais",
     "entregue": False, "agrupado": False, "suavizado": False,
     "motor": "Radioterapia.AI / HNLNL (Weissmann et al. 2023)",
     "ajuda": (u"Os níveis linfonodais cervicais do modelo de Weissmann et "
               u"al. (2023), treinado pelo consenso de Grégoire et al. 2014 "
               u"(a atualização de 2013). Domínio público (CC0-1.0). Este "
               u"arquivo é o método publicado: o modelo, o pós-processamento "
               u"dos pesos e o ajuste aos planos da TC, com os nomes de "
               u"Grégoire pelo mapa dos autores (Lvl_Ia a Lvl_VIII), mais a "
               u"união dos níveis Ia a VIIb, LNL_UNION, união anatômica não "
               u"aprovada que não é OAR nem CTV. Sai sem a nossa suavização. "
               u"Só quando pedido, e só em série em que a cabeça aparece; o "
               u"modelo exige um recorte por marcos que sai da própria "
               u"segmentação do TotalSegmentator.")},


)

PLUGINS = (
    {"cod": "orb", "task": "oculomotor_muscles", "infixo": "ORB_",
     "sufixo": "_orb", "nome": u"Órbita (oculomotor_muscles)",
     "rotulo": u"plugin — músculos extraoculares, globos e nervos ópticos",
     "rotulo_curto": u"Órbita", "achado": False},
    {"cod": "tth", "task": "teeth", "infixo": "TTH_", "sufixo": "_tth",
     "nome": u"Dentes (teeth)",
     "rotulo": u"plugin — dentes, um a um", "rotulo_curto": u"Dentes",
     "achado": False},
    {"cod": "lvs", "task": "lung_vessels", "infixo": "LVS_", "sufixo": "_lvs",
     "nome": u"Vasos e vias aéreas pulmonares (lung_vessels)",
     "rotulo": u"plugin — artérias, veias e vias aéreas do pulmão",
     "rotulo_curto": u"Vasos pulmonares", "achado": False},
    {"cod": "lvl", "task": "lung_vessels_LEGACY", "infixo": "LVL_",
     "sufixo": "_lvl", "nome": u"Vasos pulmonares, modelo antigo "
                               u"(lung_vessels_LEGACY)",
     "rotulo": u"plugin — árvore vascular e brônquica, modelo de 2023",
     "rotulo_curto": u"Vasos pulmonares (legado)", "achado": False},
    {"cod": "nod", "task": "lung_nodules", "infixo": "NOD_", "sufixo": "_nod",
     "nome": u"Nódulos pulmonares — ACHADO (lung_nodules)",
     "rotulo": u"plugin de ACHADO — nódulos pulmonares",
     "rotulo_curto": u"Nódulos (ACHADO)", "achado": True},
    {"cod": "lsg", "task": "liver_segments", "infixo": "LSG_",
     "sufixo": "_lsg", "nome": u"Segmentos hepáticos (liver_segments)",
     "rotulo": u"plugin — os oito segmentos de Couinaud",
     "rotulo_curto": u"Segmentos hepáticos", "achado": False},
    {"cod": "lls", "task": "liver_lesions", "infixo": "LLS_", "sufixo": "_lls",
     "nome": u"Lesões hepáticas — ACHADO (liver_lesions)",
     "rotulo": u"plugin de ACHADO — lesões hepáticas (exige contraste)",
     "rotulo_curto": u"Lesões hepáticas (ACHADO)", "achado": True},
    {"cod": "vbd", "task": "vertebrae_body", "infixo": "VBD_",
     "sufixo": "_vbd", "nome": u"Corpos vertebrais e discos (vertebrae_body)",
     "rotulo": u"plugin — corpo vertebral e disco intervertebral",
     "rotulo_curto": u"Corpos vertebrais", "achado": False},
    {"cod": "hip", "task": "hip_implant", "infixo": "HIP_", "sufixo": "_hip",
     "nome": u"Prótese de quadril (hip_implant)",
     "rotulo": u"plugin — prótese metálica de quadril",
     "rotulo_curto": u"Prótese de quadril", "achado": False},
    {"cod": "vmr", "task": "vertebrae_mr", "infixo": "VMR_", "sufixo": "_vmr",
     "nome": u"Vértebras na RM (vertebrae_mr)",
     "rotulo": u"plugin — vértebras e discos na RM",
     "rotulo_curto": u"Vértebras (RM)", "achado": False},
    {"cod": "lsm", "task": "liver_segments_mr", "infixo": "LSM_",
     "sufixo": "_lsm", "nome": u"Segmentos hepáticos na RM "
                               u"(liver_segments_mr)",
     "rotulo": u"plugin — os oito segmentos de Couinaud na RM",
     "rotulo_curto": u"Segmentos hepáticos (RM)", "achado": False},
    {"cod": "llm", "task": "liver_lesions_mr", "infixo": "LLM_",
     "sufixo": "_llm", "nome": u"Lesões hepáticas na RM — ACHADO "
                               u"(liver_lesions_mr)",
     "rotulo": u"plugin de ACHADO — lesões hepáticas na RM",
     "rotulo_curto": u"Lesões hepáticas RM (ACHADO)", "achado": True},
)
for _p in PLUGINS:
    _p.setdefault("entregue", False)
    _p.setdefault("agrupado", False)
    _p.setdefault("suavizado", True)
    _p.setdefault("plugin", True)
    _p.setdefault("motor", u"Radioterapia.AI / TotalSegmentator (%s)"
                  % _p["task"])
    _p.setdefault("ajuda", u"Task opcional, em arquivo próprio: ela não "
                           u"alimenta o conjunto completo nem o entregue.")
del _p

PLUGIN_DA_TASK = dict((p["task"], p) for p in PLUGINS)

SAIDAS_DE_MODO = (
    {"cod": "fast", "infixo": "FAST_", "sufixo": "_ai",
     "nome": "Radioterapia.ai_OAR_Fast",
     "rotulo": u"entregue ao TPS (modo FAST) — o OAR sem a Bag_Bowel_OAR e "
               u"o Anus, compostos suavizados inteiros",
     "rotulo_curto": "OAR_Fast",
     "rotulo_dicom": "RadAI_OAR_Fast",
     "entregue": True, "agrupado": True, "suavizado": True,
     "desconta": True, "modo": "fast",
     "motor": "Radioterapia.AI / TotalSegmentator",
     "ajuda": (u"O conjunto entregue do modo FAST: as estruturas do OAR, "
               u"menos a Bag_Bowel_OAR e o Anus (que sai da Bag_Bowel, e o "
               u"FAST não monta as bags), montadas pelo mesmo "
               u"pós-processamento do FULL, mas com os compostos suavizados "
               u"inteiros e os pontos de cada contorno reduzidos. Não há FULL "
               u"ao lado dele.")},
)

POR_COD = dict((c["cod"], c)
               for c in CONJUNTOS + PLUGINS + SAIDAS_DE_MODO)
INFIXOS = tuple(c["infixo"] for c in CONJUNTOS + PLUGINS + SAIDAS_DE_MODO
                if c["infixo"])
SUFIXOS = tuple(c["sufixo"] for c in CONJUNTOS + PLUGINS)


TASKS_DO_FULL = (
    "total", "total_mr",
    "head_glands_cavities", "headneck_muscles", "headneck_bones_vessels",
    "head_muscles", "craniofacial_structures",
    "trunk_cavities", "breasts", "abdominal_muscles",
    # GUARDA: o derrame e anatomia do torax e alimenta o FULL; o plugin EFF_
    # saiu (o sufixo `_eff` fica em SUFIXOS_APOSENTADOS, para ler arquivo
    # antigo).
    "pleural_pericard_effusion",
)

ROTULOS_FORA_DO_FULL = {
    "craniofacial_structures": ("head",),
}

ROTULOS_SO_NO_FULL = {}


def _familia(task):
    try:
        import radai_tasks
        return radai_tasks.familia_da_task(task)
    except Exception:
        return task


def task_do_full(task):
    fam = _familia(task)
    return fam in TASKS_DO_FULL or task in TASKS_DO_FULL


def rotulo_vai_ao_full(task, rotulo):
    if not task_do_full(task):
        return False
    t = _familia(task) if _familia(task) in TASKS_DO_FULL else task
    if rotulo in ROTULOS_FORA_DO_FULL.get(t, ()):
        return False
    so = ROTULOS_SO_NO_FULL.get(t)
    if so is not None and rotulo not in so:
        return False
    return True


def rotulo_vai_ao_plugin(task, rotulo):
    if task not in PLUGIN_DA_TASK:
        return False
    if not task_do_full(task):
        return True
    return not rotulo_vai_ao_full(task, rotulo)


PERMITIDOS_NO_OAR = frozenset([
    "lung_left", "lung_right", "heart", "trachea", "esophagus",
    "great_arteries", "great_veins", "thyroid_gland",
    "sternum", "costal_cartilages", "ribs_left", "ribs_right",
    "Skin", "ChestWall_L", "ChestWall_R",
    "breast_left", "breast_right",
    "vertebrae_cervical", "vertebrae_thoracic", "vertebrae_lumbar",
    "spinal_cord",
    "liver", "spleen", "stomach", "pancreas", "gallbladder",
    "kidney_left", "kidney_right", "kidney_cyst_left", "kidney_cyst_right",
    "duodenum",
    "small_intestine", "colon", "rectum", "bag_bowel_oar",
    "urinary_bladder", "prostate",
    "femur_oar_left", "femur_oar_right",
    "bone_pelvic", "iliac_crest_left", "iliac_crest_right", "anus",
    "brain", "skull", "eye_left", "eye_right", "eye_lens_left",
    "eye_lens_right", "optic_nerve_left", "optic_nerve_right",
    # GUARDA: dos niveis cervicais so a uniao (nao e OAR nem CTV) e a
    # parotida do VIII (`radai_hnlnl.CHAVES_NO_OAR`); os Lvl_* nunca. A
    # parotida do TotalSegmentator nunca vai ao OAR: fica no FULL como _ts.
    "LNL_UNION", "parotid_lnl_left", "parotid_lnl_right",
    "submandibular_gland_left", "submandibular_gland_right",
    "hard_palate", "soft_palate", "nasal_cavity", "nasopharynx",
    "oropharynx", "hypopharynx", "auditory_canal_left",
    "auditory_canal_right", "pharyngeal_constrictor_superior",
    "pharyngeal_constrictor_middle", "pharyngeal_constrictor_inferior",
    "larynx_air", "thyroid_cartilage", "cricoid_cartilage", "hyoid",
    "zygomatic_arch_left", "zygomatic_arch_right",
    "styloid_process_left", "styloid_process_right",
    "masseter_left", "masseter_right", "temporalis_left", "temporalis_right",
    "lateral_pterygoid_left", "lateral_pterygoid_right",
    "medial_pterygoid_left", "medial_pterygoid_right", "tongue",
    "digastric_left", "digastric_right", "mandible", "teeth_upper",
    "teeth_lower", "sinus_maxillary", "sinus_frontal",
    "brain_brainstem", "brain_cerebellum", "caudate_nucleus",
    "central_sulcus", "frontal_lobe", "insular_cortex", "internal_capsule",
    "lentiform_nucleus", "occipital_lobe", "parietal_lobe",
    "septum_pellucidum", "subarachnoid_space", "temporal_lobe", "thalamus",
    "venous_sinuses", "ventricle",
    "optic_chiasm",
])

FORA_DO_OAR_FAST = frozenset(["bag_bowel_oar", "anus"])
PERMITIDOS_NO_OAR_FAST = frozenset(PERMITIDOS_NO_OAR - FORA_DO_OAR_FAST)

# GUARDA: chave que substitui -> chave substituida, com o MESMO nome no TPS.
# O "x" numa vale para as duas, e a previa mostra uma linha so; sem isto o
# "x" na linha errada deixava o OAR com a parotida, ou sem ela, calado.
MESMA_ROI_NO_OAR = {"parotid_lnl_left": "parotid_gland_left",
                    "parotid_lnl_right": "parotid_gland_right"}


def chaves_da_mesma_roi(chave):
    fora = [chave]
    for nova, velha in (MESMA_ROI_NO_OAR or {}).items():
        if chave == nova and velha not in fora:
            fora.append(velha)
        elif chave == velha and nova not in fora:
            fora.append(nova)
    return fora


SUFIXOS_VIVOS = tuple(c["sufixo"] for c in CONJUNTOS + PLUGINS)

SUFIXOS_APOSENTADOS = (
    "_v3D",
    "_pel",
    "_tx",
    "_eff",
    "_der",
    "_abm",
)

SUFIXOS_DE_TODAS_AS_GERACOES = tuple(sorted(
    set(s.lower() for s in SUFIXOS_VIVOS) |
    set(s.lower() for s in SUFIXOS_APOSENTADOS),
    key=lambda s: (-len(s), s)))


def raiz_sem_sufixo(nome):
    n = str(nome or "").strip().lower()
    for s in SUFIXOS_DE_TODAS_AS_GERACOES:
        if n.endswith(s):
            return n[: -len(s)]
    return n

INFIXOS_DE_OUTRO_CONSUMIDOR = ("TX_",)

SEM_DATA = "semdata"


def data_do_nome(serie):
    try:
        s = serie or {}
        if s.get("data_da_pasta"):
            return SEM_DATA
        d = (u"%s" % (s.get("date") or u""))[:8]
        if len(d) == 8 and d.isdigit() and d != u"00000000":
            return d
    except Exception:
        pass
    return SEM_DATA

INFIXOS_HISTORICOS = INFIXOS_DE_OUTRO_CONSUMIDOR


def desconto_do_entregue():
    return bool(POR_COD["oar"].get("desconta", False))


def nome_do_arquivo(cod, data, curto):
    c = POR_COD[cod]
    s = u"%s" % (curto or u"")
    if (not s) or any(ch in s for ch in ("/", "\\", ":")) or s in (".", ".."):
        raise ValueError(
            "sufixo de UID invalido para nome de arquivo: %r" % (curto,))
    return "RS_RadAI_%s%s_%s.dcm" % (c["infixo"], data or SEM_DATA, s)


def nome_parcial(alvo):
    import os
    import socket
    quem = ""
    try:
        quem = os.environ.get("COMPUTERNAME") or socket.gethostname() or ""
    except Exception:
        quem = ""
    bruto = str(quem)
    quem = "".join(c for c in bruto
                   if (c.isascii() and c.isalnum()) or c in "-_")[:24]
    if quem != bruto:
        import hashlib
        quem = "%s%s" % (quem, hashlib.md5(
            bruto.encode("utf-8", "replace")).hexdigest()[:4])
    return "%s.%s.%d.parcial" % (alvo, quem or "maquina", os.getpid())


def arquivos_da_serie(nomes, uid):
    curto = (u"%s" % (uid or u""))[-8:].lower()
    if not curto:
        return []
    cauda = u"_%s.dcm" % curto
    fora = []
    for n in (nomes or ()):
        s = u"%s" % n
        if s.startswith(u"RS_RadAI_") and s.lower().endswith(cauda):
            fora.append(s)
    return fora


def do_arquivo(nome):
    base = str(nome or "")
    if not base.startswith("RS_RadAI_"):
        return None
    resto = base[len("RS_RadAI_"):]
    for c in CONJUNTOS + PLUGINS + SAIDAS_DE_MODO:
        if c["infixo"] and resto.startswith(c["infixo"]):
            return c
    for h in INFIXOS_DE_OUTRO_CONSUMIDOR:
        if resto.startswith(h):
            return {"cod": "torax", "infixo": h, "sufixo": "",
                    "nome": u"tórax (cru)", "rotulo_curto": u"tórax",
                    "rotulo": u"tórax: lobos e árvore, cru — gravado nas "
                              u"séries finas (≤3 mm) para o módulo torácico, "
                              u"que mede no cru",
                    "entregue": False, "agrupado": False, "suavizado": False,
                    "motor": "TotalSegmentator (rotulos crus)", "ajuda": ""}

    if len(resto) >= 8 and resto[:8].isdigit():
        return POR_COD["oar"]
    if resto.startswith(SEM_DATA + "_"):
        return POR_COD["oar"]
    return None


def e_entregue(nome):
    c = do_arquivo(nome)
    return bool(c and c.get("entregue"))


def rotulo(nome):
    c = do_arquivo(nome)
    return c["rotulo"] if c else str(nome)


# GUARDA: nome de ROI que arquivo de geracao anterior traz -> a chave de hoje.
# A lista so cresce: parar de gravar um nome nao e deixar de saber le-lo.
NOMES_DE_ROI_DE_GERACOES_ANTERIORES = {
    "Bag_Bowel_tst_ai": "bag_bowel_oar",
}


def chave_de_roi_antiga(nome):
    return NOMES_DE_ROI_DE_GERACOES_ANTERIORES.get(str(nome or "").strip())
