# -*- coding: utf-8 -*-
import io
import json
import os
import socket
import subprocess
import sys
import time

AQUI = os.path.dirname(os.path.abspath(__file__))

BIBLIOTECAS = [
    ("torch", u"a rede neural roda sobre ele", True),
    ("numpy", u"toda conta de imagem", True),
    ("pydicom", u"ler e escrever DICOM", True),
    ("SimpleITK", u"carregar a série e reamostrar", True),
    ("nibabel", u"o formato que o TotalSegmentator devolve", True),
    ("scipy", u"o pós-processamento das máscaras", True),
    ("rt_utils", u"montar o RTSTRUCT", True),
    ("fastapi", u"o servidor do painel", True),
    ("uvicorn", u"idem", True),
    ("totalsegmentator", u"o motor principal", True),
    ("nnunetv2", u"a rede do TotalSegmentator", True),
    ("pkg_resources", u"o TotalSegmentator ainda o importa "
                      u"(por isso setuptools<81)", True),
    ("pylibjpeg", u"DICOM comprimido em JPEG sem perdas", False),
    ("PIL", u"opcional: as prévias saem sem ele", False),
]


DISTRIBUICAO = {"totalsegmentator": "TotalSegmentator", "rt_utils": "rt-utils",
                "pkg_resources": "setuptools", "PIL": "Pillow"}


def _versao(nome, mod=None):
    try:
        from importlib import metadata
        v = metadata.version(DISTRIBUICAO.get(nome, nome))
        if v:
            return str(v)
    except Exception:
        pass
    for a in ("__version__", "VERSION", "version"):
        v = getattr(mod, a, None)
        if isinstance(v, str) and v:
            return v
        if v is not None and not callable(v):
            return str(v)
    return u""


def _item(nome, ok, valor=u"", detalhe=u"", grave=True, nota=False):
    return {"nome": nome, "ok": ok, "valor": valor,
            "detalhe": detalhe, "grave": bool(grave), "nota": bool(nota)}


def _secao_identidade():
    itens = []
    ent = {}
    for cand in (os.path.join(AQUI, "..", "entrega.txt"),
                 os.path.join(AQUI, "entrega.txt")):
        if os.path.isfile(cand):
            try:
                for linha in io.open(cand, encoding="utf-8-sig",
                                     errors="ignore").read().splitlines():
                    if "=" in linha and not linha.strip().startswith("#"):
                        k, v = linha.split("=", 1)
                        ent[k.strip()] = v.strip()
            except Exception:
                pass
            break
    itens.append(_item(u"Produto", bool(ent.get("PROJETO")),
                       ent.get("PROJETO", u"—")))
    itens.append(_item(u"Versão", bool(ent.get("VERSAO")),
                       ent.get("VERSAO", u"—")))
    itens.append(_item(u"Build", bool(ent.get("BUILD")),
                       ent.get("BUILD", u"não carimbado"),
                       u"sem ele o suporte não sabe qual publicação é esta",
                       grave=False))
    itens.append(_item(u"Máquina", True, socket.gethostname()))
    itens.append(_item(u"Python", True, u"%d.%d.%d"
                       % sys.version_info[:3]))
    itens.append(_item(u"Interpretador", True, sys.executable))
    return {"titulo": u"Identidade", "itens": itens}


def _secao_bibliotecas():
    itens = []
    import warnings
    for nome, para_que, obrigatoria in BIBLIOTECAS:
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                mod = __import__(nome)
        except Exception as e:
            itens.append(_item(nome, False,
                               u"não importa",
                               u"%s — %s" % (para_que,
                                             str(e)[:110]),
                               grave=obrigatoria))
            continue
        versao = _versao(nome, mod)
        if versao:
            itens.append(_item(nome, True, versao, para_que,
                               grave=obrigatoria))
        else:
            itens.append(_item(nome, None, u"versão desconhecida",
                               u"%s — importa, mas o pacote instalado não "
                               u"declara versão" % para_que,
                               grave=obrigatoria))
    return {"titulo": u"Bibliotecas", "itens": itens}


def _secao_gpu():
    itens = []
    try:
        import radai_arranque as RA
    except Exception as e:
        return {"titulo": u"GPU",
                "itens": [_item(u"torch", None, u"não consegui medir",
                                str(e)[:110], grave=False)]}
    tr = RA.torch_da_estacao(sys.executable, timeout=60)
    if tr.get("falha"):
        return {"titulo": u"GPU",
                "itens": [_item(u"torch", None, u"não consegui medir",
                                str(tr.get("falha"))[:110], grave=False)]}
    if not tr.get("importa"):
        return {"titulo": u"GPU",
                "itens": [_item(u"torch", False, u"não importa",
                                str(tr.get("erro") or u"")[:110])]}
    tem = bool(tr.get("disponivel"))
    itens.append(_item(u"CUDA disponível", tem,
                       u"sim" if tem else u"não",
                       u"sem GPU a série de planejamento leva horas"))
    itens.append(_item(u"CUDA do torch", True, str(tr.get("cuda") or u"—"),
                       grave=False))
    pl = RA.placas(timeout=15)
    for p in pl.get("placas") or []:
        itens.append(_item(u"Placa %d" % p["indice"], True,
                           u"%s, %.1f GB" % (p["nome"],
                                             (p.get("total_mb") or 0) / 1024.0)))
    if tem and not pl.get("placas"):
        for i, p in enumerate(tr.get("placas") or []):
            itens.append(_item(u"Placa %d" % i, True,
                               u"%s, %.1f GB" % (p.get("nome"),
                                                 (p.get("total_mb") or 0) / 1024.0)))
    itens.extend(_itens_das_outras_placas())
    return {"titulo": u"GPU", "itens": itens}


def _itens_das_outras_placas():
    fora = []
    try:
        import radai_devices as RD
    except Exception as e:
        return [_item(u"Outras placas", None, u"não consegui medir",
                      str(e)[:110], grave=False)]
    for p in RD.placas_rapidas():
        if p.get("vendor") in ("nvidia",):
            continue
        fora.append(_item(u"Placa de vídeo", None,
                          u"%s%s" % (p.get("nome") or u"?",
                                     (u", %d MiB%s" % (p["memoria_mb"],
                                                       u" compartilhada"
                                                       if p.get("integrada")
                                                       else u""))
                                     if p.get("memoria_mb") else u""),
                          RD.frase_na_tela(p.get("vendor")), grave=False))
    conf = RD.conferencia_atual()
    if conf is None:
        fora.append(_item(u"Backends conferidos pelo canário", None,
                          u"o arranque ainda não mediu",
                          u"o diagnóstico de computação roda no arranque do "
                          u"vigia: a tela já responde, e a fila só começa "
                          u"depois dele", grave=False))
        return fora
    fora.append(_item(u"Backends conferidos pelo canário", True,
                      u", ".join(conf["conferidos"]),
                      u"a fila ainda decide placa ou CPU pela VRAM, como desde "
                      u"a v8; esta é a lista que ela vai usar quando despachar "
                      u"por backend", grave=False))
    for f in conf["fora"]:
        if f.get("politica") != "producao":
            continue
        fora.append(_item(_NOME_NO_CANARIO.get(f["backend"],
                                               u"Canário de backend"),
                          None,
                          u"reprovada no canário" if f["estado"] == "reprovado"
                          else u"não conferida (DEVICE=cpu)"
                          if f["estado"] == "device_cpu"
                          else u"não conferida",
                          f.get("motivo") or u"", grave=False))
    return fora


_NOME_NO_CANARIO = {"cuda": u"CUDA no canário"}


def _tamanho(caminho):
    if os.path.isfile(caminho):
        try:
            return os.path.getsize(caminho)
        except Exception:
            return 0
    total = 0
    for raiz, _d, arqs in os.walk(caminho):
        for a in arqs:
            try:
                total += os.path.getsize(os.path.join(raiz, a))
            except Exception:
                pass
    return total


def _gb(n):
    return u"%.2f GB" % (n / 1e9) if n >= 1e8 else u"%.1f MB" % (n / 1e6)


def _secao_pesos():
    prog = os.path.dirname(AQUI) if os.path.isdir(
        os.path.join(os.path.dirname(AQUI), "modelos")) else AQUI
    itens = []
    ALVOS = [(u"TotalSegmentator", os.path.join(prog, "ts_weights"), 1e9, True)]
    PISO = {"nv_segment_ct": 5e8, "cads_open": 1e7, "moose": 1e8, "hnlnl": 1e6}
    ROTULO = {"nv_segment_ct": u"NV-Segment-CT", "cads_open": u"CADS",
              "moose": u"MOOSE", "hnlnl": u"Níveis cervicais"}
    try:
        import radai_models as RM
        for ident in RM.MODELOS:
            if ident == "totalsegmentator":
                continue
            ALVOS.append((ROTULO.get(ident, ident),
                          str(RM.pasta_do_modelo(ident)),
                          PISO.get(ident, 1e6), False))
    except Exception as e:
        itens.append(_item(u"modelos de comparação", None,
                           u"não consegui medir", str(e)[:110], grave=False))
    for nome, caminho, minimo, obrigatorio in ALVOS:
        n = _tamanho(caminho)
        if not n:
            itens.append(_item(nome, False, u"ausente",
                               u"procurei em %s" % caminho,
                               grave=obrigatorio))
            continue
        itens.append(_item(nome, n >= minimo, _gb(n),
                           u"" if n >= minimo
                           else u"menor que o esperado (%s): download "
                                u"interrompido?" % _gb(minimo),
                           grave=obrigatorio))
    return {"titulo": u"Modelos e pesos", "itens": itens}


def _secao_estrutura():
    prog = os.path.dirname(AQUI) if os.path.isfile(
        os.path.join(os.path.dirname(AQUI), "radai_watcher.py")) else AQUI
    itens = []
    acima = os.path.dirname(prog)
    ESSENCIAIS = [
        ("radai_watcher.py", [prog], True),
        ("engine.py", [prog], True),
        ("radai_geom.py", [prog], True),
        ("radai_panel.py", [prog], True),
        ("RADIOTERAPIA_AI_LOCAL_SUITE.cmd", [prog], True),
        ((os.path.join("launchers", "start_watcher.cmd"),
          os.path.join("ferramentas", "start_watcher.cmd")), [prog], True),
        ((os.path.join("launchers", "open_browser.cmd"),
          os.path.join("ferramentas", "open_browser.cmd")), [prog], True),
        ((os.path.join("maintenance", "UNINSTALL.cmd"),
          os.path.join("ferramentas", "UNINSTALL.cmd")),
         [prog, os.path.join(acima, "installer")], False),
        ("LICENSE", [prog, acima], True),
        ("NOTICE", [prog, acima], True),
    ]
    for rel, ondes, obrig in ESSENCIAIS:
        rels = (rel,) if isinstance(rel, str) else tuple(rel)
        folha = os.path.basename(rels[0])
        achado = u""
        for onde in ondes:
            cands = [os.path.join(onde, r) for r in rels]
            cands.append(os.path.join(onde, folha))
            for cand in cands:
                if os.path.isfile(cand):
                    achado = cand
                    break
            if achado:
                break
        itens.append(_item(rels[0].replace("\\", "/"), bool(achado),
                           u"" if achado else u"ausente",
                           u"" if achado
                           else u"procurei em %s" % u" e ".join(ondes),
                           grave=obrig))
    return {"titulo": u"Arquivos do programa", "itens": itens}


def _secao_travas():
    prog = os.path.dirname(AQUI) if os.path.isfile(
        os.path.join(os.path.dirname(AQUI), "engine.py")) else AQUI
    TRAVAS = [
        (u"TotalSegmentator", "engine.py", ("conferir_tasks",),
         u"só roda task que está em TASKS_PERMITIDAS"),
        (u"NV-Segment-CT", "radai_nv_engine.py", ("conferir_classes",),
         u"só aceita classe da lista; achado fica fora do prompt da entrega"),
        (u"Níveis cervicais (índices)", "radai_hnlnl_engine.py",
         ("conferir_niveis",),
         u"guarda o espaço de saída do modelo — peso trocado não passa"),
        (u"Níveis cervicais (nomes)", "radai_hnlnl.py", ("conferir_saida",),
         u"guarda os nomes que vão para o RTSTRUCT"),
        (u"Vocabulário do laudo (o que se DIZ)", "radai_plausibility.py",
         ("conferir_ancoragem", "conferir_motivo"),
         u"só julga o que um motor já desenhou, e a frase sai de um "
         u"dicionário fechado"),
    ]
    fontes = {}
    try:
        for nome_arq in sorted(os.listdir(prog)):
            if not nome_arq.endswith(".py"):
                continue
            try:
                fontes[nome_arq] = io.open(os.path.join(prog, nome_arq),
                                           encoding="utf-8",
                                           errors="replace").read()
            except Exception:
                continue
    except Exception:
        pass

    itens = []
    for rotulo, arq, funcoes, o_que in TRAVAS:
        p = os.path.join(prog, arq)
        if not os.path.isfile(p):
            itens.append(_item(rotulo, False, u"arquivo ausente", arq))
            continue
        txt = fontes.get(arq)
        if txt is None:
            try:
                txt = io.open(p, encoding="utf-8", errors="replace").read()
            except Exception as e:
                itens.append(_item(rotulo, None, u"não consegui ler",
                                   str(e)[:90]))
                continue
        faltando = []
        mudas = []
        chamada_em = []
        for funcao in funcoes:
            if ("def %s(" % funcao) not in txt:
                faltando.append(funcao)
                continue
            onde = []
            for nome_arq, t2 in fontes.items():
                n = t2.count("%s(" % funcao) - (1 if nome_arq == arq else 0)
                if n > 0:
                    onde.append(nome_arq)
            if onde:
                for nome_arq in onde:
                    if nome_arq not in chamada_em:
                        chamada_em.append(nome_arq)
            else:
                mudas.append(funcao)
        assinaturas = u", ".join(u"%s()" % f for f in funcoes)
        if not fontes and not faltando:
            itens.append(_item(rotulo, None, u"não consegui varrer a pasta",
                               u"%s · %s · quem chama não pôde ser respondido"
                               % (arq, assinaturas), grave=False))
            continue
        viva = not faltando and not mudas
        itens.append(_item(rotulo, viva,
                           u"presente e chamada" if viva
                           else (u"definida mas NÃO chamada" if not faltando
                                 else u"AUSENTE"),
                           u"%s · %s%s · %s"
                           % (arq, assinaturas,
                              (u" — chamada de %s"
                               % u", ".join(sorted(chamada_em)[:2]))
                              if chamada_em else u"", o_que)))

    itens.append(_item(
        u"O que esta conferência mede",
        None,
        u"presença e chamada — não execução",
        u"ela lê o código e responde «a trava está no posto?». Não responde "
        u"«a trava barrou alguém?»: quem executa cada uma com entrada "
        u"inválida são tools/test_engine.py, test_hnlnl.py e "
        u"test_plausibility.py, na bateria do repositório.",
        grave=False, nota=True))
    return {"titulo": u"Travas clínicas — o que cada motor pode rodar, "
                      u"e o que o programa pode dizer",
            "itens": itens}


def _secao_configuracao(cfg=None, root=u"", porta=0):
    itens = []
    root = (root or u"").strip()
    if not root:
        itens.append(_item(u"Pasta dos exames (ROOT)", None, u"vazia",
                           u"de propósito: sem ela o programa sobe o painel "
                           u"e não toca em nada", grave=False))
    else:
        existe = os.path.isdir(root)
        le = False
        escreve = False
        if existe:
            try:
                os.listdir(root)
                le = True
            except Exception:
                le = False
            marca = os.path.join(root, "_radai_teste_escrita.tmp")
            try:
                with io.open(marca, "w", encoding="utf-8") as f:
                    f.write(u"ok")
                escreve = True
            except Exception:
                escreve = False
            finally:
                try:
                    os.remove(marca)
                except Exception:
                    pass
        itens.append(_item(u"Pasta dos exames (ROOT)", existe and le and escreve,
                           root,
                           u"existe=%s lê=%s escreve=%s"
                           % (u"sim" if existe else u"NÃO",
                              u"sim" if le else u"NÃO",
                              u"sim" if escreve else u"NÃO")
                           + (u" — o RTSTRUCT é gravado AO LADO da série"
                              if not escreve else u"")))
    if porta:
        s = socket.socket()
        livre = False
        try:
            s.bind(("127.0.0.1", int(porta)))
            livre = True
        except Exception:
            livre = False
        finally:
            try:
                s.close()
            except Exception:
                pass
        itens.append(_item(u"Porta do painel", True, str(porta),
                           u"em uso por este programa" if not livre
                           else u"livre", grave=False))
    return {"titulo": u"Configuração", "itens": itens}


def conferir(root=u"", porta=0):
    t0 = time.time()
    secoes = []
    for fn, args in ((_secao_identidade, ()),
                     (_secao_estrutura, ()),
                     (_secao_bibliotecas, ()),
                     (_secao_gpu, ()),
                     (_secao_pesos, ()),
                     (_secao_travas, ()),
                     (_secao_configuracao, (None, root, porta))):
        try:
            secoes.append(fn(*args))
        except Exception as e:
            secoes.append({"titulo": getattr(fn, "__name__", u"?"),
                           "itens": [_item(u"a conferência falhou aqui",
                                           False, u"%s" % type(e).__name__,
                                           str(e)[:160])]})
    ok = faltam = avisos = 0
    for s in secoes:
        for i in s["itens"]:
            if i["ok"] is True:
                ok += 1
            elif i["ok"] is False and i["grave"]:
                faltam += 1
            else:
                avisos += 1
    return {"secoes": secoes,
            "resumo": {"ok": ok, "faltam": faltam, "avisos": avisos},
            "segundos": round(time.time() - t0, 1)}


def texto(rel):
    linhas = [u"CONFERENCIA DA ESTACAO — Radioterapia.AI Local Suite",
              u"=" * 62, u""]
    for s in rel.get("secoes", []):
        linhas.append(s["titulo"])
        linhas.append(u"-" * len(s["titulo"]))
        for i in s["itens"]:
            marca = u"[ok]  " if i["ok"] is True else (
                u"[FALTA]" if (i["ok"] is False and i["grave"])
                else u"[  ?  ]")
            linhas.append(u"  %-7s %-34s %s"
                          % (marca, i["nome"], i["valor"]))
            if i["detalhe"]:
                linhas.append(u"          %s" % i["detalhe"])
        linhas.append(u"")
    r = rel.get("resumo", {})
    linhas.append(u"%d ok · %d faltando · %d avisos · %s s"
                  % (r.get("ok", 0), r.get("faltam", 0), r.get("avisos", 0),
                     rel.get("segundos", 0)))
    return u"\n".join(linhas)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    _r = conferir()
    if "--json" in sys.argv:
        print(json.dumps(_r, ensure_ascii=False, indent=1))
    else:
        print(texto(_r))
    sys.exit(1 if _r["resumo"]["faltam"] else 0)
