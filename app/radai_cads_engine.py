# -*- coding: utf-8 -*-
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

import numpy as np

TAREFA = "556"
PASTA_PESO = "Dataset556_GC256"
TREINADOR = "nnUNetTrainerNoMirroring__nnUNetResEncUNetLPlans__3d_fullres"


def pasta_do_peso(base=None):
    if base is None:
        try:
            import radai_models
            base = str(radai_models.pasta_do_modelo("cads_open"))
        except Exception:
            return ""
    p = os.path.join(base, PASTA_PESO, TREINADOR)
    return p if os.path.isdir(p) else ""


def disponivel(base=None):
    p = pasta_do_peso(base)
    if not p:
        return False, "os pesos do CADS não estão nesta estação"
    ck = os.path.join(p, "fold_all", "checkpoint_final.pth")
    if not os.path.isfile(ck):
        return False, "a pasta do CADS existe mas falta o checkpoint"
    try:
        import nnunetv2
    except Exception as e:
        return False, "nnU-Net não importa neste Python (%s)" % type(e).__name__
    return True, ""


def rotulos(base=None):
    import radai_cads
    p = pasta_do_peso(base)
    if not p:
        return {}
    try:
        with open(os.path.join(p, "dataset.json"), encoding="utf-8") as f:
            d = json.load(f)
    except Exception:
        return {}
    fora = {}
    for nome, idx in (d.get("labels") or {}).items():
        try:
            i = int(idx)
        except Exception:
            continue
        if i <= 0:
            continue
        fora[i] = radai_cads.normalizar(nome)
    return fora


def _torch_device(d):
    d = str(d or "").strip().lower()
    if d in ("gpu", "cuda"):
        return "cuda"
    if d.startswith("cuda:"):
        return d
    return "cpu"


_SCRIPT = r'''
import os, sys, multiprocessing
# GUARDA: no Windows o filho do predict_from_files re-importa este script (spawn); sem o guarda __main__ com freeze_support() ele re-executa tudo e fica parado, sem sair.
def _principal():
    # GUARDA: as variaveis do nnU-Net se definem aqui, no filho; definidas na maquina, mudariam o TotalSegmentator.
    for k in ("nnUNet_raw", "nnUNet_preprocessed", "nnUNet_results"):
        os.environ.setdefault(k, sys.argv[4])
    from nnunetv2.inference.predict_from_raw_data import nnUNetPredictor
    import torch
    pasta_peso, entrada, saida, _tmp, dispositivo = sys.argv[1:6]
    # GUARDA: espelhar na inferencia troca esquerda por direita sem erro no log; o padrao do nnUNetPredictor e use_mirroring=True, entao o False e literal.
    p = nnUNetPredictor(
        tile_step_size=0.5, use_gaussian=True, use_mirroring=False,
        device=torch.device(dispositivo), verbose=False,
        verbose_preprocessing=False, allow_tqdm=False)
    p.initialize_from_trained_model_folder(pasta_peso, use_folds=("all",),
                                           checkpoint_name="checkpoint_final.pth")
    # GUARDA: a pasta de saida vai como string; dentro de lista o nnU-Net a le como nome de arquivo truncado e grava ao lado da pasta.
    p.predict_from_files([[entrada]], saida, save_probabilities=False,
                         overwrite=True, num_processes_preprocessing=1,
                         num_processes_segmentation_export=1)
    print("CADS_OK")


if __name__ == "__main__":
    multiprocessing.freeze_support()
    _principal()
'''


TETO_S = 3600

BATIDA_S = 10

SILENCIO_S = 120


def _tamanho(caminho):
    try:
        return os.path.getsize(caminho)
    except Exception:
        return -1


def rodar(nifti_entrada, destino_nii, python_exe=None, dispositivo="cpu",
          timeout_s=None, log=None, base=None, cancelado=None):
    ok, motivo = disponivel(base)
    if not ok:
        return False, motivo
    peso = pasta_do_peso(base)
    trab = tempfile.mkdtemp(prefix="radai_cads_")
    script = os.path.join(trab, "roda.py")
    with open(script, "w", encoding="utf-8") as f:
        f.write(_SCRIPT)
    saida_dir = os.path.join(trab, "out")
    os.makedirs(saida_dir, exist_ok=True)
    log_path = os.path.join(trab, "cads.log")
    cmd = [python_exe or sys.executable, script, peso, nifti_entrada,
           saida_dir, trab, _torch_device(dispositivo)]
    teto = int(timeout_s or TETO_S)
    try:
        with open(log_path, "wb") as saida:
            proc = subprocess.Popen(cmd, stdout=saida, stderr=subprocess.STDOUT)
            t0 = time.time()
            ultimo = 0
            visto, mudou_em = -1, 0.0
            while proc.poll() is None:
                secs = int(time.time() - t0)
                agora = _tamanho(log_path)
                if agora != visto:
                    visto, mudou_em = agora, time.time()
                if secs - ultimo >= BATIDA_S:
                    ultimo = secs
                    parado = int(time.time() - mudou_em)
                    extra = ""
                    if parado >= SILENCIO_S:
                        extra = " · sem saida nova ha %ds" % parado
                    if log:
                        log("   CADS rodando... %ds (still working, please wait)"
                            " · log %.1f KB%s"
                            % (secs, max(agora, 0) / 1024.0, extra))
                if cancelado is not None and cancelado():
                    try:
                        proc.kill(); proc.wait(timeout=30)
                    except Exception:
                        pass
                    return False, "o CADS foi interrompido a pedido, aos %ds" % secs
                if secs > teto:
                    try:
                        proc.kill(); proc.wait(timeout=30)
                    except Exception:
                        pass
                    return False, ("o CADS passou do teto de %d s e foi "
                                   "encerrado (aos %ds)" % (teto, secs))
                time.sleep(2)
        if proc.returncode != 0:
            cauda = ""
            try:
                with open(log_path, encoding="utf-8", errors="replace") as f:
                    cauda = f.read()[-400:]
            except Exception:
                pass
            return False, "o CADS terminou com codigo %s: %s" % (proc.returncode, cauda)
        gerados = [x for x in os.listdir(saida_dir) if x.endswith(".nii.gz")]
        if not gerados:
            return False, "o CADS rodou mas nao gravou saida"
        shutil.copy2(os.path.join(saida_dir, gerados[0]), destino_nii)
        return True, ""
    except Exception as e:
        return False, "%s: %s" % (type(e).__name__, str(e)[:200])
    finally:
        if log:
            try:
                with open(log_path, encoding="utf-8", errors="replace") as f:
                    for linha in f.read().splitlines()[-6:]:
                        log("   cads: " + linha[:160])
            except Exception:
                pass
        shutil.rmtree(trab, ignore_errors=True)


def contornar(stage, python_exe=None, dispositivo="cpu", timeout_s=None,
              log=None, base=None, cancelado=None):
    import os as _os, time as _t, tempfile as _tmp, shutil as _sh
    ok, motivo = disponivel(base)
    if not ok:
        if log:
            log(u"CADS: %s — o conjunto dele nao sai nesta serie" % motivo)
        return {}
    import SimpleITK as sitk
    import engine as _m
    ref = _m.load_sitk(str(stage))
    forma = tuple(int(v) for v in reversed(ref.GetSize()))
    trab = _tmp.mkdtemp(prefix="radai_cads_in_")
    try:
        entrada = _os.path.join(trab, "serie_0000.nii.gz")
        saida = _os.path.join(trab, "saida.nii.gz")
        sitk.WriteImage(ref, entrada)
        t0 = _t.time()
        ok, motivo = rodar(entrada, saida, python_exe=python_exe,
                           dispositivo=dispositivo, timeout_s=timeout_s,
                           log=log, base=base, cancelado=cancelado)
        if not ok:
            raise RuntimeError(motivo)
        masks = masks_da_saida(saida, forma, base=base)
        if log:
            log("CADS: %d estrutura(s) em %ds" % (len(masks), int(_t.time() - t0)))
        return masks
    finally:
        _sh.rmtree(trab, ignore_errors=True)


def conferir_rotulos(nomes, base=None):
    import radai_cads

    permitidos = set(radai_cads.estruturas())
    fora = sorted(set(n for n in (nomes or ()) if n not in permitidos))
    if fora:
        raise ValueError(
            u"o CADS devolveu %d rotulo(s) que nao estao na lista conferida "
            u"deste motor: %s. A lista e de PERMITIDOS -- rotulo novo cai fora "
            u"por omissao, ate alguem olhar o que ele desenha e acrescenta-lo "
            u"a `radai_cads.DE_PARA`. Isto importa mais aqui que nos outros "
            u"motores: o CADS ALIMENTA o RTSTRUCT entregue, por "
            u"`engine.MELHOR_FONTE`." % (len(fora), u", ".join(fora[:8])))


def masks_da_saida(caminho_nii, forma, base=None):
    import SimpleITK as sitk
    img = sitk.ReadImage(str(caminho_nii))
    arr = sitk.GetArrayFromImage(img)
    if tuple(int(v) for v in arr.shape) != tuple(int(v) for v in forma):
        raise ValueError("o CADS devolveu forma %s e a serie e %s"
                         % (arr.shape, tuple(forma)))
    tabela = rotulos(base)
    conferir_rotulos(tabela.values(), base=base)
    fora = {}
    for idx, nome in tabela.items():
        m = (arr == idx)
        if m.any():
            fora[nome] = m
    return fora
