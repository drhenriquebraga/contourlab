# -*- coding: utf-8 -*-
import base64
import os
import subprocess
import threading

PRAZO_S = 30

AUMID = (u"{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}"
         u"\\WindowsPowerShell\\v1.0\\powershell.exe")

FRASES = {
    "titulo_ok": u"Radioterapia.AI: série pronta",
    "ok": u"Série …{0}: todas as gravações feitas ({1}). Pronta para o TPS, "
          u"como sugestão não aprovada.",
    "titulo_erro": u"Radioterapia.AI: série não saiu",
    "falhou": u"Série …{0}: falhou (tentativa {1} de {2}). O motivo está no "
              u"log do vigia.",
    "falhou_lote": u"Série …{0}: falhou no «Rodar agora». O motivo está no "
                   u"log da tela.",
    "adiada_recurso": u"Série …{0}: adiada por falta de memória. Volta no fim "
                      u"da fila, sem gastar tentativa.",
    "adiada_trava": u"Série …{0}: adiada por trava. Volta no fim da fila, sem "
                    u"gastar tentativa.",
    "ambiente": u"Série …{0}: erro de ambiente, e o vigia pausou. O motivo "
                u"está no log do vigia.",
    "recusada": u"Série …{0}: não é uma série de contorno (imagem colorida "
                u"ou reconstrução). Não volta à fila.",
    "em_espera": u"Série …{0}: a mesma falha se repetiu em {1} séries. As "
                 u"séries com ela ficam em espera até «Liberar».",
}

ROTULOS_DOS_GRAVADOS = {"oar": u"RadAI_OAR", "full": u"FULL",
                        "fast": u"RadAI_OAR_Fast"}

_DESLIGADA = ("0", "off", "nao", "false", "no")
_ARMADA = [False]
FALHOU = [False]


def ambiente_permite():
    try:
        return (os.name == "nt" and str(os.environ.get(
            "RADAI_NOTIFICACAO", "1")).strip().lower() not in _DESLIGADA)
    except Exception:
        return False


def armar(sim=True):
    _ARMADA[0] = bool(sim)


def ligada():
    return bool(_ARMADA[0]) and ambiente_permite()


def rotulo_do_gravado(cod):
    return ROTULOS_DOS_GRAVADOS.get(str(cod), str(cod).upper())


def _sem_caminho(v):
    try:
        t = u"%s" % (v,)
    except Exception:
        return u"?"
    if u"\\" in t or u"/" in t or u":" in t:
        return u"?"
    return t[:80]


def frase(chave, *args, **kw):
    pt = FRASES.get(chave, chave)
    alvo = pt
    vals = tuple(_sem_caminho(a) for a in args)
    try:
        idioma = kw.get("idioma")
        if not idioma:
            import radai_languages as _rl
            idioma = _rl.padrao_efetivo()
        if idioma and not str(idioma).lower().startswith("pt"):
            import radai_phrases as _rp
            alvo = _rp.construir().get(idioma, {}).get(
                _rp.normalizar(pt), pt)
    except Exception:
        alvo = pt
    try:
        return alvo.format(*vals)
    except Exception:
        try:
            return pt.format(*vals)
        except Exception:
            return pt


def _xml(t):
    return (u"%s" % t).replace(u"&", u"&amp;").replace(u"<", u"&lt;") \
        .replace(u">", u"&gt;").replace(u'"', u"&quot;")


def script(titulo, texto):
    xml = (u"<toast><visual><binding template=\"ToastGeneric\">"
           u"<text>%s</text><text>%s</text></binding></visual>"
           u"<audio src=\"ms-winsoundevent:Notification.Default\"/></toast>"
           % (_xml(titulo), _xml(texto)))
    return (u"$ErrorActionPreference = 'Stop'\n"
            u"[void][Windows.UI.Notifications.ToastNotificationManager, "
            u"Windows.UI.Notifications, ContentType = WindowsRuntime]\n"
            u"[void][Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom."
            u"XmlDocument, ContentType = WindowsRuntime]\n"
            u"$x = New-Object Windows.Data.Xml.Dom.XmlDocument\n"
            u"$x.LoadXml('%s')\n"
            u"$t = New-Object Windows.UI.Notifications.ToastNotification $x\n"
            u"[Windows.UI.Notifications.ToastNotificationManager]::"
            u"CreateToastNotifier('%s').Show($t)\n"
            % (xml.replace(u"'", u"''"), AUMID))


def mostrar(titulo, texto):
    cmd = ["powershell.exe", "-NoProfile", "-NonInteractive",
           "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden",
           "-EncodedCommand", base64.b64encode(
               script(titulo, texto).encode("utf-16-le")).decode("ascii")]
    try:
        r = subprocess.run(cmd, stdin=subprocess.DEVNULL,
                           stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                           timeout=PRAZO_S,
                           creationflags=getattr(subprocess,
                                                 "CREATE_NO_WINDOW", 0))
    except subprocess.TimeoutExpired:
        return False, u"o PowerShell passou de %d s" % PRAZO_S
    except Exception as e:
        return False, u"%s: %s" % (type(e).__name__, str(e)[:120])
    if r.returncode != 0:
        err = (r.stderr or b"").decode("utf-8", "replace").strip()
        return False, u"PowerShell saiu com %d (%s)" % (
            r.returncode, (err.splitlines() or [u""])[-1][:120])
    return True, u""


def em_segundo_plano(titulo, texto, mostrar_fn=None, log=None):
    try:
        ok, motivo = (mostrar_fn or mostrar)(titulo, texto)
    except Exception as e:
        ok, motivo = False, u"%s: %s" % (type(e).__name__, str(e)[:120])
    try:
        if not ok and not FALHOU[0]:
            if log:
                log("notificacao do Windows: nao consegui mostrar (%s) — o "
                    "programa segue; o resultado da serie esta no log e no "
                    "painel" % motivo)
        elif ok and FALHOU[0]:
            if log:
                log("notificacao do Windows: voltou a sair")
    except Exception:
        pass
    FALHOU[0] = not ok


def disparar(titulo, texto, mostrar_fn=None, log=None):
    try:
        threading.Thread(target=em_segundo_plano,
                         args=(titulo, texto, mostrar_fn, log),
                         name="radai_notificacao", daemon=True).start()
        return True
    except Exception:
        return False


def notificar(chave_titulo, chave_texto, *args, **kw):
    try:
        if not ligada():
            return False
        idioma = kw.get("idioma")
        titulo = frase(chave_titulo, idioma=idioma)
        texto = frase(chave_texto, *args, idioma=idioma)
        return disparar(titulo, texto, mostrar_fn=kw.get("mostrar"),
                        log=kw.get("log"))
    except Exception:
        return False
