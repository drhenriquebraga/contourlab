# -*- coding: utf-8 -*-
import os
import subprocess
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.abspath(os.path.join(AQUI, ".."))
for _c in (os.path.join(RAIZ, "app"), RAIZ):
    if os.path.exists(os.path.join(_c, "radai_arranque.py")):
        APP = _c
        sys.path.insert(0, _c)
        break
sys.path.insert(0, AQUI)
import _cleanup
_cleanup.adotar_prefixo("radai_teste_arrdev_")
os.environ.setdefault("RADAI_CALIB_DIR",
                      _cleanup.temporaria("radai_teste_arrdev_ac_"))

import radai_arranque as RA
import radai_devices as RD

VERBOSO = "-v" in sys.argv
_R = []


def checar(nome, ok, detalhe=""):
    ok = bool(ok)
    _R.append((nome, ok, detalhe))
    if VERBOSO or not ok:
        print(u"  %s  %s%s" % ("OK   " if ok else "FALHA", nome,
                               (u"  [%s]" % (detalhe,)) if detalhe else u""))
    return ok


def secao(t):
    print(u"\n-- %s --" % t)


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


def _inv_iris(openvino=False):
    placa = RD._placa({"nome": "Intel(R) Iris(R) Xe Graphics",
                       "fabricante": "Intel Corporation",
                       "driver": "32.0.101.7076", "data": "2025-09-11",
                       "ram": 2147479552, "pnp": "PCI\\VEN_8086&DEV_A7A1"}, {})
    sondas = {"torch": {"importa": True, "versao": "2.5.1+cu121", "cuda": "12.1",
                        "cuda_disponivel": False, "xpu_disponivel": False,
                        "xpu_motivo": "torch 2.5.1+cu121: xpu.is_available() falso"},
              "directml": {"importa": False, "erro": "torch_directml nao instalado"},
              "openvino": ({"importa": True, "versao": "2026.4.0",
                            "dispositivos": {"CPU": "i7", "GPU": "Iris Xe"}}
                           if openvino else
                           {"importa": False, "erro": "openvino nao instalado"})}
    return {"quando": "agora", "placas": [placa], "placas_fonte": u"CIM",
            "placas_falha": u"", "nvidia": {"placas": [], "falha": u"x"},
            "cpu": {"fisicos": 10, "logicos": 12, "classes": {1: 2, 0: 8},
                    "nome": "13th Gen Intel(R) Core(TM) i7-1355U"},
            "memoria": {}, "sondas": sondas,
            "backends": RD.backends_das_sondas(sondas), "segundos": 0.1}


def _ctx(pasta, dry_run=False):
    linhas = []
    return {"log": linhas.append, "python_exe": sys.executable,
            "pasta_trabalho": pasta, "dry_run": dry_run}, linhas


def _rel(com_torch=True):
    rel = {"dados": {}, "avisos": [], "pendencias": []}
    if com_torch:
        rel["dados"]["torch"] = {"importa": True, "versao": "2.5.1+cu121",
                                 "cuda": "12.1", "disponivel": False, "n": 0,
                                 "placas": [], "xpu_disponivel": False}
    return rel


def teste_a_placa_que_existe_e_nomeada():
    secao(u"1 · a placa que nao e NVIDIA e nomeada, e vira aviso")
    pasta = _cleanup.temporaria("radai_teste_arrdev_")
    ctx, _l = _ctx(pasta, dry_run=True)
    rel = _rel()
    with _Troca(RD, inventario=lambda **k: _inv_iris()):
        L = RA._p_computacao(ctx, rel)
    t = u"\n".join(L)
    checar(u"a Iris Xe sai no log com «o TotalSegmentator nao usa»",
           u"Iris(R) Xe" in t and u"nao usa" in t, L[:2])
    checar(u"  e vira AVISO do bloco (nao ha NVIDIA)",
           any(u"Iris(R) Xe" in a and u"NAO usa" in a for a in rel["avisos"]),
           rel["avisos"])
    checar(u"a CPU sai com fisicos, logicos e hibrida",
           u"10 nucleo(s) fisico(s), 12 logico(s)" in t and u"hibrida" in t)
    checar(u"cada backend tem a sua linha com a politica",
           all((u"backend %s:" % b) in t for b in RD.BACKENDS))
    checar(u"tudo ASCII (o console e cp850)",
           all(all(ord(c) < 128 for c in RA.ascii_(l)) for l in L))
    bl = u"\n".join(RA.bloco(dict(rel, passos=[], dados=dict(
        rel["dados"], cpu={"nucleos": 12, "fisicos": 10}))))
    checar(u"o bloco lista TODAS as placas, pelo Windows",
           u"Placas de video (todas, pelo Windows): Intel(R) Iris(R) Xe Graphics"
           in bl, [l for l in bl.splitlines() if l.startswith(u"Placas")])
    checar(u"  com a memoria compartilhada e a frase",
           u"2047 MiB compartilhada" in bl and u"nao usa" in bl)
    checar(u"  a CPU e os backends", u"\nCPU: " in bl and u"\nBackends: " in bl)
    checar(u"  a linha da maquina diz logicos E fisicos",
           u"12 logicos, 10 fisicos" in bl,
           [l for l in bl.splitlines() if l.startswith(u"Maquina")])
    checar(u"  e o bloco continua ASCII", all(ord(c) < 128 for c in bl))
    velho_rt = os.environ.pop("RADAI_THREADS", None)
    try:
        rel3 = _rel()
        with _Troca(RD, inventario=lambda **k: _inv_iris()):
            L3 = RA._p_computacao(ctx, rel3)
        bl3 = u"\n".join(RA.bloco(dict(rel3, passos=[], dados=dict(
            rel3["dados"], cpu={"nucleos": 12, "fisicos": 10}))))
        inv8 = _inv_iris()
        inv8["cpu"] = {"fisicos": 8, "logicos": 16, "nome": "8C/16T"}
        rel4 = _rel()
        with _Troca(RD, inventario=lambda **k: inv8):
            L4 = RA._p_computacao(ctx, rel4)
    finally:
        if velho_rt is not None:
            os.environ["RADAI_THREADS"] = velho_rt
    checar(u"o log diz o teto de threads do envelope em CPU (12 no i7-1355U)",
           any(l.startswith(u"threads do nnU-Net em CPU (envelope): 12 ")
               for l in L3), [l for l in L3 if u"threads" in l])
    checar(u"  e o bloco o repete na linha da CPU",
           u"nnU-Net em CPU: 12 threads" in bl3,
           [l for l in bl3.splitlines() if l.startswith(u"CPU:")])
    checar(u"  com SMT simetrico (8C/16T) o log diz o 8 da biblioteca, e o porque",
           any(u"8 (o da biblioteca)" in l and u"SMT simetrico" in l for l in L4),
           [l for l in L4 if u"threads" in l])
    inv = _inv_iris()
    inv["placas"].append(RD._placa({"nome": "NVIDIA RTX A2000",
                                    "pnp": "PCI\\VEN_10DE&DEV_2531"}, {}))
    rel2 = _rel()
    with _Troca(RD, inventario=lambda **k: inv):
        RA._p_computacao(ctx, rel2)
    checar(u"ISCA: com NVIDIA presente, a integrada NAO vira aviso",
           not any(u"NAO usa" in a for a in rel2["avisos"]), rel2["avisos"])


def teste_o_torch_nao_e_perguntado_duas_vezes():
    secao(u"2 · o torch nao e perguntado duas vezes")
    pasta = _cleanup.temporaria("radai_teste_arrdev_")
    ctx, _l = _ctx(pasta, dry_run=True)
    pedidos = []

    def inv_espia(**k):
        pedidos.append(k)
        return _inv_iris()
    with _Troca(RD, inventario=inv_espia):
        RA._p_computacao(ctx, _rel(com_torch=True))
        RA._p_computacao(ctx, _rel(com_torch=False))
    checar(u"com a sonda do passo do torch, ela vai PRONTA ao inventario",
           "torch" in (pedidos[0].get("sondas_prontas") or {}), pedidos[0])
    checar(u"ISCA: sem ela, o inventario pergunta (nada pronto)",
           not (pedidos[1].get("sondas_prontas") or {}), pedidos[1])
    s = RD.sonda_torch_do_arranque({"importa": True, "versao": "2.9.1+xpu",
                                    "cuda": "", "disponivel": False,
                                    "xpu_disponivel": True,
                                    "xpu_placas": ["Intel Arc A770"]})
    b = RD.backends_das_sondas({"torch": s, "directml": {}, "openvino": {}})
    checar(u"a XPU da sonda do arranque chega ao backend `xpu`",
           b["xpu"]["disponivel"] and b["xpu"]["dispositivos"] == ["Intel Arc A770"],
           b["xpu"])
    checar(u"a sonda do arranque pergunta a XPU (no mesmo filho)",
           "xpu_disponivel" in RA._SONDA_TORCH and "xpu.is_available()" in RA._SONDA_TORCH)
    r = RA.sondar_torch(sys.executable, timeout=120)
    checar(u"a sonda roda neste Python e responde (com ou sem torch)",
           "importa" in r and not r.get("falha"), r)
    if r.get("importa"):
        checar(u"  com torch: a resposta traz xpu_disponivel",
               "xpu_disponivel" in r, sorted(r))


def teste_o_canario_so_quando_faz_sentido():
    secao(u"3 · o canario: simulacao, sem candidato, e com prazo")
    pasta = _cleanup.temporaria("radai_teste_arrdev_")
    disparos = []

    class _Fio(object):

        def __init__(self, vivo):
            self.vivo = vivo
            self.esperou = None

        def join(self, t=None):
            self.esperou = t

        def is_alive(self):
            return self.vivo
    fio = {"atual": _Fio(False)}

    def disparar(inv, **k):
        disparos.append(k)
        RD.ULTIMO["canarios"] = {"openvino_gpu": RD.julgar({
            "backend": "openvino_gpu", "concordancia": 1.0, "nao_finito": False,
            "sha256": "a", "sha256_ref": "a", "contagem_ref": [1] * 18})}
        return fio["atual"]
    ctx, _l = _ctx(pasta, dry_run=True)
    rel = _rel()
    with _Troca(RD, inventario=lambda **k: _inv_iris(openvino=True),
                canarios_em_segundo_plano=disparar):
        L = RA._p_computacao(ctx, rel)
    checar(u"DRY_RUN: o canario NAO roda, e a linha diz",
           not disparos and any(u"nao roda em simulacao" in l for l in L), L[-1:])
    ctx, _l = _ctx(pasta, dry_run=False)
    rel = _rel()
    with _Troca(RD, inventario=lambda **k: _inv_iris(openvino=False),
                canarios_em_segundo_plano=disparar):
        L = RA._p_computacao(ctx, rel)
    checar(u"sem candidato alem do PyTorch CPU: nao dispara, e diz",
           not disparos and any(u"nenhum backend alem do PyTorch CPU" in l
                                for l in L), L[-1:])
    rel = _rel()
    with _Troca(RD, inventario=lambda **k: _inv_iris(openvino=True),
                canarios_em_segundo_plano=disparar):
        L = RA._p_computacao(ctx, rel)
    checar(u"com OpenVINO disponivel: o canario e DISPARADO",
           len(disparos) == 1, disparos)
    checar(u"  com o Python do vigia e a pasta dos pesos",
           disparos and disparos[0].get("python_exe") == sys.executable
           and disparos[0].get("pasta_pesos"), disparos)
    checar(u"  e o cache na pasta de trabalho (sem paciente: so medidas)",
           disparos and disparos[0].get("cache") == os.path.join(
               pasta, "canario_backends.json"), disparos)
    checar(u"  o passo ESPERA o canario, com o prazo do modulo",
           fio["atual"].esperou == RD.ESPERA_DO_ARRANQUE_S, fio["atual"].esperou)
    checar(u"  terminado no prazo: o veredito sai no passo, e os CONFERIDOS",
           any(u"canario openvino_gpu: APROVADO" in l for l in L)
           and any(l.startswith(u"backends conferidos pelo canario:") for l in L),
           L[-4:])
    checar(u"  e o aprovado de PESQUISA nao entra na lista (dito fora pela politica)",
           any(l == u"backends conferidos pelo canario: torch_cpu (o chao, sem canario)"
               for l in L)
           and any(u"openvino_gpu: fora pela politica" in l for l in L), L[-4:])
    checar(u"  e nenhuma linha diz que a fila usa a lista (ela decide pela VRAM)",
           not any(u"fila pode usar" in l for l in L)
           and any(RD.AVISO_DA_FILA in l for l in L), L[-4:])
    fio["atual"] = _Fio(True)
    ctx2 = dict(ctx, espera_canario_s=0.01)
    rel2 = _rel()
    with _Troca(RD, inventario=lambda **k: _inv_iris(openvino=True),
                canarios_em_segundo_plano=disparar):
        L = RA._p_computacao(ctx2, rel2)
    checar(u"passou do prazo: segue em segundo plano, e o que esta no ar e "
           u"NAO CONFERIDO",
           any(u"passou do prazo" in l for l in L)
           and any(u"openvino_gpu: NAO CONFERIDO (o canario ainda roda)" in l
                   for l in L), L[-4:])
    checar(u"  e a linha nao promete mais «ate la a fila usa o PyTorch»",
           not any(u"a fila usa o PyTorch" in l for l in L), L[-4:])
    checar(u"  o bloco diz em segundo plano, e o aviso",
           u"em segundo plano" in rel2["dados"]["computacao"]["canario"]
           and RD.AVISO_DA_FILA in rel2["dados"]["computacao"]["canario"],
           rel2["dados"]["computacao"].get("canario"))
    checar(u"  e o prazo pedido foi o do ctx", fio["atual"].esperou == 0.01)
    checar(u"o prazo do passo e maior que a espera pedida ao canario",
           [p[2] for p in RA.PASSOS if p[1] is RA._p_computacao][0]
           > RD.ESPERA_DO_ARRANQUE_S)
    RD.ULTIMO["canarios"] = None
    RD.ULTIMO["canario_rodando"] = True
    try:
        with _Troca(RD, rodar_canarios=lambda *a, **k: {}):
            t = RD.canarios_em_segundo_plano(_inv_iris(openvino=True))
        checar(u"com um canario ja rodando, o segundo pedido volta None", t is None)
    finally:
        RD.ULTIMO["canario_rodando"] = False
    logs = []
    with _Troca(RD, rodar_canarios=lambda inv, **k: {
            "openvino_gpu": RD.julgar({"backend": "openvino_gpu",
                                       "concordancia": 1.0, "nao_finito": False,
                                       "sha256": "a", "sha256_ref": "a",
                                       "contagem_ref": [1] * 18})}):
        t = RD.canarios_em_segundo_plano(_inv_iris(openvino=True), log=logs.append)
        t.join(10)
    checar(u"o lancador de verdade roda numa thread e diz os CONFERIDOS",
           any(u"backends conferidos pelo canario" in l for l in logs)
           and not RD.ULTIMO["canario_rodando"], logs)
    checar(u"  e o aprovado de PESQUISA nao entra na lista (dito fora)",
           any(u"conferidos pelo canario: torch_cpu (o chao, sem canario)" in l
               for l in logs)
           and any(u"openvino_gpu: fora pela politica" in l for l in logs), logs)
    checar(u"  e nenhuma linha do lancador diz «a fila pode usar»",
           not any(u"fila pode usar" in l for l in logs), logs)


def _inv_cuda():
    placa = RD._placa({"nome": "NVIDIA RTX A2000", "fabricante": "NVIDIA",
                       "driver": "31.0.15.3623", "pnp": "PCI\\VEN_10DE&DEV_2531"},
                      {})
    sondas = {"torch": {"importa": True, "versao": "2.5.1+cu121", "cuda": "12.1",
                        "cuda_disponivel": True,
                        "cuda_placas": ["NVIDIA RTX A2000 (6138 MiB)"],
                        "xpu_disponivel": False},
              "directml": {"importa": False, "erro": "x"},
              "openvino": {"importa": False, "erro": "x"}}
    return {"quando": "agora", "placas": [placa], "placas_fonte": u"CIM",
            "placas_falha": u"", "nvidia": {"placas": [], "falha": u""},
            "cpu": {"fisicos": 8, "logicos": 16, "nome": "Xeon"},
            "memoria": {}, "sondas": sondas,
            "backends": RD.backends_das_sondas(sondas), "segundos": 0.1}


def teste_a_cuda_de_fora_e_dita():
    secao(u"3b · numa estacao NVIDIA, a CUDA que ficou de fora e dita")
    pasta = _cleanup.temporaria("radai_teste_arrdev_")
    ctx, _l = _ctx(pasta, dry_run=False)

    class _Fio(object):
        def join(self, t=None):
            pass

        def is_alive(self):
            return False

    adiado = {"cuda": {"backend": "cuda", "aprovado": False, "adiado": True,
                       "motivo": u"adiado: 3000 MB de RAM livre, o canario de "
                                 u"cuda pede 4096"}}

    def disparar(inv, **k):
        RD.ULTIMO["canarios"] = dict(adiado)
        return _Fio()
    rel = _rel()
    with _Troca(RD, inventario=lambda **k: _inv_cuda(),
                canarios_em_segundo_plano=disparar):
        L = RA._p_computacao(ctx, rel)
    t = u"\n".join(L)
    checar(u"o log diz a CUDA NAO CONFERIDA (adiado), com o motivo",
           u"cuda: NAO CONFERIDO (adiado)" in t and u"3000 MB" in t, L[-4:])
    checar(u"  e o veredito dela e «ADIADO», nao «REPROVADO»",
           u"canario cuda: ADIADO, nao conferido" in t
           and u"canario cuda: REPROVADO" not in t, L[-5:])
    checar(u"  e o aviso de que a fila ainda decide pela VRAM",
           RD.AVISO_DA_FILA in t)
    can = rel["dados"]["computacao"]["canario"]
    checar(u"o bloco (o que se cola num chat) diz a CUDA de fora, sem «fila:»",
           u"cuda NAO CONFERIDO (adiado)" in can and u"| fila:" not in can, can)
    bl = u"\n".join(RA.bloco(dict(rel, passos=[], dados=dict(
        rel["dados"], cpu={"nucleos": 16, "fisicos": 8}))))
    linha = [l for l in bl.splitlines() if l.startswith(u"Canario:")]
    checar(u"  e a linha «Canario:» do bloco leva isso",
           linha and u"cuda NAO CONFERIDO" in linha[0]
           and RD.AVISO_DA_FILA in linha[0], linha)
    velha = u"a fila pode usar: %s" % u", ".join(
        RD.admitidos(_inv_cuda(), adiado))
    checar(u"ISCA: a linha antiga nao dizia a CUDA", u"cuda" not in velha, velha)
    ctx2 = dict(ctx, espera_canario_s=0.01)

    class _Vivo(_Fio):
        def is_alive(self):
            return True
    RD.ULTIMO["canarios"] = None
    with _Troca(RD, inventario=lambda **k: _inv_cuda(),
                canarios_em_segundo_plano=lambda inv, **k: _Vivo()):
        L = RA._p_computacao(ctx2, _rel())
    checar(u"passou do prazo: «cuda: NAO CONFERIDO (o canario ainda roda)»",
           any(u"cuda: NAO CONFERIDO (o canario ainda roda)" in l for l in L),
           L[-4:])
    RD.ULTIMO["canarios"] = None


def teste_o_passo_esta_na_ordem_certa():
    secao(u"7 · o passo esta em PASSOS, depois do torch")
    nomes = [p[1] for p in RA.PASSOS]
    checar(u"_p_computacao esta em PASSOS", RA._p_computacao in nomes)
    checar(u"  DEPOIS de _p_torch (reaproveita a sonda dele)",
           RA._p_computacao in nomes and RA._p_torch in nomes
           and nomes.index(RA._p_computacao) > nomes.index(RA._p_torch))
    lim = [p[2] for p in RA.PASSOS if p[1] is RA._p_computacao]
    checar(u"  com tempo-limite (o PowerShell e as sondas sao subprocessos)",
           lim and 30 <= lim[0] <= 600, lim)


def teste_o_nvidia_smi_nao_importa_o_motor():
    secao(u"5 · achar o nvidia-smi nao importa o motor")
    cod = (u"import sys; sys.path.insert(0, %r); import radai_arranque as RA; "
           u"RA.caminho_do_nvidia_smi(); print('ENGINE=%%s' %% ('engine' in "
           u"sys.modules))" % APP)
    r = subprocess.run([sys.executable, "-c", cod], capture_output=True,
                       text=True, timeout=120)
    checar(u"caminho_do_nvidia_smi nao arrasta o engine",
           "ENGINE=False" in r.stdout, (r.stdout + r.stderr)[-200:])
    checar(u"  e responde o mesmo que radai_devices",
           RA.caminho_do_nvidia_smi() == RD.achar_nvidia_smi())


def teste_a_cpu_diz_fisicos_e_logicos():
    secao(u"4 · o passo da CPU diz fisicos e logicos")
    rel = _rel()
    with _Troca(RD, topologia_da_cpu=lambda: {"fisicos": 10, "logicos": 12,
                                              "classes": {1: 2, 0: 8},
                                              "fonte": "x", "falha": ""}):
        L = RA._p_cpu_ram({}, rel)
    checar(u"a linha diz 10 fisicos, 12 logicos e hibrida",
           u"10 nucleo(s) fisico(s), 12 logico(s)" in L[0] and u"hibrida" in L[0],
           L[0])
    checar(u"  e os dados guardam os dois",
           rel["dados"]["cpu"].get("fisicos") == 10, rel["dados"]["cpu"])

    def quebra():
        raise OSError("sem ctypes")
    rel = _rel()
    with _Troca(RD, topologia_da_cpu=quebra):
        L = RA._p_cpu_ram({}, rel)
    checar(u"sem a topologia: o logico sozinho, e a linha diz que nao leu",
           u"os fisicos nao foram lidos" in L[0], L[0])


def teste_o_passo_de_verdade_em_simulacao():
    secao(u"o passo de verdade (PowerShell e sondas), em simulacao")
    pasta = _cleanup.temporaria("radai_teste_arrdev_")
    ctx, _l = _ctx(pasta, dry_run=True)
    rel = _rel(com_torch=False)
    t0 = time.time()
    L = RA._p_computacao(ctx, rel)
    dt = time.time() - t0
    lim = [p[2] for p in RA.PASSOS if p[1] is RA._p_computacao][0]
    checar(u"terminou dentro do tempo-limite do passo (%.1f s de %d)" % (dt, lim),
           dt < lim, dt)
    if os.name == "nt":
        checar(u"o Windows listou ao menos uma placa",
               (rel["dados"]["computacao"].get("placas") or [])
               or rel["dados"]["computacao"].get("placas_falha"),
               rel["dados"]["computacao"])
    checar(u"  e o diagnostico ficou guardado para as telas (radai_devices.ULTIMO)",
           RD.ULTIMO.get("diagnostico") is not None)
    checar(u"tudo ASCII depois do filtro do log",
           all(all(ord(c) < 128 for c in RA.ascii_(l)) for l in L))


def teste_a_conferencia_nomeia_a_placa():
    secao(u"a conferencia da estacao nomeia a placa, sem virar falta")
    import radai_station_check as CE
    velho_diag = RD.ULTIMO.get("diagnostico")
    velho_can = RD.ULTIMO.get("canarios")
    velho_torch = RA.ULTIMO.get("torch")
    try:
        RA.ULTIMO["torch"] = {"importa": True, "versao": "2.5.1+cu121",
                              "cuda": "12.1", "disponivel": False, "n": 0,
                              "placas": [], "ts": time.time()}
        RD.ULTIMO["diagnostico"] = None
        iris = _inv_iris()["placas"]
        nv = RD._placa({"nome": "NVIDIA RTX A2000",
                        "pnp": "PCI\\VEN_10DE&DEV_2531"}, {})
        with _Troca(RA, placas=lambda timeout=20: {"placas": [], "driver": "",
                                                   "falha": "sem"}), \
                _Troca(RD, placas_rapidas=lambda: iris + [nv]):
            t0 = time.time()
            sec = CE._secao_gpu()
            dt = time.time() - t0
        itens = sec["itens"]
        checar(u"o primeiro item continua o do CUDA (as outras baterias o leem)",
               itens and itens[0]["nome"] == u"CUDA disponível", itens[:1])
        pv = [i for i in itens if i["nome"] == u"Placa de vídeo"]
        checar(u"a Iris Xe e nomeada, com a frase do que o pacote faz",
               pv and u"Iris(R) Xe" in pv[0]["valor"] and u"não usa" in pv[0]["detalhe"],
               pv)
        checar(u"  como AVISO (ok=None, grave=False), nunca FALTA",
               pv and pv[0]["ok"] is None and not pv[0]["grave"], pv)
        checar(u"ISCA: a NVIDIA nao entra nesta lista",
               not any(u"A2000" in i["valor"] for i in pv), pv)
        NOME = u"Backends conferidos pelo canário"
        bk = [i for i in itens if i["nome"] == NOME]
        checar(u"sem diagnostico ainda: «o arranque ainda nao mediu»",
               bk and u"ainda não mediu" in bk[0]["valor"], bk)
        checar(u"e a secao e rapida (%.2f s)" % dt, dt < 5.0)
        RD.ULTIMO["diagnostico"] = _inv_iris(openvino=True)
        RD.ULTIMO["canarios"] = {}
        with _Troca(RA, placas=lambda timeout=20: {"placas": [], "driver": "",
                                                   "falha": "sem"}):
            sec = CE._secao_gpu()
        bk = [i for i in sec["itens"] if i["nome"] == NOME]
        checar(u"com o diagnostico: os backends CONFERIDOS pelo canario",
               bk and bk[0]["valor"] == u"torch_cpu", bk)
        checar(u"  e o detalhe diz que a fila ainda decide pela VRAM",
               bk and u"VRAM" in bk[0]["detalhe"], bk)
        checar(u"  nenhum item se chama mais «Backends da fila»",
               not [i for i in sec["itens"] if i["nome"] == u"Backends da fila"])
        RD.ULTIMO["diagnostico"] = _inv_cuda()
        RD.ULTIMO["canarios"] = {"cuda": {"backend": "cuda", "aprovado": False,
                                          "adiado": True,
                                          "motivo": u"adiado: 3000 MB livres"}}
        with _Troca(RA, placas=lambda timeout=20: {"placas": [], "driver": "",
                                                   "falha": "sem"}), \
                _Troca(RD, placas_rapidas=lambda: []):
            sec = CE._secao_gpu()
        cu = [i for i in sec["itens"] if i["nome"] == u"CUDA no canário"]
        checar(u"CUDA adiada: item «CUDA no canário», «não conferida», como AVISO",
               cu and cu[0]["valor"] == u"não conferida" and cu[0]["ok"] is None
               and not cu[0]["grave"] and u"3000 MB" in cu[0]["detalhe"], cu)
        RD.ULTIMO["canarios"] = {"cuda": RD.julgar({
            "backend": "cuda", "concordancia": 1.0, "nao_finito": False,
            "sha256": "a", "sha256_ref": "a", "contagem_ref": [1] * 18})}
        with _Troca(RA, placas=lambda timeout=20: {"placas": [], "driver": "",
                                                   "falha": "sem"}), \
                _Troca(RD, placas_rapidas=lambda: []):
            sec = CE._secao_gpu()
        cu = [i for i in sec["itens"] if i["nome"] == u"CUDA no canário"]
        bk = [i for i in sec["itens"] if i["nome"] == NOME]
        checar(u"ISCA: com a CUDA aprovada, o aviso some e ela entra na lista",
               not cu and bk and u"cuda" in bk[0]["valor"], (cu, bk))
    finally:
        RD.ULTIMO["diagnostico"] = velho_diag
        RD.ULTIMO["canarios"] = velho_can
        if velho_torch is None:
            RA.ULTIMO.pop("torch", None)
        else:
            RA.ULTIMO["torch"] = velho_torch


def teste_as_placas_rapidas_vem_do_registro():
    secao(u"as placas rapidas: diagnostico do arranque, ou registro")
    velho = RD.ULTIMO.get("diagnostico")
    try:
        RD.ULTIMO["diagnostico"] = {"placas": [{"nome": "do arranque"}]}
        checar(u"com o diagnostico, sao as dele",
               RD.placas_rapidas() == [{"nome": "do arranque"}])
        RD.ULTIMO["diagnostico"] = None
        t0 = time.time()
        r = RD.placas_rapidas()
        dt = time.time() - t0
        if os.name == "nt":
            checar(u"sem diagnostico: o registro responde em menos de 1 s "
                   u"(%.3f s)" % dt, dt < 1.0)
            checar(u"  e lista ao menos uma placa, com a fonte declarada",
                   r and u"registro" in (r[0].get("memoria_fonte") or u""), r[:1])
    finally:
        RD.ULTIMO["diagnostico"] = velho


class _FioQueDorme(object):

    def __init__(self):
        self.esperou = None

    def join(self, t=None):
        self.esperou = t
        time.sleep(max(0.0, float(t or 0)))

    def is_alive(self):
        return True


def teste_o_prazo_do_passo_cobre_o_pior_inventario():
    secao(u"W2E · o prazo do passo cobre o pior inventario, e a espera encolhe")
    limite = [p[2] for p in RA.PASSOS if p[1] is RA._p_computacao][0]
    pior = RD.pior_inventario_s()
    checar(u"a soma: pior inventario (%d s) + folga (%d s) cabe no prazo do "
           u"passo (%d s)" % (pior, RA.FOLGA_DO_PASSO_S, limite),
           pior + RA.FOLGA_DO_PASSO_S < limite,
           (pior, RA.FOLGA_DO_PASSO_S, limite))
    checar(u"  a soma e a dos prazos declarados (PowerShell, wmic, nvidia-smi e "
           u"as tres sondas)",
           pior == (RD.PRAZO_POWERSHELL_S + RD.PRAZO_WMIC_S
                    + RD.PRAZO_NVIDIA_SMI_S + 3 * RD.PRAZO_SONDA_NO_ARRANQUE_S),
           pior)
    import inspect
    checar(u"  e os subprocessos usam esses prazos (os padroes das funcoes)",
           inspect.signature(RD.inventario_windows).parameters["timeout"].default
           == RD.PRAZO_POWERSHELL_S
           and inspect.signature(RD.inventario_windows).parameters[
               "timeout_wmic"].default == RD.PRAZO_WMIC_S
           and inspect.signature(RD.placas_nvidia).parameters["timeout"].default
           == RD.PRAZO_NVIDIA_SMI_S)
    pedidos = []

    def inv_lento(**k):
        pedidos.append(k)
        time.sleep(1.5)
        return _inv_iris(openvino=True)
    pasta = _cleanup.temporaria("radai_teste_arrdev_")
    ctx, linhas = _ctx(pasta, dry_run=False)
    ctx["espera_canario_s"] = 240.0
    ctx["limites"] = {u"comp": 4.0}
    fio = _FioQueDorme()
    with _Troca(RD, inventario=inv_lento,
                canarios_em_segundo_plano=lambda inv, **k: fio), \
            _Troca(RA, FOLGA_DO_PASSO_S=0.5):
        ctx["passos"] = ((u"comp", RA._p_computacao, 4.0),)
        t0 = time.time()
        rel = RA.executar(ctx)
        dt = time.time() - t0
    reg = rel["passos"][0]
    checar(u"inventario de 1,5 s num passo de 4 s: o passo TERMINA no prazo",
           reg.get("ok") and not reg.get("falha"), (reg, dt))
    checar(u"  a espera encolheu para o que sobrou (< 4 s, e nao os 240)",
           fio.esperou is not None and fio.esperou < 4.0, fio.esperou)
    checar(u"  a linha diz que encolheu, e quanto o inventario levou",
           any(u"encurtado de 240 s" in l for l in reg.get("linhas") or []),
           [l for l in reg.get("linhas") or [] if u"canario:" in l])
    checar(u"  e as linhas de placas e backends estao no log",
           any(u"placa de video [0]" in l for l in reg.get("linhas") or [])
           and any(u"backend openvino_gpu" in l for l in reg.get("linhas") or []))
    checar(u"  as sondas foram perguntadas com o prazo curto do arranque",
           pedidos and pedidos[0].get("sondas_timeout")
           == RD.PRAZO_SONDA_NO_ARRANQUE_S, pedidos[:1])
    fio2 = _FioQueDorme()
    ctx2, _l2 = _ctx(pasta, dry_run=False)
    ctx2["espera_canario_s"] = 6.0
    ctx2["_prazo_do_passo"] = (time.time(), None)
    with _Troca(RD, inventario=inv_lento,
                canarios_em_segundo_plano=lambda inv, **k: fio2):
        terminou, _v, _e = RA._com_limite(RA._p_computacao, (ctx2, _rel()), 4.0)
    checar(u"ISCA: sem o prazo do passo (espera cheia), o mesmo passo ESTOURA "
           u"o prazo e as linhas se perdem", not terminou, terminou)
    time.sleep(4.0)


def teste_o_canario_ja_rodando_nao_fala_de_prazo():
    secao(u"W2E · o canario ja rodando nao fala de prazo")
    pasta = _cleanup.temporaria("radai_teste_arrdev_")
    ctx, _l = _ctx(pasta, dry_run=False)
    with _Troca(RD, inventario=lambda **k: _inv_iris(openvino=True),
                canarios_em_segundo_plano=lambda inv, **k: None):
        L = RA._p_computacao(dict(ctx, espera_canario_s=0.01), _rel())
    checar(u"t is None: «ja estava rodando», e o passo nao esperou",
           any(u"ja estava rodando" in l and u"nao esperou" in l for l in L)
           and not any(u"passou do prazo" in l for l in L),
           [l for l in L if u"canario" in l])
    checar(u"  e o que esta no ar sai NAO CONFERIDO (ainda roda)",
           any(u"openvino_gpu: NAO CONFERIDO (o canario ainda roda)" in l
               for l in L))
    fio = _FioQueDorme()
    with _Troca(RD, inventario=lambda **k: _inv_iris(openvino=True),
                canarios_em_segundo_plano=lambda inv, **k: fio):
        L2 = RA._p_computacao(dict(ctx, espera_canario_s=0.01), _rel())
    checar(u"ISCA: disparado e passado do prazo, a frase do prazo esta la",
           any(u"passou do prazo" in l for l in L2)
           and not any(u"ja estava rodando" in l for l in L2), L2[-4:])


def teste_device_cpu_nao_confere_a_placa():
    secao(u"W2E · DEVICE=cpu: o canario da placa nao roda")
    pasta = _cleanup.temporaria("radai_teste_arrdev_")
    disparos = []

    class _Fio(object):
        def join(self, t=None):
            pass

        def is_alive(self):
            return False

    def disparar(inv, **k):
        disparos.append(k.get("device"))
        RD.ULTIMO["canarios"] = {}
        return _Fio()
    for dev in ("cpu", "CPU "):
        del disparos[:]
        ctx, _l = _ctx(pasta, dry_run=False)
        ctx["device"] = dev
        rel = _rel()
        with _Troca(RD, inventario=lambda **k: _inv_cuda(),
                    canarios_em_segundo_plano=disparar):
            L = RA._p_computacao(ctx, rel)
        t = u"\n".join(L)
        checar(u"DEVICE=%r: nenhum canario disparado (a CUDA era o unico "
               u"candidato)" % dev, not disparos, disparos)
        checar(u"  a linha diz DEVICE=cpu e que a placa nao e conferida",
               u"DEVICE=cpu no radai_watcher.config - a placa nao e conferida "
               u"(cuda" in t, [l for l in L if u"canario" in l])
    ctx, _l = _ctx(pasta, dry_run=False)
    ctx["device"] = "auto"
    del disparos[:]
    with _Troca(RD, inventario=lambda **k: _inv_cuda(),
                canarios_em_segundo_plano=disparar):
        L = RA._p_computacao(ctx, _rel())
    checar(u"ISCA: DEVICE=auto, a mesma estacao dispara o canario (com a CUDA)",
           disparos == ["auto"], disparos)
    c = RD.conferencia(_inv_cuda(), {}, device="cpu")
    fora = dict((f["backend"], f) for f in c["fora"])
    checar(u"a conferencia diz a CUDA fora por DEVICE=cpu (e nao «o canario "
           u"nao rodou»)", fora.get("cuda", {}).get("estado") == "device_cpu"
           and u"DEVICE=cpu" in fora["cuda"]["motivo"], fora.get("cuda"))
    checar(u"  e a linha do log leva o rotulo",
           any(u"cuda: NAO CONFERIDO (DEVICE=cpu" in l
               for l in RD.linhas_da_conferencia(_inv_cuda(), {}, device="cpu")))
    c2 = RD.conferencia(_inv_cuda(), {}, device="auto")
    checar(u"ISCA: com DEVICE=auto e sem canario, a CUDA e «sem resultado»",
           dict((f["backend"], f["estado"]) for f in c2["fora"]).get("cuda")
           == "sem_resultado", c2["fora"])
    import radai_station_check as SC
    velho = dict(RD.ULTIMO)
    try:
        RD.ULTIMO.update(diagnostico=_inv_cuda(), canarios={}, device="cpu",
                         canario_rodando=False)
        itens = SC._itens_das_outras_placas()
    finally:
        RD.ULTIMO.clear()
        RD.ULTIMO.update(velho)
    cuda = [i for i in itens if i.get("nome") == u"CUDA no canário"]
    checar(u"a tela da estacao diz «não conferida (DEVICE=cpu)»",
           cuda and u"DEVICE=cpu" in (cuda[0].get("valor") or u""), cuda)


def teste_a_sonda_do_torch_fica_guardada():
    secao(u"a sonda do torch guardada por driver + torch, refeita em segundo plano")
    import tempfile as _tf
    pasta = _tf.mkdtemp(prefix="radai_teste_arrdev_")
    arquivo = os.path.join(pasta, "sonda_torch.json")
    chamadas = []
    resposta = [{"importa": True, "versao": "2.5.1+cu121", "cuda": "12.1",
                 "disponivel": True, "n": 1,
                 "placas": [{"nome": "Quadro P2200", "cap": "6.1",
                             "total_mb": 5120}], "arch": ["sm_61"]}]

    def sonda(python_exe=None, timeout=120):
        chamadas.append(1)
        return dict(resposta[0])

    def rel(driver=u"552.22"):
        return {"dados": {"placas": {"driver": driver,
                                     "placas": [{"nome": "Quadro P2200"}]},
                          "versoes": {"torch": "2.5.1+cu121",
                                      "torch_cuda_build": "12.1"}},
                "pendencias": []}
    linhas = []
    ctx = {"python_exe": u"py.exe", "arquivo_da_sonda": arquivo,
           "log": linhas.append}
    velho = RA.ULTIMO.get("torch")
    try:
        with _Troca(RA, sondar_torch=sonda):
            r1 = rel()
            L1 = RA._p_torch(ctx, r1)
            checar(u"sem resposta guardada: pergunta na hora, uma vez",
                   len(chamadas) == 1 and not r1["dados"]["torch"].get("do_cache"))
            checar(u"  e guarda a resposta no disco", os.path.isfile(arquivo))
            r2 = rel()
            L2 = RA._p_torch(ctx, r2)
            sincronas = len(chamadas)
            checar(u"mesmo driver, mesmas placas e mesmo torch: usa a guardada "
                   u"sem esperar a sonda", r2["dados"]["torch"].get("do_cache") is True
                   and u"resposta guardada" in L2[0], repr(L2[:1]))
            t = RA.ULTIMO.get("sonda_em_segundo_plano")
            if t is not None:
                t.join(30)
            checar(u"  e a refaz em segundo plano",
                   len(chamadas) == sincronas + 1 or len(chamadas) == 2,
                   repr(len(chamadas)))
            checar(u"  e o resultado e o mesmo de antes (linha do torch)",
                   L2[1:2] == L1[:1], u"%r / %r" % (L2[1:2], L1[:1]))
            resposta[0] = dict(resposta[0], disponivel=False, n=0, placas=[])
            r3 = rel()
            RA._p_torch(ctx, r3)
            t = RA.ULTIMO.get("sonda_em_segundo_plano")
            if t is not None:
                t.join(30)
            checar(u"a sonda de fundo que muda o resultado avisa no log",
                   any(u"mudou" in l for l in linhas), repr(linhas))
            checar(u"  e passa a valer para as telas",
                   (RA.ULTIMO.get("torch") or {}).get("disponivel") is False)
            antes = len(chamadas)
            r4 = rel(driver=u"561.09")
            L4 = RA._p_torch(ctx, r4)
            checar(u"driver novo: pergunta de novo, na hora",
                   len(chamadas) == antes + 1
                   and not any(u"resposta guardada" in l for l in L4))
            antes = len(chamadas)
            arq2 = os.path.join(pasta, "sem_driver.json")
            ctx2 = dict(ctx, arquivo_da_sonda=arq2)
            RA._p_torch(ctx2, rel(driver=u""))
            RA._p_torch(ctx2, rel(driver=u""))
            checar(u"(isca) sem driver lido, nada se guarda: as duas perguntam",
                   len(chamadas) == antes + 2 and not os.path.isfile(arq2))
    finally:
        RA.ULTIMO["torch"] = velho


def main():
    print(u"test_arranque_devices | todas as placas, a cpu, os backends e o canario "
          u"no arranque")
    for t in (teste_a_placa_que_existe_e_nomeada,
              teste_o_torch_nao_e_perguntado_duas_vezes,
              teste_o_canario_so_quando_faz_sentido,
              teste_a_cuda_de_fora_e_dita,
              teste_a_cpu_diz_fisicos_e_logicos,
              teste_o_nvidia_smi_nao_importa_o_motor,
              teste_o_passo_esta_na_ordem_certa,
              teste_o_passo_de_verdade_em_simulacao,
              teste_a_conferencia_nomeia_a_placa,
              teste_as_placas_rapidas_vem_do_registro,
              teste_o_prazo_do_passo_cobre_o_pior_inventario,
              teste_o_canario_ja_rodando_nao_fala_de_prazo,
              teste_device_cpu_nao_confere_a_placa,
              teste_a_sonda_do_torch_fica_guardada):
        try:
            t()
        except Exception as e:
            import traceback
            checar(u"%s (excecao)" % t.__name__, False,
                   u"%s: %s" % (type(e).__name__, e))
            traceback.print_exc()
    falhas = [(n, d) for n, ok, d in _R if not ok]
    print(u"\n" + u"=" * 66)
    if falhas:
        print(u"FALHOU: %d de %d checagens" % (len(falhas), len(_R)))
        for n, d in falhas:
            print(u"  - %s%s" % (n, (u"  [%s]" % (d,)) if d else u""))
    else:
        print(u"OK: %d checagens, todas passaram" % len(_R))
    print(u"=" * 66)
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
