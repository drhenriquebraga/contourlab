# -*- coding: utf-8 -*-
import os

_LINHAS = [
    ("total_v3",                  "Corpo inteiro (117 estruturas)",
     117, "CT", False, [831, 832, 833, 834, 835], 1773, "nucleo"),
    ("total_v2",                  "Corpo inteiro — modelo de 2023 (117)",
     117, "CT", False, [291, 292, 293, 294, 295], 1170, "util"),
    ("head_glands_cavities",      "Glândulas e cavidades da cabeça",
     19,  "CT", False, [775], 231, "nucleo"),
    ("headneck_muscles",          "Músculos de cabeça e pescoço",
     23,  "CT", False, [778, 779], 461, "nucleo"),
    ("headneck_bones_vessels",    "Ossos e vasos de cabeça e pescoço",
     12,  "CT", False, [776], 231, "util"),
    ("total_mr",                  "Corpo inteiro em RM (50 estruturas)",
     50,  "MR", False, [850, 851], 464, "util"),
    ("head_muscles",              "Músculos da cabeça",
     11,  "CT", False, [777], 230, "situacional"),
    ("lung_vessels",              "Vasos e vias aéreas do pulmão (novo)",
     4,   "CT", False, [117], 230, "situacional"),
    ("lung_vessels_LEGACY",       "Vasos e vias aéreas (modelo clássico)",
     2,   "CT", False, [258], 231, "situacional"),
    ("trunk_cavities",            "Cavidades do tronco e mediastino",
     4,   "CT", False, [343], 233, "util"),
    ("pleural_pericard_effusion", "Derrame pleural e pericárdico",
     3,   "CT", False, [315], 234, "util"),
    ("hip_implant",               "Prótese de quadril",
     1,   "CT", False, [260], 233, "fora"),
    ("craniofacial_structures",   "Estruturas craniofaciais (mandíbula, crânio, seios)",
     7,   "CT", False, [115], 230, "nucleo"),
    ("oculomotor_muscles",        "Órbita: músculos extraoculares e nervos ópticos",
     19,  "CT", False, [351], 231, "nucleo"),
    ("breasts",                   "Mamas (parênquima mamário)",
     1,   "CT", False, [527], 234, "util"),
    ("vertebrae_body",            "Corpo vertebral e discos",
     2,   "CT", False, [305], 234, "util"),
    ("lung_nodules",              "Nódulos pulmonares",
     2,   "CT", False, [913], 765, "situacional"),


    ("abdominal_muscles",         "Musculatura da parede abdominal e do dorso",
     22,  "CT", False, [952], 124, "util"),

    ("liver_segments",            "Segmentos hepáticos de Couinaud (I-VIII)",
     8,   "CT", False, [570], 230, "util"),

    ("liver_segments_mr",         "Segmentos hepáticos de Couinaud em RM (I-VIII)",
     8,   "MR", False, [576], 230, "util"),

    ("vertebrae_mr",              "Vértebras C1-L5 em RM",
     25,  "MR", False, [756], 231, "util"),

    ("teeth",                     "Dentes, polpas e canais (numeração FDI)",
     77,  "CT", False, [113], 232, "situacional"),

    ("liver_lesions",             "Lesões hepáticas — ACHADO",
     1,   "CT", False, [591], 231, "situacional"),
    ("liver_lesions_mr",          "Lesões hepáticas em RM — ACHADO",
     1,   "MR", False, [589], 231, "situacional"),
]

EXIGEM_TS = {}

CATALOGO = [{"task": t, "rotulo": r, "classes": c, "modalidade": m,
             "comercial": lic, "datasets": ds, "mb": mb, "rt": rt}
            for (t, r, c, m, lic, ds, mb, rt) in _LINHAS]


NOME_NA_BIBLIOTECA = {
    "total_v2": "total",
}


def nome_na_biblioteca(task):
    return NOME_NA_BIBLIOTECA.get(task, task)


FAMILIA = {
    "total": "total",
    "total_v2": "total",
    "total_v3": "total",
}


def familia_da_task(task):
    return FAMILIA.get(task, task)


BASES_CT = ("total_v3", "total_v2")
BASES_MR = ("total_mr",)

RESERVAS = frozenset(BASES_CT[1:]) | frozenset(BASES_MR[1:])


APELIDOS = {"total": "total_v3"}


def traduzir_apelidos(tasks):
    return [APELIDOS.get(str(t).strip(), str(t).strip()) for t in tasks]


def base_no_disco(modalidade="CT", pasta_pesos=None, log=None):
    ordem = BASES_MR if str(modalidade).upper() == "MR" else BASES_CT
    if not ordem:
        return None
    try:
        no_disco = set(baixados(pasta_pesos))
    except Exception:
        return ordem[0]
    for t in ordem:
        precisa = set(datasets_necessarios(t, recorte_no_corpo=False))
        if precisa and precisa <= no_disco:
            if t != ordem[0] and callable(log):
                log("base anatomica: %s (a %s nao esta instalada nesta "
                    "estacao)" % (t, ordem[0]))
            return t
    return ordem[0]


def lista_para_rodar(tarefas, pasta_pesos=None, log=None):
    saida, vistos = [], set()
    for t in list(tarefas or []):
        modal = modalidade_da_base(t)
        if modal:
            ordem = BASES_MR if modal == "MR" else BASES_CT
            if ordem and t == ordem[0]:
                t = base_no_disco(modal, pasta_pesos, log=log) or t
        fam = familia_da_task(t)
        if fam in vistos:
            if callable(log):
                log("task ignorada: %s ja roda como %s (mesma familia)"
                    % (t, saida[[familia_da_task(x) for x in saida].index(fam)]))
            continue
        vistos.add(fam)
        saida.append(t)
    return saida


def modalidade_da_base(task):
    if task in BASES_CT:
        return "CT"
    if task in BASES_MR:
        return "MR"
    return None


def tasks_da_serie(tarefas, modalidade, pasta_pesos=None, log=None):
    modal = "MR" if str(modalidade or "").strip().upper() in ("MR", "RM") \
        else "CT"
    ordem = BASES_MR if modal == "MR" else BASES_CT
    base = base_no_disco(modal, pasta_pesos, log=log) or \
        (ordem[0] if ordem else None)
    fam_base = set(familia_da_task(t) for t in ordem)
    saida = []
    for t in traduzir_apelidos([x for x in list(tarefas or []) if x]):
        if not t:
            continue
        mb = modalidade_da_base(t)
        if mb:
            if mb != modal:
                if callable(log):
                    log("task %s e base de %s; nesta serie %s a base e %s"
                        % (t, mb, modal, base))
                t = base
            elif ordem and t == ordem[0]:
                t = base
        else:
            d = POR_NOME.get(t)
            if d is not None:
                m_t = str(d.get("modalidade") or "CT").upper()
                if m_t != modal:
                    if callable(log):
                        log("task %s e de %s; nao roda nesta serie %s"
                            % (t, m_t, modal))
                    continue
        if t:
            saida.append(t)
    tem_base = [t for t in saida if familia_da_task(t) in fam_base]
    if not tem_base and base:
        saida.insert(0, base)
    elif tem_base:
        primeira = tem_base[0]
        saida.remove(primeira)
        saida.insert(0, primeira)
    final, vistos = [], set()
    for t in saida:
        fam = familia_da_task(t)
        if fam in vistos:
            if callable(log):
                log("task ignorada: %s ja roda como %s (mesma familia)"
                    % (t, [x for x in final
                           if familia_da_task(x) == fam][0]))
            continue
        vistos.add(fam)
        final.append(t)
    return final


def reserva_de(task):
    for ordem in (BASES_CT, BASES_MR):
        if task in ordem:
            i = ordem.index(task)
            if i + 1 < len(ordem):
                return ordem[i + 1]
            return None
    return None

USOS_RT = ("nucleo", "util", "situacional", "fora")

AJUDA_RT = {
    "nucleo": u"OAR de rotina — entra sempre",
    "util": u"entra quando o serviço trata aquele sítio",
    "situacional": u"caso específico; pesa o mesmo e rende pouco",
    "fora": u"diagnóstico ou QA — não é estrutura de planejamento",
}

CONTRASTE_TASK = {
    "total_v3": "misto",
    "total_v2": "misto",
    "head_glands_cavities": "nao",
    "headneck_muscles": "ajuda",

    "headneck_bones_vessels": "misto",
    "coronary_arteries": "exige",
    "total_mr": "nao",
    "head_muscles": "ajuda",
    "craniofacial_structures": "nao",
    "oculomotor_muscles": "nao",
    "lung_vessels": "ajuda",
    "lung_nodules": "nao",
    "lung_vessels_LEGACY": "ajuda",
    "ventricle_parts": "nao",
    "breasts": "ajuda",
    "kidney_cysts": "exige",
    "trunk_cavities": "ajuda",
    "pleural_pericard_effusion": "nao",
    "liver_vessels": "exige",
    "hip_implant": "nao",
    "brain_structures": "ajuda",
    "heartchambers_highres": "exige",
    "vertebrae_body": "nao",
    "appendicular_bones": "nao",
    "tissue_types": "nao",
    "face": "nao",
    "tissue_types_mr": "nao",
    "face_mr": "nao",
    "abdominal_muscles": "nao",
    "teeth": "nao",
    "vertebrae_mr": "nao",
    "liver_lesions_mr": "nao",
    "liver_segments_mr": "nao",
    "liver_segments": "ajuda",
    "liver_lesions": "exige",
}

CONTRASTE_ESTRUTURA = {
    "portal_vein_and_splenic_vein": "exige",
    "pulmonary_vein": "exige",
    "atrial_appendage_left": "exige",
    "common_carotid_artery_left": "exige",
    "common_carotid_artery_right": "exige",
    "brachiocephalic_trunk": "exige",
    "brachiocephalic_vein_left": "exige",
    "brachiocephalic_vein_right": "exige",
    "subclavian_artery_left": "exige",
    "subclavian_artery_right": "exige",
    "kidney_cyst_left": "ajuda",
    "kidney_cyst_right": "ajuda",
    "carotids": "exige",
    "pancreas": "ajuda",
    "duodenum": "ajuda",
    "adrenal_gland_left": "ajuda",
    "adrenal_gland_right": "ajuda",
    "small_bowel": "ajuda",
    "colon": "ajuda",
    "esophagus": "ajuda",
    "aorta": "ajuda",
    "inferior_vena_cava": "ajuda",
    "iliac_artery_left": "ajuda",
    "iliac_artery_right": "ajuda",
    "iliac_vena_left": "ajuda",
    "iliac_vena_right": "ajuda",
    "great_vessels": "ajuda",
    "spleen": "ajuda",
    "liver": "ajuda",
    "kidney_left": "ajuda",
    "kidney_right": "ajuda",
    "gallbladder": "ajuda",
    "prostate": "ajuda",
    "urinary_bladder": "ajuda",
}

_TG263_CONTRASTE = {
    "carotids": "exige", "a_carotid_l": "exige", "a_carotid_r": "exige",
    "greatvessels": "ajuda", "a_aorta": "ajuda", "v_venacava_i": "ajuda",
    "kidney_l": "ajuda", "kidney_r": "ajuda",
    "adrenal_l": "ajuda", "adrenal_r": "ajuda",
    "bowel_large": "ajuda", "bowel_small": "ajuda",
    "bladder": "ajuda", "prostate": "ajuda",
    "esophagus": "ajuda", "liver": "ajuda", "spleen": "ajuda",
    "pancreas": "ajuda", "duodenum": "ajuda", "gallbladder": "ajuda",
}

AJUDA_CONTRASTE = {
    "nao": u"não depende de contraste",
    "ajuda": u"sai sem contraste; com contraste fica melhor",
    "exige": u"sem contraste o limite não está na imagem — contorno não confiável",
    "misto": u"depende da estrutura",
}


def _raiz_e_lado(nome):
    n = str(nome or "").strip().lower()
    try:
        import radai_sets
        n = radai_sets.raiz_sem_sufixo(n)
    except Exception:
        for sufixo in ("_ai", "_v3d"):
            if n.endswith(sufixo):
                n = n[:-len(sufixo)]
                break
    for sufixo, lado in (("_left", "l"), ("_right", "r"),
                         ("_l", "l"), ("_r", "r")):
        if n.endswith(sufixo):
            return n[:-len(sufixo)].strip("_"), lado
    return n.strip("_"), ""


_INDICE_CONTRASTE = {}
for _tabela in (CONTRASTE_ESTRUTURA, _TG263_CONTRASTE):
    for _chave, _nivel in _tabela.items():
        _INDICE_CONTRASTE[_raiz_e_lado(_chave)] = _nivel

_MIN_PREFIXO = 5


def contraste_da_estrutura(nome):
    raiz, lado = _raiz_e_lado(nome)
    if not raiz:
        return "nao"
    if (raiz, lado) in _INDICE_CONTRASTE:
        return _INDICE_CONTRASTE[(raiz, lado)]
    if (raiz, "") in _INDICE_CONTRASTE:
        return _INDICE_CONTRASTE[(raiz, "")]
    if len(raiz) < _MIN_PREFIXO:
        return "nao"
    achados = set()
    for (r, l), nivel in _INDICE_CONTRASTE.items():
        if r.startswith(raiz) and (lado == "" or l == "" or l == lado):
            achados.add(nivel)
    for nivel in ("exige", "ajuda"):
        if nivel in achados:
            return nivel
    return "nao"


def estruturas_que_exigem_contraste():
    return sorted(k for k, v in CONTRASTE_ESTRUTURA.items() if v == "exige")


def detectar_contraste(pasta):
    try:
        import pydicom
    except ImportError:
        return None, "pydicom ausente neste runtime"
    try:
        arquivos = [os.path.join(pasta, f) for f in sorted(os.listdir(pasta))]
    except OSError as e:
        return None, "nao consegui ler a pasta: %s" % e
    for caminho in arquivos[:40]:
        if not os.path.isfile(caminho):
            continue
        try:
            d = pydicom.dcmread(caminho, stop_before_pixels=True, force=True)
        except Exception:
            continue
        if not getattr(d, "SOPClassUID", None):
            continue
        agente = str(getattr(d, "ContrastBolusAgent", "") or "").strip()
        if agente:
            return True, "ContrastBolusAgent = %s" % agente[:40]
        if str(getattr(d, "ContrastBolusStartTime", "") or "").strip():
            return True, "ContrastBolusStartTime preenchida"
        return False, "ContrastBolusAgent vazia no cabecalho"
    return None, "nenhum DICOM legivel na pasta"


def alertas_de_contraste(estruturas, tem_contraste):
    if tem_contraste is not False:
        return []
    saida = []
    for nome in estruturas or []:
        nivel = contraste_da_estrutura(nome)
        if nivel == "exige":
            saida.append({"estrutura": nome, "nivel": nivel,
                          "aviso": AJUDA_CONTRASTE["exige"]})
    return saida

POR_NOME = {d["task"]: d for d in CATALOGO}

Z_DO_MODELO = {
    "craniofacial_structures": 0.50,
    "oculomotor_muscles": 0.85,
    "head_glands_cavities": 1.00,
    "headneck_muscles": 1.00,
    "headneck_bones_vessels": 1.00,
    "head_muscles": 1.00,
    "lung_vessels": 1.00,
    "trunk_cavities": 1.50,
    "breasts": 1.50,
    "lung_nodules": 1.50,
    "teeth": 0.50,
    "abdominal_muscles": 1.00,
    "liver_lesions": 1.00,
    "liver_lesions_mr": 1.00,
    "liver_segments": 1.50,
    "vertebrae_mr": 1.50,
    "liver_segments_mr": 3.00,
}


def desproporcao_de_resolucao(task, espessura_mm):
    z = Z_DO_MODELO.get(task)
    try:
        e = float(espessura_mm)
    except (TypeError, ValueError):
        return None
    if not z or e <= 0:
        return None
    return e / z


CUSTOS = ("leve", "medio", "pesado")

AJUDA_CUSTO = {
    "leve":   u"roda num recorte, em grade grossa",
    "medio":  u"roda num recorte, mas em grade fina",
    "pesado": u"roda sem localizar um órgão antes, sobre o corpo inteiro "
              u"ou a série inteira",
}

ROTULO_CUSTO = {
    "leve":   u"rápida",
    "medio":  u"intermediária",
    "pesado": u"demorada",
}


def custo_relativo(task):
    if task not in POR_NOME:
        return None
    if not RECORTAM.get(task):
        return "pesado"
    z = Z_DO_MODELO.get(task)
    if z is None:
        return "medio"
    return "medio" if z < 1.0 else "leve"


VELOCIDADES = ("fast", "regular", "slow", "ultra-slow")
REFERENCIA_DE_VELOCIDADE = "total_v3"
CORTES_DE_VELOCIDADE = ((0.25, "fast"), (0.75, "regular"), (2.0, "slow"))
ESTIMATIVA_PELO_CUSTO = {"leve": "fast", "medio": "regular", "pesado": "slow"}

TEMPO_MEDIDO = {
    "total_v3": {"razao": 1.0, "cota": False,
                 "fonte": u"a referência: 1.324,2 s na P20 (24/09/2026, "
                          u"--body_seg, CPU disputada)"},
    "trunk_cavities": {"razao": 746.0 / 1324.2, "cota": False,
                       "fonte": u"746,0 s contra 1.324,2 s da base, P20 "
                                u"(24/09/2026; P19: 420,2 s)"},
    "breasts": {"razao": 883.1 / 1324.2, "cota": False,
                "fonte": u"883,1 s contra 1.324,2 s da base, P20 "
                         u"(24/09/2026; P19: 451,8 s)"},
    "abdominal_muscles": {"razao": 3464.6 / 1324.2,
                          "cota": False,
                          "fonte": u"3.464,6 s contra 1.324,2 s da base, P20 "
                                   u"(24/09/2026, envelope consertado, CPU "
                                   u"disputada; a exportação levou 173 s "
                                   u"nesta série). Antes dela: ~2,12 bases "
                                   u"por ponte na P19 (1.582,6 s contra "
                                   u"420,2 s da trunk_cavities); e a "
                                   u"primeira rodada, pelo pipe antigo, "
                                   u"falhou na exportação depois de "
                                   u"5.750,5 s na P20"},
}


def velocidade_da_razao(razao):
    try:
        r = float(razao)
    except (TypeError, ValueError):
        return None
    for teto, tag in CORTES_DE_VELOCIDADE:
        if r < teto:
            return tag
    return "ultra-slow"


def velocidade(task):
    if task not in POR_NOME:
        return None
    m = TEMPO_MEDIDO.get(task)
    if m:
        return {"tag": velocidade_da_razao(m["razao"]), "medida": True,
                "razao": round(float(m["razao"]), 2),
                "cota": bool(m.get("cota")), "ponte": bool(m.get("ponte")),
                "fonte": m.get("fonte") or u""}
    c = custo_relativo(task)
    tag = ESTIMATIVA_PELO_CUSTO.get(c)
    if not tag:
        return None
    return {"tag": tag, "medida": False, "razao": None, "cota": False,
            "ponte": False, "fonte": u""}


def peso_em_bases(task):
    try:
        v = velocidade(task)
    except Exception:
        v = None
    if not v:
        return 1.0
    if v.get("medida") and v.get("razao") is not None:
        return float(v["razao"])
    for teto, tag in CORTES_DE_VELOCIDADE:
        if tag == v.get("tag"):
            return float(teto)
    return 1.0


def rotulo_de_velocidade(v):
    if not v or not v.get("tag"):
        return u""
    return (u"" if v.get("medida") else u"~") + v["tag"]


Z_DA_ROTINA = 3.0


def pede_corte_fino(task):
    z = Z_DO_MODELO.get(task)
    if not z or z >= Z_DA_ROTINA:
        return None
    return z, Z_DA_ROTINA / z


def _mm(v):
    return (u"%.2f mm" % float(v)).replace(u".", u",")


def _campo_de_trabalho(task, recorte_no_corpo=None):
    if RECORTAM.get(task):
        return u"recorta antes de rodar"
    if not recorte_no_corpo_se_aplica(task)[0]:
        return u"a série inteira"
    if recorte_no_corpo is False or not pesos_do_recorte_no_corpo()[0]:
        return u"a série inteira"
    if recorte_no_corpo is None:
        return u"só o corpo, quando o recorte no corpo está ligado"
    return u"só o corpo, sem o ar em volta"


def ficha(task, entregues=None, recorte_no_corpo=None):
    d = POR_NOME.get(task)
    if not d:
        return []
    fora = []

    def por(rot, val, frase=False):
        if val in (None, u"", []):
            return
        fora.append({"rot": rot, "val": val, "frase": bool(frase)})

    por(u"modelo", u"TotalSegmentator")
    ds = [u"Dataset%s" % n for n in (d.get("datasets") or ())]
    por(u"conjunto de dados", u", ".join(ds))
    por(u"estruturas do modelo", u"%d" % d["classes"] if d.get("classes")
        else None)
    if entregues is not None:
        por(u"no conjunto entregue", u"%d" % int(entregues))
    por(u"peso do modelo", u"%d MB" % d["mb"] if d.get("mb") else None)

    z = Z_DO_MODELO.get(task)
    por(u"espaçamento do modelo",
        _mm(z) if z else u"não medido", frase=not z)

    fino = pede_corte_fino(task)
    if fino:
        _z, fator = fino
        por(u"mais fino que a rotina",
            (u"%d×" % round(fator)) if abs(fator - round(fator)) < 0.05
            else (u"%.1f×" % fator).replace(u".", u","))
        por(u"o que isso quer dizer",
            u"treinado em corte mais fino que a TC de planejamento",
            frase=True)

    por(u"campo de trabalho", _campo_de_trabalho(task, recorte_no_corpo),
        frase=True)

    c = CONTRASTE_TASK.get(task)
    por(u"contraste", AJUDA_CONTRASTE.get(c), frase=True)
    por(u"uso em radioterapia", AJUDA_RT.get(d.get("rt")), frase=True)

    custo = custo_relativo(task)
    if custo:
        por(u"custo relativo", ROTULO_CUSTO[custo], frase=True)
        por(u"por quê", AJUDA_CUSTO[custo], frase=True)

    vel = velocidade(task)
    if vel:
        por(u"velocidade", rotulo_de_velocidade(vel))
        if vel["medida"]:
            por(u"tempo contra a base",
                (u"≥ " if vel["cota"] else u"")
                + (u"%.2f×" % vel["razao"]).replace(u".", u","))
            if vel["cota"]:
                _de_onde = (u"medida até a falha: a task não terminou, e o "
                            u"tempo verdadeiro é maior")
            elif vel.get("ponte"):
                _de_onde = (u"medida por ponte: contra outra task da mesma "
                            u"série, e essa contra a base")
            else:
                _de_onde = (u"medida contra a base, na mesma série e na "
                            u"mesma máquina")
            por(u"de onde vem a velocidade", _de_onde, frase=True)
        else:
            por(u"de onde vem a velocidade",
                u"estimada pela forma do modelo; não medida", frase=True)
    return fora


DATASET_RECORTE = 298
DATASET_RECORTE_ROBUSTO = 297
DATASET_BODY = 300
DATASET_RECORTE_MR = 852

RECORTAM = {
    "head_glands_cavities":     (DATASET_RECORTE,),
    "headneck_bones_vessels":   (DATASET_RECORTE,),
    "head_muscles":             (DATASET_RECORTE,),
    "headneck_muscles":         (DATASET_RECORTE,),
    "lung_vessels":             (DATASET_RECORTE_ROBUSTO,),
    "pleural_pericard_effusion": (DATASET_RECORTE,),
    "hip_implant":              (DATASET_RECORTE,),
    "lung_vessels_LEGACY":      (DATASET_RECORTE,),
    "craniofacial_structures":  (DATASET_RECORTE,),
    "oculomotor_muscles":       (DATASET_RECORTE,),
    "lung_nodules":             (DATASET_RECORTE,),
    "liver_segments":           (DATASET_RECORTE,),
    "abdominal_muscles":        (DATASET_BODY,),
    "liver_lesions":            (DATASET_RECORTE_ROBUSTO,),
    "liver_lesions_mr":         (DATASET_RECORTE_MR,),
    "liver_segments_mr":        (DATASET_RECORTE_MR,),
    "teeth":                    (115, DATASET_RECORTE),
    "coronary_arteries":        (DATASET_RECORTE,),
    "liver_vessels":            (DATASET_RECORTE,),
    "brain_structures":         (DATASET_RECORTE,),
    "heartchambers_highres":    (DATASET_RECORTE_ROBUSTO,),
}

SEM_RECORTE = frozenset([
    "total_v3", "total_v2", "total_mr",
    "breasts", "trunk_cavities", "vertebrae_body", "vertebrae_mr",
])

CUSTO_DO_RECORTE = {
    DATASET_RECORTE: 135,
    DATASET_RECORTE_ROBUSTO: 135,
    DATASET_BODY: 124,
    DATASET_RECORTE_MR: 126,
    115: 230,
}

PADRAO = ["total_v3"]


def pasta_pesos(amb=None):
    amb = os.environ if amb is None else amb
    p = str(amb.get("TOTALSEG_WEIGHTS_PATH") or "").strip()
    if p:
        return p
    casa = str(amb.get("TOTALSEG_HOME_DIR") or "").strip()
    if casa:
        return os.path.join(casa, "nnunet", "results")
    return os.path.join(os.path.expanduser("~"), ".totalsegmentator",
                        "nnunet", "results")


def _pastas_no_disco(base=None):
    base = base if base is not None else pasta_pesos()
    try:
        return [d for d in os.listdir(base) if os.path.isdir(os.path.join(base, d))]
    except OSError:
        return []


def _numero_do_dataset(nome):
    if not nome.startswith("Dataset"):
        return None
    digitos = nome[7:10]
    return int(digitos) if digitos.isdigit() else None


def baixados(base=None):
    achados = set()
    for d in _pastas_no_disco(base):
        n = _numero_do_dataset(d)
        if n is not None:
            achados.add(n)
    return achados


DATASET_DO_BODY_PASTA = "Dataset300_body_6mm_1559subj"
PESO_DO_BODY = os.path.join("nnUNetTrainer__nnUNetPlans__3d_fullres",
                            "fold_0", "checkpoint_final.pth")


def recorte_no_corpo_se_aplica(task):
    t = APELIDOS.get(str(task).strip(), str(task).strip())
    d = POR_NOME.get(t)
    if d is None:
        return False, (u"a task nao esta no catalogo: nao sei se ela ja "
                       u"recorta por conta propria")
    if (str(d.get("modalidade") or "CT").upper() == "MR"
            or nome_na_biblioteca(t).endswith("_mr")):
        return False, (u"RM: a biblioteca ignora o --body_seg em task _mr "
                       u"(python_api.py:342-345)")
    loc = RECORTAM.get(t)
    if loc:
        return False, (u"a task ja recorta no proprio localizador (%s)"
                       % u", ".join(u"Dataset%s" % n for n in loc))
    if t not in SEM_RECORTE:
        return False, (u"a task nao esta classificada em RECORTAM nem em "
                       u"SEM_RECORTE: nao sei se ela recorta")
    return True, u""


def pesos_do_recorte_no_corpo(pasta=None):
    base = pasta if pasta is not None else pasta_pesos()
    dirp = os.path.join(base, DATASET_DO_BODY_PASTA)
    try:
        if not os.path.isdir(dirp):
            return False, u"a pasta %s nao existe em %s" % (
                DATASET_DO_BODY_PASTA, base)
        if not os.path.isfile(os.path.join(dirp, PESO_DO_BODY)):
            return False, (u"a pasta %s existe e o peso dela nao (%s) — "
                           u"download interrompido?" % (DATASET_DO_BODY_PASTA,
                                                        PESO_DO_BODY))
    except Exception as e:
        return False, u"nao consegui olhar %s (%s)" % (dirp, type(e).__name__)
    return True, u"Dataset%d presente em %s" % (DATASET_BODY, base)


def datasets_necessarios(task, recorte_no_corpo=True):
    d = POR_NOME.get(task)
    if not d:
        return []
    extra = [n for n in RECORTAM.get(task, ()) if n not in d["datasets"]]
    fora = list(d["datasets"]) + extra
    if (recorte_no_corpo and DATASET_BODY not in fora
            and recorte_no_corpo_se_aplica(task)[0]):
        fora.append(DATASET_BODY)
    return fora


def datasets_do_pacote(tasks):
    fora = []
    for t in normalizar(tasks):
        for n in datasets_necessarios(t):
            if n not in fora:
                fora.append(n)
    return fora


def _ofertaveis():
    return tuple(d for d in CATALOGO if d["task"] not in RESERVAS)


def estado(base=None):
    presentes = baixados(base)
    saida = []
    for d in _ofertaveis():
        exigidos = datasets_necessarios(d["task"])
        faltando = [n for n in exigidos if n not in presentes]
        proprios = [n for n in d["datasets"] if n not in presentes]
        item = dict(d)
        item["exigidos"] = exigidos
        item["baixado"] = bool(exigidos) and not faltando
        item["parcial"] = bool(proprios) and len(proprios) < len(d["datasets"])
        item["faltando"] = faltando
        item["recorta"] = d["task"] in RECORTAM
        item["permitida"], item["porque_nao"] = _permissao(d["task"])

        item["achado"] = _e_achado(d["task"])

        exige = EXIGEM_TS.get(d["task"])
        if exige:
            item["disponivel"] = False
            item["exige_ts"] = exige
            item["porque_indisponivel"] = (
                u"exige o TotalSegmentator %s ou mais novo; este pacote traz "
                u"a 2.4.0, que nao tem esta biblioteca. Ela aparece aqui para "
                u"voce saber que existe -- ligar depende de atualizar o "
                u"motor, que e decisao do servico." % exige)
        else:
            item["disponivel"] = True
            item["exige_ts"] = u""
            item["porque_indisponivel"] = u""
        saida.append(item)
    return saida


def _e_achado(task):
    try:
        import engine
    except Exception:
        return None
    return task in getattr(engine, "TASKS_DE_ACHADO", frozenset())


def _permissao(task):
    try:
        import engine
    except Exception:
        return None, u""
    if task in getattr(engine, "TASKS_PERMITIDAS", {}):
        return True, u""
    motivo = getattr(engine, "TASKS_RECUSADAS", {}).get(task) or (
        u"nao foi validada nesta instalacao: o mapa de nomes nao a cobre, "
        u"entao as estruturas dela sairiam com o rotulo cru do modelo.")
    return False, motivo


def _arquivo_licenca():
    return os.path.join(os.path.expanduser("~"), ".totalsegmentator", "config.json")


def tem_licenca():
    try:
        import json
        with open(_arquivo_licenca(), encoding="utf-8") as f:
            return bool(str(json.load(f).get("license_number") or "").strip())
    except Exception:
        return False


def gravar_licenca(chave):
    chave = str(chave or "").strip()
    if not chave:
        raise ValueError("chave vazia")
    if not chave.lower().startswith("aca_"):
        raise ValueError(
            "a chave academica do TotalSegmentator comeca com 'aca_'. "
            "Confira em totalsegmentator.com — o que foi colado comeca com %r"
            % chave[:6])
    from totalsegmentator.config import set_license_number
    set_license_number(chave)
    if not tem_licenca():
        raise RuntimeError("gravei mas nao consegui reler de %s" % _arquivo_licenca())
    return {"ok": True, "arquivo": _arquivo_licenca(), "fim": chave[-4:]}


def baixar(task, base=None, aviso=None):
    d = POR_NOME.get(task)
    if not d:
        raise ValueError("task desconhecida: %s" % task)
    if d["comercial"] and not tem_licenca():
        raise RuntimeError(
            "a task %s exige chave de licenca do TotalSegmentator (gratuita "
            "para uso academico, em totalsegmentator.com). Sem a chave ela "
            "baixa mas nao roda." % task)

    from totalsegmentator.libs import download_pretrained_weights

    presentes = baixados(base)
    buscados = []
    for n in datasets_necessarios(task):
        if n in presentes:
            continue
        if aviso:
            aviso("baixando pesos do Dataset%d (%s)" % (n, task))
        download_pretrained_weights(n)
        buscados.append(n)
    return buscados


def resumo(base=None):
    e = estado(base)
    return {"pasta": base if base is not None else pasta_pesos(),
            "total": len(e),
            "baixadas": sum(1 for d in e if d["baixado"]),
            "livres": sum(1 for d in e if not d["comercial"]),
            "recorte_ok": DATASET_RECORTE in baixados(base),
            "recorte_no_corpo_ok": pesos_do_recorte_no_corpo(base)[0]}


def normalizar(texto_ou_lista):
    if isinstance(texto_ou_lista, (list, tuple, set)):
        cru = list(texto_ou_lista)
    else:
        cru = str(texto_ou_lista or "").replace(",", " ").split()
    cru = traduzir_apelidos(cru)
    vistas, saida = set(), []
    for t in cru:
        t = t.strip()
        if t in POR_NOME and t not in vistas:
            vistas.add(t)
            saida.append(t)
    return saida


def custo_mb(tasks, base=None):
    presentes = baixados(base)
    por_dataset = {}
    for t in normalizar(tasks):
        d = POR_NOME[t]
        proprios = d["datasets"]
        if not proprios or not d["mb"]:
            continue
        fatia = float(d["mb"]) / len(proprios)
        for n in proprios:
            por_dataset[n] = max(por_dataset.get(n, 0.0), fatia)
        for n in datasets_necessarios(t):
            if n in proprios:
                continue
            por_dataset.setdefault(n, float(CUSTO_DO_RECORTE.get(n, 135)))
    return int(round(sum(v for n, v in por_dataset.items() if n not in presentes)))


def sugerir(teto_mb=None, com_licenca=False, modalidades=("CT",), base=None):
    def cabe(d):
        if d["comercial"] and not com_licenca:
            return False
        return not modalidades or d["modalidade"] in modalidades

    escolhidas = [d["task"] for d in CATALOGO if d["rt"] == "nucleo" and cabe(d)]
    minimo = custo_mb(escolhidas, base)
    for uso in ("util", "situacional"):
        for d in CATALOGO:
            if d["rt"] != uso or d["task"] in escolhidas or not cabe(d):
                continue
            candidato = escolhidas + [d["task"]]
            if teto_mb is not None and custo_mb(candidato, base) > teto_mb:
                continue
            escolhidas.append(d["task"])
    total = custo_mb(escolhidas, base)
    return {"tasks": escolhidas, "mb": total, "teto_mb": teto_mb,
            "mb_nucleo": minimo,
            "estourou": teto_mb is not None and total > teto_mb,
            "fora": [d["task"] for d in CATALOGO
                     if d["task"] not in escolhidas and d["rt"] != "fora"]}


def _recortes_divergentes():
    try:
        from totalsegmentator.map_tasks_config import TASK_CONFIGS
    except Exception:
        return []

    def bruto(t):
        r = TASK_CONFIGS[t]
        return r["sub_modes"]["default"] if "sub_modes" in r else r

    def alvo(t, visto=()):
        if t in visto or t not in TASK_CONFIGS:
            return ()
        c = bruto(t)
        if not c.get("crop"):
            return ()
        if c.get("crop_model"):
            filho = c["crop_model"]
            proprio = bruto(filho).get("task_id")
            proprio = tuple(proprio) if isinstance(proprio, list) else (proprio,)
            return proprio + alvo(filho, visto + (t,))
        if c.get("robust_crop"):
            return (DATASET_RECORTE_MR,) if t.endswith("_mr") \
                else (DATASET_RECORTE_ROBUSTO,)
        if t.endswith("_mr"):
            return (DATASET_RECORTE_MR,)
        crop = c["crop"]
        if "body_trunc" in crop or "body_extremities" in crop:
            return (DATASET_BODY,)
        return (DATASET_RECORTE,)

    fora = []
    for t in sorted(set(POR_NOME) | set(RECORTAM)):
        if t not in TASK_CONFIGS:
            continue
        esperado = tuple(sorted(alvo(t)))
        declarado = tuple(sorted(RECORTAM.get(t, ())))
        if esperado != declarado:
            fora.append((t, esperado, declarado))
    return fora


def conferir_contra_biblioteca():
    try:
        from totalsegmentator.map_to_binary import class_map
    except Exception:
        return True, ["biblioteca ausente: nada a comparar"]

    ignorar = {"test", "total_v1", "covid"}
    da_lib = {t for t in class_map if not t.endswith("_auxiliary") and t not in ignorar}
    meus = {nome_na_biblioteca(t): t for t in POR_NOME}
    if len(meus) != len(POR_NOME):
        _perdidas = sorted(set(POR_NOME) - set(meus.values()))
        divergencias_de_nome = [
            "colisao em nome_na_biblioteca: %s some desta conferencia"
            % ", ".join(_perdidas)]
    else:
        divergencias_de_nome = []
    divergencias, informativas = [], []
    for t in sorted(da_lib - set(meus)):
        informativas.append(
            "task no TotalSegmentator que o catalogo nao oferece (decisao "
            "nossa, nao e defeito): %s" % t)
    divergencias.extend(divergencias_de_nome)
    for t in sorted(set(meus) - da_lib):
        divergencias.append("task no catalogo que a biblioteca nao tem mais: %s"
                            % meus[t])
    for t in sorted(set(meus) & da_lib):
        n = len(class_map[t])
        if n != POR_NOME[meus[t]]["classes"]:
            divergencias.append("%s: catalogo diz %d classes, biblioteca diz %d"
                                % (meus[t], POR_NOME[meus[t]]["classes"], n))
    for t, esperado, declarado in _recortes_divergentes():
        divergencias.append(
            "%s: o upstream recorta no %s e a tabela declara %s"
            % (t, list(esperado) or "nenhum", list(declarado) or "nenhum"))
    if divergencias:
        return False, divergencias + informativas
    resumo = ("catalogo bate com a biblioteca (%d tasks no catalogo; %d "
              "tasks da biblioteca ficam de fora por decisao)"
              % (len(meus), len(informativas)))
    return True, [resumo] + informativas
