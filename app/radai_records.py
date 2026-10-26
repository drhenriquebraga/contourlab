# -*- coding: utf-8 -*-
import hashlib
import hmac
import io
import json
import os
import platform
import re
import socket
import subprocess
import sys
import threading
import time
import zipfile
from datetime import datetime

VERSAO_REGISTRO = 1
NOME_PASTA = "registro"
NOME_SEGREDO = "_pseudonimo.chave"


def raiz(base=""):
    b = str(base or os.environ.get("RADAI_REGISTRO_DIR") or "").strip()
    if not b:
        b = os.path.join(os.path.dirname(os.path.abspath(__file__)), NOME_PASTA)
    return b


def _garantir(caminho):
    if not os.path.isdir(caminho):
        os.makedirs(caminho)
    return caminho


_SEGREDO_NA_MEMORIA = {}


def _pasta_que_sincroniza(pasta):
    try:
        import radai_archive
        sim, motivo = radai_archive.em_pasta_sincronizada(pasta)
        return bool(sim), u"%s" % (motivo or u"")
    except Exception as e:
        # GUARDA: sem como conferir, a chave fica so na memoria (falha fechado).
        return True, u"sem como conferir a pasta (%s)" % type(e).__name__


AVISO_DO_SEGREDO = (u"A pasta do registro de casos sincroniza com a nuvem: a "
                    u"chave do pseudônimo não é gravada nela e vale só enquanto "
                    u"o programa está aberto. Aponte RADAI_REGISTRO_DIR para "
                    u"uma pasta fora da nuvem.")


def aviso_do_segredo(base=""):
    sim, _motivo = _pasta_que_sincroniza(raiz(base))
    return AVISO_DO_SEGREDO if sim else u""


def _segredo(base=""):
    pasta = _garantir(raiz(base))
    p = os.path.join(pasta, NOME_SEGREDO)
    try:
        if os.path.isfile(p):
            with io.open(p, "rb") as f:
                s = f.read().strip()
            if len(s) >= 32:
                return s
    except Exception:
        pass
    # GUARDA: chave em texto nunca vai para pasta que sincroniza com a nuvem.
    if _pasta_que_sincroniza(pasta)[0]:
        chave = os.path.normcase(os.path.abspath(pasta))
        if chave not in _SEGREDO_NA_MEMORIA:
            _SEGREDO_NA_MEMORIA[chave] = hashlib.sha256(
                os.urandom(64)).hexdigest().encode("ascii")
        return _SEGREDO_NA_MEMORIA[chave]
    s = hashlib.sha256(os.urandom(64)).hexdigest().encode("ascii")
    try:
        with io.open(p, "wb") as f:
            f.write(s)
    except Exception:
        pass
    return s


def pseudonimo(uid, base=""):
    if not uid:
        return "semuid00"
    return hmac.new(_segredo(base), str(uid).encode("utf-8", "replace"),
                    hashlib.sha256).hexdigest()[:8]


class ContemIdentificacao(Exception):
    pass


def _do_uid(uid):
    u = str(uid or "")
    if not u:
        return []
    fora = [u]
    if len(u) >= 8:
        fora.append(u[-8:])
    partes = u.split(".")
    if len(partes) >= 2:
        fora.append(".".join(partes[-2:])[-12:])
        fora.append(partes[-1])
    return [x for x in fora if len(str(x)) >= 4]


_CAMINHO = re.compile(
    r"(?:(?<![A-Za-z0-9])[A-Za-z]:[\\/]|\\\\[A-Za-z0-9_.-]+[\\/])")


def _trocar_caminhos(texto, marca=u"<caminho>"):
    n = 0
    fora = []
    for linha in str(texto or "").split(u"\n"):
        cr = u"\r" if linha.endswith(u"\r") else u""
        if cr:
            linha = linha[:-1]
        pedacos = []
        pos = 0
        while True:
            m = _CAMINHO.search(linha, pos)
            if not m:
                pedacos.append(linha[pos:])
                break
            pedacos.append(linha[pos:m.start()])
            pedacos.append(marca)
            n += 1
            if m.start() > 0 and linha[m.start() - 1] == u'"':
                fim = linha.find(u'"', m.end())
                if fim >= 0:
                    pos = fim
                    continue
            break
        fora.append(u"".join(pedacos) + cr)
    return u"\n".join(fora), n


def sem_caminhos(texto, marca=u"<caminho>"):
    return _trocar_caminhos(texto, marca)[0]


def pastas_para_trocar(caminhos, prefixos=()):
    def _partes(c):
        return [p for p in re.split(r"[\\/]+", str(c or u"")) if p]

    cortes = []
    for pre in (prefixos or ()):
        if not pre:
            continue
        try:
            pre = os.path.normcase(os.path.abspath(str(pre)))
        except Exception:
            pre = str(pre)
        pp = [p.lower() for p in _partes(pre)]
        if pp:
            cortes.append(pp)
    fora = []
    for c in (caminhos or ()):
        partes = _partes(c)
        baixo = [p.lower() for p in partes]
        for pp in cortes:
            if baixo[:len(pp)] == pp:
                partes = partes[len(pp):]
                break
        for p in partes:
            for q in (p.strip(), os.path.splitext(p)[0].strip()):
                if (len(q) >= 4 and not q.isdigit() and q not in (".", "..")
                        and q not in fora):
                    fora.append(q)
    return fora


def _pedacos_identificadores(*valores):
    fora = []
    for v in valores:
        s = str(v or "").strip()
        if len(s) >= 4:
            fora.append(s)
            for p in s.split("."):
                if len(p) >= 6:
                    fora.append(p)
    return sorted(set(fora), key=len, reverse=True)


def conferir_sem_identificacao(texto, identificadores):
    baixo = str(texto or "").lower()
    achados = [p for p in _pedacos_identificadores(*identificadores)
               if p.lower() in baixo]
    if achados:
        raise ContemIdentificacao(
            u"o registro ia levar %d identificador(es) real(is) — não gravei. "
            u"O primeiro tem %d caracteres." % (len(achados), len(achados[0])))
    return True


def higienizar(texto, identificadores, marca=u"<paciente>", isolados=()):
    s = str(texto or "")
    n = 0
    for p in _pedacos_identificadores(*identificadores):
        if not p:
            continue
        achou = re.compile(re.escape(p), re.I)
        s, k = achou.subn(marca, s)
        n += k
    for p in isolados or ():
        p = str(p or "").strip()
        if not p:
            continue
        if re.match(r"^[0-9.]+$", p):
            achou = re.compile(r"(?<![0-9A-Za-z])" + re.escape(p)
                               + r"(?![0-9A-Za-z])")
        else:
            achou = re.compile(re.escape(p), re.I)
        s, k = achou.subn(marca, s)
        n += k
    s, k = _trocar_caminhos(s)
    n += k
    return s, n


def _rodar(args, timeout=12):
    try:
        p = subprocess.run(args, capture_output=True, timeout=timeout,
                           creationflags=(getattr(subprocess, "CREATE_NO_WINDOW", 0)))
        saida = (p.stdout or b"").decode("cp850", "replace")
        return p.returncode == 0, saida
    except Exception:
        return False, ""


def _e_admin():
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return None


_INTERNET = {"quando": 0.0, "valor": None}
_INTERNET_VALIDADE_S = 1800.0
INTERNET_HOSTS = ("pypi.org", "github.com")
INTERNET_PORTA = 443


def _resolver_com_limite(host, limite):
    import threading
    saida = {}

    def _alvo():
        try:
            saida["ip"] = socket.gethostbyname(host)
        except Exception as e:
            saida["erro"] = e

    t = threading.Thread(target=_alvo, daemon=True)
    t.start()
    t.join(limite)
    return saida.get("ip")


def _tem_internet(timeout=2.5):
    agora = time.time()
    if (_INTERNET["valor"] is not None
            and agora - _INTERNET["quando"] < _INTERNET_VALIDADE_S):
        return _INTERNET["valor"]
    valor = False
    for host in INTERNET_HOSTS:
        try:
            ip = _resolver_com_limite(host, timeout)
            if not ip:
                continue
            s = socket.create_connection((ip, INTERNET_PORTA), timeout=timeout)
            s.close()
            valor = True
            break
        except Exception:
            continue
    _INTERNET["quando"], _INTERNET["valor"] = agora, valor
    return valor


def _edicao_windows():
    ok, s = _rodar(["cmd", "/c", "ver"])
    versao = " ".join((s or "").split())[:60]
    try:
        return {"versao": versao or platform.platform()[:60],
                "release": platform.release(), "build": platform.version()}
    except Exception:
        return {"versao": versao, "release": "", "build": ""}


def _gpu():
    ok, s = _rodar(["nvidia-smi", "--query-gpu=name,memory.total",
                    "--format=csv,noheader"])
    if ok and s.strip():
        linhas = [l.strip() for l in s.splitlines() if l.strip()]
        return {"tem": True, "placas": linhas[:4]}
    return {"tem": False, "placas": []}


def pseudonimo_da_maquina(base=""):
    return pseudonimo(
        (os.environ.get("COMPUTERNAME") or socket.gethostname() or "?"), base)


_PSEUDONIMO_DE_MAQUINA = re.compile(r"^[0-9a-f]{8}$")


def pseudonimo_de_uma_maquina(nome, base=""):
    n = u"%s" % (nome or u"")
    if not n.strip():
        return n
    try:
        daqui = set(str(x).strip().upper() for x in (
            os.environ.get("COMPUTERNAME"), os.environ.get("RADAI_MACHINE"),
            socket.gethostname()) if x)
        if n.strip().upper() in daqui:
            return pseudonimo_da_maquina(base)
        return pseudonimo(n.strip().upper(), base)
    except Exception:
        return u"?"


def _maquinas_por_pseudonimo(d, base=""):
    n = 0
    try:
        for e in (d or {}).get("etapas") or ():
            if not isinstance(e, dict):
                continue
            v = e.get("maquina")
            if v and not _PSEUDONIMO_DE_MAQUINA.match(u"%s" % v):
                e["maquina"] = pseudonimo_de_uma_maquina(v, base)
                n += 1
    except Exception:
        return n
    return n


def perfil_da_estacao(papel="", base=""):
    p = {"versao_registro": VERSAO_REGISTRO,
         "quando": datetime.now().astimezone().isoformat(timespec="seconds"),
         "papel_declarado": str(papel or "") or None}
    try:
        p["maquina"] = pseudonimo_da_maquina(base)
    except Exception:
        p["maquina"] = None
    try:
        import multiprocessing
        p["nucleos"] = int(multiprocessing.cpu_count())
    except Exception:
        p["nucleos"] = None
    try:
        p["processador"] = (platform.processor() or "")[:80] or None
    except Exception:
        p["processador"] = None
    p["windows"] = _edicao_windows()
    p["python"] = sys.version.split()[0]
    p["admin"] = _e_admin()
    p["internet"] = _tem_internet()
    p["gpu"] = _gpu()
    p["memoria"] = None
    try:
        import radai_cleaner as LP
        m = LP.memoria_da_estacao() or {}
        if m.get("total_mb"):
            p["memoria"] = {"total_gb": round(m["total_mb"] / 1024.0, 1),
                            "livre_gb": round(m.get("livre_mb", 0) / 1024.0, 1),
                            "pct_em_uso": m.get("pct")}
    except Exception:
        pass
    return p


def gravar_perfil(papel="", base=""):
    try:
        p = perfil_da_estacao(papel, base)
        alvo = os.path.join(_garantir(raiz(base)), "estacao.json")
        _gravar_json(alvo, p)
        return alvo
    except Exception:
        return ""


def _gravar_json(caminho, dado):
    tmp = "%s.%d.parcial" % (caminho, os.getpid())
    with io.open(tmp, "w", encoding="utf-8") as f:
        f.write(json.dumps(dado, ensure_ascii=False, indent=1))
    os.replace(tmp, caminho)
    return caminho


def _texto_de(caminho, limite=200):
    try:
        with io.open(caminho, encoding="utf-8-sig") as f:
            return f.read(limite).strip()
    except Exception:
        return ""


def _raiz_do_programa():
    d = os.path.dirname(os.path.abspath(__file__))
    for _ in range(3):
        if os.path.isfile(os.path.join(d, "entrega.txt")):
            return d
        pai = os.path.dirname(d)
        if pai == d:
            break
        d = pai
    return os.path.dirname(os.path.abspath(__file__))


def identidade_do_programa():
    fora = {"app": None, "build": None}
    try:
        p = os.path.join(_raiz_do_programa(), "entrega.txt")
        for linha in _texto_de(p, 8000).splitlines():
            k, _, v = linha.strip().partition("=")
            if k.strip().upper() == "VERSAO":
                fora["app"] = v.strip()[:20] or None
            elif k.strip().upper() == "BUILD":
                fora["build"] = v.strip()[:40] or None
    except Exception:
        pass
    return fora


def rotulo_da_versao(app, build=None):
    a = u"%s" % (app or u"")
    if not a:
        return u"não declarada"
    return (u"%s (build %s)" % (a, build)) if build else a


def versoes(tasks=(), base=""):
    v = {"esquema_registro": VERSAO_REGISTRO}
    raiz_prog = _raiz_do_programa()
    try:
        for linha in _texto_de(os.path.join(raiz_prog, "entrega.txt"), 4000).splitlines():
            if linha.strip().upper().startswith("VERSAO="):
                v["app"] = linha.split("=", 1)[1].strip()
            elif linha.strip().upper().startswith("PRODUTO="):
                v["produto"] = linha.split("=", 1)[1].strip()
            elif linha.strip().upper().startswith("BUILD="):
                v["build"] = linha.split("=", 1)[1].strip()[:40]
    except Exception:
        pass
    v.setdefault("app", None)
    try:
        p = os.path.join(raiz_prog, "_requisitos.json")
        if os.path.isfile(p):
            with io.open(p, encoding="utf-8") as f:
                req = json.load(f)
            v["requisitos"] = {k: req[k] for k in
                               ("impressao", "digital", "hash", "python",
                                "torch", "totalsegmentator", "tasks")
                               if k in req}
            if not v["requisitos"]:
                v["requisitos"] = {"chaves": sorted(req)[:12]}
    except Exception:
        pass
    try:
        import radai_tasks
    except Exception:
        radai_tasks = None
    try:
        if tasks and radai_tasks is not None:
            nomes = radai_tasks.traduzir_apelidos([str(t) for t in tasks])
            v["tasks"] = sorted(set(nomes))
        elif tasks:
            v["tasks"] = sorted(str(t) for t in tasks)
    except Exception:
        pass
    v["modelos"] = {}
    def _versao(mod, dist=None):
        try:
            from importlib import metadata
            return metadata.version(dist or mod)
        except Exception:
            pass
        try:
            return getattr(__import__(mod), "__version__", None) or "presente"
        except Exception:
            return None
    for mod, chave, dist in (
            ("totalsegmentator", "totalsegmentator", "TotalSegmentator"),
            ("torch", "torch", None), ("nnunetv2", "nnunetv2", None),
            ("SimpleITK", "simpleitk", "SimpleITK"),
            ("pydicom", "pydicom", None), ("monai", "monai", None)):
        v["modelos"][chave] = _versao(mod, dist)
    try:
        mods = os.environ.get("RADAI_MODELOS_DIR") or os.path.join(raiz_prog, "modelos")
        pv = os.path.join(mods, "nv_segment_ct", "models", "model.pt")
        if os.path.isfile(pv):
            v["modelos"]["vista3d_bytes"] = os.path.getsize(pv)
    except Exception:
        pass
    return v


CAMPOS_DO_PROCESSAMENTO = (
    "modo", "protocolos", "tasks_ligadas", "tasks_desligadas", "comparacao",
    "oar_fora", "clip_box", "remocoes", "travamentos", "pico_memoria",
    "plano_dispositivo", "tempos_por_passo", "niveis_cervicais",
    "ilhas_em_revisao", "oar_fora_por_regiao", "acabamento")
MODOS_DE_PROCESSAMENTO = ("fast", "auto", "perso")


_LINHA_DE_MEMORIA = re.compile(
    r"TS (\S+) memoria: ([\d.]+) GB livres no inicio, ([\d.]+) no pico de "
    r"uso .*?, (\d+)% da estacao no pior momento")


def remocoes_do_full(regras):
    fora = []
    for x in (regras or ()):
        try:
            x = dict(x)
            longa = u"%s" % (x.get("regra") or u"?")
            curta = longa.split()[0] if longa.split() else u"?"
            fora.append({
                "nome": u"%s" % (x.get("nome") or u"?"),
                "volume_cm3": round(float(x.get("cm3") or 0.0), 2),
                "regra": curta,
                "inteira": bool(x.get("inteira")),
                "motivo": (u"%s: %s" % (longa, x.get("motivo") or u""))
                .strip().rstrip(u":")})
        except Exception:
            continue
    return fora


def ilhas_do_full(ilhas):
    fora = []
    for x in (ilhas or ()):
        try:
            x = dict(x)
            fora.append({"nome": u"%s" % (x.get("nome") or u"?"),
                         "ilhas": int(x.get("ilhas") or 0),
                         "cm3": round(float(x.get("cm3") or 0.0), 2)})
        except Exception:
            continue
    return fora


def acabamento_do_caso(acabamento):
    out = []
    try:
        itens = sorted(dict(acabamento or {}).items())
    except Exception:
        return out
    for nome, med in itens:
        try:
            med = dict(med or {})
            cob = dict((u"%s" % k, round(float(v), 4))
                       for k, v in sorted(dict(med.get("cobertura")
                                               or {}).items()))
            conf = []
            for x in med.get("conflitos") or ():
                x = list(x)
                conf.append({"alca": u"%s" % x[0],
                             "cm3": round(float(x[1]), 2),
                             "motivo": u"%s" % (x[2] if len(x) > 2 else u"")})
            out.append({"estrutura": u"%s" % nome, "cobertura": cob,
                        "conflitos": conf})
        except Exception:
            continue
    return out


def oar_fora_por_regiao_do_caso(fora):
    out = []
    try:
        for k in sorted(dict(fora or {})):
            out.append({"chave": u"%s" % k,
                        "motivo": u"%s" % (dict(fora)[k] or u"")})
    except Exception:
        return out
    return out


PLANO_SEM_PLACA = {"modo": "cpu", "motivo": "DEVICE resolveu para cpu"}
_CHAVES_DO_PLANO_POR_TASK = ("modo", "modo_do_plano", "motivo", "plano_menor",
                             "placa")


def plano_do_caso(plano=None, planos=None, dispositivo=None):
    try:
        fora = dict(plano or {})
        if not fora and (u"%s" % (dispositivo or u"")).lower() == u"cpu":
            fora = dict(PLANO_SEM_PLACA)
        pt = {}
        for t, p in dict(planos or {}).items():
            pt[u"%s" % t] = dict((k, v) for k, v in dict(p or {}).items()
                                 if k in _CHAVES_DO_PLANO_POR_TASK)
        if pt:
            fora["por_task"] = pt
        return fora or None
    except Exception:
        return None


def clip_box_do_caso(recortes, modo=None, entrada=None):
    fora = {}
    for t, cx in dict(recortes or {}).items():
        try:
            item = dict((k, v) for k, v in dict(cx or {}).items()
                        if k != "zyx")
            ent = {}
            if entrada is not None:
                try:
                    ent = dict(entrada(t, modo=modo) or {})
                except Exception:
                    ent = {}
            item["usado"] = True
            item["medido"] = bool(ent.get("medido") if ent
                                  else item.get("medido"))
            if ent.get("numeros"):
                item["numeros"] = ent.get("numeros")
            fora[u"%s" % t] = item
        except Exception:
            continue
    return fora


def pico_de_memoria(linhas):
    por_task, pior = {}, None
    try:
        for ln in (linhas or ()):
            m = _LINHA_DE_MEMORIA.search(u"%s" % (ln,))
            if not m:
                continue
            t = m.group(1)
            d = {"ram_pct": float(m.group(4)),
                 "livre_inicio_gb": float(m.group(2)),
                 "livre_min_gb": float(m.group(3))}
            a = por_task.get(t)
            if a is None or d["ram_pct"] >= a["ram_pct"]:
                por_task[t] = d
            if pior is None or d["ram_pct"] > pior[1]["ram_pct"]:
                pior = (t, d)
    except Exception:
        return None
    if pior is None:
        return None
    return {"ram_pct": pior[1]["ram_pct"],
            "livre_min_gb": min(d["livre_min_gb"] for d in por_task.values()),
            "task": pior[0], "por_task": por_task,
            "origem": u"log do motor: a memoria da ESTACAO durante cada task "
                      u"(tudo o que rodou junto)"}


class Caso(object):

    def __init__(self, uid="", identificadores=(), base="", papel="", tasks=(),
                 so_trocar=(), t0=None):
        self.base = base
        self.uid = str(uid or "")
        self._ident = [x for x in identificadores if x] + _do_uid(self.uid)
        self._so_trocar = [x for x in so_trocar if x]
        self._log = ""
        self.d = {
            "versao_registro": VERSAO_REGISTRO,
            "pseudonimo": pseudonimo(self.uid, base),
            "abriu": datetime.now().astimezone().isoformat(timespec="seconds"),
            "estacao": perfil_da_estacao(papel, base),
            "versoes": versoes(tasks, base),
            "serie": {}, "execucao": {}, "resultado": {},
            "achados": [], "etapas": [],
        }
        self._t0 = float(t0) if t0 is not None else time.time()

    def serie(self, **campos):
        for k, v in campos.items():
            if k in ("descricao", "series_description", "study_description"):
                continue
            self.d["serie"][k] = v
        return self

    def etapa(self, nome, segundos=None, **extra):
        e = {"etapa": str(nome)}
        if segundos is not None:
            e["segundos"] = round(float(segundos), 1)
        e.update(extra)
        if e.get("maquina"):
            e["maquina"] = pseudonimo_de_uma_maquina(e["maquina"], self.base)
        self.d["etapas"].append(e)
        return self

    def achado(self, tipo, detalhe=u"", **numeros):
        a = {"tipo": str(tipo), "detalhe": str(detalhe or "")}
        a.update(numeros)
        self.d["achados"].append(a)
        return self

    def resultado(self, ok, erro=u"", **campos):
        self.d["resultado"] = {"ok": bool(ok), "erro": str(erro or "")}
        self.d["resultado"].update(campos)
        return self

    def execucao(self, **campos):
        self.d["execucao"].update(campos)
        return self

    def processamento(self, **campos):
        pr = self.d.setdefault("processamento", {})
        for k, v in campos.items():
            if k in CAMPOS_DO_PROCESSAMENTO:
                if k == "modo" and v is not None:
                    v = str(v).strip().lower()
                if (k == "niveis_cervicais" and isinstance(v, dict)
                        and v.get("rodam")):
                    v = dict(v)
                    v.setdefault("rede", _rede_dos_niveis())
                pr[k] = v
            elif v is not None:
                ign = pr.setdefault("campos_ignorados", [])
                if str(k) not in ign:
                    ign.append(str(k))
        return self

    def log(self, texto):
        s, n = higienizar(texto, self._ident, isolados=self._so_trocar)
        self._log = s
        self.d["log"] = {"linhas": s.count(chr(10)) + 1 if s else 0,
                         "trocas_de_identificacao": n,
                         "arquivo": "log.txt"}
        return self

    def gravar(self, segundos=None):
        if segundos is not None:
            self.d["segundos_totais"] = round(float(segundos), 1)
            self.d["segundos_origem"] = u"medido por quem rodou a serie"
        else:
            self.d["segundos_totais"] = round(time.time() - self._t0, 1)
            self.d["segundos_origem"] = u"desde a abertura do registro"
        self.d["fechou"] = datetime.now().astimezone().isoformat(timespec="seconds")
        trocar, outras = self._ident, self._so_trocar
        for a in self.d["achados"]:
            a["detalhe"], _ = higienizar(a.get("detalhe", ""), trocar,
                                         isolados=outras)
        if self.d["resultado"].get("erro"):
            self.d["resultado"]["erro"], _ = higienizar(
                self.d["resultado"]["erro"], trocar, isolados=outras)
        ex = self.d.get("execucao") or {}
        for k in ("motivo_do_modo", "plano_origem", "tempo_por_parte_nota"):
            if isinstance(ex.get(k), str):
                ex[k], _ = higienizar(ex[k], trocar, isolados=outras)
        if isinstance(ex.get("fallbacks"), list):
            ex["fallbacks"] = [higienizar(str(x), trocar, isolados=outras)[0]
                               for x in ex["fallbacks"]]
        for k in ("recorte_no_corpo", "recuo_cpu", "tasks_falharam"):
            if ex.get(k):
                ex[k] = _higienizar_arvore(ex[k], trocar, outras)

        if self.d.get("processamento"):
            self.d["processamento"] = _higienizar_arvore(
                self.d["processamento"], trocar, outras)

        texto = json.dumps(self.d, ensure_ascii=False)
        conferir_sem_identificacao(texto, self._ident)

        pasta = _pasta_nova_do_caso(
            os.path.join(_garantir(raiz(self.base)), "casos"),
            self.d["abriu"][:10], self.d["abriu"][11:19].replace(":", ""),
            self.d["pseudonimo"])
        self.d["caso"] = os.path.basename(pasta)
        _gravar_json(os.path.join(pasta, "caso.json"), self.d)
        with io.open(os.path.join(pasta, "caso.md"), "w", encoding="utf-8") as f:
            f.write(narrativa(self.d))
        if self._log:
            conferir_sem_identificacao(self._log, self._ident)
            with io.open(os.path.join(pasta, "log.txt"), "w",
                         encoding="utf-8") as f:
                f.write(self._log)
        _acrescentar_indice(self.d, self.base)
        return pasta


def _pasta_nova_do_caso(casos, dia, hora, pseudo):
    _garantir(casos)
    nome = u"%s_%s_%s" % (dia, hora or u"000000", pseudo)
    for n in range(1, 1000):
        alvo = os.path.join(casos, nome if n == 1 else u"%s_%d" % (nome, n))
        try:
            os.mkdir(alvo)
            return alvo
        except FileExistsError:
            continue
    raise OSError(u"mil tentativas no mesmo segundo para o mesmo caso")


def _higienizar_arvore(v, trocar, outras):
    if isinstance(v, dict):
        return dict((k, _higienizar_arvore(x, trocar, outras))
                    for k, x in v.items())
    if isinstance(v, list):
        return [_higienizar_arvore(x, trocar, outras) for x in v]
    if isinstance(v, str):
        return higienizar(v, trocar, isolados=outras)[0]
    return v


def _acrescentar_indice(d, base=""):
    try:
        linha = {"pseudonimo": d["pseudonimo"], "quando": d["abriu"],
                 "maquina": (d.get("estacao") or {}).get("maquina"),
                 "ok": (d.get("resultado") or {}).get("ok"),
                 "cortes": (d.get("serie") or {}).get("cortes"),
                 "espessura_mm": (d.get("serie") or {}).get("espessura_mm"),
                 "segundos": d.get("segundos_totais"),
                 "modo": (d.get("execucao") or {}).get("modo"),
                 "fallbacks": len((d.get("execucao") or {}).get("fallbacks") or []),
                 "achados": len(d.get("achados") or []),
                 "erro": ((d.get("resultado") or {}).get("erro") or "")[:120]}
        pr = d.get("processamento") or {}
        ex = d.get("execucao") or {}
        linha.update({
            "pasta": d.get("caso"),
            "origem": ex.get("origem"),
            "modo_processamento": pr.get("modo"),
            "estruturas": (d.get("resultado") or {}).get("estruturas"),
            "remocoes": len(pr.get("remocoes") or []),
            "travamentos": len(pr.get("travamentos") or []),
            "tasks_falharam": len(ex.get("tasks_falharam") or []),
            "app": (d.get("versoes") or {}).get("app"),
            "build": (d.get("versoes") or {}).get("build"),
        })
        if (d.get("resultado") or {}).get("interrompido"):
            linha["interrompido"] = True
        p = os.path.join(raiz(base), "indice.jsonl")
        with io.open(p, "a", encoding="utf-8") as f:
            f.write(json.dumps(linha, ensure_ascii=False) + "\n")
    except Exception:
        pass


PASTA_EM_ANDAMENTO = "em_andamento"
FRASE_DO_INTERROMPIDO = (u"interrompido: o programa parou no meio da série "
                         u"(última etapa «%s» às %s); o caso foi fechado ao "
                         u"abrir o programa de novo")


def _agora_iso():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _arquivo_em_andamento(pseudo, pid, base=""):
    return os.path.join(raiz(base), PASTA_EM_ANDAMENTO,
                        u"%s_%d.json" % (pseudo, int(pid)))


class CasoEmAndamento(object):

    def __init__(self, uid="", origem=u"", modo=None, base=""):
        self.base = base
        ident = identidade_do_programa()
        agora = _agora_iso()
        self.d = {"versao_registro": VERSAO_REGISTRO,
                  "pseudonimo": pseudonimo(uid, base), "abriu": agora,
                  "origem": u"%s" % (origem or u""),
                  "modo": (u"%s" % modo).strip().lower() if modo else None,
                  "pid_os": os.getpid(), "app": ident.get("app"),
                  "build": ident.get("build"),
                  "maquina": pseudonimo_da_maquina(base),
                  "ultima_etapa": u"preparo", "hora_da_etapa": agora}
        self.caminho = _arquivo_em_andamento(self.d["pseudonimo"],
                                             os.getpid(), base)
        self.aberto = False

    def abrir(self):
        try:
            _garantir(os.path.dirname(self.caminho))
            _gravar_json(self.caminho, self.d)
            self.aberto = True
        except Exception:
            self.aberto = False
        return self.aberto

    def etapa(self, nome):
        if not self.aberto:
            return False
        self.d["ultima_etapa"] = (u"%s" % (nome or u"?"))[:120]
        self.d["hora_da_etapa"] = _agora_iso()
        try:
            _gravar_json(self.caminho, self.d)
            return True
        except Exception:
            return False

    def fechar(self):
        self.aberto = False
        return _tirar_em_andamento(self.d["pseudonimo"], base=self.base)


def _tirar_em_andamento(pseudo, pid=None, base=""):
    try:
        os.remove(_arquivo_em_andamento(pseudo, os.getpid() if pid is None
                                        else pid, base))
        return True
    except FileNotFoundError:
        return False
    except Exception:
        return False


def casos_em_andamento(base=""):
    d = os.path.join(raiz(base), PASTA_EM_ANDAMENTO)
    fora = []
    try:
        nomes = sorted(n for n in os.listdir(d) if n.endswith(".json"))
    except Exception:
        return fora
    for n in nomes:
        p = os.path.join(d, n)
        try:
            with io.open(p, encoding="utf-8") as f:
                x = json.load(f)
            if isinstance(x, dict):
                fora.append((p, x))
        except Exception:
            fora.append((p, None))
    return fora


def _segundos_entre(a, b):
    try:
        return round(max(0.0, (datetime.fromisoformat(str(b))
                               - datetime.fromisoformat(str(a)))
                         .total_seconds()), 1)
    except Exception:
        return None


def caso_interrompido(x):
    hora = (u"%s" % (x.get("hora_da_etapa") or x.get("abriu") or u""))
    etapa = (u"%s" % (x.get("ultima_etapa") or u"?"))[:120]
    frase = FRASE_DO_INTERROMPIDO % (etapa, hora[11:16] or u"?")
    d = {"versao_registro": VERSAO_REGISTRO,
         "pseudonimo": u"%s" % (x.get("pseudonimo") or u"semuid00"),
         "abriu": u"%s" % (x.get("abriu") or _agora_iso()),
         "estacao": {"maquina": x.get("maquina")},
         "versoes": {"app": x.get("app"), "build": x.get("build")},
         "serie": {}, "execucao": {"origem": x.get("origem") or None},
         "resultado": {"ok": False, "interrompido": True, "erro": frase,
                       "ultima_etapa": etapa, "hora_da_etapa": hora},
         "achados": [], "etapas": [{"etapa": etapa}],
         "segundos_totais": _segundos_entre(x.get("abriu"), hora),
         "segundos_origem": u"da abertura do caso até a última etapa gravada",
         "fechou": _agora_iso()}
    if x.get("modo"):
        d["processamento"] = {"modo": u"%s" % x["modo"]}
    return d


def fechar_interrompidos(vivo=None, base="", log=None):
    fechados = []
    for p, x in casos_em_andamento(base):
        if x is None:
            try:
                os.remove(p)
            except Exception:
                pass
            continue
        try:
            pid = int(x.get("pid_os") or 0)
        except (TypeError, ValueError):
            pid = 0
        if pid == os.getpid():
            continue
        try:
            if pid and vivo is not None and vivo(pid):
                continue
        except Exception:
            continue
        try:
            d = caso_interrompido(x)
            pasta = _pasta_nova_do_caso(
                os.path.join(_garantir(raiz(base)), "casos"),
                d["abriu"][:10], d["abriu"][11:19].replace(":", ""),
                d["pseudonimo"])
            d["caso"] = os.path.basename(pasta)
            _gravar_json(os.path.join(pasta, "caso.json"), d)
            with io.open(os.path.join(pasta, "caso.md"), "w",
                         encoding="utf-8") as f:
                f.write(narrativa(d))
            _acrescentar_indice(d, base)
            os.remove(p)
            fechados.append(d["caso"])
        except Exception as e:
            if log:
                try:
                    log(u"registro de casos: nao consegui fechar um caso "
                        u"interrompido (%s)" % type(e).__name__)
                except Exception:
                    pass
    if fechados and log:
        try:
            log(u"registro de casos: %d caso(s) em andamento de um processo "
                u"que parou foram fechados como «interrompido», com a ultima "
                u"etapa e a hora" % len(fechados))
        except Exception:
            pass
    return fechados


NOME_DO_LOG_DA_SERIE = u"%s.log.txt"
NOME_DO_LOG_ANTERIOR = u"%s.log.anterior.txt"
TETO_DO_LOG_DA_SERIE = 4 * 1024 * 1024
FRASE_DO_LOG_CHEIO = u"[... o log desta serie passou de %d MB e parou aqui ...]"


class LogDaSerie(object):

    def __init__(self, pasta_radai, uid, identificadores=(), so_trocar=(),
                 teto=TETO_DO_LOG_DA_SERIE):
        self.pasta = u"%s" % pasta_radai
        nome = u"%s" % (uid or u"serie")
        self.caminho = os.path.join(self.pasta, NOME_DO_LOG_DA_SERIE % nome)
        self.anterior = os.path.join(self.pasta, NOME_DO_LOG_ANTERIOR % nome)
        self._ident = [x for x in identificadores if x] + _do_uid(uid)
        self._so_trocar = [x for x in so_trocar if x]
        self.teto = int(teto)
        self.escritos = 0
        self.cheio = False
        self.erro = u""
        self._f = None
        self._trava = threading.Lock()

    def abrir(self):
        try:
            _garantir(self.pasta)
            try:
                if os.path.getsize(self.caminho) >= self.teto:
                    os.replace(self.caminho, self.anterior)
            except OSError:
                pass
            self._f = io.open(self.caminho, "a", encoding="utf-8",
                              errors="replace")
            try:
                self.escritos = os.path.getsize(self.caminho)
            except OSError:
                self.escritos = 0
        except Exception as e:
            self._f = None
            self.erro = type(e).__name__
        return self._f is not None

    def __call__(self, linha):
        f = self._f
        if f is None or self.cheio:
            return
        try:
            s = (u"%s" % (linha,)).replace(u"\r", u" ").replace(u"\n", u" ")
            if not s.startswith(u"["):
                s = u"[%s] %s" % (datetime.now().strftime("%d/%m %H:%M:%S"),
                                  s)
            s, _n = higienizar(s, self._ident, isolados=self._so_trocar)
            s += u"\n"
            n = len(s.encode("utf-8"))
            with self._trava:
                if self.escritos + n > self.teto:
                    f.write(FRASE_DO_LOG_CHEIO % (self.teto // (1024 * 1024))
                            + u"\n")
                    self.cheio = True
                else:
                    f.write(s)
                    self.escritos += n
                f.flush()
        except Exception:
            pass

    def fechar(self):
        f, self._f = self._f, None
        if f is not None:
            try:
                f.close()
            except Exception:
                pass


def _lista_curta(v, teto=30):
    try:
        if isinstance(v, dict):
            return u", ".join(u"%s=%s" % (k, v[k]) for k in sorted(v))
        if isinstance(v, (list, tuple)):
            itens = [str(x) for x in v]
            mais = len(itens) - teto
            return (u", ".join(itens[:teto])
                    + (u" (+%d)" % mais if mais > 0 else u"")) or u"nenhuma"
        return u"%s" % (v,)
    except Exception:
        return u"?"


def _narrativa_do_processamento(pr):
    if not pr:
        return []
    L = [u"## O que foi pedido e o que o programa fez", u""]
    rotulos = (("modo", u"modo"), ("protocolos", u"protocolos"),
               ("tasks_ligadas", u"tasks ligadas"),
               ("tasks_desligadas", u"tasks desligadas"),
               ("comparacao", u"comparação pedida"),
               ("oar_fora", u"tiradas do OAR (o «x»)"),
               ("niveis_cervicais", u"níveis cervicais"),
               ("pico_memoria", u"pico de memória"),
               ("plano_dispositivo", u"plano de dispositivo"),
               ("ilhas_em_revisao", u"ilhas mantidas para revisão (R2)"))
    for k, rot in rotulos:
        if k in pr:
            L.append(u"- **%s:** %s" % (rot, _lista_curta(pr[k])))
    cb = pr.get("clip_box") or {}
    if cb:
        L.append(u"- **recorte por task (clip-box):**")
        for t in sorted(cb):
            L.append(u"  - %s: %s" % (t, _lista_curta(cb[t])))
    frg = pr.get("oar_fora_por_regiao") or []
    if frg:
        L.append(u"- **fora do entregue pela região (ficam no FULL):**")
        for x in frg:
            x = x if isinstance(x, dict) else {"chave": x}
            L.append(u"  - %s: %s" % (x.get("chave", u"?"),
                                      x.get("motivo", u"") or u""))
    if pr.get("campos_ignorados"):
        L.append(u"- **campos que a porta mandou e o registro não conhece:** %s"
                 % _lista_curta(pr["campos_ignorados"]))
    L.append(u"")
    rem = pr.get("remocoes") or []
    if rem:
        L += [u"### Remoções (%d) — regras R1 a R4" % len(rem), u"",
              u"| estrutura | cm³ | regra | motivo |", u"|---|---|---|---|"]
        for x in rem:
            x = x if isinstance(x, dict) else {"nome": x}
            L.append(u"| %s | %s | %s | %s |" % (
                x.get("nome", u"?"), x.get("volume_cm3", u"—"),
                x.get("regra", u"?"), x.get("motivo", u"") or u""))
        L.append(u"")
    trv = pr.get("travamentos") or []
    if trv:
        L += [u"### Travamentos (%d)" % len(trv), u"",
              u"| task | motivo | retomada |", u"|---|---|---|"]
        for x in trv:
            x = x if isinstance(x, dict) else {"task": x}
            L.append(u"| %s | %s | %s |" % (x.get("task", u"?"),
                                             x.get("motivo", u""),
                                             x.get("retomada", u"")))
        L.append(u"")
    passos = pr.get("tempos_por_passo") or []
    if passos:
        L += [u"### Tempo por passo", u"", u"| passo | segundos |", u"|---|---|"]
        for x in passos:
            x = x if isinstance(x, dict) else {"passo": x}
            L.append(u"| %s | %s |" % (x.get("passo") or x.get("etapa") or u"?",
                                       x.get("segundos", u"—")))
        L.append(u"")
    return L


def narrativa(d):
    e = d.get("estacao") or {}
    s = d.get("serie") or {}
    r = d.get("resultado") or {}
    L = []
    L.append(u"# Caso %s" % d.get("pseudonimo"))
    L.append(u"")
    L.append(u"- **quando:** %s" % d.get("abriu"))
    L.append(u"- **resultado:** %s%s" % (
        u"concluído" if r.get("ok") else u"NÃO concluído",
        (u" — %s" % r["erro"]) if r.get("erro") else u""))
    L.append(u"- **tempo total:** %s s" % d.get("segundos_totais"))
    L.append(u"")
    L.append(u"## A máquina")
    L.append(u"")
    mem = e.get("memoria") or {}
    L.append(u"| | |")
    L.append(u"|---|---|")
    L.append(u"| papel declarado | %s |" % (e.get("papel_declarado") or u"não declarado"))
    L.append(u"| núcleos | %s |" % e.get("nucleos"))
    L.append(u"| memória | %s GB total, %s GB livres (%s%% em uso) |"
             % (mem.get("total_gb"), mem.get("livre_gb"), mem.get("pct_em_uso")))
    L.append(u"| GPU | %s |" % (u", ".join((e.get("gpu") or {}).get("placas") or [])
                                or u"nenhuma"))
    L.append(u"| administrador | %s |" % {True: u"sim", False: u"não",
                                          None: u"não deu para saber"}.get(e.get("admin")))
    L.append(u"| internet | %s |" % (u"sim" if e.get("internet") else u"não"))
    L.append(u"| Windows | %s |" % (e.get("windows") or {}).get("versao"))
    L.append(u"")
    ver = d.get("versoes") or {}
    if ver:
        L.append(u"## O que produziu este caso")
        L.append(u"")
        L.append(u"| | |")
        L.append(u"|---|---|")
        L.append(u"| app | %s |" % (ver.get("app") or u"não declarada"))
        mods = ver.get("modelos") or {}
        for k in sorted(mods):
            if mods[k]:
                L.append(u"| %s | %s |" % (k, mods[k]))
        if ver.get("tasks"):
            L.append(u"| tasks | %s |" % u", ".join(ver["tasks"]))
        L.append(u"")
    L.append(u"## A série")
    L.append(u"")
    for k in sorted(s):
        L.append(u"- **%s:** %s" % (k, s[k]))
    L.append(u"")
    ex = d.get("execucao") or {}
    if ex:
        L.append(u"## Como rodou")
        L.append(u"")
        for k in sorted(ex):
            if k == "fallbacks":
                continue
            if k == "recorte_no_corpo" and isinstance(ex[k], dict):
                L.append(u"- **%s:** %s" % (k, u"; ".join(
                    u"%s %s%s" % (t, (v or {}).get("estado"),
                                  (u" (%s)" % v["motivo"])
                                  if (v or {}).get("motivo") else u"")
                    for t, v in sorted(ex[k].items()))))
                continue
            L.append(u"- **%s:** %s" % (k, u"não informado" if ex[k] is None
                                        else ex[k]))
        fb = ex.get("fallbacks") or []
        L.append(u"- **fallbacks:** %s" % (u"nenhum" if not fb else u""))
        for x in fb:
            L.append(u"  - %s" % x)
        L.append(u"")
    L += _narrativa_do_processamento(d.get("processamento") or {})
    if d.get("etapas"):
        L.append(u"## O que levou tempo")
        L.append(u"")
        L.append(u"| etapa | segundos |")
        L.append(u"|---|---|")
        _por_nome = dict((x.get("etapa"), x) for x in d["etapas"]
                         if isinstance(x, dict))

        def _nivel(x):
            n, vistos = 0, set()
            while isinstance(x, dict) and x.get("parte_de") and n < 5:
                pai = x.get("parte_de")
                if pai in vistos:
                    break
                vistos.add(pai)
                n += 1
                x = _por_nome.get(pai)
            return n
        tem_passo = False
        for x in d["etapas"]:
            nv = _nivel(x)
            tem_passo = tem_passo or nv > 0
            L.append(u"| %s%s | %s |" % (u"↳" * nv + (u" " if nv else u""),
                                         x.get("etapa"),
                                         x.get("segundos", u"—")))
        if tem_passo:
            L.append(u"")
            L.append(u"As linhas com ↳ são PASSOS da etapa de cima (`parte_de` "
                     u"no caso.json): somar a coluna conta a mesma cadeia mais "
                     u"de uma vez.")
        L.append(u"")
    ach = d.get("achados") or []
    if ach:
        L.append(u"## Os %d achado(s)" % len(ach))
        L.append(u"")
        por = {}
        for a in ach:
            por.setdefault(a.get("tipo", u"?"), []).append(a)
        for tipo in sorted(por):
            L.append(u"### %s (%d)" % (tipo, len(por[tipo])))
            L.append(u"")
            for a in por[tipo]:
                nums = u" · ".join(u"%s=%s" % (k, v) for k, v in sorted(a.items())
                                   if k not in ("tipo", "detalhe"))
                L.append(u"- %s%s" % (a.get("detalhe") or u"—",
                                      (u"  (%s)" % nums) if nums else u""))
            L.append(u"")
    if r:
        L.append(u"## O que saiu")
        L.append(u"")
        for k in sorted(r):
            if k in ("ok", "erro"):
                continue
            L.append(u"- **%s:** %s" % (k, r[k]))
        L.append(u"")
    L.append(u"---")
    L.append(u"")
    L.append(u"*Registro do Radioterapia.AI, versão %d do esquema. Sem "
             u"identificação de paciente: o pseudônimo é estável dentro desta "
             u"instalação e não é reversível fora dela.*" % VERSAO_REGISTRO)
    return u"\n".join(L)


class Coletor(object):

    PADROES = (
        ("sobreposicao", ("SOBREPOSICAO:",)),
        ("suspeita", ("SUSPEITA:",)),
        ("cortada_pelo_campo", ("cortadas pelo campo",)),
        ("margem_de_oar", ("margem de OAR em",)),
        ("refino_por_hu", ("refino por densidade",)),
        ("recorte_de_oar", ("recorte de OAR", "recortada em")),
        ("sustentacao", ("sustentacao:",)),
        ("parede_toracica", ("parede toracica:",)),
        ("coracao_rt", ("coracao de radioterapia:",)),
        ("conjunto", ("conjuntos gravados",)),
        ("derivada", ("derivadas de", "NAO DERIVADO")),
        ("fallback", None),
        ("ambiente", ("ERRO", "FALHOU", "nao consegui")),
    )

    def __init__(self, log=None, teto_linhas=6000):
        self._log = log
        self.linhas = []
        self.teto = int(teto_linhas)

    def __call__(self, msg):
        try:
            t = str(msg)
            if len(self.linhas) < self.teto:
                self.linhas.append(t)
            elif len(self.linhas) == self.teto:
                self.linhas.append(u"[... log truncado em %d linhas ...]"
                                   % self.teto)
        except Exception:
            pass
        if self._log:
            try:
                self._log(msg)
            except Exception:
                pass

    def texto(self):
        return u"\n".join(self.linhas)

    def achados(self):
        fora = []
        for l in self.linhas:
            n = l.strip()
            for tipo, marcas in self.PADROES:
                casou = (e_fallback(n) if marcas is None
                         else any(m in n for m in marcas))
                if casou:
                    fora.append({"tipo": tipo, "detalhe": n[:400]})
                    break
        return fora

    def fallbacks(self):
        return achar_fallbacks(self.linhas)


FALLBACKS = (
    "refazendo a task inteira em cpu",
    "saida aproveitada",
    "moving results arrays to cpu",
    "base anatomica:",
)


def e_fallback(linha):
    baixo = str(linha or "").lower()
    return any(m in baixo for m in FALLBACKS)


def achar_fallbacks(linhas, teto=40):
    fora, vistos = [], set()
    for l in linhas or ():
        n = str(l or "").strip()
        if not n or not e_fallback(n):
            continue
        chave = re.sub(r"^\s*(\[[^\]]*\]\s*)+", "", n).strip().lower()
        if chave in vistos:
            continue
        vistos.add(chave)
        fora.append(n[:400])
        if len(fora) >= teto:
            fora.append(u"[... mais fallbacks omitidos (teto %d) ...]" % teto)
            break
    return fora


def do_job(job):
    fora = {}
    try:
        j = dict(job or {})
        if j.get("plano"):
            fora["plano"] = dict(j["plano"])
        if j.get("partes") is not None:
            fora["partes"] = [dict(p) if isinstance(p, dict) else p
                              for p in (j.get("partes") or [])]
        if j.get("recorte_no_corpo"):
            fora["recorte_no_corpo"] = dict(
                (str(t), dict(d or {}))
                for t, d in dict(j["recorte_no_corpo"]).items())
    except Exception as e:
        fora["job_ilegivel"] = type(e).__name__
    return fora


def recorte_que_valeu(por_task):
    if not por_task:
        return None
    fora = {}
    for task, d in sorted(dict(por_task).items()):
        d = dict(d or {})
        fora[str(task)] = {"estado": str(d.get("estado") or u"?"),
                           "motivo": str(d.get("motivo") or u"")[:200],
                           "falta_peso": bool(d.get("falta_peso"))}
    return fora


def nota_do_tempo_por_parte(partes, job_ilegivel=u""):
    if partes is not None:
        return u""
    if job_ilegivel:
        return (u"o job do motor nao pode ser lido (%s): o tempo por parte "
                u"nao foi guardado" % job_ilegivel)
    return (u"nenhuma parte vista pelo motor (task de rede unica, ou a serie "
            u"caiu antes da primeira parte)")


def execucao_do_motor(do_job_, recorte_pedido=None):
    d = dict(do_job_ or {})
    plano = dict(d.get("plano") or {})
    partes = d.get("partes")
    return {
        "recorte_no_corpo_pedido": (None if recorte_pedido is None
                                    else bool(recorte_pedido)),
        "recorte_no_corpo": recorte_que_valeu(d.get("recorte_no_corpo")),
        "modo": plano.get("modo"),
        "modo_do_plano": plano.get("modo_do_plano"),
        "recuo_cpu": (dict(plano["recuo_cpu"]) if plano.get("recuo_cpu")
                      else None),
        "motivo_do_modo": plano.get("motivo"),
        "placa": plano.get("placa"),
        "vram_livre_inicio_mb": plano.get("vram_livre_mb"),
        "vram_total_mb": plano.get("vram_total_mb"),
        "tempo_por_parte": partes,
        "tempo_por_parte_nota": nota_do_tempo_por_parte(
            partes, d.get("job_ilegivel") or u""),
    }


MEDIDAS_TECNICAS = ("forma_zyx", "espacamento_zyx_mm", "fov_mm",
                    "cobertura_z_mm", "medida_falhou")


def medidas_da_imagem(ref, cortes):
    d = {"cortes": int(cortes or 0)}
    try:
        tam = ref.GetSize()
        esp = ref.GetSpacing()
        d["forma_zyx"] = [int(tam[2]), int(tam[1]), int(tam[0])]
        d["espacamento_zyx_mm"] = [round(float(esp[2]), 3),
                                   round(float(esp[1]), 3),
                                   round(float(esp[0]), 3)]
        d["espessura_mm"] = round(float(esp[2]), 2)
        d["fov_mm"] = round(float(tam[0]) * float(esp[0]), 1)
        d["cobertura_z_mm"] = round(float(tam[2]) * float(esp[2]), 1)
    except Exception as e:
        d["medida_falhou"] = type(e).__name__
    return d


def dispositivo_da_task(job, task, dev):
    try:
        p = ((job or {}).get("planos") or {}).get(task) or {}
        if p.get("modo"):
            return str(p["modo"])
    except Exception:
        pass
    return str(dev or "")


def etapa_da_task(task, segundos, maquina, dispositivo, falhou=False):
    e = {"etapa": u"TS %s" % task, "task": task,
         "segundos": float(segundos or 0.0),
         "maquina": str(maquina or u""), "dispositivo": str(dispositivo or u"")}
    if falhou:
        e["falhou"] = True
    return e


def etapas_do_done(etapas):
    fora = []
    for e in (etapas or ()):
        try:
            d = dict((k, e.get(k)) for k in
                     ("etapa", "task", "maquina", "dispositivo")
                     if e.get(k) is not None)
            d["segundos"] = int(e.get("segundos") or 0)
            fora.append(d)
        except Exception:
            continue
    return fora


def motores_que_desenharam(niveis=None, extras=None):
    fora = set()
    if niveis:
        fora.add(u"hnlnl")
    try:
        for c in dict((extras or {}).get("origem") or {}).values():
            if c:
                fora.add(u"%s" % c)
    except Exception:
        pass
    return sorted(fora)


def campos_do_done(modalidade=None, tasks_da_serie=(), plano=None,
                   dispositivo=None, gravados=(), travamentos=(), regioes=(),
                   etapas=(), protocolos=(), tasks_sem_estrutura=(),
                   faltou=(), tasks_do_cache=(), receita_pos=u"",
                   cache_das_tasks=None, motores_fora_do_ts=()):
    try:
        _pl = dict(plano or {}).get("modo")
    except Exception:
        _pl = None
    _prot = [u"%s" % p for p in (protocolos or ()) if p]
    _sem = [{"task": u"%s" % (x.get("task") or u""),
             "motivo": u"%s" % (x.get("motivo") or u"")}
            for x in (tasks_sem_estrutura or ()) if isinstance(x, dict)]
    _falt = [{"estrutura": u"%s" % (x.get("estrutura") or u""),
              "porque": u"%s" % (x.get("porque") or u"")}
             for x in (faltou or ()) if isinstance(x, dict)]
    _cache = [u"%s" % t for t in (tasks_do_cache or ()) if t]
    _motores = sorted(set(u"%s" % m for m in (motores_fora_do_ts or ())
                          if m))
    _rede = _rede_dos_niveis() if u"hnlnl" in _motores else None
    _chaves = dict((u"%s" % t, u"%s" % c) for t, c in
                   dict(cache_das_tasks or {}).items()
                   if t and c and re.match(r"^[0-9a-f]{64}$", u"%s" % c))
    return {
        "modalidade": u"%s" % (modalidade or u""),
        "tasks_da_serie": [u"%s" % t for t in (tasks_da_serie or ()) if t],
        "plano_dispositivo": u"%s" % (_pl or dispositivo or u""),
        "gravados": [u"%s" % g for g in (gravados or ()) if g],
        "travamentos": [
            {"task": u"%s" % (x.get("task") or u""),
             "motivo": u"%s" % (x.get("motivo") or u""),
             "retomada": u"%s" % (x.get("retomada") or u"")}
            for x in (travamentos or ()) if isinstance(x, dict)],
        "regioes": [u"%s" % r for r in (regioes or ()) if r],
        "etapas": etapas_do_done(etapas),
        **({"protocolos": _prot} if _prot else {}),
        **({"tasks_sem_estrutura": _sem} if _sem else {}),
        **({"faltou": _falt} if _falt else {}),
        **({"tasks_do_cache": _cache} if _cache else {}),
        **({"receita_pos": u"%s" % receita_pos} if receita_pos else {}),
        **({"cache_das_tasks": _chaves} if _chaves else {}),
        **({"motores_fora_do_ts": _motores} if _motores else {}),
        **({"rede_dos_niveis": _rede} if _rede else {})}


def _rede_dos_niveis():
    try:
        import radai_hnlnl
        return u"%s" % radai_hnlnl.rede_dos_niveis()
    except Exception:
        return None


def faltou_da_serie(tasks_falharam=(), nao_sairam=(),
                    estruturas_da_task=None, saidas_da_construcao=None,
                    motores_falharam=(), estruturas_do_motor=None):
    fora, vistos = [], set()

    def _por(estrutura, porque):
        if estrutura and estrutura not in vistos:
            vistos.add(estrutura)
            fora.append({"estrutura": u"%s" % estrutura,
                         "porque": u"%s" % porque})
    falhas = [f for f in (tasks_falharam or ()) if isinstance(f, dict)
              and f.get("task")]
    for f in falhas:
        t = u"%s" % f["task"]
        porque = u"%s: %s" % (t, f.get("classe") or u"falhou")
        nomes = []
        if estruturas_da_task is not None:
            try:
                nomes = list(estruturas_da_task(t) or ())
            except Exception:
                nomes = []
        for n in nomes or [u"rotulos de %s" % t]:
            _por(n, porque)
    for item in (nao_sairam or ()):
        try:
            cod, motivo = item[0], u"%s" % item[1]
        except Exception:
            continue
        culpada = [f for f in falhas if u"%s" % f["task"] in motivo]
        if not culpada:
            continue
        porque = u"%s: %s (%s)" % (culpada[0]["task"],
                                   culpada[0].get("classe") or u"falhou",
                                   motivo[:160])
        saidas = []
        if saidas_da_construcao is not None:
            try:
                saidas = list(saidas_da_construcao(cod) or ())
            except Exception:
                saidas = []
        for n in saidas or [cod]:
            _por(n, porque)
    for f in (motores_falharam or ()):
        if not isinstance(f, dict) or not f.get("motor"):
            continue
        cod = u"%s" % f["motor"]
        porque = u"%s: %s" % (cod, f.get("classe") or u"falhou")
        if f.get("motivo"):
            # GUARDA: so o tipo da excecao; o texto dela pode trazer caminho
            porque += u" (%s)" % (u"%s" % f["motivo"]).split(u": ")[0][:160]
        nomes = []
        if estruturas_do_motor is not None:
            try:
                nomes = list(estruturas_do_motor(cod) or ())
            except Exception:
                nomes = []
        for n in nomes or [u"estruturas de %s" % cod]:
            _por(n, porque)
    return fora


def resultado_do_campo(info):
    info = info or {}
    fora = {}
    if info.get("classe"):
        fora["classe"] = u"%s" % info["classe"]
    if _ASSINATURA.match(u"%s" % (info.get("assinatura") or u"")):
        fora["assinatura"] = info["assinatura"]
    tipo = u"%s" % (info.get("tipo_da_falha") or u"")
    if _TIPO_DE_EXCECAO.match(tipo):
        fora["tipo_da_falha"] = tipo
    if info.get("em_espera"):
        fora["em_espera"] = True
    if info.get("classe") == u"inelegivel":
        fora["inelegivel"] = True
    for k in ("faltou", "tasks_sem_estrutura"):
        if info.get(k):
            fora[k] = [dict(x) for x in info[k] if isinstance(x, dict)]
    for k in ("regioes", "tasks_do_cache"):
        if info.get(k):
            fora[k] = [u"%s" % x for x in info[k]]
    return fora


def nomes_do_faltou(done_ou_lista):
    if isinstance(done_ou_lista, dict):
        done_ou_lista = done_ou_lista.get("faltou")
    fora = []
    for x in done_ou_lista or ():
        n = x.get("estrutura") if isinstance(x, dict) else None
        if n and u"%s" % n not in fora:
            fora.append(u"%s" % n)
    return fora


def linha_do_parcial(curto, faltou):
    nomes = [x.get("estrutura") for x in faltou or () if x.get("estrutura")]
    porques = []
    for x in faltou or ():
        p = (x.get("porque") or u"").split(u" (")[0]
        if p and p not in porques:
            porques.append(p)
    return u"PARCIAL serie %s: faltou %s — %s" % (
        curto, u", ".join(nomes[:12]) + (u" e mais %d" % (len(nomes) - 12)
                                        if len(nomes) > 12 else u""),
        u"; ".join(porques))


_TIPO_DE_EXCECAO = re.compile(r"^[A-Za-z_][\w.]{0,60}$")
_ASSINATURA = re.compile(r"^[0-9a-f]{10}$")


def _min(seg):
    try:
        return float(seg or 0) / 60.0
    except (TypeError, ValueError):
        return 0.0


def casos_do_periodo(base="", desde="", ate=""):
    pcasos = os.path.join(raiz(base), "casos")
    fora = []
    for c in listar_casos(base):
        d, porque = _ler_caso_conferido(pcasos, c)
        if porque or not isinstance(d, dict):
            continue
        quando = u"%s" % (d.get("abriu") or u"")
        if desde and quando[:19].replace(u"T", u" ") < desde:
            continue
        if ate and quando[:19].replace(u"T", u" ") > ate:
            continue
        fora.append(d)
    return fora


def resumo_do_turno(casos=None, desde="", ate="", base=""):
    if casos is None:
        casos = casos_do_periodo(base, desde, ate)
    sel = []
    for d in casos or ():
        q = (u"%s" % (d.get("abriu") or u""))[:19].replace(u"T", u" ")
        if desde and q < desde or ate and q > ate:
            continue
        sel.append((q, d))
    sel.sort(key=lambda x: x[0])
    entregues = parciais = nao_cont = falhas = espera = 0
    minutos = {}
    por_ass = {}
    por_task, picos = {}, {}
    linhas_series = []
    for i, (q, d) in enumerate(sel, start=1):
        r = d.get("resultado") or {}
        s = d.get("serie") or {}
        mod = (u"%s" % (s.get("modalidade") or u"?"))[:4]
        reg = u", ".join(u"%s" % x for x in (r.get("regioes") or ())
                         if _TIPO_DE_EXCECAO.match(u"%s" % x))
        cortes = s.get("cortes")
        rotulo = u"#%d %s %s%s cortes" % (
            i, mod, (reg + u", ") if reg else u"",
            int(cortes) if isinstance(cortes, (int, float)) else u"?")
        mins = _min(d.get("segundos_totais"))
        faltou = [x for x in (r.get("faltou") or ()) if isinstance(x, dict)]
        classe = u"%s" % (r.get("classe") or u"")
        if r.get("ok"):
            entregues += 1
            desfecho = u"entregue"
            if faltou:
                parciais += 1
                desfecho = u"parcial"
        elif classe == u"inelegivel" or r.get("inelegivel"):
            nao_cont += 1
            desfecho = u"nao contornavel"
        else:
            falhas += 1
            desfecho = u"falha"
            if r.get("em_espera"):
                espera += 1
        minutos[desfecho] = minutos.get(desfecho, 0.0) + mins
        ass = u"%s" % (r.get("assinatura") or u"")
        if not r.get("ok") and _ASSINATURA.match(ass):
            tipo = u"%s" % (r.get("tipo_da_falha") or u"")
            a = por_ass.setdefault(ass, {"n": 0, "primeira": q[11:16],
                                         "classe": classe,
                                         "tipo": tipo if _TIPO_DE_EXCECAO
                                         .match(tipo) else u""})
            a["n"] += 1
        extra = u""
        if faltou:
            extra = u" | faltou: %s" % u", ".join(
                (u"%s" % x.get("estrutura"))[:40] for x in faltou[:8]
                if _TIPO_DE_EXCECAO.match(u"%s" % x.get("estrutura") or u""))
        elif not r.get("ok"):
            extra = u" | %s%s" % (classe or u"falha",
                                  (u", assinatura %s" % ass)
                                  if _ASSINATURA.match(ass) else u"")
        linhas_series.append(u"  %s — %s, %.0f min%s"
                             % (rotulo, desfecho, mins, extra))
        for e in d.get("etapas") or ():
            nome = u"%s" % (e.get("etapa") or u"")
            if nome.startswith(u"TS ") and e.get("segundos") is not None:
                por_task.setdefault(nome, []).append(float(e["segundos"]))
        pico = (d.get("processamento") or {}).get("pico_memoria") or {}
        por_task_pico = pico.get("por_task")
        if isinstance(por_task_pico, dict):
            for t, v in por_task_pico.items():
                try:
                    picos[u"%s" % t] = max(picos.get(u"%s" % t, 0.0),
                                           float(v.get("ram_pct") or 0))
                except Exception:
                    continue
    L = [u"Resumo do turno %s a %s (Radioterapia.AI Local Suite; sem "
         u"identificacao de paciente)" % (desde or u"?", ate or u"?"),
         u"series vistas: %d | entregues: %d (%d parcial(is)) | nao "
         u"contornaveis: %d | falhas: %d (em espera: %d)"
         % (len(sel), entregues, parciais, nao_cont, falhas, espera),
         u"minutos por desfecho: %s" % (u" | ".join(
             u"%s %.0f" % (k, v) for k, v in sorted(minutos.items()))
             or u"—")]
    if por_ass:
        L.append(u"falhas por assinatura:")
        for a, v in sorted(por_ass.items(), key=lambda x: -x[1]["n"]):
            L.append(u"  %s: %d serie(s), %s%s, primeira as %s"
                     % (a, v["n"], v["classe"] or u"?",
                        (u", " + v["tipo"]) if v["tipo"] else u"",
                        v["primeira"] or u"?"))
    if por_task:
        L.append(u"tempo mediano por task:")
        for t, vs in sorted(por_task.items()):
            vs = sorted(vs)
            L.append(u"  %s: %.0f s (n=%d, %.0f a %.0f s)"
                     % (t, vs[len(vs) // 2], len(vs), vs[0], vs[-1]))
    if picos:
        L.append(u"pico de memoria da estacao por task (%% em uso): %s"
                 % u", ".join(u"%s %.0f" % (t, v)
                              for t, v in sorted(picos.items())))
    L.append(u"series:")
    L.extend(linhas_series)
    return u"\n".join(L)


def medir_serie(s, res=None, origem=u"rodar agora"):
    s = s or {}
    res = res or {}
    def _primeira(*valores):
        for v in valores:
            if v is not None:
                return v
        return None
    d = {"cortes": s.get("cortes") or res.get("cortes") or s.get("count"),
         "espessura_mm": _primeira(s.get("espessura_mm"), s.get("espessura"),
                                   res.get("espessura_mm"), s.get("esp_dec")),
         "origem": origem}
    m = str(s.get("modalidade") or res.get("modalidade")
            or s.get("modality") or "").strip().upper()
    d["modalidade"] = m or "CT"
    d["modalidade_origem"] = "dicom" if m else "presumida"
    for k in MEDIDAS_TECNICAS:
        if res.get(k) is not None:
            d[k] = res[k]
    nii = res.get("nifti") or res.get("nifti_entrada") or ""
    if nii:
        try:
            import radai_phase
            f, erro = radai_phase.fase(nii, estatisticas=res.get("statistics"))
            if f:
                d["fase_contraste"] = f.get("fase")
                d["com_contraste"] = f.get("com_contraste")
                d["fase_probabilidade"] = f.get("probabilidade")
            elif erro:
                d["fase_contraste"] = ""
                d["fase_nao_medida"] = erro[:120]
        except Exception as e:
            d["fase_nao_medida"] = u"%s" % type(e).__name__
    return d


def registrar_serie(uid, identificadores, serie, resultado, coletor=None,
                    etapas=(), achados=(), base="", papel="", tasks=(),
                    log=None, execucao=None, segundos_totais=None,
                    so_trocar=(), processamento=None):
    try:
        return _registrar_serie(uid, identificadores, serie, resultado,
                                coletor, etapas, achados, base, papel, tasks,
                                log, execucao, segundos_totais, so_trocar,
                                processamento)
    finally:
        try:
            _tirar_em_andamento(pseudonimo(uid, base), base=base)
        except Exception:
            pass


def _registrar_serie(uid, identificadores, serie, resultado, coletor,
                     etapas, achados, base, papel, tasks, log, execucao,
                     segundos_totais, so_trocar, processamento):
    try:
        c = Caso(uid=uid, identificadores=identificadores, base=base,
                 papel=papel, tasks=tasks, so_trocar=so_trocar)
        c.serie(**(serie or {}))
        if execucao:
            c.execucao(**dict(execucao))
        if processamento:
            c.processamento(**dict(processamento))
        for e in (etapas or ()):
            c.etapa(e.get("etapa", "?"), e.get("segundos"),
                    **{k: v for k, v in e.items()
                       if k not in ("etapa", "segundos")})
        for a in (achados or ()):
            c.achado(a.get("tipo", "?"), a.get("detalhe", ""),
                     **{k: v for k, v in a.items()
                        if k not in ("tipo", "detalhe")})
        if coletor is not None:
            for a in coletor.achados():
                c.achado(a["tipo"], a["detalhe"])
            c.log(coletor.texto())
        r = dict(resultado or {})
        c.resultado(bool(r.pop("ok", True)), r.pop("erro", ""), **r)
        return c.gravar(segundos=segundos_totais)
    except ContemIdentificacao as e:
        if log:
            try:
                log(u"o registro do caso NAO foi gravado: %s "
                    u"(o contorno nao foi afetado)" % e)
            except Exception:
                pass
        return ""
    except Exception as e:
        if log:
            try:
                log(u"nao consegui gravar o registro do caso (%s) — o "
                    u"contorno nao foi afetado" % str(e)[:140])
            except Exception:
                pass
        return ""


def listar_casos(base=""):
    d = os.path.join(raiz(base), "casos")
    try:
        return sorted(n for n in os.listdir(d)
                      if os.path.isdir(os.path.join(d, n)))
    except Exception:
        return []


def exportar(destino, base="", desde="", ate="", nota=u""):
    r = {"ok": False, "arquivo": "", "casos": 0, "recusados": [], "avisos": []}
    casos = listar_casos(base)
    if desde:
        casos = [c for c in casos if c[:10] >= desde]
    if ate:
        casos = [c for c in casos if c[:10] <= ate]
    if not casos:
        r["avisos"].append(u"não há caso no período pedido")
        return r
    praiz = raiz(base)
    pcasos = os.path.join(praiz, "casos")
    carimbo = datetime.now().strftime("%Y%m%d_%H%M")
    alvo = os.path.join(destino, "radai_registro_%s.zip" % carimbo)
    if not os.path.isdir(destino):
        os.makedirs(destino)

    bons = []
    lidos = {}
    for c in casos:
        d, porque = _ler_caso_conferido(pcasos, c)
        if porque:
            r["recusados"].append({"caso": c, "porque": porque})
            continue
        bons.append(c)
        lidos[c] = d

    if not bons:
        r["avisos"].append(u"nenhum caso passou na conferência")
        return r

    with zipfile.ZipFile(alvo, "w", zipfile.ZIP_DEFLATED) as z:
        pe = os.path.join(praiz, "estacao.json")
        if os.path.isfile(pe):
            z.write(pe, "estacao.json")
        else:
            try:
                z.writestr("estacao.json", json.dumps(
                    perfil_da_estacao("", base), ensure_ascii=False, indent=1))
            except Exception:
                r["avisos"].append(u"não consegui montar o perfil da estação")
        for c in bons:
            for nome in ("caso.json", "caso.md", "log.txt"):
                p = os.path.join(pcasos, c, nome)
                if nome == "caso.json" and _maquinas_por_pseudonimo(
                        lidos.get(c), base):
                    z.writestr("casos/%s/%s" % (c, nome), json.dumps(
                        lidos[c], ensure_ascii=False, indent=1))
                    continue
                if os.path.isfile(p):
                    z.write(p, "casos/%s/%s" % (c, nome))
        try:
            rel = relatorio_de_periodo(base=base, desde=desde, ate=ate,
                                       casos=bons)
            md, ht = relatorio_markdown(rel), relatorio_html(rel)
            conferir_relatorio(md)
            conferir_relatorio(ht)
            z.writestr("relatorio.md", md)
            z.writestr("relatorio.html", ht)
        except ContemIdentificacao as e:
            r["avisos"].append(u"o relatório de período ficou fora do "
                               u"pacote: %s" % e)
        except Exception as e:
            r["avisos"].append(u"não consegui montar o relatório de período "
                               u"(%s)" % type(e).__name__)
        z.writestr("LEIA-ME.md", _leiame(bons, r["recusados"], nota))

    with zipfile.ZipFile(alvo) as z:
        dentro = z.namelist()
        ruim = z.testzip()
    if ruim:
        os.remove(alvo)
        r["avisos"].append(u"o pacote saiu corrompido (%s) — apaguei" % ruim)
        return r
    vazado = [n for n in dentro if NOME_SEGREDO in n]
    if vazado:
        os.remove(alvo)
        r["avisos"].append(u"o segredo do pseudônimo entrou no pacote — apaguei")
        return r
    r["ok"] = True
    r["arquivo"] = alvo
    r["casos"] = len(bons)
    r["tamanho_kb"] = round(os.path.getsize(alvo) / 1024.0, 1)
    return r


def _leiame(casos, recusados, nota=u""):
    L = [u"# Registro do Radioterapia.AI",
         u"",
         u"%d caso(s), esquema versão %d." % (len(casos), VERSAO_REGISTRO),
         u"",
         u"## O que tem aqui",
         u"",
         u"- `estacao.json` — o retrato da máquina que produziu estes casos.",
         u"- `casos/<data>_<hora>_<pseudônimo>/caso.json` — o registro "
         u"estruturado de UMA tentativa (casos gravados até a v8.2 estão em "
         u"`casos/<data>_<pseudônimo>/`).",
         u"- `casos/.../caso.md` — a mesma coisa, para ler.",
         u"- `casos/.../log.txt` — o log completo, higienizado.",
         u"- `relatorio.md` e `relatorio.html` — o relatório do período: "
         u"casos, modos, tempo por etapa, remoções, falhas e travamentos.",
         u"",
         u"## O que NÃO tem, de propósito",
         u"",
         u"Nenhuma identificação de paciente: nem nome, nem registro, nem data",
         u"de nascimento, nem UID, nem caminho de pasta. O pseudônimo é estável",
         u"dentro da instalação que o gerou e **não é reversível fora dela** — a",
         u"chave que o produz nunca sai da estação.",
         u"",
         u"Toda estrutura contornada aqui é **sugestão não aprovada**. Revisão e",
         u"aprovação são ato médico humano.",
         u""]
    if recusados:
        L += [u"## %d caso(s) ficaram de fora" % len(recusados), u""]
        for x in recusados:
            L.append(u"- `%s` — %s" % (x["caso"], x["porque"]))
        L.append(u"")
    if nota:
        L += [u"## Nota de quem exportou", u"", str(nota), u""]
    return u"\n".join(L)


CAMPOS_PROIBIDOS = ("patientid", "patientname", "patient_name",
                    "patientbirthdate", "studyinstanceuid", "seriesinstanceuid",
                    "sopinstanceuid", "accessionnumber", "seriesdescription",
                    "studydescription")


def _ler_caso_conferido(pcasos, c):
    p = os.path.join(pcasos, c, "caso.json")
    try:
        with io.open(p, encoding="utf-8") as f:
            d = json.load(f)
    except Exception as e:
        return None, u"não abriu (%s)" % str(e)[:60]
    texto = json.dumps(d, ensure_ascii=False).lower()
    achou = [k for k in CAMPOS_PROIBIDOS if ('"%s"' % k) in texto]
    if achou:
        return None, u"campo proibido: %s" % ", ".join(achou)
    if re.search(r"[a-z]:\\\\|\\\\\\\\[a-z0-9_-]+\\\\", texto):
        return None, u"há caminho de sistema de arquivos"
    if not isinstance(d, dict):
        return None, u"não é um caso (esperava um objeto JSON)"
    return d, u""


VERSAO_RELATORIO = 1
_UID_NO_TEXTO = re.compile(r"(?<![0-9.])\d+(?:\.\d+){5,}(?![0-9.])")
_SEM_MODO = u"não declarado"


def _sem_uid(texto):
    return _UID_NO_TEXTO.sub(u"<uid>", str(texto or u""))


def conferir_relatorio(texto, identificadores=()):
    s = str(texto or u"")
    if identificadores:
        conferir_sem_identificacao(s, identificadores)
    if _CAMINHO.search(s):
        raise ContemIdentificacao(
            u"o relatório ia levar um caminho de sistema de arquivos — não "
            u"gravei")
    baixo = s.lower()
    achou = [k for k in CAMPOS_PROIBIDOS if k in baixo]
    if achou:
        raise ContemIdentificacao(
            u"o relatório ia levar o campo proibido %s — não gravei" % achou[0])
    if _UID_NO_TEXTO.search(s):
        raise ContemIdentificacao(
            u"o relatório ia levar um UID — não gravei")
    return True


def _estat(valores):
    v = sorted(float(x) for x in valores
               if isinstance(x, (int, float)) and not isinstance(x, bool))
    if not v:
        return {"n": 0}
    n = len(v)
    med = v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2.0
    p90 = v[min(n - 1, int(round(0.9 * (n - 1))))]
    return {"n": n, "mediana": round(med, 1), "p90": round(p90, 1),
            "min": round(v[0], 1), "max": round(v[-1], 1),
            "total": round(sum(v), 1)}


def _conta(dic, chave, n=1):
    chave = u"%s" % (chave,)
    dic[chave] = dic.get(chave, 0) + n


TETO_DA_TABELA = 40


def _ocorrencia(dic, chave, dia, versao):
    a = dic.setdefault(u"%s" % (chave,), {"n": 0, "primeira": u"",
                                         "ultima": u"", "versoes": []})
    a["n"] += 1
    dia = u"%s" % (dia or u"")
    if dia:
        a["primeira"] = min(a["primeira"] or dia, dia)
        a["ultima"] = max(a["ultima"], dia)
    if versao and versao not in a["versoes"]:
        a["versoes"].append(versao)
    return a


def _ocorrencias_em_lista(dic, campo):
    fora = []
    for k, a in sorted(dic.items(), key=lambda kv: (-kv[1]["n"], kv[0])):
        x = dict(a)
        x[campo] = k
        x["versoes"] = sorted(a.get("versoes") or [])
        fora.append(x)
    return fora[:TETO_DA_TABELA]


def _ler_indice(base=""):
    linhas, ruins = [], 0
    p = os.path.join(raiz(base), "indice.jsonl")
    try:
        with io.open(p, encoding="utf-8") as f:
            for l in f:
                if not l.strip():
                    continue
                try:
                    linhas.append(json.loads(l))
                except Exception:
                    ruins += 1
    except Exception:
        pass
    return linhas, ruins


def _no_periodo(dia, desde, ate):
    dia = str(dia or u"")[:10]
    return (not desde or dia >= desde) and (not ate or dia <= ate)


def relatorio_de_periodo(base="", desde="", ate="", casos=None):
    rel = {"versao_relatorio": VERSAO_RELATORIO,
           "gerado": datetime.now().astimezone().isoformat(timespec="seconds"),
           "desde": str(desde or u""), "ate": str(ate or u""),
           "casos": 0, "tentativas": 0, "indice_ilegivel": 0,
           "recusados": [], "concluidos": 0, "falharam": 0,
           "primeiro": u"", "ultimo": u"",
           "modos": {}, "origens": {}, "tempo_total": {"n": 0},
           "etapas": [], "passos": [], "estruturas": {"n": 0},
           "remocoes": {"total": 0, "por_regra": {}, "por_estrutura": []},
           "achados": {}, "falhas": [], "tasks_falharam": {},
           "travamentos": {"total": 0, "por_task": {}, "por_motivo": {},
                           "retomadas": {}},
           "clip_box": {}, "comparacao": {}, "oar_fora": {},
           "dispositivos": {}, "versoes": {"app": {}, "totalsegmentator": {}},
           "estacoes": [], "interrompidos": 0, "lista_interrompidos": [],
           "interrompidos_por_etapa": [], "falhas_recentes": [],
           "gerado_por": identidade_do_programa()}
    try:
        linhas, ruins = _ler_indice(base)
        rel["indice_ilegivel"] = ruins
        rel["tentativas"] = sum(
            1 for x in linhas
            if isinstance(x, dict) and _no_periodo(x.get("quando"), desde, ate)
            and (casos is None or x.get("pasta") in casos
                 or not x.get("pasta")))
        pcasos = os.path.join(raiz(base), "casos")
        nomes = listar_casos(base) if casos is None else list(casos)
        nomes = [c for c in nomes if _no_periodo(c, desde, ate)]
        totais, estruturas = [], []
        por_etapa, por_passo = {}, {}
        rem_estr, falhas = {}, {}
        por_motivo_trav, por_etapa_int, recentes = {}, {}, []
        estacoes = {}
        for c in nomes:
            d, porque = _ler_caso_conferido(pcasos, c)
            if porque:
                rel["recusados"].append({"caso": c, "porque": porque})
                continue
            rel["casos"] += 1
            dia = c[:10]
            rel["primeiro"] = min(rel["primeiro"] or dia, dia)
            rel["ultimo"] = max(rel["ultimo"], dia)
            r = d.get("resultado") or {}
            ex = d.get("execucao") or {}
            pr = d.get("processamento") or {}
            ver_c = d.get("versoes") or {}
            rot_ver = rotulo_da_versao(ver_c.get("app"), ver_c.get("build"))
            quando_c = (u"%s" % (d.get("abriu") or dia))[:16].replace(u"T",
                                                                     u" ")
            if r.get("ok"):
                rel["concluidos"] += 1
            elif r.get("interrompido"):
                rel["interrompidos"] += 1
                etapa = _sem_uid(sem_caminhos(
                    u"%s" % (r.get("ultima_etapa") or u"?")))[:80]
                _ocorrencia(por_etapa_int, etapa, dia, rot_ver)
                rel["lista_interrompidos"].append({
                    "pseudonimo": u"%s" % (d.get("pseudonimo") or u"?"),
                    "quando": quando_c, "versao": rot_ver,
                    "porta": u"%s" % (ex.get("origem") or _SEM_MODO),
                    "modo": u"%s" % (pr.get("modo") or _SEM_MODO),
                    "ultima_etapa": etapa,
                    "hora": (u"%s" % (r.get("hora_da_etapa") or u""))[11:16]})
                recentes.append((quando_c, {
                    "pseudonimo": u"%s" % (d.get("pseudonimo") or u"?"),
                    "quando": quando_c, "versao": rot_ver,
                    "porta": u"%s" % (ex.get("origem") or _SEM_MODO),
                    "modo": u"%s" % (pr.get("modo") or _SEM_MODO),
                    "motivo": u"interrompido na etapa «%s»" % etapa}))
            else:
                rel["falharam"] += 1
                motivo = _sem_uid(sem_caminhos(r.get("erro") or u"sem motivo "
                                               u"gravado"))[:160]
                _conta(falhas, motivo)
                _ocorrencia(rel.setdefault("_falhas_det", {}), motivo, dia,
                            rot_ver)
                recentes.append((quando_c, {
                    "pseudonimo": u"%s" % (d.get("pseudonimo") or u"?"),
                    "quando": quando_c, "versao": rot_ver,
                    "porta": u"%s" % (ex.get("origem") or _SEM_MODO),
                    "modo": u"%s" % (pr.get("modo") or _SEM_MODO),
                    "motivo": motivo[:90]}))
            _conta(rel["modos"], pr.get("modo") or _SEM_MODO)
            _conta(rel["origens"], ex.get("origem") or _SEM_MODO)
            _conta(rel["dispositivos"], ex.get("modo") or _SEM_MODO)
            totais.append(d.get("segundos_totais"))
            if isinstance(r.get("estruturas"), (int, float)):
                estruturas.append(r["estruturas"])
            for e in d.get("etapas") or []:
                if not isinstance(e, dict):
                    continue
                nome = u"%s" % (e.get("etapa") or u"?")
                if e.get("parte_de"):
                    chave = (nome, u"%s" % e["parte_de"])
                    por_passo.setdefault(chave, []).append(e.get("segundos"))
                else:
                    por_etapa.setdefault(nome, []).append(e.get("segundos"))
            for x in pr.get("tempos_por_passo") or []:
                if isinstance(x, dict):
                    chave = (u"%s" % (x.get("passo") or x.get("etapa") or u"?"),
                             u"(processamento)")
                    por_passo.setdefault(chave, []).append(x.get("segundos"))
            for x in pr.get("remocoes") or []:
                x = x if isinstance(x, dict) else {"nome": x}
                rel["remocoes"]["total"] += 1
                _conta(rel["remocoes"]["por_regra"], x.get("regra") or u"?")
                _conta(rem_estr, x.get("nome") or u"?")
            for a in d.get("achados") or []:
                if isinstance(a, dict):
                    _conta(rel["achados"], a.get("tipo") or u"?")
            for f in ex.get("tasks_falharam") or []:
                t = f.get("task") if isinstance(f, dict) else f
                _conta(rel["tasks_falharam"], t or u"?")
            for x in pr.get("travamentos") or []:
                x = x if isinstance(x, dict) else {"task": x}
                tv = rel["travamentos"]
                tv["total"] += 1
                _conta(tv["por_task"], x.get("task") or u"?")
                _mot_tv = _sem_uid(sem_caminhos(x.get("motivo") or u"?"))[:120]
                _conta(tv["por_motivo"], _mot_tv)
                _ocorrencia(por_motivo_trav, _mot_tv, dia, rot_ver)
                _conta(tv["retomadas"], x.get("retomada") or _SEM_MODO)
            for t, cb in sorted((pr.get("clip_box") or {}).items()):
                cb = cb if isinstance(cb, dict) else {}
                acc = rel["clip_box"].setdefault(
                    u"%s" % t, {"casos": 0, "usado": 0, "ganho_s": []})
                acc["casos"] += 1
                if cb.get("usado"):
                    acc["usado"] += 1
                if isinstance(cb.get("ganho_s"), (int, float)):
                    acc["ganho_s"].append(cb["ganho_s"])
            for k, v in sorted((pr.get("comparacao") or {}).items()):
                if v:
                    _conta(rel["comparacao"], k)
            for k in pr.get("oar_fora") or []:
                _conta(rel["oar_fora"], k)
            ver = d.get("versoes") or {}
            _conta(rel["versoes"]["app"], ver.get("app") or _SEM_MODO)
            ts = (ver.get("modelos") or {}).get("totalsegmentator")
            if ts:
                _conta(rel["versoes"]["totalsegmentator"], ts)
            es = d.get("estacao") or {}
            m = u"%s" % (es.get("maquina") or u"?")
            acc = estacoes.setdefault(m, {"maquina": m, "casos": 0})
            acc["casos"] += 1
            mem = es.get("memoria") or {}
            if es.get("nucleos"):
                acc["nucleos"] = es.get("nucleos")
            if mem.get("total_gb"):
                acc["memoria_gb"] = mem.get("total_gb")
            placas = (es.get("gpu") or {}).get("placas") or []
            if placas:
                acc["gpu"] = u", ".join(u"%s" % p for p in placas)[:120]
            if es.get("papel_declarado"):
                acc["papel"] = u"%s" % es["papel_declarado"]
        rel["tempo_total"] = _estat(totais)
        rel["estruturas"] = _estat(estruturas)
        rel["etapas"] = [dict(_estat(v), etapa=k)
                         for k, v in sorted(por_etapa.items())]
        rel["passos"] = [dict(_estat(v), etapa=k[0], parte_de=k[1])
                         for k, v in sorted(por_passo.items())]
        rel["remocoes"]["por_estrutura"] = sorted(
            rem_estr.items(), key=lambda kv: (-kv[1], kv[0]))[:25]
        _det = rel.pop("_falhas_det", {})
        rel["falhas"] = [dict({"motivo": k, "n": v}, **_det.get(k, {}))
                         for k, v in
                         sorted(falhas.items(), key=lambda kv: (-kv[1], kv[0]))]
        rel["travamentos"]["por_motivo_detalhe"] = _ocorrencias_em_lista(
            por_motivo_trav, "motivo")
        rel["interrompidos_por_etapa"] = _ocorrencias_em_lista(
            por_etapa_int, "etapa")
        rel["lista_interrompidos"].sort(key=lambda x: x["quando"],
                                        reverse=True)
        rel["lista_interrompidos"] = rel["lista_interrompidos"][:TETO_DA_TABELA]
        recentes.sort(key=lambda x: x[0], reverse=True)
        rel["falhas_recentes"] = [x for _q, x in recentes[:TETO_DA_TABELA]]
        for t, acc in rel["clip_box"].items():
            acc["ganho_s"] = _estat(acc["ganho_s"])
        rel["estacoes"] = sorted(estacoes.values(),
                                 key=lambda e: (-e["casos"], e["maquina"]))
    except Exception as e:
        rel["erro"] = u"%s" % type(e).__name__
    return rel


def _tabela_de_contagem(dic, cab=(u"", u"casos")):
    L = [u"| %s | %s |" % cab, u"|---|---|"]
    for k, v in sorted(dic.items(), key=lambda kv: (-kv[1], kv[0])):
        L.append(u"| %s | %s |" % (k, v))
    return L


def relatorio_markdown(rel):
    rel = rel or {}
    L = [u"# Relatório de período — Radioterapia.AI", u""]
    per = (u"de %s a %s" % (rel.get("desde") or rel.get("primeiro") or u"o início",
                            rel.get("ate") or rel.get("ultimo") or u"hoje"))
    gp = rel.get("gerado_por") or {}
    L += [u"- **período:** %s" % per,
          u"- **gerado em:** %s" % rel.get("gerado", u""),
          u"- **gerado por:** versão %s do app" % rotulo_da_versao(
              gp.get("app"), gp.get("build")),
          u"- **casos lidos:** %s (tentativas no índice: %s)"
          % (rel.get("casos", 0), rel.get("tentativas", 0)),
          u"- **concluídos:** %s · **falharam:** %s · **interrompidos:** %s"
          % (rel.get("concluidos", 0), rel.get("falharam", 0),
             rel.get("interrompidos", 0))]
    if rel.get("recusados"):
        L.append(u"- **ficaram fora (a conferência recusou):** %d"
                 % len(rel["recusados"]))
    L.append(u"")
    if not rel.get("casos"):
        L += [u"Nenhum caso no período pedido.", u""]
        return u"\n".join(L + _rodape_md())
    L += [u"## Modos de processamento", u""]
    L += _tabela_de_contagem(rel.get("modos") or {}, (u"modo", u"casos"))
    L += [u"", u"Portas: " + (u", ".join(
        u"%s %s" % (k, v) for k, v in sorted((rel.get("origens") or {}).items()))
        or u"—"), u""]
    L += [u"## Tempo por etapa", u""]
    tt = rel.get("tempo_total") or {}
    if tt.get("n"):
        L.append(u"Série inteira: mediana %s s, p90 %s s, máximo %s s (%s casos)."
                 % (tt["mediana"], tt["p90"], tt["max"], tt["n"]))
        L.append(u"")
    L += [u"| etapa | casos | mediana (s) | p90 (s) | máximo (s) |",
          u"|---|---|---|---|---|"]
    for e in rel.get("etapas") or []:
        if e.get("n"):
            L.append(u"| %s | %s | %s | %s | %s |" % (
                e["etapa"], e["n"], e["mediana"], e["p90"], e["max"]))
    if rel.get("passos"):
        L += [u"", u"Passos (parte de uma etapa — não se somam a ela):", u"",
              u"| passo | parte de | casos | mediana (s) |", u"|---|---|---|---|"]
        for e in rel["passos"]:
            if e.get("n"):
                L.append(u"| %s | %s | %s | %s |" % (
                    e["etapa"], e["parte_de"], e["n"], e["mediana"]))
    L.append(u"")
    es = rel.get("estruturas") or {}
    L += [u"## Estruturas entregues", u""]
    L.append(u"Mediana %s por caso (mínimo %s, máximo %s, %s casos)."
             % (es.get("mediana"), es.get("min"), es.get("max"), es.get("n"))
             if es.get("n") else u"Nenhum caso registrou a contagem.")
    L.append(u"")
    rm = rel.get("remocoes") or {}
    L += [u"## Remoções (regras R1 a R4)", u"",
          u"Total: %s." % rm.get("total", 0), u""]
    if rm.get("total"):
        L += _tabela_de_contagem(rm.get("por_regra") or {}, (u"regra", u"remoções"))
        L += [u"", u"| estrutura | remoções |", u"|---|---|"]
        for k, v in rm.get("por_estrutura") or []:
            L.append(u"| %s | %s |" % (k, v))
        L.append(u"")
    L += [u"## Suspeitas e achados do processamento", u""]
    L += (_tabela_de_contagem(rel["achados"], (u"tipo", u"ocorrências"))
          if rel.get("achados") else [u"Nenhum."])
    L.append(u"")
    L += [u"## Falhas", u""]
    if rel.get("falhas"):
        L += [u"| motivo | casos | primeira | última | versões do app |",
              u"|---|---|---|---|---|"]
        for f in rel["falhas"]:
            L.append(u"| %s | %s | %s | %s | %s |" % (
                f["motivo"].replace(u"|", u"/"), f["n"],
                f.get("primeira") or u"—", f.get("ultima") or u"—",
                _versoes_em_texto(f.get("versoes"))))
    else:
        L.append(u"Nenhuma série falhou.")
    if rel.get("tasks_falharam"):
        L += [u"", u"Tasks que falharam sem derrubar a série:", u""]
        L += _tabela_de_contagem(rel["tasks_falharam"], (u"task", u"vezes"))
    L.append(u"")
    tv = rel.get("travamentos") or {}
    L += [u"## Travamentos", u"", u"Total: %s." % tv.get("total", 0), u""]
    if tv.get("total"):
        L += _tabela_de_contagem(tv.get("por_task") or {}, (u"task", u"vezes"))
        L += [u"", u"| motivo | vezes | primeira | última | versões do app |",
              u"|---|---|---|---|---|"]
        for f in tv.get("por_motivo_detalhe") or []:
            L.append(u"| %s | %s | %s | %s | %s |" % (
                f["motivo"].replace(u"|", u"/"), f["n"],
                f.get("primeira") or u"—", f.get("ultima") or u"—",
                _versoes_em_texto(f.get("versoes"))))
        L += [u""] + _tabela_de_contagem(tv.get("retomadas") or {},
                                         (u"retomada", u"vezes"))
        L.append(u"")
    L += [u"## Casos interrompidos", u"",
          u"Total: %s (o programa parou no meio da série; o caso foi fechado "
          u"ao abrir de novo)." % rel.get("interrompidos", 0), u""]
    if rel.get("interrompidos_por_etapa"):
        L += [u"| última etapa | casos | primeira | última | versões do app |",
              u"|---|---|---|---|---|"]
        for f in rel["interrompidos_por_etapa"]:
            L.append(u"| %s | %s | %s | %s | %s |" % (
                f["etapa"].replace(u"|", u"/"), f["n"],
                f.get("primeira") or u"—", f.get("ultima") or u"—",
                _versoes_em_texto(f.get("versoes"))))
        L += [u"", u"| caso (pseudônimo) | quando | versão | porta | modo "
                  u"| última etapa | às |", u"|---|---|---|---|---|---|---|"]
        for x in rel.get("lista_interrompidos") or []:
            L.append(u"| %s | %s | %s | %s | %s | %s | %s |" % (
                x["pseudonimo"], x["quando"], x["versao"], x["porta"],
                x["modo"], x["ultima_etapa"].replace(u"|", u"/"),
                x.get("hora") or u"—"))
        L.append(u"")
    L += [u"## Casos recentes com falha", u""]
    if rel.get("falhas_recentes"):
        L += [u"| caso (pseudônimo) | quando | versão | porta | modo "
              u"| motivo |", u"|---|---|---|---|---|---|"]
        for x in rel["falhas_recentes"]:
            L.append(u"| %s | %s | %s | %s | %s | %s |" % (
                x["pseudonimo"], x["quando"], x["versao"], x["porta"],
                x["modo"], x["motivo"].replace(u"|", u"/")))
    else:
        L.append(u"Nenhuma.")
    L.append(u"")
    if rel.get("clip_box"):
        L += [u"## Recorte por task (clip-box)", u"",
              u"| task | casos | usado | ganho mediano (s) |", u"|---|---|---|---|"]
        for t, acc in sorted(rel["clip_box"].items()):
            L.append(u"| %s | %s | %s | %s |" % (
                t, acc["casos"], acc["usado"],
                (acc.get("ganho_s") or {}).get("mediana", u"—")))
        L.append(u"")
    if rel.get("comparacao") or rel.get("oar_fora"):
        L += [u"## O que foi pedido no PERSONALIZADO", u""]
        if rel.get("comparacao"):
            L += [u"- comparação: " + u", ".join(
                u"%s %s" % kv for kv in sorted(rel["comparacao"].items()))]
        if rel.get("oar_fora"):
            L += [u"- tiradas do OAR: " + u", ".join(
                u"%s %s" % kv for kv in sorted(rel["oar_fora"].items()))]
        L.append(u"")
    L += [u"## Dispositivos", u""]
    L += _tabela_de_contagem(rel.get("dispositivos") or {}, (u"dispositivo", u"casos"))
    L += [u"", u"## Versões", u""]
    L += _tabela_de_contagem((rel.get("versoes") or {}).get("app") or {},
                             (u"versão do app", u"casos"))
    if (rel.get("versoes") or {}).get("totalsegmentator"):
        L += [u""] + _tabela_de_contagem(rel["versoes"]["totalsegmentator"],
                                         (u"TotalSegmentator", u"casos"))
    L += [u"", u"## Estações", u"",
          u"| estação (pseudônimo) | casos | núcleos | memória (GB) | GPU | papel |",
          u"|---|---|---|---|---|---|"]
    for e in rel.get("estacoes") or []:
        L.append(u"| %s | %s | %s | %s | %s | %s |" % (
            e.get("maquina"), e.get("casos"), e.get("nucleos", u"—"),
            e.get("memoria_gb", u"—"), e.get("gpu", u"nenhuma"),
            e.get("papel", u"—")))
    L.append(u"")
    return u"\n".join(L + _rodape_md())


def _versoes_em_texto(versoes):
    v = sorted(u"%s" % x for x in (versoes or ()) if x)
    return u", ".join(v) if v else u"—"


def _rodape_md():
    return [u"---", u"",
            u"*Relatório gerado do registro de casos, sem identificação de "
            u"paciente (nem nome, nem registro, nem data de nascimento, nem "
            u"identificador de série, nem pasta). Toda estrutura contornada é "
            u"sugestão não aprovada; revisão e aprovação são ato médico "
            u"humano.*", u""]


def relatorio_html(rel):
    import html as _h
    esc = lambda x: _h.escape(u"%s" % (x,), quote=True)
    rel = rel or {}

    def tabela(cab, linhas):
        t = [u"<div class='tab'><table><thead><tr>"]
        t += [u"<th>%s</th>" % esc(c) for c in cab]
        t.append(u"</tr></thead><tbody>")
        for ln in linhas:
            t.append(u"<tr>" + u"".join(u"<td>%s</td>" % esc(c) for c in ln)
                     + u"</tr>")
        t.append(u"</tbody></table></div>")
        return u"".join(t)

    def contagem(dic):
        return sorted((dic or {}).items(), key=lambda kv: (-kv[1], kv[0]))

    per = (u"de %s a %s" % (rel.get("desde") or rel.get("primeiro") or u"o início",
                            rel.get("ate") or rel.get("ultimo") or u"hoje"))
    C = []
    gp = rel.get("gerado_por") or {}
    C.append(u"<h1>Relatório de período</h1>")
    C.append(u"<p class='sub'>Radioterapia.AI · %s · gerado em %s · gerado "
             u"pela versão %s do app</p>"
             % (esc(per), esc(rel.get("gerado", u"")),
                esc(rotulo_da_versao(gp.get("app"), gp.get("build")))))
    C.append(u"<div class='fichas'>")
    for rot, v in ((u"casos lidos", rel.get("casos", 0)),
                   (u"tentativas no índice", rel.get("tentativas", 0)),
                   (u"concluídos", rel.get("concluidos", 0)),
                   (u"falharam", rel.get("falharam", 0)),
                   (u"interrompidos", rel.get("interrompidos", 0)),
                   (u"remoções", (rel.get("remocoes") or {}).get("total", 0)),
                   (u"travamentos", (rel.get("travamentos") or {}).get("total", 0))):
        C.append(u"<div class='ficha'><b>%s</b><span>%s</span></div>"
                 % (esc(v), esc(rot)))
    C.append(u"</div>")
    if not rel.get("casos"):
        C.append(u"<p>Nenhum caso no período pedido.</p>")
    else:
        C.append(u"<h2>Modos de processamento</h2>")
        C.append(tabela((u"modo", u"casos"), contagem(rel.get("modos"))))
        C.append(u"<p class='sub'>Portas: %s</p>" % esc(u", ".join(
            u"%s %s" % kv for kv in sorted((rel.get("origens") or {}).items()))))
        C.append(u"<h2>Tempo por etapa</h2>")
        tt = rel.get("tempo_total") or {}
        if tt.get("n"):
            C.append(u"<p>Série inteira: mediana %s s, p90 %s s, máximo %s s "
                     u"(%s casos).</p>" % (esc(tt["mediana"]), esc(tt["p90"]),
                                           esc(tt["max"]), esc(tt["n"])))
        C.append(tabela((u"etapa", u"casos", u"mediana (s)", u"p90 (s)",
                         u"máximo (s)"),
                        [(e["etapa"], e["n"], e["mediana"], e["p90"], e["max"])
                         for e in rel.get("etapas") or [] if e.get("n")]))
        if rel.get("passos"):
            C.append(u"<p class='sub'>Passos (parte de uma etapa — não se "
                     u"somam a ela)</p>")
            C.append(tabela((u"passo", u"parte de", u"casos", u"mediana (s)"),
                            [(e["etapa"], e["parte_de"], e["n"], e["mediana"])
                             for e in rel["passos"] if e.get("n")]))
        es = rel.get("estruturas") or {}
        C.append(u"<h2>Estruturas entregues</h2>")
        C.append(u"<p>%s</p>" % esc(
            u"Mediana %s por caso (mínimo %s, máximo %s, %s casos)."
            % (es.get("mediana"), es.get("min"), es.get("max"), es.get("n"))
            if es.get("n") else u"Nenhum caso registrou a contagem."))
        rm = rel.get("remocoes") or {}
        C.append(u"<h2>Remoções (regras R1 a R4)</h2>")
        C.append(u"<p>Total: %s.</p>" % esc(rm.get("total", 0)))
        if rm.get("total"):
            C.append(tabela((u"regra", u"remoções"), contagem(rm.get("por_regra"))))
            C.append(tabela((u"estrutura", u"remoções"),
                            rm.get("por_estrutura") or []))
        C.append(u"<h2>Suspeitas e achados do processamento</h2>")
        C.append(tabela((u"tipo", u"ocorrências"), contagem(rel.get("achados")))
                 if rel.get("achados") else u"<p>Nenhum.</p>")
        _cab_oc = (u"casos", u"primeira", u"última", u"versões do app")

        def _oc(lista, campo):
            return [(f[campo], f["n"], f.get("primeira") or u"—",
                     f.get("ultima") or u"—",
                     _versoes_em_texto(f.get("versoes"))) for f in lista]
        C.append(u"<h2>Falhas</h2>")
        C.append(tabela((u"motivo",) + _cab_oc, _oc(rel["falhas"], "motivo"))
                 if rel.get("falhas") else u"<p>Nenhuma série falhou.</p>")
        if rel.get("tasks_falharam"):
            C.append(u"<p class='sub'>Tasks que falharam sem derrubar a série</p>")
            C.append(tabela((u"task", u"vezes"), contagem(rel["tasks_falharam"])))
        tv = rel.get("travamentos") or {}
        C.append(u"<h2>Travamentos</h2>")
        C.append(u"<p>Total: %s.</p>" % esc(tv.get("total", 0)))
        if tv.get("total"):
            C.append(tabela((u"task", u"vezes"), contagem(tv.get("por_task"))))
            C.append(tabela((u"motivo",) + _cab_oc,
                            _oc(tv.get("por_motivo_detalhe") or [], "motivo")))
            C.append(tabela((u"retomada", u"vezes"), contagem(tv.get("retomadas"))))
        C.append(u"<h2>Casos interrompidos</h2>")
        C.append(u"<p>Total: %s (o programa parou no meio da série; o caso foi "
                 u"fechado ao abrir de novo).</p>"
                 % esc(rel.get("interrompidos", 0)))
        if rel.get("interrompidos_por_etapa"):
            C.append(tabela((u"última etapa",) + _cab_oc,
                            _oc(rel["interrompidos_por_etapa"], "etapa")))
            C.append(tabela(
                (u"caso (pseudônimo)", u"quando", u"versão", u"porta", u"modo",
                 u"última etapa", u"às"),
                [(x["pseudonimo"], x["quando"], x["versao"], x["porta"],
                  x["modo"], x["ultima_etapa"], x.get("hora") or u"—")
                 for x in rel.get("lista_interrompidos") or []]))
        C.append(u"<h2>Casos recentes com falha</h2>")
        C.append(tabela(
            (u"caso (pseudônimo)", u"quando", u"versão", u"porta", u"modo",
             u"motivo"),
            [(x["pseudonimo"], x["quando"], x["versao"], x["porta"],
              x["modo"], x["motivo"]) for x in rel["falhas_recentes"]])
            if rel.get("falhas_recentes") else u"<p>Nenhuma.</p>")
        if rel.get("clip_box"):
            C.append(u"<h2>Recorte por task (clip-box)</h2>")
            C.append(tabela((u"task", u"casos", u"usado", u"ganho mediano (s)"),
                            [(t, a["casos"], a["usado"],
                              (a.get("ganho_s") or {}).get("mediana", u"—"))
                             for t, a in sorted(rel["clip_box"].items())]))
        if rel.get("comparacao") or rel.get("oar_fora"):
            C.append(u"<h2>O que foi pedido no PERSONALIZADO</h2>")
            if rel.get("comparacao"):
                C.append(tabela((u"comparação", u"casos"),
                                contagem(rel["comparacao"])))
            if rel.get("oar_fora"):
                C.append(tabela((u"tirada do OAR", u"casos"),
                                contagem(rel["oar_fora"])))
        C.append(u"<h2>Dispositivos</h2>")
        C.append(tabela((u"dispositivo", u"casos"), contagem(rel.get("dispositivos"))))
        C.append(u"<h2>Versões</h2>")
        C.append(tabela((u"versão do app", u"casos"),
                        contagem((rel.get("versoes") or {}).get("app"))))
        if (rel.get("versoes") or {}).get("totalsegmentator"):
            C.append(tabela((u"TotalSegmentator", u"casos"),
                            contagem(rel["versoes"]["totalsegmentator"])))
        C.append(u"<h2>Estações</h2>")
        C.append(tabela((u"estação (pseudônimo)", u"casos", u"núcleos",
                         u"memória (GB)", u"GPU", u"papel"),
                        [(e.get("maquina"), e.get("casos"),
                          e.get("nucleos", u"—"), e.get("memoria_gb", u"—"),
                          e.get("gpu", u"nenhuma"), e.get("papel", u"—"))
                         for e in rel.get("estacoes") or []]))
    C.append(u"<p class='rodape'>Relatório gerado do registro de casos, sem "
             u"identificação de paciente (nem nome, nem registro, nem data de "
             u"nascimento, nem identificador de série, nem pasta). Toda "
             u"estrutura contornada é sugestão não aprovada; revisão e "
             u"aprovação são ato médico humano.</p>")
    css = (u":root{--fundo:#f6f7f9;--papel:#fff;--texto:#1b2230;--sub:#5b6577;"
           u"--linha:#dde2ea;--realce:#12873F}"
           u"@media (prefers-color-scheme:dark){:root{--fundo:#0e141d;"
           u"--papel:#151d29;--texto:#e6ebf2;--sub:#98a3b5;--linha:#263244;"
           u"--realce:#5bc57f}}"
           u"body{margin:0;background:var(--fundo);color:var(--texto);"
           u"font:15px/1.5 system-ui,-apple-system,'Segoe UI',sans-serif}"
           u"main{max-width:960px;margin:0 auto;padding:24px 16px 48px}"
           u"h1{font-size:26px;margin:0 0 4px}h2{font-size:18px;margin:28px 0 8px;"
           u"border-bottom:1px solid var(--linha);padding-bottom:4px}"
           u".sub{color:var(--sub);margin:4px 0 12px}"
           u".fichas{display:flex;flex-wrap:wrap;gap:10px;margin:16px 0}"
           u".ficha{background:var(--papel);border:1px solid var(--linha);"
           u"border-radius:10px;padding:10px 14px;min-width:120px}"
           u".ficha b{display:block;font-size:22px;color:var(--realce)}"
           u".ficha span{color:var(--sub);font-size:13px}"
           u".tab{overflow-x:auto;margin:8px 0 12px;max-width:100%}"
           u"table{border-collapse:collapse;background:var(--papel);"
           u"border:1px solid var(--linha);border-radius:8px;min-width:240px}"
           u"th,td{text-align:left;padding:6px 12px;border-bottom:1px solid "
           u"var(--linha);vertical-align:top}tr:last-child td{border-bottom:0}"
           u"td:not(:first-child){font-variant-numeric:tabular-nums}"
           u"th{color:var(--sub);font-weight:600}"
           u".rodape{margin-top:32px;color:var(--sub);font-size:13px}")
    return (u"<!doctype html>\n<html lang='pt-BR'><head><meta charset='utf-8'>"
            u"<meta name='viewport' content='width=device-width,initial-scale=1'>"
            u"<title>Relatório de período</title><style>%s</style></head>"
            u"<body><main>%s</main></body></html>\n" % (css, u"\n".join(C)))


def gravar_relatorio(destino, base="", desde="", ate="", identificadores=()):
    r = {"ok": False, "md": u"", "html": u"", "casos": 0, "avisos": []}
    try:
        rel = relatorio_de_periodo(base=base, desde=desde, ate=ate)
        md, ht = relatorio_markdown(rel), relatorio_html(rel)
        conferir_relatorio(md, identificadores)
        conferir_relatorio(ht, identificadores)
        _garantir(destino)
        carimbo = datetime.now().strftime("%Y%m%d_%H%M%S")
        pm = os.path.join(destino, u"relatorio_periodo_%s.md" % carimbo)
        ph = os.path.join(destino, u"relatorio_periodo_%s.html" % carimbo)
        with io.open(pm, "w", encoding="utf-8") as f:
            f.write(md)
        with io.open(ph, "w", encoding="utf-8") as f:
            f.write(ht)
        r.update({"ok": True, "md": pm, "html": ph, "casos": rel.get("casos", 0),
                  "recusados": len(rel.get("recusados") or [])})
    except ContemIdentificacao as e:
        r["avisos"].append(u"%s" % e)
    except Exception as e:
        r["avisos"].append(u"%s: %s" % (type(e).__name__, str(e)[:160]))
    return r
