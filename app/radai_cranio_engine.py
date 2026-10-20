# -*- coding: utf-8 -*-
import json
import os
import subprocess
import sys
import tempfile
import time

IDENT = "cranio_buti"
TREINADOR = "nnUNetTrainer__nnUNetPlans__3d_fullres"

# GUARDA: indice -> nome exatamente como o dataset.json do peso conferido diz
ROTULOS_CONFERIDOS = {
    1: "Brain", 2: "Brainstem", 3: "Cerebellum", 4: "Chiasm",
    5: "OpticNerve_L", 6: "OpticNerve_R", 7: "Ventricles_connected",
    8: "Midline",
}

PARA_O_FULL = {
    "Brainstem": "brain_brainstem",
    "Chiasm": "optic_chiasm",
    "Cerebellum": "cerebellum",
    "Ventricles_connected": "brain_ventricles",
    "Midline": "brain_midline",
}
NO_OAR = frozenset(["brain_brainstem", "optic_chiasm"])
DESCARTADOS = {
    "Brain": u"o encefalo do pacote e o do TotalSegmentator",
    "OpticNerve_L": u"os nervos opticos do pacote sao os do TotalSegmentator",
    "OpticNerve_R": u"os nervos opticos do pacote sao os do TotalSegmentator",
}

_NOMES_PT = {
    "brain_brainstem": u"Tronco encefalico", "optic_chiasm": u"Quiasma optico",
    "cerebellum": u"Cerebelo", "brain_ventricles": u"Ventriculos",
    "brain_midline": u"Linha media",
}
_DICE_DO_ARTIGO = {"brain_brainstem": u"0,93", "optic_chiasm": u"0,64"}


def descricao(chave):
    nome = _NOMES_PT.get(chave, chave)
    t = u"%s do modelo de Buti et al. 2025 (TC)." % nome
    if chave in _DICE_DO_ARTIGO:
        t += (u" Dice %s no teste do artigo." % _DICE_DO_ARTIGO[chave])
    if chave == "optic_chiasm":
        t += u" Estrutura pequena: confira inteira antes de usar."
    if chave not in NO_OAR:
        t += u" So no FULL."
    return t


VOLUME_MINIMO_DE_ENCEFALO_CM3 = 100.0
MARGEM_MM = 15.0
TETO_S = 2 * 3600


def conferir_rotulos(tabela):
    t = dict((int(k), str(v)) for k, v in (tabela or {}).items())
    if t != ROTULOS_CONFERIDOS:
        diferentes = sorted(set(t.items()) ^ set(ROTULOS_CONFERIDOS.items()))
        raise ValueError(
            u"o modelo do cranio devolveu um mapa de rotulos diferente do "
            u"conferido (%s). A lista e de PERMITIDOS: rotulo novo ou trocado "
            u"cai fora ate alguem olhar o que ele desenha." %
            u", ".join(u"%s=%s" % x for x in diferentes[:8]))
    return True


def pasta_do_peso(base=None):
    if base is None:
        try:
            import radai_models
            base = str(radai_models.pasta_do_modelo(IDENT))
        except Exception:
            return ""
    base = str(base or "")
    if not os.path.isdir(base):
        return ""
    for d, subs, arqs in os.walk(base):
        if (TREINADOR in os.path.basename(d) or "plans.json" in arqs) \
                and "dataset.json" in arqs and "plans.json" in arqs \
                and os.path.isfile(os.path.join(d, "fold_all",
                                                "checkpoint_final.pth")):
            return d
    return ""


def rotulos(base=None):
    p = pasta_do_peso(base)
    if not p:
        return {}
    with open(os.path.join(p, "dataset.json"), encoding="utf-8") as f:
        d = json.load(f)
    return dict((int(i), str(n)) for n, i in (d.get("labels") or {}).items()
                if int(i) > 0)


class PesoAusente(RuntimeError):
    pass


def disponivel(base=None):
    p = pasta_do_peso(base)
    if not p:
        return False, (u"os pesos do modelo do cranio nao estao nesta "
                       u"instalacao (pasta `modelos\\%s`)" % IDENT)
    try:
        import nnunetv2
    except Exception as e:
        return False, u"nnU-Net nao importa neste Python (%s)" % type(e).__name__
    return True, p


def encefalo_no_campo(cruas_base, grade):
    try:
        import numpy as np
        import radai_geom
        if cruas_base is None or "brain" not in cruas_base:
            return False, u"sem encefalo no campo", 0.0
        v = float(radai_geom.volume_cm3(
            np.asarray(cruas_base["brain"], dtype=bool), grade))
    except Exception as e:
        return False, u"nao consegui medir o encefalo (%s)" % type(e).__name__, 0.0
    if v < VOLUME_MINIMO_DE_ENCEFALO_CM3:
        return False, (u"so %.0f cm3 de encefalo no campo (minimo %.0f)"
                       % (v, VOLUME_MINIMO_DE_ENCEFALO_CM3)), v
    return True, u"%.0f cm3 de encefalo no campo" % v, v


def caixa(cruas_base, forma, grade, margem_mm=MARGEM_MM):
    import numpy as np
    m = None
    for n in ("brain", "skull"):
        if cruas_base is not None and n in cruas_base:
            a = np.asarray(cruas_base[n], dtype=bool)
            if a.any():
                m = a if m is None else (m | a)
    if m is None:
        raise ValueError(u"sem encefalo nem cranio para recortar")
    fora = []
    for i in range(3):
        eixo = np.where(m.any(axis=tuple(j for j in range(3) if j != i)))[0]
        mg = int(round(float(margem_mm) / max(float(grade.spacing[i]), 1e-6)))
        fora.append((max(0, int(eixo.min()) - mg),
                     min(int(forma[i]), int(eixo.max()) + mg + 1)))
    return (fora[0][0], fora[0][1], fora[1][0], fora[1][1],
            fora[2][0], fora[2][1])


def _torch_device(d):
    d = str(d or "").strip().lower()
    if d in ("gpu", "cuda"):
        return "cuda"
    if d.startswith("cuda:"):
        return d
    return "cpu"


_SCRIPT = r'''
import os, sys, multiprocessing
def _principal():
    for k in ("nnUNet_raw", "nnUNet_preprocessed", "nnUNet_results"):
        os.environ.setdefault(k, sys.argv[4])
    from nnunetv2.inference.predict_from_raw_data import nnUNetPredictor
    import torch
    pasta_peso, entrada, saida, _tmp, dispositivo = sys.argv[1:6]
    # GUARDA: use_mirroring=False -- espelhar troca esquerda por direita
    p = nnUNetPredictor(
        tile_step_size=0.5, use_gaussian=True, use_mirroring=False,
        device=torch.device(dispositivo), verbose=False,
        verbose_preprocessing=False, allow_tqdm=False)
    p.initialize_from_trained_model_folder(pasta_peso, use_folds=("all",),
                                           checkpoint_name="checkpoint_final.pth")
    p.predict_from_files([[entrada]], saida, save_probabilities=False,
                         overwrite=True, num_processes_preprocessing=1,
                         num_processes_segmentation_export=1)
    print("CRANIO_OK")


if __name__ == "__main__":
    # GUARDA: sem o guarda de __main__ o nnU-Net trava no Windows (spawn)
    multiprocessing.freeze_support()
    _principal()
'''


def rodar(nifti_entrada, destino_nii, python_exe=None, dispositivo="cpu",
          timeout_s=TETO_S, log=None, base=None):
    ok, peso = disponivel(base)
    if not ok:
        return False, peso
    trab = tempfile.mkdtemp(prefix="radai_cranio_")
    script = os.path.join(trab, "roda.py")
    with open(script, "w", encoding="utf-8") as f:
        f.write(_SCRIPT)
    saida_dir = os.path.join(trab, "out")
    os.makedirs(saida_dir, exist_ok=True)
    log_path = os.path.join(trab, "cranio.log")
    cmd = [python_exe or sys.executable, script, peso, nifti_entrada,
           saida_dir, trab, _torch_device(dispositivo)]
    import shutil
    try:
        with open(log_path, "wb") as saida:
            proc = subprocess.Popen(cmd, stdout=saida, stderr=subprocess.STDOUT)
            try:
                proc.wait(timeout=timeout_s)
            except subprocess.TimeoutExpired:
                try:
                    import radai_hnlnl_engine as HE
                    HE._encerrar_arvore(proc)
                except Exception:
                    proc.kill()
                return False, (u"o modelo do cranio passou de %d s e foi "
                               u"interrompido" % int(timeout_s))
        if proc.returncode != 0:
            cauda = u""
            try:
                with open(log_path, encoding="utf-8", errors="replace") as f:
                    cauda = f.read()[-400:]
            except Exception:
                pass
            return False, (u"o modelo do cranio terminou com codigo %s: %s"
                           % (proc.returncode, cauda))
        gerados = [x for x in os.listdir(saida_dir) if x.endswith(".nii.gz")]
        if not gerados:
            return False, u"o modelo do cranio rodou mas nao gravou saida"
        shutil.copy2(os.path.join(saida_dir, gerados[0]), destino_nii)
        return True, u""
    except Exception as e:
        return False, u"%s: %s" % (type(e).__name__, str(e)[:200])
    finally:
        shutil.rmtree(trab, ignore_errors=True)


def masks_do_mapa(rot, tabela):
    import numpy as np
    conferir_rotulos(tabela)
    rot = np.asarray(rot)
    fora = {}
    for idx, nome in sorted(tabela.items()):
        chave = PARA_O_FULL.get(nome)
        if not chave:
            continue
        m = rot == int(idx)
        if m.any():
            fora[chave] = m
    return fora


def segmentar_serie(ref, cruas_base, grade, python_exe=None, dispositivo="cpu",
              log=None, base=None, tempos=None):
    import numpy as np
    import SimpleITK as sitk

    def _log(m):
        if log:
            try:
                log(m)
            except Exception:
                pass

    def _marca(etapa, t0):
        if tempos is not None:
            tempos.append((etapa, time.time() - t0))

    tem, porque, _v = encefalo_no_campo(cruas_base, grade)
    if not tem:
        _log(u"cranio: nao roda nesta serie — %s" % porque)
        return {}
    ok, motivo = disponivel(base)
    if not ok:
        raise PesoAusente(motivo)
    _log(u"cranio: %s" % porque)
    forma = tuple(int(v) for v in reversed(ref.GetSize()))
    t0 = time.time()
    z0, z1, y0, y1, x0, x1 = caixa(cruas_base, forma, grade)
    rec = ref[x0:x1, y0:y1, z0:z1]
    trab = tempfile.mkdtemp(prefix="radai_cranio_in_")
    import shutil
    try:
        entrada = os.path.join(trab, "serie_0000.nii.gz")
        sitk.WriteImage(rec, entrada)
        _marca(u"recorte e escrita", t0)
        _log(u"  recorte pelo encefalo e cranio: %s de %s"
             % ((z1 - z0, y1 - y0, x1 - x0), forma))
        t1 = time.time()
        saida = os.path.join(trab, "saida.nii.gz")
        ok, motivo = rodar(entrada, saida, python_exe=python_exe,
                           dispositivo=dispositivo, log=log, base=base)
        _marca(u"inferencia", t1)
        if not ok:
            raise RuntimeError(motivo)
        t2 = time.time()
        rot = sitk.GetArrayFromImage(sitk.ReadImage(saida))
        if tuple(rot.shape) != (z1 - z0, y1 - y0, x1 - x0):
            raise ValueError(u"o modelo do cranio devolveu forma %s para um "
                             u"recorte %s" % (rot.shape, (z1 - z0, y1 - y0,
                                                          x1 - x0)))
        parciais = masks_do_mapa(rot, rotulos(base))
        fora = {}
        for k, m in parciais.items():
            cheio = np.zeros(forma, dtype=bool)
            cheio[z0:z1, y0:y1, x0:x1] = m
            fora[k] = cheio
        _marca(u"leitura e volta a grade", t2)
        return fora
    finally:
        shutil.rmtree(trab, ignore_errors=True)
