# -*- coding: utf-8 -*-

DE_PARA = {
    "spinal_canal": "spinal_canal",
    "larynx": "larynx",
    "heart": "heart",
    "bowel_bag": "bowel_bag",
    "sigmoid": "colon_sigmoid",
    "rectum": "rectum",
    "prostate": "prostate",
    "seminal_vesicle": "seminal_vesicles",
    "left_mammary_gland": "breast_left",
    "right_mammary_gland": "breast_right",
    "sternum": "sternum",
    "left psoas major": "iliopsoas_left",
    "right psoas major": "iliopsoas_right",
    "left rectus abdominis": "rectus_abdominis_left",
    "right rectus abdominis": "rectus_abdominis_right",
}


TAREFA = "556"
PASTA_PESO = "Dataset556_GC256"


def normalizar(rotulo):
    r = str(rotulo or "").strip()
    if r in DE_PARA:
        return DE_PARA[r]
    return r.replace(" ", "_").lower()


def estruturas():
    return sorted(set(DE_PARA.values()))
