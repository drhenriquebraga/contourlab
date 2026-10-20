# -*- coding: utf-8 -*-
import radai_menu

CSS = u"""
.pr-wrap{max-width:1160px;margin:0 auto;padding:0 18px 44px 18px}
.pr-bloco{border:1px solid var(--line);border-radius:12px;padding:14px 16px;
 margin:16px 0;background:var(--panel,#0c1322)}
.pr-bloco>h2{margin:0 0 10px 0;font-size:15px;letter-spacing:-.01em}
.pr-bloco p{margin:6px 0;font-size:12.5px;line-height:1.6;color:var(--text-muted)}
.pr-bloco code{font-family:var(--mono,monospace);font-size:11.5px;
 color:var(--text,#e6edf7)}
.pr-bloco ul{margin:6px 0 6px 18px;padding:0;font-size:12.5px;
 line-height:1.6;color:var(--text-muted)}
.pr-cursores,.pr-conta{display:flex;gap:8px;flex-wrap:wrap;margin:6px 0 10px}
.pr-cursores .p,.pr-conta .p{border:1px solid var(--line);border-radius:8px;
 padding:6px 12px;font-size:11.5px;color:var(--text-dim)}
.pr-cursores .p b,.pr-conta .p b{color:var(--text);font-family:var(--mono,monospace)}
.pr-cursores .p.em-uso{border-color:var(--accent,#4DA3FF)}
.pr-bloco p.pr-nota{font-size:11px;color:var(--text-dim);margin:4px 0 8px}
.pr-bloco p.pr-nota code{font-size:10.5px;color:var(--text-dim)}
.pr-alerta{border:1px solid rgba(255,200,87,.45);background:rgba(255,200,87,.07);
 border-radius:10px;padding:10px 13px;margin:8px 0;font-size:12.5px;
 line-height:1.6;color:var(--text-muted)}
.pr-alerta b{color:var(--warn,#E1B23B)}
.pr-alerta code{overflow-wrap:anywhere;word-break:break-all}
.pr-tab{width:100%;border-collapse:collapse;margin-top:6px}
.pr-tab th{text-align:left;font-size:9.5px;letter-spacing:.1em;
 text-transform:uppercase;color:var(--text-dim);padding:7px 10px;
 border-bottom:1px solid var(--line);position:sticky;top:0;
 background:var(--panel,#0c1322)}
.pr-tab td{padding:7px 10px;border-bottom:1px solid rgba(255,255,255,.05);
 vertical-align:top;font-size:12.5px;color:var(--text-muted)}
.pr-tab td b{color:var(--text,#e6edf7);font-weight:600}
.pr-tab .est{font-family:var(--mono,monospace);font-size:11.5px;
 color:var(--text,#e6edf7);white-space:nowrap}
.pr-larga{overflow-x:auto;max-width:100%}
.pr-tab .tag{display:inline-block;font-size:10.5px;color:var(--text-dim);
 max-width:100%;white-space:normal;overflow-wrap:anywhere;
 border:1px solid var(--line);border-radius:6px;padding:0 6px;margin:2px 4px 0 0}
.pr-tab .tag.aviso{color:var(--warn,#E1B23B);border-color:rgba(255,200,87,.4)}
.pr-tab .lic{display:block;font-size:10px;color:var(--text-dim)}
.pr-bloco p .lic{margin-left:6px;font-size:11px;color:var(--text-dim)}
.pr-tab .lic.restrito{color:var(--warn,#E1B23B)}
.pr-tab .porque{display:block;font-size:10.5px;color:var(--text-dim)}
.pr-tab .tag.achado{color:var(--perigo,#E96A5C);border-color:rgba(233,106,92,.45)}
.pr-barra{display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin:6px 0}
.pr-barra input[type=text]{padding:6px 10px;border-radius:7px;
 border:1px solid var(--line);background:var(--panel-2,#0f1729);color:var(--text);
 font-size:12px;min-width:0;flex:0 1 260px}
.pr-rolar{max-height:64vh;overflow:auto;border:1px solid var(--line);
 border-radius:10px}
#pr_msg{font-size:12.5px;margin-top:10px;line-height:1.55;color:var(--perigo,#E96A5C)}
@media (max-width:640px){
 .pr-wrap{padding:0 12px 32px 12px}
 .pr-tab .tps{display:none}
 .pr-tab td,.pr-tab th{padding:6px 6px}
}
"""

JS = u"""
var PR = {d: null, filtro: ''};
var PR_GRUPO = {osso:'osso', ar:'ar', alca:'alça', vaso:'vaso',
                musculo:'músculo', parenquima:'parênquima'};

function prEl(i){ return document.getElementById(i) }
function prEsc(t){ return String(t==null?'':t).replace(/&/g,'&amp;')
 .replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;') }
function prMm(v){
 if(v==null) return '?';
 var r = Math.round(Number(v)*100)/100;
 return (r === Math.floor(r)) ? r.toFixed(1) : String(r);
}
function prPor(el, html){
 if(!el) return;
 if(window.uiHTML) window.uiHTML(el, html); else el.innerHTML = html;
}
function prMsg(t){ var e = prEl('pr_msg'); if(e) e.textContent = t || '' }

function prCarregar(){
 fetch('/api/procedencia').then(function(r){ return r.json() })
  .then(function(d){
   if(d.erro){ prMsg(d.erro); return }
   PR.d = d; prAvisos(); prSuav(); prOrigem(); prRegras(); prBib(); prTabela();
  })
  .catch(function(e){ prMsg(String(e)) });
}

function prAvisos(){
 var h = '';
 (PR.d.avisos || []).forEach(function(a){
  h += '<div class="pr-alerta"><b>AVISO</b> <span>' + prEsc(a.texto) + '</span>'
    + (a.detalhe ? ' <code>' + prEsc(a.detalhe) + '</code>' : '') + '</div>';
 });
 prPor(prEl('pr_avisos'), h);
}

function prCursor(rot, v, cls){
 return '<div class="p' + (cls ? ' ' + cls : '') + '"><span>' + rot
   + '</span> <b>' + prMm(v) + ' mm</b></div>';
}

var PR_ORIGEM = {
 processo: 'em uso nesta estação',
 arquivo: 'lido do arquivo: o vigia não informou',
 fabrica: 'de fábrica: nem o vigia nem o arquivo informaram',
 referencia: 'referência da tabela: nada foi lido'
};

function prRotulo(g){
 if(g.rotulos && g.rotulos.length)
  return g.rotulos.map(function(k){
   return '<span>' + prEsc(PR_GRUPO[k] || k) + '</span>' }).join(' · ');
 if(!g.tabela_mm) return '<span>não se suaviza</span>';
 return '—';
}

function prSuav(){
 var s = PR.d.suavizacao, h = '';
 h += '<div class="pr-cursores">'
   + prCursor(PR_ORIGEM[s.origem] || PR_ORIGEM.referencia, s.cursor_mm, 'em-uso')
   + ((s.no_arquivo_aplicado_mm != null && s.no_arquivo_aplicado_mm !== s.cursor_mm)
      ? prCursor('no arquivo, vale ao reiniciar', s.no_arquivo_aplicado_mm) : '')
   + (s.fabrica_mm != null ? prCursor('de fábrica', s.fabrica_mm) : '')
   + '</div>';
 if(s.fabrica_mm != null && s.fabrica_mm !== s.cursor_mm)
  h += '<div class="pr-alerta"><span>Esta estação está fora do padrão de fábrica.</span></div>';
 h += '<div class="pr-larga"><table class="pr-tab"><tr><th>grupo de borda</th><th>na tabela</th>'
   + '<th>nesta estação</th><th>estruturas</th></tr>';
 (s.grupos || []).forEach(function(g){
  h += '<tr><td><b>' + prRotulo(g) + '</b></td>'
    + '<td>' + prMm(g.tabela_mm) + ' mm</td>'
    + '<td><b>' + prMm(g.efetivo_mm) + ' mm</b></td>'
    + '<td>' + g.n + ' <span class="tag">' + prEsc((g.exemplos || []).join(', '))
    + '</span></td></tr>';
 });
 var st = s.sem_tabela || {};
 h += '<tr><td><span>sem entrada na tabela: vale o cursor</span></td><td>—</td>'
   + '<td><b>' + prMm(st.efetivo_mm) + ' mm</b></td><td>' + (st.n || 0)
   + ' <span class="tag">' + prEsc((st.exemplos || []).join(', ')) + '</span></td></tr>';
 h += '</table></div>';
 h += '<p class="pr-nota"><span>«na tabela» é a medida de cada grupo; «nesta estação» é o que o motor aplica: a tabela vezes o cursor em uso, dividido pela régua da tabela</span> <code>'
   + prMm(s.referencia_mm) + '</code></p>';
 h += '<ul>'
   + '<li><b>' + prMm(s.fina_mm) + ' mm</b> <span>raio inscrito mínimo para suavizar: abaixo dele a estrutura sai como o modelo a deu</span></li>'
   + '<li><b>1/' + prMm(s.divisor_do_raio) + '</b> <span>teto do sigma, como fração do raio inscrito medido na própria série</span></li>'
   + '</ul>';
 var d = s.derivacao || {};
 if(d.usa_o_cursor && (d.membros || []).length)
  h += '<div class="pr-alerta"><code>' + prEsc(d.membros.join(', '))
    + '</code> <b>' + prMm(s.cursor_mm) + ' mm</b> '
    + '<span>A mãe e a derivada saem suavizadas juntas, pelo cursor inteiro, e não pela tabela. É o que o motor faz hoje.</span></div>';
 if(s.conjuntos == null){
  h += '<p><span>Os conjuntos não responderam: ver o aviso no topo.</span></p>';
 } else {
  var sim = s.conjuntos.filter(function(c){ return c.suavizado })
    .map(function(c){ return c.nome });
  var nao = s.conjuntos.filter(function(c){ return !c.suavizado })
    .map(function(c){ return c.nome });
  h += '<p><span>Suaviza nestes conjuntos:</span> <code>' + prEsc(sim.join(', '))
    + '</code></p><p><span>Saem sem suavização:</span> <code>'
    + prEsc(nao.join(', ')) + '</code></p>';
 }
 prPor(prEl('pr_suav'), h);
}

function prMotor(m){
 if(!m) return '';
 return '<b>' + prEsc(m.nome) + '</b><span class="lic' + (m.restrito ? ' restrito' : '')
   + '">' + prEsc(m.licenca) + '</span>';
}

function prOrigem(){
 var o = PR.d.origem, c = o.conta || {}, h = '';
 h += '<div class="pr-conta">'
   + '<div class="p"><b>' + PR.d.total + '</b> <span>estruturas</span></div>'
   + '<div class="p"><b>' + (c.modelo || 0) + '</b> <span>direto do modelo</span></div>'
   + '<div class="p"><b>' + (c.composta || 0) + '</b> <span>compostas de outras</span></div>'
   + '<div class="p"><b>' + (c.derivada || 0) + '</b> <span>derivadas por marco anatômico</span></div>'
   + '<div class="p"><b>' + (c.construida || 0) + '</b> <span>construídas por função</span></div>'
   + '<div class="p"><b>' + (c.outro_motor || 0) + '</b> <span>de outro motor</span></div>'
   + '</div>';
 var as = o.assinadas || {}, ks = Object.keys(as).sort();
 if(ks.length){
  h += '<div class="pr-alerta"><b>ATENÇÃO</b> '
    + '<span>Há linhas assinadas no acervo desta estação, e o motor as aplica em toda série:</span><ul>';
  ks.forEach(function(k){
   var a = as[k];
   h += '<li><code>' + prEsc(k) + '</code> <b>' + prEsc(((o.motores || {})[a.modelo] || {}).nome || a.modelo)
     + '</b> <span class="tag">' + prEsc(a.quando || '') + '</span></li>';
  });
  h += '</ul><p><b>' + ks.length + '</b> <span>linha(s) assinada(s), lidas de</span> <code>'
    + prEsc(o.arquivo_assinado_caminho || o.arquivo_assinado) + '</code></p>'
    + '<p><span>Para voltar ao padrão de fábrica, apague ou renomeie este arquivo: o motor o relê a cada série.</span></p></div>';
 } else {
  h += '<p><span>Nenhuma linha assinada no acervo desta estação: vale o padrão de fábrica.</span></p>';
 }
 if(!(o.melhor_fonte || []).length && !(o.ambos || []).length){
  h += '<p><span>No padrão de fábrica, nenhuma estrutura vem de outro motor.</span></p>';
 } else {
  if((o.melhor_fonte || []).length)
   h += '<p><span>Vêm de outro motor no padrão de fábrica:</span> <code>'
     + prEsc(o.melhor_fonte.join(', ')) + '</code></p>';
  if((o.ambos || []).length)
   h += '<p><span>Comparação aberta, sai o nosso e o do outro motor:</span> <code>'
     + prEsc(o.ambos.join(', ')) + '</code></p>';
 }
 var ms = o.motores || {}, mk = Object.keys(ms).sort();
 if(mk.length){
  h += '<p>' + mk.map(function(k){ return prMotor(ms[k]) }).join(' ') + '</p>';
 }
 prPor(prEl('pr_origem'), h);
}

function prRegras(){
 var t = PR.d.entregue, L = [];
 function linha(est, regra, ref, onde){
  L.push('<tr><td class="est">' + prEsc(est) + '</td><td><span>' + regra
    + '</span></td><td>' + ref + '</td><td><span>' + onde + '</span></td></tr>');
 }
 var FULL = (t.construcoes != null);
 var ONDE = FULL ? 'no FULL e no OAR' : 'no entregue';
 if(t.desconta !== false) (t.descontadas || []).forEach(function(p){
  linha(p[1], 'perde o volume da outra', '<code>' + prEsc(p[0]) + '</code>',
        t.desconta === null ? 'não sei: ver o aviso no topo' : ONDE);
 });
 (t.contidas || []).forEach(function(p){
  linha(p[0], 'recortada para dentro da outra', '<code>' + prEsc(p[1]) + '</code>', 'em todos, menos o cru');
 });
 var rde = t.recorte_de || {};
 (t.recortes || []).forEach(function(p){
  var onde = (FULL && t.no_oar != null)
    ? ((t.no_oar.indexOf(p[0]) >= 0) ? 'no FULL e no OAR' : 'só no FULL')
    : ONDE;
  linha(p[0], 'cortada no plano do marco', '<code>' + prEsc(p[1].join(' | '))
    + '</code> <span class="tag">' + prEsc(p[2]) + '</span>'
    + (rde[p[0]] ? ' <span>a partir do rótulo de</span> <code>'
       + prEsc(rde[p[0]]) + '</code>' : ''), onde);
 });
 (t.margens || []).forEach(function(p){
  linha(p[0], 'ganha margem', '<b>+' + prMm(p[1]) + ' mm</b>', ONDE);
 });
 (t.refino || []).forEach(function(p){
  linha(p[0] + '*', 'cresce até a densidade do osso, só em TC', '<b>' + Math.round(p[1]) + ' HU</b>', ONDE);
 });
 var oar = {};
 (t.no_oar || []).forEach(function(n){ oar[n] = true });
 if(FULL){
  (t.construcoes || []).forEach(function(k){
   Object.keys(k.saidas || {}).sort().forEach(function(n){
    linha(n, k.so_tc ? 'construída por função, só em TC' : 'construída por função',
          '<code>' + prEsc(k.funcao) + '</code>',
          (t.no_oar == null) ? 'não sei: ver o aviso no topo'
          : (oar[n] ? 'no FULL e no OAR' : 'só no FULL'));
   });
  });
 } else {
  var pp = t.pele_e_parede;
  if(pp) (pp.nomes || []).forEach(function(n){
   linha(n, 'construída por função, só em TC', '<code>' + prEsc(pp.funcao) + '</code>', 'no entregue');
  });
 }
 var c = t.coracao;
 if(c){
  linha(c.estrutura, 'reconstruído: absorve a aorta ascendente e os vasos ao lado, só no intervalo do coração, e fecha o saco pericárdico',
        '<code>' + prEsc([c.aorta].concat(c.vasos || []).join(', ')) + '</code> <b>'
        + prMm(c.fechamento_mm) + ' mm</b>', ONDE);
  if(FULL){
   linha(c.aorta, 'a ascendente entra no coração; a descendente fica nos grandes vasos', '<code>' + prEsc(c.funcao) + '</code>', 'só no FULL');
   (c.vasos || []).forEach(function(v){
    linha(v, 'o trecho no intervalo do coração entra nele; a estrutura inteira fica no FULL', '<code>' + prEsc(c.funcao) + '</code>', 'só no FULL');
   });
  } else {
   linha(c.aorta, 'sai só a descendente: a ascendente entra no coração', '<code>' + prEsc(c.funcao) + '</code>', 'no entregue');
   (c.vasos || []).forEach(function(v){
    linha(v, 'o trecho no intervalo do coração entra nele, e a estrutura não sai separada', '<code>' + prEsc(c.funcao) + '</code>', 'no entregue');
   });
  }
  (c.cedem || []).forEach(function(v){
   linha(v, 'cede ao coração o que estiver dentro dele', '<code>' + prEsc(c.estrutura) + '</code>', ONDE);
  });
 }
 (t.compostos || []).forEach(function(p){
  linha(p[0], FULL ? 'no OAR, sai no lugar das partes; no FULL, os dois'
                   : 'sai no lugar das partes, quando existe na série',
        '<code>' + prEsc(p[1].join(', ')) + '</code>', ONDE);
 });
 var h = L.length
  ? '<div class="pr-larga"><table class="pr-tab"><tr><th>estrutura</th><th>regra</th><th>referência</th>'
    + '<th>onde</th></tr>' + L.join('') + '</table></div>'
  : '<p><span>Nenhuma regra além da suavização.</span></p>';
 prPor(prEl('pr_regras'), h);
}

var PR_GRUPO_RT = {nucleo:'rotina', util:'quando o serviço trata o sítio',
                   situacional:'situacional', fora:'fora de radioterapia'};
function prBib(){
 var b = PR.d.bibliotecas, h = '';
 if(!b){ prPor(prEl('pr_bib'), '<p><span>As bibliotecas não responderam: ver o aviso no topo.</span></p>'); return }
 h += '<div class="pr-cursores">'
   + '<div class="p"><span>TotalSegmentator</span> <b>' + prEsc(b.versao_ts || '?') + '</b></div>'
   + '<div class="p"><span>pesos nesta estação</span> <b>' + (b.no_disco || 0) + '/' + (b.tasks || []).length + '</b></div>'
   + '</div>';
 var rc = (b.recorte_no_corpo == null) ? '?' : String(b.recorte_no_corpo);
 h += '<p><code>RECORTE_NO_CORPO=' + prEsc(rc) + '</code> <span>O recorte no corpo (--body_seg) vem ligado de fábrica: antes de segmentar, o programa acha o corpo e processa só dentro dele. Ele muda a borda das estruturas e corta o tempo pela metade; por isso fica no arquivo de configuração, e o log de cada task diz se ele valeu.</span></p>';
 h += '<div class="pr-larga"><table class="pr-tab"><tr><th>task</th><th>o que segmenta</th>'
   + '<th>modalidade</th><th>peso</th><th>uso</th></tr>';
 (b.tasks || []).forEach(function(t){
  h += '<tr><td class="est">' + prEsc(t.task) + '</td>'
    + '<td><b>' + prEsc(t.rotulo) + '</b> <span class="tag">' + t.classes + '</span>'
    + (t.achado ? ' <span class="tag achado">ACHADO</span>' : '')
    + (t.permitida === false ? ' <span class="tag aviso"><span>não roda nesta instalação</span></span>'
       + (t.porque_nao ? '<span class="porque">' + prEsc(t.porque_nao) + '</span>' : '') : '')
    + '</td><td>' + prEsc(t.modalidade) + '</td>'
    + '<td>' + (t.mb || 0) + ' MB <span class="tag' + (t.baixado ? '' : ' aviso') + '"><span>'
    + (t.baixado ? 'no disco' : 'falta nesta estação') + '</span></span></td>'
    + '<td><span>' + prEsc(PR_GRUPO_RT[t.rt] || t.rt || '') + '</span></td></tr>';
 });
 h += '</table></div>';
 prPor(prEl('pr_bib'), h);
}

function prOrigemCelula(o){
 var h = '';
 if(o.tipo === 'modelo'){
  h = prMotor(o.motor) + ' <span class="tag">' + prEsc((o.tarefas || []).join(', ')) + '</span>';
 } else if(o.tipo === 'composta'){
  h = '<span>composta de</span> <code>' + prEsc((o.partes || []).join(', ')) + '</code>';
  if((o.direto_do_modelo_em || []).length)
   h += ' <span class="tag"><span>direto do modelo em</span> '
     + prEsc(o.direto_do_modelo_em.join(', ')) + '</span>';
 } else if(o.tipo === 'derivada'){
  h = '<span>derivada de</span> <code>' + prEsc(o.de) + '</code> <span class="tag">'
    + prEsc((o.marcos || []).join(' | ') + ' · ' + (o.extremo || '')) + '</span>';
 } else if(o.tipo === 'construida'){
  h = '<span>construída por</span> <code>' + prEsc(o.funcao) + '</code>'
    + (o.so_tc ? ' <span class="tag"><span>só em TC</span></span>' : '');
  if((o.a_partir_de || []).length)
   h += ' <span class="tag"><span>a partir do rótulo de</span> '
     + prEsc(o.a_partir_de.join(', ')) + '</span>';
 } else if(o.tipo === 'outro_motor'){
  h = prMotor(o.motor)
    + (o.assinada ? ' <span class="tag aviso">assinada</span>' : '')
    + ' <span class="tag"><span>sem ele</span>: ' + prEsc(
        o.sem_ele && o.sem_ele.tipo === 'modelo' ? (o.sem_ele.motor || {}).nome
        : (o.sem_ele || {}).tipo || '') + '</span>';
 } else {
  h = '<span>só existe se outro motor rodar</span>';
 }
 if(o.comparacao_com)
  h += ' <span class="tag aviso"><span>comparação aberta com</span> ' + prEsc(o.comparacao_com.nome) + '</span>';
 return h;
}

function prSuavCelula(s){
 var h = '<b>' + prMm(s.efetivo_mm) + ' mm</b>';
 if(s.tabela_mm == null) h += ' <span class="tag"><span>sem entrada: vale o cursor</span></span>';
 else h += ' <span class="tag"><span>tabela</span> ' + prMm(s.tabela_mm) + '</span>';
 if(s.na_derivacao && s.efetivo_mm !== s.tabela_x_cursor_mm)
  h += ' <span class="tag aviso"><span>junto com a derivação</span></span>';
 if(s.grupo_disjunto)
  h += ' <span class="tag"><span>fronteira partilhada</span> ' + prEsc(s.grupo_disjunto) + '</span>';
 return h;
}

function prEntregueCelula(t){
 var h = [], inc = t.desconto_incerto ? ' aviso' : '', q = t.desconto_incerto ? ' ?' : '';
 if(t.construida) h.push(t.construida.so_tc === false
   ? '<span class="tag aviso"><span>construída por função</span></span>'
   : '<span class="tag aviso"><span>construída, só em TC</span></span>');
 if(t.reconstruida) h.push('<span class="tag aviso"><span>reconstruída; absorve:</span> '
   + prEsc([t.reconstruida.aorta].concat(t.reconstruida.vasos || []).join(', ')) + '</span>');
 if(t.so_a_descendente) h.push('<span class="tag aviso"><span>só a descendente</span></span>');
 if(t.descendente_em) h.push('<span class="tag"><span>a descendente fica em</span> '
   + prEsc(t.descendente_em.join(', ')) + '</span>');
 if(t.absorvida_pelo_coracao) h.push('<span class="tag aviso"><span>absorvida pelo coração</span></span>');
 if(t.no_oar === true) h.push('<span class="tag"><span>no OAR</span></span>');
 if(t.no_oar === false) h.push('<span class="tag"><span>só no FULL</span></span>');
 if(t.cede_ao_coracao) h.push('<span class="tag"><span>cede ao coração</span></span>');
 if(t.perde_o_que_ocupa) h.push('<span class="tag' + inc + '"><span>perde</span> ' + prEsc(t.perde_o_que_ocupa.join(', ')) + q + '</span>');
 if(t.descontada_de) h.push('<span class="tag' + inc + '"><span>descontada de</span> ' + prEsc(t.descontada_de) + q + '</span>');
 if(t.contida_em) h.push('<span class="tag"><span>contida em</span> ' + prEsc(t.contida_em) + '</span>');
 if(t.recorte) h.push('<span class="tag"><span>recorte</span> ' + prEsc(t.recorte.marcos.join(' | ') + ' · ' + t.recorte.extremo) + '</span>');
 if(t.recortado_em) h.push('<span class="tag"><span>inteiro; o recortado é</span> ' + prEsc(t.recortado_em) + '</span>');
 if(t.margem_mm) h.push('<span class="tag">+' + prMm(t.margem_mm) + ' mm</span>');
 if(t.refino_hu) h.push('<span class="tag">' + Math.round(t.refino_hu) + ' HU</span>');
 if(t.sai_dentro_de) h.push('<span class="tag"><span>sai dentro de</span> ' + prEsc(t.sai_dentro_de.join(', ')) + '</span>');
 if(t.no_lugar_das_partes) h.push('<span class="tag"><span>no lugar das partes</span></span>');
 return h.join(' ') || '—';
}

function prTabela(){
 var f = (PR.filtro || '').toLowerCase();
 var linhas = (PR.d.estruturas || []).filter(function(e){
  return !f || e.estrutura.toLowerCase().indexOf(f) >= 0
         || String(e.nome_tps || '').toLowerCase().indexOf(f) >= 0;
 });
 var h = '<table class="pr-tab"><tr><th>estrutura</th><th class="tps">no TPS</th>'
   + '<th>de onde vem</th><th>suavização</th><th>no entregue</th></tr>';
 linhas.forEach(function(e){
  h += '<tr><td class="est">' + prEsc(e.estrutura) + '</td>'
    + '<td class="est tps">' + prEsc(e.nome_tps) + '</td>'
    + '<td>' + prOrigemCelula(e.origem || {}) + '</td>'
    + '<td>' + prSuavCelula(e.suavizacao || {}) + '</td>'
    + '<td>' + prEntregueCelula(e.entregue || {}) + '</td></tr>';
 });
 h += '</table>';
 prPor(prEl('pr_tab'), h);
 var n = prEl('pr_n'); if(n) n.textContent = linhas.length;
}

window.addEventListener('DOMContentLoaded', function(){
 prCarregar();
 var f = prEl('pr_filtro');
 if(f) f.oninput = function(){ PR.filtro = f.value; if(PR.d) prTabela() };
});
"""


def pagina():
    return PAGINA.replace("@CSS@", CSS).replace("@JS@", JS)


PAGINA = u"""<!doctype html><html><head><meta charset="utf-8">
<title>Procedência · Radioterapia.AI Local</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>@CSS@</style></head><body><div class="pr-wrap">

<div class="rc-capa">
 <div class="rc-eyebrow" data-radai-frase>PROCEDÊNCIA DAS ESTRUTURAS</div>
 <h1 class="rc-titulo" data-radai-frase>O que o programa faz com cada estrutura</h1>
 <p class="sub" style="line-height:1.65;max-width:76ch" data-radai-frase>Espelho
  do código, só leitura. Tudo o que aparece aqui sai das tabelas do motor no
  momento em que a tela abre, com a suavização que esta estação está usando.
  Nada aqui é configurável: o pacote é um só, com todos os modelos e pesos, e o
  que roda em cada série se decide no «Rodar agora» e, na fila da noite, pela
  anatomia.</p>
</div>

<div id="pr_avisos"></div>

<section class="pr-bloco">
 <h2>Suavização</h2>
 <p><code>SUAVIZAR_MM</code> <span>O cursor mora no arquivo de configuração,
  com o comentário que explica. Ele multiplica a tabela inteira e muda a
  entrega de todas as estruturas; por isso não se ajusta por uma tela.</span></p>
 <div id="pr_suav"></div>
</section>

<section class="pr-bloco">
 <h2>De onde vem cada estrutura</h2>
 <div id="pr_origem"></div>
</section>

<section class="pr-bloco" id="pr_bibliotecas">
 <h2 data-radai-frase>Bibliotecas do TotalSegmentator</h2>
 <div id="pr_bib"></div>
</section>

<section class="pr-bloco">
 <h2>O que cada conjunto recebe a mais</h2>
 <div id="pr_regras"></div>
</section>

<section class="pr-bloco">
 <h2>Estrutura por estrutura</h2>
 <div class="pr-barra">
  <input type="text" id="pr_filtro" placeholder="filtrar estrutura"
         aria-label="filtrar estrutura">
  <span class="pr-conta"><span class="p"><b id="pr_n">&#8212;</b></span></span>
 </div>
 <div class="pr-rolar"><div id="pr_tab"></div></div>
</section>
<div id="pr_msg"></div>

</div>
<script>@JS@</script>
</body></html>"""


def cursores(config=None):
    import radai_provenance as P
    cfg = dict(config or {})
    avisos = []
    em_uso, origem = None, None
    v = cfg.get("em_uso")
    if callable(v):
        try:
            v = v()
        except Exception as ex:
            v = None
            avisos.append(P.aviso("cursor_processo", P._erro(ex)))
    if isinstance(v, dict) and v.get("SUAVIZAR_MM") is not None:
        em_uso, origem = v.get("SUAVIZAR_MM"), "processo"
    arquivo = None
    try:
        import radai_config
        _t, disco = radai_config.ler_arquivo(
            cfg.get("caminho") or radai_config.caminho_padrao())
        arquivo = disco.get("SUAVIZAR_MM")
    except Exception as ex:
        arquivo = None
        avisos.append(P.aviso("arquivo", P._erro(ex)))
    fabrica = (cfg.get("padroes") or {}).get("SUAVIZAR_MM")
    if em_uso is None:
        if arquivo is not None:
            em_uso, origem = arquivo, "arquivo"
        elif fabrica is not None:
            em_uso, origem = fabrica, "fabrica"
    return {"em_uso": em_uso, "origem": origem, "arquivo": arquivo,
            "fabrica": fabrica, "avisos": avisos}


def bibliotecas(config=None):
    import radai_provenance as P
    cfg = dict(config or {})
    fora = {"tasks": [], "no_disco": 0, "versao_ts": u"",
            "recorte_no_corpo": None, "avisos": []}
    try:
        import radai_tasks
        for t in radai_tasks.estado():
            fora["tasks"].append(dict(
                (k, t.get(k)) for k in ("task", "rotulo", "classes",
                                        "modalidade", "mb", "baixado", "rt",
                                        "achado", "permitida", "porque_nao")))
        fora["no_disco"] = sum(1 for t in fora["tasks"] if t.get("baixado"))
    except Exception as ex:
        fora["avisos"].append(P.aviso("bibliotecas", P._erro(ex)))
    try:
        from importlib.metadata import version
        fora["versao_ts"] = version("TotalSegmentator")
    except Exception:
        fora["versao_ts"] = u"não instalado neste Python"
    valores = {}
    v = cfg.get("em_uso")
    if callable(v):
        try:
            v = v()
        except Exception:
            v = None
    if isinstance(v, dict):
        valores.update(v)
    if "RECORTE_NO_CORPO" not in valores:
        try:
            import radai_config
            _t, disco = radai_config.ler_arquivo(
                cfg.get("caminho") or radai_config.caminho_padrao())
            valores.setdefault("RECORTE_NO_CORPO", disco.get("RECORTE_NO_CORPO"))
        except Exception:
            pass
    r = valores.get("RECORTE_NO_CORPO")
    if isinstance(r, bool):
        r = 1 if r else 0
    fora["recorte_no_corpo"] = r
    return fora


def montar(app, config=None):
    from fastapi.responses import HTMLResponse
    cfg = dict(config or {})

    @app.get("/procedencia", response_class=HTMLResponse)
    def _tela():
        return radai_menu.aplicar(pagina(), "procedencia", com_tarefas=False)

    @app.get("/api/procedencia")
    def _espelho():
        try:
            import radai_provenance
            c = cursores(cfg)
            d = radai_provenance.espelho(
                c["em_uso"], fabrica=c["fabrica"], no_arquivo=c["arquivo"],
                origem_do_cursor=c["origem"], avisos=c["avisos"])
            b = bibliotecas(cfg)
            d["bibliotecas"] = b
            d.setdefault("avisos", []).extend(b.pop("avisos", []))
            return d
        except Exception as e:
            return {"erro": u"%s: %s" % (type(e).__name__, str(e)[:200])}

    return app
