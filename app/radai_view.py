# -*- coding: utf-8 -*-
import radai_menu

CSS = u"""
.wrap{max-width:1500px;margin:0 auto;padding:0 16px 26px 16px}
button{font:inherit;font-size:12.5px;padding:7px 13px;border-radius:6px;
 border:1px solid var(--line-strong,#2a3a55);background:var(--panel-2,#0f1729);
 color:var(--text,#e6edf7);cursor:pointer}
button:hover{border-color:var(--accent,#4DA3FF);color:var(--text,#e6edf7)}
button:focus-visible{outline:2px solid var(--accent,#4DA3FF);outline-offset:2px}
button[disabled]{opacity:.45;cursor:not-allowed}
.vr .ui-bt.mini{padding:5px 12px;font-size:12px}
.rc-frase{color:var(--text-muted);font-size:13px;line-height:1.65;margin:0 0 14px 0}
.vr-lista{max-height:330px;overflow:auto;border:1px solid var(--line);
 border-radius:8px;margin-top:10px}
.vr-lista table{width:100%;border-collapse:collapse;font-size:12px}
.vr-lista thead th{position:sticky;top:0;z-index:1;background:var(--panel-2,#0f1729);
 text-align:left;padding:7px 9px;font-family:var(--mono,monospace);font-size:9.5px;
 letter-spacing:.11em;text-transform:uppercase;color:var(--text-dim);
 border-bottom:1px solid var(--line);white-space:nowrap}
.vr-lista td{padding:6px 9px;border-bottom:1px solid rgba(255,255,255,.05);
 vertical-align:middle}
.vr-lista tr:hover{background:rgba(77,163,255,.06)}
.vr-lista tr.on{background:rgba(77,163,255,.14)}
.vr-lista .num{font-family:var(--mono,monospace);text-align:right}
.vr-conj{display:flex;gap:6px;flex-wrap:wrap;min-width:300px}
.vr-conj .cj{font-size:10px;padding:2px 7px;border-radius:99px;
 border:1px solid var(--line);color:var(--text-dim);white-space:nowrap}
.vr-conj .cj.tem{border-color:var(--accent);color:var(--text)}
.vr-conj .cj.entregue{background:rgba(77,163,255,.16);font-weight:600}
.vr-vazio{border:1px dashed var(--line);border-radius:10px;padding:26px;
 text-align:center;color:var(--text-dim);font-size:12.5px;line-height:1.6}
.vr-vazio b{display:block;color:var(--text-muted);font-size:13.5px;margin-bottom:6px}

.vr-rolar{max-height:420px;overflow:auto}
.vr .ps-cx{min-width:0}
.vr-rolar{scrollbar-color:var(--line-strong) transparent}
.vr-lista td.vr-acao,.vr-lista th.vr-acao{position:sticky;right:0;z-index:2;
 background:var(--panel);text-align:right;box-shadow:-1px 0 0 var(--line)}
.vr-lista thead th.vr-acao{z-index:3;background:var(--panel-2)}
.vr-busca{display:flex;gap:10px;align-items:flex-end;flex-wrap:wrap}
.vr-campo{flex:1 1 240px;min-width:0}
.vr-busca input{width:100%;box-sizing:border-box}
.vr-busca label{display:block;font-size:11px;color:var(--text-dim);
 margin:0 0 4px;font-family:var(--font-mono,monospace);text-transform:uppercase;
 letter-spacing:.3px}
.vr-bts{display:flex;gap:6px;flex-wrap:wrap}
.vr .vr-busca{align-items:flex-start}
.vr .vr-bts{padding-top:19px}
.vr .vr-bts .ui-bt{min-height:34px}
#vr_msg,#vr_acervo_msg{font-size:12.5px;color:var(--text-dim)}
.vr-lista td{white-space:nowrap}
/* GUARDA: a ação é a última coluna e fica pregada à direita (`sticky`); sem
   isso, com a tabela rolando de lado, o Abrir sai da vista. */
.vr-acao{width:1%;white-space:nowrap}
.vr-sub{font-size:13px;font-weight:650;margin:16px 0 0;color:var(--text);
 display:flex;align-items:center;gap:8px}
.vr .oculto{display:none !important}
.vr-serie{margin:6px 0 16px}
.vr-ps{position:relative}
.vr-ps-ajuda{position:absolute;right:4px;top:8px;z-index:2}
"""

PAGINA = u"""<!doctype html><html><head><meta charset="utf-8">
<title>Ver segmentação · Radioterapia.AI</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
@VERCSS@
@VISORCSS@
</style></head><body><div class="wrap vr">

@CABECA@



<div class="vr-serie" id="cx_vr0">@CARTAO@</div>

@VERSEG@

@ALERTA@

</div>
@POPUP@
<script>
@VISORJS@
@VERSEGJS@
@VERJS@
</script>
</body></html>"""

ACERVO_HTML = u"""
 @TABELA@
 <div id="vr_acervo_msg" class="sub" role="status" style="margin-top:8px"></div>
"""

PASTA_HTML = u"""
 <div class="vr-busca">
  <div class="vr-campo">
   <label for="vr_pasta">Pasta do exame, ou o <b>.zip</b> dele</label>
   <input type="text" id="vr_pasta" spellcheck="false"
    placeholder="cole o caminho da pasta, ou use o Procurar ao lado">
  </div>
  <div class="vr-bts">
   <button type="button" class="ui-bt" id="vr_procurar" onclick="vrProcurar(this)">Procurar&hellip;</button>
   <button type="button" class="ui-bt pri" onclick="vrVarrer()">Buscar contornadas</button>
  </div>
 </div>
 <div id="vr_msg" class="sub" role="status" style="margin-top:8px"></div>
 <h3 class="vr-sub oculto" id="vr_sub_encontradas">Séries encontradas
  <span class="ui-ajuda dir" tabindex="0" aria-label="ajuda">?<span class="ui-balao"><p>Aparecem só as séries que já têm contorno ao lado — um RTSTRUCT ou o mapa de rótulos dos estudos 3D. Série sem contorno é o assunto do <b>Rodar agora</b>.</p><p>Cada série grava um arquivo por conjunto que rodou — o OAR, o FULL, o TS cru e um por modelo ou plugin —, e as marcas ao lado dizem quais existem. O <b>Radioterapia.ai_OAR</b> (ou o <b>OAR_Fast</b>, do modo FAST) é a seleção voltada para radioterapia; os outros são estudo.</p></span></span></h3>
 <div id="vr_vazio" class="vr-vazio oculto"></div>
 <div id="vr_lista" class="vr-lista oculto"><table id="vr_tab"></table></div>
"""

JS = u"""
var VR = {series: [], escolhida: -1, uidPedido: '', handoff: false};
function vrPopup(){ return window.uiPopupSerie ? uiPopupSerie('vr_escolha') : null }

function esc(s){
 return String(s == null ? '' : s)
  .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/"/g,'&quot;');
}

// GUARDA: quem lista é o servidor, por POST e só pastas; caminho de paciente não vai em GET.
function vrProcurar(bt){
 var campo = vrEl('vr_pasta');
 if(!window.uiExplorador){ vrMsg('não consegui abrir o seletor de pastas', false); return; }
 window.uiExplorador({titulo: 'Escolher a pasta', origem: bt || null,
  inicial: ((campo && campo.value) || '').trim(),
  aoUsar: function(c){
   if(!c) return;
   if(campo) campo.value = c;
   vrVarrer();
  }});
}
document.addEventListener('keydown', function(ev){
 if(ev.key === 'Enter' && ev.target && ev.target.id === 'vr_pasta'){
  ev.preventDefault(); vrVarrer();
 }
});

function vrEl(id){ return document.getElementById(id) }
function vrMsg(t, ok){
 var e = vrEl('vr_msg');
 if(window.uiTexto) window.uiTexto(e, t || ''); else e.textContent = t || '';
 try{ if(window.radaiRetraduzir) window.radaiRetraduzir() }catch(x){}
 e.style.color = (ok === false) ? 'var(--perigo,#E96A5C)' : 'var(--text-dim)';
}



function vrDataBr(d){
 d = (d==null?'':(''+d)).trim();
 var m = /^(\\d{4})(\\d{2})(\\d{2})/.exec(d);
 return m ? (m[3]+'/'+m[2]+'/'+m[1]) : d;
}
var VR_TABELA = null;
function vrAcervo(){
 if(window.uiPopupSerie)
  uiPopupSerie('vr_escolha', {sozinho: function(){ return !VR.handoff }});
 if(window.psAbrir) psAbrir('cx_verseg');
 if(!window.uiTabelaAcervo || !vrEl('vr_acervo')) return;
 // GUARDA: uma frase por nó; o tradutor casa o texto inteiro do bloco.
 VR_TABELA = window.uiTabelaAcervo('vr_acervo', {aoAbrir: vrAbrirDoAcervo,
  vazio: '<p class="sub"><span data-radai-frase>Para contornar uma, vá ao</span> '
   + '<a href="/lote">Rodar agora</a>.</p>'
   + '<p class="sub">Para ver uma série contornada em outra estação, use a aba Aponte uma pasta.</p>'});
}

function vrAcervoMsg(t, ok){
 var e = vrEl('vr_acervo_msg'); if(!e) return;
 if(window.uiTexto) window.uiTexto(e, t || ''); else e.textContent = t || '';
 e.style.color = (ok === false) ? 'var(--perigo,#E96A5C)' : 'var(--text-dim)';
}
function vrCarregandoVisor(ligado){
 try{
  var cx = vrEl('cx_verseg'), raiz = vrEl('cp_raiz');
  var aberto = !!(raiz && raiz.classList && !raiz.classList.contains('cp-oculto'));
  var alvos = aberto ? [vrEl('cp_visor0'), vrEl('cp_visor1')] : [vrEl('cp_vazio')];
  if(!ligado) alvos = [vrEl('cp_vazio'), vrEl('cp_visor0'), vrEl('cp_visor1')];
  if(ligado && window.psAbrir) window.psAbrir('cx_verseg');
  alvos.forEach(function(a){
   if(a && window.uiCarregando) window.uiCarregando(a, !!ligado, 'abrindo a série…');
  });
  if(ligado && cx && cx.scrollIntoView) cx.scrollIntoView({block: 'start', behavior: 'smooth'});
 }catch(e){}
}
function vrMarcarAcervo(i){
 try{ if(VR_TABELA) VR_TABELA.marcar(i == null ? null : i) }catch(e){}
}
function vrFalhaAoAbrir(e){
 vrCarregandoVisor(false);
 // GUARDA: a frase e a exceção em nós separados; colados, não casam a chave.
 var m = vrEl('vr_acervo_msg'); if(!m) return;
 var h = '<span data-radai-frase>não consegui abrir a série</span> <code></code>';
 if(window.uiHTML) window.uiHTML(m, h); else m.innerHTML = h;
 m.querySelector('code').textContent = String((e && e.message) || e || '');
 m.style.color = 'var(--perigo,#E96A5C)';
}
// GUARDA: a linha do acervo leva só o bilhete; a pasta e o UID ficam no servidor.
function vrAbrirDoAcervo(linha, i){
 if(!linha || !linha.bilhete) return;
 vrAcervoMsg('');
 vrCarregandoVisor(true);
 fetch('/api/ver/abrir', {method:'POST',
   headers:{'Content-Type':'application/json'},
   body: JSON.stringify({bilhete: linha.bilhete})})
  .then(function(r){ return r.json() })
  .then(function(d){
   var s = d && d.serie;
   if(!s){
    vrCarregandoVisor(false);
    vrMarcarAcervo(null);
    vrAcervoMsg('a série não está mais nesta pasta', false);
    return;
   }
   vrMarcarAcervo(i);
   VR.escolhida = -1;
   if(VR.series.length) vrPintar();
   vrAbrirSerie([s], 0);
  })
  .catch(vrFalhaAoAbrir);
}
document.addEventListener('DOMContentLoaded', vrAcervo);

function vrVarrer(){
 var p = (vrEl('vr_pasta').value || '').trim();
 if(!p){ vrMsg('diga onde procurar', false); return; }
 vrMsg('procurando séries contornadas…');
 vrEl('vr_lista').className = 'vr-lista oculto';
 vrEl('vr_vazio').className = 'vr-vazio oculto';
 vrEl('vr_sub_encontradas').className = 'vr-sub oculto';
 fetch('/api/verseg/series', {method:'POST',
   headers:{'Content-Type':'application/json'},
   body: JSON.stringify({pasta: p})})
  .then(function(r){ return r.json() })
  .then(function(d){
   VR.series = d.series || [];
   if(d.erro && !VR.series.length){
    if(VR.handoff){ VR.handoff = false; VR.uidPedido = ''; vrEscolherDeNovo(); }
    vrEl('vr_vazio').innerHTML = '<b>Nenhuma série contornada aqui</b>'
      + esc(d.erro) + '<div style="margin-top:12px">'
      + '<a class="btn pri" href="/lote">Ir para o Rodar agora</a></div>';
    vrEl('vr_vazio').className = 'vr-vazio';
    vrEl('vr_sub_encontradas').className = 'vr-sub';
    vrMsg('');
    return;
   }
   vrMsg('%s série(s) com contorno'.replace('%s', VR.series.length));
   vrEl('vr_sub_encontradas').className = 'vr-sub';
   vrPintar();
   if(VR.uidPedido){
    var k = -1;
    VR.series.forEach(function(x, j){ if(k < 0 && x.uid === VR.uidPedido) k = j; });
    VR.uidPedido = '';
    if(k >= 0){ VR.escolhida = k; vrPintar(); vrAbrirSerie(VR.series, k); }
    else vrEscolherDeNovo();
   } else if(VR.handoff) vrEscolherDeNovo();
   VR.handoff = false;
  })
  .catch(function(e){
   if(VR.handoff){ VR.handoff = false; vrEscolherDeNovo(); }
   var m = vrEl('vr_msg'); if(!m) return;
   var h = '<span data-radai-frase>não consegui procurar nesta pasta</span> <code></code>';
   if(window.uiHTML) window.uiHTML(m, h); else m.innerHTML = h;
   m.querySelector('code').textContent = String((e && e.message) || e || '');
   m.style.color = 'var(--perigo,#E96A5C)';
  });
}

var VR_CONJ = @CONJUNTOS@;

function vrPintar(){
 var h = '<thead><tr><th>ID</th><th>Data do exame</th>'
       + '<th class="num">Cortes</th>'
       + '<th class="num">Espessura</th><th>Série</th><th>Conjuntos entregues</th>'
       + '<th class="vr-acao"></th></tr></thead><tbody>';
 VR.series.forEach(function(s, i){
  var tem = {};
  (s.rs || []).forEach(function(r){ tem[vrCodDe(r.arquivo)] = true });
  var chips = VR_CONJ.filter(function(c){
    return !(c.plugin || c.so_se_tem) || tem[c.cod] })
   .map(function(c){
   var cl = 'cj' + (tem[c.cod] ? ' tem' : '') + (c.entregue ? ' entregue' : '');
   return '<span class="' + cl + '" title="' + esc(c.ajuda || '') + '">'
        + (tem[c.cod] ? '' : '&middot; ') + esc(c.rotulo_curto) + '</span>';
  }).join('');
  h += '<tr class="linha' + (i === VR.escolhida ? ' on' : '') + '" data-i="' + i + '">'
     + '<td>' + esc(s.pid || '—') + '</td><td>' + esc(vrDataBr(s.date) || '—') + '</td>'
     + '<td class="num">' + (s.cortes || 0) + '</td>'
     + '<td class="num">' + (s.espessura_mm == null ? '—' : esc(s.espessura_mm + ' mm')) + '</td>'
     + '<td class="sub" style="font-family:var(--mono,monospace)">…' + esc(s.curto || '') + '</td>'
     + '<td><div class="vr-conj">' + chips + '</div></td>'
     + '<td class="vr-acao"><button type="button" class="ui-bt mini" data-abrir="' + i + '">Abrir</button></td></tr>';
 });
 vrEl('vr_tab').innerHTML = h + '</tbody>';
 vrEl('vr_lista').className = 'vr-lista';
}

function vrCodDe(nome){
 var resto = (nome || '').indexOf('RS_RadAI_') === 0
   ? nome.substring(9) : (nome || '');
 for(var i = 0; i < VR_CONJ.length; i++){
  var c = VR_CONJ[i];
  if(c.infixo && resto.indexOf(c.infixo) === 0) return c.cod;
 }
 if(/^[0-9]{8}/.test(resto) || resto.indexOf('semdata_') === 0) return 'oar';
 if((nome || '').indexOf('rotulos_') === 0) return 'rotulos';
 return '';
}

document.addEventListener('click', function(ev){
 var b = ev.target.closest ? ev.target.closest('[data-abrir]') : null;
 if(!b) return;
 var i = +b.getAttribute('data-abrir');
 VR.escolhida = i;
 vrPintar();
 vrMarcarAcervo(null);
 vrAbrirSerie(VR.series, i);
});

function vrEscolherDeNovo(){
 var p = vrPopup(); if(p) p.abrir(vrEl('vr_cartao'));
}
function vrAbrirSerie(lista, i){
 var s = (lista || [])[i];
 if(!s) return;
 var pp = vrPopup(); if(pp) pp.fechar();
 if(window.uiCartaoRotulo)
  uiCartaoRotulo('vr_cartao', [vrDataBr(s.date), s.pid, s.desc]
   .filter(function(x){ return x }).join(' · '));
 var q = vrEl('cp_qual');
 if(q){
  // GUARDA: rótulo e valor em nós separados; frase composta não casa a chave.
  var h = '<span translate="no">' + esc(s.desc || '—') + '</span> · '
    + '<span data-radai-frase>Cortes</span> ' + esc(s.cortes || 0)
    + (s.espessura_mm == null ? '' : (' · <span data-radai-frase>Espessura</span> '
       + esc(s.espessura_mm) + ' mm'));
  if(window.uiHTML) window.uiHTML(q, h); else q.innerHTML = h;
 }
 vrCarregandoVisor(false);
 if(window.psAbrir) psAbrir('cx_verseg');
 if(typeof cpAbrirSerie === 'function') cpAbrirSerie(s);
 var cx = vrEl('cx_verseg');
 if(cx && cx.scrollIntoView){
  try{ cx.scrollIntoView({block: 'start', behavior: 'smooth'}); }catch(e){}
 }
}

(function(){
 try{
  var p = sessionStorage.getItem('radai_ver_pasta');
  var u = sessionStorage.getItem('radai_ver_uid') || '';
  sessionStorage.removeItem('radai_ver_uid');
  if(!p) return;
  sessionStorage.removeItem('radai_ver_pasta');
  var alvo = document.getElementById('vr_pasta');
  if(!alvo) return;
  if(window.uiGuia) window.uiGuia('vr_guias', 'pasta');
  alvo.value = p;
  VR.uidPedido = u;
  VR.handoff = true;
  if(typeof vrVarrer === 'function'){ vrVarrer(); }
 }catch(e){}
})();
"""


def _conjuntos_da_tela():
    import radai_sets
    import radai_viewseg
    plugins = tuple(getattr(radai_sets, "PLUGINS", ()))
    modos = tuple(getattr(radai_sets, "SAIDAS_DE_MODO", ()))
    fonte = tuple(radai_sets.CONJUNTOS) + modos + plugins
    ordem = radai_viewseg.ORDEM

    def _peso(par):
        i, c = par
        cod = c["cod"]
        if cod in ordem:
            return (0, ordem.index(cod), i)
        return (1 if c in plugins else 0, len(ordem), i)
    fora = []
    for _i, c in sorted(enumerate(fonte), key=_peso):
        cod = c["cod"]
        plugin = bool(c.get("plugin") or c in plugins)
        de_modo = c in modos
        fora.append({"cod": cod, "infixo": c["infixo"],
                     "rotulo_curto": (radai_viewseg.CURTO_DA_TELA.get(cod)
                                      if cod in (u"full", u"fast")
                                      else c["rotulo_curto"]),
                     "entregue": bool(c.get("entregue")), "ajuda": c["ajuda"],
                     "plugin": plugin,
                     "so_se_tem": plugin or de_modo})
    fora.append({"cod": radai_viewseg.COD_MAPA, "infixo": u"",
                 "rotulo_curto": radai_viewseg.CURTO_MAPA,
                 "entregue": False, "ajuda": radai_viewseg.ROTULO_MAPA,
                 "plugin": False, "so_se_tem": True})
    return fora


def _pagina():
    import json
    css_visor, js_visor, bloco, js_verseg = u"", u"", u"", u""
    try:
        import radai_viewseg
        bloco = radai_viewseg.bloco(numero=u"2")
        css_visor = css_visor + radai_viewseg.CSS
        js_verseg = radai_viewseg.JS
    except Exception as e:
        bloco = (u'<section class="ps-cx"><h2 class="ps-cab">'
                 u'<span class="ps-num">2</span>Visor</h2><div class="ps-corpo">'
                 u'indisponível nesta instalação (%s)</div></section>'
                 % type(e).__name__)
    try:
        conj = json.dumps(_conjuntos_da_tela(), ensure_ascii=False)
    except Exception:
        conj = u"[]"
    cabeca, guias, ajuda_serie, alerta = _partes_do_padrao()
    import radai_ui
    cartao = radai_ui.cartao_de_serie(u"vr_cartao", u"vr_escolha",
                                      u"Escolha a série",
                                      chave_modulo=u"autocontorno", numero=u"1")
    popup = radai_ui.popup_de_serie(
        u"vr_escolha", u'<div class="vr-ps"><div class="vr-ps-ajuda">%s</div>%s</div>'
        % (ajuda_serie, guias), sozinho=True)
    return (PAGINA.replace("@VERCSS@", CSS)
                  .replace("@VISORCSS@", css_visor)
                  .replace("@VISORJS@", js_visor)
                  .replace("@VERSEGJS@", js_verseg)
                  .replace("@VERJS@", JS.replace("@CONJUNTOS@", conj))
                  .replace("@CABECA@", cabeca)
                  .replace("@CARTAO@", cartao)
                  .replace("@POPUP@", popup)
                  .replace("@ALERTA@", alerta)
                  .replace("@VERSEG@", bloco))


ICONE = u"&#9673;"
NOME = u"Ver segmentação"
FRASE = (u"Avalie os resultados comparando diferentes processamentos em cortes "
         u"axiais lado a lado, e veja como eles se comportam.")
AJUDA = (
    u"Escolha uma série já contornada — no Acervo Local desta estação ou "
    u"apontando a pasta de outra — e ela abre em dois visores axiais, no "
    u"mesmo corte.",
    u"Cada visor mostra um arquivo da série: o OAR, o FULL, o TS cru, os "
    u"outros modelos, os plugins e o mapa de rótulos dos estudos 3D. Ligue, "
    u"desligue e espelhe as estruturas de um lado no outro, ou leve o "
    u"conjunto visível às Reconstruções 3D.",
    u"Aqui se olha: nada nesta tela mede, aprova ou grava.",
)
AJUDA_DA_SERIE = (
    u"No Acervo Local estão as séries que este programa contornou nesta "
    u"estação.",
    u"Série contornada em outra estação não aparece no acervo: para essa, "
    u"use a aba Aponte uma pasta.",
    u"O nome do paciente, a modalidade e a espessura são lidos da série na "
    u"hora em que a lista abre, e não ficam gravados no acervo.",
)


def _acervo_html():
    try:
        import radai_tabela_acervo
        tabela = radai_tabela_acervo.html(u"vr_acervo", u"vr-rolar")
    except Exception:
        tabela = u'<div class="ui-acervo vr-rolar" id="vr_acervo"></div>'
    return ACERVO_HTML.replace(u"@TABELA@", tabela)


def _partes_do_padrao():
    import radai_ui
    import radai_modules
    cabeca = radai_ui.cabeca_de_funcao(ICONE, NOME, FRASE,
                                       radai_ui.ajuda(*AJUDA),
                                       u"autocontorno")
    guias = radai_ui.abas_de_serie(u"vr_guias", [
        (u"acervo", u"Acervo Local", _acervo_html()),
        (u"pasta", u"Aponte uma pasta", PASTA_HTML),
    ], padrao=u"acervo", cor_var=u"--mod-auto")
    return (cabeca, guias, radai_ui.ajuda(*AJUDA_DA_SERIE, direita=True),
            radai_modules.linha_clinica(u"autocontorno"))


def serie_do_acervo(bilhete):
    import radai_tabela_acervo
    import radai_viewseg
    pasta, uid = radai_tabela_acervo.resolver(bilhete)
    if not pasta:
        return None
    lista, _erro = radai_viewseg.series_contornadas(pasta)
    for s in lista:
        if str(s.get("uid") or u"") != str(uid):
            continue
        s = radai_viewseg.anotar_bilhete(dict(s))
        s.pop("pasta", None)
        return s
    return None


def montar(app):
    from fastapi import Request
    from fastapi.responses import HTMLResponse

    @app.post("/api/ver/abrir")
    async def _api_abrir(request: Request):
        try:
            c = await request.json() or {}
            b = str((c or {}).get("bilhete") or u"")
            import radai_web
            s = await radai_web.no_threadpool(serie_do_acervo, b)
        except Exception as e:
            return {"serie": None, "erro": type(e).__name__}
        if not s:
            return {"serie": None, "erro": u"a série não está mais no acervo"}
        return {"serie": s}

    @app.get("/ver", response_class=HTMLResponse)
    def _tela():
        return radai_menu.aplicar(_pagina(), "ver")

    return app
