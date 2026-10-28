# -*- coding: utf-8 -*-
import io
import json
import os
import re
import shutil
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
APP = os.path.join(RAIZ, "app")
sys.path.insert(0, APP)
sys.path.insert(0, AQUI)

import _cleanup
_cleanup.adotar_prefixo("radai_vs_")
os.environ["RADAI_CALIB_DIR"] = tempfile.mkdtemp(prefix="radai_vs_calib_")
os.environ["RADAI_NOTIFICACAO"] = "0"

import test_ui as U

_RES = []


def checar(nome, cond, detalhe=u""):
    _RES.append((nome, bool(cond), detalhe))
    print(u"  %s  %s%s" % (u"ok    " if cond else u"FALHA ", nome,
                           (u"  [%s]" % detalhe) if (detalhe and not cond) else u""))


def secao(t):
    print(u"\n─── %s %s" % (t, u"─" * max(0, 66 - len(t))))


def _pagina():
    import radai_view
    return radai_view._pagina()


def _sem_comentarios(p):
    return re.sub(r"<!--.*?-->", u" ", p, flags=re.S)


def _sem_comentarios_js(js):
    return u"\n".join(ln for ln in js.splitlines()
                      if not ln.strip().startswith(u"//"))


def falhas_do_padrao(p):
    import radai_view
    falhas = []
    a = U._Arvore(p)
    cab = re.search(r'<header class="ui-fn">(.*?)</header>', p, re.S)
    if not cab:
        return [u"sem a cabeça `ui-fn`"]
    tag = re.search(r'<h1 class="ui-fn-tag"[^>]*>(.*?)</h1>', cab.group(1), re.S)
    if not tag or u"&#9673;" not in tag.group(1) or u">Ver segmentação<" \
            not in tag.group(1):
        falhas.append(u"a tag não é «◉ Ver segmentação»")
    if u"--mod-auto" not in (tag.group(0) if tag else u""):
        falhas.append(u"a tag não veste a cor do ContourLab")
    if u'class="ui-ajuda' not in cab.group(1):
        falhas.append(u"a cabeça não tem o «?»")
    fr = re.search(r'<p class="ui-fn-frase"[^>]*>(.*?)</p>', cab.group(1), re.S)
    if not fr or fr.group(1) != radai_view.FRASE:
        falhas.append(u"a frase não é a do autor")
    if p.find(u'<header class="ui-fn">') > p.find(u'id="cx_vr0"'):
        falhas.append(u"a cabeça não vem antes do item 1")
    if u'class="rc-chip"' in _sem_comentarios(p):
        falhas.append(u"a capa antiga (`rc-chip`) continua")
    nums = re.findall(r'<span class="(?:ps-num|ui-cartao-ic)"'
                      r'(?: aria-hidden="true")?>(\d)</span>', p)
    if nums != [u"1", u"2"]:
        falhas.append(u"os itens não são 1 e 2: %s" % nums)
    if (not a.dentro(u"vr_cartao", u"cx_vr0")
            or u'data-ui-ps-abre="vr_escolha"' not in p):
        falhas.append(u"o item 1 não é o cartão que abre o popup da série")
    if not a.dentro(u"vr_guias", u"vr_escolha"):
        falhas.append(u"as abas não estão no popup da série")
    if u'class="ui-guias esq" id="vr_guias" data-ativa="acervo"' not in p:
        falhas.append(u"o popup não abre no Acervo Local, com as abas à esquerda")
    for k, rot in ((u"acervo", u"Acervo Local"), (u"pasta", u"Aponte uma pasta")):
        if not re.search(r'data-guia="%s"[^>]*><span data-radai-frase>%s</span>'
                         % (k, rot), p):
            falhas.append(u"falta a aba «%s»" % rot)
    if not a.dentro(u"vr_acervo", u"vr_guias-p-acervo"):
        falhas.append(u"o acervo não mora na aba dele")
    for i in (u"vr_pasta", u"vr_lista", u"vr_vazio", u"vr_procurar"):
        if not a.dentro(i, u"vr_guias-p-pasta"):
            falhas.append(u"%s não mora na aba da pasta" % i)
    codigo = _sem_comentarios_js(_sem_comentarios(p))
    if u"vr-duas" in codigo or u"vrp_cx" in codigo:
        falhas.append(u"as duas colunas ou o seletor antigo continuam")
    h = re.search(r'<h2 class="ps-cab" id="h_verseg".*?</h2>', p, re.S)
    if not h or u"Ver segmentação" not in h.group(0) or u"ps-sub" in h.group(0):
        falhas.append(u"o item 2 não é só «Ver segmentação»")
    if h and u'class="ui-ajuda' not in h.group(0):
        falhas.append(u"o item 2 perdeu o «?»")
    if u'class="ps-cx fechado cp-bloco" id="cx_verseg"' not in p \
            or u"div.cp-bloco{margin-top:22px}" not in p:
        falhas.append(u"o item 2 não tem o respiro acima dele")
    al = p.find(u'class="ui-alerta')
    if al < 0 or al < p.find(u'id="cx_verseg"'):
        falhas.append(u"o alerta de uma linha não está no pé")
    return falhas


def teste_a_tela_segue_o_padrao():
    secao(u"a tela no padrão: tag, frase, item 1 com abas, item 2, alerta")
    p = _pagina()
    f = falhas_do_padrao(p)
    checar(u"a página segue o padrão de função da v8.4", not f, u"; ".join(f))
    iscas = [
        (u"sem a cabeça", re.sub(r'<header class="ui-fn">.*?</header>', u"", p,
                                 count=1, flags=re.S)),
        (u"o item 2 com o subtítulo antigo", p.replace(
            u'<span data-radai-frase>Ver segmentação</span>\n  <span class="ui-ajuda',
            u'Ver segmentação <span class="ps-sub">— dois arquivos lado a lado, '
            u'no mesmo corte</span>\n  <span class="ui-ajuda', 1)),
        (u"a numeração antiga", p.replace(u'<span class="ps-num">2</span>',
                                          u'<span class="ps-num">3</span>', 1)),
        (u"o campo fora da aba", p.replace(u'id="vr_guias-p-pasta"', u'id="x"', 1)),
        (u"a aba da pasta como padrão", p.replace(
            u'id="vr_guias" data-ativa="acervo"', u'id="vr_guias" data-ativa="pasta"', 1)),
        (u"as abas fora do popup", p.replace(u'id="vr_escolha"', u'id="y"', 1)),
        (u"o seletor antigo no código", p.replace(
            u"</body>", u'<div id="vrp_cx"></div></body>', 1)),
    ]
    for nome, isca in iscas:
        checar(u"  (isca) %s reprova" % nome, bool(falhas_do_padrao(isca)))


def _literais_js(js):
    linhas = []
    for ln in js.splitlines():
        if ln.strip().startswith(u"//"):
            continue
        linhas.append(re.sub(r"\s//[^'\"\n]*$", u"", ln))
    js = u"\n".join(linhas)
    return re.findall(r"'((?:[^'\\\n]|\\.)*)'|\"((?:[^\"\\\n]|\\.)*)\"", js)


def textos_com_tps():
    import radai_view
    import radai_viewseg
    fora = []
    html = _sem_comentarios(radai_view.PAGINA + radai_view.ACERVO_HTML
                            + radai_view.PASTA_HTML + radai_viewseg.bloco())
    html = re.sub(r"<script.*?</script>|<style.*?</style>", u" ", html, flags=re.S)
    texto = re.sub(r"<[^>]+>", u" ", html)
    for ln in texto.splitlines():
        if u"TPS" in ln:
            fora.append(ln.strip())
    for a, b in _literais_js(radai_view.JS + radai_viewseg.JS):
        s = a or b
        if u"TPS" in s:
            fora.append(s)
    for v in list(radai_viewseg.ROTULO_DA_TELA.values()) + [
            radai_viewseg.ROTULO_MAPA] + list(radai_view.AJUDA) + list(
            radai_view.AJUDA_DA_SERIE):
        if u"TPS" in v:
            fora.append(v)
    for c in radai_view._conjuntos_da_tela():
        if u"TPS" in (c.get("ajuda") or u"") + (c.get("rotulo_curto") or u""):
            fora.append(c.get("rotulo_curto"))
    return fora


def teste_a_tela_nao_cita_tps():
    secao(u"a tela não cita o TPS (V13)")
    import radai_viewseg
    f = textos_com_tps()
    checar(u"nenhuma frase da tela cita o TPS", not f, u" | ".join(f)[:300])
    checar(u"o STUDY é «a seleção do FULL voltada para radioterapia»",
           radai_viewseg.ROTULO_DA_TELA.get(u"oar")
           == u"STUDY — a seleção do FULL voltada para radioterapia")
    velho = radai_viewseg.ROTULO_DA_TELA[u"oar"]
    try:
        radai_viewseg.ROTULO_DA_TELA[u"oar"] = u"OAR — o entregue ao TPS, seleção do FULL"
        checar(u"  (isca) o rótulo antigo reprova", bool(textos_com_tps()))
    finally:
        radai_viewseg.ROTULO_DA_TELA[u"oar"] = velho


_HARNESS = u"""
var CHAMADAS = [], PEDIDOS = [], LOC = {href: ''}, RETRADUZ = 0;
function El(id){ this.id = id; this.style = {}; this.classList = {
  add: function(){}, remove: function(){}, toggle: function(){}, contains: function(){ return false; }};
 this.textContent = ''; this.innerHTML = ''; this.value = ''; this.clientWidth = 0;
 this.clientHeight = 0; this.offsetWidth = 0; this.offsetHeight = 0; }
El.prototype.setAttribute = function(){};
El.prototype.getAttribute = function(){ return null; };
El.prototype.querySelector = function(){ return null; };
El.prototype.querySelectorAll = function(){ return []; };
El.prototype.addEventListener = function(){};
var ELS = {};
var document = {readyState: 'complete', getElementById: function(id){
  if(!ELS[id]) ELS[id] = new El(id); return ELS[id]; },
 addEventListener: function(){}, querySelectorAll: function(){ return []; }};
var window = {location: LOC, uiCarregando: function(e, lig, t){
  CHAMADAS.push({id: e && e.id, lig: lig, t: t || ''}); },
 radaiRetraduzir: function(){ RETRADUZ++; }};
function Image(){ var eu = this; var s = '';
 Object.defineProperty(this, 'src', {get: function(){ return s; },
  set: function(v){ s = v; setTimeout(function(){ if(eu.onload) eu.onload(); }, 0); }}); }
function fetch(u, o){
 PEDIDOS.push({u: u, corpo: o && o.body ? JSON.parse(o.body) : null});
 var c = {};
 if(u.indexOf('/api/verseg/forma') === 0) c = {forma: [20, 128, 128], sp: [3, 2, 2], hu: true};
 else if(u.indexOf('/api/verseg/estruturas') === 0) c = {rs: 'X', estruturas: []};
 else if(u.indexOf('/api/verseg/contornos') === 0) c = {rs: 'X', estruturas: []};
 else if(u.indexOf('/api/verseg/recon3d') === 0) c = {ficha: 'FICHA1'};
 return Promise.resolve({json: function(){ return Promise.resolve(c); }});
}
"""

_RODA = u"""
function espera(ms){ return new Promise(function(r){ setTimeout(r, ms); }); }
(async function(){
 var R = {};
 cpAbrirSerie({b: 'B', uid: 'U', cortes: 20, nome: 'FANTOMA <TESTE>',
  pid: 'SINTETICO', modalidade: 'MR', date: '20261028', desc: 'SERIE TESTE',
  espessura_mm: 2, rs: [{arquivo: 'RS_RadAI_FULL_1.dcm', cod: 'full'}]});
 R.cabecalho = ELS['cp_qual'] ? ELS['cp_qual'].innerHTML : '';
 R.zoom = CP.zoom;
 R.ligouNoAbrir = CHAMADAS.filter(function(c){ return c.lig === true; }).map(function(c){ return c.id; });
 await espera(60);
 R.desligou = CHAMADAS.filter(function(c){ return c.lig === false; }).map(function(c){ return c.id; });
 CHAMADAS = [];
 cpAbrirSerie({b: 'B2', uid: 'U2', cortes: 20, rs: [], sem_contorno: true});
 await espera(60);
 R.msgSemContorno = ELS['cp_msg'] ? ELS['cp_msg'].textContent : '';
 CP.serie = {b: 'B', rs: [{arquivo: 'RS_RadAI_1.dcm', cod: 'oar', curto: 'OAR',
                           rotulo: 'OAR — a seleção do FULL voltada para radioterapia'}]};
 var E = cpNovoLado(0); E.arq = 'RS_RadAI_1.dcm'; E.rotuloDicom = 'RadAI_OAR';
 RETRADUZ = 0; cpEtiqueta(E);
 R.etiqueta = ELS['cp_dicom0'] ? ELS['cp_dicom0'].innerHTML : '';
 R.retradEtiqueta = RETRADUZ;
 RETRADUZ = 0; cpMsg('a série não está mais nesta pasta');
 R.retradMsg = RETRADUZ;
 R.lista0 = ELS['cp_chips0'] ? ELS['cp_chips0'].innerHTML : '';
 PEDIDOS = [];
 var L = cpNovoLado(0); L.arq = 'RS_RadAI_FULL_1.dcm';
 L.estruturas = [{nome: 'Heart_ai', cortes: 3}, {nome: 'Lung_L_ai', cortes: 2},
                 {nome: 'Vazia_ai', cortes: 0}];
 L.ligadas = {'Heart_ai': 1, 'Vazia_ai': 1};
 CP.serie = {b: 'B'};
 R.ficha = await cpParaReconstrucao(L);
 R.pedido = PEDIDOS.filter(function(p){ return p.u === '/api/verseg/recon3d'; })[0] || null;
 R.href = LOC.href;
 PEDIDOS = [];
 var N = cpNovoLado(1); N.arq = 'X'; N.estruturas = [{nome: 'A', cortes: 1}];
 await cpParaReconstrucao(N);
 R.semLigadasPediu = PEDIDOS.length;
 R.msgSemLigadas = ELS['cp_msg'].textContent;
 PEDIDOS = [];
 var C = cpNovoLado(0); C.arq = 'X'; C.carregando = true;
 C.estruturas = [{nome: 'A', cortes: 1}]; C.ligadas = {'A': 1};
 await cpParaReconstrucao(C);
 R.carregandoPediu = PEDIDOS.length;
 R.msgCarregando = ELS['cp_msg'].textContent;
 console.log('JSON:' + JSON.stringify(R));
})();
"""


def _rodar_comparador(js):
    node = U._node()
    if not node:
        return None, u"sem node"
    return U._rodar_node(_HARNESS + js + _RODA, node)


def falhas_do_comparador(d):
    f = []
    if not d:
        return [u"não executou"]
    cabecalho = d.get(u"cabecalho") or u""
    if not all(v in cabecalho for v in (
            u"Paciente", u"FANTOMA &lt;TESTE&gt;", u"ID", u"SINTETICO",
            u"Modalidade", u"MR", u"Data do exame", u"28/10/2026",
            u"SERIE TESTE", u"Cortes", u"Espessura")):
        f.append(u"o cabecalho nao mostra todos os metadados selecionados")
    if u"FANTOMA <TESTE>" in cabecalho:
        f.append(u"o nome da serie entrou como HTML sem escape")
    if abs(float(d.get(u"zoom") or 0) - 1.25) > 1e-9:
        f.append(u"o zoom inicial é %s, e não 125%%" % d.get(u"zoom"))
    if sorted(d.get(u"ligouNoAbrir") or []) != [u"cp_visor0", u"cp_visor1"]:
        f.append(u"o carregamento orgânico não nasce nos dois visores: %s"
                 % d.get(u"ligouNoAbrir"))
    if sorted(d.get(u"desligou") or []) != [u"cp_visor0", u"cp_visor1"]:
        f.append(u"o carregamento não sai com a primeira imagem: %s"
                 % d.get(u"desligou"))
    if u"ainda não foi segmentada" not in (d.get(u"msgSemContorno") or u""):
        f.append(u"a série sem contorno não diz que não foi segmentada")
    if u"referência" in (d.get(u"msgSemContorno") or u""):
        f.append(u"a série do acervo fala do RTSTRUCT de referência da demo")
    if u"nenhum arquivo de contorno" not in (d.get(u"lista0") or u""):
        f.append(u"a lista da série sem contorno fica «carregando»")
    if u"RadAI_OAR" not in (d.get(u"etiqueta") or u""):
        f.append(u"a etiqueta do arquivo não foi escrita: %r" % d.get(u"etiqueta"))
    if not d.get(u"retradEtiqueta"):
        f.append(u"a etiqueta do arquivo é reescrita e não pede a tradução na "
                 u"hora: fica em português até a próxima passada do tradutor")
    if not d.get(u"retradMsg"):
        f.append(u"a mensagem do visor não pede a tradução na hora")
    ped = d.get(u"pedido") or {}
    if (ped.get(u"corpo") or {}).get(u"estruturas") != [u"Heart_ai"]:
        f.append(u"a ida às Reconstruções não leva só o visível: %s" % ped)
    if (ped.get(u"corpo") or {}).get(u"rs") != u"RS_RadAI_FULL_1.dcm":
        f.append(u"a ida às Reconstruções não leva o arquivo do visor")
    if d.get(u"href") != u"/recon3d/anatomia?ficha=FICHA1":
        f.append(u"não abriu /recon3d/anatomia com a ficha: %s" % d.get(u"href"))
    if d.get(u"semLigadasPediu") or u"ligue ao menos uma estrutura" not in (
            d.get(u"msgSemLigadas") or u""):
        f.append(u"sem estrutura ligada ele pediu assim mesmo")
    if d.get(u"carregandoPediu") or u"carregando" not in (d.get(u"msgCarregando") or u""):
        f.append(u"com as estruturas ainda carregando ele pediu (ou disse outra coisa)")
    return f


def teste_o_comparador_executado():
    secao(u"o comparador executado: zoom 125%, carregamento, Reconstrução 3D")
    import radai_viewseg
    js = radai_viewseg.JS
    d, erro = _rodar_comparador(js)
    if d is None and erro == u"sem node":
        checar(u"node disponível", False, u"PULADO")
        return
    f = falhas_do_comparador(d)
    checar(u"o comparador abre a 125%, com o carregamento, e leva o visível",
           not f, u"; ".join(f) or (erro or u""))
    iscas = [
        (u"zoom 100%", js.replace(u"CP.zoom = CP_ZOOM_INICIAL;", u"CP.zoom = 1;")),
        (u"sem o carregamento", js.replace(u"cpCarregando(true, 'abrindo a série…');", u"")),
        (u"todas as ligadas, até as sem corte",
         js.replace(u"if(lado.ligadas[e.nome] && e.cortes)", u"if(lado.ligadas[e.nome])")),
        (u"pede com as estruturas carregando",
         js.replace(u" if(lado.carregando){\n  cpMsg", u" if(false){\n  cpMsg")),
    ]
    for nome, isca in iscas:
        checar(u"  (isca) %s reprova" % nome,
               bool(falhas_do_comparador(_rodar_comparador(isca)[0])))
    checar(u"«espelhar com o outro lado» no lugar de «copiar»",
           u">espelhar com o outro lado<" in radai_viewseg.bloco()
           and u"copiar para o outro lado" not in radai_viewseg.bloco())
    b = radai_viewseg.bloco()
    checar(u"o botão «Reconstrução 3D» em cada visor, com a cor das Reconstruções",
           b.count(u"data-cp-recon=") == 2 and u">Reconstrução 3D<" in b
           and u".cp-bt.cp-recon{border-color:var(--mod-recon)" in radai_viewseg.CSS)
    checar(u"os passos do corte são ícones desenhados, e não glifos",
           u"&#8249;" not in b and u"&#8250;" not in b and b.count(u'class="ui-ic') >= 2)


_RODA_DA_RODA = u"""
function espera(ms){ return new Promise(function(r){ setTimeout(r, ms); }); }
function roda(dy, extra){
 var ev = {deltaY: dy, preventDefault: function(){}};
 for(var k in (extra || {})) ev[k] = extra[k];
 cpRoda(ev, 0); return CP.corte;
}
function tecla(k){ cpTecla({key: k, preventDefault: function(){}}); return CP.corte; }
(async function(){
 var R = {};
 cpAbrirSerie({b: 'B', uid: 'U', cortes: 20, rs: []});
 await espera(60);
 R.cranial = CP.cranial;
 R.meio = CP.corte;
 R.baixo = roda(100);
 R.cima = roda(-100);
 CP.corte = 20; R.baixoShift = roda(100, {shiftKey: true});
 CP.corte = 20; R.setaBaixo = tecla('ArrowDown');
 CP.corte = 20; R.setaCima = tecla('ArrowUp');
 CP.corte = 20; R.pageDown = tecla('PageDown');
 CP.corte = 20; R.direita = tecla('ArrowRight');
 CP.corte = 20; var z0 = CP.zoom; roda(-100, {ctrlKey: true});
 R.ctrlAproxima = CP.zoom > z0; R.ctrlCorte = CP.corte;
 console.log('JSON:' + JSON.stringify(R));
})();
"""

_FORMA_DO_HARNESS = u"c = {forma: [20, 128, 128], sp: [3, 2, 2], hu: true};"


def _rodar_a_roda(js, cranial):
    node = U._node()
    if not node:
        return None, u"sem node"
    h = _HARNESS.replace(_FORMA_DO_HARNESS, _FORMA_DO_HARNESS.replace(
        u"[20, 128, 128]", u"[40, 128, 128]").replace(
        u"hu: true}", u"hu: true, cranial: %d}" % cranial))
    return U._rodar_node(h + js + _RODA_DA_RODA, node)


def falhas_da_roda(d, cranial):
    if not d:
        return [u"não executou"]
    f = []

    def z(k):
        return (k - d[u"meio"]) * cranial

    if d.get(u"cranial") != cranial:
        f.append(u"o sentido do servidor (%d) não chegou ao visor: %s"
                 % (cranial, d.get(u"cranial")))
    if not z(d[u"baixo"]) < 0:
        f.append(u"rodar para baixo não foi para caudal (corte %s -> %s)"
                 % (d[u"meio"], d[u"baixo"]))
    if d[u"cima"] != d[u"meio"]:
        f.append(u"rodar para cima não voltou ao corte de partida")
    if d[u"meio"] != 20:
        f.append(u"a série não abriu no meio dos 40 cortes: %s" % d[u"meio"])
    if (d[u"baixoShift"] - 20) * cranial != -10:
        f.append(u"Shift com a roda para baixo não andou dez para caudal: %s"
                 % d[u"baixoShift"])
    if (d[u"setaBaixo"] - 20) * cranial != -1 or \
            (d[u"setaCima"] - 20) * cranial != 1:
        f.append(u"as setas para baixo e para cima não seguem a roda")
    if (d[u"pageDown"] - 20) * cranial != -10:
        f.append(u"o PageDown não andou dez para caudal")
    if d[u"direita"] != 21:
        f.append(u"a seta para a direita deixou de ser o próximo corte")
    if not d.get(u"ctrlAproxima") or d.get(u"ctrlCorte") != 20:
        f.append(u"Ctrl com a roda deixou de aproximar sem trocar o corte")
    return f


def teste_a_roda_vai_para_caudal():
    secao(u"a roda do mouse: para baixo vai para caudal (retorno de campo)")
    import radai_viewseg
    js = radai_viewseg.JS
    for cranial, nome in ((1, u"índice cresce para cranial (cabeça "
                              u"primeiro)"),
                          (-1, u"índice cresce para caudal (pés primeiro)")):
        d, erro = _rodar_a_roda(js, cranial)
        if d is None and erro == u"sem node":
            checar(u"node disponível", False, u"PULADO")
            return
        f = falhas_da_roda(d, cranial)
        checar(u"%s: rodar para baixo vai para caudal, e as setas seguem"
               % nome, not f, u"; ".join(f) or (erro or u""))
    iscas = [
        (u"a roda antiga (para baixo = próximo índice)",
         js.replace(u"cpAndar(cpRumoCaudal((ev.deltaY > 0 ? 1 : -1)",
                    u"cpAndar(((ev.deltaY > 0 ? 1 : -1)")),
        (u"o sentido do servidor ignorado",
         js.replace(u"CP.cranial = (d && d.cranial === -1) ? -1 : 1;",
                    u"CP.cranial = 1;")),
    ]
    for nome, isca in iscas:
        checar(u"  (isca) %s reprova" % nome, isca != js and any(
            falhas_da_roda(_rodar_a_roda(isca, c)[0], c) for c in (1, -1)))

    import SimpleITK as sitk
    img = sitk.Image(4, 4, 3, sitk.sitkInt16)
    checar(u"o servidor: série axial com o índice para +z (cranial em LPS) "
           u"dá +1", radai_viewseg.sentido_cranial(img) == 1)
    img.SetDirection((-1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, -1.0))
    checar(u"  e com o índice para -z (pés primeiro) dá -1",
           radai_viewseg.sentido_cranial(img) == -1)
    import numpy as np
    velho = radai_viewseg._serie
    try:
        radai_viewseg._serie = lambda pasta, uid: (
            np.zeros((3, 4, 4), np.int16), img, {"sp": [1.0, 1.0, 1.0]})
        pes = radai_viewseg.forma_da_serie(u"P", u"U").get(u"cranial")
    finally:
        radai_viewseg._serie = velho
    checar(u"  e a forma que o visor pede leva o sentido (%s)" % pes, pes == -1)
    img.SetDirection((0.0, 0.0, 1.0, 1.0, 0.0, 0.0, 0.0, 1.0, 0.0))
    checar(u"  e série sagital (o índice não anda no eixo craniocaudal) fica "
           u"no +1", radai_viewseg.sentido_cranial(img) == 1)


def teste_o_acervo_e_o_seletor_no_js():
    secao(u"o acervo e o seletor de pasta no JS")
    import radai_view
    js = radai_view.JS
    corpo = U._corpo_js(js, u"vrProcurar")
    checar(u"«Procurar» abre o explorador do «Rodar agora» (`uiExplorador`)",
           u"uiExplorador(" in corpo and u"aoUsar" in corpo, corpo[:120])
    def seletor_antigo(j):
        j = _sem_comentarios_js(j)
        return u"function vrpIr(" in j or u"/api/pastas" in j
    checar(u"e o seletor próprio antigo saiu", not seletor_antigo(js))
    checar(u"  (isca) o seletor antigo de volta no código reprova",
           seletor_antigo(js + u"\nfunction vrpIr(c){ fetch('/api/pastas') }\n"))
    ac = U._corpo_js(js, u"vrAcervo")
    checar(u"o acervo é a tabela da Suite (`uiTabelaAcervo`), aberta pelo "
           u"«Abrir» dela", u"uiTabelaAcervo(" in ac
           and u"aoAbrir: vrAbrirDoAcervo" in ac, ac[:160])

    def tabela_propria(j):
        j = _sem_comentarios_js(j)
        return any(m in j for m in (u"VR_COLUNAS", u"function vrLinhaDoAcervo(",
                                    u"function vrPreencher(", u"/api/ver/acervo"))
    checar(u"  e a tabela própria antiga saiu (colunas, linha, detalhes e a "
           u"rota)", not tabela_propria(js))
    checar(u"  (isca) a tabela própria de volta reprova",
           tabela_propria(js + u"\nvar VR_COLUNAS = ['ID'];\n"))
    import radai_view as _rv
    pg = _rv._pagina()
    checar(u"  e o contêiner é o da Suite (`data-ui-acervo`), na aba do acervo",
           re.search(r'<div class="ui-acervo[^"]*" id="vr_acervo" data-ui-acervo>',
                     pg) is not None)
    checar(u"a demo saiu do acervo: sem a linha DEMO e sem abrir a demo",
           u"vrLinhaDaDemo" not in js and u"vrAbrirDemo" not in js
           and u"vr-demo" not in js and u"VR_DEMOS" not in js)
    ab = U._corpo_js(js, u"vrAbrirDoAcervo")
    checar(u"«Abrir» liga o carregamento no visor, e não escreve «abrindo» no item 1",
           u"vrCarregandoVisor(true)" in ab and u"abrindo a série" not in ab)
    checar(u"«Abrir» manda só o bilhete da linha (nem pasta, nem UID)",
           u"JSON.stringify({bilhete: linha.bilhete})" in ab
           and u"pasta:" not in ab and u".pasta" not in ab
           and u".uid" not in ab, ab[:200])


def _busca_propria(js):
    j = _sem_comentarios_js(js)
    return u"fetch('/api/verseg/series'" in j or u"/api/verseg/series" in j


def _series_pela_casca(pasta):
    import radai_varrer
    import radai_view
    radai_view.registrar_varredura()
    d = radai_varrer.iniciar(radai_view.USO_DA_VARREDURA, pasta, dias=0,
                             em_segundo_plano=False)
    return {u"series": list(d.get(u"linhas") or []), u"erro": d.get(u"erro")}


def teste_a_pasta_e_a_varredura_da_casca():
    secao(u"«Aponte uma pasta»: a varredura da casca, só com as séries contornadas")
    import radai_view
    import radai_viewseg
    import radai_varrer
    import make_test_series
    from datetime import datetime
    js = radai_view.JS
    vr = U._corpo_js(js, u"vrVarrer")
    checar(u"a busca é a lista que cresce da casca (uiVarrerLista), com o uso "
           u"«verseg» e o filtro de data", u"window.uiVarrerLista(" in vr
           and u"@USO_JS@" in vr and radai_view.USO_DA_VARREDURA == u"verseg"
           and u"'vr_dias'" in vr and u"pintar:" in vr, vr[:160])
    checar(u"e o POST único antigo saiu da tela", not _busca_propria(js))
    checar(u"  (isca) o POST único de volta reprova",
           _busca_propria(js + u"\nfetch('/api/verseg/series', {});\n"))
    _app_s, _cli_s = _app()
    checar(u"  e a rota dele saiu do servidor (só a varredura da casca lista)",
           u"/api/verseg/series" not in set(
               getattr(r, "path", u"") for r in _app_s.routes)
           and _cli_s.post(u"/api/verseg/series", json={}).status_code
           in (404, 405))
    p = radai_view._pagina()
    checar(u"o popup tem o filtro de data e a estrela da pasta favorita",
           u'id="vr_dias"' in p and u'data-ui-dias' in p
           and u'data-ui-fav="vr_pasta"' in p)
    checar(u"a série que chega de outra tela é procurada em todas as datas",
           u"vrVarrer({dias: 0})" in js)

    base, pasta, uid = U._ver_serie_com_rtstructs()
    for n in os.listdir(pasta):
        if n.startswith(u"RS_RadAI_") and n.endswith(u"_00000001.dcm"):
            os.rename(os.path.join(pasta, n), os.path.join(
                pasta, n.replace(u"_00000001.dcm", u"_%s.dcm" % uid[-8:])))
    solta = os.path.join(base, u"_irma")
    irma = make_test_series.escreve_serie(solta, u"PAC_VER", datetime.now(), 20)
    for n in os.listdir(solta):
        shutil.move(os.path.join(solta, n), os.path.join(pasta, u"IRMA_" + n))
    os.rmdir(solta)
    vazia = os.path.join(base, u"PAC_SEM", u"CT")
    make_test_series.escreve_serie(vazia, u"PAC_SEM", datetime.now(), 20)
    radai_view.registrar_varredura()
    d = radai_varrer.iniciar(radai_view.USO_DA_VARREDURA, base, dias=0,
                             em_segundo_plano=False)
    e = radai_varrer.estado(d.get(u"v"))
    linhas = e.get(u"linhas") or []
    checar(u"só a série com RTSTRUCT RadAI ao lado volta",
           [l.get(u"uid") for l in linhas] == [uid],
           str([(l.get(u"uid") or u"")[-8:] for l in linhas]))
    l0 = (linhas or [{}])[0]
    velha, _erro = radai_viewseg.series_contornadas(pasta)
    checar(u"  com os mesmos arquivos que a busca antiga dava",
           [r.get(u"arquivo") for r in l0.get(u"rs") or ()]
           == [r.get(u"arquivo") for r in (velha or [{}])[0].get(u"rs") or ()]
           and l0.get(u"rs"), str([r.get(u"cod") for r in l0.get(u"rs") or ()]))
    checar(u"  com o bilhete do visor, e a modalidade guardada para ele",
           l0.get(u"b") and l0.get(u"b") == l0.get(u"bilhete")
           and radai_viewseg._MODALIDADE.get(l0.get(u"b")) == u"CT")
    checar(u"  e a pasta não vai à tela", not any(u"pasta" in l for l in linhas))
    checar(u"a série irmã, na mesma pasta e sem RTSTRUCT dela, fica de fora",
           irma not in [l.get(u"uid") for l in linhas])
    checar(u"  (isca) sem saber das irmãs da pasta, ela levaria os RTSTRUCT da outra",
           bool(radai_viewseg.arquivos_contornados(pasta, irma, ())))
    z = radai_varrer.iniciar(radai_view.USO_DA_VARREDURA,
                             os.path.join(base, u"NAO_EXISTE.zip"), dias=0,
                             em_segundo_plano=False)
    ze = radai_varrer.estado(z.get(u"v"))
    checar(u"pasta ou .zip que não existe responde o erro, sem lista",
           ze.get(u"erro") and not ze.get(u"linhas"), str(ze.get(u"erro")))


def _app():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    import radai_view
    import radai_viewseg
    import radai_tabela_acervo
    app = FastAPI()
    radai_viewseg.montar(app)
    radai_view.montar(app)
    radai_tabela_acervo.montar(app)
    return app, TestClient(app)


def _mapa_sintetico(pasta, uid, forma):
    import numpy as np
    import radai_rotulos
    cora = np.zeros(forma, dtype=bool)
    cora[5:11, 50:71, 50:71] = True
    figado = np.zeros(forma, dtype=bool)
    figado[3:8, 80:91, 20:41] = True
    nod = np.zeros(forma, dtype=bool)
    nod[9:10, 30:33, 30:33] = True
    return radai_rotulos.gravar(pasta, uid, {
        "total": {"heart": cora, "liver": figado},
        "lung_nodules": {"lung_nodules": nod}},
        protocolos=("anatomia_geral",), achados=("lung_nodules",))


def teste_o_servidor():
    secao(u"o servidor: acervo, detalhes lidos na hora, mapa, ficha (sem demo)")
    import radai_archive
    import radai_fichas
    import radai_viewseg as V
    import make_test_series
    from datetime import datetime
    base, pasta, uid = U._ver_serie_com_rtstructs()
    demo = tempfile.mkdtemp(prefix="radai_vs_demo_")
    try:
        app, cli = _app()
        radai_archive.registrar_serie(uid, pasta, u"RS_RadAI_20260926_00000001.dcm",
                                      date=u"20260926", pid=u"PAC_VER",
                                      estruturas=7, secs=95)
        os.makedirs(os.path.join(pasta, u"_RadAI"), exist_ok=True)
        io.open(os.path.join(pasta, u"_RadAI", uid + u".done.json"), u"w",
                encoding=u"utf-8").write(json.dumps({
                    u"uid": uid, u"modo": u"perso", u"cortes": 20,
                    u"tasks_ok": [u"total_v3", u"trunk_cavities"],
                    u"protocolos": [u"torax"]}))
        dpasta = os.path.join(demo, u"lctsc", u"CT")
        duid = make_test_series.escreve_serie(dpasta, u"DEMO", datetime.now(), 6)
        io.open(os.path.join(demo, u"MANIFESTO.json"), u"w", encoding=u"utf-8").write(
            json.dumps({u"demos": [{u"id": u"lctsc", u"titulo": u"LCTSC demo",
                                    u"modulos": [u"Ver segmentação"],
                                    u"licenca": u"CC BY 3.0",
                                    u"atribuicao": u"Yang et al., TCIA",
                                    u"series": [
                                        {u"pasta": u"lctsc/CT", u"modalidade": u"CT",
                                         u"cortes": 6},
                                        {u"pasta": u"lctsc/CT", u"modalidade": u"RTSTRUCT",
                                         u"cortes": 1}]}]}))

        import radai_thumbnail
        ac = cli.post(u"/api/acervo/tabela", json={}).json()
        linhas = ac.get(u"series") or []
        checar(u"a tabela do acervo traz a série",
               [s.get(u"uid8") for s in linhas] == [uid[-8:]], str(ac)[:200])
        checar(u"e nao traz a demo",
               "demos" not in ac, str(ac)[:200])
        pj = json.dumps(pasta)[1:-1]
        checar(u"a tabela não leva o nome do paciente, a pasta nem o UID inteiro",
               u"FANTOMA" not in json.dumps(ac) and pj not in json.dumps(ac)
               and uid not in json.dumps(ac))
        bil = (linhas or [{}])[0].get(u"bilhete") or u""
        ab = cli.post(u"/api/ver/abrir", json={u"bilhete": bil}).json()
        sa = ab.get(u"serie") or {}
        checar(u"«Abrir» pelo bilhete devolve a série da linha, com o bilhete "
               u"do visor e os arquivos dela",
               sa.get(u"uid") == uid and sa.get(u"b") and sa.get(u"rs"),
               str(ab)[:200])
        checar(u"  e a resposta não leva a pasta", u"pasta" not in sa
               and pj not in json.dumps(ab), str(sorted(sa))[:200])
        fora_b = radai_thumbnail.bilhete(dpasta, duid)
        ab2 = cli.post(u"/api/ver/abrir", json={u"bilhete": fora_b}).json()
        checar(u"  (isca) bilhete de série que o acervo não conhece não abre "
               u"(a pasta da demo)", ab2.get(u"serie") is None, str(ab2)[:200])
        ab3 = cli.post(u"/api/ver/abrir", json={u"bilhete": u"f" * 32}).json()
        checar(u"  (isca) bilhete morto não abre", ab3.get(u"serie") is None,
               str(ab3)[:200])

        de = cli.post(u"/api/acervo/tabela/detalhes", json={u"bilhetes": [
            bil, fora_b]}).json()
        it = (de.get(u"itens") or [{}])[0]
        checar(u"o nome do paciente é lido na hora, da série",
               it.get(u"nome") == u"FANTOMA TESTE", str(it))
        checar(u"  e a modalidade, a espessura, os cortes, o modo e as tasks",
               it.get(u"modalidade") == u"CT" and it.get(u"espessura_mm") == 3.0
               and it.get(u"cortes") == 20 and it.get(u"modo") == u"perso"
               and it.get(u"tasks") == [u"total_v3", u"trunk_cavities"]
               and it.get(u"protocolos") == [u"torax"], str(it))
        fora = (de.get(u"itens") or [{}, {}])[1]
        checar(u"par que o acervo não conhece volta vazio (isca: a pasta da demo)",
               not fora.get(u"nome") and not fora.get(u"modalidade"), str(fora))
        indice = io.open(str(radai_archive.caminho_acervo()), encoding=u"utf-8").read()
        checar(u"o nome nunca vai ao índice do acervo", u"FANTOMA" not in indice)

        s1 = _series_pela_casca(dpasta)
        checar(u"a marca de demo nao abre mais serie sem contorno",
               not (s1.get(u"series") or []), str(s1)[:200])

        _mapa_sintetico(pasta, uid, (20, 128, 128))
        s = (_series_pela_casca(pasta).get(u"series") or [{}])[0]
        rs = s.get(u"rs") or []
        mapa = [r for r in rs if r.get(u"cod") == u"rotulos"]
        checar(u"o mapa de rótulos entra como um conjunto a mais",
               len(mapa) == 1 and mapa[0].get(u"curto") == u"Estudo 3D"
               and len(rs) == 6, str([r.get(u"cod") for r in rs]))
        b = s.get(u"b")
        arq = mapa[0][u"arquivo"] if mapa else u""
        es = cli.get(u"/api/verseg/estruturas", params={u"b": b, u"rs": arq}).json()
        por = dict((e[u"nome"], e) for e in es.get(u"estruturas") or [])
        checar(u"as estruturas do mapa, com cortes e o selo de achado",
               sorted(por) == [u"heart", u"liver", u"lung_nodules"]
               and por[u"heart"][u"cortes"] == 6 and por[u"liver"][u"cortes"] == 5
               and por[u"lung_nodules"][u"achado"] is True
               and por[u"heart"][u"achado"] is False, str(es)[:240])
        co = cli.get(u"/api/verseg/contornos", params={u"b": b, u"rs": arq,
                                                       u"corte": 7}).json()
        h = [x for x in co.get(u"estruturas") or [] if x[u"n"] == u"heart"]
        nums = [int(v) for v in re.findall(r"\d+", h[0][u"d"])] if h else []
        xs = re.findall(r"M(\d+) (\d+)h(\d+)", h[0][u"d"]) if h else []
        x0 = min(int(a) for a, _b, _n in xs) if xs else -1
        x1 = max(int(a) + int(n) for a, _b, n in xs) if xs else -1
        checar(u"o contorno do mapa segue a borda dos pixels (x de 50 a 71)",
               co.get(u"rs") == arq and x0 == 50 and x1 == 71, str(co)[:200])
        checar(u"  e o fígado não aparece no corte 7 (ele vai de 3 a 7, isca no 8)",
               any(x[u"n"] == u"liver" for x in co.get(u"estruturas") or [])
               and not any(x[u"n"] == u"liver" for x in cli.get(
                   u"/api/verseg/contornos", params={u"b": b, u"rs": arq,
                                                    u"corte": 8}).json()
                   .get(u"estruturas") or []), str(nums[:4]))
        ce = cli.get(u"/api/verseg/centro", params={u"b": b, u"rs": arq,
                                                    u"nome": u"heart"}).json()
        checar(u"o centro da estrutura do mapa (corte 7,5; x 60)",
               abs(float(ce.get(u"z", -9)) - 7.5) < 1e-6
               and abs(float(ce.get(u"x", -9)) - 60.0) < 1e-6, str(ce))
        outro = io.open(os.path.join(pasta, u"_RadAI", u"rotulos_%s.npz" % uid[-8:]),
                        u"rb").read()
        V._MAPA[u"chave"] = None
        checar(u"  (isca) o mapa com o UID de outra série não entra",
               V._item_do_mapa(pasta, uid + u"9") is None and bool(outro))

        r = cli.post(u"/api/verseg/recon3d", json={
            u"b": b, u"rs": u"RS_RadAI_FULL_20260926_00000001.dcm",
            u"estruturas": [u"Heart_ai", u"Inventada_ai", u"Heart_ai"]}).json()
        f = radai_fichas.ler(r.get(u"ficha") or u"") or {}
        checar(u"a ficha leva a série, o arquivo e só as estruturas que ele tem",
               f.get(u"origem") == u"verseg" and bool(f.get(u"pasta"))
               and os.path.samefile(f.get(u"pasta"), pasta)
               and f.get(u"uid") == uid and f.get(u"tipo") == u"rtstruct"
               and f.get(u"arquivo") == u"RS_RadAI_FULL_20260926_00000001.dcm"
               and f.get(u"estruturas") == [u"Heart_ai"]
               and r.get(u"url") == u"/recon3d/anatomia?ficha=%s" % r.get(u"ficha"),
               str(r) + str(f))
        rm = cli.post(u"/api/verseg/recon3d", json={
            u"b": b, u"rs": arq, u"estruturas": [u"heart"]}).json()
        fm = radai_fichas.ler(rm.get(u"ficha") or u"") or {}
        checar(u"  e do mapa, com o tipo «rotulos»",
               fm.get(u"tipo") == u"rotulos" and fm.get(u"estruturas") == [u"heart"],
               str(rm))
        for nome, corpo in ((u"arquivo de fora da série", {u"b": b, u"rs": u"..\\x.dcm",
                                                          u"estruturas": [u"Heart_ai"]}),
                            (u"bilhete morto", {u"b": u"f" * 32, u"rs": arq,
                                                u"estruturas": [u"heart"]}),
                            (u"nenhuma estrutura que o arquivo tem",
                             {u"b": b, u"rs": arq, u"estruturas": [u"x"]})):
            rr = cli.post(u"/api/verseg/recon3d", json=corpo).json()
            checar(u"  (isca) %s é recusado" % nome, rr.get(u"erro") and not rr.get(u"ficha"),
                   str(rr))
    finally:
        shutil.rmtree(base, ignore_errors=True)
        shutil.rmtree(demo, ignore_errors=True)


_ORG_STUBS = u"""
function Cls(){ this.s = {}; }
Cls.prototype.add = function(k){ this.s[k] = 1; };
Cls.prototype.remove = function(k){ delete this.s[k]; };
Cls.prototype.contains = function(k){ return !!this.s[k]; };
function No(){ this.classList = new Cls(); this.children = []; this.parentNode = null;
 this.attrs = {}; this.firstChild = null; this.textContent = ''; }
No.prototype.setAttribute = function(k, v){ this.attrs[k] = v; };
No.prototype.removeAttribute = function(k){ delete this.attrs[k]; };
No.prototype.appendChild = function(c){ c.parentNode = this; this.children.push(c); };
No.prototype.removeChild = function(c){ this.children = this.children.filter(function(x){ return x !== c; }); c.parentNode = null; };
Object.defineProperty(No.prototype, 'innerHTML', {set: function(v){ this.firstChild = new No(); }});
Object.defineProperty(No.prototype, 'className', {set: function(v){
 var eu = this; String(v).split(/\\s+/).forEach(function(k){ if(k) eu.classList.add(k); }); }});
var document = {createElement: function(){ return new No(); }};
var window = {};
function getComputedStyle(){ return {position: 'relative'}; }
function requestAnimationFrame(f){ setTimeout(f, 0); }
function $(id){ return null; }
function traduzir(){}
"""

_ORG_RODA = u"""
var E = new No(), F = new No(), R = {};
window.uiCarregando(E, true, 'a');
window.uiCarregando(F, true, 'a');
window.uiCarregando(F, false);
setTimeout(function(){
 window.uiCarregando(E, false);
 window.uiCarregando(E, true, 'b');
 setTimeout(function(){
  var c = E.children[0], g = F.children[0];
  console.log('JSON:' + JSON.stringify({n: E.children.length,
   vis: !!(c && c.classList.contains('vis')),
   nf: F.children.length, visf: !!(g && g.classList.contains('vis'))}));
 }, 400);
}, 60);
"""


def _funcao_atribuida(js, nome):
    i = js.find(u"window.%s = function(" % nome)
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
                return js[i:j + 1] + u";"
    return u""


def teste_o_carregamento_religado_nao_some():
    secao(u"o carregamento orgânico desligado e religado em seguida continua")
    import radai_ui
    node = U._node()
    if not node:
        checar(u"node disponível", False, u"PULADO")
        return
    f = _funcao_atribuida(radai_ui.COMPONENTES_JS, u"uiCarregando")

    def roda(fonte):
        d, _e = U._rodar_node(_ORG_STUBS + fonte + _ORG_RODA, node)
        return d or {}
    d = roda(f)
    checar(u"religado logo depois de desligar, ele fica na tela (visível)",
           d.get(u"n") == 1 and d.get(u"vis") is True, str(d))
    checar(u"desligado antes de a entrada terminar, ele sai e não volta",
           d.get(u"nf") == 0 and d.get(u"visf") is False, str(d))
    isca = f.replace(u"clearTimeout(c._uiApaga); c._uiTira = null;",
                     u"c._uiTira = null;")
    isca = isca.replace(u"if(tira._uiLigado) return;", u"")
    di = roda(isca)
    checar(u"  (isca) sem cancelar a remoção pendente ele some",
           isca != f and not (di.get(u"n") == 1 and di.get(u"vis") is True), str(di))
    isca2 = f.replace(u"if(nova._uiLigado) nova.classList.add('vis')",
                      u"nova.classList.add('vis')").replace(
                          u"!tira._uiLigado", u"!tira.classList.contains('vis')")
    d2 = roda(isca2)
    checar(u"  (isca) a entrada atrasada reacende o desligado",
           isca2 != f and not (d2.get(u"nf") == 0 and d2.get(u"visf") is False), str(d2))


_AO_LADO = (
    (u"RS_RadAI_NV_20260926_00000001.dcm", u"STUDY_nv", u"nv", u"Heart_nv"),
    (u"RS_RadAI_CADS_20260926_00000001.dcm", u"STUDY_cads", u"cads", u"Heart_cds"),
    (u"RS_RadAI_MSE_20260926_00000001.dcm", u"STUDY_mse", u"mse", u"Heart_mse"),
    (u"RS_RadAI_HNL_20260926_00000001.dcm", u"STUDY_hnl", u"hnl", u"LNL01_lnl"),
    (u"RS_RadAI_LVS_20260926_00000001.dcm", u"STUDY_lvs", u"lvs", u"Vessel_lvs"),
)


def teste_os_conjuntos_ao_lado_abrem():
    secao(u"os conjuntos ao lado (TS cru, NV, CADS, MOOSE, níveis, plugins) abrem")
    import radai_viewseg as V
    base, pasta, uid = U._ver_serie_com_rtstructs()
    try:
        for arq, rot, _cod, nome in _AO_LADO:
            U._ver_rs_sintetico(os.path.join(pasta, arq), rot, (
                (nome, (200, 120, 40), (5, 8), (30, 30, 50, 50)),))
        _app_, cli = _app()
        s = (_series_pela_casca(pasta).get(u"series") or [{}])[0]
        cods = [r.get(u"cod") for r in s.get(u"rs") or []]
        checar(u"todos os arquivos da série estão no seletor, na ordem da tela",
               cods == [u"oar", u"fast", u"full", u"ts", u"nv", u"cads", u"mse",
                        u"hnl", u"orb", u"lvs"], str(cods))
        for arq, _rot, cod, nome in _AO_LADO + ((u"RS_RadAI_TS_20260926_00000001.dcm",
                                                u"", u"ts", u"heart_ts"),):
            e = cli.get(u"/api/verseg/estruturas", params={u"b": s.get(u"b"),
                                                           u"rs": arq}).json()
            c = cli.get(u"/api/verseg/contornos", params={u"b": s.get(u"b"),
                                                          u"rs": arq, u"corte": 6}).json()
            checar(u"  o %s abre num visor, com a estrutura dele" % cod,
                   [x[u"nome"] for x in e.get(u"estruturas") or []] == [nome]
                   and [x[u"n"] for x in c.get(u"estruturas") or []] == [nome],
                   str(e)[:120] + str(c)[:120])
    finally:
        shutil.rmtree(base, ignore_errors=True)


def teste_as_bordas_do_mapa():
    secao(u"a borda dos pixels: anel, ilha e canto")
    import numpy as np
    import radai_viewseg as V
    m = np.zeros((6, 6), dtype=bool)
    m[1:5, 1:5] = True
    m[2:4, 2:4] = False
    d = V.bordas_svg(m, 10, 20)
    hs = re.findall(r"M(\d+) (\d+)h(\d+)", d)
    vs = re.findall(r"M(\d+) (\d+)v(\d+)", d)
    tot_h = sum(int(c) for _a, _b, c in hs)
    tot_v = sum(int(c) for _a, _b, c in vs)
    checar(u"o anel: 12 de borda horizontal e 12 de vertical (fora e dentro)",
           tot_h == 12 and tot_v == 12, u"%s | %s" % (hs, vs))
    checar(u"  com o deslocamento da caixa (x 21..25, y 11..15)",
           min(int(a) for a, _b, _c in hs) == 21 and min(int(b) for _a, b, _c in hs) == 11
           and max(int(a) for a, _b, _c in vs) == 25, d)
    checar(u"máscara vazia não desenha nada", V.bordas_svg(np.zeros((3, 3), bool)) == u"")
    um = np.zeros((1, 1), bool)
    um[0, 0] = True
    checar(u"um pixel só é um quadrado de lado 1",
           V.bordas_svg(um) == u"M0 0h1M0 1h1M0 0v1M1 0v1", V.bordas_svg(um))


def teste_as_mascaras_da_serie():
    secao(u"C6: as máscaras de uma série (a que o Nidus usa para o osso)")
    import numpy as np
    import radai_batch
    import radai_viewseg as V
    base, pasta, uid = U._ver_serie_com_rtstructs()
    try:
        full = os.path.join(pasta, u"RS_RadAI_FULL_20260926_00000001.dcm")
        desta = os.path.join(pasta, u"RS_RadAI_FULL_20260926_%s.dcm"
                             % uid.replace(u".", u"")[-8:])
        _ct, img = radai_batch._abrir_ct(pasta, uid)
        forma = (20, 128, 128)
        so_cor = lambda n: n == u"Heart_ai"
        sem, info0 = V.mascaras_da_serie(pasta, uid, img, aceita=so_cor)
        checar(u"(isca) sem o UID desta série no nome do arquivo, nada sai "
               u"(o FULL de outra série da pasta não serve)",
               sem is None and info0.get(u"motivo") == V.SEM_SEGMENTACAO,
               str(info0))
        shutil.copy2(full, desta)
        m, info = V.mascaras_da_serie(pasta, uid, img, aceita=so_cor)
        checar(u"o FULL desta série devolve a máscara da estrutura aceita",
               m is not None and tuple(m.shape) == forma
               and info.get(u"fonte") == u"FULL" and info.get(u"cod") == u"full"
               and info.get(u"estruturas") == 1
               and info.get(u"nomes") == [u"Heart_ai"]
               and info.get(u"arquivo") == os.path.basename(desta), str(info))
        zs = sorted(set(np.nonzero(m)[0].tolist())) if m is not None else []
        checar(u"  só nos cortes do contorno (5 a 10), com o centro dentro e a "
               u"borda fora", zs == list(range(5, 11)) and bool(m[7, 60, 60])
               and not bool(m[7, 10, 10]), str(zs))
        checar(u"  e com a área do quadrado (40 x 40 pixels por corte)",
               m is not None and abs(int(m[7].sum()) - 1600) <= 81,
               str(int(m[7].sum()) if m is not None else None))
        checar(u"  e a informação não leva caminho",
               json.dumps(pasta)[1:-1] not in json.dumps(info))
        dois, i2 = V.mascaras_da_serie(
            pasta, uid, img, aceita=lambda n: n in (u"Heart_ai", u"Lung_L_ai"))
        checar(u"duas estruturas aceitas viram a união",
               dois is not None and i2.get(u"estruturas") == 2
               and int(dois.sum()) > int(m.sum()) and bool((dois & m).sum()
                                                         == m.sum()), str(i2))
        nada, i3 = V.mascaras_da_serie(pasta, uid, img, aceita=lambda n: False)
        checar(u"(isca) nenhuma estrutura aceita: nada, e o motivo",
               nada is None and i3 == {u"tem": False,
                                       u"motivo": V.SEM_SEGMENTACAO}, str(i3))
        su, isu = V.mascaras_da_serie(pasta, u"", img)
        checar(u"sem UID não procura", su is None
               and isu.get(u"motivo") == V.SEM_UID, str(isu))
        sp, isp = V.mascaras_da_serie(os.path.join(base, u"nao_existe"), uid, img)
        checar(u"pasta que não existe não levanta", sp is None
               and isp.get(u"motivo") == V.SEM_SEGMENTACAO, str(isp))

        try:
            import radai_nidus as N
        except Exception:
            N = None
        if N is None:
            checar(u"o radai_nidus importável para a paridade", False, u"PULADO")
        else:
            lido = V._rs_lido(desta, V._geometria(img))
            ref = np.zeros(forma, dtype=bool)
            for roi in lido.get(u"rois") or ():
                if roi.get(u"nome") == u"Heart_ai":
                    N.mascara_dos_cortes(roi[u"cortes"], forma, destino=ref)
            checar(u"a máscara é a mesma que o rasterizador do Nidus dá",
                   m is not None and np.array_equal(m, ref))
            anel = {3: [np.array([(10.5, 10.5), (50.5, 10.5), (50.5, 50.5),
                                  (10.5, 50.5)], np.float32),
                        np.array([(20.5, 20.5), (40.5, 20.5), (40.5, 40.5),
                                  (20.5, 40.5)], np.float32)],
                    4: [np.array([(5.2, 7.9), (60.1, 12.3), (30.7, 55.5)],
                                 np.float32)],
                    9: [np.array([(1.0, 1.0), (9.0, 1.0), (9.0, 9.0)],
                                 np.float32)]}
            a = V._mascara_dos_cortes(anel, (8, 64, 64),
                                      np.zeros((8, 64, 64), dtype=bool))
            b = N.mascara_dos_cortes(anel, (8, 64, 64))
            checar(u"  e no anel (o furo fica furo), no triângulo inclinado e "
                   u"no corte fora da série, pixel a pixel",
                   np.array_equal(a, b) and bool(a[3, 15, 15])
                   and not bool(a[3, 30, 30]) and bool(a[4].any()),
                   u"%d %d" % (int(a.sum()), int(b.sum())))

        _mapa_sintetico(pasta, uid, forma)
        mm, im = V.mascaras_da_serie(pasta, uid, img,
                                     aceita=lambda n: n == u"heart",
                                     conjuntos=())
        checar(u"sem RTSTRUCT pedido, o mapa de rótulos (Estudo 3D) responde",
               mm is not None and im.get(u"fonte") == V.CURTO_MAPA
               and im.get(u"estruturas") == 1
               and int(mm.sum()) == 6 * 21 * 21, str(im))
        sm, ism = V.mascaras_da_serie(pasta, uid, img,
                                      aceita=lambda n: n == u"heart",
                                      conjuntos=(), com_mapa=False)
        checar(u"  (isca) com_mapa=False não lê o mapa", sm is None, str(ism))
        mf, imf = V.mascaras_da_serie(
            pasta, uid, img, aceita=lambda n: n in (u"Heart_ai", u"heart"))
        checar(u"com os dois, o FULL vem antes do mapa",
               imf.get(u"fonte") == u"FULL", str(imf))
    finally:
        shutil.rmtree(base, ignore_errors=True)


def _serie_rm(pasta, iop, n=8, lado=32, pico=None):
    import numpy as np
    import pydicom
    from pydicom.dataset import Dataset, FileMetaDataset
    from pydicom.uid import generate_uid, ExplicitVRLittleEndian
    os.makedirs(pasta, exist_ok=True)
    linha = np.asarray(iop[:3], dtype=float)
    coluna = np.asarray(iop[3:], dtype=float)
    normal = np.cross(linha, coluna)
    serie, estudo = generate_uid(), generate_uid()
    for k in range(n):
        ds = Dataset()
        ds.file_meta = FileMetaDataset()
        ds.SOPClassUID = u"1.2.840.10008.5.1.4.1.1.4"
        ds.SOPInstanceUID = generate_uid()
        ds.file_meta.MediaStorageSOPClassUID = ds.SOPClassUID
        ds.file_meta.MediaStorageSOPInstanceUID = ds.SOPInstanceUID
        ds.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
        ds.Modality = u"MR"
        ds.PatientName = u"FANTOMA^RM"
        ds.PatientID = u"FANTOMA_RM"
        ds.StudyInstanceUID = estudo
        ds.SeriesInstanceUID = serie
        ds.FrameOfReferenceUID = estudo
        ds.InstanceNumber = k + 1
        ds.ImagePositionPatient = [float(v) for v in
                                   np.array([-20.0, -30.0, 10.0]) + 3.0 * k * normal]
        ds.ImageOrientationPatient = [float(v) for v in iop]
        ds.PixelSpacing = [1.0, 1.0]
        ds.SliceThickness = 3.0
        ds.Rows = ds.Columns = lado
        ds.SamplesPerPixel = 1
        ds.PhotometricInterpretation = u"MONOCHROME2"
        ds.BitsAllocated = ds.BitsStored = 16
        ds.HighBit = 15
        ds.PixelRepresentation = 0
        img = np.full((lado, lado), 300 + 10 * k, dtype=np.uint16)
        if pico:
            img[lado // 2, lado // 2] = pico
        ds.PixelData = img.tobytes()
        pydicom.dcmwrite(os.path.join(pasta, u"MR_%02d.dcm" % k), ds,
                         enforce_file_format=True)
    return serie


def teste_a_rm_abre_no_visor():
    secao(u"a RM (axial e sagital) abre no «Ver segmentação»: a série não é "
          u"filtrada como TC")
    import numpy as np
    import radai_batch
    import radai_thumbnail
    import radai_viewseg as V
    base = tempfile.mkdtemp(prefix=u"radai_vs_rm_")
    try:
        app, cli = _app()
        for rotulo, iop in ((u"axial", (1, 0, 0, 0, 1, 0)),
                            (u"sagital", (0, 1, 0, 0, 0, -1))):
            pasta = os.path.join(base, rotulo)
            uid = _serie_rm(pasta, iop, pico=40000)
            todos = [os.path.join(pasta, f) for f in sorted(os.listdir(pasta))]
            checar(u"(isca) %s: o filtro de antes (modalidade CT) não acha "
                   u"nenhum corte da RM" % rotulo,
                   len(radai_batch._so_da_serie(todos, uid)) == 0)
            ct, img = radai_batch._abrir_ct(pasta, uid)
            checar(u"%s: a RM abre com os oito cortes" % rotulo,
                   tuple(ct.shape) == (8, 32, 32), str(ct.shape))
            checar(u"%s: o pixel acima de 32767 satura e não dá a volta "
                   u"para negativo" % rotulo,
                   int(ct.max()) == 32767 and int(ct.min()) >= 0,
                   u"%d %d" % (int(ct.min()), int(ct.max())))
            b = radai_thumbnail.bilhete(pasta, uid)
            V._MODALIDADE[b] = u"MR"
            V._SERIE[u"chave"] = None
            f = cli.get(u"/api/verseg/forma", params={u"b": b}).json()
            checar(u"%s: /api/verseg/forma responde a forma, sem HU" % rotulo,
                   f.get(u"forma") == [8, 32, 32] and f.get(u"hu") is False,
                   str(f))
            r = cli.get(u"/api/verseg/ct", params={u"b": b, u"corte": 4})
            checar(u"%s: /api/verseg/ct devolve o PNG do corte (o «não "
                   u"consegui carregar a imagem deste corte» de campo)" % rotulo,
                   r.status_code == 200
                   and r.content[:8] == b"\x89PNG\r\n\x1a\n",
                   u"%s %s" % (r.status_code, r.headers.get(u"X-RadAI-Erro")))
        V._SERIE[u"chave"] = None
    finally:
        shutil.rmtree(base, ignore_errors=True)


def teste_o_visor_nao_abre_serie_parcial():
    secao(u"a lista progressiva nao abre parcial nem apaga o visor atual")
    import radai_view
    node = U._node()
    if not node:
        checar(u"node disponivel", False, u"PULADO")
        return
    funcoes = u"\n".join(u"function %s(%s){%s}\n" % (
        nome, args, U._corpo_js(radai_view.JS, nome)) for nome, args in (
            (u"vrSerieDisponivel", u"s"), (u"vrPintar", u""),
            (u"vrAbrirSerie", u"lista,i")))
    base = u"""
var ELS = {}, VR = {series:[], escolhida:-1}, VR_CONJ = [];
var CP = {serie:{b:'ANTERIOR'}}, ABRIU = 0, FECHOU = 0, PEDIU = 0;
var window = {};
function vrEl(id){ return ELS[id] || (ELS[id] = {innerHTML:'',className:''}); }
function esc(x){ return String(x == null ? '' : x); }
function vrDataBr(x){ return x || ''; }
function vrPopup(){ return {fechar:function(){ FECHOU++; }}; }
function vrCarregandoVisor(){}
function cpAbrirSerie(s){ CP.serie = s; ABRIU++; PEDIU++; }
"""
    roda = u"""
VR.series = [{uid:'SINTETICO', cortes:2, carregando:true, bilhete:null}];
vrPintar();
var R = {parcialDesabilitada:ELS.vr_tab.innerHTML.indexOf(' disabled') >= 0,
 lendo:ELS.vr_tab.innerHTML.indexOf('Lendo os cortes da série…') >= 0};
vrAbrirSerie(VR.series, 0);
R.preservou = CP.serie.b === 'ANTERIOR' && !ABRIU && !FECHOU && !PEDIU;
VR.series = [{uid:'SINTETICO', cortes:20, carregando:false, b:'COMPLETA',rs:[]}];
vrPintar();
R.habilitou = ELS.vr_tab.innerHTML.indexOf(' disabled') < 0;
vrAbrirSerie(VR.series, 0);
R.abriuCompleta = CP.serie.b === 'COMPLETA' && ABRIU === 1 && PEDIU === 1;
console.log('JSON:' + JSON.stringify(R));
"""
    d, erro = U._rodar_node(base + funcoes + roda, node)
    checar(u"a parcial fica desabilitada com estado traduzivel de leitura",
           d and d.get("parcialDesabilitada") and d.get("lendo"), erro)
    checar(u"abrir parcial por chamada direta preserva serie e nao pede b vazio",
           d and d.get("preservou"), erro)
    checar(u"a mesma linha finalizada habilita e abre com bilhete completo",
           d and d.get("habilitou") and d.get("abriuCompleta"), erro)
    isca = funcoes.replace(u"if(!vrSerieDisponivel(s)) return;", u"")
    ruim, _e = U._rodar_node(base + isca + roda, node)
    checar(u"ISCA: sem a guarda, abrir parcial apaga o visor e pede imagem",
           isca != funcoes and ruim and not ruim.get("preservou"))


def main():
    print(u"=" * 68)
    print(u"test_verseg | o «Ver segmentação» da v8.4")
    print(u"=" * 68)
    testes = [teste_a_tela_segue_o_padrao, teste_a_tela_nao_cita_tps,
              teste_o_comparador_executado, teste_a_roda_vai_para_caudal,
              teste_o_acervo_e_o_seletor_no_js,
              teste_a_pasta_e_a_varredura_da_casca,
              teste_as_bordas_do_mapa, teste_o_servidor,
              teste_os_conjuntos_ao_lado_abrem,
              teste_o_carregamento_religado_nao_some,
              teste_as_mascaras_da_serie,
              teste_a_rm_abre_no_visor, teste_o_visor_nao_abre_serie_parcial]
    import traceback
    for t in testes:
        try:
            t()
        except Exception as e:
            checar(u"%s (exceção inesperada)" % t.__name__, False,
                   u"%s: %s" % (type(e).__name__, e))
            traceback.print_exc()
    falhas = [(n, d) for n, ok, d in _RES if not ok]
    print(u"\n" + u"=" * 68)
    if falhas:
        print(u"FALHOU: %d de %d checagens" % (len(falhas), len(_RES)))
        for n, d in falhas:
            print(u"  - %s%s" % (n, (u"  [%s]" % d) if d else u""))
    else:
        print(u"OK: %d checagens, todas passaram" % len(_RES))
    print(u"=" * 68)
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
