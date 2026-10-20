# -*- coding: utf-8 -*-
import time


def duracao(segundos):
    s = max(0.0, float(segundos or 0.0))
    if s < 10:
        return (u"%.1f s" % s).replace(u".", u",")
    s = int(round(s))
    if s < 60:
        return u"%d s" % s
    if s < 3600:
        return u"%dm%02ds" % (s // 60, s % 60)
    return u"%dh%02dm%02ds" % (s // 3600, (s % 3600) // 60, s % 60)


class Cronometro(object):
    def __init__(self, relogio=None):
        self._relogio = relogio or time.monotonic
        self.inicio = self._relogio()
        self.etapas = []
        self._atual = None

    def etapa(self, nome):
        nome = str(nome or u"").strip()
        if not nome or (self._atual is not None and self._atual[0] == nome):
            return None
        fechada = self.fechar()
        self._atual = (nome, self._relogio())
        return fechada

    def fechar(self):
        if self._atual is None:
            return None
        nome, t0 = self._atual
        self._atual = None
        par = (nome, max(0.0, self._relogio() - t0))
        self.etapas.append(par)
        return par

    def soma(self):
        return sum(s for _n, s in self.etapas)

    def total(self):
        return max(0.0, self._relogio() - self.inicio)

    def resumo(self):
        partes = [u"%s %s" % (n, duracao(s)) for n, s in self.etapas]
        return (u"tempo por etapa: %s | soma %s (serie inteira %s)"
                % (u", ".join(partes) or u"-", duracao(self.soma()),
                   duracao(self.total())))


def linha(par):
    return u"   tempo: %s levou %s" % (par[0], duracao(par[1]))
