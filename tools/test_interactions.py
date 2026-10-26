# -*- coding: utf-8 -*-
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _cleanup
import _componentes
_cleanup.adotar_prefixo('radai_inter_')

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(RAIZ, "app")
sys.path.insert(0, APP)

_ok = 0
_falhou = 0
_falhas = []
PORTA = 0


def secao(t):
    print(u"")
    print(u"\u2500\u2500 %s %s" % (t, u"\u2500" * max(0, 60 - len(t))))


def checar(rotulo, cond, detalhe=u""):
    global _ok, _falhou
    if cond:
        _ok += 1
        print(u"  OK     %s" % rotulo)
    else:
        _falhou += 1
        _falhas.append(rotulo)
        print(u"  FALHA  %s  %s" % (rotulo, str(detalhe).replace("\n", " | ")[:160]))


def _url(caminho):
    return "http://127.0.0.1:%d%s" % (PORTA, caminho)


def pegar(caminho, timeout=20, dados=None, tipo=None, metodo=None,
          cabecalhos=None):
    req = urllib.request.Request(_url(caminho), data=dados, method=metodo)
    if tipo:
        req.add_header("Content-Type", tipo)
    for k, v in (cabecalhos or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.getcode(), r.read().decode("utf-8", "replace"), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace"), dict(e.headers or {})
    except Exception as e:
        return 0, u"%s: %s" % (type(e).__name__, e), {}


def postar(caminho, obj, timeout=30):
    dados = json.dumps(obj).encode("utf-8")
    return pegar(caminho, timeout=timeout, dados=dados,
                 tipo="application/json", metodo="POST")


def json_de(corpo):
    try:
        return json.loads(corpo)
    except Exception:
        return None


def varrer_lote(pasta, prazo=90.0):
    cod, corpo, _ = postar("/api/varrer/iniciar",
                           {"uso": "lote", "pasta": pasta, "dias": 0})
    j = json_de(corpo) or {}
    fim = time.time() + prazo
    while cod == 200 and j.get("v") and not j.get("fim") and time.time() < fim:
        time.sleep(0.3)
        cod, corpo, _ = postar("/api/varrer/estado", {"v": j["v"]})
        j = json_de(corpo) or {}
    fora = dict(j.get("extra") or {})
    fora.update(series=list(j.get("linhas") or []), erro=j.get("erro"),
                fim=j.get("fim"))
    return cod, fora


def perfil_primeiro_dia():
    secao(u"1. PRIMEIRO DIA: abrir, aceitar, navegar, voltar")

    cod, corpo, _ = pegar("/")
    checar(u"a porta abre", cod == 200, cod)
    checar(u"e sem aceite ela leva ao portão",
           "aceite" in corpo.lower() or "aceit" in corpo.lower(),
           corpo[:120])

    for rota in ("/vigia", "/lote", "/bridge", "/recon3d", "/nidus",
                 "/elastic", "/bolus", "/config"):
        cod, corpo, _ = pegar(rota)
        checar(u"  %s tambem passa pelo portao" % rota,
               cod == 200 and ("aceit" in corpo.lower()), cod)

    for rota in ("/termos", "/politica-privacidade", "/creditos",
                 "/radai-idiomas.js"):
        cod, _c, _ = pegar(rota)
        checar(u"  %s passa sem aceite" % rota, cod == 200, cod)

    cod, corpo, _ = pegar("/api/aceite")
    j = json_de(corpo) or {}
    pontos = [p.get("chave") for p in (j.get("pontos") or [])]
    checar(u"a tela do aceite declara os pontos", len(pontos) >= 3,
           corpo[:160])

    if pontos:
        cod, corpo, _ = postar("/api/aceite",
                               {"quem": "", "itens": pontos[:-1]})
        jj = json_de(corpo) or {}
        checar(u"aceite PARCIAL e' recusado", bool(jj.get("erro")),
               corpo[:160])

    cod, corpo, _ = postar("/api/aceite", {"quem": "", "itens": pontos})
    j = json_de(corpo) or {}
    checar(u"o aceite completo e' registrado",
           cod == 200 and not j.get("erro"), corpo[:160])

    cod, corpo, _ = pegar("/")
    checar(u"e agora a porta mostra os modulos",
           cod == 200 and "radai-menu" in corpo, cod)

    for rota in ("/autocontorno", "/vigia", "/bridge", "/nidus", "/config"):
        cod, corpo, _ = pegar(rota)
        tem_marca = 'class="rc-nome"' in corpo
        checar(u"  %s tem a marca certa" % rota, cod == 200 and tem_marca, cod)
    cod, corpo, _ = pegar("/vigia")
    checar(u"e a ferramenta tem como VOLTAR",
           'class="ui-volta"' in corpo,
           u"o unico caminho de volta dentro da suite")


def perfil_rotina(root, vazia, so_lixo, curta):
    secao(u"2. ROTINA: apontar pasta e entender a resposta")

    cod, j = varrer_lote(root)
    checar(u"a pasta com exames devolve series (a varredura da tela)",
           cod == 200 and len(j.get("series") or []) >= 1, str(j)[:200])

    cod, j = varrer_lote(vazia)
    checar(u"pasta vazia: zero series, sem erro",
           cod == 200 and j.get("fim") and not j.get("erro")
           and not (j.get("series") or []), str(j)[:200])
    checar(u"  e sem descartadas (nao ha o que descartar)",
           not (j.get("curtas") or []), j.get("curtas"))

    cod, j = varrer_lote(so_lixo)
    checar(u"pasta so com lixo binario: zero series, e rapido",
           cod == 200 and j.get("fim") and not (j.get("series") or []),
           str(j)[:200])

    cod, j = varrer_lote(curta)
    checar(u"serie curta: zero aceitas...",
           cod == 200 and j.get("fim") and not (j.get("series") or []),
           str(j)[:200])
    checar(u"  ...MAS ela diz quantas achou e com quantos cortes",
           bool(j.get("curtas")) and j.get("piso"),
           u"curtas=%s piso=%s" % (j.get("curtas"), j.get("piso")))

    cod, j = varrer_lote(root + "_nao_existe")
    checar(u"pasta inexistente: diz o que houve",
           cod == 200 and j.get("erro") and not (j.get("series") or []),
           str(j)[:200])
    cod, _c, _ = postar("/api/lote/varrer", {"pasta": root})
    checar(u"  e o POST unico antigo saiu (a tela varre pela casca)",
           cod in (404, 405), cod)

    cod, corpo, _ = postar("/api/pastas", {"caminho": ""})
    j = json_de(corpo) or {}
    checar(u"o seletor abre com as unidades", bool(j.get("unidades")),
           corpo[:160])
    cod, corpo, _ = postar("/api/pastas", {"caminho": root})
    j = json_de(corpo) or {}
    checar(u"e desce na arvore", j.get("caminho") == root, corpo[:160])
    checar(u"e nao lista arquivos", not j.get("arquivos"), j.get("arquivos"))


def perfil_experiente(root):
    secao(u"3. EXPERIENTE: a API, e os valores de fronteira")

    cod, corpo, _ = pegar("/api/status")
    j = json_de(corpo) or {}
    checar(u"o status responde",
           cod == 200 and "paused" in j and "versao" in j, corpo[:160])
    atual = j.get("current") or {}
    checar(u"  o status nao leva o caminho da serie",
           "sdir" not in atual, list(atual))
    checar(u"  nem o UID inteiro dela",
           "uid_cheio" not in atual, list(atual))
    checar(u"  e o log nao viaja no status",
           "log" not in j or not isinstance(j.get("log"), list),
           u"o log tem barra propria")

    cod, corpo, _ = pegar("/api/config")
    j = json_de(corpo) or {}
    checar(u"a config responde",
           cod == 200 and "chaves" in j and "valores" in j, corpo[:120])
    checar(u"  e diz o que divergiu do que esta em uso",
           "divergente" in j, list(j)[:8])
    checar(u"  e a ajuda de cada chave viaja junto",
           "ajuda" in j, list(j)[:8])

    for valor, esperado in ((1, u"aceita ou recusa, mas nao explode"),
                            (0, u"idem"), (999999, u"idem")):
        cod, corpo, _ = postar("/api/config", {"MIN_SLICES": str(valor)})
        checar(u"MIN_SLICES=%s: %s" % (valor, esperado),
               cod == 200 and json_de(corpo) is not None, corpo[:120])

    cod, corpo, _ = postar("/api/config", {"DAYS_BACK": "36500"})
    checar(u"DAYS_BACK=36500 e' aceito sem derrubar", cod == 200, corpo[:120])
    cod, corpo, _ = pegar("/api/status")
    checar(u"  e o vigia continua de pe depois disso", cod == 200, cod)

    cod, corpo, _ = pegar("/api/plano")
    checar(u"o plano de execucao responde", cod in (200, 404), cod)


def perfil_inesperado(root):
    secao(u"4. O INESPERADO: o que ninguem previu, e acontece")

    cod, corpo, _ = pegar("/api/varrer/iniciar", dados=b"isto nao e json",
                          tipo="application/json", metodo="POST")
    checar(u"corpo que nao e' JSON: responde, nao quebra",
           cod in (200, 400, 422), u"%s %s" % (cod, corpo[:120]))

    cod, corpo, _ = postar("/api/varrer/iniciar", {"uso": "lote", "paster": root})
    checar(u"chave errada: responde, nao quebra", cod in (200, 400, 422),
           u"%s %s" % (cod, corpo[:120]))

    for valor in (123, None, [], {"a": 1}, True):
        cod, corpo, _ = postar("/api/varrer/iniciar",
                               {"uso": "lote", "pasta": valor, "dias": 0})
        checar(u"pasta=%r: responde, nao quebra" % (valor,),
               cod in (200, 400, 422), u"%s %s" % (cod, corpo[:100]))

    for caminho, rot in (
            (root + "\\..\\..\\..\\Windows", u"travessia com .."),
            ("\\\\maquina_que_nao_existe\\share", u"UNC inexistente"),
            ("CON", u"dispositivo do DOS"),
            ("", u"vazio")):
        cod, j = varrer_lote(caminho)
        checar(u"%s: responde sem travar" % rot, cod == 200 and j.get("fim"),
               u"%s %s" % (cod, str(j)[:100]))

    import time as _time
    t0 = _time.time()
    cod, corpo, _ = postar("/api/varrer/iniciar",
                           {"uso": "lote", "pasta": "C:\\Windows\\System32",
                            "dias": 0}, timeout=15)
    j = json_de(corpo) or {}
    checar(u"pasta do sistema: a varredura da tela responde na hora, "
           u"sem esperar a leitura", cod == 200 and bool(j.get("v"))
           and _time.time() - t0 < 10, u"%s %.1f s" % (cod, _time.time() - t0))
    if j.get("v"):
        cod2, corpo2, _ = postar("/api/varrer/estado", {"v": j["v"]}, timeout=15)
        checar(u"  e o estado responde enquanto ela le", cod2 == 200
               and (json_de(corpo2) or {}).get("v") == j["v"], cod2)
        postar("/api/varrer/parar", {"v": j["v"]}, timeout=15)
        fim = _time.time() + 60.0
        e = {}
        while _time.time() < fim:
            e = json_de(postar("/api/varrer/estado", {"v": j["v"]},
                               timeout=15)[1]) or {}
            if e.get("fim"):
                break
            _time.sleep(0.3)
        checar(u"  e «Parar a leitura» encerra a varredura",
               e.get("fim") is True and e.get("parado") is True, str(e)[:120])
        checar(u"  e nao devolve serie de dentro do Windows",
               not (e.get("linhas") or []), len(e.get("linhas") or []))

    for nome, rot in ((u"pasta com acento çãé", u"acento"),
                      (u"pasta com espaço", u"espaco"),
                      (u"検査フォルダ", u"japones"),
                      (u"p" * 200, u"nome de 200 letras")):
        cod, j = varrer_lote(os.path.join(root, nome))
        checar(u"nome %s: responde" % rot, cod == 200 and j.get("fim"),
               u"%s" % cod)

    for caminho in ("..\\..", "C:", "\\\\", "//", "\x00", "a\tb\nc"):
        cod, corpo, _ = postar("/api/pastas", {"caminho": caminho})
        checar(u"seletor com %r: responde" % caminho[:12], cod == 200,
               u"%s %s" % (cod, corpo[:80]))

    a = postar("/api/config", {"MIN_SLICES": "20"})
    b = postar("/api/config", {"MIN_SLICES": "20"})
    checar(u"salvar duas vezes seguidas: as duas respondem",
           a[0] == 200 and b[0] == 200, u"%s %s" % (a[0], b[0]))

    cod, corpo, _ = pegar("/api/pastas?caminho=C:\\")
    checar(u"GET em rota que virou POST e' recusado",
           cod in (404, 405), u"%s" % cod)

    cod, corpo, _ = pegar("/isto/nao/existe")
    checar(u"rota inexistente: 404, e nao 500", cod == 404, cod)

    cod, corpo, _ = postar("/api/varrer/iniciar",
                           {"uso": "lote", "pasta": "C:\\" + "x" * 100000})
    checar(u"corpo de 100 mil caracteres: responde",
           cod in (200, 400, 413, 422), u"%s" % cod)

    cod, corpo, _ = pegar("/api/status")
    checar(u"DEPOIS DE TUDO, o vigia continua de pe", cod == 200, cod)


def perfil_o_aplicar_aplica(base):
    secao(u"3b. o Aplicar aplica: a pasta nova vale NO PROCESSO")

    nova = os.path.join(base, "arvore_nova")
    os.makedirs(os.path.join(nova, "PACIENTE", "CT"), exist_ok=True)

    cod, corpo, _ = postar("/api/config", {"valores": {"ROOT": nova}})
    j = json_de(corpo) or {}
    checar(u"trocar o ROOT sem confirmar e' recusado",
           bool(j.get("precisa_confirmar")), corpo[:140])
    checar(u"e a recusa vem com o laudo do caminho",
           bool((j.get("validacao") or {}).get("escrita")),
           u"existe/le/ESCREVE — e o RTSTRUCT e' gravado ao lado da serie")

    cod, corpo, _ = postar("/api/config",
                           {"valores": {"ROOT": nova}, "confirmar_root": True})
    j = json_de(corpo) or {}
    checar(u"com confirmacao, grava", bool(j.get("ok")), corpo[:140])

    cod, corpo, _ = postar("/api/reiniciar", {})
    j = json_de(corpo) or {}
    checar(u"a recarga a quente e' aceita", bool(j.get("ok")), corpo[:140])
    checar(u"e ela diz QUANDO vale", bool(j.get("quando")),
           u"sem isso a tela nao tem o que prometer")

    virou = False
    for _ in range(40):
        time.sleep(0.5)
        cod, corpo, _ = pegar("/api/status", timeout=5)
        st = json_de(corpo) or {}
        if (st.get("root") or u"").rstrip("\\/") == nova.rstrip("\\/"):
            virou = True
            break
    checar(u"o PROCESSO passou a varrer a pasta nova", virou,
           u"o arquivo mudou e o vigia continuou na pasta antiga — "
           u"que e' exatamente o defeito que o botao tinha")

    cod, corpo, _ = pegar("/config")
    _i = corpo.find("function salvar(")
    _j = corpo.find("function recarregar(")
    checar(u"a tela de configuracoes tem o salvar e a recarga",
           _i >= 0 and _j >= 0,
           u"salvar=%d recarregar=%d — sem as duas, o «Aplicar» nao existe "
           u"nesta tela e o resto desta secao mede outra coisa" % (_i, _j))
    if _i < 0 or _j < 0:
        return
    trecho = corpo[min(_i, _j):max(_i, _j) + 1800]
    tela = re.sub(r"//[^\n]*", u" ", trecho)
    checar(u"o Aplicar da tela chama a recarga",
           "/api/reiniciar" in trecho,
           u"gravar e parar ali faz o botao prometer aplicar e nao aplicar")
    checar(u"  e a tela oferece as DUAS saidas",
           u"Salvar no arquivo" in corpo
           and u"Reiniciar agora" in corpo,
           u"recarregar entre series e uma escolha: quem tem um lote de seis "
           u"horas rodando pode querer so gravar e aplicar de manha")
    checar(u"e nao manda ninguem reiniciar o programa",
           u"proximo arranque" not in tela,
           u"a recarga a quente existe justamente porque o operador de "
           u"campo as vezes nao tem console para fechar e reabrir")


def perfil_as_duas_conferencias(root):
    secao(u"a conferencia rapida responde, e a profunda saiu da instalacao")
    import radai_station_check as CE

    j = CE.conferir(root=root, porta=PORTA)
    checar(u"a checagem rapida responde", isinstance(j, dict) and not j.get("erro"),
           str(j)[:160])
    if j.get("erro"):
        return

    secoes = {s.get("titulo", u""): s for s in (j.get("secoes") or [])}
    checar(u"e ela traz as sete secoes", len(secoes) >= 7,
           u", ".join(sorted(secoes))[:150])

    ident = secoes.get(u"Identidade") or {}
    valores = [i.get("valor") for i in (ident.get("itens") or [])]
    checar(u"a identidade diz produto, versao e interpretador",
           any(u"." in str(v) for v in valores) and len(valores) >= 5,
           valores[:3])

    travas = next((s for t, s in secoes.items()
                   if u"travas cl" in t.lower()), None)
    PISO_DE_TRAVAS = 5
    itens = [i for i in ((travas or {}).get("itens") or [])
             if not i.get("nota")]
    n = len(itens)
    checar(u"o relatorio lista as travas do item 6 (piso de %d)"
           % PISO_DE_TRAVAS, bool(travas) and n >= PISO_DE_TRAVAS,
           u"%d" % n)
    if travas:
        vivas = [i for i in itens if i.get("ok") is True]
        checar(u"e todas estao presentes E sao chamadas",
               len(vivas) == n,
               u"; ".join(u"%s: %s" % (i["nome"], i["valor"])
                          for i in itens if i.get("ok") is not True))
        notas = [i for i in ((travas or {}).get("itens") or []) if i.get("nota")]
        checar(u"a secao declara o que ela MEDE e o que nao mede",
               bool(notas) and any(u"execu" in str(i.get("valor") or "")
                                   for i in notas))
        nomes = u" ".join(str(i.get("nome") or "") for i in travas["itens"])
        checar(u"a quinta trava (a do que se DIZ) esta na lista",
               u"plausibility" in nomes.lower()
               or u"ancoragem" in nomes.lower()
               or u"vocabul" in nomes.lower(), nomes[:120])

    r = j.get("resumo") or {}
    checar(u"o resumo separa faltando de avisos",
           set(r) >= {"ok", "faltam", "avisos"}, r)
    cfgs = secoes.get(u"Configuração") or {}
    root = next((i for i in (cfgs.get("itens") or []) if u"ROOT" in i["nome"]),
                None)
    checar(u"o ROOT aparece com laudo (existe / le / ESCREVE)",
           bool(root) and (u"escreve" in (root.get("detalhe") or u"").lower()
                           or u"propósito" in (root.get("detalhe") or u"")),
           (root or {}).get("detalhe"))
    vazio = CE.conferir(root=u"", porta=0)
    it = next((i for s in vazio["secoes"] for i in s["itens"]
               if u"ROOT" in i["nome"]), None)
    checar(u"e ROOT vazio e AVISO, nao falta",
           bool(it) and it.get("ok") is None and not it.get("grave"),
           u"ok=%s grave=%s" % ((it or {}).get("ok"), (it or {}).get("grave")))

    checar(u"e ela e' rapida mesmo", float(j.get("segundos") or 99) < 10,
           u"%s s" % j.get("segundos"))

    cod, pag, _ = pegar("/config")
    checar(u"a tela oferece o botão «Diagnosticar» (a checagem rápida)",
           u'id="btDiag"' in pag and u'onclick="diagnosticar()"' in pag
           and u">Diagnosticar</button>" in pag)
    checar(u"a tela nao oferece mais a «Verificação profunda»",
           u"Verificação profunda" not in pag
           and u"conferirProfunda" not in pag)
    def _funcao(texto, nome):
        i = texto.find("function %s(" % nome)
        if i < 0:
            return u""
        f = texto.find("\nfunction ", i + 10)
        return texto[i:f if f > i else i + 900]
    jsr = _funcao(pag, "diagnosticar")
    checar(u"e o Diagnosticar existe e NAO pergunta nada",
           bool(jsr) and u"confirm(" not in jsr
           and u"/api/diagnosticar" in jsr,
           u"%d caracteres ate a proxima funcao" % len(jsr))
    checar(u"  isca: o Diagnosticar com um `confirm` e acusado",
           u"confirm(" in _funcao(pag.replace(
               "function diagnosticar(){",
               "function diagnosticar(){ if(!confirm('x')) return;", 1),
               "diagnosticar"))


def _botoes_sem_roupa(html_servido, css):
    import html.parser

    css = re.sub(r"/\*.*?\*/", u" ", css, flags=re.S)
    regras = []
    for bloco in re.findall(r"(?:^|[{}])\s*([^{}@][^{}]*?)\s*\{", css):
        for parte in bloco.split(","):
            parte = parte.strip()
            if not parte:
                continue
            if re.search(r"(:|\[)", parte):
                continue
            simples = [p for p in re.split(r"\s+|>", parte) if p]
            if not simples:
                continue
            alvo = simples[-1].lower()
            if not (alvo.startswith(u"button") or alvo[:1] in u".#"):
                continue
            regras.append(simples)

    def casa(simples, tag, classes, ident):
        m = re.match(r"^([a-zA-Z][\w-]*)?((?:[.#][\w-]+)*)$", simples)
        if not m:
            return True
        if m.group(1) and m.group(1).lower() != tag:
            return False
        for parte in re.findall(r"[.#][\w-]+", m.group(2) or u""):
            if parte[0] == u"." and parte[1:] not in classes:
                return False
            if parte[0] == u"#" and parte[1:] != ident:
                return False
        return True

    class Leitor(html.parser.HTMLParser):
        VAZIAS = {"br", "img", "input", "hr", "meta", "link", "source"}

        def __init__(self):
            html.parser.HTMLParser.__init__(self, convert_charrefs=True)
            self.pilha = []
            self.nus = []

        def handle_starttag(self, tag, attrs):
            d = dict(attrs)
            no = (tag, set((d.get("class") or u"").split()), d.get("id") or u"")
            if tag == "button":
                if not self._vestido(no):
                    caminho = u" ".join(
                        t + (u"." + u".".join(sorted(c)) if c else u"")
                        for t, c, _i in (self.pilha[-2:] + [no]))
                    self.nus.append(caminho)
            if tag not in self.VAZIAS:
                self.pilha.append(no)

        def handle_startendtag(self, tag, attrs):
            self.handle_starttag(tag, attrs)
            if tag not in self.VAZIAS and self.pilha:
                self.pilha.pop()

        def handle_endtag(self, tag):
            for i in range(len(self.pilha) - 1, -1, -1):
                if self.pilha[i][0] == tag:
                    del self.pilha[i:]
                    break

        def _vestido(self, no):
            for simples in regras:
                if not casa(simples[-1], no[0], no[1], no[2]):
                    continue
                i = 0
                for anc in self.pilha:
                    if i < len(simples) - 1 and casa(simples[i], *anc):
                        i += 1
                if i == len(simples) - 1:
                    return True
            return False

    leitor = Leitor()
    try:
        leitor.feed(html_servido)
    except Exception:
        return []
    return leitor.nus


def perfil_a_tela_esta_vestida():
    secao(u"toda tela servida se veste: fonte, botao e ficha de cor")

    TELAS = [u"/", u"/ver", u"/lote", u"/vigia",
             u"/bridge/laudo", u"/nidus/projecao",
             u"/elastic/fusao", u"/config", u"/recon3d/anatomia",
             u"/bolus/gerar"]

    for rota in TELAS:
        cod, corpo, _ = pegar(rota)
        if cod != 200:
            checar(u"%s responde" % rota, False, u"HTTP %s" % cod)
            continue
        css = u"\n".join(re.findall(r"<style[^>]*>(.*?)</style>", corpo,
                                    re.S | re.I))
        if not css.strip():
            checar(u"%s traz folha de estilo" % rota, False)
            continue

        tem_fonte = re.search(
            r"(^|[,\s{}])(html\s*,\s*body|body\s*,\s*html|body|html)\s*\{[^}]*"
            r"font-family\s*:", css, re.I | re.M)
        checar(u"%s declara a fonte do corpo" % rota, bool(tem_fonte),
               u"sem font-family em html/body: cai no serif do navegador")

        nus = _botoes_sem_roupa(corpo, css)
        checar(u"%s veste TODOS os botoes" % rota, not nus,
               u"%d botao(oes) caem no padrao do sistema: %s"
               % (len(nus), u"; ".join(nus[:3])))

        usados = set(re.findall(r"var\(\s*(--[A-Za-z0-9-]+)\s*\)", css))
        definidos = set(re.findall(r"(--[A-Za-z0-9-]+)\s*:", css))
        for m in re.finditer(r"style=[\"']([^\"']*)[\"']", corpo):
            for t in re.findall(r"(--[A-Za-z0-9-]+)\s*:", m.group(1)):
                definidos.add(t)
        orfas = sorted(usados - definidos)
        checar(u"%s: nenhuma ficha de cor sem valor" % rota, not orfas,
               u"%s — a declaracao inteira nao se aplica"
               % u", ".join(orfas[:5]))


def baixar_bytes(caminho, timeout=30):
    req = urllib.request.Request(_url(caminho))
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.getcode(), r.read(), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read(), dict(e.headers or {})
    except Exception as e:
        return 0, ("%s: %s" % (type(e).__name__, e)).encode(), {}


def perfil_bridge_tres_colunas(root):
    secao(u"PERFIL 8 — o médico com uma série: escolher e ler")

    st_l, h_laudo, _c = pegar("/bridge/laudo")
    st_t, h_tps, _c = pegar("/bridge/tps")
    checar(u"as duas portas do DicomBridge abrem", st_l == 200 and st_t == 200,
           u"laudo %s · tps %s" % (st_l, st_t))
    checar(u"e são a mesma página (a do TPS leva à do laudo)",
           h_laudo.count(u'id="dc_e1"') == 1 and h_tps.count(u'id="dc_e1"') == 1)
    checar(u"o modo não viaja na query",
           u"?modo=" not in h_laudo and u"?modo=" not in h_tps)

    import radai_modules as _M
    nome_card = [f[2] for f in _M.FERRAMENTAS["bridge"]
                 if f[0] == "bridge_laudo"]
    checar(u"o card do laudo tem nome", bool(nome_card))
    if nome_card:
        _h1 = re.search(r'<h1 class="ui-fn-tag"[^>]*>.*?<span data-radai-frase>'
                        r'(.*?)</span></h1>', h_laudo, re.S)
        checar(u"e o h1 da tela diz o mesmo nome do card",
               _h1 is not None and _h1.group(1) == nome_card[0],
               u"card diz %r" % nome_card[0])

    st, corpo, _c = postar("/api/bridge/varrer", {"pasta": root})
    d = json_de(corpo) or {}
    series = d.get("series") or []
    checar(u"varrer a pasta lista a série", st == 200 and len(series) >= 1,
           u"%s · %d série(s)" % (st, len(series)))
    if not series:
        return

    bil = str(series[0].get("bilhete") or "")
    checar(u"e cada série vem com o bilhete que amarra pasta+UID", bool(bil))

    st, corpo, _c = postar("/api/bridge/laudo",
                           {"pasta": root, "indice": 0, "b": bil})
    laudo = json_de(corpo) or {}
    checar(u"o diagnóstico da série vem no passo 2",
           st == 200 and not laudo.get("erro") and laudo.get("achados"),
           u"%s · %s" % (st, str(laudo)[:90]))
    for rota in ("/api/bridge/entregar", "/api/bridge/baixar"):
        st, _b, _c = baixar_bytes(rota)
        checar(u"a entrega pelo navegador saiu: %s não responde" % rota,
               st in (404, 405), str(st))


def perfil_bridge_tps(base):
    secao(u"PERFIL 9 — o técnico com um estudo grande: as séries que ele traz")
    import datetime
    from make_test_series import escreve_serie

    estudo = os.path.join(base, "estudo_grande")
    for i, cortes in enumerate((6, 4, 5)):
        d = os.path.join(estudo, "S%03d" % (i + 1))
        os.makedirs(d)
        escreve_serie(d, "PAC_TPS", datetime.datetime(2026, 9, 1, 8, i), cortes)

    st, corpo, _c = postar("/api/bridge/varrer", {"pasta": estudo})
    d = json_de(corpo) or {}
    series = d.get("series") or []
    checar(u"o estudo grande varre e mostra as três séries",
           st == 200 and len(series) == 3,
           u"%s · %d série(s)" % (st, len(series)))
    checar(u"  cada uma com o bilhete que amarra pasta+UID",
           all(s.get("bilhete") for s in series), str(len(series)))


def _serie_no_root_atual(base):
    from make_test_series import escreve_serie
    import datetime
    st, corpo, _c = pegar("/api/status", timeout=10)
    raiz = (json_de(corpo) or {}).get("root") or u""
    if not raiz or not os.path.isdir(raiz):
        return raiz, u""
    serie = os.path.join(raiz, "PAC_TOPO", "2026_AGO_30_TC_09h00", "S002")
    if not os.path.isdir(serie):
        escreve_serie(serie, "PAC_TOPO", datetime.datetime(2026, 8, 30, 9, 0),
                      30)
    st, corpo, _c = pegar("/api/vigia/plano", timeout=60)
    for ex in (json_de(corpo) or {}).get("exames") or []:
        if u"PAC_TOPO" in (ex.get("pasta") or u""):
            for sr in ex.get("series") or []:
                return serie, sr.get("uid") or u""
    return serie, u""


def perfil_o_painel_so_atende_pelos_proprios_nomes():
    secao(u"PERFIL 13 — o painel so atende pelos proprios nomes (E5)")
    for host in ("atacante.exemplo:%d" % PORTA, "127.0.0.1:%d" % (PORTA + 1),
                 "127.0.0.1"):
        cod, corpo, _c = pegar("/api/status", cabecalhos={"Host": host})
        checar(u"GET /api/status com Host %r: 403" % host, cod == 403,
               u"%s %s" % (cod, corpo[:80]))
    cod, corpo, _c = pegar("/", cabecalhos={"Host": "atacante.exemplo:%d"
                                            % PORTA})
    checar(u"GET / (uma TELA) com Host estranho: 403", cod == 403, cod)
    cod, _c, _h = pegar("/api/status", cabecalhos={"Host": "localhost:%d"
                                                   % PORTA})
    checar(u"(isca) localhost:porta passa", cod == 200, cod)
    cod, _c, _h = pegar("/api/status")
    checar(u"(isca) 127.0.0.1:porta passa", cod == 200, cod)
    cod, corpo, _c = pegar("/api/rescan", dados=b"{}",
                           tipo="application/json", metodo="POST",
                           cabecalhos={"Content-Length": str(64 * 1024 * 1024)})
    checar(u"POST com corpo declarado acima do teto: 413", cod == 413,
           u"%s %s" % (cod, corpo[:80]))
    cod, _c, _h = postar("/api/rescan", {})
    checar(u"(isca) o mesmo POST com corpo normal passa", cod == 200, cod)


def perfil_topografia(root, base=None):
    secao(u"PERFIL 10 — topografia: duas ao mesmo tempo, e sem apagar a fila")
    import radai_topography as T

    sug, por_que = T.detectar(u"TC PESCOCO C CONTRASTE")
    checar(u"«pescoço» sugere o protocolo de cabeça e pescoço",
           T.CABECA_PESCOCO in sug, u"sugeriu %r" % (sug,))
    checar(u"e diz na tela por que sugeriu", u"pescoco" in por_que.lower(),
           u"motivo=%r" % por_que)
    sug, _m = T.detectar(u"CT NECK SOFT TISSUE")
    checar(u"e «neck» também, que é como o equipamento escreve",
           T.CABECA_PESCOCO in sug, u"sugeriu %r" % (sug,))
    sug, motivo = T.detectar(u"TC PELVE")
    checar(u"uma pelve não sugere cabeça e pescoço",
           T.CABECA_PESCOCO not in sug, u"sugeriu %r" % (sug,))
    checar(u"e não inventa motivo quando não sugeriu nada", not motivo,
           u"motivo=%r" % motivo)

    serie, uid = _serie_no_root_atual(base)
    if not uid:
        checar(u"a serie do teste aparece no plano do vigia", False, serie)
        return
    st, corpo, _c = postar("/api/fila/topografia",
                           {"uid": uid,
                            "topo": [T.TOTAL, T.CABECA_PESCOCO]})
    d = json_de(corpo) or {}
    guardado = d.get("topo") or []
    if isinstance(guardado, type(u"")):
        guardado = [guardado]
    checar(u"gravar duas topografias guarda as duas",
           st == 200 and len(guardado) == 2,
           u"%s · %r" % (st, d))

    checar(u"  e o marcador foi gravado na pasta da VARREDURA",
           os.path.exists(os.path.join(serie, "_RadAI",
                                       "%s.fila.json" % uid)))

    st, corpo, _c = postar("/api/fila/decidir",
                           {"uid": uid, "decisao": "incluir"})
    checar(u"e decidir «incluir» também responde de verdade",
           st == 200 and (json_de(corpo) or {}).get("ok"),
           u"%s · %s" % (st, str(corpo)[:80]))

    forjada = os.path.join(base, "pasta_forjada")
    os.makedirs(forjada, exist_ok=True)
    for rota, extra in (("/api/fila/decidir", {"decisao": "pular"}),
                        ("/api/fila/topografia", {"topo": [T.TOTAL]})):
        st, corpo, _c = postar(rota, dict(extra, uid=uid, pasta=forjada))
        checar(u"%s com uma pasta FORJADA no corpo: grava na da varredura, "
               u"e nao na forjada" % rota,
               st == 200 and not os.path.exists(
                   os.path.join(forjada, "_RadAI")),
               u"%s · %s" % (st, str(corpo)[:80]))
        st, corpo, _c = postar(rota, dict(extra, uid="1.2.826.0.1.99",
                                          pasta=forjada))
        checar(u"%s com um UID que a varredura nao viu: 404, e nada gravado"
               % rota, st == 404 and not os.path.exists(
                   os.path.join(forjada, "_RadAI")),
               u"%s · %s" % (st, str(corpo)[:80]))
    io.open(os.path.join(forjada, "sonda.txt"), "w").write(u"x")
    checar(u"  (isca) a pasta forjada aceita escrita: a recusa e da rota",
           os.path.exists(os.path.join(forjada, "sonda.txt")))
    st, corpo, _c = pegar("/api/vigia/plano", timeout=60)
    checar(u"o plano nao manda mais o caminho absoluto da serie a tela",
           st == 200 and u"pasta_abs" not in corpo
           and serie not in corpo
           and json.dumps(serie)[1:-1] not in corpo, corpo[:120])

    base = ("total", "lung_vessels")
    com = T.tasks_de([T.CABECA_PESCOCO], base)
    checar(u"escolher cabeça e pescoço acrescenta as tasks do pescoço",
           all(t in com for t in T.TASKS_DO_PESCOCO), u"ficou %r" % (com,))
    checar(u"e mantém as que já estavam",
           all(t in com for t in base), u"ficou %r" % (com,))

    sem = T.tasks_de([T.TOTAL], tuple(base) + tuple(T.TASKS_DO_PESCOCO))
    checar(u"voltar para Total tira as do pescoço",
           not any(t in sem for t in T.TASKS_DO_PESCOCO))
    checar(u"e não tira as outras", all(t in sem for t in base))

    for lixo in ([], [u""], [u"protocolo_que_nao_existe"], None):
        r = T.tasks_de(lixo, base)
        checar(u"topografia %r não zera as tasks" % (lixo,), bool(r),
               u"devolveu %r" % (r,))


def perfil_o_body_nunca_sai():
    secao(u"PERFIL 11 — BODY: proibido, e a trava mora em quem escreve")
    import engine

    recusou_todos = True
    passaram = []
    for raiz in sorted(engine.NOMES_DE_CONTORNO_EXTERNO):
        for sufixo in ("", "_ai", "_ts", "_v3D", "_cds"):
            nome = raiz + sufixo
            try:
                engine.conferir_sem_body([nome, "lung_left_ai"])
                recusou_todos = False
                passaram.append(nome)
            except Exception:
                pass
    checar(u"nenhum nome de contorno externo entra num RTSTRUCT",
           recusou_todos, u"passaram: %s" % passaram[:5])

    try:
        engine.conferir_sem_body(["v3d:body"])
        passou = True
    except Exception:
        passou = False
    checar(u"«v3d:body» também não", not passou)

    detalhe = u""
    try:
        engine.conferir_sem_body(["pele_ai", "chestwall_L_ai", "chestwall_R_ai"])
        passou = True
    except Exception as e:
        passou = False
        detalhe = str(e)[:90]
    checar(u"a pele e as duas paredes torácicas passam", passou, detalhe)

    import inspect
    fonte = inspect.getsource(engine.build_rtstruct)
    checar(u"e `build_rtstruct` chama a trava",
           "conferir_sem_body" in fonte)


def perfil_decisoes_de_estacao():
    secao(u"PERFIL 12 — as decisões de estação, e o selo que avisa sem impedir")

    for tela in ("/vigia", "/lote"):
        h = pegar(tela)[1]
        controle = (u'id="incluir_vista' in h.lower()
                    or u'name="incluir_vista' in h.lower()
                    or u'id="lt_vista' in h.lower())
        checar(u"%s não pergunta mais pelo VISTA-3D" % tela, not controle)

    _c, _corpo, _ = pegar("/api/config")
    _chaves = set((json_de(_corpo) or {}).get("chaves") or ())
    _saidas = ("INCLUIR_NV", "INCLUIR_CADS", "INCLUIR_MOOSE", "INCLUIR_HNLNL",
               "ENTREGAR_TS")
    checar(u"e /config não oferece mais as chaves de motor da estação",
           bool(_chaves) and not (_chaves & set(_saidas)),
           str(sorted(_chaves & set(_saidas))) if _chaves else _corpo[:120])
    import radai_watcher as W
    checar(u"e elas saíram do config de exemplo e do DEFAULTS",
           not [k for k in _saidas
                if re.search(r"(?m)^%s=" % k, W.DEFAULT_CFG) or k in W.DEFAULTS],
           str([k for k in _saidas
                if re.search(r"(?m)^%s=" % k, W.DEFAULT_CFG)
                or k in W.DEFAULTS]))
    checar(u"e o config antigo (com o nome de antes do NV) cai em "
           u"CHAVES_OBSOLETAS, e não é apelido de nada",
           all(k in W.CHAVES_OBSOLETAS
               for k in _saidas + ("INCLUIR_VISTA3D",))
           and not [k for k in _saidas + ("INCLUIR_VISTA3D",)
                    if k in getattr(W, "ALIAS_CFG", {})],
           repr(getattr(W, "ALIAS_CFG", None)))
    import engine as _E
    _do_cads = sorted(k for k, v in _E.MELHOR_FONTE.items() if v[0] == "cads")
    _do_nv = sorted(k for k, v in _E.MELHOR_FONTE.items() if v[0] == "nv")
    _candidatas = getattr(_E, "CANDIDATAS_AO_FULL", {})
    checar(u"o CADS nao elege mais nenhuma estrutura para o entregue",
           not _do_cads, "%d: %s" % (len(_do_cads), ", ".join(_do_cads[:4])))
    import radai_modes as _MD

    def _comparacao_por_omissao(protocolos):
        return sorted(set(m for p in protocolos
                          for m in (p.get("motores") or ())
                          if m in ("nv", "cads", "mse")))
    checar(u"e por isso ele nunca roda por omissão (nenhum protocolo o "
           u"arrasta; sem caixa, nenhum motor)",
           not _comparacao_por_omissao(_MD.PROTOCOLOS)
           and _MD.motores_da_escolha((), "CT") == (),
           str(_comparacao_por_omissao(_MD.PROTOCOLOS)))
    checar(u"  isca: um protocolo forjado arrastando o CADS é acusado",
           _comparacao_por_omissao(tuple(_MD.PROTOCOLOS) + (
               {"cod": "isca", "motores": ("cads",)},)) == ["cads"])
    checar(u"  e as dez que ele elegia estao registradas, com o motivo",
           len(_candidatas) == 10, str(sorted(_candidatas)))
    checar(u"  entre elas a mama bilateral",
           "breast_left" in _candidatas and "breast_right" in _candidatas)
    checar(u"o segundo motor tambem nao elege nenhuma", not _do_nv, str(_do_nv))
    checar(u"e por isso ele nunca roda por omissão — comparar é escolha",
           "nv" not in _comparacao_por_omissao(_MD.PROTOCOLOS)
           and _MD.motores_da_escolha(("nv",), "CT") == ("nv",)
           and _MD.motores_da_escolha(("nv",), "MR") == (),
           str(_MD.motores_da_escolha(("nv",), "CT")))
    checar(u"nenhum motor de terceiro alimenta o entregue hoje",
           not _E.motores_que_alimentam(), str(_E.motores_que_alimentam()))

    import radai_modules as M
    el = M.MODULOS["elastic"]
    checar(u"o Elastic RT não anuncia obra encerrada",
           not (el.get("selo") or u"").strip(),
           u"selo=%r" % el.get("selo"))
    checar(u"nem carrega ajuda de selo órfã",
           not (el.get("selo_ajuda") or u"").strip(),
           u"selo_ajuda=%r" % (el.get("selo_ajuda") or u"")[:40])
    checar(u"e o cartão continua alcançável",
           not str(el.get("estado", "")).upper().startswith("EM CONSTRU"),
           u"estado=%r" % el.get("estado"))
    checar(u"e a tela dele responde", pegar("/elastic/fusao")[0] == 200)


def montar_cenario(base):
    import datetime
    from make_test_series import escreve_serie

    root = os.path.join(base, "TCs")
    d = os.path.join(root, "PAC_INTER_1", "2026_AGO_30_TC_09h00", "S002_PELVE")
    os.makedirs(d)
    escreve_serie(d, "PAC_INTER_1", datetime.datetime(2026, 8, 30, 9, 0), 30)

    vazia = os.path.join(base, "vazia")
    os.makedirs(vazia)

    so_lixo = os.path.join(base, "so_lixo")
    os.makedirs(so_lixo)
    for i in range(30):
        io.open(os.path.join(so_lixo, "f%02d.dll" % i), "wb").write(
            os.urandom(120000))

    curta = os.path.join(base, "curta")
    os.makedirs(curta)
    escreve_serie(curta, "PAC_CURTO", datetime.datetime(2026, 8, 30, 9, 0), 3)

    for nome in (u"pasta com acento çãé", u"pasta com espaço", u"検査フォルダ"):
        try:
            os.makedirs(os.path.join(root, nome))
        except Exception:
            pass
    return root, vazia, so_lixo, curta


def main():
    global PORTA
    print(u"=" * 68)
    print(u"test_interactions | do primeiro clique ao pedido mais estranho")
    print(u"=" * 68)

    from test_panel import porta_de_teste
    PORTA, aviso = porta_de_teste(8795)
    if aviso:
        print(u"  %s" % aviso)

    base = tempfile.mkdtemp(prefix="radai_inter_")
    acervo = tempfile.mkdtemp(prefix="radai_inter_acervo_")
    root, vazia, so_lixo, curta = montar_cenario(base)

    cfg = os.path.join(base, "inter.config")
    with io.open(cfg, "w", encoding="utf-8") as f:
        f.write("ROOT=%s\nDRY_RUN=1\nMIN_SLICES=20\nQUIET_MIN=0\nPORT=%d\n"
                "LOG_DIR=%s\n" % (root, PORTA, os.path.join(base, "log")))
    env = dict(os.environ, RADAI_CONFIG=cfg, RADAI_MACHINE="PC_INTERACOES",
               RADAI_CALIB_DIR=acervo, LOCALAPPDATA=os.path.join(base, "ad"),
               RADAI_REGISTRO_DIR=os.path.join(base, "registro"),
               PYTHONIOENCODING="utf-8:replace")
    # GUARDA: o vigia importado no proprio processo le o config e grava o log; sem isto, os da pasta app de quem roda.
    for _k in ("RADAI_CONFIG", "RADAI_CALIB_DIR", "RADAI_REGISTRO_DIR"):
        os.environ[_k] = env[_k]
    proc = subprocess.Popen(
        [sys.executable, _componentes.fonte("app/radai_watcher.py")],
        env=env, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    try:
        vivo = False
        for _ in range(60):
            time.sleep(0.5)
            if pegar("/api/status", timeout=2)[0] == 200:
                vivo = True
                break
        checar(u"o servidor do teste subiu", vivo,
               u"porta %d" % PORTA)
        if vivo:
            perfil_primeiro_dia()
            perfil_rotina(root, vazia, so_lixo, curta)
            perfil_experiente(root)
            perfil_inesperado(root)
            perfil_o_aplicar_aplica(base)
            perfil_a_tela_esta_vestida()
            perfil_as_duas_conferencias(root)
            perfil_bridge_tres_colunas(root)
            perfil_bridge_tps(base)
            perfil_topografia(root, base)
            perfil_o_painel_so_atende_pelos_proprios_nomes()
            perfil_o_body_nunca_sai()
            perfil_decisoes_de_estacao()
    finally:
        try:
            proc.terminate()
            proc.wait(timeout=20)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
        shutil.rmtree(base, ignore_errors=True)
        shutil.rmtree(acervo, ignore_errors=True)

    print(u"\n" + u"=" * 68)
    if _falhou:
        print(u"FALHOU: %d de %d checagens" % (_falhou, _ok + _falhou))
        for f in _falhas:
            print(u"  - %s" % f)
    else:
        print(u"OK: %d checagens, todas passaram" % _ok)
    print(u"=" * 68)
    return 1 if _falhou else 0


if __name__ == "__main__":
    sys.exit(main())
