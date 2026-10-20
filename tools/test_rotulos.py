# -*- coding: utf-8 -*-
import os
import shutil
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8")
AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
APP = os.path.join(RAIZ, "app") if os.path.isdir(os.path.join(RAIZ, "app")) \
    else RAIZ
sys.path.insert(0, APP)
sys.path.insert(0, AQUI)
os.environ["RADAI_CALIB_DIR"] = tempfile.mkdtemp(prefix="radai_t_rotulos_calib_")
os.environ["RADAI_REGISTRO_DIR"] = tempfile.mkdtemp(prefix="radai_t_rotulos_reg_")
_TEMP_DA_BATERIA = tempfile.gettempdir()
import _cleanup
_cleanup.adotar_prefixo("radai_t_rotulos_")

import numpy as np

OK = 0
FALHOU = []


def secao(t):
    print(u"\n-- %s --" % t)


def checar(rotulo, cond, detalhe=""):
    global OK
    if cond:
        OK += 1
        print(u"  ok     %s" % rotulo)
    else:
        FALHOU.append(rotulo)
        print(u"  FALHA  %s  [%s]" % (rotulo, detalhe))


def teste_os_protocolos_de_estudo():
    secao(u"os protocolos das Reconstrucoes 3D")
    import radai_modes as M
    import radai_tasks as T
    import engine as E
    checar(u"o estudo 3D e ato declarado (origem ESTUDO)",
           M.ESTUDO in M.ATOS_DECLARADOS)
    cods = [p["cod"] for p in M.protocolos_3d_de("CT")]
    checar(u"na TC: Anatomia Geral e Anatomia Toracica",
           cods == ["anatomia_geral", "anatomia_toracica"], str(cods))
    checar(u"na RM: so a Anatomia Geral",
           [p["cod"] for p in M.protocolos_3d_de("MR")]
           == ["anatomia_geral_rm"])
    todas_ct = [d["task"] for d in T.CATALOGO
                if d.get("modalidade") == "CT"
                and T.familia_da_task(d["task"]) != "total"]
    geral = M.tasks_do_estudo_3d(["anatomia_geral"], "CT",
                                 permitidas=E.TASKS_PERMITIDAS,
                                 achados=E.TASKS_DE_ACHADO)
    checar(u"a Anatomia Geral roda a base e TODAS as tasks da TC (achados "
           u"inclusive): 19", geral[0] == "total_v3"
           and set(geral[1:]) == set(todas_ct) and len(geral) == 19,
           u"%d: %s" % (len(geral), u", ".join(geral)))
    checar(u"  e liga os niveis cervicais, e nenhuma comparacao de modelos",
           M.motores_do_estudo_3d(["anatomia_geral"], "CT") == ("hnlnl",))
    tor = M.tasks_do_estudo_3d(["anatomia_toracica"], "CT",
                               permitidas=E.TASKS_PERMITIDAS,
                               achados=E.TASKS_DE_ACHADO)
    esperado = ["total_v3", "trunk_cavities", "breasts", "abdominal_muscles",
                "vertebrae_body", "lung_vessels", "lung_vessels_LEGACY",
                "pleural_pericard_effusion", "lung_nodules"]
    checar(u"a Anatomia Toracica: a lista do autor (P4)", list(tor) == esperado,
           u", ".join(tor))
    fora = {"head_glands_cavities", "headneck_muscles", "headneck_bones_vessels",
            "head_muscles", "craniofacial_structures", "liver_segments",
            "hip_implant", "oculomotor_muscles", "teeth", "liver_lesions"}
    checar(u"  e sem cabeca e pescoco, segmentos e lesoes hepaticas, protese, "
           u"orbita e dentes", not (fora & set(tor)))
    checar(u"  e sem motor nenhum (comparacao em 0, sem niveis)",
           M.motores_do_estudo_3d(["anatomia_toracica"], "CT") == ())
    checar(u"  o achado entra (nodulos) e a trava nao levanta: e estudo",
           "lung_nodules" in tor)
    checar(u"as duas categorias da coluna: PROTOCOLOS RT e PROTOCOLOS "
           u"RECONSTRUCOES 3D, cada uma com a sua tabela (P1, P2)",
           [c["rotulo"] for c in M.CATEGORIAS_DE_PROTOCOLO]
           == [u"PROTOCOLOS RT", u"PROTOCOLOS RECONSTRUÇÕES 3D"]
           and all(hasattr(M, c["tabela"]) for c in M.CATEGORIAS_DE_PROTOCOLO))
    checar(u"os protocolos 3D NAO estao entre os protocolos RT",
           not (set(cods) & set(p["cod"] for p in M.PROTOCOLOS)))
    velho = M.ATOS_DECLARADOS
    try:
        M.ATOS_DECLARADOS = (M.MARCADO,)
        try:
            M.tasks_do_estudo_3d(["anatomia_toracica"], "CT",
                                 achados=E.TASKS_DE_ACHADO)
            lev = False
        except M.AchadoSemPedido:
            lev = True
    finally:
        M.ATOS_DECLARADOS = velho
    checar(u"ISCA: sem a origem ESTUDO, o achado do estudo levanta", lev)
    checar(u"a frase do log diz que o achado roda porque o estudo foi pedido",
           u"ACHADO: lung_nodules" in M.descricao_da_escolha(
               M.ESTUDO, tor, E.TASKS_DE_ACHADO)
           and u"estudo 3D foi pedido" in M.descricao_da_escolha(
               M.ESTUDO, tor, E.TASKS_DE_ACHADO))


def teste_o_mapa_de_rotulos():
    secao(u"o mapa de rotulos: grava, le, e nao confunde series")
    import radai_rotulos as R
    import engine as E
    import SimpleITK as sitk
    base = tempfile.mkdtemp(prefix="radai_t_rotulos_")
    try:
        lab = np.zeros((6, 20, 20), np.int16)
        lab[1:3, 2:8, 2:8] = 5
        lab[3:5, 10:15, 10:15] = 9
        cru_total = E.MasksCruas(lab, {5: "liver", 9: "spleen"})
        v1 = np.zeros((6, 20, 20), np.int16)
        v1[0:2, 0:5, 0:5] = 1
        cru_novo = E.MasksCruas(v1, {1: "lung_trachea_bronchia"})
        legado = {"lung_trachea_bronchia": np.zeros((6, 20, 20), bool)}
        legado["lung_trachea_bronchia"][4:6, 15:20, 15:20] = True
        nod = {"lung_nodules": np.zeros((6, 20, 20), bool)}
        nod["lung_nodules"][2, 5, 5] = True
        ref = sitk.GetImageFromArray(np.zeros((6, 20, 20), np.int16))
        ref.SetSpacing((1.0, 1.0, 3.0))
        uid = "1.2.3.4.5.6.7.8.99887766"
        cruas = {"total_v3": cru_total, "lung_vessels": cru_novo,
                 "lung_vessels_LEGACY": legado, "lung_nodules": nod}
        alvo = R.gravar(base, uid, cruas, ref=ref,
                        protocolos=["anatomia_toracica"], modalidade="CT",
                        achados=E.TASKS_DE_ACHADO, versao="bateria")
        checar(u"grava em _RadAI, com o fim do UID no nome, comprimido",
               os.path.isfile(alvo)
               and os.path.basename(os.path.dirname(alvo)) == "_RadAI"
               and os.path.basename(alvo) == "rotulos_99887766.npz")
        checar(u"  e nenhum RTSTRUCT na pasta",
               not [n for n in os.listdir(base) if n.startswith("RS_")])
        m = R.ler(base, uid)
        checar(u"le de volta", m is not None)
        if m is None:
            return
        checar(u"os nomes do novo e do legado nao colidem",
               "lung_trachea_bronchia" in m.nomes
               and "lung_trachea_bronchia_legacy" in m.nomes, str(m.nomes))
        checar(u"cada mascara volta voxel a voxel",
               np.array_equal(m.mascara("liver"), lab == 5)
               and np.array_equal(m.mascara("spleen"), lab == 9)
               and np.array_equal(m.mascara("lung_trachea_bronchia_legacy"),
                                  legado["lung_trachea_bronchia"]))
        checar(u"o achado vem marcado (o selo ACHADO da tela)",
               m.achados() == ["lung_nodules"], str(m.achados()))
        checar(u"a meta guarda protocolo, modalidade e geometria, sem PHI",
               m.meta["protocolos"] == ["anatomia_toracica"]
               and m.meta["modalidade"] == "CT"
               and m.meta["geometria"]["spacing"] == [1.0, 1.0, 3.0]
               and not [k for k in m.meta if "patient" in k.lower()
                        or k.lower() in ("pid", "nome")])
        checar(u"a serie com o mesmo fim de UID e outro UID NAO le este mapa",
               R.ler(base, "9.9.9.99887766") is None)
        checar(u"  e sem arquivo nenhum, `None`",
               R.ler(base, "1.2.3.11112222") is None)
        velho = R.ler

        def _sem_conferir(p, u):
            alvo = R.caminho(p, u)
            if not os.path.isfile(alvo):
                return None
            import json
            with np.load(alvo) as z:
                meta = json.loads(bytes(z["_meta"]).decode("ascii"))
                vols = dict((k, np.array(z[k])) for k in z.files
                            if k != "_meta")
            return R.Mapa(meta, vols)
        checar(u"ISCA: sem conferir o UID, a outra serie leria o mapa",
               _sem_conferir(base, "9.9.9.99887766") is not None)
        R.ler = velho
    finally:
        shutil.rmtree(base, ignore_errors=True)


def teste_a_porta_da_saida_grava_o_mapa():
    secao(u"a porta unica (`radai_output.Saida`) grava o mapa, sem RTSTRUCT")
    import engine as E
    import radai_output as RO
    import radai_rotulos as R
    from datetime import datetime
    from make_test_series import escreve_serie
    base = tempfile.mkdtemp(prefix="radai_t_rotulos_")
    try:
        serie = os.path.join(base, "serie")
        escreve_serie(serie, "PAC_ROTULOS", datetime.now(), 8)
        ref = E.load_sitk(serie)
        import SimpleITK as sitk
        forma = sitk.GetArrayFromImage(ref).shape
        lab = np.zeros(forma, np.int16)
        lab[2:5, 40:60, 40:60] = 3
        linhas = []
        sd = RO.Saida(E, serie, serie, "RS_RadAI_20261004_99887766.dcm",
                      tasks=["total_v3"], versao="bateria",
                      log=linhas.append, modalidade="CT")
        uid = "1.2.3.99887766"
        alvo = sd.mapa_de_rotulos({"total_v3": E.MasksCruas(lab, {3: "liver"})},
                                  uid, protocolos=["anatomia_geral"])
        m = R.ler(serie, uid)
        checar(u"o mapa esta na pasta da serie, e le de volta",
               m is not None and os.path.dirname(os.path.dirname(alvo))
               == serie and np.array_equal(m.mascara("liver"), lab == 3))
        checar(u"  com a geometria da serie",
               m is not None and m.meta["geometria"]["size"]
               == [int(v) for v in ref.GetSize()])
        checar(u"  e nenhum RTSTRUCT gravado, e o log diz",
               not [n for n in os.listdir(serie) if n.startswith("RS_")]
               and any(u"mapa de rotulos" in l for l in linhas))
    finally:
        shutil.rmtree(base, ignore_errors=True)


def teste_o_done_grava_os_protocolos():
    secao(u"o `done` grava os protocolos pedidos")
    import radai_records as RR
    c = RR.campos_do_done("CT", ["total_v3"], protocolos=["anatomia_toracica"])
    checar(u"com protocolo, o campo vai", c.get("protocolos")
           == ["anatomia_toracica"], str(c.get("protocolos")))
    c0 = RR.campos_do_done("CT", ["total_v3"])
    checar(u"sem protocolo, o campo nao aparece (o done de antes fica igual)",
           "protocolos" not in c0)


def _serie_fantoma(destino, cortes=6):
    from pydicom.dataset import Dataset, FileDataset
    from pydicom.uid import ExplicitVRLittleEndian, generate_uid
    serie_uid, estudo_uid = generate_uid(), generate_uid()
    os.makedirs(destino, exist_ok=True)
    for i in range(cortes):
        meta = Dataset()
        meta.MediaStorageSOPClassUID = "1.2.840.10008.5.1.4.1.1.2"
        meta.MediaStorageSOPInstanceUID = generate_uid()
        meta.TransferSyntaxUID = ExplicitVRLittleEndian
        meta.ImplementationClassUID = generate_uid()
        ds = FileDataset(None, {}, file_meta=meta, preamble=b"\0" * 128)
        ds.SOPClassUID = meta.MediaStorageSOPClassUID
        ds.SOPInstanceUID = meta.MediaStorageSOPInstanceUID
        ds.Modality = "CT"
        ds.PatientName = "FANTOMA^TESTE"
        ds.PatientID = "FANTOMA001"
        ds.StudyInstanceUID = estudo_uid
        ds.SeriesInstanceUID = serie_uid
        ds.FrameOfReferenceUID = estudo_uid
        ds.SeriesNumber = 2
        ds.InstanceNumber = i + 1
        ds.StudyDate = ds.SeriesDate = "20260101"
        ds.SliceThickness = 3.0
        ds.ImagePositionPatient = [0.0, 0.0, i * 3.0]
        ds.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
        ds.PixelSpacing = [0.7, 0.7]
        ds.Rows = ds.Columns = 8
        ds.SamplesPerPixel = 1
        ds.PhotometricInterpretation = "MONOCHROME2"
        ds.BitsAllocated = ds.BitsStored = 16
        ds.HighBit = 15
        ds.PixelRepresentation = 1
        ds.RescaleIntercept, ds.RescaleSlope = 0, 1
        ds.PixelData = np.zeros((8, 8), dtype=np.int16).tobytes()
        ds.is_little_endian, ds.is_implicit_VR = True, False
        ds.save_as(os.path.join(destino, "IM%04d" % i), write_like_original=False)
    return serie_uid


def teste_o_rodar_agora_roda_o_estudo_3d():
    secao(u"o «Rodar agora» roda o estudo 3D, e o estudo nao chega ao TPS")
    import radai_batch as L
    import radai_modes as M
    import radai_queue_state as Q
    e = L.escolha_da_serie({"modo": "perso",
                            "protocolos_3d": ["anatomia_toracica", "xyz"]})
    checar(u"a escolha do PERSONALIZADO leva `protocolos_3d` normalizado",
           tuple(e.get("protocolos_3d") or ()) == ("anatomia_toracica",),
           str(e.get("protocolos_3d")))
    ea = L.escolha_da_serie({"modo": "auto",
                             "protocolos_3d": ["anatomia_toracica"]})
    checar(u"  e fora do PERSONALIZADO, nada", not ea.get("protocolos_3d"),
           str(ea.get("protocolos_3d")))
    corpo = L._com_escolhas_da_tela({"series": [
        {"uid": "1.2", "modo": "perso",
         "protocolos_3d": ["anatomia_toracica"]},
        {"uid": "1.3", "modo": "auto", "protocolos_3d": ["anatomia_geral"]}]})
    _s = corpo.get("series") if isinstance(corpo, dict) else corpo
    checar(u"a tela guarda `protocolos_3d` so no PERSONALIZADO",
           _s[0].get("protocolos_3d") == ["anatomia_toracica"]
           and "protocolos_3d" not in _s[1], str(_s))
    checar(u"a fila leva `protocolos_3d` na carga da escolha",
           "protocolos_3d" in Q._ESCOLHA)
    linhas = []
    lista, origem = L.tasks_iniciais(
        {"modo": "perso", "modalidade": "CT",
         "protocolos_3d": ["anatomia_toracica"]}, log=linhas.append)
    checar(u"a lista do estudo traz o achado pedido (lung_nodules)",
           origem == "perso" and "lung_nodules" in lista, str(lista))
    checar(u"  e o log anuncia com a palavra ACHADO",
           any(u"ACHADO" in l for l in linhas), u" | ".join(linhas)[:300])
    l0, _o = L.tasks_iniciais({"modo": "perso", "modalidade": "CT"})
    checar(u"  sem o estudo, o achado nao entra", "lung_nodules" not in l0,
           str(l0))
    so = L.tasks_so_do_estudo({"modo": "perso", "modalidade": "CT",
                               "protocolos_3d": ["anatomia_toracica"]})
    checar(u"as tasks SO do estudo sao conhecidas (o achado e a legada)",
           "lung_nodules" in so and "lung_vessels_LEGACY" in so
           and "trunk_cavities" not in so, str(so))
    cr = {"total_v3": {"liver": 1}, "lung_nodules": {"lung_nodule": 1},
          "trunk_cavities": {"mediastinum": 1}}
    ent = L.cruas_do_entregue(cr, so)
    checar(u"`cruas_do_entregue` tira o que so o estudo pediu",
           sorted(ent) == ["total_v3", "trunk_cavities"], sorted(ent))
    checar(u"  e sem estudo devolve tudo", sorted(L.cruas_do_entregue(cr, ()))
           == sorted(cr))

    import engine as E
    import radai_output as RO
    import radai_records as RG
    import SimpleITK as sitk
    base = tempfile.mkdtemp(prefix="radai_t_rotulos_lote_")
    pasta = os.path.join(base, "PAC", "CT")
    uid = _serie_fantoma(pasta)
    chamadas = {"full": [], "plugins": [], "cru": [], "mapa": [], "done": []}
    guardado = {}

    def _dublar(obj, nome, novo):
        guardado[(id(obj), nome)] = (obj, nome, getattr(obj, nome))
        setattr(obj, nome, novo)

    def _ref():
        img = sitk.Image(8, 8, 6, sitk.sitkInt16)
        img.SetSpacing((0.7, 0.7, 3.0))
        return img

    def _run(ref, t, **k):
        c = k.get("cruas")
        if isinstance(c, dict):
            c[t] = {"x_" + t: np.ones((6, 8, 8), bool)}
        return {"liver": 1}

    grava_o_rs = {"sim": True}

    class _Saida(object):
        def __init__(self, *a, **k):
            self.gravados = []

        def _alvo(self, infixo):
            return os.path.join(pasta, u"RS_RadAI_%sF_x.dcm" % infixo)

        def full_e_oar(self, cruas, **k):
            chamadas["full"].append(sorted(cruas))
            self.gravados.append("oar")
            if grava_o_rs["sim"]:
                with open(self._alvo(u""), "wb") as f:
                    f.write(b"\0" * 132 + b"DICM")
            return {"estruturas": ["Liver_ai"], "entregue": ""}

        def plugins(self, cruas):
            chamadas["plugins"].append(sorted(cruas))
            return []

        def totalsegmentator_cru(self, cruas):
            chamadas["cru"].append(sorted(cruas))

        def mapa_de_rotulos(self, cruas, uid, **k):
            chamadas["mapa"].append((sorted(cruas), dict(k)))
            return os.path.join(pasta, "_RadAI", "rotulos_x.npz")

        def __getattr__(self, nome):
            return lambda *a, **k: None

    class _Nada(object):
        def write_text(self, *a, **k):
            return 0

    marc = {"has_marker": lambda *a, **k: False,
            "claim": lambda *a, **k: True,
            "unclaim": lambda *a, **k: None,
            "renovar": lambda *a, **k: None,
            "m_path": lambda *a, **k: _Nada()}
    velho_cfg = dict(L._CFG)

    def _rodar():
        s = {"uid": uid, "pasta": pasta, "modalidade": "CT", "pid": "F",
             "curto": uid[-4:], "modo": "perso",
             "protocolos_3d": ["anatomia_toracica"],
             "comparacao": {"ts": 1}}
        return L._uma_serie(s, False, [], "cpu", None, 60, 60, None, marc,
                            "BATERIA", 3600, 0.0)
    try:
        _dublar(E, "copy_sorted", lambda arqs, stage: None)
        _dublar(E, "load_sitk", lambda stage: _ref())
        _dublar(E, "_resolve_device", lambda d: "cpu")
        _dublar(E, "run_ts_task", _run)
        _dublar(RO, "Saida", _Saida)
        _dublar(RG, "registrar_serie", lambda *a, **k: "")
        _dublar(L, "_marcar_done",
                lambda *a, **k: chamadas["done"].append(dict(k)))
        L._CFG.clear()
        r = _rodar()
        checar(u"a serie do estudo vai ate o fim", not r.get("erro"),
               str(r.get("erro"))[:300])
        f = chamadas["full"][-1] if chamadas["full"] else []
        checar(u"o FULL e o OAR nao recebem a task SO do estudo",
               bool(f) and "lung_nodules" not in f
               and "lung_vessels_LEGACY" not in f, str(f))
        p = chamadas["plugins"][-1] if chamadas["plugins"] else None
        checar(u"  nem os plugins (nenhum RTSTRUCT do achado)",
               p is not None and "lung_nodules" not in p, str(p))
        c = chamadas["cru"][-1] if chamadas["cru"] else None
        checar(u"  nem o TS cru", c is not None and "lung_nodules" not in c,
               str(c))
        mp = chamadas["mapa"][-1] if chamadas["mapa"] else None
        checar(u"o mapa de rotulos recebe tudo, achado inclusive, com os "
               u"protocolos", mp is not None and "lung_nodules" in mp[0]
               and list(mp[1].get("protocolos") or ())
               == ["anatomia_toracica"]
               and "lung_nodules" in (mp[1].get("achados") or ()), str(mp))
        d = chamadas["done"][-1] if chamadas["done"] else {}
        checar(u"o `done` grava os protocolos do estudo",
               (d.get("campos") or {}).get("protocolos")
               == ["anatomia_toracica"], str(d.get("campos"))[:300])
        _dublar(L, "cruas_do_entregue", lambda cruas, so: dict(cruas))
        chamadas["full"][:] = []
        _rodar()
        fi = chamadas["full"][-1] if chamadas["full"] else []
        checar(u"ISCA: sem o filtro, o achado do estudo chega ao FULL",
               "lung_nodules" in fi, str(fi))
        grava_o_rs["sim"] = False
        try:
            os.remove(os.path.join(pasta, u"RS_RadAI_F_x.dcm"))
        except OSError:
            pass
        chamadas["done"][:] = []
        rn = _rodar()
        checar(u"ISCA: a Saida que anuncia o OAR sem gravar o RTSTRUCT "
               u"reprova a serie, sem marcar pronta",
               u"nenhum RTSTRUCT RadAI" in str(rn.get("erro") or u"")
               and not chamadas["done"], str(rn.get("erro"))[:200])
    finally:
        for obj, nome, val in guardado.values():
            setattr(obj, nome, val)
        L._CFG.clear()
        L._CFG.update(velho_cfg)
        shutil.rmtree(base, ignore_errors=True)


def _isolada(raiz_acervo, raiz_registro, temp):
    t = os.path.normcase(os.path.abspath(temp)) + os.sep
    return [nome for nome, p in ((u"acervo", raiz_acervo),
                                 (u"registro de casos", raiz_registro))
            if not os.path.normcase(os.path.abspath(str(p))).startswith(t)]


def teste_a_serie_da_bateria_fica_no_temporario():
    secao(u"a serie que a bateria roda grava no temporario, e nao no acervo "
          u"nem no registro de quem roda")
    import radai_archive as A
    import radai_records as RG
    temp = _TEMP_DA_BATERIA
    fora = _isolada(A.raiz(), RG.raiz(), temp)
    checar(u"o acervo e o registro de casos desta bateria moram no "
           u"temporario", not fora, u", ".join(fora))
    checar(u"  e a serie do estudo gravou no acervo isolado (a bateria "
           u"alcanca o acervo)", os.path.isfile(os.path.join(
               os.environ["RADAI_CALIB_DIR"], "acervo.jsonl")))
    velho = {k: os.environ.pop(k, None) for k in ("RADAI_CALIB_DIR",
                                                  "RADAI_REGISTRO_DIR")}
    try:
        isca = _isolada(A.raiz(), RG.raiz(), temp)
    finally:
        for k, v in velho.items():
            if v is not None:
                os.environ[k] = v
    checar(u"  isca: sem as duas variaveis, o acervo e o registro saem do "
           u"temporario (reprova)", len(isca) == 2, u", ".join(isca))


def main():
    print(u"=" * 64)
    print(u"test_rotulos | protocolos de estudo 3D e o mapa de rotulos")
    print(u"=" * 64)
    for t in (teste_os_protocolos_de_estudo, teste_o_mapa_de_rotulos,
              teste_a_porta_da_saida_grava_o_mapa,
              teste_o_done_grava_os_protocolos,
              teste_o_rodar_agora_roda_o_estudo_3d,
              teste_a_serie_da_bateria_fica_no_temporario):
        try:
            t()
        except Exception as e:
            import traceback
            checar(u"%s (excecao inesperada)" % t.__name__, False,
                   u"%s: %s" % (type(e).__name__, e))
            traceback.print_exc()
    print()
    if FALHOU:
        print(u"FALHOU: %d de %d checagens" % (len(FALHOU), OK + len(FALHOU)))
        for f in FALHOU:
            print(u"  - %s" % f)
        return 1
    print(u"OK: %d checagens, todas passaram" % OK)
    return 0


if __name__ == "__main__":
    sys.exit(main())
