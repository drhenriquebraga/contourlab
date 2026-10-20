# -*- coding: utf-8 -*-
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import traceback
from collections import deque

try:
    import radai_archive as _arq
    _TMP_LOCAL = _arq.pasta_temporaria_local()
except Exception:
    _TMP_LOCAL = tempfile.gettempdir()
from datetime import datetime
from pathlib import Path
try:
    import radai_falhas as _falhas
except ImportError:
    # GUARDA: carregado por caminho (as baterias), a pasta do vigia pode nao
    # estar no `sys.path`; o modulo mora ao lado dele.
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import radai_falhas as _falhas

try:
    sys.stdout.reconfigure(errors="replace")
    sys.stderr.reconfigure(errors="replace")
except Exception:
    pass

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import pydicom
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse

_ENGINE = None
_ENGINE_ERRO = ""

try:
    import radai_archive
    import radai_panel
    _PAINEL_ERRO = ""
except Exception as _e:
    radai_archive = None
    radai_panel = None
    _PAINEL_ERRO = "%s: %s" % (type(_e).__name__, _e)

try:
    import radai_validation
except Exception:
    radai_validation = None

_APPVER_RECUO = "2.5"


def _versao_do_entrega():
    for base in (os.path.dirname(os.path.abspath(__file__)),
                 os.path.dirname(os.path.dirname(os.path.abspath(__file__)))):
        try:
            alvo = os.path.join(base, "entrega.txt")
            if not os.path.isfile(alvo):
                continue
            with open(alvo, "r", encoding="utf-8-sig", errors="replace") as f:
                for linha in f:
                    if linha.strip().startswith("VERSAO"):
                        return linha.split("=", 1)[1].strip()
        except Exception:
            continue
    return ""


APPVER = _versao_do_entrega() or _APPVER_RECUO
MACHINE = os.environ.get("RADAI_MACHINE") or socket.gethostname()
import radai_config

CFG_PATH = Path(radai_config.caminho_padrao())

DEFAULT_CFG = u"""# ─── Radioterapia.AI · Vigia de Auto-Contorno ───────────────────────────
# Pasta-raiz no servidor com as pastas dos pacientes.
# VAZIO = o vigia sobe o painel e NAO faz nada (proposital: ninguem varre
# producao por acidente). Preencha quando combinar com o TI.
# Ex.: ROOT=\\\\servidor\\exames
ROOT=

# 1 = SIMULACAO: varre, ordena, reivindica lock e grava marcadores, mas NAO
# chama o TotalSegmentator e NAO grava RTSTRUCT de verdade. Serve para validar
# a coordenacao entre maquinas em segundos, em vez de uma noite de GPU.
DRY_RUN=0

# As tasks NAO se escrevem aqui. O vigia roda sempre o modo AUTO: a base
# (total_v3 na TC, total_mr na RM) e, depois dela, as tasks da regiao que a
# anatomia mostrou (radai_modes.TASKS_POR_TOPOGRAFIA). Task avulsa, achado e
# comparacao de modelos se pedem serie a serie, no PERSONALIZADO do
# «Rodar agora». Uma linha TASKS= de um config antigo e ignorada.

# auto | gpu | cpu
DEVICE=auto

# 1 = o TotalSegmentator recorta o processamento no CORPO antes de segmentar
# (a opcao --body_seg dele). Primeiro roda um modelo grosseiro de corpo, em
# cortes espessos (o Dataset300, body 6 mm, que ja vem no pacote), e a
# segmentacao de verdade so olha o que esta dentro do paciente: o ar em
# volta, a mesa e o campo vazio deixam de ser processados.
#
# Numa TC de planejamento em CPU, a task `total` completa leva cerca de
# metade do tempo com o recorte (40,8 contra 19,1 min). A diferenca no
# contorno fica quase toda na BORDA -- 0,7% dos voxels diferentes a mais de
# 4 mm da borda. Confira a pele e o que encosta nela nas primeiras series.
#
# NUMA RM ELE NAO FAZ NADA: o TotalSegmentator ignora o recorte em task de
# ressonancia (e diz isso no log dele). E ele se desliga sozinho nas tasks
# que ja trazem recorte proprio.
#
# 0 = segmenta o campo inteiro. Vale para o vigia e para o «Rodar agora».
RECORTE_NO_CORPO=1

# Modalidades aceitas (separadas por espaço)
MODALITIES=CT

# Minimo de cortes para valer a pena segmentar
MIN_SLICES=20

# Re-varredura da pasta (minutos)
SCAN_EVERY_MIN=10

# Porta do painel local
PORT=8777

# Idioma da tela: pt-BR, en, es, de, fr, it, pl, ar, bn, ko, zh-CN ou ja.
# VAZIO = automatico: vale o idioma que o pacote trouxe (idioma.txt) ou, sem
# ele, o ingles. O seletor de idioma grava aqui E no navegador; na primeira
# abertura de um navegador novo, vale o que estiver aqui.
IDIOMA=

# Sistema de planejamento que importa os RTSTRUCT desta estacao. Na tela do
# primeiro uso: eclipse = "Eclipse / Monaco" (o furo de um contorno em anel
# sai como um segundo contorno); monaco = "Xio / Focal" (o furo ligado a
# borda por uma linha divisoria). VAZIO = ainda nao escolhido: o primeiro uso
# pergunta, e ate la o RTSTRUCT sai como eclipse. Nos dois, o arquivo usa
# Implicit VR Little Endian e texto so ASCII. Refazer: Configuracoes, Geral,
# primeiro uso.
TPS_DESTINO=

# Lock sem sinal de vida por mais de N horas = maquina caiu, outra assume.
# O dono renova o lock a cada HEARTBEAT_MIN enquanto trabalha, entao uma serie
# demorada NAO e roubada.
LOCK_MAX_H=2
HEARTBEAT_MIN=5

# Lock sem RENOVACAO ha mais que isto (minutos) = a maquina dona esta TRAVADA,
# e nao trabalhando. Outra maquina assume a serie -- e, se o dono travado for
# desta mesma maquina, ela ainda encerra o processo antes.
#
# TRES ESTADOS: o dono trabalhando numa serie longa (normal: uma TC de torax
# em CPU passa de 2 h), o dono travado e o dono morto. Esta chave separa o
# travado do que trabalha.
#
# O padrao e 3x o HEARTBEAT_MIN: quem renova a cada 5 min e considerado parado
# depois de 15. Margem para uma renovacao perdida por lentidao de rede, sem
# deixar a serie presa.
#
# Um valor alto (60, por exemplo) nao compensa: o batimento e uma thread
# trivial que so escreve um JSON, e quinze minutos de silencio sao queda, e
# nao lentidao. Com 60, cada maquina que cai prende a serie dela por 45 min a
# mais. Retomar uma serie que o dono ainda gravava custa CPU, e nao estraga a
# entrega: cada gravacao vai para um rascunho de nome proprio antes de
# substituir o arquivo.
#
# O piso util e 2x o HEARTBEAT_MIN. Abaixo disso uma renovacao perdida por
# rede ruim ja dispara a retomada.
LOCK_PARADO_MIN=15

# Serie cujo arquivo mais novo tem menos que isto (minutos) e considerada
# ainda em transito (o Vitrea pode estar gravando) e fica para a proxima volta.
QUIET_MIN=10

# Teto ABSOLUTO de tempo para UMA task (horas): cada task do TotalSegmentator
# (a base e as complementares), e tambem o NV-Segment-CT e o MOOSE pedidos no
# PERSONALIZADO. Passou disso, a task e encerrada. NAO vale para os niveis
# cervicais (teto fixo de 6 h), nem para o CADS (teto fixo de 1 h), nem
# para o modelo do encefalo em TC (teto fixo de 2 h): mudar este numero nao
# muda o deles.
# O travamento (as tres chaves TRAVA_ abaixo) decide ANTES dele; este teto e
# o ultimo cinto, para a task que continua dando sinal de vida e nao termina.
TIMEOUT_TASK_H=3

# ─── travamento: quando uma task e dada como TRAVADA ───
# Uma task travada e encerrada SOZINHA (a task, nao a serie); a fila segue
# para a proxima task, e ao fim da lista a travada e refeita UMA vez com um
# plano de memoria menor. Travou de novo: a serie sai sem ela, e o log diz.
#
# Minutos SEM PULSO do processo da task. O envelope do TotalSegmentator bate
# um pulso enquanto trabalha; silencio mais longo que isto e processo parado.
TRAVA_SEM_PULSO_MIN=15

# Minutos SEM PROGRESSO com a memoria acima de TRAVA_RAM_PCT. E a maquina
# PAGINANDO: o processo continua vivo, o disco trabalha, e a task nao anda,
# horas a fio.
TRAVA_PAGINANDO_MIN=30

# Uso de memoria (% da RAM) a partir do qual «sem progresso» conta como
# paginacao, para a regra de cima.
TRAVA_RAM_PCT=95

# Tentativas por série antes de marcar .fail.json e pular
MAX_RETRIES=3

# 0 = processa TODO o arquivo historico; N>0 = só séries dos últimos N dias
# (pela DATA DA SERIE, nao pela data do arquivo no disco)
DAYS_BACK=0

# Vazio = RTSTRUCT salvo na MESMA pasta da série (padrão do serviço).
# Ou um caminho para espelhar a saída em outra árvore (a estrutura de pastas
# relativa ao ROOT e preservada, para nao misturar pacientes).
OUT_DIR=

# Vazio = log ao lado deste arquivo. O log em arquivo e o que permite
# diagnosticar de manha o que travou de madrugada.
LOG_DIR=

# Opcional: pasta onde cada maquina grava seu sinal de vida, para dar para
# conferir de outro micro se o vigia da estacao parou. Combine com o TI.
STATUS_DIR=

# A pasta que o «Rodar agora» ja abre. Vazia = o seletor comeca nas unidades.
# E' comodidade, e nao destino: ela nao decide onde nada e' gravado, e nao tem
# relacao com o ROOT. Apontar para uma arvore de pacientes aqui e' so' dizer
# «e' daqui que eu sempre parto».
PASTA_FAVORITA=

# A ESCALA da suavizacao. Nao e "quanto alisar": QUANTO e decidido POR
# ESTRUTURA, dentro do programa, e este numero multiplica a tabela inteira.
# 1,5 usa a tabela como ela foi medida; 1,0 (o padrao) leva tudo a dois
# tercos; 0 desliga tudo e entrega a mascara crua do voxel; 3,0 dobra tudo,
# mantendo osso conservador e parenquima solto.
#
# Por que por estrutura, e nao um numero para todas: medido, o otimo nao segue
# o tamanho do orgao, segue quanto DETALHE VERDADEIRO ele tem. Um tubo reto de
# 2,5 mm melhora ate 6 mm de suavizacao; um TORTUOSO da mesma espessura piora
# depois de 1,5 mm, porque ali a tortuosidade e o orgao e nao o ruido.
#
# Suavizar nao muda o volume: a suavizacao preserva o volume por construcao,
# e o que ela muda e a forma da borda. Fica declarado na descricao do
# RTSTRUCT.
#
# O cursor ESCALA a tabela inteira, e nao a substitui: com 1,0 tudo cai para
# dois tercos E AS PROPORCOES ANATOMICAS FICAM -- osso 0,8 -> 0,53;
# parenquima 2,5 -> 1,67; vaso 1,5 -> 1,00. Por isso a intensidade se ajusta
# AQUI, e nao na tabela: mexer nos valores por estrutura desfaria o racional
# de borda de cada um (borda cortical e real, haustracao E o orgao, ar-tecido
# e o maior contraste da TC). Suavizar demais tira as pontas das estruturas
# finas (hioide, cartilagens, digastrico, platisma, constritores).
SUAVIZAR_MM=1.0
"""

DEFAULTS = {"ROOT": "", "DRY_RUN": "0",
            "DEVICE": "auto",
            "RECORTE_NO_CORPO": "1",
            "MODALITIES": "CT", "MIN_SLICES": "20",
            "SCAN_EVERY_MIN": "10", "PORT": "8777",
            "IDIOMA": "",
            "TPS_DESTINO": "",
            "LOCK_MAX_H": "2",
            "HEARTBEAT_MIN": "5", "LOCK_PARADO_MIN": "15",
            "QUIET_MIN": "10", "TIMEOUT_TASK_H": "3",
            "TRAVA_SEM_PULSO_MIN": "15", "TRAVA_PAGINANDO_MIN": "30",
            "TRAVA_RAM_PCT": "95",
            "MAX_RETRIES": "3", "DAYS_BACK": "0", "OUT_DIR": "",
            "LOG_DIR": "", "STATUS_DIR": "",
            "PASTA_FAVORITA": "",
            "SUAVIZAR_MM": "1.0"}

CHAVES_OBSOLETAS = {
    "INCLUIR_NV": u"comparacao de modelos so no PERSONALIZADO do «Rodar agora»",
    "INCLUIR_CADS": u"comparacao de modelos so no PERSONALIZADO do «Rodar agora»",
    "INCLUIR_MOOSE": u"comparacao de modelos so no PERSONALIZADO do «Rodar agora»",
    "INCLUIR_HNLNL": u"os niveis cervicais rodam no AUTO quando o pescoco e "
                     u"detectado, e entram no FULL",
    "ENTREGAR_TS": u"o TS cru so sai por pedido, no PERSONALIZADO",
    "TIMEOUT_NV_H": u"o TIMEOUT_TASK_H e o teto do NV tambem",
    "URL_VERSOES": u"o endereco das versoes mora no codigo",
    "INCLUIR_VISTA3D": u"nome antigo do INCLUIR_NV, que saiu",
    "TIMEOUT_VISTA_H": u"nome antigo do TIMEOUT_NV_H, que saiu",
    "ENTREGAR_NV": u"nome antigo do INCLUIR_NV, que saiu",
    "TASKS": u"o vigia roda sempre o modo AUTO (a base e as tasks que a "
             u"anatomia pede); task avulsa e achado so no PERSONALIZADO",
}
VERSAO_DA_SAIDA = {"TASKS": u"v8.4"}

def url_das_versoes():
    try:
        import radai_version as _rv
        return str(_rv.url_em_vigor() or "")
    except Exception:
        return ""


AVISOS_CFG = []


def load_cfg():
    if not CFG_PATH.exists():
        try:
            CFG_PATH.write_text(DEFAULT_CFG, encoding="utf-8")
        except Exception as e:
            AVISOS_CFG.append("nao consegui criar %s (%s)" % (CFG_PATH.name, e))
    cfg = dict(DEFAULTS)
    try:
        for linha in CFG_PATH.read_text(encoding="utf-8-sig", errors="ignore").splitlines():
            linha = linha.strip()
            if not linha or linha.startswith("#") or "=" not in linha:
                continue
            k, v = linha.split("=", 1)
            k = k.strip()
            if k in CHAVES_OBSOLETAS and k not in DEFAULTS:
                aviso = (u"chave obsoleta ignorada: %s (saiu na %s: %s)"
                         % (k, VERSAO_DA_SAIDA.get(k, u"v8.3"),
                            CHAVES_OBSOLETAS[k]))
                if aviso not in AVISOS_CFG:
                    AVISOS_CFG.append(aviso)
                continue
            if k not in DEFAULTS:
                AVISOS_CFG.append("chave desconhecida no config, ignorada: %s" % k)
                continue
            cfg[k] = v.strip()
    except Exception as e:
        AVISOS_CFG.append("nao consegui ler o config (%s); usando os padroes" % e)
    return cfg


def migrar_config(caminho=None, obsoletas=None, vivas=None, log=None):
    log = log or wlog
    caminho = str(caminho or CFG_PATH)
    obsoletas = CHAVES_OBSOLETAS if obsoletas is None else obsoletas
    vivas = DEFAULTS if vivas is None else vivas
    _texto, valores = radai_config.ler_arquivo(caminho)
    alvo = [k for k in valores if k in obsoletas and k not in vivas]
    if not alvo:
        return []
    ok, tiradas, copia, erro = radai_config.remover(caminho, alvo)
    if not ok:
        log(u"config: nao consegui tirar as chaves que sairam (%s); elas "
            u"continuam ignoradas" % erro)
        return []
    log(u"config: migrado uma vez - tirei %d chave(s) que nao valem mais "
        u"(%s); o arquivo anterior ficou em %s"
        % (len(tiradas), u", ".join(tiradas), os.path.basename(copia) or u"-"))
    AVISOS_CFG[:] = [a for a in AVISOS_CFG
                     if not any(a.startswith(u"chave obsoleta ignorada: %s " % k)
                                for k in tiradas)]
    return tiradas


def _liga(cfg, chave):
    return str(cfg.get(chave, "")).strip().lower() in (
        "1", "true", "sim", "yes", "on", "ligado")


def _num(cfg, chave, conv, minimo=None, maximo=None):
    bruto = str(cfg.get(chave, DEFAULTS[chave])).split("#")[0].strip().replace(",", ".")
    try:
        v = conv(bruto)
    except Exception:
        v = conv(DEFAULTS[chave])
        AVISOS_CFG.append("%s=%r nao e numero; usando %s" % (chave, bruto, v))
    if minimo is not None and v < minimo:
        v = minimo
    if maximo is not None and v > maximo:
        v = maximo
    return v


def base_do_vigia():
    try:
        import radai_modes as _modos
        return _modos.base_de("CT")
    except Exception:
        return "total_v3"


CFG = load_cfg()

SO_NO_ARRANQUE = ("PORT",)


URL_VERSOES = ""


def _idioma_canonico(bruto):
    b = str(bruto or "").split("#")[0].strip().strip('"')
    if not b:
        return ""
    try:
        import radai_languages as _rl
        c = _rl.canonico(b)
    except Exception:
        return b
    if not c:
        AVISOS_CFG.append(u"IDIOMA=%s nao e um idioma desta instalacao; "
                          u"uso o automatico" % b[:20])
    return c


def regra_de_travamento():
    return {"sem_pulso_min": float(TRAVA_SEM_PULSO_S) / 60.0,
            "paginando_min": float(TRAVA_PAGINANDO_S) / 60.0,
            "ram_pct": float(TRAVA_RAM_PCT)}


def aplicar_cfg():
    global ROOT, DRY_RUN, TASKS, MODALITIES, MIN_SLICES, SCAN_EVERY, LOCK_MAX_S
    global HEARTBEAT_S, QUIET_S, TIMEOUT_TASK_S, MAX_RETRIES, DAYS_BACK
    global LOCK_PARADO_S
    global OUT_DIR, LOG_DIR, STATUS_DIR, URL_VERSOES
    global RECORTE_NO_CORPO
    global SUAVIZAR_MM
    global IDIOMA, TRAVA_SEM_PULSO_S, TRAVA_PAGINANDO_S, TRAVA_RAM_PCT
    ROOT = CFG["ROOT"].strip().strip('"')
    DRY_RUN = str(CFG["DRY_RUN"]).strip().lower() in ("1", "true", "sim", "yes")
    TASKS = [base_do_vigia()]
    MODALITIES = set(m.upper() for m in
                     re.split(r"[,;\s]+", CFG["MODALITIES"] or "") if m)
    MIN_SLICES = _num(CFG, "MIN_SLICES", int, 5)
    SCAN_EVERY = _num(CFG, "SCAN_EVERY_MIN", int, 1) * 60
    LOCK_MAX_S = _num(CFG, "LOCK_MAX_H", float, 0.1) * 3600
    HEARTBEAT_S = _num(CFG, "HEARTBEAT_MIN", float, 0.5) * 60
    LOCK_PARADO_S = _num(CFG, "LOCK_PARADO_MIN", float, 1.0) * 60
    QUIET_S = _num(CFG, "QUIET_MIN", float, 0) * 60
    TIMEOUT_TASK_S = int(_num(CFG, "TIMEOUT_TASK_H", float, 0.1) * 3600)
    TRAVA_SEM_PULSO_S = _num(CFG, "TRAVA_SEM_PULSO_MIN", float, 2.0) * 60
    TRAVA_PAGINANDO_S = _num(CFG, "TRAVA_PAGINANDO_MIN", float, 2.0) * 60
    TRAVA_RAM_PCT = _num(CFG, "TRAVA_RAM_PCT", float, 50.0, 100.0)
    MAX_RETRIES = _num(CFG, "MAX_RETRIES", int, 1)
    DAYS_BACK = _num(CFG, "DAYS_BACK", int, 0)
    OUT_DIR = CFG["OUT_DIR"].strip().strip('"')
    _padrao_log = str(HERE)
    try:
        if radai_archive is not None:
            _padrao_log = str(radai_archive.raiz())
    except Exception:
        pass
    LOG_DIR = Path(CFG["LOG_DIR"].strip().strip('"') or _padrao_log)
    STATUS_DIR = CFG["STATUS_DIR"].strip().strip('"')
    URL_VERSOES = url_das_versoes()
    IDIOMA = _idioma_canonico(CFG.get("IDIOMA", ""))
    _tps = str(CFG.get("TPS_DESTINO", "")).split("#")[0].strip()
    if _tps and not radai_config.tps_canonico(_tps):
        AVISOS_CFG.append(u"TPS_DESTINO=%s nao e eclipse nem monaco; o "
                          u"RTSTRUCT sai como %s"
                          % (str(CFG.get("TPS_DESTINO"))[:20],
                             radai_config.rotulo_do_tps("eclipse")))
    RECORTE_NO_CORPO = _liga(CFG, "RECORTE_NO_CORPO")
    SUAVIZAR_MM = _num(CFG, "SUAVIZAR_MM", float, 0.0, 5.0)


aplicar_cfg()
PORT = _num(CFG, "PORT", int, 1, 65535)

LOGBUF = deque(maxlen=800)
LOGSEQ = [0]
_CONSOLE = {"saida": None, "ate_o_painel": False}
PULSO = None
LOCK = threading.Lock()
LOCK_DO_LOG = threading.Lock()
RESCAN_NOW = threading.Event()
RECARREGAR = threading.Event()
_RECARGA = {"pedida": 0, "aplicada": 0, "resultado": ""}
_RECARGA_FEITA = threading.Condition()
CHAVES_DO_TURNO = ("ROOT", "MODALITIES", "DAYS_BACK")
TURNO_TEMPORARIO = {}
ROOT_DO_TURNO = {}
_LOG_FH = None
_LOG_TENTADO = False
LOG_PATH = None


def _abrir_log():
    global _LOG_FH, LOG_PATH, _LOG_TENTADO
    _LOG_TENTADO = True
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        LOG_PATH = LOG_DIR / "radai_vigia.log"
        if LOG_PATH.exists() and LOG_PATH.stat().st_size > 8 * 1024 * 1024:
            antigo = LOG_DIR / "radai_vigia.anterior.log"
            try:
                if antigo.exists():
                    antigo.unlink()
                LOG_PATH.rename(antigo)
            except Exception:
                pass
        _LOG_FH = open(str(LOG_PATH), "a", encoding="utf-8", errors="replace")
    except Exception:
        _LOG_FH = None


_COLETOR_DA_SERIE = [None]


class _EscutaDaSerie(object):

    def __init__(self, coletor):
        self.coletor = coletor
        self.arquivo = None
        self.threads = set([threading.current_thread()])

    def ouvir(self, linha):
        if threading.current_thread() in self.threads:
            self.coletor(linha)
            if self.arquivo is not None:
                self.arquivo(linha)


def _falar_pela_serie(coletor):
    e = _COLETOR_DA_SERIE[0]
    if coletor is not None and e is not None and e.coletor is coletor:
        e.threads.add(threading.current_thread())


def linhas_de_log(msg, quando=None):
    carimbo = (quando or datetime.now()).strftime("%d/%m %H:%M:%S")
    texto = str(msg if msg is not None else "")
    partes = texto.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    partes = [p for p in partes if p.strip()] or [partes[0] if partes else ""]
    return ["[%s] %s" % (carimbo, p) for p in partes]


def wlog(msg):
    if not _LOG_TENTADO:
        _abrir_log()
    linhas = linhas_de_log(msg)
    bloco = "\n".join(linhas) + "\n"
    with LOCK_DO_LOG:
        for linha in linhas:
            LOGBUF.append(linha)
            LOGSEQ[0] += 1
        if _LOG_FH is not None:
            try:
                _LOG_FH.write(bloco)
                _LOG_FH.flush()
            except Exception:
                pass
        try:
            _saida = (_CONSOLE["saida"] if _CONSOLE["saida"] is not None
                      else sys.stdout)
            if _CONSOLE["ate_o_painel"] and _painel_no_ar():
                _saida = None
                _esvaziar_o_console()
            if _saida is not None:
                _saida.write(bloco)
                _saida.flush()
        except Exception:
            pass
    escuta = _COLETOR_DA_SERIE[0]
    if escuta is not None:
        for linha in linhas:
            escuta.ouvir(linha)


def fatia_do_log(desde=0, teto=400):
    with LOCK_DO_LOG:
        buf = list(LOGBUF)
        total = max(int(LOGSEQ[0]), len(buf))
    primeiro = total - len(buf)
    try:
        desde = int(desde or 0)
    except (TypeError, ValueError):
        desde = 0
    reiniciou = desde > total
    if reiniciou or desde < primeiro:
        desde = primeiro
    i = desde - primeiro
    fatia = buf[i:i + int(teto)]
    return fatia, desde + len(fatia), reiniciou


STATE = {
    "ligado": False,
    "paused": False, "current": None, "queue": [], "n_queue": 0, "done_today": 0,
    "fila_manual": 0,
    "fails": [], "last_scan": None, "scan_secs": 0, "series_total": 0,
    "started": datetime.now().strftime("%d/%m %H:%M"), "worker_vivo": time.time(),
    "worker_erro": "", "root_ok": None, "sem_permissao": 0, "em_transito": 0,
    "nao_simulacao": 0,
    "recarga": "",
    "ambiente_erro": "",
    "puladas": 0,
    "adiadas": 0,
    "nao_contornaveis": 0,
    "em_espera": 0,
    "turno_id": datetime.now().strftime("%Y%m%d%H%M%S"),
    "assinaturas": {},
    "alertas_de_assinatura": [],
    "overnight": False,
    "overnight_desde": 0.0,
    "overnight_pausados": [],
    "arranque": {"estado": "esperando", "passo": 0, "total": 0, "nome": "",
                 "arquivo": "", "segundos": 0.0},
    "dispositivo": {},
}
SEM_PERMISSAO = set()
PULADAS_POR_FALHA = []
NAO_CONTORNAVEIS = []
EM_ESPERA = []
REPETICOES_DA_ASSINATURA = 3


def bate_ponto(erro=""):
    STATE["worker_vivo"] = time.time()
    if erro:
        STATE["worker_erro"] = erro


_STATUS_DIR_RECUSADO = [False]


def conferir_status_dir():
    if not (STATUS_DIR or "").strip():
        return True
    try:
        import radai_archive
        nuvem, motivo = radai_archive.em_pasta_sincronizada(STATUS_DIR)
    except Exception as e:
        wlog("nao consegui conferir se o STATUS_DIR sincroniza (%s) — vou "
             "gravar nele assim mesmo" % str(e)[:120])
        return True
    if not nuvem:
        return True
    _STATUS_DIR_RECUSADO[0] = True
    wlog("")
    wlog("STATUS_DIR RECUSADO: `%s`" % STATUS_DIR)
    wlog("  ele esta dentro de uma pasta que sincroniza com a nuvem (%s)."
         % motivo)
    wlog("  O sinal de vida leva, da serie em curso, a data e os 8 ultimos")
    wlog("  digitos do UID (sem nome, sem PatientID e sem caminho) -- e mesmo")
    wlog("  isso e dado de paciente, que nao sai do ambiente da clinica.")
    wlog("  Escolha com o TI uma pasta de rede que NAO sincronize. O vigia")
    wlog("  roda normalmente; so o painel da frota fica sem as outras")
    wlog("  maquinas.")
    wlog("")
    return False


def sem_caminho_nem_uid(atual, com_pid=False):
    if not atual:
        return None
    fora = dict(atual)
    for _f in ("sdir", "uid_cheio"):
        fora.pop(_f, None)
    if not com_pid:
        fora.pop("pid", None)
    return fora


def erro_sem_caminho_nem_uid(texto):
    t = str(texto or u"")
    if not t:
        return t
    try:
        import radai_records
        t = radai_records.sem_caminhos(t)
    except Exception:
        t = re.sub(r"(?:[A-Za-z]:[\\/]|\\\\[^\\/\s]+[\\/])[^\r\n]*",
                   u"<caminho>", t)
    return re.sub(r"(?<![\d.])\d+(?:\.\d+){4,}(?![\d.])", u"<uid>", t)


def salvar_status():
    dado = {"maquina": MACHINE, "versao": APPVER, "dry_run": DRY_RUN,
            "quando": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "pausado": STATE["paused"], "atual": sem_caminho_nem_uid(STATE["current"]),
            "na_fila": STATE["n_queue"], "concluidas_sessao": STATE["done_today"],
            "adiadas": int(STATE.get("adiadas") or 0),
            "ultima_varredura": STATE["last_scan"], "root": ROOT,
            "worker_erro": erro_sem_caminho_nem_uid(STATE["worker_erro"])}
    destinos = [LOG_DIR / "radai_status.json"]
    if STATUS_DIR and not _STATUS_DIR_RECUSADO[0]:
        destinos.append(Path(STATUS_DIR) / ("%s.json" % MACHINE))
    for d in destinos:
        try:
            d.parent.mkdir(parents=True, exist_ok=True)
            d.write_text(json.dumps(dado, ensure_ascii=False, indent=1), encoding="utf-8")
        except Exception:
            pass
    _STATUS_SALVO[0] = time.time()


_STATUS_SALVO = [0.0]


def _status_periodico(agora=None):
    agora = time.time() if agora is None else float(agora)
    if agora - _STATUS_SALVO[0] < HEARTBEAT_S:
        return False
    try:
        salvar_status()
    except Exception:
        return False
    return True


_EM_USO_PARAR = threading.Event()
_EM_USO_TRAVA = threading.Lock()
_EM_USO_FALHOU = [False]
_EM_USO_ATIVO = [False]


def _sinalizar_em_uso_uma_vez():
    try:
        import radai_cleaner
        with _EM_USO_TRAVA:
            if _EM_USO_PARAR.is_set():
                return False
            ok = radai_cleaner.gravar_em_uso(
                PORT, segmentando=bool(quem_esta_segmentando()))
    except Exception:
        ok = False
    if not ok and not _EM_USO_FALHOU[0]:
        wlog("sinalizacao para o Workstation RT: nao consegui gravar o "
             "em_uso.json — o vigia segue, e o kit deles volta a contar so "
             "com a marca de pasta")
    elif ok and _EM_USO_FALHOU[0]:
        wlog("sinalizacao para o Workstation RT: em_uso.json gravado de novo")
    _EM_USO_FALHOU[0] = not ok
    return ok


def _laco_em_uso():
    import radai_cleaner
    while not _EM_USO_PARAR.is_set():
        _sinalizar_em_uso_uma_vez()
        _EM_USO_PARAR.wait(radai_cleaner.RENOVAR_EM_USO_S)


def iniciar_sinalizacao():
    _EM_USO_PARAR.clear()
    _EM_USO_ATIVO[0] = True
    try:
        import atexit
        atexit.register(encerrar_sinalizacao)
    except Exception:
        pass
    threading.Thread(target=_laco_em_uso, name="radai_em_uso",
                     daemon=True).start()


def encerrar_sinalizacao():
    _EM_USO_PARAR.set()
    _EM_USO_ATIVO[0] = False
    try:
        import radai_cleaner
        with _EM_USO_TRAVA:
            return radai_cleaner.apagar_em_uso()
    except Exception:
        return False


def _sinalizar_em_uso_agora():
    if not _EM_USO_ATIVO[0]:
        return False
    try:
        return _sinalizar_em_uso_uma_vez()
    except Exception:
        return False


import radai_notify

NOTIFICAR = radai_notify.ambiente_permite()
NOTIFICACAO_PRAZO_S = radai_notify.PRAZO_S
FRASES_DA_NOTIFICACAO = radai_notify.FRASES
_NOTIFICACAO_FALHOU = radai_notify.FALHOU
_ROTULOS_DOS_GRAVADOS = radai_notify.ROTULOS_DOS_GRAVADOS


def _frase_da_notificacao(chave, *args):
    return radai_notify.frase(chave, *args, idioma=(IDIOMA or None))


def _script_da_notificacao(titulo, texto):
    return radai_notify.script(titulo, texto)


def _mostrar_notificacao(titulo, texto):
    return radai_notify.mostrar(titulo, texto)


def _notificar_em_segundo_plano(titulo, texto):
    radai_notify.em_segundo_plano(titulo, texto,
                                  mostrar_fn=_mostrar_notificacao, log=wlog)


def _rotulo_do_gravado(cod):
    return radai_notify.rotulo_do_gravado(cod)


def notificar(chave_titulo, chave_texto, *args):
    try:
        if not NOTIFICAR or DRY_RUN:
            return False
        titulo = _frase_da_notificacao(chave_titulo)
        texto = _frase_da_notificacao(chave_texto, *args)
        return radai_notify.disparar(
            titulo, texto, mostrar_fn=_mostrar_notificacao, log=wlog)
    except Exception:
        return False


CACHE_DIR = Path(os.environ.get("LOCALAPPDATA", tempfile.gettempdir())) / "RadAI_Watcher"
try:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
except Exception:
    CACHE_DIR = Path(tempfile.gettempdir())
CACHE_PATH = CACHE_DIR / "index.json"

TAGS_UTEIS = ["SeriesInstanceUID", "Modality", "PatientID",
              "SeriesDate", "SeriesTime", "StudyDate", "StudyTime",
              "SliceThickness", "SpacingBetweenSlices",
              "ImagePositionPatient",
              "StudyInstanceUID", "SeriesDescription",
              "ImageOrientationPatient", "ImageType", "SamplesPerPixel",
              "SOPClassUID"]
VERSAO_DO_INDICE = 2

SIM_PISO_MM = 1.0
SIM_TETO_MM = 5.0
SIM_FOLGA_MM = 0.05


CACHE_VERSAO = 3


def _orientacao_e_cor(rec, ds):
    import radai_triage as _tr
    ax = _tr.orientacao_axial(getattr(ds, "ImageOrientationPatient", None))
    if ax is not None and rec.get("axial") is not False:
        rec["axial"] = ax
    try:
        spp = int(getattr(ds, "SamplesPerPixel", 0) or 0)
    except (TypeError, ValueError):
        spp = 0
    if spp:
        rec["colorida"] = bool(rec.get("colorida")) or spp > 1
    if "ImageType" in ds or "SOPClassUID" in ds:
        rec["secundaria"] = (bool(rec.get("secundaria"))
                             or _tr.captura_secundaria(
                                 getattr(ds, "ImageType", None),
                                 getattr(ds, "SOPClassUID", None)))


def _juntar_orientacao_e_cor(s, rec):
    if rec.get("axial") is False or (rec.get("axial") is True
                                     and s.get("axial") is not False):
        s["axial"] = rec.get("axial")
    for k in ("colorida", "secundaria"):
        if rec.get(k) is not None:
            s[k] = bool(s.get(k)) or bool(rec.get(k))


def cache_load():
    try:
        c = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(c, dict) or c.get("_v") != CACHE_VERSAO:
        return {}
    return c.get("pastas") or {}


def cache_save(c):
    try:
        tmp = CACHE_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps({"_v": CACHE_VERSAO, "pastas": c}),
                       encoding="utf-8")
        os.replace(str(tmp), str(CACHE_PATH))
    except Exception:
        pass


def is_dicom(path):
    try:
        import radai_dicom
        sim, _motivo = radai_dicom.vale_abrir(path)
        return bool(sim)
    except Exception:
        pass
    try:
        with open(path, "rb") as f:
            f.seek(128)
            return f.read(4) == b"DICM"
    except Exception:
        return False


def parse_date(ds):
    d = str(getattr(ds, "SeriesDate", "") or getattr(ds, "StudyDate", "") or "").strip()
    t = str(getattr(ds, "SeriesTime", "") or getattr(ds, "StudyTime", "") or "").strip()
    if len(d) == 8 and d.isdigit():
        t = (t.split(".")[0] + "000000")[:6] if t else "000000"
        return d + t
    return None


def rel_root(caminho):
    try:
        return os.path.relpath(sem_prefixo(caminho), sem_prefixo(ROOT))
    except Exception:
        return os.path.basename(str(caminho))


def caminho_longo(caminho):
    try:
        bruto = str(caminho)
        if os.path.isabs(bruto):
            p = bruto.replace("/", os.sep)
        else:
            cauda = bruto[len(bruto.rstrip(". ")):]
            p = os.path.abspath(bruto) + cauda
    except Exception:
        return str(caminho)
    if os.name != "nt" or p.startswith("\\\\?\\"):
        return p
    if p.startswith("\\\\"):
        return "\\\\?\\UNC" + p[1:]
    return "\\\\?\\" + p


def sem_prefixo(caminho):
    c = str(caminho)
    if c.startswith("\\\\?\\UNC\\"):
        return "\\\\" + c[8:]
    if c.startswith("\\\\?\\"):
        return c[4:]
    return c


def _sobrevive_ao_ponto(caminho):
    try:
        return os.path.isdir(caminho_longo(caminho))
    except Exception:
        return False


def _erro_walk(err):
    alvo = str(getattr(err, "filename", "") or "")
    if alvo and (alvo.rstrip().endswith(".") or alvo != alvo.rstrip()):
        if _sobrevive_ao_ponto(alvo):
            wlog("varredura: %s termina em ponto e o Windows nao a abre pelo "
                 "nome normal; lida pelo caminho literal" % rel_root(alvo))
            return
    wlog("varredura: sem acesso a %s (%s)" % (rel_root(alvo or "?"), err))


def _prefixo_do_bridge():
    try:
        from radai_dicom import PREFIXO_SAIDA
        return PREFIXO_SAIDA
    except Exception:
        return "DICOM_BRIDGE_"


def scan_root():
    t0 = time.time()
    cache = cache_load()
    novo_cache = {}
    series, done_dates = {}, []
    n_dirs = 0

    corte_pasta = None
    if DAYS_BACK > 0:
        corte_pasta = time.time() - (DAYS_BACK * 2 + 30) * 86400

    _prefixo_bridge = _prefixo_do_bridge()
    for dirpath, dirnames, filenames in os.walk(caminho_longo(ROOT),
                                                onerror=_erro_walk):
        base = os.path.basename(dirpath)
        try:
            import radai_batch as _rl
            if base.lower() in _rl.PASTAS_DE_SISTEMA:
                dirnames[:] = []
                continue
        except Exception:
            pass
        # GUARDA: a saida do DicomBridge e copia de serie (as vezes com os
        # mesmos UIDs); segmentar e gravar RTSTRUCT nela seria escrita nao pedida.
        if base.startswith(_prefixo_bridge):
            dirnames[:] = []
            continue
        if base in ("_RadAI", "_RadAI_status"):
            if base == "_RadAI":
                _afastados = set()
                for fn in filenames:
                    if MARCA_DO_DONE_AFASTADO in fn:
                        _afastados.add(fn.split(MARCA_DO_DONE_AFASTADO, 1)[0])
                for _u_af in sorted(_afastados):
                    resolver_done_afastado(os.path.dirname(dirpath), _u_af)
                for fn in filenames:
                    if fn.endswith(".done.json"):
                        try:
                            dd = json.loads(Path(dirpath, fn).read_text(encoding="utf-8"))
                            if dd.get("date"):
                                done_dates.append(dd["date"])
                        except Exception:
                            pass
            dirnames[:] = []
            continue
        n_dirs += 1
        if not filenames:
            continue
        try:
            st = os.stat(dirpath)
        except Exception:
            continue
        if corte_pasta and st.st_mtime < corte_pasta:
            continue

        sig = [st.st_mtime, len(filenames)]
        ent = cache.get(dirpath)
        if (ent and ent.get("sig") == sig
                and ent.get("v") == VERSAO_DO_INDICE):
            achadas = ent.get("series", {})
        else:
            achadas = {}
            for fn in filenames:
                fp = os.path.join(dirpath, fn)
                try:
                    if not is_dicom(fp):
                        continue
                    ds = pydicom.dcmread(fp, stop_before_pixels=True, force=True,
                                         specific_tags=TAGS_UTEIS)
                    uid = str(getattr(ds, "SeriesInstanceUID", "") or "")
                    if not uid:
                        continue
                    rec = achadas.setdefault(uid, {
                        "count": 0, "date": None, "pid": "",
                        "modality": str(getattr(ds, "Modality", "") or "").upper(),
                        "mais_novo": 0,
                        "z0": None, "z1": None, "esp_dec": None,
                        "estudo": str(getattr(ds, "StudyInstanceUID", "")
                                      or ""),
                        "desc": str(getattr(ds, "SeriesDescription", "")
                                    or "")[:64]})
                    rec["count"] += 1
                    _orientacao_e_cor(rec, ds)
                    try:
                        _z = float(ds.ImagePositionPatient[2])
                        rec["z0"] = _z if rec["z0"] is None else min(rec["z0"], _z)
                        rec["z1"] = _z if rec["z1"] is None else max(rec["z1"], _z)
                    except Exception:
                        pass
                    if rec["esp_dec"] is None:
                        for _t in ("SpacingBetweenSlices", "SliceThickness"):
                            try:
                                _v = float(getattr(ds, _t, 0) or 0)
                            except Exception:
                                _v = 0.0
                            if _v > 0:
                                rec["esp_dec"] = _v
                                break
                    if not rec["date"]:
                        rec["date"] = parse_date(ds)
                    if not rec["pid"]:
                        rec["pid"] = str(getattr(ds, "PatientID", "") or "")
                    try:
                        rec["mais_novo"] = max(rec["mais_novo"], os.path.getmtime(fp))
                    except Exception:
                        pass
                except Exception:
                    continue
        novo_cache[dirpath] = {"sig": sig, "series": achadas,
                               "v": VERSAO_DO_INDICE}

        for uid, rec in achadas.items():
            if rec.get("modality") not in MODALITIES:
                continue
            s = series.setdefault(uid, {"dir": dirpath, "dirs": {}, "count": 0,
                                        "date": rec.get("date"), "pid": rec.get("pid"),
                                        "uid": uid, "mais_novo": 0,
                                        "z0": None, "z1": None,
                                        "esp_dec": None,
                                        "modality": rec.get("modality") or "",
                                        "estudo": rec.get("estudo") or "",
                                        "desc": rec.get("desc") or ""})
            s["dirs"][dirpath] = rec.get("count", 0)
            s["count"] += rec.get("count", 0)
            for _k, _f in (("z0", min), ("z1", max)):
                _v = rec.get(_k)
                if _v is not None:
                    s[_k] = _v if s.get(_k) is None else _f(s[_k], _v)
            if s.get("esp_dec") is None:
                s["esp_dec"] = rec.get("esp_dec")
            _juntar_orientacao_e_cor(s, rec)
            s["mais_novo"] = max(s["mais_novo"], rec.get("mais_novo", 0))
            if not s["date"]:
                s["date"] = rec.get("date")
            if not s["pid"]:
                s["pid"] = rec.get("pid")

    cache_save(novo_cache)

    for uid, s in series.items():
        s["dir"] = max(s["dirs"].items(), key=lambda kv: kv[1])[0] if s["dirs"] else s["dir"]
        if not s["date"]:
            s["data_da_pasta"] = True
            try:
                s["date"] = datetime.fromtimestamp(os.stat(s["dir"]).st_mtime).strftime("%Y%m%d%H%M%S")
            except Exception:
                s["date"] = "00000000000000"

    series = dict((u, s) for u, s in series.items() if s["count"] >= MIN_SLICES)

    if DAYS_BACK > 0:
        _quando = max(0.0, time.time() - DAYS_BACK * 86400)
        limite = datetime.fromtimestamp(_quando).strftime("%Y%m%d%H%M%S")
        series = dict((u, s) for u, s in series.items() if (s["date"] or "") >= limite)

    STATE["series_total"] = len(series)
    STATE["last_scan"] = datetime.now().strftime("%H:%M:%S")
    STATE["scan_secs"] = int(time.time() - t0)
    _lembrar_da_varredura(series)
    return series, done_dates


_DA_VARREDURA = {}
_DA_VARREDURA_TRAVA = threading.Lock()


def _lembrar_da_varredura(series):
    novo = {}
    for uid, sr in (series or {}).items():
        try:
            novo[str(uid)] = (str(sr.get("dir") or ""),
                              str(sr.get("pid") or ""))
        except Exception:
            continue
    with _DA_VARREDURA_TRAVA:
        _DA_VARREDURA.clear()
        _DA_VARREDURA.update(novo)


def serie_da_varredura(uid):
    with _DA_VARREDURA_TRAVA:
        return _DA_VARREDURA.get(str(uid or ""), ("", ""))


def espessura_varrida(s):
    try:
        import radai_triage
        return radai_triage.espessura_varrida(s)
    except Exception:
        return 0.0


def escolher_simulacao(series):
    try:
        import radai_triage
    except Exception as e:
        wlog("nao consegui carregar a triagem (%s): vou contornar TODAS as "
             "series desta volta, em vez de pular alguma calado"
             % (str(e)[:120],))
        return dict((u, u"triagem indisponivel: nao escolhi") 
                    for u in (series or {}))
    return radai_triage.escolher_simulacao(series)


def marker_dir(sdir, criar=False):
    d = Path(sdir) / "_RadAI"
    if criar:
        d.mkdir(parents=True, exist_ok=True)
    return d


_PERIGO_NO_NOME = ("/", "\\", ":", "\x00")


def uid_ok(uid):
    s = u"%s" % (uid or u"")
    if not s or len(s) > 128:
        return False
    if s in (u".", u"..") or u".." in s:
        return False
    if any(ch in s for ch in _PERIGO_NO_NOME):
        return False
    return not any(ord(ch) < 32 for ch in s)


def _desconto_do_entregue():
    try:
        import radai_sets
        return radai_sets.desconto_do_entregue()
    except Exception:
        return False


def m_path(sdir, uid, kind, criar=False):
    if not uid_ok(uid):
        raise ValueError(
            "SeriesInstanceUID escaparia da pasta do paciente: %r — a serie "
            "e recusada, e o marcador nao e escrito" % (uid,))
    d = marker_dir(sdir, criar)
    alvo = d / ("%s.%s.json" % (uid, kind))
    try:
        if os.path.commonpath([os.path.abspath(str(d)),
                               os.path.abspath(str(alvo))]) != \
                os.path.abspath(str(d)):
            raise ValueError("marcador escaparia de _RadAI: %r" % (uid,))
    except ValueError:
        raise
    except Exception:
        pass
    return alvo


def has_marker(sdir, uid, kind):
    try:
        return m_path(sdir, uid, kind).exists()
    except Exception:
        return False


def read_marker(sdir, uid, kind):
    try:
        return json.loads(m_path(sdir, uid, kind).read_text(encoding="utf-8"))
    except Exception:
        return None


def _token():
    return "%s#%d" % (MACHINE, os.getpid())


def _processo_vivo(pid):
    try:
        pid = int(pid)
    except Exception:
        return True
    if pid <= 0:
        return True
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        ERROR_ACCESS_DENIED = 5
        ERROR_INVALID_PARAMETER = 87
        try:
            k32 = ctypes.WinDLL("kernel32", use_last_error=True)
            k32.OpenProcess.restype = wintypes.HANDLE
            h = k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
            if h:
                k32.CloseHandle(h)
                return True
            err = ctypes.get_last_error()
            if err == ERROR_ACCESS_DENIED:
                return True
            if err == ERROR_INVALID_PARAMETER:
                return False
            return True
        except Exception:
            return True
    try:
        os.kill(pid, 0)
        return True
    except PermissionError:
        return True
    except (ProcessLookupError, OSError):
        return False
    except Exception:
        return True


_EPOCA_DO_FILETIME = 116444736000000000
TOLERANCIA_DO_SINAL_DA_TRAVA_S = 5.0


def _criado_em(pid):
    if os.name != "nt":
        return None
    try:
        import ctypes
        from ctypes import wintypes
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.OpenProcess.restype = wintypes.HANDLE
        h = k32.OpenProcess(0x1000, False, int(pid))
        if not h:
            return None
        try:
            c, s, kk, u = (wintypes.FILETIME(), wintypes.FILETIME(),
                           wintypes.FILETIME(), wintypes.FILETIME())
            if not k32.GetProcessTimes(h, ctypes.byref(c), ctypes.byref(s),
                                       ctypes.byref(kk), ctypes.byref(u)):
                return None
            return (int(c.dwHighDateTime) << 32) | int(c.dwLowDateTime)
        finally:
            k32.CloseHandle(h)
    except Exception:
        return None


def _ultimo_sinal_da_trava(d):
    d = d or {}
    for k in ("heartbeat", "desde"):
        try:
            if float(d.get(k) or 0) > 0:
                return float(d[k])
        except (TypeError, ValueError):
            pass
    try:
        return time.mktime(datetime.strptime(
            str(d.get("start") or "")[:19], "%Y-%m-%d %H:%M:%S").timetuple())
    except Exception:
        return None


def _com_o_instante_de_criacao(meta):
    try:
        if int(meta.get("pid_os") or 0) == os.getpid():
            c = _criado_em(os.getpid())
            if c is not None:
                meta.setdefault("criado", c)
    except (TypeError, ValueError):
        pass
    return meta


def _dono_da_trava_vivo(d, pid=None, criado_em=None):
    d = d or {}
    pid = pid or d.get("pid_os") or _pid_do_token(d.get("token"))
    if not pid:
        return True
    if not _processo_vivo(pid):
        return False
    criado = (criado_em or _criado_em)(pid)
    if criado is None:
        return True
    # GUARDA: PID + instante de criacao e a identidade; o processo criado depois do ultimo sinal da trava nao e o dono.
    if d.get("criado") is not None:
        try:
            return int(d["criado"]) == int(criado)
        except (TypeError, ValueError):
            pass
    sinal = _ultimo_sinal_da_trava(d)
    if sinal is None:
        return True
    criado_s = (criado - _EPOCA_DO_FILETIME) / 1e7
    return criado_s <= sinal + TOLERANCIA_DO_SINAL_DA_TRAVA_S


def _imagem_do_processo(pid):
    try:
        r = subprocess.run(
            ["tasklist", "/FI", "PID eq %d" % int(pid), "/NH", "/FO", "CSV"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=10)
        saida = (r.stdout or b"").decode("utf-8", "replace").strip()
        if not saida or saida.startswith('"'):
            return saida.split('","')[0].strip('"') if saida.startswith('"') else ""
        return ""
    except Exception:
        return ""


PIDS_LOCAIS = "_radai_pids.json"


def registrar_pid_local():
    try:
        alvo = LOG_DIR / PIDS_LOCAIS
        try:
            antigos = json.loads(alvo.read_text(encoding="utf-8"))
            if not isinstance(antigos, list):
                antigos = []
        except Exception:
            antigos = []
        antigos = [p for p in antigos
                   if isinstance(p, dict) and p.get("pid") != os.getpid()]
        antigos.append({"pid": os.getpid(), "quando": time.time()})
        alvo.write_text(json.dumps(antigos[-50:]), encoding="utf-8")
    except Exception as e:
        wlog("nao consegui registrar o pid local (%s) — vou retomar serie "
             "travada sem matar processo" % str(e)[:90])


PID_LOCAL_VALIDO_H = 12


def _pid_e_nosso(pid):
    try:
        dados = json.loads((LOG_DIR / PIDS_LOCAIS).read_text(encoding="utf-8"))
        limite = time.time() - PID_LOCAL_VALIDO_H * 3600
        return any(isinstance(d, dict)
                   and int(d.get("pid") or -1) == int(pid)
                   and float(d.get("quando") or 0) >= limite
                   for d in dados)
    except Exception:
        return False


def _e_o_proprio_pid(pid):
    try:
        return int(pid) == os.getpid()
    except Exception:
        return False


_SERIES_DESTE_PROCESSO = set()
_PASTAS_DOS_LOCKS = {}

_ESCRITA_DO_LOCK = threading.RLock()


def _matar_travado(pid, uid):
    if _e_o_proprio_pid(pid):
        wlog("lock parado da serie ...%s diz o pid %s, que e ESTE processo: "
             "nao encerro o proprio vigia. O lock e um orfao desta maquina, e "
             "a serie e retomada sem matar nada." % (uid[-8:], pid))
        return False
    if not _pid_e_nosso(pid):
        wlog("lock parado da serie ...%s diz o pid %s, que este registro local "
             "nao conhece — assumo a serie SEM matar processo nenhum"
             % (uid[-8:], pid))
        return False
    img = (_imagem_do_processo(pid) or "").lower()
    if not img:
        return False
    if "python" not in img:
        wlog("lock parado da serie ...%s: o pid %s existe mas e `%s`, e nao um "
             "Python — o worker original ja saiu. Assumo SEM matar."
             % (uid[-8:], pid, img))
        return False
    try:
        subprocess.run(["taskkill", "/PID", str(int(pid)), "/T", "/F"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       timeout=20)
        wlog("worker TRAVADO encerrado (pid %s, `%s`) — a serie ...%s era dele"
             % (pid, img, uid[-8:]))
        return True
    except Exception as e:
        wlog("nao consegui encerrar o worker travado (pid %s): %s" % (pid, e))
        return False


def _pid_do_token(token):
    s = str(token or "")
    if "#" not in s:
        return None
    maq, _, pid = s.rpartition("#")
    if maq != MACHINE:
        return None
    try:
        return int(pid)
    except ValueError:
        return None


def _diagnostico_do_lock(sdir, uid):
    try:
        lp = m_path(sdir, uid, "lock")
        if not lp.exists():
            return "livre", {}
        d = read_marker(sdir, uid, "lock") or {}
        hb = float(d.get("heartbeat") or 0)
        if hb <= 0:
            hb = lp.stat().st_mtime
        parado_ha = time.time() - hb
        pid = d.get("pid_os") or _pid_do_token(d.get("token"))
        desta = str(d.get("machine") or "") == MACHINE
        if parado_ha < LOCK_PARADO_S:
            # GUARDA: batimento recente nao prova vida; processo desta maquina que nao existe mais e trava morta.
            if (desta and pid and not _e_o_proprio_pid(pid)
                    and not _dono_da_trava_vivo(d, pid)):
                return "morto", d
            return "trabalhando", d
        if not desta:
            return "travado", d
        if _e_o_proprio_pid(pid) and uid in _SERIES_DESTE_PROCESSO:
            return "trabalhando", d
        if pid and _dono_da_trava_vivo(d, pid):
            return "travado", d
        return "morto", d
    except Exception:
        return "trabalhando", {}


def soltar_trava_morta(sdir, uid):
    with _ESCRITA_DO_LOCK:
        try:
            lp = m_path(sdir, uid, "lock")
            if not lp.exists():
                return False
        except Exception:
            return False
        estado, dado = _diagnostico_do_lock(sdir, uid)
        if estado != "morto":
            return False
        if str((dado or {}).get("machine") or "") != MACHINE:
            return False
        if not _tomar_lock(lp):
            return False
    _SERIES_DESTE_PROCESSO.discard(uid)
    _PASTAS_DOS_LOCKS.pop(uid, None)
    wlog("trava da serie ...%s solta: era desta maquina e o processo dela "
         "(pid %s) nao existe mais" % (str(uid)[-8:],
                                       (dado or {}).get("pid_os")))
    return True


def _tomar_lock(lp):
    tomado = lp.with_name(lp.name + ".tomado.%s.%d" % (MACHINE, os.getpid()))
    try:
        os.replace(str(lp), str(tomado))
    except Exception:
        return False
    try:
        tomado.unlink()
    except Exception:
        pass
    return True


def claim(sdir, uid, meta):
    try:
        lp = m_path(sdir, uid, "lock", criar=True)
    except Exception as e:
        SEM_PERMISSAO.add(str(sdir))
        wlog("sem permissao de escrita em %s (%s) — nao vou insistir nesta pasta" % (rel_root(sdir), e))
        return False
    try:
        if lp.exists():
            estado, dado = _diagnostico_do_lock(sdir, uid)
            if estado == "trabalhando":
                return False
            if estado in ("travado", "morto"):
                quem = str(dado.get("machine") or "?")
                pid = dado.get("pid_os")
                parado_min = (time.time() - float(dado.get("heartbeat") or 0)) / 60.0
                proprio = (quem == MACHINE and _e_o_proprio_pid(pid))
                if proprio:
                    wlog("serie ...%s: o lock parado e deste processo (pid %s) "
                         "e sobrou de uma execucao que ja terminou — retomo "
                         "sem encerrar nada" % (uid[-8:], pid))
                elif estado == "travado" and quem == MACHINE and pid:
                    _matar_travado(pid, uid)
                if not _tomar_lock(lp):
                    return False
                if quem == MACHINE:
                    wlog("serie ...%s retomada: o dono era desta maquina e "
                         "estava %s ha %.0f min" % (uid[-8:], estado, parado_min))
                else:
                    wlog("serie ...%s ASSUMIDA de `%s`: sem sinal de vida ha "
                         "%.0f min (o limite e %.0f). Se aquela maquina "
                         "voltar, ela vai achar o lock de outro dono e NAO vai "
                         "sobrescrever."
                         % (uid[-8:], quem, parado_min, LOCK_PARADO_S / 60.0))
                meta = dict(meta or {})
                meta.setdefault("machine", MACHINE)
                meta.setdefault("pid_os", os.getpid())
                _com_o_instante_de_criacao(meta)
                meta["token"] = _token()
                meta["heartbeat"] = time.time()
                fd = os.open(str(lp), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                with os.fdopen(fd, "w") as f:
                    json.dump(meta, f)
                _SERIES_DESTE_PROCESSO.add(uid)
                _PASTAS_DOS_LOCKS[uid] = sdir
                return True
            idade = time.time() - lp.stat().st_mtime
            morto = False
            if idade >= 60:
                try:
                    d = read_marker(sdir, uid, "lock") or {}
                    if (str(d.get("machine") or "") == MACHINE
                            and d.get("pid_os")):
                        morto = not _dono_da_trava_vivo(d)
                except Exception:
                    morto = False
            if idade < LOCK_MAX_S and not morto:
                return False
            if not _tomar_lock(lp):
                return False
            if morto:
                wlog("lock de um processo desta maquina que ja saiu "
                     "(pid %s) removido — a serie ...%s volta para a fila"
                     % (d.get("pid_os"), uid[-8:]))
            else:
                wlog("lock sem sinal de vida ha %.1fh removido (serie ...%s)" % (idade / 3600, uid[-8:]))
        meta = dict(meta or {})
        meta.setdefault("machine", MACHINE)
        meta.setdefault("pid_os", os.getpid())
        _com_o_instante_de_criacao(meta)
        meta["token"] = _token()
        meta["heartbeat"] = time.time()
        fd = os.open(str(lp), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        with os.fdopen(fd, "w") as f:
            json.dump(meta, f)
        _SERIES_DESTE_PROCESSO.add(uid)
        _PASTAS_DOS_LOCKS[uid] = sdir
        return True
    except FileExistsError:
        return False
    except OSError as e:
        SEM_PERMISSAO.add(str(sdir))
        wlog("nao consegui reivindicar em %s (%s)" % (rel_root(sdir), e))
        return False


def _regravar_sem_criar(caminho, dado):
    fd = os.open(str(caminho), os.O_WRONLY | os.O_TRUNC)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(dado, f, ensure_ascii=False)


def renovar_lock(sdir, uid, extra=None):
    with _ESCRITA_DO_LOCK:
        try:
            lp = m_path(sdir, uid, "lock")
            # GUARDA: ler e regravar pelo MESMO handle. Aberto, o Windows
            # recusa a renomeacao de `_tomar_lock` da outra maquina; reabrir
            # pelo caminho escreveria o nosso token no lock novo dela.
            with open(str(lp), "r+b") as f:
                try:
                    dado = json.loads(f.read().decode("utf-8"))
                except ValueError:
                    return False
                if not isinstance(dado, dict):
                    return False
                if dado.get("token") != _token():
                    return False
                dado["heartbeat"] = time.time()
                if extra:
                    for k, v in dict(extra).items():
                        if k not in ("token", "machine", "pid_os",
                                     "heartbeat", "criado"):
                            dado[k] = v
                novo = json.dumps(dado, ensure_ascii=False).encode("utf-8")
                f.seek(0)
                f.truncate()
                f.write(novo)
            return True
        except Exception:
            return False


def lock_e_meu(sdir, uid):
    with _ESCRITA_DO_LOCK:
        d = read_marker(sdir, uid, "lock")
        if not isinstance(d, dict) and has_marker(sdir, uid, "lock"):
            # GUARDA: o arquivo existe e veio vazio ou cortado: a regravacao
            # de outra maquina no meio. Uma releitura, e nao um palpite.
            time.sleep(0.2)
            d = read_marker(sdir, uid, "lock")
    if not isinstance(d, dict):
        return False, u""
    if d.get("token") == _token():
        return True, MACHINE
    return False, str(d.get("machine") or d.get("token") or u"?")[:60]


def unclaim(sdir, uid):
    _SERIES_DESTE_PROCESSO.discard(uid)
    _PASTAS_DOS_LOCKS.pop(uid, None)
    with _ESCRITA_DO_LOCK:
        try:
            lp = m_path(sdir, uid, "lock")
            # GUARDA: renomear ANTES de conferir o dono. Ler e depois apagar
            # pelo caminho apagaria o lock que outra maquina criou no meio.
            soltando = lp.with_name(lp.name + ".soltando.%s.%d"
                                    % (MACHINE, os.getpid()))
            os.replace(str(lp), str(soltando))
            try:
                dado = json.loads(soltando.read_text(encoding="utf-8"))
            except Exception:
                dado = None
            tok = dado.get("token") if isinstance(dado, dict) else None
            if tok not in (None, _token()):
                try:
                    os.rename(str(soltando), str(lp))
                except Exception:
                    try:
                        soltando.unlink()
                    except Exception:
                        pass
                wlog("lock da serie ...%s agora e de %s; nao vou remover"
                     % (uid[-8:], tok))
                return
            soltando.unlink()
        except FileNotFoundError:
            pass
        except Exception as e:
            wlog("NAO consegui liberar o lock da serie ...%s (%s) — vai expirar em %.1fh"
                 % (uid[-8:], e, LOCK_MAX_S / 3600))


ENTREGA = "entrega"


def reservar_entrega(sdir, uid):
    try:
        if has_marker(sdir, uid, "done"):
            d = read_marker(sdir, uid, "done") or {}
            return False, (u"a serie ja foi entregue por `%s` as %s — a "
                           u"primeira entrega vale"
                           % (str(d.get("machine") or "?")[:60],
                              str(d.get("finished") or "?")[:19]))
        ep = m_path(sdir, uid, ENTREGA, criar=True)
        dado = {"token": _token(), "machine": MACHINE, "pid_os": os.getpid(),
                "desde": time.time(), "heartbeat": time.time()}
        _com_o_instante_de_criacao(dado)
        for _tentativa in (1, 2):
            try:
                fd = os.open(str(ep), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                with os.fdopen(fd, "w") as f:
                    json.dump(dado, f)
                return True, u""
            except FileExistsError:
                outro = read_marker(sdir, uid, ENTREGA) or {}
                if outro.get("token") == _token():
                    return True, u""
                hb = float(outro.get("heartbeat") or 0) or ep.stat().st_mtime
                _morto = (str(outro.get("machine") or "") == MACHINE
                          and outro.get("pid_os")
                          and not _e_o_proprio_pid(outro.get("pid_os"))
                          and not _dono_da_trava_vivo(outro))
                if time.time() - hb < LOCK_PARADO_S and not _morto:
                    return False, (u"`%s` esta gravando esta serie agora — a "
                                   u"primeira entrega vale"
                                   % str(outro.get("machine") or "?")[:60])
                if not _tomar_lock(ep):
                    return False, (u"outra maquina tomou a entrega desta "
                                   u"serie no mesmo instante")
                wlog("serie ...%s: a entrega de `%s` parou no meio ha %.0f min"
                     " — esta maquina assume e grava por cima"
                     % (uid[-8:], str(outro.get("machine") or "?")[:60],
                        (time.time() - hb) / 60.0))
        return False, u"nao consegui reservar a entrega"
    except Exception as e:
        return False, u"nao consegui reservar a entrega (%s)" % type(e).__name__


def renovar_entrega(sdir, uid):
    with _ESCRITA_DO_LOCK:
        try:
            d = read_marker(sdir, uid, ENTREGA)
            if not isinstance(d, dict) or d.get("token") != _token():
                return False
            d["heartbeat"] = time.time()
            _regravar_sem_criar(m_path(sdir, uid, ENTREGA), d)
            return True
        except Exception:
            return False


def soltar_entrega(sdir, uid):
    with _ESCRITA_DO_LOCK:
        try:
            d = read_marker(sdir, uid, ENTREGA)
            if isinstance(d, dict) and d.get("token") != _token():
                return
            m_path(sdir, uid, ENTREGA).unlink()
        except FileNotFoundError:
            pass
        except Exception as e:
            wlog("nao consegui tirar a reserva de entrega da serie ...%s (%s)"
                 % (uid[-8:], type(e).__name__))


MARCA_DO_DONE_AFASTADO = ".done.json.substituido."


def resolver_done_afastado(sdir, uid):
    try:
        if not uid_ok(uid):
            return ""
        d = marker_dir(sdir)
        prefixo = "%s%s" % (uid, MARCA_DO_DONE_AFASTADO)
        try:
            nomes = [n for n in os.listdir(str(d)) if n.startswith(prefixo)]
        except OSError:
            return ""
        if not nomes:
            return ""
        estado, _dado = _diagnostico_do_lock(sdir, uid)
        if estado == "trabalhando":
            return ""

        def _idade(p):
            try:
                return p.stat().st_mtime
            except OSError:
                return 0.0
        rastros = sorted((Path(str(d)) / n for n in nomes), key=_idade,
                         reverse=True)
        u8 = uid[-8:]
        if has_marker(sdir, uid, "done"):
            for p in rastros:
                try:
                    p.unlink()
                except FileNotFoundError:
                    pass
            wlog("serie ...%s: o rastro do marcador de conclusao afastado por "
                 "um «Substituir» que ja tinha gravado o marcador novo foi "
                 "apagado" % u8)
            return "apagado"
        novo = rastros[0]
        if has_marker(sdir, uid, "done"):
            for p in rastros:
                try:
                    p.unlink()
                except FileNotFoundError:
                    pass
            return "apagado"
        os.replace(str(novo), str(m_path(sdir, uid, "done")))
        for p in rastros[1:]:
            try:
                p.unlink()
            except FileNotFoundError:
                pass
        wlog("serie ...%s: a substituicao anterior foi interrompida no meio "
             "(queda durante a gravacao) -- o marcador de conclusao anterior "
             "VOLTOU, e a serie fica como estava antes do pedido. Confira a "
             "pasta: a execucao pode ter publicado parte dos arquivos novos "
             "antes de cair. Para refaze-la, peca de novo com «Substituir»."
             % u8)
        return "devolvido"
    except Exception as e:
        try:
            wlog("serie ...%s: nao consegui resolver o rastro do marcador de "
                 "conclusao afastado (%s)" % (str(uid or "")[-8:],
                                              type(e).__name__))
        except Exception:
            pass
        return ""


def custo_da_noite_em_bases(modalidade="CT"):
    tasks = [t for t in (TASKS or ("total_v3",)) if t]
    try:
        import radai_tasks as _rt
        import radai_topography as _tp
        fica = list(tasks[:1])
        regiao = sorted(t for t in _tp.tasks_governadas(modalidade)
                        if t not in fica)
        piso = sum(_rt.peso_em_bases(t) for t in fica) or 1.0
        teto = piso + sum(_rt.peso_em_bases(t) for t in regiao)
        return {"piso": piso, "teto": teto, "n_teto": len(fica) + len(regiao),
                "tasks_do_config": fica, "tasks_da_regiao": regiao}
    except Exception:
        n = float(len(tasks) or 1)
        return {"piso": n, "teto": n, "n_teto": int(n),
                "tasks_do_config": tasks, "tasks_da_regiao": []}


def plano_de_execucao(limite_exames=200):
    import radai_sets
    fora = {"root": ROOT, "erro": "", "exames": [], "conjuntos": [],
            "resumo": {"a_fazer": 0, "prontos": 0, "rodando": 0,
                       "pulados": 0, "falhados": 0, "em_transito": 0}}
    _liga_conj = {
        "oar": True,
        "full": True,
        "ts": False,
        "nv": False,
        "cads": False,
        "mse": False,
        "hnl": False,
    }
    _chave_conj = {}
    _comparacao = u"so por pedido da serie, no PERSONALIZADO do Rodar agora"
    _decide_conj = {
        "oar": u"sempre", "full": u"sempre",
        "ts": _comparacao, "nv": _comparacao, "cads": _comparacao,
        "mse": _comparacao,
        "hnl": (u"os niveis entram no FULL quando o pescoco aparece (C2, C3 "
                u"e C4); o arquivo proprio deles so sai no PERSONALIZADO do "
                u"Rodar agora"),
    }
    fora["conjuntos"] = [
        {"cod": c["cod"], "nome": c["nome"], "rotulo": c["rotulo"],
         "rotulo_curto": c["rotulo_curto"], "entregue": c["entregue"],
         "ajuda": c["ajuda"],
         "marcado": _liga_conj.get(c["cod"], True),
         "chave": _chave_conj.get(c["cod"], ""),
         "decide": _decide_conj.get(c["cod"], u"")}
        for c in radai_sets.CONJUNTOS]
    if not ROOT:
        fora["erro"] = ("O ROOT esta vazio: o vigia nao varre nada. Configure a "
                        "pasta dos exames no passo 1.")
        return fora
    try:
        series, _done = scan_root()
    except Exception as e:
        fora["erro"] = "nao consegui varrer %s: %s" % (ROOT, str(e)[:200])
        return fora

    _chave_do_exame = _chave_do_exame_da_fila()
    por_exame = {}
    for uid, sr in series.items():
        por_exame.setdefault(_chave_do_exame(sr), []).append(dict(sr, uid=uid))

    escolhidas_sim = escolher_com_decisao(series)

    grupos = sorted(((_pasta_comum(por_exame[k]), k) for k in por_exame))
    for pasta, _k in grupos[:int(limite_exames)]:
        itens = por_exame[_k]
        itens.sort(key=lambda x: (-int(x.get("count", 0)), str(x.get("uid", ""))))
        do_exame = [x["uid"] for x in itens if x["uid"] in escolhidas_sim]
        _motivos = [escolhidas_sim[u] for u in do_exame]
        motivo_do_exame = next(
            (m for m in _motivos if m != MOTIVO_DO_OPERADOR),
            u"voce marcou outra serie deste exame para contornar"
            if _motivos else
            u"nenhuma serie deste exame esta escolhida: a triagem nao "
            u"escolheu nenhuma (abaixo de 1 mm, de corpo inteiro ou nao "
            u"axial), ou voce descartou a que ela escolheu")
        linhas = []
        for it in itens:
            uid = it["uid"]
            estado, detalhe = "a_fazer", ""
            _sem_rs = (marcador_sem_rtstruct(it["dir"], uid)
                       or marcador_sem_rtstruct_afastado(it["dir"], uid))
            if _sem_rs:
                detalhe = FRASE_DO_MARCADOR_SEM_RTSTRUCT
            if has_marker(it["dir"], uid, "done") and not _sem_rs:
                d = read_marker(it["dir"], uid, "done") or {}
                estado = "pronto"
                detalhe = str(d.get("finished") or d.get("quando")
                              or d.get("when") or "")[:16]
                if str(d.get("modo") or "") == "fast":
                    detalhe = (detalhe + " · " if detalhe else "") + "FAST"
                _outra = marcador_de_outra_estacao(it["dir"], uid)
                if _outra:
                    detalhe = ((detalhe + " · " if detalhe else "")
                               + FRASE_DO_MARCADOR_DE_OUTRA_ESTACAO % _outra)
            else:
                lk = read_marker(it["dir"], uid, "lock")
                if lk and (time.time() - float(lk.get("heartbeat", 0))) < LOCK_MAX_S:
                    estado = "rodando"
                    quem = str(lk.get("machine") or lk.get("maquina") or "?")
                    if lk.get("pid_os"):
                        quem += " (pid %s)" % lk["pid_os"]
                    detalhe = quem
                else:
                    fl = read_marker(it["dir"], uid, "fail")
                    _ate_adiada, _classe_adiada = adiamento_de(fl)
                    if fl and fl.get("tries", 0) >= MAX_RETRIES:
                        estado = "falhado"
                        detalhe = str(fl.get("last_error", ""))[:160]
                    elif _ate_adiada and uid in escolhidas_sim:
                        detalhe = ("adiada nesta maquina (%s, nao contou "
                                   "tentativa): volta depois de %s"
                                   % (_classe_adiada,
                                      datetime.fromtimestamp(_ate_adiada)
                                      .strftime("%d/%m %H:%M")))
                    elif uid not in escolhidas_sim:
                        estado = "pulado"
                        esp_dela = espessura_varrida(it)
                        if ler_decisao(it.get("dir") or pasta, uid) == "pular":
                            detalhe = ("%.2f mm: voce descartou esta serie "
                                       "(a decisao manual manda na escada)"
                                       % esp_dela)
                        else:
                            detalhe = (
                                "%.2f mm: nao e a TC de simulacao deste "
                                "exame. %s" % (esp_dela, motivo_do_exame))
                    elif QUIET_S > 0 and (time.time() - float(
                            it.get("mais_novo", 0) or 0)) < QUIET_S:
                        estado = "em_transito"
                        _falta = int(QUIET_S - (time.time() - float(
                            it.get("mais_novo", 0) or 0)))
                        detalhe = ("ainda chegando no servidor; entra na "
                                   "fila em ~%d min" % max(1, _falta // 60))
            fora["resumo"][{"a_fazer": "a_fazer", "pronto": "prontos",
                            "rodando": "rodando", "pulado": "pulados",
                            "em_transito": "em_transito",
                            "falhado": "falhados"}[estado]] += 1
            linhas.append({
                "uid": uid, "curto": uid[-12:], "cortes": int(it.get("count", 0)),
                "espessura_mm": it.get("espessura_mm"),
                "desc": str(it.get("desc", ""))[:60],
                "modality": it.get("modality", ""),
                "estado": estado, "detalhe": detalhe,
                "escolhida": (uid in escolhidas_sim and estado == "a_fazer"),
                "decisao": ler_decisao(it.get("dir") or pasta, uid),
                "topo": _topo_da_linha(it, pasta, uid),
            })
        fora["exames"].append({
            "pasta": rel_root(pasta),
            "pid": (itens[0].get("pid", "") if itens else ""),
            "date": (itens[0].get("date", "") or "")[:8],
            "series": linhas,
        })

    try:
        import radai_review
        a_fazer = int(fora["resumo"].get("a_fazer") or 0)
        try:
            import engine as _m
            _dev = _m._resolve_device(CFG.get("DEVICE", "auto"))
        except Exception:
            _dev = str(CFG.get("DEVICE", "auto"))
        fora["device"] = _dev
        _custo = custo_da_noite_em_bases()
        fora["estacao"] = radai_review._estacao(
            device=_dev, n_series=a_fazer or 1,
            n_tasks=_custo["n_teto"])
        _mins_p, _txt_p = radai_review.estimativa(
            a_fazer, _custo["piso"], _dev)
        _mins, _txt = radai_review.estimativa(
            a_fazer, _custo["teto"], _dev)
        fora["estimativa_min"] = _mins
        fora["estimativa_piso_min"] = _mins_p
        _sem_faixa = (_txt == _txt_p or _mins is None or _mins_p is None)
        fora["estimativa_regiao"] = ([] if _sem_faixa
                                     else list(_custo["tasks_da_regiao"]))
        fora["estimativa"] = (_txt if _sem_faixa
                              else u"%s – %s" % (_txt_p, _txt))
        fora["aviso"] = radai_review.montar([], origem="vigia")["aviso"]
    except Exception as e:
        fora["estacao"] = {"erro": "%s: %s" % (type(e).__name__, str(e)[:120])}
    return fora


DECISOES = ("incluir", "pular")


def ler_decisao(sdir, uid):
    m = read_marker(sdir, uid, "fila") or {}
    d = str(m.get("decisao") or "")
    return d if d in DECISOES else ""


def _sugestao_de_topo(it, pasta):
    try:
        import radai_topography as _tp
        return _tp.detectar(rel_root(pasta), it.get("desc"),
                            it.get("estudo"), it.get("dir"))
    except Exception:
        return ["total"], u""


def _topo_da_linha(it, pasta, uid):
    try:
        return ler_topografia(it.get("dir") or pasta, uid, None)
    except Exception:
        return ["total"]


def ler_topografia(sdir, uid, sugestao=None):
    import radai_topography as _tp
    m = read_marker(sdir, uid, "fila") or {}
    v = m.get("topo")
    if isinstance(v, (list, tuple)) and v:
        return list(_tp._lista(v))
    return list(_tp._lista(sugestao))


def gravar_topografia(sdir, uid, protocolos, quem=""):
    import radai_topography as _tp
    try:
        m = read_marker(sdir, uid, "fila") or {}
        m["topo"] = list(_tp._lista(protocolos))
        m["quem"] = quem or MACHINE
        m["quando"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        lp = m_path(sdir, uid, "fila", criar=True)
        lp.write_text(json.dumps(m), encoding="utf-8")
        return {"ok": True, "topo": m["topo"]}
    except Exception as e:
        return {"ok": False, "erro": str(e)[:200]}


def gravar_decisao(sdir, uid, decisao, quem=""):
    decisao = str(decisao or "")
    if decisao and decisao not in DECISOES:
        return {"ok": False, "erro": "decisao invalida: %r" % decisao[:20]}
    try:
        p = m_path(sdir, uid, "fila", criar=bool(decisao))
        if not decisao:
            try:
                p.unlink()
            except FileNotFoundError:
                pass
            return {"ok": True, "decisao": ""}
        p.write_text(json.dumps({
            "decisao": decisao, "quem": quem or MACHINE,
            "quando": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "ver": APPVER}, ensure_ascii=False), encoding="utf-8")
        return {"ok": True, "decisao": decisao}
    except Exception as e:
        return {"ok": False, "erro": "%s: %s" % (type(e).__name__, e)}


MOTIVO_DO_OPERADOR = u"escolhida por você"


def _chave_do_exame_da_fila():
    try:
        import radai_triage
        return radai_triage._chave_do_exame
    except Exception:
        return lambda sr: str((sr or {}).get("dir") or "")


def _pasta_comum(itens):
    dirs = [str(x.get("dir") or "") for x in (itens or ()) if x.get("dir")]
    if not dirs:
        return ""
    try:
        return os.path.commonpath(dirs)
    except Exception:
        return sorted(dirs)[0]


def escolher_com_decisao(series):
    escada = escolher_simulacao(series)
    fora, manuais = {}, 0
    for uid, s in series.items():
        d = ler_decisao(s["dir"], uid)
        if d:
            manuais += 1
        if d == "pular":
            continue
        if d == "incluir":
            fora[uid] = MOTIVO_DO_OPERADOR
            continue
        if uid in escada:
            fora[uid] = escada[uid]
    STATE["fila_manual"] = manuais
    return fora


CONJUNTOS_DE_PROVA = (("oar", "full"), ("fast",))


def conjuntos_no_disco(pasta, uid):
    curto = str(uid or "")[-8:]
    if not curto:
        return set()
    try:
        nomes = os.listdir(str(pasta))
    except Exception:
        return set()
    try:
        import radai_sets
    except Exception:
        return set()
    achados = set()
    for n in radai_sets.arquivos_da_serie(nomes, uid):
        c = radai_sets.do_arquivo(n)
        if c and c.get("cod"):
            achados.add(c["cod"])
    return achados


def forma_da_prova(achados):
    achados = set(achados or ())
    for forma in CONJUNTOS_DE_PROVA:
        if all(c in achados for c in forma):
            return tuple(forma)
    return None


def entrega_completa_no_disco(pasta, uid):
    return forma_da_prova(conjuntos_no_disco(pasta, uid)) is not None


MARCADOR_SEM_RTSTRUCT = "done_sem_rtstruct"
FRASE_DO_MARCADOR_SEM_RTSTRUCT = u"marcador sem RTSTRUCT: refazendo"
MARCADORES_SEM_RTSTRUCT = {}
_PRONTAS_COM_ARQUIVO = set()
FRASE_DO_MARCADOR_DE_OUTRA_ESTACAO = (
    u"feita por %s, que grava o RTSTRUCT no destino dela: esta estacao nao o "
    u"ve e nao refaz")
_PRONTAS_DE_OUTRA_ESTACAO = {}


def _rtstruct_da_serie_em(pasta, uid, ausente_e_vazio=False):
    try:
        nomes = os.listdir(str(pasta))
    except FileNotFoundError:
        if not ausente_e_vazio:
            return None
        nomes = []
    except OSError:
        return None
    import radai_sets
    return bool(radai_sets.arquivos_da_serie(nomes, uid))


def _situacao_do_marcador(sdir, uid):
    if not has_marker(sdir, uid, "done"):
        return None
    chave = (str(sdir), str(uid))
    if chave in _PRONTAS_COM_ARQUIVO:
        return None
    if chave in _PRONTAS_DE_OUTRA_ESTACAO:
        return ("outra_estacao", _PRONTAS_DE_OUTRA_ESTACAO[chave])
    d = read_marker(sdir, uid, "done")
    if not isinstance(d, dict) or d.get("dry_run"):
        return None
    # GUARDA: pasta que nao se lista (share fora, acesso negado) nao e ausencia.
    na_serie = _rtstruct_da_serie_em(sdir, uid)
    if na_serie is None:
        return None
    if na_serie:
        _PRONTAS_COM_ARQUIVO.add(chave)
        return None
    destino = _destino({"dir": sdir})
    ao_lado = (os.path.normcase(os.path.abspath(str(destino)))
               == os.path.normcase(os.path.abspath(str(sdir))))
    if not ao_lado:
        no_destino = _rtstruct_da_serie_em(
            destino, uid,
            ausente_e_vazio=bool(OUT_DIR and os.path.isdir(OUT_DIR)))
        if no_destino is None:
            return None
        if no_destino:
            _PRONTAS_COM_ARQUIVO.add(chave)
            return None
        quem = str(d.get("machine") or u"").strip()
        # GUARDA: com destino proprio, o RTSTRUCT de outra estacao foi para o destino DELA, que daqui nao se ve.
        if quem != MACHINE:
            _PRONTAS_DE_OUTRA_ESTACAO[chave] = quem[:60] or u"?"
            return ("outra_estacao", _PRONTAS_DE_OUTRA_ESTACAO[chave])
    return ("sem_rtstruct", None)


def marcador_sem_rtstruct(sdir, uid):
    try:
        sit = _situacao_do_marcador(sdir, uid)
        return bool(sit and sit[0] == "sem_rtstruct")
    except Exception:
        return False


def marcador_de_outra_estacao(sdir, uid):
    try:
        sit = _situacao_do_marcador(sdir, uid)
        return sit[1] if (sit and sit[0] == "outra_estacao") else u""
    except Exception:
        return u""


def marcador_sem_rtstruct_afastado(sdir, uid):
    try:
        return (has_marker(sdir, uid, MARCADOR_SEM_RTSTRUCT)
                and not has_marker(sdir, uid, "done"))
    except Exception:
        return False


def afastar_marcador_sem_rtstruct(sdir, uid):
    if not marcador_sem_rtstruct(sdir, uid):
        return False
    try:
        os.replace(str(m_path(sdir, uid, "done")),
                   str(m_path(sdir, uid, MARCADOR_SEM_RTSTRUCT, criar=True)))
    except Exception as e:
        wlog("serie ...%s: o marcador de pronta nao tem RTSTRUCT no disco, e "
             "nao consegui afasta-lo (%s): ela continua como pronta"
             % (str(uid)[-8:], type(e).__name__))
        return False
    MARCADORES_SEM_RTSTRUCT[uid] = FRASE_DO_MARCADOR_SEM_RTSTRUCT
    wlog("serie ...%s: o marcador de pronta (ou parcial) nao tem nenhum "
         "RTSTRUCT RadAI da serie no disco, e nao vale como pronta: foi "
         "afastado (marcador %s) e a serie volta para a fila do vigia"
         % (str(uid)[-8:], MARCADOR_SEM_RTSTRUCT))
    return True


def _tirar_o_marcador_sem_rtstruct(sdir, uid):
    MARCADORES_SEM_RTSTRUCT.pop(uid, None)
    try:
        m_path(sdir, uid, MARCADOR_SEM_RTSTRUCT).unlink()
    except Exception:
        pass


def readotar_entrega(s):
    try:
        pasta = _destino(s)
        uid = s["uid"]
        achados = conjuntos_no_disco(pasta, uid)
        forma = forma_da_prova(achados)
        if forma is None:
            return False
        agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        done = {"uid": uid, "date": s.get("date", ""), "pid": s.get("pid", ""),
                "machine": MACHINE, "finished": agora, "secs": 0,
                "rs": "", "tasks": TASKS, "tasks_ok": [],
                "cortes": s.get("count", 0), "structures": [],
                "ver": APPVER, "dry_run": False,
                "origem": "readotado",
                "adotado_em": agora,
                "modo": "fast" if forma == ("fast",) else "",
                "conjuntos_no_disco": sorted(achados)}
        m_path(s["dir"], uid, "done", criar=True).write_text(
            json.dumps(done, ensure_ascii=False), encoding="utf-8")
        wlog("serie ...%s ja tinha a entrega completa na pasta (%s) e nao "
             "tinha marcador — adotada como concluida, sem reprocessar. Para "
             "refaze-la, apague os RS_RadAI_*.dcm da pasta."
             % (uid[-8:], u"so o OAR_Fast: feita no modo FAST"
                if forma == ("fast",) else u"OAR e FULL"))
        return True
    except Exception as e:
        wlog("nao consegui conferir a entrega ja gravada da serie ...%s (%s) "
             "— ela segue para a fila" % (str(s.get("uid", ""))[-8:], str(e)[:120]))
        return False


def _assinatura_do_fail(fl):
    return str((fl or {}).get("em_espera") or (fl or {}).get("assinatura")
               or u"")


def _assinaturas_em_espera():
    with LOCK:
        return set(a for a, r in (STATE.get("assinaturas") or {}).items()
                   if r.get("em_espera"))


def _fora_da_fila_pela_falha(s, fl):
    if not fl:
        return None
    if fl.get(INELEGIVEL):
        try:
            mesma = int(fl.get("cortes") or -1) == int(s.get("count") or -2)
        except (TypeError, ValueError):
            mesma = True
        if mesma:
            return "nao_contornavel"
    if str(fl.get("versao_do_app") or APPVER) == APPVER:
        if fl.get("em_espera"):
            return "em_espera"
        if (fl.get("assinatura") and fl.get("ultimo_tipo") in (
                DETERMINISTICO, INDETERMINADA)
                and fl["assinatura"] in _assinaturas_em_espera()):
            return "em_espera"
    if (fl.get("ultimo_tipo") == INDETERMINADA
            and fl.get("turno") == STATE.get("turno_id")):
        return "proximo_turno"
    return None


_TURNOS_ABERTOS = [0]


def abrir_turno_das_assinaturas():
    with LOCK:
        # GUARDA: dois turnos no mesmo segundo teriam o mesmo id, e a falha
        # indeterminada do turno velho nao voltaria no novo.
        _TURNOS_ABERTOS[0] += 1
        STATE["turno_id"] = "%s.%d" % (datetime.now().strftime("%Y%m%d%H%M%S"),
                                       _TURNOS_ABERTOS[0])
        STATE["assinaturas"] = {}
        STATE["alertas_de_assinatura"] = []


def registrar_assinatura(assinatura, classe, s, frase):
    curto = str(s.get("uid") or u"")[-8:]
    with LOCK:
        tab = STATE.setdefault("assinaturas", {})
        r = tab.setdefault(assinatura, {
            "series": [], "itens": [], "primeira": datetime.now().strftime(
                "%d/%m %H:%M"), "primeira_serie": curto, "classe": classe,
            "frase": frase, "em_espera": False, "notificada": False})
        ja_estava = bool(r.get("em_espera"))
        if curto not in r["series"]:
            r["series"].append(curto)
            r["itens"].append((str(s.get("dir") or u""),
                               str(s.get("uid") or u"")))
        entrou = False
        if (not ja_estava and classe in (DETERMINISTICO, INDETERMINADA)
                and len(r["series"]) >= REPETICOES_DA_ASSINATURA):
            r["em_espera"] = True
            entrou = True
            STATE["alertas_de_assinatura"] = [
                a for a in STATE.get("alertas_de_assinatura") or []
                if a.get("assinatura") != assinatura] + [{
                    "assinatura": assinatura, "classe": classe,
                    "frase": frase, "series": len(r["series"]),
                    "primeira": r["primeira"]}]
        notificada = bool(r.get("notificada"))
        r["notificada"] = True
        return {"n": len(r["series"]), "em_espera": bool(r["em_espera"]),
                "ja_estava": ja_estava, "entrou": entrou,
                "primeira": r.get("primeira_serie") or curto,
                "notificada": notificada, "itens": list(r["itens"])}


def _por_em_espera(itens, assinatura):
    for d, uid in itens or ():
        try:
            fl = read_marker(d, uid, "fail")
            if not fl or fl.get("em_espera"):
                continue
            fl["em_espera"] = assinatura
            fl.setdefault("versao_do_app", APPVER)
            m_path(d, uid, "fail", criar=True).write_text(
                json.dumps(fl, ensure_ascii=False), encoding="utf-8")
        except Exception:
            continue


def _mesma_falha(reg, assinatura):
    wlog("   mesma falha da serie ...%s, assinatura %s (o traceback e a "
         "notificacao sairam na primeira)" % (reg.get("primeira") or u"?",
                                              assinatura))


def _recusar_serie(s, e, limpo, assinatura, repetida):
    sdir, uid = s["dir"], s["uid"]
    curto = uid[-8:]
    motivo = limpar_erro(getattr(e, "motivo", None) or limpo) or limpo
    motivo = _falhas.sem_caminho_nem_uid(motivo)
    fl = read_marker(sdir, uid, "fail") or {"tries": 0}
    fl.update({INELEGIVEL: motivo[:300], "assinatura": assinatura,
               "cortes": s.get("count"), "versao_do_app": APPVER,
               "last_error": motivo[:500], "machine": MACHINE,
               "when": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
               "ultimo_tipo": INELEGIVEL})
    fl.setdefault("tries", 0)
    try:
        m_path(sdir, uid, "fail", criar=True).write_text(
            json.dumps(fl, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass
    with LOCK:
        STATE["fails"] = ([{"uid": curto, "err": u"nao contornavel: %s"
                            % motivo[:120]}] + STATE["fails"])[:20]
    wlog("RECUSADA serie ...%s: %s — nao gasta tentativa e nao volta a fila "
         "(assinatura %s)" % (curto, motivo[:300], assinatura))
    if not repetida:
        notificar("titulo_erro", "recusada", curto)
    return False


def build_queue(series, done_dates):
    pendentes = []
    adiadas_agora, voltaram = 0, []
    volta_das_adiadas = None
    del PULADAS_POR_FALHA[:]
    del NAO_CONTORNAVEIS[:]
    del EM_ESPERA[:]
    escolhidas = escolher_com_decisao(series)
    STATE["nao_simulacao"] = len(series) - len(escolhidas)
    for uid, s in series.items():
        if str(s["dir"]) in SEM_PERMISSAO:
            continue
        if uid not in escolhidas:
            continue
        s["porque"] = escolhidas[uid]
        afastar_marcador_sem_rtstruct(s["dir"], uid)
        if has_marker(s["dir"], uid, "done"):
            continue
        if marcador_sem_rtstruct_afastado(s["dir"], uid):
            MARCADORES_SEM_RTSTRUCT[uid] = FRASE_DO_MARCADOR_SEM_RTSTRUCT
        if readotar_entrega(s):
            continue
        fl = read_marker(s["dir"], uid, "fail")
        _fora = _fora_da_fila_pela_falha(s, fl)
        if _fora == "nao_contornavel":
            NAO_CONTORNAVEIS.append({"dir": str(s["dir"]), "uid": uid,
                                     "pid": s.get("pid", ""),
                                     "motivo": str(fl.get("inelegivel"))[:200]})
            continue
        if _fora == "em_espera":
            EM_ESPERA.append({"dir": str(s["dir"]), "uid": uid,
                              "pid": s.get("pid", ""),
                              "assinatura": _assinatura_do_fail(fl),
                              "frase": str(fl.get("last_error") or "")[:300]})
            continue
        if _fora == "proximo_turno":
            adiadas_agora += 1
            continue
        if fl and fl.get("tries", 0) >= MAX_RETRIES:
            PULADAS_POR_FALHA.append({"dir": str(s["dir"]), "uid": uid,
                                      "pid": s.get("pid", ""),
                                      "erro": str(fl.get("last_error", ""))[:200]})
            continue
        if fl:
            _ate, _pq = adiamento_de(fl)
            if _ate:
                adiadas_agora += 1
                try:
                    volta_das_adiadas = (float(_ate) if volta_das_adiadas is None
                                         else min(volta_das_adiadas,
                                                  float(_ate)))
                except (TypeError, ValueError):
                    pass
                continue
            if ja_foi_adiada(fl) or int(fl.get("tries", 0) or 0) >= 1:
                voltaram.append(uid)
        pendentes.append(s)

    STATE["adiadas"] = adiadas_agora
    _volta_antes = STATE.get("volta_das_adiadas")
    STATE["volta_das_adiadas"] = volta_das_adiadas
    if (volta_das_adiadas and adiadas_agora
            and volta_das_adiadas != _volta_antes
            and volta_das_adiadas - time.time() <= HORIZONTE_DAS_ADIADAS_S):
        wlog("energia: ha %d serie(s) adiada(s) nesta maquina — a estacao "
             "fica acordada ate %s, quando a primeira volta para a fila"
             % (adiadas_agora, datetime.fromtimestamp(
                 volta_das_adiadas).strftime("%d/%m %H:%M")))
    STATE["nao_contornaveis"] = len(NAO_CONTORNAVEIS)
    STATE["em_espera"] = len(EM_ESPERA)

    if QUIET_S > 0:
        agora = time.time()
        prontas = [s for s in pendentes if (agora - s.get("mais_novo", 0)) >= QUIET_S]
        STATE["em_transito"] = len(pendentes) - len(prontas)
        pendentes = prontas
    else:
        STATE["em_transito"] = 0

    ordem = _ordem_da_fila(pendentes, done_dates)
    if voltaram:
        _depois = set(voltaram)
        return ([s for s in ordem if s["uid"] not in _depois]
                + [s for s in ordem if s["uid"] in _depois])
    return ordem


def _ordem_da_fila(pendentes, done_dates):

    if STATE.get("overnight"):
        return sorted(pendentes, key=lambda x: x["date"], reverse=True)
    if done_dates:
        ultima = max(done_dates)
        novas = sorted([s for s in pendentes if (s["date"] or "") > ultima],
                       key=lambda x: x["date"])
        resto = sorted([s for s in pendentes if (s["date"] or "") <= ultima],
                       key=lambda x: x["date"], reverse=True)
        return novas + resto
    return sorted(pendentes, key=lambda x: x["date"], reverse=True)


def carregar_engine():
    global _ENGINE, _ENGINE_ERRO
    if _ENGINE is not None:
        return _ENGINE
    try:
        import engine
        _ENGINE = engine
        _ENGINE_ERRO = ""
        return _ENGINE
    except Exception as e:
        _ENGINE_ERRO = "%s: %s" % (type(e).__name__, e)
        raise RuntimeError("engine.py nao carregou (%s). Rode o vigia com o python "
                           "do bundle, ou use DRY_RUN=1 para testar so o encanamento."
                           % _ENGINE_ERRO)


def series_files(s):
    uid = s["uid"]
    achados, erros = [], 0
    for sdir in (s.get("dirs") or {s["dir"]: 0}):
        try:
            nomes = os.listdir(sdir)
        except Exception as e:
            raise RuntimeError("nao consegui listar %s (%s)" % (rel_root(sdir), e))
        for fn in nomes:
            fp = os.path.join(sdir, fn)
            try:
                if not os.path.isfile(fp) or not is_dicom(fp):
                    continue
                ds = pydicom.dcmread(fp, stop_before_pixels=True, force=True,
                                     specific_tags=["SeriesInstanceUID"])
                if str(getattr(ds, "SeriesInstanceUID", "")) == uid:
                    achados.append(fp)
            except Exception:
                erros += 1
    if erros:
        raise RuntimeError("%d arquivo(s) da serie ilegiveis (rede instavel?) — "
                           "nao vou segmentar uma serie incompleta" % erros)
    return achados


def _copiar_atomico(origem, destino):
    import radai_sets
    destino = Path(destino)
    parcial = radai_sets.nome_parcial(str(destino))
    try:
        shutil.copy2(str(origem), parcial)
        os.replace(parcial, str(destino))
    finally:
        try:
            if os.path.exists(parcial):
                os.remove(parcial)
        except Exception:
            pass
    return destino


def _drenar_log_motor(engine, jid, parar, coletor=None):
    _falar_pela_serie(coletor)
    engine.drenar_log(jid, lambda ln: wlog("   " + ln), parar)


def marcar_etapa(texto, passo=0, total=0):
    with LOCK:
        atual = STATE.get("current")
        if atual:
            atual["etapa"] = texto
            atual["passo"] = int(passo)
            atual["total"] = int(total)
            atual["etapa_desde"] = time.time()
    _cronometrar(texto)
    _no_log_da_serie(u"etapa %s: %s" % (
        (u"%d de %d" % (int(passo), int(total))) if total else u"-", texto))
    c = _CASO_DA_SERIE[0]
    if c is not None:
        c.etapa(texto)


_CRONOMETRO_DA_SERIE = [None]


def _abrir_cronometro():
    try:
        import radai_etapas
        _CRONOMETRO_DA_SERIE[0] = radai_etapas.Cronometro()
        _CRONOMETRO_DA_SERIE[0].etapa(u"preparo")
    except Exception:
        _CRONOMETRO_DA_SERIE[0] = None


def _cronometrar(texto):
    c = _CRONOMETRO_DA_SERIE[0]
    if c is None:
        return
    try:
        import radai_etapas
        fechada = c.etapa(texto)
        if fechada:
            wlog(radai_etapas.linha(fechada))
    except Exception:
        pass


def _fechar_cronometro():
    c, _CRONOMETRO_DA_SERIE[0] = _CRONOMETRO_DA_SERIE[0], None
    if c is None:
        return
    try:
        import radai_etapas
        fechada = c.fechar()
        if fechada:
            wlog(radai_etapas.linha(fechada))
        wlog(c.resumo())
    except Exception:
        pass


class _PrimeiraEntregaValeu(Exception):
    pass


def _etapas_de_topo(info):
    import radai_output
    return radai_output.sem_os_passos((info or {}).get("etapas"))


def _etapas_do_done(info):
    import radai_records
    return radai_records.etapas_do_done(_etapas_de_topo(info))


def _estado_para_o_lock(info):
    fora = {"maquina": MACHINE}
    try:
        with LOCK:
            atual = dict(STATE.get("current") or {})
        _etapas = _etapas_de_topo(info)
        fora["etapa"] = (atual.get("etapa") or info.get("task_em_curso")
                         or (_etapas[-1].get("etapa") if _etapas else "")
                         or "")
        fora["passo"] = int(atual.get("passo")
                            or len(info.get("tasks_ok") or []))
        fora["total"] = int(atual.get("total")
                            or len(info.get("tarefas") or []))
        fora["dispositivo"] = str(info.get("dispositivo") or "")
        fora["feito"] = [
            {"task": str(e.get("task") or e.get("etapa") or ""),
             "dispositivo": str(e.get("dispositivo") or ""),
             "segundos": int(e.get("segundos") or 0)}
            for e in _etapas]
        if info.get("gravados"):
            fora["gravados"] = list(info["gravados"])
        fora["atualizado"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        pass
    return fora


MODO_DO_VIGIA = "auto"


def process_series(s):
    CANCELAR_VIGIA.clear()
    ULTIMO_DESFECHO.clear()
    uid, sdir = s["uid"], s["dir"]
    curto = uid[-8:]
    t0 = time.time()
    stage = None
    _tmp_serie = None
    hb = None
    coletor = None
    parar_hb = threading.Event()
    info = {"ok": False, "erro": "", "ambiente": False,
            "modalidade": str(s.get("modality") or "").upper(),
            "tasks_pedidas": list(TASKS), "tarefas": [], "tasks_ok": [],
            "task_em_curso": "", "etapas": [], "log_motor": [],
            "plano": None, "plano_origem": "", "partes": None,
            "dispositivo": "", "medidas": {}, "estruturas": None}

    def bater_heartbeat():
        _falar_pela_serie(coletor)
        falhas = 0
        while not parar_hb.is_set():
            try:
                salvar_status()
            except Exception:
                pass
            if info.get("entrega_reservada"):
                renovar_entrega(sdir, uid)
            if renovar_lock(sdir, uid, extra=_estado_para_o_lock(info)):
                if falhas >= 2:
                    wlog("   o sinal de vida da serie ...%s voltou a ser "
                         "gravado (falhou %d vez(es) seguidas)"
                         % (uid[-8:], falhas))
                falhas = 0
            else:
                falhas += 1
                if falhas == 2:
                    wlog("   NAO consigo gravar o sinal de vida da serie "
                         "...%s ha %.0f min. Se passar de %.0f min, outra "
                         "maquina pode assumir esta serie e o trabalho sai "
                         "dobrado. Confira o acesso de escrita a pasta _RadAI."
                         % (uid[-8:], falhas * HEARTBEAT_S / 60.0,
                            LOCK_PARADO_S / 60.0))
            parar_hb.wait(HEARTBEAT_S)

    # GUARDA: tudo o que pode levantar depois do claim fica dentro do try; so o finally solta a trava.
    try:
        _tmp_serie = _arq.TemporariaDaSerie()
        _esvaziar_cofres()
        coletor = _abrir_coletor()
        _abrir_log_da_serie(s)
        _abrir_caso_em_andamento(s)
        _abrir_cronometro()
        hb = threading.Thread(target=bater_heartbeat, daemon=True)
        hb.start()
        wlog("=== serie ...%s | %s | %d cortes | %s%s ===" %
             (curto, s.get("pid", "?"), s["count"], rel_root(sdir),
              " | SIMULACAO" if DRY_RUN else ""))
        arquivos = series_files(s)
        if len(arquivos) < s["count"]:
            raise RuntimeError("serie incompleta: achei %d dos %d cortes indexados"
                               % (len(arquivos), s["count"]))
        if len(arquivos) < MIN_SLICES:
            raise RuntimeError("so %d arquivos da serie na pasta" % len(arquivos))

        if DRY_RUN:
            time.sleep(0.2)
            estruturas = ["SIMULACAO"]
            import radai_sets as _rs_nome
            rs_name = "RS_RadAI_%s_%s.SIMULACAO.txt" % (
                _rs_nome.data_do_nome(s), curto)
            destino = _destino(s) / rs_name
            destino.parent.mkdir(parents=True, exist_ok=True)
            destino.write_text(
                "SIMULACAO (DRY_RUN=1) - nenhum RTSTRUCT foi gerado.\n"
                "serie ...%s, %d cortes, %s\n" % (curto, len(arquivos), datetime.now()),
                encoding="utf-8")
            tasks_ok = ["(simulacao)"]
        else:
            engine = carregar_engine()
            _arq.conferir_escrita_no_destino(str(_destino(s)),
                                             subir=bool(OUT_DIR))
            _tmp_serie.abrir()
            _arq.conferir_espaco_da_serie(arquivos, n_tasks=len(info.get("tasks_pedidas") or []))
            stage = Path(tempfile.mkdtemp(prefix="radai_"))
            jid = engine._job_new()
            parar_dren = threading.Event()
            drenador = threading.Thread(target=_drenar_log_motor,
                                        args=(engine, jid, parar_dren, coletor),
                                        daemon=True)
            drenador.start()
            n_etapas = len(TASKS) + 1
            try:
                marcar_etapa("copiando a série", 0, n_etapas)
                engine.copy_sorted(arquivos, str(stage))
                ref = engine.load_sitk(str(stage))
                engine.conferir_volume_contornavel(
                    ref, min_cortes=MIN_SLICES,
                    modalidade=info["modalidade"])
                info["receita_pos"] = getattr(engine, "VERSAO_DA_RECEITA_POS",
                                              u"")
                info["medidas"] = _medidas_da_imagem(ref, len(arquivos))
                dev = engine._resolve_device(CFG["DEVICE"])
                info["dispositivo"] = str(dev)
                masks, tasks_ok = {}, []
                info["tasks_ok"] = tasks_ok
                cruas = {}

                import radai_topography as _tp
                _manuais_da_fila = []
                try:
                    _proto = ler_topografia(s["dir"], s["uid"], None)
                    tarefas = list(TASKS)
                    _manuais = list(_tp.tasks_da_escolha_manual(_proto))
                    _manuais_da_fila = list(_manuais)
                    for _t in _manuais:
                        if _t not in tarefas:
                            tarefas.append(_t)
                    if _manuais:
                        wlog("topografia escolhida por voce na fila (%s): "
                             "acrescenta %s"
                             % (_tp.rotulo_de(_proto), ", ".join(_manuais)))
                    try:
                        _sug, _mot = _sugestao_de_topo(s, s.get("dir") or "")
                        if (_tp.CABECA_PESCOCO in _sug
                                and _tp.CABECA_PESCOCO not in _proto):
                            wlog("o texto do exame sugere cabeca e pescoco "
                                 "(%s) — desde a v8.2 o texto nao acrescenta "
                                 "task: quem decide e a anatomia" % _mot)
                    except Exception:
                        pass
                except _tp.AchadoPorOmissao:
                    raise
                except Exception as _e:
                    _proto = ["total"]
                    tarefas = list(TASKS)
                    wlog("nao consegui montar as tasks da topografia (%s) — "
                         "rodo a lista do config" % str(_e)[:100])
                tarefas = tasks_pela_modalidade(tarefas, info["modalidade"])
                tarefas = base_na_frente(tarefas)
                try:
                    import radai_tasks as _rt
                    _bases = tuple(_rt.BASES_CT) + tuple(_rt.BASES_MR)
                except Exception:
                    _bases = ("total_v3", "total_v2", "total_mr")

                try:
                    tarefas = _rt.lista_para_rodar(tarefas, log=wlog)
                except Exception:
                    pass
                n_etapas = len(tarefas) + 1
                puladas = _tasks_fora_do_protocolo(tarefas, ref, curto)
                if puladas:
                    tarefas = [t for t in tarefas if t not in puladas]
                    n_etapas = len(tarefas) + 1
                info["tarefas"] = list(tarefas)
                _plano_para_o_registro(engine, jid, ref, tarefas, dev, info)

                _complementos = set(_manuais_da_fila)
                _laco = {"passo": 0, "anatomia": False}
                _falhas_do_vigia = {}

                def _rodar_uma(ref_, t, dev_, jid_, **kw):
                    _laco["passo"] += 1
                    marcar_etapa(t, _laco["passo"],
                                 max(len(info["tarefas"]) + 1,
                                     _laco["passo"] + 1))
                    info["task_em_curso"] = t
                    return engine.run_ts_task(
                        ref_, t, device=dev_, jid=jid_,
                        recorte_no_corpo=bool(RECORTE_NO_CORPO), **kw)

                def _antes_de(t, masks_ate_aqui, _cruas_ate_aqui):
                    if t not in TASKS_SO_TORAX:
                        return None
                    try:
                        _tem, _pq = torax_no_campo(masks_ate_aqui,
                                                   grade=_grade_de(stage))
                    except Exception as _e:
                        _tem, _pq = True, ("nao consegui medir (%s)"
                                           % str(_e)[:80])
                    if _tem:
                        return None
                    wlog("pulando `%s`: %s" % (t, _pq))
                    return _pq

                def _ao_terminar(t, d):
                    _et = _etapa_da_task(
                        t, float(d.get("segundos") or 0), MACHINE,
                        _dispositivo_da_task(engine, jid, t, dev),
                        falhou=not d.get("ok"))
                    if d.get("retomada"):
                        _et["retomada"] = True
                    info["etapas"].append(_et)
                    if d.get("ok"):
                        info["task_em_curso"] = ""
                        if t not in tasks_ok:
                            tasks_ok.append(t)
                    renovar_lock(sdir, uid, extra=_estado_para_o_lock(info))

                def _depois_de(t, masks_ate_aqui, _cruas_ate_aqui):
                    if _laco["anatomia"] or t not in _bases:
                        return []
                    _laco["anatomia"] = True
                    _novas = _tasks_pela_anatomia(
                        engine, masks_ate_aqui, cruas, ref, info,
                        list(info["tarefas"]))
                    if _novas:
                        _complementos.update(_novas)
                        _lista = list(info["tarefas"])
                        _pos = (_lista.index(t) + 1) if t in _lista \
                            else len(_lista)
                        _lista[_pos:_pos] = [n for n in _novas
                                             if n not in _lista]
                        info["tarefas"] = _lista
                    return _novas

                def _ao_falhar(t, e):
                    if t not in _complementos or erro_de_ambiente(e):
                        return True
                    _classe_t = classificar_erro(e)
                    _fl_t = None
                    # GUARDA: so RECURSO e TRAVOU adiam; INDETERMINADA e
                    # INELEGIVEL num complemento seguem com a base, porque o
                    # `except` da serie so conta o adiamento dessas duas.
                    _adia_t = _classe_t in (RECURSO, TRAVOU)
                    if _adia_t:
                        _fl_t = read_marker(sdir, uid, "fail")
                        if complemento_ainda_adia(_fl_t, t):
                            info["complemento_adiado"] = t
                            return True
                    _motivo_t = limpar_erro(e) or type(e).__name__
                    if _adia_t:
                        _motivo_t = (
                            u"%s pela %da vez — teto de %d adiamentos do "
                            u"complemento (%s)"
                            % (u"falta de RECURSO" if _classe_t == RECURSO
                               else u"TRAVA (tempo limite)",
                               adiamentos_do_complemento(_fl_t, t) + 1,
                               TETO_ADIAMENTOS_DO_COMPLEMENTO, _motivo_t))
                    wlog("a task `%s` do complemento de regiao FALHOU nesta "
                         "serie (%s) — a serie segue: o FULL e o OAR saem "
                         "da base, sem o que ela daria"
                         % (t, _motivo_t[:200]))
                    try:
                        for _l in traceback.format_exc().strip().splitlines():
                            wlog("   " + _l)
                    except Exception:
                        pass
                    try:
                        _ass_c = _falhas.assinatura_da_falha(e, _classe_t)
                    except Exception:
                        _ass_c = ""
                    _falhas_do_vigia[t] = {"motivo": _motivo_t,
                                           "classe": _classe_t,
                                           "assinatura": _ass_c}
                    return False

                _res = engine.rodar_tasks(
                    ref, tarefas, dev, jid,
                    timeout_s=TIMEOUT_TASK_S, trava=regra_de_travamento(),
                    rodar=_rodar_uma, antes_de=_antes_de,
                    depois_de=_depois_de, ao_terminar=_ao_terminar,
                    ao_falhar=_ao_falhar, classificar=classificar_erro,
                    obrigatorias=(), modo=MODO_DO_VIGIA,
                    cruas=cruas)
                masks = dict(_res.get("masks") or {})
                tasks_ok[:] = [t for t in (_res.get("rodaram") or [])]
                info["task_em_curso"] = ""
                for _f in (_res.get("falharam") or []):
                    _t_f = str(_f.get("task") or "")
                    _dv = _falhas_do_vigia.get(_t_f) or {}
                    _motivo_t = (_dv.get("motivo") or _f.get("erro")
                                 or u"?")
                    _ass_t = _dv.get("assinatura") or ""
                    info.setdefault("tasks_falharam", []).append(
                        {"task": _t_f, "erro": _motivo_t[:300],
                         "classe": _dv.get("classe") or _f.get("classe"),
                         "assinatura": _ass_t})
                info["travamentos"] = [dict(x) for x in
                                       (_res.get("travamentos") or [])]
                info["puladas"] = [dict(x) for x in
                                   (_res.get("puladas") or [])]
                info["tasks_puladas_por_memoria"] = [
                    dict(x) for x in
                    (_res.get("tasks_puladas_por_memoria") or [])
                    if isinstance(x, dict)]
                info["recortes"] = dict(_res.get("recortes") or {})
                info["tasks_sem_estrutura"] = [
                    dict(x) for x in (_res.get("ausentes") or [])]
                for _au in info["tasks_sem_estrutura"]:
                    wlog("`%s` sem estrutura no campo nesta serie (%s) — "
                         "ausencia anatomica, nao falha"
                         % (_au.get("task"), _au.get("motivo")))
                for _tv in info["travamentos"]:
                    wlog("TRAVAMENTO na serie ...%s: `%s` (%s) — retomada "
                         "com o plano de memoria menor: %s"
                         % (curto, _tv.get("task", "?"),
                            _tv.get("motivo", "?"), _tv.get("retomada", "?")))
                n_etapas = len(info["tarefas"]) + 1
                if not masks:
                    raise RuntimeError("nenhuma estrutura gerada")

                import radai_sets as _rs_nome
                rs_name = "RS_RadAI_%s_%s.dcm" % (_rs_nome.data_do_nome(s),
                                                  curto)


                # GUARDA: os niveis nao vao ao OAR; a uniao e as parotidas do VIII
                # vao (`radai_sets.PERMITIDOS_NO_OAR`).
                _extras_da_vez = _rodar_motores_do_full(cruas, ref, info)
                if _niveis_cervicais_nesta_serie(masks, cruas, ref, info):
                    try:
                        _HNLNL_DA_VEZ["masks"] = _rodar_hnlnl(
                            str(stage), cruas, ref)
                    except Exception as e:
                        _HNLNL_DA_VEZ["masks"] = {}
                        wlog("niveis cervicais nao rodaram nesta serie (%s) — "
                             "o contorno entregue nao foi afetado" % str(e)[:140])
                        try:
                            for _l in traceback.format_exc().strip().splitlines():
                                wlog("   " + _l)
                        except Exception:
                            pass

                marcar_etapa("montando o FULL e o OAR", n_etapas, n_etapas)
                try:
                    import SimpleITK as _sitk
                    _hu_serie = _sitk.GetArrayFromImage(ref)
                except Exception:
                    _hu_serie = None
                _pode, _porque = reservar_entrega(sdir, uid)
                if not _pode:
                    raise _PrimeiraEntregaValeu(_porque)
                info["entrega_reservada"] = True
                _meu, _dono = lock_e_meu(sdir, uid)
                if not _meu:
                    wlog("serie ...%s: o lock agora e de `%s` (o sinal de vida "
                         "desta maquina falhou e ela assumiu). Ninguem "
                         "entregou ainda, e a primeira entrega vale: esta "
                         "maquina publica, e a outra descarta quando terminar."
                         % (curto, _dono))
                destino = _destino(s)
                destino.mkdir(parents=True, exist_ok=True)
                sd = _saida_de(engine, str(stage), destino, rs_name,
                               modalidade=info["modalidade"],
                               tasks=list(tasks_ok))
                _t_entrega = time.time()
                entrega = sd.full_e_oar(
                    cruas, volume_hu=_hu_serie,
                    cads={},
                    cervicais=_HNLNL_DA_VEZ.get("masks") or None,
                    modo=MODO_DO_VIGIA, extras=_extras_da_vez)
                if isinstance(entrega, dict) and isinstance(
                        entrega.get("parcial"), dict):
                    info["parcial"] = {
                        "conjunto": u"%s" % (entrega["parcial"].get(
                            "conjunto") or u""),
                        "motivo": erro_sem_caminho_nem_uid(u"%s" % (
                            entrega["parcial"].get("motivo") or u""))[:240]}
                try:
                    import radai_records as _rg_mot
                    info["motores_fora_do_ts"] = (
                        _rg_mot.motores_que_desenharam(
                            _HNLNL_DA_VEZ.get("masks"), _extras_da_vez))
                except Exception:
                    pass
                _meta_full = dict(getattr(sd, "meta_do_full", None) or {})
                info["regras_de_gravacao"] = [
                    dict(x) for x in (_meta_full.get("regras_de_gravacao")
                                      or [])]
                info["ilhas_em_revisao"] = [
                    dict(x) for x in (_meta_full.get("ilhas_em_revisao")
                                      or [])]
                try:
                    import radai_records as _rg_f
                    info["faltou"] = _rg_f.faltou_da_serie(
                        info.get("tasks_falharam"),
                        _meta_full.get("nao_sairam"),
                        estruturas_da_task=getattr(
                            engine, "estruturas_da_task", None),
                        saidas_da_construcao=getattr(
                            engine, "saidas_da_construcao", None),
                        motores_falharam=_falhas_dos_motores(_extras_da_vez),
                        estruturas_do_motor=_estruturas_do_motor)
                    if info["faltou"]:
                        wlog(_rg_f.linha_do_parcial("..." + curto,
                                                    info["faltou"]))
                except Exception as _e_f:
                    wlog("nao consegui montar o que faltou nesta serie (%s)"
                         % type(_e_f).__name__)
                if _meta_full.get("acabamento"):
                    info["acabamento"] = dict(_meta_full["acabamento"])
                if isinstance(entrega, dict) \
                        and "oar_fora_por_regiao" in entrega:
                    info["oar_fora_por_regiao"] = dict(
                        entrega.get("oar_fora_por_regiao") or {})
                import radai_output as _ro_passos
                info["etapas"].append({"etapa": _ro_passos.PAI_DOS_PASSOS,
                                       "segundos": time.time() - _t_entrega,
                                       "maquina": MACHINE,
                                       "dispositivo": "cpu"})
                info["passos_do_full"] = list(entrega.get("etapas") or [])
                estruturas = list(entrega.get("estruturas") or [])
                info["estruturas"] = len(estruturas)
                info["gravados"] = [g for g in (getattr(sd, "gravados", None)
                                                or []) if g]
                renovar_lock(sdir, uid, extra=_estado_para_o_lock(info))
                _entregar_motores(engine, str(stage), destino, rs_name,
                                  masks, cruas=cruas, uid=uid,
                                  modalidade=info["modalidade"], sd=sd)
                import radai_batch as _lote_cf
                info["rtstruct_conferidos"] = _lote_cf.exigir_rtstruct_no_disco(
                    sd, (info.get("parcial") or {}).get("motivo") or u"")
            finally:
                parar_dren.set()
                try:
                    drenador.join(timeout=10.0)
                except Exception:
                    pass
                _guardar_o_job(engine, jid, info)
                try:
                    engine._job_del(jid)
                except Exception:
                    pass

        secs = int(time.time() - t0)
        done = {"uid": uid, "date": s["date"], "pid": s.get("pid", ""), "machine": MACHINE,
                "finished": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "secs": secs,
                "rs": rs_name, "tasks": TASKS, "tasks_ok": tasks_ok,
                "cortes": len(arquivos), "structures": estruturas,
                "ver": APPVER, "dry_run": DRY_RUN,
                "modo": MODO_DO_VIGIA,
                "tasks_falharam": list(info.get("tasks_falharam") or [])}
        import radai_records as _rg_done
        done.update(_rg_done.campos_do_done(
            modalidade=info["modalidade"],
            tasks_da_serie=list(info["tarefas"]),
            plano=info.get("plano"), dispositivo=info.get("dispositivo"),
            gravados=info.get("gravados"),
            travamentos=info.get("travamentos"),
            regioes=info.get("regioes"),
            etapas=_etapas_do_done(info),
            tasks_sem_estrutura=info.get("tasks_sem_estrutura"),
            faltou=info.get("faltou"),
            tasks_do_cache=info.get("tasks_do_cache"),
            receita_pos=info.get("receita_pos") or u"",
            cache_das_tasks=info.get("cache_das_tasks"),
            motores_fora_do_ts=info.get("motores_fora_do_ts")))
        if info.get("tasks_puladas_por_memoria"):
            done["tasks_puladas_por_memoria"] = [
                dict(x) for x in info["tasks_puladas_por_memoria"]]
        if info.get("parcial"):
            done["parcial"] = dict(info["parcial"])
        m_path(sdir, uid, "done", criar=True).write_text(
            json.dumps(done, ensure_ascii=False), encoding="utf-8")
        _tirar_o_marcador_sem_rtstruct(sdir, uid)
        try:
            m_path(sdir, uid, "fail").unlink()
        except Exception:
            pass
        if info.get("entrega_reservada"):
            soltar_entrega(sdir, uid)
            info["entrega_reservada"] = False
        STATE["done_today"] += 1
        if radai_archive is not None and not DRY_RUN:
            if not radai_archive.registrar_serie(
                    uid=uid, pasta=str(_destino(s)), rs=rs_name, date=s.get("date", ""),
                    pid=s.get("pid", ""), estruturas=len(estruturas), secs=secs,
                    maquina=MACHINE, ver=APPVER):
                wlog("aviso: nao anotei a serie ...%s no indice do acervo "
                     "(a serie esta concluida; so a lista do acervo local nao "
                     "vai mostra-la)" % curto)
        if radai_validation is not None and not DRY_RUN:
            if not radai_validation.registrar_caso(
                    identificador=uid, versao_app=APPVER, resultado="ok",
                    extra={"estruturas": len(estruturas), "segundos": secs,
                           "cortes": len(arquivos), "tasks": list(tasks_ok),
                           "modelo": "TotalSegmentator+_ai"}):
                wlog("aviso: nao registrei a serie ...%s na rastreabilidade "
                     "(a serie esta concluida; falta a linha do registro)" % curto)
        wlog("=== OK ...%s | %d estruturas | %dm%02ds -> %s%s ===" %
             (curto, len(estruturas), secs // 60, secs % 60, rs_name,
              (" | SEM o complemento de: %s" % ", ".join(
                  f.get("task", "?") for f in info.get("tasks_falharam")))
              if info.get("tasks_falharam") else ""))
        info["ok"] = True
        recurso_voltou()
        notificar("titulo_ok", "ok", curto, u" + ".join(
            _rotulo_do_gravado(g) for g in (info.get("gravados") or [])))
        return True
    except _PrimeiraEntregaValeu as e:
        info["erro"] = u"descartada: %s" % e
        wlog("serie ...%s: NAO publico — %s. O que esta maquina calculou e "
             "descartado." % (curto, e))
        return True
    except Exception as e:
        info["erro"] = limpar_erro(e)
        if ENCERRANDO.is_set():
            info["erro"] = u"interrompida: o programa foi encerrado"
            info["encerrada"] = True
            wlog("serie ...%s interrompida pelo encerramento do programa: "
                 "NAO conta como falha e volta para a fila" % curto)
            return False
        if CANCELAR_VIGIA.is_set():
            info["erro"] = u"interrompida pelo operador"
            info["cancelada"] = True
            wlog("serie ...%s interrompida pelo operador: NAO conta como "
                 "falha e volta para a fila do vigia" % curto)
            return False
        _regra_a = False
        try:
            import radai_topography as _tp_e
            _regra_a = isinstance(e, _tp_e.AchadoPorOmissao)
        except Exception:
            pass
        if erro_de_ambiente(e) or _regra_a:
            info["ambiente"] = True
            barrar_por_ambiente(e)
            with LOCK:
                STATE["fails"] = ([{"uid": curto, "err": "ambiente (nao contou como falha)"}]
                                  + STATE["fails"])[:20]
            notificar("titulo_erro", "ambiente", curto)
            return False
        limpo = limpar_erro(e)
        if not limpo:
            limpo = type(e).__name__
            info["erro"] = limpo
        classe = classificar_erro(e)
        try:
            assinatura = _falhas.assinatura_da_falha(e, classe)
            frase_da_falha = _falhas.frase_curta(e)
        except Exception:
            assinatura, frase_da_falha = u"", limpo[:140]
        info["assinatura"], info["classe"] = assinatura, classe
        try:
            info["tipo_da_falha"] = _falhas.causa_da_falha(e)[0]
        except Exception:
            pass
        _reg_ass = (registrar_assinatura(assinatura, classe, s, frase_da_falha)
                    if assinatura else {"n": 1, "em_espera": False,
                                        "ja_estava": False, "entrou": False,
                                        "primeira": curto,
                                        "notificada": False, "itens": []})
        _repetida = bool(_reg_ass.get("notificada"))
        if classe == INELEGIVEL:
            return _recusar_serie(s, e, limpo, assinatura, _repetida)
        _comp = (info.get("complemento_adiado")
                 if classe in (RECURSO, TRAVOU) else None)
        fl = read_marker(sdir, uid, "fail") or {"tries": 0}
        # GUARDA: a serie que rodou nao estava em espera nesta versao; a
        # espera so volta pela assinatura desta falha (logo abaixo).
        fl.pop("em_espera", None)
        agora_s = time.time()
        fl.update({"last_error": limpo[:500], "machine": MACHINE,
                   "when": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                   "ultimo_tipo": classe, "assinatura": assinatura,
                   "versao_do_app": APPVER,
                   "turno": STATE.get("turno_id")})
        if classe in (DETERMINISTICO, INDETERMINADA):
            if _reg_ass.get("ja_estava"):
                fl["em_espera"] = assinatura
                fl.setdefault("tries", 0)
            else:
                fl["tries"] = int(fl.get("tries", 0) or 0) + 1
                if _reg_ass.get("entrou"):
                    fl["em_espera"] = assinatura
        else:
            fl[classe] = int(fl.get(classe, 0) or 0) + 1
            _vezes = int(fl.get(RECURSO, 0) or 0) + int(fl.get(TRAVOU, 0) or 0)
            _ate = agora_s + espera_do_adiamento_s(_vezes)
            _adiada = dict(fl.get("adiada") or {})
            _adiada[MACHINE] = _ate
            fl["adiada"] = _adiada
            fl.setdefault("tries", 0)
            if _comp:
                _por = dict(fl.get(ADIAMENTOS_DO_COMPLEMENTO) or {})
                _por[_comp] = int(_por.get(_comp, 0) or 0) + 1
                fl[ADIAMENTOS_DO_COMPLEMENTO] = _por
        try:
            m_path(sdir, uid, "fail", criar=True).write_text(
                json.dumps(fl, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass
        if fl.get("em_espera"):
            info["em_espera"] = True
            _por_em_espera(_reg_ass.get("itens"), assinatura)
        if classe == RECURSO:
            contar_falha_de_recurso()
        if classe in (RECURSO, TRAVOU):
            with LOCK:
                STATE["fails"] = ([{"uid": curto,
                                    "err": (u"%s (nao contou tentativa): %s"
                                            % (classe, limpo[:120]))}]
                                  + STATE["fails"])[:20]
            wlog("ADIADA serie ...%s por %s (NAO conta como tentativa; esta "
                 "maquina volta a ela depois de %s, no fim da fila — outra "
                 "estacao pode pega-la antes): %s | assinatura %s"
                 % (curto, u"erro de RECURSO" if classe == RECURSO
                    else u"TRAVA (tempo limite)",
                    datetime.fromtimestamp(fl["adiada"][MACHINE]).strftime(
                        "%d/%m %H:%M"), limpo[:500], assinatura))
            if _comp:
                _n_comp = int(fl[ADIAMENTOS_DO_COMPLEMENTO].get(_comp, 0))
                wlog("   quem estourou foi a task `%s` do complemento de "
                     "regiao (adiamento %d de %d): %s"
                     % (_comp, _n_comp, TETO_ADIAMENTOS_DO_COMPLEMENTO,
                        u"na proxima volta, se ela estourar de novo, a serie "
                        u"sai com a base e SEM ela (registrada em "
                        u"tasks_falharam)"
                        if _n_comp >= TETO_ADIAMENTOS_DO_COMPLEMENTO
                        else u"a serie ainda sera adiada se ela estourar "
                             u"de novo"))
            if _repetida:
                _mesma_falha(_reg_ass, assinatura)
                return False
            try:
                for _l in traceback.format_exc().strip().splitlines():
                    wlog("   " + _l)
            except Exception:
                pass
            notificar("titulo_erro", "adiada_recurso" if classe == RECURSO
                      else "adiada_trava", curto)
            return False
        with LOCK:
            STATE["fails"] = ([{"uid": curto, "err": limpo[:160]}] + STATE["fails"])[:20]
        if _reg_ass.get("ja_estava"):
            wlog("FALHOU serie ...%s (%s): a assinatura %s esta em espera — "
                 "a serie fica em espera, SEM tentativa a mais: %s"
                 % (curto, classe, assinatura, limpo[:300]))
        else:
            wlog("FALHOU serie ...%s (tentativa %d/%d): %s | %s, assinatura %s"
                 % (curto, fl["tries"], MAX_RETRIES, limpo[:500], classe,
                    assinatura))
        if _reg_ass.get("entrou"):
            wlog("EM ESPERA: a mesma falha se repetiu em %d series (%s, "
                 "assinatura %s): %s — as series com ela ficam em espera ate "
                 "«Liberar» ou ate a versao do app mudar; as series novas "
                 "continuam sendo tentadas"
                 % (_reg_ass.get("n"), classe, assinatura, frase_da_falha))
            notificar("titulo_erro", "em_espera", curto, _reg_ass.get("n"))
        if _repetida:
            _mesma_falha(_reg_ass, assinatura)
            return False
        try:
            for _l in traceback.format_exc().strip().splitlines():
                wlog("   " + _l)
        except Exception:
            pass
        notificar("titulo_erro", "falhou", curto, fl["tries"], MAX_RETRIES)
        return False
    finally:
        parar_hb.set()
        if hb is not None:
            try:
                hb.join(timeout=30)
            except Exception:
                pass
        _esvaziar_cofres()
        if info.get("entrega_reservada"):
            soltar_entrega(sdir, uid)
        unclaim(sdir, uid)
        if stage:
            shutil.rmtree(str(stage), ignore_errors=True)
        _fechar_cronometro()
        if _tmp_serie is not None:
            _tmp_serie.fechar()
        _no_log_da_serie(u"fim da serie ...%s: %s; trava solta" % (
            curto, _desfecho_em_frase(info)))
        _fechar_coletor(coletor)
        _registrar_caso_do_vigia(s, t0, info, coletor)
        _fechar_caso_em_andamento()
        ULTIMO_DESFECHO.clear()
        ULTIMO_DESFECHO.update(info)
        ULTIMO_DESFECHO["uid"] = uid
        CANCELAR_VIGIA.clear()


def _abrir_coletor():
    try:
        import radai_records
        c = radai_records.Coletor(None)
    except Exception as e:
        wlog("registro de casos indisponivel nesta serie (%s) - o contorno "
             "nao e afetado" % type(e).__name__)
        return None
    _COLETOR_DA_SERIE[0] = _EscutaDaSerie(c)
    return c


def _fechar_coletor(coletor):
    e = _COLETOR_DA_SERIE[0]
    if e is not None and e.coletor is coletor:
        _COLETOR_DA_SERIE[0] = None
        if e.arquivo is not None:
            e.arquivo.fechar()
            e.arquivo = None


def _abrir_log_da_serie(s):
    e = _COLETOR_DA_SERIE[0]
    if e is None or not uid_ok(s.get("uid")):
        return None
    try:
        import radai_records
        conferidos, so_trocados = _identificadores_da_serie(s)
        so_trocados = list(so_trocados) + _de_outras(
            menos=_identificadores_de(s.get("pid"), s.get("uid")))
        lg = radai_records.LogDaSerie(str(marker_dir(s["dir"])), s["uid"],
                                      identificadores=conferidos,
                                      so_trocar=so_trocados)
        if lg.abrir():
            e.arquivo = lg
            return lg
        wlog("log da serie: nao abri o arquivo na _RadAI (%s) - o log geral "
             "continua" % lg.erro)
    except Exception as ex:
        wlog("log da serie: indisponivel nesta serie (%s) - o log geral "
             "continua" % type(ex).__name__)
    return None


def _no_log_da_serie(texto):
    e = _COLETOR_DA_SERIE[0]
    if e is not None and e.arquivo is not None:
        for linha in linhas_de_log(texto):
            e.arquivo(linha)


def _desfecho_em_frase(info):
    if info.get("ok"):
        return u"parcial" if (info.get("parcial") or info.get("faltou")) \
            else u"pronta"
    for chave, frase in (("encerrada", u"interrompida pelo encerramento"),
                         ("cancelada", u"interrompida pelo operador"),
                         ("ambiente", u"barrada pelo ambiente"),
                         ("em_espera", u"em espera")):
        if info.get(chave):
            return frase
    if info.get("classe") in (RECURSO, TRAVOU):
        return u"adiada (%s)" % info.get("classe")
    return u"falhou: %s" % (u"%s" % (info.get("erro") or u"?"))[:160]


_CASO_DA_SERIE = [None]


def _abrir_caso_em_andamento(s):
    _CASO_DA_SERIE[0] = None
    if DRY_RUN:
        return None
    try:
        import radai_records
        c = radai_records.CasoEmAndamento(uid=s.get("uid", ""),
                                          origem=u"vigia", modo=MODO_DO_VIGIA)
        if c.abrir():
            _CASO_DA_SERIE[0] = c
            return c
    except Exception as e:
        wlog("registro de casos: o caso em andamento nao foi gravado (%s) - "
             "o contorno nao e afetado" % type(e).__name__)
    return None


def _fechar_caso_em_andamento():
    c, _CASO_DA_SERIE[0] = _CASO_DA_SERIE[0], None
    if c is not None:
        try:
            c.fechar()
        except Exception:
            pass


TETO_DE_OUTRAS = 200
_DE_OUTRAS = []
_LOCK_DE_OUTRAS = threading.Lock()


def _identificadores_de(pid, uid):
    fora = [str(pid or "").strip()]
    u = str(uid or "").strip()
    if len(u) >= 8:
        fora.append(u[-8:])
    return fora


def _lembrar_de_outras(valores):
    try:
        novos = [str(v).strip() for v in (valores or ()) if v]
        novos = [v for v in novos if len(v) >= 4]
        if not novos:
            return
        with _LOCK_DE_OUTRAS:
            for v in novos:
                if v in _DE_OUTRAS:
                    _DE_OUTRAS.remove(v)
                _DE_OUTRAS.append(v)
            del _DE_OUTRAS[:-TETO_DE_OUTRAS]
    except Exception as e:
        wlog("registro de casos: nao consegui guardar os identificadores de "
             "outras series (%s) - o filtro por thread continua valendo"
             % type(e).__name__)


def _de_outras(menos=()):
    fora = set(str(m) for m in menos if m)
    with _LOCK_DE_OUTRAS:
        return [v for v in _DE_OUTRAS if v not in fora]


def _medidas_da_imagem(ref, cortes):
    import radai_records
    return radai_records.medidas_da_imagem(ref, cortes)


def _so_o_que_aceita(fn, **kw):
    try:
        import inspect
        params = inspect.signature(fn).parameters
    except (TypeError, ValueError):
        return {}
    if any(p.kind == p.VAR_KEYWORD for p in params.values()):
        return dict(kw)
    return {k: v for k, v in kw.items() if k in params}


def _guardar_o_job(engine, jid, info):
    try:
        j = engine._job(jid) or {}
    except Exception as e:
        info["job_ilegivel"] = type(e).__name__
        return
    info["log_motor"] = [str(x) for x in (j.get("log") or [])]
    try:
        _c = dict(j.get("cache") or {})
        info["tasks_do_cache"] = sorted(str(t) for t, v in _c.items()
                                        if (v or {}).get("lido"))
        info["cache_das_tasks"] = dict((str(t), (v or {}).get("chave"))
                                       for t, v in _c.items()
                                       if (v or {}).get("chave"))
    except Exception:
        pass
    try:
        import radai_records
        do_motor = radai_records.do_job(j)
    except Exception as e:
        info["job_ilegivel"] = type(e).__name__
        return
    if do_motor.get("plano"):
        info["plano"] = dict(do_motor["plano"])
        info["plano_origem"] = "motor"
    try:
        if j.get("planos"):
            info["planos"] = dict((str(t), dict(p or {}))
                                  for t, p in dict(j["planos"]).items())
    except Exception:
        pass
    if do_motor.get("partes") is not None:
        info["partes"] = do_motor["partes"]
    if do_motor.get("recorte_no_corpo"):
        info["recorte_no_corpo"] = do_motor["recorte_no_corpo"]
    try:
        if j.get("travamentos"):
            info["travamentos_do_job"] = [dict(x) for x in j["travamentos"]
                                          if isinstance(x, dict)]
    except Exception:
        pass


def _plano_para_o_registro(engine, jid, ref, tarefas, dev, info):
    if str(dev).lower() == "cpu":
        info["plano"] = {"modo": "cpu", "motivo": "DEVICE resolveu para cpu"}
        info["plano_origem"] = "vigia: o dispositivo resolvido"
        return
    fn = getattr(engine, "plano_de_dispositivo", None)
    if fn is None:
        info["plano_origem"] = "indisponivel nesta versao do motor"
        return
    try:
        m = _medidas_da_imagem(ref, 0)
        base = next((t for t in tarefas if t in _bases_conhecidas()), "total_v3")
        info["plano"] = dict(fn(tuple(m["forma_zyx"]),
                                tuple(m["espacamento_zyx_mm"]), task=base) or {})
        info["plano_origem"] = "vigia, no inicio da serie (mesmas entradas do motor)"
    except Exception as e:
        info["plano_origem"] = "o plano levantou %s: %s" % (type(e).__name__,
                                                           str(e)[:80])


def _bases_conhecidas():
    try:
        import radai_tasks as _rt
        return tuple(_rt.BASES_CT) + tuple(_rt.BASES_MR)
    except Exception:
        return ("total_v3", "total_v2", "total_mr")


def _identificadores_da_serie(s):
    import radai_records
    uid = str(s.get("uid") or "")
    rel = ""
    try:
        rel = rel_root(s.get("dir") or "")
    except Exception:
        rel = ""
    conferidos = [x for x in (s.get("pid"), uid, rel)
                  if x and x not in (".", "..")]
    so_trocados = radai_records.pastas_para_trocar(
        [sem_prefixo(s.get("dir") or "")] if s.get("dir") else [],
        prefixos=[sem_prefixo(ROOT)] if ROOT else [])
    return conferidos, so_trocados


def _registrar_caso_do_vigia(s, t0, info, coletor):
    if DRY_RUN:
        return ""
    try:
        return _montar_e_registrar_caso(s, t0, info, coletor)
    except Exception as e:
        wlog("registro de casos: nao consegui montar o caso desta serie "
             "(%s: %s) - o contorno nao foi afetado"
             % (type(e).__name__, str(e)[:120]))
        return ""


def _montar_e_registrar_caso(s, t0, info, coletor):
    try:
        import radai_records
    except Exception as e:
        wlog("registro de casos indisponivel (%s) - o contorno nao foi "
             "afetado" % type(e).__name__)
        return ""
    conferidos, so_trocados = _identificadores_da_serie(s)
    so_trocados = list(so_trocados) + _de_outras(
        menos=_identificadores_de(s.get("pid"), s.get("uid")))
    linhas = list(info.get("log_motor") or []) + list(
        (coletor.linhas if coletor is not None else []))
    segundos = time.time() - t0
    execucao = {
        "origem": "vigia",
        "modalidade": info.get("modalidade") or None,
        "dispositivo_pedido": str(CFG.get("DEVICE", "auto")),
        "dispositivo": info.get("dispositivo") or None,
        "plano_origem": info.get("plano_origem") or None,
    }
    execucao.update(radai_records.execucao_do_motor(
        {"plano": info.get("plano"), "partes": info.get("partes"),
         "recorte_no_corpo": info.get("recorte_no_corpo"),
         "job_ilegivel": info.get("job_ilegivel")},
        recorte_pedido=bool(RECORTE_NO_CORPO)))
    execucao.update({
        "fallbacks": radai_records.achar_fallbacks(linhas),
        "tasks_pedidas": list(info.get("tasks_pedidas") or []),
        "tasks_da_serie": list(info.get("tarefas") or []),
        "tasks_rodadas": list(info.get("tasks_ok") or []),
        "tasks_falharam": [dict(f) for f in
                           (info.get("tasks_falharam") or [])],
        "task_em_curso_na_falha": (info.get("task_em_curso") or None)
        if not info.get("ok") else None,
    })
    etapas = [dict(e, segundos=round(float(e.get("segundos") or 0), 1))
              for e in (info.get("etapas") or [])]
    try:
        import radai_output
        etapas = radai_output.etapas_do_caso(etapas,
                                             info.get("passos_do_full"))
    except Exception as e:
        wlog("registro de casos: os passos da cadeia do FULL nao entraram "
             "no caso (%s) - a linha 'FULL e OAR' continua" % type(e).__name__)
    etapas.append({"etapa": "serie inteira", "segundos": round(segundos, 1)})
    processamento = {
        "modo": MODO_DO_VIGIA,
        "tasks_ligadas": list(info.get("tarefas") or []),
        "comparacao": {"ts": 0, "nv": 0, "cads": 0, "mse": 0},
    }
    if info.get("niveis_cervicais"):
        processamento["niveis_cervicais"] = dict(info["niveis_cervicais"])
    _plano = radai_records.plano_do_caso(info.get("plano"),
                                         info.get("planos"))
    if _plano:
        processamento["plano_dispositivo"] = _plano
    if "regras_de_gravacao" in info:
        processamento["remocoes"] = radai_records.remocoes_do_full(
            info.get("regras_de_gravacao"))
    if "ilhas_em_revisao" in info:
        processamento["ilhas_em_revisao"] = radai_records.ilhas_do_full(
            info.get("ilhas_em_revisao"))
    if info.get("acabamento"):
        processamento["acabamento"] = radai_records.acabamento_do_caso(
            info.get("acabamento"))
    if "travamentos" in info:
        processamento["travamentos"] = [
            dict(x) for x in (info.get("travamentos") or [])]
    elif info.get("travamentos_do_job"):
        _por_task = {}
        for x in info["travamentos_do_job"]:
            t = str(x.get("task") or "?")
            a = _por_task.setdefault(t, {"task": t, "motivo": x.get("motivo"),
                                         "numeros": dict(x.get("numeros")
                                                         or {}),
                                         "onde": x.get("onde"),
                                         "retomada": "nao"})
            if x.get("plano_menor"):
                a["retomada"] = "travou"
        processamento["travamentos"] = list(_por_task.values())
    if info.get("recortes"):
        try:
            _entrada = getattr(carregar_engine(), "entrada_do_recorte", None)
        except Exception:
            _entrada = None
        _cb = radai_records.clip_box_do_caso(
            info["recortes"], modo=MODO_DO_VIGIA, entrada=_entrada)
        if _cb:
            processamento["clip_box"] = _cb
    if "oar_fora_por_regiao" in info:
        processamento["oar_fora_por_regiao"] = (
            radai_records.oar_fora_por_regiao_do_caso(
                info.get("oar_fora_por_regiao")))
    try:
        _pico = radai_records.pico_de_memoria(info.get("log_motor") or [])
    except Exception:
        _pico = None
    if _pico:
        processamento["pico_memoria"] = _pico
    return radai_records.registrar_serie(
        uid=s.get("uid", ""),
        identificadores=conferidos, so_trocar=so_trocados,
        serie=radai_records.medir_serie(s, info.get("medidas") or {},
                                        origem="vigia"),
        resultado=dict({"ok": bool(info.get("ok")), "erro": info.get("erro", ""),
                        "ambiente": bool(info.get("ambiente")),
                        "estruturas": info.get("estruturas")},
                       **radai_records.resultado_do_campo(info)),
        etapas=etapas, execucao=execucao,
        processamento=processamento,
        coletor=coletor,
        tasks=tuple(info.get("tasks_ok") or info.get("tarefas") or ()),
        segundos_totais=segundos, log=wlog)


def _uniao_de_cruas(mapas):
    import radai_output
    return radai_output.UniaoDeCruas(mapas)


class _UniaoDeCruas(object):

    def __new__(cls, mapas):
        import radai_output
        return radai_output.UniaoDeCruas(mapas)


class _MasksJuntas(object):

    def __init__(self, nossas, nv):
        self._a, self._b = nossas, nv

    def __iter__(self):
        for k in self._a:
            yield k
        for k in self._b:
            yield k

    def __len__(self):
        return len(self._a) + len(self._b)

    def __contains__(self, k):
        return k in self._a or k in self._b

    def keys(self):
        return list(self)

    def __getitem__(self, k):
        return self._a[k] if k in self._a else self._b[k]




def _saida_de(engine, stage, destino, rs_name, modalidade=None, tasks=None):
    import radai_output
    return radai_output.Saida(
        engine, str(stage), str(destino), rs_name,
        tasks=(TASKS if tasks is None else list(tasks)), versao=APPVER,
        suavizar_mm=SUAVIZAR_MM,
        log=wlog, copiar=lambda o, d: _copiar_atomico(o, Path(d)),
        **_so_o_que_aceita(radai_output.Saida, modalidade=modalidade))


def _entregar_motores(engine, stage, destino, rs_name, masks_nossas,
                      cruas=None, uid="", modalidade=None, sd=None):
    if sd is None:
        sd = _saida_de(engine, stage, destino, rs_name, modalidade=modalidade)


    try:
        sd.plugins(cruas or {})
    except Exception as e:
        wlog("nao consegui gravar os plugins (%s) — o contorno entregue nao "
             "foi afetado" % str(e)[:140])
        try:
            for _l in traceback.format_exc().strip().splitlines():
                wlog("   " + _l)
        except Exception:
            pass
    sd.pelvicos(masks_nossas)



    _HNLNL_DA_VEZ["masks"] = None
    try:
        import radai_output
        wlog(radai_output.relatorio(sd.gravados))
    except Exception:
        pass
    return sd




TASKS_SO_TORAX = ("lung_vessels",)


def espessura_da_serie(ref):
    try:
        return float(ref.GetSpacing()[2])
    except Exception:
        return 0.0


def _tasks_fora_do_protocolo(tarefas, ref, curto):
    fora = set()
    alvo = [t for t in tarefas if t in TASKS_SO_TORAX]
    if not alvo:
        return fora
    esp = espessura_da_serie(ref)
    try:
        import radai_triage
        teto = float(radai_triage.ESPESSURA_RECUSA_MM)
    except Exception:
        teto = 3.0
    if not serie_elegivel_torax(ref):
        for t in alvo:
            fora.add(t)
        wlog("serie ...%s tem corte de %.2f mm (teto do torax: %.2f mm): "
             "pulando %s — o modulo toracico recusaria a serie, e a inferencia "
             "seria tempo gasto para gerar um arquivo que ninguem abre"
             % (curto, esp, teto, ", ".join(sorted(alvo))))
    return fora



def base_na_frente(tarefas, bases=None):
    tarefas = list(tarefas or [])
    if bases is None:
        try:
            import radai_tasks as _rt
            bases = tuple(_rt.BASES_CT) + tuple(_rt.BASES_MR)
        except Exception:
            bases = ("total_v3", "total_v2", "total_mr")
    na_frente = [t for t in tarefas if t in bases]
    if not na_frente:
        return tarefas
    return na_frente + [t for t in tarefas if t not in bases]


def tasks_pela_modalidade(tarefas, modalidade, log=None,
                          quem_pediu=u"o config"):
    log = log or wlog
    tarefas = list(tarefas or [])
    mod = str(modalidade or "").strip().upper()
    try:
        import radai_tasks as _rtm
    except Exception as e:
        log("nao consegui carregar a regra de tasks por modalidade (%s) - "
            "rodo a lista como veio" % type(e).__name__)
        return tarefas
    fn = getattr(_rtm, "tasks_da_serie", None)
    if fn is not None and mod:
        try:
            nova = list(fn(list(tarefas), mod, log=log))
            if nova != tarefas:
                log("tasks desta serie %s: %s (%s pediu %s)"
                    % (mod, ", ".join(nova) or "(nenhuma)", quem_pediu,
                       ", ".join(tarefas) or "(nenhuma)"))
            return nova
        except Exception as e:
            log("a regra de tasks por modalidade levantou (%s: %s) - rodo a "
                "lista como veio, e aviso o que e de outra modalidade"
                % (type(e).__name__, str(e)[:120]))
    trocadas = []
    for t in tarefas:
        e = _rtm.POR_NOME.get(t) or {}
        mt = str(e.get("modalidade") or "").upper()
        if mod and mt and mt != mod:
            trocadas.append("%s (e de %s)" % (t, mt))
    if trocadas:
        log("ATENCAO: esta serie e %s e %d task(s) sao de outra modalidade: "
            "%s. Elas rodam assim mesmo (foi %s que as pediu, e esta versao "
            "nao troca a base pela modalidade), e o contorno sai marcado - "
            "mas o volume esperado de cada estrutura foi medido na "
            "modalidade dela"
            % (mod, len(trocadas), ", ".join(trocadas), quem_pediu))
    return tarefas


_RM_NO_DISCO = [None, 0.0]
_RM_NO_DISCO_VALIDADE_S = 300.0


def rm_no_disco(pasta_pesos=None, agora=None):
    t = time.time() if agora is None else float(agora)
    if (pasta_pesos is None and _RM_NO_DISCO[1]
            and t - _RM_NO_DISCO[1] < _RM_NO_DISCO_VALIDADE_S):
        return _RM_NO_DISCO[0]
    try:
        import radai_tasks as _rtm
        no_disco = set(_rtm.baixados(pasta_pesos))
        resp = False
        for base in tuple(getattr(_rtm, "BASES_MR", ()) or ()):
            precisa = set(_rtm.datasets_necessarios(base,
                                                    recorte_no_corpo=False))
            if precisa and precisa <= no_disco:
                resp = True
                break
    except Exception:
        resp = None
    if pasta_pesos is None:
        _RM_NO_DISCO[0], _RM_NO_DISCO[1] = resp, t
    return resp


def torax_no_campo(masks, grade=None):
    return carregar_engine().torax_no_campo(masks, grade=grade)




def pescoco_no_campo(masks, grade, cru=None):
    import engine
    return engine.pescoco_no_campo(masks, grade, cru=cru)


def _niveis_cervicais_nesta_serie(masks, cruas, ref, info):
    try:
        if str(info.get("modalidade") or "CT").upper() == "MR":
            motivo = u"so em TC (o modelo dos niveis e de tomografia)"
            info["niveis_cervicais"] = {"rodam": False, "motivo": motivo}
            wlog("niveis cervicais: nao rodam nesta serie — %s" % motivo)
            return False
        _pb = info.get("pescoco_da_base")
        if isinstance(_pb, dict) and "tem" in _pb:
            tem, laudo = bool(_pb["tem"]), _pb.get("laudo") or u""
        else:
            import radai_geom
            grade = radai_geom.Grade.de_sitk(ref)
            tem, laudo = pescoco_no_campo(masks, grade,
                                          cru=cruas_da_base(cruas))
        info["niveis_cervicais"] = {"rodam": bool(tem), "motivo": laudo}
        wlog("niveis cervicais: %s — %s"
             % (u"rodam (vao para o FULL, nunca para o OAR)" if tem
                else u"nao rodam", laudo))
        return bool(tem)
    except Exception as e:
        info["niveis_cervicais"] = {
            "rodam": False,
            "motivo": u"nao consegui medir o pescoco (%s)" % type(e).__name__}
        wlog("niveis cervicais: nao rodam — nao consegui medir o pescoco "
             "(%s: %s)" % (type(e).__name__, str(e)[:120]))
        return False




def _dispositivo_da_task(engine, jid, task, dev):
    try:
        j = engine._job(jid) or {}
    except Exception:
        j = {}
    import radai_records
    return radai_records.dispositivo_da_task(j, task, dev)


def _etapa_da_task(task, segundos, maquina, dispositivo, falhou=False):
    import radai_records
    return radai_records.etapa_da_task(task, segundos, maquina, dispositivo,
                                       falhou=falhou)


def _tasks_pela_anatomia(engine, masks, cruas, ref, info, ja):
    import radai_topography as _tp
    try:
        import radai_geom
        grade = radai_geom.Grade.de_sitk(ref)
        nome_tab, tabela = _tp.tabela_da_topografia(info.get("modalidade"))
        if not any(tabela.values()):
            wlog("anatomia: a lista por topografia (%s) desta modalidade esta "
                 "vazia — so a base roda" % (nome_tab or "radai_modes ausente"))
            return []
        anat = _tp.anatomia_da_base(masks, grade, cruas=cruas, motor=engine)
        regioes, laudo = anat["regioes"], list(anat["laudo"])
        coracao = anat["coracao_cm3"]
        info["coracao_cm3"] = coracao
        if anat.get("pescoco") is not None:
            info["pescoco_da_base"] = {"tem": bool(anat["pescoco"][0]),
                                       "laudo": anat["pescoco"][1]}
        info["regioes"] = list(regioes)
        info["anatomia"] = list(laudo)
        wlog("anatomia da serie (depois da base): %s"
             % (", ".join(regioes) or "nenhuma regiao com lista"))
        for linha in laudo:
            wlog("   " + linha)
        achados = getattr(engine, "TASKS_DE_ACHADO", None)
        tasks, fora, _nome = _tp.tasks_da_anatomia(
            regioes, info.get("modalidade") or "CT",
            achados=set(achados) if achados is not None else None,
            coracao_cm3=coracao)
        for t, pq in fora:
            wlog("   `%s` esta na lista da regiao e NAO roda: %s" % (t, pq))
        novas = [t for t in tasks if t not in (ja or ())]
        if not novas:
            return []
        novas = tasks_pela_modalidade(novas, info.get("modalidade"),
                                      quem_pediu=u"a anatomia")
        try:
            import radai_tasks as _rt
            novas = _rt.lista_para_rodar(novas, log=wlog)
        except Exception:
            pass
        novas = [t for t in novas if t not in (ja or ())]
        if novas:
            wlog("pela anatomia (%s, tabela %s): %s"
                 % (", ".join(regioes) or "sem regiao", _nome,
                    ", ".join(novas)))
            if "torax" not in regioes and coracao is not None:
                try:
                    import radai_modes as _md
                    _pelo_cor = [t for t in novas if t in tuple(
                        getattr(_md, "TASKS_DO_CORACAO_SEM_TORAX", ()))]
                    if _pelo_cor and coracao >= float(
                            getattr(_md, "CORACAO_MINIMO_CM3", 100.0)):
                        wlog("   %s: o coracao do modelo tem %.1f cm3 (piso "
                             "%.0f) e o torax nao foi identificado — roda "
                             "para o pericardio do Heart_ai"
                             % (", ".join(_pelo_cor), coracao,
                                float(_md.CORACAO_MINIMO_CM3)))
                except Exception:
                    pass
        return novas
    except _tp.AchadoPorOmissao:
        raise
    except Exception as e:
        wlog("anatomia: nao consegui decidir as tasks da regiao (%s: %s) — a "
             "serie segue so com a base e o que o config pediu"
             % (type(e).__name__, str(e)[:120]))
        try:
            for _l in traceback.format_exc().strip().splitlines():
                wlog("   " + _l)
        except Exception:
            pass
        return []




def serie_elegivel_torax(ref):
    esp = espessura_da_serie(ref)
    try:
        import radai_triage
        teto = float(radai_triage.ESPESSURA_RECUSA_MM)
    except Exception:
        teto = 3.0
    return bool(esp) and esp <= teto




_HNLNL_DA_VEZ = {"masks": None}


def _esvaziar_cofres():
    _HNLNL_DA_VEZ["masks"] = None


def _grade_de(stage):
    import engine
    import radai_geom
    return radai_geom.Grade.de_sitk(engine.load_sitk(str(stage)))


def cruas_da_base(cruas):
    import radai_output
    return radai_output.cruas_da_base(cruas)


def _rodar_hnlnl(stage, cruas, ref):
    engine = carregar_engine()
    import radai_output
    return radai_output.niveis_cervicais_da_serie(
        ref, cruas, device=engine._resolve_device(CFG["DEVICE"]), log=wlog)


def _rodar_motores_do_full(cruas, ref, info):
    try:
        import radai_modes
        pedidos = radai_modes.motores_do_auto(info.get("regioes") or (),
                                              info.get("modalidade") or "CT")
    except Exception:
        pedidos = ()
    if not pedidos:
        return None
    try:
        engine = carregar_engine()
        import radai_motores_full
        return radai_motores_full.motores_na_serie(
            ref, cruas, pedidos,
            device=engine._resolve_device(CFG["DEVICE"]), log=wlog,
            modalidade=info.get("modalidade") or "CT")
    except Exception as e:
        wlog("motores do FULL nao rodaram nesta serie (%s) — o contorno "
             "entregue nao foi afetado" % str(e)[:140])
        try:
            for _l in traceback.format_exc().strip().splitlines():
                wlog("   " + _l)
        except Exception:
            pass
        try:
            import radai_motores_full
            return radai_motores_full.falha_de_todos(
                pedidos, radai_motores_full.FALHOU,
                "%s: %s" % (type(e).__name__, str(e)[:140]))
        except Exception:
            return None


def _falhas_dos_motores(extras):
    try:
        import radai_motores_full
        return radai_motores_full.falhas_dos_extras(extras)
    except Exception:
        return []


def _estruturas_do_motor(cod):
    try:
        import radai_motores_full
        return radai_motores_full.estruturas_do_motor(cod)
    except Exception:
        return []




def _destino(s):
    if not OUT_DIR:
        return Path(s["dir"])
    return Path(OUT_DIR) / rel_root(s["dir"])


def _arranque_do_cache_por_task():
    try:
        import radai_cache_tasks as _ct
        _ct.armar(True)
        _f = _ct.faxina()
        e = _ct.estado()
        if e.get("ligado"):
            wlog("cache por task: %s | %d entrada(s), %.1f GB (teto %.0f GB, "
                 "%d dias)%s" % (e["pasta"], e["entradas"], e["ocupado_gb"],
                                 e["teto_gb"], e["ttl_dias"],
                                 (u" | faxina: %d apagada(s)" % _f["apagadas"])
                                 if _f.get("apagadas") else u""))
        else:
            wlog("cache por task DESLIGADO: %s" % e.get("motivo"))
    except Exception as e:
        wlog("cache por task: nao consegui armar (%s)" % type(e).__name__)


def _faxina_do_cache():
    try:
        import radai_cache_tasks as _ct
        if _ct.armado():
            _ct.faxina()
    except Exception:
        pass


def liberar_falhas():
    liberadas, erros = 0, 0
    alvos = list(PULADAS_POR_FALHA) + list(NAO_CONTORNAVEIS) + list(EM_ESPERA)
    with LOCK:
        for _r in (STATE.get("assinaturas") or {}).values():
            if _r.get("em_espera"):
                _r["em_espera"] = False
                _r["series"], _r["itens"] = [], []
        STATE["alertas_de_assinatura"] = []
    for item in alvos:
        try:
            m_path(item["dir"], item["uid"], "fail").unlink()
            liberadas += 1
        except FileNotFoundError:
            liberadas += 1
        except Exception as e:
            erros += 1
            wlog("nao consegui liberar a serie ...%s (%s)" % (item["uid"][-8:], e))
    del PULADAS_POR_FALHA[:]
    del NAO_CONTORNAVEIS[:]
    del EM_ESPERA[:]
    with LOCK:
        STATE["puladas"] = 0
        STATE["nao_contornaveis"] = 0
        STATE["em_espera"] = 0
    RESCAN_NOW.set()
    wlog("liberadas %d serie(s) que estavam marcadas como falha%s — nova varredura pedida"
         % (liberadas, (" | %d nao consegui" % erros) if erros else ""))
    return {"liberadas": liberadas, "erros": erros, "tentadas": len(alvos)}


def fora_da_fila(teto=30):
    def _limpo(t, n=200):
        try:
            return _falhas.sem_caminho_nem_uid(t)[:n]
        except Exception:
            return u""
    nc = [{"uid8": str(x.get("uid") or "")[-8:], "pid": str(x.get("pid") or ""),
           "motivo": _limpo(x.get("motivo"))}
          for x in list(NAO_CONTORNAVEIS)[:teto]]
    with LOCK:
        alertas = {a.get("assinatura"): dict(a)
                   for a in STATE.get("alertas_de_assinatura") or []}
    grupos = {}
    for x in list(EM_ESPERA):
        a = str(x.get("assinatura") or "")
        g = grupos.setdefault(a, {"assinatura": a, "series": 0,
                                  "frase": u"", "uid8": []})
        g["series"] += 1
        if len(g["uid8"]) < teto:
            g["uid8"].append(str(x.get("uid") or "")[-8:])
        if not g["frase"]:
            g["frase"] = ((alertas.get(a) or {}).get("frase")
                          or _limpo(x.get("frase"), 140))
    for a, al in alertas.items():
        g = grupos.setdefault(a, {"assinatura": a, "series": 0,
                                  "frase": u"", "uid8": []})
        g["series"] = max(g["series"], int(al.get("series") or 0))
        g["frase"] = g["frase"] or _limpo(al.get("frase"), 140)
    return {"nao_contornaveis": nc,
            "n_nao_contornaveis": len(NAO_CONTORNAVEIS),
            "em_espera": sorted(grupos.values(),
                                key=lambda g: -g["series"])[:teto],
            "n_em_espera": len(EM_ESPERA)}


def limpar_temporarios():
    limite = time.time() - 24 * 3600
    n = 0
    try:
        import radai_archive as _arq_uso
        em_uso = _arq_uso.pasta_temporaria_em_uso
        raizes = _arq_uso.raizes_temporarias() or [tempfile.gettempdir()]
    except Exception:
        return
    try:
        for p in [x for r in raizes for x in Path(r).glob("radai_*")]:
            try:
                if p.is_dir() and p.stat().st_mtime < limite:
                    if em_uso(p, 24)[0]:
                        continue
                    shutil.rmtree(str(p), ignore_errors=True)
                    n += 1
            except Exception:
                pass
    except Exception:
        pass
    if n:
        wlog("limpei %d pasta(s) temporaria(s) de execucoes anteriores" % n)


ERROS_DE_AMBIENTE = (
    "no module named 'totalsegmentator'",
    "error while finding module specification",
    "no module named 'torch'",
    "no module named 'nnunet",
    "no module named 'pkg_resources'",
    "dll load failed",
)


def erro_de_ambiente(msg):
    if isinstance(msg, BaseException):
        # GUARDA: falta de memoria, trava e volume recusado nunca pausam o
        # vigia, mesmo com "DLL load failed" na excecao do filho.
        try:
            if _falhas.classificar_falha(msg) in (
                    _falhas.RECURSO, _falhas.TRAVOU, _falhas.INELEGIVEL):
                return False
        except Exception:
            pass
        msg = u"%s: %s" % (type(msg).__name__, msg)
    baixo = str(msg).lower()
    return any(a in baixo for a in ERROS_DE_AMBIENTE)


RECURSO = _falhas.RECURSO
TETO_DE_RECURSO_SEGUIDO = 3
FRASE_DO_RECURSO_ESGOTADO = (u"o processo parece sem recurso (memória ou "
                             u"threads): feche e abra o programa")
_RECURSO_SEGUIDO = {"n": 0, "avisou": False}


def contar_falha_de_recurso():
    with LOCK:
        _RECURSO_SEGUIDO["n"] += 1
        return _RECURSO_SEGUIDO["n"]


def recurso_voltou():
    with LOCK:
        _RECURSO_SEGUIDO["n"] = 0
        _RECURSO_SEGUIDO["avisou"] = False


def recurso_esgotado():
    return _RECURSO_SEGUIDO["n"] >= TETO_DE_RECURSO_SEGUIDO
TRAVOU = _falhas.TRAVOU
DETERMINISTICO = _falhas.DETERMINISTICO
INELEGIVEL = _falhas.INELEGIVEL
INDETERMINADA = _falhas.INDETERMINADA

ADIADA_BASE_MIN = 30.0
ADIADA_TETO_H = 12.0

_TIPOS_DE_RECURSO = _falhas.TIPOS_DE_RECURSO
_FRASES_DE_RECURSO = _falhas.FRASES_DE_RECURSO
_FRASES_DE_TRAVA = _falhas.FRASES_DE_TEMPO_LIMITE
_TIPOS_DE_TRAVA = _falhas.TIPOS_DE_TRAVA
_PALAVRA_DA_TRAVA = _falhas.PALAVRA_DA_TRAVA


def _cadeia_de(e):
    return _falhas._cadeia(e)


def classificar_erro(e):
    try:
        return _falhas.classificar_falha(e)
    except Exception:
        return DETERMINISTICO


def espera_do_adiamento_s(vezes):
    n = max(1, int(vezes or 1))
    return min(ADIADA_TETO_H * 3600.0,
               ADIADA_BASE_MIN * 60.0 * (2 ** (n - 1)))


def adiamento_de(fl, agora=None, maquina=None):
    try:
        ate = float(((fl or {}).get("adiada") or {}).get(maquina or MACHINE)
                    or 0)
    except Exception:
        ate = 0.0
    agora = time.time() if agora is None else float(agora)
    if ate <= agora:
        return 0.0, u""
    return ate, str((fl or {}).get("ultimo_tipo") or RECURSO)


def ja_foi_adiada(fl):
    fl = fl or {}
    return bool(int(fl.get(RECURSO) or 0) or int(fl.get(TRAVOU) or 0))


TETO_ADIAMENTOS_DO_COMPLEMENTO = 2
ADIAMENTOS_DO_COMPLEMENTO = "adiamentos_do_complemento"


def adiamentos_do_complemento(fl, task):
    try:
        return int(((fl or {}).get(ADIAMENTOS_DO_COMPLEMENTO) or {})
                   .get(str(task)) or 0)
    except Exception:
        return 0


def complemento_ainda_adia(fl, task):
    return adiamentos_do_complemento(fl, task) < TETO_ADIAMENTOS_DO_COMPLEMENTO


_BARRA = re.compile(r"\s*\d{1,3}%\s*\|[^|]*\|\s*\d+/\d+\s*\[[^\]]*\]")
_BLOCOS = re.compile(u"[─-▟░-▓]+")
_RESTO_BARRA = re.compile(r"\|?\s*\d+/\d+\s*\[[^\]]*\]")


def limpar_erro(msg):
    t = str(msg).replace("\r", "\n")
    t = _BARRA.sub(" ", t)
    t = _BLOCOS.sub("", t)
    t = _RESTO_BARRA.sub(" ", t)
    t = re.sub(r"\s*\|\s*", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def conferir_ambiente():
    try:
        import engine
        engine.conferir_tasks(TASKS)
    except ValueError as e:
        return False, u"%s" % e
    except Exception:
        pass

    try:
        import engine
        engine.conferir_tasks_existem(TASKS)
    except ValueError as e:
        return False, u"%s" % e
    except Exception:
        pass

    if DRY_RUN:
        return True, "simulacao: o TotalSegmentator nao e chamado"
    try:
        r = subprocess.run([sys.executable, "-c", "import totalsegmentator"],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=300)
        if r.returncode == 0:
            return True, ""
        saida = (r.stderr or b"").decode("utf-8", "replace").strip()
        ultima = saida.splitlines()[-1] if saida else "codigo %d" % r.returncode
        return False, ultima[:300]
    except Exception as e:
        return False, "%s: %s" % (type(e).__name__, e)


def barrar_por_ambiente(detalhe):
    with LOCK:
        STATE["ambiente_erro"] = str(detalhe)[:400]
        STATE["paused"] = True
    wlog("=" * 64)
    wlog("PAREI: este Python nao consegue rodar o TotalSegmentator.")
    wlog("  %s" % str(detalhe)[:300])
    wlog("  NENHUMA serie foi marcada como falha: o problema e do ambiente, nao")
    wlog("  das imagens. Rode o vigia com o Python do bundle (a pasta python\\ ao")
    wlog("  lado do radai_watcher.py, via start_watcher.cmd) e clique em Rodar.")
    wlog("=" * 64)


def _sem_aspas(v):
    return (u"%s" % (v or u"")).strip().strip('"')


def _mesma_pasta(a, b):
    a, b = _sem_aspas(a), _sem_aspas(b)
    if not a or not b:
        return a == b
    return os.path.normcase(os.path.normpath(a)) == os.path.normcase(
        os.path.normpath(b))


def _root_no_arquivo():
    try:
        texto = CFG_PATH.read_text(encoding="utf-8-sig", errors="ignore")
    except Exception:
        return None
    for linha in texto.splitlines():
        linha = linha.strip()
        if linha.startswith("#") or "=" not in linha:
            continue
        k, v = linha.split("=", 1)
        if k.strip() == "ROOT":
            return _sem_aspas(v)
    return u""


def root_para_o_proximo_turno():
    with _RECARGA_FEITA:
        do_turno = ROOT_DO_TURNO.get("root")
        tmp = TURNO_TEMPORARIO.get("ROOT")
    if do_turno is None or not STATE.get("overnight"):
        return u""
    novo = tmp if tmp is not None else _root_no_arquivo()
    if novo is None or _mesma_pasta(novo, do_turno):
        return u""
    return novo


def recarregar_cfg():
    global CFG, _LOG_FH, _LOG_TENTADO
    antigo, log_antigo = dict(CFG), LOG_DIR
    del AVISOS_CFG[:]
    CFG = load_cfg()
    with _RECARGA_FEITA:
        _do_turno = dict(TURNO_TEMPORARIO)
        _root_do_turno = ROOT_DO_TURNO.get("root")
    if _do_turno:
        CFG.update(_do_turno)
    # GUARDA: com o turno aberto, o ROOT dele nao muda no meio; o gravado vale a partir do proximo turno.
    if (_root_do_turno is not None and STATE.get("overnight")
            and not _mesma_pasta(CFG.get("ROOT"), _root_do_turno)):
        CFG["ROOT"] = _root_do_turno
        wlog(u"o ROOT gravado mudou com o turno aberto: a pasta nova vale a "
             u"partir do proximo turno, e este segue na pasta em que abriu")
    aplicar_cfg()

    if LOG_DIR != log_antigo:
        with LOCK_DO_LOG:
            try:
                if _LOG_FH is not None:
                    _LOG_FH.close()
            except Exception:
                pass
            _LOG_FH = None
            _LOG_TENTADO = False

    SEM_PERMISSAO.clear()
    _STATUS_DIR_RECUSADO[0] = False
    conferir_status_dir()
    return sorted(k for k in DEFAULTS if str(antigo.get(k)) != str(CFG.get(k)))


PASTA_NO_PROXIMO_TURNO = (u"a partir do próximo turno para a pasta dos "
                          u"exames: este Overnight Run segue na pasta em que "
                          u"abriu")


def pedir_recarga():
    ocupado = STATE["current"] is not None
    with _RECARGA_FEITA:
        _RECARGA["pedida"] += 1
    RECARREGAR.set()
    RESCAN_NOW.set()
    r = {"agendada": True, "ocupado": ocupado,
         "quando": ("assim que a serie atual terminar" if ocupado
                    else "em instantes")}
    if root_para_o_proximo_turno():
        r["root_no_proximo_turno"] = True
        r["quando"] = PASTA_NO_PROXIMO_TURNO
    return r


def recarga_pendente():
    with _RECARGA_FEITA:
        return _RECARGA["pedida"] > _RECARGA["aplicada"]


def chaves_so_do_turno():
    with _RECARGA_FEITA:
        return sorted(TURNO_TEMPORARIO)


TETO_DA_RECARGA_S = 30.0


def esperar_recarga(teto_s=None):
    teto = TETO_DA_RECARGA_S if teto_s is None else float(teto_s)
    limite = time.monotonic() + max(0.0, teto)
    with _RECARGA_FEITA:
        alvo = _RECARGA["pedida"]
        havia = _RECARGA["aplicada"] < alvo
        while _RECARGA["aplicada"] < alvo:
            falta = limite - time.monotonic()
            if falta <= 0:
                break
            _RECARGA_FEITA.wait(min(falta, 1.0))
        aplicada = _RECARGA["aplicada"] >= alvo
        res = str(_RECARGA.get("resultado") or u"")
    return {"aplicada": aplicada, "pendente": not aplicada,
            "falhou": (res[len("falhou: "):]
                       if (havia and aplicada and res.startswith("falhou"))
                       else u"")}


def quem_esta_segmentando():
    try:
        with LOCK:
            atual = STATE.get("current")
        if atual:
            return {"quem": "vigia",
                    "o_que": u"%s …%s" % (atual.get("pid") or u"série",
                                          str(atual.get("uid") or "")[-8:]),
                    "etapa": str(STATE.get("etapa") or u"")}
    except Exception:
        pass
    try:
        import radai_batch
        e = radai_batch.estado() or {}
        if e.get("rodando"):
            return {"quem": "lote",
                    "o_que": u"%s" % (e.get("atual") or u"uma série"),
                    "etapa": str(e.get("etapa") or u"")}
    except Exception:
        pass
    return None


def _fila_da_estacao(nome, *args, **kw):
    padrao = kw.pop("padrao", None)
    try:
        import radai_queue_state as _fq
        return getattr(_fq, nome)(*args, **kw)
    except Exception:
        return padrao


def _rotulo_do_vigia(q):
    data = str((q or {}).get("date") or "")[:8]
    if len(data) == 8:
        data = "%s/%s/%s" % (data[6:8], data[4:6], data[:4])
    return u" · ".join(x for x in (str((q or {}).get("pid") or u"série"), data)
                       if x)


TRAVAS_SOLTAS_AO_ABRIR = {}
FRASE_DA_TRAVA_SOLTA_AO_ABRIR = (
    u"a trava ficou de um processo desta estação que parou; foi solta ao "
    u"abrir, e a série voltou para a fila do vigia")


def soltar_travas_mortas_do_indice():
    try:
        c = cache_load()
    except Exception:
        return 0
    pares = []
    for dirpath, info in (c or {}).items():
        for uid in ((info or {}).get("series") or {}):
            if uid_ok(uid):
                pares.append((uid, {"dir": dirpath}))
    return soltar_travas_mortas_ao_abrir(pares)


def soltar_travas_mortas_ao_abrir(series):
    soltas = 0
    pares = list(series.items()) if isinstance(series, dict) \
        else list(series or ())
    for uid, s in pares:
        try:
            if not has_marker(s["dir"], uid, "lock"):
                continue
            d = read_marker(s["dir"], uid, "lock") or {}
            if str(d.get("machine") or "") != MACHINE:
                continue
            if soltar_trava_morta(s["dir"], uid):
                soltas += 1
                TRAVAS_SOLTAS_AO_ABRIR[uid] = FRASE_DA_TRAVA_SOLTA_AO_ABRIR
        except Exception as e:
            wlog("nao conferi a trava da serie ...%s ao abrir (%s)"
                 % (str(uid)[-8:], type(e).__name__))
    if soltas:
        wlog("ao abrir: %d trava(s) desta estacao de um processo que parou "
             "foram soltas, e as series voltaram para a fila do vigia" % soltas)
    return soltas


def _publicar_fila_do_vigia(fila):
    fila = list(fila or ())
    itens = []
    for q in fila[:24]:
        if not q.get("uid"):
            continue
        it = {"uid": q.get("uid"), "rotulo": _rotulo_do_vigia(q),
              "pasta": str(q.get("dir") or u"")}
        if q.get("uid") in TRAVAS_SOLTAS_AO_ABRIR:
            it["mensagem"] = TRAVAS_SOLTAS_AO_ABRIR[q["uid"]]
        elif q.get("uid") in MARCADORES_SEM_RTSTRUCT:
            it["mensagem"] = MARCADORES_SEM_RTSTRUCT[q["uid"]]
        if not itens and recurso_esgotado():
            it["mensagem"] = FRASE_DO_RECURSO_ESGOTADO
        itens.append(it)
    _fila_da_estacao("vigia_na_fila", itens, len(fila))


ULTIMO_DESFECHO = {}


def _contar_o_desfecho_a_fila(uid):
    info = dict(ULTIMO_DESFECHO) if ULTIMO_DESFECHO.get("uid") == uid else {}
    _fq = sys.modules.get("radai_queue_state")
    volta = getattr(_fq, "VIGIA_VOLTA", "volta")
    if not info:
        return _fila_da_estacao("vigia_terminou", uid, volta)
    if info.get("cancelada"):
        return _fila_da_estacao(
            "vigia_terminou", uid, "cancelado",
            mensagem=u"interrompida pelo operador; o que ela fez foi "
                     u"descartado, e ela volta para a fila do vigia")
    if info.get("encerrada"):
        return _fila_da_estacao(
            "vigia_terminou", uid, "falhou",
            mensagem=getattr(_fq, "FRASE_FECHOU_NO_MEIO", u""))
    if info.get("ambiente") or info.get("classe") in (RECURSO, TRAVOU):
        return _fila_da_estacao("vigia_terminou", uid, volta)
    if info.get("ok"):
        return _fila_da_estacao(
            "vigia_terminou", uid, "pronto",
            faltou=[(f or {}).get("estrutura") for f in
                    (info.get("faltou") or ()) if isinstance(f, dict)],
            pendentes=info.get("tasks_puladas_por_memoria") or None,
            parcial=(info.get("parcial") or {}).get("motivo") or u"")
    if str(info.get("erro") or u"").startswith(u"descartada"):
        return _fila_da_estacao(
            "vigia_terminou", uid, "pronto", ja_concluida=True,
            mensagem=u"outra estação entregou primeiro; o que esta calculou "
                     u"foi descartado")
    return _fila_da_estacao(
        "vigia_terminou", uid, "falhou",
        mensagem=erro_sem_caminho_nem_uid(u"%s" % (info.get("erro") or
                                                    u"falhou"))[:200])


CANCELAR_VIGIA = threading.Event()


def _soltar_a_trava_do_que_nao_terminou(s, tipo=None):
    try:
        meu, _dono = lock_e_meu(s["dir"], s["uid"])
    except Exception:
        meu = False
    if not meu:
        return False
    unclaim(s["dir"], s["uid"])
    wlog("serie ...%s: a preparacao levantou %s antes de a serie terminar; a "
         "trava foi solta agora e ela volta para a fila do vigia"
         % (str(s.get("uid") or "")[-8:],
            getattr(tipo, "__name__", None) or "uma excecao"))
    return True


def cancelar_serie_do_vigia(pausar=True):
    with LOCK:
        atual = dict(STATE["current"]) if STATE.get("current") else None
    if not atual:
        return {"ok": False, "erro": u"o vigia não está segmentando agora"}
    CANCELAR_VIGIA.set()
    if pausar:
        STATE["paused"] = True
    eng = sys.modules.get("engine")
    if eng is not None:
        try:
            with eng._LOCK:
                jids = list(eng._JOBS.keys())
            for jid in jids:
                eng._set(jid, cancelar=True)
        except Exception as e:
            wlog("nao consegui interromper o motor (%s)" % type(e).__name__)
    wlog("a serie ...%s do vigia foi INTERROMPIDA pelo operador: o que ela "
         "fez e descartado, nao conta como falha e ela volta para a fila do "
         "vigia%s" % (atual.get("uid"), u"; o vigia fica pausado" if pausar
                      else u"; as series pedidas a mao comecam em seguida"))
    return {"ok": True, "interrompida": atual.get("uid"),
            "vigia_pausado": bool(pausar)}


def _uma_volta(estado):
    if RECARREGAR.is_set():
        RECARREGAR.clear()
        with _RECARGA_FEITA:
            _alvo_da_recarga = _RECARGA["pedida"]
        try:
            mudou = recarregar_cfg()
            wlog("configuracao recarregada pelo painel: %s"
                 % (", ".join(mudou) if mudou else "nada mudou"))
            for a in AVISOS_CFG:
                wlog("config: " + a)
            if TURNO_TEMPORARIO:
                wlog("turno com valores TEMPORARIOS em uso (nao gravados no "
                     "radai_watcher.config): %s"
                     % ", ".join(chaves_so_do_turno()))
            estado["fila"] = None
            estado["proxima_varredura"] = 0.0
            with LOCK:
                STATE["recarga"] = "aplicada as %s%s" % (
                    datetime.now().strftime("%H:%M:%S"),
                    (" (%s)" % ", ".join(mudou)) if mudou else "")
        except Exception as e:
            wlog("FALHOU recarregar a configuracao: %s" % e)
            with LOCK:
                STATE["recarga"] = "falhou: %s" % str(e)[:120]
        with _RECARGA_FEITA:
            _RECARGA["aplicada"] = max(_RECARGA["aplicada"], _alvo_da_recarga)
            _RECARGA["resultado"] = str(STATE.get("recarga") or u"")
            _RECARGA_FEITA.notify_all()

    if not STATE["ligado"]:
        estado["turno"] = False
        if estado.get("fila"):
            estado["fila"] = None
        _publicar_fila_do_vigia([])
        time.sleep(3)
        return
    if not estado.get("turno"):
        estado["turno"] = True
        abrir_turno_das_assinaturas()
        _calibracao_do_turno()
    _status_periodico()
    if STATE["paused"]:
        time.sleep(2)
        return
    if not ROOT:
        time.sleep(5)
        return

    agora = time.time()
    precisa_varrer = (agora >= estado["proxima_varredura"] or RESCAN_NOW.is_set()
                      or estado["fila"] is None)
    if precisa_varrer:
        RESCAN_NOW.clear()
        STATE["root_ok"] = os.path.isdir(ROOT)
        if not STATE["root_ok"]:
            wlog("ROOT inacessivel: %s — tento de novo na proxima varredura" % ROOT)
            estado["fila"] = []
            estado["proxima_varredura"] = agora + SCAN_EVERY
            return
        series, done_dates = scan_root()
        if not estado.get("travas_conferidas"):
            estado["travas_conferidas"] = True
            soltar_travas_mortas_ao_abrir(series)
        estado["fila"] = build_queue(series, done_dates)
        _publicar_fila_do_vigia(estado["fila"])
        _faxina_do_cache()
        with LOCK:
            STATE["n_queue"] = len(estado["fila"])
            STATE["queue"] = [{"pid": q.get("pid", ""), "date": (q["date"] or "")[:8],
                               "count": q["count"], "uid": q["uid"][-8:]}
                              for q in estado["fila"][:12]]
            STATE["sem_permissao"] = len(SEM_PERMISSAO)
            STATE["puladas"] = len(PULADAS_POR_FALHA)
        _lembrar_de_outras(
            v for q in reversed(estado["fila"][:TETO_DE_OUTRAS // 2])
            for v in _identificadores_de(q.get("pid"), q.get("uid")))
        wlog("varredura: %d series %s | %d na fila%s%s%s | %ds" %
             (STATE["series_total"], "/".join(sorted(MODALITIES)), len(estado["fila"]),
              (" | %d nao sao a TC de simulacao do exame"
               % STATE["nao_simulacao"]) if STATE["nao_simulacao"] else "",
              (" | %d ainda em transito" % STATE["em_transito"]) if STATE["em_transito"] else "",
              (" | %d adiada(s) nesta maquina (recurso ou trava; nao contam "
               "tentativa)" % STATE["adiadas"]) if STATE.get("adiadas") else "",
              STATE["scan_secs"]))
        estado["proxima_varredura"] = time.time() + SCAN_EVERY
        salvar_status()

    fila = estado["fila"] or []
    if not fila:
        time.sleep(min(15, max(1, estado["proxima_varredura"] - time.time())))
        return

    if (_fila_da_estacao("fechando_ao_fim", padrao=False)
            and not STATE.get("overnight")):
        if not estado.get("avisou_fechando"):
            wlog("o navegador foi fechado: o vigia nao comeca outra serie, e "
                 "o programa se encerra quando a que roda terminar")
            estado["avisou_fechando"] = True
        time.sleep(2)
        return
    estado["avisou_fechando"] = False
    if recurso_esgotado():
        if not _RECURSO_SEGUIDO.get("avisou"):
            _RECURSO_SEGUIDO["avisou"] = True
            wlog("%s (%d falhas de recurso seguidas neste processo, sem "
                 "nenhum sucesso entre elas): o vigia nao pega serie nova; o "
                 "«Rodar agora» continua possivel, e um sucesso zera a conta"
                 % (FRASE_DO_RECURSO_ESGOTADO, _RECURSO_SEGUIDO["n"]))
            _publicar_fila_do_vigia(fila)
        time.sleep(2)
        return
    _ocupado = quem_esta_segmentando()
    if ((_ocupado and _ocupado.get("quem") == "lote")
            or not _fila_da_estacao("tentar_a_vez", "vigia", padrao=True)):
        if not estado.get("avisou_lote"):
            wlog("o «Rodar agora» tem a vez (%s) — o vigia espera a serie "
                 "pedida a mao terminar. Duas segmentacoes na mesma maquina "
                 "estouram a memoria."
                 % ((_ocupado or {}).get("o_que") or u"esperando comecar"))
            estado["avisou_lote"] = True
        time.sleep(2)
        return
    estado["avisou_lote"] = False

    try:
        s = fila.pop(0)
        with LOCK:
            STATE["n_queue"] = len(fila)
        if has_marker(s["dir"], s["uid"], "done"):
            return
        if not claim(s["dir"], s["uid"], {"machine": MACHINE, "pid_os": os.getpid(),
                                          "start": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}):
            return
        TRAVAS_SOLTAS_AO_ABRIR.pop(s["uid"], None)
        _terminou = False
        try:
            with LOCK:
                STATE["current"] = {"pid": s.get("pid", ""), "uid": s["uid"][-8:],
                                    "count": s["count"], "date": (s["date"] or "")[:8],
                                    "desde": datetime.now().strftime("%H:%M"),
                                    "sdir": s["dir"], "uid_cheio": s["uid"]}
            _fila_da_estacao("vigia_comecou", s["uid"], _rotulo_do_vigia(s),
                             str(s["dir"]))
            _publicar_fila_do_vigia(fila)
            salvar_status()
            _sinalizar_em_uso_agora()
            process_series(s)
            _terminou = True
        finally:
            if not _terminou:
                _soltar_a_trava_do_que_nao_terminou(s, sys.exc_info()[0])
            with LOCK:
                STATE["current"] = None
            _contar_o_desfecho_a_fila(s["uid"])
            salvar_status()
            _sinalizar_em_uso_agora()
    finally:
        _fila_da_estacao("soltar_a_vez", "vigia")


def _ao_passo_do_arranque(k, n, nome):
    with LOCK:
        STATE["arranque"].update({"estado": "rodando", "passo": int(k),
                                  "total": int(n), "nome": str(nome)})


def _relatorio_de_arranque(avisos_previos=()):
    with LOCK:
        STATE["arranque"].update({"estado": "rodando", "passo": 0})
    t0 = time.time()
    try:
        import radai_arranque as RA
    except Exception as e:
        wlog("relatorio de arranque indisponivel (%s: %s) - uso o diagnostico "
             "curto de antes" % (type(e).__name__, str(e)[:120]))
        _diagnostico_da_maquina()
        ok, detalhe = conferir_ambiente()
        if ok and detalhe:
            wlog(detalhe)
        with LOCK:
            STATE["arranque"].update({"estado": "pronto",
                                      "segundos": round(time.time() - t0, 1)})
        return ok, detalhe
    ctx = {"log": wlog, "bater": bate_ponto, "ao_passo": _ao_passo_do_arranque,
           "appver": APPVER, "maquina": MACHINE, "python_exe": sys.executable,
           "device": str(CFG.get("DEVICE", "auto")), "tasks": list(TASKS),
           "modalidades": sorted(MODALITIES), "root": ROOT,
           "pasta_trabalho": str(LOG_DIR), "pasta_temp": _TMP_LOCAL,
           "dry_run": DRY_RUN,
           "incluir": {},
           "trava": regra_de_travamento(),
           "recorte_no_corpo": bool(RECORTE_NO_CORPO),
           "carregar_engine": carregar_engine,
           "conferir_ambiente": conferir_ambiente,
           "suavizar_mm": SUAVIZAR_MM,
           "suavizar_fabrica": DEFAULTS.get("SUAVIZAR_MM"),
           "avisos_previos": list(avisos_previos or [])}
    try:
        rel = RA.executar(ctx)
    except Exception as e:
        wlog("o relatorio de arranque QUEBROU (%s: %s) - sigo com a "
             "conferencia do ambiente de antes" % (type(e).__name__, str(e)[:160]))
        for _l in traceback.format_exc().strip().splitlines():
            wlog("   " + _l)
        ok, detalhe = conferir_ambiente()
        with LOCK:
            STATE["arranque"].update({"estado": "pronto",
                                      "segundos": round(time.time() - t0, 1)})
        return ok, detalhe
    arquivo = ""
    try:
        arquivo = RA.gravar(rel, str(LOG_DIR))
        wlog("arranque: bloco gravado em %s (%.1f s no total)"
             % (arquivo, rel.get("segundos") or 0))
    except Exception as e:
        wlog("arranque: nao consegui gravar o bloco em disco (%s: %s) - ele "
             "esta inteiro no log logo acima" % (type(e).__name__, str(e)[:120]))
    amb = (rel.get("dados") or {}).get("ambiente")
    if amb is None:
        falha = next((p.get("falha") for p in rel.get("passos") or []
                      if p.get("nome") == u"pendencias de ambiente"),
                     u"o passo nao rodou")
        ok, detalhe = False, (u"nao consegui conferir o ambiente no arranque "
                              u"(%s)" % falha)
    else:
        ok, detalhe = bool(amb.get("ok")), amb.get("detalhe") or ""
    with LOCK:
        STATE["dispositivo"] = dict((rel.get("dados") or {}).get("dispositivo") or {})
        STATE["arranque"].update({"estado": "pronto",
                                  "arquivo": os.path.basename(arquivo or ""),
                                  "segundos": rel.get("segundos") or 0.0})
    return ok, detalhe


def _calibracao_do_turno():
    try:
        import radai_arranque as RA
        linha = RA.linha_de_calibracao(
            {"device": str(CFG.get("DEVICE", "auto")), "dry_run": DRY_RUN,
             "carregar_engine": carregar_engine},
            do_arranque=STATE.get("dispositivo") or None)
    except Exception as e:
        linha = ("calibracao de arranque do turno nao mediu (%s: %s) - a fila "
                 "segue" % (type(e).__name__, str(e)[:100]))
    wlog(linha)


def worker_loop():
    wlog("Vigia %s iniciado em %s%s" % (APPVER, MACHINE, "  [MODO SIMULACAO]" if DRY_RUN else ""))
    wlog("ROOT=%s | tasks=%s | log=%s" % (ROOT or "(vazio)", ",".join(TASKS), LOG_PATH))
    avisos_do_arranque = []

    try:
        import radai_version
        _laudo_ver = radai_version.conferir(APPVER)
        for _l in radai_version.linhas_para_log(_laudo_ver):
            wlog(_l)
            avisos_do_arranque.append(_l.strip())
        STATE["versoes"] = _laudo_ver
        _idade = radai_version.idade()
        STATE["versoes"]["idade"] = _idade
        if _idade.get("estado") in ("vencido", "sem_carimbo",
                                    "relogio_suspeito"):
            wlog("versao: " + _idade.get("frase", ""))
            avisos_do_arranque.append("versao: " + _idade.get("frase", ""))
    except Exception as _e:
        wlog("nao consegui conferir as versoes (%s) — o vigia segue"
             % type(_e).__name__)

    try:
        import radai_version as _rv
        if URL_VERSOES:
            _rv.iniciar_consulta(
                ao_terminar=lambda d: [wlog(_x)
                                       for _x in _rv.linhas_de_consulta(d)])
        else:
            wlog("versao: consulta desligada (%s=0) — nao vou conferir se ha "
                 "versao nova (isso e diferente de estar em dia)"
                 % _rv.VARIAVEL_URL_VERSOES)
    except Exception as _e:
        wlog("nao consegui iniciar a consulta de versao (%s) — o vigia segue"
             % type(_e).__name__)

    try:
        migrar_config()
    except Exception as _e:
        wlog("config: a migracao das chaves que sairam falhou (%s)"
             % type(_e).__name__)
    for a in AVISOS_CFG:
        wlog("config: " + a)
        avisos_do_arranque.append("config: " + a)
    if not ROOT:
        wlog("ROOT vazio: o vigia nao varre pasta nenhuma (a vigilia noturna "
             "esta parada; o «Rodar agora» funciona normalmente).")
        wlog("   ROOT = a pasta raiz que o vigia varre atras de series novas "
             "-- tipicamente o share de tomografias do servico.")

    if radai_archive is not None:
        try:
            laudo = radai_archive.conferir_local()
            if laudo["nuvem"]:
                wlog("=" * 62)
                wlog("ATENCAO — DADO DE PACIENTE EM PASTA SINCRONIZADA")
                wlog(laudo["aviso"])
                wlog("=" * 62)
                avisos_do_arranque.append(
                    "o acervo (dado derivado de paciente) esta em pasta que "
                    "SINCRONIZA com a nuvem")
            else:
                wlog("acervo: %s" % laudo["caminho"])
        except Exception as e:
            wlog("nao consegui conferir onde o acervo grava: %s" % e)

    if radai_validation is not None:
        try:
            radai_validation.semear(versao_app=APPVER)
            lv = radai_validation.conferir()
            if lv["nuvem"]:
                wlog("=" * 62)
                wlog("ATENCAO — REGISTRO DE VALIDACAO EM PASTA SINCRONIZADA")
                wlog(lv["aviso"])
                wlog("=" * 62)
                avisos_do_arranque.append(
                    "o registro de validacao esta em pasta que SINCRONIZA "
                    "com a nuvem")
            else:
                wlog("registro de validacao: %s | %d caso(s)"
                     % (lv["caminho"], lv["casos"]))
        except Exception as e:
            wlog("nao consegui preparar o registro de validacao: %s" % e)

    limpar_temporarios()

    ok_amb, detalhe = _relatorio_de_arranque(avisos_do_arranque)
    if not ok_amb:
        barrar_por_ambiente(detalhe)

    estado = {"fila": None, "proxima_varredura": 0.0}
    falhas_seguidas = 0
    while True:
        try:
            _uma_volta(estado)
            bate_ponto()
            falhas_seguidas = 0
        except Exception as e:
            falhas_seguidas += 1
            bate_ponto("%s: %s" % (type(e).__name__, e))
            wlog("ERRO no laco principal (%dx): %s" % (falhas_seguidas, e))
            if falhas_seguidas == 1:
                try:
                    for _l in traceback.format_exc().strip().splitlines():
                        wlog("   " + _l)
                except Exception:
                    pass
            else:
                try:
                    wlog("   " + traceback.format_exc().strip()
                         .splitlines()[-1] + "  (traceback na 1a volta)")
                except Exception:
                    pass
            estado["fila"] = None
            time.sleep(min(300, 5 * falhas_seguidas))


app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

_METODOS_QUE_MUDAM = ("POST", "PUT", "PATCH", "DELETE")


@app.middleware("http")
async def _so_da_propria_tela(request, call_next):
    from starlette.responses import JSONResponse
    if request.method in _METODOS_QUE_MUDAM:
        origem = request.headers.get("origin") or ""
        if origem:
            try:
                from urllib.parse import urlsplit
                alvo = urlsplit(str(request.url))
                de = urlsplit(origem)
                mesma = (de.scheme == alvo.scheme and de.netloc == alvo.netloc)
            except Exception:
                mesma = False
            if not mesma:
                return JSONResponse(status_code=403, content={
                    "erro": "requisicao veio de outro site (%s) e foi recusada"
                            % origem[:80],
                    "porque": "esta tela so aceita acao vinda dela mesma. Um "
                              "site aberto noutra aba podia trocar a pasta que "
                              "o vigia varre sem voce ver."})
    return await call_next(request)


HOSTS_PERMITIDOS = ("127.0.0.1", "localhost")
TETO_DO_CORPO_BYTES = 16 * 1024 * 1024


def hosts_permitidos(porta=None):
    p = int(porta or PORT)
    return frozenset("%s:%d" % (h, p) for h in HOSTS_PERMITIDOS)


def host_permitido(host, porta=None):
    h = str(host or "").strip().lower()
    return bool(h) and h in hosts_permitidos(porta)


class PortaoDoHost(object):

    def __init__(self, app, porta=None, teto=None):
        self.app = app
        self.porta = porta
        self.teto = int(teto or TETO_DO_CORPO_BYTES)

    @staticmethod
    async def _responder(send, codigo, corpo):
        dados = json.dumps(corpo, ensure_ascii=False).encode("utf-8")
        await send({"type": "http.response.start", "status": int(codigo),
                    "headers": [(b"content-type",
                                 b"application/json; charset=utf-8"),
                                (b"content-length", str(len(dados)).encode())]})
        await send({"type": "http.response.body", "body": dados})

    async def __call__(self, scope, receive, send):
        tipo = scope.get("type")
        if tipo not in ("http", "websocket"):
            return await self.app(scope, receive, send)
        cab = {}
        for k, v in (scope.get("headers") or ()):
            try:
                cab[k.decode("latin-1").lower()] = v.decode("latin-1")
            except Exception:
                continue
        if not host_permitido(cab.get("host"), self.porta):
            if tipo == "websocket":
                await send({"type": "websocket.close", "code": 1008})
                return
            return await self._responder(send, 403, {
                "erro": "pedido recusado: este painel so atende por %s"
                        % " ou ".join(sorted(hosts_permitidos(self.porta))),
                "porque": "um site pode apontar o proprio nome para este "
                          "computador e conversar com o painel como se "
                          "fosse ele (rebinding de DNS). O nome no endereco "
                          "e o que separa as duas coisas."})
        if tipo == "http":
            cl = cab.get("content-length")
            if cl is not None:
                try:
                    tamanho = int(cl)
                except Exception:
                    tamanho = -1
                if tamanho < 0 or tamanho > self.teto:
                    return await self._responder(send, 413, {
                        "erro": "corpo do pedido acima do teto do painel "
                                "(%d MB)" % (self.teto // (1024 * 1024))})
            lido = [0]
            teto = self.teto

            async def receber_com_teto():
                msg = await receive()
                if msg.get("type") == "http.request":
                    lido[0] += len(msg.get("body") or b"")
                    if lido[0] > teto:
                        return {"type": "http.disconnect"}
                return msg
            return await self.app(scope, receber_com_teto, send)
        return await self.app(scope, receive, send)


def montar_portao_do_host(aplicacao, porta=None):
    aplicacao.add_middleware(PortaoDoHost, porta=porta)


@app.middleware("http")
async def _portao_do_navegador(request, call_next):
    resposta = await call_next(request)
    tipo = resposta.headers.get("content-type") or ""
    if "text/html" not in tipo.lower():
        return resposta
    fluxo = getattr(resposta, "body_iterator", None)
    if fluxo is None:
        return resposta
    pedacos = []
    async for p in fluxo:
        pedacos.append(p if isinstance(p, bytes) else str(p).encode("utf-8"))
    bruto = b"".join(pedacos)
    try:
        import radai_ui
        corpo = radai_ui.com_portao(bruto.decode("utf-8")).encode("utf-8")
    except Exception:
        corpo = bruto
    from starlette.responses import Response
    nova = Response(content=corpo, status_code=resposta.status_code,
                    media_type=tipo)
    nova.raw_headers = nova.raw_headers + [
        (k, v) for (k, v) in resposta.raw_headers
        if k.lower() not in (b"content-length", b"content-type")]
    nova.background = getattr(resposta, "background", None)
    return nova



PAGE = u"""<!doctype html><html><head><meta charset="utf-8">
<title>Vigia de Segmentação · Radioterapia.AI</title><style>
#pl_fundo{display:none;position:fixed;inset:0;background:rgba(0,0,0,.6);z-index:60}
#pl_cx{display:none;position:fixed;z-index:61;left:50%;top:4vh;
 transform:translateX(-50%);width:min(940px,94vw);max-height:92vh;overflow:auto;
 background:var(--panel,#0c1322);border:1px solid var(--line,#1e293b);
 border-radius:14px;padding:20px 22px}
#pl_cx h3{margin:0 0 4px 0;font-size:17px}
.pl-prep{display:flex;gap:7px;align-items:center;font-size:12px;
 color:var(--text-muted,#8fa3bd);margin-right:auto;cursor:pointer}
.pl-btn{text-align:right;white-space:nowrap}
.pl-tp-cel{white-space:nowrap;min-width:140px}
.pl-tp{display:flex;align-items:center;gap:5px;font-size:11px;margin:0 0 2px;
 color:var(--text,#e6edf7);cursor:pointer}
.pl-tp input{width:auto;margin:0}
.pl-tp-cel .sub{display:block;white-space:normal;max-width:190px;font-size:10px}
.pl-esc{font:inherit;font-size:10.5px;padding:2px 8px;margin-left:4px;
 border-radius:99px;cursor:pointer;border:1px solid var(--line,#1e293b);
 background:transparent;color:var(--text-dim,#72829b)}
.pl-esc:hover{color:var(--text,#e6edf7);border-color:var(--accent,#4DA3FF)}
.pl-esc.on{background:rgba(21,163,74,.18);border-color:var(--ok,#12873F);
 color:var(--text,#e6edf7);font-weight:600}
.pl-esc.off{background:rgba(233,106,92,.16);
 border-color:var(--perigo,#E96A5C);color:var(--text,#e6edf7);
 font-weight:600}
.pl-av{border:1px solid var(--aviso,#E1B23B);background:rgba(225,178,59,.08);border-radius:8px;padding:8px 11px;margin:8px 0;font-size:12.5px}
.pl-loc{display:flex;align-items:center;gap:10px;margin:10px 0 2px}
.pl-loc input{flex:1 1 auto;min-width:0}
.pl-loc .sub{white-space:nowrap}
.pl-resumo{display:flex;gap:8px;flex-wrap:wrap;margin:12px 0}
.pl-resumo .p{border:1px solid var(--line,#1e293b);border-radius:8px;
 padding:7px 11px;font-size:12px}
.pl-resumo .p b{display:block;font-size:17px;font-family:var(--mono,monospace)}
.pl-resumo .p.faz b{color:var(--accent,#4DA3FF)}
.pl-resumo .p.roda b{color:#ffc857}
.pl-resumo .p.falha b{color:#ff6b6b}
.pl-ex{border:1px solid var(--line,#1e293b);border-radius:9px;margin-bottom:8px}
.pl-ex > .cab{padding:8px 11px;font-size:12.5px;border-bottom:1px solid var(--line,#1e293b);
 display:flex;gap:10px;align-items:baseline}
.pl-ex > .cab b{font-size:13px}
.pl-ex table{width:100%;border-collapse:collapse;font-size:11.5px}
.pl-ex td{padding:5px 11px;border-bottom:1px solid rgba(255,255,255,.04)}
.pl-ex tr:last-child td{border-bottom:0}
.pl-ex .num{font-family:var(--mono,monospace);text-align:right;white-space:nowrap}
.pl-tag{font-size:10px;padding:2px 7px;border-radius:99px;border:1px solid var(--line,#1e293b);
 white-space:nowrap}
.pl-tag.faz{border-color:var(--accent,#4DA3FF);color:var(--accent,#4DA3FF);font-weight:600}
.pl-tag.pronto{opacity:.55}
.pl-tag.roda{border-color:#ffc857;color:#ffc857}
.pl-tag.pulado{opacity:.55;font-style:italic}
.pl-tag.falha{border-color:#ff6b6b;color:#ff6b6b}
.pl-conj{border:1px solid var(--line,#1e293b);border-radius:9px;padding:11px 13px;
 margin-bottom:12px}
.pl-cj{display:flex;gap:8px;align-items:flex-start;padding:5px 0;
 border-bottom:1px solid var(--linha-fraca,rgba(255,255,255,.06))}
.pl-cj.off{opacity:.5}
.pl-mk{flex:none;width:14px;text-align:center;font-weight:700}
.pl-cj.off .pl-mk{color:var(--text-dim,#72829b)}
.pl-cj code{font-size:10.5px;opacity:.75}
.pl-conj label{display:flex;gap:8px;align-items:flex-start;margin:6px 0;font-size:12px;
 cursor:pointer}
.pl-conj .aj{display:block;font-size:10.5px;color:var(--text-dim,#72829b);line-height:1.4}
.pl-rodape{display:flex;gap:8px;margin-top:14px;position:sticky;bottom:0;
 background:var(--panel,#0c1322);padding-top:10px}

body{font-family:Segoe UI,Arial;background:var(--bg-0,#060d1a);color:var(--text,#e6edf7);margin:0;padding:18px}
h1{font-size:20px;margin:0 0 2px 0}.a{color:var(--accent,#4DA3FF)}.sub{color:var(--text-muted,#a3b1c6);font-size:12px;margin-bottom:12px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:10px;margin-bottom:12px}
.vg-faixa{display:flex;gap:12px;align-items:stretch;flex-wrap:wrap;
 margin-bottom:12px}
.vg-cartoes{flex:1;min-width:0;margin-bottom:0;
 grid-template-columns:repeat(4,minmax(0,1fr))}
@media (max-width:900px){.vg-cartoes{grid-template-columns:repeat(2,minmax(0,1fr))}}
.vg-acao{display:flex;align-items:center;gap:8px}
.vg-acao button{height:100%;min-height:44px}
.ov-faixa{border:1px solid rgba(129,140,248,.42);
 background:linear-gradient(180deg,rgba(129,140,248,.10),rgba(129,140,248,.03));
 border-radius:12px;padding:12px 14px;margin-bottom:12px}
.ov-topo{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.ov-tit{font-weight:700;font-size:14px;letter-spacing:.2px}
.ov-h{opacity:.75;font-size:12.5px;font-variant-numeric:tabular-nums}
.ov-dir{margin-left:auto;display:flex;gap:8px;align-items:center}
.ov-linha{margin-top:9px;font-size:12.5px;opacity:.9;line-height:1.65}
.ov-chip{display:inline-block;border:1px solid rgba(255,255,255,.16);
 border-radius:999px;padding:1px 9px;margin:2px 5px 2px 0;font-size:11.5px;
 opacity:.85;white-space:nowrap}
.ov-chip.pausado{border-color:rgba(129,140,248,.5)}
.ov-chip.parada{border-color:rgba(255,120,120,.55)}
.ov-chip.eu{border-color:rgba(120,220,160,.55);font-weight:600}
.ov-gira{display:inline-block;width:13px;height:13px;border-radius:50%;
 border:2px solid rgba(129,140,248,.28);border-top-color:rgba(129,140,248,.95);
 animation:ovgira 900ms linear infinite;vertical-align:-2px}
@keyframes ovgira{to{transform:rotate(360deg)}}
@media (prefers-reduced-motion:reduce){.ov-gira{animation:none}}
.ov-pulso{font-variant-numeric:tabular-nums;letter-spacing:1px;opacity:.8}
.vg-semroot{display:flex;gap:10px;align-items:center;flex-wrap:wrap;
 border:1px solid rgba(255,200,87,.4);background:rgba(255,200,87,.06);
 border-radius:10px;padding:11px 13px;margin-bottom:12px;font-size:12.5px;
 line-height:1.55}
.vg-semroot .ic{color:var(--aviso,#E8A33D);flex:0 0 auto}
.vg-semroot button{margin-left:auto}
.card{background:var(--panel,#0c1322);border:1px solid var(--line,#1e293b);border-radius:8px;padding:10px}
.k{color:var(--text-muted,#a3b1c6);font-size:11px}.v{font-size:17px;font-weight:600}.ok{color:#5bd07a}.warn{color:#ffcf66}.err{color:#ff8a7a}
table{width:100%;border-collapse:collapse;font-size:12px}td,th{padding:4px 6px;border-bottom:1px solid var(--panel,#0c1322);text-align:left}
.prog{height:4px;background:var(--panel,#0c1322);border-radius:3px;overflow:hidden;margin-bottom:3px;min-width:70px}
.prog>i{display:block;height:100%;background:var(--accent,#4DA3FF);transition:width .4s}
.sit{font-size:11px;color:var(--text-muted,#a3b1c6);white-space:nowrap}
.sit.run{color:var(--accent,#4DA3FF);font-weight:600}
#log{background:var(--bg-0,#060d1a);border:1px solid var(--line,#1e293b);border-radius:8px;padding:8px;height:260px;overflow:auto;
font-family:Consolas,monospace;font-size:11px;color:var(--text-muted,#a3b1c6);white-space:pre-wrap}
button{background:var(--panel-2,#0f1729);color:var(--text,#e6edf7);border:0;border-radius:6px;padding:8px 14px;margin-right:8px;cursor:pointer}
button.pri{background:var(--ok,#12873F);color:var(--ok-txt,#fff)}
#faixa{display:none;background:#4a3a00;border:1px solid #ffcf66;color:#ffcf66;padding:8px 10px;
border-radius:8px;margin-bottom:12px;font-size:13px}
#alerta{display:none;background:#4a1010;border:1px solid #ff8a7a;color:#ff8a7a;padding:8px 10px;
border-radius:8px;margin-bottom:12px;font-size:13px}
.topo{display:flex;align-items:flex-start;gap:12px;margin-bottom:12px}
.topo>div:first-child{flex:1}
a.menu{text-decoration:none;color:var(--text,#e6edf7);background:var(--panel-2,#0f1729);border:1px solid var(--accent-line,#2a3d57);
border-radius:6px;padding:9px 13px;font-size:12px;white-space:nowrap}
a.menu:hover{background:var(--line-strong,#2a3a55)}
.passo{background:var(--panel,#0c1322);border:1px solid var(--line,#1e293b);border-left:2px solid var(--accent,#4DA3FF);
 border-radius:10px;padding:18px 20px;margin:0 0 16px;max-width:760px}
.passo h2{margin:0 0 8px;font-size:15px;font-weight:600;color:var(--text,#e6edf7)}
.passo p{margin:0 0 13px;font-size:13px;color:var(--text-muted,#a3b1c6);line-height:1.55}
.passo .linha{display:flex;gap:9px;flex-wrap:wrap}
.passo input{flex:1;min-width:300px;background:var(--bg-0,#060d1a);border:1px solid var(--line-strong,#2a3a55);
 border-radius:6px;padding:9px 12px;color:var(--text,#e6edf7);font-family:Consolas,monospace;font-size:12.5px}
.passo input:focus{outline:2px solid var(--accent,#4DA3FF);outline-offset:1px}
.passo .bt{background:var(--panel-2,#0f1729);border:1px solid var(--line-strong,#2a3a55);color:var(--text,#e6edf7);border-radius:6px;
 padding:9px 15px;font-size:13px;cursor:pointer}
.passo .bt:hover{border-color:var(--accent,#4DA3FF);color:var(--accent,#4DA3FF)}
.passo .dica{margin-top:9px;font-size:12px;color:var(--text-dim,#72829b);line-height:1.5}
.passo .erro{margin-top:9px;font-size:12.5px;color:var(--perigo,#E96A5C);line-height:1.5}
.opcoes{gap:7px;display:flex;flex-wrap:wrap}
.opcoes .op{min-width:78px;justify-content:center}
.passo-num{gap:8px;align-items:center;display:flex}
.passo-num .ui-bt{min-width:36px;justify-content:center;font-size:16px;
 line-height:1;padding:6px 0}
.passo-num .ui-bt:disabled{opacity:.35;cursor:not-allowed}
.passo-num .num{font-family:var(--font-mono);font-size:16px;color:var(--text);
 min-width:56px;text-align:center;background:var(--bg-1);
 border:1px solid var(--line);border-radius:var(--r-md);padding:6px 8px}
.ps-corpo label{display:block;font-family:var(--font-mono);font-size:10.5px;
 letter-spacing:.4px;text-transform:uppercase;color:var(--text-dim);
 margin:16px 0 4px}
.ps-corpo .linha{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.ps-corpo .linha input[type=text]{flex:1 1 320px;min-width:220px}
.ps-corpo .dica{margin-top:9px;font-size:12px;color:var(--text-dim);line-height:1.5}
.ps-corpo .erro{margin-top:9px;font-size:12.5px;color:var(--perigo);line-height:1.5}
.rodape-clinico{display:flex;gap:9px;align-items:flex-start;max-width:760px;
 margin:26px 0 10px;padding:10px 13px;font-size:11.5px;line-height:1.55;
 background:var(--fundo-aviso);border:1px solid var(--borda-aviso);
 border-left:3px solid var(--aviso);border-radius:0 var(--r-lg) var(--r-lg) 0;
 color:var(--text-muted)}
.rodape-clinico .ic{color:var(--aviso);font-size:13px;line-height:1.4;flex:0 0 auto}
.rodape-clinico b{color:var(--text);font-weight:600}
.rodape-clinico code{font-family:var(--font-mono);font-size:11px;color:var(--text)}
.ui-alerta{color:var(--aviso);font-size:13px;margin-left:6px;vertical-align:1px}
.fp{margin-top:9px;background:var(--bg-1);border:1px solid var(--line);
 border-radius:var(--r-lg);padding:9px 11px;max-height:250px;overflow:auto}
.fp .fpcam{font-family:var(--font-mono);font-size:11px;color:var(--text-dim);
 margin-bottom:7px;word-break:break-all}
.fp .fpi{display:block;width:100%;text-align:left;padding:5px 7px;
 border-radius:var(--r-sm);font-family:var(--font-mono);font-size:12px;
 color:var(--text);cursor:pointer;border:none;background:none;letter-spacing:0}
.fp .fpi:hover{background:var(--panel-2);color:var(--text)}
.fp .fpi.drv{display:inline-block;width:auto;
 border:1px solid var(--line-strong);margin:0 5px 6px 0}
</style></head><body>
<header class="rc-topo"><a class="rc-marca" href="/" title="Radioterapia.AI Local"><span class="rc-nome">radioterapia<span class="g">.ai</span></span><span class="rc-sub" data-radai-frase>Local Suite</span></a><span class="rc-seta">&#8594;</span><span class="rc-tela">Vigia de Segmentação</span><div class="dir"><a class="rc-voltar" href="/">&#8592; Voltar ao menu</a></div></header>
<div class="topo">
 <div class="rc-capa rc-compacta">
  <span class="rc-chip"><i>◐</i> Estação</span>
  <h1 data-radai-frase>Fila de estudo</h1>
  <p class="rc-frase"><span data-radai-frase>o lote automático da noite,
   nesta máquina</span> <b id="mach"></b></p>
 </div>
</div>

<div class="vg-faixa">
 <div class="grid vg-cartoes">
  <div class="card"><div class="k">Estado</div><div class="v" id="st">—</div></div>
  <div class="card"><div class="k">Na fila</div><div class="v" id="nq">—</div></div>
  <div class="card"><div class="k">Concluídas (sessão)</div><div class="v ok" id="done">0</div></div>
  <div class="card"><div class="k">Última varredura</div><div class="v" id="scan">—</div></div>
 </div>
 <div class="vg-acao"><button class="pri" id="btLiga"></button><button id="btDesliga" style="display:none" onclick="if(confirm('Desligar a fila devolve a estacao para as outras telas.

A serie em curso TERMINA; nenhuma nova comeca.

Desligar?')) act('vigia/desligar')">@ICO_POWER@<span data-radai-frase>Desligar a fila</span></button><button id="btNoite" title="Dedica esta estação à noite: liga a fila, pausa os serviços que disputam memória e passa a pegar o caso mais recente primeiro." onclick="noiteIniciar()">@ICO_LUA@Iniciar overnight run</button></div>
</div>

<div class="ov-faixa" id="ovFaixa" style="display:none">
 <div class="ov-topo">
  <span class="ov-gira" id="ovGira"></span>
  <span class="ov-tit">OVERNIGHT RUN</span>
  <span class="ov-h" id="ovH"></span>
  <span class="ov-pulso" id="ovPulso">⠋</span>
  <span class="ov-dir">
   <button id="btNoiteFim" onclick="noiteEncerrar()">@ICO_SOL@<span data-radai-frase>Encerrar overnight run</span></button>
  </span>
 </div>
 <div class="ov-linha" id="ovServicos"></div>
 <div class="ov-linha" id="ovFrota"></div>
</div>

<div id="faixa"></div>
<div id="alerta"></div>

<div class="vg-semroot" id="semRoot" style="display:none">
 <span class="ic">&#9888;</span>
 <span><b data-radai-frase>A pasta dos exames ainda não foi apontada.</b>
  <span data-radai-frase>Sem ela o vigia sobe, mostra este painel e não toca
  em nada — que é o estado normal de quem acabou de instalar.</span></span>
 <button class="ui-bt" onclick="abrirPasso1()"
  data-radai-frase>Apontar a pasta</button>
</div>
<section class="ps-cx fechado" id="cx1">
 <h2 class="ps-cab" tabindex="0" role="button"><span class="ps-num">1</span>
  <span data-radai-frase>Pasta dos exames</span>
  <span class="ps-sub" id="subPasta"></span><span class="ui-ajuda" tabindex="0" aria-label="ajuda">?<span class="ui-balao"><p>O vigia varre esta pasta e grava o RTSTRUCT ao lado de cada série.</p><p><b>Testar</b> só confere: existe, lê, escreve. <b>Aplicar</b> grava.</p><p>A pasta passa a valer no próximo arranque do vigia.</p></span></span>
  <span class="ps-seta">&#9662;</span></h2>
 <div class="ps-corpo">
  <div class="linha">
   <input type="text" id="rootIn" spellcheck="false"
          placeholder="\\\\servidor\\compartilhamento\\Pacientes">
   <button class="ui-bt" id="btPastas">@ICO_PASTA@<span data-radai-frase>Procurar…</span></button>
   <button class="ui-bt" id="btTestar" data-radai-frase>Testar</button>
   <button class="ui-bt pri" id="btRoot" data-radai-frase>Aplicar</button>
  </div>
  <div class="fp" id="fpVigia" style="display:none"></div>
  <div class="dica" id="rootDica"></div>
  <div class="erro" id="rootErro"></div>
 </div>
</section>

<section class="ps-cx fechado" id="cx2">
 <h2 class="ps-cab" tabindex="0" role="button"><span class="ps-num">2</span>
  <span data-radai-frase>O que varrer</span>
  <span class="ps-sub" id="subVarrer"></span><span class="ui-ajuda" tabindex="0" aria-label="ajuda">?<span class="ui-balao"><p>O que entra na fila. <b>CT</b> é o normal; <b>MR</b> só se o serviço contornar em ressonância.</p><p>Salvar aqui grava no mesmo arquivo da tela de Configurações.</p></span></span>
  <span class="ps-seta">&#9662;</span></h2>
 <div class="ps-corpo">
  <label data-radai-frase>Modalidade</label>
  <div class="linha opcoes" id="opMod">
   <button class="ui-bt op" data-mod="CT">CT</button>
   <button class="ui-bt op" data-mod="MR" id="opMR">MR</button>
   <button class="ui-bt op" data-mod="CT,MR" id="opCTMR" data-radai-frase>CT e MR</button>
   <span id="avisoMR" style="display:none"><span class="ui-alerta">&#9888;</span><span class="ui-ajuda" tabindex="0" aria-label="ajuda">?<span class="ui-balao"><p><b>Não há biblioteca de ressonância neste pacote.</b> Marcar MR faria o vigia varrer, achar séries e falhar em todas.</p><p>Para habilitar, o pacote precisa ser montado com uma tarefa que leia MR (por exemplo <code>total_mr</code>) — é uma troca de pacote, não uma opção de configuração. Fale com quem preparou a instalação.</p></span></span></span>
  </div>

  <label><span data-radai-frase>Dias para trás</span><span class="ui-ajuda" tabindex="0" aria-label="ajuda">?<span class="ui-balao"><p>Só séries dos últimos N dias. <b>0 = sem limite.</b></p><p>Comece curto: um número alto na primeira noite põe o acervo inteiro na fila de uma vez.</p></span></span></label>
  <div class="linha passo-num">
   <button class="ui-bt" data-num="cfgDIAS" data-d="-1">&#8722;</button>
   <span class="num" id="vDIAS">0</span>
   <button class="ui-bt" data-num="cfgDIAS" data-d="1">+</button>
   <input type="hidden" id="cfgDIAS" value="0">
  </div>

  <label><span data-radai-frase>Mínimo de cortes</span><span class="ui-ajuda" tabindex="0" aria-label="ajuda">?<span class="ui-balao"><p>Abaixo disto a série é ignorada.</p><p>O botão não desce abaixo de 20: mais baixo põe localizador e captura de tela na fila, e o modelo devolve contorno para elas.</p></span></span></label>
  <div class="linha passo-num">
   <button class="ui-bt" data-num="cfgMIN" data-d="-1">&#8722;</button>
   <span class="num" id="vMIN">20</span>
   <button class="ui-bt" data-num="cfgMIN" data-d="1">+</button>
   <input type="hidden" id="cfgMIN" value="20">
  </div>

  <div class="linha" style="margin-top:16px">
   <button class="ui-bt pri" id="btVarrer" data-radai-frase>Salvar</button>
   <span class="dica" id="varrerMsg"></span></div>
 </div>
</section>

<section class="ps-cx fechado" id="cx3">
 <h2 class="ps-cab" tabindex="0" role="button"><span class="ps-num">3</span>
  <span data-radai-frase>Fila e andamento</span>
  <span class="ps-sub" id="subFila"></span><span class="ui-ajuda dir" tabindex="0" aria-label="ajuda">?<span class="ui-balao"><p>Séries novas primeiro; esgotadas, o backlog da mais recente para trás.</p><p>Duas máquinas na mesma rede não pegam a mesma série: cada pasta de paciente ganha marcadores numa subpasta <b>_RadAI</b>.</p><p>O log mostra o identificador do paciente e os 8 últimos dígitos do UID — o suficiente para achar a série, e não mais que isso.</p></span></span>
  <span class="ps-seta">&#9662;</span></h2>
 <div class="ps-corpo">
<div class="grid" id="grade" style="grid-template-columns:1fr">
 <div class="card"><div class="k">Série atual</div><div class="v" id="cur">—</div></div>
</div>
<div style="margin-bottom:10px">
<div id="pl_fundo" onclick="planoFechar()"></div>
<div id="pl_cx" role="dialog" aria-labelledby="pl_tit">
 <h3 id="pl_tit">O vigia está pronto para iniciar</h3>
 <p class="sub" id="pl_sub">Revise as ações antes de começar. Nada foi
  reivindicado ainda.</p>
 <div id="pl_resumo" class="pl-resumo"></div>
 <div id="pl_avisos"></div>
 <div id="pl_conj"></div>
 <div class="pl-loc"><input id="pl_loc" spellcheck="false"
  oninput="planoFiltrar()" placeholder="localizar &mdash; trecho da pasta,
  do prontu&aacute;rio, da data ou da descri&ccedil;&atilde;o">
  <span class="sub" id="pl_loc_conta"></span></div>
 <div id="pl_corpo"></div>
 <div class="pl-rodape">
  <label class="pl-prep"><input type="checkbox" id="pl_prep">
   <span>preparar a esta&ccedil;&atilde;o antes (parar servi&ccedil;os da lista e limpar cache)</span></label>
  <button class="pri" id="pl_ok" onclick="planoConfirmar()">Começar</button>
  <button onclick="planoFechar()">Cancelar</button>
 </div>
</div>
 <button onclick="act('rescan')"
  title="Relê as pastas de pacientes e refaz a fila agora, sem esperar o intervalo normal de varredura. Não reprocessa nada: só atualiza a lista.">↻ Atualizar a fila agora</button>
</div>
<div class="grid" style="grid-template-columns:1.2fr 1fr">
 <div class="card"><div class="k" style="margin-bottom:4px">Fila de trabalho</div>
  <table id="tq"><tr><th>Paciente</th><th>Data</th><th>Cortes</th><th>Série</th><th>Situação</th></tr></table></div>
 <div class="card"><div class="k" style="margin-bottom:4px">Falhas recentes</div>
  <table id="tf"><tr><th>Série</th><th>Erro</th></tr></table></div>
</div>
 </div>
</section>
<div class="rodape-clinico">
 <span class="ic">&#9888;</span>
 <span>Tudo o que o vigia grava sai como <b>sugestão não aprovada</b>
 (<code>ApprovalStatus = UNAPPROVED</code>). Revisar e aprovar é ato médico —
 nenhuma estrutura aqui entra em plano sem passar por isso.</span>
</div>
<script>
var PULADAS=0;
var ROOT_SUGERIDO=0;

function gravarRoot(v, confirmado){
 return fetch('/api/config',{method:'POST',
  headers:{'Content-Type':'application/json'},
  body:JSON.stringify({valores:{ROOT:v}, confirmar_root:!!confirmado})})
  .then(function(r){return r.json()});
}

function salvarRoot(gravar){
 var v=(document.getElementById('rootIn').value||'').trim();
 var er=document.getElementById('rootErro'); er.textContent='';
 var di=document.getElementById('rootDica'); di.textContent='';
 var b=document.getElementById(gravar?'btRoot':'btTestar');
 var rot=b.textContent;
 if(!v){ er.textContent='Informe a pasta.'; return; }
 b.textContent='conferindo...';
 fetch('/api/config/testar',{method:'POST',headers:{'Content-Type':'application/json'},
  body:JSON.stringify({caminho:v})})
 .then(function(r){return r.json()}).then(function(t){
  if(t && t.existe===false){ b.textContent=rot;
   er.textContent='A pasta nao existe ou nao esta acessivel desta maquina.'; return; }
  if(t && t.escreve===false){ b.textContent=rot;
   er.textContent='Sem permissao de ESCRITA nessa pasta \u2014 o RTSTRUCT precisa ser gravado ao lado da serie.'; return; }
  if(!gravar){ b.textContent=rot;
   di.textContent='A pasta existe, le e escreve. Clique em Aplicar: o vigia passa a varre-la na proxima serie.';
   return; }
  return gravarRoot(v, false).then(function(s){
    if(s && s.precisa_confirmar){
     var L=s.validacao||{};
     var ok=confirm(
      'Apontar o vigia para outra pasta?\\n\\n'+
      'de:   '+(s.root_atual||'(vazio)')+'\\n'+
      'para: '+(s.root_novo||'(vazio)')+'\\n\\n'+
      'Laudo do caminho: '+(L.existe?'existe':'NAO EXISTE')+
       ', '+(L.leitura?'le':'NAO LE')+', '+(L.escrita?'escreve':'NAO ESCREVE')+'.\\n\\n'+
      'E dessa pasta que sai a fila da noite.\\n\\n'+
      'Ela passa a valer na proxima serie: uma segmentacao em curso '+
      'termina na pasta antiga.\\n\\nConfirma?');
     if(!ok){ b.textContent=rot; er.textContent='Nada foi gravado.'; return null; }
     return gravarRoot(v, true);
    }
    return s;
   }).then(function(s){
    if(s===null) return;
    b.textContent=rot;
    if(!s || !s.ok){ er.textContent=(s&&s.erro)||'Nao consegui gravar.'; return; }
    mostrarPasta(v);
    di.textContent='Gravado. Pedindo a recarga...';
    return fetch('/api/reiniciar',{method:'POST'})
     .then(function(r){return r.json()})
     .then(function(rc){
      di.textContent = (rc && rc.ok)
       ? ('Aplicado. Vale ' + (rc.quando || 'na proxima serie') +
          ' \u2014 uma segmentacao em curso termina na pasta antiga.')
       : ('Gravado no arquivo, mas nao consegui pedir a recarga' +
          ((rc && rc.erro) ? (': ' + rc.erro) : '') +
          '. Feche e reabra o programa para a pasta nova valer.');
      upd();
     })
     .catch(function(e){
      di.textContent='Gravado no arquivo, mas nao consegui pedir a recarga: '+e;
      upd();
     });
   });
 }).catch(function(e){ b.textContent=rot;
  er.textContent='Nao consegui conferir a pasta: '+e; });
}
function mostrarPasta(v){
 v=(v||'').trim();
 var a=document.getElementById('subPasta');
 if(a) a.textContent = v ? ('— ' + v) : '— nenhuma pasta configurada';
}
var GRAVADO = '';
function estadoVarrer(){
 return modAtual() + '|' + document.getElementById('cfgDIAS').value
        + '|' + document.getElementById('cfgMIN').value;
}
function resumirVarrer(){
 var e=document.getElementById('subVarrer'); if(!e) return;
 var d=document.getElementById('cfgDIAS').value;
 var t = '— ' + modAtual() + ' · '
  + (d==='0' ? 'sem limite de dias' : d + (d==='1' ? ' dia' : ' dias'))
  + ' · min ' + document.getElementById('cfgMIN').value + ' cortes';
 if(GRAVADO && estadoVarrer()!==GRAVADO) t += '  · não salvo';
 e.textContent = t;
}

var PISO={cfgDIAS:0, cfgMIN:20}, TETO={cfgDIAS:3650, cfgMIN:9999};
var VISOR={cfgDIAS:'vDIAS', cfgMIN:'vMIN'};
var CHAVE={cfgDIAS:'DAYS_BACK', cfgMIN:'MIN_SLICES'};
function porNum(id,n,doArquivo){
 var v=Math.max(PISO[id], Math.min(TETO[id], Math.round(n)||0));
 if(doArquivo && v!==n){
  document.getElementById('varrerMsg').textContent =
   'O radai_watcher.config tem '+CHAVE[id]+'='+n+', fora da faixa permitida. '+
   'A tela mostra '+v+'; clique em Salvar para o arquivo passar a dizer o mesmo.';
 }
 document.getElementById(id).value=String(v);
 document.getElementById(VISOR[id]).textContent=String(v);
 var mn=document.querySelector('[data-num="'+id+'"][data-d="-1"]');
 if(mn) mn.disabled = (v<=PISO[id]);
 resumirVarrer();
}
document.addEventListener('click', function(ev){
 var b=ev.target.closest('[data-num]'); if(!b) return;
 var id=b.getAttribute('data-num');
 porNum(id, (parseInt(document.getElementById(id).value,10)||0)
            + parseInt(b.getAttribute('data-d'),10));
});
var MR_OK = true;
function temMR(ok){
 MR_OK = !!ok;
 var a=document.getElementById('avisoMR');
 if(a) a.style.display = ok ? 'none' : '';
 ['opMR','opCTMR'].forEach(function(id){
  var b=document.getElementById(id); if(!b) return;
  b.classList.toggle('desligado', !ok);
  b.disabled = !ok;
 });
 if(!ok && modAtual()!=='CT'){ porMod('CT'); }
}

function porMod(v){
 v=(v||'CT').toUpperCase().split(/[,;\\s]+/).filter(function(x){return x;})
   .sort().join(',');
 if(v!=='CT' && v!=='MR' && v!=='CT,MR') v='CT';   // valor estranho no config
 var bs=document.querySelectorAll('#opMod .op');   // volta ao normal, visivel
 for(var i=0;i<bs.length;i++)
  bs[i].classList.toggle('lig', bs[i].getAttribute('data-mod')===v);
 resumirVarrer();
}
function modAtual(){
 var b=document.querySelector('#opMod .op.lig');
 return b ? b.getAttribute('data-mod') : 'CT';
}
document.addEventListener('click', function(ev){
 var b=ev.target.closest('#opMod .op'); if(!b) return;
 if(b.disabled) return;                 // opção apagada não responde
 porMod(b.getAttribute('data-mod'));
});

function carregarVarrer(){
 fetch('/api/config').then(function(r){return r.json()}).then(function(d){
  var v=(d && d.valores) || {};
  var r=(v.ROOT||'').trim();
  var e=document.getElementById('rootIn'); if(e && !e.value) e.value=r;
  mostrarPasta(r);
  porMod(v.MODALITIES);
  porNum('cfgDIAS', v.DAYS_BACK==null||v.DAYS_BACK===''
          ? 0 : (parseInt(v.DAYS_BACK,10)||0), true);
  porNum('cfgMIN',  v.MIN_SLICES==null||v.MIN_SLICES===''
          ? 20 : (parseInt(v.MIN_SLICES,10)||0), true);
  GRAVADO = estadoVarrer();      // a referencia do "não salvo" vem do disco
  resumirVarrer();
  if(r){ psFechar('cx1'); } else { psAbrir('cx1'); psFechar('cx3'); }
 }).catch(function(){});
}

function salvarVarrer(){
 var m=document.getElementById('varrerMsg'); m.textContent='salvando...';
 var vals={MODALITIES:modAtual(),
           DAYS_BACK:(document.getElementById('cfgDIAS').value||'0'),
           MIN_SLICES:(document.getElementById('cfgMIN').value||'20')};
 fetch('/api/config',{method:'POST',headers:{'Content-Type':'application/json'},
  body:JSON.stringify({valores:vals})})
 .then(function(r){return r.json()}).then(function(s){
  m.textContent = s.ok ? 'Gravado. Vale no pr\u00f3ximo arranque do vigia.'
                       : (s.erro||'Nao consegui gravar.');
  if(s.ok) GRAVADO = estadoVarrer();
  resumirVarrer(); upd();
 }).catch(function(e){ m.textContent='Nao consegui gravar: '+e; });
}

function act(a){fetch('/api/'+a,{method:'POST'}).then(upd)}

function noiteIniciar(){
 uiPainel({
  titulo:'Dedicar esta estacao a noite?',
  ok:'Dedicar a noite',
  html:'<ul><li>a fila liga e passa a pegar o <b>caso mais recente</b> '
   +'primeiro</li>'
   +'<li>os servicos do Windows que disputam memoria sao pausados</li>'
   +'<li>as outras telas da suite ficam trancadas ate voce encerrar</li></ul>'
   +'<p>Ao encerrar, os servicos voltam ao estado em que estavam.</p>',
  aoSim:function(){
 fetch('/api/overnight/iniciar',{method:'POST'}).then(r=>r.json()).then(d=>{
  if(d && d.ok===false && d.erro) alert(d.erro);
  upd(); noiteFrota();
 }).catch(function(){ if(window.uiConexao) uiConexao(false) });
  }});
}
function noiteEncerrar(){
 uiPainel({
  titulo:'Encerrar o overnight run?',
  ok:'Encerrar o turno',
  html:'<p>A serie em curso <b>termina</b>; nenhuma nova comeca.</p>'
   +'<p>Os servicos pausados voltam ao estado em que estavam.</p>',
  aoSim:function(){
 fetch('/api/overnight/encerrar',{method:'POST'}).then(r=>r.json()).then(d=>{
  if(d && d.falhas && d.falhas.length)
   alert('Encerrado. Estes nao voltaram agora e voltam no proximo arranque '
    +'da estacao:\\n\\n' + d.falhas.join('\\n'));
  upd();
 }).catch(function(){ if(window.uiConexao) uiConexao(false) });
  }});
}

var OV_PULSO = ['⠋','⠙','⠹','⠸','⠼','⠴',
                '⠦','⠧','⠇','⠏'];
var _ovI = 0;
setInterval(function(){
 var e = document.getElementById('ovPulso');
 if(e && e.offsetParent !== null){ _ovI = (_ovI+1) % OV_PULSO.length;
  e.textContent = OV_PULSO[_ovI]; }
}, 120);

function noiteFrota(){
 var box = document.getElementById('ovFrota');
 if(!box) return;
 fetch('/api/overnight/frota').then(r=>r.json()).then(d=>{
  if(d.configurado===false){ uiHTML(box,
   '<span style="opacity:.7" data-radai-frase>' + (d.aviso||'') + '</span>');
   return; }
  var ms = d.maquinas||[], r = d.resumo||{};
  if(!ms.length){ uiHTML(box,
   '<span style="opacity:.7" data-radai-frase>'
   + 'Nenhuma estação escreveu status ainda.</span>');
   return; }
  var h = '<b data-radai-frase>Frota:</b> ' + r.n
        + ' <span data-radai-frase>estação(ões)</span> · ' + r.trabalhando
        + ' <span data-radai-frase>segmentando</span> · ' + r.concluidas
        + ' <span data-radai-frase>série(s) concluída(s) esta sessão</span>'
        + (r.paradas ? ' · ' + r.paradas
           + ' <span data-radai-frase>sem sinal</span>' : '')
        + '<br>';
  ms.forEach(function(m){
   var cls = 'ov-chip' + (m.eu?' eu':'') + (m.parada?' parada':'');
   var det = !m.legivel ? '<span data-radai-frase>ilegível</span>'
     : (m.parada ? '<span data-radai-frase>sem sinal há</span> '
                   + Math.round(m.muda_min) + ' min'
        : (m.atual ? '<span data-radai-frase>segmentando</span>'
           : (m.pausado ? '<span data-radai-frase>pausada</span>'
              : '<span data-radai-frase>ociosa</span>')));
   h += '<span class="'+cls+'">' + (m.maquina||'?') + ' · ' + det
     + ' · ' + (m.concluidas||0) + '✓</span>';
  });
  uiHTML(box, h);
 }).catch(function(){});
}
setInterval(function(){
 var f = document.getElementById('ovFaixa');
 if(f && f.style.display !== 'none') noiteFrota();
}, 30000);
function liberar(){
 if(!confirm('Apagar o marcador de falha de '+PULADAS+' serie(s) e tentar de novo?\\n\\n'
  +'Faca isto DEPOIS de corrigir a causa (Python errado, permissao no share, GPU fora),'
  +' senao elas vao falhar de novo.')) return;
 fetch('/api/liberar_falhas',{method:'POST'}).then(upd);
}
function esc(s){return String(s==null?'':s).replace(/&/g,'&amp;').replace(/</g,'&lt;')
 .replace(/>/g,'&gt;').replace(/"/g,'&quot;');}
function dur(s){s=Math.max(0,parseInt(s,10)||0);
 if(s<60) return s+'s';
 var m=Math.floor(s/60); return m<60 ? (m+'min') : (Math.floor(m/60)+'h'+('0'+(m%60)).slice(-2));}
function planoFechar(){
 document.getElementById('pl_fundo').style.display='none';
 document.getElementById('pl_cx').style.display='none';
}
function planoConfirmar(){
 var prep = document.getElementById('pl_prep');
 if(!prep || !prep.checked){ planoFechar(); filaComecar(); return; }
 var bt = document.getElementById('pl_ok');
 bt.disabled = true; bt.textContent = 'preparando a estacao...';
 fetch('/api/limpador', {method:'POST'}).then(function(r){return r.json()})
 .then(function(d){
  var passos = (d.servicos||[]).filter(function(x){return x.estado==='rodando'})
    .map(function(x){ return fetch('/api/limpador/parar', {method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({nome:x.nome})}); });
  passos = passos.concat((d.recuperavel||[])
    .filter(function(i){ return i.apagavel && i.sugerido })
    .map(function(i){ return fetch('/api/limpador/liberar', {method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({chave:i.chave})}); }));
  return Promise.all(passos);
 }).catch(function(){ /* preparar e um extra: falhar aqui nao pode custar
    a noite inteira, e o lote roda igual numa maquina nao preparada. */ })
 .then(function(){ planoFechar(); filaComecar(); });
}

function filaComecar(){
 var rota = window._ligado ? 'resume' : 'vigia/ligar';
 fetch('/api/'+rota, {method:'POST'}).then(function(r){return r.json()})
 .then(function(d){
  if(d && d.ok === false && (d.erro || d.ambiente_erro))
   alert(d.erro || d.ambiente_erro);
  upd();
 }).catch(function(){ if(window.uiConexao) uiConexao(false) });
}

function planoDecidir(ev){
 var b = ev.target.closest && ev.target.closest('[data-dec]');
 if(!b) return;
 var jaEsta = b.classList.contains('on') || b.classList.contains('off');
 var dec = jaEsta ? '' : b.getAttribute('data-dec');
 b.disabled = true;
 fetch('/api/fila/decidir', {method:'POST',
   headers:{'Content-Type':'application/json'},
   body: JSON.stringify({uid:b.getAttribute('data-uid'), decisao:dec})})
 .then(function(r){return r.json()}).then(function(){
  fetch('/api/vigia/plano').then(function(r){return r.json()}).then(planoPintar);
 }).catch(function(){ b.disabled = false; });
}
function planoAbrir(){
 var f=document.getElementById('pl_fundo'), c=document.getElementById('pl_cx');
 f.style.display='block'; c.style.display='block';
 document.getElementById('pl_corpo').innerHTML='<p class="sub">varrendo a pasta…</p>';
 document.getElementById('pl_resumo').innerHTML='';
 document.getElementById('pl_conj').innerHTML='';
 var _pc = document.getElementById('pl_corpo');
 if(_pc && !_pc.dataset.ligado){ _pc.addEventListener('click', planoDecidir);
                                 _pc.dataset.ligado = '1'; }
 fetch('/api/vigia/plano').then(function(r){return r.json()}).then(planoPintar)
  .catch(function(e){
   document.getElementById('pl_corpo').innerHTML=
    '<p class="sub" style="color:#ff6b6b">nao consegui montar o plano: '+esc(e)+'</p>';
  });
}
var PLANO = null;
function planoNorm(t){
 t = String(t==null?'':t).toLowerCase();
 try{ t = t.normalize('NFD').replace(/[\\u0300-\\u036f]/g, '') }catch(e){}
 return t;
}
function planoCasa(e, x){
 var q = planoNorm((document.getElementById('pl_loc')||{}).value||'').trim();
 if(!q) return true;
 var alvo = planoNorm([e.pasta, e.pid, e.date,
                       (x ? [x.detalhe, x.cortes, x.espessura_mm].join(' ') : '')
                      ].join(' · '));
 return q.split(/\\s+/).every(function(t){ return alvo.indexOf(t) >= 0 });
}
function planoFiltrar(){ if(PLANO) planoPintar(PLANO) }

var PL_TOPOS = [{cod:'total', rotulo:'Total'},
                {cod:'cabeca_pescoco', rotulo:'Cabeça e pescoço'}];
document.addEventListener('change', function(ev){
 var el = ev.target;
 if(!el || !el.getAttribute) return;
 var uid = el.getAttribute('data-tp-uid');
 if(uid === null) return;
 var cod = el.getAttribute('data-tp-cod');
 if(cod === 'total') return;                 // a base nao se desmarca
 var linha = el.closest('tr');
 var marcadas = [].filter.call(linha.querySelectorAll('input[data-tp-uid]'),
                               function(c){return c.checked})
                 .map(function(c){return c.getAttribute('data-tp-cod')});
 if(marcadas.indexOf('total') < 0) marcadas.unshift('total');
 fetch('/api/fila/topografia', {method:'POST',
   headers:{'Content-Type':'application/json'},
   body: JSON.stringify({uid:uid, topo:marcadas})})
  .then(function(r){return r.json()})
  .then(function(){ planoAbrir() })
  .catch(function(){});
});

function planoPintar(d){
 PLANO = d;
 var r=d.resumo||{};
 document.getElementById('pl_resumo').innerHTML =
   '<div class="p faz"><b>'+(r.a_fazer||0)+'</b>vão ser contornadas</div>'
  +'<div class="p"><b>'+(r.prontos||0)+'</b>já prontas</div>'
  +'<div class="p roda"><b>'+(r.rodando||0)+'</b>rodando em outra máquina</div>'
  +'<div class="p"><b>'+(r.pulados||0)+'</b>puladas (outra série do exame)</div>'
  +((r.nao_simulacao||0)?('<div class="p"><b>'+r.nao_simulacao
     +'</b>não são a TC de simulação'
     +'<span class="ui-ajuda" tabindex="0" aria-label="ajuda">?'
     +'<span class="ui-balao"><p>O vigia contorna <b>uma série por'
     +' exame</b>: a TC de simulação, que é a mais grossa a partir de'
     +' 1 mm — 5 mm, depois 3,75, depois 2, depois 1.</p>'
     +'<p>Reconstrução abaixo de 1 mm não é simulação, e exame que só'
     +' tenha séries finas não entra na fila.</p>'
     +'<p>Para contornar qualquer outra, use o <b>Rodar agora</b>: lá'
     +' a espessura não filtra nada e quem escolhe é você.</p>'
     +'</span></span></div>'):'')
  +((r.em_transito||0)?('<div class="p roda"><b>'+r.em_transito
     +'</b>ainda chegando no servidor</div>'):'')
  +'<div class="p falha"><b>'+(r.falhados||0)+'</b>falharam 3 vezes</div>'
  +(d.estimativa?('<div class="p"><b>'+esc(d.estimativa)+'</b>tempo provavel'
    +'<span class="ui-ajuda" tabindex="0" aria-label="ajuda">?'
    +'<span class="ui-balao"><p>Sai de <b>dois pontos de medicao</b> nesta'
    +' familia de estacao, e do processamento em <b>'+esc(d.device||'?')
    +'</b>.</p><p>Numa maquina ocupada ela erra por um fator: serve para'
    +' planejar a noite, nao para prometer hora.</p>'
    +((d.estimativa_regiao||[]).length?'<p>O primeiro número é só a base; o segundo, a base mais todas as tasks de região que a anatomia pode acrescentar depois dela.</p>':'')
    +'</span></span></div>'):'');

 var est=d.estacao||{}, mem=est.memoria||{}, av=[];
 if(mem.total_mb && mem.livre_mb < 4000) av.push('Memoria livre baixa: '
   +mem.livre_mb+' MB. Ver Configuracoes, Otimizar processamento.');
 (est.disco||[]).forEach(function(u){ if(u.aperta) av.push('Pouco espaco em '
   +u.unidade+': '+u.livre_gb+' GB livres.'); });
 (est.ganhos||[]).forEach(function(g){
   if(g.chave==='gpu' && g.onde) av.push(g.detalhe+' '+g.onde+'.');
   if(g.chave==='energia') av.push(g.rotulo+'. '+g.detalhe);
 });
 var pa=document.getElementById('pl_avisos');
 if(pa) pa.innerHTML = av.length
   ? av.map(function(x){return '<div class="pl-av">! '+esc(x)+'</div>'}).join('')
   : '';

 var lig=(d.conjuntos||[]).filter(function(c){return c.marcado}).length;
 var cj=(d.conjuntos||[]).map(function(c){
  var on=!!c.marcado;
  return '<div class="pl-cj'+(on?'':' off')+'">'
   +'<span class="pl-mk">'+(on?'✓':'✕')+'</span>'
   +'<span><b>'+esc(c.nome)+'</b>'+(c.entregue?' — vai para o TPS':'')
   +(on?'':' — desligado')
   +(c.chave?(' <code>'+esc(c.chave)+'</code>'):'')
   +(c.decide?(' <span class="aj">'+esc(c.decide)+'</span>'):'')
   +'<span class="aj">'+esc(c.ajuda||'')+'</span></span></div>';
 }).join('');
 var NOM=['nenhum','Um','Dois','Tres','Quatro','Cinco','Seis','Sete',
          'Oito','Nove','Dez'];
 document.getElementById('pl_conj').innerHTML =
  '<div class="pl-conj"><b style="font-size:12px">O que vai ser gravado por série</b>'
  +'<p class="sub" style="margin:4px 0 8px 0">'
  +(NOM[lig]||lig)+' arquivo'+(lig===1?'':'s')+' ao lado dos DICOMs. '
  +'Só o primeiro vai para o TPS. '
  +'Para ligar ou desligar um deles, ⚙ Configurações.</p>'+cj+'</div>';

 if(d.erro){
  document.getElementById('pl_corpo').innerHTML=
   '<p class="sub" style="color:#ff6b6b">'+esc(d.erro)+'</p>';
  document.getElementById('pl_ok').disabled=true;
  return;
 }
 document.getElementById('pl_ok').disabled=false;
 var ROT={a_fazer:['faz','vai contornar'],pronto:['pronto','já contornada'],
          rodando:['roda','rodando agora'],pulado:['pulado','fica de fora'],
          em_transito:['roda','ainda chegando'],
          falhado:['falha','falhou 3x']};
 var visiveis = 0, total = 0;
 var h=(d.exames||[]).map(function(e){
  var exameCasa = planoCasa(e, null);
  var ss = (e.series||[]).filter(function(x){
   total++;
   var ok = exameCasa || planoCasa(e, x);
   if(ok) visiveis++;
   return ok;
  });
  if(!ss.length) return '';
  var linhas=ss.map(function(x){
   var t=ROT[x.estado]||['','?'];
   if(x.decisao === 'incluir') t = ['faz','você escolheu'];
   else if(x.decisao === 'pular') t = ['pulado','você descartou'];
   var bt = (x.estado === 'pronto' || x.estado === 'rodando') ? ''
    : ('<button class="pl-esc'+(x.decisao==='incluir'?' on':'')+'"'
       +' data-dec="incluir" data-uid="'+esc(x.uid)+'"'
       +' title="contornar esta série nesta noite">incluir</button>'
      +'<button class="pl-esc'+(x.decisao==='pular'?' off':'')+'"'
       +' data-dec="pular" data-uid="'+esc(x.uid)+'"'
       +' title="deixar esta série de fora">pular</button>');
   var tp = (x.topo && x.topo.length) ? x.topo : ['total'];
   var cxs = PL_TOPOS.map(function(o){
    var base = (o.cod === 'total');
    return '<label class="pl-tp"><input type="checkbox"'
     +((tp.indexOf(o.cod)>=0)?' checked':'')
     +(base?' disabled':'')
     +' data-tp-uid="'+esc(x.uid)+'"'
     +' data-tp-cod="'+o.cod+'"> '+esc(o.rotulo)+'</label>'}).join('');
   return '<tr><td class="num">'+x.cortes+' cortes</td>'
    +'<td class="num">'+(x.espessura_mm==null?'—':x.espessura_mm+' mm')+'</td>'
    +'<td><span class="pl-tag '+t[0]+'">'+t[1]+'</span></td>'
    +'<td class="sub">'+esc(x.detalhe||'')+'</td>'
    +'<td class="pl-tp-cel">'+cxs
    +((x.topo_motivo && tp.indexOf('cabeca_pescoco')>=0)
      ? ('<span class="sub">'+esc(x.topo_motivo)+'</span>') : '')+'</td>'
    +'<td class="pl-btn">'+bt+'</td></tr>';
  }).join('');
  return '<div class="pl-ex"><div class="cab"><b>'+esc(e.pasta)+'</b>'
   +'<span class="sub">'+esc(e.pid||'')+(e.date?(' · '+esc(e.date)):'')+'</span></div>'
   +'<table>'+linhas+'</table></div>';
 }).join('');
 var filtrando = !!((document.getElementById('pl_loc')||{}).value||'').trim();
 var lc = document.getElementById('pl_loc_conta');
 if(lc) lc.textContent = filtrando
   ? ('mostrando ' + visiveis + ' de ' + total + ' série(s)') : '';
 document.getElementById('pl_corpo').innerHTML = h || (filtrando
  ? '<p class="sub">Nada com esse trecho. Apague a busca para ver a pasta inteira.</p>'
  : '<p class="sub">Nenhum exame na pasta. Confira o caminho no passo 1.</p>');
}
function upd(){fetch('/api/status').then(r=>r.json()).then(d=>{
 if(window.uiConexao) uiConexao(true);
 window._ligado = !!d.ligado;
 var bl=document.getElementById('btLiga');
 if(bl){
  if(!d.ligado){
   bl.textContent='\u25B6 Ligar a fila';
   bl.className='pri';
   bl.title='Liga a fila de estudo. A esta\u00e7\u00e3o passa a ser dela: as outras '
    +'telas da su\u00edte ficam trancadas enquanto ela roda.';
   bl.onclick=function(){ planoAbrir() };
  } else if(d.paused){
   bl.textContent='\u25B6 Rodar';
   bl.className='pri';
   bl.title='Retoma o trabalho. Se o vigia tinha parado por problema de '
    +'ambiente, este botão confere o ambiente de novo antes de retomar.';
   bl.onclick=function(){ planoAbrir() };
  } else {
   bl.textContent='\u23F8 Pausar (após a série atual)';
   bl.className='';
   bl.title='Termina a série que está sendo processada e para. Não '
    +'interrompe no meio.';
   bl.onclick=function(){ act('pause') };
  }
 }
 var bd=document.getElementById('btDesliga');
 if(bd){ bd.style.display = d.ligado ? '' : 'none'; }
 var bn=document.getElementById('btNoite');
 var ovf=document.getElementById('ovFaixa');
 if(bn) bn.style.display = d.overnight ? 'none' : '';
 if(bd && d.overnight) bd.style.display='none';
 if(ovf){
  ovf.style.display = d.overnight ? '' : 'none';
  if(d.overnight && !window._ovFrotaJa){ window._ovFrotaJa=1; noiteFrota(); }
  if(!d.overnight) window._ovFrotaJa=0;
  if(d.overnight){
   var oh=document.getElementById('ovH');
   if(oh) uiHTML(oh,
     '<span data-radai-frase>aberto há</span> '
     + (d.overnight_h||0).toFixed(1) + ' h'
     + ' · ' + (d.done_today||0)
     + ' <span data-radai-frase>concluída(s) nesta estação</span>'
     + ' · ' + (d.n_queue||0) + ' <span data-radai-frase>na fila</span>'
     + ' · <span data-radai-frase>ordem: caso mais recente primeiro</span>');
   var os_=document.getElementById('ovServicos');
   if(os_){
    var ps=d.overnight_pausados||[];
    var frPausados = 'Serviços pausados para liberar memória:';
    var frSemPausa = 'Nenhum serviço pausado.';
    var frPorQue = 'Eles precisam de administrador nesta estação, ou já estavam parados. A noite roda assim mesmo, com um pouco menos de memória livre.';
    var frVoltam = 'Eles voltam ao estado em que estavam quando você encerrar — e também sozinhos, se a estação reiniciar.';
    var h = ps.length
      ? '<b data-radai-frase>' + frPausados + '</b> '
        + ps.map(function(n){return '<span class="ov-chip pausado">'+n+'</span>'}).join('')
      : '<span style="opacity:.7"><b data-radai-frase>' + frSemPausa
        + '</b> <span data-radai-frase>' + frPorQue + '</span></span>';
    h += '<br><span style="opacity:.62" data-radai-frase>' + frVoltam
      + '</span>';
    uiHTML(os_, h);
   }
  }
 }
 temMR(d.rm_no_disco !== false);
 mach.textContent=d.machine;
 st.textContent = !d.ligado ? 'DESLIGADA'
   : (d.paused ? 'PAUSADA' : (d.saudavel ? 'RODANDO' : 'SEM RESPOSTA'));
 st.className='v '+(!d.ligado ? '' : (d.paused?'warn':(d.saudavel?'ok':'err')));
 cur.textContent=d.current?(d.current.pid+' · '+d.current.count+'c · desde '+d.current.desde):'—';
 done.textContent=d.done_today; nq.textContent=d.n_queue; scan.textContent=d.last_scan||'—';
 var semRoot = !d.root;
 var sf=document.getElementById('subFila');
 if(sf) sf.textContent = semRoot ? '— aguardando a pasta do passo 1'
   : ('— ' + (d.paused?'pausado':(d.saudavel?'rodando':'sem resposta'))
      + ' · ' + d.n_queue + ' na fila');
 var gr=document.getElementById('grade');
 if(gr) gr.style.display = semRoot ? 'none' : '';
 var sr=document.getElementById('semRoot');
 if(sr) sr.style.display = semRoot ? 'flex' : 'none';
 if(semRoot && !ROOT_SUGERIDO){
  ROOT_SUGERIDO = 1;
  fetch('/api/config').then(function(r){return r.json()}).then(function(c){
   var v=(c.valores&&c.valores.ROOT)||(c.padroes&&c.padroes.ROOT)||'';
   var i=document.getElementById('rootIn');
   if(i && !i.value){ i.value=v; }
   document.getElementById('rootDica').textContent = v
     ? 'Esta pasta ja esta no radai_watcher.config. O vigia so passa a usa-la'
       + ' depois de reiniciar.'
     : '';
   if(v) mostrarPasta(v);
  }).catch(function(){});
 }

 var f=document.getElementById('faixa'); var msgs=[];
 if(d.dry_run) msgs.push('MODO SIMULAÇÃO (DRY_RUN=1): nenhum RTSTRUCT de verdade é gravado.');
 if(d.em_transito) msgs.push(esc(d.em_transito)+' serie(s) ainda chegando no servidor; ficam para a proxima volta.');
 if(d.sem_permissao) msgs.push(esc(d.sem_permissao)+' pasta(s) sem permissao de escrita foram deixadas de lado.');
 if(d.recarga) msgs.push('Recarga de configuracao: '+esc(d.recarga));
 PULADAS=d.puladas||0;
 if(PULADAS) msgs.push(PULADAS+' serie(s) estouraram as tentativas e foram '
  +'PULADAS. Corrija a causa e libere aqui para tentar de novo.<br>'
  +'<button class="pri" style="margin:6px 0 0" onclick="liberar()">'
  +'\\u27F2 Liberar '+PULADAS+' serie(s) pulada(s)</button>');
 f.innerHTML=msgs.join('  &middot;  '); f.style.display=msgs.length?'block':'none';
 var al=document.getElementById('alerta'); var av=[];
 if(d.ambiente_erro) av.push('PAREI: este Python nao roda o TotalSegmentator ('+d.ambiente_erro
   +'). Nenhuma serie foi marcada como falha. Use o Python do bundle (start_watcher.cmd) '
   +'e clique em Rodar para conferir de novo.');
 if(!d.saudavel) av.push('O laco de trabalho nao responde ha '+d.parado_ha+'s. '+(d.worker_erro||''));
 if(d.root_ok===false) av.push('ROOT inacessivel agora: '+d.root);
 al.textContent=av.join('  ·  '); al.style.display=av.length?'block':'none';
 var tq=document.getElementById('tq');
 tq.innerHTML='<tr><th>Paciente</th><th>Data</th><th>Cortes</th><th>Série</th><th>Situação</th></tr>';
 var proc=d.current||null, aguardando=0;
 (d.queue||[]).forEach(function(q){
  var sit;
  if(proc && q.uid===proc.uid){
   var p=proc.passo||0, n=proc.total||0, pct=n?Math.round(Math.max(p-1,0)*100/n):0;
   sit='<div class="prog" title="etapa '+p+' de '+n+'"><i style="width:'+pct+'%"></i></div>'
      +'<span class="sit run">'+esc(proc.etapa||'preparando')
      +(n?(' · '+p+'/'+n):'')+(proc.etapa_secs?(' · '+dur(proc.etapa_secs)):'')+'</span>';
  } else if(d.paused){ sit='<span class="sit">parado</span>'; }
  else { aguardando++; sit='<span class="sit">'+(aguardando===1?'próxima':'na fila')+'</span>'; }
  tq.innerHTML+='<tr><td>'+esc(q.pid)+'</td><td>'+esc(q.date)+'</td><td>'+esc(q.count)
   +'</td><td>'+esc(q.uid)+'</td><td>'+sit+'</td></tr>';
 });
 var tf=document.getElementById('tf');tf.innerHTML='<tr><th>Série</th><th>Erro</th></tr>';
 (d.fails||[]).forEach(f=>{tf.innerHTML+='<tr><td>'+f.uid+'</td><td class="err">'+f.err+'</td></tr>'});
})
 .catch(function(e){
  if(window.uiConexao) uiConexao(false, ''+e);
 })}

function abrirPasso1(){
 var cx = document.getElementById('cx1');
 if(!cx) return;
 cx.classList.remove('fechado');
 cx.scrollIntoView({behavior:'smooth', block:'center'});
 var campo = document.getElementById('rootIn');
 if(campo) setTimeout(function(){ campo.focus() }, 300);
}
document.getElementById('btVarrer').addEventListener('click', salvarVarrer);
function listarPastas(caminho){
 var cx=document.getElementById('fpVigia');
 var esc2=function(t){return String(t==null?'':t).replace(/[&<>"]/g,function(c){
   return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c];});};
 cx.style.display='block'; cx.innerHTML='<div class="dica">listando…</div>';
 fetch('/api/pastas',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({caminho:caminho||''})})
 .then(function(r){return r.json()}).then(function(d){
  var h='<div class="fpcam">'+esc2(d.caminho||'(unidades desta máquina)')+'</div>';
  (d.unidades||[]).forEach(function(u){
   h+='<button class="fpi drv" data-c="'+esc2(u)+'">'+esc2(u)+'</button>'; });
  if(d.pai) h+='<div class="fpi" data-c="'+esc2(d.pai)+'">.. (subir)</div>';
  (d.pastas||[]).forEach(function(p){
   h+='<div class="fpi" data-c="'+esc2(p.caminho)+'">'+esc2(p.nome)+'</div>'; });
  if(d.erro) h+='<div class="erro">'+esc2(d.erro)+'</div>';
  h+='<div class="linha"><button class="bt" id="fpUsar">Usar esta pasta</button>'
   + '<button class="bt" id="fpFechar">Fechar</button></div>';
  cx.innerHTML=h;
 }).catch(function(e){ cx.innerHTML='<div class="erro">Nao consegui listar: '+e+'</div>'; });
}
document.getElementById('btPastas').addEventListener('click', function(){
 listarPastas((document.getElementById('rootIn').value||'').trim()); });
document.getElementById('fpVigia').addEventListener('click', function(ev){
 if(ev.target.id==='fpFechar'){ this.style.display='none'; return; }
 if(ev.target.id==='fpUsar'){
  var cam=this.querySelector('.fpcam');
  if(cam) document.getElementById('rootIn').value=cam.textContent;
  this.style.display='none'; return; }
 var t=ev.target.closest('[data-c]');
 if(t) listarPastas(t.getAttribute('data-c'));
});
document.getElementById('btRoot').addEventListener('click',
 function(){ salvarRoot(true) });
document.getElementById('btTestar').addEventListener('click',
 function(){ salvarRoot(false) });
document.getElementById('rootIn').addEventListener('keydown', function(e){
 if(e.key==='Enter') salvarRoot(true);
});
setInterval(upd,3000);upd();carregarVarrer();
</script></body></html>"""


def _com_menu(pagina, ativo):
    # GUARDA: import preguiçoso e protegido: tela quebrada não derruba o
    # painel do vigia.
    try:
        import radai_menu
        return radai_menu.aplicar(pagina, ativo)
    except Exception:
        return pagina


@app.get("/vigia")
def home():
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/lote", status_code=307)


def _turno_agendado_na_fila():
    try:
        return bool(sys.modules["radai_queue_state"].turno_agendado())
    except Exception:
        return False


@app.get("/api/status")
def status():
    ocupado = quem_esta_segmentando()
    turno_agendado = _turno_agendado_na_fila()
    try:
        _grupos = fora_da_fila(teto=10)["em_espera"]
    except Exception:
        _grupos = []
    with LOCK:
        parado_ha = int(time.time() - STATE["worker_vivo"])
        atual = dict(STATE["current"]) if STATE["current"] else None
        if atual:
            atual["etapa_secs"] = int(time.time() - atual.pop("etapa_desde", time.time()))
            atual = sem_caminho_nem_uid(atual, com_pid=True)
        return {"machine": MACHINE, "versao": APPVER, "paused": STATE["paused"],
                "ligado": STATE["ligado"],
                "overnight": STATE["overnight"],
                "overnight_h": (max(0.0, time.time() - STATE["overnight_desde"]) / 3600.0
                                if STATE["overnight_desde"] else 0.0),
                "overnight_pausados": list(STATE["overnight_pausados"]),
                "turno_agendado": turno_agendado,
                "current": atual, "done_today": STATE["done_today"],
                "ocupado": ocupado,
                "n_queue": STATE["n_queue"], "queue": STATE["queue"],
                "fails": STATE["fails"], "last_scan": STATE["last_scan"],
                "dry_run": DRY_RUN, "root": ROOT, "root_ok": STATE["root_ok"],
                "em_transito": STATE["em_transito"], "sem_permissao": STATE["sem_permissao"],
                "saudavel": parado_ha < 600, "parado_ha": parado_ha,
                "worker_erro": STATE["worker_erro"], "recarga": STATE["recarga"],
                "recarga_pendente": recarga_pendente(),
                "turno_temporario": chaves_so_do_turno(),
                "root_no_proximo_turno": bool(root_para_o_proximo_turno()),
                "ambiente_erro": STATE["ambiente_erro"], "puladas": STATE["puladas"],
                "nao_contornaveis": STATE.get("nao_contornaveis", 0),
                "em_espera": STATE.get("em_espera", 0),
                "em_espera_grupos": _grupos,
                "alertas_de_assinatura": [
                    dict(a) for a in STATE.get("alertas_de_assinatura") or []],
                "log_arquivo": str(LOG_PATH or ""), "tasks": list(TASKS),
                "rm_no_disco": rm_no_disco(),
                "arranque": dict(STATE["arranque"]),
                }


VRAM_MINIMA_GB = 6.0


def _recomendar_processamento(laudo):
    gpu = laudo.get("gpu") or None
    atual = str(laudo.get("escolhido") or "auto").strip().lower()

    def _r(porque, ganho=u"", risco=u""):
        return {"device": "auto", "porque": porque, "ganho": ganho,
                "risco": risco, "ja_esta": atual in ("auto", "")}

    if not gpu:
        return _r(u"Não há CUDA disponível nesta estação: com `auto`, cada "
                  u"task roda no processador. Se uma placa passar a ser "
                  u"alcançada (driver atualizado, a mesma instalação noutra "
                  u"máquina), ela é usada sem mexer aqui.",
                  risco=u"Medido neste projeto: uma série de 409 cortes levou "
                        u"1 h 20 em CPU. O lote de uma pasta inteira não fecha "
                        u"em uma noite; uma série por vez, sim.")
    mem = float(gpu.get("memoria_gb") or 0)
    if mem and mem < VRAM_MINIMA_GB:
        livre = gpu.get("memoria_livre_gb")
        conta = u""
        try:
            if livre:
                conta = (u" No momento da medida havia %.1f GB livres — o "
                         u"resto está com outros programas (navegador, "
                         u"Teams, Office costumam segurar meio giga)."
                         % float(livre))
        except Exception:
            conta = u""
        return _r(u"A placa é a %s, com %.1f GB — abaixo dos ~%.0f GB que a "
                  u"documentação do TotalSegmentator pede para a `total` em "
                  u"resolução cheia.%s Com `auto`, o programa mede a memória "
                  u"livre antes de cada task e escolhe: a placa quando cabe, "
                  u"a rede na placa com o resultado na RAM quando só a rede "
                  u"cabe, e o processador quando nem isso."
                  % (gpu.get("nome", "?"), mem, VRAM_MINIMA_GB, conta),
                  risco=u"`cpu` fixo deixaria a placa parada mesmo nas tasks "
                        u"que cabem nela; `gpu` fixo pede a placa mesmo "
                        u"quando o driver a perde.")
    return _r(u"A placa é a %s, com %.1f GB e CUDA %s. Com `auto`, a "
              u"inferência vai para ela, e o programa ainda confere a memória "
              u"livre antes de cada task."
              % (gpu.get("nome", "?"), mem, gpu.get("cuda") or "?"),
              ganho=u"Com GPU a inferência sai em minutos por série, contra "
                    u"dezenas de minutos em CPU.",
              risco=u"`gpu` fixo FALHA ALTO se a placa sumir (driver, sessão "
                    u"remota sem acesso à placa); `auto` cai para o "
                    u"processador, e o log de cada task diz onde ela rodou.")


@app.get("/api/processamento")
def api_processamento():
    dev_cfg = str(CFG.get("DEVICE", "auto"))
    fora = {"escolhido": dev_cfg, "resolve_em": "", "gpu": None,
            "cpu": {}, "aviso": "", "estimativa": {}}
    try:
        import multiprocessing
        fora["cpu"] = {"nucleos": multiprocessing.cpu_count()}
    except Exception:
        pass
    tr = {}
    try:
        import radai_arranque as RA
        pl = RA.placas(timeout=15)
        tr = RA.torch_da_estacao(sys.executable, timeout=90)
        if tr.get("disponivel"):
            p0 = (pl.get("placas") or [{}])[0]
            t0 = (tr.get("placas") or [{}])[0]
            total_mb = p0.get("total_mb") or t0.get("total_mb") or 0
            fora["gpu"] = {"nome": p0.get("nome") or t0.get("nome") or "?",
                           "memoria_gb": round(float(total_mb) / 1024.0, 1),
                           "cuda": tr.get("cuda") or "",
                           "n": int(tr.get("n") or len(pl.get("placas") or []))}
            if p0.get("livre_mb") is not None:
                fora["gpu"]["memoria_livre_gb"] = round(
                    float(p0["livre_mb"]) / 1024.0, 1)
        elif tr.get("falha") or tr.get("erro"):
            fora["aviso"] = ("nao consegui consultar o torch (%s)"
                             % str(tr.get("falha") or tr.get("erro"))[:120])
    except Exception as e:
        fora["aviso"] = "nao consegui consultar a placa (%s)" % str(e)[:120]
    _d = dev_cfg.strip().lower()
    _d = "gpu" if _d == "cuda" else _d
    fora["resolve_em"] = (_d if _d in ("gpu", "cpu")
                          else ("gpu" if tr.get("disponivel") else "cpu"))

    if fora["resolve_em"] == "cpu":
        fora["estimativa"] = {
            "texto": ("~1,1 min por milhao de voxels no espaco do modelo. Uma TC "
                      "de planejamento de corpo inteiro da ~35 M voxels: cerca de "
                      "40 min so na task `total`, mais o pos-processamento."),
            "base": "dois pontos medidos neste projeto (15/08/2026) — serve para "
                    "dizer a ordem de grandeza, nao para prometer numero",
            "recomendacao": ("Sem GPU, o lote noturno de uma pasta inteira nao "
                             "fecha em uma noite. Uma serie por vez, sim.")}
    else:
        fora["estimativa"] = {
            "texto": "Com GPU, a inferencia sai em minutos por serie.",
            "base": "",
            "recomendacao": ""}
    if not fora["gpu"] and dev_cfg.strip().lower() == "gpu":
        fora["aviso"] = ("O DEVICE esta em `gpu` e esta estacao nao tem CUDA "
                         "disponivel. O vigia vai falhar na primeira serie.")
    fora["recomendacao"] = _recomendar_processamento(fora)
    return fora


@app.get("/api/vigia/plano")
def api_plano():
    try:
        return plano_de_execucao()
    except Exception as e:
        return {"erro": "%s: %s" % (type(e).__name__, str(e)[:240]),
                "exames": [], "conjuntos": [],
                "resumo": {"a_fazer": 0, "prontos": 0, "rodando": 0,
                           "pulados": 0, "falhados": 0}}


@app.post("/api/vigia/ligar")
def vigia_ligar():
    if STATE["ambiente_erro"]:
        ok, detalhe = conferir_ambiente()
        if not ok:
            barrar_por_ambiente(detalhe)
            return {"ok": False, "ambiente_erro": STATE["ambiente_erro"]}
        with LOCK:
            STATE["ambiente_erro"] = ""
    if not (ROOT or "").strip():
        return {"ok": False,
                "erro": "o ROOT esta vazio: a fila nao teria o que varrer. "
                        "Preencha em Configuracoes antes de ligar."}

    _oc = quem_esta_segmentando()
    with LOCK:
        STATE["ligado"] = True
        STATE["paused"] = False
    wlog("fila de estudo LIGADA pelo operador — a estacao passa a ser dela%s."
         % (u"; o «Rodar agora» termina o que pediram a mao primeiro"
            if _oc and _oc.get("quem") == "lote" else u""))
    return {"ok": True, "espera_o_lote": bool(_oc and _oc.get("quem") == "lote")}


@app.post("/api/vigia/desligar")
def vigia_desligar():
    with LOCK:
        STATE["ligado"] = False
        STATE["paused"] = False
    wlog("fila de estudo DESLIGADA pelo operador (a serie atual termina).")
    return {"ok": True}


@app.post("/api/overnight/iniciar")
def overnight_iniciar():
    return abrir_turno(origem="tela")


def abrir_turno_pela_fila():
    return abrir_turno(origem="fila")


_TRAVA_DO_TURNO = threading.Lock()


def _laudo_em_frase(laudo):
    l = laudo or {}
    if l.get("existe") and l.get("leitura") and l.get("escrita"):
        return u"existe, le e grava"
    return u"%s" % (l.get("erro") or l.get("aviso") or u"sem laudo")


def conferir_temporarios(tmp):
    tmp = dict(tmp or {})
    estranhas = sorted(k for k in tmp if k not in CHAVES_DO_TURNO)
    if estranhas:
        return None, None, (u"o turno so aceita %s sem gravar, e recusou: %s"
                            % (", ".join(CHAVES_DO_TURNO), ", ".join(estranhas)))
    fora, laudo = {}, None
    if "ROOT" in tmp:
        root = (u"%s" % (tmp.get("ROOT") or u"")).strip().strip('"')
        try:
            import radai_config as _rc
            laudo = _rc.validar_pasta(root)
        except Exception as e:
            laudo = {"existe": False, "leitura": False, "escrita": False,
                     "erro": u"%s: %s" % (type(e).__name__, str(e)[:160])}
        if not (laudo.get("existe") and laudo.get("leitura")
                and laudo.get("escrita")):
            return None, laudo, (u"a pasta do turno nao passou no laudo "
                                 u"(existe? le? grava?): %s"
                                 % _laudo_em_frase(laudo))
        fora["ROOT"] = root
    if "MODALITIES" in tmp:
        mods = sorted(set(m.upper() for m in re.split(
            r"[,;\s]+", u"%s" % (tmp.get("MODALITIES") or u"")) if m))
        if not mods or [m for m in mods if m not in ("CT", "MR")]:
            return None, laudo, (u"MODALITIES do turno e CT, MR ou CT,MR "
                                 u"(veio %r)" % (u"%s" % tmp.get("MODALITIES"))[:40])
        fora["MODALITIES"] = u",".join(mods)
    if "DAYS_BACK" in tmp:
        try:
            dias = int((u"%s" % tmp.get("DAYS_BACK")).strip())
        except (TypeError, ValueError):
            return None, laudo, (u"DAYS_BACK do turno nao e numero (veio %r)"
                                 % (u"%s" % tmp.get("DAYS_BACK"))[:40])
        if not (0 <= dias <= 36500):
            return None, laudo, (u"DAYS_BACK do turno vai de 0 a 36500 "
                                 u"(veio %d)" % dias)
        fora["DAYS_BACK"] = str(dias)
    return fora, laudo, u""


def _descartar_temporarios(motivo):
    with _RECARGA_FEITA:
        fora = sorted(TURNO_TEMPORARIO)
        TURNO_TEMPORARIO.clear()
    if not fora:
        return []
    pedir_recarga()
    wlog(u"os valores gravados voltam (%s): %s -- a recarga entra entre "
         u"series, e a serie em curso termina onde comecou"
         % (motivo, ", ".join(fora)))
    return fora


def abrir_turno(origem="tela"):
    with _TRAVA_DO_TURNO:
        return _abrir_turno(origem)


def _abrir_turno(origem):
    quem = (u"pelo card da fila" if origem == "fila" else u"pela tela")
    fila_ov, cfg_turno = None, None
    try:
        import radai_queue_state as fila_ov
        cfg_turno = fila_ov.config_do_turno()
    except Exception:
        fila_ov, cfg_turno = None, None

    def _fechar(estado, motivo):
        if fila_ov is None or cfg_turno is None:
            return
        try:
            fila_ov.fechar_turno(estado, erro_sem_caminho_nem_uid(motivo))
        except Exception as e:
            wlog(u"o card do turno nao foi fechado na fila (%s: %s)"
                 % (type(e).__name__, str(e)[:120]))

    def _recusar(resposta, motivo):
        wlog(u"o turno da noite NAO abriu (%s): %s" % (quem, motivo))
        _fechar(Q_FALHOU, motivo)
        resposta = dict(resposta or {})
        resposta["ok"] = False
        resposta.setdefault("erro", motivo)
        return resposta

    _pausar = True
    if cfg_turno is not None:
        _pausar = bool(cfg_turno.get("pausar_servicos", True))
    tmp = dict((cfg_turno or {}).get("temporarios") or {})

    if STATE.get("overnight"):
        _fechar(Q_FEITO, u"o turno ja estava aberto nesta estacao"
                + (u"; os valores deste card (%s) nao foram aplicados"
                   % ", ".join(sorted(tmp)) if tmp else u""))
        return {"ok": True, "ja_aberto": True,
                "pausados": list(STATE.get("overnight_pausados") or []),
                "n_pausados": len(STATE.get("overnight_pausados") or []),
                "servicos": [], "recarga_pendente": recarga_pendente(),
                "temporario": chaves_so_do_turno()}

    aplicados = []
    if tmp:
        valores, laudo, erro = conferir_temporarios(tmp)
        if erro:
            return _recusar({"laudo": laudo}, erro)
        wlog(u"turno com valores TEMPORARIOS (nao gravados no "
             u"radai_watcher.config): %s%s -- os gravados voltam quando o "
             u"turno for encerrado"
             % (", ".join(u"%s=%s" % (k, valores[k]) for k in sorted(valores)),
                (u" | laudo da pasta: %s" % _laudo_em_frase(laudo))
                if laudo is not None else u""))
        with _RECARGA_FEITA:
            TURNO_TEMPORARIO.clear()
            TURNO_TEMPORARIO.update(valores)
        pedir_recarga()
        aplicados = sorted(valores)

    esp = esperar_recarga()
    if esp.get("falhou"):
        _descartar_temporarios(u"a recarga falhou")
        return _recusar({"recarga": esp},
                        u"a configuracao nova nao foi aplicada (%s): o turno "
                        u"nao abriu com valores que nao sao os pedidos"
                        % esp["falhou"])
    pendente = bool(esp.get("pendente"))

    r = vigia_ligar()
    if not r.get("ok"):
        _descartar_temporarios(u"o turno nao abriu")
        motivo = (r.get("erro") or r.get("ambiente_erro")
                  or u"a fila de estudo nao ligou")
        if pendente and not (ROOT or "").strip():
            motivo = (u"a configuracao nova ainda nao foi aplicada (a recarga "
                      u"so entra entre series) e a pasta em uso esta vazia")
        return _recusar(r, motivo)

    try:
        import radai_overnight
        res = radai_overnight.iniciar(pausar_servicos=_pausar, log=wlog)
    except Exception as e:
        wlog("nao consegui pausar os servicos (%s) — o overnight run comeca "
             "assim mesmo, sem liberar memoria" % str(e)[:140])
        res = {"ok": False, "servicos": [], "msg": str(e)[:140]}
    pausados = [s.get("nome") for s in (res.get("servicos") or [])
                if s.get("acao") == "parado"]
    with _RECARGA_FEITA:
        if "ROOT" in TURNO_TEMPORARIO:
            _root_aberto = TURNO_TEMPORARIO["ROOT"]
        elif pendente:
            _root_aberto = _root_no_arquivo()
        else:
            _root_aberto = None
        ROOT_DO_TURNO.clear()
        ROOT_DO_TURNO["root"] = _sem_aspas(
            ROOT if _root_aberto is None else _root_aberto)
    with LOCK:
        STATE["overnight"] = True
        STATE["overnight_desde"] = time.time()
        STATE["overnight_pausados"] = pausados
    wlog("=== OVERNIGHT RUN aberto nesta estacao (%s) — a fila pega o caso "
         "mais recente primeiro, e %d servico(s) estao pausados ==="
         % (quem, len(pausados)))
    aviso = u""
    if pendente:
        aviso = (u"A configuração nova ainda não foi aplicada: o vigia termina "
                 u"a série em curso na pasta de antes, e nenhuma série nova "
                 u"começa antes de a recarga entrar.")
        wlog(u"turno aberto com a recarga pendente: a configuracao nova vale "
             u"quando a serie em curso terminar (o laco so troca de pasta "
             u"entre series)")
    motivo = u"turno aberto as %s" % datetime.now().strftime("%H:%M")
    if aplicados:
        motivo += u"; so neste turno: %s" % ", ".join(aplicados)
    if pendente:
        motivo += u"; a configuracao nova vale quando a serie em curso terminar"
    _fechar(Q_FEITO, motivo)
    return {"ok": True, "pausados": pausados,
            "n_pausados": len(pausados), "servicos": res.get("servicos") or [],
            "recarga_pendente": pendente, "aviso": aviso,
            "temporario": aplicados}


Q_FEITO, Q_FALHOU = "pronto", "falhou"


@app.post("/api/overnight/encerrar")
def overnight_encerrar():
    religados, falhas = 0, []
    try:
        import radai_overnight
        r = radai_overnight.encerrar(log=wlog)
        religados, falhas = r.get("religados", 0), r.get("falhas") or []
    except Exception as e:
        wlog("nao consegui religar os servicos (%s) — eles voltam sozinhos no "
             "proximo arranque da estacao" % str(e)[:140])
        falhas = [str(e)[:140]]
    adiada = bool(root_para_o_proximo_turno())
    with _RECARGA_FEITA:
        ROOT_DO_TURNO.clear()
    with LOCK:
        STATE["overnight"] = False
        STATE["overnight_desde"] = 0.0
        STATE["overnight_pausados"] = []
        STATE["ligado"] = False
        STATE["paused"] = False
    wlog("=== OVERNIGHT RUN encerrado — %d servico(s) religado(s); a serie "
         "atual termina e nenhuma nova comeca ===" % religados)
    devolvidos = _descartar_temporarios(u"o turno foi encerrado")
    if adiada:
        pedir_recarga()
        wlog(u"o turno acabou: a pasta nova do ROOT passa a valer")
    try:
        import radai_queue_state as _fila_ov
        _fila_ov.tirar_turno_cumprido()
    except Exception:
        pass
    return {"ok": True, "religados": religados, "falhas": falhas,
            "devolvidos": devolvidos}


@app.get("/api/overnight/frota")
def overnight_frota():
    if not (STATUS_DIR or "").strip():
        return {"ok": True, "configurado": False, "maquinas": [],
                "resumo": {"n": 0, "trabalhando": 0, "paradas": 0,
                           "concluidas": 0},
                "aviso": "Sem STATUS_DIR em Configurações, cada estação só "
                         "enxerga a si mesma. Combine uma pasta comum com o TI "
                         "para ver a noite inteira numa tela."}
    if _STATUS_DIR_RECUSADO[0]:
        return {"ok": True, "configurado": False, "maquinas": [],
                "resumo": {"n": 0, "trabalhando": 0, "paradas": 0,
                           "concluidas": 0},
                "aviso": "A pasta do STATUS_DIR sincroniza com a nuvem, e o "
                         "sinal de vida leva a data e o final do UID da série "
                         "em curso — este programa não grava dado de paciente "
                         "em pasta espelhada. Escolha com o TI uma pasta de "
                         "rede que não sincronize."}
    try:
        import radai_overnight
        maqs = radai_overnight.frota(STATUS_DIR, eu=MACHINE)
        return {"ok": True, "configurado": True, "maquinas": maqs,
                "resumo": radai_overnight.resumo_da_frota(maqs), "aviso": ""}
    except Exception as e:
        return {"ok": False, "configurado": True, "maquinas": [],
                "resumo": {"n": 0, "trabalhando": 0, "paradas": 0,
                           "concluidas": 0},
                "aviso": "nao consegui ler a pasta de status: %s" % str(e)[:160]}


@app.post("/api/pause")
def pause():
    STATE["paused"] = True
    wlog("pausado pelo operador (termina a serie atual e para).")
    return {"ok": True}


@app.post("/api/resume")
def resume():
    if STATE["ambiente_erro"]:
        ok, detalhe = conferir_ambiente()
        if not ok:
            barrar_por_ambiente(detalhe)
            return {"ok": False, "ambiente_erro": STATE["ambiente_erro"]}
        with LOCK:
            STATE["ambiente_erro"] = ""
        wlog("ambiente conferido de novo: o TotalSegmentator responde neste Python.")
    STATE["paused"] = False
    wlog("retomado pelo operador.")
    return {"ok": True}


@app.post("/api/fila/topografia")
async def api_topografia(request: Request):
    try:
        c = await request.json() or {}
    except Exception:
        c = {}
    uid = str(c.get("uid") or "")
    if not uid:
        return {"ok": False, "erro": "faltou o uid"}
    pasta, _pid = serie_da_varredura(uid)
    if not pasta:
        return _serie_fora_da_varredura()
    return gravar_topografia(pasta, uid, c.get("topo"))


@app.post("/api/fila/decidir")
async def api_decidir(request: Request):
    try:
        c = await request.json() or {}
    except Exception:
        c = {}
    uid = str(c.get("uid") or "")
    if not uid:
        return {"ok": False, "erro": "faltou o uid"}
    pasta, pid = serie_da_varredura(uid)
    if not pasta:
        return _serie_fora_da_varredura()
    r = gravar_decisao(Path(pasta), uid, str(c.get("decisao") or ""))
    _lembrar_de_outras(_identificadores_de(pid, uid))
    if r.get("ok"):
        wlog("fila: %s ...%s -> %s" % (
            (pid or "serie"), uid[-8:],
            r.get("decisao") or "sem marca (a escada volta a decidir)"))
    return r


def _serie_fora_da_varredura():
    from starlette.responses import JSONResponse
    return JSONResponse(status_code=404, content={
        "ok": False,
        "erro": "esta serie nao esta na ultima varredura do ROOT: abra o "
                "plano de novo (ele varre a pasta) e marque outra vez"})


@app.post("/api/rescan")
def rescan():
    RESCAN_NOW.set()
    return {"ok": True}


@app.get("/api/fora_da_fila")
def _api_fora_da_fila():
    return fora_da_fila()


@app.post("/api/liberar_falhas")
def liberar():
    resultado = liberar_falhas()
    resultado["ok"] = True
    return resultado


if radai_panel is not None:
    def _pausar_o_vigia(valor):
        STATE["paused"] = bool(valor)
        wlog("vigia %s pelo controle do pipeline."
             % ("pausado" if valor else "retomado"))
        return bool(valor)

    radai_panel.montar(app, status, config={
        "caminho": str(CFG_PATH),
        "chaves": list(DEFAULTS.keys()),
        "padroes": dict(DEFAULTS),
        "modelo": DEFAULT_CFG,
        "em_uso": lambda: dict(CFG),
        "temporarias": chaves_so_do_turno,
        "arranque": {"PORT": str(PORT)},
        "registrar": wlog,
        "recarregar": pedir_recarga,
        "so_no_arranque": list(SO_NO_ARRANQUE),
        "lote": {"tasks": list(TASKS), "device": CFG["DEVICE"],
                 "ocupado": quem_esta_segmentando,
                 "cancelar_vigia": cancelar_serie_do_vigia,
                 "pausar_vigia": _pausar_o_vigia,
                 "abrir_turno": abrir_turno_pela_fila,
                 "trava": regra_de_travamento(),
                 "recorte_no_corpo": bool(RECORTE_NO_CORPO),
                 "min_cortes": MIN_SLICES, "python_exe": sys.executable,
                 "classificar_erro": classificar_erro,
                 "erro_de_ambiente": erro_de_ambiente,
                 "limpar_erro": limpar_erro,
                 "timeout_task_s": TIMEOUT_TASK_S,
                 "suavizar_mm": SUAVIZAR_MM,
                 "maquina": MACHINE, "heartbeat_s": HEARTBEAT_S,
                 "recurso_voltou": recurso_voltou,
                 "log": lambda m: wlog("[rodar agora] " + m),
                 "marcadores": {"claim": claim, "unclaim": unclaim,
                                "has_marker": has_marker, "read_marker": read_marker,
                                "m_path": m_path, "renovar": renovar_lock,
                                "diagnostico": _diagnostico_do_lock,
                                "reservar_entrega": reservar_entrega,
                                "soltar_entrega": soltar_entrega,
                                "lock_e_meu": lock_e_meu,
                                "renovar_entrega": renovar_entrega,
                                "resolver_done_afastado":
                                    resolver_done_afastado,
                                "sem_rtstruct": marcador_sem_rtstruct,
                                "sem_rtstruct_afastado":
                                    marcador_sem_rtstruct_afastado,
                                "afastar_sem_rtstruct":
                                    afastar_marcador_sem_rtstruct,
                                "tirar_sem_rtstruct":
                                    _tirar_o_marcador_sem_rtstruct}}})

    try:
        import radai_shutdown
        radai_shutdown.montar(app, lambda: encerrar_tudo())
    except Exception as _e:
        wlog("botao de fechar indisponivel: %s" % _e)

    try:
        import radai_pulso
        PULSO = radai_pulso.Pulso(0.0)
        radai_pulso.montar(app, PULSO)
    except Exception as _e:
        wlog("pulso das telas indisponivel: %s" % _e)

    try:
        import radai_languages
        radai_languages.montar(app)
    except Exception as _e:
        wlog("dicionario de idiomas indisponivel: %s" % _e)

    try:
        import radai_ui as _ui_icone
        _ui_icone.montar_icone(app)
    except Exception as _e:
        wlog("icone do produto indisponivel: %s" % _e)

    try:
        import radai_credits
        radai_credits.montar(app)
    except Exception as _e:
        wlog("tela de creditos indisponivel: %s" % _e)

    try:
        import radai_consent
        radai_consent.montar_portao(app)
        wlog("portao do aceite ativo: tela sem aceite em dia vai para /aceite")
    except Exception as _e:
        wlog("PORTAO DO ACEITE NAO SUBIU (%s) — as telas abrem sem ele" % _e)

else:
    @app.get("/", response_class=HTMLResponse)
    def home_sem_landing():
        return PAGE


SERVIDOR = {"s": None}
_VIGILANCIA = [None]


def _painel_no_ar():
    s = SERVIDOR.get("s")
    return bool(s is not None and getattr(s, "started", False))


HORIZONTE_DAS_ADIADAS_S = 12 * 3600


def _adiadas_voltam_logo(agora=None):
    if not (STATE.get("ligado") and not STATE.get("paused")
            and int(STATE.get("adiadas") or 0) > 0):
        return False
    try:
        volta = float(STATE.get("volta_das_adiadas") or 0)
    except (TypeError, ValueError):
        return False
    agora = time.time() if agora is None else agora
    return bool(volta) and volta - agora <= HORIZONTE_DAS_ADIADAS_S


def fila_ocupada():
    if quem_esta_segmentando() is not None:
        return True
    if (STATE.get("ligado") and not STATE.get("paused")
            and (STATE.get("n_queue") or 0) > 0):
        return True
    # GUARDA: a serie adiada por recurso volta sozinha; a estacao nao dorme
    # antes dela.
    if _adiadas_voltam_logo():
        return True
    try:
        import radai_batch as _lote
        e = _lote.estado() or {}
        return bool(e.get("rodando") or e.get("fila"))
    except Exception:
        return False


def _esvaziar_o_console():
    if _CONSOLE.get("esvaziado"):
        return
    _CONSOLE["esvaziado"] = True
    try:
        import radai_lancador as _la
        _la.limpar_o_console(os.environ.get(_la.VARIAVEL_CONSOLE, ""))
    except Exception:
        pass


def _marcar_o_motor(estado):
    if not _CONSOLE.get("ate_o_painel"):
        return
    try:
        import radai_lancador as _la
        _la.marcar_estado(PORT, estado)
    except Exception:
        pass


def _preparar_motor_oculto():
    try:
        import radai_pulso as _rp
    except Exception:
        return False
    if not _rp.motor_oculto():
        return False
    _CONSOLE["saida"] = sys.stdout
    _CONSOLE["ate_o_painel"] = True
    sys.stdout = _rp.CapturaDoConsole(wlog, original=_CONSOLE["saida"])
    sys.stderr = _rp.CapturaDoConsole(wlog, original=_CONSOLE["saida"])
    return True


def _turno_segue_na_fila():
    if not _turno_agendado_na_fila():
        return False
    lote = sys.modules.get("radai_batch")
    if lote is None:
        return False
    try:
        a = lote.andamento() or {}
    except Exception:
        return False
    if a.get("pausar") or a.get("cancelar"):
        return False
    return bool(a.get("rodando") or a.get("terminando"))


def o_que_segura_o_fechar():
    if STATE.get("overnight"):
        return u"o turno da noite esta aberto"
    q = quem_esta_segmentando()
    if q:
        return (u"a serie do vigia esta rodando" if q.get("quem") == "vigia"
                else u"o lote do Rodar agora esta rodando")
    if _turno_segue_na_fila():
        return u"o turno da noite esta na fila"
    return None


def _segurar_a_fila_ao_fechar(sim):
    if sim and _turno_segue_na_fila():
        wlog("o navegador foi fechado com o turno da noite na fila: a fila "
             "segue ate o turno, e o programa se encerra no fim dele")
        return
    _fila_da_estacao("pedir_fechar_ao_fim", bool(sim))
    if not sim:
        lote = sys.modules.get("radai_batch")
        if lote is not None:
            try:
                lote.retomar_o_lote_que_parou_ao_fechar(
                    lambda m: wlog("[rodar agora] " + m))
            except Exception as e:
                wlog("nao consegui retomar o lote que parou ao fechar (%s)"
                     % type(e).__name__)


def _armar_vigilancia(oculto):
    try:
        import radai_pulso as _rp
    except Exception as e:
        wlog("pulso indisponivel (%s): a estacao pode suspender com a fila "
             "rodando" % type(e).__name__)
        return None
    tol = _rp.tolerancia_do_ambiente(oculto)
    if PULSO is not None and tol > 0:
        PULSO.armar(tol)
        wlog("pulso: o programa se encerra %d s depois que a ultima tela "
             "dele for fechada" % int(tol))
    pulso = PULSO if PULSO is not None else _rp.Pulso(0.0)
    v = _rp.Vigilancia(pulso,
                       lambda: encerrar_tudo(u"porque o navegador foi fechado"),
                       fila_ocupada, log=wlog,
                       em_curso=o_que_segura_o_fechar,
                       ao_adiar=_segurar_a_fila_ao_fechar)
    v.iniciar()
    _VIGILANCIA[0] = v
    return v


TETO_DA_SAIDA_S = 5


def config_do_servidor(app_, porta):
    return uvicorn.Config(app_, host="127.0.0.1", port=porta,
                          log_level="warning",
                          timeout_graceful_shutdown=TETO_DA_SAIDA_S)


ENCERRANDO = threading.Event()
TETO_DO_ENCERRAMENTO_S = 20.0


def _cancelar_o_trabalho_em_curso():
    try:
        import radai_batch as _lote
        if (_lote.estado() or {}).get("rodando"):
            _lote.cancelar()
    except Exception as e:
        wlog("encerrando: nao consegui cancelar o «Rodar agora» (%s)"
             % type(e).__name__)
    eng = sys.modules.get("engine")
    if eng is None:
        return
    try:
        with eng._LOCK:
            jids = list(eng._JOBS.keys())
        for jid in jids:
            eng._set(jid, cancelar=True)
    except Exception as e:
        wlog("encerrando: nao consegui cancelar os jobs do motor (%s)"
             % type(e).__name__)


def soltar_os_locks_deste_processo():
    for uid, sdir in list(_PASTAS_DOS_LOCKS.items()):
        try:
            unclaim(sdir, uid)
            wlog("encerrando: lock da serie ...%s liberado; ela volta para a "
                 "fila." % str(uid)[-8:])
        except Exception as e:
            wlog("encerrando: NAO consegui liberar o lock da serie ...%s (%s)"
                 % (str(uid)[-8:], e))


def encerrar_tudo(motivo=u"pelo operador"):
    if ENCERRANDO.is_set():
        return False
    ENCERRANDO.set()
    STATE["paused"] = True
    wlog("encerrando %s: a fila para e a serie em curso e interrompida, sem "
         "contar como falha" % motivo)
    _cancelar_o_trabalho_em_curso()
    fim = time.time() + TETO_DO_ENCERRAMENTO_S
    while time.time() < fim and quem_esta_segmentando() is not None:
        time.sleep(0.5)
    try:
        import radai_pulso as _rp
        _rp.encerrar_filhos_do_motor(log=wlog)
    except Exception as e:
        wlog("encerrando: nao conferi os processos de segmentacao (%s)"
             % type(e).__name__)
    atual = None
    with LOCK:
        if STATE.get("current"):
            atual = dict(STATE["current"])
    if atual and atual.get("sdir") and atual.get("uid_cheio"):
        try:
            unclaim(atual["sdir"], atual["uid_cheio"])
            wlog("encerrando: lock da serie ...%s liberado; ela volta para a fila."
                 % atual["uid"])
        except Exception as e:
            wlog("encerrando: NAO consegui liberar o lock da serie ...%s (%s)"
                 % (atual["uid"], e))
    else:
        wlog("encerrando: nenhuma serie em curso.")
    soltar_os_locks_deste_processo()
    try:
        import radai_queue_state as _fq_fim
        _fq_fim.ao_fechar()
    except Exception as e:
        wlog("encerrando: a fila nao foi gravada (%s)" % type(e).__name__)
    if STATE.get("overnight"):
        try:
            import radai_overnight as _ov
            _ov.encerrar(log=wlog)
        except Exception as e:
            wlog("encerrando: nao consegui religar os servicos do overnight "
                 "(%s); eles voltam no proximo arranque" % type(e).__name__)
    encerrar_sinalizacao()
    salvar_status()
    srv = SERVIDOR.get("s")
    if srv is not None:
        srv.should_exit = True
        wlog("encerrado %s." % motivo)
    else:
        wlog("encerrando: servidor nao registrado; feche a janela do vigia.")


def _porta_livre(port):
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", port))
        return True, ""
    except OSError:
        return False, _quem_esta_na_porta(port)
    finally:
        try:
            s.close()
        except Exception:
            pass


def _quem_esta_na_porta(port):
    import re
    import subprocess
    try:
        saida = subprocess.run(["netstat", "-ano", "-p", "TCP"],
                               stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL,
                               timeout=20).stdout.decode("cp1252", "replace")
        pid = ""
        alvo = ":%d" % port
        for linha in saida.splitlines():
            campos = linha.split()
            if len(campos) >= 5 and campos[1].endswith(alvo) \
                    and campos[3].upper() == "LISTENING":
                pid = campos[4]
                break
        if not pid:
            return ""
        tl = subprocess.run(["tasklist", "/FI", "PID eq " + pid, "/NH"],
                            stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL,
                            timeout=20).stdout.decode("cp1252", "replace")
        m = re.match(r"\s*(\S+)", tl)
        nome = m.group(1) if m else ""
        if nome.lower() in ("info:", "informa\u00e7\u00f5es:", ""):
            return ""
        return "%s (PID %s)" % (nome, pid)
    except Exception:
        return ""


def _diagnostico_da_maquina():
    try:
        import radai_cleaner as LP
    except Exception:
        return
    try:
        import multiprocessing
        nucleos = multiprocessing.cpu_count()
    except Exception:
        nucleos = 0
    try:
        m = LP.memoria_da_estacao() or {}
    except Exception:
        m = {}
    partes = []
    if nucleos:
        partes.append("%d nucleo(s) logico(s)" % nucleos)
    if m.get("total_mb"):
        partes.append("memoria %.1f GB, %.1f GB livres (%d%% em uso)"
                      % (m["total_mb"] / 1024.0, m["livre_mb"] / 1024.0,
                         m.get("pct", 0)))
    if partes:
        wlog("maquina: " + " | ".join(partes))
    try:
        _eng = carregar_engine()
        wlog("computacao: " + _eng.diagnostico_de_computacao(
            CFG.get("DEVICE", "auto")))
    except Exception as _e:
        wlog("computacao: nao consegui medir (%s)" % type(_e).__name__)
    try:
        import shutil as _sh
        u = _sh.disk_usage(str(LOG_PATH.parent if hasattr(LOG_PATH, "parent")
                               else os.path.dirname(str(LOG_PATH))))
        wlog("disco da pasta de trabalho: %.1f GB livres de %.1f GB"
             % (u.free / 1e9, u.total / 1e9))
    except Exception:
        pass
    try:
        for g in (LP.ganhos_de_velocidade(CFG.get("DEVICE", "")) or []):
            if g.get("chave") == "gpu":
                wlog("   %s: %s (%s)" % (g.get("rotulo", ""),
                                         g.get("ganho", ""),
                                         g.get("detalhe", "")[:120]))
    except Exception:
        pass


def fechar_casos_interrompidos():
    try:
        import radai_records
        return radai_records.fechar_interrompidos(vivo=_processo_vivo,
                                                  log=wlog)
    except Exception as e:
        wlog("registro de casos: nao conferi os casos em andamento de antes "
             "(%s)" % type(e).__name__)
        return []


def _ligar_a_fila_da_estacao():
    try:
        import radai_queue_state as _fq
    except Exception as e:
        wlog("a fila da estacao nao foi achada (%s): ela fica so na memoria"
             % type(e).__name__)
        return None
    _fq.ligar_ganchos(soltar_trava_morta=soltar_trava_morta,
                      achar_pasta=lambda uid: serie_da_varredura(uid)[0])
    try:
        r = _fq.carregar(log=wlog)
    except Exception as e:
        wlog("a fila gravada nao foi lida (%s: %s): ela comeca vazia"
             % (type(e).__name__, str(e)[:120]))
        r = None
    try:
        import radai_batch as _lote
        _lote.armar_relogio_do_complemento()
    except Exception as e:
        wlog("o relogio do complemento por memoria nao subiu (%s)"
             % type(e).__name__)
    return r


def main():
    _abrir_log()
    oculto = _preparar_motor_oculto()
    if oculto:
        wlog("motor sem janela: o log fica na aba Log do painel e em %s"
             % LOG_PATH)
    if _PAINEL_ERRO:
        wlog("landing page indisponivel (%s) — a raiz mostra o painel do vigia" % _PAINEL_ERRO)

    livre, quem = _porta_livre(PORT)
    if not livre:
        nosso = ("python" in quem.lower() or "radioterapia" in quem.lower()
                 or "autocontorno" in quem.lower())
        wlog("")
        wlog("=" * 60)
        wlog(" A PORTA %d JA ESTA EM USO." % PORT)
        if quem:
            wlog(" Quem esta nela: %s" % quem)
        wlog("")
        if nosso or not quem:
            wlog(" Isto quase sempre e OUTRA INSTANCIA DESTE PROGRAMA ja aberta.")
            wlog(" O painel dela ja esta funcionando: abra o navegador em")
            wlog("   http://127.0.0.1:%d/" % PORT)
            wlog(" Se quiser recomecar, feche-a pelo Fechar do menu da "
                 "engrenagem e abra o programa de novo.")
        else:
            wlog(" Nao e este programa. Para usar outra porta, edite")
            wlog("   radai_watcher.config   ->   PORT=8778")
            wlog(" e abra de novo. A PORT so muda com o programa fechado:")
            wlog(" o socket e aberto uma vez, no arranque.")
        wlog("=" * 60)
        wlog("")
        return 4

    radai_notify.armar(NOTIFICAR)
    _arranque_do_cache_por_task()

    try:
        import radai_archive as _ac
        _regs = _ac.conferir_acervo(podar=True, log=wlog)
        _vivos = [r for r in _regs if r.get("estado") == "ok"]
        wlog("ultimos processamentos: %d serie(s) contornadas nesta maquina, "
             "%d ainda no lugar" % (len(_regs), len(_vivos)))
    except Exception as e:
        wlog("nao consegui conferir o acervo (%s) — o vigia sobe assim mesmo"
             % str(e)[:120])

    try:
        conferir_status_dir()
    except Exception as e:
        wlog("nao consegui conferir o STATUS_DIR (%s)" % str(e)[:120])

    registrar_pid_local()
    fechar_casos_interrompidos()

    try:
        import radai_overnight as _ov
        _ov.restaurar_se_pendente(log=wlog)
    except Exception as e:
        wlog("nao consegui conferir o overnight run da noite passada (%s) — "
             "servico pausado volta no proximo arranque do Windows"
             % str(e)[:120])

    _ligar_a_fila_da_estacao()
    threading.Thread(target=soltar_travas_mortas_do_indice, daemon=True,
                     name="radai-travas-ao-abrir").start()
    montar_portao_do_host(app, porta=PORT)
    wlog("painel atende so por %s"
         % " e ".join(sorted(hosts_permitidos(PORT))))
    threading.Thread(target=worker_loop, daemon=True).start()
    iniciar_sinalizacao()
    config = config_do_servidor(app, PORT)
    SERVIDOR["s"] = uvicorn.Server(config)
    _armar_vigilancia(oculto)
    _marcar_o_motor("rodando")
    try:
        SERVIDOR["s"].run()
    except KeyboardInterrupt:
        wlog("Vigia encerrado pelo operador (Ctrl+C). Nada foi perdido: o "
             "RTSTRUCT so e gravado no fim de cada serie, e a que estava em "
             "curso volta para a fila.")
        try:
            atual = None
            with LOCK:
                if STATE.get("current"):
                    atual = dict(STATE["current"])
            if atual and atual.get("sdir") and atual.get("uid_cheio"):
                unclaim(atual["sdir"], atual["uid_cheio"])
                wlog("Lock da serie em curso solto: ela volta para a fila.")
        except Exception:
            pass
        encerrar_sinalizacao()
        _marcar_o_motor("encerrado")
        return 0
    encerrar_sinalizacao()
    wlog("vigia encerrado.")
    _marcar_o_motor("encerrado")


if __name__ == "__main__":
    sys.exit(main() or 0)
