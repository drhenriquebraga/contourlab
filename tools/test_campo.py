# -*- coding: utf-8 -*-
import io
import json
import os
import shutil
import sys
import tempfile
import time

try:
    sys.stdout.reconfigure(errors="replace")
except Exception:
    pass

import numpy as np

AQUI = os.path.dirname(os.path.abspath(__file__))


def pasta_app(aqui):
    for c in (os.path.join(aqui, "..", "app"), os.path.join(aqui, "..")):
        if os.path.exists(os.path.join(c, "engine.py")):
            return os.path.abspath(c)
    return os.path.abspath(os.path.join(aqui, "..", "app"))


APP_DIR = pasta_app(AQUI)
sys.path.insert(0, APP_DIR)
sys.path.insert(0, AQUI)

os.environ["RADAI_CALIB_DIR"] = tempfile.mkdtemp(prefix="radai_campo_ac_")
os.environ["TOTALSEG_HOME_DIR"] = tempfile.mkdtemp(prefix="radai_campo_tsh_")
os.environ["RADAI_REGISTRO_DIR"] = tempfile.mkdtemp(prefix="radai_campo_reg_")
os.environ["RADAI_NOTIFICACAO"] = "0"
os.environ["RADAI_URL_VERSOES"] = "0"
os.environ["LOCALAPPDATA"] = tempfile.mkdtemp(prefix="radai_campo_lad_")
_CFG_DIR = tempfile.mkdtemp(prefix="radai_campo_cfg_")
with io.open(os.path.join(_CFG_DIR, "radai_watcher.config"), "w",
             encoding="utf-8") as _f:
    _f.write(u"ROOT=\nDRY_RUN=1\nLOG_DIR=%s\n" % _CFG_DIR)
os.environ["RADAI_CONFIG"] = os.path.join(_CFG_DIR, "radai_watcher.config")

import _cleanup
_cleanup.adotar_prefixo("radai_campo_")

import radai_falhas as F
import engine as M
import _componentes

VERBOSO = "-v" in sys.argv
_RESULTADOS = []


def checar(nome, condicao, detalhe=""):
    ok = bool(condicao)
    _RESULTADOS.append((nome, ok, detalhe))
    if VERBOSO or not ok:
        print("  %s  %s%s" % ("OK   " if ok else "FALHA", nome,
                              ("  [%s]" % (detalhe,)) if detalhe else ""))
    return ok


def secao(t):
    if VERBOSO:
        print("\n-- %s " % t + "-" * max(0, 58 - len(t)))


def temp(prefixo="radai_campo_"):
    return _cleanup.temporaria(prefixo)


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


_TB_DO_TRABALHADOR = u"""Process SpawnProcess-3:
Traceback (most recent call last):
  File "C:\\RADIOTERAPIA_AI\\LOCAL_SUITE\\python\\lib\\multiprocessing\\process.py", line 314, in _bootstrap
    self.run()
  File "C:\\RADIOTERAPIA_AI\\LOCAL_SUITE\\python\\site-packages\\nnunetv2\\inference\\data_iterators.py", line 31, in preprocess_fromfiles_save_to_queue
    data, seg, data_properties = preprocessor.run_case(list_of_lists[idx],
  File "C:\\RADIOTERAPIA_AI\\LOCAL_SUITE\\python\\site-packages\\nnunetv2\\imageio\\nibabel_reader_writer.py", line 123, in read_images
    assert len(original_affine) == 4 and len(image.shape) == 3, 'only 3d images are supported by NibabelIO'
AssertionError: only 3d images are supported by NibabelIO
"""

_TB_DO_PAI = u"""Traceback (most recent call last):
  File "C:\\RADIOTERAPIA_AI\\LOCAL_SUITE\\python\\site-packages\\totalsegmentator\\nnunet.py", line 555, in nnUNet_predict_image
    nnUNetv2_predict(tmp_dir, tmp_dir, task_id, model, folds, trainer, tta,
  File "C:\\RADIOTERAPIA_AI\\LOCAL_SUITE\\python\\site-packages\\nnunetv2\\inference\\predict_from_raw_data.py", line 476, in predict_from_data_iterator
    raise RuntimeError('Background workers died. Look for the error message further up! If there is none then your RAM was full and the worker was killed by the OS. Use fewer workers or get more RAM in that case!')
RuntimeError: Background workers died. Look for the error message further up! If there is none then your RAM was full and the worker was killed by the OS. Use fewer workers or get more RAM in that case!
"""


def _barras(n_bytes):
    partes, total, i = [], 0, 0
    while total < n_bytes:
        b = (u"\r %3d%%|%s| %d/64 [00:%02d<00:07, 1.30it/s]RADAI|pulso|"
             u"parte=2|dataset=292|rss_mb=%d\n"
             % (i % 100, u"#" * (i % 40), i % 64, i % 60, 900 + i))
        partes.append(b)
        total += len(b)
        i += 1
    return u"".join(partes)


def _log_sintetico(pasta, nome, texto):
    p = os.path.join(pasta, nome)
    with io.open(p, "w", encoding="utf-8", newline="") as f:
        f.write(texto)
    return p


def teste_a_primeira_excecao_do_filho():
    secao(u"CA-01: a primeira excecao do filho")
    d = temp()
    a = _log_sintetico(d, "a.log", u"Predicting part 1 of 5 ...\n"
                       + _TB_DO_TRABALHADOR + _barras(20 * 1024) + _TB_DO_PAI)
    p = F.primeira_excecao(a)
    u = F.ultima_excecao(a)
    checar(u"(a) a primeira e o AssertionError do trabalhador",
           p and p["tipo"] == "AssertionError"
           and u"only 3d" in p["mensagem"], p)
    checar(u"(a) o onde e o ultimo quadro, sem a pasta da instalacao",
           p and p["onde"] == u"nibabel_reader_writer.py:123 em read_images"
           and u"RADIOTERAPIA_AI" not in p["onde"], p and p["onde"])
    checar(u"(a) a ultima e o RuntimeError do pai",
           u and u["tipo"] == "RuntimeError"
           and u"Background workers died" in u["mensagem"], u)
    with io.open(a, encoding="utf-8") as f:
        texto = f.read()
    isca_ultima = F.excecoes_do_texto(texto)[-1]
    checar(u"ISCA: pegar o ULTIMO traceback le o RuntimeError, e a (a) "
           u"reprovaria", isca_ultima["tipo"] == "RuntimeError")
    isca_cauda = F.primeira_excecao(texto[-16 * 1024:])
    checar(u"ISCA: ler so os ultimos 16 KB nao acha o AssertionError",
           not isca_cauda or isca_cauda["tipo"] != "AssertionError",
           isca_cauda)
    b = _log_sintetico(d, "b.log", _barras(4096) + _TB_DO_PAI)
    pb, ub = F.primeira_excecao(b), F.ultima_excecao(b)
    checar(u"(b) so o Background workers died: a primeira e a ultima",
           pb and ub and pb["tipo"] == ub["tipo"] == "RuntimeError"
           and pb["mensagem"] == ub["mensagem"], (pb, ub))
    c = _log_sintetico(d, "c.log", _barras(4096) + u"Killed\n")
    checar(u"(c) log sem traceback: primeira None",
           F.primeira_excecao(c) is None)
    e = F.FalhaDaTask("total_v3", codigo=1, primeira=None, ultima=None,
                      cauda=u"Killed")
    checar(u"(c) sem traceback, a frase cai no codigo de saida",
           u"saiu com codigo 1" in str(e) and u"Primeira" not in str(e),
           str(e))
    e = F.FalhaDaTask("total_v3", codigo=1, primeira=p, ultima=u)
    checar(u"a frase diz a primeira, com o onde, e a ultima",
           str(e).startswith(u"TS total_v3 saiu com codigo 1. Primeira "
                             u"excecao: AssertionError: only 3d images are "
                             u"supported by NibabelIO (nibabel_reader_writer"
                             u".py:123 em read_images).")
           and u"Ultima: RuntimeError: Background workers died" in str(e),
           str(e)[:300])
    d2 = temp()
    falso = _escrever_falso(d2, u"sys.stdout.write(%r)\nsys.stdout.write(%r)\n"
                                u"sys.stdout.write(%r)\nsys.exit(1)\n"
                            % (_TB_DO_TRABALHADOR, _barras(20 * 1024),
                               _TB_DO_PAI))
    r, log = _rodar_com_falso(falso, "total_v3")
    checar(u"pelo envelope falso: run_ts_task levanta FalhaDaTask",
           isinstance(r, F.FalhaDaTask) and isinstance(r, M.FalhaDaTask),
           repr(r)[:200])
    checar(u"  com a primeira certa e o codigo 1",
           isinstance(r, F.FalhaDaTask) and r.codigo == 1
           and (r.primeira or {}).get("tipo") == "AssertionError",
           getattr(r, "primeira", None))
    checar(u"  e o fim do log vai ao log da serie",
           any(u"fim do log" in l and u"Background workers died" in l
               for l in log), log[-6:])


_FALSO = u'''# -*- coding: utf-8 -*-
import json, os, sys, time
args = sys.argv[1:]
def arg(nome):
    return args[args.index(nome) + 1] if nome in args else None
ENTRADA, SAIDA, TASK = arg("-i"), arg("-o"), arg("--task")
CONTA = os.environ.get("FALSO_CONTADOR")
if CONTA:
    with open(CONTA, "a") as f:
        f.write(TASK + "\\n")
def gravar(rotulos):
    import numpy as np
    import SimpleITK as sitk
    img = sitk.ReadImage(ENTRADA)
    a = np.zeros(sitk.GetArrayFromImage(img).shape, np.uint8)
    for valor, fatia in rotulos:
        a[fatia] = valor
    o = sitk.GetImageFromArray(a)
    o.CopyInformation(img)
    sitk.WriteImage(o, SAIDA)
'''


def _escrever_falso(pasta, corpo):
    p = os.path.join(pasta, "ts_falso_%d.py" % len(os.listdir(pasta)))
    with io.open(p, "w", encoding="utf-8") as f:
        f.write(_FALSO + corpo)
    return p


def _volume(forma=(8, 16, 16), esp=(2.0, 2.0, 3.0), direcao=None):
    import SimpleITK as sitk
    v = sitk.GetImageFromArray(np.zeros(forma, dtype=np.int16))
    v.SetSpacing(esp)
    if direcao is not None:
        v.SetDirection(direcao)
    return v


def _rodar_com_falso(falso, task, mapa=None, vol=None, contador=None, **kw):
    mapa = mapa or {M._nome_biblioteca(task): {1: "liver", 2: "spleen"}}
    novos = dict(TS_CMD=[sys.executable, falso], TS_CLASS_MAP=mapa,
                 base_eleita=lambda modalidade="CT", **k: None)
    velho = os.environ.get("FALSO_CONTADOR")
    if contador:
        os.environ["FALSO_CONTADOR"] = contador
    jid = M._job_new()
    try:
        with _Troca(M, **novos):
            try:
                r = M.run_ts_task(vol if vol is not None else _volume(), task,
                                  "cpu", jid, timeout_s=60, suavizar=False,
                                  recorte_no_corpo=False, **kw)
            except Exception as e:
                r = e
        return r, list(M._job(jid).get("log") or [])
    finally:
        if contador:
            if velho is None:
                os.environ.pop("FALSO_CONTADOR", None)
            else:
                os.environ["FALSO_CONTADOR"] = velho
        M._job_del(jid)


def _falha_com(tipo, msg, onde=u"x.py:1 em f", codigo=1, task="total_v3"):
    p = {"tipo": tipo, "mensagem": msg, "onde": onde, "bloco": u""}
    return F.FalhaDaTask(task, codigo=codigo, primeira=p, ultima=p)


def teste_uma_classificacao_so():
    secao(u"CA-02: uma classificacao so, com INELEGIVEL e INDETERMINADA")
    bwd = (u"Background workers died. Look for the error message further up! "
           u"If there is none then your RAM was full and the worker was "
           u"killed by the OS.")
    tabela = [
        (u"NibabelIO na primeira",
         _falha_com("AssertionError", u"only 3d images are supported by "
                    u"NibabelIO", u"nibabel_reader_writer.py:123 em "
                    u"read_images"), F.INELEGIVEL),
        (u"so o Background workers died", _falha_com("RuntimeError", bwd),
         F.INDETERMINADA),
        (u"DefaultCPUAllocator", _falha_com(
            "RuntimeError", u"DefaultCPUAllocator: not enough memory: you "
            u"tried to allocate 9122542992 bytes."), F.RECURSO),
        (u"TaskTravada", M.TaskTravada("abdominal_muscles", "sem_pulso", {}),
         F.TRAVOU),
        (u"ValueError qualquer", ValueError(u"quebrou"), F.DETERMINISTICO),
        (u"SerieNaoContornavel", F.SerieNaoContornavel(u"imagem colorida"),
         F.INELEGIVEL),
        (u"RecursoPrevisto", F.RecursoPrevisto("abdominal_muscles", 31000,
                                               9000, 11000), F.RECURSO),
        (u"o tempo limite", F.FalhaDaTask(
            "total_v3", frase=u"TS total_v3 passou do tempo limite (10800 s) "
            u"e foi encerrada.", tempo_limite=True), F.TRAVOU),
        (u"MemoryError", MemoryError(), F.RECURSO),
        (u"a frase no texto (o tipo perdido)", RuntimeError(
            u"TS total_v3 saiu com codigo 1. Primeira excecao: "
            u"AssertionError: only 3d images are supported by NibabelIO "
            u"(nibabel_reader_writer.py:123 em read_images). Ultima: "
            u"RuntimeError: " + bwd), F.INELEGIVEL),
    ]
    for nome, e, esperado in tabela:
        checar(u"%s -> %s" % (nome, esperado),
               F.classificar_falha(e) == esperado, F.classificar_falha(e))
    checar(u"o motor reexporta a mesma funcao",
           M.classificar_falha is F.classificar_falha
           and M._classe_da_falha(tabela[0][1]) == F.INELEGIVEL)
    import importlib
    W = importlib.import_module("radai_watcher")
    iguais = [n for n, e, _x in tabela
              if W.classificar_erro(e) != M._classe_da_falha(e)]
    checar(u"o vigia e o motor devolvem o mesmo para a tabela inteira",
           not iguais, iguais)
    checar(u"o vigia tem as constantes novas",
           W.INELEGIVEL == F.INELEGIVEL and W.INDETERMINADA == F.INDETERMINADA)

    def isca(e):
        t = str(e).lower()
        if "ram was full" in t:
            return F.RECURSO
        return F.classificar_falha(e)
    checar(u"ISCA: ler «RAM was full» como recurso reprova a linha do "
           u"Background workers died", isca(tabela[1][1]) != F.INDETERMINADA)

    a1 = _falha_com("RuntimeError", u"DefaultCPUAllocator: not enough memory:"
                    u" you tried to allocate 9122542992 bytes.",
                    u"predict_from_raw_data.py:639 em predict_sliding_window")
    a2 = _falha_com("RuntimeError", u"DefaultCPUAllocator: not enough memory:"
                    u" you tried to allocate 3647832384 bytes.",
                    u"predict_from_raw_data.py:639 em predict_sliding_window")
    checar(u"mesma causa, numeros diferentes: mesma assinatura",
           F.assinatura_da_falha(a1) == F.assinatura_da_falha(a2)
           and len(F.assinatura_da_falha(a1)) == 10,
           (F.assinatura_da_falha(a1), F.assinatura_da_falha(a2)))
    c1 = RuntimeError(u"serie quebrou no processo 1234 em "
                      u"C:\\pacientes\\FULANO\\CT_1\\x.dcm")
    c2 = RuntimeError(u"serie quebrou no processo 98765 em "
                      u"D:\\outra\\BELTRANO\\CT_2\\y.dcm")
    checar(u"mesma causa, PID e caminho diferentes: mesma assinatura",
           F.assinatura_da_falha(c1) == F.assinatura_da_falha(c2))
    checar(u"causas diferentes: assinaturas diferentes",
           F.assinatura_da_falha(tabela[0][1])
           != F.assinatura_da_falha(tabela[1][1])
           != F.assinatura_da_falha(a1))
    import hashlib

    def isca_pid(e):
        return hashlib.sha1(str(e).encode("utf-8")).hexdigest()[:10]
    checar(u"ISCA: a assinatura com o numero dentro reprova a igualdade",
           isca_pid(c1) != isca_pid(c2))
    checar(u"a frase curta nao leva caminho",
           u"FULANO" not in F.frase_curta(c1)
           and u"<caminho>" in F.frase_curta(c1), F.frase_curta(c1))


_SAGITAL = (0.0, 0.0, -1.0, 1.0, 0.0, 0.0, 0.0, -1.0, 0.0)


def _rgb(forma=(8, 16, 16)):
    import SimpleITK as sitk
    v = sitk.GetImageFromArray(np.zeros(forma + (3,), dtype=np.uint8),
                               isVector=True)
    v.SetSpacing((1.0, 1.0, 3.0))
    return v


def _tela_traduzivel(frase):
    import re
    import radai_phrases as P
    d = P.construir()
    f = P.normalizar(frase)
    for k in d["en"]:
        if u"%s" not in k and u"%d" not in k:
            continue
        rx = u"^" + u"(.+?)".join(re.escape(p) for p in re.split(r"%s|%d", k)) + u"$"
        if re.match(rx, f) and all(d[c].get(k) for c in P.CODIGOS):
            return True
    return False


def teste_o_volume_tem_de_ser_contornavel():
    secao(u"CA-03: o volume tem de ser contornavel antes da inferencia")
    casos = [(u"(a) RGB de 3 componentes", _rgb(), u"colorida"),
             (u"(b) a direcao de um sagital", _volume(direcao=_SAGITAL),
              u"sagital"),
             (u"volume de 1 corte", _volume(forma=(1, 16, 16)), u"corte")]
    for nome, vol, palavra in casos:
        try:
            M.conferir_volume_contornavel(vol, min_cortes=5)
            r = None
        except F.SerieNaoContornavel as e:
            r = e
        checar(u"%s: recusado com o motivo em portugues" % nome,
               r is not None and palavra in str(r), r)
        checar(u"  TEL-11: e a frase da tela casa um molde com as onze traduções",
               r is not None and _tela_traduzivel(getattr(r, "tela", u"")),
               getattr(r, "tela", None))
    try:
        M.conferir_volume_contornavel(_volume(), min_cortes=5)
        ok = True
    except Exception as e:
        ok = e
    checar(u"(c) axial de 1 canal passa", ok is True, ok)
    checar(u"  (isca) o motivo cru do log (sem acento) não casa molde nenhum",
           not _tela_traduzivel(u"a serie e uma imagem colorida (3 componentes "
                                u"por pixel) — captura de tela ou laudo —, e nao "
                                u"uma TC/RM de contorno"))
    import radai_batch as _B
    _fb = io.open(_B.__file__, encoding="utf-8").read()
    checar(u"  e o «Rodar agora» põe no cartão a frase da tela, e não o motivo do log",
           u'getattr(e, "tela", None) or _mot' in _fb)
    d = temp()
    conta = os.path.join(d, "contador.txt")
    falso = _escrever_falso(d, u"gravar([(1, (slice(2, 6), slice(3, 9), "
                               u"slice(3, 9)))])\n")
    for nome, vol in ((u"RGB", _rgb()), (u"sagital", _volume(direcao=_SAGITAL))):
        r, log = _rodar_com_falso(falso, "total_v3", vol=vol, contador=conta)
        checar(u"run_ts_task recusa o %s, e o envelope NAO e chamado" % nome,
               isinstance(r, F.SerieNaoContornavel)
               and not os.path.exists(conta), repr(r)[:160])
    r, log = _rodar_com_falso(falso, "total_v3", contador=conta)
    checar(u"o axial roda no falso (o contador prova que a isca discrimina)",
           isinstance(r, dict) and os.path.exists(conta), repr(r)[:160])
    checar(u"a classe da recusa e inelegivel",
           F.classificar_falha(F.SerieNaoContornavel(u"x")) == F.INELEGIVEL)


def teste_a_rm_segmenta_em_qualquer_orientacao():
    secao(u"v8.5: na RM qualquer orientacao; na TC so o axial; colorida, 4D e "
          u"volume curto recusados para todas")
    import SimpleITK as sitk
    sag = _volume(direcao=_SAGITAL)

    def _recusa(vol, **kw):
        try:
            M.conferir_volume_contornavel(vol, min_cortes=5, **kw)
            return None
        except F.SerieNaoContornavel as e:
            return e
    checar(u"RM sagital passa", _recusa(sag, modalidade="MR") is None)
    checar(u"  e com o nome da modalidade em portugues tambem",
           _recusa(sag, modalidade="RM") is None)
    checar(u"TC sagital e recusada", _recusa(sag, modalidade="CT") is not None)
    checar(u"sem modalidade (os chamadores de antes): o sagital continua "
           u"recusado", _recusa(sag) is not None)
    v4 = sitk.Image([16, 16, 8, 3], sitk.sitkInt16)
    for nome, vol in ((u"colorida", _rgb()), (u"4D", v4),
                      (u"curta", _volume(forma=(1, 16, 16)))):
        checar(u"RM %s e recusada" % nome,
               _recusa(vol, modalidade="MR") is not None)
    checar(u"a task de RM e da RM no catalogo (e a de TC, da TC)",
           M.modalidade_da_task("total_mr") == "MR"
           and M.modalidade_da_task("total_v3") == "CT")
    d = temp()
    conta = os.path.join(d, "contador_rm.txt")
    falso = _escrever_falso(d, u"gravar([(1, (slice(2, 6), slice(3, 9), "
                               u"slice(3, 9)))])\n")
    r, _log = _rodar_com_falso(falso, "total_mr", vol=sag, contador=conta)
    checar(u"run_ts_task da total_mr roda a RM sagital (o envelope e chamado)",
           isinstance(r, dict) and os.path.exists(conta), repr(r)[:160])
    if os.path.exists(conta):
        os.remove(conta)
    velho = M.modalidade_da_task
    M.modalidade_da_task = lambda task: "CT"
    try:
        r2, _l2 = _rodar_com_falso(falso, "total_mr", vol=sag, contador=conta)
    finally:
        M.modalidade_da_task = velho
    checar(u"ISCA: tomada como TC, a mesma RM sagital e recusada antes do "
           u"envelope", isinstance(r2, F.SerieNaoContornavel)
           and not os.path.exists(conta), repr(r2)[:160])
    import radai_triage as TR
    checar(u"triagem: o sagital da RM nao e recusado; o da TC e",
           not TR.orientacao_recusada({"axial": False, "modalidade": "MR"})
           and TR.orientacao_recusada({"axial": False, "modalidade": "CT"})
           and TR.orientacao_recusada({"axial": False}))
    checar(u"  e a RM colorida continua fora do volume de contorno",
           TR._nao_e_volume_de_contorno({"axial": False, "modalidade": "MR",
                                         "colorida": True})
           and not TR._nao_e_volume_de_contorno({"axial": False,
                                                 "modalidade": "MR"}))


def _tw():
    import importlib
    return importlib.import_module("test_watcher")


def _motor_que_le(TW, base, volume):
    class _Motor(TW._MotorQueEntrega):
        def load_sitk(self, pasta):
            return volume

        def conferir_volume_contornavel(self, img, min_cortes=None,
                                        modalidade=None):
            return M.conferir_volume_contornavel(img, min_cortes=min_cortes,
                                                 modalidade=modalidade)
    return _Motor(base)


def _serie_no_vigia(TW, motor_de, n=8, pid="PAC_CAMPO", extra=None,
                    pids=None):
    from datetime import datetime, timedelta
    agora = datetime.now()
    cfg = {"DRY_RUN": "0", "TASKS": "total_v3", "RECORTE_NO_CORPO": "0"}
    cfg.update(extra or {})
    lista = [(p, agora - timedelta(days=1 + i), n)
             for i, p in enumerate(pids or [pid])]
    mod, root, base = TW.montar(lista, extra=cfg)
    TW.envelhecer(root, 60)
    fila, _ = TW.fila_de(mod)
    motor = motor_de(base)
    mod.carregar_engine = lambda: motor
    return mod, root, base, fila, motor


def _processar(mod, s, linhas=None):
    velho = mod.wlog

    def _wlog(m=""):
        if linhas is not None:
            linhas.append(str(m))
    mod.wlog = _wlog
    try:
        mod.claim(s["dir"], s["uid"], {"machine": "PC_A",
                                       "pid_os": os.getpid()})
        return mod.process_series(s)
    finally:
        mod.wlog = velho


def teste_a_serie_nao_contornavel_sai_da_fila():
    secao(u"CA-03: a serie nao contornavel sai da fila")
    TW = _tw()
    mod, root, base, fila, motor = _serie_no_vigia(
        TW, lambda b: _motor_que_le(TW, b, _rgb()))
    if not fila:
        checar(u"a serie entrou na fila", False)
        return
    s = fila[0]
    linhas = []
    ok = _processar(mod, s, linhas)
    fl = mod.read_marker(s["dir"], s["uid"], "fail") or {}
    checar(u"a serie colorida NAO sai, e nenhuma task rodou",
           ok is False and motor.tasks == [], (ok, motor.tasks))
    checar(u"o `fail` diz inelegivel, com o motivo e a assinatura, e SEM "
           u"tentativa", fl.get("inelegivel") and u"colorida" in
           fl.get("inelegivel") and len(str(fl.get("assinatura") or "")) == 10
           and int(fl.get("tries", 0) or 0) == 0, fl)
    checar(u"o log diz RECUSADA, uma vez, e que nao volta",
           len([l for l in linhas if u"RECUSADA serie" in l]) == 1
           and any(u"nao volta a fila" in l for l in linhas),
           [l for l in linhas if u"RECUSADA" in l])
    checar(u"  e sem traceback", not any(u"Traceback" in l for l in linhas))
    fila2, _ = TW.fila_de(mod)
    checar(u"a varredura seguinte NAO a oferece",
           not [x for x in fila2 if x["uid"] == s["uid"]],
           [x["uid"][-8:] for x in fila2])
    checar(u"e ela esta em NAO_CONTORNAVEIS, com o motivo, e nao nas puladas",
           [x for x in mod.NAO_CONTORNAVEIS if x["uid"] == s["uid"]
            and u"colorida" in x.get("motivo", u"")]
           and not [x for x in mod.PULADAS_POR_FALHA
                    if x["uid"] == s["uid"]], mod.NAO_CONTORNAVEIS)
    checar(u"o estado do painel conta as nao contornaveis",
           mod.STATE.get("nao_contornaveis") == 1,
           mod.STATE.get("nao_contornaveis"))
    r = mod.liberar_falhas()
    fila3, _ = TW.fila_de(mod)
    checar(u"«Liberar» a devolve a fila",
           [x for x in fila3 if x["uid"] == s["uid"]] and r.get("liberadas"),
           (r, [x["uid"][-8:] for x in fila3]))
    checar(u"ISCA: gravar tentativa poria tries 1 -- a checagem acima pede 0",
           int(fl.get("tries", 0) or 0) != 1)


def teste_o_que_saiu_da_fila_aparece_com_o_motivo():
    secao(u"CA-03/CA-05: o que saiu da fila aparece com o motivo")
    TW = _tw()
    mod, root, base, fila, motor = _serie_no_vigia(
        TW, lambda b: _motor_que_le(TW, b, _rgb()))
    if not fila:
        checar(u"a serie entrou na fila", False)
        return
    s = fila[0]
    _processar(mod, s, [])
    TW.fila_de(mod)
    fora = mod.fora_da_fila()
    nc = fora.get("nao_contornaveis") or []
    checar(u"a serie nao contornavel vem uma a uma, com o motivo",
           len(nc) == 1 and nc[0].get("uid8") == s["uid"][-8:]
           and u"colorida" in nc[0].get("motivo", u""), nc)
    texto = json.dumps(fora, ensure_ascii=False)
    checar(u"  sem a pasta e sem o UID inteiro",
           s["uid"] not in texto and str(s["dir"]) not in texto
           and os.path.basename(str(root)) not in texto, texto[:200])
    del mod.EM_ESPERA[:]
    mod.EM_ESPERA.extend([
        {"dir": "x1", "uid": "1.2.3.111", "pid": "P1", "assinatura": "a" * 10,
         "frase": u"RuntimeError: Background workers died"},
        {"dir": "x2", "uid": "1.2.3.222", "pid": "P2", "assinatura": "a" * 10,
         "frase": u"RuntimeError: Background workers died"},
        {"dir": "x3", "uid": "1.2.3.333", "pid": "P3", "assinatura": "b" * 10,
         "frase": u"ValueError: outra"}])
    with mod.LOCK:
        mod.STATE["alertas_de_assinatura"] = []
    g = {x["assinatura"]: x for x in mod.fora_da_fila().get("em_espera")
         or []}
    checar(u"em espera: agrupada pela assinatura, com o numero de series DE "
           u"CADA grupo e a frase",
           g.get("a" * 10, {}).get("series") == 2
           and g.get("b" * 10, {}).get("series") == 1
           and u"Background" in g.get("a" * 10, {}).get("frase", u""), g)
    del mod.EM_ESPERA[:]
    rotas = set(getattr(r, "path", "") for r in mod.app.routes)
    checar(u"a rota do que saiu da fila existe", "/api/fora_da_fila" in rotas)
    import radai_todo as TD
    fonte_td = io.open(_componentes.fonte("app/radai_todo.py"),
                       encoding="utf-8").read()
    checar(u"a barra da direita pede a rota, desenha por uiHTML e tem o "
           u"«Liberar»",
           u"fetch('/api/fora_da_fila')" in fonte_td
           and u'id="radai_fora_fila"' in fonte_td
           and u"radaiForaDaFila" in fonte_td and u"uiHTML" in fonte_td
           and u"/api/liberar_falhas" in fonte_td)
    fonte_pn = io.open(_componentes.fonte("app/radai_panel.py"),
                       encoding="utf-8").read()
    checar(u"o /config nao conta o total em espera como «a mesma falha»",
           u"String(d.em_espera)" not in fonte_pn, u"")
    del TD


def _mexer_na_serie(root, pid, **tags):
    import pydicom
    for d, _x, fs in os.walk(os.path.join(root, pid)):
        for f in fs:
            if not f.lower().endswith(".dcm"):
                continue
            p = os.path.join(d, f)
            ds = pydicom.dcmread(p)
            for k, v in tags.items():
                if v is None:
                    if k in ds:
                        delattr(ds, k)
                else:
                    setattr(ds, k, v)
            ds.save_as(p)


def teste_a_triagem_ve_orientacao_e_cor():
    secao(u"CA-09: a triagem do vigia ve orientacao, cor e SECONDARY")
    import radai_triage as TR
    checar(u"axial [1,0,0,0,1,0] e axial; sagital [0,1,0,0,0,-1] nao; "
           u"sem a tag, nao sei",
           TR.orientacao_axial([1, 0, 0, 0, 1, 0]) is True
           and TR.orientacao_axial([0, 1, 0, 0, 0, -1]) is False
           and TR.orientacao_axial(None) is None)
    TW = _tw()
    pids = ["PAC_AXIAL", "PAC_SAGITAL", "PAC_RGB", "PAC_SECUNDARIA",
            "PAC_SEM_TAGS", "PAC_DERIVADA"]
    from datetime import datetime, timedelta
    agora = datetime.now()
    mod, root, base = TW.montar([(p, agora - timedelta(days=1 + i), 8)
                                 for i, p in enumerate(pids)])
    _mexer_na_serie(root, "PAC_AXIAL", ImageType=["ORIGINAL", "PRIMARY",
                                                  "AXIAL"])
    _mexer_na_serie(root, "PAC_SAGITAL",
                    ImageOrientationPatient=[0, 1, 0, 0, 0, -1])
    _mexer_na_serie(root, "PAC_RGB", SamplesPerPixel=3,
                    PhotometricInterpretation="RGB")
    _mexer_na_serie(root, "PAC_SECUNDARIA", ImageType=["DERIVED",
                                                       "SECONDARY"])
    _mexer_na_serie(root, "PAC_SEM_TAGS", ImageOrientationPatient=None)
    _mexer_na_serie(root, "PAC_DERIVADA", ImageType=["DERIVED", "PRIMARY",
                                                     "AXIAL"])
    TW.envelhecer(root, 60)
    series, done = mod.scan_root()
    fila = mod.build_queue(series, done)
    na_fila = sorted(s["pid"] for s in fila)
    checar(u"so o axial, o sem tags e o DERIVED\\PRIMARY entram na fila",
           na_fila == ["PAC_AXIAL", "PAC_DERIVADA", "PAC_SEM_TAGS"], na_fila)
    por_pid = dict((s["pid"], s) for s in series.values())
    checar(u"o registro da varredura leva axial, colorida e secundaria",
           por_pid.get("PAC_SAGITAL", {}).get("axial") is False
           and por_pid.get("PAC_RGB", {}).get("colorida") is True
           and por_pid.get("PAC_SECUNDARIA", {}).get("secundaria") is True
           and por_pid.get("PAC_AXIAL", {}).get("axial") is True
           and por_pid.get("PAC_SEM_TAGS", {}).get("axial") is None,
           dict((p, (r.get("axial"), r.get("colorida"), r.get("secundaria")))
                for p, r in por_pid.items()))
    sem = dict((u, dict((k, v) for k, v in r.items()
                        if k not in ("axial", "colorida", "secundaria")))
               for u, r in series.items())
    isca = sorted(r["pid"] for u, r in sem.items()
                  if u in TR.escolher_simulacao(sem))
    checar(u"ISCA: sem passar as tags a triagem, o sagital entra",
           "PAC_SAGITAL" in isca, isca)


def teste_ausencia_anatomica_nao_e_falha():
    secao(u"CA-04: ausencia anatomica nao e falha")
    d = temp()
    vazio_crop = _escrever_falso(d, u"print('INFO: Crop is empty. Returning "
                                    u"empty segmentation.')\ngravar([])\n")
    vazio = _escrever_falso(d, u"gravar([])\n")
    mapa = {"oculomotor_muscles": {1: "eye_muscle_lateral_rectus_left"},
            "head_glands_cavities": {1: "parotid_gland_left"}}
    r, log = _rodar_com_falso(vazio_crop, "oculomotor_muscles", mapa=mapa)
    checar(u"(a) com «Crop is empty»: {} e o motivo do localizador",
           isinstance(r, dict) and not r and u"localizador" in
           (getattr(r, "ausencia", u"") or u""), repr(r)[:200])
    checar(u"  e o log diz ausencia anatomica, nao falha",
           any(u"nenhuma estrutura no campo" in l and u"ausencia anatomica"
               in l for l in log), log[-4:])
    r, log = _rodar_com_falso(vazio, "head_glands_cavities", mapa=mapa)
    checar(u"(b) sem a frase: {} e o outro motivo",
           isinstance(r, dict) and not r and u"nao achou estrutura" in
           (getattr(r, "ausencia", u"") or u""), repr(r)[:200])
    r, log = _rodar_com_falso(vazio, "total_v3",
                              mapa={"total_v3": {1: "liver"}})
    checar(u"(c) a BASE vazia levanta", isinstance(r, Exception)
           and u"nenhuma estrutura" in str(r), repr(r)[:200])

    def _rodar(ref, t, dev, jid, **kw):
        if t == "total_v3":
            return {"liver": np.ones((2, 2, 2), bool)}
        return M.SemEstrutura(u"o localizador da task nao achou a regiao "
                              u"dela no campo")
    jid = M._job_new()
    try:
        res = M.rodar_tasks(_volume(), ["total_v3", "oculomotor_muscles"],
                            "cpu", jid, rodar=_rodar, portao=False)
    finally:
        M._job_del(jid)
    checar(u"rodar_tasks devolve `ausentes`, e a ausente nao entra em "
           u"falharam nem some de rodaram",
           [a.get("task") for a in res.get("ausentes") or []]
           == ["oculomotor_muscles"] and not res.get("falharam")
           and "oculomotor_muscles" in res.get("rodaram"), res.get("ausentes"))


def teste_a_ausente_no_vigia_sai_ok():
    secao(u"CA-04: a serie com task vazia sai pelo vigia")
    TW = _tw()

    class _Vazia(TW._MotorAnatomico):
        def run_ts_task(self, ref, t, device=None, jid=None, timeout_s=None,
                        cruas=None, **kw):
            if t == "breasts":
                self.tasks.append(t)
                return M.SemEstrutura(u"a task rodou e nao achou estrutura "
                                      u"no campo")
            return TW._MotorAnatomico.run_ts_task(
                self, ref, t, device=device, jid=jid, timeout_s=timeout_s,
                cruas=cruas, **kw)
    ok, motor, mod, s, linhas = TW._rodar_anatomia({"torax"},
                                                   motor_cls=_Vazia)
    done = (mod.read_marker(s["dir"], s["uid"], "done") or {}) if s else {}
    checar(u"a serie sai OK", ok is True, (ok, linhas[-3:]))
    checar(u"  e o `done` leva tasks_sem_estrutura com o motivo",
           [x.get("task") for x in done.get("tasks_sem_estrutura") or []]
           == ["breasts"], done.get("tasks_sem_estrutura"))
    checar(u"  e NAO a poe em tasks_falharam",
           not [f for f in done.get("tasks_falharam") or []
                if f.get("task") == "breasts"], done.get("tasks_falharam"))


def _anatomia_sintetica(regioes):
    forma = (60, 64, 64)
    m = {}

    def bloco(z0, z1):
        a = np.zeros(forma, bool)
        a[z0:z1, 10:50, 10:50] = True
        return a
    if "torax" in regioes:
        m["lung_left"], m["lung_right"] = bloco(10, 40), bloco(10, 40)
        m["heart"] = bloco(15, 25)
    if "cabeca" in regioes:
        m["brain"] = bloco(40, 58)
        m["skull"] = bloco(38, 59)
    if "figado" in regioes:
        m["liver"] = bloco(2, 12)
    return m, forma


def teste_o_portao_da_regiao_nas_duas_portas():
    secao(u"CA-10: o portao de regiao de cada task, no motor")
    import radai_geom as G
    torax, forma = _anatomia_sintetica({"torax"})
    cabeca, _f = _anatomia_sintetica({"cabeca", "torax"})
    vol = _volume(forma=forma, esp=(2.0, 2.0, 3.0))
    grade = G.Grade.de_sitk(vol)
    for t in ("oculomotor_muscles", "teeth", "liver_segments", "hip_implant"):
        motivo = M.portao_da_regiao(t, torax, grade=grade)
        checar(u"torax sem cabeca: `%s` pulada, com a frase" % t,
               motivo and u"a regiao da task nao esta no campo" in motivo,
               motivo)
    for t in ("oculomotor_muscles", "teeth"):
        checar(u"cabeca no campo: `%s` roda" % t,
               M.portao_da_regiao(t, cabeca, grade=grade) is None,
               M.portao_da_regiao(t, cabeca, grade=grade))
    checar(u"task sem portao (a base, a do torax com torax) roda",
           M.portao_da_regiao("total_v3", torax, grade=grade) is None
           and M.portao_da_regiao("trunk_cavities", torax,
                                  grade=grade) is None)
    checar(u"sem anatomia nenhuma (na duvida) roda",
           M.portao_da_regiao("oculomotor_muscles", {}, grade=grade) is None)
    rodou = []

    def _rodar(ref, t, dev, jid, **kw):
        rodou.append(t)
        if t == "total_v3":
            return dict(torax)
        return {}
    jid = M._job_new()
    try:
        res = M.rodar_tasks(vol, ["total_v3", "oculomotor_muscles", "teeth"],
                            "cpu", jid, rodar=_rodar)
    finally:
        M._job_del(jid)
    checar(u"o primitivo pula as duas sem antes_de nenhum",
           rodou == ["total_v3"] and sorted(p["task"] for p in res["puladas"])
           == ["oculomotor_muscles", "teeth"], (rodou, res.get("puladas")))
    import radai_batch as B
    fonte = io.open(_componentes.fonte("app/radai_batch.py"),
                    encoding="utf-8").read()
    checar(u"o «Rodar agora» chama o primitivo do motor (o portao vem junto)",
           u"engine.rodar_tasks(" in fonte and u"portao=False" not in fonte)
    rodou[:] = []
    jid = M._job_new()
    try:
        res = M.rodar_tasks(vol, ["total_v3", "oculomotor_muscles"], "cpu",
                            jid, rodar=_rodar, portao=False)
    finally:
        M._job_del(jid)
    checar(u"ISCA: sem o portao do motor (so o do vigia), o «Rodar agora» "
           u"rodaria a oculomotora no torax",
           rodou == ["total_v3", "oculomotor_muscles"], rodou)
    del B


class _ContaNotificacao(object):
    def __init__(self):
        self.chamadas = []

    def __call__(self, *a, **k):
        self.chamadas.append(a)
        return True


def _motor_que_falha(TW, erro_por_pid):
    class _Motor(TW._MotorQueEntrega):
        serie_pid = [None]

        def run_ts_task(self, ref, t, device=None, jid=None, timeout_s=None,
                        cruas=None, **kw):
            e = erro_por_pid.get(self.serie_pid[0])
            if e is not None and t.startswith("total"):
                self.tasks.append(t)
                raise e() if callable(e) and isinstance(e, type) else e
            return TW._MotorQueEntrega.run_ts_task(
                self, ref, t, device=device, jid=jid, timeout_s=timeout_s,
                cruas=cruas, **kw)
    return _Motor


def _erro_da_base(pid):
    return RuntimeError(u"TS total_v3 rodou mas nenhuma estrutura conhecida "
                        u"apareceu no volume (processo %d)"
                        % (1000 + sum(ord(c) for c in pid)))


def teste_sem_repeticao_cega():
    secao(u"CA-05: a parada pela assinatura, e CA-11: uma notificacao")
    TW = _tw()
    pids = ["PAC_F1", "PAC_F2", "PAC_F3", "PAC_F4", "PAC_F5"]
    erros = dict((p, _erro_da_base(p)) for p in pids)
    Motor = _motor_que_falha(TW, erros)
    mod, root, base, fila, motor = _serie_no_vigia(
        TW, lambda b: Motor(b), pids=pids)
    conta = _ContaNotificacao()
    mod.notificar = conta
    por_pid = dict((s["pid"], s) for s in fila)
    linhas = []
    resultados = {}
    for i, p in enumerate(pids):
        s = por_pid.get(p)
        if s is None:
            continue
        Motor.serie_pid[0] = p
        resultados[p] = _processar(mod, s, linhas)
        if i == 1:
            checar(u"depois da 2a serie ainda nao ha alerta",
                   not mod.STATE.get("alertas_de_assinatura"),
                   mod.STATE.get("alertas_de_assinatura"))
    fls = dict((p, mod.read_marker(por_pid[p]["dir"], por_pid[p]["uid"],
                                   "fail") or {}) for p in pids
               if p in por_pid)
    ass = set(f.get("assinatura") for f in fls.values())
    checar(u"as cinco tem a MESMA assinatura (o numero do processo nao "
           u"entra)", len(ass) == 1 and all(ass), ass)
    checar(u"(a) a 1a, a 2a e a 3a gastam tentativa",
           [int(fls[p].get("tries", 0)) for p in pids[:3]] == [1, 1, 1],
           [fls[p].get("tries") for p in pids[:3]])
    checar(u"(a) da 3a em diante o alerta existe, com a frase curta",
           len(mod.STATE.get("alertas_de_assinatura") or []) == 1
           and u"nenhuma estrutura" in mod.STATE["alertas_de_assinatura"][0]
           .get("frase", u""), mod.STATE.get("alertas_de_assinatura"))
    checar(u"(a) a 4a e a 5a ficam em espera, SEM tentativa a mais",
           all(fls[p].get("em_espera") == list(ass)[0]
               and int(fls[p].get("tries", 0)) == 0 for p in pids[3:]),
           [(fls[p].get("em_espera"), fls[p].get("tries"))
            for p in pids[3:]])
    fila2, _ = TW.fila_de(mod)
    checar(u"a varredura seguinte nao oferece nenhuma das cinco",
           not [s for s in fila2 if s["pid"] in pids],
           [s["pid"] for s in fila2])
    checar(u"e as cinco estao em EM_ESPERA",
           sorted(x["pid"] for x in mod.EM_ESPERA) == pids,
           [x["pid"] for x in mod.EM_ESPERA])
    checar(u"o log diz EM ESPERA uma vez",
           len([l for l in linhas if l.startswith(u"EM ESPERA")]) == 1,
           [l for l in linhas if u"ESPERA" in l][:3])
    checar(u"CA-11: um traceback no log e uma notificacao de falha, nao "
           u"cinco", len([l for l in linhas if u"Traceback" in l]) == 1
           and len([c for c in conta.chamadas if c[1] == "falhou"]) == 1,
           (len([l for l in linhas if u"Traceback" in l]),
            [c[1] for c in conta.chamadas]))
    checar(u"CA-11: a repeticao escreve uma linha com a assinatura",
           len([l for l in linhas if u"mesma falha da serie" in l]) == 4,
           len([l for l in linhas if u"mesma falha da serie" in l]))
    checar(u"e a notificacao da espera sai uma vez",
           len([c for c in conta.chamadas if c[1] == "em_espera"]) == 1,
           [c[1] for c in conta.chamadas])
    s5 = por_pid[pids[4]]
    fl5 = dict(fls[pids[4]], versao_do_app="0.0-velha")
    mod.m_path(s5["dir"], s5["uid"], "fail", criar=True).write_text(
        json.dumps(fl5), encoding="utf-8")
    mod.STATE["assinaturas"] = {}
    fila3, _ = TW.fila_de(mod)
    checar(u"(c) com a versao do app trocada, a espera se solta",
           [s for s in fila3 if s["pid"] == pids[4]],
           [s["pid"] for s in fila3])

    mod2, root2, base2, fila2b, motor2 = _serie_no_vigia(
        TW, lambda b: Motor(b), pids=["PAC_F1"])
    mod2.notificar = _ContaNotificacao()
    Motor.serie_pid[0] = "PAC_F1"
    for _i in range(3):
        _processar(mod2, fila2b[0])
    checar(u"ISCA: a MESMA serie tres vezes nao vira «tres series» -- sem "
           u"alerta", not mod2.STATE.get("alertas_de_assinatura"),
           mod2.STATE.get("alertas_de_assinatura"))


def teste_a_serie_que_falhou_vai_para_o_fim():
    secao(u"CA-05: a serie que falhou volta no fim da fila")
    TW = _tw()
    pids = ["PAC_VELHA", "PAC_MEIO", "PAC_RECENTE"]
    Motor = _motor_que_falha(TW, {"PAC_RECENTE": _erro_da_base("x")})
    from datetime import datetime, timedelta
    agora = datetime.now()
    mod, root, base = TW.montar([("PAC_VELHA", agora - timedelta(days=3), 8),
                                 ("PAC_MEIO", agora - timedelta(days=2), 8),
                                 ("PAC_RECENTE", agora - timedelta(days=1),
                                  8)], extra={"DRY_RUN": "0"})
    TW.envelhecer(root, 60)
    fila, _ = TW.fila_de(mod)
    motor = Motor(base)
    mod.carregar_engine = lambda: motor
    mod.notificar = _ContaNotificacao()
    rec = [s for s in fila if s["pid"] == "PAC_RECENTE"]
    checar(u"antes da falha, a mais recente vem primeiro",
           fila and fila[0]["pid"] == "PAC_RECENTE", [s["pid"] for s in fila])
    Motor.serie_pid[0] = "PAC_RECENTE"
    _processar(mod, rec[0])
    fila2, _ = TW.fila_de(mod)
    checar(u"(b) depois da falha ela vem DEPOIS das que ainda nao falharam",
           [s["pid"] for s in fila2][-1:] == ["PAC_RECENTE"]
           and len(fila2) == 3, [s["pid"] for s in fila2])


def teste_a_indeterminada_uma_vez_por_turno():
    secao(u"CA-05: a indeterminada, uma vez por turno")
    TW = _tw()
    bwd = {"tipo": "RuntimeError", "onde": u"x.py:1 em f", "bloco": u"",
           "mensagem": u"Background workers died. Look for the error message "
                       u"further up!"}
    Motor = _motor_que_falha(TW, {"PAC_IND": F.FalhaDaTask(
        "total_v3", codigo=1, primeira=bwd, ultima=bwd)})
    mod, root, base, fila, motor = _serie_no_vigia(
        TW, lambda b: Motor(b), pids=["PAC_IND"])
    mod.notificar = _ContaNotificacao()
    Motor.serie_pid[0] = "PAC_IND"
    _processar(mod, fila[0])
    fl = mod.read_marker(fila[0]["dir"], fila[0]["uid"], "fail") or {}
    checar(u"a classe e indeterminada e gasta tentativa",
           fl.get("ultimo_tipo") == F.INDETERMINADA
           and int(fl.get("tries", 0)) == 1, fl)
    fila2, _ = TW.fila_de(mod)
    checar(u"no mesmo turno ela nao volta", not fila2,
           [s["pid"] for s in fila2])
    mod.abrir_turno_das_assinaturas()
    fila3, _ = TW.fila_de(mod)
    checar(u"no turno seguinte ela volta", [s["pid"] for s in fila3]
           == ["PAC_IND"], [s["pid"] for s in fila3])


def _memoria(livre_gib, commit_gib, total_gib=31.7):
    return lambda: {"total_mb": int(total_gib * 1024),
                    "livre_mb": int(livre_gib * 1024), "pct": 50,
                    "commit_total_mb": int(48 * 1024),
                    "commit_livre_mb": int(commit_gib * 1024)}


def teste_o_plano_olha_a_ram_e_o_commit():
    secao(u"CA-06: o plano olha a RAM e o commit, pela regiao")
    d = temp()
    conta = os.path.join(d, "contador.txt")
    falso = _escrever_falso(d, u"gravar([(1, (slice(2, 6), slice(3, 9), "
                               u"slice(3, 9)))])\n")
    mapa = {"abdominal_muscles": {1: "rectus_abdominis_left"}}
    grande = {"precisa_mb": int(30.8 * 1024), "conta_mb": int(30.8 * 1024),
              "voxels": 434000000, "regiao": u"a grade inteira"}
    with _Troca(M, estimativa_de_ram=lambda *a, **k: dict(grande),
                memoria_e_commit=_memoria(9.0, 11.0)):
        r, log = _rodar_com_falso(falso, "abdominal_muscles", mapa=mapa,
                                  contador=conta)
    checar(u"(a) 434 M voxels com 11 GiB de commit: RecursoPrevisto, sem "
           u"abrir o filho", isinstance(r, F.RecursoPrevisto)
           and not os.path.exists(conta), repr(r)[:200])
    checar(u"  a classe e recurso, e a frase traz os numeros",
           F.classificar_falha(r) == F.RECURSO and u"GiB" in str(r)
           and u"o processo nao e aberto" in str(r), str(r))
    with _Troca(M, estimativa_de_ram=lambda *a, **k: dict(grande),
                memoria_e_commit=_memoria(9.0, 11.0),
                decidir_ram=lambda e, m: ("cabe", u"isca")):
        r, log = _rodar_com_falso(falso, "abdominal_muscles", mapa=mapa,
                                  contador=conta)
    checar(u"ISCA: o plano que so olha a VRAM abre o filho",
           os.path.exists(conta), repr(r)[:120])
    os.remove(conta)
    media = {"precisa_mb": int(14.8 * 1024), "conta_mb": int(14.8 * 1024),
             "voxels": 205000000, "regiao": u"a grade inteira"}
    with _Troca(M, estimativa_de_ram=lambda *a, **k: dict(media),
                memoria_e_commit=_memoria(20.0, 30.0)):
        r, log = _rodar_com_falso(falso, "abdominal_muscles", mapa=mapa,
                                  contador=conta)
    checar(u"(b) 205 M voxels com 30 GiB de commit: roda",
           os.path.exists(conta) and not isinstance(r, Exception),
           repr(r)[:200])
    checar(u"  e a linha do dispositivo diz a RAM",
           any(u"RAM:" in l and u"commit livre" in l for l in log), log[-8:])
    with _Troca(M, estimativa_de_ram=lambda *a, **k: dict(media),
                memoria_e_commit=_memoria(6.0, 30.0)):
        r, log = _rodar_com_falso(falso, "abdominal_muscles", mapa=mapa)
    checar(u"cabe no commit e nao na RAM livre: roda, com o aviso de paginar",
           not isinstance(r, Exception)
           and any(u"vai paginar" in l for l in log), log[-8:])
    forma, esp = (181, 512, 512), (3.0, 0.98, 0.98)
    caixa = ((100, 133), (180, 329), (200, 307))
    inteira = M.estimativa_de_ram("craniofacial_structures", forma, esp)
    na_caixa = M.estimativa_de_ram("craniofacial_structures", forma, esp,
                                   caixa_zyx=caixa)
    mem = _memoria(10.0, 20.0)()
    checar(u"(c) a craniofacial na caixa da cabeca roda com 20 GiB de commit",
           M.decidir_ram(na_caixa, mem)[0] != "adiar",
           (na_caixa, M.decidir_ram(na_caixa, mem)))
    checar(u"ISCA (c): pela grade inteira ela seria adiada",
           M.decidir_ram(inteira, mem)[0] == "adiar",
           (inteira["conta_mb"], M.decidir_ram(inteira, mem)))
    real_g = M.estimativa_de_ram("abdominal_muscles", (434, 1000, 1000),
                                 (1.0, 1.0, 1.0))
    real_m = M.estimativa_de_ram("abdominal_muscles", (205, 1000, 1000),
                                 (1.0, 1.0, 1.0))
    checar(u"a conta REAL de 434 M voxels pede a ordem do plano medido "
           u"(~30 GiB) e e adiada com 11 GiB de commit livre",
           real_g["voxels"] == 434000000
           and 26 * 1024 <= real_g["precisa_mb"] <= 36 * 1024
           and M.decidir_ram(real_g, _memoria(9.0, 11.0)())[0] == "adiar",
           (real_g, M.decidir_ram(real_g, _memoria(9.0, 11.0)())))
    checar(u"  e a de 205 M voxels roda com 30 GiB de commit livre",
           M.decidir_ram(real_m, _memoria(20.0, 30.0)())[0] != "adiar",
           (real_m, M.decidir_ram(real_m, _memoria(20.0, 30.0)())))
    beira = {"precisa_mb": int(10.9 * 1024), "conta_mb": int(9.5 * 1024),
             "voxels": 1, "regiao": u"a grade inteira"}
    checar(u"a decisao compara o que o processo PRECISA (com o fixo e o piso) "
           u"com o commit livre menos a margem -- ISCA: so a parte que cresce "
           u"com o volume (9,5 GiB) caberia nos 10 GiB",
           M.decidir_ram(beira, _memoria(5.0, 11.0)())[0] == "adiar",
           M.decidir_ram(beira, _memoria(5.0, 11.0)()))
    pequena = {"precisa_mb": 4096, "conta_mb": 200, "voxels": 1,
               "regiao": u"a grade inteira"}
    checar(u"a task pequena (conta abaixo do minimo) nao e adiada pelo piso",
           M.decidir_ram(pequena, _memoria(2.0, 4.0)())[0] != "adiar",
           M.decidir_ram(pequena, _memoria(2.0, 4.0)()))
    torax, forma_t = _anatomia_sintetica({"torax", "cabeca"})
    vol = _volume(forma=forma_t)
    recebeu = {}

    def _rodar(ref, t, dev, jid, **kw):
        recebeu[t] = kw.get("regiao_ram")
        return dict(torax) if t == "total_v3" else {}
    jid = M._job_new()
    try:
        M.rodar_tasks(vol, ["total_v3", "craniofacial_structures",
                            "trunk_cavities"], "cpu", jid, rodar=_rodar)
    finally:
        M._job_del(jid)
    checar(u"o primitivo manda a caixa da cabeca para a task que recorta "
           u"pelo proprio localizador, e nada para a que roda a grade inteira",
           (recebeu.get("craniofacial_structures") or {}).get("zyx")
           and recebeu.get("trunk_cavities") is None, recebeu)


def teste_o_recurso_previsto_no_vigia():
    secao(u"v8.5 (C4): a task que nao cabe e pulada na hora, e a serie segue")

    def _rodar(ref, t, dev, jid, **kw):
        if t == "breasts":
            raise F.RecursoPrevisto("breasts", 20480, 5120, 9216)
        return {}
    jid = M._job_new()
    try:
        res = M.rodar_tasks(_volume(), ["total_v3", "breasts",
                                        "trunk_cavities"], "cpu", jid,
                            rodar=_rodar)
        log = list(M._job(jid).get("log") or [])
    finally:
        M._job_del(jid)
    checar(u"o resultado leva tasks_puladas_por_memoria com a task, quanto "
           u"pedia e quanto havia (o commit livre), em GiB",
           res.get("tasks_puladas_por_memoria")
           == [{"task": "breasts", "pedia_gib": 20.0, "livre_gib": 9.0}],
           res.get("tasks_puladas_por_memoria"))
    checar(u"  e o resto da lista roda (a serie e entregue sem ela)",
           "trunk_cavities" in res["rodaram"]
           and "breasts" not in res["rodaram"]
           and not res["falharam"], (res["rodaram"], res["falharam"]))
    checar(u"  e o log diz, com os numeros",
           any(u"PULADA por memoria" in l and u"breasts" in l
               and u"20,0" in l and u"9,0" in l for l in log),
           [l for l in log if u"PULADA" in l][:2])

    def _base(ref, t, dev, jid, **kw):
        raise F.RecursoPrevisto("total_v3", 40960, 2048, 4096)
    jid = M._job_new()
    try:
        try:
            M.rodar_tasks(_volume(), ["total_v3", "breasts"], "cpu", jid,
                          rodar=_base)
            levantou = False
        except F.RecursoPrevisto:
            levantou = True
    finally:
        M._job_del(jid)
    checar(u"a BASE que nao cabe nao e pulada: levanta, e a serie e adiada",
           levantou)
    velho = M.pulada_por_memoria
    M.pulada_por_memoria = lambda e, task=None: {"task": task,
                                                  "pedia_gib": None,
                                                  "livre_gib": None}
    try:
        jid = M._job_new()
        try:
            ri = M.rodar_tasks(_volume(), ["total_v3", "breasts"], "cpu", jid,
                               rodar=_rodar)
        finally:
            M._job_del(jid)
    finally:
        M.pulada_por_memoria = velho
    checar(u"ISCA: sem os numeros, a checagem de cima reprovaria",
           ri.get("tasks_puladas_por_memoria") != [
               {"task": "breasts", "pedia_gib": 20.0, "livre_gib": 9.0}])
    TW = _tw()
    rp = F.RecursoPrevisto("breasts", 20000, 5000, 9000)
    ok, motor, mod, s, linhas = TW._rodar_anatomia(
        {"torax"}, erro_na={"breasts": rp})
    fl = (mod.read_marker(s["dir"], s["uid"], "fail") or {}) if s else {}
    checar(u"no vigia a serie e entregue, sem adiamento e sem tentativa",
           ok is not False and not fl.get(mod.RECURSO)
           and int(fl.get("tries", 0) or 0) == 0, (ok, fl))


def teste_a_complementar_que_falha_nao_derruba_a_serie():
    secao(u"o complemento indeterminado ou inelegivel nao derruba a serie")
    TW = _tw()
    bwd = {"tipo": "RuntimeError", "mensagem": u"Background workers died. "
           u"Look for the error message further up! If there is none then "
           u"your RAM was full and the worker was killed by the OS.",
           "onde": u"data_loader.py:N em __next__", "bloco": u""}
    nib = {"tipo": "AssertionError", "mensagem": u"only 3d images are "
           u"supported by NibabelIO", "onde": u"nibabel_reader_writer.py:N "
           u"em read_images", "bloco": u""}
    casos = (
        (F.INDETERMINADA, F.FalhaDaTask("breasts", codigo=1,
                                        primeira=dict(bwd),
                                        ultima=dict(bwd))),
        (F.INELEGIVEL, F.FalhaDaTask("breasts", codigo=1,
                                     primeira=dict(nib), ultima=dict(bwd))),
    )
    for classe, e in casos:
        checar(u"a falha sintetica e da classe %s" % classe,
               F.classificar_falha(e) == classe, F.classificar_falha(e))
        ok, motor, mod, s, linhas = TW._rodar_anatomia(
            {"torax"}, erro_na={"breasts": e})
        if motor is None:
            checar(u"a serie entrou na fila (%s)" % classe, False)
            continue
        fl = mod.read_marker(s["dir"], s["uid"], "fail") or {}
        done = mod.read_marker(s["dir"], s["uid"], "done") or {}
        checar(u"%s no complemento: a serie SAI com a base" % classe,
               ok is True and bool(done) and len(motor.rts) >= 1,
               (ok, bool(done), fl))
        checar(u"  sem tentativa gasta e sem recusa da serie (%s)" % classe,
               int(fl.get("tries", 0) or 0) == 0 and not fl.get("inelegivel")
               and not [x for x in mod.NAO_CONTORNAVEIS
                        if x["uid"] == s["uid"]], fl)
        _tf = [f for f in done.get("tasks_falharam") or []
               if f.get("task") == "breasts"]
        checar(u"  o `done` leva a task em tasks_falharam com a classe "
               u"(%s)" % classe,
               _tf and _tf[0].get("classe") == classe, _tf)
        checar(u"  e o log diz que a serie segue sem ela (%s)" % classe,
               any(u"SEM o complemento de: breasts" in l for l in linhas)
               and not any(u"TRAVA (tempo limite)" in l or u"falta de RECURSO"
                           in l for l in linhas),
               [l for l in linhas if u"complemento" in l][:3])


def teste_a_memoria_do_vigia_no_log():
    secao(u"CA-13: a memoria do vigia no log")
    meu = M.memoria_do_processo_mb()
    checar(u"a memoria deste processo e medida (ele carregou numpy e o "
           u"SimpleITK)", meu and meu > 50, meu)
    import subprocess
    filho = subprocess.Popen([sys.executable, "-c",
                              "import time; time.sleep(8)"])
    try:
        time.sleep(1.0)
        do_filho = M.memoria_do_processo_mb(filho.pid)
    finally:
        filho.kill()
    checar(u"ISCA: o RSS de um filho e outro numero (o do pai e o que conta)",
           do_filho and meu and do_filho < meu * 0.8, (meu, do_filho))
    d = temp()
    falso = _escrever_falso(d, u"gravar([(1, (slice(2, 6), slice(3, 9), "
                               u"slice(3, 9)))])\n")
    r, log = _rodar_com_falso(falso, "total_v3",
                              mapa={"total_v3": {1: "liver"}})
    ini = [l for l in log if u"(iniciando)" in l]
    checar(u"a linha «(iniciando)» diz «vigia N GiB»",
           ini and u"vigia " in ini[0] and u"GiB" in ini[0], ini)
    with _Troca(M, memoria_do_processo_mb=lambda pid=None: None):
        r, log = _rodar_com_falso(falso, "total_v3",
                                  mapa={"total_v3": {1: "liver"}})
    ini = [l for l in log if u"(iniciando)" in l]
    checar(u"sem a medida, a linha sai sem o campo e sem excecao",
           ini and u"vigia" not in ini[0] and isinstance(r, dict), ini)


class _CacheLigado(object):

    def __init__(self, pasta):
        self.pasta = pasta

    def __enter__(self):
        import radai_cache_tasks as CT
        self.CT = CT
        self.velho = os.environ.get("RADAI_CACHE_TASKS_DIR")
        os.environ["RADAI_CACHE_TASKS_DIR"] = self.pasta
        CT.armar(True)
        return CT

    def __exit__(self, *a):
        self.CT.armar(False)
        if self.velho is None:
            os.environ.pop("RADAI_CACHE_TASKS_DIR", None)
        else:
            os.environ["RADAI_CACHE_TASKS_DIR"] = self.velho
        return False


def _linhas_do(contador):
    try:
        with io.open(contador, encoding="utf-8") as f:
            return [l for l in f.read().splitlines() if l.strip()]
    except OSError:
        return []


def teste_o_cache_por_task():
    secao(u"CA-07: o cache por task na estacao")
    d = temp()
    pasta = os.path.join(d, "cache_tasks")
    conta = os.path.join(d, "contador.txt")
    falso = _escrever_falso(d, u"gravar([(1, (slice(2, 6), slice(3, 9), "
                               u"slice(3, 9))), (2, (slice(2, 6), slice(9, "
                               u"14), slice(9, 14)))])\n")
    mapa = {"total_v3": {1: "liver", 2: "spleen"}}
    uid = u"1.2.840.99999.4242.17.3"
    vol = _volume()
    vol.SetMetaData("0020|000e", uid)
    with _CacheLigado(pasta) as CT:
        c1, c2 = {}, {}
        r1, l1 = _rodar_com_falso(falso, "total_v3", mapa=mapa, vol=vol,
                                  contador=conta, cruas=c1)
        r2, l2 = _rodar_com_falso(falso, "total_v3", mapa=mapa, vol=vol,
                                  contador=conta, cruas=c2)
        checar(u"(a) duas chamadas da mesma task: o filho roda UMA vez",
               len(_linhas_do(conta)) == 1 and isinstance(r2, dict),
               (_linhas_do(conta), repr(r2)[:120]))
        checar(u"(a) as mascaras e as cruas da segunda sao identicas",
               sorted(r1) == sorted(r2) and all(np.array_equal(r1[k], r2[k])
                                                for k in r1)
               and sorted(c1["total_v3"]) == sorted(c2["total_v3"])
               and all(np.array_equal(c1["total_v3"][k], c2["total_v3"][k])
                       for k in c1["total_v3"]), (sorted(r1), sorted(r2)))
        checar(u"(a) o log diz que veio do cache desta estacao",
               any(u"do cache desta estacao" in l for l in l2), l2[-3:])
        with _Troca(CT, impressao_dos_pesos=lambda *a, **k: u"outro peso"):
            _rodar_com_falso(falso, "total_v3", mapa=mapa, vol=vol,
                             contador=conta)
        checar(u"(b) com o peso trocado a task roda de novo",
               len(_linhas_do(conta)) == 2, _linhas_do(conta))
        with _Troca(CT, impressao_dos_pesos=lambda *a, **k: u"fixo"):
            _rodar_com_falso(falso, "total_v3", mapa=mapa, vol=vol,
                             contador=conta)
            _rodar_com_falso(falso, "total_v3", mapa=mapa, vol=vol,
                             contador=conta)
        checar(u"ISCA (b): com a impressao dos pesos fixa, o peso trocado "
               u"nao seria visto (a segunda leu do cache)",
               len(_linhas_do(conta)) == 3, _linhas_do(conta))
        _rodar_com_falso(falso, "total_v3", mapa=mapa,
                         vol=_volume(forma=(9, 16, 16)), contador=conta)
        checar(u"(c) a serie com um corte a mais roda de novo",
               len(_linhas_do(conta)) == 4, _linhas_do(conta))
        achou = []
        for raiz, _x, fs in os.walk(pasta):
            for f in fs:
                caminho = os.path.join(raiz, f)
                with open(caminho, "rb") as fh:
                    bruto = fh.read()
                if uid.encode("ascii") in bruto or uid in caminho:
                    achou.append(caminho)
        checar(u"(e) o UID da serie nao aparece em nenhum nome nem conteudo",
               not achou and os.listdir(pasta), achou)
        falso_1 = _escrever_falso(d, u"gravar([(1, (slice(2, 6), slice(3, 9),"
                                     u" slice(3, 9)))])\nsys.exit(1)\n")
        antes = len(os.listdir(pasta))
        r, log = _rodar_com_falso(falso_1, "total_v3", mapa=mapa,
                                  vol=_volume(forma=(10, 16, 16)))
        checar(u"ISCA: a task que sai com codigo 1 nao grava no cache",
               isinstance(r, Exception) and len(os.listdir(pasta)) == antes,
               (repr(r)[:80], os.listdir(pasta)))
    with _CacheLigado(pasta) as CT:
        velho = os.environ.get("RADAI_RAIZES_NUVEM")
        os.environ["RADAI_RAIZES_NUVEM"] = d
        try:
            import radai_archive as A
            try:
                A._CACHE_RAIZES["quando"] = None
            except Exception:
                pass
            r, log = _rodar_com_falso(falso, "total_v3", mapa=mapa, vol=vol,
                                      contador=conta)
        finally:
            if velho is None:
                os.environ.pop("RADAI_RAIZES_NUVEM", None)
            else:
                os.environ["RADAI_RAIZES_NUVEM"] = velho
            try:
                A._CACHE_RAIZES["quando"] = None
            except Exception:
                pass
        checar(u"(d) na pasta sincronizada o cache recusa, a task roda e o "
               u"log diz", len(_linhas_do(conta)) == 5
               and any(u"cache por task desligado" in l for l in log),
               (_linhas_do(conta), log[:3]))
    f = temp()
    agora = time.time()
    for i, (idade_d, mb) in enumerate(((20, 1), (1, 3), (2, 3), (3, 3))):
        e = os.path.join(f, "e%d" % i)
        os.makedirs(e)
        with open(os.path.join(e, "rotulos.npz"), "wb") as fh:
            fh.write(b"\0" * (mb * 1000 * 1000))
        os.utime(e, (agora - idade_d * 86400, agora - idade_d * 86400))
    import radai_cache_tasks as CT2
    r = CT2.faxina(ttl_dias=14, teto_gb=0.0065, agora=agora, p=f)
    checar(u"(f) a faxina tira a de 20 dias pelo prazo e a mais antiga pelo "
           u"teto", sorted(os.listdir(f)) == ["e1", "e2"]
           and r["apagadas"] == 2, (sorted(os.listdir(f)), r))
    checar(u"o cache nasce desarmado (as baterias e o lote nao gravam)",
           not CT2.armado())


def teste_a_impressao_do_volume_nao_copia_nem_segura():
    secao(u"CA-07: a impressao do volume, sem copia e sem segurar")
    import gc
    import tracemalloc
    import weakref
    import SimpleITK as sitk
    import radai_cache_tasks as CT
    arr = (np.arange(48 * 256 * 256) % 977).astype(np.int16).reshape(
        48, 256, 256)
    img = sitk.GetImageFromArray(arr)
    tamanho = arr.nbytes
    esperado = CT.impressao_do_volume(img)
    CT._IMPRESSOES_DE_VOLUME.clear()
    tracemalloc.start()
    try:
        tracemalloc.reset_peak()
        v = CT.impressao_do_volume(img)
        _atual, pico = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    checar(u"a impressao nao aloca uma copia do volume (pico bem abaixo do "
           u"tamanho dele)", v == esperado and pico < tamanho // 4,
           (pico, tamanho))
    checar(u"  e a mesma imagem de novo da a mesma impressao",
           CT.impressao_do_volume(img) == esperado)
    ref = weakref.ref(img)
    del img
    gc.collect()
    checar(u"depois da serie a imagem nao fica viva no cache da impressao",
           ref() is None, u"")


def teste_o_parcial_diz_o_que_faltou():
    secao(u"CA-08: o parcial diz o que faltou")
    import radai_records as RG
    falhas = [{"task": "trunk_cavities", "classe": "recurso",
               "erro": u"a task trunk_cavities precisa ~30,8 GiB"}]
    nao = [("pericardio", u"o `pericardium` so existe na task "
                          u"`trunk_cavities`, e ela nao rodou nesta serie"),
           ("femur_oar", u"a serie nao e TC (le densidade)")]
    f = RG.faltou_da_serie(falhas, nao,
                           estruturas_da_task=M.estruturas_da_task,
                           saidas_da_construcao=M.saidas_da_construcao)
    nomes = [x["estrutura"] for x in f]
    checar(u"faltou leva o pericardio com o porque",
           "pericardium" in nomes
           and all(u"trunk_cavities" in x["porque"] for x in f
                   if x["estrutura"] == "pericardium"), f)
    checar(u"  e as estruturas da propria task (os rotulos dela no FULL)",
           {"abdominal_cavity", "thoracic_cavity", "mediastinum"}
           <= set(nomes), nomes)
    checar(u"  e NAO a construcao que nao saiu por outro motivo",
           not [n for n in nomes if n.startswith("femur_oar")], nomes)
    checar(u"ISCA: sem a task na frase da construcao, o pericardio nao entra "
           u"-- o vinculo e pela task que falhou",
           not [x for x in RG.faltou_da_serie(
               [], nao, estruturas_da_task=M.estruturas_da_task,
               saidas_da_construcao=M.saidas_da_construcao)])
    cd = RG.campos_do_done(faltou=f)
    checar(u"o `done` leva `faltou` pela funcao comum das duas portas",
           [x["estrutura"] for x in cd.get("faltou") or []] == nomes,
           cd.get("faltou"))
    checar(u"a linha do log diz PARCIAL com o que faltou e o porque",
           RG.linha_do_parcial("...abc12345", f).startswith(
               u"PARCIAL serie ...abc12345: faltou ")
           and u"pericardium" in RG.linha_do_parcial("...abc12345", f)
           and u"trunk_cavities: recurso" in RG.linha_do_parcial(
               "...abc12345", f), RG.linha_do_parcial("...abc12345", f))
    for porta in ("radai_watcher.py", "radai_batch.py"):
        fonte = io.open(_componentes.fonte("app/" + porta), encoding="utf-8").read()
        checar(u"a porta %s chama `faltou_da_serie`" % porta,
               u"faltou_da_serie(" in fonte)


def teste_o_parcial_na_tabela_e_no_acervo():
    secao(u"CA-08: o parcial na tabela do /lote e no acervo")
    import radai_batch as B
    import radai_view as V
    import radai_records as RG
    done = {"finished": "2026-10-07 03:40", "machine": "PC_A",
            "modo": "auto", "tasks_ok": ["total_v3", "trunk_cavities"],
            "faltou": [{"estrutura": "pericardium",
                        "porque": u"trunk_cavities: recurso"},
                       {"estrutura": "abdominal_cavity",
                        "porque": u"trunk_cavities: recurso"}]}
    checar(u"os nomes do que faltou saem do `done` por uma funcao so",
           RG.nomes_do_faltou(done) == ["pericardium", "abdominal_cavity"]
           and RG.nomes_do_faltou({}) == []
           and RG.nomes_do_faltou(done["faltou"]) == ["pericardium",
                                                     "abdominal_cavity"],
           RG.nomes_do_faltou(done))
    marc = {"has_marker": lambda p, u, k: k == "done",
            "read_marker": lambda p, u, k: done if k == "done" else None}
    sit = B._situacao({"pasta": "x", "uid": "1.2.3"}, marc)
    checar(u"a tabela do /lote: a serie concluida leva o que faltou",
           sit.get("situacao") == "concluida"
           and sit.get("faltou") == ["pericardium", "abdominal_cavity"],
           sit)
    inteira = dict(done)
    inteira.pop("faltou")
    marc2 = {"has_marker": lambda p, u, k: k == "done",
             "read_marker": lambda p, u, k: inteira if k == "done" else None}
    checar(u"  e a serie inteira nao leva",
           not B._situacao({"pasta": "x", "uid": "1.2.3"}, marc2).get(
               "faltou"))
    pasta = temp()
    import radai_tabela_acervo as TA
    with _Troca(TA, resolver=lambda b: (pasta, "1.2.3"),
                _ler_done=lambda p, u: done,
                _cabecalho_da_serie=lambda p, u: (u"", u"CT", 3.0)):
        det = TA.detalhes(["b" * 32])
    checar(u"o acervo do /ver (a tabela da Suite): os detalhes levam o que "
           u"faltou",
           det and det[0].get("faltou") == ["pericardium",
                                            "abdominal_cavity"], det)
    js_lote = B.PAGINA
    i = js_lote.find("function linhaDaSerie(")
    corpo = js_lote[i:i + 12000]
    checar(u"o JS da tabela do /lote desenha o selo Parcial com o que faltou",
           u"s.faltou" in corpo and u">Parcial<" in corpo
           and u"Faltou nesta série: %s" in corpo, corpo[:80])
    checar(u"TEL-10: o que faltou fica À VISTA no /lote, e não só no title",
           u'<span class="tec2 sit-faltou">\' + esc(ftx)' in corpo)
    import radai_ui as UI
    js_ui = UI.COMPONENTES_JS
    j = js_ui.find("window.uiTabelaAcervo = function(")
    k = js_ui.find("function preencher(", j) if j >= 0 else -1
    corpo_v = js_ui[k:k + 4000] if k >= 0 else u""
    checar(u"o acervo do /ver é a tabela da Suite (`uiTabelaAcervo`)",
           u"uiTabelaAcervo(" in V.JS)
    checar(u"o JS da tabela do acervo desenha o selo Parcial com o que faltou",
           u"x.faltou" in corpo_v and u"'Parcial'" in corpo_v
           and u"Faltou nesta série: %s" in corpo_v, corpo_v[:80])
    checar(u"TEL-10: o que faltou fica À VISTA no acervo do /ver, e não só no title",
           u"fl.textContent = ftx;" in corpo_v and u"a.appendChild(fl);" in corpo_v)


def teste_o_disco_do_arranque():
    secao(u"CA-12: o disco do arranque")
    import radai_cleaner as LP
    import radai_archive as A
    checar(u"22 tasks pedidas nao multiplicam a conta",
           LP.disco_necessario_gb(1, 22) == LP.disco_necessario_gb(1, 1)
           and A.espaco_da_serie_gb(10 ** 6, 22) == A.espaco_da_serie_gb(
               10 ** 6, 1), (LP.disco_necessario_gb(1, 22),
                             LP.disco_necessario_gb(1, 1)))
    isca = A.GB_FOLGA + A.GB_POR_SERIE + 22 * A.GB_POR_TASK
    checar(u"ISCA: a conta de antes (22 x 1,5 GB) pediria ~%.0f GB" % isca,
           isca > LP.disco_necessario_gb(1, 22))
    import radai_arranque as R
    d = temp()
    rel = {"avisos": [], "dados": {}}
    with _Troca(LP, disco_necessario_gb=lambda *a, **k: 1e9):
        R._p_disco({"pasta_temp": d, "pasta_trabalho": d,
                    "tasks": ["total_v3"] * 22}, rel)
    unidade = os.path.splitdrive(os.path.abspath(d))[0]
    checar(u"o aviso cita a unidade do temporario",
           any(u"temporario" in a and unidade in a for a in rel["avisos"]),
           rel["avisos"])


def teste_o_rt_utils_nao_escreve_fora_do_log():
    secao(u"CA-14: o rt_utils nao escreve fora do log")
    from make_test_series import escreve_serie
    from datetime import datetime
    import contextlib
    d = temp()
    serie = os.path.join(d, "serie")
    escreve_serie(serie, "FANTOMA_CAMPO", datetime(2026, 3, 15, 10, 30), 12)
    m = np.zeros((12, 128, 128), bool)
    m[3:9, 40:80, 40:80] = True
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        caminho, nomes = M.build_rtstruct(serie, {"liver": m},
                                          tasks=["total_v3"],
                                          versao_worker="campo")
    checar(u"o RTSTRUCT sai, e nada de «Writing file to» na saida padrao",
           os.path.exists(caminho) and u"Writing file to" not in
           buf.getvalue(), buf.getvalue()[:200])
    from rt_utils import RTStructBuilder
    rt = RTStructBuilder.create_new(dicom_series_path=serie)
    buf2 = io.StringIO()
    with contextlib.redirect_stdout(buf2):
        rt.save(os.path.join(d, "isca.dcm"))
    checar(u"ISCA: o `rt.save` cru escreve «Writing file to»",
           u"Writing file to" in buf2.getvalue())

    class _Sentinela(object):
        def __init__(self):
            self.escritas = []

        def write(self, t):
            self.escritas.append(t)

        def flush(self):
            pass
    sentinela = _Sentinela()
    vista = []

    class _Ds(object):
        def save_as(self, caminho):
            vista.append(sys.stdout is sentinela)
            with io.open(caminho, "wb") as f:
                f.write(b"x")

    class _Rt(object):
        ds = _Ds()
    velho = sys.stdout
    sys.stdout = sentinela
    try:
        M._salvar_sem_escrever_no_console(_Rt(), os.path.join(d, "fio"))
    finally:
        sys.stdout = velho
    checar(u"a gravacao nao troca o `sys.stdout` do processo (outra thread "
           u"que escreve no meio continua na janela) -- ISCA: o "
           u"`redirect_stdout` o trocava", vista == [True]
           and not sentinela.escritas
           and os.path.exists(os.path.join(d, "fio.dcm")),
           (vista, sentinela.escritas))


def teste_o_resumo_da_noite():
    secao(u"CA-16: o resumo da noite, sem identificacao")
    import radai_records as RG
    nome, pid, uid = u"FULANO DE TAL", u"PID778899", u"1.2.840.555.66.77.88"
    pasta = u"C:\\PACIENTES\\FULANO DE TAL\\CT_1"
    def caso(quando, ok, cortes, regioes=(), seg=0.0, etapas=(), **res):
        r = dict(res, ok=ok, regioes=list(regioes))
        return {"abriu": "2026-10-07T%s-03:00" % quando,
                "serie": {"modalidade": "CT", "cortes": cortes,
                          "origem": "vigia"},
                "resultado": r, "segundos_totais": seg,
                "etapas": [{"etapa": e, "segundos": v} for e, v in etapas],
                "processamento": {"pico_memoria": {"por_task": {
                    "total_v3": {"ram_pct": 88.0}}}}}
    casos = [
        caso("01:30:00", True, 176, ("torax", "abdome"), 2040.0,
             (("TS total_v3", 217.0),),
             erro=u"%s %s %s %s" % (nome, pid, uid, pasta)),
        caso("02:10:00", True, 223, ("torax",), 1600.0,
             (("TS total_v3", 230.0),),
             faltou=[{"estrutura": "pericardium",
                      "porque": u"trunk_cavities: recurso"}]),
        caso("03:00:00", False, 25, (), 12.0, classe="inelegivel",
             assinatura="aaaaaaaaaa",
             erro=u"a serie e uma imagem colorida %s" % nome),
        caso("03:05:00", False, 41, (), 12.0, classe="deterministico",
             assinatura="bbbbbbbbbb", tipo_da_falha="RuntimeError",
             erro=u"RuntimeError: quebrou em %s" % pasta, em_espera=True),
        caso("03:07:00", False, 41, (), 12.0, classe="deterministico",
             assinatura="bbbbbbbbbb", tipo_da_falha=u"%s" % nome,
             erro=u"RuntimeError: quebrou %s" % pid),
        dict(caso("12:00:00", True, 100), abriu="2026-10-06T12:00:00-03:00"),
    ]
    r = RG.resumo_do_turno(casos, desde="2026-10-07 00:00:00",
                           ate="2026-10-07 09:00:00")
    for valor in (nome, pid, uid, u"PACIENTES", u"778899"):
        checar(u"o resumo nao leva %s" % (u"o valor semeado"),
               valor not in r, valor)
    checar(u"as contagens: 5 series, 2 entregues (1 parcial), 1 nao "
           u"contornavel, 2 falhas na mesma assinatura",
           u"series vistas: 5" in r and u"entregues: 2 (1 parcial" in r
           and u"nao contornaveis: 1" in r
           and u"bbbbbbbbbb: 2" in r, r)
    checar(u"a serie e «#n» com modalidade, regiao e cortes",
           u"#1 CT torax, abdome, 176 cortes" in r, r)
    checar(u"o tempo mediano por task", u"TS total_v3" in r, r)
    linhas_do_log = [u"=== serie ...%s | %s | 176 cortes | %s ===" % (
        uid[-8:], pid, pasta)]
    checar(u"ISCA: o resumo pelas linhas do log vaza o PatientID",
           pid in u"\n".join(linhas_do_log))


def teste_refazer_so_o_pos():
    secao(u"CA-15: refazer so o pos-processamento")
    r0 = M.receita_do_pos()
    with _Troca(M, VOLUME_DA_PODA_CM3=M.VOLUME_DA_PODA_CM3 + 1.0):
        r1 = M.receita_do_pos()
    checar(u"mudar uma constante da receita muda a impressao",
           r0 != r1 and r0 == M.VERSAO_DA_RECEITA_POS, (r0, r1))
    checar(u"os modulos de construcao entram na receita (sem o radai_breast, "
           u"que saiu com a Breast_OAR)",
           all(m in M.MODULOS_DO_POS for m in (
               "radai_skin", "radai_constructs", "radai_hnlnl"))
           and "radai_breast" not in M.MODULOS_DO_POS,
           getattr(M, "MODULOS_DO_POS", None))
    _fonte = M._fonte_do_modulo

    def _troca_fonte(nome_mod, velho, novo):
        def _f(nome):
            t = _fonte(nome)
            return t.replace(velho, novo, 1) if nome == nome_mod else t
        return _f
    import radai_skin as _SK
    _src_sk = _fonte("radai_skin")
    _linha = [l for l in _src_sk.splitlines()
              if l.startswith("ESPESSURA_PELE_MM")]
    checar(u"a constante da pele esta na fonte do radai_skin", _linha, u"")
    if _linha:
        with _Troca(M, _fonte_do_modulo=_troca_fonte(
                "radai_skin", _linha[0], u"ESPESSURA_PELE_MM = %r"
                % (float(_SK.ESPESSURA_PELE_MM) + 1.0))):
            r2 = M.receita_do_pos()
        checar(u"mudar a pele no radai_skin muda a receita (ISCA: a receita "
               u"so das tabelas do motor nao mudava)", r2 != r0, (r0, r2))
    with _Troca(M, _fonte_do_modulo=_troca_fonte(
            "radai_breast", u"\n", u"\n# so um comentario a mais\n")):
        r3 = M.receita_do_pos()
    checar(u"comentario a mais num modulo do pos NAO muda a receita",
           r3 == r0, (r0, r3))
    import re as _re
    _src_e = _fonte("engine")

    def _no_fim_da_funcao(nome, linha):
        i = _src_e.find(u"\ndef %s(" % nome)
        m = _re.compile(u"\n(?=[^\\s#])").search(_src_e, i + 1)
        if i < 0 or not m:
            return _src_e
        return _src_e[:m.start()] + u"\n    " + linha + _src_e[m.start():]

    def _fonte_engine(nova):
        def _f(nome):
            return nova if nome == "engine" else _fonte(nome)
        return _f
    with _Troca(M, _fonte_do_modulo=_fonte_engine(
            _no_fim_da_funcao("selecionar_do_full", u"_isca_do_pos = 1"))):
        r4 = M.receita_do_pos()
    checar(u"mudar o CODIGO de uma funcao do pos no motor muda a receita",
           r4 != r0, (r0, r4))
    with _Troca(M, _fonte_do_modulo=_fonte_engine(
            _no_fim_da_funcao("run_ts_task", u"_isca_da_inferencia = 1"))):
        r5 = M.receita_do_pos()
    checar(u"  e mudar a inferencia (run_ts_task) nao muda", r5 == r0,
           (r0, r5))
    d = temp()
    pasta = os.path.join(d, "cache_tasks")
    conta = os.path.join(d, "contador.txt")
    falso = _escrever_falso(d, u"gravar([(1, (slice(2, 6), slice(3, 9), "
                               u"slice(3, 9)))])\n")
    mapa = {"total_v3": {1: "liver"}}
    vol = _volume(forma=(11, 16, 16))
    with _CacheLigado(pasta) as CT:
        r, log = _rodar_com_falso(falso, "total_v3", mapa=mapa, vol=vol,
                                  contador=conta, so_cache=True)
        checar(u"so o pos sem cache: SemCacheParaOPos, e o filho NAO roda",
               isinstance(r, M.SemCacheParaOPos)
               and not _linhas_do(conta), repr(r)[:160])
        r, log = _rodar_com_falso(falso, "total_v3", mapa=mapa, vol=vol,
                                  contador=conta)
        checar(u"ISCA: sem o `so_cache`, a mesma task abre o filho",
               len(_linhas_do(conta)) == 1, _linhas_do(conta))
        r, log = _rodar_com_falso(falso, "total_v3", mapa=mapa, vol=vol,
                                  contador=conta, so_cache=True)
        checar(u"com o cache, so o pos le do cache e o filho nao roda de "
               u"novo", isinstance(r, dict) and r
               and len(_linhas_do(conta)) == 1, (repr(r)[:80],
                                                 _linhas_do(conta)))
        import radai_batch as B
        chaves = [n for n in os.listdir(pasta) if len(n) == 64]
        done = {"modo": "auto", "receita_pos": M.VERSAO_DA_RECEITA_POS,
                "cache_das_tasks": {"total_v3": chaves[0] if chaves else ""}}
        p = B.pos_refazivel(done)
        checar(u"a serie AUTO com o cache de todas as tasks e refazivel",
               p["refazivel"] and not p["receita_mudou"], p)
        p = B.pos_refazivel(dict(done, cache_das_tasks={"total_v3": "f" * 64}))
        checar(u"sem o cache de uma task: nao e refazivel, e diz por que",
               not p["refazivel"] and u"total_v3" in p["motivo"], p)
        p = B.pos_refazivel(dict(done, modo="perso"))
        checar(u"o PERSONALIZADO nao refaz so o pos", not p["refazivel"], p)
        p = B.pos_refazivel(dict(done, receita_pos="0" * 16))
        checar(u"a receita de antes acende «a receita mudou»",
               p["receita_mudou"], p)
    p = B.pos_refazivel(done)
    checar(u"com o cache desarmado nao e refazivel",
           not p["refazivel"] and u"desligado" in p["motivo"], p)
    fonte = io.open(_componentes.fonte("app/radai_batch.py"),
                    encoding="utf-8").read()
    checar(u"a rota existe, confere pela mesma funcao e responde 409",
           u'@app.post("/api/lote/refazer_pos")' in fonte
           and u"status_code=409" in fonte and u"pos_refazivel(done)" in fonte)
    checar(u"a serie «so o pos» pede o cache e a falta dele derruba a serie",
           u'kw["so_cache"] = True' in fonte
           and u'"SemCacheParaOPos"' in fonte)
    md = temp()
    import pathlib

    def m_path(p_, u, k, criar=False):
        dd = os.path.join(p_, "_RadAI")
        os.makedirs(dd, exist_ok=True)
        return pathlib.Path(dd, "%s.%s.json" % (u, k))
    B._marcar_done({"uid": "9.9", "pasta": md, "so_pos": True},
                   {"m_path": m_path}, "PC", "RS.dcm", [], 8, ["total_v3"],
                   10, None, campos={"receita_pos": M.VERSAO_DA_RECEITA_POS})
    dn = json.loads(m_path(md, "9.9", "done").read_text(encoding="utf-8"))
    checar(u"o `done` do refazer diz `refeito_pos` e a receita",
           dn.get("origem") == "refeito_pos"
           and dn.get("receita_pos") == M.VERSAO_DA_RECEITA_POS, dn)


def _marcadores_em_disco():
    import pathlib

    def m_path(p, u, k, criar=False):
        dd = os.path.join(str(p), "_RadAI")
        if criar:
            os.makedirs(dd, exist_ok=True)
        return pathlib.Path(dd, "%s.%s.json" % (u, k))

    def has(p, u, k):
        return m_path(p, u, k).exists()

    def ler(p, u, k):
        try:
            return json.loads(m_path(p, u, k).read_text(encoding="utf-8"))
        except Exception:
            return None

    def claim(p, u, info):
        m_path(p, u, "lock", criar=True).write_text(json.dumps(info))
        return True

    def _tirar(p, u, k):
        try:
            m_path(p, u, k).unlink()
        except Exception:
            pass

    def reservar(p, u):
        if has(p, u, "done"):
            return False, u"a serie ja foi entregue -- a primeira vale"
        m_path(p, u, "entrega", criar=True).write_text(u"{}")
        return True, u""
    return {"has_marker": has, "read_marker": ler, "claim": claim,
            "unclaim": lambda p, u: _tirar(p, u, "lock"),
            "renovar": lambda *a, **k: True, "m_path": m_path,
            "reservar_entrega": reservar,
            "soltar_entrega": lambda p, u: _tirar(p, u, "entrega"),
            "lock_e_meu": lambda p, u: (True, u""),
            "resolver_done_afastado": lambda p, u: u""}


def teste_refazer_so_o_pos_de_ponta_a_ponta():
    secao(u"CA-15: refazer so o pos, de ponta a ponta")
    import radai_batch as B
    import radai_topography as TP
    from datetime import datetime as _dt
    from make_test_series import escreve_serie
    import pydicom
    d = temp()
    pasta = os.path.join(d, "serie")
    uid = escreve_serie(pasta, "PAC_REFAZER", _dt(2026, 10, 7), 30)
    conta = os.path.join(d, "contador.txt")
    falso = _escrever_falso(d, u"gravar([(1, (slice(5, 25), slice(30, 90), "
                               u"slice(30, 90))), (2, (slice(5, 25), "
                               u"slice(90, 118), slice(40, 80)))])\n")
    mapa = {"total_v3": {1: "liver", 2: "spleen"}}
    marc = _marcadores_em_disco()

    def _serie(**extra):
        s = dict({"uid": uid, "pasta": pasta, "modalidade": "CT",
                  "pid": "PAC_REFAZER", "curto": uid[-8:],
                  "date": "20261007", "modo": "auto"}, **extra)
        return B._com_escolhas_da_tela({"series": [s]})[0]

    def _rodar(s):
        return B._uma_serie(s, False, ["total_v3"], "cpu", None, 600, 600,
                            None, marc, "BATERIA", 3600, 1.5)

    def _entregues():
        fora = {}
        for f in sorted(os.listdir(pasta)):
            if f.startswith("RS_RadAI_"):
                fora[f] = str(pydicom.dcmread(os.path.join(pasta, f),
                                              force=True).SOPInstanceUID)
        return fora
    anat = (lambda m, g, cruas=None, motor=None: {
        "regioes": (), "laudo": [u"dublada"], "coracao_cm3": None,
        "pescoco": (False, u"pescoco: nao")})
    novos = dict(TS_CMD=[sys.executable, falso], TS_CLASS_MAP=mapa,
                 base_eleita=lambda modalidade="CT", **k: None)
    velho_cfg = dict(B._CFG)
    velho_cont = os.environ.get("FALSO_CONTADOR")
    os.environ["FALSO_CONTADOR"] = conta
    try:
        with _CacheLigado(os.path.join(d, "cache")) as CT, \
                _Troca(M, **novos), _Troca(TP, anatomia_da_base=anat):
            B._CFG.clear()
            r1 = _rodar(_serie())
            done1 = marc["read_marker"](pasta, uid, "done") or {}
            rs1 = _entregues()
            n1 = len(_linhas_do(conta))
            checar(u"a serie roda pelo «Rodar agora» e entrega o FULL e o OAR",
                   not r1.get("erro") and len(rs1) == 2 and n1 == 1,
                   (str(r1.get("erro"))[:200], rs1, n1))
            checar(u"  e o `done` guarda o cache da task e a receita",
                   (done1.get("cache_das_tasks") or {}).get("total_v3")
                   and done1.get("receita_pos") == M.VERSAO_DA_RECEITA_POS,
                   done1)
            nova = u"f" * 16
            with _Troca(M, VERSAO_DA_RECEITA_POS=nova):
                p = B.pos_refazivel(done1)
                checar(u"a receita mudou: a tela acende o aviso e oferece "
                       u"refazer", p["receita_mudou"] and p["refazivel"], p)
                r2 = _rodar(_serie(substituir=True, so_pos=True))
                done2 = marc["read_marker"](pasta, uid, "done") or {}
            rs2 = _entregues()
            checar(u"refazer so o pos: RTSTRUCT novo nos mesmos arquivos, e o "
                   u"filho NAO abriu (contador igual)",
                   not r2.get("erro") and sorted(rs2) == sorted(rs1)
                   and all(rs2[k] != rs1[k] for k in rs1)
                   and len(_linhas_do(conta)) == n1,
                   (str(r2.get("erro"))[:200], rs1, rs2, _linhas_do(conta)))
            checar(u"  e o `done` diz `refeito_pos` com a receita nova",
                   done2.get("origem") == "refeito_pos"
                   and done2.get("receita_pos") == nova, done2)
            CT.armar(False)
            r3 = _rodar(_serie(substituir=True))
            checar(u"ISCA: refeita sem o cache, a serie abre o filho (o "
                   u"contador sabe subir)",
                   not r3.get("erro") and len(_linhas_do(conta)) == n1 + 1,
                   (str(r3.get("erro"))[:200], _linhas_do(conta)))
    finally:
        B._CFG.clear()
        B._CFG.update(velho_cfg)
        if velho_cont is None:
            os.environ.pop("FALSO_CONTADOR", None)
        else:
            os.environ["FALSO_CONTADOR"] = velho_cont
    import radai_queue_state as F
    F.limpar()
    try:
        F.acrescentar_series([{"uid": u"SP1", "pasta": u"p", "modo": u"auto",
                               "substituir": True, "so_pos": True}])
        r = F.acrescentar_series([{"uid": u"SP1", "pasta": u"p",
                                   "modo": u"auto", "substituir": True}])
        carga = [c.get("carga") or {} for c in F._CARDS
                 if c.get("uid") == u"SP1" or (c.get("carga") or {}).get(
                     "uid") == u"SP1"]
        checar(u"pedir de novo SEM o «so o pos» o tira da serie que espera",
               r.get("atualizadas") == 1 and carga
               and not carga[0].get("so_pos"), (r, carga))
    finally:
        F.limpar()
    fonte = B.PAGINA
    i = fonte.find(u"function refazerPos(")
    corpo = fonte[i:i + 1500]
    checar(u"o botao pergunta antes de substituir a entrega",
           u"perguntar(" in corpo and u"perigo: true" in corpo
           and u"aoSim" in corpo, corpo[:120])


_PAGINACAO_EN = (u"[WinError 1455] The paging file is too small for this "
                 u"operation to complete. Error loading \"x\\torch\\lib\\"
                 u"cudnn.dll\" or one of its dependencies.")
_PAGINACAO_PT = (u"[WinError 1455] O arquivo de paginação é muito pequeno "
                 u"para que esta operação seja concluída.")


def teste_a_falta_de_commit_e_recurso():
    secao(u"VIG-02: a falta de commit e recurso, em qualquer idioma")
    tabela = [
        (u"WinError 1455 em ingles", _falha_com("OSError", _PAGINACAO_EN)),
        (u"WinError 1455 em portugues", _falha_com("OSError", _PAGINACAO_PT)),
        (u"WinError 8 em portugues", _falha_com(
            "OSError", u"[WinError 8] Não há memória suficiente para "
            u"processar este comando")),
        (u"WinError 1450 em portugues", _falha_com(
            "OSError", u"[WinError 1450] Recursos de sistema insuficientes "
            u"para concluir o serviço solicitado")),
        (u"o DLL load failed do trabalhador", _falha_com(
            "ImportError", u"DLL load failed while importing _C: The paging "
            u"file is too small for this operation to complete.")),
        (u"o mesmo em portugues", _falha_com(
            "ImportError", u"DLL load failed while importing _C: O arquivo de "
            u"paginação é muito pequeno para que esta operação seja "
            u"concluída.")),
    ]
    for nome, e in tabela:
        checar(u"%s -> recurso" % nome,
               F.classificar_falha(e) == F.RECURSO, F.classificar_falha(e))
    checar(u"um OSError comum continua deterministico",
           F.classificar_falha(_falha_com(
               "OSError", u"[WinError 5] Acesso negado")) == F.DETERMINISTICO)
    velhas = ("not enough memory", "out of memory", "unable to allocate",
              "can't allocate memory", "cannot allocate memory", "bad_alloc",
              "defaultcpuallocator")

    def isca(e):
        p = e.primeira
        b = (u"%s %s" % (p["tipo"], p["mensagem"])).lower()
        return F.RECURSO if any(f in b for f in velhas) else F.DETERMINISTICO
    checar(u"ISCA: as frases de antes leem o 1455 em portugues como "
           u"deterministico", isca(tabela[1][1]) == F.DETERMINISTICO)


def teste_memoria_no_filho_nao_pausa_o_vigia():
    secao(u"VIG-01: memoria no filho nao pausa o vigia")
    import importlib
    W = importlib.import_module("radai_watcher")
    e = F.FalhaDaTask("breasts", codigo=1, primeira={
        "tipo": "ImportError", "mensagem": u"DLL load failed while importing "
        u"_C: The paging file is too small for this operation to complete.",
        "onde": u"__init__.py:1 em <module>", "bloco": u""}, ultima={
        "tipo": "RuntimeError", "mensagem": u"Background workers died.",
        "onde": u"x.py:1 em f", "bloco": u""}, volume_conferido=True)
    checar(u"a falta de commit no trabalhador nao e ambiente",
           W.erro_de_ambiente(e) is False, str(e)[:160])
    checar(u"e sai como recurso no vigia",
           W.classificar_erro(e) == W.RECURSO, W.classificar_erro(e))
    quebrado = _falha_com("ImportError", u"DLL load failed while importing "
                          u"_C: The specified module could not be found.")
    checar(u"a DLL que falta continua sendo ambiente",
           W.erro_de_ambiente(quebrado) is True)
    checar(u"o modulo que falta continua sendo ambiente",
           W.erro_de_ambiente(_falha_com(
               "ModuleNotFoundError", u"No module named 'totalsegmentator'"))
           is True)
    checar(u"o texto solto continua como antes",
           W.erro_de_ambiente(u"DLL load failed while importing x") is True)
    checar(u"ISCA: a regra de antes (o texto) pausaria o vigia",
           any(a in str(e).lower() for a in W.ERROS_DE_AMBIENTE))


def teste_a_frase_da_falha_sem_o_resto_do_caminho():
    secao(u"PRIV-02: a frase da falha sem o resto do caminho")
    t = (u"achei so 3 corte(s) da serie em C:\\RADIOTERAPIA_AI\\tmp\\"
         u"FULANO DE TAL\\CT 1.2.826.0.1.3680043.8.498.7")
    s = F.sem_caminho_nem_uid(t)
    checar(u"o texto local nao leva o resto do nome",
           u"DE TAL" not in s and u"<caminho>" in s, s)
    unc = F.sem_caminho_nem_uid(u"Sem DICOM em \\\\servidor\\imagens\\"
                                u"Patients\\ISCA BELTRANO 12345\\CT")
    checar(u"o caminho UNC tambem", u"BELTRANO" not in unc
           and u"12345" not in unc, unc)
    fc = F.frase_curta(FileNotFoundError(
        2, u"No such file", u"C:\\X\\FULANO DE TAL\\x.dcm"))
    checar(u"a frase curta tambem", u"DE TAL" not in fc
           and u"x.dcm" not in fc, fc)
    a1 = RuntimeError(u"sem DICOM em C:\\X\\FULANO DE TAL\\CT")
    a2 = RuntimeError(u"sem DICOM em C:\\X\\BELTRANO SOUZA\\CT")
    checar(u"duas pastas com espaco: a mesma assinatura",
           F.assinatura_da_falha(a1) == F.assinatura_da_falha(a2))
    checar(u"o endereco do painel nao vira caminho",
           u"127.0.0.1:8777" in F.sem_caminho_nem_uid(
               u"painel em http://127.0.0.1:8777/lote"))
    import re as _re
    velho = _re.compile(r"(?:[A-Za-z]:[\\/]|\\\\[^\\/\s]+[\\/]|"
                        r"/(?:[^/\s'\"]+/)+)[^\s'\"]*")
    checar(u"ISCA: o corte no primeiro espaco deixa «DE TAL»",
           u"DE TAL" in velho.sub(u"<caminho>", t))


def teste_o_nibabel_depois_da_guarda_nao_culpa_o_exame():
    secao(u"VIG-11: o NibabelIO depois da guarda")
    p = {"tipo": "AssertionError", "mensagem": u"only 3d images are "
         u"supported by NibabelIO", "onde": u"x.py:1 em f", "bloco": u""}
    e = F.FalhaDaTask("total_v3", codigo=1, primeira=p, ultima=p,
                      volume_conferido=True)
    checar(u"com a guarda: deterministico",
           F.classificar_falha(e) == F.DETERMINISTICO,
           F.classificar_falha(e))
    embrulho = RuntimeError(u"a serie falhou")
    embrulho.__cause__ = e
    checar(u"embrulhada pela porta: deterministico",
           F.classificar_falha(embrulho) == F.DETERMINISTICO)
    d = temp()
    log = _log_sintetico(d, "n.log", _TB_DO_TRABALHADOR + _TB_DO_PAI)
    r = M._falha_da_task("total_v3", log, 0, None, codigo=1)
    checar(u"o motor marca a guarda em toda FalhaDaTask",
           getattr(r, "volume_conferido", False)
           and F.classificar_falha(r) == F.DETERMINISTICO,
           F.classificar_falha(r))
    checar(u"a SerieNaoContornavel da guarda continua inelegivel",
           F.classificar_falha(F.SerieNaoContornavel(u"x")) == F.INELEGIVEL)
    sem = F.FalhaDaTask("total_v3", codigo=1, primeira=p, ultima=p)
    checar(u"ISCA: sem a marca da guarda, inelegivel",
           F.classificar_falha(sem) == F.INELEGIVEL)


def teste_a_espera_de_outra_versao_nao_volta_sozinha():
    secao(u"VIG-05: a espera de outra versao nao volta sozinha")
    TW = _tw()
    vista = {}

    def antes(mod, s, motor):
        mod.m_path(s["dir"], s["uid"], "fail", criar=True).write_text(
            json.dumps({"tries": 1, "ultimo_tipo": "deterministico",
                        "assinatura": "aaaaaaaaaa",
                        "em_espera": "aaaaaaaaaa",
                        "versao_do_app": "0.0-velha"}), encoding="utf-8")
        fila, _ = TW.fila_de(mod)
        vista["antes"] = any(x["uid"] == s["uid"] for x in fila)
    ok, motor, mod, s, linhas = TW._rodar_anatomia(
        set(), antes=antes, erro_na={"total_v3": ValueError(u"causa nova")})
    checar(u"na versao nova a serie volta a fila", vista.get("antes") is True)
    fl = mod.read_marker(s["dir"], s["uid"], "fail") or {}
    checar(u"a falha nova gasta tentativa e nao guarda a espera velha",
           fl.get("tries") == 2 and not fl.get("em_espera")
           and fl.get("versao_do_app") == mod.APPVER, fl)
    fila, _ = TW.fila_de(mod)
    checar(u"e a serie continua na fila", any(x["uid"] == s["uid"]
                                             for x in fila))
    isca = dict(fl, em_espera="aaaaaaaaaa")
    checar(u"ISCA: com o `em_espera` velho no `fail`, a serie sai da fila",
           mod._fora_da_fila_pela_falha(s, isca) == "em_espera")


def teste_o_cache_fica_fora_da_rede_e_das_series():
    secao(u"PRIV-05: o cache fora da rede e das series")
    import radai_cache_tasks as CT
    ok, motivo = CT.conferir_pasta(u"\\\\servidor\\Patients\\cache_tasks")
    checar(u"pasta de rede: recusada", ok is False and u"rede" in motivo,
           (ok, motivo))
    root = temp()
    ok2, m2 = CT.conferir_pasta(os.path.join(root, u"cache_tasks"),
                                clinicas=[root])
    checar(u"dentro do ROOT: recusada", ok2 is False and u"ROOT" in m2,
           (ok2, m2))
    cfg = os.path.join(temp(), u"radai_watcher.config")
    with io.open(cfg, "w", encoding="utf-8") as f:
        f.write(u"ROOT=%s\nOUT_DIR=\n" % root)
    velho = os.environ.get("RADAI_CONFIG")
    os.environ["RADAI_CONFIG"] = cfg
    try:
        ok3, _m3 = CT.conferir_pasta(os.path.join(root, u"cache_tasks"))
        ok4, _m4 = CT.conferir_pasta(os.path.join(temp(), u"cache_tasks"))
    finally:
        if velho is None:
            os.environ.pop("RADAI_CONFIG", None)
        else:
            os.environ["RADAI_CONFIG"] = velho
    checar(u"o ROOT vem do config desta instalacao", ok3 is False and ok4,
           (ok3, ok4))
    import radai_archive as A
    checar(u"ISCA: so a conferencia da nuvem aceitaria o compartilhamento",
           not A.em_pasta_sincronizada(u"\\\\servidor\\Patients\\x")[0])


def teste_a_chave_do_cache_ve_o_codigo_da_grade():
    secao(u"VIG-12: a chave do cache ve o codigo da grade")
    import radai_cache_tasks as CT
    fonte = io.open(_componentes.fonte("app/engine.py"),
                    encoding="utf-8").read()
    alvo = u"def resample(mi, ri):\n"
    checar(u"o motor tem a funcao que reamostra", alvo in fonte)
    mudado = fonte.replace(alvo, alvo + u"    _radai_x = 1\n", 1)
    comentado = fonte.replace(alvo, alvo + u"    # so um comentario\n", 1)
    h0 = M.codigo_da_volta_a_grade(fonte)
    h1 = M.codigo_da_volta_a_grade(mudado)
    h2 = M.codigo_da_volta_a_grade(comentado)
    checar(u"mudar o corpo de `resample` muda a impressao", h0 != h1,
           (h0, h1))
    checar(u"mudar so comentario nao muda", h0 == h2, (h0, h2))
    checar(u"a impressao do processo e a do arquivo",
           M.codigo_da_volta_a_grade() == h0)
    k0 = CT.chave(u"v", "total_v3", CT.receita("total_v3", codigo=h0))
    k1 = CT.chave(u"v", "total_v3", CT.receita("total_v3", codigo=h1))
    checar(u"e a chave do cache muda junto", k0 != k1)
    isca0 = CT.chave(u"v", "total_v3", CT.receita("total_v3"))
    isca1 = CT.chave(u"v", "total_v3", CT.receita("total_v3"))
    checar(u"ISCA: sem o codigo na receita, a chave e a mesma",
           isca0 == isca1)


def teste_o_acerto_do_cache_nao_escreve_a_entrada():
    secao(u"VIG-08: o acerto do cache nao escreve o NIfTI")
    d = temp()
    pasta = os.path.join(d, "cache_tasks")
    falso = _escrever_falso(d, u"gravar([(1, (slice(2, 6), slice(3, 9), "
                               u"slice(3, 9)))])\n")
    mapa = {"total_v3": {1: "liver"}}
    vol = _volume()
    escritos = []
    real = M.sitk.WriteImage

    def contar(img, caminho, *a, **k):
        if str(caminho).endswith("in.nii.gz"):
            escritos.append(str(caminho))
        return real(img, caminho, *a, **k)
    with _CacheLigado(pasta):
        with _Troca(M.sitk, WriteImage=contar):
            _rodar_com_falso(falso, "total_v3", mapa=mapa, vol=vol)
            n1 = len(escritos)
            r, log = _rodar_com_falso(falso, "total_v3", mapa=mapa, vol=vol)
    checar(u"ISCA: sem cache, o NIfTI de entrada e escrito", n1 == 1, n1)
    checar(u"do cache: nenhum NIfTI de entrada", len(escritos) == n1
           and isinstance(r, dict)
           and any(u"do cache desta estacao" in l for l in log),
           (len(escritos), log[-2:]))


def teste_refazer_so_o_pos_na_serie_parcial():
    secao(u"VIG-06: refazer so o pos na serie parcial")
    import radai_batch as B
    import radai_topography as TP
    from datetime import datetime as _dt
    from make_test_series import escreve_serie
    d = temp()
    pasta = os.path.join(d, "serie")
    uid = escreve_serie(pasta, "PAC_VIG06", _dt(2026, 10, 7), 30)
    conta = os.path.join(d, "contador.txt")
    falso = _escrever_falso(d, u"gravar([(1, (slice(5, 25), slice(30, 90), "
                               u"slice(30, 90))), (2, (slice(5, 25), "
                               u"slice(90, 118), slice(40, 80)))])\n")
    mapa = {"total_v3": {1: "liver", 2: "spleen"}}
    marc = _marcadores_em_disco()

    def _serie(**extra):
        s = dict({"uid": uid, "pasta": pasta, "modalidade": "CT",
                  "pid": "PAC_VIG06", "curto": uid[-8:],
                  "date": "20261007", "modo": "auto"}, **extra)
        return B._com_escolhas_da_tela({"series": [s]})[0]

    def _rodar(s):
        return B._uma_serie(s, False, ["total_v3"], "cpu", None, 600, 600,
                            None, marc, "BATERIA", 3600, 1.5)

    def anat(m, g, cruas=None, motor=None):
        return {"regioes": ("torax",), "laudo": [u"dublada"],
                "coracao_cm3": None, "pescoco": (False, u"pescoco: nao")}
    real_run = M.run_ts_task

    def run_dub(ref, task, *a, **kw):
        if task == "abdominal_muscles":
            if kw.get("so_cache"):
                raise M.SemCacheParaOPos(task)
            raise MemoryError("Unable to allocate 4.2 GiB (dublado)")
        return real_run(ref, task, *a, **kw)
    novos = dict(TS_CMD=[sys.executable, falso], TS_CLASS_MAP=mapa,
                 base_eleita=lambda modalidade="CT", **k: None,
                 run_ts_task=run_dub)
    velho_ct = os.environ.get("FALSO_CONTADOR")
    os.environ["FALSO_CONTADOR"] = conta
    try:
        with _CacheLigado(os.path.join(d, "cache")), _Troca(M, **novos), \
                _Troca(TP, anatomia_da_base=anat), \
                _Troca(B, tasks_depois_da_base=lambda *a, **k:
                       ["abdominal_muscles"]):
            B._CFG.clear()
            _rodar(_serie())
            done1 = marc["read_marker"](pasta, uid, "done") or {}
            n1 = len(_linhas_do(conta))
            checar(u"a entrega e parcial, com o complemento em "
                   u"`tasks_falharam`, e o botao aparece",
                   [f.get("task") for f in done1.get("tasks_falharam") or ()]
                   == ["abdominal_muscles"]
                   and B.pos_refazivel(done1)["refazivel"],
                   (done1.get("tasks_falharam"), B.pos_refazivel(done1)))
            isca = _rodar(_serie(substituir=True, so_pos=True))
            checar(u"ISCA: sem o `tasks_falharam` no pedido, a serie cai com "
                   u"SemCacheParaOPos",
                   u"SemCacheParaOPos" in str(isca.get("erro") or u""),
                   str(isca.get("erro"))[:160])
            r2 = _rodar(_serie(substituir=True, so_pos=True,
                               so_pos_falharam=B._falharam_do_done(done1)))
            done2 = marc["read_marker"](pasta, uid, "done") or {}
            checar(u"refazer so o pos entrega", not r2.get("erro")
                   and done2.get("origem") != done1.get("origem"),
                   (str(r2.get("erro"))[:160], done2.get("origem")))
            checar(u"  sem abrir o filho do TotalSegmentator",
                   len(_linhas_do(conta)) == n1, _linhas_do(conta))
            checar(u"  e a falha da entrega volta igual",
                   done2.get("tasks_falharam") == done1.get("tasks_falharam")
                   and done2.get("faltou") == done1.get("faltou"),
                   (done2.get("tasks_falharam"), done1.get("tasks_falharam")))
    finally:
        if velho_ct is None:
            os.environ.pop("FALSO_CONTADOR", None)
        else:
            os.environ["FALSO_CONTADOR"] = velho_ct


def teste_refazer_so_o_pos_recusa_o_motor_sem_cache():
    secao(u"VIG-07: refazer so o pos recusa o motor sem cache")
    import ast as _ast
    import radai_batch as B
    import radai_records as R
    checar(u"os niveis e o crânio que desenharam entram na lista",
           R.motores_que_desenharam({"LNL01_lnl": 1},
                                    {"origem": {"Brainstem": "cranio_ct"}})
           == ["cranio_ct", "hnlnl"])
    checar(u"  e o que nao desenhou nao entra",
           R.motores_que_desenharam({}, None) == [])
    campos = R.campos_do_done(modalidade="CT",
                              motores_fora_do_ts=["hnlnl"])
    base = {"modo": "auto", "cache_das_tasks": {"total_v3": "a" * 64}}
    import radai_cache_tasks as CT
    CT.armar(True)
    try:
        p = B.pos_refazivel(dict(base, **campos))
        isca = B.pos_refazivel(base)
    finally:
        CT.armar(False)
    checar(u"com os niveis no `done`, o botao nao aparece e diz por que",
           not p["refazivel"] and u"hnlnl" in p["motivo"], p)
    checar(u"ISCA: sem o campo, o botao apareceria (ou cairia so pelo cache)",
           u"hnlnl" not in isca["motivo"], isca)
    for mod in ("radai_batch.py", "radai_watcher.py"):
        arv = _ast.parse(io.open(_componentes.fonte("app/" + mod),
                                 encoding="utf-8").read())
        chamadas = [n for n in _ast.walk(arv) if isinstance(n, _ast.Call)
                    and getattr(n.func, "attr", "") == "campos_do_done"]
        checar(u"%s grava os motores no `done`" % mod,
               chamadas and all(any(k.arg == "motores_fora_do_ts"
                                    for k in c.keywords) for c in chamadas),
               len(chamadas))


def teste_a_estacao_nao_dorme_com_serie_adiada():
    secao(u"VIG-10: a estacao nao dorme com serie adiada")
    TW = _tw()
    ok, motor, mod, s, linhas = TW._rodar_anatomia(
        set(), erro_na={"total_v3": MemoryError()})
    fl = mod.read_marker(s["dir"], s["uid"], "fail") or {}
    checar(u"a serie foi adiada por recurso", fl.get("ultimo_tipo") ==
           mod.RECURSO, fl)
    falados = []
    velho_wlog = mod.wlog
    mod.wlog = lambda m="": falados.append(str(m))
    try:
        fila, _ = TW.fila_de(mod)
    finally:
        mod.wlog = velho_wlog
    checar(u"a varredura conta a adiada e quando ela volta",
           not fila and mod.STATE.get("adiadas") == 1
           and mod.STATE.get("volta_das_adiadas"),
           (len(fila), mod.STATE.get("adiadas")))
    checar(u"  e o log diz ate quando a estacao fica acordada",
           any(u"fica acordada ate" in l for l in falados), falados[-3:])
    import radai_batch as B
    with _Troca(mod, quem_esta_segmentando=lambda: None), \
            _Troca(B, estado=lambda: {}):
        mod.STATE["ligado"], mod.STATE["paused"] = True, False
        mod.STATE["n_queue"] = 0
        checar(u"fila vazia e serie adiada: a estacao continua acordada",
               mod.fila_ocupada() is True)
        mod.STATE["volta_das_adiadas"] = time.time() + 2 * 86400
        checar(u"  e fora do horizonte, nao", mod.fila_ocupada() is False)
        mod.STATE["paused"] = True
        mod.STATE["volta_das_adiadas"] = time.time() + 60
        checar(u"  e com o vigia pausado, nao", mod.fila_ocupada() is False)
        mod.STATE["paused"] = False

        def isca():
            if mod.quem_esta_segmentando() is not None:
                return True
            return bool(mod.STATE.get("ligado") and not mod.STATE.get(
                "paused") and (mod.STATE.get("n_queue") or 0) > 0)
        checar(u"ISCA: a pergunta de antes deixaria a estacao dormir",
               isca() is False)


def teste_o_plano_de_ram_ve_o_teto_da_paginacao():
    secao(u"VIG-09: o plano de RAM ve o teto da paginacao")
    import radai_cleaner as L
    ram = 16 * 1024
    livre = lambda d: 200 * 1024
    checar(u"gerenciada pelo sistema: 3x a RAM, limitada ao disco",
           L.teto_do_commit_mb(ram, [u"?:\\pagefile.sys"], livre) ==
           ram + 3 * ram)
    checar(u"  e com o disco curto, o disco mais o arquivo de agora",
           L.teto_do_commit_mb(ram, [u"C:\\pagefile.sys 0 0"],
                               lambda d: 10 * 1024, atual_mb=2048)
           == ram + 10 * 1024 + 2048)
    checar(u"tamanho fixo: o maximo declarado",
           L.teto_do_commit_mb(ram, [u"C:\\pagefile.sys 1024 4096"], livre)
           == ram + 4096)
    checar(u"sem a linha do registro: nao se sabe",
           L.teto_do_commit_mb(ram, [], livre) is None)
    est = {"precisa_mb": 14 * 1024, "conta_mb": 14 * 1024,
           "regiao": u"a grade inteira"}
    agora = {"total_mb": ram, "livre_mb": 6 * 1024, "pct": 60,
             "commit_total_mb": 20 * 1024, "commit_livre_mb": 9 * 1024}
    dec, frase = M.decidir_ram(est, dict(agora,
                                         commit_livre_no_teto_mb=40 * 1024))
    checar(u"abaixo do teto da paginacao: pagina, e o log diz o teto",
           dec == "paginar" and u"teto usado" in frase, (dec, frase))
    dec2, _f2 = M.decidir_ram(dict(est, precisa_mb=60 * 1024,
                                   conta_mb=60 * 1024),
                              dict(agora, commit_livre_no_teto_mb=40 * 1024))
    checar(u"acima do teto: adia", dec2 == "adiar", dec2)
    dec3, _f3 = M.decidir_ram(est, agora)
    checar(u"ISCA: so com o commit de agora, adiaria", dec3 == "adiar", dec3)


def _conferir_registro(chamados):
    todos = set(k for k, v in globals().items()
                if k.startswith("teste_") and callable(v))
    fora = sorted(todos - set(f.__name__ for f in chamados))
    checar(u"todo teste do arquivo esta na lista do main()", not fora,
           u"nunca chamados: " + ", ".join(fora))


def main():
    print("test_campo | a robustez do vigia pelos logs de campo")
    _TESTES = (teste_a_primeira_excecao_do_filho,
               teste_uma_classificacao_so,
               teste_o_volume_tem_de_ser_contornavel,
               teste_a_rm_segmenta_em_qualquer_orientacao,
               teste_a_serie_nao_contornavel_sai_da_fila,
               teste_o_que_saiu_da_fila_aparece_com_o_motivo,
               teste_a_triagem_ve_orientacao_e_cor,
               teste_ausencia_anatomica_nao_e_falha,
               teste_a_ausente_no_vigia_sai_ok,
               teste_o_portao_da_regiao_nas_duas_portas,
               teste_sem_repeticao_cega,
               teste_a_serie_que_falhou_vai_para_o_fim,
               teste_a_indeterminada_uma_vez_por_turno,
               teste_o_plano_olha_a_ram_e_o_commit,
               teste_o_recurso_previsto_no_vigia,
               teste_a_complementar_que_falha_nao_derruba_a_serie,
               teste_a_memoria_do_vigia_no_log,
               teste_o_cache_por_task,
               teste_a_impressao_do_volume_nao_copia_nem_segura,
               teste_o_parcial_diz_o_que_faltou,
               teste_o_parcial_na_tabela_e_no_acervo,
               teste_o_disco_do_arranque,
               teste_o_rt_utils_nao_escreve_fora_do_log,
               teste_o_resumo_da_noite,
               teste_refazer_so_o_pos,
               teste_refazer_so_o_pos_de_ponta_a_ponta,
               teste_a_falta_de_commit_e_recurso,
               teste_memoria_no_filho_nao_pausa_o_vigia,
               teste_a_frase_da_falha_sem_o_resto_do_caminho,
               teste_o_nibabel_depois_da_guarda_nao_culpa_o_exame,
               teste_a_espera_de_outra_versao_nao_volta_sozinha,
               teste_o_cache_fica_fora_da_rede_e_das_series,
               teste_a_chave_do_cache_ve_o_codigo_da_grade,
               teste_o_acerto_do_cache_nao_escreve_a_entrada,
               teste_refazer_so_o_pos_na_serie_parcial,
               teste_refazer_so_o_pos_recusa_o_motor_sem_cache,
               teste_a_estacao_nao_dorme_com_serie_adiada,
               teste_o_plano_de_ram_ve_o_teto_da_paginacao)
    _conferir_registro(_TESTES)
    for t in _TESTES:
        try:
            t()
        except Exception as e:
            import traceback
            checar("%s (excecao inesperada)" % t.__name__, False,
                   "%s: %s" % (type(e).__name__, e))
            traceback.print_exc()
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
