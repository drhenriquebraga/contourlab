# -*- coding: utf-8 -*-
import os

VERSAO_REVISAO = "1.0"


def _num(v, padrao=0):
    try:
        return int(v)
    except Exception:
        return padrao


_NINGUEM_PEDIU = (u"nenhuma série da fila pede: o motor roda só no modo "
                  u"PERSONALIZADO, com a chave dele ligada em Comparação de "
                  u"modelos")
_NINGUEM_PEDIU_TS = (u"nenhuma série da fila pede: o TS cru só sai no modo "
                     u"PERSONALIZADO, com a chave «TS cru (não corrigido)»")
_SO_FAST = (u"só séries FAST na fila: o FAST grava só o RadAI_STUDY_Fast")

_NINGUEM_PEDIU_HNL = (u"nenhuma série da fila pede: o arquivo próprio dos "
                      u"níveis só sai no PERSONALIZADO, pelo protocolo "
                      u"Cabeça e Pescoço avançado ou pela chave própria; no "
                      u"AUTO, com o pescoço no campo, eles entram no FULL")
_HNL_NO_FULL = (u"no vigia (AUTO) os níveis entram no FULL quando o pescoço "
                u"está no campo; o arquivo próprio deles só sai no "
                u"PERSONALIZADO do «Rodar agora»")
_PORTAO_HNL = (u"pedido; só sai em série com a cabeça no campo — o portão "
               u"mede o encéfalo depois da biblioteca principal, e numa TC "
               u"de tórax ele não sai, o que não é erro")


def _nome_na_tela(c):
    # GUARDA: o nome longo dos níveis é texto dos Termos; com chave, o
    # dicionário entraria no documento. O rótulo curto tem chave própria.
    if c.get("cod") == "hnl" and c.get("rotulo_curto"):
        return c["rotulo_curto"]
    return c["nome"]


def _conjuntos_previstos(incluir_nv=True, incluir_cads=False,
                         incluir_hnlnl=False, elegivel_tx=False,
                         incluir_moose=False, origem="lote", por_serie=False,
                         tasks=(), incluir_ts=None, modos=None):
    import radai_sets
    fora = []
    _modos = dict(modos or {})
    _n_fast = int(_modos.get("fast") or 0)
    _n_cheio = sum(int(_modos.get(k) or 0) for k in ("auto", "perso", ""))
    for c in radai_sets.CONJUNTOS:
        cod = str(c["cod"])
        sai, porque = True, u""
        if modos is not None and cod in ("oar", "full") and _n_fast \
                and not _n_cheio:
            fora.append({"cod": cod, "nome": _nome_na_tela(c),
                         "infixo": c["infixo"], "sai": False,
                         "porque": _SO_FAST, "entregue": cod == "oar"})
            continue
        if por_serie and cod == "ts" and incluir_ts is not None:
            sai = bool(incluir_ts)
            fora.append({"cod": cod, "nome": _nome_na_tela(c),
                         "infixo": c["infixo"], "sai": sai,
                         "porque": u"" if sai else _NINGUEM_PEDIU_TS,
                         "entregue": False})
            continue
        if origem == "vigia" and cod == "hnl":
            fora.append({"cod": cod, "nome": _nome_na_tela(c), "infixo": c["infixo"],
                         "sai": False, "porque": _HNL_NO_FULL,
                         "entregue": False})
            continue
        if por_serie and cod in ("nv", "cads", "mse", "hnl"):
            ligado = {"nv": incluir_nv, "cads": incluir_cads,
                      "mse": incluir_moose, "hnl": incluir_hnlnl}[cod]
            if not ligado:
                sai, porque = False, (_NINGUEM_PEDIU_HNL if cod == "hnl"
                                      else _NINGUEM_PEDIU)
            elif cod == "hnl":
                porque = _PORTAO_HNL
            fora.append({"cod": cod, "nome": _nome_na_tela(c), "infixo": c["infixo"],
                         "sai": sai, "porque": porque, "entregue": False})
            continue
        if cod == "nv" and not incluir_nv:
            sai, porque = False, (u"desligado na estação: INCLUIR_NV=0 "
                                  u"no radai_watcher.config")
        elif cod == "cads" and not incluir_cads:
            sai, porque = False, (u"desligado na estação: INCLUIR_CADS=0 no "
                                  u"radai_watcher.config (ele é lento sem GPU)")
        elif cod == "mse" and not incluir_moose:
            sai, porque = False, (u"desligado na estação: INCLUIR_MOOSE=0 no "
                                  u"radai_watcher.config")
        elif cod == "hnl" and not incluir_hnlnl:
            sai, porque = False, (u"desligado na estação: INCLUIR_HNLNL=0 no "
                                  u"radai_watcher.config")
        elif cod == "hnl":
            porque = (u"ligado; o portão mede depois da task total e só "
                      u"deixa passar se o encéfalo aparecer — numa TC de "
                      u"tórax ele não sai, e isso não é erro")
        fora.append({"cod": cod, "nome": _nome_na_tela(c), "infixo": c["infixo"],
                     "sai": sai, "porque": porque,
                     "entregue": cod == "oar"})
    if _n_fast:
        for c in getattr(radai_sets, "SAIDAS_DE_MODO", ()) or ():
            if c.get("cod") == "fast":
                fora.insert(0, {"cod": "fast", "nome": _nome_na_tela(c),
                                "infixo": c["infixo"], "sai": True,
                                "porque": u"", "entregue": True})
    _plugins = getattr(radai_sets, "PLUGIN_DA_TASK", {}) or {}
    _vistos = set()
    for t in (tasks or ()):
        p = _plugins.get(t)
        if not p or p["cod"] in _vistos:
            continue
        _vistos.add(p["cod"])
        fora.append({"cod": p["cod"], "nome": p["nome"],
                     "infixo": p["infixo"], "sai": True,
                     "porque": p.get("rotulo") or u"",
                     "entregue": False, "plugin": True,
                     "achado": bool(p.get("achado"))})
    if any(str(k).startswith(u"perso3d:") for k in _modos):
        fora.append({"cod": "rotulos", "nome": ROTULO_DO_MAPA_3D,
                     "infixo": u"_RadAI/", "sai": True,
                     "porque": u"Reconstruções 3D, sem RTSTRUCT",
                     "entregue": False, "plugin": False, "achado": False})
    return fora


def _estacao(device="", n_series=1, n_tasks=1):
    fora = {"memoria": {}, "disco": [], "ganhos": [], "erro": ""}
    try:
        import radai_cleaner as LP
        fora["memoria"] = LP.memoria_da_estacao()
        fora["disco"] = LP.espaco_em_disco(n_series=n_series, n_tasks=n_tasks)
        fora["ganhos"] = LP.ganhos_de_velocidade(device=device)
    except Exception as e:
        fora["erro"] = u"%s: %s" % (type(e).__name__, e)
    return fora


try:
    from radai_arranque import MIN_POR_MVOXEL_CPU
except Exception as _e:
    MIN_POR_MVOXEL_CPU = None
    _REGUA_FALTOU = u"%s: %s" % (type(_e).__name__, _e)
else:
    _REGUA_FALTOU = u""
FATOR_GPU = 0.06


def estimativa(n_series, n_tasks=1, device="", mvoxels=35.0):
    n_series = max(0, _num(n_series))
    try:
        n_tasks = max(1.0, float(n_tasks))
    except Exception:
        n_tasks = 1.0
    if MIN_POR_MVOXEL_CPU is None:
        _avisar_uma_vez("regua", u"[revisao] sem a regua de CPU do "
                        u"radai_arranque (%s): a estimativa sai em branco"
                        % _REGUA_FALTOU)
        return None, u"sem estimativa (a régua de CPU não carregou)"
    por_serie = MIN_POR_MVOXEL_CPU * float(mvoxels) * n_tasks
    if str(device or "").lower().startswith("cuda") or \
            str(device or "").lower() == "gpu":
        por_serie *= FATOR_GPU
    total = por_serie * n_series
    if total < 1:
        return 0, u"menos de um minuto"
    if total < 90:
        txt = u"~%d min" % int(round(total))
    else:
        txt = u"~%dh%02d" % (int(total // 60), int(total % 60))
    return int(round(total)), txt


_AVISADOS = set()


def _avisar_uma_vez(chave, texto):
    if chave in _AVISADOS:
        return
    _AVISADOS.add(chave)
    try:
        print(texto)
    except Exception:
        pass


def _estudos_da_fila(estudos):
    if not estudos:
        return []
    try:
        import radai_modes as _md
    except Exception as e:
        _avisar_uma_vez("estudos", u"[revisao] a linha dos estudos saiu da "
                        u"conferencia: radai_modes nao importou (%s: %s)"
                        % (type(e).__name__, e))
        return []
    _modos = {u"fast": u"FAST", u"auto": u"AUTO", u"perso": u"PERSONALIZADO"}
    fora = []
    ordem = [u"fast", u"auto", u"perso"] + [
        u"perso:%s" % p["cod"] for p in getattr(_md, "PROTOCOLOS", ())] + [
        u"perso3d:%s" % p["cod"] for p in getattr(_md, "PROTOCOLOS_3D", ())] + [
        u"-", u""]
    ordem += sorted(c for c in (estudos or {}) if c not in ordem)
    for cod in ordem:
        n = int((estudos or {}).get(cod) or 0)
        if not n:
            continue
        if cod == u"":
            rot = u"lista do chamador"
        elif cod == u"-":
            rot = u"só a base e as chaves ligadas"
        elif cod in _modos:
            rot = _modos[cod]
        elif cod.startswith(u"perso:"):
            rot = ((getattr(_md, "PROT_POR_COD", {}).get(cod[6:]) or {})
                   .get("rotulo") or cod[6:])
        elif cod.startswith(u"perso3d:"):
            rot = ((getattr(_md, "PROT_3D_POR_COD", {}).get(cod[8:]) or {})
                   .get("rotulo") or cod[8:])
        else:
            rot = cod
        fora.append({"cod": cod, "n": n, "rotulo": rot})
    return fora


def achados_declarados(series):
    fora = []
    try:
        import radai_sets as _rs
    except Exception:
        return fora
    for s in (series or ()):
        s = s or {}
        if s.get("achado_declarado") is not True or not s.get(
                "protocolo_proprio"):
            continue
        try:
            p = _rs.protocolo_proprio(s.get("protocolo_proprio"),
                                      s.get("modalidade") or "CT")
            achados = list(_rs.selecao_do_protocolo(p)["achados"]) if p \
                else []
        except Exception:
            achados = []
        if achados:
            fora.append({"uid8": str(s.get("uid") or "")[-8:],
                         "protocolo": u"%s" % (p.get("nome") or p.get("id")),
                         "tasks": achados})
    return fora


def montar(series, destino="", tasks=(), device="", suavizar_mm=1.5,
           incluir_nv=True, incluir_cads=False, incluir_hnlnl=False,
           incluir_moose=False,
           elegivel_tx=False, origem="lote", ocupado=None, estudos=None,
           problemas=None, incluir_ts=None):
    series = list(series or [])
    n = len(series)
    problemas = [dict(p) for p in (problemas or ()) if p]
    try:
        import radai_tasks as _rt
        _recuo = tuple(_rt.PADRAO)
    except Exception:
        _recuo = ()
    tasks = tuple(tasks) if tasks else (() if problemas else _recuo)
    mins, txt = estimativa(n, len(tasks), device)
    pacientes = []
    for s in series[:8]:
        pacientes.append({
            "pid": str(s.get("pid") or ""),
            "uid8": str(s.get("uid") or "")[-8:],
            "cortes": _num(s.get("cortes")),
            "espessura_mm": s.get("espessura_mm"),
        })
    return {
        "versao": VERSAO_REVISAO,
        "origem": origem,
        "n_series": n,
        "series": pacientes,
        "mais": max(0, n - len(pacientes)),
        "tasks": list(tasks),
        "destino": str(destino or ""),
        "device": str(device or ""),
        "suavizar_mm": suavizar_mm,
        "conjuntos": _conjuntos_previstos(incluir_nv, incluir_cads,
                                          incluir_hnlnl, elegivel_tx,
                                          incluir_moose, origem,
                                          por_serie=estudos is not None,
                                          tasks=tasks, incluir_ts=incluir_ts,
                                          modos=estudos),
        "estudos": _estudos_da_fila(estudos),
        "achados_declarados": achados_declarados(series),
        "problemas": [{"uid8": str(p.get("uid8") or "")[-8:],
                       "o_que": ("motores" if p.get("o_que") == "motores"
                                 else "tasks"),
                       "erro": str(p.get("erro") or "")[:200]}
                      for p in problemas],
        "estimativa_min": mins,
        "estimativa": txt,
        "estacao": _estacao(device, n_series=n,
                            n_tasks=len(tasks)),
        "ocupado": ocupado or None,
        "aviso": FRASE_DA_FRONTEIRA,
        "onde": (u"Os arquivos são gravados AO LADO dos DICOM de cada série, "
                 u"na própria pasta do exame."),
    }


FRASE_DA_FRONTEIRA = (
    u"Tudo o que é gravado se mantém com sugestão não aprovada "
    u"(ApprovalStatus = UNAPPROVED). Revisar é ato médico — utilize as "
    u"ferramentas de Ver Segmentação e Reconstrução 3D para estudo. Não é um "
    u"dispositivo médico.")
ROTULO_DO_INICIAR = u"Começar a segmentar a fila agora"
ROTULO_DO_MAPA_3D = u"mapa de rótulos das Reconstruções 3D"
SEM_CONFERENCIA = (u"A conferência não pôde ser montada agora; a fila "
                   u"começa com o que está nela.")


def tag_da_fronteira(ident=u""):
    return (u'<p class="rc-fronteira"%s role="note"><span class="pt" '
            u'aria-hidden="true"></span><span data-radai-frase>%s</span></p>'
            % ((u' id="%s"' % ident) if ident else u"", FRASE_DA_FRONTEIRA))


CSS_DA_FRONTEIRA = u"""
.rc-fronteira{display:flex;align-items:flex-start;gap:9px;margin:14px 0 0;
 padding:10px 12px;border:1px solid var(--borda-aviso,#4a3a18);
 border-radius:var(--r-lg,8px);background:var(--fundo-aviso,#1c1608);
 color:var(--text,#e6edf7);font-size:12.5px;line-height:1.5;text-align:start}
.rc-fronteira .pt{width:7px;height:7px;border-radius:50%;flex:0 0 auto;
 margin-top:6px;background:var(--warn,#E1B23B)}
"""

CSS = u"""
<style id="radai-rev-css">
#radai_rev_fundo{position:fixed;inset:0;background:rgba(2,6,14,.72);
 z-index:9998;display:none}
#radai_rev{position:fixed;z-index:9999;left:50%;top:50%;
 transform:translate(-50%,-50%);width:min(760px,94vw);max-height:88vh;
 overflow:auto;display:none;background:var(--panel,#0b111a);
 border:1px solid var(--line-strong,#2a3a55);border-radius:12px;
 padding:20px 22px;box-shadow:0 24px 70px rgba(0,0,0,.6)}
#radai_rev h3{margin:0 0 4px;font-size:17px;color:var(--text,#e6edf7)}
#radai_rev .rev-sub{color:var(--text-muted,#8fa3bd);font-size:12.5px;
 margin:0 0 14px}
#radai_rev .rev-bl{border:1px solid var(--line,#1e293b);border-radius:9px;
 padding:11px 13px;margin:0 0 10px}
#radai_rev .rev-bl h4{margin:0 0 7px;font-size:11px;letter-spacing:.1em;
 text-transform:uppercase;color:var(--text-dim,#72829b);
 font-family:var(--mono,monospace)}
#radai_rev table{width:100%;border-collapse:collapse;font-size:12.5px}
#radai_rev td{padding:3px 0;vertical-align:top}
#radai_rev td.n{text-align:right;font-family:var(--mono,monospace);
 white-space:nowrap;color:var(--text-muted,#8fa3bd)}
#radai_rev .cj{display:flex;gap:7px;align-items:baseline;padding:2px 0}
#radai_rev .cj b{font-family:var(--mono,monospace);font-size:11px;
 min-width:52px;color:var(--text-dim,#72829b)}
#radai_rev .cj .nao{color:var(--text-dim,#72829b);text-decoration:line-through}
#radai_rev .pq{color:var(--text-dim,#72829b);font-size:11.5px}
#radai_rev .cj .ent{color:var(--accent,#4DA3FF);font-weight:600}
#radai_rev .rev-alerta{border-color:var(--aviso,#E1B23B);
 background:rgba(225,178,59,.08)}
#radai_rev .rev-clin{border-color:var(--accent,#4DA3FF);
 background:rgba(77,163,255,.08);font-size:12.5px;
 color:var(--text,#e6edf7)}
#radai_rev .rev-bt{display:flex;gap:9px;margin-top:16px;flex-wrap:wrap}
#radai_rev .rev-bt button{font:inherit;font-size:13px;padding:9px 18px;
 border-radius:7px;cursor:pointer;border:1px solid var(--line-strong,#2a3a55);
 background:var(--panel-2,#0f1729);color:var(--text,#e6edf7)}
#radai_rev .rev-bt button.pri{background:var(--ok,#12873F);
 border-color:var(--ok,#12873F);color:var(--ok-txt,#fff);font-weight:600}
#radai_rev .rev-bt button:focus-visible{outline:2px solid var(--accent,#4DA3FF);
 outline-offset:2px}
#radai_rev .rev-bt button:disabled{opacity:.45;cursor:not-allowed}
""" + CSS_DA_FRONTEIRA + u"""
</style>"""

HTML = u"""
<div id="radai_rev_fundo" onclick="radaiRevFechar()"></div>
<div id="radai_rev" role="dialog" aria-modal="true"
 aria-labelledby="radai_rev_tit">
 <h3 id="radai_rev_tit">Confira antes de come&ccedil;ar</h3>
 <p class="rev-sub" id="radai_rev_sub"></p>
 <div id="radai_rev_corpo"></div>
 @FRONTEIRA@
 <div class="rev-bt">
  <button class="pri" id="radai_rev_ok" data-radai-frase>Começar a segmentar a fila agora</button>
  <button onclick="radaiRevFechar()">Cancelar</button>
 </div>
</div>
<script>
var RADAI_REV_ACAO = null;
var RADAI_REV_VOLTA = null;
var RADAI_REV_SEM_CONFERENCIA = @SEM_CONFERENCIA@;

function radaiRevEsc(s){return String(s==null?'':s).replace(/&/g,'&amp;')
 .replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;')}

function radaiRevFechar(){
 var bt0 = document.getElementById('radai_rev_ok');
 if(bt0){
  if(typeof uiTexto === 'function') uiTexto(bt0, 'Começar a segmentar a fila agora');
  else bt0.textContent = 'Começar a segmentar a fila agora';
  bt0.disabled = false;
 }
 var d=document.getElementById('radai_rev');
 var f=document.getElementById('radai_rev_fundo');
 var aberto = d && d.style.display === 'block';
 if(d) d.style.display='none';
 if(f) f.style.display='none';
 RADAI_REV_ACAO = null;
 var volta = RADAI_REV_VOLTA; RADAI_REV_VOLTA = null;
 if(aberto && volta && volta.focus && document.contains(volta)){
  try{ volta.focus() }catch(e){}
 }
}

function radaiRevBloco(titulo, corpo, classe){
 return '<div class="rev-bl '+(classe||'')+'"><h4>'+radaiRevEsc(titulo)
  +'</h4>'+corpo+'</div>';
}

function radaiRevAbrir(d, aoIniciar){
 var corpo = document.getElementById('radai_rev_corpo');
 if(!corpo){ if(aoIniciar) aoIniciar(); return; }
 RADAI_REV_ACAO = aoIniciar;
 var _dlg = document.getElementById('radai_rev');
 if(!(_dlg && _dlg.style.display === 'block')) RADAI_REV_VOLTA = document.activeElement;
 // GUARDA: sem a conferencia (rota fora do ar), o dialogo abre so com a tag da regra 1 e o botao; nao vira portao.
 if(!d){
  var sub0 = document.getElementById('radai_rev_sub');
  if(typeof uiTexto === 'function') uiTexto(sub0, RADAI_REV_SEM_CONFERENCIA);
  else sub0.textContent = RADAI_REV_SEM_CONFERENCIA;
  corpo.innerHTML = '';
  var bt1 = document.getElementById('radai_rev_ok');
  if(typeof uiTexto === 'function') uiTexto(bt1, 'Começar a segmentar a fila agora');
  else bt1.textContent = 'Começar a segmentar a fila agora';
  bt1.disabled = false;
  try{ if(window.radaiRetraduzir) window.radaiRetraduzir() }catch(e){}
  document.getElementById('radai_rev_fundo').style.display='block';
  document.getElementById('radai_rev').style.display='block';
  bt1.focus();
  return;
 }

 var sub = (d.origem === 'vigia')
  ? 'O vigia vai começar a varrer a pasta e contornar sozinho o que achar.'
  : '%d série(s) selecionada(s). Nada começou ainda.'.replace('%d', d.n_series);
 var subEl = document.getElementById('radai_rev_sub');
 if(typeof uiTexto === 'function') uiTexto(subEl, sub); else subEl.textContent = sub;

 var h = '';

 var linhas = (d.series||[]).map(function(s){
  return '<tr><td>' + (s.pid ? radaiRevEsc(s.pid)
                      : '<span data-radai-frase>(sem ID)</span>')
   + ' <span class="pq">...' + radaiRevEsc(s.uid8) + '</span></td>'
   + '<td class="n">' + radaiRevEsc(s.cortes) + ' <span data-radai-frase>cortes</span>'
   + (s.espessura_mm ? (' &middot; ' + radaiRevEsc(s.espessura_mm) + ' mm') : '')
   + '</td></tr>';
 }).join('');
 if(d.mais) linhas += '<tr><td colspan="2" class="pq">'
  + 'e mais %s série(s)'.replace('%s', radaiRevEsc(d.mais)) + '</td></tr>';
 if(linhas) h += radaiRevBloco('o que vai ser processado',
  '<table>'+linhas+'</table>');

 var ests = (d.estudos||[]).map(function(m){
  return '<span style="margin-left:8px"><b>' + radaiRevEsc(m.n) + '</b> '
   + '<span data-radai-frase>' + radaiRevEsc(m.rotulo) + '</span></span>';
 }).join('');
 h += radaiRevBloco('como vai rodar',
  '<table>'
  + (ests ? ('<tr><td>Estudos pedidos</td><td class="n">'
              + ests + '</td></tr>') : '')
  + '<tr><td>Modelos (tasks)</td><td class="n" data-radai-t="1" translate="no">'
  +   radaiRevEsc((d.tasks||[]).join(', ')) + '</td></tr>'
  + '<tr><td>Processamento</td><td class="n">'
  +   radaiRevEsc(d.device || 'auto') + '</td></tr>'
  + '<tr><td>Suavização</td><td class="n">'
  +   '%s mm (escala da tabela por estrutura)'.replace('%s', radaiRevEsc(d.suavizar_mm))
  +   '</td></tr>'
  + '<tr><td>Tempo provável</td><td class="n">'
  +   radaiRevEsc(d.estimativa) + '</td></tr>'
  + '</table>'
  + '<p class="pq" style="margin:7px 0 0">'
  + 'A estimativa sai de dois pontos de medição. Numa máquina ocupada ela erra por um fator — serve para planejar a tarde, não para prometer hora.'
  + '</p>');

 var prob = (d.problemas||[]).map(function(p){
  return '<div class="rev-falha" style="padding:2px 0">! <span data-radai-frase>'
   + (p.o_que === 'motores'
      ? 'os motores de comparação desta série não foram calculados'
      : 'as tasks desta série não foram calculadas')
   + '</span> <span class="pq">...' + radaiRevEsc(p.uid8) + ' &middot; '
   + radaiRevEsc(p.erro) + '</span></div>';
 }).join('');
 if(prob) h += radaiRevBloco('o que ficou fora da conta', prob
  + '<p class="pq" style="margin:7px 0 0" data-radai-frase>'
  + 'O que falhou aqui não está na lista acima.</p>', 'rev-alerta');

 var achs = (d.achados_declarados||[]).map(function(a){
  return '<tr><td>' + radaiRevEsc(a.protocolo) + ' <span class="pq">...'
   + radaiRevEsc(a.uid8) + '</span></td><td class="n" data-radai-t="1" translate="no">'
   + radaiRevEsc((a.tasks||[]).join(', ')) + '</td></tr>';
 }).join('');
 if(achs) h += radaiRevBloco('detecção (ACHADO) declarada', '<table>' + achs + '</table>'
  + '<p class="pq" style="margin:7px 0 0" data-radai-frase>'
  + 'Declarada no envio à fila, pelo protocolo próprio da série. O resultado sai no arquivo próprio do achado, nunca no STUDY.</p>', 'rev-alerta');

 var cjs = (d.conjuntos||[]).map(function(c){
  return '<div class="cj"><b>' + radaiRevEsc(c.infixo || '\u2014') + '</b>'
   + '<span class="' + (c.sai ? (c.entregue ? 'ent' : '') : 'nao') + '">'
   + radaiRevEsc(c.nome) + '</span>'
   + (c.porque ? ('<span class="pq">' + radaiRevEsc(c.porque) + '</span>') : '')
   + (c.entregue ? '<span class="pq">&mdash; <span data-radai-frase>'
      + 'pós-processamento voltado para radioterapia; é o que vai para o plano'
      + '</span></span>' : '')
   + '</div>';
 }).join('');
 h += radaiRevBloco('arquivos que vão ser gravados', cjs
  + '<p class="pq" style="margin:7px 0 0">' + radaiRevEsc(d.onde) + '</p>');

 var est = d.estacao || {}, m = est.memoria || {}, avisos = [];
 if(m.total_mb && m.livre_mb < 4000) avisos.push(
  'Memória livre baixa: %s MB. Segmentar uma TC de planejamento usa vários GB.'
  .replace('%s', m.livre_mb));
 (est.disco||[]).forEach(function(u){
  if(u.aperta) avisos.push(
   'Pouco espaço em %s: %s GB livres. A cópia de trabalho e o temporário do modelo precisam de disco.'
   .replace('%s', u.unidade).replace('%s', u.livre_gb));
 });
 (est.ganhos||[]).forEach(function(g){
  if(g.chave === 'gpu' && g.onde) avisos.push(g.detalhe + ' ' + g.onde + '.');
  if(g.chave === 'energia') avisos.push(g.rotulo + '. ' + g.detalhe);
 });
 if(avisos.length) h += radaiRevBloco('vale olhar antes',
  avisos.map(function(a){return '<div style="padding:2px 0">! <span data-radai-frase>'
   + radaiRevEsc(a) + '</span></div>'}).join(''), 'rev-alerta');


 var oc = d.ocupado;
 if(oc && oc.quem && oc.quem !== 'lote'){
  h += '<div class="rev-bl rev-alerta"><h4>a máquina já está segmentando</h4>'
   + '<div><span data-radai-frase>O vigia está processando:</span> <b>'
   + radaiRevEsc(oc.o_que) + '</b>'
   + (oc.etapa ? (' (' + radaiRevEsc(oc.etapa) + ')') : '') + '</div>'
   + '<p style="margin:6px 0 0">'
   + 'Duas segmentações na mesma máquina estouram a memória. Pause o vigia e espere a série atual terminar, ou use Configurações → Encerrar o programa → Fechar tudo para interromper agora.'
   + '</p></div>';
 }

 var bt = document.getElementById('radai_rev_ok');
 if(oc && oc.quem && oc.quem !== 'lote'){
  if(typeof uiTexto === 'function') uiTexto(bt, 'Não dá para começar agora');
  else bt.textContent = 'Não dá para começar agora';
  bt.disabled = true;
 } else {
  if(typeof uiTexto === 'function') uiTexto(bt, 'Começar a segmentar a fila agora');
  else bt.textContent = 'Começar a segmentar a fila agora';
  bt.disabled = false;
 }

 corpo.innerHTML = h;
 try{ if(window.radaiRetraduzir) window.radaiRetraduzir() }catch(e){}
 document.getElementById('radai_rev_fundo').style.display='block';
 document.getElementById('radai_rev').style.display='block';
 document.getElementById('radai_rev_ok').focus();
}

document.addEventListener('click', function(ev){
 if(ev.target && ev.target.id === 'radai_rev_ok'){
  var f = RADAI_REV_ACAO;
  radaiRevFechar();
  if(f) f();
 }
});
document.addEventListener('keydown', function(ev){
 var d = document.getElementById('radai_rev');
 if(!d || d.style.display !== 'block') return;
 if(ev.key === 'Escape'){ radaiRevFechar(); return }
 // GUARDA: aria-modal promete que o Tab nao sai do dialogo.
 if(ev.key === 'Tab'){
  if(typeof window.uiPrenderFoco === 'function'){ window.uiPrenderFoco(d, ev); return }
  var fs = Array.prototype.filter.call(d.querySelectorAll('button,[href],input,select,textarea,[tabindex]'),
   function(x){ return !x.disabled && x.getAttribute('tabindex') !== '-1' && x.offsetParent !== null });
  if(!fs.length){ ev.preventDefault(); return }
  var i = fs.indexOf(document.activeElement);
  if(ev.shiftKey){ if(i <= 0){ ev.preventDefault(); fs[fs.length-1].focus() } }
  else if(i < 0 || i === fs.length-1){ ev.preventDefault(); fs[0].focus() }
 }
});
</script>"""


def aplicar(pagina):
    if not pagina or u"radai-rev-css" in pagina:
        return pagina
    baixa = pagina.lower()
    fim_head = baixa.find(u"</head>")
    fim_corpo = baixa.rfind(u"</body>")
    if fim_head < 0 or fim_corpo < 0:
        return pagina
    saida = pagina[:fim_head] + CSS + pagina[fim_head:]
    corte = fim_corpo + len(CSS)
    import json
    html = (HTML.replace(u"@FRONTEIRA@", tag_da_fronteira(u"radai_rev_fronteira"))
            .replace(u"@SEM_CONFERENCIA@", json.dumps(SEM_CONFERENCIA, ensure_ascii=False)))
    return saida[:corte] + html + saida[corte:]
