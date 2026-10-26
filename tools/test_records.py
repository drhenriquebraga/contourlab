# -*- coding: utf-8 -*-
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import zipfile

_INICIO = time.time()
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _cleanup
import _componentes
import radai_records as _RG_RAIZ
if not os.path.isfile(os.path.join(_RG_RAIZ._raiz_do_programa(), "entrega.txt")):
    _RG_RAIZ._raiz_do_programa = _componentes.raiz_da_suite
_cleanup.adotar_prefixo('radai_reg_')

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(RAIZ, "app")
sys.path.insert(0, APP)

_ACERVO = tempfile.mkdtemp(prefix="radai_reg_acervo_")
os.environ["RADAI_CALIB_DIR"] = _ACERVO
os.environ["RADAI_REGISTRO_DIR"] = tempfile.mkdtemp(prefix="radai_reg_registro_")

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
    return tempfile.mkdtemp(prefix="radai_reg_")


UID = "1.9.999.999999.9.99.9.9999999999.999.9999999999.999"
PID = "FANTOMA-PID"
NOME = u"FANTOMA^ISCA^DE^TESTE"
NASC = "18991332"
IDENT = [PID, NOME, NASC, UID]

LOG = u"\n".join([
    u"[20:17:12] === serie ...%s | %%s | 89 cortes | %%s ===" % UID[-8:] % (
        PID, "\\\\servidor\\imagens\\Patients\\ISCA_FANTOMA\\CT"),
    u"[20:17:14] paciente %s, nascido em %s" % (NOME, NASC),
    u"[20:46:09] 94 estrutura(s) do TotalSegmentator",
    u"[21:16:29] margem de OAR em carotids: +1.0 mm (8.4 -> 13.5 cm3)",
    u"[21:20:00] copia local em D:\\RADIOTERAPIA_AI\\stage\\%s" % PID,
    u"[21:27:38] OK %s -> RS_RadAI_20160930_%s.dcm (35 estruturas)"
    % (PID, UID[-8:]),
])


def um_caso(base, uid=UID, ident=None, log=LOG, papel=u"estacao de trabalho"):
    import radai_records as RG
    c = RG.Caso(uid=uid, identificadores=(ident if ident is not None else IDENT),
                base=base, papel=papel)
    c.serie(modalidade="CT", cortes=89, espessura_mm=5.0, fov_mm=500)
    c.etapa(u"TotalSegmentator total", 1725.0)
    c.achado(u"margem_de_oar", u"carotids +1.0 mm", antes_cm3=8.4, depois_cm3=13.5)
    c.achado(u"sobreposicao", u"liver e portal_vein em comum", cm3=0.62)
    if log:
        c.log(log)
    c.resultado(True, conjuntos=["oar", "ts", "v3d", "full"], estruturas=94)
    return c


def teste_o_modulo_e_so_stdlib():
    secao(u"o registro e so biblioteca padrao")
    import ast
    f = io.open(_componentes.fonte("app/radai_records.py"), encoding="utf-8").read()
    topo = []
    for no in ast.parse(f).body:
        if isinstance(no, ast.Import):
            topo += [a.name.split(".")[0] for a in no.names]
        elif isinstance(no, ast.ImportFrom) and no.module:
            topo.append(no.module.split(".")[0])
    PADRAO = {"hashlib", "hmac", "io", "json", "os", "platform", "re",
              "socket", "subprocess", "sys", "threading", "time", "zipfile",
              "datetime"}
    fora = [m for m in topo if m not in PADRAO]
    checar(u"nenhum import de topo fora da stdlib", not fora, str(fora))
    checar(u"e o limpador entra DENTRO da funcao",
           "radai_cleaner" not in topo and "import radai_cleaner" in f)


def teste_o_pseudonimo_e_estavel_e_nao_reversivel():
    secao(u"o pseudonimo: estavel dentro, opaco fora")
    import radai_records as RG
    a, b = temp(), temp()
    p1 = RG.pseudonimo(UID, a)
    p2 = RG.pseudonimo(UID, a)
    p3 = RG.pseudonimo(UID, b)
    checar(u"o mesmo UID da o mesmo pseudonimo na mesma instalacao", p1 == p2)
    checar(u"  e OUTRO numa instalacao diferente", p1 != p3,
           u"sem isso, duas clinicas colidiriam no meu lado")
    checar(u"  e nao e o UID nem um hash simples dele",
           UID not in p1 and len(p1) == 8)
    import hashlib
    checar(u"  e nao bate com sha256(uid), que seria testavel por candidato",
           p1 != hashlib.sha256(UID.encode()).hexdigest()[:8])
    checar(u"UID vazio nao explode", RG.pseudonimo("", a) == "semuid00")


def _segredo_em_pasta_que_sincroniza(fonte_do_segredo=None):
    import radai_records as RG
    nuvem = temp()
    base = os.path.join(nuvem, u"registro")
    guardado = os.environ.get("RADAI_RAIZES_NUVEM")
    original = RG._segredo
    try:
        os.environ["RADAI_RAIZES_NUVEM"] = nuvem
        if fonte_do_segredo is not None:
            ns = dict(RG.__dict__)
            exec(fonte_do_segredo, ns)
            RG._segredo = ns["_segredo"]
        p1 = RG.pseudonimo(UID, base)
        p2 = RG.pseudonimo(UID, base)
        gravou = os.path.isfile(os.path.join(base, RG.NOME_SEGREDO))
        aviso = RG.aviso_do_segredo(base) if hasattr(RG, "aviso_do_segredo") else u""
    finally:
        RG._segredo = original
        if guardado is None:
            os.environ.pop("RADAI_RAIZES_NUVEM", None)
        else:
            os.environ["RADAI_RAIZES_NUVEM"] = guardado
    return {"gravou": gravou, "estavel": p1 == p2, "aviso": aviso, "p": p1}


def teste_a_chave_nao_vai_para_pasta_que_sincroniza():
    secao(u"a chave do pseudonimo nunca e gravada em pasta que sincroniza")
    import radai_records as RG
    m = _segredo_em_pasta_que_sincroniza()
    checar(u"numa pasta que sincroniza, a chave nao vai para o disco",
           m["gravou"] is False, repr(m))
    checar(u"  e o pseudonimo continua estavel dentro do processo",
           m["estavel"] and len(m["p"]) == 8, repr(m))
    checar(u"  e o registro diz por que, com a variavel que tira de la",
           u"RADAI_REGISTRO_DIR" in (m["aviso"] or u""), repr(m))
    fora = temp()
    p = RG.pseudonimo(UID, fora)
    checar(u"fora da nuvem a chave e gravada como antes (estavel entre processos)",
           os.path.isfile(os.path.join(fora, RG.NOME_SEGREDO)) and len(p) == 8)
    checar(u"  e la o registro nao avisa nada", RG.aviso_do_segredo(fora) == u"")
    velha = (u"def _segredo(base=''):\n"
             u"    p = os.path.join(_garantir(raiz(base)), NOME_SEGREDO)\n"
             u"    s = hashlib.sha256(os.urandom(64)).hexdigest().encode('ascii')\n"
             u"    with io.open(p, 'wb') as f:\n"
             u"        f.write(s)\n"
             u"    return s\n")
    mi = _segredo_em_pasta_que_sincroniza(velha)
    checar(u"  (isca) a versao que grava sempre poe a chave na pasta da nuvem",
           mi["gravou"] is True, repr(mi))


RAIZES_SO_PELA_VARIAVEL = (
    u"def raizes_espelhadas():\n"
    u"    base = os.environ.get('LOCALAPPDATA') or ''\n"
    u"    db = os.path.join(base, *_DRIVE_DB) if base else ''\n"
    u"    if not (db and os.path.isfile(db)):\n"
    u"        return tuple(_raizes_declaradas())\n"
    u"    return tuple(_raizes_declaradas()) + tuple(_raizes_do_banco(db))\n")


def _banco_do_drive_falso(A, perfil, raiz_espelhada):
    import sqlite3
    db = os.path.join(perfil, *A._DRIVE_DB)
    os.makedirs(os.path.dirname(db))
    con = sqlite3.connect(db)
    try:
        con.execute("create table roots (last_seen_absolute_path text)")
        con.execute("insert into roots values (?)", (raiz_espelhada,))
        con.commit()
    finally:
        con.close()


def _chave_com_a_localappdata_trocada(raizes_fonte=None):
    import radai_archive as A
    import radai_records as RG
    caixa = temp()
    perfil = os.path.join(caixa, u"perfil")
    espelhada = os.path.join(caixa, u"espelhada")
    _banco_do_drive_falso(A, perfil, espelhada)
    vazia = os.path.join(caixa, u"lad_vazia")
    os.makedirs(vazia)
    base = os.path.join(espelhada, u"registro")
    guardado = dict((k, os.environ.get(k))
                    for k in ("LOCALAPPDATA", "RADAI_RAIZES_NUVEM"))
    local_real, raizes_real = A._local_do_perfil, A.raizes_espelhadas
    try:
        os.environ["LOCALAPPDATA"] = vazia
        os.environ.pop("RADAI_RAIZES_NUVEM", None)
        A._local_do_perfil = lambda: perfil
        if raizes_fonte is not None:
            ns = dict(vars(A))
            exec(raizes_fonte, ns)
            A.raizes_espelhadas = ns["raizes_espelhadas"]
        A._CACHE_RAIZES["quando"] = None
        p = RG.pseudonimo(UID, base)
        gravou = os.path.isfile(os.path.join(base, RG.NOME_SEGREDO))
    finally:
        A._local_do_perfil, A.raizes_espelhadas = local_real, raizes_real
        A._CACHE_RAIZES["quando"] = None
        for k, v in guardado.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    return {"gravou": gravou, "p": p}


def teste_a_chave_nao_vai_para_a_nuvem_com_a_localappdata_trocada():
    secao(u"a chave nao vai para a nuvem com a LOCALAPPDATA trocada")
    m = _chave_com_a_localappdata_trocada()
    checar(u"com a LOCALAPPDATA trocada (como a bateria que sobe o vigia), "
           u"a pasta que o Drive do perfil espelha continua recusada",
           m["gravou"] is False and len(m["p"]) == 8, repr(m))
    mi = _chave_com_a_localappdata_trocada(RAIZES_SO_PELA_VARIAVEL)
    checar(u"  (isca) lendo o Drive so pela variavel, a chave vai para a "
           u"pasta da nuvem", mi["gravou"] is True, repr(mi))


def teste_sem_como_conferir_a_chave_fica_na_memoria():
    secao(u"sem como conferir a pasta, a chave fica na memoria")
    import radai_archive as A
    import radai_records as RG

    def _explode(*_a, **_k):
        raise OSError(u"isca")
    velha = (u"def _pasta_que_sincroniza(pasta):\n"
             u"    try:\n"
             u"        import radai_archive\n"
             u"        sim, motivo = radai_archive.em_pasta_sincronizada(pasta)\n"
             u"        return bool(sim), u'%s' % (motivo or u'')\n"
             u"    except Exception:\n"
             u"        return False, u''\n")
    ns = dict(vars(RG))
    exec(velha, ns)
    real, guarda = A.em_pasta_sincronizada, RG._pasta_que_sincroniza
    base, base_isca = temp(), temp()
    A.em_pasta_sincronizada = _explode
    try:
        p1, p2 = RG.pseudonimo(UID, base), RG.pseudonimo(UID, base)
        RG._pasta_que_sincroniza = ns["_pasta_que_sincroniza"]
        RG.pseudonimo(UID, base_isca)
    finally:
        A.em_pasta_sincronizada, RG._pasta_que_sincroniza = real, guarda
    checar(u"a conferencia que estoura nao deixa gravar a chave",
           not os.path.isfile(os.path.join(base, RG.NOME_SEGREDO)))
    checar(u"  e o pseudonimo continua estavel no processo", p1 == p2)
    checar(u"  (isca) a guarda que falha aberta grava a chave",
           os.path.isfile(os.path.join(base_isca, RG.NOME_SEGREDO)))


def _o_vigia_filho_ve_a_pasta_padrao(com_a_velha):
    import radai_archive as A
    import radai_records as RG
    vazia = temp()
    codigo = [u"import os, sys",
              u"sys.path[:0] = %r" % [os.path.dirname(os.path.abspath(RG.__file__)),
                                      os.path.dirname(os.path.abspath(A.__file__))],
              u"import radai_archive as A",
              u"import radai_records as RG"]
    if com_a_velha:
        codigo += [u"ns = dict(vars(A))", u"exec(%r, ns)" % RAIZES_SO_PELA_VARIAVEL,
                   u"A.raizes_espelhadas = ns['raizes_espelhadas']"]
    codigo += [u"print('PASTA=' + RG.raiz())",
               u"print('NUVEM=%s' % RG._pasta_que_sincroniza(RG.raiz())[0])"]
    amb = dict(os.environ)
    for k in ("RADAI_REGISTRO_DIR", "RADAI_RAIZES_NUVEM"):
        amb.pop(k, None)
    amb["LOCALAPPDATA"] = vazia
    amb["PYTHONIOENCODING"] = "utf-8"
    r = subprocess.run([sys.executable, "-c", u"\n".join(codigo)], env=amb,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                       timeout=120)
    saida = r.stdout.decode("utf-8", "replace")
    linhas = dict(l.split("=", 1) for l in saida.splitlines() if "=" in l)
    return linhas.get("PASTA", u""), linhas.get("NUVEM", u""), saida


def teste_a_rodada_nao_grava_chave_na_pasta_padrao():
    secao(u"a pasta padrao do registro, nesta maquina")
    import radai_archive as A
    import radai_records as RG
    padrao = os.path.join(os.path.dirname(os.path.abspath(RG.__file__)),
                          RG.NOME_PASTA)
    checar(u"a bateria isola o registro (RADAI_REGISTRO_DIR fora da pasta "
           u"padrao)", os.path.normcase(os.path.abspath(RG.raiz()))
           != os.path.normcase(os.path.abspath(padrao)), RG.raiz())
    chave = os.path.join(padrao, RG.NOME_SEGREDO)
    checar(u"  e nenhuma chave nova apareceu na pasta padrao nesta rodada",
           not (os.path.isfile(chave) and os.path.getmtime(chave) >= _INICIO - 1),
           chave)
    guardado = os.environ.pop("RADAI_RAIZES_NUVEM", None)
    try:
        A._CACHE_RAIZES["quando"] = None
        aqui = A.em_pasta_sincronizada(padrao)[0]
    finally:
        if guardado is not None:
            os.environ["RADAI_RAIZES_NUVEM"] = guardado
        A._CACHE_RAIZES["quando"] = None
    pasta, nuvem, saida = _o_vigia_filho_ve_a_pasta_padrao(False)
    checar(u"o filho com a LOCALAPPDATA trocada e sem RADAI_REGISTRO_DIR (o "
           u"vigia das baterias) ve a pasta padrao como quem roda (%s)"
           % (u"sincroniza" if aqui else u"nao sincroniza"),
           os.path.normcase(pasta) == os.path.normcase(padrao)
           and nuvem == str(aqui), saida[-300:])
    if not aqui:
        print(u"    PULADO a isca do filho: nesta maquina a pasta padrao nao "
              u"sincroniza")
        return
    _p, nuvem_velha, saida_velha = _o_vigia_filho_ve_a_pasta_padrao(True)
    checar(u"  (isca) lendo o Drive so pela variavel, o filho nao ve a "
           u"nuvem (e gravaria a chave nela)", nuvem_velha == u"False",
           saida_velha[-300:])


def teste_a_trava_procura_o_VALOR_e_nao_o_padrao():
    secao(u"a trava procura o valor real, nao um padrao")
    import radai_records as RG
    checar(u"aceita texto limpo",
           RG.conferir_sem_identificacao(u"89 cortes, 5.0 mm", IDENT) is True)
    for rotulo, texto in ((u"o PatientID", u"serie do paciente %s" % PID),
                          (u"o nome", u"laudo de %s" % NOME),
                          (u"o UID inteiro", u"uid=%s" % UID),
                          (u"um pedaco longo do UID", u"..." + UID.split(".")[7] + u"...")):
        try:
            RG.conferir_sem_identificacao(texto, IDENT)
            pegou = False
        except RG.ContemIdentificacao:
            pegou = True
        checar(u"recusa %s" % rotulo, pegou, texto[:40])
    try:
        RG.conferir_sem_identificacao(u"sexo F, estudo 1", ["F", "1", "M"])
        curto_ok = True
    except RG.ContemIdentificacao:
        curto_ok = False
    checar(u"e NAO dispara por identificador de 1 caractere", curto_ok,
           u"guarda que acusa tudo e guarda que se aprende a ignorar")
    try:
        RG.conferir_sem_identificacao(NOME.lower(), IDENT)
        caixa = False
    except RG.ContemIdentificacao:
        caixa = True
    checar(u"e a caixa da palavra nao escapa", caixa)


def teste_o_log_completo_viaja_higienizado():
    secao(u"o log completo, higienizado")
    import radai_records as RG
    base = temp()
    c = um_caso(base)
    p = c.gravar()
    lt = io.open(os.path.join(p, "log.txt"), encoding="utf-8").read()

    for rotulo, valor in ((u"PatientID", PID), (u"nome", NOME),
                          (u"nascimento", NASC), (u"UID", UID)):
        checar(u"o log nao leva o %s" % rotulo, valor.lower() not in lt.lower())
    checar(u"  nem os 8 ultimos do UID, que e o que o log imprime",
           "5171.209" not in lt, lt[:120])
    checar(u"  nem o caminho UNC do share",
           "\\\\servidor" not in lt.lower() and "ISCA_FANTOMA" not in lt, lt[:160])
    checar(u"  nem o caminho de unidade local", "RADIOTERAPIA_AI\\stage" not in lt)
    checar(u"e o que ensina continua no log",
           "94 estrutura" in lt and "carotids" in lt and "13.5 cm3" in lt)
    checar(u"  e o registro diz quantas trocas fez",
           int(c.d["log"]["trocas_de_identificacao"]) >= 4,
           str(c.d["log"]))
    cj = io.open(os.path.join(p, "caso.json"), encoding="utf-8").read()
    checar(u"e o log fica FORA do caso.json (que e o que se varre)",
           "94 estrutura" not in cj and c.d["log"]["arquivo"] == "log.txt")


def teste_o_caso_gravado_nao_carrega_identificacao():
    secao(u"o caso gravado: nada que identifique")
    import radai_records as RG
    base = temp()
    p = um_caso(base).gravar()
    for nome in ("caso.json", "caso.md", "log.txt"):
        txt = io.open(os.path.join(p, nome), encoding="utf-8").read()
        vaza = [v[:14] for v in IDENT if v.lower() in txt.lower()]
        checar(u"`%s` sem identificacao" % nome, not vaza, str(vaza))
    d = json.loads(io.open(os.path.join(p, "caso.json"), encoding="utf-8").read())
    checar(u"tem a serie", d["serie"]["cortes"] == 89)
    checar(u"tem os achados", len(d["achados"]) == 2)
    checar(u"tem o tempo da etapa", d["etapas"][0]["segundos"] == 1725.0)
    checar(u"tem o perfil da maquina", bool(d["estacao"].get("nucleos")))
    checar(u"e o esquema e versionado", d["versao_registro"] == RG.VERSAO_REGISTRO)
    md = io.open(os.path.join(p, "caso.md"), encoding="utf-8").read()
    checar(u"a narrativa tem as secoes que ensinam",
           u"## A máquina" in md and u"## A série" in md and u"achado" in md)
    checar(u"  e declara que nao ha identificacao", u"Sem \nidentificação" in md
           or u"Sem identificação" in md.replace("\n", " "))


def teste_a_descricao_de_serie_e_recusada_na_entrada():
    secao(u"a descricao da serie nao entra")
    import radai_records as RG
    base = temp()
    c = RG.Caso(uid=UID, identificadores=IDENT, base=base)
    c.serie(cortes=10, descricao=u"TC TORAX - MARIA DE FATIMA",
            series_description=u"idem", study_description=u"idem")
    checar(u"`descricao` nao vira campo", "descricao" not in c.d["serie"])
    checar(u"  nem `series_description`", "series_description" not in c.d["serie"])
    checar(u"  nem `study_description`", "study_description" not in c.d["serie"])
    checar(u"e o que e tecnico entra", c.d["serie"]["cortes"] == 10)


def teste_a_gravacao_RECUSA_quando_algo_escapa():
    secao(u"gravar RECUSA quando um identificador escapa")
    import radai_records as RG
    base = temp()
    c = um_caso(base, log=u"")
    c.d["serie"]["operador_anotou"] = u"conferir com %s" % NOME
    try:
        c.gravar()
        recusou = False
    except RG.ContemIdentificacao:
        recusou = True
    checar(u"recusa gravar", recusou,
           u"esquema fechado nao basta: alguem acrescenta um campo")
    casos = RG.listar_casos(base)
    checar(u"  e nao deixou arquivo no disco", not casos, str(casos))


def teste_o_perfil_da_estacao_responde_o_que_ele_perguntou():
    secao(u"o perfil da estacao")
    import radai_records as RG
    base = temp()
    p = RG.perfil_da_estacao(u"servidor de radioterapia", base)
    for campo in ("nucleos", "memoria", "admin", "internet", "gpu",
                  "windows", "papel_declarado"):
        checar(u"tem `%s`" % campo, campo in p, str(sorted(p)))
    checar(u"e nao tem mais os servicos nem o turno (a pausa de servicos "
           u"saiu)", "servicos" not in p and "overnight" not in p,
           str(sorted(p)))
    checar(u"o papel e DECLARADO, nao adivinhado",
           p["papel_declarado"] == u"servidor de radioterapia")
    checar(u"  e `admin` admite «nao deu para saber»",
           p["admin"] in (True, False, None))
    real = os.environ.get("COMPUTERNAME") or ""
    checar(u"o nome da maquina entra pseudonimizado",
           (not real) or (real.lower() not in json.dumps(p).lower()),
           str(p.get("maquina")))
    checar(u"  e ele e estavel (da para comparar a mesma maquina)",
           p["maquina"] == RG.perfil_da_estacao(u"x", base)["maquina"])


def teste_as_versoes_entram_sozinhas():
    secao(u"as versoes do app e dos modelos, automaticas")
    import radai_records as RG
    base = temp()
    import radai_tasks as _K
    _BASE = _K.BASES_CT[0]
    v = RG.versoes(tasks=(_BASE, "lung_vessels"), base=base)
    checar(u"tem a versao do app", bool(v.get("app")), str(v.get("app")))
    checar(u"  e ela sai do entrega.txt, nao de constante no codigo",
           "." in str(v.get("app") or ""), str(v.get("app")))
    checar(u"tem as tasks usadas",
           v.get("tasks") == sorted(["lung_vessels", _BASE]),
           str(v.get("tasks")))

    for _velho, _novo in sorted(_K.APELIDOS.items()):
        _r = RG.versoes(tasks=(_velho,), base=base).get("tasks")
        checar(u"o apelido `%s` vira `%s` no registro" % (_velho, _novo),
               _r == [_novo], str(_r))
    _res = _K.BASES_CT[-1]
    if _res != _BASE:
        _r = RG.versoes(tasks=(_res,), base=base).get("tasks")
        checar(u"e a reserva declarada e registrada COMO ELA",
               _r == [_res], str(_r))
    m = v.get("modelos") or {}
    checar(u"tem as versoes dos motores", bool(m), str(m))
    vagos = [k for k, x in m.items() if x == "presente"]
    checar(u"  e nenhuma delas e a palavra «presente»", not vagos, str(vagos))
    p = um_caso(base).gravar()
    d = json.loads(io.open(os.path.join(p, "caso.json"), encoding="utf-8").read())
    checar(u"o caso gravado ja tem as versoes", bool(d.get("versoes", {}).get("app")))
    md = io.open(os.path.join(p, "caso.md"), encoding="utf-8").read()
    checar(u"  e a narrativa mostra o que produziu o caso",
           u"O que produziu este caso" in md)


def teste_o_indice_acrescenta():
    secao(u"o indice e JSONL e acrescenta")
    import radai_records as RG
    base = temp()
    um_caso(base, uid=UID).gravar()
    um_caso(base, uid=UID + ".2").gravar()
    p = os.path.join(RG.raiz(base), "indice.jsonl")
    linhas = [l for l in io.open(p, encoding="utf-8").read().splitlines() if l.strip()]
    checar(u"uma linha por caso", len(linhas) == 2, str(len(linhas)))
    d = json.loads(linhas[0])
    checar(u"  e cada linha se le sozinha",
           d["pseudonimo"] and d["cortes"] == 89 and d["ok"] is True)
    checar(u"  sem identificacao",
           not [v for v in IDENT if v.lower() in linhas[0].lower()])


def teste_o_exportador_confere_antes_de_selar():
    secao(u"o exportador: confere, recusa, e sela")
    import radai_records as RG
    base = temp()
    um_caso(base).gravar()
    um_caso(base, uid=UID + ".9").gravar()
    saida = temp()
    r = RG.exportar(saida, base=base, nota=u"lote de teste")
    checar(u"exportou", r["ok"], str(r.get("avisos")))
    checar(u"  com os dois casos", r["casos"] == 2, str(r["casos"]))
    with zipfile.ZipFile(r["arquivo"]) as z:
        dentro = z.namelist()
        leiame = z.read("LEIA-ME.md").decode("utf-8")
        tudo = u"".join(z.read(n).decode("utf-8", "replace")
                        for n in dentro if n.endswith((".json", ".md", ".txt")))
    checar(u"  leva o perfil da estacao", "estacao.json" in dentro)
    checar(u"  leva caso.json, caso.md e log.txt",
           any(n.endswith("caso.json") for n in dentro)
           and any(n.endswith("caso.md") for n in dentro)
           and any(n.endswith("log.txt") for n in dentro))
    checar(u"  e um LEIA-ME que diz o que NAO tem",
           u"identificação" in leiame and u"não aprovada" in leiame)
    checar(u"  e o SEGREDO do pseudonimo fica fora",
           not [n for n in dentro if RG.NOME_SEGREDO in n], str(dentro))
    checar(u"  e nada no pacote inteiro carrega identificacao",
           not [v[:14] for v in IDENT if v.lower() in tudo.lower()])

    ruim = os.path.join(RG.raiz(base), "casos", "2020-01-01_velho00")
    os.makedirs(ruim)
    io.open(os.path.join(ruim, "caso.json"), "w", encoding="utf-8").write(
        json.dumps({"versao_registro": 0, "PatientID": PID}))
    r2 = RG.exportar(temp(), base=base)
    checar(u"o caso com campo proibido e recusado",
           any(x["caso"] == "2020-01-01_velho00" for x in r2["recusados"]),
           str(r2["recusados"]))
    checar(u"  e os bons continuam saindo", r2["casos"] == 2)
    ruim2 = os.path.join(RG.raiz(base), "casos", "2020-01-02_velho01")
    os.makedirs(ruim2)
    io.open(os.path.join(ruim2, "caso.json"), "w", encoding="utf-8").write(
        json.dumps({"versao_registro": 1,
                    "nota": "copiei de \\\\servidor\\imagens\\x"}))
    r3 = RG.exportar(temp(), base=base)
    checar(u"e o caso com caminho de sistema tambem e recusado",
           any(x["caso"] == "2020-01-02_velho01" for x in r3["recusados"]),
           str(r3["recusados"]))
    r4 = RG.exportar(temp(), base=base, desde="2099-01-01")
    checar(u"periodo vazio nao gera pacote", r4["ok"] is False)


def teste_quem_chama_registrar_serie():
    import ast
    secao(u"quem chama registrar_serie (as duas portas)")
    vig = io.open(_componentes.fonte("app/radai_watcher.py"),
                  encoding="utf-8", errors="replace").read()
    bat = io.open(_componentes.fonte("app/radai_batch.py"),
                  encoding="utf-8", errors="replace").read()

    checar(u"o «Rodar agora» registra o caso",
           u"radai_records.registrar_serie" in bat)

    VIGIA_REGISTRA = True
    arv = ast.parse(vig)
    funcs = dict((n.name, n) for n in ast.walk(arv)
                 if isinstance(n, ast.FunctionDef))

    def _chama(no, alvo_attr=None, alvo_nome=None):
        for n in ast.walk(no):
            if not isinstance(n, ast.Call):
                continue
            f = n.func
            if alvo_attr and isinstance(f, ast.Attribute) and f.attr == alvo_attr:
                return True
            if alvo_nome and isinstance(f, ast.Name) and f.id == alvo_nome:
                return True
        return False

    reg = funcs.get("_registrar_caso_do_vigia")
    alvos = [reg] if reg else []
    if reg:
        for n in ast.walk(reg):
            if (isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                    and n.func.id in funcs):
                alvos.append(funcs[n.func.id])
    tem = any(_chama(a, alvo_attr="registrar_serie")
              and u"radai_records" in ast.get_source_segment(vig, a)
              for a in alvos)
    checar(u"o vigia registra o caso pelo MESMO ponto de entrada",
           tem == VIGIA_REGISTRA,
           u"`_registrar_caso_do_vigia` %s `radai_records.registrar_serie`"
           % (u"chama" if tem else u"NAO chama"))
    ps = funcs.get("process_series")
    no_finally = False
    if ps is not None:
        for n in ast.walk(ps):
            if isinstance(n, ast.Try) and n.finalbody:
                if any(_chama(x, alvo_nome="_registrar_caso_do_vigia")
                       for x in n.finalbody):
                    no_finally = True
    checar(u"  e chama no `finally` de `process_series` (a serie que falha "
           u"tambem ensina)", no_finally)
    checar(u"  e mede a serie pela medida comum, e nao por uma copia",
           any(_chama(a, alvo_attr="medir_serie") for a in alvos))
    checar(u"  e o vigia continua alimentando o indice do acervo",
           u"radai_archive.registrar_serie" in vig,
           u"sao duas funcoes com o mesmo nome, em modulos diferentes")


def teste_fixture_nao_usa_identificador_plausivel():
    secao(u"nenhum fixture usa identificador plausivel")
    import glob
    import re

    RAIZES = {u"1.2.840.113619": u"GE",
              u"1.3.12.2": u"Siemens",
              u"1.2.840.113704": u"Philips",
              u"1.3.46.670589": u"Philips",
              u"1.2.392": u"Toshiba/Canon",
              u"1.2.840.113845": u"Elekta",
              u"1.2.246": u"Varian"}
    cadeia = re.compile(u"[\"']((?:[0-9]+[.]){3,}[0-9]+)[\"']")

    ruins = []
    for f in _componentes.arquivos("tools", "test_*.py"):
        try:
            t = io.open(f, encoding="utf-8").read()
        except Exception:
            continue
        for m in cadeia.finditer(t):
            for raiz, quem in RAIZES.items():
                if m.group(1).startswith(raiz + u"."):
                    ruins.append(u"%s: raiz de %s"
                                 % (os.path.basename(f), quem))
                    break
    checar(u"nenhum UID de fixture usa raiz de fabricante",
           not ruins, u"; ".join(sorted(set(ruins))) or u"nenhum")

    isca = sorted(RAIZES)[0] + u".2.55.3.1234567890.123"
    checar(u"e a checagem sabe reprovar (isca)",
           any(isca.startswith(r + u".") for r in RAIZES),
           u"se a isca passa, a varredura nao esta olhando a raiz")

    checar(u"o PID do fantoma nao tem a forma de um prontuario",
           not PID.isdigit(), PID)


def teste_o_tempo_da_serie_vem_de_fora():
    secao(u"o tempo da serie vem de quem a rodou")
    import radai_records as RG
    base = temp()
    p = RG.registrar_serie(uid=UID, identificadores=IDENT,
                           serie={"cortes": 117}, resultado={"ok": True},
                           base=base, segundos_totais=2412.37)
    checar(u"o caso foi gravado", bool(p))
    if not p:
        return
    d = json.load(io.open(os.path.join(p, "caso.json"), encoding="utf-8"))
    checar(u"`segundos_totais` é o que o chamador mediu",
           d.get("segundos_totais") == 2412.4, d.get("segundos_totais"))
    checar(u"  e o caso diz de onde veio o número",
           d.get("segundos_origem") == u"medido por quem rodou a serie")
    linha = io.open(os.path.join(base, "indice.jsonl"),
                    encoding="utf-8").read().strip().splitlines()[-1]
    checar(u"  e o índice leva o mesmo número", json.loads(linha)["segundos"] == 2412.4)
    p2 = RG.registrar_serie(uid=UID, identificadores=IDENT,
                            serie={"cortes": 1}, resultado={"ok": True},
                            base=base)
    d2 = json.load(io.open(os.path.join(p2, "caso.json"), encoding="utf-8"))
    checar(u"sem o tempo de fora, o caso diz que contou desde a abertura",
           d2.get("segundos_origem") == u"desde a abertura do registro")


def teste_como_a_serie_rodou():
    secao(u"como a serie rodou (execucao)")
    import radai_records as RG
    base = temp()
    fb = (u"[02:14:09] a placa falhou em parte 3/5 da serie ...%s: CUDA "
          u"error; refazendo a task INTEIRA em CPU" % UID[-8:])
    p = RG.registrar_serie(
        uid=UID, identificadores=IDENT, serie={"cortes": 89},
        resultado={"ok": True}, base=base, segundos_totais=10.0,
        execucao={"modo": "gpu_resultado_na_cpu",
                  "motivo_do_modo": u"livre 2048 MiB (%s)" % PID,
                  "vram_livre_inicio_mb": 2048, "fallbacks": [fb],
                  "tasks_pedidas": ["total_v3"], "tasks_rodadas": ["total_v3"],
                  "tempo_por_parte": None})
    checar(u"o caso foi gravado (a execução passou pela trava)", bool(p))
    if not p:
        return
    d = json.load(io.open(os.path.join(p, "caso.json"), encoding="utf-8"))
    ex = d.get("execucao") or {}
    checar(u"o modo e a VRAM do início ficam no caso",
           ex.get("modo") == "gpu_resultado_na_cpu"
           and ex.get("vram_livre_inicio_mb") == 2048, ex)
    checar(u"o fallback fica, SEM os 8 últimos do UID",
           len(ex.get("fallbacks") or []) == 1
           and UID[-8:] not in ex["fallbacks"][0]
           and "refazendo a task INTEIRA" in ex["fallbacks"][0], ex.get("fallbacks"))
    checar(u"o motivo do modo é higienizado", PID not in (ex.get("motivo_do_modo") or ""),
           ex.get("motivo_do_modo"))
    checar(u"o tempo por parte ausente fica `null`, e não some",
           "tempo_por_parte" in ex and ex["tempo_por_parte"] is None)
    ind = json.loads(io.open(os.path.join(base, "indice.jsonl"),
                             encoding="utf-8").read().strip().splitlines()[-1])
    checar(u"o índice diz o modo e quantos fallbacks (varredura sem abrir caso)",
           ind.get("modo") == "gpu_resultado_na_cpu" and ind.get("fallbacks") == 1, ind)
    md = io.open(os.path.join(p, "caso.md"), encoding="utf-8").read()
    checar(u"a narrativa tem a seção «Como rodou»", u"## Como rodou" in md)


def teste_o_que_o_motor_decidiu_vai_ao_caso():
    secao(u"o que o motor decidiu vai ao caso")
    import radai_records as RG
    job = {"log": [u"x"],
           "plano": {"modo": "cpu", "modo_do_plano": "gpu",
                     "motivo": u"placa com folga | a placa caiu",
                     "recuo_cpu": {"onde": u"parte 2/5",
                                   "prova": u"CUDA out of memory",
                                   "segundos_na_placa": 40.0}},
           "partes": [{"task": "total_v3", "parte": 1, "segundos": 12.0}],
           "recorte_no_corpo": {
               "total_mr": {"estado": u"nao se aplica", "flag": False,
                            "motivo": u"RM: a biblioteca ignora --body_seg",
                            "alerta": False, "falta_peso": False}}}
    d = RG.do_job(job)
    checar(u"`do_job` leva plano, partes e recorte, e nao o log",
           sorted(d) == ["partes", "plano", "recorte_no_corpo"], sorted(d))
    ex = RG.execucao_do_motor(d, recorte_pedido=1)
    checar(u"o recorte e o que VALEU por task, e o pedido fica a parte",
           ex["recorte_no_corpo"]["total_mr"]["estado"] == u"nao se aplica"
           and ex["recorte_no_corpo_pedido"] is True, ex)
    checar(u"  o modo que valeu, o do plano e o recuo da placa",
           ex["modo"] == "cpu" and ex["modo_do_plano"] == "gpu"
           and ex["recuo_cpu"]["onde"] == u"parte 2/5", ex)
    checar(u"  e com partes, a nota fica vazia",
           ex["tempo_por_parte"] == job["partes"]
           and ex["tempo_por_parte_nota"] == u"", ex["tempo_por_parte_nota"])
    vazio = RG.execucao_do_motor(RG.do_job({}), recorte_pedido=None)
    checar(u"sem decisao no job, o recorte e `null` (nao sei), e nao `{}`",
           vazio["recorte_no_corpo"] is None
           and vazio["recorte_no_corpo_pedido"] is None, vazio)
    checar(u"  e a nota diz que nenhuma parte foi vista, e nao que o motor "
           u"nao expoe", u"nenhuma parte vista" in vazio["tempo_por_parte_nota"]
           and u"nao expos" not in vazio["tempo_por_parte_nota"],
           vazio["tempo_por_parte_nota"])
    ruim = RG.do_job(object())
    checar(u"job ilegivel: `do_job` nao levanta, e a nota diz por que",
           bool(ruim.get("job_ilegivel")) and u"nao pode ser lido"
           in RG.execucao_do_motor(ruim)["tempo_por_parte_nota"], ruim)
    base = temp()
    ex2 = RG.execucao_do_motor(RG.do_job(dict(job, recorte_no_corpo={
        "total_v3": {"estado": u"desligado", "falta_peso": True,
                     "motivo": u"falta o Dataset300 (%s)" % PID}})), True)
    p = RG.registrar_serie(uid=UID, identificadores=IDENT,
                           serie={"cortes": 89}, resultado={"ok": True},
                           base=base, segundos_totais=10.0, execucao=ex2)
    checar(u"o caso com o motivo aninhado e gravado (a trava nao o recusou)",
           bool(p), p)
    if p:
        txt = io.open(os.path.join(p, "caso.json"), encoding="utf-8").read()
        checar(u"  o motivo do recorte e higienizado", PID not in txt
               and u"falta o Dataset300" in txt, txt[:160])
        md = io.open(os.path.join(p, "caso.md"), encoding="utf-8").read()
        checar(u"  e a narrativa diz o recorte por task, numa linha legivel",
               u"total_v3 desligado (falta o Dataset300" in md,
               [l for l in md.splitlines() if u"recorte_no_corpo" in l])


def teste_a_task_que_falhou_vai_ao_caso_higienizada():
    secao(u"a task que falhou vai ao caso higienizada")
    import inspect
    import textwrap
    import radai_records as RG
    unc = u"\\\\srv\\Patients\\FANTOMA_ISCA_PASTA\\CT\\IM0001.dcm"
    ex = {"tasks_rodadas": ["total_v3", "breasts"],
          "tasks_falharam": [{"task": "abdominal_muscles",
                              "classe": "recurso",
                              "erro": u"RuntimeError: TS abdominal_muscles "
                                      u"falhou: (%s) nao li %s" % (PID, unc)}]}

    def gravar(execucao):
        base = temp()
        return RG.registrar_serie(uid=UID, identificadores=IDENT,
                                  serie={"cortes": 89},
                                  resultado={"ok": True}, base=base,
                                  segundos_totais=10.0,
                                  execucao=json.loads(json.dumps(execucao)))
    p = gravar(ex)
    checar(u"o caso com o erro da task marcada e gravado (a trava nao o "
           u"recusou)", bool(p), p)
    if p:
        txt = io.open(os.path.join(p, "caso.json"), encoding="utf-8").read()
        d = json.loads(txt)
        f = ((d.get("execucao") or {}).get("tasks_falharam") or [{}])[0]
        checar(u"  sem o PatientID e sem o caminho, com as marcas no lugar",
               PID not in txt and u"FANTOMA_ISCA_PASTA" not in txt
               and u"<paciente>" in f.get("erro", u"")
               and u"<caminho>" in f.get("erro", u""), f)
        checar(u"  e a task, a classe e a causa continuam legiveis",
               f.get("task") == "abdominal_muscles"
               and f.get("classe") == "recurso"
               and u"RuntimeError: TS abdominal_muscles falhou"
               in f.get("erro", u""), f)
    src = textwrap.dedent(inspect.getsource(RG.Caso.gravar))
    alvo = u'("recorte_no_corpo", "recuo_cpu", "tasks_falharam")'
    checar(u"a tupla das frases aninhadas cita `tasks_falharam` (a isca "
           u"abaixo acha o alvo)", alvo in src)
    ns = dict(vars(RG))
    exec(compile(src.replace(alvo, u'("recorte_no_corpo", "recuo_cpu")'),
                 "<isca>", "exec"), ns)
    velho = RG.Caso.gravar
    try:
        RG.Caso.gravar = ns["gravar"]
        p_isca = gravar(ex)
    finally:
        RG.Caso.gravar = velho
    checar(u"ISCA: sem `tasks_falharam` na tupla, o caso e RECUSADO (o "
           u"PatientID fica no texto e a trava o acha)", not p_isca, p_isca)


def teste_os_fallbacks_sao_achados():
    secao(u"os fallbacks do motor sao achados")
    import radai_records as RG
    linhas = [
        u"[22/09 02:14:09]    [02:14:09] a placa falhou em parte 3/5: CUDA error; "
        u"refazendo a task INTEIRA em CPU",
        u"[02:14:09] a placa falhou em parte 3/5: CUDA error; refazendo a task "
        u"INTEIRA em CPU",
        u"[02:20:00] Prediction on device was unsuccessful, probably due to a "
        u"lack of memory. Moving results arrays to CPU",
        u"[02:40:00] a task terminou e o processo nao saiu (thread orfa do "
        u"nnU-Net) - saida aproveitada",
        u"[02:40:01] base anatomica: total_v2 (a total_v3 nao esta instalada "
        u"nesta estacao)",
        u"[02:41:00] TS total_v3 rodando... 30s (still working, please wait)",
    ]
    fb = RG.achar_fallbacks(linhas)
    checar(u"quatro fallbacks distintos, e a linha espelhada conta UMA vez",
           len(fb) == 4, fb)
    checar(u"a frase do próprio nnU-Net é reconhecida",
           any("Moving results arrays to CPU" in x for x in fb))
    checar(u"o batimento NÃO é fallback",
           not any("still working" in x for x in fb))
    c = RG.Coletor(None)
    c(u"FALHOU a placa: refazendo a task INTEIRA em CPU")
    c(u"FALHOU serie ...12345678: nenhuma estrutura gerada")
    tipos = [a["tipo"] for a in c.achados()]
    checar(u"no coletor, a linha de fallback vira achado «fallback», e não "
           u"«ambiente» (ela traz FALHOU também)",
           tipos == ["fallback", "ambiente"], tipos)
    checar(u"  e o coletor devolve os fallbacks dele", len(c.fallbacks()) == 1)


def teste_o_que_so_se_troca_nao_trava():
    secao(u"o que so se troca nao trava a gravacao")
    import radai_records as RG
    base = temp()
    log = (u"[20:17:12] === serie ...%s | %s | 89 cortes | "
           u"SOBRENOME_FANTOMA\\DICOM\\ST00001 ===" % (UID[-8:], PID))
    c = RG.Caso(uid=UID, identificadores=IDENT, base=base,
                so_trocar=["SOBRENOME_FANTOMA", "DICOM", "ST00001"])
    c.serie(modalidade="CT", modalidade_origem="dicom", cortes=89)
    c.log(log)
    c.resultado(True)
    try:
        p = c.gravar()
    except RG.ContemIdentificacao as e:
        p = ""
        checar(u"a gravação NÃO recusou por causa da pasta DICOM", False, str(e))
    if not p:
        return
    lt = io.open(os.path.join(p, "log.txt"), encoding="utf-8").read()
    checar(u"a pasta do paciente foi trocada no log",
           "SOBRENOME_FANTOMA" not in lt, lt)
    cj = io.open(os.path.join(p, "caso.json"), encoding="utf-8").read()
    checar(u"e o caso gravou, com «dicom» onde o registro o escreve",
           '"modalidade_origem": "dicom"' in cj)
    c2 = RG.Caso(uid=UID, identificadores=list(IDENT) + ["DICOM"], base=temp())
    c2.serie(modalidade="CT", modalidade_origem="dicom", cortes=89)
    c2.resultado(True)
    try:
        c2.gravar()
        travou = False
    except RG.ContemIdentificacao:
        travou = True
    checar(u"  (isca) conferida como identificador, a pasta `DICOM` travaria",
           travou, u"se isto passa, a separação entre os dois não mede nada")


def teste_o_caminho_com_espaco_nao_deixa_o_nome():
    secao(u"o caminho com espaco nao deixa pedaco do nome no registro")
    import radai_records as RG
    base = temp()
    pasta = u"\\\\servidor\\imagens\\Patients\\ISCA BELTRANO 12345\\CT"
    log = u"\n".join([
        u"[20:17:12] === serie ...%s | %s | 89 cortes ===" % (UID[-8:], PID),
        u"[20:17:13] Sem DICOM em %s" % pasta,
        u'[20:17:14] The file "C:\\RADIOTERAPIA_AI\\tmp\\ISCA BELTRANO '
        u'12345\\IM0001.dcm" does not exist.',
        u"[20:17:15] copia local em D:\\TEMP\\ISCA BELTRANO 12345 (3 arquivos)",
        u"[20:17:16] painel em http://127.0.0.1:8777/lote",
        u"[20:46:09] 94 estrutura(s) do TotalSegmentator",
    ])
    col = RG.Coletor()
    for ln in log.split(u"\n"):
        col(ln)
    p = RG.registrar_serie(uid=UID, identificadores=[PID], serie={"cortes": 89},
                           resultado={"ok": True}, coletor=col, base=base)
    checar(u"o caso foi gravado", bool(p) and os.path.isdir(p), str(p))
    if not p:
        return
    lt = io.open(os.path.join(p, "log.txt"), encoding="utf-8").read()
    sobra = [x for x in (u"ISCA", u"BELTRANO", u"12345") if x.lower() in lt.lower()]
    checar(u"nenhum pedaco do nome sobra no log.txt (ISCA, BELTRANO, 12345)",
           not sobra, u"%s | %s" % (sobra, lt[:300]))
    checar(u"  e o caminho entre aspas guarda a CAUSA (does not exist)",
           u'"<caminho>" does not exist.' in lt, lt[:400])
    checar(u"  e o endereco do painel NAO e confundido com unidade de disco",
           u"http://127.0.0.1:8777/lote" in lt, lt[-200:])
    checar(u"  e o que ensina continua la", u"94 estrutura" in lt)


def teste_as_duas_portas_trocam_as_pastas_pela_mesma_regra():
    secao(u"as duas portas trocam as pastas pela mesma regra")
    import ast
    import radai_records as RG
    r = RG.pastas_para_trocar(
        [u"\\\\servidor\\imagens\\Patients\\ISCA BELTRANO 12345\\CT\\2016"],
        prefixos=[u"\\\\servidor\\imagens\\Patients"])
    checar(u"com o ROOT como prefixo, sobra so a pasta do paciente",
           r == [u"ISCA BELTRANO 12345"], str(r))
    tmp = tempfile.gettempdir()
    r2 = RG.pastas_para_trocar(
        [os.path.join(tmp, u"radai_portal_ab12", u"ISCA BELTRANO.zip"),
         u"SOBRENOME FANTOMA/CT"], prefixos=[tmp])
    checar(u"com o temporario como prefixo, «Temp» e «Local» nao entram",
           not [x for x in r2 if x.lower() in (u"temp", u"local", u"appdata")],
           str(r2))
    checar(u"  e o .zip entra com e sem a extensao, e a pasta relativa tambem",
           u"ISCA BELTRANO.zip" in r2 and u"ISCA BELTRANO" in r2
           and u"SOBRENOME FANTOMA" in r2, str(r2))
    checar(u"  e pasta curta ou so de digitos nao entra (CT, 2016)",
           u"CT" not in r2 and u"2016" not in r and u"CT" not in r, str(r + r2))

    def _chama(arquivo, funcao):
        arv = ast.parse(io.open(_componentes.fonte("app/" + arquivo), encoding="utf-8").read())
        for no in ast.walk(arv):
            if isinstance(no, ast.FunctionDef) and no.name == funcao:
                return any(isinstance(n, ast.Call)
                           and getattr(n.func, "attr", "") == "pastas_para_trocar"
                           for n in ast.walk(no))
        return None
    checar(u"o vigia usa a regra comum (_identificadores_da_serie)",
           _chama("radai_watcher.py", "_identificadores_da_serie") is True)
    checar(u"e o lote tambem (_pastas_para_trocar)",
           _chama("radai_batch.py", "_pastas_para_trocar") is True)


def teste_a_fase_desliga_a_estatistica_antes_do_cli():
    secao(u"a fase: a estatistica de uso desligada antes do CLI")
    import radai_phase as F
    import radai_records as RG
    try:
        import engine
    except Exception as e:
        checar(u"o motor importa neste runtime (pre-condicao)", False,
               u"%s: %s" % (type(e).__name__, e))
        return
    casa = temp()
    guardado = os.environ.get("TOTALSEG_HOME_DIR")
    os.environ["TOTALSEG_HOME_DIR"] = casa
    cfg = os.path.join(casa, "config.json")
    with io.open(cfg, "w", encoding="utf-8") as f:
        f.write(u'{"totalseg_id": "totalseg_FANTOMA", "send_usage_stats": true, '
                u'"prediction_counter": 3}')
    visto, chamadas = [], []
    velho_run = F.subprocess.run

    def _cli(cmd, **kw):
        chamadas.append(list(cmd))
        with io.open(cfg, encoding="utf-8") as g:
            visto.append(json.load(g).get("send_usage_stats"))
        saida = cmd[cmd.index("-o") + 1]
        with io.open(saida, "w", encoding="utf-8") as g:
            g.write(u'{"phase": "portal_venous", "probability": 0.91}')

        class _R(object):
            returncode, stdout, stderr = 0, b"", b""
        return _R()

    F.subprocess.run = _cli
    try:
        d = RG.medir_serie({"cortes": 89, "modalidade": "CT"},
                           {"nifti": os.path.join(casa, "serie.nii.gz")})
        checar(u"o CLI da fase foi chamado", len(chamadas) == 1, str(chamadas)[:120])
        checar(u"  e no instante do CLI, o arquivo ja dizia false",
               visto == [False], str(visto))
        checar(u"  e a fase medida entra na serie", d.get("fase_contraste")
               == "portal_venous", str(d))
        with io.open(cfg, encoding="utf-8") as g:
            depois = json.load(g)
        checar(u"  e as outras chaves do arquivo ficaram (o contador, o id)",
               depois.get("prediction_counter") == 3
               and depois.get("totalseg_id") == "totalseg_FANTOMA", str(depois))
        with io.open(cfg, "w", encoding="utf-8") as f:
            f.write(u"{{{ nao sou json")
        del chamadas[:]
        d2 = RG.medir_serie({"cortes": 89}, {"nifti": os.path.join(casa, "s.nii")})
        checar(u"sem conseguir desligar, o CLI NAO roda (nenhuma chamada de rede)",
               not chamadas, str(chamadas)[:120])
        checar(u"  e a serie diz «nao medi», com o motivo",
               u"nao rodei" in (d2.get("fase_nao_medida") or u""), str(d2))
    finally:
        F.subprocess.run = velho_run
        if guardado is None:
            os.environ.pop("TOTALSEG_HOME_DIR", None)
        else:
            os.environ["TOTALSEG_HOME_DIR"] = guardado


def teste_a_serie_medida_mora_aqui():
    secao(u"a serie medida mora no registro")
    import ast
    import radai_records as RG
    lote = {"cortes": 117, "espessura_mm": 3.75, "modalidade": "CT", "uid": UID,
            "pid": PID}
    vigia = {"count": 117, "esp_dec": 3.75, "modality": "MR", "uid": UID,
             "pid": PID}
    d = RG.medir_serie(lote, {}, origem=u"rodar agora")
    checar(u"a série do lote: cortes, espessura, modalidade declarada",
           d == {"cortes": 117, "espessura_mm": 3.75, "origem": u"rodar agora",
                 "modalidade": "CT", "modalidade_origem": "dicom"}, d)
    v = RG.medir_serie(vigia, {"forma_zyx": [117, 512, 512], "fov_mm": 500.0,
                               "texto_livre": u"NAO ENTRA"}, origem=u"vigia")
    checar(u"a série do vigia, com as chaves DELE",
           v.get("cortes") == 117 and v.get("espessura_mm") == 3.75
           and v.get("modalidade") == "MR" and v.get("origem") == u"vigia", v)
    checar(u"  as medidas técnicas da imagem entram", v.get("fov_mm") == 500.0)
    checar(u"  e o que não está na lista de permitidos NÃO entra",
           "texto_livre" not in v, sorted(v))
    checar(u"sem modalidade: CT PRESUMIDA, e dito",
           RG.medir_serie({}, {})["modalidade_origem"] == "presumida")
    checar(u"a medida nunca carrega PID nem UID",
           PID not in json.dumps(v) and UID not in json.dumps(v))
    fonte = io.open(_componentes.fonte("app/radai_batch.py"), encoding="utf-8",
                    errors="replace").read()
    if "def _serie_medida" in fonte:
        ns = {}
        i = fonte.index("def _serie_medida")
        j = fonte.index("\ndef ", i + 10)
        exec(compile(fonte[i:j], "<_serie_medida>", "exec"), ns)
        for s, res in ((lote, {}), ({"cortes": 8}, {}),
                       ({"espessura": 0.8, "modalidade": "mr"}, {"cortes": 409}),
                       ({}, {"modalidade": "CT", "cortes": 5})):
            checar(u"a medida comum dá o mesmo que a do lote para %s" % sorted(s),
                   RG.medir_serie(s, res, origem=u"rodar agora")
                   == ns["_serie_medida"](s, res),
                   (RG.medir_serie(s, res), ns["_serie_medida"](s, res)))
        NOVAS = {"count": 117, "esp_dec": 3.75, "modality": "MR"}
        TEC = {"espessura_mm": 2.5, "forma_zyx": [117, 512, 512],
               "fov_mm": 500.0}
        for s, res in ((dict(lote, **NOVAS), dict(TEC)),
                       (dict({"cortes": 8}, **NOVAS), dict(TEC)),
                       (dict(NOVAS), dict(TEC)),
                       ({"espessura": 0.8, "modalidade": "mr"},
                        dict(TEC, cortes=409))):
            antiga = ns["_serie_medida"](s, res)
            nova = RG.medir_serie(s, res, origem=u"rodar agora")
            presumida = antiga.get("modalidade_origem") == "presumida"
            contradiz = [k for k, v in antiga.items()
                         if v is not None
                         and not (presumida and k in ("modalidade",
                                                      "modalidade_origem"))
                         and nova.get(k) != v]
            checar(u"com as chaves novas, %s: nada que a antiga mediu muda"
                   % sorted(s), not contradiz and set(antiga) <= set(nova),
                   (contradiz, antiga, nova))
        so_novas = RG.medir_serie(dict(NOVAS), dict(TEC))
        checar(u"  e onde a antiga ficava sem dado, as chaves novas preenchem",
               so_novas.get("cortes") == 117
               and so_novas.get("espessura_mm") == 2.5
               and so_novas.get("modalidade") == "MR"
               and so_novas.get("fov_mm") == 500.0, so_novas)
    else:
        arv = ast.parse(fonte)
        chama = any(isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                    and n.func.attr == "medir_serie" for n in ast.walk(arv))
        checar(u"o lote trocou a medida própria pela comum", chama)


def teste_o_passo_se_le_como_parte():
    secao(u"o passo da cadeia se le como parte, no caso.md")
    import radai_records as R
    etapas = [{"etapa": u"TS total_v3", "segundos": 812.4},
              {"etapa": u"FULL e OAR", "segundos": 86.0},
              {"etapa": u"montagem e gravacao do FULL", "segundos": 55.8,
               "parte_de": u"FULL e OAR"},
              {"etapa": u"FULL: suavizacao (duas passadas) e compostos",
               "segundos": 30.2, "parte_de": u"montagem e gravacao do FULL"},
              {"etapa": u"serie inteira", "segundos": 920.0}]
    md = R.narrativa({"etapas": etapas})
    linhas = md.splitlines()
    checar(u"a etapa de topo sai sem marca",
           u"| TS total_v3 | 812.4 |" in linhas
           and u"| FULL e OAR | 86.0 |" in linhas, md[:200])
    checar(u"  o passo da cadeia sai com uma marca (↳)",
           u"| ↳ montagem e gravacao do FULL | 55.8 |" in linhas)
    checar(u"  e o passo da montagem, com duas (↳↳)",
           u"| ↳↳ FULL: suavizacao (duas passadas) e compostos | 30.2 |"
           in linhas)
    checar(u"  e a nota diz que somar a coluna conta a cadeia mais de uma vez",
           any(u"somar a coluna" in l for l in linhas))
    sem = [dict((k, v) for k, v in e.items() if k != "parte_de")
           for e in etapas]
    md0 = R.narrativa({"etapas": sem})
    checar(u"  (isca) sem `parte_de`, nenhuma marca e nenhuma nota",
           u"↳" not in md0 and u"somar a coluna" not in md0)


def teste_a_espessura_do_lote_chega_ao_caso():
    secao(u"a espessura do lote chega ao caso")
    import inspect
    import radai_records as RG
    import radai_batch as LB
    s = LB._fixar_espessura({"uid": UID, "pid": PID, "cortes": 3,
                             "modalidade": "CT", "espessura_mm": 5.0,
                             "_zs": set([0.0, 5.0, 10.0])})
    checar(u"(a serie do lote e descrita por `espessura_mm`, sem `espessura`)",
           s.get("espessura_mm") == 5.0 and "espessura" not in s, sorted(s))
    d = RG.medir_serie(s, {}, origem=u"rodar agora")
    checar(u"a serie do lote chega ao caso COM a espessura (era None)",
           d.get("espessura_mm") == 5.0, d)
    checar(u"  e a medida nunca carrega PID nem UID",
           PID not in json.dumps(d) and UID not in json.dumps(d))
    src = inspect.getsource(RG.medir_serie)
    alvo = u'_primeira(s.get("espessura_mm"), s.get("espessura"),'
    checar(u"  (isca) a leitura esta onde a isca a procura", alvo in src)
    ns = dict(vars(RG))
    exec(compile(src.replace(alvo, u'_primeira(s.get("espessura"),'),
                 "<isca-espessura>", "exec"), ns)
    checar(u"ISCA: a leitura antiga (sem `espessura_mm`) devolve None para a "
           u"mesma serie — a checagem sabe reprovar",
           ns["medir_serie"](s, {}).get("espessura_mm") is None)

    class _Ref(object):
        def GetSize(self):
            return (512, 400, 92)

        def GetSpacing(self):
            return (0.9765625, 0.9765625, 5.0)
    m = RG.medidas_da_imagem(_Ref(), 92)
    checar(u"`medidas_da_imagem`: forma, espacamento, FOV e cobertura",
           m.get("forma_zyx") == [92, 400, 512]
           and m.get("espacamento_zyx_mm") == [5.0, 0.977, 0.977]
           and m.get("fov_mm") == 500.0 and m.get("cobertura_z_mm") == 460.0
           and m.get("espessura_mm") == 5.0, m)
    d2 = RG.medir_serie(s, m, origem=u"rodar agora")
    checar(u"  e elas entram no caso pela lista de permitidos",
           d2.get("fov_mm") == 500.0 and d2.get("forma_zyx") == [92, 400, 512],
           d2)
    checar(u"  imagem que nao se mede diz que nao mediu, e nao levanta",
           RG.medidas_da_imagem(object(), 3).get("medida_falhou")
           == "AttributeError")

    e = RG.etapa_da_task("total_v3", 681.34, "ESTACAO", "cuda")
    checar(u"`etapa_da_task`: a linha «TS <task>» com tempo, maquina e "
           u"dispositivo", e == {"etapa": u"TS total_v3", "task": "total_v3",
                                 "segundos": 681.34, "maquina": "ESTACAO",
                                 "dispositivo": "cuda"}, e)
    checar(u"  e a que falhou diz que falhou",
           RG.etapa_da_task("breasts", 1, "E", "cpu", falhou=True).get(
               "falhou") is True)
    job = {"planos": {"total_v3": {"modo": "gpu_resultado_na_cpu"}}}
    checar(u"`dispositivo_da_task`: o modo do plano da task, que o recuo "
           u"reescreve; sem plano, o dispositivo resolvido",
           RG.dispositivo_da_task(job, "total_v3", "cuda")
           == "gpu_resultado_na_cpu"
           and RG.dispositivo_da_task(job, "breasts", "cuda") == "cuda"
           and RG.dispositivo_da_task(None, "x", None) == "")


_NOME_NOVO = r"^\d{4}-\d{2}-\d{2}_\d{6}_[0-9a-f]{8}(_\d+)?$"


def _modulo_de(fonte, nome):
    import types
    m = types.ModuleType(nome)
    m.__file__ = _componentes.fonte("app/radai_records.py")
    exec(compile(fonte, m.__file__, "exec"), m.__dict__)
    return m


def _segunda_tentativa_sobrescreve(RG, base):
    c1 = RG.Caso(uid=UID, identificadores=IDENT, base=base)
    c1.serie(modalidade="CT", cortes=89)
    c1.resultado(False, u"falhou a primeira")
    p1 = c1.gravar(segundos=10)
    c2 = RG.Caso(uid=UID, identificadores=IDENT, base=base)
    c2.serie(modalidade="CT", cortes=89)
    c2.resultado(True)
    p2 = c2.gravar(segundos=20)
    pastas = RG.listar_casos(base)
    idx = os.path.join(RG.raiz(base), "indice.jsonl")
    linhas = [l for l in io.open(idx, encoding="utf-8").read().splitlines()
              if l.strip()]
    return (os.path.normcase(p1) == os.path.normcase(p2)
            or len(pastas) < 2), pastas, linhas


def teste_a_segunda_tentativa_nao_grava_por_cima():
    import re as _re
    secao(u"a segunda tentativa nao grava por cima (pasta com a hora)")
    import radai_records as RG
    sobrescreveu, pastas, linhas = _segunda_tentativa_sobrescreve(RG, temp())
    checar(u"duas tentativas da mesma serie no mesmo dia = duas pastas",
           not sobrescreveu and len(pastas) == 2, str(pastas))
    checar(u"  e o nome tem a data, a HORA e o pseudonimo",
           all(_re.match(_NOME_NOVO, p) for p in pastas), str(pastas))
    checar(u"  e o indice continua UMA linha por tentativa", len(linhas) == 2,
           str(len(linhas)))
    ds = [json.loads(l) for l in linhas]
    checar(u"  e cada linha diz a SUA pasta, que existe",
           sorted(str(d.get("pasta")) for d in ds) == sorted(pastas),
           str([d.get("pasta") for d in ds]))
    checar(u"  e a primeira (a que falhou) continua la",
           any(d.get("ok") is False for d in ds)
           and any(d.get("ok") is True for d in ds))
    base = temp()
    RG_ = RG
    velho = RG_.datetime

    class _Fixo(object):
        @staticmethod
        def now(tz=None):
            return velho(2026, 9, 26, 3, 15, 2)
    try:
        RG_.datetime = _Fixo
        a = um_caso(base).gravar()
        b = um_caso(base).gravar()
    finally:
        RG_.datetime = velho
    checar(u"  e no MESMO SEGUNDO o contador desempata",
           a != b and os.path.basename(b).endswith("_2")
           and os.path.isfile(os.path.join(a, "caso.json"))
           and os.path.isfile(os.path.join(b, "caso.json")),
           "%s | %s" % (os.path.basename(a), os.path.basename(b)))
    fonte = io.open(_componentes.fonte("app/radai_records.py"),
                    encoding="utf-8").read()
    isca = _re.sub(r"(?m)^(def _pasta_nova_do_caso\(.*\n)",
                   r"\1    return _garantir(os.path.join(_garantir(casos), "
                   r"'%s_%s' % (dia, pseudo)))\n", fonte, count=1)
    checar(u"  (isca montada) o nome antigo substitui a funcao",
           isca != fonte)
    if isca != fonte:
        RI = _modulo_de(isca, "radai_records_isca_pasta")
        s2, p2, _ = _segunda_tentativa_sobrescreve(RI, temp())
        checar(u"  (isca) com o nome antigo, a segunda GRAVA POR CIMA e a "
               u"checagem acusa", s2 is True, str(p2))
    base = temp()
    nova = um_caso(base).gravar()
    velha = os.path.join(RG.raiz(base), "casos", "2026-09-20_ab12cd34")
    os.makedirs(velha)
    d = json.loads(io.open(os.path.join(nova, "caso.json"),
                           encoding="utf-8").read())
    d["abriu"] = "2026-09-20T02:00:00-03:00"
    io.open(os.path.join(velha, "caso.json"), "w", encoding="utf-8").write(
        json.dumps(d, ensure_ascii=False))
    checar(u"a pasta no formato ANTIGO continua listada",
           "2026-09-20_ab12cd34" in RG.listar_casos(base),
           str(RG.listar_casos(base)))
    r = RG.exportar(temp(), base=base)
    checar(u"  e exportada", r["ok"] and r["casos"] == 2, str(r))
    r2 = RG.exportar(temp(), base=base, desde="2026-09-20", ate="2026-09-20")
    checar(u"  e o periodo por data vale para os dois formatos",
           r2["ok"] and r2["casos"] == 1, str(r2))


PROCESSAMENTO = {
    "modo": "perso",
    "protocolos": ["torax_mama"],
    "tasks_ligadas": ["total_v3", "trunk_cavities", "breasts"],
    "tasks_desligadas": ["abdominal_muscles"],
    "comparacao": {"ts": 1, "nv": 0, "cads": 0, "mse": 0},
    "oar_fora": ["Esophagus"],
    "clip_box": {"breasts": {"ancora": "torax", "margem_mm": 30,
                             "medido": True, "usado": True, "ganho_s": 41.0}},
    "remocoes": [
        {"nome": "Liver", "volume_cm3": 12.3, "regra": "R1"},
        {"nome": "Lung_L", "volume_cm3": 0.8, "regra": "R2"},
        {"nome": "Lung_L", "volume_cm3": 0.5, "regra": "R2"},
    ],
    "travamentos": [
        {"task": "abdominal_muscles", "motivo": u"15 min sem pulso",
         "retomada": "sem_a_task"},
    ],
    "pico_memoria": {"ram_pct": 97.0, "ram_gb": 15.6},
    "plano_dispositivo": {"modo": "cpu"},
    "tempos_por_passo": [{"passo": "suavizacao", "segundos": 30.2}],
}


def teste_o_caso_leva_o_processamento():
    secao(u"o processamento da v8.3 no caso (modo, remocoes, travamentos...)")
    import radai_records as RG
    base = temp()
    proc = json.loads(json.dumps(PROCESSAMENTO))
    proc["travamentos"][0]["motivo"] = (
        u"sem pulso na serie de %s em \\\\servidor\\imagens\\X" % PID)
    proc["descricao_livre"] = NOME
    p = RG.registrar_serie(
        UID, IDENT, {"modalidade": "CT", "cortes": 89},
        {"ok": True, "estruturas": 40}, processamento=proc, base=base,
        segundos_totais=100.0)
    checar(u"gravou com o processamento", bool(p), str(p))
    if not p:
        return
    d = json.loads(io.open(os.path.join(p, "caso.json"),
                           encoding="utf-8").read())
    pr = d.get("processamento") or {}
    for k in ("modo", "protocolos", "tasks_ligadas", "tasks_desligadas",
              "comparacao", "oar_fora", "clip_box", "remocoes",
              "travamentos", "pico_memoria", "plano_dispositivo",
              "tempos_por_passo"):
        checar(u"  `%s` no caso" % k, k in pr, str(sorted(pr)))
    checar(u"  e chave nao declarada fica FORA (lista de permitidos)",
           "descricao_livre" not in pr
           and "descricao_livre" in (pr.get("campos_ignorados") or []),
           str(sorted(pr)))
    txt = json.dumps(d, ensure_ascii=False).lower()
    checar(u"  e o motivo do travamento sai higienizado (sem PHI, sem "
           u"caminho)", PID.lower() not in txt and "servidor" not in txt
           and NOME.lower() not in txt)
    idx = [json.loads(l) for l in io.open(
        os.path.join(RG.raiz(base), "indice.jsonl"),
        encoding="utf-8").read().splitlines() if l.strip()]
    checar(u"  e o indice leva o modo, as remocoes e os travamentos",
           idx and idx[-1].get("modo_processamento") == "perso"
           and idx[-1].get("remocoes") == 3
           and idx[-1].get("travamentos") == 1, str(idx[-1:]))
    md = io.open(os.path.join(p, "caso.md"), encoding="utf-8").read()
    checar(u"  e a narrativa mostra o modo e as remocoes",
           u"perso" in md and u"R1" in md and u"Liver" in md)
    p2 = RG.registrar_serie(UID + ".7", IDENT, {"modalidade": "CT"},
                            {"ok": True}, base=temp())
    d2 = json.loads(io.open(os.path.join(p2, "caso.json"),
                            encoding="utf-8").read())
    checar(u"sem o processamento, o caso nao ganha a chave (opcional)",
           "processamento" not in d2, str(sorted(d2)))


def teste_as_funcoes_comuns_do_processamento():
    secao(u"as funcoes comuns do processamento (as duas portas)")
    import inspect
    import radai_records as RG
    rem = RG.remocoes_do_full([
        {"regra": u"R2 ilhas", "nome": "lung_left", "cm3": 0.804,
         "inteira": False, "motivo": u"ilha de 2%"}, "ilegivel", None])
    checar(u"remocoes_do_full: a regra curta, o cm3 arredondado e o motivo "
           u"com a frase inteira; item ilegivel fica fora",
           rem == [{"nome": "lung_left", "volume_cm3": 0.8, "regra": "R2",
                    "inteira": False, "motivo": u"R2 ilhas: ilha de 2%"}],
           str(rem))
    il = RG.ilhas_do_full([{"nome": "stomach", "ilhas": "2", "cm3": 3.14159},
                           42, {"nome": "liver", "ilhas": "x"}])
    checar(u"ilhas_do_full: {nome, ilhas, cm3} normalizados; item ilegivel "
           u"fica fora", il == [{"nome": "stomach", "ilhas": 2, "cm3": 3.14}],
           str(il))
    checar(u"ilhas_do_full(None) e [] (nunca levanta)",
           RG.ilhas_do_full(None) == [])
    pl = RG.plano_do_caso({"modo": "gpu", "placa": "P2200", "task": "total_v3"},
                          {"breasts": {"modo": "cpu", "plano_menor": True,
                                       "x": 1}})
    checar(u"plano_do_caso: o plano solto, e o de cada task em `por_task` so "
           u"com as chaves de plano",
           pl == {"modo": "gpu", "placa": "P2200", "task": "total_v3",
                  "por_task": {"breasts": {"modo": "cpu",
                                           "plano_menor": True}}}, str(pl))
    checar(u"plano_do_caso: sem plano, a serie em CPU diz que nao havia placa "
           u"a decidir (a frase do vigia)",
           RG.plano_do_caso(None, None, dispositivo="CPU")
           == RG.PLANO_SEM_PLACA
           and RG.PLANO_SEM_PLACA == {"modo": "cpu",
                                      "motivo": "DEVICE resolveu para cpu"})
    checar(u"plano_do_caso: sem plano e fora da CPU, `None` (nao inventa)",
           RG.plano_do_caso(None, None, dispositivo="cuda") is None
           and RG.plano_do_caso() is None)
    checar(u"plano_do_caso com lixo nao levanta",
           RG.plano_do_caso(object(), 7) is None)
    linhas = [u"TS breasts memoria: 6.0 GB livres no inicio, 2.5 no pico de "
              u"uso (-3.5 GB com tudo o que rodou junto), 84% da estacao no "
              u"pior momento",
              u"TS total_v3 memoria: 9.3 GB livres no inicio, 0.4 no pico de "
              u"uso (-8.9 GB com tudo o que rodou junto), 97% da estacao no "
              u"pior momento"]
    pm = RG.pico_de_memoria(linhas) or {}
    checar(u"pico_de_memoria: o pior momento, e o de cada task",
           pm.get("ram_pct") == 97.0 and pm.get("task") == "total_v3"
           and pm.get("livre_min_gb") == 0.4
           and sorted(pm.get("por_task") or {}) == ["breasts", "total_v3"],
           str(pm))
    checar(u"pico_de_memoria sem a linha do motor e `None` (campo fora)",
           RG.pico_de_memoria([u"outra coisa"]) is None
           and RG.pico_de_memoria(None) is None)
    src = inspect.getsource(RG.plano_do_caso)
    alvo = u"if k in _CHAVES_DO_PLANO_POR_TASK"
    ns = dict(vars(RG))
    exec(compile(src.replace(alvo, u"if True"), "<isca-plano>", "exec"), ns)
    pl_i = ns["plano_do_caso"](None, {"breasts": {"modo": "cpu", "x": 1}})
    checar(u"ISCA: sem o filtro, a chave estranha do job chega ao `por_task` "
           u"(a checagem reprova)", alvo in src
           and (pl_i or {}).get("por_task", {}).get("breasts", {}).get("x")
           == 1, str(pl_i))


def teste_as_funcoes_comuns_da_trilha_e1():
    secao(u"as funcoes comuns da trilha E1")
    import inspect
    import radai_records as RG

    def _entrada(t, modo=None):
        e = {"ancora": "torax", "medido": False, "numeros": None}
        if modo == "fast":
            e.update({"ancora": "glandula", "medido": True,
                      "numeros": {"dice_min": 0.9925}})
        return e
    rec = {"abdominal_muscles": {"ancora": "glandula", "medido": True,
                                 "fracao": 0.3, "zyx": ((1, 2), (0, 5),
                                                        (0, 5))}}
    cb = RG.clip_box_do_caso(rec, modo="fast", entrada=_entrada)
    a = cb.get("abdominal_muscles") or {}
    checar(u"clip_box_do_caso: medido e numeros da entrada do modo, sem `zyx`",
           a.get("medido") is True and a.get("usado") is True
           and a.get("numeros") == {"dice_min": 0.9925} and "zyx" not in a,
           str(a))
    b = (RG.clip_box_do_caso(rec).get("abdominal_muscles") or {})
    checar(u"  sem a entrada, o `medido` da caixa e nenhum numero inventado",
           b.get("medido") is True and "numeros" not in b, str(b))
    checar(u"  e lixo nao levanta", RG.clip_box_do_caso(None) == {}
           and RG.clip_box_do_caso({"x": 7}) == {})
    src = inspect.getsource(RG.clip_box_do_caso)
    alvo = u"entrada(t, modo=modo)"
    ns = dict(vars(RG))
    exec(compile(src.replace(alvo, u"entrada(t, modo=None)"), "<isca-cb>",
                 "exec"), ns)
    ai = (ns["clip_box_do_caso"](rec, modo="fast", entrada=_entrada)
          .get("abdominal_muscles") or {})
    checar(u"ISCA: pela entrada da TASK, o recorte do FAST sai «nao medido» "
           u"(a checagem reprova)", alvo in src and ai.get("medido") is False,
           str(ai))
    fr = RG.oar_fora_por_regiao_do_caso({"pelvic_muscles": u"pelve: nao",
                                         "bone_pelvic": u"pelve: nao"})
    checar(u"oar_fora_por_regiao_do_caso: [{chave, motivo}] na ordem da chave",
           fr == [{"chave": "bone_pelvic", "motivo": u"pelve: nao"},
                  {"chave": "pelvic_muscles", "motivo": u"pelve: nao"}],
           str(fr))
    checar(u"  e e campo do registro (nao vai para `campos_ignorados`)",
           "oar_fora_por_regiao" in RG.CAMPOS_DO_PROCESSAMENTO)
    c = RG.Caso(UID, IDENT)
    c.processamento(modo="auto", oar_fora_por_regiao=fr)
    md = u"\n".join(RG._narrativa_do_processamento(c.d["processamento"]))
    checar(u"  e o caso.md diz cada estrutura com o motivo",
           u"fora do entregue pela região" in md and u"pelvic_muscles" in md
           and not c.d["processamento"].get("campos_ignorados"), md[-300:])
    cd = RG.campos_do_done(
        modalidade="CT", tasks_da_serie=["total_v3", "breasts"],
        plano={"modo": "gpu_resultado_na_cpu", "motivo": u"x"},
        dispositivo="cuda", gravados=["oar", "full", ""],
        travamentos=[{"task": "breasts", "motivo": "sem_pulso",
                      "retomada": "ok", "numeros": {"sem_pulso_s": 900}}],
        regioes=("torax",),
        etapas=[{"etapa": "TS total_v3", "task": "total_v3",
                 "segundos": 812.6, "maquina": "PC_A", "dispositivo": "cpu",
                 "falhou": False}])
    checar(u"campos_do_done: as chaves comuns",
           sorted(cd) == ["etapas", "gravados", "modalidade",
                          "plano_dispositivo", "regioes", "tasks_da_serie",
                          "travamentos"], str(sorted(cd)))
    checar(u"  o plano e o `modo` dele; sem plano, o dispositivo",
           cd["plano_dispositivo"] == "gpu_resultado_na_cpu"
           and RG.campos_do_done(dispositivo="cpu")["plano_dispositivo"]
           == "cpu")
    checar(u"  as travas sem os numeros crus; os gravados sem vazio",
           cd["travamentos"] == [{"task": "breasts", "motivo": "sem_pulso",
                                  "retomada": "ok"}]
           and cd["gravados"] == ["oar", "full"], str(cd))
    checar(u"  as etapas com a maquina, o dispositivo e os segundos inteiros",
           cd["etapas"] == [{"etapa": "TS total_v3", "task": "total_v3",
                             "maquina": "PC_A", "dispositivo": "cpu",
                             "segundos": 812}], str(cd["etapas"]))
    checar(u"  e com lixo nao levanta",
           isinstance(RG.campos_do_done(plano=7, travamentos=[3],
                                        etapas=[None]), dict))


_MAQ_FANTOMA = u"PC-FANTOMA-MARIA"


def teste_a_maquina_das_etapas_entra_por_pseudonimo():
    secao(u"a maquina das etapas do caso entra por pseudonimo")
    import inspect
    import radai_records as RG
    antes = os.environ.get("COMPUTERNAME")
    os.environ["COMPUTERNAME"] = _MAQ_FANTOMA
    try:
        base = temp()
        etapas = [RG.etapa_da_task(u"total_v3", 812.6, _MAQ_FANTOMA, "cpu"),
                  RG.etapa_da_task(u"breasts", 90.0, _MAQ_FANTOMA.lower(),
                                   "cpu"),
                  RG.etapa_da_task(u"trunk_cavities", 60.0,
                                   u"OUTRA-ESTACAO-JOAO", "cpu")]
        p = RG.registrar_serie(uid=UID, identificadores=IDENT,
                               serie={"modalidade": "CT", "cortes": 89},
                               resultado={"ok": True, "estruturas": 40},
                               etapas=etapas, base=base,
                               segundos_totais=1000.0)
        checar(u"o caso foi gravado", bool(p), str(p))
        txt = io.open(os.path.join(p, "caso.json"),
                      encoding="utf-8").read() if p else u""
        md = io.open(os.path.join(p, "caso.md"),
                     encoding="utf-8").read() if p else u""
        d = json.loads(txt) if txt else {}
        crus = [n for n in (_MAQ_FANTOMA, u"OUTRA-ESTACAO-JOAO")
                if n.lower() in (txt + md).lower()]
        checar(u"nenhum nome de maquina cru no caso.json nem no caso.md",
               bool(txt) and not crus, str(crus))
        est = (d.get("estacao") or {}).get("maquina")
        maqs = [e.get("maquina") for e in d.get("etapas") or []
                if e.get("task")]
        checar(u"  a desta estacao e o MESMO pseudonimo do estacao.maquina "
               u"(maiuscula ou minuscula)", bool(est)
               and maqs[:2] == [est, est], u"%s %s" % (est, maqs))
        checar(u"  e a de outra estacao tambem sai por pseudonimo (8 hex, "
               u"diferente da desta)", len(maqs) == 3 and len(maqs[2]) == 8
               and maqs[2] != est and maqs[2] == RG.pseudonimo_de_uma_maquina(
                   u"OUTRA-ESTACAO-JOAO", base), str(maqs))
        checar(u"  e as etapas do chamador (as do `done`) continuam com o "
               u"nome real", etapas[0]["maquina"] == _MAQ_FANTOMA
               and RG.campos_do_done(etapas=etapas)["etapas"][0]["maquina"]
               == _MAQ_FANTOMA)
        src = inspect.getsource(RG.Caso.etapa)
        alvo = u"pseudonimo_de_uma_maquina(e[\"maquina\"], self.base)"
        ns = dict(vars(RG))
        exec(compile(u"class _C(Caso):\n" + u"\n".join(
            u"    " + l[4:] if l.startswith(u"    ") else l
            for l in src.replace(alvo, u"e[\"maquina\"]").splitlines()),
            "<isca-etapa>", "exec"), ns)
        c = ns["_C"](UID, IDENT, base=base)
        c.etapa(u"TS total_v3", 1.0, maquina=_MAQ_FANTOMA)
        checar(u"ISCA: o Caso.etapa sem a troca grava o nome cru (a checagem "
               u"reprova)", alvo in src
               and c.d["etapas"][-1].get("maquina") == _MAQ_FANTOMA,
               str(c.d["etapas"][-1]))
        velho = os.path.join(RG.raiz(base), "casos", "2026-09-20_velhomaq")
        os.makedirs(velho)
        io.open(os.path.join(velho, "caso.json"), "w",
                encoding="utf-8").write(json.dumps(
                    {"versao_registro": 1, "pseudonimo": "ab12cd34",
                     "estacao": {"maquina": est},
                     "etapas": [{"etapa": "TS total_v3", "task": "total_v3",
                                 "maquina": _MAQ_FANTOMA,
                                 "dispositivo": "cpu"}]}))
        r = RG.exportar(temp(), base=base)
        with zipfile.ZipFile(r["arquivo"]) as z:
            tudo = u"".join(z.read(n).decode("utf-8", "replace")
                            for n in z.namelist())
            vj = json.loads(z.read(
                "casos/2026-09-20_velhomaq/caso.json").decode("utf-8"))
        checar(u"o exportador leva o caso antigo com a maquina por "
               u"pseudonimo", r["ok"] and _MAQ_FANTOMA.lower()
               not in tudo.lower() and vj["etapas"][0]["maquina"] == est,
               str(vj.get("etapas")))
        checar(u"  e o caso antigo no disco nao muda", _MAQ_FANTOMA in io.open(
            os.path.join(velho, "caso.json"), encoding="utf-8").read())
        src2 = inspect.getsource(RG._maquinas_por_pseudonimo)
        alvo2 = u"e[\"maquina\"] = pseudonimo_de_uma_maquina("
        ns2 = dict(vars(RG))
        exec(compile(src2.replace(alvo2, u"_x = (", 1), "<isca-exp>",
                     "exec"), ns2)
        verdadeira = RG._maquinas_por_pseudonimo
        RG._maquinas_por_pseudonimo = ns2["_maquinas_por_pseudonimo"]
        try:
            ri = RG.exportar(temp(), base=base)
            with zipfile.ZipFile(ri["arquivo"]) as z:
                tudo_i = u"".join(z.read(n).decode("utf-8", "replace")
                                  for n in z.namelist())
        finally:
            RG._maquinas_por_pseudonimo = verdadeira
        checar(u"ISCA: sem a troca no exportador, o nome cru entra no pacote "
               u"(a checagem reprova)", alvo2 in src2
               and _MAQ_FANTOMA.lower() in tudo_i.lower())
    finally:
        if antes is None:
            os.environ.pop("COMPUTERNAME", None)
        else:
            os.environ["COMPUTERNAME"] = antes


def _base_do_relatorio():
    import radai_records as RG
    base = temp()
    for i, (modo, ok) in enumerate((("auto", True), ("fast", True),
                                    ("perso", False))):
        proc = json.loads(json.dumps(PROCESSAMENTO))
        proc["modo"] = modo
        if ok:
            proc["travamentos"] = []
        RG.registrar_serie(
            UID + ".%d" % i, IDENT,
            {"modalidade": "CT", "cortes": 89, "espessura_mm": 5.0},
            {"ok": ok, "estruturas": 40 + i,
             "erro": ("" if ok else u"a task %s travou" % PID)},
            etapas=[{"etapa": u"TS total_v3", "segundos": 1200.0 + i},
                    {"etapa": u"FULL e OAR", "segundos": 80.0},
                    {"etapa": u"suavizacao", "segundos": 30.0,
                     "parte_de": u"FULL e OAR"}],
            achados=[{"tipo": "suspeita", "detalhe": u"rim pequeno"}],
            execucao={"origem": "vigia" if modo == "auto" else "rodar agora",
                      "modo": "cpu"},
            processamento=proc, base=base, segundos_totais=1500.0 + i)
    velha = os.path.join(RG.raiz(base), "casos", "2026-09-20_ab12cd34")
    os.makedirs(velha)
    io.open(os.path.join(velha, "caso.json"), "w", encoding="utf-8").write(
        json.dumps({"versao_registro": 1, "pseudonimo": "ab12cd34",
                    "abriu": "2026-09-20T02:00:00-03:00",
                    "resultado": {"ok": True, "estruturas": 38},
                    "versoes": {"app": "8.1"}, "segundos_totais": 2000.0,
                    "estacao": {"maquina": "ffff0000"}}))
    ruim = os.path.join(RG.raiz(base), "casos", "2026-09-21_velho00")
    os.makedirs(ruim)
    io.open(os.path.join(ruim, "caso.json"), "w", encoding="utf-8").write(
        json.dumps({"versao_registro": 0, "PatientID": PID}))
    return base


def teste_o_relatorio_de_periodo():
    secao(u"o relatorio de periodo (HTML e Markdown, sem identificacao)")
    import radai_records as RG
    base = _base_do_relatorio()
    rel = RG.relatorio_de_periodo(base=base)
    checar(u"leu os quatro casos bons e recusou o do campo proibido",
           rel.get("casos") == 4
           and any(x.get("caso") == "2026-09-21_velho00"
                   for x in rel.get("recusados") or []),
           "%s %s" % (rel.get("casos"), rel.get("recusados")))
    checar(u"  as tentativas vem do indice (tres linhas)",
           rel.get("tentativas") == 3, str(rel.get("tentativas")))
    checar(u"  os modos: auto, fast, perso e o antigo sem modo",
           (rel.get("modos") or {}).get("auto") == 1
           and rel["modos"].get("fast") == 1
           and rel["modos"].get("perso") == 1
           and rel["modos"].get(u"não declarado") == 1, str(rel.get("modos")))
    checar(u"  concluidos 3, falharam 1",
           rel.get("concluidos") == 3 and rel.get("falharam") == 1,
           "%s %s" % (rel.get("concluidos"), rel.get("falharam")))
    et = dict((e["etapa"], e) for e in rel.get("etapas") or [])
    checar(u"  o tempo por etapa (mediana), SEM somar os passos na etapa",
           u"TS total_v3" in et and et[u"TS total_v3"]["n"] == 3
           and et[u"TS total_v3"]["mediana"] == 1201.0
           and (u"suavizacao" not in et
                or et[u"suavizacao"].get("parte_de") == u"FULL e OAR"),
           str(et.get(u"TS total_v3")))
    rm = rel.get("remocoes") or {}
    checar(u"  as remocoes por regra e por estrutura",
           rm.get("total") == 9 and rm.get("por_regra", {}).get("R2") == 6
           and dict(rm.get("por_estrutura") or []).get("Lung_L") == 6,
           str(rm))
    checar(u"  as suspeitas (achados por tipo)",
           (rel.get("achados") or {}).get("suspeita") == 3,
           str(rel.get("achados")))
    tv = rel.get("travamentos") or {}
    checar(u"  os travamentos por task",
           tv.get("total") == 1
           and (tv.get("por_task") or {}).get("abdominal_muscles") == 1,
           str(tv))
    checar(u"  as falhas com o motivo, sem o identificador",
           rel.get("falhas") and all(PID.lower() not in json.dumps(
               rel["falhas"], ensure_ascii=False).lower() for _ in (1,)),
           str(rel.get("falhas")))
    checar(u"  as versoes (app) e as estacoes (pseudonimo)",
           (rel.get("versoes") or {}).get("app", {}).get("8.1") == 1
           and rel.get("estacoes"), str(rel.get("versoes")))
    md = RG.relatorio_markdown(rel)
    ht = RG.relatorio_html(rel)
    for nome, t in ((u"Markdown", md), (u"HTML", ht)):
        baixo = t.lower()
        checar(u"  o %s tem as secoes (modos, etapas, remocoes, falhas, "
               u"travamentos, versoes, estacoes)" % nome,
               all(x in baixo for x in (u"modo", u"etapa", u"remo", u"falha",
                                        u"travamento", u"vers", u"esta")))
        checar(u"  e o %s nao carrega identificacao nem caminho" % nome,
               not [v for v in IDENT if v.lower() in baixo]
               and "\\\\servidor" not in baixo and ":\\" not in baixo)
    checar(u"  o HTML e uma pagina inteira, com tema claro e escuro",
           ht.lstrip().lower().startswith("<!doctype html")
           and "prefers-color-scheme" in ht)
    def _recusa(texto, ident=()):
        try:
            RG.conferir_relatorio(texto, ident)
            return False
        except RG.ContemIdentificacao:
            return True
    checar(u"a trava passa o relatorio limpo", not _recusa(md)
           and not _recusa(ht))
    checar(u"  (isca) um CAMINHO no texto e recusado",
           _recusa(md + u"\ncopiado de \\\\servidor\\imagens\\X"))
    checar(u"  (isca) um UID no texto e recusado",
           _recusa(md + u"\n" + UID))
    checar(u"  (isca) o VALOR real, quando quem chama o tem, e recusado",
           _recusa(md + u"\n" + NOME, IDENT))
    saida = temp()
    g = RG.gravar_relatorio(saida, base=base)
    checar(u"gravar_relatorio escreve o .md e o .html",
           g.get("ok") and os.path.isfile(g.get("md", ""))
           and os.path.isfile(g.get("html", "")), str(g))
    r = RG.exportar(temp(), base=base)
    with zipfile.ZipFile(r["arquivo"]) as z:
        dentro = z.namelist()
    checar(u"e o pacote de casos leva o relatorio junto (md e html)",
           "relatorio.md" in dentro and "relatorio.html" in dentro,
           str(dentro))
    rp = RG.relatorio_de_periodo(base=base, desde="2026-09-20",
                                 ate="2026-09-20")
    checar(u"o periodo filtra (so o caso antigo de 20/09)",
           rp.get("casos") == 1, str(rp.get("casos")))
    rv = RG.relatorio_de_periodo(base=base, desde="2099-01-01")
    checar(u"periodo vazio: zero casos, e o relatorio diz",
           rv.get("casos") == 0
           and u"nenhum caso" in RG.relatorio_markdown(rv).lower())


def _mudar_pid_do_andamento(RG, base, pseudo, pid_novo):
    velho = RG._arquivo_em_andamento(pseudo, os.getpid(), base)
    with io.open(velho, encoding="utf-8") as f:
        x = json.load(f)
    x["pid_os"] = pid_novo
    novo = RG._arquivo_em_andamento(pseudo, pid_novo, base)
    with io.open(novo, "w", encoding="utf-8") as f:
        f.write(json.dumps(x))
    os.remove(velho)
    return novo


def teste_o_caso_em_andamento_vira_interrompido():
    secao(u"o caso gravado ao comecar, e o interrompido fechado ao abrir")
    import radai_records as RG
    base = temp()
    c = RG.CasoEmAndamento(uid=UID, origem=u"vigia", modo=u"auto", base=base)
    checar(u"o caso em andamento e gravado ao comecar", c.abrir()
           and os.path.isfile(c.caminho), c.caminho)
    c.etapa(u"TS total_v3")
    bruto = io.open(c.caminho, encoding="utf-8").read()
    checar(u"  leva a ultima etapa e a hora, sem UID nem identificacao",
           u"TS total_v3" in bruto and u"hora_da_etapa" in bruto
           and not [v for v in IDENT if v.lower() in bruto.lower()]
           and UID[-8:] not in bruto, bruto[:200])
    checar(u"  o do PROPRIO processo nao e fechado ao abrir (ele esta vivo)",
           RG.fechar_interrompidos(vivo=lambda p: False, base=base) == []
           and os.path.isfile(c.caminho))
    p_morto = _mudar_pid_do_andamento(RG, base, c.d["pseudonimo"], 4000001)
    checar(u"  (isca) com o processo dono VIVO, nada e fechado",
           RG.fechar_interrompidos(vivo=lambda p: True, base=base) == []
           and os.path.isfile(p_morto))
    linhas = []
    fechados = RG.fechar_interrompidos(vivo=lambda p: False, base=base,
                                       log=linhas.append)
    checar(u"de processo morto: vira um caso «interrompido»",
           len(fechados) == 1 and not os.path.exists(p_morto), str(fechados))
    d = {}
    if fechados:
        d = json.load(io.open(os.path.join(RG.raiz(base), "casos",
                                           fechados[0], "caso.json"),
                              encoding="utf-8"))
    r = d.get("resultado") or {}
    checar(u"  com a ultima etapa e a hora no motivo",
           r.get("interrompido") is True and r.get("ok") is False
           and r.get("ultima_etapa") == u"TS total_v3"
           and u"TS total_v3" in (r.get("erro") or u"")
           and (r.get("hora_da_etapa") or u"")[11:16] in r.get("erro", u""),
           str(r))
    checar(u"  a porta e o modo vao junto",
           (d.get("execucao") or {}).get("origem") == u"vigia"
           and (d.get("processamento") or {}).get("modo") == u"auto", str(d)[:200])
    idx = [json.loads(l) for l in io.open(
        os.path.join(RG.raiz(base), "indice.jsonl"), encoding="utf-8")
        if l.strip()]
    checar(u"  e entra no indice marcado como interrompido",
           idx and idx[-1].get("interrompido") is True, str(idx[-1:]))
    checar(u"  e o log diz quantos fechou", linhas
           and u"interrompido" in linhas[-1], str(linhas))
    c2 = RG.CasoEmAndamento(uid=UID + ".7", origem=u"rodar agora", base=base)
    c2.abrir()
    RG.registrar_serie(UID + ".7", IDENT, {"modalidade": "CT"},
                       {"ok": True}, base=base)
    checar(u"o caso que termina tira o em andamento (registrar_serie)",
           not os.path.exists(c2.caminho))
    c3 = RG.CasoEmAndamento(uid=UID + ".8", origem=u"vigia", base=base)
    c3.abrir()
    RG.registrar_serie(UID + ".8", IDENT, {"modalidade": "CT"},
                       {"ok": False, "erro": u"falhou com %s" % PID}, base=base)
    checar(u"  e tambem quando o registro e RECUSADO (a serie terminou)",
           not os.path.exists(c3.caminho))


def teste_o_log_da_serie_na_pasta():
    secao(u"o log da serie na pasta dela: linha a linha, sem identificacao")
    import radai_records as RG
    pasta = os.path.join(temp(), "_RadAI")
    lg = RG.LogDaSerie(pasta, UID, identificadores=IDENT,
                       so_trocar=[u"ISCA_FANTOMA"])
    checar(u"abre o arquivo na _RadAI, com o UID no nome", lg.abrir()
           and os.path.basename(lg.caminho) == UID + u".log.txt")
    for l in LOG.splitlines():
        lg(l)
    lg(u"etapa sem carimbo")
    escrito = io.open(lg.caminho, encoding="utf-8").read()
    checar(u"  cada linha ja esta no disco ANTES de fechar (flush a cada linha)",
           escrito.count(u"\n") == len(LOG.splitlines()) + 1,
           str(escrito.count(u"\n")))
    checar(u"  sem PatientID, sem nome, sem data de nascimento e sem caminho",
           not [v for v in IDENT if v.lower() in escrito.lower()]
           and u"ISCA_FANTOMA" not in escrito and u":\\" not in escrito,
           escrito[:300])
    checar(u"  a linha sem carimbo ganha a hora",
           re.search(r"\[\d\d/\d\d \d\d:\d\d:\d\d\] etapa sem carimbo", escrito))
    lg.fechar()
    curto = RG.LogDaSerie(pasta, UID + ".2", teto=200)
    curto.abrir()
    for i in range(40):
        curto(u"linha %02d de um log comprido" % i)
    t = io.open(curto.caminho, encoding="utf-8").read()
    curto.fechar()
    checar(u"o teto para o log e diz onde parou",
           len(t.encode("utf-8")) < 200 + 120
           and t.rstrip().endswith(u"parou aqui ...]"), str(len(t)))
    de_novo = RG.LogDaSerie(pasta, UID + ".2", teto=200)
    de_novo.abrir()
    de_novo(u"a tentativa seguinte")
    de_novo.fechar()
    checar(u"  e a tentativa seguinte comeca um arquivo novo (o cheio vira o "
           u"anterior)", os.path.isfile(de_novo.anterior)
           and u"a tentativa seguinte" in io.open(
               de_novo.caminho, encoding="utf-8").read())
    cru = os.path.join(pasta, u"cru.txt")
    with io.open(cru, "w", encoding="utf-8") as f:
        f.write(LOG)
    checar(u"  (isca) sem a higienizacao o PatientID estaria no arquivo",
           PID in io.open(cru, encoding="utf-8").read())


def teste_o_relatorio_diz_versao_datas_e_interrompidos():
    secao(u"o relatorio diz a versao, as datas, os interrompidos e os recentes")
    import radai_records as RG
    base = temp()
    casos = os.path.join(RG.raiz(base), "casos")

    def caso(nome, abriu, app, build, ok, erro=u"", origem=u"vigia",
             modo=u"auto"):
        p = os.path.join(casos, nome)
        os.makedirs(p)
        d = {"versao_registro": 1, "pseudonimo": nome[-8:], "abriu": abriu,
             "resultado": {"ok": ok, "erro": erro},
             "versoes": {"app": app, "build": build},
             "execucao": {"origem": origem},
             "processamento": {"modo": modo,
                               "travamentos": ([{"task": "total_v3",
                                                 "motivo": u"tempo limite"}]
                                               if not ok else [])},
             "estacao": {"maquina": "ab12ab12"}, "segundos_totais": 600.0}
        io.open(os.path.join(p, "caso.json"), "w",
                encoding="utf-8").write(json.dumps(d))
    caso("2026-09-23_000000_aaaa0001", "2026-09-23T10:00:00-03:00", "8.3",
         None, False, u"Background workers died")
    caso("2026-10-14_000000_aaaa0002", "2026-10-14T11:00:00-03:00", "8.4",
         "b20261012", False, u"Background workers died")
    caso("2026-10-15_000000_aaaa0003", "2026-10-15T09:00:00-03:00", "8.4",
         "b20261012", True)
    c = RG.CasoEmAndamento(uid=UID, origem=u"vigia", modo=u"auto", base=base)
    c.abrir()
    c.etapa(u"montando o FULL e o OAR")
    _mudar_pid_do_andamento(RG, base, c.d["pseudonimo"], 4000002)
    RG.fechar_interrompidos(vivo=lambda p: False, base=base)
    rel = RG.relatorio_de_periodo(base=base)
    f = (rel.get("falhas") or [{}])[0]
    checar(u"a falha por motivo diz a primeira e a ultima data e as versoes",
           f.get("n") == 2 and f.get("primeira") == u"2026-09-23"
           and f.get("ultima") == u"2026-10-14"
           and f.get("versoes") == [u"8.3", u"8.4 (build b20261012)"], str(f))
    tv = (rel.get("travamentos") or {}).get("por_motivo_detalhe") or [{}]
    checar(u"  e o travamento por motivo tambem",
           tv[0].get("n") == 2 and tv[0].get("primeira") == u"2026-09-23"
           and len(tv[0].get("versoes") or []) == 2, str(tv))
    checar(u"o interrompido conta a parte (nem concluido, nem falha)",
           rel.get("interrompidos") == 1 and rel.get("falharam") == 2
           and rel.get("concluidos") == 1,
           "%s %s %s" % (rel.get("interrompidos"), rel.get("falharam"),
                         rel.get("concluidos")))
    li = (rel.get("lista_interrompidos") or [{}])[0]
    checar(u"  com a ultima etapa, a hora, a porta e o modo",
           li.get("ultima_etapa") == u"montando o FULL e o OAR"
           and li.get("porta") == u"vigia" and li.get("modo") == u"auto"
           and len(li.get("hora") or u"") == 5, str(li))
    rec = rel.get("falhas_recentes") or []
    checar(u"os recentes com falha: o mais novo primeiro, com pseudonimo, data, "
           u"versao, porta, modo e motivo",
           len(rec) == 3 and rec[1]["pseudonimo"] == u"aaaa0002"
           and rec[1]["quando"] == u"2026-10-14 11:00"
           and rec[1]["versao"] == u"8.4 (build b20261012)"
           and rec[1]["porta"] == u"vigia" and rec[1]["modo"] == u"auto"
           and u"Background" in rec[1]["motivo"]
           and rec[0]["quando"] > rec[1]["quando"], str(rec)[:300])
    gp = rel.get("gerado_por") or {}
    checar(u"o relatorio guarda a versao e o build que o geraram",
           "app" in gp and "build" in gp, str(gp))
    md, ht = RG.relatorio_markdown(rel), RG.relatorio_html(rel)
    for nome, t in ((u"Markdown", md), (u"HTML", ht)):
        checar(u"  o %s diz quem gerou, as datas e as duas secoes novas" % nome,
               (u"gerado por" in t.lower() or u"gerado pela" in t.lower())
               and u"do app" in t and u"2026-09-23" in t
               and u"Casos interrompidos" in t
               and u"Casos recentes com falha" in t
               and u"8.4 (build b20261012)" in t, t[:200])
        checar(u"  e o %s nao leva identificacao" % nome,
               not [v for v in IDENT if v.lower() in t.lower()])
    try:
        RG.conferir_relatorio(md)
        RG.conferir_relatorio(ht)
        passa = True
    except RG.ContemIdentificacao:
        passa = False
    checar(u"  a trava do relatorio passa o novo formato", passa)
    checar(u"(isca) sem versao gravada, a celula diz «não declarada»",
           RG.rotulo_da_versao(None) == u"não declarada"
           and RG.rotulo_da_versao(u"8.5") == u"8.5")


def main():
    print(u"=" * 70)
    print(u"  O REGISTRO DE CASOS — o que viaja, e o que nunca sai da clinica")
    print(u"=" * 70)
    for t in (teste_o_modulo_e_so_stdlib,
              teste_o_pseudonimo_e_estavel_e_nao_reversivel,
              teste_a_chave_nao_vai_para_pasta_que_sincroniza,
              teste_a_chave_nao_vai_para_a_nuvem_com_a_localappdata_trocada,
              teste_sem_como_conferir_a_chave_fica_na_memoria,
              teste_a_trava_procura_o_VALOR_e_nao_o_padrao,
              teste_o_log_completo_viaja_higienizado,
              teste_o_caso_gravado_nao_carrega_identificacao,
              teste_a_descricao_de_serie_e_recusada_na_entrada,
              teste_a_gravacao_RECUSA_quando_algo_escapa,
              teste_o_perfil_da_estacao_responde_o_que_ele_perguntou,
              teste_as_versoes_entram_sozinhas,
              teste_o_indice_acrescenta,
              teste_o_exportador_confere_antes_de_selar,
              teste_fixture_nao_usa_identificador_plausivel,
              teste_o_tempo_da_serie_vem_de_fora,
              teste_como_a_serie_rodou,
              teste_o_que_o_motor_decidiu_vai_ao_caso,
              teste_a_task_que_falhou_vai_ao_caso_higienizada,
              teste_os_fallbacks_sao_achados,
              teste_o_que_so_se_troca_nao_trava,
              teste_o_caminho_com_espaco_nao_deixa_o_nome,
              teste_as_duas_portas_trocam_as_pastas_pela_mesma_regra,
              teste_a_fase_desliga_a_estatistica_antes_do_cli,
              teste_a_serie_medida_mora_aqui,
              teste_a_espessura_do_lote_chega_ao_caso,
              teste_quem_chama_registrar_serie,
              teste_o_passo_se_le_como_parte,
              teste_a_segunda_tentativa_nao_grava_por_cima,
              teste_o_caso_leva_o_processamento,
              teste_as_funcoes_comuns_do_processamento,
              teste_as_funcoes_comuns_da_trilha_e1,
              teste_a_maquina_das_etapas_entra_por_pseudonimo,
              teste_o_relatorio_de_periodo,
              teste_o_caso_em_andamento_vira_interrompido,
              teste_o_log_da_serie_na_pasta,
              teste_o_relatorio_diz_versao_datas_e_interrompidos,
              teste_a_rodada_nao_grava_chave_na_pasta_padrao):
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
