# -*- coding: utf-8 -*-
import sys
import time

COD_CRANIO = "cranio_ct"
CODIGOS = (COD_CRANIO,)

MODELO_DO_MOTOR = {
    COD_CRANIO: "cranio_buti",
}


def modelos_do_entregue():
    import radai_hnlnl_engine as HN
    return tuple(sorted(set(MODELO_DO_MOTOR.values()) | {HN.IDENT}))


def estruturas_no_full():
    import radai_cranio_engine as CR
    return {COD_CRANIO: tuple(sorted(CR.PARA_O_FULL.values()))}


def estruturas_no_oar():
    import radai_cranio_engine as CR
    return {COD_CRANIO: tuple(sorted(CR.NO_OAR))}


def estruturas_do_motor(cod):
    try:
        oar = list(estruturas_no_oar().get(cod) or ())
        full = list(estruturas_no_full().get(cod) or ())
    except Exception:
        return []
    return oar + [k for k in full if k not in oar]


SEM_PESO = u"sem_peso"
FALHOU = u"falhou"


class Extras(dict):

    def __init__(self):
        dict.__init__(self, orgaos={}, alvos={}, origem={}, observacoes={},
                      tempos=[], falhas=[])

    def vazio(self):
        return not self["orgaos"] and not self["alvos"]


def _registrar_falha(fora, cod, classe, motivo):
    fora["falhas"].append({"motor": u"%s" % cod, "classe": classe,
                           "motivo": (u"%s" % motivo)[:200]})


def falha_de_todos(pedidos, classe, motivo):
    fora = Extras()
    for cod in [c for c in CODIGOS if c in set(pedidos or ())]:
        _registrar_falha(fora, cod, classe, motivo)
    return fora


def falhas_dos_extras(extras):
    try:
        return [dict(f) for f in ((extras or {}).get("falhas") or ())
                if isinstance(f, dict) and f.get("motor")]
    except Exception:
        return []


def conferir_destinos(extras, permitidos_no_oar):
    fora = sorted(set((extras or {}).get("alvos") or {})
                  & set(permitidos_no_oar or ()))
    if fora:
        raise ValueError(u"PAREI: alvo na lista do OAR: %s" % u", ".join(fora))
    return True


def _registrador(log):
    def _log(m):
        if log:
            try:
                log(m)
            except Exception:
                pass
    return _log


def dizer_tempos(nome, tempos, log, inicio=None):
    if not log:
        return
    try:
        soma = sum(float(s) for _e, s in tempos)
        log(u"%s: %s; soma %.1f s" % (
            nome, u"; ".join(u"%s %.1f s" % (e, float(s)) for e, s in tempos),
            soma if inicio is None else (time.time() - inicio)))
    except Exception:
        pass


def motores_na_serie(ref, cruas, motores, device="cpu", log=None,
                   modalidade="CT", python_exe=None):
    import traceback
    _log = _registrador(log)
    fora = Extras()
    pedidos = [c for c in CODIGOS if c in set(motores or ())]
    if not pedidos:
        return fora
    if str(modalidade or "CT").upper() not in ("CT",):
        _log(u"motores do FULL (%s): nao rodam em %s — sao de TC"
             % (u", ".join(pedidos), modalidade))
        return fora
    try:
        import radai_geom
        import radai_output
        grade = radai_geom.Grade.de_sitk(ref)
        base = radai_output.cruas_da_base(cruas)
    except Exception as e:
        motivo = u"%s: %s" % (type(e).__name__, str(e)[:160])
        _log(u"motores do FULL (%s) FALHARAM antes de rodar (%s) — o resto "
             u"da serie segue" % (u", ".join(pedidos), motivo))
        for cod in pedidos:
            _registrar_falha(fora, cod, FALHOU, motivo)
        return fora
    t_total = time.time()

    for cod in pedidos:
        tempos = []
        t0 = time.time()
        try:
            if cod == COD_CRANIO:
                import radai_cranio_engine as CR
                m = CR.segmentar_serie(ref, base, grade, python_exe=python_exe,
                                 dispositivo=device, log=log, tempos=tempos)
                for k, v in m.items():
                    fora["orgaos"][k] = v
                    fora["origem"][k] = cod
                    fora["observacoes"][k] = CR.descricao(k)
        except Exception as e:
            ausente = getattr(sys.modules.get("radai_cranio_engine"),
                              "PesoAusente", None)
            if ausente is not None and isinstance(e, ausente):
                _log(u"motor %s SEM PESO nesta instalacao (%s) — faltam %s; "
                     u"o resto da serie segue"
                     % (cod, str(e)[:200],
                        u", ".join(estruturas_do_motor(cod))))
                _registrar_falha(fora, cod, SEM_PESO, str(e))
            else:
                motivo = u"%s: %s" % (type(e).__name__, str(e)[:160])
                _log(u"motor %s FALHOU (%s) — o resto da serie segue"
                     % (cod, motivo))
                _registrar_falha(fora, cod, FALHOU, motivo)
                try:
                    for linha in traceback.format_exc().strip().splitlines():
                        _log(u"   " + linha)
                except Exception:
                    pass
        tempos.append((u"total", time.time() - t0))
        dizer_tempos(u"motor %s" % cod, tempos[:-1], log, inicio=t0)
        fora["tempos"].append((u"motor %s" % cod, time.time() - t0))
    _log(u"motores do FULL: %d orgao(s), %d alvo(s), soma %.1f s"
         % (len(fora["orgaos"]), len(fora["alvos"]), time.time() - t_total))
    return fora
