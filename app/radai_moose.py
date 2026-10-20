# -*- coding: utf-8 -*-

MODELOS = {
    "cardiac": {
        "id_moose": "clin_ct_cardiac",
        "pasta": "Dataset888_Cardiac",
        "treinador": "nnUNetTrainer_2000epochs_NoMirroring__nnUNetPlans__3d_fullres",
        "zip": "clin_ct_cardiac_ras_21052025.zip",
        "bytes": 459_078_903,
        "sha256": "be368e2086a24aada06da2aa870326bcab4f879f0acad105ab00bf4bf71a0704",
        "url": ("https://github.com/ENHANCE-PET/MOOSE/releases/download/"
                "moosez-v.3.1.3/clin_ct_cardiac_ras_21052025.zip"),
        "rotulo": u"Câmaras cardíacas e grandes vasos",
    },
    "body_composition": {
        "id_moose": "clin_ct_body_composition",
        "pasta": "Dataset778_Body_composition",
        "treinador": "nnUNetTrainer_2000epochs__nnUNetPlans__3d_fullres",
        "zip": "clin_ct_body_composition_05092024.zip",
        "bytes": 672_487_698,
        "sha256": "a671fdf840ba986bd23a4a1a4caf67a3cf1b2641a8b79327f29fae66a22adcc4",
        "url": ("https://github.com/ENHANCE-PET/MOOSE/releases/download/"
                "moosez-v.3.1.3/clin_ct_body_composition_05092024.zip"),
        "rotulo": u"Composição corporal (músculo e os dois compartimentos de gordura)",
    },
}

DE_PARA = {
    "heart_myocardium": "heart_myocardium",
    "heart_atrium_left": "heart_atrium_left",
    "heart_atrium_right": "heart_atrium_right",
    "heart_ventricle_left": "heart_ventricle_left",
    "heart_ventricle_right": "heart_ventricle_right",
    "aorta": "aorta",
    "iliac_artery_left": "iliac_artery_left",
    "iliac_artery_right": "iliac_artery_right",
    "iliac_vena_left": "iliac_vena_left",
    "iliac_vena_right": "iliac_vena_right",
    "inferior_vena_cava": "inferior_vena_cava",
    "portal_splenic_vein": "portal_vein_and_splenic_vein",
    "pulmonary_artery": "pulmonary_artery",

    "skeletal_muscle": "skeletal_muscle",
    "subcutaneous_fat": "subcutaneous_fat",
    "visceral_fat": "visceral_fat",
}

POR_MODELO = {
    "cardiac": ("heart_myocardium", "heart_atrium_left", "heart_atrium_right",
                "heart_ventricle_left", "heart_ventricle_right", "aorta",
                "iliac_artery_left", "iliac_artery_right", "iliac_vena_left",
                "iliac_vena_right", "inferior_vena_cava",
                "portal_vein_and_splenic_vein", "pulmonary_artery"),
    "body_composition": ("skeletal_muscle", "subcutaneous_fat", "visceral_fat"),
}

TG263_MOOSE = {
    "heart_myocardium": "Myocardium",
    "heart_atrium_left": "Atrium_L",
    "heart_atrium_right": "Atrium_R",
    "heart_ventricle_left": "Ventricle_L",
    "heart_ventricle_right": "Ventricle_R",
    "pulmonary_artery": "A_Pulmonary",
    "inferior_vena_cava": "V_Venacava_I",
    "portal_vein_and_splenic_vein": "V_Portal",

    "skeletal_muscle": "Musc_Skel",
    "subcutaneous_fat": "Fat_Subcut",
    "visceral_fat": "Fat_Visceral",
}

NOME_NOSSO_NAO_E_TG263 = ("skeletal_muscle", "subcutaneous_fat", "visceral_fat")


def normalizar(rotulo):
    r = str(rotulo or "").strip()
    if r in DE_PARA:
        return DE_PARA[r]
    return r.replace(" ", "_").lower()


def estruturas():
    return sorted(set(DE_PARA.values()))


def estruturas_de(modelo):
    return sorted(POR_MODELO.get(modelo, ()))


def so_do_moose():
    return ("heart_myocardium", "heart_atrium_left", "heart_atrium_right",
            "heart_ventricle_left", "heart_ventricle_right", "pulmonary_artery",
            "skeletal_muscle", "subcutaneous_fat", "visceral_fat")
