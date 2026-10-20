# -*- coding: utf-8 -*-
import hashlib
import io
import json
import os
import platform
import re
import subprocess
import sys
import threading
import time
from datetime import datetime

VERSAO_DEVICES = "1.0"

BACKENDS = ("cuda", "xpu", "openvino_gpu", "directml", "openvino_cpu",
            "torch_cpu")

FAMILIA = {"torch_cpu": "torch", "cuda": "torch", "xpu": "torch",
           "directml": "directml", "openvino_cpu": "openvino",
           "openvino_gpu": "openvino"}

POLITICA_DE_ADOCAO = {
    "torch_cpu": "producao",
    "cuda": "producao",
    "openvino_cpu": "recusado",
    "openvino_gpu": "pesquisa",
    "directml": "recusado",
    "xpu": "pesquisa",
}

MOTIVO_DA_POLITICA = {
    "torch_cpu": u"o chao: roda em toda estacao, e e para ele que todo recuo volta",
    "cuda": u"o caminho de campo desde a v8 (NVIDIA)",
    "openvino_cpu": u"medido 24/09: 1,01-1,07x o tempo do PyTorch CPU (sem ganho)",
    "openvino_gpu": (u"medido 24/09: identico, 3 s/patch, mas ~126 s na primeira "
                     u"inferencia de CADA rede; o openvino nao esta no pacote"),
    "directml": (u"medido 24/09: o torch-directml 0.2.5 nao executa convolucao "
                 u"3D; em manutencao"),
    "xpu": (u"medido 24/09: identico, 3,4-4,1 s/patch, primeira passada ~30 s "
            u"por processo; exige um segundo runtime (torch XPU) fora do pacote"),
}

TETO_MEDIDO_DE_THREADS = 12
THREADS_DA_BIBLIOTECA = 8


def regra_de_threads(topo=None):
    try:
        topo = topo if topo is not None else topologia_da_cpu()
    except Exception as e:
        topo = {"falha": u"%s: %s" % (type(e).__name__, str(e)[:80])}
    topo = topo or {}
    fis, log = topo.get("fisicos"), topo.get("logicos")
    if not fis or not log:
        return {"n": None,
                "motivo": u"os nucleos fisicos nao foram lidos (%s): fica o %d "
                          u"da biblioteca" % (topo.get("falha") or u"?",
                                              THREADS_DA_BIBLIOTECA)}
    fis, log = int(fis), int(log)
    if log >= 2 * fis:
        base = fis
        de = u"%d fisicos (SMT simetrico: %d logicos)" % (fis, log)
    else:
        base = log
        de = u"%d logicos (%d fisicos)" % (log, fis)
    n = min(base, TETO_MEDIDO_DE_THREADS)
    if n <= THREADS_DA_BIBLIOTECA:
        return {"n": None,
                "motivo": u"%s: %d nao passa do %d da biblioteca, e descer "
                          u"dele nao foi medido" % (de, n, THREADS_DA_BIBLIOTECA)}
    return {"n": n,
            "motivo": u"%s, ate %d (o maior numero medido, S0 de 24/09/2026)"
                      % (de, TETO_MEDIDO_DE_THREADS)}


def threads_para_o_nnunet(topo=None):
    return regra_de_threads(topo)["n"]

LIMIAR_CONCORDANCIA = 0.999
CLASSES_MINIMAS = 8
ESTRUTURAS_MINIMAS_NO_PATCH = 1
FRACAO_MINIMA_DE_ESTRUTURA_NO_PATCH = 0.01
PATCHES_MAXIMOS_PARA_CONFERIR = 8
CANARIO_VERSAO = "1"
MEMORIA_MINIMA_CANARIO_MB = 6144
MEMORIA_DO_CANARIO_MB = {
    "openvino_cpu": 6144,
    "openvino_gpu": 6144,
    "xpu": 4096,
    "cuda": 4096,
}


def memoria_minima_do_canario(backend):
    return int(MEMORIA_DO_CANARIO_MB.get(backend, MEMORIA_MINIMA_CANARIO_MB))
ESPERA_DO_ARRANQUE_S = 240

PRAZO_POWERSHELL_S = 40
PRAZO_WMIC_S = 40
PRAZO_NVIDIA_SMI_S = 20
PRAZO_SONDA_NO_ARRANQUE_S = 60
FAMILIAS_DE_SONDA = ("torch", "directml", "openvino")


def pior_inventario_s(sonda_s=None):
    s = PRAZO_SONDA_NO_ARRANQUE_S if sonda_s is None else sonda_s
    return (PRAZO_POWERSHELL_S + PRAZO_WMIC_S + PRAZO_NVIDIA_SMI_S
            + len(FAMILIAS_DE_SONDA) * s)


CANARIO_DATASET = 831
CANARIO_LADO = 128

CANARIO_REFERENCIA = {
    "sha256": "ac3a5cadaeadd89103b198445a9518755d95f87e70abcfeec7b2cf233ef9e35c",
    "classes": 18,
    "medido": u"24/09/2026, torch 2.5.1+cu121, i7-1355U, 4 a 12 threads",
}

FANTOMA_SHA256 = "2c26b1577959c271f02bb2e58073ae83fcc1bfc16a5795d13bffd0241fea0275"

MARCA_SONDA = "RADAI_SONDA_BACKEND "
MARCA_CANARIO = "RADAI_CANARIO "

ULTIMO = {"diagnostico": None, "canarios": None, "canario_rodando": False,
          "device": None}
_TRAVA = threading.Lock()

_ABAIXO_DO_NORMAL = 0x00004000
_SEM_JANELA = 0x08000000


def _rodar(args, timeout, baixa_prioridade=False, env=None):
    r = {"codigo": None, "saida": u"", "erro": u"", "falha": u"",
         "segundos": 0.0}
    t0 = time.time()
    try:
        flags = 0
        if os.name == "nt":
            flags = _SEM_JANELA | (_ABAIXO_DO_NORMAL if baixa_prioridade else 0)
        p = subprocess.run(args, stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE, timeout=timeout,
                           creationflags=flags, env=env)
        r["codigo"] = p.returncode
        r["saida"] = (p.stdout or b"").decode("utf-8", "replace")
        r["erro"] = (p.stderr or b"").decode("utf-8", "replace")
    except FileNotFoundError:
        r["falha"] = u"nao encontrado"
    except subprocess.TimeoutExpired:
        r["falha"] = u"nao respondeu em %d s" % timeout
    except Exception as e:
        r["falha"] = u"%s: %s" % (type(e).__name__, str(e)[:160])
    r["segundos"] = round(time.time() - t0, 1)
    return r


def _num(v):
    try:
        return float(str(v).strip().split()[0])
    except Exception:
        return None


def achar_nvidia_smi():
    candidatos = []
    raiz = os.environ.get("SystemRoot")
    if raiz:
        candidatos.append(os.path.join(raiz, "System32", "nvidia-smi.exe"))
    for pf in (os.environ.get("ProgramFiles"), os.environ.get("ProgramW6432")):
        if pf:
            candidatos.append(os.path.join(pf, "NVIDIA Corporation", "NVSMI",
                                           "nvidia-smi.exe"))
    for c in candidatos:
        try:
            if os.path.isfile(c):
                return c
        except Exception:
            pass
    return "nvidia-smi"


def placas_nvidia(timeout=PRAZO_NVIDIA_SMI_S):
    fora = {"placas": [], "falha": u""}
    campos = "index,name,memory.total,memory.free,driver_version"
    r = _rodar([achar_nvidia_smi(), "--query-gpu=" + campos,
                "--format=csv,noheader,nounits"], timeout)
    if r["falha"]:
        fora["falha"] = u"nvidia-smi %s" % r["falha"]
        return fora
    if r["codigo"] != 0:
        t = (r["saida"] or r["erro"]).strip().splitlines()
        fora["falha"] = u"nvidia-smi saiu com codigo %s%s" % (
            r["codigo"], (u": %s" % t[0][:120]) if t else u"")
        return fora
    for linha in r["saida"].strip().splitlines():
        c = [x.strip() for x in linha.split(",")]
        if len(c) < 5:
            continue
        fora["placas"].append({"indice": int(_num(c[0]) or 0),
                               "nome": u", ".join(c[1:len(c) - 3]),
                               "total_mb": _num(c[-3]), "livre_mb": _num(c[-2]),
                               "driver": c[-1]})
    if not fora["placas"]:
        fora["falha"] = u"nvidia-smi respondeu e nao listou placa"
    return fora


_PS_INVENTARIO = r"""
$ErrorActionPreference = 'SilentlyContinue'
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$v = @(Get-CimInstance Win32_VideoController | ForEach-Object {
  [pscustomobject]@{
    nome = $_.Name; fabricante = $_.AdapterCompatibility;
    driver = $_.DriverVersion;
    data = $(if ($_.DriverDate) { $_.DriverDate.ToString('yyyy-MM-dd') } else { '' });
    ram = $_.AdapterRAM; pnp = $_.PNPDeviceID; status = $_.Status;
    processador = $_.VideoProcessor } })
$m = @(Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}\0*' | ForEach-Object {
  [pscustomobject]@{ nome = $_.DriverDesc; mem = $_.'HardwareInformation.qwMemorySize' } })
$c = @(Get-CimInstance Win32_Processor | ForEach-Object {
  [pscustomobject]@{ nome = $_.Name; fisicos = $_.NumberOfCores;
    logicos = $_.NumberOfLogicalProcessors; mhz = $_.MaxClockSpeed } })
ConvertTo-Json -Depth 3 -Compress -InputObject @{ placas = $v; memoria = $m; cpu = $c }
"""

VENDORS = {"10DE": "nvidia", "8086": "intel", "1002": "amd", "1022": "amd",
           "1414": "microsoft", "15AD": "vmware", "1AB8": "parallels",
           "80EE": "virtualbox", "1234": "virtual"}


def _vendor_de(pnp, fabricante=u"", nome=u""):
    m = re.search(r"VEN_([0-9A-Fa-f]{4})", pnp or u"")
    if m and m.group(1).upper() in VENDORS:
        return VENDORS[m.group(1).upper()]
    t = (u"%s %s" % (fabricante or u"", nome or u"")).lower()
    for chave, v in (("nvidia", "nvidia"), ("intel", "intel"),
                     ("amd", "amd"), ("advanced micro", "amd"),
                     ("radeon", "amd"), ("microsoft", "microsoft"),
                     ("vmware", "vmware"), ("citrix", "virtual"),
                     ("remote", "microsoft")):
        if chave in t:
            return v
    return "outro"


def uso_pelo_pacote(vendor, cuda=None):
    if vendor == "nvidia":
        if cuda is not None and not cuda.get("disponivel"):
            return False, (u"NVIDIA, mas o torch deste pacote nao a alcanca: o "
                           u"TotalSegmentator roda na CPU (%s)"
                           % (cuda.get("motivo") or u"?"))
        return True, u"o TotalSegmentator usa (CUDA)"
    if vendor == "intel":
        return False, (u"o TotalSegmentator nao usa (OpenVINO e XPU foram "
                       u"medidos na pesquisa; o pacote nao os traz)")
    if vendor == "amd":
        return False, (u"o TotalSegmentator nao usa (o DirectML, que alcancaria "
                       u"esta placa, nao executa convolucao 3D - medido)")
    if vendor in ("microsoft", "vmware", "virtual", "parallels", "virtualbox"):
        return False, u"adaptador virtual ou de acesso remoto: nao calcula"
    return False, u"o TotalSegmentator nao usa"


FRASE_NA_TELA = {
    "nvidia": u"o TotalSegmentator usa (CUDA)",
    "nvidia_sem_torch": (u"NVIDIA, mas o torch deste pacote não a alcança: o "
                         u"TotalSegmentator roda na CPU"),
    "intel": (u"o TotalSegmentator não usa (OpenVINO e XPU foram medidos na "
              u"pesquisa; o pacote não os traz)"),
    "amd": (u"o TotalSegmentator não usa (o DirectML, que alcançaria esta "
            u"placa, não executa convolução 3D - medido)"),
    "virtual": u"adaptador virtual ou de acesso remoto: não calcula",
    "outro": u"o TotalSegmentator não usa",
}


def frase_na_tela(vendor, cuda=None):
    if vendor in ("microsoft", "vmware", "virtual", "parallels", "virtualbox"):
        return FRASE_NA_TELA["virtual"]
    if vendor == "nvidia" and cuda is not None and not cuda.get("disponivel"):
        return FRASE_NA_TELA["nvidia_sem_torch"]
    return FRASE_NA_TELA.get(vendor, FRASE_NA_TELA["outro"])


def cruzar_com_o_torch(placas, backends):
    cuda = (backends or {}).get("cuda")
    if cuda is None:
        return placas
    for p in placas or []:
        if p.get("vendor") == "nvidia":
            usa, frase = uso_pelo_pacote("nvidia", cuda)
            p["o_ts_usa"], p["frase"] = usa, frase
            p["frase_na_tela"] = frase_na_tela("nvidia", cuda)
    return placas


def _como_lista(v):
    if v is None:
        return []
    if isinstance(v, list):
        return v
    return [v]


def inventario_windows(timeout=PRAZO_POWERSHELL_S, timeout_wmic=PRAZO_WMIC_S):
    fora = {"placas": [], "cpu_cim": [], "falha": u"", "fonte": u""}
    if os.name != "nt":
        fora["falha"] = u"nao e Windows"
        return fora
    r = _rodar(["powershell", "-NoProfile", "-NonInteractive",
                "-ExecutionPolicy", "Bypass", "-Command", _PS_INVENTARIO],
               timeout)
    dados = None
    if not r["falha"] and r["codigo"] == 0:
        texto = r["saida"].strip()
        i = texto.find("{")
        try:
            dados = json.loads(texto[i:]) if i >= 0 else None
        except Exception as e:
            fora["falha"] = u"PowerShell respondeu ilegivel (%s)" % type(e).__name__
    else:
        fora["falha"] = u"PowerShell %s" % (r["falha"] or u"saiu com codigo %s"
                                             % r["codigo"])
    if dados is not None:
        fora["fonte"] = u"CIM (PowerShell)"
        mem = {}
        for m in _como_lista(dados.get("memoria")):
            if m and m.get("nome") and m.get("mem"):
                try:
                    mem[m["nome"]] = int(m["mem"])
                except Exception:
                    pass
        for p in _como_lista(dados.get("placas")):
            if not p:
                continue
            fora["placas"].append(_placa(p, mem))
        fora["cpu_cim"] = [c for c in _como_lista(dados.get("cpu")) if c]
        return fora
    w = _rodar(["wmic", "path", "Win32_VideoController", "get",
                "Name,AdapterCompatibility,DriverVersion,AdapterRAM,PNPDeviceID",
                "/format:csv"], timeout_wmic)
    if w["falha"] or w["codigo"] != 0:
        fora["falha"] += u" | wmic %s" % (w["falha"] or u"saiu com codigo %s"
                                          % w["codigo"])
        return fora
    fora["fonte"] = u"wmic (recuo: sem a memoria do registro)"
    cab = None
    for linha in w["saida"].splitlines():
        c = [x.strip() for x in linha.split(",")]
        if len(c) < 5 or not any(c):
            continue
        if cab is None:
            cab = [x.lower() for x in c]
            continue
        d = dict(zip(cab, c))
        fora["placas"].append(_placa({
            "nome": d.get("name"), "fabricante": d.get("adaptercompatibility"),
            "driver": d.get("driverversion"), "ram": d.get("adapterram"),
            "pnp": d.get("pnpdeviceid")}, {}))
    return fora


_CLASSE_VIDEO = (r"SYSTEM\CurrentControlSet\Control\Class"
                 r"\{4d36e968-e325-11ce-bfc1-08002be10318}")


def placas_do_registro():
    if os.name != "nt":
        return []
    fora = []
    try:
        import winreg
        raiz = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, _CLASSE_VIDEO)
    except Exception:
        return []
    i = 0
    while True:
        try:
            sub = winreg.EnumKey(raiz, i)
        except OSError:
            break
        i += 1
        if not re.match(r"^\d{4}$", sub):
            continue
        try:
            k = winreg.OpenKey(raiz, sub)
        except OSError:
            continue

        def ler(nome):
            try:
                return winreg.QueryValueEx(k, nome)[0]
            except OSError:
                return None
        desc = ler("DriverDesc")
        if not desc:
            continue
        mem = ler("HardwareInformation.qwMemorySize")
        if mem is None:
            bruto = ler("HardwareInformation.MemorySize")
            if isinstance(bruto, (bytes, bytearray)) and len(bruto) >= 4:
                mem = int.from_bytes(bytes(bruto[:8]), "little")
            elif isinstance(bruto, int):
                mem = bruto
        p = _placa({"nome": desc, "fabricante": ler("ProviderName") or u"",
                    "driver": ler("DriverVersion") or u"",
                    "data": ler("DriverDate") or u"",
                    "pnp": ler("MatchingDeviceId") or u"",
                    "ram": mem}, {})
        p["memoria_fonte"] = (u"registro (a classe guarda o driver instalado; "
                              u"o CIM do arranque lista so o presente)")
        fora.append(p)
    return fora


def placas_rapidas():
    try:
        inv = ULTIMO.get("diagnostico") or {}
        if inv.get("placas"):
            return list(inv["placas"])
        return placas_do_registro()
    except Exception:
        return []


_INTEGRADA = re.compile(
    r"(?i)(\buhd\b|\biris\b|\bhd graphics\b|^intel\(r\) graphics$"
    r"|\barc\(tm\) graphics\b|\barc\(tm\) \d{3}v\b"
    r"|\bvega \d+ graphics\b|radeon\(tm\) graphics|radeon\(tm\) \d{3}m\b)")


def placa_integrada(nome):
    return bool(_INTEGRADA.search((nome or u"").strip()))


def _placa(p, mem):
    nome = (p.get("nome") or u"?").strip()
    vendor = _vendor_de(p.get("pnp"), p.get("fabricante"), nome)
    usa, frase = uso_pelo_pacote(vendor)
    ram = _num(p.get("ram"))
    real = mem.get(nome)
    mb = (real if real else ram)
    return {"nome": nome, "vendor": vendor,
            "fabricante": (p.get("fabricante") or u"").strip(),
            "driver": (p.get("driver") or u"").strip(),
            "data_driver": (p.get("data") or u"").strip(),
            "memoria_mb": int(mb // 1048576) if mb else None,
            "memoria_fonte": u"registro" if real else (u"CIM (uint32)" if ram else u""),
            "integrada": placa_integrada(nome),
            "status": (p.get("status") or u"").strip(),
            "o_ts_usa": usa, "frase": frase}


def topologia_da_cpu():
    fora = {"fisicos": None, "logicos": os.cpu_count() or None,
            "classes": {}, "fonte": u"os.cpu_count", "falha": u""}
    if os.name != "nt":
        fora["falha"] = u"nao e Windows"
        return fora
    try:
        import ctypes
        import struct
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        f = k32.GetLogicalProcessorInformationEx
        f.argtypes = [ctypes.c_int, ctypes.c_void_p,
                      ctypes.POINTER(ctypes.c_ulong)]
        f.restype = ctypes.c_int
        tam = ctypes.c_ulong(0)
        f(0, None, ctypes.byref(tam))
        if not tam.value:
            raise OSError("tamanho zero (erro %d)" % ctypes.get_last_error())
        buf = ctypes.create_string_buffer(tam.value)
        if not f(0, buf, ctypes.byref(tam)):
            raise OSError("erro %d" % ctypes.get_last_error())
        bruto = buf.raw[:tam.value]
        pos, nucleos, logicos, classes = 0, 0, 0, {}
        while pos + 8 <= len(bruto):
            rel, size = struct.unpack_from("<II", bruto, pos)
            if size <= 0:
                break
            if rel == 0 and pos + 40 <= len(bruto):
                _flags, efic = struct.unpack_from("<BB", bruto, pos + 8)
                ngrp = struct.unpack_from("<H", bruto, pos + 30)[0]
                n_log = 0
                for g in range(ngrp):
                    off = pos + 32 + 16 * g
                    if off + 8 > len(bruto):
                        break
                    mask = struct.unpack_from("<Q", bruto, off)[0]
                    n_log += bin(mask).count("1")
                nucleos += 1
                logicos += n_log
                classes[int(efic)] = classes.get(int(efic), 0) + 1
            pos += size
        if nucleos:
            fora.update({"fisicos": nucleos, "logicos": logicos or fora["logicos"],
                         "classes": classes,
                         "fonte": u"GetLogicalProcessorInformationEx"})
    except Exception as e:
        fora["falha"] = u"%s: %s" % (type(e).__name__, str(e)[:100])
    return fora


def descrever_cpu(topo, nome=u""):
    partes = []
    if nome:
        partes.append(nome.strip())
    fis, log = topo.get("fisicos"), topo.get("logicos")
    if fis:
        partes.append(u"%d nucleo(s) fisico(s), %s logico(s)" % (fis, log or u"?"))
    else:
        partes.append(u"%s nucleo(s) logico(s); os fisicos nao foram lidos (%s)"
                      % (log or u"?", topo.get("falha") or topo.get("fonte")))
    cl = topo.get("classes") or {}
    if len(cl) > 1:
        altas = max(cl)
        p = cl.get(altas, 0)
        e = sum(n for k, n in cl.items() if k != altas)
        partes.append(u"hibrida: %d nucleo(s) de desempenho + %d de eficiencia"
                      % (p, e))
    return u" | ".join(partes)


def memoria():
    try:
        import radai_cleaner
        return radai_cleaner.memoria_da_estacao() or {}
    except Exception as e:
        return {"falha": type(e).__name__}


def _comando_filho(python_exe, modo, argumentos, caminhos_antes=None):
    cmd = [python_exe or sys.executable, os.path.abspath(__file__), modo]
    cmd += list(argumentos or [])
    for c in caminhos_antes or ():
        cmd += ["--caminho-antes", c]
    return cmd


def _ler_marcada(r, marca):
    if r.get("falha"):
        return {"falha": u"o filho %s" % r["falha"]}
    for linha in reversed((r.get("saida") or u"").splitlines()):
        if linha.startswith(marca):
            try:
                return json.loads(linha[len(marca):])
            except Exception as e:
                return {"falha": u"resposta ilegivel (%s)" % type(e).__name__}
    ultima = ((r.get("erro") or u"").strip().splitlines() or [u""])[-1]
    return {"falha": u"o filho saiu com codigo %s sem responder%s"
                     % (r.get("codigo"), (u": " + ultima[:160]) if ultima else u"")}


def sondar(familia, python_exe=None, caminhos_antes=None, timeout=120):
    r = _rodar(_comando_filho(python_exe, "--sonda", [familia], caminhos_antes),
               timeout)
    d = _ler_marcada(r, MARCA_SONDA)
    d.setdefault("familia", familia)
    d["segundos"] = r.get("segundos")
    return d


def backends_das_sondas(sondas):
    fora = {}
    tr = sondas.get("torch") or {}
    for b in ("torch_cpu", "cuda", "xpu"):
        if tr.get("falha"):
            fora[b] = {"disponivel": False, "motivo": tr["falha"]}
            continue
        if not tr.get("importa"):
            fora[b] = {"disponivel": False,
                       "motivo": u"o torch nao importa (%s)" % (tr.get("erro") or u"?")}
            continue
        if b == "torch_cpu":
            fora[b] = {"disponivel": True, "versao": tr.get("versao"),
                       "dispositivos": [u"CPU"]}
        elif b == "cuda":
            fora[b] = ({"disponivel": True, "versao": tr.get("cuda"),
                        "dispositivos": tr.get("cuda_placas") or []}
                       if tr.get("cuda_disponivel")
                       else {"disponivel": False,
                             "motivo": u"torch %s: CUDA %s" % (
                                 tr.get("versao"),
                                 u"indisponivel" if tr.get("cuda")
                                 else u"ausente (build de CPU)")})
        else:
            fora[b] = ({"disponivel": True, "versao": tr.get("versao"),
                        "dispositivos": tr.get("xpu_placas") or []}
                       if tr.get("xpu_disponivel")
                       else {"disponivel": False,
                             "motivo": tr.get("xpu_motivo")
                             or u"torch %s sem XPU" % tr.get("versao")})
    dm = sondas.get("directml") or {}
    if dm.get("disponivel"):
        fora["directml"] = {"disponivel": True, "versao": dm.get("versao"),
                            "dispositivos": dm.get("placas") or []}
    else:
        fora["directml"] = {"disponivel": False,
                            "motivo": dm.get("falha") or dm.get("erro")
                            or u"torch_directml nao instalado neste Python"}
    ov = sondas.get("openvino") or {}
    devs = ov.get("dispositivos") or {}
    for b, chave in (("openvino_cpu", "CPU"), ("openvino_gpu", "GPU")):
        if ov.get("importa") and any(k.split(".")[0] == chave for k in devs):
            fora[b] = {"disponivel": True, "versao": ov.get("versao"),
                       "dispositivos": [v for k, v in sorted(devs.items())
                                        if k.split(".")[0] == chave]}
        else:
            fora[b] = {"disponivel": False,
                       "motivo": ov.get("falha") or ov.get("erro")
                       or (u"openvino nao instalado neste Python"
                           if not ov.get("importa")
                           else u"o OpenVINO nao ve dispositivo %s" % chave)}
    return fora


def pasta_do_canario(pasta_pesos):
    if not pasta_pesos or not os.path.isdir(pasta_pesos):
        return None
    for d in sorted(os.listdir(pasta_pesos)):
        if not d.startswith("Dataset%d_" % CANARIO_DATASET):
            continue
        base = os.path.join(pasta_pesos, d)
        try:
            filhos = sorted(os.listdir(base))
        except OSError:
            continue
        for s in filhos:
            if s.endswith("__nnUNetPlans__3d_fullres"):
                cam = os.path.join(base, s)
                if (os.path.isfile(os.path.join(cam, "plans.json"))
                        and os.path.isfile(os.path.join(cam, "fold_0",
                                                        "checkpoint_final.pth"))):
                    return cam
    return None


def canario(backend, python_exe=None, pasta_pesos=None, threads=None,
            repeticoes=1, caminhos_antes=None, timeout=900,
            baixa_prioridade=True, precisao=None):
    modelo = pasta_do_canario(pasta_pesos)
    if not modelo:
        return {"backend": backend, "aprovado": False,
                "falha": u"sem o modelo do canario (Dataset%d, nnUNetPlans) "
                         u"em %s" % (CANARIO_DATASET, pasta_pesos or u"?")}
    args = [backend, "--modelo", modelo, "--repeticoes", str(int(repeticoes))]
    if threads:
        args += ["--threads", str(int(threads))]
    if precisao:
        args += ["--precisao", str(precisao)]
    r = _rodar(_comando_filho(python_exe, "--canario", args, caminhos_antes),
               timeout, baixa_prioridade=baixa_prioridade)
    d = _ler_marcada(r, MARCA_CANARIO)
    d["backend"] = backend
    d["segundos_filho"] = r.get("segundos")
    return julgar(d)


def julgar(d):
    if d.get("falha"):
        d["aprovado"] = False
        d["motivo"] = d["falha"]
        return d
    conc = d.get("concordancia")
    n_cl = sum(1 for c in (d.get("contagem_ref") or []) if c)
    if d.get("contagem_ref") is not None and n_cl < CLASSES_MINIMAS:
        d["aprovado"] = False
        d["motivo"] = (u"canario inerte: a referencia so tem %d classe(s) no "
                       u"argmax (minimo %d) - o fantoma nao exercita a rede"
                       % (n_cl, CLASSES_MINIMAS))
    elif d.get("nao_finito"):
        d["aprovado"] = False
        d["motivo"] = u"a saida tem NaN ou infinito"
    elif conc is None:
        d["aprovado"] = False
        d["motivo"] = u"o filho nao mediu a concordancia"
    elif conc < LIMIAR_CONCORDANCIA:
        d["aprovado"] = False
        d["motivo"] = (u"concordancia do argmax %.4f%% < %.1f%%"
                       % (conc * 100.0, LIMIAR_CONCORDANCIA * 100.0))
    else:
        d["aprovado"] = True
        d["motivo"] = (u"identico a referencia (mesmo sha256)"
                       if d.get("sha256") == d.get("sha256_ref")
                       else u"concordancia do argmax %.4f%%, maior diferenca "
                            u"de logit %.2g" % (conc * 100.0,
                                                d.get("max_dif_logit") or 0.0))
    ref = CANARIO_REFERENCIA
    if d.get("fantoma_sha256") and d["fantoma_sha256"] != FANTOMA_SHA256:
        d["fabrica"] = (u"nao comparavel: o fantoma desta estacao saiu "
                        u"diferente do de fabrica (numpy?)")
    elif ref and d.get("sha256_ref"):
        d["fabrica"] = (u"identica" if d["sha256_ref"] == ref.get("sha256")
                        else u"DIFERENTE da de fabrica (pesos, torch ou "
                             u"instrucoes desta CPU nao sao os da montagem)")
    else:
        d["fabrica"] = u"sem referencia de fabrica"
    return d


def sonda_torch_do_arranque(r):
    r = dict(r or {})
    if r.get("falha"):
        return {"familia": "torch", "falha": r["falha"]}
    return {"familia": "torch", "importa": bool(r.get("importa")),
            "erro": r.get("erro"), "versao": r.get("versao"),
            "cuda": r.get("cuda"), "cuda_disponivel": bool(r.get("disponivel")),
            "cuda_placas": [u"%s (%s MiB)" % (p.get("nome"), p.get("total_mb"))
                            for p in r.get("placas") or []],
            "xpu_disponivel": bool(r.get("xpu_disponivel")),
            "xpu_placas": list(r.get("xpu_placas") or []),
            "xpu_motivo": r.get("xpu_motivo")}


def inventario(python_exe=None, caminhos_antes=None, sondas_timeout=120,
               sondas_prontas=None):
    t0 = time.time()
    win = inventario_windows()
    nv = placas_nvidia()
    topo = topologia_da_cpu()
    nome_cpu = u""
    for c in win.get("cpu_cim") or []:
        nome_cpu = (c.get("nome") or u"").strip()
        if topo.get("fisicos") is None and c.get("fisicos"):
            topo["fisicos"] = int(c["fisicos"])
            topo["fonte"] = u"CIM Win32_Processor"
        break
    if not nome_cpu:
        nome_cpu = (platform.processor() or u"")[:80]
    sondas = dict(sondas_prontas or {})
    for fam in FAMILIAS_DE_SONDA:
        if fam not in sondas:
            sondas[fam] = sondar(fam, python_exe, caminhos_antes,
                                 timeout=sondas_timeout)
    backends = backends_das_sondas(sondas)
    d = {"quando": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
         "placas": cruzar_com_o_torch(win.get("placas") or [], backends),
         "placas_fonte": win.get("fonte") or u"",
         "placas_falha": win.get("falha") or u"",
         "nvidia": nv, "cpu": dict(topo, nome=nome_cpu),
         "memoria": memoria(), "sondas": sondas,
         "backends": backends}
    d["segundos"] = round(time.time() - t0, 1)
    return d


BACKENDS_DE_PLACA = ("cuda", "xpu", "openvino_gpu", "directml")


def device_e_cpu(device):
    return str(device or u"").strip().lower() == "cpu"


def candidatos_ao_canario(inv, device=None):
    bk = inv.get("backends") or {}
    sem_placa = device_e_cpu(device)
    fora = [b for b in BACKENDS
            if b != "torch_cpu" and (bk.get(b) or {}).get("disponivel")
            and POLITICA_DE_ADOCAO.get(b) != "recusado"
            and not (sem_placa and b in BACKENDS_DE_PLACA)]
    return fora


def rodar_canarios(inv, python_exe=None, pasta_pesos=None, threads=None,
                   caminhos_antes=None, log=None, cache=None, device=None):
    log = log or (lambda m: None)
    fora = {}
    salvo = _ler_cache(cache)
    falhas_antes = salvo.get(CHAVE_FALHAS) if isinstance(
        salvo.get(CHAVE_FALHAS), dict) else {}
    for b in candidatos_ao_canario(inv, device):
        imp = impressao(inv, b, pasta_pesos)
        antigo = salvo.get(b) or {}
        if (antigo.get("impressao") == imp and "aprovado" in antigo
                and medida_completa(antigo)):
            r = dict(antigo)
            r["do_cache"] = True
            fora[b] = julgar(r)
            log(u"canario %s: do cache de %s -> %s" % (
                b, antigo.get("quando") or u"?", _veredito(fora[b])))
            continue
        livre = (memoria() or {}).get("livre_mb")
        pede = memoria_minima_do_canario(b)
        if livre is not None and livre < pede:
            fora[b] = {"backend": b, "aprovado": False, "adiado": True,
                       "motivo": u"adiado: %d MB de RAM livre, o canario de %s "
                                 u"pede %d" % (livre, b, pede)}
            log(u"canario %s: %s" % (b, fora[b]["motivo"]))
            continue
        log(u"canario %s: rodando (processo filho, prioridade baixa)..." % b)
        r = canario(b, python_exe=python_exe, pasta_pesos=pasta_pesos,
                    threads=threads, caminhos_antes=caminhos_antes)
        r["impressao"] = imp
        r["quando"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        fora[b] = r
        linha = u"canario %s: %s" % (b, _veredito(r))
        ant = falhas_antes.get(b) or {}
        if r.get("falha") and ant.get("impressao") == imp:
            linha += (u" (a partida de %s tambem falhou: %s)"
                      % (ant.get("quando") or u"?",
                         (ant.get("motivo") or u"?")[:120]))
        log(linha)
    if cache and fora:
        novo = dict(salvo)
        falhas = dict(falhas_antes)
        for b, r in fora.items():
            if r.get("do_cache"):
                continue
            if medida_completa(r):
                novo[b] = r
                falhas.pop(b, None)
                continue
            novo.pop(b, None)
            if r.get("falha"):
                falhas[b] = {"quando": r.get("quando"),
                             "impressao": r.get("impressao"),
                             "motivo": (r.get("falha") or u"")[:300]}
        novo[CHAVE_FALHAS] = falhas
        _gravar_cache(cache, novo)
    return fora


CHAVE_FALHAS = "falhas_recentes"


def medida_completa(r):
    if not isinstance(r, dict) or r.get("falha") or r.get("adiado"):
        return False
    return r.get("concordancia") is not None or bool(r.get("nao_finito"))


def _veredito(r):
    if r.get("aprovado"):
        base = u"APROVADO - %s" % r.get("motivo")
    elif r.get("adiado"):
        base = u"ADIADO, nao conferido - %s" % (r.get("motivo") or u"?")
    elif r.get("falha"):
        base = u"FALHOU, nao conferido - %s" % (r.get("falha") or u"?")
    else:
        base = u"REPROVADO - %s" % (r.get("motivo") or u"?")
    if r.get("s_por_patch") and r.get("s_por_patch_ref"):
        base += (u" | %.2f s/patch contra %.2f do PyTorch CPU"
                 % (r["s_por_patch"], r["s_por_patch_ref"]))
    if r.get("rss_pico_mb"):
        try:
            base += u" | pico de RAM do filho %d MB" % int(r["rss_pico_mb"])
        except (TypeError, ValueError):
            pass
    return base


def impressao(inv, backend, pasta_pesos):
    bk = (inv.get("backends") or {}).get(backend) or {}
    placas = sorted(u"%s|%s" % (p.get("nome"), p.get("driver"))
                    for p in inv.get("placas") or [])
    ck = u""
    m = pasta_do_canario(pasta_pesos)
    if m:
        try:
            st = os.stat(os.path.join(m, "fold_0", "checkpoint_final.pth"))
            ck = u"%d|%d" % (st.st_size, int(st.st_mtime))
        except OSError:
            ck = u"?"
    base = json.dumps([CANARIO_VERSAO, backend, bk.get("versao"),
                       bk.get("dispositivos"), placas,
                       (inv.get("cpu") or {}).get("nome"), ck], sort_keys=True)
    return hashlib.sha256(base.encode("utf-8")).hexdigest()[:16]


def _ler_cache(cache):
    if not cache or not os.path.isfile(cache):
        return {}
    try:
        with io.open(cache, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _gravar_cache(cache, d):
    try:
        pasta = os.path.dirname(cache)
        if pasta and not os.path.isdir(pasta):
            os.makedirs(pasta)
        tmp = cache + ".tmp"
        with io.open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=True, indent=1)
        os.replace(tmp, cache)
    except Exception:
        pass


def admitidos(inv, canarios):
    bk = inv.get("backends") or {}
    fora = []
    for b in BACKENDS:
        if not (bk.get(b) or {}).get("disponivel"):
            continue
        if b == "torch_cpu":
            fora.append(b)
            continue
        if POLITICA_DE_ADOCAO.get(b) != "producao":
            continue
        if (canarios or {}).get(b, {}).get("aprovado"):
            fora.append(b)
    return fora


def executor_para_o_envelope(inv, canarios):
    adm = admitidos(inv, canarios)
    for b in ("xpu", "openvino_gpu", "openvino_cpu"):
        if b in adm:
            return {"RADAI_EXECUTOR": b}
    return {}


AVISO_DA_FILA = (u"a fila ainda decide placa ou CPU pela VRAM "
                 u"(engine.plano_de_dispositivo), e nao por esta lista")

ROTULO_FORA = {
    "device_cpu": u"NAO CONFERIDO (DEVICE=cpu: a placa nao e usada pelo app)",
    "rodando": u"NAO CONFERIDO (o canario ainda roda)",
    "sem_resultado": u"NAO CONFERIDO (sem resultado do canario)",
    "adiado": u"NAO CONFERIDO (adiado)",
    "falhou": u"NAO CONFERIDO (o canario falhou)",
    "reprovado": u"REPROVADO no canario",
    "politica": u"fora pela politica de adocao",
}


def conferencia(inv, canarios, rodando=False, device=None):
    bk = inv.get("backends") or {}
    canarios = canarios or {}
    conf = admitidos(inv, canarios)
    candidatos = set(candidatos_ao_canario(inv, device))
    fora = []
    for b in BACKENDS:
        if b in conf or not (bk.get(b) or {}).get("disponivel"):
            continue
        pol = POLITICA_DE_ADOCAO.get(b, u"?")
        r = canarios.get(b)
        if (device_e_cpu(device) and b in BACKENDS_DE_PLACA
                and pol != "recusado"):
            est, mot = "device_cpu", (u"DEVICE=cpu no radai_watcher.config: o "
                                      u"canario desta placa nao roda")
        elif b not in candidatos:
            est, mot = "politica", u"politica %s (%s)" % (
                pol, MOTIVO_DA_POLITICA.get(b) or u"?")
        elif r is None:
            est = "rodando" if rodando else "sem_resultado"
            mot = (u"o resultado sai no log quando o canario terminar"
                   if rodando else u"o canario nao rodou nesta partida")
        elif r.get("adiado"):
            est, mot = "adiado", r.get("motivo") or u"?"
        elif r.get("falha"):
            est, mot = "falhou", r.get("falha") or u"?"
        elif not r.get("aprovado"):
            est, mot = "reprovado", r.get("motivo") or u"?"
        else:
            est, mot = "politica", (u"aprovado no canario, mas a politica e "
                                    u"%s (%s)" % (pol, MOTIVO_DA_POLITICA.get(b)
                                                  or u"?"))
        fora.append({"backend": b, "estado": est, "motivo": mot,
                     "politica": pol})
    return {"conferidos": conf, "fora": fora}


def linhas_da_conferencia(inv, canarios, rodando=False, device=None):
    c = conferencia(inv, canarios, rodando, device)
    L = [u"backends conferidos pelo canario: %s" % (
        u", ".join((u"%s (o chao, sem canario)" % b) if b == "torch_cpu" else b
                   for b in c["conferidos"]) or u"nenhum")]
    for f in c["fora"]:
        L.append(u"  %s: %s - %s" % (f["backend"], ROTULO_FORA[f["estado"]],
                                     f["motivo"]))
    L.append(u"  (%s)" % AVISO_DA_FILA)
    return L


def resumo_da_conferencia(inv, canarios, rodando=False, device=None):
    c = conferencia(inv, canarios, rodando, device)
    partes = [u"conferidos: %s" % (u", ".join(c["conferidos"]) or u"nenhum")]
    partes += [u"%s %s" % (f["backend"], ROTULO_FORA[f["estado"]])
               for f in c["fora"] if f["estado"] != "politica"]
    partes.append(AVISO_DA_FILA)
    return u" | ".join(partes)


def canarios_em_segundo_plano(inv, python_exe=None, pasta_pesos=None,
                              threads=None, log=None, cache=None,
                              caminhos_antes=None, device=None):
    log = log or (lambda m: None)
    ULTIMO["device"] = device
    if not candidatos_ao_canario(inv, device):
        ULTIMO["canarios"] = {}
        log(u"canario: nenhum backend alem do PyTorch CPU a conferir nesta "
            u"estacao (o PyTorch CPU e o chao, e nao tem com quem ser "
            u"comparado)")
        return None
    with _TRAVA:
        if ULTIMO.get("canario_rodando"):
            return None
        ULTIMO["canario_rodando"] = True

    def _alvo():
        try:
            r = rodar_canarios(inv, python_exe=python_exe,
                               pasta_pesos=pasta_pesos, threads=threads,
                               caminhos_antes=caminhos_antes, log=log,
                               cache=cache, device=device)
            ULTIMO["canarios"] = r
            for linha in linhas_da_conferencia(inv, r, device=device):
                log(u"canario: %s" % linha.strip())
        except Exception as e:
            log(u"canario: falhou (%s: %s) - os conferidos ficam so com o "
                u"PyTorch CPU, e %s"
                % (type(e).__name__, str(e)[:160], AVISO_DA_FILA))
        finally:
            ULTIMO["canario_rodando"] = False

    t = threading.Thread(target=_alvo, name="radai-canario", daemon=True)
    t.start()
    return t


def backends_admitidos():
    inv = ULTIMO.get("diagnostico")
    if not inv:
        return None
    return admitidos(inv, ULTIMO.get("canarios") or {})


def conferencia_atual():
    inv = ULTIMO.get("diagnostico")
    if not inv:
        return None
    return conferencia(inv, ULTIMO.get("canarios") or {},
                       rodando=bool(ULTIMO.get("canario_rodando")),
                       device=ULTIMO.get("device"))


def linhas(inv, canarios=None):
    L = []
    pls = inv.get("placas") or []
    if pls:
        for i, p in enumerate(pls):
            mem = (u"%d MiB%s" % (p["memoria_mb"],
                                  u" compartilhada" if p.get("integrada") else u"")
                   if p.get("memoria_mb") else u"memoria nao lida")
            L.append(u"placa de video [%d]: %s | %s | driver %s%s | %s"
                     % (i, p["nome"], mem, p.get("driver") or u"?",
                        (u" de %s" % p["data_driver"]) if p.get("data_driver") else u"",
                        p.get("frase")))
    else:
        L.append(u"placas de video: nenhuma listada (%s)"
                 % (inv.get("placas_falha") or u"?"))
    cpu = inv.get("cpu") or {}
    L.append(u"cpu: %s" % descrever_cpu(cpu, cpu.get("nome") or u""))
    for b in BACKENDS:
        x = (inv.get("backends") or {}).get(b) or {}
        pol = POLITICA_DE_ADOCAO.get(b, u"?")
        if pol != "producao" and MOTIVO_DA_POLITICA.get(b):
            pol = u"%s (%s)" % (pol, MOTIVO_DA_POLITICA[b])
        if x.get("disponivel"):
            L.append(u"backend %s: disponivel (%s%s) | politica: %s"
                     % (b, x.get("versao") or u"?",
                        (u"; " + u", ".join(x.get("dispositivos") or []))
                        if x.get("dispositivos") else u"", pol))
        else:
            L.append(u"backend %s: indisponivel (%s) | politica: %s"
                     % (b, x.get("motivo") or u"?", pol))
    if canarios is not None:
        if not canarios:
            L.append(u"canario: nenhum backend alem do PyTorch CPU a conferir "
                     u"(o PyTorch CPU e o chao, e nao tem com quem ser comparado)")
        for b, r in sorted(canarios.items()):
            L.append(u"canario %s: %s" % (b, _veredito(r)))
        L.extend(linhas_da_conferencia(inv, canarios))
    return L


def _filho_sonda(familia):
    r = {"familia": familia, "importa": False}
    try:
        import importlib.util as _iu
        alvo = {"directml": "torch_directml", "openvino": "openvino"}.get(familia)
        if alvo and _iu.find_spec(alvo) is None:
            r["erro"] = "%s nao instalado neste Python" % alvo
            return r
    except Exception:
        pass
    if familia == "torch":
        try:
            import torch
            r["importa"] = True
            r["versao"] = str(torch.__version__)
            r["cuda"] = str(getattr(torch.version, "cuda", None) or "")
            r["cuda_disponivel"] = bool(torch.cuda.is_available())
            r["cuda_placas"] = []
            if r["cuda_disponivel"]:
                for i in range(torch.cuda.device_count()):
                    p = torch.cuda.get_device_properties(i)
                    r["cuda_placas"].append("%s (%d MiB)" % (
                        p.name, int(p.total_memory // 1048576)))
            xpu = getattr(torch, "xpu", None)
            if xpu is None:
                r["xpu_disponivel"] = False
                r["xpu_motivo"] = "torch %s sem o modulo xpu" % r["versao"]
            else:
                try:
                    r["xpu_disponivel"] = bool(xpu.is_available())
                    r["xpu_placas"] = ([xpu.get_device_name(i)
                                        for i in range(xpu.device_count())]
                                       if r["xpu_disponivel"] else [])
                    if not r["xpu_disponivel"]:
                        r["xpu_motivo"] = ("torch %s: xpu.is_available() falso"
                                           % r["versao"])
                except Exception as e:
                    r["xpu_disponivel"] = False
                    r["xpu_motivo"] = "%s: %s" % (type(e).__name__, str(e)[:160])
        except Exception as e:
            r["erro"] = "%s: %s" % (type(e).__name__, str(e)[:200])
    elif familia == "directml":
        try:
            import torch
            import torch_directml
            r["importa"] = True
            r["versao"] = "torch %s + torch_directml %s" % (
                torch.__version__, _versao_dist("torch-directml"))
            r["disponivel"] = bool(torch_directml.is_available())
            r["placas"] = [torch_directml.device_name(i)
                           for i in range(torch_directml.device_count())]
        except Exception as e:
            r["erro"] = "%s: %s" % (type(e).__name__, str(e)[:200])
    elif familia == "openvino":
        try:
            import openvino as ov
            r["importa"] = True
            r["versao"] = str(ov.__version__).split("-")[0]
            c = ov.Core()
            r["dispositivos"] = {}
            for d in c.available_devices:
                try:
                    r["dispositivos"][d] = str(c.get_property(d, "FULL_DEVICE_NAME"))
                except Exception:
                    r["dispositivos"][d] = d
        except Exception as e:
            r["erro"] = "%s: %s" % (type(e).__name__, str(e)[:200])
    else:
        r["erro"] = "familia desconhecida: %s" % familia
    return r


def _versao_dist(nome):
    try:
        from importlib import metadata
        return metadata.version(nome)
    except Exception:
        return "?"


def _rss_pico_mb():
    if os.name != "nt":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        class PMC(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                        ("PeakWorkingSetSize", ctypes.c_size_t),
                        ("WorkingSetSize", ctypes.c_size_t),
                        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                        ("PagefileUsage", ctypes.c_size_t),
                        ("PeakPagefileUsage", ctypes.c_size_t)]
        k32 = ctypes.WinDLL("kernel32")
        k32.GetCurrentProcess.restype = wintypes.HANDLE
        try:
            f = k32.K32GetProcessMemoryInfo
        except AttributeError:
            f = ctypes.WinDLL("psapi").GetProcessMemoryInfo
        f.argtypes = [wintypes.HANDLE, ctypes.POINTER(PMC), wintypes.DWORD]
        f.restype = wintypes.BOOL
        p = PMC()
        p.cb = ctypes.sizeof(PMC)
        if f(k32.GetCurrentProcess(), ctypes.byref(p), p.cb):
            return int(p.PeakWorkingSetSize // 1048576)
    except Exception:
        pass
    return None


def fantoma(np, lado, props, mm=1.5):
    ix = np.arange(lado, dtype=np.float64)
    a, b, k = np.meshgrid(ix, ix, ix, indexing="ij")
    c = (lado - 1) / 2.0
    X, Y, Z = (a - c) * mm, (b - c) * mm, (k - c) * mm

    def elip(cx, cy, cz, rx, ry, rz):
        return (((X - cx) / rx) ** 2 + ((Y - cy) / ry) ** 2
                + ((Z - cz) / rz) ** 2) <= 1.0

    def cil(cx, cy, r):
        return ((X - cx) ** 2 + (Y - cy) ** 2) <= r * r

    hu = np.full((lado, lado, lado), -1000.0)
    corpo = ((X / 165.0) ** 2 + ((Y - 5.0) / 115.0) ** 2) <= 1.0
    hu[corpo] = -100.0
    hu[((X / 150.0) ** 2 + ((Y - 5.0) / 100.0) ** 2) <= 1.0] = 50.0
    dentro = ((X / 140.0) ** 2 + ((Y - 5.0) / 90.0) ** 2) <= 1.0
    hu[dentro] = -60.0
    for sx in (-1.0, 1.0):
        hu[elip(sx * 75.0, 0.0, 70.0, 62.0, 85.0, 95.0) & dentro] = -850.0
    hu[elip(-15.0, 30.0, 45.0, 58.0, 48.0, 55.0)] = 40.0
    hu[elip(60.0, 5.0, -40.0, 85.0, 80.0, 65.0) & dentro] = 60.0
    est = elip(-60.0, 35.0, -35.0, 40.0, 35.0, 45.0) & dentro
    hu[est] = 25.0
    hu[est & (Y > 45.0)] = -900.0
    hu[elip(-100.0, -35.0, -40.0, 25.0, 40.0, 50.0) & dentro] = 48.0
    for sx in (-1.0, 1.0):
        hu[elip(sx * 55.0, -50.0, -85.0, 28.0, 28.0, 55.0) & dentro] = 32.0
    hu[cil(0.0, -62.0, 20.0)] = 700.0
    hu[cil(0.0, -62.0, 16.0)] = 250.0
    hu[cil(0.0, -88.0, 8.0)] = 20.0
    hu[cil(-22.0, -38.0, 12.0)] = 45.0
    hu[cil(-8.0, -30.0, 8.0) & (Z > 0)] = 40.0
    hu[cil(-8.0, -30.0, 3.0) & (Z > 0)] = -900.0
    h = ((a.astype(np.uint64) * np.uint64(73856093))
         ^ (b.astype(np.uint64) * np.uint64(19349663))
         ^ (k.astype(np.uint64) * np.uint64(83492791)))
    ruido = (h % np.uint64(41)).astype(np.float64) - 20.0
    hu = np.where(corpo, hu + ruido, hu)
    lo = float(props["percentile_00_5"])
    hi = float(props["percentile_99_5"])
    hu = (np.clip(hu, lo, hi) - float(props["mean"])) / max(float(props["std"]), 1e-8)
    return hu.astype(np.float32)[None, None]


def _montar_rede(torch, pasta_modelo):
    import pydoc
    with io.open(os.path.join(pasta_modelo, "plans.json"), encoding="utf-8") as f:
        plans = json.load(f)
    with io.open(os.path.join(pasta_modelo, "dataset.json"), encoding="utf-8") as f:
        ds = json.load(f)
    cfg = plans["configurations"]["3d_fullres"]
    arq = cfg["architecture"]
    kw = dict(arq["arch_kwargs"])
    for k in arq.get("_kw_requires_import") or ():
        if kw.get(k) is not None:
            kw[k] = pydoc.locate(kw[k])
    cls = pydoc.locate(arq["network_class_name"])
    if cls is None:
        raise ImportError("classe da rede nao encontrada: %s"
                          % arq["network_class_name"])
    n_classes = len(ds["labels"])
    n_canais = len(ds.get("channel_names") or ds.get("modality") or {"0": 1})
    rede = cls(input_channels=n_canais, num_classes=n_classes,
               deep_supervision=False, **kw)
    ck = torch.load(os.path.join(pasta_modelo, "fold_0", "checkpoint_final.pth"),
                    map_location="cpu", weights_only=False)
    rede.load_state_dict(ck["network_weights"])
    rede.eval()
    props = plans["foreground_intensity_properties_per_channel"]["0"]
    return rede, props, cfg["patch_size"], n_classes


def _filho_canario(backend, pasta_modelo, threads, repeticoes, precisao):
    import numpy as np
    import torch
    r = {"backend": backend, "canario_versao": CANARIO_VERSAO,
         "torch": str(torch.__version__)}
    if threads:
        torch.set_num_threads(int(threads))
    r["threads"] = int(torch.get_num_threads())
    t0 = time.time()
    rede, props, patch, n_classes = _montar_rede(torch, pasta_modelo)
    r["montar_s"] = round(time.time() - t0, 2)
    lado = int(patch[0]) if patch else CANARIO_LADO
    xn0 = fantoma(np, lado, props)
    r["fantoma_sha256"] = hashlib.sha256(xn0.tobytes()).hexdigest()
    x = torch.from_numpy(xn0)
    r["forma"] = list(x.shape)

    def _cronometrar(fn, n):
        ts = []
        y = None
        for _ in range(max(1, n)):
            t = time.time()
            y = fn()
            ts.append(time.time() - t)
        ts.sort()
        return y, ts[len(ts) // 2], ts

    with torch.inference_mode():
        ref, s_ref, ts_ref = _cronometrar(lambda: rede(x), 1 if backend != "torch_cpu"
                                          else max(1, repeticoes))
    ref = ref.float().numpy()
    r["s_por_patch_ref"] = round(s_ref, 3)
    r["tempos_ref"] = [round(t, 3) for t in ts_ref]
    a_ref = np.argmax(ref[0], axis=0).astype(np.uint8)
    r["sha256_ref"] = hashlib.sha256(a_ref.tobytes()).hexdigest()
    r["contagem_ref"] = np.bincount(a_ref.ravel(), minlength=n_classes).tolist()
    t0 = time.time()
    if backend == "torch_cpu":
        y = ref
        r["s_por_patch"] = r["s_por_patch_ref"]
        r["tempos"] = r["tempos_ref"]
    elif backend in ("cuda", "xpu", "directml"):
        if backend == "directml":
            import torch_directml
            dev = torch_directml.device()
        else:
            dev = torch.device(backend)
        rede_d = rede.to(dev)
        xd = x.to(dev)
        auto = (backend == "cuda" and (precisao or "fp16") == "fp16")
        r["precisao"] = "fp16 (autocast)" if auto else "fp32"

        def _uma():
            with torch.no_grad():
                if auto:
                    with torch.autocast("cuda", enabled=True):
                        s = rede_d(xd)
                else:
                    s = rede_d(xd)
                s = s.float().cpu()
            return s
        _uma()
        r["preparar_s"] = round(time.time() - t0, 2)
        y, s, ts = _cronometrar(_uma, repeticoes)
        y = y.numpy()
        r["s_por_patch"] = round(s, 3)
        r["tempos"] = [round(t, 3) for t in ts]
    elif backend in ("openvino_cpu", "openvino_gpu"):
        import openvino as ov
        r["openvino"] = str(ov.__version__).split("-")[0]
        disp = "CPU" if backend == "openvino_cpu" else "GPU"
        prec = (precisao or "f32").lower()
        r["precisao"] = prec
        m = ov.convert_model(rede, example_input=x)
        r["converter_s"] = round(time.time() - t0, 2)
        conf = {"INFERENCE_PRECISION_HINT": prec}
        if disp == "CPU" and threads:
            conf["INFERENCE_NUM_THREADS"] = int(threads)
        t1 = time.time()
        comp = ov.Core().compile_model(m, disp, conf)
        r["compilar_s"] = round(time.time() - t1, 2)
        xn = x.numpy()

        def _uma():
            return comp(xn)[0]
        _uma()
        y, s, ts = _cronometrar(_uma, repeticoes)
        y = np.asarray(y, dtype=np.float32)
        r["s_por_patch"] = round(s, 3)
        r["tempos"] = [round(t, 3) for t in ts]
    else:
        raise ValueError("backend desconhecido: %s" % backend)
    r["nao_finito"] = bool(not np.isfinite(y).all())
    a = np.argmax(y[0], axis=0).astype(np.uint8)
    r["sha256"] = hashlib.sha256(a.tobytes()).hexdigest()
    r["contagem"] = np.bincount(a.ravel(), minlength=n_classes).tolist()
    r["concordancia"] = float((a == a_ref).mean())
    r["voxels_diferentes"] = int((a != a_ref).sum())
    dif = np.abs(y.astype(np.float64) - ref.astype(np.float64))
    r["max_dif_logit"] = float(np.nanmax(dif)) if dif.size else 0.0
    r["media_dif_logit"] = float(np.nanmean(dif)) if dif.size else 0.0
    r["classes_no_argmax"] = int((np.asarray(r["contagem_ref"]) > 0).sum())
    r["rss_pico_mb"] = _rss_pico_mb()
    return r


def principal(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    argv = list(sys.argv[1:] if argv is None else argv)
    antes = []
    resto = []
    i = 0
    while i < len(argv):
        if argv[i] == "--caminho-antes" and i + 1 < len(argv):
            antes.append(argv[i + 1])
            i += 2
            continue
        resto.append(argv[i])
        i += 1
    for c in reversed(antes):
        sys.path.insert(0, c)
        dlls = os.path.join(c, "Library", "bin")
        if os.path.isdir(dlls):
            try:
                os.add_dll_directory(dlls)
            except Exception:
                pass
            os.environ["PATH"] = dlls + os.pathsep + os.environ.get("PATH", "")
    if len(resto) >= 2 and resto[0] == "--sonda":
        try:
            d = _filho_sonda(resto[1])
        except Exception as e:
            d = {"falha": "%s: %s" % (type(e).__name__, str(e)[:200])}
        print(MARCA_SONDA + json.dumps(d, ensure_ascii=True))
        return 0
    if len(resto) >= 2 and resto[0] == "--canario":
        op = {"--modelo": None, "--threads": None, "--repeticoes": "1",
              "--precisao": None}
        j = 2
        while j < len(resto) - 1:
            if resto[j] in op:
                op[resto[j]] = resto[j + 1]
                j += 2
            else:
                j += 1
        try:
            d = _filho_canario(resto[1], op["--modelo"],
                               int(op["--threads"]) if op["--threads"] else None,
                               int(op["--repeticoes"] or 1), op["--precisao"])
        except Exception as e:
            import traceback
            d = {"backend": resto[1],
                 "falha": "%s: %s" % (type(e).__name__, str(e)[:300]),
                 "traceback": traceback.format_exc()[-1500:]}
        print(MARCA_CANARIO + json.dumps(d, ensure_ascii=True))
        return 0
    print("uso: radai_devices.py --sonda <torch|directml|openvino> | "
          "--canario <backend> --modelo <pasta> [--threads N] [--repeticoes N] "
          "[--precisao f32|f16|fp16|fp32] [--caminho-antes <pasta>]")
    return 2


if __name__ == "__main__":
    sys.exit(principal())
