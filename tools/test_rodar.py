# -*- coding: utf-8 -*-
import asyncio
import html as _html
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import traceback
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
APP = os.path.join(RAIZ, "app")
sys.path.insert(0, AQUI)
sys.path.insert(0, APP)

import _cleanup
import _componentes
_cleanup.adotar_prefixo("radai_rodar_")
os.environ["RADAI_CALIB_DIR"] = tempfile.mkdtemp(prefix="radai_rodar_")
_CFG = os.path.join(os.environ["RADAI_CALIB_DIR"], "radai_watcher.config")
io.open(_CFG, "w", encoding="utf-8").write(u"ROOT=\n")
os.environ["RADAI_CONFIG"] = _CFG

PORTA = 8858
BASE = "http://127.0.0.1:%d" % PORTA
_RES = []


def checar(nome, cond, detalhe=""):
    _RES.append((nome, bool(cond), detalhe))
    print(u"  %s  %s%s" % (u"ok   " if cond else u"FALHA", nome,
                          (u"  [%s]" % detalhe) if (detalhe and not cond) else u""))


def secao(t):
    print(u"\n─── %s %s" % (t, u"─" * max(0, 66 - len(t))))


def _visivel(p):
    p = re.sub(r"(?s)<script.*?</script>", u" ", p)
    p = re.sub(r"(?s)<style.*?</style>", u" ", p)
    p = re.sub(r"(?s)<template.*?</template>", u" ", p)
    p = re.sub(r"(?s)<!--.*?-->", u" ", p)
    return u" ".join(_html.unescape(re.sub(r"<[^>]+>", u" ", p)).split())


def _pagina():
    import radai_batch as L
    import radai_menu
    import radai_review
    return radai_review.aplicar(radai_menu.aplicar(L._pagina(), "lote"))


def _js(p):
    return u"\n".join(re.findall(r"(?s)<script[^>]*>(.*?)</script>", p))


def _sem_comentario(js):
    js = re.sub(r"(?s)/\*.*?\*/", u" ", js)
    return re.sub(r"(?m)^\s*//.*$", u" ", js)


def _funcao(js, nome):
    i = js.index(u"function %s(" % nome)
    j = js.find(u"\nfunction ", i + 10)
    return js[i:j if j > 0 else len(js)]


FRASE = (u"Utilize esta ferramenta de segmentação para iniciar os estudos dentro "
         u"do aplicativo (alimenta os módulos de comparação de segmentações e de "
         u"reconstruções 3D).")
CARD_ADD = u"Carregue imagens a partir de uma pasta e adicione à fila segmentações"
ALERTA = u"Material de estudo — 100% local. Nenhuma imagem sai desta rede"
FRONTEIRA = (u"Tudo o que é gravado se mantém com sugestão não aprovada "
             u"(ApprovalStatus = UNAPPROVED). Revisar é ato médico — utilize as "
             u"ferramentas de Ver Segmentação e Reconstrução 3D para estudo. Não "
             u"é um dispositivo médico.")
GANCHO = u"Exercite o aprendizado em:"
SAIRAM = (u"Um paciente ou uma pasta inteira", u"O RTSTRUCT é gravado na pasta de cada série, ao lado dos DICOMs — sobrevive",
          u"Ver detalhes da lista", u"incluir todas desta pasta",
          u"tirar as desta pasta", u"Tudo o que esta tela grava sai como",
          u"como ele veio do sistema de imagens", u"Iniciar sem salvar",
          u"desta pasta no carrinho")


VARRER_DE_ANTES = u"""function _ltFim(linhas, d, ler, dias, p, o){
 var popup = uiPopupSerie('cx1');
 popup.fechar();
 SERIES = linhas || [];
 if(!SERIES.length){ ltEscolha(); msg('Nenhuma série nesta pasta.', false); return; }
 _achouNaTela(molde.replace('%s', SERIES.length), nota);
}
"""


def _sem_serie_fica_aberto(fim):
    fecha = u"popup.fechar()"
    vazio = u": 'Nenhuma série nesta pasta.', false)"
    if fecha not in fim or vazio not in fim:
        return False
    i_fecha, i_vazio = fim.index(fecha), fim.index(vazio)
    i_cond = fim.rfind(u"!series.length", 0, i_vazio)
    if i_vazio > i_fecha or i_cond < 0:
        return False
    bloco = fim[i_cond:i_fecha]
    return (u"ltEscolha()" in bloco
            and u"return;" in bloco[bloco.index(vazio):]
            and u"_achouNaTela(molde" in fim[bloco.index(vazio) + i_cond:])


def _cabeca_ok(p):
    m = re.search(r'<h1 class="ui-fn-tag"[^>]*>(.*?)</h1>', p, re.S)
    if not m or u"Rodar agora" not in _visivel(m.group(1)):
        return False
    f = re.search(r'<p class="ui-fn-frase"[^>]*>(.*?)</p>', p, re.S)
    return bool(f) and _visivel(f.group(1)) == FRASE


def teste_a_cabeca_e_o_rodape():
    secao(u"R1–R5: a tag, a frase, o card e o alerta de uma linha")
    p = _pagina()
    vis = _visivel(p)
    checar(u"a cabeça é `cabeca_de_funcao`: tag «Rodar agora» e a frase do autor",
           _cabeca_ok(p))
    isca = p.replace(u'class="ui-fn-tag"', u'class="rc-chip"', 1)
    checar(u"  (isca) a tag velha no lugar reprova", not _cabeca_ok(isca))
    checar(u"  o «?» está ao lado da tag",
           re.search(r'</h1>\s*<span class="ui-ajuda', p) is not None)
    checar(u"  e o chip «Processar» saiu", u"> Processar<" not in p
           and u"rc-capa" not in p.split(u"</head>", 1)[1])
    fora = [t for t in SAIRAM if t in vis]
    checar(u"os textos que o autor tirou não aparecem na tela", not fora,
           u" | ".join(fora))
    checar(u"o card «Adicionar novas séries» com o texto novo", CARD_ADD in vis)
    alertas = re.findall(r'<div class="ui-alerta[^"]*">(.*?)</div>', p, re.S)
    _tx = lambda h: u" ".join(_html.unescape(re.sub(r"<[^>]+>", u"", h)).split())
    checar(u"um alerta só, no pé, com «100% local» em negrito",
           len(alertas) == 1 and _tx(alertas[0]) == ALERTA
           and u"<b>100% local</b>" in alertas[0], str(len(alertas)))
    checar(u"  e ele vem depois do gancho e do passo 2",
           p.index(u'class="ui-alerta') > p.index(GANCHO) > p.index(u'id="cx2"'))
    checar(u"a tela não cita TPS (V13)", u"TPS" not in vis,
           vis[max(0, vis.find(u"TPS") - 60):vis.find(u"TPS") + 20])


def teste_os_passos():
    secao(u"R6–R13: os dois passos, o carrinho e o gancho")
    p = _pagina()
    vis = _visivel(p)
    checar(u"o passo 2 nasce recolhido",
           re.search(r'class="ps-cx fechado" id="cx2"', p) is not None)
    checar(u"o passo 1 mora no popup da casca, «Carregar imagens», e abre sozinho",
           u'<div class="ui-ps" id="cx1" data-ui-ps data-titulo="Carregar imagens"' in p
           and u'data-largura="860" data-sozinho>' in p
           and u'class="ps-cx fechado" id="cx1"' not in p)
    checar(u"  o «Adicionar novas séries» fica antes do passo 2",
           0 <= p.find(u'id="cd_add"') < p.find(u'id="cx2"'))
    checar(u"o rótulo do caminho é o do autor",
           u"Caminho — pasta, ou o .zip do exame" in vis)
    m = re.search(r'<div class="linha cam-linha">(.*?)</div>', p, re.S)
    checar(u"R10: o campo e os dois botões na MESMA linha flexível, com a "
           u"estrela da favorita e o explorador da casca",
           m is not None and u'id="pasta"' in m.group(1)
           and u"ltProcurar(this)" in m.group(1) and u"varrer()" in m.group(1)
           and u'data-ui-fav="pasta"' in m.group(1))
    js = _sem_comentario(_js(p))
    checar(u"  e o seletor próprio (#fp) saiu: o «Procurar…» abre o uiExplorador",
           u'id="fp"' not in p and u"function fpAbrir" not in js
           and u"uiExplorador(" in _funcao(js, u"ltProcurar"))
    checar(u"R11: a frase da varredura é inteira",
           u"Varrendo a pasta: o cabeçalho de cada arquivo é lido, e uma pasta "
           u"grande pode levar alguns minutos." in _visivel(p)
           and u"pode levar)..." not in js)
    checar(u"o filtro de data mora no popup e a varredura manda os dias dele",
           u'<select data-ui-dias id="lt_dias"' in p
           and u"uiDias('lt_dias')" in _funcao(js, u"varrer"))
    m = re.search(r'<div class="cart-acoes">(.*?)</div>', p, re.S)
    bts = re.findall(r'<button[^>]*>([^<]*)</button>', m.group(1) if m else u"")
    checar(u"R12: o banner tem os três botões, nessa ordem",
           bts == [u"Adicionar as selecionadas à fila",
                   u"Selecionar todas as séries", u"Esvaziar seleção"],
           u" | ".join(bts))
    corpo = _funcao(js, u"esvaziarSelecao")
    checar(u"  «Esvaziar seleção» não pergunta e tira só as desta lista",
           u"perguntar(" not in corpo and u"limparSelecao()" not in corpo
           and u"porNoCarrinho(s, false)" in corpo)
    checar(u"  e a lista de detalhes saiu", u'id="cartlista"' not in p
           and u"cartAlternar" not in js)
    checar(u"R7/R15: «Adicionar novas séries» chama `novasSeries`",
           u'id="cd_add"' in p and u'onclick="novasSeries()"' in p)
    nv = _funcao(js, u"novasSeries")
    checar(u"  que limpa a lista, recolhe o 2, abre o popup do 1 e põe a favorita",
           u"SERIES = []" in nv and u"psFechar('cx2')" in nv
           and u"ltEscolha()" in nv and u"FP_FAV" in nv
           and u"uiPopupSerie('cx1')" in _funcao(js, u"ltEscolha"))
    vr = _funcao(js, u"varrer")
    fim = _funcao(js, u"_ltFim")
    checar(u"  a varredura é a da casca, em segundo plano, e não um "
           u"POST único", u"uiVarrer({uso: 'lote'" in vr
           and u"/api/lote/varrer" not in vr)
    checar(u"  e a varredura que achou séries fecha o popup; a que falhou o reabre",
           u"popup.fechar()" in fim
           and fim.index(u"ltEscolha()") < fim.index(u"popup.fechar()"))
    checar(u"  a que não achou série deixa o popup aberto e diz que não achou; a "
           u"que achou leva a contagem para a tela de trabalho",
           _sem_serie_fica_aberto(fim) and u'id="lt_achou"' in p
           and p.index(u'id="lt_achou"') > p.index(u'id="cx2"'))
    checar(u"  ISCA: o fim que fecha o popup antes de olhar se achou série reprova",
           not _sem_serie_fica_aberto(VARRER_DE_ANTES))
    checar(u"  e o erro de rede também reabre o popup",
           u"aoErro: function(m){" in vr and u"ltEscolha(); msg('ERRO: '" in vr)
    checar(u"  só o sucesso fecha sozinho: o check, a confirmação e depois o popup "
           u"fecha", u"ler.pronto(" in fim and u"LT_CONFIRMACAO_MS" in fim
           and fim.index(u"ler.pronto(") > fim.index(u"if(!series.length)"))
    checar(u"  fechar o popup no meio para a leitura (e o que achou vai para a tela)",
           u"uiPopupSerie('cx1', {aoFechar: _ltAoFecharPopup," in js
           and u"ltParar()" in _funcao(js, u"_ltAoFecharPopup"))
    checar(u"  e reabrir o popup mostra o formulário e conta a abertura (o "
           u"fechamento automático da confirmação não leva o reaberto)",
           u"aoAbrir: function(){ _ltAoAbrirPopup() }" in js
           and u"_ltModo(false)" in _funcao(js, u"_ltAoAbrirPopup")
           and u"LT_ABERTURAS === vez" in fim)
    checar(u"  e quem chega com séries (a ficha, a lista guardada na aba) não vê o popup",
           u"uiPopupSerie('cx1', {sozinho: function(){ return !LT_CHEGOU_COM_SERIES }})" in js
           and js.count(u"LT_CHEGOU_COM_SERIES = true;") == 2)
    i2 = p.index(u'id="cx2"')
    checar(u"R13: o gancho do autor, depois do passo 2",
           p.index(GANCHO) > i2 and u"Terminou de processar?" in vis
           and u'href="/ver"' in p and u'href="/recon3d"' in p)


def teste_a_coluna_serie():
    secao(u"R24: a coluna «Série» é a miniatura, e o duplo clique abre o visor")
    js = _sem_comentario(_js(_pagina()))
    linha = _funcao(js, u"linhaDaSerie")
    checar(u"a célula da série é a miniatura (`celulaSerie`)",
           u"celulaSerie(i)" in linha and u"esc(s.curto)+'</td>'" not in linha)
    cel = _funcao(js, u"celulaSerie")
    checar(u"  pela rota do bilhete, sem caminho na URL",
           u"/api/lote/miniatura?b=" in cel and u"s.pasta" not in cel)
    vis = _funcao(js, u"abrirVisorDaSerie")
    checar(u"  e o visor modal é o `uiVisor`, com o cabeçalho e as janelas",
           u"window.uiVisor(" in vis and u"cabecalho" in vis
           and u"/api/lote/corte?b=" in vis)
    checar(u"  o duplo clique e o Enter abrem", u"'dblclick'" in js
           and u"abrirVisorDaSerie(parseInt" in js)
    checar(u"  a roda vai para caudal: o visor recebe o sentido da série "
           u"(cranial), e sem ele pergunta ao servidor por bilhete",
           u"cranial: s.cranial" in vis and u"'/api/lote/sentido'" in vis
           and u"JSON.stringify({b: s.b})" in vis
           and u"v.definirSentido(d.cranial)" in vis, vis[-400:])
    import radai_batch as L
    import radai_thumbnail as T
    bs = T.registrar_series(u"X:\\fantoma_do_sentido", [
        {"uid": u"9.9.1", "arquivos": [{"ipp": [0.0, 0.0, z]}
                                       for z in (0.0, 2.5, 5.0)]},
        {"uid": u"9.9.2", "arquivos": [{"ipp": [0.0, 0.0, z]}
                                       for z in (5.0, 2.5, 0.0)]}])

    def medir(f):
        return (f(bs[u"9.9.1"]), f(bs[u"9.9.2"]), f(u"0" * 32))
    checar(u"  o sentido por bilhete: cabeça primeiro 1, pés primeiro -1, "
           u"bilhete desconhecido 0", medir(L.sentido_do_bilhete) == (1, -1, 0),
           str(medir(L.sentido_do_bilhete)))
    checar(u"  (isca) o sentido que não lê a série (sempre 0) reprova",
           medir(lambda b: 0) != (1, -1, 0))


def teste_a_fronteira_no_iniciar():
    secao(u"R14: a frase UNAPPROVED no diálogo do INICIAR, logo antes do botão")
    import radai_review as R

    def medir(htm):
        m = re.search(r'<p class="rc-fronteira" id="radai_rev_fronteira"[^>]*>(.*?)</p>\s*'
                      r'<div class="rev-bt">\s*<button class="pri" id="radai_rev_ok"[^>]*>'
                      r'([^<]*)</button>', htm, re.S)
        return bool(m) and _visivel(m.group(1)) == FRONTEIRA \
            and m.group(2) == u"Começar a segmentar a fila agora"
    p = _pagina()
    checar(u"a tag está na marcação do diálogo, imediatamente antes do botão",
           medir(p))
    isca = p.replace(u'<p class="rc-fronteira" id="radai_rev_fronteira"',
                     u'<p class="x" id="radai_rev_fronteira"', 1)
    checar(u"  (isca) sem a tag no lugar, reprova", not medir(isca))
    checar(u"  e a frase velha saiu", u"Toda estrutura sai como SUGESTÃO" not in p
           and R.montar([], tasks=("total_v3",))["aviso"] == FRONTEIRA)
    css = R.CSS
    checar(u"  a tag não tem «não mostrar de novo» nem se esconde",
           u"não mostrar" not in p and u".rc-fronteira{display:none" not in css)
    import radai_batch as L
    corpo = L._corpo_da_folha_do_turno()
    checar(u"o modal do Overnight Run leva a mesma frase", FRONTEIRA in _visivel(
        corpo.replace(u"<template", u"<div").replace(u"</template>", u"</div>")))


def teste_a_folha_do_turno():
    secao(u"R18/R19: sem a caixa dos serviços, o STATUS_DIR na folha, e só dois botões")
    import radai_batch as L
    c = L._corpo_da_folha_do_turno()
    checar(u"a caixa de pausar serviços e o «?» dela saíram",
           u"ov-escolha" not in c and u'id="ov_pausar"' not in c
           and u"ov_balao" not in c and u"SysMain" not in c
           and u"Nunca tocados" not in c)
    aviso = re.search(r'<p class="ov-frota-aviso" id="ov_frota_aviso" hidden '
                      r'data-radai-frase>(.*?)</p><div class="ov-frota"', c, re.S)
    checar(u"  o aviso do STATUS_DIR fica logo acima da frota, oculto até a "
           u"frota responder", bool(aviso)
           and u"Sem STATUS_DIR em Configurações" in aviso.group(1), c[-400:])
    js = _sem_comentario(_js(_pagina()))
    checar(u"R19: o «Iniciar sem salvar» saiu da folha",
           u"ov_bt_sem" not in js and u"Iniciar sem salvar" not in js
           and u"_ovTemporarios" not in js)
    checar(u"  e a folha só tem «Cancelar» e «Salvar e incluir na fila»",
           u"ok: 'Salvar e incluir na fila'" in js and u"cancelar: 'Cancelar'" in js)


def teste_o_personalizado():
    secao(u"P1, P2, P6, a «Seleção livre» e a comparação sem os «em breve»")
    import radai_batch as L
    import radai_models as M
    o = L.opcoes_da_tela("CT")
    rot = dict((c["cod"], c["rotulo"]) for c in o.get("categorias") or ())
    checar(u"P1/P2: as duas categorias da coluna 1",
           rot.get("rt") == u"PROTOCOLOS RT"
           and rot.get("reconstrucoes_3d") == u"PROTOCOLOS RECONSTRUÇÕES 3D")
    cods = [p["cod"] for p in o.get("protocolos_3d") or ()]
    checar(u"  com a Anatomia Geral e a Anatomia Torácica",
           cods == ["anatomia_geral", "anatomia_toracica"], str(cods))
    js = _sem_comentario(_js(_pagina()))
    checar(u"  e a frase «Ligar um protocolo…» saiu",
           u"Ligar um protocolo liga" not in js)
    checar(u"P6: «não se desmarca» saiu da linha", u"não se desmarca" not in js)
    checar(u"  e o porquê mora no «?» da base",
           len(o["base_item"].get("por_que_travada") or u"") > 40
           and u"t.por_que_travada" in _funcao(js, u"_fichaHTML"))
    painel = _funcao(js, u"painelPerso")
    checar(u"os «em breve» (HN-OAR e TLI) saíram da terceira coluna",
           "em_breve" not in o and u"ui-breve" not in painel
           and u"em_breve" not in painel and u"'breve'" not in js)
    checar(u"  e o registro deles saiu do código, com a regra do CSS deles",
           not hasattr(M, "em_breve") and u".p4-breve" not in _pagina())
    frase = u"Cada modelo grava um arquivo próprio; nenhum entra no RadAI_STUDY."
    ajuda = _funcao(js, u"_ajudaDoPainel")
    comp = ajuda[ajuda.index(u"if(tipo === 'comp')"):]
    checar(u"o aviso «Cada modelo grava…» mora no «?» de cada modelo",
           frase in comp and frase not in painel and u"p4-nota" not in painel)
    checar(u"a «Seleção livre» fica na primeira coluna, abaixo dos protocolos 3D",
           u"p4-livre-ck" in painel and painel.index(u"p4-livre-ck")
           > painel.index(u"p4-p3d-ck")
           and painel.index(u"p4-livre-ck") < painel.index(u"p4-tasks"))
    checar(u"  e nasce desligada", u"livre:false" in _funcao(js, u"escolhaDe"))
    pay = _funcao(js, u"payloadDaSerie")
    checar(u"o payload leva os protocolos 3D", u"protocolos3dLigados(s, e)" in pay)
    checar(u"  e ligar um protocolo 3D zera a comparação",
           u"e.comp = {}" in _funcao(js, u"ligarProtocolo3d"))
    s = {"modo": "perso", "modalidade": "CT", "uid": "1.2.3.4.5.6",
         "date": "20260101", "protocolos_3d": ["anatomia_toracica"]}
    arq = [a["cod"] for a in L.arquivos_da_escolha(s, ())]
    checar(u"a prévia da entrega mostra o mapa de rótulos do estudo 3D",
           "rotulos" in arq, str(arq))
    s.pop("protocolos_3d")
    checar(u"  (isca) sem protocolo 3D, nenhum mapa",
           "rotulos" not in [a["cod"] for a in L.arquivos_da_escolha(s, ())])
    s3 = {"modo": "perso", "modalidade": "CT", "uid": "1.2.3.4.5.6",
          "date": "20260101"}
    sem = L.previa_da_entrega(dict(s3))
    com = L.previa_da_entrega(dict(s3, protocolos_3d=["anatomia_toracica"]))
    n_sem = len(sem["oar"]["estruturas"])
    n_com = len(com["oar"]["estruturas"])
    checar(u"o estudo 3D não muda o OAR da prévia (as tasks dele vão ao mapa)",
           n_sem == n_com, u"%d vs %d" % (n_sem, n_com))
    t, _m, modos, _p = L.conferencia_das_series([dict(s3, protocolos_3d=["anatomia_toracica"])])
    import radai_review as R
    cj = [c["cod"] for c in R.montar([s3], tasks=t, estudos=modos)["conjuntos"]]
    checar(u"a conferência do INICIAR anuncia o mapa e nenhum plugin só do estudo",
           "rotulos" in cj and u"perso3d:anatomia_toracica" in modos
           and not any(c in cj for c in ("nod", "lvs", "lvl", "vbd")), str(cj))
    vis = json.dumps(o, ensure_ascii=False)
    checar(u"nenhum texto do PERSONALIZADO cita TPS (V13)", u"TPS" not in vis)


def _app_de_teste():
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
    import radai_batch as L
    app = FastAPI()
    L.montar(app, {"tasks": ["total_v3"], "device": "cpu", "min_cortes": 5})
    return TestClient(app)


def _fantoma(raiz):
    from datetime import datetime, timedelta
    from make_test_series import escreve_serie
    for nome, dias, cortes in (("PAC_A", 1, 12), ("PAC_B", 2, 10)):
        escreve_serie(os.path.join(raiz, nome, "CT"), nome,
                      datetime.now() - timedelta(days=dias), cortes)


def _varrer_pela_casca(pasta, uso="lote"):
    import radai_varrer
    d = radai_varrer.iniciar(uso, pasta, dias=0, em_segundo_plano=False)
    fora = dict(d.get("extra") or {})
    fora["series"] = list(d.get("linhas") or [])
    if d.get("erro"):
        fora["erro"] = d["erro"]
    return fora


def teste_as_rotas():
    secao(u"E11/E12 e R24: a seleção por ficha, a miniatura e o corte")
    import radai_batch as L
    tmp = tempfile.mkdtemp(prefix="radai_rodar_")
    _fantoma(os.path.join(tmp, "share"))
    cli = _app_de_teste()
    v = _varrer_pela_casca(os.path.join(tmp, "share"))
    ss = v.get("series") or []
    checar(u"a varredura devolve as séries com o bilhete `b`",
           len(ss) == 2 and all(s.get("b") for s in ss), str(len(ss)))
    if not ss:
        return
    alvo = [s for s in ss if s.get("pid") == "PAC_B"] or ss[:1]
    alvo = alvo[0]
    r = cli.get("/api/lote/miniatura", params={"b": alvo["b"]})
    checar(u"a miniatura é um PNG", r.status_code == 200
           and r.content[:8] == b"\x89PNG\r\n\x1a\n", str(r.status_code))
    r = cli.get("/api/lote/corte", params={"b": alvo["b"], "corte": 3,
                                            "janela": "pulmao"})
    checar(u"o corte do visor é um PNG", r.status_code == 200
           and r.content[:4] == b"\x89PNG", str(r.status_code))
    r = cli.get("/api/lote/corte", params={"b": "x" * 32, "corte": 0})
    checar(u"  bilhete desconhecido dá 404", r.status_code == 404, str(r.status_code))
    sen = cli.post("/api/lote/sentido", json={"b": alvo["b"]}).json()
    nada = cli.post("/api/lote/sentido", json={"b": "x" * 32}).json()
    lixo = cli.post("/api/lote/sentido", content=b"{").json()
    checar(u"POST /api/lote/sentido: o fantoma HFS com o z subindo é 1, e o "
           u"bilhete desconhecido ou o corpo ruim, 0",
           sen == {"cranial": 1} and nada == {"cranial": 0}
           and lixo == {"cranial": 0}, json.dumps([sen, nada, lixo]))
    sel = cli.post("/api/lote/selecao", json={"series": [
        {"pasta": alvo["pasta"], "uid": alvo["uid"]},
        {"pasta": alvo["pasta"], "uid": alvo["uid"]}, {"pasta": "", "uid": "x"},
        "lixo"]}).json()
    checar(u"POST /api/lote/selecao devolve a ficha (sem caminho)",
           sel.get("ok") and sel.get("n") == 1 and "\\" not in sel.get("ficha", "")
           and alvo["uid"] not in sel.get("ficha", ""), json.dumps(sel)[:200])
    ab = cli.post("/api/lote/selecao/abrir", json={"ficha": sel.get("ficha")}).json()
    got = ab.get("series") or []
    checar(u"  e a ficha abre só as séries pedidas",
           ab.get("ok") and len(got) == 1 and got[0]["uid"] == alvo["uid"]
           and got[0].get("b"), json.dumps(ab, ensure_ascii=False)[:200])
    ruim = cli.post("/api/lote/selecao/abrir", json={"ficha": "naoexiste"}).json()
    checar(u"  ficha desconhecida: ok falso, com o motivo",
           ruim.get("ok") is False and ruim.get("erro"))
    vazio = cli.post("/api/lote/selecao", json={"series": []}).json()
    checar(u"  seleção vazia é recusada", vazio.get("ok") is False)
    checar(u"  (isca) UID trocado não casa nada", L.series_da_selecao(
        [{"pasta": alvo["pasta"], "uid": "9.9.9"}], ss) == [])
    import radai_fichas
    f = radai_fichas.guardar({"tipo": "outra_coisa", "series": [
        {"pasta": alvo["pasta"], "uid": alvo["uid"]}]})
    checar(u"  ficha de outro tipo não abre", cli.post(
        "/api/lote/selecao/abrir", json={"ficha": f}).json().get("ok") is False)


def teste_a_demo():
    secao(u"a demo saiu do Rodar agora (o autor a abandonou)")
    import ast
    import radai_batch as L
    fonte = io.open(L.__file__, encoding="utf-8").read()
    checar(u"o lote nao usa mais o modulo da demo",
           u"radai_demo" not in fonte)
    rotas = [n.args[0].value for n in ast.walk(ast.parse(fonte))
             if isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "get"
             and n.args and isinstance(n.args[0], ast.Constant)]
    checar(u"  nem serve a rota da demo", u"/api/lote/demos" not in rotas)
    js = _sem_comentario(_js(_pagina()))
    checar(u"  e a tela nao tem a linha DEMO", u"_demosCarregar" not in js
           and u"demo-tag" not in js and u"lote_demos" not in _pagina())


def teste_a_barra_abre_ao_por_na_fila():
    secao(u"R26: pôr na fila abre a barra da direita na aba da fila")
    js = _sem_comentario(_js(_pagina()))
    env = _funcao(js, u"mandarParaAFila")
    checar(u"o envio bem-sucedido chama `_abrirAFila`", u"_abrirAFila()" in env)
    ab = _funcao(js, u"_abrirAFila")

    def _abre_pela_casca(corpo, pagina):
        return (u"radaiTfAbrirAba('fila')" in corpo
                and u"radai_dir_recolhido" not in pagina)
    checar(u"  que abre a aba da fila pela casca (que expande a barra), sem "
           u"gravar no navegador a chave que ninguém lê",
           _abre_pela_casca(ab, js))
    velho = (u"function _abrirAFila(){\n try{ localStorage.setItem("
             u"'radai_dir_recolhido', '0') }catch(e){}\n "
             u"radaiTfAbrirAba('fila');\n}")
    checar(u"  ISCA: o corpo de antes, com a chave morta, reprova",
           not _abre_pela_casca(velho, velho))


FRASES_NOVAS = None


def teste_as_frases_tem_os_doze_idiomas():
    secao(u"toda frase nova da trilha nos doze idiomas")
    import radai_phrases as P
    import radai_batch as L
    import radai_review as R
    import radai_models as M
    import radai_modes as MD
    linhas = dict((P.normalizar(l[0]), l) for l in P.TABELA)
    fr = [L.FRASE_DA_TELA] + list(L.AJUDA_DA_TELA) + [
        CARD_ADD, u"Carregar imagens", u"Caminho — pasta, ou o .zip do exame",
        u"Varrendo a pasta: o cabeçalho de cada arquivo é lido, e uma pasta "
        u"grande pode levar alguns minutos.",
        u"Séries selecionadas", u"%s série(s) nesta lista", u"Adicionar as selecionadas à fila",
        u"Selecionar todas as séries", u"Nenhuma série no carrinho — selecione na tabela acima.",
        u"selecionar para processar", u"selecionada", u"Parar a leitura",
        u"Lendo os cabeçalhos dos arquivos…", u"Procurando séries nas subpastas…",
        u"Conferindo as séries achadas…", u"Ler todas as datas",
        u"%s pasta(s) ficaram fora do filtro de data.", u"%s pasta(s) olhada(s)",
        u"%s arquivo(s) lido(s)", u"%s série(s) achada(s)",
        u"%s série(s) no carrinho, de %s pastas", u"%s série(s) no carrinho",
        GANCHO, u"duplo clique abre a série", u"cortes", u"PROTOCOLOS RT",
        u"PROTOCOLOS RECONSTRUÇÕES 3D", L.POR_QUE_A_BASE_RODA_SEMPRE,
        L.ROTULO_DO_MAPA_3D, R.FRASE_DA_FRONTEIRA, R.ROTULO_DO_INICIAR,
        u"a seleção não está mais disponível — escolha as séries de novo no DicomBridge",
        u"%s série(s) da seleção não foram achadas", L.AVISO_SEM_STATUS_DIR,
        u"a fila está vazia — use «Adicionar as selecionadas à fila»", ALERTA]
    for mod in ("CT", "MR"):
        for p in MD.protocolos_3d_de(mod):
            fr += [p["rotulo"], p["ajuda"]]
    falta = []
    for f in dict.fromkeys(fr):
        l = linhas.get(P.normalizar(f))
        sem = [c for i, c in enumerate(P.CODIGOS, start=1)
               if not l or i >= len(l) or not P.normalizar(l[i])]
        if sem:
            falta.append(u"%s (%s)" % (f[:50], u",".join(sem)))
    checar(u"%d frases, todas com as onze traduções" % len(set(fr)), not falta,
           u" | ".join(falta[:6]))


def _chromium():
    base = os.path.join(os.environ.get("LOCALAPPDATA", ""), "ms-playwright")
    if not os.path.isdir(base):
        return None
    for nome in sorted(os.listdir(base), reverse=True):
        if not nome.startswith("chromium-"):
            continue
        for sub in ("chrome-win64", "chrome-win"):
            exe = os.path.join(base, nome, sub, "chrome.exe")
            if os.path.isfile(exe):
                return exe
    return None


def _subir(tmp):
    from datetime import datetime, timedelta
    from make_test_series import escreve_serie
    root = os.path.join(tmp, "share")
    for nome, dias, cortes in (("PAC_A", 1, 30), ("PAC_B", 2, 28), ("PAC_C", 3, 26)):
        escreve_serie(os.path.join(root, nome, "CT"), nome,
                      datetime.now() - timedelta(days=dias), cortes)
    calib = os.path.join(tmp, "calib")
    cfg = os.path.join(tmp, "t.config")
    io.open(cfg, "w", encoding="utf-8").write(
        u"ROOT=%s\nDRY_RUN=1\nMIN_SLICES=5\nQUIET_MIN=0\nTPS_DESTINO=eclipse\n"
        u"PORT=%d\nLOG_DIR=%s\nPASTA_FAVORITA=%s\n"
        % (root, PORTA, os.path.join(tmp, "log"), root))
    env = dict(os.environ, RADAI_CONFIG=cfg, RADAI_MACHINE="BATERIA_RODAR",
               RADAI_CALIB_DIR=calib, RADAI_REGISTRO_DIR=os.path.join(tmp, "reg"),
               LOCALAPPDATA=os.path.join(tmp, "ad"), RADAI_NOTIFICACAO="0",
               RADAI_URL_VERSOES="0", PYTHONIOENCODING="utf-8:replace")
    env["RADAI_FILA_DIR"] = os.path.join(tmp, "fila")
    velho = os.environ.get("RADAI_CALIB_DIR")
    os.environ["RADAI_CALIB_DIR"] = calib
    try:
        import radai_consent
        radai_consent.registrar_aceite(u"bateria do Rodar agora")
    finally:
        os.environ["RADAI_CALIB_DIR"] = velho
    saida = io.open(os.path.join(tmp, "vigia.log"), "wb")
    proc = subprocess.Popen([sys.executable, _componentes.fonte("app/radai_watcher.py")],
                            env=env, stdout=saida, stderr=subprocess.STDOUT)
    for _ in range(90):
        try:
            urllib.request.urlopen(BASE + "/api/fila", timeout=2).read()
            return proc, root
        except Exception:
            time.sleep(1)
    proc.kill()
    return None, root


async def _navegar(exe, root, prints):
    from playwright.async_api import async_playwright
    async with async_playwright() as pw:
        nav = await pw.chromium.launch(executable_path=exe, headless=True)
        try:
            ctx = await nav.new_context(viewport={"width": 1280, "height": 900})
            pg = await ctx.new_page()
            erros = []
            pg.on("pageerror", lambda e: erros.append(str(e)))
            await pg.goto(BASE + "/aceite", wait_until="domcontentloaded")
            await pg.evaluate("localStorage.setItem('radai_idioma', 'pt-BR')")
            await pg.goto(BASE + "/lote", wait_until="networkidle")
            await pg.wait_for_timeout(700)
            est = await pg.evaluate("""() => ({
              c1: !!document.getElementById('cx1').closest('.ui-modal-veu.vis'),
              c2: document.getElementById('cx2').classList.contains('fechado')})""")
            checar(u"[tela] abre sem erro de JavaScript", not erros, u" | ".join(erros[:3]))
            checar(u"[tela] R6: ao carregar, o popup do passo 1 já aparece, e o 2 nasce "
                   u"recolhido", est["c1"] and est["c2"], json.dumps(est))
            await pg.keyboard.press("Escape")
            await pg.wait_for_timeout(400)
            await pg.click("#cd_add")
            await pg.wait_for_timeout(400)
            est = await pg.evaluate("""() => ({
              c1: !!document.getElementById('cx1').closest('.ui-modal-veu.vis'),
              c2: document.getElementById('cx2').classList.contains('fechado'),
              v: document.getElementById('pasta').value})""")
            checar(u"[tela] R7/R15: «Adicionar novas séries» reabre o popup do 1, recolhe o 2 "
                   u"e põe a favorita",
                   est["c1"] and est["c2"] and est["v"] == root, json.dumps(est))
            geo = await pg.evaluate("""() => {
              const r = e => e.getBoundingClientRect();
              const i = r(document.getElementById('pasta'));
              const b = [...document.querySelectorAll('.cam-linha button')].map(r);
              return b.map(x => Math.abs((x.top + x.height/2) - (i.top + i.height/2)));
            }""")
            checar(u"[tela] R10: os botões alinhados ao centro do campo",
                   geo and max(geo) <= 2.5, str(geo))
            vazia = os.path.join(os.path.dirname(root), "pasta_vazia")
            os.makedirs(vazia, exist_ok=True)
            await pg.fill("#pasta", vazia)
            await pg.click(".cam-linha button.pri")
            await pg.wait_for_timeout(2500)
            est = await pg.evaluate("""() => ({
              c1: !!document.getElementById('cx1').closest('.ui-modal-veu.vis'),
              msg: (document.getElementById('msg').textContent || '').trim(),
              achou: (document.getElementById('lt_achou').textContent || '').trim()})""")
            checar(u"[tela] a varredura sem série deixa o popup aberto e diz que não "
                   u"achou", est["c1"] and est["msg"] == u"Nenhuma série nesta pasta."
                   and not est["achou"], json.dumps(est, ensure_ascii=False))
            await pg.fill("#pasta", root)
            await pg.click(".cam-linha button.pri")
            await pg.wait_for_timeout(120)
            lendo = await pg.evaluate("""() => ({
              form: document.getElementById('lt_form').hidden,
              ler: !!document.querySelector('#lt_ler_cx .ui-ler .ui-pensa-linha'),
              c1: !!document.getElementById('cx1').closest('.ui-modal-veu.vis')})""")
            checar(u"[tela] depois de «Varrer séries» o popup não volta ao formulário: "
                   u"mostra a leitura (thinking-states sobre o fundo orgânico)",
                   lendo["form"] and lendo["ler"] and lendo["c1"], json.dumps(lendo))
            await pg.wait_for_selector("#lt_ler_cx .ui-certo.on", timeout=30000)
            pronto = await pg.evaluate("""() => ({
              c1: !!document.getElementById('cx1').closest('.ui-modal-veu.vis'),
              linha: (document.querySelector('#lt_ler_cx .ui-pensa-linha') || {}).textContent || ''})""")
            await pg.wait_for_timeout(950)
            linha = await pg.evaluate(
                "(document.querySelector('#lt_ler_cx .ui-pensa-linha') || {}).textContent || ''")
            checar(u"[tela]   ao terminar, o check aparece com o popup ainda aberto e a "
                   u"linha troca para a confirmação",
                   pronto["c1"] and linha.startswith(u"3 "), json.dumps([pronto, linha],
                                                                    ensure_ascii=False))
            await pg.wait_for_function(
                "!document.getElementById('cx1').closest('.ui-modal-veu.vis')", timeout=8000)
            await pg.wait_for_selector("#tab .mini-serie img", timeout=30000)
            await pg.wait_for_timeout(1500)
            n = await pg.evaluate("document.querySelectorAll('#tab tr[id^=linha_]').length")
            checar(u"[tela] a varredura lista as três séries", n == 3, str(n))
            est = await pg.evaluate("""() => ({
              c1: !!document.getElementById('cx1').closest('.ui-modal-veu.vis'),
              c2: document.getElementById('cx2').classList.contains('fechado')})""")
            checar(u"[tela]   e a escolha chega ao passo 2: o popup fecha e o 2 abre",
                   not est["c1"] and not est["c2"], json.dumps(est))
            conta = await pg.evaluate("""() => {
              const c = document.querySelector('#lt_achou .lt-conta');
              if(!c) return null;
              const r = c.getBoundingClientRect();
              return {t: c.textContent.trim(), h: r.height,
                      noPopup: !!c.closest('#cx1')};
            }""")
            checar(u"[tela]   e a contagem aparece na tela de trabalho, fora do popup",
                   conta and conta["t"].startswith(u"3 ") and conta["h"] > 0
                   and not conta["noPopup"], json.dumps(conta, ensure_ascii=False))
            _REABRIR = """async (isca) => {
               if(isca) _ltAoAbrirPopup = function(){};
               ltEscolha(); varrer();
               for(let i = 0; i < 300; i++){
                if(document.querySelector('#lt_ler_cx .ui-certo.on')) break;
                await new Promise(r => setTimeout(r, 100)) }
               uiPopupSerie('cx1').fechar();
               await new Promise(r => setTimeout(r, 120));
               ltEscolha();
               await new Promise(r => setTimeout(r, 2600));
               const r = {c1: !!document.getElementById('cx1').closest('.ui-modal-veu.vis'),
                          form: !document.getElementById('lt_form').hidden};
               uiPopupSerie('cx1').fechar();
               return r; }"""
            reab = await pg.evaluate(_REABRIR, False)
            await pg.wait_for_timeout(500)
            checar(u"[tela] o popup reaberto durante a confirmação fica aberto, no "
                   u"formulário, e não fecha sozinho", reab["c1"] and reab["form"],
                   json.dumps(reab))
            reab_i = await pg.evaluate(_REABRIR, True)
            await pg.wait_for_timeout(500)
            checar(u"[tela]   (isca) sem contar as aberturas, o fechamento atrasado "
                   u"levaria o popup reaberto", not (reab_i["c1"] and reab_i["form"]),
                   json.dumps(reab_i))
            await pg.reload(wait_until="networkidle")
            await pg.wait_for_timeout(1200)
            await pg.evaluate("(r) => { ltEscolha(); document.getElementById('pasta').value = r;"
                              " varrer(); return true }", root)
            await pg.wait_for_function(
                "!document.getElementById('cx1').closest('.ui-modal-veu.vis')", timeout=30000)
            await pg.wait_for_selector("#tab .mini-serie img", timeout=30000)
            await pg.wait_for_timeout(1500)
            larg = await pg.evaluate(
                "document.querySelector('#tab .mini-serie img').naturalWidth")
            checar(u"[tela] R24: a miniatura carregou", larg and larg > 0, str(larg))
            if prints:
                await _prints(pg, prints, u"lista")
            await pg.dblclick("#tab .mini-serie")
            await pg.wait_for_selector(".ui-modal .ui-visor", timeout=10000)
            await pg.wait_for_timeout(800)
            ini = await pg.text_content(".ui-visor-pos")
            cab = await pg.text_content(".ui-visor-cab")
            await pg.hover(".ui-visor-img")
            await pg.mouse.wheel(0, 120)
            await pg.wait_for_timeout(400)
            dep = await pg.text_content(".ui-visor-pos")
            checar(u"[tela] R24: o duplo clique abre o visor modal com o cabeçalho",
                   u"Cortes" in (cab or u"") and u"Paciente" in (cab or u""), cab)
            checar(u"[tela]   e a roda troca o corte", ini != dep, u"%s → %s" % (ini, dep))

            def _n(t):
                m = re.match(r"\s*(\d+)\s*/", t or u"")
                return int(m.group(1)) if m else None
            checar(u"[tela]   a roda para baixo vai para caudal (o fantoma HFS "
                   u"tem o z subindo com o índice: o índice desce)",
                   _n(ini) is not None and _n(dep) == _n(ini) - 1,
                   u"%s → %s" % (ini, dep))
            if prints:
                await _prints(pg, prints, u"visor", so_um=True)
            await pg.keyboard.press("Escape")
            await pg.wait_for_timeout(400)
            await pg.click("#cartesv")
            await pg.wait_for_timeout(300)
            dlg = await pg.evaluate(
                "!!document.querySelector('.ui-pnl-veu') && getComputedStyle(document.querySelector('.ui-pnl-veu')).display !== 'none' && document.querySelector('.ui-pnl-veu').classList.contains('vis')")
            nc = await pg.evaluate("carrinhoLista().length")
            checar(u"[tela] R12: «Esvaziar seleção» esvazia sem diálogo", nc == 0 and not dlg,
                   u"carrinho=%s dialogo=%s" % (nc, dlg))
            await pg.click("#cartsel")
            await pg.wait_for_timeout(300)
            nc = await pg.evaluate("carrinhoLista().length")
            checar(u"[tela] R12: «Selecionar todas as séries» põe as três", nc == 3, str(nc))
            await pg.evaluate("""() => { const s = document.querySelector('#tab select.md-sel');
               s.value = 'perso'; s.dispatchEvent(new Event('change', {bubbles:true})); }""")
            await pg.wait_for_selector("tr.perso .p4", timeout=10000)
            await pg.wait_for_timeout(600)
            p4 = await pg.evaluate("""() => {
              const p = document.querySelector('tr.perso .p4');
              const hs = [...p.querySelectorAll('.p4-prot h4')].map(h => h.textContent.trim());
              const br = [...p.querySelectorAll('.ui-breve')];
              return {hs, nbr: br.length,
                      livre: p.querySelectorAll('input.p4-livre-ck').length,
                      trava: p.textContent.includes('não se desmarca'),
                      p3d: p.querySelectorAll('input.p4-p3d-ck').length,
                      nota: !!p.querySelector('.p4-rt3d')};
            }""")
            checar(u"[tela] P1/P2: «PROTOCOLOS RT» e «PROTOCOLOS RECONSTRUÇÕES 3D»",
                   p4["hs"] == [u"PROTOCOLOS RT", u"PROTOCOLOS RECONSTRUÇÕES 3D"]
                   and p4["p3d"] == 2, json.dumps(p4, ensure_ascii=False))
            checar(u"[tela] os «em breve» não aparecem mais, e a «Seleção livre» sim",
                   p4["nbr"] == 0 and p4["livre"] == 1,
                   json.dumps(p4, ensure_ascii=False))
            checar(u"[tela] P6: «não se desmarca» não aparece", not p4["trava"])
            await pg.evaluate("""() => { const x = document.querySelector('tr.perso input.p4-comp-ck[data-comp=ts]');
               x.checked = true; x.dispatchEvent(new Event('change', {bubbles:true})); }""")
            await pg.evaluate("""() => { const x = document.querySelector('tr.perso input.p4-p3d-ck[data-p3d=anatomia_toracica]');
               x.checked = true; x.dispatchEvent(new Event('change', {bubbles:true})); }""")
            await pg.wait_for_timeout(500)
            pay = json.loads(await pg.evaluate("JSON.stringify(payloadDaSerie(SERIES[0]))"))
            checar(u"[tela] o protocolo 3D viaja, e zera a comparação",
                   pay.get("protocolos_3d") == ["anatomia_toracica"]
                   and not any((pay.get("comparacao") or {}).values()),
                   json.dumps({k: pay.get(k) for k in ("protocolos_3d", "comparacao")}))
            nota = await pg.evaluate("""() => { const n = document.querySelector('tr.perso .p4-rt3d');
               return {vis: !!(n && n.offsetParent), t: n ? n.textContent : ''}; }""")
            checar(u"[tela] com o protocolo 3D ligado, a tela diz que o RTSTRUCT "
                   u"sai só com o que está ligado nas colunas de RT",
                   p4["nota"] is False and nota["vis"]
                   and u"o RTSTRUCT sai só com o que estiver ligado nas colunas "
                       u"de RT" in nota["t"], json.dumps(nota, ensure_ascii=False))
            await pg.click("tr.perso .p4-ln .tk-aj[data-p4-aj=task]")
            await pg.wait_for_timeout(500)
            tr = await pg.evaluate("(document.querySelector('.ui-pnl .tk-trava')||{}).textContent || ''")
            checar(u"[tela] P6: o «?» da base diz por que ela não se desliga",
                   u"A base roda em toda série" in tr, tr[:80])
            if prints:
                await _prints(pg, prints, u"personalizado_ficha_da_base", so_um=True)
            await pg.keyboard.press("Escape")
            await pg.wait_for_timeout(300)
            if prints:
                await pg.evaluate("document.querySelector('tr.perso').scrollIntoView({block:'center'})")
                await _prints(pg, prints, u"personalizado")
            await pg.evaluate("uiDireita('1')")
            await pg.click("#btrodar")
            await pg.wait_for_timeout(1500)
            rec = await pg.evaluate("document.documentElement.classList.contains('dir-recolhida')")
            aba = await pg.evaluate(
                "(document.querySelector('#radai_tf_ab_fila')||{}).getAttribute && document.querySelector('#radai_tf_ab_fila').getAttribute('aria-selected')")
            checar(u"[tela] R26: pôr na fila abre a barra, na aba da fila",
                   rec is False and aba == "true", u"recolhida=%s aba=%s" % (rec, aba))
            await pg.wait_for_selector("#radai_fila .cd .ui-mais", timeout=15000)
            await pg.click("#radai_fila .cd .ui-mais")
            await pg.wait_for_timeout(600)
            mf = await pg.evaluate("""() => { const m = document.querySelector('.ui-morfo.aberto');
               const b = document.querySelector('#radai_fila .cd .ui-mais');
               return {aberto: !!m, txt: m ? m.textContent : '',
                       exp: b.getAttribute('aria-expanded')}; }""")
            checar(u"[tela] R17: o «+» do card da fila abre o pedido (morph), sem caminho",
                   mf["aberto"] and mf["exp"] == "true" and u"Modo" in mf["txt"]
                   and u"\\" not in mf["txt"] and u"share" not in mf["txt"],
                   json.dumps(mf, ensure_ascii=False)[:200])
            if prints:
                await _prints(pg, prints, u"fila_detalhe", so_um=True)
            carga = await pg.evaluate("""() => {
               const b0 = document.querySelector('#radai_fila .cd .ui-mais');
               radaiFilaPintar(window.RADAI_FILA_D);
               const b1 = document.querySelector('#radai_fila .cd .ui-mais');
               return {mesmo: b0 === b1, exp: b1 && b1.getAttribute('aria-expanded'),
                       aberto: !!document.querySelector('.ui-morfo.aberto')}; }""")
            checar(u"[tela] R17: uma carga da fila com o «+» aberto mantém o "
                   u"botão aberto e o painel no lugar",
                   carga["mesmo"] and carga["exp"] == "true" and carga["aberto"],
                   json.dumps(carga))
            isca = await pg.evaluate("""() => {
               const velho = radaiFilaManterDetalhe;
               try{
                radaiFilaManterDetalhe = function(){};
                radaiFilaPintar(window.RADAI_FILA_D);
                const b = document.querySelector('#radai_fila .cd .ui-mais');
                return {exp: b && b.getAttribute('aria-expanded'),
                        aberto: !!document.querySelector('.ui-morfo.aberto')};
               } finally { radaiFilaManterDetalhe = velho; } }""")
            checar(u"[tela] ISCA: sem o conserto, a carga recria o «+» fechado "
                   u"com o painel aberto (a corrida do R17 reproduzida)",
                   isca["exp"] == "false" and isca["aberto"], json.dumps(isca))
            await pg.keyboard.press("Escape")
            await pg.wait_for_timeout(350)
            await pg.click("#radai_fila .cd .ui-mais")
            await pg.wait_for_timeout(500)
            sumiu = await pg.evaluate("""() => {
               const D = window.RADAI_FILA_D;
               const antes = !!document.querySelector('.ui-morfo.aberto');
               radaiFilaPintar({cards: [], resumo: {}});
               const depois = !!document.querySelector('.ui-morfo.aberto');
               radaiFilaPintar(D);
               return {antes: antes, depois: depois}; }""")
            checar(u"[tela] R17: o cartão que sai da fila leva o painel do "
                   u"detalhe junto", sumiu["antes"] and not sumiu["depois"],
                   json.dumps(sumiu))
            await pg.keyboard.press("Escape")
            await pg.wait_for_timeout(300)
            await pg.evaluate("radaiPipe('iniciar')")
            await pg.wait_for_selector("#radai_rev_fronteira", state="visible", timeout=10000)
            await pg.wait_for_timeout(400)
            g = await pg.evaluate("""() => {
              const t = document.getElementById('radai_rev_fronteira');
              const b = document.getElementById('radai_rev_ok');
              const rt = t.getBoundingClientRect(), rb = b.getBoundingClientRect();
              return {texto: t.textContent.trim(), prox: t.nextElementSibling.className,
                      bt: b.textContent.trim(), gap: rb.top - rt.bottom,
                      vis: rt.height > 0 && rt.top >= 0 && rt.bottom <= innerHeight};
            }""")
            checar(u"[tela] R14: a tag amarela visível, logo antes do botão de começar",
                   g["texto"] == FRONTEIRA and g["prox"] == "rev-bt" and g["vis"]
                   and 0 <= g["gap"] <= 40
                   and g["bt"] == u"Começar a segmentar a fila agora",
                   json.dumps(g, ensure_ascii=False))
            if prints:
                await _prints(pg, prints, u"iniciar")
            await pg.evaluate("radaiRevFechar()")
            await pg.evaluate("folhaOvernight()")
            await pg.wait_for_selector(".ui-pnl .ov-form", timeout=10000)
            await pg.wait_for_timeout(900)
            await pg.click(".ui-pnl #ov_root_add")
            checar(u"[tela] o mais adiciona outra pasta ao Overnight",
                   await pg.locator(".ui-pnl [data-ov-root]").count() == 2)
            await pg.locator(".ui-pnl #ov_roots .ov-root").last.locator("button").last.click()
            bts = await pg.evaluate("""() => [...document.querySelectorAll('.ui-pnl button')]
               .filter(b => b.offsetParent && !b.closest('.ov-form')).map(b => b.textContent.trim())""")
            checar(u"[tela] R19: a folha só tem «Cancelar» e «Salvar e incluir na fila»",
                   sorted(bts) == sorted([u"Cancelar", u"Salvar e incluir na fila"])
                   and not await pg.evaluate("!!document.getElementById('ov_bt_sem')"),
                   u" | ".join(bts))
            bal = await pg.evaluate("""() => { const b = document.querySelector('.ui-pnl #ov_frota_aviso');
               if(!b) return {existe: false};
               b.scrollIntoView({block:'nearest'});
               const r = b.getBoundingClientRect(), c = document.querySelector('.ui-pnl .pnl-corpo').getBoundingClientRect();
               return {existe: true, vis: !b.hidden && r.height > 0, t: b.textContent,
                       dentro: r.left >= c.left && r.right <= c.right,
                       caixa: !!document.querySelector('.ui-pnl #ov_pausar')}; }""")
            checar(u"[tela] R18: sem STATUS_DIR, o aviso aparece na folha, dentro dela, "
                   u"e a caixa dos serviços não existe mais",
                   bal.get("existe") and bal.get("vis") and u"STATUS_DIR" in bal.get("t", u"")
                   and bal.get("dentro") and not bal.get("caixa"),
                   json.dumps({k: bal.get(k) for k in ("existe", "vis", "dentro", "caixa")}))
            fr = await pg.evaluate("(document.querySelector('.ui-pnl .rc-fronteira')||{}).textContent||''")
            checar(u"[tela]   e a folha leva a frase da regra 1", FRONTEIRA in fr)
            if prints:
                await _prints(pg, prints, u"overnight")
            await pg.keyboard.press("Escape")
            await pg.wait_for_timeout(400)
            _VAZIA = """async (o_) => {
               const fVelho = window.fetch, tVelho = window.uiTremer, oVelho = _ovTremerRoot;
               const vistos = [];
               window.fetch = function(u, o){
                if(o_.vazio && String(u) === '/api/config' && !(o && o.method === 'POST'))
                 return fVelho(u, o).then(r => r.json()).then(d => {
                  d.valores = Object.assign({}, d.valores || {}, {ROOT: ''});
                  return {json: () => Promise.resolve(d)}; });
                return fVelho(u, o);
               };
               window.uiTremer = function(a){ vistos.push((a && a.id) || '?'); return tVelho(a) };
               if(o_.isca) _ovTremerRoot = function(){};
               try{
                folhaOvernight();
                await new Promise(r => setTimeout(r, 1500));
                const r = {abrir: vistos.slice(), foco: (document.activeElement || {}).id || ''};
                const c = document.querySelector('.ui-pnl #ov_root');
                if(c){ c.focus();
                       c.dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter', bubbles: true})) }
                r.enter = vistos.slice(r.abrir.length);
                r.aberta = !!document.querySelector('.ui-pnl .ov-form');
                return r;
               } finally { window.fetch = fVelho; window.uiTremer = tVelho; _ovTremerRoot = oVelho; } }"""
            cheio = await pg.evaluate(_VAZIA, {"vazio": False, "isca": False})
            await pg.keyboard.press("Escape")
            await pg.wait_for_timeout(400)
            checar(u"[tela] a folha com o ROOT preenchido não treme ao abrir nem no Enter",
                   cheio["abrir"] == [] and cheio["enter"] == [] and cheio["aberta"],
                   json.dumps(cheio))
            vaz = await pg.evaluate(_VAZIA, {"vazio": True, "isca": False})
            await pg.keyboard.press("Escape")
            await pg.wait_for_timeout(400)
            checar(u"[tela] a folha com o ROOT vazio treme o campo uma vez ao abrir "
                   u"e dá o foco a ele", vaz["abrir"] == ["ov_root"]
                   and vaz["foco"] == "ov_root", json.dumps(vaz))
            checar(u"[tela]   e o Enter com o ROOT vazio treme de novo, sem fechar a folha",
                   vaz["enter"] == ["ov_root"] and vaz["aberta"], json.dumps(vaz))
            isca_f = await pg.evaluate(_VAZIA, {"vazio": True, "isca": True})
            await pg.keyboard.press("Escape")
            await pg.wait_for_timeout(400)
            checar(u"[tela] ISCA: sem o tremor da folha, nada treme ao abrir nem no "
                   u"Enter (a checagem sabe reprovar)",
                   isca_f["abrir"] == [] and isca_f["enter"] == [], json.dumps(isca_f))
            s0 = await pg.evaluate("({pasta: SERIES[1].pasta, uid: SERIES[1].uid})")
            r = await pg.evaluate("""(s) => fetch('/api/lote/selecao', {method:'POST',
               headers:{'Content-Type':'application/json'}, body: JSON.stringify({series:[s]})})
               .then(r => r.json())""", s0)
            await pg.goto(BASE + "/lote?ficha=" + (r.get("ficha") or ""), wait_until="networkidle")
            await pg.wait_for_timeout(2500)
            fx = await pg.evaluate("""() => ({
              tit: document.getElementById('cx2_tit').textContent.trim(),
              n: document.querySelectorAll('#tab tr[id^=linha_]').length,
              c1: !document.getElementById('cx1').closest('.ui-modal-veu.vis'),
              c2: document.getElementById('cx2').classList.contains('fechado'),
              cart: carrinhoLista().length})""")
            checar(u"[tela] E11: a ficha abre o passo 2 como «Séries selecionadas», com a série "
                   u"no carrinho, sem o popup do 1 por cima",
                   fx["tit"] == u"Séries selecionadas" and fx["n"] == 1 and fx["c1"]
                   and not fx["c2"] and fx["cart"] == 1, json.dumps(fx, ensure_ascii=False))
            if prints:
                await _prints(pg, prints, u"selecionadas", so_um=True)
            await pg.evaluate("localStorage.setItem('radai_idioma', 'en')")
            await pg.goto(BASE + "/lote", wait_until="networkidle")
            await pg.wait_for_timeout(1500)
            await pg.evaluate("ltEscolha(); true")
            await pg.wait_for_timeout(600)
            en = await pg.evaluate("""() => ({
              tag: document.querySelector('.ui-fn-tag').textContent.trim(),
              frase: document.querySelector('.ui-fn-frase').textContent.trim(),
              alerta: document.querySelector('.ui-alerta').textContent.trim(),
              bt: document.getElementById('btrodar').textContent.trim(),
              p1: document.querySelector('.ui-modal-veu.vis .ui-modal-tit').textContent.trim(),
              p2: document.getElementById('cx2_tit').textContent.trim()})""")
            pt = [k for k, v in en.items() if re.search(u"[ãõçéêíóúâ]|Rodar|Carregar|Adicionar", v)]
            checar(u"[tela] em inglês, as frases novas saem traduzidas", not pt,
                   json.dumps(en, ensure_ascii=False))
            await pg.keyboard.press("Escape")
            await pg.wait_for_timeout(400)
            await _a_conferencia_em_ingles(pg)
            await _o_ponto_da_fila(pg)
            if prints:
                await _prints(pg, prints, u"inicio_en")
                await pg.click("#cd_add")
                await pg.click(".cam-linha button.pri")
                await pg.wait_for_selector("#tab .mini-serie img", timeout=30000)
                await pg.wait_for_timeout(1200)
                await _prints(pg, prints, u"lista_en")
                await pg.evaluate("""() => { const s = document.querySelector('#tab select.md-sel');
                   s.value = 'perso'; s.dispatchEvent(new Event('change', {bubbles:true})); }""")
                await pg.wait_for_selector("tr.perso .p4", timeout=10000)
                await pg.wait_for_timeout(900)
                await pg.evaluate("document.querySelector('tr.perso').scrollIntoView({block:'center'})")
                await _prints(pg, prints, u"personalizado_en")
                await pg.evaluate("radaiPipe('iniciar')")
                await pg.wait_for_selector("#radai_rev_fronteira", state="visible", timeout=10000)
                await pg.wait_for_timeout(600)
                await _prints(pg, prints, u"iniciar_en")
                await pg.evaluate("radaiRevFechar()")
                await pg.evaluate("folhaOvernight()")
                await pg.wait_for_selector(".ui-pnl .ov-form", timeout=10000)
                await pg.wait_for_timeout(900)
                await _prints(pg, prints, u"overnight_en")
                await pg.keyboard.press("Escape")
            await pg.evaluate("localStorage.setItem('radai_idioma', 'pt-BR')")
            checar(u"[tela] nenhum erro de JavaScript em todo o percurso", not erros,
                   u" | ".join(erros[:3]))
        finally:
            await nav.close()


PT_DA_CONFERENCIA = (
    u"Modelos (tasks)", u"Suavização", u"Suavizacao", u"Tempo provável",
    u"Tempo provavel", u"menos de um minuto", u"A estimativa sai de dois",
    u"arquivos que v", u"pós-processamento voltado", u"pos-processamento",
    u"Nada começou", u"Nada comecou", u"Níveis cervicais", u"AO LADO",
    u"o que vai ser processado", u"como vai rodar", u"vale olhar antes",
    u"Memória livre", u"Pouco espaço", u"a máquina já está",
    u"O vigia está processando", u"Duas segmentações", u"Não dá para começar",
    u"(sem ID)", u"e mais ", u" cortes")


def _payload_da_conferencia():
    import radai_review as R
    base = R.montar([{"pid": u"", "uid": u"1.2.3.40001111", "cortes": 30,
                      "espessura_mm": 3.0}], tasks=("total_v3",), device="cpu")
    base.update({
        "mais": 2, "estimativa": u"menos de um minuto",
        "conjuntos": [{"infixo": u"", "nome": u"Radioterapia.ai_OAR", "sai": True,
                       "entregue": True, "porque": u""},
                      {"infixo": u"HNL_", "nome": u"Níveis cervicais",
                       "sai": False, "entregue": False, "porque": u""}],
        "estacao": {"memoria": {"total_mb": 16000, "livre_mb": 900},
                    "disco": [{"aperta": True, "unidade": u"C:", "livre_gb": 3}],
                    "ganhos": []},
        "ocupado": {"quem": u"vigia", "o_que": u"#1", "etapa": u"total_v3"},
    })
    return base


async def _a_conferencia_em_ingles(pg):
    dados = _payload_da_conferencia()
    await pg.evaluate("() => { const b = document.createElement('button');"
                      " b.id = 't_abridor'; b.textContent = 'x';"
                      " document.body.prepend(b); b.focus(); }")
    await pg.evaluate("d => radaiRevAbrir(d, null)", dados)
    await pg.wait_for_timeout(300)
    await pg.evaluate("() => window.radaiRetraduzir && window.radaiRetraduzir()")
    await pg.wait_for_timeout(300)
    txt = await pg.evaluate("document.getElementById('radai_rev').textContent")
    sobra = [f for f in PT_DA_CONFERENCIA if f in txt]
    checar(u"[tela] TEL-01: a conferência do INICIAR sai inteira em inglês",
           not sobra, u" | ".join(sobra))
    fora = []
    for _ in range(8):
        await pg.keyboard.press("Tab")
        dentro = await pg.evaluate(
            "document.getElementById('radai_rev').contains(document.activeElement)")
        if not dentro:
            fora.append(await pg.evaluate(
                "document.activeElement.tagName + '#' + document.activeElement.id"))
    await pg.keyboard.press("Shift+Tab")
    await pg.keyboard.press("Shift+Tab")
    dentro_shift = await pg.evaluate(
        "document.getElementById('radai_rev').contains(document.activeElement)")
    checar(u"[tela] TEL-02: o Tab não sai do diálogo da conferência",
           not fora and dentro_shift, u" | ".join(fora[:3]))
    await pg.keyboard.press("Escape")
    await pg.wait_for_timeout(200)
    volta = await pg.evaluate("document.activeElement && document.activeElement.id")
    checar(u"[tela] TEL-02: ao fechar, o foco volta a quem abriu", volta == u"t_abridor",
           str(volta))
    await pg.evaluate("() => document.getElementById('t_abridor').remove()")


_FORA_FALSO = u"""(isca) => {
  window.__fetch0 = window.__fetch0 || window.fetch;
  window.fetch = function(u){
    if(String(u).indexOf('/api/fora_da_fila') >= 0)
      return Promise.resolve({json: function(){ return Promise.resolve(
        {em_espera: [], nao_contornaveis: [{uid8: '40001111', pid: '',
         motivo: 'x'}], n_nao_contornaveis: 1}) }});
    return window.__fetch0.apply(this, arguments);
  };
  if(isca){ window.__pf0 = radaiTfPontoFila; radaiTfPontoFila = function(){}; }
  return true;
}"""

_PONTOS = u"""() => ({
  ic: !!document.querySelector('#radai_tf_ic_fila > .ui-ponto'),
  rot: !!document.querySelector('#radai_tf_ab_fila > .ui-ponto')})"""


async def _o_ponto_da_fila(pg):
    await pg.evaluate(_FORA_FALSO, False)
    await pg.evaluate("uiDireita('1')")
    await pg.evaluate("radaiForaDaFila()")
    await pg.wait_for_timeout(300)
    rec = await pg.evaluate(_PONTOS)
    await pg.evaluate("uiDireita('0'); radaiTfAba('log')")
    await pg.wait_for_timeout(200)
    log = await pg.evaluate(_PONTOS)
    await pg.evaluate("radaiTfAba('fila')")
    await pg.wait_for_timeout(200)
    fila = await pg.evaluate(_PONTOS)
    checar(u"[tela] COMP-10: fora da fila, com a barra recolhida, o ponto acende no ícone",
           rec["ic"], json.dumps(rec))
    checar(u"[tela]   na aba Log, acende na aba Fila; na Fila à vista, apaga",
           log["rot"] and not fila["rot"] and not fila["ic"],
           json.dumps([log, fila]))
    await pg.evaluate("radaiTfPontoFila(false); uiDireita('1')")
    await pg.evaluate(_FORA_FALSO, True)
    await pg.evaluate("radaiForaDaFila()")
    await pg.wait_for_timeout(300)
    isca = await pg.evaluate(_PONTOS)
    checar(u"[tela]   (isca) sem a chamada do ponto, nada acende",
           not isca["ic"] and not isca["rot"], json.dumps(isca))
    await pg.evaluate("radaiTfPontoFila = window.__pf0; window.fetch = window.__fetch0;"
                      " radaiTfPontoFila(false); uiDireita('0')")


async def _prints(pg, pasta, nome, so_um=False):
    os.makedirs(pasta, exist_ok=True)
    combos = [(1280, "escuro")] if so_um else [(1280, "escuro"), (1600, "escuro"),
                                               (1280, "claro"), (1600, "claro")]
    for larg, tema in combos:
        await pg.set_viewport_size({"width": larg, "height": 900})
        await pg.evaluate("t => uiTema(t)", tema)
        await pg.wait_for_timeout(300)
        await pg.screenshot(path=os.path.join(pasta, "rodar_%s_%d_%s.png" % (nome, larg, tema)))
    await pg.set_viewport_size({"width": 1280, "height": 900})
    await pg.evaluate("t => uiTema(t)", "escuro")


def teste_a_tela_renderizada():
    secao(u"a tela renderizada (Chromium, vigia de verdade, séries fantoma)")
    try:
        import playwright
    except Exception:
        print(u"  PULADO: sem Playwright neste Python")
        return
    exe = _chromium()
    if not exe:
        print(u"  PULADO: sem o Chromium do Playwright na máquina")
        return
    tmp = tempfile.mkdtemp(prefix="radai_rodar_")
    proc, root = _subir(tmp)
    if proc is None:
        checar(u"o vigia de teste subiu", False, open(os.path.join(tmp, "vigia.log"),
                                                    encoding="utf-8", errors="replace").read()[-400:])
        return
    try:
        asyncio.run(_navegar(exe, root, os.environ.get("RADAI_PRINTS_DIR") or None))
    finally:
        proc.kill()
        try:
            proc.wait(timeout=10)
        except Exception:
            pass


def main():
    print(u"=" * 68)
    print(u"test_rodar | o «Rodar agora» da v8.4 (trilha RODAR)")
    print(u"=" * 68)
    testes = (teste_a_cabeca_e_o_rodape, teste_os_passos, teste_a_coluna_serie,
              teste_a_fronteira_no_iniciar, teste_a_folha_do_turno,
              teste_o_personalizado, teste_as_rotas, teste_a_demo,
              teste_a_barra_abre_ao_por_na_fila,
              teste_as_frases_tem_os_doze_idiomas, teste_a_tela_renderizada)
    for t in testes:
        try:
            t()
        except Exception as e:
            checar(u"%s chegou ao fim" % t.__name__, False,
                   u"%s: %s" % (type(e).__name__, e))
            traceback.print_exc()
    falhas = [r for r in _RES if not r[1]]
    print()
    if falhas:
        print(u"FALHOU: %d de %d checagens" % (len(falhas), len(_RES)))
        for n, _ok, d in falhas:
            print(u"  - %s%s" % (n, (u"  [%s]" % d) if d else u""))
        return 1
    print(u"OK: %d checagens, todas passaram" % len(_RES))
    return 0


if __name__ == "__main__":
    sys.exit(main())
