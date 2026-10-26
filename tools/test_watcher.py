# -*- coding: utf-8 -*-
import importlib.util
import json
import io
import os
import re
import shutil
import stat
import sys
import tempfile
import time
from datetime import datetime, timedelta

try:
    sys.stdout.reconfigure(errors="replace")
except Exception:
    pass

AQUI = os.path.dirname(os.path.abspath(__file__))


def pasta_app(aqui):
    for c in (os.path.join(aqui, "..", "app"), os.path.join(aqui, "..")):
        if os.path.exists(os.path.join(c, "radai_watcher.py")):
            return os.path.abspath(c)
    return os.path.abspath(os.path.join(aqui, "..", "app"))


APP = pasta_app(AQUI)

_TMP_BATERIA = tempfile.mkdtemp(prefix="radai_vigia_tmp_")
for _k in ("RADAI_TMP", "TEMP", "TMP", "TMPDIR"):
    os.environ[_k] = _TMP_BATERIA
tempfile.tempdir = None


def _apagar_tmp_da_bateria():
    try:
        _soltar_logs()
    except Exception as e:
        print("  (nao consegui soltar os logs no fim: %s)" % e)
    shutil.rmtree(_TMP_BATERIA, ignore_errors=True)


import atexit
atexit.register(_apagar_tmp_da_bateria)

_ACERVO_TESTE = tempfile.mkdtemp(prefix="radai_vigia_acervo_")
os.environ["RADAI_CALIB_DIR"] = _ACERVO_TESTE
_REGISTRO_TESTE = tempfile.mkdtemp(prefix="radai_vigia_registro_")
os.environ["RADAI_REGISTRO_DIR"] = _REGISTRO_TESTE
_TSHOME_TESTE = tempfile.mkdtemp(prefix="radai_vigia_tshome_")
os.environ["TOTALSEG_HOME_DIR"] = _TSHOME_TESTE
os.environ["RADAI_URL_VERSOES"] = "0"
os.environ["RADAI_NOTIFICACAO"] = "0"

sys.path.insert(0, AQUI)
from make_test_series import escreve_serie

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _cleanup
import _componentes
_cleanup.adotar_prefixo('radai_eleg_')
_cleanup.adotar_prefixo('radai_plano_')
_cleanup.adotar_prefixo('radai_fila_')
_cleanup.adotar_prefixo('radai_vigia_acervo_')
_cleanup.adotar_prefixo('radai_vigia_tmp_')
_cleanup.adotar_prefixo('radai_vigia_registro_')
_cleanup.adotar_prefixo('radai_vigia_tshome_')
atexit.register(shutil.rmtree, _TSHOME_TESTE, True)
_cleanup.adotar_prefixo('radai_arranque_')
_cleanup.adotar_prefixo('radai_t_uso_')
_cleanup.adotar_prefixo('radai_caso_vigia_')
_cleanup.adotar_prefixo('radai_caso_lote_')
_cleanup.adotar_prefixo('radai_lote_duas_portas_')
_cleanup.adotar_prefixo('radai_vigia_prof_')
_cleanup.adotar_prefixo('radai_reserva_')
_cleanup.adotar_prefixo('radai_reserva_js_')
_cleanup.adotar_prefixo('radai_familia_')
_cleanup.adotar_prefixo('radai_modalidade_')
_cleanup.adotar_prefixo('radai_tx_')
_cleanup.adotar_prefixo('radai_tx_stage_')
_cleanup.adotar_prefixo('radai_sem_tx_')
_cleanup.adotar_prefixo('radai_sem_tx_serie_')


VERBOSO = "-v" in sys.argv
_RESULTADOS = []
_TEMPS = []
_N = [0]
_MODULOS = []


def _soltar_logs():
    vistos = []
    for m in list(_MODULOS) + list(sys.modules.values()):
        if m is None or any(m is v for v in vistos):
            continue
        try:
            e_vigia = ("_LOG_FH" in vars(m) and "_LOG_TENTADO" in vars(m))
        except TypeError:
            e_vigia = False
        if e_vigia:
            vistos.append(m)
    for m in vistos:
        fh = getattr(m, "_LOG_FH", None)
        if fh is not None:
            try:
                fh.close()
            except Exception as e:
                print("  (nao consegui fechar o log de uma instancia: %s)" % e)
        try:
            m._LOG_FH = None
            m._LOG_TENTADO = True
        except Exception as e:
            print("  (nao consegui soltar o log de uma instancia: %s)" % e)


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


CFG_BASE = {"DRY_RUN": "1", "MIN_SLICES": "5", "QUIET_MIN": "0",
            "SCAN_EVERY_MIN": "60", "LOCK_MAX_H": "2", "HEARTBEAT_MIN": "5",
            "MAX_RETRIES": "3", "DAYS_BACK": "0", "MODALITIES": "CT"}


def _porta_livre():
    import socket as _s
    with _s.socket(_s.AF_INET, _s.SOCK_STREAM) as sk:
        sk.bind(("127.0.0.1", 0))
        return int(sk.getsockname()[1])


def _esperar_o_vigia(proc, porta, maquina, prazo=180.0):
    import urllib.request as _ur
    t0 = time.time()
    while time.time() - t0 < prazo:
        if proc.poll() is not None:
            return False, u"o processo SAIU (codigo %s) depois de %.0f s" % (
                proc.returncode, time.time() - t0)
        try:
            d = json.loads(_ur.urlopen(
                "http://127.0.0.1:%d/api/status" % porta,
                timeout=2).read().decode("utf-8"))
            if d.get("machine") == maquina:
                return True, u"respondeu em %.0f s" % (time.time() - t0)
        except Exception:
            pass
        time.sleep(0.5)
    return False, u"nao respondeu em %.0f s, e o processo continua vivo" % prazo


def _aceite_da_bateria(CS, maquina):
    import json as _json
    import subprocess
    itens = [k for k, _t, _d in CS.PONTOS]
    cod = ("import sys, json; sys.path.insert(0, %r); import radai_consent "
           "as C; print(json.dumps(C.montar_registro('bateria', %r)))"
           % (APP, itens))
    try:
        r = subprocess.run([sys.executable, "-c", cod], stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE, timeout=120)
        reg = _json.loads(r.stdout.decode("utf-8").strip().splitlines()[-1])
    except Exception:
        reg = {"versao": CS.VERSAO_DOCS, "quem": u"bateria", "itens": itens,
               "quando": u"2026-09-22 00:00:00"}
    reg["maquina"] = maquina
    return reg


def novo_temp(prefixo="radai_t_"):
    d = tempfile.mkdtemp(prefix=prefixo)
    _TEMPS.append(d)
    return d


def montar(series, extra=None, machine="PC_A"):
    base = novo_temp()
    root = os.path.join(base, "share")
    for pid, quando, n in series:
        pasta = os.path.join(root, pid, "CT_" + quando.strftime("%Y%m%d_%H%M"))
        escreve_serie(pasta, pid, quando, n)
    return carregar(root, base, extra, machine), root, base


def carregar(root, base, extra=None, machine="PC_A"):
    cfg = dict(CFG_BASE)
    cfg.update({"ROOT": root, "LOG_DIR": os.path.join(base, "log_" + machine)})
    cfg.update(extra or {})
    caminho_cfg = os.path.join(base, "cfg_%s_%d.config" % (machine, _N[0]))
    with open(caminho_cfg, "w", encoding="utf-8") as f:
        for k, v in cfg.items():
            f.write("%s=%s\n" % (k, v))

    _N[0] += 1
    os.environ["RADAI_CONFIG"] = caminho_cfg
    os.environ["RADAI_MACHINE"] = machine
    os.environ["LOCALAPPDATA"] = os.path.join(base, "appdata_" + machine)
    try:
        spec = importlib.util.spec_from_file_location(
            "vigia_%d" % _N[0], _componentes.fonte("app/radai_watcher.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.STATE["ligado"] = True
        _MODULOS.append(mod)
        return mod
    finally:
        os.environ.pop("RADAI_CONFIG", None)
        os.environ.pop("RADAI_MACHINE", None)


def envelhecer(root, minutos):
    quando = time.time() - minutos * 60
    for d, _, fs in os.walk(root):
        for f in fs:
            try:
                os.utime(os.path.join(d, f), (quando, quando))
            except Exception:
                pass
        try:
            os.utime(d, (quando, quando))
        except Exception:
            pass


def fila_de(mod):
    series, done = mod.scan_root()
    return mod.build_queue(series, done), series


def pids_da_fila(fila):
    return [s["pid"] for s in fila]


def teste_o_vigia_pula_a_saida_do_dicombridge():
    secao("o vigia nao desce na pasta que o DicomBridge gravou")
    agora = datetime.now()
    mod, root, base = montar([("PAC_ORIGEM", agora - timedelta(days=2), 8)])
    saida = "DICOM_BRIDGE_" + agora.strftime("%Y%m%d_%H%M%S")
    escreve_serie(os.path.join(root, "PAC_ORIGEM", saida, "CT"), "PAC_COPIA",
                  agora - timedelta(days=2), 8)
    envelhecer(root, 60)
    series, _ = mod.scan_root()
    pids = sorted(s["pid"] for s in series.values())
    checar("a copia gravada pelo DicomBridge nao entra na fila",
           pids == ["PAC_ORIGEM"], str(pids))


def teste_ordem_primeira_execucao():
    secao("ordem: primeira execucao = da mais recente para tras")
    agora = datetime.now()
    mod, root, base = montar([
        ("PAC_ANTIGA", agora - timedelta(days=300), 8),
        ("PAC_MEIO", agora - timedelta(days=100), 8),
        ("PAC_NOVA", agora - timedelta(days=2), 8),
    ])
    envelhecer(root, 60)
    fila, _ = fila_de(mod)
    checar("as 3 series entraram na fila", len(fila) == 3, str(pids_da_fila(fila)))
    checar("primeira execucao comeca pela MAIS RECENTE",
           pids_da_fila(fila) == ["PAC_NOVA", "PAC_MEIO", "PAC_ANTIGA"],
           str(pids_da_fila(fila)))


def teste_ordem_com_concluidas():
    secao("ordem: novas (apos a ultima concluida) antes do backlog")
    agora = datetime.now()
    mod, root, base = montar([
        ("PAC_VELHA1", agora - timedelta(days=300), 8),
        ("PAC_VELHA2", agora - timedelta(days=200), 8),
        ("PAC_MARCO", agora - timedelta(days=100), 8),
        ("PAC_NOVA1", agora - timedelta(days=10), 8),
        ("PAC_NOVA2", agora - timedelta(days=3), 8),
    ])
    envelhecer(root, 60)
    series, _ = mod.scan_root()
    marco = [s for s in series.values() if s["pid"] == "PAC_MARCO"][0]
    mod.claim(marco["dir"], marco["uid"], {})
    mod.process_series(marco)

    fila, _ = fila_de(mod)
    ordem = pids_da_fila(fila)
    checar("a concluida saiu da fila", "PAC_MARCO" not in ordem, str(ordem))
    checar("novas primeiro, da mais ANTIGA para a mais recente",
           ordem[:2] == ["PAC_NOVA1", "PAC_NOVA2"], str(ordem))
    checar("depois o backlog, da mais RECENTE para tras",
           ordem[2:] == ["PAC_VELHA2", "PAC_VELHA1"], str(ordem))


def teste_days_back():
    secao("DAYS_BACK: recorte pela data da SERIE, nao do arquivo")
    agora = datetime.now()
    mod, root, base = montar([
        ("PAC_ANTIGA", agora - timedelta(days=200), 8),
        ("PAC_RECENTE", agora - timedelta(days=5), 8),
    ], extra={"DAYS_BACK": "30"})
    envelhecer(root, 60)
    fila, series = fila_de(mod)
    checar("DAYS_BACK=30 mantem so a serie recente",
           pids_da_fila(fila) == ["PAC_RECENTE"], str(pids_da_fila(fila)))
    checar("a serie antiga sumiu do indice", len(series) == 1, "%d series" % len(series))


def teste_duas_maquinas():
    secao("duas maquinas na mesma serie")
    agora = datetime.now()
    mod_a, root, base = montar([("PAC_1", agora - timedelta(days=1), 8)], machine="PC_A")
    envelhecer(root, 60)
    mod_b = carregar(root, base, machine="PC_B")

    fila_a, _ = fila_de(mod_a)
    fila_b, _ = fila_de(mod_b)
    checar("as duas maquinas veem a mesma serie",
           len(fila_a) == 1 and len(fila_b) == 1)

    s_a, s_b = fila_a[0], fila_b[0]
    ok_a = mod_a.claim(s_a["dir"], s_a["uid"], {"machine": "PC_A"})
    ok_b = mod_b.claim(s_b["dir"], s_b["uid"], {"machine": "PC_B"})
    checar("so UMA maquina reivindica a serie", ok_a != ok_b,
           "A=%s B=%s" % (ok_a, ok_b))

    perdedora, vencedora = (mod_b, mod_a) if ok_a else (mod_a, mod_b)
    s_p = s_b if ok_a else s_a
    perdedora.unclaim(s_p["dir"], s_p["uid"])
    checar("a perdedora NAO consegue liberar o lock alheio",
           perdedora.has_marker(s_p["dir"], s_p["uid"], "lock"))

    vencedora.process_series(s_a if ok_a else s_b)
    checar("o dono conclui e libera o lock",
           not vencedora.has_marker(s_a["dir"], s_a["uid"], "lock"))
    checar("marcador done gravado", vencedora.has_marker(s_a["dir"], s_a["uid"], "done"))

    fila_b2, _ = fila_de(mod_b)
    checar("a outra maquina nao reprocessa a serie concluida", len(fila_b2) == 0,
           str(pids_da_fila(fila_b2)))


def teste_tres_estados_do_lock():
    secao("os tres estados do lock: trabalhando, travado, morto")
    agora = datetime.now()
    mod, root, base = montar([("PAC_1", agora - timedelta(days=1), 8)],
                             extra={"LOCK_PARADO_MIN": "15"}, machine="PC_A")
    envelhecer(root, 60)
    fila, _ = fila_de(mod)
    s = fila[0]

    def escreve(**kw):
        p = mod.m_path(s["dir"], s["uid"], "lock", criar=True)
        d = {"machine": mod.MACHINE, "pid_os": os.getpid(),
             "token": mod._token(), "heartbeat": time.time()}
        d.update(kw)
        p.write_text(json.dumps(d), encoding="utf-8")
        return p

    def est():
        return mod._diagnostico_do_lock(s["dir"], s["uid"])[0]

    escreve(heartbeat=time.time())
    checar("heartbeat de agora: TRABALHANDO", est() == "trabalhando", est())

    p = escreve(heartbeat=time.time())
    v = time.time() - 3 * 3600
    os.utime(str(p), (v, v))
    checar("arquivo de 3h com heartbeat vivo: AINDA trabalhando "
           "(a serie longa nao e roubada)", est() == "trabalhando", est())

    escreve(heartbeat=time.time() - 40 * 60,
            criado=mod._criado_em(os.getpid()))
    checar("heartbeat parado + processo vivo: TRAVADO", est() == "travado", est())

    escreve(heartbeat=time.time() - 40 * 60, pid_os=999999)
    checar("heartbeat parado + pid inexistente: MORTO", est() == "morto", est())

    escreve(heartbeat=time.time() - 40 * 60, machine="OUTRA", pid_os=4321)
    checar("de outra maquina e parado: TRAVADO (assume, mas nao mata)",
           est() == "travado", est())

    escreve(heartbeat=time.time(), machine="OUTRA", pid_os=4321)
    checar("de outra maquina e viva: TRABALHANDO (nao se toca)",
           est() == "trabalhando", est())

    img = mod._imagem_do_processo(os.getpid())
    checar("acha a imagem do proprio processo",
           "python" in (img or "").lower(), str(img))
    checar("pid inexistente devolve vazio",
           mod._imagem_do_processo(999999) in ("", None))
    checar("NAO mata processo que nao e Python",
           mod._matar_travado(4, s["uid"]) is False)

    escreve(heartbeat=time.time(), machine="OUTRA", pid_os=4321)
    checar("lock trabalhando: claim recusa",
           not mod.claim(s["dir"], s["uid"], {"machine": mod.MACHINE}))
    escreve(heartbeat=time.time() - 40 * 60, machine="OUTRA", pid_os=4321)
    checar("lock de outra maquina, parado: claim ASSUME",
           mod.claim(s["dir"], s["uid"],
                     {"machine": mod.MACHINE, "pid_os": os.getpid()}))
    d = mod.read_marker(s["dir"], s["uid"], "lock")
    checar("e o lock novo e desta maquina", d.get("machine") == mod.MACHINE)


def teste_lock_abandonado():
    secao("lock abandonado (maquina caiu) x lock com sinal de vida")
    agora = datetime.now()
    mod_a, root, base = montar([("PAC_1", agora - timedelta(days=1), 8)],
                               extra={"LOCK_MAX_H": "1"}, machine="PC_A")
    envelhecer(root, 60)
    fila, _ = fila_de(mod_a)
    s = fila[0]
    mod_a.claim(s["dir"], s["uid"], {"machine": "PC_A"})

    mod_b = carregar(root, base, extra={"LOCK_MAX_H": "1"}, machine="PC_B")
    checar("lock recente nao e roubado", not mod_b.claim(s["dir"], s["uid"], {}))

    lp = mod_a.m_path(s["dir"], s["uid"], "lock")
    velho = time.time() - 3 * 3600
    d = json.loads(lp.read_text(encoding="utf-8"))
    d["heartbeat"] = velho
    lp.write_text(json.dumps(d), encoding="utf-8")
    os.utime(str(lp), (velho, velho))
    checar("lock sem sinal de vida ha 3h e assumido por outra maquina",
           mod_b.claim(s["dir"], s["uid"], {"machine": "PC_B"}))

    mod_b.renovar_lock(s["dir"], s["uid"])
    mod_c = carregar(root, base, extra={"LOCK_MAX_H": "1"}, machine="PC_C")
    checar("lock RENOVADO (serie longa) nao e roubado",
           not mod_c.claim(s["dir"], s["uid"], {}))
    dono = mod_b.read_marker(s["dir"], s["uid"], "lock")
    checar("o lock registra quem e o dono", "PC_B" in str(dono.get("token")), str(dono))


def teste_serie_incompleta():
    secao("serie incompleta nao vira RTSTRUCT nem marcador done")
    agora = datetime.now()
    mod, root, base = montar([("PAC_1", agora - timedelta(days=1), 12)])
    envelhecer(root, 60)
    series, _ = mod.scan_root()
    s = list(series.values())[0]
    checar("indexou 12 cortes", s["count"] == 12, str(s["count"]))

    arquivos = sorted(os.listdir(s["dir"]))[:4]
    for f in arquivos:
        os.remove(os.path.join(s["dir"], f))

    mod.claim(s["dir"], s["uid"], {})
    ok = mod.process_series(s)
    checar("processamento FALHA quando faltam cortes", not ok)
    checar("nao gravou marcador done", not mod.has_marker(s["dir"], s["uid"], "done"))
    checar("gravou marcador fail", mod.has_marker(s["dir"], s["uid"], "fail"))
    fl = mod.read_marker(s["dir"], s["uid"], "fail")
    checar("o fail explica o motivo", "incompleta" in str(fl.get("last_error", "")),
           str(fl.get("last_error"))[:70])
    checar("nenhuma saida foi gravada na pasta",
           not any(f.startswith("RS_RadAI") for f in os.listdir(s["dir"])))


def teste_serie_em_transito():
    secao("serie ainda chegando fica para a proxima volta")
    agora = datetime.now()
    mod, root, base = montar([("PAC_CHEGANDO", agora - timedelta(days=1), 8)],
                             extra={"QUIET_MIN": "10"})
    fila, _ = fila_de(mod)
    checar("serie recem-chegada NAO entra na fila", len(fila) == 0, str(pids_da_fila(fila)))
    checar("o painel informa quantas estao em transito", mod.STATE["em_transito"] == 1,
           str(mod.STATE["em_transito"]))

    envelhecer(root, 30)
    fila2, _ = fila_de(mod)
    checar("passado o periodo de quarentena, entra na fila", len(fila2) == 1)


def teste_max_retries():
    secao("serie que falha 3x e pulada")
    agora = datetime.now()
    mod, root, base = montar([("PAC_1", agora - timedelta(days=1), 8)])
    envelhecer(root, 60)
    series, _ = mod.scan_root()
    s = list(series.values())[0]
    for i in range(3):
        mod.m_path(s["dir"], s["uid"], "fail", criar=True).write_text(
            '{"tries": %d}' % (i + 1), encoding="utf-8")
        fila, _ = fila_de(mod)
        esperado = 0 if i + 1 >= 3 else 1
        checar("apos %d falha(s), na fila: %d" % (i + 1, esperado), len(fila) == esperado)


def teste_pasta_somente_leitura():
    secao("pasta somente-leitura nao trava o vigia")
    if os.name != "nt":
        checar("teste de somente-leitura (so no Windows)", True, "pulado")
        return
    agora = datetime.now()
    mod, root, base = montar([("PAC_RO", agora - timedelta(days=1), 8)])
    envelhecer(root, 60)
    series, _ = mod.scan_root()
    s = list(series.values())[0]

    os.system('icacls "%s" /deny "%s":(AD) >nul 2>&1' % (s["dir"], os.environ.get("USERNAME", "")))
    try:
        ok = mod.claim(s["dir"], s["uid"], {})
        checar("claim falha sem derrubar o vigia", not ok)
        checar("a pasta entra na lista de sem-permissao",
               str(s["dir"]) in mod.SEM_PERMISSAO)
        fila, _ = fila_de(mod)
        checar("a pasta sem permissao sai da fila (nao insiste para sempre)",
               len(fila) == 0, str(pids_da_fila(fila)))
    finally:
        os.system('icacls "%s" /remove:d "%s" >nul 2>&1' % (s["dir"], os.environ.get("USERNAME", "")))


class _MotorFalso(object):

    def __init__(self, erro):
        self.erro = erro

    def _job_new(self):
        return "job_teste"

    def _job(self, jid):
        return {"log": []}

    def _job_del(self, jid):
        pass

    def copy_sorted(self, arquivos, destino):
        pass

    def load_sitk(self, pasta):
        return object()

    def _resolve_device(self, escolha):
        return "cpu"

    def drenar_log(self, jid, escrever, parar, a_cada_s=None, intervalo=3.0):
        escrever("(dublê do motor: sem log para drenar)")
        return None

    def run_ts_task(self, *a, **kw):
        raise RuntimeError(self.erro)

    def conferir_volume_contornavel(self, img, min_cortes=None,
                                    modalidade=None):
        return None

    VERSAO_DA_RECEITA_POS = u"receita-da-dubla"

    def rodar_tasks(self, *a, **kw):
        return _motor_do_teste().rodar_tasks(*a, **kw)


ERRO_AMBIENTE = ("TS total saiu com codigo 1. python.exe: Error while finding module "
                 "specification for 'totalsegmentator.bin.TotalSegmentator' "
                 "(ModuleNotFoundError: No module named 'totalsegmentator')")


def teste_classificacao_de_erro_de_ambiente():
    secao("o que e erro de ambiente e o que e da serie")
    mod, root, base = montar([])
    for msg in (ERRO_AMBIENTE,
                "ModuleNotFoundError: No module named 'torch'",
                "ImportError: DLL load failed while importing _C",
                "No module named 'pkg_resources'"):
        checar("ambiente: %s" % msg[:44], mod.erro_de_ambiente(msg) is True)
    for msg in ("serie incompleta: achei 8 dos 12 cortes indexados",
                "nenhuma estrutura gerada",
                "TS total estourou o tempo limite (3h)",
                "3 arquivo(s) da serie ilegiveis (rede instavel?)"):
        checar("da serie: %s" % msg[:44], mod.erro_de_ambiente(msg) is False)
    ok, detalhe = mod.conferir_ambiente()
    checar("em DRY_RUN o pre-voo passa sem chamar a IA", ok is True)
    checar("e diz por que", "simulacao" in detalhe.lower(), detalhe)


def teste_falha_de_ambiente_nao_queima_a_fila():
    secao("falha de ambiente nao vira falha de serie")
    agora = datetime.now()
    mod, root, base = montar([("PAC_1", agora - timedelta(days=1), 8),
                              ("PAC_2", agora - timedelta(days=2), 8)],
                             extra={"DRY_RUN": "0"})
    envelhecer(root, 60)
    series, done_dates = mod.scan_root()
    fila = mod.build_queue(series, done_dates)
    checar("as duas series entraram na fila", len(fila) == 2, str(len(fila)))
    if len(fila) != 2:
        return

    mod.carregar_engine = lambda: _MotorFalso(ERRO_AMBIENTE)
    s = fila[0]
    mod.claim(s["dir"], s["uid"], {})
    ok = mod.process_series(s)
    checar("a serie nao conclui", ok is False)
    checar("NAO escreveu marcador de falha na serie",
           not mod.has_marker(s["dir"], s["uid"], "fail"))
    checar("o vigia se pausou sozinho em vez de mastigar a fila",
           mod.STATE["paused"] is True)
    checar("e registra que o problema e o ambiente",
           "totalsegmentator" in mod.STATE["ambiente_erro"].lower(),
           mod.STATE["ambiente_erro"])
    fila2 = mod.build_queue(*mod.scan_root())
    checar("as series continuam na fila, esperando o ambiente ser corrigido",
           len(fila2) == 2, str(len(fila2)))

    mod.carregar_engine = lambda: _MotorFalso("serie corrompida: cabecalho ilegivel no corte 3")
    mod.STATE["paused"] = False
    mod.STATE["ambiente_erro"] = ""
    s2 = fila[1]
    mod.claim(s2["dir"], s2["uid"], {})
    mod.process_series(s2)
    checar("falha comum CONTINUA gastando tentativa da serie",
           mod.has_marker(s2["dir"], s2["uid"], "fail"))
    checar("e NAO para o vigia", mod.STATE["paused"] is False)
    checar("nem inventa erro de ambiente", mod.STATE["ambiente_erro"] == "",
           mod.STATE["ambiente_erro"])


def _motor_do_teste():
    return _app_import("engine")


def teste_progresso_nao_afoga_o_log():
    secao("batida de progresso nao afoga o log")
    mod, root, base = montar([])
    f = _motor_do_teste().FiltroProgresso(a_cada_s=120)
    checar("a primeira batida passa (o operador precisa saber que comecou)",
           f.passa("TS total rodando... 10s (still working, please wait)", agora=1000.0))
    checar("a de 10s depois nao passa",
           not f.passa("TS total rodando... 20s (still working, please wait)", agora=1010.0))
    checar("a de 60s depois ainda nao passa",
           not f.passa("TS total rodando... 70s (still working, please wait)", agora=1060.0))
    checar("passados os 120s, volta a passar",
           f.passa("TS total rodando... 130s (still working, please wait)", agora=1125.0))

    for texto in ("TS total (iniciando)", "montando RTSTRUCT (75 estruturas)",
                  "ERRO: nnUNet ficou sem memoria", "=== OK ...12345678 ==="):
        checar("linha que nao e progresso passa sempre: %s" % texto[:34],
               f.passa(texto, agora=1126.0))

    f2 = _motor_do_teste().FiltroProgresso(a_cada_s=120)
    passaram = sum(1 for i in range(240)
                   if f2.passa("TS total rodando... %ds (still working)" % (i * 10),
                               agora=2000.0 + i * 10))
    checar("40 min de task viram ~20 linhas, nao 240", passaram <= 21, str(passaram))
    checar("mas nao viram zero (o painel tem de mostrar que esta vivo)", passaram >= 15,
           str(passaram))


def teste_erro_sem_barra_de_progresso():
    secao("mensagem de erro sem a barra do tqdm")
    mod, root, base = montar([])
    cru = (u"TS total passou do tempo limite (3600 s) e foi encerrada. "
           u"█▊    | 28/48 [05:02<03:36, 10.80s/it]  60%|██████    "
           u"| 29/48 [05:13<03:24, 10.77s/it]  83%|████████▎ | "
           u"40/48 [07:12<01:26, 10.86s/it]")
    limpo = mod.limpar_erro(cru)
    checar("o motivo real sobrevive",
           "passou do tempo limite (3600 s)" in limpo, limpo[:90])
    checar("a barra de progresso sai", "|" not in limpo and "s/it]" not in limpo, limpo[:90])
    checar("os blocos saem", u"█" not in limpo, limpo[:90])
    checar("e o resultado cabe no marcador", len(limpo) < 200, str(len(limpo)))
    normal = mod.limpar_erro("serie incompleta: achei 8 dos 12 cortes indexados")
    checar("mensagem limpa passa intacta",
           normal == "serie incompleta: achei 8 dos 12 cortes indexados", normal)


def teste_liberar_series_puladas():
    secao("liberar series puladas por falha repetida")
    agora = datetime.now()
    mod, root, base = montar([("PAC_1", agora - timedelta(days=1), 8),
                              ("PAC_2", agora - timedelta(days=2), 8)])
    envelhecer(root, 60)
    series, done_dates = mod.scan_root()

    for uid, s in series.items():
        mod.m_path(s["dir"], uid, "fail", criar=True).write_text(
            '{"tries": 3, "last_error": "causa unica ja corrigida"}', encoding="utf-8")

    fila = mod.build_queue(series, done_dates)
    checar("as series somem da fila", len(fila) == 0, str(len(fila)))
    checar("mas ficam contabilizadas como puladas",
           len(mod.PULADAS_POR_FALHA) == 2, str(len(mod.PULADAS_POR_FALHA)))

    r = mod.liberar_falhas()
    checar("liberou as duas", r["liberadas"] == 2, str(r))
    checar("sem erro", r["erros"] == 0, str(r))
    checar("nenhum marcador de falha sobrou",
           not any(mod.has_marker(s["dir"], uid, "fail") for uid, s in series.items()))
    checar("o painel para de acusar puladas", mod.STATE["puladas"] == 0)
    checar("e pede nova varredura", mod.RESCAN_NOW.is_set())

    fila2 = mod.build_queue(*mod.scan_root())
    checar("as series voltam para a fila", len(fila2) == 2, str(len(fila2)))

    uid0, s0 = list(series.items())[0]
    mod.m_path(s0["dir"], uid0, "done", criar=True).write_text('{"uid": "x"}', encoding="utf-8")
    with open(os.path.join(s0["dir"], "RS_RadAI_x_%s.dcm" % uid0[-8:].lower()),
              "wb") as f:
        f.write(b"\0" * 200)
    mod.build_queue(*mod.scan_root())
    mod.liberar_falhas()
    checar("marcador de serie concluida continua intacto",
           mod.has_marker(s0["dir"], uid0, "done"))


def teste_varredura_nao_suja_o_share():
    secao("varredura nao cria _RadAI em pasta nenhuma")
    agora = datetime.now()
    mod, root, base = montar([("PAC_1", agora - timedelta(days=1), 8),
                              ("PAC_2", agora - timedelta(days=2), 8)])
    envelhecer(root, 60)
    fila, _ = fila_de(mod)
    criadas = []
    for d, dirs, _ in os.walk(root):
        criadas += [os.path.join(d, x) for x in dirs if x == "_RadAI"]
    checar("nenhuma pasta _RadAI criada so por varrer e montar a fila",
           not criadas, str(criadas))

    s = fila[0]
    mod.claim(s["dir"], s["uid"], {})
    checar("_RadAI so aparece quando a serie e reivindicada",
           os.path.isdir(os.path.join(s["dir"], "_RadAI")))


def teste_root_vazio_e_inerte():
    secao("ROOT vazio: o vigia sobe e nao toca em nada")
    base = novo_temp()
    mod = carregar("", base, machine="PC_INERTE")
    checar("ROOT vazio nao derruba o modulo", mod.ROOT == "")
    estado = {"fila": None, "proxima_varredura": 0.0}
    t0 = time.time()
    mod._uma_volta(estado)
    checar("uma volta com ROOT vazio nao faz nada", estado["fila"] is None)
    checar("e nao trava", time.time() - t0 < 10)


def teste_config_tolerante():
    secao("config mal digitado nao mata o vigia")
    agora = datetime.now()
    mod, root, base = montar(
        [("PAC_1", agora - timedelta(days=1), 8)],
        extra={"PORT": "8777 # painel", "MIN_SLICES": "vinte",
               "LOCK_MAX_H": "2,5", "CHAVE_INVENTADA": "1",
               "GUIA_VISTO": "1"})
    checar("comentario na mesma linha nao quebra a porta", mod.PORT == 8777, str(mod.PORT))
    checar("numero invalido cai no padrao", mod.MIN_SLICES == 20, str(mod.MIN_SLICES))
    checar("virgula decimal e aceita", abs(mod.LOCK_MAX_S - 2.5 * 3600) < 1, str(mod.LOCK_MAX_S))
    checar("chave desconhecida vira aviso, nao erro",
           any("CHAVE_INVENTADA" in a for a in mod.AVISOS_CFG), str(mod.AVISOS_CFG))
    checar(u"GUIA_VISTO, que o guia grava, e chave conhecida (sem aviso a "
           u"cada arranque)",
           "GUIA_VISTO" in mod.DEFAULTS
           and not [a for a in mod.AVISOS_CFG if "GUIA_VISTO" in a],
           str(mod.AVISOS_CFG))
    checar(u"  e nao vira caixa de texto no /config (o guia tem a tela dele)",
           "GUIA_VISTO" in _app_import("radai_panel").FORA_DA_TELA)


def teste_chave_renomeada_continua_sendo_lida():
    secao("config: a chave renomeada continua sendo lida")
    agora = datetime.now()

    mod, _r, _b = montar([("PAC_1", agora - timedelta(days=1), 8)],
                         extra={"INCLUIR_VISTA3D": "1",
                                "TIMEOUT_VISTA_H": "6"})
    checar("a chave VELHA do NV nao liga motor nenhum (a chave saiu)",
           not hasattr(mod, "INCLUIR_NV") and not hasattr(mod, "TIMEOUT_NV_S"),
           str([n for n in ("INCLUIR_NV", "TIMEOUT_NV_S") if hasattr(mod, n)]))
    checar("  e o arranque diz «chave obsoleta ignorada», e nao «desconhecida»",
           any("chave obsoleta ignorada: INCLUIR_VISTA3D" in a
               for a in mod.AVISOS_CFG)
           and not [a for a in mod.AVISOS_CFG
                    if "desconhecida" in a and "VISTA" in a],
           str(mod.AVISOS_CFG))
    checar("o apelido de chave, que ninguem usava, saiu (ALIAS_CFG)",
           not hasattr(mod, "ALIAS_CFG"))


def teste_as_chaves_que_sairam_e_entraram_na_v83():
    secao(u"config da v8.3: as chaves que sairam e as que entraram")
    agora = datetime.now()
    velhas = {"INCLUIR_NV": "1", "INCLUIR_CADS": "1", "INCLUIR_MOOSE": "1",
              "INCLUIR_HNLNL": "1", "ENTREGAR_TS": "1",
              "URL_VERSOES": "https://exemplo.invalid/x", "TIMEOUT_NV_H": "6"}
    mod, _r, base = montar([("PAC_1", agora - timedelta(days=1), 8)],
                           extra=velhas)
    for k in sorted(velhas):
        n = [a for a in mod.AVISOS_CFG if "chave obsoleta ignorada: %s " % k in a]
        checar(u"`%s` no config: UMA linha «chave obsoleta ignorada»" % k,
               len(n) == 1, str(n))
    checar(u"  e nenhuma delas cai em «chave desconhecida»",
           not [a for a in mod.AVISOS_CFG if "desconhecida" in a
                and any(k in a for k in velhas)], str(mod.AVISOS_CFG))
    checar(u"  e nenhuma vira global do vigia (nada que as leia)",
           not [k for k in ("INCLUIR_NV", "INCLUIR_CADS", "INCLUIR_MOOSE",
                            "INCLUIR_HNLNL", "ENTREGAR_TS", "ENTREGAR_NV",
                            "TIMEOUT_NV_S") if hasattr(mod, k)],
           str([k for k in ("INCLUIR_NV", "ENTREGAR_TS", "INCLUIR_HNLNL")
                if hasattr(mod, k)]))
    checar(u"  e o endereco das versoes NAO vem do config",
           mod.URL_VERSOES != "https://exemplo.invalid/x", mod.URL_VERSOES)
    velho = os.environ.get("RADAI_URL_VERSOES")
    try:
        os.environ.pop("RADAI_URL_VERSOES", None)
        de_fabrica = mod.url_das_versoes()
        os.environ["RADAI_URL_VERSOES"] = "https://espelho.invalid/releases"
        espelho = mod.url_das_versoes()
        os.environ["RADAI_URL_VERSOES"] = "0"
        desligada = mod.url_das_versoes()
    finally:
        if velho is None:
            os.environ.pop("RADAI_URL_VERSOES", None)
        else:
            os.environ["RADAI_URL_VERSOES"] = velho
    checar(u"o endereco das versoes: o do CODIGO sem a variavel, o espelho "
           u"com ela, e `0` desliga",
           de_fabrica.startswith("https://github.com/")
           and espelho == "https://espelho.invalid/releases"
           and desligada == "", str((de_fabrica, espelho, desligada)))
    p = os.path.join(novo_temp(), "duas.config")
    with open(p, "w", encoding="utf-8") as f:
        f.write("ENTREGAR_TS=1\nENTREGAR_TS=0\n")
    velho_path = mod.CFG_PATH
    antes = list(mod.AVISOS_CFG)
    try:
        del mod.AVISOS_CFG[:]
        mod.CFG_PATH = type(velho_path)(p)
        mod.load_cfg()
        n = [a for a in mod.AVISOS_CFG if "ENTREGAR_TS" in a]
    finally:
        mod.CFG_PATH = velho_path
        del mod.AVISOS_CFG[:]
        mod.AVISOS_CFG.extend(antes)
    checar(u"a mesma chave obsoleta duas vezes no arquivo: UMA linha",
           len(n) == 1, str(n))
    checar(u"TRAVA_* de fabrica: 15 min, 30 min, 95%",
           mod.TRAVA_SEM_PULSO_S == 900 and mod.TRAVA_PAGINANDO_S == 1800
           and mod.TRAVA_RAM_PCT == 95,
           str((mod.TRAVA_SEM_PULSO_S, mod.TRAVA_PAGINANDO_S,
                mod.TRAVA_RAM_PCT)))
    checar(u"  e `regra_de_travamento` as entrega na forma do motor (min e %)",
           mod.regra_de_travamento() == {"sem_pulso_min": 15.0,
                                         "paginando_min": 30.0,
                                         "ram_pct": 95.0},
           str(mod.regra_de_travamento()))
    checar(u"IDIOMA de fabrica e vazio (automatico)", mod.IDIOMA == "",
           repr(mod.IDIOMA))
    mod2, _r2, _b2 = montar([("PAC_1", agora - timedelta(days=1), 8)],
                            extra={"TRAVA_SEM_PULSO_MIN": "20",
                                   "TRAVA_PAGINANDO_MIN": "45 # disco lento",
                                   "TRAVA_RAM_PCT": "90", "IDIOMA": "en"})
    checar(u"TRAVA_* do arquivo chegam ao global (20 min, 45 min, 90%)",
           mod2.TRAVA_SEM_PULSO_S == 1200 and mod2.TRAVA_PAGINANDO_S == 2700
           and mod2.TRAVA_RAM_PCT == 90,
           str((mod2.TRAVA_SEM_PULSO_S, mod2.TRAVA_PAGINANDO_S,
                mod2.TRAVA_RAM_PCT)))
    checar(u"IDIOMA=en chega ao global", mod2.IDIOMA == "en", repr(mod2.IDIOMA))
    _ef = _motor_do_teste().trava_efetiva(mod2.regra_de_travamento())
    checar(u"  e chegam ao MOTOR: `trava_efetiva` le 20 min, 45 min, 90%",
           _ef == {"sem_pulso_min": 20.0, "paginando_min": 45.0,
                   "ram_pct": 90.0}, str(_ef))
    _velha = {"sem_pulso_s": mod2.TRAVA_SEM_PULSO_S,
              "paginando_s": mod2.TRAVA_PAGINANDO_S,
              "ram_pct": float(mod2.TRAVA_RAM_PCT)}
    checar(u"  ISCA: a forma de antes (em segundos) cai no padrao do motor "
           u"(15 e 30) -- o config seria ignorado calado",
           _motor_do_teste().trava_efetiva(_velha)["sem_pulso_min"] == 15.0,
           str(_motor_do_teste().trava_efetiva(_velha)))
    mod2.CFG["TRAVA_RAM_PCT"] = "80"
    mod2.CFG["IDIOMA"] = "pt"
    mod2.aplicar_cfg()
    checar(u"a recarga a quente rele TRAVA_RAM_PCT e IDIOMA (canonico: pt -> "
           u"pt-BR)", mod2.TRAVA_RAM_PCT == 80 and mod2.IDIOMA == "pt-BR",
           str((mod2.TRAVA_RAM_PCT, mod2.IDIOMA)))
    mod2.CFG["IDIOMA"] = "xx-lixo"
    del mod2.AVISOS_CFG[:]
    mod2.aplicar_cfg()
    checar(u"IDIOMA que a instalacao nao conhece vira automatico, com aviso",
           mod2.IDIOMA == ""
           and any("IDIOMA" in a for a in mod2.AVISOS_CFG),
           str((mod2.IDIOMA, mod2.AVISOS_CFG)))
    mod2.CFG.update({"TRAVA_SEM_PULSO_MIN": "0.1", "TRAVA_RAM_PCT": "10",
                     "TRAVA_PAGINANDO_MIN": "abc"})
    mod2.aplicar_cfg()
    checar(u"os pisos do travamento seguram valor absurdo (2 min, 50%) e "
           u"texto cai no padrao",
           mod2.TRAVA_SEM_PULSO_S == 120 and mod2.TRAVA_RAM_PCT == 50
           and mod2.TRAVA_PAGINANDO_S == 1800,
           str((mod2.TRAVA_SEM_PULSO_S, mod2.TRAVA_RAM_PCT,
                mod2.TRAVA_PAGINANDO_S)))
    RB = _app_import("radai_batch")
    antes_lote = dict(RB._CFG)
    try:
        for k in ("incluir_nv", "incluir_vista", "incluir_cads",
                  "incluir_moose", "incluir_hnlnl"):
            RB._CFG.pop(k, None)
        mot, ori = RB.motores_da_serie({"modalidade": "CT"})
        RB._CFG.update({"incluir_nv": True, "incluir_cads": True,
                        "incluir_moose": True, "incluir_hnlnl": True})
        mot2, ori2 = RB.motores_da_serie({"modalidade": "CT"})
    finally:
        RB._CFG.clear()
        RB._CFG.update(antes_lote)
    checar(u"o lote SEM as chaves injetadas: nenhum motor de comparacao liga "
           u"(a serie sem modo e AUTO)",
           ori == "auto" and not any(mot.values()), str((ori, mot)))
    checar(u"  e COM as chaves velhas no `_CFG` tambem nao: quem liga e o "
           u"pedido da serie no PERSONALIZADO",
           ori2 == "auto" and not any(mot2.values()), str((ori2, mot2)))
    RA = _app_import("radai_arranque")
    rel = {"dados": {}, "avisos": [], "pendencias": []}
    try:
        L = RA._p_modelos({}, rel)
    except Exception as e:
        L = [u"levantou %s" % type(e).__name__]
    dm = rel["dados"].get("modelos") or []
    checar(u"o arranque diz quem liga cada modelo, sem chave INCLUIR_*",
           dm and all(x.get("quem_liga") and not x.get("chave") for x in dm)
           and not any("INCLUIR_" in l for l in L + rel["avisos"]),
           str(L)[:300])
    bl = u"\n".join(RA.bloco({"dados": {"modelos": dm}}))
    checar(u"  e a linha dos modelos no bloco diz «roda ...», e nao «=0|1»",
           u"Modelos de comparacao" in bl and u", roda " in bl
           and u"INCLUIR_" not in bl, bl[:300])
    import re as _re
    m = _re.search(r"((?:^#[^\n]*\n)+)TIMEOUT_TASK_H=", mod.DEFAULT_CFG, _re.M)
    checar(u"o TIMEOUT_TASK_H e descrito como teto das tasks do "
           u"TotalSegmentator, e nao dos niveis cervicais nem do CADS",
           bool(m) and "QUALQUER task" not in m.group(1)
           and "TotalSegmentator" in m.group(1)
           and "niveis" in m.group(1) and "CADS" in m.group(1))
    for k in ("TRAVA_SEM_PULSO_MIN", "TRAVA_PAGINANDO_MIN", "TRAVA_RAM_PCT",
              "IDIOMA"):
        m = _re.search(r"((?:^#[^\n]*\n)+)%s=" % k, mod.DEFAULT_CFG, _re.M)
        checar(u"  `%s` tem comentario no DEFAULT_CFG (a ajuda da tela)" % k,
               bool(m) and len(m.group(1)) > 40)

_NARRATIVA_NO_CONFIG = (
    (u"data", r"\b\d{1,2}/\d{1,2}/\d{4}\b"),
    (u"assinatura", r"--\s*Dr\.|\bHenrique\b"),
    (u"versao do programa", r"\bv\d+\.\d"),
    (u"documento de oficina", r"`Analise_|docs/|HISTORICO"),
    (u"citacao entre aspas angulares em bloco", r"(?m)^#\s{3,}«"),
)


def narrativa_no_config(texto):
    import re as _re
    return [nome for nome, rx in _NARRATIVA_NO_CONFIG
            if _re.search(rx, texto or u"")]


def teste_o_modelo_do_config_e_texto_tecnico():
    secao(u"o modelo do config gravado na estacao e texto tecnico neutro")
    mod = carregar(novo_temp(), novo_temp())
    achados = narrativa_no_config(mod.DEFAULT_CFG)
    checar(u"o DEFAULT_CFG nao traz data, assinatura, versao, documento de "
           u"oficina nem citacao (vai a estacao e ao repositorio publico)",
           not achados, str(achados))
    isca = (u"#     «quero isso agora»\n#            -- Dr. Henrique, "
            u"23/09/2026\n# como era ate a v8.0; ver `Analise_cranio`\nX=1\n")
    checar(u"  isca: a citacao assinada com data, a versao e o documento de "
           u"oficina sao acusados",
           sorted(narrativa_no_config(isca)) == sorted(
               n for n, _rx in _NARRATIVA_NO_CONFIG), str(narrativa_no_config(isca)))
    checar(u"  e a ajuda de cada chave continua (a tela de configuracao a le)",
           all(k in mod.DEFAULT_CFG for k in (u"--body_seg", u"Dataset300",
                                             u"HEARTBEAT_MIN", u"SUAVIZAR_MM=1.0",
                                             u"PASTA_FAVORITA=")))
    import re as _re
    import radai_config

    def _tps_pela_tela(texto):
        m = _re.search(r"((?:^#[^\n]*\n)+)TPS_DESTINO=", texto or u"", _re.M)
        b = m.group(1) if m else u""
        return (all(radai_config.rotulo_do_tps(v) in b
                    for v in ("eclipse", "monaco"))
                and u"Nos dois" in b and u"Implicit VR" in b
                and u"Com monaco" not in b)
    checar(u"a ajuda do TPS_DESTINO diz o nome de cada valor na tela e que "
           u"a sintaxe Implicit VR vale para os dois",
           _tps_pela_tela(mod.DEFAULT_CFG))
    velho = (u"# Sistema de planejamento que importa os RTSTRUCT desta "
             u"estacao: eclipse ou\n# monaco. Com monaco, contorno com "
             u"buraco sai com\n# fenda e o arquivo usa Implicit VR Little "
             u"Endian.\nTPS_DESTINO=\n")
    checar(u"  isca: a ajuda de antes (so o monaco em Implicit VR, sem o "
           u"nome da tela) reprova", not _tps_pela_tela(velho))


def teste_o_prefixo_longo_nao_come_o_caminho_relativo():
    secao(u"o prefixo literal nao come o caminho relativo")
    mod = carregar(novo_temp(), novo_temp())
    raiz = "C:" + os.sep + "x" + os.sep + "share"
    mod.ROOT = raiz
    alvo = os.sep.join([raiz, "PAC_A", "CT"])
    checar(u"o caminho literal vai e volta inteiro",
           mod.sem_prefixo(mod.caminho_longo(alvo)) == alvo,
           repr(mod.sem_prefixo(mod.caminho_longo(alvo))))
    r = mod.rel_root(mod.caminho_longo(alvo))
    checar(u"e rel_root devolve a arvore, e nao so o ultimo nome",
           r == os.path.join("PAC_A", "CT"), repr(r))
    ponto = os.sep.join([raiz, "S020_BODY_0."])
    checar(u"  e a pasta terminada em ponto mantem o ponto",
           mod.caminho_longo(ponto).endswith("_0."),
           repr(mod.caminho_longo(ponto)))


def teste_out_dir_nao_mistura_pacientes():
    secao("OUT_DIR preserva a arvore (nao mistura pacientes)")
    agora = datetime.now()
    base = novo_temp()
    root = os.path.join(base, "share")
    saida = os.path.join(base, "saida")
    for pid in ("PAC_A", "PAC_B"):
        escreve_serie(os.path.join(root, pid, "CT"), pid, agora - timedelta(days=1), 8)
    envelhecer(root, 60)
    mod = carregar(root, base, extra={"OUT_DIR": saida})
    fila, _ = fila_de(mod)
    checar("as duas series na fila", len(fila) == 2)
    for s in fila:
        mod.claim(s["dir"], s["uid"], {})
        mod.process_series(s)
    gerados = []
    for d, _, fs in os.walk(saida):
        gerados += [os.path.join(d, f) for f in fs]
    checar("cada paciente tem sua propria saida", len(gerados) == 2,
           str([os.path.relpath(g, saida) for g in gerados]))
    checar("a arvore relativa foi preservada",
           any("PAC_A" in g for g in gerados) and any("PAC_B" in g for g in gerados),
           str([os.path.relpath(g, saida) for g in gerados]))


def teste_dry_run_ponta_a_ponta():
    secao("DRY_RUN ponta a ponta pelo laco de verdade")
    agora = datetime.now()
    mod, root, base = montar([("PAC_%d" % i, agora - timedelta(days=i * 3), 8)
                              for i in range(1, 5)])
    envelhecer(root, 60)
    estado = {"fila": None, "proxima_varredura": 0.0}
    for _ in range(12):
        mod._uma_volta(estado)
        if estado["fila"] == [] and mod.STATE["done_today"] >= 4:
            break
    checar("o laco processou as 4 series", mod.STATE["done_today"] == 4,
           str(mod.STATE["done_today"]))
    dones, locks = 0, 0
    for d, dirs, fs in os.walk(root):
        if os.path.basename(d) == "_RadAI":
            dones += len([f for f in fs if f.endswith(".done.json")])
            locks += len([f for f in fs if f.endswith(".lock.json")])
    checar("4 marcadores done gravados", dones == 4, str(dones))
    checar("nenhum lock ficou para tras", locks == 0, str(locks))
    checar("o laco bateu ponto (painel sabe que esta vivo)",
           time.time() - mod.STATE["worker_vivo"] < 60)

    dry = [f for d, _, fs in os.walk(root) for f in fs if "SIMULACAO" in f]
    checar("em DRY_RUN a saida e marcada como simulacao", len(dry) == 4, str(len(dry)))
    checar("DRY_RUN nao gera .dcm nenhum",
           not [f for d, _, fs in os.walk(root) for f in fs if f.endswith(".dcm")
                and f.startswith("RS_")])
    marcador = None
    for d, _, fs in os.walk(root):
        for f in fs:
            if f.endswith(".done.json"):
                import json
                marcador = json.loads(open(os.path.join(d, f), encoding="utf-8").read())
                break
        if marcador:
            break
    checar("o marcador done registra que foi simulacao", marcador.get("dry_run") is True,
           str(marcador)[:80])
    checar("o marcador registra quantos cortes entraram", marcador.get("cortes") == 8,
           str(marcador.get("cortes")))
    checar("o marcador registra as tasks que de fato rodaram",
           "tasks_ok" in marcador, str(marcador.get("tasks_ok")))
    checar("existe log em arquivo para diagnostico",
           os.path.exists(str(mod.LOG_PATH)) and os.path.getsize(str(mod.LOG_PATH)) > 0,
           str(mod.LOG_PATH))
    checar("o vigia grava sinal de vida em arquivo",
           os.path.exists(os.path.join(str(mod.LOG_DIR), "radai_status.json")))


def teste_log_nao_expoe_caminho_absoluto():
    secao("PHI: o log nao imprime o caminho absoluto do share")
    agora = datetime.now()
    mod, root, base = montar([("PAC_SIGILO", agora - timedelta(days=1), 8)])
    envelhecer(root, 60)
    fila, _ = fila_de(mod)
    s = fila[0]
    mod.claim(s["dir"], s["uid"], {})
    mod.process_series(s)
    texto = "\n".join(mod.LOGBUF)
    checar("o log usa caminho relativo ao ROOT", root not in texto,
           "achei o caminho absoluto no log" if root in texto else "")
    checar("o log ainda identifica a serie pelos 8 ultimos digitos",
           s["uid"][-8:] in texto)


def teste_etapa_da_serie_atual():
    secao("fila: situacao da serie com progresso")
    agora = datetime.now()
    mod, root, base = montar([("PAC_ETAPA", agora - timedelta(days=1), 8)])
    envelhecer(root, 60)

    checar("sem serie corrente, marcar_etapa nao explode",
           mod.marcar_etapa("nada", 1, 3) is None)

    mod.STATE["current"] = {"pid": "P", "uid": "1234", "count": 8, "desde": "10:00"}
    mod.marcar_etapa("total", 1, 4)
    c = mod.STATE["current"]
    checar("publica a etapa", c.get("etapa") == "total", str(c))
    checar("publica o passo e o total", (c.get("passo"), c.get("total")) == (1, 4), str(c))
    checar("e marca quando a etapa comecou", c.get("etapa_desde", 0) > 0)

    d = mod.status()
    checar("o status devolve segundos na etapa",
           isinstance(d["current"].get("etapa_secs"), int), str(d["current"]))
    checar("o status NAO vaza etapa_desde para a tela",
           "etapa_desde" not in d["current"], str(d["current"]))
    checar("e nao removeu etapa_desde do STATE do worker",
           mod.STATE["current"].get("etapa_desde", 0) > 0,
           str(mod.STATE["current"]))
    mod.STATE["current"] = None
    checar("sem serie, o status devolve current nulo",
           mod.status()["current"] is None)


def teste_tela_do_vigia_explica_os_botoes():
    secao("fila: a tela do vigia")
    import radai_watcher as W
    p = W.PAGE
    checar("o botao diz que atualiza a fila", "Atualizar a fila agora" in p)
    checar("e a dica explica que NAO reprocessa",
           "so atualiza a lista" in p.lower() or "só atualiza a lista" in p.lower(), )
    checar("nao sobrou o nome antigo", "Re-varrer" not in p)
    checar("Rodar e Pausar tambem tem dica", p.count("title=") >= 3)
    checar("a tabela tem a coluna Situacao", "<th>Situação</th>" in p)
    checar("com barra de progresso", 'class="prog"' in p and ".prog>i{" in p)
    checar("a barra mede etapas, nao tempo",
           "var p=proc.passo||0, n=proc.total||0" in p
           and "Math.max(p-1,0)*100/n" in p)
    checar("a fila distingue a proxima das demais",
           "'próxima'" in p and "'na fila'" in p)
    checar("a variavel da serie em processamento nao se chama cur",
           "var proc=d.current" in p and "var cur=d.current" not in p)


def teste_acao_de_outro_site_e_recusada():
    import json as _json
    import subprocess
    import urllib.request
    import urllib.error

    base = novo_temp()
    root = os.path.join(base, "share")
    escreve_serie(os.path.join(root, "PAC_1", "CT"), "PAC_1",
                  datetime.now() - timedelta(days=1), 8)
    porta = _porta_livre()
    cfg = os.path.join(base, "csrf.config")
    with open(cfg, "w", encoding="utf-8") as f:
        f.write("ROOT=%s\nDRY_RUN=1\nMIN_SLICES=5\nQUIET_MIN=0\nTPS_DESTINO=eclipse\nPORT=%d\nLOG_DIR=%s\n"
                % (root, porta, os.path.join(base, "log")))
    env = dict(os.environ, RADAI_CONFIG=cfg, RADAI_MACHINE="PC_CSRF",
               LOCALAPPDATA=os.path.join(base, "ad"),
               PYTHONIOENCODING="utf-8:replace")
    proc = subprocess.Popen([sys.executable, _componentes.fonte("app/radai_watcher.py")],
                            env=env, stdout=subprocess.DEVNULL,
                            stderr=subprocess.STDOUT)
    try:
        alvo = "http://127.0.0.1:%d" % porta
        pronto, _como = _esperar_o_vigia(proc, porta, "PC_CSRF")
        checar("o vigia do teste subiu", pronto, _como)
        if not pronto:
            return

        def post(origem):
            req = urllib.request.Request(
                alvo + "/api/config", data=b"{}", method="POST",
                headers={"Content-Type": "application/json"})
            if origem:
                req.add_header("Origin", origem)
            try:
                urllib.request.urlopen(req, timeout=5)
                return 200
            except urllib.error.HTTPError as e:
                return e.code
            except Exception:
                return 0

        checar("POST sem Origin passa (curl, bateria, script local)",
               post(None) == 200, str(post(None)))
        checar("POST com a Origin da propria tela passa",
               post(alvo) == 200, str(post(alvo)))
        codigo = post("https://site-malicioso.example")
        checar("POST de outro site e recusado com 403", codigo == 403,
               str(codigo))

        req = urllib.request.Request(alvo + "/api/status")
        req.add_header("Origin", "https://site-malicioso.example")
        try:
            urllib.request.urlopen(req, timeout=5)
            ok_get = True
        except Exception:
            ok_get = False
        checar("GET continua livre mesmo de outra origem", ok_get)
    finally:
        try:
            proc.terminate()
            proc.wait(timeout=15)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass


def teste_a_faixa_de_estado_fica_no_topo():
    secao("a faixa de estado fica acima dos passos")
    fonte = io.open(_componentes.fonte("app/radai_watcher.py"),
                    encoding="utf-8").read()
    i = fonte.index('PAGE = u"""')
    j = fonte.index('def _com_menu', i)
    pag = fonte[i:j]

    corpo = pag[pag.index("<body>"):]
    i_faixa = corpo.index('class="vg-faixa"')
    i_passo = corpo.index('<section class="ps-cx')
    checar("a faixa vem ANTES do primeiro passo", i_faixa < i_passo,
           "faixa=%d passo=%d" % (i_faixa, i_passo))

    faixa = corpo[i_faixa:corpo.index("</div>", corpo.index("vg-acao"))]
    for ident in ("st", "nq", "done", "scan"):
        checar("a faixa tem `%s`" % ident, ('id="%s"' % ident) in faixa)
    checar("e NAO tem a serie atual", 'id="cur"' not in faixa)
    checar("a serie atual desceu para o passo 3", 'id="cur"' in corpo)
    checar("a faixa tem exatamente quatro cartoes",
           faixa.count('class="card"') == 4, str(faixa.count('class="card"')))

    checar("ha um botao primario, e um so",
           corpo.count('id="btLiga"') == 1)
    checar("e ele fica na faixa", 'id="btLiga"' in faixa)

    import re as _re
    passos = _re.findall(r'<section class="ps-cx([^"]*)"', corpo)
    checar("ha tres passos", len(passos) == 3, str(len(passos)))
    checar("e os tres nascem recolhidos",
           all("fechado" in c for c in passos), str(passos))


def teste_o_root_vazio_tem_acao():
    secao("o aviso de ROOT vazio leva ao passo 1")
    fonte = io.open(_componentes.fonte("app/radai_watcher.py"),
                    encoding="utf-8").read()
    checar("existe a caixa", 'id="semRoot"' in fonte)
    checar("com acao dentro dela", "abrirPasso1()" in fonte)
    checar("e a funcao abre o passo 1",
           "function abrirPasso1" in fonte and "cx1" in fonte)
    checar("ela e ambar, e nao vermelha",
           "rgba(255,200,87" in fonte[fonte.index(".vg-semroot{"):
                                      fonte.index(".vg-semroot{") + 400])
    checar("nasce escondida", 'id="semRoot" style="display:none"' in fonte)
    checar("e quem a mostra e o `upd`",
           "sr.style.display = semRoot" in fonte)


class _JanelaPreta(object):

    def __init__(self):
        import threading as _th
        self.partes = []
        self.chamadas = 0
        self._cont = _th.Lock()

    def write(self, s):
        with self._cont:
            self.chamadas += 1
        for ch in s:
            self.partes.append(ch)
            time.sleep(0)
        return len(s)

    def flush(self):
        pass

    def texto(self):
        return u"".join(self.partes)


_WLOG_DA_V82 = u'''
def wlog(msg):
    if not _LOG_TENTADO:
        _abrir_log()
    linha = "[%s] %s" % (datetime.now().strftime("%d/%m %H:%M:%S"), msg)
    with LOCK:
        LOGBUF.append(linha)
        if _LOG_FH is not None:
            try:
                _LOG_FH.write(linha + "\\n")
                _LOG_FH.flush()
            except Exception:
                pass
    try:
        print(linha)
    except Exception:
        pass
'''


def _linhas_quebradas(texto):
    fora = []
    data = re.compile(r"\[\d\d/\d\d \d\d:\d\d:\d\d\] ")
    for l in texto.split(u"\n")[:-1]:
        if not data.match(l) or len(data.findall(l)) != 1:
            fora.append(l[:60])
    return fora


def _falar_em_paralelo(mod, janela, threads=6, linhas=40):
    import threading as _th
    velho = sys.stdout
    sys.stdout = janela
    try:
        def fala(i):
            for j in range(linhas):
                mod.wlog(u"thread %d linha %d" % (i, j))
        ts = [_th.Thread(target=fala, args=(i,)) for i in range(threads)]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
    finally:
        sys.stdout = velho


def teste_o_log_e_uma_escrita_por_linha_com_data():
    secao(u"o log: uma escrita por linha, com data, na janela e no arquivo")
    agora = datetime.now()
    mod, _r, _b = montar([("PAC_LOG", agora - timedelta(days=1), 8)])
    janela = _JanelaPreta()
    velho = sys.stdout
    sys.stdout = janela
    try:
        mod.wlog(u"FALHOU serie ...1234: tempo limite\r\nlinha 2 do motor\n"
                 u"\nlinha 3 do motor\rlinha 4")
        antes = janela.chamadas
        mod.wlog(u"")
    finally:
        sys.stdout = velho
    linhas = janela.texto().split(u"\n")[:-1]
    checar(u"mensagem com quebra vira QUATRO linhas (a vazia do meio some)",
           len(linhas) == 5 and linhas[0].endswith(u"tempo limite")
           and linhas[3].endswith(u"linha 4"), str(linhas))
    checar(u"  e CADA uma tem a data e a hora na frente",
           not _linhas_quebradas(janela.texto()), str(_linhas_quebradas(
               janela.texto())))
    checar(u"  e a janela recebeu o bloco numa escrita SO (uma por wlog)",
           antes == 1 and janela.chamadas == 2, str(janela.chamadas))
    checar(u"  e a mensagem vazia continua sendo UMA linha, com a data",
           linhas[-1].rstrip().endswith(u"]") and len(linhas[-1]) >= 17,
           repr(linhas[-1]))
    buf = list(mod.LOGBUF)[-5:]
    checar(u"  e o buffer do painel tem as mesmas linhas", buf == linhas,
           str(buf))
    arq = u""
    try:
        if mod._LOG_FH is not None:
            mod._LOG_FH.flush()
        with io.open(str(mod.LOG_PATH), encoding="utf-8") as f:
            arq = f.read()
    except Exception as e:
        arq = u"(nao li: %s)" % e
    checar(u"  e o ARQUIVO tambem (cada linha com a data)",
           arq.endswith(u"\n".join(linhas) + u"\n"), arq[-200:])
    janela = _JanelaPreta()
    _falar_em_paralelo(mod, janela)
    q = _linhas_quebradas(janela.texto())
    checar(u"seis threads falando: nenhuma linha colada nem vazia na janela",
           not q and janela.texto().count(u"\n") == 240,
           u"%d quebradas, ex.: %s" % (len(q), q[:2]))
    real = mod.wlog
    try:
        exec(compile(_WLOG_DA_V82, "wlog_v82", "exec"), mod.__dict__)
        janela = _JanelaPreta()
        _falar_em_paralelo(mod, janela)
        q2 = _linhas_quebradas(janela.texto())
        janela2 = _JanelaPreta()
        sys.stdout = janela2
        try:
            mod.wlog(u"a\nb")
        finally:
            sys.stdout = velho
    finally:
        mod.wlog = real
    checar(u"ISCA: com o wlog da v8.2 as linhas se entremeiam na janela (a "
           u"checagem de cima reprovaria)", bool(q2), str(len(q2)))
    checar(u"ISCA: e a mensagem com quebra sai com uma linha SEM data",
           bool(_linhas_quebradas(janela2.texto())), janela2.texto())


def teste_o_log_saiu_do_corpo():
    secao("o log saiu do corpo da tela")
    fonte = io.open(_componentes.fonte("app/radai_watcher.py"),
                    encoding="utf-8").read()
    i = fonte.index('PAGE = u"""')
    j = fonte.index('def _com_menu', i)
    pag = fonte[i:j]
    corpo = pag[pag.index("<body>"):pag.index("<script>")]
    checar("nao ha mais `<div id=\"log\">` no corpo",
           'id="log"' not in corpo)
    checar("e o JS nao o preenche mais",
           "getElementById('log')" not in pag)
    t = io.open(_componentes.fonte("app/radai_todo.py"), encoding="utf-8").read()
    checar("a barra da direita tem a aba Log", "Log" in t)
    checar("e ela busca em /api/log", "/api/log" in t)


def teste_o_rodape_nao_cita_um_sufixo_entre_seis():
    secao("o rodape clinico do vigia diz o que vale para os SETE conjuntos")
    fonte = io.open(_componentes.fonte("app/radai_watcher.py"),
                    encoding="utf-8").read()
    i = fonte.index('class="rodape-clinico"')
    rod = fonte[i:fonte.index("</div>", fonte.index("</span>", i))]
    import re as _re2
    rod = _re2.sub(r"<!--.*?-->", " ", rod, flags=_re2.S)
    checar("diz sugestao nao aprovada", u"sugestão não aprovada" in rod)
    checar("e cita o ApprovalStatus", "ApprovalStatus = UNAPPROVED" in rod)
    checar("e que revisar e ato medico", u"ato médico" in rod)
    checar("e NAO diz que toda estrutura leva `_ai`",
           "_ai" not in rod, rod[:120])

    import radai_sets
    checar("o registro dos conjuntos e quem sabe quantos sao",
           len(radai_sets.CONJUNTOS) >= 6,
           str(len(radai_sets.CONJUNTOS)))


def teste_a_fila_nasce_desligada_e_dedica_a_estacao():
    secao("a fila nasce desligada, e ligada ela dedica a estacao")
    base = novo_temp()
    root = os.path.join(base, "share")
    escreve_serie(os.path.join(root, "PAC_1", "CT"), "PAC_1",
                  datetime.now() - timedelta(days=1), 8)
    envelhecer(root, 60)
    mod = carregar(root, base, machine="PC_DESLIG")
    mod.STATE["ligado"] = False

    estado = {"fila": None, "proxima_varredura": 0.0}
    t0 = time.time()
    mod._uma_volta(estado)
    checar("desligada, uma volta nao monta fila", estado["fila"] is None)
    checar("  e nao processa nada", mod.STATE["done_today"] == 0,
           str(mod.STATE["done_today"]))
    checar("  e nao trava", time.time() - t0 < 10)
    checar("desligado nao e o mesmo que pausado",
           mod.STATE["ligado"] is False and mod.STATE["paused"] is False)

    mod.STATE["ligado"] = True
    for _ in range(10):
        mod._uma_volta(estado)
        if mod.STATE["done_today"]:
            break
    checar("ligada, ela processa", mod.STATE["done_today"] >= 1,
           str(mod.STATE["done_today"]))

    fonte = io.open(_componentes.fonte("app/radai_watcher.py"),
                    encoding="utf-8").read()
    checar("a navegacao fica livre com a fila ligada: o portao que mandava "
           "toda tela para /lote saiu", "montar_portao_da_fila" not in fonte
           and "dedicada=1" not in fonte and 'id="ovDedicada"' not in fonte)

    checar("ha rota de ligar", '"/api/vigia/ligar"' in fonte)
    checar("e de desligar", '"/api/vigia/desligar"' in fonte)
    checar("ligar confere o ROOT antes", 'o ROOT esta vazio' in fonte)


def teste_painel_sobe():
    secao("painel web sobe e responde")
    import json as _json
    import subprocess
    import urllib.request

    agora = datetime.now()
    base = novo_temp()
    root = os.path.join(base, "share")
    escreve_serie(os.path.join(root, "PAC_1", "CT"), "PAC_1", agora - timedelta(days=1), 8)
    envelhecer(root, 60)
    porta = _porta_livre()
    cfg = os.path.join(base, "painel.config")
    with open(cfg, "w", encoding="utf-8") as f:
        f.write("ROOT=%s\nDRY_RUN=1\nMIN_SLICES=5\nQUIET_MIN=0\nTPS_DESTINO=eclipse\nPORT=%d\nLOG_DIR=%s\n"
                % (root, porta, os.path.join(base, "log")))
    env = dict(os.environ, RADAI_CONFIG=cfg, RADAI_MACHINE="PC_PAINEL",
               LOCALAPPDATA=os.path.join(base, "ad"), PYTHONIOENCODING="utf-8:replace")
    proc = subprocess.Popen([sys.executable, _componentes.fonte("app/radai_watcher.py")],
                            env=env, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    try:
        _subiu, _como = _esperar_o_vigia(proc, porta, "PC_PAINEL")
        checar("o vigia do teste subiu", _subiu, _como)
        _ligou = False
        for _ in range(60):
            try:
                urllib.request.urlopen(urllib.request.Request(
                    "http://127.0.0.1:%d/api/vigia/ligar" % porta,
                    data=b"", method="POST"), timeout=2).read()
                _ligou = True
                break
            except Exception:
                time.sleep(0.5)
        checar("a rota de ligar a fila respondeu", _ligou)
        dados, pagina = None, ""
        for _ in range(60):
            try:
                pagina = urllib.request.urlopen("http://127.0.0.1:%d/vigia" % porta, timeout=2).read().decode("utf-8", "replace")
                dados = _json.loads(urllib.request.urlopen(
                    "http://127.0.0.1:%d/api/status" % porta, timeout=2).read().decode("utf-8"))
                if dados.get("done_today"):
                    break
            except Exception:
                pass
            time.sleep(0.5)

        checar("o painel responde em 127.0.0.1", dados is not None)
        if dados is None:
            return
        de_quem = dados.get("machine")
        checar("quem respondeu foi o vigia QUE ESTE TESTE levantou",
               de_quem == "PC_PAINEL",
               "" if de_quem == "PC_PAINEL" else
               "respondeu %r — ha outro vigia segurando a porta %d, e as "
               "checagens abaixo mediriam ELE" % (de_quem, porta))
        if dados.get("machine") != "PC_PAINEL":
            return
        checar("sem aceite, a tela que responde e o portao",
               'id="ac_ok"' in pagina, pagina[:70])

        import radai_consent as _CS
        with open(os.path.join(_ACERVO_TESTE, _CS.ARQUIVO_ACEITE), "w",
                  encoding="utf-8") as _f:
            _json.dump(_aceite_da_bateria(_CS, "PC_PAINEL"), _f)
        pagina = urllib.request.urlopen(
            "http://127.0.0.1:%d/" % porta, timeout=2).read().decode(
                "utf-8", "replace")
        import html as _html
        plano = " ".join(_html.unescape(pagina).lower().split())
        checar("a pagina avisa que a estrutura e sugestao nao aprovada",
               "não aprovada" in plano, plano[:90])
        checar("o status diz que esta em simulacao", dados.get("dry_run") is True)
        checar("o status reporta saude do laco de trabalho", dados.get("saudavel") is True,
               "parado ha %ss" % dados.get("parado_ha"))
        checar("o vigia processou a serie com o painel no ar",
               dados.get("done_today") == 1, str(dados.get("done_today")))
        try:
            _lg = _json.loads(urllib.request.urlopen(
                "http://127.0.0.1:%d/api/log" % porta,
                timeout=3).read().decode("utf-8"))
        except Exception as _e:
            _lg = {"erro": str(_e)[:80]}
        _linhas = _lg.get("linhas") or _lg.get("log") or []
        checar("o log chega ao painel, por /api/log", len(_linhas) > 0,
               str(_lg)[:90])
        checar("e ele NAO viaja mais no /api/status",
               "log" not in dados,
               "%d linhas no corpo de 3 em 3 s" % len(dados.get("log") or []))
        checar("o painel expoe a versao", dados.get("versao"), str(dados.get("versao")))
        arr = dados.get("arranque") or {}
        checar("o status diz que o arranque terminou",
               arr.get("estado") == "pronto", str(arr))
        pasta_log = os.path.join(base, "log")
        blocos = sorted(n for n in os.listdir(pasta_log)
                        if n.startswith("arranque_") and n.endswith(".txt")) \
            if os.path.isdir(pasta_log) else []
        checar("o bloco do arranque foi gravado na pasta do log",
               len(blocos) == 1 and blocos[0] == arr.get("arquivo"),
               "%s / %s" % (blocos, arr.get("arquivo")))
        if blocos:
            _b = io.open(os.path.join(pasta_log, blocos[0]),
                         encoding="utf-8").read()
            checar("  com a frase para colar num chat de IA",
                   "cole este bloco num chat de IA para diagnostico" in _b)
            checar("  e SEM o ROOT nem a pasta do paciente",
                   root not in _b and "PAC_1" not in _b)
            _tempos = next((l for l in _b.splitlines()
                            if l.startswith("Tempos:")), "")
            _n_passos = len(_app_import("radai_arranque").PASSOS)
            checar("  e com os %d passos cronometrados" % _n_passos,
                   len(_tempos.split(" | ")) == _n_passos
                   and "pendencias de ambiente" in _tempos
                   and "estatistica de uso do TotalSegmentator" in _tempos,
                   _tempos[:200])
    finally:
        try:
            proc.terminate()
            proc.wait(timeout=15)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass


def teste_elegibilidade_do_torax():
    secao("torax: serie fora do protocolo nem chega a segmentar")
    base = tempfile.mkdtemp(prefix="radai_eleg_"); _TEMPS.append(base)
    W = carregar("", base, machine="PC_ELEG")

    class _Img(object):
        def __init__(self, esp):
            self._e = esp

        def GetSpacing(self):
            return (0.98, 0.98, self._e)

    for esp, elegivel in ((1.0, True), (1.25, True), (2.5, True),
                          (3.0, True), (3.75, False), (5.0, False)):
        checar("%.2f mm -> %s" % (esp, "elegivel" if elegivel else "fora"),
               W.serie_elegivel_torax(_Img(esp)) is elegivel)
    checar("espessura ausente nao passa por elegivel",
           W.serie_elegivel_torax(_Img(0.0)) is False)

    import radai_triage
    checar("o teto e o do modulo toracico",
           radai_triage.ESPESSURA_RECUSA_MM == 3.0,
           str(radai_triage.ESPESSURA_RECUSA_MM))

    tarefas = ["total", "head_glands_cavities", "lung_vessels"]
    fora = W._tasks_fora_do_protocolo(tarefas, _Img(5.0), "TESTE")
    checar("lung_vessels e pulada em 5 mm", "lung_vessels" in fora, str(fora))
    checar("mas `total` roda sempre — e o contorno de radioterapia",
           "total" not in fora, str(fora))
    checar("e head_glands_cavities tambem", "head_glands_cavities" not in fora)

    nenhuma = W._tasks_fora_do_protocolo(tarefas, _Img(1.0), "TESTE")
    checar("em 1 mm nao pula nada", not nenhuma, str(nenhuma))

    vazio = W._tasks_fora_do_protocolo(["total"], _Img(5.0), "TESTE")
    checar("sem task de torax na lista, nao ha o que pular", not vazio)

    secao("torax: ha torax NO CAMPO? (anatomia, e nao espessura)")
    import numpy as _np
    import radai_geom as _rg
    _g = _rg.Grade((3.0, 1.0, 1.0))

    def _pulmao(nz, z0, z1, raio=40):
        m = _np.zeros((nz, 120, 120), bool)
        m[z0:z1, 60 - raio:60 + raio, 60 - raio:60 + raio] = True
        return m

    _torax = {"lung_left": _pulmao(120, 10, 100),
              "lung_right": _pulmao(120, 10, 100),
              "heart": _pulmao(120, 50, 80, 25)}
    ok, pq = W.torax_no_campo(_torax, grade=_g)
    checar("torax: pulmao inteiro no campo -> RODA", ok, pq)

    _pelve = {"lung_left": _pulmao(120, 100, 120),
              "lung_right": _pulmao(120, 100, 120)}
    ok, pq = W.torax_no_campo(_pelve, grade=_g)
    checar("pelve: so a base, encostando na borda cranial -> NAO roda",
           not ok, pq)
    checar("e o motivo diz qual borda", "cranial" in pq, pq)

    _cranio = {"lung_left": _pulmao(120, 0, 12),
               "lung_right": _pulmao(120, 0, 12)}
    ok, pq = W.torax_no_campo(_cranio, grade=_g)
    checar("cranio: so o apice, encostando na borda caudal -> NAO roda",
           not ok, pq)

    ok, pq = W.torax_no_campo({}, grade=_g)
    checar("sem pulmao desenhado, na duvida RODA", ok, pq)

    _raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    fonte = io.open(_componentes.fonte("app/radai_watcher.py"),
                    encoding="utf-8").read()
    import radai_tasks as _K
    _B = _K.BASES_CT[0]
    checar("a base e posta na frente da lista de tasks",
           W.base_na_frente(["lung_vessels", _B, "teeth"])[0] == _B,
           str(W.base_na_frente(["lung_vessels", _B, "teeth"])))
    checar("  e o resto guarda a ordem em que veio",
           W.base_na_frente(["lung_vessels", _B, "teeth"])[1:]
           == ["lung_vessels", "teeth"])
    checar("  e a reserva conta como base",
           W.base_na_frente(["teeth", _K.BASES_CT[-1]])[0] == _K.BASES_CT[-1],
           u"numa estacao sem o peso da preferida, quem desenha e ela")
    checar("  e a base da RM tambem",
           W.base_na_frente(["teeth", _K.BASES_MR[0]])[0] == _K.BASES_MR[0])
    checar("  sem base nenhuma, a lista passa intacta",
           W.base_na_frente(["teeth", "lung_vessels"])
           == ["teeth", "lung_vessels"])
    checar("  e a lista de bases NAO e um literal no vigia",
           "BASES_CT" in fonte,
           u"foi o literal `total` que deixou esta ordem inerte")
    g = _ganchos_da_lista(fonte)
    checar("e o portao anatomico roda DENTRO do laco das tasks (o gancho "
           "`antes_de` do primitivo pergunta TASKS_SO_TORAX e torax_no_campo)",
           {"TASKS_SO_TORAX", "torax_no_campo"} <= g.get("antes_de", set()),
           str(sorted(g.get("antes_de", set())))[:200])
    _isca = fonte.replace("rodar=_rodar_uma, antes_de=_antes_de,",
                          "rodar=_rodar_uma,")
    checar("  ISCA: sem o `antes_de=` na chamada do primitivo, a leitura acusa",
           _isca != fonte and "antes_de" not in _ganchos_da_lista(_isca))


def _ganchos_da_lista(fonte):
    import ast as _ast
    try:
        arv = _ast.parse(fonte)
    except SyntaxError:
        return {}
    ps = next((n for n in _ast.walk(arv) if isinstance(n, _ast.FunctionDef)
               and n.name == "process_series"), None)
    if ps is None:
        return {}
    locais = dict((n.name, n) for n in _ast.walk(ps)
                  if isinstance(n, _ast.FunctionDef) and n is not ps)
    fora = {}
    for c in _ast.walk(ps):
        if not (isinstance(c, _ast.Call)
                and getattr(c.func, "attr", "") == "rodar_tasks"):
            continue
        for k in c.keywords:
            if isinstance(k.value, _ast.Name) and k.value.id in locais:
                fn = locais[k.value.id]
                nomes = set()
                for n in _ast.walk(fn):
                    if isinstance(n, _ast.Name):
                        nomes.add(n.id)
                    elif isinstance(n, _ast.Attribute):
                        nomes.add(n.attr)
                fora[k.arg] = nomes
            elif k.arg:
                fora.setdefault(k.arg, set())
    return fora


def teste_o_lote_nao_deixa_tx_na_pasta():
    secao("o lote nao deixa `_tx` na pasta")
    import numpy as np
    from datetime import datetime

    base = novo_temp("radai_sem_tx_serie_")
    W = carregar("", base, machine="PC_TX")
    serie = os.path.join(base, "serie")
    escreve_serie(serie, "PAC_TX", datetime(2026, 8, 14, 9, 0), 12)

    import engine
    arq = [os.path.join(serie, f) for f in sorted(os.listdir(serie))
           if f.endswith(".dcm")]
    stage = novo_temp("radai_sem_tx_stage_")
    engine.copy_sorted(arq, stage)
    ref = engine.load_sitk(stage)
    forma = tuple(int(v) for v in reversed(ref.GetSize()))

    def bloco(z0, z1, x0, x1):
        m = np.zeros(forma, dtype=bool)
        m[z0:z1, forma[1] // 4:forma[1] * 3 // 4, x0:x1] = True
        return m

    cruas = {"total": {
        "lung_upper_lobe_right": bloco(8, 12, 10, 40),
        "lung_middle_lobe_right": bloco(4, 8, 10, 40),
        "lung_lower_lobe_right": bloco(0, 4, 10, 40),
        "lung_upper_lobe_left": bloco(6, 12, 60, 90),
        "lung_lower_lobe_left": bloco(0, 6, 60, 90),
        "liver": bloco(0, 3, 45, 55),
        "heart": bloco(4, 7, 45, 58),
    }, "lung_vessels": {
        "lung_vessels": bloco(2, 10, 20, 26),
        "lung_trachea_bronchia": bloco(6, 12, 46, 52),
    }}

    destino = novo_temp("radai_sem_tx_")

    gravadores = [n for n in dir(W) if "torax" in n.lower()
                  and n.startswith(("_entregar", "entregar", "gravar"))]
    checar("o vigia nao expoe gravador de torax", not gravadores,
           ", ".join(gravadores) or "nenhum")

    gm = [n for n in dir(engine) if "torax" in n.lower()
          and n.startswith(("entregar", "gravar", "salvar"))]
    checar("nem o motor", not gm, ", ".join(gm) or "nenhum")

    for nome in sorted(cruas):
        assert cruas[nome], nome
    checar("o fantoma tem os cinco lobos",
           sum(1 for k in cruas["total"] if "lobe" in k) == 5,
           str(sorted(k for k in cruas["total"] if "lobe" in k)))

    saiu = [f for f in os.listdir(destino) if f.startswith("RS_RadAI_TX_")]
    checar("e a pasta nao ganhou `_tx`", not saiu, str(saiu))


def teste_lock_nao_e_reentrante():
    secao(u"o LOCK nao e reentrante, e nada acusa quem o pede duas vezes")
    import re as _re
    fonte = io.open(_componentes.fonte("app/radai_watcher.py"),
                    encoding="utf-8").read()

    pedem = []
    for m in _re.finditer(r"^def ([a-z_0-9]+)\(", fonte, _re.M):
        nome, ini = m.group(1), m.end()
        fim = fonte.find("\ndef ", ini)
        corpo = fonte[ini:fim if fim > 0 else len(fonte)]
        if _re.search(r"^\s+with LOCK:", corpo, _re.M):
            pedem.append(nome)
    checar(u"achei as funcoes que pedem o LOCK", len(pedem) >= 2,
           ", ".join(pedem[:8]))

    ruins = []
    for m in _re.finditer(r"^([ \t]*)with LOCK:[ \t]*$", fonte, _re.M):
        recuo, ini = len(m.group(1)), m.end()
        linhas = []
        for linha in fonte[ini:].splitlines():
            if linha.strip() and (len(linha) - len(linha.lstrip())) <= recuo:
                break
            linhas.append(linha)
        bloco = "\n".join(linhas)
        for nome in pedem:
            if _re.search(r"(?<![\w.])" + _re.escape(nome) + r"[ \t]*\(", bloco):
                ruins.append(nome)
    checar(u"e NENHUMA delas e chamada de dentro de um `with LOCK:`",
           not ruins,
           u"%s — `threading.Lock` nao e reentrante: isso TRAVA, sem erro"
           % (sorted(set(ruins)) or "-"))

    i_st = fonte.find("def status():")
    corpo = fonte[i_st:i_st + 3200] if i_st >= 0 else ""
    i_calc = corpo.find("ocupado = quem_esta_segmentando()")
    m_lock = _re.search(r"^[ \t]+with LOCK:[ \t]*$", corpo, _re.M)
    i_lock = m_lock.start() if m_lock else -1
    checar(u"o `ocupado` do /api/status e calculado ANTES do lock",
           0 <= i_calc < i_lock, "calc=%d lock=%d" % (i_calc, i_lock))


def teste_modalidades_ida_e_volta():
    secao(u"modalidades: o que a tela grava volta do config")
    import re as _re
    def _ler(v):
        return set(m.upper() for m in _re.split(r"[,;\s]+", v or "") if m)

    for escrito, esperado in ((u"CT", {"CT"}),
                              (u"CT,MR", {"CT", "MR"}),
                              (u"CT MR", {"CT", "MR"}),
                              (u"CT; MR", {"CT", "MR"}),
                              (u"MR", {"MR"})):
        checar(u"`MODALITIES=%s` vira %s" % (escrito, sorted(esperado)),
               _ler(escrito) == esperado, str(sorted(_ler(escrito))))

    fonte = io.open(_componentes.fonte("app/radai_watcher.py"),
                    encoding="utf-8").read()
    i = fonte.find("MODALITIES = set(")
    trecho = fonte[i:i + 160] if i >= 0 else ""
    checar(u"e `aplicar_cfg` usa o separador das tasks",
           "re.split" in trecho, trecho.replace(chr(10), " ")[:78])
    checar(u"e NAO usa `.split()` seco",
           '["MODALITIES"].split()' not in trecho)

    checar(u"o botao da tela normaliza virgula e espaco",
           "split(/[,;" + (chr(92) * 2) + "s]+/)" in fonte, "porMod")
    checar(u"e nao apaga o espaco (era o defeito espelhado)",
           "toUpperCase().replace(/ /g,'')" not in fonte)


def teste_plano_de_execucao():
    secao(u"o plano de execucao: mostra antes de fazer")
    import importlib.util as _iu
    import tempfile, shutil
    _sp = _iu.spec_from_file_location(
        "vigia_plano", _componentes.fonte("app/radai_watcher.py"))
    W = _iu.module_from_spec(_sp)
    _sp.loader.exec_module(W)
    base = tempfile.mkdtemp(prefix="radai_plano_")
    try:
        exame = os.path.join(base, "EXAME_A")
        os.makedirs(exame)
        series = {}
        for uid, n in (("1.2.3.40", 40), ("1.2.3.120", 120), ("1.2.3.90", 90)):
            series[uid] = {"dir": exame, "count": n, "pid": "P1",
                           "date": "20240101000000", "desc": "TC",
                           "modality": "CT", "espessura_mm": 2.5,
                           "mais_novo": 0}
        velho_scan = W.scan_root
        velho_root = W.ROOT
        W.ROOT = base
        W.scan_root = lambda: (series, [])
        try:
            p = W.plano_de_execucao()
        finally:
            W.scan_root = velho_scan
            W.ROOT = velho_root

        checar(u"um exame (as tres sao do mesmo)", len(p["exames"]) == 1,
               str(len(p["exames"])))
        linhas = p["exames"][0]["series"]
        checar(u"as tres series aparecem", len(linhas) == 3, str(len(linhas)))
        escolhidas = [x for x in linhas if x["escolhida"]]
        checar(u"UMA so e escolhida", len(escolhidas) == 1, str(len(escolhidas)))
        checar(u"e e a de MAIS CORTES",
               escolhidas and escolhidas[0]["cortes"] == 120,
               str(escolhidas[0]["cortes"]) if escolhidas else "-")
        pulados = [x for x in linhas if x["estado"] == "pulado"]
        checar(u"as outras duas ficam de fora", len(pulados) == 2, str(len(pulados)))
        checar(u"  e DIZEM por que",
               all("simulacao" in (x["detalhe"] or "") for x in pulados),
               (pulados[0]["detalhe"][:70] if pulados else ""))
        checar(u"o resumo conta certo",
               p["resumo"]["a_fazer"] == 1 and p["resumo"]["pulados"] == 2,
               str(p["resumo"]))
        import radai_sets as _cj
        checar(u"traz todos os conjuntos do registro",
               len(p["conjuntos"]) == len(_cj.CONJUNTOS),
               u"%d na tela, %d no registro"
               % (len(p["conjuntos"]), len(_cj.CONJUNTOS)))
        marcados = [c["cod"] for c in p["conjuntos"] if c["marcado"]]
        checar(u"  os NOSSOS dois estao sempre marcados",
               set(("oar", "full")) <= set(marcados), str(marcados))
        sem_origem = [c["cod"] for c in p["conjuntos"]
                      if not (c.get("decide") or c.get("chave"))]
        checar(u"  e todo conjunto diz quem decide se ele sai (v8.3: sem "
               u"chave no config)", not sem_origem, str(sem_origem))
        vig = dict((c["cod"], c) for c in p["conjuntos"])
        checar(u"  e no vigia (AUTO) o TS cru e os motores de comparacao "
               u"saem DESLIGADOS",
               not any(vig[k]["marcado"] for k in ("ts", "nv", "cads", "mse")
                       if k in vig),
               str([(k, vig[k]["marcado"]) for k in ("ts", "nv", "cads", "mse")
                    if k in vig]))
        checar(u"  e nenhum deles aponta para uma chave de config",
               not [c["cod"] for c in p["conjuntos"] if c.get("chave")])
        checar(u"  e o `hnl` (o arquivo HNL_) sai DESMARCADO no vigia, dizendo "
               u"que os niveis vao ao FULL",
               "hnl" in vig and vig["hnl"]["marcado"] is False
               and u"FULL" in (vig["hnl"].get("decide") or u""),
               str(vig.get("hnl")))
        checar(u"  o `mse` aparece na tela (marcado ou nao)",
               "mse" in [c["cod"] for c in p["conjuntos"]],
               str([c["cod"] for c in p["conjuntos"]]))
        checar(u"  e so um vai para o TPS",
               sum(1 for c in p["conjuntos"] if c["entregue"]) == 1, "")
        checar(u"nao criou _RadAI (leitura pura)",
               not os.path.isdir(os.path.join(exame, "_RadAI")),
               "criou a pasta de marcadores")
    finally:
        _soltar_logs()
        shutil.rmtree(base, ignore_errors=True)


def teste_o_plano_diz_quando_e_em_que_modo_ficou_pronto():
    secao(u"o plano diz quando e em que modo a serie ficou pronta")
    import importlib.util as _iu
    import json as _j
    import tempfile, shutil
    _sp = _iu.spec_from_file_location(
        "vigia_plano_pronto", _componentes.fonte("app/radai_watcher.py"))
    W = _iu.module_from_spec(_sp)
    _sp.loader.exec_module(W)
    base = tempfile.mkdtemp(prefix="radai_plano_pronto_")
    try:
        series = {}
        for n, (uid, modo) in enumerate((("1.2.3.71", "fast"),
                                         ("1.2.3.72", "auto"))):
            exame = os.path.join(base, "EXAME_%d" % n)
            os.makedirs(os.path.join(exame, "_RadAI"))
            io.open(os.path.join(exame, "_RadAI", "%s.done.json" % uid), "w",
                    encoding="utf-8").write(_j.dumps(
                        {"uid": uid, "finished": "2026-09-27 15:04:05",
                         "modo": modo, "machine": "TARDE"}))
            with open(os.path.join(exame, "RS_RadAI_%s_%s.dcm"
                                   % ("OAR_Fast" if modo == "fast" else "x",
                                      uid[-8:])), "wb") as f:
                f.write(b"\0" * 200)
            series[uid] = {"dir": exame, "count": 90, "pid": "P%d" % n,
                           "date": "20240101000000", "desc": "TC",
                           "modality": "CT", "espessura_mm": 2.5,
                           "mais_novo": 0}
        velho_scan, velho_root = W.scan_root, W.ROOT
        W.ROOT = base
        W.scan_root = lambda: (series, [])
        try:
            p = W.plano_de_execucao()
            isca = _plano_mutado(W, [(u'd.get("finished") or ', u'')])()
        finally:
            W.scan_root, W.ROOT = velho_scan, velho_root
        por = dict((x["uid"], x) for e in p["exames"] for x in e["series"])
        fast, auto = por.get("1.2.3.71") or {}, por.get("1.2.3.72") or {}
        checar(u"as duas series concluidas saem `pronto`",
               fast.get("estado") == "pronto" and auto.get("estado") == "pronto",
               u"%s | %s" % (fast.get("estado"), auto.get("estado")))
        checar(u"  e dizem QUANDO (o `finished` do marcador)",
               u"2026-09-27 15:04" in (fast.get("detalhe") or u"")
               and u"2026-09-27 15:04" in (auto.get("detalhe") or u""),
               u"%r | %r" % (fast.get("detalhe"), auto.get("detalhe")))
        checar(u"  e a feita so em FAST diz FAST (o vigia nao a refaz), e a "
               u"AUTO nao", u"FAST" in (fast.get("detalhe") or u"")
               and u"FAST" not in (auto.get("detalhe") or u""),
               u"%r | %r" % (fast.get("detalhe"), auto.get("detalhe")))
        por_i = dict((x["uid"], x) for e in isca["exames"] for x in e["series"])
        checar(u"  (isca) com a leitura de antes, o detalhe sai sem a hora -- "
               u"a checagem discrimina",
               u"15:04" not in ((por_i.get("1.2.3.72") or {}).get("detalhe")
                                or u""), str(por_i.get("1.2.3.72")))
    finally:
        _soltar_logs()
        shutil.rmtree(base, ignore_errors=True)


def teste_o_botao_rodar_mostra_antes():
    secao(u"o botao Rodar mostra o trabalho antes")
    fonte = open(_componentes.fonte("app/radai_watcher.py"), encoding="utf-8").read()
    checar(u"o botao chama a revisao", "planoAbrir()" in fonte, "")
    checar(u"e nao chama `resume` direto",
           "bl.onclick=function(){ act('resume') }" not in fonte, "")
    _i = fonte.find("function planoConfirmar()")
    checar(u"`planoConfirmar` existe", _i >= 0)
    _corpo = ""
    if _i >= 0:
        _fim = fonte.find(chr(10) + "}" + chr(10), _i)
        _corpo = fonte[_i:_fim if _fim > 0 else _i + 2000]
        checar(u"quem confirma e que comeca",
               "filaComecar()" in _corpo, "")
        checar(u"e ele fecha o dialogo antes",
               "planoFechar()" in _corpo, "")
    checar(u"e comecar nao sai de nenhum outro lugar da tela",
           fonte.count("filaComecar();") == _corpo.count("filaComecar();"),
           u"um segundo caminho para comecar pularia a conferencia")
    _j = fonte.find("function filaComecar(){")
    _fc = fonte[_j:fonte.find(chr(10) + "}" + chr(10), _j)] if _j >= 0 else ""
    checar(u"`filaComecar` existe", _j >= 0)
    checar(u"  e e ele quem escolhe entre ligar e retomar",
           "window._ligado ? 'resume' : 'vigia/ligar'" in _fc)
    checar(u"  e nenhum `act('resume')` sobrou solto na tela",
           "act('resume')" not in fonte,
           u"`resume` cru nao acende `ligado`: o botao diria RODANDO sem rodar")
    checar(u"a rota do plano existe", '@app.get("/api/vigia/plano")' in fonte, "")
    checar(u"e e GET, porque consultar nao muda nada",
           '@app.post("/api/vigia/plano")' not in fonte, "")

def teste_days_back_grande_nao_derruba_o_laco():
    secao(u"DAYS_BACK grande nao derruba o laco")
    from datetime import datetime
    import time as _t

    levantou = False
    try:
        datetime.fromtimestamp(_t.time() - 36500 * 86400)
    except (OSError, OverflowError, ValueError):
        levantou = True
    checar(u"a conta crua levanta neste sistema", levantou,
           u"(no Linux nao levanta; a trava vale para os dois)")

    for dias in (0, 30, 3650, 36500, 10 ** 6):
        try:
            quando = max(0.0, _t.time() - dias * 86400)
            limite = datetime.fromtimestamp(quando).strftime("%Y%m%d%H%M%S")
            ok = len(limite) == 14 and limite.isdigit()
        except Exception as e:
            ok, limite = False, u"%s: %s" % (type(e).__name__, e)
        checar(u"DAYS_BACK=%d produz um limite valido" % dias, ok, str(limite))

    limite = datetime.fromtimestamp(0.0).strftime("%Y%m%d%H%M%S")
    checar(u"e o limite da epoca deixa passar serie de 1990",
           u"19900101120000" >= limite, limite)
    checar(u"e o de hoje NAO deixaria (a checagem sabe reprovar)",
           not (u"19900101120000" >=
                datetime.now().strftime("%Y%m%d%H%M%S")))

    import io as _io, os as _os
    fonte = _io.open(_componentes.fonte("app/radai_watcher.py"),
                     encoding="utf-8", errors="replace").read()
    checar(u"o corte por data para na epoca",
           u"max(0.0, time.time() - DAYS_BACK * 86400)" in fonte)
    checar(u"o laco registra o traceback INTEIRO na primeira volta",
           u"for _l in traceback.format_exc().strip().splitlines():" in fonte,
           u"a ultima linha sozinha nao aponta lugar nenhum")
    checar(u"e nao o repete a cada volta",
           u"if falhas_seguidas == 1:" in fonte,
           u"800 linhas com uma informacao so e o outro lado do mesmo defeito")


def teste_mapeamentos_preguicosos():
    secao(u"mapeamentos preguicosos: contrato, e sem recursao")
    import sys as _sys
    if APP not in _sys.path:
        _sys.path.insert(0, APP)
    import numpy as np
    import engine
    import radai_watcher as W

    arr = np.zeros((8, 8, 8), np.int16)
    arr[2:5, 2:5, 2:5] = 1
    arr[5:7, 5:7, 5:7] = 2
    cru = engine.MasksCruas(arr, {1: "lung_left", 2: "liver"})

    for rotulo, m in ((u"MasksCruas", cru),
                      (u"_UniaoDeCruas", W._UniaoDeCruas([cru])),
                      (u"_MasksJuntas", W._MasksJuntas(cru, {})),
                      (u"_Sobreposto", engine._Sobreposto(cru))):
        try:
            n = len(m)
            recursao = False
        except RecursionError:
            n, recursao = -1, True
        checar(u"%s: `len` nao recorre" % rotulo, not recursao,
               u"`len(list(self))` dentro de `__len__` e recursao infinita")
        checar(u"%s: len bate com as chaves" % rotulo,
               (not recursao) and n == len(list(m)), str(n))
        checar(u"%s: iterar devolve os nomes" % rotulo,
               sorted(m) == ["liver", "lung_left"], str(sorted(m)))
        checar(u"%s: `in` responde" % rotulo,
               ("liver" in m) and ("nao_existe" not in m))
        checar(u"%s: `[]` materializa uma so" % rotulo,
               int(np.asarray(m["liver"]).sum()) == 8,
               str(int(np.asarray(m["liver"]).sum())))
        checar(u"%s: NAO tem `.items()`" % rotulo, not hasattr(m, "items"),
               u"ter `.items()` convida a materializar tudo")

    sob = engine._Sobreposto(cru)
    sob["novo"] = arr > 0
    checar(u"o que se escreve fica na camada de cima", "novo" in sob)
    checar(u"e a base continua intocada", "novo" not in cru)
    checar(u"e o len acompanha", len(sob) == 3, str(len(sob)))

    fora, origem = engine.curar(W._UniaoDeCruas([cru]), {})
    checar(u"`curar` aceita mapeamento preguicoso",
           sorted(fora) == ["liver", "lung_left"], str(sorted(fora)))
    checar(u"e devolve origem para cada um", len(origem) == 2, str(origem))
    checar(u"e NAO copiou a base",
           not isinstance(fora, dict),
           u"`dict(masks_nossas)` com as 79 cruas sao 1,7 GB")

    import io as _io
    import os as _os
    src = _io.open(_componentes.fonte("app/radai_watcher.py"),
                   encoding="utf-8", errors="replace").read()
    checar(u"o lote nao chama `.items()` sobre as cruas de uma task",
           u"for nome, m in (mapa or {}).items():" not in src,
           u"foi assim que o AI_completo deixou de ser gravado")


def teste_arvore_do_sincronizador():
    import datetime
    secao(u"A arvore do sincronizador: subpasta profunda e serie partida")

    base = tempfile.mkdtemp(prefix="radai_vigia_prof_")
    try:
        root = os.path.join(base, "TCs")
        casos = [("PAC_A_10001", "2026_AGO_28_TC_10h33", "S002_PELVE", 40),
                 ("PAC_B_10002", "2026_AGO_28_TC_14h05", "S003_TORAX", 60),
                 ("PAC_C_10003", "2026_AGO_29_TC_08h10", "S001_ABDOME", 25)]
        for pid, data, serie, n in casos:
            d = os.path.join(root, pid, data, serie)
            os.makedirs(d)
            escreve_serie(d, pid, datetime.datetime(2026, 8, 28, 10, 33), n)

        inteira = os.path.join(root, "PAC_C_10003", "2026_AGO_29_TC_08h10",
                               "S001_ABDOME")
        parte2 = inteira + "_parte2"
        os.makedirs(parte2)
        for f in sorted(os.listdir(inteira))[12:]:
            shutil.move(os.path.join(inteira, f), os.path.join(parte2, f))

        import sys as _s
        if APP not in _s.path:
            _s.path.insert(0, APP)
        import radai_batch
        series = radai_batch.varrer(root, min_cortes=20)
        checar(u"[Rodar agora] achou as 3 series em 3 niveis de subpasta",
               len(series) == 3, u"%d" % len(series))
        checar(u"[Rodar agora] e a partida veio inteira (25 cortes)",
               25 in [x["cortes"] for x in series],
               u"%s" % sorted(x["cortes"] for x in series))

        cfg = os.path.join(base, "prof.config")
        io.open(cfg, "w", encoding="utf-8").write(
            "ROOT=%s\nDRY_RUN=1\nMIN_SLICES=20\nDAYS_BACK=0\nPORT=8791\n" % root)
        antigo = os.environ.get("RADAI_CONFIG")
        os.environ["RADAI_CONFIG"] = cfg
        try:
            import importlib
            import radai_watcher
            importlib.reload(radai_watcher)
            achadas = list(radai_watcher.scan_root()[0].values())
        finally:
            if antigo is None:
                os.environ.pop("RADAI_CONFIG", None)
            else:
                os.environ["RADAI_CONFIG"] = antigo
        checar(u"[vigia] achou as 3 series", len(achadas) == 3,
               u"%d" % len(achadas))
        partida = [x for x in achadas if x["count"] == 25]
        checar(u"[vigia] e a partida veio inteira (25 cortes)",
               len(partida) == 1,
               u"%s" % sorted(x["count"] for x in achadas))
        if partida:
            checar(u"[vigia] e ele guarda as DUAS pastas dela",
                   len(partida[0].get("dirs") or {}) == 2,
                   u"%d" % len(partida[0].get("dirs") or {}))
    finally:
        _soltar_logs()
        shutil.rmtree(base, ignore_errors=True)


def teste_a_escolha_do_operador_manda_na_escada():
    secao(u"a escolha do operador manda na escada")
    import json as _json
    import sys as _sys
    if APP not in _sys.path:
        _sys.path.insert(0, APP)
    import radai_watcher as W
    from pathlib import Path

    base = novo_temp("radai_fila_")
    pasta = os.path.join(base, "PAC")
    os.makedirs(pasta, exist_ok=True)

    series = {
        "1.2.5mm": {"dir": Path(pasta), "espessura_mm": 5.0, "count": 100,
                    "modality": "CT", "eixo": "axial", "z0": 0.0, "z1": 495.0},
        "1.2.06mm": {"dir": Path(pasta), "espessura_mm": 0.6, "count": 400,
                     "modality": "CT", "eixo": "axial", "z0": 0.0, "z1": 239.4},
    }
    for uid, s in series.items():
        s["uid"] = uid

    sem = W.escolher_com_decisao(dict(series))
    checar(u"sem marca, a escada decide: a de 5 mm entra",
           "1.2.5mm" in sem, ", ".join(sorted(sem)))
    checar(u"e a de 0,6 mm fica de fora (abaixo do piso)",
           "1.2.06mm" not in sem)

    r = W.gravar_decisao(Path(pasta), "1.2.06mm", "incluir")
    checar(u"gravar a decisao devolve ok", r.get("ok"), str(r))
    com = W.escolher_com_decisao(dict(series))
    checar(u"`incluir` faz entrar a de 0,6 mm, que a escada recusava",
           "1.2.06mm" in com,
           u"e o caso da radiocirurgia de cranio, que a heuristica recusa "
           u"de proposito")
    checar(u"e o motivo diz que foi voce",
           u"voc" in (com.get("1.2.06mm") or u"").lower(),
           str(com.get("1.2.06mm")))

    W.gravar_decisao(Path(pasta), "1.2.5mm", "pular")
    com = W.escolher_com_decisao(dict(series))
    checar(u"`pular` tira a de 5 mm, que a escada escolhia",
           "1.2.5mm" not in com, ", ".join(sorted(com)))

    W.gravar_decisao(Path(pasta), "1.2.5mm", "")
    W.gravar_decisao(Path(pasta), "1.2.06mm", "")
    volta = W.escolher_com_decisao(dict(series))
    checar(u"apagar as marcas devolve o comportamento de antes",
           set(volta) == set(sem), ", ".join(sorted(volta)))

    for ruim in ("apagar", "INCLUIR", "sim", "1", "../x"):
        checar(u"recusa a decisao `%s`" % ruim,
               W.gravar_decisao(Path(pasta), "1.2.5mm", ruim).get("ok") is False)

    W.gravar_decisao(Path(pasta), "1.2.5mm", "pular")
    m = W.m_path(Path(pasta), "1.2.5mm", "fila")
    checar(u"a decisao mora em `_RadAI`, com os outros marcadores",
           "_RadAI" in str(m) and m.exists(), str(m))
    dados = _json.loads(m.read_text(encoding="utf-8"))
    checar(u"e registra quem e quando", bool(dados.get("quem"))
           and bool(dados.get("quando")), str(dados))

    fonte = io.open(_componentes.fonte("app/radai_watcher.py"),
                    encoding="utf-8").read()
    checar(u"a fila do laco usa `escolher_com_decisao`",
           "escolhidas = escolher_com_decisao(series)" in fonte)
    checar(u"e o plano da tela tambem",
           "escolhidas_sim = escolher_com_decisao(series)" in fonte,
           u"tela que promete o que o laco nao faz e o defeito de 01/09")
    import ast as _ast
    _arv = _ast.parse(fonte)
    _crus = []
    for _f in _ast.walk(_arv):
        if not isinstance(_f, _ast.FunctionDef):
            continue
        if _f.name in ("escolher_simulacao", "escolher_com_decisao"):
            continue
        for _n in _ast.walk(_f):
            if isinstance(_n, _ast.Call) and                     getattr(_n.func, "id", "") == "escolher_simulacao":
                _crus.append(_f.name)
    checar(u"ninguem alem de `escolher_com_decisao` chama a escada crua",
           not _crus, u", ".join(sorted(set(_crus))))


def teste_o_plano_tem_localizar_e_o_liberar_mora_no_aviso():
    secao(u"o plano tem localizar, e o Liberar mora dentro do aviso")
    import radai_watcher as W
    pag = W.PAGE
    checar(u"a caixa de localizar existe no plano",
           u'id="pl_loc"' in pag and u'oninput="planoFiltrar()"' in pag)
    checar(u"e o plano fica guardado, para filtrar sem varrer de novo",
           u"var PLANO = null" in pag and u"function planoFiltrar(" in pag)
    checar(u"o casamento ignora acento e caixa",
           u"function planoNorm(" in pag and u"normalize('NFD')" in pag)
    checar(u"  e a classe dos acentos viaja escapada, e nao como caractere",
           (chr(92) + u"u0300") in pag and (u"[" + u"̀") not in pag)
    checar(u"o exame casa por pasta, prontuario e data",
           u"[e.pasta, e.pid, e.date," in pag)
    checar(u"e nada com o trecho diz o que fazer, em vez de parecer pasta vazia",
           u"Apague a busca para ver a pasta inteira" in pag)

    checar(u"o botao Liberar nasce dentro do proprio aviso",
           u"libere aqui para tentar de novo" in pag
           and u'onclick="liberar()"' in pag)
    checar(u"e nao ha mais um botao solto la embaixo",
           u'id="btlib"' not in pag)
    checar(u"o que vem do servidor e escapado antes de virar HTML",
           u"esc(d.recarga)" in pag and u"f.innerHTML=msgs.join(" in pag)


def teste_pid_de_arquivo_do_share_nao_mata_processo():
    secao(u"pid vindo de arquivo do share nao mata processo")
    import radai_watcher as mod

    import subprocess as _sp
    filho = _sp.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        matou = mod._matar_travado(filho.pid, "1.2.3.4.5171209")
        time.sleep(0.6)
        vivo = filho.poll() is None
        checar(u"pid que o registro local nao conhece NAO e morto",
               matou is False, repr(matou))
        checar(u"   e o processo continua vivo (a prova de que nao matou)",
               vivo, u"o filho morreu")
    finally:
        try:
            filho.kill()
            filho.wait(timeout=5)
        except Exception:
            pass

    mod.registrar_pid_local()
    checar(u"e o registro reconhece o proprio processo",
           mod._pid_e_nosso(os.getpid()))
    checar(u"e continua nao reconhecendo um pid forjado",
           not mod._pid_e_nosso(4321))

    import json as _json
    alvo = mod.LOG_DIR / mod.PIDS_LOCAIS
    guardado = alvo.read_text(encoding="utf-8")
    try:
        velho_ts = time.time() - (mod.PID_LOCAL_VALIDO_H + 1) * 3600
        alvo.write_text(_json.dumps([{"pid": 31337, "quando": velho_ts}]),
                        encoding="utf-8")
        checar(u"pid registrado ha tempo demais deixa de ser nosso",
               not mod._pid_e_nosso(31337))
        alvo.write_text(_json.dumps([{"pid": 31337, "quando": time.time()}]),
                        encoding="utf-8")
        checar(u"   e um registrado agora continua sendo",
               mod._pid_e_nosso(31337))
    finally:
        alvo.write_text(guardado, encoding="utf-8")


def teste_o_uid_nao_tira_o_marcador_da_pasta_do_paciente():
    secao(u"o UID nao tira o marcador da pasta do paciente")
    import radai_sets as S
    import radai_watcher as mod
    base = tempfile.mkdtemp(prefix="radai_eleg_")
    _TEMPS.append(base)

    maus = ["../../../../../../Users/Public/pwn", "..\\..\\pwn", "a/b",
            "C:x", "", ".", "..", "a\x00b", "x" * 200]
    passou = []
    for u in maus:
        try:
            mod.m_path(base, u, "lock")
            passou.append(u)
        except ValueError:
            pass
    checar(u"UID que escaparia da pasta e recusado",
           not passou, u"passaram: %r" % (passou,))

    bons = ["9.9.9.99999.2.55.3.123456", "1.2.06mm", "1.2.5mm", "1.2.3"]
    recusados = []
    for u in bons:
        try:
            mod.m_path(base, u, "lock")
        except ValueError:
            recusados.append(u)
    checar(u"UID legitimo (inclusive fora do charset) continua aceito",
           not recusados, u"recusou: %r" % (recusados,))

    escapou = []
    for c in ["../pwn12", "a/b", "..\\x"]:
        try:
            S.nome_do_arquivo("oar", "20260914", c)
            escapou.append(c)
        except ValueError:
            pass
    checar(u"o nome do RTSTRUCT recusa separador no sufixo do UID",
           not escapou, u"passaram: %r" % (escapou,))
    checar(u"e aceita um sufixo legitimo com ponto",
           S.nome_do_arquivo("oar", "20260914", "5171.209").endswith(
               "5171.209.dcm"))


def teste_a_base_e_achada_por_familia_e_nao_pelo_nome():
    base = tempfile.mkdtemp(prefix="radai_familia_")
    try:
        root = os.path.join(base, "root")
        os.makedirs(root)
        mod = carregar(root, base)

        sys.path.insert(0, APP)
        try:
            import radai_tasks as RT
        finally:
            sys.path.pop(0)

        geracoes = sorted(t for t, f in RT.FAMILIA.items() if f == "total")
        checar(u"a tabela declara mais de uma geração da base",
               len(geracoes) >= 2, geracoes)

        for nome in geracoes:
            cruas = {nome: "AS_CRUAS_DA_BASE",
                     "head_glands_cavities": "outra",
                     "lung_vessels": "outra"}
            achado = mod.cruas_da_base(cruas)
            checar(u"com a base em `%s`, os rótulos crus são achados" % nome,
                   achado == "AS_CRUAS_DA_BASE", achado)

        checar(u"sem nenhuma task da família, devolve None "
               u"(e o chamador diz o motivo no log)",
               mod.cruas_da_base({"head_glands_cavities": "x"}) is None)
        checar(u"dicionário vazio devolve None", mod.cruas_da_base({}) is None)
        checar(u"`None` devolve None (o `ENTREGAR_TS` desligado)",
               mod.cruas_da_base(None) is None)

        checar(u"`total_mr` NAO passa por base — é família própria",
               RT.familia_da_task("total_mr") != "total"
               and mod.cruas_da_base({"total_mr": "x"}) is None)

        fonte = io.open(_componentes.fonte("app/radai_watcher.py"),
                        encoding="utf-8", errors="replace").read()
        checar(u"o log não diz mais «a task `total`» "
               u"(numa estação com `total_v3` isso manda procurar o nada)",
               "os rotulos crus da task `total`" not in fonte)

        import ast as _ast
        arv = _ast.parse(fonte)
        chamadas = [n for n in _ast.walk(arv)
                    if isinstance(n, _ast.Call)
                    and isinstance(n.func, _ast.Name)
                    and n.func.id == "_rodar_hnlnl"]
        checar(u"há exatamente um ponto de chamada de `_rodar_hnlnl`",
               len(chamadas) == 1, len(chamadas))
        if chamadas:
            arg = chamadas[0].args[1] if len(chamadas[0].args) > 1 else None
            inteiro = isinstance(arg, _ast.Name) and arg.id == "cruas"
            checar(u"e ele recebe o dicionário INTEIRO (`cruas`), nunca uma "
                   u"chave escolhida no vigia", inteiro,
                   _ast.dump(arg)[:90] if arg is not None else "sem 2o arg")
        _rh = [n for n in _ast.walk(arv) if isinstance(n, _ast.FunctionDef)
               and n.name == "_rodar_hnlnl"]
        _delega = _rh and any(
            isinstance(n, _ast.Call) and isinstance(n.func, _ast.Attribute)
            and n.func.attr == "niveis_cervicais_da_serie"
            for n in _ast.walk(_rh[0]))
        checar(u"e `_rodar_hnlnl` delega à cadeia comum (a busca por família "
               u"é a de `radai_output`)", bool(_delega))
    finally:
        _soltar_logs()
        shutil.rmtree(base, ignore_errors=True)


def _app_import(nome):
    sys.path.insert(0, APP)
    try:
        return __import__(nome)
    finally:
        sys.path.pop(0)


class _SemTasksDaSerie(object):

    def __init__(self, rt, substituta=None):
        self.rt, self.sub = rt, substituta

    def __enter__(self):
        self.tinha = hasattr(self.rt, "tasks_da_serie")
        self.velha = getattr(self.rt, "tasks_da_serie", None)
        if self.sub is None:
            if self.tinha:
                delattr(self.rt, "tasks_da_serie")
        else:
            self.rt.tasks_da_serie = self.sub
        return self

    def __exit__(self, *a):
        if self.tinha:
            self.rt.tasks_da_serie = self.velha
        elif hasattr(self.rt, "tasks_da_serie"):
            delattr(self.rt, "tasks_da_serie")
        return False


def teste_task_de_outra_modalidade_e_anunciada():
    secao(u"a lista de tasks pela modalidade da serie")
    RT = _app_import("radai_tasks")
    base = tempfile.mkdtemp(prefix="radai_modalidade_")
    try:
        mod = carregar(os.path.join(base, "root"), base)
        ct = sorted(t for t, e in RT.POR_NOME.items()
                    if str(e.get("modalidade", "")).upper() == "CT")
        mr = sorted(t for t, e in RT.POR_NOME.items()
                    if str(e.get("modalidade", "")).upper() == "MR")
        checar(u"o catálogo tem task de CT e de MR (senão isto não mede nada)",
               bool(ct) and bool(mr), "CT=%d MR=%d" % (len(ct), len(mr)))
        if not (ct and mr):
            return

        ditas = []
        with _SemTasksDaSerie(RT):
            for modalidade, tarefas, espera in (
                    ("MR", [ct[0]], True), ("CT", [ct[0]], False),
                    ("MR", [mr[0]], False), ("", [ct[0]], False)):
                del ditas[:]
                fora = mod.tasks_pela_modalidade(list(tarefas), modalidade,
                                                 log=ditas.append)
                avisou = any("ATENCAO" in m for m in ditas)
                checar(u"sem a regra, série `%s` com `%s`: %s, e roda como veio"
                       % (modalidade or "(sem modalidade)", tarefas[0],
                          "avisa" if espera else "não avisa"),
                       avisou == espera and fora == tarefas,
                       "; ".join(ditas)[:110])
            del ditas[:]
            mod.tasks_pela_modalidade([ct[0]], "MR", log=ditas.append)
            texto = " ".join(ditas)
            checar(u"  o aviso nomeia a task", ct[0] in texto, texto[:110])
            checar(u"  e diz de que modalidade ela é", "CT" in texto, texto[:110])

        chamadas = []

        def _regra(tarefas, modalidade, pasta_pesos=None, log=None):
            chamadas.append((list(tarefas), modalidade))
            if log:
                log("task %s e de CT; nao roda nesta serie MR" % tarefas[0])
            return ["total_mr"] if modalidade == "MR" else list(tarefas)

        with _SemTasksDaSerie(RT, _regra):
            del ditas[:]
            fora = mod.tasks_pela_modalidade(["total_v3"], "MR", log=ditas.append)
        checar(u"com a regra, a RM recebe a base DELA", fora == ["total_mr"], fora)
        checar(u"  a regra recebe a modalidade da série",
               chamadas and chamadas[-1] == (["total_v3"], "MR"), chamadas)
        checar(u"  e o log diz o que o config pediu e o que roda",
               any("total_mr" in m and "total_v3" in m for m in ditas),
               "; ".join(ditas)[:120])
        checar(u"  e as linhas da regra chegam ao log",
               any("nao roda nesta serie MR" in m for m in ditas))

        def _quebrada(*a, **k):
            raise ValueError("regra quebrada de proposito")

        with _SemTasksDaSerie(RT, _quebrada):
            del ditas[:]
            fora = mod.tasks_pela_modalidade([ct[0]], "MR", log=ditas.append)
        checar(u"regra que levanta: roda como veio, diz por quê, e AVISA",
               fora == [ct[0]] and any("levantou" in m for m in ditas)
               and any("ATENCAO" in m for m in ditas), "; ".join(ditas)[:140])
    finally:
        _soltar_logs()
        shutil.rmtree(base, ignore_errors=True)


def teste_a_varredura_leva_a_modalidade():
    secao(u"a varredura leva a modalidade ate a serie")
    agora = datetime.now()
    mod, root, base = montar([("PAC_MOD", agora - timedelta(days=1), 8)])
    envelhecer(root, 60)
    fila, _ = fila_de(mod)
    checar(u"a série entrou na fila", len(fila) == 1, len(fila))
    if fila:
        checar(u"e ela chega a `process_series` com `modality`",
               fila[0].get("modality") == "CT", fila[0].get("modality"))


class _MotorQueRegistra(_MotorFalso):

    def __init__(self, erro, log_do_job=(), plano=None, espera=0.0,
                 drenado=(), recorte=None):
        _MotorFalso.__init__(self, erro)
        self.log_do_job = list(log_do_job)
        self.plano = plano
        self.espera = espera
        self.drenado = list(drenado)
        self.recorte = recorte
        self.tasks = []

    def drenar_log(self, jid, escrever, parar, a_cada_s=None, intervalo=3.0):
        for l in self.drenado:
            escrever(l)
        return None

    def copy_sorted(self, arquivos, destino):
        time.sleep(self.espera)

    def _job(self, jid):
        d = {"log": list(self.log_do_job)}
        if self.plano:
            d["plano"] = dict(self.plano)
        if self.recorte:
            d["recorte_no_corpo"] = dict(self.recorte)
        return d

    def run_ts_task(self, ref, t, **kw):
        self.tasks.append(t)
        raise RuntimeError(self.erro)


def _casos_em(pasta):
    d = os.path.join(pasta, "casos")
    try:
        return sorted(os.path.join(d, n) for n in os.listdir(d))
    except OSError:
        return []


def teste_o_vigia_registra_o_caso():
    secao(u"o vigia registra o caso (e o que falhou tambem)")
    RT = _app_import("radai_tasks")
    agora = datetime.now()
    mod, root, base = montar([("PAC_REG_1", agora - timedelta(days=1), 8)],
                             extra={"DRY_RUN": "0"})
    envelhecer(root, 60)
    fila, _ = fila_de(mod)
    if not checar(u"a série entrou na fila", len(fila) == 1, len(fila)):
        return
    s = fila[0]
    s["modality"] = "MR"
    pasta_reg = tempfile.mkdtemp(prefix="radai_caso_vigia_")
    velho = os.environ.get("RADAI_REGISTRO_DIR")
    os.environ["RADAI_REGISTRO_DIR"] = pasta_reg
    fallback = ("[02:14:09] a placa falhou em parte 3/5: CUDA error: unspecified "
                "launch failure; refazendo a task INTEIRA em CPU")
    motor = _MotorQueRegistra(
        "nnUNet parou de proposito na bateria",
        log_do_job=["[02:00:01] TS total_mr (iniciando)", fallback],
        plano={"modo": "gpu_resultado_na_cpu", "motivo": "2048 MiB livres",
               "vram_livre_mb": 2048, "vram_total_mb": 5120,
               "placa": "Quadro P2200"},
        recorte={"total_mr": {"estado": u"nao se aplica",
                              "motivo": u"a biblioteca ignora --body_seg "
                                        u"em task de RM",
                              "flag": False, "alerta": False,
                              "falta_peso": False}},
        espera=1.3,
        drenado=["lendo os cortes de %s" % os.path.basename(s["dir"])])
    mod.carregar_engine = lambda: motor

    def _regra(tarefas, modalidade, pasta_pesos=None, log=None):
        return ["total_mr"] if modalidade == "MR" else list(tarefas)

    try:
        with _SemTasksDaSerie(RT, _regra):
            mod.claim(s["dir"], s["uid"], {})
            ok = mod.process_series(s)
        checar(u"a série falhou (de propósito)", ok is False)
        checar(u"a task que o motor recebeu é a da modalidade DA SÉRIE",
               motor.tasks == ["total_mr"], motor.tasks)
        casos = _casos_em(pasta_reg)
        if not checar(u"o vigia gravou UM caso no registro", len(casos) == 1,
                      casos):
            return
        with io.open(os.path.join(casos[0], "caso.json"), encoding="utf-8") as f:
            d = json.load(f)
        r, ex, se = d.get("resultado") or {}, d.get("execucao") or {}, d.get("serie") or {}
        checar(u"  o caso diz que NÃO concluiu, e por quê",
               r.get("ok") is False and "parou de proposito" in (r.get("erro") or ""),
               r)
        checar(u"  `segundos_totais` é o tempo REAL da série (>= 1,3 s)",
               float(d.get("segundos_totais") or 0) >= 1.2,
               d.get("segundos_totais"))
        checar(u"  e diz de onde veio o tempo",
               d.get("segundos_origem") == u"medido por quem rodou a serie",
               d.get("segundos_origem"))
        checar(u"  a modalidade da série vai para o caso",
               se.get("modalidade") == "MR" and se.get("origem") == "vigia", se)
        checar(u"  o modo e a VRAM do início vêm do plano do MOTOR",
               ex.get("modo") == "gpu_resultado_na_cpu"
               and ex.get("vram_livre_inicio_mb") == 2048
               and ex.get("plano_origem") == "motor", ex)
        checar(u"  o fallback do log do motor está no caso",
               any("refazendo a task INTEIRA em CPU" in x
                   for x in ex.get("fallbacks") or []), ex.get("fallbacks"))
        checar(u"  tempo por parte: `null` DECLARADO, e não zero — e a nota "
               u"diz que nenhuma parte foi vista, e não que o motor não expõe",
               ex.get("tempo_por_parte") is None
               and u"nenhuma parte vista" in (ex.get("tempo_por_parte_nota")
                                              or u"")
               and u"nao expos" not in (ex.get("tempo_por_parte_nota") or u""),
               ex.get("tempo_por_parte_nota"))
        rc = ex.get("recorte_no_corpo") or {}
        checar(u"  o recorte no corpo do caso é o que VALEU, lido do job: a RM "
               u"diz «nao se aplica»",
               (rc.get("total_mr") or {}).get("estado") == u"nao se aplica",
               rc)
        checar(u"  e a CHAVE do config vai para `recorte_no_corpo_pedido`",
               ex.get("recorte_no_corpo_pedido") is True,
               ex.get("recorte_no_corpo_pedido"))
        checar(u"  pedida × rodada: o config pediu total_v3, a série rodou total_mr",
               ex.get("tasks_pedidas") == ["total_v3"]
               and ex.get("tasks_da_serie") == ["total_mr"]
               and ex.get("task_em_curso_na_falha") == "total_mr", ex)
        pr = d.get("processamento") or {}
        checar(u"  o caso do vigia diz modo AUTO, sem comparacao (v8.3)",
               pr.get("modo") == "auto"
               and not any((pr.get("comparacao") or {}).values())
               and pr.get("tasks_ligadas") == ["total_mr"], pr)
        idx = os.path.join(pasta_reg, "indice.jsonl")
        try:
            ult = json.loads([l for l in io.open(idx, encoding="utf-8")
                              .read().splitlines() if l.strip()][-1])
        except Exception as e:
            ult = {"erro": str(e)}
        checar(u"  e o indice leva o modo de processamento e a pasta do caso",
               ult.get("modo_processamento") == "auto"
               and ult.get("pasta") == os.path.basename(casos[0]), ult)
        pasta_pac = os.path.basename(os.path.dirname(s["dir"]))
        pasta_ser = os.path.basename(s["dir"])
        textos = {}
        for nome in ("caso.json", "caso.md", "log.txt"):
            p = os.path.join(casos[0], nome)
            textos[nome] = io.open(p, encoding="utf-8").read() if os.path.isfile(p) else ""
        checar(u"  o log.txt existe e tem a série", "=== serie" in textos["log.txt"],
               textos["log.txt"][:80])
        for nome, tx in sorted(textos.items()):
            vaz = [x for x in (s["pid"], s["uid"], s["uid"][-8:], pasta_pac,
                               pasta_ser, root) if x and x in tx]
            checar(u"  %s sem PID, UID, pasta de paciente nem caminho" % nome,
                   not vaz, vaz)
        mod2, root2, base2 = montar([("PAC_REG_2", agora - timedelta(days=2), 8)])
        envelhecer(root2, 60)
        f2, _ = fila_de(mod2)
        if f2:
            mod2.claim(f2[0]["dir"], f2[0]["uid"], {})
            mod2.process_series(f2[0])
        checar(u"série de DRY_RUN não vira caso no registro",
               len(_casos_em(pasta_reg)) == 1, _casos_em(pasta_reg))
    finally:
        if velho is None:
            os.environ.pop("RADAI_REGISTRO_DIR", None)
        else:
            os.environ["RADAI_REGISTRO_DIR"] = velho
        shutil.rmtree(pasta_reg, ignore_errors=True)


def teste_o_caso_do_vigia_com_sucesso():
    secao(u"o caso de uma serie que deu certo")
    base = tempfile.mkdtemp(prefix="radai_caso_vigia_")
    velho = os.environ.get("RADAI_REGISTRO_DIR")
    os.environ["RADAI_REGISTRO_DIR"] = os.path.join(base, "reg")
    try:
        mod = carregar(os.path.join(base, "root"), base, extra={"DRY_RUN": "0"})
        s = {"uid": "1.9.999.2.55.3.11111.12345678", "pid": "FANTOMA-OK",
             "dir": os.path.join(base, "root", "SOBRENOME_FANTOMA", "CT_X"),
             "modality": "CT", "count": 117, "esp_dec": 3.75}
        info = {"ok": True, "erro": "", "ambiente": False, "modalidade": "CT",
                "tasks_pedidas": ["total_v3"], "tarefas": ["total_v2"],
                "tasks_ok": ["total_v2"], "task_em_curso": "",
                "etapas": [{"etapa": "TS total_v2", "segundos": 1812.4}],
                "log_motor": ["[03:00:00] base anatomica: total_v2 (a total_v3 "
                              "nao esta instalada nesta estacao)"],
                "plano": {"modo": "cpu", "motivo": "sem placa",
                          "modo_do_plano": "gpu",
                          "recuo_cpu": {"onde": "parte 3/5 (vertebras)",
                                        "prova": "CUDA error: out of memory",
                                        "segundos_na_placa": 95.0}},
                "plano_origem": "motor", "partes": [{"parte": 1, "s": 300.0}],
                "dispositivo": "cpu", "estruturas": 98,
                "tasks_falharam": [{"task": "abdominal_muscles",
                                    "classe": "recurso",
                                    "erro": "MemoryError lendo %s"
                                    % os.path.join(base, "root",
                                                   "SOBRENOME_FANTOMA")}],
                "medidas": {"cortes": 117, "forma_zyx": [117, 512, 512],
                            "espacamento_zyx_mm": [3.75, 0.977, 0.977],
                            "fov_mm": 500.2}}
        pasta = mod._registrar_caso_do_vigia(s, time.time() - 2400.0, info, None)
        checar(u"o caso foi gravado", bool(pasta) and os.path.isdir(pasta), pasta)
        if not pasta:
            return
        d = json.load(io.open(os.path.join(pasta, "caso.json"), encoding="utf-8"))
        ex = d.get("execucao") or {}
        checar(u"  ok e estruturas", (d.get("resultado") or {}).get("ok") is True
               and (d.get("resultado") or {}).get("estruturas") == 98)
        checar(u"  os 40 min da série, e não o instante do registro",
               2390 <= float(d.get("segundos_totais") or 0) <= 2500,
               d.get("segundos_totais"))
        checar(u"  a task que RODOU (a reserva) está nas versões",
               (d.get("versoes") or {}).get("tasks") == ["total_v2"],
               (d.get("versoes") or {}).get("tasks"))
        checar(u"  e a queda de base conta como fallback",
               any("base anatomica" in x for x in ex.get("fallbacks") or []),
               ex.get("fallbacks"))
        checar(u"  o tempo por parte do motor, quando ele expõe, é gravado",
               ex.get("tempo_por_parte") == [{"parte": 1, "s": 300.0}], ex)
        checar(u"  e a placa que caiu fica no caso: `modo` é o que valeu, "
               u"`modo_do_plano` e `recuo_cpu` dizem o que o plano escolheu",
               ex.get("modo") == "cpu" and ex.get("modo_do_plano") == "gpu"
               and (ex.get("recuo_cpu") or {}).get("onde")
               == "parte 3/5 (vertebras)",
               dict((k, ex.get(k)) for k in ("modo", "modo_do_plano",
                                             "recuo_cpu")))
        checar(u"  e sem decisao de recorte no job, o caso diz `null` (nao "
               u"sei), e nao a chave", ex.get("recorte_no_corpo") is None
               and "recorte_no_corpo_pedido" in ex,
               dict((k, ex.get(k)) for k in ("recorte_no_corpo",
                                             "recorte_no_corpo_pedido")))
        checar(u"  a task que falhou e nao derrubou a serie vai ao caso, com "
               u"a classe (as duas portas levam `tasks_falharam`)",
               [(f.get("task"), f.get("classe"))
                for f in ex.get("tasks_falharam") or []]
               == [("abdominal_muscles", "recurso")], ex.get("tasks_falharam"))
        checar(u"  as medidas técnicas da imagem entram na série",
               (d.get("serie") or {}).get("fov_mm") == 500.2, d.get("serie"))
        texto = io.open(os.path.join(pasta, "caso.json"), encoding="utf-8").read()
        checar(u"  o nome da pasta do paciente não aparece",
               "SOBRENOME_FANTOMA" not in texto and "12345678" not in texto)
    finally:
        if velho is None:
            os.environ.pop("RADAI_REGISTRO_DIR", None)
        else:
            os.environ["RADAI_REGISTRO_DIR"] = velho
        _soltar_logs()
        shutil.rmtree(base, ignore_errors=True)


def teste_o_status_compartilhado_nao_leva_caminho_no_erro():
    secao(u"o status compartilhado nao leva caminho nem UID no erro")
    base = novo_temp()
    status = os.path.join(base, "status_da_frota")
    mod = carregar(os.path.join(base, "share"), base,
                   extra={"STATUS_DIR": status})
    uid = "1.2.826.0.1.3680043.8.498.5156037744130450"
    erros = [
        u"PermissionError: [WinError 5] Acesso negado: '\\\\\\\\servidor\\\\"
        u"exames\\\\Patients\\\\ISCA BELTRANO 12345\\\\CT\\\\_RadAI\\\\%s"
        u".lock.json'" % uid,
        u"FileNotFoundError: nao achei D:\\EXAMES\\ISCA BELTRANO 12345\\CT",
        u"KeyError: '%s'" % uid,
    ]
    lidos = []
    for e in erros:
        mod.STATE["worker_erro"] = e
        mod.salvar_status()
        try:
            with io.open(os.path.join(status, "%s.json" % mod.MACHINE),
                         encoding="utf-8") as f:
                lidos.append(json.load(f).get("worker_erro") or u"")
        except (IOError, OSError, ValueError) as x:
            lidos.append(u"<nao li: %s>" % x)
    checar(u"o nome da pasta do paciente nao vai ao STATUS_DIR",
           not any(u"ISCA" in t or u"BELTRANO" in t for t in lidos), lidos)
    checar(u"  nem o share, nem a unidade com o caminho",
           not any(u"servidor" in t or u"EXAMES" in t for t in lidos), lidos)
    checar(u"  nem o UID inteiro", not any(uid in t for t in lidos), lidos)
    checar(u"  e o TIPO do erro fica (e o que a frota precisa saber)",
           [t.split(u":")[0] for t in lidos]
           == [u"PermissionError", u"FileNotFoundError", u"KeyError"], lidos)
    mod.STATE["worker_erro"] = erros[1]
    try:
        tela = (mod.status() or {}).get("worker_erro")
    except Exception as x:
        tela = u"<a rota levantou %s>" % type(x).__name__
    checar(u"a tela (/api/status, 127.0.0.1) continua recebendo o erro "
           u"inteiro: so o arquivo do share e higienizado", tela == erros[1],
           tela)


_AFIRMA_PID = re.compile(u"\\bleva\\b[^.(\u2014]*PatientID")


def _recusa_afirma_pid(texto):
    return bool(_AFIRMA_PID.search(u" ".join(str(texto or u"").split())))


def teste_a_recusa_do_status_dir_diz_o_que_o_arquivo_leva():
    secao(u"a recusa do STATUS_DIR diz o que o arquivo leva")
    base = novo_temp()
    status = os.path.join(base, "status_da_frota")
    mod = carregar(os.path.join(base, "share"), base,
                   extra={"STATUS_DIR": status})
    mod.STATE["current"] = {"pid": u"PID_ISCA_7788", "uid": u"44130450",
                            "count": 90, "date": u"20260923",
                            "desde": u"22:10", "sdir": u"X:\\ISCA",
                            "uid_cheio": u"1.2.3.4.5.44130450"}
    mod.STATE["worker_erro"] = u""
    try:
        mod.salvar_status()
        with io.open(os.path.join(status, "%s.json" % mod.MACHINE),
                     encoding="utf-8") as f:
            arquivo = f.read()
    except (IOError, OSError) as x:
        arquivo = u"<nao li: %s>" % x
    finally:
        mod.STATE["current"] = None
    leva_pid = u"PID_ISCA_7788" in arquivo
    checar(u"o arquivo do STATUS_DIR leva o final do UID e a data da serie",
           u"44130450" in arquivo and u"20260923" in arquivo, arquivo[:300])

    linhas = []
    wlog_velho = mod.wlog
    if APP not in sys.path:
        sys.path.insert(0, APP)
    import radai_archive as _RARQ
    detector_velho = _RARQ.em_pasta_sincronizada
    mod.wlog = lambda m="": linhas.append(str(m))
    _RARQ.em_pasta_sincronizada = lambda p: (True, u"isca da bateria")
    recusado_antes = mod._STATUS_DIR_RECUSADO[0]
    try:
        devolveu = mod.conferir_status_dir()
        frota = mod.overnight_frota()
    finally:
        mod.wlog = wlog_velho
        _RARQ.em_pasta_sincronizada = detector_velho
        mod._STATUS_DIR_RECUSADO[0] = recusado_antes
    log_recusa = u" ".join(linhas)
    aviso = (frota or {}).get("aviso") or u""
    checar(u"com a pasta na nuvem, a recusa acontece (e diz no log)",
           devolveu is False and u"STATUS_DIR RECUSADO" in log_recusa,
           log_recusa[:200])
    checar(u"  o log da recusa so afirma PatientID se o arquivo o leva",
           _recusa_afirma_pid(log_recusa) == leva_pid, log_recusa[:300])
    checar(u"  e a tela da frota tambem", _recusa_afirma_pid(aviso) == leva_pid,
           aviso)
    checar(u"  e os dois dizem o que ele leva de fato (o UID da serie)",
           u"UID" in log_recusa and u"UID" in aviso, aviso)
    f = io.open(_componentes.fonte("app/radai_watcher.py"), encoding="utf-8").read()
    i = f.find("def conferir_status_dir")
    doc = f[i:f.find('"""', f.find('u"""', i) + 4)]
    checar(u"  e a docstring da recusa tambem",
           _recusa_afirma_pid(doc) == leva_pid)

    velhos = [u"O sinal de vida leva o PatientID, e dado de paciente nao sai "
              u"do ambiente da clinica.",
              u"A pasta do STATUS_DIR sincroniza com a nuvem, e o sinal de "
              u"vida leva o PatientID \u2014 este programa n\u00e3o grava "
              u"dado de paciente em pasta espelhada."]
    checar(u"  isca: os textos velhos reprovam no mesmo criterio",
           all(_recusa_afirma_pid(v) != leva_pid for v in velhos))


def _regra_do_mr_na_tela(pagina):
    return (u"temMR(d.rm_no_disco !== false)" in pagina,
            u"/_mr$/i.test(String(t))" in pagina)


def teste_o_mr_da_tela_de_recuo_segue_o_disco():
    secao(u"o MR da tela de recuo segue o disco")
    if APP not in sys.path:
        sys.path.insert(0, APP)
    import radai_tasks as RT
    import radai_watcher as W
    base = novo_temp()
    vazia = os.path.join(base, "pesos_vazios")
    os.makedirs(vazia)
    cheia = os.path.join(base, "pesos_com_rm")
    precisa = sorted(RT.datasets_necessarios(RT.BASES_MR[0],
                                             recorte_no_corpo=False))
    for n in precisa:
        os.makedirs(os.path.join(cheia, "Dataset%03d_isca_da_bateria" % n))
    checar(u"a base de RM declara os pesos que precisa", bool(precisa),
           str(precisa))
    checar(u"sem os pesos da base de RM, a estacao nao le RM",
           W.rm_no_disco(vazia) is False)
    checar(u"com eles, le — o TASKS do config (sem `_mr` de fabrica) nao "
           u"entra na conta", W.rm_no_disco(cheia) is True)
    velho = RT.baixados
    RT.baixados = lambda *a, **k: (_ for _ in ()).throw(OSError(u"isca"))
    try:
        sem_olhar = W.rm_no_disco(cheia)
    finally:
        RT.baixados = velho
    checar(u"sem conseguir olhar, devolve None (e a tela nao apaga)",
           sem_olhar is None, repr(sem_olhar))
    mod = carregar(os.path.join(base, "share"), base)
    d = mod.status() or {}
    checar(u"o status leva a resposta para a tela",
           "rm_no_disco" in d and d.get("rm_no_disco") in (True, False, None),
           str(d.get("rm_no_disco")))
    disco, sufixo = _regra_do_mr_na_tela(W.PAGE)
    checar(u"a tela de recuo decide o MR pelo disco", disco)
    checar(u"  e nao mais pelo sufixo `_mr` do TASKS", not sufixo)
    isca = W.PAGE.replace(
        u"temMR(d.rm_no_disco !== false)",
        u"temMR((d.tasks||[]).some(function(t){ return "
        u"/_mr$/i.test(String(t)) }))")
    d_i, s_i = _regra_do_mr_na_tela(isca)
    checar(u"  isca: a linha velha de volta reprova", not d_i and s_i)


def teste_a_pasta_com_espaco_sai_do_caso_do_vigia():
    secao(u"a pasta com espaco sai do caso do vigia")
    base = tempfile.mkdtemp(prefix="radai_caso_vigia_")
    velho = os.environ.get("RADAI_REGISTRO_DIR")
    os.environ["RADAI_REGISTRO_DIR"] = os.path.join(base, "reg")
    try:
        root = os.path.join(base, "root")
        mod = carregar(root, base, extra={"DRY_RUN": "0"})
        s = {"uid": "1.9.999.2.55.3.22222.87654321", "pid": "FANTOMA-ESP",
             "dir": os.path.join(root, "ISCA BELTRANO 12345", "CT_X"),
             "modality": "CT", "count": 117, "esp_dec": 3.75}
        conferidos, trocados = mod._identificadores_da_serie(s)
        checar(u"a pasta do paciente, com espaco, vai para o so_trocar",
               u"ISCA BELTRANO 12345" in trocados, trocados)
        checar(u"  e as pastas do ROOT nao (o prefixo e cortado)",
               not [x for x in trocados if x in root], trocados)
        import radai_records as _RG
        col = _RG.Coletor()
        for ln in (u"=== serie ...87654321 | FANTOMA-ESP | ISCA BELTRANO 12345\\CT_X ===",
                   u"Sem DICOM em %s" % s["dir"],
                   u"copia local em D:\\TEMP\\ISCA BELTRANO 12345 (3 arquivos)",
                   u"94 estrutura(s) do TotalSegmentator"):
            col(ln)
        info = {"ok": True, "erro": "", "ambiente": False, "modalidade": "CT",
                "tasks_pedidas": ["total_v3"], "tarefas": ["total_v3"],
                "tasks_ok": ["total_v3"], "etapas": [], "estruturas": 94,
                "medidas": {"cortes": 117}}
        pasta = mod._registrar_caso_do_vigia(s, time.time() - 60.0, info, col)
        checar(u"o caso foi gravado", bool(pasta) and os.path.isdir(pasta), pasta)
        if not pasta:
            return
        lt = io.open(os.path.join(pasta, "log.txt"), encoding="utf-8").read()
        sobra = [x for x in (u"ISCA", u"BELTRANO", u"12345") if x in lt]
        checar(u"  e nenhum pedaco do nome sobra no log.txt", not sobra,
               u"%s | %s" % (sobra, lt[:240]))
    finally:
        if velho is None:
            os.environ.pop("RADAI_REGISTRO_DIR", None)
        else:
            os.environ["RADAI_REGISTRO_DIR"] = velho
        _soltar_logs()
        shutil.rmtree(base, ignore_errors=True)


def teste_o_arranque_escreve_a_suavizacao_e_o_registro():
    secao(u"o arranque escreve a suavizacao, a procedencia e o registro")
    RA = _app_import("radai_arranque")
    try:
        import engine as _E
    except Exception as e:
        checar(u"o motor importa neste runtime (pre-condicao)", False,
               u"%s: %s" % (type(e).__name__, e))
        return
    nomes = [p[0] for p in RA.PASSOS]
    checar(u"o passo esta na sequencia do arranque",
           any(p[1] is RA._p_procedencia for p in RA.PASSOS), nomes)
    pasta = tempfile.mkdtemp(prefix="radai_arranque_")
    reg = os.path.join(pasta, "reg")
    velho = os.environ.get("RADAI_REGISTRO_DIR")
    os.environ["RADAI_REGISTRO_DIR"] = reg
    try:
        os.makedirs(os.path.join(reg, "casos", "2026-09-20_ab12cd34"))
        ctx, linhas = _ctx_do_arranque(
            pasta, engine=_E,
            passos=((u"suavizacao, procedencia e registro de casos",
                     RA._p_procedencia, 60),))
        ctx["suavizar_mm"] = 0.5
        ctx["suavizar_fabrica"] = "1.0"
        rel = RA.executar(ctx)
        texto = u"\n".join(linhas)
        checar(u"o passo terminou", all(p.get("ok") for p in rel["passos"]),
               rel["passos"])
        checar(u"  com o cursor que o vigia entregou (0.5), e o de fabrica",
               u"suavizacao: cursor 0.5" in texto and u"fabrica 1.0" in texto,
               [l for l in linhas if u"cursor" in l][:1])
        checar(u"  e a procedencia (quantas estruturas, de onde vem)",
               u"procedencia:" in texto and u"estruturas | modelo" in texto)
        checar(u"  e o registro de casos (quantos, e a pasta)",
               u"registro de casos: 1 caso(s)" in texto, texto[-300:])
        checar(u"o log e ASCII", all(ord(c) < 128 for c in texto),
               [l for l in linhas if any(ord(c) > 127 for c in l)][:1])
        arq = RA.gravar(rel, pasta)
        conteudo = io.open(arq, encoding="utf-8").read()
        bl = conteudo[conteudo.index(RA.INICIO_BLOCO):]
        checar(u"  e o bloco gravado as traz (o arquivo que se cola num chat)",
               u"Suavizacao, procedencia e registro de casos:" in bl
               and u"suavizacao: cursor 0.5" in bl
               and u"registro de casos: 1 caso(s)" in bl, bl[:400])
        checar(u"  e sem caminho de paciente (so a pasta do registro)",
               u"Patients" not in bl and u"SILVA" not in bl)
        ctx2, linhas2 = _ctx_do_arranque(
            pasta, engine=_E,
            passos=((u"procedencia", RA._p_procedencia, 60),))
        RA.executar(ctx2)
        checar(u"sem o cursor no ctx, o log diz que nao sabe o em uso",
               any(u"nao sei o cursor em uso" in l for l in linhas2), linhas2[:4])
    finally:
        if velho is None:
            os.environ.pop("RADAI_REGISTRO_DIR", None)
        else:
            os.environ["RADAI_REGISTRO_DIR"] = velho
        shutil.rmtree(pasta, ignore_errors=True)


class _PedidoFalso(object):

    def __init__(self, corpo):
        self.corpo = corpo

    async def json(self):
        return self.corpo


def teste_o_caso_nao_leva_o_paciente_de_outra_serie():
    secao(u"o caso so guarda o que a serie disse")
    import asyncio
    import threading
    RT = _app_import("radai_tasks")
    agora = datetime.now()
    mod, root, base = montar([("PAC_CASO_A", agora - timedelta(days=1), 8),
                              ("PAC_OUTRO_B", agora - timedelta(days=2), 8)],
                             extra={"DRY_RUN": "0"})
    envelhecer(root, 60)
    fila, _ = fila_de(mod)
    if not checar(u"as duas séries entraram na fila", len(fila) == 2,
                  [q.get("pid") for q in fila]):
        return
    s = next(q for q in fila if q["pid"] == "PAC_CASO_A")
    outra = next(q for q in fila if q["pid"] == "PAC_OUTRO_B")
    pasta_reg = tempfile.mkdtemp(prefix="radai_caso_vigia_")
    velho = os.environ.get("RADAI_REGISTRO_DIR")
    os.environ["RADAI_REGISTRO_DIR"] = pasta_reg
    clique = {}

    def _clicar_na_tela_do_plano():
        try:
            clique["r"] = asyncio.run(mod.api_decidir(_PedidoFalso(
                {"pasta": outra["dir"], "uid": outra["uid"],
                 "pid": outra["pid"], "decisao": "pular"})))
        except Exception as e:
            clique["erro"] = "%s: %s" % (type(e).__name__, e)

    class _MotorComVizinho(_MotorQueRegistra):
        def copy_sorted(self, arquivos, destino):
            t = threading.Thread(target=_clicar_na_tela_do_plano)
            t.start()
            t.join(20)
            mod.wlog("   (bateria) linha da serie citando %s ...%s"
                     % (outra["pid"], outra["uid"][-8:]))
            time.sleep(self.espera)

    motor = _MotorComVizinho(
        "parou de proposito na bateria", log_do_job=["[02:00:01] TS total"],
        espera=0.8,
        drenado=["(bateria) linha do DRENADOR do motor"])
    mod.carregar_engine = lambda: motor
    try:
        with _SemTasksDaSerie(RT):
            mod.claim(s["dir"], s["uid"], {})
            mod.HEARTBEAT_S = 0.1
            mod.renovar_lock = lambda sdir, uid, extra=None: False
            mod.process_series(s)
        checar(u"a rota da tela do plano rodou durante a série",
               (clique.get("r") or {}).get("ok") is True, clique)
        checar(u"  e escreveu a linha dela no log da ESTAÇÃO",
               any("-> pular" in l for l in mod.LOGBUF))
        casos = _casos_em(pasta_reg)
        if not checar(u"o caso foi gravado", len(casos) == 1, casos):
            return
        textos = {}
        for nome in ("caso.json", "caso.md", "log.txt"):
            p = os.path.join(casos[0], nome)
            textos[nome] = (io.open(p, encoding="utf-8").read()
                            if os.path.isfile(p) else "")
        log = textos["log.txt"]
        checar(u"a linha da rota, de OUTRA thread, não entra no log.txt do caso",
               "-> pular" not in log and "fila:" not in log,
               [l for l in log.splitlines() if "pular" in l or "fila:" in l][:2])
        for nome, tx in sorted(textos.items()):
            vaz = [x for x in (outra["pid"], outra["uid"], outra["uid"][-8:])
                   if x in tx]
            checar(u"  %s sem o PatientID nem o UID da OUTRA série" % nome,
                   not vaz, vaz)
        checar(u"a linha da série que cita o outro paciente chega TROCADA "
               u"(o segundo cinto)",
               "(bateria) linha da serie citando <paciente> ...<paciente>" in log,
               [l for l in log.splitlines() if "citando" in l][:1])
        checar(u"o que o DRENADOR do motor disse (outra thread, DA série) "
               u"continua no caso", "linha do DRENADOR do motor" in log)
        checar(u"o que o BATIMENTO disse (outra thread, DA série) continua "
               u"no caso", "NAO consigo gravar o sinal de vida" in log,
               [l for l in mod.LOGBUF if "sinal de vida" in l][:1])
        checar(u"e o gancho desligou no fim da série",
               mod._COLETOR_DA_SERIE[0] is None)

        mod3, root3, base3 = montar(
            [("PAC_FILA_C", agora - timedelta(days=1), 8),
             ("PAC_FILA_D", agora - timedelta(days=3), 8)])
        envelhecer(root3, 60)
        mod3.claim = lambda *a, **k: False
        estado = {"fila": None, "proxima_varredura": 0.0, "turno": True}
        mod3._uma_volta(estado)
        guardados = mod3._de_outras()
        checar(u"a varredura guarda o PatientID e o ...uid8 da cabeça da fila",
               "PAC_FILA_C" in guardados and "PAC_FILA_D" in guardados
               and any(len(v) == 8 and v not in ("PAC_FILA_C", "PAC_FILA_D")
                       for v in guardados), guardados)
        mod3._lembrar_de_outras("P%05d" % i for i in range(mod3.TETO_DE_OUTRAS + 50))
        todos = mod3._de_outras()
        checar(u"  e tem teto (%d), com os mais recentes"
               % mod3.TETO_DE_OUTRAS,
               len(todos) == mod3.TETO_DE_OUTRAS
               and todos[-1] == "P%05d" % (mod3.TETO_DE_OUTRAS + 49), len(todos))
    finally:
        if velho is None:
            os.environ.pop("RADAI_REGISTRO_DIR", None)
        else:
            os.environ["RADAI_REGISTRO_DIR"] = velho
        _soltar_logs()
        shutil.rmtree(pasta_reg, ignore_errors=True)


def teste_a_bateria_nao_deixa_pasta_para_tras():
    secao(u"a bateria nao deixa pasta para tras")
    base = tempfile.mkdtemp(prefix="radai_caso_vigia_")
    mod = carregar(os.path.join(base, "root"), base)
    mod.wlog("linha que abre o radai_vigia.log desta instancia")
    checar(u"o log da instância está aberto (senão isto não mede nada)",
           getattr(mod, "_LOG_FH", None) is not None)
    repo_tmp = os.path.normcase(os.path.join(os.path.dirname(APP), "tmp"))
    tmp_mod = os.path.normcase(str(mod._TMP_LOCAL))
    checar(u"a temporária do vigia carregado é a da bateria, e não "
           u"`<repositório>\\tmp` (que sincroniza)",
           tmp_mod.startswith(os.path.normcase(_TMP_BATERIA))
           and not tmp_mod.startswith(repo_tmp), mod._TMP_LOCAL)
    checar(u"  e o `tempfile` do processo também",
           os.path.normcase(tempfile.gettempdir()).startswith(
               os.path.normcase(_TMP_BATERIA)), tempfile.gettempdir())
    _soltar_logs()
    shutil.rmtree(base, ignore_errors=True)
    checar(u"soltar o log e apagar: a pasta do teste SAI do disco",
           not os.path.exists(base),
           os.listdir(base) if os.path.exists(base) else "")


def teste_o_registro_do_caso_nunca_levanta():
    secao(u"o registro do caso nunca derruba a serie")
    RG = _app_import("radai_records")
    base = tempfile.mkdtemp(prefix="radai_caso_vigia_")
    velho = os.environ.get("RADAI_REGISTRO_DIR")
    os.environ["RADAI_REGISTRO_DIR"] = os.path.join(base, "reg")
    velha_medida = RG.medir_serie

    def _quebrada(*a, **k):
        raise ValueError("medida quebrada de proposito")

    try:
        mod = carregar(os.path.join(base, "root"), base, extra={"DRY_RUN": "0"})
        s = {"uid": "1.9.999.2.55.3.11111.87654321", "pid": "FANTOMA-QUEBRA",
             "dir": os.path.join(base, "root", "FANTOMA_Q", "CT"),
             "modality": "CT", "count": 5}
        RG.medir_serie = _quebrada
        levantou, r = None, None
        try:
            r = mod._registrar_caso_do_vigia(
                s, time.time() - 1.0, {"ok": True, "tasks_ok": ["total_v3"]}, None)
        except Exception as e:
            levantou = "%s: %s" % (type(e).__name__, e)
        checar(u"a medida que levanta NÃO sobe", levantou is None and r == "",
               levantou or r)
        checar(u"  e o log diz por quê",
               any("nao consegui montar o caso" in l
                   and "medida quebrada de proposito" in l for l in mod.LOGBUF),
               [l for l in mod.LOGBUF if "registro" in l][-2:])
    finally:
        RG.medir_serie = velha_medida
        if velho is None:
            os.environ.pop("RADAI_REGISTRO_DIR", None)
        else:
            os.environ["RADAI_REGISTRO_DIR"] = velho
        _soltar_logs()
        shutil.rmtree(base, ignore_errors=True)


_TABELA_SMI = u"""\
+---------------------------------------------------------------------------------------+
| NVIDIA-SMI 528.86                 Driver Version: 528.86       CUDA Version: 12.0     |
|-----------------------------------------+----------------------+----------------------+
| Processes:                                                                            |
|  GPU   GI   CI        PID   Type   Process name                            GPU Memory |
|        ID   ID                                                             Usage      |
|=======================================================================================|
|    0   N/A  N/A      4120    C+G   ...crosoft\\Edge\\Application\\msedge.exe    N/A      |
|    0   N/A  N/A      5230    C+G   ...Local\\Microsoft\\Teams\\current\\Teams.exe N/A  |
|    0   N/A  N/A      6001      G   C:\\Program Files\\Varian\\Eclipse.exe          N/A      |
|    0   N/A  N/A      7777      C   ...LOCAL_SUITE\\python\\python.exe           N/A      |
+---------------------------------------------------------------------------------------+
"""


class _Engine(object):

    def __init__(self, com_plano=True):
        self.chamadas = []
        if com_plano:
            self.plano_de_dispositivo = self._plano

    def _plano(self, forma, esp, task="total_v3", inv=None):
        self.chamadas.append((tuple(forma), task))
        return {"modo": "gpu_resultado_na_cpu",
                "motivo": "livre 2048 MiB >= rede 900 + margem 768",
                "vram_livre_mb": 2048, "vram_total_mb": 5120,
                "placa": "Quadro P2200", "indice": 0}

    def estatistica_do_ts(self, desligar=False, amb=None, pasta=None):
        return {"arquivo": "X:\\home\\.totalsegmentator\\config.json",
                "existia": True, "valor": False, "gravou": False,
                "criou": False, "erro": ""}

    def envelope_bloqueia_estatistica(self):
        return True, ""


def _ctx_do_arranque(pasta, root="", engine=None, limites=None, passos=None):
    linhas = []
    ctx = {"log": linhas.append, "bater": lambda: None, "appver": "7.9",
           "maquina": "PC_ARRANQUE", "python_exe": sys.executable,
           "device": "auto", "tasks": ["total_v3"], "modalidades": ["CT"],
           "root": root, "pasta_trabalho": pasta, "pasta_temp": pasta,
           "dry_run": True, "incluir": {"INCLUIR_HNLNL": True},
           "carregar_engine": (lambda: engine) if engine is not None
           else (lambda: (_ for _ in ()).throw(RuntimeError("sem motor"))),
           "conferir_ambiente": lambda: (True, "simulacao: nada e chamado"),
           "avisos_previos": ["versao: aviso de teste"]}
    if limites:
        ctx["limites"] = limites
    if passos:
        ctx["passos"] = passos
    return ctx, linhas


class _Dublagem(object):

    def __init__(self, RA, **troca):
        self.RA, self.troca, self.velhas = RA, troca, {}

    def __enter__(self):
        for k, v in self.troca.items():
            self.velhas[k] = getattr(self.RA, k)
            setattr(self.RA, k, v)
        return self

    def __exit__(self, *a):
        for k, v in self.velhas.items():
            setattr(self.RA, k, v)
        return False


class _versoes_no_ambiente(object):

    def __init__(self, valor):
        self.valor, self.velho = valor, None

    def __enter__(self):
        self.velho = os.environ.get("RADAI_URL_VERSOES")
        if self.valor is None:
            os.environ.pop("RADAI_URL_VERSOES", None)
        else:
            os.environ["RADAI_URL_VERSOES"] = self.valor
        return self

    def __exit__(self, *a):
        if self.velho is None:
            os.environ.pop("RADAI_URL_VERSOES", None)
        else:
            os.environ["RADAI_URL_VERSOES"] = self.velho
        return False


def _medidas_dubladas(RA):
    return _Dublagem(
        RA,
        placas=lambda timeout=20: {
            "placas": [{"indice": 0, "nome": "Quadro P2200", "total_mb": 5120.0,
                        "livre_mb": 2048.0, "usada_mb": 3072.0,
                        "driver": "528.86", "cap": "6.1"}],
            "driver": "528.86", "falha": ""},
        processos_na_placa=lambda timeout=20: {
            "processos": RA._processos_da_tabela(_TABELA_SMI), "falha": ""},
        sondar_torch=lambda python_exe=None, timeout=120: {
            "importa": True, "versao": "2.5.1+cu121", "cuda": "12.1",
            "disponivel": True, "n": 1,
            "placas": [{"nome": "Quadro P2200", "cap": "6.1", "total_mb": 5120}],
            "arch": ["sm_50", "sm_60", "sm_61", "sm_70", "sm_86"]})


def _checar_bloco_sem_nome_e_com_rede(RA, texto, bl, ctx):
    import platform
    RR = _app_import("radai_records")
    if not checar(u"  o registro tem a conta do pseudônimo da máquina",
                  hasattr(RR, "pseudonimo_da_maquina")):
        return
    pseudo = RR.pseudonimo_da_maquina()
    cru = os.environ.get("COMPUTERNAME") or platform.node()
    antes = texto[:texto.index(RA.INICIO_BLOCO)]
    checar(u"  o bloco traz a máquina pelo PSEUDÔNIMO do registro de casos",
           (u"Maquina: %s (pseudonimo" % pseudo) in bl,
           [l for l in bl.splitlines() if l.startswith("Maquina:")][:1])
    checar(u"  e NÃO o nome: nem o do vigia, nem o do Windows",
           "PC_ARRANQUE" not in bl and (not cru or cru not in bl),
           [l for l in bl.splitlines() if "PC_ARRANQUE" in l or (cru and cru in l)][:2])
    checar(u"  o log da estação continua com o nome, e o pseudônimo ao lado",
           "maquina PC_ARRANQUE (no bloco: %s)" % pseudo in antes,
           [l for l in antes.splitlines() if "maquina" in l][:1])
    so_nome = RA.bloco({"dados": {"estacao": {"maquina": "PC-MARIA"}},
                        "maquina": "PC-MARIA", "avisos": [], "pendencias": [],
                        "passos": []})
    checar(u"  sem pseudônimo, o bloco OMITE o nome (isca: nome no rel)",
           not any("PC-MARIA" in l for l in so_nome)
           and any(l.startswith("Maquina: nome omitido") for l in so_nome),
           [l for l in so_nome if l.startswith("Maquina:")])
    rel_u = {"dados": {"python": {"versao": "3.10.11", "embeddable": True,
                                  "executavel": "C:\\Users\\usuario fantoma\\AppData"
                                                "\\Local\\RADAI\\python\\python.exe"}},
             "avisos": ["nao achei C:\\Users\\usuario fantoma\\Desktop\\x.json"],
             "pendencias": [], "passos": []}
    blu = u"\n".join(RA.bloco(rel_u))
    checar(u"  caminho em \\Users\\<nome>\\ sai com <usuario> no bloco",
           "usuario fantoma" not in blu
           and "C:\\Users\\<usuario>\\AppData\\Local\\RADAI" in blu
           and "C:\\Users\\<usuario>\\Desktop\\x.json" in blu,
           [l for l in blu.splitlines() if "Users" in l][:2])
    if checar(u"  o filtro de usuário do bloco existe (`_sem_usuario`)",
              hasattr(RA, "_sem_usuario")):
        with _Dublagem(RA, _sem_usuario=lambda l: l):
            blu_isca = u"\n".join(RA.bloco(rel_u))
        checar(u"  isca: sem o filtro, o nome sai (a checagem discrimina)",
               "usuario fantoma" in blu_isca)
    checar(u"o bloco DECLARA a rede por omissão",
           "Rede por omissao (o que a estacao faz sozinha" in bl, bl[:200])
    checar(u"  a consulta de versão: destino da API, quando, e o que leva",
           "consulta de versao: GET https://api.github.com/repos/radioterapia-ai/"
           "local-suite/releases/latest | quando: uma vez, no arranque" in bl
           and "so o User-Agent 'radioterapia-ai-local-suite' - sem corpo" in bl,
           [l for l in bl.splitlines() if "consulta de versao" in l][:1])
    checar(u"  o teste de internet do registro: destinos, porta e frequência",
           "teste de internet do registro de casos: DNS + TCP 443 a pypi.org e "
           "github.com | quando: no maximo a cada 30 min" in bl
           and "sem enviar dado" in bl,
           [l for l in bl.splitlines() if "teste de internet" in l][:1])
    if not checar(u"  a declaração é uma função (`chamadas_de_rede`)",
                  hasattr(RA, "chamadas_de_rede")
                  and hasattr(RR, "INTERNET_HOSTS")):
        return
    velhos = RR.INTERNET_HOSTS
    RR.INTERNET_HOSTS = ("isca.invalid",)
    try:
        isca = RA.chamadas_de_rede(ctx)
    finally:
        RR.INTERNET_HOSTS = velhos
    checar(u"  isca: os destinos vêm do MÓDULO que chama, e não de cópia",
           any("a isca.invalid |" in l for l in isca), isca)
    with _versoes_no_ambiente("0"):
        sem = RA.chamadas_de_rede(ctx)
    checar(u"  RADAI_URL_VERSOES=0: a consulta aparece DESLIGADA, e diz como",
           any("consulta de versao: DESLIGADA nesta estacao "
               "(RADAI_URL_VERSOES=0" in l for l in sem)
           and not any("URL_VERSOES vazio" in l for l in sem), sem)
    RV = _app_import("radai_version")
    with _versoes_no_ambiente(None):
        de_contexto = RA.chamadas_de_rede(dict(ctx, url_versoes=""))
        velha = RV.URL_VERSOES
        RV.URL_VERSOES = u"https://github.com/isca-dono/isca-repo/releases"
        try:
            trocada = RA.chamadas_de_rede(ctx)
        finally:
            RV.URL_VERSOES = velha
    checar(u"  isca: o contexto não desliga a consulta (ele não é mais lido)",
           any("consulta de versao: GET https://api.github.com/" in l
               for l in de_contexto), de_contexto)
    checar(u"  isca: a constante trocada em `radai_version` muda o destino",
           any("GET https://api.github.com/repos/isca-dono/isca-repo/"
               in l for l in trocada), trocada)


def teste_o_arranque_se_explica():
    secao(u"o arranque se explica, passo a passo")
    RA = _app_import("radai_arranque")
    pasta = tempfile.mkdtemp(prefix="radai_arranque_")
    try:
        root = os.path.join(pasta, "share")
        os.makedirs(os.path.join(root, "ISCA_FANTOMA_DA_PASTA", "CT"))
        eng = _Engine()
        ctx, linhas = _ctx_do_arranque(pasta, root=root, engine=eng)
        with _medidas_dubladas(RA), _versoes_no_ambiente(None):
            rel = RA.executar(ctx)
        n = len(RA.PASSOS)
        for k, (nome, _f, _l) in enumerate(RA.PASSOS, start=1):
            checar(u"passo %d/%d (%s) anunciado" % (k, n, nome),
                   any(l.startswith("arranque [%d/%d]" % (k, n)) for l in linhas))
        checar(u"cada passo diz o TEMPO que levou",
               sum(1 for l in linhas if l.lstrip().startswith("(")
                   and " s) " in l) == n,
               [l for l in linhas if " s) " in l][:3])
        checar(u"todos os passos terminaram (as medidas estão dubladas)",
               all(p.get("ok") for p in rel["passos"]),
               [p for p in rel["passos"] if not p.get("ok")][:2])
        checar(u"o log é ASCII (o console da estação é cp850)",
               all(all(ord(c) < 128 for c in l) for l in linhas),
               [l for l in linhas if any(ord(c) > 127 for c in l)][:1])
        texto = "\n".join(linhas)
        checar(u"a placa sai com nome, VRAM livre, driver e sm",
               "Quadro P2200" in texto and "2048 livres" in texto
               and "driver 528.86" in texto and "sm 6.1" in texto)
        checar(u"quem segura a placa é NOMEADO",
               "msedge.exe" in texto and "Teams.exe" in texto)
        checar(u"  e o N/A do WDDM é dito com todas as letras",
               "WDDM" in texto and "NAO informa" in texto)
        proc = next((l for l in linhas if "Fechar e decisao" in l), "")
        checar(u"  o Eclipse aparece como protegido, e NÃO entre os fecháveis",
               "Eclipse.exe" in texto and "protegido" in texto
               and "Eclipse" not in proc and "msedge.exe" in proc, proc[:140])
        checar(u"  um python.exe na placa vira aviso (TotalSegmentator órfão?)",
               any("python.exe segura a placa" in a for a in rel["avisos"]))
        checar(u"o driver é conferido contra o cuda do torch",
               "528.86 >= 525" in texto)
        checar(u"a decisão pergunta ao motor as DUAS séries-tipo",
               [c[0] for c in eng.chamadas] == [(117, 512, 512), (409, 512, 512)],
               eng.chamadas)
        checar(u"  com a base eleita pelo disco",
               all(c[1] in ("total_v3", "total_v2") for c in eng.chamadas),
               eng.chamadas)
        checar(u"  e o log diz o modo E o motivo",
               "-> gpu_resultado_na_cpu: livre 2048 MiB" in texto)
        checar(u"o arranque diz que a estatistica de uso do TotalSegmentator "
               u"esta desligada, e onde",
               "estatistica de uso do TotalSegmentator: desligada (nenhuma "
               "chamada de rede)" in texto and "send_usage_stats=false" in texto,
               [l for l in linhas if "estatistica" in l][:2])
        checar(u"  e o bloco diz o estado dela",
               "Estatistica de uso do TotalSegmentator: desligada no arquivo "
               "| envelope bloqueia o envio" in texto)
        checar(u"  e a decisão fica guardada para o turno",
               (rel["dados"].get("dispositivo") or {}).get("modo")
               == "gpu_resultado_na_cpu")
        checar(u"o bloco tem começo e fim delimitados",
               RA.INICIO_BLOCO in texto and RA.FIM_BLOCO in texto
               and texto.index(RA.INICIO_BLOCO) < texto.index(RA.FIM_BLOCO))
        checar(u"  e diz para colar num chat de IA",
               "cole este bloco num chat de IA para diagnostico" in texto)
        bl = texto[texto.index(RA.INICIO_BLOCO):]
        _checar_bloco_sem_nome_e_com_rede(RA, texto, bl, ctx)
        for rotulo, trecho in ((u"o que o app é", "SUGESTAO NAO APROVADA"),
                               (u"as versões", "Versoes:"),
                               (u"as decisões", "Decisoes:"),
                               (u"os avisos prévios", "versao: aviso de teste"),
                               (u"os tempos", "Tempos:")):
            checar(u"  o bloco traz %s" % rotulo, trecho in bl, trecho)
        arq = RA.gravar(rel, pasta)
        nome = os.path.basename(arq)
        checar(u"o bloco vai para arranque_<AAAAMMDD_HHMMSS>.txt",
               re.match(r"^arranque_\d{8}_\d{6}\.txt$", nome) is not None, nome)
        conteudo = io.open(arq, encoding="utf-8").read()
        checar(u"  o arquivo tem o bloco inteiro",
               RA.INICIO_BLOCO in conteudo and RA.FIM_BLOCO in conteudo)
        checar(u"  e NÃO tem o ROOT nem o nome da pasta do paciente",
               root not in conteudo and "ISCA_FANTOMA" not in conteudo
               and root not in texto and "ISCA_FANTOMA" not in texto)
        checar(u"  mas diz que o ROOT está acessível e quantas pastas tem",
               "acessivel, 1 pasta(s)" in conteudo, conteudo[-400:])
    finally:
        shutil.rmtree(pasta, ignore_errors=True)


def teste_o_arranque_diz_o_que_nao_mediu():
    secao(u"o arranque diz o que nao mediu, e nao trava")
    RA = _app_import("radai_arranque")
    pasta = tempfile.mkdtemp(prefix="radai_arranque_")
    try:
        def _quebra(ctx, rel):
            raise RuntimeError("sonda quebrada de proposito")

        def _pendura(ctx, rel):
            time.sleep(4.0)
            return ["nao devia aparecer"]

        def _depois(ctx, rel):
            return ["o passo seguinte rodou"]

        ctx, linhas = _ctx_do_arranque(
            pasta, passos=((u"quebra", _quebra, 5), (u"pendura", _pendura, 5),
                           (u"depois", _depois, 5)),
            limites={u"pendura": 0.6})
        t0 = time.time()
        rel = RA.executar(ctx)
        dt = time.time() - t0
        texto = "\n".join(linhas)
        checar(u"a exceção vira «nao consegui medir X: motivo»",
               "nao consegui medir quebra: RuntimeError: sonda quebrada" in texto)
        checar(u"o passo que pendura estoura o PRAZO, e é dito",
               "nao consegui medir pendura: tempo-limite de 1 s estourado" in texto,
               [l for l in linhas if "pendura" in l])
        checar(u"  e o arranque NÃO espera ele (%.1f s < 3 s)" % dt, dt < 3.0,
               "%.1f s" % dt)
        checar(u"  e o passo seguinte roda", "o passo seguinte rodou" in texto)
        checar(u"os tempos do bloco marcam o que ficou SEM MEDIDA",
               "quebra" in texto and "(SEM MEDIDA)" in texto)
        ctx2, linhas2 = _ctx_do_arranque(pasta, engine=_Engine(com_plano=False),
                                         passos=((u"versoes", RA._p_versoes, 30),
                                                 (u"placas", RA._p_placas, 30),
                                                 (u"torch", RA._p_torch, 30),
                                                 (u"decisao", RA._p_decisao, 30)))
        with _medidas_dubladas(RA):
            RA.executar(ctx2)
        checar(u"sem `plano_de_dispositivo`, a linha diz que não conseguiu o "
               u"plano, com o erro, e segue",
               any(u"nao consegui o plano do motor (AttributeError" in l
                   for l in linhas2),
               u" | ".join(l for l in linhas2 if u"plano" in l)[:240])
        checar(u"driver 472.98 contra cu121: NÃO alcança (o caso medido)",
               RA.driver_contra_cuda("472.98", "12.1")[0] is False)
        checar(u"driver 528.86 contra cu121: ok",
               RA.driver_contra_cuda("528.86", "12.1")[0] is True)
        checar(u"sem placa: não se aplica (None, e não False)",
               RA.driver_contra_cuda("", "12.1")[0] is None)
        checar(u"cuda sem piso declarado: diz que não há piso, sem inventar",
               RA.driver_contra_cuda("450.0", "11.8")[0] is None)
        ps = RA._processos_da_tabela(_TABELA_SMI)
        checar(u"a tabela do nvidia-smi vira 4 processos, pelo nome do exe",
               [p["nome"] for p in ps] == ["msedge.exe", "Teams.exe",
                                           "Eclipse.exe", "python.exe"],
               [p["nome"] for p in ps])
        checar(u"  e a memória N/A vira None, e não zero",
               all(p["mem_mb"] is None for p in ps))
        respostas = [
            {"codigo": 6, "saida": "", "erro": "Field \"compute_cap\" is not a valid field",
             "falha": ""},
            {"codigo": 0, "saida": "0, Quadro P2000, 5120, 4000, 1120, 472.98\n",
             "erro": "", "falha": ""}]
        with _Dublagem(RA, _rodar=lambda args, timeout: respostas.pop(0),
                       caminho_do_nvidia_smi=lambda: "nvidia-smi"):
            r = RA.placas()
        checar(u"nvidia-smi sem `compute_cap`: pergunta de novo e acha a placa",
               [p["nome"] for p in r["placas"]] == ["Quadro P2000"]
               and r["driver"] == "472.98", r)
        with _Dublagem(RA, _rodar=lambda args, timeout: {
                "codigo": None, "saida": "", "erro": "", "falha": "nao encontrado"},
                caminho_do_nvidia_smi=lambda: "nvidia-smi"):
            r = RA.placas()
        checar(u"sem nvidia-smi: a lista vazia vem COM o motivo",
               r["placas"] == [] and "nao encontrado" in r["falha"], r)
        with _Dublagem(RA, _rodar=lambda args, timeout: {
                "codigo": 0, "erro": "", "falha": "",
                "saida": "0, NVIDIA RTX A2000, 12GB, 12282, 9000, 3282, 536.25, 8.6\n"},
                caminho_do_nvidia_smi=lambda: "nvidia-smi"):
            r = RA.placas()
        p = (r["placas"] or [{}])[0]
        checar(u"placa com vírgula no nome: nome inteiro, e os números no lugar",
               p.get("nome") == "NVIDIA RTX A2000, 12GB"
               and p.get("total_mb") == 12282 and p.get("livre_mb") == 9000
               and p.get("usada_mb") == 3282 and p.get("driver") == "536.25"
               and p.get("cap") == "8.6", p)
        rel = {"dados": {}, "avisos": [], "pendencias": []}
        L = RA._p_python({"python_exe": os.path.join(pasta, "nao_existe",
                                                     "python.exe")}, rel)
        checar(u"pasta do Python ilegível: «não consegui ler», e não "
               u"«instalação comum»",
               "nao consegui ler a pasta do Python" in L[0]
               and "instalacao comum" not in L[0]
               and rel["dados"]["python"]["embeddable"] is None, L)
        checar(u"  e o bloco não diz «comum» sobre o que não leu",
               "comum" not in [l for l in RA.bloco(rel) if l.startswith("Python:")][0],
               [l for l in RA.bloco(rel) if l.startswith("Python:")])
        import importlib.metadata as _md
        velha_versao = _md.version

        def _versao(dist):
            if dist == "numpy":
                raise _md.PackageNotFoundError(dist)
            if dist == "pydicom":
                raise RuntimeError("metadado corrompido de proposito")
            return "1.0"

        _md.version = _versao
        try:
            v = RA.versoes_instaladas()
        finally:
            _md.version = velha_versao
        checar(u"biblioteca sem metadado: AUSENTE (None)", v.get("numpy") is None, v)
        checar(u"  metadado que não se lê: «nao consegui ler», e não AUSENTE",
               str(v.get("pydicom") or "").startswith("? (nao consegui ler: RuntimeError"),
               v.get("pydicom"))
        RC = _app_import("radai_cleaner")
        velha_conta = RC.disco_necessario_gb

        def _conta_quebrada(*a, **k):
            raise ValueError("conta quebrada de proposito")

        RC.disco_necessario_gb = _conta_quebrada
        try:
            L = RA._p_disco({"pasta_trabalho": pasta, "pasta_temp": pasta,
                             "tasks": ["total_v3"]},
                            {"dados": {}, "avisos": [], "pendencias": []})
        finally:
            RC.disco_necessario_gb = velha_conta
        checar(u"sem a conta de disco, o log diz que o aviso de disco curto "
               u"está desligado",
               any("nao sei quanto disco uma serie pede (ValueError)" in l
                   for l in L), L)
        _rt = sys.modules.get("radai_tasks")
        sys.modules["radai_tasks"] = None
        try:
            rel = {"dados": {"torch": {"importa": True, "disponivel": False}},
                   "avisos": [], "pendencias": []}
            L = RA._p_decisao({"device": "auto", "tasks": ["total_v3"],
                               "modalidades": ["CT"]}, rel)
        finally:
            if _rt is not None:
                sys.modules["radai_tasks"] = _rt
            else:
                sys.modules.pop("radai_tasks", None)
        checar(u"radai_tasks que não carrega: dito, e não «indisponível nesta "
               u"versão»",
               any("nao consegui carregar o radai_tasks: " in l for l in L)
               and not any("indisponivel nesta versao)" in l for l in L), L)
    finally:
        shutil.rmtree(pasta, ignore_errors=True)


def teste_a_fila_espera_o_arranque():
    secao(u"a fila so comeca depois do relatorio de arranque")
    import threading
    base = tempfile.mkdtemp(prefix="radai_arranque_")
    try:
        mod = carregar(os.path.join(base, "root"), base, extra={})
        checar(u"a consulta de versao da bateria esta DESLIGADA "
               u"(RADAI_URL_VERSOES=0)", mod.URL_VERSOES == "",
               mod.URL_VERSOES)
        solta, voltou, relatorio = (threading.Event(), threading.Event(),
                                    threading.Event())
        voltas = []

        def _relatorio(avisos=()):
            relatorio.set()
            solta.wait(10)
            return True, ""

        def _volta(estado):
            voltas.append(time.time())
            voltou.set()
            raise SystemExit(0)

        mod._relatorio_de_arranque = _relatorio
        mod._uma_volta = _volta
        th = threading.Thread(target=mod.worker_loop, daemon=True)
        th.start()
        checar(u"o relatório começou", relatorio.wait(20))
        time.sleep(0.8)
        checar(u"  e ENQUANTO ele roda, nenhuma volta da fila", not voltas)
        solta.set()
        checar(u"quando ele termina, a fila começa", voltou.wait(10))
        th.join(5)
    finally:
        _soltar_logs()
        shutil.rmtree(base, ignore_errors=True)


def teste_o_relatorio_de_arranque_do_vigia():
    secao(u"o relatorio de arranque do vigia")
    RA = _app_import("radai_arranque")
    base = tempfile.mkdtemp(prefix="radai_arranque_")
    try:
        mod = carregar(os.path.join(base, "root"), base)
        mod.carregar_engine = lambda: _Engine()
        with _medidas_dubladas(RA):
            ok, detalhe = mod._relatorio_de_arranque(["aviso previo"])
        checar(u"devolve o par do ambiente (DRY_RUN passa sem chamar a IA)",
               ok is True and "simulacao" in (detalhe or ""), str((ok, detalhe)))
        checar(u"o estado do arranque fica «pronto»",
               mod.STATE["arranque"]["estado"] == "pronto", mod.STATE["arranque"])
        arq = mod.STATE["arranque"].get("arquivo") or ""
        checar(u"  e aponta o arquivo do bloco, na pasta do log",
               arq.startswith("arranque_")
               and os.path.isfile(os.path.join(str(mod.LOG_DIR), arq)), arq)
        checar(u"a decisão do arranque fica para o turno",
               mod.STATE["dispositivo"].get("modo") == "gpu_resultado_na_cpu",
               mod.STATE["dispositivo"])
        checar(u"e o /api/status mostra o arranque",
               (mod.status().get("arranque") or {}).get("estado") == "pronto")
    finally:
        _soltar_logs()
        shutil.rmtree(base, ignore_errors=True)


def teste_a_tela_de_processamento_nao_abre_cuda_no_vigia():
    secao(u"a tela de processamento nao abre CUDA no vigia")
    import types
    RA = _app_import("radai_arranque")
    base = tempfile.mkdtemp(prefix="radai_arranque_")
    tocou = []

    class _CudaEspiao(object):
        def __getattr__(self, nome):
            tocou.append(nome)
            raise AssertionError("torch.cuda.%s no processo do vigia" % nome)

    espiao = types.ModuleType("torch")
    espiao.cuda = _CudaEspiao()
    espiao.version = types.SimpleNamespace(cuda="12.1")
    mod = carregar(os.path.join(base, "root"), base)
    velho = sys.modules.get("torch")
    sys.modules["torch"] = espiao
    try:
        RA.ULTIMO.pop("torch", None)
        with _medidas_dubladas(RA):
            d = mod.api_processamento()
        checar(u"nenhum `torch.cuda` foi tocado no processo do vigia",
               not tocou, tocou)
        g = d.get("gpu") or {}
        checar(u"a placa vem do nvidia-smi, com a VRAM LIVRE",
               g.get("nome") == "Quadro P2200" and g.get("memoria_gb") == 5.0
               and g.get("memoria_livre_gb") == 2.0, g)
        checar(u"  e o cuda do torch, perguntado no subprocesso",
               g.get("cuda") == "12.1", g)
        checar(u"`auto` resolve para gpu quando o torch alcança a placa",
               d.get("resolve_em") == "gpu", d.get("resolve_em"))
    finally:
        if velho is None:
            sys.modules.pop("torch", None)
        else:
            sys.modules["torch"] = velho
        RA.ULTIMO.pop("torch", None)
        _soltar_logs()
        shutil.rmtree(base, ignore_errors=True)


def teste_a_conferencia_da_estacao_nao_abre_cuda():
    secao(u"a conferencia da estacao nao abre CUDA, e lista o que existe")
    import types
    RA = _app_import("radai_arranque")
    CE = _app_import("radai_station_check")
    RM = _app_import("radai_models")
    tocou = []

    class _CudaEspiao(object):
        def __getattr__(self, nome):
            tocou.append(nome)
            raise AssertionError("torch.cuda.%s no processo do vigia" % nome)

    espiao = types.ModuleType("torch")
    espiao.cuda = _CudaEspiao()
    velho = sys.modules.get("torch")
    sys.modules["torch"] = espiao
    try:
        RA.ULTIMO.pop("torch", None)
        with _medidas_dubladas(RA):
            try:
                sec = CE._secao_gpu()
            except AssertionError as e:
                sec = {"titulo": "GPU", "itens": []}
                tocou.append("levantou: %s" % e)
    finally:
        if velho is None:
            sys.modules.pop("torch", None)
        else:
            sys.modules["torch"] = velho
        RA.ULTIMO.pop("torch", None)
    checar(u"nenhum `torch.cuda` tocado no processo", not tocou, tocou)
    nomes = dict((i["nome"], i["valor"]) for i in sec["itens"])
    checar(u"a placa vem do nvidia-smi",
           "Quadro P2200" in (nomes.get(u"Placa 0") or ""), nomes)
    checar(u"e o CUDA do torch vem da sonda", nomes.get(u"CUDA do torch") == "12.1",
           nomes)
    pesos = [i["nome"] for i in CE._secao_pesos()["itens"]]
    checar(u"a lista de pesos não anuncia licença que não existe",
           not any(u"não comercial" in n for n in pesos), pesos)
    checar(u"  nem o nnInteractive, que saiu do pacote",
           not any("nnInteractive" in n for n in pesos), pesos)
    checar(u"  e tem um item por modelo do registro (mais o TotalSegmentator)",
           len(pesos) == len(RM.MODELOS), "%s x %s" % (pesos, list(RM.MODELOS)))
    itens = CE._secao_pesos()["itens"]
    cads = next((i for i in itens if i["nome"] == u"CADS"), {})
    checar(u"  e procura o CADS na pasta de verdade (`cads_open`)",
           cads.get("ok") is True or "cads_open" in (cads.get("detalhe") or ""),
           cads)


def teste_a_secao_de_arquivos_nao_levanta():
    secao(u"a secao «Arquivos do programa» roda em toda estacao")
    CE = _app_import("radai_station_check")
    try:
        sec = CE._secao_estrutura()
        erro = None
    except Exception as e:
        sec, erro = {"itens": []}, u"%s: %s" % (type(e).__name__, e)
    checar(u"_secao_estrutura() não levanta", erro is None, erro)
    nomes = [i.get("nome") for i in sec.get("itens") or []]
    checar(u"  e o item de duas gerações leva o nome da NOVA "
           u"(launchers/start_watcher.cmd)",
           u"launchers/start_watcher.cmd" in nomes, nomes)
    checar(u"  e nenhum nome é tupla nem tem contrabarra",
           all(isinstance(n, type(u"")) and u"\\" not in n for n in nomes),
           nomes)


def teste_a_sonda_que_falhou_nao_segura_a_tela():
    secao(u"a sonda que falhou nao segura a tela")
    RA = _app_import("radai_arranque")
    CE = _app_import("radai_station_check")
    base = tempfile.mkdtemp(prefix="radai_arranque_")
    chamadas = []

    def _sonda_muda(python_exe=None, timeout=120):
        chamadas.append(timeout)
        return {"importa": False,
                "falha": u"a sonda nao respondeu em %d s" % timeout}

    velho = RA.ULTIMO.pop("torch", None)
    try:
        mod = carregar(os.path.join(base, "root"), base)
        sem_placa = lambda timeout=20: {"placas": [], "driver": "",
                                        "falha": "nvidia-smi nao encontrado"}
        with _Dublagem(RA, sondar_torch=_sonda_muda, placas=sem_placa):
            sec = CE._secao_gpu()
            item = (sec.get("itens") or [{}])[0]
            checar(u"sonda que não respondeu: «não consegui medir», e não "
                   u"«não importa»",
                   item.get("ok") is None and u"consegui medir" in item.get("valor", "")
                   and u"importa" not in item.get("valor", ""), item)
            checar(u"  e o motivo vai junto", u"nao respondeu" in item.get("detalhe", ""),
                   item)
            n1 = len(chamadas)
            CE._secao_gpu()
            mod.api_processamento()
            CE._secao_gpu()
            checar(u"a falha recente fica guardada: 4 aberturas, UMA sonda",
                   n1 == 1 and len(chamadas) == 1, chamadas)
            RA.ULTIMO["torch"]["ts"] = time.time() - RA.REPERGUNTAR_FALHA_S - 1
            mod.api_processamento()
            checar(u"  passado o intervalo, pergunta de novo (uma vez)",
                   len(chamadas) == 2, chamadas)
            RA.ULTIMO["torch"] = {"importa": True, "versao": "2.5.1+cu121",
                                  "cuda": "12.1", "disponivel": False, "n": 0,
                                  "ts": 0.0}
            CE._secao_gpu()
            mod.api_processamento()
            checar(u"a sonda que RESPONDEU vale até o programa reiniciar",
                   len(chamadas) == 2, chamadas)
        RA.ULTIMO["torch"] = {"importa": False, "erro": "ModuleNotFoundError: torch",
                              "ts": time.time()}
        item = (CE._secao_gpu().get("itens") or [{}])[0]
        checar(u"o torch que NÃO importa continua «não importa», grave",
               item.get("ok") is False and u"importa" in item.get("valor", ""), item)
    finally:
        RA.ULTIMO.pop("torch", None)
        if velho is not None:
            RA.ULTIMO["torch"] = velho
        _soltar_logs()
        shutil.rmtree(base, ignore_errors=True)


def teste_o_lancador_abre_a_porta_do_config():
    secao(u"o lancador abre a porta do config")
    import subprocess
    if os.name != "nt":
        checar(u"(fora do Windows o lançador .cmd não se aplica)", True)
        return
    lanc = _componentes.fonte("app/launchers/start_watcher.cmd")
    bruto = open(lanc, "rb").read()
    checar(u"o lançador continua em CRLF", bruto.count(b"\n") == bruto.count(b"\r\n"))
    t = bruto.decode("ascii", "replace")
    i = t.find('set "URL=http://127.0.0.1:8777/"')
    j = t.find('if defined PORTA set "URL=', i)
    j = t.find("\r\n", j) + 2 if 0 <= i < j else -1
    if not checar(u"achei o bloco da porta no lançador", 0 <= i < j):
        return
    bloco = t[i:j]
    checar(u"o navegador abre no endereço calculado, e não num literal",
           'call "%JANELA%" %URL%' in t
           and 'start "" /min cmd /c call "%JANELA%" %URL%' in t)
    checar(u"  e o .cmd nao e aberto por `start` direto (deixava um cmd /K "
           u"parado no prompt: a segunda janela preta)",
           'start "" /min "%JANELA%"' not in t)
    base = tempfile.mkdtemp(prefix="radai_arranque_")
    try:
        prog = base + os.sep
        cmd = os.path.join(base, "porta.cmd")
        with open(cmd, "wb") as f:
            f.write(("@echo off\r\nset \"PROG=%s\"\r\n" % prog).encode("mbcs")
                    + bloco.encode("ascii") + b"echo URL=%URL%\r\n")
        env = dict(os.environ)
        env.pop("RADAI_CONFIG", None)

        def _url(conteudo=None, env_extra=None, codificacao="utf-8"):
            cfg = os.path.join(base, "radai_watcher.config")
            if conteudo is None:
                if os.path.exists(cfg):
                    os.remove(cfg)
            else:
                with open(cfg, "w", encoding=codificacao) as f:
                    f.write(conteudo)
            e = dict(env, **(env_extra or {}))
            p = subprocess.run(["cmd", "/c", cmd], stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, env=e, timeout=30)
            s = p.stdout.decode("ascii", "replace")
            return (s.split("URL=")[-1].strip() if "URL=" in s else s.strip())

        checar(u"sem config: 8777", _url() == "http://127.0.0.1:8777/", _url())
        u = _url("# Porta do painel local\nROOT=\nPORT=8791 # painel\n")
        checar(u"PORT=8791 com comentário no fim: 8791",
               u == "http://127.0.0.1:8791/", u)
        u = _url("PORT = 8792\n")
        checar(u"PORT com espaço antes do igual: 8792",
               u == "http://127.0.0.1:8792/", u)
        u = _url("PORT=abc\n")
        checar(u"PORT que não é número: volta para 8777",
               u == "http://127.0.0.1:8777/", u)
        outro = os.path.join(base, "outro.config")
        with open(outro, "w", encoding="utf-8") as f:
            f.write("PORT=8796\n")
        u = _url("PORT=8791\n", {"RADAI_CONFIG": outro})
        checar(u"RADAI_CONFIG manda, como no Python",
               u == "http://127.0.0.1:8796/", u)
        RC = _app_import("radai_config")
        vig = carregar(os.path.join(base, "root_lanc"), base)
        for rotulo, conteudo, cod in (
                (u"PORT na primeira linha, com BOM", u"PORT=8793\nROOT=\n", "utf-8-sig"),
                (u"comentário #PORT antes do PORT", u"#PORT=1111\nPORT=8791\n", "utf-8"),
                (u"comentário # PORT depois do PORT", u"PORT=8791\n# PORT=1111\n", "utf-8"),
                (u"outra chave que termina em PORT", u"XPORT=9999\n", "utf-8"),
                (u"PORT recuado com espaço", u"  PORT=8794\n", "utf-8"),
                (u"dois PORT: o último manda", u"PORT=8791\nPORT=8795\n", "utf-8"),
                (u"o último PORT vazio: o padrão", u"PORT=8791\nPORT=\n", "utf-8")):
            u = _url(conteudo, codificacao=cod)
            py = vig._num(RC.ler_bruto(conteudo), "PORT", int, 1, 65535)
            checar(u"%s: o lançador abre a mesma porta que o Python (%d)"
                   % (rotulo, py), u == "http://127.0.0.1:%d/" % py, u)
    finally:
        _soltar_logs()
        shutil.rmtree(base, ignore_errors=True)


def teste_perguntar_se_o_pid_vive_nao_sinaliza_o_processo():
    import subprocess
    secao("perguntar se um PID vive nao pode sinalizar o processo")
    if os.name != "nt":
        checar(u"(fora do Windows: a armadilha do CTRL_C_EVENT nao existe)",
               True)
        return
    cod = (
        "import sys, os\n"
        "sys.path.insert(0, %r)\n"
        "import radai_watcher as W\n"
        "espiao = []\n"
        "os.kill = lambda *a, **k: espiao.append(a)\n"
        "vivo = W._processo_vivo(os.getpid())\n"
        "morto = W._processo_vivo(999999)\n"
        "assert not espiao, 'chamou os.kill: %%r' %% (espiao,)\n"
        "assert vivo is True, 'proprio pid devia ser True, veio %%r' %% (vivo,)\n"
        "assert morto is False, 'pid 999999 devia ser False, veio %%r' %% (morto,)\n"
    ) % (APP,)
    p = subprocess.run([sys.executable, "-c", cod],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    CTRL_C_EXIT = -1073741510
    erro = (p.stderr or b"").decode("utf-8", "replace").strip()
    checar(u"consultar um PID nao derruba quem consultou",
           p.returncode != CTRL_C_EXIT,
           u"exit=%s -- 0xC000013A e morte por Ctrl+C" % p.returncode)
    checar(u"nao passa por os.kill, e o veredito continua certo "
           u"(vivo=True, inexistente=False)",
           p.returncode == 0, erro[-400:])


def teste_a_espera_pelo_vigia_acusa_quem_morreu():
    secao(u"a espera pelo vigia acusa o processo que morreu")
    import subprocess
    proc = subprocess.Popen([sys.executable, "-c", "import sys; sys.exit(3)"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    t0 = time.time()
    pronto, como = _esperar_o_vigia(proc, _porta_livre(), "NINGUEM",
                                    prazo=30.0)
    gasto = time.time() - t0
    checar(u"processo morto: nao esta pronto, e o detalhe diz que SAIU com "
           u"o codigo", not pronto and u"SAIU (codigo 3)" in como, como)
    checar(u"  e sai cedo, sem pagar o prazo", gasto < 15.0,
           u"%.1f s de 30" % gasto)


def teste_a_documentacao_da_api_nao_e_servida():
    secao(u"o vigia nao serve a documentacao da API")
    import json as _json
    import subprocess
    import urllib.error
    import urllib.request

    base = novo_temp()
    acervo = os.path.join(base, "acervo")
    os.makedirs(acervo)
    _CS = _app_import("radai_consent")
    with open(os.path.join(acervo, _CS.ARQUIVO_ACEITE), "w",
              encoding="utf-8") as _f:
        _json.dump(_aceite_da_bateria(_CS, "PC_DOCS"), _f)
    porta = _porta_livre()
    cfg = os.path.join(base, "docs.config")
    with open(cfg, "w", encoding="utf-8") as f:
        f.write("ROOT=\nDRY_RUN=1\nTPS_DESTINO=eclipse\nPORT=%d\nLOG_DIR=%s\n"
                % (porta, os.path.join(base, "log")))
    env = dict(os.environ, RADAI_CONFIG=cfg, RADAI_MACHINE="PC_DOCS",
               RADAI_CALIB_DIR=acervo,
               LOCALAPPDATA=os.path.join(base, "ad"),
               PYTHONIOENCODING="utf-8:replace")
    proc = subprocess.Popen([sys.executable, _componentes.fonte("app/radai_watcher.py")],
                            env=env, stdout=subprocess.DEVNULL,
                            stderr=subprocess.STDOUT)

    class _SemSeguir(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k):
            return None
    abridor = urllib.request.build_opener(_SemSeguir)

    def status(rota):
        try:
            return abridor.open("http://127.0.0.1:%d%s" % (porta, rota),
                                timeout=10).getcode()
        except urllib.error.HTTPError as e:
            return e.code
        except Exception as e:
            return "%s" % type(e).__name__
    try:
        pronto, _como = _esperar_o_vigia(proc, porta, "PC_DOCS")
        checar(u"o vigia do teste subiu", pronto, _como)
        if not pronto:
            return
        checar(u"CONTROLE: a home responde 200 pelos mesmos portoes",
               status("/") == 200, str(status("/")))
        for rota in ("/docs", "/redoc", "/openapi.json",
                     "/docs/oauth2-redirect"):
            st = status(rota)
            checar(u"o vigia responde 404 em %s" % rota, st == 404, str(st))
    finally:
        try:
            proc.terminate()
            proc.wait(timeout=15)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass


def teste_o_passo_da_estatistica_so_le_e_diz():
    secao(u"o passo da estatistica de uso so le, e diz")
    RA = _app_import("radai_arranque")
    engine = _app_import("engine")
    pasta = tempfile.mkdtemp(prefix="radai_arranque_")
    velho = os.environ.get("TOTALSEG_HOME_DIR")
    casa = os.path.join(pasta, "tshome")
    os.makedirs(casa)
    os.environ["TOTALSEG_HOME_DIR"] = casa
    arq = os.path.join(casa, "config.json")

    def rodar():
        ctx, linhas = _ctx_do_arranque(pasta, engine=engine)
        rel = {"dados": {}, "avisos": [], "pendencias": []}
        return RA._p_estatistica(ctx, rel), rel

    def escrever(txt):
        with io.open(arq, "w", encoding="utf-8") as f:
            f.write(txt)
    try:
        escrever(u'{"totalseg_id": "t", "send_usage_stats": false}')
        L, rel = rodar()
        checar(u"false: «desligada (nenhuma chamada de rede)», e o envelope "
               u"tambem bloqueia", L and "desligada (nenhuma chamada de rede)"
               in L[0] and "tambem bloqueia" in L[0] and not rel["avisos"],
               L[:1])
        escrever(u'{"totalseg_id": "t", "send_usage_stats": true, '
                 u'"license_number": "aca_X"}')
        antes = io.open(arq, encoding="utf-8").read()
        L, rel = rodar()
        checar(u"true com o envelope: o envio esta BLOQUEADO pelo envelope",
               L and "BLOQUEADO pelo envelope" in L[0]
               and "send_usage_stats=true" in L[0] and not rel["avisos"],
               L[:1])
        checar(u"  e o arranque NAO gravou nada (so le)",
               io.open(arq, encoding="utf-8").read() == antes)
        os.remove(arq)
        L, rel = rodar()
        checar(u"ausente: diz que o motor o cria com false antes da primeira "
               u"task", L and "ainda nao existe" in L[0]
               and not os.path.exists(arq), L[:1])
        escrever(u'{"license_number": ')
        L, rel = rodar()
        checar(u"quebrado: diz que nao leu, e vira aviso",
               L and "nao consegui ler" in L[0] and rel["avisos"], L[:1])
        escrever(u'{"totalseg_id": "t", "send_usage_stats": true}')
        fonte = io.open(engine.RUNNER_TS, encoding="utf-8").read()
        velho_run = os.path.join(pasta, "radai_ts_runner.py")
        with io.open(velho_run, "w", encoding="utf-8") as f:
            f.write(fonte.replace("def remendar_estatistica(",
                                  "def _sem_remendo_aqui("))
        antigos = (engine.RUNNER_TS, list(engine.TS_CMD))
        engine.RUNNER_TS = velho_run
        engine.TS_CMD = [sys.executable, velho_run]
        try:
            L, rel = rodar()
        finally:
            engine.RUNNER_TS, engine.TS_CMD = antigos[0], antigos[1]
        checar(u"ISCA: um envelope sem o remendo -> LIGADA, e vira aviso",
               L and "LIGADA" in L[0] and "NAO bloqueia" in L[0]
               and rel["avisos"], L[:1])
    finally:
        if velho is None:
            os.environ.pop("TOTALSEG_HOME_DIR", None)
        else:
            os.environ["TOTALSEG_HOME_DIR"] = velho
        shutil.rmtree(pasta, ignore_errors=True)


def teste_a_sonda_do_arranque_e_a_da_tela_nao_correm_juntas():
    secao(u"a sonda do arranque e a da tela nao correm juntas")
    import threading
    RA = _app_import("radai_arranque")

    class _NaoTranca(object):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def cena(trava):
        chamadas = []

        def sonda(python_exe=None, timeout=120):
            chamadas.append(1)
            time.sleep(1.5)
            return {"importa": True, "versao": "2.5.1", "cuda": "12.1",
                    "disponivel": False, "n": 0}
        velho = dict(RA.ULTIMO)
        RA.ULTIMO.pop("torch", None)
        try:
            with _Dublagem(RA, sondar_torch=sonda, _LOCK_SONDA=trava):
                ctx, _l = _ctx_do_arranque(tempfile.gettempdir())
                rel = {"dados": {}, "avisos": [], "pendencias": []}
                t = threading.Thread(target=RA._p_torch, args=(ctx, rel))
                t.start()
                time.sleep(0.3)
                tela = RA.torch_da_estacao()
                t.join(10)
            return len(chamadas), tela, rel
        finally:
            RA.ULTIMO.clear()
            RA.ULTIMO.update(velho)
    n, tela, rel = cena(threading.Lock())
    checar(u"UMA sonda so, e a tela le a resposta do arranque",
           n == 1 and tela.get("versao") == "2.5.1"
           and (rel["dados"].get("torch") or {}).get("versao") == "2.5.1",
           u"%d sonda(s) | %s" % (n, tela))
    n2, _t2, _r2 = cena(_NaoTranca())
    checar(u"ISCA: sem a trava compartilhada, a tela dispara a SEGUNDA sonda",
           n2 == 2, u"%d sonda(s)" % n2)


class _MotorQueEntrega(_MotorFalso):

    MELHOR_FONTE = {}

    def __init__(self, pasta):
        _MotorFalso.__init__(self, "")
        self.pasta = pasta
        self.tasks = []
        self.rts = []
        self.oar_kw = None

    def load_sitk(self, pasta):
        import numpy as np
        import SimpleITK as sitk
        img = sitk.GetImageFromArray(np.zeros((8, 16, 16), dtype=np.int16))
        img.SetSpacing((2.0, 2.0, 3.0))
        return img

    def _mascara(self):
        import numpy as np
        m = np.zeros((8, 16, 16), dtype=bool)
        m[2:6, 4:12, 4:12] = True
        return m

    def run_ts_task(self, ref, t, device=None, jid=None, timeout_s=None,
                    cruas=None, **kw):
        self.tasks.append(t)
        if cruas is not None:
            cruas[t] = {"liver": self._mascara()}
        return {"liver": self._mascara()}

    def curar(self, masks, por_motor, log=None, tabela=None):
        return dict((k, masks[k]) for k in masks), {}

    def para_oar(self, masks, **kw):
        self.oar_kw = dict(kw)
        return dict(masks)

    TS_MAP = {}

    def preparar_full(self, masks, **kw):
        self.oar_kw = dict(kw)
        return dict((k, masks[k]) for k in masks), {
            "construcoes": {}, "observacoes": {}, "nao_sairam": [],
            "tempos": []}

    def selecionar_do_full(self, rt_full, mapa, permitidos, log=None,
                           meta=None):
        p = os.path.join(self.pasta, "rt_oar_%d.dcm" % len(self.rts))
        with open(p, "wb") as f:
            f.write(b"RTSTRUCT de mentira (selecao)")
        return p, dict(mapa), []

    def build_rtstruct(self, stage, masks, **kw):
        self.rts.append(dict(kw))
        p = os.path.join(self.pasta, "rt_%d.dcm" % len(self.rts))
        with open(p, "wb") as f:
            f.write(b"RTSTRUCT de mentira")
        return p, dict((k, k + "_ai") for k in masks)


def teste_a_rm_do_pescoco_roda_so_a_base_de_rm_e_leva_a_modalidade():
    secao(u"a RM do pescoco roda so a base de RM, e leva a modalidade")
    RT = _app_import("radai_tasks")
    TP = _app_import("radai_topography")
    agora = datetime.now()
    extra = {"DRY_RUN": "0", "MODALITIES": "CT,MR", "TASKS": "total_v3"}

    def rodar(isca=None):
        mod, root, base = montar([("PAC_RM_HN", agora - timedelta(days=1), 8)],
                                 extra=extra)
        envelhecer(root, 60)
        fila, _ = fila_de(mod)
        if not fila:
            return None, None, None
        s = fila[0]
        s["modality"] = "MR"
        motor = _MotorQueEntrega(base)
        mod.carregar_engine = lambda: motor
        mod.ler_topografia = lambda *a, **k: [TP.CABECA_PESCOCO]
        desfazer = []
        if isca == "ordem":
            real_de = TP.tasks_de
            regra = RT.tasks_da_serie

            def na_ordem_errada(proto, tasks):
                return real_de(proto, regra(list(tasks), "MR"))
            TP.tasks_de = na_ordem_errada
            mod.tasks_pela_modalidade = lambda t, m, log=None: list(t)
            desfazer.append(lambda: setattr(TP, "tasks_de", real_de))
        elif isca == "saida":
            real_saida = mod._saida_de
            mod._saida_de = (lambda e, st, d, rs, modalidade=None, tasks=None:
                             real_saida(e, st, d, rs, tasks=tasks))
        elif isca == "tasks":
            real_saida_t = mod._saida_de
            mod._saida_de = (lambda e, st, d, rs, modalidade=None, tasks=None:
                             real_saida_t(e, st, d, rs, modalidade=modalidade))
        try:
            mod.claim(s["dir"], s["uid"], {})
            ok = mod.process_series(s)
        finally:
            for f in desfazer:
                f()
        return ok, motor, mod

    ok, motor, mod = rodar()
    if motor is None:
        checar(u"a serie entrou na fila", False)
        return
    checar(u"a serie SAIU (caminho de sucesso inteiro, motor dublado)",
           ok is True, str(ok))
    checar(u"o motor recebeu SO a base de RM (a topografia de TC foi podada "
           u"depois)", motor.tasks == ["total_mr"], motor.tasks)
    checar(u"o entregue recebeu modalidade=MR (preparar_full, a cadeia do "
           u"FULL)", (motor.oar_kw or {}).get("modalidade") == "MR",
           (motor.oar_kw or {}).get("modalidade"))
    mods = [k.get("modalidade") for k in motor.rts]
    rotulos = [k.get("rotulo") for k in motor.rts]
    checar(u"TODO build_rtstruct recebeu modalidade=MR -- o FULL, de onde "
           u"sai o entregue (%d arquivo(s))" % len(motor.rts),
           len(motor.rts) >= 1 and all(m == "MR" for m in mods)
           and "RadAI_FULL" in rotulos,
           u"%s | %s" % (mods, rotulos))
    checar(u"  e o vigia NAO gravou o TS cru (v8.3: so por pedido)",
           "RadAI_TS" not in rotulos, str(rotulos))
    def _tasks_do_full(m):
        for k in (m.rts if m else []):
            if k.get("rotulo") == "RadAI_FULL":
                return list(k.get("tasks") or [])
        return None
    checar(u"o FULL (de onde sai o entregue) recebeu `tasks_ok` = o que "
           u"RODOU (total_mr), e nao o TASKS do config (total_v3)",
           _tasks_do_full(motor) == ["total_mr"], _tasks_do_full(motor))
    okt, motort, _mt = rodar("tasks")
    checar(u"ISCA: um `_saida_de` que ignora o `tasks_ok` entrega o TASKS "
           u"do config (a checagem reprovaria)",
           _tasks_do_full(motort) == ["total_v3"], _tasks_do_full(motort))
    ok1, motor1, _m1 = rodar("ordem")
    checar(u"ISCA: com a poda ANTES da topografia, as tasks de TC do pescoco "
           u"chegam ao motor numa RM",
           motor1 is not None and bool(set(_CP) & set(motor1.tasks)),
           motor1.tasks if motor1 else None)
    ok2, motor2, _m2 = rodar("saida")
    mods2 = [k.get("modalidade") for k in (motor2.rts if motor2 else [])]
    checar(u"ISCA: sem repassar a modalidade, NENHUM conjunto a recebe (o "
           u"entregue inclusive: ele sai da mesma `Saida`)",
           motor2 is not None and mods2 and all(m is None for m in mods2)
           and (motor2.oar_kw or {}).get("modalidade") is None, mods2)


def teste_a_serie_do_vigia_na_cadeia_da_v82():
    secao(u"a serie do vigia na cadeia da v8.2 (cofres, sem TS cru, rascunho)")
    agora = datetime.now()

    mod, root, base = montar([("PAC_COFRE", agora - timedelta(days=1), 8)],
                             extra={"DRY_RUN": "0"})
    envelhecer(root, 60)
    fila, _ = fila_de(mod)
    if not fila:
        checar(u"a serie entrou na fila", False)
        return
    s = fila[0]
    mod.carregar_engine = lambda: _MotorFalso("parou de proposito na bateria")
    lixo = {"orgao_do_paciente_anterior": True}
    mod._HNLNL_DA_VEZ["masks"] = lixo
    mod.claim(s["dir"], s["uid"], {})
    ok = mod.process_series(s)
    checar(u"a serie falhou (o caminho que deixava o cofre cheio)",
           ok is False, str(ok))
    checar(u"e o cofre dos niveis voltou a vazio",
           mod._HNLNL_DA_VEZ["masks"] is None, str(mod._HNLNL_DA_VEZ))
    checar(u"  e os cofres do NV e do CADS nao existem mais (v8.3)",
           not hasattr(mod, "_NV_DA_VEZ") and not hasattr(mod, "_CADS_DA_VEZ"))
    import ast as _ast
    fonte = io.open(_componentes.fonte("app/radai_watcher.py"),
                    encoding="utf-8").read()
    ps = [n for n in _ast.walk(_ast.parse(fonte))
          if isinstance(n, _ast.FunctionDef) and n.name == "process_series"]
    chamadas_topo, no_finally = False, False
    if ps:
        for no in ps[0].body:
            if isinstance(no, _ast.Try):
                no_finally = any(
                    isinstance(c, _ast.Call)
                    and getattr(c.func, "id", "") == "_esvaziar_cofres"
                    for f in no.finalbody for c in _ast.walk(f))
                for k, inst in enumerate(no.body):
                    nomes = [getattr(c.func, "id", "") or
                             getattr(c.func, "attr", "")
                             for c in _ast.walk(inst)
                             if isinstance(c, _ast.Call)]
                    if "_esvaziar_cofres" in nomes:
                        chamadas_topo = True
                        break
                    if "carregar_engine" in nomes or "copy_sorted" in nomes:
                        break
                break
    checar(u"`process_series` esvazia os cofres no comeco do `try`, antes de "
           u"o motor ser chamado (e o `finally` que solta a trava ja vale)",
           chamadas_topo)
    checar(u"  e no `finally`", no_finally)

    mod2, root2, base2 = montar([("PAC_TS0", agora - timedelta(days=1), 8)],
                                extra={"DRY_RUN": "0", "TASKS": "total_v3",
                                       "ENTREGAR_TS": "1"})
    envelhecer(root2, 60)
    fila2, _ = fila_de(mod2)
    if not fila2:
        checar(u"a serie entrou na fila", False)
        return
    s2 = fila2[0]
    motor = _MotorQueEntrega(base2)
    mod2.carregar_engine = lambda: motor
    mod2.ler_topografia = lambda *a, **k: ["total"]
    linhas = []
    velho = mod2.wlog
    mod2.wlog = lambda m="": linhas.append(str(m))
    try:
        mod2.claim(s2["dir"], s2["uid"], {})
        ok2 = mod2.process_series(s2)
    finally:
        mod2.wlog = velho
    checar(u"sem o TS cru a serie SAI (o entregue vem das cruas)",
           ok2 is True, str(ok2))
    rotulos = [k.get("rotulo") for k in motor.rts]
    checar(u"  o FULL foi montado", "RadAI_FULL" in rotulos, str(rotulos))
    checar(u"  e o `TS_` NAO, nem com ENTREGAR_TS=1 de um config antigo "
           u"(v8.3: o vigia nunca o grava)",
           "RadAI_TS" not in rotulos, str(rotulos))
    checar(u"  e nenhum motor de comparacao foi gravado (RadAI_NV, _CADS, "
           u"_MSE)", not [r for r in rotulos
                          if r in ("RadAI_NV", "RadAI_CADS", "RadAI_MSE")],
           str(rotulos))
    checar(u"o relatorio dos conjuntos sai no log do vigia",
           any(l.startswith("conjuntos gravados:") for l in linhas),
           u" | ".join(l for l in linhas if "conjunto" in l)[:200])

    destino = os.path.join(base2, "alvo.dcm")
    origem = os.path.join(base2, "origem.dcm")
    with open(origem, "wb") as f:
        f.write(b"RT")
    real_replace = os.replace

    def _quebra(a, b):
        raise OSError("o share caiu de proposito")
    os.replace = _quebra
    try:
        try:
            mod2._copiar_atomico(origem, destino)
            levantou = False
        except OSError:
            levantou = True
    finally:
        os.replace = real_replace
    sobras = [n for n in os.listdir(base2) if n.endswith(".parcial")]
    checar(u"a copia que falha LEVANTA (quem chama decide)", levantou)
    checar(u"  e o `.parcial` nao sobra na pasta da serie", not sobras,
           str(sobras))

    ps_fonte = ""
    if ps:
        linhas_f = fonte.splitlines()
        ps_fonte = u"\n".join(linhas_f[ps[0].lineno - 1:ps[0].end_lineno])
    checar(u"e a `Saida` do entregue nasce com o que rodou "
           u"(`tasks=list(tasks_ok)`)",
           u"tasks=list(tasks_ok)" in ps_fonte)


class _MotorQueGuardaOsPedidos(_MotorQueEntrega):

    def __init__(self, pasta):
        _MotorQueEntrega.__init__(self, pasta)
        self.kw_ts = []

    def run_ts_task(self, ref, t, device=None, jid=None, timeout_s=None,
                    cruas=None, **kw):
        self.kw_ts.append(dict(kw, _task=t))
        return _MotorQueEntrega.run_ts_task(self, ref, t, device=device,
                                            jid=jid, timeout_s=timeout_s,
                                            cruas=cruas)


class _MotorQueGuardaAsChaves(_MotorQueGuardaOsPedidos):

    def __init__(self, pasta):
        _MotorQueGuardaOsPedidos.__init__(self, pasta)
        self.chaves = {}

    def build_rtstruct(self, stage, masks, **kw):
        self.chaves[kw.get("rotulo")] = sorted(masks)
        return _MotorQueGuardaOsPedidos.build_rtstruct(self, stage, masks, **kw)


def teste_os_niveis_seguem_o_pescoco_e_o_recorte_chega_ao_motor():
    secao(u"os niveis seguem o pescoco; o recorte no corpo chega ao motor")
    agora = datetime.now()

    mod, _r, _b = montar([("PAC_CH", agora - timedelta(days=1), 8)])
    checar(u"INCLUIR_HNLNL saiu do config (DEFAULTS, texto e global)",
           "INCLUIR_HNLNL" not in mod.DEFAULTS
           and "\nINCLUIR_HNLNL=" not in mod.DEFAULT_CFG
           and not hasattr(mod, "INCLUIR_HNLNL"))
    checar(u"sem a chave no config, RECORTE_NO_CORPO vale 1 (DEFAULTS)",
           mod.RECORTE_NO_CORPO is True
           and mod.DEFAULTS.get("RECORTE_NO_CORPO") == "1",
           str((mod.RECORTE_NO_CORPO, mod.DEFAULTS.get("RECORTE_NO_CORPO"))))
    checar(u"  e o texto do config a declara, com o porquê",
           "\nRECORTE_NO_CORPO=1\n" in mod.DEFAULT_CFG
           and "--body_seg" in mod.DEFAULT_CFG
           and "Dataset300" in mod.DEFAULT_CFG)
    mod.CFG["RECORTE_NO_CORPO"] = "0"
    mod.aplicar_cfg()
    checar(u"a RECARGA A QUENTE obedece ao recorte (aplicar_cfg)",
           mod.RECORTE_NO_CORPO is False, str(mod.RECORTE_NO_CORPO))

    RO = _app_import("radai_output")

    def rodar(extra, pescoco=None, isca=None):
        cfg = {"DRY_RUN": "0", "TASKS": "total_v3"}
        cfg.update(extra)
        m2, root, base = montar([("PAC_RC", agora - timedelta(days=1), 8)],
                                extra=cfg)
        envelhecer(root, 60)
        fila, _ = fila_de(m2)
        if not fila:
            return None, None, [], m2
        s = fila[0]
        motor = _MotorQueGuardaAsChaves(base)
        m2.carregar_engine = lambda: motor
        m2.ler_topografia = lambda *a, **k: ["total"]
        if pescoco is not None:
            motor.pescoco_no_campo = (
                lambda masks, grade, cru=None:
                (bool(pescoco), u"pescoco: %s (dublado)"
                 % (u"sim" if pescoco else u"nao")))
            m2.pescoco_no_campo = (
                lambda masks, grade, cru=None:
                (not pescoco, u"pescoco: medida DE NOVO (nao devia)"))
        if isca == "portao":
            m2._niveis_cervicais_nesta_serie = lambda *a, **k: True
        if isca == "hnl_de_volta":
            _real_em = m2._entregar_motores

            def _com_o_hnl(*a, **k):
                _cofre = m2._HNLNL_DA_VEZ.get("masks")
                sd = _real_em(*a, **k)
                if _cofre and sd is not None:
                    sd.niveis_cervicais(_cofre)
                return sd
            m2._entregar_motores = _com_o_hnl
        pedidos = []
        real = RO.niveis_cervicais_da_serie

        def _niveis(ref, cruas, device="cpu", log=None):
            import numpy as np
            pedidos.append(sorted(cruas or {}))
            m = np.zeros((8, 16, 16), dtype=bool)
            m[2:6, 4:12, 4:12] = True
            return {"LNL07": m, "LNL_Union": m.copy()}
        RO.niveis_cervicais_da_serie = _niveis
        try:
            m2.claim(s["dir"], s["uid"], {})
            ok = m2.process_series(s)
        finally:
            RO.niveis_cervicais_da_serie = real
        return ok, motor, pedidos, m2

    ok, motor, pedidos, _m = rodar({"RECORTE_NO_CORPO": "0"}, pescoco=True)
    if motor is None:
        checar(u"a serie entrou na fila", False)
        return
    checar(u"a serie SAIU (caminho de sucesso inteiro, motor dublado)",
           ok is True, str(ok))
    recs = [k.get("recorte_no_corpo", u"AUSENTE") for k in motor.kw_ts]
    checar(u"com RECORTE_NO_CORPO=0, TODA task recebe recorte_no_corpo=False",
           recs and all(r is False for r in recs), recs)
    checar(u"COM PESCOCO, o vigia chama a cadeia COMUM dos niveis, UMA vez, "
           u"com as cruas da serie (a base e as de C&P da topografia)",
           len(pedidos) == 1 and "total_v3" in pedidos[0]
           and "headneck_bones_vessels" in pedidos[0], pedidos)
    checar(u"  e sem o pescoco confirmado pelo MOTOR (o fantoma nao tem "
           u"mandibula), os constritores ficam de fora: a trava vence",
           len(pedidos) == 1 and "headneck_muscles" not in pedidos[0], pedidos)
    full = motor.chaves.get("RadAI_FULL") or []
    checar(u"  e os niveis ENTRAM NO FULL (spec 1.1: «entra no FULL»)",
           "LNL07" in full and "LNL_Union" in full, str(full))
    checar(u"  e seguem a MESMA medida da anatomia (o `pescoco_no_campo` do "
           u"modulo, dublado ao contrario, nao foi quem decidiu)",
           len(pedidos) == 1, pedidos)
    _kw_full = [k for k in motor.rts if k.get("rotulo") == "RadAI_FULL"]
    obs = (_kw_full[0].get("observacoes") or {}) if _kw_full else {}
    checar(u"  e o FULL leva a descricao de cada nivel (a ressalva do nome "
           u"neutro)",
           u"Rotulo 7 de 20" in (obs.get("LNL07") or u"")
           and u"Uniao dos 20" in (obs.get("LNL_Union") or u""),
           sorted(obs) if _kw_full else u"o FULL nao foi gravado")
    _rot_hnl = _app_import("radai_hnlnl").ROTULO_TPS
    hnl = [k for k in motor.rts if k.get("rotulo") == _rot_hnl]
    checar(u"  e o vigia NAO grava o `HNL_` (o AUTO grava o FULL e o "
           u"RadAI_OAR; o arquivo proprio dos niveis so no PERSONALIZADO)",
           not hnl, u"o HNL_ foi gravado")
    ok_h, motor_h, pedidos_h, _m = rodar({"RECORTE_NO_CORPO": "0"},
                                         pescoco=True, isca="hnl_de_volta")
    checar(u"  ISCA: o vigia gravando o `HNL_` de novo e acusado (a "
           u"checagem acima reprovaria)",
           motor_h is not None and len(pedidos_h) == 1 and bool(
               [k for k in motor_h.rts if k.get("rotulo") == _rot_hnl]),
           str([k.get("rotulo") for k in (motor_h.rts if motor_h else [])]))

    ok, motor, pedidos, _m = rodar({})
    recs = [k.get("recorte_no_corpo", u"AUSENTE") for k in motor.kw_ts] \
        if motor else []
    checar(u"de fabrica, TODA task recebe recorte_no_corpo=True",
           recs and all(r is True for r in recs), recs)
    checar(u"SEM PESCOCO (o fantoma de fabrica), o vigia NAO roda os niveis",
           ok is True and pedidos == [], pedidos)
    full = (motor.chaves.get("RadAI_FULL") or []) if motor else []
    checar(u"  e nenhum nivel entra no FULL",
           not [k for k in full if k.startswith("LNL")], str(full))

    ok, motor, pedidos, _m = rodar({"INCLUIR_HNLNL": "1"})
    checar(u"a linha velha INCLUIR_HNLNL=1 de um config antigo NAO liga os "
           u"niveis sem pescoco", ok is True and pedidos == [], pedidos)

    info = {"modalidade": "MR"}
    checar(u"numa RM os niveis nao rodam (o modelo e de TC), e o motivo fica "
           u"no caso", _m._niveis_cervicais_nesta_serie({}, {}, None, info)
           is False and "TC" in (info.get("niveis_cervicais") or {})
           .get("motivo", u""), str(info))

    ok, motor, pedidos, _m = rodar({}, isca="portao")
    checar(u"ISCA: com o portao forcado, os niveis rodam SEM pescoco (a "
           u"checagem «sem pescoco, nao roda» reprovaria)",
           pedidos == [["total_v3"]], pedidos)

    import ast as _ast
    fonte = io.open(_componentes.fonte("app/radai_watcher.py"),
                    encoding="utf-8").read()
    chamadas = [n for n in _ast.walk(_ast.parse(fonte))
                if isinstance(n, _ast.Call) and isinstance(n.func, _ast.Attribute)
                and n.func.attr == "run_ts_task"]
    sem = [n.lineno for n in chamadas
           if "recorte_no_corpo" not in [k.arg for k in n.keywords]]
    checar(u"TODA chamada de `engine.run_ts_task` do vigia passa "
           u"`recorte_no_corpo=`", chamadas and not sem,
           u"%d chamada(s), sem a chave nas linhas %s" % (len(chamadas), sem))
    checar(u"e o lote recebe a chave injetada (o «Rodar agora» recorta igual)",
           '"recorte_no_corpo": bool(RECORTE_NO_CORPO)' in fonte)
    arv = _ast.parse(fonte)
    fns = dict((n.name, n) for n in _ast.walk(arv)
               if isinstance(n, _ast.FunctionDef))

    def _chama(fn, nome):
        return fn is not None and any(
            isinstance(c, _ast.Call) and getattr(c.func, "id", "") == nome
            for c in _ast.walk(fn))
    checar(u"`process_series` decide os niveis por "
           u"`_niveis_cervicais_nesta_serie`",
           _chama(fns.get("process_series"), "_niveis_cervicais_nesta_serie"))
    checar(u"  e ela pergunta a `pescoco_no_campo` (o marco da topografia)",
           _chama(fns.get("_niveis_cervicais_nesta_serie"), "pescoco_no_campo"))


def teste_o_lote_recebe_as_funcoes_de_erro_do_vigia():
    secao(u"o lote recebe as funcoes de erro do vigia")
    import ast as _ast
    fonte = io.open(_componentes.fonte("app/radai_watcher.py"),
                    encoding="utf-8").read()
    chaves = ("classificar_erro", "erro_de_ambiente", "limpar_erro")

    def _ligadas(texto):
        achou = []
        for n in _ast.walk(_ast.parse(texto)):
            if not isinstance(n, _ast.Dict):
                continue
            ks = [k.value for k in n.keys if isinstance(k, _ast.Constant)]
            if "recorte_no_corpo" not in ks or "python_exe" not in ks:
                continue
            for k, v in zip(n.keys, n.values):
                if (isinstance(k, _ast.Constant) and k.value in chaves
                        and isinstance(v, _ast.Name) and v.id == k.value):
                    achou.append(k.value)
        return sorted(achou)
    checar(u"o dicionario do lote liga as tres chaves as funcoes do vigia",
           _ligadas(fonte) == sorted(chaves), _ligadas(fonte))
    for c in chaves:
        checar(u"  e `%s` existe no vigia" % c,
               any(isinstance(n, _ast.FunctionDef) and n.name == c
                   for n in _ast.walk(_ast.parse(fonte))))
    forjada = fonte
    for c in chaves:
        forjada = forjada.replace(u'"%s": %s,' % (c, c), u"")
    checar(u"ISCA: sem as tres linhas, a checagem acusa (ela sabe reprovar)",
           forjada != fonte and _ligadas(forjada) == [], _ligadas(forjada))


def teste_a_saida_so_passa_a_modalidade_quando_sabe():
    secao(u"radai_output so passa a modalidade quando sabe")
    RO = _app_import("radai_output")
    base = novo_temp()
    try:
        class _Motor(object):
            def __init__(self):
                self.kw = []

            def build_rtstruct(self, stage, masks, **kw):
                self.kw.append(kw)
                p = os.path.join(base, "rt_%d.dcm" % len(self.kw))
                with open(p, "wb") as f:
                    f.write(b"x")
                return p, {"liver": "Liver_ts"}
        m1 = _Motor()
        RO.Saida(m1, base, base, "RS_RadAI_x.dcm", modalidade="mr").conjunto(
            "ts", {"liver": object()}, "ts")
        checar(u"com modalidade: o build_rtstruct a recebe (normalizada: MR)",
               m1.kw and m1.kw[0].get("modalidade") == "MR", m1.kw[:1])
        m2 = _Motor()
        RO.Saida(m2, base, base, "RS_RadAI_x.dcm").conjunto(
            "ts", {"liver": object()}, "ts")
        checar(u"sem modalidade: o argumento NAO e passado",
               m2.kw and "modalidade" not in m2.kw[0], m2.kw[:1])
    finally:
        shutil.rmtree(base, ignore_errors=True)



_GRADE_ANAT = (40, 64, 64)
_ESPAC_ANAT = (4.0, 4.0, 5.0)


def _bloco(z0, z1, y0, y1, x0, x1):
    import numpy as np
    m = np.zeros(_GRADE_ANAT, dtype=bool)
    m[z0:z1, y0:y1, x0:x1] = True
    return m


def _anatomia(regioes):
    amig, cru = {}, {}
    if "cabeca" in regioes:
        amig["brain"] = _bloco(24, 39, 20, 32, 20, 32)
    if "pescoco" in regioes:
        amig["vertebrae_C2"] = _bloco(34, 38, 40, 45, 30, 35)
        amig["vertebrae_C3"] = _bloco(30, 34, 40, 45, 30, 35)
        amig["vertebrae_C4"] = _bloco(26, 30, 40, 45, 30, 35)
        amig["mandible"] = _bloco(28, 38, 46, 56, 25, 40)
    if "pescoco_sem_mandibula" in regioes:
        amig["vertebrae_C2"] = _bloco(34, 38, 40, 45, 30, 35)
        amig["vertebrae_C3"] = _bloco(30, 34, 40, 45, 30, 35)
        amig["vertebrae_C4"] = _bloco(26, 30, 40, 45, 30, 35)
    if "c3c4_c2_na_borda" in regioes:
        amig["vertebrae_C2"] = _bloco(38, 39, 40, 45, 30, 31)
        amig["vertebrae_C3"] = _bloco(30, 34, 40, 45, 30, 35)
        amig["vertebrae_C4"] = _bloco(26, 30, 40, 45, 30, 35)
    if "so_c6c7" in regioes:
        amig["vertebrae_C6"] = _bloco(30, 34, 40, 45, 30, 35)
        amig["vertebrae_C7"] = _bloco(26, 30, 40, 45, 30, 35)
    if "torax" in regioes or "pulmao" in regioes:
        amig["lung_left"] = _bloco(8, 23, 10, 30, 40, 50)
        amig["lung_right"] = _bloco(8, 23, 10, 30, 14, 24)
    if "torax" in regioes:
        cru["clavicula_left"] = _bloco(22, 24, 5, 8, 40, 50)
        cru["clavicula_right"] = _bloco(22, 24, 5, 8, 14, 24)
        cru["scapula_left"] = _bloco(12, 20, 40, 45, 45, 55)
        cru["scapula_right"] = _bloco(12, 20, 40, 45, 9, 19)
    if "pelve" in regioes:
        amig["hip_left"] = _bloco(0, 6, 20, 40, 40, 55)
        amig["hip_right"] = _bloco(0, 6, 20, 40, 9, 24)
    if "coracao" in regioes:
        amig["heart"] = _bloco(8, 18, 30, 45, 25, 40)
    if "coracao_pequeno" in regioes:
        amig["heart"] = _bloco(8, 13, 30, 40, 25, 37)
    return amig, cru


class _MotorAnatomico(_MotorQueEntrega):

    def __init__(self, pasta, regioes, ao_rodar=None, erro_na=None):
        _MotorQueEntrega.__init__(self, pasta)
        real = _motor_do_teste()
        self.regioes_no_campo = real.regioes_no_campo
        self.TASKS_DE_ACHADO = real.TASKS_DE_ACHADO
        self._volume_cm3 = real._volume_cm3
        self.pescoco_no_campo = real.pescoco_no_campo
        self.anat, self.cru_base = _anatomia(regioes)
        self.ao_rodar = ao_rodar
        self.erro_na = erro_na or {}
        self.kw_tentativas = []

    def load_sitk(self, pasta):
        import numpy as np
        import SimpleITK as sitk
        img = sitk.GetImageFromArray(np.zeros(_GRADE_ANAT, dtype=np.int16))
        img.SetSpacing(_ESPAC_ANAT)
        return img

    def run_ts_task(self, ref, t, device=None, jid=None, timeout_s=None,
                    cruas=None, **kw):
        self.tasks.append(t)
        self.kw_tentativas.append(dict(kw, _task=t, timeout_s=timeout_s))
        if self.ao_rodar is not None:
            self.ao_rodar(t)
        if t in self.erro_na:
            e = self.erro_na[t]
            if isinstance(e, list):
                e = e.pop(0) if e else None
            if e is not None:
                raise e
        if t.startswith("total"):
            base = dict(self.anat)
            base.setdefault("liver", self._mascara_grande())
            if cruas is not None:
                c = dict(self.cru_base)
                c.update(base)
                cruas[t] = c
            return base
        if cruas is not None:
            cruas[t] = {"liver": self._mascara_grande()}
        return {}

    def _mascara_grande(self):
        return _bloco(10, 20, 20, 30, 20, 30)


def _tirar_as_datas(root):
    import pydicom
    for d, _, fs in os.walk(root):
        for f in fs:
            if not f.lower().endswith(".dcm"):
                continue
            fp = os.path.join(d, f)
            ds = pydicom.dcmread(fp)
            for tag in ("StudyDate", "SeriesDate", "AcquisitionDate",
                        "ContentDate", "StudyTime", "SeriesTime",
                        "AcquisitionTime", "ContentTime"):
                if tag in ds:
                    delattr(ds, tag)
            ds.save_as(fp)


def _rodar_anatomia(regioes, extra=None, pid="PAC_ANAT", manual=None,
                    ao_rodar=None, erro_na=None, machine="PC_A", antes=None,
                    motor_cls=None, sem_data=False):
    cfg = {"DRY_RUN": "0", "TASKS": "total_v3", "INCLUIR_NV": "0",
           "INCLUIR_CADS": "0", "INCLUIR_MOOSE": "0", "INCLUIR_HNLNL": "0",
           "ENTREGAR_TS": "0", "RECORTE_NO_CORPO": "0"}
    cfg.update(extra or {})
    agora = datetime.now()
    mod, root, base = montar([(pid, agora - timedelta(days=1), 8)],
                             extra=cfg, machine=machine)
    if sem_data:
        _tirar_as_datas(root)
    envelhecer(root, 60)
    fila, _ = fila_de(mod)
    if not fila:
        return None, None, mod, None, []
    s = fila[0]
    motor = (motor_cls or _MotorAnatomico)(
        base, regioes, ao_rodar=(lambda t: ao_rodar(t, mod, s))
        if ao_rodar else None, erro_na=erro_na)
    mod.carregar_engine = lambda: motor
    if manual is not None:
        mod.ler_topografia = lambda *a, **k: list(manual)
    linhas = []
    velho = mod.wlog

    def _wlog(m=""):
        linhas.append(str(m))
    mod.wlog = _wlog
    if antes is not None:
        antes(mod, s, motor)
    try:
        mod.claim(s["dir"], s["uid"], {"machine": machine,
                                       "pid_os": os.getpid()})
        ok = mod.process_series(s)
    finally:
        mod.wlog = velho
    return ok, motor, mod, s, linhas


_CP = ("head_glands_cavities", "headneck_muscles", "headneck_bones_vessels",
       "head_muscles", "craniofacial_structures")
_CR = ("head_glands_cavities", "craniofacial_structures")
_TORAX = ("trunk_cavities", "breasts", "pleural_pericard_effusion")


def _vigia_com_o_encefalo(regioes, segmentar=None):
    CR = _app_import("radai_cranio_engine")
    velho_d, velho_s = CR.disponivel, CR.segmentar_serie

    def _antes(mod, s, motor):
        CR.disponivel = lambda base=None: (
            False, u"os pesos do modelo do cranio nao estao nesta instalacao")
        if segmentar is not None:
            CR.segmentar_serie = segmentar
    try:
        ok, motor, mod, s, linhas = _rodar_anatomia(regioes, antes=_antes)
    finally:
        CR.disponivel, CR.segmentar_serie = velho_d, velho_s
    done = (mod.read_marker(s["dir"], s["uid"], "done") or {}) if s else {}
    return ok, done, linhas


def teste_o_encefalo_sem_peso_entra_no_faltou_do_vigia():
    secao(u"INS-02: o encefalo sem peso entra no faltou do vigia")
    ok, done, linhas = _vigia_com_o_encefalo({"cabeca"})
    nomes = [x.get("estrutura") for x in done.get("faltou") or ()]
    checar(u"o cranio sem o peso do motor: a serie SAI", ok is True, str(ok))
    checar(u"  e o `done` diz que faltaram o tronco e o quiasma, pelo motor "
           u"sem peso",
           {"brain_brainstem", "optic_chiasm"} <= set(nomes)
           and all(u"cranio_ct: sem_peso" in (x.get("porque") or u"")
                   for x in done.get("faltou") or ()),
           done.get("faltou"))
    checar(u"  e o log diz PARCIAL com o tronco",
           any(u"PARCIAL" in l and u"brain_brainstem" in l for l in linhas),
           [l for l in linhas if u"PARCIAL" in l or u"SEM PESO" in l][:3])
    ok, done, linhas = _vigia_com_o_encefalo({"pescoco"})
    checar(u"o pescoco SEM encefalo no campo: o motor nao se aplica, e o "
           u"`done` nao tem `faltou`",
           ok is True and not done.get("faltou"), done.get("faltou"))

    def _so_loga(ref, base, grade, log=None, **k):
        if log:
            log(u"cranio: os pesos do modelo do cranio nao estao nesta "
                u"instalacao")
        return {}
    ok, done, linhas = _vigia_com_o_encefalo({"cabeca"}, segmentar=_so_loga)
    checar(u"ISCA: o motor que so loga deixa o `faltou` sem o tronco -- a "
           u"checagem reprova",
           "brain_brainstem" not in [x.get("estrutura")
                                     for x in done.get("faltou") or ()],
           done.get("faltou"))


def teste_o_vigia_decide_a_regiao_pela_anatomia():
    secao(u"E2: o vigia decide a regiao pela anatomia, depois da base")
    MO = _app_import("radai_modes")
    TP = _app_import("radai_topography")

    ok, motor, mod, s, linhas = _rodar_anatomia({"torax"})
    if motor is None:
        checar(u"a serie entrou na fila", False)
        return
    checar(u"torax pela anatomia: a serie SAI", ok is True, str(ok))
    checar(u"  e roda a base e, DEPOIS dela, a lista do torax "
           u"(trunk_cavities, breasts e o derrame)",
           motor.tasks == ["total_v3"] + list(_TORAX), motor.tasks)
    checar(u"  e o log diz a anatomia e de onde veio a lista",
           any(u"anatomia da serie" in l and u"torax" in l for l in linhas)
           and any(u"pela anatomia" in l and u"TASKS_POR_TOPOGRAFIA" in l
                   for l in linhas), [l for l in linhas if "anatomia" in l][:4])
    done = mod.read_marker(s["dir"], s["uid"], "done") or {}
    checar(u"  e o `done` guarda as regioes e a maquina/dispositivo de cada "
           u"task (spec E3)",
           done.get("regioes") == ["torax"]
           and any(e.get("task") == "trunk_cavities"
                   and e.get("maquina") == "PC_A" and e.get("dispositivo")
                   for e in done.get("etapas") or []),
           str((done.get("regioes"), (done.get("etapas") or [])[:2])))

    ok, motor, mod, s, linhas = _rodar_anatomia({"pulmao"})
    checar(u"ISCA: pulmao SEM clavicula e escapula nao e torax (so a base)",
           motor is not None and motor.tasks == ["total_v3"],
           motor.tasks if motor else None)

    ok, motor, mod, s, linhas = _rodar_anatomia({"cabeca"})
    checar(u"CRANIO pelo encefalo, sem pescoco: so as duas do cranio "
           u"(head_glands_cavities, craniofacial_structures)",
           motor is not None and motor.tasks == ["total_v3"] + list(_CR),
           motor.tasks if motor else None)
    checar(u"  e NENHUMA das tres do pescoco roda",
           motor is not None and not ({"headneck_muscles",
                                       "headneck_bones_vessels",
                                       "head_muscles"} & set(motor.tasks)),
           motor.tasks if motor else None)
    checar(u"  e o `done` guarda a regiao `cranio`, e o log diz por que",
           (mod.read_marker(s["dir"], s["uid"], "done") or {}).get("regioes")
           == ["cranio"] and any(u"cranio: sim" in l for l in linhas),
           [l for l in linhas if u"cranio" in l][:2])
    _velho_cr = TP.CRANIO
    TP.CRANIO = TP.CABECA_PESCOCO
    try:
        _ok_i, motor_i, _m_i, _s_i, _l_i = _rodar_anatomia({"cabeca"})
    finally:
        TP.CRANIO = _velho_cr
    checar(u"  ISCA: com a regra de antes (o encefalo vale cabeca e pescoco), "
           u"o cranio sem pescoco roda as do pescoco (menos os constritores, "
           u"que a trava do pescoco segura) -- a checagem do cranio "
           u"reprovaria",
           motor_i is not None
           and motor_i.tasks != ["total_v3"] + list(_CR)
           and {"headneck_bones_vessels", "head_muscles"} <= set(motor_i.tasks)
           and "headneck_muscles" not in motor_i.tasks,
           motor_i.tasks if motor_i else None)
    ok, motor, mod, s, linhas = _rodar_anatomia({"cabeca", "pescoco"})
    checar(u"cranio COM pescoco: a lista de cabeca e pescoco (as cinco, que "
           u"contem as do cranio), cada task UMA vez",
           motor is not None and motor.tasks == ["total_v3"] + list(_CP),
           motor.tasks if motor else None)
    ok, motor, mod, s, linhas = _rodar_anatomia({"pescoco"})
    checar(u"PESCOCO sem encefalo (o tireoidectomizado): C2, C3 e C4 "
           u"disparam a lista de cabeca e pescoco",
           motor is not None and motor.tasks == ["total_v3"] + list(_CP),
           motor.tasks if motor else None)
    ok, motor, mod, s, linhas = _rodar_anatomia({"pescoco_sem_mandibula"})
    checar(u"ISCA: C2, C3 e C4 sem a mandibula no campo NAO e pescoco (o "
           u"gatilho mais rigido)",
           motor is not None and motor.tasks == ["total_v3"],
           motor.tasks if motor else None)
    ok, motor, mod, s, linhas = _rodar_anatomia({"c3c4_c2_na_borda"})
    checar(u"ISCA (a P20): C3 e C4 inteiras com a C2 so na borda NAO e "
           u"pescoco -- o pescoco alto esta fora do campo",
           motor is not None and motor.tasks == ["total_v3"],
           motor.tasks if motor else None)
    ok, motor, mod, s, linhas = _rodar_anatomia({"so_c6c7"})
    checar(u"ISCA: so C6 e C7 (a TC de torax que sobe a fossa) NAO e pescoco",
           motor is not None and motor.tasks == ["total_v3"],
           motor.tasks if motor else None)
    checar(u"  e o laudo diz o volume de cada cervical",
           any(u"pescoco: nao" in l and u"C6" in l for l in linhas),
           [l for l in linhas if "pescoco" in l][:2])

    ok, motor, mod, s, linhas = _rodar_anatomia({"torax"}, pid="PAC_PESCOCO")
    checar(u"o texto do exame diz «pescoco» e a anatomia e so torax: NAO roda "
           u"a lista do pescoco",
           motor is not None and not (set(_CP) & set(motor.tasks)),
           motor.tasks if motor else None)
    checar(u"  e o log diz que o texto sugeriu e nao decide",
           any(u"texto do exame sugere" in l for l in linhas),
           [l for l in linhas if "texto" in l][:2])
    ok, motor, mod, s, linhas = _rodar_anatomia(
        {"torax"}, manual=["total", TP.CABECA_PESCOCO])
    # GUARDA: `engine.portao_da_regiao` pula a task da cabeca sem cabeca nem pescoco, e a dos constritores sem o pescoco confirmado.
    _pescoco = ("headneck_bones_vessels",)
    checar(u"a escolha MANUAL do operador na fila acrescenta a lista do "
           u"pescoco (e a anatomia acrescenta a do torax)",
           motor is not None and set(_pescoco) <= set(motor.tasks)
           and set(_TORAX) <= set(motor.tasks)
           and motor.tasks[0] == "total_v3", motor.tasks if motor else None)
    checar(u"  e os constritores (headneck_muscles), pedidos a mao sem o "
           u"pescoco confirmado, NAO rodam: a trava vence",
           motor is not None and "headneck_muscles" not in motor.tasks,
           motor.tasks if motor else None)
    checar(u"  e as da cabeca, sem cabeca nem pescoco no campo, saem pelo "
           u"portao de regiao",
           motor is not None and not ((set(_CP) - set(_pescoco))
                                      & set(motor.tasks)),
           motor.tasks if motor else None)

    ok, motor, mod, s, linhas = _rodar_anatomia(
        {"pelve"}, extra={"TASKS": "total_v3 head_glands_cavities"})
    checar(u"`head_glands_cavities` escrita no TASKS NAO roda numa pelve (a "
           u"decisao de 02/09: a anatomia decide)",
           motor is not None and "head_glands_cavities" not in motor.tasks,
           motor.tasks if motor else None)
    checar(u"  e o arranque diz que a chave TASKS e obsoleta (v8.4: o vigia "
           u"nao le task do config)",
           any(u"chave obsoleta ignorada: TASKS" in a
               for a in getattr(mod, "AVISOS_CFG", ())),
           [a for a in getattr(mod, "AVISOS_CFG", ()) if "TASKS" in a][:2])

    velha_pelve = MO.TASKS_POR_TOPOGRAFIA.get(MO.PELVE)
    MO.TASKS_POR_TOPOGRAFIA[MO.PELVE] = ("hip_implant",)
    try:
        ok, motor, mod, s, linhas = _rodar_anatomia({"pelve"})
    finally:
        MO.TASKS_POR_TOPOGRAFIA[MO.PELVE] = velha_pelve
    checar(u"ISCA: `hip_implant` posta na tabela da pelve NAO roda (nao "
           u"alimenta o FULL: plugin, so quando pedido)",
           motor is not None and "hip_implant" not in motor.tasks,
           motor.tasks if motor else None)
    checar(u"  e o log diz que ela e plugin",
           any(u"hip_implant" in l and u"plugin" in l for l in linhas))
    ok, motor, mod, s, linhas = _rodar_anatomia(
        {"pelve"}, extra={"TASKS": "total_v3 hip_implant"})
    checar(u"e escrita no TASKS ela NAO roda: o vigia e sempre AUTO, e o "
           u"ato declarado e a chave da task no PERSONALIZADO (v8.4)",
           motor is not None and "hip_implant" not in motor.tasks
           and motor.tasks[0] == "total_v3",
           motor.tasks if motor else None)

    velho_torax = MO.TASKS_POR_TOPOGRAFIA.get(MO.TORAX)
    MO.TASKS_POR_TOPOGRAFIA[MO.TORAX] = tuple(velho_torax) + ("lung_nodules",)
    try:
        ok, motor, mod, s, linhas = _rodar_anatomia({"torax"})
    finally:
        MO.TASKS_POR_TOPOGRAFIA[MO.TORAX] = velho_torax
    checar(u"ISCA: `lung_nodules` posta na tabela do torax NUNCA chega ao "
           u"motor (REGRA A)",
           motor is not None and "lung_nodules" not in motor.tasks,
           motor.tasks if motor else None)
    checar(u"  e o vigia PAUSA, como erro de configuracao",
           mod.STATE["paused"] is True
           and u"achado" in mod.STATE["ambiente_erro"].lower(),
           mod.STATE["ambiente_erro"][:120])
    checar(u"  sem gastar tentativa da serie",
           not mod.has_marker(s["dir"], s["uid"], "fail"))

    import ast as _ast
    fonte = io.open(_componentes.fonte("app/radai_watcher.py"),
                    encoding="utf-8").read()
    ps = [n for n in _ast.walk(_ast.parse(fonte))
          if isinstance(n, _ast.FunctionDef) and n.name == "process_series"]
    nomes = set()
    if ps:
        for n in _ast.walk(ps[0]):
            if isinstance(n, _ast.Call):
                f = n.func
                nomes.add(getattr(f, "id", None) or getattr(f, "attr", None))
    g = _ganchos_da_lista(fonte)
    no_laco = {"_tasks_pela_anatomia", "_bases"} <= g.get("depois_de", set())
    checar(u"`process_series` chama `_tasks_pela_anatomia` DENTRO do laco "
           u"das tasks (na mesma serie: caso completo antes de parcial) -- o "
           u"gancho `depois_de` do primitivo, so depois da base",
           no_laco, str(sorted(g.get("depois_de", set())))[:200])
    _isca = fonte.replace("depois_de=_depois_de, ", "")
    checar(u"  ISCA: sem o `depois_de=` na chamada do primitivo, a leitura "
           u"acusa", _isca != fonte
           and "depois_de" not in _ganchos_da_lista(_isca))
    checar(u"  e nao chama mais `tasks_de` (o texto nao decide)",
           "tasks_de" not in nomes, sorted(x for x in nomes if x)[:5])


def teste_a_escada_de_recuperacao():
    secao(u"E3: a escada de recuperacao (recurso e trava nao gastam)")
    mod, _r, _b = montar([])
    try:
        raise RuntimeError("conjunto entregue (FULL/OAR) nao saiu: "
                           "MemoryError") from MemoryError()
    except RuntimeError as e:
        embrulhado = e
    casos = [
        (MemoryError(), mod.RECURSO, u"MemoryError"),
        (embrulhado, mod.RECURSO, u"RuntimeError com MemoryError na cadeia"),
        (RuntimeError("RuntimeError: not enough memory: 12907446880 bytes"),
         mod.RECURSO, u"o texto do log da clinica (02/09)"),
        (RuntimeError("numpy.core._exceptions._ArrayMemoryError: Unable to "
                      "allocate 3.2 GiB"), mod.RECURSO, u"numpy"),
        (RuntimeError("torch.OutOfMemoryError: CUDA out of memory"),
         mod.RECURSO, u"VRAM"),
        (RuntimeError("TS total passou do tempo limite (10800 s) e foi "
                      "encerrada."), mod.TRAVOU, u"o tempo limite do motor"),
        (ValueError("serie corrompida"), mod.DETERMINISTICO, u"determinista"),
        (RuntimeError("nenhuma estrutura gerada"), mod.DETERMINISTICO,
         u"nenhuma estrutura"),
        (RuntimeError("DICOM memory card mount failed"), mod.DETERMINISTICO,
         u"ISCA: 'memory' em outro sentido"),
    ]
    _TT = _motor_do_teste().TaskTravada
    _trav = _TT("total_v3", "sem_pulso", {"sem_pulso_s": 900.0},
                tentativa=2)
    try:
        raise RuntimeError("conjunto nao saiu") from _TT(
            "total_v3", "paginando", {"ram_pct": 97.0})
    except RuntimeError as e:
        _trav_emb = e
    casos += [
        (_trav, mod.TRAVOU, u"engine.TaskTravada (a base, duas vezes)"),
        (_trav_emb, mod.TRAVOU, u"TaskTravada na cadeia (__cause__)"),
        (RuntimeError(u"TS breasts TRAVADA (sem pulso) e foi encerrada: sem "
                      u"pulso do envelope"), mod.TRAVOU,
         u"a palavra TRAVADA no texto (o tipo perdido)"),
        (RuntimeError(u"a pasta estava travada por outro programa"),
         mod.DETERMINISTICO, u"ISCA: «travada» minusculo, de outra coisa"),
    ]
    for e, esperado, nome in casos:
        checar(u"classificar: %s -> %s" % (nome, esperado),
               mod.classificar_erro(e) == esperado, mod.classificar_erro(e))
    _FA = _app_import("radai_falhas")
    _velhos = (_FA.TIPOS_DE_TRAVA, _FA.PALAVRA_DA_TRAVA)
    _FA.TIPOS_DE_TRAVA, _FA.PALAVRA_DA_TRAVA = (), u"\x00nunca"
    try:
        _cl = mod.classificar_erro(_trav)
    finally:
        _FA.TIPOS_DE_TRAVA, _FA.PALAVRA_DA_TRAVA = _velhos
    checar(u"ISCA: sem o ramo da trava, a base travada vira %s (gastaria "
           u"tentativa)" % mod.DETERMINISTICO,
           _cl == mod.DETERMINISTICO, _cl)

    agora = datetime.now()
    cfg = {"DRY_RUN": "0", "TASKS": "total_v3", "INCLUIR_NV": "0",
           "INCLUIR_CADS": "0", "INCLUIR_MOOSE": "0", "INCLUIR_HNLNL": "0"}
    mod, root, base = montar([("PAC_VELHA", agora - timedelta(days=3), 8),
                              ("PAC_NOVA", agora - timedelta(days=1), 8)],
                             extra=cfg)
    envelhecer(root, 60)
    fila, _ = fila_de(mod)
    if len(fila) != 2:
        checar(u"as duas series entraram na fila", False, len(fila))
        return
    nova = [x for x in fila if x["pid"] == "PAC_NOVA"][0]
    checar(u"sem adiamento, a mais recente e a primeira da fila (a ordem de "
           u"sempre)", fila[0]["pid"] == "PAC_NOVA", pids_da_fila(fila))
    mod.carregar_engine = lambda: _MotorAnatomico(
        base, set(), erro_na={"total_v3": MemoryError()})
    mod.claim(nova["dir"], nova["uid"], {})
    ok = mod.process_series(nova)
    fl = mod.read_marker(nova["dir"], nova["uid"], "fail") or {}
    checar(u"MemoryError: a serie nao conclui", ok is False, str(ok))
    checar(u"  e NAO gasta tentativa (tries continua 0)",
           int(fl.get("tries", -1)) == 0, fl)
    checar(u"  e o motivo nao fica em branco (MemoryError nao tem mensagem: "
           u"vai o tipo)", fl.get("last_error") == "MemoryError",
           fl.get("last_error"))
    checar(u"  e conta como recurso, e fica adiada NESTA maquina",
           fl.get(mod.RECURSO) == 1
           and float((fl.get("adiada") or {}).get("PC_A", 0)) > time.time(),
           fl)
    fila2, _ = fila_de(mod)
    checar(u"  enquanto a espera nao passa, ela NAO entra na fila desta "
           u"maquina", pids_da_fila(fila2) == ["PAC_VELHA"],
           pids_da_fila(fila2))
    checar(u"  e NAO some calada: a varredura a conta como adiada",
           mod.STATE.get("adiadas") == 1, mod.STATE.get("adiadas"))
    plano = mod.plano_de_execucao()
    linha = [x for e in plano.get("exames") or [] for x in e.get("series") or []
             if x.get("uid") == nova["uid"]]
    checar(u"  e o plano a mostra adiada, com a hora em que volta",
           linha and u"adiada" in (linha[0].get("detalhe") or u"")
           and linha[0].get("estado") == "a_fazer",
           linha[0] if linha else u"a linha sumiu do plano")
    mod_b = carregar(root, base, extra=cfg, machine="PC_B")
    fila_b, _ = fila_de(mod_b)
    checar(u"  outra maquina a ve na fila dela (a espera e por maquina)",
           "PAC_NOVA" in pids_da_fila(fila_b), pids_da_fila(fila_b))
    checar(u"    no FIM (ja estourou uma vez), atras da que nunca falhou",
           pids_da_fila(fila_b) == ["PAC_VELHA", "PAC_NOVA"],
           pids_da_fila(fila_b))
    fl["adiada"]["PC_A"] = time.time() - 1
    mod.m_path(nova["dir"], nova["uid"], "fail").write_text(
        json.dumps(fl), encoding="utf-8")
    fila3, _ = fila_de(mod)
    checar(u"passada a espera, ela VOLTA -- no fim da fila",
           pids_da_fila(fila3) == ["PAC_VELHA", "PAC_NOVA"],
           pids_da_fila(fila3))
    ordem_sem = mod._ordem_da_fila(list(fila3), [])
    checar(u"ISCA: sem a particao, ela seria a PRIMEIRA (a mais recente)",
           ordem_sem and ordem_sem[0]["pid"] == "PAC_NOVA",
           pids_da_fila(ordem_sem))
    checar(u"a espera cresce e tem teto (30 min, 60, ... ate 12 h)",
           mod.espera_do_adiamento_s(1) == 1800.0
           and mod.espera_do_adiamento_s(2) == 3600.0
           and mod.espera_do_adiamento_s(99) == 12 * 3600.0)

    velha = [x for x in fila if x["pid"] == "PAC_VELHA"][0]
    mod.carregar_engine = lambda: _MotorAnatomico(
        base, set(), erro_na={"total_v3": ValueError("serie corrompida")})
    mod.claim(velha["dir"], velha["uid"], {})
    mod.process_series(velha)
    fv = mod.read_marker(velha["dir"], velha["uid"], "fail") or {}
    checar(u"ISCA: erro deterministico GASTA tentativa (tries=1) e nao "
           u"adia", int(fv.get("tries", 0)) == 1 and not fv.get("adiada"), fv)
    mod.m_path(velha["dir"], velha["uid"], "fail").unlink()
    mod.carregar_engine = lambda: _MotorAnatomico(
        base, set(), erro_na={"total_v3": RuntimeError(
            "TS total_v3 passou do tempo limite (10800 s) e foi encerrada.")})
    mod.claim(velha["dir"], velha["uid"], {})
    mod.process_series(velha)
    ft = mod.read_marker(velha["dir"], velha["uid"], "fail") or {}
    checar(u"TRAVA (tempo limite): nao gasta tentativa, conta como travou e "
           u"adia", int(ft.get("tries", -1)) == 0 and ft.get(mod.TRAVOU) == 1
           and bool(ft.get("adiada")), ft)


def teste_o_lock_conta_onde_a_serie_esta():
    secao(u"E3: o lock conta onde a serie esta; o status sai no meio")
    visto = {}

    def ao_rodar(t, mod, s):
        if t == "trunk_cavities":
            visto["lock"] = mod.read_marker(s["dir"], s["uid"], "lock")
            visto["texto"] = mod.m_path(s["dir"], s["uid"], "lock").read_text(
                encoding="utf-8")
            visto["pasta"] = s["dir"]
            visto["pid"] = s.get("pid")

    ok, motor, mod, s, linhas = _rodar_anatomia({"torax"}, ao_rodar=ao_rodar)
    lk = visto.get("lock") or {}
    feito = lk.get("feito") or []
    checar(u"no meio da serie, o lock diz a etapa e o passo",
           bool(lk.get("etapa")) and "passo" in lk and "total" in lk, lk)
    checar(u"  e o que ja foi feito: a base, com maquina e dispositivo",
           any(f.get("task") == "total_v3" and f.get("dispositivo") == "cpu"
               for f in feito), feito)
    checar(u"  e continua sendo DESTA maquina (token intacto)",
           str(lk.get("token") or "").startswith("PC_A#"), lk.get("token"))
    checar(u"  sem caminho e sem o registro do paciente no marcador",
           visto.get("texto") and visto["pasta"] not in visto["texto"]
           and os.path.basename(visto["pasta"]) not in visto["texto"]
           and str(visto.get("pid")) not in visto["texto"],
           (visto.get("texto") or "")[:160])

    def contar(heartbeat_s):
        chamadas = []

        def ao_rodar2(t, mod, s):
            time.sleep(0.35)
        agora = datetime.now()
        cfg = {"DRY_RUN": "0", "TASKS": "total_v3", "INCLUIR_NV": "0",
               "INCLUIR_CADS": "0", "INCLUIR_MOOSE": "0",
               "INCLUIR_HNLNL": "0"}
        m, root, base = montar([("PAC_HB", agora - timedelta(days=1), 8)],
                               extra=cfg)
        envelhecer(root, 60)
        fila, _ = fila_de(m)
        s2 = fila[0]
        motor = _MotorAnatomico(base, set(),
                                ao_rodar=lambda t: ao_rodar2(t, m, s2))
        m.carregar_engine = lambda: motor
        m.HEARTBEAT_S = heartbeat_s
        m.salvar_status = lambda: chamadas.append(time.time())
        m.claim(s2["dir"], s2["uid"], {})
        m.process_series(s2)
        return len(chamadas)
    n_rapido = contar(0.05)
    n_lento = contar(300.0)
    checar(u"o batimento grava o sinal de vida DURANTE a serie (a frota nao "
           u"ve a estacao «parada» numa serie de 40 min)", n_rapido >= 3,
           n_rapido)
    checar(u"ISCA: com o batimento de 300 s, so a primeira batida cai na "
           u"serie", n_lento == 1, n_lento)

    m3, _r3, _b3 = montar([])
    m3._STATUS_SALVO[0] = time.time()
    checar(u"`_status_periodico` nao grava de novo antes do batimento",
           m3._status_periodico() is False)
    m3._STATUS_SALVO[0] = time.time() - m3.HEARTBEAT_S - 1
    checar(u"  e grava depois dele", m3._status_periodico() is True)
    import ast as _ast
    fonte = io.open(_componentes.fonte("app/radai_watcher.py"),
                    encoding="utf-8").read()
    uv = [n for n in _ast.walk(_ast.parse(fonte))
          if isinstance(n, _ast.FunctionDef) and n.name == "_uma_volta"]
    chama = uv and any(isinstance(c, _ast.Call)
                       and getattr(c.func, "id", "") == "_status_periodico"
                       for c in _ast.walk(uv[0]))
    checar(u"  e `_uma_volta` o chama (o vigia LIGADO com a fila vazia)",
           bool(chama))


def teste_a_primeira_entrega_vale():
    secao(u"E3: a primeira entrega vale")
    agora = datetime.now()
    mod, root, base = montar([("PAC_RES", agora - timedelta(days=1), 8)])
    envelhecer(root, 60)
    fila, _ = fila_de(mod)
    s = fila[0]
    mod.claim(s["dir"], s["uid"], {})
    pode, pq = mod.reservar_entrega(s["dir"], s["uid"])
    checar(u"sem ninguem, a reserva e desta maquina", pode is True, pq)
    checar(u"  e e reentrante (a mesma maquina reserva de novo)",
           mod.reservar_entrega(s["dir"], s["uid"])[0] is True)
    mod_b = carregar(root, base, machine="PC_B")
    pode_b, pq_b = mod_b.reservar_entrega(s["dir"], s["uid"])
    checar(u"outra maquina, com a reserva FRESCA de A: nao publica",
           pode_b is False and u"primeira entrega vale" in pq_b, pq_b)
    ep = mod.m_path(s["dir"], s["uid"], mod.ENTREGA)
    d = json.loads(ep.read_text(encoding="utf-8"))
    d["heartbeat"] = time.time() - 3600
    ep.write_text(json.dumps(d), encoding="utf-8")
    pode_b2, _pq = mod_b.reservar_entrega(s["dir"], s["uid"])
    checar(u"reserva VELHA (A caiu no meio da publicacao): B toma e publica",
           pode_b2 is True
           and (mod.read_marker(s["dir"], s["uid"], mod.ENTREGA) or {})
           .get("machine") == "PC_B")
    mod.soltar_entrega(s["dir"], s["uid"])
    checar(u"A nao solta a reserva que agora e de B",
           mod.has_marker(s["dir"], s["uid"], mod.ENTREGA))
    mod_b.soltar_entrega(s["dir"], s["uid"])
    checar(u"B solta a dela", not mod.has_marker(s["dir"], s["uid"],
                                                 mod.ENTREGA))
    mod.m_path(s["dir"], s["uid"], "done", criar=True).write_text(
        json.dumps({"machine": "PC_B", "finished": "2026-09-24 03:00:00"}),
        encoding="utf-8")
    pode3, pq3 = mod.reservar_entrega(s["dir"], s["uid"])
    checar(u"com o `done` de outra maquina: nao publica, e diz quem entregou",
           pode3 is False and u"PC_B" in pq3, pq3)

    def outra_entregou(t, mod, s):
        mod.m_path(s["dir"], s["uid"], "done", criar=True).write_text(
            json.dumps({"machine": "PC_OUTRA",
                        "finished": "2026-09-24 03:00:00"}), encoding="utf-8")
    ok, motor, mod2, s2, linhas = _rodar_anatomia(set(),
                                                  ao_rodar=outra_entregou)
    checar(u"a outra maquina entregou no meio: esta NAO grava RTSTRUCT",
           motor is not None and motor.rts == [], motor.rts if motor else None)
    checar(u"  nem `fail`, e o log diz por que",
           not mod2.has_marker(s2["dir"], s2["uid"], "fail")
           and any(u"NAO publico" in l for l in linhas), linhas[-3:])
    checar(u"  e o `done` que fica e o da outra",
           (mod2.read_marker(s2["dir"], s2["uid"], "done") or {})
           .get("machine") == "PC_OUTRA")
    ok, motor, mod3, s3, linhas = _rodar_anatomia(set())
    checar(u"ISCA: sem o `done` da outra, a mesma serie publica",
           motor is not None and len(motor.rts) >= 1 and ok is True,
           motor.rts if motor else None)
    checar(u"  e a reserva sai depois do `done`",
           not mod3.has_marker(s3["dir"], s3["uid"], mod3.ENTREGA))

    def tomaram(t, mod, s):
        lp = mod.m_path(s["dir"], s["uid"], "lock")
        with mod._ESCRITA_DO_LOCK:
            d = json.loads(lp.read_text(encoding="utf-8"))
            d.update({"token": "PC_OUTRA#1", "machine": "PC_OUTRA"})
            velho = lp.with_name(lp.name + ".tomado.PC_OUTRA.1")
            os.replace(str(lp), str(velho))
            fd = os.open(str(lp), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            with os.fdopen(fd, "w") as f:
                json.dump(d, f)
            os.remove(str(velho))
    ok, motor, mod4, s4, linhas = _rodar_anatomia(set(), ao_rodar=tomaram)
    checar(u"lock tomado e ninguem entregou: publica (chegou primeiro) e diz",
           motor is not None and len(motor.rts) >= 1
           and any(u"o lock agora e de `PC_OUTRA`" in l for l in linhas),
           [l for l in linhas if "lock" in l][:2])
    checar(u"  e o `unclaim` NAO apaga o lock da outra",
           (mod4.read_marker(s4["dir"], s4["uid"], "lock") or {})
           .get("token") == "PC_OUTRA#1")


class _JsonComCorrida(object):

    def __init__(self, real, gancho):
        self._real, self._gancho, self.feito = real, gancho, False

    def __getattr__(self, nome):
        return getattr(self._real, nome)

    def loads(self, *a, **kw):
        d = self._real.loads(*a, **kw)
        if not self.feito and isinstance(d, dict) and "token" in d:
            self.feito = True
            self._gancho()
        return d


def _corrida_do_batimento(mod, mod_b, s, renovar):
    lp = mod.m_path(s["dir"], s["uid"], "lock")
    estado = {}

    def gancho():
        d = json.loads(lp.read_text(encoding="utf-8"))
        d["heartbeat"] = time.time() - 3600
        lp.write_text(json.dumps(d), encoding="utf-8")
        estado["b"] = mod_b.claim(s["dir"], s["uid"], {"machine": "PC_B"})
    real = mod.json
    mod.json = _JsonComCorrida(real, gancho)
    try:
        r = renovar(s["dir"], s["uid"])
    finally:
        mod.json = real
    tok = (mod.read_marker(s["dir"], s["uid"], "lock") or {}).get("token")
    return r, estado.get("b"), tok, mod_b.renovar_lock(s["dir"], s["uid"])


def teste_o_batimento_nao_regrava_o_lock_que_outra_tomou():
    secao(u"VIG-04: o batimento e a corrida do lock")
    agora = datetime.now()
    mod, root, base = montar([("PAC_COR", agora - timedelta(days=1), 8)])
    envelhecer(root, 60)
    fila, _ = fila_de(mod)
    s = fila[0]
    checar(u"A reivindica", mod.claim(s["dir"], s["uid"], {}) is True)
    mod_b = carregar(root, base, machine="PC_B")
    r, b, tok, b_renova = _corrida_do_batimento(mod, mod_b, s,
                                                mod.renovar_lock)
    duas_donas = bool(b) and bool(r)
    checar(u"nunca as duas donas: ou B tomou e A nao renovou, ou o contrario",
           not duas_donas, (r, b, tok))
    checar(u"o token no disco e o de quem a corrida diz que ficou",
           (b and tok and tok.startswith(u"PC_B#") and b_renova)
           or (not b and tok == mod._token()), (r, b, tok, b_renova))

    mod2, root2, base2 = montar([("PAC_COR2", agora - timedelta(days=1), 8)])

    def renovar_de_antes(sdir, uid):
        with mod2._ESCRITA_DO_LOCK:
            lp = mod2.m_path(sdir, uid, "lock")
            dado = mod2.read_marker(sdir, uid, "lock")
            if (not isinstance(dado, dict)
                    or dado.get("token") != mod2._token()):
                return False
            dado["heartbeat"] = time.time()
            mod2._regravar_sem_criar(lp, dado)
            return True
    envelhecer(root2, 60)
    s2 = fila_de(mod2)[0][0]
    mod2.claim(s2["dir"], s2["uid"], {})
    mod2_b = carregar(root2, base2, machine="PC_B")
    r2, b2, tok2, _b2 = _corrida_do_batimento(mod2, mod2_b, s2,
                                              renovar_de_antes)
    checar(u"ISCA: o batimento de antes deixa as duas donas",
           bool(r2) and bool(b2) and tok2 == mod2._token(), (r2, b2, tok2))

    mod3, root3, base3 = montar([("PAC_COR3", agora - timedelta(days=1), 8)])
    envelhecer(root3, 60)
    s3 = fila_de(mod3)[0][0]
    mod3.claim(s3["dir"], s3["uid"], {})
    lp3 = mod3.m_path(s3["dir"], s3["uid"], "lock")
    d3 = json.loads(lp3.read_text(encoding="utf-8"))
    d3.update({"token": "PC_OUTRA#7", "machine": "PC_OUTRA"})
    lp3.write_text(json.dumps(d3), encoding="utf-8")
    mod3.unclaim(s3["dir"], s3["uid"])
    checar(u"o `unclaim` devolve o lock que nao e dele",
           (mod3.read_marker(s3["dir"], s3["uid"], "lock") or {})
           .get("token") == "PC_OUTRA#7")
    sobras = [p.name for p in lp3.parent.iterdir() if ".soltando." in p.name]
    checar(u"  sem rastro do nome proprio", not sobras, sobras)
    d3["token"] = mod3._token()
    lp3.write_text(json.dumps(d3), encoding="utf-8")
    mod3.unclaim(s3["dir"], s3["uid"])
    checar(u"e apaga o que e dele",
           not mod3.has_marker(s3["dir"], s3["uid"], "lock")
           and not [p for p in lp3.parent.iterdir()
                    if ".soltando." in p.name])


def _marcadores_injetados(fonte):
    import ast as _ast
    for no in _ast.walk(_ast.parse(fonte)):
        if not isinstance(no, _ast.Dict):
            continue
        for k, v in zip(no.keys, no.values):
            if (getattr(k, "value", None) == "marcadores"
                    and isinstance(v, _ast.Dict)
                    and any(getattr(x, "value", None) == "claim"
                            for x in v.keys)):
                return dict((getattr(kk, "value", None),
                             getattr(vv, "id", None))
                            for kk, vv in zip(v.keys, v.values))
    return {}


def teste_o_lote_bate_a_reserva_de_entrega():
    secao(u"E3: o lote bate a reserva de entrega")
    agora = datetime.now()
    mod, root, base = montar([("PAC_REN", agora - timedelta(days=1), 8)])
    envelhecer(root, 60)
    fila, _ = fila_de(mod)
    s = fila[0]
    mod.claim(s["dir"], s["uid"], {})

    checar(u"sem reserva, `renovar_entrega` nao faz nada (e nao cria o "
           u"marcador)", mod.renovar_entrega(s["dir"], s["uid"]) is False
           and not mod.has_marker(s["dir"], s["uid"], mod.ENTREGA))
    mod.reservar_entrega(s["dir"], s["uid"])
    ep = mod.m_path(s["dir"], s["uid"], mod.ENTREGA)
    d = json.loads(ep.read_text(encoding="utf-8"))
    d["heartbeat"] = time.time() - 3600
    ep.write_text(json.dumps(d), encoding="utf-8")
    ok = mod.renovar_entrega(s["dir"], s["uid"])
    hb = float((mod.read_marker(s["dir"], s["uid"], mod.ENTREGA) or {})
               .get("heartbeat") or 0)
    checar(u"a reserva NOSSA, velha, volta a ser fresca",
           ok is True and time.time() - hb < 60, u"%.0f s" % (time.time() - hb))
    d = json.loads(ep.read_text(encoding="utf-8"))
    d.update({"token": "PC_OUTRA#1", "machine": "PC_OUTRA",
              "heartbeat": time.time() - 3600})
    ep.write_text(json.dumps(d), encoding="utf-8")
    ok = mod.renovar_entrega(s["dir"], s["uid"])
    hb = float((mod.read_marker(s["dir"], s["uid"], mod.ENTREGA) or {})
               .get("heartbeat") or 0)
    checar(u"  e a de OUTRA maquina nao e renovada por esta",
           ok is False and time.time() - hb > 3000,
           u"%s %.0f s" % (ok, time.time() - hb))

    try:
        import radai_batch as _L
        injetados = dict(_L._CFG.get("marcadores") or {})
    except Exception as e:
        injetados = {}
        checar(u"o painel montou o lote (pre-condicao)", False,
               u"%s: %s" % (type(e).__name__, e))
    checar(u"o lote recebe `renovar_entrega`, e e a funcao DO VIGIA",
           injetados.get("renovar_entrega") is mod.renovar_entrega,
           sorted(injetados))
    for k in ("reservar_entrega", "soltar_entrega", "lock_e_meu", "renovar",
              "resolver_done_afastado"):
        checar(u"  e `%s` continua indo junto" % k,
               injetados.get(k) is getattr(mod, {"renovar": "renovar_lock"}
                                           .get(k, k)), sorted(injetados))

    with io.open(_componentes.fonte("app/radai_watcher.py"),
                 encoding="utf-8") as f:
        fonte = f.read()
    lido = _marcadores_injetados(fonte)
    checar(u"por `ast`: o dicionario `marcadores` leva as quatro da entrega",
           all(lido.get(k) == k for k in ("reservar_entrega",
                                          "soltar_entrega", "lock_e_meu",
                                          "renovar_entrega")), str(lido))
    alvo = u'"renovar_entrega": renovar_entrega,'
    checar(u"  (isca) a linha esta onde a isca a procura", alvo in fonte)
    isca = _marcadores_injetados(fonte.replace(alvo, u""))
    checar(u"  (isca) sem a linha, a leitura acusa a falta",
           bool(isca) and "renovar_entrega" not in isca, str(isca))


def teste_o_lock_nao_renasce_e_o_vigia_nao_se_mata():
    secao(u"E4: o lock nao renasce, e o vigia nao se mata")
    agora = datetime.now()
    mod, root, base = montar([("PAC_LK", agora - timedelta(days=1), 8)])
    envelhecer(root, 60)
    fila, _ = fila_de(mod)
    s = fila[0]
    lp = mod.m_path(s["dir"], s["uid"], "lock", criar=True)

    def renovar_antigo(sdir, uid):
        try:
            lp2 = mod.m_path(sdir, uid, "lock")
            if not lp2.exists():
                return False
            dado = mod.read_marker(sdir, uid, "lock") or {}
            if dado.get("token") not in (None, mod._token()):
                return False
            dado["heartbeat"] = time.time()
            dado["token"] = mod._token()
            lp2.write_text(json.dumps(dado), encoding="utf-8")
            return True
        except Exception:
            return False

    lp.write_text(json.dumps({"machine": "ANTIGA", "heartbeat": 1.0}),
                  encoding="utf-8")
    checar(u"lock SEM token (versao antiga): NAO e renovado",
           mod.renovar_lock(s["dir"], s["uid"]) is False
           and "token" not in (mod.read_marker(s["dir"], s["uid"], "lock")
                               or {}))
    checar(u"ISCA: a renovacao da v8.1 o ADOTAVA (gravava o nosso token)",
           renovar_antigo(s["dir"], s["uid"]) is True
           and (mod.read_marker(s["dir"], s["uid"], "lock") or {})
           .get("token") == mod._token())
    ok = mod.renovar_lock(s["dir"], s["uid"],
                          extra={"etapa": "TS total_v3", "token": "INVASOR"})
    d = mod.read_marker(s["dir"], s["uid"], "lock") or {}
    checar(u"o lock nosso e renovado, com a etapa, e o `extra` nao troca o "
           u"dono", ok is True and d.get("etapa") == "TS total_v3"
           and d.get("token") == mod._token(), d)
    lp.unlink()
    checar(u"lock APAGADO (o unclaim passou): a renovacao NAO o recria",
           mod.renovar_lock(s["dir"], s["uid"]) is False and not lp.exists())
    lp.write_text(json.dumps({"token": mod._token()}), encoding="utf-8")
    real_read = mod.read_marker
    apagou = {}

    def some():
        try:
            lp.unlink()
            apagou["sim"] = True
        except Exception:
            apagou["sim"] = False

    def le_e_some(sdir, uid, kind):
        r = real_read(sdir, uid, kind)
        some()
        return r
    real_json = mod.json
    mod.json = _JsonComCorrida(real_json, some)
    try:
        novo = mod.renovar_lock(s["dir"], s["uid"])
        existe_novo = lp.exists()
        no_novo = dict(apagou)
    finally:
        mod.json = real_json
    mod.read_marker = le_e_some
    try:
        lp.write_text(json.dumps({"token": mod._token()}), encoding="utf-8")
        velho = renovar_antigo(s["dir"], s["uid"])
        existe_velho = lp.exists()
    finally:
        mod.read_marker = real_read
    checar(u"o lock apagado ENTRE a leitura e a escrita nao renasce",
           "sim" in no_novo and existe_novo is (not no_novo["sim"]),
           str((novo, existe_novo, no_novo)))
    checar(u"ISCA: a v8.1 o recriava (o lock orfao com o nosso nome)",
           velho is True and existe_velho, str((velho, existe_velho)))

    mortos = []

    class _Sub(object):
        DEVNULL = -3

        @staticmethod
        def run(cmd, **kw):
            mortos.append(list(cmd))

            class R(object):
                stdout = b""
                returncode = 0
            return R()
    real_sub = mod.subprocess
    real_img = mod._imagem_do_processo
    mod.subprocess = _Sub
    mod._imagem_do_processo = lambda pid: "python.exe"
    try:
        mod.LOG_DIR.mkdir(parents=True, exist_ok=True)
        mod.registrar_pid_local()
        checar(u"`_matar_travado` recusa o PROPRIO pid",
               mod._matar_travado(os.getpid(), s["uid"]) is False
               and not mortos, mortos)
        reg = mod.LOG_DIR / mod.PIDS_LOCAIS
        dados = json.loads(reg.read_text(encoding="utf-8"))
        dados.append({"pid": 999991, "quando": time.time()})
        reg.write_text(json.dumps(dados), encoding="utf-8")
        checar(u"ISCA: um pid registrado que NAO e o proprio e encerrado",
               mod._matar_travado(999991, s["uid"]) is True
               and any("999991" in c for c in mortos), mortos)
        del mortos[:]
        lp.write_text(json.dumps({
            "machine": mod.MACHINE, "pid_os": os.getpid(),
            "token": "%s#%d" % (mod.MACHINE, os.getpid()),
            "heartbeat": time.time() - 20 * 60}), encoding="utf-8")
        mod._SERIES_DESTE_PROCESSO.discard(s["uid"])
        tomou = mod.claim(s["dir"], s["uid"], {"machine": mod.MACHINE,
                                                "pid_os": os.getpid()})
        checar(u"lock orfao do PROPRIO processo: o `claim` retoma SEM matar",
               tomou is True and not mortos, mortos)
        mod.unclaim(s["dir"], s["uid"])
        lp.write_text(json.dumps({
            "machine": mod.MACHINE, "pid_os": os.getpid(),
            "token": "%s#%d" % (mod.MACHINE, os.getpid()),
            "heartbeat": time.time() - 20 * 60}), encoding="utf-8")
        mod._SERIES_DESTE_PROCESSO.add(s["uid"])
        est, _d = mod._diagnostico_do_lock(s["dir"], s["uid"])
        checar(u"ISCA: a serie que ESTE processo segura e «trabalhando» (nao "
               u"se retoma de si mesmo)",
               est == "trabalhando"
               and mod.claim(s["dir"], s["uid"], {}) is False, est)
        mod._SERIES_DESTE_PROCESSO.discard(s["uid"])
    finally:
        mod.subprocess = real_sub
        mod._imagem_do_processo = real_img


def teste_a_readocao_e_oar_e_full():
    secao(u"a readocao: OAR e FULL provam a entrega")
    mod, _r, _b = montar([])
    rc = _app_import("radai_sets")
    checar(u"CONJUNTOS_DE_PROVA: a primeira forma continua oar+full",
           tuple(mod.CONJUNTOS_DE_PROVA[0]) == ("oar", "full"),
           str(mod.CONJUNTOS_DE_PROVA))
    uid = "1.9.999.2.55.3.11111.45678901"
    d_oar = novo_temp()
    io.open(os.path.join(d_oar, rc.nome_do_arquivo("oar", "20260904",
                                                   uid[-8:])),
            "w").write(u"x")
    checar(u"ISCA: so o OAR NAO adota (a execucao que morreu entre o OAR e o "
           u"FULL)", mod.entrega_completa_no_disco(d_oar, uid) is False)
    io.open(os.path.join(d_oar, rc.nome_do_arquivo("full", "20260904",
                                                   uid[-8:])),
            "w").write(u"x")
    checar(u"  e com o FULL ao lado, adota",
           mod.entrega_completa_no_disco(d_oar, uid) is True)
    d = novo_temp()
    io.open(os.path.join(d, rc.nome_do_arquivo("full", "20260904", uid[-8:])),
            "w").write(u"x")
    checar(u"ISCA: so o FULL NAO adota", mod.entrega_completa_no_disco(
        d, uid) is False)
    io.open(os.path.join(d, rc.nome_do_arquivo("oar", "20260904", uid[-8:])),
            "w").write(u"x")
    checar(u"OAR e FULL, sem o TS cru: adota (ENTREGAR_TS=0 nao impede)",
           mod.entrega_completa_no_disco(d, uid) is True)


def teste_o_vigia_pula_o_que_o_fast_ja_fez():
    secao(u"v8.3: o vigia pula o que o FAST ja fez (done e readocao)")
    agora = datetime.now()
    rc = _app_import("radai_sets")
    mod, root, base = montar([("PAC_FAST", agora - timedelta(days=1), 8)])
    envelhecer(root, 60)
    checar(u"CONJUNTOS_DE_PROVA: (OAR e FULL) OU o OAR_Fast",
           tuple(tuple(f) for f in mod.CONJUNTOS_DE_PROVA)
           == (("oar", "full"), ("fast",)), str(mod.CONJUNTOS_DE_PROVA))
    series, dd = mod.scan_root()
    s = list(series.values())[0] if series else None
    if s is None:
        checar(u"a serie foi varrida", False)
        return
    done = {"uid": s["uid"], "date": s["date"], "machine": "PC_LOTE",
            "finished": agora.strftime("%Y-%m-%d %H:%M:%S"), "secs": 300,
            "rs": "", "tasks": ["total_v3"], "tasks_ok": ["total_v3"],
            "structures": [], "ver": "lote 8.3", "dry_run": False,
            "modo": "fast"}
    mod.m_path(s["dir"], s["uid"], "done", criar=True).write_text(
        json.dumps(done), encoding="utf-8")
    rs_do_done = os.path.join(s["dir"], rc.nome_do_arquivo(
        "full", (s["date"] or "")[:8] or rc.SEM_DATA, s["uid"][-8:]))
    with open(rs_do_done, "wb") as f:
        f.write(b"\0" * 200)
    fila, _ = fila_de(mod)
    checar(u"serie com `done` de FAST NAO entra na fila do vigia",
           s["uid"] not in [x["uid"] for x in fila], pids_da_fila(fila))
    src = io.open(_componentes.fonte("app/radai_watcher.py"), encoding="utf-8").read()
    i = src.find("\ndef build_queue(")
    corpo = src[i:src.find("\ndef ", i + 10)]
    errado = corpo.replace(
        'if has_marker(s["dir"], uid, "done"):',
        'if has_marker(s["dir"], uid, "done") and (read_marker(s["dir"], '
        'uid, "done") or {}).get("modo") != "fast":', 1)
    velho = mod.build_queue
    try:
        exec(compile(errado, "<isca_fast>", "exec"), mod.__dict__)
        fila_isca, _ = fila_de(mod)
    finally:
        mod.build_queue = velho
    checar(u"ISCA: a fila que so pula o done que nao e de FAST poe a serie de "
           u"volta (e o vigia a refaria)", errado != corpo
           and s["uid"] in [x["uid"] for x in fila_isca],
           pids_da_fila(fila_isca))
    mod.m_path(s["dir"], s["uid"], "done").unlink()
    os.remove(rs_do_done)
    io.open(os.path.join(s["dir"], rc.nome_do_arquivo(
        "fast", (s["date"] or "")[:8] or rc.SEM_DATA, s["uid"][-8:])),
        "w").write(u"x")
    envelhecer(root, 60)
    velha_prova = mod.CONJUNTOS_DE_PROVA
    try:
        mod.CONJUNTOS_DE_PROVA = (("oar", "full"),)
        fila_isca2, _ = fila_de(mod)
    finally:
        mod.CONJUNTOS_DE_PROVA = velha_prova
    checar(u"ISCA: com a prova da v8.2 (so OAR e FULL), a pasta com o "
           u"OAR_Fast NAO e readotada -- a serie voltaria a fila",
           s["uid"] in [x["uid"] for x in fila_isca2]
           and not mod.has_marker(s["dir"], s["uid"], "done"),
           pids_da_fila(fila_isca2))
    fila2, _ = fila_de(mod)
    d2 = mod.read_marker(s["dir"], s["uid"], "done") or {}
    checar(u"so o OAR_Fast na pasta, sem `done`: READOTA (sai da fila)",
           s["uid"] not in [x["uid"] for x in fila2]
           and d2.get("origem") == "readotado", str((pids_da_fila(fila2), d2)))
    checar(u"  e o `done` readotado diz modo=fast e o que achou no disco",
           d2.get("modo") == "fast"
           and d2.get("conjuntos_no_disco") == ["fast"], d2)
    d3 = novo_temp()
    uid = s["uid"]
    io.open(os.path.join(d3, rc.nome_do_arquivo("oar", "20260904", uid[-8:])),
            "w").write(u"x")
    checar(u"o OAR sozinho (sem FULL e sem ser o FAST) continua NAO adotando",
           mod.entrega_completa_no_disco(d3, uid) is False)
    checar(u"a forma devolvida: OAR+FULL vence quando os tres estao na pasta",
           mod.forma_da_prova({"oar", "full", "fast"}) == ("oar", "full")
           and mod.forma_da_prova({"fast"}) == ("fast",)
           and mod.forma_da_prova({"oar"}) is None)


def teste_o_done_afastado_que_ficou_orfao_e_resolvido():
    secao(u"v8.3 4b: o done afastado que ficou orfao e resolvido")
    agora = datetime.now()
    mod, root, base = montar([("PAC_ORFAO", agora - timedelta(days=1), 8)])
    envelhecer(root, 60)
    series, _dd = mod.scan_root()
    s = list(series.values())[0] if series else None
    if s is None:
        checar(u"a serie foi varrida", False)
        return
    uid, sdir = s["uid"], s["dir"]
    radai = os.path.join(sdir, "_RadAI")
    checar(u"a marca do rastro e a do `radai_batch._afastar_o_done`",
           getattr(mod, "MARCA_DO_DONE_AFASTADO", None)
           == u".done.json.substituido.")
    done_velho = {"uid": uid, "machine": "TARDE", "modo": "fast",
                  "finished": "2026-09-27 15:00:00", "date": "20260926"}

    def _rastro(sufixo, conteudo, idade_s=0):
        os.makedirs(radai, exist_ok=True)
        p = os.path.join(radai, "%s.done.json.substituido.%s" % (uid, sufixo))
        io.open(p, "w", encoding="utf-8").write(
            json.dumps(conteudo, ensure_ascii=False))
        if idade_s:
            t = time.time() - idade_s
            os.utime(p, (t, t))
        return p

    def _limpar():
        shutil.rmtree(radai, ignore_errors=True)

    def _rastros():
        try:
            return sorted(n for n in os.listdir(radai)
                          if u".done.json.substituido." in n)
        except OSError:
            return []
    linhas = []
    velho_wlog = mod.wlog
    mod.wlog = lambda m="": linhas.append(str(m))
    try:
        _limpar()
        _rastro(u"LOTE.4242", done_velho)
        checar(u"(o rastro sozinho nao e marcador: `has_marker` nao o ve)",
               not mod.has_marker(sdir, uid, "done"))
        mod.scan_root()
        d1 = mod.read_marker(sdir, uid, "done") or {}
        checar(u"sem `done` e sem lock, o rastro VOLTA a ser o `done` (a "
               u"serie fica como estava antes do pedido)",
               not _rastros() and d1.get("machine") == "TARDE"
               and d1.get("modo") == "fast", u"%s | %s" % (_rastros(), d1))
        checar(u"  e o `done` devolvido e o de antes, sem chave nova (a "
               u"Politica diz o que o de conclusao guarda)", d1 == done_velho,
               str(d1))
        checar(u"  e o log manda conferir a pasta, sem caminho e sem o UID "
               u"inteiro", any(u"interrompida" in l and u"Confira a pasta" in l
                               and uid[-8:] in l and uid not in l
                               and sdir not in l for l in linhas),
               u" | ".join(linhas[-2:]))
        _limpar()
        mod.m_path(sdir, uid, "done", criar=True).write_text(
            json.dumps({"uid": uid, "machine": "NOITE", "modo": "auto"}),
            encoding="utf-8")
        _rastro(u"LOTE.4242", done_velho)
        mod.scan_root()
        d2 = mod.read_marker(sdir, uid, "done") or {}
        checar(u"com o `done` novo gravado, o rastro sai e o `done` fica",
               not _rastros() and d2.get("machine") == "NOITE",
               u"%s | %s" % (_rastros(), d2))
        _limpar()
        _rastro(u"A.1", dict(done_velho, machine="PRIMEIRA"), idade_s=7200)
        _rastro(u"B.2", dict(done_velho, machine="SEGUNDA"), idade_s=60)
        mod.scan_root()
        d3 = mod.read_marker(sdir, uid, "done") or {}
        checar(u"dois rastros (duas quedas): o mais novo volta, o outro sai",
               not _rastros() and d3.get("machine") == "SEGUNDA",
               u"%s | %s" % (_rastros(), d3))
        _limpar()
        mod.m_path(sdir, uid, "lock", criar=True).write_text(
            json.dumps({"machine": "OUTRA", "heartbeat": time.time()}),
            encoding="utf-8")
        _rastro(u"OUTRA.7", done_velho)
        _s4, dd4 = mod.scan_root()
        checar(u"com o lock `trabalhando` (o «Substituir» vivo), o rastro nao "
               u"e tocado, e nao vira `done`", _rastros()
               and not mod.has_marker(sdir, uid, "done"), str(_rastros()))
        checar(u"  e o que sobra nao e lido como marcador: a varredura das "
               u"datas nao ve a data de dentro dele",
               u"20260926" not in (dd4 or []), str(dd4))
        _src4 = io.open(_componentes.fonte("app/radai_watcher.py"),
                        encoding="utf-8").read()
        _i4 = _src4.find("\ndef scan_root(")
        _c4 = _src4[_i4:_src4.find("\ndef ", _i4 + 10)]
        _velho4 = mod.scan_root
        try:
            exec(compile(_c4.replace('fn.endswith(".done.json")',
                                     '".done.json" in fn'),
                         "<isca-le-rastro>", "exec"), mod.__dict__)
            _s4i, dd4i = mod.scan_root()
        finally:
            mod.scan_root = _velho4
        checar(u"    (isca) lendo por «contem .done.json», a data do rastro "
               u"entraria -- a checagem discrimina",
               'fn.endswith(".done.json")' in _c4
               and u"20260926" in (dd4i or []), str(dd4i))
        mod.m_path(sdir, uid, "lock").write_text(
            json.dumps({"machine": "OUTRA",
                        "heartbeat": time.time() - mod.LOCK_PARADO_S - 60}),
            encoding="utf-8")
        mod.scan_root()
        checar(u"com o lock parado (a publicadora caiu), o rastro e resolvido",
               not _rastros() and mod.has_marker(sdir, uid, "done"),
               str(_rastros()))
        _limpar()
        _rastro(u"LOTE.4242", done_velho)
        src = io.open(_componentes.fonte("app/radai_watcher.py"),
                      encoding="utf-8").read()
        i = src.find("\ndef scan_root(")
        corpo = src[i:src.find("\ndef ", i + 10)]
        chamada = u"resolver_done_afastado(os.path.dirname(dirpath), _u_af)"
        velho = mod.scan_root
        try:
            exec(compile(corpo.replace(chamada, u"None"), "<isca-orfao>",
                         "exec"), mod.__dict__)
            mod.scan_root()
            isca = _rastros()
        finally:
            mod.scan_root = velho
        checar(u"  (isca) sem a chamada na varredura, o rastro fica para "
               u"sempre -- a checagem discrimina", chamada in corpo
               and bool(isca), str(isca))
    finally:
        mod.wlog = velho_wlog
        _limpar()
    src = io.open(_componentes.fonte("app/radai_watcher.py"), encoding="utf-8").read()
    checar(u"o vigia injeta a regra no lote (`resolver_done_afastado` nos "
           u"marcadores do «Rodar agora»)",
           re.search(r'"resolver_done_afastado":\s*resolver_done_afastado\b',
                     src) is not None)


def teste_o_portao_do_host():
    secao(u"E5: o portao do Host e o teto do corpo")
    import asyncio
    mod, _r, _b = montar([])

    async def app_min(scope, receive, send):
        corpo = b""
        while True:
            m = await receive()
            if m.get("type") == "http.disconnect":
                corpo = b"<desconectou>"
                break
            corpo += m.get("body") or b""
            if not m.get("more_body"):
                break
        await send({"type": "http.response.start", "status": 200,
                    "headers": []})
        await send({"type": "http.response.body",
                    "body": b"ok:" + str(len(corpo)).encode()})

    def pedir(app, host, corpo=b"", cl=True, pedacos=1):
        cab = [(b"host", host.encode())] if host is not None else []
        if cl:
            cab.append((b"content-length", str(len(corpo)).encode()))
        scope = {"type": "http", "method": "POST", "path": "/api/x",
                 "headers": cab}
        fatias = [corpo[i::pedacos] for i in range(pedacos)] if corpo else [b""]
        fila_msgs = [{"type": "http.request", "body": f,
                      "more_body": i < len(fatias) - 1}
                     for i, f in enumerate(fatias)]
        enviado = []

        async def receive():
            return fila_msgs.pop(0) if fila_msgs else {
                "type": "http.disconnect"}

        async def send(m):
            enviado.append(m)
        asyncio.run(app(scope, receive, send))
        st = [m for m in enviado if m["type"] == "http.response.start"]
        bd = b"".join(m.get("body", b"") for m in enviado
                      if m["type"] == "http.response.body")
        return (st[0]["status"] if st else 0), bd

    porta = 8777
    pt = mod.PortaoDoHost(app_min, porta=porta, teto=64)
    checar(u"127.0.0.1:porta passa", pedir(pt, "127.0.0.1:8777")[0] == 200)
    checar(u"localhost:porta passa (e sem diferenciar caixa)",
           pedir(pt, "LocalHost:8777")[0] == 200)
    for host in ("atacante.exemplo:8777", "127.0.0.1:8778", "127.0.0.1",
                 "", None, "127.0.0.1:8777.atacante.exemplo"):
        checar(u"Host %r: 403" % (host,), pedir(pt, host)[0] == 403)
    checar(u"ISCA: sem o portao, o Host estranho e atendido",
           pedir(app_min, "atacante.exemplo:8777")[0] == 200)
    st, _bd = pedir(pt, "127.0.0.1:8777", corpo=b"x" * 65)
    checar(u"corpo acima do teto, com Content-Length: 413", st == 413, st)
    st, bd = pedir(pt, "127.0.0.1:8777", corpo=b"x" * 65, cl=False, pedacos=3)
    checar(u"acima do teto SEM Content-Length (em pedacos): a rota nao le o "
           u"resto", bd == b"ok:13" or b"desconectou" in bd, bd)
    st, bd = pedir(pt, "127.0.0.1:8777", corpo=b"x" * 60)
    checar(u"abaixo do teto: passa inteiro", st == 200 and bd == b"ok:60",
           str((st, bd)))
    checar(u"o teto de fabrica e 16 MB",
           mod.TETO_DO_CORPO_BYTES == 16 * 1024 * 1024)

    import ast as _ast
    fonte = io.open(_componentes.fonte("app/radai_watcher.py"),
                    encoding="utf-8").read()

    def ordem_no_main(txt):
        arv = _ast.parse(txt)
        mn = [n for n in arv.body if isinstance(n, _ast.FunctionDef)
              and n.name == "main"]
        if not mn:
            return None
        linhas = {}
        for n in _ast.walk(mn[0]):
            if isinstance(n, _ast.Call):
                nome = (getattr(n.func, "id", None)
                        or getattr(n.func, "attr", None))
                linhas.setdefault(nome, n.lineno)
        return linhas
    lin = ordem_no_main(fonte) or {}
    checar(u"`main` liga a fila da estacao, monta o portao do Host e so "
           u"depois sobe o servidor",
           lin.get("_ligar_a_fila_da_estacao", 10 ** 9)
           < lin.get("montar_portao_do_host", -1)
           < lin.get("Server", -1), lin)
    isca = fonte.replace("    montar_portao_do_host(app, porta=PORT)\n", "")
    lin2 = ordem_no_main(isca) or {}
    checar(u"ISCA: sem a chamada, a checagem acusa",
           "montar_portao_do_host" not in lin2)


def teste_o_vigia_nao_segmenta_cada_fase_do_4d():
    secao(u"E2: o vigia nao segmenta cada fase do 4D (a AVG)")
    import pydicom
    agora = datetime.now()
    base = novo_temp()
    root = os.path.join(base, "share")
    estudo = "1.2.826.0.1.3680043.8.498.424242"
    descs = ["%d%%" % (10 * i) for i in range(10)] + ["AVG"]
    uids = {}
    for i, desc in enumerate(descs):
        d = os.path.join(root, "PAC_4D", "2026_SET_23_TC_4D", "S%03d" % (i + 2))
        uid = escreve_serie(d, "PAC_4D", agora - timedelta(days=1), 8)
        for fn in os.listdir(d):
            fp = os.path.join(d, fn)
            ds = pydicom.dcmread(fp)
            ds.StudyInstanceUID = estudo
            ds.SeriesDescription = desc
            ds.save_as(fp)
        uids[desc] = uid
    envelhecer(root, 60)
    mod = carregar(root, base)
    series, done = mod.scan_root()
    checar(u"a varredura le o estudo e a descricao de cada serie",
           all(sr.get("estudo") == estudo for sr in series.values())
           and sorted(sr.get("desc") for sr in series.values())
           == sorted(descs), str(sorted(sr.get("desc") for sr in
                                        series.values())))
    fila = mod.build_queue(series, done)
    checar(u"das onze series do 4D, a fila do vigia pega SO a AVG",
           [x["uid"] for x in fila] == [uids["AVG"]],
           [series[x["uid"]].get("desc") for x in fila])
    velhos = dict((u, dict((k, v) for k, v in sr.items()
                           if k not in ("estudo", "desc")))
                  for u, sr in series.items())
    fila_velha = mod.build_queue(velhos, done)
    checar(u"ISCA: sem o estudo e a descricao (a varredura da v8.1), as "
           u"ONZE vao para a fila", len(fila_velha) == 11, len(fila_velha))
    checar(u"e o indice local da varredura subiu de versao (as entradas "
           u"antigas nao tem estudo)", mod.CACHE_VERSAO >= 3, mod.CACHE_VERSAO)
    _pastas = {"PAC_X": {"mtime": 1.0, "series": {}}}
    _salvo = None
    try:
        _salvo = mod.CACHE_PATH.read_text(encoding="utf-8")
    except Exception:
        _salvo = None
    try:
        mod.CACHE_PATH.write_text(json.dumps(
            {"_v": mod.CACHE_VERSAO - 1, "pastas": _pastas}), encoding="utf-8")
        _velho = mod.cache_load()
        mod.CACHE_PATH.write_text(json.dumps(
            {"_v": mod.CACHE_VERSAO, "pastas": _pastas}), encoding="utf-8")
        _hoje = mod.cache_load()
    finally:
        if _salvo is not None:
            mod.CACHE_PATH.write_text(_salvo, encoding="utf-8")
        else:
            try:
                mod.CACHE_PATH.unlink()
            except Exception:
                pass
    checar(u"o indice de versao anterior volta VAZIO de `cache_load` (a "
           u"varredura rele com o estudo)", _velho == {}, str(_velho)[:80])
    checar(u"  (isca) o mesmo indice com a versao de hoje e lido",
           _hoje == _pastas, str(_hoje)[:80])
    _o_plano_diz_o_mesmo_que_a_fila(mod, uids, estudo)


def _plano_mutado(mod, trocas):
    import ast as _ast
    fonte = io.open(_componentes.fonte("app/radai_watcher.py"),
                    encoding="utf-8").read()
    no = next(n for n in _ast.parse(fonte).body
              if isinstance(n, _ast.FunctionDef)
              and n.name == "plano_de_execucao")
    trecho = _ast.get_source_segment(fonte, no)
    for de, para in trocas:
        if trecho.count(de) != 1:
            raise AssertionError(u"a isca nao casa: %r" % de)
        trecho = trecho.replace(de, para)
    ns = dict(mod.__dict__)
    exec(compile(trecho, "<plano_mutado>", "exec"), ns)
    return ns["plano_de_execucao"]


def _o_plano_diz_o_mesmo_que_a_fila(mod, uids, estudo):
    secao(u"a previa (plano) diz o mesmo que a fila: o 4D e dois estudos "
          u"numa pasta")
    import pydicom

    def _4d(plano):
        linhas = [x for e in plano.get("exames") or []
                  for x in e.get("series") or []]
        por = dict((x["uid"], x) for x in linhas)
        fases = [por.get(uids[d]) for d in uids if d != "AVG"]
        avg = por.get(uids["AVG"]) or {}
        return linhas, fases, avg

    plano = mod.plano_de_execucao()
    linhas, fases, avg = _4d(plano)
    checar(u"4D: o plano mostra as onze series num exame SO (o estudo)",
           len(plano.get("exames") or []) == 1 and len(linhas) == 11,
           [len(e.get("series") or []) for e in plano.get("exames") or []])
    checar(u"  a AVG e `a_fazer` e marcada como a escolhida (como na fila)",
           avg.get("estado") == "a_fazer" and avg.get("escolhida") is True,
           avg)
    checar(u"  as dez fases saem `pulado` com o motivo do 4D (a AVG), e nao "
           u"«nenhuma serie chega a 1 mm»",
           all(f and f.get("estado") == "pulado"
               and u"4D" in (f.get("detalhe") or u"")
               and u"AVG" in (f.get("detalhe") or u"")
               and u"chega a 1 mm" not in (f.get("detalhe") or u"")
               for f in fases),
           [(f or {}).get("detalhe") for f in fases][:1])
    checar(u"  e o resumo bate com a fila (1 a fazer, 10 pulados)",
           plano["resumo"]["a_fazer"] == 1 and plano["resumo"]["pulados"] == 10,
           plano["resumo"])

    so_pasta = _plano_mutado(mod, [(
        u"_chave_do_exame = _chave_do_exame_da_fila()",
        u"_chave_do_exame = lambda sr: str(sr['dir'])")])
    _l, fases_isca, _a = _4d(so_pasta())
    checar(u"ISCA: agrupando por PASTA (o resto certo), o motivo das fases "
           u"deixa de ser o do 4D",
           not all(f and u"AVG" in (f.get("detalhe") or u"")
                   for f in fases_isca),
           [(f or {}).get("detalhe") for f in fases_isca][:1])

    agora = datetime.now()
    base = novo_temp()
    root = os.path.join(base, "share")
    pasta = os.path.join(root, "PAC_2EST", "plana")
    os.makedirs(pasta)
    for sub, est, dias in (("tmpa", "1.2.826.0.1.3680043.8.498.111", 2),
                           ("tmpb", "1.2.826.0.1.3680043.8.498.222", 1)):
        d = os.path.join(base, sub)
        escreve_serie(d, "PAC_2EST", agora - timedelta(days=dias), 8)
        for fn in os.listdir(d):
            ds = pydicom.dcmread(os.path.join(d, fn))
            ds.StudyInstanceUID = est
            ds.save_as(os.path.join(pasta, "%s_%s" % (sub, fn)))
    envelhecer(root, 60)
    mod2 = carregar(root, base)
    mod2.wlog = lambda m="": None
    s2, dn2 = mod2.scan_root()
    fila2 = mod2.build_queue(s2, dn2)
    p2 = mod2.plano_de_execucao()
    a_fazer = sorted(x["uid"] for e in p2.get("exames") or []
                     for x in e.get("series") or []
                     if x.get("estado") == "a_fazer")
    checar(u"dois estudos numa pasta: a fila contorna os dois",
           len(fila2) == 2, [x["uid"][-6:] for x in fila2])
    checar(u"  e o plano marca os DOIS `a_fazer` (a mesma lista da fila)",
           a_fazer == sorted(x["uid"] for x in fila2)
           and p2["resumo"]["a_fazer"] == 2,
           (a_fazer, p2["resumo"]))

    antigo = _plano_mutado(mod2, [
        (u"_chave_do_exame = _chave_do_exame_da_fila()",
         u"_chave_do_exame = lambda sr: str(sr['dir'])"),
        (u"elif uid not in escolhidas_sim:",
         u"elif uid != (do_exame[0] if do_exame else ''):")])
    p_isca = antigo()
    checar(u"ISCA: o plano de antes (por pasta, UMA por grupo) mostra o "
           u"segundo estudo como pulado -- a divergencia, reproduzida",
           p_isca["resumo"]["a_fazer"] == 1 and p_isca["resumo"]["pulados"] == 1,
           p_isca["resumo"])
    _l, fases_antigas, _a = _4d(_plano_mutado(mod, [
        (u"_chave_do_exame = _chave_do_exame_da_fila()",
         u"_chave_do_exame = lambda sr: str(sr['dir'])"),
        (u"elif uid not in escolhidas_sim:",
         u"elif uid != (do_exame[0] if do_exame else ''):")])())
    checar(u"ISCA: e no 4D o plano de antes explica as fases sem a AVG",
           not any(f and u"AVG" in (f.get("detalhe") or u"")
                   for f in fases_antigas),
           [(f or {}).get("detalhe") for f in fases_antigas][:1])


def _falhas_sem_traceback(fonte, funcoes):
    import ast as _ast
    marcas = (u"nao rodou", u"nao rodaram", u"falhou", u"nao consegui gravar",
              u"nao consegui rodar", u"FALHOU", u"ADIADA")
    fora = []
    for no in _ast.walk(_ast.parse(fonte)):
        if not (isinstance(no, _ast.FunctionDef) and no.name in funcoes):
            continue
        for h in _ast.walk(no):
            if not isinstance(h, _ast.ExceptHandler):
                continue
            frases = []
            for c in _ast.walk(h):
                if (isinstance(c, _ast.Call)
                        and getattr(c.func, "id", "") == "wlog"):
                    for k in _ast.walk(c):
                        if (isinstance(k, _ast.Constant)
                                and isinstance(k.value, str)):
                            frases.append(k.value)
            if not any(m in f for f in frases for m in marcas):
                continue
            tem_tb = any(isinstance(c, _ast.Attribute)
                         and c.attr == "format_exc" for c in _ast.walk(h))
            if not tem_tb:
                fora.append((no.name, h.lineno, (frases or [u""])[0][:50]))
    return fora


def teste_as_falhas_da_serie_levam_o_traceback():
    secao(u"E4: as falhas da serie levam o traceback inteiro")
    fonte = io.open(_componentes.fonte("app/radai_watcher.py"),
                    encoding="utf-8").read()
    funcoes = ("process_series", "_entregar_motores", "_tasks_pela_anatomia")
    sem = _falhas_sem_traceback(fonte, funcoes)
    checar(u"nenhum `except` que anuncia falha da serie fica sem o traceback",
           not sem, str(sem))
    alvo = (u"                        try:\n"
            u"                            for _l in traceback.format_exc()"
            u".strip().splitlines():\n"
            u"                                wlog(\"   \" + _l)\n"
            u"                        except Exception:\n"
            u"                            pass\n\n"
            u"                marcar_etapa(\"montando o FULL e o STUDY\"")
    isca = fonte.replace(alvo, u"\n                marcar_etapa("
                         u"\"montando o FULL e o STUDY\"", 1)
    sem2 = _falhas_sem_traceback(isca, funcoes)
    checar(u"ISCA: o `except` dos niveis cervicais sem o traceback e acusado, "
           u"com a linha",
           alvo in fonte and any(u"niveis cervicais" in f
                                 for _n, _l, f in sem2),
           str(sem2))


def teste_o_complemento_de_regiao_nao_derruba_a_serie():
    secao(u"o complemento de regiao que falha nao derruba a serie")
    nada = RuntimeError("TS breasts rodou mas nenhuma estrutura conhecida "
                        "apareceu no volume")
    ok, motor, mod, s, linhas = _rodar_anatomia(
        {"torax"}, erro_na={"breasts": nada})
    if motor is None:
        checar(u"a serie entrou na fila", False)
        return
    done = mod.read_marker(s["dir"], s["uid"], "done") or {}
    checar(u"`breasts` falhou e a serie SAI (o FULL e o OAR da base)",
           ok is True and len(motor.rts) >= 1, str((ok, len(motor.rts))))
    checar(u"  as outras do torax rodaram depois dela",
           motor.tasks == ["total_v3"] + list(_TORAX), motor.tasks)
    checar(u"  e o `done` diz que ela falhou, com o motivo",
           any(f.get("task") == "breasts" and u"nenhuma estrutura" in
               (f.get("erro") or u"") for f in done.get("tasks_falharam") or []),
           done.get("tasks_falharam"))
    checar(u"  e o log diz, com o traceback e na linha do OK",
           any(u"complemento de regiao FALHOU" in l for l in linhas)
           and any(u"Traceback" in l for l in linhas)
           and any(u"SEM o complemento de: breasts" in l for l in linhas))

    ok, motor, mod, s, linhas = _rodar_anatomia(
        {"torax"}, erro_na={"total_v3": RuntimeError(
            "TS total_v3 rodou mas nenhuma estrutura conhecida apareceu")})
    fl = mod.read_marker(s["dir"], s["uid"], "fail") or {}
    checar(u"ISCA: o mesmo erro na BASE derruba a serie (C5) e gasta "
           u"tentativa", ok is False and int(fl.get("tries", 0)) == 1, fl)

    ok, motor, mod, s, linhas = _rodar_anatomia(
        {"pelve"}, extra={"TASKS": "total_v3 hip_implant"},
        erro_na={"hip_implant": RuntimeError("quebrou de proposito")})
    checar(u"uma task escrita no TASKS do config nem roda (v8.4: o vigia e "
           u"sempre AUTO), entao nao derruba a serie",
           ok is True and motor is not None
           and "hip_implant" not in motor.tasks,
           (ok, motor.tasks if motor else None))

    ok, motor, mod, s, linhas = _rodar_anatomia(
        {"torax"}, erro_na={"breasts": MemoryError()})
    fl = mod.read_marker(s["dir"], s["uid"], "fail") or {}
    checar(u"ISCA: falta de MEMORIA no complemento NAO e engolida na 1a vez: "
           u"a serie inteira e adiada pela escada",
           ok is False and fl.get(mod.RECURSO) == 1
           and not mod.has_marker(s["dir"], s["uid"], "done"), fl)
    _o_complemento_tem_teto_na_escada(mod, s, motor, fl, linhas)


def _de_novo(mod, s, motor_velho, regioes, erro_na=None, machine="PC_A"):
    motor = _MotorAnatomico(motor_velho.pasta, regioes, erro_na=erro_na)
    mod.carregar_engine = lambda: motor
    linhas = []
    velho = mod.wlog

    def _wlog(m=""):
        linhas.append(str(m))
    mod.wlog = _wlog
    try:
        mod.claim(s["dir"], s["uid"], {"machine": machine,
                                       "pid_os": os.getpid()})
        ok = mod.process_series(s)
    finally:
        mod.wlog = velho
    return ok, motor, linhas


def _o_complemento_tem_teto_na_escada(mod, s, motor, fl1, linhas1):
    secao(u"a escada do complemento de regiao tem teto")
    checar(u"1a volta: o adiamento e contado NO complemento (breasts: 1), e o "
           u"log diz que ainda vai adiar",
           mod.adiamentos_do_complemento(fl1, "breasts") == 1
           and any(u"`breasts` do complemento" in l and u"adiamento 1 de 2" in l
                   for l in linhas1),
           (fl1.get(mod.ADIAMENTOS_DO_COMPLEMENTO),
            [l for l in linhas1 if u"complemento" in l][:2]))

    mem = {"breasts": MemoryError()}
    ok2, motor2, linhas2 = _de_novo(mod, s, motor, {"torax"}, mem)
    fl2 = mod.read_marker(s["dir"], s["uid"], "fail") or {}
    checar(u"2a volta: adiada de novo (breasts: 2), sem gastar tentativa",
           ok2 is False and mod.adiamentos_do_complemento(fl2, "breasts") == 2
           and int(fl2.get("tries", -1)) == 0
           and not mod.has_marker(s["dir"], s["uid"], "done"), fl2)
    checar(u"  e o log avisa que, se estourar de novo, a serie sai SEM ela",
           any(u"adiamento 2 de 2" in l and u"SEM ela" in l for l in linhas2),
           [l for l in linhas2 if u"complemento" in l][:2])

    ok3, motor3, linhas3 = _de_novo(mod, s, motor, {"torax"}, mem)
    fl3 = mod.read_marker(s["dir"], s["uid"], "fail") or {}
    done = mod.read_marker(s["dir"], s["uid"], "done") or {}
    falhas = done.get("tasks_falharam") or []
    checar(u"3a volta: a MESMA falta de memoria no complemento -- a serie SAI "
           u"com a base (FULL e OAR)",
           ok3 is True and len(motor3.rts) >= 1
           and mod.has_marker(s["dir"], s["uid"], "done"),
           (ok3, len(motor3.rts), linhas3[-3:]))
    checar(u"  as outras do torax rodaram depois dela (a serie nao parou)",
           motor3.tasks == ["total_v3"] + list(_TORAX), motor3.tasks)
    checar(u"  e o `done` diz a task, a CLASSE (recurso) e o teto",
           any(f.get("task") == "breasts" and f.get("classe") == mod.RECURSO
               and u"teto" in (f.get("erro") or u"") for f in falhas), falhas)
    checar(u"  e NAO ficou adiada: o `fail` sai junto com o `done`, e a "
           u"fila desta maquina nao a ve mais",
           not fl3 and not mod.adiamento_de(fl3)[0], fl3)
    checar(u"  e o log diz, na linha da falha e na do OK",
           any(u"complemento de regiao FALHOU" in l and u"teto" in l
               for l in linhas3)
           and any(u"SEM o complemento de: breasts" in l for l in linhas3),
           [l for l in linhas3 if u"complemento" in l][:3])

    trava = {"pleural_pericard_effusion": RuntimeError(
        "TS pleural_pericard_effusion passou do tempo limite (10800 s) e foi "
        "encerrada")}
    ok, motor, mod, s, linhas = _rodar_anatomia({"torax"}, erro_na=trava)
    checar(u"TRAVA no complemento, 1a volta: adiada (travou: 1)",
           ok is False and (mod.read_marker(s["dir"], s["uid"], "fail")
                            or {}).get(mod.TRAVOU) == 1)
    _de_novo(mod, s, motor, {"torax"}, trava)
    ok3, motor3, linhas3 = _de_novo(mod, s, motor, {"torax"}, trava)
    done = mod.read_marker(s["dir"], s["uid"], "done") or {}
    checar(u"  e na 3a volta sai com a base, com a classe `travou`",
           ok3 is True and any(
               f.get("task") == "pleural_pericard_effusion"
               and f.get("classe") == mod.TRAVOU
               for f in done.get("tasks_falharam") or []),
           (ok3, done.get("tasks_falharam")))

    base_mem = {"total_v3": MemoryError()}
    ok, motor, mod, s, linhas = _rodar_anatomia({"torax"}, erro_na=base_mem)
    _de_novo(mod, s, motor, {"torax"}, base_mem)
    ok3, motor3, linhas3 = _de_novo(mod, s, motor, {"torax"}, base_mem)
    fl = mod.read_marker(s["dir"], s["uid"], "fail") or {}
    checar(u"ISCA: a BASE com falta de memoria continua ADIANDO na 3a volta "
           u"(sem teto: a memoria pode sobrar depois)",
           ok3 is False and int(fl.get(mod.RECURSO, 0)) == 3
           and int(fl.get("tries", -1)) == 0
           and not fl.get(mod.ADIAMENTOS_DO_COMPLEMENTO)
           and not mod.has_marker(s["dir"], s["uid"], "done"), fl)

    ok, motor, mod, s, linhas = _rodar_anatomia({"torax"}, erro_na=mem)
    _de_novo(mod, s, motor, {"torax"}, mem)
    real = mod.complemento_ainda_adia
    mod.complemento_ainda_adia = lambda fl, task: True
    try:
        ok3, motor3, linhas3 = _de_novo(mod, s, motor, {"torax"}, mem)
    finally:
        mod.complemento_ainda_adia = real
    checar(u"ISCA: sem o teto, a 3a volta do complemento ainda adia a serie "
           u"inteira (o defeito, reproduzido)",
           ok3 is False and not mod.has_marker(s["dir"], s["uid"], "done"),
           ok3)


class _MotorComPassos(_MotorQueEntrega):

    def preparar_full(self, masks, **kw):
        m, meta = _MotorQueEntrega.preparar_full(self, masks, **kw)
        meta["tempos"] = [(u"pele e parede", 1.5)]
        return m, meta

    def build_rtstruct(self, stage, masks, **kw):
        meta = kw.get("meta")
        if isinstance(meta, dict):
            meta["etapas"] = [(u"serie, grade e imagem", 0.25),
                              (u"suavizacao (duas passadas) e compostos", 3.5)]
        return _MotorQueEntrega.build_rtstruct(self, stage, masks, **kw)


def _serie_com_passos(isca=None):
    RO = _app_import("radai_output")
    RG = _app_import("radai_records")
    agora = datetime.now()
    mod, root, base = montar([("PAC_PASSOS", agora - timedelta(days=1), 8)],
                             extra={"DRY_RUN": "0", "TASKS": "total_v3",
                                    "INCLUIR_NV": "0", "INCLUIR_CADS": "0",
                                    "INCLUIR_MOOSE": "0", "INCLUIR_HNLNL": "0",
                                    "ENTREGAR_TS": "0"})
    envelhecer(root, 60)
    fila, _ = fila_de(mod)
    if not fila:
        return None, [], [], {}, 0
    s = fila[0]
    motor = _MotorComPassos(base)
    mod.carregar_engine = lambda: motor
    mod.ler_topografia = lambda *a, **k: ["total"]
    locks, casos = [], []
    real_renovar = mod.renovar_lock

    def _renovar(sdir, uid, extra=None):
        locks.append(dict(extra or {}))
        return real_renovar(sdir, uid, extra=extra)

    def _registrar(*a, **k):
        casos.append(dict(k))
        return ""
    guardados = [(RG, "registrar_serie", RG.registrar_serie),
                 (RO, "etapas_do_caso", RO.etapas_do_caso)]
    mod.renovar_lock = _renovar
    RG.registrar_serie = _registrar
    if isca == "sem_etapas_do_caso":
        RO.etapas_do_caso = lambda etapas, passos, segundos=None: [
            dict(e) for e in (etapas or ()) if isinstance(e, dict)]
    try:
        mod.claim(s["dir"], s["uid"], {})
        ok = mod.process_series(s)
    finally:
        for obj, nome, val in guardados:
            setattr(obj, nome, val)
        mod.renovar_lock = real_renovar
    done = mod.read_marker(s["dir"], s["uid"], "done") or {}
    return ok, casos, locks, done, 5


def teste_os_passos_do_full_vao_ao_caso_e_nao_ao_lock():
    secao(u"os passos da cadeia do FULL vao ao caso, e nao ao lock nem ao done")
    RO = _app_import("radai_output")
    ok, casos, locks, done, n = _serie_com_passos()
    checar(u"a serie saiu pelo caminho de sucesso", ok is True, ok)
    if not checar(u"o vigia registrou UM caso", len(casos) == 1, len(casos)):
        return
    et = list(casos[0].get("etapas") or [])
    nomes = [e.get("etapa") for e in et]
    passos = [e for e in et if RO.e_passo(e)]
    checar(u"o caso leva os %d passos da cadeia, cada um com `parte_de`" % n,
           len(passos) == n
           and all(e.get(RO.PARTE_DE) for e in passos), nomes)
    i_pai = nomes.index(RO.PAI_DOS_PASSOS) if RO.PAI_DOS_PASSOS in nomes else -1
    checar(u"  logo depois da linha «FULL e OAR», que continua no caso",
           i_pai >= 0 and et[i_pai + 1:i_pai + 1 + n] == passos, nomes)
    checar(u"  e com os passos da montagem do FULL (prefixo `FULL:`)",
           any(str(p.get("etapa")).startswith(u"FULL: ") for p in passos),
           nomes)
    checar(u"  e a «serie inteira» fica no fim",
           nomes and nomes[-1] == "serie inteira", nomes)
    nomes_dos_passos = set(p.get("etapa") for p in passos)
    feitos = [f.get("task") for lk in locks for f in (lk.get("feito") or [])]
    checar(u"o lock (toda renovacao) NAO lista passo como task feita",
           locks and not (set(feitos) & nomes_dos_passos)
           and RO.PAI_DOS_PASSOS in feitos, sorted(set(feitos)))
    et_done = [e.get("etapa") for e in (done.get("etapas") or [])]
    checar(u"o `done` NAO lista passo, e tem a linha «FULL e OAR»",
           et_done and not (set(et_done) & nomes_dos_passos)
           and RO.PAI_DOS_PASSOS in et_done
           and not any(RO.PARTE_DE in e for e in done.get("etapas") or []),
           et_done)

    ok0, casos0, _l0, _d0, _n0 = _serie_com_passos(isca="sem_etapas_do_caso")
    et0 = list((casos0 or [{}])[0].get("etapas") or [])
    checar(u"ISCA: sem `etapas_do_caso`, o caso sai sem passo nenhum (o "
           u"defeito da revisao, reproduzido)",
           ok0 is True and et0 and not any(RO.e_passo(e) for e in et0),
           [e.get("etapa") for e in et0])

    mod = carregar(novo_temp(), novo_temp())
    topo = [{"etapa": "TS total_v3", "task": "total_v3", "segundos": 812.4,
             "maquina": "PC_A", "dispositivo": "cpu"},
            {"etapa": RO.PAI_DOS_PASSOS, "segundos": 90.0, "maquina": "PC_A",
             "dispositivo": "cpu"}]
    armada = RO.etapas_do_caso(topo, [
        {"etapa": u"pele e parede", "segundos": 1.5,
         RO.PARTE_DE: RO.PAI_DOS_PASSOS},
        {"etapa": u"FULL: suavizacao", "segundos": 3.5,
         RO.PARTE_DE: u"montagem e gravacao do FULL"}])
    info = {"etapas": armada, "tasks_ok": ["total_v3"],
            "tarefas": ["total_v3"], "dispositivo": "cpu"}

    def _medir():
        return ([f.get("task") for f in
                 mod._estado_para_o_lock(info).get("feito") or []],
                [e.get("etapa") for e in mod._etapas_do_done(info)])
    feito, do_done = _medir()
    checar(u"com passos na lista, o lock lista so as tasks de topo",
           feito == ["total_v3", RO.PAI_DOS_PASSOS], feito)
    checar(u"  e o `done` tambem", do_done == ["TS total_v3",
                                             RO.PAI_DOS_PASSOS], do_done)
    real = RO.sem_os_passos
    RO.sem_os_passos = lambda etapas: [e for e in (etapas or ())
                                       if isinstance(e, dict)]
    try:
        feito_i, done_i = _medir()
    finally:
        RO.sem_os_passos = real
    checar(u"ISCA: sem o filtro, o lock e o `done` listariam os 2 passos "
           u"como task feita", len(feito_i) == 4 and len(done_i) == 4,
           (feito_i, done_i))

    import ast as _ast
    fonte = io.open(_componentes.fonte("app/radai_watcher.py"),
                    encoding="utf-8").read()
    ps = [n for n in _ast.walk(_ast.parse(fonte))
          if isinstance(n, _ast.FunctionDef) and n.name == "process_series"]
    guarda, estende = False, []
    for no in (_ast.walk(ps[0]) if ps else ()):
        if (isinstance(no, _ast.Assign) and any(
                isinstance(t, _ast.Subscript)
                and getattr(t.value, "id", "") == "info"
                and getattr(t.slice, "value", None) == "passos_do_full"
                for t in no.targets)):
            guarda = True
        if (isinstance(no, _ast.Call)
                and isinstance(no.func, _ast.Attribute)
                and no.func.attr in ("extend", "__iadd__")
                and isinstance(no.func.value, _ast.Subscript)
                and getattr(no.func.value.value, "id", "") == "info"
                and getattr(no.func.value.slice, "value", None) == "etapas"):
            estende.append(no.lineno)
    checar(u"`process_series` guarda os passos em `info['passos_do_full']`",
           guarda)
    checar(u"  e NAO estende `info['etapas']` (o que o lock e o done leem)",
           not estende, estende)
    dn = [n for n in _ast.walk(_ast.parse(fonte))
          if isinstance(n, _ast.FunctionDef)
          and n.name in ("_estado_para_o_lock", "_etapas_do_done")]
    checar(u"o lock e o done perguntam ao filtro do topo (`_etapas_de_topo`)",
           len(dn) == 2 and all(any(
               isinstance(c, _ast.Call)
               and getattr(c.func, "id", "") == "_etapas_de_topo"
               for c in _ast.walk(f)) for f in dn))
    checar(u"  e o `done` de `process_series` sai de `_etapas_do_done`",
           bool(ps) and any(isinstance(c, _ast.Call)
                            and getattr(c.func, "id", "") == "_etapas_do_done"
                            for c in _ast.walk(ps[0])))


def teste_a_conferencia_conta_a_noite_da_anatomia():
    secao(u"a conferencia antes da noite conta o que a anatomia acrescenta")
    import ast as _ast
    import importlib.util as _iu
    import tempfile, shutil
    _sp = _iu.spec_from_file_location(
        "vigia_plano_noite", _componentes.fonte("app/radai_watcher.py"))
    W = _iu.module_from_spec(_sp)
    _sp.loader.exec_module(W)
    import radai_tasks as _rt
    import radai_topography as _tp
    base = tempfile.mkdtemp(prefix="radai_plano_")
    velho = (W.scan_root, W.ROOT, W.TASKS)
    try:
        exame = os.path.join(base, "EXAME_N")
        os.makedirs(exame)
        series = {"1.2.3.117": {"dir": exame, "count": 117, "pid": "P1",
                                "date": "20240101000000", "desc": "TC",
                                "modality": "CT", "espessura_mm": 3.75,
                                "mais_novo": 0}}
        W.ROOT = base
        W.scan_root = lambda: (series, [])
        W.TASKS = ["total_v3"]
        c = W.custo_da_noite_em_bases()
        esperado = 1.0 + sum(_rt.peso_em_bases(t)
                             for t in _tp.tasks_governadas("CT"))
        checar(u"o custo da noite: piso = a base; teto = a base e TODAS as "
               u"tasks da regiao, pelo peso medido",
               abs(c["piso"] - 1.0) < 1e-9
               and abs(c["teto"] - esperado) < 1e-9
               and "breasts" in c["tasks_da_regiao"]
               and "abdominal_muscles" not in c["tasks_da_regiao"]
               and "trunk_cavities" in c["tasks_da_regiao"], str(c))
        checar(u"  a `abdominal_muscles` pesa o que foi MEDIDO (mais de duas "
               u"bases), e nao uma task qualquer",
               _rt.peso_em_bases("abdominal_muscles") > 2.0,
               str(_rt.peso_em_bases("abdominal_muscles")))
        p = W.plano_de_execucao()
        checar(u"o plano guarda o TETO como o tempo provavel, e o piso ao lado",
               p.get("estimativa_min") and p.get("estimativa_piso_min")
               and p["estimativa_min"] > p["estimativa_piso_min"],
               u"%s / %s" % (p.get("estimativa_piso_min"),
                             p.get("estimativa_min")))
        checar(u"  e a tela recebe a faixa e as tasks da regiao",
               u"–" in (p.get("estimativa") or u"")
               and "breasts" in (p.get("estimativa_regiao") or []),
               str(p.get("estimativa")))
        fonte = io.open(_componentes.fonte("app/radai_watcher.py"),
                        encoding="utf-8").read()
        no = next(n for n in _ast.parse(fonte).body
                  if isinstance(n, _ast.FunctionDef)
                  and n.name == "plano_de_execucao")
        contas = [n for n in _ast.walk(no) if isinstance(n, _ast.Call)
                  and getattr(n.func, "attr", None) in ("estimativa",
                                                        "_estacao")]
        com_len = [n for n in contas for x in _ast.walk(n)
                   if isinstance(x, _ast.Call)
                   and getattr(x.func, "id", None) == "len"]
        checar(u"(ast) `plano_de_execucao` nao conta a noite por `len(...)` "
               u"na estimativa nem no disco",
               len(contas) >= 3 and not com_len,
               u"%d conta(s), %d com len" % (len(contas), len(com_len)))
        chama = any(isinstance(n, _ast.Call)
                    and getattr(n.func, "id", None)
                    == "custo_da_noite_em_bases" for n in _ast.walk(no))
        checar(u"  e chama `custo_da_noite_em_bases`", chama)
        _isca = _plano_mutado(W, [(u'a_fazer, _custo["teto"], _dev)',
                                   u'a_fazer, len(TASKS or ("total",)), _dev)')])
        pi = _isca()
        checar(u"ISCA: com `len(TASKS)` no lugar do teto, o tempo volta a ser "
               u"o de uma task so (a checagem sabe reprovar)",
               pi.get("estimativa_min") == pi.get("estimativa_piso_min"),
               u"%s / %s" % (pi.get("estimativa_piso_min"),
                             pi.get("estimativa_min")))
        import radai_review as _rv
        _est_velha = _rv._estacao
        vistos = []

        def _espiao(*a, **k):
            vistos.append(k.get("n_tasks"))
            return _est_velha(*a, **k)
        try:
            _rv._estacao = _espiao
            W.plano_de_execucao()
            n_ok = list(vistos)
            del vistos[:]
            _plano_mutado(W, [(u'n_tasks=_custo["n_teto"])',
                               u'n_tasks=1)')])()
            n_isca = list(vistos)
        finally:
            _rv._estacao = _est_velha
        checar(u"a conta de disco recebe o TETO de tasks da noite (%s)"
               % c.get("n_teto"), c.get("n_teto") in n_ok
               and (c.get("n_teto") or 0) > 1, str(n_ok))
        checar(u"ISCA: com `n_tasks=1`, a conta de disco recebe uma task so (a "
               u"checagem sabe reprovar)", c.get("n_teto") not in n_isca
               and 1 in n_isca, str(n_isca))
        W.scan_root = lambda: ({}, [])
        p0 = W.plano_de_execucao()
        checar(u"sem serie a fazer, a tela recebe UM numero e nenhuma lista "
               u"da regiao (o balao nao explica uma faixa que nao existe)",
               u"–" not in (p0.get("estimativa") or u"")
               and p0.get("estimativa_regiao") == [],
               u"%s | %s" % (p0.get("estimativa"),
                             p0.get("estimativa_regiao")))
        p0i = _plano_mutado(W, [(
            u"fora[\"estimativa_regiao\"] = ([] if _sem_faixa\n"
            u"                                     else list(_custo["
            u"\"tasks_da_regiao\"]))",
            u"fora[\"estimativa_regiao\"] = list(_custo[\"tasks_da_regiao\"])"
        )])()
        checar(u"ISCA: com a lista sempre preenchida, a checagem acusa (o "
               u"defeito da verificacao)",
               bool(p0i.get("estimativa_regiao")),
               str(p0i.get("estimativa_regiao")))
    finally:
        W.scan_root, W.ROOT, W.TASKS = velho
        shutil.rmtree(base, ignore_errors=True)


def _ciclo_em_uso_no_main(src):
    import ast as _ast
    arv = _ast.parse(src)
    fn = next((n for n in arv.body if isinstance(n, _ast.FunctionDef)
               and n.name == "main"), None)
    if fn is None:
        return [u"main() nao existe"]
    chamadas = []
    for no in _ast.walk(fn):
        if isinstance(no, _ast.Call):
            f = no.func
            nome = (f.id if isinstance(f, _ast.Name) else
                    f.attr if isinstance(f, _ast.Attribute) else u"")
            chamadas.append((nome, no.lineno))
    ini = [ln for n, ln in chamadas if n == "iniciar_sinalizacao"]
    fim = [ln for n, ln in chamadas if n == "encerrar_sinalizacao"]
    run = [ln for n, ln in chamadas if n == "run"]
    ruins = []
    if len(ini) != 1:
        ruins.append(u"iniciar_sinalizacao chamada %d vez(es)" % len(ini))
    elif not run or ini[0] > min(run):
        ruins.append(u"a sinalizacao nao sobe antes do servidor")
    no_ctrlc, dentro = False, set()
    for h in _ast.walk(fn):
        if (isinstance(h, _ast.ExceptHandler) and isinstance(h.type, _ast.Name)
                and h.type.id == "KeyboardInterrupt"):
            for c in _ast.walk(h):
                if (isinstance(c, _ast.Call)
                        and getattr(c.func, "id", "") == "encerrar_sinalizacao"):
                    no_ctrlc = True
                    dentro.add(c.lineno)
    if not no_ctrlc:
        ruins.append(u"o Ctrl+C nao apaga o arquivo")
    if not any(run and ln > max(run) and ln not in dentro for ln in fim):
        ruins.append(u"a saida limpa (depois do run) nao apaga o arquivo")
    return ruins


def teste_o_vigia_sinaliza_o_uso_e_apaga_na_saida():
    secao(u"em_uso.json: o vigia sinaliza enquanto vive, e apaga na saida")
    import atexit as _ax
    base = tempfile.mkdtemp(prefix="radai_t_uso_")
    root = os.path.join(base, "root")
    os.makedirs(root)
    w = carregar(root, base, machine="PC_USO")
    RC = _app_import("radai_cleaner")
    cam = RC.caminho_em_uso()
    checar(u"o endereco cai na LOCALAPPDATA do fantoma, e nao na da maquina",
           cam.startswith(base), cam)
    try:
        w.iniciar_sinalizacao()
        for _ in range(200):
            if os.path.isfile(cam):
                break
            time.sleep(0.05)
        checar(u"o vigia grava o em_uso.json ao subir", os.path.isfile(cam), cam)
        d = {}
        try:
            d = json.load(io.open(cam, encoding="utf-8"))
        except Exception:
            pass
        checar(u"o formato e o combinado (versao, app, atualizado, pids, porta, "
               u"segmentando)",
               set(d) == {"versao", "app", "atualizado", "pids", "porta",
                          "segmentando"} and d.get("versao") == 1
               and d.get("app") == "radioterapia-ai-local-suite", d)
        checar(u"  com o PID deste processo (o vigia) e a porta do config",
               os.getpid() in (d.get("pids") or [])
               and d.get("porta") == w.PORT, (d.get("pids"), d.get("porta")))
        checar(u"  e segmentando=False com a fila parada",
               d.get("segmentando") is False, d)
        with w.LOCK:
            w.STATE["current"] = {"pid": "X", "uid": "1.2.3.4.5"}
        try:
            w._sinalizar_em_uso_uma_vez()
            d2 = json.load(io.open(cam, encoding="utf-8"))
        finally:
            with w.LOCK:
                w.STATE["current"] = None
        checar(u"com serie em curso, segmentando=True",
               d2.get("segmentando") is True, d2)
        checar(u"  e nada de paciente no arquivo (nem o UID da serie)",
               "1.2.3.4.5" not in json.dumps(d2) and "X" not in json.dumps(d2),
               d2)
        w.encerrar_sinalizacao()
        checar(u"a saida limpa APAGA o arquivo", not os.path.exists(cam))
        time.sleep(0.3)
        checar(u"  e a renovacao em voo nao o recria depois",
               not os.path.exists(cam))
        checar(u"  e uma renovacao pedida depois da saida nao grava",
               w._sinalizar_em_uso_uma_vez() is False and not os.path.exists(cam))
        w._EM_USO_PARAR.clear()
        w._sinalizar_em_uso_uma_vez()
        w._EM_USO_PARAR.set()
        checar(u"ISCA: parar a renovacao sem apagar deixa o arquivo (e a "
               u"checagem ve)", os.path.exists(cam))
    finally:
        w._EM_USO_PARAR.set()
        try:
            _ax.unregister(w.encerrar_sinalizacao)
        except Exception:
            pass
        if cam.startswith(base):
            RC.apagar_em_uso(cam)
        shutil.rmtree(base, ignore_errors=True)
    src = io.open(_componentes.fonte("app/radai_watcher.py"), encoding="utf-8").read()
    checar(u"main(): sobe antes do servidor, apaga na saida limpa e no Ctrl+C",
           _ciclo_em_uso_no_main(src) == [], _ciclo_em_uso_no_main(src))
    _isca = src.replace(u"    encerrar_sinalizacao()\n    wlog(\"vigia encerrado.\")",
                        u"    wlog(\"vigia encerrado.\")")
    checar(u"ISCA: sem o encerrar da saida limpa, a leitura acusa",
           _isca != src and _ciclo_em_uso_no_main(_isca) != [],
           _ciclo_em_uso_no_main(_isca))




def _gravados_e_rotulos(motor):
    return [str(k.get("rotulo") or "") for k in motor.rts]


def teste_o_vigia_e_sempre_auto_e_nao_grava_ts_cru():
    secao(u"v8.3: o vigia e sempre AUTO (FULL + RadAI_OAR, sem TS cru)")
    RO = _app_import("radai_output")
    pedidos, crus = [], []
    real_fo = RO.Saida.full_e_oar
    real_ts = RO.Saida.totalsegmentator_cru

    def _fo(self, cruas, **kw):
        pedidos.append(dict(kw))
        return real_fo(self, cruas, **kw)

    def _ts(self, cruas):
        crus.append(1)
        return real_ts(self, cruas)
    RO.Saida.full_e_oar = _fo
    RO.Saida.totalsegmentator_cru = _ts
    try:
        ok, motor, mod, s, linhas = _rodar_anatomia({"torax"})
    finally:
        RO.Saida.full_e_oar = real_fo
        RO.Saida.totalsegmentator_cru = real_ts
    if motor is None:
        checar(u"a serie entrou na fila", False)
        return
    checar(u"a serie SAI", ok is True, str(ok))
    checar(u"a porta do entregue recebe modo=\"auto\" (dito, e nao o padrao)",
           len(pedidos) == 1 and pedidos[0].get("modo") == "auto"
           and mod.MODO_DO_VIGIA == "auto", str(pedidos))
    checar(u"  e sem `oar_fora` (o «x» e do PERSONALIZADO)",
           pedidos and not pedidos[0].get("oar_fora"), str(pedidos))
    rot = _gravados_e_rotulos(motor)
    checar(u"nada de TS cru: nenhum `RadAI_TS` gravado, e a porta do cru "
           u"nunca e chamada", "RadAI_TS" not in rot and not crus, rot)
    checar(u"  e o FULL (`RadAI_FULL`) e gravado",
           "RadAI_FULL" in rot, rot)
    done = mod.read_marker(s["dir"], s["uid"], "done") or {}
    checar(u"o `done` grava modo=auto (spec 1.1) e o plano de dispositivo "
           u"em chave propria", done.get("modo") == "auto"
           and done.get("plano_dispositivo") == "cpu", str(
               dict((k, done.get(k)) for k in ("modo", "plano_dispositivo"))))
    checar(u"  e o que gravou: oar e full", done.get("gravados")
           == ["oar", "full"], done.get("gravados"))
    def _fo_com_cru(self, cruas, **kw):
        r = real_fo(self, cruas, **kw)
        self.totalsegmentator_cru(cruas)
        return r
    RO.Saida.full_e_oar = _fo_com_cru
    try:
        ok2, motor2, _m2, _s2, _l2 = _rodar_anatomia({"torax"})
    finally:
        RO.Saida.full_e_oar = real_fo
    checar(u"ISCA: a porta que gravasse o cru junto deixa o `RadAI_TS` -- e a "
           u"checagem «nada de TS cru» o ve",
           motor2 is not None and "RadAI_TS" in _gravados_e_rotulos(motor2),
           _gravados_e_rotulos(motor2) if motor2 else None)
    import ast as _ast
    fonte = io.open(_componentes.fonte("app/radai_watcher.py"),
                    encoding="utf-8").read()
    ps = next(n for n in _ast.walk(_ast.parse(fonte))
              if isinstance(n, _ast.FunctionDef) and n.name == "process_series")
    chamadas = [n for n in _ast.walk(ps) if isinstance(n, _ast.Call)]
    checar(u"`process_series` nao chama `totalsegmentator_cru` nem motor de "
           u"comparacao (nv, cads, moose)",
           not [c for c in chamadas if getattr(c.func, "attr", "") in (
               "totalsegmentator_cru", "nv", "cads", "moose")])
    fo = [c for c in chamadas if getattr(c.func, "attr", "") == "full_e_oar"]
    checar(u"  e chama `full_e_oar` com `modo=MODO_DO_VIGIA`",
           len(fo) == 1 and any(
               k.arg == "modo" and getattr(k.value, "id", "") == "MODO_DO_VIGIA"
               for k in fo[0].keywords))


def teste_a_pelve_e_o_coracao_disparam_as_cavidades():
    secao(u"v8.3: a pelve e o coracao sem torax disparam a trunk_cavities")
    MO = _app_import("radai_modes")
    ok, motor, mod, s, linhas = _rodar_anatomia({"pelve"})
    if motor is None:
        checar(u"a serie entrou na fila", False)
        return
    checar(u"PELVE pura: a base e, depois dela, a `trunk_cavities`",
           motor.tasks == ["total_v3", "trunk_cavities"], motor.tasks)
    velha = MO.TASKS_POR_TOPOGRAFIA.get(MO.PELVE)
    MO.TASKS_POR_TOPOGRAFIA[MO.PELVE] = ()
    try:
        ok_i, motor_i, _m, _s, _l = _rodar_anatomia({"pelve"})
    finally:
        MO.TASKS_POR_TOPOGRAFIA[MO.PELVE] = velha
    checar(u"ISCA: com a linha da pelve vazia (a v8.2), so a base",
           motor_i is not None and motor_i.tasks == ["total_v3"],
           motor_i.tasks if motor_i else None)

    ok, motor, mod, s, linhas = _rodar_anatomia({"coracao"})
    checar(u"CORACAO do modelo com 180 cm3, sem torax: a `trunk_cavities` "
           u"roda (o pericardio)",
           motor is not None and motor.tasks == ["total_v3", "trunk_cavities"],
           motor.tasks if motor else None)
    checar(u"  e o log diz o volume e o porque",
           any(u"coracao do modelo: 180.0 cm3" in l for l in linhas)
           and any(u"tem 180.0 cm3" in l and u"pericardio" in l
                   for l in linhas),
           [l for l in linhas if u"coracao" in l][:3])
    ok, motor, mod, s, linhas = _rodar_anatomia({"coracao_pequeno"})
    checar(u"ISCA: coracao de 48 cm3 (abaixo do piso de 100) nao dispara",
           motor is not None and motor.tasks == ["total_v3"],
           motor.tasks if motor else None)
    TP = _app_import("radai_topography")
    _velha_cor = TP.coracao_do_modelo_cm3
    TP.coracao_do_modelo_cm3 = lambda *a, **k: None
    try:
        ok, motor, mod, s, linhas = _rodar_anatomia({"coracao"})
    finally:
        TP.coracao_do_modelo_cm3 = _velha_cor
    checar(u"ISCA: sem a medida do coracao ligada, o coracao de 180 cm3 NAO "
           u"dispara -- a ligacao e o que faz passar",
           motor is not None and motor.tasks == ["total_v3"],
           motor.tasks if motor else None)
    ok, motor, mod, s, linhas = _rodar_anatomia({"torax", "coracao"})
    checar(u"torax E coracao: a lista do torax, e a `trunk_cavities` UMA vez",
           motor is not None
           and motor.tasks == ["total_v3"] + list(_TORAX), motor.tasks
           if motor else None)


def teste_a_task_travada_vai_para_o_fim_e_volta_uma_vez():
    secao(u"v8.3: a task travada vai para o fim e volta UMA vez")
    E = _motor_do_teste()
    TT = E.TaskTravada

    def _tt(t, motivo="sem_pulso"):
        return TT(t, motivo, {"sem_pulso_s": 900.0, "limite_s": 900.0,
                              "pulsos": 3})
    ok, motor, mod, s, linhas = _rodar_anatomia(
        {"torax"}, erro_na={"trunk_cavities": [_tt("trunk_cavities"), None]},
        extra={"TRAVA_SEM_PULSO_MIN": "20", "TRAVA_PAGINANDO_MIN": "45",
               "TRAVA_RAM_PCT": "90"})
    if motor is None:
        checar(u"a serie entrou na fila", False)
        return
    checar(u"a serie SAI (a trava nao e falha da serie)", ok is True, str(ok))
    checar(u"a travada foi para o FIM da lista e voltou UMA vez: base, "
           u"trunk_cavities (trava), breasts, derrame, trunk_cavities",
           motor.tasks == ["total_v3", "trunk_cavities", "breasts",
                           "pleural_pericard_effusion", "trunk_cavities"],
           motor.tasks)
    tent = [k for k in motor.kw_tentativas if k.get("_task") == "trunk_cavities"]
    checar(u"  e a retomada foi com o plano de memoria MENOR, a primeira nao",
           len(tent) == 2 and not tent[0].get("plano_menor")
           and tent[1].get("plano_menor") is True,
           [k.get("plano_menor") for k in tent])
    checar(u"  e TODA tentativa recebeu a trava do CONFIG (20 min, 45 min, "
           u"90%), na forma do motor",
           motor.kw_tentativas and all(
               (k.get("trava") or {}) == {"sem_pulso_min": 20.0,
                                          "paginando_min": 45.0,
                                          "ram_pct": 90.0}
               for k in motor.kw_tentativas),
           str([k.get("trava") for k in motor.kw_tentativas][:2]))
    checar(u"  e o teto absoluto e o TIMEOUT_TASK_S (o de qualquer task)",
           all(k.get("timeout_s") == mod.TIMEOUT_TASK_S
               for k in motor.kw_tentativas))
    done = mod.read_marker(s["dir"], s["uid"], "done") or {}
    checar(u"o `done` diz a trava: a task, o motivo e a retomada ok",
           done.get("travamentos") == [{"task": "trunk_cavities",
                                        "motivo": "sem_pulso",
                                        "retomada": "ok"}],
           done.get("travamentos"))
    checar(u"  e a task voltou a lista do que rodou, sem `tasks_falharam`",
           "trunk_cavities" in (done.get("tasks_ok") or [])
           and not done.get("tasks_falharam"), str(
               (done.get("tasks_ok"), done.get("tasks_falharam"))))
    checar(u"  e o log do vigia diz o TRAVAMENTO, com a retomada",
           any(u"TRAVAMENTO" in l and u"trunk_cavities" in l and u"ok" in l
               for l in linhas), [l for l in linhas if "TRAVA" in l][:3])
    def _sem_retomada(mod_, s_, motor_):
        real = motor_.rodar_tasks
        motor_.rodar_tasks = lambda *a, **k: real(*a, **dict(k, retomar=False))
    ok_i, motor_i, mod_i, s_i, _l = _rodar_anatomia(
        {"torax"}, erro_na={"trunk_cavities": [_tt("trunk_cavities"), None]},
        antes=_sem_retomada)
    checar(u"ISCA: sem a retomada, a travada fica para tras (a checagem «volta "
           u"uma vez» reprovaria)", motor_i is not None
           and motor_i.tasks.count("trunk_cavities") == 1,
           motor_i.tasks if motor_i else None)
    ok, motor, mod, s, linhas = _rodar_anatomia(
        {"torax"}, erro_na={"breasts": [_tt("breasts"), _tt("breasts")]})
    done = (mod.read_marker(s["dir"], s["uid"], "done") or {}) if s else {}
    checar(u"complemento travado DUAS vezes: a serie SAI sem ele",
           ok is True and "breasts" not in (done.get("tasks_ok") or []), str(
               (ok, done.get("tasks_ok"))))
    checar(u"  e fica em `tasks_falharam` com a classe `travou`",
           [(f.get("task"), f.get("classe"))
            for f in done.get("tasks_falharam") or []]
           == [("breasts", "travou")], done.get("tasks_falharam"))
    checar(u"  e o travamento diz que a retomada travou",
           [(x.get("task"), x.get("retomada"))
            for x in done.get("travamentos") or []]
           == [("breasts", "travou")], done.get("travamentos"))
    ok, motor, mod, s, linhas = _rodar_anatomia(
        {"torax"}, erro_na={"total_v3": [_tt("total_v3"), _tt("total_v3")]})
    fl = (mod.read_marker(s["dir"], s["uid"], "fail") or {}) if s else {}
    checar(u"BASE travada duas vezes: a serie NAO sai, e fica ADIADA sem "
           u"gastar tentativa (tries 0, travou 1)",
           ok is False and int(fl.get("tries", -1)) == 0
           and fl.get("travou") == 1 and bool(fl.get("adiada")), fl)
    checar(u"  e a base foi tentada duas vezes (a retomada com o plano menor)",
           motor is not None and motor.tasks.count("total_v3") == 2,
           motor.tasks if motor else None)

    _FA = _app_import("radai_falhas")
    _velhos = (_FA.TIPOS_DE_TRAVA, _FA.PALAVRA_DA_TRAVA)

    def _sem_ramo(mod_, s_, motor_):
        _FA.TIPOS_DE_TRAVA, _FA.PALAVRA_DA_TRAVA = (), u"\x00nunca"
    try:
        ok, motor, mod, s, linhas = _rodar_anatomia(
            {"torax"}, erro_na={"total_v3": [_tt("total_v3"),
                                             _tt("total_v3")]},
            antes=_sem_ramo)
    finally:
        _FA.TIPOS_DE_TRAVA, _FA.PALAVRA_DA_TRAVA = _velhos
    fl = (mod.read_marker(s["dir"], s["uid"], "fail") or {}) if s else {}
    checar(u"ISCA: sem o ramo da trava, a base travada GASTA tentativa "
           u"(tries 1) -- o defeito que o ramo conserta",
           int(fl.get("tries", 0)) == 1 and not fl.get("adiada"), fl)


class _PowerShellDublado(object):

    def __init__(self, ok=False, espera_s=20.0):
        import threading as _th
        self.ok, self.espera_s = ok, espera_s
        self.chamadas, self.terminou = [], 0
        self.solta = _th.Event()

    def __call__(self, titulo, texto):
        self.chamadas.append((titulo, texto))
        self.solta.wait(self.espera_s)
        self.terminou += 1
        return (True, u"") if self.ok else (
            False, u"PowerShell saiu com 1 (dublado)")


def teste_a_notificacao_nao_derruba_nem_segura_o_laco():
    secao(u"v8.3: a notificacao do Windows nao derruba nem segura o laco")
    import threading as _th
    base_mod, _r, _b = montar([])
    checar(u"a bateria roda com a notificacao DESLIGADA (RADAI_NOTIFICACAO=0: "
           u"nenhum toast na maquina de quem a roda)", base_mod.NOTIFICAR is False,
           base_mod.NOTIFICAR)
    ps = _PowerShellDublado(ok=False)

    def _liga(mod_, s_, motor_):
        mod_.NOTIFICAR = True
        mod_.IDIOMA = u"pt-BR"
        mod_._mostrar_notificacao = ps
        mod_._NOTIFICACAO_FALHOU[0] = False
    t0 = time.time()
    ok, motor, mod, s, linhas = _rodar_anatomia({"torax"}, antes=_liga,
                                               pid="PAC_TOAST")
    dt = time.time() - t0
    for _ in range(100):
        if ps.chamadas:
            break
        time.sleep(0.05)
    terminou_antes = ps.terminou
    checar(u"a serie SAI com o toast falhando", ok is True, str(ok))
    checar(u"o vigia voltou ANTES de o PowerShell terminar (o toast e numa "
           u"thread; ele esperava o sinal)",
           len(ps.chamadas) == 1 and terminou_antes == 0,
           str((len(ps.chamadas), terminou_antes, round(dt, 1))))
    ps.solta.set()
    for _ in range(100):
        if ps.terminou:
            break
        time.sleep(0.05)
    time.sleep(0.2)
    uid8 = s["uid"][-8:] if s else ""
    titulo, texto = ps.chamadas[0] if ps.chamadas else (u"", u"")
    checar(u"o toast de SUCESSO diz a serie (…uid8), o que foi gravado e que "
           u"e sugestao nao aprovada",
           u"pronta" in titulo and (u"…" + uid8) in texto
           and u"RadAI_STUDY" in texto and u"FULL" in texto
           and u"não aprovada" in texto, (titulo, texto))
    checar(u"  sem PatientID nem caminho", u"PAC_TOAST" not in texto + titulo
           and u"\\" not in texto and u":/" not in texto, texto)
    falhas_log = [l for l in linhas + [x for x in mod.LOGBUF]
                  if u"notificacao do Windows: nao consegui" in str(l)]
    checar(u"a falha do PowerShell vira UMA linha de log, e o vigia segue",
           len(set(str(x)[-120:] for x in falhas_log)) == 1,
           [str(x)[-120:] for x in falhas_log][:3])
    antes_n = len([x for x in mod.LOGBUF
                   if u"notificacao do Windows: nao consegui" in str(x)])
    mod._notificar_em_segundo_plano(u"t", u"x")
    depois_n = len([x for x in mod.LOGBUF
                    if u"notificacao do Windows: nao consegui" in str(x)])
    checar(u"  e a segunda falha seguida nao repete a linha",
           depois_n == antes_n, str((antes_n, depois_n)))
    ps2 = _PowerShellDublado(ok=True, espera_s=0.0)

    def _liga2(mod_, s_, motor_):
        mod_.NOTIFICAR = True
        mod_.IDIOMA = u"pt-BR"
        mod_._mostrar_notificacao = ps2
    ok, motor, mod, s, linhas = _rodar_anatomia(
        {"torax"}, antes=_liga2, pid="PAC_TOAST2",
        erro_na={"total_v3": ValueError(
            u"serie corrompida em C:\\RADIOTERAPIA_AI\\PAC_TOAST2\\CT")})
    for _ in range(100):
        if ps2.chamadas:
            break
        time.sleep(0.05)
    titulo2, texto2 = ps2.chamadas[0] if ps2.chamadas else (u"", u"")
    checar(u"o toast de ERRO: a serie nao saiu, com a tentativa (1 de 3)",
           ok is False and u"não saiu" in titulo2
           and u"tentativa 1 de 3" in texto2, (titulo2, texto2))
    checar(u"  sem a mensagem do erro (que traz o caminho e o paciente)",
           u"corrompida" not in texto2 and u"PAC_TOAST2" not in texto2
           and u"RADIOTERAPIA_AI" not in texto2, texto2)
    import radai_phrases as _RP
    _de = _RP.construir()["de"]
    _k_ok = _RP.normalizar(mod.radai_notify.FRASES["ok"])
    _k_fa = _RP.normalizar(mod.radai_notify.FRASES["falhou"])
    _idioma_antes = mod.IDIOMA
    try:
        mod.IDIOMA = u"de"
        de_ok = mod._frase_da_notificacao("ok", "12345678", u"RadAI_OAR + FULL")
        de_fa = mod._frase_da_notificacao("falhou", "12345678", 1, 3)
        mod.IDIOMA = u"pt-BR"
        pt_ok = mod._frase_da_notificacao("ok", "12345678", u"RadAI_OAR + FULL")
    finally:
        mod.IDIOMA = _idioma_antes
    checar(u"com a estacao em alemao, o toast do vigia sai em alemao, pela "
           u"entrada do dicionario (sucesso e falha)",
           _k_ok in _de and _k_fa in _de
           and de_ok == _de[_k_ok].format("12345678", u"RadAI_OAR + FULL")
           and de_fa == _de[_k_fa].format("12345678", 1, 3), (de_ok, de_fa))
    checar(u"  (isca) e em portugues a mesma chamada da a frase portuguesa",
           pt_ok == mod.radai_notify.FRASES["ok"].format(
               "12345678", u"RadAI_OAR + FULL") and pt_ok != de_ok, pt_ok)
    mod.NOTIFICAR = True
    mod.DRY_RUN = True
    try:
        checar(u"em SIMULACAO (DRY_RUN) nao ha toast",
               mod.notificar("titulo_ok", "ok", "12345678", "x") is False)
    finally:
        mod.DRY_RUN = False
    mod.NOTIFICAR = False
    checar(u"desligada, `notificar` nao dispara nada",
           mod.notificar("titulo_ok", "ok", "12345678", "x") is False)
    scr = mod._script_da_notificacao(u"Título <x>", u"Série …1234 'ok' & fim")
    checar(u"o script do toast escapa o XML e a aspa simples, e usa a "
           u"identidade do PowerShell (sem registrar nada)",
           u"&lt;x&gt;" in scr and u"&amp;" in scr and u"''ok''" in scr
           and u"WindowsPowerShell" in scr and u"ToastGeneric" in scr, scr[:200])
    ps3 = _PowerShellDublado(ok=True, espera_s=3.0)

    def _sincrona(mod_, s_, motor_):
        mod_.NOTIFICAR = True
        mod_._mostrar_notificacao = ps3
        mod_.notificar = lambda ct, cx, *a: mod_._notificar_em_segundo_plano(
            mod_._frase_da_notificacao(ct), mod_._frase_da_notificacao(cx, *a))
    ok3, _mo, _md, _s3, _l3 = _rodar_anatomia({"torax"}, antes=_sincrona,
                                              pid="PAC_TOAST3")
    checar(u"ISCA: a notificacao SINCRONA so volta depois do PowerShell (a "
           u"checagem «voltou antes» reprovaria)", ps3.terminou == 1,
           ps3.terminou)


def teste_o_em_uso_diz_segmentando_na_borda_da_serie():
    secao(u"v8.3: o em_uso.json diz `segmentando` na borda da serie")
    agora = datetime.now()

    def _volta(mod, ativo=True):
        fila, _ = fila_de(mod)
        vistos = []
        mod._EM_USO_ATIVO[0] = ativo
        mod._sinalizar_em_uso_uma_vez = lambda: vistos.append(
            bool(mod.quem_esta_segmentando())) or True
        dentro = []
        mod.process_series = lambda s: dentro.append(
            bool(mod.quem_esta_segmentando())) or True
        estado = {"fila": list(fila), "proxima_varredura": time.time() + 999,
                  "turno": True}
        mod._uma_volta(estado)
        mod._EM_USO_ATIVO[0] = False
        return vistos, dentro, fila

    mod, root, base = montar([("PAC_USO", agora - timedelta(days=1), 8)])
    envelhecer(root, 60)
    vistos, dentro, fila = _volta(mod)
    checar(u"a serie entrou na fila", len(fila) == 1, len(fila))
    checar(u"o em_uso.json e gravado na ENTRADA (segmentando=True) e na SAIDA "
           u"(False) da serie", vistos == [True, False] and dentro == [True],
           str((vistos, dentro)))
    mod2, root2, _b2 = montar([("PAC_USO2", agora - timedelta(days=1), 8)])
    envelhecer(root2, 60)
    vistos2, _d2, _f2 = _volta(mod2, ativo=False)
    checar(u"sem a renovacao de pe, nada e gravado fora de hora",
           vistos2 == [], vistos2)
    src = io.open(_componentes.fonte("app/radai_watcher.py"), encoding="utf-8").read()
    i = src.find("\ndef _uma_volta(")
    corpo = src[i:src.find("\ndef ", i + 10)]
    errado = corpo.replace("_sinalizar_em_uso_agora()", "None")
    mod3, root3, _b3 = montar([("PAC_USO3", agora - timedelta(days=1), 8)])
    envelhecer(root3, 60)
    exec(compile(errado, "<isca_em_uso>", "exec"), mod3.__dict__)
    vistos3, _d3, _f3 = _volta(mod3)
    checar(u"ISCA: o laco sem as duas chamadas nao grava na borda (a "
           u"checagem reprovaria)", errado != corpo and vistos3 == [],
           vistos3)


class _MotorComRegras(_MotorAnatomico):

    def preparar_full(self, masks, **kw):
        m, meta = _MotorAnatomico.preparar_full(self, masks, **kw)
        meta = dict(meta)
        meta["regras_de_gravacao"] = [
            {"regra": u"R1 borda do campo", "nome": "liver", "cm3": 12.34,
             "inteira": True, "motivo": u"grande na borda cranial"},
            {"regra": u"R2 ilhas", "nome": "lung_left", "cm3": 0.8,
             "inteira": False, "motivo": u"ilha de 2% e 0,8 cm3"}]
        meta["ilhas_em_revisao"] = [{"nome": "lung_right", "ilhas": 1,
                                     "cm3": 3.1}]
        meta["fora_do_oar_por_regiao"] = {
            "pelvic_muscles": u"pelve nao identificada pela anatomia (pelve: "
                              u"nao (nenhum marco desenhado))"}
        return m, meta

    def _job(self, jid):
        return {"log": [u"[02:00:00]   TS total_v3 memoria: 9.3 GB livres no "
                        u"inicio, 0.4 no pico de uso (-8.9 GB com tudo o que "
                        u"rodou junto), 97% da estacao no pior momento",
                        u"[02:30:00]   TS breasts memoria: 6.0 GB livres no "
                        u"inicio, 2.5 no pico de uso (-3.5 GB com tudo o que "
                        u"rodou junto), 84% da estacao no pior momento"]}


def teste_o_caso_do_vigia_leva_o_processamento_da_v83():
    secao(u"v8.3: o caso do vigia leva o processamento (T-RC)")
    TT = _motor_do_teste().TaskTravada
    reg = tempfile.mkdtemp(prefix="radai_caso_vigia_")
    _TEMPS.append(reg)
    velho = os.environ.get("RADAI_REGISTRO_DIR")
    os.environ["RADAI_REGISTRO_DIR"] = reg
    try:
        ok, motor, mod, s, linhas = _rodar_anatomia(
            {"torax"}, motor_cls=_MotorComRegras,
            erro_na={"trunk_cavities": [TT("trunk_cavities", "paginando",
                                           {"ram_pct": 97.0}), None]})
    finally:
        if velho is None:
            os.environ.pop("RADAI_REGISTRO_DIR", None)
        else:
            os.environ["RADAI_REGISTRO_DIR"] = velho
    casos = _casos_em(reg)
    checar(u"a serie saiu e o caso foi gravado", ok is True and len(casos) == 1,
           str((ok, casos)))
    if not casos:
        return
    d = json.load(io.open(os.path.join(casos[0], "caso.json"),
                          encoding="utf-8"))
    pr = d.get("processamento") or {}
    checar(u"modo auto, e a comparacao toda em 0",
           pr.get("modo") == "auto" and pr.get("comparacao")
           == {"ts": 0, "nv": 0, "cads": 0, "mse": 0}, pr.get("modo"))
    checar(u"as tasks ligadas: a base e as do torax",
           pr.get("tasks_ligadas") == ["total_v3"] + list(_TORAX),
           pr.get("tasks_ligadas"))
    checar(u"as remocoes R1 a R4, no formato do registro (regra curta, cm3, "
           u"motivo por extenso)",
           [(x.get("regra"), x.get("nome"), x.get("volume_cm3"))
            for x in pr.get("remocoes") or []]
           == [("R1", "liver", 12.34), ("R2", "lung_left", 0.8)]
           and u"R1 borda do campo" in (pr["remocoes"][0].get("motivo") or u""),
           pr.get("remocoes"))
    checar(u"as ilhas mantidas para revisao",
           pr.get("ilhas_em_revisao") == [{"nome": "lung_right", "ilhas": 1,
                                           "cm3": 3.1}],
           pr.get("ilhas_em_revisao"))
    checar(u"o que a REGIAO tirou do OAR (E1: a porta devolvia, o caso nao "
           u"guardava)",
           [x.get("chave") for x in pr.get("oar_fora_por_regiao") or []]
           == ["pelvic_muscles"], pr.get("oar_fora_por_regiao"))
    checar(u"o travamento, com a retomada",
           [(x.get("task"), x.get("motivo"), x.get("retomada"))
            for x in pr.get("travamentos") or []]
           == [("trunk_cavities", "paginando", "ok")], pr.get("travamentos"))
    pm = pr.get("pico_memoria") or {}
    checar(u"o pico de memoria (a pior task, do log do motor)",
           pm.get("ram_pct") == 97.0 and pm.get("task") == "total_v3"
           and pm.get("livre_min_gb") == 0.4, pm)
    checar(u"o plano de dispositivo", bool(pr.get("plano_dispositivo")),
           pr.get("plano_dispositivo"))
    checar(u"e nenhum campo que o registro nao conhece",
           not pr.get("campos_ignorados"), pr.get("campos_ignorados"))
    checar(u"os tempos por passo NAO se repetem em `tempos_por_passo` (ja "
           u"vao em `etapas`, com `parte_de`)",
           "tempos_por_passo" not in pr
           and any(e.get("parte_de") for e in d.get("etapas") or []),
           [e.get("etapa") for e in d.get("etapas") or []][:6])
    info = {"ok": True, "erro": "", "modalidade": "CT", "tarefas": ["total_v3"],
            "tasks_ok": ["total_v3"], "etapas": [], "log_motor": []}
    reg2 = tempfile.mkdtemp(prefix="radai_caso_vigia_")
    _TEMPS.append(reg2)
    os.environ["RADAI_REGISTRO_DIR"] = reg2
    try:
        p = mod._registrar_caso_do_vigia(
            {"uid": "1.9.999.2.55.3.11111.87654321", "pid": "FANTOMA",
             "dir": os.path.join(reg2, "X"), "modality": "CT", "count": 8},
            time.time() - 5, info, None)
    finally:
        if velho is None:
            os.environ.pop("RADAI_REGISTRO_DIR", None)
        else:
            os.environ["RADAI_REGISTRO_DIR"] = velho
    d2 = json.load(io.open(os.path.join(p, "caso.json"), encoding="utf-8")) \
        if p else {}
    checar(u"ISCA: sem a costura das regras, o caso sai sem `remocoes` (a "
           u"checagem das remocoes reprovaria)",
           "remocoes" not in (d2.get("processamento") or {}),
           (d2.get("processamento") or {}).keys())
    info3 = dict(info, ok=False, erro=u"TS total_v3 TRAVADA duas vezes",
                 travamentos_do_job=[
                     {"task": "total_v3", "motivo": "sem_pulso",
                      "numeros": {"sem_pulso_s": 900.0}, "plano_menor": False},
                     {"task": "total_v3", "motivo": "sem_pulso",
                      "numeros": {"sem_pulso_s": 900.0}, "plano_menor": True}])
    reg3 = tempfile.mkdtemp(prefix="radai_caso_vigia_")
    _TEMPS.append(reg3)
    os.environ["RADAI_REGISTRO_DIR"] = reg3
    try:
        p3 = mod._registrar_caso_do_vigia(
            {"uid": "1.9.999.2.55.3.11111.87654399", "pid": "FANTOMA",
             "dir": os.path.join(reg3, "X"), "modality": "CT", "count": 8},
            time.time() - 5, info3, None)
    finally:
        if velho is None:
            os.environ.pop("RADAI_REGISTRO_DIR", None)
        else:
            os.environ["RADAI_REGISTRO_DIR"] = velho
    d3 = json.load(io.open(os.path.join(p3, "caso.json"), encoding="utf-8")) \
        if p3 else {}
    checar(u"a BASE travada duas vezes (a lista levantou): o caso leva a trava "
           u"do JOB, uma por task, com a retomada que travou",
           [(x.get("task"), x.get("retomada"))
            for x in (d3.get("processamento") or {}).get("travamentos") or []]
           == [("total_v3", "travou")],
           (d3.get("processamento") or {}).get("travamentos"))


class _MotorDoLote(object):

    _DO_REAL = ("rodar_tasks",)

    def __init__(self, dubla):
        object.__setattr__(self, "_dubla", dubla)
        object.__setattr__(self, "_real", _motor_do_teste())

    def __getattr__(self, nome):
        if nome in _MotorDoLote._DO_REAL:
            return getattr(self._real, nome)
        try:
            return getattr(self._dubla, nome)
        except AttributeError:
            return getattr(self._real, nome)


class _MarcadorQueNaoGrava(object):

    def __init__(self, textos=None, qual=""):
        self.textos, self.qual = textos, qual

    def write_text(self, texto=u"", *a, **k):
        if self.textos is not None:
            self.textos.append((self.qual, texto))
        return 0


def _caso_do_lote_sobre(s, dubla, reg, proc=None, serie=None, marcas=None,
                        fn=None):
    L = _app_import("radai_batch")
    marc = {"has_marker": lambda *a, **k: False,
            "claim": lambda *a, **k: True,
            "unclaim": lambda *a, **k: None,
            "renovar": lambda *a, **k: None,
            "m_path": lambda pasta, uid, qual, *a, **k:
                _MarcadorQueNaoGrava(marcas, qual)}
    base_s = dict(serie) if serie is not None else {
        "uid": s["uid"], "pasta": s["dir"], "modalidade": "CT",
        "pid": s.get("pid", ""), "curto": "c"}
    base_s["modo"] = "auto"
    serie = L._com_escolhas_da_tela({"series": [base_s]})[0]
    velho_motor = sys.modules.get("engine")
    velho_cfg = dict(L._CFG)
    velho_proc = L.processamento_do_caso
    velho_reg = os.environ.get("RADAI_REGISTRO_DIR")
    linhas = []
    sys.modules["engine"] = _MotorDoLote(dubla)
    os.environ["RADAI_REGISTRO_DIR"] = reg
    if proc is not None:
        L.processamento_do_caso = proc
    L._CFG.clear()
    res = None
    try:
        res = (fn or L._uma_serie)(serie, False, ["total_v3"], "cpu", None,
                                   60, 60, linhas.append, marc, "BATERIA",
                                   3600, 0.0)
    finally:
        L.processamento_do_caso = velho_proc
        L._CFG.clear()
        L._CFG.update(velho_cfg)
        if velho_motor is None:
            sys.modules.pop("engine", None)
        else:
            sys.modules["engine"] = velho_motor
        if velho_reg is None:
            os.environ.pop("RADAI_REGISTRO_DIR", None)
        else:
            os.environ["RADAI_REGISTRO_DIR"] = velho_reg
    casos = _casos_em(reg)
    if len(casos) != 1:
        return {"_linhas": linhas, "_casos": casos, "_res": res}
    d = json.load(io.open(os.path.join(casos[0], "caso.json"),
                          encoding="utf-8"))
    d["_linhas"] = linhas
    d["_res"] = res
    return d


def teste_o_caso_do_lote_e_o_do_vigia_tem_o_mesmo_processamento():
    secao(u"FD3: o caso do lote e o do vigia tem o mesmo processamento")
    reg_v = tempfile.mkdtemp(prefix="radai_caso_vigia_")
    _TEMPS.append(reg_v)
    velho = os.environ.get("RADAI_REGISTRO_DIR")
    os.environ["RADAI_REGISTRO_DIR"] = reg_v
    try:
        ok, motor, mod, s, _l = _rodar_anatomia({"torax"},
                                                motor_cls=_MotorComRegras,
                                                pid="PAC_DUAS_PORTAS")
    finally:
        if velho is None:
            os.environ.pop("RADAI_REGISTRO_DIR", None)
        else:
            os.environ["RADAI_REGISTRO_DIR"] = velho
    casos_v = _casos_em(reg_v)
    checar(u"a serie saiu pelo vigia e o caso foi gravado",
           ok is True and len(casos_v) == 1, str((ok, casos_v)))
    if not casos_v or s is None:
        return
    pr_v = (json.load(io.open(os.path.join(casos_v[0], "caso.json"),
                              encoding="utf-8")).get("processamento") or {})
    base_l = tempfile.mkdtemp(prefix="radai_lote_duas_portas_")
    _TEMPS.append(base_l)

    def _pelo_lote(proc=None, marcas=None, fn=None):
        reg = tempfile.mkdtemp(prefix="radai_caso_lote_")
        _TEMPS.append(reg)
        return _caso_do_lote_sobre(s, _MotorComRegras(base_l, {"torax"}), reg,
                                   proc=proc, marcas=marcas, fn=fn)

    marcas_l = []
    d_l = _pelo_lote(marcas=marcas_l)
    pr_l = d_l.get("processamento") or {}
    checar(u"a mesma serie saiu pelo lote e o caso foi gravado", bool(pr_l),
           str(d_l.get("_casos")) + u" | " + u" / ".join(
               d_l.get("_linhas", [])[-4:])[:400])
    if not pr_l:
        return
    checar(u"as MESMAS chaves de processamento nas duas portas",
           set(pr_l) == set(pr_v),
           u"so no lote: %s; so no vigia: %s"
           % (sorted(set(pr_l) - set(pr_v)), sorted(set(pr_v) - set(pr_l))))
    for k in ("remocoes", "ilhas_em_revisao", "pico_memoria",
              "plano_dispositivo", "oar_fora_por_regiao"):
        checar(u"  e `%s` igual nas duas (a mesma funcao)" % k,
               bool(pr_v.get(k)) and pr_l.get(k) == pr_v.get(k),
               u"lote=%r | vigia=%r" % (pr_l.get(k), pr_v.get(k)))
    _forma = lambda v: (type(v).__name__,
                        sorted(v) if isinstance(v, dict) else None)
    checar(u"  e cada campo no MESMO formato nas duas portas",
           all(_forma(pr_l[k]) == _forma(pr_v[k]) for k in pr_v if k in pr_l),
           str([(k, _forma(pr_l.get(k)), _forma(pr_v[k])) for k in pr_v
                if k in pr_l and _forma(pr_l[k]) != _forma(pr_v[k])]))
    checar(u"  e os niveis cervicais com o mesmo motivo (o laudo do pescoco)",
           pr_l.get("niveis_cervicais") == pr_v.get("niveis_cervicais")
           and (pr_v.get("niveis_cervicais") or {}).get("motivo"),
           u"lote=%r | vigia=%r" % (pr_l.get("niveis_cervicais"),
                                    pr_v.get("niveis_cervicais")))
    try:
        done_v = json.loads(mod.m_path(s["dir"], s["uid"], "done").read_text(
            encoding="utf-8"))
    except Exception as e:
        done_v = {"_erro": str(e)}
    _dl = [t for q, t in marcas_l if q == "done"]
    done_l = json.loads(_dl[-1]) if _dl else {}
    _so_do_lote = set(done_l) - set(done_v)
    checar(u"o `done` do lote tem TODOS os campos do vigia (e a mais so o "
           u"`origem`)",
           bool(done_l) and not (set(done_v) - set(done_l))
           and _so_do_lote <= {"origem"},
           u"so no vigia: %s; so no lote: %s"
           % (sorted(set(done_v) - set(done_l)), sorted(_so_do_lote)))
    for k in ("modalidade", "plano_dispositivo", "gravados", "regioes",
              "travamentos", "modo"):
        checar(u"  e `%s` igual nos dois `done`" % k,
               k in done_v and done_l.get(k) == done_v.get(k),
               u"lote=%r | vigia=%r" % (done_l.get(k), done_v.get(k)))
    _et = lambda d: [(e.get("etapa"), sorted(e))
                     for e in d.get("etapas") or []]
    checar(u"  e as etapas de topo com os mesmos nomes e as mesmas chaves",
           bool(done_v.get("etapas")) and _et(done_l) == _et(done_v),
           u"lote=%r | vigia=%r" % (_et(done_l), _et(done_v)))
    L0 = _app_import("radai_batch")
    import inspect as _insp
    _src_u = _insp.getsource(L0._uma_serie)
    _alvo_d = u"campos=_campos_done)"
    _ns = dict(vars(L0))
    exec(compile(_src_u.replace(_alvo_d, u"campos=None)"), "<isca-done>",
                 "exec"), _ns)
    marcas_i = []
    _pelo_lote(marcas=marcas_i, fn=_ns["_uma_serie"])
    _dli = [t for q, t in marcas_i if q == "done"]
    done_i = json.loads(_dli[-1]) if _dli else {}
    checar(u"ISCA: sem os campos comuns, o `done` do lote volta a faltar o "
           u"que o vigia grava (a checagem reprova)",
           _alvo_d in _src_u and bool(done_i)
           and bool(set(done_v) - set(done_i)),
           str(sorted(set(done_v) - set(done_i))))
    checar(u"  e o modo e a comparacao do AUTO",
           pr_l.get("modo") == pr_v.get("modo") == "auto"
           and pr_l.get("comparacao") == pr_v.get("comparacao"),
           u"%r %r" % (pr_l.get("modo"), pr_l.get("comparacao")))
    L = _app_import("radai_batch")
    import inspect
    src = inspect.getsource(L.processamento_do_caso)

    def _isca(troca, por):
        if troca not in src:
            return None
        ns = dict(vars(L))
        exec(compile(src.replace(troca, por, 1), "<isca-fd3>", "exec"), ns)
        return (_pelo_lote(proc=ns["processamento_do_caso"])
                .get("processamento") or {})

    alvo_ilhas = u'pr["ilhas_em_revisao"] = '
    pr_i = _isca(alvo_ilhas, u"_isca_sem_ilhas = ")
    checar(u"ISCA: sem as ilhas na montagem do lote, as chaves divergem (a "
           u"checagem reprova)", pr_i is not None and "ilhas_em_revisao"
           not in pr_i and set(pr_i) != set(pr_v), str(sorted(pr_i or ())))
    alvo_rem = u"_RG.remocoes_do_full("
    pr_r = _isca(alvo_rem, u"list(")
    checar(u"ISCA: as remocoes copiadas cruas do `meta` (a montagem de antes) "
           u"divergem das do vigia (a checagem reprova)",
           pr_r is not None and pr_r.get("remocoes")
           and pr_r.get("remocoes") != pr_v.get("remocoes"),
           str((pr_r or {}).get("remocoes"))[:200])
    import ast as _ast
    _fontes = dict((n, io.open(_componentes.fonte("app/" + n), encoding="utf-8").read())
                   for n in ("radai_watcher.py", "radai_batch.py"))

    def _chama(arq, func, alvo):
        for no in _ast.walk(_ast.parse(_fontes[arq])):
            if isinstance(no, _ast.FunctionDef) and no.name == func:
                return any(isinstance(c, _ast.Call)
                           and getattr(c.func, "attr", "") == alvo
                           for c in _ast.walk(no))
        return False
    checar(u"o clip-box do caso sai de `radai_records.clip_box_do_caso` nas "
           u"duas portas",
           _chama("radai_watcher.py", "_montar_e_registrar_caso",
                  "clip_box_do_caso")
           and _chama("radai_batch.py", "processamento_do_caso",
                      "clip_box_do_caso"))
    checar(u"  e o `done` de `radai_records.campos_do_done` nas duas",
           _chama("radai_watcher.py", "process_series", "campos_do_done")
           and _chama("radai_batch.py", "_uma_serie", "campos_do_done"))


def teste_as_duas_portas_dao_o_mesmo_nome_sem_data():
    secao(u"E1: as duas portas dao o mesmo nome a uma serie sem data")
    RS = _app_import("radai_sets")

    def _pelo_vigia(regra=None):
        velha = RS.data_do_nome
        if regra is not None:
            RS.data_do_nome = regra
        try:
            ok, motor, mod, s, _l = _rodar_anatomia(
                {"torax"}, motor_cls=_MotorComRegras, pid="PAC_SEM_DATA",
                sem_data=True)
        finally:
            RS.data_do_nome = velha
        nomes = sorted(f for f in os.listdir(s["dir"])
                       if f.startswith("RS_RadAI_")) if s else []
        return ok, s, nomes

    ok, s, nomes_v = _pelo_vigia()
    checar(u"o vigia processou a serie sem data", ok is True and bool(s),
           str(ok))
    if not s:
        return
    checar(u"  a varredura pos a data da PASTA na serie, marcada",
           s.get("data_da_pasta") is True
           and str(s.get("date") or "")[:8].isdigit(), str(s.get("date")))
    ent_v = [n for n in nomes_v if not n.startswith("RS_RadAI_FULL_")]
    checar(u"  e o entregue do vigia leva `semdata`, e nao a data da pasta",
           len(ent_v) == 1 and "_%s_" % RS.SEM_DATA in ent_v[0], str(nomes_v))
    L = _app_import("radai_batch")
    ss = L.varrer(s["dir"], min_cortes=3)
    checar(u"a varredura do lote acha a mesma serie, sem data",
           len(ss) == 1 and ss[0]["uid"] == s["uid"] and not ss[0]["date"],
           str([(x.get("uid", "")[-8:], x.get("date")) for x in ss]))
    if len(ss) != 1:
        return
    base_l = tempfile.mkdtemp(prefix="radai_lote_duas_portas_")
    reg = tempfile.mkdtemp(prefix="radai_caso_lote_")
    _TEMPS.extend([base_l, reg])
    d = _caso_do_lote_sobre(s, _MotorComRegras(base_l, {"torax"}), reg,
                            serie=ss[0])
    rs_l = str((d.get("_res") or {}).get("rs") or "")
    checar(u"o «Rodar agora» grava o entregue com o MESMO nome do vigia",
           bool(ent_v) and rs_l == ent_v[0],
           u"lote=%s | vigia=%s" % (rs_l, ent_v))
    _antes = (lambda serie: (u"%s" % ((serie or {}).get("date") or u""))[:8]
              or RS.SEM_DATA)
    _ok, _s, nomes_i = _pelo_vigia(regra=_antes)
    ent_i = [n for n in nomes_i if not n.startswith("RS_RadAI_FULL_")]
    checar(u"ISCA: pela regra de antes, o vigia poe a data da pasta no nome e "
           u"as portas divergem (a checagem reprova)",
           len(ent_i) == 1 and "_%s_" % RS.SEM_DATA not in ent_i[0]
           and ent_i[0] != rs_l, str(nomes_i))


def teste_a_linha_das_tasks_diz_quem_pediu():
    secao(u"E1: a linha das tasks diz quem pediu")
    _tor = [t for t in _TORAX]

    def _linhas_de(isca=False):
        def _antes(mod, s, motor):
            if isca:
                real = mod.tasks_pela_modalidade
                mod.tasks_pela_modalidade = (
                    lambda tarefas, modalidade, log=None, **kw:
                    real(tarefas, modalidade, log=log))
        ok, motor, mod, s, linhas = _rodar_anatomia({"torax"}, antes=_antes)
        return ok, [l for l in linhas if u"tasks desta serie" in l]

    ok, ls = _linhas_de()
    checar(u"a serie de torax saiu, e a linha das tasks foi escrita",
           ok is True and bool(ls), str(ls)[:200])
    checar(u"  e ela diz que foi a ANATOMIA que pediu as tasks do torax",
           any(u"a anatomia pediu" in l and all(t in l for t in _tor)
               for l in ls), str(ls)[:300])
    checar(u"  e nenhuma linha atribui as tasks do torax ao config",
           not any(u"o config pediu" in l and any(t in l.split(u"pediu")[-1]
                                                  for t in _tor) for l in ls),
           str(ls)[:300])
    _ok, ls_i = _linhas_de(isca=True)
    checar(u"ISCA: com a chamada de antes, a linha volta a dizer «o config "
           u"pediu» as tasks do torax (a checagem reprova)",
           any(u"o config pediu" in l and u"trunk_cavities" in
               l.split(u"pediu")[-1] for l in ls_i), str(ls_i)[:300])


def teste_encerrar_no_meio_nao_gasta_tentativa():
    secao("encerrar o programa no meio da serie nao conta como falha")
    agora = datetime.now()
    mod, root, base = montar([("PAC_1", agora - timedelta(days=1), 8),
                              ("PAC_2", agora - timedelta(days=2), 8)],
                             extra={"DRY_RUN": "0"})
    envelhecer(root, 60)
    fila = mod.build_queue(*mod.scan_root())
    checar("as duas series entraram na fila", len(fila) == 2, str(len(fila)))
    if len(fila) != 2:
        return
    mod.carregar_engine = lambda: _MotorFalso(
        "TS total_v3 interrompida a pedido, aos 12s")
    s = fila[0]
    mod.claim(s["dir"], s["uid"], {})
    mod.ENCERRANDO.set()
    try:
        ok = mod.process_series(s)
    finally:
        mod.ENCERRANDO.clear()
    checar("a serie interrompida nao conclui", ok is False)
    checar("NAO escreveu marcador de falha (nao gasta tentativa)",
           not mod.has_marker(s["dir"], s["uid"], "fail"))
    checar("e soltou o lock: ela volta para a fila",
           not mod.has_marker(s["dir"], s["uid"], "lock"))
    checar("e nao pausou o vigia por ambiente",
           mod.STATE["ambiente_erro"] == "", mod.STATE["ambiente_erro"])
    s2 = fila[1]
    mod.claim(s2["dir"], s2["uid"], {})
    mod.process_series(s2)
    checar("(isca) a mesma falha sem o encerramento gasta tentativa",
           mod.has_marker(s2["dir"], s2["uid"], "fail"))


def teste_o_encerramento_solta_os_locks_deste_processo():
    secao("o encerramento solta todo lock deste processo, e so os dele")
    agora = datetime.now()
    mod, root, base = montar([("PAC_1", agora - timedelta(days=1), 8),
                              ("PAC_2", agora - timedelta(days=2), 8)])
    envelhecer(root, 60)
    fila = mod.build_queue(*mod.scan_root())
    if len(fila) != 2:
        checar("as duas series entraram na fila", False, str(len(fila)))
        return
    a, b = fila
    checar("as duas reivindicadas por este processo",
           mod.claim(a["dir"], a["uid"], {}) and mod.claim(b["dir"], b["uid"], {}))
    lp = mod.m_path(b["dir"], b["uid"], "lock")
    d = json.loads(io.open(str(lp), encoding="utf-8").read())
    d["token"] = "outra-maquina"
    io.open(str(lp), "w", encoding="utf-8").write(json.dumps(d))
    mod.soltar_os_locks_deste_processo()
    checar("o lock deste processo saiu",
           not mod.has_marker(a["dir"], a["uid"], "lock"))
    checar("o que outra maquina assumiu ficou",
           mod.has_marker(b["dir"], b["uid"], "lock"))
    checar("e o registro das pastas esvaziou", not mod._PASTAS_DOS_LOCKS,
           repr(mod._PASTAS_DOS_LOCKS))


def teste_o_config_antigo_e_migrado_uma_vez():
    secao("o config antigo perde as chaves que sairam, uma vez, com copia")
    mod, root, base = montar([])
    pasta = novo_temp()

    def ler(c):
        return io.open(c, encoding="utf-8").read()

    def copias(nome):
        return [n for n in os.listdir(pasta)
                if n.startswith(nome + ".antes-da-migracao-")]
    cfg = os.path.join(pasta, "velho.config")
    io.open(cfg, "w", encoding="utf-8").write(
        u"# ─── Vigia ───\n# a pasta\nROOT=X\n\n"
        u"# liga o NV\n# em toda serie\nINCLUIR_NV=1\nENTREGAR_TS=1\n\n"
        u"# porta\nPORT=8777\n\n# acrescentado pela tela de configuracoes\n"
        u"URL_VERSOES=http://x\n")
    linhas = []
    tiradas = mod.migrar_config(cfg, log=linhas.append)
    texto = ler(cfg)
    checar("as tres chaves que sairam sairam do arquivo",
           set(tiradas) == {"INCLUIR_NV", "ENTREGAR_TS", "URL_VERSOES"},
           repr(tiradas))
    checar("  e a ajuda colada nelas tambem",
           "liga o NV" not in texto and "em toda serie" not in texto
           and "acrescentado pela tela" not in texto, texto)
    checar("  e o resto ficou, com a moldura e a ajuda de cada chave",
           u"─── Vigia" in texto and "# a pasta\nROOT=X" in texto
           and "# porta\nPORT=8777" in texto, texto)
    cs = copias("velho.config")
    checar("ficou uma copia de seguranca com o arquivo anterior",
           len(cs) == 1 and "INCLUIR_NV=1" in ler(os.path.join(pasta, cs[0])),
           repr(cs))
    checar("e uma linha no log, que diz o que saiu e onde ficou a copia",
           len(linhas) == 1 and "migrado" in linhas[0]
           and "INCLUIR_NV" in linhas[0] and cs and cs[0] in linhas[0],
           repr(linhas))
    checar("UMA vez: a segunda abertura nao mexe em nada",
           mod.migrar_config(cfg, log=linhas.append) == []
           and len(linhas) == 1 and len(copias("velho.config")) == 1)

    cfg2 = os.path.join(pasta, "aviso.config")
    io.open(cfg2, "w", encoding="utf-8").write(u"ROOT=\nINCLUIR_NV=1\n")
    mod.AVISOS_CFG[:] = [u"chave obsoleta ignorada: INCLUIR_NV (saiu na v8.3: x)",
                         u"chave desconhecida no config, ignorada: XPTO"]
    mod.migrar_config(cfg2, log=lambda m: None)
    checar("o aviso da chave migrada sai do arranque; o resto fica",
           mod.AVISOS_CFG == [u"chave desconhecida no config, ignorada: XPTO"],
           repr(mod.AVISOS_CFG))

    cfg3 = os.path.join(pasta, "tasks.config")
    io.open(cfg3, "w", encoding="utf-8").write(
        u"# extras do vigia\nTASKS=total_v3,lung_nodules,teeth\nROOT=\n")
    tir = mod.migrar_config(cfg3, obsoletas={"TASKS": u"x"},
                            vivas={"ROOT": u""}, log=lambda m: None)
    checar("o TASKS sai pelo mesmo caminho quando ele for obsoleto",
           tir == ["TASKS"] and "TASKS" not in ler(cfg3)
           and "extras do vigia" not in ler(cfg3), ler(cfg3))
    cfg4 = os.path.join(pasta, "viva.config")
    io.open(cfg4, "w", encoding="utf-8").write(u"ROOT=Y\n")
    tir = mod.migrar_config(cfg4, obsoletas={"ROOT": u"x"}, log=lambda m: None)
    checar("(isca) chave que ainda vale nao sai, mesmo listada como obsoleta",
           tir == [] and "ROOT=Y" in ler(cfg4))
    fonte = io.open(_componentes.fonte("app/radai_watcher.py"), encoding="utf-8").read()
    i = fonte.find("def worker_loop():")
    corpo = fonte[i:fonte.find("\ndef ", i + 10)]
    checar("o arranque migra ANTES de escrever os avisos do config",
           0 < corpo.find("migrar_config()") < corpo.find("for a in AVISOS_CFG:"))


def teste_toda_chave_obsoleta_sai_pela_migracao_de_verdade():
    secao("toda chave de CHAVES_OBSOLETAS sai do arquivo sem vivas forjado")
    mod, root, base = montar([])
    pasta = novo_temp()

    def presas(obsoletas, vivas):
        return sorted(k for k in obsoletas if k in vivas)
    p = presas(mod.CHAVES_OBSOLETAS, mod.DEFAULTS)
    checar("nenhuma chave obsoleta continua em DEFAULTS (a migracao a pularia)",
           not p, repr(p))
    checar("  (isca) TASKS obsoleta e ainda em DEFAULTS seria acusada",
           presas({"TASKS": u"x"}, {"TASKS": u"total_v3"}) == ["TASKS"])
    cfg = os.path.join(pasta, "todas.config")
    io.open(cfg, "w", encoding="utf-8").write(
        u"ROOT=\n" + u"".join(u"%s=1\n" % k for k in sorted(mod.CHAVES_OBSOLETAS)))
    tir = mod.migrar_config(cfg, log=lambda m: None)
    checar("a migracao com as listas de verdade tira todas as obsoletas",
           sorted(tir) == sorted(mod.CHAVES_OBSOLETAS), repr(tir))


def teste_a_fila_ocupada_e_trabalho_e_nao_vigia_ligado():
    secao("pedir para nao suspender so com trabalho na fila, nao com o vigia ocioso")
    mod, root, base = montar([])
    guardado = dict((k, mod.STATE.get(k)) for k in ("ligado", "paused", "current", "n_queue"))
    try:
        mod.STATE.update({"ligado": True, "paused": False, "current": None, "n_queue": 0})
        checar("vigia ligado, fila vazia, nada segmentando: a estacao pode suspender",
               mod.fila_ocupada() is False)
        mod.STATE["n_queue"] = 3
        checar("  com series na fila do vigia: pede para nao suspender",
               mod.fila_ocupada() is True)
        mod.STATE["paused"] = True
        checar("  pausado, com fila: pode suspender", mod.fila_ocupada() is False)
        mod.STATE.update({"paused": False, "n_queue": 0,
                          "current": {"pid": u"P", "uid": u"12345678"}})
        checar("  segmentando uma serie: pede para nao suspender",
               mod.fila_ocupada() is True)
    finally:
        mod.STATE.update(guardado)


def _prints_no_codigo(fonte):
    import ast as _ast
    achados = []
    for no in _ast.walk(_ast.parse(fonte)):
        if (isinstance(no, _ast.Call) and isinstance(no.func, _ast.Name)
                and no.func.id == "print"):
            achados.append(no.lineno)
    return achados


def teste_o_vigia_nao_tem_print_orfao():
    secao("o vigia fala pelo log: nenhum print que so a janela preta via")
    fonte = io.open(_componentes.fonte("app/radai_watcher.py"), encoding="utf-8").read()
    p = _prints_no_codigo(fonte)
    checar("nenhum print() no radai_watcher.py (tudo passa pelo wlog)",
           not p, repr(p))
    checar("  (isca) um print acrescentado e acusado",
           bool(_prints_no_codigo(fonte + u"\nprint('x')\n")))


def teste_o_tempo_de_cada_etapa_vai_ao_log():
    secao("o tempo de cada etapa da serie no log, com a soma (vigia e lote)")
    sys.path.insert(0, APP)
    import radai_etapas as E
    checar("duracao curta com virgula", E.duracao(4.24) == u"4,2 s", E.duracao(4.24))
    checar("duracao em minutos", E.duracao(125) == u"2m05s", E.duracao(125))
    checar("duracao em horas", E.duracao(3725) == u"1h02m05s", E.duracao(3725))
    agora = [0.0]
    c = E.Cronometro(relogio=lambda: agora[0])
    c.etapa(u"copiando a serie")
    agora[0] += 12.0
    f = c.etapa(u"total_v3")
    checar("trocar de etapa fecha a anterior com o tempo dela",
           f == (u"copiando a serie", 12.0), repr(f))
    checar("  e repetir a mesma etapa nao fecha nada", c.etapa(u"total_v3") is None)
    agora[0] += 600.0
    c.fechar()
    r = c.resumo()
    checar("o resumo lista cada etapa e a soma",
           u"copiando a serie 12 s" in r and u"total_v3 10m00s" in r
           and u"soma 10m12s" in r, r)

    import radai_batch as B
    linhas = []
    B._abrir_cronometro(linhas.append)
    B._passo(u"copiando a serie")
    B._passo(u"segmentando: total_v3")
    B._fechar_cronometro()
    checar("o «Rodar agora» escreve o tempo de cada etapa e o resumo",
           any(u"tempo: preparo levou" in l for l in linhas)
           and any(u"tempo: copiando a serie levou" in l for l in linhas)
           and any(l.startswith(u"tempo por etapa:") for l in linhas),
           repr(linhas))
    B._passo(u"fora de serie")
    checar("  e fora de uma serie o _passo nao escreve nada", len(linhas) == 4,
           repr(linhas))
    fonte = io.open(_componentes.fonte("app/radai_batch.py"), encoding="utf-8").read()
    i = fonte.find("def _uma_serie(")
    corpo = fonte[i:fonte.find("\ndef ", i + 10)]
    checar("a serie do lote abre o cronometro e o fecha no finally",
           u"_abrir_cronometro(log)" in corpo
           and corpo.rfind(u"_fechar_cronometro()") > corpo.rfind(u"    finally:"))

    agora2 = datetime.now()
    mod, root, base = montar([("PAC_T", agora2 - timedelta(days=1), 8)],
                             extra={"DRY_RUN": "0"})
    envelhecer(root, 60)
    fila = mod.build_queue(*mod.scan_root())
    if not fila:
        checar("a serie entrou na fila", False)
        return
    mod.carregar_engine = lambda: _MotorFalso("serie corrompida: corte 3")
    s = fila[0]
    mod.claim(s["dir"], s["uid"], {})
    antes = len(mod.LOGBUF)
    mod.process_series(s)
    novas = list(mod.LOGBUF)[antes:]
    checar("o vigia escreve o tempo de cada etapa, mesmo na serie que falhou",
           any(u"tempo: copiando a s" in l for l in novas)
           and any(u"tempo por etapa:" in l for l in novas),
           repr([l for l in novas if u"tempo" in l][:4]))
    checar("  e o cronometro da serie fecha com ela",
           mod._CRONOMETRO_DA_SERIE[0] is None)


class _Trava(RuntimeError):
    tempo_limite = True


class _SdParcial(object):

    def __init__(self, destino, rs_name, grava):
        self.destino, self.rs_name = str(destino), str(rs_name)
        self.gravados, self.meta_do_full, self.grava = [], {}, grava

    def _alvo(self, infixo):
        RO = _app_import("radai_output")
        return RO.Saida._alvo(self, infixo)

    def full_e_oar(self, cruas, **k):
        RS = _app_import("radai_sets")
        if self.grava:
            with io.open(self._alvo(RS.POR_COD["oar"]["infixo"]), "wb") as f:
                f.write(b"RTSTRUCT de mentira (OAR)")
            self.gravados.append("oar")
        return {"estruturas": ["Liver_ai"], "full": None, "etapas": [],
                "parcial": {"conjunto": u"FULL",
                            "motivo": u"o FULL nao coube na memoria"}}

    def plugins(self, *a, **k):
        return None

    def pelvicos(self, *a, **k):
        return None


class _MotorQuePulaPorMemoria(_MotorAnatomico):

    def rodar_tasks(self, *a, **kw):
        r = dict(_motor_do_teste().rodar_tasks(*a, **kw) or {})
        r["tasks_puladas_por_memoria"] = [
            {"task": "abdominal_muscles", "pedia_gib": 9.5, "livre_gib": 2.0}]
        return r


def _casos_do_registro():
    d = os.path.join(_REGISTRO_TESTE, "casos")
    try:
        return set(os.listdir(d))
    except OSError:
        return set()


def _em_andamento_do_registro():
    d = os.path.join(_REGISTRO_TESTE, "em_andamento")
    try:
        return [n for n in os.listdir(d) if n.endswith(".json")]
    except OSError:
        return []


def _uma_saida(nome, erro_na=None, ao_rodar=None, antes=None,
               motor_cls=None):
    agora = datetime.now()
    pid = "PAC_SAIDA_%s" % nome.upper()
    cfg = {"DRY_RUN": "0", "TASKS": "total_v3", "INCLUIR_NV": "0",
           "INCLUIR_CADS": "0", "INCLUIR_MOOSE": "0", "INCLUIR_HNLNL": "0",
           "ENTREGAR_TS": "0", "RECORTE_NO_CORPO": "0"}
    mod, root, base = montar([(pid, agora - timedelta(days=1), 8)], extra=cfg)
    envelhecer(root, 60)
    fila, _ = fila_de(mod)
    if not fila:
        return None
    s = fila[0]
    motor = (motor_cls or _MotorAnatomico)(
        base, {"torax"}, ao_rodar=(lambda t: ao_rodar(t, mod, s))
        if ao_rodar else None, erro_na=erro_na)
    mod.carregar_engine = lambda: motor
    mod.ler_topografia = lambda *a, **k: ["total"]
    if antes is not None:
        antes(mod, s, motor)
    casos0 = _casos_do_registro()
    mod.claim(s["dir"], s["uid"], {"machine": "PC_A", "pid_os": os.getpid()})
    try:
        ok = mod.process_series(s)
    finally:
        mod.ENCERRANDO.clear()
        mod.CANCELAR_VIGIA.clear()
    log_serie = os.path.join(s["dir"], "_RadAI", s["uid"] + ".log.txt")
    texto = u""
    if os.path.isfile(log_serie):
        texto = io.open(log_serie, encoding="utf-8").read()
    rs = []
    try:
        RS = _app_import("radai_sets")
        rs = RS.arquivos_da_serie(os.listdir(s["dir"]), s["uid"])
    except Exception:
        pass
    return {"ok": ok, "mod": mod, "s": s, "pid": pid, "log": texto,
            "lock": mod.has_marker(s["dir"], s["uid"], "lock"),
            "done": mod.read_marker(s["dir"], s["uid"], "done"),
            "fail": mod.read_marker(s["dir"], s["uid"], "fail"),
            "casos": len(_casos_do_registro() - casos0), "rs": rs,
            "desfecho": dict(mod.ULTIMO_DESFECHO)}


def teste_toda_saida_da_serie_solta_a_trava():
    secao(u"toda saida de uma serie do vigia solta a trava, grava o marcador "
          u"certo, o caso e o log da serie")
    E_AMB = RuntimeError(ERRO_AMBIENTE)

    def _cancelar(t, mod, s):
        mod.CANCELAR_VIGIA.set()

    def _encerrar(t, mod, s):
        mod.ENCERRANDO.set()

    def _parcial(grava):
        def _antes(mod, s, motor):
            mod._saida_de = (lambda engine, stage, destino, rs_name, **k:
                             _SdParcial(destino, rs_name, grava))
        return _antes

    def _copia_quebra(mod, s, motor):
        def _quebra(*a, **k):
            raise OSError("o share caiu no meio da copia")
        motor.copy_sorted = _quebra
    cenarios = (
        ("sucesso", {}, "done", None),
        ("parcial", {"antes": _parcial(True)}, "done", None),
        ("parcial_sem_arquivo", {"antes": _parcial(False)}, "fail",
         u"nenhum RTSTRUCT RadAI"),
        ("pulada_por_memoria", {"motor_cls": _MotorQuePulaPorMemoria}, "done",
         None),
        ("falha_de_task", {"erro_na": {"total_v3": RuntimeError(
            "serie corrompida: cabecalho ilegivel no corte 3")}}, "fail", None),
        ("recurso", {"erro_na": {"total_v3": MemoryError()}}, "fail", None),
        ("tempo_esgotado", {"erro_na": {"total_v3": [
            _Trava("TS total_v3 estourou o tempo limite")] * 4}}, "fail", None),
        ("excecao", {"antes": _copia_quebra}, "fail", None),
        ("ambiente", {"erro_na": {"total_v3": E_AMB}}, None, None),
        ("cancelamento", {"ao_rodar": _cancelar, "erro_na": {
            "total_v3": RuntimeError("parado pelo operador")}}, None, None),
        ("encerramento", {"ao_rodar": _encerrar, "erro_na": {
            "total_v3": RuntimeError("o programa esta saindo")}}, None, None),
    )
    for nome, kw, marcador, frase in cenarios:
        r = _uma_saida(nome, **kw)
        if r is None:
            checar(u"[%s] a serie entrou na fila" % nome, False)
            continue
        checar(u"[%s] a trava foi solta" % nome, not r["lock"])
        if marcador == "done":
            checar(u"[%s]   marcador de pronta, e o RTSTRUCT esta no disco"
                   % nome, r["done"] is not None and r["fail"] is None
                   and r["rs"], "%s %s" % (r["rs"], r["desfecho"].get("erro")))
        elif marcador == "fail":
            checar(u"[%s]   marcador de falha, e nenhum de pronta" % nome,
                   r["fail"] is not None and r["done"] is None,
                   str(r["fail"])[:160])
        else:
            checar(u"[%s]   nem pronta nem falha (nao conta tentativa)" % nome,
                   r["fail"] is None and r["done"] is None,
                   str(r["fail"])[:160])
        if frase:
            checar(u"[%s]   com o motivo: %s" % (nome, frase),
                   frase in u"%s" % ((r["fail"] or {}).get("last_error")),
                   str(r["fail"])[:200])
        checar(u"[%s]   o caso foi gravado no registro" % nome,
               r["casos"] == 1, str(r["casos"]))
        checar(u"[%s]   e nao sobra caso «em andamento»" % nome,
               not _em_andamento_do_registro(), str(_em_andamento_do_registro()))
        checar(u"[%s]   o log da serie, na _RadAI, tem o comeco e o fim, sem o "
               u"PatientID" % nome,
               u"=== serie" in r["log"] and u"fim da serie" in r["log"]
               and u"trava solta" in r["log"] and r["pid"] not in r["log"],
               r["log"][-300:])
    r = _uma_saida("pulada_por_memoria_2", motor_cls=_MotorQuePulaPorMemoria)
    checar(u"[pulada_por_memoria] o done leva a task que ficou de fora "
           u"(o relogio do complemento a retoma)",
           r and [x.get("task") for x in (r["done"] or {}).get(
               "tasks_puladas_por_memoria") or []] == ["abdominal_muscles"],
           str((r or {}).get("done"))[:200])


def teste_a_janela_entre_o_claim_e_a_serie():
    secao(u"a janela entre o claim e a serie: o que levanta ali solta a trava")
    agora = datetime.now()
    mod, root, base = montar([("PAC_JANELA", agora - timedelta(days=1), 8)])
    envelhecer(root, 60)
    fila, series = fila_de(mod)
    s = fila[0]
    mod.claim(s["dir"], s["uid"], {"machine": "PC_A", "pid_os": os.getpid(),
                                   "start": "2026-10-15 14:02:00"})
    lock = mod.read_marker(s["dir"], s["uid"], "lock") or {}
    checar(u"(isca, o campo) um claim sem o finally deixa a trava so com os "
           u"campos do claim, sem batimento nenhum",
           set(lock) - {"criado"}
           == {"machine", "pid_os", "start", "token", "heartbeat"},
           str(sorted(lock)))
    checar(u"  e este mesmo processo nunca mais a pega (diz «trabalhando»)",
           mod._diagnostico_do_lock(s["dir"], s["uid"])[0] == "trabalhando"
           and mod.claim(s["dir"], s["uid"], {}) is False)
    mod.unclaim(s["dir"], s["uid"])
    velho = mod._abrir_cronometro

    def _quebra():
        raise RuntimeError("can't start new thread (de proposito)")
    mod._abrir_cronometro = _quebra
    mod.STATE["ligado"] = True
    estado = {"fila": [dict(s)], "proxima_varredura": time.time() + 3600,
              "turno": True}
    try:
        try:
            mod._uma_volta(estado)
        except Exception:
            pass
    finally:
        mod._abrir_cronometro = velho
    checar(u"com o preparo levantando depois do claim, a trava sai",
           not mod.has_marker(s["dir"], s["uid"], "lock"))
    checar(u"  e a serie nao fica dada como deste processo",
           s["uid"] not in mod._SERIES_DESTE_PROCESSO)
    fl = mod.read_marker(s["dir"], s["uid"], "fail") or {}
    checar(u"  «can't start new thread» e falta de recurso: a serie e adiada "
           u"sem gastar tentativa",
           int(fl.get("tries", 0) or 0) == 0
           and bool(mod.adiamento_de(fl)[0])
           and mod.classificar_erro(RuntimeError("can't start new thread"))
           == mod.RECURSO, str(fl)[:200])
    checar(u"  (isca) um erro comum na mesma janela gasta tentativa",
           mod.classificar_erro(RuntimeError("chave errada"))
           == mod.DETERMINISTICO)
    for frase in (u"[WinError 1455] The paging file is too small",
                  u"VirtualAlloc failed: commit limit reached",
                  u"Intel MKL ERROR: memory allocation failed"):
        checar(u"  memoria de commit esgotada e recurso: %s" % frase[:40],
               mod.classificar_erro(OSError(frase)) == mod.RECURSO)
    mod.m_path(s["dir"], s["uid"], "fail").unlink()
    fila2, _ = fila_de(mod)
    checar(u"  e, passado o adiamento, volta para a fila do vigia",
           [q["uid"] for q in fila2] == [s["uid"]])
    mod.claim(s["dir"], s["uid"], {})
    meu = mod.lock_e_meu(s["dir"], s["uid"])[0]
    checar(u"  (o soltar da janela so solta a trava que e desta execucao, uma "
           u"vez)", meu and mod._soltar_a_trava_do_que_nao_terminou(s)
           and not mod.has_marker(s["dir"], s["uid"], "lock")
           and mod._soltar_a_trava_do_que_nao_terminou(s) is False)


_EXECUTOR_QUE_MORRE = u'''
import importlib.util, os, sys
caminho, tarefa = sys.argv[1], sys.argv[2]
spec = importlib.util.spec_from_file_location("vigia_que_morre", caminho)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
mod.STATE["ligado"] = True
import numpy as np
import SimpleITK as sitk

class Motor(object):
    VERSAO_DA_RECEITA_POS = u"dublada"
    def _job_new(self): return "j"
    def _job(self, jid): return {"log": []}
    def _job_del(self, jid): pass
    def copy_sorted(self, a, d): pass
    def load_sitk(self, p):
        img = sitk.GetImageFromArray(np.zeros((8, 16, 16), dtype=np.int16))
        img.SetSpacing((2.0, 2.0, 3.0))
        return img
    def _resolve_device(self, e): return "cpu"
    def drenar_log(self, jid, escrever, parar, a_cada_s=None, intervalo=3.0):
        return None
    def conferir_volume_contornavel(self, *a, **k): return None
    def run_ts_task(self, ref, t, **kw):
        sys.stdout.flush()
        os._exit(9)
    def rodar_tasks(self, ref, tarefas, dev, jid, rodar=None, **kw):
        return rodar(ref, tarefa, dev, jid)

mod.carregar_engine = lambda: Motor()
series, done = mod.scan_root()
fila = mod.build_queue(series, done)
s = fila[0]
mod.claim(s["dir"], s["uid"], {"machine": mod.MACHINE, "pid_os": os.getpid(),
                               "start": "2026-10-15 14:02:00"})
mod.process_series(s)
'''


def teste_a_serie_que_morre_no_meio_deixa_o_rastro():
    secao(u"o processo que morre no meio: o log ate a ultima etapa, e ao abrir "
          u"a trava solta e o caso interrompido")
    import subprocess
    agora = datetime.now()
    pid = "PAC_MORRE"
    mod, root, base = montar([(pid, agora - timedelta(days=1), 8)],
                             extra={"DRY_RUN": "0", "TASKS": "total_v3"})
    envelhecer(root, 60)
    cfgs = sorted((os.path.getmtime(os.path.join(base, n)), n)
                  for n in os.listdir(base) if n.startswith("cfg_"))
    script = os.path.join(base, "executor_que_morre.py")
    with io.open(script, "w", encoding="utf-8") as f:
        f.write(_EXECUTOR_QUE_MORRE)
    env = dict(os.environ)
    env.update({"RADAI_CONFIG": os.path.join(base, cfgs[-1][1]),
                "RADAI_MACHINE": "PC_A",
                "LOCALAPPDATA": os.path.join(base, "appdata_PC_A"),
                "PYTHONPATH": os.pathsep.join(p for p in sys.path if p),
                "PYTHONIOENCODING": "utf-8"})
    r = subprocess.run([sys.executable, script,
                        _componentes.fonte("app/radai_watcher.py"), "total_v3"],
                       env=env, cwd=base, stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, timeout=300)
    fila, series = fila_de(mod)
    s = fila[0] if fila else None
    checar(u"o executor morreu no meio da task, sem o finally (codigo 9)",
           r.returncode == 9,
           (r.stdout or b"")[-400:].decode("utf-8", "replace"))
    if s is None:
        checar(u"a serie esta na varredura", False)
        return
    log_serie = os.path.join(s["dir"], "_RadAI", s["uid"] + ".log.txt")
    texto = io.open(log_serie, encoding="utf-8").read() \
        if os.path.isfile(log_serie) else u""
    ultima = (texto.strip().splitlines() or [u""])[-1]
    checar(u"o log da serie ficou na _RadAI ate a ultima etapa (a task em "
           u"que morreu), linha a linha",
           u"=== serie" in texto and u": copiando a s" in texto
           and u"etapa" in ultima and u"total_v3" in ultima, texto[-300:])
    checar(u"  sem o PatientID", pid not in texto)
    lock = mod.read_marker(s["dir"], s["uid"], "lock") or {}
    checar(u"a trava ficou (o processo morreu), de um pid desta maquina que "
           u"nao existe mais", lock and mod._diagnostico_do_lock(
               s["dir"], s["uid"])[0] == "morto", str(lock)[:160])
    L = _app_import("radai_batch")
    marc = {"has_marker": mod.has_marker, "read_marker": mod.read_marker,
            "diagnostico": mod._diagnostico_do_lock}
    sit = L._situacao({"pasta": s["dir"], "uid": s["uid"]}, marc)
    checar(u"  (isca, o campo) sem soltar, a tela diz «parou aqui» e «sem "
           u"sinal de vida»", sit.get("situacao") == "retomavel"
           and u"parou aqui" in sit.get("detalhe", u""), str(sit))
    andamento = _em_andamento_do_registro()
    checar(u"o caso ficou «em andamento» no registro", len(andamento) == 1,
           str(andamento))
    casos0 = _casos_do_registro()
    mod2 = carregar(root, base, {"DRY_RUN": "0", "TASKS": "total_v3"})
    fechados = mod2.fechar_casos_interrompidos()
    novos = _casos_do_registro() - casos0
    d = {}
    if novos:
        d = json.load(io.open(os.path.join(_REGISTRO_TESTE, "casos",
                                           sorted(novos)[0], "caso.json"),
                              encoding="utf-8"))
    res = d.get("resultado") or {}
    checar(u"ao abrir, o caso vira «interrompido», com a ultima etapa e a hora",
           len(fechados) == 1 and res.get("interrompido") is True
           and res.get("ultima_etapa") == u"total_v3"
           and len(res.get("hora_da_etapa") or u"") >= 16
           and not _em_andamento_do_registro(), str(res)[:200])
    soltas = mod2.soltar_travas_mortas_do_indice()
    checar(u"ao abrir (pelo indice da varredura, com o vigia ligado ou nao), "
           u"a trava desta maquina de processo morto e solta",
           soltas == 1 and not mod2.has_marker(s["dir"], s["uid"], "lock"),
           str(soltas))
    series2, _d = mod2.scan_root()
    checar(u"  e a varredura seguinte nao tem mais trava para soltar",
           mod2.soltar_travas_mortas_ao_abrir(series2) == 0)
    fq = _app_import("radai_queue_state")
    fq.limpar()
    mod2._publicar_fila_do_vigia(mod2.build_queue(series2, _d))
    cards = [c for c in fq.cards() if c.get("uid") == s["uid"]]
    checar(u"  e a serie volta para a fila do vigia, com a linha no cartao",
           cards and cards[0].get("mensagem")
           == mod2.FRASE_DA_TRAVA_SOLTA_AO_ABRIR, str(cards)[:200])
    sit2 = L._situacao({"pasta": s["dir"], "uid": s["uid"]}, marc)
    checar(u"  e a tela deixa de dizer «parou no meio»",
           sit2.get("situacao") == "livre", str(sit2))
    fq.limpar()


def teste_fechar_pelo_x_nao_mata_a_serie():
    secao(u"fechar pelo X nao mata a serie em curso; o Fechar tudo, sim")
    rp = _app_import("radai_pulso")

    class _Relogio(object):
        t = 1000.0

        def __call__(self):
            return self.t
    rel = _Relogio()
    p = rp.Pulso(180.0, relogio=rel, graca_s=15.0)
    p.bater("aba1")
    em = {"o_que": u"a serie do vigia esta rodando"}
    eventos = []
    v = rp.Vigilancia(p, lambda: eventos.append("encerrou"), lambda: True,
                      log=lambda m: eventos.append(m), acordado=lambda s: True,
                      navegador_aberto=lambda: False,
                      em_curso=lambda: em["o_que"],
                      ao_adiar=lambda sim: eventos.append(("adiar", sim)))
    p.sair("aba1")
    rel.t += 16
    v.passo()
    checar(u"a ultima aba fechou com a serie rodando: nada e encerrado",
           "encerrou" not in eventos and v.adiando, str(eventos))
    checar(u"  e a fila e segurada (nao comeca outra serie)",
           ("adiar", True) in eventos)
    rel.t += 600
    v.passo()
    checar(u"  dez minutos depois, com a serie ainda rodando, continua",
           "encerrou" not in eventos)
    em["o_que"] = u"o turno da noite esta aberto"
    rel.t += 600
    v.passo()
    checar(u"  com o turno da noite aberto, segue o turno",
           "encerrou" not in eventos)
    em["o_que"] = None
    v.passo()
    checar(u"a serie terminou (e o turno fechou): encerra",
           "encerrou" in eventos)
    p2 = rp.Pulso(180.0, relogio=rel, graca_s=15.0)
    p2.bater("a")
    ev2 = []
    v2 = rp.Vigilancia(p2, lambda: ev2.append("encerrou"), lambda: False,
                       log=lambda m: None, acordado=lambda s: True,
                       navegador_aberto=lambda: False,
                       em_curso=lambda: None, ao_adiar=lambda s: ev2.append(s))
    p2.sair("a")
    rel.t += 16
    v2.passo()
    checar(u"parado: encerra nos 15 s de sempre", ev2 == ["encerrou"], str(ev2))
    p3 = rp.Pulso(180.0, relogio=rel, graca_s=15.0)
    p3.bater("a")
    ev3 = []
    v3 = rp.Vigilancia(p3, lambda: ev3.append("encerrou"), lambda: True,
                       log=lambda m: None, acordado=lambda s: True,
                       navegador_aberto=lambda: False,
                       em_curso=lambda: u"a serie do vigia esta rodando",
                       ao_adiar=lambda s: ev3.append(("adiar", s)))
    p3.sair("a")
    rel.t += 16
    v3.passo()
    p3.bater("b")
    v3.passo()
    checar(u"a tela voltou antes de a serie acabar: o encerramento e "
           u"cancelado e a fila solta",
           ev3 == [("adiar", True), ("adiar", False)] and not v3.adiando,
           str(ev3))
    ev4 = []
    v4 = rp.Vigilancia(rp.Pulso(180.0, relogio=rel, graca_s=15.0),
                       lambda: ev4.append("encerrou"), lambda: True,
                       log=lambda m: None, acordado=lambda s: True,
                       navegador_aberto=lambda: False)
    v4.pulso.bater("a")
    v4.pulso.sair("a")
    rel.t += 16
    v4.passo()
    checar(u"(isca) sem quem diga o que roda, o X encerra no meio da serie "
           u"(o defeito do campo)", ev4 == ["encerrou"], str(ev4))
    agora = datetime.now()
    mod, root, base = montar([("PAC_FECHAR", agora - timedelta(days=1), 8)])
    fq = _app_import("radai_queue_state")
    mod.STATE["current"] = {"uid": "12345678", "pid": "PAC_FECHAR"}
    try:
        checar(u"o vigia diz o que segura o fechar, sem o PatientID",
               mod.o_que_segura_o_fechar() == u"a serie do vigia esta rodando")
        mod.STATE["current"] = None
        mod.STATE["overnight"] = True
        checar(u"  e o turno da noite aberto tambem segura",
               mod.o_que_segura_o_fechar() == u"o turno da noite esta aberto")
    finally:
        mod.STATE["current"] = None
        mod.STATE["overnight"] = False
    L = _app_import("radai_batch")
    fq.limpar()
    manual = {"uid": "1.2.826.0.1.3680043.8.498.4242", "pasta": base}
    fq.acrescentar_series([dict(manual)])
    mod._segurar_a_fila_ao_fechar(True)
    try:
        checar(u"segurada a fila, a estacao diz que fecha ao fim",
               fq.fechando_ao_fim() is True)
        envelhecer(root, 60)
        mod.STATE["ligado"] = True
        estado = {"fila": None, "proxima_varredura": 0.0, "turno": True}
        linhas_do_laco = []
        velho_wlog = mod.wlog
        mod.wlog = lambda m="": linhas_do_laco.append(str(m))
        try:
            mod._uma_volta(estado)
        finally:
            mod.wlog = velho_wlog
        checar(u"  e o laco diz por que espera numa frase que nao supoe quem "
               u"pediu (o X ou a atualizacao em espera)",
               mod.FRASE_DO_FECHAR_AO_FIM in linhas_do_laco
               and not [l for l in linhas_do_laco
                        if u"navegador foi fechado" in l],
               str(linhas_do_laco)[-300:])
        checar(u"  e o vigia nao reivindica serie nova",
               not [q for q in fila_de(mod)[0]
                    if mod.has_marker(q["dir"], q["uid"], "lock")])
        checar(u"  e o lote nao comeca a proxima serie (nem a da lista, nem "
               u"a da fila)",
               list(L._series_a_rodar([dict(manual)], False)) == []
               and list(L._series_a_rodar([], True)) == [])
    finally:
        mod._segurar_a_fila_ao_fechar(False)
    checar(u"  solta a fila, o lote anda de novo",
           len(list(L._series_a_rodar([dict(manual)], False))) == 1)
    fq.limpar()
    checar(u"o «Fechar tudo» continua dizendo que interrompe a serie em curso",
           u"Fechar tudo interrompe esse trabalho" in io.open(
               _componentes.fonte("app/radai_shutdown.py"),
               encoding="utf-8").read())


def teste_o_turno_na_fila_segura_o_fechar_e_a_tela_que_volta_solta_o_lote():
    secao(u"o X com o turno da noite na fila segue ate o turno; a tela que "
          u"volta solta o lote")
    agora = datetime.now()
    mod, root, base = montar([("PAC_TURNO", agora - timedelta(days=1), 8)])
    fq = _app_import("radai_queue_state")
    L = _app_import("radai_batch")
    velho_and, velho_ini, velha_fila = L.andamento, L.iniciar, \
        mod._fila_da_estacao
    velho_cfg = dict(L._CFG)
    pedidos = []
    try:
        fq.limpar()
        fq.overnight(True)
        L.andamento = lambda: {"rodando": True}
        checar(u"turno agendado com o lote andando ate ele: o X segura",
               mod.o_que_segura_o_fechar() == u"o turno da noite esta na fila")
        mod._fila_da_estacao = lambda nome, *a, **k: pedidos.append(nome)
        mod._segurar_a_fila_ao_fechar(True)
        checar(u"  e nao segura a fila: o lote segue ate abrir o turno",
               "pedir_fechar_ao_fim" not in pedidos, str(pedidos))
        mod._fila_da_estacao = velha_fila
        L.andamento = lambda: {"rodando": False, "terminando": True}
        checar(u"  na passagem do fim do lote para o turno, continua segurando",
               mod.o_que_segura_o_fechar() == u"o turno da noite esta na fila")
        L.andamento = lambda: {"rodando": True, "pausar": True}
        checar(u"lote pausado (o turno nunca chegaria): o X encerra",
               mod.o_que_segura_o_fechar() is None)
        L.andamento = lambda: {"rodando": False}
        checar(u"lote parado (o turno nao abre sozinho): o X encerra",
               mod.o_que_segura_o_fechar() is None)
        L.andamento = lambda: {"rodando": True}
        velho_ts = mod._turno_segue_na_fila
        mod._turno_segue_na_fila = lambda: False
        checar(u"(isca) sem olhar o turno agendado, o X encerra antes do turno",
               mod.o_que_segura_o_fechar() is None)
        mod._turno_segue_na_fila = velho_ts
        fq.limpar()
        checar(u"sem turno na fila, o lote sozinho nao segura por aqui",
               mod.o_que_segura_o_fechar() is None)
        L.andamento = velho_and
        manual = {"uid": "1.2.826.0.1.3680043.8.498.4343", "pasta": base}
        fq.acrescentar_series([dict(manual)])
        mod._segurar_a_fila_ao_fechar(True)
        checar(u"o X com o lote rodando segura a fila",
               fq.fechando_ao_fim() is True)
        checar(u"  e o lote para entre series, marcando que parou ao fechar",
               list(L._series_a_rodar([], True)) == []
               and L._JOB.get("parou_ao_fechar") is True)
        iniciados = []
        L.iniciar = lambda series, **k: (iniciados.append(list(series))
                                         or {"ok": True})
        L._CFG.update({"device": "cpu"})
        mod._segurar_a_fila_ao_fechar(False)
        checar(u"a tela voltou: o encerramento cancela e o lote anda sozinho",
               fq.fechando_ao_fim() is False and len(iniciados) == 1
               and iniciados[0][0].get("uid") == manual["uid"],
               str(iniciados)[:200])
        mod._segurar_a_fila_ao_fechar(False)
        checar(u"  uma vez so", len(iniciados) == 1)
        checar(u"(isca) o lote que nao parou ao fechar nao e relancado",
               L.retomar_o_lote_que_parou_ao_fechar() is None
               and len(iniciados) == 1)
    finally:
        L.andamento, L.iniciar = velho_and, velho_ini
        mod._fila_da_estacao = velha_fila
        L._CFG.clear()
        L._CFG.update(velho_cfg)
        L._JOB["parou_ao_fechar"] = False
        fq.pedir_fechar_ao_fim(False)
        fq.limpar()


def teste_o_pid_reaproveitado_e_dono_morto():
    secao(u"a trava desta maquina com o PID reaproveitado e de dono morto")
    if os.name != "nt":
        checar(u"(so no Windows) o instante de criacao vem do GetProcessTimes",
               True)
        return
    import subprocess as _sp
    agora = datetime.now()
    mod, root, base = montar([("PAC_PID", agora - timedelta(days=1), 8)])
    envelhecer(root, 60)
    s = list(mod.scan_root()[0].values())[0]
    filho = _sp.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
    velho_parado = mod.LOCK_PARADO_S
    mod.LOCK_PARADO_S = 1.0
    try:
        time.sleep(2.5)
        criado = mod._criado_em(filho.pid)
        checar(u"o instante de criacao do processo e lido",
               isinstance(criado, int) and criado > 0, str(criado))
        velho = time.time() - 3600
        recente = time.time() - 1.2

        def _trava(hb, **extra):
            d = {"machine": "PC_A", "pid_os": filho.pid,
                 "token": "PC_A#%d" % filho.pid, "heartbeat": hb,
                 "start": (agora - timedelta(hours=2)).strftime(
                     "%Y-%m-%d %H:%M:%S")}
            d.update(extra)
            mod.m_path(s["dir"], s["uid"], "lock", criar=True).write_text(
                json.dumps(d), encoding="utf-8")
        _trava(velho)
        checar(u"PID vivo, mas criado depois do ultimo sinal da trava: dono "
               u"morto", mod._diagnostico_do_lock(s["dir"], s["uid"])[0]
               == "morto")
        _trava(recente)
        checar(u"  criado antes do ultimo sinal: o dono vive (travado)",
               mod._diagnostico_do_lock(s["dir"], s["uid"])[0] == "travado")
        _trava(recente, criado=criado + 1)
        checar(u"  o instante gravado na trava manda: diferente, dono morto",
               mod._diagnostico_do_lock(s["dir"], s["uid"])[0] == "morto")
        _trava(velho, criado=criado)
        checar(u"  igual, dono vivo",
               mod._diagnostico_do_lock(s["dir"], s["uid"])[0] == "travado")
        mortos = []
        velho_matar = mod._matar_travado
        mod._matar_travado = lambda pid, uid: mortos.append(pid)
        try:
            _trava(velho)
            mod.claim(s["dir"], s["uid"], {"machine": "PC_A",
                                           "pid_os": os.getpid()})
            checar(u"o claim sobre a trava do PID reaproveitado nao encerra "
                   u"processo nenhum", mortos == [], str(mortos))
            mod.unclaim(s["dir"], s["uid"])
        finally:
            mod._matar_travado = velho_matar
        _trava(velho)
        dono_vivo = mod._dono_da_trava_vivo
        mod._dono_da_trava_vivo = (lambda d, pid=None, **k: mod._processo_vivo(
            pid or d.get("pid_os")))
        checar(u"(isca) so com o OpenProcess, o PID reaproveitado parece o dono "
               u"vivo", mod._diagnostico_do_lock(s["dir"], s["uid"])[0]
               == "travado")
        mod._dono_da_trava_vivo = dono_vivo
        mod.TRAVAS_SOLTAS_AO_ABRIR.clear()
        n = mod.soltar_travas_mortas_ao_abrir({s["uid"]: s})
        checar(u"ao abrir, a trava do PID reaproveitado e solta, com a linha "
               u"do cartao", n == 1
               and not mod.has_marker(s["dir"], s["uid"], "lock")
               and s["uid"] in mod.TRAVAS_SOLTAS_AO_ABRIR)
        mod.claim(s["dir"], s["uid"], {"machine": "PC_A",
                                       "pid_os": os.getpid()})
        minha = mod.read_marker(s["dir"], s["uid"], "lock") or {}
        checar(u"a trava nova leva o instante de criacao do dono",
               minha.get("criado") == mod._criado_em(os.getpid()))
        mod.unclaim(s["dir"], s["uid"])
    finally:
        mod.LOCK_PARADO_S = velho_parado
        filho.kill()
        filho.wait(10)


def teste_o_processo_que_saiu_e_dono_morto_com_o_handle_aberto():
    secao(u"o processo que saiu e dono morto, mesmo com alguem segurando o "
          u"handle dele")
    if os.name != "nt":
        checar(u"(so no Windows) o codigo de saida vem do GetExitCodeProcess",
               True)
        return
    import ctypes
    import subprocess as _sp
    from ctypes import wintypes

    def _so_abre(pid):
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.OpenProcess.restype = wintypes.HANDLE
        h = k32.OpenProcess(0x1000, False, int(pid))
        if h:
            k32.CloseHandle(h)
        return bool(h)
    agora = datetime.now()
    mod, root, base = montar([("PAC_ZUMBI", agora - timedelta(days=1), 8)])
    envelhecer(root, 60)
    s = list(mod.scan_root()[0].values())[0]
    filho = _sp.Popen([sys.executable, "-c", "import os; os._exit(9)"])
    filho.wait(60)
    checar(u"o processo saiu (codigo 9), e o Popen ainda segura o handle dele",
           filho.returncode == 9, str(filho.returncode))
    checar(u"o processo que saiu nao conta como vivo",
           mod._processo_vivo(filho.pid) is False)
    checar(u"(isca) so com o OpenProcess, o processo que saiu parece vivo",
           _so_abre(filho.pid) is True)
    mod.m_path(s["dir"], s["uid"], "lock", criar=True).write_text(json.dumps({
        "machine": mod.MACHINE, "pid_os": filho.pid,
        "token": "%s#%d" % (mod.MACHINE, filho.pid),
        "heartbeat": time.time() - 1.0, "criado": mod._criado_em(filho.pid),
        "start": agora.strftime("%Y-%m-%d %H:%M:%S")}), encoding="utf-8")
    checar(u"a trava dele, com batimento recente, e de dono morto",
           mod._diagnostico_do_lock(s["dir"], s["uid"])[0] == "morto")
    vivo = mod._processo_vivo
    mod._processo_vivo = _so_abre
    try:
        checar(u"(isca) so com o OpenProcess, a trava parece «trabalhando» "
               u"(a tela dizia «processando» de um processo que morreu)",
               mod._diagnostico_do_lock(s["dir"], s["uid"])[0]
               == "trabalhando")
    finally:
        mod._processo_vivo = vivo
    checar(u"e ao abrir ela e solta",
           mod.soltar_trava_morta(s["dir"], s["uid"]) is True
           and not mod.has_marker(s["dir"], s["uid"], "lock"))
    del filho


def teste_o_marcador_da_v84_sem_rtstruct_volta_para_a_fila():
    secao(u"o marcador de pronta que a v8.4 gravou sem RTSTRUCT nao vale")
    agora = datetime.now()
    mod, root, base = montar([("PAC_SEM_RS", agora - timedelta(days=3), 8),
                              ("PAC_COM_RS", agora - timedelta(days=2), 8),
                              ("PAC_ENSAIO", agora - timedelta(days=1), 8)])
    envelhecer(root, 60)
    series, _ = mod.scan_root()
    por_pid = dict((s["pid"], s) for s in series.values())
    for pid, s in por_pid.items():
        done = {"uid": s["uid"], "date": s["date"], "machine": "PC_A",
                "finished": "2026-10-14 17:15:00", "ver": "8.4",
                "parcial": {"motivo": u"faltou abdominal_muscles"}}
        if pid == "PAC_ENSAIO":
            done["dry_run"] = True
        mod.m_path(s["dir"], s["uid"], "done", criar=True).write_text(
            json.dumps(done), encoding="utf-8")
    com = por_pid["PAC_COM_RS"]
    with open(os.path.join(com["dir"], "RS_RadAI_PAC_%s.dcm"
                           % com["uid"][-8:].lower()), "wb") as f:
        f.write(b"\0" * 200)
    sem = por_pid["PAC_SEM_RS"]
    L = _app_import("radai_batch")
    marc = {"has_marker": mod.has_marker, "read_marker": mod.read_marker,
            "sem_rtstruct": mod.marcador_sem_rtstruct,
            "sem_rtstruct_afastado": mod.marcador_sem_rtstruct_afastado}
    checar(u"o «Rodar agora» mostra a serie do marcador sem arquivo como a "
           u"refazer",
           L._situacao({"pasta": sem["dir"], "uid": sem["uid"]}, marc)
           .get("situacao") == "refazer")
    checar(u"  e a que tem o RTSTRUCT continua concluida",
           L._situacao({"pasta": com["dir"], "uid": com["uid"]}, marc)
           .get("situacao") == "concluida")
    velho = mod._rtstruct_da_serie_em
    mod._rtstruct_da_serie_em = lambda *a, **k: None
    try:
        checar(u"pasta que nao se lista nao e ausencia: o marcador vale",
               mod.marcador_sem_rtstruct(sem["dir"], sem["uid"]) is False)
    finally:
        mod._rtstruct_da_serie_em = velho
    publicados = []
    velha_fila = mod._fila_da_estacao
    mod._fila_da_estacao = lambda nome, *a, **k: publicados.append((nome, a))
    try:
        fila, _ = fila_de(mod)
        mod._publicar_fila_do_vigia(fila)
    finally:
        mod._fila_da_estacao = velha_fila
    pids = pids_da_fila(fila)
    checar(u"o marcador sem arquivo nao e pronta: a serie volta para a fila "
           u"do vigia", "PAC_SEM_RS" in pids, str(pids))
    checar(u"  a que tem o RTSTRUCT e a do ensaio continuam prontas",
           "PAC_COM_RS" not in pids and "PAC_ENSAIO" not in pids, str(pids))
    checar(u"  o marcador sem arquivo foi afastado, e nao apagado",
           not mod.has_marker(sem["dir"], sem["uid"], "done")
           and mod.has_marker(sem["dir"], sem["uid"],
                              mod.MARCADOR_SEM_RTSTRUCT))
    itens = [a[0] for n, a in publicados if n == "vigia_na_fila"]
    linha = [it.get("mensagem") for it in (itens[-1] if itens else [])
             if it.get("uid") == sem["uid"]]
    checar(u"  e o cartao do vigia leva a linha «marcador sem RTSTRUCT: "
           u"refazendo»",
           linha == [u"marcador sem RTSTRUCT: refazendo"], str(linha))
    checar(u"  o «Rodar agora» continua mostrando a refazer depois de "
           u"afastado",
           L._situacao({"pasta": sem["dir"], "uid": sem["uid"]}, marc)
           .get("situacao") == "refazer")
    mod.claim(sem["dir"], sem["uid"], {})
    mod.process_series(sem)
    checar(u"refeita, o marcador afastado sai, e a linha tambem",
           mod.has_marker(sem["dir"], sem["uid"], "done")
           and not mod.has_marker(sem["dir"], sem["uid"],
                                  mod.MARCADOR_SEM_RTSTRUCT)
           and sem["uid"] not in mod.MARCADORES_SEM_RTSTRUCT)
    mod2, root2, base2 = montar([("PAC_ISCA", agora - timedelta(days=3), 8)])
    envelhecer(root2, 60)
    s2 = list(mod2.scan_root()[0].values())[0]
    mod2.m_path(s2["dir"], s2["uid"], "done", criar=True).write_text(
        json.dumps({"uid": s2["uid"], "ver": "8.4"}), encoding="utf-8")
    mod2.afastar_marcador_sem_rtstruct = lambda *a, **k: False
    checar(u"(isca) sem afastar o marcador sem arquivo, a serie fica pulada "
           u"como pronta (o defeito do campo)",
           "PAC_ISCA" not in pids_da_fila(fila_de(mod2)[0]))


def teste_a_falha_do_import_fora_do_caminho_volta_a_fila():
    secao("a serie que falhou pelo import fora do caminho volta a fila")
    agora = datetime.now()
    mod, root, base = montar([("PAC_ARQ", agora - timedelta(days=1), 8),
                              ("PAC_OUTRA", agora - timedelta(days=2), 8)])
    envelhecer(root, 60)
    series, done = mod.scan_root()
    por_pid = dict((s["pid"], (uid, s)) for uid, s in series.items())
    uid_a, s_a = por_pid["PAC_ARQ"]
    uid_b, s_b = por_pid["PAC_OUTRA"]
    mod.m_path(s_a["dir"], uid_a, "fail", criar=True).write_text(json.dumps(
        {"tries": 3, "last_error": "name '_arq' is not defined",
         "ultimo_tipo": "deterministico", "assinatura": "e7d4e7d7d2",
         "em_espera": "e7d4e7d7d2"}), encoding="utf-8")
    mod.m_path(s_b["dir"], uid_b, "fail", criar=True).write_text(json.dumps(
        {"tries": 3, "last_error": "outra causa, de verdade"}),
        encoding="utf-8")
    fila = mod.build_queue(series, done)
    checar("a serie da assinatura do import volta a fila",
           [s["uid"] for s in fila] == [uid_a], str([s["pid"] for s in fila]))
    checar("  e o marcador de falha dela saiu",
           not mod.has_marker(s_a["dir"], uid_a, "fail"))
    checar("  (isca) a que falhou por outra causa continua fora, com o marcador",
           [x["uid"] for x in mod.PULADAS_POR_FALHA] == [uid_b]
           and mod.has_marker(s_b["dir"], uid_b, "fail"))
    checar("  e o log diz por que ela voltou",
           "import fora do caminho" in "\n".join(list(mod.LOGBUF)))


def teste_a_fila_que_esvazia_depois_de_uma_pronta_revarre_na_hora():
    secao("a fila do vigia que esvazia depois de uma serie pronta revarre na hora")
    agora = datetime.now()
    mod, root, base = montar([("PAC_REV", agora - timedelta(days=1), 8)])
    envelhecer(root, 60)
    estado = {"fila": None, "proxima_varredura": 0.0}
    for _ in range(10):
        mod._uma_volta(estado)
        if mod.STATE["done_today"]:
            break
    checar("a serie ficou pronta", mod.STATE["done_today"] >= 1,
           str(mod.STATE["done_today"]))
    checar("  e a proxima varredura e agora, e nao daqui a SCAN_EVERY",
           estado.get("proxima_varredura") == 0.0,
           str(estado.get("proxima_varredura")))
    checar("  e o log diz por que", "varro de novo agora" in
           "\n".join(list(mod.LOGBUF)))

    mod2, root2, base2 = montar([("PAC_FALHA", agora - timedelta(days=1), 8)],
                                machine="PC_FALHA")
    envelhecer(root2, 60)
    mod2.process_series = lambda s: False
    estado2 = {"fila": None, "proxima_varredura": 0.0}
    mod2._uma_volta(estado2)
    if estado2.get("fila"):
        mod2._uma_volta(estado2)
    checar("(isca) a que nao ficou pronta espera o intervalo",
           estado2.get("proxima_varredura", 0) > time.time() + 60,
           str(estado2.get("proxima_varredura")))


def teste_tres_falhas_de_recurso_seguidas_param_o_vigia():
    secao(u"tres falhas de recurso seguidas no mesmo processo: o vigia para de "
          u"pegar serie nova, e um sucesso zera a conta")
    agora = datetime.now()
    cfg = {"DRY_RUN": "0", "TASKS": "total_v3", "INCLUIR_NV": "0",
           "INCLUIR_CADS": "0", "INCLUIR_MOOSE": "0", "INCLUIR_HNLNL": "0"}
    mod, root, base = montar([("PAC_R%d" % i, agora - timedelta(days=i), 8)
                              for i in range(1, 6)], extra=cfg)
    envelhecer(root, 60)
    fila, _ = fila_de(mod)
    if len(fila) != 5:
        checar(u"as cinco series entraram na fila", False, len(fila))
        return
    falha = lambda: _MotorAnatomico(base, set(),
                                    erro_na={"total_v3": MemoryError()})
    mod.carregar_engine = falha
    checar(u"a conta nasce zerada", not mod.recurso_esgotado())
    for s in fila[:2]:
        mod.claim(s["dir"], s["uid"], {})
        mod.process_series(s)
    checar(u"  duas falhas de recurso ainda nao param o vigia",
           not mod.recurso_esgotado(), mod._RECURSO_SEGUIDO)
    mod.claim(fila[2]["dir"], fila[2]["uid"], {})
    mod.process_series(fila[2])
    checar(u"  a terceira seguida para", mod.recurso_esgotado(),
           mod._RECURSO_SEGUIDO)
    publicados = []
    velha_fila = mod._fila_da_estacao
    mod._fila_da_estacao = (lambda nome, *a, **k: publicados.append((nome, a))
                            or (True if nome == "tentar_a_vez" else None))
    try:
        estado = {"fila": [fila[3], fila[4]], "proxima_varredura":
                  time.time() + 3600}
        mod._uma_volta(estado)
    finally:
        mod._fila_da_estacao = velha_fila
    checar(u"com a conta no teto, a volta do vigia nao pega a proxima serie",
           not mod.has_marker(fila[3]["dir"], fila[3]["uid"], "lock")
           and not mod.has_marker(fila[3]["dir"], fila[3]["uid"], "fail")
           and len(estado["fila"]) == 2, [n for n, _a in publicados])
    itens = [a[0] for n, a in publicados if n == "vigia_na_fila"]
    linha = [it.get("mensagem") for it in (itens[-1] if itens else [])][:1]
    checar(u"  e o cartao da proxima diz «%s»" % mod.FRASE_DO_RECURSO_ESGOTADO,
           linha == [mod.FRASE_DO_RECURSO_ESGOTADO], str(linha))
    log = u""
    for d, _, fs in os.walk(base):
        for f in fs:
            if f.endswith(".log") and "log_PC_A" in d:
                log += io.open(os.path.join(d, f), encoding="utf-8",
                               errors="replace").read()
    checar(u"  e o log diz por que, uma vez",
           log.count(u"o processo parece sem recurso") == 1, log[-300:])
    mod.carregar_engine = lambda: _MotorAnatomico(base, set())
    mod.claim(fila[3]["dir"], fila[3]["uid"], {})
    ok = mod.process_series(fila[3])
    checar(u"um sucesso zera a conta, e o vigia volta a pegar serie",
           ok is True and not mod.recurso_esgotado(), (ok, mod._RECURSO_SEGUIDO))
    mod.recurso_voltou()
    mod.carregar_engine = falha
    for s in (fila[4], fila[0], fila[1]):
        mod.claim(s["dir"], s["uid"], {})
        mod.process_series(s)
    mod.carregar_engine = lambda: _MotorAnatomico(base, set())
    velho = mod.recurso_voltou
    mod.recurso_voltou = lambda: None
    try:
        mod.claim(fila[2]["dir"], fila[2]["uid"], {})
        mod.process_series(fila[2])
        checar(u"  (isca) sem zerar no sucesso, a conta continuaria no teto",
               mod.recurso_esgotado())
    finally:
        mod.recurso_voltou = velho
    mod.carregar_engine = falha
    velho_teto = mod.recurso_esgotado
    mod.recurso_esgotado = lambda: False
    mod._fila_da_estacao = (lambda nome, *a, **k:
                            True if nome == "tentar_a_vez" else None)
    try:
        alvo = fila[1]
        _vezes = lambda: int((mod.read_marker(alvo["dir"], alvo["uid"], "fail")
                              or {}).get(mod.RECURSO, 0) or 0)
        antes = _vezes()
        mod._uma_volta({"fila": [alvo], "proxima_varredura":
                        time.time() + 3600})
        checar(u"  (isca) sem o teto na volta, o vigia pegaria a serie",
               _vezes() == antes + 1, (antes, _vezes()))
    finally:
        mod.recurso_esgotado = velho_teto
        mod._fila_da_estacao = velha_fila
    import ast
    lote = io.open(_componentes.fonte("app/radai_batch.py"),
                   encoding="utf-8").read()
    vig = io.open(_componentes.fonte("app/radai_watcher.py"),
                  encoding="utf-8").read()

    def _avisa_antes_do_pronto(src):
        for n in ast.walk(ast.parse(src)):
            if not isinstance(n, ast.If):
                continue
            for corpo in (n.body, n.orelse):
                chama_pronto = [i for i, st in enumerate(corpo)
                                if "'pronto'" in ast.dump(st)
                                and "_fila_diz" in ast.dump(st)]
                avisa = [i for i, st in enumerate(corpo)
                         if "recurso_voltou" in ast.dump(st)]
                if chama_pronto and avisa and avisa[0] < chama_pronto[0]:
                    return True
        return False
    checar(u"o «Rodar agora» que termina pronto tambem zera a conta (o vigia "
           u"lhe passa recurso_voltou)",
           _avisa_antes_do_pronto(lote)
           and u'"recurso_voltou": recurso_voltou,' in vig)
    isca = lote.replace(u'_voltou = _CFG.get("recurso_voltou")',
                        u'_voltou = _CFG.get("nada")', 1)
    checar(u"  (isca) o lote que nao avisa o sucesso reprova",
           isca != lote and not _avisa_antes_do_pronto(
               isca.replace(u'"recurso_voltou"', u'"nada"')))


def _marcar_pronta(mod, s, maquina):
    mod.m_path(s["dir"], s["uid"], "done", criar=True).write_text(
        json.dumps({"uid": s["uid"], "date": s["date"], "machine": maquina,
                    "finished": "2026-10-15 03:10:00", "ver": "8.5"}),
        encoding="utf-8")


def _linha_do_plano(mod, uid):
    p = mod.plano_de_execucao()
    for ex in p.get("exames") or []:
        for ln in ex.get("series") or []:
            if ln.get("uid") == uid:
                return ln
    return {}


def _vigia_de_fonte(root, base, extra, machine, troca):
    fonte = io.open(_componentes.fonte("app/radai_watcher.py"),
                    encoding="utf-8").read()
    isca = fonte.replace(troca[0], troca[1], 1)
    alvo = os.path.join(base, "vigia_isca_%d.py" % _N[0])
    io.open(alvo, "w", encoding="utf-8").write(isca)
    velho = _componentes.fonte
    _componentes.fonte = (lambda rel, *a, **k: alvo
                          if rel == "app/radai_watcher.py"
                          else velho(rel, *a, **k))
    try:
        return carregar(root, base, extra, machine), isca != fonte
    finally:
        _componentes.fonte = velho


def teste_o_marcador_de_outra_estacao_com_destino_proprio_fica():
    secao(u"o marcador sem RTSTRUCT a vista: so se afasta o desta maquina, ou "
          u"quando o RTSTRUCT vai ao lado da serie")
    agora = datetime.now()
    base = novo_temp()
    root = os.path.join(base, "share")
    for pid, dias in (("PAC_DE_A", 3), ("PAC_DE_B", 2)):
        escreve_serie(os.path.join(root, pid, "CT"), pid,
                      agora - timedelta(days=dias), 8)
    envelhecer(root, 60)
    saida_a = os.path.join(base, "saida_A")
    saida_b = os.path.join(base, "saida_B")
    os.makedirs(saida_a)
    os.makedirs(saida_b)
    a = carregar(root, base, extra={"OUT_DIR": saida_a}, machine="PC_A")
    series, _ = a.scan_root()
    por = dict((s["pid"], s) for s in series.values())
    de_a, de_b = por["PAC_DE_A"], por["PAC_DE_B"]
    _marcar_pronta(a, de_a, "PC_A")
    _marcar_pronta(a, de_b, "PC_B")
    destino_a = a._destino({"dir": de_a["dir"]})
    os.makedirs(str(destino_a), exist_ok=True)
    with open(os.path.join(str(destino_a), "RS_RadAI_OAR_%s.dcm"
                           % de_a["uid"][-8:].lower()), "wb") as f:
        f.write(b"\0" * 200)
    b = carregar(root, base, extra={"OUT_DIR": saida_b}, machine="PC_B")
    checar(u"na B, com destino proprio, o marcador da A (RTSTRUCT no destino "
           u"dela) nao e «sem RTSTRUCT»",
           b.marcador_sem_rtstruct(de_a["dir"], de_a["uid"]) is False
           and b.marcador_de_outra_estacao(de_a["dir"], de_a["uid"]) == u"PC_A")
    checar(u"  e o marcador da propria B, sem RTSTRUCT no destino dela, e",
           b.marcador_sem_rtstruct(de_b["dir"], de_b["uid"]) is True
           and b.marcador_de_outra_estacao(de_b["dir"], de_b["uid"]) == u"")
    pids = pids_da_fila(fila_de(b)[0])
    checar(u"a B nao refaz a serie da A, e refaz a dela",
           "PAC_DE_A" not in pids and "PAC_DE_B" in pids, str(pids))
    checar(u"  o marcador da A continua no lugar (nada afastado)",
           b.has_marker(de_a["dir"], de_a["uid"], "done")
           and not b.has_marker(de_a["dir"], de_a["uid"],
                                b.MARCADOR_SEM_RTSTRUCT))
    ln = _linha_do_plano(b, de_a["uid"])
    checar(u"  o plano da B diz que a serie e pronta pela A, com o RTSTRUCT "
           u"no destino dela",
           ln.get("estado") == "pronto"
           and u"feita por PC_A" in (ln.get("detalhe") or u"")
           and u"destino dela" in (ln.get("detalhe") or u""), str(ln))
    checar(u"na A, o mesmo marcador tem o RTSTRUCT no destino: pronta",
           a.marcador_sem_rtstruct(de_a["dir"], de_a["uid"]) is False
           and a.marcador_de_outra_estacao(de_a["dir"], de_a["uid"]) == u"")
    c = carregar(root, base, extra={}, machine="PC_C")
    _marcar_pronta(c, de_b, "PC_A")
    checar(u"sem destino proprio (o RTSTRUCT vai ao lado da serie), o marcador "
           u"de outra estacao sem arquivo ao lado e afastado",
           c.marcador_sem_rtstruct(de_b["dir"], de_b["uid"]) is True)
    isca, achou = _vigia_de_fonte(
        root, base, {"OUT_DIR": saida_b}, "PC_B",
        (u"        if quem != MACHINE:\n", u"        if False:\n"))
    checar(u"  (a isca acha a pergunta pela maquina)", achou)
    checar(u"  (isca) sem perguntar a maquina, a B afastaria o marcador da A",
           isca.marcador_sem_rtstruct(de_a["dir"], de_a["uid"]) is True)


_ROTEIRO_DA_RESERVA = u"""
var EL = {};
function el(id){
 if(!EL[id]) EL[id] = {id: id, value: '', disabled: false, title: '',
  textContent: '', innerHTML: '', style: {}, attrs: {},
  setAttribute: function(k, v){ this.attrs[k] = v },
  focus: function(){}};
 return EL[id];
}
var document = {getElementById: el};
var CHAMADAS = [], RESP = {};
function fetch(url, o){
 CHAMADAS.push(url + ' ' + ((o && o.body) || ''));
 var r = RESP[url];
 return Promise.resolve({json: function(){ return Promise.resolve(r) }});
}
@FUNCOES@
async function cenario(nome, resp, acao){
 EL = {}; CHAMADAS = []; RESP = resp;
 el('rootIn').value = 'antes';
 await acao();
 await new Promise(function(r){ setTimeout(r, 0) });
 return {nome: nome, root: el('rootIn').value, fav_desligado: el('btFav').disabled,
         fav_titulo: el('btFav').title, mapa: el('fpMapa').textContent,
         mapear_desligado: el('fpMapear').disabled, chamadas: CHAMADAS};
}
(async function(){
 var out = {};
 out.fav = await cenario('fav', {'/api/pastas/favorita': {favorita: 'D:/EXAMES'}}, favUsar);
 out.semfav = await cenario('semfav', {'/api/pastas/favorita': {favorita: ''}}, favUsar);
 out.mapeou = await cenario('mapeou', {'/api/pastas/mapear': {ok: true, novas: ['Z:']},
   '/api/pastas': {caminho: 'Z:', pastas: [], unidades: []}}, mapearUnidade);
 out.cancelou = await cenario('cancelou', {'/api/pastas/mapear':
   {ok: false, cancelado: true, novas: [], erro: 'CANCELADO'}}, mapearUnidade);
 console.log('JSON:' + JSON.stringify(out));
})();
"""


def _funcao_da_pagina(js, nome):
    i = js.find(u"function %s(" % nome)
    if i < 0:
        return u""
    k, prof = js.find(u"{", i), 0
    for j in range(k, len(js)):
        if js[j] == u"{":
            prof += 1
        elif js[j] == u"}":
            prof -= 1
            if prof == 0:
                return js[i:j + 1]
    return u""


def _roteiro_da_reserva(pagina):
    import subprocess
    node = shutil.which("node")
    if not node:
        return None, u"sem node"
    funcoes = u"\n".join(_funcao_da_pagina(pagina, n) for n in (
        "favPintar", "favCarregar", "favUsar", "mapearUnidade", "listarPastas"))
    alvo = os.path.join(novo_temp("radai_reserva_js_"), "t.js")
    io.open(alvo, "w", encoding="utf-8").write(
        _ROTEIRO_DA_RESERVA.replace(u"@FUNCOES@", funcoes))
    r = subprocess.run([node, alvo], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=60)
    for ln in reversed((r.stdout or u"").splitlines()):
        if ln.startswith(u"JSON:"):
            return json.loads(ln[5:]), u""
    return None, ((r.stderr or u"") + (r.stdout or u""))[-400:]


def _a_estrela_preenche(d):
    return bool(d) and (d["fav"]["root"] == u"D:/EXAMES"
                        and not d["fav"]["fav_desligado"]
                        and d["fav"]["fav_titulo"] == u"Preencher com a pasta favorita"
                        and all(c.startswith(u"/api/pastas/favorita ")
                                for c in d["fav"]["chamadas"])
                        and d["semfav"]["root"] == u"antes"
                        and d["semfav"]["fav_desligado"]
                        and d["semfav"]["fav_titulo"]
                        == u"Nenhuma pasta favorita configurada")


def _o_mapear_relista(d):
    return bool(d) and (u'/api/pastas {"caminho":"Z:"}' in d["mapeou"]["chamadas"]
                        and d["mapeou"]["mapa"] == u"Unidade mapeada: Z:"
                        and d["cancelou"]["mapa"] == u"CANCELADO"
                        and not d["cancelou"]["mapear_desligado"]
                        and not any(c.startswith(u"/api/pastas {")
                                    for c in d["cancelou"]["chamadas"]))


def teste_a_pagina_de_reserva_tem_a_estrela_e_o_mapear():
    secao(u"a pagina de reserva (vigia sem o painel): a estrela e o Mapear")
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    import radai_ui
    import radai_varrer
    base = novo_temp("radai_reserva_")
    fav = os.path.join(base, "favorita")
    os.makedirs(os.path.join(fav, "SERIE_1"))
    io.open(os.path.join(fav, "corte.dcm"), "w").close()
    tinha, antes = "radai_panel" in sys.modules, sys.modules.get("radai_panel")
    sys.modules["radai_panel"] = None
    try:
        mod = carregar(os.path.join(base, "share"), base,
                       extra={"PASTA_FAVORITA": fav})
    finally:
        if tinha:
            sys.modules["radai_panel"] = antes
        else:
            sys.modules.pop("radai_panel", None)
    checar(u"sem o painel, o vigia serve a pagina de reserva",
           mod.radai_panel is None, mod._PAINEL_ERRO)
    cli = TestClient(mod.app)
    pag = cli.get("/").text
    checar(u"a estrela da pasta favorita fica ao lado do campo da pasta",
           u'id="btFav"' in pag and radai_ui.icone(u"estrela") in pag
           and pag.find(u'id="rootIn"') < pag.find(u'id="btFav"')
           < pag.find(u'id="btPastas"'))
    checar(u"e o seletor tem o «Mapear nova unidade de rede»",
           u'id="fpMapear"' in pag and u"Mapear nova unidade de rede" in pag
           and radai_ui.icone(u"rede") in pag)
    checar(u"nenhuma marca de icone sobra crua na pagina servida",
           u"@ICO_" not in pag, re.findall(r"@ICO_\w+@", pag)[:3])
    checar(u"  ISCA: a pagina servida crua, como antes, mostrava as marcas",
           u"@ICO_PASTA@" in mod.PAGE)

    def _rotas(cliente):
        pedidos = []
        original = radai_varrer.mapear_unidade
        radai_varrer.mapear_unidade = lambda: (pedidos.append(1) or
                                               {"ok": True, "novas": ["Z:"]})
        os.environ["RADAI_CONFIG"] = str(getattr(mod, "CFG_PATH", u""))
        try:
            rf = cliente.post("/api/pastas/favorita", json={})
            rp = cliente.post("/api/pastas", json={"caminho": fav})
            rm = cliente.post("/api/pastas/mapear", json={})
        finally:
            radai_varrer.mapear_unidade = original
            os.environ.pop("RADAI_CONFIG", None)
        if any(r.status_code != 200 for r in (rf, rp, rm)):
            return None
        return rf.json(), rp.json(), rm.json(), pedidos
    resp = _rotas(cli)
    checar(u"sem o painel, as tres rotas do seletor respondem", resp is not None)
    if resp:
        rf, rp, rm, pedidos = resp
        checar(u"a estrela le a pasta favorita do config",
               rf.get("favorita") == fav, rf)
        checar(u"o seletor lista as pastas, e nunca arquivo",
               [p.get("nome") for p in rp.get("pastas") or []] == ["SERIE_1"]
               and not rp.get("arquivos"), rp)
        checar(u"o Mapear chama o mapeamento do radai_varrer (dublado)",
               pedidos == [1] and rm == {"ok": True, "novas": ["Z:"]}, rm)
    checar(u"  ISCA: sem as rotas da reserva, o seletor respondia 404",
           _rotas(TestClient(FastAPI())) is None)
    original = radai_varrer.mapear_unidade

    def _quebra():
        raise OSError("sem mpr")
    radai_varrer.mapear_unidade = _quebra
    try:
        rm = cli.post("/api/pastas/mapear", json={}).json()
    finally:
        radai_varrer.mapear_unidade = original
    checar(u"a falha do mapeamento volta como erro, sem derrubar a rota",
           rm.get("ok") is False and u"sem mpr" in rm.get("erro", u"")
           and rm.get("novas") == [], rm)

    d, err = _roteiro_da_reserva(pag)
    checar(u"a estrela preenche o campo com a favorita, sem gravar nada, e "
           u"fica apagada sem favorita", _a_estrela_preenche(d), d or err)
    checar(u"o Mapear relista na unidade nova, e o cancelado so diz o motivo",
           _o_mapear_relista(d), d or err)
    isca, err = _roteiro_da_reserva(pag.replace(u"  i.value=f;\n", u"", 1))
    checar(u"  ISCA: a estrela que nao preenche o campo reprova",
           isca is not None and not _a_estrela_preenche(isca), isca or err)
    isca, err = _roteiro_da_reserva(pag.replace(u"return listarPastas(",
                                                u"return (", 1))
    checar(u"  ISCA: o Mapear que nao relista reprova",
           isca is not None and not _o_mapear_relista(isca), isca or err)


def main():
    print("test_watcher | vigia em DRY_RUN sobre fantomas sinteticos")
    testes = [teste_a_escolha_do_operador_manda_na_escada,
              teste_mapeamentos_preguicosos,
              teste_days_back_grande_nao_derruba_o_laco,
              teste_tres_estados_do_lock,
              teste_o_lote_nao_deixa_tx_na_pasta,
              teste_lock_nao_e_reentrante,
              teste_modalidades_ida_e_volta,
              teste_plano_de_execucao, teste_o_botao_rodar_mostra_antes,
              teste_o_plano_diz_quando_e_em_que_modo_ficou_pronto,
              teste_a_conferencia_conta_a_noite_da_anatomia,
              teste_o_vigia_pula_a_saida_do_dicombridge,
              teste_ordem_primeira_execucao, teste_ordem_com_concluidas, teste_days_back,
              teste_duas_maquinas, teste_lock_abandonado, teste_serie_incompleta,
              teste_serie_em_transito, teste_max_retries, teste_pasta_somente_leitura,
              teste_classificacao_de_erro_de_ambiente,
              teste_falha_de_ambiente_nao_queima_a_fila,
              teste_progresso_nao_afoga_o_log, teste_erro_sem_barra_de_progresso,
              teste_liberar_series_puladas,
              teste_varredura_nao_suja_o_share, teste_root_vazio_e_inerte,
              teste_config_tolerante,
              teste_chave_renomeada_continua_sendo_lida,
              teste_as_chaves_que_sairam_e_entraram_na_v83,
              teste_o_plano_tem_localizar_e_o_liberar_mora_no_aviso,
              teste_o_modelo_do_config_e_texto_tecnico,
              teste_o_prefixo_longo_nao_come_o_caminho_relativo,
              teste_out_dir_nao_mistura_pacientes,
              teste_dry_run_ponta_a_ponta, teste_log_nao_expoe_caminho_absoluto,
              teste_etapa_da_serie_atual, teste_tela_do_vigia_explica_os_botoes,
              teste_a_faixa_de_estado_fica_no_topo,
              teste_o_root_vazio_tem_acao,
              teste_o_log_saiu_do_corpo,
              teste_o_log_e_uma_escrita_por_linha_com_data,
              teste_o_rodape_nao_cita_um_sufixo_entre_seis,
              teste_a_fila_nasce_desligada_e_dedica_a_estacao,
              teste_painel_sobe,
              teste_acao_de_outro_site_e_recusada,
              teste_elegibilidade_do_torax,
              teste_pid_de_arquivo_do_share_nao_mata_processo,
              teste_o_uid_nao_tira_o_marcador_da_pasta_do_paciente,
              teste_a_base_e_achada_por_familia_e_nao_pelo_nome,
              teste_task_de_outra_modalidade_e_anunciada,
              teste_a_varredura_leva_a_modalidade,
              teste_o_vigia_registra_o_caso,
              teste_o_caso_do_vigia_com_sucesso,
              teste_o_status_compartilhado_nao_leva_caminho_no_erro,
              teste_a_recusa_do_status_dir_diz_o_que_o_arquivo_leva,
              teste_o_mr_da_tela_de_recuo_segue_o_disco,
              teste_a_pasta_com_espaco_sai_do_caso_do_vigia,
              teste_o_caso_nao_leva_o_paciente_de_outra_serie,
              teste_a_bateria_nao_deixa_pasta_para_tras,
              teste_o_registro_do_caso_nunca_levanta,
              teste_o_arranque_se_explica,
              teste_o_arranque_diz_o_que_nao_mediu,
              teste_a_fila_espera_o_arranque,
              teste_o_relatorio_de_arranque_do_vigia,
              teste_o_arranque_escreve_a_suavizacao_e_o_registro,
              teste_a_tela_de_processamento_nao_abre_cuda_no_vigia,
              teste_a_conferencia_da_estacao_nao_abre_cuda,
              teste_a_secao_de_arquivos_nao_levanta,
              teste_a_sonda_que_falhou_nao_segura_a_tela,
              teste_o_lancador_abre_a_porta_do_config,
              teste_perguntar_se_o_pid_vive_nao_sinaliza_o_processo,
              teste_arvore_do_sincronizador,
              teste_a_espera_pelo_vigia_acusa_quem_morreu,
              teste_a_documentacao_da_api_nao_e_servida,
              teste_o_passo_da_estatistica_so_le_e_diz,
              teste_a_sonda_do_arranque_e_a_da_tela_nao_correm_juntas,
              teste_a_rm_do_pescoco_roda_so_a_base_de_rm_e_leva_a_modalidade,
              teste_a_serie_do_vigia_na_cadeia_da_v82,
              teste_os_niveis_seguem_o_pescoco_e_o_recorte_chega_ao_motor,
              teste_o_lote_recebe_as_funcoes_de_erro_do_vigia,
              teste_a_saida_so_passa_a_modalidade_quando_sabe,
              teste_o_vigia_decide_a_regiao_pela_anatomia,
              teste_o_encefalo_sem_peso_entra_no_faltou_do_vigia,
              teste_a_escada_de_recuperacao,
              teste_o_lock_conta_onde_a_serie_esta,
              teste_a_primeira_entrega_vale,
              teste_o_batimento_nao_regrava_o_lock_que_outra_tomou,
              teste_o_lote_bate_a_reserva_de_entrega,
              teste_o_lock_nao_renasce_e_o_vigia_nao_se_mata,
              teste_a_readocao_e_oar_e_full,
              teste_o_vigia_pula_o_que_o_fast_ja_fez,
              teste_o_vigia_e_sempre_auto_e_nao_grava_ts_cru,
              teste_a_pelve_e_o_coracao_disparam_as_cavidades,
              teste_a_task_travada_vai_para_o_fim_e_volta_uma_vez,
              teste_a_notificacao_nao_derruba_nem_segura_o_laco,
              teste_o_em_uso_diz_segmentando_na_borda_da_serie,
              teste_o_caso_do_vigia_leva_o_processamento_da_v83,
              teste_o_caso_do_lote_e_o_do_vigia_tem_o_mesmo_processamento,
              teste_as_duas_portas_dao_o_mesmo_nome_sem_data,
              teste_a_linha_das_tasks_diz_quem_pediu,
              teste_o_done_afastado_que_ficou_orfao_e_resolvido,
              teste_o_portao_do_host,
              teste_o_vigia_nao_segmenta_cada_fase_do_4d,
              teste_as_falhas_da_serie_levam_o_traceback,
              teste_o_complemento_de_regiao_nao_derruba_a_serie,
              teste_os_passos_do_full_vao_ao_caso_e_nao_ao_lock,
              teste_o_vigia_sinaliza_o_uso_e_apaga_na_saida,
              teste_encerrar_no_meio_nao_gasta_tentativa,
              teste_o_encerramento_solta_os_locks_deste_processo,
              teste_o_config_antigo_e_migrado_uma_vez,
              teste_toda_chave_obsoleta_sai_pela_migracao_de_verdade,
              teste_a_fila_ocupada_e_trabalho_e_nao_vigia_ligado,
              teste_o_vigia_nao_tem_print_orfao,
              teste_o_tempo_de_cada_etapa_vai_ao_log,
              teste_toda_saida_da_serie_solta_a_trava,
              teste_a_janela_entre_o_claim_e_a_serie,
              teste_a_serie_que_morre_no_meio_deixa_o_rastro,
              teste_fechar_pelo_x_nao_mata_a_serie,
              teste_o_turno_na_fila_segura_o_fechar_e_a_tela_que_volta_solta_o_lote,
              teste_o_pid_reaproveitado_e_dono_morto,
              teste_o_processo_que_saiu_e_dono_morto_com_o_handle_aberto,
              teste_o_marcador_da_v84_sem_rtstruct_volta_para_a_fila,
              teste_o_marcador_de_outra_estacao_com_destino_proprio_fica,
              teste_tres_falhas_de_recurso_seguidas_param_o_vigia,
              teste_a_falha_do_import_fora_do_caminho_volta_a_fila,
              teste_a_fila_que_esvazia_depois_de_uma_pronta_revarre_na_hora,
              teste_a_pagina_de_reserva_tem_a_estrela_e_o_mapear]
    for t in testes:
        try:
            t()
        except Exception as e:
            import traceback
            checar("%s (excecao inesperada)" % t.__name__, False,
                   "%s: %s" % (type(e).__name__, e))
            traceback.print_exc()

    _soltar_logs()
    for d in _TEMPS:
        shutil.rmtree(d, ignore_errors=True)

    falhas = [(n, d) for n, ok, d in _RESULTADOS if not ok]
    print("\n" + "=" * 64)
    if falhas:
        print("FALHOU: %d de %d checagens" % (len(falhas), len(_RESULTADOS)))
        for n, d in falhas:
            print("  - %s%s" % (n, ("  [%s]" % d) if d else ""))
    else:
        print("OK: %d checagens, todas passaram" % len(_RESULTADOS))
    print("=" * 64)
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
