# -*- coding: utf-8 -*-
import io
import json
import os
import platform
import re
import subprocess
import sys
import threading
import time
import unicodedata
from datetime import datetime

ULTIMO = {"relatorio": None}

SERIES_TIPO = (
    (u"TC de planejamento 512x512x117 a 3,75 mm (campo 500 mm)",
     (117, 512, 512), (3.75, 500.0 / 512, 500.0 / 512)),
    (u"TC de torax fino 512x512x409 a 0,80 mm (campo 400 mm)",
     (409, 512, 512), (0.80, 400.0 / 512, 400.0 / 512)),
)

DRIVER_MINIMO = {"12": 525.0}

MIN_POR_MVOXEL_CPU = 1.1

BIBLIOTECAS = (
    ("TotalSegmentator", "TotalSegmentator"),
    ("nnunetv2", "nnunetv2"),
    ("torch", "torch"),
    ("SimpleITK", "SimpleITK"),
    ("pydicom", "pydicom"),
    ("numpy", "numpy"),
)

QUEM_LIGA_O_MODELO = {
    "nv_segment_ct": u"so por pedido da serie (PERSONALIZADO)",
    "cads_open": u"so por pedido da serie (PERSONALIZADO)",
    "moose": u"so por pedido da serie (PERSONALIZADO)",
    "hnlnl": u"no AUTO quando o pescoco aparece, e no PERSONALIZADO",
    "cranio_buti": u"no AUTO quando o encefalo aparece, e no PERSONALIZADO",
}

INICIO_BLOCO = u"======== BLOCO DE DIAGNOSTICO DO ARRANQUE (inicio) ========"
FIM_BLOCO = u"======== BLOCO DE DIAGNOSTICO DO ARRANQUE (fim) ========"
FRASE_DO_BLOCO = u"cole este bloco num chat de IA para diagnostico"


_TROCAS = {u"—": u"-", u"–": u"-", u"×": u"x", u"≥": u">=",
           u"≤": u"<=", u"«": u'"', u"»": u'"', u"…": u"...",
           u"→": u"->", u"·": u"|", u"³": u"3"}


def ascii_(texto):
    s = u"%s" % (texto if texto is not None else u"")
    for a, b in _TROCAS.items():
        s = s.replace(a, b)
    s = unicodedata.normalize("NFKD", s)
    return s.encode("ascii", "ignore").decode("ascii")


def _rodar(args, timeout):
    r = {"codigo": None, "saida": u"", "erro": u"", "falha": u""}
    try:
        p = subprocess.run(
            args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=timeout,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        r["codigo"] = p.returncode
        r["saida"] = (p.stdout or b"").decode("utf-8", "replace")
        r["erro"] = (p.stderr or b"").decode("utf-8", "replace")
    except FileNotFoundError:
        r["falha"] = u"nao encontrado"
    except subprocess.TimeoutExpired:
        r["falha"] = u"nao respondeu em %d s" % timeout
    except Exception as e:
        r["falha"] = u"%s: %s" % (type(e).__name__, str(e)[:120])
    return r


def caminho_do_nvidia_smi():
    try:
        import radai_devices
        return radai_devices.achar_nvidia_smi()
    except Exception:
        return "nvidia-smi"


def _num(v):
    try:
        return float(str(v).strip().split()[0])
    except Exception:
        return None


def placas(timeout=20):
    fora = {"placas": [], "driver": u"", "falha": u""}
    smi = caminho_do_nvidia_smi()
    base = "index,name,memory.total,memory.free,memory.used,driver_version"
    for campos in (base + ",compute_cap", base):
        r = _rodar([smi, "--query-gpu=" + campos,
                    "--format=csv,noheader,nounits"], timeout)
        if r["falha"]:
            fora["falha"] = u"nvidia-smi %s" % r["falha"]
            return fora
        if r["codigo"] == 0:
            break
    else:
        texto = (r["saida"] or r["erro"]).strip().splitlines()
        fora["falha"] = u"nvidia-smi saiu com codigo %s%s" % (
            r["codigo"], (u": %s" % texto[0][:140]) if texto else u"")
        return fora
    n_campos = len(campos.split(","))
    atras = n_campos - 2
    for linha in r["saida"].strip().splitlines():
        c = [x.strip() for x in linha.split(",")]
        if len(c) < n_campos:
            continue
        nome = u", ".join(c[1:len(c) - atras])
        resto = c[len(c) - atras:]
        fora["placas"].append({
            "indice": int(_num(c[0]) or 0), "nome": nome,
            "total_mb": _num(resto[0]), "livre_mb": _num(resto[1]),
            "usada_mb": _num(resto[2]), "driver": resto[3],
            "cap": (resto[4].strip() if len(resto) > 4
                    and re.match(r"^\d+\.\d+$", resto[4].strip()) else u"")})
        fora["driver"] = resto[3]
    if not fora["placas"]:
        fora["falha"] = u"nvidia-smi respondeu e nao listou placa"
    return fora


_TIPOS = ("C", "G", "C+G")


def _processos_da_tabela(texto):
    fora = []
    dentro = False
    for linha in (texto or u"").splitlines():
        if "Processes" in linha:
            dentro = True
            continue
        if not dentro or not linha.strip().startswith("|"):
            continue
        tok = linha.strip().strip("|").split()
        if len(tok) < 5 or not tok[0].isdigit():
            continue
        tipo_i = next((i for i, t in enumerate(tok) if t in _TIPOS), None)
        if tipo_i is None or tipo_i < 1 or not tok[tipo_i - 1].isdigit():
            continue
        nome = u" ".join(tok[tipo_i + 1:-1]) or u"?"
        mem = tok[-1]
        fora.append({"pid": int(tok[tipo_i - 1]), "tipo": tok[tipo_i],
                     "nome": re.split(r"[\\/]", nome)[-1],
                     "mem_mb": _num(mem.replace("MiB", ""))
                     if "N/A" not in mem.upper() else None})
    return fora


def processos_na_placa(timeout=20):
    fora = {"processos": [], "falha": u""}
    smi = caminho_do_nvidia_smi()
    r = _rodar([smi], timeout)
    if r["falha"]:
        fora["falha"] = u"nvidia-smi %s" % r["falha"]
        return fora
    vistos = {}
    for p in _processos_da_tabela(r["saida"]):
        vistos[p["pid"]] = p
    r2 = _rodar([smi, "--query-compute-apps=pid,process_name,used_memory",
                 "--format=csv,noheader"], timeout)
    if not r2["falha"] and r2["codigo"] == 0:
        for linha in r2["saida"].strip().splitlines():
            c = [x.strip() for x in linha.split(",")]
            if len(c) < 3 or not c[0].isdigit():
                continue
            pid = int(c[0])
            mem = _num(c[2].replace("MiB", "")) if "N/A" not in c[2].upper() else None
            p = vistos.setdefault(pid, {"pid": pid, "tipo": "C",
                                        "nome": re.split(r"[\\/]", c[1])[-1],
                                        "mem_mb": None})
            if p.get("mem_mb") is None:
                p["mem_mb"] = mem
    fora["processos"] = sorted(vistos.values(), key=lambda p: p["pid"])
    if r["codigo"] not in (0, None) and not fora["processos"]:
        fora["falha"] = u"nvidia-smi saiu com codigo %s" % r["codigo"]
    return fora


_SONDA_TORCH = u"""
import json
r = {"importa": False}
try:
    import torch
    r["importa"] = True
    r["versao"] = str(getattr(torch, "__version__", ""))
    r["cuda"] = str(getattr(torch.version, "cuda", None) or "")
    r["disponivel"] = bool(torch.cuda.is_available())
    r["n"] = int(torch.cuda.device_count()) if r["disponivel"] else 0
    r["placas"] = []
    for i in range(r["n"]):
        p = torch.cuda.get_device_properties(i)
        r["placas"].append({"nome": p.name, "cap": "%d.%d" % (p.major, p.minor),
                            "total_mb": int(p.total_memory // 1048576)})
    try:
        r["arch"] = list(torch.cuda.get_arch_list())
    except Exception as e:
        r["arch_erro"] = type(e).__name__
    # GUARDA: a XPU vai na mesma sonda; radai_devices a reaproveita para nao importar o torch duas vezes no arranque.
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
                r["xpu_motivo"] = "torch %s: xpu.is_available() falso" % r["versao"]
        except Exception as e:
            r["xpu_disponivel"] = False
            r["xpu_motivo"] = "%s: %s" % (type(e).__name__, str(e)[:160])
except Exception as e:
    r["erro"] = "%s: %s" % (type(e).__name__, str(e)[:200])
print("RADAI_SONDA " + json.dumps(r))
"""


def sondar_torch(python_exe=None, timeout=120):
    r = _rodar([python_exe or sys.executable, "-c", _SONDA_TORCH], timeout)
    if r["falha"]:
        return {"importa": False, "falha": u"a sonda %s" % r["falha"]}
    for linha in r["saida"].splitlines():
        if linha.startswith("RADAI_SONDA "):
            try:
                return json.loads(linha[len("RADAI_SONDA "):])
            except Exception as e:
                return {"importa": False,
                        "falha": u"resposta ilegivel (%s)" % type(e).__name__}
    ultima = (r["erro"].strip().splitlines() or [u""])[-1]
    return {"importa": False,
            "falha": u"a sonda saiu com codigo %s sem responder%s"
                     % (r["codigo"], (u": " + ultima[:160]) if ultima else u"")}


REPERGUNTAR_FALHA_S = 600
_LOCK_SONDA = threading.Lock()


def _guardar_torch(r):
    ULTIMO["torch"] = dict(r, quando=datetime.now().strftime("%H:%M"),
                           ts=time.time())
    return ULTIMO["torch"]


def torch_da_estacao(python_exe=None, timeout=60):
    with _LOCK_SONDA:
        tr = ULTIMO.get("torch") or {}
        if tr and not tr.get("falha"):
            return tr
        if tr and time.time() - float(tr.get("ts") or 0) < REPERGUNTAR_FALHA_S:
            return tr
        return _guardar_torch(sondar_torch(python_exe, timeout=timeout))


def versoes_instaladas():
    fora = {}
    try:
        from importlib import metadata
    except Exception as e:
        return {"_falha": u"importlib.metadata indisponivel (%s)" % type(e).__name__}
    for nome, dist in BIBLIOTECAS:
        try:
            fora[nome] = metadata.version(dist)
        except metadata.PackageNotFoundError:
            fora[nome] = None
        except Exception as e:
            fora[nome] = u"? (nao consegui ler: %s)" % type(e).__name__
    fora["torch_cuda_build"] = u""
    try:
        import importlib.util
        esp = importlib.util.find_spec("torch")
        if esp is not None and esp.submodule_search_locations:
            for d in esp.submodule_search_locations:
                p = os.path.join(d, "version.py")
                if os.path.isfile(p):
                    t = io.open(p, encoding="utf-8", errors="replace").read()
                    m = re.search(r"^cuda\s*(?::\s*\S+)?\s*=\s*['\"]([^'\"]+)['\"]",
                                  t, re.M)
                    fora["torch_cuda_build"] = m.group(1) if m else u"cpu"
                    break
    except Exception as e:
        fora["torch_cuda_build"] = u"? (%s)" % type(e).__name__
    return fora


def driver_contra_cuda(driver, cuda):
    if not driver:
        return None, u"nao se aplica (nenhuma placa NVIDIA listada)"
    if not cuda or cuda in ("cpu", "-"):
        return None, (u"o torch deste Python e de CPU (sem cuda): o driver %s "
                      u"nao entra na conta" % driver)
    maior = str(cuda).split(".")[0]
    piso = DRIVER_MINIMO.get(maior)
    d = _num(driver)
    if piso is None or d is None:
        return None, (u"driver %s, cuda %s do torch: sem piso declarado neste "
                      u"projeto para cuda %s.x" % (driver, cuda, maior))
    if d >= piso:
        return True, (u"driver %s >= %.0f exigido pelo cuda %s do torch: ok"
                      % (driver, piso, cuda))
    return False, (u"driver %s < %.0f exigido pelo cuda %s do torch: o torch "
                   u"NAO alcanca a placa ate o driver ser atualizado (TI)"
                   % (driver, piso, cuda))


def voxels_no_modelo(forma_zyx, espacamento_zyx, mm=1.5):
    n = 1
    for f, e in zip(forma_zyx, espacamento_zyx):
        n *= max(1, int(-(-float(f) * float(e) // mm)))
    return n


def eh_protegido(nome):
    try:
        import radai_cleaner
        return bool(radai_cleaner._protegido(nome))
    except Exception:
        return True


def _p_estacao(ctx, rel):
    d = {}
    L = []
    so = u"%s %s" % (platform.system(), platform.release())
    build = u""
    try:
        build = str(sys.getwindowsversion().build)
    except Exception:
        build = platform.version()
    try:
        import winreg
        k = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                           r"SOFTWARE\Microsoft\Windows NT\CurrentVersion")
        nome = winreg.QueryValueEx(k, "ProductName")[0]
        if nome.startswith("Windows 10") and (_num(build) or 0) >= 22000:
            nome = u"Windows 11" + nome[len("Windows 10"):]
        so = nome
    except Exception as e:
        d["edicao_nao_lida"] = type(e).__name__
    d["so"] = so
    d["build"] = build
    try:
        import getpass
        d["usuario"] = getpass.getuser()
    except Exception as e:
        d["usuario"] = u"? (%s)" % type(e).__name__
    try:
        import ctypes
        d["admin"] = u"sim" if ctypes.windll.shell32.IsUserAnAdmin() else u"nao"
    except Exception as e:
        d["admin"] = u"nao deu para saber (%s)" % type(e).__name__
    d["maquina"] = ctx.get("maquina") or platform.node()
    try:
        import radai_records
        d["pseudonimo"] = radai_records.pseudonimo_da_maquina()
    except Exception as e:
        d["pseudonimo_falha"] = u"%s: %s" % (type(e).__name__, str(e)[:80])
    rel["dados"]["estacao"] = d
    L.append(u"%s (build %s) | maquina %s (no bloco: %s) | usuario %s | "
             u"administrador: %s"
             % (so, build, d["maquina"],
                d.get("pseudonimo") or u"nome omitido - %s"
                % d.get("pseudonimo_falha", u"?"),
                d["usuario"], d["admin"]))
    return L


def _p_python(ctx, rel):
    exe = ctx.get("python_exe") or sys.executable
    pasta = os.path.dirname(exe)
    nao_lida = u""
    try:
        embutido = any(n.lower().endswith("._pth") for n in os.listdir(pasta))
    except Exception as e:
        embutido = None
        nao_lida = type(e).__name__
    d = {"versao": sys.version.split()[0], "executavel": exe,
         "embeddable": embutido, "bits": 64 if sys.maxsize > 2 ** 32 else 32}
    if nao_lida:
        d["embeddable_nao_lido"] = nao_lida
    rel["dados"]["python"] = d
    if embutido is None:
        tipo = (u"nao consegui ler a pasta do Python para saber se e o "
                u"embeddable (%s)" % nao_lida)
    elif embutido:
        tipo = u"embeddable (ignora PYTHONPATH)"
    else:
        tipo = u"instalacao comum (nao e o embeddable do bundle)"
    return [u"Python %s %d bits, %s | %s" % (d["versao"], d["bits"], tipo, exe)]


def _p_versoes(ctx, rel):
    v = versoes_instaladas()
    rel["dados"]["versoes"] = v
    if v.get("_falha"):
        raise RuntimeError(v["_falha"])
    partes = [u"app %s" % (ctx.get("appver") or u"?")]
    for nome, _ in BIBLIOTECAS:
        ver = v.get(nome)
        if nome == "torch" and ver:
            ver = u"%s (cuda do build: %s)" % (ver, v.get("torch_cuda_build") or u"?")
        partes.append(u"%s %s" % (nome, ver or u"AUSENTE"))
    faltam = [n for n, _ in BIBLIOTECAS if not v.get(n)]
    if faltam:
        rel["pendencias"].append(
            u"bibliotecas ausentes neste Python: %s — o motor nao roda com elas "
            u"faltando (e o Python do bundle que as tem)" % u", ".join(faltam))
    return [u" | ".join(partes)]


def _p_cpu_ram(ctx, rel):
    d = {"nucleos": os.cpu_count() or 0,
         "processador": (platform.processor() or u"")[:60]}
    try:
        import radai_devices
        topo = radai_devices.topologia_da_cpu()
        d["fisicos"] = topo.get("fisicos")
        d["logicos"] = topo.get("logicos") or d["nucleos"]
        d["classes"] = {str(k): v for k, v in (topo.get("classes") or {}).items()}
        d["topologia"] = radai_devices.descrever_cpu(topo)
    except Exception as e:
        d["topologia"] = (u"%d nucleo(s) logico(s); os fisicos nao foram lidos "
                          u"(%s)" % (d["nucleos"], type(e).__name__))
    try:
        import radai_cleaner
        m = radai_cleaner.memoria_da_estacao() or {}
    except Exception as e:
        m = {}
        d["memoria_falha"] = type(e).__name__
    d["ram_gb"] = round((m.get("total_mb") or 0) / 1024.0, 1)
    d["ram_livre_gb"] = round((m.get("livre_mb") or 0) / 1024.0, 1)
    d["ram_pct"] = m.get("pct")
    rel["dados"]["cpu"] = d
    if not d["ram_gb"]:
        return [u"%s | %s | memoria: nao consegui medir (%s)"
                % (d["topologia"], d["processador"] or u"?",
                   d.get("memoria_falha") or u"a medida voltou zerada")]
    return [u"%s | %s | RAM %.1f GB, %.1f GB livres (%s%% em uso)"
            % (d["topologia"], d["processador"] or u"?", d["ram_gb"],
               d["ram_livre_gb"], d["ram_pct"])]


def _p_placas(ctx, rel):
    r = placas()
    rel["dados"]["placas"] = r
    if not r["placas"]:
        return [u"nenhuma placa NVIDIA listada: %s" % (r["falha"] or u"?")]
    L = []
    for p in r["placas"]:
        L.append(u"[%d] %s | %s MiB total, %s livres, %s em uso | driver %s%s"
                 % (p["indice"], p["nome"], _fmt(p["total_mb"]),
                    _fmt(p["livre_mb"]), _fmt(p["usada_mb"]), p["driver"],
                    (u" | capacidade sm %s" % p["cap"]) if p.get("cap") else u""))
    return L


def _fmt(v):
    return u"?" if v is None else u"%.0f" % v


def _p_processos(ctx, rel):
    if not (rel["dados"].get("placas") or {}).get("placas"):
        rel["dados"]["processos"] = {"processos": [], "falha": u"sem placa"}
        return [u"nao se aplica (nenhuma placa NVIDIA listada)"]
    r = processos_na_placa()
    rel["dados"]["processos"] = r
    if r["falha"] and not r["processos"]:
        return [u"nao consegui listar: %s" % r["falha"]]
    if not r["processos"]:
        return [u"nenhum processo segura a placa agora"]
    L = []
    nomes = []
    sem_mem = 0
    for p in r["processos"]:
        prot = eh_protegido(p["nome"])
        if p["mem_mb"] is None:
            sem_mem += 1
        nomes.append(u"%s (PID %d, %s, %s%s)"
                     % (p["nome"], p["pid"], p["tipo"],
                        u"N/A" if p["mem_mb"] is None else u"%.0f MiB" % p["mem_mb"],
                        u", protegido" if prot else u""))
    L.append(u"%d processo(s): %s" % (len(nomes), u"; ".join(nomes)))
    if sem_mem:
        usada = sum((pl.get("usada_mb") or 0)
                    for pl in rel["dados"]["placas"]["placas"])
        L.append(u"o uso por processo vem N/A: no Windows (modo WDDM) o driver "
                 u"NAO informa a VRAM de cada processo; a placa inteira tem "
                 u"%.0f MiB em uso" % usada)
    py = [p for p in r["processos"] if p["nome"].lower().startswith("python")]
    if py:
        rel["avisos"].append(
            u"%d python.exe segura a placa (PID %s): o vigia NAO abre CUDA no "
            u"proprio processo, entao pode ser um TotalSegmentator orfao de "
            u"serie anterior ou o \"Rodar agora\" em curso"
            % (len(py), u", ".join(str(p["pid"]) for p in py)))
    fechaveis = sorted(set(p["nome"] for p in r["processos"]
                           if not eh_protegido(p["nome"])
                           and not p["nome"].lower().startswith("python")))
    if fechaveis:
        L.append(u"VRAM so volta FECHANDO o processo (compactar memoria libera "
                 u"RAM, nao VRAM). Fechar e decisao de quem esta na maquina: %s"
                 % u", ".join(fechaveis))
    return L


NOME_DA_SONDA_GUARDADA = "sonda_torch.json"


def arquivo_da_sonda():
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(base, "RADIOTERAPIA_AI", NOME_DA_SONDA_GUARDADA)


def chave_da_sonda(rel, python_exe=None):
    pl = rel["dados"].get("placas") or {}
    ver = rel["dados"].get("versoes") or {}
    return {"driver": str(pl.get("driver") or u""),
            "placas": [str(p.get("nome") or u"") for p in pl.get("placas") or []],
            "torch": str(ver.get("torch") or u""),
            "cuda_build": str(ver.get("torch_cuda_build") or u""),
            "python": os.path.normcase(os.path.abspath(
                python_exe or sys.executable))}


def ler_sonda_guardada(chave, arquivo=None):
    try:
        with io.open(arquivo or arquivo_da_sonda(), encoding="utf-8") as f:
            d = json.load(f)
    except Exception:
        return None
    r = d.get("resultado") if isinstance(d, dict) else None
    # GUARDA: sem driver não há o que comparar (nvidia-smi não respondeu);
    # sem `importa` a resposta guardada não é de uma sonda que respondeu.
    if (not isinstance(r, dict) or d.get("chave") != chave
            or not chave.get("driver") or r.get("falha")
            or "importa" not in r):
        return None
    return d


def guardar_sonda(chave, r, arquivo=None):
    if not isinstance(r, dict) or r.get("falha") or not chave.get("driver"):
        return False
    caminho = arquivo or arquivo_da_sonda()
    try:
        os.makedirs(os.path.dirname(caminho), exist_ok=True)
        tmp = caminho + ".tmp"
        with io.open(tmp, "w", encoding="utf-8") as f:
            json.dump({"chave": chave, "resultado": r,
                       "quando": datetime.now().strftime("%d/%m/%Y %H:%M")},
                      f, ensure_ascii=False)
        os.replace(tmp, caminho)
        return True
    except Exception:
        return False


_CAMPOS_DA_SONDA = ("importa", "versao", "cuda", "disponivel", "n", "placas")


def _refazer_sonda(ctx, chave, guardada):
    log = ctx.get("log") or (lambda m: None)
    try:
        with _LOCK_SONDA:
            r = sondar_torch(ctx.get("python_exe"))
            if r.get("falha"):
                log(u"torch: a sonda refeita em segundo plano nao respondeu "
                    u"(%s); vale a resposta guardada" % r["falha"])
                return
            _guardar_torch(r)
        guardar_sonda(chave, r, ctx.get("arquivo_da_sonda"))
        antes = dict((k, guardada.get(k)) for k in _CAMPOS_DA_SONDA)
        agora = dict((k, r.get(k)) for k in _CAMPOS_DA_SONDA)
        if antes != agora:
            log(u"torch: a sonda refeita em segundo plano mudou (CUDA "
                u"disponivel: %s, %s placa(s)); a proxima serie decide por ela"
                % (u"sim" if r.get("disponivel") else u"nao", r.get("n") or 0))
    except Exception as e:
        log(u"torch: a sonda em segundo plano falhou (%s)" % type(e).__name__)


def _p_torch(ctx, rel):
    chave = chave_da_sonda(rel, ctx.get("python_exe"))
    guardada = ler_sonda_guardada(chave, ctx.get("arquivo_da_sonda"))
    cabeca = []
    if guardada:
        r = dict(guardada["resultado"], do_cache=True)
        with _LOCK_SONDA:
            _guardar_torch(r)
        cabeca.append(u"resposta guardada em %s, com o mesmo driver, as "
                      u"mesmas placas e o mesmo torch; refeita em segundo plano"
                      % (guardada.get("quando") or u"?"))
        t = threading.Thread(target=_refazer_sonda,
                             args=(ctx, chave, guardada["resultado"]),
                             name="radai-sonda-torch", daemon=True)
        t.start()
        ULTIMO["sonda_em_segundo_plano"] = t
    else:
        with _LOCK_SONDA:
            r = sondar_torch(ctx.get("python_exe"))
            _guardar_torch(r)
        guardar_sonda(chave, r, ctx.get("arquivo_da_sonda"))
    rel["dados"]["torch"] = r
    if r.get("falha"):
        rel["pendencias"].append(u"o torch deste Python nao respondeu: %s"
                                 % r["falha"])
        return [u"nao consegui perguntar ao torch: %s" % r["falha"]]
    if not r.get("importa"):
        rel["pendencias"].append(u"o torch nao importa neste Python: %s"
                                 % (r.get("erro") or u"?"))
        return [u"o torch NAO importa neste Python: %s" % (r.get("erro") or u"?")]
    L = [u"torch %s (cuda %s) | CUDA disponivel: %s | alcanca %d placa(s)"
         % (r.get("versao"), r.get("cuda") or u"-",
            u"sim" if r.get("disponivel") else u"nao", r.get("n") or 0)]
    arch = r.get("arch") or []
    for i, p in enumerate(r.get("placas") or []):
        sm = u"sm_%s" % str(p.get("cap", "")).replace(".", "")
        L.append(u"[%d] %s | sm %s | %s no build do torch"
                 % (i, p.get("nome"), p.get("cap"),
                    (u"%s presente" % sm) if sm in arch
                    else (u"%s AUSENTE" % sm if arch else u"lista de arquiteturas nao lida")))
        if arch and sm not in arch:
            rel["pendencias"].append(
                u"a placa %s (%s) nao esta no build do torch: ele nao roda nela"
                % (p.get("nome"), sm))
    return cabeca + L


def _p_driver(ctx, rel):
    pl = rel["dados"].get("placas") or {}
    tr = rel["dados"].get("torch") or {}
    ver = rel["dados"].get("versoes") or {}
    cuda = tr.get("cuda") or ver.get("torch_cuda_build") or u""
    ok, frase = driver_contra_cuda(pl.get("driver"), cuda)
    rel["dados"]["driver"] = {"ok": ok, "frase": frase}
    if ok is False:
        rel["pendencias"].append(frase)
    return [frase]


def _p_computacao(ctx, rel):
    import radai_devices as RD
    inicio_do_passo, limite_do_passo = ctx.get("_prazo_do_passo") or (
        time.time(), _limite_de(_p_computacao))
    device = str(ctx.get("device") or u"").strip().lower() or None
    prontas = {}
    tr = rel["dados"].get("torch")
    if tr:
        prontas["torch"] = RD.sonda_torch_do_arranque(tr)
    inv = RD.inventario(python_exe=ctx.get("python_exe"),
                        sondas_prontas=prontas,
                        sondas_timeout=RD.PRAZO_SONDA_NO_ARRANQUE_S)
    RD.ULTIMO["diagnostico"] = inv
    RD.ULTIMO["device"] = device
    rel["dados"]["computacao"] = {
        "placas": [{"nome": p.get("nome"), "vendor": p.get("vendor"),
                    "memoria_mb": p.get("memoria_mb"),
                    "integrada": p.get("integrada"),
                    "driver": p.get("driver"), "o_ts_usa": p.get("o_ts_usa"),
                    "frase": p.get("frase")} for p in inv.get("placas") or []],
        "placas_falha": inv.get("placas_falha") or u"",
        "cpu": RD.descrever_cpu(inv.get("cpu") or {},
                                (inv.get("cpu") or {}).get("nome") or u""),
        "backends": {b: {"disponivel": bool(x.get("disponivel")),
                         "detalhe": x.get("versao") if x.get("disponivel")
                         else x.get("motivo"),
                         "politica": RD.POLITICA_DE_ADOCAO.get(b)}
                     for b, x in (inv.get("backends") or {}).items()},
        "candidatos": RD.candidatos_ao_canario(inv)}
    L = RD.linhas(inv)
    rg = RD.regra_de_threads(inv.get("cpu") or {})
    manual = (os.environ.get("RADAI_THREADS") or u"").strip()
    L.append(u"threads do nnU-Net em CPU (envelope): %s - %s%s" % (
        rg["n"] or u"%d (o da biblioteca)" % RD.THREADS_DA_BIBLIOTECA,
        rg["motivo"],
        (u" | RADAI_THREADS=%s no ambiente manda" % manual) if manual else u""))
    rel["dados"]["computacao"]["threads_cpu"] = (
        u"RADAI_THREADS=%s" % manual if manual
        else (u"%d threads" % rg["n"]) if rg["n"]
        else u"%d threads (biblioteca)" % RD.THREADS_DA_BIBLIOTECA)
    nao_nvidia = [p for p in inv.get("placas") or [] if not p.get("o_ts_usa")
                  and p.get("vendor") not in ("microsoft", "vmware", "virtual",
                                              "parallels", "virtualbox")]
    if nao_nvidia and not [p for p in inv.get("placas") or []
                           if p.get("vendor") == "nvidia"]:
        rel["avisos"].append(
            u"esta estacao tem %s, que o TotalSegmentator do pacote NAO usa: "
            u"a inferencia roda na CPU" % u", ".join(p["nome"] for p in nao_nvidia))
    if ctx.get("dry_run"):
        L.append(u"canario: nao roda em simulacao (DRY_RUN=1: nada vai ser "
                 u"segmentado)")
        rel["dados"]["computacao"]["canario"] = u"simulacao"
        return L
    candidatos = RD.candidatos_ao_canario(inv, device)
    de_placa = [b for b in RD.candidatos_ao_canario(inv)
                if b not in candidatos]
    if de_placa:
        L.append(u"canario: DEVICE=cpu no radai_watcher.config - a placa nao "
                 u"e conferida (%s fica(m) fora; nenhum contexto e aberto "
                 u"nela no arranque)" % u", ".join(de_placa))
    if not candidatos:
        RD.ULTIMO["canarios"] = {}
        L.append(u"canario: nenhum backend alem do PyTorch CPU a conferir "
                 u"(o PyTorch CPU e o chao, e nao tem com quem ser comparado)")
        rel["dados"]["computacao"]["canario"] = u"sem candidato"
        return L
    try:
        import radai_tasks
        pesos = radai_tasks.pasta_pesos()
    except Exception as e:
        L.append(u"canario: nao sei a pasta dos pesos (%s) - nao roda"
                 % type(e).__name__)
        rel["dados"]["computacao"]["canario"] = u"sem pasta de pesos"
        return L
    log = ctx.get("log") or (lambda m: None)
    cache = None
    if ctx.get("pasta_trabalho"):
        cache = os.path.join(ctx["pasta_trabalho"], "canario_backends.json")
    t = RD.canarios_em_segundo_plano(
        inv, python_exe=ctx.get("python_exe"), pasta_pesos=pesos,
        log=lambda m: log(ascii_(m)), cache=cache, device=device)
    pedida = float(ctx.get("espera_canario_s", RD.ESPERA_DO_ARRANQUE_S))
    espera = pedida
    if limite_do_passo:
        sobra = (float(limite_do_passo) - (time.time() - inicio_do_passo)
                 - FOLGA_DO_PASSO_S)
        espera = max(0.0, min(pedida, sobra))
    if t is not None:
        t.join(espera)
    terminou = t is not None and not t.is_alive()
    if t is not None and terminou:
        can = RD.ULTIMO.get("canarios") or {}
        L.extend(u"canario %s: %s" % (b, RD._veredito(r))
                 for b, r in sorted(can.items()))
        L.extend(RD.linhas_da_conferencia(inv, can, device=device))
        vereditos = u"; ".join(
            u"%s %s" % (b, u"APROVADO" if r.get("aprovado") else
                        (u"adiado" if r.get("adiado") else
                         (u"falhou" if r.get("falha") else u"REPROVADO")))
            for b, r in sorted(can.items()))
        rel["dados"]["computacao"]["canario"] = u" | ".join(
            p for p in (vereditos, RD.resumo_da_conferencia(
                inv, can, device=device)) if p)
        return L
    if t is None:
        L.append(u"canario: ja estava rodando (disparado antes deste passo), "
                 u"e este passo nao esperou por ele (%s); o resultado sai neste "
                 u"log quando terminar" % u", ".join(candidatos))
    else:
        L.append(u"canario: disparado (%s) - passou do prazo de %.0f s %s e "
                 u"segue em segundo plano; o resultado sai neste log quando "
                 u"terminar"
                 % (u", ".join(candidatos), espera,
                    u"do arranque" if espera >= pedida else
                    (u"(encurtado de %.0f s para caber no prazo de %.0f s do "
                     u"passo: o inventario levou %.0f s)"
                     % (pedida, float(limite_do_passo),
                        time.time() - inicio_do_passo - espera))))
    L.extend(RD.linhas_da_conferencia(inv, {}, rodando=True, device=device))
    rel["dados"]["computacao"]["canario"] = u"em segundo plano: %s | %s" % (
        u", ".join(candidatos),
        RD.resumo_da_conferencia(inv, {}, rodando=True, device=device))
    return L


FOLGA_DO_PASSO_S = 15


def _limite_de(fn):
    for _nome, f, limite in PASSOS:
        if f is fn:
            return float(limite)
    return None


def _base_no_disco(modalidade):
    try:
        import radai_tasks
        return radai_tasks.base_no_disco(modalidade)
    except Exception as e:
        return u"? (%s)" % type(e).__name__


_SEM_300_QUEM_MUDA = (u"a base e as tasks de TC sem localizador proprio rodam "
                      u"a TC INTEIRA")
_SEM_300_QUEM_NAO = u"as que recortam no proprio localizador nao mudam"


def _linha_do_recorte_no_corpo(ctx, rel, RT, pasta):
    pedido = ctx.get("recorte_no_corpo")
    origem = u"RECORTE_NO_CORPO do config"
    if pedido is None:
        try:
            pedido = bool(ctx["carregar_engine"]().RECORTE_NO_CORPO_PADRAO)
            origem = (u"padrao do motor: o vigia desta versao nao entrega a "
                      u"chave ao arranque")
        except Exception as e:
            origem = (u"nao sei: o vigia nao entregou a chave e o motor nao "
                      u"respondeu (%s)" % type(e).__name__)
    else:
        pedido = bool(pedido)
    presente, frase = RT.pesos_do_recorte_no_corpo(pasta)
    rel["dados"]["recorte_no_corpo"] = {"pedido": pedido, "origem": origem,
                                        "dataset300": presente,
                                        "frase": frase}
    estado = {True: u"ligado", False: u"desligado"}.get(pedido, u"?")
    linha = u"recorte no corpo (--body_seg): %s (%s); Dataset300 %s" % (
        estado, origem, u"presente" if presente else u"AUSENTE (%s)" % frase)
    if not presente and pedido is not False:
        alerta = (u"ALERTA: o recorte no corpo esta %s e o Dataset300 esta "
                  u"AUSENTE (%s) - %s, sem o recorte: mais lentas (medido "
                  u"numa TC de planejamento em CPU: 40,8 contra 19,1 min); "
                  u"%s. A serie sai, com o contorno da TC inteira (o de "
                  u"antes de 23/09; a diferenca medida para o recortado fica "
                  u"na borda). O preparador o baixa junto com a base; a "
                  u"pasta e %s em %s"
                  % (estado, frase, _SEM_300_QUEM_MUDA, _SEM_300_QUEM_NAO,
                     RT.DATASET_DO_BODY_PASTA, pasta))
        rel["avisos"].append(alerta)
        linha += u" | " + alerta
    return linha


def _p_pesos(ctx, rel):
    import radai_tasks as RT
    pasta = RT.pasta_pesos()
    no_disco = set(RT.baixados())
    d = {"pasta": pasta, "n": len(no_disco), "grupos": []}
    L = [u"pasta dos pesos: %s | %d dataset(s) no disco" % (pasta, len(no_disco))]
    ordem = list(RT.BASES_CT) + list(RT.BASES_MR)
    for t in ordem + [t for t in (ctx.get("tasks") or []) if t not in ordem]:
        precisa = RT.datasets_necessarios(t, recorte_no_corpo=False)
        if not precisa:
            continue
        faltam = [n for n in precisa if n not in no_disco]
        rotulo = t
        if t in RT.RESERVAS:
            rotulo = u"%s (reserva)" % t
        d["grupos"].append({"task": t, "precisa": precisa, "faltam": faltam})
        L.append(u"%s: %s %s" % (rotulo, u" ".join(str(n) for n in precisa),
                                 u"presentes" if not faltam
                                 else u"| AUSENTES: %s" % u" ".join(str(n) for n in faltam)))
        if faltam and t in (ctx.get("tasks") or []) and t not in RT.RESERVAS:
            eleita = RT.base_no_disco(RT.modalidade_da_base(t) or "CT") \
                if RT.modalidade_da_base(t) else t
            if eleita == t:
                rel["pendencias"].append(
                    u"a task %s do config nao tem peso completo no disco "
                    u"(faltam %s): a serie vai falhar nela, ou tentar baixar "
                    u"da internet" % (t, u", ".join(str(n) for n in faltam)))
    L.append(u"837 (6 mm; vem junto no download da total_v3, o padrao nao o "
             u"usa): %s" % (u"presente" if 837 in no_disco else u"ausente"))
    L.append(_linha_do_recorte_no_corpo(ctx, rel, RT, pasta))
    mods = set(m.upper() for m in (ctx.get("modalidades") or ()))
    if "MR" in mods:
        falta_mr = [n for g in d["grupos"] if g["task"] in RT.BASES_MR
                    for n in g["faltam"]]
        if falta_mr:
            rel["pendencias"].append(
                u"MR esta no MODALITIES e a base de RM nao tem peso (faltam %s)"
                % u", ".join(str(n) for n in falta_mr))
    rel["dados"]["pesos"] = d
    return L


def _p_estatistica(ctx, rel):
    try:
        eng = ctx["carregar_engine"]()
    except Exception as e:
        rel["dados"]["estatistica"] = {"falha": type(e).__name__}
        return [u"nao sei: o motor nao carregou (%s: %s)"
                % (type(e).__name__, str(e)[:100])]
    r = dict(eng.estatistica_do_ts() or {})
    bloqueia, porque = eng.envelope_bloqueia_estatistica()
    d = {"arquivo": r.get("arquivo"), "valor": r.get("valor"),
         "existia": bool(r.get("existia")), "erro": r.get("erro") or u"",
         "envelope": bool(bloqueia), "envelope_porque": porque or u""}
    rel["dados"]["estatistica"] = d
    cinto = (u"o envelope (radai_ts_runner) tambem bloqueia o envio, mesmo "
             u"se alguem religar" if bloqueia
             else u"o envelope NAO bloqueia (%s)" % (porque or u"?"))
    if d["erro"]:
        rel["avisos"].append(u"estatistica de uso do TotalSegmentator: %s"
                             % d["erro"])
        return [u"%s | %s" % (d["erro"], cinto)]
    if d["valor"] is False:
        return [u"estatistica de uso do TotalSegmentator: desligada (nenhuma "
                u"chamada de rede) | send_usage_stats=false em %s | %s"
                % (d["arquivo"], cinto)]
    if not d["existia"]:
        linha = (u"o arquivo de configuracao do TotalSegmentator ainda nao "
                 u"existe (%s): o motor o cria com send_usage_stats=false "
                 u"antes da primeira task" % d["arquivo"])
    else:
        linha = (u"o arquivo diz send_usage_stats=%s (%s): o motor grava "
                 u"false antes da proxima task"
                 % (u"true" if d["valor"] else u"ausente", d["arquivo"]))
    if bloqueia:
        return [u"estatistica de uso do TotalSegmentator: o envio esta "
                u"BLOQUEADO pelo envelope (radai_ts_runner) | " + linha]
    rel["avisos"].append(
        u"estatistica de uso do TotalSegmentator LIGADA nesta estacao: %s, e "
        u"%s - sem os dois, cada task faz um POST para "
        u"stats.totalsegmentator.com" % (linha, cinto))
    return [u"estatistica de uso do TotalSegmentator: LIGADA | %s | %s"
            % (linha, cinto)]


def _p_procedencia(ctx, rel):
    L = []
    d = {}
    cursor = ctx.get("suavizar_mm")
    if cursor is None:
        L.append(u"nao sei o cursor em uso: o vigia desta versao nao o entrega "
                 u"ao arranque (o espelho usa o de fabrica e diz)")
    eng = None
    try:
        eng = ctx["carregar_engine"]()
    except Exception as e:
        L.append(u"o motor nao carregou (%s: %s) - o espelho tenta importar o "
                 u"dele" % (type(e).__name__, str(e)[:100]))
    try:
        import radai_provenance
        linhas = radai_provenance.linhas_para_arranque(
            cursor, fabrica=ctx.get("suavizar_fabrica"), engine=eng)
    except Exception as e:
        linhas = [u"procedencia: nao consegui montar (%s: %s)"
                  % (type(e).__name__, str(e)[:120])]
    L.extend(linhas)
    d["procedencia"] = [ascii_(x) for x in linhas]
    for x in linhas:
        if x.startswith(u"procedencia: AVISO") or x.startswith(
                u"procedencia: ATENCAO"):
            rel["avisos"].append(x)
    try:
        import radai_panel
        reg = radai_panel.linhas_do_registro_para_arranque()
    except Exception as e:
        reg = [u"registro de casos: nao consegui ler (%s: %s)"
               % (type(e).__name__, str(e)[:120])]
    L.extend(reg)
    d["registro"] = [ascii_(x) for x in reg]
    rel["dados"]["procedencia"] = d
    return L


def _p_modelos(ctx, rel):
    import radai_models as RM
    L = []
    d = []
    for ident in RM.MODELOS:
        if ident == "totalsegmentator":
            continue
        e = RM.estado_do_modelo(ident)
        nome = re.split(u"[—(]", e.get("nome") or ident)[0].strip() or ident
        quem = QUEM_LIGA_O_MODELO.get(ident, u"")
        d.append({"id": ident, "nome": nome, "instalado": bool(e.get("instalado")),
                  "quem_liga": quem,
                  "uso": e.get("uso_permitido")})
        L.append(u"%s: %s | %s" % (
            nome, u"instalado" if e.get("instalado") else u"NAO instalado",
            (u"roda " + quem) if quem else u"sem chave no config"))
    rel["dados"]["modelos"] = d
    return L


def _p_decisao(ctx, rel):
    L = []
    pedido = str(ctx.get("device") or "auto").strip().lower()
    tr = rel["dados"].get("torch") or {}
    alcanca = bool(tr.get("disponivel"))
    base_ct = _base_no_disco("CT")
    decisoes = []
    if pedido == "cpu":
        L.append(u"cpu: pedido no config (DEVICE=cpu) — a placa nao e consultada")
        decisoes = [{"serie": s[0], "modo": "cpu",
                     "motivo": u"DEVICE=cpu no config"} for s in SERIES_TIPO]
    elif "torch" not in rel["dados"]:
        L.append(u"nao sei: o passo do torch nao terminou, entao nao ha como "
                 u"dizer se ele alcanca a placa (a serie decide na hora)")
        decisoes = [{"serie": s[0], "modo": u"?",
                     "motivo": u"o torch nao foi medido no arranque"}
                    for s in SERIES_TIPO]
    elif not alcanca:
        porque = tr.get("falha") or tr.get("erro") or (
            u"o torch nao ve CUDA" if tr.get("importa") else u"o torch nao importa")
        L.append(u"cpu: o torch deste Python nao alcanca placa (%s)" % porque)
        if pedido == "gpu":
            rel["pendencias"].append(
                u"DEVICE=gpu e o torch nao alcanca placa: a primeira serie vai "
                u"falhar ao pedir a GPU")
        decisoes = [{"serie": s[0], "modo": "cpu", "motivo": porque}
                    for s in SERIES_TIPO]
    else:
        plano = None
        motivo_sem_plano = u""
        try:
            eng = ctx["carregar_engine"]()
            plano = eng.plano_de_dispositivo
        except Exception as e:
            motivo_sem_plano = u"nao consegui o plano do motor (%s: %s)" % (
                type(e).__name__, str(e)[:100])
        if plano is None:
            L.append(u"nao sei: %s — a serie decide na hora, no motor"
                     % motivo_sem_plano)
            decisoes = [{"serie": s[0], "modo": u"?",
                         "motivo": motivo_sem_plano}
                        for s in SERIES_TIPO]
        else:
            for rotulo, forma, esp in SERIES_TIPO:
                try:
                    p = dict(plano(forma, esp, task=base_ct) or {})
                except Exception as e:
                    p = {"modo": u"?", "motivo": u"o plano levantou %s: %s"
                                                % (type(e).__name__, str(e)[:100])}
                p["serie"] = rotulo
                decisoes.append(p)
                L.append(u"%s -> %s: %s" % (rotulo, p.get("modo"), p.get("motivo")))
    _rc = rel["dados"].get("recorte_no_corpo") or {}
    _com_recorte = bool(_rc.get("pedido")) and bool(_rc.get("dataset300"))
    for dec, (rotulo, forma, esp) in zip(decisoes, SERIES_TIPO):
        vx = voxels_no_modelo(forma, esp)
        dec["mvoxels"] = round(vx / 1e6, 1)
        if dec.get("modo") == "cpu":
            dec["estimativa_min"] = round(vx / 1e6 * MIN_POR_MVOXEL_CPU)
            L.append(u"   em CPU: %.1f M voxels a 1,5 mm -> ~%d min de inferencia "
                     u"da base (regua do projeto, %.1f min/M voxels, medida numa "
                     u"CPU de 12 nucleos; outra CPU, outro numero)%s"
                     % (vx / 1e6, dec["estimativa_min"], MIN_POR_MVOXEL_CPU,
                        u" | com o recorte no corpo isto e o TETO: a regua e "
                        u"da grade inteira, e numa TC de planejamento medida "
                        u"a base caiu de 40,8 para 19,1 min"
                        if _com_recorte else u""))
    rel["dados"]["decisoes"] = decisoes
    rel["dados"]["dispositivo"] = dict(decisoes[0]) if decisoes else {}
    rel["dados"]["dispositivo"]["pedido"] = pedido
    mods = sorted(set(m.upper() for m in (ctx.get("modalidades") or ())) | {"CT"})
    bases = {}
    for m in ("CT", "MR"):
        bases[m] = _base_no_disco(m)
    rel["dados"]["bases"] = bases
    L.append(u"base anatomica por modalidade: CT -> %s | MR -> %s"
             % (bases["CT"], bases["MR"]))
    sem_regra = u""
    try:
        import radai_tasks
        fn = radai_tasks.tasks_da_serie
    except Exception as e:
        fn = None
        sem_regra = u"nao consegui carregar o radai_tasks: %s" % type(e).__name__
    tarefas = list(ctx.get("tasks") or [])
    por_mod = {}
    for m in mods:
        if fn is None:
            por_mod[m] = None
            continue
        ditas = []
        try:
            por_mod[m] = list(fn(list(tarefas), m, log=ditas.append))
        except Exception as e:
            por_mod[m] = None
            ditas.append(u"tasks_da_serie levantou %s: %s" % (type(e).__name__, str(e)[:80]))
        for x in ditas:
            L.append(u"   %s" % x)
    rel["dados"]["tasks_por_modalidade"] = por_mod
    if fn is None:
        rel["dados"]["tasks_sem_regra"] = sem_regra
        L.append(u"tasks: TASKS=%s roda em TODA serie aceita (a escolha da base "
                 u"pela modalidade da serie: %s)"
                 % (u",".join(tarefas), sem_regra))
        if "MR" in mods:
            rel["avisos"].append(
                u"MR esta no MODALITIES e o vigia desta versao roda a base de CT "
                u"na RM (o log de cada serie diz)")
    else:
        L.append(u"tasks por modalidade: %s" % u" | ".join(
            u"%s -> %s" % (m, u",".join(por_mod[m]) if por_mod[m] is not None else u"?")
            for m in mods))
    return L


def _p_disco(ctx, rel):
    import shutil
    L = []
    d = {}
    alvos = [(u"pasta de trabalho", ctx.get("pasta_trabalho")),
             (u"temporario", ctx.get("pasta_temp"))]
    try:
        import radai_tasks
        alvos.append((u"pesos", radai_tasks.pasta_pesos()))
    except Exception as e:
        L.append(u"pesos: nao sei a pasta (%s)" % type(e).__name__)
    precisa = None
    try:
        import radai_cleaner
        precisa = radai_cleaner.disco_necessario_gb(1, len(ctx.get("tasks") or []) or 1)
    except Exception as e:
        precisa = None
        L.append(u"nao sei quanto disco uma serie pede (%s): o aviso de disco "
                 u"curto fica desligado neste arranque" % type(e).__name__)
    for rotulo, p in alvos:
        if not p:
            continue
        try:
            alvo = p if os.path.exists(p) else os.path.dirname(p)
            u = shutil.disk_usage(alvo)
            livre = u.free / 1e9
            d[rotulo] = round(livre, 1)
            L.append(u"%s: %.1f GB livres de %.1f GB (unidade %s)"
                     % (rotulo, livre, u.total / 1e9,
                        os.path.splitdrive(os.path.abspath(alvo))[0] or u"?"))
            if precisa and rotulo != u"pesos" and livre < precisa:
                rel["avisos"].append(
                    u"%s (unidade %s) com %.1f GB livres: uma serie pede "
                    u"~%.0f GB" % (rotulo, os.path.splitdrive(
                        os.path.abspath(alvo))[0] or u"?", livre, precisa))
        except Exception as e:
            L.append(u"%s: nao consegui medir (%s)" % (rotulo, type(e).__name__))
    rel["dados"]["disco"] = d
    return L


def _p_root(ctx, rel):
    root = (ctx.get("root") or u"").strip()
    d = {"vazio": not root}
    if not root:
        rel["dados"]["root"] = d
        return [u"vazio: a vigilia noturna nao varre nada (o \"Rodar agora\" "
                u"funciona normalmente)"]
    d["rede"] = root.startswith("\\\\") or root.startswith("//")
    d["acessivel"] = os.path.isdir(root)
    n = 0
    if d["acessivel"]:
        with os.scandir(root) as it:
            for e in it:
                try:
                    if e.is_dir():
                        n += 1
                except OSError:
                    continue
                if n >= 100000:
                    break
    d["pastas"] = n
    rel["dados"]["root"] = d
    if not d["acessivel"]:
        rel["pendencias"].append(u"o ROOT esta preenchido e NAO esta acessivel "
                                 u"(pasta de rede fora do ar, ou sem permissao)")
    return [u"preenchido | %s | %s | %d pasta(s) no primeiro nivel (nomes nao "
            u"sao lidos: sao de paciente)"
            % (u"pasta de rede" if d["rede"] else u"pasta local",
               u"acessivel" if d["acessivel"] else u"NAO acessivel", n)]


def _p_ambiente(ctx, rel):
    ok, detalhe = ctx["conferir_ambiente"]()
    rel["dados"]["ambiente"] = {"ok": bool(ok), "detalhe": detalhe or u""}
    if not ok:
        rel["pendencias"].append(u"ambiente: %s" % (detalhe or u"?"))
        return [u"PARADO: %s" % (detalhe or u"?")]
    return [detalhe or u"o TotalSegmentator importa neste Python"]


PASSOS = (
    (u"estacao", _p_estacao, 15),
    (u"python", _p_python, 10),
    (u"versoes das bibliotecas", _p_versoes, 30),
    (u"cpu e memoria", _p_cpu_ram, 15),
    (u"placas (nvidia-smi)", _p_placas, 45),
    (u"quem segura a placa", _p_processos, 45),
    (u"o torch alcanca a placa? (subprocesso curto)", _p_torch, 150),
    (u"driver contra o cuda do torch", _p_driver, 10),
    (u"todas as placas, a cpu e os backends (subprocessos)", _p_computacao, 300),
    (u"pesos no disco", _p_pesos, 45),
    (u"modelos de comparacao", _p_modelos, 30),
    (u"decisao de dispositivo", _p_decisao, 120),
    (u"estatistica de uso do TotalSegmentator", _p_estatistica, 60),
    (u"suavizacao, procedencia e registro de casos", _p_procedencia, 60),
    (u"disco", _p_disco, 20),
    (u"ROOT", _p_root, 30),
    (u"pendencias de ambiente", _p_ambiente, 330),
)


def _com_limite(fn, args, limite):
    caixa = {}

    def _alvo():
        try:
            caixa["valor"] = fn(*args)
        except Exception as e:
            caixa["erro"] = u"%s: %s" % (type(e).__name__, str(e)[:160])

    t = threading.Thread(target=_alvo, daemon=True)
    t.start()
    t.join(limite)
    if t.is_alive():
        return False, None, None
    return True, caixa.get("valor"), caixa.get("erro")


def executar(ctx):
    log = ctx.get("log") or (lambda m: None)
    bater = ctx.get("bater") or (lambda: None)
    passos = ctx.get("passos") or PASSOS
    limites = ctx.get("limites") or {}
    t0 = time.time()
    rel = {"inicio": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
           "passos": [], "avisos": list(ctx.get("avisos_previos") or []),
           "pendencias": [], "dados": {}, "appver": ctx.get("appver") or u"",
           "maquina": ctx.get("maquina") or u"", "dry_run": bool(ctx.get("dry_run")),
           "device": ctx.get("device") or u"auto",
           "tasks": list(ctx.get("tasks") or []),
           "modalidades": sorted(ctx.get("modalidades") or [])}
    n = len(passos)

    def _diz(m):
        try:
            log(ascii_(m))
        except Exception:
            rel.setdefault("log_falhou", True)

    _diz(u"===== ARRANQUE %s: %d passos, com o tempo de cada um. O painel ja "
         u"responde enquanto isto roda; a fila so comeca no fim =====" % (
             rel["appver"] or u"", n))
    for k, (nome, fn, limite) in enumerate(passos, start=1):
        limite = float(limites.get(nome, limite))
        ctx_estado = ctx.get("ao_passo")
        if callable(ctx_estado):
            try:
                ctx_estado(k, n, nome)
            except Exception:
                rel.setdefault("ao_passo_falhou", nome)
        _diz(u"arranque [%d/%d] %s..." % (k, n, nome))
        ti = time.time()
        ctx["_prazo_do_passo"] = (ti, limite)
        terminou, linhas, erro = _com_limite(fn, (ctx, rel), limite)
        dt = time.time() - ti
        reg = {"nome": nome, "segundos": round(dt, 1), "ok": terminou and not erro}
        if not terminou:
            reg["falha"] = u"tempo-limite de %.0f s estourado" % limite
            _diz(u"   (%.1f s) nao consegui medir %s: tempo-limite de %.0f s "
                 u"estourado — sigo sem este dado" % (dt, nome, limite))
        elif erro:
            reg["falha"] = erro
            _diz(u"   (%.1f s) nao consegui medir %s: %s" % (dt, nome, erro))
        else:
            linhas = [l for l in (linhas or []) if l] or [u"(nada a dizer)"]
            reg["linhas"] = [ascii_(l) for l in linhas]
            _diz(u"   (%.1f s) %s" % (dt, linhas[0]))
            for l in linhas[1:]:
                _diz(u"   %s" % l)
        rel["passos"].append(reg)
        try:
            bater()
        except Exception:
            rel.setdefault("bater_falhou", True)
    rel["segundos"] = round(time.time() - t0, 1)
    try:
        rel["dados"]["rede"] = chamadas_de_rede(ctx)
    except Exception as e:
        rel["dados"]["rede"] = [u"nao consegui montar a lista (%s: %s)"
                                % (type(e).__name__, str(e)[:100])]
    for l in bloco(rel):
        _diz(l)
    ULTIMO["relatorio"] = rel
    return rel


def chamadas_de_rede(ctx):
    L = []
    try:
        import radai_version as _rv
        url = _rv.url_em_vigor()
        api = _rv._api_de(url) if url else u""
        agente = _rv.USER_AGENT
    except Exception as e:
        _rv, url, api, agente = None, u"", u"", u"?"
        L.append(u"consulta de versao: nao sei o destino (%s: %s)"
                 % (type(e).__name__, str(e)[:80]))
    if _rv is not None:
        if not str(url).strip():
            L.append(u"consulta de versao: DESLIGADA nesta estacao "
                     u"(RADAI_URL_VERSOES=0 no ambiente)")
        elif not api:
            L.append(u"consulta de versao: DESLIGADA - o endereco das versoes "
                     u"esta fora do formato (%s)" % str(url)[:80])
        else:
            L.append(u"consulta de versao: GET %s | quando: uma vez, no "
                     u"arranque, em segundo plano | leva: so o User-Agent "
                     u"'%s' - sem corpo, sem parametro, nada da estacao nem "
                     u"de paciente | RADAI_URL_VERSOES=0 no ambiente desliga"
                     % (api, agente))
    try:
        import radai_records as _rr
        hosts = u" e ".join(_rr.INTERNET_HOSTS)
        L.append(u"teste de internet do registro de casos: DNS + TCP %d a %s "
                 u"| quando: no maximo a cada %d min, entre uma serie e a "
                 u"seguinte | leva: nada - resolve o nome, abre e fecha a "
                 u"conexao, sem enviar dado"
                 % (_rr.INTERNET_PORTA, hosts,
                    int(round(_rr._INTERNET_VALIDADE_S / 60.0))))
    except Exception as e:
        L.append(u"teste de internet do registro de casos: nao sei o destino "
                 u"(%s: %s)" % (type(e).__name__, str(e)[:80]))
    return L


def _sem_usuario(linha):
    return re.sub(r"(?i)([\\/]Users[\\/])[^\\/:*?\"<>|\r\n]+", r"\1<usuario>",
                  linha)


def bloco(rel):
    d = rel.get("dados") or {}
    est = d.get("estacao") or {}
    cpu = d.get("cpu") or {}
    ver = d.get("versoes") or {}
    py = d.get("python") or {}
    pl = (d.get("placas") or {}).get("placas") or []
    tr = d.get("torch") or {}
    L = [INICIO_BLOCO,
         u"-> %s." % FRASE_DO_BLOCO,
         u"O que e: Radioterapia.AI Local Suite %s - vigia que roda o "
         u"TotalSegmentator (terceiro, Apache-2.0) e plugins LOCALMENTE em series "
         u"DICOM e grava RTSTRUCT como SUGESTAO NAO APROVADA; revisao e aprovacao "
         u"sao ato medico no TPS." % (rel.get("appver") or u"?"),
         u"Quando: %s | arranque em %s s | %d passos%s | DRY_RUN=%s"
         % (rel.get("inicio"), rel.get("segundos"), len(rel.get("passos") or []),
            (u", %d sem medida" % sum(1 for p in rel.get("passos") or [] if not p.get("ok")))
            if any(not p.get("ok") for p in rel.get("passos") or []) else u"",
            1 if rel.get("dry_run") else 0),
         u"Maquina: %s | %s (build %s) | administrador: %s | %s nucleos | RAM %s GB "
         u"(%s livres)" % ((u"%s (pseudonimo, o mesmo do registro de casos)"
                            % est["pseudonimo"]) if est.get("pseudonimo")
                           else u"nome omitido (%s)"
                           % (est.get("pseudonimo_falha") or u"sem pseudonimo"),
                          est.get("so") or u"?", est.get("build") or u"?",
                          est.get("admin") or u"?",
                          (u"%s logicos, %s fisicos" % (cpu.get("nucleos") or u"?",
                                                        cpu["fisicos"]))
                          if cpu.get("fisicos") else (cpu.get("nucleos") or u"?"),
                          cpu.get("ram_gb") or u"?", cpu.get("ram_livre_gb") or u"?"),
         u"Python: %s %s | %s" % (py.get("versao") or u"?",
                                  u"embeddable" if py.get("embeddable")
                                  else (u"? (%s)" % py.get("embeddable_nao_lido", u"nao medido")
                                        if py.get("embeddable") is None else u"comum"),
                                  py.get("executavel") or u"?"),
         u"Versoes: %s" % u" | ".join(
             [u"app %s" % (rel.get("appver") or u"?")]
             + [u"%s %s" % (n, ver.get(n) or u"AUSENTE") for n, _ in BIBLIOTECAS]
             + [u"cuda do build do torch %s" % (ver.get("torch_cuda_build") or u"?")])]
    if pl:
        for p in pl:
            L.append(u"Placa [%d]: %s | %s MiB, %s livres | driver %s | sm %s"
                     % (p["indice"], p["nome"], _fmt(p["total_mb"]),
                        _fmt(p["livre_mb"]), p["driver"], p.get("cap") or u"?"))
    else:
        L.append(u"Placa: nenhuma NVIDIA listada (%s)"
                 % ((d.get("placas") or {}).get("falha") or u"nao medido"))
    cp = d.get("computacao") or {}
    if cp:
        todas = cp.get("placas") or []
        L.append(u"Placas de video (todas, pelo Windows): %s" % (
            u" | ".join(u"%s (%s; %s)" % (
                p.get("nome"),
                (u"%s MiB%s" % (p["memoria_mb"], u" compartilhada"
                                if p.get("integrada") else u""))
                if p.get("memoria_mb") else u"memoria nao lida",
                p.get("frase") or u"?") for p in todas)
            if todas else u"nenhuma listada (%s)" % (cp.get("placas_falha")
                                                    or u"?")))
        if cp.get("cpu"):
            L.append(u"CPU: %s%s" % (cp["cpu"], (
                u" | nnU-Net em CPU: %s" % cp["threads_cpu"])
                if cp.get("threads_cpu") else u""))
        bks = cp.get("backends") or {}
        if bks:
            L.append(u"Backends: %s" % u" | ".join(
                u"%s %s (%s; politica %s)" % (
                    b, u"disponivel" if x.get("disponivel") else u"indisponivel",
                    x.get("detalhe") or u"?", x.get("politica") or u"?")
                for b, x in sorted(bks.items())))
        can = cp.get("canario")
        if can:
            L.append(u"Canario: %s" % can)
    L.append(u"Torch alcanca a placa: %s" % (
        u"sim, %d placa(s)" % (tr.get("n") or 0) if tr.get("disponivel")
        else u"nao (%s)" % (tr.get("falha") or tr.get("erro")
                            or (u"sem CUDA" if tr.get("importa") else u"nao medido"))))
    procs = (d.get("processos") or {}).get("processos") or []
    if procs:
        L.append(u"Quem segura a placa: %s" % u", ".join(
            u"%s%s" % (p["nome"], u"" if p["mem_mb"] is None else u" %.0f MiB" % p["mem_mb"])
            for p in procs) + (u" (uso por processo N/A no WDDM)"
                               if any(p["mem_mb"] is None for p in procs) else u""))
    dr = d.get("driver") or {}
    if dr.get("frase"):
        L.append(u"Driver: %s" % dr["frase"])
    L.append(u"Decisoes:")
    for dec in d.get("decisoes") or []:
        L.append(u"  dispositivo (DEVICE=%s) %s -> %s: %s%s"
                 % (rel.get("device"), dec.get("serie"), dec.get("modo"),
                    dec.get("motivo"),
                    (u" | ~%s min em CPU" % dec["estimativa_min"])
                    if dec.get("estimativa_min") is not None else u""))
    if not d.get("decisoes"):
        L.append(u"  dispositivo: nao decidido no arranque (ver o passo)")
    b = d.get("bases") or {}
    L.append(u"  base anatomica: CT -> %s | MR -> %s" % (b.get("CT") or u"?",
                                                        b.get("MR") or u"?"))
    L.append(u"  modalidades aceitas: %s | TASKS do config: %s"
             % (u",".join(rel.get("modalidades") or []) or u"?",
                u",".join(rel.get("tasks") or []) or u"(vazio)"))
    tpm = d.get("tasks_por_modalidade") or {}
    if tpm:
        sem = d.get("tasks_sem_regra") or u"a regra levantou; ver o passo"
        L.append(u"  roda por modalidade: %s" % u" | ".join(
            u"%s -> %s" % (m, u",".join(v) if v is not None else u"(%s)" % sem)
            for m, v in sorted(tpm.items())))
    pe = d.get("pesos") or {}
    if pe.get("grupos"):
        L.append(u"Pesos: %s" % u" | ".join(
            u"%s %s" % (g["task"], u"ok" if not g["faltam"]
                        else u"FALTAM %s" % u",".join(str(x) for x in g["faltam"]))
            for g in pe["grupos"]))
    rc = d.get("recorte_no_corpo")
    if rc:
        if rc.get("dataset300"):
            _d300 = u"presente"
        elif rc.get("pedido") is False:
            _d300 = u"AUSENTE"
        else:
            _d300 = u"AUSENTE - %s (mais lentas); %s" % (_SEM_300_QUEM_MUDA,
                                                         _SEM_300_QUEM_NAO)
        L.append(u"Recorte no corpo (--body_seg): %s (%s); Dataset300 %s" % (
            {True: u"ligado", False: u"desligado"}.get(rc.get("pedido"), u"?"),
            rc.get("origem") or u"?", _d300))
    rede = d.get("rede")
    L.append(u"Rede por omissao (o que a estacao faz sozinha; nada de paciente):")
    for x in (rede if rede is not None
              else [u"nao sei - este relatorio nao montou a lista"]):
        L.append(u"  %s" % x)
    L.append(u"  por ato declarado de quem opera, e nao sozinho: download de "
             u"pesos e validacao de licenca")
    es = d.get("estatistica") or {}
    if es:
        if es.get("falha"):
            est = u"nao sei (%s)" % es["falha"]
        elif es.get("erro"):
            est = u"nao consegui ler (%s)" % es["erro"]
        elif es.get("valor") is False:
            est = u"desligada no arquivo"
        elif not es.get("existia"):
            est = u"arquivo ainda nao existe"
        else:
            est = u"LIGADA no arquivo"
        L.append(u"Estatistica de uso do TotalSegmentator: %s | envelope %s"
                 % (est, u"bloqueia o envio" if es.get("envelope")
                    else u"NAO bloqueia (%s)" % (es.get("envelope_porque")
                                                 or u"?")))
    mo = d.get("modelos") or []
    if mo:
        L.append(u"Modelos de comparacao: %s" % u" | ".join(
            u"%s %s%s" % (m["nome"], u"instalado" if m["instalado"] else u"ausente",
                          (u", roda %s" % m["quem_liga"])
                          if m.get("quem_liga") else u"")
            for m in mo))
    pr = d.get("procedencia") or {}
    if pr:
        L.append(u"Suavizacao, procedencia e registro de casos:")
        for x in list(pr.get("procedencia") or []) + list(pr.get("registro") or []):
            L.append(u"  %s" % x)
    dk = d.get("disco") or {}
    if dk:
        L.append(u"Disco livre: %s" % u" | ".join(u"%s %.1f GB" % (k, v)
                                                   for k, v in sorted(dk.items())))
    rt = d.get("root") or {}
    L.append(u"ROOT: %s" % (u"vazio (a vigilia nao varre)" if rt.get("vazio", True)
                            else u"%s, %s, %s pasta(s)"
                            % (u"rede" if rt.get("rede") else u"local",
                               u"acessivel" if rt.get("acessivel") else u"NAO acessivel",
                               rt.get("pastas", u"?"))))
    am = d.get("ambiente") or {}
    L.append(u"Ambiente: %s" % ((u"ok - %s" % am.get("detalhe")) if am.get("ok")
                                 else (u"PARADO - %s" % am.get("detalhe")) if am
                                 else u"nao conferido"))
    L.append(u"Avisos:%s" % (u"" if rel.get("avisos") else u" nenhum"))
    for a in rel.get("avisos") or []:
        L.append(u"  - %s" % a)
    L.append(u"Pendencias:%s" % (u"" if rel.get("pendencias") else u" nenhuma"))
    for p in rel.get("pendencias") or []:
        L.append(u"  - %s" % p)
    L.append(u"Tempos: %s" % u" | ".join(
        u"%s %.1fs%s" % (p["nome"], p["segundos"], u"" if p.get("ok") else u" (SEM MEDIDA)")
        for p in rel.get("passos") or []))
    L.append(FIM_BLOCO)
    return [ascii_(_sem_usuario(l)) for l in L]


def gravar(rel, pasta):
    carimbo = datetime.now().strftime("%Y%m%d_%H%M%S")
    if not os.path.isdir(pasta):
        os.makedirs(pasta)
    alvo = os.path.join(pasta, "arranque_%s.txt" % carimbo)
    with io.open(alvo, "w", encoding="utf-8", newline="\r\n") as f:
        f.write(u"\n".join(bloco(rel)) + u"\n")
    return alvo


def linha_de_calibracao(ctx, do_arranque=None):
    partes = []
    try:
        import radai_cleaner
        m = radai_cleaner.memoria_da_estacao() or {}
        if m.get("total_mb"):
            partes.append(u"RAM livre %.1f de %.1f GB"
                          % (m.get("livre_mb", 0) / 1024.0, m["total_mb"] / 1024.0))
    except Exception as e:
        partes.append(u"RAM: nao medi (%s)" % type(e).__name__)
    pl = placas(timeout=15)
    if pl["placas"]:
        partes.append(u"; ".join(u"placa [%d] %s %s/%s MiB livres"
                                 % (p["indice"], p["nome"], _fmt(p["livre_mb"]),
                                    _fmt(p["total_mb"])) for p in pl["placas"]))
    else:
        partes.append(u"sem placa NVIDIA (%s)" % (pl["falha"] or u"?"))
    pedido = str(ctx.get("device") or "auto").strip().lower()
    rotulo, forma, esp = SERIES_TIPO[0]
    if ctx.get("dry_run"):
        partes.append(u"simulacao: a decisao de dispositivo nao e medida")
    elif pedido == "cpu":
        partes.append(u"%s -> cpu (DEVICE=cpu)" % rotulo)
    elif pl["placas"] or (ULTIMO.get("torch") or {}).get("disponivel"):
        try:
            eng = ctx["carregar_engine"]()
            p = eng.plano_de_dispositivo(forma, esp,
                                         task=_base_no_disco("CT")) or {}
            partes.append(u"%s -> %s: %s" % (rotulo, p.get("modo"), p.get("motivo")))
        except Exception as e:
            partes.append(u"decisao de dispositivo nao medida (%s: %s)"
                          % (type(e).__name__, str(e)[:80]))
    else:
        partes.append(u"%s -> cpu (sem placa)" % rotulo)
    if do_arranque:
        partes.append(u"no arranque: %s" % (do_arranque.get("modo") or u"?"))
    return ascii_(u"calibracao de arranque do turno: " + u" | ".join(partes))
