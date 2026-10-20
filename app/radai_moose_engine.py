# -*- coding: utf-8 -*-
import json
import os
import subprocess
import sys
import tempfile

import numpy as np

import radai_moose


def _descritor(modelo):
    d = radai_moose.MODELOS.get(modelo)
    if d is None:
        raise ValueError("modelo do MOOSE desconhecido: %r (ha %s)"
                         % (modelo, ", ".join(sorted(radai_moose.MODELOS))))
    return d


def pasta_do_peso(modelo, base=None):
    d = _descritor(modelo)
    if base is None:
        try:
            import radai_models
            base = str(radai_models.pasta_do_modelo("moose"))
        except Exception:
            return ""
    p = os.path.join(base, d["pasta"], d["treinador"])
    return p if os.path.isdir(p) else ""


def disponivel(modelo, base=None):
    try:
        d = _descritor(modelo)
    except ValueError as e:
        return False, str(e)
    p = pasta_do_peso(modelo, base)
    if not p:
        return False, (u"o peso `%s` do MOOSE não está nesta estação" % d["pasta"])
    ck = os.path.join(p, "fold_all", "checkpoint_final.pth")
    if not os.path.isfile(ck):
        return False, (u"a pasta `%s` existe mas falta o checkpoint" % d["pasta"])
    try:
        import nnunetv2
    except Exception as e:
        return False, "nnU-Net nao importa neste Python (%s)" % type(e).__name__
    return True, ""


def modelos_disponiveis(base=None):
    fora = {}
    for k in sorted(radai_moose.MODELOS):
        ok, motivo = disponivel(k, base)
        fora[k] = (ok, motivo)
    return fora


def rotulos(modelo, base=None):
    p = pasta_do_peso(modelo, base)
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
        fora[i] = radai_moose.normalizar(nome)
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
    print("MOOSE_OK")


if __name__ == "__main__":
    multiprocessing.freeze_support()
    _principal()
'''


def rodar(modelo, nifti_entrada, destino_nii, python_exe=None, dispositivo="cpu",
          timeout_s=7200, log=None, base=None):
    ok, motivo = disponivel(modelo, base)
    if not ok:
        return False, motivo
    peso = pasta_do_peso(modelo, base)
    trab = tempfile.mkdtemp(prefix="radai_moose_")
    script = os.path.join(trab, "roda.py")
    with open(script, "w", encoding="utf-8") as f:
        f.write(_SCRIPT)
    saida_dir = os.path.join(trab, "out")
    os.makedirs(saida_dir, exist_ok=True)
    log_path = os.path.join(trab, "moose.log")
    cmd = [python_exe or sys.executable, script, peso, nifti_entrada,
           saida_dir, trab, _torch_device(dispositivo)]
    proc = None
    try:
        with open(log_path, "wb") as saida:
            proc = subprocess.Popen(cmd, stdout=saida, stderr=subprocess.STDOUT)
            try:
                proc.wait(timeout=timeout_s)
            except subprocess.TimeoutExpired:
                proc.kill()
                return False, ("o MOOSE/%s passou de %d s e foi interrompido"
                               % (modelo, timeout_s))
        if proc.returncode != 0:
            cauda = ""
            try:
                with open(log_path, encoding="utf-8", errors="replace") as f:
                    cauda = f.read()[-400:]
            except Exception:
                pass
            return False, ("o MOOSE/%s terminou com codigo %s: %s"
                           % (modelo, proc.returncode, cauda))
        gerados = [x for x in os.listdir(saida_dir) if x.endswith(".nii.gz")]
        if not gerados:
            return False, "o MOOSE/%s rodou mas nao gravou saida" % modelo
        import shutil
        shutil.copy2(os.path.join(saida_dir, gerados[0]), destino_nii)
        return True, ""
    except Exception as e:
        return False, "%s: %s" % (type(e).__name__, str(e)[:200])
    finally:
        if log:
            try:
                with open(log_path, encoding="utf-8", errors="replace") as f:
                    for linha in f.read().splitlines()[-6:]:
                        log("   moose/%s: %s" % (modelo, linha[:150]))
            except Exception:
                pass


def conferir_rotulos(nomes, base=None):
    permitidos = set(radai_moose.estruturas())
    fora = sorted(set(n for n in (nomes or ()) if n not in permitidos))
    if fora:
        raise ValueError(
            u"o MOOSE devolveu %d rotulo(s) que nao estao na lista conferida "
            u"deste motor: %s. A lista e de PERMITIDOS -- rotulo novo cai fora "
            u"por omissao, ate alguem olhar o que ele desenha e acrescenta-lo "
            u"a `radai_moose.DE_PARA`." % (len(fora), u", ".join(fora[:8])))


def masks_da_saida(modelo, caminho_nii, forma, base=None):
    import SimpleITK as sitk
    img = sitk.ReadImage(str(caminho_nii))
    arr = sitk.GetArrayFromImage(img)
    if tuple(int(v) for v in arr.shape) != tuple(int(v) for v in forma):
        raise ValueError("o MOOSE/%s devolveu forma %s e a serie e %s"
                         % (modelo, arr.shape, tuple(forma)))
    tabela = rotulos(modelo, base)
    conferir_rotulos(tabela.values(), base=base)
    fora = {}
    for idx, nome in tabela.items():
        m = (arr == idx)
        if m.any():
            fora[nome] = m
    return fora


def contornar(stage, python_exe=None, dispositivo="cpu", timeout_s=7200,
              log=None, base=None):
    import os as _os, time as _t, tempfile as _tmp, shutil as _sh
    estado = modelos_disponiveis(base)
    prontos = [k for k, (ok, _m) in estado.items() if ok]
    if not prontos:
        if log:
            for k, (_ok, motivo) in sorted(estado.items()):
                log(u"MOOSE/%s: %s" % (k, motivo))
            log(u"MOOSE: nenhum peso nesta estacao — o conjunto dele nao sai")
        return {}
    if log:
        for k, (ok, motivo) in sorted(estado.items()):
            if not ok:
                log(u"MOOSE/%s: %s — as estruturas dele faltam neste conjunto"
                    % (k, motivo))

    import SimpleITK as sitk
    import engine as _m
    ref = _m.load_sitk(str(stage))
    forma = tuple(int(v) for v in reversed(ref.GetSize()))
    trab = _tmp.mkdtemp(prefix="radai_moose_in_")
    fora = {}
    try:
        entrada = _os.path.join(trab, "serie_0000.nii.gz")
        sitk.WriteImage(ref, entrada)
        for k in sorted(prontos):
            saida = _os.path.join(trab, "saida_%s.nii.gz" % k)
            t0 = _t.time()
            try:
                ok, motivo = rodar(k, entrada, saida, python_exe=python_exe,
                                   dispositivo=dispositivo, timeout_s=timeout_s,
                                   log=log, base=base)
                if not ok:
                    raise RuntimeError(motivo)
                m = masks_da_saida(k, saida, forma, base=base)
            except Exception as e:
                if log:
                    log(u"MOOSE/%s FALHOU: %s: %s — o resto do conjunto sai "
                        u"assim mesmo" % (k, type(e).__name__, str(e)[:200]))
                continue
            fora.update(m)
            if log:
                log("MOOSE/%s: %d estrutura(s) em %ds"
                    % (k, len(m), int(_t.time() - t0)))
        if log:
            log("MOOSE: %d estrutura(s) no total" % len(fora))
        return fora
    finally:
        _sh.rmtree(trab, ignore_errors=True)
