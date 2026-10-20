# -*- coding: utf-8 -*-
import io
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _cleanup
_cleanup.adotar_prefixo('radai_sim_')

import tempfile as _tf
os.environ['RADAI_CALIB_DIR'] = _tf.mkdtemp(prefix='radai_sim_acervo_')

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(RAIZ, "app")
sys.path.insert(0, APP)

_ok = 0
_falhou = 0
_falhas = []


def secao(t):
    print(u"")
    print(u"── %s %s" % (t, u"─" * max(0, 58 - len(t))))


def checar(rotulo, cond, detalhe=u""):
    global _ok, _falhou
    if cond:
        _ok += 1
        print(u"  OK     %s" % rotulo)
    else:
        _falhou += 1
        _falhas.append(rotulo)
        print(u"  FALHA  %s  %s" % (rotulo, str(detalhe).replace("\n", " | ")[:150]))


def serie(uid, esp, cortes=None, pasta=u"EXAME", cobertura=300.0):
    if cortes is None:
        cortes = max(2, int(round(float(cobertura) / float(esp))) + 1)
    return uid, {"uid": uid, "dir": pasta, "count": cortes,
                 "z0": 0.0, "z1": esp * (cortes - 1),
                 "esp_dec": None, "date": "18991332000000", "pid": "X"}


def exame(*series_):
    return dict(series_)


def teste_a_escada():
    secao(u"a escada: 5 mm > 3,75 mm > 2 mm > 1 mm")
    import radai_watcher as W

    DEGRAUS = [
        (u"5 mm ganha de 3,75", [5.00, 3.75], 5.00),
        (u"3,75 ganha de 2", [3.75, 2.00], 3.75),
        (u"2 ganha de 1", [2.00, 1.00], 2.00),
        (u"5 ganha de todos juntos", [1.00, 2.00, 3.75, 5.00], 5.00),
        (u"so 3,75 disponivel", [3.75], 3.75),
        (u"so 2 disponivel", [2.00], 2.00),
        (u"so 1 disponivel (radiocirurgia de cranio)", [1.00], 1.00),
    ]
    for rotulo, esps, esperada in DEGRAUS:
        s = exame(*[serie(u"1.2.%d" % i, e) for i, e in enumerate(esps)])
        esc = W.escolher_simulacao(s)
        checar(rotulo, len(esc) == 1, u"%d escolhidas" % len(esc))
        if len(esc) != 1:
            continue
        uid = list(esc)[0]
        checar(u"  e a escolhida tem %.2f mm" % esperada,
               abs(W.espessura_varrida(s[uid]) - esperada) < 0.01,
               u"escolheu %.2f mm" % W.espessura_varrida(s[uid]))


def teste_o_piso():
    secao(u"o piso: abaixo de 1 mm nao e TC de simulacao")
    import radai_watcher as W

    so_fina = exame(serie(u"1.1", 0.625), serie(u"1.2", 0.80))
    esc = W.escolher_simulacao(so_fina)
    checar(u"exame so com serie fina NAO entra na fila", not esc,
           u"%d escolhida(s) — o Rodar agora e' quem faz esse caso" % len(esc))

    mista = exame(serie(u"2.1", 0.625, cortes=400),
                  serie(u"2.2", 1.00, cortes=250))
    esc = W.escolher_simulacao(mista)
    checar(u"com uma de 1 mm ao lado, a de 0,625 nao e' escolhida",
           list(esc) == [u"2.2"], u"escolheu %s" % list(esc))

    quase = exame(serie(u"3.1", 1.0 - 1e-7))
    checar(u"1 mm com erro de arredondamento ainda passa no piso",
           len(W.escolher_simulacao(quase)) == 1,
           u"a folga e' %.2f mm" % W.SIM_FOLGA_MM)

    dedo = exame(serie(u"3.2", 0.90))
    checar(u"e 0,90 mm nao passa (a folga nao vira um piso novo)",
           not W.escolher_simulacao(dedo))


def teste_acima_do_teto():
    secao(u"acima do teto: ultima colocacao, e nao recusa")
    import radai_watcher as W

    grossa = exame(serie(u"4.1", 10.0))
    esc = W.escolher_simulacao(grossa)
    checar(u"exame so com serie de 10 mm ainda e' contornado", len(esc) == 1,
           u"recusar deixaria o exame sem contorno NENHUM")

    junto = exame(serie(u"5.1", 10.0), serie(u"5.2", 3.00))
    esc = W.escolher_simulacao(junto)
    checar(u"mas perde para a de 3 mm quando ela existe",
           list(esc) == [u"5.2"], u"escolheu %s" % list(esc))

    duas = exame(serie(u"6.1", 10.0), serie(u"6.2", 7.0))
    esc = W.escolher_simulacao(duas)
    checar(u"entre 10 e 7 mm, escolhe a de 7 (a mais proxima da faixa)",
           list(esc) == [u"6.2"], u"escolheu %s" % list(esc))


def teste_um_por_exame():
    secao(u"um por exame, e exame e' pasta")
    import radai_watcher as W

    s = {}
    for pasta, base in ((u"EXAME_A", 10), (u"EXAME_B", 20)):
        for i, e in enumerate((0.625, 1.25, 3.00, 5.00)):
            uid, rec = serie(u"9.%d.%d" % (base, i), e, pasta=pasta)
            s[uid] = rec
    esc = W.escolher_simulacao(s)
    checar(u"oito series em dois exames devolvem DUAS escolhidas",
           len(esc) == 2, u"%d escolhidas de %d series" % (len(esc), len(s)))
    esps = sorted(round(W.espessura_varrida(s[u]), 2) for u in esc)
    checar(u"e as duas sao as de 5,00 mm", esps == [5.00, 5.00], esps)

    motivos = [m for m in esc.values()]
    checar(u"cada escolhida traz o motivo por escrito",
           all(u"mm" in m for m in motivos), motivos[:1])


def teste_o_empate_de_espessura_vai_para_a_mais_recente():
    secao(u"empate de espessura: a mais recente ganha")
    import radai_watcher as W

    def s(uid, esp, cortes, date, n=0):
        return {"uid": uid, "espessura": esp, "espessura_mm": esp,
                "cortes": cortes, "count": cortes, "axial": True,
                "modalidade": "CT", "estudo": "E1", "date": date, "n": n,
                "desc": u"RECON %s" % uid}

    dentro = [s("A", 3.00, 200, "20260901"), s("B", 2.60, 231, "20260903")]
    esc = W.escolher_simulacao(dentro)
    checar(u"dentro da faixa, a mais RECENTE ganha da mais grossa",
           list(esc) == ["B"], u"escolhida: %s" % (list(esc) or u"nenhuma"))
    checar(u"  e o motivo diz que foi a data",
           u"mais recente" in (esc.get("B") or u""), (esc.get("B") or u"")[-60:])

    igual = [s("A", 3.00, 200, "20260905"), s("B", 2.60, 231, "20260901")]
    checar(u"sem inversao, a escada continua valendo",
           list(W.escolher_simulacao(igual)) == ["A"])

    fora = [s("A", 3.00, 200, "20260901"), s("B", 1.80, 334, "20260909")]
    checar(u"fora da faixa, a data NAO conta",
           list(W.escolher_simulacao(fora)) == ["A"],
           u"escolhida: %s" % (list(W.escolher_simulacao(fora)) or u"nenhuma"))


def teste_no_4d_a_avg_ganha_de_todas():
    secao(u"no 4D, a AVG ganha de todas")
    import radai_watcher as W

    def s(uid, esp, cortes, desc, n=0):
        return {"uid": uid, "espessura": esp, "espessura_mm": esp,
                "cortes": cortes, "count": cortes, "axial": True,
                "modalidade": "CT", "estudo": "E1", "date": "20260901",
                "n": n, "desc": desc}

    quatro_d = [s("AVG", 3.00, 200, u"CT THORAX AVE", 50)]
    for i in range(11):
        quatro_d.append(s("F%d" % i, 3.00, 200, u"CT THORAX %d%%" % (i * 10),
                          60 + i))
    esc = W.escolher_simulacao(quatro_d)
    checar(u"com 12 series, a AVG e' a escolhida",
           list(esc) == ["AVG"], u"escolhida: %s" % (list(esc) or u"nenhuma"))
    checar(u"  e o motivo diz que e' um 4D",
           u"4D" in (esc.get("AVG") or u""), (esc.get("AVG") or u"")[-70:])

    comum = [s("AVG", 3.00, 200, u"CT AVERAGE", 50)]
    for i in range(8):
        comum.append(s("F%d" % i, 4.00, 150, u"CT %d%%" % (i * 10), 60 + i))
    checar(u"com 9 series, «AVERAGE» no nome NAO decide",
           list(W.escolher_simulacao(comum)) != ["AVG"],
           u"escolhida: %s" % (list(W.escolher_simulacao(comum)) or u"nenhuma"))

    import radai_triage as TR
    checar(u"`AVE`, `AVG`, `AveIP` e `AVERAGE` contam",
           all(TR._e_media({"desc": d}) for d in
               (u"CT AVE", u"CT_AVG", u"AveIP 50%", u"THORAX AVERAGE")))
    checar(u"  e `MIP`/`MINIP` nao, nem palavra que so CONTEM as letras",
           not any(TR._e_media({"desc": d}) for d in
                   (u"CT MIP", u"MINIP TORAX", u"CAVERNA", u"WAVE")))


def teste_sem_medida():
    secao(u"sem medida nao se recusa")
    import radai_watcher as W

    cego = {u"7.1": {"uid": u"7.1", "dir": u"E", "count": 80,
                     "z0": None, "z1": None, "esp_dec": None,
                     "date": "18991332", "pid": "X"}}
    esc = W.escolher_simulacao(cego)
    checar(u"serie sem z e sem espessura declarada ainda entra",
           len(esc) == 1,
           u"deixar de contornar por nao ter conseguido medir e' o erro caro")

    dec = {u"8.1": {"uid": u"8.1", "dir": u"F", "count": 1,
                    "z0": None, "z1": None, "esp_dec": 3.0,
                    "date": "18991332", "pid": "X"}}
    checar(u"e a espessura DECLARADA serve de reserva",
           abs(W.espessura_varrida(dec[u"8.1"]) - 3.0) < 0.001,
           W.espessura_varrida(dec[u"8.1"]))


def teste_a_conta_fecha_no_dicom():
    secao(u"do DICOM ate a decisao, sobre fantoma")
    try:
        import numpy as np
        import pydicom
        from pydicom.dataset import Dataset, FileMetaDataset
        from pydicom.uid import ExplicitVRLittleEndian, generate_uid
    except Exception as e:
        print(u"  (pulado: %s)" % e)
        return
    import radai_watcher as W

    base = tempfile.mkdtemp(prefix="radai_sim_")
    try:
        for esp, n in ((3.0, 30), (1.0, 60)):
            uid = generate_uid()
            for i in range(n):
                fm = FileMetaDataset()
                fm.MediaStorageSOPClassUID = "1.2.840.10008.5.1.4.1.1.2"
                fm.MediaStorageSOPInstanceUID = generate_uid()
                fm.TransferSyntaxUID = ExplicitVRLittleEndian
                ds = Dataset()
                ds.file_meta = fm
                ds.SOPClassUID = fm.MediaStorageSOPClassUID
                ds.SOPInstanceUID = fm.MediaStorageSOPInstanceUID
                ds.SeriesInstanceUID = uid
                ds.StudyInstanceUID = "1.2.3.4"
                ds.Modality = "CT"
                ds.PatientID = "FANTOMA"
                ds.SeriesDate = "18991332"
                ds.SliceThickness = esp
                ds.ImagePositionPatient = [0.0, 0.0, i * esp]
                ds.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
                ds.PixelSpacing = [1.0, 1.0]
                ds.Rows = ds.Columns = 8
                ds.BitsAllocated = 16
                ds.BitsStored = 16
                ds.HighBit = 15
                ds.PixelRepresentation = 1
                ds.SamplesPerPixel = 1
                ds.PhotometricInterpretation = "MONOCHROME2"
                ds.PixelData = np.zeros((8, 8), dtype=np.int16).tobytes()
                ds.save_as(os.path.join(base, "%s_%03d.dcm" % (esp, i)),
                           enforce_file_format=True)

        cfg = os.path.join(base, "sim.config")
        io.open(cfg, "w", encoding="utf-8").write(
            u"ROOT=%s\nDRY_RUN=1\nMIN_SLICES=20\nPORT=8798\n"
            u"QUIET_MIN=0\n" % base)
        os.environ["RADAI_CONFIG"] = cfg
        import pathlib
        W.CFG_PATH = pathlib.Path(cfg)
        W.CACHE_PATH = pathlib.Path(base) / "index.json"
        W.CFG = W.load_cfg()
        W.aplicar_cfg()
        checar(u"a bateria varre o FANTOMA, e nao o share da maquina",
               os.path.normcase(str(W.ROOT).rstrip("\\/"))
               == os.path.normcase(base.rstrip("\\/")),
               u"ROOT=%s" % W.ROOT)
        if os.path.normcase(str(W.ROOT).rstrip("\\/")) != \
                os.path.normcase(base.rstrip("\\/")):
            return

        series, _ = W.scan_root()
        checar(u"a varredura achou as duas series", len(series) == 2,
               u"%d serie(s)" % len(series))

        medidas = sorted(round(W.espessura_varrida(s), 2)
                         for s in series.values())
        checar(u"e mediu 1,00 e 3,00 mm a partir do z dos arquivos",
               medidas == [1.00, 3.00], medidas)

        esc = W.escolher_simulacao(series)
        checar(u"a escolha entrega UMA serie", len(esc) == 1,
               u"%d escolhida(s)" % len(esc))
        if len(esc) == 1:
            uid = list(esc)[0]
            checar(u"e e' a de 3,00 mm — a de simulacao",
                   abs(W.espessura_varrida(series[uid]) - 3.0) < 0.01,
                   u"escolheu %.2f mm" % W.espessura_varrida(series[uid]))

        fila = W.build_queue(series, [])
        checar(u"a FILA traz uma serie so", len(fila) == 1,
               u"%d na fila" % len(fila))
        if fila:
            checar(u"com o motivo por escrito",
                   u"simulacao" in (fila[0].get("porque") or u"").lower(),
                   fila[0].get("porque"))

        rev = W.plano_de_execucao()
        exames = rev.get("exames") or []
        checar(u"a previa enxerga o exame", len(exames) == 1,
               u"%d exame(s): %s" % (len(exames), rev.get("erro") or ""))
        if exames:
            linhas = exames[0].get("series") or exames[0].get("linhas") or []
            a_fazer = [l for l in linhas if l.get("estado") == "a_fazer"]
            checar(u"e marca UMA serie como a_fazer", len(a_fazer) == 1,
                   u"%s" % [(l.get("estado"), l.get("cortes")) for l in linhas])
            if a_fazer and fila:
                checar(u"e e' a MESMA que a fila escolheu",
                       str(a_fazer[0].get("uid", ""))[-8:]
                       == str(fila[0].get("uid", ""))[-8:],
                       u"previa=%s fila=%s"
                       % (a_fazer[0].get("uid"), fila[0].get("uid")))
            pulada = [l for l in linhas if l.get("estado") == "pulado"]
            checar(u"e a pulada explica pela espessura, nao por cortes",
                   bool(pulada) and u"mm" in (pulada[0].get("detalhe") or u""),
                   pulada[0].get("detalhe") if pulada else u"(nenhuma pulada)")
    finally:
        os.environ.pop("RADAI_CONFIG", None)
        shutil.rmtree(base, ignore_errors=True)


def teste_o_4d_nao_elege_uma_fase():
    secao(u"o 4D nao elege uma fase")
    import radai_watcher as W

    d = {}
    d[u"vol"] = {"uid": u"vol", "estudo": u"ST", "dir": u"P/S003",
                 "count": 200, "z0": 0.0, "z1": 2.0 * 199, "esp_dec": None,
                 "date": "18991332000000", "pid": u"FANTOMA"}
    fases = [(29, 3.00), (34, 3.00), (35, 3.18), (36, 3.51), (37, 4.08),
             (38, 4.62), (39, 5.13), (36, 5.74), (31, 6.70), (29, 7.18)]
    for i, (n, e) in enumerate(fases):
        d[u"f%d" % i] = {"uid": u"f%d" % i, "estudo": u"ST",
                         "dir": u"P/S%03d" % (10 + i), "count": n,
                         "z0": 0.0, "z1": e * (n - 1), "esp_dec": None,
                         "date": "18991332000000", "pid": u"FANTOMA"}

    esc = W.escolher_simulacao(d)
    checar(u"o estudo inteiro rende UMA sugestao, e nao 31",
           len(esc) == 1, u"%d sugerida(s): %s" % (len(esc), sorted(esc)))
    checar(u"e a escolhida e a aquisicao, nao uma fase",
           list(esc) == [u"vol"], u"escolheu %s" % list(esc))
    if esc:
        motivo = list(esc.values())[0]
        checar(u"e o motivo diz que foi a COBERTURA, e nao a espessura",
               u"cobre" in motivo.lower(), motivo)
        checar(u"  e nao mente dizendo `a mais grossa`",
               u"mais grossa" not in motivo.lower(), motivo)

    normal = exame(serie(u"n1", 5.00), serie(u"n2", 2.00), serie(u"n3", 1.00))
    esc2 = W.escolher_simulacao(normal)
    checar(u"exame normal continua escolhendo a mais grossa da faixa",
           list(esc2) == [u"n1"], u"escolheu %s" % list(esc2))

    quase = exame(serie(u"q1", 5.00, cobertura=300.0),
                  serie(u"q2", 2.00, cobertura=294.0))
    esc3 = W.escolher_simulacao(quase)
    checar(u"6 mm de diferenca de cobertura nao muda a decisao",
           list(esc3) == [u"q1"], u"escolheu %s" % list(esc3))


def main():
    print(u"=" * 66)
    print(u"test_dryrun | a escada da TC de simulacao")
    print(u"=" * 66)
    teste_a_escada()
    teste_o_piso()
    teste_acima_do_teto()
    teste_um_por_exame()
    teste_o_4d_nao_elege_uma_fase()
    teste_o_empate_de_espessura_vai_para_a_mais_recente()
    teste_no_4d_a_avg_ganha_de_todas()
    teste_sem_medida()
    teste_a_conta_fecha_no_dicom()
    print(u"\n" + u"=" * 66)
    if _falhou:
        print(u"FALHOU: %d de %d checagens" % (_falhou, _ok + _falhou))
        for f in _falhas:
            print(u"  - %s" % f)
    else:
        print(u"OK: %d checagens, todas passaram" % _ok)
    print(u"=" * 66)
    return 1 if _falhou else 0


if __name__ == "__main__":
    sys.exit(main())
