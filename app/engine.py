import os, sys, re, gc, time, uuid, shutil, tempfile, zipfile, threading, traceback
import math
from pathlib import Path

import numpy as np
import SimpleITK as sitk
import pydicom
from pydicom.uid import generate_uid
from scipy.ndimage import gaussian_filter, zoom as ndzoom
from rt_utils import RTStructBuilder

try:
    from totalsegmentator.map_to_binary import class_map as TS_CLASS_MAP
except Exception:
    TS_CLASS_MAP = {}


try:
    import radai_archive as _arq
    _TMP_LOCAL = _arq.pasta_temporaria_local()
except Exception:
    _TMP_LOCAL = tempfile.gettempdir()

from radai_falhas import (FalhaDaTask, SerieNaoContornavel,
                          RecursoPrevisto, classificar_falha,
                          assinatura_da_falha, primeira_excecao,
                          ultima_excecao)


def _memoria_agora():
    try:
        import radai_cleaner
        m = radai_cleaner.memoria_da_estacao() or {}
        if not m.get("total_mb"):
            return None
        return (m["total_mb"], m.get("livre_mb") or 0, m.get("pct") or 0)
    except Exception:
        return None

TS_MAP = {
    "abdominal_cavity": {"trunk_cavities": ["abdominal_cavity"]},
    "adrenal_gland_left": {"total": ["adrenal_gland_left"], "total_mr": ["adrenal_gland_left"]},
    "adrenal_gland_right": {"total": ["adrenal_gland_right"], "total_mr": ["adrenal_gland_right"]},
    "atrial_appendage_left": {"total": ["atrial_appendage_left"]},
    "auditory_canal_left": {"head_glands_cavities": ["auditory_canal_left"]},
    "auditory_canal_right": {"head_glands_cavities": ["auditory_canal_right"]},
    "brain": {"total": ["brain"], "total_mr": ["brain"]},
    "brain_brainstem": {"brain_structures": ["brainstem"]},
    "brain_cerebellum": {"brain_structures": ["cerebellum"]},
    "common_carotid_artery_left": {"total": ["common_carotid_artery_left"]},
    "common_carotid_artery_right": {"total": ["common_carotid_artery_right"]},
    "caudate_nucleus": {"brain_structures": ["caudate_nucleus"]},
    "central_sulcus": {"brain_structures": ["central_sulcus"]},
    "colon": {"total": ["colon"], "total_mr": ["colon"]},
    "costal_cartilages": {"total": ["costal_cartilages"]},
    "duodenum": {"total": ["duodenum"], "total_mr": ["duodenum"]},
    "esophagus": {"total": ["esophagus"], "total_mr": ["esophagus"]},
    "eye_left": {"head_glands_cavities": ["eye_left"]},
    "eye_lens_left": {"head_glands_cavities": ["eye_lens_left"]},
    "eye_lens_right": {"head_glands_cavities": ["eye_lens_right"]},
    "eye_right": {"head_glands_cavities": ["eye_right"]},
    "femur_left": {"total": ["femur_left"], "total_mr": ["femur_left"]},
    "femur_right": {"total": ["femur_right"], "total_mr": ["femur_right"]},
    "frontal_lobe": {"brain_structures": ["frontal_lobe"]},
    "gallbladder": {"total": ["gallbladder"], "total_mr": ["gallbladder"]},
    "gluteus_maximus_left": {"total": ["gluteus_maximus_left"], "total_mr": ["gluteus_maximus_left"]},
    "gluteus_maximus_right": {"total": ["gluteus_maximus_right"], "total_mr": ["gluteus_maximus_right"]},
    "gluteus_medius_left": {"total": ["gluteus_medius_left"], "total_mr": ["gluteus_medius_left"]},
    "gluteus_medius_right": {"total": ["gluteus_medius_right"], "total_mr": ["gluteus_medius_right"]},
    "gluteus_minimus_left": {"total": ["gluteus_minimus_left"], "total_mr": ["gluteus_minimus_left"]},
    "gluteus_minimus_right": {"total": ["gluteus_minimus_right"], "total_mr": ["gluteus_minimus_right"]},
    "aorta": {"total": ["aorta"], "total_mr": ["aorta"]},
    "inferior_vena_cava": {"total": ["inferior_vena_cava"], "total_mr": ["inferior_vena_cava"]},
    "superior_vena_cava": {"total": ["superior_vena_cava"]},
    "portal_vein_and_splenic_vein": {"total": ["portal_vein_and_splenic_vein"], "total_mr": ["portal_vein_and_splenic_vein"]},
    "pulmonary_vein": {"total": ["pulmonary_vein"]},
    "brachiocephalic_trunk": {"total": ["brachiocephalic_trunk"]},
    "subclavian_artery_right": {"total": ["subclavian_artery_right"]},
    "subclavian_artery_left": {"total": ["subclavian_artery_left"]},
    "brachiocephalic_vein_left": {"total": ["brachiocephalic_vein_left"]},
    "brachiocephalic_vein_right": {"total": ["brachiocephalic_vein_right"]},
    "hard_palate": {"head_glands_cavities": ["hard_palate"]},
    "heart": {"total": ["heart"], "total_mr": ["heart"]},
    "hip_left": {"total": ["hip_left"], "total_mr": ["hip_left"]},
    "hip_right": {"total": ["hip_right"], "total_mr": ["hip_right"]},
    "hypopharynx": {"head_glands_cavities": ["hypopharynx"]},
    "iliac_artery_left": {"total": ["iliac_artery_left"], "total_mr": ["iliac_artery_left"]},
    "iliac_artery_right": {"total": ["iliac_artery_right"], "total_mr": ["iliac_artery_right"]},
    "iliac_vena_left": {"total": ["iliac_vena_left"], "total_mr": ["iliac_vena_left"]},
    "iliac_vena_right": {"total": ["iliac_vena_right"], "total_mr": ["iliac_vena_right"]},
    "iliopsoas_left": {"total": ["iliopsoas_left"], "total_mr": ["iliopsoas_left"]},
    "iliopsoas_right": {"total": ["iliopsoas_right"], "total_mr": ["iliopsoas_right"]},
    "insular_cortex": {"brain_structures": ["insular_cortex"]},
    "internal_capsule": {"brain_structures": ["internal_capsule"]},
    "kidney_cyst_left": {"total": ["kidney_cyst_left"]},
    "kidney_cyst_right": {"total": ["kidney_cyst_right"]},
    "kidney_left": {"total": ["kidney_left"], "total_mr": ["kidney_left"]},
    "kidney_right": {"total": ["kidney_right"], "total_mr": ["kidney_right"]},
    "lentiform_nucleus": {"brain_structures": ["lentiform_nucleus"]},
    "liver": {"total": ["liver"], "total_mr": ["liver"]},
    "lung_left": {"total_mr": ["lung_left"]},
    "lung_right": {"total_mr": ["lung_right"]},
    "lung_lower_lobe_left": {"total": ["lung_lower_lobe_left"]},
    "lung_lower_lobe_right": {"total": ["lung_lower_lobe_right"]},
    "lung_middle_lobe_right": {"total": ["lung_middle_lobe_right"]},
    "lung_upper_lobe_left": {"total": ["lung_upper_lobe_left"]},
    "lung_upper_lobe_right": {"total": ["lung_upper_lobe_right"]},
    "mediastinum": {"trunk_cavities": ["mediastinum"]},
    "nasal_cavity_left": {"head_glands_cavities": ["nasal_cavity_left"]},
    "nasal_cavity_right": {"head_glands_cavities": ["nasal_cavity_right"]},
    "nasopharynx": {"head_glands_cavities": ["nasopharynx"]},
    "occipital_lobe": {"brain_structures": ["occipital_lobe"]},
    "optic_nerve_left": {"head_glands_cavities": ["optic_nerve_left"]},
    "optic_nerve_right": {"head_glands_cavities": ["optic_nerve_right"]},
    "oropharynx": {"head_glands_cavities": ["oropharynx"]},
    "pancreas": {"total": ["pancreas"], "total_mr": ["pancreas"]},
    "parietal_lobe": {"brain_structures": ["parietal_lobe"]},
    "parotid_gland_left": {"head_glands_cavities": ["parotid_gland_left"]},
    "parotid_gland_right": {"head_glands_cavities": ["parotid_gland_right"]},
    "pericardium": {"trunk_cavities": ["pericardium"]},
    "pleural_effusion": {"pleural_pericard_effusion": ["pleural_effusion"]},
    "pericardial_effusion": {
        "pleural_pericard_effusion": ["pericardial_effusion"]},
    "pharyngeal_constrictor_inferior": {"headneck_muscles": ["inferior_pharyngeal_constrictor"]},
    "pharyngeal_constrictor_middle": {"headneck_muscles": ["middle_pharyngeal_constrictor"]},
    "pharyngeal_constrictor_superior": {"headneck_muscles": ["superior_pharyngeal_constrictor"]},
    "prostate": {"total": ["prostate"], "total_mr": ["prostate"]},
    "rib_left_1": {"total": ["rib_left_1"]},
    "rib_left_2": {"total": ["rib_left_2"]},
    "rib_left_3": {"total": ["rib_left_3"]},
    "rib_left_4": {"total": ["rib_left_4"]},
    "rib_left_5": {"total": ["rib_left_5"]},
    "rib_left_6": {"total": ["rib_left_6"]},
    "rib_left_7": {"total": ["rib_left_7"]},
    "rib_left_8": {"total": ["rib_left_8"]},
    "rib_left_9": {"total": ["rib_left_9"]},
    "rib_left_10": {"total": ["rib_left_10"]},
    "rib_left_11": {"total": ["rib_left_11"]},
    "rib_left_12": {"total": ["rib_left_12"]},
    "rib_right_1": {"total": ["rib_right_1"]},
    "rib_right_2": {"total": ["rib_right_2"]},
    "rib_right_3": {"total": ["rib_right_3"]},
    "rib_right_4": {"total": ["rib_right_4"]},
    "rib_right_5": {"total": ["rib_right_5"]},
    "rib_right_6": {"total": ["rib_right_6"]},
    "rib_right_7": {"total": ["rib_right_7"]},
    "rib_right_8": {"total": ["rib_right_8"]},
    "rib_right_9": {"total": ["rib_right_9"]},
    "rib_right_10": {"total": ["rib_right_10"]},
    "rib_right_11": {"total": ["rib_right_11"]},
    "rib_right_12": {"total": ["rib_right_12"]},
    "sacrum": {"total": ["sacrum"], "total_mr": ["sacrum"]},
    "septum_pellucidum": {"brain_structures": ["septum_pellucidum"]},
    "skull": {"total": ["skull"]},

    "mandible": {"craniofacial_structures": ["mandible"]},
    "teeth_upper": {"craniofacial_structures": ["teeth_upper"]},
    "teeth_lower": {"craniofacial_structures": ["teeth_lower"]},
    "sinus_maxillary": {"craniofacial_structures": ["sinus_maxillary"]},
    "sinus_frontal": {"craniofacial_structures": ["sinus_frontal"]},
    "eyeball_left": {"oculomotor_muscles": ["eyeball_left"]},
    "eyeball_right": {"oculomotor_muscles": ["eyeball_right"]},
    "levator_palpebrae_left": {"oculomotor_muscles": ["levator_palpebrae_superioris_left"]},
    "levator_palpebrae_right": {"oculomotor_muscles": ["levator_palpebrae_superioris_right"]},
    "rectus_lateral_left": {"oculomotor_muscles": ["lateral_rectus_muscle_left"]},
    "rectus_lateral_right": {"oculomotor_muscles": ["lateral_rectus_muscle_right"]},
    "rectus_medial_left": {"oculomotor_muscles": ["medial_rectus_muscle_left"]},
    "rectus_medial_right": {"oculomotor_muscles": ["medial_rectus_muscle_right"]},
    "rectus_superior_left": {"oculomotor_muscles": ["superior_rectus_muscle_left"]},
    "rectus_superior_right": {"oculomotor_muscles": ["superior_rectus_muscle_right"]},
    "rectus_inferior_left": {"oculomotor_muscles": ["inferior_rectus_muscle_left"]},
    "rectus_inferior_right": {"oculomotor_muscles": ["inferior_rectus_muscle_right"]},
    "oblique_superior_left": {"oculomotor_muscles": ["superior_oblique_muscle_left"]},
    "oblique_superior_right": {"oculomotor_muscles": ["superior_oblique_muscle_right"]},
    "oblique_inferior_left": {"oculomotor_muscles": ["inferior_oblique_muscle_left"]},
    "oblique_inferior_right": {"oculomotor_muscles": ["inferior_oblique_muscle_right"]},
    "small_intestine": {"total": ["small_bowel"], "total_mr": ["small_bowel"]},
    "soft_palate": {"head_glands_cavities": ["soft_palate"]},
    "spinal_cord": {"total": ["spinal_cord"], "total_mr": ["spinal_cord"]},
    "spleen": {"total": ["spleen"], "total_mr": ["spleen"]},
    "sternum": {"total": ["sternum"]},
    "stomach": {"total": ["stomach"], "total_mr": ["stomach"]},
    "subarachnoid_space": {"brain_structures": ["subarachnoid_space"]},
    "submandibular_gland_left": {"head_glands_cavities": ["submandibular_gland_left"]},
    "submandibular_gland_right": {"head_glands_cavities": ["submandibular_gland_right"]},
    "temporal_lobe": {"brain_structures": ["temporal_lobe"]},
    "thalamus": {"brain_structures": ["thalamus"]},
    "thoracic_cavity": {"trunk_cavities": ["thoracic_cavity"]},
    "thyroid_gland": {"total": ["thyroid_gland"]},
    "trachea": {"total": ["trachea"]},
    "urinary_bladder": {"total": ["urinary_bladder"], "total_mr": ["urinary_bladder"]},
    "venous_sinuses": {"brain_structures": ["venous_sinuses"]},
    "ventricle": {"brain_structures": ["ventricle"]},
    "vertebrae_S1": {"total": ["vertebrae_S1"]},
    "vertebrae_L6": {"total": ["vertebrae_L6"]},
    "vertebrae_C1": {"total": ["vertebrae_C1"]},
    "vertebrae_C2": {"total": ["vertebrae_C2"]},
    "vertebrae_C3": {"total": ["vertebrae_C3"]},
    "vertebrae_C4": {"total": ["vertebrae_C4"]},
    "vertebrae_C5": {"total": ["vertebrae_C5"]},
    "vertebrae_C6": {"total": ["vertebrae_C6"]},
    "vertebrae_C7": {"total": ["vertebrae_C7"]},
    "vertebrae_L1": {"total": ["vertebrae_L1"]},
    "vertebrae_L2": {"total": ["vertebrae_L2"]},
    "vertebrae_L3": {"total": ["vertebrae_L3"]},
    "vertebrae_L4": {"total": ["vertebrae_L4"]},
    "vertebrae_L5": {"total": ["vertebrae_L5"]},
    "vertebrae_T1": {"total": ["vertebrae_T1"]},
    "vertebrae_T2": {"total": ["vertebrae_T2"]},
    "vertebrae_T3": {"total": ["vertebrae_T3"]},
    "vertebrae_T4": {"total": ["vertebrae_T4"]},
    "vertebrae_T5": {"total": ["vertebrae_T5"]},
    "vertebrae_T6": {"total": ["vertebrae_T6"]},
    "vertebrae_T7": {"total": ["vertebrae_T7"]},
    "vertebrae_T8": {"total": ["vertebrae_T8"]},
    "vertebrae_T9": {"total": ["vertebrae_T9"]},
    "vertebrae_T10": {"total": ["vertebrae_T10"]},
    "vertebrae_T11": {"total": ["vertebrae_T11"]},
    "vertebrae_T12": {"total": ["vertebrae_T12"]},
    "larynx_air": {"headneck_bones_vessels": ["larynx_air"]},
    "thyroid_cartilage": {"headneck_bones_vessels": ["thyroid_cartilage"]},
    "hyoid": {"headneck_bones_vessels": ["hyoid"]},
    "cricoid_cartilage": {"headneck_bones_vessels": ["cricoid_cartilage"]},
    "zygomatic_arch_left": {"headneck_bones_vessels": ["zygomatic_arch_left"]},
    "zygomatic_arch_right": {"headneck_bones_vessels": ["zygomatic_arch_right"]},
    "styloid_process_left": {"headneck_bones_vessels": ["styloid_process_left"]},
    "styloid_process_right": {"headneck_bones_vessels": ["styloid_process_right"]},
    "internal_carotid_artery_left": {
        "headneck_bones_vessels": ["internal_carotid_artery_left"]},
    "internal_carotid_artery_right": {
        "headneck_bones_vessels": ["internal_carotid_artery_right"]},
    "internal_jugular_vein_left": {
        "headneck_bones_vessels": ["internal_jugular_vein_left"]},
    "internal_jugular_vein_right": {
        "headneck_bones_vessels": ["internal_jugular_vein_right"]},
    "masseter_left": {"head_muscles": ["masseter_left"]},
    "masseter_right": {"head_muscles": ["masseter_right"]},
    "temporalis_left": {"head_muscles": ["temporalis_left"]},
    "temporalis_right": {"head_muscles": ["temporalis_right"]},
    "lateral_pterygoid_left": {"head_muscles": ["lateral_pterygoid_left"]},
    "lateral_pterygoid_right": {"head_muscles": ["lateral_pterygoid_right"]},
    "medial_pterygoid_left": {"head_muscles": ["medial_pterygoid_left"]},
    "medial_pterygoid_right": {"head_muscles": ["medial_pterygoid_right"]},
    "tongue": {"head_muscles": ["tongue"]},
    "digastric_left": {"head_muscles": ["digastric_left"]},
    "digastric_right": {"head_muscles": ["digastric_right"]},
}

import radai_names as _nomes
_nomes.registrar(TS_MAP)


def resolve_friendly(raw, run_tasks):
    out = {}
    rt = set(_familia(t) for t in run_tasks)
    for fn, taskmap in TS_MAP.items():
        for task, labels in taskmap.items():
            if task not in rt:
                continue
            parts = [raw[l] for l in labels if l in raw]
            if not parts:
                continue
            m = parts[0] if len(parts) == 1 else np.logical_or.reduce(parts)
            if np.any(m):
                out[fn] = m
    return aplicar_compostos(out)


COMPOSTOS = {
    'lung_right': ['lung_upper_lobe_right', 'lung_middle_lobe_right', 'lung_lower_lobe_right'],
    'lung_left':  ['lung_upper_lobe_left', 'lung_lower_lobe_left'],

    'carotids': ['common_carotid_artery_left', 'common_carotid_artery_right'],
    # GUARDA: carotida nenhuma (comum ou interna) entra no composto dos grandes
    # vasos, que vai ao OAR; elas ficam no FULL, cada uma com o seu nome.
    'great_arteries': ['aorta', 'brachiocephalic_trunk',
                       'iliac_artery_left', 'iliac_artery_right',
                       'subclavian_artery_left', 'subclavian_artery_right'],
    'great_veins': ['brachiocephalic_vein_left', 'brachiocephalic_vein_right',
                    'iliac_vena_left', 'iliac_vena_right',
                    'inferior_vena_cava', 'internal_jugular_vein_left',
                    'internal_jugular_vein_right',
                    'portal_vein_and_splenic_vein', 'pulmonary_vein',
                    'superior_vena_cava'],
    'gluteus_muscles': ['gluteus_maximus_left', 'gluteus_maximus_right',
                        'gluteus_medius_left', 'gluteus_medius_right',
                        'gluteus_minimus_left', 'gluteus_minimus_right'],
    'pelvic_muscles': ['gluteus_maximus_left', 'gluteus_maximus_right',
                       'gluteus_medius_left', 'gluteus_medius_right',
                       'gluteus_minimus_left', 'gluteus_minimus_right',
                       'iliopsoas_left', 'iliopsoas_right'],
    'bone_pelvic': ['hip_left', 'hip_right', 'sacrum'],
    'nasal_cavity': ['nasal_cavity_left', 'nasal_cavity_right'],
    'ribs_left': ['rib_left_1', 'rib_left_2', 'rib_left_3', 'rib_left_4', 'rib_left_5', 'rib_left_6', 'rib_left_7', 'rib_left_8', 'rib_left_9', 'rib_left_10', 'rib_left_11', 'rib_left_12'],
    'ribs_right': ['rib_right_1', 'rib_right_2', 'rib_right_3', 'rib_right_4', 'rib_right_5', 'rib_right_6', 'rib_right_7', 'rib_right_8', 'rib_right_9', 'rib_right_10', 'rib_right_11', 'rib_right_12'],
    'vertebrae_cervical': ['vertebrae_C1', 'vertebrae_C2', 'vertebrae_C3', 'vertebrae_C4', 'vertebrae_C5', 'vertebrae_C6', 'vertebrae_C7'],
    'vertebrae_lumbar': ['vertebrae_L1', 'vertebrae_L2', 'vertebrae_L3', 'vertebrae_L4', 'vertebrae_L5'],
    'vertebrae_thoracic': ['vertebrae_T1', 'vertebrae_T2', 'vertebrae_T3', 'vertebrae_T4', 'vertebrae_T5', 'vertebrae_T6', 'vertebrae_T7', 'vertebrae_T8', 'vertebrae_T9', 'vertebrae_T10', 'vertebrae_T11', 'vertebrae_T12'],
}


def _nome_biblioteca(task):
    try:
        import radai_tasks
        return radai_tasks.nome_na_biblioteca(task)
    except Exception:
        return task


def _familia(task):
    try:
        import radai_tasks
        return radai_tasks.familia_da_task(task)
    except Exception:
        return task


def _bases_preferidas():
    try:
        import radai_tasks
        pref = []
        for ordem in (radai_tasks.BASES_CT, radai_tasks.BASES_MR):
            if ordem:
                pref.append(ordem[0])
        return tuple(pref) + tuple(radai_tasks.APELIDOS)
    except Exception:
        return ("total_v3", "total_mr", "total")


def base_eleita(modalidade="CT", pasta_pesos=None, log=None):
    try:
        import radai_tasks
    except Exception:
        return "total_v3" if str(modalidade).upper() != "MR" else "total_mr"
    ordem = (radai_tasks.BASES_MR if str(modalidade).upper() == "MR"
             else radai_tasks.BASES_CT)
    eleita = radai_tasks.base_no_disco(modalidade, pasta_pesos)
    if eleita and ordem and eleita != ordem[0] and callable(log):
        log("base anatomica: %s (a %s nao esta instalada nesta "
            "estacao)" % (eleita, ordem[0]))
    return eleita or (ordem[0] if ordem else None)


def alimenta_o_entregue(task):
    _fam = _familia(task)
    for taskmap in TS_MAP.values():
        if _fam in taskmap:
            return True
    return False


def estruturas_da_task(task):
    fam = _familia(task)
    nomes = sorted(n for n, tm in TS_MAP.items() if fam in tm)
    if nomes:
        return nomes
    try:
        import radai_sets as _rs
        if _rs.task_do_full(task):
            return [u"rotulos de %s (FULL)" % task]
    except Exception:
        pass
    return []


def saidas_da_construcao(cod):
    for c in CONSTRUCOES:
        if c.get("cod") == cod:
            return sorted(c.get("saidas") or {})
    return []


def destino_dos_rotulos_fora_do_mapa(task):
    try:
        import radai_sets as _rs
        if _rs.task_do_full(task):
            return (u"eles alimentam o FULL pelo pos-processamento "
                    u"(radai_sets.TASKS_DO_FULL) e, por ele, o entregue "
                    u"(OAR ou OAR_Fast)")
        if task in getattr(_rs, "PLUGIN_DA_TASK", {}):
            return (u"eles vao ao arquivo proprio da task (plugin) e ao "
                    u"conjunto cru, quando pedido; esta task nao alimenta o "
                    u"FULL nem o entregue")
    except Exception:
        pass
    return (u"eles vao so ao conjunto cru, quando pedido; esta task nao "
            u"alimenta o FULL nem o entregue")


ROTULOS_TORAX = (
    "lung_upper_lobe_right", "lung_middle_lobe_right", "lung_lower_lobe_right",
    "lung_upper_lobe_left", "lung_lower_lobe_left",
    "lung_vessels", "lung_trachea_bronchia",
    "lung_arteries", "lung_veins", "lung_airways", "lung_airways_wall",
)


MINIMO_LOBOS_TX = 2


PROXIMIDADE_SI_MM = 6.0

NOME_JUNCAO_SI = "_juncao_sacroiliaca"

DERIVADAS = {
    "colon": {
        "planos": [
            ((NOME_JUNCAO_SI,), "inf", 0.0, "rectum"),
        ],
        "exige": ("hip_left|hip_right", "sacrum"),
        # GUARDA: o reto e o colon abaixo do plano axial E abaixo/atras do
        # plano do plato do sacro (face superior de S1), num volume so; o que
        # o plano obliquo tira volta ao colon.
        "plano_do_sacro": "rectum",
    },
}

PLATO_DO_SACRO = ("vertebrae_S1", "sacrum")
FAIXA_DO_PLATO_MM = 25.0
PROFUNDIDADE_DO_CORPO_S1_MM = 40.0
MEIA_LARGURA_SAGITAL_MM = 15.0
INCLINACAO_DO_PLATO_GRAUS = (5.0, 75.0)


def plano_do_plato_do_sacro(masks, grade):
    import radai_skin
    partes = [masks[k] for k in PLATO_DO_SACRO if k in masks]
    partes = [_bool_seguro(p) for p in partes if _bool_seguro(p).any()]
    if not partes:
        return None, u"sem sacro"
    s_ = partes[0].copy()
    for p in partes[1:]:
        s_ |= p
    c = np.asarray(radai_skin._para_canonico(s_, grade), dtype=bool)
    sz, sy, sx = radai_skin._espacamento_canonico(grade)
    zs = np.flatnonzero(c.any(axis=(1, 2)))
    if not zs.size:
        return None, u"sem sacro"
    z_top = int(zs.max())
    z_bai = max(0, z_top - int(round(FAIXA_DO_PLATO_MM / sz)))
    faixa = c[z_bai:z_top + 1]
    xs = np.flatnonzero(faixa.any(axis=(0, 1)))
    xm = float(np.median(np.nonzero(faixa)[2]))
    meia = int(round(MEIA_LARGURA_SAGITAL_MM / sx))
    x0, x1 = max(0, int(xm) - meia), int(xm) + meia + 1
    sag = faixa[:, :, x0:x1].any(axis=2)
    ys = np.flatnonzero(sag.any(axis=0))
    if not ys.size or not xs.size:
        return None, u"sem perfil sagital do sacro"
    y_ant = int(ys.min())
    y_fim = y_ant + int(round(PROFUNDIDADE_DO_CORPO_S1_MM / sy))
    pts_y, pts_z = [], []
    for y in range(y_ant, min(y_fim + 1, sag.shape[1])):
        col = np.flatnonzero(sag[:, y])
        if col.size:
            pts_y.append(y * sy)
            pts_z.append((z_bai + int(col.max())) * sz)
    if len(pts_y) < 3:
        return None, u"perfil do plato curto demais"
    yy = np.asarray(pts_y)
    zz = np.asarray(pts_z)
    b, a = np.polyfit(yy, zz, 1)
    alfa = float(np.degrees(np.arctan(b)))
    lo, hi = INCLINACAO_DO_PLATO_GRAUS
    if not (lo <= alfa <= hi):
        return None, (u"inclinacao do plato de %.0f graus, fora de %.0f a "
                      u"%.0f" % (alfa, lo, hi))
    return {"z0_mm": float(a), "y0_mm": 0.0, "inclinacao": float(b),
            "alfa_graus": alfa}, u""


def abaixo_do_plato(forma_ou_mascara, plano, grade):
    import radai_skin
    ref = np.asarray(forma_ou_mascara)
    c = radai_skin._para_canonico(ref, grade)
    sz, sy, _sx = radai_skin._espacamento_canonico(grade)
    nz, ny, nx = c.shape
    zmm = (np.arange(nz) * sz)[:, None, None]
    ymm = (np.arange(ny) * sy)[None, :, None]
    lim = plano["z0_mm"] + plano["inclinacao"] * ymm
    reg = np.broadcast_to(zmm < lim, (nz, ny, nx))
    return radai_skin._de_canonico(np.array(reg, dtype=bool), grade)


def limitar_reto_pelo_plato(reto, masks, grade, log=None):
    from scipy import ndimage
    import radai_skin
    reto = _bool_seguro(reto)
    info = {"plano": False}
    try:
        plano, motivo = plano_do_plato_do_sacro(masks, grade)
    except Exception as e:
        plano, motivo = None, u"%s: %s" % (type(e).__name__, str(e)[:80])
    if plano is None:
        info["motivo"] = motivo
        if log:
            log(u"reto: plano do plato do sacro nao usado (%s) — fica o corte "
                u"axial da juncao sacroiliaca" % motivo)
        return reto, np.zeros_like(reto), info
    abaixo = reto & abaixo_do_plato(reto, plano, grade)
    if not abaixo.any():
        info["motivo"] = u"o plano tiraria o reto inteiro"
        if log:
            log(u"reto: o plano do plato do sacro tiraria o reto inteiro — "
                u"fica o corte axial")
        return reto, np.zeros_like(reto), info
    rot, n = ndimage.label(abaixo)
    if n > 1:
        c = radai_skin._para_canonico(rot, grade)
        zs = np.nonzero(c)[0]
        z_min = int(zs.min())
        cand = [int(v) for v in np.unique(c[z_min]) if v]
        tam = ndimage.sum(np.ones_like(rot), rot, cand)
        fica = cand[int(np.argmax(tam))]
        final = rot == fica
    else:
        final = abaixo
    devolvido = reto & ~final
    vx = float(np.prod(grade.spacing)) / 1000.0
    info.update({"plano": True, "alfa_graus": round(plano["alfa_graus"], 1),
                 "antes_cm3": round(int(reto.sum()) * vx, 2),
                 "depois_cm3": round(int(final.sum()) * vx, 2),
                 "devolvido_cm3": round(int(devolvido.sum()) * vx, 2),
                 "pedacos_abaixo": int(n)})
    if log:
        log(u"reto: plano do plato do sacro (inclinacao %.0f graus) — %.1f -> "
            u"%.1f cm3, %.1f cm3 voltam ao colon, %d pedaco(s) abaixo do plano, "
            u"fica o que desce ate o fim" % (
                plano["alfa_graus"], info["antes_cm3"], info["depois_cm3"],
                info["devolvido_cm3"], n))
    return final, devolvido, info


INDICE_26 = ("vertebrae_L6", "vertebrae_S1")
OBSERVACAO_DO_INDICE_26 = (
    u"Inclui o indice 26 do TotalSegmentator (vertebrae_L6 na v3, "
    u"vertebrae_S1 na v2), %.1f cm3, fundido ao sacro por decisao do servico; "
    u"uma vertebra de transicao lombossacra, se houver, esta dentro desta ROI.")


def _chaves_do_indice_26(masks):
    fora = []
    for n in INDICE_26:
        try:
            k = _nomes.achar(masks, n)
        except Exception:
            k = n if n in masks else None
        if k is not None and k not in fora:
            fora.append(k)
    return fora


def fundir_indice_26_no_sacro(masks, grade=None, log=None):
    from scipy import ndimage
    rel = {"fundidas": [], "cm3": 0.0, "pecas_novas": 0}
    try:
        chaves = _chaves_do_indice_26(masks)
        if not chaves:
            return rel
        idx = None
        for k in chaves:
            b = _bool_seguro(masks[k])
            idx = b.copy() if idx is None else (idx | b)
        sac_k = _nomes.achar(masks, "sacrum") or "sacrum"
        sac = _bool_seguro(masks[sac_k]) if sac_k in masks else None
        if idx is not None and idx.any():
            if sac is None or not sac.any():
                novo, n_antes = idx, 0
                acrescentou = idx
            else:
                novo = sac | idx
                n_antes = int(ndimage.label(sac)[1])
                acrescentou = idx & ~sac
            n_depois = int(ndimage.label(novo)[1])
            rel["pecas_novas"] = max(0, n_depois - n_antes) if n_antes else 0
            vx = (float(np.prod(grade.spacing)) / 1000.0
                  if grade is not None else 0.0)
            rel["cm3"] = round(float(acrescentou.sum()) * vx, 2)
            masks[sac_k] = novo
        for k in chaves:
            try:
                del masks[k]
            except Exception:
                pass
        rel["fundidas"] = list(chaves)
        if log:
            try:
                log(u"indice 26 fundido ao sacro: %s (+%.1f cm3, %d peca(s) "
                    u"nova(s) no sacro)" % (u", ".join(chaves), rel["cm3"],
                                            rel["pecas_novas"]))
            except Exception:
                pass
    except Exception as e:
        if log:
            try:
                log(u"indice 26: a fusao ao sacro falhou (%s: %s)"
                    % (type(e).__name__, str(e)[:100]))
            except Exception:
                pass
    return rel


OBSERVACAO_DO_INDICE_26_NO_CRU = (
    u"Inclui o indice 26 do TotalSegmentator (vertebrae_L6 na v3, "
    u"vertebrae_S1 na v2), fundido ao sacro por decisao do servico: nenhum "
    u"arquivo grava o indice 26 sozinho.")


class _VistaComIndice26Fundido(object):

    def __init__(self, base, chaves):
        self._b = base
        self._fora = set(chaves)
        self._sac = _nomes.achar(base, "sacrum") or "sacrum"
        self._cache = None

    def __iter__(self):
        vistos = False
        for k in self._b:
            if k in self._fora:
                continue
            if k == self._sac:
                vistos = True
            yield k
        if not vistos:
            yield self._sac

    def keys(self):
        return list(self)

    def __len__(self):
        n = 0
        for _ in self:
            n += 1
        return n

    def __contains__(self, k):
        if k in self._fora:
            return False
        return k == self._sac or k in self._b

    def __getitem__(self, k):
        if k in self._fora:
            raise KeyError(k)
        if k != self._sac:
            return self._b[k]
        if self._cache is None:
            m = None
            if self._sac in self._b:
                m = _bool_seguro(self._b[self._sac]).copy()
            for c in sorted(self._fora):
                b = _bool_seguro(self._b[c])
                m = b.copy() if m is None else (m | b)
            self._cache = m
        return self._cache

    def get(self, k, padrao=None):
        try:
            return self[k]
        except KeyError:
            return padrao


def vista_com_indice_26_fundido(masks):
    try:
        chaves = _chaves_do_indice_26(masks)
    except Exception:
        return masks
    if not chaves:
        return masks
    return _VistaComIndice26Fundido(masks, chaves)




def desenhar_juncao_sacroiliaca(masks, grade):
    from scipy import ndimage
    sac = masks.get("sacrum")
    if sac is None:
        return None
    sac = _bool_seguro(sac)
    quadril = None
    for n in ("hip_left", "hip_right"):
        if n in masks:
            b = _bool_seguro(masks[n])
            if b.any():
                quadril = b if quadril is None else (quadril | b)
    if not sac.any() or quadril is None or not quadril.any():
        return None
    esp = tuple(abs(float(v)) for v in grade.spacing)
    d = ndimage.distance_transform_edt(~quadril, sampling=esp)
    juncao = sac & (d <= PROXIMIDADE_SI_MM)
    return juncao if juncao.any() else None


RECORTE_DE_OAR = {
    "femur_left": (("hip_left", "hip_right"), "inf", 0.0),
    "femur_right": (("hip_left", "hip_right"), "inf", 0.0),
}

NOME_DO_RECORTE = {
    "femur_left": "femur_oar_left",
    "femur_right": "femur_oar_right",
}


def aplicar_recorte_de_oar(masks, grade, log=None, manter_orgao=False):
    if grade is None or not RECORTE_DE_OAR:
        return 0
    import radai_geom
    feitas = 0
    for nome, (marcos, extremo, off) in sorted(RECORTE_DE_OAR.items()):
        nome = _nomes.achar(masks, nome) or nome
        if nome not in masks:
            continue
        destino = (NOME_DO_RECORTE.get(_nomes.canonico(nome), nome)
                   if manter_orgao else nome)
        try:
            alvo = _bool_seguro(masks[nome])
            if not alvo.any():
                continue
            if manter_orgao:
                masks[destino] = alvo.copy()
            marco = None
            for m in marcos:
                if m in masks:
                    b = _bool_seguro(masks[m])
                    if b.any():
                        marco = b if marco is None else (marco | b)
            if marco is None:
                if log:
                    log("recorte de OAR em `%s`: sem %s nesta serie — a "
                        "estrutura sai inteira, como o modelo a deu"
                        % (nome, " nem ".join(marcos)))
                continue
            idx = radai_geom.indice_do_extremo(marco, extremo, grade)
            if off:
                idx += grade.mm_para_voxels(float(off), 0)
            abaixo, acima = radai_geom.partir_no_plano(alvo, "inf", idx, grade)
            if not acima.any():
                if log:
                    log("recorte de OAR em `%s`: o plano ficaria acima da "
                        "estrutura inteira — nao cortei" % nome)
                continue
            vx = float(np.prod(grade.spacing)) / 1000.0
            masks[destino] = acima
            feitas += 1
            if log:
                log("recorte de OAR em `%s`%s: parou na tuberosidade isquiatica "
                    "(%.0f -> %.0f cm3, -%.0f%%) — RTOG/Gay 2012. O orgao "
                    "inteiro continua no FULL"
                    % (nome, (" -> `%s`" % destino) if destino != nome else "",
                       alvo.sum() * vx, acima.sum() * vx,
                       100.0 * (1.0 - acima.sum() / float(alvo.sum()))))
        except Exception as e:
            if log:
                log("nao consegui recortar %s (%s) — ela sai como o modelo "
                    "entregou" % (nome, str(e)[:100]))
    return feitas


PISO_DE_PECA_DO_SACRO_CM3 = 1.0


def _marco_confiavel(masks, grade, log=None, tolerancia_de_pecas=0):
    import radai_geom
    from scipy import ndimage

    colon = masks.get("colon")
    sac = masks.get("sacrum")
    if sac is None or not _bool_seguro(sac).any():
        return False, "nao ha sacrum"
    sac = _bool_seguro(sac)

    vol = radai_geom.volume_cm3(sac, grade)
    if vol < 8.0:
        return False, ("sacrum tem so %.1f cm3 — pequeno demais para ser o "
                       "sacro" % vol)
    # GUARDA: o indice 26 fundido pode chegar separado do sacro pelo disco; e
    # a lasca abaixo de `PISO_DE_PECA_DO_SACRO_CM3` nao conta como pedaco.
    _rot_sac, _n_sac = ndimage.label(sac)
    _vx = float(np.prod([float(s) for s in grade.spacing])) / 1000.0
    _tam = np.bincount(_rot_sac.ravel())[1:] * _vx
    _pecas = int(np.count_nonzero(_tam >= PISO_DE_PECA_DO_SACRO_CM3))
    if _pecas > 2 + max(0, int(tolerancia_de_pecas or 0)):
        return False, ("sacrum saiu fragmentado em %d pedacos de %.0f cm3 "
                       "ou mais" % (_pecas, PISO_DE_PECA_DO_SACRO_CM3))

    lombar = masks.get("vertebrae_lumbar")
    if lombar is None:
        _partes = [masks.get(p) for p in COMPOSTOS.get("vertebrae_lumbar", ())]
        _partes = [_bool_seguro(p) for p in _partes if p is not None]
        if _partes:
            lombar = _partes[0].copy()
            for _p in _partes[1:]:
                lombar |= _p
    if lombar is None and log:
        try:
            log(u"derivadas: a conferencia «sacro abaixo da lombar» nao "
                u"rodou — nao ha vertebra lombar nesta serie")
        except Exception:
            pass
    if lombar is not None and _bool_seguro(lombar).any():
        lombar = _bool_seguro(lombar)
        eixo, sinal = grade.eixo_sinal("sup")
        import numpy as _np
        z_sa = _np.where(sac)[eixo]
        z_lo = _np.where(lombar)[eixo]
        topo = int(z_sa.max()) if sinal > 0 else int(z_sa.min())
        base_lo = int(z_lo.min()) if sinal > 0 else int(z_lo.max())
        folga = grade.mm_para_voxels(35.0, eixo)
        if ((topo - base_lo) * sinal) > folga:
            return False, ("o rotulo sacrum saiu ACIMA da coluna lombar — o "
                           "modelo confundiu o nivel vertebral")

    juncao = masks.get(NOME_JUNCAO_SI)
    if juncao is None:
        try:
            juncao = desenhar_juncao_sacroiliaca(masks, grade)
        except Exception:
            juncao = None
    if juncao is None or not _bool_seguro(juncao).any():
        return False, ("nao consegui achar a juncao sacroiliaca (falta sacro "
                       "ou quadril, ou eles nao se encostam nesta serie)")
    juncao = _bool_seguro(juncao)

    eixo, _sinal = grade.eixo_sinal("sup")
    import numpy as _np
    zj = _np.where(juncao)[eixo]
    alt_mm = (int(zj.max()) - int(zj.min()) + 1) * float(grade.spacing[eixo])
    if alt_mm < 25.0:
        return False, ("a juncao sacroiliaca saiu com %.0f mm de altura — "
                       "pouco para uma sacroiliaca, o plano cairia em lugar "
                       "arbitrario" % alt_mm)

    if colon is None or not _bool_seguro(colon).any():
        return False, "nao ha colon"
    colon = _bool_seguro(colon)
    idx = radai_geom.indice_do_extremo(juncao, "inf", grade)
    abaixo, _acima = radai_geom.partir_no_plano(colon, "inf", idx, grade)
    if not abaixo.any():
        return False, "o colon nao desce ate o fim da juncao sacroiliaca"
    n_comp = int(ndimage.label(abaixo)[1])
    if n_comp > 3:
        return False, ("o colon esta partido em %d pedacos abaixo da juncao "
                       "sacroiliaca (falha tipica do modelo)" % n_comp)
    return True, ""


def aplicar_derivadas(masks, grade, log=None, protegidas=None,
                      tolerancia_de_pecas=0):
    import radai_geom
    criadas = []

    def _diz(msg):
        if log:
            try:
                log(msg)
            except Exception:
                pass

    for mae, regra in DERIVADAS.items():
        if mae not in masks or grade is None:
            continue
        planos = regra["planos"]
        if NOME_JUNCAO_SI not in masks:
            try:
                j = desenhar_juncao_sacroiliaca(masks, grade)
                if j is not None:
                    masks[NOME_JUNCAO_SI] = j
            except Exception:
                pass
        refs = []
        faltou = ""
        for marcos, extremo, offset, nome in planos:
            presentes = [masks[k] for k in marcos if k in masks and masks[k].any()]
            if not presentes:
                faltou = " ou ".join(marcos)
                break
            r = presentes[0]
            for outro in presentes[1:]:
                r = r | outro
            refs.append((r, extremo, offset, nome))
        if faltou:
            if faltou == NOME_JUNCAO_SI:
                try:
                    _ok2, _motivo = _marco_confiavel(
                        masks, grade, tolerancia_de_pecas=tolerancia_de_pecas)
                except Exception:
                    _motivo = ""
                faltou = _motivo or "a juncao sacroiliaca"
                _diz("derivadas de %s: NAO DERIVADO — %s. O colon vai "
                     "inteiro." % (mae, faltou))
                continue
            _diz("derivadas de %s: nao ha %s nesta serie -- nada derivado "
                 "(reto sem limite sobe pelo colon transverso)" % (mae, faltou))
            continue
        try:
            ok, motivo = _marco_confiavel(
                masks, grade, log=log,
                tolerancia_de_pecas=tolerancia_de_pecas)
        except Exception as exc:
            ok, motivo = False, "nao consegui conferir os marcos (%s)" % str(exc)[:70]
        if not ok:
            _diz("derivadas de %s: NAO DERIVADO — %s. O colon vai inteiro; "
                 "derivar sobre marco duvidoso poria no plano uma estrutura "
                 "com nome de reto e extensao de outra coisa." % (mae, motivo))
            continue
        try:
            indices = [radai_geom.indice_do_extremo(r, e, grade, o)
                       for (r, e, o, _) in refs]
        except Exception as exc:
            _diz("derivadas de %s: nao consegui achar os planos (%s)"
                 % (mae, str(exc)[:90]))
            continue
        eixo, sinal = grade.eixo_sinal("sup")
        ordenados = indices if sinal > 0 else [-i for i in indices]
        if any(b <= a for a, b in zip(ordenados, ordenados[1:])):
            _diz("derivadas de %s: os planos sairam fora de ordem anatomica "
                 "(%s) -- nada derivado" % (mae, indices))
            continue

        restante = masks[mae]
        saida = {}
        for (r, e, o, nome), idx in zip(refs, indices):
            parte, restante = radai_geom.partir_no_plano(restante, "inf", idx, grade)
            if parte.any():
                saida[nome] = parte
        if not saida:
            _diz("derivadas de %s: os cortes nao deixaram nada" % mae)
            continue
        _obl = regra.get("plano_do_sacro")
        if _obl and _obl in saida:
            try:
                _r, _dev, _inf = limitar_reto_pelo_plato(saida[_obl], masks,
                                                         grade, log=log)
                saida[_obl] = _r
                restante = restante | _dev
            except Exception as _e:
                _diz("reto: o plano do plato do sacro falhou (%s) — fica o "
                     "corte axial" % str(_e)[:90])
        guardadas = set(protegidas or ())
        for nome in sorted(set(saida) & guardadas):
            saida.pop(nome)
            _diz("derivadas de %s: %s ficou com o do modelo — a geometria so "
                 "serviu para tirar a regiao de dentro da mae" % (mae, nome))
        for nome in sorted(guardadas):
            g = masks.get(nome)
            if g is None or not g.any():
                continue
            for outro in list(saida):
                saida[outro] = saida[outro] & ~g
            restante = restante & ~g
        saida = dict((k, v) for k, v in saida.items() if v.any())
        masks.update(saida)
        masks[mae] = restante
        criadas.extend(sorted(saida))
        _diz("derivadas de %s: %s" % (mae, ", ".join(sorted(saida))))
    masks.pop(NOME_JUNCAO_SI, None)
    return criadas



def partes_de_composto():
    fora = set()
    for partes in COMPOSTOS.values():
        fora.update(partes)
    return fora


VASOS_DO_CORACAO = (
    ("superior_vena_cava", True),
    ("pulmonary_vein", True),
    ("inferior_vena_cava", True),
)


FECHAMENTO_PERICARDIO_MM = 12.0

FORA_DO_PERICARDIO = (
    "lung_left", "lung_right", "lung_upper_lobe", "lung_lower_lobe",
    "lung_middle_lobe", "lung_vessels", "lung_trachea_bronchia",
    "vertebrae_", "sternum", "rib_", "scapula", "clavicula",
    "esophagus", "trachea", "liver", "stomach", "spleen",
)


def _aorta_ascendente(aorta, coracao, grade):
    import numpy as np
    from scipy import ndimage as ndi

    post_cresce = grade.sentido[1] == "post"
    asc = np.zeros_like(aorta)
    desc = np.zeros_like(aorta)
    for z in range(aorta.shape[0]):
        fatia = aorta[z]
        if not fatia.any():
            continue
        fc = coracao[z]
        if not fc.any():
            desc[z] = fatia
            continue
        y_cor = float(np.where(fc.any(axis=1))[0].mean())
        rot, n = ndi.label(fatia)
        if n == 0:
            continue
        centros = ndi.center_of_mass(fatia, rot, range(1, n + 1))
        for i in range(n):
            y_m = centros[i][0]
            atras = (y_m > y_cor) if post_cresce else (y_m < y_cor)
            (desc if atras else asc)[z] |= (rot == i + 1)
    return asc, desc


def coracao_de_radioterapia(masks, grade, log=None, chave="heart"):
    import numpy as np
    if grade is None or chave not in masks:
        return None, None
    cor = np.asarray(masks[chave])
    cor = cor if cor.dtype == bool else cor.astype(bool)
    if not cor.any():
        return None, None

    sup = grade.sentido[0] == "sup"
    z = np.where(cor.any(axis=(1, 2)))[0]
    topo = z.max() if sup else z.min()
    abaixo = np.zeros_like(cor)
    if sup:
        abaixo[:topo + 1] = True
    else:
        abaixo[topo:] = True

    janela = np.zeros_like(cor)
    janela[z.min():z.max() + 1] = True

    novo = cor.copy()
    entrou = []
    desc = None

    if "aorta" in masks:
        ao = np.asarray(masks["aorta"])
        ao = (ao if ao.dtype == bool else ao.astype(bool)) & abaixo
        asc, desc = _aorta_ascendente(ao, cor, grade)
        asc = asc & janela
        if asc.any():
            novo |= asc
            entrou.append("aorta ascendente")

    for nome, _ in VASOS_DO_CORACAO:
        if nome not in masks:
            continue
        m = np.asarray(masks[nome])
        m = (m if m.dtype == bool else m.astype(bool)) & janela
        if m.any():
            novo |= m
            entrou.append(nome)

    try:
        import radai_geom as _g
        from scipy import ndimage as _ndi
        antes_saco = int(novo.sum())
        saco = _g.expandir(novo, FECHAMENTO_PERICARDIO_MM, grade)
        saco = _g.contrair(saco, FECHAMENTO_PERICARDIO_MM, grade)
        saco = _g.preencher_buracos(saco, por_fatia=True)
        vizinhos = None
        for nome in FORA_DO_PERICARDIO:
            for k in list(masks):
                alvo = str(k).split(":")[-1]
                if alvo != nome and not alvo.startswith(nome):
                    continue
                b = np.asarray(masks[k])
                b = b if b.dtype == bool else b.astype(bool)
                vizinhos = b.copy() if vizinhos is None else (vizinhos | b)
        if desc is not None and desc.any():
            vizinhos = desc.copy() if vizinhos is None else (vizinhos | desc)
        if vizinhos is not None:
            saco = saco & ~vizinhos
        saco = saco | novo
        _rot, _n = _ndi.label(saco)
        if _n > 1:
            _vivos = set(int(v) for v in np.unique(_rot[novo]) if v)
            saco = np.isin(_rot, list(_vivos)) if _vivos else saco
        if saco.any():
            if log:
                vox = float(np.prod(grade.spacing)) / 1000.0
                log("   pericardio: %.0f -> %.0f cm3 (fechamento de %.0f mm, "
                    "recortado no pulmao e nos vizinhos) — volume unico, e "
                    "nao a uniao das camaras"
                    % (antes_saco * vox, saco.sum() * vox,
                       FECHAMENTO_PERICARDIO_MM))
            novo = saco
    except Exception as _exc:
        if log:
            log("   nao consegui fechar o pericardio (%s) — o coracao sai "
                "como a uniao das partes" % str(_exc)[:110])

    if log and entrou:
        vox = float(np.prod(grade.spacing)) / 1000.0
        log("coracao de radioterapia: %.0f -> %.0f cm3 (entraram: %s)"
            % (cor.sum() * vox, novo.sum() * vox, ", ".join(entrou)))
    return novo, desc


_ARTERIAS_COM_MARGEM = (
    "aorta", "brachiocephalic_trunk",
    "subclavian_artery_left", "subclavian_artery_right",
    "common_carotid_artery_left", "common_carotid_artery_right",
    "internal_carotid_artery_left", "internal_carotid_artery_right",
    "iliac_artery_left", "iliac_artery_right",
)
_VEIAS_COM_MARGEM = (
    "pulmonary_vein", "superior_vena_cava", "inferior_vena_cava",
    "brachiocephalic_vein_left", "brachiocephalic_vein_right",
    "portal_vein_and_splenic_vein",
    "iliac_vena_left", "iliac_vena_right",
    "internal_jugular_vein_left", "internal_jugular_vein_right",
)


MARGEM_OAR_MM = {"trachea": 2.0}
for _n in _ARTERIAS_COM_MARGEM:
    MARGEM_OAR_MM[_n] = 1.0
for _n in _VEIAS_COM_MARGEM:
    MARGEM_OAR_MM[_n] = 1.0
del _n

COMPOSTOS_MENOS = {
    "great_arteries": ("heart",),
    "great_veins": ("heart",),
    "carotids": ("heart",),
}


def texto_da_margem_perdida(mm, real, grade):
    sp = [float(v) for v in grade.spacing]
    entre = (u" Entre cortes (%.2f mm) a margem nao cresce." % sp[0]
             if sp[0] > float(mm) else u"")
    return (u"Margem de convencao: +%.1f mm pedidos, %.2f mm no plano nesta "
            u"grade (pixel de %.2f mm): o contorno fica perto do lumen do "
            u"modelo, e nao da parede.%s" % (float(mm), float(real),
                                             min(sp[1:]), entre))


def aplicar_margens_de_oar(masks, grade, log=None, so=None, ressalvas=None):
    if grade is None or not MARGEM_OAR_MM:
        return 0
    import radai_geom
    feitas = 0
    vasos = []
    for nome, mm in sorted(MARGEM_OAR_MM.items()):
        if so is not None and nome not in so:
            continue
        nome = _nomes.achar(masks, nome) or nome
        if nome not in masks or not float(mm):
            continue
        try:
            antes = _bool_seguro(masks[nome])
            if not antes.any():
                continue
            depois = radai_geom.expandir(antes, float(mm), grade)
            masks[nome] = depois
            feitas += 1
            if ressalvas is not None:
                _px0 = min(float(v) for v in grade.spacing[1:])
                _real0 = int(float(mm) / _px0) * _px0 if _px0 else float(mm)
                # GUARDA: a grade que engole a margem vai na descricao da
                # ROI, e nao so no log.
                if _real0 < 0.5 * float(mm):
                    _t = texto_da_margem_perdida(mm, _real0, grade)
                    _a = ressalvas.get(nome)
                    ressalvas[nome] = (u"%s %s" % (_a, _t)) if _a else _t
            if log:
                vx = float(np.prod(grade.spacing)) / 1000.0
                _px = min(float(v) for v in grade.spacing[1:])
                _real = int(float(mm) / _px) * _px if _px else float(mm)
                if _nomes.canonico(nome) in _ARTERIAS_COM_MARGEM + _VEIAS_COM_MARGEM:
                    vasos.append((nome, mm, _real, antes.sum() * vx,
                                  depois.sum() * vx))
                    continue
                log("margem de OAR em `%s`: +%.1f mm pedidos, %.2f mm nesta "
                    "grade (%.1f -> %.1f cm3) — a saida do modelo e o lumen; "
                    "o orgao de risco e a parede"
                    % (nome, mm, _real, antes.sum() * vx, depois.sum() * vx))
        except Exception as e:
            if log:
                log("nao consegui aplicar a margem de %s (%s) — ela sai como "
                    "o modelo entregou" % (nome, str(e)[:100]))
    if log and vasos:
        log("margem de OAR em %d vaso(s): +%s mm pedidos, %.2f mm nesta grade "
            "(%.1f -> %.1f cm3 somados) — cada vaso com a sua, na tabela "
            "`MARGEM_OAR_MM`; o composto e a soma dos vasos prontos"
            % (len(vasos), "/".join(sorted(set("%.1f" % v[1] for v in vasos))),
               vasos[0][2], sum(v[3] for v in vasos), sum(v[4] for v in vasos)))
    return feitas


RECORTE_DA_AORTA_DEPOIS_DA_MARGEM = (
    "lung_left", "lung_right", "lung_upper_lobe_left", "lung_lower_lobe_left",
    "lung_upper_lobe_right", "lung_middle_lobe_right",
    "lung_lower_lobe_right", "esophagus", "trachea")


def recortar_aorta_dos_vizinhos(masks, grade, log=None):
    if grade is None:
        return 0.0
    chave = _nomes.achar(masks, "aorta")
    if chave is None or chave not in masks:
        return 0.0
    try:
        ao = _bool_seguro(masks[chave])
        if not ao.any():
            return 0.0
        viz = None
        for k in list(masks):
            if k == chave or str(k).startswith("_"):
                continue
            if _nomes.canonico(k) not in RECORTE_DA_AORTA_DEPOIS_DA_MARGEM:
                continue
            b = _bool_seguro(masks[k])
            if b.shape != ao.shape or not b.any():
                continue
            viz = b.copy() if viz is None else (viz | b)
        if viz is None:
            return 0.0
        novo = ao & ~viz
        tirou = int(ao.sum()) - int(novo.sum())
        if not tirou:
            return 0.0
        vx = float(np.prod(grade.spacing)) / 1000.0
        if not novo.any():
            if log:
                log(u"aorta: ficaria VAZIA no recorte pelos pulmoes, esofago e "
                    u"traqueia — nao recortei")
            return 0.0
        masks[chave] = novo
        if log:
            log(u"aorta: depois da margem, recortada dos pulmoes, do esofago e "
                u"da traqueia (-%.2f cm3)" % (tirou * vx))
        return tirou * vx
    except Exception as e:
        if log:
            log(u"nao consegui recortar a aorta dos vizinhos (%s) — ela sai "
                u"com a margem" % str(e)[:100])
        return 0.0


_MODALIDADES_EM_HU = ("CT",)

_PISO_DE_AR_HU = -500.0


def _modalidade_da_serie(pasta):
    try:
        nomes = sorted(os.listdir(str(pasta)))
    except Exception:
        return None
    for n in nomes[:20]:
        c = os.path.join(str(pasta), n)
        if not os.path.isfile(c):
            continue
        try:
            ds = pydicom.dcmread(c, stop_before_pixels=True, force=True,
                                 specific_tags=["Modality"])
            m = str(getattr(ds, "Modality", "") or "").strip().upper()
            if m:
                return m
        except Exception:
            continue
    return None


def _hu_valido(volume_hu, modalidade=None):
    if volume_hu is None:
        return False, u"sem o volume da serie"
    m = str(modalidade or "").strip().upper()
    if m:
        if m in _MODALIDADES_EM_HU:
            return True, u""
        return False, (u"a serie e %s: o valor do pixel nao e HU, e a "
                       u"janela destes passos e em HU" % m)
    try:
        import numpy as np
        minimo = float(np.min(volume_hu))
    except Exception as e:
        return False, u"nao consegui ler a escala do volume (%s)" % (
            type(e).__name__)
    if minimo <= _PISO_DE_AR_HU:
        return True, u""
    return False, (u"o volume nao tem ar na escala HU (minimo %.0f, piso "
                   u"%.0f): nao e TC, e estes passos sao em HU"
                   % (minimo, _PISO_DE_AR_HU))


def acrescentar_pele_e_parede(masks, grade, volume_hu, log=None,
                              modalidade=None):
    novos = []
    if grade is None or volume_hu is None:
        return novos
    _ok, _pq = _hu_valido(volume_hu, modalidade)
    if not _ok:
        if log:
            log(u"pele/parede toracica: nao rodou — %s" % _pq)
        return novos
    try:
        import radai_skin
        externo = radai_skin.contorno_externo(volume_hu, grade, log=log)
        if externo is None:
            return novos
        externo = radai_skin.corpo_da_pele(externo, masks, grade,
                                           volume_hu=volume_hu, log=log)
        casca = radai_skin.pele(externo, grade, log=log)
        if casca is not None and casca.any():
            masks["Skin"] = casca
            novos.append("Skin")
        for nome, m in sorted(radai_skin.parede_toracica(
                masks, externo, grade, log=log).items()):
            masks[nome] = m
            novos.append(nome)
    except Exception as e:
        if log:
            log("pele/parede toracica: %s — o contorno entregue nao foi "
                "afetado" % str(e)[:140])
    return novos



def limpar_fora_do_corpo(masks, volume_hu, grade, log=None, externo=None):
    tirados = []
    if grade is None or volume_hu is None or not masks:
        return tirados
    try:
        import numpy as np
        from scipy import ndimage
        import radai_skin

        if (externo is not None and np.asarray(externo).shape
                != np.asarray(volume_hu).shape):
            externo = None
        if externo is None:
            externo = radai_skin.contorno_externo(volume_hu, grade, log=None,
                                                  com_o_corpo=True)[1]
        if externo is None or not np.asarray(externo).any():
            return tirados
        externo = np.asarray(externo, dtype=bool)
        derivadas_do_externo = ("Skin", "ChestWall_L", "ChestWall_R")
        import radai_geom
        for nome in sorted(masks):
            if nome in derivadas_do_externo:
                continue
            m = np.asarray(masks[nome])
            m = m if m.dtype == bool else m.astype(bool)
            if m.shape != externo.shape or m.ndim != 3:
                if not m.any():
                    continue
                fora = m & ~externo
            else:
                _lim = radai_geom._limites(m)
                if _lim is None:
                    continue
                _cx = tuple(slice(a, b + 1) for a, b in _lim)
                fora = m[_cx] & ~externo[_cx]
            if not fora.any():
                continue
            rot, n = ndimage.label(m)
            if n <= 0:
                continue
            dentro = np.bincount(rot[externo].ravel(), minlength=n + 1)
            soltos = [i for i in range(1, n + 1) if dentro[i] == 0]
            if not soltos:
                continue
            sai = np.isin(rot, soltos)
            novo = m & ~sai
            vox = int(sai.sum())
            if not novo.any():
                if log:
                    log("R3 fora do corpo: `%s` saiu (%.2f cm3) — inteira "
                        "fora do contorno externo"
                        % (nome, vox * float(np.prod(grade.spacing))
                           / 1000.0))
                del masks[nome]
                tirados.append((nome, len(soltos), vox))
                continue
            masks[nome] = novo
            tirados.append((nome, len(soltos), vox))
        parciais = [t for t in tirados if t[0] in masks]
        if log and parciais:
            vox_cm3 = float(np.prod(grade.spacing)) / 1000.0
            for nome, n_p, vox in sorted(parciais, key=lambda t: -t[2])[:6]:
                log("fora do corpo: `%s` perdeu %d pedaco(s), %.2f cm3"
                    % (nome, n_p, vox * vox_cm3))
            if len(parciais) > 6:
                log("fora do corpo: mais %d estrutura(s) limpas"
                    % (len(parciais) - 6))
    except Exception as e:
        if log:
            log("limpeza fora do corpo: %s — o contorno entregue nao foi "
                "afetado" % str(e)[:140])
    return tirados



BANDA_REFINO_MM = 2.5

REFINO_POR_HU = {
    "rib": 300.0,
    "sternum": 300.0,
    "clavicula": 300.0,
    "scapula": 300.0,
    "vertebrae": 300.0,
    "humerus": 300.0,
    "costal_cartilages": None,
}


def _familia_para_refino(nome):
    raiz = _nomes.casa_prefixo(str(nome or "").lower(), tuple(REFINO_POR_HU))
    if raiz is None:
        return None
    return REFINO_POR_HU[raiz]


def refinar_por_hu(mask, volume_hu, grade, limiar_hu, banda_mm=None):
    try:
        import numpy as np
        from scipy import ndimage as ndi
    except Exception:
        return mask
    if volume_hu is None or grade is None or not limiar_hu:
        return mask
    try:
        m = np.asarray(mask, bool)
        hu = np.asarray(volume_hu)
        if m.shape != hu.shape or not m.any():
            return mask
        esp = tuple(abs(float(v)) for v in grade.spacing)
        banda = float(banda_mm or BANDA_REFINO_MM)

        idx = np.nonzero(m)
        fatia = []
        for eixo in range(m.ndim):
            folga = int(np.ceil(banda / max(esp[eixo], 1e-6))) + 1
            ini = max(0, int(idx[eixo].min()) - folga)
            fim = min(m.shape[eixo], int(idx[eixo].max()) + folga + 1)
            fatia.append(slice(ini, fim))
        fatia = tuple(fatia)

        mc = m[fatia]
        huc = hu[fatia]
        dist = ndi.distance_transform_edt(~mc, sampling=esp)
        candidato = mc | ((dist <= banda) & (huc >= float(limiar_hu)))
        rot, _n = ndi.label(candidato)
        vivos = sorted(set(np.unique(rot[mc & (rot > 0)])) - {0})
        if not vivos:
            return mask
        fora = np.zeros_like(m)
        fora[fatia] = np.isin(rot, vivos)
        return np.ascontiguousarray(fora)
    except Exception:
        return mask


def aplicar_refino_por_hu(masks, grade, volume_hu, log=None, modalidade=None):
    if grade is None or volume_hu is None:
        return 0
    _ok, _pq = _hu_valido(volume_hu, modalidade)
    if not _ok:
        if log:
            log(u"refino por densidade: nao rodou — %s" % _pq)
        return 0
    try:
        import numpy as np
    except Exception:
        return 0
    alvos = [n for n in sorted(masks) if _familia_para_refino(n)]
    if log and len(alvos) >= 8:
        log(u"refino por densidade: %d estrutura(s) de osso a conferir — "
            u"leva alguns minutos, e o resultado sai no fim" % len(alvos))
    mudou = 0
    for i, nome in enumerate(alvos, 1):
        limiar = _familia_para_refino(nome)
        antes = masks[nome]
        try:
            n0 = int(np.asarray(antes, bool).sum())
        except Exception:
            continue
        depois = refinar_por_hu(antes, volume_hu, grade, limiar)
        try:
            n1 = int(np.asarray(depois, bool).sum())
        except Exception:
            continue
        if n1 > n0:
            masks[nome] = depois
            mudou += 1
            if log and mudou <= 3:
                log(u"refino por densidade: %s ganhou %.1f%% "
                    u"(a ponta que o corte axial perdia)"
                    % (nome, 100.0 * (n1 - n0) / max(1, n0)))
        if log and len(alvos) >= 8 and i % 15 == 0 and i < len(alvos):
            log(u"refino por densidade: %d de %d conferidas..."
                % (i, len(alvos)))
    if log and mudou:
        log(u"refino por densidade adjacente: %d estrutura(s) de osso" % mudou)
    return mudou


def para_oar(masks, grade=None, log=None, volume_hu=None, modalidade=None):
    fora = dict(masks)

    _hu_ok, _hu_pq = (False, u"")
    if grade is not None and volume_hu is not None:
        _hu_ok, _hu_pq = _hu_valido(volume_hu, modalidade)
        if not _hu_ok and log:
            log(u"pele/parede e refino por densidade: NAO rodaram — %s. O "
                u"recorte pela diretriz (marcos) continua" % _hu_pq)
    _modal_hu = "CT" if _hu_ok else (modalidade or "?")

    if grade is not None and volume_hu is not None and _hu_ok:
        try:
            acrescentar_pele_e_parede(fora, grade, volume_hu, log=log,
                                      modalidade=_modal_hu)
        except Exception as exc:
            if log:
                log("pele/parede: %s" % str(exc)[:120])

    if grade is not None and volume_hu is not None:
        try:
            if _hu_ok:
                aplicar_refino_por_hu(fora, grade, volume_hu, log=log,
                                      modalidade=_modal_hu)
            aplicar_recorte_de_oar(fora, grade, log=log)
        except Exception as exc:
            if log:
                log("refino por densidade: %s" % str(exc)[:120])

    if grade is not None:
        try:
            aplicar_margens_de_oar(fora, grade, log=log)
            recortar_aorta_dos_vizinhos(fora, grade, log=log)
            recompor_compostos(fora)
        except Exception as exc:
            if log:
                log("margens de OAR: %s" % str(exc)[:120])

    if grade is not None:
        try:
            rt, desc = coracao_de_radioterapia(fora, grade, log=log)
            if rt is not None:
                fora["heart"] = rt
                absorvidos = set()
                for nome, _ in VASOS_DO_CORACAO:
                    if nome in fora:
                        absorvidos.add(nome)
                    fora.pop(nome, None)
                if desc is not None and desc.any():
                    if "great_arteries" not in fora:
                        fora["aorta"] = desc
                    else:
                        fora.pop("aorta", None)
                    absorvidos.add("aorta")
                else:
                    if "aorta" in fora:
                        absorvidos.add("aorta")
                    fora.pop("aorta", None)

                try:
                    import numpy as _np
                    for _comp, _partes in COMPOSTOS.items():
                        if _comp not in fora or not (absorvidos & set(_partes)):
                            continue
                        _m = _np.asarray(fora[_comp])
                        _m = _m if _m.dtype == bool else _m.astype(bool)
                        _sobra = _m & ~rt
                        _perdeu = int(_m.sum() - _sobra.sum())
                        if not _perdeu:
                            continue
                        if _sobra.any():
                            fora[_comp] = _sobra
                        else:
                            fora.pop(_comp, None)
                        if log:
                            _vox = float(_np.prod(grade.spacing)) / 1000.0
                            log("`%s` cedeu %.1f cm3 ao coracao de "
                                "radioterapia (os dois entregues fariam o "
                                "DVH contar a mesma dose duas vezes)"
                                % (_comp, _perdeu * _vox))
                except Exception as _exc:
                    if log:
                        log("nao consegui separar o composto do coracao "
                            "(%s) - os dois saem como estao" % str(_exc)[:100])
        except Exception as exc:
            if log:
                try:
                    log("coracao de radioterapia: %s" % str(exc)[:140])
                except Exception:
                    pass

    for composto, partes in COMPOSTOS.items():
        if composto not in fora:
            continue
        for p in partes:
            fora.pop(p, None)
    return fora


class _SaidaComFaltou(dict):

    def __init__(self, *a, **kw):
        dict.__init__(self, *a, **kw)
        self.faltou = []


def _log_que_guarda(log):
    linhas = []

    def _log(m):
        linhas.append(u"%s" % (m,))
        if log:
            try:
                log(m)
            except Exception:
                pass
    return _log, linhas


def _motivo_do_log(linhas, prefixo, padrao):
    p = prefixo.lower()
    for l in reversed(linhas or ()):
        b = l.lower()
        if p in b and u"nao sai" in b:
            for sep in (u" — ", u" -- ", u" - "):
                if sep in l:
                    antes, depois = l.split(sep, 1)
                    if depois.strip().lower().startswith(u"nao sai"):
                        return antes.split(u":", 1)[-1].strip()[:200]
                    return depois.strip()[:200]
            return l.strip()[:200]
    for l in reversed(linhas or ()):
        b = l.lower()
        if p in b and u"nao consegui" in b:
            return l.strip()[:200]
    return padrao


def _construir_pele_e_parede(masks, grade, volume_hu=None, log=None,
                             torax=None, cru=None, externo=None):
    fora = _SaidaComFaltou()
    if grade is None or volume_hu is None:
        fora.faltou.append(u"Skin, ChestWall_L, ChestWall_R: sem a grade ou "
                           u"sem o volume da serie")
        return fora
    try:
        import radai_skin
        prefixos = (tuple(getattr(radai_skin, "BASE_DA_PAREDE", ()))
                    + tuple(getattr(radai_skin, "CROPS_DA_PAREDE", ()))
                    + tuple(getattr(radai_skin, "CAVIDADES_PROIBIDAS", ())))
        vista = {}
        for k in list(masks):
            if str(k).startswith("_"):
                continue
            p = _nomes.casa_prefixo(k, prefixos)
            if p is None:
                continue
            chave = str(k)
            if not (chave == p or chave.startswith(p)):
                chave = next((f for f in _nomes.formas(k)
                              if f == p or f.startswith(p)), chave)
            vista[chave] = masks[k]
        if externo is None:
            externo = radai_skin.contorno_externo(volume_hu, grade, log=log)
        if externo is None:
            fora.faltou.append(u"Skin, ChestWall_L, ChestWall_R: o contorno "
                               u"externo nao saiu nesta serie")
            return fora
        externo = radai_skin.corpo_da_pele(externo, masks, grade,
                                           volume_hu=volume_hu, log=log)
        casca = radai_skin.pele(externo, grade, log=log)
        if casca is not None and casca.any():
            fora["Skin"] = casca
        _log, _linhas = _log_que_guarda(log)
        paredes = radai_skin.parede_toracica(
            vista, externo, grade, log=_log, torax=torax, cru=cru)
        desc = None
        if paredes:
            try:
                _faltaram = list(radai_skin.vizinhos_da_parede(
                    vista, cru=cru)[1])
                _est = radai_skin.uniao_por_nome(vista, ("sternum",),
                                                 cru=cru)
                _sem_est = not (_est is not None
                                and bool(np.asarray(_est).any()))
                _cav = radai_skin.uniao_por_nome(
                    vista, radai_skin.CAVIDADE_TORACICA, cru=cru, exato=True,
                    ambas=True)
                _sem_cav = not (_cav is not None
                                and bool(np.asarray(_cav).any()))
                desc = descricao_da_parede(_faltaram, _sem_est,
                                           sem_cavidade=_sem_cav)
            except Exception:
                desc = None
        for nome, m in sorted(paredes.items()):
            fora[nome] = (m, desc) if desc else m
        if not paredes:
            fora.faltou.append(u"ChestWall_L, ChestWall_R: %s" % _motivo_do_log(
                _linhas, u"parede toracica", u"a parede nao saiu nesta serie"))
    except Exception as e:
        fora.faltou.append(u"Skin, ChestWall_L, ChestWall_R: %s: %s"
                           % (type(e).__name__, str(e)[:100]))
        if log:
            log("pele/parede toracica: %s — as outras estruturas nao foram "
                "afetadas" % str(e)[:140])
    return fora


DESCRICAO_FEMUR_SEM_RECORTE = (
    u"Femur INTEIRO: o recorte RTOG (Gay 2012) na tuberosidade isquiatica NAO "
    u"foi aplicado nesta serie (%s). Confira a extensao antes de usar como "
    u"OAR.")


def _construir_femur_oar(masks, grade, volume_hu=None, log=None):
    fora = {}
    camada = _Sobreposto(masks)
    aplicar_recorte_de_oar(camada, grade, log=log, manter_orgao=True)
    for orgao, destino in sorted(NOME_DO_RECORTE.items()):
        if destino not in camada._novo:
            continue
        recortado = camada._novo[destino]
        chave = _nomes.achar(masks, orgao) or orgao
        try:
            inteiro = int(_bool_seguro(masks[chave]).sum())
            ficou = int(_bool_seguro(recortado).sum())
        except Exception:
            inteiro, ficou = 0, 0
        if inteiro and ficou < inteiro:
            fora[destino] = recortado
            continue
        marcos = (RECORTE_DE_OAR.get(orgao) or ((),))[0]
        tem_marco = False
        for m in marcos:
            k = _nomes.achar(masks, m) or m
            try:
                if k in masks and _bool_seguro(masks[k]).any():
                    tem_marco = True
                    break
            except Exception:
                continue
        motivo = (u"o plano da tuberosidade ficaria acima do femur inteiro"
                  if tem_marco else
                  u"sem %s no campo" % u" nem ".join(marcos or (u"o marco",)))
        fora[destino] = (recortado, DESCRICAO_FEMUR_SEM_RECORTE % motivo)
        if log:
            log(u"`%s` sai IGUAL ao femur inteiro (%s) — e a descricao da ROI "
                u"diz isso, em vez de afirmar o recorte" % (destino, motivo))
    return fora


def _construcao_de_c1(funcao, prefixo_do_log, masks, grade, log, **kw):
    _log, linhas = _log_que_guarda(log)
    c = funcao(masks, grade, log=_log, **kw)
    fora = _SaidaComFaltou()
    if c is None or not bool(c):
        fora.faltou.append(_motivo_do_log(
            linhas, prefixo_do_log, u"a construcao nao devolveu nada nesta "
                                    u"serie"))
        return fora
    fora[c.chave] = (c.mascara, u"%s" % (c.descricao or u""))
    fora.faltou.extend(u"%s: %s" % (c.chave, f) for f in (c.faltou or ()))
    return fora


def _construir_pericardio(masks, grade, volume_hu=None, log=None, cru=None):
    import radai_constructs as _rc
    return _construcao_de_c1(_rc.pericardio_corrigido, u"pericardio corrigido",
                             masks, grade, log, cru=cru)


def _construir_coracao(masks, grade, volume_hu=None, log=None, cru=None,
                       construidas=None):
    import radai_constructs as _rc
    peri = (construidas or {}).get(_rc.CHAVE_PERICARDIO)
    fora = _construcao_de_c1(_rc.coracao_ai, u"Heart_ai", masks, grade, log,
                             cru=cru, pericardio=peri)
    try:
        cava = _rc._exata(masks, CAVA_INFERIOR, cru)
        if cava is not None and _bool_seguro(cava).any():
            fora.cava_inferior = {_rc.CHAVE_CORACAO_AI: _bool_seguro(cava)}
    except Exception:
        pass
    try:
        modelo, _de = _rc._coracao_do_modelo(masks, cru)
        if modelo is not None and _bool_seguro(modelo).any():
            fora.coracao_do_modelo = {
                _rc.CHAVE_CORACAO_AI: _bool_seguro(modelo)}
    except Exception:
        pass
    return fora


def _construir_bag_bowel(masks, grade, volume_hu=None, log=None, cru=None):
    import radai_constructs as _rc
    return _construcao_de_c1(_rc.bag_bowel_declarada, u"Bag_Bowel", masks,
                             grade, log, cru=cru)


def _construir_olhos(masks, grade, volume_hu=None, log=None, cru=None):
    import radai_constructs as _rc
    fora = _SaidaComFaltou()
    for chave, c in sorted((_rc.olhos(masks, grade, log=log, cru=cru)
                            or {}).items()):
        if c is None or not bool(c):
            continue
        fora[chave] = (c.mascara, u"%s" % (c.descricao or u""))
        fora.faltou.extend(u"%s" % f for f in (c.faltou or ()))
    if not fora:
        fora.faltou.append(u"olhos: nenhum globo nesta serie")
    return fora


def _construir_bag_bowel_oar(masks, grade, volume_hu=None, log=None,
                             cru=None, construidas=None):
    import radai_constructs as _rc
    return _construcao_de_c1(_rc.bag_bowel_oar, u"Bag_Bowel_OAR", masks,
                             grade, log, cru=cru, construidas=construidas)


CAVA_INFERIOR = "inferior_vena_cava"


def sem_a_cava_nos_cortes(m, cava, grade):
    from scipy import ndimage
    m = _bool_seguro(m)
    if cava is None:
        return m, 0
    cava = _bool_seguro(cava)
    if cava.shape != m.shape or not (m & cava).any():
        return m, 0
    eixo, _sinal = grade.eixo_sinal("inf")
    novo = m.copy()
    tirados = 0
    vizinhanca = np.ones((3, 3), bool)
    for k in range(m.shape[eixo]):
        fatia = np.take(m, k, axis=eixo)
        cv = np.take(cava, k, axis=eixo)
        if not (fatia & cv).any():
            continue
        rot, n = ndimage.label(fatia, vizinhanca)
        if n < 2:
            continue
        tam = np.bincount(rot.ravel(), minlength=n + 1)
        comum = np.bincount(rot[fatia & cv].ravel(), minlength=n + 1)
        cruzam = dict((j, comum[j] / float(tam[j])) for j in range(1, n + 1)
                      if comum[j])
        if len(cruzam) == n:
            del cruzam[min(cruzam, key=cruzam.get)]
        if not cruzam:
            continue
        sai = np.isin(rot, list(cruzam))
        idx = [slice(None)] * m.ndim
        idx[eixo] = k
        alvo = novo[tuple(idx)]
        alvo[sai] = False
        novo[tuple(idx)] = alvo
        tirados += int(sai.sum())
    return novo, tirados


def sem_a_cava_fundida(m, cava, modelo, grade, margem_mm=None):
    from scipy import ndimage
    m = _bool_seguro(m)
    if cava is None or modelo is None:
        return m, 0, 0
    cava = _bool_seguro(cava)
    modelo = _bool_seguro(modelo)
    if cava.shape != m.shape or modelo.shape != m.shape:
        return m, 0, 0
    mm = (MARGEM_OAR_MM.get(CAVA_INFERIOR, 0.0) if margem_mm is None
          else float(margem_mm))
    if mm > 0 and cava.any():
        import radai_geom
        cava = radai_geom.expandir(
            cava, dict((l, mm) for l in ("ant", "post", "esq", "dir")), grade)
    if not (m & cava).any():
        return m, 0, 0
    eixo, _sinal = grade.eixo_sinal("inf")
    vizinhanca = np.ones((3, 3), bool)
    novo = m.copy()
    tirados = 0
    vazios = 0
    for k in range(m.shape[eixo]):
        fatia = np.take(novo, k, axis=eixo)
        cv = np.take(cava, k, axis=eixo)
        if not (fatia & cv).any():
            continue
        mh = np.take(modelo, k, axis=eixo) & fatia
        # GUARDA: a cava que encosta no coracao do modelo e a juncao com o
        # atrio direito, e fica; so a cava separada dele sai.
        if (ndimage.binary_dilation(cv, vizinhanca)
                & np.take(modelo, k, axis=eixo)).any():
            continue
        rot, _n = ndimage.label(fatia, vizinhanca)
        cruzam = [j for j in np.unique(rot[fatia & cv]) if j]
        regiao = np.isin(rot, cruzam)
        resto = regiao & ~(cv & ~mh)
        rot2, _n2 = ndimage.label(resto, vizinhanca)
        vivos = [j for j in np.unique(rot2[resto & mh]) if j]
        fica = (np.isin(rot2, vivos) if vivos
                else np.zeros_like(resto))
        sai = regiao & ~fica
        if not sai.any():
            continue
        nova = fatia & ~sai
        idx = [slice(None)] * m.ndim
        idx[eixo] = k
        novo[tuple(idx)] = nova
        tirados += int(sai.sum())
        if not nova.any():
            vazios += 1
    return novo, tirados, vazios


def _acabamento_do_coracao(nome, m, masks, grade, log=None, spec=None):
    import radai_geom
    import radai_constructs as _rc
    m = _bool_seguro(m)
    der = _rc._derrame_pericardico(masks)
    if der is not None and m.any():
        m = m | radai_geom.limitar_por_plano(der, "sup", m, grade=grade)
    cheio = radai_geom.preencher_buracos(m, por_fatia=True)
    um = radai_geom.maior_componente(cheio, conectividade=1)
    vx = float(np.prod(grade.spacing)) / 1000.0
    if log and um.any():
        ganho = int((cheio & ~m).sum())
        caiu = int((cheio & ~um).sum())
        if ganho or caiu:
            log(u"   `%s`: buracos de cada corte preenchidos (+%.2f cm3), um "
                u"volume (-%.2f cm3)" % (nome, ganho * vx, caiu * vx))
    if not um.any():
        return m, None, {}
    # GUARDA: no corte com dois contornos, o que cruza a veia cava inferior
    # sai e fica o do apice; a cava nao entra no coracao por baixo.
    cava = masks.get(CAVA_INFERIOR) if hasattr(masks, "get") else None
    if cava is None:
        cava = (spec or {}).get("cava_inferior")
    um, tirados = sem_a_cava_nos_cortes(um, cava, grade)
    info = {}
    if tirados:
        info["cava_inferior_tirada_cm3"] = round(tirados * vx, 2)
        if log:
            log(u"   `%s`: nos cortes com dois contornos, o que cruza a veia "
                u"cava inferior saiu (-%.2f cm3); ficou o do apice"
                % (nome, tirados * vx))
    modelo = (masks.get(_nomes.CHAVE_DO_CORACAO_DO_MODELO)
              if hasattr(masks, "get") else None)
    if modelo is None:
        modelo = (spec or {}).get("coracao_do_modelo")
    um, fundida, vazios = sem_a_cava_fundida(um, cava, modelo, grade)
    if fundida:
        info["cava_fundida_tirada_cm3"] = round(fundida * vx, 2)
        info["cortes_so_de_cava"] = int(vazios)
        if log:
            log(u"   `%s`: nos cortes em que a veia cava inferior nao encosta "
                u"no coracao do modelo, a cava (com a margem de %.1f mm) saiu "
                u"do contorno unico (-%.2f cm3); %d corte(s) so de cava "
                u"ficaram vazios; o apice fica"
                % (nome, MARGEM_OAR_MM.get(CAVA_INFERIOR, 0.0),
                   fundida * vx, vazios))
    return um, None, info


SUAVIZACAO_A_MAIS_DO_CORACAO_MM = 3.0

_CONTEM_DO_CORACAO = ("heart_model", "heart", "aorta", "superior_vena_cava",
                      "inferior_vena_cava", "pulmonary_vein",
                      "atrial_appendage_left", "pericardium",
                      "pericardial_effusion")

_CONTEM_DO_PERICARDIO = ("heart", "atrial_appendage_left", "great_arteries",
                         "great_veins", "aorta", "superior_vena_cava",
                         "inferior_vena_cava", "pulmonary_vein")

_CONTEM_DA_BAG = ("small_intestine", "small_bowel", "colon", "rectum",
                  "stomach", "pancreas", "duodenum")

_RECORTES_DA_PAREDE_DESCRITOS = (
    (None, u"vertebras"),
    (u"esterno", u"esterno (plano na borda lateral dele)"),
    (u"escapula", u"escapula"),
    (u"clavicula", u"clavicula"),
    (u"coracao", u"coracao"),
    (u"pericardio", u"pericardio"),
    (u"mediastino", u"mediastino"),
    (None, u"esofago"),
    (None, u"traqueia"),
    (None, u"tireoide"),
    (None, u"visceras"),
    (None, u"cavidade abdominal"),
)


def _numeros_da_parede():
    try:
        import radai_skin as _sk
        return (u"%g" % float(_sk.MARGEM_PAREDE_MM),
                u"%g" % float(_sk.SUAVIZACAO_PAREDE_MM))
    except Exception:
        return (u"?", u"?")


def descricao_da_parede(faltaram=(), sem_esterno=False, sem_cavidade=False):
    tirar = set(faltaram or ())
    if sem_esterno:
        tirar.add(u"esterno")
    recortes = [t for r, t in _RECORTES_DA_PAREDE_DESCRITOS
                if r is None or r not in tirar]
    lista = (u", ".join(recortes[:-1]) + u" e " + recortes[-1]
             if len(recortes) > 1 else u"".join(recortes))
    margem, suav = _numeros_da_parede()
    if sem_cavidade:
        base = (u"pulmao, costelas e cartilagens costais expandidos %s mm, "
                u"menos os pulmoes" % margem)
    else:
        base = (u"cavidade toracica do lado (pulmao e derrame), costelas e "
                u"metade das cartilagens costais expandidos %s mm, menos a "
                u"cavidade toracica inteira" % margem)
    texto = (u"Parede toracica do lado: %s; recortada por %s; sem recorte "
             u"por vasos; por dentro da pele; ate a ultima costela; "
             u"suavizada %s mm e recortada de novo; um contorno por corte "
             u"(o maior) onde ha pulmao, e abaixo da base do pulmao ate dois "
             u"(os ramos com costela); nenhum corte com costela e pulmao do "
             u"lado fica sem parede: onde a suavizacao a tirou de cima das "
             u"costelas, volta o pedaco sem suavizar. O autoctone nao e "
             u"recortado. "
             % (base, lista, suav))
    notas = []
    if sem_cavidade:
        notas.append(u"sem a cavidade toracica, um derrame pleural nao foi "
                     u"subtraido")
    if sem_esterno:
        notas.append(u"sem esterno, o plano medial nao existe")
    outros = [f for f in (faltaram or ()) if f != u"esterno"]
    if outros:
        notas.append(u"recortes que nao vieram: %s" % u", ".join(outros))
    if notas:
        texto += u"Nesta serie: %s. " % u"; ".join(notas)
    return texto + (u"Sobreposicao com a mama (Breast_L/R) do mesmo lado e "
                    u"esperada (nenhuma desconta a outra): no DVH a regiao "
                    u"comum conta nas duas.")


DESCRICAO_DA_PAREDE = descricao_da_parede()

CONSTRUCOES = [
    {"cod": "femur_oar", "funcao": _construir_femur_oar,
     "momento": "depois_do_refino", "exige_hu": False,
     "exige": ("femur_left|femur_right",),
     "saidas": {
         "femur_oar_left": {
             "suavizar_mm": None, "recortar_por": (), "contem": ("femur_left",),
             "descricao": u"Femur recortado no nivel mais baixo das "
                          u"tuberosidades isquiaticas (RTOG, Gay 2012). O "
                          u"femur inteiro esta no FULL."},
         "femur_oar_right": {
             "suavizar_mm": None, "recortar_por": (),
             "contem": ("femur_right",),
             "descricao": u"Femur recortado no nivel mais baixo das "
                          u"tuberosidades isquiaticas (RTOG, Gay 2012). O "
                          u"femur inteiro esta no FULL."}}},
    {"cod": "pericardio", "funcao": _construir_pericardio,
     "momento": "depois_das_margens", "exige_hu": False,
     "exige": ("pericardium",
               _nomes.CHAVE_DO_CORACAO_DO_MODELO + "|heart"),
     "saidas": {
         "pericardium": {
             "suavizar_mm": None, "recortar_por": FORA_DO_PERICARDIO,
             "contem": _CONTEM_DO_PERICARDIO,
             "reune": (_nomes.CHAVE_DO_CORACAO_DO_MODELO,
                       "atrial_appendage_left"),
             "descricao": u"Pericardio: o da task trunk_cavities unido ao "
                          u"coracao do modelo, menos pulmoes, esofago, vias "
                          u"aereas, aorta descendente e os vizinhos do "
                          u"coracao. O coracao fica dentro do pericardio."}}},
    {"cod": "coracao", "funcao": _construir_coracao,
     "momento": "depois_do_pericardio", "exige_hu": False,
     "exige": (_nomes.CHAVE_DO_CORACAO_DO_MODELO + "|heart",),
     "saidas": {
         "heart": {
             "suavizar_mm": None, "recortar_por": FORA_DO_PERICARDIO,
             "contem": _CONTEM_DO_CORACAO,
             "suavizar_a_mais_mm": SUAVIZACAO_A_MAIS_DO_CORACAO_MM,
             "um_volume_com": ("pericardium",),
             "um_volume": True,
             "acabamento": _acabamento_do_coracao,
             "descricao": u"Coracao de radioterapia: heart do modelo + aorta "
                          u"ascendente e VCS, VCI e veia pulmonar na janela "
                          u"do coracao, fechamento de 12 mm, recortado nos "
                          u"vizinhos. O heart do modelo esta no FULL como "
                          u"Heart_Model."}}},
    {"cod": "bag_bowel", "funcao": _construir_bag_bowel,
     "momento": "no_fim", "exige_hu": False,
     "exige": ("abdominal_cavity",),
     "saidas": {
         "bag_bowel": {
             "suavizar_mm": 0.0,
             "recortar_por": None,
             "contem": _CONTEM_DA_BAG,
             "reune": ("pancreas",),
             "descricao": u"Bag_Bowel: cavidade abdominal da task "
                          u"trunk_cavities menos figado, vesicula, bexiga, "
                          u"baco, vasos, rins, adrenais, esofago, coracao, "
                          u"pericardio e pulmao; o pancreas entra inteiro. "
                          u"Sobrepoe os orgaos abdominais."}}},
    {"cod": "olhos", "funcao": _construir_olhos,
     "momento": "no_fim", "exige_hu": False,
     "exige": ("eye_left|eye_right",),
     "saidas": {
         "eye_left": {"suavizar_mm": 0.0, "recortar_por": (),
                      "contem": ("eye_lens_left",),
                      "reune": ("eye_lens_left",),
                      "descricao": u""},
         "eye_right": {"suavizar_mm": 0.0, "recortar_por": (),
                       "contem": ("eye_lens_right",),
                       "reune": ("eye_lens_right",),
                       "descricao": u""}}},
    {"cod": "pele_e_parede", "funcao": _construir_pele_e_parede,
     "momento": "no_fim", "exige_hu": True, "exige": (),
     "saidas": {
         "Skin": {"suavizar_mm": None, "recortar_por": (),
                  "contem": ("breast_left", "breast_right"),
                  "descricao": u""},
         "ChestWall_L": {"suavizar_mm": None, "recortar_por": None,
                         "um_contorno_por_corte": True,
                         "contem": ("rib_", "ribs_", "costal_cartilages",
                                    "autochthon", "pectoralis",
                                    "latissimus", "serratus", "breast",
                                    "humerus"),
                         "descricao": DESCRICAO_DA_PAREDE},
         "ChestWall_R": {"suavizar_mm": None, "recortar_por": None,
                         "um_contorno_por_corte": True,
                         "contem": ("rib_", "ribs_", "costal_cartilages",
                                    "autochthon", "pectoralis",
                                    "latissimus", "serratus", "breast",
                                    "humerus"),
                         "descricao": DESCRICAO_DA_PAREDE}}},
]


def _recorte_da_bag():
    try:
        import radai_constructs as _rc
        return (tuple(_rc.ORGAOS_FORA_DA_BAG)
                + tuple(_rc.ORGAOS_DO_TORAX_FORA_DA_BAG)
                + tuple(_rc.vasos_do_motor())
                + tuple(_rc.compostos_de_vaso()))
    except Exception:
        return ()


def _recorte_da_parede():
    try:
        import radai_skin as _sk
        return tuple(_sk.RECORTES_DA_SEGUNDA_PASSADA)
    except Exception:
        return ()


for _c in CONSTRUCOES:
    if _c.get("cod") == "bag_bowel":
        _c["saidas"]["bag_bowel"]["recortar_por"] = _recorte_da_bag()
    if _c.get("cod") == "pele_e_parede":
        for _lado in ("ChestWall_L", "ChestWall_R"):
            _c["saidas"][_lado]["recortar_por"] = _recorte_da_parede()
        del _lado
del _c

_CONTEM_DA_BAG_OAR = ("small_intestine", "small_bowel", "colon", "duodenum",
                      "stomach", "pancreas", "bag_bowel", "great_veins",
                      "portal_vein_and_splenic_vein")


def _recorte_da_bag_oar():
    try:
        import radai_constructs as _rc
        return (tuple(_rc.ORGAOS_FORA_DA_BAG)
                + tuple(_rc.ORGAOS_DO_TORAX_FORA_DA_BAG)
                + tuple(_rc.ORGAOS_FORA_DA_BAG_OAR)
                + tuple(_rc.vasos_da_bag_oar())
                + tuple(_rc.MUSCULOS_FORA_DA_BAG_OAR)
                + tuple(_rc.OSSOS_FORA_DA_BAG_OAR)
                + tuple(_rc.CONSTRUCOES_FORA_DA_BAG_OAR))
    except Exception:
        return ()


def _acabamento_da_bag_oar(nome, m, masks, grade, log=None):
    import radai_constructs as _rc
    novo, desc, cob, conf = _rc.acabamento_da_bag_oar(m, masks, grade,
                                                      log=log)
    return novo, desc, {"cobertura": cob, "conflitos": conf}


CONSTRUCOES.append(
    {"cod": "bag_bowel_oar", "funcao": _construir_bag_bowel_oar,
     "momento": "no_fim", "exige_hu": False,
     "exige": ("abdominal_cavity",),
     "saidas": {
         "bag_bowel_oar": {
             "suavizar_mm": 0.0,
             "recortar_por": _recorte_da_bag_oar(),
             "contem": _CONTEM_DA_BAG_OAR,
             "um_volume": True,
             "acabamento": _acabamento_da_bag_oar,
             "descricao": u"Bag_Bowel_OAR: as alcas com margem dos vizinhos "
                          u"e os orgaos ocos inteiros."}}})


def _saida_das_construcoes(cs):
    fora = _SaidaComFaltou()
    for chave, c in sorted((cs or {}).items()):
        if c is None:
            continue
        if bool(c):
            fora[chave] = (c.mascara, u"%s" % (c.descricao or u""))
        fora.faltou.extend(u"%s" % f for f in (c.faltou or ()) if f)
    return fora


def _construir_cristas_iliacas(masks, grade, volume_hu=None, log=None,
                               cru=None):
    import radai_constructs as _rc
    return _saida_das_construcoes(_rc.cristas_iliacas(masks, grade, log=log,
                                                      cru=cru))


def _construir_anus(masks, grade, volume_hu=None, log=None, cru=None,
                    construidas=None):
    import radai_constructs as _rc
    bag = (construidas or {}).get(_rc.CHAVE_BAG_BOWEL)
    return _saida_das_construcoes({_rc.CHAVE_ANUS: _rc.anus(
        masks, grade, log=log, cru=cru, bag=bag)})


def _acabamento_da_crista(nome, m, masks, grade, log=None):
    import radai_constructs as _rc
    c = _rc.crista_iliaca(masks, grade, nome)
    if not c:
        return None, None, {}
    return c.mascara, c.descricao, {}


def _acabamento_do_anus(nome, m, masks, grade, log=None):
    import radai_constructs as _rc
    c = _rc.anus(masks, grade)
    if not c:
        return None, None, {}
    return c.mascara, c.descricao, {}


_CONTEM_DO_ANUS = ("rectum", "colon", "bag_bowel", "prostate",
                   "small_intestine", "small_bowel", "anal_canal")

# GUARDA: as duas entram antes da Bag_Bowel_OAR, que continua a ultima
# construcao (recebe a pele pronta).
_ONDE_ENTRAM = [i for i, _c in enumerate(CONSTRUCOES)
                if _c.get("cod") == "bag_bowel_oar"][0]
CONSTRUCOES[_ONDE_ENTRAM:_ONDE_ENTRAM] = [
    {"cod": "crista_iliaca", "funcao": _construir_cristas_iliacas,
     "momento": "no_fim", "exige_hu": False,
     "exige": ("hip_left|hip_right",),
     "saidas": {
         "iliac_crest_left": {
             "suavizar_mm": 0.0, "recortar_por": (),
             "contem": ("hip_left", "bone_pelvic"),
             "acabamento": _acabamento_da_crista,
             "descricao": u"IliacCrest_L: o osso do quadril esquerdo menos o "
                          u"sacro e menos o femur para baixo (recorte do "
                          u"FULL)."},
         "iliac_crest_right": {
             "suavizar_mm": 0.0, "recortar_por": (),
             "contem": ("hip_right", "bone_pelvic"),
             "acabamento": _acabamento_da_crista,
             "descricao": u"IliacCrest_R: o osso do quadril direito menos o "
                          u"sacro e menos o femur para baixo (recorte do "
                          u"FULL)."}}},
    {"cod": "anus", "funcao": _construir_anus,
     "momento": "no_fim", "exige_hu": False,
     "exige": ("abdominal_cavity", "hip_left|hip_right"),
     "saidas": {
         "anus": {
             "suavizar_mm": 0.0, "recortar_por": (),
             "contem": _CONTEM_DO_ANUS,
             "acabamento": _acabamento_do_anus,
             "descricao": u"Anus: a Bag_Bowel_ai do ultimo corte do osso "
                          u"pelvico para baixo (recorte do FULL)."}}}]
del _ONDE_ENTRAM



ORDEM_DO_FULL = (
    ("regras", u"regras de gravacao (R1 a R4)"),
    ("fusao_do_indice_26", u"indice 26 fundido ao sacro"),
    ("derrame_por_lado", u"derrame pleural por lado, fora do pulmao"),
    ("construcoes", "antes_do_refino"),
    ("refino", u"refino por densidade"),
    ("construcoes", "depois_do_refino"),
    ("margens", u"margem da traqueia e de cada vaso"),
    ("construcoes", "depois_das_margens"),
    ("construcoes", "depois_do_pericardio"),
    ("coracao_do_modelo", u"recuo do coracao"),
    ("compostos", u"compostos"),
    ("derivadas", u"reto e colon (derivadas)"),
    ("construcoes", "no_fim"),
    ("glandula_por_lado", u"glandula mamaria por lado"),
)


CHAVE_GLANDULA_BILATERAL = "breast"
CHAVES_GLANDULA_POR_LADO = {"L": "breast_left", "R": "breast_right"}


def _tem_linha_media(masks, cru=None):
    import radai_skin
    for prefixos in (("sternum",), ("vertebrae_",), radai_skin.PULMOES):
        try:
            m = radai_skin.uniao_por_nome(masks, prefixos, cru=cru)
            if m is not None and bool(np.asarray(m).any()):
                return True
        except Exception:
            continue
    return False


def separar_glandula_por_lado(masks, grade, cru=None, log=None):
    if grade is None or CHAVE_GLANDULA_BILATERAL not in masks:
        return []
    import radai_skin
    try:
        gl = _bool_seguro(masks[CHAVE_GLANDULA_BILATERAL])
    except Exception:
        return []
    if not gl.any():
        return []
    if not _tem_linha_media(masks, cru):
        linha = None
    else:
        linha = radai_skin.linha_media_por_corte(masks, grade, cru=cru)
    if linha is None:
        if log:
            log(u"glandula mamaria: sem referencia para a linha media — "
                u"fica o contorno bilateral (breast)")
        return []
    esq, dir_ = radai_skin.separar_por_lado(gl, grade, linha)
    entraram, ja = [], []
    for lado, m in (("L", esq), ("R", dir_)):
        chave = CHAVES_GLANDULA_POR_LADO[lado]
        if chave in masks:
            ja.append(chave)
            continue
        if _bool_seguro(m).any():
            masks[chave] = m
            entraram.append(chave)
    lados = set(entraram) | set(ja)
    if lados >= set(CHAVES_GLANDULA_POR_LADO.values()) or (
            entraram and not ja):
        del masks[CHAVE_GLANDULA_BILATERAL]
    if log:
        try:
            log(u"glandula mamaria por lado: %s%s"
                % (u", ".join(entraram) or u"nenhum lado novo",
                   (u" (ja existia(m), da curadoria: %s — nao sobrescrevi)"
                    % u", ".join(ja)) if ja else u""))
        except Exception:
            pass
    return entraram

CHAVE_DERRAME_PLEURAL = "pleural_effusion"
CHAVES_DERRAME_POR_LADO = {"L": "pleural_effusion_left",
                           "R": "pleural_effusion_right"}
CHAVE_DERRAME_PERICARDICO = "pericardial_effusion"


def separar_derrame_por_lado(masks, grade, cru=None, log=None):
    fora = {"lados": [], "descontado_cm3": {}}
    if grade is None or CHAVE_DERRAME_PLEURAL not in masks:
        return fora
    import radai_skin
    try:
        der = _bool_seguro(masks[CHAVE_DERRAME_PLEURAL])
    except Exception:
        return fora
    if not der.any():
        return fora
    pe = radai_skin.uniao_por_nome(masks, radai_skin.PULMAO_ESQ, cru=cru)
    pd = radai_skin.uniao_por_nome(masks, radai_skin.PULMAO_DIR, cru=cru)
    if not _tem_linha_media(masks, cru):
        if log:
            log(u"derrame pleural: sem referencia para a linha media nem "
                u"pulmao — fica o contorno bilateral (pleural_effusion)")
        linha = None
    else:
        linha = radai_skin.linha_media_por_corte(masks, grade, cru=cru)
    if linha is not None or (pe is not None and pd is not None):
        esq, dir_ = radai_skin.cavidade_por_lado(der, pe, pd, grade, linha)
        for lado, m in (("L", esq), ("R", dir_)):
            m = _bool_seguro(m)
            if m.any():
                masks[CHAVES_DERRAME_POR_LADO[lado]] = m
                fora["lados"].append(CHAVES_DERRAME_POR_LADO[lado])
        if fora["lados"]:
            del masks[CHAVE_DERRAME_PLEURAL]
    vx = float(np.prod(grade.spacing)) / 1000.0
    try:
        import radai_skin as _sk
        pulmoes = tuple(_sk.PULMOES)
    except Exception:
        pulmoes = ()
    for nome in list(masks):
        if nome not in pulmoes:
            continue
        try:
            p = _bool_seguro(masks[nome])
            comum = int((p & der).sum())
            if not comum:
                continue
            novo = p & ~der
            if not novo.any():
                if log:
                    log(u"`%s` ficaria VAZIO sem o derrame — nao descontei"
                        % nome)
                continue
            masks[nome] = novo
            fora["descontado_cm3"][nome] = round(comum * vx, 2)
        except Exception:
            continue
    if log:
        try:
            log(u"derrame pleural: %s; tirado dos pulmoes: %s"
                % (u", ".join(fora["lados"]) or u"bilateral (sem partir)",
                   u", ".join(u"%s %.1f cm3" % kv for kv in
                              sorted(fora["descontado_cm3"].items()))
                   or u"nada (sem sobreposicao)"))
        except Exception:
            pass
    return fora


MOMENTOS_DAS_CONSTRUCOES = tuple(v for e, v in ORDEM_DO_FULL
                                 if e == "construcoes")


def _exige_presente(masks, exige):
    for req in exige or ():
        opcoes = [o for o in str(req).split("|") if o]
        ok = False
        for o in opcoes:
            k = _nomes.achar(masks, o)
            if k is None:
                continue
            try:
                if _bool_seguro(masks[k]).any():
                    ok = True
                    break
            except Exception:
                continue
        if not ok:
            return req
    return None


def _contorno_externo_da_serie(ctx, volume_hu, grade, hu_ok, meta, log):
    if "externo" in ctx:
        return ctx["externo"]
    ext = corpo = None
    if hu_ok and volume_hu is not None and grade is not None:
        t0 = time.time()
        try:
            import radai_skin
            ext, corpo = radai_skin.contorno_externo(volume_hu, grade,
                                                     log=log,
                                                     com_o_corpo=True)
        except Exception as e:
            ext = corpo = None
            if log:
                try:
                    log(u"contorno externo: %s — quem o usa recalcula ou nao "
                        u"sai" % str(e)[:140])
                except Exception:
                    pass
        meta.setdefault("tempos", []).append(
            (u"contorno externo (uma vez)", time.time() - t0))
    ctx["externo"] = ext
    ctx["corpo"] = corpo if corpo is not None else ext
    return ext


def _corpo_da_serie(ctx, volume_hu, grade, hu_ok, meta, log):
    if "corpo" not in ctx:
        ext = _contorno_externo_da_serie(ctx, volume_hu, grade, hu_ok, meta,
                                         log)
        ctx.setdefault("corpo", ext)
    return ctx["corpo"]


def _faltou_de(saida):
    try:
        return [u"%s" % f for f in (getattr(saida, "faltou", None) or ())
                if u"%s" % f]
    except Exception:
        return []


def _frase_da_saida(faltou, nome):
    alvos = [str(nome).lower()]
    tps = TG263.get(nome) if isinstance(TG263, dict) else None
    if tps:
        alvos.append(str(tps).lower())
    for f in faltou or ():
        b = f.lower()
        if any(a in b for a in alvos):
            return f
    return None


def _rodar_construcoes(fora, momento, grade, volume_hu, hu_ok, meta, log,
                       torax=None, cru=None, ctx=None, so_cods=None):
    ctx = {} if ctx is None else ctx
    meta.setdefault("faltou", {})
    for c in CONSTRUCOES:
        if c.get("momento") != momento:
            continue
        cod = c.get("cod", "?")
        if so_cods is not None and cod not in so_cods:
            meta.setdefault("fora_do_filtro", []).append(cod)
            continue
        if c.get("exige_hu") and not hu_ok:
            meta["nao_sairam"].append((cod, u"a serie nao e TC (le densidade)"))
            continue
        falta = _exige_presente(fora, c.get("exige"))
        if falta:
            _pela_regra = meta.get("saiu_pela_regra") or {}
            _qual = None
            for _o in str(falta).split("|"):
                _k = _o if _o in _pela_regra else _nomes.achar(_pela_regra, _o)
                if _k is not None:
                    _qual = (_k, _pela_regra[_k])
                    break
            if _qual:
                meta["nao_sairam"].append(
                    (cod, u"`%s` saiu pela regra %s" % _qual))
                continue
            meta["nao_sairam"].append(
                (cod, u"falta %s nesta serie" % falta.replace("|", " ou ")))
            continue
        t0 = time.time()
        try:
            _kw = {}
            try:
                import inspect as _insp
                _ps = _insp.signature(c["funcao"]).parameters
                _tudo = any(p.kind == p.VAR_KEYWORD for p in _ps.values())
                for _k, _v in (("volume_hu", volume_hu), ("log", log),
                               ("torax", torax), ("cru", cru)):
                    if _tudo or _k in _ps:
                        _kw[_k] = _v
                if _tudo or "externo" in _ps:
                    _kw["externo"] = _contorno_externo_da_serie(
                        ctx, volume_hu, grade, hu_ok, meta, log)
                if _tudo or "construidas" in _ps:
                    _kw["construidas"] = dict(
                        (k, fora[k]) for k in meta["construcoes"] if k in fora)
            except (TypeError, ValueError):
                _kw = {"volume_hu": volume_hu, "log": log}
            saida = c["funcao"](_Sobreposto(fora), grade, **_kw)
            if saida is not None and not isinstance(saida, dict):
                _decl = list((c.get("saidas") or {}))
                saida = ({_decl[0]: saida} if len(_decl) == 1 else {})
            saida = {} if saida is None else saida
        except Exception as e:
            meta["nao_sairam"].append((cod, u"%s: %s" % (type(e).__name__,
                                                         str(e)[:100])))
            if log:
                log(u"construcao `%s` falhou (%s) — as outras estruturas "
                    u"seguem" % (cod, str(e)[:140]))
                try:
                    for _l in traceback.format_exc().strip().splitlines()[-6:]:
                        log(u"   " + _l)
                except Exception:
                    pass
            continue
        declaradas = c.get("saidas") or {}
        entraram = []
        for nome, m in saida.items():
            desc_da_serie = None
            if (isinstance(m, tuple) and len(m) == 2
                    and isinstance(m[1], str)):
                m, desc_da_serie = m
            try:
                if not _bool_seguro(m).any():
                    continue
            except Exception:
                continue
            fora[nome] = m
            entraram.append(nome)
            spec = dict(declaradas.get(nome) or {})
            if desc_da_serie is not None:
                spec["descricao"] = desc_da_serie
            _rm = (getattr(saida, "reune_mascaras", None) or {}).get(nome)
            if _rm is not None:
                spec["reune_mascaras"] = _rm
            _cv = (getattr(saida, "cava_inferior", None) or {}).get(nome)
            if _cv is not None:
                spec["cava_inferior"] = _cv
            _mh = (getattr(saida, "coracao_do_modelo", None) or {}).get(nome)
            if _mh is not None:
                spec["coracao_do_modelo"] = _mh
            meta["construcoes"][nome] = spec
            if spec.get("descricao"):
                meta["observacoes"][nome] = spec["descricao"]
        faltou = _faltou_de(saida)
        if faltou:
            meta["faltou"][cod] = list(faltou)
        if not entraram:
            meta["nao_sairam"].append(
                (cod, faltou[0] if faltou else
                 u"a construcao nao devolveu nada nesta serie"))
        else:
            ditas = set()
            for nome in declaradas:
                if nome in entraram:
                    continue
                f = _frase_da_saida(faltou, nome)
                if f and f not in ditas:
                    ditas.add(f)
                    meta["nao_sairam"].append((cod, f))
        meta["tempos"].append((u"construcao %s" % cod, time.time() - t0))


def construcoes_para(alvo):
    if alvo is None:
        return None
    alvo = set(alvo)
    por_saida = {}
    for c in CONSTRUCOES:
        for nome in (c.get("saidas") or {}):
            por_saida[nome] = c.get("cod")
    precisa = set()
    pendentes = [c for c in CONSTRUCOES
                 if set(c.get("saidas") or {}) & alvo]
    while pendentes:
        c = pendentes.pop()
        cod = c.get("cod")
        if cod in precisa:
            continue
        precisa.add(cod)
        for spec in (c.get("saidas") or {}).values():
            for dep in tuple((spec or {}).get("um_volume_com") or ()):
                d = por_saida.get(dep)
                if d and d not in precisa:
                    pendentes.extend(x for x in CONSTRUCOES
                                     if x.get("cod") == d)
    return precisa


def insumos_das_derivadas():
    fora = set()
    for mae, spec in DERIVADAS.items():
        for req in spec.get("exige") or ():
            fora.update(o for o in str(req).split("|") if o)
        if spec.get("plano_do_sacro"):
            fora.update(PLATO_DO_SACRO)
        for marcos, _ext, _off, _nome in spec.get("planos") or ():
            fora.update(m for m in marcos if not str(m).startswith("_"))
    return fora


def protegidas_da_origem(origem):
    return set(k for k, v in dict(origem or {}).items()
               if v not in ("", FONTE_PADRAO, "derivada"))


def preparar_full(masks, grade=None, log=None, volume_hu=None, modalidade=None,
                  torax=None, cru=None, para=None, protegidas=None):
    fora = _Sobreposto(masks)
    meta = {"construcoes": {}, "observacoes": {}, "nao_sairam": [],
            "tempos": []}

    def _diz(m):
        if log:
            try:
                log(m)
            except Exception:
                pass

    _cm = _nomes.CHAVE_DO_CORACAO_DO_MODELO
    if "heart" in fora and _cm not in fora:
        fora[_cm] = fora["heart"]
        del fora["heart"]

    if grade is None:
        _diz(u"FULL: sem a grade da serie o pos-processamento nao roda")
        return fora, meta

    _hu_ok, _hu_pq = (False, u"sem o volume da serie")
    if volume_hu is not None:
        _hu_ok, _hu_pq = _hu_valido(volume_hu, modalidade)
    if not _hu_ok:
        _diz(u"pele/parede e refino por densidade: NAO rodaram — %s. O "
             u"recorte pela diretriz (marcos) e o coracao continuam" % _hu_pq)
    _modal_hu = "CT" if _hu_ok else (modalidade or "?")

    def _etapa(nome, fn):
        t0 = time.time()
        try:
            fn()
        except Exception as exc:
            _diz(u"%s: %s — as outras estruturas seguem" % (nome, str(exc)[:140]))
        meta["tempos"].append((nome, time.time() - t0))

    ctx = {}
    _conhecidos = set(MOMENTOS_DAS_CONSTRUCOES)
    for c in CONSTRUCOES:
        if c.get("momento") not in _conhecidos:
            meta["nao_sairam"].append(
                (c.get("cod", "?"), u"momento `%s` fora de ORDEM_DO_FULL — "
                 u"ela nunca roda" % c.get("momento")))
    _alvo = frozenset(para) if para is not None else None
    _so_cods = construcoes_para(_alvo)

    def _passo_regras():
        ext = None
        if _hu_ok:
            ext = _corpo_da_serie(ctx, volume_hu, grade, _hu_ok, meta, log)
        else:
            _diz(u"regras de gravacao: R3 (fora do corpo) nao roda — %s"
                 % _hu_pq)
        rel = {}

        def _aplica():
            rel.update(aplicar_regras_de_gravacao(fora, grade, externo=ext,
                                                  cru=cru, log=log))
        _etapa(u"regras de gravacao (R1 a R4)", _aplica)
        meta["regras_de_gravacao"] = list(rel.get("removidas") or [])
        meta["ilhas_em_revisao"] = list(rel.get("revisao") or [])
        meta["saiu_pela_regra"] = dict(rel.get("saiu") or {})
        inteiras = sum(1 for r in meta["regras_de_gravacao"] if r["inteira"])
        if meta["regras_de_gravacao"] or meta["ilhas_em_revisao"]:
            _diz(u"regras de gravacao: %d estrutura(s) sairam inteiras, %d "
                 u"perderam pedacos, %d com ilha mantida para revisao"
                 % (inteiras, len(meta["regras_de_gravacao"]) - inteiras,
                    len(meta["ilhas_em_revisao"])))

    def _passo_refino():
        if _hu_ok:
            _etapa(u"refino por densidade",
                   lambda: aplicar_refino_por_hu(fora, grade, volume_hu,
                                                 log=log,
                                                 modalidade=_modal_hu))

    def _passo_margens():
        _antes = set(meta["observacoes"])
        _etapa(u"margem da traqueia e de cada vaso",
               lambda: aplicar_margens_de_oar(
                   fora, grade, log=log, ressalvas=meta["observacoes"]))
        _etapa(u"aorta recortada dos pulmoes, do esofago e da traqueia",
               lambda: recortar_aorta_dos_vizinhos(fora, grade, log=log))
        _perdidas = set(meta["observacoes"]) - _antes
        for _c, _partes in sorted(COMPOSTOS.items()):
            _de = [p for p in (_partes or ()) if p in _perdidas]
            if _de and _c not in meta["observacoes"]:
                meta["observacoes"][_c] = (
                    u"%s (%d vaso(s) do composto)"
                    % (meta["observacoes"][_de[0]].rstrip(u"."), len(_de)))

    def _passo_coracao_do_modelo():
        if _cm in meta.get("saiu_pela_regra", {}) or "heart" in meta.get(
                "saiu_pela_regra", {}):
            return
        if "heart" not in fora and _cm in fora:
            try:
                if _bool_seguro(fora[_cm]).any():
                    fora["heart"] = _bool_seguro(fora[_cm]).copy()
                    meta["construcoes"]["heart"] = dict(
                        CONSTRUCOES_POR_SAIDA().get("heart") or {})
                    meta["observacoes"]["heart"] = (
                        u"O coracao de radioterapia NAO pode ser montado nesta "
                        u"serie; este contorno e o heart do modelo, sem os "
                        u"vasos da janela e sem o fechamento do saco.")
                    _diz(u"coracao de radioterapia: nao montado — o Heart_ai "
                         u"desta serie e o heart do modelo, e o arquivo diz "
                         u"isso")
            except Exception:
                pass

    def _passo_compostos():
        _so_comp = (set(COMPOSTOS) & _alvo) if _alvo is not None else None
        _etapa(u"compostos",
               lambda: recompor_compostos(fora, log=None, criar=True,
                                          subtrair=set(meta["construcoes"]),
                                          so=_so_comp))

    def _passo_derrame_por_lado():
        if _alvo is not None and not (
                (set(CHAVES_DERRAME_POR_LADO.values())
                 | {CHAVE_DERRAME_PLEURAL}) & _alvo):
            return
        _r = {}
        _etapa(u"derrame pleural por lado",
               lambda: _r.update(separar_derrame_por_lado(
                   fora, grade, cru=cru, log=log)))
        meta["derrame"] = dict(_r)

    def _passo_glandula_por_lado():
        if _alvo is not None and not (
                set(CHAVES_GLANDULA_POR_LADO.values()) & _alvo):
            return
        _etapa(u"glandula mamaria por lado",
               lambda: separar_glandula_por_lado(fora, grade, cru=cru,
                                                 log=log))

    def _passo_fusao_do_indice_26():
        _r = {}
        _etapa(u"indice 26 fundido ao sacro",
               lambda: _r.update(fundir_indice_26_no_sacro(fora, grade,
                                                           log=log)))
        meta["fusao_do_indice_26"] = dict(_r)
        if _r.get("cm3"):
            _obs = OBSERVACAO_DO_INDICE_26 % float(_r["cm3"])
            for _k in ("sacrum", "bone_pelvic"):
                meta["observacoes"][_k] = _obs

    def _passo_derivadas():
        _criadas = []
        _tol = int((meta.get("fusao_do_indice_26") or {}).get(
            "pecas_novas") or 0)

        def _deriva():
            _criadas.extend(aplicar_derivadas(
                fora, grade, log=log, protegidas=set(protegidas or ()),
                tolerancia_de_pecas=_tol))
        _etapa(u"reto e colon (derivadas)", _deriva)
        meta["derivadas"] = {"criadas": sorted(_criadas),
                             "maes": sorted(m for m in DERIVADAS
                                            if m in fora)}

    passos = {"regras": _passo_regras,
              "fusao_do_indice_26": _passo_fusao_do_indice_26,
              "derivadas": _passo_derivadas,
              "derrame_por_lado": _passo_derrame_por_lado,
              "refino": _passo_refino, "margens": _passo_margens,
              "coracao_do_modelo": _passo_coracao_do_modelo,
              "compostos": _passo_compostos,
              "glandula_por_lado": _passo_glandula_por_lado}
    for etapa, valor in ORDEM_DO_FULL:
        if etapa == "construcoes":
            _rodar_construcoes(fora, valor, grade, volume_hu, _hu_ok, meta,
                               log, torax=torax, cru=cru, ctx=ctx,
                               so_cods=_so_cods)
        else:
            passos[etapa]()

    _corpo = ctx.get("corpo", ctx.get("externo"))
    if _corpo is not None:
        meta["externo"] = _corpo

    for cod, motivo in meta["nao_sairam"]:
        _diz(u"FULL: `%s` nao saiu — %s" % (cod, motivo))
    meta["fora_do_oar_por_regiao"] = fora_do_oar_por_regiao(fora, grade)
    if _alvo is not None:
        fora = _filtrar_para(fora, _alvo, meta, _diz)
    return fora, meta


def insumos_da_particao(alvo):
    alvo = set(alvo or ())
    partes = partes_de_composto()
    fora = set()
    for membros in GRUPOS_DISJUNTOS.values():
        membros = list(membros)
        if set(membros) & alvo:
            fora.update(m for m in membros
                        if m not in alvo and m not in partes)
    return fora


def _filtrar_para(fora, alvo, meta, diz=None):
    _deriv = insumos_das_derivadas()
    _grupo = insumos_da_particao(alvo)
    manter = []
    for k in list(fora):
        if (k in alvo or k in meta.get("construcoes", {}) or k in _deriv
                or k in _grupo or _nomes.canonico(k) in _grupo):
            manter.append(k)
    _fica = set(manter)
    saiu = [k for k in fora if k not in _fica]
    filtrado = dict((k, fora[k]) for k in manter)
    gravar = sorted(k for k in manter if k in alvo)
    insumos = sorted(k for k in manter if k not in alvo)
    meta["filtro"] = {"alvo": len(alvo), "gravar": gravar,
                      "insumos": insumos, "fora": len(saiu),
                      "fora_do_filtro": sorted(set(
                          meta.get("fora_do_filtro") or ()))}
    if diz is not None:
        diz(u"FAST: o filtro do OAR_Fast deixou %d estrutura(s) — %d vao ao "
            u"arquivo, %d so como insumo (%s); %d do FULL ficaram fora%s"
            % (len(manter), len(gravar), len(insumos),
               u", ".join(insumos) or u"nenhum", len(saiu),
               (u"; construcao(oes) que nao rodaram no FAST: %s"
                % u", ".join(meta["filtro"]["fora_do_filtro"]))
               if meta["filtro"]["fora_do_filtro"] else u""))
    return filtrado


def CONSTRUCOES_POR_SAIDA():
    fora = {}
    for c in CONSTRUCOES:
        for nome, spec in (c.get("saidas") or {}).items():
            fora[nome] = spec
    return fora


VOLUME_MINIMO_PULMAO_CM3 = 200.0
VOLUME_MINIMO_CORACAO_CM3 = 100.0

MARCOS_DE_REGIAO = (
    ("cabeca_pescoco", ("brain",), 150.0),
    ("torax", ("lung_left", "lung_right"), VOLUME_MINIMO_PULMAO_CM3),
    ("abdome", ("liver", "spleen", "kidney_left", "kidney_right",
                "pancreas", "stomach"), 400.0),
    ("pelve", ("hip_left", "hip_right", "urinary_bladder", "sacrum",
               "prostate"), 150.0),
)


def _volume_cm3(masks, nomes, grade):
    import numpy as np

    if grade is None:
        return 0.0
    try:
        vox = float(np.prod(grade.spacing)) / 1000.0
    except Exception:
        return 0.0
    if not vox:
        return 0.0
    acc = None
    for n in nomes:
        n = _nomes.achar(masks, n) or n
        if n not in masks:
            continue
        a = np.asarray(masks[n], dtype=bool)
        acc = a if acc is None else (acc | a)
    if acc is None:
        return 0.0
    return float(acc.sum()) * vox


def torax_no_campo(masks, grade=None):
    import numpy as np

    lados = [masks[n] for n in ("lung_left", "lung_right") if n in masks]
    if not lados:
        return True, u"nao ha pulmao desenhado — nao da para afirmar que nao ha torax"
    m = np.asarray(lados[0], dtype=bool)
    for outro in lados[1:]:
        m = m | np.asarray(outro, dtype=bool)
    if not m.any():
        return True, u"o pulmao veio vazio — nao da para afirmar que nao ha torax"

    vox_cm3 = (float(np.prod(grade.spacing)) / 1000.0) if grade is not None else 0.0
    if vox_cm3:
        vol = float(m.sum()) * vox_cm3
        if vol < VOLUME_MINIMO_PULMAO_CM3:
            return False, (u"o pulmao tem %.0f cm3 no campo (piso de %.0f) — e "
                           u"uma ponta de pulmao, e nao um torax"
                           % (vol, VOLUME_MINIMO_PULMAO_CM3))

    z = np.where(m.any(axis=(1, 2)))[0]
    z0, z1, nz = int(z.min()), int(z.max()), int(m.shape[0])
    if z0 == 0 or z1 == nz - 1:
        ponta = u"cranial" if z1 >= nz - 1 else u"caudal"
        return False, (u"o pulmao encosta na borda %s do campo (cortes %d..%d "
                       u"de %d) — a serie pega PARTE do torax, e nao o torax"
                       % (ponta, z0, z1, nz))

    if "heart" in masks:
        c = np.asarray(masks["heart"], dtype=bool)
        if vox_cm3 and c.any():
            vc = float(c.sum()) * vox_cm3
            if vc < VOLUME_MINIMO_CORACAO_CM3:
                return False, (u"o coracao tem %.0f cm3 no campo (piso de %.0f)"
                               % (vc, VOLUME_MINIMO_CORACAO_CM3))
    return True, u"pulmao inteiro no campo"


def regioes_no_campo(masks, grade=None):
    fora, laudo = [], []
    if grade is None:
        return (), [u"sem grade: nao da para medir volume, e regiao por "
                    u"contagem de voxel mede outra coisa em cada serie"]

    for cod, nomes, piso in MARCOS_DE_REGIAO:
        if cod == "torax":
            tem, pq = torax_no_campo(masks, grade=grade)
            if tem:
                fora.append(cod)
            laudo.append(u"torax: %s (%s)" % (u"sim" if tem else u"nao", pq))
            continue
        vol = _volume_cm3(masks, nomes, grade)
        if vol >= piso:
            fora.append(cod)
            laudo.append(u"%s: sim (%.0f cm3, piso %.0f)" % (cod, vol, piso))
        elif vol > 0:
            laudo.append(u"%s: nao (%.0f cm3, piso %.0f — e uma ponta, e nao a "
                         u"regiao)" % (cod, vol, piso))
        else:
            laudo.append(u"%s: nao (nenhum marco desenhado)" % cod)
    return tuple(fora), laudo


REGIAO_EXIGIDA_NO_OAR = {
    "bone_pelvic": "pelve",
    "iliac_crest_left": "pelve",
    "iliac_crest_right": "pelve",
    "anus": "pelve",
}


FORA_DO_OAR_NA_REGIAO = {
    "cabeca_pescoco": (
        "hyoid", "cricoid_cartilage", "thyroid_cartilage",
        "nasal_cavity", "auditory_canal_left", "auditory_canal_right",
        "hard_palate", "larynx_air", "digastric_left", "digastric_right",
        "masseter_left", "masseter_right", "lateral_pterygoid_left",
        "lateral_pterygoid_right", "medial_pterygoid_left",
        "medial_pterygoid_right", "temporalis_left", "temporalis_right",
        "soft_palate", "hypopharynx", "nasopharynx", "oropharynx",
        "sinus_frontal", "sinus_maxillary", "skull", "styloid_process_left",
        "styloid_process_right", "teeth_lower", "teeth_upper", "tongue",
        "zygomatic_arch_left", "zygomatic_arch_right"),
}
FORA_DO_OAR_NO_PESCOCO_SEM_TORAX = ("great_arteries", "great_veins")


def fora_do_oar_por_regiao(masks, grade):
    try:
        if grade is None:
            return {}
        exige = [k for k in REGIAO_EXIGIDA_NO_OAR
                 if _nomes.achar(masks, k) is not None]
        na_regiao = {}
        for cod, chaves in FORA_DO_OAR_NA_REGIAO.items():
            for k in chaves:
                if _nomes.achar(masks, k) is not None:
                    na_regiao[k] = cod
        sem_torax = [k for k in FORA_DO_OAR_NO_PESCOCO_SEM_TORAX
                     if _nomes.achar(masks, k) is not None]
        if not (exige or na_regiao or sem_torax):
            return {}
        import radai_topography
        an = radai_topography.anatomia_da_base(
            masks, grade, motor=sys.modules[__name__])
        regioes = tuple(an.get("regioes") or ())
        laudo = list(an.get("laudo") or ())
    except Exception:
        return {}

    def _linha(cod):
        pref = {"cabeca_pescoco": u"pescoco:"}.get(cod, cod + u":")
        return next((l for l in laudo if l.startswith(pref)),
                    u"%s: nao medida" % cod)

    fora = {}
    for k in exige:
        cod = REGIAO_EXIGIDA_NO_OAR[k]
        if cod in regioes:
            continue
        fora[k] = u"%s nao identificada pela anatomia (%s)" % (cod, _linha(cod))
    for k, cod in sorted(na_regiao.items()):
        if cod in regioes:
            fora[k] = (u"%s identificado pela anatomia: fica so no FULL (%s)"
                       % (cod, _linha(cod)))
    if "cabeca_pescoco" in regioes and "torax" not in regioes:
        for k in sem_torax:
            fora[k] = (u"cabeca_pescoco sem torax identificado: fica so no "
                       u"FULL (%s; %s)" % (_linha("cabeca_pescoco"),
                                           _linha("torax")))
    return fora


VERTEBRAS_DO_PESCOCO = ("vertebrae_C2", "vertebrae_C3", "vertebrae_C4")
VOLUME_MINIMO_VERTEBRA_CERVICAL_CM3 = 5.0
# GUARDA: na base (total) o rotulo `skull` contem o cranio E a mandibula; com
# a craniofacial_structures ela vem a parte. Mede-se a uniao das duas, para a
# decisao antes e depois das tasks de cabeca e pescoco ser a mesma, em duas
# faixas: a da mandibula, do topo do C1 (sem o C1, do topo do C2) ao fim do
# C4, e o cranio acima do topo do C1. Uma das duas confirma, sempre com C2 a
# C4: a mandibula pequena ou desdentada confirma pelo cranio, e a TC de torax
# que so sobe ao C1 nao tem cranio acima dele.
MANDIBULA_E_CRANIO = ("skull", "mandible")
TOPO_DA_FAIXA_DA_MANDIBULA = ("vertebrae_C1", "vertebrae_C2")
FIM_DA_FAIXA_DA_MANDIBULA = "vertebrae_C4"
VOLUME_MINIMO_DA_MANDIBULA_CM3 = 80.0
VOLUME_MINIMO_DO_CRANIO_ACIMA_DO_C1_CM3 = 50.0
CERVICAIS = tuple("vertebrae_C%d" % n for n in range(1, 8))


def _mascara_de(masks, nome, cru=None):
    for fonte in (masks, cru):
        if fonte is None:
            continue
        try:
            k = _nomes.achar(fonte, nome)
            if k is not None:
                return fonte[k]
        except Exception:
            continue
    return None


def _cm3_da_mascara(m, grade):
    try:
        vox = (float(grade.spacing[0]) * float(grade.spacing[1])
               * float(grade.spacing[2])) / 1000.0
    except Exception:
        return 0.0
    if m is None:
        return 0.0
    return float(np.asarray(m, dtype=bool).sum()) * vox


def pescoco_no_campo(masks, grade, cru=None):
    if grade is None:
        return False, u"pescoco: sem grade, nao da para medir a vertebra em cm3"
    vols = {}
    for n in CERVICAIS:
        vols[n] = _cm3_da_mascara(_mascara_de(masks, n, cru), grade)
    piso = VOLUME_MINIMO_VERTEBRA_CERVICAL_CM3
    vertebras = all(vols.get(n, 0.0) >= piso for n in VERTEBRAS_DO_PESCOCO)
    mand = mandibula_no_campo_cm3(masks, grade, cru)
    piso_m = VOLUME_MINIMO_DA_MANDIBULA_CM3
    cranio = cranio_acima_do_c1_cm3(masks, grade, cru)
    piso_c = VOLUME_MINIMO_DO_CRANIO_ACIMA_DO_C1_CM3
    pela_mandibula = mand >= piso_m
    pelo_cranio = cranio >= piso_c
    tem = vertebras and (pela_mandibula or pelo_cranio)
    no_campo = [u"%s %.1f" % (n.split("_")[-1], v)
                for n, v in sorted(vols.items()) if v > 0]
    faixa = faixa_da_mandibula(masks, grade, cru)
    topo = faixa[2].split("_")[-1] if faixa is not None else None
    onde = (u"do topo do %s ao fim do C4" % topo
            if faixa is not None else u"sem C1 nem C2, sem faixa")
    acima = (u"acima do topo do %s" % topo if faixa is not None
             else u"sem C1 nem C2, sem faixa")
    if not vertebras:
        caminho = u"nenhum: faltam C2, C3 ou C4"
    elif pela_mandibula and pelo_cranio:
        caminho = u"a mandibula e o cranio"
    elif pela_mandibula:
        caminho = u"a mandibula"
    elif pelo_cranio:
        caminho = u"o cranio acima do C1"
    else:
        caminho = u"nenhum"
    laudo = (u"pescoco: %s (C2, C3 e C4 com pelo menos %.0f cm3 cada: %s; "
             u"mandibula no campo (%s), %.1f cm3, piso %.0f: %s; cranio %s, "
             u"%.1f cm3, piso %.0f: %s; confirmado por: %s; cervicais no "
             u"campo, em cm3: %s)"
             % (u"sim" if tem else u"nao", piso,
                u"sim" if vertebras else u"nao", onde, mand, piso_m,
                u"sim" if pela_mandibula else u"nao", acima, cranio, piso_c,
                u"sim" if pelo_cranio else u"nao", caminho,
                u", ".join(no_campo) or u"nenhuma"))
    return tem, laudo


def _cortes_da_mascara(m, eixo):
    b = np.asarray(m, dtype=bool)
    outros = tuple(i for i in range(b.ndim) if i != eixo)
    c = np.flatnonzero(b.any(axis=outros))
    return c if c.size else None


def faixa_da_mandibula(masks, grade, cru=None):
    if grade is None:
        return None
    eixo, sinal = grade.eixo_sinal("sup")
    for nome in TOPO_DA_FAIXA_DA_MANDIBULA:
        m = _mascara_de(masks, nome, cru)
        c = None if m is None else _cortes_da_mascara(m, eixo)
        if c is None:
            continue
        topo = int(c.max()) if sinal > 0 else int(c.min())
        m4 = _mascara_de(masks, FIM_DA_FAIXA_DA_MANDIBULA, cru)
        c4 = None if m4 is None else _cortes_da_mascara(m4, eixo)
        fim = None
        if c4 is not None:
            fim = int(c4.min()) if sinal > 0 else int(c4.max())
        return topo, fim, nome
    return None


def _osso_da_cabeca(masks, cru=None):
    acc = None
    for n in MANDIBULA_E_CRANIO:
        m = _mascara_de(masks, n, cru)
        if m is None:
            continue
        b = np.asarray(m, dtype=bool)
        acc = b.copy() if acc is None else (acc | b)
    return acc


def cranio_acima_do_c1_cm3(masks, grade, cru=None):
    acc = _osso_da_cabeca(masks, cru)
    faixa = faixa_da_mandibula(masks, grade, cru)
    if acc is None or faixa is None:
        return 0.0
    topo = faixa[0]
    eixo, sinal = grade.eixo_sinal("sup")
    idx = np.arange(acc.shape[eixo])
    acima = (idx > topo) if sinal > 0 else (idx < topo)
    forma = [1] * acc.ndim
    forma[eixo] = -1
    return _cm3_da_mascara(acc & acima.reshape(forma), grade)


def mandibula_no_campo_cm3(masks, grade, cru=None):
    acc = _osso_da_cabeca(masks, cru)
    faixa = faixa_da_mandibula(masks, grade, cru)
    if acc is None or faixa is None:
        return 0.0
    topo, fim, _nome = faixa
    eixo, sinal = grade.eixo_sinal("sup")
    idx = np.arange(acc.shape[eixo])
    dentro = (idx <= topo) if sinal > 0 else (idx >= topo)
    if fim is not None:
        dentro &= (idx >= fim) if sinal > 0 else (idx <= fim)
    forma = [1] * acc.ndim
    forma[eixo] = -1
    return _cm3_da_mascara(acc & dentro.reshape(forma), grade)


FAIXA_DA_BORDA_MM = 10.0
FAIXA_DA_BORDA_CORTES = 2
VOLUME_MAXIMO_NA_BORDA_CM3 = 300.0
FRACAO_DA_PODA = 0.05
VOLUME_DA_PODA_CM3 = 10.0

GRANDES = {
    "lung_left": u"pulmao, 1.000 a 3.000 cm3",
    "lung_right": u"pulmao, 1.000 a 3.000 cm3",
    "liver": u"figado, 1.200 a 1.800 cm3",
    "brain": u"encefalo, 1.100 a 1.400 cm3",
    "skull": u"cranio, 500 a 800 cm3 de osso",
    "heart": u"coracao do modelo, 500 a 800 cm3",
    "pericardium": u"pericardio da trunk_cavities (contem o coracao), 600 a "
                   u"900 cm3",
    "stomach": u"estomago com o conteudo, 300 a 1.000 cm3",
    "colon": u"colon, 500 a 1.000 cm3",
    "small_bowel": u"delgado, 800 a 1.500 cm3",
    "gluteus_maximus_left": u"gluteo maximo, 500 a 900 cm3",
    "gluteus_maximus_right": u"gluteo maximo, 500 a 900 cm3",
    "gluteus_medius_left": u"gluteo medio, 300 a 450 cm3",
    "gluteus_medius_right": u"gluteo medio, 300 a 450 cm3",
    "femur_left": u"femur, 400 a 600 cm3 inteiro",
    "femur_right": u"femur, 400 a 600 cm3 inteiro",
    "hip_left": u"osso do quadril, 250 a 400 cm3",
    "hip_right": u"osso do quadril, 250 a 400 cm3",
    "thoracic_cavity": u"cavidade toracica da trunk_cavities, milhares de cm3",
    "abdominal_cavity": u"cavidade abdominal da trunk_cavities, milhares de "
                        u"cm3",
    "mediastinum": u"mediastino da trunk_cavities, 500 a 1.000 cm3",
}

PODA = {
    "lung_left": u"pulmao: uma peca por lado",
    "lung_right": u"pulmao: uma peca por lado",
    "liver": u"figado: uma peca",
    "brain": u"encefalo: uma peca",
    "heart": u"coracao do modelo: uma peca",
    "pericardium": u"pericardio: um saco",
    "kidney_left": u"rim: uma peca (o cisto e rotulo proprio)",
    "kidney_right": u"rim: uma peca (o cisto e rotulo proprio)",
    "stomach": u"estomago: uma peca",
    "gallbladder": u"vesicula: uma peca",
    "prostate": u"prostata: uma peca",
    "femur_left": u"femur: um osso",
    "femur_right": u"femur: um osso",
    "hip_left": u"osso do quadril: um osso",
    "hip_right": u"osso do quadril: um osso",
    "sacrum": u"sacro: um osso",
    "gluteus_maximus_left": u"musculo: uma peca",
    "gluteus_maximus_right": u"musculo: uma peca",
    "gluteus_medius_left": u"musculo: uma peca",
    "gluteus_medius_right": u"musculo: uma peca",
    "gluteus_minimus_left": u"musculo: uma peca",
    "gluteus_minimus_right": u"musculo: uma peca",
    "iliopsoas_left": u"musculo: uma peca",
    "iliopsoas_right": u"musculo: uma peca",
}

ORGAOS_POR_PARTES = ("lung_left", "lung_right")

def _mesmo_motivo(motivo, *nomes):
    return dict((n, motivo) for n in nomes)


NUNCA_PODA_PALAVRAS = {}
NUNCA_PODA_PALAVRAS.update(_mesmo_motivo(
    u"vaso: o contorno se parte em segmentos que sao o vaso",
    "artery", "arteries", "vein", "veins", "vena", "aorta", "carotid",
    "carotids", "jugular", "vessels", "sinuses"))
NUNCA_PODA_PALAVRAS.update(_mesmo_motivo(
    u"achado ou nodulo: mais de uma lesao e o normal, e a pequena conta",
    "nodule", "nodules", "effusion", "lesion", "lesions", "tumor", "tumors",
    "cyst", "cysts", "mass", "cancer", "metastasis"))
NUNCA_PODA_PALAVRAS.update(_mesmo_motivo(
    u"cabeca e pescoco: estrutura pequena, a ilha pode ser a propria",
    "eye", "eyeball", "lens", "optic", "chiasm", "pituitary", "hypophysis",
    "cochlea", "auditory", "mastoid", "parotid", "submandibular",
    "sublingual", "thyroid", "cricoid", "hyoid", "arytenoid", "epiglottis",
    "glottis", "larynx", "nasopharynx", "oropharynx", "hypopharynx",
    "palate", "constrictor", "pterygoid", "masseter", "temporalis",
    "digastric", "styloid", "zygomatic", "sinus", "nasal", "tongue",
    "mandible"))
NUNCA_PODA_PALAVRAS.update(_mesmo_motivo(
    u"dentes: cada dente e uma peca", "teeth", "tooth"))
NUNCA_PODA_PALAVRAS.update(_mesmo_motivo(
    u"abdome e pelve: estrutura pequena ou tubo fino",
    "adrenal", "ureter", "ureters", "urethra"))
NUNCA_PODA_PALAVRAS.update(_mesmo_motivo(
    u"vias aereas: a arvore bronquica se parte no corte espesso",
    "bronchus", "bronchi", "bronchia"))
NUNCA_PODA_PREFIXOS = {
    "rib_": u"costela: cada uma e uma peca, e fina",
    "ribs_": u"costelas de um lado: doze pecas por definicao",
    "vertebrae_": u"vertebra: e a coluna, peca a peca",
    "costal_cartilage": u"cartilagens costais: vinte pecas numa mascara",
    "lnl": u"niveis cervicais: compartimentos, e a uniao deles",
    "lvl_": u"niveis cervicais: compartimentos, e a uniao deles",
    "lung_vessels": u"vasos do pulmao: milhares de segmentos",
    "lung_trachea": u"traqueia e bronquios: a arvore se parte",
    "great_arteries": u"composto de vaso",
    "great_veins": u"composto de vaso",
    "brachiocephalic_": u"vaso",
    "subclavian_": u"vaso",
    "iliac_": u"vaso",
    "portal_vein": u"vaso",
    "pulmonary_": u"vaso",
    "venous_sinus": u"vaso",
    "kidney_cyst": u"cisto renal: mais de um e o normal",
}


def _formas_de_gravacao(nome):
    try:
        fs = list(_nomes.formas(nome))
        remover = set()
        for f in fs:
            cr = _nomes.crus_de(f)
            if len(cr) > 1:
                remover.update(cr)
        fs = [f for i, f in enumerate(fs) if i == 0 or f not in remover]
    except Exception:
        fs = [str(nome)]
    return tuple(str(f).lower() for f in fs if f)


def _na_lista(tabela, nome):
    for f in _formas_de_gravacao(nome):
        if f in tabela:
            return tabela[f]
    return None


def _vasos_do_motor_para_poda():
    fora = set(k.lower() for k in MARGEM_OAR_MM if k != "trachea")
    try:
        import radai_constructs as _rc
        fora.update(str(k).lower() for k in _rc.compostos_de_vaso())
    except Exception:
        pass
    return fora


def nunca_poda(nome):
    formas = _formas_de_gravacao(nome)
    vasos = _vasos_do_motor_para_poda()
    achados = set(str(k).lower() for k in (ROTULOS_DE_ACHADO or ()))
    for f in formas:
        if f in vasos:
            return u"vaso da tabela de margens (`MARGEM_OAR_MM`)"
        if f in achados:
            return u"rotulo de achado (`ROTULOS_DE_ACHADO`)"
        for p in sorted(NUNCA_PODA_PREFIXOS):
            if f.startswith(p):
                return u"%s (`%s`)" % (NUNCA_PODA_PREFIXOS[p], p)
        for palavra in f.split("_"):
            if palavra in NUNCA_PODA_PALAVRAS:
                return u"%s (`%s`)" % (NUNCA_PODA_PALAVRAS[palavra], palavra)
    return None


def classe_de_poda(nome):
    m = nunca_poda(nome)
    if m:
        return "nunca", m
    m = _na_lista(PODA, nome)
    if m:
        return "poda", m
    return "revisao", u"nem em PODA nem em NUNCA_PODA"


def faixa_da_borda(grade):
    eixo = grade.eixo_sinal("sup")[0]
    esp = float(grade.spacing[eixo])
    cortes = int(math.ceil(FAIXA_DA_BORDA_MM / esp - 1e-9)) if esp > 0 else 0
    return eixo, max(cortes, int(FAIXA_DA_BORDA_CORTES))


def _registrar_regra(rel, regra, nome, cm3, inteira, motivo, log):
    rel["removidas"].append({"regra": regra, "nome": str(nome),
                             "cm3": round(float(cm3), 2),
                             "inteira": bool(inteira), "motivo": motivo})
    if inteira:
        rel["saiu"][str(nome)] = u"%s (%s)" % (regra, motivo)
    if log:
        try:
            log(u"%s: `%s` %s (%.2f cm3) — %s"
                % (regra, nome, u"saiu" if inteira else u"perdeu pedacos",
                   cm3, motivo))
        except Exception:
            pass


def _partes_de_orgao_presentes(masks):
    fora = {}
    for orgao in ORGAOS_POR_PARTES:
        for p in COMPOSTOS.get(orgao, ()):
            try:
                k = _nomes.achar(masks, p)
            except Exception:
                k = p if p in masks else None
            if k is None or str(k).startswith("_") or k in fora:
                continue
            fora[k] = orgao
    return fora


def _pendente_de_volta(pend):
    cx, sub, _mudou, forma = pend
    novo = np.zeros(forma, bool)
    novo[cx] = sub
    return novo


def _regras_no_orgao(orgao, partes, pendentes, grade, rel, eixo, n_faixa,
                     vox_cm3, log=None):
    from scipy import ndimage
    import radai_geom
    forma = pendentes[partes[0]][3]
    ini = [min(pendentes[k][0][i].start for k in partes) for i in range(3)]
    fim = [max(pendentes[k][0][i].stop for k in partes) for i in range(3)]
    caixa = tuple(slice(a, b) for a, b in zip(ini, fim))
    tam = tuple(b - a for a, b in zip(ini, fim))
    locais = {}
    for k in partes:
        cx, sub = pendentes[k][0], pendentes[k][1]
        loc = np.zeros(tam, bool)
        loc[tuple(slice(s.start - a, s.stop - a)
                  for s, a in zip(cx, ini))] = sub
        locais[k] = loc
    uniao = np.logical_or.reduce([locais[k] for k in partes])
    lista = u", ".join(u"`%s`" % k for k in partes)
    mudou = set(k for k in partes if pendentes[k][2])
    saem = set()

    motivo_g = _na_lista(GRANDES, orgao)
    n_total = int(forma[eixo])
    if motivo_g is not None and uniao.any() and n_total > 2 * n_faixa:
        lim_u = radai_geom._limites(uniao)
        z0 = ini[eixo] + lim_u[eixo][0]
        z1 = ini[eixo] + lim_u[eixo][1]
        cm3_u = float(uniao.sum()) * vox_cm3
        baixa = z1 <= n_faixa - 1
        alta = z0 >= n_total - n_faixa
        if cm3_u < VOLUME_MAXIMO_NA_BORDA_CM3 and (baixa or alta):
            sinal = grade.eixo_sinal("sup")[1]
            borda = (u"cranial" if (alta and sinal > 0)
                     or (baixa and sinal < 0) else u"caudal")
            for k in partes:
                _registrar_regra(
                    rel, u"R1 borda do campo", k,
                    float(locais[k].sum()) * vox_cm3, True,
                    u"parte de `%s` (%s), e o orgao inteiro (%s) tem %.2f "
                    u"cm3, menos de %.0f, inteiro nos %d corte(s) da borda "
                    u"%s (faixa de %.0f mm ou %d cortes)"
                    % (orgao, motivo_g, lista, cm3_u,
                       VOLUME_MAXIMO_NA_BORDA_CM3, n_faixa, borda,
                       FAIXA_DA_BORDA_MM, FAIXA_DA_BORDA_CORTES), log)
            return dict((k, None) for k in partes)

    classe, motivo_p = classe_de_poda(orgao)
    if classe != "nunca":
        rot, n = ndimage.label(uniao, structure=np.ones((3, 3, 3), bool))
        if n >= 2:
            tam_c = np.bincount(rot.ravel(), minlength=n + 1)[1:]
            total = float(tam_c.sum())
            maior = int(tam_c.argmax())
            ilhas = [c + 1 for c in range(n)
                     if c != maior
                     and float(tam_c[c]) < FRACAO_DA_PODA * total
                     and float(tam_c[c]) * vox_cm3 < VOLUME_DA_PODA_CM3]
            if ilhas:
                em_ilha = np.isin(rot, ilhas)
                for k in partes:
                    perde = locais[k] & em_ilha
                    if not perde.any():
                        continue
                    cm3 = float(perde.sum()) * vox_cm3
                    n_k = len(np.unique(rot[perde]))
                    if classe == "poda":
                        resta = locais[k] & ~em_ilha
                        inteira = not resta.any()
                        _registrar_regra(
                            rel, u"R2 ilhas", k, cm3, inteira,
                            u"%d ilha(s) de `%s` (a uniao de %s) com menos "
                            u"de %.0f%% do volume dele e de %.0f cm3 cada (%s)"
                            % (n_k, orgao, lista, FRACAO_DA_PODA * 100,
                               VOLUME_DA_PODA_CM3, motivo_p), log)
                        locais[k] = resta
                        if inteira:
                            saem.add(k)
                        else:
                            mudou.add(k)
                    else:
                        rel["revisao"].append(
                            {"nome": str(k), "ilhas": n_k,
                             "cm3": round(cm3, 2)})
                        if log:
                            try:
                                log(u"R2 ilhas: `%s` tem %d ilha(s) de `%s`, "
                                    u"%.2f cm3 — ilha mantida para revisao"
                                    % (k, n_k, orgao, cm3))
                            except Exception:
                                pass

    fora = dict((k, None) for k in saem)
    for k in mudou - saem:
        novo = np.zeros(forma, bool)
        novo[caixa] = locais[k]
        fora[k] = novo
    return fora


def aplicar_regras_de_gravacao(masks, grade, externo=None, cru=None,
                               log=None):
    from scipy import ndimage
    import radai_geom
    rel = {"removidas": [], "revisao": [], "saiu": {}}
    if grade is None or masks is None:
        return rel
    vox_cm3 = float(grade.volume_voxel_mm3) / 1000.0
    eixo, n_faixa = faixa_da_borda(grade)
    ext = None
    if externo is not None:
        try:
            ext = np.asarray(externo, dtype=bool)
            if not ext.any():
                ext = None
        except Exception:
            ext = None
    cheia = np.ones((3, 3, 3), bool)

    def _tirar(nome):
        try:
            del masks[nome]
        except Exception:
            pass

    parte_de = _partes_de_orgao_presentes(masks)
    pendentes = {}

    for nome in list(masks):
        if str(nome).startswith("_"):
            continue
        try:
            m0 = masks[nome]
            if m0 is None:
                continue
            m = np.asarray(m0)
            if m.ndim != 3:
                continue
            mb = m if m.dtype == bool else m.astype(bool)
            lim = radai_geom._limites(mb)
            if lim is None:
                continue
            cx = tuple(slice(a, b + 1) for a, b in lim)
            sub = mb[cx]
            mudou = False

            if ext is not None and ext.shape == mb.shape:
                ext_cx = ext[cx]
                if (sub & ~ext_cx).any():
                    rot, n = ndimage.label(sub)
                    dentro = np.bincount(rot[ext_cx].ravel(), minlength=n + 1)
                    soltos = [i for i in range(1, n + 1) if dentro[i] == 0]
                    if soltos:
                        sai = np.isin(rot, soltos)
                        resto = sub & ~sai
                        cm3 = float(sai.sum()) * vox_cm3
                        if not resto.any():
                            _registrar_regra(
                                rel, u"R3 fora do corpo", nome, cm3, True,
                                u"inteira fora do contorno externo", log)
                            _tirar(nome)
                            continue
                        _registrar_regra(
                            rel, u"R3 fora do corpo", nome, cm3, False,
                            u"%d pedaco(s) inteiramente fora do contorno "
                            u"externo" % len(soltos), log)
                        sub, mudou = resto, True

            if nome in parte_de:
                pendentes[nome] = (cx, sub, mudou, mb.shape)
                continue

            motivo_g = _na_lista(GRANDES, nome)
            if motivo_g is not None:
                n_total = int(mb.shape[eixo])
                if n_total > 2 * n_faixa:
                    lim_s = radai_geom._limites(sub)
                    z0 = cx[eixo].start + lim_s[eixo][0]
                    z1 = cx[eixo].start + lim_s[eixo][1]
                    cm3 = float(sub.sum()) * vox_cm3
                    baixa = z1 <= n_faixa - 1
                    alta = z0 >= n_total - n_faixa
                    if cm3 < VOLUME_MAXIMO_NA_BORDA_CM3 and (baixa or alta):
                        sinal = grade.eixo_sinal("sup")[1]
                        borda = (u"cranial" if (alta and sinal > 0)
                                 or (baixa and sinal < 0) else u"caudal")
                        _registrar_regra(
                            rel, u"R1 borda do campo", nome, cm3, True,
                            u"grande (%s) com menos de %.0f cm3, inteira nos "
                            u"%d corte(s) da borda %s (faixa de %.0f mm ou %d "
                            u"cortes)" % (motivo_g, VOLUME_MAXIMO_NA_BORDA_CM3,
                                          n_faixa, borda, FAIXA_DA_BORDA_MM,
                                          FAIXA_DA_BORDA_CORTES), log)
                        _tirar(nome)
                        continue

            classe, motivo_p = classe_de_poda(nome)
            if classe != "nunca":
                rot, n = ndimage.label(sub, structure=cheia)
                if n >= 2:
                    tam = np.bincount(rot.ravel(), minlength=n + 1)[1:]
                    total = float(tam.sum())
                    maior = int(tam.argmax())
                    ilhas = [k + 1 for k in range(n)
                             if k != maior
                             and float(tam[k]) < FRACAO_DA_PODA * total
                             and float(tam[k]) * vox_cm3 < VOLUME_DA_PODA_CM3]
                    if ilhas:
                        cm3 = float(sum(int(tam[k - 1]) for k in ilhas)) \
                            * vox_cm3
                        if classe == "poda":
                            _registrar_regra(
                                rel, u"R2 ilhas", nome, cm3, False,
                                u"%d ilha(s) com menos de %.0f%% do volume e "
                                u"de %.0f cm3 cada (%s)"
                                % (len(ilhas), FRACAO_DA_PODA * 100,
                                   VOLUME_DA_PODA_CM3, motivo_p), log)
                            sub = sub & ~np.isin(rot, ilhas)
                            mudou = True
                        else:
                            rel["revisao"].append(
                                {"nome": str(nome), "ilhas": len(ilhas),
                                 "cm3": round(cm3, 2)})
                            if log:
                                try:
                                    log(u"R2 ilhas: `%s` tem %d ilha(s), "
                                        u"%.2f cm3 — ilha mantida para "
                                        u"revisao" % (nome, len(ilhas), cm3))
                                except Exception:
                                    pass

            if mudou:
                novo = np.zeros(mb.shape, bool)
                novo[cx] = sub
                masks[nome] = novo
        except Exception as e:
            if log:
                try:
                    log(u"regras de gravacao: `%s` nao foi julgada (%s: %s) — "
                        u"segue como veio" % (nome, type(e).__name__,
                                              str(e)[:100]))
                except Exception:
                    pass

    for orgao in ORGAOS_POR_PARTES:
        partes = [k for k in parte_de
                  if parte_de[k] == orgao and k in pendentes]
        if not partes:
            continue
        try:
            res = _regras_no_orgao(orgao, partes, pendentes, grade, rel,
                                   eixo, n_faixa, vox_cm3, log=log)
        except Exception as e:
            res = dict((k, _pendente_de_volta(pendentes[k])) for k in partes
                       if pendentes[k][2])
            if log:
                try:
                    log(u"regras de gravacao: `%s` nao foi julgado pela uniao "
                        u"das partes (%s: %s) — as partes seguem sem R1 e "
                        u"sem R2" % (orgao, type(e).__name__, str(e)[:100]))
                except Exception:
                    pass
        for k, novo in res.items():
            if novo is None:
                _tirar(k)
            else:
                masks[k] = novo

    _portoes_de_regiao(masks, grade, rel, cru=cru, log=log, tirar=_tirar)
    _so_revisao_do_que_ficou(rel, masks, log=log)
    return rel


def _so_revisao_do_que_ficou(rel, masks, log=None):
    try:
        saiu = rel.get("saiu") or {}
        fica, tirou = [], []
        for x in list(rel.get("revisao") or []):
            nome = str(x.get("nome"))
            try:
                presente = nome in masks
            except Exception:
                presente = True
            (fica if presente and nome not in saiu else tirou).append(x)
        rel["revisao"] = fica
        if log:
            for x in tirou:
                try:
                    log(u"R2 ilhas: `%s` saiu da lista de revisao — a "
                        u"estrutura saiu inteira (%s)"
                        % (x.get("nome"), saiu.get(str(x.get("nome")),
                                                   u"nao esta mais no FULL")))
                except Exception:
                    pass
    except Exception:
        pass


def _portoes_de_regiao(masks, grade, rel, cru=None, log=None, tirar=None):
    cm = _nomes.CHAVE_DO_CORACAO_DO_MODELO
    coracoes = [k for k in (cm, "heart") if k in masks]
    if coracoes:
        try:
            v_cor = _volume_cm3(masks, coracoes, grade)
            if v_cor < VOLUME_MINIMO_CORACAO_CM3:
                try:
                    import radai_skin
                    tem_t, pq_t = radai_skin.torax_identificado(
                        masks, grade, cru=cru)
                except Exception as e:
                    tem_t, pq_t = False, (u"nao consegui medir o torax (%s)"
                                          % type(e).__name__)
                if not tem_t:
                    motivo = (u"sem torax identificado (%s) e coracao do "
                              u"modelo com %.1f cm3, abaixo de %.0f"
                              % (pq_t, v_cor, VOLUME_MINIMO_CORACAO_CM3))
                    sai = list(coracoes)
                    p = _nomes.achar(masks, "pericardium")
                    if p is not None:
                        sai.append(p)
                    for k in sai:
                        cm3 = _cm3_da_mascara(masks[k], grade)
                        _registrar_regra(rel, u"R4 portao de regiao", k, cm3,
                                         True, motivo, log)
                        tirar(k)
        except Exception as e:
            if log:
                log(u"R4 (coracao): nao julgado (%s) — segue como veio"
                    % str(e)[:100])

    cabecas = [k for k in (_nomes.achar(masks, "skull"),
                           _nomes.achar(masks, "brain")) if k is not None]
    if cabecas:
        try:
            piso = dict((c, p) for c, _n, p in MARCOS_DE_REGIAO)[
                "cabeca_pescoco"]
            v_enc = _volume_cm3(masks, ("brain",), grade)
            if v_enc < piso:
                tem_p, laudo_p = pescoco_no_campo(masks, grade, cru=cru)
                if not tem_p:
                    motivo = (u"sem cabeca (encefalo com %.1f cm3, piso %.0f) "
                              u"e sem pescoco (%s)" % (v_enc, piso, laudo_p))
                    for k in cabecas:
                        cm3 = _cm3_da_mascara(masks[k], grade)
                        _registrar_regra(rel, u"R4 portao de regiao", k, cm3,
                                         True, motivo, log)
                        tirar(k)
        except Exception as e:
            if log:
                log(u"R4 (cranio e encefalo): nao julgado (%s) — segue como "
                    u"veio" % str(e)[:100])

    _portao_dos_orgaos_solidos(masks, grade, rel, cru=cru, log=log,
                               tirar=tirar)


ORGAOS_SOLIDOS_DO_TRONCO = {
    "liver": (("torax", "abdome", "pelve"), 100.0,
              u"figado, 1.200 a 1.800 cm3"),
    "spleen": (("torax", "abdome", "pelve"), 15.0, u"baco, 150 a 250 cm3"),
    "kidney_left": (("torax", "abdome", "pelve"), 15.0, u"rim, ~150 cm3"),
    "kidney_right": (("torax", "abdome", "pelve"), 15.0, u"rim, ~150 cm3"),
    "pancreas": (("torax", "abdome", "pelve"), 6.0,
                 u"pancreas, 60 a 100 cm3"),
}


def _regioes_do_tronco(masks, grade, cru=None):
    regioes, laudo = set(), []
    try:
        import radai_skin
        tem_t, pq_t = radai_skin.torax_identificado(masks, grade, cru=cru)
    except Exception as e:
        tem_t, pq_t = False, u"nao consegui medir (%s)" % type(e).__name__
    if not tem_t:
        v_p = _volume_cm3(masks, ("lung_left", "lung_right"), grade)
        # GUARDA: pulmao inteiro sem clavicula (4DCT, SBRT) tambem e tronco.
        if v_p >= VOLUME_MINIMO_PULMAO_CM3:
            tem_t, pq_t = True, u"pulmao com %.0f cm3" % v_p
    if tem_t:
        regioes.add("torax")
    laudo.append(u"torax: %s (%s)" % (u"sim" if tem_t else u"nao", pq_t))
    try:
        r, l = regioes_no_campo(masks, grade=grade)
        for cod in ("abdome", "pelve"):
            if cod in r:
                regioes.add(cod)
        laudo.extend(x for x in l if x.startswith((u"abdome", u"pelve")))
    except Exception as e:
        laudo.append(u"abdome e pelve: nao medidos (%s)" % type(e).__name__)
    return regioes, laudo


def _cabeca_ou_pescoco_no_campo(masks, grade, cru=None):
    try:
        piso = dict((c, p) for c, _n, p in MARCOS_DE_REGIAO)["cabeca_pescoco"]
        v_enc = _volume_cm3(masks, ("brain",), grade)
        if v_enc >= piso:
            return True, u"cabeca: encefalo com %.0f cm3" % v_enc
        tem_p, laudo_p = pescoco_no_campo(masks, grade, cru=cru)
        return bool(tem_p), laudo_p
    except Exception as e:
        return False, u"cabeca e pescoco: nao medidos (%s)" % type(e).__name__


def _na_faixa_caudal(m, grade):
    import numpy as np
    m = np.asarray(m, dtype=bool)
    eixo, n = faixa_da_borda(grade)
    outros = tuple(i for i in range(m.ndim) if i != eixo)
    cortes = np.flatnonzero(m.any(axis=outros))
    if not cortes.size:
        return False
    if grade.eixo_sinal("sup")[1] > 0:
        return int(cortes.min()) <= n - 1
    return int(cortes.max()) >= int(m.shape[eixo]) - n


def _o_torax_explica_o_orgao(masks, k, grade, cru=None):
    try:
        import radai_skin
        pulmao = radai_skin.uniao_por_nome(masks, radai_skin.PULMOES, cru=cru)
        if pulmao is None or not _na_faixa_caudal(pulmao, grade):
            return True, u"a base do pulmao esta no campo"
        if _na_faixa_caudal(masks[k], grade):
            return True, u"o orgao chega a borda caudal do campo"
        return False, (u"o pulmao chega a borda caudal do campo (so a parte "
                       u"de cima do torax) e o orgao nao chega a ela")
    except Exception as e:
        return True, u"nao consegui medir (%s)" % type(e).__name__


def _portao_dos_orgaos_solidos(masks, grade, rel, cru=None, log=None,
                               tirar=None):
    try:
        presentes = [(n, _nomes.achar(masks, n))
                     for n in ORGAOS_SOLIDOS_DO_TRONCO]
        presentes = [(n, k) for n, k in presentes if k is not None]
        if not presentes:
            return
        regioes, laudo = None, None
        cabeca = None
        for nome, k in presentes:
            legit, piso, tipico = ORGAOS_SOLIDOS_DO_TRONCO[nome]
            cm3 = _cm3_da_mascara(masks[k], grade)
            if cm3 >= piso:
                continue
            if cabeca is None:
                cabeca = _cabeca_ou_pescoco_no_campo(masks, grade, cru=cru)
            if not cabeca[0]:
                continue
            if regioes is None:
                regioes, laudo = _regioes_do_tronco(masks, grade, cru=cru)
                laudo = [cabeca[1]] + list(laudo)
            legit_aqui = set(legit) & regioes
            if legit_aqui - {"torax"}:
                continue
            if legit_aqui:
                explica, frase_t = _o_torax_explica_o_orgao(masks, k, grade,
                                                            cru=cru)
                if explica:
                    continue
                motivo = (u"orgao solido do tronco sem abdome nem pelve no "
                          u"campo, e o torax nao o explica (%s), %.2f cm3, "
                          u"abaixo de %.0f (%s; %s)"
                          % (frase_t, cm3, piso, tipico, u"; ".join(laudo)))
            else:
                motivo = (u"orgao solido do tronco sem torax, abdome nem "
                          u"pelve no campo, %.2f cm3, abaixo de %.0f (%s; %s)"
                          % (cm3, piso, tipico, u"; ".join(laudo)))
            _registrar_regra(rel, u"R4 portao de regiao", k, cm3, True,
                             motivo, log)
            tirar(k)
    except Exception as e:
        if log:
            log(u"R4 (orgao solido do tronco): nao julgado (%s) — segue como "
                u"veio" % str(e)[:100])


def aplicar_compostos(masks):
    for nome, partes in COMPOSTOS.items():
        if nome in masks:
            continue
        pedacos = [masks[p] for p in partes if p in masks]
        if not pedacos:
            continue
        m = pedacos[0] if len(pedacos) == 1 else np.logical_or.reduce(pedacos)
        if np.any(m):
            masks[nome] = m
    return masks


ROTULOS_DE_ACHADO = frozenset([
])

ORIGEM_DO_ACHADO = {}


class MascaraCompacta(object):

    __slots__ = ("_forma", "_caixa", "_sub", "_cheia", "__weakref__")

    def __init__(self, forma, caixa, sub):
        self._forma = tuple(int(n) for n in forma)
        self._caixa = caixa
        self._sub = sub
        self._cheia = None

    @classmethod
    def de(cls, m):
        if isinstance(m, MascaraCompacta):
            return m
        a = np.asarray(m)
        if a.dtype != bool:
            a = a.astype(bool)
        from scipy import ndimage
        caixas = ndimage.find_objects(a.view(np.uint8))
        caixa = caixas[0] if caixas else None
        sub = None if caixa is None else np.array(a[caixa], dtype=bool)
        return cls(a.shape, caixa, sub)

    @property
    def shape(self):
        return self._forma

    @property
    def dtype(self):
        return np.dtype(bool)

    @property
    def ndim(self):
        return len(self._forma)

    @property
    def size(self):
        n = 1
        for v in self._forma:
            n *= v
        return n

    @property
    def caixa(self):
        return self._caixa

    def cheia(self):
        if self._cheia is not None:
            return self._cheia
        a = np.zeros(self._forma, dtype=bool)
        if self._caixa is not None:
            a[self._caixa] = self._sub
        return a

    def _virar_cheia(self):
        if self._cheia is None:
            self._cheia = self.cheia()
            self._caixa = self._sub = None
        return self._cheia

    def __array__(self, dtype=None, copy=None):
        a = self.cheia()
        if dtype is not None and np.dtype(dtype) != a.dtype:
            return a.astype(dtype)
        return a

    def any(self, axis=None, **kw):
        if axis is None and not kw:
            if self._cheia is not None:
                return bool(self._cheia.any())
            return bool(self._sub is not None and self._sub.any())
        return self.cheia().any(axis=axis, **kw)

    def sum(self, axis=None, **kw):
        if axis is None and not kw:
            if self._cheia is not None:
                return self._cheia.sum()
            return (np.int64(0) if self._sub is None
                    else np.int64(np.count_nonzero(self._sub)))
        return self.cheia().sum(axis=axis, **kw)

    def copy(self):
        if self._cheia is not None:
            return self._cheia.copy()
        return self.cheia()

    def astype(self, dtype, *a, **kw):
        return self.cheia().astype(dtype, *a, **kw)

    def __getattr__(self, nome):
        # GUARDA: nada de dunder pelo atalho -- o __array_interface__ de uma
        # copia temporaria apontaria para memoria ja devolvida.
        if nome.startswith("__"):
            raise AttributeError(nome)
        return getattr(self.cheia(), nome)

    def __getitem__(self, k):
        return self.cheia()[k]

    def __setitem__(self, k, v):
        self._virar_cheia()[k] = v

    def __len__(self):
        return self._forma[0]

    def __iter__(self):
        return iter(self.cheia())

    def __bool__(self):
        return bool(self.cheia())

    __nonzero__ = __bool__

    def __or__(self, o):
        return self.cheia() | np.asarray(o)

    def __ror__(self, o):
        return np.asarray(o) | self.cheia()

    def __and__(self, o):
        return self.cheia() & np.asarray(o)

    def __rand__(self, o):
        return np.asarray(o) & self.cheia()

    def __xor__(self, o):
        return self.cheia() ^ np.asarray(o)

    def __rxor__(self, o):
        return np.asarray(o) ^ self.cheia()

    def __invert__(self):
        return ~self.cheia()

    def __eq__(self, o):
        return self.cheia() == (o if np.isscalar(o) else np.asarray(o))

    def __ne__(self, o):
        return self.cheia() != (o if np.isscalar(o) else np.asarray(o))

    __hash__ = None

    def __ior__(self, o):
        self._virar_cheia().__ior__(np.asarray(o, dtype=bool))
        return self

    def __iand__(self, o):
        self._virar_cheia().__iand__(np.asarray(o, dtype=bool))
        return self

    def __ixor__(self, o):
        self._virar_cheia().__ixor__(np.asarray(o, dtype=bool))
        return self

    def __repr__(self):
        return "MascaraCompacta(forma=%r, caixa=%r)" % (self._forma,
                                                       self._caixa)

    def bytes_guardados(self):
        if self._cheia is not None:
            return int(self._cheia.nbytes)
        return 0 if self._sub is None else int(self._sub.nbytes)


def _uniao_compacta(partes, forma):
    if any(p._cheia is not None for p in partes):
        a = np.zeros(forma, dtype=bool)
        for p in partes:
            a |= p.cheia()
        return MascaraCompacta.de(a)
    caixas = [p._caixa for p in partes if p._caixa is not None]
    if not caixas:
        return MascaraCompacta(forma, None, None)
    lim = tuple(slice(min(c[k].start for c in caixas),
                      max(c[k].stop for c in caixas))
                for k in range(len(forma)))
    sub = np.zeros(tuple(s_.stop - s_.start for s_ in lim), dtype=bool)
    for p in partes:
        if p._caixa is None:
            continue
        rel = tuple(slice(c.start - l.start, c.stop - l.start)
                    for c, l in zip(p._caixa, lim))
        sub[rel] |= p._sub
    return MascaraCompacta(forma, lim, sub)


def _grupos_da_task(task, idx_to_name):
    nome_para_idx = dict((nm, idx) for idx, nm in idx_to_name.items())
    _fam = _familia(task)
    grupos = []
    for amigavel, taskmap in TS_MAP.items():
        if amigavel in ROTULOS_DE_ACHADO:
            continue
        if _fam not in taskmap:
            continue
        idxs = [nome_para_idx[l] for l in taskmap[_fam] if l in nome_para_idx]
        if idxs:
            grupos.append((amigavel, idxs))
    return grupos


def masks_compactas_da_task(arr, task, idx_to_name):
    from scipy import ndimage
    grupos = _grupos_da_task(task, idx_to_name)
    if not grupos:
        return {}
    maior = int(arr.max()) if arr.size else 0
    tabela = np.zeros(max(maior, max(max(i) for _, i in grupos)) + 1,
                      dtype=np.int16)
    for g, (_, idxs) in enumerate(grupos, start=1):
        for i in idxs:
            tabela[i] = g
    por_grupo = tabela[arr]
    del tabela
    caixas = ndimage.find_objects(por_grupo, max_label=len(grupos))
    out = {}
    for g, (amigavel, _) in enumerate(grupos, start=1):
        cx = caixas[g - 1] if g - 1 < len(caixas) else None
        if cx is None:
            continue
        sub = por_grupo[cx] == g
        if sub.any():
            out[amigavel] = MascaraCompacta(arr.shape, cx, sub)
    del por_grupo
    for nome, partes in COMPOSTOS.items():
        if nome in out:
            continue
        pedacos = [out[p] for p in partes if p in out]
        if not pedacos:
            continue
        m = (pedacos[0] if len(pedacos) == 1
             else _uniao_compacta(pedacos, arr.shape))
        if m.any():
            out[nome] = m
    return out


def bytes_das_mascaras(masks):
    total = 0
    vistos = set()
    for v in (masks or {}).values():
        if id(v) in vistos:
            continue
        vistos.add(id(v))
        if isinstance(v, MascaraCompacta):
            total += v.bytes_guardados()
        else:
            try:
                total += int(np.asarray(v).nbytes)
            except Exception:
                pass
    return total


def masks_da_task(arr, task, idx_to_name):
    nome_para_idx = dict((nm, idx) for idx, nm in idx_to_name.items())
    _fam = _familia(task)
    grupos = []
    for amigavel, taskmap in TS_MAP.items():
        if amigavel in ROTULOS_DE_ACHADO:
            continue
        if _fam not in taskmap:
            continue
        idxs = [nome_para_idx[l] for l in taskmap[_fam] if l in nome_para_idx]
        if idxs:
            grupos.append((amigavel, idxs))
    if not grupos:
        return {}

    maior = int(arr.max()) if arr.size else 0
    tabela = np.zeros(max(maior, max(max(i) for _, i in grupos)) + 1, dtype=np.int16)
    for g, (_, idxs) in enumerate(grupos, start=1):
        for i in idxs:
            tabela[i] = g
    por_grupo = tabela[arr]
    del tabela

    out = {}
    for g, (amigavel, _) in enumerate(grupos, start=1):
        m = (por_grupo == g)
        if m.any():
            out[amigavel] = m
    return aplicar_compostos(out)


GRUPOS_DISJUNTOS = {
    "lobos_pulmonares": [
        "lung_upper_lobe_left", "lung_lower_lobe_left",
        "lung_upper_lobe_right", "lung_middle_lobe_right",
        "lung_lower_lobe_right",
        "pleural_effusion_left", "pleural_effusion_right",
    ],
    "cardiomediastinal": [
        "heart", "heart_model", "pericardium", "trachea",
        "esophagus",
          
         "brachiocephalic_trunk",
        "brachiocephalic_vein_left", "brachiocephalic_vein_right",
         
         
        "lung_vessels", "lung_trachea_bronchia",
    ],
    "esqueleto_toracico": (
        ["rib_left_%d" % i for i in range(1, 13)]
        + ["rib_right_%d" % i for i in range(1, 13)]
        + ["vertebrae_%s%d" % (r, i) for r, n in (("T", 12), ("C", 7), ("L", 5))
           for i in range(1, n + 1)]
        + ["vertebrae_S1", "vertebrae_L6", "sternum", "costal_cartilages"]
    ),
    "visceras_altas": [
        "liver", "spleen", "stomach", "gallbladder", "pancreas",
        "kidney_left", "kidney_right", "adrenal_gland_left",
        "adrenal_gland_right", "duodenum",
        "kidney_cyst_left", "kidney_cyst_right",
    ],
}


CONTIDAS_EM = {
    "eye_lens_left": "eye_left",
    "eye_lens_right": "eye_right",
}


def aplicar_contencao(masks, grade=None, log=None):
    import numpy as np
    ajustes = []
    for dentro, fora in CONTIDAS_EM.items():
        dentro = _nomes.achar(masks, dentro) or dentro
        fora = _nomes.achar(masks, fora) or fora
        if dentro not in masks or fora not in masks:
            continue
        d = np.asarray(masks[dentro])
        d = d if d.dtype == bool else d.astype(bool)
        f = np.asarray(masks[fora])
        f = f if f.dtype == bool else f.astype(bool)
        if not (d.any() and f.any()):
            continue
        sobra = int((d & ~f).sum())
        if not sobra:
            continue
        novo = d & f
        if not novo.any():
            if log:
                log("`%s` ficaria VAZIO dentro de `%s` — nao recortei. Isso "
                    "quase sempre quer dizer que `%s` e que esta errado."
                    % (dentro, fora, fora))
            continue
        masks[dentro] = novo
        vox = (float(np.prod(grade.spacing)) / 1000.0) if grade is not None else 0.0
        ajustes.append((dentro, fora, sobra, sobra * vox))
        if log:
            log("`%s` recortado para dentro de `%s`: %d voxel(s)%s estavam fora"
                % (dentro, fora, sobra,
                   (" (%.2f cm3)" % (sobra * vox)) if vox else ""))
    return ajustes


DESCONTADAS_DE = {
    "kidney_cyst_left": "kidney_left",
    "kidney_cyst_right": "kidney_right",
}


def aplicar_desconto(masks, grade=None, log=None):
    import numpy as np
    ajustes = []
    for dentro, fora in DESCONTADAS_DE.items():
        dentro = _nomes.achar(masks, dentro) or dentro
        fora = _nomes.achar(masks, fora) or fora
        if dentro not in masks or fora not in masks:
            continue
        d = np.asarray(masks[dentro])
        d = d if d.dtype == bool else d.astype(bool)
        f = np.asarray(masks[fora])
        f = f if f.dtype == bool else f.astype(bool)
        if not (d.any() and f.any()):
            continue
        comum = int((d & f).sum())
        if not comum:
            continue
        novo = f & ~d
        if not novo.any():
            if log:
                log("`%s` ficaria VAZIO ao descontar `%s` — nao descontei. "
                    "Rim inteiro rotulado como cisto e policistico ou erro do "
                    "modelo, e nos dois entregar rim nenhum e pior."
                    % (fora, dentro))
            continue
        masks[fora] = novo
        vox = (float(np.prod(grade.spacing)) / 1000.0) if grade is not None else 0.0
        ajustes.append((fora, dentro, comum, comum * vox))
        if log:
            log("`%s` descontado de `%s`: %d voxel(s)%s eram da lesao"
                % (fora, dentro, comum,
                   (" (%.2f cm3)" % (comum * vox)) if vox else ""))
    return ajustes


def _grupo_disjunto_da_serie(masks, nomes):
    import numpy as np
    presentes = [n for n in nomes if n in masks and _bool_seguro(masks[n]).any()]
    if len(presentes) < 2:
        return {}, []
    presentes.sort(key=lambda n: int(_bool_seguro(masks[n]).sum()))
    grupo, tomado, ajustes = {}, None, []
    for n in presentes:
        m = _bool_seguro(masks[n]).copy()
        if tomado is None:
            tomado = m.copy()
        else:
            conflito = int((m & tomado).sum())
            if conflito:
                m = m & ~tomado
                ajustes.append((n, conflito))
            tomado |= m
        if m.any():
            grupo[n] = m
    return grupo, ajustes


def _bool_seguro(m):
    import numpy as np
    a = np.asarray(m)
    return a if a.dtype == bool else a.astype(bool)


def _compostos_no_lugar_das_partes(masks, nomes, excluir=()):
    grupo = set(nomes)
    fora = []
    for comp, partes in COMPOSTOS.items():
        if comp in excluir or comp not in masks or comp in grupo:
            continue
        if not partes or any(p in masks for p in partes):
            continue
        if set(partes) <= grupo:
            fora.append(comp)
    return fora


def suavizar_em_grupos(masks, grade, mm, log=None, detalhe=None,
                       descontou=False, excluir=None, compostos_inteiros=False):
    if grade is None or not mm or float(mm) <= 0:
        return set()
    import radai_geom
    feitas = set()
    _subtraidas = set(DESCONTADAS_DE) if not descontou else set()
    _excluir = set(excluir or ())
    for rotulo, nomes in sorted(GRUPOS_DISJUNTOS.items()):
        try:
            nomes = [n for n in nomes
                     if n not in _subtraidas and n not in _excluir]
            if compostos_inteiros:
                nomes = nomes + _compostos_no_lugar_das_partes(
                    masks, nomes, _excluir)
            grupo, ajustes = _grupo_disjunto_da_serie(masks, nomes)
            if len(grupo) < 2:
                continue
            porcada = dict((k, suavizacao_de(str(k).split(":")[-1], mm))
                           for k in grupo)
            cortadas = []
            _ks = list(porcada)
            _raios = dict(zip(_ks, _em_paralelo(
                lambda _k: estrutura_fina(grupo[_k], grade), _ks)))
            for k in list(porcada):
                _fina, _r = _raios[k]
                if _fina:
                    cortadas.append((str(k), porcada[k], 0.0))
                    porcada[k] = 0.0
                    continue
                t = teto_de_suavizacao(grupo[k], grade, raio=_r)
                if t is not None and t < porcada[k]:
                    cortadas.append((str(k), porcada[k], t))
                    porcada[k] = t
            juntos = radai_geom.suavizar_conjunto(grupo, porcada, grade)
            if detalhe is not None:
                for k in juntos:
                    try:
                        a_m = _bool_seguro(grupo[k])
                        d_m = _bool_seguro(juntos[k])
                        a_n = int(a_m.sum())
                        detalhe.append(
                            (str(k), float(porcada.get(k, 0.0)), a_n,
                             int(d_m.sum()),
                             (int((a_m & d_m).sum()) / float(a_n))
                             if a_n else 1.0))
                    except Exception:
                        pass
            masks.update(juntos)
            feitas |= set(juntos)
            if log:
                log("fronteira compartilhada em `%s`: %d estrutura(s)"
                    % (rotulo, len(juntos)))
                if cortadas:
                    piores = sorted(cortadas, key=lambda x: x[1] - x[2])[-3:]
                    log("   suavizacao limitada pela espessura em %d "
                        "estrutura(s): %s" % (len(cortadas), ", ".join(
                            "%s %.1f->%.1f mm" % (n, a, b_)
                            for n, a, b_ in reversed(piores))))
                for nome, quantos in sorted(ajustes, key=lambda x: -x[1])[:3]:
                    log("   %s cedeu %d voxel(s) que estavam em duas "
                        "estruturas" % (nome, quantos))
        except Exception as exc:
            if log:
                log("grupo `%s` seguiu com suavizacao individual (%s)"
                    % (rotulo, str(exc)[:110]))
    return feitas


def recompor_compostos(masks, log=None, criar=False, subtrair=None, so=None,
                       exceto=None, inteiros=False):
    import numpy as np
    refeitos = []
    subtrair = set(subtrair or ())
    for comp, partes in COMPOSTOS.items():
        if so is not None and comp not in so:
            continue
        if exceto is not None and comp in exceto:
            continue
        if comp not in masks and not criar:
            continue
        tem = [p for p in partes if p in masks]
        if not tem and inteiros and comp in masks:
            _tira = [c for c in COMPOSTOS_MENOS.get(comp, ())
                     if c in subtrair and c in masks]
            if _tira:
                u = _bool_seguro(masks[comp]).copy()
                for c in _tira:
                    u &= ~_bool_seguro(masks[c])
                if u.any():
                    masks[comp] = u
                    if log:
                        log("composto inteiro `%s` sem o que %s ocupa"
                            % (comp, ", ".join(_tira)))
                else:
                    try:
                        del masks[comp]
                    except Exception:
                        pass
            continue
        if not tem:
            continue
        u = _bool_seguro(masks[tem[0]]).copy()
        for p in tem[1:]:
            u |= _bool_seguro(masks[p])
        for c in COMPOSTOS_MENOS.get(comp, ()):
            if c in subtrair and c in masks:
                u &= ~_bool_seguro(masks[c])
        if u.any():
            masks[comp] = u
            refeitos.append(comp)
        elif comp in masks and COMPOSTOS_MENOS.get(comp):
            try:
                del masks[comp]
            except Exception:
                pass
    if log and refeitos:
        log("compostos refeitos a partir das partes suavizadas: %s"
            % ", ".join(sorted(refeitos)))
    return refeitos


def suavizar_masks(masks, jid=None):
    if jid:
        _log(jid, "suavizacao: aplicada na montagem do RTSTRUCT, por "
                  "estrutura (Taubin 2D no contorno + gaussiana na mascara, "
                  "sigma da tabela `SUAVIZACAO`)")
    return masks

MIN_SLICES = 20
RUNNER_TS = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "radai_ts_runner.py")
TS_CMD = [sys.executable, RUNNER_TS]
TS_CMD_DIRETO = [sys.executable, "-m", "totalsegmentator.bin.TotalSegmentator"]


TS_CONFIG_ARQUIVO = "config.json"
_ESTATISTICA_DITA = {"erro": u""}


def pasta_config_do_ts(amb=None):
    amb = os.environ if amb is None else amb
    p = str(amb.get("TOTALSEG_HOME_DIR") or "").strip()
    if p:
        return p
    casa = os.path.expanduser("~")
    return os.path.join("/tmp" if casa == "/" else casa, ".totalsegmentator")


def estatistica_do_ts(desligar=False, amb=None, pasta=None):
    import json
    import random
    import string
    pasta = pasta or pasta_config_do_ts(amb)
    arq = os.path.join(pasta, TS_CONFIG_ARQUIVO)
    r = {"arquivo": arq, "existia": os.path.isfile(arq), "valor": None,
         "gravou": False, "criou": False, "erro": u""}
    cfg = None
    if r["existia"]:
        try:
            with open(arq, encoding="utf-8-sig") as f:
                cfg = json.load(f)
            if not isinstance(cfg, dict):
                raise ValueError(u"o conteudo nao e um objeto JSON")
            v = cfg.get("send_usage_stats")
            r["valor"] = None if v is None else bool(v)
        except Exception as e:
            r["erro"] = u"nao consegui ler %s (%s: %s)" % (
                arq, type(e).__name__, str(e)[:120])
            return r
    if not desligar or r["valor"] is False:
        return r
    if cfg is None:
        cfg = {"totalseg_id": "totalseg_" + "".join(
                   random.Random().choices(string.ascii_uppercase
                                           + string.digits, k=8)),
               "send_usage_stats": False, "prediction_counter": 0,
               "statistics_disclaimer_shown": True}
        r["criou"] = True
    else:
        cfg["send_usage_stats"] = False
    rascunho = arq + ".radai_%d_%d_%s.tmp" % (
        os.getpid(), threading.get_ident(), uuid.uuid4().hex[:8])
    try:
        if not os.path.isdir(pasta):
            os.makedirs(pasta)
        with open(rascunho, "w", encoding="ascii") as f:
            json.dump(cfg, f, indent=4)
        os.replace(rascunho, arq)
        r["gravou"] = True
        r["valor"] = False
    except Exception as e:
        r["erro"] = u"nao consegui gravar %s (%s: %s)" % (
            arq, type(e).__name__, str(e)[:120])
        try:
            if os.path.exists(rascunho):
                os.remove(rascunho)
        except OSError as e2:
            r["erro"] += u"; e o rascunho ficou (%s)" % type(e2).__name__
    return r


def envelope_bloqueia_estatistica():
    if RUNNER_TS not in TS_CMD:
        return False, u"o motor nao chama o envelope (TS_CMD sem o radai_ts_runner.py)"
    if not os.path.isfile(RUNNER_TS):
        return False, u"o envelope radai_ts_runner.py nao esta ao lado do motor"
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "_radai_ts_runner_conferido", RUNNER_TS)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    except Exception as e:
        return False, u"o envelope nao carregou (%s: %s)" % (
            type(e).__name__, str(e)[:100])
    if not callable(getattr(mod, "remendar_estatistica", None)):
        return False, u"o envelope desta versao nao tem o remendo da estatistica"
    return True, u""


def _e_o_totalsegmentator(cmd):
    partes = [str(x) for x in (cmd or [])]
    if RUNNER_TS in partes and os.path.isfile(RUNNER_TS):
        return True
    return "totalsegmentator.bin.TotalSegmentator" in partes


def _desligar_estatistica_antes(cmd, amb, jid, task):
    if not _e_o_totalsegmentator(cmd):
        return None
    r = estatistica_do_ts(desligar=True, amb=amb)
    if r.get("gravou"):
        _log(jid, "TS %s: estatistica de uso do TotalSegmentator desligada "
                  "no arquivo dele (send_usage_stats=false em %s%s) — "
                  "nenhuma chamada de rede" % (
                      task, r.get("arquivo"),
                      u", arquivo criado agora" if r.get("criou") else u""))
    elif r.get("erro") and r["erro"] != _ESTATISTICA_DITA.get("erro"):
        _ESTATISTICA_DITA["erro"] = r["erro"]
        _log(jid, "  ! TS %s: %s — o envelope continua bloqueando o envio, "
                  "mas sem ele (o recuo pelo `-m`) o TotalSegmentator "
                  "enviaria a estatistica de uso" % (task, r["erro"]))
    return r

class Cancelado(RuntimeError):
    pass


class TaskTravada(RuntimeError):

    def __init__(self, task, motivo, numeros=None, tentativa=1, frase=None,
                 onde=None):
        self.task = task
        self.motivo = motivo
        self.numeros = dict(numeros or {})
        self.tentativa = int(tentativa or 1)
        self.onde = onde
        if frase is None:
            frase = _frase_da_trava(motivo, self.numeros)
        if self.tentativa >= 2:
            msg = (u"TS %s TRAVADA duas vezes (%s) -- a segunda com o plano "
                   u"de memoria menor -- e foi encerrada: %s"
                   % (task, _NOME_DA_TRAVA.get(motivo, motivo), frase))
        else:
            msg = (u"TS %s TRAVADA (%s)%s e foi encerrada: %s"
                   % (task, _NOME_DA_TRAVA.get(motivo, motivo),
                      (u" em %s" % onde) if onde else u"", frase))
        RuntimeError.__init__(self, msg)


_JOBS = {}
_LOCK = threading.Lock()

def _job_new():
    jid = uuid.uuid4().hex[:12]
    with _LOCK:
        _JOBS[jid] = {"status": "queued", "log": [], "started": time.time(),
                      "elapsed": 0, "rt": "", "error": ""}
    return jid
def _job(jid):
    with _LOCK:
        return dict(_JOBS.get(jid, {}))
def _set(jid, **kw):
    with _LOCK:
        if jid in _JOBS: _JOBS[jid].update(kw)


def _inteiro_ou_nulo(v):
    try:
        n = int(v)
    except (TypeError, ValueError):
        return None
    return n if n > 0 else None


def frase_do_pico(pico):
    pico = pico or {}
    c, w = pico.get("commit_mb"), pico.get("ws_mb")
    if c is None and w is None:
        return u"pico de memoria do processo da task: nao medido"
    return (u"pico de memoria do processo da task: %s GiB de commit, %s GiB "
            u"de memoria fisica" % (_gib(c) if c is not None else u"?",
                                    _gib(w) if w is not None else u"?"))


def _anotar_no_job(jid, task, plano=None, recorte=None, partes=None,
                   recuo_cpu=None, travamento=None, clip=None, ausente=None,
                   cache=None, pico=None):
    try:
        with _LOCK:
            j = _JOBS.get(jid)
            if j is None:
                return
            if plano is not None:
                j.setdefault("planos", {})[task] = dict(plano)
                if not j.get("plano"):
                    j["plano"] = dict(plano, task=task)
            if recuo_cpu is not None:
                alvos = [j.setdefault("planos", {}).setdefault(task, {})]
                if (j.get("plano") or {}).get("task") == task:
                    alvos.append(j["plano"])
                for p in alvos:
                    if "modo_do_plano" not in p:
                        p["modo_do_plano"] = p.get("modo")
                    p["modo"] = "cpu"
                    p["recuo_cpu"] = dict(recuo_cpu)
                    p["motivo"] = (
                        u"%s | a placa caiu em %s: a task foi refeita INTEIRA "
                        u"em CPU" % (p.get("motivo") or u"",
                                     recuo_cpu.get("onde") or u"?"))
            if recorte is not None:
                j.setdefault("recorte_no_corpo", {})[task] = dict(recorte)
            if partes:
                j.setdefault("partes", []).extend(dict(p) for p in partes)
            if travamento is not None:
                j.setdefault("travamentos", []).append(
                    dict(travamento, task=task))
            if clip is not None:
                j.setdefault("recortes", {})[task] = dict(clip)
            if ausente is not None:
                j.setdefault("ausentes", {})[task] = u"%s" % ausente
            if cache is not None:
                j.setdefault("cache", {})[task] = dict(cache)
            if pico is not None:
                j.setdefault("picos", {})[task] = dict(pico)
    except Exception:
        pass
PROGRESSO_A_CADA_S = 120


class FiltroProgresso(object):

    def __init__(self, a_cada_s=None):
        self.a_cada_s = PROGRESSO_A_CADA_S if a_cada_s is None else a_cada_s
        self.ultimo = 0.0

    def passa(self, texto, agora=None):
        t = str(texto)
        if "still working" not in t and "rodando..." not in t:
            return True
        agora = time.time() if agora is None else agora
        if self.ultimo and agora - self.ultimo < self.a_cada_s:
            return False
        self.ultimo = agora
        return True


def drenar_log(jid, escrever, parar, a_cada_s=None, intervalo=3.0):
    mostradas = 0
    filtro = FiltroProgresso(a_cada_s)

    def _uma_volta(ja):
        try:
            linhas = (_job(jid) or {}).get("log") or []
            for ln in linhas[ja:]:
                if filtro.passa(ln):
                    try:
                        escrever(str(ln))
                    except Exception:
                        pass
            return max(ja, len(linhas))
        except Exception:
            return ja

    while not parar.is_set():
        mostradas = _uma_volta(mostradas)
        parar.wait(intervalo)
    _uma_volta(mostradas)


def _log(jid, msg):
    ts = time.strftime("%H:%M:%S")
    with _LOCK:
        if jid in _JOBS:
            _JOBS[jid]["log"].append("[%s] %s" % (ts, msg))
            _JOBS[jid]["elapsed"] = int(time.time() - _JOBS[jid]["started"])
def _job_del(jid):
    with _LOCK:
        _JOBS.pop(jid, None)

def sort_dcm(files):
    t = []
    for f in files:
        # GUARDA: corte sem preambulo (comeca na tag) so e lido com force.
        try: z = float(pydicom.dcmread(f, stop_before_pixels=True, force=True).ImagePositionPatient[2])
        except Exception: z = 0.0
        t.append((z, f))
    t.sort(key=lambda x: x[0]); return [f for _, f in t]


def _tem_preambulo_dicom(caminho):
    try:
        with open(str(caminho), "rb") as f:
            return f.read(132)[128:132] == b"DICM"
    except OSError:
        return False


def _sintaxe_lida(ds):
    from pydicom.uid import (ImplicitVRLittleEndian, ExplicitVRLittleEndian,
                             ExplicitVRBigEndian)
    meta = getattr(ds, "file_meta", None)
    ts = getattr(meta, "TransferSyntaxUID", None) if meta is not None else None
    if ts:
        return ts
    implicito, little = getattr(ds, "original_encoding", (True, True))
    if implicito:
        return ImplicitVRLittleEndian
    return ExplicitVRLittleEndian if little else ExplicitVRBigEndian


def copiar_como_parte_10(origem, destino):
    if _tem_preambulo_dicom(origem):
        shutil.copy(str(origem), str(destino))
        return False
    from pydicom.dataset import FileMetaDataset
    ds = pydicom.dcmread(str(origem), force=True)
    ts = _sintaxe_lida(ds)
    meta = getattr(ds, "file_meta", None) or FileMetaDataset()
    if not isinstance(meta, FileMetaDataset):
        meta = FileMetaDataset(meta)
    meta.MediaStorageSOPClassUID = ds.SOPClassUID
    meta.MediaStorageSOPInstanceUID = ds.SOPInstanceUID
    meta.TransferSyntaxUID = ts
    ds.file_meta = meta
    ds.preamble = b"\0" * 128
    ds.save_as(str(destino), enforce_file_format=True)
    return True


def copy_sorted(files, dest):
    dest = Path(dest); dest.mkdir(parents=True, exist_ok=True)
    for i, f in enumerate(sort_dcm(files)):
        # GUARDA: o rt_utils le sem force e descarta calado o corte sem preambulo.
        copiar_como_parte_10(f, dest / ("slice_%04d.dcm" % i))

TILT_MAX_MM = 2.0


def _conferir_inclinacao(pasta, arquivos):
    _bruto = (os.environ.get("RADAI_ACEITA_TILT_MM") or "").strip()
    teto = TILT_MAX_MM
    if _bruto:
        try:
            teto = float(_bruto.replace(",", "."))
        except Exception:
            print("[motor] RADAI_ACEITA_TILT_MM=%r nao e um numero; "
                  "usando %.2f mm" % (_bruto, TILT_MAX_MM))
            teto = TILT_MAX_MM
    try:
        import radai_dicom
        arqs = [{"caminho": str(c)} for c in arquivos]
        graus, desvio, _decl = radai_dicom.inclinacao_de_gantry(arqs)
    except Exception:
        return
    if graus <= radai_dicom.TOLERANCIA_TILT_GRAUS or desvio <= teto:
        return
    raise RuntimeError(
        "gantry inclinado em %.1f graus: do primeiro ao ultimo corte ha %.1f mm "
        "de desvio, e o volume seria empilhado como se nao houvesse inclinacao. "
        "O contorno sairia deslocado e plausivel. Para processar mesmo assim, "
        "defina RADAI_ACEITA_TILT_MM acima de %.1f." % (graus, desvio, desvio))


_PREFIXO_LONGO = "\\\\?\\"

_TETO_DO_CAMINHO_PLANO = 259


def _sem_prefixo_longo(caminho):
    c = str(caminho)
    if c.startswith("\\\\?\\UNC\\"):
        return "\\\\" + c[8:]
    if c.startswith(_PREFIXO_LONGO):
        return c[4:]
    return c


def _componentes_intactos(caminho):
    partes = [x for x in str(caminho).replace("/", "\\").split("\\") if x]
    return all(x == x.rstrip(". ") for x in partes if x not in (".", ".."))


def _pasta_para_o_gdcm(d):
    p = str(d)
    if not p.startswith(_PREFIXO_LONGO):
        return p
    plana = _sem_prefixo_longo(p)
    try:
        nomes = os.listdir(p)
        maior = max([len(n) for n in nomes] or [0])
        if (_componentes_intactos(plana)
                and len(plana) + 1 + maior <= _TETO_DO_CAMINHO_PLANO
                and os.path.isdir(plana) and os.path.samefile(p, plana)):
            return plana
    except Exception:
        pass
    return None


def _load_sitk_por_copia(d, uid=None):
    p = str(d)
    arquivos = []
    try:
        nomes = sorted(os.listdir(p))
    except OSError:
        raise ValueError("Sem DICOM em %s" % d)
    for nome in nomes:
        fp = os.path.join(p, nome)
        if not os.path.isfile(fp):
            continue
        if uid:
            try:
                ds = pydicom.dcmread(fp, stop_before_pixels=True, force=True,
                                     specific_tags=["SeriesInstanceUID"])
                if str(getattr(ds, "SeriesInstanceUID", "") or "") != str(uid):
                    continue
            except Exception:
                continue
        arquivos.append(fp)
    if not arquivos:
        raise ValueError("Sem DICOM em %s" % d)
    stage = tempfile.mkdtemp(prefix="radai_longo_")
    try:
        copy_sorted(arquivos, stage)
        return load_sitk(stage, uid)
    finally:
        shutil.rmtree(stage, ignore_errors=True)


CORTES_MINIMOS_CONTORNAVEIS = 2
COS_MINIMO_AXIAL = 0.95


def _e_rm(modalidade):
    return str(modalidade or "").strip().upper() in ("MR", "MRI", "RM")


def modalidade_da_task(task):
    try:
        import radai_tasks as _rt
        d = _rt.POR_NOME.get(task) or {}
        if d.get("modalidade"):
            return str(d["modalidade"]).upper()
    except Exception:
        pass
    return "MR" if str(task or "").endswith("_mr") else "CT"


def conferir_volume_contornavel(img, min_cortes=None, modalidade=None):
    minimo = int(min_cortes or CORTES_MINIMOS_CONTORNAVEIS)
    try:
        dim = int(img.GetDimension())
    except Exception:
        dim = None
    if dim != 3:
        raise SerieNaoContornavel(
            u"o volume nao e 3D (dimensao %s): nao e uma serie de contorno"
            % dim,
            tela=u"O volume não é 3D (dimensão %s): não é uma série de "
                 u"contorno." % dim)
    if int(img.GetNumberOfComponentsPerPixel()) != 1:
        _comp = int(img.GetNumberOfComponentsPerPixel())
        raise SerieNaoContornavel(
            u"a serie e uma imagem colorida (%d componentes por pixel) — "
            u"captura de tela ou laudo —, e nao uma TC/RM de contorno"
            % _comp,
            tela=u"A série é uma imagem colorida (%s componentes por pixel) — "
                 u"captura de tela ou laudo —, e não uma TC/RM de contorno."
                 % _comp)
    n = int(img.GetSize()[2])
    if n < minimo:
        raise SerieNaoContornavel(
            u"a serie tem %d corte(s), e o contorno pede pelo menos %d"
            % (n, minimo),
            tela=u"A série tem %s corte(s), e o contorno pede pelo menos %s."
                 % (n, minimo))
    if any(float(e) <= 0 for e in img.GetSpacing()):
        _esp = (tuple(round(float(e), 3) for e in img.GetSpacing()),)
        raise SerieNaoContornavel(
            u"o espacamento do volume e nulo (%s): a geometria nao se le"
            % _esp,
            tela=u"O espaçamento do volume é nulo (%s): a geometria não se "
                 u"lê." % _esp)
    d = [float(v) for v in img.GetDirection()]
    # GUARDA: na RM qualquer orientacao e segmentada; na TC so o axial.
    if _e_rm(modalidade):
        return
    if len(d) == 9 and abs(d[8]) < COS_MINIMO_AXIAL:
        _graus = math.degrees(math.acos(max(-1.0, min(1.0, abs(d[8])))))
        raise SerieNaoContornavel(
            u"reconstrucao sagital/coronal (a normal do corte faz %.0f graus "
            u"com o eixo z): o contorno nao casaria com o plano axial do TPS"
            % _graus,
            tela=u"Reconstrução sagital/coronal (a normal do corte faz %s graus "
                 u"com o eixo z): o contorno não casaria com o plano axial do "
                 u"TPS." % (u"%.0f" % _graus))


def load_sitk(d, uid=None):
    pasta = _pasta_para_o_gdcm(d)
    if pasta is None:
        return _load_sitk_por_copia(d, uid)
    r = sitk.ImageSeriesReader()
    if uid:
        n = r.GetGDCMSeriesFileNames(pasta, str(uid))
    else:
        n = r.GetGDCMSeriesFileNames(pasta)
    if not n: raise ValueError("Sem DICOM em %s" % d)
    _conferir_inclinacao(d, n)
    r.SetFileNames(n); return r.Execute()

def resample(mi, ri):
    r = sitk.ResampleImageFilter()
    r.SetReferenceImage(ri); r.SetInterpolator(sitk.sitkNearestNeighbor)
    r.SetDefaultPixelValue(0); r.SetOutputSpacing(ri.GetSpacing())
    r.SetOutputOrigin(ri.GetOrigin()); r.SetOutputDirection(ri.GetDirection())
    r.SetSize(ri.GetSize()); return r.Execute(mi)

def smooth_mask_2d(mask, is_lung=False):
    s = 3.0 if is_lung else 2.0
    out = np.zeros_like(mask, dtype=np.bool_)
    for z in range(mask.shape[0]):
        slc = mask[z].astype(np.float32)
        if not np.any(slc): continue
        up = ndzoom(slc, 3, order=1)
        up_s = gaussian_filter(up, sigma=s * 3) > 0.35
        out[z] = ndzoom(up_s.astype(np.float32), 1.0 / 3, order=1) > 0.5
    return out

def ingest_zip(zip_path):
    tmp = Path(tempfile.mkdtemp(prefix="radai_"))
    ex = tmp / "ex"; ex.mkdir()
    with zipfile.ZipFile(zip_path, "r") as z: z.extractall(ex)
    skip = {".zip", ".txt", ".xml", ".pdf", ".html", ".png", ".jpg", ".md", ".log"}
    files = []
    for r, _, fs in os.walk(str(ex)):
        for f in fs:
            if Path(f).suffix.lower() in skip: continue
            p = str(Path(r) / f)
            try:
                ds = pydicom.dcmread(p, stop_before_pixels=True, force=True)
                if hasattr(ds, "ImagePositionPatient") or hasattr(ds, "PixelData"):
                    files.append(p)
            except Exception: continue
    if not files: raise ValueError("Nenhum DICOM encontrado no zip.")
    clean = tmp / "clean"
    copy_sorted(files, clean)
    return str(clean), str(tmp)

TIMEOUT_TASK_S = int(os.environ.get("RADAI_TS_TIMEOUT_S", "10800"))

TRAVA_SEM_PULSO_MIN = 15
TRAVA_PAGINANDO_MIN = 30
TRAVA_RAM_PCT = 95

MEMORIA_A_CADA_S = 10


def trava_efetiva(trava=None):
    padrao = {"sem_pulso_min": float(TRAVA_SEM_PULSO_MIN),
              "paginando_min": float(TRAVA_PAGINANDO_MIN),
              "ram_pct": float(TRAVA_RAM_PCT)}
    out = dict(padrao)
    for k in padrao:
        try:
            v = float(str((trava or {}).get(k)).replace(",", "."))
        except (TypeError, ValueError):
            continue
        if v > 0 and v == v:
            out[k] = min(v, 100.0) if k == "ram_pct" else v
    return out


_NOME_DA_TRAVA = {"sem_pulso": u"sem pulso", "paginando": u"paginando"}


def _frase_da_trava(motivo, n):
    n = n or {}
    try:
        if motivo == "sem_pulso":
            if n.get("pulsos"):
                return (u"sem pulso do envelope ha %s (limite %s; %d pulso(s) "
                        u"antes de calar)"
                        % (_duracao(n.get("sem_pulso_s") or 0),
                           _duracao(n.get("limite_s") or 0),
                           int(n.get("pulsos") or 0)))
            return (u"sem pulso do envelope ha %s desde o inicio (limite %s): "
                    u"o processo nunca deu sinal de vida"
                    % (_duracao(n.get("sem_pulso_s") or 0),
                       _duracao(n.get("limite_s") or 0)))
        if motivo == "paginando":
            pf = n.get("pf_no_periodo")
            return (u"sem progresso ha %s com a memoria da estacao em %s%% "
                    u"(>= %s%% ha %s; limite %s)%s"
                    % (_duracao(n.get("sem_progresso_s") or 0),
                       _pct(n.get("ram_pct")), _pct(n.get("ram_limite")),
                       _duracao(n.get("ram_alta_s") or 0),
                       _duracao(n.get("limite_s") or 0),
                       (u"; o processo teve %s falhas de pagina no periodo"
                        % pf) if pf is not None else u""))
    except Exception:
        pass
    return u"%s %s" % (motivo, n)


def _pct(v):
    try:
        f = float(v)
        return (u"%d" % f) if f == int(f) else (u"%.1f" % f)
    except (TypeError, ValueError):
        return u"?"


def _tail_arquivo(caminho, n=800):
    try:
        with open(str(caminho), "rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - max(n * 20, 16384)))
            txt = f.read().decode("utf-8", "replace")
        linhas = [l for l in txt.replace("\r", "\n").split("\n")
                  if "RADAI|pulso|" not in l]
        txt = "\n".join(linhas).strip()
        return txt[-n:].strip().replace("\r", " ")
    except Exception:
        return "(sem log)"


LINHAS_DO_FIM_DO_LOG = 12

MOTIVO_DO_LOCALIZADOR_VAZIO = (u"o localizador da task nao achou a regiao "
                               u"dela no campo")
MOTIVO_SEM_ESTRUTURA = u"a task rodou e nao achou estrutura no campo"


class SemEstrutura(dict):

    def __init__(self, ausencia=MOTIVO_SEM_ESTRUTURA):
        dict.__init__(self)
        self.ausencia = ausencia


def _localizador_vazio(log_ts, desde):
    try:
        with open(str(log_ts), "rb") as f:
            f.seek(max(0, int(desde or 0)))
            return _RECORTE_VAZIO in f.read().decode("utf-8", "replace")
    except Exception:
        return False


def _ausencia(jid, task, localizador_vazio=False):
    motivo = (MOTIVO_DO_LOCALIZADOR_VAZIO if localizador_vazio
              else MOTIVO_SEM_ESTRUTURA)
    _log(jid, u"TS %s: nenhuma estrutura no campo — ausencia anatomica, nao "
              u"falha (%s)" % (task, motivo))
    _anotar_no_job(jid, task, ausente=motivo)
    return SemEstrutura(motivo)


def _falha_da_task(task, log_ts, desde, jid, codigo=None, frase=None,
                   tempo_limite=False):
    prim = primeira_excecao(str(log_ts), desde=desde)
    ult = ultima_excecao(str(log_ts), desde=desde)
    cauda = _tail_arquivo(log_ts)
    for linha in [l for l in cauda.splitlines() if l.strip()][
            -LINHAS_DO_FIM_DO_LOG:]:
        _log(jid, u"  TS %s (fim do log): %s" % (task, linha.strip()[:200]))
    return FalhaDaTask(task, codigo=codigo, primeira=prim, ultima=ult,
                       frase=frase, cauda=u"" if prim else cauda,
                       tempo_limite=tempo_limite, volume_conferido=True)


class MasksCruas(object):

    def __init__(self, arr, idx_to_name):
        self._arr = arr
        presentes = set(int(v) for v in np.unique(arr)) - {0}
        self._nomes = dict((idx_to_name[i], i) for i in sorted(presentes)
                           if i in idx_to_name
                           and idx_to_name[i] not in ROTULOS_DE_ACHADO)

    def __len__(self):
        return len(self._nomes)

    def __iter__(self):
        return iter(self._nomes)

    def keys(self):
        return self._nomes.keys()

    def __contains__(self, k):
        return k in self._nomes

    def __getitem__(self, k):
        return self._arr == self._nomes[k]


TASKS_PERMITIDAS = {
    "total_v3": u"os 117 orgaos, ossos, musculos e vasos — o fluxo principal",
    "total_v2": u"a mesma anatomia, pelo modelo de 2023 — rede de seguranca",
    "head_glands_cavities": u"glandulas e cavidades de cabeca e pescoco",
    "headneck_muscles": u"musculatura de cabeca e pescoco",
    "headneck_bones_vessels": u"laringe, cartilagem tireoide e cricoide, hioide, carotida interna e jugular interna",
    "head_muscles": u"masseter, temporal, pterigoideos, lingua e digastrico — os OAR de TRISMO",
    "oculomotor_muscles": u"retos, obliquos e levantador da palpebra, mais globos, "
                          u"nervos opticos e cranio — a orbita que a `total` nao tem",
    "vertebrae_body": u"o CORPO vertebral (sem os elementos posteriores) e os "
                      u"discos intervertebrais — dois rotulos, e o primeiro e "
                      u"OAR de metastase ossea",
    "lung_vessels": u"arvore vascular e bronquica do pulmao — no 2.15 ela "
                    u"entrega QUATRO rotulos (vias aereas, parede das vias, "
                    u"arterias e veias)",
    "lung_vessels_LEGACY": u"a arvore classica, com os dois rotulos de sempre",
    "trunk_cavities": u"pericardio, mediastino e as cavidades toracica e abdominal",
    "breasts": u"as mamas — OAR e alvo ao mesmo tempo num servico de RT",
    "craniofacial_structures": u"mandibula, dentes, cranio e os seios da face",
    "total_mr": u"corpo inteiro em RM (50 estruturas) — a base da RM",
    "hip_implant": u"protese de quadril — material de alta densidade que o "
                   u"calculo de dose precisa conhecer",

    "abdominal_muscles": u"reto abdominal, obliquos, eretor da espinha, "
                         u"quadrado lombar, psoas maior, serratil, grande "
                         u"dorsal, peitoral maior e trapezio — a parede do "
                         u"tronco, que nenhuma outra task do pacote entrega",
    "liver_segments": u"os oito segmentos hepaticos de Couinaud — a unidade "
                      u"de reserva funcional em SBRT de figado",
    "vertebrae_mr": u"vertebras C1-L5 em RM — o que a `total_mr` nao nomeia, "
                    u"e o que a fusao de RM de coluna precisa",
    "liver_segments_mr": u"os oito segmentos hepaticos de Couinaud em RM — "
                         u"a mesma unidade da TC, para a RM de figado fundida",
    "teeth": u"os 32 dentes com numeracao FDI, as polpas, os canais "
             u"alveolares e o trabalho dentario instalado",


    "lung_nodules": u"nodulos pulmonares — ACHADO",
    "pleural_pericard_effusion": u"derrame pleural e pericardico — anatomia "
                                 u"do torax, so no FULL (no OAR o Heart_ai "
                                 u"integra o pericardico e os pulmoes saem "
                                 u"sem o pleural)",
    "liver_lesions": u"lesoes hepaticas — ACHADO (exige contraste)",
    "liver_lesions_mr": u"lesoes hepaticas em RM — ACHADO",
}


TASKS_DE_ACHADO = frozenset([
    "lung_nodules",
    # GUARDA: o derrame e anatomia do torax (vai so ao FULL; no OAR e no
    # OAR_Fast entra pelo Heart_ai e pelos pulmoes); nao e achado e roda no
    # FAST e no AUTO quando ha torax.
    "liver_lesions",
    "liver_lesions_mr",
])

TASKS_FORA_DE_ESCOPO = {
    "cerebral_bleed": u"escopo — ela varre o volume e devolve onde esta o "
                      u"sangramento intracerebral. E radiologia diagnostica, "
                      u"nao estrutura de planejamento de radioterapia: nao ha "
                      u"dose a prescrever nem orgao a poupar num hematoma. "
                      u"Eram 326 MB no pacote (Dataset150).",
    "body": u"escopo — ela devolve o CONTORNO EXTERNO, que este aplicativo "
            u"calcula por conta propria (`radai_skin.contorno_externo`) e usa "
            u"como insumo interno da pele e da parede toracica. Ele nunca vai "
            u"para RTSTRUCT nenhum, e `conferir_sem_body` recusa o arquivo se "
            u"alguem tentar. Rodar a task nao acrescentaria nada e produziria "
            u"uma estrutura que o gravador barra.",
    "face": u"escopo — ela marca a regiao da face para ANONIMIZACAO, que nao e "
            u"contorno para plano.",
    "face_mr": u"escopo — a mesma, em RM.",
}

TASKS_RECUSADAS = TASKS_FORA_DE_ESCOPO


def tasks_do_motor():
    try:
        from totalsegmentator.map_to_binary import class_map
        nomes = set(class_map.keys())
        return nomes or None
    except Exception:
        return None


def conferir_tasks_existem(tasks):
    conhecidas = tasks_do_motor()
    if not conhecidas:
        return
    fora = [t for t in (tasks or [])
            if t and _nome_biblioteca(t) not in conhecidas]
    if not fora:
        return
    raise ValueError(
        u"task que este TotalSegmentator nao conhece: %s. Ela pode estar "
        u"certa pela regra clinica e ainda assim nao existir nesta versao do "
        u"pacote — `trunk_cavities`, por exemplo, so aparece depois da 2.4.0. "
        u"Rodar assim derruba toda serie da fila, uma tentativa por vez. "
        u"Tire-a do TASKS, ou prepare um pacote com a versao que a tem."
        % ", ".join(sorted(set(fora))))


def conferir_tasks(tasks):
    fora = [t for t in (tasks or []) if t and t not in TASKS_PERMITIDAS]
    if not fora:
        return
    partes = []
    for t in fora:
        if "," in t or ";" in t:
            partes.append(
                u"`%s`: parece DUAS ou mais tasks grudadas por um separador. "
                u"No `radai_watcher.config`, separe com espaco: `TASKS=%s`"
                % (t, " ".join(x for x in t.replace(";", ",").split(",") if x)))
            continue
        porque = TASKS_RECUSADAS.get(
            t, u"nao esta na lista de tasks validadas neste aplicativo")
        partes.append(u"`%s`: %s" % (t, porque))
    raise ValueError(
        u"task nao permitida no TASKS: " + u" | ".join(partes)
        + u" — permitidas: " + u", ".join(sorted(TASKS_PERMITIDAS)))


def _task_que_roda(task, log=None):
    if task not in _bases_preferidas():
        return task
    try:
        import radai_tasks
        modal = radai_tasks.modalidade_da_base(
            radai_tasks.APELIDOS.get(task, task))
    except Exception as e:
        modal = "MR" if str(task).endswith("_mr") else "CT"
        if log:
            log(u"! TS %s: nao consegui perguntar a modalidade da base a "
                u"radai_tasks (%s: %s) — deduzida pelo nome: %s"
                % (task, type(e).__name__, str(e)[:120], modal))
    if not modal:
        return task
    eleita = base_eleita(modal, log=log)
    return eleita or task


def _dispositivo_pedido_e_placa(device):
    d = str(device or "").strip().lower()
    return d.startswith("gpu") or d.startswith("cuda") or d in ("auto", "")


_DEGRAU_MENOR = {"gpu": "gpu_resultado_na_cpu",
                 "gpu_resultado_na_cpu": "cpu",
                 "cpu": "cpu"}


def _plano_um_degrau_abaixo(plano):
    orig = (plano or {}).get("modo") or "cpu"
    novo = _DEGRAU_MENOR.get(orig, "cpu")
    p = dict(plano or {})
    p.update(modo=novo, modo_do_plano=orig, plano_menor=True)
    p["motivo"] = (u"%s | PLANO MENOR (retomada de task travada): %s -> %s"
                   % (p.get("motivo") or u"", orig, novo))
    if novo == "cpu":
        p["indice"] = None
    return p



SAIDA_PARADA_S = 60

SILENCIO_AVISO_S = 600

BATIMENTO_TS_S = PROGRESSO_A_CADA_S + 5

_ERROS_DE_PLACA = (
    "cuda out of memory",
    "outofmemoryerror",
    "cuda error",
    "cudaerror",
    "device-side assert",
    "cudnn_status_",
    "cublas_status_",
)


def _erro_de_placa(texto):
    for linha in str(texto or "").replace("\r", "\n").splitlines():
        b = linha.lower()
        if any(m in b for m in _ERROS_DE_PLACA):
            return linha.strip()[:200]
        if "driver" in b and "reset" in b:
            return linha.strip()[:200]
    return None


def _saida_inteira(caminho, ref):
    import gzip
    c = str(caminho)
    try:
        if c.endswith(".gz"):
            with gzip.open(c, "rb") as fh:
                while fh.read(8 * 1024 * 1024):
                    pass
    except Exception as e:
        return False, u"o gzip nao le ate o fim (%s)" % type(e).__name__
    try:
        img = sitk.ReadImage(c)
    except Exception as e:
        return False, u"o SimpleITK nao abre (%s)" % str(e)[:80]
    try:
        tam, esperado = tuple(img.GetSize()), tuple(ref.GetSize())
    except Exception as e:
        return False, u"nao consegui ler a grade (%s)" % type(e).__name__
    if tam != esperado:
        return False, u"grade %s, a serie e %s" % (tam, esperado)
    return True, u"abre inteiro, grade %s" % (tam,)


def _texto_do_console(b):
    if not b:
        return u""
    if not isinstance(b, bytes):
        return str(b)
    for cod in ("oem", "utf-8"):
        try:
            return b.decode(cod, "replace")
        except LookupError:
            continue
    return b.decode("latin-1", "replace")


_TASKKILL_NAO_ACHOU = 128


def _encerrar_arvore(proc):
    import subprocess
    if proc.poll() is not None:
        return None
    problemas = []
    if os.name == "nt":
        raiz = os.environ.get("SystemRoot")
        tk = os.path.join(raiz, "System32", "taskkill.exe") if raiz else ""
        try:
            r = subprocess.run([tk if tk and os.path.isfile(tk) else "taskkill",
                                "/PID", str(proc.pid), "/T", "/F"],
                               capture_output=True, timeout=30)
            if r.returncode not in (0, _TASKKILL_NAO_ACHOU):
                ult = [x for x in (_texto_do_console(r.stderr) + u"\n"
                                   + _texto_do_console(r.stdout))
                       .strip().splitlines() if x.strip()]
                problemas.append(
                    u"taskkill /T saiu com codigo %s (%s) — os processos "
                    u"filhos do nnU-Net podem ter ficado vivos"
                    % (r.returncode, (ult[-1].strip() if ult else u"")[:120]))
        except Exception as e:
            problemas.append(
                u"taskkill /T nao rodou (%s: %s) — os processos filhos do "
                u"nnU-Net podem ter ficado vivos"
                % (type(e).__name__, str(e)[:120]))
    try:
        proc.kill()
    except Exception as e:
        if proc.poll() is None:
            problemas.append(u"kill do processo falhou (%s: %s)"
                             % (type(e).__name__, str(e)[:120]))
    try:
        proc.wait(timeout=30)
    except Exception as e:
        problemas.append(u"o processo nao saiu 30 s depois do kill (%s)"
                         % type(e).__name__)
    return u"; ".join(problemas) or None


def _encerrar_arvore_e_dizer(proc, jid, task):
    problema = _encerrar_arvore(proc)
    if problema:
        _log(jid, "  ! TS %s: ao encerrar o processo: %s" % (task, problema))
    return problema


_MARCA_DO_ENVELOPE = b"RADAI|"


def _texto_antes_do_pulso(b):
    i = b.find(_MARCA_DO_ENVELOPE)
    if i >= 0:
        return b[:i]
    for n in range(min(len(b), len(_MARCA_DO_ENVELOPE) - 1), 0, -1):
        if b.endswith(_MARCA_DO_ENVELOPE[:n]):
            return b[:-n]
    return b


class _LeitorDoLogTS(object):

    _PARTE = re.compile(r"Predicting part (\d+) of (\d+)")

    def __init__(self, caminho, offset=0, agora=None):
        self.caminho = str(caminho)
        self.offset = int(offset or 0)
        self.resto = b""
        self.parte = None
        self.dataset = None
        self.recorte = None
        self.dataset_do_recorte = None
        self.rede_unica = False
        self.etapas = []
        self.pulso = {}
        self._assinatura = None
        self.t_sinal = time.time() if agora is None else agora
        self.t_pulso = None
        self.pulsos = 0
        self.t_progresso = self.t_sinal
        self.desceu_para_ram = False
        self.sem_placa = False
        self.fim = None
        self.pico = None
        self.executor = {}
        self.eventos = []
        self.erro = None
        self._disse_erro = False

    def ler(self, agora=None):
        agora = time.time() if agora is None else agora
        try:
            with open(self.caminho, "rb") as fh:
                fh.seek(self.offset)
                novo = fh.read()
        except Exception as e:
            self.erro = u"%s: %s" % (type(e).__name__, str(e)[:120])
            if not self._disse_erro:
                self._disse_erro = True
                self.eventos.append(
                    u"! nao consegui ler o log do TotalSegmentator (%s) — o "
                    u"batimento fica sem a parte e sem o pulso ate a leitura "
                    u"voltar, e um «sem sinal» que vier depois pode ser ISTO, "
                    u"e nao a task parada" % self.erro)
            return
        if self.erro is not None:
            self.erro = None
            self._disse_erro = False
            self.eventos.append(u"a leitura do log do TotalSegmentator voltou")
        if not novo:
            return
        self.offset += len(novo)
        bruto = self.resto + novo
        partes = re.split(rb"[\r\n]", bruto)
        self.resto = partes.pop() if partes else b""
        for b in partes:
            if not b.strip():
                continue
            t = b.decode("utf-8", "replace").strip()
            i = t.find("RADAI|")
            if i > 0:
                self._saida_ts(t[:i].strip(), agora)
                t = t[i:]
            if t.startswith("RADAI|"):
                self._radai(t, agora)
                continue
            self._saida_ts(t, agora)
        if self.resto.strip():
            self.t_sinal = agora
            if _texto_antes_do_pulso(self.resto).strip():
                self.t_progresso = agora

    def _abrir_etapa(self, tipo, agora, parte=None, dataset=None):
        self._fechar_etapa(agora)
        self.etapas.append({"tipo": tipo, "parte": parte, "dataset": dataset,
                            "inicio": agora, "fim": None})
        if tipo == "rede":
            self.rede_unica = True

    def _etapa_aberta(self):
        return bool(self.etapas) and self.etapas[-1]["fim"] is None

    def dataset_da_task(self):
        if self.dataset and self.dataset != self.dataset_do_recorte:
            return self.dataset
        return None

    def onde(self, task):
        if self.recorte == "rodando":
            return u"recorte do corpo (6 mm)"
        if self.parte:
            nome = _nome_da_parte(task, self.parte, self.dataset)
            return u"parte %d/%d%s" % (self.parte[0], self.parte[1],
                                       (u" (%s)" % nome) if nome else u"")
        if self.recorte == "feito" and not self.rede_unica:
            return u"recorte do corpo pronto"
        ds = self.dataset_da_task()
        if ds:
            nome = _nome_da_parte(task, None, ds)
            return u"rede %s%s" % (ds, (u" (%s)" % nome) if nome else u"")
        if self.rede_unica:
            return u"rede unica"
        return None

    def _fechar_etapa(self, agora):
        if self.etapas and self.etapas[-1]["fim"] is None:
            self.etapas[-1]["fim"] = agora

    def fechar(self, agora=None):
        agora = time.time() if agora is None else agora
        if self.etapas and self.etapas[-1]["fim"] is None:
            self.etapas[-1]["fim"] = agora
            self.etapas[-1]["incompleta"] = True

    def _saida_ts(self, t, agora):
        if not t:
            return
        self.t_sinal = agora
        self.t_progresso = agora
        if _INICIO_DO_RECORTE in t:
            self.recorte = "rodando"
            self._abrir_etapa("recorte", agora)
        elif self.recorte == "rodando" and (_FIM_DO_RECORTE in t
                                            or _CORTOU_A_SERIE in t):
            self.recorte = "feito"
            self._fechar_etapa(agora)
        m = self._PARTE.search(t)
        if m:
            if self.recorte == "rodando":
                self.recorte = "feito"
            self.parte = (int(m.group(1)), int(m.group(2)))
            self._abrir_etapa("parte", agora, parte=self.parte)
        elif t.startswith(_REDE_UNICA) and self.recorte != "rodando" \
                and not self.parte:
            self._abrir_etapa("rede", agora)
        elif "Predicted in" in t and self.recorte != "rodando":
            self._fechar_etapa(agora)
        if "Moving results arrays to CPU" in t:
            self.desceu_para_ram = True
        if "No GPU detected" in t:
            self.sem_placa = True

    def _radai(self, t, agora):
        campos = t.split("|")
        tipo = campos[1] if len(campos) > 1 else ""
        kv = {}
        for c in campos[2:]:
            if "=" in c:
                k, v = c.split("=", 1)
                kv[k.strip()] = v.strip()
        if tipo == "pulso":
            assin = (kv.get("rss_mb"), kv.get("vram_mb"), kv.get("dataset"))
            if assin != self._assinatura:
                self._assinatura = assin
                self.t_sinal = agora
            self.t_pulso = agora
            self.pulsos += 1
            self.pulso = kv
            if kv.get("dataset"):
                self.dataset = kv["dataset"]
        elif tipo == "rede":
            self.dataset = kv.get("dataset") or self.dataset
            self.t_sinal = agora
            self.t_progresso = agora
            if self.recorte == "rodando" and kv.get("dataset"):
                self.dataset_do_recorte = kv.get("dataset")
            if self._etapa_aberta() and not self.etapas[-1]["dataset"]:
                self.etapas[-1]["dataset"] = kv.get("dataset")
            elif (self.recorte == "feito" and not self.parte
                  and not self._etapa_aberta()):
                self._abrir_etapa("rede", agora, dataset=kv.get("dataset"))
            self.eventos.append(u"rede carregada: dataset %s em %s, "
                                u"resultado na %s%s"
                                % (kv.get("dataset", "?"),
                                   kv.get("device", "?"),
                                   kv.get("resultados", "?"),
                                   u" (o recorte do corpo, antes das partes)"
                                   if self.recorte == "rodando" else u""))
        elif tipo == "pico":
            self.pico = {"commit_mb": _inteiro_ou_nulo(kv.get("commit_mb")),
                         "ws_mb": _inteiro_ou_nulo(kv.get("ws_mb"))}
        elif tipo == "fim":
            self.t_progresso = agora
            try:
                self.fim = int(kv.get("codigo"))
            except (TypeError, ValueError):
                self.fim = kv.get("codigo")
        elif tipo == "executor":
            self.t_sinal = agora
            self.t_progresso = agora
            ds = kv.get("dataset") or self.dataset or "?"
            reg = self.executor.setdefault(str(ds), {})
            for k, v in kv.items():
                if k != "dataset":
                    reg[k] = v
            self.eventos.append(u"executor da rede %s: %s" % (
                ds, u", ".join(u"%s=%s" % (k, v) for k, v in sorted(kv.items())
                               if k != "dataset")[:180]))
        elif tipo in ("remendo", "aviso"):
            self.t_sinal = agora
            self.t_progresso = agora
            self.eventos.append(u"envelope: %s" % "|".join(campos[1:])[:200])


class _JuizDaTrava(object):

    RELOGIO_DO_PROGRESSO = "t_progresso"

    def __init__(self, trava=None, com_envelope=True, t0=None):
        c = trava_efetiva(trava)
        self.sem_pulso_s = c["sem_pulso_min"] * 60.0
        self.paginando_s = c["paginando_min"] * 60.0
        self.ram_limite = c["ram_pct"]
        self.com_envelope = bool(com_envelope)
        self.t0 = time.time() if t0 is None else float(t0)
        self.ram_alta_desde = None
        self.ram_pct = None
        self.pf_no_inicio = None

    @staticmethod
    def _pf(leitor):
        try:
            return int((leitor.pulso or {}).get("pf"))
        except (TypeError, ValueError):
            return None

    def anotar_memoria(self, mem, agora, leitor=None):
        if not mem:
            return
        try:
            pct = float(mem[2])
        except (TypeError, ValueError, IndexError):
            return
        self.ram_pct = mem[2]
        if pct >= self.ram_limite:
            if self.ram_alta_desde is None:
                self.ram_alta_desde = agora
                self.pf_no_inicio = self._pf(leitor) if leitor else None
        else:
            self.ram_alta_desde = None
            self.pf_no_inicio = None

    def julgar(self, leitor, agora, mem=None):
        try:
            self.anotar_memoria(mem, agora, leitor)
            if self.com_envelope:
                ultimo = (leitor.t_pulso if leitor.t_pulso is not None
                          else self.t0)
                calado = agora - ultimo
                if calado >= self.sem_pulso_s:
                    return ("sem_pulso", {
                        "sem_pulso_s": round(calado, 1),
                        "limite_s": round(self.sem_pulso_s, 1),
                        "pulsos": int(getattr(leitor, "pulsos", 0) or 0),
                        "rss_mb": (leitor.pulso or {}).get("rss_mb")})
            if self.ram_alta_desde is not None:
                prog = getattr(leitor, self.RELOGIO_DO_PROGRESSO)
                parado = agora - prog
                alta = agora - self.ram_alta_desde
                if parado >= self.paginando_s and alta >= self.paginando_s:
                    pf, pf0 = self._pf(leitor), self.pf_no_inicio
                    return ("paginando", {
                        "sem_progresso_s": round(parado, 1),
                        "ram_alta_s": round(alta, 1),
                        "ram_pct": self.ram_pct,
                        "ram_limite": self.ram_limite,
                        "limite_s": round(self.paginando_s, 1),
                        "rss_mb": (leitor.pulso or {}).get("rss_mb"),
                        "pf_no_periodo": ((pf - pf0) if (pf is not None
                                                         and pf0 is not None)
                                          else None)})
        except Exception:
            return None
        return None


def _nome_da_parte(task, parte, dataset=None):
    if parte:
        try:
            import radai_tasks
            ds = (radai_tasks.POR_NOME.get(task) or {}).get("datasets") or []
        except ImportError:
            ds = []
        if 1 <= parte[0] <= len(ds):
            try:
                n = NOME_DA_PARTE.get(int(ds[parte[0] - 1]))
            except (TypeError, ValueError):
                n = None
            if n:
                return n
    try:
        if dataset:
            return NOME_DA_PARTE.get(int(dataset))
    except (TypeError, ValueError):
        pass
    return None


RECORTE_NO_CORPO_PADRAO = True

_INICIO_DO_RECORTE = "Generating rough body segmentation"
_FIM_DO_RECORTE = "Rough body segmentation generated in"
_CORTOU_A_SERIE = "cropping from"
_REDE_UNICA = "Predicting..."
_RECORTE_VAZIO = "Crop is empty"


def _recorte_no_corpo(task, pedido, amb):
    pedido = RECORTE_NO_CORPO_PADRAO if pedido is None else bool(pedido)
    try:
        import radai_tasks
        aplica, porque = radai_tasks.recorte_no_corpo_se_aplica(task)
        pasta = radai_tasks.pasta_pesos(amb)
    except Exception as e:
        return {"estado": "desligado", "flag": False, "alerta": True,
                "falta_peso": False,
                "motivo": u"nao consegui perguntar a radai_tasks (%s: %s)"
                          % (type(e).__name__, str(e)[:120])}
    if not aplica:
        estado = u"desligado" if u"nao sei" in porque else u"nao se aplica"
        return {"estado": estado, "flag": False, "alerta": False,
                "falta_peso": False, "motivo": porque}
    if not pedido:
        return {"estado": "desligado", "flag": False, "alerta": False,
                "falta_peso": False,
                "motivo": u"quem chamou pediu sem o recorte (a chave "
                          u"RECORTE_NO_CORPO do config)"}
    presente, frase = radai_tasks.pesos_do_recorte_no_corpo(pasta)
    if not presente:
        return {"estado": "desligado", "flag": False, "alerta": True,
                "falta_peso": True, "motivo": frase}
    return {"estado": "ligado", "flag": True, "alerta": False,
            "falta_peso": False, "motivo": frase}


def _linha_do_recorte(task, dec):
    if dec["estado"] == "ligado":
        return u"TS %s recorte no corpo: ligado (Dataset300, 6 mm)" % task
    if dec.get("falta_peso"):
        return (u"! TS %s recorte no corpo: DESLIGADO nesta task, faltam os "
                u"pesos do Dataset300 (%s) — rodando a TC inteira"
                % (task, dec["motivo"]))
    return u"%sTS %s recorte no corpo: %s (%s)" % (
        u"! " if dec.get("alerta") else u"", task, dec["estado"],
        dec["motivo"])


def _guardar_etapas(jid, task, leitor, tentativa, dispositivo):
    try:
        leitor.fechar()
        fora = []
        for e in leitor.etapas:
            if e.get("tipo") == "recorte":
                nome, parte, de = u"recorte do corpo (6 mm)", None, None
            elif e.get("tipo") == "rede":
                parte, de = None, None
                ds = e.get("dataset")
                n = _nome_da_parte(task, None, ds) if ds else None
                nome = (u"rede %s%s" % (ds, (u" (%s)" % n) if n else u"")
                        if ds else u"rede unica")
            else:
                parte, de = e["parte"]
                n = _nome_da_parte(task, e["parte"], e.get("dataset"))
                nome = u"parte %d/%d%s" % (parte, de,
                                           (u" (%s)" % n) if n else u"")
            item = {"task": task, "tentativa": int(tentativa),
                    "dispositivo": dispositivo, "etapa": nome,
                    "parte": parte, "de": de, "dataset": e.get("dataset"),
                    "segundos": round(max(0.0, float(e["fim"])
                                          - float(e["inicio"])), 1)}
            if e.get("incompleta"):
                item["incompleta"] = True
            _ex = (getattr(leitor, "executor", None) or {}).get(
                str(e.get("dataset"))) if e.get("dataset") else None
            if _ex:
                item["executor"] = dict(_ex)
            fora.append(item)
        leitor.etapas = []
        _anotar_no_job(jid, task, partes=fora)
    except Exception:
        pass


def _duracao(s):
    s = int(max(0, s))
    if s >= 3600:
        return u"%dh%02dm" % (s // 3600, (s % 3600) // 60)
    return u"%dm%02ds" % (s // 60, s % 60)


def _linha_do_batimento(task, leitor, secs, modo, agora, ram_livre_mb=None):
    campos = [u"TS %s" % task]
    onde = leitor.onde(task)
    if onde:
        campos.append(onde)
    campos.append(_duracao(secs))
    rot = {"gpu": u"gpu", "gpu_resultado_na_cpu": u"gpu-resultado-na-cpu",
           "cpu": u"cpu"}.get(modo, modo)
    if leitor.sem_placa and modo != "cpu":
        rot = u"cpu (o torch nao alcancou a placa)"
    elif leitor.desceu_para_ram and modo == "gpu":
        rot = u"gpu-resultado-na-cpu (a biblioteca desceu sozinha)"
    campos.append(rot)
    vram = (leitor.pulso or {}).get("vram_mb") or ""
    if "/" in vram:
        try:
            u_, t_ = vram.split("/", 1)
            campos.append(u"VRAM %s/%s GiB" % (_gib(float(u_)),
                                               _gib(float(t_))))
        except ValueError:
            pass
    if ram_livre_mb is not None:
        campos.append(u"RAM livre %s GiB" % _gib(ram_livre_mb))
    rss = (leitor.pulso or {}).get("rss_mb")
    if rss and rss != "?":
        try:
            campos.append(u"processo %s GiB" % _gib(float(rss)))
        except ValueError:
            pass
    campos.append(u"ultimo sinal ha %s" % (
        u"%ds" % int(agora - leitor.t_sinal)
        if agora - leitor.t_sinal < 120
        else _duracao(agora - leitor.t_sinal)))
    return u" | ".join(campos)


_CACHE_DITO = set()


class SemCacheParaOPos(RuntimeError):

    def __init__(self, task):
        self.task = task
        RuntimeError.__init__(
            self, u"refazer so o pos-processamento: a task %s nao esta no "
                  u"cache desta estacao — a inferencia nao roda; refaca a "
                  u"serie inteira" % task)


RAIZES_DA_VOLTA_A_GRADE = ("resample", "colar_na_grade", "recortar_imagem")
_CODIGO_DA_VOLTA = {}


def codigo_da_volta_a_grade(fonte=None):
    import hashlib as _h
    if fonte is None and "valor" in _CODIGO_DA_VOLTA:
        return _CODIGO_DA_VOLTA["valor"]
    try:
        texto = fonte if fonte is not None else _fonte_do_modulo("engine")
        valor = _h.sha256(u"\n".join(_codigo_do_pos_no_motor(
            texto, raizes=RAIZES_DA_VOLTA_A_GRADE)).encode("utf-8")
        ).hexdigest()[:16]
    except Exception as e:
        valor = u"?%s" % type(e).__name__
    if fonte is None:
        _CODIGO_DA_VOLTA["valor"] = valor
    return valor


def _contexto_do_cache(ref, task, body_seg, caixa, jid):
    try:
        import radai_cache_tasks as _ct
        if not _ct.armado():
            return None
        p = _ct.pasta()
        ok, motivo = _ct.conferir_pasta(p)
        if not ok:
            if jid not in _CACHE_DITO:
                _CACHE_DITO.add(jid)
                _log(jid, u"cache por task desligado nesta serie: %s" % motivo)
            return None
        rec = _ct.receita(task, recorte_no_corpo=body_seg, caixa=caixa,
                          envelope=RUNNER_TS if os.path.isfile(RUNNER_TS)
                          else None, codigo=codigo_da_volta_a_grade())
        ch = _ct.chave(_ct.impressao_do_volume(ref), task, rec)
        return {"chave": ch, "receita": rec, "pasta": p,
                "lido": _ct.ler(ch, p)}
    except Exception as e:
        _log(jid, u"cache por task: nao consegui montar a chave (%s: %s) — "
                  u"a task roda" % (type(e).__name__, str(e)[:120]))
        return None


def _gravar_no_cache(ctx, arr, task, jid, modo, localizador_vazio):
    try:
        import radai_cache_tasks as _ct
        ok, motivo = _ct.gravar(ctx["chave"], arr, {
            "task": task, "receita": ctx["receita"], "plano": modo,
            "localizador_vazio": bool(localizador_vazio),
            "forma": [int(v) for v in arr.shape]}, p=ctx["pasta"])
        if not ok:
            _log(jid, u"TS %s: nao gravei no cache desta estacao (%s)"
                 % (task, motivo))
        else:
            _anotar_no_job(jid, task, cache={"lido": False, "gravado": True,
                                             "chave": ctx["chave"]})
    except Exception as e:
        _log(jid, u"TS %s: nao gravei no cache desta estacao (%s)"
             % (task, type(e).__name__))


def _mascaras_do_arr(arr, task, jid, cruas, suavizar,
                     localizador_vazio=False):
    idx_to_name = TS_CLASS_MAP.get(_nome_biblioteca(task), {})
    if not idx_to_name:
        raise RuntimeError("mapa de classes do TS indisponivel para a task %s "
                           "(totalsegmentator.map_to_binary nao importou)"
                           % task)
    tem_rotulo = bool(np.any(arr))
    # GUARDA: as mascaras por task ficam na caixa delas; na grade inteira,
    # as ~120 da base de uma TC de 400 cortes passam de 12 GiB no vigia.
    masks = masks_compactas_da_task(arr, task, idx_to_name)
    if cruas is not None:
        cruas[task] = MasksCruas(arr, idx_to_name)
    if not masks:
        if not alimenta_o_entregue(task):
            crus = len(cruas[task]) if (cruas is not None and task in cruas) else 0
            _log(jid, "TS %s: %d rotulo(s) fora do TS_MAP -- %s"
                      % (task, crus,
                         destino_dos_rotulos_fora_do_mapa(task)))
            if not tem_rotulo and not _e_base(task):
                return _ausencia(jid, task, localizador_vazio)
            return {}
        if not _e_base(task):
            return _ausencia(jid, task, localizador_vazio)
        raise RuntimeError("TS %s rodou mas nenhuma estrutura conhecida "
                           "apareceu no volume" % task)
    _log(jid, "TS %s: %d estruturas" % (task, len(masks)))
    if suavizar:
        suavizar_masks(masks, jid)
    return masks


FRASE_DA_DECISAO_DE_RAM = {
    "cabe": u"cabe",
    "paginar": u"vai paginar e ficar lenta (passa da RAM livre e cabe no "
               u"commit)",
    "adiar": u"nao cabe: o processo nao e aberto (a base adia a serie; "
             u"as outras ficam de fora desta serie)"}


def _plano_de_ram(task, ref_env, jid, caixa, regiao_ram):
    try:
        forma = tuple(int(v) for v in ref_env.GetSize())[::-1]
        esp = tuple(float(v) for v in ref_env.GetSpacing())[::-1]
        cx = (regiao_ram or {}).get("zyx") if caixa is None else None
        est = estimativa_de_ram(task, forma, esp, caixa_zyx=cx)
    except Exception as e:
        _log(jid, u"TS %s RAM: sem estimativa (%s: %s)"
             % (task, type(e).__name__, str(e)[:100]))
        return
    mem = memoria_e_commit()
    dec, frase = decidir_ram(est, mem)
    _log(jid, u"TS %s RAM: %s — %s" % (task, frase,
                                       FRASE_DA_DECISAO_DE_RAM.get(dec, dec)))
    if dec == "adiar":
        raise RecursoPrevisto(task, est["precisa_mb"],
                              (mem or {}).get("livre_mb"),
                              (mem or {}).get("commit_livre_mb"))


def run_ts_task(ref, task, device, jid, timeout_s=None, log_path=None,
                suavizar=True, cruas=None, recorte_no_corpo=None, trava=None,
                plano_menor=False, caixa=None, regiao_ram=None,
                so_cache=False):
    import subprocess
    task = _task_que_roda(task, log=lambda m: _log(jid, m))
    conferir_tasks([task])
    # GUARDA: a recusa fica na funcao que executa, e nao so nas portas.
    conferir_volume_contornavel(ref, modalidade=modalidade_da_task(task))
    timeout_s = TIMEOUT_TASK_S if timeout_s is None else timeout_s
    work = Path(tempfile.mkdtemp(prefix="ts_"))
    log_ts = Path(log_path) if log_path else (work / ("%s.log" % task))
    try:
        nii = work / "in.nii.gz"
        ref_env = ref
        if caixa is not None:
            ref_env = recortar_imagem(ref, caixa)
            _log(jid, u"TS %s recortada (clip-box): a caixa de «%s» com %s mm "
                      u"de margem (eixos %s), %s -> %s voxels, %s%% da serie "
                      u"— a saida volta a grade inteira"
                 % (task, caixa.get("ancora") or u"?",
                    _pct(caixa.get("margem_mm")), caixa.get("eixos") or u"?",
                    u"x".join(str(v) for v in ref.GetSize()),
                    u"x".join(str(v) for v in ref_env.GetSize()),
                    _pct(round(100.0 * _fracao_da_caixa(ref, caixa), 1))))
            _anotar_no_job(jid, task, clip=dict(
                caixa, zyx=[list(par) for par in caixa["zyx"]],
                grade_serie=list(ref.GetSize()),
                grade_da_task=list(ref_env.GetSize())))
        out_ml = work / ("%s_ml.nii.gz" % task)
        _base_cmd = list(TS_CMD)
        if RUNNER_TS in _base_cmd and not os.path.isfile(RUNNER_TS):
            _log(jid, "! TS %s: o envelope radai_ts_runner.py nao esta ao "
                      "lado do motor -- rodando o TotalSegmentator direto, "
                      "SEM o batimento e SEM a saida dura (a thread orfa do "
                      "nnU-Net pode segurar o processo; o vigia da saida "
                      "aproveita o arquivo se isso acontecer)" % task)
            _base_cmd = list(TS_CMD_DIRETO)
        _com_envelope = RUNNER_TS in _base_cmd
        _disp = device if device else "gpu"
        cmd = _base_cmd + ["-i", str(nii), "-o", str(out_ml),
                        "--task", _nome_biblioteca(task),
                        "--ml", "--device", _disp,
                        "-v"]
        # GUARDA: nada de --fast/--fastest: a resolução reduzida dá contorno
        # ruidoso para radioterapia; é exceção, e não `assert` (o -O o tira).
        _reduzida = [f for f in ("--fast", "--fastest") if f in cmd]
        if _reduzida:
            raise RuntimeError(
                "resolucao reduzida nao entra nesta entrega (%s). O padrao "
                "foi decidido depois de rodar os dois modos e olhar o "
                "contorno: ruidoso demais para radioterapia."
                % ", ".join(_reduzida))
        if task in TASKS_DE_ACHADO:
            _log(jid, "ACHADO: a task `%s` procura achado, e esta rodando "
                      "porque foi PEDIDA (ela nao esta no padrao do pacote). "
                      "O que ela devolver sai como sugestao nao-aprovada, "
                      "como todo o resto." % task)
        _amb = dict(os.environ, PYTHONUNBUFFERED="1")
        try:
            _amb = _arq.ambiente_da_serie(_amb)
        except Exception:
            pass
        for _k in ("RADAI_RESULTADOS_NA_CPU", "RADAI_SEM_AUTOCAST"):
            _amb.pop(_k, None)
        _recorte = _recorte_no_corpo(task, recorte_no_corpo, _amb)
        _log(jid, _linha_do_recorte(task, _recorte))
        if _recorte["flag"]:
            # GUARDA: o --body_seg recorta a REGIAO do corpo e NAO reduz
            # resolucao; nao confundir com --fast.
            cmd.append("--body_seg")
        _anotar_no_job(jid, task, recorte=_recorte)
        _cache_ctx = _contexto_do_cache(ref, task, _recorte["flag"], caixa,
                                        jid)
        if _cache_ctx is not None and _cache_ctx.get("lido") is not None:
            _arr_c, _meta_c = _cache_ctx["lido"]
            _log(jid, u"TS %s: do cache desta estacao (gravado em %s, mesma "
                      u"receita) — a inferencia nao roda"
                 % (task, _meta_c.get("gravado_em") or u"?"))
            _anotar_no_job(jid, task, cache={
                "lido": True, "gravado_em": _meta_c.get("gravado_em"),
                "plano": _meta_c.get("plano"),
                "chave": _cache_ctx.get("chave")})
            return _mascaras_do_arr(
                _arr_c, task, jid, cruas, suavizar,
                localizador_vazio=bool(_meta_c.get("localizador_vazio")))
        if so_cache:
            raise SemCacheParaOPos(task)
        _modo = "cpu"
        if _dispositivo_pedido_e_placa(device):
            try:
                _forma = tuple(int(v) for v in ref_env.GetSize())[::-1]
                _esp = tuple(float(v) for v in ref_env.GetSpacing())[::-1]
                _plano = plano_de_dispositivo(_forma, _esp, task=task)
            except Exception as _e:
                _plano = {"modo": "cpu", "indice": None, "capacidade": None,
                          "motivo": u"cpu: nao consegui montar o plano "
                                    u"(%s: %s)" % (type(_e).__name__,
                                                   str(_e)[:120])}
            if plano_menor:
                _plano = _plano_um_degrau_abaixo(_plano)
                _log(jid, u"TS %s plano menor (retomada de task travada): %s "
                          u"-> %s" % (task, _plano.get("modo_do_plano"),
                                      _plano.get("modo")))
            _modo = _plano.get("modo") or "cpu"
            if _recorte["flag"]:
                _plano = dict(_plano)
                _plano["motivo"] = (
                    u"%s | com o recorte no corpo o volume real e menor que "
                    u"o desta conta (grade inteira): a escolha fica do lado "
                    u"seguro" % (_plano.get("motivo") or u""))
            _anotar_no_job(jid, task, plano=_plano)
            _log(jid, "TS %s dispositivo: %s" % (task, _plano.get("motivo")))
            if _modo != "cpu":
                if _plano.get("indice") is not None:
                    _amb["CUDA_DEVICE_ORDER"] = "PCI_BUS_ID"
                    _amb["CUDA_VISIBLE_DEVICES"] = str(_plano["indice"])
                if _modo == "gpu_resultado_na_cpu":
                    _amb["RADAI_RESULTADOS_NA_CPU"] = "1"
                if not usar_autocast(_plano.get("capacidade")):
                    _amb["RADAI_SEM_AUTOCAST"] = "1"
                    _log(jid, "TS %s: autocast desligado para esta placa "
                              "(sm %s)" % (task, _plano.get("capacidade")))
        else:
            _log(jid, "TS %s dispositivo: cpu — pedido por quem chamou "
                      "(DEVICE=cpu, ou nenhuma placa alcancada pelo torch)"
                 % task)
            _plano_cpu = {
                "modo": "cpu", "indice": None, "capacidade": None,
                "motivo": u"cpu: pedido por quem chamou (DEVICE=cpu, ou "
                          u"nenhuma placa alcancada pelo torch)"}
            if plano_menor:
                _plano_cpu = _plano_um_degrau_abaixo(_plano_cpu)
                _log(jid, u"TS %s plano menor (retomada de task travada): ja "
                          u"em cpu, nao ha degrau abaixo — a task e refeita do "
                          u"zero no mesmo plano" % task)
            _anotar_no_job(jid, task, plano=_plano_cpu)
        _disp = "cpu" if _modo == "cpu" else "gpu"
        _i_disp = cmd.index("--device") + 1
        cmd[_i_disp] = _disp
        if _modo in ("cpu", "gpu_resultado_na_cpu"):
            _plano_de_ram(task, ref_env, jid, caixa, regiao_ram)
        _desligar_estatistica_antes(cmd, _amb, jid, task)
        # GUARDA: a entrada do filho so e escrita depois do cache e do plano
        # de RAM; no acerto do cache e no adiamento ela nao serve a ninguem.
        sitk.WriteImage(ref_env, str(nii))

        _vigia_mb = memoria_do_processo_mb()
        _log(jid, "TS %s (iniciando)%s" % (
            task, (u" | vigia %s GiB" % _gib(_vigia_mb)) if _vigia_mb
            else u""))
        _mem0 = _memoria_agora()
        _pior = _mem0[1] if _mem0 else None
        _pico_pct = _mem0[2] if _mem0 else 0
        _avisou_mem = False
        _aproveitada = False
        _tentativa = 0
        _refez_em_cpu = False
        _refez_sem_recorte = False
        while True:
            _tentativa += 1
            try:
                _inicio_log = os.path.getsize(str(log_ts))
            except OSError:
                _inicio_log = 0
            with open(str(log_ts), "ab") as saida:
                proc = subprocess.Popen(cmd, stdout=saida,
                                        stderr=subprocess.STDOUT, env=_amb)
                t0 = time.time()
                ultimo_mem = 0
                _leitor = _LeitorDoLogTS(log_ts, offset=_inicio_log, agora=t0)
                _juiz = _JuizDaTrava(trava, com_envelope=_com_envelope,
                                     t0=t0)
                _ultimo_beat = t0
                _estado_dito = (None, None, False, False, None, False)
                _avisou_silencio = False
                _saida_tam, _saida_t, _saida_julgada = None, t0, False
                _disse_saida_ruim = False
                while proc.poll() is None:
                    agora = time.time()
                    secs = int(agora - t0)
                    _leitor.ler(agora)
                    for _ev in _leitor.eventos:
                        _log(jid, "  TS %s: %s" % (task, _ev))
                    _leitor.eventos = []
                    _m = None
                    if secs - ultimo_mem >= MEMORIA_A_CADA_S:
                        ultimo_mem = secs
                        _m = _memoria_agora()
                        if _m:
                            if _pior is None or _m[1] < _pior:
                                _pior = _m[1]
                            _pico_pct = max(_pico_pct, _m[2])
                            if _m[2] >= 92 and not _avisou_mem:
                                _avisou_mem = True
                                _log(jid, "  ! memoria apertada: %.1f GB livres de "
                                          "%.1f (%d%% em uso). A estacao pode "
                                          "comecar a paginar, e a task fica lenta "
                                          "sem erro nenhum"
                                     % (_m[1] / 1024.0, _m[0] / 1024.0, _m[2]))
                    _estado = (_leitor.parte, _leitor.dataset,
                               _leitor.desceu_para_ram, _leitor.sem_placa,
                               _leitor.recorte, _leitor.rede_unica)
                    _mudou = _estado != _estado_dito
                    if _mudou or agora - _ultimo_beat >= BATIMENTO_TS_S:
                        if _m is None:
                            _m = _memoria_agora()
                        _texto = _linha_do_batimento(
                            task, _leitor, secs, _modo, agora,
                            ram_livre_mb=(_m[1] if _m else None))
                        if _mudou:
                            _log(jid, "  " + _texto)
                        else:
                            _log(jid, "  " + _texto
                                 + " (still working, please wait)")
                        _estado_dito = _estado
                        _ultimo_beat = agora
                    _calado = agora - _leitor.t_sinal
                    if _calado >= SILENCIO_AVISO_S and not _avisou_silencio:
                        _avisou_silencio = True
                        _log(jid, "  ! TS %s: sem sinal ha %s — nem saida do "
                                  "TotalSegmentator nem mudanca no pulso do "
                                  "runner. NAO encerro: o pos-processamento "
                                  "ja ficou 6m36s calado e terminou certo. O "
                                  "limite e o tempo da task (%d s)%s"
                             % (task, _duracao(_calado), timeout_s,
                                (u" — e a LEITURA do log esta falhando (%s): "
                                 u"o silencio pode ser do motor, e nao da task"
                                 % _leitor.erro) if _leitor.erro else u""))
                    elif _calado < SILENCIO_AVISO_S and _avisou_silencio:
                        _avisou_silencio = False
                        _log(jid, "  TS %s: o sinal voltou" % task)
                    if out_ml.exists():
                        try:
                            _tam = out_ml.stat().st_size
                        except OSError:
                            _tam = None
                        if _tam != _saida_tam:
                            _saida_tam, _saida_t = _tam, agora
                            _saida_julgada = False
                        elif (not _saida_julgada
                              and agora - _saida_t >= SAIDA_PARADA_S):
                            _saida_julgada = True
                            _ok, _porque = _saida_inteira(out_ml, ref_env)
                            if _ok:
                                _encerrar_arvore_e_dizer(proc, jid, task)
                                _aproveitada = True
                                _log(jid, "  TS %s: a task terminou e o "
                                          "processo nao saiu (thread orfa do "
                                          "nnU-Net) — saida aproveitada "
                                          "(parada ha %ds, %s)"
                                     % (task, int(agora - _saida_t), _porque))
                                break
                            if not _disse_saida_ruim:
                                _disse_saida_ruim = True
                                _log(jid, "  ! TS %s: a saida parou de crescer "
                                          "e NAO abre inteira (%s) — nao "
                                          "aproveito; sigo esperando ate o "
                                          "tempo limite (%d s)"
                                     % (task, _porque, timeout_s))
                    _veredito = _juiz.julgar(_leitor, agora, _m)
                    if _veredito is not None:
                        _mot_t, _nums_t = _veredito
                        _onde_t = _leitor.onde(task) or u"preparacao"
                        _frase_t = _frase_da_trava(_mot_t, _nums_t)
                        _encerrar_arvore_e_dizer(proc, jid, task)
                        _guardar_etapas(jid, task, _leitor, _tentativa, _disp)
                        _log(jid, u"  ! TS %s TRAVADA (%s) em %s, aos %s: %s — "
                                  u"encerrada com a arvore de processos, antes "
                                  u"do teto da task (%s)"
                             % (task, _NOME_DA_TRAVA.get(_mot_t, _mot_t),
                                _onde_t, _duracao(secs), _frase_t,
                                _duracao(timeout_s)))
                        _anotar_no_job(jid, task, travamento={
                            "motivo": _mot_t, "numeros": dict(_nums_t),
                            "onde": _onde_t, "segundos": secs,
                            "modo": _modo, "plano_menor": bool(plano_menor),
                            "recortada": caixa is not None})
                        raise TaskTravada(task, _mot_t, _nums_t,
                                          frase=_frase_t, onde=_onde_t)
                    if _job(jid).get("cancelar"):
                        _encerrar_arvore_e_dizer(proc, jid, task)
                        _guardar_etapas(jid, task, _leitor, _tentativa, _disp)
                        raise Cancelado("TS %s interrompida a pedido, aos %ds"
                                        % (task, secs))
                    if secs > timeout_s:
                        _encerrar_arvore_e_dizer(proc, jid, task)
                        _guardar_etapas(jid, task, _leitor, _tentativa, _disp)
                        raise _falha_da_task(
                            task, log_ts, _inicio_log, jid, tempo_limite=True,
                            frase=u"TS %s passou do tempo limite (%d s) e foi "
                                  u"encerrada." % (task, timeout_s))
                    time.sleep(2)
            _leitor.ler()
            for _ev in _leitor.eventos:
                _log(jid, "  TS %s: %s" % (task, _ev))
            _leitor.eventos = []
            if _leitor.fim is not None:
                _log(jid, "  TS %s: o envelope saiu com codigo %s"
                     % (task, _leitor.fim))
            _log(jid, u"  TS %s: %s" % (task, frase_do_pico(_leitor.pico)))
            _anotar_no_job(jid, task, pico=_leitor.pico or {
                "commit_mb": None, "ws_mb": None})
            _guardar_etapas(jid, task, _leitor, _tentativa, _disp)
            if (_recorte["flag"] and not _refez_sem_recorte
                    and (_aproveitada or not proc.returncode)):
                try:
                    with open(str(log_ts), "rb") as _fv:
                        _fv.seek(_inicio_log)
                        _vazio = _RECORTE_VAZIO in _fv.read().decode(
                            "utf-8", "replace")
                except Exception:
                    _vazio = False
                if _vazio:
                    _log(jid, "  ! TS %s: o recorte do corpo saiu VAZIO (a "
                              "biblioteca devolveu a segmentacao vazia, sem "
                              "erro) — refazendo a task SEM o recorte, uma "
                              "vez" % task)
                    _refez_sem_recorte = True
                    _aproveitada = False
                    cmd = [c for c in cmd if c != "--body_seg"]
                    _i_disp = cmd.index("--device") + 1
                    _recorte = dict(_recorte, estado="desligado", flag=False,
                                    motivo=u"a mascara do corpo saiu vazia; "
                                           u"a task foi refeita sem o recorte")
                    _anotar_no_job(jid, task, recorte=_recorte)
                    try:
                        if out_ml.exists():
                            out_ml.unlink()
                    except OSError as _e_un:
                        _log(jid, "  ! TS %s: nao consegui apagar a saida "
                                  "vazia (%s: %s) — se ela ficar, o vigia da "
                                  "saida pode julga-la" % (
                                      task, type(_e_un).__name__,
                                      str(_e_un)[:120]))
                    continue
            if _aproveitada:
                break
            if proc.returncode:
                if _disp != "cpu" and not _refez_em_cpu:
                    try:
                        with open(str(log_ts), "rb") as _fh:
                            _fh.seek(_inicio_log)
                            _deste = _fh.read().decode("utf-8", "replace")
                    except Exception as _e_log:
                        _deste = u""
                        _log(jid, "  ! TS %s: nao consegui ler o log desta "
                                  "tentativa para decidir o recuo (%s: %s) "
                                  "— sem a prova de erro de placa, a CPU NAO "
                                  "refaz" % (task, type(_e_log).__name__,
                                             str(_e_log)[:120]))
                    _prova = _erro_de_placa(_deste)
                    if _prova:
                        _onde = _leitor.onde(task) or u"preparacao"
                        _log(jid, "  ! TS %s: a placa falhou em %s: %s; "
                                  "refazendo a task INTEIRA em CPU — o "
                                  "TotalSegmentator nao guarda as partes, "
                                  "entao nao ha como retomar do meio. A "
                                  "tentativa na placa durou %s; a refeita "
                                  "tem o tempo limite inteiro de novo (%d s), "
                                  "e nao o que sobrou"
                             % (task, _onde, _prova,
                                _duracao(time.time() - t0), timeout_s))
                        try:
                            if out_ml.exists():
                                out_ml.unlink()
                        except OSError as _e_un:
                            _log(jid, "  ! TS %s: nao consegui apagar a saida "
                                      "da tentativa na placa (%s: %s) — se "
                                      "ela ficar, o vigia da saida da refeita "
                                      "pode julga-la" % (
                                          task, type(_e_un).__name__,
                                          str(_e_un)[:120]))
                        for _k in ("RADAI_RESULTADOS_NA_CPU",
                                   "RADAI_SEM_AUTOCAST", "CUDA_DEVICE_ORDER"):
                            _amb.pop(_k, None)
                        _amb["CUDA_VISIBLE_DEVICES"] = "-1"
                        _disp, _modo = "cpu", "cpu"
                        cmd[_i_disp] = "cpu"
                        _refez_em_cpu = True
                        _anotar_no_job(jid, task, recuo_cpu={
                            "onde": _onde, "prova": _prova,
                            "segundos_na_placa": round(time.time() - t0, 1)})
                        continue
                raise _falha_da_task(task, log_ts, _inicio_log, jid,
                                     codigo=proc.returncode)
            break

        try:
            _INTERESSA = ("Moving results arrays to CPU",
                          "No GPU detected",
                          "Resampled in", "Predicted in", "Saved in",
                          "Using 'fast'", "Using 'fastest'",
                          _FIM_DO_RECORTE, "cropping from", _RECORTE_VAZIO)
            _vistas = []
            with open(str(log_ts), "rb") as _fb:
                _fb.seek(_inicio_log)
                _deste_log = _fb.read().decode("utf-8", "replace")
            for _linha in _deste_log.replace("\r", "\n").splitlines():
                _linha = _linha.strip()
                if not _linha:
                    continue
                for _marca in _INTERESSA:
                    if _marca in _linha and _linha not in _vistas:
                        _vistas.append(_linha)
                        break
            for _linha in _vistas[:12]:
                _log(jid, "  TS %s: %s" % (task, _linha[:150]))
            if any("Moving results arrays to CPU" in _l for _l in _vistas):
                _log(jid, "  ! TS %s CAIU PARA CPU por falta de VRAM — a task "
                          "termina certa, e varias vezes mais devagar. Feche o "
                          "que estiver usando a placa (navegador, Teams, "
                          "visualizador) antes do proximo lote" % task)
        except Exception:
            pass

        if _mem0 and _pior is not None:
            _gasto = max(0.0, (_mem0[1] - _pior) / 1024.0)
            _log(jid, "  TS %s memoria: %.1f GB livres no inicio, %.1f no "
                      "pico de uso (-%.1f GB com tudo o que rodou junto), "
                      "%d%% da estacao no pior momento"
                 % (task, _mem0[1] / 1024.0, _pior / 1024.0, _gasto,
                    _pico_pct))

        cand = [out_ml] if out_ml.exists() else sorted(work.glob("*.nii.gz"))
        cand = [c for c in cand if c.name != "in.nii.gz"]
        if not cand:
            raise _falha_da_task(task, log_ts, _inicio_log, jid,
                                 frase=u"TS %s terminou sem saida "
                                       u"multi-label." % task)

        idx_to_name = TS_CLASS_MAP.get(_nome_biblioteca(task), {})
        if not idx_to_name:
            raise RuntimeError("mapa de classes do TS indisponivel para a task %s "
                               "(totalsegmentator.map_to_binary nao importou)" % task)

        mi = sitk.ReadImage(str(cand[0]))
        if caixa is not None:
            mi = colar_na_grade(resample(mi, ref_env), ref, caixa)
            arr = sitk.GetArrayFromImage(mi)
        else:
            arr = sitk.GetArrayFromImage(resample(mi, ref))
        del mi
        _vazio_loc = _localizador_vazio(log_ts, _inicio_log)
        if (_cache_ctx is not None and not _aproveitada
                and not proc.returncode):
            _gravar_no_cache(_cache_ctx, arr, task, jid, _modo, _vazio_loc)
        return _mascaras_do_arr(arr, task, jid, cruas, suavizar,
                                localizador_vazio=_vazio_loc)
    finally:
        shutil.rmtree(str(work), ignore_errors=True)


MARGEM_DO_RECORTE_MM = 30.0

TASKS_COM_CROP_MODEL = ("teeth",)

_PULMOES = ("lung_upper_lobe_left", "lung_lower_lobe_left",
            "lung_upper_lobe_right", "lung_middle_lobe_right",
            "lung_lower_lobe_right", "lung_left", "lung_right")
ANCORAS_DO_RECORTE = {
    "pulmoes": _PULMOES,
    "torax": _PULMOES + tuple("rib_%s_%d" % (l, i) for l in ("left", "right")
                              for i in range(1, 13))
             + ("sternum", "costal_cartilages", "clavicula_left",
                "clavicula_right", "scapula_left", "scapula_right"),
    "glandula": ("breast", "breast_left", "breast_right"),
    "cabeca_pescoco": ("skull", "brain") + tuple(
        "vertebrae_C%d" % i for i in range(1, 8)),
}

MARGEM_DO_CORPO_MM = 10.0
LIMIAR_DO_CORPO_HU = -500.0
PASSO_DA_AMOSTRA_DO_CORPO = 4

RECORTE_POR_TASK = {
    "breasts": {
        "ancora": "torax", "eixos": "z", "margem_mm": MARGEM_DO_RECORTE_MM,
        "medido": False, "numeros": None, "lateral_pelo_corpo": True},
    "trunk_cavities": {
        "ancora": "torax", "eixos": "z", "margem_mm": MARGEM_DO_RECORTE_MM,
        "medido": False, "numeros": None, "lateral_pelo_corpo": True},
    "abdominal_muscles": {
        "ancora": "torax", "eixos": "z", "margem_mm": MARGEM_DO_RECORTE_MM,
        "medido": False, "numeros": None, "lateral_pelo_corpo": True},
    "lung_vessels": {
        "ancora": "pulmoes", "eixos": "zyx", "margem_mm": MARGEM_DO_RECORTE_MM,
        "medido": False, "numeros": None},
}


def entrada_do_recorte(task, modo=None, registro=None):
    registro = RECORTE_POR_TASK if registro is None else registro
    ent = dict(registro.get(task) or {})
    var = ent.pop("fast", None)
    if ent and str(modo or "").lower() == "fast" and var:
        ent.update(var)
    return ent


def _e_base(task):
    try:
        import radai_tasks as _rt
        bases = set(_rt.BASES_CT) | set(_rt.BASES_MR)
        return (task in bases or _rt.APELIDOS.get(task, task) in bases
                or task == "total")
    except Exception:
        return task in ("total", "total_v2", "total_v3", "total_mr")


def _caixa_da_mascara(m):
    zs = np.flatnonzero(m.any(axis=(1, 2)))
    if not zs.size:
        return None
    ys = np.flatnonzero(m.any(axis=(0, 2)))
    xs = np.flatnonzero(m.any(axis=(0, 1)))
    return ((int(zs[0]), int(zs[-1])), (int(ys[0]), int(ys[-1])),
            (int(xs[0]), int(xs[-1])))


def _fracao_da_caixa(ref, caixa):
    tam = [int(v) for v in ref.GetSize()][::-1]
    total = float(tam[0] * tam[1] * tam[2]) or 1.0
    n = 1
    for a, b in caixa["zyx"]:
        n *= max(0, int(b) - int(a))
    return n / total


def corpo_da_amostra(hu, espacamento_zyx):
    try:
        import radai_geom
        import radai_skin
        corpo = radai_skin.contorno_externo(
            hu, radai_geom.Grade(espacamento_zyx), com_o_corpo=True)[1]
    except Exception:
        corpo = None
    if corpo is not None and np.asarray(corpo).any():
        return np.asarray(corpo, dtype=bool)
    # GUARDA: sem contorno externo (corpo abaixo do piso de volume, ou falha),
    # a caixa volta ao limiar, que contem o corpo e a mesa: nunca corta corpo.
    return hu > LIMIAR_DO_CORPO_HU


def caixa_do_corpo_xy(ref, margem_mm=None):
    margem_mm = MARGEM_DO_CORPO_MM if margem_mm is None else float(margem_mm)
    try:
        arr = sitk.GetArrayViewFromImage(ref)
    except Exception:
        arr = sitk.GetArrayFromImage(ref)
    if arr.ndim != 3:
        return None
    p = int(PASSO_DA_AMOSTRA_DO_CORPO)
    esp = [float(v) for v in ref.GetSpacing()][::-1]
    hu = np.asarray(arr[::2, ::p, ::p])
    amostra = corpo_da_amostra(hu, (esp[0] * 2, esp[1] * p, esp[2] * p))
    ys = np.flatnonzero(amostra.any(axis=(0, 2)))
    xs = np.flatnonzero(amostra.any(axis=(0, 1)))
    if not ys.size or not xs.size:
        return None
    ny, nx = int(arr.shape[1]), int(arr.shape[2])
    my = int(math.ceil(margem_mm / esp[1])) + p if esp[1] > 0 else p
    mx = int(math.ceil(margem_mm / esp[2])) + p if esp[2] > 0 else p
    y0 = max(0, int(ys[0]) * p - my)
    y1 = min(ny, (int(ys[-1]) + 1) * p + my)
    x0 = max(0, int(xs[0]) * p - mx)
    x1 = min(nx, (int(xs[-1]) + 1) * p + mx)
    return (y0, y1), (x0, x1)


def caixa_de_recorte(task, fontes, ref, registro=None, forcar=False,
                     modo=None, cruas=None):
    registro = RECORTE_POR_TASK if registro is None else registro
    if _e_base(task):
        return None, (u"a base nunca e recortada (pular parte dela ja perdeu "
                      u"L1-L3, as carotidas e a 1a costela)")
    if task in TASKS_COM_CROP_MODEL:
        return None, (u"a task ja recorta pelo modelo de outra task "
                      u"(crop_model) -- recortar por fora mudaria a entrada "
                      u"dele")
    ent = entrada_do_recorte(task, modo=modo, registro=registro)
    if not ent:
        return None, u"sem entrada no registro RECORTE_POR_TASK"
    pela_ancora = bool(ent.get("medido") or forcar)
    pelo_corpo = bool(ent.get("lateral_pelo_corpo"))
    if not pela_ancora and not pelo_corpo:
        return None, (u"o recorte desta task nao foi medido (medido=nao): "
                      u"ela roda inteira")
    tam = [int(v) for v in ref.GetSize()][::-1]
    nome_anc = ent.get("ancora")
    margem = float(ent.get("margem_mm", MARGEM_DO_RECORTE_MM))
    eixos = ent.get("eixos") or "zyx"
    zyx, vistos = None, []
    if pela_ancora:
        nomes = ANCORAS_DO_RECORTE.get(nome_anc)
        if not nomes:
            return None, u"ancora desconhecida: %r" % (nome_anc,)
        zyx, vistos = _caixa_dos_nomes(nomes, fontes, cruas, ref, margem,
                                       eixos)
        if zyx is None and not pelo_corpo:
            return None, (u"a ancora «%s» nao apareceu nas mascaras da base: "
                          u"a task roda inteira" % nome_anc)
    if zyx is None:
        zyx = tuple((0, n) for n in tam)
        eixos, nome_anc = "", None
    corpo = None
    if pelo_corpo:
        try:
            corpo = caixa_do_corpo_xy(ref)
        except Exception:
            corpo = None
        if corpo is not None:
            (cy0, cy1), (cx0, cx1) = corpo
            zyx = (tuple(zyx[0]),
                   (max(int(zyx[1][0]), cy0), min(int(zyx[1][1]), cy1)),
                   (max(int(zyx[2][0]), cx0), min(int(zyx[2][1]), cx1)))
            eixos = (eixos + u"+xy pelo corpo") if eixos else u"xy pelo corpo"
    zyx = tuple((int(a), int(b)) for a, b in zyx)
    if any(b <= a for a, b in zyx):
        return None, u"a caixa ficou vazia: a task roda inteira"
    if all(a == 0 and b == n for (a, b), n in zip(zyx, tam)):
        return None, (u"a caixa (%s) e a serie inteira: nada a recortar"
                      % (nome_anc or u"corpo"))
    caixa = {"task": task, "zyx": zyx, "ancora": nome_anc or u"corpo",
             "eixos": eixos, "margem_mm": margem,
             "medido": bool(ent.get("medido")),
             "forcado": bool(forcar and not ent.get("medido")),
             "rotulos_da_ancora": len(vistos),
             "pelo_corpo": corpo is not None}
    caixa["fracao"] = round(_fracao_da_caixa(ref, caixa), 4)
    partes = []
    if pela_ancora and nome_anc:
        partes.append(u"pela ancora «%s» (%d rotulo(s)), margem %s mm"
                      % (nome_anc, len(vistos), _pct(margem)))
    if corpo is not None:
        partes.append(u"nas laterais pelo corpo (HU > %.0f, margem %s mm)"
                      % (LIMIAR_DO_CORPO_HU, _pct(MARGEM_DO_CORPO_MM)))
    frase = u"recortada " + u" e ".join(partes)
    return caixa, (u"%s, eixos %s: %.1f%% da serie"
                   % (frase, eixos, 100.0 * caixa["fracao"]))


def _caixa_dos_nomes(nomes, fontes, cruas, ref, margem, eixos="zyx"):
    lim = None
    vistos = []
    fontes = fontes or {}
    for nome in (list(fontes) if nomes is None else nomes):
        m = None
        if nome in fontes:
            m = fontes[nome]
        else:
            for c in (cruas or {}).values():
                try:
                    if nome in c:
                        m = c[nome]
                        break
                except Exception:
                    continue
        if m is None:
            continue
        cx = _caixa_da_mascara(np.asarray(m, dtype=bool))
        if cx is None:
            continue
        vistos.append(nome)
        lim = cx if lim is None else tuple(
            (min(a[0], b[0]), max(a[1], b[1])) for a, b in zip(lim, cx))
    if lim is None:
        return None, []
    tam = [int(v) for v in ref.GetSize()][::-1]
    esp = [float(v) for v in ref.GetSpacing()][::-1]
    zyx = []
    for k in range(3):
        if k > 0 and eixos == "z":
            zyx.append((0, tam[k]))
            continue
        mv = int(math.ceil(margem / esp[k] - 1e-9)) if esp[k] > 0 else 0
        zyx.append((max(0, lim[k][0] - mv), min(tam[k], lim[k][1] + mv + 1)))
    return tuple(zyx), vistos


ANCORA_DA_RAM = {
    "oculomotor_muscles": "cabeca_pescoco", "teeth": "cabeca_pescoco",
    "craniofacial_structures": "cabeca_pescoco",
    "head_glands_cavities": "cabeca_pescoco", "head_muscles": "cabeca_pescoco",
    "headneck_muscles": "cabeca_pescoco",
    "headneck_bones_vessels": "cabeca_pescoco",
    "lung_vessels": "pulmoes", "lung_vessels_LEGACY": "pulmoes",
    "lung_nodules": "pulmoes", "pleural_pericard_effusion": "torax",
}


def regiao_da_ram(task, fontes, ref, cruas=None):
    try:
        import radai_tasks as _rt
        if not _rt.RECORTAM.get(task):
            return None
    except Exception:
        return None
    anc = ANCORA_DA_RAM.get(task)
    nomes = ANCORAS_DO_RECORTE.get(anc) if anc else None
    if anc and not nomes:
        return None
    zyx, vistos = _caixa_dos_nomes(nomes, fontes, cruas, ref,
                                   MARGEM_DO_RECORTE_MM)
    if zyx is None:
        return None
    return {"zyx": zyx, "ancora": anc or u"corpo",
            "rotulos": len(vistos)}


def recortar_imagem(ref, caixa):
    (z0, z1), (y0, y1), (x0, x1) = [(int(a), int(b)) for a, b in caixa["zyx"]]
    return sitk.RegionOfInterest(ref, [x1 - x0, y1 - y0, z1 - z0],
                                 [x0, y0, z0])


def colar_na_grade(lab, ref, caixa):
    (z0, z1), (y0, y1), (x0, x1) = [(int(a), int(b)) for a, b in caixa["zyx"]]
    esperado = (x1 - x0, y1 - y0, z1 - z0)
    if tuple(int(v) for v in lab.GetSize()) != esperado:
        raise ValueError(u"a imagem a colar tem a grade %s, e a caixa e %s"
                         % (tuple(lab.GetSize()), esperado))
    tol = 0.05 * min(float(v) for v in ref.GetSpacing())
    o = ref.TransformIndexToPhysicalPoint((x0, y0, z0))
    if max(abs(a - b) for a, b in zip(lab.GetOrigin(), o)) > tol:
        raise ValueError(u"a imagem a colar nao comeca no primeiro voxel da "
                         u"caixa (origem %s, esperada %s)"
                         % (tuple(lab.GetOrigin()), tuple(o)))
    if (max(abs(a - b) for a, b in zip(lab.GetSpacing(), ref.GetSpacing()))
            > 1e-3 * min(float(v) for v in ref.GetSpacing())
            or max(abs(a - b) for a, b in zip(lab.GetDirection(),
                                              ref.GetDirection())) > 1e-4):
        raise ValueError(u"a imagem a colar nao tem o espacamento e a direcao "
                         u"da serie")
    a = sitk.GetArrayFromImage(lab)
    cheia = np.zeros(tuple(int(v) for v in ref.GetSize())[::-1], dtype=a.dtype)
    cheia[z0:z1, y0:y1, x0:x1] = a
    img = sitk.GetImageFromArray(cheia)
    img.CopyInformation(ref)
    return img


VOLUME_MINIMO_DA_CABECA_CM3 = 100.0
VOLUME_MINIMO_DO_CRANIO_CM3 = 20.0
VOLUME_MINIMO_DO_FIGADO_CM3 = 20.0
VOLUME_MINIMO_DO_QUADRIL_CM3 = 10.0
FRASE_DO_PORTAO = u"a regiao da task nao esta no campo"

REGIAO_DA_TASK = {
    # GUARDA: os constritores rodam so com o pescoco confirmado, mesmo
    # ligados a mao; a trava vence e o log diz.
    "headneck_muscles": "pescoco",
    "oculomotor_muscles": "cabeca",
    "teeth": "cabeca",
    "craniofacial_structures": "cabeca_ou_pescoco",
    "head_glands_cavities": "cabeca_ou_pescoco",
    "head_muscles": "cabeca_ou_pescoco",
    "liver_segments": "figado",
    "liver_lesions": "figado",
    "liver_segments_mr": "figado",
    "liver_lesions_mr": "figado",
    "hip_implant": "quadril",
    "lung_vessels": "torax",
    "lung_vessels_LEGACY": "torax",
    "lung_nodules": "torax",
}


def _cm3_de(masks, nomes, cru, grade):
    total = 0.0
    for n in nomes:
        total += _cm3_da_mascara(_mascara_de(masks, n, cru), grade)
    return total


def portao_da_regiao(task, masks, cruas=None, grade=None):
    regiao = REGIAO_DA_TASK.get(task)
    if not regiao or grade is None or not masks:
        return None
    cru = None
    for c in (cruas or {}).values():
        cru = c
        break
    try:
        if regiao in ("cabeca", "cabeca_ou_pescoco"):
            enc = _cm3_de(masks, ("brain",), cru, grade)
            cra = _cm3_de(masks, ("skull",), cru, grade)
            if (enc >= VOLUME_MINIMO_DA_CABECA_CM3
                    or cra >= VOLUME_MINIMO_DO_CRANIO_CM3):
                return None
            if regiao == "cabeca_ou_pescoco" and pescoco_no_campo(
                    masks, grade, cru=cru)[0]:
                return None
            return (u"%s: encefalo %.0f cm3 (piso %.0f), cranio %.0f cm3 "
                    u"(piso %.0f)%s" % (FRASE_DO_PORTAO, enc,
                                        VOLUME_MINIMO_DA_CABECA_CM3, cra,
                                        VOLUME_MINIMO_DO_CRANIO_CM3,
                                        u" e sem o pescoco" if regiao ==
                                        "cabeca_ou_pescoco" else u""))
        if regiao == "pescoco":
            tem, laudo = pescoco_no_campo(masks, grade, cru=cru)
            if tem:
                return None
            return u"%s: so roda com o pescoco confirmado — %s" % (
                FRASE_DO_PORTAO, laudo)
        if regiao == "figado":
            v = _cm3_de(masks, ("liver",), cru, grade)
            if v >= VOLUME_MINIMO_DO_FIGADO_CM3:
                return None
            return u"%s: figado %.0f cm3 (piso %.0f)" % (
                FRASE_DO_PORTAO, v, VOLUME_MINIMO_DO_FIGADO_CM3)
        if regiao == "quadril":
            v = _cm3_de(masks, ("hip_left", "hip_right", "femur_left",
                                "femur_right"), cru, grade)
            if v >= VOLUME_MINIMO_DO_QUADRIL_CM3:
                return None
            return u"%s: quadril e femur %.0f cm3 (piso %.0f)" % (
                FRASE_DO_PORTAO, v, VOLUME_MINIMO_DO_QUADRIL_CM3)
        if regiao == "torax":
            tem, pq = torax_no_campo(masks, grade=grade)
            return None if tem else u"%s: %s" % (FRASE_DO_PORTAO, pq)
    except Exception:
        return None
    return None


def _classe_da_falha(e):
    return classificar_falha(e)


def rodar_tasks(ref, tasks, device, jid, timeout_s=None, trava=None,
                rodar=None, depois_de=None, antes_de=None, ao_terminar=None,
                retomar=True, ao_falhar=None, classificar=None,
                obrigatorias=(), modo=None, recortar=True, cruas=None,
                portao=True, **kw):
    rodar = run_ts_task if rodar is None else rodar
    obrig = set(obrigatorias or ())
    cruas = {} if cruas is None else cruas
    classificar = classificar or _classe_da_falha
    plano = []
    ordem = []
    for t in tasks or ():
        if t and t not in ordem:
            plano.append((t, False))
            ordem.append(t)
    rodaram, falharam, puladas, travamentos = [], [], [], []
    puladas_por_memoria = []
    ausentes = []
    masks_por_task, recortes, primeira_trava = {}, {}, {}
    _grade_do_portao = []

    def _grade():
        if not _grade_do_portao:
            try:
                import radai_geom as _g
                _grade_do_portao.append(_g.Grade.de_sitk(ref))
            except Exception:
                _grade_do_portao.append(None)
        return _grade_do_portao[0]

    def _juntas():
        out = {}
        for t in ordem:
            out.update(masks_por_task.get(t) or {})
        return out

    def _critica(t):
        return _e_base(t) or t in obrig

    def _avisar(t, dados):
        if ao_terminar is not None:
            try:
                ao_terminar(t, dados)
            except Exception as e_cb:
                _log(jid, u"! lista de tasks: o gancho ao_terminar de `%s` "
                          u"falhou (%s: %s)" % (t, type(e_cb).__name__,
                                                str(e_cb)[:120]))

    i = 0
    while i < len(plano):
        t, retomada = plano[i]
        i += 1
        if not retomada and portao:
            motivo = portao_da_regiao(t, _juntas(), cruas=cruas,
                                      grade=_grade())
            if motivo:
                puladas.append({"task": t, "motivo": u"%s" % motivo})
                _log(jid, u"lista de tasks: `%s` pulada — %s" % (t, motivo))
                continue
        if not retomada and antes_de is not None:
            motivo = antes_de(t, _juntas(), cruas)
            if motivo:
                puladas.append({"task": t, "motivo": u"%s" % motivo})
                _log(jid, u"lista de tasks: `%s` pulada — %s" % (t, motivo))
                continue
        extra = dict(kw)
        extra.update(timeout_s=timeout_s, trava=trava, cruas=cruas)
        if retomada:
            extra["plano_menor"] = True
            _log(jid, u"TS %s: retomando a task travada — UMA vez, do zero, "
                      u"com o plano de memoria menor" % t)
        try:
            _rr = regiao_da_ram(t, _juntas(), ref, cruas=cruas)
        except Exception:
            _rr = None
        if _rr is not None:
            extra["regiao_ram"] = _rr
        ent = entrada_do_recorte(t, modo=modo)
        if recortar and (ent.get("medido")
                         or ent.get("lateral_pelo_corpo")):
            caixa, motivo_cx = caixa_de_recorte(t, _juntas(), ref, modo=modo,
                                                cruas=cruas)
            if caixa is not None:
                extra["caixa"] = caixa
                recortes[t] = dict((k, v) for k, v in caixa.items()
                                   if k != "zyx")
            else:
                _log(jid, u"TS %s: clip-box medido e NAO aplicado — %s"
                     % (t, motivo_cx))
        t0 = time.time()
        try:
            r = rodar(ref, t, device, jid, **extra)
        except Cancelado:
            raise
        except RecursoPrevisto as e:
            if _critica(t):
                raise
            seg = round(time.time() - t0, 1)
            pulada = pulada_por_memoria(e, t)
            puladas_por_memoria.append(pulada)
            _avisar(t, {"ok": False, "segundos": seg, "retomada": retomada,
                        "erro": str(e)[:300], "classe": "recurso",
                        "pulada_por_memoria": dict(pulada)})
            _log(jid, u"! TS %s PULADA por memoria nesta serie: pedia ~%s GiB "
                      u"e a estacao tinha %s GiB — o resto segue e e "
                      u"entregue sem ela" % (t, _gib_ou_q(pulada["pedia_gib"]),
                                              _gib_ou_q(pulada["livre_gib"])))
            continue
        except TaskTravada as e:
            seg = round(time.time() - t0, 1)
            _avisar(t, {"ok": False, "segundos": seg, "retomada": retomada,
                        "erro": str(e)[:300], "classe": "travou"})
            if not retomada:
                primeira_trava[t] = {"task": t, "motivo": e.motivo,
                                     "numeros": dict(e.numeros),
                                     "onde": e.onde}
                if retomar:
                    plano.append((t, True))
                    faltam = len(plano) - i - 1
                    _log(jid, u"! TS %s TRAVADA: adiada para o fim da lista "
                              u"(%d task(s) antes da retomada) — ela sera "
                              u"refeita UMA vez, com o plano de memoria menor"
                         % (t, faltam))
                    continue
                travamentos.append(dict(primeira_trava[t], retomada="nao"))
                if _critica(t):
                    raise
                falharam.append({"task": t, "erro": str(e)[:300],
                                 "classe": "travou"})
                _log(jid, u"! TS %s TRAVADA, sem retomada pedida: a serie sai "
                          u"sem ela" % t)
                continue
            travamentos.append(dict(primeira_trava.get(t) or {"task": t},
                                    retomada="travou"))
            if _critica(t):
                _log(jid, u"! TS %s TRAVOU DE NOVO na retomada, e ela e %s: a "
                          u"serie falha com o motivo"
                     % (t, u"a base" if _e_base(t) else u"obrigatoria"))
                raise TaskTravada(t, e.motivo, e.numeros, tentativa=2,
                                  onde=e.onde)
            falharam.append({"task": t, "erro": str(e)[:300],
                             "classe": "travou"})
            _log(jid, u"! TS %s TRAVOU DE NOVO na retomada: a serie sai sem "
                      u"ela (tasks_falharam)" % t)
            continue
        except Exception as e:
            seg = round(time.time() - t0, 1)
            classe = classificar(e)
            _avisar(t, {"ok": False, "segundos": seg, "retomada": retomada,
                        "erro": str(e)[:300], "classe": classe})
            if retomada:
                travamentos.append(dict(primeira_trava.get(t) or {"task": t},
                                        retomada="falhou"))
            if _critica(t):
                raise
            if ao_falhar is not None and ao_falhar(t, e):
                raise
            falharam.append({"task": t, "erro": str(e)[:300],
                             "classe": classe})
            _log(jid, u"! TS %s FALHOU (%s): a lista segue sem ela — %s"
                 % (t, classe, str(e)[:200]))
            continue
        masks_por_task[t] = r or {}
        rodaram.append(t)
        if getattr(r, "ausencia", None):
            ausentes.append({"task": t, "motivo": u"%s" % r.ausencia})
        _avisar(t, {"ok": True, "segundos": round(time.time() - t0, 1),
                    "retomada": retomada})
        if retomada:
            travamentos.append(dict(primeira_trava.get(t) or {"task": t},
                                    retomada="ok"))
            _log(jid, u"TS %s: a retomada terminou — a task destravou" % t)
        if depois_de is not None:
            novas = [n for n in (depois_de(t, _juntas(), cruas) or ())
                     if n and n not in ordem]
            if novas:
                plano[i:i] = [(n, False) for n in novas]
                ordem.extend(novas)
    return {"rodaram": rodaram, "falharam": falharam, "puladas": puladas,
            "masks": _juntas(), "cruas": cruas, "travamentos": travamentos,
            "recortes": recortes, "ausentes": ausentes,
            "tasks_puladas_por_memoria": puladas_por_memoria}


def _em_gib(mb):
    try:
        if mb is None:
            return None
        return round(float(mb) / 1024.0, 1)
    except (TypeError, ValueError):
        return None


def _gib_ou_q(v):
    return u"?" if v is None else (u"%.1f" % v).replace(".", ",")


def pulada_por_memoria(e, task=None):
    livre = getattr(e, "commit_livre_mb", None)
    if livre is None:
        livre = getattr(e, "livre_mb", None)
    return {"task": task or getattr(e, "task", None),
            "pedia_gib": _em_gib(getattr(e, "precisa_mb", None)),
            "livre_gib": _em_gib(livre)}


_CORES_FAMILIA = {
    "osso":       [241, 214, 145],
    "musculo":    [192, 104, 88],
    "arteria":    [216, 101, 79],
    "veia":       [90, 140, 210],
    "ar":         [182, 228, 255],
    "digestorio": [204, 150, 100],
    "urinario":   [140, 170, 80],
    "nervoso":    [244, 214, 49],
    "glandula":   [230, 130, 175],
    "cardiaco":   [190, 60, 60],
    "gordura":    [232, 220, 158],
    "outro":      [150, 170, 190],
}

_FAMILIA_POR_PALAVRA = (
    ("transversospinalis", "musculo"),
    ("spinal_cord", "nervoso"), ("spinal", "nervoso"), ("brain", "nervoso"),
    ("optic", "nervoso"), ("cerebell", "nervoso"), ("brainstem", "nervoso"),
    ("chiasm", "nervoso"), ("nerve", "nervoso"), ("cauda", "nervoso"),
    ("heart", "cardiaco"), ("pericard", "cardiaco"), ("atrial", "cardiaco"),
    ("ventricle_left", "cardiaco"), ("ventricle_right", "cardiaco"),
    ("myocard", "cardiaco"), ("atrium", "cardiaco"),
    ("lung", "ar"), ("trachea", "ar"), ("bronch", "ar"), ("airway", "ar"),
    ("sinus", "ar"), ("nasal_cavity", "ar"), ("pharynx", "ar"),
    ("larynx", "ar"),
    ("aorta", "arteria"), ("artery", "arteria"), ("_arteries", "arteria"),
    ("carotid", "arteria"), ("iliac_artery", "arteria"),
    ("subclavian_artery", "arteria"), ("pulmonary_artery", "arteria"),
    ("brachiocephalic_trunk", "arteria"), ("celiac_trunk", "arteria"),
    ("vein", "veia"), ("vena_cava", "veia"), ("portal", "veia"),
    ("iliac_vena", "veia"), ("azygos", "veia"), ("lung_vessels", "veia"),
    ("kidney", "urinario"), ("urinary_bladder", "urinario"),
    ("ureter", "urinario"), ("renal", "urinario"),
    ("esophagus", "digestorio"), ("stomach", "digestorio"),
    ("duodenum", "digestorio"), ("small_bowel", "digestorio"),
    ("colon", "digestorio"), ("rectum", "digestorio"),
    ("anal_canal", "digestorio"), ("anus", "digestorio"),
    ("liver", "digestorio"),
    ("gallbladder", "digestorio"), ("pancreas", "digestorio"),
    ("spleen", "digestorio"), ("intestine", "digestorio"),
    ("thyroid", "glandula"), ("adrenal", "glandula"), ("parotid", "glandula"),
    ("submandibular", "glandula"), ("prostate", "glandula"),
    ("seminal", "glandula"), ("lacrimal", "glandula"), ("gland", "glandula"),
    ("pituitary", "glandula"), ("breast", "glandula"), ("uter", "glandula"),
    ("ovar", "glandula"),
    ("rib", "osso"), ("vertebra", "osso"), ("sternum", "osso"),
    ("clavicula", "osso"), ("scapula", "osso"), ("humerus", "osso"),
    ("femur", "osso"), ("hip", "osso"), ("sacrum", "osso"),
    ("iliac_crest", "osso"), ("skull", "osso"), ("costal_cartilage", "osso"), ("mandible", "osso"),
    ("patella", "osso"), ("tibia", "osso"), ("fibula", "osso"),
    ("carpal", "osso"), ("metacarpal", "osso"), ("phalan", "osso"),
    ("tarsal", "osso"), ("metatarsal", "osso"), ("radius", "osso"),
    ("ulna", "osso"), ("bone", "osso"),
    ("gluteus", "musculo"), ("iliopsoas", "musculo"), ("autochthon", "musculo"),
    ("muscle", "musculo"), ("masseter", "musculo"), ("pterygoid", "musculo"),
    ("constrictor", "musculo"), ("sternocleido", "musculo"),
    ("digastric", "musculo"), ("mylohyoid", "musculo"),
    ("rectus_abdominis", "musculo"), ("oblique", "musculo"),
    ("erector_spinae", "musculo"), ("quadratus_lumborum", "musculo"),
    ("psoas", "musculo"), ("trapezius", "musculo"),
    ("latissimus", "musculo"), ("serratus", "musculo"),
    ("pectoralis", "musculo"),
    ("subcutaneous_fat", "gordura"), ("visceral_fat", "gordura"),
    ("torso_fat", "gordura"), ("_fat", "gordura"),
    ("eye", "nervoso"), ("lens", "nervoso"), ("retina", "nervoso"),
)

_CORES = {
    "spinal_cord":       [244, 214, 49],
    "brain":             [176, 136, 255],
    "eye":               [0, 229, 255],
    "lens":              [120, 245, 255],
    "optic":             [255, 153, 51],
    "parotid":           [0, 221, 160],
    "submandibular":     [90, 215, 190],
    "thyroid":           [62, 162, 114],
    "lung":              [125, 190, 245],
    "trachea":           [182, 228, 255],
    "heart":             [190, 40, 40],
    "pericardium":       [230, 120, 120],
    "aorta":             [216, 60, 50],
    "vena_cava":         [70, 120, 200],
    "esophagus":         [211, 171, 143],
    "stomach":           [255, 238, 85],
    "liver":             [160, 82, 45],
    "gallbladder":       [140, 190, 90],
    "pancreas":          [210, 232, 67],
    "spleen":            [144, 112, 204],
    "kidney_left":       [90, 200, 110],
    "kidney_right":      [70, 175, 95],
    "kidney":            [80, 188, 102],
    "urinary_bladder":   [255, 255, 0],
    "rectum":            [180, 120, 80],
    "anus":              [150, 95, 70],
    "iliac_crest_left":  [144, 238, 144],
    "iliac_crest_right": [152, 251, 152],
    "colon":             [200, 150, 100],
    "small_bowel":       [215, 175, 130],
    "duodenum":          [225, 190, 145],
    "prostate":          [230, 130, 175],
    "seminal":           [240, 165, 200],
    "femur":             [235, 220, 175],
    "hip":               [241, 214, 145],
    "sacrum":            [230, 205, 150],
    "vertebra":          [225, 205, 160],
    "rib":               [245, 230, 195],
    "sternum":           [240, 222, 180],
    "clavicula":         [238, 218, 170],
    "scapula":           [232, 212, 165],
    "humerus":           [236, 216, 172],
    "gluteus":           [192, 104, 88],
    "iliopsoas":         [180, 96, 82],
    "autochthon":        [172, 92, 78],
    "adrenal_gland":     [235, 150, 190],
    "thyroid_gland":     [62, 162, 114],
    "great_arteries":    [255, 100, 100],
    "great_veins":       [68, 136, 255],
    "skin":              [247, 241, 209],
}

def _cores_dos_niveis():
    try:
        import radai_hnlnl as _hn
        return (dict(_hn.CORES_DOS_NIVEIS), dict(_hn.CORES_DA_PAROTIDA_TS))
    except Exception:
        return {}, {}


_CORES_NIVEIS, _CORES_PAROTIDA_TS = _cores_dos_niveis()
CORES_A_CONFERIR = tuple(sorted(list(_CORES) + list(_CORES_NIVEIS)
                                + [k + "_ts" for k in _CORES_PAROTIDA_TS]))


def cores_a_conferir():
    return CORES_A_CONFERIR


def familia_de(n):
    for palavra, fam in _FAMILIA_POR_PALAVRA:
        if palavra in n:
            return fam
    return "outro"


def _cor_derivada(n, fam, base=None, giro=44.0):
    if base is None:
        base = _CORES_FAMILIA.get(fam, _CORES_FAMILIA["outro"])
    h = 2166136261
    for ch in n:
        h = ((h ^ ord(ch)) * 16777619) & 0xFFFFFFFF
    h ^= h >> 16
    h = (h * 0x85EBCA6B) & 0xFFFFFFFF
    h ^= h >> 13
    h = (h * 0xC2B2AE35) & 0xFFFFFFFF
    h ^= h >> 16
    lum = ((h >> 8) & 0xFF) / 255.0 * (2.0 * giro) - giro
    fora = []
    for i in range(3):
        jit = ((h >> (i * 5)) & 0x1F) / 31.0 * 16.0 - 8.0
        fora.append(max(0, min(255, int(round(base[i] + lum + jit)))))
    return fora


_CLARO = 0.75

_ESCURO = 1.0


def _color(nm, do_nv=False):
    # GUARDA: os níveis cervicais têm tabela própria, e nunca cor por hash.
    if str(nm) in _CORES_NIVEIS:
        base = list(_CORES_NIVEIS[str(nm)])
        if do_nv:
            return [int(round(v + (255 - v) * _CLARO)) for v in base]
        return base
    n = _nomes.canonico(nm).lower()
    base, chave = None, ""
    for forma in [n] + [f.lower() for f in _nomes.formas(nm) if f.lower() != n]:
        for k in sorted(_CORES, key=len, reverse=True):
            if k in forma:
                base, chave = _CORES[k], k
                break
        if base is not None:
            break
    if base is None:
        base = _cor_derivada(n, familia_de(n))
    elif n != chave:
        base = _cor_derivada(n, "", base=base, giro=28.0)
    if do_nv:
        return [int(round(v + (255 - v) * _CLARO)) for v in base]
    return [int(round(v * _ESCURO)) for v in base]


TG263 = {
    'aorta': 'A_Aorta',
    'brachiocephalic_trunk': 'A_Innominate',
    'brachiocephalic_vein_left': 'V_Innominate_L',
    'brachiocephalic_vein_right': 'V_Innominate_R',
    'common_carotid_artery_left': 'A_Carotid_L',
    'common_carotid_artery_right': 'A_Carotid_R',
    'costal_cartilages': 'Cartilage_Costal',
    'hypopharynx': 'Pharynx_Hypo',
    'inferior_vena_cava': 'V_Venacava_I',
    'nasal_cavity_left': 'Cavity_Nasal_L',
    'nasal_cavity_right': 'Cavity_Nasal_R',
    'nasopharynx': 'Pharynx_Naso',
    'oropharynx': 'Pharynx_Oro',
    'portal_vein_and_splenic_vein': 'V_Portal_Splenic',
    'pulmonary_vein': 'V_Pulmonary',
    'rib_left_1': 'Rib01_L',
    'rib_left_10': 'Rib10_L',
    'rib_left_11': 'Rib11_L',
    'rib_left_12': 'Rib12_L',
    'rib_left_2': 'Rib02_L',
    'rib_left_3': 'Rib03_L',
    'rib_left_4': 'Rib04_L',
    'rib_left_5': 'Rib05_L',
    'rib_left_6': 'Rib06_L',
    'rib_left_7': 'Rib07_L',
    'rib_left_8': 'Rib08_L',
    'rib_left_9': 'Rib09_L',
    'rib_right_1': 'Rib01_R',
    'rib_right_10': 'Rib10_R',
    'rib_right_11': 'Rib11_R',
    'rib_right_12': 'Rib12_R',
    'rib_right_2': 'Rib02_R',
    'rib_right_3': 'Rib03_R',
    'rib_right_4': 'Rib04_R',
    'rib_right_5': 'Rib05_R',
    'rib_right_6': 'Rib06_R',
    'rib_right_7': 'Rib07_R',
    'rib_right_8': 'Rib08_R',
    'rib_right_9': 'Rib09_R',
    'subclavian_artery_left': 'A_Subclavian_L',
    'subclavian_artery_right': 'A_Subclavian_R',
    'superior_vena_cava': 'V_Venacava_S',
    'ventricle': 'Ventricle',
    'vertebrae_C1': 'Vertebrae_C1',
    'vertebrae_C2': 'Vertebrae_C2',
    'vertebrae_C3': 'Vertebrae_C3',
    'vertebrae_C4': 'Vertebrae_C4',
    'vertebrae_C5': 'Vertebrae_C5',
    'vertebrae_C6': 'Vertebrae_C6',
    'vertebrae_C7': 'Vertebrae_C7',
    'vertebrae_L1': 'Vertebrae_L1',
    'vertebrae_L2': 'Vertebrae_L2',
    'vertebrae_L3': 'Vertebrae_L3',
    'vertebrae_L4': 'Vertebrae_L4',
    'vertebrae_L5': 'Vertebrae_L5',
    'vertebrae_T1': 'Vertebrae_T1',
    'vertebrae_T10': 'Vertebrae_T10',
    'vertebrae_T11': 'Vertebrae_T11',
    'vertebrae_T12': 'Vertebrae_T12',
    'vertebrae_T2': 'Vertebrae_T2',
    'vertebrae_T3': 'Vertebrae_T3',
    'vertebrae_T4': 'Vertebrae_T4',
    'vertebrae_T5': 'Vertebrae_T5',
    'vertebrae_T6': 'Vertebrae_T6',
    'vertebrae_T7': 'Vertebrae_T7',
    'vertebrae_T8': 'Vertebrae_T8',
    'vertebrae_T9': 'Vertebrae_T9',
    "seminal_vesicles": "SeminalVes",
    "colon_sigmoid": "Colon_Sigmoid",
    "bowel_bag": "Spc_Bowel",
    "larynx": "Larynx",
    "spinal_canal": "SpinalCanal",
    "breast_left": "Breast_L",
    "breast_right": "Breast_R",
    "rectus_abdominis_left": "Musc_Rectus_L",
    "rectus_abdominis_right": "Musc_Rectus_R",
    "pectoralis_major_left": "Musc_PecMaj_L",
    "pectoralis_major_right": "Musc_PecMaj_R",
    "serratus_anterior_left": "Musc_SerAnt_L",
    "serratus_anterior_right": "Musc_SerAnt_R",
    "latissimus_dorsi_left": "Musc_LatDor_L",
    "latissimus_dorsi_right": "Musc_LatDor_R",
    "trapezius_left": "Musc_Trapez_L",
    "trapezius_right": "Musc_Trapez_R",
    "external_oblique_left": "Musc_ObExt_L",
    "external_oblique_right": "Musc_ObExt_R",
    "internal_oblique_left": "Musc_ObInt_L",
    "internal_oblique_right": "Musc_ObInt_R",
    "erector_spinae_left": "Musc_ErSpin_L",
    "erector_spinae_right": "Musc_ErSpin_R",
    "transversospinalis_left": "Musc_TrSpin_L",
    "transversospinalis_right": "Musc_TrSpin_R",
    "psoas_major_left": "Musc_Psoas_L",
    "psoas_major_right": "Musc_Psoas_R",
    "quadratus_lumborum_left": "Musc_QLumb_L",
    "quadratus_lumborum_right": "Musc_QLumb_R",
    "rectum": "Rectum",
    "anal_canal": "Canal_Anal",
    "gluteus_maximus_left": "Glute_Max_L",
    "gluteus_maximus_right": "Glute_Max_R",
    "gluteus_medius_left": "Glute_Med_L",
    "gluteus_medius_right": "Glute_Med_R",
    "gluteus_minimus_left": "Glute_Min_L",
    "gluteus_minimus_right": "Glute_Min_R",
    "iliopsoas_left": "Musc_Iliopsoas_L",
    "iliopsoas_right": "Musc_Iliopsoas_R",
    "iliac_artery_left": "A_Iliac_L",
    "iliac_artery_right": "A_Iliac_R",
    "iliac_vena_left": "V_Iliac_L",
    "iliac_vena_right": "V_Iliac_R",
    "vertebrae_S1": "Vertebrae_S1",
    "vertebrae_L6": "Vertebrae_L6",
    "hip_left": "Bone_Pelvic_L",
    "hip_right": "Bone_Pelvic_R",
    "brain": "Brain", "brain_brainstem": "Brainstem", "brain_cerebellum": "Cerebellum",
    "spinal_cord": "SpinalCord", "skull": "Skull",
    "mandible": "Bone_Mandible",
    "teeth_upper": "Teeth_Upper", "teeth_lower": "Teeth_Lower",
    "sinus_maxillary": "Sinus_Maxill", "sinus_frontal": "Sinus_Frontal",
    "eyeball_left": "Eyeball_L", "eyeball_right": "Eyeball_R",
    "rectus_lateral_left": "Musc_ReLat_L", "rectus_lateral_right": "Musc_ReLat_R",
    "rectus_medial_left": "Musc_ReMed_L", "rectus_medial_right": "Musc_ReMed_R",
    "rectus_superior_left": "Musc_ReSup_L", "rectus_superior_right": "Musc_ReSup_R",
    "rectus_inferior_left": "Musc_ReInf_L", "rectus_inferior_right": "Musc_ReInf_R",
    "oblique_superior_left": "Musc_ObSup_L", "oblique_superior_right": "Musc_ObSup_R",
    "oblique_inferior_left": "Musc_ObInf_L", "oblique_inferior_right": "Musc_ObInf_R",
    "levator_palpebrae_left": "Musc_LevPalp_L",
    "levator_palpebrae_right": "Musc_LevPalp_R",
    "parotid_gland_left": "Parotid_L", "parotid_gland_right": "Parotid_R",
    "submandibular_gland_left": "Glnd_Submand_L", "submandibular_gland_right": "Glnd_Submand_R",
    "eye_left": "Eye_L", "eye_right": "Eye_R",
    "eye_lens_left": "Lens_L", "eye_lens_right": "Lens_R",
    "optic_nerve_left": "OpticNrv_L", "optic_nerve_right": "OpticNrv_R",
    "thyroid_gland": "Glnd_Thyroid", "esophagus": "Esophagus", "trachea": "Trachea",
    "pericardium": "Pericardium",
    "pleural_effusion": "PleuralEff",
    "pleural_effusion_left": "PleuralEff_L",
    "pleural_effusion_right": "PleuralEff_R",
    "pericardial_effusion": "PericardEff",
    "mediastinum": "Mediastinum",
    "thoracic_cavity": "Cavity_Thoracic",
    "abdominal_cavity": "Cavity_Abdominal",
    "pharyngeal_constrictor_superior": "Musc_Constrict_S",
    "pharyngeal_constrictor_middle": "Musc_Constrict_M",
    "pharyngeal_constrictor_inferior": "Musc_Constrict_I",
    "internal_carotid_artery_left": "A_CarotidInt_L",
    "internal_carotid_artery_right": "A_CarotidInt_R",
    "internal_jugular_vein_left": "V_Jugular_L",
    "internal_jugular_vein_right": "V_Jugular_R",
    "masseter_left": "Musc_Masseter_L",
    "masseter_right": "Musc_Masseter_R",
    "temporalis_left": "Musc_Temporalis_L",
    "temporalis_right": "Musc_Temporalis_R",
    "lateral_pterygoid_left": "Musc_PtgLat_L",
    "lateral_pterygoid_right": "Musc_PtgLat_R",
    "medial_pterygoid_left": "Musc_PtgMed_L",
    "medial_pterygoid_right": "Musc_PtgMed_R",
    "digastric_left": "Musc_Digastric_L",
    "digastric_right": "Musc_Digastric_R",
    "tongue": "Tongue",
    "larynx_air": "Larynx_Air",
    "thyroid_cartilage": "Cartlg_Thyroid",
    "cricoid_cartilage": "Cartlg_Cricoid",
    "hyoid": "Bone_Hyoid",
    "soft_palate": "Palate_Soft", "hard_palate": "Hardpalate",
    "nasal_cavity": "Cavity_Nasal",
    "auditory_canal_left": "EAC_L", "auditory_canal_right": "EAC_R",
    "lung_left": "Lung_L", "lung_right": "Lung_R", "heart": "Heart",
    "heart_model": "Heart_Model",
    "femur_oar_left": "Femur_OAR_L", "femur_oar_right": "Femur_OAR_R",
    "iliac_crest_left": "IliacCrest_L", "iliac_crest_right": "IliacCrest_R",
    "anus": "Anus",
    "bag_bowel": "Bag_Bowel",
    "bag_bowel_oar": "Bag_Bowel_OAR",
    "lung_upper_lobe_right": "Lung_RUL", "lung_middle_lobe_right": "Lung_RML",
    "lung_lower_lobe_right": "Lung_RLL", "lung_upper_lobe_left": "Lung_LUL",
    "lung_lower_lobe_left": "Lung_LLL",
    "carotids": "A_Carotid",
    "great_arteries": "GreatArteries",
    "great_veins": "GreatVeins",
    "gluteus_muscles": "Musc_Gluteus",
    "pelvic_muscles": "Muscles",
    "bone_pelvic": "Bone_Pelvic",
    "atrial_appendage_left": "AtrialApp_L",
    "sternum": "Sternum",
    "ribs_left": "Ribs_L", "ribs_right": "Ribs_R",
    "liver": "Liver", "spleen": "Spleen", "stomach": "Stomach", "pancreas": "Pancreas",
    "gallbladder": "Gallbladder",
    "kidney_left": "Kidney_L", "kidney_right": "Kidney_R",
    "kidney_cyst_left": "Kidney_Cyst_L",
    "kidney_cyst_right": "Kidney_Cyst_R",
    "adrenal_gland_left": "Glnd_Adrenal_L", "adrenal_gland_right": "Glnd_Adrenal_R",
    "small_intestine": "Bowel_Small", "colon": "Bowel_Large", "duodenum": "Duodenum",
    "urinary_bladder": "Bladder", "prostate": "Prostate",
    "femur_left": "Femur_L", "femur_right": "Femur_R", "sacrum": "Sacrum",
    "vertebrae_cervical": "Vertebrae_C", "vertebrae_thoracic": "Vertebrae_T",
    "vertebrae_lumbar": "Vertebrae_L",
    "thalamus": "Thalamus", "frontal_lobe": "Lobe_Frontal",
    "parietal_lobe": "Lobe_Parietal", "occipital_lobe": "Lobe_Occipital",
    "temporal_lobe": "Lobe_Temporal",
    "optic_chiasm": "OpticChiasm", "cerebellum": "Cerebellum",
    "brain_ventricles": "Ventricles", "brain_midline": "Brain_Midline",
}

TG263_A_CONFERIR = {
    "brain_ventricles", "brain_midline",
    "kidney_cyst_left", "kidney_cyst_right",
    "pleural_effusion", "pleural_effusion_left", "pleural_effusion_right",
    "pericardial_effusion",

    "heart_model", "femur_oar_left", "femur_oar_right",
    "iliac_crest_left", "iliac_crest_right", "anus",

    "pelvic_muscles", "bone_pelvic", "atrial_appendage_left",
    "bag_bowel_oar",


    "larynx_air",
    "thyroid_cartilage",
    "cricoid_cartilage",
    "lateral_pterygoid_left", "lateral_pterygoid_right",
    "medial_pterygoid_left", "medial_pterygoid_right",

    "teeth_upper", "teeth_lower", "sinus_maxillary", "sinus_frontal",
    "eyeball_left", "eyeball_right",
    "rectus_lateral_left", "rectus_lateral_right",
    "rectus_medial_left", "rectus_medial_right",
    "rectus_superior_left", "rectus_superior_right",
    "rectus_inferior_left", "rectus_inferior_right",
    "oblique_superior_left", "oblique_superior_right",
    "oblique_inferior_left", "oblique_inferior_right",
    "levator_palpebrae_left", "levator_palpebrae_right",
    "hyoid",
    "tongue",

    "colon_sigmoid",
    "bowel_bag",


    "sternum",


    "rectus_abdominis_left",
    "rectus_abdominis_right",
    "pectoralis_major_left", "pectoralis_major_right",
    "serratus_anterior_left", "serratus_anterior_right",
    "latissimus_dorsi_left", "latissimus_dorsi_right",
    "trapezius_left", "trapezius_right",
    "external_oblique_left", "external_oblique_right",
    "internal_oblique_left", "internal_oblique_right",
    "erector_spinae_left", "erector_spinae_right",
    "transversospinalis_left", "transversospinalis_right",
    "psoas_major_left", "psoas_major_right",
    "quadratus_lumborum_left", "quadratus_lumborum_right",
    "gluteus_maximus_left",
    "gluteus_maximus_right",
    "gluteus_medius_left",
    "gluteus_medius_right",
    "gluteus_minimus_left",
    "gluteus_minimus_right",
    "iliopsoas_left",
    "iliopsoas_right",




    "vertebrae_S1",



  "hard_palate",  "auditory_canal_left",
    "auditory_canal_right",   "ribs_left", "ribs_right",
 "vertebrae_cervical", "vertebrae_thoracic", "vertebrae_lumbar",
   

 "thoracic_cavity", "abdominal_cavity",

    'aorta',
    'brachiocephalic_trunk',
    'brachiocephalic_vein_left',
    'brachiocephalic_vein_right',
    'common_carotid_artery_left',
    'common_carotid_artery_right',
    'costal_cartilages',
    'hypopharynx',
    'inferior_vena_cava',
    'nasal_cavity_left',
    'nasal_cavity_right',
    'nasopharynx',
    'oropharynx',
    'portal_vein_and_splenic_vein',
    'pulmonary_vein',
    'rib_left_1',
    'rib_left_10',
    'rib_left_11',
    'rib_left_12',
    'rib_left_2',
    'rib_left_3',
    'rib_left_4',
    'rib_left_5',
    'rib_left_6',
    'rib_left_7',
    'rib_left_8',
    'rib_left_9',
    'rib_right_1',
    'rib_right_10',
    'rib_right_11',
    'rib_right_12',
    'rib_right_2',
    'rib_right_3',
    'rib_right_4',
    'rib_right_5',
    'rib_right_6',
    'rib_right_7',
    'rib_right_8',
    'rib_right_9',
    'subclavian_artery_left',
    'subclavian_artery_right',
    'superior_vena_cava',
    'ventricle',
    'vertebrae_C1',
    'vertebrae_C2',
    'vertebrae_C3',
    'vertebrae_C4',
    'vertebrae_C5',
    'vertebrae_C6',
    'vertebrae_C7',
    'vertebrae_L1',
    'vertebrae_L2',
    'vertebrae_L3',
    'vertebrae_L4',
    'vertebrae_L5',
    'vertebrae_T1',
    'vertebrae_T10',
    'vertebrae_T11',
    'vertebrae_T12',
    'vertebrae_T2',
    'vertebrae_T3',
    'vertebrae_T4',
    'vertebrae_T5',
    'vertebrae_T6',
    'vertebrae_T7',
    'vertebrae_T8',
    'vertebrae_T9',
}



RESSALVA_DE_ROI = {}

try:
    import radai_moose as _moose

    TG263.update(_moose.TG263_MOOSE)
    TG263_A_CONFERIR |= set(_moose.TG263_MOOSE)
except Exception:
    pass

SO_COMPARACAO = frozenset()

SUFIXO_AI = "_ai"
SUFIXO_NV = "_nv"

SUFIXO_TS = "_ts"
PREFIXO_NV = "nv:"

SUFIXO_POR_MOTOR = {
    "cads": "_cds",
    "nv": SUFIXO_NV,
    "ts": SUFIXO_TS,
}


def sufixo_de_procedencia(chave, origem=None, motor_alt="",
                          sufixo_do_conjunto=SUFIXO_AI):
    if motor_alt:
        return SUFIXO_POR_MOTOR.get(motor_alt, "_" + motor_alt[:3])
    if str(chave).startswith(PREFIXO_NV):
        return SUFIXO_NV
    marca = (origem or {}).get(chave)
    if marca == "ts":
        return SUFIXO_TS
    return sufixo_do_conjunto


LIMITE_NOME = 16
_QUALIFICADORES = ("_L", "_R", "_S", "_M", "_I")
_NIVEL = re.compile(r"_([A-Za-z]?\d+)$")


def tg263_a_conferir():
    return sorted((ts, TG263[ts]) for ts in TG263_A_CONFERIR if ts in TG263)


TG263_SO_NOSSO = {
    "prostate": "ProstaticArea",
    # GUARDA: a parotida do VIII sai com o nome da do TS, que ela substitui
    # no OAR.
    "parotid_lnl_left": "Parotid_L",
    "parotid_lnl_right": "Parotid_R",
}


def _alias_do_rotulo_cru():
    candidatos = {}
    for amigavel, por_task in TS_MAP.items():
        if not isinstance(por_task, dict):
            continue
        partes = set()
        for lista in por_task.values():
            partes.update(lista)
        if len(partes) != 1:
            continue
        cru = partes.pop()
        if cru == amigavel:
            continue
        candidatos.setdefault(cru, set()).add(amigavel)
    return {cru: next(iter(a)) for cru, a in candidatos.items()
            if len(a) == 1 and cru not in TS_MAP}


ALIAS_DO_CRU = _alias_do_rotulo_cru()


def nome_clinico(nome_amigavel, usados=None, sufixo=SUFIXO_AI, limite=LIMITE_NOME):
    base = TG263_SO_NOSSO.get(nome_amigavel) if sufixo == SUFIXO_AI else None
    if base is None:
        base = TG263.get(nome_amigavel)
    if base is None and sufixo == SUFIXO_AI:
        try:
            base = _nomes.procurar(TG263, nome_amigavel)
        except NameError:
            base = TG263.get(ALIAS_DO_CRU.get(nome_amigavel, ""))
    if base is None:
        base = nome_amigavel

    qualificador = ""
    for marca in _QUALIFICADORES:
        if base.endswith(marca):
            base, qualificador = base[:-len(marca)], marca
            break
    else:
        if sufixo == SUFIXO_AI or len(base) + len(sufixo) > limite:
            for longo, curto in (("_left", "_L"), ("_right", "_R")):
                if base.endswith(longo):
                    base, qualificador = base[:-len(longo)], curto
                    break

    achado = _NIVEL.search(base)
    if achado:
        base, nivel = base[:achado.start()], "_" + achado.group(1)
    else:
        nivel = ""
    cauda = nivel + qualificador

    def montar(extra=""):
        espaco = max(1, limite - len(sufixo) - len(cauda) - len(extra))
        raiz = base[:espaco].rstrip("_") if len(base) > espaco else base
        return raiz + extra + cauda + sufixo

    nome = montar()
    if usados is None:
        return nome
    if nome not in usados:
        usados.add(nome)
        return nome
    for k in range(2, 100):
        cand = montar(str(k))
        if cand not in usados:
            usados.add(cand)
            return cand
    usados.add(nome)
    return nome


MIN_PONTOS_CONTORNO = 3


def _espacamento_no_plano(clean_dir, padrao=1.0):
    try:
        files = sort_dcm([str(f) for f in Path(clean_dir).glob("*.dcm")])
        if not files:
            return padrao, padrao
        ref = pydicom.dcmread(files[len(files) // 2], stop_before_pixels=True,
                              force=True)
        ps = [float(v) for v in getattr(ref, "PixelSpacing", [padrao, padrao])]
        return (ps[1] if len(ps) > 1 else padrao), ps[0]
    except Exception:
        return padrao, padrao


def _suavizar_contornos(ds, dxdy=None, suavizar=True, formatados=None,
                        prontos=None):
    if not hasattr(ds, "ROIContourSequence"):
        return 0
    try:
        import radai_geom
    except Exception:
        return 0
    prontos = prontos or ()
    feitos = 0
    for rc in ds.ROIContourSequence:
        lidos = {}
        for c in getattr(rc, "ContourSequence", None) or []:
            dados = getattr(c, "ContourData", None)
            if not dados or id(c) in prontos:
                continue
            try:
                v = np.asarray([float(x) for x in dados], dtype=np.float64)
            except Exception:
                continue
            if v.size % 3 or v.size // 3 < 3:
                continue
            lidos[id(c)] = v.reshape(-1, 3)
        furos = set()
        if dxdy:
            try:
                furos = _furos_da_roi(rc, lidos)
            except Exception:
                furos = set()
        for c in getattr(rc, "ContourSequence", None) or []:
            p = lidos.get(id(c))
            if p is None:
                continue
            try:
                xy = p[:, :2]
                if dxdy:
                    xy = radai_geom.expandir_meio_pixel(
                        xy, dxdy[0], dxdy[1], furo=(id(c) in furos))
                if suavizar and len(xy) >= radai_geom.MIN_PONTOS_SUAVIZAR:
                    xy = radai_geom.suavizar_poligono(xy)
                elif not dxdy:
                    continue
                if xy.shape != p[:, :2].shape:
                    continue
                p[:, :2] = xy
                if formatados is not None:
                    c.ContourData = ["%.4f" % float(x) for x in p.ravel()]
                    formatados.add(id(c))
                else:
                    c.ContourData = [float(x) for x in p.ravel()]
                feitos += 1
            except Exception:
                continue
    return feitos


DECIMACAO_FAST_MM = 0.2
MIN_PONTOS_DECIMADO = 3

AREA_MINIMA_DECIMADA_MM2 = 100.0
PERDA_MAXIMA_DECIMACAO = 0.01

MEDIDA_DO_FAST_CONTRA_O_AUTO = {
    "fonte": u"duas TC de torax de teste, o AUTO e o FAST na mesma serie",
    "series": 2, "espessura_mm": 5.0,
    "decimacao": {"tol_mm": 0.2, "min_pontos": 3, "area_min_mm2": 100.0,
                  "perda_max": 0.01},
    "dsc_min": 0.9697, "volume_dif_max_pct": 4.09,
    "estrutura_pior": "GreatVeins_ai", "volume_voxel_max_pct": 1.78,
}


def _decimar_contornos(ds, tol_mm, minimo=MIN_PONTOS_DECIMADO,
                       area_minima=AREA_MINIMA_DECIMADA_MM2,
                       perda_maxima=PERDA_MAXIMA_DECIMACAO, poupar_rois=None):
    import radai_geom
    laudo = {"tol_mm": float(tol_mm), "contornos": 0, "antes": 0,
             "depois": 0, "por_roi": {}, "poupados_area": 0,
             "poupados_perda": 0, "poupados_delgadas": 0}
    if not hasattr(ds, "ROIContourSequence") or not tol_mm or tol_mm <= 0:
        return laudo
    poupar_rois = set(poupar_rois or ())
    for rc in ds.ROIContourSequence:
        num = int(getattr(rc, "ReferencedROINumber", -1))
        if num in poupar_rois:
            laudo["poupados_delgadas"] += len(
                getattr(rc, "ContourSequence", None) or [])
            continue
        pa = pd_ = 0
        aa = ad = 0.0
        for c in getattr(rc, "ContourSequence", None) or []:
            dados = getattr(c, "ContourData", None)
            if not dados:
                continue
            try:
                v = np.asarray([float(x) for x in dados], dtype=np.float64)
                if v.size % 3 or v.size // 3 < 3:
                    continue
                p = v.reshape(-1, 3)
                a_p = radai_geom.area_poligono(p)
                q = p
                if area_minima and a_p < float(area_minima):
                    laudo["poupados_area"] += 1
                else:
                    idx = radai_geom.douglas_peucker_fechado(p, tol_mm,
                                                             minimo=minimo)
                    q = p[idx]
                    a_q = radai_geom.area_poligono(q)
                    if (perda_maxima is not None and a_p > 0
                            and abs(a_q / a_p - 1.0) > float(perda_maxima)):
                        laudo["poupados_perda"] += 1
                        q = p
                pa += p.shape[0]
                pd_ += q.shape[0]
                aa += a_p
                ad += radai_geom.area_poligono(q)
                laudo["contornos"] += 1
                if q.shape[0] != p.shape[0]:
                    c.ContourData = ["%.4f" % float(x) for x in q.ravel()]
                    c.NumberOfContourPoints = int(q.shape[0])
            except Exception:
                continue
        laudo["antes"] += pa
        laudo["depois"] += pd_
        laudo["por_roi"][num] = (pa, pd_, aa, ad)
    return laudo


AREA_MINIMA_DO_CONTORNO_MM2 = 0.01
TOLERANCIA_DO_VERTICE_MM = 5e-5


def _sem_vertice_repetido(p):
    p = np.asarray(p, dtype=np.float64)
    if len(p) < 2:
        return p
    passo = np.abs(np.diff(p[:, :2], axis=0)).max(axis=1)
    q = p[np.concatenate([[True], passo > TOLERANCIA_DO_VERTICE_MM])]
    while (len(q) > 1 and np.abs(q[-1, :2] - q[0, :2]).max()
           <= TOLERANCIA_DO_VERTICE_MM):
        q = q[:-1]
    return q


def contorno_degenerado(p):
    q = _sem_vertice_repetido(p)
    if len(q) < MIN_PONTOS_CONTORNO:
        return True
    return abs(_area_assinada(q[:, :2])) < AREA_MINIMA_DO_CONTORNO_MM2


def cruza_a_si_mesmo(xy):
    a = np.asarray(xy, dtype=np.float64)[:, :2]
    n = len(a)
    if n < 4:
        return False
    b = np.roll(a, -1, axis=0)
    x0, x1 = np.minimum(a[:, 0], b[:, 0]), np.maximum(a[:, 0], b[:, 0])
    y0, y1 = np.minimum(a[:, 1], b[:, 1]), np.maximum(a[:, 1], b[:, 1])
    ordem = np.argsort(x0, kind="stable")
    ate = np.searchsorted(x0[ordem], x1[ordem], side="right")
    quantos = np.maximum(ate - np.arange(n) - 1, 0)
    inicio = 0
    while inicio < n:
        fim, soma = inicio, 0
        while fim < n and (soma + quantos[fim] <= 2000000 or fim == inicio):
            soma += int(quantos[fim])
            fim += 1
        q = quantos[inicio:fim]
        if soma:
            ii = np.repeat(np.arange(inicio, fim), q)
            desl = np.arange(soma) - np.repeat(np.cumsum(q) - q, q)
            I, J = ordem[ii], ordem[ii + 1 + desl]
            dif = np.abs(I - J)
            m = ((y0[I] <= y1[J]) & (y0[J] <= y1[I])
                 & (dif != 1) & (dif != n - 1))
            if m.any():
                I, J = I[m], J[m]
                p1, p2, p3, p4 = a[I], b[I], a[J], b[J]

                def _giro(p, q_, r):
                    return ((q_[:, 0] - p[:, 0]) * (r[:, 1] - p[:, 1])
                            - (q_[:, 1] - p[:, 1]) * (r[:, 0] - p[:, 0]))
                o1, o2 = _giro(p1, p2, p3), _giro(p1, p2, p4)
                o3, o4 = _giro(p3, p4, p1), _giro(p3, p4, p2)
                nulo = ((np.abs(o1) < 1e-9) | (np.abs(o2) < 1e-9)
                        | (np.abs(o3) < 1e-9) | (np.abs(o4) < 1e-9))
                if np.any((o1 * o2 < 0) & (o3 * o4 < 0) & ~nulo):
                    return True
        inicio = fim
    return False


def _caixa_do_pixel(xs, ys, z, dx, dy):
    x0, x1 = min(xs) - dx / 2.0, max(xs) + dx / 2.0
    y0, y1 = min(ys) - dy / 2.0, max(ys) + dy / 2.0
    return [x0, y0, z, x1, y0, z, x1, y1, z, x0, y1, z]


def contorno_dos_pixels(pontos, dx, dy):
    p = np.asarray(pontos, dtype=np.float64).reshape(-1, 3)
    z = float(p[0, 2])
    try:
        import cv2
        import radai_geom
        o = p[:, :2].min(axis=0)
        ij = np.rint((p[:, :2] - o) / np.array([dx, dy])).astype(int)
        pix = set()
        for k in range(len(ij)):
            a, b = ij[k], ij[(k + 1) % len(ij)]
            n = int(np.abs(b - a).max())
            for t in range(n + 1):
                pix.add(tuple(int(v) for v in
                              np.rint(a + (b - a) * t / max(n, 1))))
        larg = max(c for c, _r in pix) + 1
        alt = max(r for _c, r in pix) + 1
        img = np.zeros((2 * alt + 2, 2 * larg + 2), np.uint8)
        for c, r in pix:
            img[2 * r + 1:2 * r + 3, 2 * c + 1:2 * c + 3] = 1
        # GUARDA: dois pixels que se tocam pela quina ganham uma ponte de
        # meio pixel, senao a quina vira laco no contorno.
        for c, r in pix:
            for dc, dr in ((1, 1), (1, -1)):
                if ((c + dc, r + dr) in pix and (c + dc, r) not in pix
                        and (c, r + dr) not in pix):
                    ca = 2 * c + 2
                    la = 2 * r + 2 if dr > 0 else 2 * r + 1
                    img[la, ca + 1] = 1
                    img[la + dr, ca] = 1
        achados = cv2.findContours(img, cv2.RETR_EXTERNAL,
                                   cv2.CHAIN_APPROX_SIMPLE)[-2]
        maior = max(achados, key=cv2.contourArea).reshape(-1, 2)
        xy = np.column_stack([o[0] + (maior[:, 0] - 1.5) / 2.0 * dx,
                              o[1] + (maior[:, 1] - 1.5) / 2.0 * dy])
        xy = radai_geom.expandir_meio_pixel(xy, dx / 2.0, dy / 2.0)
        if len(xy) < MIN_PONTOS_CONTORNO or abs(_area_assinada(xy)) <= 0:
            raise ValueError("contorno dos pixels vazio")
        return np.column_stack([xy, np.full(len(xy), z)])
    except Exception:
        return np.asarray(_caixa_do_pixel(p[:, 0].tolist(), p[:, 1].tolist(),
                                          z, dx, dy)).reshape(-1, 3)


def _reparar_contornos_degenerados(ds, clean_dir, dxdy=None,
                                   reparados_ids=None):
    if not hasattr(ds, "ROIContourSequence"):
        return 0
    dx, dy = dxdy if dxdy else _espacamento_no_plano(clean_dir)
    reparados, vazias = 0, []
    for rc in ds.ROIContourSequence:
        seq = getattr(rc, "ContourSequence", None)
        if not seq:
            vazias.append(int(getattr(rc, "ReferencedROINumber", -1)))
            continue
        for c in seq:
            dados = [float(v) for v in (getattr(c, "ContourData", None) or [])]
            n = len(dados) // 3
            if n < 1:
                continue
            p = np.asarray(dados[:3 * n]).reshape(-1, 3)
            if n >= MIN_PONTOS_CONTORNO and not contorno_degenerado(p):
                continue
            q = contorno_dos_pixels(p, dx, dy)
            c.ContourData = [float(v) for v in q.ravel()]
            c.NumberOfContourPoints = int(len(q))
            if reparados_ids is not None:
                reparados_ids.add(id(c))
            reparados += 1
        rc.ContourSequence = [c for c in seq
                              if len(getattr(c, "ContourData", None) or []) >= 9]
        if not rc.ContourSequence:
            vazias.append(int(getattr(rc, "ReferencedROINumber", -1)))
    if vazias:
        fora = set(vazias)
        ds.ROIContourSequence = [rc for rc in ds.ROIContourSequence
                                 if int(getattr(rc, "ReferencedROINumber", -1)) not in fora]
        for chave in ("StructureSetROISequence", "RTROIObservationsSequence"):
            seq = getattr(ds, chave, None)
            if seq is None:
                continue
            campo = "ROINumber" if chave == "StructureSetROISequence" else "ReferencedROINumber"
            setattr(ds, chave, [x for x in seq
                                if int(getattr(x, campo, -1)) not in fora])
    return reparados


MELHOR_FONTE = {}

CANDIDATAS_AO_FULL = {
    "spinal_canal": ("cads", u"o TotalSegmentator entrega `spinal_cord`, que e "
                             u"OUTRA COISA: o canal e o continente osseo e a "
                             u"medula e o conteudo",
                     u"fora do entregue: o OAR e a medula do TotalSegmentator"),
    "larynx": ("cads", u"a `total` nao entrega laringe; so a coluna de ar",
               u"fora do entregue: a task de cabeca e pescoco traz a laringe, "
               u"separada"),
    "breast_left": ("cads", u"nenhum dos outros entrega mama",
                    u"fora do entregue: sai so no arquivo de comparacao do CADS"),
    "breast_right": ("cads", u"idem", u"idem"),
    "seminal_vesicles": ("cads", u"nenhum dos outros entrega vesicula seminal",
                         u"fora do entregue: sai so no arquivo de comparacao do CADS"),
    "bowel_bag": ("cads", u"estrutura de planejamento que so o CADS entrega",
                  u"fora do entregue: sai so no arquivo de comparacao do CADS"),
    "colon_sigmoid": ("cads", u"o sigmoide separado do colon so o CADS entrega",
                      u"fora do entregue: sai so no arquivo de comparacao do CADS"),
    "rectus_abdominis_left": ("cads", u"parede abdominal -- o TotalSegmentator "
                                      u"so tem `autochthon`, que e paraespinhal",
                              u"fora do entregue: sai so no arquivo de comparacao do CADS"),
    "rectus_abdominis_right": ("cads", u"idem", u"idem"),
    "rectum": ("cads", u"o do CADS e modelo treinado; o nosso e particao "
                       u"geometrica do colon por dois marcos",
               u"fica o nosso: o reto deriva do colon do TotalSegmentator por "
               u"marcos anatomicos"),
}

AMBOS = {}

FONTE_PADRAO = "nosso"


def motores_que_alimentam():
    fora = {}
    for tabela in (MELHOR_FONTE, AMBOS):
        for estrutura, par in tabela.items():
            motor = par[0] if isinstance(par, (list, tuple)) else par
            if not motor or motor == FONTE_PADRAO:
                continue
            fora.setdefault(motor, []).append(estrutura)
    return dict((m, tuple(sorted(v))) for m, v in fora.items())


class _Sobreposto(object):

    def __init__(self, base):
        self._base = base
        self._novo = {}
        self._fora = set()

    def __iter__(self):
        vistos = set(self._fora)
        for k in self._base:
            if k in vistos:
                continue
            vistos.add(k)
            yield k
        for k in self._novo:
            if k not in vistos:
                yield k

    def keys(self):
        return list(self)

    def __len__(self):
        n = 0
        for _ in self:
            n += 1
        return n

    def __contains__(self, k):
        if k in self._novo:
            return True
        return k not in self._fora and k in self._base

    def __getitem__(self, k):
        if k in self._novo:
            return self._novo[k]
        if k in self._fora:
            raise KeyError(k)
        return self._base[k]

    def __setitem__(self, k, v):
        self._fora.discard(k)
        self._novo[k] = v

    def __delitem__(self, k):
        if k not in self:
            raise KeyError(k)
        self._novo.pop(k, None)
        self._fora.add(k)

    def pop(self, k, *padrao):
        if k in self:
            v = self[k]
            del self[k]
            return v
        if padrao:
            return padrao[0]
        raise KeyError(k)

    def get(self, k, padrao=None):
        return self[k] if k in self else padrao


    def update(self, outro):
        for k in (outro.keys() if hasattr(outro, "keys") else outro):
            self[k] = outro[k]


def curar(masks_nossas, por_motor, log=None, tabela=None):
    fora = (dict(masks_nossas) if isinstance(masks_nossas, dict)
            else _Sobreposto(masks_nossas))
    origem = dict((k, FONTE_PADRAO) for k in fora)

    escolhas = dict(MELHOR_FONTE)
    assinadas = set()
    try:
        if tabela is None:
            import radai_provenance
            tabela = radai_provenance.ler()
        for nome, linha in (tabela or {}).items():
            m = str((linha or {}).get("modelo") or "")
            if not (linha or {}).get("assinado_por"):
                continue
            assinadas.add(nome)
            if m and m != "ts":
                escolhas[nome] = (m, str(linha.get("motivo") or u"assinada"))
            else:
                escolhas.pop(nome, None)
    except Exception as e:
        if log:
            try:
                log("tabela de procedencia nao lida (%s) — vale o padrao de "
                    "fabrica" % type(e).__name__)
            except Exception:
                pass

    for estrutura, (motor_alt, _pq) in (AMBOS or {}).items():
        alt = ((por_motor or {}).get(motor_alt) or {}).get(estrutura)
        if alt is None or not getattr(alt, "any", lambda: False)():
            continue
        if estrutura not in fora:
            fora[estrutura] = alt
            origem[estrutura] = motor_alt
            continue
        chave_alt = "%s@%s" % (estrutura, motor_alt)
        fora[chave_alt] = alt
        origem[chave_alt] = motor_alt
        if log:
            try:
                log("comparacao aberta: %s sai em dobro (o nosso e o do %s)"
                    % (estrutura, motor_alt))
            except Exception:
                pass

    for estrutura, (motor_pref, _porque) in escolhas.items():
        d = (por_motor or {}).get(motor_pref) or {}
        m = d.get(estrutura)
        if m is not None and getattr(m, "any", lambda: False)():
            tinha = estrutura in fora
            fora[estrutura] = m
            origem[estrutura] = motor_pref
            if log:
                try:
                    log("curadoria: %s vem do %s%s%s"
                        % (estrutura, motor_pref,
                           " (substituiu o nosso)" if tinha else "",
                           " [ASSINADA]" if estrutura in assinadas
                           else " [padrao de fabrica]"))
                except Exception:
                    pass
        elif estrutura in fora and log:
            try:
                log("curadoria: %s ficou com o nosso — o %s nao entregou nesta "
                    "serie" % (estrutura, motor_pref))
            except Exception:
                pass
    return fora, origem


SUAVIZACAO_PADRAO_MM = 1.5

_S_OSSO = 0.8
_S_ALCA = 1.0
_S_AR = 0.8
_S_VASO = 1.5
_S_PARENQUIMA = 2.5

_S_MUSCULO = 1.5

SUAVIZACAO = {}

for _i in range(1, 21):
    SUAVIZACAO["LNL%02d" % _i] = 0.0
SUAVIZACAO["LNL_Union"] = 0.0
# GUARDA: o acabamento dos níveis (e da parótida do VIII) é o de
# `radai_hnlnl.suavizar_niveis`; aqui eles não são suavizados de novo.
for _n in ("Lvl_Ia", "Lvl_Ib_L", "Lvl_Ib_R", "Lvl_II_L", "Lvl_II_R",
           "Lvl_III_L", "Lvl_III_R", "Lvl_IVa_L", "Lvl_IVa_R", "Lvl_IVb_L",
           "Lvl_IVb_R", "Lvl_V_L", "Lvl_V_R", "Lvl_VIa", "Lvl_VIb",
           "Lvl_VIIa", "Lvl_VIIb_L", "Lvl_VIIb_R", "Lvl_VIII_L",
           "Lvl_VIII_R", "LNL_UNION", "parotid_lnl_left",
           "parotid_lnl_right"):
    SUAVIZACAO[_n] = 0.0

for _n in ("vertebrae_cervical", "vertebrae_thoracic", "vertebrae_lumbar",
           "vertebrae_S1", "vertebrae_L6",
           "sacrum", "ribs_left", "ribs_right", "sternum",
           "femur_left", "femur_right", "hip_left", "hip_right", "skull",
           "costal_cartilages", "clavicula_left", "clavicula_right",
           "scapula_left", "scapula_right", "humerus_left", "humerus_right"):
    SUAVIZACAO[_n] = _S_OSSO
SUAVIZACAO["bone_pelvic"] = _S_OSSO
for _i in range(1, 13):
    SUAVIZACAO["rib_left_%d" % _i] = _S_OSSO
    SUAVIZACAO["rib_right_%d" % _i] = _S_OSSO
for _reg, _n_ in (("C", 7), ("T", 12), ("L", 5)):
    for _i in range(1, _n_ + 1):
        SUAVIZACAO["vertebrae_%s%d" % (_reg, _i)] = _S_OSSO
for _n in ("colon", "small_intestine", "duodenum", "stomach", "rectum",
           "anal_canal", "esophagus"):
    SUAVIZACAO[_n] = _S_ALCA
for _n in ("trachea", "nasal_cavity", "nasal_cavity_left", "nasal_cavity_right",
           "nasopharynx", "oropharynx", "hypopharynx", "auditory_canal_left",
           "auditory_canal_right", "lung_left", "lung_right"):
    SUAVIZACAO[_n] = _S_AR
for _n in ("carotids", "great_vessels", "aorta", "iliac_artery_left",
           "iliac_artery_right", "iliac_vena_left", "iliac_vena_right",
           "pulmonary_vein", "superior_vena_cava", "inferior_vena_cava"):
    SUAVIZACAO[_n] = _S_VASO
for _n in ("liver", "spleen", "kidney_left", "kidney_right", "pancreas",
           "brain", "urinary_bladder", "prostate", "heart", "thyroid_gland",
           "parotid_gland_left", "parotid_gland_right",
           "submandibular_gland_left", "submandibular_gland_right",
           "kidney_cyst_left", "kidney_cyst_right"):
    SUAVIZACAO[_n] = _S_PARENQUIMA
for _n in (
        "lung_upper_lobe_left", "lung_lower_lobe_left",
        "lung_upper_lobe_right", "lung_middle_lobe_right",
        "lung_lower_lobe_right", "thoracic_cavity", "abdominal_cavity",
        "mediastinum", "pericardium", "eye_left", "eye_right",
        "eye_lens_left", "eye_lens_right", "hard_palate",
        "soft_palate", "larynx", "spinal_cord", "spinal_canal",
    ):
    SUAVIZACAO[_n] = _S_AR
# GUARDA: lamina, tubo ou estrutura pequena de poucos mm: a suavizacao da
# mascara apaga o corte fino, e a decimacao tira a largura que ele nao tem.
ESTRUTURAS_DELGADAS = ("optic_nerve_left", "optic_nerve_right",
                       "optic_chiasm",
                       "pharyngeal_constrictor_superior",
                       "pharyngeal_constrictor_middle",
                       "pharyngeal_constrictor_inferior")
for _n in ESTRUTURAS_DELGADAS:
    SUAVIZACAO[_n] = 0.0
for _n in (
        "common_carotid_artery_left", "common_carotid_artery_right",
        "subclavian_artery_left", "subclavian_artery_right",
        "brachiocephalic_trunk", "brachiocephalic_vein_left",
        "brachiocephalic_vein_right", "portal_vein_and_splenic_vein",
        
    ):
    SUAVIZACAO[_n] = _S_VASO
for _n in (
        "adrenal_gland_left", "adrenal_gland_right", "gallbladder",
        "brain_brainstem", "brain_cerebellum", "frontal_lobe",
        "parietal_lobe", "temporal_lobe", "occipital_lobe",
        "insular_cortex", "thalamus", "caudate_nucleus",
        "lentiform_nucleus", "internal_capsule", "septum_pellucidum",
        "central_sulcus", "subarachnoid_space", "venous_sinuses",
        "seminal_vesicles",
    ):
    SUAVIZACAO[_n] = _S_PARENQUIMA
SUAVIZACAO_A_MAIS_DA_MAMA_MM = 3.0

for _n in ("breast_left", "breast_right"):
    SUAVIZACAO[_n] = _S_PARENQUIMA + SUAVIZACAO_A_MAIS_DA_MAMA_MM
for _n in (
        "gluteus_maximus_left", "gluteus_maximus_right",
        "gluteus_medius_left", "gluteus_medius_right",
        "gluteus_minimus_left", "gluteus_minimus_right",
        "iliopsoas_left", "iliopsoas_right",
        "rectus_abdominis_left", "rectus_abdominis_right",
        "autochthon_left", "autochthon_right",
    ):
    SUAVIZACAO[_n] = _S_MUSCULO
for _n in (
        "colon_sigmoid", "bowel_bag",
    ):
    SUAVIZACAO[_n] = _S_ALCA
for _n in ("great_arteries", "great_veins",
           "internal_carotid_artery_left", "internal_carotid_artery_right",
           "internal_jugular_vein_left", "internal_jugular_vein_right"):
    SUAVIZACAO[_n] = _S_VASO
for _n in ("femur_oar_left", "femur_oar_right"):
    SUAVIZACAO[_n] = _S_OSSO
for _n in ("ChestWall_L", "ChestWall_R", "iliac_crest_left",
           "iliac_crest_right", "anus"):
    SUAVIZACAO[_n] = 0.0
del _n


def suavizacao_de(nome, padrao=None):
    base = SUAVIZACAO_PADRAO_MM if padrao is None else float(padrao)
    v = _nomes.procurar(SUAVIZACAO, str(nome))
    if v is None:
        return base
    return v * (base / SUAVIZACAO_PADRAO_MM)


ESPESSURA_FINA_MM = 3.0


def estrutura_fina(mask, grade):
    try:
        import radai_geom
        r = float(radai_geom.espessura_mm(mask, grade))
    except Exception:
        return False, 0.0
    if r <= 0.0:
        return False, 0.0
    return (r < ESPESSURA_FINA_MM), r


_DIVISOR_DO_RAIO = 3.0


def teto_de_suavizacao(mask, grade, raio=None):
    if raio is not None and float(raio) > 0:
        return float(raio) / _DIVISOR_DO_RAIO
    try:
        m = _bool_seguro(mask)
        if not m.any():
            return None
        import radai_geom
        r = float(radai_geom.espessura_mm(m, grade))
        return (r / _DIVISOR_DO_RAIO) if r > 0 else None
    except Exception:
        return None


VOLUME_MINIMO_CM3 = {
    "adrenal_gland_left": 1,
    "adrenal_gland_right": 1,
    "brain": 700,
    "colon": 100,
    "duodenum": 20,
    "esophagus": 20,
    "femur_left": 90,
    "femur_right": 90,
    "gallbladder": 1,
    "gluteus_maximus_left": 100,
    "gluteus_maximus_right": 100,
    "gluteus_medius_left": 100,
    "gluteus_medius_right": 100,
    "gluteus_minimus_left": 30,
    "gluteus_minimus_right": 30,
    "aorta": 40,
    "heart": 300,
    "hip_left": 100,
    "hip_right": 100,
    "iliac_artery_left": 10,
    "iliac_artery_right": 10,
    "iliac_vena_left": 10,
    "iliac_vena_right": 10,
    "iliopsoas_left": 100,
    "iliopsoas_right": 100,
    "kidney_left": 60,
    "kidney_right": 60,
    "liver": 500,
    "lung_left": 300,
    "lung_lower_lobe_left": 100,
    "lung_lower_lobe_right": 100,
    "lung_middle_lobe_right": 100,
    "lung_right": 400,
    "lung_upper_lobe_left": 100,
    "lung_upper_lobe_right": 100,
    "pancreas": 20,
    "parotid_gland_left": 8,
    "parotid_gland_right": 8,
    "prostate": 10,
    "ribs_left": 93,
    "ribs_right": 93,
    "sacrum": 100,
    "small_intestine": 150,
    "spinal_cord": 15,
    "spleen": 40,
    "stomach": 70,
    "thyroid_gland": 4,
    "trachea": 20,
    "urinary_bladder": 40,
    "vertebrae_S1": 3,
    "vertebrae_L6": 3,
    "vertebrae_cervical": 16,
    "vertebrae_lumbar": 170,
    "vertebrae_thoracic": 170,
}

VOLUME_MINIMO_GERAL_CM3 = 0.02


def toca_a_borda(m):
    if m is None or not m.any():
        return False
    for eixo in range(m.ndim):
        for fatia in (0, -1):
            idx = [slice(None)] * m.ndim
            idx[eixo] = fatia
            if m[tuple(idx)].any():
                return True
    return False


def implausiveis(masks, grade, caixas=None, so=None):
    import radai_geom
    if caixas is None:
        caixas = radai_geom.Caixas(masks)
    fora, cortadas = [], []
    for nome in sorted(n for n in masks if so is None or n in so):
        try:
            m = masks[nome]
            base = str(nome).split(":")[-1]
            piso = _nomes.procurar(VOLUME_MINIMO_CM3, base,
                                   VOLUME_MINIMO_GERAL_CM3)
            v = radai_geom.volume_de_voxels(caixas.de(nome)[2], grade)
            if v >= piso:
                continue
            if toca_a_borda(m):
                cortadas.append(nome)
            else:
                fora.append((nome, round(v, 2), piso))
        except Exception:
            continue
    return fora, cortadas


FRACAO_DE_ILHA = 0.05
DISTANCIA_DE_ILHA_MM = 30.0


def _centros_na_caixa(sub, rot, indices, origem):
    from scipy import ndimage
    normal = ndimage.sum_labels(sub, rot, indices)
    grades = np.ogrid[[slice(int(o), int(o) + int(n))
                       for o, n in zip(origem, sub.shape)]]
    res = [ndimage.sum_labels(sub * grades[d].astype(float), rot, indices)
           / normal for d in range(sub.ndim)]
    return [tuple(v) for v in np.array(res).T]


def componentes_distantes(masks, grade,
                          fracao=FRACAO_DE_ILHA,
                          distancia_mm=DISTANCIA_DE_ILHA_MM, caixas=None,
                          so=None):
    from scipy import ndimage
    import radai_geom
    esp = getattr(grade, "spacing", (1.0, 1.0, 1.0))
    if caixas is None:
        caixas = radai_geom.Caixas(masks)
    fora = []
    for nome in sorted(n for n in masks if so is None or n in so):
        try:
            if masks[nome] is None:
                continue
            _mb, cx, _n = caixas.de(nome)
            if cx is None:
                continue
            m = caixas.cru(nome)
            rot, quantos = ndimage.label(m)
            if quantos < 2:
                continue
            tam = ndimage.sum(m, rot, range(1, quantos + 1))
            total = float(tam.sum())
            maior = int(tam.argmax()) + 1
            centros = _centros_na_caixa(
                m, rot, range(1, quantos + 1),
                [s.start or 0 for s in cx])
            c0 = centros[maior - 1]
            pior_d, pior_f, n_ilhas = 0.0, 0.0, 0
            for k in range(1, quantos + 1):
                if k == maior:
                    continue
                f = float(tam[k - 1]) / total if total else 0.0
                if f > fracao:
                    continue
                c = centros[k - 1]
                d = sum(((c[i] - c0[i]) * esp[i]) ** 2
                        for i in range(len(esp))) ** 0.5
                if d < distancia_mm:
                    continue
                n_ilhas += 1
                if d > pior_d:
                    pior_d, pior_f = d, f
            if n_ilhas:
                fora.append((nome, n_ilhas, round(pior_d, 1), round(pior_f, 4)))
        except Exception:
            continue
    return fora



FRACAO_SOBREPOSICAO = 0.02

RECIPIENTES_NO_FULL = ("abdominal_cavity", "thoracic_cavity", "mediastinum")

# GUARDA: a união dos níveis cervicais é recipiente de linfonodos no OAR —
# encosta em glândula, constritor e vaso por definição. A parótida do VIII
# não é recipiente: sobreposição dela continua alarme.
RECIPIENTES_NO_OAR = ("LNL_UNION",)

# GUARDA: o encefalo do TotalSegmentator contem o tronco, o cerebelo, os
# ventriculos e a linha media do modelo do encefalo em TC; o par e esperado
# nos dois modos, e nao alarme de dose contada duas vezes
DENTRO_DO_ENCEFALO = (
    ("brain", "brain_brainstem"), ("brain", "cerebellum"),
    ("brain", "brain_ventricles"), ("brain", "brain_midline"),
)

MESMO_MUSCULO_NO_FULL = (
    ("autochthon", "erector_spinae"),
    ("autochthon", "transversospinalis"),
    ("iliopsoas", "psoas_major"),
)


def _mesmo_musculo(a, b):
    for p, q in MESMO_MUSCULO_NO_FULL:
        if ((_nomes.casa_prefixo(a, (p,)) and _nomes.casa_prefixo(b, (q,)))
                or (_nomes.casa_prefixo(a, (q,))
                    and _nomes.casa_prefixo(b, (p,)))):
            return True
    return False


def _caixa(m):
    import numpy as np
    eixos = []
    for eixo in range(3):
        outros = tuple(i for i in range(3) if i != eixo)
        onde = np.where(m.any(axis=outros))[0]
        if not len(onde):
            return None
        eixos.append((int(onde[0]), int(onde[-1]) + 1))
    return eixos


def _caixas_se_tocam(a, b):
    return all(a[i][0] < b[i][1] and b[i][0] < a[i][1] for i in range(3))


def sobreposicoes(masks, grade, fracao=FRACAO_SOBREPOSICAO, construcoes=None,
                  estrito=False, so=None, caixas=None):
    import radai_geom
    _cx = caixas if caixas is not None else radai_geom.Caixas(masks)
    nomes = [k for k in sorted(masks)
             if (so is None or k in so)
             and masks[k] is not None and _cx.de(k)[1] is not None]
    caixas, esperados = {}, set()
    for k in nomes:
        c = _cx.justa(k)
        if c:
            caixas[k] = c
    for composto, partes in COMPOSTOS.items():
        for p in partes:
            esperados.add(tuple(sorted((composto, p))))
    for a, pa in COMPOSTOS.items():
        for b, pb in COMPOSTOS.items():
            if a != b and pa and set(pa) <= set(pb):
                esperados.add(tuple(sorted((a, b))))
    for mae in DERIVADAS:
        for _marcos, _e, _o, filha in DERIVADAS[mae]["planos"]:
            esperados.add(tuple(sorted((mae, filha))))
    for fora_, dentro_ in DENTRO_DO_ENCEFALO:
        esperados.add(tuple(sorted((fora_, dentro_))))
    _regra_a4 = construcoes is not None
    construcoes = dict(construcoes or {})
    _constr = (set(construcoes) | set(COMPOSTOS)) if _regra_a4 else set()

    def _esperado(a, b):
        if tuple(sorted((a, b))) in esperados:
            return True
        if _regra_a4 and not estrito and any(
                _nomes.casa_prefixo(x, RECIPIENTES_NO_FULL) is not None
                for x in (a, b)):
            return True
        if _regra_a4 and estrito and any(
                str(x) in RECIPIENTES_NO_OAR for x in (a, b)):
            return True
        if _regra_a4 and not estrito and _mesmo_musculo(a, b):
            return True
        for c, o in ((a, b), (b, a)):
            if c not in _constr:
                continue
            contem = tuple((construcoes.get(c) or {}).get("contem") or ())
            if contem and _nomes.casa_prefixo(o, contem):
                return True
            if not estrito and o not in _constr:
                return True
        return False

    fora = []
    for i, a in enumerate(nomes):
        if a not in caixas:
            continue
        for b in nomes[i + 1:]:
            if b not in caixas or not _caixas_se_tocam(caixas[a], caixas[b]):
                continue
            if _esperado(a, b):
                continue
            ca, cb = caixas[a], caixas[b]
            ib = tuple(slice(max(ca[i][0], cb[i][0]), min(ca[i][1], cb[i][1]))
                       for i in range(3))
            if _cx.folga is None:
                ib = (slice(None),) * 3
            inter = _cx.de(a)[0][ib] & _cx.de(b)[0][ib]
            if not inter.any():
                continue
            vol = radai_geom.volume_cm3(inter, grade)
            menor = min(radai_geom.volume_de_voxels(_cx.de(a)[2], grade),
                        radai_geom.volume_de_voxels(_cx.de(b)[2], grade))
            fr = (vol / menor) if menor else 1.0
            if fr < fracao:
                continue
            fora.append((a, b, round(vol, 2), round(fr, 4)))
    fora.sort(key=lambda t: -t[2])
    return fora


NOMES_DE_CONTORNO_EXTERNO = (
    "body", "body_trunc", "body_extremities", "bodycontour",
    "external", "externo", "contorno_externo", "corpo",
    "outercontour", "patient", "paciente",
)


def conferir_sem_body(nomes):
    ruins = []
    for n in (nomes or []):
        raiz = str(n).split(":")[-1].strip().lower()
        try:
            import radai_sets
            raiz = radai_sets.raiz_sem_sufixo(raiz)
        except Exception:
            for suf in ("_ai", "_ts", "_v3d", "_cds", "_lnl", "_pel"):
                if raiz.endswith(suf):
                    raiz = raiz[: -len(suf)]
                break
        if raiz in NOMES_DE_CONTORNO_EXTERNO:
            ruins.append(str(n))
    if not ruins:
        return
    raise ValueError(
        u"contorno externo nao entra em RTSTRUCT nenhum: %s. Ele diz ao "
        u"algoritmo onde calcular dose, e nenhum conjunto deste aplicativo e "
        u"revisado para isso. O que se entrega e a casca (`Skin`) e a parede "
        u"(`ChestWall_L`/`_R`) — ver `radai_skin`."
        % ", ".join(sorted(set(ruins))[:6]))


_TIPOGRAFICO = {
    0x2014: u" - ",
    0x2013: u"-",
    0x2018: u"'", 0x2019: u"'",
    0x201C: u'"', 0x201D: u'"',
    0x2026: u"...",
    0x00AB: u'"', 0x00BB: u'"',
}


_ASCII_DO_RTSTRUCT = {
    0x00B0: u" graus", 0x00D7: u"x", 0x00B1: u"+/-", 0x2265: u">=",
    0x2264: u"<=", 0x2192: u"->", 0x2190: u"<-", 0x00B7: u"-", 0x2022: u"-",
    0x00B5: u"u", 0x00A0: u" ", 0x2248: u"~", 0x2212: u"-",
}


def texto_ascii(t):
    import unicodedata
    t = str(t or "").translate(_TIPOGRAFICO).translate(_ASCII_DO_RTSTRUCT)
    t = unicodedata.normalize("NFKD", t)
    return t.encode("ascii", "ignore").decode("ascii")


def _para_dicom(t):
    try:
        return texto_ascii(t)
    except Exception:
        return str(t or "")


TPS_ECLIPSE = "eclipse"
TPS_MONACO = "monaco"
TPS_DESTINOS = (TPS_ECLIPSE, TPS_MONACO)


def _tps_configurado():
    bruto = (os.environ.get("RADAI_TPS_DESTINO") or "").strip()
    if not bruto:
        try:
            import radai_config
            bruto = radai_config.chave_configurada("TPS_DESTINO") or ""
        except Exception:
            bruto = ""
    valor = bruto.strip().lower()
    return valor if valor in TPS_DESTINOS else ""


def tps_destino():
    return _tps_configurado() or TPS_ECLIPSE


# GUARDA: o compartimento linfonodal nao e orgao; o tipo estruturado do
# DICOM diz o mesmo que a descricao da ROI (nao e OAR nem CTV).
PREFIXOS_DE_CONTROLE = ("Lvl_", "LNL")


def tipo_interpretado(chave):
    return ("CONTROL" if str(chave or "").startswith(PREFIXOS_DE_CONTROLE)
            else "ORGAN")


def tps_escolhido():
    return bool(_tps_configurado())


def rotulo_do_tps(valor):
    try:
        import radai_config
        r = radai_config.rotulo_do_tps(valor)
    except Exception:
        r = u""
    return r or u"TPS_DESTINO=%s" % (valor or u"")


AVISO_DO_TPS_NAO_ESCOLHIDO = (
    u"ALERTA: TPS de destino nao escolhido (TPS_DESTINO vazio): o RTSTRUCT "
    u"foi gravado como %s, com o furo do anel num segundo contorno. Num TPS "
    u"que precisa da linha divisoria nos aneis (%s), a Skin e a ChestWall "
    u"chegariam preenchidas. Escolha o TPS no primeiro uso do painel."
    % (rotulo_do_tps(TPS_ECLIPSE), rotulo_do_tps(TPS_MONACO)))


_VR_DE_TEXTO = frozenset(("AE", "AS", "CS", "DA", "DT", "LO", "LT", "PN",
                          "SH", "ST", "TM", "UC", "UT"))
_IDENTIDADE_DA_IMAGEM = frozenset((
    "PatientName", "PatientID", "PatientBirthDate", "PatientSex",
    "PatientAge", "OtherPatientIDs", "PatientComments", "StudyDescription",
    "StudyID", "AccessionNumber", "ReferringPhysicianName"))


def _texto_ascii_no_dataset(ds, com_identidade):
    from pydicom.multival import MultiValue
    trocados = 0
    for el in ds.iterall():
        if el.VR not in _VR_DE_TEXTO or el.value is None:
            continue
        if not com_identidade and el.keyword in _IDENTIDADE_DA_IMAGEM:
            continue
        v = el.value
        if isinstance(v, (list, MultiValue)):
            novos = [texto_ascii(x) if isinstance(x, str) else x for x in v]
            if [str(x) for x in novos] != [str(x) for x in v]:
                el.value = novos
                trocados += 1
            continue
        texto = str(v)
        novo = texto_ascii(texto)
        if novo != texto:
            el.value = novo
            trocados += 1
    return trocados


def _identidade_fora_do_ascii(ds):
    for k in _IDENTIDADE_DA_IMAGEM:
        v = getattr(ds, k, None)
        if v is not None and not str(v).isascii():
            return True
    return False


def _area_assinada(xy):
    x, y = xy[:, 0], xy[:, 1]
    return 0.5 * float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))


def _ponto_dentro(p, xy):
    xs, ys = xy[:, 0], xy[:, 1]
    xs2, ys2 = np.roll(xs, -1), np.roll(ys, -1)
    cruza = (ys > p[1]) != (ys2 > p[1])
    with np.errstate(divide="ignore", invalid="ignore"):
        xint = xs + (p[1] - ys) * (xs2 - xs) / (ys2 - ys)
    return bool(np.count_nonzero(cruza & (p[0] < xint)) % 2)


def _dentro_de(a, b):
    n = len(a)
    amostra = [a[0], a[n // 3], a[(2 * n) // 3]]
    return sum(_ponto_dentro(p, b) for p in amostra) >= 2


def aninhamento(poligonos):
    xy = [np.asarray(p, dtype=np.float64)[:, :2] for p in poligonos]
    areas = [abs(_area_assinada(a)) if len(a) >= 3 else 0.0 for a in xy]
    caixas = [(a[:, 0].min(), a[:, 1].min(), a[:, 0].max(), a[:, 1].max())
              if len(a) else (0, 0, 0, 0) for a in xy]
    contem = []
    for m in range(len(xy)):
        dentro = []
        if len(xy[m]) >= 3:
            cm = caixas[m]
            for k in range(len(xy)):
                if k == m or areas[k] <= areas[m] or len(xy[k]) < 3:
                    continue
                ck = caixas[k]
                if cm[0] < ck[0] or cm[1] < ck[1] or cm[2] > ck[2] \
                        or cm[3] > ck[3]:
                    continue
                if _dentro_de(xy[m], xy[k]):
                    dentro.append(k)
        contem.append(dentro)
    return areas, contem, [len(c) for c in contem]


def _furos_da_roi(rc, lidos=None):
    por_z = {}
    for c in getattr(rc, "ContourSequence", None) or []:
        if lidos is not None:
            pts = lidos.get(id(c))
            if pts is None:
                continue
        else:
            dados = getattr(c, "ContourData", None) or []
            if len(dados) < 9 or len(dados) % 3:
                continue
            pts = np.asarray([float(v) for v in dados]).reshape(-1, 3)
        por_z.setdefault(round(float(pts[0, 2]), 2), []).append((c, pts))
    furos = set()
    for grupo in por_z.values():
        if len(grupo) < 2:
            continue
        _a, _c, prof = aninhamento([p for _x, p in grupo])
        furos.update(id(grupo[m][0]) for m in range(len(grupo))
                     if prof[m] % 2 == 1)
    return furos


def fundir_furo(pai, furo):
    from scipy.spatial import cKDTree
    # GUARDA: o furo percorre o sentido oposto ao do pai; na regra de
    # enrolamento diferente de zero, o mesmo sentido o preencheria.
    if (_area_assinada(pai[:, :2]) > 0) == (_area_assinada(furo[:, :2]) > 0):
        furo = furo[::-1]
    dist, j = cKDTree(furo[:, :2]).query(pai[:, :2])
    i = int(np.argmin(dist))
    j = int(j[i])
    return np.concatenate([pai[:i + 1], furo[j:], furo[:j + 1], pai[i:]])


def _fundir_furos_por_fenda(ds):
    fundidos = 0
    for rc in getattr(ds, "ROIContourSequence", []) or []:
        itens = list(getattr(rc, "ContourSequence", []) or [])
        if len(itens) < 2:
            continue
        por_z = {}
        for c in itens:
            dados = getattr(c, "ContourData", None) or []
            if len(dados) < 9 or len(dados) % 3:
                continue
            pts = np.asarray([float(v) for v in dados]).reshape(-1, 3)
            por_z.setdefault(round(float(pts[0, 2]), 2), []).append((c, pts))
        saem = set()
        for grupo in por_z.values():
            if len(grupo) < 2:
                continue
            areas, contem, prof = aninhamento([p for _c, p in grupo])
            pontos = [p for _c, p in grupo]
            ordem = sorted(range(len(grupo)), key=lambda m: -prof[m])
            for m in ordem:
                if prof[m] % 2 == 0:
                    continue
                pais = [k for k in contem[m] if prof[k] == prof[m] - 1]
                if not pais:
                    continue
                k = min(pais, key=lambda q: areas[q])
                pontos[k] = fundir_furo(pontos[k], pontos[m])
                saem.add(id(grupo[m][0]))
                fundidos += 1
            for k, (c, _p) in enumerate(grupo):
                if id(c) in saem or pontos[k] is grupo[k][1]:
                    continue
                c.ContourData = ["%.4f" % float(v) for v in pontos[k].ravel()]
                c.NumberOfContourPoints = int(len(pontos[k]))
        if saem:
            rc.ContourSequence = pydicom.Sequence(
                [c for c in itens if id(c) not in saem])
    return fundidos


def guardar_contornos(ds):
    fora = {}
    for rc in getattr(ds, "ROIContourSequence", None) or []:
        for c in getattr(rc, "ContourSequence", None) or []:
            dados = getattr(c, "ContourData", None)
            if not dados:
                continue
            try:
                v = np.asarray([float(x) for x in dados], dtype=np.float64)
            except Exception:
                continue
            if v.size % 3 or v.size < 9:
                continue
            fora[id(c)] = v.reshape(-1, 3)
    return fora


def acabar_contornos(ds, originais=None, dxdy=None):
    laudo = {"repetidos": 0, "degenerados": 0, "cruzados": 0,
             "cruzados_restantes": 0}
    dx, dy = dxdy if dxdy else (1.0, 1.0)
    for rc in getattr(ds, "ROIContourSequence", None) or []:
        furos = None
        for c in getattr(rc, "ContourSequence", None) or []:
            dados = getattr(c, "ContourData", None)
            if not dados:
                continue
            try:
                v = np.asarray([float(x) for x in dados], dtype=np.float64)
            except Exception:
                continue
            if v.size % 3 or not v.size:
                continue
            p = v.reshape(-1, 3)
            q = _sem_vertice_repetido(p)
            mudou = len(q) != len(p)
            if mudou:
                laudo["repetidos"] += 1
            if originais is not None and cruza_a_si_mesmo(q):
                # GUARDA: o cruzamento nasce na suavizacao do poligono; o
                # contorno volta ao de antes dela, com o meio pixel se der.
                velho = originais.get(id(c))
                troca = None
                if velho is not None:
                    candidatos = []
                    if dxdy:
                        try:
                            import radai_geom
                            if furos is None:
                                furos = _furos_da_roi(rc)
                            xy = radai_geom.expandir_meio_pixel(
                                velho[:, :2], dx, dy, furo=(id(c) in furos))
                            candidatos.append(np.column_stack(
                                [xy, velho[:, 2]]))
                        except Exception:
                            pass
                    candidatos.append(velho)
                    for cand in candidatos:
                        cq = _sem_vertice_repetido(cand)
                        if not cruza_a_si_mesmo(cq):
                            troca = cq
                            break
                if troca is None:
                    laudo["cruzados_restantes"] += 1
                else:
                    laudo["cruzados"] += 1
                    q, mudou = troca, True
            if contorno_degenerado(q):
                q = contorno_dos_pixels(p, dx, dy)
                laudo["degenerados"] += 1
                mudou = True
            if mudou:
                c.ContourData = ["%.4f" % float(x) for x in q.ravel()]
                c.NumberOfContourPoints = int(len(q))
    return laudo


def frase_dos_contornos(laudo):
    l = dict(laudo or {})
    partes = []
    if l.get("repetidos"):
        partes.append(u"%d com vertice repetido" % l["repetidos"])
    if l.get("degenerados"):
        partes.append(u"%d de area nula refeito(s) pelo contorno dos pixels"
                      % l["degenerados"])
    if l.get("cruzados"):
        partes.append(u"%d que cruzavam a si mesmos voltaram ao contorno de "
                      u"antes da suavizacao" % l["cruzados"])
    if l.get("cruzados_restantes"):
        partes.append(u"%d ainda cruzam a si mesmos" % l["cruzados_restantes"])
    if not partes:
        return u""
    return u"acabamento dos contornos: " + u"; ".join(partes)


def _somar_laudos(a, b):
    return dict((k, int(a.get(k, 0)) + int(b.get(k, 0)))
                for k in set(a) | set(b))


def acabamento_para_o_tps(ds, tps=None, originais=None, dxdy=None,
                          charset=None):
    from pydicom.uid import ImplicitVRLittleEndian
    tps = tps if tps in TPS_DESTINOS else tps_destino()
    laudo = {"tps": tps, "furos": 0, "textos": 0}
    laudo["textos"] = _texto_ascii_no_dataset(ds, com_identidade=False)
    laudo["contornos"] = acabar_contornos(ds, originais, dxdy)
    if tps == TPS_MONACO:
        laudo["furos"] = _fundir_furos_por_fenda(ds)
        if laudo["furos"]:
            laudo["contornos"] = _somar_laudos(
                laudo["contornos"], acabar_contornos(ds, None, dxdy))
    # GUARDA: a identidade sai com os bytes da imagem (o TPS associa por
    # ela): com acento, o repertorio declarado e o da TC; sem, nenhum.
    if _identidade_fora_do_ascii(ds):
        ds.SpecificCharacterSet = charset or "ISO_IR 100"
    elif "SpecificCharacterSet" in ds:
        del ds.SpecificCharacterSet
    meta = getattr(ds, "file_meta", None)
    if meta is not None:
        meta.TransferSyntaxUID = ImplicitVRLittleEndian
    return laudo


def _internos_do_pydicom():
    from pydicom.charset import convert_encodings, default_encoding
    from pydicom.dataset import FileMetaDataset
    from pydicom.filebase import DicomFile
    from pydicom.filewriter import (_determine_encoding, correct_ambiguous_vr,
                                    write_data_element, write_file_meta_info,
                                    write_sequence_item)
    from pydicom.tag import SequenceDelimiterTag
    from pydicom.uid import DeflatedExplicitVRLittleEndian
    return locals()


def gravar_dicom_em_fluxo(ds, caminho, implicit_vr=None, little_endian=None):
    from copy import deepcopy
    try:
        P = _internos_do_pydicom()
    except (ImportError, AttributeError):
        P = None
    meta = getattr(ds, "file_meta", None)
    if (P is None or not isinstance(ds, pydicom.dataset.Dataset)
            or (meta is not None and meta.get("TransferSyntaxUID")
                == P["DeflatedExplicitVRLittleEndian"])):
        kw = {}
        if implicit_vr is not None:
            kw = {"implicit_vr": implicit_vr, "little_endian": little_endian}
        ds.save_as(str(caminho), **kw)
        return "save_as"
    if [x for x in ds._dict if x >> 16 in (0, 2)]:
        raise ValueError("Command Set or File Meta elements in the dataset")
    file_meta = P["FileMetaDataset"]()
    if meta is not None:
        file_meta = deepcopy(meta)
    tsyntax = file_meta.get("TransferSyntaxUID", None)
    encoding = P["_determine_encoding"](ds, tsyntax, implicit_vr,
                                        little_endian, False)
    if encoding == (True, False):
        raise ValueError("Implicit VR and big endian is not a valid "
                         "encoding combination")
    preamble = getattr(ds, "preamble", None)
    if preamble and len(preamble) != 128:
        raise ValueError("'preamble' must be 128-bytes long")
    fp = P["DicomFile"](str(caminho), "wb")
    fp.is_implicit_VR, fp.is_little_endian = encoding
    try:
        if preamble:
            fp.write(preamble)
            fp.write(b"DICM")
        if file_meta:
            P["write_file_meta_info"](fp, file_meta, enforce_standard=False)
        dataset, get_item = ds, ds.get_item
        if (encoding != ds.original_encoding
                or ds.original_character_set != ds._character_set):
            dataset = P["correct_ambiguous_vr"](ds, fp.is_little_endian)
            get_item = dataset.__getitem__
        enc = dataset.get("SpecificCharacterSet", P["default_encoding"])
        for tag in sorted(dataset.keys()):
            if tag.element == 0 and tag.group > 6:
                continue
            elem = get_item(tag)
            if (getattr(elem, "is_raw", False) or elem.VR != "SQ"
                    or elem.is_empty):
                P["write_data_element"](fp, elem, enc)
                continue
            # GUARDA: a sequencia de nivel 1 vai direto ao arquivo, item a
            # item, com o comprimento remendado no fim -- os mesmos bytes do
            # pydicom, sem o buffer da sequencia inteira e a copia dele.
            fp.write_tag(elem.tag)
            if not fp.is_implicit_VR:
                fp.write(b"SQ")
                fp.write_US(0)
            lugar = fp.tell()
            fp.write_UL(0xFFFFFFFF)
            encs = P["convert_encodings"](enc or [P["default_encoding"]])
            for item in elem.value:
                P["write_sequence_item"](fp, item, encs)
            if elem.is_undefined_length:
                fp.write_tag(P["SequenceDelimiterTag"])
                fp.write_UL(0)
            else:
                fim = fp.tell()
                fp.seek(lugar)
                fp.write_UL(fim - lugar - 4)
                fp.seek(fim)
    finally:
        fp.close()
    return "fluxo"


def gravar_rtstruct(ds, caminho, tps=None, log=None, originais=None,
                    dxdy=None, charset=None):
    laudo = acabamento_para_o_tps(ds, tps, originais=originais, dxdy=dxdy,
                                  charset=charset)
    gravar_dicom_em_fluxo(ds, caminho, implicit_vr=True, little_endian=True)
    _frase = frase_dos_contornos(laudo.get("contornos"))
    if log and _frase:
        try:
            log(_frase)
        except Exception:
            pass
    if not log:
        return laudo
    try:
        if laudo["tps"] == TPS_MONACO:
            log(u"TPS de destino %s: %d furo(s) ligado(s) a borda por linha "
                u"divisoria, texto so ASCII, Implicit VR Little Endian"
                % (rotulo_do_tps(TPS_MONACO), laudo["furos"]))
        elif tps is None and not tps_escolhido():
            log(AVISO_DO_TPS_NAO_ESCOLHIDO)
        else:
            log(u"TPS de destino %s: o furo do anel num segundo contorno, "
                u"texto so ASCII, Implicit VR Little Endian"
                % rotulo_do_tps(TPS_ECLIPSE))
    except Exception:
        pass
    return laudo


def _desconto_do_entregue():
    try:
        import radai_sets
        return radai_sets.desconto_do_entregue()
    except Exception:
        return False


ROTULO_OAR_FAST = "RadAI_OAR_Fast"


def _textos_do_conjunto(rotulo, versao_worker, tem_nv, sufixo_do_conjunto,
                        suspeitas, suavizadas, suavizar_mm, modo=None,
                        decimar_mm=None):
    if modo == "fast":
        return _textos_do_oar_fast(rotulo, versao_worker, sufixo_do_conjunto,
                                   suspeitas, suavizadas, suavizar_mm,
                                   decimar_mm)
    rotulo_ = (rotulo or "RadAI_OAR")[:16]
    nome = ("RadAI auto-contorno (sugestao nao aprovada)" if not rotulo else
            "%s - estudo, nao e o entregue" % rotulo)[:64]
    descricao = (
        ("Conjunto %s: material de estudo e comparacao entre motores. O "
         "conjunto entregue para o plano e o RadAI_OAR. " % rotulo
         if rotulo else "")
        + "Estruturas geradas automaticamente por Radioterapia.AI "
        "(TotalSegmentator%s). SUGESTAO NAO APROVADA: revisao e aprovacao "
        "sao ato medico e continuam obrigatorias no TPS. "
        "%s" % (" / worker " + versao_worker if versao_worker else "",
                ("Sufixo '%s' = TotalSegmentator; sufixo '%s' = "
                 "NV-Segment-CT. "
                 "AS DUAS sao geracao automatica, NENHUMA foi revisada: o "
                 "arquivo traz as duas versoes da mesma estrutura de "
                 "proposito, para comparacao. Ver ROIGenerationDescription "
                 "de cada estrutura." % (SUFIXO_AI, SUFIXO_NV))
                if tem_nv else
                ("Sufixo '%s' em todos os nomes."
                 % (sufixo_do_conjunto or SUFIXO_AI)))
        + ((" %d estrutura(s) com volume abaixo do anatomicamente "
            "plausivel: %s. Entregues assim mesmo, para revisao."
            % (len(suspeitas), ", ".join(x[0] for x in suspeitas[:6])))
           if suspeitas else "")
        + (" Contornos SUAVIZADOS (escala %.1f, por estrutura): o contorno "
           "NAO e a saida crua do modelo. O volume e preservado; o que "
           "muda e a forma da borda." % (suavizar_mm or 0.0)
           if suavizadas else ""))
    serie = ("RadAI auto-contorno - SUGESTAO NAO APROVADA" if not rotulo else
             "%s - estudo (o entregue e RadAI_OAR)" % rotulo)[:64]
    return {"StructureSetLabel": rotulo_, "StructureSetName": nome,
            "StructureSetDescription": descricao, "SeriesDescription": serie,
            "SeriesNumber": 900 if not rotulo else 901}


def _fora_do_fast_por_extenso():
    try:
        import radai_sets as _rs
        nomes = sorted(nome_clinico(k) for k in _rs.FORA_DO_OAR_FAST)
    except Exception:
        nomes = []
    if not nomes:
        return "o que o FAST nao leva"
    if len(nomes) == 1:
        return nomes[0]
    return "%s e %s" % (", ".join(nomes[:-1]), nomes[-1])


def _textos_do_oar_fast(rotulo, versao_worker, sufixo_do_conjunto, suspeitas,
                        suavizadas, suavizar_mm, decimar_mm):
    rotulo_ = (rotulo or ROTULO_OAR_FAST)[:16]
    nome = "RadAI OAR_Fast (sugestao nao aprovada)"[:64]
    descricao = (
        "Conjunto entregue do modo FAST (%s): as estruturas do RadAI_OAR "
        "menos %s, montadas pelo mesmo pos-processamento "
        "do FULL, com os compostos suavizados INTEIROS (e nao a partir das "
        "partes)%s. NAO e copia de um FULL, e nao ha FULL ao lado dele. "
        % (rotulo_, _fora_do_fast_por_extenso(),
           (", e os pontos de cada contorno reduzidos (Douglas-Peucker, "
            "%.1f mm)" % float(decimar_mm)) if decimar_mm else "")
        + "Estruturas geradas automaticamente por Radioterapia.AI "
        "(TotalSegmentator%s). SUGESTAO NAO APROVADA: revisao e aprovacao "
        "sao ato medico e continuam obrigatorias no TPS. "
        "Sufixo '%s' em todos os nomes."
        % (" / worker " + versao_worker if versao_worker else "",
           sufixo_do_conjunto or SUFIXO_AI)
        + ((" %d estrutura(s) com volume abaixo do anatomicamente "
            "plausivel: %s. Entregues assim mesmo, para revisao."
            % (len(suspeitas), ", ".join(x[0] for x in suspeitas[:6])))
           if suspeitas else "")
        + (" Contornos SUAVIZADOS (escala %.1f, por estrutura): o contorno "
           "NAO e a saida crua do modelo." % (suavizar_mm or 0.0)
           if suavizadas else ""))
    serie = "RadAI OAR_Fast - SUGESTAO NAO APROVADA"[:64]
    return {"StructureSetLabel": rotulo_, "StructureSetName": nome,
            "StructureSetDescription": descricao, "SeriesDescription": serie,
            "SeriesNumber": 900}


THREADS_DO_POS = 4


def _em_paralelo(fn, itens):
    itens = list(itens)
    try:
        n = int(THREADS_DO_POS or 1)
    except Exception:
        n = 1
    if n <= 1 or len(itens) <= 1:
        return [fn(i) for i in itens]
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=min(n, len(itens))) as ex:
        return list(ex.map(fn, itens))


def _suavizar_individuais(masks, nomes, grade, suavizar_mm, detalhe, finas):
    import radai_geom
    tratadas = set()

    def _uma(nm):
        try:
            m = _bool_seguro(masks[nm])
        except Exception:
            return None
        fina = None
        try:
            mm_dela = suavizacao_de(str(nm).split(":")[-1], suavizar_mm)
            if mm_dela > 0:
                _fina, _raio = estrutura_fina(m, grade)
                if _fina:
                    fina = (str(nm), _raio)
                    mm_dela = 0.0
            if mm_dela <= 0 or int(m.sum()) < 10:
                return (fina, None, None)
            antes_n = int(m.sum())
            s = radai_geom.suavizar(m, mm_dela, grade)
            if not s.any():
                return (fina, None, None)
            depois_n = int(s.sum())
            comum = int((m & s).sum())
            return (fina, (str(nm), float(mm_dela), antes_n, depois_n,
                           (comum / float(antes_n)) if antes_n else 1.0), s)
        except Exception:
            return (fina, None, None)

    for nm, r in zip(nomes, _em_paralelo(_uma, nomes)):
        if r is None:
            continue
        tratadas.add(nm)
        fina, det, s = r
        if fina is not None:
            finas.append(fina)
        if det is not None:
            detalhe.append(det)
            masks[nm] = s
    return tratadas


def _reunir_e_fechar(nome, m, spec, masks, viz, reune, grade, log=None):
    import radai_geom
    extra = spec.get("reune_mascaras")
    contem = None
    if extra is not None:
        try:
            e = _bool_seguro(extra)
            if e.shape == m.shape:
                contem = e.copy()
        except Exception:
            contem = None
    if reune:
        for k in list(masks):
            if k == nome or str(k).startswith("_"):
                continue
            if _nomes.casa_prefixo(k, reune) is None:
                continue
            b = _bool_seguro(masks[k])
            if b.shape == m.shape:
                contem = b.copy() if contem is None else (contem | b)
    vx = float(np.prod(grade.spacing)) / 1000.0
    if contem is not None:
        fora_dela = int((contem & ~m).sum())
        if fora_dela:
            m = m | contem
            if log:
                log(u"   `%s`: +%.2f cm3 da estrutura que ela contem sempre"
                    % (nome, fora_dela * vx))
    fech = float(spec.get("fechar_mm") or 0.0)
    if fech > 0 and m.any():
        fechado = radai_geom.contrair(radai_geom.expandir(m, fech, grade),
                                      fech, grade)
        pode = np.ones(m.shape, dtype=bool) if viz is None else ~viz
        if contem is not None:
            pode = pode | radai_geom.expandir(contem, fech, grade)
        novo = fechado & pode & ~m
        if novo.any():
            m = m | novo
            if log:
                log(u"   `%s`: fechamento de %.1f mm, +%.2f cm3"
                    % (nome, fech, int(novo.sum()) * vx))
    return m


def _suavizar_construcoes(masks, grade, suavizar_mm, construcoes, detalhe,
                          finas, log=None):
    import radai_geom
    tratadas = set()
    nomes_constr = set(construcoes)

    def _conta(nome):
        tratada, fina, det = False, None, None
        try:
            m = _bool_seguro(masks[nome])
            if not m.any():
                return ("vazia", False, None, None, None, None)
            tratada = True
            spec = construcoes.get(nome) or {}
            mm = spec.get("suavizar_mm")
            mm = (suavizacao_de(nome, suavizar_mm) if mm is None
                  else float(mm))
            if mm > 0:
                mm += float(spec.get("suavizar_a_mais_mm") or 0.0)
            if mm > 0:
                _fina, _raio = estrutura_fina(m, grade)
                if _fina:
                    fina = (str(nome), _raio)
                    mm = 0.0
            if mm > 0 and int(m.sum()) >= 10:
                antes_n = int(m.sum())
                s = radai_geom.suavizar(m, mm, grade)
                if s.any():
                    comum = int((m & s).sum())
                    det = (str(nome), float(mm), antes_n, int(s.sum()),
                           (comum / float(antes_n)) if antes_n else 1.0)
                    m = s
            return ("ok", True, m, fina, det, None)
        except Exception as e:
            return ("erro", tratada, None, fina, None, e)

    _da_vez = [n for n in sorted(construcoes) if n in masks]
    _contas = dict(zip(_da_vez, _em_paralelo(_conta, _da_vez)))
    for nome in sorted(construcoes):
        if nome not in masks:
            continue
        spec = construcoes.get(nome) or {}
        try:
            _estado, _tratada, m, _fina_de, _det, _erro = _contas[nome]
            if _estado == "vazia":
                continue
            if _tratada:
                tratadas.add(nome)
            if _fina_de is not None:
                finas.append(_fina_de)
            if _estado == "erro":
                raise _erro
            if _det is not None:
                detalhe.append(_det)
            recorte = tuple(spec.get("recortar_por") or ())
            viz = None
            if recorte:
                for k in list(masks):
                    if k == nome or k in nomes_constr or str(k).startswith("_"):
                        continue
                    if _nomes.casa_prefixo(k, recorte) is None:
                        continue
                    b = _bool_seguro(masks[k])
                    viz = b.copy() if viz is None else (viz | b)
                if viz is not None:
                    novo = m & ~viz
                    if novo.any():
                        tirou = int(m.sum() - novo.sum())
                        m = novo
                        if log and tirou:
                            vx = float(np.prod(grade.spacing)) / 1000.0
                            log(u"   `%s` recortado de novo depois de "
                                u"suavizado: -%.1f cm3 nos vizinhos"
                                % (nome, tirou * vx))
                    elif log:
                        log(u"   `%s` ficaria VAZIO no recorte depois da "
                            u"suavizacao — nao recortei" % nome)
            reune = tuple(spec.get("reune") or ())
            if reune:
                volta = None
                for k in list(masks):
                    if k == nome or str(k).startswith("_"):
                        continue
                    if _nomes.casa_prefixo(k, reune) is None:
                        continue
                    b = _bool_seguro(masks[k])
                    volta = b.copy() if volta is None else (volta | b)
                if volta is not None:
                    fora_dela = int((volta & ~m).sum())
                    if fora_dela:
                        m = m | volta
                        if log:
                            vx = float(np.prod(grade.spacing)) / 1000.0
                            log(u"   `%s`: +%.2f cm3 do que ela contem por "
                                u"definicao (%s), que a suavizacao tinha "
                                u"deixado de fora" % (nome, fora_dela * vx,
                                                      u", ".join(reune)))
            m = _reunir_e_fechar(nome, m, spec, masks, viz, reune, grade,
                                 log)
            um_com = tuple(spec.get("um_volume_com") or ())
            if um_com and all(c in construcoes and c in masks
                              for c in um_com):
                um = radai_geom.maior_componente(m)
                caiu = int(m.sum() - um.sum())
                if caiu and um.any():
                    m = um
                    if log:
                        vx = float(np.prod(grade.spacing)) / 1000.0
                        log(u"   `%s`: um volume depois do recorte, -%.2f "
                            u"cm3 em pedaco(s) solto(s)" % (nome, caiu * vx))
            masks[nome] = m
        except Exception as e:
            if log:
                log(u"   construcao `%s` na segunda passada: %s — sai como "
                    u"estava" % (nome, str(e)[:100]))

    for nome in sorted(construcoes):
        if nome not in masks:
            continue
        recorte = tuple((construcoes.get(nome) or {}).get("recortar_por")
                        or ())
        if not recorte:
            continue
        prontas = [k for k in sorted(nomes_constr)
                   if k != nome and k in masks
                   and _nomes.casa_prefixo(k, recorte) is not None]
        if not prontas:
            continue
        try:
            m = _bool_seguro(masks[nome])
            viz = None
            for k in prontas:
                b = _bool_seguro(masks[k])
                viz = b.copy() if viz is None else (viz | b)
            novo = m & ~viz
            tirou = int(m.sum() - novo.sum())
            if not tirou:
                continue
            if novo.any():
                masks[nome] = novo
                if log:
                    vx = float(np.prod(grade.spacing)) / 1000.0
                    log(u"   `%s` recortado pelas construcoes prontas (%s): "
                        u"-%.2f cm3" % (nome, u", ".join(prontas), tirou * vx))
            elif log:
                log(u"   `%s` ficaria VAZIO no recorte pelas construcoes "
                    u"prontas — nao recortei" % nome)
        except Exception as e:
            if log:
                log(u"   construcao `%s`, recorte pelas construcoes prontas: "
                    u"%s — sai como estava" % (nome, str(e)[:100]))

    for nome in sorted(construcoes):
        if nome not in masks:
            continue
        spec = construcoes.get(nome) or {}
        try:
            if spec.get("um_volume"):
                m = _bool_seguro(masks[nome])
                um = radai_geom.maior_componente(m, conectividade=1)
                caiu = int(m.sum() - um.sum())
                if caiu and um.any():
                    masks[nome] = um
                    if log:
                        vx = float(np.prod(grade.spacing)) / 1000.0
                        log(u"   `%s`: um volume depois do recorte, -%.2f "
                            u"cm3" % (nome, caiu * vx))
            _acab = spec.get("acabamento")
            if callable(_acab):
                _kw_acab = {"log": log}
                try:
                    import inspect as _insp
                    if "spec" in _insp.signature(_acab).parameters:
                        _kw_acab["spec"] = spec
                except (TypeError, ValueError):
                    pass
                novo, desc, info = _acab(nome, masks[nome], masks, grade,
                                         **_kw_acab)
                if novo is not None and _bool_seguro(novo).any():
                    masks[nome] = novo
                spec["descricao_final"] = desc
                spec["medida_final"] = info
        except Exception as e:
            if log:
                log(u"   construcao `%s`, acabamento: %s — sai como estava"
                    % (nome, str(e)[:100]))

    for nome in sorted(construcoes):
        if nome not in masks or not (construcoes.get(nome) or {}).get(
                "um_contorno_por_corte"):
            continue
        try:
            import radai_skin as _sk
            _pul, _grd = _sk.ramos_da_parede(nome, masks)
            m, tirou = _sk.maior_contorno_por_corte(_bool_seguro(masks[nome]),
                                                     grade, pulmao=_pul,
                                                     costelas=_grd)
            if tirou and m.any():
                masks[nome] = m
                if log:
                    vx = float(np.prod(grade.spacing)) / 1000.0
                    log(u"   `%s`: um contorno por corte depois da segunda "
                        u"passada: -%.2f cm3" % (nome, tirou * vx))
        except Exception as e:
            if log:
                log(u"   construcao `%s`, um contorno por corte: %s — sai "
                    u"como estava" % (nome, str(e)[:100]))
    return tratadas


def _mascara_para_o_rt_utils(m):
    return np.transpose(m, (1, 2, 0))


PREFIXO_TEMP_DO_OAR = "radai_oar_"


def _renumerar_pelo_plano(ds, numero_por_nome):
    troca = {}
    for roi in getattr(ds, "StructureSetROISequence", None) or []:
        novo = (numero_por_nome or {}).get(str(getattr(roi, "ROIName", "")))
        if novo is not None:
            troca[int(roi.ROINumber)] = int(novo)
    if all(a == b for a, b in troca.items()):
        return 0
    for roi in ds.StructureSetROISequence:
        roi.ROINumber = troca.get(int(roi.ROINumber), int(roi.ROINumber))
    for chave in ("ROIContourSequence", "RTROIObservationsSequence"):
        for item in getattr(ds, chave, None) or []:
            n = int(getattr(item, "ReferencedROINumber", -1))
            if n in troca:
                item.ReferencedROINumber = troca[n]
    return sum(1 for a, b in troca.items() if a != b)


class ConjuntoPreparado(object):

    def __init__(self, caminho, gravar, gravar_selecao):
        self.caminho = str(caminho)
        self._gravar = gravar
        self._gravar_selecao = gravar_selecao

    def gravar_selecao(self, chaves, destino, versao_worker=u""):
        if self._gravar_selecao is None:
            raise RuntimeError(u"o conjunto preparado ja foi liberado")
        return self._gravar_selecao(chaves, destino, versao_worker)

    def gravar(self):
        if self._gravar is None:
            raise RuntimeError(u"o conjunto preparado ja foi liberado")
        try:
            return self._gravar()
        finally:
            self.liberar()

    def liberar(self):
        self._gravar = None
        self._gravar_selecao = None


def selecionar_do_full(preparo, mapa_nomes, permitidos, log=None, meta=None):
    if not hasattr(preparo, "gravar_selecao"):
        raise TypeError(u"o OAR sai do FULL preparado (build_rtstruct com "
                        u"adiar=True), e nao de um arquivo")
    permitidos = set(permitidos or ())
    ficam, fora = {}, []
    for chave, nome_final in (mapa_nomes or {}).items():
        if chave in permitidos and not str(chave).startswith("_"):
            ficam[chave] = nome_final
        else:
            fora.append(chave)
    conferir_sem_body(list(ficam.values()))
    m = dict(meta or {})
    destino = Path(tempfile.mkdtemp(prefix=PREFIXO_TEMP_DO_OAR)) / "RS.dcm"
    gravadas, etapas = preparo.gravar_selecao(set(ficam), destino,
                                              m.get("versao_worker", u""))
    if isinstance(meta, dict):
        meta["etapas"] = list(etapas)
    if log:
        try:
            log(u"OAR: %d estrutura(s) gravada(s) das mascaras finais do FULL, "
                u"antes dele; %d ficaram so no FULL" % (len(gravadas),
                                                        len(fora)))
            if fora:
                _f = sorted(set(str(x) for x in fora))
                log(u"OAR: fora da selecao: %s%s"
                    % (u", ".join(_f[:40]),
                       u" e mais %d" % (len(_f) - 40) if len(_f) > 40 else u""))
        except Exception:
            pass
    return str(destino), dict(gravadas), sorted(set(str(x) for x in fora))


def _salvar_sem_escrever_no_console(rt, caminho):
    # GUARDA: nada de `redirect_stdout` -- ele troca o `sys.stdout` do
    # processo inteiro, e duas gravacoes em threads diferentes podem deixa-lo
    # preso num buffer (a janela preta muda).
    ds = getattr(rt, "ds", None)
    if ds is None or not hasattr(ds, "save_as"):
        rt.save(str(caminho))
        return
    destino = str(caminho)
    if not destino.endswith(".dcm"):
        destino += ".dcm"
    try:
        gravar_dicom_em_fluxo(ds, destino)
    except OSError:
        raise Exception("Cannot write to file path '%s'" % destino)


def build_rtstruct(clean_dir, masks, tasks=None, versao_worker="", origem=None,
                   suavizar_mm=0.0, rotulo=None,
                   derivar=False, log=None, cru=False, descontar=False,
                   sufixo_do_conjunto=None, modalidade=None,
                   observacoes=None, construcoes=None, exigir_grade=False,
                   selecao=None, meta=None, externo=None, serie=None,
                   gravar=None, compostos_inteiros=False, decimar_mm=None,
                   modo=None, adiar=False):
    conferir_sem_body(list(masks or []))
    if cru and masks is not None:
        # GUARDA: o indice 26 nunca sai em RTSTRUCT, nem no cru.
        masks = vista_com_indice_26_fundido(masks)
        if isinstance(masks, _VistaComIndice26Fundido):
            observacoes = dict(observacoes or {})
            observacoes[masks._sac] = OBSERVACAO_DO_INDICE_26_NO_CRU
    origem = dict(origem or {})
    _etapas = []
    _t_etapa = [time.time()]

    def _marca(nome, rodou=True):
        agora = time.time()
        if rodou:
            _etapas.append((nome, agora - _t_etapa[0]))
        _t_etapa[0] = agora

    if modo != "fast":
        rt_path = Path(tempfile.mkdtemp()) / "RS.dcm"
    else:
        rt_path = Path(tempfile.mkdtemp(prefix=PREFIXO_TEMP_DO_OAR)) / "RS.dcm"
    # GUARDA: sem o sufixo por ROI duas chaves com o mesmo nome TG-263 (a
    # parótida do TS e a do VIII) virariam `Parotid_L_ai` e `Parotid1_L_ai`.
    sufixo_por_roi = dict((meta or {}).get("sufixo_por_roi") or {})
    grade = None
    _img_hu = None
    if not cru:
        try:
            import radai_geom
            if (serie is not None and len(serie) == 2
                    and serie[0] is not None and serie[1] is not None):
                grade = serie[0]
                _img_hu = np.array(serie[1], copy=True)
            else:
                _sitk_img = load_sitk(str(clean_dir))
                grade = radai_geom.Grade.de_sitk(_sitk_img)
                _img_hu = sitk.GetArrayFromImage(_sitk_img)
        except Exception as _e_grade:
            grade = None
            if exigir_grade:
                raise RuntimeError(
                    u"nao consegui carregar a grade da serie (%s: %s) — o "
                    u"conjunto do qual sai o entregue nao e gravado sem ela: "
                    u"nenhuma guarda rodaria"
                    % (type(_e_grade).__name__, str(_e_grade)[:120]))
            if log:
                try:
                    log(u"NAO carreguei a grade da serie (%s: %s) — neste "
                        u"conjunto (%s) nao rodam derivadas, contencao, "
                        u"desconto, suavizacao, sobreposicao, volume nem "
                        u"densidade" % (type(_e_grade).__name__,
                                        str(_e_grade)[:100],
                                        rotulo or "RadAI_OAR"))
                except Exception:
                    pass
    _modal = modalidade or (None if cru else _modalidade_da_serie(clean_dir))
    _hu_ok, _hu_pq = _hu_valido(_img_hu, _modal)
    _img_densidade = _img_hu if _hu_ok else None
    _marca(u"serie, grade e imagem", rodou=not cru)
    _fala = rotulo is None or selecao is not None or modo == "fast"
    if (not _hu_ok and _img_hu is not None and log is not None
            and _fala):
        try:
            log(u"pedaco no ar e sustentacao por densidade: NAO rodaram — %s"
                % _hu_pq)
        except Exception:
            pass
    suavizadas = 0
    detalhe = []
    finas = []
    descartadas = []

    ja_suavizadas = set()
    if derivar and grade is not None:
        try:
            masks = dict(masks)
            _ja = (meta or {}).get("derivadas") if isinstance(
                meta, dict) else None
            if isinstance(_ja, dict):
                # GUARDA: a derivacao ja rodou na cadeia do FULL; rodar de
                # novo sobre o colon sem o reto sobrescreveria o reto.
                criadas = [n for n in (_ja.get("criadas") or ())
                           if n in masks]
            else:
                protegidas = protegidas_da_origem(origem)
                criadas = aplicar_derivadas(masks, grade, log=log,
                                            protegidas=protegidas)
            for nome in criadas:
                origem[nome] = "derivada"
            if criadas and suavizar_mm and suavizar_mm > 0:
                import radai_geom
                grupo = set(criadas)
                for mae in DERIVADAS:
                    if mae in masks:
                        grupo.add(mae)
                juntos = radai_geom.suavizar_conjunto(
                    dict((k, masks[k]) for k in grupo), suavizar_mm, grade)
                masks.update(juntos)
                ja_suavizadas = grupo
        except Exception as exc:
            if log:
                try:
                    log("derivadas: %s" % str(exc)[:140])
                except Exception:
                    pass
    _marca(u"derivadas", rodou=bool(derivar and grade is not None))

    _gravar = None if gravar is None else set(gravar)
    if compostos_inteiros and not cru:
        _partes_fora = []
        masks = dict(masks)
        for comp, partes in COMPOSTOS.items():
            if comp not in masks:
                continue
            for p in partes:
                if p in masks and (_gravar is None or p not in _gravar):
                    del masks[p]
                    _partes_fora.append(p)
        if log and _partes_fora:
            try:
                log(u"compostos inteiros: %d parte(s) sairam depois das "
                    u"derivadas — cada composto e suavizado inteiro"
                    % len(_partes_fora))
            except Exception:
                pass

    if grade is not None and not cru:
        try:
            masks = dict(masks)
            limpar_fora_do_corpo(masks, _img_densidade, grade, log=log,
                                 externo=externo)
            aplicar_contencao(masks, grade, log=log)
            if descontar:
                aplicar_desconto(masks, grade, log=log)
        except Exception as exc:
            if log:
                try:
                    log("contencao anatomica: %s" % str(exc)[:140])
                except Exception:
                    pass
    _marca(u"fora do corpo, contencao e desconto",
           rodou=(grade is not None and not cru))

    if grade is not None and suavizar_mm and suavizar_mm > 0 and not cru:
        _constr = dict(construcoes or {})
        _compostos_com_partes = set(
            c for c, ps in COMPOSTOS.items()
            if c in masks and any(p in masks for p in ps))
        try:
            masks = dict(masks)
            feitas = suavizar_em_grupos(masks, grade, suavizar_mm, log=log,
                                        detalhe=detalhe, descontou=descontar,
                                        excluir=(set(_constr)
                                                 | _compostos_com_partes),
                                        compostos_inteiros=compostos_inteiros)
            ja_suavizadas = set(ja_suavizadas) | feitas
        except Exception as exc:
            if log:
                try:
                    log("fronteira compartilhada: %s" % str(exc)[:140])
                except Exception:
                    pass
        try:
            _orgaos = [n for n in sorted(masks)
                       if n not in ja_suavizadas and n not in _constr
                       and n not in _compostos_com_partes
                       and not str(n).startswith("_")]
            ja_suavizadas = set(ja_suavizadas) | _suavizar_individuais(
                masks, _orgaos, grade, suavizar_mm, detalhe, finas)
        except Exception as exc:
            if log:
                try:
                    log("suavizacao individual: %s" % str(exc)[:140])
                except Exception:
                    pass
        try:
            _de_vaso = set(COMPOSTOS_MENOS) if _constr else set()
            for c in recompor_compostos(masks, log=log, exceto=_de_vaso):
                ja_suavizadas.add(c)
        except Exception as exc:
            if log:
                try:
                    log("compostos: %s" % str(exc)[:140])
                except Exception:
                    pass
        if _constr:
            try:
                ja_suavizadas = set(ja_suavizadas) | _suavizar_construcoes(
                    masks, grade, suavizar_mm, _constr, detalhe, finas, log)
            except Exception as exc:
                if log:
                    try:
                        log("construcoes: %s" % str(exc)[:140])
                    except Exception:
                        pass
            for _nc, _sc in sorted(_constr.items()):
                if (_sc or {}).get("descricao_final"):
                    observacoes = dict(observacoes or {})
                    observacoes[_nc] = _sc["descricao_final"]
                    if isinstance(meta, dict) and _sc.get("medida_final"):
                        meta.setdefault("acabamento", {})[_nc] = dict(
                            _sc.get("medida_final") or {})
            try:
                for c in recompor_compostos(masks, log=log,
                                            so=set(COMPOSTOS_MENOS),
                                            subtrair=set(_constr),
                                            inteiros=compostos_inteiros):
                    ja_suavizadas.add(c)
            except Exception as exc:
                if log:
                    try:
                        log("compostos de vaso: %s" % str(exc)[:140])
                    except Exception:
                        pass
        suavizadas = len(detalhe)
    _marca(u"suavizacao (duas passadas) e compostos",
           rodou=bool(grade is not None and suavizar_mm and suavizar_mm > 0
                      and not cru))

    if _gravar is not None:
        _insumos = sorted(str(k) for k in masks
                          if k not in _gravar and not str(k).startswith("_"))
        if _insumos and log:
            try:
                log(u"insumo(s) que nao vao ao arquivo: %s"
                    % u", ".join(_insumos))
            except Exception:
                pass
    plano, usados = [], set()
    for nm in sorted(masks):
        if _gravar is not None and nm not in _gravar:
            continue
        if str(nm).startswith("_"):
            if log:
                try:
                    log("   marco interno `%s` nao vai para o RTSTRUCT" % nm)
                except Exception:
                    pass
            continue
        _n_vx = int(_bool_seguro(masks[nm]).sum())
        if _n_vx < 10:
            descartadas.append((nm, _n_vx))
            continue
        do_nv = str(nm).startswith(PREFIXO_NV)
        base = str(nm)[len(PREFIXO_NV):] if do_nv else nm
        motor_alt = ""
        if "@" in str(base):
            base, motor_alt = str(base).split("@", 1)
        if (str(base) in INDICE_26
                or _nomes.canonico(str(base)) in INDICE_26):
            # GUARDA: o segundo cinto da fusao do indice 26 ao sacro.
            if log:
                try:
                    log(u"   `%s` recusada: indice 26 deveria ter sido "
                        u"fundido ao sacro" % nm)
                except Exception:
                    pass
            continue
        sufixo = (sufixo_por_roi.get(nm)
                  or sufixo_de_procedencia(nm, origem, motor_alt,
                                           sufixo_do_conjunto or SUFIXO_AI))
        if base in SO_COMPARACAO and sufixo == SUFIXO_AI:
            continue
        nome_final = nome_clinico(base, usados, sufixo=sufixo)
        cor = ((list(_CORES_PAROTIDA_TS[base]) if (
            sufixo_por_roi.get(nm) == SUFIXO_TS and base in _CORES_PAROTIDA_TS)
            else None) or _color(base, do_nv))
        plano.append((nm, nome_final, cor,
                      "nv" if do_nv else origem.get(nm, "nosso")))
    tem_nv = any(e[3] == "nv" for e in plano)
    # GUARDA: o numero da ROI e a posicao no plano do FULL, em todo arquivo
    # que sai deste preparo: a mesma ROI tem o mesmo numero no OAR e no FULL.
    numero_no_plano = dict((e[1], i + 1) for i, e in enumerate(plano))
    if descartadas and log:
        try:
            log("NAO ENTRARAM no RTSTRUCT (menos de 10 voxels, nao formam "
                "contorno): %s" % ", ".join("%s (%d vx)" % (a, b)
                                            for a, b in descartadas[:10]))
        except Exception:
            pass
    if finas and log:
        try:
            log("estrutura fina: %d nao suavizada(s) — o que o TotalSegmentator "
                "entregou fica (raio inscrito < %.1f mm)"
                % (len(finas), ESPESSURA_FINA_MM))
            for nm, raio in sorted(finas, key=lambda x: x[1])[:10]:
                log("   %-22s raio %.2f mm" % (str(nm)[:22], raio))
            if len(finas) > 10:
                log("   e mais %d" % (len(finas) - 10))
        except Exception:
            pass
    if detalhe and log:
        try:
            piores = sorted(detalhe, key=lambda x: x[4])[:10]
            log("pos-processamento: %d estrutura(s) suavizadas "
                "(as que mais mudaram)" % len(detalhe))
            for nm, mm, a_n, d_n, mant in piores:
                log("   %-22s %.1f mm  %7d -> %7d vx (%+.1f%%)  "
                    "mantido %.0f%%"
                    % (str(nm)[:22], mm, a_n, d_n,
                       (d_n - a_n) / float(a_n) * 100.0 if a_n else 0.0,
                       mant * 100.0))
        except Exception:
            pass
    _densidade = {}

    def _escrever(destino, chaves=None, versao_oar=None, _marca=_marca,
                  zerar=False):
        do_oar = versao_oar is not None
        if zerar:
            _marca(u"gravacao", rodou=False)
        entradas = [e for e in plano if chaves is None or e[0] in chaves]
        rt = RTStructBuilder.create_new(dicom_series_path=str(clean_dir))
        mapa_nomes, mapa_origem, nao_entraram = {}, {}, []
        _ultimo_beat = time.time()
        for _i, (nm, nome_final, cor, de_onde) in enumerate(entradas):
            _agora = time.time()
            if log and (_agora - _ultimo_beat) >= 15.0:
                _ultimo_beat = _agora
                try:
                    log("   gravando o RTSTRUCT... %d de %d estruturas"
                        % (_i, len(entradas)))
                except Exception:
                    pass
            mapa_origem[nome_final] = de_onde
            mb = _mascara_para_o_rt_utils(_bool_seguro(masks[nm]))
            try:
                rt.add_roi(mask=mb, name=nome_final, color=cor)
                mapa_nomes[nm] = nome_final
            except Exception as _e1:
                nao_entraram.append(
                    (nome_final, "%s: %s" % (type(_e1).__name__,
                                             str(_e1)[:80])))
            del mb
        _marca(u"mascara em contorno (add_roi)")
        if nao_entraram and log:
            try:
                log("%sNAO ENTRARAM no RTSTRUCT (o add_roi recusou): %s"
                    % (u"OAR: " if do_oar else u"",
                       ", ".join("%s [%s]" % (a, b)
                                 for a, b in nao_entraram[:10])))
            except Exception:
                pass

        _cx = None
        if grade is not None:
            try:
                import radai_geom
                _cx = radai_geom.Caixas(masks)
            except Exception:
                _cx = None
        _no_arquivo = set(mapa_nomes)
        if grade is not None:
            if not do_oar:
                try:
                    pares = sobreposicoes(masks, grade, construcoes=construcoes,
                                          so=_no_arquivo, caixas=_cx)
                    for a, b, vol, fr in pares[:8]:
                        if log:
                            try:
                                log("SOBREPOSICAO: %s e %s ocupam %.2f cm3 em "
                                    "comum (%.1f%% da menor) — entregues "
                                    "assim mesmo; dois OAR sobrepostos fazem "
                                    "o DVH contar a mesma dose duas vezes"
                                    % (a, b, vol, fr * 100))
                            except Exception:
                                pass
                except Exception:
                    pass
            _estrita = (_no_arquivo if do_oar
                        else (None if adiar else selecao))
            if _estrita is not None:
                try:
                    _sel = set(k for k in masks
                               if k in set(_estrita) and k in _no_arquivo)
                    pares_oar = sobreposicoes(masks, grade,
                                              construcoes=construcoes or {},
                                              estrito=True, so=_sel,
                                              caixas=_cx)
                    if meta is not None:
                        meta["sobreposicoes_oar"] = list(pares_oar)
                    if log:
                        try:
                            if pares_oar:
                                for a, b, vol, fr in pares_oar[:8]:
                                    log("OAR: SOBREPOSICAO: %s e %s ocupam "
                                        "%.2f cm3 em comum (%.1f%% da "
                                        "menor) — no arquivo que vai ao "
                                        "plano, o DVH conta essa dose duas "
                                        "vezes" % (a, b, vol, fr * 100))
                            else:
                                log("OAR: sobreposicao conferida nas %d "
                                    "estrutura(s) selecionadas — nenhum par "
                                    "acima de %.0f%% da menor"
                                    % (len(_sel), FRACAO_SOBREPOSICAO * 100))
                        except Exception:
                            pass
                except Exception as exc:
                    if log:
                        try:
                            log("OAR: nao consegui conferir a sobreposicao da "
                                "selecao (%s)" % str(exc)[:120])
                        except Exception:
                            pass

        _marca(u"sobreposicao", rodou=(grade is not None))
        suspeitas = []
        if grade is not None:
            try:
                suspeitas, truncadas = implausiveis(masks, grade, caixas=_cx,
                                                    so=_no_arquivo)
                if not do_oar:
                    for nm_s, v_s, piso_s in suspeitas[:12]:
                        if log:
                            try:
                                log("SUSPEITA: %s saiu com %s cm3 (esperado "
                                    "ao menos %s) — entregue assim mesmo, "
                                    "marcada para revisao"
                                    % (nm_s, "%.3g" % v_s, "%.3g" % piso_s))
                            except Exception:
                                pass
                    for nm_i, qtd_i, d_i, f_i in componentes_distantes(
                            masks, grade, caixas=_cx, so=_no_arquivo)[:8]:
                        if log:
                            try:
                                log("SUSPEITA: %s tem %d pedaco(s) solto(s), "
                                    "o pior a %.0f mm do corpo principal e "
                                    "com %.1f%% do volume — entregue assim "
                                    "mesmo, marcado para revisao"
                                    % (nm_i, qtd_i, d_i, f_i * 100))
                            except Exception:
                                pass
                    if truncadas and log:
                        try:
                            log("cortadas pelo campo (o piso de volume nao se "
                                "aplica, e elas NAO foram julgadas): %s%s"
                                % (", ".join(truncadas[:8]),
                                   " e mais %d" % (len(truncadas) - 8)
                                   if len(truncadas) > 8 else ""))
                        except Exception:
                            pass
            except Exception:
                suspeitas = []
        _marca(u"plausibilidade (volume e pecas soltas)",
               rodou=(grade is not None))
        _salvar_sem_escrever_no_console(rt, destino)
        # GUARDA: o objeto do rt_utils (o Dataset e a serie inteira) morre
        # antes de o arquivo ser relido: com ele vivo, o conjunto fica duas
        # vezes na memoria no pico da gravacao.
        del rt
        gc.collect()
        ds = pydicom.dcmread(str(destino))
        _renumerar_pelo_plano(ds, numero_no_plano)
        ROTULO_MOTOR = {"nosso": "Radioterapia.AI / TotalSegmentator",
                        "ts": "TotalSegmentator (rotulos crus)",
                        "nv": "Radioterapia.AI / NV-Segment-CT",
                        "cads": "Radioterapia.AI / CADS",
                        "moose": "Radioterapia.AI / MOOSE (ENHANCE.PET)",
                        "hnlnl": "Radioterapia.AI / HNLNL (Weissmann et al. 2023)",
                        "cranio_ct": "Radioterapia.AI / encefalo TC (Buti et al. 2025)",
                        "derivada": "Radioterapia.AI (derivada por marco anatomico)"}
        for roi in getattr(ds, "StructureSetROISequence", []):
            de_onde = mapa_origem.get(str(getattr(roi, "ROIName", "")), "nosso")
            roi.ROIGenerationAlgorithm = "AUTOMATIC"
            roi.ROIGenerationDescription = ROTULO_MOTOR.get(de_onde, de_onde)[:64]
        try:
            _dxdy = _espacamento_no_plano(clean_dir)
        except Exception:
            _dxdy = None
        # GUARDA: contorno degenerado se REPARA, nunca se descarta (a ROI
        # sumiria calada); e antes da formatacao dos cortes.
        _pelos_pixels = set()
        _reparar_contornos_degenerados(ds, clean_dir, dxdy=_dxdy,
                                       reparados_ids=_pelos_pixels)
        _originais = guardar_contornos(ds)
        _formatados = set()
        if (suavizar_mm and suavizar_mm > 0) or _dxdy:
            _suavizar_contornos(ds, _dxdy if _dxdy else None,
                                suavizar=bool(suavizar_mm and suavizar_mm > 0),
                                formatados=_formatados, prontos=_pelos_pixels)
        if hasattr(ds, "ROIContourSequence"):
            for rc in ds.ROIContourSequence:
                for c in getattr(rc, "ContourSequence", []):
                    if hasattr(c, "ContourData") and id(c) not in _formatados:
                        c.ContourData = ["%.4f" % float(v) for v in c.ContourData]
        _laudo_dec = None
        if decimar_mm and float(decimar_mm) > 0 and not cru:
            _num_da_roi = dict(
                (str(getattr(r, "ROIName", "")), int(r.ROINumber))
                for r in getattr(ds, "StructureSetROISequence", []))
            _delgadas = set(_num_da_roi[nf] for k, nf in mapa_nomes.items()
                            if str(k) in ESTRUTURAS_DELGADAS
                            and nf in _num_da_roi)
            _laudo_dec = _decimar_contornos(ds, float(decimar_mm),
                                            poupar_rois=_delgadas)
            if log:
                try:
                    _a, _d = _laudo_dec["antes"], _laudo_dec["depois"]
                    log(u"decimacao (Douglas-Peucker, %.1f mm, >= %d pontos "
                        u"por poligono): %d -> %d pontos (-%d, %.0f%%) em %d "
                        u"contorno(s)" % (
                            float(decimar_mm), MIN_PONTOS_DECIMADO, _a, _d,
                            _a - _d, (100.0 * (_a - _d) / _a) if _a else 0.0,
                            _laudo_dec["contornos"]))
                    log(u"   poupados da decimacao: %d poligono(s) com menos "
                        u"de %.0f mm2 (estrutura pequena), %d que mudariam a "
                        u"area em mais de %.0f%% (forma fina) e %d de "
                        u"estrutura delgada (nervos e quiasma opticos, constritores)" % (
                            _laudo_dec.get("poupados_area", 0),
                            AREA_MINIMA_DECIMADA_MM2,
                            _laudo_dec.get("poupados_perda", 0),
                            100.0 * PERDA_MAXIMA_DECIMACAO,
                            _laudo_dec.get("poupados_delgadas", 0)))
                    _nome_roi = dict(
                        (int(r.ROINumber), str(getattr(r, "ROIName", "")))
                        for r in getattr(ds, "StructureSetROISequence", []))
                    _piores = sorted(
                        ((ad / aa - 1.0, num) for num, (pa, pd_, aa, ad)
                         in _laudo_dec["por_roi"].items() if aa > 0))[:3]
                    if _piores:
                        log(u"   a area que mais andou com a decimacao: %s"
                            % u", ".join(u"%s %+.1f%%" % (
                                _nome_roi.get(num, num), 100.0 * f)
                                for f, num in _piores))
                except Exception:
                    pass
            _marca(u"decimacao (Douglas-Peucker), com o acabamento dos "
                   u"contornos antes dela")
        files = sort_dcm([str(f) for f in Path(clean_dir).glob("*.dcm")])
        _charset = None
        if files:
            ref = pydicom.dcmread(files[len(files) // 2],
                                  stop_before_pixels=True, force=True)
            _charset = ref.get("SpecificCharacterSet", None)
            ds.SOPClassUID = pydicom.uid.UID("1.2.840.10008.5.1.4.1.1.481.3")
            ds.Modality = "RTSTRUCT"; ds.Manufacturer = "Radioterapia.AI"
            ds.ManufacturerModelName = "RadAI motor"
            ds.StudyInstanceUID = ref.StudyInstanceUID
            ds.SeriesInstanceUID = generate_uid()
            ds.FrameOfReferenceUID = getattr(ref, "FrameOfReferenceUID",
                                             generate_uid())
            ds.PatientName = getattr(ref, "PatientName", "^Radioterapia.AI")
            ds.PatientID = getattr(ref, "PatientID", "RADAI")
            ds.ApprovalStatus = "UNAPPROVED"
            if do_oar:
                _txt = _textos_do_conjunto(None, versao_oar, tem_nv,
                                           sufixo_do_conjunto, suspeitas,
                                           suavizadas, suavizar_mm)
            else:
                _txt = _textos_do_conjunto(rotulo, versao_worker, tem_nv,
                                           sufixo_do_conjunto, suspeitas,
                                           suavizadas, suavizar_mm, modo=modo,
                                           decimar_mm=(decimar_mm if _laudo_dec
                                                       is not None else None))
            ds.StructureSetLabel = _txt["StructureSetLabel"]
            ds.StructureSetName = _txt["StructureSetName"]
            ds.StructureSetDescription = _txt["StructureSetDescription"]
            ds.SeriesDescription = _txt["SeriesDescription"]
            ds.SeriesNumber = _txt["SeriesNumber"]
            agora = time.localtime()
            ds.StructureSetDate = time.strftime("%Y%m%d", agora)
            ds.StructureSetTime = time.strftime("%H%M%S", agora)
            ds.AccessionNumber = getattr(ref, "AccessionNumber", "")
            ds.ReferringPhysicianName = getattr(ref, "ReferringPhysicianName",
                                                "")
            ds.PositionReferenceIndicator = ""; ds.OperatorsName = ""
            for r in getattr(ds, "ReferencedFrameOfReferenceSequence", []):
                r.FrameOfReferenceUID = ds.FrameOfReferenceUID
            if hasattr(ds, "StructureSetROISequence"):
                _feitos_no_contorno = [n for n, rodou in (
                    (u"meio pixel", bool(_dxdy)),
                    (u"Taubin", bool(suavizar_mm and suavizar_mm > 0)))
                    if rodou]
                _marca(u"contornos (%s) e cabecalho" % u", ".join(
                    _feitos_no_contorno) if _feitos_no_contorno
                    else u"contornos e cabecalho")
                _laudo = {}
                try:
                    import radai_plausibility
                    if _hu_ok:
                        _log_dens = log if _fala else None
                        if log is not None and not _fala:
                            def _log_dens(m, _r=str(rotulo)):
                                log(u"%s: %s" % (_r, m))
                        # GUARDA: cada estrutura e medida uma vez por preparo;
                        # o OAR mede as dele, e o FULL so as que faltam.
                        _medir = dict((k, v) for k, v in masks.items()
                                      if k in _no_arquivo
                                      and k not in _densidade)
                        if _medir:
                            _feito = radai_plausibility.conferir_sustentacao(
                                _medir, grade, _img_densidade,
                                log=_log_dens,
                                modalidade="CT",
                                caixas=_cx) or {}
                            for _k in _medir:
                                _densidade[_k] = _feito.get(_k)
                        _laudo = dict((k, _densidade[k]) for k in _no_arquivo
                                      if _densidade.get(k) is not None)
                except ValueError:
                    raise
                except Exception:
                    _laudo = {}
                _marca(u"densidade (sustentacao)", rodou=bool(_hu_ok))
                _por_roi = {}
                for _k, _r in _laudo.items():
                    _por_roi[str(mapa_nomes.get(_k, _k))] = _r
                _cru_por_roi = {}
                for _k in masks:
                    _cru_por_roi[str(mapa_nomes.get(_k, _k))] = _k
                _obs = dict((k, str(v)) for k, v in dict(observacoes or {}).items()
                            if str(v or "").strip()
                            and (_gravar is None or k in _gravar)
                            and (chaves is None or k in chaves))
                _usadas_obs = set()
                obs = []
                for roi in ds.StructureSetROISequence:
                    o = pydicom.Dataset()
                    o.ObservationNumber = int(roi.ROINumber)
                    o.ReferencedROINumber = roi.ROINumber
                    o.RTROIInterpretedType = tipo_interpretado(_cru_por_roi.get(
                        str(getattr(roi, "ROIName", "")), ""))
                    o.ROIInterpreter = ""
                    _r = _por_roi.get(str(getattr(roi, "ROIName", "")))
                    if _r and _r.get("cod") in ("duvidosa", "super_segmentada",
                                                "interior_fora_da_janela"):
                        _n = ""
                        if _r.get("mediana_hu") is not None:
                            _n = (" Medido: mediana %s HU no interior, %d%% "
                                  "dele dentro da janela declarada de %s a %s "
                                  "HU (%d voxels)." % (
                                      _r["mediana_hu"],
                                      int(100 * (_r.get("fracao") or 0)),
                                      _r.get("janela_hu", [None, None])[0],
                                      _r.get("janela_hu", [None, None])[1],
                                      _r.get("voxels") or 0))
                        o.ROIObservationDescription = _para_dicom(
                            "RadAI: %s.%s %s" % (_r.get("frase", ""), _n,
                                                 radai_plausibility.COBERTURA))[:1024]
                    _nome_roi = str(getattr(roi, "ROIName", ""))
                    _res = RESSALVA_DE_ROI.get(_cru_por_roi.get(_nome_roi, ""))
                    if _res:
                        _antes = getattr(o, "ROIObservationDescription", "") or ""
                        o.ROIObservationDescription = _para_dicom(
                            (_antes + " " if _antes else "") + "RadAI: " + _res
                        )[:1024]
                    _cru_da_roi = _cru_por_roi.get(_nome_roi, "")
                    _ob = _obs.get(_cru_da_roi)
                    if _ob:
                        _usadas_obs.add(_cru_da_roi)
                        _nova = _para_dicom("RadAI: " + _ob)[:1024]
                        _antes = _para_dicom(
                            getattr(o, "ROIObservationDescription", "") or "")
                        _cabe = 1024 - len(_nova) - (1 if _antes else 0)
                        if _antes and len(_antes) > _cabe:
                            _antes = (_antes[:_cabe - 3] + "...") \
                                if _cabe >= 4 else ""
                        o.ROIObservationDescription = (
                            (_antes + " " if _antes else "") + _nova)[:1024]
                    obs.append(o); roi.ROIGenerationAlgorithm = "AUTOMATIC"
                ds.RTROIObservationsSequence = pydicom.Sequence(obs)
                _sobrou_obs = sorted(set(_obs) - _usadas_obs, key=str)
                if _sobrou_obs and log and not do_oar:
                    try:
                        log("observacao sem ROI no arquivo (a estrutura nao "
                            "entrou): %s" % ", ".join(str(k)
                                                      for k in _sobrou_obs[:10]))
                    except Exception:
                        pass
        _marca(u"descricao das ROIs")
        if meta is not None and not do_oar:
            try:
                meta.update({
                    "suspeitas": list(suspeitas or []),
                    "suavizadas": int(suavizadas),
                    "suavizar_mm": suavizar_mm,
                    "versao_worker": versao_worker,
                    "sufixo": sufixo_do_conjunto or SUFIXO_AI,
                    "tem_nv": tem_nv,
                    "descartadas": list(descartadas),
                    "nao_entraram": list(nao_entraram),
                    "finas": list(finas),
                    "suavizacao": list(detalhe),
                    "etapas": list(_etapas),
                })
                if _laudo_dec is not None:
                    meta["decimacao"] = dict(
                        (k, _laudo_dec[k]) for k in ("tol_mm", "contornos",
                                                     "antes", "depois",
                                                     "poupados_area",
                                                     "poupados_perda"))
                if meta.get("devolver_mascaras"):
                    meta["mascaras"] = masks
            except Exception:
                pass
        _lg = gravar_rtstruct(ds, destino, log=(None if do_oar else log),
                              originais=_originais, dxdy=_dxdy,
                              charset=_charset)
        del _originais
        _frase = frase_dos_contornos(_lg.get("contornos"))
        if do_oar and log and _frase:
            try:
                log(u"OAR: " + _frase)
            except Exception:
                pass
        return mapa_nomes

    if not adiar:
        return str(rt_path), _escrever(rt_path)

    def _gravar_selecao(chaves, destino, versao_oar):
        etapas_oar = []
        relogio = [time.time()]

        def _marca_do_oar(nome, rodou=True):
            agora = time.time()
            if rodou:
                etapas_oar.append((nome, agora - relogio[0]))
            relogio[0] = agora
        nomes = _escrever(destino, chaves=set(chaves),
                          versao_oar=versao_oar or u"",
                          _marca=_marca_do_oar)
        return nomes, etapas_oar

    def _gravar_o_full():
        return str(rt_path), _escrever(rt_path, zerar=True)

    return (ConjuntoPreparado(rt_path, _gravar_o_full, _gravar_selecao),
            dict((e[0], e[1]) for e in plano))


def _resolve_device(device):
    device = (device or "").strip().lower()
    if device == "cuda": device = "gpu"
    if device in ("gpu", "cpu"):
        return device
    try:
        import torch
        if torch.cuda.is_available(): return "gpu"
    except Exception: pass
    return "cpu"


def _achar_nvidia_smi():
    try:
        import radai_devices as _rd
        return _rd.achar_nvidia_smi()
    except Exception:
        return "nvidia-smi"


def versao_do_pacote(dist, mod=None):
    try:
        from importlib import metadata
        return metadata.version(dist)
    except Exception:
        pass
    v = getattr(mod, "__version__", None) if mod is not None else None
    return str(v) if v else u""


def inventario_de_computacao():
    import subprocess

    inv = {"nucleos": 0, "ram_gb": 0.0, "ram_livre_gb": 0.0,
           "placas": [], "torch_ve": 0, "torch_cuda": "", "torch_versao": "",
           "driver": "", "smi": "", "escolhido": "", "porque": ""}
    try:
        import multiprocessing
        inv["nucleos"] = multiprocessing.cpu_count()
    except Exception:
        pass
    try:
        import radai_cleaner
        m = radai_cleaner.memoria_da_estacao() or {}
        inv["ram_gb"] = round((m.get("total_mb") or 0) / 1024.0, 1)
        inv["ram_livre_gb"] = round((m.get("livre_mb") or 0) / 1024.0, 1)
    except Exception:
        pass

    inv["smi"] = ""
    try:
        saida = subprocess.run(
            [_achar_nvidia_smi(),
             "--query-gpu=name,memory.total,memory.used,driver_version",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=20)
        for linha in (saida.stdout or "").strip().splitlines():
            campos = [c.strip() for c in linha.split(",")]
            if len(campos) >= 4:
                inv["placas"].append({"nome": campos[0],
                                      "vram_mb": campos[1],
                                      "usada_mb": campos[2]})
                inv["driver"] = campos[3]
        if not inv["placas"]:
            inv["smi"] = (u"nvidia-smi respondeu e nao listou placa"
                          if saida.returncode == 0
                          else u"nvidia-smi saiu com codigo %s"
                               % saida.returncode)
    except FileNotFoundError:
        inv["smi"] = u"nvidia-smi nao esta no PATH"
    except Exception as e:
        inv["smi"] = u"nvidia-smi nao respondeu (%s)" % type(e).__name__

    try:
        import torch
        inv["torch_versao"] = versao_do_pacote("torch", torch)
        inv["torch_cuda"] = getattr(getattr(torch, "version", None), "cuda", "") or ""
        if torch.cuda.is_available():
            inv["torch_ve"] = torch.cuda.device_count()
    except Exception:
        pass
    return inv


def escolher_dispositivo(pedido="auto", inv=None):
    inv = inv or inventario_de_computacao()
    pedido = str(pedido or "auto").strip().lower()
    if pedido == "cpu":
        return "cpu", u"pedido no config (DEVICE=cpu)"
    if inv.get("torch_ve"):
        idx, porque = 0, u"%d placa(s) alcancadas pelo torch" % inv["torch_ve"]
        try:
            livres = []
            for i, p in enumerate(inv.get("placas") or []):
                livres.append((float(p["vram_mb"]) - float(p["usada_mb"]), i))
            if len(livres) > 1:
                livres.sort(reverse=True)
                idx = livres[0][1]
                porque = (u"%d placas; escolhida a de indice %d, com mais VRAM "
                          u"livre (a outra costuma ser a do monitor)"
                          % (len(livres), idx))
        except Exception:
            pass
        return ("gpu" if idx == 0 else "cuda:%d" % idx), porque
    if inv.get("placas"):
        return "cpu", (u"ha %d placa(s) (driver %s) e o torch %s (cuda %s) NAO "
                       u"as alcanca -- conferir driver contra a versao do cuda"
                       % (len(inv["placas"]), inv.get("driver") or "?",
                          inv.get("torch_versao") or "?",
                          inv.get("torch_cuda") or "sem cuda"))
    return "cpu", u"nenhuma GPU encontrada nesta maquina"


def diagnostico_de_computacao(pedido="auto"):
    inv = inventario_de_computacao()
    disp, porque = escolher_dispositivo(pedido, inv)
    partes = []
    if inv["placas"]:
        for p in inv["placas"]:
            try:
                livre = float(p["vram_mb"]) - float(p["usada_mb"])
            except Exception:
                livre = 0.0
            partes.append("%s (%.1f GB livres de %s MB)"
                          % (p["nome"], livre / 1024.0, p["vram_mb"]))
        partes.append("driver %s" % (inv.get("driver") or "?"))
    elif inv.get("torch_ve"):
        partes.append("o torch alcanca placa, mas %s — sem VRAM medida"
                      % (inv.get("smi") or "nao consegui consultar a placa"))
    else:
        partes.append("sem GPU (%s)"
                      % (inv.get("smi") or "nenhuma placa listada"))
    partes.append("torch %s (cuda %s), alcanca %d placa(s)"
                  % (inv.get("torch_versao") or "?",
                     inv.get("torch_cuda") or "-", inv.get("torch_ve", 0)))
    partes.append("USANDO: %s — %s" % (disp, porque))
    if disp != "cpu" and inv.get("placas"):
        try:
            p = inv["placas"][0]
            livre = (float(p["vram_mb"]) - float(p["usada_mb"])) / 1024.0
            if livre < 3.0:
                partes.append(
                    u"ATENCAO: so %.1f GB de VRAM livres — a serie pode "
                    u"levar varias vezes mais; feche o que estiver usando "
                    u"a placa (navegador, Teams, visualizador)" % livre)
        except Exception:
            pass
    return " | ".join(partes)


GRADE_BASE_MM = 1.5

PARAMETROS_DA_REDE = 31215719
PESOS_MB = 120
ATIVACOES_FP16_MB = 846
ATIVACOES_FP32_MB = 1693
COPIA_FP16_PESOS_MB = 60
PATCHES_MB = 32
GAUSSIANA_MB = 4
CONTEXTO_CUDA_MB = 300

MARGEM_MINIMA_MB = 768
MARGEM_FRACAO = 0.15
MARGEM_REDE_MB = 256

TEMPO_NVIDIA_SMI_S = 20
TEMPO_TORCH_S = 90

NOME_DA_PARTE = {
    831: u"orgaos", 832: u"vertebras", 833: u"cardiaco", 834: u"musculos",
    835: u"costelas",
    291: u"orgaos", 292: u"vertebras", 293: u"cardiaco", 294: u"musculos",
    295: u"costelas",
    850: u"orgaos", 851: u"musculos",
}


def usar_autocast(capacidade):
    return True


def _mib(v):
    return int(math.ceil(float(v) / 1048576.0))


def _gib(mb):
    try:
        g = float(mb) / 1024.0
        return ((u"%.2f" if g < 1.0 else u"%.1f") % g).replace(".", ",")
    except Exception:
        return u"?"


def _vram_por_placa():
    import subprocess
    placas, erros = [], []
    try:
        r = subprocess.run(
            [_achar_nvidia_smi(),
             "--query-gpu=index,name,memory.total,memory.free",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=TEMPO_NVIDIA_SMI_S)
        descartadas = []
        if r.returncode == 0:
            for linha in (r.stdout or "").strip().splitlines():
                if not linha.strip():
                    continue
                c = [x.strip() for x in linha.split(",")]
                if len(c) < 4:
                    descartadas.append(linha.strip())
                    continue
                try:
                    placas.append({"indice": int(c[0]),
                                   "nome": ", ".join(c[1:-2]),
                                   "total_mb": int(float(c[-2])),
                                   "livre_mb": int(float(c[-1])),
                                   "capacidade": None})
                except ValueError:
                    descartadas.append(linha.strip())
                    continue
        if r.returncode == 0 and not placas and descartadas:
            erros.append(u"nvidia-smi respondeu e nenhuma linha se leu como "
                         u"placa (%d linha(s); a primeira: %r)"
                         % (len(descartadas), descartadas[0][:80]))
        elif r.returncode == 0:
            aviso = u""
            if placas:
                try:
                    r2 = subprocess.run(
                        [_achar_nvidia_smi(), "--query-gpu=index,compute_cap",
                         "--format=csv,noheader,nounits"],
                        capture_output=True, text=True,
                        timeout=TEMPO_NVIDIA_SMI_S)
                    if r2.returncode == 0:
                        cap = {}
                        for linha in (r2.stdout or "").strip().splitlines():
                            c = [x.strip() for x in linha.split(",")]
                            if (len(c) == 2 and c[0].isdigit()
                                    and re.match(r"^\d+\.\d+$", c[1])):
                                cap[int(c[0])] = c[1]
                        for p in placas:
                            p["capacidade"] = cap.get(p["indice"])
                        sem = [str(p["indice"]) for p in placas
                               if not p["capacidade"]]
                        if sem:
                            bruto = (r2.stdout or "").strip().splitlines()
                            aviso = (u"compute_cap sem valor para a placa %s "
                                     u"(o nvidia-smi respondeu %r)"
                                     % (", ".join(sem),
                                        (bruto[0] if bruto else u"")[:60]))
                    else:
                        ult = [x for x in ((r2.stderr or "") + "\n"
                                           + (r2.stdout or "")).strip()
                               .splitlines() if x.strip()]
                        aviso = (u"compute_cap nao lida: o nvidia-smi saiu com "
                                 u"codigo %s (%s)"
                                 % (r2.returncode,
                                    (ult[-1].strip() if ult else u"")[:120]))
                except Exception as e:
                    aviso = (u"compute_cap nao lida: %s (%s)"
                             % (type(e).__name__, str(e)[:80]))
            return {"placas": placas, "erro": "", "fonte": "nvidia-smi",
                    "aviso": aviso}
        if r.returncode != 0:
            erros.append(u"nvidia-smi saiu com codigo %s" % r.returncode)
    except FileNotFoundError:
        erros.append(u"nvidia-smi nao encontrado")
    except Exception as e:
        erros.append(u"nvidia-smi nao respondeu (%s)" % type(e).__name__)

    codigo = (
        "import torch\n"
        "n = torch.cuda.device_count() if torch.cuda.is_available() else 0\n"
        "for i in range(n):\n"
        "    l, t = torch.cuda.mem_get_info(i)\n"
        "    c = torch.cuda.get_device_capability(i)\n"
        "    print('RADAI|%d|%d|%d|%d.%d|%s' % (i, t // 1048576, "
        "l // 1048576, c[0], c[1], torch.cuda.get_device_name(i)))\n")
    try:
        r = subprocess.run([sys.executable, "-c", codigo],
                           capture_output=True, text=True,
                           timeout=TEMPO_TORCH_S,
                           env=dict(os.environ, CUDA_DEVICE_ORDER="PCI_BUS_ID"))
        if r.returncode == 0:
            for linha in (r.stdout or "").splitlines():
                if not linha.startswith("RADAI|"):
                    continue
                c = linha.split("|", 5)
                try:
                    placas.append({"indice": int(c[1]), "total_mb": int(c[2]),
                                   "livre_mb": int(c[3]), "capacidade": c[4],
                                   "nome": c[5].strip()})
                except (ValueError, IndexError):
                    continue
            return {"placas": placas, "erro": "", "fonte": "torch",
                    "aviso": u"", "recuo": u"; ".join(erros)}
        ult = [x for x in (r.stderr or "").strip().splitlines() if x.strip()]
        erros.append(u"torch saiu com codigo %s (%s)"
                     % (r.returncode, (ult[-1] if ult else "")[:120]))
    except Exception as e:
        erros.append(u"torch nao respondeu (%s)" % type(e).__name__)
    return {"placas": [], "erro": u"; ".join(erros), "fonte": ""}


def _classes_por_parte(task):
    nome = _nome_biblioteca(task)
    causa = u"a biblioteca nao tem esta task"
    try:
        import totalsegmentator.map_to_binary as mb
        por_task = {"total": "class_map_5_parts",
                    "total_v3": "class_map_5_parts_total_v3",
                    "total_mr": "class_map_parts_mr",
                    "headneck_muscles": "class_map_parts_headneck_muscles"}
        if nome in por_task and hasattr(mb, por_task[nome]):
            partes = getattr(mb, por_task[nome])
            ns = [len(v) for k, v in partes.items() if k != "test" and v]
            if ns:
                return ns, u"class_map da biblioteca"
        if nome in mb.class_map:
            return [len(mb.class_map[nome])], u"class_map da biblioteca"
    except Exception as e:
        causa = u"a biblioteca nao importou: %s" % type(e).__name__
    causa_cat = u"o catalogo nao tem a task"
    try:
        import radai_tasks
        d = radai_tasks.POR_NOME.get(task) or {}
        if d.get("classes"):
            return [int(d["classes"])], (u"catalogo, como UMA rede (%s)"
                                         % causa)
        if task in radai_tasks.POR_NOME:
            causa_cat = u"o catalogo nao diz quantas classes a task tem"
    except Exception as e:
        causa_cat = u"o catalogo levantou %s: %s" % (type(e).__name__,
                                                     str(e)[:80])
    return [120], (u"120 classes, para cima (%s; %s)" % (causa, causa_cat))


def _grade_do_modelo(task, avisos=None):
    try:
        import radai_tasks
        z = radai_tasks.Z_DO_MODELO.get(task)
        if z:
            return float(z)
    except Exception as e:
        if avisos is not None:
            avisos.append(u"grade do modelo pelo recuo de %s mm: o catalogo "
                          u"levantou %s: %s" % (
                              (u"%.1f" % GRADE_BASE_MM).replace(".", ","),
                              type(e).__name__, str(e)[:80]))
    return GRADE_BASE_MM


def _pico_das_partes(voxels, partes, fixo, ativ, dados, n_pred):
    tudo, isinf_max, fase = 0, 0, u"patches"
    for c in partes:
        cab = int(c) + 1
        resultado = (dados + n_pred + _mib(cab * voxels * 2)
                     + GAUSSIANA_MB)
        isinf = _mib(cab * voxels)
        esta = fixo + resultado + max(ativ, isinf)
        if esta > tudo:
            tudo = esta
            fase = u"isinf" if isinf > ativ else u"patches"
        isinf_max = max(isinf_max, isinf)
    return tudo, isinf_max, fase


PISO_DE_RAM_DA_TASK_MB = 4096
FATOR_DE_RAM_DA_TASK = 1.0
MARGEM_DO_COMMIT_MB = 1024
CONTA_MINIMA_PARA_ADIAR_MB = 1024


def voxels_no_modelo(task, forma_zyx, espacamento_zyx):
    grade = _grade_do_modelo(task)
    v = 1
    for n, e in zip(forma_zyx, espacamento_zyx):
        v *= max(1, int(math.ceil(float(n) * float(e) / grade)))
    return v


def estimativa_de_ram(task, forma_zyx, espacamento_zyx, caixa_zyx=None,
                      partes=None):
    forma = tuple(int(n) for n in forma_zyx)
    regiao = u"a grade inteira"
    if caixa_zyx:
        forma = tuple(max(1, int(b) - int(a)) for a, b in caixa_zyx)
        regiao = u"a caixa da regiao"
    voxels = voxels_no_modelo(task, forma, espacamento_zyx)
    if partes is None:
        partes, _de_onde = _classes_por_parte(task)
    fixo = CONTEXTO_CUDA_MB + PESOS_MB + PATCHES_MB + COPIA_FP16_PESOS_MB
    variavel, _i, _f = _pico_das_partes(voxels, list(partes), 0, 0,
                                        _mib(voxels * 4), _mib(voxels * 2))
    conta = int(FATOR_DE_RAM_DA_TASK * variavel)
    return {"precisa_mb": max(PISO_DE_RAM_DA_TASK_MB,
                              conta + fixo + ATIVACOES_FP16_MB),
            "conta_mb": conta, "voxels": voxels, "regiao": regiao}


def memoria_do_processo_mb(pid=None):
    try:
        import radai_cleaner
        return radai_cleaner.memoria_do_processo_mb(pid)
    except Exception:
        return None


def memoria_e_commit():
    try:
        import radai_cleaner
        m = radai_cleaner.memoria_da_estacao() or {}
        if not m.get("total_mb"):
            return None
        fora = {"total_mb": int(m["total_mb"]),
                "livre_mb": int(m.get("livre_mb") or 0),
                "pct": int(m.get("pct") or 0),
                "commit_total_mb": int(m.get("commit_total_mb") or 0),
                "commit_livre_mb": int(m.get("commit_livre_mb") or 0)}
        if m.get("commit_livre_no_teto_mb"):
            fora["commit_livre_no_teto_mb"] = int(m["commit_livre_no_teto_mb"])
        return fora
    except Exception:
        return None


def decidir_ram(estimativa, memoria):
    if not estimativa or not memoria or not memoria.get("commit_livre_mb"):
        return "cabe", u"RAM sem medida de commit: segue sem o plano de RAM"
    precisa, conta = estimativa["precisa_mb"], estimativa["conta_mb"]
    livre, commit = memoria["livre_mb"], memoria["commit_livre_mb"]
    nums = (u"precisa ~%s GiB (%s), RAM livre %s GiB, commit livre %s GiB"
            % (_gib(precisa), estimativa.get("regiao") or u"?", _gib(livre),
               _gib(commit)))
    teto = memoria.get("commit_livre_no_teto_mb")
    if (conta >= CONTA_MINIMA_PARA_ADIAR_MB
            and precisa > commit - MARGEM_DO_COMMIT_MB):
        # GUARDA: com a paginacao que cresce (gerenciada pelo sistema), o
        # commit livre de agora nao e o teto; adia so acima do teto.
        if teto and precisa <= teto - MARGEM_DO_COMMIT_MB:
            return "paginar", (u"%s; o Windows cresce a paginacao ate %s GiB "
                               u"de commit livre (teto usado)"
                               % (nums, _gib(teto)))
        return "adiar", (nums + (u"; teto da paginacao %s GiB" % _gib(teto)
                                 if teto else u""))
    if precisa > livre:
        return "paginar", nums
    return "cabe", nums


def plano_de_dispositivo(forma_zyx, espacamento_zyx, task="total_v3", inv=None,
                         partes=None):
    plano = {"modo": "cpu", "motivo": u"", "vram_livre_mb": 0,
             "vram_total_mb": 0, "precisa_tudo_mb": 0, "precisa_rede_mb": 0,
             "margem_mb": 0, "margem_rede_mb": 0, "isinf_mb": 0,
             "fase_do_pico": u"", "placa": u"", "indice": None,
             "capacidade": None, "voxels": 0}
    try:
        avisos = []
        grade = _grade_do_modelo(task, avisos=avisos)
        voxels = 1
        for n, e in zip(forma_zyx, espacamento_zyx):
            voxels *= max(1, int(math.ceil(float(n) * float(e) / grade)))
        plano["voxels"] = voxels
        if partes is None:
            partes, de_onde = _classes_por_parte(task)
        else:
            partes, de_onde = list(partes), u"dublado"
        cabecas = max(int(c) for c in partes) + 1

        inv = _vram_por_placa() if inv is None else inv
        placas = list((inv or {}).get("placas") or [])
        if not placas:
            erro = (inv or {}).get("erro") or u""
            recuo = (inv or {}).get("recuo") or u""
            plano["motivo"] = (
                u"cpu: nao consegui medir a VRAM (%s) — sem medida nao "
                u"arrisco a placa" % erro if erro
                else u"cpu: nenhuma placa NVIDIA nesta maquina%s" % (
                    (u" (o torch nao viu placa; antes: %s)" % recuo)
                    if recuo else u""))
            return plano
        placa = sorted(placas, key=lambda p: (-int(p.get("livre_mb") or 0),
                                              int(p.get("indice") or 0)))[0]
        livre = int(placa.get("livre_mb") or 0)
        total = int(placa.get("total_mb") or 0)
        cap = placa.get("capacidade")
        auto = usar_autocast(cap)
        ativ = ATIVACOES_FP16_MB if auto else ATIVACOES_FP32_MB
        fixo = (CONTEXTO_CUDA_MB + PESOS_MB + PATCHES_MB
                + (COPIA_FP16_PESOS_MB if auto else 0))
        rede = fixo + ativ
        dados = _mib(voxels * 4)
        n_pred = _mib(voxels * 2)
        tudo, isinf_max, fase = _pico_das_partes(voxels, partes, fixo, ativ,
                                                 dados, n_pred)
        margem = max(MARGEM_MINIMA_MB, int(MARGEM_FRACAO * total))
        margem_rede = int(MARGEM_REDE_MB)
        plano.update({"vram_livre_mb": livre, "vram_total_mb": total,
                      "precisa_tudo_mb": tudo, "precisa_rede_mb": rede,
                      "margem_mb": margem, "margem_rede_mb": margem_rede,
                      "isinf_mb": isinf_max, "fase_do_pico": fase,
                      "placa": placa.get("nome") or u"?",
                      "indice": placa.get("indice"), "capacidade": cap})
        if livre >= tudo + margem:
            plano["modo"] = "gpu"
        elif livre >= rede + margem_rede:
            plano["modo"] = "gpu_resultado_na_cpu"
        else:
            plano["modo"] = "cpu"
        if cap:
            sm = u", sm %s" % cap
        else:
            sm = (u", sm nao lido: %s — o criterio do autocast decide sem o "
                  u"dado (autocast %s)"
                  % ((inv or {}).get("aviso")
                     or u"o inventario nao trouxe a causa",
                     u"ligado" if usar_autocast(None) else u"desligado"))
        fonte = u""
        if (inv or {}).get("fonte") == "torch":
            fonte = u", medida pelo torch%s" % (
                (u" (%s)" % inv["recuo"]) if (inv or {}).get("recuo") else u"")
        onde = u"%s (placa %s%s) com %s GiB livres de %s%s" % (
            plano["placa"], plano["indice"], sm, _gib(livre), _gib(total),
            fonte)
        serie = (u"a serie vira %s M voxels a %s mm, ate %d classes por "
                 u"rede (%s)%s" % ((u"%.1f" % (voxels / 1e6)).replace(".", ","),
                                   (u"%.2f" % grade).rstrip("0").rstrip(",.")
                                   .replace(".", ","),
                                   cabecas - 1, de_onde,
                                   (u"; " + u"; ".join(avisos)) if avisos
                                   else u""))
        c_tudo = (u"tudo na placa precisa %s GiB (%s) + margem %s do degrau "
                  u"placa/RAM = %s, livre %s" % (
                      _gib(tudo),
                      u"o fim da parte, o isinf, pesa mais que os patches"
                      if fase == u"isinf" else u"a fase dos patches manda",
                      _gib(margem), _gib(tudo + margem), _gib(livre)))
        c_rede = (u"so a rede precisa %s GiB (ativacao %s %d MiB) + margem "
                  u"%s do degrau rede/CPU = %s, livre %s" % (
                      _gib(rede), u"fp16" if auto else u"fp32", ativ,
                      _gib(margem_rede), _gib(rede + margem_rede),
                      _gib(livre)))
        if plano["modo"] == "gpu":
            plano["motivo"] = u"gpu: %s | %s | %s — cabe" % (onde, serie,
                                                             c_tudo)
        elif plano["modo"] == "gpu_resultado_na_cpu":
            plano["motivo"] = (
                u"gpu_resultado_na_cpu: %s | %s | %s — nao cabe | %s — cabe: "
                u"a rede fica na placa e o resultado vai para a RAM (~1 min a "
                u"mais numa serie de planejamento, medido na pesquisa G2); se "
                u"a placa faltar no meio, a CPU refaz a task"
                % (onde, serie, c_tudo, c_rede))
        else:
            plano["motivo"] = (
                u"cpu: %s | %s | %s — nao cabe: a placa nao tem espaco seguro "
                u"nem para a rede sozinha" % (onde, serie, c_rede))
        return plano
    except Exception as e:
        plano["modo"] = "cpu"
        plano["motivo"] = (u"cpu: nao consegui montar o plano (%s: %s)"
                           % (type(e).__name__, str(e)[:120]))
        return plano


def _canonico(v):
    if callable(v):
        return getattr(v, "__name__", u"?")
    if isinstance(v, dict):
        return [[_canonico(k), _canonico(x)] for k, x in
                sorted(v.items(), key=lambda kv: u"%s" % (kv[0],))]
    if isinstance(v, (list, tuple)):
        return [_canonico(x) for x in v]
    if isinstance(v, (set, frozenset)):
        return sorted(_canonico(x) for x in v)
    if isinstance(v, float):
        return repr(round(v, 6))
    return v if isinstance(v, (int, bool, type(None))) else u"%s" % (v,)


MODULOS_DO_POS = ("radai_skin", "radai_constructs",
                  "radai_hnlnl", "radai_geom", "radai_names",
                  "radai_plausibility", "radai_output")
RAIZES_DO_POS_NO_MOTOR = ("ORDEM_DO_FULL", "CONSTRUCOES", "preparar_full",
                          "aplicar_regras_de_gravacao", "selecionar_do_full",
                          "build_rtstruct")


def _fonte_do_modulo(nome):
    import importlib as _il
    import io as _io
    mod = sys.modules.get(nome) or _il.import_module(nome)
    with _io.open(mod.__file__, encoding="utf-8") as f:
        return f.read()


def _sem_docstrings(arvore):
    import ast as _ast
    for no in _ast.walk(arvore):
        if isinstance(no, (_ast.Module, _ast.FunctionDef,
                           _ast.AsyncFunctionDef, _ast.ClassDef)):
            c = no.body
            if (c and isinstance(c[0], _ast.Expr)
                    and isinstance(getattr(c[0], "value", None), _ast.Constant)
                    and isinstance(c[0].value.value, str)):
                no.body = c[1:] or [_ast.Pass()]
    return arvore


def _codigo_do_pos_no_motor(fonte, raizes=RAIZES_DO_POS_NO_MOTOR):
    import ast as _ast
    arvore = _sem_docstrings(_ast.parse(fonte))
    nos = {}
    for n in arvore.body:
        if isinstance(n, (_ast.FunctionDef, _ast.AsyncFunctionDef,
                          _ast.ClassDef)):
            nos.setdefault(n.name, []).append(n)
        elif isinstance(n, (_ast.Assign, _ast.AnnAssign, _ast.AugAssign)):
            alvos = n.targets if isinstance(n, _ast.Assign) else [n.target]
            for a in alvos:
                if isinstance(a, _ast.Name):
                    nos.setdefault(a.id, []).append(n)
        elif isinstance(n, _ast.Expr) and isinstance(n.value, _ast.Call):
            f = n.value.func
            if (isinstance(f, _ast.Attribute)
                    and isinstance(f.value, _ast.Name)):
                nos.setdefault(f.value.id, []).append(n)
    vistos, fila, partes = set(), list(raizes), []
    while fila:
        nome = fila.pop()
        if nome in vistos or nome not in nos:
            continue
        vistos.add(nome)
        for no in nos[nome]:
            partes.append(_ast.dump(no))
            for sub in _ast.walk(no):
                if isinstance(sub, _ast.Name) and sub.id not in vistos:
                    fila.append(sub.id)
    return sorted(set(partes))


def receita_do_pos():
    import ast as _ast
    import hashlib as _h
    import json as _j
    tabelas = {}
    for nome in ("ORDEM_DO_FULL", "COMPOSTOS", "RECORTE_DE_OAR",
                 "MARGEM_OAR_MM", "VOLUME_MAXIMO_NA_BORDA_CM3",
                 "FRACAO_DA_PODA", "VOLUME_DA_PODA_CM3", "GRANDES", "PODA",
                 "NUNCA_PODA_PALAVRAS", "NUNCA_PODA_PREFIXOS",
                 "DESCONTADAS_DE", "DECIMACAO_FAST_MM", "SUAVIZACAO",
                 "CONSTRUCOES"):
        tabelas[nome] = _canonico(globals().get(nome))
    codigo = {}
    try:
        codigo["engine"] = _h.sha256(u"\n".join(_codigo_do_pos_no_motor(
            _fonte_do_modulo("engine"))).encode("utf-8")).hexdigest()
    except Exception as e:
        codigo["engine"] = u"?%s" % type(e).__name__
    for m in MODULOS_DO_POS:
        try:
            codigo[m] = _h.sha256(_ast.dump(_sem_docstrings(_ast.parse(
                _fonte_do_modulo(m)))).encode("utf-8")).hexdigest()
        except Exception as e:
            codigo[m] = u"?%s" % type(e).__name__
    try:
        return _h.sha256(_j.dumps({"tabelas": tabelas, "codigo": codigo},
                                  sort_keys=True, ensure_ascii=True,
                                  default=str).encode("ascii")).hexdigest()[:16]
    except Exception:
        return u"?"


# GUARDA: declarado sem valor de proposito -- o nome existe para quem le o
# modulo, e o valor sai de `__getattr__` na primeira leitura.
VERSAO_DA_RECEITA_POS: str


def __getattr__(nome):
    # GUARDA: a receita le e analisa a fonte de nove modulos; so na primeira
    # leitura, e nao em todo `import engine`.
    if nome == "VERSAO_DA_RECEITA_POS":
        v = receita_do_pos()
        globals()["VERSAO_DA_RECEITA_POS"] = v
        return v
    raise AttributeError("module %r has no attribute %r" % (__name__, nome))
