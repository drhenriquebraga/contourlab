# -*- coding: utf-8 -*-
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import types

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

AQUI = os.path.dirname(os.path.abspath(__file__))


def pasta_app(aqui):
    for c in (os.path.join(aqui, "..", "app"), os.path.join(aqui, "..")):
        if os.path.exists(os.path.join(c, "engine.py")):
            return os.path.abspath(c)
    return os.path.abspath(os.path.join(aqui, "..", "app"))


APP = pasta_app(AQUI)
sys.path.insert(0, APP)
sys.path.insert(0, AQUI)

os.environ["RADAI_CALIB_DIR"] = tempfile.mkdtemp(prefix="radai_ac_runner_")
os.environ["TOTALSEG_HOME_DIR"] = tempfile.mkdtemp(prefix="radai_tshome_runner_")
import atexit
atexit.register(shutil.rmtree, os.environ["TOTALSEG_HOME_DIR"], True)

import numpy as np
import engine as M
import radai_ts_runner as R
import _cleanup
import _componentes
_cleanup.adotar_prefixo("radai_teste_runner_")
_cleanup.adotar_prefixo("radai_ac_runner_")
_cleanup.adotar_prefixo("radai_tshome_runner_")

VERBOSO = "-v" in sys.argv
_RESULTADOS = []
PY = sys.executable

_MEUS_PIDS = set()


def checar(nome, condicao, detalhe=""):
    ok = bool(condicao)
    _RESULTADOS.append((nome, ok, detalhe))
    if VERBOSO or not ok:
        print("  %s  %s%s" % ("OK   " if ok else "FALHA", nome,
                              ("  [%s]" % (detalhe,)) if detalhe else ""))


def secao(t):
    print(u"\n-- %s --" % t)


def _vivo(pid):
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        k32 = ctypes.WinDLL("kernel32")
        k32.OpenProcess.restype = wintypes.HANDLE
        h = k32.OpenProcess(0x1000, False, int(pid))
        if not h:
            return False
        try:
            cod = wintypes.DWORD()
            if not k32.GetExitCodeProcess(h, ctypes.byref(cod)):
                return False
            return cod.value == 259
        finally:
            k32.CloseHandle(h)
    try:
        os.kill(int(pid), 0)
        return True
    except OSError:
        return False


def _encerrar_os_meus():
    for pid in sorted(_MEUS_PIDS):
        if _vivo(pid):
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                               capture_output=True, timeout=30)
            else:
                try:
                    os.kill(pid, 9)
                except OSError:
                    pass


def _ref():
    import SimpleITK as sitk
    vol = sitk.GetImageFromArray(np.zeros((8, 16, 16), dtype=np.int16))
    vol.SetSpacing((2.0, 2.0, 3.0))
    return vol


class _Calado(object):

    def __enter__(self):
        self._antigo, self._buf = sys.stdout, io.StringIO()
        sys.stdout = self._buf
        return self

    def __exit__(self, *a):
        sys.stdout = self._antigo
        self.texto = self._buf.getvalue()
        return False


class _Troca(object):

    def __init__(self, alvo, **novos):
        self.alvo, self.novos, self.velhos = alvo, novos, {}

    def __enter__(self):
        for k, v in self.novos.items():
            self.velhos[k] = getattr(self.alvo, k)
            setattr(self.alvo, k, v)
        return self

    def __exit__(self, *a):
        for k, v in self.velhos.items():
            setattr(self.alvo, k, v)
        return False


_PREAMBULO = u'''# -*- coding: utf-8 -*-
import json, os, subprocess, sys, time
args = sys.argv[1:]
def arg(nome):
    return args[args.index(nome) + 1] if nome in args else None
ENTRADA, SAIDA, TASK, DEV = arg("-i"), arg("-o"), arg("--task"), arg("--device")
REG = os.environ.get("FALSO_REGISTRO")
def registrar(**kw):
    if REG:
        with open(REG, "a") as f:
            f.write(json.dumps(kw) + "\\n")
def gravar_saida(truncar=False):
    import numpy as np
    import SimpleITK as sitk
    img = sitk.ReadImage(ENTRADA)
    a = np.zeros(sitk.GetArrayFromImage(img).shape, np.uint8)
    a[2:6, 3:9, 3:9] = 1
    a[2:6, 9:14, 9:14] = 2
    o = sitk.GetImageFromArray(a)
    o.CopyInformation(img)
    sitk.WriteImage(o, SAIDA)
    if truncar:
        n = os.path.getsize(SAIDA)
        with open(SAIDA, "r+b") as f:
            f.truncate(max(16, n // 2))
def linha(t):
    sys.stdout.write(t + "\\n")
    sys.stdout.flush()
registrar(pid=os.getpid(), task=TASK, dev=DEV,
          na_cpu=os.environ.get("RADAI_RESULTADOS_NA_CPU", ""),
          visiveis=os.environ.get("CUDA_VISIBLE_DEVICES", ""))
'''


def _runner_falso(tmp, corpo):
    cam = os.path.join(tmp, "runner_falso_%d.py" % len(os.listdir(tmp)))
    with io.open(cam, "w", encoding="utf-8") as f:
        f.write(_PREAMBULO + corpo)
    return cam


def _registro(cam):
    try:
        with io.open(cam, encoding="utf-8") as f:
            regs = [json.loads(l) for l in f if l.strip()]
    except OSError:
        return []
    for r in regs:
        for k in ("pid", "neto"):
            if r.get(k):
                _MEUS_PIDS.add(int(r[k]))
    return regs


def _log_do_job(jid):
    return list((M._job(jid) or {}).get("log") or [])


def _rodar_task(tmp, corpo, task="head_glands_cavities", device="cpu",
                timeout_s=40, mapa=None, plano=None, eleita=None,
                trava=None, plano_menor=None, caixa=None, cruas=None,
                job=None, envelope=False, ref=None, **trocas):
    falso = _runner_falso(tmp, corpo)
    reg = os.path.join(tmp, "registro_%d.jsonl" % len(os.listdir(tmp)))
    mapa = mapa or {M._nome_biblioteca(task): {1: "parotid_gland_left",
                                                2: "parotid_gland_right"}}
    novos = dict(TS_CMD=[PY, falso], TS_CLASS_MAP=mapa)
    if envelope:
        novos["RUNNER_TS"] = falso
    if plano is not None:
        novos["plano_de_dispositivo"] = (lambda *a, **k: dict(plano))
    if eleita is not None:
        novos["base_eleita"] = (lambda modalidade="CT", **k:
                                eleita.get(str(modalidade).upper()))
    novos.update(trocas)
    extra = {}
    if trava is not None:
        extra["trava"] = trava
    if plano_menor is not None:
        extra["plano_menor"] = plano_menor
    if caixa is not None:
        extra["caixa"] = caixa
    if cruas is not None:
        extra["cruas"] = cruas
    jid = M._job_new()
    velho_reg = os.environ.get("FALSO_REGISTRO")
    os.environ["FALSO_REGISTRO"] = reg
    t0 = time.time()
    try:
        with _Troca(M, **novos):
            try:
                r = M.run_ts_task(ref if ref is not None else _ref(), task,
                                  device, jid, timeout_s=timeout_s,
                                  suavizar=False, **extra)
            except Exception as e:
                r = e
        if isinstance(job, dict):
            job.update(M._job(jid) or {})
        return r, _log_do_job(jid), _registro(reg), time.time() - t0
    finally:
        if velho_reg is None:
            os.environ.pop("FALSO_REGISTRO", None)
        else:
            os.environ["FALSO_REGISTRO"] = velho_reg
        M._job_del(jid)


def _harness(tmp, corpo, nome="harness"):
    cam = os.path.join(tmp, "%s_%d.py" % (nome, len(os.listdir(tmp))))
    with io.open(cam, "w", encoding="utf-8") as f:
        f.write(u"# -*- coding: utf-8 -*-\nimport sys, threading, time\n"
                u"sys.path.insert(0, %r)\nimport radai_ts_runner as R\n"
                % APP + corpo)
    return cam


def teste_o_envelope_mata_a_thread_orfa():
    secao(u"A1 · o envelope mata a thread orfa")
    tmp = tempfile.mkdtemp(prefix="radai_teste_runner_")
    try:
        cam = _harness(tmp, u'''
if len(sys.argv) > 1 and sys.argv[1] == "isca":
    R._SAIR = sys.exit
def main():
    t = threading.Thread(target=time.sleep, args=(600,))
    t.daemon = False
    t.start()
    print("main falso terminou")
R.executar(main, [])
''')
        t0 = time.time()
        try:
            r = subprocess.run([PY, cam], capture_output=True, text=True,
                               timeout=10)
            dt = time.time() - t0
            checar(u"o processo termina em < 10 s com a thread orfa viva",
                   dt < 10, u"%.1f s" % dt)
            checar(u"  e sai com o codigo do main (0)", r.returncode == 0,
                   str(r.returncode))
            checar(u"  e a linha RADAI|fim|codigo=0 foi escrita",
                   "RADAI|fim|codigo=0" in r.stdout, r.stdout[-120:])
        except subprocess.TimeoutExpired:
            checar(u"o processo termina em < 10 s com a thread orfa viva",
                   False, u"expirou: o os._exit nao agiu")
        try:
            subprocess.run([PY, cam, "isca"], capture_output=True, text=True,
                           timeout=5)
            preso = False
        except subprocess.TimeoutExpired:
            preso = True
        checar(u"ISCA: com sys.exit no lugar do os._exit o processo NAO sai",
               preso, u"se sair, a checagem de cima nao prova nada")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def teste_o_envelope_devolve_o_codigo():
    secao(u"A1 · o codigo de saida do main chega ao motor")
    tmp = tempfile.mkdtemp(prefix="radai_teste_runner_")
    casos = (
        (u"def main():\n    return None\n", 0, u"None"),
        (u"def main():\n    raise ValueError('quebrou de proposito')\n", 1,
         u"excecao"),
        (u"def main():\n    raise SystemExit(3)\n", 3, u"SystemExit(3)"),
        (u"def main():\n    sys.exit('mensagem de erro')\n", 1,
         u"SystemExit(texto)"),
    )
    try:
        for corpo, esperado, nome in casos:
            cam = _harness(tmp, corpo + u"R.executar(main, ['-i', 'x'])\n")
            r = subprocess.run([PY, cam], capture_output=True, text=True,
                               timeout=30)
            checar(u"main com %s sai com %d" % (nome, esperado),
                   r.returncode == esperado,
                   u"saiu %s | %s" % (r.returncode, r.stderr[-120:]))
            if nome == u"excecao":
                checar(u"  e o traceback sai (e o diagnostico do motor)",
                       "ValueError: quebrou de proposito" in r.stderr,
                       r.stderr[-160:])
        cam = _harness(tmp, u'''
def engolir(main, argv, prog="TotalSegmentator"):
    try:
        main()
    except BaseException:
        pass
    return 0
R.rodar = engolir
def main():
    raise SystemExit(3)
R.executar(main, [])
''')
        r = subprocess.run([PY, cam], capture_output=True, text=True,
                           timeout=30)
        checar(u"ISCA: um envelope que engole o codigo devolveria 0 no lugar "
               u"de 3", r.returncode == 0, str(r.returncode))
        visto = []

        def main_argv():
            visto.append(list(sys.argv))
        cod = R.rodar(main_argv, ["-i", "a.nii.gz", "--task", "total_v3"])
        checar(u"o argv do motor chega ao main do TotalSegmentator",
               cod == 0 and visto and visto[0][1:] ==
               ["-i", "a.nii.gz", "--task", "total_v3"], str(visto))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


_MAIN_QUE_REGISTRA = u'''
import json, os
def main():
    args = sys.argv[1:]
    with open(os.environ["FALSO_REGISTRO"], "a") as f:
        f.write(json.dumps({"argv": args}) + "\\n")
    import numpy as np
    import SimpleITK as sitk
    img = sitk.ReadImage(args[args.index("-i") + 1])
    a = np.zeros(sitk.GetArrayFromImage(img).shape, np.uint8)
    a[2:6, 3:9, 3:9] = 1
    o = sitk.GetImageFromArray(a)
    o.CopyInformation(img)
    sitk.WriteImage(o, args[args.index("-o") + 1])
'''


def teste_o_body_seg_passa_intacto():
    secao(u"A1 · o --body_seg passa pelo envelope intacto")
    tmp = tempfile.mkdtemp(prefix="radai_teste_runner_")
    pesos = tempfile.mkdtemp(prefix="radai_teste_runner_pesos_")
    import radai_tasks as T
    cam = os.path.join(pesos, T.DATASET_DO_BODY_PASTA, T.PESO_DO_BODY)
    os.makedirs(os.path.dirname(cam))
    open(cam, "wb").close()
    velho = os.environ.get("TOTALSEG_WEIGHTS_PATH")
    os.environ["TOTALSEG_WEIGHTS_PATH"] = pesos
    mapa = {"total_v3": {1: "liver"}}
    eleita = {"CT": "total_v3", "MR": "total_mr"}
    try:
        env = _harness(tmp, _MAIN_QUE_REGISTRA
                       + u"R.executar(main, sys.argv[1:])\n", nome="env")
        r, log, reg, _ = _rodar_task(tmp, u"", task="total_v3", mapa=mapa,
                                     eleita=eleita, timeout_s=60,
                                     TS_CMD=[PY, env])
        argv = (reg[0].get("argv") if reg else None) or []
        checar(u"a serie sai pelo envelope de verdade",
               isinstance(r, dict) and "liver" in r, repr(r)[:120])
        checar(u"o main do TotalSegmentator recebe --body_seg",
               "--body_seg" in argv, str(argv)[-160:])
        checar(u"  no fim, depois do -v, como o motor o pos (nada reordenado)",
               argv[-2:] == ["-v", "--body_seg"], str(argv[-4:]))
        checar(u"  e o resto do comando chega igual (task, --ml, dispositivo)",
               argv[argv.index("--task") + 1] == "total_v3" and "--ml" in argv
               and argv[argv.index("--device") + 1] == "cpu", str(argv))
        isca = _harness(tmp, _MAIN_QUE_REGISTRA + u'''
_orig = R.rodar
R.rodar = lambda main, argv, prog="TotalSegmentator": _orig(
    main, [a for a in argv if a != "--body_seg"], prog)
R.executar(main, sys.argv[1:])
''', nome="isca")
        r2, log2, reg2, _ = _rodar_task(tmp, u"", task="total_v3", mapa=mapa,
                                        eleita=eleita, timeout_s=60,
                                        TS_CMD=[PY, isca])
        argv2 = (reg2[0].get("argv") if reg2 else None) or []
        checar(u"ISCA: um envelope que filtra argumento tira a flag",
               argv2 and "--body_seg" not in argv2, str(argv2)[-120:])
    finally:
        if velho is None:
            os.environ.pop("TOTALSEG_WEIGHTS_PATH", None)
        else:
            os.environ["TOTALSEG_WEIGHTS_PATH"] = velho
        _encerrar_os_meus()
        shutil.rmtree(tmp, ignore_errors=True)
        shutil.rmtree(pesos, ignore_errors=True)


def _predictor_falso():
    mod = types.ModuleType("predict_falso")

    class PredictorFalso(object):
        def __init__(self, tile_step_size=0.5, use_gaussian=True,
                     use_mirroring=False, perform_everything_on_device=True,
                     device=None, verbose=False, verbose_preprocessing=False,
                     allow_tqdm=True):
            self.perform_everything_on_device = perform_everything_on_device
            self.device = device

        def initialize_from_trained_model_folder(self, pasta, use_folds=None,
                                                 checkpoint_name=None):
            self.pasta = pasta
    mod.nnUNetPredictor = PredictorFalso
    import multiprocessing
    mod.multiprocessing = multiprocessing
    return mod


def teste_resultados_na_cpu_chega_ao_predictor():
    secao(u"A1 · o resultado na RAM chega ao predictor")
    mod = _predictor_falso()
    with _Calado() as cal:
        feitos = R.aplicar_remendos(resultados_na_cpu=True, sem_autocast=False,
                                    modulo=mod)
        p = mod.nnUNetPredictor(tile_step_size=0.5, use_mirroring=False,
                                perform_everything_on_device=True,
                                device="cuda")
    checar(u"o remendo foi aplicado", "resultados_na_cpu" in feitos,
           str(feitos))
    checar(u"  e se anuncia (RADAI|remendo|resultados_na_cpu=1)",
           "RADAI|remendo|resultados_na_cpu=1" in cal.texto, cal.texto[:120])
    checar(u"por NOME: o predictor recebe perform_everything_on_device=False",
           p.perform_everything_on_device is False,
           str(p.perform_everything_on_device))
    construir = mod.nnUNetPredictor
    with _Calado():
        p2 = construir(0.5, True, False, True)
    checar(u"por POSICAO tambem", p2.perform_everything_on_device is False,
           str(p2.perform_everything_on_device))
    mod2 = _predictor_falso()
    with _Calado() as cal2:
        R.aplicar_remendos(resultados_na_cpu=False, sem_autocast=False,
                           modulo=mod2)
        p3 = mod2.nnUNetPredictor(use_mirroring=False,
                                  perform_everything_on_device=True)
    checar(u"ISCA: sem o pedido, a biblioteca fica como e (True)",
           p3.perform_everything_on_device is True,
           str(p3.perform_everything_on_device))
    checar(u"  e nada se anuncia", "resultados_na_cpu" not in cal2.texto,
           cal2.texto[:120])
    mod3 = _predictor_falso()
    velho = os.environ.get("RADAI_RESULTADOS_NA_CPU")
    os.environ["RADAI_RESULTADOS_NA_CPU"] = "1"
    try:
        with _Calado():
            R.aplicar_remendos(modulo=mod3)
    finally:
        if velho is None:
            os.environ.pop("RADAI_RESULTADOS_NA_CPU", None)
        else:
            os.environ["RADAI_RESULTADOS_NA_CPU"] = velho
    with _Calado():
        p_amb = mod3.nnUNetPredictor(use_mirroring=False)
    checar(u"o caminho de campo le RADAI_RESULTADOS_NA_CPU do ambiente",
           p_amb.perform_everything_on_device is False)
    R._ESTADO.update(dataset=None, redes=0)
    with _Calado():
        p4 = mod3.nnUNetPredictor(use_mirroring=False)
        p4.initialize_from_trained_model_folder(
            "x/Dataset833_TotalSegmentator_part3_cardiac_1830subj/y")
    checar(u"a rede carregada vira `dataset=833` no batimento",
           "dataset=833" in R.amostra(), R.amostra())
    R._ESTADO.update(dataset=None, redes=0)


def teste_sem_autocast_so_no_predictor():
    secao(u"A1 · autocast desligado so onde o predictor o abre")
    chamadas = []

    def autocast_falso(*a, **k):
        chamadas.append((a, k))
        import contextlib
        return contextlib.nullcontext()
    torch_falso = types.SimpleNamespace(autocast=autocast_falso,
                                        zeros=lambda *a: "zeros-de-verdade")

    def montar():
        mod = _predictor_falso()
        mod.torch = torch_falso
        exec(u"def prever():\n"
             u"    with torch.autocast('cuda', enabled=True):\n"
             u"        return torch.zeros(3)\n", mod.__dict__)
        return mod
    m1 = montar()
    m1.prever()
    checar(u"ISCA: sem o remendo, o predictor abre o autocast",
           len(chamadas) == 1, str(len(chamadas)))
    del chamadas[:]
    m2 = montar()
    with _Calado():
        R.aplicar_remendos(resultados_na_cpu=False, sem_autocast=True,
                           modulo=m2)
    r = m2.prever()
    checar(u"com RADAI_SEM_AUTOCAST o autocast NAO e aberto",
           not chamadas, str(chamadas))
    checar(u"  e o resto do torch do modulo continua o de verdade",
           r == "zeros-de-verdade", str(r))
    checar(u"  e o torch do PROCESSO nao foi tocado",
           torch_falso.autocast is autocast_falso)
    try:
        import inspect
        with _Calado():
            import nnunetv2.inference.predict_from_raw_data as real
        fonte = inspect.getsource(
            real.nnUNetPredictor.predict_sliding_window_return_logits)
        checar(u"no nnU-Net instalado o autocast e aberto por `torch.autocast`"
               u" dentro de predict_sliding_window_return_logits",
               "torch.autocast(" in fonte)
        sig = inspect.signature(real.nnUNetPredictor.__init__)
        checar(u"  e o __init__ tem perform_everything_on_device",
               "perform_everything_on_device" in sig.parameters)
    except ImportError:
        pass


def teste_as_pastas_do_nnunet_vem_antes_dos_remendos():
    secao(u"A1 · as pastas do nnU-Net vem antes dos remendos")
    velho = os.environ.pop("nnUNet_results", None)
    saida = io.StringIO()
    antigo = sys.stdout
    try:
        sys.stdout = saida
        feitos = R.aplicar_remendos(resultados_na_cpu=True)
    finally:
        sys.stdout = antigo
        if velho is not None:
            os.environ["nnUNet_results"] = velho
    checar(u"sem nnUNet_results, os remendos NAO importam o nnU-Net",
           feitos == [] and "remendos NAO aplicados" in saida.getvalue(),
           saida.getvalue()[:120])
    try:
        import nnunetv2
        import totalsegmentator
    except ImportError:
        return
    tmp = tempfile.mkdtemp(prefix="radai_teste_runner_")
    try:
        cam = _harness(tmp, u'''
import os
os.environ.pop("nnUNet_results", None)
os.environ["TOTALSEG_WEIGHTS_PATH"] = sys.argv[1]
if sys.argv[2] == "isca":
    import nnunetv2.inference.predict_from_raw_data  # antes de preparar
R._preparar_nnunet()
R.aplicar_remendos(resultados_na_cpu=True)
import nnunetv2.paths as p
print("PASTA=%s" % p.nnUNet_results)
''')
        r = subprocess.run([PY, cam, tmp, "certo"], capture_output=True,
                           text=True, timeout=180)
        checar(u"no bundle: preparado antes, o nnU-Net ve a pasta dos pesos",
               ("PASTA=%s" % tmp) in r.stdout, (r.stdout + r.stderr)[-160:])
        r2 = subprocess.run([PY, cam, tmp, "isca"], capture_output=True,
                            text=True, timeout=180)
        checar(u"ISCA: importado ANTES de preparar, a pasta fica None",
               "PASTA=None" in r2.stdout, (r2.stdout + r2.stderr)[-160:])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def teste_o_pulso_nao_inicializa_o_cuda():
    secao(u"A1 · o pulso mede e nao inventa")
    perguntas = []

    class CudaFalso(object):
        def __init__(self, ini):
            self.ini = ini

        def is_initialized(self):
            return self.ini

        def mem_get_info(self, *a):
            perguntas.append("mem_get_info")
            return (2 * 1024 ** 3, 5 * 1024 ** 3)

        def memory_allocated(self, *a):
            return 1024 ** 3

        def memory_reserved(self, *a):
            return 1536 * 1024 ** 2
    velho = sys.modules.get("torch")
    try:
        sys.modules["torch"] = types.SimpleNamespace(cuda=CudaFalso(False))
        a1 = R.amostra()
        checar(u"CUDA nao inicializado: nenhuma pergunta a placa",
               not perguntas and "vram_mb" not in a1, a1)
        sys.modules["torch"] = types.SimpleNamespace(cuda=CudaFalso(True))
        a2 = R.amostra()
        checar(u"CUDA inicializado: vram_mb=usada/total medida",
               "vram_mb=3072/5120" in a2 and perguntas, a2)
        checar(u"  e a parte do torch sai junto", "torch_mb=1024/1536" in a2,
               a2)
    finally:
        if velho is None:
            sys.modules.pop("torch", None)
        else:
            sys.modules["torch"] = velho
    rss = R._rss_mb()
    checar(u"a memoria do processo e MEDIDA (nao inventada)",
           rss is None or (isinstance(rss, int) and rss > 0), str(rss))
    if os.name == "nt":
        checar(u"  e no Windows ela sai (GetProcessMemoryInfo)",
               isinstance(rss, int) and rss > 0, str(rss))
    tmp = tempfile.mkdtemp(prefix="radai_teste_runner_")
    try:
        cam = _harness(tmp, u"def main():\n    time.sleep(1.6)\n"
                            u"R.executar(main, [])\n")
        amb = dict(os.environ, RADAI_PULSO_S="0.4")
        r = subprocess.run([PY, cam], capture_output=True, text=True,
                           timeout=30, env=amb)
        n = r.stdout.count("RADAI|pulso|")
        checar(u"o batimento sai durante o main (RADAI_PULSO_S=0,4)", n >= 2,
               u"%d pulso(s)" % n)
        checar(u"  e cada pulso traz rss_mb", "rss_mb=" in r.stdout,
               r.stdout[:160])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


PARTES_V3 = [24, 26, 18, 23, 26]
PLANEJAMENTO = ((96, 512, 512), (5.0, 500.0 / 512, 500.0 / 512))
TORAX = ((409, 512, 512), (326.0 / 409, 400.0 / 512, 400.0 / 512))


def _placa(i, nome, total, livre, cap="6.1"):
    return {"indice": i, "nome": nome, "total_mb": total, "livre_mb": livre,
            "capacidade": cap}


def _plano(geom, placas, erro=""):
    return M.plano_de_dispositivo(geom[0], geom[1], task="total_v3",
                                  inv={"placas": placas, "erro": erro},
                                  partes=PARTES_V3)


def teste_o_plano_escolhe_pela_vram_livre():
    secao(u"A2 · o plano de dispositivo")
    vox_plan = M.plano_de_dispositivo(*PLANEJAMENTO, task="total_v3",
                                      inv={"placas": []},
                                      partes=PARTES_V3)["voxels"]
    vox_tx = M.plano_de_dispositivo(*TORAX, task="total_v3",
                                    inv={"placas": []},
                                    partes=PARTES_V3)["voxels"]
    checar(u"a conta e do CAMPO DE VISAO: planejamento 35,7 M voxels a 1,5 mm",
           35.0e6 < vox_plan < 36.5e6, u"%.2f M" % (vox_plan / 1e6))
    checar(u"  e o torax diagnostico, com 4x mais cortes, 15,5 M",
           15.0e6 < vox_tx < 16.0e6, u"%.2f M" % (vox_tx / 1e6))

    p = _plano(PLANEJAMENTO, [_placa(0, "Quadro P2200", 5120, 2048)])
    checar(u"P2200, 2048 MiB livres, planejamento -> gpu_resultado_na_cpu "
           u"(a rede cabe com a margem de 256)",
           p["modo"] == "gpu_resultado_na_cpu",
           u"%s | rede %d + margem %d <= %d" % (
               p["modo"], p["precisa_rede_mb"], p["margem_rede_mb"],
               p["vram_livre_mb"]))
    vox = p["voxels"]
    mib = M._mib
    fixo = (M.CONTEXTO_CUDA_MB + M.PESOS_MB + M.COPIA_FP16_PESOS_MB
            + M.PATCHES_MB)
    rede = fixo + M.ATIVACOES_FP16_MB
    cab = max(PARTES_V3) + 1
    resultado = mib(vox * 4) + mib(vox * 2) + mib(cab * vox * 2) + \
        M.GAUSSIANA_MB
    isinf = mib(cab * vox)
    tudo = fixo + resultado + max(M.ATIVACOES_FP16_MB, isinf)
    checar(u"  a rede e fixo + ativacao fp16 medida (%d MiB)" % rede,
           p["precisa_rede_mb"] == rede == 1358, p["precisa_rede_mb"])
    checar(u"  o tudo-na-placa leva o isinf do fim da parte (%d MiB), que "
           u"passa a fase dos patches nesta grade" % isinf,
           p["precisa_tudo_mb"] == tudo == 3481 and isinf > M.ATIVACOES_FP16_MB
           and p["fase_do_pico"] == u"isinf",
           u"%d / %d (%s)" % (p["precisa_tudo_mb"], tudo, p["fase_do_pico"]))
    checar(u"  e as duas margens: 768 no degrau placa/RAM, 256 no rede/CPU",
           p["margem_mb"] == 768 and p["margem_rede_mb"] == 256,
           u"%d / %d" % (p["margem_mb"], p["margem_rede_mb"]))
    checar(u"  e o motivo diz os dois numeros e a margem de CADA degrau",
           u"tudo na placa precisa 3,4 GiB" in p["motivo"]
           and u"margem 0,75 do degrau placa/RAM" in p["motivo"]
           and u"so a rede precisa 1,3 GiB" in p["motivo"]
           and u"margem 0,25 do degrau rede/CPU" in p["motivo"]
           and u"livre 2,0" in p["motivo"], p["motivo"])
    p3 = _plano(PLANEJAMENTO, [_placa(0, "Quadro P2200", 5120, 3072)])
    checar(u"P2200, 3072 MiB livres, planejamento -> gpu_resultado_na_cpu",
           p3["modo"] == "gpu_resultado_na_cpu",
           u"%s | tudo %d, rede %d, margem %d" % (
               p3["modo"], p3["precisa_tudo_mb"], p3["precisa_rede_mb"],
               p3["margem_mb"]))
    pa = _plano(TORAX, [_placa(0, "RTX A2000", 6144, 6000, "8.6")])
    checar(u"A2000, 6000 MiB livres, torax -> gpu", pa["modo"] == "gpu",
           u"%s | tudo %d + margem %d" % (pa["modo"], pa["precisa_tudo_mb"],
                                          pa["margem_mb"]))
    checar(u"  e a margem e 15%% de uma placa de 6 GiB (921), nao os 768",
           pa["margem_mb"] == 921, str(pa["margem_mb"]))
    p0 = _plano(PLANEJAMENTO, [])
    checar(u"sem placa -> cpu, e o motivo diz que nao ha placa",
           p0["modo"] == "cpu" and "nenhuma placa" in p0["motivo"],
           p0["motivo"])
    pe = _plano(PLANEJAMENTO, [], erro=u"nvidia-smi nao encontrado")
    checar(u"sem conseguir medir -> cpu, e o motivo DIZ que nao mediu",
           pe["modo"] == "cpu" and "nao consegui medir a VRAM" in pe["motivo"]
           and "nvidia-smi nao encontrado" in pe["motivo"], pe["motivo"])
    p4 = _plano(TORAX, [_placa(0, "placa pequena", 4096, 400)])
    checar(u"placa com 400 MiB livres -> cpu", p4["modo"] == "cpu",
           p4["motivo"][:80])
    p2 = _plano(TORAX, [_placa(0, "monitor", 6144, 1500),
                        _placa(1, "livre", 6144, 5900)])
    checar(u"duas placas -> a de MAIS VRAM livre, com o indice",
           p2["indice"] == 1 and p2["placa"] == "livre"
           and p2["modo"] == "gpu", u"%s %s %s" % (p2["indice"], p2["placa"],
                                                    p2["modo"]))
    checar(u"o motivo leva os numeros (GiB, voxels, margem)",
           "GiB" in p3["motivo"] and "M voxels" in p3["motivo"]
           and "margem" in p3["motivo"], p3["motivo"])
    f1 = [_placa(0, "Quadro P2200", 5120, 3900)]
    q1 = _plano(PLANEJAMENTO, f1)
    with _Troca(M, MARGEM_MINIMA_MB=0, MARGEM_FRACAO=0.0):
        q1z = _plano(PLANEJAMENTO, f1)
    with _Troca(M, MARGEM_REDE_MB=0):
        q1r = _plano(PLANEJAMENTO, f1)
    checar(u"ISCA degrau placa/RAM: com 3900 livres, zerar a margem DELE muda "
           u"gpu_resultado_na_cpu -> gpu (e zerar a do outro nao muda nada)",
           q1["modo"] == "gpu_resultado_na_cpu" and q1z["modo"] == "gpu"
           and q1r["modo"] == "gpu_resultado_na_cpu",
           u"%s / %s / %s" % (q1["modo"], q1z["modo"], q1r["modo"]))
    f2 = [_placa(0, "Quadro P2200", 5120, 1500)]
    q2 = _plano(PLANEJAMENTO, f2)
    with _Troca(M, MARGEM_REDE_MB=0):
        q2z = _plano(PLANEJAMENTO, f2)
    with _Troca(M, MARGEM_MINIMA_MB=0, MARGEM_FRACAO=0.0):
        q2m = _plano(PLANEJAMENTO, f2)
    checar(u"ISCA degrau rede/CPU: com 1500 livres, zerar a margem DELE muda "
           u"cpu -> gpu_resultado_na_cpu (e zerar a do outro nao muda nada)",
           q2["modo"] == "cpu" and q2z["modo"] == "gpu_resultado_na_cpu"
           and q2m["modo"] == "cpu",
           u"%s / %s / %s" % (q2["modo"], q2z["modo"], q2m["modo"]))
    f3 = [_placa(0, "Quadro P2200", 5120, 4200)]
    q3 = _plano(PLANEJAMENTO, f3)
    alvo_isinf = cab * vox
    real_mib = M._mib

    def _sem_isinf(v):
        return 0 if int(v) == alvo_isinf else real_mib(v)
    with _Troca(M, _mib=_sem_isinf):
        q3z = _plano(PLANEJAMENTO, f3)
    checar(u"ISCA isinf: com 4200 livres, a conta com o isinf manda o "
           u"resultado para a RAM; sem ele, a mesma serie iria inteira para a "
           u"placa", q3["modo"] == "gpu_resultado_na_cpu"
           and q3z["modo"] == "gpu",
           u"%s / %s" % (q3["modo"], q3z["modo"]))


def teste_o_plano_nao_abre_cuda_neste_processo():
    secao(u"A2 · a medida nao abre contexto CUDA no vigia")
    tmp = tempfile.mkdtemp(prefix="radai_teste_runner_")
    try:
        cam = os.path.join(tmp, "plano_limpo.py")
        with io.open(cam, "w", encoding="utf-8") as f:
            f.write(u"import json, os, sys, tempfile\n"
                    u"sys.path.insert(0, %r)\n"
                    u"os.environ['RADAI_CALIB_DIR'] = tempfile.mkdtemp("
                    u"prefix='radai_ac_runner_')\n"
                    u"import engine\n"
                    u"if sys.argv[1:] == ['isca']:\n"
                    u"    def _no_processo():\n"
                    u"        import torch\n"
                    u"        torch.cuda.is_available()\n"
                    u"        return {'placas': [], 'erro': ''}\n"
                    u"    engine._vram_por_placa = _no_processo\n"
                    u"antes = 'torch' in sys.modules\n"
                    u"p = engine.plano_de_dispositivo((409, 512, 512), "
                    u"(0.8, 0.78, 0.78), task='total_v3')\n"
                    u"print('JSON=' + json.dumps({'modo': p['modo'], "
                    u"'motivo': p['motivo'], 'antes': antes, "
                    u"'depois': 'torch' in sys.modules}))\n" % APP)
        r = subprocess.run([PY, cam], capture_output=True, text=True,
                           timeout=300)
        linha = [l for l in r.stdout.splitlines() if l.startswith("JSON=")]
        p = json.loads(linha[0][5:]) if linha else {}
        checar(u"sem placa alcancavel o plano cai para cpu, e diz por que",
               p.get("modo") == "cpu" and p.get("motivo"),
               (p.get("motivo") or r.stderr[-200:])[:140])
        checar(u"  e o torch NAO foi importado no processo que perguntou",
               p and not p.get("antes") and not p.get("depois"), str(p)[:160])
        import importlib.util
        if importlib.util.find_spec("torch") is not None:
            r2 = subprocess.run([PY, cam, "isca"], capture_output=True,
                                text=True, timeout=300)
            l2 = [l for l in r2.stdout.splitlines() if l.startswith("JSON=")]
            p2 = json.loads(l2[0][5:]) if l2 else {}
            checar(u"ISCA: medir no proprio processo importaria o torch nele",
                   p2.get("depois") is True, str(p2)[:160])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    checar(u"a pergunta ao sistema e o nvidia-smi, com tempo-limite",
           M.TEMPO_NVIDIA_SMI_S > 0 and M.TEMPO_TORCH_S > 0)
    ns, de_onde = M._classes_por_parte("total_v3")
    try:
        import totalsegmentator.map_to_binary
        checar(u"com a biblioteca: as cinco redes da total_v3, do class_map",
               ns == PARTES_V3 and "biblioteca" in de_onde,
               u"%s (%s)" % (ns, de_onde))
        ns_mr, _ = M._classes_por_parte("total_mr")
        checar(u"  e as duas da total_mr (29 + 21)", ns_mr == [29, 21],
               str(ns_mr))
    except ImportError:
        checar(u"sem a biblioteca: o recuo e o catalogo como UMA rede "
               u"(grosseiro para cima)",
               ns == [117] and "catalogo" in de_onde,
               u"%s (%s)" % (ns, de_onde))


def _smi_falso(resposta_cap):
    def run(cmd, *a, **k):
        q = [str(x) for x in cmd if str(x).startswith("--query-gpu=")]
        q = q[0] if q else ""
        if "compute_cap" in q:
            if isinstance(resposta_cap, BaseException):
                raise resposta_cap
            rc, out, err = resposta_cap
            return subprocess.CompletedProcess(cmd, rc, out, err)
        if "memory.free" in q:
            return subprocess.CompletedProcess(
                cmd, 0, "0, Quadro P2200, 5120, 2048\n", "")
        raise AssertionError(u"pergunta inesperada ao sistema: %r" % (cmd,))
    return run


def teste_a_capacidade_que_nao_veio_e_dita():
    secao(u"A2 · a capacidade que nao veio e dita")
    import subprocess as sp
    casos = (
        (u"driver sem o campo (codigo 2)",
         (2, u'Field "compute_cap" is not a valid field to query.\n', u""),
         (u"compute_cap nao lida", u"codigo 2", u"not a valid field")),
        (u"tempo esgotado",
         sp.TimeoutExpired(["nvidia-smi"], M.TEMPO_NVIDIA_SMI_S),
         (u"compute_cap nao lida", u"TimeoutExpired")),
        (u"campo conhecido sem valor ([N/A])",
         (0, u"0, [N/A]\n", u""),
         (u"compute_cap sem valor para a placa 0", u"[N/A]")),
    )
    for nome, resposta, esperado in casos:
        with _Troca(sp, run=_smi_falso(resposta)), \
                _Troca(M, _achar_nvidia_smi=lambda: "nvidia-smi"):
            inv = M._vram_por_placa()
        placas = inv.get("placas") or []
        aviso = inv.get("aviso") or u""
        checar(u"%s: a placa continua no inventario, SEM capacidade" % nome,
               len(placas) == 1 and placas[0].get("capacidade") is None
               and placas[0].get("livre_mb") == 2048, str(placas))
        checar(u"  e o inventario diz POR QUE", all(e in aviso
                                                    for e in esperado),
               aviso or u"(aviso vazio)")
        p = M.plano_de_dispositivo(PLANEJAMENTO[0], PLANEJAMENTO[1],
                                   task="total_v3", inv=inv, partes=PARTES_V3)
        checar(u"  e o motivo do plano leva «sm nao lido» com a causa",
               u"sm nao lido" in p["motivo"] and esperado[-1] in p["motivo"],
               p["motivo"][:200])
    with _Troca(sp, run=_smi_falso((0, u"0, 6.1\n", u""))), \
            _Troca(M, _achar_nvidia_smi=lambda: "nvidia-smi"):
        inv = M._vram_por_placa()
    checar(u"capacidade lida: 6.1, e aviso vazio",
           (inv.get("placas") or [{}])[0].get("capacidade") == "6.1"
           and not inv.get("aviso"), str(inv)[:160])
    p = M.plano_de_dispositivo(PLANEJAMENTO[0], PLANEJAMENTO[1],
                               task="total_v3", inv=inv, partes=PARTES_V3)
    checar(u"  e o motivo diz «sm 6.1», sem «sm nao lido»",
           u"sm 6.1" in p["motivo"] and u"sm nao lido" not in p["motivo"],
           p["motivo"][:160])
    velho = {"placas": [_placa(0, "Quadro P2200", 5120, 2048, cap=None)],
             "erro": ""}
    pv = M.plano_de_dispositivo(PLANEJAMENTO[0], PLANEJAMENTO[1],
                                task="total_v3", inv=velho, partes=PARTES_V3)
    checar(u"ISCA: sem a causa no inventario, o motivo nao tem o porque "
           u"(so «nao trouxe a causa»)",
           u"codigo 2" not in pv["motivo"]
           and u"o inventario nao trouxe a causa" in pv["motivo"],
           pv["motivo"][:160])


def teste_a_resposta_que_nao_se_le_cai_no_recuo():
    secao(u"K · a resposta do nvidia-smi que nao se le cai no recuo")

    def dublado(torch_responde):
        def run(cmd, *a, **k):
            txt = [str(x) for x in cmd]
            q = [x for x in txt if x.startswith("--query-gpu=")]
            if q and "memory.free" in q[0]:
                return subprocess.CompletedProcess(
                    cmd, 0, "0, Quadro P2200, [N/A], [N/A]\n", "")
            if "-c" in txt:
                if torch_responde:
                    return subprocess.CompletedProcess(
                        cmd, 0, "RADAI|0|5120|2048|6.1|Quadro P2200\n", "")
                return subprocess.CompletedProcess(
                    cmd, 1, "", "ModuleNotFoundError: No module named 'torch'\n")
            raise AssertionError(u"pergunta inesperada: %r" % (cmd,))
        return run
    import subprocess as sp
    with _Troca(sp, run=dublado(True)), \
            _Troca(M, _achar_nvidia_smi=lambda: "nvidia-smi"):
        inv = M._vram_por_placa()
    placas = inv.get("placas") or []
    checar(u"a linha ilegivel NAO vira «sem placa»: o recuo pelo torch acha "
           u"a P2200", len(placas) == 1 and placas[0].get("livre_mb") == 2048
           and inv.get("fonte") == "torch", str(inv)[:200])
    checar(u"  e o que levou ao recuo vai junto (a linha que nao se leu)",
           u"nenhuma linha se leu" in (inv.get("recuo") or u"")
           and u"[N/A]" in (inv.get("recuo") or u""), inv.get("recuo"))
    p = M.plano_de_dispositivo(PLANEJAMENTO[0], PLANEJAMENTO[1],
                               task="total_v3", inv=inv, partes=PARTES_V3)
    checar(u"  e o motivo do plano diz que a medida veio do torch, e por que",
           u"medida pelo torch" in p["motivo"]
           and u"nenhuma linha se leu" in p["motivo"], p["motivo"][:240])
    with _Troca(sp, run=dublado(False)), \
            _Troca(M, _achar_nvidia_smi=lambda: "nvidia-smi"):
        inv2 = M._vram_por_placa()
    checar(u"sem o torch tambem: e ERRO (nao consegui perguntar), e nao «nao "
           u"ha placa»", not inv2.get("placas")
           and u"nenhuma linha se leu" in (inv2.get("erro") or u"")
           and u"torch saiu com codigo 1" in (inv2.get("erro") or u""),
           inv2.get("erro"))
    p2 = M.plano_de_dispositivo(PLANEJAMENTO[0], PLANEJAMENTO[1],
                                task="total_v3", inv=inv2, partes=PARTES_V3)
    checar(u"  e o plano diz «nao consegui medir», e nao «nenhuma placa»",
           u"nao consegui medir a VRAM" in p2["motivo"]
           and u"nenhuma placa" not in p2["motivo"], p2["motivo"][:200])


def teste_a_causa_do_catalogo_nao_se_perde():
    secao(u"K · a causa do catalogo nao se perde")
    import radai_tasks as T

    class _Quebra(object):
        def get(self, *a, **k):
            raise KeyError(u"catalogo quebrado de proposito")

        def __contains__(self, k):
            raise KeyError(u"catalogo quebrado de proposito")
    with _Troca(T, POR_NOME=_Quebra(), Z_DO_MODELO=_Quebra()):
        ns, de_onde = M._classes_por_parte("tarefa_que_nao_existe_2099")
        av = []
        g = M._grade_do_modelo("tarefa_que_nao_existe_2099", avisos=av)
        p = M.plano_de_dispositivo(
            PLANEJAMENTO[0], PLANEJAMENTO[1], task="tarefa_que_nao_existe_2099",
            inv={"placas": [_placa(0, "Quadro P2200", 5120, 2048)], "erro": ""})
    checar(u"_classes_por_parte diz que o catalogo LEVANTOU (e o que)",
           ns == [120] and u"o catalogo levantou KeyError" in de_onde,
           de_onde)
    checar(u"_grade_do_modelo cai para 1,5 mm e DIZ por que",
           g == M.GRADE_BASE_MM and av
           and u"o catalogo levantou KeyError" in av[0], av)
    checar(u"  e as duas causas chegam ao motivo do plano",
           p["motivo"].count(u"o catalogo levantou KeyError") >= 2,
           p["motivo"][:300])


_TS_FALSO = {
    "totalsegmentator/__init__.py": u"",
    "totalsegmentator/bin/__init__.py": u"",
    "totalsegmentator/config.py": u'''
import os
def _registrar(t):
    with open(os.environ["FALSO_ENVIO"], "a") as f:
        f.write(t + "\\n")
def send_usage_stats(config, params):
    if config is not None and config["send_usage_stats"]:
        _registrar("ENVIOU task=%s" % params.get("task"))
def send_usage_stats_application(nome):
    _registrar("ENVIOU aplicacao=%s" % nome)
def setup_nnunet():
    pass
''',
    "totalsegmentator/python_api.py": u'''
from totalsegmentator.config import send_usage_stats
def totalsegmentator(task):
    send_usage_stats({"send_usage_stats": True, "totalseg_id": "x",
                      "prediction_counter": 1}, {"task": task})
''',
    "totalsegmentator/bin/TotalSegmentator.py": u'''
import sys
from totalsegmentator.python_api import totalsegmentator
def main():
    totalsegmentator(sys.argv[sys.argv.index("--task") + 1])
''',
}


def teste_o_envelope_nao_envia_estatistica():
    secao(u"K · o envelope nao envia a estatistica de uso")
    tmp = tempfile.mkdtemp(prefix="radai_teste_runner_")
    try:
        pkg = os.path.join(tmp, "pkg")
        for rel, txt in _TS_FALSO.items():
            cam = os.path.join(pkg, *rel.split("/"))
            if not os.path.isdir(os.path.dirname(cam)):
                os.makedirs(os.path.dirname(cam))
            with io.open(cam, "w", encoding="utf-8") as f:
                f.write(txt)
        cam = _harness(tmp, u'''
sys.path.insert(0, %r)
if len(sys.argv) > 1 and sys.argv[1] == "isca":
    R.remendar_estatistica = lambda modulos=None: []
R.principal(["-i", "x.nii.gz", "--task", "total_v3"])
''' % pkg)

        def rodar(*extra):
            envio = os.path.join(tmp, "envio_%d.txt" % len(os.listdir(tmp)))
            amb = dict(os.environ, FALSO_ENVIO=envio)
            amb.pop("nnUNet_results", None)
            r = subprocess.run([PY, cam] + list(extra), capture_output=True,
                               text=True, timeout=60, env=amb)
            try:
                with io.open(envio, encoding="utf-8") as f:
                    enviado = f.read()
            except OSError:
                enviado = u""
            return r, enviado
        r, enviado = rodar()
        checar(u"o main() do TotalSegmentator rodou pelo envelope (codigo 0)",
               r.returncode == 0 and "RADAI|fim|codigo=0" in r.stdout,
               (r.stdout + r.stderr)[-200:])
        checar(u"  e a funcao de envio NAO foi chamada (nada no registro)",
               u"ENVIOU" not in enviado, enviado[:120])
        checar(u"  e o envelope fica calado quando a troca da certo",
               u"remendo estatistica" not in r.stdout, r.stdout[-160:])
        r2, enviado2 = rodar("isca")
        checar(u"ISCA: sem o remendo, o MESMO main() envia",
               u"ENVIOU task=total_v3" in enviado2,
               (enviado2 or r2.stderr[-160:])[:160])
        m1 = types.SimpleNamespace(send_usage_stats=lambda *a: "rede",
                                   send_usage_stats_application=lambda *a: 1)
        m2 = types.SimpleNamespace(send_usage_stats=m1.send_usage_stats)
        with _Calado() as cal:
            feitos = R.remendar_estatistica([("totalsegmentator.config", m1),
                                             ("totalsegmentator.python_api",
                                              m2)])
        checar(u"a troca pega o nome importado em cada modulo (o python_api "
               u"importa pelo NOME)", m1.send_usage_stats(None, {}) is None
               and m2.send_usage_stats(None, {}) is None
               and len(feitos) == 3, str(feitos))
        with _Calado() as cal:
            nada = R.remendar_estatistica([("totalsegmentator.config",
                                            types.SimpleNamespace())])
        checar(u"  e sem a funcao (a biblioteca a renomeou) o aviso SAI",
               nada == [] and u"remendo estatistica" in cal.texto,
               cal.texto[:160])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    import importlib.util
    if importlib.util.find_spec("totalsegmentator") is None:
        return
    tmp = tempfile.mkdtemp(prefix="radai_teste_runner_")
    try:
        cam = _harness(tmp, u'''
import os
os.environ["TOTALSEG_HOME_DIR"] = sys.argv[1]
import requests
chamadas = []
requests.post = lambda *a, **k: chamadas.append(a[0] if a else k.get("url"))
import totalsegmentator.python_api as api
if sys.argv[2] == "remendo":
    R.remendar_estatistica()
api.send_usage_stats({"send_usage_stats": True, "totalseg_id": "t",
                      "prediction_counter": 1},
                     {"task": "total_v3", "fast": False, "preview": False,
                      "multilabel": True, "roi_subset": None,
                      "statistics": False, "radiomics": False})
print("POSTS=%d" % len(chamadas))
''')
        r = subprocess.run([PY, cam, tmp, "remendo"], capture_output=True,
                           text=True, timeout=300)
        checar(u"no bundle: com o remendo, o send_usage_stats DO python_api "
               u"nao posta nada", "POSTS=0" in r.stdout,
               (r.stdout + r.stderr)[-200:])
        r2 = subprocess.run([PY, cam, tmp, "isca"], capture_output=True,
                            text=True, timeout=300)
        checar(u"ISCA no bundle: sem o remendo, a funcao da biblioteca posta "
               u"(no requests dublado)", "POSTS=1" in r2.stdout,
               (r2.stdout + r2.stderr)[-200:])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def teste_o_arquivo_do_ts_diz_false():
    secao(u"K · o config.json do TotalSegmentator diz false")
    tmp = tempfile.mkdtemp(prefix="radai_teste_runner_")
    try:
        casa = os.path.join(tmp, "tshome")
        os.makedirs(casa)
        arq = os.path.join(casa, "config.json")
        original = {"totalseg_id": "totalseg_ABCD1234",
                    "send_usage_stats": True, "prediction_counter": 82,
                    "statistics_disclaimer_shown": True,
                    "license_number": "aca_FANTOMA"}

        def gravar(d):
            with io.open(arq, "w", encoding="utf-8") as f:
                json.dump(d, f, indent=4)

        def ler():
            with io.open(arq, encoding="utf-8") as f:
                return json.load(f)
        gravar(original)
        r = M.estatistica_do_ts(pasta=casa)
        checar(u"so ler NAO grava", r.get("valor") is True
               and not r.get("gravou") and ler()["send_usage_stats"] is True,
               str(r))
        r = M.estatistica_do_ts(desligar=True, pasta=casa)
        d = ler()
        checar(u"desligar grava false", r.get("gravou") and
               d.get("send_usage_stats") is False, str(r))
        checar(u"  e as outras chaves ficam (licenca, contador, id)",
               all(d.get(k) == v for k, v in original.items()
                   if k != "send_usage_stats"), str(d))
        t0 = os.path.getmtime(arq)
        time.sleep(0.05)
        r = M.estatistica_do_ts(desligar=True, pasta=casa)
        checar(u"  e com false ja escrito, nao regrava",
               not r.get("gravou") and os.path.getmtime(arq) == t0, str(r))
        casa2 = os.path.join(tmp, "tshome_nova")
        r = M.estatistica_do_ts(desligar=True, pasta=casa2)
        d2 = json.load(io.open(os.path.join(casa2, "config.json"),
                               encoding="utf-8"))
        checar(u"arquivo ausente e CRIADO com false (senao o TotalSegmentator "
               u"o criaria com true)", r.get("criou")
               and d2.get("send_usage_stats") is False
               and str(d2.get("totalseg_id", "")).startswith("totalseg_")
               and d2.get("prediction_counter") == 0, str(d2))
        casa3 = os.path.join(tmp, "tshome_quebrada")
        os.makedirs(casa3)
        with io.open(os.path.join(casa3, "config.json"), "w",
                     encoding="utf-8") as f:
            f.write(u'{"license_number": "aca_X", ')
        r = M.estatistica_do_ts(desligar=True, pasta=casa3)
        checar(u"JSON quebrado: nao sobrescreve, e DIZ por que",
               not r.get("gravou") and u"nao consegui ler" in r.get("erro", "")
               and io.open(os.path.join(casa3, "config.json"),
                           encoding="utf-8").read().startswith(u'{"license'),
               str(r))
        checar(u"a pasta sai de TOTALSEG_HOME_DIR, e sem ela de ~/.totalsegmentator",
               M.pasta_config_do_ts({"TOTALSEG_HOME_DIR": casa}) == casa
               and M.pasta_config_do_ts({}).endswith(".totalsegmentator"))
        gravar(original)
        falso = _runner_falso(tmp, u"gravar_saida()\n")
        velho_home = os.environ.get("TOTALSEG_HOME_DIR")
        os.environ["TOTALSEG_HOME_DIR"] = casa
        try:
            r1, log1, _, _ = _rodar_task(tmp, u"", TS_CMD=[PY, falso],
                                         RUNNER_TS=falso)
            checar(u"run_ts_task grava false antes do TotalSegmentator",
                   ler().get("send_usage_stats") is False
                   and ler().get("license_number") == "aca_FANTOMA",
                   str(ler()))
            checar(u"  e o log diz, uma linha, que desligou",
                   len([l for l in log1 if u"estatistica de uso do "
                        u"TotalSegmentator desligada" in l]) == 1,
                   u"\n".join(log1[:6]))
            gravar(original)
            r2, log2, _, _ = _rodar_task(
                tmp, u"", TS_CMD=[PY, falso], RUNNER_TS=falso,
                _desligar_estatistica_antes=lambda *a, **k: None)
            checar(u"ISCA: sem a gravacao, o arquivo fica em true",
                   ler().get("send_usage_stats") is True, str(ler()))
            r3, log3, _, _ = _rodar_task(tmp, u"gravar_saida()\n")
            checar(u"processo que nao e o TotalSegmentator nao mexe na "
                   u"configuracao dele", ler().get("send_usage_stats") is True
                   and not [l for l in log3 if u"estatistica" in l],
                   str(ler()))
        finally:
            if velho_home is None:
                os.environ.pop("TOTALSEG_HOME_DIR", None)
            else:
                os.environ["TOTALSEG_HOME_DIR"] = velho_home
    finally:
        _encerrar_os_meus()
        shutil.rmtree(tmp, ignore_errors=True)


def teste_o_recuo_diz_o_que_nao_conseguiu():
    secao(u"K · o recuo diz o que nao conseguiu")
    tmp = tempfile.mkdtemp(prefix="radai_teste_runner_")
    import builtins
    import pathlib
    real_open = builtins.open
    try:
        def open_cego(caminho, modo="r", *a, **k):
            if "rb" == modo and str(caminho).endswith(".log"):
                raise PermissionError(13, u"arquivo preso de proposito")
            return real_open(caminho, modo, *a, **k)
        M.open = open_cego
        try:
            r, log, reg, _ = _rodar_task(tmp, _PLACA_CAI, device="gpu",
                                         plano=_PLANO_GPU, timeout_s=60)
        finally:
            del M.open
        f = [l for l in log if u"para decidir o recuo" in l]
        checar(u"o log que nao abre na decisao do recuo e DITO",
               f and u"PermissionError" in f[0] and u"NAO refaz" in f[0],
               u"\n".join(log[-5:]))
        checar(u"  e, sem a prova, a serie cai (uma tentativa so)",
               isinstance(r, RuntimeError) and len(reg) == 1,
               u"%s | %d tentativa(s)" % (repr(r)[:80], len(reg)))
        grava_e_cai = (u'gravar_saida()\n'
                       u'if DEV == "gpu":\n'
                       u'    sys.stderr.write("RuntimeError: CUDA error: out '
                       u'of memory\\n")\n'
                       u'    sys.exit(1)\n')
        real_unlink = pathlib.Path.unlink

        def unlink_preso(self, *a, **k):
            if str(self).endswith("_ml.nii.gz"):
                raise PermissionError(13, u"preso de proposito")
            return real_unlink(self, *a, **k)
        with _Troca(pathlib.Path, unlink=unlink_preso):
            r2, log2, reg2, _ = _rodar_task(tmp, grava_e_cai, device="gpu",
                                            plano=_PLANO_GPU, timeout_s=60)
        g = [l for l in log2 if u"nao consegui apagar a saida" in l]
        checar(u"a saida da placa que nao se apaga e DITA",
               g and u"PermissionError" in g[0], u"\n".join(log2[-6:]))
        checar(u"  e a CPU refaz assim mesmo",
               [x.get("dev") for x in reg2 if "dev" in x] == ["gpu", "cpu"],
               str(reg2))
    finally:
        if hasattr(M, "open"):
            del M.open
        _encerrar_os_meus()
        shutil.rmtree(tmp, ignore_errors=True)


_GRAVA_E_FICA = u'''
neto = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(600)"])
registrar(neto=neto.pid)
gravar_saida()
linha("Saved in 0.10s")
time.sleep(600)
'''


def teste_a_saida_pronta_e_aproveitada():
    secao(u"A3 · a saida pronta e aproveitada, e o processo encerrado")
    tmp = tempfile.mkdtemp(prefix="radai_teste_runner_")
    try:
        r, log, reg, dt = _rodar_task(tmp, _GRAVA_E_FICA, timeout_s=60,
                                      SAIDA_PARADA_S=3)
        checar(u"a serie sai com as estruturas", isinstance(r, dict)
               and "parotid_gland_left" in r,
               repr(r)[:140] if not isinstance(r, dict) else str(sorted(r)))
        checar(u"  em ~limiar, e nao no tempo limite", dt < 25, u"%.1f s" % dt)
        frase = [l for l in log if "saida aproveitada" in l]
        checar(u"  e o log diz: a task terminou e o processo nao saiu",
               frase and "thread orfa do nnU-Net" in frase[0],
               frase[0] if frase else u"sem a frase")
        time.sleep(1.0)
        pids = [x.get("pid") for x in reg if x.get("pid")]
        netos = [x.get("neto") for x in reg if x.get("neto")]
        checar(u"  e o runner falso foi encerrado",
               pids and not any(_vivo(p) for p in pids), str(pids))
        checar(u"  e o NETO dele tambem (a arvore, e nao so o filho)",
               netos and not any(_vivo(p) for p in netos), str(netos))
        r2, log2, reg2, dt2 = _rodar_task(tmp, _GRAVA_E_FICA, timeout_s=10,
                                          SAIDA_PARADA_S=10 ** 6)
        checar(u"ISCA: sem o vigia da saida, a mesma serie morre no tempo "
               u"limite", isinstance(r2, RuntimeError)
               and "tempo limite" in str(r2), repr(r2)[:120])
    finally:
        _encerrar_os_meus()
        shutil.rmtree(tmp, ignore_errors=True)


def teste_a_saida_truncada_nao_e_aproveitada():
    secao(u"A3 · a saida truncada nao e aproveitada")
    tmp = tempfile.mkdtemp(prefix="radai_teste_runner_")
    corpo = u"gravar_saida(truncar=True)\ntime.sleep(600)\n"
    try:
        r, log, reg, dt = _rodar_task(tmp, corpo, timeout_s=10,
                                      SAIDA_PARADA_S=2)
        checar(u"a serie NAO sai com o arquivo pela metade (tempo limite)",
               isinstance(r, RuntimeError) and "tempo limite" in str(r),
               repr(r)[:120])
        ruins = [l for l in log if "NAO abre inteira" in l]
        checar(u"  e o log diz, UMA vez, que a saida nao abre inteira",
               len(ruins) == 1, u"%d vez(es)" % len(ruins))
        checar(u"  e nao diz que aproveitou",
               not [l for l in log if "saida aproveitada" in l])
        r2, log2, reg2, dt2 = _rodar_task(
            tmp, corpo, timeout_s=10, SAIDA_PARADA_S=2,
            _saida_inteira=lambda *a: (True, u"isca"))
        checar(u"ISCA: sem a prova, o arquivo pela metade seria aproveitado",
               [l for l in log2 if "saida aproveitada" in l],
               repr(r2)[:100])
        ok, porque = M._saida_inteira(os.path.join(tmp, "nao_existe.nii.gz"),
                                      _ref())
        checar(u"arquivo inexistente nao e «inteiro»", not ok, porque)
    finally:
        _encerrar_os_meus()
        shutil.rmtree(tmp, ignore_errors=True)


_PLACA_CAI = u'''
if DEV == "gpu":
    linha("Predicting part 2 of 5 ...")
    sys.stderr.write("RuntimeError: CUDA error: an illegal memory access "
                     "was encountered\\n")
    sys.exit(1)
gravar_saida()
'''

_PLANO_GPU = {"modo": "gpu_resultado_na_cpu", "motivo": u"gpu: dublado",
              "indice": 0, "capacidade": "6.1"}


def teste_a_placa_cai_e_a_cpu_refaz():
    secao(u"A3 · a placa cai e a CPU refaz")
    tmp = tempfile.mkdtemp(prefix="radai_teste_runner_")
    try:
        r, log, reg, dt = _rodar_task(tmp, _PLACA_CAI, device="gpu",
                                      plano=_PLANO_GPU, timeout_s=60)
        checar(u"a serie sai (a CPU refez)", isinstance(r, dict) and r,
               repr(r)[:140])
        devs = [x.get("dev") for x in reg if "dev" in x]
        checar(u"  duas tentativas: gpu e depois cpu", devs == ["gpu", "cpu"],
               str(devs))
        checar(u"  a primeira levou o resultado na RAM (o plano chegou ao "
               u"filho)", reg and reg[0].get("na_cpu") == "1"
               and reg[0].get("visiveis") == "0", str(reg[:1]))
        checar(u"  e a segunda NAO leva nada de placa",
               len(reg) > 1 and reg[1].get("na_cpu") == ""
               and reg[1].get("visiveis") == "-1", str(reg[1:2]))
        f = [l for l in log if "refazendo a task INTEIRA em CPU" in l]
        checar(u"  e o log diz em que parte a placa caiu, e por que refaz",
               f and "parte 2/5" in f[0] and "CUDA error" in f[0]
               and "nao ha como retomar do meio" in f[0],
               f[0] if f else u"sem a frase")
        r2, log2, reg2, _ = _rodar_task(tmp, _PLACA_CAI, device="gpu",
                                        plano=_PLANO_GPU, timeout_s=60,
                                        _erro_de_placa=lambda t: None)
        checar(u"ISCA: sem reconhecer o erro de placa, a serie cai",
               isinstance(r2, RuntimeError) and "codigo 1" in str(r2),
               repr(r2)[:120])
        outro = u'sys.stderr.write("ValueError: serie ruim\\n")\nsys.exit(1)\n'
        r3, log3, reg3, _ = _rodar_task(tmp, outro, device="gpu",
                                        plano=_PLANO_GPU, timeout_s=60)
        checar(u"erro que nao e de placa NAO refaz em CPU (uma tentativa)",
               isinstance(r3, RuntimeError) and len(reg3) == 1,
               u"%d tentativa(s)" % len(reg3))
        r4, log4, reg4, _ = _rodar_task(tmp, _PLACA_CAI.replace(
            'if DEV == "gpu":', "if True:"), device="gpu", plano=_PLANO_GPU,
            timeout_s=60)
        checar(u"falhou de novo em CPU: levanta como sempre (so UMA refeita)",
               isinstance(r4, RuntimeError) and len(reg4) == 2,
               u"%d tentativa(s)" % len(reg4))
        checar(u"a lista de erros de placa pega o TDR e o driver reiniciado",
               M._erro_de_placa(u"CUDA error: the launch timed out and was "
                                u"terminated")
               and M._erro_de_placa(u"the NVIDIA driver has been reset")
               and not M._erro_de_placa(u"Moving results arrays to CPU"))
    finally:
        _encerrar_os_meus()
        shutil.rmtree(tmp, ignore_errors=True)


_DUAS_PARTES = u'''
linha("Predicting part 1 of 5 ...")
linha("RADAI|rede|dataset=831|ordem=1|device=cuda:0|resultados=ram")
linha("RADAI|pulso|parte=?|dataset=831|vram_mb=3174/5120|rss_mb=2048")
time.sleep(3)
linha("Predicting part 2 of 5 ...")
linha("RADAI|rede|dataset=832|ordem=2|device=cuda:0|resultados=ram")
linha("RADAI|pulso|parte=?|dataset=832|vram_mb=3200/5120|rss_mb=2100")
time.sleep(3)
gravar_saida()
'''


def teste_o_batimento_diz_a_parte_e_a_memoria():
    secao(u"A3 · o batimento diz a parte, o modo e a memoria")
    tmp = tempfile.mkdtemp(prefix="radai_teste_runner_")
    mapa = {"total_v3": {1: "liver", 2: "spleen"}}
    eleita = {"CT": "total_v3", "MR": "total_mr"}
    try:
        r, log, reg, dt = _rodar_task(tmp, _DUAS_PARTES, task="total_v3",
                                      device="gpu", plano=_PLANO_GPU,
                                      mapa=mapa, eleita=eleita, timeout_s=60)
        checar(u"a serie sai", isinstance(r, dict) and "liver" in r,
               repr(r)[:120])
        p2 = [l for l in log if "parte 2/5 (vertebras)" in l]
        checar(u"a linha diz a parte e o NOME dela", p2, u"\n".join(log[-8:]))
        checar(u"  e o modo, a VRAM e a RAM",
               p2 and "gpu-resultado-na-cpu" in p2[0]
               and "VRAM 3,1/5,0 GiB" in p2[0] and "RAM livre" in p2[0],
               p2[0] if p2 else "")
        checar(u"  e ha quanto tempo algo mudou",
               p2 and "ultimo sinal ha" in p2[0], p2[0] if p2 else "")
        checar(u"a rede carregada vira linha de log (qual dataset, onde)",
               [l for l in log if "rede carregada: dataset 832 em cuda:0"
                in l], u"")
        checar(u"a linha de MUDANCA nao leva «still working» (o filtro do "
               u"drenador nao a segura)",
               p2 and "still working" not in p2[0])
        checar(u"o plano chegou ao filho (RADAI_RESULTADOS_NA_CPU=1)",
               reg and reg[0].get("na_cpu") == "1", str(reg[:1]))
        checar(u"o log diz o dispositivo com o motivo, SEMPRE",
               [l for l in log if "dispositivo: gpu: dublado" in l])
        with _Troca(M._LeitorDoLogTS, _PARTE=re.compile("nunca-casa")):
            r2, log2, _, _ = _rodar_task(tmp, _DUAS_PARTES, task="total_v3",
                                         device="gpu", plano=_PLANO_GPU,
                                         mapa=mapa, eleita=eleita,
                                         timeout_s=60)
        checar(u"ISCA: sem ler «Predicting part», a linha nao tem a parte",
               not [l for l in log2 if "parte 2/5" in l])
        checar(u"a batida periodica passa o filtro do drenador sempre",
               M.BATIMENTO_TS_S > M.PROGRESSO_A_CADA_S + 3,
               u"%s contra %s" % (M.BATIMENTO_TS_S, M.PROGRESSO_A_CADA_S))
    finally:
        _encerrar_os_meus()
        shutil.rmtree(tmp, ignore_errors=True)


_PULSO_COLADO = u'''
linha("Predicting part 1 of 5 ...")
linha("RADAI|rede|dataset=831|ordem=1|device=cuda:0|resultados=ram")
sys.stderr.write("\\r 25%|##   | 1/4 [00:06<00:19,  6.53s/it]")
sys.stderr.flush()
linha("RADAI|pulso|parte=?|dataset=831|vram_mb=3174/5120|rss_mb=2076")
time.sleep(3)
linha("Predicting part 2 of 5 ...")
time.sleep(3)
gravar_saida()
'''


def teste_o_pulso_colado_na_barra_e_lido():
    secao(u"A3 · o pulso colado na barra do tqdm e lido")
    tmp = tempfile.mkdtemp(prefix="radai_teste_runner_")
    try:
        cam = os.path.join(tmp, "ts.log")
        with io.open(cam, "w", encoding="utf-8", newline="") as f:
            f.write(u"Predicting part 1 of 5 ...\n"
                    u"  0%|          | 0/4 [00:00<?, ?it/s]\r"
                    u" 25%|██▌       | 1/4 [00:06<00:19,  "
                    u"6.53s/it]RADAI|pulso|parte=?|dataset=831|"
                    u"vram_mb=3174/5120|rss_mb=2076\n"
                    u" 50%|#####     | 2/4 [00:13<00:13,  6.70s/it]"
                    u"RADAI|fim|codigo=0\n")
        L = M._LeitorDoLogTS(cam, agora=0)
        L.ler(agora=1)
        checar(u"o pulso grudado e lido como pulso (VRAM e memoria)",
               L.pulso.get("vram_mb") == "3174/5120"
               and L.pulso.get("rss_mb") == "2076", str(L.pulso))
        checar(u"  e o dataset dele tambem", L.dataset == "831",
               str(L.dataset))
        checar(u"  e o `RADAI|fim` grudado tambem", L.fim == 0, str(L.fim))
        checar(u"  e a parte, que vem numa linha limpa, continua",
               L.parte == (1, 5), str(L.parte))
        mapa = {"total_v3": {1: "liver", 2: "spleen"}}
        eleita = {"CT": "total_v3", "MR": "total_mr"}
        r, log, _, _ = _rodar_task(tmp, _PULSO_COLADO, task="total_v3",
                                   device="gpu", plano=_PLANO_GPU, mapa=mapa,
                                   eleita=eleita, timeout_s=60)
        p2 = [l for l in log if u"parte 2/5" in l and u"TS total_v3 |" in l]
        checar(u"a batida da parte 2 leva a VRAM e o processo do pulso "
               u"grudado", p2 and u"VRAM 3,1/5,0 GiB" in p2[0]
               and u"processo 2,0 GiB" in p2[0], p2[0] if p2 else u"sem")
    finally:
        _encerrar_os_meus()
        shutil.rmtree(tmp, ignore_errors=True)


def teste_o_silencio_avisa_e_nao_mata():
    secao(u"A3 · o silencio avisa e nao mata")
    tmp = tempfile.mkdtemp(prefix="radai_teste_runner_")
    corpo = u"time.sleep(6)\ngravar_saida()\n"
    try:
        r, log, _, _ = _rodar_task(tmp, corpo, timeout_s=60,
                                   SILENCIO_AVISO_S=2)
        checar(u"a serie sai depois do silencio", isinstance(r, dict) and r,
               repr(r)[:100])
        av = [l for l in log if "sem sinal ha" in l]
        checar(u"  e o aviso saiu, dizendo que NAO encerra",
               av and "NAO encerro" in av[0], av[0] if av else u"sem aviso")
        r2, log2, _, _ = _rodar_task(tmp, corpo, timeout_s=60,
                                     SILENCIO_AVISO_S=10 ** 6)
        checar(u"ISCA: com o limiar no infinito o aviso nao sai",
               not [l for l in log2 if "sem sinal ha" in l])
    finally:
        _encerrar_os_meus()
        shutil.rmtree(tmp, ignore_errors=True)


def teste_o_fim_do_log_nao_e_so_pulso():
    secao(u"A3 · o fim do log e o motivo, e nao o pulso")
    tmp = tempfile.mkdtemp(prefix="radai_teste_runner_")
    try:
        cam = os.path.join(tmp, "ts.log")
        with io.open(cam, "w", encoding="utf-8") as f:
            f.write(u"Predicting part 3 of 5 ...\n")
            f.write(u"RuntimeError: CUDA error: unspecified launch failure\n")
            f.write(u"  3%|#  | 1/30 [00:10<04:50]\r")
            for i in range(40):
                f.write(u"RADAI|pulso|parte=?|dataset=833|rss_mb=%d\n"
                        % (4000 + i))
        t = M._tail_arquivo(cam)
        checar(u"o traceback esta no fim que vai para a mensagem",
               "CUDA error: unspecified launch failure" in t, t[-120:])
        checar(u"  e nenhum pulso", "RADAI|pulso|" not in t, t[-120:])

        def antiga(c, n=800):
            with open(c, "rb") as f:
                f.seek(0, 2)
                f.seek(max(0, f.tell() - n))
                return f.read().decode("utf-8", "replace").strip()
        checar(u"ISCA: a leitura antiga perde o traceback no meio dos pulsos",
               "CUDA error" not in antiga(cam))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def teste_o_encerramento_que_falha_e_dito():
    secao(u"A3 · o encerramento que falha e dito")
    if os.name != "nt":
        return
    real = subprocess.run

    def taskkill_com(codigo, texto=u""):
        def run(cmd, *a, **k):
            if cmd and "taskkill" in str(cmd[0]).lower():
                return subprocess.CompletedProcess(
                    cmd, codigo, b"", texto.encode("cp850"))
            return real(cmd, *a, **k)
        return run

    def dorminhoco():
        p = subprocess.Popen([PY, "-c", "import time; time.sleep(120)"])
        _MEUS_PIDS.add(p.pid)
        return p
    tmp = tempfile.mkdtemp(prefix="radai_teste_runner_")
    try:
        proc = dorminhoco()
        with _Troca(subprocess, run=taskkill_com(1, u"ERRO: acesso negado.")):
            p = M._encerrar_arvore(proc)
        checar(u"taskkill com codigo 1: a funcao devolve o motivo e o codigo",
               p and u"codigo 1" in p and u"acesso negado" in p, repr(p))
        checar(u"  e o filho cai assim mesmo (proc.kill)",
               proc.poll() is not None, str(proc.poll()))
        proc = dorminhoco()
        with _Troca(subprocess, run=taskkill_com(
                128, u'ERRO: o processo "1" não foi encontrado.')):
            p = M._encerrar_arvore(proc)
        checar(u"taskkill com 128 (o processo ja tinha saido) nao e problema",
               p is None, repr(p))
        proc = dorminhoco()
        p = M._encerrar_arvore(proc)
        checar(u"de verdade, sem dublagem: a arvore cai e nada a dizer",
               p is None and proc.poll() is not None, repr(p))
        checar(u"processo que ja saiu: nada a encerrar, nada a dizer",
               M._encerrar_arvore(proc) is None)

        def cai_mas_diz(pr):
            pr.kill()
            pr.wait(30)
            return u"taskkill /T saiu com codigo 1 (dublado)"
        r, log, reg, _ = _rodar_task(tmp, _GRAVA_E_FICA, timeout_s=60,
                                     SAIDA_PARADA_S=3,
                                     _encerrar_arvore=cai_mas_diz)
        _encerrar_os_meus()
        checar(u"o motor escreve no log o que falhou ao encerrar",
               [l for l in log if u"ao encerrar o processo" in l
                and u"codigo 1" in l], u"\n".join(log[-5:]))
        checar(u"  e a serie sai assim mesmo (a saida era inteira)",
               isinstance(r, dict) and r, repr(r)[:100])

        def cai_calado(pr):
            pr.kill()
            pr.wait(30)
            return None
        r2, log2, _, _ = _rodar_task(tmp, _GRAVA_E_FICA, timeout_s=60,
                                     SAIDA_PARADA_S=3,
                                     _encerrar_arvore=cai_calado)
        checar(u"ISCA: com o encerramento calado, a linha nao sai",
               not [l for l in log2 if u"ao encerrar o processo" in l])
    finally:
        _encerrar_os_meus()
        shutil.rmtree(tmp, ignore_errors=True)


def teste_a_leitura_do_log_que_falha_e_dita():
    secao(u"A3 · a leitura do log que falha e dita")
    tmp = tempfile.mkdtemp(prefix="radai_teste_runner_")
    try:
        cam = os.path.join(tmp, "ts.log")
        L = M._LeitorDoLogTS(cam, agora=0)
        for t in (1, 2, 3):
            L.ler(agora=t)
        ev = [e for e in L.eventos if u"nao consegui ler o log" in e]
        checar(u"a falha de leitura e dita UMA vez, em tres voltas",
               len(ev) == 1 and L.erro, u"%d vez(es) | %s" % (len(ev), L.erro))
        with io.open(cam, "w", encoding="utf-8") as f:
            f.write(u"Predicting part 1 of 5 ...\n")
        L.ler(agora=4)
        checar(u"  e a volta tambem, e a leitura segue de onde estava",
               [e for e in L.eventos if u"voltou" in e] and L.erro is None
               and L.parte == (1, 5), u"%s %s" % (L.erro, L.parte))
        def _sequencia(classe):
            cam2 = os.path.join(tmp, "rearma_%s.log" % classe.__name__)
            L2 = classe(cam2, agora=0)
            L2.ler(agora=1)
            with io.open(cam2, "w", encoding="utf-8") as f:
                f.write(u"Predicting part 1 of 5 ...\n")
            L2.ler(agora=2)
            os.remove(cam2)
            L2.ler(agora=3)
            return [e for e in L2.eventos if u"nao consegui ler o log" in e]
        duas = _sequencia(M._LeitorDoLogTS)
        checar(u"falha -> volta -> falha: as DUAS falhas sao ditas",
               len(duas) == 2, u"%d vez(es)" % len(duas))

        class _NaoRearma(M._LeitorDoLogTS):

            def ler(self, agora=None):
                ja = self._disse_erro
                M._LeitorDoLogTS.ler(self, agora)
                self._disse_erro = self._disse_erro or ja
        checar(u"ISCA: um leitor que nao rearma cala a segunda falha",
               len(_sequencia(_NaoRearma)) == 1)
        cego = os.path.join(tmp, "nunca_existe.log")
        Base = M._LeitorDoLogTS

        class LeitorCego(Base):
            def __init__(self, caminho, *a, **k):
                Base.__init__(self, cego, *a, **k)
        corpo = u"time.sleep(6)\ngravar_saida()\n"
        r, log, _, _ = _rodar_task(tmp, corpo, timeout_s=60,
                                   SILENCIO_AVISO_S=2,
                                   _LeitorDoLogTS=LeitorCego)
        checar(u"a serie sai (a leitura e diagnostico, nao decide nada)",
               isinstance(r, dict) and r, repr(r)[:100])
        checar(u"  o log diz, uma vez, que nao le o log do TotalSegmentator",
               len([l for l in log if u"nao consegui ler o log" in l]) == 1,
               u"\n".join(log[-6:]))
        av = [l for l in log if u"sem sinal ha" in l]
        checar(u"  e o aviso de silencio aponta a LEITURA",
               av and u"a LEITURA do log esta falhando" in av[0],
               av[0] if av else u"sem aviso")
        r2, log2, _, _ = _rodar_task(tmp, corpo, timeout_s=60,
                                     SILENCIO_AVISO_S=2)
        av2 = [l for l in log2 if u"sem sinal ha" in l]
        checar(u"ISCA: lendo de verdade, o mesmo silencio NAO fala da leitura",
               av2 and u"LEITURA" not in av2[0], av2[0] if av2 else u"")
    finally:
        _encerrar_os_meus()
        shutil.rmtree(tmp, ignore_errors=True)


_PARTE_2_ANTES_DA_REDE = u'''
linha("Predicting part 1 of 5 ...")
linha("RADAI|rede|dataset=831|ordem=1|device=cuda:0|resultados=ram")
time.sleep(3)
linha("Predicting part 2 of 5 ...")
time.sleep(3)
if DEV == "gpu":
    sys.stderr.write("RuntimeError: CUDA error: out of memory\\n")
    sys.exit(1)
gravar_saida()
'''


def teste_o_nome_da_parte_segue_o_indice():
    secao(u"A3 · o nome da parte segue o indice")
    checar(u"parte 2/5 com o dataset ainda da 1 (831): vertebras",
           M._nome_da_parte("total_v3", (2, 5), "831") == u"vertebras",
           str(M._nome_da_parte("total_v3", (2, 5), "831")))
    checar(u"parte 3/5 sem dataset: cardiaco",
           M._nome_da_parte("total_v3", (3, 5)) == u"cardiaco")
    checar(u"sem indice, o dataset manda: 834 -> musculos",
           M._nome_da_parte("total_v3", None, "834") == u"musculos")
    checar(u"task sem lista no catalogo (a `total` v2): o dataset",
           M._nome_da_parte("total", (2, 5), "292") == u"vertebras",
           str(M._nome_da_parte("total", (2, 5), "292")))
    tmp = tempfile.mkdtemp(prefix="radai_teste_runner_")
    mapa = {"total_v3": {1: "liver", 2: "spleen"}}
    eleita = {"CT": "total_v3", "MR": "total_mr"}
    try:
        r, log, _, _ = _rodar_task(tmp, _PARTE_2_ANTES_DA_REDE,
                                   task="total_v3", device="gpu",
                                   plano=_PLANO_GPU, mapa=mapa, eleita=eleita,
                                   timeout_s=60)
        f = [l for l in log if u"refazendo a task INTEIRA em CPU" in l]
        checar(u"a frase do recuo nomeia a parte certa (vertebras), e nao a "
               u"rede que ainda estava carregada",
               f and u"parte 2/5 (vertebras)" in f[0] and u"orgaos" not in f[0],
               f[0] if f else u"sem a frase")
        b = [l for l in log if u"parte 2/5" in l and u"TS total_v3 |" in l]
        checar(u"  e o batimento tambem", b and u"(vertebras)" in b[0],
               b[0] if b else u"sem batimento da parte 2")

        def antiga(task, parte, dataset=None):
            if dataset:
                return M.NOME_DA_PARTE.get(int(dataset))
            return None
        r2, log2, _, _ = _rodar_task(tmp, _PARTE_2_ANTES_DA_REDE,
                                     task="total_v3", device="gpu",
                                     plano=_PLANO_GPU, mapa=mapa,
                                     eleita=eleita, timeout_s=60,
                                     _nome_da_parte=antiga)
        f2 = [l for l in log2 if u"refazendo a task INTEIRA em CPU" in l]
        checar(u"ISCA: com o dataset primeiro, o recuo diria «orgaos»",
               f2 and u"parte 2/5 (orgaos)" in f2[0],
               f2[0] if f2 else u"sem a frase")
    finally:
        _encerrar_os_meus()
        shutil.rmtree(tmp, ignore_errors=True)


_LENTA_S = 9
_FOLGA_S = 8
_LENTA_NAS_DUAS = u'''
time.sleep(%d)
if DEV == "gpu":''' % _LENTA_S + u'''
    sys.stderr.write("RuntimeError: CUDA error: an illegal memory access "
                     "was encountered\\n")
    sys.exit(1)
gravar_saida()
'''


def teste_a_refeita_tem_o_tempo_inteiro():
    secao(u"A3 · a refeita em CPU tem o tempo limite inteiro")
    tmp = tempfile.mkdtemp(prefix="radai_teste_runner_")
    limite = _LENTA_S + _FOLGA_S
    try:
        r, log, reg, dt = _rodar_task(tmp, _LENTA_NAS_DUAS, device="gpu",
                                      plano=_PLANO_GPU, timeout_s=limite)
        checar(u"as duas tentativas somam mais que o tempo limite, e a serie "
               u"sai", isinstance(r, dict) and r and dt > limite,
               u"%.1f s contra %d | %s" % (dt, limite, repr(r)[:80]))
        f = [l for l in log if u"refazendo a task INTEIRA em CPU" in l]
        checar(u"  e a frase do recuo diz quanto a placa gastou e que a "
               u"refeita tem o tempo inteiro",
               f and u"A tentativa na placa durou" in f[0]
               and (u"tempo limite inteiro de novo (%d s)" % limite) in f[0],
               f[0] if f else u"sem a frase")
    finally:
        _encerrar_os_meus()
        shutil.rmtree(tmp, ignore_errors=True)


def teste_sem_o_envelope_o_ts_roda_direto_e_diz():
    secao(u"A3 · sem o envelope, o recuo dito")
    tmp = tempfile.mkdtemp(prefix="radai_teste_runner_")
    try:
        falso = _runner_falso(tmp, u"gravar_saida()\n")
        some = os.path.join(tmp, "radai_ts_runner.py")
        r, log, _, _ = _rodar_task(
            tmp, u"", timeout_s=60, TS_CMD=[PY, some], RUNNER_TS=some,
            TS_CMD_DIRETO=[PY, falso])
        checar(u"a serie sai pelo TotalSegmentator direto",
               isinstance(r, dict) and r, repr(r)[:120])
        checar(u"  e o log diz que o envelope nao esta la",
               [l for l in log if "envelope radai_ts_runner.py nao esta" in l])
        checar(u"no pacote de verdade o envelope esta ao lado do motor",
               os.path.isfile(M.RUNNER_TS) and M.TS_CMD[1] == M.RUNNER_TS,
               M.RUNNER_TS)
        checar(u"  e o caminho sai de __file__, nao e absoluto no fonte",
               "radai_ts_runner.py" in io.open(M.__file__, encoding="utf-8")
               .read() and os.path.dirname(M.RUNNER_TS)
               == os.path.dirname(os.path.abspath(M.__file__)))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def teste_a_rm_nao_vira_base_de_tc():
    secao(u"A4 · a base da RM nao vira a de TC")
    tmp = tempfile.mkdtemp(prefix="radai_teste_runner_")
    eleita = {"CT": "total_v3", "MR": "total_mr"}
    corpo = u"sys.exit(1)\n"
    try:
        r, log, reg, _ = _rodar_task(tmp, corpo, task="total_mr",
                                     eleita=eleita, timeout_s=30)
        checar(u"`total_mr` chega ao TotalSegmentator como total_mr",
               reg and reg[0].get("task") == "total_mr", str(reg[:1]))
        r, log, reg, _ = _rodar_task(tmp, corpo, task="total", eleita=eleita,
                                     timeout_s=30)
        checar(u"o apelido `total` e de TC, e vira a base de TC",
               reg and reg[0].get("task") == "total_v3", str(reg[:1]))
        checar(u"_task_que_roda nao toca task que nao e base",
               M._task_que_roda("head_glands_cavities") ==
               "head_glands_cavities")

        def antiga(task, log=None):
            if task in M._bases_preferidas():
                return M.base_eleita("CT", log=log)
            return task
        r, log, reg, _ = _rodar_task(tmp, corpo, task="total_mr",
                                     eleita=eleita, timeout_s=30,
                                     _task_que_roda=antiga)
        checar(u"ISCA: com a eleicao antiga a RM roda a base de TC",
               reg and reg[0].get("task") == "total_v3", str(reg[:1]))
        import radai_tasks as T

        def quebra(*a, **k):
            raise RuntimeError(u"dublado")
        avisos = []
        with _Troca(T, modalidade_da_base=quebra), \
                _Troca(M, base_eleita=lambda modalidade="CT", **k:
                       eleita.get(str(modalidade).upper())):
            t_mr = M._task_que_roda("total_mr", log=avisos.append)
            t_ct = M._task_que_roda("total_v3", log=avisos.append)
        checar(u"sem radai_tasks a modalidade sai do nome, e a RM continua RM",
               t_mr == "total_mr" and t_ct == "total_v3",
               u"%s %s" % (t_mr, t_ct))
        checar(u"  e o log diz que foi DEDUZIDA, e por que",
               [a for a in avisos if u"deduzida pelo nome: MR" in a
                and u"RuntimeError" in a], u" | ".join(avisos)[:200])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def teste_o_teto_de_threads_vem_antes_do_nnunet():
    secao(u"D · o teto de threads vem antes do nnU-Net")
    _cfg_velho = sys.modules.pop("nnunetv2.configuration", None)
    try:
        _teto_unidade()
    finally:
        if _cfg_velho is not None:
            sys.modules["nnunetv2.configuration"] = _cfg_velho
    _teto_ordem_e_bundle()


def _teto_unidade():
    amb = {"RADAI_THREADS": "12"}
    with _Calado() as cal:
        n = R._teto_de_threads(amb)
    checar(u"RADAI_THREADS=12 escreve nnUNet_def_n_proc=12",
           n == 12 and amb.get("nnUNet_def_n_proc") == "12", str(amb))
    checar(u"  e se anuncia (RADAI|remendo|threads=12)",
           "RADAI|remendo|threads=12" in cal.texto, cal.texto)
    for ruim in ("0", "-3", "doze", "1.5"):
        amb = {"RADAI_THREADS": ruim}
        with _Calado() as cal:
            n = R._teto_de_threads(amb)
        checar(u"RADAI_THREADS=%r nao vira teto, e e dito" % ruim,
               n is None and "nnUNet_def_n_proc" not in amb
               and "aviso|RADAI_THREADS" in cal.texto, cal.texto[:120])
    amb = {}
    with _Calado() as cal:
        n = R._teto_de_threads(amb)
    checar(u"sem a variavel e sem saber o dispositivo: nada muda (o 8 da "
           u"biblioteca)", n is None and not amb and not cal.texto, cal.texto)
    import radai_devices as RDV
    esperado = RDV.regra_de_threads()["n"]
    for argv in (["-i", "a", "-o", "b", "--device", "cpu"], ["-d", "cpu"],
                 ["--device=cpu"]):
        amb = {}
        with _Calado() as cal:
            n = R._teto_de_threads(amb, argv=argv)
        checar(u"%s sem a variavel: o teto e o da regra de radai_devices (%s)"
               % (" ".join(argv[-2:]), esperado),
               n == esperado
               and amb.get("nnUNet_def_n_proc") == (str(esperado) if esperado else None)
               and "origem=regra de radai_devices" in cal.texto
               if esperado else
               n is None and "threads=biblioteca" in cal.texto, cal.texto)
    velha_topo = RDV.topologia_da_cpu
    try:
        for topo, n_esp in (({"fisicos": 6, "logicos": 12}, None),
                            ({"fisicos": 16, "logicos": 32}, 12),
                            ({"fisicos": 10, "logicos": 10}, 10)):
            RDV.topologia_da_cpu = (lambda t=topo: dict(t))
            amb = {}
            with _Calado() as cal:
                n = R._teto_de_threads(amb, argv=["--device", "cpu"])
            checar(u"topologia %s/%s: o envelope da %s, como radai_devices"
                   % (topo["fisicos"], topo["logicos"], n_esp or u"o 8"),
                   n == n_esp and n == RDV.regra_de_threads()["n"]
                   and (("nnUNet_def_n_proc" not in amb
                         and "threads=biblioteca" in cal.texto) if n_esp is None
                        else amb.get("nnUNet_def_n_proc") == str(n_esp)),
                   str((n, amb, cal.texto[:160])))
        RDV.topologia_da_cpu = lambda: {"fisicos": 6, "logicos": 12}
        amb = {}
        with _Calado():
            n = R._teto_de_threads(amb, argv=["--device", "cpu"])
        checar(u"ISCA: SMT simetrico 6C/12T nao sobe para os 12 logicos "
               u"(a regra antiga, os.cpu_count(), subiria)",
               n is None and "nnUNet_def_n_proc" not in amb, str((n, amb)))
    finally:
        RDV.topologia_da_cpu = velha_topo
    amb = {"nnUNet_def_n_proc": "5"}
    with _Calado() as cal:
        n = R._teto_de_threads(amb, argv=["--device", "cpu"])
    checar(u"nnUNet_def_n_proc ja no ambiente: o padrao nao passa por cima, e diz",
           n is None and amb["nnUNet_def_n_proc"] == "5"
           and "ja estava no ambiente" in cal.texto, cal.texto)
    import ast
    fonte = io.open(_componentes.fonte("app/radai_ts_runner.py"),
                    encoding="utf-8").read()
    fn = next(n for n in ast.walk(ast.parse(fonte))
              if isinstance(n, ast.FunctionDef) and n.name == "_teto_de_threads")
    conta = [n for n in ast.walk(fn) if isinstance(n, ast.Attribute)
             and n.attr in ("cpu_count", "sched_getaffinity")]
    checar(u"_teto_de_threads nao conta nucleo por conta propria (uma regra so)",
           not conta, [getattr(c, "lineno", 0) for c in conta])
    for argv in (["--device", "gpu"], ["-d", "gpu:0"], []):
        amb = {}
        with _Calado():
            n = R._teto_de_threads(amb, argv=argv)
        checar(u"ISCA: %r (placa, ou sem dizer) NAO muda o teto" % argv,
               n is None and not amb)
    amb = {"RADAI_THREADS": "8"}
    with _Calado() as cal:
        n = R._teto_de_threads(amb, argv=["--device", "cpu"])
    checar(u"RADAI_THREADS escrito manda, mesmo em CPU (volta ao 8)",
           n == 8 and "origem=RADAI_THREADS" in cal.texto, cal.texto)
    ja = "nnunetv2.configuration" in sys.modules
    if not ja:
        sys.modules["nnunetv2.configuration"] = types.ModuleType("x")
    try:
        amb = {"RADAI_THREADS": "12"}
        with _Calado() as cal:
            n = R._teto_de_threads(amb)
        checar(u"ISCA: com o nnU-Net ja importado, o teto NAO e fingido",
               n is None and "chegou depois" in cal.texto, cal.texto[:140])
    finally:
        if not ja:
            sys.modules.pop("nnunetv2.configuration", None)


def _regra_pelo_caminho():
    import json as _json
    import radai_devices as RDV
    tmp = tempfile.mkdtemp(prefix="radai_teste_runner_")
    try:
        roteiro = os.path.join(tmp, "carrega_pelo_caminho.py")
        with io.open(roteiro, "w", encoding="utf-8") as f:
            f.write(u'''# -*- coding: utf-8 -*-
import importlib.util, json, os, sys
alvo = sys.argv[1]
pasta = os.path.dirname(alvo)
sys.path[:] = [p for p in sys.path
               if os.path.normcase(os.path.abspath(p or ".")) != os.path.normcase(pasta)]
spec = importlib.util.spec_from_file_location("radai_ts_runner", alvo)
R = importlib.util.module_from_spec(spec)
spec.loader.exec_module(R)
n, motivo = R._regra_de_threads()
print("REGRA=" + json.dumps({"n": n, "motivo": motivo,
                             "app_no_path": any(os.path.normcase(os.path.abspath(p or ".")) == os.path.normcase(pasta) for p in sys.path),
                             "devices_no_sys_modules": "radai_devices" in sys.modules}))
''')
        def rodar(alvo):
            r = subprocess.run([PY, roteiro, alvo], capture_output=True, text=True,
                               timeout=120, cwd=tmp)
            linha = [l for l in r.stdout.splitlines() if l.startswith("REGRA=")]
            return (_json.loads(linha[0][6:]) if linha else
                    {"erro": (r.stdout + r.stderr)[-300:]})
        d = rodar(_componentes.fonte("app/radai_ts_runner.py"))
        esperado = RDV.regra_de_threads()["n"]
        checar(u"sem app/ no sys.path, o envelope acha a regra PELO CAMINHO (%s)"
               % esperado,
               "erro" not in d and not d.get("app_no_path")
               and not d.get("devices_no_sys_modules") and d.get("n") == esperado
               and "nao carregou" not in (d.get("motivo") or ""), d)
        copia = os.path.join(tmp, "sozinho")
        os.makedirs(copia)
        shutil.copy2(_componentes.fonte("app/radai_ts_runner.py"), copia)
        d2 = rodar(os.path.join(copia, "radai_ts_runner.py"))
        checar(u"ISCA: sem radai_devices.py ao lado, fica o 8 da biblioteca, e dito",
               "erro" not in d2 and d2.get("n") is None
               and "nao carregou" in (d2.get("motivo") or ""), d2)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _teto_ordem_e_bundle():
    import ast
    fonte = io.open(_componentes.fonte("app/radai_ts_runner.py"),
                    encoding="utf-8").read()
    fn = next(n for n in ast.walk(ast.parse(fonte))
              if isinstance(n, ast.FunctionDef) and n.name == "principal")
    linha_teto = min((n.lineno for n in ast.walk(fn) if isinstance(n, ast.Call)
                      and getattr(n.func, "id", "") == "_teto_de_threads"),
                     default=None)
    linha_ts = min((n.lineno for n in ast.walk(fn)
                    if isinstance(n, ast.ImportFrom)
                    and (n.module or "").startswith("totalsegmentator")),
                   default=None)
    checar(u"em `principal`, _teto_de_threads vem ANTES do import do TS",
           linha_teto and linha_ts and linha_teto < linha_ts,
           "%s < %s" % (linha_teto, linha_ts))
    _regra_pelo_caminho()
    try:
        import nnunetv2
    except ImportError:
        return
    tmp = tempfile.mkdtemp(prefix="radai_teste_runner_")
    try:
        cam = _harness(tmp, u'''
import os
os.environ["RADAI_THREADS"] = "11"
os.environ.pop("nnUNet_def_n_proc", None)
if sys.argv[1] == "isca":
    import nnunetv2.configuration
R._teto_de_threads()
import nnunetv2.configuration as c
print("TETO=%d" % c.default_num_processes)
''')
        r = subprocess.run([PY, cam, "certo"], capture_output=True, text=True,
                           timeout=180)
        checar(u"no bundle: o nnU-Net le o teto (11)", "TETO=11" in r.stdout,
               (r.stdout + r.stderr)[-160:])
        r2 = subprocess.run([PY, cam, "isca"], capture_output=True, text=True,
                            timeout=180)
        checar(u"ISCA no bundle: depois do import, fica o 8 da biblioteca",
               "TETO=8" in r2.stdout, (r2.stdout + r2.stderr)[-160:])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


class _TorchFalso(object):

    def __init__(self, threads=7):
        self.threads = threads

    def from_numpy(self, a):
        return a

    def get_num_threads(self):
        return self.threads


class _OvFalso(object):
    __version__ = "2026.4.0-falso"

    def __init__(self, saida, falhar_em=None):
        self.saida = saida
        self.falhar_em = falhar_em
        self.pedidos = []

    def convert_model(self, rede, example_input=None):
        self.pedidos.append(("converter",))
        if self.falhar_em == "converter":
            raise RuntimeError("conversao falsa falhou")
        return {"modelo": "convertido"}

    def save_model(self, modelo, caminho, compress_to_fp16=True):
        self.pedidos.append(("salvar", compress_to_fp16))
        io.open(caminho, "w").write(u"<xml/>")
        io.open(caminho[:-4] + ".bin", "wb").write(b"\0")

    def Core(self):
        ov = self

        class _Core(object):
            def set_property(self, *a, **k):
                ov.pedidos.append(("propriedade", a))

            def read_model(self, caminho):
                ov.pedidos.append(("ler", os.path.basename(caminho)))
                return {"modelo": "do_cache"}

            def compile_model(self, modelo, disp, conf):
                ov.pedidos.append(("compilar", disp, dict(conf)))
                if ov.falhar_em == "compilar":
                    raise RuntimeError("compilacao falsa falhou")

                def _inferir(x):
                    if ov.falhar_em == "inferir":
                        raise RuntimeError("inferencia falsa falhou")
                    return [ov.saida(x)]
                return _inferir
        return _Core()


def _rede_ref(x):
    import numpy as _np
    y = _np.zeros((1, 3) + tuple(x.shape[2:]), _np.float32)
    y[:, 1, : x.shape[2] // 2] = 5.0
    y[:, 2, x.shape[2] // 2:] = 5.0
    return y


class _RedeTorchFalsa(object):
    def __init__(self):
        self.chamadas = 0
        self.pesos = []

    def __call__(self, x):
        self.chamadas += 1
        return _rede_ref(x)

    def load_state_dict(self, sd, *a, **k):
        self.pesos.append(sd)
        return "carregado"

    def to(self, *a, **k):
        return self

    def eval(self):
        return self

    def parameters(self):
        return iter(())


def _predictor_com_rede(device="cpu", pasta_pesos=None):
    mod = _predictor_falso()
    cls = mod.nnUNetPredictor

    def initialize_from_trained_model_folder(self, pasta, use_folds=None,
                                             checkpoint_name=None):
        self.pasta = pasta
        self.network = _RedeTorchFalsa()
    cls.initialize_from_trained_model_folder = initialize_from_trained_model_folder
    return mod


def _x(n=8):
    import numpy as _np
    return _np.zeros((1, 1, n, n, n), _np.float32)


def _executor(ov, conferir=True, cache=None, nome="openvino_cpu"):
    return (nome, {"precisao": "f32", "conferir": conferir,
                   "pasta_cache": cache, "ov": ov, "versao": "2026.4.0"})


def _montar(ov, device="cpu", conferir=True, cache=None, pasta=None,
            nome="openvino_cpu"):
    R._EXECUTOR.update(desligado=None, redes=0)
    mod = _predictor_com_rede()
    with _Calado() as cal:
        feitos = R.aplicar_remendos(resultados_na_cpu=False, sem_autocast=False,
                                    modulo=mod,
                                    executor=_executor(ov, conferir, cache, nome))
        p = mod.nnUNetPredictor(use_mirroring=False,
                                device=types.SimpleNamespace(type=device))
        p.initialize_from_trained_model_folder(
            pasta or "x/Dataset831_TotalSegmentator_part1_organs_1830subj/y")
    rede = p.network
    if isinstance(rede, R._RedeOpenVINO):
        rede._torch = _TorchFalso()
    return feitos, p, rede, cal.texto


def teste_o_executor_troca_so_a_passada_e_confere():
    secao(u"D · o executor troca so a passada da rede, e confere")
    import numpy as _np
    ov = _OvFalso(_rede_ref)
    feitos, p, rede, txt = _montar(ov)
    checar(u"o remendo do executor foi aplicado e se anuncia",
           "executor" in feitos and "RADAI|remendo|executor=openvino_cpu" in txt,
           txt[:160])
    checar(u"depois de montada, a rede e o procurador do OpenVINO",
           isinstance(rede, R._RedeOpenVINO), type(rede).__name__)
    checar(u"  e o remendo da rede continua anotando (dataset=831)",
           "RADAI|rede|dataset=831" in txt, txt[:200])
    torch_real = rede._rede
    with _Calado() as cal:
        y1 = rede(_x())
        y2 = rede(_x())
    checar(u"o primeiro patch roda nos DOIS (OpenVINO e PyTorch)",
           torch_real.chamadas == 1, torch_real.chamadas)
    checar(u"  o segundo so no OpenVINO", torch_real.chamadas == 1)
    checar(u"  e a conferencia sai no log com a concordancia",
           "RADAI|executor|dataset=831|conferido=1|concordancia=1.00000" in cal.texto,
           cal.texto[:200])
    checar(u"a saida e a do OpenVINO, copiada (nao o buffer do pedido)",
           _np.array_equal(y1, _rede_ref(_x())) and y1 is not y2)
    comp = [q for q in ov.pedidos if q[0] == "compilar"]
    checar(u"compilado UMA vez para a forma do patch", len(comp) == 1, comp)
    checar(u"  em f32, com as threads que o nnU-Net ja aplicou (7)",
           comp and comp[0][2].get("INFERENCE_PRECISION_HINT") == "f32"
           and comp[0][2].get("INFERENCE_NUM_THREADS") == 7, comp)
    with _Calado():
        rede.load_state_dict({"pesos": 2})
        rede(_x())
    checar(u"load_state_dict vai a rede PyTorch e obriga compilar de novo",
           torch_real.pesos[-1] == {"pesos": 2}
           and len([q for q in ov.pedidos if q[0] == "compilar"]) == 2)
    checar(u"  e a conferencia vale de novo para os pesos novos",
           torch_real.chamadas == 2, torch_real.chamadas)
    checar(u".to() e .eval() devolvem o proprio procurador",
           rede.to("cpu") is rede and rede.eval() is rede)
    checar(u"o que o procurador nao tem vai a rede de verdade (parameters)",
           list(rede.parameters()) == [])
    vazio = R._RedeOpenVINO.__new__(R._RedeOpenVINO)
    checar(u"atributo privado que falta levanta, e nao vira recursao",
           not hasattr(vazio, "_rede"))
    ov_g = _OvFalso(_rede_ref)
    _f, _p, rede_g, _t = _montar(ov_g, nome="openvino_gpu")
    with _Calado():
        rede_g(_x())
    cg = [q for q in ov_g.pedidos if q[0] == "compilar"]
    checar(u"openvino_gpu compila para GPU, sem INFERENCE_NUM_THREADS",
           cg and cg[0][1] == "GPU" and "INFERENCE_NUM_THREADS" not in cg[0][2], cg)
    R._EXECUTOR.update(desligado=None, redes=0)


def teste_o_executor_cai_para_o_pytorch():
    secao(u"D · o executor cai para o PyTorch, e diz")
    import numpy as _np

    def trocada(x):
        y = _rede_ref(x)
        return y[:, ::-1].copy()
    for falha in ("converter", "compilar", "inferir"):
        ov = _OvFalso(_rede_ref, falhar_em=falha)
        _f, _p, rede, _t = _montar(ov)
        with _Calado() as cal:
            y = rede(_x())
        checar(u"falha ao %s: o PyTorch responde" % falha,
               _np.array_equal(y, _rede_ref(_x())))
        checar(u"  RADAI|aviso|executor ... recuo para o PyTorch CPU",
               "RADAI|aviso|executor openvino_cpu falhou" in cal.texto
               and "recuo para o PyTorch CPU" in cal.texto, cal.texto[:200])
        checar(u"  e o executor fica DESLIGADO no processo",
               bool(R._EXECUTOR.get("desligado")), R._EXECUTOR)
    mod = _predictor_com_rede()
    with _Calado():
        R.aplicar_remendos(resultados_na_cpu=False, sem_autocast=False,
                           modulo=mod, executor=_executor(_OvFalso(_rede_ref)))
        p = mod.nnUNetPredictor(use_mirroring=False,
                                device=types.SimpleNamespace(type="cpu"))
        p.initialize_from_trained_model_folder("x/Dataset832_y/z")
    checar(u"desligado, a rede seguinte fica a do PyTorch (nao embrulha)",
           not isinstance(p.network, R._RedeOpenVINO), type(p.network).__name__)
    ov = _OvFalso(trocada)
    _f, _p, rede, _t = _montar(ov)
    with _Calado() as cal:
        y = rede(_x())
    checar(u"primeiro patch DISCORDA: sai o do PyTorch",
           _np.array_equal(y, _rede_ref(_x())))
    checar(u"  e o motivo tem a concordancia medida",
           "patch conferido discorda do PyTorch" in cal.texto
           and "onde ha estrutura" in cal.texto, cal.texto[:300])
    ov = _OvFalso(trocada)
    _f, _p, rede, _t = _montar(ov, conferir=False)
    with _Calado():
        y = rede(_x())
    checar(u"ISCA: sem a conferencia, a saida trocada PASSARIA",
           not _np.array_equal(y, _rede_ref(_x())))
    ov = _OvFalso(_rede_ref)
    _f, p, rede, txt = _montar(ov, device="cuda")
    checar(u"predictor em CUDA: o executor fica de fora, e diz",
           not isinstance(rede, R._RedeOpenVINO)
           and "executor openvino_cpu ignorado" in txt, txt[:200])
    R._EXECUTOR.update(desligado=None, redes=0)


def teste_o_ir_convertido_e_guardado():
    secao(u"D · o IR convertido e guardado, e so reaproveitado com os mesmos pesos")
    tmp = tempfile.mkdtemp(prefix="radai_teste_runner_")
    try:
        pasta = os.path.join(tmp, "Dataset831_x", "trainer__nnUNetPlans__3d_fullres")
        os.makedirs(os.path.join(pasta, "fold_0"))
        ck = os.path.join(pasta, "fold_0", "checkpoint_final.pth")
        io.open(ck, "wb").write(b"pesos")
        cache = os.path.join(tmp, "cache")
        ov1 = _OvFalso(_rede_ref)
        _f, _p, r1, _t = _montar(ov1, cache=cache, pasta=pasta)
        with _Calado() as c1:
            r1.load_state_dict({"w": 1})
            r1(_x())
        salvos = [q for q in ov1.pedidos if q[0] == "salvar"]
        checar(u"primeira vez: converte e GUARDA o IR",
               ("converter",) in ov1.pedidos and salvos, ov1.pedidos)
        checar(u"  sem comprimir os pesos para fp16 (compress_to_fp16=False)",
               salvos and salvos[0][1] is False, salvos)
        checar(u"  e a linha diz ir=convertido", "ir=convertido" in c1.texto,
               c1.texto[:200])
        ov2 = _OvFalso(_rede_ref)
        _f, _p, r2, _t = _montar(ov2, cache=cache, pasta=pasta)
        with _Calado() as c2:
            r2.load_state_dict({"w": 1})
            r2(_x())
        checar(u"segunda vez, mesmos pesos: le o IR guardado, sem converter",
               ("converter",) not in ov2.pedidos
               and any(q[0] == "ler" for q in ov2.pedidos), ov2.pedidos)
        checar(u"  e a linha diz ir=cache", "ir=cache" in c2.texto, c2.texto[:200])
        os.utime(ck, (1, 1))
        ov3 = _OvFalso(_rede_ref)
        _f, _p, r3, _t = _montar(ov3, cache=cache, pasta=pasta)
        with _Calado():
            r3.load_state_dict({"w": 1})
            r3(_x())
        checar(u"ISCA: checkpoint com outra data converte de novo",
               ("converter",) in ov3.pedidos, ov3.pedidos)
        ov4 = _OvFalso(_rede_ref)
        _f, _p, r4, _t = _montar(ov4, cache=None, pasta=pasta)
        with _Calado():
            r4.load_state_dict({"w": 1})
            r4(_x())
        checar(u"sem pasta de cache, nada e gravado",
               not [q for q in ov4.pedidos if q[0] == "salvar"], ov4.pedidos)
    finally:
        R._EXECUTOR.update(desligado=None, redes=0)
        shutil.rmtree(tmp, ignore_errors=True)


class _TensorFalso(object):

    def __init__(self, a, onde="cpu", log=None):
        self.a, self.onde, self.log = a, onde, log if log is not None else []

    def to(self, dev):
        self.log.append(("x.to", dev))
        return _TensorFalso(self.a, dev, self.log)

    def float(self):
        return self

    def detach(self):
        return self

    def numpy(self):
        return self.a

    def cpu(self):
        return _TensorFalso(self.a, "cpu", self.log)

    @property
    def shape(self):
        return self.a.shape


class _RedeXpuFalsa(_RedeTorchFalsa):

    def __init__(self, trocar_na_placa=False):
        _RedeTorchFalsa.__init__(self)
        self.onde = "cpu"
        self.trocar = trocar_na_placa

    def to(self, dev, *a, **k):
        self.onde = dev
        return self

    def __call__(self, x):
        self.chamadas += 1
        a = x.a if isinstance(x, _TensorFalso) else x
        y = _rede_ref(a)
        if self.onde != "cpu" and self.trocar:
            y = y[:, ::-1].copy()
        if isinstance(x, _TensorFalso):
            return _TensorFalso(y, x.onde, x.log)
        return y


class _TorchXpuFalso(_TorchFalso):
    class _SemGrad(object):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def no_grad(self):
        return self._SemGrad()


def teste_o_executor_xpu():
    secao(u"D · o executor XPU: copia na placa, original na CPU")
    import numpy as _np
    R._EXECUTOR.update(desligado=None, redes=0)
    rede = _RedeXpuFalsa()
    p = R._RedeXPU(rede, "xpu", dataset="831", torch_mod=_TorchXpuFalso())
    x = _TensorFalso(_x())
    with _Calado() as cal:
        y = p(x)
    checar(u"a passada volta na CPU", isinstance(y, _TensorFalso) and y.onde == "cpu")
    checar(u"  e a entrada foi a XPU", ("x.to", "xpu") in x.log, x.log)
    checar(u"a rede ORIGINAL continua na CPU (e a copia que foi a placa)",
           rede.onde == "cpu" and p._na_placa is not None
           and p._na_placa is not rede, (rede.onde, type(p._na_placa)))
    checar(u"a copia e anunciada com o tempo (mover_s)",
           "RADAI|executor|dataset=831|backend=xpu|mover_s=" in cal.texto,
           cal.texto[:200])
    checar(u"  e o primeiro patch conferido contra a CPU",
           "conferido=1|concordancia=1.00000" in cal.texto, cal.texto[:300])
    with _Calado():
        p.load_state_dict({"w": 9})
    checar(u"pesos novos: a copia na placa e refeita", p._na_placa is None)
    rede2 = _RedeXpuFalsa(trocar_na_placa=True)
    p2 = R._RedeXPU(rede2, "xpu", dataset="832", torch_mod=_TorchXpuFalso())
    with _Calado() as cal2:
        y2 = p2(_TensorFalso(_x()))
    checar(u"ISCA: a copia que ERRA na placa e pega; sai o da CPU",
           _np.array_equal(getattr(y2, "a", y2), _rede_ref(_x()))
           and "discorda" in cal2.texto, cal2.texto[:200])
    R._EXECUTOR.update(desligado=None, redes=0)
    with _Calado() as cal3:
        ex, _op = R._executor_pedido({"RADAI_EXECUTOR": "xpu"})
    checar(u"xpu pedido num torch sem XPU (o .venv, ou o CUDA do pacote): "
           u"aviso, e o PyTorch CPU",
           ex is None and "aviso|executor xpu" in cal3.texto, cal3.texto)


def teste_sem_pedido_o_envelope_e_o_de_antes():
    secao(u"D · sem pedido, o envelope e o de antes")
    velho = {k: os.environ.pop(k, None) for k in ("RADAI_EXECUTOR",
                                                   "RADAI_EXECUTOR_PASTA")}
    try:
        with _Calado() as cal:
            ex, op = R._executor_pedido()
        checar(u"sem RADAI_EXECUTOR: nenhum executor, calado",
               ex is None and not cal.texto, cal.texto)
        mod = _predictor_com_rede()
        with _Calado():
            feitos = R.aplicar_remendos(resultados_na_cpu=False,
                                        sem_autocast=False, modulo=mod)
            p = mod.nnUNetPredictor(use_mirroring=False,
                                    device=types.SimpleNamespace(type="cpu"))
            p.initialize_from_trained_model_folder("x/Dataset831_a/b")
        checar(u"  e a rede fica a do PyTorch",
               "executor" not in feitos
               and not isinstance(p.network, R._RedeOpenVINO), feitos)
        for pedido, espera in (("torch_cpu", None), ("TORCH", None)):
            with _Calado() as cal:
                ex, _op = R._executor_pedido({"RADAI_EXECUTOR": pedido})
            checar(u"RADAI_EXECUTOR=%s e o PyTorch, calado" % pedido,
                   ex is espera and not cal.texto, cal.texto)
        with _Calado() as cal:
            ex, _op = R._executor_pedido({"RADAI_EXECUTOR": "cuda_turbo"})
        checar(u"executor desconhecido: aviso, e o PyTorch",
               ex is None and "desconhecido" in cal.texto, cal.texto)
        falsos = dict(sys.modules)
        sys.modules["openvino"] = None
        try:
            with _Calado() as cal:
                ex, _op = R._executor_pedido({"RADAI_EXECUTOR": "openvino_cpu"})
        finally:
            if falsos.get("openvino") is None:
                sys.modules.pop("openvino", None)
            else:
                sys.modules["openvino"] = falsos["openvino"]
        checar(u"openvino pedido e ausente: aviso, e o PyTorch (a serie segue)",
               ex is None and "openvino nao importa" in cal.texto, cal.texto)
    finally:
        for k, v in velho.items():
            if v is not None:
                os.environ[k] = v


class _AsyncFalso(object):
    def __init__(self, valor=None, erro=None):
        self.valor, self.erro = valor, erro

    def ready(self):
        return True

    def get(self, timeout=None):
        if self.erro is not None:
            raise self.erro
        return self.valor


class _PoolFalsa(object):

    def __init__(self, registro, pipe_bytes):
        self.registro = registro
        self.pipe_bytes = pipe_bytes
        self._pool = [types.SimpleNamespace(is_alive=lambda: True)] * 2
        self.saiu = False

    def __enter__(self):
        self.registro.append(("enter",))
        return self

    def __exit__(self, *a):
        self.saiu = True
        self.registro.append(("exit",))
        return False

    def _carga(self, args):
        return sum(getattr(a, "nbytes", 0) for a in args)

    def apply_async(self, func, args=(), kwds=None, callback=None,
                    error_callback=None):
        self.registro.append(("apply_async", self._carga(args)))
        if self._carga(args) > self.pipe_bytes:
            return _AsyncFalso(erro=OSError(22, "[WinError 87] Parametro "
                                                "incorreto (pipe dublado)"))
        return _AsyncFalso(valor=("filho", func(*args, **(kwds or {}))))

    def starmap_async(self, func, iterable, chunksize=None, callback=None,
                      error_callback=None):
        lista = list(iterable)
        self.registro.append(("starmap_async", max(self._carga(a) for a in lista)))
        if max(self._carga(a) for a in lista) > self.pipe_bytes:
            return _AsyncFalso(erro=OSError(22, "[WinError 87] (dublado)"))
        return _AsyncFalso(valor=[("filho", func(*a)) for a in lista])


def _mp_falso(registro, pipe_bytes):
    ctx = types.SimpleNamespace(Pool=lambda *a, **k: _PoolFalsa(registro,
                                                               pipe_bytes))
    return types.SimpleNamespace(get_context=lambda *a, **k: ctx,
                                 Pool=ctx.Pool, TimeoutError=TimeoutError,
                                 cpu_count=lambda: 3)


def _laco_do_ts(mod, func, matriz, extra="s01"):
    with mod.multiprocessing.get_context("spawn").Pool(2) as export_pool:
        worker_list = [i for i in export_pool._pool]
        r = [export_pool.apply_async(func, (matriz, extra))]
        [not i.ready() for i in r]
        try:
            while True:
                if not all(j.is_alive() for j in worker_list):
                    raise RuntimeError("worker morreu")
                try:
                    return r[0].get(timeout=0.1)
                except mod.multiprocessing.TimeoutError:
                    pass
        except Exception as e:
            return e


def teste_a_exportacao_grande_roda_no_processo():
    secao(u"W2E · a exportacao grande roda no proprio processo")
    import numpy as _np
    chamadas = []

    def exportar(matriz, nome):
        chamadas.append((os.getpid(), matriz.shape, nome))
        return int(_np.argmax(matriz, axis=0).sum())
    grande = _np.zeros((3, 40, 40, 40), _np.float16)
    grande[1, :20] = 5
    grande[2, 20:] = 5
    pequena = grande[:, :10].copy()
    esperado = int(_np.argmax(grande, axis=0).sum())
    limiar = 200000
    reg = []
    mod = _predictor_falso()
    mod.multiprocessing = _mp_falso(reg, pipe_bytes=250000)
    with _Calado() as cal:
        feitos = R.aplicar_remendos(resultados_na_cpu=False, sem_autocast=False,
                                    modulo=mod, executor=False,
                                    exportacao=limiar)
        v = _laco_do_ts(mod, exportar, grande)
    checar(u"o remendo da exportacao e aplicado (e o modulo ve o procurador)",
           "exportacao" in feitos and isinstance(
               mod.multiprocessing, R._MultiprocessingComExportacaoNoProcesso),
           (feitos, type(mod.multiprocessing).__name__))
    checar(u"matriz acima do limiar: exportada AQUI, e o valor e o da funcao",
           v == esperado and chamadas and chamadas[-1][0] == os.getpid(),
           (v, esperado, chamadas[-1:]))
    checar(u"  e a Pool da biblioteca NAO recebeu a matriz (nem o pipe)",
           not [q for q in reg if q[0] == "apply_async"], reg)
    checar(u"  com a linha RADAI|remendo|exportacao=no_processo e o tamanho",
           "RADAI|remendo|exportacao=no_processo|funcao=exportar|matriz_mb=0|"
           "limiar_mb=0" in cal.texto and "feita_s=" in cal.texto,
           cal.texto[:300])
    checar(u"  e a Pool continua sendo aberta e fechada como antes (with)",
           ("enter",) in reg and ("exit",) in reg, reg)
    del reg[:]
    with _Calado() as cal2:
        v2 = _laco_do_ts(mod, exportar, pequena)
    checar(u"matriz abaixo do limiar: vai a Pool da biblioteca, como sempre",
           v2 == ("filho", int(_np.argmax(pequena, axis=0).sum()))
           and ("apply_async", pequena.nbytes) in reg, (v2, reg))
    checar(u"  e nada se anuncia", "exportacao=no_processo" not in cal2.texto,
           cal2.texto[:160])
    del reg[:]
    with _Calado():
        pool = mod.multiprocessing.get_context("spawn").Pool(2)
        with pool as p:
            rs = p.starmap_async(exportar, ((grande, "s01"),))
            v3 = rs.get()[0]
            rs2 = p.starmap_async(exportar, ((pequena, "s02"),))
            v4 = rs2.get()[0]
    checar(u"starmap_async: a grande aqui, a pequena na Pool",
           v3 == esperado and v4[0] == "filho"
           and [q[0] for q in reg if q[0] == "starmap_async"] == ["starmap_async"],
           (v3, v4, reg))
    def explode(matriz, nome):
        raise MemoryError("sem RAM (dublado)")
    erros = []
    with _Calado() as cal3:
        with mod.multiprocessing.get_context("spawn").Pool(2) as p:
            r = p.apply_async(explode, (grande, "s01"),
                              error_callback=erros.append)
            pronto = r.ready()
            try:
                r.get(timeout=0.1)
                subiu = None
            except MemoryError as e:
                subiu = e
    checar(u"excecao da exportacao: sobe no get(), com o error_callback",
           pronto and isinstance(subiu, MemoryError) and len(erros) == 1
           and not r.successful(), (pronto, subiu, erros))
    checar(u"  e e dita (RADAI|aviso|exportacao no processo levantou)",
           "aviso|exportacao no processo levantou MemoryError" in cal3.texto,
           cal3.texto[:200])
    checar(u"o resto do multiprocessing e o de verdade (TimeoutError)",
           mod.multiprocessing.TimeoutError is TimeoutError
           and mod.multiprocessing.cpu_count() == 3)
    with _Calado():
        R.aplicar_remendos(resultados_na_cpu=False, sem_autocast=False,
                           modulo=mod, executor=False, exportacao=limiar)
    checar(u"aplicado duas vezes nao embrulha duas vezes",
           not isinstance(mod.multiprocessing._real,
                          R._MultiprocessingComExportacaoNoProcesso))
    reg_isca = []
    mod_isca = _predictor_falso()
    mod_isca.multiprocessing = _mp_falso(reg_isca, pipe_bytes=250000)
    with _Calado():
        R.aplicar_remendos(resultados_na_cpu=False, sem_autocast=False,
                           modulo=mod_isca, executor=False, exportacao=False)
        vi = _laco_do_ts(mod_isca, exportar, grande)
    checar(u"ISCA: sem o remendo, a matriz grande vai ao pipe e a task morre "
           u"(WinError 87)", isinstance(vi, OSError) and "87" in str(vi), vi)
    mod_sem = _predictor_falso()
    del mod_sem.multiprocessing
    with _Calado() as cal4:
        feitos4 = R.aplicar_remendos(resultados_na_cpu=False,
                                     sem_autocast=False, modulo=mod_sem,
                                     executor=False)
    checar(u"sem `multiprocessing` no modulo: o remendo nao entra, e e dito",
           "exportacao" not in feitos4
           and "aviso|remendo exportacao FALHOU" in cal4.texto, cal4.texto[:200])
    for bruto, esp, dito in (("", R.LIMIAR_EXPORTACAO_NO_PROCESSO_MB * 1048576,
                              False),
                             ("0", 0, False), ("512", 512 * 1048576, False),
                             ("-1", R.LIMIAR_EXPORTACAO_NO_PROCESSO_MB * 1048576,
                              True),
                             ("dois", R.LIMIAR_EXPORTACAO_NO_PROCESSO_MB * 1048576,
                              True)):
        with _Calado() as c5:
            n, _o = R._limiar_de_exportacao({"RADAI_EXPORTACAO_LIMIAR_MB": bruto})
        checar(u"RADAI_EXPORTACAO_LIMIAR_MB=%r -> %d MiB%s"
               % (bruto, esp // 1048576, u", e o valor ruim e dito" if dito else u""),
               n == esp and (("aviso|RADAI_EXPORTACAO_LIMIAR_MB" in c5.texto)
                             == dito), (n, c5.texto))
    checar(u"o limiar de fabrica e 2048 MiB (abaixo das 2,02 GiB medidas "
           u"passando no pipe; a falha medida e 4,24 GiB)",
           R.LIMIAR_EXPORTACAO_NO_PROCESSO_MB == 2048)
    import ast
    fonte = io.open(_componentes.fonte("app/radai_ts_runner.py"),
                    encoding="utf-8").read()
    arvore = ast.parse(fonte)
    fn = next(n for n in ast.walk(arvore)
              if isinstance(n, ast.FunctionDef) and n.name == "aplicar_remendos")
    pais = {}
    for n in ast.walk(fn):
        for f in ast.iter_child_nodes(n):
            pais[f] = n
    chamada = [n for n in ast.walk(fn) if isinstance(n, ast.Call)
               and getattr(n.func, "id", "") == "_remendar_exportacao"]
    condicoes = []
    no = chamada[0] if chamada else None
    while no is not None and no is not fn:
        no = pais.get(no)
        if isinstance(no, ast.If):
            condicoes.append(ast.dump(no.test))
    so_o_parametro = (len(condicoes) == 1 and "exportacao" in condicoes[0]
                      and "IsNot" in condicoes[0]
                      and "RADAI" not in condicoes[0]
                      and "environ" not in condicoes[0])
    checar(u"AST: _remendar_exportacao e chamado em aplicar_remendos, so sob "
           u"`exportacao is not False` (incondicional no campo)",
           bool(chamada) and so_o_parametro, condicoes)
    ret_cedo = [n.lineno for n in ast.walk(fn) if isinstance(n, ast.Return)]
    checar(u"  e antes dos remendos que SO rodam quando pedidos",
           chamada and chamada[0].lineno < min(
               n.lineno for n in ast.walk(fn) if isinstance(n, ast.Call)
               and getattr(n.func, "id", "") == "_remendar_resultados_na_cpu"),
           ret_cedo)
    _exportacao_de_verdade()


_MODULO_DA_EXPORTACAO = u'''# -*- coding: utf-8 -*-
import hashlib, os
import numpy as np


def exportar(matriz, destino):
    seg = np.argmax(matriz, axis=0).astype(np.uint8)
    np.save(destino, seg)
    return {"pid": os.getpid(),
            "sha": hashlib.sha256(seg.tobytes()).hexdigest()}
'''

_HARNESS_DA_EXPORTACAO = u'''# -*- coding: utf-8 -*-
import json, multiprocessing, os, sys, types
sys.path.insert(0, sys.argv[1])
sys.path.insert(0, sys.argv[2])
import radai_ts_runner as R
import exportacao_falsa as F
import numpy as np
if __name__ == "__main__":
    limiar, saida = int(sys.argv[3]), sys.argv[4]
    mod = types.ModuleType("prd_falso")
    mod.multiprocessing = multiprocessing
    R._remendar_exportacao(mod, limiar)
    m = np.random.RandomState(7).standard_normal((4, 20, 24, 16)).astype(np.float16)
    with mod.multiprocessing.get_context("spawn").Pool(2) as pool:
        workers = [w.pid for w in pool._pool]
        r = pool.apply_async(F.exportar, (m, saida))
        while True:
            try:
                v = r.get(timeout=0.1)
                break
            except mod.multiprocessing.TimeoutError:
                pass
        v2 = pool.starmap_async(F.exportar, ((m, saida[:-4] + "_s.npy"),)).get()[0]
    print("RESULTADO=" + json.dumps({"pai": os.getpid(), "v": v, "v2": v2,
                                     "workers": workers}))
'''


def _exportacao_de_verdade():
    import hashlib
    tmp = tempfile.mkdtemp(prefix="radai_teste_runner_")
    try:
        io.open(os.path.join(tmp, "exportacao_falsa.py"), "w",
                encoding="utf-8").write(_MODULO_DA_EXPORTACAO)
        h = os.path.join(tmp, "harness_exportacao.py")
        io.open(h, "w", encoding="utf-8").write(_HARNESS_DA_EXPORTACAO)
        res = {}
        for nome, limiar in (("pipe", 1 << 40), ("aqui", 0)):
            saida = os.path.join(tmp, "seg_%s.npy" % nome)
            r = subprocess.run([PY, h, APP, tmp, str(limiar), saida],
                               capture_output=True, text=True, timeout=300,
                               cwd=tmp)
            linha = [l for l in r.stdout.splitlines()
                     if l.startswith("RESULTADO=")]
            res[nome] = (json.loads(linha[0][10:]) if linha else
                         {"erro": (r.stdout + r.stderr)[-400:]})
            res[nome]["log"] = r.stdout
            if os.path.isfile(saida):
                res[nome]["arquivo"] = hashlib.sha256(
                    io.open(saida, "rb").read()).hexdigest()
        p, a = res["pipe"], res["aqui"]
        checar(u"Pool de verdade, limiar alto: a exportacao roda num FILHO",
               "erro" not in p and p["v"]["pid"] != p["pai"]
               and p["v"]["pid"] in p["workers"], p.get("erro") or p.get("v"))
        checar(u"limiar 0: a MESMA funcao roda no PAI, e diz",
               "erro" not in a and a["v"]["pid"] == a["pai"]
               and "exportacao=no_processo" in a["log"],
               a.get("erro") or a.get("v"))
        checar(u"os dois caminhos dao o MESMO resultado (argmax e arquivo)",
               "erro" not in p and "erro" not in a
               and p["v"]["sha"] == a["v"]["sha"] == a["v2"]["sha"]
               and p.get("arquivo") and p.get("arquivo") == a.get("arquivo"),
               (p.get("v"), a.get("v")))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    _exportacao_do_ts_de_verdade()


_HARNESS_DO_TS = u'''# -*- coding: utf-8 -*-
import hashlib, json, os, sys
sys.path.insert(0, sys.argv[1])
import radai_ts_runner as R
if __name__ == "__main__":
    modelo, limiar, pasta = sys.argv[2], int(sys.argv[3]), sys.argv[4]
    import numpy as np
    import SimpleITK as sitk
    import torch
    import nnunetv2.inference.predict_from_raw_data as prd
    from totalsegmentator import nnunet_runtime_patches as P
    from nnunetv2.utilities.plans_handling.plans_handler import PlansManager
    from batchgenerators.utilities.file_and_folder_operations import load_json
    R._remendar_exportacao(prd, limiar)
    pm = PlansManager(os.path.join(modelo, "plans.json"))
    ds = load_json(os.path.join(modelo, "dataset.json"))
    cm = pm.get_configuration("3d_fullres")
    lm = pm.get_label_manager(ds)
    img = sitk.GetImageFromArray(np.zeros((12, 20, 16), np.int16))
    img.SetSpacing((6.0, 6.0, 6.0))
    arq = os.path.join(pasta, "entrada_0000.nii.gz")
    sitk.WriteImage(img, arq)
    rw = pm.image_reader_writer_class()
    dados, props = rw.read_images([arq])
    forma = list(dados.shape[1:])
    props["shape_before_cropping"] = forma
    props["bbox_used_for_cropping"] = [[0, s] for s in forma]
    props["shape_after_cropping_and_before_resampling"] = forma
    rs = np.random.RandomState(11)
    logits = rs.standard_normal([lm.num_segmentation_heads] + forma).astype(np.float16)

    class Falso(object):
        verbose = False
        perform_everything_on_device = False
        device = torch.device("cpu")
        configuration_manager = cm
        plans_manager = pm
        dataset_json = ds
        label_manager = lm

        def predict_logits_from_preprocessed_data(self, data):
            return torch.from_numpy(logits.copy())
    it = [{"data": torch.zeros([1] + forma), "ofile": os.path.join(pasta, "s01"),
           "data_properties": props}]
    P.predict_from_data_iterator(Falso(), it, False, 1, False)
    seg = sitk.GetArrayFromImage(sitk.ReadImage(os.path.join(pasta, "s01" + ds["file_ending"])))
    print("RESULTADO=" + json.dumps({"sha": hashlib.sha256(seg.tobytes()).hexdigest(),
                                     "classes": sorted(int(c) for c in np.unique(seg)),
                                     "forma": list(seg.shape)}))
'''


def _pasta_dos_pesos():
    for c in (os.environ.get("RADAI_PESOS_CANARIO"),
              os.path.join(os.path.dirname(os.path.dirname(
                  os.path.abspath(sys.executable))), "ts_weights")):
        if c and os.path.isdir(c):
            return c
    return None


def _exportacao_do_ts_de_verdade():
    try:
        import nnunetv2
        import totalsegmentator.nnunet_runtime_patches
    except Exception:
        return
    pesos = _pasta_dos_pesos()
    modelo = None
    for d in sorted(os.listdir(pesos)) if pesos else []:
        if d.startswith("Dataset300_"):
            base = os.path.join(pesos, d)
            for s in sorted(os.listdir(base)):
                if s.endswith("__nnUNetPlans__3d_fullres") and os.path.isfile(
                        os.path.join(base, s, "plans.json")):
                    modelo = os.path.join(base, s)
    if not modelo:
        checar(u"no pacote: os planos do Dataset300 para a exportacao de verdade",
               False, u"sem ts_weights/Dataset300 (RADAI_PESOS_CANARIO?)")
        return
    tmp = tempfile.mkdtemp(prefix="radai_teste_runner_")
    try:
        h = os.path.join(tmp, "harness_ts.py")
        io.open(h, "w", encoding="utf-8").write(_HARNESS_DO_TS)
        res = {}
        for nome, limiar in (("pipe", 1 << 40), ("aqui", 0)):
            pasta = os.path.join(tmp, nome)
            os.makedirs(pasta)
            r = subprocess.run([PY, h, APP, modelo, str(limiar), pasta],
                               capture_output=True, text=True, timeout=600,
                               cwd=tmp)
            linha = [l for l in r.stdout.splitlines()
                     if l.startswith("RESULTADO=")]
            res[nome] = (json.loads(linha[0][10:]) if linha else
                         {"erro": (r.stdout + r.stderr)[-500:]})
            res[nome]["no_processo"] = "exportacao=no_processo" in r.stdout
        p, a = res["pipe"], res["aqui"]
        checar(u"no pacote: o laco do TotalSegmentator exporta pela Pool "
               u"(limiar alto) e no processo (limiar 0)",
               "erro" not in p and "erro" not in a and not p["no_processo"]
               and a["no_processo"], (p, a))
        checar(u"  e o NIfTI dos dois caminhos e o MESMO (sha256 do rotulo)",
               "erro" not in p and "erro" not in a and p["sha"] == a["sha"]
               and len(p.get("classes") or []) >= 2, (p, a))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def teste_a_regua_da_conferencia_e_a_do_canario():
    secao(u"W2E · a regua da conferencia e a do canario, e o patch tem estrutura")
    import numpy as _np
    import radai_devices as RDV
    rg = R._regua_da_conferencia()
    checar(u"a regua vem de radai_devices (limiar %s)" % RDV.LIMIAR_CONCORDANCIA,
           rg["limiar"] == RDV.LIMIAR_CONCORDANCIA
           and rg["estruturas"] == RDV.ESTRUTURAS_MINIMAS_NO_PATCH
           and rg["fracao"] == RDV.FRACAO_MINIMA_DE_ESTRUTURA_NO_PATCH
           and rg["patches"] == RDV.PATCHES_MAXIMOS_PARA_CONFERIR, rg)
    import ast
    fonte = io.open(_componentes.fonte("app/radai_ts_runner.py"),
                    encoding="utf-8").read()
    arvore = ast.parse(fonte)
    atrib = [n.targets[0].id for n in arvore.body if isinstance(n, ast.Assign)
             and isinstance(n.targets[0], ast.Name)]
    literais = [n.lineno for n in ast.walk(arvore)
                if isinstance(n, ast.Constant) and n.value in (0.999, 0.99)]
    checar(u"AST: o envelope nao tem limiar proprio (nem CONCORDANCIA_MINIMA, "
           u"nem 0.999 literal)",
           "CONCORDANCIA_MINIMA" not in atrib and not literais, literais)
    cls = next(n for n in ast.walk(arvore)
               if isinstance(n, ast.ClassDef) and n.name == "_RedeOpenVINO")
    chama = next(n for n in cls.body if isinstance(n, ast.FunctionDef)
                 and n.name == "__call__")
    usa_regua = [n for n in ast.walk(chama) if isinstance(n, ast.Subscript)
                 and isinstance(n.value, ast.Name) and n.value.id == "regua"]
    checar(u"AST: __call__ julga pela regua (limiar, estruturas e fracao)",
           {"limiar", "estruturas", "fracao", "patches"} <= set(
               getattr(n.slice, "value", None) for n in usa_regua),
           [getattr(n.slice, "value", None) for n in usa_regua])

    def logits_de(rotulos, c=3):
        y = _np.zeros((1, c) + rotulos.shape, _np.float32)
        for k in range(c):
            y[0, k][rotulos == k] = 5.0
        return y
    n = 24
    fundo = _np.zeros((n, n, n), _np.int64)
    fundo[0, 0, :5] = 1
    com_estrutura = _np.zeros((n, n, n), _np.int64)
    com_estrutura[:6] = 1
    com_estrutura[6:12] = 2
    tudo_fundo = _np.zeros((n, n, n), _np.int64)

    class _RedeDeRotulos(object):

        def __init__(self, seq):
            self.seq, self.chamadas = list(seq), 0

        def __call__(self, x):
            self.chamadas += 1
            return logits_de(self.seq[min(self.chamadas, len(self.seq)) - 1])

        def load_state_dict(self, *a, **k):
            return None

        def eval(self):
            return self

    class _ExecutorDeFundo(R._RedeOpenVINO):
        def _passada(self, x):
            return logits_de(tudo_fundo)

    def montar(seq, regua=None):
        R._EXECUTOR.update(desligado=None, redes=0)
        return _ExecutorDeFundo(_RedeDeRotulos(seq), "openvino_cpu",
                                dataset="833", regua=regua)
    x = _np.zeros((1, 1, n, n, n), _np.float32)
    p = montar([fundo, com_estrutura])
    with _Calado() as c1:
        y1 = p(x)
    checar(u"patch quase todo fundo (0,04% de estrutura): nao e julgado, "
           u"sai o do PyTorch", _np.array_equal(y1, logits_de(fundo))
           and not p._conferido and not R._EXECUTOR.get("desligado"),
           (p._conferido, R._EXECUTOR, c1.texto[:200]))
    with _Calado() as c2:
        y2 = p(x)
    checar(u"  o patch seguinte TEM estrutura, e o executor de fundo e "
           u"REPROVADO nele (onde ha estrutura)",
           _np.array_equal(y2, logits_de(com_estrutura))
           and bool(R._EXECUTOR.get("desligado"))
           and "onde ha estrutura" in c2.texto, c2.texto[:300])
    p_meia = montar([fundo], regua={"limiar": RDV.LIMIAR_CONCORDANCIA,
                                    "estruturas": 0, "fracao": 0.0,
                                    "patches": 8})
    with _Calado() as ci:
        p_meia(x)
    checar(u"sem a guarda de fracao, o patch de fundo e julgado -- e a "
           u"concordancia onde ha estrutura (0%) reprova o executor de fundo",
           "conferido=1" not in ci.texto and "onde ha estrutura" in ci.texto
           and bool(R._EXECUTOR.get("desligado")), ci.texto[:300])
    m = R._medir_patch(logits_de(tudo_fundo), logits_de(fundo))
    checar(u"  a medida do patch: 99,96% no argmax inteiro, 0% onde ha estrutura",
           m["concordancia"] >= 0.999 and m["concordancia_estrutura"] == 0.0
           and m["estruturas"] == 1 and m["fracao"] < 0.01, m)
    def medida_antiga(a, b):
        mm = R.__dict__["_medir_patch_original"](a, b)
        mm["concordancia_estrutura"] = mm["concordancia"]
        return mm
    R._medir_patch_original = R._medir_patch
    try:
        with _Troca(R, _medir_patch=medida_antiga):
            p_isca = montar([fundo], regua={"limiar": RDV.LIMIAR_CONCORDANCIA,
                                            "estruturas": 0, "fracao": 0.0,
                                            "patches": 8})
            with _Calado() as cj:
                yj = p_isca(x)
    finally:
        del R._medir_patch_original
    checar(u"ISCA: com a regua antiga, o executor de FUNDO seria conferido "
           u"e aprovado no patch de fundo",
           "conferido=1" in cj.texto and not R._EXECUTOR.get("desligado")
           and _np.array_equal(yj, logits_de(tudo_fundo)), cj.texto[:300])
    p3 = montar([fundo] * 20)
    with _Calado() as c3:
        for _ in range(RDV.PATCHES_MAXIMOS_PARA_CONFERIR + 2):
            y3 = p3(x)
    checar(u"%d patches sem estrutura: ESTA rede fica no PyTorch, e diz"
           % RDV.PATCHES_MAXIMOS_PARA_CONFERIR,
           p3._so_pytorch and not R._EXECUTOR.get("desligado")
           and "ESTA rede fica no PyTorch CPU" in c3.texto
           and c3.texto.count("ESTA rede") == 1, c3.texto[-300:])
    checar(u"  e as passadas seguintes nem chamam o executor",
           p3._rede.chamadas == RDV.PATCHES_MAXIMOS_PARA_CONFERIR + 2,
           p3._rede.chamadas)
    with _Calado():
        p3.load_state_dict({})
    checar(u"  pesos novos: a rede volta a tentar conferir",
           not p3._so_pytorch and p3._tentativas == 0)
    class _ExecutorIgual(R._RedeOpenVINO):
        def _passada(self, x):
            return logits_de(com_estrutura)
    R._EXECUTOR.update(desligado=None, redes=0)
    with _Troca(RDV, LIMIAR_CONCORDANCIA=1.01):
        pi = _ExecutorIgual(_RedeDeRotulos([com_estrutura]), "openvino_cpu",
                            dataset="831")
        with _Calado() as c4:
            pi(x)
    checar(u"ISCA: com o limiar de radai_devices em 1,01, o executor IDENTICO "
           u"cai -- o envelope le a regua de la",
           bool(R._EXECUTOR.get("desligado")), c4.texto[:200])
    R._EXECUTOR.update(desligado=None, redes=0)
    pj = _ExecutorIgual(_RedeDeRotulos([com_estrutura]), "openvino_cpu",
                        dataset="831")
    with _Calado() as c5:
        pj(x)
    checar(u"com a regua de fabrica, o executor identico e conferido no patch 1",
           not R._EXECUTOR.get("desligado")
           and "conferido=1|concordancia=1.00000|concordancia_estrutura=1.00000"
           "|estruturas=2|fracao=0.500|patch=1" in c5.texto, c5.texto[:300])
    R._EXECUTOR.update(desligado=None, redes=0)

    def sem_modulo():
        raise ImportError("sem radai_devices.py (dublado)")
    with _Troca(R, _carregar_radai_devices=sem_modulo):
        with _Calado() as c6:
            ex, mot = R._executor_pedido({"RADAI_EXECUTOR": "openvino_cpu"})
        pk = _ExecutorIgual(_RedeDeRotulos([com_estrutura]), "openvino_cpu",
                            dataset="831")
        with _Calado() as c7:
            yk = pk(x)
    checar(u"sem radai_devices: o executor pedido NAO entra, e e dito",
           ex is None and mot == u"sem regua"
           and "regua da conferencia (radai_devices) nao carregou" in c6.texto,
           (ex, mot, c6.texto[:200]))
    checar(u"  e o procurador ja montado cai para o PyTorch na primeira passada",
           _np.array_equal(yk, logits_de(com_estrutura))
           and bool(R._EXECUTOR.get("desligado")) and "regua" in c7.texto,
           c7.texto[:200])
    R._EXECUTOR.update(desligado=None, redes=0)


class _Ambiente(object):

    def __init__(self, **novos):
        self.novos, self.velhos = novos, {}

    def __enter__(self):
        for k, v in self.novos.items():
            self.velhos[k] = os.environ.get(k)
            os.environ[k] = str(v)
        return self

    def __exit__(self, *a):
        for k, v in self.velhos.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        return False


_DOIS_S = 2.0 / 60.0
_NUNCA = 10.0 ** 6

_PULSA_E_CALA = u'''
linha("Predicting part 1 of 5 ...")
for _i in range(5):
    linha("RADAI|pulso|parte=?|dataset=831|rss_mb=%d" % (900 + _i))
    time.sleep(0.2)
time.sleep(600)
'''

_PULSA_SEM_ANDAR = u'''
import threading
def _pulsar():
    n = 0
    while True:
        n += 1
        linha("RADAI|pulso|parte=?|dataset=831|rss_mb=%d|pf=%d"
              % (900 + (n % 7) * 50, n * 1000))
        time.sleep(0.2)
threading.Thread(target=_pulsar, daemon=True).start()
linha("Predicting part 1 of 5 ...")
sys.stderr.write("\\r 84%|########  | 54/64 [00:39<00:07,  1.34it/s]")
sys.stderr.flush()
time.sleep(600)
'''

_ANDA_DEVAGAR = u'''
import numpy, SimpleITK
for _i in range(12):
    sys.stderr.write("\\r %d%%|##   | %d/12 [00:0%d<00:19,  2.0s/it]"
                     % (_i * 8, _i, _i % 10))
    sys.stderr.flush()
    linha("RADAI|pulso|parte=?|dataset=831|rss_mb=900")
    time.sleep(0.5)
gravar_saida()
'''

_CALADO = u"time.sleep(600)\n"


def teste_o_pulso_parado_trava_a_task():
    secao(u"M4 · o pulso parado trava a task")
    tmp = tempfile.mkdtemp(prefix="radai_teste_runner_")
    trava = {"sem_pulso_min": _DOIS_S, "paginando_min": _NUNCA,
             "ram_pct": 95}
    try:
        with _Ambiente(RADAI_PULSO_S="0.2"):
            job = {}
            r, log, reg, dt = _rodar_task(tmp, _PULSA_E_CALA, timeout_s=60,
                                          trava=trava, envelope=True,
                                          job=job)
            checar(u"a task sem pulso levanta TaskTravada",
                   isinstance(r, getattr(M, "TaskTravada", ())),
                   repr(r)[:160])
            checar(u"  com o motivo «sem_pulso» e os numeros",
                   getattr(r, "motivo", None) == "sem_pulso"
                   and (getattr(r, "numeros", None) or {}).get(
                       "sem_pulso_s") is not None,
                   u"%s %s" % (getattr(r, "motivo", None),
                               getattr(r, "numeros", None)))
            checar(u"  em ~limite, e nao no tempo limite", dt < 20,
                   u"%.1f s" % dt)
            checar(u"  e a mensagem NAO se confunde com o tempo limite",
                   "tempo limite" not in str(r).lower()
                   and "TRAVADA" in str(r), str(r)[:200])
            f = [l for l in log if "TRAVADA" in l]
            checar(u"  e o log diz TRAVADA, o motivo e ha quanto tempo",
                   f and "sem pulso" in f[0], f[0] if f else u"sem a linha")
            checar(u"  e o job guarda o travamento (o registro de casos le)",
                   [t for t in (job.get("travamentos") or [])
                    if t.get("task") == "head_glands_cavities"
                    and t.get("motivo") == "sem_pulso"],
                   str(job.get("travamentos"))[:200])
            time.sleep(1.0)
            pids = [x.get("pid") for x in reg if x.get("pid")]
            checar(u"  e o processo da task foi encerrado",
                   pids and not any(_vivo(p) for p in pids), str(pids))
            r3, log3, _, _ = _rodar_task(tmp, _CALADO, timeout_s=60,
                                         trava=trava, envelope=True)
            checar(u"o envelope que nunca pulsou tambem trava (sem pulso "
                   u"desde o inicio)",
                   getattr(r3, "motivo", None) == "sem_pulso", repr(r3)[:140])
            r4, log4, _, _ = _rodar_task(tmp, _CALADO, timeout_s=8,
                                         trava=trava, envelope=False)
            checar(u"sem o envelope (runner direto) o silencio NAO trava por "
                   u"pulso: so o tempo limite encerra",
                   isinstance(r4, RuntimeError)
                   and not isinstance(r4, getattr(M, "TaskTravada", ()))
                   and "tempo limite" in str(r4), repr(r4)[:140])
            r2, log2, _, _ = _rodar_task(
                tmp, _PULSA_E_CALA, timeout_s=8, envelope=True,
                trava={"sem_pulso_min": _NUNCA, "paginando_min": _NUNCA,
                       "ram_pct": 95})
            checar(u"ISCA: com o limite do pulso no infinito, a mesma task "
                   u"so termina no tempo limite",
                   isinstance(r2, RuntimeError)
                   and not isinstance(r2, getattr(M, "TaskTravada", ()))
                   and "tempo limite" in str(r2), repr(r2)[:140])
    finally:
        _encerrar_os_meus()
        shutil.rmtree(tmp, ignore_errors=True)


def teste_paginando_trava_a_task():
    secao(u"M4 · paginando: sem progresso com a RAM alta trava a task")
    tmp = tempfile.mkdtemp(prefix="radai_teste_runner_")
    trava = {"sem_pulso_min": _NUNCA, "paginando_min": _DOIS_S,
             "ram_pct": 95}
    alta = (lambda: (16000.0, 300.0, 97))
    try:
        with _Ambiente(RADAI_PULSO_S="0.2"):
            r, log, reg, dt = _rodar_task(tmp, _PULSA_SEM_ANDAR, timeout_s=60,
                                          trava=trava, envelope=True,
                                          _memoria_agora=alta,
                                          MEMORIA_A_CADA_S=0)
            checar(u"sem progresso com a RAM a 97% levanta TaskTravada",
                   isinstance(r, getattr(M, "TaskTravada", ())),
                   repr(r)[:160])
            nums = getattr(r, "numeros", None) or {}
            checar(u"  com o motivo «paginando», a RAM e o tempo sem "
                   u"progresso", getattr(r, "motivo", None) == "paginando"
                   and nums.get("ram_pct") == 97
                   and nums.get("sem_progresso_s") is not None,
                   u"%s %s" % (getattr(r, "motivo", None), nums))
            checar(u"  e o pulso do envelope NAO conta como progresso (ele "
                   u"continuou, e a trava disparou assim mesmo)", dt < 20,
                   u"%.1f s" % dt)
            f = [l for l in log if "TRAVADA" in l]
            checar(u"  e o log diz a memoria e a paginacao",
                   f and "97%" in f[0] and "sem progresso" in f[0],
                   f[0] if f else u"sem a linha")
            r5, log5, _, _ = _rodar_task(
                tmp, _ANDA_DEVAGAR, timeout_s=60, envelope=True,
                trava=dict(trava, paginando_min=5.0 / 60.0),
                _memoria_agora=alta, MEMORIA_A_CADA_S=0)
            checar(u"devagar e ANDANDO (a barra muda) com a RAM alta NAO "
                   u"trava: a task termina", isinstance(r5, dict) and r5,
                   repr(r5)[:140])
            r2, _, _, _ = _rodar_task(tmp, _PULSA_SEM_ANDAR, timeout_s=8,
                                      trava=trava, envelope=True,
                                      _memoria_agora=lambda: (16000.0, 6000.0,
                                                              60),
                                      MEMORIA_A_CADA_S=0)
            checar(u"ISCA: com a RAM a 60% a mesma task so termina no tempo "
                   u"limite", isinstance(r2, RuntimeError)
                   and not isinstance(r2, getattr(M, "TaskTravada", ())),
                   repr(r2)[:140])
            juiz = getattr(M, "_JuizDaTrava", None)
            if juiz is not None:
                with _Troca(juiz, RELOGIO_DO_PROGRESSO="t_sinal"):
                    r3, _, _, _ = _rodar_task(
                        tmp, _PULSA_SEM_ANDAR, timeout_s=8, trava=trava,
                        envelope=True, _memoria_agora=alta,
                        MEMORIA_A_CADA_S=0)
                checar(u"ISCA: medindo o progresso pelo `t_sinal` (que conta "
                       u"o pulso que muda) a trava NUNCA dispara",
                       not isinstance(r3, getattr(M, "TaskTravada", ())),
                       repr(r3)[:140])
            else:
                checar(u"o juiz da trava existe (_JuizDaTrava)", False)
    finally:
        _encerrar_os_meus()
        shutil.rmtree(tmp, ignore_errors=True)


def teste_a_retomada_usa_o_plano_menor():
    secao(u"M4 · a retomada usa o plano de memoria menor")
    tmp = tempfile.mkdtemp(prefix="radai_teste_runner_")
    gpu = {"modo": "gpu", "motivo": u"gpu: dublado", "indice": 0,
           "capacidade": "6.1"}
    corpo = u"gravar_saida()\n"
    try:
        job = {}
        r, log, reg, _ = _rodar_task(tmp, corpo, device="gpu", plano=gpu,
                                     plano_menor=True, job=job)
        checar(u"tudo-na-placa com plano menor -> resultado na RAM no filho",
               reg and reg[0].get("dev") == "gpu"
               and reg[0].get("na_cpu") == "1", str(reg[:1]))
        checar(u"  e o log diz «plano menor» com o degrau",
               [l for l in log if "plano menor" in l
                and "gpu_resultado_na_cpu" in l], u"\n".join(log[-6:]))
        p = (job.get("planos") or {}).get("head_glands_cavities") or {}
        checar(u"  e o job guarda o modo que valeu e o do plano",
               p.get("modo") == "gpu_resultado_na_cpu"
               and p.get("modo_do_plano") == "gpu"
               and p.get("plano_menor") is True, str(p))
        r2, log2, reg2, _ = _rodar_task(
            tmp, corpo, device="gpu", plano=dict(gpu,
                                                 modo="gpu_resultado_na_cpu"),
            plano_menor=True)
        checar(u"rede-na-placa com plano menor -> CPU",
               reg2 and reg2[0].get("dev") == "cpu"
               and reg2[0].get("na_cpu") == "", str(reg2[:1]))
        r3, log3, reg3, _ = _rodar_task(tmp, corpo, device="cpu",
                                        plano_menor=True)
        checar(u"ja em CPU, fica em CPU, e o log diz que refaz do zero",
               reg3 and reg3[0].get("dev") == "cpu"
               and [l for l in log3 if "plano menor" in l],
               u"\n".join(log3[-4:]))
        r4, log4, reg4, _ = _rodar_task(tmp, corpo, device="gpu", plano=gpu)
        checar(u"ISCA: sem o plano menor, tudo-na-placa chega ao filho sem o "
               u"resultado na RAM", reg4 and reg4[0].get("na_cpu") == "",
               str(reg4[:1]))
    finally:
        _encerrar_os_meus()
        shutil.rmtree(tmp, ignore_errors=True)


_CONTA_E_TRAVA = u'''
import threading
_vivo = [True]
def _pulsar():
    while _vivo[0]:
        linha("RADAI|pulso|parte=?|rss_mb=900")
        time.sleep(0.2)
threading.Thread(target=_pulsar, daemon=True).start()
_cam = os.environ.get("FALSO_CONTADOR")
_c = {}
if _cam and os.path.exists(_cam):
    with open(_cam) as _f:
        _c = json.load(_f)
_c[TASK] = _c.get(TASK, 0) + 1
with open(_cam, "w") as _f:
    json.dump(_c, _f)
registrar(t=TASK, tentativa=_c[TASK])
_trava = {}
for _p in (os.environ.get("FALSO_TRAVAM") or "").split(","):
    if "=" in _p:
        _k, _v = _p.split("=", 1)
        _trava[_k.strip()] = int(_v)
if _c[TASK] <= _trava.get(TASK, 0):
    _vivo[0] = False
    time.sleep(600)
gravar_saida()
'''

_MAPA_DAS_LISTAS = {
    "total_v3": {1: "liver", 2: "spleen"},
    "head_glands_cavities": {1: "parotid_gland_left",
                             2: "parotid_gland_right"},
    "lung_vessels": {1: "lung_vessels", 2: "lung_trachea_bronchia"},
}


def _rodar_lista(tmp, tarefas, travam, device="gpu", plano=None, **kw):
    falso = _runner_falso(tmp, _CONTA_E_TRAVA)
    reg = os.path.join(tmp, "registro_%d.jsonl" % len(os.listdir(tmp)))
    cont = os.path.join(tmp, "contador_%d.json" % len(os.listdir(tmp)))
    plano = plano or {"modo": "gpu", "motivo": u"gpu: dublado", "indice": 0,
                      "capacidade": "6.1"}
    novos = dict(TS_CMD=[PY, falso], RUNNER_TS=falso,
                 TS_CLASS_MAP=_MAPA_DAS_LISTAS,
                 plano_de_dispositivo=(lambda *a, **k: dict(plano)),
                 base_eleita=(lambda modalidade="CT", **k:
                              {"CT": "total_v3", "MR": "total_mr"}.get(
                                  str(modalidade).upper())))
    jid = M._job_new()
    t0 = time.time()
    try:
        with _Ambiente(FALSO_REGISTRO=reg, FALSO_CONTADOR=cont,
                       FALSO_TRAVAM=travam, RADAI_PULSO_S="0.2"):
            with _Troca(M, **novos):
                try:
                    r = M.rodar_tasks(
                        _ref(), list(tarefas), device, jid, timeout_s=60,
                        suavizar=False,
                        trava={"sem_pulso_min": _DOIS_S,
                               "paginando_min": _NUNCA, "ram_pct": 95},
                        **kw)
                except Exception as e:
                    r = e
        return r, _log_do_job(jid), _registro(reg), time.time() - t0
    finally:
        M._job_del(jid)


def teste_a_lista_adia_a_travada_e_refaz_uma_vez():
    secao(u"M4 · a lista adia a travada e refaz uma vez (processo real)")
    tmp = tempfile.mkdtemp(prefix="radai_teste_runner_")
    rodar = getattr(M, "rodar_tasks", None)
    if rodar is None:
        checar(u"engine.rodar_tasks existe", False)
        shutil.rmtree(tmp, ignore_errors=True)
        return
    try:
        r, log, reg, dt = _rodar_lista(
            tmp, ["head_glands_cavities", "lung_vessels"],
            "head_glands_cavities=1")
        ordem = [(x.get("t"), x.get("tentativa")) for x in reg if x.get("t")]
        checar(u"a travada vai para o FIM: hgc(1), lung_vessels(1), hgc(2)",
               ordem == [("head_glands_cavities", 1), ("lung_vessels", 1),
                         ("head_glands_cavities", 2)], str(ordem))
        na_cpu = [x.get("na_cpu") for x in reg if "na_cpu" in x]
        checar(u"  e a retomada foi com o plano menor (resultado na RAM)",
               len(na_cpu) == 3 and na_cpu[0] == "" and na_cpu[2] == "1",
               str(na_cpu))
        ok = isinstance(r, dict)
        checar(u"  e a lista devolve o que rodou, sem falha",
               ok and r.get("rodaram") == ["lung_vessels",
                                           "head_glands_cavities"]
               and not r.get("falharam")
               and "parotid_gland_left" in (r.get("masks") or {}),
               repr(r)[:200] if not ok else str(r.get("rodaram")))
        trs = (r.get("travamentos") if ok else None) or []
        checar(u"  e o travamento fica registrado, com a retomada «ok»",
               len(trs) == 1 and trs[0].get("task") == "head_glands_cavities"
               and trs[0].get("retomada") == "ok"
               and trs[0].get("motivo") == "sem_pulso", str(trs)[:200])
        checar(u"  e o log diz que adiou e que refez",
               [l for l in log if "adiada para o fim" in l]
               and [l for l in log if "retomando" in l],
               u"\n".join(l for l in log if "TRAVADA" in l or "adiad" in l
                          or "retoma" in l)[:300])
        r2, log2, reg2, _ = _rodar_lista(
            tmp, ["lung_vessels", "head_glands_cavities"],
            "head_glands_cavities=9")
        checar(u"travou duas vezes (nao e base): a lista NAO levanta, e a "
               u"task vai para `falharam` com a classe «travou»",
               isinstance(r2, dict) and r2.get("rodaram") == ["lung_vessels"]
               and [f for f in r2.get("falharam") or []
                    if f.get("task") == "head_glands_cavities"
                    and f.get("classe") == "travou"],
               repr(r2)[:240])
        n_hgc = len([x for x in reg2 if x.get("t") == "head_glands_cavities"])
        checar(u"  e so UMA retomada (duas tentativas, e nao tres)",
               n_hgc == 2, u"%d tentativa(s)" % n_hgc)
        r3, log3, reg3, _ = _rodar_lista(tmp, ["total_v3", "lung_vessels"],
                                         "total_v3=9")
        checar(u"a BASE travada duas vezes levanta TaskTravada (tentativa 2)",
               isinstance(r3, getattr(M, "TaskTravada", ()))
               and getattr(r3, "tentativa", None) == 2
               and "duas vezes" in str(r3), repr(r3)[:200])
        ordem3 = [(x.get("t"), x.get("tentativa")) for x in reg3
                  if x.get("t")]
        checar(u"  depois de rodar o resto da lista (a base tambem vai para "
               u"o fim)", ordem3 == [("total_v3", 1), ("lung_vessels", 1),
                                     ("total_v3", 2)], str(ordem3))
        r4, _, reg4, _ = _rodar_lista(
            tmp, ["head_glands_cavities", "lung_vessels"],
            "head_glands_cavities=1", retomar=False)
        checar(u"ISCA: sem a retomada, a task que destravaria sai da serie",
               isinstance(r4, dict)
               and "head_glands_cavities" not in (r4.get("rodaram") or []),
               repr(r4)[:200])
    finally:
        _encerrar_os_meus()
        shutil.rmtree(tmp, ignore_errors=True)


class _RodarFalso(object):

    def __init__(self, roteiro):
        self.roteiro = dict((k, list(v)) for k, v in roteiro.items())
        self.chamadas = []

    def __call__(self, ref, task, device, jid, **kw):
        self.chamadas.append((task, dict(kw)))
        fila = self.roteiro.get(task) or ["ok"]
        efeito = fila.pop(0) if len(fila) > 1 else fila[0]
        self.roteiro[task] = fila
        if efeito == "trava":
            raise M.TaskTravada(task, "sem_pulso", {"sem_pulso_s": 900})
        if isinstance(efeito, BaseException):
            raise efeito
        return {"m_" + task: np.ones((2, 2, 2), bool)}


def teste_a_logica_da_lista():
    secao(u"M4 · a logica da lista (run_ts_task dublado)")
    if getattr(M, "rodar_tasks", None) is None:
        checar(u"engine.rodar_tasks existe", False)
        return
    ref = _ref()
    f = _RodarFalso({"total_v3": ["ok"], "trunk_cavities": ["trava", "ok"],
                     "lung_vessels": ["ok"]})
    ganchos = []

    def depois_de(task, masks, cruas):
        ganchos.append(task)
        return ["trunk_cavities"] if task == "total_v3" else []
    res = M.rodar_tasks(ref, ["total_v3", "lung_vessels"], "cpu", None,
                        rodar=f, depois_de=depois_de, timeout_s=77,
                        trava={"sem_pulso_min": 1})
    ordem = [c[0] for c in f.chamadas]
    checar(u"o gancho insere LOGO depois da base, e a retomada vai ao fim",
           ordem == ["total_v3", "trunk_cavities", "lung_vessels",
                     "trunk_cavities"], str(ordem))
    checar(u"  plano_menor so na retomada",
           [bool(c[1].get("plano_menor")) for c in f.chamadas]
           == [False, False, False, True],
           str([c[1].get("plano_menor") for c in f.chamadas]))
    checar(u"  trava e timeout_s chegam a toda chamada",
           all(c[1].get("timeout_s") == 77
               and (c[1].get("trava") or {}).get("sem_pulso_min") == 1
               for c in f.chamadas))
    checar(u"  o resultado: rodaram na ordem em que terminaram",
           res.get("rodaram") == ["total_v3", "lung_vessels",
                                  "trunk_cavities"]
           and res.get("travamentos")[0].get("retomada") == "ok",
           str(res.get("rodaram")))
    checar(u"  e as mascaras de todas", sorted(res.get("masks") or {})
           == ["m_lung_vessels", "m_total_v3", "m_trunk_cavities"],
           str(sorted(res.get("masks") or {})))
    f0 = _RodarFalso({})
    M.rodar_tasks(ref, ["total_v3", "lung_vessels"], "cpu", None, rodar=f0)
    checar(u"ISCA: sem o gancho, a task da anatomia nunca roda",
           "trunk_cavities" not in [c[0] for c in f0.chamadas])
    f2 = _RodarFalso({"lung_vessels": [M.Cancelado("pedido")]})
    try:
        M.rodar_tasks(ref, ["lung_vessels", "head_glands_cavities"], "cpu",
                      None, rodar=f2)
        subiu = False
    except M.Cancelado:
        subiu = True
    checar(u"Cancelado sobe na hora, sem retomada e sem rodar o resto",
           subiu and [c[0] for c in f2.chamadas] == ["lung_vessels"],
           str([c[0] for c in f2.chamadas]))
    f3 = _RodarFalso({"lung_vessels": [ValueError("serie ruim")]})
    r3 = M.rodar_tasks(ref, ["lung_vessels", "head_glands_cavities"], "cpu",
                       None, rodar=f3)
    checar(u"erro de task comum vai para `falharam` e a lista segue",
           r3.get("rodaram") == ["head_glands_cavities"]
           and r3["falharam"][0].get("task") == "lung_vessels"
           and "serie ruim" in r3["falharam"][0].get("erro", ""),
           str(r3.get("falharam")))
    f4 = _RodarFalso({"total_v3": [ValueError("base ruim")]})
    try:
        M.rodar_tasks(ref, ["total_v3", "lung_vessels"], "cpu", None,
                      rodar=f4)
        subiu4 = None
    except ValueError as e:
        subiu4 = e
    checar(u"erro da BASE sobe (o contrato C5)", subiu4 is not None
           and "base ruim" in str(subiu4), repr(subiu4))
    f5 = _RodarFalso({"lung_vessels": [MemoryError("sem memoria")]})
    try:
        M.rodar_tasks(ref, ["lung_vessels"], "cpu", None, rodar=f5,
                      ao_falhar=lambda t, e: isinstance(e, MemoryError))
        subiu5 = False
    except MemoryError:
        subiu5 = True
    checar(u"`ao_falhar` e a porta decidindo: True sobe (a escada do vigia)",
           subiu5)
    f6 = _RodarFalso({"lung_vessels": [ValueError("x")]})
    r6 = M.rodar_tasks(ref, ["lung_vessels"], "cpu", None, rodar=f6,
                       classificar=lambda e: "recurso")
    checar(u"`classificar` da porta vai para a classe da falha",
           r6["falharam"][0].get("classe") == "recurso",
           str(r6.get("falharam")))
    f7 = _RodarFalso({"lung_vessels": [ValueError("pedida no config")]})
    try:
        M.rodar_tasks(ref, ["lung_vessels"], "cpu", None, rodar=f7,
                      obrigatorias=("lung_vessels",))
        subiu7 = False
    except ValueError:
        subiu7 = True
    checar(u"task em `obrigatorias` sobe como a base", subiu7)


_RECORTADA = u'''
import numpy as np
import SimpleITK as sitk
img = sitk.ReadImage(ENTRADA)
a = np.zeros(sitk.GetArrayFromImage(img).shape, np.uint8)
registrar(forma=list(a.shape), origem=[float(v) for v in img.GetOrigin()])
a[1:3, 2:5, 2:5] = 1
o = sitk.GetImageFromArray(a)
o.CopyInformation(img)
sitk.WriteImage(o, SAIDA)
'''


def teste_a_task_recortada_volta_na_grade_inteira():
    secao(u"M4 · a task recortada volta na grade inteira")
    tmp = tempfile.mkdtemp(prefix="radai_teste_runner_")
    ref = _ref()
    caixa = {"task": "head_glands_cavities", "zyx": ((2, 6), (4, 12), (3, 11)),
             "ancora": "teste", "eixos": "zyx", "margem_mm": 0.0}
    try:
        cruas = {}
        r, log, reg, _ = _rodar_task(tmp, _RECORTADA, caixa=caixa,
                                     cruas=cruas, ref=ref)
        forma = [x.get("forma") for x in reg if x.get("forma")]
        checar(u"o filho recebe SO a caixa (4 x 8 x 8)",
               forma and forma[0] == [4, 8, 8], str(forma))
        orig = [x.get("origem") for x in reg if x.get("origem")]
        esperado = list(ref.TransformIndexToPhysicalPoint((3, 4, 2)))
        checar(u"  com a origem no primeiro voxel da caixa",
               orig and np.allclose(orig[0], esperado), u"%s x %s"
               % (orig[:1], esperado))
        a = getattr(cruas.get("head_glands_cavities"), "_arr", None)
        checar(u"a saida volta na grade INTEIRA da serie",
               a is not None and tuple(a.shape) == (8, 16, 16),
               str(None if a is None else a.shape))
        if a is not None and tuple(a.shape) == (8, 16, 16):
            dentro = a[3:5, 6:9, 5:8]
            checar(u"  com o rotulo no lugar certo (a caixa + o indice "
                   u"dentro dela), e nada fora", bool((dentro == 1).all())
                   and int((a == 1).sum()) == 18, u"%d voxels"
                   % int((a == 1).sum()))
        checar(u"  e o log diz o recorte",
               [l for l in log if "recortada" in l], u"\n".join(log[-6:]))
        r2, _, reg2, _ = _rodar_task(tmp, _RECORTADA, ref=ref)
        forma2 = [x.get("forma") for x in reg2 if x.get("forma")]
        checar(u"ISCA: sem a caixa, o filho recebe a serie inteira",
               forma2 and forma2[0] == [8, 16, 16], str(forma2))
    finally:
        _encerrar_os_meus()
        shutil.rmtree(tmp, ignore_errors=True)


def teste_o_pulso_diz_as_falhas_de_pagina():
    secao(u"M4 · o pulso diz as falhas de pagina")
    a = R.amostra()
    checar(u"a amostra do pulso leva pf=", "|pf=" in a, a)
    campo = [c for c in a.split("|") if c.startswith("pf=")]
    checar(u"  com um numero, ou `?`",
           campo and (campo[0][3:].isdigit() or campo[0][3:] == "?"),
           str(campo))
    L = M._LeitorDoLogTS(os.devnull, agora=0)
    L._radai(u"RADAI|pulso|parte=?|rss_mb=900|pf=12345", 5.0)
    checar(u"o leitor guarda o pf e a hora do pulso",
           L.pulso.get("pf") == "12345" and getattr(L, "t_pulso", None) == 5.0
           and getattr(L, "pulsos", 0) == 1,
           u"%s %s" % (L.pulso, getattr(L, "t_pulso", None)))
    checar(u"  e o pulso NAO e progresso (o relogio do progresso fica)",
           getattr(L, "t_progresso", None) == 0, str(getattr(L, "t_progresso",
                                                            None)))
    L._saida_ts(u"Predicting part 1 of 5 ...", 7.0)
    checar(u"  e a saida do TotalSegmentator E progresso",
           getattr(L, "t_progresso", None) == 7.0)


def teste_o_pulso_nao_cala_quando_a_medida_falha():
    secao(u"M4 · o pulso nao cala quando a medida falha")
    import threading

    def _quebra():
        raise OSError("medida quebrada")

    def _pulsar_de_antes(intervalo_s, parar):
        disse_erro = False
        while not parar.wait(intervalo_s):
            try:
                R._linha(R.MARCA + "pulso|" + R.amostra())
            except Exception as e:
                if not disse_erro:
                    disse_erro = True
                    R._linha(R.MARCA + "pulso|erro=%s: %s"
                             % (type(e).__name__, e))

    def _contar(alvo):
        linhas = []
        parar = threading.Event()
        with _Troca(R, amostra=_quebra, _linha=linhas.append):
            t = threading.Thread(target=alvo, args=(0.05, parar))
            t.start()
            time.sleep(0.6)
            parar.set()
            t.join(5)
        return linhas

    linhas = _contar(R._pulsar)
    pulsos = [l for l in linhas if l.startswith(R.MARCA + "pulso|")]
    checar(u"com a medida quebrada, o pulso continua saindo a toda volta",
           len(pulsos) >= 4, u"%d pulso(s)" % len(pulsos))
    checar(u"  e o texto do erro sai uma vez so",
           sum(1 for l in linhas if "medida quebrada" in l) == 1,
           u"\n".join(linhas[:4]))
    L = M._LeitorDoLogTS(os.devnull, agora=0)
    for k, l in enumerate(pulsos):
        L._radai(l, float(k + 1))
    checar(u"  e o leitor do motor conta cada um como pulso",
           L.pulsos == len(pulsos) and L.t_pulso == float(len(pulsos)),
           u"%s %s" % (L.pulsos, L.t_pulso))
    antes = [l for l in _contar(_pulsar_de_antes)
             if l.startswith(R.MARCA + "pulso|")]
    checar(u"ISCA: o _pulsar de antes calava depois do primeiro erro",
           len(antes) == 1, u"%d pulso(s)" % len(antes))
    ap = getattr(M, "_texto_antes_do_pulso", None)
    checar(u"a barra antes de um pulso cortado e progresso; o pulso cortado "
           u"em qualquer ponto nao",
           ap is not None and ap(b" 54/64 [00:39]RAD") == b" 54/64 [00:39]"
           and ap(b"RAD") == b"" and ap(b"RADAI|pul") == b""
           and ap(b"R") == b"" and ap(b" 54/64") == b" 54/64")
    tmp = tempfile.mkdtemp(prefix="radai_teste_runner_")
    try:
        cam = os.path.join(tmp, "log.txt")
        with open(cam, "wb") as f:
            f.write(b"RADAI|pulso|rss_mb=1\nRAD")
        L2 = M._LeitorDoLogTS(cam, agora=0)
        L2.ler(5.0)
        checar(u"  e o leitor nao conta `RAD` pendente como progresso",
               L2.t_progresso == 0 and L2.t_pulso == 5.0,
               u"%s %s" % (L2.t_progresso, L2.t_pulso))
        with open(cam, "ab") as f:
            f.write(b"AI|pulso|rss_mb=2\n\r 55/64 [00:40]")
        L2.ler(7.0)
        checar(u"  e completa o pulso na volta seguinte, e a barra nova e "
               u"progresso", L2.pulsos == 2 and L2.t_progresso == 7.0,
               u"%s %s" % (L2.pulsos, L2.t_progresso))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def teste_a_trava_efetiva_e_o_juiz():
    secao(u"M4 · a trava efetiva e o juiz, sem processo")
    te = getattr(M, "trava_efetiva", None)
    J = getattr(M, "_JuizDaTrava", None)
    if te is None or J is None:
        checar(u"engine.trava_efetiva e engine._JuizDaTrava existem", False)
        return
    p = te(None)
    checar(u"de fabrica: 15 min sem pulso, 30 min paginando, 95% de RAM",
           p == {"sem_pulso_min": 15.0, "paginando_min": 30.0,
                 "ram_pct": 95.0}, str(p))
    q = te({"sem_pulso_min": "x", "paginando_min": -3, "ram_pct": "90,5"})
    checar(u"o que nao e numero positivo cai no padrao; a virgula vale",
           q == {"sem_pulso_min": 15.0, "paginando_min": 30.0,
                 "ram_pct": 90.5}, str(q))
    tr = {"sem_pulso_min": 1.0, "paginando_min": 1.0, "ram_pct": 95}

    class _L(object):
        def __init__(self):
            self.t_pulso, self.pulsos, self.pulso = None, 0, {}
            self.t_progresso, self.t_sinal = 0.0, 0.0

    L = _L()
    j = J(tr, com_envelope=True, t0=0.0)
    checar(u"sem pulso desde o inicio: 59 s nao trava, 60 s trava",
           j.julgar(L, 59.0) is None
           and (j.julgar(L, 60.0) or (None,))[0] == "sem_pulso")
    L.t_pulso, L.pulsos = 100.0, 3
    checar(u"  e o pulso zera o relogio", j.julgar(L, 150.0) is None)
    j2 = J(tr, com_envelope=False, t0=0.0)
    L2 = _L()
    checar(u"sem o envelope nao ha regra de pulso", j2.julgar(L2, 10000.0)
           is None)
    j3 = J(tr, com_envelope=False, t0=0.0)
    alta, baixa = (16000, 300, 97), (16000, 6000, 60)
    j3.julgar(L2, 10.0, alta)
    checar(u"paginando: 60 s sem progresso mas so 50 s de RAM alta nao trava",
           j3.julgar(L2, 60.0, alta) is None)
    v = j3.julgar(L2, 70.0, alta)
    checar(u"  60 s de cada um trava, com a RAM e o tempo nos numeros",
           v is not None and v[0] == "paginando" and v[1]["ram_pct"] == 97
           and v[1]["sem_progresso_s"] == 70.0, str(v))
    j3.julgar(L2, 80.0, baixa)
    checar(u"  uma amostra abaixo do limiar zera a contagem da memoria",
           j3.julgar(L2, 100.0, alta) is None
           and j3.julgar(L2, 159.0, None) is None
           and (j3.julgar(L2, 160.0, None) or (None,))[0] == "paginando")
    j4 = J(tr, com_envelope=False, t0=0.0)
    checar(u"  sem medida de memoria, a paginacao nao decide nada",
           j4.julgar(L2, 10000.0, None) is None)
    L3 = _L()
    L3.t_sinal = 1000.0
    with _Troca(J, RELOGIO_DO_PROGRESSO="t_sinal"):
        j5 = J(tr, com_envelope=False, t0=0.0)
        j5.julgar(L3, 0.0, alta)
        v5 = j5.julgar(L3, 1030.0, alta)
    j6 = J(tr, com_envelope=False, t0=0.0)
    j6.julgar(L3, 0.0, alta)
    v6 = j6.julgar(L3, 1030.0, alta)
    checar(u"ISCA: pelo t_sinal a trava nao dispara; pelo t_progresso sim",
           v5 is None and v6 is not None and v6[0] == "paginando",
           u"%s %s" % (v5, v6))


def _conferir_registro(chamados):
    todos = set(k for k, v in globals().items()
                if k.startswith("teste_") and callable(v))
    fora = sorted(todos - set(f.__name__ for f in chamados))
    checar(u"todo teste do arquivo esta na lista do main()", not fora,
           u"nunca chamados: " + ", ".join(fora))


def main():
    print(u"test_ts_runner | o envelope, o plano de dispositivo e o vigia da "
          u"saida (sem TotalSegmentator)")
    _TESTES = (teste_o_envelope_mata_a_thread_orfa,
               teste_o_envelope_devolve_o_codigo,
               teste_o_body_seg_passa_intacto,
               teste_resultados_na_cpu_chega_ao_predictor,
               teste_sem_autocast_so_no_predictor,
               teste_as_pastas_do_nnunet_vem_antes_dos_remendos,
               teste_o_pulso_nao_inicializa_o_cuda,
               teste_o_plano_escolhe_pela_vram_livre,
               teste_o_plano_nao_abre_cuda_neste_processo,
               teste_a_capacidade_que_nao_veio_e_dita,
               teste_a_resposta_que_nao_se_le_cai_no_recuo,
               teste_a_causa_do_catalogo_nao_se_perde,
               teste_o_envelope_nao_envia_estatistica,
               teste_o_arquivo_do_ts_diz_false,
               teste_o_recuo_diz_o_que_nao_conseguiu,
               teste_a_saida_pronta_e_aproveitada,
               teste_a_saida_truncada_nao_e_aproveitada,
               teste_a_placa_cai_e_a_cpu_refaz,
               teste_o_batimento_diz_a_parte_e_a_memoria,
               teste_o_pulso_colado_na_barra_e_lido,
               teste_o_silencio_avisa_e_nao_mata,
               teste_o_fim_do_log_nao_e_so_pulso,
               teste_o_encerramento_que_falha_e_dito,
               teste_a_leitura_do_log_que_falha_e_dita,
               teste_o_nome_da_parte_segue_o_indice,
               teste_a_refeita_tem_o_tempo_inteiro,
               teste_sem_o_envelope_o_ts_roda_direto_e_diz,
               teste_a_rm_nao_vira_base_de_tc,
               teste_o_teto_de_threads_vem_antes_do_nnunet,
               teste_o_executor_troca_so_a_passada_e_confere,
               teste_o_executor_cai_para_o_pytorch,
               teste_o_ir_convertido_e_guardado,
               teste_o_executor_xpu,
               teste_sem_pedido_o_envelope_e_o_de_antes,
               teste_a_exportacao_grande_roda_no_processo,
               teste_a_regua_da_conferencia_e_a_do_canario,
               teste_o_pulso_diz_as_falhas_de_pagina,
               teste_o_pulso_nao_cala_quando_a_medida_falha,
               teste_a_trava_efetiva_e_o_juiz,
               teste_o_pulso_parado_trava_a_task,
               teste_paginando_trava_a_task,
               teste_a_retomada_usa_o_plano_menor,
               teste_a_logica_da_lista,
               teste_a_lista_adia_a_travada_e_refaz_uma_vez,
               teste_a_task_recortada_volta_na_grade_inteira)
    _conferir_registro(_TESTES)
    try:
        for t in _TESTES:
            try:
                t()
            except Exception as e:
                import traceback
                checar("%s (excecao inesperada)" % t.__name__, False,
                       "%s: %s" % (type(e).__name__, e))
                traceback.print_exc()
    finally:
        _encerrar_os_meus()

    falhas = [(n, d) for n, ok, d in _RESULTADOS if not ok]
    print("\n" + "=" * 64)
    if falhas:
        print("FALHOU: %d de %d checagens" % (len(falhas), len(_RESULTADOS)))
        for n, d in falhas:
            print("  - %s%s" % (n, ("  [%s]" % (d,)) if d else ""))
    else:
        print("OK: %d checagens, todas passaram" % len(_RESULTADOS))
    print("=" * 64)
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
