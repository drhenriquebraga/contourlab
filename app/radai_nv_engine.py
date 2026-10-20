# -*- coding: utf-8 -*-
import json
import os
import subprocess
import sys
import tempfile

import numpy as np

import radai_models

VERSAO_NV_MOTOR = "1.0"

NAO_AVALIADO = 255
ESTRUTURA = 1


def classes(ident="nv_segment_ct"):
    p = radai_models.pasta_do_modelo(ident) / "docs" / "labels.json"
    if not p.exists():
        raise ValueError("labels.json ausente em %s — o modelo nao esta baixado" % p)
    return dict((str(k), int(v)) for k, v in
                json.loads(p.read_text(encoding="utf-8")).items())


CLASSES_DE_ACHADO = {
    u"bone lesion": u"lesao ossea",
    u"colon cancer primaries": u"tumor primario de colon",
    u"hepatic tumor": u"tumor de figado",
    u"kidney mass": u"massa renal",
    u"left kidney cyst": u"cisto renal esquerdo",
    u"liver tumor": u"tumor de figado (rotulo proprio do mapa de 132)",
    u"lung tumor": u"tumor de pulmao",
    u"pancreatic tumor": u"tumor de pancreas",
    u"right kidney cyst": u"cisto renal direito",
}

CLASSES_RECUSADAS = {}


CLASSES_DE_ENTREGA = frozenset([
    u"aorta", u"bladder", u"brachiocephalic trunk", u"brain", u"colon",
    u"costal cartilages", u"duodenum", u"esophagus", u"gallbladder",
    u"heart", u"inferior vena cava", u"left adrenal gland",
    u"left atrial appendage", u"left autochthon",
    u"left brachiocephalic vein", u"left clavicula",
    u"left common carotid artery", u"left femur", u"left gluteus maximus",
    u"left gluteus medius", u"left gluteus minimus", u"left hip",
    u"left humerus", u"left iliac artery", u"left iliac vena",
    u"left iliopsoas", u"left kidney", u"left lung lower lobe",
    u"left lung upper lobe", u"left rib 1", u"left rib 10", u"left rib 11",
    u"left rib 12", u"left rib 2", u"left rib 3", u"left rib 4",
    u"left rib 5", u"left rib 6", u"left rib 7", u"left rib 8",
    u"left rib 9", u"left scapula", u"left subclavian artery", u"liver",
    u"pancreas", u"portal vein and splenic vein", u"prostate",
    u"pulmonary vein", u"right adrenal gland", u"right autochthon",
    u"right brachiocephalic vein", u"right clavicula",
    u"right common carotid artery", u"right femur",
    u"right gluteus maximus", u"right gluteus medius",
    u"right gluteus minimus", u"right hip", u"right humerus",
    u"right iliac artery", u"right iliac vena", u"right iliopsoas",
    u"right kidney", u"right lung lower lobe", u"right lung middle lobe",
    u"right lung upper lobe", u"right rib 1", u"right rib 10",
    u"right rib 11", u"right rib 12", u"right rib 2", u"right rib 3",
    u"right rib 4", u"right rib 5", u"right rib 6", u"right rib 7",
    u"right rib 8", u"right rib 9", u"right scapula",
    u"right subclavian artery", u"sacrum", u"skull", u"small bowel",
    u"spinal cord", u"spleen", u"sternum", u"stomach",
    u"superior vena cava", u"thyroid gland", u"trachea", u"vertebrae C1",
    u"vertebrae C2", u"vertebrae C3", u"vertebrae C4", u"vertebrae C5",
    u"vertebrae C6", u"vertebrae C7", u"vertebrae L1", u"vertebrae L2",
    u"vertebrae L3", u"vertebrae L4", u"vertebrae L5", u"vertebrae S1",
    u"vertebrae T1", u"vertebrae T10", u"vertebrae T11", u"vertebrae T12",
    u"vertebrae T2", u"vertebrae T3", u"vertebrae T4", u"vertebrae T5",
    u"vertebrae T6", u"vertebrae T7", u"vertebrae T8", u"vertebrae T9",
])


CLASSES_FORA_DA_ENTREGA = {
    u"kidney": u"agregado: `left kidney` e `right kidney` ja saem separados",
    u"lung": u"agregado: os cinco lobos ja saem separados",
    u"bone": u"agregado: costelas, vertebras e ossos longos ja saem separados",
    u"prostate or uterus": u"nome ambiguo -- nao diz QUAL dos dois",
    u"rectum": u"vale medir: hoje o reto sai por derivacao geometrica do colon",
    u"vertebrae L6": u"vale medir: variante que o mapa de 124 nem nomeava",
    u"hepatic vessel": u"fora do `everything_labels`; era entregue pelo mapa de 124",
    u"airway": u"fora do `everything_labels`; era entregue pelo mapa de 124",
}


CLASSES_PERMITIDAS = frozenset(
    set(CLASSES_DE_ENTREGA) | set(CLASSES_DE_ACHADO)
    | set(CLASSES_FORA_DA_ENTREGA))

POR_MODELO = {
    "nv_segment_ct": {"entrega": CLASSES_DE_ENTREGA,
                      "achado": CLASSES_DE_ACHADO,
                      "permitidas": CLASSES_PERMITIDAS},
}


def listas(ident="nv_segment_ct"):
    try:
        return POR_MODELO[str(ident)]
    except KeyError:
        raise ValueError(
            u"o modelo %r nao tem listas de classes declaradas. Todo motor "
            u"precisa das DUAS (entrega e achado) antes de rodar: a lista e "
            u"de PERMITIDOS, e mapa sem registro cai fora por omissao."
            % ident)


def conferir_classes(ids, ident="nv_segment_ct", por_nome=None):
    mapa = por_nome if por_nome is not None else classes(ident)
    permitidas = listas(ident)["permitidas"]
    de_id = dict((int(i), n) for n, i in mapa.items())
    fora = []
    for i in sorted(set(int(v) for v in (ids or []))):
        nome = de_id.get(i)
        if nome is None:
            fora.append(u"id %d: nao existe no labels.json de %s" % (i, ident))
        elif nome not in permitidas:
            fora.append(
                u"id %d `%s`: existe no labels.json e NAO esta na lista de "
                u"classes conferidas deste modelo. A lista e de PERMITIDOS: "
                u"classe nova cai fora por omissao, ate alguem olhar o que "
                u"ela devolve e decidir." % (i, nome))
    if fora:
        raise ValueError(
            u"classe nao permitida no label_prompt: " + u" | ".join(fora)
            + u" — a lista deste motor e de PERMITIDOS, e classe que nao "
              u"esteja nela cai fora por omissao. Anatomia entra em "
              u"`CLASSES_DE_ENTREGA`; achado, em `CLASSES_DE_ACHADO` — e "
              u"achado so roda por ato declarado de quem opera (regra 6, "
              u"regras A e B)")


def ids_permitidos(ident="nv_segment_ct", por_nome=None):
    mapa = por_nome if por_nome is not None else classes(ident)
    entrega = listas(ident)["entrega"]
    return sorted(int(i) for n, i in mapa.items() if n in entrega)


def para_nifti(pasta_dicom, destino):
    import SimpleITK as sitk
    leitor = sitk.ImageSeriesReader()
    nomes = leitor.GetGDCMSeriesFileNames(str(pasta_dicom))
    if not nomes:
        raise ValueError("sem DICOM em %s" % pasta_dicom)
    leitor.SetFileNames(nomes)
    sitk.WriteImage(leitor.Execute(), str(destino))
    return str(destino)


def _runner(bundle, config, saida, entrada, trabalho=None):
    ida = (u"import os\nos.chdir(%r)\n" % trabalho) if trabalho else u""
    return (
        "import sys, json\n"
        + ida +
        "sys.path.insert(0, %r)\n"
        "from monai.bundle import run\n"
        "run(config_file=%r, bundle_root=%r, output_dir=%r,\n"
        "    input_dict=json.loads(%r))\n"
        % (bundle, config, bundle, saida, json.dumps(entrada)))


def rodar(nifti, ident="nv_segment_ct", label_prompt=None, points=None,
          point_labels=None, timeout_s=3600, python_exe=None, log=None):
    if not label_prompt and not points:
        raise ValueError("informe label_prompt (classe) ou points (clique)")
    if label_prompt:
        conferir_classes(label_prompt, ident=ident)
        try:
            mapa = classes(ident)
            de_id = dict((int(i), n) for n, i in mapa.items())
            achou = sorted(set(
                de_id.get(int(v)) for v in label_prompt)
                & set(listas(ident)["achado"]))
            if achou and log:
                log(u"ACHADO: o prompt pede %d classe(s) de achado (%s). Elas "
                    u"nao entram no prompt da ENTREGA -- estao aqui porque "
                    u"foram PEDIDAS. O que sair vai como sugestao nao-aprovada."
                    % (len(achou), u", ".join(achou)))
        except Exception:
            pass
    modelo = radai_models.pasta_do_modelo(ident)
    config = modelo / "configs" / "inference.json"
    if not config.exists():
        raise ValueError("o modelo %s nao esta instalado (falta %s)" % (ident, config))

    trabalho = tempfile.mkdtemp(prefix="radai_nv_")
    saida = os.path.join(trabalho, "saida")
    entrada = {"image": str(nifti).replace("\\", "/")}
    if label_prompt:
        entrada["label_prompt"] = [int(v) for v in label_prompt]
    if points:
        entrada["points"] = [[int(c) for c in p] for p in points]
        entrada["point_labels"] = [int(v) for v in
                                   (point_labels or [1] * len(points))]

    runner = os.path.join(trabalho, "runner.py")
    with open(runner, "w", encoding="utf-8") as f:
        f.write(_runner(str(modelo), str(config), saida, entrada,
                        trabalho=trabalho))

    exe = python_exe or sys.executable
    if log:
        log("VISTA-3D: %s" % ("classe %s" % entrada.get("label_prompt")
                              if label_prompt else "%d ponto(s)" % len(points)))
    r = subprocess.run([exe, runner], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       timeout=timeout_s,
                       env=dict(os.environ, PYTHONIOENCODING="utf-8:replace"))
    if r.returncode != 0:
        fim = (r.stderr or b"").decode("utf-8", "replace").strip().splitlines()
        raise RuntimeError("VISTA-3D saiu com codigo %d. %s"
                           % (r.returncode, " | ".join(fim[-3:])))
    for raiz, _, arquivos in os.walk(saida):
        for a in arquivos:
            if a.endswith((".nii", ".nii.gz")):
                return os.path.join(raiz, a)
    raise RuntimeError("VISTA-3D terminou sem gravar NIfTI em %s" % saida)


def ler_saida(caminho, forma_zyx=None, rotulo=None):
    import nibabel as nib
    v = np.asanyarray(nib.load(str(caminho)).dataobj)
    if rotulo is None:
        bruto = (v != 0) & (v != NAO_AVALIADO)
    else:
        bruto = v == float(rotulo)
    m = np.ascontiguousarray(np.transpose(bruto, (2, 1, 0)))
    if forma_zyx is not None and tuple(m.shape) != tuple(forma_zyx):
        raise ValueError("saida do VISTA-3D com forma %r; o CT e %r"
                         % (tuple(m.shape), tuple(forma_zyx)))
    return m


def rotulos_da_saida(caminho):
    import nibabel as nib
    v = np.asanyarray(nib.load(str(caminho)).dataobj)
    vals, cont = np.unique(v, return_counts=True)
    return dict((int(a), int(b)) for a, b in zip(vals.tolist(), cont.tolist()))


def diagnostico_da_saida(caminho):
    import nibabel as nib
    v = np.asanyarray(nib.load(str(caminho)).dataobj)
    total = int(v.size)
    return {"voxels_estrutura": int((v == ESTRUTURA).sum()),
            "voxels_nao_avaliados": int((v == NAO_AVALIADO).sum()),
            "voxels_fundo": int(((v != ESTRUTURA) & (v != NAO_AVALIADO)).sum()),
            "total": total}


def segmentar_varias(nifti, ids, forma_zyx, ident="nv_segment_ct",
                     timeout_s=7200, python_exe=None, log=None):
    ids = [int(v) for v in (ids or [])]
    if not ids:
        return {}, {}
    if log:
        log("VISTA-3D: %d classes numa chamada" % len(ids))
    caminho = rodar(nifti, ident=ident, label_prompt=ids, timeout_s=timeout_s,
                    python_exe=python_exe, log=log)
    presentes = rotulos_da_saida(caminho)
    fora = {}
    for i in ids:
        if presentes.get(i, 0) > 0:
            fora[i] = ler_saida(caminho, forma_zyx, rotulo=i)
    return fora, presentes


def segmentar(pasta_dicom, forma_zyx, ident="nv_segment_ct", label_prompt=None,
              points=None, point_labels=None, timeout_s=3600, python_exe=None,
              log=None, nifti=None):
    trabalho = None
    try:
        if nifti is None:
            trabalho = tempfile.mkdtemp(prefix="radai_ct_")
            nifti = para_nifti(pasta_dicom, os.path.join(trabalho, "ct.nii.gz"))
        caminho = rodar(nifti, ident=ident, label_prompt=label_prompt, points=points,
                        point_labels=point_labels, timeout_s=timeout_s,
                        python_exe=python_exe, log=log)
        return ler_saida(caminho, forma_zyx), diagnostico_da_saida(caminho)
    finally:
        if trabalho:
            import shutil
            shutil.rmtree(trabalho, ignore_errors=True)
