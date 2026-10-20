# -*- coding: utf-8 -*-
import io
import json
import os
import re
import sys
import tempfile
import time

_TMP_BATERIA = tempfile.mkdtemp(prefix="radai_noite_tmp_")
for _k in ("RADAI_TMP", "TEMP", "TMP", "TMPDIR"):
    os.environ[_k] = _TMP_BATERIA
tempfile.tempdir = None
_VIGIAS = []


def _apagar_tmp_da_bateria():
    import shutil
    for m in _VIGIAS:
        fh = getattr(m, "_LOG_FH", None)
        if fh is not None:
            try:
                fh.close()
            except Exception as e:
                print(u"  (nao consegui fechar o log de uma instancia: %s)" % e)
        m._LOG_FH = None
        m._LOG_TENTADO = True
    shutil.rmtree(_TMP_BATERIA, ignore_errors=True)


import atexit
atexit.register(_apagar_tmp_da_bateria)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _cleanup
import _componentes
_cleanup.adotar_prefixo('radai_noite_')

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_ACERVO_TESTE = tempfile.mkdtemp(prefix="radai_noite_acervo_")
_cleanup.adotar_prefixo('radai_noite_acervo_')
os.environ["RADAI_CALIB_DIR"] = _ACERVO_TESTE

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(RAIZ, "app")
sys.path.insert(0, APP)

_ok = 0
_falhas = []


def checar(nome, cond, detalhe=u""):
    global _ok
    if cond:
        _ok += 1
        print(u"    OK     %s" % nome)
    else:
        _falhas.append(nome)
        print(u"    FALHA  %s  %s" % (nome, detalhe))


def secao(t):
    print(u"\n  ── %s %s" % (t, u"─" * max(0, 60 - len(t))))


def temp():
    return tempfile.mkdtemp(prefix="radai_noite_")


def fonte(nome):
    return io.open(_componentes.fonte("app/" + nome), encoding="utf-8").read()


class LimpadorFalso(object):

    def __init__(self, estados, nega=()):
        self.estados = dict(estados)
        self.nega = set(nega)
        self.parados = []
        self.iniciados = []

    def estado_dos_servicos(self):
        return [{"nome": n, "porque": u"—", "estado": e}
                for n, e in sorted(self.estados.items())]

    def parar_servico(self, nome):
        if nome in self.nega:
            return {"ok": False, "msg": u"%s: o Windows negou." % nome}
        self.parados.append(nome)
        self.estados[nome] = "parado"
        return {"ok": True, "msg": u"%s: parado." % nome}

    def iniciar_servico(self, nome):
        if nome in self.nega:
            return {"ok": False, "msg": u"%s: o Windows negou." % nome}
        self.iniciados.append(nome)
        self.estados[nome] = "rodando"
        return {"ok": True, "msg": u"%s: religado." % nome}


def com_limpador(falso):
    sys.modules["radai_cleaner"] = falso
    return falso


def teste_o_modulo_e_so_stdlib():
    secao(u"o modulo do turno e so biblioteca padrao")
    import ast
    f = fonte("radai_overnight.py")
    arvore = ast.parse(f)
    topo = []
    for no in arvore.body:
        if isinstance(no, ast.Import):
            topo += [a.name.split(".")[0] for a in no.names]
        elif isinstance(no, ast.ImportFrom) and no.module:
            topo.append(no.module.split(".")[0])
    PADRAO = {"json", "os", "socket", "time", "hashlib", "sys", "re"}
    fora = [m for m in topo if m not in PADRAO]
    checar(u"nenhum import de topo fora da stdlib", not fora, str(fora))
    checar(u"e o limpador entra DENTRO das funcoes",
           "radai_cleaner" not in topo and "import radai_cleaner" in f,
           u"no topo, ele impediria o vigia de subir")
    w = fonte("radai_watcher.py")
    checar(u"e o arranque do vigia chama a restauracao",
           "restaurar_se_pendente(log=wlog)" in w)
    i = w.find("def main()")
    checar(u"  dentro do `main`", "restaurar_se_pendente" in w[i:])


def teste_o_turno_abre_e_fecha():
    secao(u"o turno abre, pausa, e o fim devolve a estacao")
    import radai_overnight as ov
    d = temp()

    lp = com_limpador(LimpadorFalso({
        "SysMain": "rodando",
        "WSearch": "rodando",
        "DiagTrack": "parado",
        "MapsBroker": "ausente",
    }))
    r = ov.iniciar(pausar_servicos=True, pasta=d)
    checar(u"abriu", r["ok"] and not r["ja_estava"])
    checar(u"parou os dois que estavam rodando",
           sorted(lp.parados) == ["SysMain", "WSearch"], str(lp.parados))
    checar(u"  e nao tocou no que ja estava parado",
           "DiagTrack" not in lp.parados)
    checar(u"  nem no que nao existe", "MapsBroker" not in lp.parados)

    e = ov.estado(d)
    checar(u"a tela ve o turno aberto", e["ativo"])
    checar(u"  e ve QUAIS estao pausados",
           sorted(e["pausados"]) == ["SysMain", "WSearch"], str(e["pausados"]))

    r2 = ov.encerrar(pasta=d)
    checar(u"encerrou", r2["ok"])
    checar(u"religou os dois", sorted(lp.iniciados) == ["SysMain", "WSearch"],
           str(lp.iniciados))
    checar(u"e NAO religou o que ja estava parado antes da noite",
           "DiagTrack" not in lp.iniciados,
           u"devolver a estacao e devolver o que estava")
    checar(u"o registro sumiu no fim", not ov.ha_registro(d))
    checar(u"e a tela volta a dizer que nao ha turno", not ov.estado(d)["ativo"])


def teste_o_registro_nasce_antes_da_primeira_parada():
    secao(u"o registro e gravado ANTES de parar qualquer coisa")
    import radai_overnight as ov
    d = temp()
    visto = {"antes_da_primeira_parada": None}

    class Espia(LimpadorFalso):
        def parar_servico(self, nome):
            if visto["antes_da_primeira_parada"] is None:
                visto["antes_da_primeira_parada"] = ov.ha_registro(d)
            return LimpadorFalso.parar_servico(self, nome)

    com_limpador(Espia({"SysMain": "rodando", "WSearch": "rodando"}))
    ov.iniciar(pausar_servicos=True, pasta=d)
    checar(u"o registro ja existia quando o primeiro servico foi parado",
           visto["antes_da_primeira_parada"] is True,
           u"gravar depois perde justamente o que a queda interrompeu")

    dado = json.loads(io.open(ov.caminho_do_registro(d),
                              encoding="utf-8").read())
    acoes = dict((s["nome"], s["acao"]) for s in dado["servicos"])
    checar(u"e ele anota a acao de cada um",
           acoes.get("SysMain") == "parado" and acoes.get("WSearch") == "parado",
           str(acoes))
    ov.encerrar(pasta=d)


def teste_a_queda_de_energia():
    secao(u"a noite que a queda de energia interrompeu")
    import radai_overnight as ov
    d = temp()
    lp = com_limpador(LimpadorFalso({"SysMain": "rodando",
                                     "WSearch": "rodando"}))
    ov.iniciar(pausar_servicos=True, pasta=d)
    lp.iniciados = []
    checar(u"o registro sobreviveu a queda", ov.ha_registro(d))

    linhas = []
    r = ov.restaurar_se_pendente(log=linhas.append, pasta=d)
    checar(u"o arranque seguinte percebe", r["havia"] is True)
    checar(u"  e devolve os servicos",
           sorted(lp.iniciados) == ["SysMain", "WSearch"], str(lp.iniciados))
    checar(u"  e diz no log que a noite foi INTERROMPIDA",
           any("interrompida" in l for l in linhas), " | ".join(linhas)[:200])
    checar(u"  e limpa o registro", not ov.ha_registro(d))
    lp.iniciados = []
    r2 = ov.restaurar_se_pendente(pasta=d)
    checar(u"o arranque seguinte a esse nao mexe em nada",
           r2["havia"] is False and not lp.iniciados)


def teste_abrir_duas_vezes_nao_perde_o_estado_original():
    secao(u"abrir duas vezes nao apaga o estado original")
    import radai_overnight as ov
    d = temp()
    lp = com_limpador(LimpadorFalso({"SysMain": "rodando"}))
    ov.iniciar(pausar_servicos=True, pasta=d)
    r = ov.iniciar(pausar_servicos=True, pasta=d)
    checar(u"o segundo diz que ja estava aberto", r["ja_estava"] is True)
    dado = json.loads(io.open(ov.caminho_do_registro(d),
                              encoding="utf-8").read())
    checar(u"e o registro ainda diz que o SysMain ESTAVA RODANDO",
           dado["servicos"][0]["antes"] == "rodando",
           u"sobrescrever aqui gravaria `parado`, e de manha ninguem o religa")
    lp.iniciados = []
    ov.encerrar(pasta=d)
    checar(u"por isso o fim ainda o religa", lp.iniciados == ["SysMain"])


def teste_sem_registro_nao_para_nada():
    secao(u"sem conseguir gravar o registro, nada e pausado")
    import radai_overnight as ov
    d = temp()
    lp = com_limpador(LimpadorFalso({"SysMain": "rodando"}))
    real = ov._gravar
    try:
        ov._gravar = lambda dado, pasta="": False
        r = ov.iniciar(pausar_servicos=True, pasta=d)
    finally:
        ov._gravar = real
    checar(u"o turno recusa abrir", r["ok"] is False)
    checar(u"e NENHUM servico foi parado", lp.parados == [], str(lp.parados))


def teste_o_negado_nao_vira_pausado():
    secao(u"servico que o Windows negou nao entra como pausado")
    import radai_overnight as ov
    d = temp()
    com_limpador(LimpadorFalso({"SysMain": "rodando", "WSearch": "rodando"},
                               nega=("WSearch",)))
    ov.iniciar(pausar_servicos=True, pasta=d)
    e = ov.estado(d)
    checar(u"so o que parou de verdade conta como pausado",
           e["pausados"] == ["SysMain"], str(e["pausados"]))
    dado = json.loads(io.open(ov.caminho_do_registro(d),
                              encoding="utf-8").read())
    acoes = dict((s["nome"], s["acao"]) for s in dado["servicos"])
    checar(u"e o que falhou fica registrado como falhou",
           acoes.get("WSearch") == "falhou", str(acoes))
    ov.encerrar(pasta=d)


def teste_o_que_nao_religou_nao_vira_alarme_eterno():
    secao(u"o que nao religou fica dito, e nao vira alarme eterno")
    import radai_overnight as ov
    d = temp()
    lp = com_limpador(LimpadorFalso({"SysMain": "rodando",
                                     "WSearch": "rodando"}))
    ov.iniciar(pausar_servicos=True, pasta=d)
    lp.nega = set(["WSearch"])
    linhas = []
    r = ov.encerrar(log=linhas.append, pasta=d)
    checar(u"religou o que deu", r["religados"] == 1, str(r["religados"]))
    checar(u"e diz QUAL nao voltou",
           any("WSearch" in l for l in linhas), " | ".join(linhas)[:220])
    checar(u"  dizendo que ele volta no proximo arranque",
           any(u"próximo arranque" in l for l in linhas),
           " | ".join(linhas)[:220])
    checar(u"e o registro sai assim mesmo", not ov.ha_registro(d),
           u"guardar faria todo arranque anunciar a mesma noite para sempre")

    d2 = temp()
    com_limpador(LimpadorFalso({"SysMain": "rodando"}))
    ov.iniciar(pausar_servicos=True, pasta=d2)
    sys.modules.pop("radai_cleaner", None)
    class Quebrado(object):
        def __getattr__(self, _):
            raise ImportError("limpador quebrado")
    sys.modules["radai_cleaner"] = Quebrado()
    try:
        r2 = ov.encerrar(pasta=d2)
    finally:
        sys.modules.pop("radai_cleaner", None)
    checar(u"sem conseguir nem tentar, o registro FICA",
           ov.ha_registro(d2),
           u"aqui o proximo arranque tem o que tentar de verdade")
    checar(u"  e o resultado diz que nao deu", r2["ok"] is False)


def teste_a_lista_de_religar_e_fechada():
    secao(u"religar tem lista fechada, e a trava e no modulo")
    sys.modules.pop("radai_cleaner", None)
    import radai_cleaner as LP
    checar(u"a funcao existe", hasattr(LP, "iniciar_servico"))
    for nome in ("Spooler", "WinDefend", "Vitrea", "", "SysMain "):
        r = LP.iniciar_servico(nome)
        checar(u"  recusa `%s`" % (nome or "(vazio)"), r["ok"] is False)
    f = fonte("radai_cleaner.py")
    i = f.find("def iniciar_servico")
    corpo = f[i:f.find("\ndef ", i + 10)]
    checar(u"e usa a MESMA lista de permitidos do parar",
           "_NOMES_SERVICOS" in corpo)
    checar(u"e a mesma lista de protegidos", "_protegido(" in corpo)
    checar(u"e a chamada e `sc start`", '"sc", "start", nome' in corpo)
    codigo = "\n".join(l for l in corpo.splitlines()
                       if not l.lstrip().startswith("#"))
    a = codigo.find('u"""')
    if a >= 0:
        codigo = codigo[:a] + codigo[codigo.find('"""', a + 4) + 3:]
    checar(u"e nao mexe no tipo de inicializacao",
           "sc config" not in codigo and "start=" not in codigo,
           u"`sc start`, nunca `sc config start= auto`")


def teste_o_parcial_leva_o_nome_de_quem_escreve():
    secao(u"o rascunho leva o nome de quem escreve")
    import radai_sets as rc
    alvo = "RS_RadAI_20260904_12345678.dcm"
    p = rc.nome_parcial(alvo)
    checar(u"comeca pelo alvo", p.startswith(alvo))
    checar(u"e termina em .parcial", p.endswith(".parcial"))
    checar(u"e nao e o nome fixo antigo", p != alvo + ".parcial",
           u"nome fixo e o defeito")
    checar(u"leva o pid deste processo", ("%d" % os.getpid()) in p)
    meio = p[len(alvo) + 1:-len(".parcial") - 1]
    checar(u"e so caractere seguro no nome",
           all(c.isalnum() or c in "-_." for c in meio), meio)
    velho = os.environ.get("COMPUTERNAME")
    try:
        os.environ["COMPUTERNAME"] = u"SALA 2 · RÁDIO/CT"
        sujo = rc.nome_parcial(alvo)
        checar(u"nome de maquina com acento, espaco e barra nao vaza",
               all(c not in sujo[len(alvo):] for c in u" ·/Á"), sujo)
    finally:
        if velho is None:
            os.environ.pop("COMPUTERNAME", None)
        else:
            os.environ["COMPUTERNAME"] = velho

    for arq, quantos in (("radai_watcher.py", 1), ("radai_output.py", 1)):
        f = fonte(arq)
        checar(u"  `%s` usa nome_parcial" % arq, "nome_parcial(" in f)
        checar(u"  `%s` nao monta o `.parcial` a mao" % arq,
               '+ ".parcial"' not in f and "+ '.parcial'" not in f
               and 'name + ".parcial"' not in f,
               u"nome fixo volta em uma linha")

    def _chama_dentro(fonte_py, funcao, nome):
        import ast as _ast
        for no in _ast.walk(_ast.parse(fonte_py)):
            if (isinstance(no, (_ast.FunctionDef, _ast.AsyncFunctionDef))
                    and no.name == funcao):
                return any(isinstance(c, _ast.Call)
                           and (getattr(c.func, "attr", None) == nome
                                or getattr(c.func, "id", None) == nome)
                           for c in _ast.walk(no))
        return None
    fo = fonte("radai_output.py")
    checar(u"  o gravador do lote (`radai_output._gravar_arquivo`) monta o "
           u"rascunho por `nome_parcial`",
           _chama_dentro(fo, "_gravar_arquivo", "nome_parcial") is True,
           u"e por ele que o «Rodar agora» grava desde a v8.2")
    isca_fo = fo.replace("radai_sets.nome_parcial(alvo)", "alvo + '.x'")
    checar(u"  ISCA: sem `nome_parcial` dentro de `_gravar_arquivo`, a "
           u"checagem acusa", _chama_dentro(isca_fo, "_gravar_arquivo",
                                            "nome_parcial") is False)
    fb = fonte("radai_batch.py")
    checar(u"  e o lote grava PELA porta unica (chama `full_e_oar`)",
           ".full_e_oar(" in fb, u"sem isto o lote teria outro gravador")
    checar(u"  e o lote nao monta `.parcial` a mao",
           '+ ".parcial"' not in fb and "+ '.parcial'" not in fb)

    fm = fonte("engine.py")
    PODEM_TROCAR_ARQUIVO = {
        "estatistica_do_ts": u"grava o config.json do TotalSegmentator, e "
                             u"nao um RTSTRUCT",
    }

    def gravadores(fonte_py):
        import ast as _ast
        arv = _ast.parse(fonte_py)
        docs = set()
        for no in _ast.walk(arv):
            if isinstance(no, (_ast.Module, _ast.FunctionDef,
                               _ast.AsyncFunctionDef, _ast.ClassDef)):
                corpo = getattr(no, "body", None) or []
                if (corpo and isinstance(corpo[0], _ast.Expr)
                        and isinstance(corpo[0].value, _ast.Constant)
                        and isinstance(corpo[0].value.value, str)):
                    docs.add(id(corpo[0].value))

        def _marca(sub):
            if isinstance(sub, _ast.Call):
                f = sub.func
                if isinstance(f, _ast.Attribute):
                    dono = getattr(f.value, "id", "")
                    if dono == "os" and f.attr in ("replace", "rename"):
                        return "os.%s(" % f.attr
                    if dono == "shutil" and f.attr in ("copy2", "copyfile", "move"):
                        return "shutil.%s(" % f.attr
                    if (f.attr in ("replace", "rename") and len(sub.args) == 1
                            and not sub.keywords):
                        return ".%s(<um argumento>)" % f.attr
                elif getattr(f, "id", "") in ("copy2", "copyfile", "move"):
                    return "%s(" % f.id
            elif (isinstance(sub, _ast.Constant) and isinstance(sub.value, str)
                  and ".parcial" in sub.value and id(sub) not in docs):
                return "'.parcial'"
            return None

        achados = []
        dentro = set()
        for no in _ast.walk(arv):
            if not isinstance(no, (_ast.FunctionDef, _ast.AsyncFunctionDef)):
                continue
            for sub in _ast.walk(no):
                dentro.add(id(sub))
                marca = _marca(sub)
                if marca and no.name not in PODEM_TROCAR_ARQUIVO:
                    achados.append("%s: %s" % (no.name, marca))
        for sub in _ast.walk(arv):
            if id(sub) in dentro:
                continue
            marca = _marca(sub)
            if marca:
                achados.append("<modulo>: %s" % marca)
        return sorted(set(achados))
    grava = gravadores(fm)
    checar(u"  `engine.py` nao grava RTSTRUCT (por isso saiu da lista)",
           not grava, u", ".join(grava) or u"nada",
           )
    isca = fm + (u"\n\ndef gravar_rt_de_novo(rt, alvo):\n"
                 u"    import shutil\n"
                 u"    shutil.copy2(rt, alvo + '.parcial')\n"
                 u"    os.replace(alvo + '.parcial', alvo)\n")
    achou = gravadores(isca)
    checar(u"  ISCA: um gravador novo no motor e achado, com o nome da funcao",
           any(a.startswith("gravar_rt_de_novo: os.replace(") for a in achou)
           and any(a.startswith("gravar_rt_de_novo: shutil.copy2(")
                   for a in achou)
           and any(a.startswith("gravar_rt_de_novo: '.parcial'")
                   for a in achou), u", ".join(achou))
    iscas = fm + (u"\n\nfrom shutil import copy2 as _c2\n"
                  u"def isca_copy2_solto(rt, alvo):\n"
                  u"    from shutil import copy2\n"
                  u"    copy2(rt, alvo)\n"
                  u"def isca_path_replace(p, alvo):\n"
                  u"    p.replace(alvo)\n"
                  u"def isca_os_rename(a, b):\n"
                  u"    os.rename(a, b)\n"
                  u"def isca_shutil_move(a, b):\n"
                  u"    shutil.move(a, b)\n"
                  u"def isca_parcial_no_meio(alvo):\n"
                  u"    return alvo + '.parcial_%s' % 1\n"
                  u"GRAVADO_NO_MODULO = shutil.copy2('a', 'b.parcial')\n")
    ach2 = gravadores(iscas)
    for esperado in ("isca_copy2_solto: copy2(",
                     "isca_path_replace: .replace(<um argumento>)",
                     "isca_os_rename: os.rename(",
                     "isca_shutil_move: shutil.move(",
                     "isca_parcial_no_meio: '.parcial'",
                     "<modulo>: shutil.copy2("):
        checar(u"  ISCA: a forma `%s` e achada" % esperado,
               esperado in ach2, u", ".join(a for a in ach2
                                            if not a.startswith("gravar_"))[:240])
    limpo = gravadores(u'def f(s):\n    u"""o `.parcial` de antes"""\n'
                       u'    return s.replace("a", "b")\n')
    checar(u"  e `str.replace` e a docstring que cita `.parcial` nao sao gravador",
           limpo == [], str(limpo))
    checar(u"  e nao expoe gravador de torax",
           "def entregar_torax(" not in fm,
           u"se voltar, ele tem de usar `nome_parcial` e voltar a lista acima")


def teste_o_caminho_do_paciente_nao_vai_para_o_share():
    secao(u"o caminho da serie e o UID inteiro nao vao para o arquivo")
    f = fonte("radai_watcher.py")
    checar(u"ha uma funcao unica para a truncagem",
           "def sem_caminho_nem_uid" in f)
    i = f.find("def sem_caminho_nem_uid")
    corpo = f[i:f.find("\ndef ", i + 10)]
    checar(u"  e ela tira os dois campos",
           '"sdir"' in corpo and '"uid_cheio"' in corpo)

    j = f.find("def salvar_status")
    sv = f[j:f.find("\ndef ", j + 10)]
    checar(u"`salvar_status` passa pela funcao",
           "sem_caminho_nem_uid(STATE[\"current\"])" in sv,
           u"era `STATE[\"current\"]` cru, e um dos destinos e um share")
    checar(u"  e nao grava mais o dicionario cru",
           '"atual": STATE["current"]' not in sv)

    checar(u"a rota usa a mesma funcao, e nao uma segunda copia",
           f.count("sem_caminho_nem_uid(") >= 3, str(f.count("sem_caminho_nem_uid(")))
    checar(u"  e a copia manual saiu da rota",
           'for _fora in ("sdir", "uid_cheio")' not in f)

    ns = {}
    exec(compile(corpo, "<sem_caminho>", "exec"), ns)
    fn = ns["sem_caminho_nem_uid"]
    saiu = fn({"pid": "P1", "uid": "95678901", "count": 90,
               "sdir": r"\\servidor\exames\ISCA_FANTOMA\CT",
               "uid_cheio": "1.9.999.2.55.3.12345.45678901"})
    checar(u"o caminho da pasta do paciente nao sai", "sdir" not in saiu)
    checar(u"o UID inteiro nao sai", "uid_cheio" not in saiu)
    checar(u"e os 8 digitos continuam saindo", saiu.get("uid") == "95678901")
    checar(u"None continua None", fn(None) is None)
    orig = {"uid": "1", "sdir": "X", "uid_cheio": "Y"}
    fn(orig)
    checar(u"e o STATE original fica intacto (o lock precisa dele)",
           orig.get("sdir") == "X")


def teste_o_status_dir_nao_pode_sincronizar():
    secao(u"o STATUS_DIR nao pode ser pasta que sincroniza")
    f = fonte("radai_watcher.py")
    checar(u"ha a conferencia", "def conferir_status_dir" in f)
    i = f.find("def conferir_status_dir")
    corpo = f[i:f.find("\ndef ", i + 10)]
    checar(u"  e ela usa o detector do projeto, e nao nome de pasta",
           "em_pasta_sincronizada" in corpo,
           u"casar por nome pegava so quem chamasse a pasta de Google Drive")
    checar(u"  e RECUSA, nao so avisa", "_STATUS_DIR_RECUSADO[0] = True" in corpo)
    checar(u"  e falhar em conferir nao tira o painel de quem esta certo",
           "vou " in corpo and "gravar nele assim mesmo" in corpo)

    j = f.find("def salvar_status")
    sv = f[j:f.find("\ndef ", j + 10)]
    checar(u"e o gravador respeita a recusa",
           "_STATUS_DIR_RECUSADO[0]" in sv,
           u"recusar sem parar de gravar seria so um aviso")
    checar(u"o arranque confere", "conferir_status_dir()" in f)
    k = f.find("def recarregar_cfg")
    rc = f[k:f.find("\ndef ", k + 10)]
    checar(u"  e a recarga a quente tambem", "conferir_status_dir()" in rc)
    checar(u"  e ela limpa a recusa antes de reconferir",
           "_STATUS_DIR_RECUSADO[0] = False" in rc,
           u"senao corrigir a pasta na tela nunca voltaria a gravar")
    checar(u"e a tela da frota explica a recusa",
           "sincroniza com a nuvem" in f)


def teste_o_arquivo_de_status_nao_leva_PatientID():
    secao(u"o arquivo de status nao leva PatientID")
    f = fonte("radai_watcher.py")
    i = f.find("def sem_caminho_nem_uid")
    corpo = f[i:f.find(chr(10) + "def ", i + 10)]
    checar(u"a funcao aceita `com_pid`", "com_pid=False" in corpo,
           u"o padrao tem de ser o estrito")
    checar(u"  e o padrao TIRA o pid",
           'if not com_pid:' in corpo and 'fora.pop("pid"' in corpo)

    j = f.find("def salvar_status")
    sv = f[j:f.find(chr(10) + "def ", j + 10)]
    checar(u"`salvar_status` nao pede o pid", "com_pid" not in sv,
           u"o arquivo pode ir para uma pasta compartilhada")
    checar(u"e a TELA pede explicitamente",
           "sem_caminho_nem_uid(atual, com_pid=True)" in f,
           u"127.0.0.1, para quem esta na frente do exame")

    ns = {}
    exec(compile(corpo, "<sem_caminho>", "exec"), ns)
    fn = ns["sem_caminho_nem_uid"]
    atual = {"pid": "FANTOMA-0001", "uid": "95678901", "count": 90,
             "sdir": "X", "uid_cheio": "Y"}
    arquivo = fn(dict(atual))
    tela = fn(dict(atual), com_pid=True)
    checar(u"no arquivo, o PatientID nao sai", "pid" not in arquivo, str(arquivo))
    checar(u"  e os 8 digitos do UID continuam saindo",
           arquivo.get("uid") == "95678901")
    checar(u"na tela, ele sai", tela.get("pid") == "FANTOMA-0001")
    checar(u"e nos dois o caminho e o UID inteiro ficam fora",
           "sdir" not in arquivo and "uid_cheio" not in tela)


def teste_a_frota_le_o_status_das_outras():
    secao(u"a frota: as outras estacoes da noite")
    import radai_overnight as ov
    d = temp()
    def grava(nome, dado, idade_min=0.0):
        p = os.path.join(d, nome + ".json")
        io.open(p, "w", encoding="utf-8").write(json.dumps(dado))
        if idade_min:
            t = time.time() - idade_min * 60
            os.utime(p, (t, t))
    grava("PC_A", {"maquina": "PC_A", "concluidas_sessao": 3, "na_fila": 2,
                   "atual": {"pid": "P1", "uid": "12345678"}})
    grava("PC_B", {"maquina": "PC_B", "concluidas_sessao": 1, "na_fila": 0,
                   "atual": None}, idade_min=90)
    io.open(os.path.join(d, "PC_C.json"), "w", encoding="utf-8").write("{quebr")

    ms = ov.frota(d, eu="PC_A")
    checar(u"leu as tres", len(ms) == 3, str(len(ms)))
    por = dict((m["maquina"], m) for m in ms)
    checar(u"a que trabalha aparece trabalhando",
           por["PC_A"]["atual"] is not None and not por["PC_A"]["parada"])
    checar(u"  e ela se reconhece", por["PC_A"]["eu"] is True)
    checar(u"a que nao escreve ha 90 min aparece parada",
           por["PC_B"]["parada"] is True)
    checar(u"a ilegivel entra na lista, marcada",
           por["PC_C"]["legivel"] is False and por["PC_C"]["parada"] is True)
    r = ov.resumo_da_frota(ms)
    checar(u"o resumo conta", r["n"] == 3 and r["trabalhando"] == 1
           and r["paradas"] == 2 and r["concluidas"] == 4, json.dumps(r))
    checar(u"pasta inexistente devolve lista vazia",
           ov.frota(os.path.join(d, "nao_existe")) == [])
    checar(u"e STATUS_DIR vazio tambem", ov.frota("") == [])

    grava("PC_D", {"maquina": "PC_D", "na_fila": 0, "adiadas": 3,
                   "atual": None})
    ms2 = dict((m["maquina"], m) for m in ov.frota(d))
    checar(u"a frota le as adiadas de cada estacao",
           ms2["PC_D"].get("adiadas") == 3 and ms2["PC_A"].get("adiadas") == 0,
           str(ms2["PC_D"]))
    checar(u"  e o resumo as soma", ov.resumo_da_frota(
        list(ms2.values())).get("adiadas") == 3)
    import ast as _ast
    f = fonte("radai_watcher.py")
    ss = [n for n in _ast.walk(_ast.parse(f))
          if isinstance(n, _ast.FunctionDef) and n.name == "salvar_status"]
    chaves = set()
    for n in (_ast.walk(ss[0]) if ss else ()):
        if isinstance(n, _ast.Dict):
            chaves |= set(getattr(k, "value", None) for k in n.keys)
    checar(u"e o vigia grava as adiadas no arquivo de status",
           "adiadas" in chaves, sorted(x for x in chaves if x)[:12])
    hb = [n for n in _ast.walk(_ast.parse(f))
          if isinstance(n, _ast.FunctionDef) and n.name == "bater_heartbeat"]
    grava_no_hb = hb and any(isinstance(c, _ast.Call)
                             and getattr(c.func, "id", "") == "salvar_status"
                             for c in _ast.walk(hb[0]))
    checar(u"e o batimento da serie grava o sinal de vida (a estacao nao "
           u"aparece «parada» no meio de uma serie)", bool(grava_no_hb))


def teste_a_tela_da_noite():
    secao(u"a tela do turno: log, simbolos rodando e o que esta pausado")
    f = fonte("radai_watcher.py")
    checar(u"ha a faixa do turno", 'id="ovFaixa"' in f)
    checar(u"ha o botao de abrir", 'id="btNoite"' in f)
    checar(u"e o de encerrar", 'id="btNoiteFim"' in f)
    checar(u"ha simbolo girando (CSS)", ".ov-gira" in f and "@keyframes ovgira" in f)
    checar(u"e um pulso pintado pelo JavaScript", "OV_PULSO" in f)
    checar(u"  animacao respeita quem pediu para nao animar",
           "prefers-reduced-motion" in f)
    checar(u"a tela lista os servicos pausados", 'id="ovServicos"' in f)
    checar(u"e mostra as outras maquinas", 'id="ovFrota"' in f)

    _liso = f
    for _de, _para in ((u"á", "a"), (u"ã", "a"), (u"ç", "c"),
                       (u"é", "e"), (u"ó", "o")):
        _liso = _liso.replace(_de, _para)
    checar(u"zero pausados aparece dizendo por que",
           "frSemPausa" in f and "Nenhum servico pausado." in _liso)
    checar(u"  e o motivo e nomeado (administrador ou ja parado)",
           "administrador nesta estacao" in _liso
           and "ja estavam parados" in _liso)
    checar(u"  e as duas frases passam pelo dicionario",
           f.count("data-radai-frase") >= 2
           and "uiHTML(os_" in f)
    checar(u"e o que nao religou aparece no fim",
           "d.falhas.length" in f)

    for r in ("/api/overnight/iniciar", "/api/overnight/encerrar",
              "/api/overnight/frota"):
        checar(u"ha a rota %s" % r, '"%s"' % r in f)

    checar(u"com o turno aberto a navegacao fica livre: o portao e o aviso "
           u"de «estação dedicada» sairam",
           "def montar_portao_da_fila" not in f and "dedicada=1" not in f
           and 'id="ovDedicada"' not in f)

    checar(u"durante a noite o `Desligar a fila` some",
           "if(bd && d.overnight) bd.style.display='none'" in f,
           u"seria a saida que nao devolve os servicos")


def teste_a_retomada_e_de_uma_maquina_so():
    secao(u"a retomada de serie travada e de uma maquina so")
    f = fonte("radai_watcher.py")
    i = f.find("def _tomar_lock(")
    tomar = f[i:f.find("\ndef ", i + 10)]
    checar(u"ha uma tomada exclusiva", i >= 0)
    checar(u"  e ela renomeia para um nome proprio",
           ".tomado." in tomar and "os.replace(str(lp)" in tomar)
    checar(u"  com maquina e pid", "MACHINE, os.getpid()" in tomar)
    checar(u"  e falhar em renomear NAO e erro: e a exclusao funcionando",
           "return False" in tomar)

    j = f.find("def claim(")
    corpo = f[j:f.find("\ndef ", j + 10)]
    checar(u"os DOIS ramos de retomada passam por ela",
           corpo.count("_tomar_lock(lp)") == 2,
           str(corpo.count("_tomar_lock(lp)")))
    checar(u"e o `unlink` cru saiu dos dois",
           "lp.unlink()" not in corpo,
           u"apagar para depois criar deixa o buraco onde a segunda entra")

    d = temp()
    origem = os.path.join(d, "uid.lock.json")
    io.open(origem, "w").write("{}")
    a = os.path.join(d, "uid.lock.json.tomado.PC_A.1")
    b = os.path.join(d, "uid.lock.json.tomado.PC_B.2")
    os.replace(origem, a)
    venceu_b = True
    try:
        os.replace(origem, b)
    except OSError:
        venceu_b = False
    checar(u"a segunda renomeacao da mesma origem falha",
           venceu_b is False,
           u"se as duas passassem, as duas maquinas pegariam a serie")
    checar(u"  e a primeira levou o arquivo", os.path.isfile(a))
    checar(u"  e o rastro nao termina em .json (nao vira marcador)",
           not a.endswith(".json"))


def teste_o_batimento_reclama_quando_falha():
    secao(u"o sinal de vida reclama quando nao consegue gravar")
    f = fonte("radai_watcher.py")
    i = f.find("def bater_heartbeat")
    corpo = f[i:f.find("\n    hb = threading.Thread", i)]
    checar(u"o batimento olha o retorno de renovar_lock",
           "if renovar_lock(" in corpo,
           u"chamar e ignorar era o defeito")
    checar(u"  e avisa no log quando falha", "NAO consigo gravar o sinal" in corpo)
    checar(u"  dizendo o risco (outra maquina assume)",
           "outra" in corpo and "assumir" in corpo)
    checar(u"  e so na transicao, nao a cada batida",
           "falhas == 2" in corpo, u"repetir a cada volta enche o log")
    checar(u"  e diz tambem quando volta a funcionar",
           "voltou a ser" in corpo,
           u"silencio na volta e indistinguivel de continuar falhando")

    import re
    hb = re.search(r"^HEARTBEAT_MIN=(\d+)", f, re.M)
    pa = re.search(r"^LOCK_PARADO_MIN=(\d+)", f, re.M)
    checar(u"os dois numeros estao declarados", bool(hb and pa))
    if hb and pa:
        checar(u"e o limite de parado da margem para pelo menos 2 batidas "
               u"perdidas", int(pa.group(1)) >= 2 * int(hb.group(1)),
               u"%s min de batida contra %s min de limite"
               % (hb.group(1), pa.group(1)))


def teste_a_tela_consegue_ligar_a_fila():
    secao(u"a tela consegue ligar a fila (e nao so a rota)")
    f = fonte("radai_watcher.py")

    i = f.find("var bl=document.getElementById('btLiga')")
    pintor = f[i:f.find("// E O DESLIGAR", i)] if i >= 0 else ""
    checar(u"o pintor pergunta por `ligado`", "if(!d.ligado){" in pintor,
           u"com dois estados, DESLIGADA se pinta como RODANDO")
    checar(u"  e oferece LIGAR quando esta desligada",
           "Ligar a fila" in pintor)
    checar(u"  e ainda oferece Pausar quando roda",
           "Pausar" in pintor)

    _i = f.find("function act(a)")
    _fim = f.find("@app.", _i)
    js = f[_i:_fim if _fim > _i else len(f)]
    js_codigo = re.sub(r"(?m)^\s*//.*$", "", js)
    js_codigo = re.sub(r"/\*.*?\*/", "", js_codigo, flags=re.S)
    checar(u"a tela chama `vigia/ligar` em CODIGO, e nao so no comentario",
           "vigia/ligar" in js_codigo,
           u"rota que so a bateria chama e rota que o operador nao alcanca")
    checar(u"  e a rota e escolhida pelo estado da fila",
           "window._ligado ? 'resume' : 'vigia/ligar'" in js_codigo)
    checar(u"  e e o botao de comecar que chama",
           "function filaComecar(){" in js and "filaComecar();" in js)
    checar(u"  e o plano usa esse caminho, e nao `act('resume')` cru",
           "planoFechar(); filaComecar();" in js
           and "planoFechar(); act('resume');" not in js)
    checar(u"  e a recusa e MOSTRADA (act ignora o corpo da resposta)",
           "alert(d.erro" in js)

    j = f.find("def resume():")
    corpo = f[j:f.find("\n@app.", j)]
    checar(u"`resume` mexe em `paused`", 'STATE["paused"] = False' in corpo)
    checar(u"  e NAO acende `ligado` (por isso o botao precisa da outra rota)",
           'STATE["ligado"] = True' not in corpo,
           u"se um dia acender, o `filaComecar` fica com duas verdades")


def teste_nao_se_arma_a_segunda_segmentacao():
    secao(u"nao se arma a segunda segmentacao na mesma maquina")
    f = fonte("radai_watcher.py")

    checar(u"ha uma funcao unica que responde quem esta segmentando",
           "def quem_esta_segmentando" in f)
    usos = f.count("quem_esta_segmentando()")
    checar(u"  e ela e usada em pelo menos tres pontos", usos >= 3, str(usos))

    i = f.find("def vigia_ligar():")
    corpo = f[i:f.find("\n@app.", i)]
    checar(u"ligar a fila com o «Rodar agora» rodando nao e recusado: o vigia "
           u"espera a vez (a fila unica)",
           "quem_esta_segmentando()" in corpo and '"ok": False, "ocupado"'
           not in corpo and "espera_o_lote" in corpo)

    fl = fonte("radai_batch.py")
    k = fl.find("def iniciar(")
    cl = fl[k:fl.find("\ndef ", k + 10)]
    checar(u"o «Rodar agora» com o vigia ocupado NAO e recusado: quer a vez e "
           u"espera a serie do vigia terminar",
           'oc.get("quem") != "lote"' not in cl
           and '_fila.querer_a_vez("lote")' in cl and "espera_o_vigia" in cl)
    checar(u"  e quer a vez ANTES de soltar a thread (o vigia nao pega outra)",
           cl.find('querer_a_vez("lote")') < cl.find("threading.Thread("))
    k2 = fl.find("def _rodar_tudo(")
    rt = fl[k2:fl.find("\ndef ", k2 + 10)]
    checar(u"  e so roda a primeira serie depois de ter a vez",
           rt.find("_esperar_a_vez_do_lote(") < rt.find("_series_a_rodar(")
           and "_soltar_a_vez_do_lote()" in rt)
    checar(u"e o laco do vigia espera a vez do lote",
           'avisou_lote' in f and '"tentar_a_vez", "vigia"' in f
           and '"soltar_a_vez", "vigia"' in f)


def teste_a_ordem_da_noite():
    secao(u"a ordem da noite: o caso mais recente primeiro")
    f = fonte("radai_watcher.py")
    i = f.find("def _ordem_da_fila")
    corpo = f[i:f.find("\ndef ", i + 10)]
    checar(u"a fila pergunta pelo turno", 'STATE.get("overnight")' in corpo)
    checar(u"  e a ordem do turno e decrescente por data",
           'reverse=True' in corpo)
    checar(u"  e o FIFO das novas continua existindo fora dele",
           'key=lambda x: x["date"])' in corpo,
           u"trocar a ordem do dia a dia nao foi pedido")
    checar(u"  e o ramo antigo nao foi apagado", "if done_dates:" in corpo)


def teste_a_entrega_ja_gravada():
    secao(u"serie que ja tem a entrega e nao tem marcador")
    import radai_sets as rc
    f = io.open(_componentes.fonte("app/radai_watcher.py"), encoding="utf-8").read()
    checar(u"ha a conferencia no disco", "def entrega_completa_no_disco" in f)
    checar(u"e a adocao", "def readotar_entrega" in f)
    i = f.find("def build_queue")
    corpo = f[i:f.find("\ndef ", i + 10)]
    checar(u"e a fila a consulta", "readotar_entrega(s)" in corpo)

    ns = {"os": os}
    for _nome in ("conjuntos_no_disco", "forma_da_prova",
                  "entrega_completa_no_disco"):
        j = f.find("def %s" % _nome)
        exec(compile(f[j:f.find("\ndef ", j + 10)], "<entrega>", "exec"), ns)
    fn = ns["entrega_completa_no_disco"]
    import ast as _ast
    _prova = None
    for _no in _ast.parse(f).body:
        if (isinstance(_no, _ast.Assign)
                and any(getattr(t, "id", "") == "CONJUNTOS_DE_PROVA"
                        for t in _no.targets)):
            _prova = _ast.literal_eval(_no.value)
    checar(u"a prova de readocao e (OAR + FULL) ou o OAR_Fast",
           tuple(tuple(x) for x in (_prova or ()))
           == (("oar", "full"), ("fast",)), str(_prova))
    ns["CONJUNTOS_DE_PROVA"] = tuple(_prova or (("oar", "full"),))

    d = temp()
    uid = "1.9.999.2.55.3.11111.45678901"
    curto = uid[-8:]
    checar(u"pasta vazia: nao adota", fn(d, uid) is False)

    io.open(os.path.join(d, rc.nome_do_arquivo("oar", "20260904", curto)),
            "w").write("x")
    checar(u"so o entregue: NAO adota (execucao que morreu no meio)",
           fn(d, uid) is False)
    io.open(os.path.join(d, rc.nome_do_arquivo("full", "20260904", curto)),
            "w").write("x")
    checar(u"OAR e FULL, sem o TS cru: adota", fn(d, uid) is True)
    d_fast = temp()
    io.open(os.path.join(d_fast, rc.nome_do_arquivo("fast", "20260904",
                                                    curto)), "w").write("x")
    checar(u"so o OAR_Fast (a serie do modo FAST): adota", fn(d_fast, uid)
           is True)
    ns_v82 = dict(ns, CONJUNTOS_DE_PROVA=(("oar", "full"),))
    for _nome in ("conjuntos_no_disco", "forma_da_prova",
                  "entrega_completa_no_disco"):
        j = f.find("def %s" % _nome)
        exec(compile(f[j:f.find("\ndef ", j + 10)], "<entrega_v82>", "exec"),
             ns_v82)
    checar(u"  ISCA: com a prova da v8.2 (so OAR e FULL), o OAR_Fast sozinho "
           u"NAO adota", ns_v82["entrega_completa_no_disco"](d_fast, uid)
           is False)

    outro = "1.9.999.2.55.3.11111.99999999"
    checar(u"a entrega de OUTRA serie na mesma pasta nao conta",
           fn(d, outro) is False, u"o casamento e pelos 8 digitos do UID")
    checar(u"pasta que nao existe: nao adota, e nao levanta",
           fn(os.path.join(d, "nao_existe"), uid) is False)
    checar(u"uid vazio: nao adota", fn(d, "") is False)

    k = f.find("def readotar_entrega")
    rd = f[k:f.find("\ndef ", k + 10)]
    checar(u"o marcador adotado diz que foi adotado",
           '"origem": "readotado"' in rd)
    checar(u"  e o log diz como refazer",
           "apague os RS_RadAI" in rd,
           u"serie pulada em silencio e o erro menos visivel deste produto")


_N_VIGIA = [0]


class _RelogioSemSono(object):

    def __getattr__(self, nome):
        return getattr(time, nome)

    def sleep(self, s):
        return None


def _vigia_da_noite(base, root):
    import importlib.util
    cfg = os.path.join(base, "noite.config")
    with io.open(cfg, "w", encoding="utf-8") as f:
        f.write(u"ROOT=%s\nDRY_RUN=1\nLOG_DIR=%s\n"
                % (root, os.path.join(base, "log")))
    _N_VIGIA[0] += 1
    velhos = dict((k, os.environ.get(k))
                  for k in ("RADAI_CONFIG", "RADAI_MACHINE", "LOCALAPPDATA"))
    os.environ["RADAI_URL_VERSOES"] = "0"
    os.environ["RADAI_CONFIG"] = cfg
    os.environ["RADAI_MACHINE"] = "PC_NOITE"
    os.environ["LOCALAPPDATA"] = os.path.join(base, "ad")
    try:
        spec = importlib.util.spec_from_file_location(
            "vigia_noite_%d" % _N_VIGIA[0], _componentes.fonte("app/radai_watcher.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    finally:
        for k, v in velhos.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    mod.time = _RelogioSemSono()
    _VIGIAS.append(mod)
    return mod


def teste_a_calibracao_abre_cada_turno():
    secao(u"a calibracao abre cada turno, e so ele")
    base = temp()
    root = os.path.join(base, "share")
    os.makedirs(root)
    velho_limpador = sys.modules.pop("radai_cleaner", None)
    try:
        mod = _vigia_da_noite(base, root)
        mod.STATE["dispositivo"] = {"modo": "gpu_resultado_na_cpu"}

        def _calibracoes():
            return [l for l in list(mod.LOGBUF)
                    if "calibracao de arranque do turno" in l]

        estado = {"fila": None, "proxima_varredura": 0.0}
        mod._uma_volta(estado)
        checar(u"com a fila desligada, nenhuma calibração", not _calibracoes())
        r = mod.vigia_ligar()
        checar(u"a rota liga a fila", r.get("ok") is True, str(r))
        mod._uma_volta(estado)
        c1 = _calibracoes()
        checar(u"o turno abriu: UMA linha de calibração", len(c1) == 1, c1)
        checar(u"  que diz a RAM livre", c1 and "RAM livre" in c1[0], c1)
        checar(u"  e põe ao lado a decisão do arranque",
               c1 and "no arranque: gpu_resultado_na_cpu" in c1[0], c1)
        checar(u"  e, em simulação, diz que não mediu o dispositivo",
               c1 and "simulacao" in c1[0], c1)
        for _ in range(3):
            mod._uma_volta(estado)
        checar(u"sem calibração nova NO MEIO do turno", len(_calibracoes()) == 1,
               len(_calibracoes()))
        mod.vigia_desligar()
        mod._uma_volta(estado)
        mod.vigia_ligar()
        mod._uma_volta(estado)
        checar(u"o turno seguinte tem a SUA calibração",
               len(_calibracoes()) == 2, len(_calibracoes()))
        import radai_queue_state as fila
        itens = fila.cards()
        checar(u"e nenhum card de calibração entrou na fila",
               not any("calibra" in json.dumps(x, ensure_ascii=False,
                                               default=str).lower()
                       for x in (itens or [])), len(itens or []))
    finally:
        if velho_limpador is not None:
            sys.modules["radai_cleaner"] = velho_limpador


def teste_o_arranque_nomeia_e_nao_fecha():
    secao(u"o arranque nomeia quem segura a placa, e nao fecha nada")
    import radai_arranque as RA
    tabela = u"\n".join([
        u"| Processes:                                                     |",
        u"|  GPU   GI   CI    PID   Type   Process name         GPU Memory |",
        u"|================================================================|",
        u"|    0   N/A  N/A  1001    C+G   ...\\msedge.exe             N/A |",
        u"|    0   N/A  N/A  1002    C+G   ...\\VitreaWorkstation.exe  N/A |",
        u"|    0   N/A  N/A  1003      G   ...\\Varian\\Eclipse.exe     N/A |",
        u"|    0   N/A  N/A  1004      G   ...\\ARIA\\aria_client.exe   N/A |",
        u"|    0   N/A  N/A  1005      G   ...\\Elekta\\MOSAIQ.exe      N/A |",
        u"|    0   N/A  N/A  1006    C+G   ...\\Teams\\ms-teams.exe     N/A |",
        u"+----------------------------------------------------------------+"])
    rel = {"dados": {"placas": {"placas": [
        {"indice": 0, "nome": "Quadro P2200", "total_mb": 5120.0,
         "livre_mb": 2048.0, "usada_mb": 3072.0, "driver": "528.86",
         "cap": "6.1"}]}}, "avisos": [], "pendencias": []}
    velho_proc = RA.processos_na_placa
    velho_limpador = sys.modules.get("radai_cleaner")
    RA.processos_na_placa = lambda timeout=20: {
        "processos": RA._processos_da_tabela(tabela), "falha": ""}
    try:
        sys.modules.pop("radai_cleaner", None)
        import radai_cleaner as _real
        linhas = RA._p_processos({}, rel)
        texto = u"\n".join(linhas)
        fechaveis = next((l for l in linhas if u"Fechar e decisao" in l), u"")
        for nome in ("VitreaWorkstation.exe", "Eclipse.exe", "aria_client.exe",
                     "MOSAIQ.exe"):
            marcado = re.search(re.escape(nome) + r" \(PID \d+, [^)]*protegido\)",
                                texto)
            checar(u"%s é NOMEADO, marcado protegido, e NÃO sugerido" % nome,
                   bool(marcado) and nome not in fechaveis,
                   fechaveis[:160] or texto[:160])
        checar(u"o navegador e o Teams são os sugeridos",
               "msedge.exe" in fechaveis and "ms-teams.exe" in fechaveis,
               fechaveis[:160])
        lp = com_limpador(LimpadorFalso({"SysMain": "rodando"}))
        linhas2 = RA._p_processos({}, rel)
        checar(u"sem a lista de protegidos, NADA é sugerido (o erro barato)",
               not any(u"Fechar e decisao" in l for l in linhas2), linhas2)
        checar(u"e o arranque não parou serviço nenhum",
               lp.parados == [] and lp.iniciados == [], lp.parados)
    finally:
        RA.processos_na_placa = velho_proc
        if velho_limpador is not None:
            sys.modules["radai_cleaner"] = velho_limpador
        else:
            sys.modules.pop("radai_cleaner", None)
    import ast
    arv = ast.parse(fonte("radai_arranque.py"))
    proibidas = ("kill", "terminate", "parar_servico", "TerminateProcess")
    chamadas = sorted(set(
        (getattr(n.func, "attr", None) or getattr(n.func, "id", ""))
        for n in ast.walk(arv) if isinstance(n, ast.Call)))
    checar(u"o módulo do arranque não chama nada que mate ou pare",
           not [c for c in chamadas if c in proibidas],
           [c for c in chamadas if c in proibidas])
    textos = [n.value for n in ast.walk(arv)
              if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    checar(u"  nem monta `taskkill`/`sc stop` num argumento",
           not any("taskkill" in t.lower() or "sc stop" in t.lower()
                   for t in textos if len(t) < 60))


class _TurnoDublado(object):

    def __init__(self):
        self.chamadas = []

    def iniciar(self, pausar_servicos=True, log=None, pasta=""):
        self.chamadas.append(("iniciar", bool(pausar_servicos)))
        servs = ([{"nome": "SysMain", "acao": "parado"}]
                 if pausar_servicos else [])
        return {"ok": True, "servicos": servs, "msg": u""}

    def encerrar(self, log=None, pasta="", motivo="encerrada"):
        self.chamadas.append(("encerrar",))
        return {"ok": True, "religados": 0, "falhas": []}

    def estado(self, pasta=""):
        return {"ativo": False, "n_pausados": 0, "pausados": []}

    def restaurar_se_pendente(self, log=None, pasta=""):
        return None


def _aplicador_de_recarga(mod, atraso=0.0):
    import threading
    parar = threading.Event()
    estado = {"fila": None, "proxima_varredura": 0.0}

    def _laco():
        while not parar.is_set():
            if mod.RECARREGAR.wait(0.05):
                if atraso:
                    time.sleep(atraso)
                try:
                    mod._uma_volta(estado)
                except Exception as e:
                    print(u"    (o laco de mentira levantou: %s)" % e)
    t = threading.Thread(target=_laco, daemon=True)
    t.start()
    return parar, t


def _card_do_turno(fila):
    return next((c for c in fila.cards() if c.get("tipo") == "overnight"), None)


def _com_turno_dublado():
    velho = sys.modules.get("radai_overnight")
    falso = _TurnoDublado()
    sys.modules["radai_overnight"] = falso
    return falso, velho


def _devolver_turno(velho):
    if velho is not None:
        sys.modules["radai_overnight"] = velho
    else:
        sys.modules.pop("radai_overnight", None)


def teste_o_card_do_turno_abre_quando_a_fila_chega_nele():
    secao(u"o card do turno abre o turno quando a fila chega nele")
    import radai_batch as L
    import radai_queue_state as fila
    base = temp()
    root = os.path.join(base, "share")
    os.makedirs(root)
    falso, velho = _com_turno_dublado()
    guarda = (dict(L._CFG), L._uma_serie)
    vistas = []
    try:
        mod = _vigia_da_noite(base, root)
        f = fonte("radai_watcher.py")
        i = f.find('"lote": {"tasks"')
        bloco = f[i:f.find('"marcadores": {', i)] if i >= 0 else ""
        checar(u"o vigia injeta no lote quem abre o turno",
               '"abrir_turno": abrir_turno_pela_fila' in bloco)

        pausar_no_meio = []

        def _serie_dublada(s, *a, **k):
            vistas.append((s.get("uid"), bool(mod.STATE["overnight"])))
            if pausar_no_meio:
                with L._TRAVA:
                    L._JOB["pausar"] = True
            return {}
        L._uma_serie = _serie_dublada
        L._CFG.clear()
        L._CFG["abrir_turno"] = mod.abrir_turno_pela_fila

        def _rodar(pausar=False):
            with L._TRAVA:
                L._JOB.update({"rodando": True, "cancelar": False,
                               "pausar": bool(pausar), "erro": "", "feitas": 0,
                               "total": 0, "resultados": []})
            L._rodar_tudo([], False, None, "cpu", None, 60, 60, None, {},
                          "PC_NOITE", 300.0, 0.0, da_fila=True)

        fila.limpar()
        fila.pedir([{"uid": "1.2.826.9.1", "pasta": root, "rotulo": u"A"},
                    {"uid": "1.2.826.9.2", "pasta": root, "rotulo": u"B"}])
        fila.overnight(True, pausar_servicos=False)
        _rodar(pausar=True)
        checar(u"com a fila PAUSADA, o turno nao abre (o card nao e a vez)",
               not falso.chamadas and not mod.STATE["overnight"],
               str(falso.chamadas))
        c = _card_do_turno(fila)
        checar(u"  e o card continua esperando", c and c.get("estado") ==
               "esperando", str(c))

        _rodar()
        checar(u"as duas series da frente rodaram antes do turno",
               [u for u, _t in vistas] == ["1.2.826.9.1", "1.2.826.9.2"],
               str(vistas))
        checar(u"  e o turno estava FECHADO enquanto elas rodavam",
               vistas and not any(t for _u, t in vistas), str(vistas))
        checar(u"a fila chegou no card: o turno ABRIU sozinho",
               mod.STATE["overnight"] is True and mod.STATE["ligado"] is True,
               str((mod.STATE["overnight"], mod.STATE["ligado"])))
        checar(u"  UMA vez, com a pausa de servicos guardada no card (nao)",
               falso.chamadas == [("iniciar", False)], str(falso.chamadas))
        c = _card_do_turno(fila)
        checar(u"  e o card virou «pronto» com o motivo",
               c and c.get("estado") == "pronto"
               and u"turno aberto" in (c.get("motivo") or u""), str(c))
        log = u"\n".join(list(mod.LOGBUF))
        checar(u"  e o log diz que foi a fila que abriu",
               u"OVERNIGHT RUN aberto" in log and u"card da fila" in log,
               log[-400:])

        mod.overnight_encerrar()
        checar(u"encerrar o turno tira da fila o card que o abriu",
               _card_do_turno(fila) is None, str(fila.cards()))

        del falso.chamadas[:]
        fila.limpar()
        fila.pedir([{"uid": "1.2.826.9.4", "pasta": root, "rotulo": u"D"}])
        fila.overnight(True, pausar_servicos=False)
        pausar_no_meio.append(1)
        try:
            _rodar()
        finally:
            del pausar_no_meio[:]
        c = _card_do_turno(fila)
        checar(u"PAUSAR durante a ultima serie: o turno NAO abre",
               not falso.chamadas and not mod.STATE["overnight"]
               and c and c.get("estado") == "esperando",
               str((falso.chamadas, c)))

        del falso.chamadas[:]
        mod.ROOT = ""
        fila.limpar()
        fila.pedir([{"uid": "1.2.826.9.3", "pasta": root, "rotulo": u"C"}])
        fila.overnight(True, pausar_servicos=True)
        _rodar()
        c = _card_do_turno(fila)
        checar(u"o turno que nao abre deixa o card «falhou»",
               c and c.get("estado") == "falhou", str(c))
        checar(u"  com o motivo (o ROOT vazio), e a estacao nao foi tocada",
               c and u"ROOT" in (c.get("motivo") or u"")
               and not falso.chamadas and not mod.STATE["overnight"],
               str((c, falso.chamadas)))
        tela = [x for x in fila.para_tela(fila.cards())
                if x.get("tipo") == "overnight"]
        checar(u"  e o card que vai para a tela nao leva a carga",
               tela and "carga" not in tela[0], str(tela))
    finally:
        L._CFG.clear()
        L._CFG.update(guarda[0])
        L._uma_serie = guarda[1]
        _devolver_turno(velho)
        fila.limpar()


def teste_iniciar_sem_salvar_vale_so_para_o_turno():
    secao(u"«iniciar sem salvar»: os valores valem so para o turno")
    import radai_queue_state as fila
    base = temp()
    share_a = os.path.join(base, "share_gravado")
    share_b = os.path.join(base, "share_da_noite")
    for p in (share_a, share_b):
        os.makedirs(p)
    falso, velho = _com_turno_dublado()
    parar = None
    try:
        mod = _vigia_da_noite(base, share_a)
        parar, _t = _aplicador_de_recarga(mod)
        texto_antes = io.open(str(mod.CFG_PATH), encoding="utf-8").read()
        mod_antes, dias_antes = set(mod.MODALITIES), mod.DAYS_BACK
        checar(u"(pre) o gravado e o share A", mod.ROOT == share_a, mod.ROOT)

        fila.limpar()
        fila.overnight(True, pausar_servicos=False,
                       temporarios={"TASKS": "lung_nodules"})
        r = mod.overnight_iniciar()
        checar(u"chave fora de ROOT/MODALITIES/DAYS_BACK: o turno RECUSA",
               r.get("ok") is False and u"TASKS" in (r.get("erro") or u"")
               and not mod.STATE["overnight"], str(r)[:300])
        checar(u"  e a lista de tasks nao mudou", "lung_nodules" not in
               mod.TASKS, str(mod.TASKS))
        fila.overnight(True, pausar_servicos=False,
                       temporarios={"DAYS_BACK": u"trinta"})
        r = mod.overnight_iniciar()
        checar(u"DAYS_BACK que nao e numero: RECUSA", r.get("ok") is False
               and u"DAYS_BACK" in (r.get("erro") or u""), str(r)[:300])

        nao_existe = os.path.join(base, "NAO_EXISTE_PACIENTE_X")
        fila.overnight(True, pausar_servicos=False,
                       temporarios={"ROOT": nao_existe})
        r = mod.overnight_iniciar()
        checar(u"a pasta que nao existe: o turno RECUSA, com o laudo",
               r.get("ok") is False and (r.get("laudo") or {}).get("existe")
               is False, str(r)[:300])
        checar(u"  e o ROOT em uso continua o gravado", mod.ROOT == share_a,
               mod.ROOT)
        checar(u"  e a estacao nao foi tocada (nem fila, nem servico)",
               not falso.chamadas and not mod.STATE["ligado"],
               str(falso.chamadas))
        c = _card_do_turno(fila)
        checar(u"  e o card diz «falhou», com o motivo do laudo",
               c and c.get("estado") == "falhou"
               and u"laudo" in (c.get("motivo") or u""), str(c))

        import radai_config as _rc
        _velho_vp = _rc.validar_pasta
        _rc.validar_pasta = lambda cam: {
            "caminho": cam, "vazio": False, "existe": True, "leitura": True,
            "escrita": False, "aviso": u"",
            "erro": (u"da para LER mas NAO para escrever ([Errno 13] "
                     u"Permission denied: '%s\\_radai_teste_escrita_1.tmp')"
                     % cam)}
        try:
            fila.overnight(True, pausar_servicos=False,
                           temporarios={"ROOT": nao_existe})
            r = mod.overnight_iniciar()
        finally:
            _rc.validar_pasta = _velho_vp
        checar(u"a pasta que le e NAO grava: o turno RECUSA",
               r.get("ok") is False and (r.get("laudo") or {}).get("escrita")
               is False and not mod.STATE["overnight"], str(r)[:300])
        c = _card_do_turno(fila)
        checar(u"  e o motivo do card vai SEM o caminho da pasta",
               c and c.get("estado") == "falhou" and c.get("motivo")
               and u"NAO_EXISTE_PACIENTE_X" not in c.get("motivo")
               and u"grava" in c.get("motivo").lower(), str(c))

        fila.overnight(False)
        fila.overnight(True, pausar_servicos=False,
                       temporarios={"ROOT": share_b, "MODALITIES": u"CT,MR",
                                    "DAYS_BACK": u"30"})
        r = mod.overnight_iniciar()
        checar(u"os valores do modal abrem o turno", r.get("ok") is True,
               str(r)[:300])
        checar(u"  o ROOT em uso e o DO TURNO", mod.ROOT == share_b, mod.ROOT)
        checar(u"  e as modalidades e os dias tambem",
               mod.MODALITIES == set(["CT", "MR"]) and mod.DAYS_BACK == 30,
               str((mod.MODALITIES, mod.DAYS_BACK)))
        checar(u"  e o radai_watcher.config NAO foi gravado",
               io.open(str(mod.CFG_PATH), encoding="utf-8").read()
               == texto_antes)
        log = u"\n".join(list(mod.LOGBUF))
        checar(u"  e o log registra o laudo e diz que NAO foi gravado",
               u"TEMPORARIOS" in log and u"existe, le e grava" in log
               and u"nao gravados" in log, log[-600:])
        st = mod.status()
        checar(u"  e o /api/status diz quais chaves sao so do turno",
               st.get("turno_temporario") == ["DAYS_BACK", "MODALITIES",
                                              "ROOT"]
               and st.get("recarga_pendente") is False, str(st.get(
                   "turno_temporario")))
        c = _card_do_turno(fila)
        checar(u"  e o card virou «pronto»", c and c.get("estado") == "pronto",
               str(c))

        fila.overnight(True, pausar_servicos=False,
                       temporarios={"ROOT": share_a})
        n_chamadas = len(falso.chamadas)
        r = mod.abrir_turno_pela_fila()
        c = _card_do_turno(fila)
        checar(u"com o turno ja aberto, um card novo nao abre outro nem troca "
               u"a pasta", r.get("ja_aberto") is True and mod.ROOT == share_b
               and len(falso.chamadas) == n_chamadas, str(r)[:200])
        checar(u"  e o card diz que os valores dele NAO foram aplicados",
               c and c.get("estado") == "pronto"
               and u"nao foram aplicados" in (c.get("motivo") or u""), str(c))

        mod.overnight_encerrar()
        esp = mod.esperar_recarga(10)
        checar(u"encerrar o turno pede a recarga, e ela entra",
               esp.get("aplicada") is True, str(esp))
        checar(u"  e os valores GRAVADOS voltam",
               mod.ROOT == share_a and set(mod.MODALITIES) == mod_antes
               and mod.DAYS_BACK == dias_antes,
               str((mod.ROOT, mod.MODALITIES, mod.DAYS_BACK)))
        checar(u"  e nada mais e temporario",
               mod.status().get("turno_temporario") == [],
               str(mod.status().get("turno_temporario")))
        log = u"\n".join(list(mod.LOGBUF))
        checar(u"  e o log diz que os gravados voltaram",
               u"os valores gravados voltam" in log, log[-400:])
    finally:
        if parar is not None:
            parar.set()
        _devolver_turno(velho)
        fila.limpar()


def teste_a_recarga_pendente_e_esperada_ou_dita():
    secao(u"a recarga pendente: a rota espera, ou diz")
    import radai_config
    import radai_queue_state as fila
    base = temp()
    share_a = os.path.join(base, "share_a")
    share_b = os.path.join(base, "share_b")
    for p in (share_a, share_b):
        os.makedirs(p)
    falso, velho = _com_turno_dublado()
    parar = None
    try:
        fila.limpar()
        mod = _vigia_da_noite(base, share_a)
        mod.TETO_DA_RECARGA_S = 0.3
        radai_config.escrever(str(mod.CFG_PATH), {"ROOT": share_b})
        mod.pedir_recarga()
        checar(u"pedida e nao aplicada: a recarga esta PENDENTE",
               mod.recarga_pendente() is True)
        r = mod.overnight_iniciar()
        checar(u"passado o teto, o turno abre DIZENDO que ela esta pendente",
               r.get("ok") is True and r.get("recarga_pendente") is True
               and u"série" in (r.get("aviso") or u""), str(r)[:300])
        checar(u"  e o /api/status tambem diz",
               mod.status().get("recarga_pendente") is True)
        log = u"\n".join(list(mod.LOGBUF))
        checar(u"  e o log diz que a pasta nova ainda nao vale",
               u"recarga pendente" in log, log[-400:])
        mod.overnight_encerrar()

        parar, _t = _aplicador_de_recarga(mod, atraso=0.5)
        mod.esperar_recarga(10)
        mod.TETO_DA_RECARGA_S = 10.0
        radai_config.escrever(str(mod.CFG_PATH), {"ROOT": share_a})
        mod.pedir_recarga()
        r = mod.overnight_iniciar()
        checar(u"com o laco vivo, a rota ESPERA a recarga e abre com a pasta "
               u"nova", r.get("ok") is True and not r.get("recarga_pendente")
               and mod.ROOT == share_a, str((r, mod.ROOT))[:300])
        checar(u"  e nada fica pendente", mod.recarga_pendente() is False)
    finally:
        if parar is not None:
            parar.set()
        _devolver_turno(velho)
        fila.limpar()


def _funcao_do_js(js, nome):
    i = js.find(u"function %s(" % nome)
    if i < 0:
        return u""
    k = js.find(u"{", i)
    prof = 0
    for j in range(k, len(js)):
        if js[j] == u"{":
            prof += 1
        elif js[j] == u"}":
            prof -= 1
            if prof == 0:
                return js[i:j + 1]
    return u""


def _rodar_no_node(fonte):
    import shutil
    import subprocess
    node = shutil.which("node")
    if not node:
        return None, u"sem node"
    d = tempfile.mkdtemp(prefix="radai_noite_js_")
    alvo = os.path.join(d, "r.js")
    try:
        io.open(alvo, "w", encoding="utf-8").write(fonte)
        r = subprocess.run([node, alvo], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=120)
        for ln in reversed((r.stdout or u"").splitlines()):
            if ln.startswith(u"JSON:"):
                return json.loads(ln[5:]), None
        return None, ((r.stderr or u"") + (r.stdout or u""))[-400:]
    finally:
        shutil.rmtree(d, ignore_errors=True)


_FOLHA_DUBLES = u"""
var CHAMADAS = [], ERROS = [], LAUDOS = [], RESP = {};
var OV = {laudo: null, t: null, rootAdiado: false, pendente: false};
var ROOT_DA_TELA = 'P';
function _ovValores(){ return {ROOT: ROOT_DA_TELA, MODALITIES: 'CT', DAYS_BACK: '0'} }
function _ovLaudo(t, c){ LAUDOS.push([t, c]) }
function _ovEstado(){}
function _ovCard(){}
function _ovErro(m){ ERROS.push(String(m)) }
function filaEstado(){}
function _ovQ(){ return null }
function _ovPorNaFila(){ CHAMADAS.push('fila'); return Promise.resolve() }
function fetch(u, o){
 CHAMADAS.push(u);
 var c = RESP[u] || {};
 return Promise.resolve({json: function(){ return Promise.resolve(c) }});
}
function espera(ms){ return new Promise(function(r){ setTimeout(r, ms) }) }
"""

_FOLHA_RODA = u"""
(async function(){
 var R = {};
 RESP['/api/lote/conferir_pasta'] = {existe: true, leitura: true};
 RESP['/api/config/testar'] = {existe: true, leitura: true, escrita: true};
 _ovTestar();
 await espera(700);
 R.abrir = CHAMADAS.slice();
 R.bom = _ovLaudoBom();
 CHAMADAS = []; ERROS = [];
 RESP['/api/config/testar'] = {existe: true, leitura: true, escrita: false,
                                erro: 'NAO GRAVA'};
 ovIniciar(true, {ROOT: 'P', MODALITIES: 'CT', DAYS_BACK: '0'}, false);
 await espera(60);
 R.ruim = CHAMADAS.slice(); R.erroRuim = ERROS.slice();
 CHAMADAS = []; ERROS = [];
 RESP['/api/config/testar'] = {existe: true, leitura: true, escrita: true};
 RESP['/api/config'] = {ok: true, salvos: []};
 ovIniciar(true, {ROOT: 'P', MODALITIES: 'CT', DAYS_BACK: '0'}, false);
 await espera(60);
 R.boa = CHAMADAS.slice(); R.erroBoa = ERROS.slice();
 OV.rootAdiado = true;
 R.texto = _ovTextoAberto();
 console.log('JSON:' + JSON.stringify(R));
})();
"""


def _falhas_da_folha(d):
    f = []
    if not d:
        return [u"nao executou"]
    if d.get(u"abrir") != [u"/api/lote/conferir_pasta"]:
        f.append(u"abrir a folha chamou %s" % d.get(u"abrir"))
    if not d.get(u"bom"):
        f.append(u"a pasta que existe e le nao habilita o Salvar")
    if d.get(u"ruim") != [u"/api/config/testar"] or not any(
            u"NAO GRAVA" in e for e in d.get(u"erroRuim") or ()):
        f.append(u"a pasta que nao grava: %s / %s"
                 % (d.get(u"ruim"), d.get(u"erroRuim")))
    if d.get(u"boa") != [u"/api/config/testar", u"/api/config", u"fila"] \
            or d.get(u"erroBoa"):
        f.append(u"a pasta que grava: %s / %s" % (d.get(u"boa"),
                                                  d.get(u"erroBoa")))
    if u"próximo turno" not in (d.get(u"texto") or u""):
        f.append(u"o cartao do turno nao diz que a pasta nova fica para o "
                 u"proximo: %r" % d.get(u"texto"))
    return f


def teste_a_folha_do_turno_so_le_a_pasta_ao_abrir():
    secao(u"a folha do turno so le a pasta ao abrir; a escrita se confere "
          u"ao salvar")
    import builtins
    import pathlib
    import radai_batch as B
    import radai_config
    base = temp()
    alvo = os.path.join(base, "share_dos_exames")
    os.makedirs(alvo)
    io.open(os.path.join(alvo, "serie.txt"), "w", encoding="utf-8").write(u"x")
    gravou = []
    velho_open, velho_wt = builtins.open, pathlib.Path.write_text

    def _open(f, modo="r", *a, **k):
        if any(c in str(modo) for c in "wax+") and alvo in str(f):
            gravou.append(str(f))
        return velho_open(f, modo, *a, **k)

    def _wt(self, *a, **k):
        if alvo in str(self):
            gravou.append(str(self))
        return velho_wt(self, *a, **k)
    antes = sorted(os.listdir(alvo))
    try:
        builtins.open, pathlib.Path.write_text = _open, _wt
        r = B.conferir_pasta_sem_gravar(alvo)
        gravou_ao_conferir = list(gravou)
        del gravou[:]
        radai_config.validar_pasta(alvo)
        gravou_no_teste = list(gravou)
    finally:
        builtins.open, pathlib.Path.write_text = velho_open, velho_wt
    checar(u"a conferencia da folha diz que a pasta existe e le",
           r.get(u"existe") is True and r.get(u"leitura") is True, str(r))
    checar(u"  e nao grava nada na pasta (nem arquivo de teste)",
           not gravou_ao_conferir and sorted(os.listdir(alvo)) == antes,
           str(gravou_ao_conferir))
    checar(u"  (isca) o teste de escrita grava na pasta -- a checagem "
           u"discrimina", bool(gravou_no_teste), str(gravou_no_teste))
    checar(u"  e a pasta que nao existe volta sem levantar",
           B.conferir_pasta_sem_gravar(os.path.join(base, u"nao_existe"))
           .get(u"existe") is False)
    checar(u"  e a pasta vazia diz vazia", B.conferir_pasta_sem_gravar(u"")
           .get(u"vazio") is True)

    js = B.PAGINA
    funcs = [_funcao_do_js(js, n) for n in (
        u"_ovTestar", u"_ovLaudoBom", u"_ovConferirEscrita", u"ovIniciar",
        u"_ovTextoAberto")]
    checar(u"as funcoes da folha estao na pagina", all(funcs),
           str([bool(x) for x in funcs]))
    if not all(funcs):
        return
    d, erro = _rodar_no_node(_FOLHA_DUBLES + u"\n".join(funcs) + _FOLHA_RODA)
    if d is None and erro == u"sem node":
        checar(u"node disponivel", False, u"PULADO")
        return
    f = _falhas_da_folha(d)
    checar(u"abrir a folha so le; Salvar confere a escrita ANTES de gravar a "
           u"configuracao, e para se a pasta nao grava", not f,
           u"; ".join(f) or (erro or u""))
    iscas = (
        (u"a folha que testa a escrita ao abrir",
         [x.replace(u"'/api/lote/conferir_pasta'", u"'/api/config/testar'")
          for x in funcs]),
        (u"o Salvar que grava sem conferir a escrita",
         [x if not x.startswith(u"function _ovConferirEscrita(") else
          u"function _ovConferirEscrita(){ return Promise.resolve(true) }"
          for x in funcs]),
    )
    for nome, fs in iscas:
        di, _e = _rodar_no_node(_FOLHA_DUBLES + u"\n".join(fs) + _FOLHA_RODA)
        checar(u"  (isca) %s reprova" % nome, bool(_falhas_da_folha(di)))
    est = _funcao_do_js(js, u"filaEstado")
    checar(u"  e o cartao le do /api/status se a pasta nova ficou para o "
           u"proximo turno", u"st.root_no_proximo_turno" in est, est[:120])


def teste_o_root_trocado_no_turno_vale_no_seguinte():
    secao(u"o ROOT trocado com o turno aberto vale a partir do turno seguinte")
    import radai_config
    import radai_queue_state as fila
    base = temp()
    share_a = os.path.join(base, "share_a")
    share_b = os.path.join(base, "share_b")
    for p in (share_a, share_b):
        os.makedirs(p)
    falso, velho = _com_turno_dublado()
    parar = None
    try:
        fila.limpar()
        mod = _vigia_da_noite(base, share_a)
        parar, _t = _aplicador_de_recarga(mod)
        fila.overnight(True, pausar_servicos=False)
        r = mod.overnight_iniciar()
        checar(u"(pre) o turno abre na pasta gravada", r.get(u"ok") is True
               and mod.ROOT == share_a, str((r, mod.ROOT))[:200])
        radai_config.escrever(str(mod.CFG_PATH), {"ROOT": share_b})
        rr = mod.pedir_recarga()
        checar(u"gravar outra pasta com o turno aberto: a recarga diz que ela "
               u"vale a partir do proximo turno",
               rr.get(u"root_no_proximo_turno") is True
               and rr.get(u"quando") == mod.PASTA_NO_PROXIMO_TURNO
               and u"próximo turno" in rr.get(u"quando"), str(rr))
        esp = mod.esperar_recarga(10)
        checar(u"  e, com a recarga aplicada, o turno segue na pasta em que "
               u"abriu", esp.get(u"aplicada") is True and mod.ROOT == share_a,
               str((esp, mod.ROOT)))
        checar(u"  e o /api/status diz que a pasta nova espera o proximo turno",
               mod.status().get(u"root_no_proximo_turno") is True)
        log = u"\n".join(list(mod.LOGBUF))
        checar(u"  e o log diz por que", u"vale a partir do proximo turno"
               in log, log[-400:])
        mod.overnight_encerrar()
        esp = mod.esperar_recarga(10)
        checar(u"encerrado o turno, a pasta nova passa a valer",
               esp.get(u"aplicada") is True and mod.ROOT == share_b,
               str((esp, mod.ROOT)))
        checar(u"  e nada mais fica para o proximo turno",
               mod.status().get(u"root_no_proximo_turno") is False
               and not mod.pedir_recarga().get(u"root_no_proximo_turno"))
        mod.esperar_recarga(10)

        fila.overnight(True, pausar_servicos=False)
        r = mod.overnight_iniciar()
        mod.ROOT_DO_TURNO.clear()
        radai_config.escrever(str(mod.CFG_PATH), {"ROOT": share_a})
        mod.pedir_recarga()
        mod.esperar_recarga(10)
        checar(u"  (isca) sem a pasta do turno guardada, ela troca no meio do "
               u"turno -- a checagem reprovaria",
               r.get(u"ok") is True and mod.ROOT == share_a,
               str((r, mod.ROOT))[:200])
        mod.overnight_encerrar()
    finally:
        if parar is not None:
            parar.set()
        _devolver_turno(velho)
        fila.limpar()


def main():
    print(u"=" * 70)
    print(u"  O OVERNIGHT RUN — o turno da noite e o que ele mexe na estacao")
    print(u"=" * 70)
    for t in (teste_o_modulo_e_so_stdlib,
              teste_o_turno_abre_e_fecha,
              teste_o_registro_nasce_antes_da_primeira_parada,
              teste_a_queda_de_energia,
              teste_abrir_duas_vezes_nao_perde_o_estado_original,
              teste_sem_registro_nao_para_nada,
              teste_o_negado_nao_vira_pausado,
              teste_o_que_nao_religou_nao_vira_alarme_eterno,
              teste_a_lista_de_religar_e_fechada,
              teste_o_parcial_leva_o_nome_de_quem_escreve,
              teste_o_caminho_do_paciente_nao_vai_para_o_share,
              teste_o_status_dir_nao_pode_sincronizar,
              teste_o_arquivo_de_status_nao_leva_PatientID,
              teste_a_frota_le_o_status_das_outras,
              teste_a_retomada_e_de_uma_maquina_so,
              teste_o_batimento_reclama_quando_falha,
              teste_a_tela_da_noite,
              teste_a_tela_consegue_ligar_a_fila,
              teste_nao_se_arma_a_segunda_segmentacao,
              teste_a_ordem_da_noite,
              teste_a_entrega_ja_gravada,
              teste_a_calibracao_abre_cada_turno,
              teste_o_arranque_nomeia_e_nao_fecha,
              teste_o_card_do_turno_abre_quando_a_fila_chega_nele,
              teste_iniciar_sem_salvar_vale_so_para_o_turno,
              teste_a_recarga_pendente_e_esperada_ou_dita,
              teste_a_folha_do_turno_so_le_a_pasta_ao_abrir,
              teste_o_root_trocado_no_turno_vale_no_seguinte):
        t()
    print(u"\n" + u"=" * 70)
    if _falhas:
        print(u"FALHOU: %d de %d checagens" % (len(_falhas), _ok + len(_falhas)))
        for f in _falhas:
            print(u"    - %s" % f)
        print(u"=" * 70)
        return 1
    print(u"OK: %d checagens, todas passaram" % _ok)
    print(u"=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
