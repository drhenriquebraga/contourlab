# -*- coding: utf-8 -*-
import os
import time
import traceback

VERSAO_SAIDA = "2.0"


class UniaoDeCruas(object):

    def __init__(self, mapas):
        self._mapas = [m for m in mapas if m]

    def __iter__(self):
        vistos = set()
        for m in self._mapas:
            for k in m:
                if k not in vistos:
                    vistos.add(k)
                    yield k

    def keys(self):
        return list(self)

    def __len__(self):
        n = 0
        for _ in self:
            n += 1
        return n

    def __contains__(self, k):
        for m in self._mapas:
            if k in m:
                return True
        return False

    def __getitem__(self, k):
        for m in reversed(self._mapas):
            if k in m:
                return m[k]
        raise KeyError(k)


class _VistaDeRotulos(object):

    def __init__(self, pares):
        self._pares = dict(pares)

    def __iter__(self):
        return iter(sorted(self._pares))

    def keys(self):
        return sorted(self._pares)

    def __len__(self):
        return len(self._pares)

    def __contains__(self, k):
        return k in self._pares

    def __getitem__(self, k):
        mapa, rotulo = self._pares[k]
        return mapa[rotulo]


def vocabulario_do_full(cruas, ts_map=None, log=None):
    import radai_sets
    import radai_names
    try:
        import radai_tasks as _rt
        _fam = _rt.familia_da_task
    except Exception:
        _fam = lambda t: t
    ordem_full = list(radai_sets.TASKS_DO_FULL)

    def _prioridade(task):
        f = _fam(task)
        if f in ("total", "total_mr"):
            return (0, task)
        if f in ordem_full:
            return (1 + ordem_full.index(f), task)
        return (99, task)

    pares, repetidos = {}, []
    for task in sorted((cruas or {}), key=_prioridade):
        mapa = cruas[task]
        if not mapa or not radai_sets.task_do_full(task):
            continue
        fam = _fam(task)
        base = fam in ("total", "total_mr")
        for rotulo in mapa:
            if not radai_sets.rotulo_vai_ao_full(task, rotulo):
                continue
            chave = radai_names.canonico(rotulo)
            if base and chave == "heart":
                chave = radai_names.CHAVE_DO_CORACAO_DO_MODELO
            dono = (ts_map or {}).get(chave)
            if dono and fam not in dono and task not in dono:
                repetidos.append((chave, task))
                continue
            if chave in pares:
                repetidos.append((chave, task))
                continue
            pares[chave] = (mapa, rotulo)
    if log and repetidos:
        try:
            log(u"FULL: %d rotulo(s) repetido(s) entre tasks ficaram com a "
                u"fonte declarada (%s)" % (
                    len(repetidos), u", ".join(
                        u"%s de %s" % (c, t) for c, t in repetidos[:6])))
        except Exception:
            pass
    return _VistaDeRotulos(pares)


def insumos_fora_do_full(cruas):
    import radai_sets
    pares = {}
    for task in sorted(cruas or {}):
        mapa = cruas[task]
        if not mapa or not radai_sets.task_do_full(task):
            continue
        for rotulo in mapa:
            if radai_sets.rotulo_vai_ao_full(task, rotulo):
                continue
            if radai_sets.rotulo_vai_ao_plugin(task, rotulo):
                continue
            pares["%s:%s" % (task, rotulo)] = (mapa, rotulo)
    return _VistaDeRotulos(pares)


def vista_do_plugin(task, mapa):
    import radai_sets
    import radai_names
    pares = {}
    for rotulo in (mapa or {}):
        if not radai_sets.rotulo_vai_ao_plugin(task, rotulo):
            continue
        chave = radai_names.canonico(rotulo)
        if chave not in pares:
            pares[chave] = (mapa, rotulo)
    return _VistaDeRotulos(pares)


class Saida(object):

    def __init__(self, engine, stage, destino, rs_name, tasks=(), versao="",
                 suavizar_mm=1.5, log=None, copiar=None, grade=None,
                 modalidade=None):
        self.engine = engine
        self.stage = str(stage)
        self.destino = str(destino)
        self.rs_name = str(rs_name)
        self.tasks = tasks
        self.versao = str(versao)
        self.suavizar_mm = suavizar_mm
        self._log = log
        self._copiar = copiar
        self._grade = grade
        self.modalidade = (str(modalidade).strip().upper()
                           if modalidade else None)
        self.gravados = []

    def mapa_de_rotulos(self, cruas, uid, pasta_serie=None, protocolos=(),
                        achados=()):
        import radai_rotulos
        _carregar = getattr(self.engine, "load_sitk", None)
        ref = None
        try:
            if _carregar is not None:
                ref = _carregar(self.stage)
        except Exception:
            ref = None
        alvo = radai_rotulos.gravar(pasta_serie or self.destino, uid, cruas,
                                    ref=ref, protocolos=protocolos,
                                    modalidade=self.modalidade or u"",
                                    achados=achados, versao=self.versao)
        self.log(u"estudo 3D: mapa de rotulos gravado em _RadAI (%s), sem "
                 u"RTSTRUCT; protocolos: %s"
                 % (os.path.basename(alvo),
                    u", ".join(protocolos) or u"nenhum"))
        return alvo

    def log(self, msg):
        if self._log:
            try:
                self._log(msg)
            except Exception:
                pass

    def _tracinho(self):
        try:
            for linha in traceback.format_exc().strip().splitlines():
                self.log("   " + linha)
        except Exception:
            pass

    def grade(self):
        if self._grade is None:
            lida = self.serie_lida()
            if lida is not None:
                self._grade = lida[0]
                return self._grade
            import radai_geom
            _carregar = getattr(self.engine, "load_sitk", None)
            if _carregar is None:
                import engine as _m
                _carregar = _m.load_sitk
            self._grade = radai_geom.Grade.de_sitk(_carregar(self.stage))
        return self._grade

    def serie_lida(self):
        if getattr(self, "_serie_lida", None) is None:
            self._serie_lida = False
            try:
                import radai_geom
                _carregar = getattr(self.engine, "load_sitk", None)
                if _carregar is None:
                    import engine as _m
                    _carregar = _m.load_sitk
                import SimpleITK as _sitk
                img = _carregar(self.stage)
                self._serie_lida = (radai_geom.Grade.de_sitk(img),
                                    _sitk.GetArrayFromImage(img))
            except Exception:
                self._serie_lida = False
        return self._serie_lida or None

    def externo_da_serie(self):
        ext = getattr(self, "_externo", None)
        if ext is None:
            self._externo = False
            if self.modalidade == "CT":
                lida = self.serie_lida()
                if lida is not None:
                    t0 = time.time()
                    try:
                        import radai_skin
                        pronto = radai_skin.contorno_externo(
                            lida[1], lida[0], log=None, com_o_corpo=True)[1]
                        if pronto is not None:
                            self._externo = pronto
                            self.log(u"contorno externo da serie: calculado "
                                     u"uma vez para os conjuntos ao lado "
                                     u"(%.1f s)" % (time.time() - t0))
                    except Exception as e:
                        self.log(u"contorno externo da serie: nao calculei "
                                 u"(%s) — cada conjunto calcula o seu"
                                 % type(e).__name__)
            ext = self._externo
        return ext if ext is not False else None

    def _alvo(self, infixo):
        return os.path.join(self.destino,
                            self.rs_name.replace("RS_RadAI_",
                                                 "RS_RadAI_" + infixo))

    def _gravar_arquivo(self, rt_local, alvo):
        if self._copiar:
            self._copiar(rt_local, alvo)
        else:
            import shutil
            import radai_sets
            parcial = radai_sets.nome_parcial(alvo)
            try:
                shutil.copy2(rt_local, parcial)
                os.replace(parcial, alvo)
            finally:
                try:
                    if os.path.exists(parcial):
                        os.remove(parcial)
                except Exception:
                    pass

    def conjunto(self, cod, masks, origem_str, origem=None, derivar=False,
                 rotulo=None, suavizar_mm=None, observacoes=None,
                 construcoes=None):
        if not masks or not len(masks):
            return None
        import radai_sets
        try:
            proc = dict((k, origem_str) for k in masks)
            proc.update(origem or {})
            reg = radai_sets.POR_COD[cod]
            extra = {}
            if self.modalidade:
                extra["modalidade"] = self.modalidade
            if observacoes:
                if _aceita(self.engine.build_rtstruct, "observacoes"):
                    extra["observacoes"] = dict(observacoes)
                else:
                    self.log("o motor instalado nao aceita a descricao por "
                             "ROI (observacoes): %s sai SEM ela no "
                             "ROIObservationDescription" % cod)
            # GUARDA: so o que o conjunto declara conter deixa de alarmar.
            if construcoes and _aceita(self.engine.build_rtstruct,
                                       "construcoes"):
                extra["construcoes"] = dict(construcoes)
            _meta = None
            if _aceita(self.engine.build_rtstruct, "meta"):
                _meta = {}
                extra["meta"] = _meta
            if (not reg.get("cru", False)
                    and _aceita(self.engine.build_rtstruct, "serie")):
                _lida = self.serie_lida()
                if _lida is not None:
                    extra["serie"] = _lida
            if (not reg.get("cru", False)
                    and _aceita(self.engine.build_rtstruct, "externo")):
                _ext = self.externo_da_serie()
                if _ext is not None:
                    extra["externo"] = _ext
            _t_conj = time.time()
            rt, nomes = self.engine.build_rtstruct(
                self.stage, masks, tasks=self.tasks,
                versao_worker=self.versao + " " + reg["nome"],
                origem=proc, derivar=derivar, log=self._log,
                sufixo_do_conjunto=reg["sufixo"],
                suavizar_mm=(self.suavizar_mm if suavizar_mm is None
                             else suavizar_mm),
                cru=bool(reg.get("cru", False)),
                descontar=bool(reg.get("desconta", False)),
                rotulo=(rotulo or radai_sets.rotulo_dicom(cod)), **extra)
            _s_conj = time.time() - _t_conj
            alvo = self._alvo(reg["infixo"])
            try:
                self._gravar_arquivo(rt, alvo)
            finally:
                _apagar_temp_do_rs(rt, self.engine)
            self.gravados.append(cod)
            self.log("%s: %d estrutura(s) em %s"
                     % (reg["nome"], len(nomes), os.path.basename(alvo)))
            _et = list((_meta or {}).get("etapas") or [])
            if _et:
                try:
                    self.log(u"  %s em %.0f s, por passo: %s" % (
                        reg["nome"], _s_conj, u"; ".join(
                            u"%s %.1f s" % (n, s) for n, s in _et)))
                except Exception:
                    pass
            return alvo
        except Exception as e:
            self.log("nao consegui gravar o conjunto %s (%s) — o contorno "
                     "entregue nao foi afetado" % (cod, str(e)[:120]))
            self._tracinho()
            return None

    def totalsegmentator_cru(self, cruas):
        juntas = UniaoDeCruas([m for m in (cruas or {}).values() if m])
        if not len(juntas):
            return None
        return self.conjunto("ts", juntas, "ts", suavizar_mm=0.0)

    def full_e_oar(self, cruas, volume_hu=None, cads=None, cervicais=None,
                   torax=None, modo="auto", oar_fora=None, extras=None,
                   protocolo=None):
        import radai_sets
        modo = normalizar_modo(modo)
        if modo == MODO_FAST:
            if protocolo:
                self.log(u"STUDY_Fast: o protocolo proprio vale so no "
                         u"PERSONALIZADO; foi IGNORADO no modo FAST")
            if oar_fora:
                self.log(u"OAR_Fast: a lista de estruturas tiradas do OAR "
                         u"(%d) foi IGNORADA no modo FAST — sem FULL, tirar "
                         u"do OAR_Fast apagaria a estrutura da serie"
                         % len(list(oar_fora)))
            if cervicais:
                self.log(u"OAR_Fast: os %d nivel(is) cervical(is) nao entram "
                         u"(so vao ao FULL, e o FAST nao grava FULL)"
                         % len(cervicais))
            return self._oar_fast(cruas, volume_hu=volume_hu, cads=cads,
                                  torax=torax)
        _unioes_proprias = []
        if protocolo:
            permitidos, _tiradas, _unioes_proprias = permitidos_do_protocolo(
                protocolo, oar_fora, log=self.log)
        else:
            permitidos, _tiradas = permitidos_do_oar(oar_fora, log=self.log,
                                                     engine=self.engine)
        _nomes_proprios = radai_sets.nomes_proprios_em_vigor()
        t0 = time.time()
        try:
            engine = self.engine
            vocab = vocabulario_do_full(cruas, getattr(engine, "TS_MAP", {}),
                                        log=self._log)
            if not len(vocab):
                raise RuntimeError(
                    u"nenhuma estrutura das tasks que alimentam o FULL nesta "
                    u"serie (tasks: %s)" % u", ".join(sorted(cruas or {})))
            masks, origem = engine.curar(vocab, {"cads": dict(cads or {})},
                                         log=self._log)
            masks, origem = _juntar_orgaos_dos_motores(masks, origem, extras,
                                                       self.log)
            grade = self.grade()
            extra_pre = {}
            if _aceita(engine.preparar_full, "cru"):
                extra_pre["cru"] = insumos_fora_do_full(cruas)
            else:
                self.log(u"o motor instalado nao aceita os insumos fora do "
                         u"FULL (cru): a parede toracica sai sem o recorte "
                         u"pelo mediastino")
            if torax is not None:
                if _aceita(engine.preparar_full, "torax"):
                    extra_pre["torax"] = torax
                else:
                    self.log(u"o motor instalado nao aceita o pedido do "
                             u"Estudo Torax (torax): a anatomia decide a "
                             u"parede toracica nesta serie")
            if (_aceita(engine.preparar_full, "protegidas")
                    and hasattr(engine, "protegidas_da_origem")):
                extra_pre["protegidas"] = engine.protegidas_da_origem(origem)
            masks, meta_pre = engine.preparar_full(
                masks, grade=grade, log=self._log, volume_hu=volume_hu,
                modalidade=self.modalidade, **extra_pre)
            origem = dict(origem or {})
            observacoes = dict(meta_pre.get("observacoes") or {})
            construcoes = dict(meta_pre.get("construcoes") or {})
            fora_regiao = dict(meta_pre.get("fora_do_oar_por_regiao") or {})
            if protocolo:
                # GUARDA: o protocolo proprio escolhe as estruturas; da regiao
                # so vale a que a anatomia exige (sem ela a estrutura e falsa).
                _exigidas = getattr(engine, "REGIAO_EXIGIDA_NO_OAR", None) or {}
                fora_regiao = dict((k, m) for k, m in fora_regiao.items()
                                   if k in _exigidas and k in permitidos)
            if fora_regiao:
                permitidos = frozenset(set(permitidos) - set(fora_regiao))
            # GUARDA: os niveis (Lvl_*) vao so ao FULL; ao OAR vao so a uniao e
            # as parotidas do VIII, pela lista `radai_sets.PERMITIDOS_NO_OAR`.
            sufixo_por_roi = {}
            fora_substituidas = {}
            if cervicais:
                try:
                    try:
                        import radai_hnlnl as _hn
                        _da_uniao = (_hn.NOME_DA_UNIAO,
                                     _hn.NOME_DA_UNIAO_NEUTRA)
                    except Exception:
                        _hn, _da_uniao = None, (u"LNL_UNION", u"LNL_Union")
                    for _n in cervicais:
                        masks[_n] = cervicais[_n]
                        origem[_n] = "hnlnl"
                        construcoes[_n] = {
                            "suavizar_mm": 0.0, "recortar_por": (),
                            "contem": ((u"Lvl_", u"LNL")
                                       if _n in _da_uniao else ()),
                            "descricao": u""}
                    try:
                        observacoes.update(
                            _hn.observacoes_dos_niveis(cervicais) or {})
                    except Exception as e:
                        self.log(u"nao consegui montar a descricao dos niveis "
                                 u"(%s) — eles entram no FULL sem ela"
                                 % str(e)[:120])
                    self.log(u"FULL: +%d nivel(is) cervical(is)"
                             % len(cervicais))
                    _ivb = dict((_k, cervicais[_k]) for _k in getattr(
                        _hn, "CLAVICULA_DO_IVB", {}) if _k in cervicais)
                    for _k in _ivb:
                        construcoes[_k]["acabamento"] = _hn.acabamento_do_ivb
                    for _u in _da_uniao:
                        if _u in construcoes:
                            construcoes[_u]["acabamento"] = (
                                _hn.acabamento_da_uniao_sem_a_clavicula(
                                    _ivb, descricao_original=observacoes.get(_u)))
                            _m, _d, _i = construcoes[_u]["acabamento"](
                                _u, masks[_u], masks, grade, log=self.log)
                            if _m is not None:
                                masks[_u] = _m
                            if _d:
                                observacoes[_u] = _d
                    _subst = _parotidas_do_viii_no_full(
                        _hn, cervicais, masks, grade, self.log)
                    for _lado, (_chave, _m, _ts) in _subst.items():
                        masks[_chave] = _m
                        origem[_chave] = "hnlnl"
                        # GUARDA: recortada de novo pelo ECM ja suavizado,
                        # para a sobreposicao com o ECM entregue ser zero.
                        construcoes[_chave] = {
                            "suavizar_mm": 0.0,
                            "recortar_por": (_hn.ECM_DO_FULL[_lado],),
                            "contem": (), "descricao": u""}
                        observacoes[_chave] = _hn.descricao_da_parotida(_lado)
                    # GUARDA: estudo MARCADO pela regua (a uniao desce alem
                    # do pescoco) nao leva a uniao ao OAR.
                    _ext = getattr(cervicais, "extensao", None) or {}
                    if _ext and not _ext.get("ok", True):
                        for _u in _da_uniao:
                            if _u in cervicais:
                                fora_substituidas[_u] = (
                                    u"estudo marcado pela regua dos niveis: "
                                    u"%s" % _ext.get("motivo", u"?"))
                    if fora_substituidas:
                        permitidos = frozenset(
                            set(permitidos) - set(fora_substituidas))
                except Exception as e:
                    self.log(u"nao consegui juntar os niveis cervicais ao "
                             u"FULL (%s)" % str(e)[:120])
                    self._tracinho()
            try:
                permitidos = _parotida_do_ts_so_no_full(
                    masks, sufixo_por_roi, observacoes, fora_substituidas,
                    permitidos)
            except Exception as e:
                permitidos = frozenset(k for k in permitidos if not str(
                    k).startswith("parotid_gland_"))
                self.log(u"a parotida do TotalSegmentator fica fora do OAR, "
                         u"sem o sufixo _ts no FULL (%s)" % str(e)[:120])
            _juntar_alvos_dos_motores(masks, origem, construcoes,
                                      observacoes, extras, permitidos,
                                      self.log)
            reg = radai_sets.POR_COD["full"]
            extra = {}
            if self.modalidade:
                extra["modalidade"] = self.modalidade
            meta = {"devolver_mascaras": bool(
                getattr(self, "devolver_mascaras", False))}
            if meta_pre.get("derivadas") is not None:
                meta["derivadas"] = dict(meta_pre["derivadas"])
            if sufixo_por_roi:
                meta["sufixo_por_roi"] = dict(sufixo_por_roi)
            self.meta_do_full = meta
            meta["nao_sairam"] = list(meta_pre.get("nao_sairam") or [])
            meta["faltou"] = dict(meta_pre.get("faltou") or {})
            meta["tempos_pre"] = list(meta_pre.get("tempos") or [])
            meta["regras_de_gravacao"] = list(
                meta_pre.get("regras_de_gravacao") or [])
            for _nome, _cm3, _d in list(getattr(cervicais, "ilhas", None)
                                        or []):
                meta["regras_de_gravacao"].append({
                    "regra": u"NIV ilhas dos niveis cervicais",
                    "nome": _nome, "cm3": _cm3, "inteira": False,
                    "motivo": u"ilha a %.0f mm do corpo principal" % _d})
            meta["ilhas_em_revisao"] = list(
                meta_pre.get("ilhas_em_revisao") or [])
            if (meta_pre.get("externo") is not None
                    and _aceita(engine.build_rtstruct, "externo")):
                extra["externo"] = meta_pre["externo"]
            if meta_pre.get("externo") is not None:
                self._externo = meta_pre["externo"]
            if _aceita(engine.build_rtstruct, "serie"):
                _lida = self.serie_lida()
                if _lida is not None:
                    extra["serie"] = _lida
            t_full = time.time()
            if _aceita(engine.build_rtstruct, "adiar"):
                extra["adiar"] = True
            preparo, nomes_full = engine.build_rtstruct(
                self.stage, masks, tasks=self.tasks,
                versao_worker=self.versao + " " + reg["nome"],
                origem=origem, derivar=True, log=self._log,
                sufixo_do_conjunto=reg["sufixo"],
                suavizar_mm=self.suavizar_mm,
                cru=bool(reg.get("cru", False)),
                descontar=bool(reg.get("desconta", False)),
                rotulo=radai_sets.rotulo_dicom(reg["cod"]),
                observacoes=observacoes,
                construcoes=construcoes,
                exigir_grade=True,
                selecao=permitidos,
                meta=meta, **extra)
            del masks
            try:
                meta["ilhas_em_revisao"] = _ilhas_do_arquivo(
                    meta.get("ilhas_em_revisao") or [], nomes_full,
                    log=self._log)
                _dizer_fora_por_regiao(fora_regiao, nomes_full, self.log,
                                       u"OAR", u"fica no FULL", engine=engine)
                for _k, _motivo in sorted(fora_substituidas.items()):
                    self.log(u"OAR: %s nao entra (%s); fica no FULL"
                             % (nomes_full.get(_k, _k), _motivo))
                t_oar = time.time()
                meta_oar = {"versao_worker": (
                    self.versao + " " + radai_sets.POR_COD["oar"]["nome"])}
                # GUARDA: o OAR sai das mascaras finais ANTES de o FULL virar
                # contorno; se o FULL estoura a memoria, o entregue ja esta
                # gravado inteiro.
                _ex_sel = {}
                if ((_nomes_proprios or _unioes_proprias)
                        and _aceita(engine.selecionar_do_full, "nomes")):
                    _ex_sel = {"nomes": _nomes_proprios,
                               "unioes": _unioes_proprias}
                rt_oar, nomes_oar, fora = engine.selecionar_do_full(
                    preparo, nomes_full, permitidos,
                    log=self._log, meta=meta_oar, **_ex_sel)
                alvo_oar, study_vazio = None, None
                if not nomes_oar:
                    # GUARDA: STUDY vazio (a RM com so o Brain_ai) nao derruba a serie; o FULL sai e ela fica pronta.
                    _apagar_temp_do_oar(rt_oar, engine)
                    study_vazio = (u"nenhuma das %d estrutura(s) do FULL esta "
                                   u"na lista do STUDY" % len(nomes_full))
                    self.log(u"STUDY: saiu vazio (%s) e nao e gravado; o FULL "
                             u"e gravado e a serie fica pronta so com ele"
                             % study_vazio)
                else:
                    alvo_oar = self._alvo("")
                    try:
                        self._gravar_arquivo(rt_oar, alvo_oar)
                    finally:
                        _apagar_temp_do_oar(rt_oar, engine)
                    self.gravados.append("oar")
                t_gr_full = time.time()
                if alvo_oar:
                    self.log(u"%s: %d estrutura(s) em %s (gravado antes do "
                             u"FULL, em %.1f s)"
                             % (radai_sets.POR_COD["oar"]["nome"],
                                len(nomes_oar), os.path.basename(alvo_oar),
                                t_gr_full - t_oar))
                alvo_full = self._alvo(reg["infixo"])
                parcial, full_gravado = None, alvo_full
                try:
                    rt_full = preparo
                    if hasattr(preparo, "gravar"):
                        rt_full, nomes_full = preparo.gravar()
                    self._gravar_arquivo(rt_full, alvo_full)
                except Exception as e_full:
                    if not alvo_oar:
                        raise
                    full_gravado = None
                    nomes_full = {}
                    parcial = {"conjunto": "full",
                               "motivo": (u"o FULL nao foi gravado (%s); o "
                                          u"OAR ja estava gravado inteiro e "
                                          u"ficou"
                                          % motivo_do_erro(e_full)[:200])}
                    self.log(u"SERIE PARCIAL: %s" % parcial["motivo"])
                    self._tracinho()
            finally:
                if hasattr(preparo, "liberar"):
                    preparo.liberar()
                _apagar_temp_do_rs(getattr(preparo, "caminho", preparo),
                                   engine)
            if full_gravado is not None:
                self.gravados.append("full")
                self.log(u"%s: %d estrutura(s) em %s"
                         % (reg["nome"], len(nomes_full),
                            os.path.basename(alvo_full)))
            tempos = list(meta_pre.get("tempos") or [])
            tempos.append((u"montagem e gravacao do FULL",
                           (t_oar - t_full) + (time.time() - t_gr_full)))
            tempos.append((PASSO_DO_OAR, t_gr_full - t_oar))
            try:
                self.log(u"FULL/OAR em %.0f s: %s" % (
                    time.time() - t0, u"; ".join(
                        u"%s %.1f s" % (n, s) for n, s in tempos)))
                _et = list(meta.get("etapas") or [])
                if _et:
                    self.log(u"  montagem do FULL por passo: %s" % u"; ".join(
                        u"%s %.1f s" % (n, s) for n, s in _et))
                _et_oar = list(meta_oar.get("etapas") or [])
                if _et_oar:
                    self.log(u"  gravacao do OAR por passo: %s" % u"; ".join(
                        u"%s %.1f s" % (n, s) for n, s in _et_oar))
            except Exception:
                pass
            etapas = [{"etapa": u"%s" % n, "segundos": round(float(s), 1),
                       PARTE_DE: PAI_DOS_PASSOS} for n, s in tempos]
            etapas.extend({"etapa": u"FULL: %s" % n,
                           "segundos": round(float(s), 1),
                           PARTE_DE: u"montagem e gravacao do FULL"}
                          for n, s in list(meta.get("etapas") or []))
            etapas.extend({"etapa": u"OAR: %s" % n,
                           "segundos": round(float(s), 1),
                           PARTE_DE: PASSO_DO_OAR}
                          for n, s in list(meta_oar.get("etapas") or []))
            return {"oar": alvo_oar, "full": full_gravado,
                    "estruturas": sorted((nomes_oar or {}).values()),
                    "estruturas_full": sorted(nomes_full.values()),
                    "fora": list(fora or ()), "segundos": time.time() - t0,
                    "tempos": tempos, "etapas": etapas,
                    "modo": modo, "entregue": alvo_oar or full_gravado,
                    "study_vazio": study_vazio,
                    "oar_fora": list(_tiradas),
                    "oar_fora_por_regiao": dict(fora_regiao,
                                                **fora_substituidas),
                    "oar_fora_por_substituicao": dict(fora_substituidas),
                    "parcial": parcial}
        except Exception as e:
            motivo = motivo_do_erro(e)
            self.log(u"O CONJUNTO ENTREGUE NAO SAIU (FULL e OAR): %s"
                     % motivo[:200])
            self._tracinho()
            raise RuntimeError(u"conjunto entregue (FULL/OAR) nao saiu: %s"
                               % motivo[:300]) from e

    def _oar_fast(self, cruas, volume_hu=None, cads=None, torax=None):
        import radai_sets
        t0 = time.time()
        reg = radai_sets.POR_COD["fast"]
        alvo = radai_sets.PERMITIDOS_NO_OAR_FAST
        try:
            engine = self.engine
            vocab = vocabulario_do_full(cruas, getattr(engine, "TS_MAP", {}),
                                        log=self._log)
            if not len(vocab):
                raise RuntimeError(
                    u"nenhuma estrutura das tasks que alimentam o FULL nesta "
                    u"serie (tasks: %s)" % u", ".join(sorted(cruas or {})))
            masks, origem = engine.curar(vocab, {"cads": dict(cads or {})},
                                         log=self._log)
            if any(str(k).startswith("parotid_gland_") for k in masks):
                self.log(u"OAR_Fast: sem parotida — a do OAR vem so dos "
                         u"niveis cervicais, que o FAST nao roda; a do "
                         u"TotalSegmentator nao vai ao arquivo")
            grade = self.grade()
            extra_pre = {"para": alvo}
            if _aceita(engine.preparar_full, "cru"):
                extra_pre["cru"] = insumos_fora_do_full(cruas)
            if torax is not None and _aceita(engine.preparar_full, "torax"):
                extra_pre["torax"] = torax
            if (_aceita(engine.preparar_full, "protegidas")
                    and hasattr(engine, "protegidas_da_origem")):
                extra_pre["protegidas"] = engine.protegidas_da_origem(origem)
            if not _aceita(engine.preparar_full, "para"):
                raise RuntimeError(
                    u"o motor instalado nao aceita o filtro do FAST (para=) — "
                    u"o OAR_Fast nao e montado sem ele")
            masks, meta_pre = engine.preparar_full(
                masks, grade=grade, log=self._log, volume_hu=volume_hu,
                modalidade=self.modalidade, **extra_pre)
            origem = dict(origem or {})
            observacoes = dict(meta_pre.get("observacoes") or {})
            construcoes = dict(meta_pre.get("construcoes") or {})
            filtro = dict(meta_pre.get("filtro") or {})
            fora_regiao = dict(
                (k, m) for k, m in dict(
                    meta_pre.get("fora_do_oar_por_regiao") or {}).items()
                if k in alvo)
            if fora_regiao:
                alvo = frozenset(set(alvo) - set(fora_regiao))
            gravar = alvo
            extra = {}
            if self.modalidade:
                extra["modalidade"] = self.modalidade
            meta = {"devolver_mascaras": bool(
                getattr(self, "devolver_mascaras", False))}
            if meta_pre.get("derivadas") is not None:
                meta["derivadas"] = dict(meta_pre["derivadas"])
            self.meta_do_fast = meta
            meta["nao_sairam"] = list(meta_pre.get("nao_sairam") or [])
            meta["faltou"] = dict(meta_pre.get("faltou") or {})
            meta["tempos_pre"] = list(meta_pre.get("tempos") or [])
            meta["regras_de_gravacao"] = list(
                meta_pre.get("regras_de_gravacao") or [])
            meta["ilhas_em_revisao"] = list(
                meta_pre.get("ilhas_em_revisao") or [])
            meta["filtro"] = filtro
            if (meta_pre.get("externo") is not None
                    and _aceita(engine.build_rtstruct, "externo")):
                extra["externo"] = meta_pre["externo"]
            if meta_pre.get("externo") is not None:
                self._externo = meta_pre["externo"]
            if _aceita(engine.build_rtstruct, "serie"):
                _lida = self.serie_lida()
                if _lida is not None:
                    extra["serie"] = _lida
            _nomes_proprios = radai_sets.nomes_proprios_em_vigor()
            if _nomes_proprios and _aceita(engine.build_rtstruct,
                                           "nomes_do_entregue"):
                extra["nomes_do_entregue"] = _nomes_proprios
            decimar = getattr(engine, "DECIMACAO_FAST_MM", 0.2)
            t_rs = time.time()
            rt, nomes = engine.build_rtstruct(
                self.stage, masks, tasks=self.tasks,
                versao_worker=self.versao + " " + reg["nome"],
                origem=origem, derivar=True, log=self._log,
                sufixo_do_conjunto=reg["sufixo"],
                suavizar_mm=self.suavizar_mm,
                cru=False, descontar=bool(reg.get("desconta", False)),
                rotulo=reg["rotulo_dicom"],
                observacoes=observacoes, construcoes=construcoes,
                exigir_grade=True, selecao=alvo, meta=meta,
                gravar=gravar, compostos_inteiros=True,
                decimar_mm=decimar, modo=MODO_FAST, **extra)
            if not nomes:
                _apagar_temp_do_oar(rt, engine)
                raise RuntimeError(u"o OAR_Fast saiu vazio")
            meta["ilhas_em_revisao"] = _ilhas_do_arquivo(
                meta.get("ilhas_em_revisao") or [], nomes, log=self._log)
            _dizer_fora_por_regiao(fora_regiao, nomes, self.log, u"OAR_Fast",
                                   u"nao vai ao arquivo", engine=engine)
            t_grav = time.time()
            try:
                alvo_fast = self._alvo(reg["infixo"])
                self._gravar_arquivo(rt, alvo_fast)
            finally:
                _apagar_temp_do_oar(rt, engine)
            self.gravados.append("fast")
            dec = dict(meta.get("decimacao") or {})
            self.log(u"%s: %d estrutura(s) em %s (%s pontos -> %s)"
                     % (reg["nome"], len(nomes), os.path.basename(alvo_fast),
                        dec.get("antes", "?"), dec.get("depois", "?")))
            tempos = list(meta_pre.get("tempos") or [])
            tempos.append((u"montagem do OAR_Fast", t_grav - t_rs))
            tempos.append((u"gravacao do OAR_Fast", time.time() - t_grav))
            try:
                self.log(u"OAR_Fast em %.0f s: %s" % (
                    time.time() - t0, u"; ".join(
                        u"%s %.1f s" % (n, s) for n, s in tempos)))
                _et = list(meta.get("etapas") or [])
                if _et:
                    self.log(u"  montagem do OAR_Fast por passo: %s"
                             % u"; ".join(u"%s %.1f s" % (n, s)
                                          for n, s in _et))
            except Exception:
                pass
            etapas = [{"etapa": u"%s" % n, "segundos": round(float(s), 1),
                       PARTE_DE: PAI_DO_FAST} for n, s in tempos]
            etapas.extend({"etapa": u"OAR_Fast: %s" % n,
                           "segundos": round(float(s), 1),
                           PARTE_DE: u"montagem do OAR_Fast"}
                          for n, s in list(meta.get("etapas") or []))
            return {"modo": MODO_FAST, "entregue": alvo_fast,
                    "oar_fast": alvo_fast, "oar": None, "full": None,
                    "estruturas": sorted(nomes.values()),
                    "estruturas_full": [], "fora": [],
                    "segundos": time.time() - t0, "tempos": tempos,
                    "etapas": etapas, "decimacao": dec,
                    "insumos": list(filtro.get("insumos") or []),
                    "oar_fora": [],
                    "oar_fora_por_regiao": dict(fora_regiao)}
        except Exception as e:
            motivo = motivo_do_erro(e)
            self.log(u"O CONJUNTO ENTREGUE NAO SAIU (OAR_Fast): %s"
                     % motivo[:200])
            self._tracinho()
            raise RuntimeError(u"conjunto entregue (OAR_Fast) nao saiu: %s"
                               % motivo[:300]) from e

    def plugins(self, cruas):
        import radai_sets
        feitos = []
        for task in sorted(cruas or {}):
            reg = radai_sets.PLUGIN_DA_TASK.get(task)
            if reg is None:
                continue
            try:
                vista = vista_do_plugin(task, cruas[task])
                if not len(vista):
                    continue
                if reg.get("achado"):
                    self.log(u"ACHADO: a task %s (ato declarado) sai no arquivo "
                             u"proprio %s — nunca no entregue"
                             % (task, radai_sets.rotulo_dicom(reg["cod"])))
                if self.conjunto(reg["cod"], vista, "nosso", derivar=False):
                    feitos.append(reg["cod"])
            except Exception as e:
                self.log(u"nao consegui gravar o plugin %s (%s) — os outros "
                         u"conjuntos nao foram afetados" % (task, str(e)[:120]))
                self._tracinho()
        return feitos

    def ai_completo_antigo(self, cruas, cads_da_serie=None, cervicais=None):
        juntas = UniaoDeCruas([m for m in (cruas or {}).values() if m])
        if not len(juntas):
            return None
        try:
            juntas, origem_full = self.engine.curar(
                juntas, {"cads": cads_da_serie or {}})
        except Exception as e:
            self.log("nao consegui curar o FULL (%s)" % str(e)[:120])
            self._tracinho()
            return None
        if cervicais:
            try:
                juntas = UniaoDeCruas([juntas, cervicais])
                origem_full = dict(origem_full or {})
                for _n in cervicais:
                    origem_full[_n] = "hnlnl"
                self.log("FULL: +%d nivel(is) cervical(is)"
                         % len(cervicais))
            except Exception as e:
                self.log("nao consegui juntar os niveis cervicais ao "
                         "FULL (%s)" % str(e)[:120])
                self._tracinho()
        return self.conjunto("full", juntas, "nosso", origem=origem_full,
                             derivar=True)

    def nv(self, masks):
        return self.conjunto("nv", masks, "nv")

    vista3d = nv

    def moose(self, masks):
        return self.conjunto("mse", masks, "moose")

    def cads(self, masks):
        return self.conjunto("cads", masks, "cads")

    def pelvicos(self, masks_nossas):
        return None

    def niveis_cervicais(self, masks):
        if not masks:
            return None
        # GUARDA: o `HNL_` é a camada publicada (o método dos autores), e não
        # a final do FULL.
        publicado = getattr(masks, "publicado", None)
        if publicado:
            masks = publicado
        try:
            import radai_hnlnl as _hn
            try:
                obs = _hn.observacoes_dos_niveis(masks)
            except Exception as e:
                obs = {}
                self.log("nao consegui montar a descricao dos niveis (%s) — "
                         "eles saem sem ela no DICOM" % str(e)[:120])
            # GUARDA: a uniao contem os niveis por definicao; sem declarar,
            # cada par uniao x nivel saia como SOBREPOSICAO no log.
            uniao = dict((n, {"suavizar_mm": 0.0, "recortar_por": (),
                              "contem": (u"Lvl_", u"LNL"), "descricao": u""})
                         for n in (_hn.NOME_DA_UNIAO, _hn.NOME_DA_UNIAO_NEUTRA)
                         if n in masks)
            return self.conjunto("hnl", masks, "hnlnl", derivar=False,
                                 rotulo=_hn.ROTULO_TPS, suavizar_mm=0.0,
                                 observacoes=obs, construcoes=uniao)
        except Exception as e:
            self.log("nao consegui gravar o conjunto dos niveis cervicais "
                     "(%s) — o contorno entregue nao foi afetado" % str(e)[:140])
            self._tracinho()
            return None


MODO_FAST = "fast"
MODO_AUTO = "auto"
MODO_PERSO = "perso"


def _juntar_orgaos_dos_motores(masks, origem, extras, log=None):
    orgaos = dict((extras or {}).get("orgaos") or {})
    if not orgaos:
        return masks, origem
    # GUARDA: sem copiar `masks` -- ele e a sobreposicao preguicosa de `curar`,
    # e `dict(masks)` materializaria todas as mascaras cruas de uma vez
    origem = dict(origem or {})
    de = dict((extras or {}).get("origem") or {})
    ja = []
    for k, m in orgaos.items():
        if k in masks:
            ja.append(k)
            continue
        masks[k] = m
        origem[k] = de.get(k, u"motor")
    if log:
        try:
            log(u"FULL: +%d estrutura(s) dos motores do FULL%s" % (
                len(orgaos) - len(ja),
                (u" (ja vinham de outra fonte: %s)" % u", ".join(sorted(ja)))
                if ja else u""))
        except Exception:
            pass
    return masks, origem


def _juntar_alvos_dos_motores(masks, origem, construcoes, observacoes,
                              extras, permitidos, log=None):
    import radai_motores_full
    alvos = dict((extras or {}).get("alvos") or {})
    obs = dict((extras or {}).get("observacoes") or {})
    for k, texto in obs.items():
        if k in (extras or {}).get("orgaos", {}) and texto:
            observacoes[k] = texto
    if not alvos:
        return
    radai_motores_full.conferir_destinos(extras, permitidos)
    de = dict((extras or {}).get("origem") or {})
    for k, m in alvos.items():
        masks[k] = m
        origem[k] = de.get(k, u"motor")
        construcoes[k] = {
            "suavizar_mm": 0.0, "recortar_por": (), "contem": (),
            "descricao": u""}
        if obs.get(k):
            observacoes[k] = obs[k]
    if log:
        try:
            log(u"FULL: +%d alvo(s) dos motores do FULL (nunca no OAR)"
                % len(alvos))
        except Exception:
            pass


def normalizar_modo(valor):
    try:
        import radai_modes
        return radai_modes.normalizar_modo(valor)
    except Exception:
        v = str(valor or "").strip().lower()
        return v if v in (MODO_FAST, MODO_AUTO, MODO_PERSO) else MODO_AUTO


def permitidos_do_oar(oar_fora=None, log=None, engine=None):
    import radai_sets
    base = radai_sets.PERMITIDOS_NO_OAR
    pedidos = []
    if isinstance(oar_fora, (list, tuple, set, frozenset)):
        pedidos = [str(x or "").strip() for x in oar_fora]
    elif oar_fora:
        pedidos = [s.strip() for s in str(oar_fora).replace(";", ",")
                   .split(",")]
    pedidos = [p for p in pedidos if p]
    if not pedidos:
        return base, []
    por_nome = {}
    for k in base:
        por_nome[str(k).lower()] = k
    try:
        if engine is None:
            import engine as _e
            engine = _e
        for k in base:
            nf = str(engine.nome_clinico(k))
            por_nome.setdefault(nf.lower(), k)
    except Exception:
        pass
    for nova, velha in (getattr(radai_sets, "MESMA_ROI_NO_OAR", None)
                        or {}).items():
        if nova in base:
            por_nome.setdefault(str(velha).lower(), nova)
    tiradas, ignoradas = [], []
    for p in pedidos:
        k = por_nome.get(p.lower())
        if k is None:
            ignoradas.append(p)
        else:
            for par in radai_sets.chaves_da_mesma_roi(k):
                if par in base and par not in tiradas:
                    tiradas.append(par)
    if log:
        try:
            if tiradas:
                log(u"OAR desta serie SEM %s (tirada(s) com o «x»; ficam no "
                    u"FULL)" % u", ".join(tiradas))
            if ignoradas:
                log(u"oar_fora: ignorei %s — nao esta(o) na lista do OAR"
                    % u", ".join(ignoradas))
        except Exception:
            pass
    return frozenset(base - set(tiradas)), tiradas


def permitidos_do_protocolo(protocolo, oar_fora=None, log=None):
    import radai_sets
    p = dict(protocolo or {})
    sel = radai_sets.selecao_do_protocolo(p)
    if isinstance(oar_fora, (list, tuple, set, frozenset)):
        pedidos = set(str(x or "").strip() for x in oar_fora)
    else:
        pedidos = set(s.strip() for s in str(oar_fora or "").replace(
            ";", ",").split(","))
    pedidos.discard("")
    try:
        import engine as _e
        _clinico = _e.nome_clinico
    except Exception:
        _clinico = lambda k: k
    tiradas = [k for k in sel["chaves"]
               if k in pedidos or _clinico(k) in pedidos]
    chaves = [k for k in sel["chaves"] if k not in tiradas]
    nome = u"%s" % (p.get("nome") or p.get("id") or u"?")
    if log:
        try:
            log(u"STUDY pelo protocolo proprio «%s»: %d estrutura(s) e %d "
                u"uniao(oes)" % (nome, len(chaves), len(sel["unioes"])))
            for item, motivo in sel["recusadas"]:
                log(u"STUDY: protocolo proprio «%s»: %s nao entra (%s)"
                    % (nome, item, motivo))
            if tiradas:
                log(u"STUDY desta serie SEM %s (tirada(s) com o «x»; ficam "
                    u"no FULL)" % u", ".join(tiradas))
        except Exception:
            pass
    return frozenset(chaves), tiradas, list(sel["unioes"])


def _dizer_fora_por_regiao(fora_regiao, nomes, log, arquivo, destino,
                           engine=None):
    if not fora_regiao or not log:
        return
    try:
        _n = dict(nomes or {})
    except Exception:
        _n = {}
    for k in sorted(fora_regiao):
        nome = _n.get(k)
        if nome is None:
            try:
                nome = engine.nome_clinico(k)
            except Exception:
                nome = k
        try:
            log(u"%s desta serie SEM %s (%s): %s — %s"
                % (arquivo, nome, k, fora_regiao[k], destino))
        except Exception:
            pass


def _ilhas_do_arquivo(ilhas, nomes, log=None):
    ilhas = list(ilhas or [])
    try:
        chaves = set(str(k) for k in dict(nomes or {}))
    except Exception:
        return ilhas
    if not chaves:
        return ilhas
    fica = [x for x in ilhas if str(x.get("nome")) in chaves]
    tirou = [str(x.get("nome")) for x in ilhas
             if str(x.get("nome")) not in chaves]
    if tirou and log:
        try:
            log(u"ilhas em revisao: %d fora da lista — nao estao neste "
                u"arquivo (%s)" % (len(tirou), u", ".join(sorted(tirou))))
        except Exception:
            pass
    return fica


def _apagar_temp_do_oar(rt_oar, engine=None):
    try:
        import shutil
        prefixo = getattr(engine, "PREFIXO_TEMP_DO_OAR", None)
        pasta = os.path.dirname(str(rt_oar or ""))
        if (prefixo and pasta and os.path.basename(pasta).startswith(prefixo)
                and os.path.isdir(pasta)):
            shutil.rmtree(pasta, ignore_errors=True)
    except Exception:
        pass


def _apagar_temp_do_rs(rt, engine=None):
    try:
        import shutil
        prefixo = getattr(engine, "PREFIXO_TEMP_DO_RS", None)
        pasta = os.path.dirname(str(rt or ""))
        if (prefixo and pasta and os.path.basename(pasta).startswith(prefixo)
                and os.path.isdir(pasta)):
            shutil.rmtree(pasta, ignore_errors=True)
    except Exception:
        pass


def motivo_do_erro(e):
    nome = type(e).__name__
    texto = str(e).strip()
    return u"%s: %s" % (nome, texto) if texto else nome


def _aceita(fn, nome):
    try:
        import inspect
        params = inspect.signature(fn).parameters
    except (TypeError, ValueError):
        return False
    if any(p.kind == p.VAR_KEYWORD for p in params.values()):
        return True
    return nome in params



def cruas_da_base(cruas):
    if not cruas:
        return None
    try:
        import radai_tasks as _rt
        familia = _rt.familia_da_task
    except Exception:
        familia = lambda t: t
    for task in cruas:
        if familia(task) == "total":
            return cruas[task]
    return None


class _VasosDoPescoco(object):

    def __init__(self, fontes):
        self._f = dict(fontes)

    def __contains__(self, k):
        return k in self._f

    def __getitem__(self, k):
        return self._f[k][k]

    def __len__(self):
        return len(self._f)

    def get(self, k, padrao=None):
        return self[k] if k in self else padrao


def _vasos_do_pescoco(hn, cruas, base):
    fora = {}
    fontes = [base]
    try:
        fontes += [m for _k, m in sorted((cruas or {}).items(),
                                        key=lambda kv: str(kv[0]))
                   if m is not base]
    except Exception:
        pass
    for nome in getattr(hn, "VASOS_DO_PESCOCO", ()):
        for m in fontes:
            try:
                if m is not None and nome in m:
                    fora[nome] = m
                    break
            except Exception:
                continue
    return _VasosDoPescoco(fora)


def _parotidas_do_ts():
    import radai_hnlnl as hn
    return hn, dict(hn.PAROTIDAS_DO_TS)


def _parotida_do_ts_so_no_full(masks, sufixo_por_roi, observacoes,
                               fora_substituidas, permitidos):
    hn, do_ts = _parotidas_do_ts()
    for lado in ("left", "right"):
        ts = do_ts[lado]
        if ts not in masks:
            continue
        com_viii = hn.PAROTIDAS_DO_VIII[lado] in masks
        sufixo_por_roi[ts] = u"_ts"
        observacoes[ts] = hn.descricao_da_parotida_ts(lado, com_viii)
        fora_substituidas[ts] = (
            u"substituida pela parotida do nivel VIII" if com_viii else
            u"a parotida do STUDY vem so dos niveis cervicais, e eles nao a "
            u"deram nesta serie")
    return frozenset(set(permitidos) - set(do_ts.values()))


def _parotidas_do_viii_no_full(hn, cervicais, masks, grade, log):
    if hn is None:
        return {}
    viii = dict(getattr(cervicais, "viii", None) or {})
    sem_lado = set(getattr(cervicais, "sem_lado", None) or ())
    if not viii:
        for lado, i in hn.INDICE_DO_VIII.items():
            if i in sem_lado:
                log(u"FULL: a parotida %s continua a do TotalSegmentator (o "
                    u"lado do nivel VIII nao se confirmou)"
                    % (u"esquerda" if lado == "left" else u"direita"))
        return {}
    ecm = dict((lado, masks.get(k)) for lado, k in hn.ECM_DO_FULL.items()
               if masks.get(k) is not None)
    ts = dict((lado, masks.get(k)) for lado, k in hn.PAROTIDAS_DO_TS.items()
              if masks.get(k) is not None)
    feitas, motivos = hn.parotidas_do_viii(viii, ecm, grade, log=log, ts=ts)
    for lado, i in hn.INDICE_DO_VIII.items():
        if i in sem_lado:
            motivos[lado] = u"o lado do nivel VIII nao se confirmou"
    fora = {}
    for lado in ("left", "right"):
        chave = hn.PAROTIDAS_DO_VIII[lado]
        if chave in feitas:
            fora[lado] = (chave, feitas[chave], hn.PAROTIDAS_DO_TS[lado])
        else:
            log(u"FULL: a parotida %s continua a do TotalSegmentator (%s)"
                % (u"esquerda" if lado == "left" else u"direita",
                   motivos.get(lado, u"?")))
    return fora


def niveis_cervicais_da_serie(ref, cruas, device="cpu", log=None):
    import time

    def _log(m):
        if log:
            try:
                log(m)
            except Exception:
                pass

    import radai_hnlnl as HN
    ok, motivo = HN.disponivel()
    if not ok:
        _log(u"niveis cervicais: %s" % motivo)
        return {}
    base = cruas_da_base(cruas)
    if base is None:
        _log(u"niveis cervicais: nenhuma task da familia `total` (a base de "
             u"CT) deixou rotulos crus nesta execucao — sem eles nao ha "
             u"marco de recorte")
        return {}

    import radai_geom
    import SimpleITK as sitk
    forma = tuple(int(v) for v in reversed(ref.GetSize()))
    grade = radai_geom.Grade.de_sitk(ref)
    vol = sitk.GetArrayFromImage(ref).astype("float32")
    import radai_hnlnl_engine as HM
    disp = HM._torch_device(device)
    t0 = time.time()
    prova = None
    vasos = _vasos_do_pescoco(HN, cruas, base)
    try:
        masks = HN.rodar_na_serie(vol, base, forma, grade, device=disp,
                                  log=log, vasos=vasos)
    except Exception as e:
        prova = HM.erro_de_placa(e) if disp != "cpu" else None
        if not prova:
            raise
    if prova:
        _log(u"niveis cervicais: a placa falhou (%s) — refazendo em CPU; o "
             u"recorte e a reamostragem sao refeitos junto, e custam segundos"
             % prova)
        disp = "cpu"
        t0 = time.time()
        masks = HN.rodar_na_serie(vol, base, forma, grade, device=disp,
                                  log=log, vasos=vasos)
    if masks:
        _log(u"niveis cervicais: %d contorno(s) em %ds (%s, %s)"
             % (len(masks), int(time.time() - t0),
                u"CPU" if disp == "cpu" else u"placa", HN.rede_dos_niveis()))
    return masks


def relatorio(gravados):
    import radai_sets
    todos = [c["cod"] for c in radai_sets.CONJUNTOS if c["cod"] != "oar"]
    if "fast" in (gravados or []):
        todos = []
    fora = [c for c in todos if c not in (gravados or [])]
    return "conjuntos gravados: %s%s" % (
        ", ".join(gravados) if gravados else "nenhum",
        ("; sem conteudo nesta serie: " + ", ".join(fora)) if fora else "")


PARTE_DE = "parte_de"
PAI_DOS_PASSOS = u"FULL e OAR"
PAI_DO_FAST = u"OAR_Fast"
PAIS_DOS_PASSOS = (PAI_DOS_PASSOS, PAI_DO_FAST)
PASSO_DO_OAR = u"gravacao do OAR, antes do FULL"


def e_passo(etapa):
    return isinstance(etapa, dict) and bool(etapa.get(PARTE_DE))


def sem_os_passos(etapas):
    return [e for e in (etapas or ()) if isinstance(e, dict)
            and not e_passo(e)]


def etapas_do_caso(etapas, passos, segundos=None):
    lista = [dict(e) for e in (etapas or ()) if isinstance(e, dict)]
    ja = set((e.get("etapa"), e.get(PARTE_DE)) for e in lista if e_passo(e))
    novos = [dict(p) for p in (passos or ()) if e_passo(p)
             and (p.get("etapa"), p.get(PARTE_DE)) not in ja]
    if not novos:
        return lista
    raiz = PAI_DOS_PASSOS
    for p in novos:
        if p.get(PARTE_DE) in PAIS_DOS_PASSOS:
            raiz = p.get(PARTE_DE)
            break
    for i, e in enumerate(lista):
        if e.get("etapa") == raiz and not e_passo(e):
            return lista[:i + 1] + novos + lista[i + 1:]
    pai = {"etapa": raiz}
    if segundos is not None:
        pai["segundos"] = round(float(segundos), 1)
    return lista + [pai] + novos
