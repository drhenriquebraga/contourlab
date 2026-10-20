# -*- coding: utf-8 -*-
import hashlib
import os
import re

TRAVOU = "travou"
INELEGIVEL = "inelegivel"
RECURSO = "recurso"
INDETERMINADA = "indeterminada"
DETERMINISTICO = "deterministico"
CLASSES = (TRAVOU, INELEGIVEL, RECURSO, INDETERMINADA, DETERMINISTICO)

INICIO_DO_TRACEBACK = u"Traceback (most recent call last):"
TETO_DA_LEITURA_BYTES = 64 * 1024 * 1024

TIPOS_DE_TRAVA = ("TaskTravada",)
PALAVRA_DA_TRAVA = u"TRAVADA"
FRASES_DE_TEMPO_LIMITE = (u"passou do tempo limite",)
TIPOS_INELEGIVEIS = ("SerieNaoContornavel",)
TIPOS_DE_RECURSO = ("MemoryError", "OutOfMemoryError", "_ArrayMemoryError",
                    "ArrayMemoryError", "TemporarioCurto", "DestinoSemEscrita",
                    "RecursoPrevisto")
FRASES_DE_RECURSO = ("not enough memory", "out of memory",
                     "unable to allocate", "can't allocate memory",
                     "cannot allocate memory", "bad_alloc",
                     "defaultcpuallocator", "paging file",
                     "arquivo de pagina", "insufficient system resources",
                     "recursos de sistema insuficientes",
                     "memoria suficiente", u"memória suficiente",
                     "memoria insuficiente", u"memória insuficiente",
                     "no space left on device",
                     "can't start new thread", "cannot start new thread",
                     "can't create new thread", "virtualalloc",
                     "commit limit", "memory allocation failed",
                     "failed to allocate memory", "could not allocate memory")
# GUARDA: o codigo numerico nao depende do idioma do Windows.
CODIGOS_WINDOWS_DE_RECURSO = (8, 14, 112, 1450, 1455)
CODIGOS_ERRNO_DE_RECURSO = (12, 28)
_WINERROR = re.compile(r"\[WinError (\d+)\]")
_ERRNO = re.compile(r"\[Errno (\d+)\]")
FRASES_INELEGIVEIS = ("only 3d images are supported",)
FRASE_INDETERMINADA = u"background workers died"
MARCA_DA_PRIMEIRA = u"Primeira excecao: "
MARCA_DA_ULTIMA = u" Ultima: "

_QUADRO = re.compile(r'^\s*File "([^"]+)", line (\d+), in (.+?)\s*$')
_LINHA_DA_EXCECAO = re.compile(r"^([A-Za-z_][\w.]*)(?:\s*:\s*(.*))?$")
_BARRA_TQDM = re.compile(r"\d{1,3}%\|")
_RESTO_TQDM = re.compile(r"\|\s*\d+/\d+\s*\[")
# GUARDA: do comeco do caminho ao fim da linha, a regra de
# `radai_records.sem_caminhos` (pasta de paciente tem espaco).
_CAMINHO = re.compile(r"(?:(?<![A-Za-z0-9])[A-Za-z]:[\\/]|\\\\[^\\/\s]+[\\/]"
                      r"|(?<![\w.:/])/(?:[^/\s'\"]+/)+)[^\r\n]*")
_UID = re.compile(r"(?<![\d.])\d+(?:\.\d+){4,}(?![\d.])")
_NUMERO = re.compile(r"\d+")
_ESPACOS = re.compile(r"\s+")


class FalhaDaTask(RuntimeError):

    def __init__(self, task, codigo=None, primeira=None, ultima=None,
                 frase=None, cauda=u"", tempo_limite=False,
                 volume_conferido=False):
        self.task = task
        self.codigo = codigo
        self.volume_conferido = bool(volume_conferido)
        self.primeira = primeira
        self.ultima = ultima
        self.tempo_limite = bool(tempo_limite)
        self.cauda = cauda or u""
        if frase is None:
            frase = u"TS %s saiu com codigo %s." % (task, codigo)
        partes = [frase]
        if primeira:
            partes.append(u"%s%s" % (MARCA_DA_PRIMEIRA, _descrever(primeira)))
            if ultima and _chave(ultima) != _chave(primeira):
                partes.append(u"Ultima: %s" % _descrever(ultima, onde=False))
        elif self.cauda:
            partes.append(self.cauda)
        RuntimeError.__init__(self, u" ".join(partes))

    @property
    def assinatura(self):
        return assinatura_da_falha(self)


class SerieNaoContornavel(ValueError):

    def __init__(self, motivo, tela=u""):
        self.motivo = motivo
        # GUARDA: `tela` é a frase com chave (molde %s); `motivo` vai ao log.
        self.tela = tela or motivo
        ValueError.__init__(self, motivo)


class RecursoPrevisto(RuntimeError):

    def __init__(self, task, precisa_mb, livre_mb, commit_livre_mb, frase=None):
        self.task = task
        self.precisa_mb = precisa_mb
        self.livre_mb = livre_mb
        self.commit_livre_mb = commit_livre_mb
        RuntimeError.__init__(self, frase or (
            u"a task %s precisa ~%s GiB de RAM e a estacao tem %s livres e %s "
            u"de commit: nao cabe, e o processo nao e aberto"
            % (task, _gib(precisa_mb), _gib(livre_mb), _gib(commit_livre_mb))))


def _gib(mb):
    try:
        return (u"%.1f" % (float(mb) / 1024.0)).replace(".", ",")
    except (TypeError, ValueError):
        return u"?"


def _chave(exc):
    return (exc.get("tipo"), exc.get("mensagem"), exc.get("onde"))


def _descrever(exc, onde=True):
    txt = u"%s: %s" % (exc.get("tipo") or u"?", (exc.get("mensagem") or u"")[:300])
    if onde and exc.get("onde"):
        txt += u" (%s)" % exc["onde"]
    return txt.rstrip(u": ") + u"."


def _limpar_linha(linha):
    i = linha.find(u"RADAI|")
    if i >= 0:
        linha = linha[:i]
    if _BARRA_TQDM.search(linha) or _RESTO_TQDM.search(linha):
        return None
    return linha


def _linhas_limpas(texto):
    fora = []
    for linha in (texto or u"").replace(u"\r", u"\n").split(u"\n"):
        l = _limpar_linha(linha)
        if l is not None and l.strip():
            fora.append(l.rstrip())
    return fora


def _onde(quadro):
    arq, num, func = quadro
    return u"%s:%s em %s" % (os.path.basename(arq.replace(u"\\", u"/")), num,
                             func.strip())


def excecoes_do_texto(texto):
    linhas = _linhas_limpas(texto)
    fora = []
    i, n = 0, len(linhas)
    while i < n:
        if INICIO_DO_TRACEBACK not in linhas[i]:
            i += 1
            continue
        inicio = i
        quadros = []
        achou = None
        j = i + 1
        while j < n and j - inicio < 400:
            l = linhas[j]
            if INICIO_DO_TRACEBACK in l:
                break
            q = _QUADRO.match(l)
            if q:
                quadros.append(q.groups())
                j += 1
                continue
            if l[:1].isspace():
                j += 1
                continue
            m = _LINHA_DA_EXCECAO.match(l.strip())
            if m and (quadros or j == inicio + 1):
                achou = (m.group(1), (m.group(2) or u"").strip())
                j += 1
                break
            j += 1
        if achou is not None:
            fora.append({"tipo": achou[0].split(u".")[-1],
                         "mensagem": achou[1],
                         "onde": _onde(quadros[-1]) if quadros else u"",
                         "bloco": u"\n".join(linhas[inicio:j])[-4000:]})
        i = max(j, i + 1)
    return fora


def _ler(caminho_ou_texto, desde=0):
    try:
        if caminho_ou_texto and os.path.isfile(str(caminho_ou_texto)):
            with open(str(caminho_ou_texto), "rb") as f:
                f.seek(max(0, int(desde or 0)))
                return f.read(TETO_DA_LEITURA_BYTES).decode("utf-8", "replace")
    except (OSError, ValueError, TypeError):
        return u""
    return u"%s" % (caminho_ou_texto or u"")


def primeira_excecao(caminho_ou_texto, desde=0):
    exc = excecoes_do_texto(_ler(caminho_ou_texto, desde))
    return exc[0] if exc else None


def ultima_excecao(caminho_ou_texto, desde=0):
    exc = excecoes_do_texto(_ler(caminho_ou_texto, desde))
    return exc[-1] if exc else None


def _cadeia(e):
    vistos, fila = [], [e]
    while fila and len(vistos) < 8:
        x = fila.pop(0)
        if x is None or any(x is v for v in vistos):
            continue
        vistos.append(x)
        fila.extend([getattr(x, "__cause__", None),
                     getattr(x, "__context__", None)])
    return vistos


def _primeira_da_cadeia(e):
    for x in _cadeia(e):
        p = getattr(x, "primeira", None)
        if isinstance(p, dict) and p.get("tipo"):
            return p
    texto = u" ".join(u"%s" % x for x in _cadeia(e))
    i = texto.find(MARCA_DA_PRIMEIRA)
    if i < 0:
        return None
    resto = texto[i + len(MARCA_DA_PRIMEIRA):]
    j = resto.find(MARCA_DA_ULTIMA)
    if j >= 0:
        resto = resto[:j]
    m = _LINHA_DA_EXCECAO.match(resto.strip())
    if not m:
        return None
    msg = (m.group(2) or u"").strip()
    onde = u""
    o = re.search(r"\(([^()]+\.py:\d+ em [^()]+)\)\.?\s*$", msg)
    if o:
        onde = o.group(1)
        msg = msg[:o.start()].strip()
    return {"tipo": m.group(1).split(u".")[-1], "mensagem": msg.rstrip(u"."),
            "onde": onde, "bloco": u""}


def _codigo_de_recurso(texto):
    t = u"%s" % (texto or u"")
    for m in _WINERROR.finditer(t):
        if int(m.group(1)) in CODIGOS_WINDOWS_DE_RECURSO:
            return True
    for m in _ERRNO.finditer(t):
        if int(m.group(1)) in CODIGOS_ERRNO_DE_RECURSO:
            return True
    return False


def _e_recurso_pelo_texto(texto):
    baixo = (u"%s" % (texto or u"")).lower()
    return (any(f in baixo for f in FRASES_DE_RECURSO)
            or _codigo_de_recurso(texto))


def _classe_da_excecao_do_filho(p, volume_conferido=False):
    tipo = u"%s" % (p.get("tipo") or u"")
    texto = u"%s %s" % (tipo, p.get("mensagem") or u"")
    baixo = texto.lower()
    if any(f in baixo for f in FRASES_INELEGIVEIS):
        # GUARDA: depois de `conferir_volume_contornavel` o volume que entrou
        # era 3D de um canal; a frase do NibabelIO aponta o caminho, nao o exame.
        return DETERMINISTICO if volume_conferido else INELEGIVEL
    if tipo in TIPOS_DE_RECURSO or _e_recurso_pelo_texto(texto):
        return RECURSO
    if FRASE_INDETERMINADA in baixo:
        return INDETERMINADA
    return None


def classificar_falha(e):
    try:
        cadeia = _cadeia(e)
        for x in cadeia:
            if type(x).__name__ in TIPOS_DE_TRAVA:
                return TRAVOU
        for x in cadeia:
            if getattr(x, "tempo_limite", False):
                return TRAVOU
        for x in cadeia:
            if type(x).__name__ in TIPOS_INELEGIVEIS:
                return INELEGIVEL
        for x in cadeia:
            if isinstance(x, MemoryError) or type(x).__name__ in TIPOS_DE_RECURSO:
                return RECURSO
        texto = u" ".join(u"%s" % x for x in cadeia)
        baixo = texto.lower()
        if PALAVRA_DA_TRAVA in texto or any(f in baixo for f in
                                            FRASES_DE_TEMPO_LIMITE):
            return TRAVOU
        conferido = any(getattr(x, "volume_conferido", False) for x in cadeia)
        p = _primeira_da_cadeia(e)
        if p is not None:
            return (_classe_da_excecao_do_filho(p, conferido)
                    or DETERMINISTICO)
        if any(t in texto for t in TIPOS_INELEGIVEIS):
            return INELEGIVEL
        if any(f in baixo for f in FRASES_INELEGIVEIS):
            return DETERMINISTICO if conferido else INELEGIVEL
        if any(t in texto for t in TIPOS_DE_RECURSO):
            return RECURSO
        if _e_recurso_pelo_texto(texto):
            return RECURSO
        if FRASE_INDETERMINADA in baixo:
            return INDETERMINADA
    except Exception:
        pass
    return DETERMINISTICO


def sem_caminho_nem_uid(texto):
    t = u"%s" % (texto or u"")
    try:
        import radai_records
        t = radai_records.sem_caminhos(t)
    except Exception:
        pass
    t = _CAMINHO.sub(u"<caminho>", t)
    return _UID.sub(u"<uid>", t)


def _normalizar(texto, teto=200):
    t = sem_caminho_nem_uid(texto).lower()
    t = _NUMERO.sub(u"N", t)
    return _ESPACOS.sub(u" ", t).strip()[:teto]


def causa_da_falha(e):
    p = _primeira_da_cadeia(e)
    if p is not None:
        return (p.get("tipo") or u"", p.get("mensagem") or u"",
                p.get("onde") or u"")
    return (type(e).__name__, u"%s" % e, u"")


def assinatura_da_falha(e, classe=None):
    classe = classe or classificar_falha(e)
    tipo, msg, onde = causa_da_falha(e)
    base = u"%s|%s|%s|%s" % (classe, tipo, _normalizar(msg), _normalizar(onde))
    return hashlib.sha1(base.encode("utf-8")).hexdigest()[:10]


def frase_curta(e, teto=140):
    tipo, msg, _onde_ = causa_da_falha(e)
    t = sem_caminho_nem_uid(u"%s: %s" % (tipo, _ESPACOS.sub(u" ", msg).strip()))
    return t if len(t) <= teto else t[:teto - 1] + u"…"
