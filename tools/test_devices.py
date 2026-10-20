# -*- coding: utf-8 -*-
import hashlib
import io
import json
import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.abspath(os.path.join(AQUI, ".."))
for _c in (os.path.join(RAIZ, "app"), RAIZ):
    if os.path.exists(os.path.join(_c, "radai_devices.py")):
        APP = _c
        sys.path.insert(0, _c)
        break
sys.path.insert(0, AQUI)
import _cleanup
_cleanup.adotar_prefixo("radai_teste_devices_")
os.environ.setdefault("RADAI_CALIB_DIR",
                      _cleanup.temporaria("radai_teste_devices_ac_"))

_MODS_ANTES = set(sys.modules)
import radai_devices as D
import _componentes
_MODS_DEPOIS = set(sys.modules)

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


class _Ambiente(object):
    def __init__(self, **v):
        self.v, self.velhos = v, {}

    def __enter__(self):
        for k, val in self.v.items():
            self.velhos[k] = os.environ.get(k)
            if val is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = val
        return self

    def __exit__(self, *a):
        for k, val in self.velhos.items():
            if val is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = val
        return False


def teste_o_nvidia_smi_e_uma_regra_so():
    secao(u"1 · o nvidia-smi e UMA regra (a do motor e a daqui)")
    eng = None
    try:
        import engine as eng
    except Exception as e:
        checar(u"o motor importa para a comparacao", False,
               "%s: %s" % (type(e).__name__, e))
    for rotulo, poe_nvsmi, poe_sys32, espera in (
            ("nenhum", False, False, "nvidia-smi"),
            ("so NVSMI", True, False, "NVSMI"),
            ("os dois (System32 ganha)", True, True, "System32")):
        b = _cleanup.temporaria("radai_teste_devices_")
        sr = os.path.join(b, "Windows")
        p = os.path.join(b, "PF")
        os.makedirs(os.path.join(sr, "System32"))
        os.makedirs(os.path.join(p, "NVIDIA Corporation", "NVSMI"))
        if poe_nvsmi:
            io.open(os.path.join(p, "NVIDIA Corporation", "NVSMI",
                                 "nvidia-smi.exe"), "w").write(u"x")
        if poe_sys32:
            io.open(os.path.join(sr, "System32", "nvidia-smi.exe"),
                    "w").write(u"x")
        with _Ambiente(SystemRoot=sr, ProgramFiles=p, ProgramW6432=None):
            aqui = D.achar_nvidia_smi()
            la = eng._achar_nvidia_smi() if eng is not None else aqui
        checar(u"%s: acha %s" % (rotulo, espera), espera in aqui, aqui)
        checar(u"  e o motor responde IGUAL", aqui == la, u"%s | %s" % (aqui, la))
        if rotulo == "so NVSMI":
            isca = "nvidia-smi"
            checar(u"  ISCA: a regra do PATH (o limpador ate 24/09) diverge",
                   isca != aqui, isca)
    checar(u"a busca nao tem caminho absoluto escrito no codigo",
           "C:\\\\" not in _codigo_de(D.achar_nvidia_smi)
           and "Program Files" not in _codigo_de(D.achar_nvidia_smi))

    import ast as _ast

    def _delega(fonte):
        for no in _ast.walk(_ast.parse(fonte)):
            if (isinstance(no, _ast.FunctionDef)
                    and no.name == "_achar_nvidia_smi"):
                chama = busca = False
                for c in _ast.walk(no):
                    if isinstance(c, _ast.Call):
                        nome = getattr(c.func, "attr", None) or getattr(
                            c.func, "id", None)
                        if nome == "achar_nvidia_smi":
                            chama = True
                        if nome == "isfile":
                            busca = True
                return chama and not busca
        return False
    try:
        with io.open(_componentes.fonte("app/engine.py"), encoding="utf-8") as f:
            _fonte_motor = f.read()
    except Exception as e:
        _fonte_motor = u""
        checar(u"o fonte do motor le (pre-condicao)", False, str(e))
    checar(u"`engine._achar_nvidia_smi` DELEGA a esta (a regra e uma so, "
           u"por construcao)", _delega(_fonte_motor))
    _isca = _fonte_motor.replace(
        u"return _rd.achar_nvidia_smi()",
        u"return 'nvidia-smi' if not os.path.isfile('x') else 'x'")
    checar(u"  (isca) com a busca de volta no motor, a leitura acusa",
           _isca != _fonte_motor and not _delega(_isca))


def _codigo_de(fn):
    import inspect
    import tokenize
    fonte = inspect.getsource(fn)
    fora = []
    for tok in tokenize.generate_tokens(io.StringIO(fonte).readline):
        if tok.type in (tokenize.COMMENT,):
            continue
        if tok.type == tokenize.STRING and tok.string.lstrip("urbURB").startswith(('"""', "'''")):
            continue
        fora.append(tok.string)
    return " ".join(fora)


def teste_toda_placa_e_nomeada():
    secao(u"2 · toda placa e nomeada, pelo fabricante do PCI")
    for pnp, fab, nome, espera in (
            ("PCI\\VEN_10DE&DEV_1FB0", "NVIDIA", "Quadro P2200", "nvidia"),
            ("PCI\\VEN_8086&DEV_A7A1", "Intel Corporation",
             "Intel(R) Iris(R) Xe Graphics", "intel"),
            ("PCI\\VEN_1002&DEV_73BF", "Advanced Micro Devices, Inc.",
             "AMD Radeon RX 6800", "amd"),
            ("", "Microsoft", "Microsoft Remote Display Adapter", "microsoft"),
            ("PCI\\VEN_8086&DEV_46A6", "Fabricante qualquer", "Placa X", "intel"),
            ("", "", "Placa desconhecida", "outro")):
        v = D._vendor_de(pnp, fab, nome)
        checar(u"%s -> %s" % (nome, espera), v == espera, v)
    usa, frase = D.uso_pelo_pacote("intel")
    checar(u"Intel: o TotalSegmentator do pacote NAO usa, e a frase diz",
           usa is False and u"nao usa" in frase, frase)
    usa, frase = D.uso_pelo_pacote("nvidia")
    checar(u"NVIDIA: usa (CUDA)", usa is True and u"CUDA" in frase, frase)
    usa, frase = D.uso_pelo_pacote("microsoft")
    checar(u"adaptador remoto: nao calcula", usa is False
           and u"nao calcula" in frase, frase)
    import unicodedata
    for v in ("nvidia", "intel", "amd", "microsoft", "outro"):
        tela = unicodedata.normalize("NFKD", D.frase_na_tela(v)).encode(
            "ascii", "ignore").decode("ascii")
        checar(u"a frase da tela e a do log dizem o mesmo (%s)" % v,
               tela == D.uso_pelo_pacote(v)[1], (tela, D.uso_pelo_pacote(v)[1]))
    p = D._placa({"nome": "Intel(R) Iris(R) Xe Graphics",
                  "fabricante": "Intel Corporation", "driver": "32.0.101.7076",
                  "ram": 2147479552, "pnp": "PCI\\VEN_8086&DEV_A7A1"}, {})
    checar(u"a Iris Xe sai integrada, com 2047 MiB (uint32 do CIM)",
           p["integrada"] and p["memoria_mb"] == 2047
           and p["memoria_fonte"].startswith(u"CIM"), p)
    p2 = D._placa({"nome": "NVIDIA RTX A4000", "ram": 4293918720,
                   "pnp": "PCI\\VEN_10DE&DEV_24B0"},
                  {"NVIDIA RTX A4000": 17171480576})
    checar(u"placa acima de 4 GiB: a memoria do REGISTRO vence a do CIM",
           p2["memoria_mb"] == 16376 and p2["memoria_fonte"] == u"registro",
           p2)


def teste_o_inventario_le_as_duas_formas_e_cai_no_wmic():
    secao(u"3 · o JSON do PowerShell nas duas formas, e o recuo do wmic")
    um = {"placas": {"nome": "Intel(R) Iris(R) Xe Graphics",
                     "fabricante": "Intel Corporation", "driver": "32.0.101.7076",
                     "data": "2025-09-11", "ram": 2147479552,
                     "pnp": "PCI\\VEN_8086&DEV_A7A1", "status": "OK"},
          "memoria": {"nome": "Intel(R) Iris(R) Xe Graphics", "mem": None},
          "cpu": {"nome": "13th Gen Intel(R) Core(TM) i7-1355U",
                  "fisicos": 10, "logicos": 12}}
    lista = dict(um, placas=[um["placas"], {
        "nome": "NVIDIA RTX A2000", "fabricante": "NVIDIA", "driver": "31.0.15.3667",
        "ram": 4293918720, "pnp": "PCI\\VEN_10DE&DEV_2531"}],
        memoria=[{"nome": "NVIDIA RTX A2000", "mem": 6442450944}])

    def rodar_ps(resposta):
        def _r(args, timeout, baixa_prioridade=False, env=None):
            if args[0] == "powershell":
                return {"codigo": 0, "saida": u"lixo antes\n" + json.dumps(resposta),
                        "erro": u"", "falha": u"", "segundos": 0.1}
            return {"codigo": 1, "saida": u"", "erro": u"", "falha": u"",
                    "segundos": 0.1}
        return _r
    if os.name == "nt":
        with _Troca(D, _rodar=rodar_ps(um)):
            r = D.inventario_windows()
        checar(u"objeto sozinho (uma placa) vira lista de uma",
               len(r["placas"]) == 1 and r["placas"][0]["vendor"] == "intel",
               r)
        checar(u"  e a CPU do CIM vem junto",
               r["cpu_cim"] and r["cpu_cim"][0]["fisicos"] == 10)
        with _Troca(D, _rodar=rodar_ps(lista)):
            r = D.inventario_windows()
        checar(u"lista (duas placas) com a memoria do registro",
               len(r["placas"]) == 2 and r["placas"][1]["memoria_mb"] == 6144,
               [p.get("memoria_mb") for p in r["placas"]])
        csv = (u"\r\nNode,AdapterCompatibility,AdapterRAM,DriverVersion,Name,"
               u"PNPDeviceID\r\nPC,Intel Corporation,2147479552,32.0.101.7076,"
               u"Intel(R) UHD Graphics 770,PCI\\VEN_8086&DEV_4680\r\n")

        def so_wmic(args, timeout, baixa_prioridade=False, env=None):
            if args[0] == "powershell":
                return {"codigo": None, "saida": u"", "erro": u"",
                        "falha": u"nao encontrado", "segundos": 0.0}
            return {"codigo": 0, "saida": csv, "erro": u"", "falha": u"",
                    "segundos": 0.1}
        with _Troca(D, _rodar=so_wmic):
            r = D.inventario_windows()
        checar(u"sem PowerShell: cai no wmic e acha a placa",
               len(r["placas"]) == 1 and r["placas"][0]["vendor"] == "intel",
               r)
        checar(u"  e DIZ que caiu (fonte e falha preenchidas)",
               u"wmic" in r["fonte"] and u"PowerShell" in r["falha"],
               (r["fonte"], r["falha"]))

        def nada(args, timeout, baixa_prioridade=False, env=None):
            return {"codigo": None, "saida": u"", "erro": u"",
                    "falha": u"nao encontrado", "segundos": 0.0}
        with _Troca(D, _rodar=nada):
            r = D.inventario_windows()
        checar(u"sem os dois: lista vazia COM o motivo (nao e «nao tem placa»)",
               not r["placas"] and u"PowerShell" in r["falha"]
               and u"wmic" in r["falha"], r["falha"])
        real = D.inventario_windows()
        checar(u"nesta maquina o Windows lista ao menos uma placa",
               len(real["placas"]) >= 1 or real["falha"],
               real.get("falha") or [p["nome"] for p in real["placas"]])


def teste_a_cpu_diz_fisicos_e_logicos():
    secao(u"4 · a CPU: fisicos, logicos e hibrida")
    t = D.topologia_da_cpu()
    if os.name == "nt":
        checar(u"a topologia vem da GetLogicalProcessorInformationEx",
               t["fonte"] == u"GetLogicalProcessorInformationEx", t)
        checar(u"  os logicos batem com os.cpu_count()",
               t["logicos"] == os.cpu_count(), (t["logicos"], os.cpu_count()))
        checar(u"  fisicos <= logicos, e a soma das classes e o fisico",
               t["fisicos"] and t["fisicos"] <= t["logicos"]
               and sum(t["classes"].values()) == t["fisicos"], t)
    h = D.descrever_cpu({"fisicos": 10, "logicos": 12, "classes": {1: 2, 0: 8}},
                        u"i7-1355U")
    checar(u"hibrida: 2 de desempenho + 8 de eficiencia",
           u"10 nucleo(s) fisico(s), 12 logico(s)" in h
           and u"2 nucleo(s) de desempenho + 8 de eficiencia" in h, h)
    n = D.descrever_cpu({"fisicos": 8, "logicos": 16, "classes": {0: 8}})
    checar(u"ISCA: uma classe so NAO vira «hibrida»", u"hibrida" not in n, n)
    s = D.descrever_cpu({"fisicos": None, "logicos": 12, "classes": {},
                         "fonte": u"os.cpu_count", "falha": u"OSError: x"})
    checar(u"sem os fisicos, a linha diz que nao leu (nao repete o logico)",
           u"os fisicos nao foram lidos" in s and u"OSError" in s, s)


def teste_as_sondas_rodam_no_filho():
    secao(u"5 · as sondas rodam num processo FILHO")
    novos = _MODS_DEPOIS - _MODS_ANTES
    for pesado in ("torch", "numpy", "openvino", "torch_directml"):
        checar(u"importar radai_devices nao importa `%s`" % pesado,
               pesado not in novos, sorted(m for m in novos if pesado in m)[:3])
    r = D.sondar("openvino", python_exe=sys.executable, timeout=60)
    checar(u"a sonda do OpenVINO responde pelo filho (com ou sem openvino)",
           "falha" not in r and ("importa" in r), r)
    checar(u"  e quem importou foi o filho, nao este processo",
           "openvino" not in sys.modules)
    r2 = D.sondar("directml", python_exe=sys.executable, timeout=60)
    checar(u"sem o torch_directml a sonda diz «nao instalado» (e rapido)",
           (r2.get("importa") is False and u"nao instalado" in (r2.get("erro") or u""))
           or r2.get("importa") is True, r2)
    r3 = D.sondar("inexistente", python_exe=sys.executable, timeout=60)
    checar(u"familia desconhecida vira erro dito", u"desconhecida" in
           (r3.get("erro") or u""), r3)
    ruim = D._ler_marcada({"codigo": 1, "saida": u"", "erro": u"Traceback\nBoom: x",
                           "falha": u""}, D.MARCA_SONDA)
    checar(u"filho que sai sem responder: a falha diz o codigo e a ultima linha",
           u"codigo 1" in ruim["falha"] and u"Boom" in ruim["falha"], ruim)
    lixo = D._ler_marcada({"codigo": 0, "saida": D.MARCA_SONDA + u"{nao json",
                           "erro": u"", "falha": u""}, D.MARCA_SONDA)
    checar(u"resposta ilegivel e dita como tal", u"ilegivel" in lixo["falha"],
           lixo)
    b = D.backends_das_sondas({
        "torch": {"importa": True, "versao": "2.5.1+cu121", "cuda": "12.1",
                  "cuda_disponivel": False, "xpu_disponivel": False,
                  "xpu_motivo": "torch 2.5.1+cu121: xpu.is_available() falso"},
        "directml": {"importa": False, "erro": "torch_directml nao instalado"},
        "openvino": {"importa": True, "versao": "2026.4.0",
                     "dispositivos": {"CPU": "i7", "GPU": "Iris Xe"}}})
    checar(u"torch_cpu disponivel; cuda nao, com o motivo",
           b["torch_cpu"]["disponivel"] and not b["cuda"]["disponivel"]
           and u"indisponivel" in b["cuda"]["motivo"], b["cuda"])
    checar(u"openvino_cpu e openvino_gpu disponiveis pela lista do Core",
           b["openvino_cpu"]["disponivel"] and b["openvino_gpu"]["disponivel"])
    checar(u"xpu indisponivel com o motivo da sonda",
           not b["xpu"]["disponivel"] and u"is_available" in b["xpu"]["motivo"])
    b2 = D.backends_das_sondas({"torch": {"falha": u"o filho nao respondeu em 120 s"},
                                "directml": {}, "openvino": {}})
    checar(u"«nao consegui perguntar» nao vira «nao tem»: o motivo e a falha",
           all(u"nao respondeu" in b2[k]["motivo"]
               for k in ("torch_cpu", "cuda", "xpu")), b2["torch_cpu"])
    s = D.sonda_torch_do_arranque({"importa": True, "versao": "2.5.1+cu121",
                                   "cuda": "12.1", "disponivel": True, "n": 1,
                                   "placas": [{"nome": "Quadro P2200",
                                               "total_mb": 5120}]})
    b3 = D.backends_das_sondas({"torch": s, "directml": {}, "openvino": {}})
    checar(u"a sonda do arranque vira a familia torch (CUDA com a placa)",
           b3["cuda"]["disponivel"] and "Quadro P2200" in b3["cuda"]["dispositivos"][0],
           b3["cuda"])


_PROPS = {"percentile_00_5": -1023.9998779296875, "percentile_99_5": 288.0,
          "mean": -355.7182728404226, "std": 431.5967952360472}


def teste_o_fantoma_e_o_mesmo_em_qualquer_numpy():
    secao(u"6 · o fantoma e o mesmo byte a byte (o hash de fabrica)")
    try:
        import numpy as np
    except ImportError:
        checar(u"(sem numpy neste Python: pulado)", True)
        return
    f = D.fantoma(np, 128, _PROPS)
    checar(u"forma (1,1,128,128,128) em float32",
           f.shape == (1, 1, 128, 128, 128) and str(f.dtype) == "float32",
           (f.shape, f.dtype))
    h = hashlib.sha256(f.tobytes()).hexdigest()
    checar(u"numpy %s: o hash e o de fabrica (medido igual no 1.26.4 e no 2.5.1)"
           % np.__version__, h == D.FANTOMA_SHA256, h)
    f2 = D.fantoma(np, 128, dict(_PROPS, mean=-355.0))
    checar(u"ISCA: outra normalizacao muda o hash (o hash mede o fantoma)",
           hashlib.sha256(f2.tobytes()).hexdigest() != D.FANTOMA_SHA256)
    fora = float((np.abs(f) > 0.01).mean())
    checar(u"o fantoma nao e constante (tem ar, gordura, orgao e osso)",
           len(np.unique(np.round(f, 2))) > 20 and 0.3 < fora <= 1.0,
           len(np.unique(np.round(f, 2))))


def _medida(**kw):
    d = {"backend": "openvino_cpu", "concordancia": 0.99999, "nao_finito": False,
         "sha256": "a" * 64, "sha256_ref": "b" * 64, "max_dif_logit": 0.03,
         "contagem_ref": [100] * 18 + [0] * 7,
         "fantoma_sha256": D.FANTOMA_SHA256}
    d.update(kw)
    return d


def teste_o_juiz_do_canario():
    secao(u"7 · o juiz do canario")
    r = D.julgar(_medida())
    checar(u"99,999% e 18 classes: aprovado (equivalente, nao identico)",
           r["aprovado"] and u"concordancia" in r["motivo"], r["motivo"])
    r = D.julgar(_medida(sha256="b" * 64))
    checar(u"mesmo sha256: aprovado e dito «identico»",
           r["aprovado"] and u"identico" in r["motivo"], r["motivo"])
    r = D.julgar(_medida(concordancia=0.9985))
    checar(u"99,85%: REPROVADO com o numero", not r["aprovado"]
           and u"99.85" in r["motivo"], r["motivo"])
    r = D.julgar(_medida(nao_finito=True, concordancia=1.0))
    checar(u"NaN/infinito: reprovado mesmo com concordancia 100%",
           not r["aprovado"] and u"NaN" in r["motivo"], r["motivo"])
    inerte = _medida(contagem_ref=[2097149, 3] + [0] * 23, concordancia=1.0)
    r = D.julgar(dict(inerte))
    checar(u"canario INERTE (a referencia so tem fundo): reprovado",
           not r["aprovado"] and u"inerte" in r["motivo"], r["motivo"])
    with _Troca(D, CLASSES_MINIMAS=0):
        r = D.julgar(dict(inerte))
    checar(u"  ISCA: sem a guarda das classes, o inerte seria aprovado",
           r["aprovado"], r["motivo"])
    with _Troca(D, LIMIAR_CONCORDANCIA=0.99):
        r = D.julgar(_medida(concordancia=0.9985))
    checar(u"  ISCA: com o limiar frouxo, os 99,85% passariam",
           r["aprovado"])
    r = D.julgar({"backend": "xpu", "falha": u"o filho nao respondeu em 900 s"})
    checar(u"falha do filho: reprovado com a falha como motivo",
           not r["aprovado"] and u"nao respondeu" in r["motivo"], r)
    r = D.julgar(_medida(sha256_ref=D.CANARIO_REFERENCIA["sha256"]))
    checar(u"referencia local = a de fabrica: «identica»",
           r["fabrica"] == u"identica", r["fabrica"])
    r = D.julgar(_medida(sha256_ref="c" * 64))
    checar(u"referencia local diferente: dito, e o canario segue",
           u"DIFERENTE" in r["fabrica"] and r["aprovado"], r["fabrica"])
    r = D.julgar(_medida(fantoma_sha256="d" * 64))
    checar(u"fantoma diferente: a comparacao com a fabrica nao se aplica",
           u"nao comparavel" in r["fabrica"], r["fabrica"])


def _inv(**disp):
    base = {b: {"disponivel": False, "motivo": u"x"} for b in D.BACKENDS}
    base["torch_cpu"] = {"disponivel": True, "versao": "2.5.1", "dispositivos": ["CPU"]}
    for b, v in disp.items():
        base[b] = {"disponivel": v, "versao": "1", "dispositivos": ["X"]}
    return {"backends": base, "placas": [{"nome": "Iris", "driver": "1"}],
            "cpu": {"nome": "i7"}}


def teste_so_o_admitido_entra_na_fila():
    secao(u"8 · a fila so recebe backend ADMITIDO")
    inv = _inv()
    checar(u"so o PyTorch CPU: nenhum candidato ao canario",
           D.candidatos_ao_canario(inv) == [], D.candidatos_ao_canario(inv))
    checar(u"  e a fila usa o chao", D.admitidos(inv, {}) == ["torch_cpu"])
    inv = _inv(openvino_cpu=True, openvino_gpu=True, cuda=True)
    checar(u"com OpenVINO e CUDA disponiveis: candidatos CUDA e OpenVINO na "
           u"placa; o OpenVINO na CPU (recusado pelo numero) nem roda canario",
           set(D.candidatos_ao_canario(inv)) == {"openvino_gpu", "cuda"},
           D.candidatos_ao_canario(inv))
    can = {"openvino_cpu": {"aprovado": True}, "openvino_gpu": {"aprovado": True},
           "cuda": {"aprovado": True}}
    adm = D.admitidos(inv, can)
    checar(u"CUDA aprovada (producao) entra; OpenVINO aprovado (pesquisa ou "
           u"recusado) NAO",
           "cuda" in adm and "openvino_cpu" not in adm
           and "openvino_gpu" not in adm and "torch_cpu" in adm, adm)
    checar(u"  e o envelope nao recebe executor", D.executor_para_o_envelope(inv, can) == {})
    pol = dict(D.POLITICA_DE_ADOCAO, openvino_cpu="producao")
    with _Troca(D, POLITICA_DE_ADOCAO=pol):
        adm2 = D.admitidos(inv, can)
        ex = D.executor_para_o_envelope(inv, can)
    checar(u"  ISCA: com a politica em producao, o OpenVINO entra",
           "openvino_cpu" in adm2 and ex == {"RADAI_EXECUTOR": "openvino_cpu"},
           (adm2, ex))
    with _Troca(D, POLITICA_DE_ADOCAO=pol):
        adm3 = D.admitidos(inv, {"openvino_cpu": {"aprovado": False}})
    checar(u"politica em producao e canario REPROVADO: nao entra",
           "openvino_cpu" not in adm3, adm3)
    checar(u"CUDA sem canario ainda (rodando): nao entra",
           "cuda" not in D.admitidos(inv, {}))
    recusado = dict(D.POLITICA_DE_ADOCAO, openvino_cpu="recusado")
    with _Troca(D, POLITICA_DE_ADOCAO=recusado):
        checar(u"politica «recusado»: nem candidato ao canario",
               "openvino_cpu" not in D.candidatos_ao_canario(inv))
    for b in D.BACKENDS:
        checar(u"%s tem politica e motivo declarados" % b,
               D.POLITICA_DE_ADOCAO.get(b) in ("producao", "pesquisa", "recusado")
               and D.MOTIVO_DA_POLITICA.get(b))
    checar(u"a decisao pelo numero: DirectML e OpenVINO na CPU recusados",
           D.POLITICA_DE_ADOCAO["directml"] == "recusado"
           and D.POLITICA_DE_ADOCAO["openvino_cpu"] == "recusado")
    checar(u"  e o motivo de cada um cita a medida (nao «a medir»)",
           all(u"medido" in D.MOTIVO_DA_POLITICA[b]
               for b in ("openvino_cpu", "openvino_gpu", "directml", "xpu")))
    pol_x = dict(D.POLITICA_DE_ADOCAO, xpu="producao", openvino_gpu="producao")
    inv_x = _inv(xpu=True, openvino_gpu=True)
    with _Troca(D, POLITICA_DE_ADOCAO=pol_x):
        ex = D.executor_para_o_envelope(inv_x, {"xpu": {"aprovado": True},
                                                "openvino_gpu": {"aprovado": True}})
    checar(u"com XPU e OpenVINO admitidos, o envelope recebe a XPU (o numero)",
           ex == {"RADAI_EXECUTOR": "xpu"}, ex)
    checar(u"o chao e a CUDA sao producao; nenhum backend novo liga de fabrica",
           D.POLITICA_DE_ADOCAO["torch_cpu"] == "producao"
           and D.POLITICA_DE_ADOCAO["cuda"] == "producao"
           and all(D.POLITICA_DE_ADOCAO[b] != "producao"
                   for b in ("openvino_cpu", "openvino_gpu", "directml", "xpu")),
           D.POLITICA_DE_ADOCAO)


def teste_o_cache_do_canario():
    secao(u"9 · o cache do canario: mesma impressao reaproveita, driver novo refaz")
    base = _cleanup.temporaria("radai_teste_devices_")
    pesos = os.path.join(base, "pesos")
    modelo = os.path.join(pesos, "Dataset831_x_1830subj",
                          "nnUNetTrainerNoMirroring__nnUNetPlans__3d_fullres")
    os.makedirs(os.path.join(modelo, "fold_0"))
    for n in ("plans.json",):
        io.open(os.path.join(modelo, n), "w").write(u"{}")
    io.open(os.path.join(modelo, "fold_0", "checkpoint_final.pth"), "wb").write(b"x" * 10)
    checar(u"a pasta do canario e achada por marca (Dataset831_, nnUNetPlans)",
           D.pasta_do_canario(pesos) == modelo, D.pasta_do_canario(pesos))
    os.makedirs(os.path.join(pesos, "Dataset831_x_1830subj",
                             "nnUNetTrainerNoMirroring__nnUNetResEncUNetLPlans_8__3d_fullres",
                             "fold_0"))
    checar(u"  e o ResEncL (small) nao a substitui", D.pasta_do_canario(pesos) == modelo)
    chamadas = []

    def canario_falso(b, **kw):
        chamadas.append(b)
        return D.julgar(_medida(backend=b))
    inv = _inv(openvino_gpu=True)
    cache = os.path.join(base, "canario.json")
    logs = []
    folga = lambda: {"livre_mb": 20000, "total_mb": 32000}
    with _Troca(D, canario=canario_falso, memoria=folga):
        D.rodar_canarios(inv, pasta_pesos=pesos, cache=cache, log=logs.append)
        n1 = len(chamadas)
        r2 = D.rodar_canarios(inv, pasta_pesos=pesos, cache=cache, log=logs.append)
        n2 = len(chamadas)
        inv2 = dict(inv, placas=[{"nome": "Iris", "driver": "2"}])
        r3 = D.rodar_canarios(inv2, pasta_pesos=pesos, cache=cache, log=logs.append)
        n3 = len(chamadas)
    checar(u"primeira vez: roda", n1 == 1, chamadas)
    checar(u"segunda, mesma impressao: do cache (nao roda de novo)",
           n2 == 1 and r2["openvino_gpu"].get("do_cache")
           and r2["openvino_gpu"].get("aprovado"), (n2, r2))
    checar(u"driver novo: roda de novo", n3 == 2
           and not r3["openvino_gpu"].get("do_cache"), (n3, r3))
    checar(u"o log diz de onde veio cada veredito",
           any(u"do cache" in l for l in logs) and any(u"rodando" in l for l in logs),
           logs)
    cont = json.load(io.open(cache, encoding="utf-8"))
    checar(u"o cache nao tem traceback, PID nem saida de processo (so medidas)",
           "openvino_gpu" in cont and u"impressao" in cont["openvino_gpu"]
           and not _o_que_nao_e_medida(cont), _o_que_nao_e_medida(cont))
    del chamadas[:]
    logs2 = []
    with _Troca(D, canario=canario_falso,
                memoria=lambda: {"livre_mb": 2000, "total_mb": 16000}):
        r = D.rodar_canarios(inv, pasta_pesos=pesos, cache=None, log=logs2.append)
    checar(u"com 2 GB livres o canario e ADIADO (nao roda), e dito",
           not chamadas and r["openvino_gpu"].get("adiado")
           and any(u"adiado" in l for l in logs2), (chamadas, logs2))
    checar(u"  adiado nao e aprovado", not r["openvino_gpu"].get("aprovado"))
    with _Troca(D, canario=canario_falso,
                memoria=lambda: {"livre_mb": 20000, "total_mb": 32000}):
        D.rodar_canarios(inv, pasta_pesos=pesos, cache=None, log=logs2.append)
    checar(u"ISCA: com 20 GB livres, o mesmo canario roda", chamadas == ["openvino_gpu"],
           chamadas)


def teste_a_falha_do_canario_nao_fica_no_cache():
    secao(u"9b · a falha do canario nao fica no cache; a medida completa fica")
    base = _cleanup.temporaria("radai_teste_devices_")
    pesos = os.path.join(base, "pesos")
    modelo = os.path.join(pesos, "Dataset831_x_1830subj",
                          "nnUNetTrainerNoMirroring__nnUNetPlans__3d_fullres")
    os.makedirs(os.path.join(modelo, "fold_0"))
    io.open(os.path.join(modelo, "plans.json"), "w").write(u"{}")
    io.open(os.path.join(modelo, "fold_0", "checkpoint_final.pth"), "wb").write(b"x" * 10)
    folga = lambda: {"livre_mb": 20000, "total_mb": 32000}
    inv = _inv(cuda=True)
    chamadas = []

    def falha_so_na_primeira(b, **kw):
        chamadas.append(b)
        if len(chamadas) == 1:
            return D.julgar({"backend": b,
                             "falha": u"o filho nao respondeu em 900 s"})
        return D.julgar(_medida(backend=b, rss_pico_mb=3100))
    cache = os.path.join(base, "canario_falha.json")
    logs = []
    with _Troca(D, canario=falha_so_na_primeira, memoria=folga):
        r1 = D.rodar_canarios(inv, pasta_pesos=pesos, cache=cache, log=logs.append)
        cont1 = json.load(io.open(cache, encoding="utf-8"))
        r2 = D.rodar_canarios(inv, pasta_pesos=pesos, cache=cache, log=logs.append)
        r3 = D.rodar_canarios(inv, pasta_pesos=pesos, cache=cache, log=logs.append)
    checar(u"1a rodada: o filho falhou, e a CUDA saiu reprovada por FALHA",
           not r1["cuda"].get("aprovado") and r1["cuda"].get("falha"), r1)
    checar(u"  a falha NAO foi gravada como veredito do backend",
           "cuda" not in cont1, sorted(cont1))
    checar(u"  e ficou so como lembranca (fora das chaves de backend)",
           (cont1.get(D.CHAVE_FALHAS) or {}).get("cuda", {}).get("motivo"),
           cont1.get(D.CHAVE_FALHAS))
    checar(u"2a rodada, mesma impressao: o filho E CHAMADO DE NOVO",
           len(chamadas) == 2 and not r2["cuda"].get("do_cache"), (chamadas, r2))
    checar(u"  e desta vez aprova", r2["cuda"].get("aprovado"), r2["cuda"])
    checar(u"3a rodada: a medida completa, essa sim, vem do cache",
           len(chamadas) == 2 and r3["cuda"].get("do_cache")
           and r3["cuda"].get("aprovado"), (chamadas, r3))
    cont3 = json.load(io.open(cache, encoding="utf-8"))
    checar(u"  e a lembranca da falha saiu quando a medida chegou",
           "cuda" not in (cont3.get(D.CHAVE_FALHAS) or {}), cont3.get(D.CHAVE_FALHAS))
    checar(u"o veredito traz o pico de RAM do filho (corrige o limiar da CUDA)",
           any(u"pico de RAM do filho 3100 MB" in l for l in logs), logs)
    del chamadas[:]
    sempre = lambda b, **kw: (chamadas.append(b) or D.julgar(
        {"backend": b, "falha": u"CUDA out of memory"}))
    cache2 = os.path.join(base, "canario_falha2.json")
    logs2 = []
    with _Troca(D, canario=sempre, memoria=folga):
        D.rodar_canarios(inv, pasta_pesos=pesos, cache=cache2, log=logs2.append)
        D.rodar_canarios(inv, pasta_pesos=pesos, cache=cache2, log=logs2.append)
    checar(u"falha repetida: o filho roda nas duas, e a 2a diz que a 1a tambem falhou",
           len(chamadas) == 2 and any(u"tambem falhou" in l for l in logs2),
           (chamadas, logs2))
    imp = D.impressao(inv, "cuda", pesos)
    cache3 = os.path.join(base, "canario_velho.json")
    json.dump({"cuda": {"backend": "cuda", "aprovado": False, "impressao": imp,
                        "falha": u"o filho nao respondeu em 900 s",
                        "motivo": u"o filho nao respondeu em 900 s"}},
              io.open(cache3, "w", encoding="utf-8"))
    del chamadas[:]
    with _Troca(D, canario=falha_so_na_primeira, memoria=folga):
        chamadas.append("x")
        r4 = D.rodar_canarios(inv, pasta_pesos=pesos, cache=cache3, log=logs.append)
    checar(u"cache velho com falha gravada: ignorado, o canario roda e aprova",
           len(chamadas) == 2 and r4["cuda"].get("aprovado")
           and not r4["cuda"].get("do_cache"), (chamadas, r4))
    velho = {"impressao": imp, "aprovado": False, "falha": u"x"}
    regra_antiga = velho.get("impressao") == imp and "aprovado" in velho
    checar(u"  ISCA: pela regra antiga, o registro com falha seria reaproveitado",
           regra_antiga and not D.medida_completa(velho))
    checar(u"medida completa: aprovado, reprovado por concordancia, NaN",
           D.medida_completa(D.julgar(_medida()))
           and D.medida_completa(D.julgar(_medida(concordancia=0.99)))
           and D.medida_completa(D.julgar(_medida(nao_finito=True))))
    checar(u"  e nao e medida: falha, adiado, e filho que nao mediu a concordancia",
           not D.medida_completa({"falha": u"x", "concordancia": 1.0})
           and not D.medida_completa({"adiado": True})
           and not D.medida_completa(D.julgar(_medida(concordancia=None))))
    cache4 = os.path.join(base, "canario_adiado.json")
    with _Troca(D, canario=falha_so_na_primeira,
                memoria=lambda: {"livre_mb": 1000, "total_mb": 16000}):
        D.rodar_canarios(inv, pasta_pesos=pesos, cache=cache4, log=logs.append)
    cont4 = json.load(io.open(cache4, encoding="utf-8"))
    checar(u"o adiado nao vai ao cache", "cuda" not in cont4, sorted(cont4))


def teste_o_limiar_de_ram_e_por_backend():
    secao(u"9c · o limiar de RAM do canario e por backend")
    base = _cleanup.temporaria("radai_teste_devices_")
    pesos = os.path.join(base, "pesos")
    modelo = os.path.join(pesos, "Dataset831_x_1830subj",
                          "nnUNetTrainerNoMirroring__nnUNetPlans__3d_fullres")
    os.makedirs(os.path.join(modelo, "fold_0"))
    io.open(os.path.join(modelo, "plans.json"), "w").write(u"{}")
    io.open(os.path.join(modelo, "fold_0", "checkpoint_final.pth"), "wb").write(b"x")
    chamadas = []
    falso = lambda b, **kw: (chamadas.append(b) or D.julgar(_medida(backend=b)))
    inv = _inv(cuda=True, openvino_gpu=True)
    cinco = lambda: {"livre_mb": 5000, "total_mb": 16000}
    with _Troca(D, canario=falso, memoria=cinco):
        r = D.rodar_canarios(inv, pasta_pesos=pesos, cache=None)
    checar(u"com 5 GB livres: a CUDA roda (pede %d MB)" % D.memoria_minima_do_canario("cuda"),
           "cuda" in chamadas and r["cuda"].get("aprovado"), (chamadas, r.get("cuda")))
    checar(u"  e o OpenVINO na placa e adiado (pede %d MB, o pico dele e 5,4 GB)"
           % D.memoria_minima_do_canario("openvino_gpu"),
           "openvino_gpu" not in chamadas and r["openvino_gpu"].get("adiado")
           and u"openvino_gpu pede 6144" in r["openvino_gpu"]["motivo"],
           r.get("openvino_gpu"))
    del chamadas[:]
    with _Troca(D, canario=falso, memoria=cinco,
                MEMORIA_DO_CANARIO_MB={}):
        D.rodar_canarios(inv, pasta_pesos=pesos, cache=None)
    checar(u"  ISCA: com o limiar unico de antes, a CUDA tambem seria adiada",
           "cuda" not in chamadas, chamadas)
    checar(u"backend sem medida propria usa o teto (%d MB)" % D.MEMORIA_MINIMA_CANARIO_MB,
           D.memoria_minima_do_canario("directml") == D.MEMORIA_MINIMA_CANARIO_MB)
    checar(u"nenhum limiar abaixo do pico medido do PyTorch CPU (2,9 GB) + folga",
           all(v >= 4096 for v in D.MEMORIA_DO_CANARIO_MB.values()),
           D.MEMORIA_DO_CANARIO_MB)


def teste_a_lista_nao_se_diz_da_fila():
    secao(u"9d · a lista e dos CONFERIDOS, e a CUDA de fora e dita")
    inv = _inv(cuda=True, openvino_gpu=True, openvino_cpu=True)
    adiado = {"cuda": {"backend": "cuda", "aprovado": False, "adiado": True,
                       "motivo": u"adiado: 3000 MB de RAM livre, o canario de "
                                 u"cuda pede 4096"},
              "openvino_gpu": D.julgar(_medida(backend="openvino_gpu"))}

    def diz_a_cuda(txt):
        return (u"cuda: NAO CONFERIDO" in txt and u"adiado" in txt)
    L = D.linhas_da_conferencia(inv, adiado)
    t = u"\n".join(L)
    checar(u"a CUDA adiada e DITA, com o motivo", diz_a_cuda(t), L)
    checar(u"  a lista se chama pelo que e (conferidos pelo canario)",
           L[0].startswith(u"backends conferidos pelo canario: torch_cpu"), L[0])
    checar(u"  e o aviso: a fila ainda decide pela VRAM",
           D.AVISO_DA_FILA in t and u"VRAM" in D.AVISO_DA_FILA)
    checar(u"  nenhuma linha diz «fila pode usar»",
           u"fila pode usar" not in t, L)
    checar(u"  o aprovado de pesquisa aparece fora pela politica",
           u"openvino_gpu: fora pela politica" in t, L)
    checar(u"  e o recusado (sem canario) tambem, com o numero",
           u"openvino_cpu: fora pela politica" in t and u"medido" in t, L)
    velha = u"fila pode usar: %s" % u", ".join(D.admitidos(inv, adiado))
    checar(u"ISCA: a linha antiga omitia a CUDA", not diz_a_cuda(velha)
           and u"cuda" not in velha, velha)
    rodando = D.linhas_da_conferencia(inv, {}, rodando=True)
    checar(u"canario no ar: a CUDA e «NAO CONFERIDO (o canario ainda roda)»",
           any(u"cuda: NAO CONFERIDO (o canario ainda roda)" in l for l in rodando),
           rodando)
    falhou = D.linhas_da_conferencia(inv, {"cuda": D.julgar(
        {"backend": "cuda", "falha": u"CUDA out of memory"})})
    checar(u"filho que falhou: «NAO CONFERIDO (o canario falhou)», com a falha",
           any(u"cuda: NAO CONFERIDO (o canario falhou)" in l
               and u"out of memory" in l for l in falhou), falhou)
    repr_ = D.linhas_da_conferencia(inv, {"cuda": D.julgar(
        _medida(backend="cuda", concordancia=0.99))})
    checar(u"medida que reprovou: «REPROVADO no canario», com o numero",
           any(u"cuda: REPROVADO no canario" in l and u"99.00" in l
               for l in repr_), repr_)
    ok = D.linhas_da_conferencia(inv, {"cuda": D.julgar(_medida(backend="cuda"))})
    checar(u"CUDA aprovada: entra na lista, e nao ha linha de fora dela",
           u"cuda" in ok[0] and not any(l.strip().startswith(u"cuda:") for l in ok), ok)
    v_adi = D._veredito(adiado["cuda"])
    v_fal = D._veredito(D.julgar({"backend": "cuda", "falha": u"OOM"}))
    v_rep = D._veredito(D.julgar(_medida(backend="cuda", concordancia=0.99)))
    checar(u"o veredito do adiado e «ADIADO, nao conferido», nunca «REPROVADO»",
           v_adi.startswith(u"ADIADO, nao conferido") and u"REPROVADO" not in v_adi,
           v_adi)
    checar(u"  o do filho que falhou e «FALHOU, nao conferido»",
           v_fal.startswith(u"FALHOU, nao conferido") and u"REPROVADO" not in v_fal,
           v_fal)
    checar(u"  e «REPROVADO» fica so para a medida que reprovou",
           v_rep.startswith(u"REPROVADO - concordancia"), v_rep)
    r = D.resumo_da_conferencia(inv, adiado)
    checar(u"o resumo do bloco diz a CUDA de fora e o aviso, sem «fila:»",
           u"cuda NAO CONFERIDO (adiado)" in r and D.AVISO_DA_FILA in r
           and u"| fila:" not in r, r)
    checar(u"  e e ASCII (o bloco se cola num chat)", all(ord(c) < 128 for c in r))
    Lx = D.linhas(dict(inv, cpu={"nome": "i7", "fisicos": 10, "logicos": 12}),
                  canarios=adiado)
    checar(u"`linhas` (o log do arranque) usa a mesma conferencia",
           diz_a_cuda(u"\n".join(Lx)) and not any(u"fila pode usar" in l for l in Lx),
           Lx[-4:])
    velho = dict(D.ULTIMO)
    try:
        D.ULTIMO.update(diagnostico=inv, canarios=None, canario_rodando=True)
        c = D.conferencia_atual()
        checar(u"conferencia_atual: com o canario rodando, a CUDA e «rodando»",
               c and [f for f in c["fora"] if f["backend"] == "cuda"
                      and f["estado"] == "rodando"], c)
        D.ULTIMO.update(diagnostico=None)
        checar(u"  sem diagnostico: None («nao sei» nao e «so CPU»)",
               D.conferencia_atual() is None)
    finally:
        D.ULTIMO.clear()
        D.ULTIMO.update(velho)


def teste_a_regra_de_threads():
    secao(u"9e · a regra de threads: do tamanho do que foi medido")
    casos = [
        ({"fisicos": 10, "logicos": 12}, 12, u"i7-1355U (o medido)"),
        ({"fisicos": 10, "logicos": 10}, 10, u"10 nucleos sem SMT"),
        ({"fisicos": 8, "logicos": 16}, None, u"8C/16T (SMT simetrico): 8 fisicos"),
        ({"fisicos": 12, "logicos": 24}, 12, u"12C/24T: os fisicos"),
        ({"fisicos": 16, "logicos": 32}, 12, u"16C/32T: fisicos, ate 12"),
        ({"fisicos": 24, "logicos": 32}, 12, u"hibrida grande: ate 12"),
        ({"fisicos": 4, "logicos": 8}, None, u"4C/8T: fica o 8"),
        ({"fisicos": 6, "logicos": 6}, None, u"6 nucleos: nao desce do 8"),
        ({"fisicos": None, "logicos": 12}, None, u"fisicos nao lidos: fica o 8"),
    ]
    for topo, esperado, nome in casos:
        r = D.regra_de_threads(topo)
        checar(u"%s -> %s" % (nome, esperado if esperado else u"o 8 da biblioteca"),
               r["n"] == esperado and r["motivo"], r)
    checar(u"nunca acima do maior numero medido (%d)" % D.TETO_MEDIDO_DE_THREADS,
           all((D.regra_de_threads(t)["n"] or 0) <= D.TETO_MEDIDO_DE_THREADS
               for t, _e, _n in casos))
    checar(u"  e nunca abaixo do 8 da biblioteca (ou None = o 8)",
           all(D.regra_de_threads(t)["n"] in (None,) or
               D.regra_de_threads(t)["n"] > D.THREADS_DA_BIBLIOTECA
               for t, _e, _n in casos))
    with _Troca(D, TETO_MEDIDO_DE_THREADS=10 ** 6):
        sem_teto = D.regra_de_threads({"fisicos": 24, "logicos": 32})["n"]
    checar(u"ISCA: sem o teto medido, 32 logicos iriam a 32", sem_teto == 32, sem_teto)
    checar(u"threads_para_o_nnunet e a mesma regra",
           D.threads_para_o_nnunet({"fisicos": 10, "logicos": 12}) == 12
           and D.threads_para_o_nnunet({"fisicos": 8, "logicos": 16}) is None)
    checar(u"o motivo e ASCII (vai a linha RADAI|remendo do envelope)",
           all(all(ord(c) < 128 for c in D.regra_de_threads(t)["motivo"])
               for t, _e, _n in casos))
    with _Troca(D, topologia_da_cpu=lambda: (_ for _ in ()).throw(OSError("x"))):
        r = D.regra_de_threads()
    checar(u"a topologia que levanta: None e dito, sem levantar",
           r["n"] is None and u"OSError" in r["motivo"], r)
    checar(u"nesta maquina (%s)" % D.descrever_cpu(D.topologia_da_cpu()),
           D.regra_de_threads()["motivo"], D.regra_de_threads())


def teste_as_linhas_nomeiam_a_placa():
    secao(u"linhas do log: ASCII, e a placa que nao e NVIDIA nomeada")
    inv = {"placas": [D._placa({"nome": "Intel(R) Iris(R) Xe Graphics",
                                "fabricante": "Intel Corporation",
                                "driver": "32.0.101.7076", "ram": 2147479552,
                                "pnp": "PCI\\VEN_8086&DEV_A7A1"}, {})],
           "cpu": {"fisicos": 10, "logicos": 12, "classes": {1: 2, 0: 8},
                   "nome": "i7-1355U"},
           "backends": _inv()["backends"]}
    L = D.linhas(inv, canarios={})
    t = u"\n".join(L)
    checar(u"a Iris Xe e nomeada, com «o TotalSegmentator nao usa»",
           u"Iris(R) Xe" in t and u"nao usa" in t, L[0])
    checar(u"a CPU diz fisicos, logicos e hibrida", u"hibrida" in t)
    checar(u"cada backend tem linha com a politica",
           all((u"backend %s:" % b) in t for b in D.BACKENDS))
    checar(u"sem candidato, o canario diz que nao ha o que conferir",
           u"nenhum backend alem do PyTorch CPU" in t)
    checar(u"tudo ASCII (o console da estacao e cp850)",
           all(all(ord(c) < 128 for c in l) for l in L),
           [l for l in L if any(ord(c) > 127 for c in l)][:1])


def teste_o_canario_de_verdade():
    secao(u"10 · o canario de verdade (so com o runtime do pacote)")
    py = os.environ.get("RADAI_PYTHON_BUNDLE") or u""
    pesos = os.environ.get("RADAI_PESOS_CANARIO") or u""
    if not (py and os.path.isfile(py) and D.pasta_do_canario(pesos)):
        print(u"  (pulado: defina RADAI_PYTHON_BUNDLE e RADAI_PESOS_CANARIO "
              u"para rodar a rede de verdade)")
        return
    r = D.canario("torch_cpu", python_exe=py, pasta_pesos=pesos, repeticoes=1,
                  baixa_prioridade=False)
    checar(u"o canario PyTorch CPU roda no filho", not r.get("falha"),
           r.get("falha") or r.get("traceback", "")[-300:])
    checar(u"  o fantoma do filho e o de fabrica",
           r.get("fantoma_sha256") == D.FANTOMA_SHA256, r.get("fantoma_sha256"))
    checar(u"  a referencia exercita a rede (>= %d classes)" % D.CLASSES_MINIMAS,
           sum(1 for c in r.get("contagem_ref") or [] if c) >= D.CLASSES_MINIMAS,
           r.get("contagem_ref"))
    checar(u"  e bate a referencia de fabrica", r.get("fabrica") == u"identica",
           (r.get("fabrica"), r.get("sha256_ref")))
    checar(u"  aprovado contra si mesmo (identico)", r.get("aprovado")
           and u"identico" in (r.get("motivo") or u""), r.get("motivo"))


_CHAVES_PROIBIDAS = ("traceback", "pid", "saida", "erro", "stdout", "stderr")


def _o_que_nao_e_medida(d, onde=u""):
    achados = []
    if isinstance(d, dict):
        for k, v in d.items():
            if str(k).lower() in _CHAVES_PROIBIDAS:
                achados.append(u"%s/%s (chave)" % (onde, k))
            achados.extend(_o_que_nao_e_medida(v, u"%s/%s" % (onde, k)))
    elif isinstance(d, list):
        for i, v in enumerate(d):
            achados.extend(_o_que_nao_e_medida(v, u"%s[%d]" % (onde, i)))
    elif isinstance(d, str):
        if u"Traceback" in d or u'File "' in d:
            achados.append(u"%s (traceback no texto)" % onde)
    return achados


def teste_o_cache_so_guarda_medida_varrido():
    secao(u"W2E · o cache so guarda medida (varrido)")
    base = _cleanup.temporaria("radai_teste_devices_")
    pesos = os.path.join(base, "pesos")
    modelo = os.path.join(pesos, "Dataset831_x_1830subj",
                          "nnUNetTrainerNoMirroring__nnUNetPlans__3d_fullres")
    os.makedirs(os.path.join(modelo, "fold_0"))
    io.open(os.path.join(modelo, "plans.json"), "w").write(u"{}")
    io.open(os.path.join(modelo, "fold_0", "checkpoint_final.pth"), "wb").write(b"x")

    def canario_falso(b, **kw):
        if b == "xpu":
            return D.julgar({"backend": b, "falha": u"RuntimeError: sem VRAM",
                             "traceback": u'Traceback (most recent call last):\n'
                                          u'  File "C:\\x\\radai_devices.py"'})
        return D.julgar(_medida(backend=b))
    inv = _inv(openvino_gpu=True, xpu=True)
    cache = os.path.join(base, "canario_varrido.json")
    with _Troca(D, canario=canario_falso,
                memoria=lambda: {"livre_mb": 20000, "total_mb": 32000}):
        r = D.rodar_canarios(inv, pasta_pesos=pesos, cache=cache)
    cont = json.load(io.open(cache, encoding="utf-8"))
    checar(u"a partida tinha uma falha COM traceback e uma medida",
           r.get("xpu", {}).get("traceback") and r.get("openvino_gpu", {})
           .get("aprovado"), sorted(r))
    checar(u"o JSON gravado nao tem traceback, PID nem saida de processo",
           not _o_que_nao_e_medida(cont), _o_que_nao_e_medida(cont))
    checar(u"  e a falha ficou so como lembranca (motivo curto, sem traceback)",
           "xpu" not in cont and cont.get(D.CHAVE_FALHAS, {}).get("xpu")
           and set(cont[D.CHAVE_FALHAS]["xpu"]) <= {"quando", "impressao",
                                                    "motivo"},
           cont.get(D.CHAVE_FALHAS))
    velho = {"xpu": {"backend": "xpu", "aprovado": False, "impressao": "x",
                     "falha": u"RuntimeError", "traceback": u"Traceback (most"
                     u" recent call last):"}}
    checar(u"ISCA: a varredura ACUSA o registro da primeira versao (falha com "
           u"traceback)", _o_que_nao_e_medida(velho), velho)


def teste_a_nvidia_cruzada_com_o_torch():
    secao(u"W2E · a NVIDIA cruzada com a sonda do torch")
    placa = lambda: D._placa({"nome": "NVIDIA Quadro P2000",
                              "fabricante": "NVIDIA", "driver": "472.98",
                              "pnp": "PCI\\VEN_10DE&DEV_1C30"}, {})
    sem = {"importa": True, "versao": "2.5.1+cu121", "cuda": "12.1",
           "cuda_disponivel": False}
    com = dict(sem, cuda_disponivel=True, cuda_placas=["Quadro P2000 (5120 MiB)"])
    bk_sem = D.backends_das_sondas({"torch": sem})
    bk_com = D.backends_das_sondas({"torch": com})
    p = D.cruzar_com_o_torch([placa()], bk_sem)[0]
    checar(u"torch sem CUDA: a NVIDIA diz que o torch NAO a alcanca, com o motivo",
           p["o_ts_usa"] is False and u"nao a alcanca" in p["frase"]
           and u"indisponivel" in p["frase"] and u"roda na CPU" in p["frase"], p)
    checar(u"  e a frase da tela, sem acento, e a do log sem o motivo",
           _sem_acento(p["frase_na_tela"]) == p["frase"].rsplit(u" (", 1)[0],
           (p["frase_na_tela"], p["frase"]))
    p2 = D.cruzar_com_o_torch([placa()], bk_com)[0]
    checar(u"torch COM CUDA: «o TotalSegmentator usa (CUDA)»",
           p2["o_ts_usa"] is True and p2["frase"] == u"o TotalSegmentator usa (CUDA)",
           p2)
    p3 = D.cruzar_com_o_torch([placa()], {})[0]
    checar(u"ISCA: sem a sonda do torch, a frase e a do fabricante (a de antes)",
           p3["o_ts_usa"] is True and u"usa (CUDA)" in p3["frase"], p3)
    iris = D._placa({"nome": "Intel(R) Iris(R) Xe Graphics",
                     "pnp": "PCI\\VEN_8086&DEV_A7A1"}, {})
    p4 = D.cruzar_com_o_torch([iris], bk_sem)[0]
    checar(u"a placa que nao e NVIDIA nao muda", u"nao usa" in p4["frase"], p4)
    win = {"placas": [placa()], "cpu_cim": [], "falha": u"", "fonte": u"CIM"}
    with _Troca(D, inventario_windows=lambda **k: win,
                placas_nvidia=lambda **k: {"placas": [], "falha": u"x"},
                topologia_da_cpu=lambda: {"fisicos": 4, "logicos": 8},
                memoria=lambda: {},
                sondar=lambda fam, *a, **k: {"familia": fam, "importa": False}):
        inv = D.inventario(sondas_prontas={"torch": sem})
    checar(u"inventario(): a P2000 sem CUDA no torch sai «nao a alcanca» no log",
           any(u"Quadro P2000" in l and u"nao a alcanca" in l
               for l in D.linhas(inv)), D.linhas(inv)[:1])
    import ast
    arv = ast.parse(io.open(_componentes.fonte("app/radai_devices.py"),
                            encoding="utf-8").read())
    fn = next(n for n in ast.walk(arv) if isinstance(n, ast.FunctionDef)
              and n.name == "inventario")
    checar(u"AST: inventario() chama cruzar_com_o_torch (ancora no ponto)",
           any(isinstance(n, ast.Call) and getattr(n.func, "id", "")
               == "cruzar_com_o_torch" for n in ast.walk(fn)))


def _sem_acento(t):
    import unicodedata
    return unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode("ascii")


def teste_a_integrada_e_pelo_nome():
    secao(u"W2E · a placa integrada e reconhecida pelo nome")
    for nome, pnp, esperado in (
            ("Intel(R) Iris(R) Xe Graphics", "PCI\\VEN_8086&DEV_A7A1", True),
            ("Intel(R) UHD Graphics 770", "PCI\\VEN_8086&DEV_4680", True),
            ("Intel(R) HD Graphics 620", "PCI\\VEN_8086&DEV_5916", True),
            ("Intel(R) Arc(TM) Graphics", "PCI\\VEN_8086&DEV_7D55", True),
            ("Intel(R) Arc(TM) 140V GPU (16GB)", "PCI\\VEN_8086&DEV_64A0", True),
            ("Intel(R) Arc(TM) A770 Graphics", "PCI\\VEN_8086&DEV_56A0", False),
            ("Intel(R) Arc(TM) B580 Graphics", "PCI\\VEN_8086&DEV_E20B", False),
            ("AMD Radeon(TM) Graphics", "PCI\\VEN_1002&DEV_1638", True),
            ("AMD Radeon(TM) 780M", "PCI\\VEN_1002&DEV_15BF", True),
            ("AMD Radeon RX 7600", "PCI\\VEN_1002&DEV_7480", False),
            ("NVIDIA RTX A2000", "PCI\\VEN_10DE&DEV_2531", False)):
        p = D._placa({"nome": nome, "pnp": pnp}, {})
        checar(u"%s: %s" % (nome, u"integrada" if esperado else u"dedicada"),
               p["integrada"] is esperado, p["integrada"])
    arc = D._placa({"nome": "Intel(R) Arc(TM) A770 Graphics",
                    "pnp": "PCI\\VEN_8086&DEV_56A0", "ram": 17163091968}, {})
    checar(u"ISCA: a Arc A770 e Intel (a regra antiga, pelo fabricante, a "
           u"marcaria integrada)", arc["vendor"] == "intel"
           and not arc["integrada"], arc)
    checar(u"  e a linha dela nao diz «compartilhada»",
           not any(u"compartilhada" in l for l in D.linhas(
               {"placas": [arc], "backends": {}, "cpu": {}})
               if u"A770" in l))


def teste_device_cpu_tira_a_placa_do_canario():
    secao(u"W2E · DEVICE=cpu tira a placa do canario")
    sondas = {"torch": {"importa": True, "versao": "2.5.1+cu121", "cuda": "12.1",
                        "cuda_disponivel": True, "xpu_disponivel": True,
                        "xpu_placas": ["Arc"]},
              "openvino": {"importa": True, "versao": "2026.4.0",
                           "dispositivos": {"CPU": "i7", "GPU": "Iris"}}}
    inv = {"backends": D.backends_das_sondas(sondas), "placas": [], "cpu": {}}
    todos = D.candidatos_ao_canario(inv)
    checar(u"DEVICE=auto: cuda, xpu e openvino_gpu sao candidatos",
           {"cuda", "xpu", "openvino_gpu"} <= set(todos), todos)
    for dev in ("cpu", "CPU", " cpu "):
        c = D.candidatos_ao_canario(inv, dev)
        checar(u"DEVICE=%r: nenhum backend de placa" % dev,
               not (set(c) & set(D.BACKENDS_DE_PLACA)), c)
    chamados = []

    def canario_falso(b, **kw):
        chamados.append(b)
        return D.julgar(_medida(backend=b))
    with _Troca(D, canario=canario_falso,
                memoria=lambda: {"livre_mb": 20000, "total_mb": 32000}):
        D.rodar_canarios(inv, pasta_pesos=None, cache=None, device="cpu")
        n_cpu = list(chamados)
        del chamados[:]
        D.rodar_canarios(inv, pasta_pesos=None, cache=None, device="auto")
    checar(u"rodar_canarios(device=cpu): o filho da CUDA NAO e chamado",
           "cuda" not in n_cpu and "xpu" not in n_cpu, n_cpu)
    checar(u"ISCA: com DEVICE=auto, o filho da CUDA e chamado",
           "cuda" in chamados, chamados)
    fora = dict((f["backend"], f["estado"])
                for f in D.conferencia(inv, {}, device="cpu")["fora"])
    checar(u"a conferencia diz DEVICE=cpu para a CUDA (e a xpu)",
           fora.get("cuda") == "device_cpu" and fora.get("xpu") == "device_cpu",
           fora)


def main():
    print(u"test_devices | o inventario de computacao e o canario dos backends")
    for t in (teste_o_nvidia_smi_e_uma_regra_so,
              teste_toda_placa_e_nomeada,
              teste_o_inventario_le_as_duas_formas_e_cai_no_wmic,
              teste_a_cpu_diz_fisicos_e_logicos,
              teste_as_sondas_rodam_no_filho,
              teste_o_fantoma_e_o_mesmo_em_qualquer_numpy,
              teste_o_juiz_do_canario,
              teste_so_o_admitido_entra_na_fila,
              teste_o_cache_do_canario,
              teste_a_falha_do_canario_nao_fica_no_cache,
              teste_o_limiar_de_ram_e_por_backend,
              teste_a_lista_nao_se_diz_da_fila,
              teste_a_regra_de_threads,
              teste_as_linhas_nomeiam_a_placa,
              teste_o_cache_so_guarda_medida_varrido,
              teste_a_nvidia_cruzada_com_o_torch,
              teste_a_integrada_e_pelo_nome,
              teste_device_cpu_tira_a_placa_do_canario,
              teste_o_canario_de_verdade):
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
