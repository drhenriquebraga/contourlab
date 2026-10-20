# -*- coding: utf-8 -*-
import io
import os
import re
import sys
import types

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "app"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import _cleanup
_cleanup.adotar_prefixo("radai_moose")

import radai_moose as MZ
import radai_moose_engine as ME
import _componentes

_R = []


def checar(nome, ok, detalhe=""):
    _R.append((nome, bool(ok), detalhe))
    print("  %s  %s%s" % ("OK   " if ok else "FALHA", nome,
                          ("  [%s]" % detalhe) if detalhe else ""))
    return bool(ok)


def secao(t):
    print(u"\n  ── %s ─────────────────────────" % t)


def _class_map_instalado():
    import glob
    c = glob.glob(os.path.join(_componentes.raiz_da_suite(), "_montagem", "**", "totalsegmentator",
                               "map_to_binary.py"), recursive=True)
    if not c:
        return None
    t = io.open(c[0], encoding="utf-8").read()
    blocos = {}
    for mt in re.finditer(r'^\s{4}"([a-z0-9_]+)":\s*\{', t, re.M):
        nome, ini = mt.group(1), mt.end()
        prof, i = 1, ini
        while prof and i < len(t):
            if t[i] == "{":
                prof += 1
            elif t[i] == "}":
                prof -= 1
            i += 1
        blocos[nome] = set(re.findall(r'"([a-z0-9_]+)"', t[ini:i]))
    return blocos


def teste_vocabulario_coerente():
    secao(u"o vocabulário fecha consigo mesmo")

    checar(u"ha exatamente DOIS modelos", len(MZ.MODELOS) == 2,
           ", ".join(sorted(MZ.MODELOS)))

    todos = sorted(set(sum([list(v) for v in MZ.POR_MODELO.values()], [])))
    checar(u"`POR_MODELO` cobre exatamente o `DE_PARA`",
           todos == MZ.estruturas(),
           u"so num deles: %s" % (sorted(set(todos) ^ set(MZ.estruturas())) or "-"))

    checar(u"sao 16 estruturas", len(MZ.estruturas()) == 16,
           str(len(MZ.estruturas())))

    checar(u"13 do cardiaco + 3 da composicao corporal",
           len(MZ.POR_MODELO["cardiac"]) == 13
           and len(MZ.POR_MODELO["body_composition"]) == 3,
           "%d + %d" % (len(MZ.POR_MODELO["cardiac"]),
                        len(MZ.POR_MODELO["body_composition"])))

    checar(u"nenhum nome nosso tem espaco",
           not [n for n in MZ.estruturas() if " " in n],
           str([n for n in MZ.estruturas() if " " in n]))

    checar(u"`normalizar` traduz o rotulo do MOOSE do porta+esplenica",
           MZ.normalizar("portal_splenic_vein") == "portal_vein_and_splenic_vein",
           MZ.normalizar("portal_splenic_vein"))

    checar(u"`normalizar` cai fora pelo fim sem levantar",
           MZ.normalizar("Coisa Nova Do Modelo") == "coisa_nova_do_modelo",
           MZ.normalizar("Coisa Nova Do Modelo"))


def teste_a_conta_do_que_destrava_e_refeita():
    secao(u"o que o MOOSE destrava — REFEITO, nao lido da lista")

    blocos = _class_map_instalado()
    if blocos is None:
        checar(u"o `class_map` da montagem esta ao alcance (PULADO)", True,
               u"sem `_montagem` nesta maquina: a conta nao foi refeita")
        return

    import radai_tasks as T
    no_catalogo = {d["task"] for d in T.CATALOGO}
    alcancavel = set()
    for task in no_catalogo:
        alcancavel |= blocos.get(task, set())

    medido = sorted(n for n in MZ.estruturas() if n not in alcancavel)
    declarado = sorted(MZ.so_do_moose())
    checar(u"`so_do_moose()` bate com a medida contra o catalogo",
           medido == declarado,
           u"medido=%d declarado=%d divergencia=%s"
           % (len(medido), len(declarado), sorted(set(medido) ^ set(declarado)) or "-"))

    checar(u"sao NOVE, e nao dez — o porta+esplenica ja vem da `total`",
           len(medido) == 9 and "portal_vein_and_splenic_vein" not in medido,
           str(len(medido)))

    checar(u"`visceral_fat` nao existe em task nenhuma do TotalSegmentator",
           not [k for k, v in blocos.items() if "visceral_fat" in v],
           str([k for k, v in blocos.items() if "visceral_fat" in v]))

    checar(u"`heartchambers_highres` e `tissue_types` estao FORA do catalogo",
           "heartchambers_highres" not in no_catalogo
           and "tissue_types" not in no_catalogo,
           u"se entrarem, metade do MOOSE vira redundante")


def teste_a_trava_e_de_verdade():
    secao(u"a trava de PERMITIDOS")

    erro = None
    try:
        ME.conferir_rotulos(["heart_myocardium", "tumor_de_alguma_coisa"])
    except ValueError as e:
        erro = str(e)
    checar(u"`conferir_rotulos` LEVANTA em rotulo desconhecido", erro is not None)
    checar(u"e a mensagem NOMEIA o rotulo intruso",
           bool(erro) and "tumor_de_alguma_coisa" in erro)
    checar(u"e explica que a lista e de PERMITIDOS",
           bool(erro) and "PERMITIDOS" in erro)

    ok = True
    try:
        ME.conferir_rotulos(MZ.estruturas())
    except Exception as e:
        ok = False
        erro = "%s: %s" % (type(e).__name__, e)
    checar(u"e NAO levanta nos 16 conferidos", ok, "" if ok else erro)

    fonte = io.open(_componentes.fonte("app/radai_moose_engine.py"),
                    encoding="utf-8").read()
    corpo = fonte[fonte.index("def masks_da_saida"):]
    corpo = corpo[:corpo.index("\ndef ")] if "\ndef " in corpo else corpo
    checar(u"`masks_da_saida` chama a trava", "conferir_rotulos(" in corpo)
    checar(u"e a chama ANTES de montar as mascaras",
           corpo.index("conferir_rotulos(") < corpo.index("for idx, nome in tabela"))


def teste_os_nomes_chegam_inteiros_ao_tps():
    secao(u"os 16 nomes no campo SH de 16 caracteres")

    try:
        import engine as E
    except Exception as e:
        checar(u"`engine` importa nesta bateria (PULADO)", True,
               u"%s — sem SimpleITK no runtime, os nomes nao foram medidos"
               % type(e).__name__)
        return

    E.TG263.update(MZ.TG263_MOOSE)
    usados, saidas = set(), {}
    for n in MZ.estruturas():
        saidas[n] = E.nome_clinico(n, usados, sufixo="_mse")

    longos = {n: f for n, f in saidas.items() if len(f) > 16}
    checar(u"nenhum passa de 16 caracteres", not longos, str(longos))

    sem_sufixo = {n: f for n, f in saidas.items() if not f.endswith("_mse")}
    checar(u"TODOS mantem o `_mse` — a cauda e inviolavel",
           not sem_sufixo, str(sem_sufixo))

    checar(u"os 16 nomes finais sao distintos",
           len(set(saidas.values())) == 16,
           u"%d distintos" % len(set(saidas.values())))

    checar(u"a gordura subcutanea nao trunca no meio da palavra",
           "fat" in saidas["subcutaneous_fat"].lower(),
           saidas["subcutaneous_fat"])
    checar(u"e a visceral tambem nao", "fat" in saidas["visceral_fat"].lower(),
           saidas["visceral_fat"])

    for lado, marca in (("left", "_L"), ("right", "_R")):
        errados = [n for n in MZ.estruturas() if n.endswith("_" + lado)
                   and marca not in saidas[n]]
        checar(u"todo `_%s` mantem o `%s` no nome final" % (lado, marca),
               not errados, str({n: saidas[n] for n in errados}))


def teste_o_palpite_esta_marcado_como_palpite():
    secao(u"o que e palpite esta declarado")

    try:
        import engine as E
    except Exception as e:
        checar(u"`engine` importa (PULADO)", True, type(e).__name__)
        return

    faltam = sorted(n for n in MZ.TG263_MOOSE if n not in E.TG263_A_CONFERIR)
    checar(u"TODA correspondencia TG-263 do MOOSE esta em `TG263_A_CONFERIR`",
           not faltam,
           u"nao marcadas: %s" % (faltam or "-"))

    nao_norma = sorted(MZ.NOME_NOSSO_NAO_E_TG263)
    checar(u"os tres de tecido estao entre os marcados",
           all(n in E.TG263_A_CONFERIR for n in nao_norma),
           str([n for n in nao_norma if n not in E.TG263_A_CONFERIR]))

    checar(u"e eles sao exatamente os do modelo de composicao corporal",
           nao_norma == sorted(MZ.POR_MODELO["body_composition"]))


def teste_os_trainers_sao_de_fabrica():
    secao(u"os trainers — a medida que dispensou o `moosez`")

    candidatos = []
    try:
        with io.open(os.path.join(RAIZ, "_bundle.txt"),
                     encoding="utf-8-sig") as _f:
            _b = _f.read().strip()
        if _b:
            candidatos.append(_b)
    except Exception:
        pass
    candidatos.append(os.path.join(_componentes.raiz_da_suite(), "_montagem", "AUTO_CONTORNO"))
    base = ""
    for c in candidatos:
        p = os.path.join(c, "python", "Lib", "site-packages", "nnunetv2")
        if os.path.isdir(p):
            base = p
            break
    if not base:
        checar(u"o `nnunetv2` da montagem esta ao alcance (PULADO)", True,
               u"sem montagem: os trainers nao foram conferidos")
        return

    fontes = []
    for raiz, _d, arqs in os.walk(base):
        for a in arqs:
            if a.endswith(".py"):
                try:
                    fontes.append(io.open(os.path.join(raiz, a),
                                          encoding="utf-8", errors="replace").read())
                except Exception:
                    pass
    tudo = "\n".join(fontes)

    for chave, d in sorted(MZ.MODELOS.items()):
        classe = d["treinador"].split("__")[0]
        achou = re.search(r"class\s+%s\b" % re.escape(classe), tudo) is not None
        checar(u"o trainer de `%s` e classe de fabrica do nnU-Net" % chave,
               achou, classe)

    proprio = "nnUNetTrainer_2000_epochs_DA5NoMirroring"
    checar(u"e o trainer PROPRIO do MOOSE nao e pedido por nenhum dos dois",
           not [d for d in MZ.MODELOS.values() if proprio in d["treinador"]],
           proprio)


def teste_o_subprocesso_nao_tem_as_armadilhas_conhecidas():
    secao(u"as tres armadilhas que ja custaram uma noite neste projeto")

    s = ME._SCRIPT

    checar(u"`use_mirroring=False` esta escrito no script",
           "use_mirroring=False" in s.replace(" ", ""))

    m = re.search(r"predict_from_files\(\s*\[\[entrada\]\]\s*,\s*(\w+)", s)
    checar(u"a pasta de saida vai como STRING, nao dentro de lista",
           bool(m) and m.group(1) == "saida", m.group(1) if m else "nao achei")

    checar(u"`multiprocessing.freeze_support()` esta no guarda `__main__`",
           "freeze_support()" in s and '__name__ == "__main__"' in s)

    fonte = io.open(_componentes.fonte("app/radai_moose_engine.py"),
                    encoding="utf-8").read()
    corpo = fonte[fonte.index("def rodar("):]
    corpo = corpo[:corpo.index("\ndef ")]
    checar(u"o `stdout` do subprocesso vai para ARQUIVO",
           "stdout=saida" in corpo and "stdout=subprocess.PIPE" not in corpo)
    checar(u"e ha teto de tempo com `kill`",
           "TimeoutExpired" in corpo and "proc.kill()" in corpo)


def teste_o_tamanho_e_o_hash_sao_medidos():
    secao(u"tamanho e hash — medidos, nunca arredondados")

    for chave, d in sorted(MZ.MODELOS.items()):
        n = d["bytes"]
        checar(u"o tamanho de `%s` nao e numero redondo" % chave,
               n % 1000 != 0, "%d bytes" % n)
        checar(u"o sha256 de `%s` tem 64 hex" % chave,
               bool(re.fullmatch(r"[0-9a-f]{64}", d["sha256"])), d["sha256"][:16])
        checar(u"a URL de `%s` e do repositorio do MOOSE" % chave,
               d["url"].startswith("https://github.com/ENHANCE-PET/MOOSE/releases/"),
               d["url"][:60])
        checar(u"e o nome do zip na URL bate com o declarado" % (),
               d["url"].endswith(d["zip"]), d["zip"])

    total = sum(d["bytes"] for d in MZ.MODELOS.values())
    checar(u"os dois somam pouco mais de 1 GB",
           1.0 <= total / float(2 ** 30) <= 1.2,
           "%.2f GB" % (total / float(2 ** 30)))


def teste_sem_peso_ele_nao_estoura():
    secao(u"sem peso na estacao — o estado normal de quem nao baixou")

    vazio = os.path.join(_componentes.raiz_da_suite(), "_montagem", "_nao_existe_de_proposito")

    for chave in sorted(MZ.MODELOS):
        ok, motivo = ME.disponivel(chave, base=vazio)
        checar(u"`disponivel(%s)` devolve (False, motivo) sem levantar" % chave,
               ok is False and bool(motivo), motivo[:60])

    estado = ME.modelos_disponiveis(base=vazio)
    checar(u"`modelos_disponiveis` responde pelos DOIS",
           sorted(estado) == sorted(MZ.MODELOS), str(sorted(estado)))
    checar(u"e o motivo NOMEIA a pasta que faltou",
           all(MZ.MODELOS[k]["pasta"] in m for k, (_o, m) in estado.items()),
           str({k: m[:40] for k, (_o, m) in estado.items()}))

    checar(u"`pasta_do_peso` devolve string vazia, nao levanta",
           ME.pasta_do_peso("cardiac", base=vazio) == "")
    checar(u"`rotulos` devolve {} sem peso",
           ME.rotulos("cardiac", base=vazio) == {})

    erro = None
    try:
        ME._descritor("clin_ct_dental")
    except ValueError as e:
        erro = str(e)
    checar(u"modelo fora dos dois levanta dizendo quais existem",
           bool(erro) and "cardiac" in erro and "body_composition" in erro,
           (erro or "")[:70])


def teste_um_falha_e_o_outro_sai():
    secao(u"um modelo cai, o outro entrega")

    reais = {k: sys.modules.get(k) for k in ("SimpleITK", "engine")}
    guarda = (ME.modelos_disponiveis, ME.rodar, ME.masks_da_saida)
    linhas = []
    try:
        sitk = types.ModuleType("SimpleITK")
        sitk.WriteImage = lambda *a, **k: None
        sitk.ReadImage = lambda *a, **k: None
        sys.modules["SimpleITK"] = sitk

        class _Img(object):
            def GetSize(self):
                return (4, 4, 3)

        eng = types.ModuleType("engine")
        eng.load_sitk = lambda *a, **k: _Img()
        sys.modules["engine"] = eng

        ME.modelos_disponiveis = lambda base=None: {
            "cardiac": (True, ""), "body_composition": (True, "")}

        def _rodar(modelo, *a, **k):
            if modelo == "cardiac":
                return False, "explodiu de proposito"
            return True, ""

        ME.rodar = _rodar
        ME.masks_da_saida = lambda modelo, *a, **k: {
            "skeletal_muscle": True, "subcutaneous_fat": True,
            "visceral_fat": True}

        fora = ME.contornar("qualquer", log=linhas.append)
    finally:
        ME.modelos_disponiveis, ME.rodar, ME.masks_da_saida = guarda
        for k, v in reais.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v

    checar(u"o modelo que funcionou entregou as estruturas dele",
           sorted(fora) == sorted(MZ.POR_MODELO["body_composition"]),
           str(sorted(fora)))
    texto = "\n".join(linhas)
    checar(u"o log NOMEIA o modelo que caiu",
           "cardiac" in texto and "FALHOU" in texto)
    checar(u"e diz que o resto do conjunto saiu assim mesmo",
           "assim mesmo" in texto)
    checar(u"e `contornar` NAO levantou", True)


def teste_sem_nenhum_peso_devolve_vazio():
    secao(u"nenhum dos dois na estacao")

    guarda = ME.modelos_disponiveis
    linhas = []
    try:
        ME.modelos_disponiveis = lambda base=None: {
            "cardiac": (False, "nao esta aqui"),
            "body_composition": (False, "nao esta aqui")}
        fora = ME.contornar("qualquer", log=linhas.append)
    finally:
        ME.modelos_disponiveis = guarda

    checar(u"devolve {} — nao e erro, e o estado de quem nao baixou",
           fora == {}, str(fora))
    checar(u"e o log DIZ que o conjunto nao sai",
           "nao sai" in "\n".join(linhas))


def teste_o_registro_declara_o_que_e():
    secao(u"o registro do acervo")

    try:
        import radai_models as V
    except Exception as e:
        checar(u"`radai_models` importa (PULADO)", True, type(e).__name__)
        return

    m = V.MODELOS.get("moose")
    if not checar(u"o MOOSE esta no acervo de modelos", m is not None):
        return

    checar(u"e declarado como uso LIVRE", m.get("uso_permitido") == "livre",
           str(m.get("uso_permitido")))
    lic = (m.get("licenca") or "")
    checar(u"a licenca do PESO aparece na letra", "CC BY 4.0" in lic, lic[:70])
    checar(u"e o codigo (Apache-2.0) e citado como coisa separada",
           "Apache" in lic, lic[:70])

    notice = io.open(os.path.join(_componentes.raiz_da_suite(), "NOTICE"), encoding="utf-8").read()
    checar(u"o NOTICE atribui o MOOSE — atribuicao e CONDICAO da CC BY 4.0",
           "MOOSE" in notice and "CC BY 4.0" in notice)
    checar(u"e nomeia o grupo autor (ENHANCE.PET)", "ENHANCE" in notice)


def teste_o_conjunto_existe_e_e_proprio():
    secao(u"o conjunto de RTSTRUCT")

    try:
        import radai_sets as S
    except Exception as e:
        checar(u"`radai_sets` importa (PULADO)", True, type(e).__name__)
        return

    d = S.POR_COD.get("mse")
    if not checar(u"o conjunto `mse` existe no registro", d is not None):
        return

    checar(u"o sufixo e `_mse`", d.get("sufixo") == "_mse", str(d.get("sufixo")))
    checar(u"o infixo do arquivo e `MSE_`", d.get("infixo") == "MSE_",
           str(d.get("infixo")))
    checar(u"e ele NAO e o entregue", d.get("entregue") is False)

    de_motor = [c.get("sufixo") for c in S.CONJUNTOS if c.get("sufixo") != "_ai"]
    checar(u"nenhum sufixo de MOTOR se repete",
           len(de_motor) == len(set(de_motor)), str(de_motor))
    checar(u"e o `_ai` e usado so pelos dois conjuntos NOSSOS",
           sorted(c["cod"] for c in S.CONJUNTOS if c.get("sufixo") == "_ai")
           == ["full", "oar"],
           str(sorted(c["cod"] for c in S.CONJUNTOS if c.get("sufixo") == "_ai")))
    checar(u"o `_mse` e de um conjunto so",
           len([c for c in S.CONJUNTOS if c.get("sufixo") == "_mse"]) == 1)
    infixos = [c.get("infixo") for c in S.CONJUNTOS if c.get("infixo")]
    checar(u"nenhum infixo se repete", len(infixos) == len(set(infixos)),
           str(infixos))


def teste_aparece_para_quem_escolhe():
    secao(u"a tela de plugins")

    try:
        import radai_modes as M
    except Exception as e:
        checar(u"`radai_modes` importa (PULADO)", True, type(e).__name__)
        return

    texto = io.open(_componentes.fonte("app/radai_modes.py"),
                    encoding="utf-8").read()
    checar(u"o MOOSE e citado na tela de modos/plugins",
           "moose" in texto.lower())

    suspeitas = [n for n in MZ.estruturas()
                 if re.search(r"tumor|lesion|cancer|nodule|cyst|metasta", n)]
    checar(u"nenhuma das 16 e classe de achado", not suspeitas, str(suspeitas))


def teste_a_procedencia_tem_frase():
    secao(u"o campo que diz de qual motor veio o contorno")

    fonte = io.open(_componentes.fonte("app/engine.py"),
                    encoding="utf-8").read()
    bloco = fonte[fonte.index("ROTULO_MOTOR = {"):]
    bloco = bloco[:bloco.index("}") + 1]

    checar(u"`moose` tem frase de procedencia", '"moose"' in bloco)
    checar(u"e ela nomeia o autor (ENHANCE.PET) — CC BY 4.0 exige credito",
           "ENHANCE" in bloco)

    saida = io.open(_componentes.fonte("app/radai_output.py"),
                    encoding="utf-8").read()
    origens = sorted(set(re.findall(
        r'self\.conjunto\(\s*"[a-z]+"\s*,\s*[a-z_]+\s*,\s*"([a-z]+)"', saida)))
    checar(u"achei as origens que `radai_output` passa", len(origens) >= 5,
           ", ".join(origens))
    sem = [o for o in origens if ('"%s"' % o) not in bloco]
    checar(u"TODA origem gravada por `radai_output` tem frase",
           not sem, u"sem frase: %s — gravariam a sigla crua" % (sem or "-"))

    # GUARDA: os motores do FULL gravam a origem por `extras['origem']`, e
    # nao por `self.conjunto(...)`; a lista de cima nao os enxerga.
    import radai_modes
    import radai_motores_full
    do_full = sorted(set(radai_motores_full.CODIGOS)
                     | set(radai_modes.MOTORES_NO_FULL))
    sem_full = [o for o in do_full if ('"%s"' % o) not in bloco]
    checar(u"todo motor do FULL (`radai_motores_full.CODIGOS`) tem frase",
           do_full and not sem_full,
           u"sem frase: %s — gravariam a sigla crua" % (sem_full or "-"))
    isca = bloco.replace('"cranio_ct"', '"cranio_xx"')
    checar(u"  ISCA: sem a frase do cranio_ct, a checagem reprova",
           any(('"%s"' % o) not in isca for o in do_full))


def teste_dois_zips_convergem():
    secao(u"dois pesos: a marca de instalado converge")
    import tempfile as _tf
    import shutil as _sh
    import zipfile as _zf
    from pathlib import Path as _P
    try:
        import radai_models as V
    except Exception as e:
        checar(u"`radai_models` importa (PULADO)", True, type(e).__name__)
        return

    d = _tf.mkdtemp(prefix="radai_moose_ex_")
    try:
        with _zf.ZipFile(os.path.join(d, "um.zip"), "w") as f:
            f.writestr("Dataset999/plans.json", "{}")
        V._extrair_se_preciso("x", {"extrair": "um.zip"}, _P(d))
        checar(u"UM zip: extrai, apaga o zip e marca",
               os.path.isfile(os.path.join(d, "pesos_extraidos.txt"))
               and not os.path.isfile(os.path.join(d, "um.zip"))
               and os.path.isdir(os.path.join(d, "Dataset999")))
    finally:
        _sh.rmtree(d, ignore_errors=True)

    d = _tf.mkdtemp(prefix="radai_moose_ex_")
    try:
        m = {"extrair": ("a.zip", "b.zip")}
        with _zf.ZipFile(os.path.join(d, "a.zip"), "w") as f:
            f.writestr("A/plans.json", "{}")
        V._extrair_se_preciso("x", m, _P(d))
        checar(u"com METADE, a marca global NAO sai",
               not os.path.isfile(os.path.join(d, "pesos_extraidos.txt")),
               u"senao o modelo se declara pronto com metade dos pesos")
        checar(u"mas o que chegou ja foi extraido",
               os.path.isdir(os.path.join(d, "A")))

        with _zf.ZipFile(os.path.join(d, "b.zip"), "w") as f:
            f.writestr("B/plans.json", "{}")
        V._extrair_se_preciso("x", m, _P(d))
        checar(u"com os DOIS, a marca sai",
               os.path.isfile(os.path.join(d, "pesos_extraidos.txt")),
               u"o primeiro zip ja tinha sido apagado — quem o conta e a "
               u"marca por zip, e nao a presenca do arquivo")
        checar(u"e as duas pastas estao no disco",
               os.path.isdir(os.path.join(d, "A"))
               and os.path.isdir(os.path.join(d, "B")))

        antes = io.open(os.path.join(d, "pesos_extraidos.txt"),
                        encoding="utf-8").read()
        V._extrair_se_preciso("x", m, _P(d))
        depois = io.open(os.path.join(d, "pesos_extraidos.txt"),
                         encoding="utf-8").read()
        checar(u"e a terceira passada nao faz nada (idempotente)",
               antes == depois)
    finally:
        _sh.rmtree(d, ignore_errors=True)


def main():
    print("=" * 70)
    print(u"  MOOSE — o que destrava, a trava, e o que nao se inventou")
    print("=" * 70)
    for t in (teste_vocabulario_coerente,
              teste_a_conta_do_que_destrava_e_refeita,
              teste_a_trava_e_de_verdade,
              teste_os_nomes_chegam_inteiros_ao_tps,
              teste_o_palpite_esta_marcado_como_palpite,
              teste_os_trainers_sao_de_fabrica,
              teste_o_subprocesso_nao_tem_as_armadilhas_conhecidas,
              teste_o_tamanho_e_o_hash_sao_medidos,
              teste_sem_peso_ele_nao_estoura,
              teste_um_falha_e_o_outro_sai,
              teste_sem_nenhum_peso_devolve_vazio,
              teste_o_registro_declara_o_que_e,
              teste_o_conjunto_existe_e_e_proprio,
              teste_aparece_para_quem_escolhe,
              teste_a_procedencia_tem_frase,
              teste_dois_zips_convergem):
        try:
            t()
        except Exception as e:
            import traceback
            checar(u"%s (excecao)" % t.__name__, False,
                   "%s: %s" % (type(e).__name__, e))
            traceback.print_exc()
    falhas = [(n, d) for n, ok, d in _R if not ok]
    print("\n" + "=" * 70)
    if falhas:
        print(u"FALHOU: %d de %d checagens" % (len(falhas), len(_R)))
        for n, d in falhas:
            print(u"  - %s%s" % (n, ("  [%s]" % d) if d else ""))
    else:
        print(u"OK: %d checagens, todas passaram" % len(_R))
    print("=" * 70)
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
